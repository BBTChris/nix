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

import ast
import json
import os
import subprocess  # nosec B404 - the subject is a REAL limiterd PROCESS
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order

# ARC 054. The daemon's OWN spellings for §3:173's onset surface, IMPORTED for
# the same reason and under the same argument as the line above: a second copy of
# the directory name here could drift from the one the process opens, and the
# gate would then declare an onset into a path nothing reads and read the silence
# as a defect. Importing two `Final[str]` constants is not driving the library.
from limiterd import ONSET_DIR, ONSET_STATE_NAME

# The WIRED-PATH DECLARATION, imported rather than spelled (directive 3). This is
# not the import the process-not-library argument forbids: the subject is still
# the running daemon, and this is a constant tuple naming which paths this build
# claims to serve. A second copy here would let the gate keep asserting a path
# the build had stopped wiring.
from nixrisk.completions import (
    EVENT_CANCEL,
    EVENT_FILL,
    EVENT_REJECT,
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
    # ARC 053. The §3 terminal handlers the daemon now CALLS on BOTH resolution
    # paths — `on_reject` from the completion dispatch and
    # `resolve_pending_timeouts` from the per-tick poll. Declared for the reason
    # `fills.py` is: the property measured is *the running Limiter resolves a
    # reject and an overdue order*, and a plant in either handler must redden
    # this gate, which it cannot do if the file is not its subject. This arc
    # edited none of it — `outcomes.py` is byte-identical and that is asserted
    # with `git hash-object`, not claimed.
    "scripts/nixrisk/outcomes.py",
    # ARC 054. I11's onset SELECTION, which the daemon now CALLS. Declared for
    # the reason `fills.py` and `outcomes.py` are: the property measured here is
    # *the running Limiter sweeps its pending entries on onset and leaves the
    # exits alone*, and a plant in `_classify_for_onset` must redden this gate.
    # It does NOT duplicate `check_flatten` ARM 3b (doctrine C.9): that arm
    # measures WHICH orders the selection admits; this one measures whether
    # anything with a pid ever invokes it. `flatten.py` is byte-identical across
    # this arc and that is asserted with `git hash-object`, not claimed.
    "scripts/nixrisk/flatten.py",
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

# -- ARC 053, the REJECT arm. Its own id, its own exec id and its own margin,
# for the reason the fill arm's are its own: an arm asserted against another
# arm's numbers is an arm that can pass on the wrong measurement.
REJECT_CID = "cdd-reject-1"
REJECT_EXEC = "cdd-exec-reject-1"
REJECT_QTY: Final[int] = 5
REJECT_MARGIN_PER_CONTRACT: Final[float] = 300.0
EXPECT_REJECT_COMMITTED: Final[float] = REJECT_QTY * REJECT_MARGIN_PER_CONTRACT

# -- ARC 053, the PENDING-TIMEOUT arm. Two orders, deliberately: one the venue
# says is DEAD (must release) and one it cannot resolve (must be HELD, and must
# still be held after many further queries). One order could only ever prove one
# of the two, and the second is where §4's no-resend rule actually bites.
TIMEOUT_DEAD_CID = "cdd-timeout-dead-1"
TIMEOUT_HELD_CID = "cdd-timeout-held-1"
TIMEOUT_QTY: Final[int] = 4
TIMEOUT_MARGIN_PER_CONTRACT: Final[float] = 250.0
EXPECT_TIMEOUT_COMMITTED: Final[float] = TIMEOUT_QTY * TIMEOUT_MARGIN_PER_CONTRACT
#: The seam's OWN spellings (`broker_seam.OrderStatus.state`), not invented here.
STATE_DEAD: Final[str] = "cancelled"
STATE_UNRESOLVABLE: Final[str] = "indeterminate"
#: How many reservations the pending-timeout arm takes, and therefore how many
#: further terminal releases the stop record must show. DERIVED into
#: `_arm_stop_record`'s expectation rather than written there as a literal.
TIMEOUT_RESERVATIONS: Final[int] = 2
#: How many FURTHER §4 queries the unresolvable order must survive unchanged.
#: One query proves nothing about the second — §0a, and the resend this arm
#: exists to refuse would most plausibly appear on a retry, not a first look.
FURTHER_QUERIES: Final[int] = 20

# -- ARC 054, the ONSET arm. §3:172-174: *"Blackout/HALT onset => Limiter cancels
# all pending ENTRY orders (exits untouched) — no order may fill inside a window
# it was not approved for."* TWO symbols and TWO strategies, deliberately: a
# per-symbol blackout that cancelled everything and a per-symbol blackout that
# cancelled the right things are indistinguishable with one symbol in the book,
# and §6.1's windows are per-symbol off the live calendar. Its own ids and its
# own margin for the reason every other arm's are its own.
ONSET_BLACKOUT_SYMBOL: Final[str] = FILL_SYMBOL
ONSET_OTHER_SYMBOL: Final[str] = "NQ"
ONSET_STRATEGY_B: Final[str] = "check-daemon-dispatch-onset-b"
ONSET_IN_SCOPE: Final[tuple[str, ...]] = ("cdd-onset-a1", "cdd-onset-a2")
ONSET_OUT_OF_SCOPE: Final[tuple[str, ...]] = ("cdd-onset-b1", "cdd-onset-b2")
ONSET_QTY: Final[int] = 6
ONSET_MARGIN_PER_CONTRACT: Final[float] = 150.0
EXPECT_ONSET_EACH: Final[float] = ONSET_QTY * ONSET_MARGIN_PER_CONTRACT
#: How many reservations the onset arm takes, and therefore how many further
#: terminal releases the stop record must show. DERIVED into `_arm_stop_record`'s
#: expectation rather than written there as a literal.
ONSET_RESERVATIONS: Final[int] = len(ONSET_IN_SCOPE) + len(ONSET_OUT_OF_SCOPE)
#: The two onset causes, by the seam's OWN spellings — never re-spelled here.
CAUSE_BLACKOUT: Final[str] = "blackout_onset"
CAUSE_HALT: Final[str] = "halt_onset"
#: How many further ticks the arm watches inside the SAME declared blackout
#: before it will say the sweep is edge-triggered. One tick proves nothing: a
#: sweep that re-fired every tick would look identical after one look.
EDGE_SETTLE_S: Final[float] = 1.5


#: ARC 053 / D3.463. Every `reserve` this gate sends now carries a signal
#: instant, because the daemon REFUSES one that does not: an absent `signal_ts`
#: reads STALE (§17) rather than being dated at arrival. Sent as a live clock
#: read rather than a constant so the drive is never accidentally stale.
def _fresh_signal_ts() -> float:
    """A signal instant the daemon will accept. See D3.463."""
    return time.time()


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
#: ARC 053, derived the same way and for the same reason.
HAS_REJECT: Final[bool] = EVENT_REJECT in WIRED
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

    @staticmethod
    def _atomically(path: Path, payload: dict[str, Any]) -> Path:
        """Write one JSON file the daemon may be reading on its own tick.

        ARC 054, MEASURED. Every writer below used `Path.write_text`, which
        creates the file and then fills it, and the daemon scans its directories
        every `DRIVE_TICK_S` (0.02s). The window between the two is real: a run
        of this gate had the daemon read `cdd0012.json` EMPTY and answer
        *"is not valid JSON: JSONDecodeError('Expecting value: line 1 column
        1')"*, after which every field of that `status` reply was absent and the
        FILL arm reported a conversion that had in fact happened. A gate that
        goes red on its own write race is a gate whose red means nothing, and the
        onset surface below is read on EVERY tick, so it is the most exposed of
        all. `os.replace` inside the same directory is atomic, and the daemon's
        scanners only ever pick up `*.json`, so the temp name is invisible to it.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".partial")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
        return path

    def cmd(self, verb: str, **fields: object) -> dict[str, Any]:
        """Send one command file; return the daemon's own reply."""
        self._n += 1
        cid = f"cdd{self._n:04d}"
        self._atomically(
            self.dir / "inbox" / f"{cid}.json",
            {"schema": 1, "id": cid, "verb": verb, **fields},
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
        return self._atomically(
            self.dir / "completions" / f"{name}.json", {"schema": 1, **fields}
        )

    def answer(self, client_order_id: str, state: str, **fields: object) -> Path:
        """ARC 053. THE STUB BROKER'S §4 STATUS ANSWER, where the daemon reads one.

        A file, not a call: the daemon's `DirectoryStatusQuery` opens
        `DIR/status/<id>.json`, so writing one here is the venue answering from
        OUTSIDE the process — the same out-of-process argument `push` makes for
        an exec report. An order with NO file here is answered `unknown`, which
        is the seam's own spelling for *this surface has no record of the id*.
        """
        return self._atomically(
            self.dir / "status" / f"{client_order_id}.json",
            {"state": state, **fields},
        )

    def declare_onset(
        self, *, halt: bool = False, blackout: list[str] | None = None
    ) -> Path:
        """ARC 054. THE ONSET, DECLARED FROM OUTSIDE THE PROCESS.

        A file, not a call, and that is the whole point of this arm: the daemon
        reads `DIR/onset/state.json` on its own tick and computes the EDGE
        itself. A gate that called `cancel_entries_on_onset` directly would prove
        `nixrisk/flatten.py`, which `check_flatten` ARM 3b already proves (ARC
        045) — and would prove nothing at all about whether anything with a pid
        ever invokes it, which is the gap I1 names.
        """
        return self._atomically(
            self.dir / ONSET_DIR / ONSET_STATE_NAME,
            {"halt": bool(halt), "blackout": list(blackout or ())},
        )

    def reserve(self, client_order_id: str, qty: int, margin: float, **fields: object):
        """One `reserve`, always carrying a FRESH signal instant (D3.463)."""
        return self.cmd(
            "reserve",
            strategy_id=STRATEGY,
            client_order_id=client_order_id,
            symbol=fields.pop("symbol", "ES"),
            side="long",
            qty=qty,
            margin_per_contract=margin,
            stop_ticks=fields.pop("stop_ticks", 8),
            stop_mode="fixed",
            signal_ts=_fresh_signal_ts(),
            **fields,
        )

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

    def settle(self, pred, seconds: float) -> dict[str, Any]:
        """Poll the daemon's own status until `pred`, then return the LAST status.

        Unlike `watch`, this NEVER raises when the condition does not arrive.
        Its callers exist to report an ABSENCE with a sentence — *the loop
        consumed the reject and did not release it*, *the order is past its
        deadline and nothing queried it* — and a `_Missed` timeout would replace
        that sentence with a generic one. The distinction is this gate's own
        PLANT C lesson (see the test module's docstring): a broken instrument
        and the defect it was built to find must not read alike.
        """
        deadline = time.time() + seconds
        status = self.cmd("status")
        while time.time() < deadline:
            if pred(status):
                return status
            time.sleep(0.03)
            status = self.cmd("status")
        return status

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
    # ARC 053 / D3.463: `signal_ts` is now REQUIRED — a reserve without one is
    # refused as STALE (§17), so `Drive.reserve` always sends a live clock read.
    took = drive.reserve(CANCEL_CID, QTY, MARGIN_PER_CONTRACT)
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
    took = drive.reserve(
        FILL_CID,
        FILL_QTY,
        FILL_MARGIN_PER_CONTRACT,
        symbol=FILL_SYMBOL,
        stop_ticks=FILL_STOP_TICKS,
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


def _arm_reject(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """ARC 053. The daemon RELEASES on a §2A reject, driven through the ingress.

    The cheap half of this arc and it reuses the ARC 046 mechanism whole: a
    reject exec report is a sender completion like any other, and the only new
    thing is that `completions.py` now routes it to `outcomes.on_reject` instead
    of naming it UNWIRED. The arm is separate from the cancel arm rather than
    parameterised over it because the two release paths must be independently
    plantable — PLANT A removes the reject dispatch and must not be able to hide
    behind a working cancel.
    """
    findings: list[tuple[str, str]] = []
    took = drive.reserve(REJECT_CID, REJECT_QTY, REJECT_MARGIN_PER_CONTRACT)
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reject reservation: {took.get('reason')}")
    before = drive.cmd("status")
    seen["reject_committed_before"] = before.get("committed")
    seen["reject_dispatched_before"] = (before.get("completions") or {}).get(
        "rejects_dispatched"
    )
    if seen["reject_dispatched_before"] is None:
        raise Cannot(
            f"{COMPLETIONS_FILE}: this build's dispatch record carries no "
            "`rejects_dispatched` counter — the per-path counters cannot "
            "distinguish a reject from a cancel, so there is nothing to measure"
        )
    path = drive.push(
        "reject",
        event=EVENT_REJECT,
        client_order_id=REJECT_CID,
        exec_id=REJECT_EXEC,
        done_qty=0,
    )
    seen["reject_pushed"] = str(path)
    # `settle`, not `watch`: a build that CONSUMES the reject and never releases
    # is the defect this arm exists to catch, and it must be reported as that
    # sentence rather than as a generic timeout. The wait keys on the completion
    # being CONSUMED — which happens on every build, wired or not — so the
    # assertions below are made against a daemon that has definitely seen it.
    consumed_before = (before.get("completions") or {}).get("consumed", 0)
    after = drive.settle(
        lambda st: (st.get("completions") or {}).get("consumed", 0) > consumed_before,
        WATCH_HORIZON_S,
    )
    completions = after.get("completions") or {}
    if completions.get("consumed", 0) <= consumed_before:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the §2A {EVENT_REJECT} written to the completions directory "
                    f"NEVER ARRIVED: consumed is still {consumed_before} after "
                    f"{WATCH_HORIZON_S}s. That is the INGRESS, not the dispatch — "
                    "the loop is not reading the directory at all, so nothing "
                    "below could measure the reject path"
                ),
            )
        )
        return findings
    seen["reject_dispatched"] = completions.get("rejects_dispatched")
    seen["reject_last_disposition"] = completions.get("last_disposition")
    seen["reject_committed_after"] = after.get("committed")
    released = float(before.get("committed") or 0.0) - float(
        after.get("committed") or 0.0
    )
    if not completions.get("rejects_dispatched"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"THE DAEMON DID NOT RELEASE ON A REJECT. The §2A "
                    f"{EVENT_REJECT} for {REJECT_CID!r} was DRAINED BY THE LOOP "
                    f"(consumed={completions.get('consumed')}) and recorded "
                    f"{completions.get('last_disposition')!r} with "
                    f"rejects_dispatched={completions.get('rejects_dispatched')} "
                    f"— reason {completions.get('last_reason')!r}. Committed is "
                    f"still {after.get('committed')} and the reservation for "
                    f"{REJECT_CID!r} is still TAKEN: §3 releases on reject, and a "
                    "venue refusal that leaks its reservation inflates §11.3's Σ "
                    "against every capital rule that reads it"
                ),
            )
        )
        return findings
    seen["reject_released"] = released
    if completions.get("last_disposition") != "dispatched":
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"the daemon consumed a §2A {EVENT_REJECT} and recorded "
                    f"{completions.get('last_disposition')!r}, not 'dispatched' — "
                    f"reason {completions.get('last_reason')!r}"
                ),
            )
        )
    if released != EXPECT_REJECT_COMMITTED:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the daemon dispatched a §2A {EVENT_REJECT} for "
                    f"{REJECT_CID!r} and committed moved by {released} — expected "
                    f"{EXPECT_REJECT_COMMITTED} released. §3 releases the "
                    "reservation on reject and nothing was ever working against "
                    "it, so a reject that releases nothing is a leak"
                ),
            )
        )
    # §7.12 guard 1, and the shape of the assertion is the whole point: a reject
    # counted as a cancel would satisfy every assertion above that reads
    # `dispatched` alone. What must hold is that pushing a REJECT moved the
    # reject counter and left the CANCEL counter where it was — not that the two
    # numbers differ, which they need not (one cancel and one reject are both
    # legitimately 1).
    cancels_before = (before.get("completions") or {}).get("cancels_dispatched")
    if completions.get("cancels_dispatched") != cancels_before:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"pushing a §2A {EVENT_REJECT} moved cancels_dispatched "
                    f"{cancels_before} -> {completions.get('cancels_dispatched')}. "
                    "The daemon counted a reject as a cancel, so this build "
                    "cannot name the path it dispatched and the release above is "
                    "attributed to the wrong §3 terminal path"
                ),
            )
        )
    # §4:214 — the identical exec report a second time is ONE release.
    drive.push(
        "reject-again",
        event=EVENT_REJECT,
        client_order_id=REJECT_CID,
        exec_id=REJECT_EXEC,
        done_qty=0,
    )
    again = drive.watch(
        lambda st: (
            (st.get("completions") or {}).get("duplicates", 0)
            > (completions.get("duplicates") or 0)
        ),
        "the daemon to refuse the re-delivered reject as a §4:214 duplicate",
    )
    replayed = (again.get("completions") or {}).get("rejects_dispatched")
    seen["reject_dispatched_after_replay"] = replayed
    if replayed != seen["reject_dispatched"]:
        findings.append(
            (
                COMPLETIONS_FILE,
                (
                    f"re-delivering the identical §2A {EVENT_REJECT} moved "
                    f"rejects_dispatched {seen['reject_dispatched']} -> "
                    f"{replayed}. §4:214 deduplicates by (order_id, exec_id) and "
                    "a second dispatch is the double release §14 forbids"
                ),
            )
        )
    return findings


