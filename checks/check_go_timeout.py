#!/usr/bin/env python3
# C0302: this module crossed pylint's 1 000-line ceiling in ARC 042, and the
# excess is PROSE — the two Plane-1 arms (D3.425) and the §7.12 hazards they
# close, written beside the arms they argue for. Doctrine B.7 puts the argument
# next to the instrument it argues for, the same trade `check_plane1_sole_writer.py`
# and `check_artifact_gate_coverage.py` state at their own heads; moving the
# reasoning away from the code it explains to satisfy a line counter is the trade
# the check contract refuses.
# pylint: disable=too-many-lines
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

ARC 042 ADDED TWO MORE ARMS, AND WHY THEY LIVE HERE
----------------------------------------------------
CHECK-DEBT **D3.425**: §12.10 puts GO-timeout on **Plane 1** because the firing
GATES MONEY — the GO is treated as DENIED and the strategy reset to
flat-and-free — and §9 makes the Limiter the sole writer of that log. ARC 040
built the breaker and it wrote a RUNTIME RECORD. A runtime record is not §9's
evidence plane. The firing happened and the money record did not know.

3. **THE PLANE-1 STATIC ARM** — `scripts/limiterd.py`'s fire path reaches an
   enqueue onto §9's write path, asserted BY SHAPE: a function that reads the
   loop's `go_timeouts()` ledger must also call `.enqueue(...)`, and its class
   must construct the row under the GO-timeout kind. Shape, not spelling, is the
   **D3.426** lesson — a census matching an identifier is green over a rename and
   over a body that names the thing without doing it.
4. **THE PLANE-1 LIVE ARM** — the drive already running for arm 2 leaves a real
   WAL beside the runtime record it already reads. Exactly ONE row for the ONE
   abandoned GO, its §9 fields matched against THAT firing, and ZERO for the GO
   the second arm resolves normally.

**Why here and not in a Plane-1 gate.** `check_plane1_event_coverage` owns
*"every §12.10 type transports and has a producer"* and now reports `go_timeout`
DRIVEN; `check_plane1_wal` owns the WAL's durability; `check_plane1_sole_writer`
owns authorship. None of them drives a firing, and the property here —
*a FIRED GO-timeout produces exactly one Plane-1 row* — cannot be measured
without one. A new gate would have to spawn a second `limiterd` and re-drive the
breaker this gate already drives, which is the duplicate instrument doctrine C.9
forbids. The subject of this gate is the fire path; the row is what the fire path
now owes.

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
  7. **(ARC 042) The Plane-1 arm read an empty WAL and called the emptiness
     correct.** A "no spurious rows" assertion is satisfied for free by a WAL
     that was never written, by a path that does not exist, and by a process
     with the booking torn out — which is the D3.425 state itself. CLOSED: the
     arm REQUIRES the abandoned GO to have produced a firing in the record
     before it reads the WAL at all, requires the WAL FILE to exist at the path
     the PROCESS reported in its own stop record, and judges *one row* and *zero
     rows* as two separate assertions against two separate GOs in the same
     drive. Absent evidence with no firing beside it is CANNOT_MEASURE.
  8. **(ARC 042) The static arm matched the identifier rather than the shape.**
     A census for `Plane1Booker` or `book_new_firings` is green over a rename and
     over a body that mentions the name and enqueues nothing — D3.426. CLOSED:
     the arm never spells a Nix identifier. It walks the AST for a function that
     CALLS `.go_timeouts()` and requires a `.enqueue(...)` call in that same
     function and a row construction under the GO-timeout kind in its class, so
     the finding survives every rename and dies the moment the call goes.
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
from typing import IO, Final, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order

# ARC 042. The WAL CODEC, imported rather than re-implemented. This is not the
# import the module header refuses: that refusal is about measuring the LOOP as
# a library instead of as a process, and the process is still the subject here.
# `recover` is only how the artefact the process LEFT BEHIND is read, exactly as
# `json.loads` is how its runtime record is read — and a second copy of the
# frame format in this file would be a source of truth that drifts from the one
# `scripts/nixrisk/wal.py` writes (directive 3).
from nixrisk.wal import recover
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

