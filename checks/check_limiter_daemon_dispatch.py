#!/usr/bin/env python3
"""The RUNNING Limiter dispatches a §2A completion to §3's handler, exactly once.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line. Spelled out
because a file under `checks/` is read against the check contract by default,
and the same section number means different things in the two documents.

ONE gate, ONE property. In `docs/nics_risk_subsystem_spec_v1.3.md` §5:322:

    Limiter = single-threaded event loop (shared-mem price poll + ZMQ inbox +
    **sender completions, processed serially**)

is true of the PROCESS on the cancel path — a §2A:78 `on_cancel` exec report that
enters `limiterd` from outside it is dispatched by the loop's own tick to
`nixrisk/outcomes.py`'s already-proven handler, the reservation releases, and
committed margin falls (`docs/nics_risk_subsystem_spec_v1.3.md`).

And in `docs/nics_risk_subsystem_spec_v1.3.md` §4:214:

    broker events are deduplicated by (order_id, exec_id)

is true of the same process: a RE-DELIVERED exec report releases nothing.

## WHY THIS GATE EXISTS AS A NEW FILE (check contract rule 8, answered honestly)

Rule 8 says extend an existing gate where one owns the property. Measured at
ARC 046 S5 against `dc78249`, none does:

  * `check_reservation_lifecycle` owns *every reservation reaches exactly one
    terminal release* over `scripts/nixrisk/reservations.py` — the LIBRARY. It
    never starts a process.
  * `check_go_timeout` and `check_limiter_loop_alive` DO spawn a real `limiterd`,
    and neither touches a reservation: the census `grep -l limiterd checks/*.py |
    xargs grep -l reserv` returned nothing at all.
  * The string `completion` appeared in ZERO of the 96 checks.

That absence IS the gap ARC 038 named five times over and ARC 046 spikes: the
handler was proven, the daemon was silent, and no instrument could tell the two
apart. This gate is the first that can.

## WHAT IT MEASURES, AND WHAT IT REFUSES TO CLAIM

**It is scoped to the ONE path ARC 046 wired.** `nixrisk/completions.py` declares
`WIRED_EVENTS` and this gate READS that tuple rather than spelling `on_cancel`:
when a later arc wires the fill path, the tuple grows, this gate's UNWIRED arm
narrows automatically, and the gate that would have gone quietly stale instead
tightens. It asserts nothing about fill, reject, pending-timeout, onset
cancellation or protective flatten, and the UNWIRED arm exists precisely so that
"this build does not dispatch a fill" is a MEASURED, named state rather than an
absence a reader could mistake for coverage.

It does NOT claim a real broker session pushed anything. There is no vendor
integration in this tree. It claims what it drives: a completion that entered the
process from the filesystem was dispatched, serially, by the loop's own tick.

## `debug.md` §7.12 — THE STANDING QUESTION

What would have to be true for a run of this gate to look healthy while proving
nothing?

 1. **No completion ever reached the daemon**, and committed sat at 0.0 because
    nothing was ever reserved. GUARDED — NON-VACUITY, asserted before any
    verdict: the gate reserves through the running daemon and REQUIRES committed
    to RISE, and requires the daemon's own `completions.seen` counter to advance,
    before it will look at whether it fell.
 2. **The gate called the handler itself** and read its own work back. GUARDED:
    this file imports no handler and constructs no ledger. Every number is read
    out of the daemon's replies, and `last_source` must equal the path of the
    file the gate wrote into the daemon's completions directory — a dispatch
    from anywhere else fails the provenance arm.
 3. **The release happened, but not from the loop** — some boot-time or
    stop-time path drained it. GUARDED: committed is read LIVE, mid-run, through
    the `status` verb, and the tick number in the reply that first shows the
    release is compared against the tick in the reply taken before the push.
 4. **The dedup deduped everything**, so the daemon looked idempotent by never
    dispatching at all. GUARDED: the DRIVEN arm asserts the FIRST delivery
    released 2000.0 before the IDEMPOTENCY arm asserts the second released
    nothing, and `dispatched == 1` is asserted at both ends.
 5. **The re-delivery was stopped by the LEDGER, not by the daemon**, and the
    gate credited a dedup that is not there. GUARDED: the stop record's
    `reservations.refused` must be ZERO. The ledger refuses a duplicate
    `client_order_id` (ARC 044 / I2, still standing) — so a re-delivery that got
    past the daemon's dedup would show up as a booked refusal. Zero refusals is
    what proves the guard was the one at the daemon boundary.
 6. **The gate passed because `limiterd` never started** and every arm read an
    absence. GUARDED: boot is waited for and its failure is CANNOT_MEASURE, never
    PASS (check contract rule 10 — a safety property proven while its subject is
    unavailable is not proven).
 7. **An exception anywhere collapsed to a bare exit 1** that read as the
    detector firing. GUARDED: every failure carries the REASON — the site, the
    counters, and the numbers — never the code alone (check contract rule 11).
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - the subject is a REAL limiterd PROCESS
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order

# The WIRED-PATH DECLARATION, imported rather than spelled (directive 3). This is
# not the import the process-not-library argument forbids: the subject is still
# the running daemon, and this is a constant tuple naming which paths this build
# claims to serve. A second copy here would let the gate keep asserting a path
# the build had stopped wiring.
from nixrisk.completions import SPEC_EVENTS, WIRED_EVENTS
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
DEPENDS_ON: tuple[str, ...] = ()
#: SPAWNS a `limiterd` subprocess into a fresh temp runtime directory. Declared
#: because check contract rule 12 has the declaration checked against what is
#: OBSERVED at runtime, not merely against itself.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:python",
    "subprocess:python3",
)
ON_FAIL = "continue"
#: NON-CORRECTABLE: the subject is risk-path source — the dispatch that releases
#: committed margin. A gate empowered to edit it until its own drive came back
#: clean would be manufacturing green over §14's terminal-release invariant.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/limiterd.py's §5:322 completion "
    "dispatch and scripts/nixrisk/completions.py's §4:214 dedup); a repair that "
    "edited it to satisfy its own gate is the same class of action risk spec §4 "
    "forbids on the order path"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/limiterd.py",
    "scripts/nixrisk/completions.py",
)

NAME = "check_limiter_daemon_dispatch"

LIMITERD_FILE = "scripts/limiterd.py"
COMPLETIONS_FILE = "scripts/nixrisk/completions.py"

#: The drive's cadence. Fast so the gate is cheap; every assertion is made
#: against numbers the PROCESS reports, never against this file's own clock.
DRIVE_TICK_S = 0.02
DRIVE_HEARTBEAT_S = 0.2
DRIVE_MAX_TICKS = 3000
BOOT_TIMEOUT_S = 25.0
REPLY_TIMEOUT_S = 20.0
#: How long the gate may WATCH PAST THE TICK for the release. Generous: a
#: dispatch that is merely slow and one that never happens must not be the same
#: reading, and the failure names which by reporting the counters it saw.
WATCH_HORIZON_S = 12.0

STRATEGY = "check-daemon-dispatch"
CANCEL_CID = "cdd-cancel-1"
CANCEL_EXEC = "cdd-exec-1"
UNWIRED_CID = "cdd-unwired-1"
UNWIRED_EXEC = "cdd-exec-unwired-1"
QTY: Final[int] = 2
MARGIN_PER_CONTRACT: Final[float] = 1000.0
EXPECT_COMMITTED: Final[float] = QTY * MARGIN_PER_CONTRACT

#: The §2A event this build must dispatch, READ from the module's declaration.
#: Empty is a CANNOT_MEASURE, not a pass: a build that wires nothing has no
#: subject for this gate.
WIRED: Final[tuple[str, ...]] = tuple(WIRED_EVENTS)
#: A §2A event this build does NOT wire, derived the same way. Used by the
#: UNWIRED arm so "not dispatched" is measured rather than assumed.
UNWIRED_CANDIDATES: Final[tuple[str, ...]] = tuple(
    ev for ev in SPEC_EVENTS if ev not in WIRED
)


class Cannot(RuntimeError):
    """The subject could not be reached. CANNOT_MEASURE, never PASS (rule 10)."""


class Drive:
    """One `limiterd` process and both paths into it. Torn down always."""

    def __init__(self, nix_home: Path) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="check-daemon-dispatch-"))
        self.nix_home = nix_home
        self._n = 0
        interpreter = nix_home / ".venv/bin/python"
        if not interpreter.exists():
            raise Cannot(f"no interpreter at {interpreter}")
        script = nix_home / LIMITERD_FILE
        if not script.exists():
            raise Cannot(f"no {LIMITERD_FILE} under {nix_home}")
        try:
            self.proc = subprocess.Popen(  # nosec B603  # pylint: disable=consider-using-with
                [
                    str(interpreter),
                    str(script),
                    "--runtime-dir",
                    str(self.dir),
                    "--heartbeat-interval",
                    str(DRIVE_HEARTBEAT_S),
                    "--tick-interval",
                    str(DRIVE_TICK_S),
                    "--max-ticks",
                    str(DRIVE_MAX_TICKS),
                ],
                cwd=str(nix_home / "scripts"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONPATH": str(nix_home / "scripts")},
            )
        except OSError as exc:
            raise Cannot(f"cannot spawn limiterd: {exc!r}") from exc
        self._await_boot()

    def _await_boot(self) -> None:
        runtime = self.dir / "limiter.runtime.json"
        deadline = time.time() + BOOT_TIMEOUT_S
        while time.time() < deadline:
            if runtime.exists():
                return
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() if self.proc.stderr else "")[-800:]
                raise Cannot(
                    f"limiterd refused to boot ({self.proc.returncode}): {err}"
                )
            time.sleep(0.05)
        raise Cannot(f"limiterd wrote no runtime record within {BOOT_TIMEOUT_S}s")

    def cmd(self, verb: str, **fields: object) -> dict[str, Any]:
        """Send one command file; return the daemon's own reply."""
        self._n += 1
        cid = f"cdd{self._n:04d}"
        (self.dir / "inbox" / f"{cid}.json").write_text(
            json.dumps({"schema": 1, "id": cid, "verb": verb, **fields})
        )
        reply = self.dir / "outbox" / f"{cid}.reply.json"
        deadline = time.time() + REPLY_TIMEOUT_S
        while time.time() < deadline:
            if reply.exists():
                try:
                    return json.loads(reply.read_text())
                except ValueError:  # a half-written read; the write is atomic,
                    time.sleep(0.02)  # so retry rather than fail
                    continue
            if self.proc.poll() is not None:
                raise Cannot(
                    f"limiterd exited with {self.proc.returncode} before "
                    f"answering {verb!r}"
                )
            time.sleep(0.02)
        raise Cannot(f"limiterd did not answer {verb!r} within {REPLY_TIMEOUT_S}s")

    def push(self, name: str, **fields: object) -> Path:
        """THE STUB BROKER: an exec report where the §5:323 sender surfaces one."""
        path = self.dir / "completions" / f"{name}.json"
        path.write_text(json.dumps({"schema": 1, **fields}))
        return path

    def watch(self, pred, what: str) -> dict[str, Any]:
        """Poll the daemon's OWN status until `pred`. Watches PAST the tick."""
        deadline = time.time() + WATCH_HORIZON_S
        status = self.cmd("status")
        while time.time() < deadline:
            if pred(status):
                return status
            time.sleep(0.03)
            status = self.cmd("status")
        raise _Missed(what, status)

    def stop(self) -> dict[str, Any]:
        """SIGTERM, join, and return the daemon's own stop record."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        record = self.dir / "limiter.runtime.json"
        if not record.exists():
            raise Cannot("limiterd left no runtime record to read")
        return json.loads(record.read_text())

    def close(self) -> None:
        """Terminate the daemon process and close its output streams."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream is not None:
                stream.close()


