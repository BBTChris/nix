#!/usr/bin/env python3
"""`check_go_timeout` — §4:210-212's deadlock breaker, measured on a REAL process.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen risk spec.

WHAT THIS GATE EXISTS BECAUSE OF
--------------------------------
ARC 038 (sub-agent F) SIGKILLed the process holding a GO and measured the
one-in-flight lock still held **11.0 s past a 10 s knob**. §14:971 states the
invariant outright — *"One in-flight action per strategy — and it can never
wedge (GO-timeout)"* — and §4:210-212 gives the mechanism:

    if a strategy receives no sized/denied feedback within T of emitting GO
    (e.g. Allocator died holding it), it treats the GO as denied and resets to
    flat-and-free. The in-flight lock can never wedge on a lost message.

The knob `limiter.go_timeout_s` existed and NOTHING READ IT. That precise state
— *knob present, knob unread* — is what this gate has to be able to redden on,
because it is the state the system was actually in while every other Limiter
gate was green.

TWO ARMS, AND WHY NEITHER ALONE IS THE CHECK
--------------------------------------------
1. **THE STATIC ARM** names the reader. A shipped module outside
   `scripts/risk_config.py`'s cross-knob boot validator must read
   `go_timeout_s`, and the finding NAMES the site when none does. On its own
   this arm is a grep, and a grep passes over a module that reads the knob into
   a variable it never compares against anything.
2. **THE LIVE ARM** drives a real `limiterd` process: registers a strategy,
   admits a real GO, abandons it with NO terminal feedback, and watches the lock
   through the process's own `status` verb until it comes off. On its own this
   arm cannot say WHY a release did not happen, which is the sentence an
   operator needs at 03:00.

Together the failure is named at its site and demonstrated at its subject.

`debug.md` §7.12 — THE STANDING QUESTION: what would have to be true for this
gate to go green while measuring nothing?

  1. **The live arm never got a GO admitted**, so it watched an empty registry
     release nothing and called that a release. CLOSED, and this is the
     NON-VACUITY assertion: the drive REQUIRES the status verb to report the
     lock HELD at least once before it may report a release. A run that never
     observed the held state returns CANNOT_MEASURE, never PASS (§17 / check
     contract v2 rule 10 — a property proven while its subject is unavailable is
     not proven).
  2. **The breaker fires on EVERY GO**, healthy ones included, and the lock is
     always free so the drive always passes. CLOSED by the SECOND live arm: a GO
     that receives terminal feedback before T must be released by that feedback
     and must NOT appear in the process's `go_timeouts` rows. Order flow that is
     shredded by a breaker firing on everything reds this gate.
  3. **The timeout is configured so large that the drive's window is the
     property.** CLOSED: the drive passes its own `--go-timeout`, and the
     measured `elapsed_s` is asserted against the T THE PROCESS REPORTS in its
     own record, not against the number the gate hoped for.
  4. **The release was a DEREGISTRATION** — the lock came off because the
     strategy was torn down, which is §4:266-268 and not §4:211-212's
     flat-and-FREE. CLOSED: the drive asserts the registration SURVIVES.
  5. **The breaker released and re-placed the order.** CLOSED: `resent` is
     asserted `False` on every row (§4:240-241 — *"never auto-resend"*).
  6. **`limiterd` never actually ran** and the gate read a stale record from a
     previous run. CLOSED: the runtime directory is fresh per drive, and the
     record's `pid` must equal the pid this gate spawned.
"""

from __future__ import annotations

import ast
import json
import os
import signal
import subprocess  # nosec B404 - the subject is a REAL limiterd PROCESS
import sys
import tempfile
import time
from pathlib import Path
from typing import IO, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
DEPENDS_ON: tuple[str, ...] = ()
#: This gate SPAWNS a `limiterd` subprocess and writes a fresh temp runtime
#: directory. It imports nothing out of `ctx.nix_home`, deliberately: the
#: subject is a PROCESS, and importing the loop into this interpreter would
#: measure the library ARC 038 already proved is not the same thing.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:python",
    "subprocess:python3",
)
#: NON-CORRECTABLE: the subject is risk-path source — the deadlock breaker on
#: the lock that gates every order. A gate empowered to edit it until its own
#: drive came back clean would be manufacturing green over §14:971.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/loop.py's §4:210-212 "
    "deadlock breaker); a repair that edited it to satisfy its own gate is the "
    "same class of action risk spec §4 forbids on the order path"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/loop.py",
    "scripts/limiterd.py",
)

