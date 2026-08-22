#!/usr/bin/env python3
# C0302 (too-many-lines) disabled, matching every daemon/gate module over
# pylint's 1000-line default elsewhere in this tree (e.g. `check_flatten.py`,
# `check_order_path_bans.py`, `feed_kill_drill.py`). ARC 046 grew this file
# past the line by wiring the completion ingress, the §11.3 ledger, and §3's
# handlers as process state (S2) — one daemon file over several is a smaller
# surface for the property this module exists to hold (a thing with a pid),
# not an accident of not having split it.
# pylint: disable=too-many-lines
"""`limiterd` — the Limiter as an OS PROCESS. The §2:42 Risk-Engine entrypoint.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 039 / sub-agent A. `scripts/nixrisk/loop.py` is §5:322's event loop as an
object; this file is what makes it a thing with a pid. Until it existed, nothing
in this tree could be sent a signal, appear in `pgrep`, show two tasks under
`/proc/<pid>/task`, or be killed — and every Limiter property the tree had
proven was a property of a library that a test constructed and then discarded
(ARC 038's deepest finding).

WHAT THIS PROCESS IS NOT, STATED FIRST SO NOTHING READS IT AS MORE
-------------------------------------------------------------------
It places no orders. It holds no positions. It has no broker session, no gate
pass, no reservations and no stops. **ARC 042 gave it ONE Plane-1 write and no
other** — §12.10's `go_timeout` row, enqueued when §4:210-212's breaker fires;
every other §9 event type is still unwritten by this process (see
`Plane1Booker`). It is the SUBSTRATE: a
single-threaded loop that beats, a low-priority sender thread that records, and a
live `StrategyRegistry` that outlives the commands it serves. Anything else a
reader wants from a Limiter is in `nixrisk/` and is not wired to this process yet.

ARC 040 (slice 2) added ONE invariant to that substrate and no other: §4:210-212's
GO-TIMEOUT, the deadlock breaker on the one-in-flight lock. The `resolve` verb
came with it, because §4:203-206's terminal feedback is the only thing that can
show the breaker does NOT fire on a healthy GO. §14:971's *"it can never wedge"*
is the claim; `checks/check_go_timeout.py` is what measures it from outside this
process, through the `go_timeouts` rows in the stop record below.

WHY FILES AND A DIRECTORY RATHER THAN ZMQ
------------------------------------------
§5:322 names a *"ZMQ inbox"* and §2:38 puts the Allocator behind one. There is no
bus in this tree yet (`CLAUDE.md`'s spec table lists the Nix-side bus
implementation under *not yet authored*), and inventing one inside the arc that
builds the loop would mean neither could be measured without the other. A
directory of small JSON files needs the kernel and nothing else, which is the
same argument `nixsentinel/heartbeat.py` makes for the heartbeat file, and it
makes the whole command path drivable from a shell — which is exactly how the
out-of-process gate must drive it.

Replies are written with `tempfile` + `os.replace` for the reason the heartbeat
is: `os.replace` is atomic within a filesystem, so a reader either sees the whole
reply or no reply, never half of one.

THE RUNTIME DIRECTORY IS A FIXED CONTRACT
------------------------------------------
    DIR/risk_engine.heartbeat.json  §12.1:604's beat. The NAME is
                                    `nixsentinel.heartbeat.DEFAULT_HEARTBEAT_NAME`
                                    imported, never spelled here (directive 3),
                                    because the Sentinel reads it by that name.
    DIR/inbox/                      `*.json` command files. Drained and unlinked
                                    by the loop's own tick.
    DIR/completions/                ARC 046. `*.json` §2A exec reports — §5:322's
                                    THIRD loop input, standing in for what the
                                    §5:323 sender thread surfaces, by the same
                                    files-rather-than-ZMQ argument above. Read
                                    inside the tick, dispatched serially, and
                                    unlinked once dispatched.
    DIR/outbox/                     `<id>.reply.json`, one per command, atomic.
    DIR/limiter.runtime.json        written ONCE at boot and again at clean stop.
    DIR/plane1.wal                  ARC 042. §9's DURABLE LOCAL WAL, appended by
                                    `Plane1Booker` when §4:210-212's breaker
                                    fires. The `--plane1-wal` flag moves it; the
                                    shared-pool writer that group-commits it into
                                    Postgres is a DIFFERENT process and is not
                                    started here (§9's own split).

`limiter.runtime.json`'s boot record is the in-process half of §12.2:618 —
*"Boot-flatten makes any single restart safe by design"* — made checkable: a
fresh process starts with an empty registry and no in-flight lock, so `flat` is
true by construction and `registrations` / `in_flight` are empty. It says
NOTHING about the broker; `nixrisk/coldstart.py` owns that half and is not wired
in here. A reader that took this file for the broker's answer would be taking
the one claim §4's cold-start section calls trustless.

DEATH — BOTH KINDS, AND BOTH ARE THE DOCUMENTED STATE
------------------------------------------------------
`SIGTERM` and `SIGINT` call `loop.stop()`, the loop exits at the top of its next
tick, the sender is joined, the stop record is written with a real `stopped_ts`,
and the exit code is 0. That is the supervised restart §12.2:617 expects.

`SIGKILL` is uncatchable BY DESIGN and nothing here pretends otherwise. The
process vanishes, the heartbeat file freezes at whatever `seq` the last completed
tick published, and `limiter.runtime.json` keeps `"stopped_ts": null`. That pair
— a frozen `seq` with a null `stopped_ts` — is precisely what §12.1:604 has the
Sentinel act on, and it is the reason `stopped_ts` is written at stop rather than
being inferable from the file's absence.

`debug.md` §7.12 — THE STANDING QUESTION: what would have to be true for a run of
this program to look healthy while proving nothing?
  1. **The loop never ticked** (a `--max-ticks 0` misread as "no ticks", say).
     GUARDED: 0 means *run forever*, and the stop record carries `ticks`, so a
     run that ticked zero times says so in the file the gate reads.
  2. **The heartbeat file was written by something other than the loop.** GUARDED
     in `nixrisk/loop.py`: `_publish_heartbeat` refuses any thread but the loop's
     and refuses any call from outside a tick, so a `seq` in that file cannot have
     come from anywhere else in this process.
  3. **The inbox was never drained, and the absence of replies read as "no
     commands".** GUARDED: every command file produces a reply file, including an
     unparsable one, and the reply names the reason. A command with no reply is a
     drain that did not happen.
  4. **The sender thread was never started, so the §5:323 two-task shape is a
     claim.** GUARDED: `SenderThread.start` waits on an `Event` the thread sets
     from inside itself, and refuses to boot if it never arrives.
  5. **The GO-timeout row was never booked and the absence read as "the breaker
     never fired"** (ARC 042 / CHECK-DEBT D3.425 — the state this process was in
     until this arc: the breaker fired, the runtime record said so, and §9's
     evidence plane held nothing). GUARDED: the stop record's `plane1` block
     reports `firings_seen`, `booked`, `refused` and the WAL's own `enqueued` /
     `durable` counters, so *fired and booked*, *fired and refused* and *never
     fired* are three distinguishable readings rather than one absence.
"""

from __future__ import annotations

import argparse
import enum
import json
import math
import os
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any, Final, cast

import risk_config
from nixrisk.calendar_seam import CacheState, FreshnessStamp

# ARC 058 / I1 ARC D. §4's CLOSE, driven by the closing fill — IMPORTED AND
# CALLED. The reconciling half C1 and C2 both stopped short of: they fire and
# send, and until this arc nothing turned the flatten's own exec report into a
# §12.10 `closed` row, a released open margin and a retired stop.
from nixrisk.closing import ClosingFillHandler, FlattenInFlightBook
from nixrisk.completions import (
    CompletionDispatcher,
    DispatchResult,
    Disposition,
    MalformedCompletion,
    SenderCompletion,
    parse_completion,
)
from nixrisk.execution import ExecutionLedger
from nixrisk.fills import (
    ApprovedOrderBook,
    FillHandler,
    IocRemainder,
    LimiterFillSink,
)

# ARC 054. I11's onset SELECTION, IMPORTED AND CALLED — never re-implemented and
# never edited. `flatten.py` is byte-identical across this arc and that is
# asserted with `git hash-object`, not claimed (see the ARC 054 block below).
from nixrisk.flatten import (
    BrokerFlattenPort,
    CloseTarget,
    OrderRole,
    PendingEntry,
    ProtectiveFlatten,
)

# ARC 057 / I1 ARC C2. §6.4's staleness DETECTOR (051), IMPORTED AND CALLED —
# never re-implemented and never edited. `freshness.py` is byte-identical
# across this arc and that is asserted with `git hash-object`, not claimed.
from nixrisk.freshness import FreshnessTracker, StalenessPolicy
from nixrisk.join import production_origins
from nixrisk.loop import (
    CONFIG_MODULE,
    GoTimeout,
    LimiterLoop,
    LoopStop,
    go_timeout_from_config,
    heartbeat_interval_from_config,
    tick_interval_for,
)
from nixrisk.outcomes import OrderOutcomes
from nixrisk.picture import FinancialPictureBook
from nixrisk.positions import PositionOriginWriter
from nixrisk.recovery import RecoveryError
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)
from nixrisk.stops import StopBook
from nixrisk.stopwatch import BreachFiring, PriceRing, PriceRingFull, StopWatch
from nixrisk.wal import Plane1Wal, WalError
from nixsentinel.heartbeat import DEFAULT_HEARTBEAT_NAME, HeartbeatPublisher

#: Named once so every refusal points at the same file (doctrine C.2).
SITE: Final[str] = "scripts/limiterd.py"

#: The runtime directory's fixed layout. `HEARTBEAT_NAME` is IMPORTED rather
#: than spelled, because the Sentinel opens that exact name and a second copy of
#: the string here could drift from the one it reads (directive 3).
HEARTBEAT_NAME: Final[str] = DEFAULT_HEARTBEAT_NAME
INBOX_DIR: Final[str] = "inbox"
OUTBOX_DIR: Final[str] = "outbox"
#: ARC 046. §5:322's THIRD serial input. A directory for the same reason the
#: inbox is one (see the module docstring): there is no bus in this tree, and a
#: completion path that needed one could not be driven by the out-of-process
#: gate that has to prove the DAEMON dispatches rather than the library.
COMPLETIONS_DIR: Final[str] = "completions"
RUNTIME_NAME: Final[str] = "limiter.runtime.json"
#: ARC 042. §9's durable local WAL, inside the runtime directory by default so
#: one directory is the whole contract and a drive can find the evidence beside
#: the record that claims it. `--plane1-wal` moves it.
PLANE1_WAL_NAME: Final[str] = "plane1.wal"

#: Wire versions. Three DIFFERENT namespaces because the three records cross
#: different boundaries and may be read by differently-built programs: the
#: runtime record is read by an operator and by the gate, the command file is
#: written by a client, and the reply is read by that client.
RUNTIME_SCHEMA: Final[int] = 1
COMMAND_SCHEMA: Final[int] = 1
REPLY_SCHEMA: Final[int] = 1
#: ARC 047. §4:203-206's OUTCOME PUSH, as a file. Its own namespace for the same
#: reason the three above have theirs: a feedback record is read by the
#: originating strategy FSM, not by the client that sent a command.
FEEDBACK_SCHEMA: Final[int] = 1

#: ARC 047. §12A:811 `DEPLOYABLE_PCT`, by the key it has in its one physical
#: home. Read through `risk_config` rather than off the raw JSON for the reason
#: `pending_ack_timeout_from_config` records: the file carries cross-knob boot
#: rules over this value and reading around the validator would leave them
#: validating a number this process then ignored.
DEPLOYABLE_PCT_KEY: Final[str] = "deployable_pct"


def deployable_fraction_from_config(root: Path | None = None) -> float:
    """§3:131 / §12A:811's deployable fraction. No default (directive 4).

    `FinancialPictureBook` refuses construction outside (0, 1] and takes no
    default of its own — *"§12A owns the value and this class takes no default"*
    — so this raises rather than substituting one here.
    """
    configs = risk_config.load_risk_configs(root)
    return risk_config.knob(configs.modules[CONFIG_MODULE], DEPLOYABLE_PCT_KEY)


#: §12A:830's key, read through the validator for the reason
#: `pending_ack_timeout_from_config` gives.
SIGNAL_MAX_AGE_KEY: Final[str] = "signal_max_age_ms"


def signal_max_age_from_config(root: Path | None = None) -> float:
    """ARC 053 / D3.463. The oldest signal a reservation may be approved against.

    A DECLARED NIX ADDITION, not a §12A knob, and `risks/limiter.config.json`'s
    `_meta` entry carries the whole argument. No default (directive 4): a Limiter
    that invented a signal-age ceiling would approve capital against opinions of
    an age nobody chose.
    """
    configs = risk_config.load_risk_configs(root)
    return risk_config.knob(configs.modules[CONFIG_MODULE], SIGNAL_MAX_AGE_KEY) / 1000.0


def signal_age_refusal(order: ProposedOrder, max_age_s: float) -> str:
    """ARC 053 / D3.463. §17's stale-until-proven-fresh, applied to a GO's OWN age.

    THE FRESHNESS-REFUSAL SITE FOR `ProposedOrder.signal_ts`, and being one is
    the point rather than a side effect. `checks/check_input_freshness.py`
    derives its STAMP FIELDS as *"an attribute a function that calls a clock
    subtracts from it"*, and until this arc `signal_ts` matched no such site
    anywhere in the tree — it was CLOCK-SOURCED (born at
    `signal_ts=... or time.time()` two hundred lines below) and read by no
    refusal, which is exactly what that gate reports as an UNGATED TIME FIELD and
    exactly what D3.463 recorded. The fix is both halves: this function makes it
    a stamp field, and killing the fallback stops it being clock-sourced.

    WHY THE RESERVE SEAM AND NOT `go`. The ARC 052 recon measured it: `signal_ts`
    enters this process through `reserve` and through nothing else — the `go`
    verb carries a strategy id and an order id and no instant at all. §3 takes
    the reservation AT APPROVAL, so the reserve is where a signal's age can still
    change a decision; by `go` the capital is already committed.

    Returns the refusal sentence, or `""` when the signal is fresh enough.
    """
    age = time.time() - order.signal_ts
    if age <= max_age_s:
        return ""
    # NO `{SITE}:` prefix: this sentence is handed to `CommandHandler._refuse`,
    # which prepends one. Two prefixes read as two sites and there is one.
    return (
        f"§3 refuses to take a reservation against a signal that is "
        f"{age:.3f}s old — the ceiling is {max_age_s:.3f}s "
        f"({SIGNAL_MAX_AGE_KEY}). §17 is stale-until-proven-fresh and §6.4 puts "
        "a reading past its threshold behind a refusal; approving capital "
        "against an opinion of unbounded age is the one entry-side time "
        "quantity nothing in this tree refused (CHECK-DEBT D3.463). Nothing "
        "was taken and nothing was sent"
    )


#: Command files read per tick. §11:581's bound applied to the ingress read for
#: the same reason `nixrisk/loop.py` bounds the drain: a directory somebody
#: dumped ten thousand files into must not hold one tick open past the beat.
INBOX_MAX_PER_TICK: Final[int] = 32

#: ARC 046. The same §11:581 bound on the completion read. Separate from the
#: command bound and deliberately so: a venue that pushes a burst of exec
#: reports and an operator who dropped files in the inbox are different
#: pressures, and one number covering both would make the tick's worst case a
#: function of two unrelated things.
COMPLETIONS_MAX_PER_TICK: Final[int] = 32

#: ARC 046. §12A:830's `PENDING_ACK_TIMEOUT_MS`, by the key it has in its one
#: physical home. Read through `risk_config` rather than off the raw JSON for
#: the reason `nixrisk/loop.py::go_timeout_from_config` records: the file
#: carries a cross-knob boot rule (`liveness.go_timeout_outlasts_pending_ack`)
#: relating this knob to the GO timeout, and reading around the validator would
#: leave that rule validating a value this process then ignored.
PENDING_ACK_TIMEOUT_KEY: Final[str] = "pending_ack_timeout_ms"


def pending_ack_timeout_from_config(root: Path | None = None) -> float:
    """§12A:830's ack deadline in SECONDS. No default (directive 4).

    `OrderOutcomes` requires a finite positive interval and refuses construction
    without one, which is why this raises rather than substituting: a Limiter
    that invented an ack deadline would query the venue about orders that were
    never late, or never query about ones that were.
    """
    configs = risk_config.load_risk_configs(root)
    return (
        risk_config.knob(configs.modules[CONFIG_MODULE], PENDING_ACK_TIMEOUT_KEY)
        / 1000.0
    )


#: The mode every file this process writes carries. Nothing in `~/nix` outside
#: `state/` needs to be world-readable and the default umask is not a guarantee;
#: `nixsentinel/heartbeat.py` records the same reasoning for the beat.
_MODE: Final[int] = 0o600

#: The verbs the loop serves this arc. Deliberately three: enough to exercise
#: the live registry and the one-in-flight lock from another process, and no
#: verb that could reach money. §12.11's authenticated operator verbs are a
#: different surface and are not these.
VERB_REGISTER: Final[str] = "register"
VERB_GO: Final[str] = "go"
VERB_STATUS: Final[str] = "status"
#: ARC 040. §4:203-206's terminal feedback, landed because §4:210-212's breaker
#: cannot be shown NOT to fire early unless a GO can end some other way. Without
#: it every GO in this process would end at the timeout and a gate would read
#: that as the invariant working — §0a of this arc's brief, exactly.
VERB_RESOLVE: Final[str] = "resolve"
#: ARC 046. §3's *"taken at approval"*. Landed because a daemon that holds no
#: reservations has nothing for a cancel completion to RELEASE: the dispatch
#: this arc wires could otherwise only be proven against a ledger a test
#: constructed, which is the exact library-not-process gap ARC 038 found and
#: this arc exists to close. It reaches money's ACCOUNTING and not the venue —
#: no order is placed, nothing is sent.
VERB_RESERVE: Final[str] = "reserve"
#: ARC 055 / I1 ARC C1. §5:322's FIRST loop input — *"shared-mem price poll"*.
#:
#: There is no capture feed, no shared-memory segment and no vendor integration
#: in this tree, so the price arrives the way every other out-of-process fact
#: does: through the serial ingress §5:322 already describes. That is the same
#: relationship the spec's shared-memory ring has with its consumer — something
#: else writes, the tick READS — and it is what lets the poll stay hot-path pure
#: (I9): `PriceRing.head` is one dict lookup. It is NOT a market data feed and
#: CHECK-DEBT D3.473 says so, so no green here may be read as *the Limiter is
#: receiving real prices*.
#:
#: Not strategy-scoped, unlike every verb below `register`: a price is a fact
#: about an INSTRUMENT, and requiring a `strategy_id` on it would make the
#: maintenance of a position's stop depend on which strategy happened to send
#: the tick.
VERB_PRICE: Final[str] = "price"
VERBS: Final[tuple[str, ...]] = (
    VERB_REGISTER,
    VERB_GO,
    VERB_STATUS,
    VERB_RESOLVE,
    VERB_RESERVE,
    VERB_PRICE,
)


@dataclass(frozen=True)
class RawCommand:
    """One file the ingress read, BEFORE anything decided what it means.

    Carries the bytes and the path rather than a parsed object on purpose: the
    parse is a decision, decisions belong in the tick (§5:322's serial
    processing), and a parse failure has to produce a REPLY, which the ingress
    cannot write because it does not know the id yet.
    """

    path: Path
    blob: bytes
    read_error: str


# R0903 (too-few-public-methods): ONE public verb is the whole collaborator.
# It is the loop's per-tick ingress callback and nothing else calls it; a
# second method added to clear a threshold would widen a surface whose
# narrowness is what keeps §11:581's bound on the tick meaningful.
# pylint: disable=too-few-public-methods
class Inbox:
    """§5:322's inbox read, standing in for the ZMQ socket the spec names.

    Called once per tick from inside the tick. Bounded at `INBOX_MAX_PER_TICK`
    and sorted, so the order commands are served in is the order the filesystem
    reports them in rather than whatever `scandir` felt like — FCFS is §5:325's
    own contention rule one component over, and an arbitrary order here would be
    a race nobody declared.
    """

    def __init__(self, directory: Path, loop: LimiterLoop) -> None:
        self.directory = directory
        self._loop = loop

    def drain(self, tick: int) -> int:
        """Read up to `INBOX_MAX_PER_TICK` command files onto the loop's queue.

        Does NOT unlink. The file is removed by `CommandHandler` after its reply
        is on disk, so a crash between the read and the reply leaves the command
        where the next boot can still see it.
        """
        del tick
        try:
            names = sorted(
                entry.name
                for entry in os.scandir(self.directory)
                if entry.is_file() and entry.name.endswith(".json")
            )
        except OSError as exc:
            raise RuntimeError(
                f"{SITE}: cannot scan the inbox {self.directory}: {exc!r}"
            ) from exc
        taken = 0
        for name in names[:INBOX_MAX_PER_TICK]:
            path = self.directory / name
            try:
                blob = path.read_bytes()
                error = ""
            except OSError as exc:
                blob = b""
                error = f"cannot read {path.name}: {exc!r}"
            self._loop.submit(RawCommand(path=path, blob=blob, read_error=error))
            taken += 1
        return taken


@dataclass(frozen=True)
class RawCompletion:
    """ARC 046. One §2A exec report the completion ingress read, UNPARSED.

    Carries bytes for the same reason `RawCommand` does: the parse is a decision,
    decisions belong in the tick (§5:322's serial processing), and a parse that
    ran on the ingress would decide what a completion means outside the one
    thread §5:322 says decides anything.
    """

    path: Path
    blob: bytes
    read_error: str


# R0903 (too-few-public-methods): ONE public verb is the whole collaborator —
# the same argument `Inbox` records above.
# pylint: disable=too-few-public-methods
class CompletionInbox:
    """ARC 046. §5:322's THIRD input read, standing in for the sender's surface.

    §5:323 puts the blocking venue I/O on the low-priority sender thread and
    §5:322 puts the PROCESSING in the loop. This reads what that thread would
    have surfaced. The read is here rather than on `SenderThread` deliberately:
    `nixrisk/loop.py`'s sender is a stub that records and never sends, and
    teaching it to also receive would put the venue's inbound path inside the
    module that owns the threading shape — two contracts in one object, which is
    what `Plane1Booker.before` refuses to do one collaborator over.

    WHAT THIS DOES NOT CLAIM: that a real broker session pushed anything. There
    is no vendor integration in this tree (`CLAUDE.md`'s spec table lists it
    under *not yet authored*). It claims exactly what it does — a completion
    that entered this PROCESS from outside it is dispatched by the loop's own
    tick, serially, on the loop's own thread.
    """

    def __init__(self, directory: Path, loop: LimiterLoop) -> None:
        self.directory = directory
        self._loop = loop

    def drain(self, tick: int) -> int:
        """Read up to `COMPLETIONS_MAX_PER_TICK` exec reports onto the loop's queue.

        Does NOT unlink and does NOT parse. `CompletionHandler` removes the file
        after the dispatch decision is made, so a crash between the read and the
        dispatch leaves the exec report where the next boot can still see it —
        the same durability argument `Inbox.drain` makes for a command.
        """
        del tick
        try:
            names = sorted(
                entry.name
                for entry in os.scandir(self.directory)
                if entry.is_file() and entry.name.endswith(".json")
            )
        except OSError as exc:
            raise RuntimeError(
                f"{SITE}: cannot scan the completions directory "
                f"{self.directory}: {exc!r}"
            ) from exc
        taken = 0
        for name in names[:COMPLETIONS_MAX_PER_TICK]:
            path = self.directory / name
            try:
                blob = path.read_bytes()
                error = ""
            except OSError as exc:
                blob = b""
                error = f"cannot read {path.name}: {exc!r}"
            self._loop.submit(RawCompletion(path=path, blob=blob, read_error=error))
            taken += 1
        return taken


# R0903 (too-few-public-methods): ONE public verb IS the whole port. `fills.py`
# declares `CancelPort` with exactly `cancel_order` and states why: a
# reservation-release path that could also PLACE would be a second
# order-placement site (§12.1 keeps stops synthetic; §14 makes flatten execution
# Limiter-only). A second verb here to clear a threshold would widen precisely
# that surface.
# pylint: disable=too-few-public-methods
class RecordedCancels:
    """ARC 047. §4's IOC remainder cancel — RECORDED, NEVER SENT.

    Satisfies `nixrisk.fills.CancelPort`. It is a STUB and it says so, for the
    same reason `nixrisk/loop.py`'s sender is *"a stub that records and never
    sends"*: there is no vendor integration in this tree (`CLAUDE.md`'s spec
    table lists it under *not yet authored*), so there is no socket to put a
    cancel on.

    WHAT THIS DOES NOT CLAIM, STATED FIRST: that the unfilled remainder of a
    partial fill was cancelled AT THE VENUE. It was not. §4's remainder rule has
    two halves — cancel the remainder, release its reservation — and this process
    performs the SECOND half for real (the reservation genuinely releases in the
    live §11.3 ledger) while the first is an entry in `issued`. The asymmetry is
    named here rather than left to be discovered, and it is recorded as CHECK-DEBT.
    The direction of error is the safe one: §4 says outright *"the reservation
    covered full size, so no cap breach either way"*, and an uncancelled remainder
    that later fills is the OVER-FILL case `IocRemainder` already counts.
    """

    def __init__(self) -> None:
        #: Every cancel this process WOULD have sent, in order. An observable for
        #: the reason every counter in this file is one: a component that cannot
        #: say what it did can only be believed, not measured.
        self.issued: list[str] = []

    def cancel_order(self, client_order_id: str) -> None:
        """Record the IOC cancel §4 requires. Sends nothing."""
        self.issued.append(str(client_order_id))


class RecordedVenue(RecordedCancels):
    """ARC 055 / I1 ARC C1. The daemon's broker, NOW WITH §4's `flatten` VERB.

    ARC 054 gave `ProtectiveFlatten` a broker that had `cancel_order` and NOT
    `flatten`, deliberately: *"a broker here that could flatten would be
    authority this arc withheld. The missing verb is the guarantee, not an
    oversight."* MEASURED again at this arc's S1 on a live daemon —
    `hasattr(RecordedCancels(), "flatten") is False`. C1 is the arc that grants
    the authority, because a synthetic stop that breaches and cannot be
    protectively closed is not a stop.

    STILL A STUB, and the same one `RecordedCancels` is: there is no vendor
    integration in this tree, so `flatten` RECORDS the protective close this
    process issued and puts it on no socket. What is real is everything on this
    side of the venue — the breach was detected on the tick, the flatten was
    arbitrated under §4's PROTECTIVE authority, the §12.10 `protective_exit` row
    was booked, and the call reached the broker port. What is NOT real is the
    position going flat at an exchange. CHECK-DEBT records it; no green here may
    be read as *the position is closed*, which is the exact distinction
    `flatten.FlattenAction` is a separate type from `ConfirmedFlat` to preserve.

    IT IS ALSO WHY I3 SURVIVES THIS ARC. §14's zero-wire property is that the
    protective exit reaches the venue through a DIRECT IN-PROCESS SYNC CALL — no
    Allocator, no ZMQ, no state bus, nothing awaited. A recorder satisfies that
    by construction and `check_flatten` ARM 6 measures it; this arc adds no
    transport and therefore removes no part of the guarantee.
    """

    def __init__(self) -> None:
        super().__init__()
        #: Every protective flatten this process issued, in order, as
        #: `(symbol, seq)`. `None` is §4's flatten-everything. Enumerated rather
        #: than counted for the reason every observable in this file is: the
        #: safety question is *was exactly one flatten issued for this breach*,
        #: and a total cannot answer it.
        self.flattened: list[str | None] = []

    def flatten(self, symbol: str | None = None) -> None:
        """Record §4's protective close. SYNC, in-process, sends nothing."""
        self.flattened.append(None if symbol is None else str(symbol))