#: ARC 042 / D3.425. §12.10's Plane-1 label for the firing. The DATA value, not
#: an identifier: it is what `plane1_event_enum` and `EventKind.GO_TIMEOUT.value`
#: both spell, and the WAL frame carries it as text.
GO_TIMEOUT_EVENT = "go_timeout"

#: How many duplicate rows a duplicate-booking finding ENUMERATES. A cap, and
#: the finding says so and prints the true total beside the sample: a re-tick
#: that books every tick produces one row per tick (156 on this gate's own
#: drive), and a reason string that pasted all of them would bury the sentence
#: an operator has to read. Doctrine: no SILENT cap.
_ROW_SAMPLE: Final[int] = 3


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
# ARM 3 (ARC 042 / D3.425) — the STATIC Plane-1 fire path, asserted BY SHAPE
# ---------------------------------------------------------------------------
def _calls_attr(node: ast.AST, attr: str) -> bool:
    """Does this subtree CALL `<anything>.<attr>(...)`? A call, not a mention."""
    return any(
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Attribute)
        and inner.func.attr == attr
        for inner in ast.walk(node)
    )


def _builds_go_timeout_row(node: ast.AST) -> bool:
    """Does this subtree construct a row under the GO-timeout KIND?

    Matched on the enum MEMBER (`<anything>.GO_TIMEOUT`) or on the §12.10 data
    value as a literal. Both are the WIRE, not a Nix identifier a rename could
    move: the member name is what `plane1_event_enum` is keyed through and the
    literal is what lands in the row. What is deliberately NOT matched is the
    name of any class, function or attribute this tree happens to use today.
    """
    for inner in ast.walk(node):
        if isinstance(inner, ast.Attribute) and inner.attr == "GO_TIMEOUT":
            return True
        if isinstance(inner, ast.Constant) and inner.value == GO_TIMEOUT_EVENT:
            return True
    return False


