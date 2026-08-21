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
import json
import os
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Final

import risk_config
from nixrisk.completions import (
    CompletionDispatcher,
    DispatchResult,
    Disposition,
    MalformedCompletion,
    parse_completion,
)
from nixrisk.execution import ExecutionLedger
from nixrisk.fills import (
    ApprovedOrderBook,
    FillHandler,
    IocRemainder,
    LimiterFillSink,
)
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
from nixrisk.seam import EventKind, EventRow, ProposedOrder, Side, StopMode
from nixrisk.stops import StopBook
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
VERBS: Final[tuple[str, ...]] = (
    VERB_REGISTER,
    VERB_GO,
    VERB_STATUS,
    VERB_RESOLVE,
    VERB_RESERVE,
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
    * **It does not maintain the stop.** §4's trailing ratchet is
      `StopBook.maintain`, driven by the price tick, and this daemon has no price
      feed. A FIXED stop is static forever and is therefore fully served; a
      TRAILING stop is ARMED here and never ratcheted, which is named debt.
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
    ) -> None:
        self._dispatcher = dispatcher
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
        result = self._dispatcher.dispatch(completion)
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
class CommandHandler:
    """Turns one `RawCommand` into one reply file. NEVER RAISES.

    Fail-closed and contained (directive 4, and `nixrisk/loop.py`'s own
    containment argument): every refusal is a reply with `accepted: false` and a
    reason naming the spec coordinate it refused under. A command that could kill
    this process would be a remote kill switch on the process §12.1:604 has the
    Sentinel watching, so an unparsable file is answered, not fatal.
    """

    # R0913/R0917 refused with a reason: SEVEN parameters and six of them are
    # COLLABORATORS this process owns and hands in — the loop, the outbox, §11.3's
    # ledger, §5:322's dispatcher, §4's fill path and §4's timeout poller — plus
    # one §12A ceiling read at boot. Bundling them into a config object would put
    # a container between this handler and the objects whose ABSENCE it reports
    # differently from their emptiness (`_picture()`'s `None`-vs-0.0 argument, and
    # check contract rule 10 underneath it), and every one is optional precisely
    # so that difference stays visible.
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        loop: LimiterLoop,
        outbox: Path,
        reservations: ReservationLedger | None = None,
        dispatcher: CompletionDispatcher | None = None,
        fills: FillPath | None = None,
        timeouts: PendingTimeoutPoller | None = None,
        signal_max_age_s: float | None = None,
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
        #: ARC 053. §4's pending-timeout poller, optional on the same argument:
        #: `timeouts: null` says *this build does not poll* and is a different
        #: fact from a poller that has run and found nothing due.
        self._timeouts = timeouts
        #: ARC 053 / D3.463. `None` means this build enforces NO signal-age
        #: ceiling, and it is reported as `null` rather than as a number so a
        #: reader cannot mistake *unbounded* for *bounded at something*. `main`
        #: always supplies one; the default exists for the ARC 040 CLI readers.
        self._signal_max_age_s = signal_max_age_s

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
            approved = (
                f"; the order is HELD (stop_ticks={order.stop_ticks}, "
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

    def __init__(self, outcomes: OrderOutcomes, query: DirectoryStatusQuery) -> None:
        self._outcomes = outcomes
        self._query = query
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
        for record in records:
            disposition = getattr(record.disposition, "value", "")
            if disposition == "released":
                self.resolved += 1
            elif disposition == "refused":
                self.refused += 1
            else:
                self.held += 1
        return len(records)

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Wrap the loop's ingress so the poll runs AFTER the reads, same tick."""

        def _ingress(tick: int) -> object:
            taken = inner(tick)
            self.poll_due()
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
        }


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


def _runtime_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
    signal_max_age_s: float | None = None,
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
        #: ARC 053 / D3.463. The signal-age ceiling this process booted with, in
        #: the record an out-of-process reader opens. `null` means UNBOUNDED and
        #: says so, because *no ceiling* and *a ceiling of zero* are opposite
        #: facts and a missing key would read as neither.
        "signal_max_age_s": signal_max_age_s,
        "stopped_ts": stopped_ts,
    }


def _stop_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
    signal_max_age_s: float | None = None,
    malformed: tuple[str, ...] = (),
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
        signal_max_age_s=signal_max_age_s,
    )
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
        for directory in (
            runtime_dir,
            inbox_dir,
            outbox_dir,
            completions_dir,
            status_dir,
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
        timeouts = PendingTimeoutPoller(outcomes, status_query)
        # ARC 053 / D3.463. Read at BOOT and refused there if unreadable, for the
        # reason every other knob in this block is: §12A's lifecycle is
        # boot-loaded and restart-only, and a ceiling re-read per command would
        # let an edit change what the running process approves without a restart.
        signal_max_age_s = signal_max_age_from_config()
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
    completion_handler = CompletionHandler(dispatcher, feedback)
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
        ingress=booker.before(timeouts.before(_read_both)),
        handler=LoopHandler(
            CommandHandler(
                loop,
                outbox_dir,
                reservations,
                dispatcher,
                fills,
                timeouts,
                signal_max_age_s,
            ),
            completion_handler,
        ).handle,
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
            signal_max_age_s=signal_max_age_s,
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
            signal_max_age_s=signal_max_age_s,
            malformed=tuple(completion_handler.malformed),
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