class FillPath:  # pylint: disable=too-many-instance-attributes
    # NINE collaborators, and that count IS this arc's central measurement:
    # ARC 046 wired `on_cancel` by handing the dispatcher ONE object it already
    # held. Fill needed nine, because §3's *converts to open-margin* is a
    # cascade and not a release. Collapsing them behind a facade would hide the
    # cost this class exists to report, and every one of them is read by
    # `record()` below out of a real drive.
    """ARC 047. Everything the PROCESS must hold for §2A:75's `on_fill` to work.

    Assembled here and nowhere else. Not one line of `nixrisk/fills.py`,
    `stops.py`, `positions.py`, `picture.py`, `execution.py` or `join.py` was
    edited to make this possible — they are byte-identical across this arc and
    that is asserted with `git hash-object`, not claimed. **The whole change is
    that something with a pid now owns them.** That sentence is ARC 046's about
    the ledger and the outcome handlers, and it is the shape of I1: the
    mechanisms were built and gated arcs ago and no running process ever called
    one (ARC 038's deepest finding; D3.178's *zero production callers*).

    THE ORDER OF THE CASCADE IS `fills.py`'s AND IS NOT RESTATED HERE
    ----------------------------------------------------------------
    `FillHandler.on_fill` arms the stop (§4's distance->price conversion at the
    CONFIRMED fill), then IOC-cancels and releases the remainder (§4's
    partial-fill rule), then publishes §3's row — and it RAISES rather than
    returning a partial outcome. This class composes; it does not sequence.

    WHAT IT IS NOT
    --------------
    * **It is not a broker.** `RecordedCancels` above records the one venue
      message this path produces and sends nothing. §12.1's synthetic-stop
      prohibition is kept structural: `StopBook` reaches no broker at all, so
      "the protective stop is placed" means a live `StopState` in this
      process's memory at `fill -/+ distance x tick_size`, and §12.1:604 has the
      Sentinel cover the process-death gap. A killed Risk Engine is still an
      unprotected position and no green here denies it.
    * **It writes no Plane-1 `filled` row.** `seam.EventKind` has no member for
      it — *"a member lands here ONLY when the machinery that emits it exists"* —
      and adding one is a frozen-seam edit outside this arc's authority.
      CHECK-DEBT D3.434, named rather than skipped.
    * **It maintains the stop, as of ARC 055.** §4's trailing ratchet is
      `StopBook.maintain`, driven by `StopWatchDriver` off the §5:322 price
      poll. A TRAILING stop armed here is ratcheted by every price the `price`
      verb publishes and fires ONE protective flatten on breach. What this
      daemon still has no CAPTURE feed for is the price itself — it arrives over
      the command ingress, which is CHECK-DEBT D3.473 and is not this line.

      ARC 056 / D3.474: until this arc a trailing stop could not be armed at
      all. `ProposedOrder` carried no trail distance, so `StopBook.arm` denied
      every trailing conversion, the fill was refused whole and the reservation
      leaked. The order now carries `trail_ticks` from the GO and the cascade
      runs; a trailing order that STILL carries none is refused with its
      reservation released — see `nixrisk/fills.py`'s `UnarmableFill`.
    * **It refreshes no balance.** §6.4b's event-driven balance refresh is not
      wired; see `--account-balance`.

    THE TICK-SIZE MAP IS BOOT-LOADED, AND ITS ABSENCE FAILS CLOSED
    -------------------------------------------------------------
    `StopBook` takes a per-symbol tick size and COPIES it, deliberately (*"so a
    later mutation of the caller's mapping cannot silently re-scale a live
    stop"*). Tick size is an instrument constant on §12.11's boot-loaded,
    restart-only lifecycle, so it arrives on the command line and never changes
    afterwards. There is no instrument table in `risks/` to read it from —
    `allocator_caps.config.json` carries `tick_value_usd`, which is the DOLLAR
    value of a tick and not its PRICE increment — so inventing one here would be
    the hardcoded `tick_size` constant `nixalloc/sizing.py` forbids by name.

    A symbol absent from the map is NOT-TRADABLE (§4:198): `StopBook.arm` raises
    `UntradableSymbol` BEFORE the remainder is released, so the cascade refuses
    whole and **no reservation converts and no position opens**. That is the
    fail-closed direction and it is the safe minimum this arc guarantees: this
    process cannot open a position it has no stop for.
    """

    def __init__(
        self,
        *,
        reservations: ReservationLedger,
        balance: float,
        deployable_fraction: float,
        tick_size: dict[str, float],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.picture = FinancialPictureBook(
            balance=balance, deployable_fraction=deployable_fraction
        )
        self.execution = ExecutionLedger()
        self.stops = StopBook(tick_size)
        self.tick_size = dict(tick_size)
        # THE PRODUCTION JOIN, not the degenerate one. `production_origins`
        # REFUSES `positions.identity_trade_id` — D3.177's architect ruling —
        # so every `trade_id` this daemon mints is genuinely distinct from its
        # `client_order_id` and the two keys can be observed to disagree.
        self.origins = production_origins()
        self.approvals = ApprovedOrderBook()
        self.cancels = RecordedCancels()
        self.writer = PositionOriginWriter(
            picture=self.picture,
            ledger=self.execution,
            stops=self.stops,
            origins=self.origins,
        )
        self._reservations = reservations
        self.remainder = IocRemainder(
            reservations=reservations, cancels=self.cancels, clock=clock
        )
        self.handler = FillHandler(
            orders=self.approvals,
            stops=self.stops,
            remainder=self.remainder,
            writer=self.writer,
        )
        self.sink = LimiterFillSink(
            handler=self.handler, orders=self.approvals, clock=clock
        )
        #: Approvals this process refused to hold after taking the reservation.
        #: Counted because such an order can NEVER fill (the sink refuses an
        #: unapproved fill) while its capital is committed — a state an operator
        #: must be able to read rather than infer.
        self.approval_failures: list[str] = []

    def approve(self, order: ProposedOrder) -> None:
        """§3's *taken at approval*, completed: HOLD the order and MINT the join.

        Called at `reserve`, which is this build's approval moment, and it is the
        only moment at which the approval's three facts exist together. Both
        registries below refuse a duplicate loudly and neither is optional:

        * `ApprovedOrderBook` holds `stop_ticks` — *the sizer's own distance*
          (§7:476) — which is the WHOLE INPUT to §4's distance->price conversion
          and which an execution report does not carry. Before this arc the
          daemon built a `ProposedOrder` at `reserve` and DISCARDED it, so a fill
          arriving later had no distance to convert and no requested size to
          measure §4's remainder against. Measured at ARC 047 S1.
        * `EntryOrderOrigins` mints the `trade_id` §3:159 keys the position table
          by, and records the trade<->order join. §4 mints at OPEN; the JOIN is
          recorded at approval because that is when it exists, and the row does
          not become `PositionState.OPEN` until the confirmed fill publishes it.

        Raises. The caller refuses the whole command rather than replying
        accepted over a half-approved order — see `CommandHandler._reserve`.
        """
        self.approvals.record(order)
        self.origins.record(order)
        # §4:198's instrument field set, seeded from the approval that named it.
        # §6.4 makes per-symbol margin LIVE venue state rather than config, and
        # this process has no margin feed, so the approval is the only authority
        # in the room. `PositionOriginWriter` refuses a fill in a symbol absent
        # from this set rather than defaulting one, so seeding it here is what
        # makes the published row's `margin` have a scale at all.
        current = dict(self.picture.current().margin_per_contract)
        current[order.symbol] = order.margin_per_contract
        # §3's Σ reservations, onto the SAME snapshot, in the SAME commit. Before
        # this arc the daemon's ledger and its picture were two numbers for one
        # fact and only the ledger moved; §3's atomicity rule is that balance and
        # the position table publish TOGETHER, and a Σ that lagged its own ledger
        # would make the conversion invisible in the one snapshot every consumer
        # reads. Taken from the ledger rather than added up here — one authority.
        self.picture.commit(
            margin_per_contract=current,
            sum_reservations=self._reservations.total_reserved(),
        )

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. Counters AND the state itself.

        The stops and the rows are enumerated, not counted, because the safety
        question an outside reader must be able to answer is *does a stop exist
        for this open position* — and two totals that happen to match cannot
        answer it. `check_limiter_daemon_dispatch` reads exactly this.
        """
        picture = self.picture.current()
        return {
            "delivered": self.sink.delivered,
            "handled": self.handler.handled,
            "conversions": self.handler.conversions,
            "re_arms_declined": self.handler.re_arms_declined,
            "approvals": self.approvals.recorded,
            "origins": self.origins.recorded,
            "approval_failures": list(self.approval_failures),
            "cancels_recorded": list(self.cancels.issued),
            "cancels_issued": self.remainder.cancels_issued,
            "releases": self.remainder.releases,
            "refused_releases": self.remainder.refused_releases,
            "over_fills": self.remainder.over_fills,
            "writes": self.writer.writes,
            "write_duplicates": self.writer.duplicates,
            "write_refusals": self.writer.refusals,
            # THE SAFETY EVIDENCE. Every live synthetic stop, by the order it
            # protects, with the absolute level §4's conversion produced.
            "stops": [
                {
                    "client_order_id": st.client_order_id,
                    "symbol": st.symbol,
                    "side": st.side.value,
                    "mode": st.mode.value,
                    "initial_distance_ticks": st.initial_distance_ticks,
                    # ARC 056 / D3.474. §4:190-196's SECOND distance, published
                    # because it is the only thing that distinguishes a trailing
                    # stop that will actually trail from one armed with a zero
                    # gap — which ratchets to the high-water mark itself and
                    # stops out on the first adverse tick. `0` for a FIXED stop.
                    "trail_distance_ticks": st.trail_distance_ticks,
                    "anchor": st.anchor,
                    "level": st.level,
                    "activated": st.activated,
                }
                for st in self.stops.stops()
            ],
            # THE §3 POSITION TABLE, as published. `state` is here so an OPEN row
            # is distinguishable from any other, and `stop_distance` so a reader
            # can join a row to the stop above WITHOUT trusting either count.
            "positions": [
                {
                    "trade_id": row.trade_id,
                    "symbol": row.symbol,
                    "strategy_id": row.strategy_id,
                    "size": row.size,
                    "margin": row.margin,
                    "state": row.state.value,
                    "stop_distance": row.stop_distance,
                }
                for row in picture.positions
            ],
            # Fills refused for want of an armed stop. §14 resolves an
            # unprotected position toward FLAT and nothing in this process fires
            # that flatten yet — the residual `positions.py` names and this
            # daemon inherits. A NON-EMPTY list here is the unprotected-position
            # condition, published where an outside reader can act on it.
            "unstopped": [
                {
                    "client_order_id": rec.client_order_id,
                    "trade_id": rec.trade_id,
                    "symbol": rec.symbol,
                    "filled_qty": rec.filled_qty,
                }
                for rec in self.writer.unstopped()
            ],
            # ARC 056 / D3.474. Fills whose STOP COULD NOT BE CONVERTED at all —
            # a different condition from `unstopped` above and reported
            # separately for §18's reason. `unstopped` is the WRITER refusing to
            # publish a row for a fill with no stop in the book; this is the
            # CONVERSION itself being denied one step earlier, and each entry
            # says in its own sentence whether that order's reservation came
            # back. A non-empty list with a `release` that does not begin
            # RELEASED is the reservation-leak condition, published where an
            # outside reader can act on it rather than inferred from a Σ that
            # will not come down.
            "arm_refusals": self.handler.arm_refusals,
            "unarmable": [
                {
                    "client_order_id": rec.client_order_id,
                    "exec_id": rec.exec_id,
                    "symbol": rec.symbol,
                    "stop_mode": rec.stop_mode,
                    "refusal": rec.refusal,
                    "release": rec.release,
                }
                for rec in self.handler.unarmable()
            ],
            "tick_size": dict(self.tick_size),
        }

    def picture_record(self) -> dict[str, Any]:
        """§3's ONE snapshot, as fields. The conversion's other half.

        `committed` in a `status` reply is §11.3's Σ over TAKEN reservations and
        is the ledger's; `committed` here is §3's `sum_open_margin +
        sum_reservations` and is the picture's. They are different figures with
        one name in two documents, so both are published under names that say
        which — a fill that converted is the pair moving in OPPOSITE directions
        under ONE version stamp, and a reader given only one number cannot see it.
        """
        picture = self.picture.current()
        return {
            "version": picture.version,
            "balance": picture.balance,
            "sum_open_margin": picture.sum_open_margin,
            "sum_reservations": picture.sum_reservations,
            "committed": picture.committed,
            "deployable": picture.deployable,
            "rows": len(picture.positions),
            "margin_symbols": sorted(picture.margin_per_contract),
            "commits": self.picture.commits,
            "refusals": self.picture.refusals,
        }


# R0903 (too-few-public-methods): ONE public verb — the push itself.
# pylint: disable=too-few-public-methods
class OpenFeedback:
    """ARC 047. §4:203-206's OUTCOME PUSH for a confirmed fill, tagged `trade_id`.

    §4:203-206, quoted by `nixrisk/loop.py::resolve_in_flight`: *"every outcome
    (sized / denied / pending / open / closed / rejected / protective-flatten) is
    pushed to the originating strategy FSM"*. `open` is one of them and this is
    the half that had no sender.

    TWO ACTIONS, AND WHY BOTH
    -------------------------
    1. **A feedback record in the outbox**, `<trade_id>.feedback.json`, written
       atomically for the reason every reply here is. Files rather than ZMQ by
       the same argument the module docstring makes for the inbox: there is no
       bus in this tree, and a feedback path that needed one could not be driven
       by the out-of-process gate that must prove the DAEMON pushed it.
    2. **The §4:208 one-in-flight lock comes OFF.** A confirmed fill is a
       TERMINAL outcome, and `loop.resolve_in_flight(..., "open")` is the Limiter
       side of §4:203-206. Without it a filled order would hold the lock until
       §4:210-212's deadlock breaker fired and booked a §12.10 `go_timeout` row
       for an order that had actually FILLED — the breaker firing on the healthy
       path, which is exactly what ARC 040 landed the `resolve` verb to make
       falsifiable.

    NEITHER IS A STRATEGY FSM. Nothing in this tree consumes the record: the
    strategy side is `nix_strategy_contract_v1.1.md`'s and there is no bus. This
    is the Limiter's half, written where a consumer can read it. The record is
    tagged by `trade_id` because §4 tags feedback BY trade id precisely so it
    cannot be applied to the wrong position.

    Runs INSIDE the tick, on the loop's thread — `resolve_in_flight` refuses any
    other thread — so it is serial with everything else §5:322 processes.
    """

    def __init__(self, loop: LimiterLoop, outbox: Path) -> None:
        self._loop = loop
        self._outbox = outbox
        #: Every push, in order. An observable, and the gate's evidence that the
        #: feedback carried THIS trade's id rather than a count of pushes.
        self.pushed: list[dict[str, Any]] = []
        self.failures: list[str] = []

    def push(self, result: DispatchResult) -> None:
        """Push OPEN feedback for one dispatched fill. NEVER RAISES.

        Contained for the reason every handler in this file is: this runs inside
        the tick and an exception escaping here would kill the process §12.1:604
        has the Sentinel watching — turning a feedback fault into a trading
        outage, and leaving every synthetic stop this process holds unwatched.
        """
        completion = result.completion
        origin = None
        try:
            record = {
                "schema": FEEDBACK_SCHEMA,
                "outcome": "open",
                "trade_id": result.trade_id,
                "client_order_id": completion.client_order_id,
                "exec_id": completion.exec_id,
                "symbol": completion.symbol,
                "fill_price": completion.price,
                "size": result.opened_size,
                "stop_level": result.stop_level,
                "stop_distance_ticks": result.stop_distance_ticks,
                "open_margin": result.converted_margin,
                "ts": time.time(),
                "tick": self._loop.tick_count,
                "reason": (
                    f"{SITE}: §4:203-206 terminal outcome 'open' — the venue "
                    f"confirmed a fill, §4 minted trade {result.trade_id!r}, the "
                    f"protective stop is ARMED at {result.stop_level} and §3's "
                    "reservation converted to open margin"
                ),
            }
            origin = self._loop_origin(completion.client_order_id)
            if origin is not None:
                record["strategy_id"] = origin
                held, why = self._loop.resolve_in_flight(
                    origin, completion.client_order_id, "open"
                )
                record["in_flight_released"] = held
                record["in_flight_reason"] = why
            else:
                record["strategy_id"] = ""
                record["in_flight_released"] = False
                record["in_flight_reason"] = (
                    f"{SITE}: no strategy_id is known for "
                    f"{completion.client_order_id!r}, so §4:208's lock could not "
                    "be addressed"
                )
            safe = "".join(
                ch if ch.isalnum() or ch in "-_." else "_"
                for ch in (result.trade_id or completion.client_order_id)
            )
            _write_json_atomically(self._outbox / f"{safe}.feedback.json", record)
            self.pushed.append(record)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self.failures.append(
                f"{SITE}: §4:203-206 OPEN feedback for trade "
                f"{result.trade_id!r} (order {completion.client_order_id!r}) was "
                f"NOT pushed: {type(exc).__name__}: {exc}. The position IS open "
                "and its stop IS armed; the strategy was not told"
            )

    def _loop_origin(self, client_order_id: str) -> str | None:
        """The strategy holding §4:208's lock for this order, or `None`.

        Read off the LOOP rather than off the approval registry deliberately: the
        question this answers is *whose in-flight lock does this fill resolve*,
        and only the loop knows which locks are held. An approval's `strategy_id`
        would answer a different question and could name a strategy whose lock
        was already released.
        """
        for strategy_id, held in self._loop.in_flight_holders():
            if held == client_order_id:
                return strategy_id
        return None


# R0903 (too-few-public-methods): ONE public verb — the §4 fan-out this daemon
# now has a channel for. A second method added to clear a threshold would widen
# a surface whose narrowness is the point, exactly as `OpenFeedback` argues.
# pylint: disable=too-few-public-methods
class ClosedFeedback:
    """ARC 058 / I1 ARC D. §4:203-206's `closed` OUTCOME PUSH — the exit half.

    `OpenFeedback` above is the same object for the `open` outcome and this is
    its mirror, written for the same reason and against the same quotation:
    *"every outcome (sized / denied / pending / open / closed / rejected /
    protective-flatten) is pushed to the originating strategy FSM"*. `closed` is
    one of them, and until this arc this daemon's only implementation of §4's
    `StrategyExitSink` was `UnwiredExitSinks.on_closed`, which RAISES.

    IT IMPLEMENTS `flatten.StrategyExitSink` AND IS NOT ONE OF ITS CALLERS
    ---------------------------------------------------------------------
    `ProtectiveFlatten` keeps `UnwiredExitSinks` — its `_fan_out` runs only from
    `reconcile_and_publish`, which needs the two ASYNC §2A query verbs this
    daemon's stub venue does not have, so that path is still unreached and still
    refuses loudly rather than absorbing. THIS sink is handed to the CLOSING-FILL
    path (`nixrisk/closing.py`), which is the route the exit report actually
    takes. Two sinks because there are two paths and only one of them exists.

    **`hard_reset` is carried, not acted on, and that is the honest boundary.**
    §4 hard-resets the owning FSM to flat on a protective close; the FSM is the
    STRATEGY's (`nix_strategy_contract_v1.1.md`) and there is no bus in this
    tree, so what the Limiter owes is the record, atomically written where a
    consumer can read it. §4:208's one-in-flight lock is deliberately NOT touched
    here: the entry order's lock was already released by the `open` outcome, and
    a lock this strategy holds NOW belongs to a DIFFERENT order — releasing it on
    a close would free a slot for an order still working at the venue.

    NEVER RAISES, for `OpenFeedback.push`'s reason: this runs inside the tick and
    an exception escaping it would kill the process holding every synthetic stop.
    """

    def __init__(self, loop: LimiterLoop, outbox: Path) -> None:
        self._loop = loop
        self._outbox = outbox
        #: Every push, in order. The gate's evidence that the feedback carried
        #: THIS trade's id and §4's verdict rather than a count of pushes.
        self.pushed: list[dict[str, Any]] = []
        self.failures: list[str] = []

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        """§4 fan-out (a). Push `closed` for one trade. NEVER RAISES."""
        try:
            record = {
                "schema": FEEDBACK_SCHEMA,
                "outcome": "closed",
                "trade_id": trade_id,
                "strategy_id": strategy_id,
                "closed_reason": reason,
                "hard_reset": hard_reset,
                #: §4's verdict spelled as the state the FSM is being reset TO,
                #: so a consumer reads the transition rather than a boolean it
                #: has to know the meaning of.
                "fsm": "flat" if hard_reset else "unchanged",
                "ts": time.time(),
                "tick": self._loop.tick_count,
                "reason": (
                    f"{SITE}: §4:203-206 terminal outcome 'closed' — trade "
                    f"{trade_id!r} is CLOSED ({reason}); §4 "
                    f"{'hard-resets' if hard_reset else 'does NOT hard-reset'} "
                    "the owning FSM to flat"
                ),
            }
            safe = "".join(
                ch if ch.isalnum() or ch in "-_." else "_" for ch in (trade_id or "-")
            )
            _write_json_atomically(self._outbox / f"{safe}.closed.json", record)
            self.pushed.append(record)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self.failures.append(
                f"{SITE}: §4:203-206 CLOSED feedback for trade {trade_id!r} was "
                f"NOT pushed: {type(exc).__name__}: {exc}. The position IS "
                "closed and its capital IS released; the strategy was not told"
            )

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. ENUMERATED, never counted."""
        return {
            "pushed": [
                {
                    "trade_id": entry.get("trade_id"),
                    "strategy_id": entry.get("strategy_id"),
                    "closed_reason": entry.get("closed_reason"),
                    "hard_reset": entry.get("hard_reset"),
                    "fsm": entry.get("fsm"),
                    "tick": entry.get("tick"),
                }
                for entry in self.pushed
            ],
            "failures": list(self.failures),
        }