NAME = "check_go_timeout"

LOOP_FILE = "scripts/nixrisk/loop.py"
LIMITERD_FILE = "scripts/limiterd.py"
CONFIG_FILE = "risks/limiter.config.json"
KNOB = "go_timeout_s"
#: The ONE shipped module allowed to read the knob without being an
#: implementation of the breaker: it is the cross-knob boot validator, and it
#: validates the value rather than acting on it (ARC 038's own census).
VALIDATOR = "scripts/risk_config.py"

#: The drive's T. Small so the gate is cheap; §12.11 makes the config
#: restart-only, and the CLI override exists precisely so a control may state
#: its own cadence. Every assertion is made against the T THE PROCESS REPORTS.
DRIVE_TIMEOUT_S = 2.0
DRIVE_TICK_S = 0.02
DRIVE_HEARTBEAT_S = 0.4
#: How long the drive may watch before calling the lock wedged. 4x T: ARC 038
#: measured 11 s past a 10 s knob, so a breaker that is merely late by more than
#: its own T again is the defect and not a slow box.
WATCH_HORIZON = DRIVE_TIMEOUT_S * 4.0
BOOT_TIMEOUT_S = 20.0
REPLY_TIMEOUT_S = 15.0

STRATEGY = "check-go-timeout-s1"
LOST_CID = "cid-lost"
FED_CID = "cid-fed"


class Finding(NamedTuple):
    """One violation: the site that owns it and why it is one."""

    site: str
    why: str


class Cannot(Exception):
    """The subject could not be observed. CANNOT_MEASURE, never PASS (§17)."""


class _Wedged(Exception):
    """Internal: the lock never came off, so the remaining arms cannot run.

    NOT a `Cannot`. The wedge is the DEFECT this gate exists to find and it has
    already been recorded as a finding by the time this is raised; it unwinds the
    drive without letting the second arm's consequential refusal overwrite the
    verdict with CANNOT_MEASURE.
    """


# ---------------------------------------------------------------------------
# ARM 1 — the static reader census (names the UNREAD KNOB at its site)
# ---------------------------------------------------------------------------
def _shipped_modules(home: Path) -> list[Path]:
    """`scripts/**.py` minus `scripts/tests/`. The shipped population."""
    scripts = home / "scripts"
    return [
        path
        for path in sorted(scripts.rglob("*.py"))
        if "tests" not in path.relative_to(scripts).parts
        and "__pycache__" not in path.parts
    ]


def _names_the_knob(path: Path, rel: str) -> bool:
    """Does this module contain the knob key as a STRING LITERAL?

    A LITERAL, via the AST, and not the substring `go_timeout_s` anywhere in the
    file. MEASURED, on this arc: a substring census called `scripts/limiterd.py`
    a reader because the key appears in an argparse help string and as a keyword
    argument NAME, and it called `scripts/nixrisk/loop.py` a reader because
    `go_timeout_s` is a parameter of its constructor. Under a plant that renamed
    the only real config key away, that census stayed green — it was measuring
    the spelling of an identifier, not a read of `risks/limiter.config.json`.

    THIS ARM IS A CENSUS AND NOT A PROOF OF MECHANISM, stated plainly: a module
    could hold the literal and never compare anything to the value behind it.
    That is what the LIVE arm below is for. What this arm owns is the ONE state
    a live drive cannot name — the knob with no reader at all, which is the
    state ARC 038 (F) measured — and it names the file.
    """
    try:
        tree = ast.parse(path.read_text(), filename=rel)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.Constant) and node.value == KNOB for node in ast.walk(tree)
    )


