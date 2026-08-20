#!/usr/bin/env python3
# C0302 (too-many-lines) disabled, matching every other gate module in this tree
# over pylint's 1000-line default (`check_flatten.py`, `check_order_path_bans.py`,
# `check_fill_handler.py`). ARC 047 grew this file past the line by adding the
# FILL arm — the conversion, the placed stop, the mint, the OPEN row, the outcome
# push and their idempotency, each asserted as its own named finding. Splitting
# the gate across two files to satisfy the counter would put one property in two
# places, which check contract rule 8 and doctrine C.9 both forbid.
# pylint: disable=too-many-lines
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

**ARC 047 added the FILL ARM, and it is the arm this gate exists for now.** §3's
reservation lifecycle is *"taken at approval -> released on: fill (converts to
open-margin) ..."*, and §4 makes the Limiter convert the stop DISTANCE to an
absolute price at the CONFIRMED fill. So a §2A:75 `on_fill` that enters
`limiterd` from outside it must, in the RUNNING process:

  * mint a `trade_id` and publish §3's row as `PositionState.OPEN` (§14: *"Open"
    = confirmed fill only. Never optimistic.*);
  * **place the protective stop** — Nix stops are SYNTHETIC (§12.1: *"This is
    our software, not a broker-side stop"*), so the stop is a live `StopState`
    in the Limiter's own book at `fill -/+ distance x tick_size`;
  * CONVERT the reservation to open margin: Σ reservations falls, Σ open margin
    rises, both on ONE version stamp.

**THE SAFETY ARM.** A fill that converted a reservation and opened a position
with NO ARMED STOP is an UNPROTECTED POSITION (§4, §12.1) — §14 resolves it
toward FLAT and it is the hazard I11 guards. This gate FAILS on that condition
BY NAME, and it does so from the pair of observations rather than from either
alone: *the capital moved* and *no stop exists* are each ordinary on their own,
and only together are they the defect. A gate that asserted "a stop exists"
without first proving the conversion happened would pass on a build that
dispatched no fill at all.

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
 8. **ARC 047. The stop arm passed because no fill was ever processed** — an
    empty stop book and an empty position table read as "nothing unprotected".
    GUARDED: the fill arm asserts the CONVERSION first (Σ reservations falls to
    0 AND Σ open margin rises to the reserved figure) and only then asks whether
    a stop exists, so "no stop" is measured against a position that provably
    opened. A build that drained the fill and converted nothing fails the
    conversion assertion under a different, named reason.
 9. **ARC 047. The daemon reported a stop it had not armed** — a count that
    matched by coincidence. GUARDED: the stop is compared by VALUE against
    `fill_price - stop_ticks x tick_size` computed here from the numbers this
    gate itself sent in, and by KEY against the `client_order_id` it reserved.
    A stop at any other level, or for any other order, fails.
10. **ARC 047. The two "committed" figures were confused.** The `status` reply's
    `committed` is §11.3's Σ over TAKEN reservations; `picture.committed` is
    §3's `Σ open margin + Σ reservations`. A fill moves the first to zero and
    leaves the second UNCHANGED — same capital, different bucket. GUARDED: both
    are asserted, separately and by name, and the invariance of the second is
    what proves a conversion rather than a leak.
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
from nixrisk.completions import (
    EVENT_CANCEL,
    EVENT_FILL,
    SPEC_EVENTS,
    WIRED_EVENTS,
)
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
    # ARC 047. The §4 cascade the daemon now CALLS. It is a subject of this gate
    # even though this arc edited none of it: the property measured is *the
    # running Limiter converts a fill and places its stop*, and the arm that
    # places the stop lives here. A plant in `FillHandler._arm` must redden this
    # gate, which it cannot do if the file is not declared its subject.
    "scripts/nixrisk/fills.py",
)

NAME = "check_limiter_daemon_dispatch"

LIMITERD_FILE = "scripts/limiterd.py"
COMPLETIONS_FILE = "scripts/nixrisk/completions.py"
FILLS_FILE = "scripts/nixrisk/fills.py"

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

# -- ARC 047, the FILL arm. Every figure here is DIFFERENT from the cancel
# arm's, deliberately: a fill asserted against 2000.0 could be satisfied by the
# cancel arm's own numbers, and two arms sharing a constant is two arms that can
# pass on one measurement.
FILL_CID = "cdd-fill-1"
FILL_EXEC = "cdd-exec-fill-1"
FILL_SYMBOL: Final[str] = "ES"
FILL_QTY: Final[int] = 3
FILL_MARGIN_PER_CONTRACT: Final[float] = 700.0
FILL_STOP_TICKS: Final[int] = 8
FILL_TICK_SIZE: Final[float] = 0.25
FILL_PRICE: Final[float] = 5000.0
ACCOUNT_BALANCE: Final[float] = 250_000.0
#: What §3's lifecycle must move: this much leaves Σ reservations and arrives in
#: Σ open margin, on ONE version stamp.
EXPECT_FILL_COMMITTED: Final[float] = FILL_QTY * FILL_MARGIN_PER_CONTRACT
#: §4's conversion, computed HERE from the numbers this gate sent in — never read
#: back off the daemon and compared against itself.
EXPECT_STOP_LEVEL: Final[float] = FILL_PRICE - FILL_STOP_TICKS * FILL_TICK_SIZE