class _Missed(RuntimeError):
    """A watched condition never arrived. Carries the last status it saw."""

    def __init__(self, what: str, status: dict[str, Any]) -> None:
        self.what = what
        self.status = status
        super().__init__(what)


def _arm_driven(drive: Drive) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """The DRIVEN arm. Returns (findings, the numbers the daemon reported)."""
    findings: list[tuple[str, str]] = []
    seen: dict[str, Any] = {}

    boot = drive.cmd("status")
    if boot.get("committed") is None:
        raise Cannot(
            f"{LIMITERD_FILE}: this build's status reply carries no `committed` "
            "— the daemon holds no §11.3 ledger, so there is no subject"
        )
    seen["committed_at_boot"] = boot["committed"]
    seen["tick_before"] = boot["tick"]
    seen["pid"] = boot["pid"]

    reg = drive.cmd("register", strategy_id=STRATEGY)
    if not reg.get("accepted"):
        raise Cannot(f"the daemon refused to register: {reg.get('reason')}")

    # -- NON-VACUITY: a reservation is really TAKEN, in the running daemon ----
    took = drive.cmd(
        "reserve",
        strategy_id=STRATEGY,
        client_order_id=CANCEL_CID,
        symbol="ES",
        side="long",
        qty=QTY,
        margin_per_contract=MARGIN_PER_CONTRACT,
        stop_ticks=8,
        stop_mode="fixed",
    )
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reservation: {took.get('reason')}")
    committed = took.get("committed")
    seen["committed_after_take"] = committed
    if committed != EXPECT_COMMITTED:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: committed is {committed!r} after reserving "
                    f"{QTY}x{MARGIN_PER_CONTRACT}; expected {EXPECT_COMMITTED}. Nothing "
                    "was committed, so a later fall to zero would prove nothing"
                ),
            )
        )
        return findings, seen

    # -- THE PUSH: a §2A cancel exec report, from outside the process ---------
    event = WIRED[0]
    path = drive.push(
        "cancel",
        event=event,
        client_order_id=CANCEL_CID,
        exec_id=CANCEL_EXEC,
        done_qty=0,
    )
    seen["pushed"] = str(path)

    try:
        consumed = drive.watch(
            # `consumed`, NOT `seen`: `seen` moves inside the dispatch, so a
            # build with no dispatch would look like a completion that never
            # arrived. `consumed` is stamped when the LOOP DRAINS it.
            lambda s: (s.get("completions") or {}).get("consumed", 0) >= 1,
            f"the loop to CONSUME the {event} completion",
        )
    except _Missed as miss:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: {miss.what} — the daemon's own completions counter "
                    f"never advanced within {WATCH_HORIZON_S}s. Last it reported: "
                    f"{json.dumps(miss.status.get('completions'))}. The completion never "
                    "reached §5:322's loop, so nothing about dispatch was measured"
                ),
            )
        )
        return findings, seen
    seen["tick_consumed"] = consumed["tick"]

    try:
        after = drive.watch(
            lambda s: s.get("committed") == 0.0,
            "committed to FALL after the dispatch",
        )
    except _Missed as miss:
        block = miss.status.get("completions") or {}
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"THE DAEMON DID NOT RELEASE. A §2A {event} for {CANCEL_CID!r} was "
                    f"DRAINED BY THE LOOP (consumed={block.get('consumed')}, "
                    f"seen={block.get('seen')}) and committed is still "
                    f"{miss.status.get('committed')!r} after {WATCH_HORIZON_S}s "
                    f"(expected {EXPECT_COMMITTED} -> 0.0). "
                    f"dispatched={block.get('dispatched')} "
                    f"unwired={block.get('unwired')} unknown={block.get('unknown')} "
                    f"refused={block.get('refused')} malformed={block.get('malformed')} "
                    f"last_disposition={block.get('last_disposition')!r} "
                    f"last_reason={block.get('last_reason')!r}. §5:322 has the loop "
                    "process sender completions serially; this build's loop received one "
                    "and did not dispatch it to §3's handler, so the reservation leaks "
                    "and deployable capital shrinks permanently"
                ),
            )
        )
        return findings, seen

    block = after.get("completions") or {}
    seen["committed_after_dispatch"] = after["committed"]
    seen["tick_released"] = after["tick"]
    seen["dispatch_block"] = block

    if block.get("dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"committed fell to 0.0 but the daemon reports "
                    f"dispatched={block.get('dispatched')!r}, not 1 — the release did "
                    "not come from the completion dispatch, so this gate's subject was "
                    "not what released it"
                ),
            )
        )
    if block.get("released_margin") != EXPECT_COMMITTED:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the dispatch reports released_margin="
                    f"{block.get('released_margin')!r}, not {EXPECT_COMMITTED} — §3's "
                    "handler ran and released a different amount than was committed"
                ),
            )
        )
    # -- PROVENANCE (§7.12 #2): it came in through the COMPLETION PATH --------
    if block.get("last_source") != str(path):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"PROVENANCE: the daemon dispatched from "
                    f"{block.get('last_source')!r}, not from the exec report this gate "
                    f"wrote at {str(path)!r}. A release that did not arrive through "
                    "§5:322's completion path proves the handler, not the daemon — the "
                    "exact library-not-process gap this gate exists to close"
                ),
            )
        )
    if after["tick"] <= seen["tick_before"]:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the release was observed at tick {after['tick']}, not after the "
                    f"pre-push tick {seen['tick_before']} — it did not happen on a tick "
                    "of the running loop"
                ),
            )
        )
    if path.exists():
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the daemon left {path.name} in the completions directory after "
                    "dispatching it; a report that is never removed is re-read every "
                    "tick forever"
                ),
            )
        )
    return findings, seen