def _arm_pending_timeout(drive: Drive, seen: dict[str, Any]) -> list[tuple[str, str]]:
    """ARC 053. §4's pending-timeout resolution, DRIVEN — and it never resends.

    Two orders, because one could only ever prove one half:

    * `TIMEOUT_DEAD_CID` — the venue answers `cancelled`. The reservation must
      be RELEASED, by a QUERY, without any exec report ever arriving.
    * `TIMEOUT_HELD_CID` — the venue answers `indeterminate`. The reservation
      must be HELD, and must STILL be held after `FURTHER_QUERIES` more queries.
      That second half is where §4's rule bites: a resend is far likelier on a
      retry than on the first look, and `committed` is the number that would
      move if one happened — a second live order needs a second reservation.

    THE ARM IS DRIVEN AND THE CENSUS BESIDE IT IS STRUCTURAL, and both are
    required. Driving proves the daemon did not resend THIS TIME; the census
    proves it holds no verb that could.
    """
    findings: list[tuple[str, str]] = []
    boot = drive.cmd("status")
    timeouts = boot.get("timeouts")
    if timeouts is None:
        raise Cannot(
            f"{LIMITERD_FILE}: this build's status reply carries no `timeouts` "
            "block — the daemon holds no §4 pending-timeout poller, so there is "
            "no subject. A build that does not poll is not a build that polled "
            "and found nothing due (check contract rule 10)"
        )
    ack_s = float(timeouts.get("pending_ack_timeout_s") or 0.0)
    if ack_s <= 0.0:
        raise Cannot(
            f"{LIMITERD_FILE}: the daemon reports pending_ack_timeout_s="
            f"{timeouts.get('pending_ack_timeout_s')!r}; §12A:830's deadline is "
            "what makes an order overdue and without it nothing is ever due"
        )
    seen["timeout_ack_s"] = ack_s

    # -- the venue's answers, written BEFORE the reservations exist so the
    #    first query already has something to read.
    drive.answer(TIMEOUT_DEAD_CID, STATE_DEAD, terminal=True)
    drive.answer(TIMEOUT_HELD_CID, STATE_UNRESOLVABLE)
    dead = drive.reserve(TIMEOUT_DEAD_CID, TIMEOUT_QTY, TIMEOUT_MARGIN_PER_CONTRACT)
    held = drive.reserve(TIMEOUT_HELD_CID, TIMEOUT_QTY, TIMEOUT_MARGIN_PER_CONTRACT)
    if not (dead.get("accepted") and held.get("accepted")):
        raise Cannot(
            "the daemon refused a pending-timeout reservation: "
            f"{dead.get('reason')!r} / {held.get('reason')!r}"
        )
    taken = drive.cmd("status")
    seen["timeout_committed_after_take"] = taken.get("committed")
    resolved_before = (taken.get("timeouts") or {}).get("resolved", 0)
    completions_before = (taken.get("completions") or {}).get("seen", 0)

    # -- the DEAD order must release, and it must release BY QUERY ------------
    # `settle`, not `watch`: a build whose poll never runs leaves an order past
    # its deadline that nothing ever asks about — a ZOMBIE — and that is the
    # defect this arm exists to name. A timeout would report it as *the gate got
    # bored*, which is the same reading as a slow machine.
    after = drive.settle(
        lambda st: (st.get("timeouts") or {}).get("resolved", 0) > resolved_before,
        WATCH_HORIZON_S,
    )
    poll = after.get("timeouts") or {}
    if (poll.get("resolved") or 0) <= resolved_before:
        overdue = float(taken.get("committed") or 0.0)
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"ZOMBIE ORDER: {TIMEOUT_DEAD_CID!r} is past §12A:830's "
                    f"{ack_s}s ack deadline, the venue's answer {STATE_DEAD!r} has "
                    f"been on disk for the whole window, and after "
                    f"{WATCH_HORIZON_S}s the daemon reports polls="
                    f"{poll.get('polls')!r} queries="
                    f"{(poll.get('query') or {}).get('queries')!r} resolved="
                    f"{poll.get('resolved')!r}. NOTHING POLLED IT. The order hangs "
                    f"indefinitely and its reservation LEAKS — committed is still "
                    f"{overdue} with outstanding={after.get('outstanding')!r}. §4 "
                    "resolves a pending timeout by querying; a daemon that never "
                    "asks holds capital against an order it has forgotten"
                ),
            )
        )
        return findings
    query = poll.get("query") or {}
    seen["timeout_poll"] = poll
    if not query.get("queries"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "the poll reported a resolution with queries="
                    f"{query.get('queries')!r} — §4 resolves a pending timeout "
                    "BY QUERYING, and a release with no query behind it did not "
                    "come from the venue"
                ),
            )
        )
    if (query.get("answers") or {}).get(STATE_DEAD, 0) < 1:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the venue answered {query.get('answers')!r}; the arm wrote "
                    f"{STATE_DEAD!r} for {TIMEOUT_DEAD_CID!r} and the poll never "
                    "read it, so the release above was not this answer's"
                ),
            )
        )
    if (after.get("completions") or {}).get("seen", 0) != completions_before:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "a completion arrived during the pending-timeout arm "
                    f"(seen {completions_before} -> "
                    f"{(after.get('completions') or {}).get('seen')}). The release "
                    "measured here must be the POLL's, and a push event in the "
                    "same window makes that unprovable"
                ),
            )
        )

    return findings + _timeout_hold_findings(drive, seen, after, resolved_before)