#: The §2A events this build must dispatch, READ from the module's declaration.
#: Empty is a CANNOT_MEASURE, not a pass: a build that wires nothing has no
#: subject for this gate.
WIRED: Final[tuple[str, ...]] = tuple(WIRED_EVENTS)
#: ARC 047. The two paths are named CONSTANTS, not positions in that tuple. The
#: cancel arm used to say `WIRED[0]`, which was exact while one path was wired
#: and becomes a silent mis-aim the moment a later arc reorders the declaration:
#: a "cancel" arm pushing a fill would still go green and would measure the
#: wrong invariant.
HAS_CANCEL: Final[bool] = EVENT_CANCEL in WIRED
HAS_FILL: Final[bool] = EVENT_FILL in WIRED
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
                    # ARC 047. §4's distance->price conversion has no scale
                    # without a tick size, and this daemon has no instrument
                    # table to read one from. Passed here so the FILL arm's
                    # expected stop level is derivable from what the gate sent.
                    "--tick-size",
                    f"{FILL_SYMBOL}={FILL_TICK_SIZE}",
                    "--account-balance",
                    str(ACCOUNT_BALANCE),
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
    event = EVENT_CANCEL
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

    if block.get("cancels_dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"committed fell to 0.0 but the daemon reports "
                    f"cancels_dispatched={block.get('cancels_dispatched')!r}, not 1 — "
                    "the release did not come from the CANCEL dispatch, so this arm's "
                    "subject was not what released it"
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


def _fill_stop_for(status: dict[str, Any], cid: str) -> dict[str, Any] | None:
    """The daemon's own record of the synthetic stop protecting `cid`, or None."""
    for stop in (status.get("fills") or {}).get("stops") or ():
        if stop.get("client_order_id") == cid:
            return stop
    return None


def _fill_row(status: dict[str, Any]) -> dict[str, Any] | None:
    """The one published §3 row, or None. More than one is itself a finding."""
    rows = (status.get("fills") or {}).get("positions") or []
    return rows[0] if len(rows) == 1 else None


# R0911: the returns ARE the fail-closed ladder — a refused reservation, an
# absent tick size, a stop that predates the fill, a completion the loop never
# drained, an unprotected position, an unstopped fill, and a conversion that did
# not happen. Seven distinguishable states, each with its own reason; collapsing
# them into one exit would mean one sentence covering seven defects, and check
# contract v2 rule 11 makes the REASON the assertion (`CommandHandler._reply_for`
# records the identical argument one module over).
#
# This arm DECIDES — did the fill convert, and is the position protected. The
# value-by-value measurement it hands off to is `_arm_fill_values`; the two were
# one function until the split made the decision readable on its own.
def _fill_non_vacuity(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """Everything that must be TRUE BEFORE the fill is pushed, or no verdict.

    Split out of `_arm_fill` so the arm that judges the fill reads as one thing.
    Each condition below is a way this arm could look healthy while measuring
    nothing (§7.12 #8): capital that was never committed cannot be converted, a
    symbol with no tick size cannot have a stop at all — so a missing stop would
    measure an ABSENT INPUT rather than an omission — and a stop that predates
    the fill would make the safety assertion vacuous.

    Returns findings. Empty means the arm may proceed.
    """
    findings: list[tuple[str, str]] = []
    before = drive.cmd("status")
    seen["fill_consumed_before"] = (before.get("completions") or {}).get("consumed", 0)
    if not before.get("fills"):
        raise Cannot(
            f"{LIMITERD_FILE}: this build's status reply carries no `fills` block "
            "— the daemon holds no §4 fill path, so there is no subject"
        )
    took = drive.cmd(
        "reserve",
        strategy_id=STRATEGY,
        client_order_id=FILL_CID,
        symbol=FILL_SYMBOL,
        side="long",
        qty=FILL_QTY,
        margin_per_contract=FILL_MARGIN_PER_CONTRACT,
        stop_ticks=FILL_STOP_TICKS,
        stop_mode="fixed",
    )
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the fill reservation: {took.get('reason')}")
    seen["fill_committed_after_take"] = took.get("committed")
    seen["fill_reservations_before"] = (took.get("picture") or {}).get(
        "sum_reservations"
    )
    if took.get("committed") != EXPECT_FILL_COMMITTED:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: committed is {took.get('committed')!r} after "
                    f"reserving {FILL_QTY}x{FILL_MARGIN_PER_CONTRACT}; expected "
                    f"{EXPECT_FILL_COMMITTED}. Nothing was committed, so a later "
                    "conversion would convert nothing"
                ),
            )
        )
        return findings
    ticks = (took.get("fills") or {}).get("tick_size") or {}
    if ticks.get(FILL_SYMBOL) != FILL_TICK_SIZE:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the daemon reports tick_size={ticks!r} and this "
                    f"gate booted it with {FILL_SYMBOL}={FILL_TICK_SIZE}. Without "
                    "the scale §4's distance->price conversion cannot run at all, "
                    "so a missing stop would measure an absent input rather than "
                    "an omission"
                ),
            )
        )
        return findings
    if _fill_stop_for(took, FILL_CID) is not None:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: a stop is ALREADY armed for {FILL_CID!r} before "
                    "any fill was pushed. §4 converts at the CONFIRMED fill and "
                    "nowhere else; a stop that predates the fill would make the "
                    "safety assertion below vacuous"
                ),
            )
        )
    return findings