def _arm_idempotent(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """§4:214: a RE-DELIVERED exec report releases nothing. The daemon's dedup."""
    findings: list[tuple[str, str]] = []
    event = WIRED[0]
    drive.push(
        "cancel-redelivered",
        event=event,
        client_order_id=CANCEL_CID,
        exec_id=CANCEL_EXEC,
        done_qty=0,
    )
    try:
        drive.watch(
            lambda s: (s.get("completions") or {}).get("consumed", 0) >= 2,
            "the loop to CONSUME the re-delivered completion",
        )
    except _Missed as miss:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: {miss.what} — the re-delivery never reached the loop, "
                    f"so idempotency was not measured. Last: "
                    f"{json.dumps(miss.status.get('completions'))}"
                ),
            )
        )
        return findings
    # WATCH PAST THE TICK: a double release that lands one tick later is still a
    # double release, and a check that read once would call it clean.
    deadline = time.time() + 1.0
    while time.time() < deadline:
        time.sleep(0.05)
    status = drive.cmd("status")
    block = status.get("completions") or {}
    seen["dispatch_block_after_redelivery"] = block
    seen["committed_after_redelivery"] = status.get("committed")

    if block.get("dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"DOUBLE DISPATCH: after re-delivering the IDENTICAL exec report "
                    f"({CANCEL_CID}, {CANCEL_EXEC}) the daemon reports "
                    f"dispatched={block.get('dispatched')!r}, not 1. §4:214 deduplicates "
                    "broker events by (order_id, exec_id); a second dispatch is the "
                    "double release §14 forbids, reached at the daemon boundary"
                ),
            )
        )
    if block.get("duplicates", 0) < 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the re-delivery was consumed (seen={block.get('seen')}) but the "
                    f"daemon booked duplicates={block.get('duplicates')!r} — the §4:214 "
                    "dedup did not see it, so whatever stopped the second release was "
                    "not the daemon's"
                ),
            )
        )
    if status.get("committed") != 0.0:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"committed is {status.get('committed')!r} after the re-delivery, "
                    "not 0.0 — a second terminal event moved §11.3's aggregate"
                ),
            )
        )
    if block.get("released_margin") != EXPECT_COMMITTED:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"released_margin is {block.get('released_margin')!r} after the "
                    f"re-delivery, not {EXPECT_COMMITTED} — margin was released twice"
                ),
            )
        )
    return findings