def _timeout_hold_findings(  # pylint: disable=too-many-locals
    drive: Drive,
    seen: dict[str, Any],
    after: dict[str, Any],
    resolved_before: int,
) -> list[tuple[str, str]]:
    """The HOLD half of §4's pending-timeout arm — and the no-resend proof.

    Split from the release half because the two ask different questions of the
    same poll: the release half asks *did a query resolve a dead order*, and this
    one asks *does an UNRESOLVABLE answer leave everything exactly where it was,
    across many further queries*. The second is where §4's rule actually bites.
    """
    findings: list[tuple[str, str]] = []
    poll = after.get("timeouts") or {}
    query = poll.get("query") or {}
    committed_at_hold = after.get("committed")
    outstanding_at_hold = after.get("outstanding")
    queries_at_hold = query.get("queries", 0)
    seen["timeout_committed_at_hold"] = committed_at_hold
    later = drive.watch(
        lambda st: (
            ((st.get("timeouts") or {}).get("query") or {}).get("queries", 0)
            >= queries_at_hold + FURTHER_QUERIES
        ),
        f"{FURTHER_QUERIES} further §4 status queries",
    )
    later_poll = later.get("timeouts") or {}
    later_query = later_poll.get("query") or {}
    seen["timeout_queries_total"] = later_query.get("queries")
    seen["timeout_answers"] = later_query.get("answers")
    if (later_query.get("answers") or {}).get(STATE_UNRESOLVABLE, 0) < 1:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the poll never read the {STATE_UNRESOLVABLE!r} answer "
                    f"written for {TIMEOUT_HELD_CID!r}; answers="
                    f"{later_query.get('answers')!r}. The hold below would then "
                    "be a hold over an order nobody asked about"
                ),
            )
        )
    if later.get("outstanding") != outstanding_at_hold:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"an {STATE_UNRESOLVABLE!r} order changed the outstanding "
                    f"count {outstanding_at_hold} -> {later.get('outstanding')} "
                    f"across {FURTHER_QUERIES} further queries. §4 resolves an "
                    "unresolvable answer by HOLDING toward flat (§14): nothing "
                    "terminal has happened, so nothing may be released — and "
                    "nothing may be placed"
                ),
            )
        )
    if later.get("committed") != committed_at_hold:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"*** §4 NO-RESEND: committed moved {committed_at_hold} -> "
                    f"{later.get('committed')} across {FURTHER_QUERIES} further "
                    "status queries with no exec report. A poll that RESENDS "
                    "takes a second reservation for a second live order at the "
                    "venue while the first is still working — the double fill §4 "
                    "forbids outright. §4 resolves by QUERYING, never by "
                    "resending ***"
                ),
            )
        )
    if later_poll.get("resends") != 0:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"*** §4 NO-RESEND: the daemon reports resends="
                    f"{later_poll.get('resends')!r} over "
                    f"{later_poll.get('polls')!r} polls. §4:240-241 forbids the "
                    "auto-resend outright ***"
                ),
            )
        )
    # -- AND THE HOLD IS NOT A DEAD END --------------------------------------
    # The unresolvable order is now answered `cancelled`, and it must release.
    # Two reasons, and the second is why this is not tidy-up: a HOLD that could
    # never be resolved would be indistinguishable from a leak, so the arm has to
    # show the reservation was recoverable; and leaving it outstanding at exit
    # would force `_arm_stop_record`'s leak detector to accept a non-zero
    # `outstanding`, which is the one number in this gate that must stay exact.
    drive.answer(TIMEOUT_HELD_CID, STATE_DEAD, terminal=True)
    freed = drive.watch(
        lambda st: (
            (st.get("timeouts") or {}).get("resolved", 0)
            > (later_poll.get("resolved") or 0)
        ),
        "the held order to release once the venue finally answers",
    )
    seen["timeout_resolved_total"] = (freed.get("timeouts") or {}).get("resolved")
    seen["timeout_outstanding_after"] = freed.get("outstanding")
    if freed.get("committed") != 0.0:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"both pending-timeout orders were answered {STATE_DEAD!r} and "
                    f"committed is {freed.get('committed')!r}, not 0.0 — a held "
                    "reservation that cannot be released once the venue answers "
                    "is a leak wearing §4's hold"
                ),
            )
        )
    later_poll = freed.get("timeouts") or later_poll
    # Idempotence: each order resolved once and only once, across every one
    # of those further sweeps.
    if later_poll.get("resolved") != resolved_before + 2:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the poll resolved {later_poll.get('resolved')} order(s); "
                    f"expected {resolved_before + 2}. A released reservation "
                    "leaves the outstanding set, so a re-queried order that "
                    "resolves twice is the double release §14 forbids"
                ),
            )
        )
    return findings