# R0911: the returns ARE the fail-closed ladder — the non-vacuity refusal, a
# completion the loop never drained, an unprotected position, an unstopped fill,
# and a conversion that did not happen. Each with its own reason; collapsing
# them into one exit would mean one sentence covering five defects, and check
# contract v2 rule 11 makes the REASON the assertion (`CommandHandler._reply_for`
# records the identical argument one module over).
#
# This arm DECIDES — did the fill convert, and is the position protected. The
# value-by-value measurement it hands off to is `_arm_fill_values`, and the
# preconditions to `_fill_non_vacuity`; the three were one function until the
# split made the decision readable on its own.
def _arm_fill(  # pylint: disable=too-many-return-statements
    drive: Drive, seen: dict[str, Any]
) -> list[tuple[str, str]]:
    """ARC 047. §2A:75's fill: OPEN, a trade_id, a PLACED STOP, and the conversion."""
    findings = _fill_non_vacuity(drive, seen)
    if findings:
        return findings
    consumed_before = seen["fill_consumed_before"]

    # -- THE PUSH: a §2A:75 fill exec report, from outside the process ---------
    path = drive.push(
        "fill",
        event=EVENT_FILL,
        client_order_id=FILL_CID,
        exec_id=FILL_EXEC,
        done_qty=FILL_QTY,
        symbol=FILL_SYMBOL,
        price=FILL_PRICE,
        cumulative_qty=FILL_QTY,
    )
    seen["fill_pushed"] = str(path)

    # -- NON-VACUITY 3: the loop DRAINED it. `consumed`, never `seen`: `seen`
    # moves inside the dispatch, so a build with no fill route would look like a
    # completion that never arrived (ARC 046 S5 / PLANT A's own measurement).
    try:
        drive.watch(
            lambda s: (s.get("completions") or {}).get("consumed", 0) > consumed_before,
            f"the loop to CONSUME the {EVENT_FILL} completion",
        )
    except _Missed as miss:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: {miss.what} — the daemon's own consumed counter "
                    f"never advanced past {consumed_before} within "
                    f"{WATCH_HORIZON_S}s. Last: "
                    f"{json.dumps(miss.status.get('completions'))}. The fill never "
                    "reached §5:322's loop, so nothing about dispatch was measured"
                ),
            )
        )
        return findings

    # -- SETTLE. The loop drained it; give the dispatch its full horizon to
    # produce a conversion, then read ONCE and judge. Deliberately NOT a watch on
    # the conversion alone: the two defects this arm separates (nothing
    # converted / converted with no stop) are both terminal states, and a watch
    # that only ever waited for the good one would report the bad one as a
    # timeout under the wrong reason.
    try:
        after = drive.watch(
            lambda s: (
                s.get("committed") == 0.0
                or ((s.get("completions") or {}).get("refused", 0) > 0)
                or ((s.get("completions") or {}).get("unwired", 0) > 0)
            ),
            "the daemon to reach a terminal state on the fill",
        )
    except _Missed as miss:
        after = miss.status
    # Watch PAST the tick: a conversion or a refusal landing a tick later is
    # still one, and a check that read once would call the interim state final.
    time.sleep(1.0)
    after = drive.cmd("status")

    block = after.get("completions") or {}
    fills = after.get("fills") or {}
    picture = after.get("picture") or {}
    stop = _fill_stop_for(after, FILL_CID)
    row = _fill_row(after)
    # TWO conditions, not one, and the split is what makes the safety arm fire on
    # the right defect. MEASURED, ARC 047 S5 / PLANT B: with the stop arm removed
    # the remainder release still ran, so the LEDGER released the capital
    # (committed 2100 -> 0) while the picture never advanced — the origin write
    # raised before its commit. A single `converted` flag over both readings was
    # False, and the run failed under "did not convert", which is the opposite of
    # what had happened: the capital moved and nothing protected the position.
    capital_released = after.get("committed") == 0.0
    open_margin_booked = picture.get("sum_open_margin") == EXPECT_FILL_COMMITTED
    converted = capital_released and open_margin_booked
    seen["fill_block"] = block
    seen["fill_stop"] = stop
    seen["fill_row"] = row
    seen["fill_picture"] = picture
    seen["fill_unstopped"] = fills.get("unstopped")

    # ================= THE SAFETY ARM — read this one first =================
    # ONE branch, TWO readings, and they must not merge: a missing stop BESIDE
    # released capital is the unprotected position; a missing stop with the
    # capital still held is simply a fill that was never dispatched. Merging
    # them would hand an operator "no stop" for a build that did nothing at all.
    # It is also the narrowing every value comparison below depends on: past
    # this block `stop` is a stop.
    if stop is None:
        if not capital_released:
            findings.append((LIMITERD_FILE, _not_converted(after, block, picture)))
            return findings
        findings.append(
            (
                FILLS_FILE,
                (
                    f"UNPROTECTED POSITION. The daemon RELEASED "
                    f"{EXPECT_FILL_COMMITTED} of reservation on a confirmed fill for "
                    f"{FILL_CID!r} (committed {EXPECT_FILL_COMMITTED} -> "
                    f"{after.get('committed')!r}, Σ open margin "
                    f"{picture.get('sum_open_margin')!r}) and its stop book holds "
                    f"NO STOP for that order (stops={fills.get('stops')!r}, "
                    f"unstopped={fills.get('unstopped')!r}, "
                    f"last_reason={block.get('last_reason')!r}). §12.1 makes the "
                    "stop SYNTHETIC and Limiter-held, so a position with no "
                    "StopState is a live position nothing protects: §7:501 prices "
                    "its bucket exposure from a distance that was never published, "
                    "and §14 resolves the condition toward FLAT. This is the "
                    "hazard I11 guards, created by the daemon itself"
                ),
            )
        )
        return findings
    if fills.get("unstopped"):
        findings.append(
            (
                FILLS_FILE,
                (
                    f"the origin writer recorded UNSTOPPED fill(s) "
                    f"{fills.get('unstopped')!r} — §3's row was refused because the "
                    "trade had no armed stop. The fill is already booked in the "
                    "execution ledger (§4 makes it a fact, not a negotiation), so "
                    "this is a real filled position that the published table does "
                    "not carry and no stop protects (§4, §12.1; §14 -> FLAT)"
                ),
            )
        )
        return findings
    # ========================================================================

    if not converted:
        # A stop IS armed and the conversion did not complete — §3's other half.
        findings.append((LIMITERD_FILE, _not_converted(after, block, picture)))
        return findings
    return findings + _arm_fill_values(drive, after, stop, row, path)