def _arm_firing_is_booked(home: Path) -> list[Finding]:
    """`limiterd`'s fire path must reach §9's enqueue. STRUCTURAL, not textual.

    THE SHAPE, and every part of it is load-bearing:

    * a function in `scripts/limiterd.py` that CALLS `.go_timeouts()` — that is
      the fire path, because the loop's firing ledger is the only thing in this
      process that knows the breaker fired;
    * the SAME function calls `.enqueue(...)` — §9's write path
      (`Plane1Port.enqueue`), the one verb that puts a row on the durable local
      WAL. In the same function, so a module that reads the ledger in one place
      and enqueues something unrelated in another does not satisfy it;
    * the enclosing SCOPE builds the row under the GO-timeout kind, so an
      enqueue of some other event type from the fire path is not the booking.

    D3.426: not one Nix identifier is spelled. `Plane1Booker`,
    `book_new_firings` and `_row_for` may all be renamed and this arm holds; the
    moment the enqueue leaves the fire path it reds, which is ARC 040's exact
    state and the one PLANT A restores.
    """
    path = home / LIMITERD_FILE
    if not path.is_file():
        raise Cannot(f"{LIMITERD_FILE} is absent; there is no fire path to read")
    try:
        tree = ast.parse(path.read_text(), filename=LIMITERD_FILE)
    except SyntaxError as exc:
        raise Cannot(f"{LIMITERD_FILE} does not parse: {exc}") from exc

    # DIRECT children of each scope, never `ast.walk`: walking the module and
    # then walking every class inside it finds each method TWICE, and a finding
    # that lists the same site twice reads as two defects.
    scopes: list[ast.AST] = [tree]
    scopes += [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    fire_paths = [
        (fn, scope)
        for scope in scopes
        for fn in getattr(scope, "body", [])
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
        and _calls_attr(fn, "go_timeouts")
    ]
    if not fire_paths:
        return [
            Finding(
                LIMITERD_FILE,
                "NO function in this module reads the loop's `go_timeouts()` "
                "firing ledger, so nothing in the Limiter process can know that "
                "§4:210-212's breaker fired. §12.10 puts GO-timeout on Plane 1 "
                "because the firing GATES MONEY, and a row cannot be booked for "
                "an event the writer never observes (CHECK-DEBT D3.425)",
            )
        ]
    for fn, scope in fire_paths:
        if _calls_attr(fn, "enqueue") and _builds_go_timeout_row(scope):
            return []
    ordered = sorted(fire_paths, key=lambda pair: pair[0].lineno)
    named = ", ".join(f"{fn.name}():{fn.lineno}" for fn, _ in ordered)
    return [
        Finding(
            f"{LIMITERD_FILE}:{min(fn.lineno for fn, _ in fire_paths)}",
            f"{len(fire_paths)} function(s) in this module read the breaker's "
            f"firing ledger — {named} — and NOT ONE of them reaches an enqueue "
            f"onto §9's durable local WAL "
            f"under the §12.10 `{GO_TIMEOUT_EVENT}` kind. A function that reads "
            f"the ledger only to REPORT it (a status verb) is not a booking. "
            f"§9 makes the Limiter "
            f"the SOLE writer of the append-only event log and §12.10 puts this "
            f"transition on Plane 1 — *anything that changes or gates money gets "
            f"a Plane-1 row* — so a breaker that fires, releases the §4:208 lock "
            f"and writes only a RUNTIME RECORD leaves the money record silent "
            f"about a GO that was treated as DENIED. That is ARC 040's measured "
            f"state and CHECK-DEBT D3.425",
        )
    ]


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


# ---------------------------------------------------------------------------
# ARM 4 (ARC 042 / D3.425) — the LIVE Plane-1 row, read off the drive's own WAL
# ---------------------------------------------------------------------------
def _judge_plane1(root: Path, record: dict, rows: list) -> list[Finding]:
    """The §9 rows the drive's own process left behind. One firing, one row.

    Read INSIDE the drive's temporary directory, from the path the PROCESS
    named in its own stop record — never a path this gate composed, so a gate
    reading the wrong file cannot report a clean absence.

    NON-VACUITY, asserted before any verdict: the drive must have produced a
    firing. With no firing there is no row owed, "zero rows" is true for free,
    and §17 / check contract v2 rule 10 make that CANNOT_MEASURE. The caller
    only reaches here when the abandoned GO ran, and this re-asserts it against
    the record rather than trusting the call site.
    """
    plane1 = record.get("plane1")
    if not isinstance(plane1, dict):
        return [
            Finding(
                LIMITERD_FILE,
                "the stop record carries no `plane1` block, so the process "
                "cannot say whether it booked §12.10's GO-timeout row, refused "
                "to, or never tried. §9's evidence plane is unfalsifiable from "
                "outside this process (CHECK-DEBT D3.425)",
            )
        ]
    if not rows:
        raise Cannot(
            "the drive recorded no §4:210-212 firing, so no Plane-1 row is owed "
            "and an empty log is not evidence of anything (§17)"
        )
    wal_path = Path(str(plane1.get("wal_path") or ""))
    if not wal_path.is_file():
        return [
            Finding(
                LIMITERD_FILE,
                f"the process reported its Plane-1 WAL at {str(wal_path)!r} and "
                f"no such file exists after {len(rows)} §4:210-212 firing(s). "
                f"§9's path begins *enqueue -> durable local WAL*; a Limiter "
                f"that fired the breaker and wrote no WAL has booked nothing",
            )
        ]
    if not wal_path.is_relative_to(root):
        raise Cannot(
            f"the process named a WAL at {wal_path} outside this drive's own "
            f"runtime directory {root} — the file is not this run's, so what it "
            f"holds is not evidence about this firing"
        )

    found: list[Finding] = []
    recovered = recover(wal_path)
    if not recovered.intact:
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the Plane-1 WAL has a torn tail "
                f"({recovered.torn_tail_bytes} byte(s), "
                f"{recovered.corrupt_records} corrupt record(s)) "
                f"after a CLEAN SIGTERM stop. A partial record on a supervised "
                f"shutdown means a row was written and not made durable",
            )
        )
    booked = [row for row in recovered.rows if row.kind.value == GO_TIMEOUT_EVENT]
    other = [row for row in recovered.rows if row.kind.value != GO_TIMEOUT_EVENT]
    if other:
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the drive booked {len(other)} non-GO-timeout Plane-1 row(s) "
                f"({sorted({r.kind.value for r in other})}) from a run whose only "
                f"money-gating transition was the breaker firing. §12.10 rows are "
                f"not interchangeable and this arc wired exactly one type",
            )
        )
    if not booked:
        found.append(
            Finding(
                f"{LIMITERD_FILE} -> {wal_path.name}",
                f"§4:210-212's breaker FIRED {len(rows)} time(s) — the runtime "
                f"record says so and the §4:208 lock came off — and §9's "
                f"append-only event log holds NO `{GO_TIMEOUT_EVENT}` row for it. "
                f"§12.10 puts this transition on Plane 1 because it GATES MONEY: "
                f"the GO is treated as DENIED and the strategy reset to "
                f"flat-and-free. The RUNTIME RECORD has the firing and the "
                f"EVIDENCE PLANE does not, which is CHECK-DEBT D3.425 exactly. "
                f"The process's own counters claim booked={plane1.get('booked')} "
                f"refused={plane1.get('refused')} against "
                f"wal_enqueued={plane1.get('wal_enqueued')} and "
                f"wal_durable={plane1.get('wal_durable')} — a booking counter "
                f"that advances over a WAL that received nothing is the claim "
                f"and the artefact disagreeing",
            )
        )
        return found
    if len(booked) != len(rows):
        found.append(
            Finding(
                f"{LIMITERD_FILE} -> {wal_path.name}",
                f"{len(rows)} §4:210-212 firing(s) produced {len(booked)} "
                f"`{GO_TIMEOUT_EVENT}` row(s) in §9's log. One firing is ONE row: "
                f"§4:240-241 forbids the auto-resend outright, and a duplicate "
                f"booking on a re-tick puts a second DENIED into the money record "
                f"for one order. Rows (first {_ROW_SAMPLE} of {len(booked)}; "
                f"the rest are elided rather than silently dropped): "
                + ", ".join(
                    f"{r.strategy_id}/{r.fields.get('client_order_id')}"
                    f"@tick{r.fields.get('fired_tick')}"
                    for r in booked[:_ROW_SAMPLE]
                ),
            )
        )
    found += _judge_plane1_fields(plane1, record, rows[0], booked)
    return found