#: The seam file whose roster names every verb that can reach the venue. READ,
#: never restated: `broker_seam.ORDER_PORT_VERBS` is *"the authority, not the
#: docstrings"* by its own comment, and a ban list this gate spelled itself would
#: go stale the day the seam gained a verb.
BROKER_SEAM_FILE = "scripts/broker/broker_seam.py"
ORDER_PORT_ROSTER = "ORDER_PORT_VERBS"
#: The ONE verb on that roster the poll path is allowed to reach.
POLL_ALLOWED_VERB = "query_order_status"
#: Where the poll path starts. QUALIFIED, because `before` is NOT a unique name
#: in `limiterd.py` — `Plane1Booker` has one too, and a bare-name index resolves
#: it to whichever the AST walk reached first, which walked the WAL-booking path
#: instead of the poll's. Both entries are named: `before` is what the loop
#: actually calls and `poll_due` is where the work is.
POLL_ENTRIES: tuple[str, ...] = (
    "PendingTimeoutPoller.poll_due",
    "PendingTimeoutPoller.before",
)
#: Modules the closure may cross. The poll path is `limiterd.py` ->
#: `outcomes.py` and nothing else; a call that leaves them is UNRESOLVED and is
#: reported as such rather than assumed harmless.
POLL_MODULES: tuple[str, ...] = (LIMITERD_FILE, "scripts/nixrisk/outcomes.py")


def _placement_verbs(home: Path) -> tuple[frozenset[str], str]:
    """Every venue-reaching verb EXCEPT the status query, read off the seam."""
    try:
        tree = ast.parse((home / BROKER_SEAM_FILE).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError) as exc:
        return frozenset(), f"{BROKER_SEAM_FILE} would not parse: {exc!r}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) and not isinstance(node, ast.Assign):
            continue
        targets: list[ast.expr] = (
            [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
        )
        if not any(
            isinstance(t, ast.Name) and t.id == ORDER_PORT_ROSTER for t in targets
        ):
            continue
        value = node.value
        if not isinstance(value, ast.Tuple):
            return frozenset(), (
                f"{BROKER_SEAM_FILE}:{ORDER_PORT_ROSTER} is not a literal tuple"
            )
        verbs = {
            elt.value
            for elt in value.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        if POLL_ALLOWED_VERB not in verbs:
            return frozenset(), (
                f"{BROKER_SEAM_FILE}:{ORDER_PORT_ROSTER} does not contain "
                f"{POLL_ALLOWED_VERB!r} — this gate is reading the wrong roster"
            )
        return frozenset(verbs) - {POLL_ALLOWED_VERB}, ""
    return frozenset(), f"{BROKER_SEAM_FILE} declares no {ORDER_PORT_ROSTER}"


def _functions(home: Path) -> tuple[dict[str, ast.FunctionDef], str]:
    """`Class.name` AND bare `name` -> FunctionDef, over the poll's modules.

    Both keyings, deliberately, and the pair is what makes the walk both aimed
    and conservative. The ENTRY POINTS are looked up qualified, so the closure
    starts in the right class; the CALL SITES are resolved bare, because
    `self._outcomes.resolve_pending_timeouts(...)` gives an attribute name and
    no class. Bare resolution OVER-APPROXIMATES — a name shared by two classes
    pulls both bodies in — and that is the safe direction for a ban check: it
    can only make the closure larger, so a verb absent from it is absent from
    every reading of it. An under-approximation would be the dangerous error and
    is what a first-wins bare index quietly produced.
    """
    found: dict[str, ast.FunctionDef] = {}
    for rel in POLL_MODULES:
        try:
            tree = ast.parse((home / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError) as exc:
            return {}, f"{rel} would not parse: {exc!r}"
        _index_module(tree, found)
    return found, ""


def _index_module(tree: ast.AST, found: dict[str, ast.FunctionDef]) -> None:
    """Fold ONE module into the index, qualified names first then bare ones."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                found[f"{node.name}.{item.name}"] = item
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            found.setdefault(node.name, node)


def _called_names(fn: ast.FunctionDef) -> set[str]:
    """Every name this function CALLS. `self.x()` and `x()` both count."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _poll_closure(
    functions: dict[str, ast.FunctionDef],
) -> tuple[set[str], set[str]]:
    """`(reachable, called)` from the poll's entry points, transitively.

    A bare call name may denote SEVERAL bodies (`before` is two in this tree).
    Every one is followed — see `_functions` on why over-approximating is the
    safe direction for a ban check.
    """
    bodies: dict[str, list[ast.FunctionDef]] = {}
    for key, fn in functions.items():
        bodies.setdefault(key.rsplit(".", 1)[-1], []).append(fn)
    reachable: set[str] = set()
    calls: set[str] = set()
    queue = [name for name in POLL_ENTRIES if name in functions]
    while queue:
        name = queue.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for fn in bodies.get(name.rsplit(".", 1)[-1], []):
            for called in _called_names(fn):
                calls.add(called)
                if called in functions and called not in reachable:
                    queue.append(called)
    return reachable, calls


def _arm_no_resend_census(
    home: Path, seen: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[str]]:
    """ARC 053. §4's no-resend rule, proven STRUCTURALLY as well as by driving.

    THE SHARPEST ASSERTION IN THIS ARC, and it is a reachability census rather
    than a grep. Starting at `PendingTimeoutPoller.poll_due`, every function the
    poll path can reach is collected transitively across `limiterd.py` and
    `outcomes.py`, and every name any of them CALLS is compared against the
    venue-reaching roster the broker seam declares. A resend is not merely absent
    from this path: it is UNREACHABLE from it.

    Driving alone could not settle this. A driven arm proves the daemon did not
    resend on the run the gate watched; it cannot prove there is no input that
    would make it. The census cannot prove the daemon runs at all — which is why
    both exist and why the driven arm runs first.

    NON-VACUITY, and it matters more here than anywhere else in the file: a
    closure that resolved nothing would contain no banned verb and would pass
    while measuring nothing. So the census REQUIRES its own reach — the closure
    must contain the poll's own work (`resolve_pending_timeouts`) and the one
    verb it is allowed (`query_order_status`) — before any absence is credited.
    """
    findings: list[tuple[str, str]] = []
    banned, complaint = _placement_verbs(home)
    if complaint:
        return findings, [f"the venue-verb roster could not be derived: {complaint}"]
    functions, complaint = _functions(home)
    if complaint:
        return findings, [f"the poll path could not be parsed: {complaint}"]

    if not any(name in functions for name in POLL_ENTRIES):
        no_entry = (
            f"{LIMITERD_FILE} defines none of {list(POLL_ENTRIES)} — the poll "
            "path has no entry point, so there is nothing to walk"
        )
        return findings, [no_entry]
    reachable, calls = _poll_closure(functions)

    seen["poll_closure"] = sorted(reachable)
    seen["poll_calls"] = len(calls)
    seen["banned_verbs"] = sorted(banned)

    # -- NON-VACUITY BEFORE THE ABSENCE ---------------------------------------
    unclassifiable: list[str] = []
    if "resolve_pending_timeouts" not in calls:
        unclassifiable.append(
            f"the closure from {list(POLL_ENTRIES)} does not reach "
            "`resolve_pending_timeouts` — the walk did not find the poll's own "
            "work, so an absence of placement verbs in it proves nothing"
        )
    if POLL_ALLOWED_VERB not in calls:
        unclassifiable.append(
            f"the closure from {list(POLL_ENTRIES)} does not reach "
            f"{POLL_ALLOWED_VERB!r} — §4 resolves a pending timeout BY QUERYING "
            "and this walk cannot see the query, so it cannot see a resend either"
        )

    # -- THE PROPERTY ----------------------------------------------------------
    reached = sorted(calls & banned)
    if reached:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"*** §4 NO-RESEND VIOLATION: the pending-timeout poll path "
                    f"REACHES venue-placement verb(s) {reached} "
                    f"(closure: {sorted(reachable)}). §4 resolves a pending "
                    "timeout by `query_order_status` and NEVER by an auto-resend; "
                    "a poll that can place puts a SECOND LIVE ORDER at the venue "
                    "while the first is still working, and §3 holds one "
                    "reservation for both ***"
                ),
            )
        )
    return findings, unclassifiable