def _not_converted(
    after: dict[str, Any], block: dict[str, Any], picture: dict[str, Any]
) -> str:
    """The reason a drained fill left §3's lifecycle where it started.

    Extracted so the two callers above state it identically: a fill with no stop
    and no conversion, and a fill with a stop whose conversion did not complete,
    are the same defect read from two sides, and two hand-written copies of one
    sentence is the restatement directive 3 forbids.
    """
    return (
        f"THE DAEMON DID NOT CONVERT. A §2A {EVENT_FILL} for "
        f"{FILL_CID!r} was DRAINED BY THE LOOP "
        f"(consumed={block.get('consumed')}, seen={block.get('seen')}) "
        f"and committed is still {after.get('committed')!r} with Σ open "
        f"margin {picture.get('sum_open_margin')!r} after "
        f"{WATCH_HORIZON_S}s — expected {EXPECT_FILL_COMMITTED} -> 0.0 "
        f"and 0.0 -> {EXPECT_FILL_COMMITTED}. "
        f"fills_dispatched={block.get('fills_dispatched')} "
        f"unwired={block.get('unwired')} refused={block.get('refused')} "
        f"unknown={block.get('unknown')} "
        f"last_disposition={block.get('last_disposition')!r} "
        f"last_reason={block.get('last_reason')!r}. §3's lifecycle "
        "releases a reservation ON FILL — it converts to open-margin — "
        "so this build holds capital against an order that has already "
        "filled, and the position it opened is in no published table"
    )