def _arm_knob_is_read(home: Path) -> list[Finding]:
    """A shipped module outside the boot validator must READ `go_timeout_s`.

    ARC 038's measured state, restated as a gate: the knob had exactly one
    reader and that reader only validated it. A breaker that does not read its
    own T is the wedge with a green test beside it.
    """
    config = home / CONFIG_FILE
    if not config.is_file():
        raise Cannot(f"{CONFIG_FILE} is absent; the knob has no physical home")
    if f'"{KNOB}"' not in config.read_text():
        return [
            Finding(
                f"{CONFIG_FILE}",
                f"§12A:831's GO_TIMEOUT_T has no `{KNOB}` key — the deadlock "
                "breaker has no T to measure against",
            )
        ]
    readers = sorted(
        rel
        for rel in (str(path.relative_to(home)) for path in _shipped_modules(home))
        if rel != VALIDATOR and _names_the_knob(home / rel, rel)
    )
    if not readers:
        return [
            Finding(
                LOOP_FILE,
                f"NO shipped module outside {VALIDATOR} reads "
                f"`limiter.{KNOB}`. §12A:831's knob is present in "
                f"{CONFIG_FILE} and UNREAD — §4:210-212's deadlock breaker has "
                f"a T that nothing measures elapsed time against, which is "
                f"exactly the state ARC 038 (F) measured when a SIGKILLed GO "
                f"holder left the §4:208 lock held 11.0s past a 10s knob. "
                f"§14:971's *'it can never wedge (GO-timeout)'* has no "
                f"implementation",
            )
        ]
    if LOOP_FILE not in readers:
        return [
            Finding(
                LOOP_FILE,
                f"`limiter.{KNOB}` is read by {readers} but NOT by {LOOP_FILE}. "
                "§5:322 puts the Limiter's serial processing in the event loop "
                "and §4:212 measures T as a DURATION, so a reader outside the "
                "loop has no clock that is still running when nobody is calling "
                "it — the reading ARC 038 found missing",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 2 — the LIVE drive: a real process, a real GO, a real abandonment
# ---------------------------------------------------------------------------
class Drive:
    """One `limiterd` process and the command path into it. Torn down always."""

    def __init__(self, home: Path, root: Path) -> None:
        self.home = home
        self.root = root
        self.inbox = root / "inbox"
        self.outbox = root / "outbox"
        for directory in (root, self.inbox, self.outbox):
            directory.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(home / "scripts")
        # Both pipes are requested below, so neither is None. Narrowed once,
        # here, rather than with a guard at each of the four read sites.
        # nosec B603 - fixed argv, no shell, interpreter is ours
        self.proc = subprocess.Popen(  # nosec B603  # pylint: disable=consider-using-with
            [
                sys.executable,
                str(home / LIMITERD_FILE),
                "--runtime-dir",
                str(root),
                "--go-timeout",
                str(DRIVE_TIMEOUT_S),
                "--tick-interval",
                str(DRIVE_TICK_S),
                "--heartbeat-interval",
                str(DRIVE_HEARTBEAT_S),
            ],
            env=env,
            cwd=str(home),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self.proc.stdout is not None  # nosec B101 - PIPE requested above
        assert self.proc.stderr is not None  # nosec B101 - PIPE requested above
        self.out: IO[bytes] = self.proc.stdout
        self.err: IO[bytes] = self.proc.stderr

    def send(self, cid: str, payload: dict) -> dict:
        """One command in, one reply out. Raises `Cannot` on silence."""
        body = json.dumps({"schema": 1, "id": cid, **payload})
        tmp = self.inbox / f".{cid}.tmp"
        tmp.write_text(body)
        os.replace(tmp, self.inbox / f"{cid}.json")
        reply = self.outbox / f"{cid}.reply.json"
        deadline = time.monotonic() + REPLY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise Cannot(
                    f"limiterd exited with {self.proc.returncode} before "
                    f"answering {cid!r}: {self.err.read()[:400]!r}"
                )
            if reply.is_file():
                try:
                    return json.loads(reply.read_text())
                except ValueError:
                    pass
            time.sleep(0.01)
        raise Cannot(f"limiterd did not answer {cid!r} within {REPLY_TIMEOUT_S}s")

    def status(self, tag: str) -> str:
        """The process's own account of its live state. Its words, not ours."""
        cid = f"st-{tag}-{time.monotonic_ns()}"
        return str(self.send(cid, {"verb": "status"})["reason"])

    def wait_for_boot(self) -> None:
        """Block until the process has written its boot record, or raise `Cannot`."""
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while time.monotonic() < deadline:
            if (self.root / "limiter.runtime.json").is_file():
                return
            if self.proc.poll() is not None:
                raise Cannot(
                    f"limiterd refused to boot ({self.proc.returncode}): "
                    f"{self.err.read()[:400]!r}"
                )
            time.sleep(0.02)
        raise Cannot(f"limiterd wrote no runtime record within {BOOT_TIMEOUT_S}s")

    def stop(self) -> dict:
        """SIGTERM, join, and return the stop record. Always called."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.out.close()
        self.err.close()
        record = self.root / "limiter.runtime.json"
        if not record.is_file():
            raise Cannot("limiterd left no runtime record to read")
        return json.loads(record.read_text())


def _held(status: str) -> bool:
    """Does the process report the §4:208 lock HELD right now?

    Reads the process's OWN status sentence. The `in flight` field is bounded by
    the field that follows it, never by the end of the string — the sentence
    grows, and a parse that swept later fields in would read a released lock as
    held (measured on this arc's own driver before it was fixed).
    """
    tail = status.split("in flight ", 1)[1]
    return tail.split(", go armed", 1)[0].strip() != "[]"


# The per-row arms, split out for the reason the sibling split was made: each
# `if` is a distinct way ONE firing can be wrong, and they are read one row at a
# time. pylint: disable=too-many-branches
def _judge_rows(rows: list) -> list[Finding]:
    """Every §4:210-212 firing, judged on its own terms. One row, six ways wrong."""
    found: list[Finding] = []
    for row in rows:
        if row.get("client_order_id") != LOST_CID:
            found.append(
                Finding(
                    LOOP_FILE,
                    f"the breaker fired for {row.get('client_order_id')!r}; the "
                    f"only GO left without terminal feedback was {LOST_CID!r}",
                )
            )
        if row.get("resent"):
            found.append(
                Finding(
                    LOOP_FILE,
                    "the breaker RESENT the order. §4:240-241 — *'issue "
                    "order-status query, never auto-resend'* — a resend turns "
                    "one intended order into two",
                )
            )
        if not row.get("released"):
            found.append(
                Finding(
                    LOOP_FILE,
                    "the breaker recorded a firing that released nothing; the "
                    "lock it fired on was still held",
                )
            )
        reported_t = float(row.get("timeout_s", 0.0))
        elapsed = float(row.get("elapsed_s", 0.0))
        if reported_t <= 0.0 or elapsed < reported_t:
            found.append(
                Finding(
                    LOOP_FILE,
                    f"the breaker fired at elapsed={elapsed}s against its own "
                    f"reported T={reported_t}s — it fired before its own "
                    f"deadline",
                )
            )
        if elapsed > reported_t * 2.0:
            found.append(
                Finding(
                    LOOP_FILE,
                    f"the breaker fired at elapsed={elapsed}s, more than twice "
                    f"its own T={reported_t}s. ARC 038 measured 11.0s past a "
                    f"10s knob; a breaker this late is the same defect slower",
                )
            )
    return found


# R0912/R0915 (too-many-branches / too-many-statements) and complexipy: the
# branches ARE the arms. Every one is a distinct way §4:210-212 can be false —
# never fired, fired early, fired on the wrong order, fired and resent, fired and
# released nothing, fired late, fired and DEREGISTERED, fired and left the
# process not flat — and each carries its own §-citing reason. Collapsing them
# would put one reason string over eight distinguishable defects, which check
# contract v2 rule 11 forbids: the REASON is the assertion. Split OUT of the
# drive (rather than merged into it) so the drive owns the live process and this
# owns the reading of what it left behind — two subjects, two functions.
# pylint: disable=too-many-branches,too-many-statements
def _judge_record(
    record: dict, *, fed_arm_ran: bool, spawned_pid: int
) -> tuple[list[Finding], list]:
    """Read the stop record the process left behind. Never touches a live process."""
    found: list[Finding] = []
    # -- the process's own record is the evidence; the gate only reads it -----
    if record.get("pid") != spawned_pid:
        raise Cannot(
            f"the runtime record names pid {record.get('pid')} and this gate "
            f"spawned {spawned_pid} — the record is not this run's"
        )
    rows = record.get("go_timeouts")
    if rows is None:
        found.append(
            Finding(
                LIMITERD_FILE,
                "the stop record carries no `go_timeouts` field, so the process "
                "cannot report whether §4:210-212 ever fired. A breaker with no "
                "record is unfalsifiable from outside the process",
            )
        )
        rows = []
    if not fed_arm_ran:
        pass  # the row-count arm below needs both GOs to have run
    elif len(rows) != 1:
        found.append(
            Finding(
                LOOP_FILE,
                f"the process recorded {len(rows)} §4:210-212 firing(s) for a "
                f"run with exactly ONE abandoned GO and ONE normally-resolved "
                f"GO. More than one means the breaker fired on the healthy "
                f"path; none means it never fired at all",
            )
        )
    found += _judge_rows(rows)
    if STRATEGY not in (record.get("registrations") or []):
        found.append(
            Finding(
                LOOP_FILE,
                f"{STRATEGY!r} is no longer registered after the breaker fired. "
                "§4:211-212 resets the strategy to flat-and-FREE; a release that "
                "took the registration with it is §4:266-268's DEREGISTRATION, "
                "which is a different verb for a strategy that has DIED",
            )
        )
    if not record.get("flat", False):
        found.append(
            Finding(
                LOOP_FILE,
                f"the process stopped NOT flat: in_flight={record.get('in_flight')}",
            )
        )
    return found, rows


def _drive_lost_go(drive: Drive) -> float | None:
    """Register, admit ONE GO, abandon it, and watch the lock. Seconds, or None.

    Returns the elapsed time at which the §4:208 lock came off, or `None` if it
    never did inside `WATCH_HORIZON` — which is the wedge.

    THE NON-VACUITY ASSERTION LIVES HERE and is made before any later reading may
    be believed: the process must REPORT THE LOCK HELD once. A drive that watched
    an empty registry and called the emptiness a release measures nothing, and
    §17 / check contract v2 rule 10 make that a CANNOT_MEASURE, never a PASS.
    """
    reply = drive.send("reg", {"verb": "register", "strategy_id": STRATEGY})
    if not reply["accepted"]:
        raise Cannot(f"the process refused registration: {reply['reason']}")
    reply = drive.send(
        "go-lost",
        {"verb": "go", "strategy_id": STRATEGY, "client_order_id": LOST_CID},
    )
    if not reply["accepted"]:
        raise Cannot(f"the process refused the GO: {reply['reason']}")
    admitted_at = time.monotonic()
    if not _held(drive.status("admitted")):
        raise Cannot(
            "the process reports NO lock held immediately after accepting a GO "
            "— the drive's scope does not contain an admitted in-flight action, "
            "so a later empty reading is not evidence of a release"
        )
    while time.monotonic() - admitted_at < WATCH_HORIZON:
        if not _held(drive.status("watch")):
            return time.monotonic() - admitted_at
        time.sleep(DRIVE_TICK_S)
    return None


def _drive_fed_go(drive: Drive) -> list[Finding]:
    """The SECOND GO: normal terminal feedback before T, then held past T.

    The direction that makes the breaker falsifiable. A timeout with no normal
    release beside it cannot be shown NOT to fire early — every GO would end at
    the breaker and a gate would read that as the invariant working (§0a).
    """
    found: list[Finding] = []
    reply = drive.send(
        "go-fed",
        {"verb": "go", "strategy_id": STRATEGY, "client_order_id": FED_CID},
    )
    if not reply["accepted"]:
        raise Cannot(
            "the process refused a SECOND GO after the breaker released the "
            f"first: {reply['reason']} — the strategy is not flat-and-FREE, "
            "which is half of §4:211-212"
        )
    reply = drive.send(
        "res-fed",
        {
            "verb": "resolve",
            "strategy_id": STRATEGY,
            "client_order_id": FED_CID,
            "outcome": "denied",
        },
    )
    if not reply["accepted"]:
        found.append(
            Finding(
                LIMITERD_FILE,
                "§4:203-206 terminal feedback was refused for a live in-flight "
                f"order: {reply['reason']}",
            )
        )
    # Sit past T with nothing in flight: a breaker that fires on everything
    # would post a second row here.
    time.sleep(DRIVE_TIMEOUT_S * 1.5)
    return found


# R0912/R0915 (too-many-branches / too-many-statements): the branches ARE the
# arms. Every one is a distinct way §4:210-212 can be false — never fired, fired
# early, fired on the wrong order, fired and resent, fired and released nothing,
# fired late, fired and deregistered, fired and left the process not flat — and
# each carries its own §-citing reason. Collapsing them would put one reason
# string over eight distinguishable defects, which check contract v2 rule 11
# forbids: the REASON is the assertion.
# pylint: disable=too-many-branches,too-many-statements
def _arm_live_breaker(home: Path) -> tuple[list[Finding], str]:
    """The whole property, on a running process. Returns (findings, evidence)."""
    findings: list[Finding] = []
    fed_arm_ran = False
    released_at: float | None = None
    final_status = "<the drive never reached a final status read>"
    with tempfile.TemporaryDirectory(prefix="check_go_timeout.") as tmp:
        drive = Drive(home, Path(tmp))
        try:
            drive.wait_for_boot()
            released_at = _drive_lost_go(drive)
            if released_at is None:
                findings.append(
                    Finding(
                        LOOP_FILE,
                        f"a GO admitted into a running limiterd and abandoned "
                        f"with NO terminal feedback still held the §4:208 "
                        f"one-in-flight lock {WATCH_HORIZON:.1f}s later, against "
                        f"T={DRIVE_TIMEOUT_S}s. §4:210-212's deadlock breaker "
                        f"did not fire and §14:971's *'it can never wedge'* is "
                        f"false on this build",
                    )
                )
            elif released_at < DRIVE_TIMEOUT_S * 0.5:
                findings.append(
                    Finding(
                        LOOP_FILE,
                        f"the lock was released {released_at:.3f}s after "
                        f"admission, far inside T={DRIVE_TIMEOUT_S}s. A breaker "
                        f"that fires early denies GOs the strategy believes are "
                        f"live — §4:211-212 resets it to flat-and-free on that "
                        f"signal, so an early T is a wrong flat",
                    )
                )

            fed_arm_ran = released_at is not None
            if not fed_arm_ran:
                final_status = drive.status("wedged")
                raise _Wedged
            findings += _drive_fed_go(drive)
            final_status = drive.status("final")
        except _Wedged:
            pass
        finally:
            record = drive.stop()

    judged, rows = _judge_record(
        record, fed_arm_ran=fed_arm_ran, spawned_pid=drive.proc.pid
    )
    findings += judged
    evidence = (
        f"{LOOP_FILE}: drove a real limiterd (pid {drive.proc.pid}, "
        f"{record.get('ticks')} ticks, {record.get('heartbeats')} beats) — "
        f"one GO ABANDONED with no terminal feedback (lock observed HELD, then "
        f"{'NEVER RELEASED' if released_at is None else f'released {released_at:.3f}s later'}"
        f" against T={DRIVE_TIMEOUT_S}s) and one GO RESOLVED normally and "
        f"held past T ({len(rows)} breaker firing(s) recorded; fed arm ran: "
        f"{fed_arm_ran}); final live "
        f"status: {final_status}"
    )
    return findings, evidence


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure-only. `CORRECTABLE = False` — see the module constant."""
    try:
        findings = _arm_knob_is_read(ctx.nix_home)
        if findings:
            # The static arm reds FIRST and alone: when the knob is unread there
            # is no breaker to drive, and a live arm run anyway would spend 8s
            # rediscovering what the site already names.
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=(
                    f"{CONFIG_FILE}: `{KNOB}` reader census over the shipped "
                    f"population (scripts/**.py minus scripts/tests/)"
                ),
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        live, evidence = _arm_live_breaker(ctx.nix_home)
        if live:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in live),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in live),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Cannot as exc:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, detail=f"{NAME}: {exc}"
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