def _arm_unwired(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """An UNWIRED §2A event is RECORDED as unwired, never absorbed as handled."""
    findings: list[tuple[str, str]] = []
    if not UNWIRED_CANDIDATES:
        # Every §2A event is wired. Not a failure — it is the state the full I1
        # capstone is aiming at, and this arm has no subject then.
        seen["unwired_arm"] = "skipped: this build wires every §2A event"
        return findings
    event = UNWIRED_CANDIDATES[0]
    before = (drive.cmd("status").get("completions") or {}).get("unwired", 0)
    drive.push(
        "unwired",
        event=event,
        client_order_id=UNWIRED_CID,
        exec_id=UNWIRED_EXEC,
        done_qty=1,
    )
    try:
        status = drive.watch(
            lambda s: (s.get("completions") or {}).get("unwired", 0) > before,
            f"the daemon to RECORD {event} as unwired",
        )
    except _Missed as miss:
        block = miss.status.get("completions") or {}
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the daemon consumed a §2A {event} and did not record it as "
                    f"unwired (unwired={block.get('unwired')!r}, "
                    f"last_disposition={block.get('last_disposition')!r}). An unwired "
                    "path that is silently dropped reads, to the next arc, exactly like "
                    "one that works"
                ),
            )
        )
        return findings
    block = status.get("completions") or {}
    seen["unwired_block"] = {
        "event": event,
        "unwired": block.get("unwired"),
        "last_disposition": block.get("last_disposition"),
    }
    if block.get("dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"dispatched moved to {block.get('dispatched')!r} on a §2A {event} "
                    f"this build declares unwired (WIRED_EVENTS={list(WIRED)})"
                ),
            )
        )
    return findings