# Every value the fill produced, judged as SEPARATE named findings — check
# contract v2 rule 11 makes the REASON the assertion, so ten distinguishable
# defects may not share one reason string. Split out of `_arm_fill` so the arm
# that DECIDES (did it convert? is it protected?) is readable apart from the arm
# that MEASURES, and split again into `_fill_stop_findings` /
# `_fill_row_findings` because *is this position protected* and *is this
# position published correctly* are two questions.
def _arm_fill_values(
    drive: Drive,
    after: dict[str, Any],
    stop: dict[str, Any],
    row: dict[str, Any] | None,
    path: Path,
) -> list[tuple[str, str]]:
    """Every value the fill produced, judged against what this gate sent in."""
    findings: list[tuple[str, str]] = []
    block = after.get("completions") or {}
    fills = after.get("fills") or {}
    picture = after.get("picture") or {}

    if block.get("fills_dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the conversion happened but the daemon reports "
                    f"fills_dispatched={block.get('fills_dispatched')!r}, not 1 — "
                    "it did not come from the fill dispatch, so this arm's subject "
                    "was not what converted it"
                ),
            )
        )
    if block.get("last_source") != str(path):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"PROVENANCE: the daemon dispatched from "
                    f"{block.get('last_source')!r}, not from the exec report this "
                    f"gate wrote at {str(path)!r}. A conversion that did not arrive "
                    "through §5:322's completion path proves the handler, not the "
                    "daemon"
                ),
            )
        )
    findings += _fill_stop_findings(stop)
    if row is None:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the fill converted and armed a stop but the published §3 table "
                    f"holds {len(fills.get('positions') or [])} row(s), not exactly 1 "
                    f"({fills.get('positions')!r}) — §3:159 keys the table by "
                    "trade_id and this drive opened one trade"
                ),
            )
        )
        return findings
    findings += _fill_row_findings(row, picture)
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
    findings += _arm_fill_feedback(drive, row)
    return findings


def _fill_stop_findings(stop: dict[str, Any]) -> list[tuple[str, str]]:
    """§4's conversion, judged BY VALUE against what this gate sent in.

    Every expected figure is computed HERE from the constants this gate pushed —
    `EXPECT_STOP_LEVEL = FILL_PRICE - FILL_STOP_TICKS x FILL_TICK_SIZE` — and
    never read back off the daemon and compared against itself (§7.12 #9).
    """
    findings: list[tuple[str, str]] = []
    if abs(float(stop.get("level", 0.0)) - EXPECT_STOP_LEVEL) > 1e-9:
        findings.append(
            (
                FILLS_FILE,
                (
                    f"the protective stop for {FILL_CID!r} is at "
                    f"{stop.get('level')!r}; §4 anchors it at the CONFIRMED fill, "
                    f"so it must be {FILL_PRICE} - {FILL_STOP_TICKS} x "
                    f"{FILL_TICK_SIZE} = {EXPECT_STOP_LEVEL}. A stop at any other "
                    "price protects a different position than the one that filled"
                ),
            )
        )
    if stop.get("anchor") != FILL_PRICE:
        findings.append(
            (
                FILLS_FILE,
                (
                    f"the stop's anchor is {stop.get('anchor')!r}, not the confirmed "
                    f"fill price {FILL_PRICE} — §4 converts the distance ONCE, "
                    "against the fill, and an anchor from anywhere else means the "
                    "conversion ran against a price the venue did not report"
                ),
            )
        )
    if stop.get("initial_distance_ticks") != FILL_STOP_TICKS:
        findings.append(
            (
                FILLS_FILE,
                (
                    f"the stop's distance is {stop.get('initial_distance_ticks')!r}, "
                    f"not the approved {FILL_STOP_TICKS} — §7:476 sized the position "
                    "against that distance and §7:501 re-prices the bucket from it"
                ),
            )
        )
    return findings