# R0903 (too-few-public-methods): ONE public verb, the loop's per-item callback.
# pylint: disable=too-few-public-methods
class CompletionHandler:
    """ARC 046. Turns one `RawCompletion` into one §3 dispatch. NEVER RAISES.

    This is I1's shape in one object: the completion arrives from outside the
    process, the LOOP drains it inside its own tick, and the dispatcher calls
    §3's already-proven handler. Nothing here decides what a release means —
    `nixrisk/outcomes.py` does, unchanged, and `nixrisk/reservations.py`
    accounts for it, unchanged. Both are byte-identical across this arc.

    Contained for the reason every other handler in this file is: a Limiter that
    died of one malformed exec report would be a remote kill switch on the
    process holding every synthetic stop (§12.1:604).
    """

    def __init__(
        self,
        dispatcher: CompletionDispatcher,
        feedback: OpenFeedback | None = None,
        uncertainty: UncertaintyDriver | None = None,
        closing: ClosingFillHandler | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        #: ARC 058 / I1 ARC D. OPTIONAL on the argument every collaborator here
        #: is optional on: a build without it dispatches a CLOSING exec report
        #: down the ENTRY path, which refuses it as an `UnapprovedFill` and
        #: leaves it in §14's `unclassified` list — the exact ARC 058 / S1 state,
        #: reported by `record()` as `closing: null` rather than as zero closes.
        self._closing = closing
        #: ARC 057 / I1 ARC C2. OPTIONAL for `feedback`'s reason: every reader
        #: written against the ARC 046/047 constructor still builds this handler,
        #: and a build without it dispatches the fill and produces no §14
        #: uncertainty flatten — which `record()` reports as `uncertainty: null`
        #: rather than as zero firings.
        self._uncertainty = uncertainty
        #: ARC 047. Optional so every reader written against the ARC 046
        #: constructor still builds this handler; a build without it dispatches
        #: the fill and pushes no §4:203-206 outcome, which `record()` below
        #: reports as `feedback: null` rather than as zero pushes.
        self._feedback = feedback
        #: Refusals that never reached the dispatcher — unreadable file, bad
        #: JSON, no exec_id. Counted here rather than in the dispatcher's ledger
        #: because "never parsed" and "parsed and refused" are two readings and
        #: one counter over both would hide which (`completions.py` §7.12 #1).
        self.malformed: list[str] = []
        #: ARC 058. CLOSES the close path itself refused — §3 declined the
        #: commit, so the position is still OPEN here and the flatten is still
        #: in flight. Kept OUT of `malformed` above for that list's own reason:
        #: *a completion this process could not parse* and *a close §3 refused*
        #: are two readings, and one counter over both would hide which.
        self.closing_refusals: list[str] = []

    def handle(self, item: RawCompletion) -> None:
        """The loop's per-item callback for a completion. Dispatches, then unlinks."""
        # Counted HERE — before the parse, before the dispatch, before anything
        # can decide the completion away. This is the loop saying "I drained
        # one", and it must survive the dispatch being absent: see
        # `nixrisk/completions.py::DispatchLedger` on the PLANT A measurement
        # that put it here.
        self._dispatcher.ledger.consumed += 1
        if item.read_error:
            self._refuse(item, item.read_error)
            return
        try:
            completion = parse_completion(item.blob, source=str(item.path))
        except MalformedCompletion as exc:
            self._refuse(item, str(exc))
            return
        # ARC 058 / I1 ARC D. THE CLOSING FILL IS ASKED FOR FIRST, AND THE ORDER
        # IS THE WHOLE FIX. `CompletionDispatcher.dispatch` CLAIMS §4:214's dedup
        # key before it runs the cascade, and the cascade refuses an exit report
        # as an `UnapprovedFill` — so a close reaching the dispatcher first is a
        # close whose key is spent and which can never be reconciled, and §14's
        # classifier then records it as `unclassified`. Measured at S1 on a live
        # daemon, which is why this branch is above and not below.
        #
        # `close()` returns `None` for anything that is not a close this process
        # asked for, and `nixrisk/closing.py` derives that from §3/§4's own join
        # and from what the daemon RECORDED SENDING — never from a field on the
        # wire, because §2A:74-84's `on_fill` carries no role.
        if self._closing is not None:
            try:
                if self._closing.close(completion) is not None:
                    self._unlink(item)
                    return
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                # Contained for this file's standing reason. A close §3 REFUSED
                # is already recorded on the handler's own `refusals` with the
                # picture's sentence, and the completion is NOT then dispatched
                # down the entry path: it is a close, it is named, and the
                # protective flatten stays in flight for a later reconcile.
                self.closing_refusals.append(
                    f"{SITE}: §4's close of "
                    f"{completion.client_order_id}/{completion.exec_id} in "
                    f"{completion.symbol!r} was REFUSED: "
                    f"{type(exc).__name__}: {exc}"
                )
                self._unlink(item)
                return
        result = self._dispatcher.dispatch(completion)
        # ARC 057 / I1 ARC C2. §14's uncertainty classification, AFTER the
        # cascade and BEFORE the feedback push. The order is the safety
        # property: a fill the cascade REFUSED opened no §3 row and armed no
        # stop, so the venue is holding a position this process can neither
        # protect (D3.475) nor account for (D3.372) — and the classifier must see
        # the refusal before anything downstream can treat the completion as
        # handled. The FIRE is not here: this notes and enqueues on the loop
        # thread and §5:323's sender thread does the rest.
        if self._uncertainty is not None:
            self._uncertainty.note_fill_dispatch(completion, result)
        # ARC 047. §4:203-206's outcome push, AFTER the cascade and only on a
        # real dispatch. Ordered that way because the feedback asserts a trade is
        # OPEN with a stop armed, and a push that ran before the cascade — or on
        # a refusal — would tell the strategy about a position that does not
        # exist. §14: *"Open" = confirmed fill only. Never optimistic.*
        if (
            self._feedback is not None
            and result.disposition == Disposition.DISPATCHED
            and result.trade_id
        ):
            self._feedback.push(result)
        self._unlink(item)

    def _refuse(self, item: RawCompletion, why: str) -> None:
        self.malformed.append(why)
        self._dispatcher.ledger.malformed += 1
        self._unlink(item)

    @staticmethod
    def _unlink(item: RawCompletion) -> None:
        try:
            item.path.unlink()
        except OSError:
            # Gone already, or a directory that vanished under us. The dispatch
            # decision is recorded either way, and §4:214's dedup makes a
            # re-served completion a counted duplicate rather than a second
            # release — which is precisely why the dedup is keyed on the exec
            # report and not on the file.
            pass


# R0903 (too-few-public-methods): ONE public verb — it IS the loop's handler.
# pylint: disable=too-few-public-methods
class LoopHandler:
    """ARC 046. Routes ONE drained item to the collaborator that owns it.

    §5:322 gives the loop three serial inputs and ONE place that processes them.
    `LimiterLoop.attach` takes one handler, so the routing is here rather than
    in the loop: which kinds of work a Limiter serves is this file's business
    (it is the process), and how they are serialised is `nixrisk/loop.py`'s.

    Still fail-closed on an unknown item, and the refusal still names both types
    — an item nobody owns is a submission bug, and absorbing it would let a
    future arc queue something the loop silently discarded.
    """

    def __init__(
        self, commands: CommandHandler, completions: CompletionHandler
    ) -> None:
        self._commands = commands
        self._completions = completions

    def handle(self, item: object) -> None:
        """The loop's per-item callback."""
        if isinstance(item, RawCommand):
            self._commands.handle(item)
            return
        if isinstance(item, RawCompletion):
            self._completions.handle(item)
            return
        raise TypeError(
            f"{SITE}: the loop handed the handler a {type(item).__name__}; this "
            f"process submits only {RawCommand.__name__} (§5:322's inbox) and "
            f"{RawCompletion.__name__} (§5:322's sender completions)"
        )


# R0903 (too-few-public-methods): ONE public verb is the whole handler. It is
# the loop's per-item callback and nothing else calls it; a second method added
# to clear a threshold would widen a surface whose narrowness is the point.
# pylint: disable=too-few-public-methods
class CommandHandler:  # pylint: disable=too-many-instance-attributes
    """Turns one `RawCommand` into one reply file. NEVER RAISES.

    Fail-closed and contained (directive 4, and `nixrisk/loop.py`'s own
    containment argument): every refusal is a reply with `accepted: false` and a
    reason naming the spec coordinate it refused under. A command that could kill
    this process would be a remote kill switch on the process §12.1:604 has the
    Sentinel watching, so an unparsable file is answered, not fatal.
    """

    # R0913/R0917 refused with a reason: every parameter but the last is a
    # COLLABORATOR this process owns and hands in — the loop, the outbox, §11.3's
    # ledger, §5:322's dispatcher, §4's fill path, §4's timeout poller, §3:173's
    # onset watch and D3.443's pending-entry book — plus one §12A ceiling read at
    # boot. Bundling them into a config object would put a container between this
    # handler and the objects whose ABSENCE it reports differently from their
    # emptiness (`_picture()`'s `None`-vs-0.0 argument, and check contract rule 10
    # underneath it), and every one is optional precisely so that difference stays
    # visible. The count is stated as a rule rather than a number because a number
    # here goes stale the moment the next collaborator lands (directive 3).
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        loop: LimiterLoop,
        outbox: Path,
        reservations: ReservationLedger | None = None,
        dispatcher: CompletionDispatcher | None = None,
        fills: FillPath | None = None,
        timeouts: PendingTimeoutPoller | None = None,
        onset: OnsetWatch | None = None,
        book: PendingEntryBook | None = None,
        signal_max_age_s: float | None = None,
        prices: PriceRing | None = None,
        stopwatch: StopWatchDriver | None = None,
        uncertainty: UncertaintyDriver | None = None,
        closing: ClosingFillHandler | None = None,
        closed_feedback: ClosedFeedback | None = None,
    ) -> None:
        self._loop = loop
        self._outbox = outbox
        #: ARC 046. Optional so every reader written against the ARC 040 CLI
        #: still constructs this handler; a build without them serves `reserve`
        #: as a NAMED refusal rather than as an unknown verb, because "this
        #: build has no ledger" and "no such verb exists" are two readings.
        self._reservations = reservations
        self._dispatcher = dispatcher
        #: ARC 047. Optional on the same argument. A build without it takes the
        #: reservation and holds no approved order, which is precisely the ARC
        #: 046 state — and `_picture()` reports `fills: null` for it rather than
        #: an empty stop book, because *no fill path* and *a fill path holding
        #: nothing* are two readings (check contract rule 10).
        self._fills = fills
        #: ARC 054. §3:173's onset watch and D3.443's pending-entry book, both
        #: optional on the same argument and for the same reason: `onset: null`
        #: says *this build cannot be told about an onset*, which is a different
        #: fact from *no onset arrived*, and the entries that survive the two are
        #: loose for different reasons.
        self._onset = onset
        self._book = book
        #: ARC 053. §4's pending-timeout poller, optional on the same argument:
        #: `timeouts: null` says *this build does not poll* and is a different
        #: fact from a poller that has run and found nothing due.
        self._timeouts = timeouts
        #: ARC 053 / D3.463. `None` means this build enforces NO signal-age
        #: ceiling, and it is reported as `null` rather than as a number so a
        #: reader cannot mistake *unbounded* for *bounded at something*. `main`
        #: always supplies one; the default exists for the ARC 040 CLI readers.
        self._signal_max_age_s = signal_max_age_s
        #: ARC 057 / I1 ARC C2. OPTIONAL, so a build without §14's producers
        #: still serves the `price` verb; such a build publishes to §5:322's ring
        #: and stamps NO freshness, which `UncertaintyWatch.record` reports as
        #: zero observations rather than as a fresh feed.
        self._uncertainty = uncertainty
        #: ARC 055. §5:322's price ring and the driver that polls it, both
        #: optional on the argument every collaborator above is optional on:
        #: `stops: null` says *this build cannot maintain a stop* and is a
        #: different fact from a build that polled and found no breach. That
        #: distinction is D3.451 itself — an armed stop nothing drives reads
        #: identical to an armed stop nothing has breached, and telling them
        #: apart is why this arc exists.
        self._prices = prices
        self._stopwatch = stopwatch
        #: ARC 058 / I1 ARC D. §4's close and its `closed` channel, both optional
        #: on the argument every collaborator above is optional on: `closing:
        #: null` says *this build cannot reconcile a closing fill* and is a
        #: different fact from a build that reconciled nothing because nothing
        #: closed. Those two are D3.481 and ARC 058 / S1 exactly.
        self._closing = closing
        self._closed_feedback = closed_feedback

    def handle(self, item: object) -> None:
        """The loop's per-item callback. Writes the reply, then unlinks the command."""
        if not isinstance(item, RawCommand):
            raise TypeError(
                f"{SITE}: the loop handed the handler a {type(item).__name__}, "
                "not a RawCommand — nothing else may be submitted to this loop"
            )
        reply = self._reply_for(item)
        self._write_reply(str(reply["id"]), reply)
        try:
            item.path.unlink()
        except OSError:
            # Unlinked already, or a directory that vanished under us. The reply
            # is on disk either way, and re-serving a command whose reply exists
            # is the lesser fault: the reply is idempotent by id.
            pass

    # -- verb dispatch ------------------------------------------------------

    # R0911 (too-many-return-statements): the returns ARE the fail-closed ladder
    # — unreadable file, bad JSON, wrong top-level type, wrong schema, unknown
    # verb, and the dispatch itself. Collapsing them into one exit would mean one
    # reason string covering six distinguishable refusals, and check contract v2
    # §11 makes the REASON the assertion.
    # pylint: disable=too-many-return-statements
    def _reply_for(self, command: RawCommand) -> dict[str, Any]:
        """One reply dict for one command. Every path returns; none raises."""
        fallback_id = command.path.stem
        if command.read_error:
            return self._refuse(fallback_id, "", command.read_error)
        try:
            raw = json.loads(command.blob.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return self._refuse(
                fallback_id, "", f"{command.path.name} is not valid JSON: {exc!r}"
            )
        if not isinstance(raw, dict):
            return self._refuse(
                fallback_id,
                "",
                f"{command.path.name}: top level is {type(raw).__name__}, "
                "expected an object",
            )
        command_id = str(raw.get("id") or fallback_id)
        verb = str(raw.get("verb") or "")
        schema = raw.get("schema")
        if schema != COMMAND_SCHEMA:
            return self._refuse(
                command_id,
                verb,
                f"command schema {schema!r} != this build's {COMMAND_SCHEMA} — "
                "refusing to read fields into a meaning they may not have",
            )
        if verb not in VERBS:
            return self._refuse(
                command_id,
                verb,
                f"unknown verb {verb!r}; this build serves {list(VERBS)}",
            )
        try:
            return self._dispatch(command_id, verb, raw)
        except RecoveryError as exc:
            return self._refuse(command_id, verb, str(exc))
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return self._refuse(
                command_id, verb, f"{type(exc).__name__}: {exc} (contained)"
            )

    def _dispatch(
        self, command_id: str, verb: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        """The three verbs. Split out so `_reply_for` holds only the refusals."""
        if verb == VERB_STATUS:
            beat = self._loop.last_beat
            return self._reply(
                command_id,
                verb,
                accepted=True,
                reason=(
                    f"{SITE}: tick {self._loop.tick_count}, heartbeat seq "
                    f"{self._loop.heartbeat_seq}, last beat ts "
                    f"{None if beat is None else beat.ts}, registrations "
                    f"{list(self._loop.registry.registered())}, in flight "
                    f"{[list(pair) for pair in self._loop.in_flight_holders()]}, "
                    f"go armed "
                    f"{[[s, c, round(e, 3)] for s, c, e in self._loop.go_armed()]}, "
                    f"go timeouts {len(self._loop.go_timeouts())}, "
                    f"go timeout knob {self._loop.go_timeout_s}, "
                    f"sender handoffs {self._loop.sender.handoffs}"
                ),
                # ARC 046. The LIVE §11.3 aggregate and the §5:322 dispatch
                # counters, in the daemon's own published snapshot. Structured
                # fields rather than more prose in `reason`: the gate has to
                # read committed BEFORE and AFTER a completion and compare two
                # numbers, and a number parsed back out of a sentence is a
                # number that drifts with the sentence.
                extra=self._picture(),
            )
        if verb == VERB_PRICE:
            return self._price(command_id, raw)
        strategy_id = str(raw.get("strategy_id") or "")
        if not strategy_id:
            return self._refuse(
                command_id, verb, f"{verb!r} requires a non-empty strategy_id"
            )
        if verb == VERB_REGISTER:
            row = self._loop.admit(strategy_id, now=time.time())
            return self._reply(
                command_id,
                verb,
                accepted=True,
                reason=(
                    f"{SITE}: {strategy_id!r} admitted into the LIVE registry at "
                    f"slot {row.slot} — §4:266-268's slot, held by this process "
                    "for as long as it runs"
                ),
            )
        client_order_id = str(raw.get("client_order_id") or "")
        if not client_order_id:
            return self._refuse(
                command_id, verb, f"{verb!r} requires a non-empty client_order_id"
            )
        if verb == VERB_RESOLVE:
            outcome = str(raw.get("outcome") or "")
            accepted, reason = self._loop.resolve_in_flight(
                strategy_id, client_order_id, outcome
            )
            return self._reply(command_id, verb, accepted=accepted, reason=reason)
        if not self._loop.registry.is_registered(strategy_id):
            return self._refuse(
                command_id,
                verb,
                f"{strategy_id!r} is not registered in this Risk Engine — "
                "§4:266-268 keys every piece of Limiter state to a registration, "
                "so there is no slot for an order to be in flight in",
            )
        if verb == VERB_RESERVE:
            return self._reserve(command_id, strategy_id, client_order_id, raw)
        accepted, reason = self._loop.take_in_flight(strategy_id, client_order_id)
        if accepted:
            self._loop.hand_to_sender((strategy_id, client_order_id))
        return self._reply(command_id, verb, accepted=accepted, reason=reason)

    def _price(self, command_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        """§5:322's price, published into the ring the TICK reads. Never raises.

        Deliberately NOT strategy-scoped (see `VERB_PRICE`): a price is a fact
        about an instrument. Every refusal below is a REPLY with a reason, never
        an exception, for `CommandHandler`'s own stated reason — a command that
        could kill this process would be a remote kill switch on the one process
        §12.1:604 has the Sentinel watching.
        """
        if self._prices is None:
            return self._refuse(
                command_id,
                VERB_PRICE,
                f"{SITE}: this build holds no §5:322 price ring, so a price has "
                "nowhere to land and no stop could be maintained against it",
            )
        symbol = str(raw.get("symbol") or "")
        if not symbol:
            return self._refuse(
                command_id, VERB_PRICE, f"{VERB_PRICE!r} requires a non-empty symbol"
            )
        raw_price = raw.get("price")
        try:
            price = float(cast(Any, raw_price))
        except TypeError, ValueError:
            return self._refuse(
                command_id,
                VERB_PRICE,
                f"{VERB_PRICE!r} for {symbol!r} carries price {raw_price!r}, which "
                "is not a number — a stop maintained against it would sit at an "
                "undefined level (§4's conversion needs a price scale)",
            )
        if not math.isfinite(price) or price <= 0.0:
            return self._refuse(
                command_id,
                VERB_PRICE,
                f"{VERB_PRICE!r} for {symbol!r} carries price {price!r}, which is "
                "not a positive finite number. §4 anchors and breaches stops "
                "against real prices; refusing rather than ratcheting on a NaN",
            )
        try:
            tick = self._prices.publish(symbol, price)
        except PriceRingFull as exc:
            return self._refuse(command_id, VERB_PRICE, str(exc))
        # ARC 057 / I1 ARC C2, D3.453. The same publication, STAMPED, so §6.4's
        # detector can age it. It runs AFTER the ring accepted the price and not
        # before: a sixth symbol is refused above, and a freshness stamp for a
        # price the ring rejected would make the feed look alive for a symbol no
        # stop is being maintained on — D3.451's shape, one layer over.
        if self._uncertainty is not None:
            self._uncertainty.observe_price(symbol, datetime.now(UTC))
        return self._reply(
            command_id,
            VERB_PRICE,
            accepted=True,
            reason=(
                f"{SITE}: {symbol} @ {tick.price} published to §5:322's price "
                f"ring at seq {tick.seq}; the next tick maintains and tests every "
                "stop on this symbol against it (§4:190-196)"
            ),
        )

    def _reserve(
        self,
        command_id: str,
        strategy_id: str,
        client_order_id: str,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        """ARC 046. §3's *taken at approval*, through the REAL ledger.

        Reaches money's ACCOUNTING and not the venue: no order is placed and
        nothing is sent. It exists because the release this arc wires has to
        have something to release, IN THIS PROCESS — a cancel dispatch proven
        against a ledger a test constructed would be one more library proof, and
        that is the gap (ARC 038) rather than the fix.
        """
        if self._reservations is None:
            return self._refuse(
                command_id,
                VERB_RESERVE,
                f"{VERB_RESERVE!r} needs §11.3's reservation ledger and this "
                "build was constructed without one",
            )
        # ARC 053 / D3.463. AN ABSENT SIGNAL INSTANT READS STALE, NOT NOW.
        #
        # This line used to be `signal_ts=float(raw.get("signal_ts") or
        # time.time())`, and the fallback is the whole defect: a GO that carried
        # no instant was DATED AT THE MOMENT IT HAPPENED TO ARRIVE, so it could
        # never be stale — the one input in this tree that got fresher by being
        # unreadable. §17 is stale-until-proven-fresh, and the absence of a stamp
        # is the strongest reason to distrust one, not a licence to mint it.
        #
        # It is a REFUSAL here rather than a sentinel value passed inward
        # (`0.0`, `-inf`) because §3's order is what a later fill converts
        # against: a `ProposedOrder` carrying a fabricated instant would travel
        # into the ledger, into `join.py`'s trade record and into §12.10's rows,
        # and every reader downstream would see a number nobody sent.
        if raw.get("signal_ts") is None:
            return self._refuse(
                command_id,
                VERB_RESERVE,
                f"{client_order_id!r} carries NO signal_ts. §17 is "
                "stale-until-proven-fresh: an absent signal instant reads STALE, "
                "never NOW, so §3 refuses the reservation rather than dating the "
                "signal at the instant the command happened to arrive "
                "(CHECK-DEBT D3.463). Nothing was taken and nothing was sent",
            )
        try:
            order = ProposedOrder(
                client_order_id=client_order_id,
                strategy_id=strategy_id,
                symbol=str(raw.get("symbol") or ""),
                side=Side(str(raw.get("side") or Side.LONG.value)),
                qty=int(raw.get("qty") or 0),
                margin_per_contract=float(raw.get("margin_per_contract") or 0.0),
                stop_ticks=int(raw.get("stop_ticks") or 0),
                stop_mode=StopMode(str(raw.get("stop_mode") or StopMode.FIXED.value)),
                signal_ts=float(raw["signal_ts"]),
                # ARC 056 / D3.474. §4:190-196's SECOND distance, which a
                # trailing stop needs and a fixed one has no use for.
                #
                # ABSENT MEANS ABSENT — `None`, never a number. Every other
                # numeric field above coalesces a missing value to zero, and
                # that is right for them because zero qty and zero margin are
                # refused downstream on their own terms. A trail distance is
                # different: `or 0` would turn a GO that sent no trail into one
                # that sent an invalid trail, and the two refusals are not the
                # same sentence — `_valid_distance` would report "0 is not a
                # whole number of ticks" for a field the strategy never sent.
                # The same reasoning ARC 053 applied to `signal_ts` one field up.
                #
                # NOT DEFAULTED FROM `stop_ticks` either. §4:187 makes the trail
                # the STRATEGY's per-signal choice and
                # `nix_strategy_contract_v1.1.md`:175 already carries it on the
                # GO, so a value invented here would be this daemon making a
                # risk decision the strategy is the authority for — and it would
                # make every malformed trailing order look armed, which is the
                # one outcome worse than refusing it.
                trail_ticks=(
                    None if raw.get("trail_ticks") is None else int(raw["trail_ticks"])
                ),
            )
        except (TypeError, ValueError) as exc:
            return self._refuse(
                command_id,
                VERB_RESERVE,
                f"{client_order_id!r} is not a readable §3 order: "
                f"{type(exc).__name__}: {exc}",
            )
        # ARC 053 / D3.463. The age check runs BEFORE the take, so a stale signal
        # costs nothing: §3's *taken at approval* has not happened yet and there
        # is no reservation to unwind.
        if self._signal_max_age_s is not None and (
            stale := signal_age_refusal(order, self._signal_max_age_s)
        ):
            return self._refuse(command_id, VERB_RESERVE, stale)
        try:
            reservation = self._reservations.take(order, time.time())
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            # The ledger's OWN refusals (duplicate, sub-minimum margin, …), each
            # of which already names its spec coordinate. Re-raising would kill
            # a tick over an accounting refusal; the reason is the assertion
            # (check contract v2 §11), so it is carried through verbatim.
            return self._refuse(
                command_id,
                VERB_RESERVE,
                f"§11.3's ledger refused the reservation: {type(exc).__name__}: {exc}",
            )
        # ARC 047. §3's approval is not finished when the capital is taken: the
        # ORDER must be held (it carries §4's stop distance, the whole input to
        # the conversion a later fill performs) and the trade<->order join must
        # be minted. Ordered AFTER the take so the take's own refusals — the
        # duplicate `client_order_id`, the sub-minimum margin — keep answering
        # first and unchanged, which is what makes ARC 046's cancel drive
        # byte-for-byte the same drive it was.
        approved = ""
        if self._fills is not None:
            try:
                self._fills.approve(order)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                # FAIL CLOSED AND LOUD. The reservation is TAKEN and the order is
                # NOT held, so a fill for it can never be handled — the sink
                # refuses an unapproved fill because §2A's `on_fill` carries no
                # side. Reported as a REFUSAL naming that exact state rather than
                # as an acceptance, because an `accepted: true` over an order this
                # process cannot ever open is the silent half of a fail-open.
                self._fills.approval_failures.append(client_order_id)
                return self._refuse(
                    command_id,
                    VERB_RESERVE,
                    f"§3 reservation {reservation.reservation_id} IS TAKEN "
                    f"({reservation.margin} committed) but the approval could "
                    f"not be completed: {type(exc).__name__}: {exc}. This order "
                    "holds capital and can NEVER be filled by this process — §4 "
                    "converts the SIZER's stop distance and there is no held "
                    "order to convert from. Resolve or cancel it",
                )
            trail = (
                ""
                if order.trail_ticks is None
                else f", trail_ticks={order.trail_ticks}"
            )
            approved = (
                f"; the order is HELD (stop_ticks={order.stop_ticks}{trail}, "
                f"{order.stop_mode.value}) and trade "
                f"{self._trade_id_for(client_order_id)!r} is minted, so a §2A "
                "on_fill for it can arm a stop and open a position"
            )
        reply = self._reply(
            command_id,
            VERB_RESERVE,
            accepted=True,
            reason=(
                f"{SITE}: §3 reservation {reservation.reservation_id} taken at "
                f"approval for {client_order_id!r} — "
                f"{reservation.margin} of margin COMMITTED in this process's "
                f"live ledger; nothing was placed and nothing was sent{approved}"
            ),
        )
        reply.update(self._picture())
        return reply

    def _trade_id_for(self, client_order_id: str) -> str:
        """The `trade_id` minted for this order, or `""`. Evidence, never a hot path."""
        if self._fills is None:
            return ""
        origin = self._fills.origins.origin_for_order(client_order_id)
        return "" if origin is None else origin.trade_id

    def _picture(self) -> dict[str, Any]:
        """The live §11.3 aggregate + §5:322 dispatch counters. DERIVED, never cached.

        `None` where the collaborator is absent, so a build without a ledger
        reads as *cannot say* rather than as *committed nothing* — check
        contract rule 10 one layer down: an aggregate reported as 0.0 by a
        process that has no ledger is a safety property certified over an
        unavailable subject.
        """
        return {
            "committed": (
                None
                if self._reservations is None
                else self._reservations.total_reserved()
            ),
            "outstanding": (
                None
                if self._reservations is None
                else len(self._reservations.outstanding())
            ),
            "completions": (
                None if self._dispatcher is None else self._dispatcher.record()
            ),
            # ARC 047. The §4/§3 fill state — every armed stop and every
            # published §3 row, ENUMERATED. `None` where the collaborator is
            # absent, so a build with no fill path reads as *cannot say* rather
            # than as *no positions and no stops* (check contract rule 10: a
            # safety property certified over an unavailable subject is not
            # proven, and "there is no unprotected position" is exactly such a
            # property).
            "fills": None if self._fills is None else self._fills.record(),
            "picture": (None if self._fills is None else self._fills.picture_record()),
            # ARC 053. §4's pending-timeout resolution, as the RUNNING process
            # reports it. `None` where the poller is absent — *this build does
            # not poll* and *this build polled and nothing was due* are two
            # readings, and the zombie this arc exists to kill lives in the gap
            # between them.
            "timeouts": None if self._timeouts is None else self._timeouts.record(),
            # ARC 054. §3:173's onset sweep as the RUNNING process reports it,
            # and the pending-entry set it sweeps — both ENUMERATED, for the
            # reason `fills` is: the safety question is *did the sweep reach
            # every one of these and leave the exits alone*, and no pair of
            # totals can answer it. `None` where absent, so *this build has no
            # onset surface* stays distinguishable from *no onset arrived*.
            "onset": None if self._onset is None else self._onset.record(),
            "pending_entries": None if self._book is None else self._book.record(),
            # ARC 055. §4:190-196's trail and the breach->flatten path as the
            # RUNNING process reports it: what it polled, what it maintained,
            # what breached, what it suppressed as already-in-flight, and what
            # the BROKER recorded on the other side of the send. `None` where
            # absent, for the reason every sibling above is `None` where absent.
            "stops": (None if self._stopwatch is None else self._stopwatch.record()),
            # ARC 057 / I1 ARC C2. §14's four uncertainty producers as the
            # RUNNING process reports them: the conditions it is accountable
            # for (DERIVED, with the debt row that named each), what it
            # detected, what it suppressed as already-fired, the reconciliation
            # windows it holds, the open positions it CANNOT price, the refused
            # fills it could not CLASSIFY, and what the BROKER recorded on the
            # far side of every send. `None` where absent, for the reason every
            # sibling above is `None` where absent — *this build has no §14
            # producers* must stay distinguishable from *nothing was uncertain*.
            "uncertainty": (
                None if self._uncertainty is None else self._uncertainty.record()
            ),
            # ARC 058 / I1 ARC D. §4's CLOSE as the RUNNING process reports it —
            # every trade closed off a flatten's own exec report, with §3's
            # published open margin AFTER the release and the stop each retired.
            # `None` where absent for the reason every sibling here is `None`
            # where absent: *this build cannot reconcile a closing fill* and
            # *nothing closed* are two readings, and check contract rule 10 makes
            # the difference between cannot-measure and pass.
            "closing": (None if self._closing is None else self._closing.record()),
            "closed_feedback": (
                None
                if self._closed_feedback is None
                else self._closed_feedback.record()
            ),
            "prices": (
                None
                if self._prices is None
                else {
                    "symbols": list(self._prices.symbols()),
                    "published": self._prices.published(),
                    "head": {
                        symbol: head.price
                        for symbol in self._prices.symbols()
                        if (head := self._prices.head(symbol)) is not None
                    },
                }
            ),
        }

    # -- reply plumbing -----------------------------------------------------

    def _reply(
        self,
        command_id: str,
        verb: str,
        *,
        accepted: bool,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """The reply record. `tick` and `seq` are read at reply time, from the loop."""
        reply = {
            "schema": REPLY_SCHEMA,
            "id": command_id,
            "verb": verb,
            "accepted": accepted,
            "reason": reason,
            "tick": self._loop.tick_count,
            "seq": self._loop.heartbeat_seq,
            "pid": os.getpid(),
        }
        if extra:
            reply.update(extra)
        return reply

    def _refuse(self, command_id: str, verb: str, why: str) -> dict[str, Any]:
        """A refusal. Always carries a reason; `accepted: false` alone says nothing."""
        return self._reply(command_id, verb, accepted=False, reason=f"{SITE}: {why}")

    def _write_reply(self, command_id: str, reply: dict[str, Any]) -> None:
        """`<id>.reply.json`, written atomically. A reader sees all of it or none."""
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in command_id)
        _write_json_atomically(self._outbox / f"{safe}.reply.json", reply)


# R0903 (too-few-public-methods): TWO public verbs and both are the contract —
# the booking itself and the ingress wrapper that schedules it. A third added to
# clear a threshold would widen the one surface in this process that can write to
# §9's evidence plane.
# pylint: disable=too-few-public-methods
class Plane1Booker:
    """ARC 042. §9's ENQUEUE for §12.10's `go_timeout` row, and nothing else.

    CHECK-DEBT **D3.425**, and the finding it discharges stated exactly:
    `_break_go_deadlocks` fires, releases the §4:208 lock and writes a RUNTIME
    RECORD — and a runtime record is not §9's evidence plane. §12.10 puts
    GO-timeout on **Plane 1** because the firing GATES MONEY (the GO is treated
    as DENIED and the strategy reset to flat-and-free), so the transition owes a
    row in the append-only log and had none.

    WHAT THIS IS NOT, STATED FIRST
    ------------------------------
    It is not a second writer. §9 makes the **Limiter** the sole Plane-1 writer
    and this process IS the Limiter (§2:42); wiring it to write is making the
    first and only intended writer function. Proving that no OTHER process can
    write is the sole-writer ENFORCEMENT property (I8) and is a different arc —
    it could not be enforced against a writer that did not yet write.

    It is not the shared-pool writer either. §9's path is *enqueue -> durable
    local WAL -> shared-pool writer -> group-commit to Postgres*, and this
    object owns the FIRST ARROW ONLY. `nixrisk.wal.GroupCommitWriter` and
    `nixrisk.plane1_sink.Plane1PostgresSink` own the rest, out of this process,
    and nothing here starts them. A row that reached the WAL and not Postgres is
    §12.4's buffering working, not this object failing.

    It books ONE event type. Every other §9 row this daemon could owe —
    accepted, denied, filled, closed, reservation, cancel, HALT, operator action,
    strategy lifecycle, cold start — is STILL UNWRITTEN by this process. That is
    named debt, not a silent gap.

    EXACTLY ONCE, WITHOUT A RETRY (§4:240-241)
    ------------------------------------------
    One firing is one enqueue is one row. The breaker is idempotent from the
    loop's side — it pops the stamp after it fires, so a strategy fires once —
    but this booker reads a LEDGER (`LimiterLoop.go_timeouts()`), and a ledger is
    re-read every tick. So each firing is keyed by
    `(strategy_id, client_order_id, fired_tick)` and the key is recorded
    **BEFORE** the enqueue is attempted, never after. That order is the §4:240-241
    rule expressed in code: a booking that raised is NOT retried on the next
    tick, because a retry is how one intended row becomes two. The failure is
    COUNTED and reported in the stop record instead, which is the loud half of
    directive 4 — a refused booking that nothing recorded would be the same
    silence D3.425 named, one layer down.

    WHY THE INGRESS, AND WHY ONE TICK LATE
    --------------------------------------
    `nixrisk.loop.LimiterLoop.tick` runs `_run_ingress` -> `_drain` ->
    `_break_go_deadlocks` -> `_beat_if_due`, and that ORDER is an invariant of
    the loop (a breaker that ran before the drain would false-release a GO whose
    terminal feedback was sitting in the same inbox). The ingress callback is the
    one hook this process owns inside the tick, so booking there books the
    PREVIOUS tick's firings. The lateness is bounded by one tick interval and is
    stated rather than hidden; the alternative is a hook inside the loop, and
    §4:210-212's breaker is risk-path source this arc deliberately did not touch.

    Nothing is lost to the ledger's bound: `LimiterLoop._go_timeouts` is a deque
    of `FAULT_LEDGER_MAX`, at most one firing per registered strategy can be
    appended between two consecutive ingress calls (the breaker is keyed by
    `strategy_id`), and `main` books ONCE MORE after `run()` returns so the last
    tick's firing is not left behind by the stop.
    """

    def __init__(self, loop: LimiterLoop, wal: Plane1Wal) -> None:
        self._loop = loop
        self._wal = wal
        self._booked: set[tuple[str, str, int]] = set()
        self.firings_seen = 0
        self.booked = 0
        self.refused = 0
        self.last_error = ""

    def book_new_firings(self) -> int:
        """Enqueue a §12.10 row for every firing not booked yet. NEVER RAISES.

        Returns the number booked by THIS call. Contained for the reason
        `CommandHandler.handle` is: this runs inside the tick, and an exception
        escaping here would kill the process §12.1:604 has the Sentinel watching
        — turning a persistence fault into a trading outage, which is precisely
        the conflation §12.4 forbids (*"degraded persistence != degraded
        trading"*).
        """
        booked = 0
        for row in self._loop.go_timeouts():
            key = (row.strategy_id, row.client_order_id, row.fired_tick)
            if key in self._booked:
                continue
            # Recorded BEFORE the attempt. See the class docstring: this is
            # §4:240-241's no-resend rule, and reversing the two lines would
            # make a transient WAL error into a duplicate row.
            self._booked.add(key)
            self.firings_seen += 1
            try:
                self._wal.enqueue(self._row_for(row))
                # §9's word is DURABLE. `enqueue` returns from an unbuffered
                # `write(2)`, which survives a SIGKILL and not a power cut;
                # `sync_to_disk` is the boundary that makes the row evidence.
                # It costs one fsync PER FIRING, and a firing is by definition
                # exceptional — §11.6 keeps GROUP-COMMIT off the hot path, and
                # this is neither a group commit nor the entry pathway.
                self._wal.sync_to_disk()
                self.booked += 1
                booked += 1
            except (WalError, OSError) as exc:
                self.refused += 1
                self.last_error = (
                    f"{SITE}: §12.10 go_timeout row for {row.strategy_id!r}/"
                    f"{row.client_order_id!r} fired on tick {row.fired_tick} was "
                    f"NOT booked to Plane 1: {type(exc).__name__}: {exc}. "
                    "§4:240-241 forbids the retry, so this firing has no row and "
                    "this counter is the only thing that says so"
                )
        return booked

    def _row_for(self, firing: GoTimeout) -> EventRow:
        """One `GoTimeout` observation -> one §9 `EventRow`.

        §9 requires timestamp + strategy_id + trade_id + reason on every row.

        * `ts` is the WALL CLOCK at booking, because `occurred_at` is a
          timestamptz and `GoTimeout` deliberately carries no wall-clock reading
          (its `elapsed_s` is the loop's own monotonic, which is the whole point
          of that record). The loop-clock truth is not discarded: `fired_tick`,
          `admitted_tick`, `elapsed_s` and `timeout_s` ride in `fields`, so a
          reader can tell the two clocks apart instead of being handed one
          number that silently mixes them.
        * `trade_id` is ABSENT and that is a measurement, not an omission. The
          Limiter mints a trade id at OPEN (§4); a GO that never received
          terminal feedback never opened, so there is no trade. The seam types
          it optional for exactly this case and the sink writes the schema's
          documented `'-'` sentinel, which is a different fact from a lost id.
        * `reason` is the breaker's OWN §4:210-212-citing sentence, not the
          string `"go_timeout"` — the event TYPE already carries that, and check
          contract v2 rule 11 makes the reason the assertion.
        """
        return EventRow(
            kind=EventKind.GO_TIMEOUT,
            ts=time.time(),
            strategy_id=firing.strategy_id,
            reason=firing.reason,
            trade_id=None,
            fields={
                "client_order_id": str(firing.client_order_id),
                "admitted_tick": str(firing.admitted_tick),
                "fired_tick": str(firing.fired_tick),
                "elapsed_s": f"{firing.elapsed_s:.6f}",
                "timeout_s": f"{firing.timeout_s:.6f}",
                "released": str(firing.released).lower(),
                "resent": str(firing.resent).lower(),
                "booked_by": SITE,
            },
        )

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Wrap the loop's ingress so the booking runs first, inside the tick.

        Composed rather than folded into `Inbox.drain`: the inbox reads commands
        and this writes evidence, and one object doing both would be one place to
        break two unrelated contracts.
        """

        def _ingress(tick: int) -> object:
            self.book_new_firings()
            return inner(tick)

        return _ingress

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. Read by `checks/check_go_timeout.py`.

        Counters, not a boolean: *fired and booked*, *fired and refused* and
        *never fired* must be three readings. `wal_enqueued` / `wal_durable` come
        off the WAL OBJECT rather than being re-counted here, so a booker that
        thought it wrote and a WAL that did not are visibly different.
        """
        return {
            "wal_path": str(self._wal.path),
            "firings_seen": self.firings_seen,
            "booked": self.booked,
            "refused": self.refused,
            "wal_enqueued": self._wal.enqueued,
            "wal_durable": self._wal.durable,
            "wal_state": self._wal.state.value,
            "last_error": self.last_error,
        }


# ===========================================================================
#  ARC 053 — §4's PENDING-TIMEOUT RESOLUTION: A POLL, AND IT QUERIES.
#
#  THE SAFETY SPINE OF THIS ARC, stated where the code is. §4 "Failure
#  resolution": a pending order past its ack deadline is resolved by
#  `query_order_status` and **NEVER by an auto-resend**. The failure mode a
#  resend produces is not a wasted call — it is a SECOND LIVE ORDER at the venue
#  while the first is still working, i.e. a double fill on a single signal, with
#  §3's reservation covering one of them. `place_order` is therefore not merely
#  unused on this path: it is UNREACHABLE from it, and
#  `checks/check_limiter_daemon_dispatch.py` proves that structurally (an AST
#  reachability census from the poll entry point) as well as by driving it.
#
#  WHY A DIRECTORY, AGAIN. `DirectoryStatusQuery` reads `DIR/status/<id>.json`
#  for exactly the reason `CompletionInbox` reads `DIR/completions/` — the
#  module docstring's files-rather-than-ZMQ argument — and for one more: it is
#  the narrowest surface that can answer §4's question. `broker_seam`'s
#  `BrokerOrderPort` can place and flatten; a reservation-release path holding
#  that port would be a second order-placement site, which is precisely what
#  `outcomes.StatusQueryPort`'s own docstring refuses. This class has ONE verb
#  and it opens one file for reading.
#
#  WHAT `filled` DOES, AND WHY IT IS NOT THE FILL CASCADE. §2A's `OrderStatus`
#  carries four fields — `client_order_id`, `terminal`, `state`,
#  `cumulative_qty`. It carries NO `exec_id`, NO `symbol` and NO `price`, and
#  §2A:75's `on_fill` seam requires all three. So a status query answering
#  `filled` CANNOT drive `fills.py`'s cascade without inventing execution data,
#  and driving it from here would create a SECOND conversion site when §4
#  converts ONCE, at the confirmed fill. The answer is therefore HELD — the
#  reservation stays committed — and the conversion happens when the real
#  `on_fill` exec report arrives through the completion path ARC 047 already
#  wired. That is a NAMED hold, counted separately below, because *held because
#  the order is still working* and *held because the venue says it filled and
#  the exec report has not arrived* are two operational facts and one counter
#  over both would hide the second.
# ===========================================================================

#: `*.json` status answers, one per `client_order_id`. Read-only to this process.
STATUS_DIR: Final[str] = "status"

#: ARC 057 / D3.469. §2A's `filled` state, named once. The status seam answers
#: it and `outcomes.py` HOLDS on it (it is not in `DEAD_STATES`: §3 releases a
#: reservation on death and a fill is not death — the fill path owns FILL), so
#: this is the string that opens C2's bounded reconciliation window.
FILLED_STATE: Final[str] = "filled"

#: The `risks/` module carrying §6.4's per-feed stale thresholds. `CONFIG_MODULE`
#: (imported from `nixrisk.loop`) is the LIMITER's; this is a second module this
#: process legitimately READS and never a second authority — `freshness.py`'s
#: `StalenessPolicy` owns every rule over these numbers.
STALENESS_MODULE: Final[str] = "staleness"

#: The seam's own spelling for *this surface has no record of the id* — NOT a
#: statement about the venue (`broker_seam.OrderStatus.state`'s own docstring
#: makes that distinction and it is the difference between holding a reservation
#: and releasing one). An absent file is exactly that case.
STATUS_UNKNOWN: Final[str] = "unknown"


@dataclass(frozen=True)
class StatusReply:
    """One §2A `OrderStatus` answer, as this process reads it off disk.

    STRUCTURAL, not imported. §2A invariant 2 keeps vendor structure below the
    seam, and `outcomes.StatusQueryPort` consumes the answer structurally
    (`.state`) precisely so nothing above the seam has to import `scripts/broker`
    — the same narrowing `fills.py::CancelPort` applies to the same adapter.
    """

    client_order_id: str
    state: str
    terminal: bool = False
    cumulative_qty: int = 0


class DirectoryStatusQuery:
    """§4's status query, served from `DIR/status/`. ONE verb, and it is a READ.

    Structurally an `outcomes.StatusQueryPort`. It cannot place, cancel or
    flatten — there is no such method on it and no object here holds one.

    NEVER RAISES. An unreadable file, malformed JSON or a missing `state` all
    answer `unknown`, which `outcomes.py` routes to HELD: the reservation stays
    committed, which is the direction that over-counts §11.3's Σ and can never
    breach a cap. Raising instead would put an I/O fault on the tick that
    §12.1:604 has the Sentinel watching, turning a filesystem hiccup into a
    trading outage — the conflation §12.4 forbids.
    """

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        #: What the VENUE said, per state. A query surface that cannot say what
        #: it was told can only be believed (`ReservationLedger`'s argument).
        self.answers: dict[str, int] = {}
        #: ARC 057 / D3.469. The LAST state this surface answered PER ORDER.
        #: `answers` above counts states across every order and cannot say which
        #: order the `filled` belonged to, and C2's reconciliation window is
        #: opened for ONE order — so the alternative to this two-line map is a
        #: SECOND query per held record, which would double §4's query count and
        #: make the daemon's own `queries` figure describe the instrument rather
        #: than the venue.
        self.states: dict[str, str] = {}
        self.queries = 0
        self.unreadable = 0
        self.last_error = ""

    def query_order_status(self, client_order_id: str) -> StatusReply:
        """§2A:71 — the status query. NEVER an auto-resend."""
        self.queries += 1
        state = STATUS_UNKNOWN
        terminal = False
        cumulative = 0
        path = self._dir / f"{client_order_id}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                state = str(raw.get("state", STATUS_UNKNOWN))
                terminal = bool(raw.get("terminal", False))
                cumulative = int(raw.get("cumulative_qty", 0) or 0)
        except FileNotFoundError:
            pass  # the documented `unknown` case: no record of this id here
        except (OSError, ValueError, TypeError) as exc:
            self.unreadable += 1
            self.last_error = (
                f"{SITE}: {path.name} could not be read as a §2A status answer "
                f"({type(exc).__name__}: {exc}); answering {STATUS_UNKNOWN!r}, "
                "which §4 resolves by HOLDING the reservation, never by "
                "releasing it and never by resending the order"
            )
        self.answers[state] = self.answers.get(state, 0) + 1
        self.states[client_order_id] = state
        return StatusReply(client_order_id, state, terminal, cumulative)

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block."""
        return {
            "dir": str(self._dir),
            "queries": self.queries,
            "answers": dict(sorted(self.answers.items())),
            "unreadable": self.unreadable,
            "last_error": self.last_error,
        }


# R0902 refused with a reason (INHERITED at ARC 058's greening pass, measured at
# HEAD in a clean worktree): NINE attributes and every one is a fact a gate reads
# out of the runtime record or a collaborator §4's resolution needs by name — the
# outcomes book, the status query, D3.469's window, the poll/resolve/hold/refuse
# counters and the last error. Folding them behind a sub-object would put the
# measured facts one indirection away from the object that produced them, which
# is the argument `loop.SenderThread` records against the same message.
# pylint: disable=too-many-instance-attributes
class PendingTimeoutPoller:
    """ARC 053. The per-tick hook that runs §4's pending-timeout resolution.

    Composed onto the loop's ingress exactly as `Plane1Booker` is, and for the
    same reason: `LimiterLoop.tick` runs `_run_ingress -> _drain ->
    _break_go_deadlocks -> _beat_if_due` and the ingress callback is the one hook
    this process owns inside the tick. §5:322's serial processing then holds for
    the poll too — the query and its resolution happen on the loop's thread,
    between drains, so a release performed here cannot race a completion being
    dispatched in the same tick.

    ORDER, and it is not a preference. The poll runs AFTER the reads, so a
    terminal completion sitting in this tick's directory resolves the order
    BEFORE the poll would ask the venue about it. Polling first would query an
    order whose answer was already on disk, and — worse — would spend a §4 query
    on an order that is about to be resolved by a push event.

    WHAT IT DOES NOT DO: it does not place, resend, cancel or flatten. Its whole
    outbound surface is `DirectoryStatusQuery.query_order_status`, and the sweep
    itself lives in `outcomes.OrderOutcomes.resolve_pending_timeouts` (ARC 044),
    which this class CALLS and does not reimplement.
    """

    def __init__(
        self,
        outcomes: OrderOutcomes,
        query: DirectoryStatusQuery,
        uncertainty: UncertaintyWatch | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._outcomes = outcomes
        self._query = query
        # ARC 057 / D3.469. OPTIONAL, so every reader written against the ARC
        # 053 constructor still builds this poller, and `record()` below reports
        # `reconcile: null` for such a build rather than zero windows — *this
        # build does not hold C2's window* and *it held one and nothing was due*
        # are two readings, and check contract rule 10 lives in the gap.
        self._uncertainty = uncertainty
        self._clock = clock
        self.polls = 0
        self.resolved = 0
        self.held = 0
        self.refused = 0
        self.last_error = ""

    def poll_due(self) -> int:
        """Resolve every overdue order. NEVER RAISES. Returns records produced.

        Contained for the reason `Plane1Booker.book_new_firings` is: this runs
        inside the tick and an exception escaping here would kill the process
        §12.1:604 has the Sentinel watching. A poll that cannot run is a
        reservation held longer than it should be — bounded and safe; a poll that
        kills the daemon is an outage.
        """
        self.polls += 1
        try:
            records = self._outcomes.resolve_pending_timeouts(self._query)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self.last_error = (
                f"{SITE}: §4's pending-timeout sweep raised "
                f"{type(exc).__name__}: {exc}. The sweep is CONTAINED — every "
                "overdue reservation stays COMMITTED, which over-counts §11.3's "
                "Σ and can never breach a cap. §4:240-241 forbids the retry and "
                "nothing here resends"
            )
            return 0
        at = self._clock()
        for record in records:
            disposition = getattr(record.disposition, "value", "")
            if disposition == "released":
                self.resolved += 1
            elif disposition == "refused":
                self.refused += 1
            else:
                self.held += 1
                # ARC 057 / D3.469. A HELD record whose venue answer was
                # `filled` opens C2's BOUNDED reconciliation window. The state
                # is read off the query surface's own per-order map rather than
                # parsed back out of the record's sentence: a producer keyed on
                # prose is a producer a reword silently disables.
                if self._uncertainty is not None:
                    self._uncertainty.note_poll_hold(
                        record.client_order_id,
                        self._query.states.get(record.client_order_id, ""),
                        at,
                    )
        return len(records)

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Wrap the loop's ingress so the poll runs AFTER the reads, same tick.

        ARC 057: and C2's reconciliation-deadline sweep runs immediately after
        the poll, inside the same tick and on the same thread. The order is not a
        preference — the poll is what OPENS a window and the completion dispatch
        earlier in this tick is what CLOSES one, so sweeping last means a window
        an exec report closed in this tick is never judged against its deadline
        in this tick. Sweeping first would make that outcome depend on which of
        two same-tick events the loop happened to reach first.
        """

        def _ingress(tick: int) -> object:
            taken = inner(tick)
            self.poll_due()
            if self._uncertainty is not None:
                self._uncertainty.sweep_reconcile(tick, self._clock())
            return taken

        return _ingress

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. Read by the daemon-dispatch gate.

        Counters, not a boolean, and SIX of them rather than one: *never polled*,
        *polled and nothing was due*, *polled and released*, *polled and held*,
        *polled and refused* and *the query surface itself could not answer* must
        be six readings. `queries` and `due` come off the HANDLER's own counters
        (`outcomes.OrderOutcomes`), not re-counted here, so a poller that thought
        it queried and a handler that did not are visibly different — §7.12
        guard 2 applied to a sweep whose real work happens one call down.

        `resends` is present and is ALWAYS 0. It is not decoration and not a
        placeholder: §4's rule is a NEGATIVE property, and a negative property
        that is nowhere reported cannot be read off a running process. An
        operator asking *did the daemon ever resend?* gets a number.
        """
        return {
            "polls": self.polls,
            "due_seen": self._outcomes.queries,
            "resolved": self.resolved,
            "held": self.held,
            "refused": self.refused,
            "timeouts_released": self._outcomes.timeouts_released,
            "pending_ack_timeout_s": self._outcomes.pending_ack_timeout_s,
            #: §4:240-241. ALWAYS 0, by construction: this path holds no verb
            #: that can place an order. See the class docstring and the gate's
            #: structural reachability census.
            "resends": 0,
            "query": self._query.record(),
            "last_error": self.last_error,
            #: ARC 057 / D3.469. `None` where this build holds no C2 window —
            #: see the constructor. Not a count: an operator's question is
            #: *which orders am I holding a filled-but-undetailed position for*.
            "reconcile": (
                None
                if self._uncertainty is None
                else {
                    "windows_open": sorted(self._uncertainty.windows_open()),
                    "windows_opened": self._uncertainty.windows_opened,
                    "windows_reconciled": self._uncertainty.windows_reconciled,
                }
            ),
        }


# ===========================================================================
#  ARC 054 — §3:173's ONSET SWEEP: THE DAEMON CANCELS, AND IT CANCELS ALL.
#
#  THE SAFETY SPINE OF THIS ARC, stated where the code is. §3:172-174 is ONE
#  sentence: *"Blackout/HALT onset => Limiter cancels all pending ENTRY orders
#  (exits untouched) — no order may fill inside a window it was not approved
#  for."* It has TWO halves and they fail in opposite directions:
#
#  COMPLETE. Every in-scope pending ENTRY must reach the venue as a cancel. An
#  entry the sweep never sees is an entry that FILLS inside a window §3:174 says
#  it was never approved for, with §3's reservation covering a position nobody
#  authorised. That is why `PendingEntryBook` below derives its set from the
#  daemon's OWN order state rather than taking a hand-written list: a list is
#  complete on the day it is written and silently incomplete on every day after.
#
#  SELECTIVE. Only entries. A pending exit and a protective stop are UNTOUCHED
#  (§3:173, §14) — cancelling a stop inside a blackout leaves a REAL position
#  unprotected inside the window, which is the live bug ARC 045 measured, and it
#  must not reappear one layer up. This daemon does not re-decide that: the
#  selection is `flatten.ProtectiveFlatten._classify_for_onset`'s, proven at
#  ARC 045, and `flatten.py`/`blackout.py` are byte-identical across this arc
#  (asserted with `git hash-object`, not claimed). The whole change is that
#  something with a pid now CALLS it.
#
#  WHY THE ENUMERATION HAD TO BE BUILT FIRST (D3.443, D3.349 lineage). Both
#  onset call sites in shipped code — `blackout.py:_fire_onset` and
#  `halt.py:_sweep_pending_entries` — iterate a `PendingEntriesPort`, and the
#  census at ARC 054 / S1 found FIVE `def pending_entries` in the tree: two
#  Protocol declarations and three test doubles. ZERO production producers. The
#  sweep's input was a docstring promise, so no running process could invoke it
#  even where one was constructed — and none was: `HaltFlag` and
#  `BlackoutEvaluator` have no production construction site at all.
#
#  WHY THE DAEMON DETECTS THE EDGE ITSELF, AND WHAT THAT DOES NOT CLAIM.
#  `BlackoutEvaluator._observe_edge` is §6.1's real per-symbol detector and
#  `HaltFlag.set` is §12.5's real global one, and both already fire the sweep on
#  the 0->1 edge only. Neither is constructible here: the first needs §6.4's
#  window cache and the vendored calendar (this process has no poller and no
#  calendar), and the second needs §12.5's cooldown floors, a marker and a
#  Plane-2 emitter — a HALT-flag lifecycle this daemon does not have. So the
#  ONSET ARRIVES FROM OUTSIDE, as a declared state, and `OnsetWatch` holds the
#  prior state and fires on the transition. What is proven here is the DISPATCH:
#  an onset transition reaching this process cancels every in-scope pending
#  entry and leaves the exits alone. What is NOT claimed is that this process
#  DETECTS a blackout window or DECLARES a HALT; both are named debt.
# ===========================================================================

#: ARC 054. §3:173's onset state, read where `completions/` and `status/` are
#: read and for the same reason (see the module docstring): there is no bus in
#: this tree, and an onset path that needed one could not be driven by the
#: out-of-process gate that has to prove the DAEMON sweeps rather than the
#: library. ONE file holding the WHOLE state rather than a queue of events,
#: because an edge is a comparison between two states and a queue of edges
#: would be the producer's opinion about a transition instead of this process's
#: own measurement of one.
ONSET_DIR: Final[str] = "onset"
ONSET_STATE_NAME: Final[str] = "state.json"


@dataclass(frozen=True)
class InFlightOnly:
    """An order holding §4:208's lock with NO reservation. DELIBERATELY role-less.

    ARC 054. `pending_entries()` is COMPLETE over the daemon's whole order state,
    and that state has two records, not one: §11.3's reservation ledger (the
    money) and §4:208's one-in-flight lock (the registry). An order can hold the
    lock without holding a reservation — `reserve` and the in-flight take are two
    commands and nothing forces their order — and such an order can still FILL.
    Omitting it would make the enumeration silently incomplete; declaring it an
    ENTRY would be a claim this process cannot support, because the money record
    that §3 admits an order by (*"approve => TAKE RESERVATION"*) has nothing for
    it.

    So it is handed over carrying NO `role` attribute and NO `symbol`, which is
    not an oversight: `_classify_for_onset` reads `getattr(entry, "role", None)`
    and then asks the ledger, finds nothing, and buckets it `unclassified` with a
    reason that names it — which makes `OnsetCancellation.complete` False and the
    §12.10:753 sweep field report `partial` rather than claiming a clean sweep.
    A fixed list of kinds that meets a kind it does not know must say
    CANNOT-MEASURE, never PASS (the I2/D3.440 lesson, applied to an enumeration).
    """

    client_order_id: str
    strategy_id: str


class PendingEntryBook:
    """ARC 054 / D3.443. The production `pending_entries()`. COMPLETE BY DERIVATION.

    Satisfies `blackout.PendingEntriesPort` and `halt.PendingEntriesPort` — one
    book for both onsets, which is the shape those two ports were deliberately
    given (*"§3:173 is ONE sentence covering blackout and HALT, and two
    incompatible port shapes would guarantee two books"*).

    THE DERIVATION, and why it is a derivation rather than a list
    ------------------------------------------------------------
    §3's pipeline is *"approve => TAKE RESERVATION (proposed margin)"*, so the
    set of orders this process has approved and not yet resolved is EXACTLY the
    TAKEN set of §11.3's ledger — the same set `Σ reservations` is derived from,
    the same set `OrderOutcomes.due_for_status_query` reads, and the same set
    `_classify_for_onset` admits an order by. Every terminal path removes an
    order from it: `on_cancel`, `on_reject`, §4's fill conversion, §4's
    pending-timeout release, and the onset release itself. An order absent from
    it is therefore either never approved or already over, and neither is
    pending.

    The lock record is added to that (see `InFlightOnly`) so the book is complete
    over BOTH of the daemon's order records rather than over the convenient one.

    Nothing is cached. A private copy of the pending set would be a second home
    for a fact §11.3 already owns, and the two could disagree at exactly the
    instant the disagreement leaves an entry working inside a window.
    """

    def __init__(
        self,
        reservations: ReservationLedger,
        approvals: ApprovedOrderBook,
        loop: LimiterLoop,
    ) -> None:
        self._reservations = reservations
        self._approvals = approvals
        self._loop = loop
        #: Observables, for the reason every counter in this file is one: a
        #: component that cannot say what it did can only be believed.
        self.enumerations = 0
        self.last_reserved = 0
        self.last_in_flight_only = 0

    def pending_entries(self) -> tuple[object, ...]:
        """Every pending ENTRY order this process holds. DERIVED on every call."""
        self.enumerations += 1
        entries: list[object] = []
        held: set[str] = set()
        for reservation in self._reservations.outstanding():
            coid = str(reservation.client_order_id)
            held.add(coid)
            # The declared role is ENTRY only where this process's OWN approval
            # book holds a `ProposedOrder` for the id — §3's entry proposal, and
            # the only order kind that reaches `ApprovedOrderBook`. A declared
            # role can only ever EXCLUDE an order from the sweep (see
            # `_classify_for_onset`), never admit one, so declaring it where it
            # is provable and withholding it where it is not costs the sweep
            # nothing and misleads it nowhere.
            if self._approvals.order_for(coid) is None:
                entries.append(
                    InFlightOnly(
                        client_order_id=coid, strategy_id=str(reservation.strategy_id)
                    )
                )
                continue
            entries.append(
                PendingEntry(
                    client_order_id=coid,
                    strategy_id=str(reservation.strategy_id),
                    symbol=str(reservation.symbol),
                    role=OrderRole.ENTRY,
                )
            )
        self.last_reserved = len(held)
        in_flight_only = [
            InFlightOnly(client_order_id=coid, strategy_id=strategy_id)
            for strategy_id, coid in self._loop.in_flight_holders()
            if coid not in held
        ]
        self.last_in_flight_only = len(in_flight_only)
        entries.extend(in_flight_only)
        return tuple(entries)

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block: the SET, not merely its size.

        The pending-entry set is enumerated rather than counted because the
        question a gate has to answer is *did the sweep reach every one of these*,
        and two totals that happen to match cannot answer it.
        """
        entries = self.pending_entries()
        return {
            "enumerations": self.enumerations,
            "reserved": self.last_reserved,
            "in_flight_only": self.last_in_flight_only,
            "entries": [
                {
                    # `getattr` throughout, and not because the fields are in
                    # doubt: `pending_entries()` returns `object` deliberately —
                    # `InFlightOnly` carries no `role` and no `symbol`, which is
                    # the whole mechanism by which `_classify_for_onset` is left
                    # to decide. A reader that assumed the wider shape would be
                    # asserting the narrower one back.
                    "client_order_id": getattr(entry, "client_order_id", None),
                    "strategy_id": getattr(entry, "strategy_id", None),
                    "symbol": getattr(entry, "symbol", None),
                    "role": getattr(getattr(entry, "role", None), "value", None),
                }
                for entry in entries
            ],
        }


# R0903 (too-few-public-methods): TWO verbs and both are §4 fan-out surfaces the
# protective path needs to EXIST before it can be constructed. Neither is on
# §3:173's onset path, which calls `cancel_order` and nothing else.
# pylint: disable=too-few-public-methods
class UnwiredExitSinks:
    """§4's `closed` notify and Scoring hand-off. NOT WIRED — both RAISE.

    ARC 054. `flatten.ProtectiveFlatten` requires a `StrategyExitSink` and a
    `ScoringSink` with no defaults, and its constructor says why: *"a protective
    executor that silently defaulted a sink would fan out into a black hole"*.
    This daemon has no strategy FSM channel and no Scoring process to hand a
    realized figure to, so the honest object is one that REFUSES rather than one
    that absorbs.

    Both verbs raise, and the raise is the point. §3:173's onset sweep never
    reaches either — it issues `cancel_order` and releases reservations — so a
    call landing here means the PROTECTIVE-EXIT path fired, which ARC 054 did not
    wire and CHECK-DEBT records as ARC C's (D3.453 / D3.372 / D3.469). A no-op
    stub would let that path run and report a close nobody was told about; this
    one stops it loudly at the boundary.

    **ARC 058 / I1 ARC D DID NOT MAKE THIS OBSOLETE, AND THE DIFFERENCE MATTERS.**
    This daemon now has a real §4 `closed` channel — `ClosedFeedback` below — and
    it is handed to the CLOSING-FILL path (`nixrisk/closing.py`), which is the
    route the exit report actually takes. The only caller of the two verbs here
    is `ProtectiveFlatten._fan_out`, reached ONLY from `reconcile_and_publish`,
    which awaits the two ASYNC §2A query verbs (`query_positions` /
    `query_balance`) this daemon's stub venue does not have. That path is still
    unreached, so this stub still refuses loudly rather than absorbing — and
    `book_realized` has no Scoring process to reach on ANY path. Replacing this
    with the real sink would claim a fan-out no reconcile in this process can
    perform.
    """

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        """§4 fan-out (a). NOT WIRED in this daemon — raises."""
        raise NotImplementedError(
            f"{SITE}: §4's `closed` notify for trade {trade_id!r} "
            f"(strategy {strategy_id!r}, reason {reason!r}, hard_reset="
            f"{hard_reset}) has NO channel in this process. ARC 054 wired §3:173's "
            "onset entry-cancel, which never reaches this sink; the protective-exit "
            "path that does is ARC C's (CHECK-DEBT D3.453/D3.372/D3.469). Refusing "
            "loudly rather than absorbing a close the owning FSM would never hear"
        )

    # too-many-arguments: the §4 fan-out payload, keyword-only, as the port
    # declares it. Trimming one would change the port, not this stub.
    def book_realized(  # pylint: disable=too-many-arguments
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        """§4 fan-out (d). NOT WIRED in this daemon — raises."""
        raise NotImplementedError(
            f"{SITE}: §4's realized hand-off for {list(closed_trades)!r} "
            f"(delta {realized_delta}, confirmed balance {confirmed_balance}, ts "
            f"{ts}) has NO Scoring process to reach. Same reason as `on_closed`: "
            "ARC 054 wired the onset entry-cancel, not the protective exit"
        )


class OnsetWatch:  # pylint: disable=too-many-instance-attributes
    """ARC 054. §3:173's onset, detected on the EDGE and dispatched to I11's sweep.

    EDGE-TRIGGERED, and that is a property of this object rather than of the
    producer. `state.json` declares the CURRENT state — which symbols are in a
    blackout window and whether HALT is up — and this class holds the PRIOR state
    and fires only on a `False -> True` transition, per symbol for blackout
    (§6.1 windows are per-symbol off the live calendar) and once globally for
    HALT (§12.5 stops every strategy and every symbol). A tick that re-reads the
    same declared state does NOT re-sweep. A `True -> False` transition re-arms,
    so a second entry into the same window fires again.

    IDEMPOTENT IF IT DOES RE-FIRE, and that is not left to chance either: a
    re-fire hands the sweep the pending set as it is THEN, and the entries the
    first sweep cancelled are no longer in it — their reservations were released
    under the onset cause, so `outstanding()` no longer holds them. The second
    sweep therefore cancels nothing and releases nothing. It cannot double-release:
    §11.3's ledger refuses a second release of the same id, and the refusal lands
    on `OnsetCancellation.refusals` rather than raising.

    WHAT THIS DOES NOT CLAIM: that a blackout window or a HALT was DETECTED here.
    §6.1's detector is `blackout.BlackoutEvaluator` (needs §6.4's window cache and
    the vendored calendar) and §12.5's is `halt.HaltFlag` (needs the cooldown
    floors, the marker and a Plane-2 emitter); neither is constructible in this
    process today and both are CHECK-DEBT. This object is the DISPATCH, and the
    dispatch is what I1 is about.

    AN UNREADABLE STATE FILE PRODUCES NO EDGE IN EITHER DIRECTION. It is counted
    and its reason is published (check contract rule 11), and the prior state
    stands. Inventing a clear from an unreadable file would silently disarm the
    watch; inventing an onset from one would sweep every tick against a symbol
    nobody named. Neither is a reading of the file.
    """

    def __init__(
        self,
        directory: Path,
        book: PendingEntryBook,
        sweep: ProtectiveFlatten,
        cancels: RecordedCancels,
        fills: FillPath,
    ) -> None:
        self.directory = directory
        self._book = book
        self._sweep = sweep
        #: §4's live protective state — every armed synthetic stop and every §3
        #: position row. Held here so THIS record can state §3:173's second half
        #: (*"exits untouched"*) as a MEASUREMENT taken across the sweep rather
        #: than as an absence a reader has to infer from another block. A safety
        #: property nobody recorded either side of the event is not proven, and
        #: the one this sweep is most obliged not to break is the one whose
        #: violation looks exactly like nothing happening.
        self._fills = fills
        #: The SAME `RecordedCancels` the executor above holds as its broker,
        #: held here too so this record can publish the venue messages the sweep
        #: produced WITHOUT reaching into the executor's private state. It is a
        #: SECOND instance from the one `IocRemainder` uses, deliberately: §4's
        #: partial-fill remainder cancel and §3:173's onset entry-cancel are two
        #: different facts, and one list over both could not tell a gate which
        #: path issued a given message.
        self._cancels = cancels
        #: The PRIOR declared state — what an edge is measured against.
        self._blackout: set[str] = set()
        self._halted = False
        #: Observables.
        self.polls = 0
        self.unreadable = 0
        self.last_error = ""
        self.blackout_onsets = 0
        self.halt_onsets = 0
        self.re_entries = 0
        #: Every sweep this watch dispatched, in order, as the executor reported
        #: it. Enumerated and not counted: *which* entries were cancelled and
        #: which were excluded, and under which bucket, is the whole safety
        #: question, and a count cannot answer it.
        self.sweeps: list[dict[str, Any]] = []

    def _read(self) -> tuple[set[str], bool] | None:
        """The declared state, or `None` when it cannot be read. Never a guess."""
        path = self.directory / ONSET_STATE_NAME
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError:
            # NOT an error: nothing has declared an onset. This is the boot state
            # and it is a real reading of the surface, not a failure to take one.
            return set(), False
        except (OSError, ValueError) as exc:
            self.unreadable += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        if not isinstance(raw, dict):
            self.unreadable += 1
            self.last_error = f"onset state is {type(raw).__name__}, not an object"
            return None
        declared = raw.get("blackout")
        symbols = {
            str(symbol)
            for symbol in (declared if isinstance(declared, list) else ())
            if str(symbol)
        }
        return symbols, bool(raw.get("halt"))

    def poll(self) -> int:
        """Read the declared state, fire on every EDGE, return how many fired."""
        self.polls += 1
        state = self._read()
        if state is None:
            return 0
        symbols, halted = state
        fired = 0
        # HALT FIRST, and the order is deliberate: §12.5's HALT is GLOBAL and a
        # blackout is one symbol's window, so a tick that declares both should
        # resolve the wider scope first and leave the narrower one nothing to do.
        # Measured either way and it is idempotent (see the class docstring); the
        # order is chosen so the Plane-1 record reads in the order §3 means.
        if halted and not self._halted:
            self._dispatch(TerminalPath.HALT_ONSET, None)
            self.halt_onsets += 1
            fired += 1
        for symbol in sorted(symbols - self._blackout):
            self._dispatch(TerminalPath.BLACKOUT_ONSET, symbol)
            self.blackout_onsets += 1
            fired += 1
        self.re_entries += len(self._blackout - symbols)
        self._blackout = symbols
        self._halted = halted
        return fired

    def _protective(self) -> list[dict[str, Any]]:
        """Every armed protective stop, by the order it protects, with its level.

        ENUMERATED, not counted: §14's question is *does a stop still exist for
        this open position and is it still at the price §4's conversion put it*,
        and a total cannot answer either half.
        """
        return [
            {
                "client_order_id": stop.client_order_id,
                "symbol": stop.symbol,
                "level": stop.level,
            }
            for stop in self._fills.stops.stops()
        ]

    def _dispatch(self, cause: TerminalPath, scope: str | None) -> None:
        """§3:173's sweep, over THIS process's pending-entry book, scoped.

        `scope=None` is GLOBAL (HALT stops every strategy and every symbol,
        §12.5); a symbol is THAT SYMBOL ONLY (§6.1 windows are per-symbol). The
        scope is the executor's argument and NOT a filter applied here, which is
        ARC 045's measured repair: filtering on the handed object's `symbol`
        silently drops an entry that carries none, while the executor scopes off
        `Reservation.symbol`, which always exists.
        """
        pending = self._book.pending_entries()
        protective_before = self._protective()
        # `cast`, and the cast IS the statement: `cancel_entries_on_onset`
        # annotates `Sequence[PendingEntry]` and its body reads every field with
        # `getattr` because ARC 045 measured that the annotation was a promise
        # nothing checked (`blackout.PendingEntriesPort` and
        # `halt.PendingEntriesPort` both declare `Sequence[object]`). This book
        # hands over `InFlightOnly` ON PURPOSE — an order the money record cannot
        # vouch for must reach `_classify_for_onset` and be REFUSED there, loudly,
        # rather than be dropped here to satisfy a type. Silencing the checker at
        # the one call site is honest; narrowing the book to please it would
        # re-create the silent omission D3.443 exists to close.
        outcome = self._sweep.cancel_entries_on_onset(
            cause, cast(Sequence[PendingEntry], pending), scope=scope
        )
        self.sweeps.append(
            {
                "cause": cause.value,
                "scope": scope,
                # §3:173's SECOND half, measured on BOTH sides of the one call
                # that could break it. A protective stop that is in `before` and
                # not in `after` is a REAL position left unprotected inside the
                # window (§14) — the ARC 045 live bug, at the daemon boundary.
                "protective_before": protective_before,
                "protective_after": self._protective(),
                # THE ENUMERATION THE SWEEP WAS HANDED — the completeness claim's
                # left-hand side. A gate compares it to the order state and to
                # what was cancelled; all three must agree or an entry is loose.
                "handed": [
                    str(getattr(entry, "client_order_id", "<unnamed>"))
                    for entry in pending
                ],
                "cancelled": list(outcome.cancelled),
                "released": [res.reservation_id for res in outcome.released],
                "refusals": [
                    getattr(ref, "reason", str(ref)) for ref in outcome.refusals
                ],
                "failures": [list(pair) for pair in outcome.failures],
                "protected": [list(pair) for pair in outcome.protected],
                "out_of_scope": [list(pair) for pair in outcome.out_of_scope],
                "unclassified": [list(pair) for pair in outcome.unclassified],
                "complete": bool(outcome.complete),
            }
        )

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Compose the poll into the tick, AHEAD of the ingress reads.

        Same composition `Plane1Booker.before` and `PendingTimeoutPoller.before`
        use, and the position in the order is the decision: the onset poll runs
        BEFORE this tick's commands are read, so a `reserve` arriving in the same
        tick as a declared onset is taken AFTER the sweep and is refused by the
        gate rather than swept by it. §3:174 is about orders that may fill inside
        the window; an order approved after the onset is a §3 branch-0 question,
        not a sweep question, and conflating them would let the sweep look like a
        gate.
        """

        def _outer(tick: int) -> object:
            self.poll()
            return inner(tick)

        return _outer

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. `check_limiter_daemon_dispatch` reads it."""
        return {
            "dir": str(self.directory),
            "polls": self.polls,
            "unreadable": self.unreadable,
            "last_error": self.last_error,
            "blackout_onsets": self.blackout_onsets,
            "halt_onsets": self.halt_onsets,
            "re_entries": self.re_entries,
            "blackout_now": sorted(self._blackout),
            "halted_now": self._halted,
            "sweeps": list(self.sweeps),
            "cancels_recorded": list(self._sweep_cancels()),
        }

    def _sweep_cancels(self) -> tuple[str, ...]:
        """Every cancel THIS sweep's broker recorded — the venue-message record."""
        return tuple(self._cancels.issued)


class StopWatchDriver:  # pylint: disable=too-many-instance-attributes
    # R0902: eight attributes, and seven of them are OBSERVATIONS a gate reads
    # out of the runtime record — fires, sends, refusals, the last action, the
    # last refusal, the sending thread's native id, and the trigger it fires
    # under. Folding them behind a sub-object would put the measured facts one
    # indirection away from the object that produced them, which is the
    # argument `loop.SenderThread` records against the same message.
    """ARC 055 / I1 ARC C1. §5:322's price poll DRIVEN, and its breach FIRED.

    TWO HALVES ON TWO THREADS, and the split is the whole design:

    * `before()` runs on the HOT LOOP. It polls `StopWatch` — §4:190-196's trail
      and the breach test, cache reads plus §15's `O(positions <= 5)/tick` stop
      evaluation — then hands each detected firing across §5:323's thread
      boundary with an unbounded `put` that never blocks the caller.
    * `send()` runs on the SENDER THREAD. It is where `ProtectiveFlatten.fire`
      is called, and it is there and not on the loop because `fire` takes the §4
      arbitration lock (`request_close` -> `_arbiter`, ARC 038 FC2) and appends a
      §12.10 row. §5:323 is explicit — *"blocking I/O ... hot loop never
      blocks"* — so a fire on the loop would break I9, a DISCHARGED invariant,
      silently.

    WHAT IT DOES NOT DO, STATED FIRST. It does not RECONCILE. C1 ends at *a
    protective flatten was correctly fired and sent*; the closing fill coming
    back, §12.10's `closed` row, the position closing and §3's release are ARC D.
    A flatten sent here is IN FLIGHT until D reconciles it, and `StopWatch`'s
    fire-once mark is what stops the next tick re-firing it in the meantime.

    NO RETRY, NO AUTO-RESEND. A firing that the sender refused or that raised is
    RECORDED (`refusals`, `SenderThread.send_errors`) and never re-queued. §4's
    resend prohibition is the same one `outcomes.py` keeps on the timeout path,
    and the reason is identical: a protective flatten resent on a schedule
    nobody declared is an unbounded stream of venue orders produced by a defect.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        watch: StopWatch,
        exits: ProtectiveFlatten,
        loop: LimiterLoop,
        fills: FillPath,
        in_flight: FlattenInFlightBook | None = None,
    ) -> None:
        self._watch = watch
        self._exits = exits
        self._loop = loop
        self._fills = fills
        #: ARC 058 / I1 ARC D. Where a SENT flatten is recorded so the closing
        #: fill can be matched back to it. OPTIONAL on the argument every
        #: collaborator in this file is optional on: a build without it fires
        #: and sends exactly as C1 shipped, and its closing fill is then
        #: unattributable — the ARC 058 / S1 state, reported rather than absorbed.
        self._in_flight = in_flight
        #: Firings handed across the §5:323 boundary by the hot loop.
        self.fires = 0
        #: Firings the SENDER THREAD actually fired a protective flatten for.
        #: Counted separately from `fires` because check contract rule 2's
        #: argument applies across a thread boundary too: what the loop handed
        #: over and what the sender did with it are two facts.
        self.sends = 0
        #: Firings the sender could not fire, with the reason. NEVER re-queued.
        self.refusals: list[str] = []
        #: The last `FlattenAction` this driver produced, flattened to JSON.
        self.last_action: dict[str, Any] = {}
        #: The native id of the thread the LAST send ran on. Read from inside
        #: the send, so it is the SENDER's id and not the loop's — the ARC 040
        #: `SenderThread.native_id` argument, applied to the work rather than to
        #: the thread. This is the field that proves the send was OFF the hot
        #: path, and it is compared against the loop thread's own id by
        #: `check_stop_maintenance`.
        self.sent_on_native_id: int | None = None

    # -- the hot loop half --------------------------------------------------

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Compose the price poll AHEAD of `inner` inside one tick.

        The position is deliberate and is the mirror of `OnsetWatch.before`'s:
        the poll runs BEFORE the ingress reads, so a stop breached by the price
        already in the ring is detected and enqueued before this tick's commands
        can approve anything new against the capital that breach is about to
        release. §4's protective exit always wins, and running it first is the
        cheapest way to make that ordering a property of the tick rather than a
        race between two readers.
        """

        def _tick(tick: int) -> object:
            self._poll_and_hand(tick)
            return inner(tick)

        return _tick

    def _poll_and_hand(self, tick: int) -> int:
        """Poll, drain, hand to the sender. HOT PATH; never blocks (§5:323).

        `StopWatch.poll` is the part `check_hot_path_purity` traces and is pure.
        The drain is a list swap and `hand_to_sender` is an unbounded
        `queue.Queue.put`, which `SenderThread.hand_off` documents as never
        blocking the caller — §5:323's own words for this boundary.
        """
        self._watch.poll(tick)
        handed = 0
        for firing in self._watch.drain():
            self._loop.hand_to_sender(firing)
            self.fires += 1
            handed += 1
        return handed

    # -- the sender-thread half ---------------------------------------------

    def send(self, payload: object) -> None:
        """Fire the protective flatten for ONE breach. RUNS ON THE SENDER THREAD.

        Ignores anything that is not a `BreachFiring`: §5:323's queue is shared
        with the `go` verb's `(strategy_id, client_order_id)` handoff, and a
        sender that flattened on an unrecognised payload would be firing venue
        orders off a type confusion.
        """
        if not isinstance(payload, BreachFiring):
            return
        self.sent_on_native_id = threading.get_native_id()
        origin = self._fills.origins.origin_for_order(payload.client_order_id)
        if origin is None:
            # §3:159 keys the position table by `trade_id` and §4's close is
            # against a TRADE. An order with no recorded join has no trade to
            # close, so this is refused and NAMED rather than flattened under a
            # guessed identity — the §4 uncertainty case that would cover it is
            # C2's (D3.372/D3.453/D3.469), and inventing it here would be this
            # arc claiming authority it was not given.
            self.refusals.append(
                f"{payload.client_order_id}: breached at {payload.level} with "
                f"price {payload.price} on tick {payload.tick}, but this process "
                "holds no trade<->order join for it, so there is no trade_id to "
                "close under (§3:159). NOT flattened; NOT re-queued"
            )
            return
        # §4's protective close, named by the trigger that caused it, with the
        # two numbers an operator needs to audit the decision without replaying
        # the tick: where the stop was and what price took it out.
        #
        # ARC 058: bound to a name rather than passed inline, because the CLOSING
        # fill's §12.10 row and the strategy's `closed` notify must carry THIS
        # word (§6.1b:352 fixes the word the strategy receives) and deriving it a
        # second time at the close would be the system choosing one fact twice.
        reason = (
            f"protective flatten (trigger={FlattenTrigger.SYNTHETIC_STOP.value}, "
            f"level={payload.level}, price={payload.price})"
        )
        action = self._exits.fire(
            FlattenTrigger.SYNTHETIC_STOP,
            symbol=payload.symbol,
            targets=(
                CloseTarget(
                    trade_id=origin.trade_id,
                    symbol=payload.symbol,
                    strategy_id=origin.strategy_id,
                ),
            ),
            reason=reason,
        )
        self.sends += 1
        # ARC 058 / I1 ARC D. RECORDED AT THE SEND, on the far side of the
        # `fire`, so the book holds only flattens the venue call really reached.
        # The closing fill is the venue's ANSWER and an answer can only be
        # matched against a question somebody recorded asking (§4:214 keys the
        # exec report, not the flatten, so nothing on the wire joins the two).
        if self._in_flight is not None:
            self._in_flight.arm(
                key=payload.client_order_id,
                symbol=payload.symbol,
                trade_id=origin.trade_id,
                strategy_id=origin.strategy_id,
                reason=reason,
                trigger=action.trigger.value,
                at=action.fired_ts,
            )
        self.last_action = {
            "trigger": action.trigger.value,
            "symbol": action.symbol,
            "trade_ids": [target.trade_id for target in action.targets],
            "executed": [outcome.executed for outcome in action.outcomes],
            "dropped": [
                outcome.dropped_reason
                for outcome in action.outcomes
                if outcome.dropped_reason
            ],
            "fired_ts": action.fired_ts,
            "client_order_id": payload.client_order_id,
            "level": payload.level,
            "price": payload.price,
            "tick": payload.tick,
        }

    # -- evidence -----------------------------------------------------------

    def record(self) -> dict[str, Any]:
        """What this driver did, for the out-of-process reader.

        ENUMERATED, not counted, wherever the safety question needs a name: *was
        exactly one protective flatten issued for this breach* is unanswerable
        from a total, which is `FillPath.record`'s own argument for enumerating
        its stops.
        """
        return {
            "polls": self._watch.polls,
            "maintained": self._watch.maintained,
            "breaches": self._watch.breaches,
            "suppressed": self._watch.suppressed,
            "in_flight": list(self._watch.in_flight()),
            "pending": len(self._watch.pending()),
            "fires": self.fires,
            "sends": self.sends,
            "refusals": list(self.refusals),
            "last_action": dict(self.last_action),
            "sent_on_native_id": self.sent_on_native_id,
            "loop_native_id": threading.get_native_id(),
            "sender_native_id": self._loop.sender.native_id,
            "sender_sent": self._loop.sender.sent,
            "sender_send_errors": list(self._loop.sender.send_errors),
            # THE BROKER'S OWN RECORD, read off the object the flatten reached.
            # Not this driver's count of what it asked for: check contract rule
            # 2 — the return value of a mutating call is not a verification, and
            # `sends` is exactly such a return value one layer up.
            "flattened": list(self._exits_broker_flattened()),
        }

    def _exits_broker_flattened(self) -> tuple[str | None, ...]:
        """Every symbol the BROKER recorded a protective flatten for, in order."""
        broker = getattr(self._exits, "_broker", None)
        return tuple(getattr(broker, "flattened", ()))


# ===========================================================================
#  ARC 057 — I1 ARC C2: §14's UNCERTAINTY PRODUCERS. WHAT CANNOT BE PROTECTED
#  IS FLATTENED.
#
#  THE SAFETY SPINE OF THIS ARC, stated where the code is. §14: *every
#  uncertainty resolves toward FLAT; known state beats optimal state*. ARC 055
#  (C1) wired the STOP protective-exit — a breached synthetic stop fires one
#  `ProtectiveFlatten` on §5:323's sender thread. What C1 deliberately did not
#  wire is the OTHER half of §14's sentence: the conditions under which this
#  process holds, or the venue holds, a position it **cannot protect or cannot
#  account for**. Four of those were detected and NAMED by prior arcs, and not
#  one had a producer:
#
#   * D3.453 — an OPEN §3 row whose price feed has gone stale past §12A's
#     `price_stale_ms`. §6.4 has two halves: BLOCK NEW ENTRIES (built — the
#     `StalenessFlagPort` `gate.py` already dispatches) and FLATTEN WHAT IS
#     ALREADY OPEN (this). A stop maintained against a price nobody is sending
#     is not maintenance, and `FlattenTrigger.STALE_PRICE` was a member of the
#     frozen vocabulary that NOTHING in this tree ever fired.
#   * D3.372 — a confirmed fill the execution ledger INGESTED and the ORIGIN
#     WRITE then refused (`positions.py::UntradableSymbol`, §4:198). §3's table
#     and §12.7's mirror read FLAT over a real venue position, so §7:501 prices
#     that exposure at ZERO and the correlation cap ADMITS MORE.
#   * D3.469 — §4's pending-timeout poll answering `filled` on a seam
#     (`broker_seam.OrderStatus`) that carries no `exec_id`, no `symbol` and no
#     `price`, so the §2A:75 cascade cannot run and nothing ever converts.
#   * D3.475 — a fill whose §4 stop conversion was REFUSED. ARC 056 closed the
#     RESERVATION half (the capital comes back, exactly once); the VENUE half is
#     a real position with no synthetic stop behind it.
#
#  ALL FOUR MEASURED ON A LIVE `limiterd` AT THIS ARC'S S1, at 5757f35, before
#  a line of this block existed — an OPEN position with a 3.0s-silent feed
#  (threshold 2.0s) untouched; a fill whose origin write refused leaving
#  `positions=[]` with `write_refusals=1`; a `filled` status answer held across
#  62 queries with the reservation still committed; and an un-armable trailing
#  fill with `arm_refusals=1`, `committed 1000.0 -> 0.0` and no position row.
#  Every one of them ended with the same reading: `flattened = []`.
#
#  THE SPLIT, AND IT IS C1's — DETECTION AND FIRING ARE DIFFERENT OBJECTS.
#  `UncertaintyWatch` holds no broker, no executor and no Plane-1 sink, so *this
#  object cannot send* is a property of the TYPE rather than a rule its caller is
#  asked to keep. `UncertaintyDriver` holds §4's executor and fires — on §5:323's
#  sender thread and never on the loop, because `ProtectiveFlatten.fire` takes
#  the §4 arbitration lock (`request_close` -> `_arbiter`) and appends a §12.10
#  row, and *the hot loop never blocks* (I9, a DISCHARGED invariant).
#
#  ONE EXECUTOR, ONE `_closed` BOOK. The driver is handed the SAME
#  `ProtectiveFlatten` §3:173's onset sweep and C1's stop exit already share, for
#  the reason `FillPath` shares the one ledger: §4's dual-authority arbiter
#  decides precedence by reading and writing ONE `_closed` book, and a second
#  executor would arbitrate against a different book — so *protective always
#  wins* would hold twice, separately, over two halves of one truth.
#
#  NO RETRY, NO AUTO-RESEND, and FIRE-ONCE PER CONDITION. Every one of these
#  conditions PERSISTS: a stale feed stays stale, an un-armable fill stays in
#  `unarmable()`, a refused origin write is never retried. Driven naively that
#  is one venue `flatten` per tick against one position for as long as the
#  condition holds. So the mark is taken in the same pass that ENQUEUES, on the
#  single loop thread, and there is no window between deciding to fire and
#  recording that the fire was decided — C1's discipline, applied to a set of
#  conditions rather than to a stop book.
#
#  WHAT THIS BLOCK DOES NOT DO. It does not RECONCILE. A flatten fired here is
#  IN FLIGHT until ARC D reconciles it: the closing fill coming back, §12.10's
#  `closed` row, the position closing and §3's release are D's, and the
#  fire-once mark is what stops the next tick re-firing in the meantime.
# ===========================================================================


class UncertaintyCondition(enum.Enum):
    """§14's unprotectable-position conditions. A CLOSED, DERIVED set.

    Each member is a CHECK-DEBT row that named a real, measured condition under
    which a position exists and this process can neither protect it nor account
    for it. The set is closed here and asserted by
    `checks/check_uncertainty_flatten.py`, which derives the daemon's producer
    set from this enum and FAILS on a member with no producer — because the
    defect this arc exists to prevent is not a producer that misfires, it is a
    FIFTH condition added later with no producer at all, which is exactly the
    shape all four of these had until this arc.
    """

    #: D3.453 / §6.4's flatten-open half.
    STALE_OPEN = "stale_open"
    #: D3.372 / §4:198's not-tradable fill — the origin write refused.
    NOT_TRADABLE_FILL = "not_tradable_fill"
    #: D3.469 / a `filled` status answer the seam cannot convert.
    UNDETAILED_POLL_FILL = "undetailed_poll_fill"
    #: D3.475 / §4's stop conversion refused — the VENUE half.
    UNARMABLE_FILL = "unarmable_fill"


#: Which CHECK-DEBT row named each condition, and which §-clause makes it a
#: flatten. PUBLISHED in the runtime record rather than kept here alone: the
#: gate's completeness assertion is *the daemon flattens exactly this set*, and
#: a set an outside reader cannot read off the running process is a set the gate
#: would have to restate — the restatement directive 3 forbids.
UNCERTAINTY_ORIGIN: Final[dict[str, str]] = {
    UncertaintyCondition.STALE_OPEN.value: (
        "D3.453 — §6.4's flatten-open half: an OPEN §3 row whose price feed is "
        "past §12A:825 price_stale_ms. §17 is stale-until-proven-fresh"
    ),
    UncertaintyCondition.NOT_TRADABLE_FILL.value: (
        "D3.372 — §4:198: the execution ledger INGESTED the fill and the origin "
        "write REFUSED it, so §3's table reads FLAT over a real venue position"
    ),
    UncertaintyCondition.UNDETAILED_POLL_FILL.value: (
        "D3.469 — §4's status query answered `filled` and §2A's OrderStatus "
        "carries no exec_id/symbol/price, so nothing converts. Held for a "
        "BOUNDED reconciliation window, then flattened"
    ),
    UncertaintyCondition.UNARMABLE_FILL.value: (
        "D3.475 — §4's stop conversion was REFUSED: a real venue position with "
        "NO synthetic stop behind it. ARC 056 closed the reservation half"
    ),
}

#: The §12A feed name whose threshold governs `STALE_OPEN`. Named once so the
#: knob this producer stands on is a single word rather than a literal repeated
#: at the observe site and the read site (`risks/staleness.config.json`'s
#: `price_stale_ms`, read through `freshness.StalenessPolicy`).
PRICE_FEED: Final[str] = "price"

#: A DECLARED NIX ADDITION, not a §12A knob — `risks/limiter.config.json`'s
#: `_derivations` entry carries the whole argument. No default (directive 4).
RECONCILE_WINDOW_KEY: Final[str] = "exec_report_reconcile_ms"


def reconcile_window_from_config(root: Path | None = None) -> float:
    """D3.469's bounded reconciliation window, in SECONDS. No default.

    How long a `filled` status answer whose exec report has not arrived is HELD
    before §14 resolves it toward flat. It is a DECLARED NIX ADDITION for the
    reason `signal_max_age_ms` is: §12A has `PENDING_ACK_TIMEOUT_MS` (how long
    an order may go un-acked) and `FILL_TIMEOUT` (how long a working order may
    take to fill) and NEITHER is this quantity — this one starts *after* the
    venue has already said `filled`, and it bounds how long this process will
    wait for the execution report that the venue has not yet sent.

    A Limiter that invented this window would either flatten a position whose
    exec report was merely delayed (the common case, and the reason the answer
    is HOLD and not an immediate flatten) or hold an unaccountable filled
    position for an interval nobody chose. So it raises rather than defaulting.
    """
    configs = risk_config.load_risk_configs(root)
    return (
        risk_config.knob(configs.modules[CONFIG_MODULE], RECONCILE_WINDOW_KEY) / 1000.0
    )


def staleness_policy_from_config(root: Path | None = None) -> StalenessPolicy:
    """§6.4's per-feed thresholds, from `risks/staleness.config.json`.

    CALLS `freshness.StalenessPolicy.from_values` and re-derives nothing:
    `nixrisk/freshness.py` is byte-identical across this arc and is asserted so
    with `git hash-object`. This function's whole content is *which module's
    values*, because the detector is deliberately constructible without the
    loader (see `from_values`' own docstring) and the daemon is the one caller
    that has a validated config set in hand.
    """
    configs = risk_config.load_risk_configs(root)
    return StalenessPolicy.from_values(configs.modules[STALENESS_MODULE].values)


@dataclass(frozen=True)
class UncertaintyFiring:
    """One detected uncertainty, enqueued for §5:323's sender thread to FIRE.

    A DECLARATION OF DETECTION, never a claim that anything was sent — the same
    distinction `stopwatch.BreachFiring` draws and for the same reason. Carries
    no timestamp: the sender stamps the instant it actually fires, which is the
    instant that matters, and a clock read taken at detection would describe
    when the loop noticed rather than when the venue was called.

    `trade_id` and `strategy_id` are EMPTY STRINGS where this process holds no
    trade<->order join for the position — the D3.372 and D3.469 cases can both
    reach that state. An empty `trade_id` is not a missing field: it routes the
    fire to §4's SYMBOL-only uncertainty path (`fire(symbol=..., targets=())`),
    which `flatten.py` documents as *"a flatten sent to be safe with no known
    trade"* — the branch §4 wrote for exactly this.
    """

    condition: UncertaintyCondition
    #: The FIRE-ONCE key. A `client_order_id` where one exists, else a trade_id.
    key: str
    symbol: str
    trade_id: str
    strategy_id: str
    detail: str
    tick: int


class UncertaintyWatch:  # pylint: disable=too-many-instance-attributes
    # R0902: the injected detector plus the SEVEN observations an out-of-process
    # reader judges this object by — what it scanned, what it detected per
    # condition, what it suppressed as already-fired, the reconciliation windows
    # it is holding, the ones a real exec report closed, and the refused fill
    # dispatches it could NOT classify. Folding any of them behind a sub-object
    # would put a measured fact one indirection away from the pass that produced
    # it, which is `StopWatch`'s own argument against the same message.
    """§14's four uncertainty conditions, DETECTED and ENQUEUED. Never fired.

    Holds no broker, no executor, no Plane-1 sink and no clock of its own — see
    the block comment above: *this object cannot send* is meant to be a property
    of the type. Every instant it needs is passed IN by the caller that already
    owns one, so there is no wall-clock read inside the hot-path scan.

    THE STALE-OPEN SCAN IS THE ONLY PER-TICK HALF, and it is bounded by §15's
    `O(positions <= 5)/tick`: it iterates §3's published position table, which
    §7 scopes to five instruments, and does one `FreshnessTracker.reading` per
    OPEN row — one dict lookup and one subtraction against a held stamp. No I/O,
    no lock, no allocation beyond the firing it may enqueue. The other three
    conditions are EVENT-DRIVEN and are noted at the sites that already observe
    them (the completion dispatch and §4's pending-timeout poll), because a
    per-tick rescan of a condition that fires once would be work §11 puts off
    the path for no gain.

    A FEED NEVER OBSERVED IS NOT FLATTENED, AND THAT NARROWING IS DELIBERATE AND
    PUBLISHED. `FreshnessTracker.reading` answers `CacheState.EMPTY` with
    `blocked=True` for a key nothing has ever been seen on — §17's
    stale-until-proven-fresh, and the right answer for a GATE that is deciding
    whether to admit new capital. It is the WRONG trigger for a flatten in THIS
    build, because CHECK-DEBT D3.473 records that this daemon has no capture
    feed at all: the price arrives over the command ingress or not at all, so
    EMPTY is the state of every symbol in a build with nothing publishing, and
    firing on it would flatten every position in the tree on the ground that the
    feed nobody wired is not sending. That is the absence of a feed reported as a
    position hazard, not §14 protection. So the producer fires on STALE — a feed
    that WAS observed and has since gone quiet past §12A's threshold — and every
    EMPTY-state open position is COUNTED and NAMED in `record()` under
    `unpriced_positions`, where the gate and an operator read it. CHECK-DEBT
    D3.478 owns the other half; the narrowing is visible rather than silent.
    """

    def __init__(
        self,
        tracker: FreshnessTracker,
        fills: FillPath,
        *,
        reconcile_window_s: float,
    ) -> None:
        self._tracker = tracker
        self._fills = fills
        self._window_s = float(reconcile_window_s)
        #: Firings detected and not yet handed across §5:323's boundary.
        self._pending: list[UncertaintyFiring] = []
        #: `(condition, key)` already enqueued. THE FIRE-ONCE MARK, taken in the
        #: same pass that enqueues, on the loop thread — see the block comment.
        self._fired: set[tuple[str, str]] = set()
        #: `client_order_id` -> the DEADLINE its reconciliation window expires
        #: at. D3.469's whole mechanism: present = held, absent = resolved.
        self._windows: dict[str, float] = {}
        #: Observables, read out of a running process by the gate.
        self.scans = 0
        self.detected: dict[str, int] = {c.value: 0 for c in UncertaintyCondition}
        self.suppressed = 0
        self.windows_opened = 0
        #: Windows a REAL exec report closed before the deadline — D3.469's
        #: convert branch. Counted separately from `windows_opened` because
        #: *held and then converted* and *held and then flattened* are the two
        #: outcomes the window exists to distinguish, and one counter over both
        #: would hide which one this daemon is actually producing.
        self.windows_reconciled = 0
        #: Open positions whose feed has NEVER been observed — see the class
        #: docstring. NAMED, not counted: which symbol is the operational fact.
        self.unpriced: set[str] = set()
        #: Refused fill dispatches this object could not classify into any
        #: member of `UncertaintyCondition`. §17 and check contract rule 10: an
        #: unclassifiable condition is CANNOT_MEASURE naming it, never a silent
        #: pass, and the gate reads this list to decide exactly that.
        self.unclassified: list[str] = []
        #: The last raise the reconciliation sweep contained. See `sweep_reconcile`.
        self.last_error = ""
        #: The counters the fill-dispatch classifier differences against. Read
        #: from the fill path itself rather than kept as a private tally: the
        #: question is *did the WRITER refuse* and *did the HANDLER refuse*, and
        #: this object's own opinion of either is not evidence.
        self._seen_write_refusals = fills.writer.refusals
        self._seen_arm_refusals = fills.handler.arm_refusals
        #: C1's in-flight set, shared read-only. See `attach_stop_watch`.
        self._stop_watch: StopWatch | None = None

    # -- the price feed's own stamp -----------------------------------------

    def observe_price(self, symbol: str, at: datetime) -> bool:
        """Record that a price for `symbol` arrived at `at`. NOT the hot path.

        Runs on the serial ingress, inside the `price` verb, for the reason
        `PriceRing.publish` does: §5:322 has something else write and the tick
        READ. `False` where §6.4b's monotonic-by-source guard discarded the
        stamp as older than the one already held.

        **`at` IS THE RECEIPT INSTANT AND NOT THE VENUE'S OWN**, because §5:322's
        `price` command carries no source timestamp — there is no capture feed
        and no vendor integration in this tree (D3.473), so the instant this
        process took delivery is the only one in the room. The consequence is
        stated rather than discovered: this measures *how long since a price
        last reached this Limiter*, which is precisely the D3.453 condition (a
        feed that has gone quiet), and it CANNOT see a feed that is delivering
        stamps the venue produced long ago. That second half needs the capture
        feed D3.473 owns; it is not silently claimed here.
        """
        return self._tracker.observe(FreshnessStamp(feed=PRICE_FEED, as_of=at), symbol)

    # -- condition 1: the per-tick stale-open scan (HOT PATH) ----------------

    def scan_open_positions(self, tick: int) -> int:
        """D3.453. Every OPEN §3 row against §12A's price threshold. HOT PATH.

        §15's `O(positions <= 5)/tick`: §3's published table, one
        `FreshnessTracker.reading` per OPEN row, and an enqueue for each row
        whose feed has gone STALE. No I/O, no lock, no clock read of this
        object's own — the tracker holds the injected clock the detector was
        built around, which is `freshness.py`'s own argument for injecting it.
        """
        self.scans += 1
        found = 0
        for row in self._fills.picture.current().positions:
            if row.state is not PositionState.OPEN:
                continue
            reading = self._tracker.reading(PRICE_FEED, row.symbol)
            if reading.state is CacheState.EMPTY:
                self.unpriced.add(row.symbol)
                continue
            if reading.state is not CacheState.STALE:
                continue
            origin = self._fills.origins.origin_for_trade(row.trade_id)
            found += self._enqueue(
                UncertaintyFiring(
                    condition=UncertaintyCondition.STALE_OPEN,
                    key=row.trade_id,
                    symbol=row.symbol,
                    trade_id=row.trade_id,
                    strategy_id=row.strategy_id,
                    detail=(
                        f"§6.4 flatten-open: trade {row.trade_id!r} is OPEN for "
                        f"{row.size} {row.symbol} and its price feed is "
                        f"{reading.age_ms:.0f}ms old against a "
                        f"{reading.threshold_ms:.0f}ms threshold "
                        f"(§12A:825 price_stale_ms). A stop maintained against "
                        f"a price nobody is sending is not maintenance, so §14 "
                        f"resolves this toward FLAT"
                    ),
                    tick=tick,
                ),
                order_id=None if origin is None else origin.client_order_id,
            )
        return found

    # -- conditions 2 and 4: the refused fill dispatch -----------------------

    def note_fill_dispatch(
        self, completion: SenderCompletion, result: Any, tick: int
    ) -> int:
        """D3.372 and D3.475. Classify ONE refused §2A fill dispatch.

        Called from `CompletionHandler.handle` immediately after the dispatch,
        on the loop thread, and only for a `fill` event. A DISPATCHED result is
        not a condition: §4's cascade armed a stop and published a §3 row, so
        the position is protected and accounted for and there is nothing for §14
        to resolve.

        THE CLASSIFICATION IS BY WHICH COUNTER MOVED, never by the exception's
        type name. `fills.py` catches the BASE exception on the arm path
        deliberately — `StopArmPort` is a structural Protocol and the refusals it
        can raise are not a set that file can enumerate — so a producer keyed on
        a type list would silently stop firing the day an unlisted refusal
        appeared, which is the defect one layer down. `PositionOriginWriter`
        counts its refusals and `FillHandler` counts its arm refusals, and those
        two counters partition the cascade at exactly the two points where a
        confirmed venue fill can leave this process holding nothing.

        A REFUSED FILL THAT MOVED NEITHER COUNTER IS NOT SILENTLY DROPPED. It is
        recorded in `unclassified`, which the gate reads and reports as
        CANNOT_MEASURE naming the site — check contract rule 10, applied to the
        producer set: a condition an instrument cannot classify has not been
        shown safe, and a producer that shrugged would be a green over an
        unprotected position.
        """
        write_refusals = self._fills.writer.refusals
        arm_refusals = self._fills.handler.arm_refusals
        wrote = write_refusals > self._seen_write_refusals
        armed = arm_refusals > self._seen_arm_refusals
        self._seen_write_refusals = write_refusals
        self._seen_arm_refusals = arm_refusals
        if getattr(result, "disposition", None) is not Disposition.REFUSED:
            return 0
        origin = self._fills.origins.origin_for_order(completion.client_order_id)
        trade_id = "" if origin is None else origin.trade_id
        strategy_id = "" if origin is None else origin.strategy_id
        if armed:
            condition = UncertaintyCondition.UNARMABLE_FILL
            detail = (
                f"§4's stop conversion was REFUSED for "
                f"{completion.client_order_id}/{completion.exec_id} in "
                f"{completion.symbol!r}: the venue filled "
                f"{completion.cumulative_qty} and this process armed NO "
                f"synthetic stop, so the quantity is open at the broker with "
                f"nothing behind it (§12.1 makes the stop synthetic and "
                f"Limiter-held). ARC 056 returned the reservation; §14 resolves "
                f"the VENUE half toward FLAT"
            )
        elif wrote:
            condition = UncertaintyCondition.NOT_TRADABLE_FILL
            detail = (
                f"the ORIGIN WRITE refused "
                f"{completion.client_order_id}/{completion.exec_id} in "
                f"{completion.symbol!r} (§4:198). The execution ledger has "
                f"already INGESTED the fill — §4 makes it a fact, not a "
                f"negotiation — so §3's position table and §12.7's mirror read "
                f"FLAT over a real venue position, §7:501 prices that exposure "
                f"at ZERO and the correlation cap ADMITS MORE. §14 resolves it "
                f"toward FLAT"
            )
        else:
            self.unclassified.append(
                f"{completion.client_order_id}/{completion.exec_id} in "
                f"{completion.symbol!r}: §4's cascade REFUSED this fill and "
                f"NEITHER the origin writer nor the stop-arm refusal counter "
                f"moved, so this process cannot say which of §14's conditions "
                f"holds — writer.refusals={write_refusals} "
                f"handler.arm_refusals={arm_refusals}. The venue has reported a "
                f"fill and nothing here classified it: NOT flattened, NOT "
                f"suppressed, RECORDED. Dispatch reason: "
                f"{getattr(result, 'reason', '')!r}"
            )
            return 0
        return self._enqueue(
            UncertaintyFiring(
                condition=condition,
                key=completion.client_order_id,
                symbol=completion.symbol,
                trade_id=trade_id,
                strategy_id=strategy_id,
                detail=detail,
                tick=tick,
            ),
            order_id=completion.client_order_id,
        )

    # -- condition 3: the BOUNDED reconciliation window ----------------------

    def note_poll_hold(self, client_order_id: str, state: str, at: float) -> None:
        """D3.469. A `filled` status answer OPENS a window; it does not flatten.

        **HOLD, NOT FLATTEN, AND THE ORDER OF THOSE TWO IS THE WHOLE RULING.**
        The venue saying `filled` while the execution report has not arrived is
        overwhelmingly the DELAYED-BUT-VALID case: §2A's `on_fill` is a push and
        pushes arrive late, §12.4's reconnect case makes a re-delivery expected,
        and the exec report that converts this order normally lands within the
        tick or two after the status answer. Flattening on the status answer
        would kill a position whose report was merely in flight — a protective
        exit issued against a healthy position, which is not a safe direction,
        it is a different failure.

        So the answer is a BOUNDED HOLD. The window opens once, at the first
        `filled` answer, and the deadline is fixed then: a window re-opened on
        every poll would never expire, because the poll re-answers `filled` on
        every tick for as long as the order is overdue, and a deadline that
        moves with the observation is not a deadline.

        AND IT DOES NOT RE-OPEN AFTER ITS OWN FLATTEN. Nothing about this order
        changes once §14 has resolved it: the poll keeps answering `filled` for
        as long as the reservation is overdue, so without the fired-check below
        a window would re-open, expire and be suppressed once per window forever
        — `windows_opened` climbing while `detected` stood still. The fire-once
        mark would still hold (that is what `suppressed` counts), but a counter
        that grows without bound describes the instrument rather than the venue.
        """
        already_fired = (
            UncertaintyCondition.UNDETAILED_POLL_FILL.value,
            client_order_id,
        ) in self._fired
        if state != FILLED_STATE or client_order_id in self._windows or already_fired:
            return
        self._windows[client_order_id] = at + self._window_s
        self.windows_opened += 1

    def sweep_reconcile(self, tick: int, at: float) -> int:
        """D3.469's two branches, decided. Exec report first -> convert; else FLAT.

        Runs after §4's pending-timeout poll, inside the same tick and on the
        loop thread, so a window closed by a completion dispatched in this tick
        is closed before the deadline in this tick is read. Both branches are
        taken from the SAME evidence — whether §3's published table now carries
        a row for the trade this order opened — because that row is what *the
        exec report arrived and converted* actually means; a counter of
        deliveries would also move for a fill that arrived and was refused.

        NEVER RAISES, AND `last_error` IS THE HALF THAT MADE THAT SAFE TO SAY.
        MEASURED at this arc's S2b, before this containment existed: an
        `AttributeError` raised inside this sweep — the firing was built from
        `TradeOrigin.symbol`, and `TradeOrigin` has no such field — was
        swallowed by the loop's own ingress containment, so the window was
        deleted, no flatten was enqueued, and the next poll re-opened it. The
        daemon reported `windows_opened` climbing 1 -> 2 -> 3 with
        `detected.undetailed_poll_fill` at 0 and `suppressed` at 0: a producer
        that had silently stopped producing, visible only because the two
        counters disagreed. Containment WITHOUT a recorded reason is how that
        happens, so the raise is caught HERE, named, and published — an
        uncaught raise on the tick would kill the process §12.1:604 has the
        Sentinel watching, and a silent one is worse than either.
        """
        try:
            return self._sweep(tick, at)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self.last_error = (
                f"{SITE}: §14's reconciliation sweep raised "
                f"{type(exc).__name__}: {exc} on tick {tick}. The sweep is "
                f"CONTAINED and NOTHING was flattened by it on this tick; every "
                f"window it had not yet judged is still held "
                f"({sorted(self._windows)}). A sweep that cannot run leaves an "
                f"unaccountable position un-flattened, which is the D3.469 "
                f"condition unchanged; a sweep that killed the daemon would "
                f"take every synthetic stop in this process with it"
            )
            return 0

    def _sweep(self, tick: int, at: float) -> int:
        """`sweep_reconcile`'s body. Separated so the containment is one frame."""
        fired = 0
        for client_order_id, deadline in sorted(self._windows.items()):
            if self._converted(client_order_id):
                del self._windows[client_order_id]
                self.windows_reconciled += 1
                continue
            if at < deadline:
                continue
            del self._windows[client_order_id]
            origin = self._fills.origins.origin_for_order(client_order_id)
            fired += self._enqueue(
                UncertaintyFiring(
                    condition=UncertaintyCondition.UNDETAILED_POLL_FILL,
                    key=client_order_id,
                    # THE APPROVAL names the instrument, and it is the only
                    # authority here that does: `seam.TradeOrigin` carries the
                    # trade<->order join and no symbol (three fields, and the
                    # instrument is deliberately not one of them), and §2A's
                    # `OrderStatus` — the thing that answered `filled` — carries
                    # no symbol either. That is the whole of D3.469.
                    symbol=self._approved_symbol(client_order_id),
                    trade_id="" if origin is None else origin.trade_id,
                    strategy_id="" if origin is None else origin.strategy_id,
                    detail=(
                        f"§4's status query answered `filled` for "
                        f"{client_order_id!r} and no §2A execution report "
                        f"converted it within the {self._window_s:.3f}s "
                        f"reconciliation window ({RECONCILE_WINDOW_KEY}). "
                        f"§2A's OrderStatus carries no exec_id, no symbol and "
                        f"no price, so nothing here can open the §3 row: the "
                        f"venue holds a filled position this process cannot "
                        f"account for, and §14 resolves it toward FLAT"
                    ),
                    tick=tick,
                ),
                order_id=client_order_id,
            )
        return fired

    def _approved_symbol(self, client_order_id: str) -> str:
        """The instrument this order was APPROVED in, or `""`. See `sweep_reconcile`."""
        order = self._fills.approvals.order_for(client_order_id)
        return "" if order is None else order.symbol

    def _converted(self, client_order_id: str) -> bool:
        """Did a real exec report open §3's row for this order? The row IS the test."""
        origin = self._fills.origins.origin_for_order(client_order_id)
        if origin is None:
            return False
        return any(
            row.trade_id == origin.trade_id
            for row in self._fills.picture.current().positions
        )

    # -- the boundary --------------------------------------------------------

    def windows_open(self) -> tuple[str, ...]:
        """The orders C2 is currently holding a reconciliation window for."""
        return tuple(sorted(self._windows))

    def drain(self) -> list[UncertaintyFiring]:
        """Take the detected firings. A list swap; the caller hands them over."""
        taken, self._pending = self._pending, []
        return taken

    def _enqueue(self, firing: UncertaintyFiring, *, order_id: str | None) -> int:
        """Mark fire-once and enqueue, or SUPPRESS. Returns 1 or 0.

        The mark is keyed on `(condition, key)` and NOT on the position alone,
        deliberately: one position really can be both un-armable and, later,
        stale-open, and those are two different facts about it. §4's arbiter is
        what makes the second flatten a no-op at the venue — `request_close`
        DROPS a redundant protective close of an already-protective trade — so
        the belt here is fire-once per condition and the braces are the one
        `_closed` book every executor in this process shares.

        `order_id` widens the suppression to C1's IN-FLIGHT set: a position
        whose synthetic stop has already fired a protective flatten this process
        has not yet reconciled must not be flattened a second time under an
        uncertainty label. The read is a set membership on the SHARED `StopWatch`
        and costs nothing on the hot path.
        """
        mark = (firing.condition.value, firing.key)
        if mark in self._fired or (order_id is not None and self._in_flight(order_id)):
            self.suppressed += 1
            return 0
        self._fired.add(mark)
        self._pending.append(firing)
        self.detected[firing.condition.value] += 1
        return 1

    def _in_flight(self, order_id: str) -> bool:
        """Whether C1's stop exit already has a protective flatten in flight.

        Read LIVE off the shared `StopWatch` on every call rather than snapshotted
        at wiring time: the set changes inside the tick (C1 marks at the enqueue,
        on this same thread), and a copy taken at boot would answer a question
        about a state that no longer exists. `in_flight()` is bounded by §7's
        five instruments, so the membership test is O(<=5) on the hot path.
        """
        watch = self._stop_watch
        return watch is not None and order_id in watch.in_flight()

    def attach_stop_watch(self, watch: StopWatch) -> None:
        """Share C1's in-flight set. READ-ONLY; this object never marks it.

        Optional, and the default of `None` is the load-bearing half: a build
        without C1's stop watch suppresses NOTHING rather than raising, which is
        the direction that FIRES the protective exit rather than withholding it.
        §14 is *resolve toward flat*, so the fail-safe direction for a missing
        collaborator here is to flatten, and §4's arbiter drops a redundant
        protective close anyway.
        """
        self._stop_watch = watch

    # -- evidence ------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. ENUMERATED wherever a name matters.

        `conditions` is published as the DERIVED set with its debt origins, not
        as a count, because the gate's completeness obligation is *the set of
        uncertainty conditions this daemon flattens equals the set that was
        named* — and a gate that had to restate the set in its own source would
        go stale the moment a fifth was added, which is the exact failure mode
        `check_flatten` ARM 6 was built to close for the trigger set.
        """
        return {
            "scans": self.scans,
            "conditions": dict(UNCERTAINTY_ORIGIN),
            "detected": dict(self.detected),
            "suppressed": self.suppressed,
            "pending": len(self._pending),
            "windows_open": sorted(self._windows),
            "windows_opened": self.windows_opened,
            "windows_reconciled": self.windows_reconciled,
            "reconcile_window_s": self._window_s,
            "unpriced_positions": sorted(self.unpriced),
            "unclassified": list(self.unclassified),
            "last_error": self.last_error,
            "price_feed_observations": self._tracker.observations,
            "price_stale_threshold_ms": self._tracker.policy.threshold_ms(PRICE_FEED),
        }


class UncertaintyDriver:  # pylint: disable=too-many-instance-attributes
    # R0902: NINE attributes — eight inherited (the watch, §4's executor, the
    # loop, the fire/send counters, the refusals, the actions and the sending
    # thread's id, every one read out of `record()` by a gate) plus ARC 058's ONE
    # in-flight book, which is what lets a closing fill be matched back to the
    # flatten this driver sent. Same refusal `StopWatchDriver` records above.
    """ARC 057 / I1 ARC C2. §14's uncertainty flatten, FIRED and SENT.

    TWO HALVES ON TWO THREADS, and the split is C1's, restated over a different
    set of conditions:

    * `before()` runs on the HOT LOOP. It runs `UncertaintyWatch`'s per-tick
      stale-open scan AHEAD of the tick's own work, then — after the tick's
      reads, dispatches and §4 poll have run — DRAINS every condition detected
      anywhere in the tick and hands each across §5:323's boundary with an
      unbounded `put` that never blocks the caller.
    * `send()` runs on the SENDER THREAD. It is where `ProtectiveFlatten.fire`
      is called, and it is there and not on the loop for C1's reason: `fire`
      takes the §4 arbitration lock and appends a §12.10 row, and §5:323 is
      explicit that the hot loop never blocks.

    THE FIRE IS §4's OWN, UNCHANGED. `nixrisk/flatten.py` is byte-identical
    across this arc and asserted so with `git hash-object`. Where a `trade_id`
    exists the flatten is a TARGETED protective close through `request_close`,
    which is §4's arbiter and the only place precedence is decided. Where none
    does — D3.372's refused origin write and D3.469's unconvertible status
    answer can both leave this process with no join — the fire is §4's
    SYMBOL-ONLY uncertainty branch, which `fire` documents as *"a flatten sent
    to be safe with no known trade"* and which records the intent so reconcile
    can attribute whatever it turns out to have closed.

    NO RETRY, NO AUTO-RESEND. A firing the sender refused or that raised is
    RECORDED and never re-queued — §4's resend prohibition, the same one
    `StopWatchDriver` keeps and for the same reason: a protective flatten resent
    on a schedule nobody declared is an unbounded stream of venue orders
    produced by a defect.
    """

    def __init__(
        self,
        watch: UncertaintyWatch,
        exits: ProtectiveFlatten,
        loop: LimiterLoop,
        in_flight: FlattenInFlightBook | None = None,
    ) -> None:
        self._watch = watch
        self._exits = exits
        #: ARC 058 / I1 ARC D. The SAME book `StopWatchDriver` arms — one book,
        #: for the reason every collaborator in this file shares one: a closing
        #: fill arrives against a SYMBOL, and a second book would let a fill sent
        #: for a C1 breach be matched against a C2 intent, or neither be matched
        #: at all. Optional on the same argument C1's is.
        self._in_flight = in_flight
        self._loop = loop
        #: Firings handed across the §5:323 boundary by the hot loop.
        self.fires = 0
        #: Firings the SENDER THREAD actually fired a protective flatten for.
        #: Counted separately from `fires` for check contract rule 2's reason,
        #: applied across a thread boundary: what the loop handed over and what
        #: the sender did with it are two facts.
        self.sends = 0
        #: Firings the sender could not fire, with the reason. NEVER re-queued.
        self.refusals: list[str] = []
        #: Every flatten this driver produced, ENUMERATED. A total cannot answer
        #: *was exactly one uncertainty flatten issued for this position*, which
        #: is the question fire-once exists to make answerable.
        self.actions: list[dict[str, Any]] = []
        #: The native id of the thread the LAST send ran on. Read from INSIDE
        #: the send, so it is the SENDER's and not the loop's — the field that
        #: proves the send was off the hot path, compared against the loop
        #: thread's own id by `check_uncertainty_flatten`.
        self.sent_on_native_id: int | None = None

    # -- the hot loop half ---------------------------------------------------

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Scan FIRST, then the tick, then hand everything the tick detected.

        The position of the two halves is deliberate. The SCAN runs ahead of the
        ingress reads for `StopWatchDriver.before`'s reason — §4's protective
        exit always wins, so a position that cannot be managed is detected
        before this tick's commands can approve anything new against the capital
        it is about to release. The HAND runs after `inner`, which is the whole
        rest of the tick, so the three EVENT-DRIVEN conditions — a refused fill
        dispatch and an expired reconciliation window, both noted while `inner`
        runs — reach §5:323's sender in the SAME tick they were detected in
        rather than one tick later.
        """

        def _tick(tick: int) -> object:
            self._watch.scan_open_positions(tick)
            taken = inner(tick)
            self._hand()
            return taken

        return _tick

    def observe_price(self, symbol: str, at: datetime) -> bool:
        """Stamp the price feed for D3.453's scan. Delegated, NOT re-implemented.

        Exposed on the driver rather than reaching past it to the watch so the
        `price` verb has ONE collaborator to hold, the same way it already holds
        C1's driver for the `stops` block. It is still DETECTION — this method
        cannot fire, and the object it delegates to structurally cannot either.
        """
        return self._watch.observe_price(symbol, at)

    def note_fill_dispatch(
        self, completion: SenderCompletion, result: DispatchResult
    ) -> int:
        """D3.372 / D3.475, noted at the dispatch and HANDED IN THE SAME TICK.

        Called from `CompletionHandler.handle`, which runs in the loop's DRAIN
        and therefore AFTER `before`'s own hand-off has already run for this
        tick. So this hands directly rather than leaving the firing for the next
        tick's drain: `LimiterLoop.hand_to_sender` is an unbounded `put` that
        never blocks the caller, and a protective flatten for a position the
        venue is already holding is not work to defer by a tick for tidiness.
        """
        detected = self._watch.note_fill_dispatch(
            completion, result, self._loop.tick_count
        )
        if detected:
            self._hand()
        return detected

    def _hand(self) -> int:
        """Drain and hand to the sender. HOT PATH; never blocks (§5:323)."""
        handed = 0
        for firing in self._watch.drain():
            self._loop.hand_to_sender(firing)
            self.fires += 1
            handed += 1
        return handed

    # -- the sender-thread half ----------------------------------------------

    def send(self, payload: object) -> None:
        """Fire ONE uncertainty flatten. RUNS ON THE SENDER THREAD.

        Ignores anything that is not an `UncertaintyFiring`: §5:323's queue is
        shared with the `go` verb's handoff and with C1's `BreachFiring`, and a
        sender that flattened on an unrecognised payload would be firing venue
        orders off a type confusion. `StopWatchDriver.send` makes the mirror-image
        refusal on the same queue, which is what lets both drivers read it.
        """
        if not isinstance(payload, UncertaintyFiring):
            return
        self.sent_on_native_id = threading.get_native_id()
        symbol = payload.symbol or None
        targets = (
            (
                CloseTarget(
                    trade_id=payload.trade_id,
                    symbol=payload.symbol,
                    strategy_id=payload.strategy_id,
                ),
            )
            if payload.trade_id
            else ()
        )
        if symbol is None and not targets:
            # Nothing to name. §4's uncertainty branch flattens a SYMBOL and the
            # targeted branch closes a TRADE; with neither there is no venue call
            # to make, so this is refused and NAMED rather than sent under a
            # guessed identity — the same refusal `StopWatchDriver.send` makes
            # for an order with no recorded join, and for the same reason.
            self.refusals.append(
                f"{payload.condition.value}/{payload.key}: detected on tick "
                f"{payload.tick} and this process holds NEITHER a symbol nor a "
                f"trade_id for it, so there is no §4 close to issue. NOT "
                f"flattened; NOT re-queued. {payload.detail}"
            )
            return
        trigger = _UNCERTAINTY_TRIGGER[payload.condition]
        # §14's word, and it is the word the strategy receives and §9's record
        # keeps. `reason` overrides `fire`'s derived string for `flatten.py`'s
        # own stated reason: a caller with a spec-named reason passes it.
        # ARC 058: bound to a name for `StopWatchDriver.send`'s reason — the
        # closing fill's `closed` row and notify carry THIS word.
        reason = (
            f"protective flatten (reason={UNCERTAINTY_REASON}, "
            f"trigger={trigger.value}, condition={payload.condition.value})"
        )
        try:
            action = self._exits.fire(
                trigger,
                symbol=symbol,
                targets=targets,
                reason=reason,
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            # CONTAINED, NEVER RE-QUEUED. This runs on §5:323's sender thread and
            # an exception escaping it would take the thread down, and with it
            # every later protective flatten C1 and C2 both depend on. The
            # failure is recorded with the exception's own sentence (rule 11).
            self.refusals.append(
                f"{payload.condition.value}/{payload.key}: §4's executor RAISED "
                f"{type(exc).__name__}: {exc}. NOT flattened; NOT re-queued "
                f"(§4:240-241 forbids the resend). {payload.detail}"
            )
            return
        self.sends += 1
        # ARC 058 / I1 ARC D. Recorded at the send, on the far side of the fire.
        # `trade_id`/`strategy_id` ride through EMPTY where this process holds no
        # join — §4's untargeted uncertainty branch — and `closing.py` attributes
        # such a close by SYMBOL against §3's live rows, refusing rather than
        # guessing when the symbol carries more than one.
        if self._in_flight is not None and symbol is not None:
            self._in_flight.arm(
                key=payload.key,
                symbol=symbol,
                trade_id=payload.trade_id,
                strategy_id=payload.strategy_id,
                reason=reason,
                trigger=action.trigger.value,
                at=action.fired_ts,
            )
        self.actions.append(
            {
                "condition": payload.condition.value,
                "key": payload.key,
                "trigger": action.trigger.value,
                "reason": UNCERTAINTY_REASON,
                "symbol": action.symbol,
                "trade_ids": [target.trade_id for target in action.targets],
                "executed": [outcome.executed for outcome in action.outcomes],
                "dropped": [
                    outcome.dropped_reason
                    for outcome in action.outcomes
                    if outcome.dropped_reason
                ],
                "fired_ts": action.fired_ts,
                "tick": payload.tick,
                "detail": payload.detail,
            }
        )

    # -- evidence ------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        """What this driver did, for the out-of-process reader."""
        block = self._watch.record()
        block.update(
            {
                "fires": self.fires,
                "sends": self.sends,
                "refusals": list(self.refusals),
                "actions": list(self.actions),
                "sent_on_native_id": self.sent_on_native_id,
                "loop_native_id": threading.get_native_id(),
                "sender_native_id": self._loop.sender.native_id,
                # THE BROKER'S OWN RECORD, read off the object the flatten
                # reached — not this driver's count of what it asked for (check
                # contract rule 2: the return value of a mutating call is not a
                # verification, and `sends` is exactly such a value one layer up).
                "flattened": list(self._broker_flattened()),
            }
        )
        return block

    def _broker_flattened(self) -> tuple[str | None, ...]:
        """Every symbol the BROKER recorded a protective flatten for, in order."""
        broker = getattr(self._exits, "_broker", None)
        return tuple(getattr(broker, "flattened", ()))


# R0903 (too-few-public-methods): ONE public verb, and it IS §5:323's sender
# callback. A second verb here would be a second thing the sender thread can be
# asked to do, which is the boundary this class exists to keep narrow.
# pylint: disable=too-few-public-methods
class ProtectiveSenders:
    """§5:323's ONE sender callback, fanned to BOTH protective producers.

    `LimiterLoop.attach` takes one `sender_send`, and from ARC 057 there are two
    producers behind it: C1's synthetic-stop exit (`BreachFiring`) and C2's
    §14 uncertainty flatten (`UncertaintyFiring`). This is the routing, and it
    is an OBJECT with one verb rather than a closure for two reasons that are
    the same reason: the send is the thing every protective exit in this process
    passes through, so it should be a named surface an AST census can find
    (`check_stop_maintenance` ARM 4 derives *the daemon hands the fire to
    §5:323's sender* from the source, and `check_uncertainty_flatten` derives
    the same for C2), and a lambda in an argument list is not one.

    ROUTED BY PAYLOAD TYPE, never by a flag or a string. Each driver's `send`
    returns immediately on a payload that is not its own frozen dataclass — see
    `StopWatchDriver.send` and `UncertaintyDriver.send`, which make the
    mirror-image refusal — so the queue stays the single boundary §5:322-323
    describes and neither producer can fire on the other's firing. A dispatcher
    that switched on a string would be a third place the two could be confused.

    THE ORDER IS C1 FIRST, and it is not arbitrary. A breached synthetic stop is
    §4's NAMED protective exit for a position that has one; an uncertainty
    flatten is what §14 does for a position that has none. With the shared
    `_closed` book underneath both, whichever fires first is the recorded winner
    and the second is DROPPED by §4's arbiter as a redundant protective close
    rather than issued twice at the venue.
    """

    def __init__(self, stops: StopWatchDriver, uncertainty: UncertaintyDriver) -> None:
        self._stops = stops
        self._uncertainty = uncertainty

    def send(self, payload: object) -> None:
        """RUNS ON THE SENDER THREAD. Offers one payload to each producer."""
        self._stops.send(payload)
        self._uncertainty.send(payload)


#: §3:169's trigger for each condition. `STALE_PRICE` is §3's own word for the
#: stale-feed case and CHECK-DEBT D3.453 is the row recording that NOTHING in
#: this tree ever fired it; the other three are §3's `uncertainty`. Both are
#: members of the FROZEN `FlattenTrigger` vocabulary — no member is added here,
#: and `seam.py` is byte-identical across this arc.
_UNCERTAINTY_TRIGGER: Final[dict[UncertaintyCondition, FlattenTrigger]] = {
    UncertaintyCondition.STALE_OPEN: FlattenTrigger.STALE_PRICE,
    UncertaintyCondition.NOT_TRADABLE_FILL: FlattenTrigger.UNCERTAINTY,
    UncertaintyCondition.UNDETAILED_POLL_FILL: FlattenTrigger.UNCERTAINTY,
    UncertaintyCondition.UNARMABLE_FILL: FlattenTrigger.UNCERTAINTY,
}

#: §14's word for what every one of these flattens IS, carried on the reason so
#: §9's record keeps it. §4:301's cooldown ladder already spells it
#: (`cooldown_min_time_s.uncertainty`), so this is the vocabulary the config
#: files use and not a new one.
UNCERTAINTY_REASON: Final[str] = "uncertainty"


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """Serialise into a sibling temp file and `os.replace` it into place.

    NOT fsynced, and the omission is deliberate and matches
    `nixsentinel/heartbeat.py`: these are LIVE runtime values whose consumer asks
    "what does the process say right now", not evidence that must outlive the
    box. §9's Plane-1 log is the evidence plane and this is not it.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.write(fd, blob.encode("utf-8"))
        os.close(fd)
        os.chmod(tmp, _MODE)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# R0914: the locals ARE the collaborators this process holds, one per §-numbered
# surface. A record builder with fewer would be a record with fewer facts in it.
def _runtime_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    loop: LimiterLoop,
    *,
    boot_ts: float,
    stopped_ts: float | None,
    booker: Plane1Booker | None = None,
    reservations: ReservationLedger | None = None,
    dispatcher: CompletionDispatcher | None = None,
    fills: FillPath | None = None,
    feedback: OpenFeedback | None = None,
    timeouts: PendingTimeoutPoller | None = None,
    onset: OnsetWatch | None = None,
    book: PendingEntryBook | None = None,
    signal_max_age_s: float | None = None,
    prices: PriceRing | None = None,
    uncertainty: UncertaintyDriver | None = None,
    stopwatch: StopWatchDriver | None = None,
    closing: ClosingFillHandler | None = None,
    closed_feedback: ClosedFeedback | None = None,
) -> dict[str, Any]:
    """`limiter.runtime.json`'s content, at boot and again at clean stop.

    Both records have the SAME shape, so the boot record and the stop record are
    read by one reader and differ only in what they say. `flat` is DERIVED from
    the live registry rather than asserted: at boot it is true because the
    registry is empty by construction, and writing `true` unconditionally would
    make the field an announcement instead of a measurement.
    """
    holders = loop.in_flight_holders()
    return {
        "schema": RUNTIME_SCHEMA,
        "pid": os.getpid(),
        "boot_ts": boot_ts,
        "flat": not holders,
        "registrations": list(loop.registry.registered()),
        "in_flight": [list(pair) for pair in holders],
        #: §12A:831's T, in the record the gate reads. Written rather than
        #: inferable because `check_go_timeout` has to distinguish *the breaker
        #: did not fire* from *the breaker was configured never to*.
        "go_timeout_s": loop.go_timeout_s,
        "go_armed": [[sid, cid, round(el, 3)] for sid, cid, el in loop.go_armed()],
        #: ARC 042 / D3.425. §9's evidence-plane counters, so an out-of-process
        #: reader can tell *fired and booked* from *fired and refused* from
        #: *never fired*. `None` only if the booker could not be built, which
        #: `main` refuses to boot on.
        "plane1": None if booker is None else booker.record(),
        #: ARC 046. §11.3's LIVE aggregate and the §5:322 dispatch counters, in
        #: the record an out-of-process reader opens. `None` rather than 0.0
        #: where the collaborator is absent: check contract rule 10 — a Σ of
        #: 0.0 reported by a process that holds no ledger would be a safety
        #: property certified over an unavailable subject.
        "reservations": (
            None
            if reservations is None
            else {
                "committed": reservations.total_reserved(),
                "outstanding": len(reservations.outstanding()),
                "released": len(reservations.released()),
                "refused": len(reservations.refusals()),
            }
        ),
        "completions": None if dispatcher is None else dispatcher.record(),
        #: ARC 047. §4/§3's fill state and §3's ONE snapshot, in the record an
        #: out-of-process reader opens. `None` rather than an empty book where
        #: the collaborator is absent, for the reason `reservations` is `None`
        #: rather than 0.0: check contract rule 10 — an empty stop list published
        #: by a process that has no stop book would certify "no unprotected
        #: position" over a subject that does not exist.
        "fills": None if fills is None else fills.record(),
        "picture": None if fills is None else fills.picture_record(),
        #: §4:203-206's outcome pushes. The records themselves, not a count: the
        #: question is whether the feedback carried THIS trade's id.
        "feedback": (
            None
            if feedback is None
            else {"pushed": list(feedback.pushed), "failures": list(feedback.failures)}
        ),
        #: ARC 053. §4's pending-timeout resolution, in the record an
        #: out-of-process reader opens. `None` rather than zeroed counters where
        #: the poller is absent, for the reason `reservations` is `None` rather
        #: than 0.0: a `resends: 0` published by a process that has no poller
        #: would certify §4:240-241's no-resend rule over a path that does not
        #: exist — check contract rule 10, applied to the one guarantee this arc
        #: is most obliged not to overstate.
        "timeouts": None if timeouts is None else timeouts.record(),
        #: ARC 054. §3:173's onset sweep, and the pending-entry book it sweeps.
        #: `None` rather than zeroed counters where either is absent, for the
        #: reason `timeouts` is `None`: a `blackout_onsets: 0` published by a
        #: process that has no onset watch would read as *no onset arrived* when
        #: the truth is *no onset could arrive*, and check contract rule 10
        #: forbids certifying a safety property whose subject is unavailable.
        "onset": None if onset is None else onset.record(),
        #: D3.443's enumeration, published as the SET. It is the left-hand side
        #: of the completeness claim: a gate compares this to what the sweep was
        #: handed and to what it cancelled, and an entry present here and absent
        #: from the cancels is the exact defect §3:174 names.
        "pending_entries": None if book is None else book.record(),
        #: ARC 055 / I1 ARC C1. §4:190-196's trail and the breach->flatten path,
        #: in the record an out-of-process reader opens. `None` rather than
        #: zeroed counters where the driver is absent, for the reason every
        #: sibling above is `None`: a `breaches: 0` published by a process that
        #: polls no prices reads as *nothing breached* when the truth is
        #: *nothing could breach*, and those two are exactly what D3.451 was.
        "stops": None if stopwatch is None else stopwatch.record(),
        #: ARC 057 / I1 ARC C2 — ADDED BY ARC 058, AND THE ABSENCE WAS A DEFECT
        #: RATHER THAN A CHOICE. This function has ACCEPTED an `uncertainty`
        #: argument since ARC 057 and never read it, so `main()` passed §14's
        #: four producers into both the boot record and the clean-stop record and
        #: neither published them: an out-of-process reader opening
        #: `limiter.runtime.json` could not tell *this build has no §14
        #: producers* from *nothing was uncertain* — the exact pair every `None`
        #: in this block exists to keep apart, and check contract rule 10's whole
        #: subject. Found by pylint's `W0613 unused-argument` at ARC 058's
        #: greening pass and confirmed INHERITED by running pylint at HEAD in a
        #: clean worktree before a line of that arc existed.
        "uncertainty": None if uncertainty is None else uncertainty.record(),
        #: The §5:322 ring the poll reads. Its `published` count is the
        #: NON-VACUITY of everything in `stops`: a trail that never moved
        #: against a ring that was never written measures an absent input, not
        #: an omission.
        "prices": (
            None
            if prices is None
            else {
                "symbols": list(prices.symbols()),
                "published": prices.published(),
                "head": {
                    symbol: head.price
                    for symbol in prices.symbols()
                    if (head := prices.head(symbol)) is not None
                },
            }
        ),
        #: ARC 053 / D3.463. The signal-age ceiling this process booted with, in
        #: the record an out-of-process reader opens. `null` means UNBOUNDED and
        #: says so, because *no ceiling* and *a ceiling of zero* are opposite
        #: facts and a missing key would read as neither.
        "signal_max_age_s": signal_max_age_s,
        #: ARC 058 / I1 ARC D. §4's CLOSE as the RUNNING process reports it:
        #: every trade this daemon closed off a flatten's own exec report, the
        #: open margin §3 published AFTER each release, the stop each retired,
        #: the closes it REFUSED by name, and the flattens still IN FLIGHT.
        #: `None` rather than zeroed counters where the handler is absent, for
        #: the reason every sibling above is `None`: a `closed: 0` published by a
        #: process that cannot reconcile a closing fill reads as *nothing closed*
        #: when the truth is *nothing could close* — the exact pair D3.481 and
        #: ARC 058 / S1 measured, and check contract rule 10's whole subject.
        "closing": None if closing is None else closing.record(),
        #: §4:203-206's `closed` outcome pushes, beside `feedback`'s `open`
        #: ones. Two blocks because they are two outcomes and one merged list
        #: could not answer *was THIS trade's FSM hard-reset to flat*.
        "closed_feedback": (
            None if closed_feedback is None else closed_feedback.record()
        ),
        "stopped_ts": stopped_ts,
    }


def _stop_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    loop: LimiterLoop,
    stop: LoopStop,
    *,
    boot_ts: float,
    stopped_ts: float,
    booker: Plane1Booker | None = None,
    reservations: ReservationLedger | None = None,
    dispatcher: CompletionDispatcher | None = None,
    fills: FillPath | None = None,
    feedback: OpenFeedback | None = None,
    timeouts: PendingTimeoutPoller | None = None,
    onset: OnsetWatch | None = None,
    book: PendingEntryBook | None = None,
    signal_max_age_s: float | None = None,
    prices: PriceRing | None = None,
    uncertainty: UncertaintyDriver | None = None,
    stopwatch: StopWatchDriver | None = None,
    closing: ClosingFillHandler | None = None,
    closed_feedback: ClosedFeedback | None = None,
    malformed: tuple[str, ...] = (),
    closing_refusals: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The clean-stop record: the boot shape plus what the run actually did."""
    record = _runtime_record(
        loop,
        boot_ts=boot_ts,
        stopped_ts=stopped_ts,
        booker=booker,
        reservations=reservations,
        dispatcher=dispatcher,
        fills=fills,
        feedback=feedback,
        timeouts=timeouts,
        onset=onset,
        book=book,
        signal_max_age_s=signal_max_age_s,
        prices=prices,
        uncertainty=uncertainty,
        stopwatch=stopwatch,
        closing=closing,
        closed_feedback=closed_feedback,
    )
    # ARC 058. Closes the CLOSE path itself refused — §3 declined the commit, so
    # the position is still OPEN and the flatten is still in flight. Kept out of
    # `completions_malformed` below for that list's own reason: *unparsable* and
    # *parsed, recognised as a close, and refused* are two readings.
    record["closing_refused"] = list(closing_refusals)
    # ARC 046. The completions the ingress read and the PARSE refused, so
    # "no exec report arrived" and "an exec report arrived unreadable" are two
    # readings rather than one absence (`nixrisk/completions.py` §7.12 #1).
    record["completions_malformed"] = list(malformed)
    record.update(
        {
            # `flat` comes from the STOP OBSERVATION here, not from the live
            # registry `_runtime_record` re-derives it from. Every other field in
            # this record is `stop`'s, and `LoopStop` is explicitly the state
            # observed AFTER the loop exited and the sender was joined — reading
            # one field of a stop record off a still-mutable object while the
            # other eleven come from the snapshot is the split source directive 3
            # forbids. The two agree today because nothing mutates the registry
            # after `run()` returns; the day something does, this field would
            # have been the one that quietly stopped describing the same moment
            # as the eleven beside it.
            "flat": stop.flat,
            "reason": stop.reason,
            "ticks": stop.ticks,
            "heartbeats": stop.heartbeats,
            "last_seq": stop.last_seq,
            "last_beat_ts": stop.last_beat_ts,
            "sender_alive": stop.sender_alive,
            "sender_joined": stop.sender_joined,
            "sender_handoffs": stop.sender_handoffs,
            "sender_ledger": [
                {"seq": row.seq, "tick": row.tick, "payload": repr(row.payload)}
                for row in loop.sender.ledger()
            ],
            "overruns": stop.overruns,
            # THE EVIDENCE `checks/check_go_timeout.py` READS. One row per
            # §4:210-212 firing, each carrying its own elapsed against its own
            # T, so a breaker that fired on EVERY GO is distinguishable from one
            # that fired on a lost one — a bare count is not.
            "go_timeouts": [
                {
                    "strategy_id": row.strategy_id,
                    "client_order_id": row.client_order_id,
                    "admitted_tick": row.admitted_tick,
                    "fired_tick": row.fired_tick,
                    "elapsed_s": row.elapsed_s,
                    "timeout_s": row.timeout_s,
                    "released": row.released,
                    "resent": row.resent,
                    "reason": row.reason,
                }
                for row in stop.go_timeouts
            ],
            "faults": list(stop.faults),
        }
    )
    return record


def _parser() -> argparse.ArgumentParser:
    """The CLI. FIXED CONTRACT — the out-of-process gate is written against it."""
    parser = argparse.ArgumentParser(
        prog="limiterd",
        description=(
            "Run the §5:322 Limiter event loop as a process: one ticking thread, "
            "one low-priority sender thread, and the §12.1:604 heartbeat "
            "published from the tick."
        ),
    )
    parser.add_argument(
        "--runtime-dir",
        required=True,
        help=(
            "Directory holding the heartbeat, inbox/, outbox/ and "
            "limiter.runtime.json. Created if absent."
        ),
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=None,
        help=(
            "Seconds between beats. Default: §12A:832 heartbeat_interval_s from "
            "risks/limiter.config.json. Overridable so a test can run the loop "
            "fast; the shipped value is the one the Sentinel's threshold derives "
            "from and production must not pass this."
        ),
    )
    parser.add_argument(
        "--tick-interval",
        type=float,
        default=None,
        help=(
            "Seconds between ticks. Default: the heartbeat interval divided by "
            "nixrisk.loop.TICKS_PER_HEARTBEAT (a declared Nix addition — §12A "
            "names no tick cadence)."
        ),
    )
    parser.add_argument(
        "--go-timeout",
        type=float,
        default=None,
        help=(
            "Seconds a GO may hold the §4:208 one-in-flight lock with no "
            "terminal feedback before §4:210-212's deadlock breaker releases it. "
            "Default: §12A:831 go_timeout_s from risks/limiter.config.json. "
            "Overridable so a control can drive the breaker inside a test's "
            "budget; the shipped value is the one the platform ISSUES to every "
            "strategy in its REGISTER_ACK (nix_strategy_contract_v1.1.md §4.2) "
            "and production must not pass this."
        ),
    )
    parser.add_argument(
        "--reconcile-window",
        type=float,
        default=None,
        help=(
            "Seconds a `filled` status answer whose §2A execution report has "
            "not arrived is HELD before §14 resolves it toward flat. Default: "
            f"{RECONCILE_WINDOW_KEY} from risks/limiter.config.json, a declared "
            "Nix addition (§12A names no such knob — PENDING_ACK_TIMEOUT_MS "
            "bounds an un-acked order and FILL_TIMEOUT bounds a working one, "
            "and this interval starts after the venue has already said "
            "`filled`). Overridable so a gate can drive BOTH branches inside a "
            "test's budget, exactly as --go-timeout is; the shipped value is "
            "the one an operator tuned and production must not pass this."
        ),
    )
    parser.add_argument(
        "--plane1-wal",
        default=None,
        help=(
            "Path to §9's durable local Plane-1 WAL this process appends the "
            f"§12.10 go_timeout row to. Default: {PLANE1_WAL_NAME} inside the "
            "runtime directory. The shared-pool writer that group-commits it "
            "into Postgres is a different process and is not started here."
        ),
    )
    parser.add_argument(
        "--tick-size",
        action="append",
        default=None,
        metavar="SYMBOL=SIZE",
        help=(
            "The PRICE value of one tick for a symbol, e.g. --tick-size ES=0.25. "
            "Repeatable. §4 converts the GO's stop DISTANCE (in ticks) to an "
            "absolute price at the confirmed fill, and that conversion has no "
            "scale without this. It is an instrument constant on §12.11's "
            "boot-loaded, restart-only lifecycle, and it arrives here because "
            "risks/ carries no instrument table (allocator_caps.config.json holds "
            "tick_value_usd, the DOLLAR value of a tick, which is a different "
            "number). A symbol absent from the map is NOT-TRADABLE (§4:198): a "
            "fill in it is REFUSED before anything is released, so no position "
            "opens without a stop."
        ),
    )
    parser.add_argument(
        "--account-balance",
        type=float,
        default=0.0,
        help=(
            "The account balance §3's picture is built on. There is NO balance "
            "feed in this process — §6.4b's event-driven refresh is not wired — "
            "so this is a declared opening figure and nothing refreshes it. The "
            "default 0.0 means NO BALANCE WAS DECLARED, which makes deployable "
            "0.0; that is the fail-closed direction, because a §3 Phase-B rule "
            "evaluated against it denies rather than admits. Σ open margin and Σ "
            "reservations are real either way, and they are what the fill "
            "conversion moves."
        ),
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=0,
        help=(
            "Stop cleanly after this many ticks. 0 or absent = run forever. A "
            "safety stop so a stray daemon cannot outlive the test that started it."
        ),
    )
    return parser


def _tick_sizes(pairs: list[str] | None) -> dict[str, float]:
    """`["ES=0.25", ...]` -> `{"ES": 0.25}`. Refuses anything unusable, loudly.

    Raises, and the raise is caught by `main`'s boot guard into an exit 2: a tick
    size read wrong is a stop armed at the wrong price, and §12A:801-802 rejects
    an invalid tunable set at boot rather than absorbing it at run time.
    """
    out: dict[str, float] = {}
    for pair in pairs or ():
        symbol, sep, raw = str(pair).partition("=")
        if not sep or not symbol.strip():
            raise ValueError(
                f"--tick-size {pair!r} is not SYMBOL=SIZE — §4's distance->price "
                "conversion needs both halves and neither can be guessed"
            )
        try:
            size = float(raw)
        except ValueError as exc:
            raise ValueError(f"--tick-size {pair!r}: {raw!r} is not a number") from exc
        if size <= 0.0:
            raise ValueError(
                f"--tick-size {pair!r}: a tick size must be positive. A zero "
                "scale puts every stop ON the entry, where it fires on the first "
                "adverse tick (§15 C3)"
            )
        out[symbol.strip()] = size
    return out


def _install_signal_handlers(loop: LimiterLoop) -> None:
    """`SIGTERM`/`SIGINT` -> `loop.stop()`. The clean death of §12.2:617.

    The handler does nothing but set a flag and record a reason. Anything that
    could block inside a handler would turn the supervisor's polite `SIGTERM`
    into its follow-up `SIGKILL`, which is the death that leaves no `stopped_ts`.
    """

    def _handler(signum: int, frame: FrameType | None) -> None:
        del frame
        loop.stop(f"{SITE}: {signal.Signals(signum).name} received (§12.2:617)")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


# R0914 (too-many-locals): `main` is a BOOT SEQUENCE, and every local is one
# thing the process must resolve before it may tick — the two intervals, the
# three directories, the publisher, the knob, the loop, the WAL path, the booker,
# the boot stamp, the record path. ARC 042 added two (`wal_path`, `booker`) and
# crossed the threshold. Extracting a helper to satisfy the counter would split
# the boot across two frames while leaving the same number of things resolved,
# and the `except` below — which turns ANY boot failure into a loud exit 2 with
# no runtime directory to write into — has to wrap all of them or it wraps a lie.
# pylint: disable=too-many-locals
# R0915 refused with a reason (INHERITED at ARC 058's greening pass, measured at
# HEAD in a clean worktree at 52/50): this function IS the daemon's assembly, and
# every statement over the threshold is one collaborator this process owns being
# constructed and handed to §5:322's loop. Splitting it would move half the
# wiring out of the one place `check_i1_convergence` reads it from — and *is the
# required path composed into the tick* is precisely what that gate derives from
# this function's body. A shorter `main` here would be a less measurable one.
# pylint: disable=too-many-statements
def main(argv: list[str] | None = None) -> int:
    """Boot, run, and write the documented final state. Returns the exit code.

    Exit 0 is a CLEAN stop — signalled or `--max-ticks` reached — and the stop
    record on disk is what says which. Exit 2 is a refusal to boot at all
    (unreadable config, a runtime directory that cannot be made), and it is loud
    on stderr because there is no runtime directory to write it into.
    """
    args = _parser().parse_args(argv)
    runtime_dir = Path(args.runtime_dir).resolve()
    try:
        interval = (
            heartbeat_interval_from_config()
            if args.heartbeat_interval is None
            else float(args.heartbeat_interval)
        )
        tick = (
            tick_interval_for(interval)
            if args.tick_interval is None
            else float(args.tick_interval)
        )
        inbox_dir = runtime_dir / INBOX_DIR
        outbox_dir = runtime_dir / OUTBOX_DIR
        completions_dir = runtime_dir / COMPLETIONS_DIR
        # ARC 053. Created at boot for the reason `completions/` is: a §4 status
        # query against a directory that does not exist would answer `unknown`
        # for a reason that has nothing to do with the venue.
        status_dir = runtime_dir / STATUS_DIR
        # ARC 054. Created at boot for the reason `status/` is: an onset state
        # read against a directory that does not exist would count as unreadable
        # for a reason that has nothing to do with whether a window opened.
        onset_dir = runtime_dir / ONSET_DIR
        for directory in (
            runtime_dir,
            inbox_dir,
            outbox_dir,
            completions_dir,
            status_dir,
            onset_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        publisher = HeartbeatPublisher(runtime_dir / HEARTBEAT_NAME)
        go_timeout = (
            go_timeout_from_config()
            if args.go_timeout is None
            else float(args.go_timeout)
        )
        loop = LimiterLoop(
            heartbeat=publisher,
            heartbeat_interval_s=interval,
            tick_interval_s=tick,
            go_timeout_s=go_timeout,
            max_ticks=max(0, int(args.max_ticks)),
        )
        # ARC 042. Opened BEFORE the loop runs and a failure REFUSES THE BOOT:
        # §12.10's go_timeout row gates money, and a Limiter that cannot write
        # its evidence plane must not start rather than trade unrecorded. This
        # is the boot half of §12.4 — the RUNNING half (a WAL that goes
        # disk-critical mid-run) is the WAL's own policy and is contained in
        # `Plane1Booker.book_new_firings`, which never kills the tick.
        wal_path = (
            runtime_dir / PLANE1_WAL_NAME
            if args.plane1_wal is None
            else Path(args.plane1_wal)
        )
        wal = Plane1Wal(wal_path)
        booker = Plane1Booker(loop, wal)
        # ARC 046. §11.3's ledger and §3's terminal handlers, held by the
        # PROCESS. Both are constructed here and NEITHER is modified by this
        # arc: `nixrisk/reservations.py` and `nixrisk/outcomes.py` are
        # byte-identical across ARC 046 and that is asserted with
        # `git hash-object`, not claimed. The whole change is that something
        # with a pid now owns them and the loop now calls one of them.
        #
        # The ledger writes §12.10's reservation rows through the SAME
        # `Plane1Port` the booker holds — §9's sole-writer split, one process,
        # one WAL. A second writer would be the thing §9 forbids outright.
        reservations = ReservationLedger(wal)
        outcomes = OrderOutcomes(
            reservations,
            clock=time.time,
            pending_ack_timeout_s=pending_ack_timeout_from_config(),
        )
        # ARC 047. §2A:75's fill path, held by the PROCESS. Nine collaborators,
        # every one of them shipped and gated arcs ago and none of them edited
        # here — see `FillPath`. It shares the ONE `ReservationLedger` above
        # rather than constructing a second: §3's Σ is one number and a fill that
        # converted a reservation in a private book would leave the number every
        # capital rule reads untouched.
        fills = FillPath(
            reservations=reservations,
            balance=float(args.account_balance),
            deployable_fraction=deployable_fraction_from_config(),
            tick_size=_tick_sizes(args.tick_size),
            clock=time.time,
        )
        dispatcher = CompletionDispatcher(outcomes, fills=fills.sink)
        # ARC 053. §4's pending-timeout resolution, held by the PROCESS. It
        # shares the ONE `OrderOutcomes` above rather than constructing a second:
        # `due_for_status_query` reads the ledger's own TAKEN set, and a poller
        # with a private handler would sweep a different set from the one Σ is
        # derived from. `outcomes.py` and `reservations.py` are byte-identical
        # across this arc — asserted with `git hash-object`, not claimed — and
        # the whole change is that something with a pid now polls them.
        status_query = DirectoryStatusQuery(status_dir)
        # ARC 053 / D3.463. Read at BOOT and refused there if unreadable, for the
        # reason every other knob in this block is: §12A's lifecycle is
        # boot-loaded and restart-only, and a ceiling re-read per command would
        # let an edit change what the running process approves without a restart.
        signal_max_age_s = signal_max_age_from_config()
        # ARC 054. §3:173's onset sweep, held by the PROCESS.
        #
        # `PendingEntryBook` is D3.443's missing production `pending_entries()`,
        # and it is handed the THREE records the daemon's order state actually
        # lives in — §11.3's ledger, the approval book and §4:208's lock — rather
        # than a fourth of its own. `ProtectiveFlatten` is I11's proven executor,
        # CONSTRUCTED here and NOT modified: `nixrisk/flatten.py` is byte-identical
        # across this arc, asserted with `git hash-object`. It shares the ONE
        # `ReservationLedger` and the ONE `FinancialPictureBook` above for the
        # reason `FillPath` shares them — §3's Σ is one number, and a sweep that
        # released capital in a private book would leave the number every capital
        # rule reads untouched.
        #
        # Its broker is a `RecordedCancels` and NOT a broker: §3:173's sweep calls
        # `cancel_order` and nothing else (`cancel_entries_on_onset`'s own
        # docstring: *"It never calls `flatten`"*), and there is no vendor
        # integration in this tree to send one on. A SECOND instance from the one
        # `IocRemainder` holds, so §4's remainder cancel and §3:173's onset cancel
        # stay two readable facts.
        # ARC 055 / I1 ARC C1. THE BROKER NOW HAS §4's `flatten` VERB.
        #
        # ARC 054 constructed this as a `RecordedCancels` and said why: *"a
        # broker here that could flatten would be authority this arc withheld.
        # The missing verb is the guarantee, not an oversight."* C1 is the arc
        # that grants it, because a synthetic stop that breaches and cannot be
        # protectively closed is not a stop (D3.451, re-measured at this arc's
        # S1 on a live daemon: `hasattr(broker, "flatten") is False`).
        #
        # ONE object and ONE `ProtectiveFlatten`, shared by §3:173's onset sweep
        # and C1's stop exit, for the reason `FillPath` shares the ONE ledger:
        # §4's dual-authority arbiter (`request_close`) decides precedence by
        # reading and writing ONE `_closed` book, and a second executor would
        # arbitrate against a different book — so *protective always wins* would
        # hold twice, separately, over two halves of one truth. The onset sweep
        # still never flattens; `cancel_entries_on_onset` issues cancels and its
        # own docstring says *"It never calls `flatten`"*, which `check_flatten`
        # ARM 3 measures rather than assumes.
        onset_cancels = RecordedVenue()
        pending_book = PendingEntryBook(reservations, fills.approvals, loop)
        exits = ProtectiveFlatten(
            # `cast` still, and it still states something: `BrokerFlattenPort`
            # declares four verbs and this object has TWO — the SYNC pair §2A
            # invariant 5 forbids blocking. The two ASYNC reconcile reads
            # (`query_positions` / `query_balance`) are still absent, and their
            # absence is still the guarantee: C1 FIRES and SENDS, and the
            # reconcile that would need them is ARC D.
            broker=cast(BrokerFlattenPort, onset_cancels),
            ledger=reservations,
            picture=fills.picture,
            strategy=UnwiredExitSinks(),
            plane1=wal,
            scoring=UnwiredExitSinks(),
            clock=time.time,
        )
        onset = OnsetWatch(onset_dir, pending_book, exits, onset_cancels, fills)
        # ARC 055. §5:322's price ring, §4:190-196's trail and the breach->fire
        # path, held by the PROCESS. `StopWatch` is handed `fills.stops` — the
        # ONE `StopBook` the fill path arms into — and not a second book, for the
        # reason every collaborator above shares one: a driver maintaining stops
        # in a private book would trail stops no position has and leave the armed
        # ones exactly as D3.451 found them.
        prices = PriceRing()
        stop_watch = StopWatch(prices, fills.stops)
        # ARC 058 / I1 ARC D. THE ONE BOOK OF SENT-AND-UNRECONCILED FLATTENS.
        #
        # Shared by both producers for the reason every collaborator above is
        # shared: a closing exec report names a SYMBOL, and two books would let a
        # C1 breach's confirmation be matched against a C2 intent — or leave both
        # unmatched, which is the ARC 058 / S1 state this arc exists to end.
        # It is the DAEMON's record of what it sent, deliberately, rather than a
        # read of `ProtectiveFlatten`'s private `_closed`/`_intents`: §5:323 puts
        # the send on the sender thread and §5:322 drains the completion on the
        # loop thread, so the two halves are genuinely two events and this is
        # what joins them.
        in_flight_flattens = FlattenInFlightBook()
        stopwatch = StopWatchDriver(stop_watch, exits, loop, fills, in_flight_flattens)
        # ARC 057 / I1 ARC C2. §14's uncertainty producers, held by the PROCESS.
        #
        # `FreshnessTracker` is ARC 051's detector, CONSTRUCTED here and NOT
        # modified: `nixrisk/freshness.py` is byte-identical across this arc,
        # asserted with `git hash-object`. Its policy is `risks/staleness.
        # config.json` read through the detector's own loader — §12A is the
        # semantic authority for `price_stale_ms` and this process re-derives
        # nothing. The clock is INJECTED because the subject is a relationship
        # between two instants and a detector that read the wall clock
        # internally could only be tested by waiting (`freshness.py`'s own
        # argument, kept rather than restated).
        #
        # The watch is handed the ONE `FillPath` above rather than a second: §3's
        # position table is one table, and a scan reading a private copy would
        # flatten positions this daemon does not hold and miss the ones it does.
        # It is handed C1's ONE `StopWatch` too — read-only — so a position whose
        # synthetic stop has already fired an unreconciled protective flatten is
        # not flattened a second time under an uncertainty label.
        #
        # The DRIVER is handed the ONE `ProtectiveFlatten` §3:173's onset sweep
        # and C1's stop exit already share, for the reason they share it: §4's
        # dual-authority arbiter decides precedence by reading and writing ONE
        # `_closed` book, and a second executor would arbitrate against a
        # different book.
        uncertainty_watch = UncertaintyWatch(
            FreshnessTracker(
                staleness_policy_from_config(),
                clock=lambda: datetime.now(UTC),
            ),
            fills,
            reconcile_window_s=(
                reconcile_window_from_config()
                if args.reconcile_window is None
                else float(args.reconcile_window)
            ),
        )
        uncertainty_watch.attach_stop_watch(stop_watch)
        uncertainty = UncertaintyDriver(
            uncertainty_watch, exits, loop, in_flight_flattens
        )
        timeouts = PendingTimeoutPoller(outcomes, status_query, uncertainty_watch)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        print(
            f"{SITE}: refusing to boot the Limiter: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    # Wired after construction because both collaborators need the loop, and the
    # loop must own them rather than the other way round: §5:322's serial
    # processing means the inbox read and the command handling happen INSIDE the
    # tick, not on either collaborator's own schedule.
    # ARC 046. The completion read runs AFTER the command read inside the same
    # tick, and both feed ONE queue that ONE drain serves — §5:322's *processed
    # serially*, enforced by there being one queue rather than asserted. The
    # ORDER matters and is not a preference: a `reserve` command and the cancel
    # completion for that same order can land in one tick, and reading the
    # commands first means the reservation exists before the release for it is
    # dispatched. Reading completions first would make that pair's outcome
    # depend on filesystem timing, which is a race nobody declared.
    command_ingress = Inbox(inbox_dir, loop).drain
    completion_ingress = CompletionInbox(completions_dir, loop).drain

    def _read_both(tick: int) -> object:
        taken = command_ingress(tick)
        completion_ingress(tick)
        return taken

    # ARC 047. The §4:203-206 outcome push needs the loop (for §4:208's lock and
    # the tick number) and the outbox, so it is built here, after both exist.
    feedback = OpenFeedback(loop, outbox_dir)
    # ARC 058 / I1 ARC D. §4's CLOSE, held by the PROCESS.
    #
    # Nine collaborators and not one of them is new or edited: §3's picture book,
    # §4's `StopBook`, C1's `StopWatch`, §3/§4's origin join, §4:214's dedup —
    # THE SAME instance the entry dispatcher claims against, never a second, or a
    # re-delivered closing fill would be a duplicate to one book and news to the
    # other — §9's WAL, this arc's `ClosedFeedback` channel, the ONE in-flight
    # book both producers arm, and §4's arbiter read through its PUBLIC
    # `closed_record` accessor for the authoritative reason and FSM verdict.
    # `nixrisk/closing.py` is a LIBRARY; the whole change is that something with
    # a pid now owns it and the loop now calls it.
    closed_feedback = ClosedFeedback(loop, outbox_dir)
    closing = ClosingFillHandler(
        picture=fills.picture,
        stops=fills.stops,
        stop_watch=stop_watch,
        origins=fills.origins,
        dedup=dispatcher.dedup,
        strategy=closed_feedback,
        plane1=wal,
        in_flight=in_flight_flattens,
        arbiter=exits,
        clock=time.time,
    )
    completion_handler = CompletionHandler(dispatcher, feedback, uncertainty, closing)

    senders = ProtectiveSenders(stopwatch, uncertainty)
    loop.attach(
        # ARC 042: the booking runs FIRST inside the tick, then the inbox read.
        # `Plane1Booker.before` composes the two rather than folding the write
        # into the reader — see its docstring for why it is one tick behind the
        # firing and why nothing is lost to that.
        #
        # ARC 053: and §4's pending-timeout poll runs LAST inside the same tick,
        # composed the same way. The resulting order is
        #   book firings -> read commands -> read completions -> poll overdue
        # and every step of it is deliberate. Polling AFTER the reads means a
        # terminal completion sitting in this tick's directory resolves its order
        # before the poll would ask the venue about it, so the daemon does not
        # spend a §4 query on an order whose answer is already on disk.
        # ARC 054: and §3:173's onset poll runs FIRST inside the tick, ahead of
        # the ingress reads. The resulting order is
        #   poll onset -> book firings -> read commands -> read completions
        #   -> poll overdue
        # and the onset's position is the decision `OnsetWatch.before` records:
        # a `reserve` arriving in the same tick as a declared onset is taken
        # AFTER the sweep, so §3's branch-0 gate answers it rather than the
        # sweep pretending to.
        # ARC 055: and §5:322's price poll runs FIRST of all, ahead of even the
        # onset sweep. The resulting order inside one tick is
        #   poll prices -> poll onset -> book firings -> read commands
        #   -> read completions -> poll overdue
        # and the poll's position is the decision `StopWatchDriver.before`
        # records: §4's protective exit always wins, so the breach that is about
        # to release capital is detected before this tick's commands can approve
        # anything against it. The FIRE is not here — it is handed to §5:323's
        # sender thread by `sender_send` below, because it takes a lock and
        # writes a row and the hot loop never blocks (I9, §5:323).
        # ARC 057: and §14's uncertainty producers wrap ALL of it. The
        # resulting order inside one tick is
        #   scan open positions -> poll prices -> poll onset -> book firings
        #   -> read commands -> read completions -> poll overdue
        #   -> sweep reconciliation deadlines -> HAND every detected uncertainty
        # and both ends of that wrapper are decisions `UncertaintyDriver.before`
        # records. The SCAN is outermost for `StopWatchDriver.before`'s reason —
        # §4's protective exit always wins, so a position that cannot be managed
        # is detected before this tick's commands can approve anything new
        # against the capital it is about to release. The HAND is last so the
        # three EVENT-DRIVEN conditions, detected while the rest of the tick
        # ran, reach §5:323's sender in the SAME tick.
        ingress=uncertainty.before(
            stopwatch.before(onset.before(booker.before(timeouts.before(_read_both))))
        ),
        handler=LoopHandler(
            CommandHandler(
                loop,
                outbox_dir,
                reservations,
                dispatcher,
                fills,
                timeouts,
                onset,
                pending_book,
                signal_max_age_s,
                prices,
                stopwatch,
                uncertainty,
                closing,
                closed_feedback,
            ),
            completion_handler,
        ).handle,
        # ARC 055. WHERE THE PROTECTIVE FLATTEN IS ACTUALLY SENT. On §5:323's
        # low-priority thread, never on the loop: `ProtectiveFlatten.fire` takes
        # the §4 arbitration lock and appends a §12.10 row, and *the hot loop
        # never blocks*.
        # ARC 057: TWO producers now share §5:323's one sender. Routed by
        # PAYLOAD TYPE and not by a flag: each `send` returns immediately on a
        # payload that is not its own dataclass, so the queue stays the single
        # boundary §5:322-323 describes and neither driver can fire on the
        # other's firing. A dispatcher that switched on a string would be a
        # third place the two could be confused.
        sender_send=senders.send,
    )

    boot_ts = time.time()
    runtime_path = runtime_dir / RUNTIME_NAME
    _write_json_atomically(
        runtime_path,
        _runtime_record(
            loop,
            boot_ts=boot_ts,
            stopped_ts=None,
            booker=booker,
            reservations=reservations,
            dispatcher=dispatcher,
            fills=fills,
            feedback=feedback,
            timeouts=timeouts,
            onset=onset,
            book=pending_book,
            signal_max_age_s=signal_max_age_s,
            prices=prices,
            stopwatch=stopwatch,
            uncertainty=uncertainty,
            closing=closing,
            closed_feedback=closed_feedback,
        ),
    )
    _install_signal_handlers(loop)

    stop = loop.run()

    # The TAIL booking. The ingress books the previous tick's firings, so a
    # breaker that fired on the LAST tick before the stop would otherwise leave
    # a released lock with no §9 row — the exact D3.425 shape, surviving in the
    # one tick this arc could not reach from inside the loop. Idempotent by the
    # same key set, so a firing already booked in the tick is not booked twice.
    booker.book_new_firings()

    _write_json_atomically(
        runtime_path,
        _stop_record(
            loop,
            stop,
            boot_ts=boot_ts,
            stopped_ts=time.time(),
            booker=booker,
            reservations=reservations,
            dispatcher=dispatcher,
            fills=fills,
            feedback=feedback,
            timeouts=timeouts,
            onset=onset,
            book=pending_book,
            signal_max_age_s=signal_max_age_s,
            prices=prices,
            stopwatch=stopwatch,
            uncertainty=uncertainty,
            closing=closing,
            closed_feedback=closed_feedback,
            malformed=tuple(completion_handler.malformed),
            closing_refusals=tuple(completion_handler.closing_refusals),
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