# R0912 (too-many-branches): the branches ARE the assertions — one per §9 field
# plus the two counter cross-checks — and each carries its own §-citing reason.
# Split OUT of `_judge_plane1` (rather than left in it) for the reason the
# sibling split above was made and for one more: the caller owns the
# PRECONDITIONS (is there a firing, is there a WAL, is it this run's, how many
# rows) and this owns the READING of one row, which is two subjects. It also
# put `_judge_plane1` back under the complexity ceiling, which is the honest
# report: the function was doing two jobs and the counter said so.
# pylint: disable=too-many-branches
def _judge_plane1_fields(
    plane1: dict, record: dict, firing: dict, booked: list
) -> list[Finding]:
    """ONE booked row, judged against ONE firing. §9's four fields, one at a time."""
    found: list[Finding] = []
    row = booked[0]
    if row.strategy_id != firing.get("strategy_id"):
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the Plane-1 row names strategy {row.strategy_id!r} and the "
                f"firing was for {firing.get('strategy_id')!r} — the row is not "
                f"this firing's",
            )
        )
    if row.fields.get("client_order_id") != firing.get("client_order_id"):
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the Plane-1 row carries client_order_id "
                f"{row.fields.get('client_order_id')!r}; the abandoned GO was "
                f"{firing.get('client_order_id')!r}",
            )
        )
    inside_life = float(record["boot_ts"]) <= row.ts <= float(record["stopped_ts"])
    if not inside_life:
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the Plane-1 row's timestamp {row.ts} is outside this process's "
                f"own life ({record['boot_ts']} .. {record['stopped_ts']}), so it "
                f"is a leftover rather than this firing's row",
            )
        )
    if not row.reason.strip():
        found.append(
            Finding(
                LIMITERD_FILE,
                "the Plane-1 row's §9 `reason` is empty. Check contract v2 rule "
                "11 makes the reason the assertion, and a money-record row that "
                "says only that something happened names nothing at 03:00",
            )
        )
    if row.fields.get("resent") not in {"false", "False"}:
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the Plane-1 row records resent={row.fields.get('resent')!r}. "
                f"§4:240-241 — *'never auto-resend'* — and a booked resend is one "
                f"intended order recorded as two",
            )
        )
    if plane1.get("booked") != len(booked) or plane1.get("refused"):
        found.append(
            Finding(
                LIMITERD_FILE,
                f"the process claims booked={plane1.get('booked')} "
                f"refused={plane1.get('refused')} and its WAL holds "
                f"{len(booked)} row(s). The counter and the artefact disagree, so "
                f"one of them is not measuring the booking",
            )
        )
    elif plane1.get("wal_durable", 0) < len(booked):
        found.append(
            Finding(
                LIMITERD_FILE,
                f"{len(booked)} row(s) enqueued and wal_durable="
                f"{plane1.get('wal_durable')}. §9 says *durable* local WAL; a row "
                f"in the page cache is lost to a power cut and is not evidence",
            )
        )
    return found


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
    plane1_findings: list[Finding] = []
    plane1_note = "not reached"
    final_status = "<the drive never reached a final status read>"
    with tempfile.TemporaryDirectory(prefix="check_go_timeout.") as tmp:
        root = Path(tmp)
        drive = Drive(home, root)
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
            # ARC 042 / ARM 4. Read INSIDE the temporary directory, because the
            # WAL the process wrote lives in it and the `with` removes it on the
            # way out. The row is judged against the record's OWN firing rows,
            # which `_judge_record` re-reads below for the arms that predate
            # this one.
            _rows = record.get("go_timeouts") or []
            if _rows:
                plane1_findings = _judge_plane1(root, record, list(_rows))
                plane1_note = (
                    f"{len(_rows)} firing(s), "
                    f"plane1={json.dumps(record.get('plane1'), sort_keys=True)}"
                )
            else:
                plane1_note = "no firing, so no Plane-1 row is owed"

    judged, rows = _judge_record(
        record, fed_arm_ran=fed_arm_ran, spawned_pid=drive.proc.pid
    )
    findings += judged
    findings += plane1_findings
    evidence = (
        f"{LOOP_FILE}: drove a real limiterd (pid {drive.proc.pid}, "
        f"{record.get('ticks')} ticks, {record.get('heartbeats')} beats) — "
        f"one GO ABANDONED with no terminal feedback (lock observed HELD, then "
        f"{'NEVER RELEASED' if released_at is None else f'released {released_at:.3f}s later'}"
        f" against T={DRIVE_TIMEOUT_S}s) and one GO RESOLVED normally and "
        f"held past T ({len(rows)} breaker firing(s) recorded; fed arm ran: "
        f"{fed_arm_ran}); §9/§12.10 Plane-1 booking: {plane1_note}; final live "
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
        # ARC 042 / ARM 3. Does NOT short-circuit the way the knob arm does.
        # PLANT A — the booking removed — must be reported at its SITE *and*
        # demonstrated as the runtime-record/Plane-1 gap on a real firing, and a
        # static arm that returned early would give the site and never drive the
        # subject. The knob arm above still short-circuits, and for the opposite
        # reason: with no reader there is no breaker to drive at all.
        static_plane1 = _arm_firing_is_booked(ctx.nix_home)
        live, evidence = _arm_live_breaker(ctx.nix_home)
        live = static_plane1 + live
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