def _fill_row_findings(
    row: dict[str, Any], picture: dict[str, Any]
) -> list[tuple[str, str]]:
    """§3's published row and §3's snapshot, judged field by field.

    Split from the stop comparisons above because they answer different
    questions — *is this position protected* and *is this position published
    correctly* — and an operator handed one reason string over both would have
    to guess which half moved.
    """
    findings: list[tuple[str, str]] = []
    if row.get("state") != "open":
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the published row is in state {row.get('state')!r}, not 'open' "
                    '— §14: *"Open" = confirmed fill only. Never optimistic.* A '
                    "confirmed fill that did not publish an OPEN row leaves §7's "
                    "correlation cap blind to a live position"
                ),
            )
        )
    if not row.get("trade_id"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "the published row carries no trade_id — §4 mints one at OPEN "
                    "and §3:159 keys the position table by it"
                ),
            )
        )
    elif row.get("trade_id") == FILL_CID:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the minted trade_id is {row.get('trade_id')!r}, which IS the "
                    f"client_order_id — D3.177's architect ruling keeps the two "
                    "DISTINCT, and an equality that holds by construction hides "
                    "every skew because no observation can contradict it"
                ),
            )
        )
    if row.get("size") != FILL_QTY:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the published size is {row.get('size')!r}, not the filled "
                    f"{FILL_QTY} — §4: the position is the ACTUAL filled qty"
                ),
            )
        )
    if row.get("stop_distance") != FILL_STOP_TICKS:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the published stop_distance is {row.get('stop_distance')!r}, "
                    f"not {FILL_STOP_TICKS} — §7:501 prices this position's bucket "
                    "exposure from that field, so a wrong one mis-prices the cap"
                ),
            )
        )
    if picture.get("sum_reservations") != 0.0:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"§3's snapshot still reports sum_reservations="
                    f"{picture.get('sum_reservations')!r} after the conversion — the "
                    "reservation was released in the ledger and the published "
                    "picture still holds it, so one commitment is booked twice"
                ),
            )
        )
    if picture.get("committed") != EXPECT_FILL_COMMITTED:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"§3's snapshot reports committed={picture.get('committed')!r} "
                    f"after the conversion, not {EXPECT_FILL_COMMITTED}. A "
                    "conversion moves capital from Σ reservations to Σ open margin "
                    "and changes neither the total nor the account's exposure; a "
                    "moved total means capital was created or destroyed by a "
                    "bookkeeping step"
                ),
            )
        )
    return findings


def _arm_fill_feedback(drive: Drive, row: dict[str, Any]) -> list[tuple[str, str]]:
    """§4:203-206's outcome push, tagged by `trade_id`. Read off the FILESYSTEM.

    Read from the outbox rather than from a counter in the reply, for the reason
    the provenance arm reads `last_source`: the question is whether the DAEMON
    wrote a record a strategy could act on, and a count of pushes cannot say
    whether the record carried this trade's id.
    """
    findings: list[tuple[str, str]] = []
    trade_id = str(row.get("trade_id") or "")
    record = drive.dir / "outbox" / f"{trade_id}.feedback.json"
    if not record.exists():
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"no §4:203-206 outcome record at {record.name} — the position "
                    f"for trade {trade_id!r} is OPEN with a stop armed and the "
                    "originating strategy FSM was never told. §4:203-206 pushes "
                    "EVERY outcome, and 'open' is one of them; a strategy that "
                    "never hears its fill holds §4:208's lock until §4:210-212's "
                    "breaker fires on an order that actually filled"
                ),
            )
        )
        return findings
    try:
        pushed = json.loads(record.read_text())
    except ValueError as exc:
        findings.append(
            (LIMITERD_FILE, f"the outcome record at {record.name} is not JSON: {exc}")
        )
        return findings
    if pushed.get("outcome") != "open":
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the outcome record says outcome={pushed.get('outcome')!r}, not "
                    "'open' — §4:203-206 enumerates the outcomes and a confirmed "
                    "fill is an open"
                ),
            )
        )
    if pushed.get("trade_id") != trade_id:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the outcome record is tagged trade_id="
                    f"{pushed.get('trade_id')!r} and the published row is "
                    f"{trade_id!r} — §4 tags feedback BY trade id precisely so it "
                    "cannot be applied to the wrong position"
                ),
            )
        )
    if abs(float(pushed.get("stop_level", 0.0)) - EXPECT_STOP_LEVEL) > 1e-9:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the outcome record reports stop_level="
                    f"{pushed.get('stop_level')!r}, not {EXPECT_STOP_LEVEL} — the "
                    "strategy is being told about a stop other than the one armed"
                ),
            )
        )
    return findings