# ==========================================================================
# ARC 054 — THE ONSET ARM. §3:172-174, DRIVEN THROUGH THE LOOP'S OWN DETECTION.
#
# The subject is the DAEMON'S DISPATCH, not I11's selection. `check_flatten`
# ARM 3b already owns the selection (ARC 045) and doctrine C.9 forbids a second
# instrument over a subject the suite already drives, so nothing below re-tests
# which orders `_classify_for_onset` admits. What is tested here is the three
# things only a running process can be wrong about:
#
#   1. that an onset transition reaching this process SWEEPS AT ALL, driven via
#      the loop's own edge detection and never by a direct call from the gate;
#   2. that the enumeration it sweeps over is COMPLETE — measured against the
#      set of orders THIS GATE reserved and never saw resolved, which is an
#      order-state truth independent of `pending_entries()` itself, plus Σ over
#      the TAKEN set as the money-record backstop;
#   3. that it is SELECTIVE — every armed protective stop is at the same level
#      after the sweep as before it, on BOTH onset types. This is the half whose
#      violation looks like nothing happening, which is why it is measured on
#      both sides of the call rather than inferred from an absence.
# ==========================================================================


def _onset_pending(status: dict[str, Any]) -> set[str]:
    """The client_order_ids the daemon's own enumeration currently holds."""
    block = status.get("pending_entries") or {}
    return {
        str(row.get("client_order_id"))
        for row in (block.get("entries") or [])
        if row.get("client_order_id")
    }


def _onset_stops(status: dict[str, Any]) -> dict[str, float]:
    """Every armed protective stop, by the order it protects, with its level."""
    fills = status.get("fills") or {}
    return {
        str(stop.get("client_order_id")): stop.get("level")
        for stop in (fills.get("stops") or [])
    }


def _onset_open_rows(status: dict[str, Any]) -> dict[str, str]:
    """`client_order_id -> trade_id` for every OPEN §3 position row.

    Joined through the stop book rather than guessed: a stop is keyed by the
    entry order it protects, and a position row carries the trade. Naming the
    POSITION an unprotected stop belongs to is what makes PLANT C's finding
    actionable instead of merely alarming.
    """
    fills = status.get("fills") or {}
    return {
        str(row.get("trade_id")): str(row.get("symbol"))
        for row in (fills.get("positions") or [])
        if row.get("state") == "open"
    }


def _onset_sweeps(status: dict[str, Any], cause: str) -> list[dict[str, Any]]:
    """Every sweep the daemon booked under `cause`, in order."""
    onset = status.get("onset") or {}
    return [row for row in (onset.get("sweeps") or []) if row.get("cause") == cause]


def _onset_bucketed(sweep: dict[str, Any]) -> set[str]:
    """Every id the sweep ACCOUNTED FOR — cancelled or in a named exclusion."""
    ids = set(sweep.get("cancelled") or [])
    for bucket in ("protected", "out_of_scope", "unclassified", "failures"):
        ids |= {str(pair[0]) for pair in (sweep.get(bucket) or []) if pair}
    return ids


# too-many-locals: the staging function resolves ONE named thing per way this
# arm could look healthy while measuring nothing — the pre-onset status, the
# stop book, the open rows, the committed figure before and after, the expected
# figure, the order state and the enumeration. Check contract rule 11 makes the
# REASON the assertion, so each has to survive to be named in one.
def _onset_stage(  # pylint: disable=too-many-locals
    drive: Drive, seen: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[str], dict[str, Any]]:
    """Stage the book and prove it is real. Returns `(findings, blind, state)`.

    Split out of `_arm_onset` so the arm that JUDGES a sweep reads apart from
    the arm that BUILDS one to judge — the same split `_fill_non_vacuity`
    makes, and for the same reason: every condition here is a way the onset
    arm could look healthy while measuring nothing (§7.12 #8).
    """
    findings: list[tuple[str, str]] = []
    unclassifiable: list[str] = []

    # -- NON-VACUITY 1: a REAL protective subject must already exist. ---------
    # "Exits untouched" measured against an empty stop book is a sentence about
    # nothing. If nothing is armed, the SELECTIVE half is UNMEASURED and says so
    # (check contract rule 10) — it is never quietly passed.
    before_stage = drive.cmd("status")
    state: dict[str, Any] = {}
    state["stops_before"] = _onset_stops(before_stage)
    state["open_rows"] = _onset_open_rows(before_stage)
    if not state["stops_before"]:
        unclassifiable.append(
            f"{LIMITERD_FILE}: no protective stop is armed at onset time, so "
            "§3:173's *exits untouched* half had NO subject to be measured "
            "against — the sweep's selectivity is UNMEASURED in this run, not "
            "proven (WIRED_EVENTS=" + f"{list(WIRED)})"
        )

    # -- STAGE: pending entries across TWO symbols and TWO strategies. --------
    drive.cmd("register", strategy_id=ONSET_STRATEGY_B)
    committed_before = before_stage.get("committed")
    for coid in ONSET_IN_SCOPE:
        drive.reserve(
            coid,
            ONSET_QTY,
            ONSET_MARGIN_PER_CONTRACT,
            symbol=ONSET_BLACKOUT_SYMBOL,
        )
    for coid in ONSET_OUT_OF_SCOPE:
        drive.cmd(
            "reserve",
            strategy_id=ONSET_STRATEGY_B,
            client_order_id=coid,
            symbol=ONSET_OTHER_SYMBOL,
            side="long",
            qty=ONSET_QTY,
            margin_per_contract=ONSET_MARGIN_PER_CONTRACT,
            stop_ticks=8,
            stop_mode="fixed",
            signal_ts=_fresh_signal_ts(),
        )
    staged = state["staged"] = drive.cmd("status")
    seen["onset_committed_after_take"] = staged.get("committed")
    # -- NON-VACUITY 2: the entries are GENUINELY PENDING, by the MONEY record
    # and not by the enumeration this arm is about to test. Σ over the TAKEN set
    # is the ledger's, and it is what makes a later "swept" mean something.
    expect_taken = round(
        float(committed_before or 0.0) + ONSET_RESERVATIONS * EXPECT_ONSET_EACH, 6
    )
    if round(float(staged.get("committed") or 0.0), 6) != expect_taken:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: staging {ONSET_RESERVATIONS} pending entries at "
                    f"{EXPECT_ONSET_EACH} each moved committed "
                    f"{committed_before} -> {staged.get('committed')}, not to "
                    f"{expect_taken} — nothing about a sweep can be measured "
                    "against a book this arm did not actually fill"
                ),
            )
        )
        return findings, unclassifiable, state
    order_state = set(ONSET_IN_SCOPE) | set(ONSET_OUT_OF_SCOPE)
    enumerated = _onset_pending(staged)
    seen["onset_order_state"] = sorted(order_state)
    seen["onset_enumerated"] = sorted(enumerated)
    # -- COMPLETENESS, FIRST HALF: what the daemon's own enumeration holds must
    # contain every order this gate reserved and never saw resolved. Measured
    # BEFORE any onset, so an incomplete producer is named as such rather than
    # discovered later as a survivor whose cause is ambiguous.
    missing = sorted(order_state - enumerated)
    if missing:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"INCOMPLETE ENUMERATION: {missing} hold OUTSTANDING §3 "
                    f"reservations in this process (committed {staged.get('committed')} "
                    f"over {staged.get('outstanding')} taken) and `pending_entries()` "
                    f"does not list them — it returned {sorted(enumerated)}. §3:173's "
                    "sweep iterates exactly this enumeration, so an order missing from "
                    "it is an order the sweep will NEVER cancel and that can still fill "
                    "inside a window it was not approved for (§3:174)"
                ),
            )
        )
        return findings, unclassifiable, state
    return findings, unclassifiable, state