def _arm_stop_record(record: dict[str, Any]) -> list[tuple[str, str]]:
    """The daemon's OWN stop record. §7.12 #5: whose dedup actually stopped it?"""
    findings: list[tuple[str, str]] = []
    res = record.get("reservations")
    if res is None:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "the stop record carries no `reservations` block — the process "
                    "cannot say what it committed or released"
                ),
            )
        )
        return findings
    if res.get("released") != 1:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the stop record reports released={res.get('released')!r}, not 1 — "
                    "§14: every reservation reaches EXACTLY ONE terminal release, and "
                    "this run took exactly one reservation"
                ),
            )
        )
    if res.get("outstanding") != 0:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the stop record reports outstanding={res.get('outstanding')!r} — "
                    "the reservation is still TAKEN at process exit"
                ),
            )
        )
    if res.get("refused"):
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the LEDGER booked {res.get('refused')} refusal(s). The daemon's "
                    "§4:214 dedup is supposed to stop a re-delivered exec report BEFORE "
                    "§3's handler runs; a ledger refusal means the re-delivery reached "
                    "the handler and only `reservations.py`'s own guard stopped it. That "
                    "guard is I2's and it stands — but it is not this gate's subject, "
                    "and a refusal booked on every re-delivery is indistinguishable, to "
                    "§11.7's reconcile, from a real venue anomaly"
                ),
            )
        )
    faults = record.get("faults") or []
    if faults:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the loop recorded {len(faults)} contained fault(s) during the "
                    f"drive: {faults[:2]}"
                ),
            )
        )
    return findings