def _arm_fill_idempotent(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """§4:214 on the FILL path: a re-delivered fill converts nothing, twice-over.

    The fill is where a defeated dedup costs most. A second cancel releases the
    same reservation twice; a second FILL would re-run an arm, a release AND a
    published row — so this arm asserts the stop count, the row count, the Σ open
    margin and the ledger's refusal count, not just the aggregate.
    """
    findings: list[tuple[str, str]] = []
    before = drive.cmd("status")
    consumed_before = (before.get("completions") or {}).get("consumed", 0)
    drive.push(
        "fill-redelivered",
        event=EVENT_FILL,
        client_order_id=FILL_CID,
        exec_id=FILL_EXEC,
        done_qty=FILL_QTY,
        symbol=FILL_SYMBOL,
        price=FILL_PRICE,
        cumulative_qty=FILL_QTY,
    )
    try:
        drive.watch(
            lambda s: (s.get("completions") or {}).get("consumed", 0) > consumed_before,
            "the loop to CONSUME the re-delivered fill",
        )
    except _Missed as miss:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: {miss.what} — the re-delivery never reached the "
                    f"loop, so fill idempotency was not measured. Last: "
                    f"{json.dumps(miss.status.get('completions'))}"
                ),
            )
        )
        return findings
    # WATCH PAST THE TICK, for the reason the cancel arm does.
    time.sleep(1.0)
    status = drive.cmd("status")
    block = status.get("completions") or {}
    fills = status.get("fills") or {}
    picture = status.get("picture") or {}
    seen["fill_block_after_redelivery"] = block
    seen["fill_picture_after_redelivery"] = picture

    if block.get("fills_dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"DOUBLE FILL DISPATCH: after re-delivering the IDENTICAL exec "
                    f"report ({FILL_CID}, {FILL_EXEC}) the daemon reports "
                    f"fills_dispatched={block.get('fills_dispatched')!r}, not 1. "
                    "§4:214 deduplicates broker events by (order_id, exec_id); a "
                    "second fill dispatch re-runs §4's whole cascade — an arm, a "
                    "release and a published row — against an execution the venue "
                    "sent once"
                ),
            )
        )
    if block.get("duplicates", 0) < 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the re-delivered fill was consumed (seen={block.get('seen')}) "
                    f"and the daemon booked duplicates={block.get('duplicates')!r} — "
                    "the §4:214 dedup did not see it, so whatever stopped the second "
                    "conversion was not the daemon's"
                ),
            )
        )
    stops = fills.get("stops") or []
    if len(stops) != 1:
        findings.append(
            (
                FILLS_FILE,
                (
                    f"after the re-delivery the stop book holds {len(stops)} stop(s) "
                    f"({stops!r}), not 1 — §4 converts distance->price ONCE at the "
                    "confirmed fill, and a second stop for one order means a live "
                    "stop was replaced by one anchored at a re-read price"
                ),
            )
        )
    rows = fills.get("positions") or []
    if len(rows) != 1:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"after the re-delivery the published §3 table holds {len(rows)} "
                    f"row(s) ({rows!r}), not 1 — §3:159 keys it by trade_id and two "
                    "rows for one trade is a table that is not keyed by it"
                ),
            )
        )
    if picture.get("sum_open_margin") != EXPECT_FILL_COMMITTED:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"Σ open margin is {picture.get('sum_open_margin')!r} after the "
                    f"re-delivery, not {EXPECT_FILL_COMMITTED} — one execution was "
                    "booked as open margin twice, and §6.5's aggregate cap is "
                    "evaluated against that number"
                ),
            )
        )
    if status.get("committed") != 0.0:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"committed is {status.get('committed')!r} after the fill "
                    "re-delivery, not 0.0 — a second terminal event moved §11.3's "
                    "aggregate"
                ),
            )
        )
    if fills.get("handled") != 1:
        findings.append(
            (
                FILLS_FILE,
                (
                    f"the fill handler reports handled={fills.get('handled')!r}, not "
                    "1 — the cascade ran a second time on one venue execution"
                ),
            )
        )
    if fills.get("refused_releases"):
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the remainder path booked "
                    f"{fills.get('refused_releases')} refused release(s). The "
                    "daemon's §4:214 dedup is supposed to stop a re-delivered exec "
                    "report BEFORE §4's cascade runs; a refused release means the "
                    "re-delivery reached the handler and only the reservation "
                    "ledger's own guard (I2's, and it stands) stopped the second "
                    "release"
                ),
            )
        )
    return findings


def _arm_idempotent(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """§4:214: a RE-DELIVERED exec report releases nothing. The daemon's dedup."""
    findings: list[tuple[str, str]] = []
    event = EVENT_CANCEL
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

    # ARC 047. `cancels_dispatched`, not `dispatched`: with two paths wired the
    # aggregate also counts the FILL arm's dispatch, and an assertion that read
    # it would be satisfied by the wrong path having run. Per-path counters are
    # what keep this arm's subject the cancel.
    if block.get("cancels_dispatched") != 1:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"DOUBLE DISPATCH: after re-delivering the IDENTICAL exec report "
                    f"({CANCEL_CID}, {CANCEL_EXEC}) the daemon reports "
                    f"cancels_dispatched={block.get('cancels_dispatched')!r}, not 1. "
                    "§4:214 deduplicates broker events by (order_id, exec_id); a "
                    "second dispatch is the double release §14 forbids, reached at "
                    "the daemon boundary"
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
    prior = drive.cmd("status").get("completions") or {}
    before = prior.get("unwired", 0)
    # ARC 047. The DELTA, not the absolute. With two paths wired, `dispatched` is
    # already 2 by the time this arm runs, so a literal `!= 1` measured how many
    # arms had gone before it rather than whether THIS event was dispatched.
    dispatched_before = prior.get("dispatched", 0)
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
    if block.get("dispatched") != dispatched_before:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"dispatched moved from {dispatched_before!r} to "
                    f"{block.get('dispatched')!r} on a §2A {event} this build "
                    f"declares unwired (WIRED_EVENTS={list(WIRED)}) — an event no "
                    "handler serves was routed to one"
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
    # ARC 047. TWO reservations are taken in a full drive — one released by the
    # cancel arm, one CONVERTED by the fill arm — and §3 makes a fill a terminal
    # release too (*"released on: fill (converts to open-margin)"*). The figure is
    # DERIVED from which arms this build can run rather than written as a
    # literal, so a build that wires only cancel still gets an exact assertion.
    expect_released = int(HAS_CANCEL) + int(HAS_FILL)
    if res.get("released") != expect_released:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the stop record reports released={res.get('released')!r}, not "
                    f"{expect_released} — §14: every reservation reaches EXACTLY ONE "
                    f"terminal release, and this run took {expect_released} "
                    f"reservation(s) (wired paths: {list(WIRED)})"
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
        + _fill_evidence(seen)
    )