# too-many-locals: the same argument as `_onset_stage` — the sweep, the status
# before and after, the survivor sets in both directions, the expected release
# figure and the two poll counts that decide edge-vs-level. Each is one
# separately-reported finding.
def _onset_blackout(  # pylint: disable=too-many-locals
    drive: Drive, seen: dict[str, Any], state: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[str]]:
    """The PER-SYMBOL half: declare, watch, judge, and prove it is edge-driven."""
    findings: list[tuple[str, str]] = []
    unclassifiable: list[str] = []
    staged = state["staged"]
    open_rows = state["open_rows"]
    order_state = set(ONSET_IN_SCOPE) | set(ONSET_OUT_OF_SCOPE)
    # ================= BLACKOUT ONSET — PER-SYMBOL =========================
    # DECLARED FROM OUTSIDE THE PROCESS, into the surface the loop reads on its
    # own tick. The gate never calls the sweep: that would prove the library,
    # which ARC 045 already proved, and not the daemon, which is the whole gap.
    drive.declare_onset(blackout=[ONSET_BLACKOUT_SYMBOL])
    try:
        drive.watch(
            lambda s: ((s.get("onset") or {}).get("blackout_onsets") or 0) > 0,
            f"the daemon to detect the {ONSET_BLACKOUT_SYMBOL} blackout onset",
        )
    except _Missed as miss:
        onset = miss.status.get("onset")
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NO SWEEP. A blackout onset for {ONSET_BLACKOUT_SYMBOL} was "
                    f"declared at {drive.dir / ONSET_DIR / ONSET_STATE_NAME} and the "
                    f"daemon never dispatched one within {WATCH_HORIZON_S}s "
                    f"(onset block: {json.dumps(onset)[:400]}). "
                    f"{sorted(order_state)} are still PENDING with "
                    f"{miss.status.get('committed')} committed against them, and "
                    f"{list(ONSET_IN_SCOPE)} are working inside the "
                    f"{ONSET_BLACKOUT_SYMBOL} window they were never approved for "
                    "(§3:172-174, §15 C4)"
                ),
            )
        )
        return findings, unclassifiable
    # Watch PAST the tick: a sweep that lands a tick later is still a sweep, and
    # the state this arm judges is the settled one.
    time.sleep(EDGE_SETTLE_S)
    after_blackout = drive.cmd("status")
    sweeps = _onset_sweeps(after_blackout, CAUSE_BLACKOUT)
    if not sweeps:
        unswept = sorted(_onset_pending(after_blackout) & set(ONSET_IN_SCOPE))
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NO SWEEP. The daemon COUNTED a {ONSET_BLACKOUT_SYMBOL} blackout "
                    f"onset and booked no sweep under {CAUSE_BLACKOUT!r}: "
                    f"{json.dumps(after_blackout.get('onset'))[:300]}. "
                    f"{unswept} are still pending ENTRY orders with "
                    f"{after_blackout.get('committed')} committed over "
                    f"{after_blackout.get('outstanding')} TAKEN reservation(s), and "
                    f"they are WORKING inside the {ONSET_BLACKOUT_SYMBOL} blackout "
                    "window they were never approved for — §3:172-174, §15 C4. A "
                    "counter that advanced while nothing was cancelled is the worst "
                    "of the three: it reads, to anything downstream, like a sweep"
                ),
            )
        )
        return findings, unclassifiable
    sweep = sweeps[-1]
    seen["onset_blackout_sweep"] = sweep
    findings += _onset_judge_sweep(
        sweep,
        cause=CAUSE_BLACKOUT,
        expect_scope=ONSET_BLACKOUT_SYMBOL,
        must_cancel=set(ONSET_IN_SCOPE),
        must_not_cancel=set(ONSET_OUT_OF_SCOPE),
        open_rows=open_rows,
    )
    # SCOPE, read off the daemon's own enumeration rather than off the sweep's
    # report: the other symbol's entries must still be PENDING afterwards.
    survivors = _onset_pending(after_blackout)
    still_in_scope = sorted(set(ONSET_IN_SCOPE) & survivors)
    if still_in_scope:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"SURVIVED THE SWEEP: {still_in_scope} are still pending ENTRY "
                    f"orders after the {ONSET_BLACKOUT_SYMBOL} blackout onset "
                    f"(committed {after_blackout.get('committed')}). §3:172 cancels "
                    "ALL pending entries on onset; a survivor can fill inside the "
                    f"{ONSET_BLACKOUT_SYMBOL} window it was not approved for (§3:174)"
                ),
            )
        )
    dropped_out_of_scope = sorted(set(ONSET_OUT_OF_SCOPE) - survivors)
    if dropped_out_of_scope:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"OVER-BROAD SCOPE: {dropped_out_of_scope} are "
                    f"{ONSET_OTHER_SYMBOL} entries and a {ONSET_BLACKOUT_SYMBOL} "
                    "blackout cancelled them. §6.1's windows are PER-SYMBOL off the "
                    "live calendar, so this cancelled gate-approved orders in a "
                    "symbol that is not in any window"
                ),
            )
        )
    # THE 044 RELEASE, as the money record moved it.
    expect_after = round(
        float(staged.get("committed") or 0.0) - len(ONSET_IN_SCOPE) * EXPECT_ONSET_EACH,
        6,
    )
    seen["onset_committed_after_blackout"] = after_blackout.get("committed")
    if round(float(after_blackout.get("committed") or 0.0), 6) != expect_after:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the blackout onset moved committed {staged.get('committed')} -> "
                    f"{after_blackout.get('committed')}, not to {expect_after}. §3:150-152 "
                    "releases each cancelled entry's reservation under the onset's OWN "
                    "cause (SPEC-A7); the sweep reported released="
                    f"{sweep.get('released')}"
                ),
            )
        )
    if findings:
        return findings, unclassifiable

    # -- EDGE-TRIGGERED: further ticks inside the SAME declared blackout. -----
    polls_before = (after_blackout.get("onset") or {}).get("polls")
    time.sleep(EDGE_SETTLE_S)
    settled = drive.cmd("status")
    polls_after = (settled.get("onset") or {}).get("polls")
    seen["onset_edge"] = {
        "polls_before": polls_before,
        "polls_after": polls_after,
        "blackout_onsets": (settled.get("onset") or {}).get("blackout_onsets"),
        "sweeps": len((settled.get("onset") or {}).get("sweeps") or []),
    }
    if (polls_after or 0) <= (polls_before or 0):
        unclassifiable.append(
            f"{LIMITERD_FILE}: the onset poll did not advance past "
            f"{polls_before} while the blackout stayed declared, so whether the "
            "sweep is EDGE-triggered or level-triggered was not measured"
        )
    elif len(_onset_sweeps(settled, CAUSE_BLACKOUT)) != len(sweeps):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NOT EDGE-TRIGGERED: the {ONSET_BLACKOUT_SYMBOL} blackout stayed "
                    f"declared and unchanged across {polls_after} polls and the daemon "
                    f"booked {len(_onset_sweeps(settled, CAUSE_BLACKOUT))} sweeps where "
                    f"{len(sweeps)} was the onset. §3:172's onset is the ENTRY into the "
                    "window, not the window; a sweep on every tick re-enters §11.3's "
                    "ledger and §9's WAL once per tick for a transition that happened once"
                ),
            )
        )

    return findings, unclassifiable


# too-many-locals: the same argument as `_onset_stage` and `_onset_blackout` —
# the sweep, the settled status, the residue, the stop book on both sides and
# the two exclusion sets. Each is one separately-reported finding, and merging
# any pair would merge two defects into one sentence naming neither.
def _onset_halt(  # pylint: disable=too-many-locals
    drive: Drive, seen: dict[str, Any], state: dict[str, Any]
) -> list[tuple[str, str]]:
    """The GLOBAL half, plus the absence proof and the selectivity assertion."""
    findings: list[tuple[str, str]] = []
    unclassifiable: list[str] = []
    open_rows = state["open_rows"]
    stops_before = state["stops_before"]
    # ================= HALT ONSET — GLOBAL ==================================
    drive.declare_onset(halt=True, blackout=[ONSET_BLACKOUT_SYMBOL])
    try:
        drive.watch(
            lambda s: ((s.get("onset") or {}).get("halt_onsets") or 0) > 0,
            "the daemon to detect the global HALT onset",
        )
    except _Missed as miss:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "NO SWEEP ON HALT. A global HALT onset was declared and the daemon "
                    f"never dispatched one within {WATCH_HORIZON_S}s (onset block: "
                    f"{json.dumps(miss.status.get('onset'))[:400]}). "
                    f"{sorted(set(ONSET_OUT_OF_SCOPE))} are still PENDING with "
                    f"{miss.status.get('committed')} committed against them, inside a "
                    "HALT that stops every strategy and every symbol (§12.5, §3:172)"
                ),
            )
        )
        return findings
    time.sleep(EDGE_SETTLE_S)
    after_halt = drive.cmd("status")
    halt_sweeps = _onset_sweeps(after_halt, CAUSE_HALT)
    if not halt_sweeps:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "the daemon counted a HALT onset but booked NO sweep under "
                    f"{CAUSE_HALT!r}: {json.dumps(after_halt.get('onset'))[:400]}"
                ),
            )
        )
        return findings
    halt_sweep = halt_sweeps[-1]
    seen["onset_halt_sweep"] = halt_sweep
    findings += _onset_judge_sweep(
        halt_sweep,
        cause=CAUSE_HALT,
        expect_scope=None,
        must_cancel=set(ONSET_OUT_OF_SCOPE),
        must_not_cancel=set(),
        open_rows=open_rows,
    )
    # -- COMPLETENESS, THE ABSENCE PROOF. A GLOBAL onset leaves NOTHING pending:
    # Σ over the TAKEN set is the ledger's own number and is derived from a
    # record `pending_entries()` cannot edit, so a residue here is exactly an
    # entry the enumeration never handed over. This is the one assertion that
    # catches an incomplete producer whose omission the enumeration also hides.
    seen["onset_committed_after_halt"] = after_halt.get("committed")
    seen["onset_outstanding_after_halt"] = after_halt.get("outstanding")
    residue = _onset_pending(after_halt)
    if round(float(after_halt.get("committed") or 0.0), 6) != 0.0 or residue:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"INCOMPLETE SWEEP ON GLOBAL HALT: committed "
                    f"{after_halt.get('committed')} over "
                    f"{after_halt.get('outstanding')} TAKEN reservation(s) survive a "
                    f"HALT onset, and the enumeration still lists {sorted(residue)}. "
                    "§12.5's HALT is global and §3:172 cancels ALL pending entries on "
                    "onset, so every one of these is a gate-approved order still "
                    "working inside a state no order may fill in (§3:174). Σ over the "
                    "TAKEN set is the LEDGER's number, not the enumeration's — a "
                    "residue here is an entry `pending_entries()` never handed over"
                ),
            )
        )

    # -- SELECTIVE, ACROSS BOTH ONSETS. The stop book must be byte-for-byte the
    # same object it was before any of this: same orders, same levels.
    stops_after = _onset_stops(after_halt)
    seen["onset_stops_before"] = stops_before
    seen["onset_stops_after"] = stops_after
    if stops_before and stops_after != stops_before:
        lost = sorted(set(stops_before) - set(stops_after))
        moved = sorted(
            coid
            for coid in set(stops_before) & set(stops_after)
            if stops_after[coid] != stops_before[coid]
        )
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"UNPROTECTED POSITION. §3:173 leaves exits UNTOUCHED and §14 gives "
                    f"the protective path zero delivery dependency, and the onset sweep "
                    f"changed the stop book: lost {lost}, moved {moved} "
                    f"(before {stops_before}, after {stops_after}). The OPEN position(s) "
                    f"{open_rows} are live at the venue with no protective stop this "
                    "process can point at — cancelling a stop inside a window is the "
                    "one thing an onset must never do"
                ),
            )
        )
    # ...and no venue message the sweep produced may NAME a protective order.
    onset_cancels = set((after_halt.get("onset") or {}).get("cancels_recorded") or [])
    protective_cancelled = sorted(onset_cancels & set(stops_before))
    if protective_cancelled:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the onset sweep issued a venue CANCEL naming protective "
                    f"order(s) {protective_cancelled}, which protect the OPEN "
                    f"position(s) {open_rows}. §3:173 cancels pending ENTRIES only"
                ),
            )
        )

    del unclassifiable
    return findings