def _evidence(seen: dict[str, Any], record: dict[str, Any]) -> str:
    block = seen.get("dispatch_block") or {}
    after = seen.get("dispatch_block_after_redelivery") or {}
    res = record.get("reservations") or {}
    return (
        f"{LIMITERD_FILE}: drove a real limiterd (pid {seen.get('pid')}), "
        f"reserved {EXPECT_COMMITTED} (committed "
        f"{seen.get('committed_at_boot')} -> {seen.get('committed_after_take')}), "
        f"pushed a §2A {WIRED[0]} exec report into the completions directory, "
        f"the loop consumed it at tick {seen.get('tick_consumed')} and committed "
        f"fell to {seen.get('committed_after_dispatch')} at tick "
        f"{seen.get('tick_released')} via {block.get('last_source')!r} "
        f"(dispatched={block.get('dispatched')}, "
        f"released_margin={block.get('released_margin')}); re-delivering the "
        f"identical exec report left dispatched={after.get('dispatched')} "
        f"duplicates={after.get('duplicates')} committed="
        f"{seen.get('committed_after_redelivery')}; unwired arm: "
        f"{seen.get('unwired_block') or seen.get('unwired_arm')}; stop record "
        f"released={res.get('released')} outstanding={res.get('outstanding')} "
        f"refused={res.get('refused')}; WIRED_EVENTS={list(WIRED)}"
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure-only. `CORRECTABLE = False` — see the module constant."""
    if not WIRED:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"{COMPLETIONS_FILE}: WIRED_EVENTS is empty — this build "
                "dispatches no §2A completion at all, so there is no subject"
            ),
        )
    drive: Drive | None = None
    try:
        drive = Drive(ctx.nix_home)
        findings, seen = _arm_driven(drive)
        if not findings:
            findings += _arm_idempotent(drive, seen)
            findings += _arm_unwired(drive, seen)
        record = drive.stop()
        findings += _arm_stop_record(record)
        evidence = _evidence(seen, record)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Cannot as exc:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, detail=f"{NAME}: {exc}"
        )
    except _Missed as exc:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=LIMITERD_FILE,
            detail=(
                f"{NAME}: {exc.what} never happened within {WATCH_HORIZON_S}s; "
                f"last status {json.dumps(exc.status)[:600]}"
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )
    finally:
        if drive is not None:
            drive.close()


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