def _fill_evidence(seen: dict[str, Any]) -> str:
    """ARC 047's arm, in the evidence block. Absent when the arm did not run."""
    if not HAS_FILL:
        return "; fill arm: NOT RUN (on_fill is not in WIRED_EVENTS)"
    block = seen.get("fill_block") or {}
    after = seen.get("fill_block_after_redelivery") or {}
    stop = seen.get("fill_stop") or {}
    row = seen.get("fill_row") or {}
    picture = seen.get("fill_picture") or {}
    return (
        f"; FILL ARM: reserved {EXPECT_FILL_COMMITTED} for {FILL_CID!r} "
        f"(committed -> {seen.get('fill_committed_after_take')}), pushed a §2A "
        f"{EVENT_FILL} at {FILL_PRICE}, the loop dispatched it via "
        f"{block.get('last_source')!r} (fills_dispatched="
        f"{block.get('fills_dispatched')}), trade {row.get('trade_id')!r} is OPEN "
        f"size {row.get('size')} stop_distance {row.get('stop_distance')}, the "
        f"PROTECTIVE STOP is armed at {stop.get('level')} (expected "
        f"{EXPECT_STOP_LEVEL} = {FILL_PRICE} - {FILL_STOP_TICKS}x"
        f"{FILL_TICK_SIZE}, anchor {stop.get('anchor')}), the reservation "
        f"CONVERTED (Σ reservations {picture.get('sum_reservations')}, Σ open "
        f"margin {picture.get('sum_open_margin')}, committed "
        f"{picture.get('committed')} unchanged), unstopped="
        f"{seen.get('fill_unstopped')!r}; re-delivering the identical fill left "
        f"fills_dispatched={after.get('fills_dispatched')} "
        f"duplicates={after.get('duplicates')} Σ open margin "
        f"{(seen.get('fill_picture_after_redelivery') or {}).get('sum_open_margin')}"
    )


def _no_subject() -> str:
    """Why this build cannot be measured at all, or `""`. Check contract rule 10.

    Split out of `run` so the preconditions are one readable statement rather
    than two early returns inside the drive's own try/finally. Both are
    CANNOT_MEASURE and neither is a pass: a build that wires nothing, and a build
    that stopped wiring the path every arm below the fill arm is written against,
    are two ways to have no subject.
    """
    if not WIRED:
        return (
            f"{COMPLETIONS_FILE}: WIRED_EVENTS is empty — this build dispatches "
            "no §2A completion at all, so there is no subject"
        )
    if not HAS_CANCEL:
        return (
            f"{COMPLETIONS_FILE}: WIRED_EVENTS is {list(WIRED)} and does not "
            f"contain {EVENT_CANCEL!r}, which every arm of this gate below the "
            "fill arm is written against"
        )
    return ""


def _drive_every_arm(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """Every arm, in order, stopping at the first that finds something.

    THE ORDER IS DELIBERATE and it is not alphabetical. The FILL arms run BEFORE
    the cancel idempotency arm because a defeated §4:214 dedup breaks BOTH paths,
    and the fill is where it costs most — a re-run cascade re-arms, re-releases
    and re-publishes, where a re-run cancel only releases twice. Running the fill
    arms first makes such a failure name the expensive site rather than the cheap
    one.
    """
    findings, seen_now = _arm_driven(drive)
    seen.update(seen_now)
    if not findings and HAS_FILL:
        findings += _arm_fill(drive, seen)
        if not findings:
            findings += _arm_fill_idempotent(drive, seen)
    if not findings:
        findings += _arm_idempotent(drive, seen)
        findings += _arm_unwired(drive, seen)
    return findings


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure-only. `CORRECTABLE = False` — see the module constant."""
    absent = _no_subject()
    if absent:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=absent)
    drive: Drive | None = None
    seen: dict[str, Any] = {}
    try:
        drive = Drive(ctx.nix_home)
        findings = _drive_every_arm(drive, seen)
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