def _arm_onset(
    drive: Drive, seen: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[str]]:
    """§3:173's onset sweep, DRIVEN. Returns `(findings, unclassifiable)`.

    Three steps, and the order is the argument: stage and prove the book is
    real, then the PER-SYMBOL onset (which must be narrow), then the GLOBAL
    one (which must be total). Running global-first would leave the per-symbol
    arm nothing to be narrow about.
    """
    findings, unclassifiable, state = _onset_stage(drive, seen)
    if findings:
        return findings, unclassifiable
    findings, blind = _onset_blackout(drive, seen, state)
    unclassifiable += blind
    if findings:
        return findings, unclassifiable
    return _onset_halt(drive, seen, state), unclassifiable


# too-many-locals: SIX named sets and their derived differences, and each name is
# one distinguishable defect this function must report separately — handed,
# cancelled, accounted, unaccounted, invented, not-cancelled, wrongly-cancelled,
# plus the protective book on both sides. Check contract rule 11 makes the REASON
# the assertion, so collapsing two of them would merge two findings into one
# sentence that names neither precisely.
def _onset_judge_sweep(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    sweep: dict[str, Any],
    *,
    cause: str,
    expect_scope: str | None,
    must_cancel: set[str],
    must_not_cancel: set[str],
    open_rows: dict[str, str],
) -> list[tuple[str, str]]:
    """One sweep, judged: scope, completeness BY DERIVATION, and selectivity.

    COMPLETENESS BY DERIVATION means the accounting closes: every id the sweep
    was HANDED is either cancelled or in a NAMED exclusion bucket, and nothing it
    cancelled was absent from what it was handed. An id that falls out of that
    equation is an order the sweep neither cancelled nor refused to cancel, which
    is the one state §3:174 has no answer for.
    """
    findings: list[tuple[str, str]] = []
    if sweep.get("scope") != expect_scope:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the {cause} sweep ran with scope={sweep.get('scope')!r}, not "
                    f"{expect_scope!r}. `None` is GLOBAL (§12.5's HALT stops every "
                    "strategy and every symbol) and a symbol is THAT SYMBOL ONLY "
                    "(§6.1's windows are per-symbol off the live calendar); the two "
                    "cancel different books"
                ),
            )
        )
    handed = {str(coid) for coid in (sweep.get("handed") or [])}
    cancelled = {str(coid) for coid in (sweep.get("cancelled") or [])}
    accounted = _onset_bucketed(sweep)
    unaccounted = sorted(handed - accounted)
    if unaccounted:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the {cause} sweep was handed {sorted(handed)} and accounted for "
                    f"{sorted(accounted)}: {unaccounted} were neither cancelled nor "
                    "placed in a named exclusion bucket. §3:172 cancels ALL pending "
                    "entries and every exclusion must SAY WHY; an order that is "
                    "neither is one nothing can prove is not working inside the window"
                ),
            )
        )
    invented = sorted(cancelled - handed)
    if invented:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the {cause} sweep cancelled {invented}, which it was never "
                    f"handed ({sorted(handed)}). A cancel outside the enumeration is a "
                    "venue message about an order this process cannot say is an entry"
                ),
            )
        )
    not_cancelled = sorted(must_cancel - cancelled)
    if not_cancelled:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the {cause} sweep did NOT cancel {not_cancelled} "
                    f"(cancelled={sorted(cancelled)}, protected={sweep.get('protected')}, "
                    f"out_of_scope={sweep.get('out_of_scope')}, "
                    f"unclassified={sweep.get('unclassified')}). Each is a gate-approved "
                    "pending ENTRY in scope, and each can now fill inside a window it "
                    "was not approved for (§3:174)"
                ),
            )
        )
    wrongly = sorted(must_not_cancel & cancelled)
    if wrongly:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the {cause} sweep cancelled {wrongly}, which are out of its "
                    f"scope ({expect_scope!r}). §6.1's windows are per-symbol"
                ),
            )
        )
    # THE SAFETY HALF, MEASURED ON BOTH SIDES OF THE ONE CALL THAT COULD BREAK IT.
    before = {
        row["client_order_id"]: row["level"]
        for row in (sweep.get("protective_before") or [])
    }
    after = {
        row["client_order_id"]: row["level"]
        for row in (sweep.get("protective_after") or [])
    }
    if before != after:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the {cause} sweep CHANGED the protective book across its own "
                    f"call: before {before}, after {after}. The OPEN position(s) "
                    f"{open_rows} were left unprotected inside the window — §3:173 "
                    "leaves exits untouched and §14 makes the protective path the one "
                    "thing that must survive an onset"
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
    # ARC 053 extends the same DERIVATION rather than editing a literal: the
    # reject arm releases one more, and the pending-timeout arm takes TWO and
    # releases both — one when the venue answers `cancelled` on the first query,
    # one when the arm finally answers the order it deliberately held. Both
    # timeout releases are the POLL's, and §3 counts them the same as a push.
    # ARC 054 extends the same DERIVATION again rather than editing a literal:
    # the onset arm takes ONSET_RESERVATIONS and releases every one of them under
    # its own onset cause (SPEC-A7), which §3 counts as a terminal release like
    # any other.
    expect_released = (
        int(HAS_CANCEL)
        + int(HAS_FILL)
        + int(HAS_REJECT)
        + TIMEOUT_RESERVATIONS
        + ONSET_RESERVATIONS
    )
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
        + _resolution_evidence(seen)
        + _onset_evidence(seen)
    )


def _onset_evidence(seen: dict[str, Any]) -> str:
    """ARC 054's arm, in the verdict line — on PASS as well as on FAIL.

    Printed green because §3:173's SELECTIVE half is a NEGATIVE property (*the
    stops did not move*) and nobody can read a negative off an absence: a gate
    whose green does not say which stops it watched has not told the operator
    what it watched them for.
    """
    if "onset_blackout_sweep" not in seen:
        return "; ONSET ARM: NOT RUN"
    blackout = seen.get("onset_blackout_sweep") or {}
    halt = seen.get("onset_halt_sweep") or {}
    edge = seen.get("onset_edge") or {}
    return (
        f"; ONSET ARM: reserved {ONSET_RESERVATIONS} pending entries across "
        f"{ONSET_BLACKOUT_SYMBOL}/{ONSET_OTHER_SYMBOL} and two strategies at "
        f"{EXPECT_ONSET_EACH} each (committed -> "
        f"{seen.get('onset_committed_after_take')}); "
        f"`pending_entries()` enumerated {seen.get('onset_enumerated')} against an "
        f"order state of {seen.get('onset_order_state')}. "
        f"A {ONSET_BLACKOUT_SYMBOL} BLACKOUT onset declared OUT OF PROCESS was "
        f"detected by the loop's own tick and swept scope="
        f"{blackout.get('scope')!r}: handed {blackout.get('handed')}, CANCELLED "
        f"{blackout.get('cancelled')}, out_of_scope "
        f"{[pair[0] for pair in (blackout.get('out_of_scope') or [])]}, released "
        f"{blackout.get('released')}, complete={blackout.get('complete')} "
        f"(committed -> {seen.get('onset_committed_after_blackout')}); it stayed "
        f"declared across {edge.get('polls_after')} polls and fired "
        f"{edge.get('blackout_onsets')} time(s) — EDGE-triggered. "
        f"A GLOBAL HALT onset then swept scope={halt.get('scope')!r}: CANCELLED "
        f"{halt.get('cancelled')}, complete={halt.get('complete')}, leaving "
        f"committed {seen.get('onset_committed_after_halt')} over "
        f"{seen.get('onset_outstanding_after_halt')} TAKEN. "
        f"*** PROTECTIVE BOOK UNCHANGED across both onsets: "
        f"{seen.get('onset_stops_before')} -> {seen.get('onset_stops_after')} ***"
    )


def _resolution_evidence(seen: dict[str, Any]) -> str:
    """ARC 053. What the two RESOLUTION paths did, in the verdict line itself.

    Printed on PASS as well as on FAIL. A gate whose green says only *the cancel
    and the fill worked* while silently also covering reject and pending-timeout
    is a gate whose scope a reader cannot see — and §4's no-resend guarantee in
    particular is a NEGATIVE property, which nobody can read off an absence.
    """
    if "reject_released" not in seen and "timeout_poll" not in seen:
        return ""
    poll = seen.get("timeout_poll") or {}
    query = poll.get("query") or {}
    parts = []
    if "reject_released" in seen:
        parts.append(
            f"REJECT ARM: reserved {EXPECT_REJECT_COMMITTED} for {REJECT_CID!r}, "
            f"pushed a §2A {EVENT_REJECT}, the loop dispatched it "
            f"(rejects_dispatched={seen.get('reject_dispatched')}, "
            f"last_disposition={seen.get('reject_last_disposition')!r}) and "
            f"{seen.get('reject_released')} of committed margin was RELEASED "
            f"({seen.get('reject_committed_before')} -> "
            f"{seen.get('reject_committed_after')}); re-delivering the identical "
            f"reject left rejects_dispatched="
            f"{seen.get('reject_dispatched_after_replay')}"
        )
    if "timeout_poll" in seen:
        parts.append(
            f"PENDING-TIMEOUT ARM: two orders reserved at "
            f"{EXPECT_TIMEOUT_COMMITTED} each past §12A:830's "
            f"{seen.get('timeout_ack_s')}s deadline; the poll QUERIED "
            f"{seen.get('timeout_queries_total')} time(s) and the venue answered "
            f"{seen.get('timeout_answers')}; the {STATE_DEAD!r} order RELEASED, "
            f"the {STATE_UNRESOLVABLE!r} order was HELD across "
            f"{FURTHER_QUERIES} further queries with committed unchanged at "
            f"{seen.get('timeout_committed_at_hold')} and then released once the "
            f"venue answered ({seen.get('timeout_resolved_total')} resolved, "
            f"outstanding {seen.get('timeout_outstanding_after')}); "
            f"*** resends={poll.get('resends')} over {poll.get('polls')} polls "
            f"and {query.get('queries')} queries ***"
        )
    if "poll_closure" in seen:
        parts.append(
            f"NO-RESEND CENSUS: the poll path's transitive closure is "
            f"{seen.get('poll_closure')} across {POLL_MODULES}, making "
            f"{seen.get('poll_calls')} distinct call(s), and it reaches NONE of "
            f"the venue-placement verbs {seen.get('banned_verbs')} derived from "
            f"{BROKER_SEAM_FILE}:{ORDER_PORT_ROSTER} — §4 resolves a pending "
            f"timeout by {POLL_ALLOWED_VERB!r} and never by an auto-resend"
        )
    return "; " + "; ".join(parts)


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


def _drive_every_arm(
    drive: Drive, seen: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Every arm, in order, stopping at the first that finds something.

    THE ORDER IS DELIBERATE and it is not alphabetical. The FILL arms run BEFORE
    the cancel idempotency arm because a defeated §4:214 dedup breaks BOTH paths,
    and the fill is where it costs most — a re-run cascade re-arms, re-releases
    and re-publishes, where a re-run cancel only releases twice. Running the fill
    arms first makes such a failure name the expensive site rather than the cheap
    one.
    """
    # ARC 053. The STRUCTURAL census runs FIRST — before anything is driven —
    # and the order is the argument. If the poll path can reach a placement verb,
    # DRIVING it is the one thing this gate must not do: the drive would itself
    # be the act of putting a second order at a venue. A census that only reads
    # source is safe to run in advance and is the only arm that can say so.
    findings, unclassifiable = _arm_no_resend_census(drive.nix_home, seen)
    if findings:
        # A build that CAN resend is never driven. The finding is enough and the
        # drive would itself be the act this arm exists to refuse.
        return findings, unclassifiable
    findings, seen_now = _arm_driven(drive)
    seen.update(seen_now)
    if not findings and HAS_FILL:
        findings += _arm_fill(drive, seen)
        if not findings:
            findings += _arm_fill_idempotent(drive, seen)
    # ARC 053. The STRUCTURAL census runs BEFORE the pending-timeout drive, and
    # the order is the argument: if the poll path can reach a placement verb,
    # DRIVING it is the one thing this gate must not do — the drive would be the
    # act of sending a second order at a venue. A census that reads source is
    # safe to run first and is the only arm that can say so in advance.
    if not findings:
        findings += _arm_idempotent(drive, seen)
        findings += _arm_unwired(drive, seen)
    # ARC 053. The two new DRIVEN arms run LAST, and that is not tidiness: both
    # take further reservations and both release them, so running either before
    # `_arm_idempotent` would move the CUMULATIVE `released_margin` that arm
    # asserts against exactly. Measured — the reject arm ran first once and the
    # idempotence assertion read 4000.0 where it expects the cancel arm's own
    # 2000.0. An arm made approximate to accommodate a later arm is an arm that
    # has stopped measuring; moving the later arm costs nothing.
    if not findings:
        findings += _arm_pending_timeout(drive, seen)
    if not findings and HAS_REJECT:
        findings += _arm_reject(drive, seen)
    # ARC 054. The ONSET arm runs LAST, and for the reason the two ARC 053 arms
    # run late, sharpened: a global HALT onset releases EVERY outstanding
    # reservation in the process, so any arm running after it would assert
    # against a ledger this one emptied. It is also the only arm that stages a
    # second strategy, and §4:266-268 keys Limiter state to a registration.
    if not findings:
        onset_findings, onset_blind = _arm_onset(drive, seen)
        findings += onset_findings
        unclassifiable += onset_blind
    return findings, unclassifiable


# R0911 refused with a reason: SEVEN returns and every one is a DISTINCT named
# outcome — no subject, the fail, the cannot-measure from a blind arm, the pass,
# the subject-unreachable refusal, the missed condition, and the uncaught error.
# Collapsing any pair would merge two verdicts this gate is required to keep
# apart (check contract rule 10, and B.2's exit-2-is-not-exit-1). The threshold
# is about branchy control flow; this is a verdict table.
def run(  # pylint: disable=unused-argument,too-many-return-statements
    mode: Mode, ctx: Context
) -> CheckResult:
    """Measure-only. `CORRECTABLE = False` — see the module constant."""
    absent = _no_subject()
    if absent:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=absent)
    drive: Drive | None = None
    seen: dict[str, Any] = {}
    try:
        drive = Drive(ctx.nix_home)
        findings, unclassifiable = _drive_every_arm(drive, seen)
        record = drive.stop()
        findings += _arm_stop_record(record)
        evidence = _evidence(seen, record)
        # RULE 4 — UNCLASSIFIABLE IS JUDGED LAST, and this ordering is the rule
        # rather than a preference. A run in which one arm found a REAL defect
        # and another could not measure at all is a FAIL: cannot-measure is the
        # verdict for a run with nothing against it, and downgrading a found
        # defect because a different arm went blind is how a red becomes a light
        # blue. The unclassifiable is still NAMED in the detail, so the operator
        # is never told the whole run was judged when part of it was not.
        if findings:
            blind = (
                ""
                if not unclassifiable
                else (
                    "; ALSO UNMEASURED (rule 4 — a FAIL outranks it, and it is "
                    "reported rather than absorbed): " + "; ".join(unclassifiable)
                )
            )
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings) + blind,
            )
        if unclassifiable:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                evidence=evidence,
                detail=f"{NAME}: " + "; ".join(unclassifiable),
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
