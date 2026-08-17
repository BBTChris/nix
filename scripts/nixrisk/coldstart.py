"""§4's cold-start reconciliation — the registration gate and its market guard.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 029 / sub-agent D. Implements the FROZEN `ColdStartPort` declared in
`scripts/nixrisk/seam.py`; it changes neither that port nor any other seam type.
Nothing here is a second authority — the seam fixes the vocabulary
(`BrokerTruth`, `FlattenTrigger`), §4 fixes the reconciliation discipline, and
this module is the ordering logic that keeps them true.

------------------------------------------------------------------------------
THE PROPERTY THIS MODULE EXISTS TO HOLD — and why it is SYNCHRONOUS (§4, V34)
------------------------------------------------------------------------------
§4, locked: on start the local state is empty and TRUSTLESS. The Limiter
**actively queries the broker** the moment broker-order has a session — the true
open-position set AND balance in one poll — and *"at cold start the broker's
answer is the record, not a reconciliation against one"*. That query **gates
registration**: no strategy registers until a provably-flat assertion has passed.

The gate is an ORDERING property, which is why the seam declares `ColdStartPort`
synchronous and why this class is too. An awaitable admission gate is a
suspension point during which a registration could interleave, admitting a
strategy against unproven state — and `restart = flat, always` (§14) is not a
preference that tolerates a race. So `reconcile` and `register` are plain calls:
between the flat assertion and the first admission there is no `await` a
registration can slip through.

------------------------------------------------------------------------------
"GATES REGISTRATION" IS ONLY FALSIFIABLE AGAINST AN ATTEMPT (§0a, MEASURED)
------------------------------------------------------------------------------
The brief states, as a hypothesis to measure: *"gates registration" is
unfalsifiable unless something attempts to register.* It is CORRECT, and the
measurement is in `test_coldstart.py`: `registration_admitted()` is a bool, and a
test that only reads it green-lights a `register()` that ignores the flag
entirely — a bool-only assertion passes against a gate that does not gate. So
this module exposes `register()` as the surface a strategy actually drives, and
it RAISES `RegistrationRefused` naming the reason while not-yet-flat. The refusal
is the property; reading the flag is a proxy for it.

------------------------------------------------------------------------------
THE MARKET-TRADABLE GUARD HAS TWO HALVES (§4, D4, MEASURED)
------------------------------------------------------------------------------
Flatten fires MARKET orders, so it needs an open, tradable market. If the box
comes up to an open position while the market is closed or halted, the system
does **NOT** fire into a shut market — it **holds in HALT with a loud alert** and
flattens the instant the market is tradable. The brief's hypothesis — *a drill
with the market always open measures NEITHER half* — is CORRECT: an always-open
run never reaches `hold_in_halt` (the HALT half) and never re-flattens on reopen
(the flatten half). `test_coldstart.py` drives both: held-in-HALT while closed,
and flattened once the same box's market reopens.

The guard lives on `flatten_to_flat` itself, not only in the reconcile flow: the
verb REFUSES to fire into a shut market and says so, so the guard is a property of
the flatten primitive and cannot be bypassed by a caller that reaches it directly.

------------------------------------------------------------------------------
WHICH TRIGGER AN INHERITED POSITION FLATTENS UNDER — ORPHAN, not UNCERTAINTY
------------------------------------------------------------------------------
§3:169's trigger set names both `orphan` and `uncertainty`. A cold-start
inherited position is not UNCERTAINTY — broker truth is definite, the position
provably exists — it is ORPHAN: a live position that no registered strategy owns,
which is exactly what cold start finds before any registration exists. The
executor chooses the trigger; `flatten_to_flat` returns what it fired. This module
records the reasoning so a future reader does not mistake a definite ownerless
position for an indeterminate one.

------------------------------------------------------------------------------
§12.1:612's SENTINEL MARKER REPLAY LIVES HERE (ARC 034 / sub-agent B)
------------------------------------------------------------------------------
*"On next boot, cold-start reconciliation reads the marker and books the flatten
into the real event log retroactively (rows tagged `source=sentinel`), then
archives the marker."* The spec names THIS component, so the replay is a method
on this class rather than a second boot-time reader: §9's sole-writer invariant
means the retroactive rows must ride the Limiter's own `Plane1Port`, and a
separate replayer would be a second thing that books money rows.

It runs FIRST inside `reconcile`, before the broker is polled, because what the
Sentinel did happened on the PREVIOUS boot. It does not decide anything about the
position an interrupted flatten names — §4's ordinary broker-truth reconcile
below is the authority on that and runs on this same boot.

The port is OPTIONAL. A box that has never run a Sentinel has no marker, and
requiring the reader would force every caller to construct one for a file that
does not exist.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO — stated, so no green here implies it
------------------------------------------------------------------------------
It does not OPEN the broker session (§2A's port owns that) — it is handed a
`BrokerSessionPort` already able to poll. It does not fire the market orders
itself: execution of any flatten is Limiter-only, and the injected
`FlattenExecutorPort` is where that execution lives. It does not decide the global
HALT flag's full §12.5 semantics or auto-clear (R4) — it is handed a
`HaltAlertPort` and raises HALT through it. It does not build the session calendar
that answers `market_tradable` (R4); it reads a port. And the frozen seam's
`EventKind` has no `COLD_START` member on purpose (see its docstring), so the
cold-start outcome is booked under the existing `BOOT` kind and the dedicated kind
is an integration debt, not a member quietly invented here.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
# pylint: disable=too-many-positional-arguments
# §4's reconciliation takes the ports it reconciles ACROSS — broker session,
# flatten executor, halt alert, the projection reader — and each is passed
# explicitly so a test can substitute one. Collapsing them into a config object
# would hide which port a given drive actually exercised.
import dataclasses
import enum
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

# ARC 034 / sub-agent B. The import edge runs `nixrisk -> nixsentinel`, and the
# DIRECTION is the safety property. §12.1:603 requires the Sentinel to sit on a
# separate code path so that a defect which kills the Risk Engine cannot take its
# watcher with it; that forbids `nixsentinel -> nixrisk`, and says nothing about
# this way round. Cold start runs when the Sentinel is not running, on the same
# boot that the Sentinel is absent from, so nothing here is in the deadman's
# import graph. `nixsentinel.seam` imports only `enum`, `dataclasses` and
# `typing`; `nixsentinel.marker` adds `json`, `os` and `time`.
from nixsentinel.marker import pending_acts, unbracketed
from nixsentinel.seam import MarkerRecord, MarkerReplayPort

# ARC 035 / sub-agent B. §12.5:637 names cold-start reconciliation as the
# thing that books a Limiter-down HALT retroactively, so the CALL lives here
# and the booking stays in `nixrisk.halt`, beside the marker it reads. The
# edge is acyclic: `halt.py` imports only stdlib and `nixrisk.seam`.
from nixrisk.halt import HaltMarker, replay_markers
from nixrisk.seam import (
    BrokerTruth,
    EventKind,
    EventRow,
    FlattenTrigger,
    Plane1Port,
    PositionRow,
)

#: The `strategy_id` a system-level Plane-1 row carries. Cold-start reconciliation
#: is not owned by any strategy — it runs before any strategy registers — so its
#: §9 row cannot name one. A sentinel actor is honest where borrowing a real
#: strategy_id would attribute a system boot to a strategy that has not registered.
SYSTEM_ACTOR = "__system__"

#: §12.1:612-613's tag, transcribed rather than invented: *"books the flatten
#: into the real event log retroactively (rows tagged `source=sentinel`)"*.
#: `nixrisk/halt.py` uses `marker_replay` for the §12.5:637 HALT rows, and the
#: two must stay distinct — a reader has to be able to tell a retroactive HALT
#: from a retroactive emergency flatten by the field the spec names.
SOURCE_SENTINEL = "sentinel"


class ColdStartError(RuntimeError):
    """Base for every refusal this reconciler raises. Never caught internally."""


class RegistrationRefused(ColdStartError):
    """A `register` attempt before the provably-flat assertion has passed.

    §4: no strategy registers until cold start asserts flat. This is raised — not
    returned — because a strategy that ignored the refusal and proceeded would be
    trading against unproven state, which is the exact hazard the gate exists to
    prevent. It NAMES the state so the caller learns WHY, not merely that it was
    refused (check contract v2 §11: assert the reason, never the code alone).
    """


# ---------------------------------------------------------------------------
# The collaborators this reconciler stands on (injected, never constructed here)
# ---------------------------------------------------------------------------
#
# R0903 (too-few-public-methods) disabled: each is a Protocol declaring exactly
# the surface §4 gives it. A second method would be a port doing two jobs.
# pylint: disable=too-few-public-methods


@runtime_checkable
class BrokerSessionPort(Protocol):
    """§4's broker truth source. ONE poll returns positions AND balance together.

    `poll_truth` pulls both halves in the same motion because §4 requires it: a
    balance read at one instant against positions read at another is exactly the
    stale-balance tear §3's atomicity rule exists to prevent. `market_tradable`
    carries a REASON alongside the flag so the held-in-HALT alert can name why the
    market is shut (weekend, session gap, exchange halt).
    """

    def poll_truth(self) -> BrokerTruth:
        """Positions + balance + one stamp, in a single broker round-trip."""

    def market_tradable(self) -> tuple[bool, str]:
        """`(tradable, why)`. Closed/halted ⇒ `(False, reason)`."""


@runtime_checkable
class FlattenExecutorPort(Protocol):
    """Where the Limiter-only flatten EXECUTION lives (§14: execution is Limiter).

    Handed the broker truth, it fires a market order to close every inherited
    position and returns the `FlattenTrigger`s it fired under. Injected rather than
    inlined so the actual market-order path — the wire — is a collaborator this
    ordering logic does not itself own.
    """

    def flatten(self, truth: BrokerTruth) -> tuple[FlattenTrigger, ...]:
        """Close every inherited position. Returns the triggers fired."""


@runtime_checkable
class HaltAlertPort(Protocol):
    """Holds the system in HALT with a loud (§12.9 Critical) alert.

    One verb, because the two are inseparable at cold start: §4 says the
    held-in-HALT state is announced with a LOUD alert, and §12.5 lists cold-start
    -in-HALT among the conditions that page immediately. A hold that set the flag
    without alerting would be a silent HALT, which is the failure mode §12.9's
    critical tier exists to prevent.
    """

    def hold_in_halt(self, reason: str) -> None:
        """Set the global HALT and raise the Critical alert, with the reason."""


@runtime_checkable
class ProjectionPort(Protocol):
    """§9's REBUILDABLE positions projection, as cold start reads it.

    §9: *"Positions table = projection (rebuildable; dashboard + reconciliation
    read it)."* This is the "reconciliation reads it" half.

    ONE verb, and it is `rebuild` rather than `read`. At cold start the local
    state is empty and TRUSTLESS (§4) — a projection READ without re-folding is
    exactly the stale local state §4 says not to trust, and a port that offered
    only a read would make trusting it the path of least resistance.

    It returns `PositionRow` — the same type `BrokerTruth` carries — so the two
    sides of the reconciliation are the same shape and the comparison is a
    comparison rather than a translation. The implementation over a real Plane-1
    database is `nixrisk.projection.PostgresProjection`; nothing here imports it,
    because a reconciler that constructed its own database handle would decide
    which database the money truth lives in.
    """

    def rebuild(self) -> tuple[PositionRow, ...]:
        """Re-fold the event log and return the OPEN positions it yields."""


# ---------------------------------------------------------------------------
# §12.1:612's marker replay — the rows, built as pure functions
# ---------------------------------------------------------------------------
#
# Module-level and side-effect-free on purpose. They turn a marker record into
# `EventRow`s and touch nothing; the ONE place a row reaches Plane 1 is
# `ColdStart.replay_sentinel_marker`, through the Limiter's own sole-writer port
# (§9:557). A builder that could also write would be a second writer wearing a
# helper's name.


def _sentinel_row(  # pylint: disable=too-many-arguments
    before: MarkerRecord,
    symbol: str,
    now: float,
    *,
    interrupted: bool,
    ack_ok: str,
    ack_detail: str,
) -> EventRow:
    """One retroactive §12.10 row for one symbol the Sentinel closed, or tried to.

    `ts` is the SENTINEL's stamp, never `now`. A retroactive row carrying the
    boot time would move a money event by however long the box was down, and the
    delay itself is preserved separately in `booked_at` so it is on the record
    rather than lost in the difference.
    """
    reason = (
        f"retroactive: the §12.1 Sentinel fired an emergency flatten on {symbol} "
        f"while the Limiter was dead (heartbeat silent {before.heartbeat_age_s:.3f}s, "
        f"cause {before.cause.value})"
    )
    if interrupted:
        reason += (
            " — and the marker holds NO 'after' record, so this Sentinel died "
            "MID-FLATTEN. The close is UNCONFIRMED; §4's broker-truth reconcile "
            "on this same boot is the authority on the resulting position"
        )
    return EventRow(
        kind=EventKind.PROTECTIVE_EXIT,
        ts=before.ts,
        strategy_id=SYSTEM_ACTOR,
        reason=reason,
        fields={
            "symbol": symbol,
            "source": SOURCE_SENTINEL,
            "retroactive": "true",
            "interrupted": "true" if interrupted else "false",
            "trigger": FlattenTrigger.SENTINEL.value,
            "cause": before.cause.value,
            "ack_ok": ack_ok,
            "ack_detail": ack_detail,
            "sentinel_pid": str(before.sentinel_pid),
            "heartbeat_age_s": repr(before.heartbeat_age_s),
            "booked_at": repr(now),
        },
    )


def _act_rows(
    before: MarkerRecord, after: MarkerRecord | None, now: float
) -> list[EventRow]:
    """Every row one bracketed (or interrupted) act produces, in symbol order."""
    if after is None:
        return [
            _sentinel_row(
                before,
                symbol,
                now,
                interrupted=True,
                ack_ok="unknown",
                ack_detail="no 'after' record — the Sentinel did not survive the act",
            )
            for symbol in before.symbols
        ]
    by_symbol = {ack.symbol: ack for ack in after.acks}
    # UNION, not the `before` list alone: a venue may acknowledge a symbol the
    # Sentinel had not enumerated (a leg opened between the read and the send),
    # and a replay that booked only what was expected would drop the surprise —
    # which is the one thing an operator most needs to see.
    symbols = tuple(dict.fromkeys(before.symbols + tuple(by_symbol)))
    rows: list[EventRow] = []
    for symbol in symbols:
        ack = by_symbol.get(symbol)
        rows.append(
            _sentinel_row(
                before,
                symbol,
                now,
                interrupted=False,
                ack_ok="true" if ack is not None and ack.ok else "false",
                ack_detail=(
                    ack.detail
                    if ack is not None
                    else "no broker acknowledgement for this symbol in the "
                    "'after' record — the close was attempted and never answered"
                ),
            )
        )
    return rows


def sentinel_replay_rows(
    records: tuple[MarkerRecord, ...], now: float
) -> tuple[EventRow, ...]:
    """Every Plane-1 row a marker's flatten records produce, in write order."""
    rows: list[EventRow] = []
    for before, after in pending_acts(records):
        rows += _act_rows(before, after, now)
    return tuple(rows)


def _sentinel_summary_row(records: tuple[MarkerRecord, ...], now: float) -> EventRow:
    """ONE §12.10 cold-start row saying that a marker was found and replayed.

    Booked under `COLD_START` and not under an exit kind, because that is what it
    is: cold-start reconciliation's own account of what it read. It is also where
    the NON-FLATTEN wake-ups land — the `HEARTBEAT_LOST_NO_POSITIONS` and
    `HEARTBEAT_RECOVERED` records — which are deliberately NOT booked as exits.
    A wake that did not flatten is not a flatten, and putting it in the money
    record under an exit kind would place a non-event in §9's ledger; it stays
    countable here and readable in full in the archived marker.
    """
    acts = pending_acts(records)
    interrupted = sum(1 for _before, after in acts if after is None)
    quiet = unbracketed(records)
    return EventRow(
        kind=EventKind.COLD_START,
        ts=now,
        strategy_id=SYSTEM_ACTOR,
        reason=(
            f"§12.1 Sentinel marker replayed: {len(records)} record(s), "
            f"{len(acts)} flatten act(s) of which {interrupted} INTERRUPTED, "
            f"{len(quiet)} wake(s) that decided not to flatten. Marker archived"
        ),
        fields={
            "source": SOURCE_SENTINEL,
            "records": str(len(records)),
            "acts": str(len(acts)),
            "interrupted": str(interrupted),
            "non_flatten_wakes": str(len(quiet)),
            "causes": ",".join(sorted({record.cause.value for record in quiet})),
        },
    )


# ---------------------------------------------------------------------------
# The outcome of one reconcile pass
# ---------------------------------------------------------------------------


class ColdStartState(enum.Enum):
    """Where cold-start reconciliation stands. Three states, and no fourth.

    `PENDING` is the trustless start: nothing polled, nothing admitted.
    `HELD_IN_HALT` is an inherited position the guard would not fire on (market
    shut) or a flatten that did not reach flat — either way registration stays
    refused. `FLAT_ASSERTED` is the ONLY state that admits registration, and it is
    reached only through a broker-confirmed flat. There is deliberately no
    "adopted" state: an inherited position is never adopted (§4).
    """

    PENDING = "pending"
    HELD_IN_HALT = "held_in_halt"
    FLAT_ASSERTED = "flat_asserted"


@dataclasses.dataclass(frozen=True)
class ReconcileOutcome:
    """One reconcile pass, recorded. Immutable — a later pass produces a new one.

    `admitted` is redundant with `state is FLAT_ASSERTED` by construction, and
    that is the point: a consumer can read the boolean the gate turns on without
    knowing the state machine, and the two can be asserted equal so a state that
    forgot to flip the flag is caught.
    """

    state: ColdStartState
    truth: BrokerTruth
    flattened: tuple[FlattenTrigger, ...]
    admitted: bool
    reason: str


# ---------------------------------------------------------------------------
# ARC 035 / sub-agent B — the CRASH GAP, and what heals it (§9, §4, §12.5)
# ---------------------------------------------------------------------------
#
# §9, verbatim: *"Enqueue -> durable local WAL -> shared-pool writer ->
# group-commit to Postgres. CRASH GAP HEALED BY STARTUP RECONCILIATION VS BROKER
# TRUTH."*
#
# The gap is structural and it is not a defect: group-commit exists precisely so
# the hot path does not wait on Postgres (§11.6), which means there is ALWAYS a
# window of rows that happened and have not committed. A crash inside that window
# leaves the projection BEHIND reality by however much was in flight.
#
# §4 already fixes what to do about the difference — *"any unexpected open
# position ⇒ flatten to flat before any strategy registers"*, *"we never adopt or
# reason about an inherited position"* — so this section adds NO new disposition.
# What it adds is the MEASUREMENT: naming the gap, so the `cold_start_outcome`
# row records what the record was missing rather than only what was done about it.
#
# **The broker may not know our `trade_id`.** It is our mint (§4), not the
# venue's. A broker adapter that cannot round-trip it returns positions whose
# trade_ids match nothing, and every one of them is then reported UNEXPECTED —
# which is the FAIL-CLOSED direction and is correct: §4 flattens an unowned
# position and never adopts one. It is recorded here so a future reader does not
# mistake a coarse match for a bug.


class GapKind(enum.Enum):
    """The three ways a rebuilt projection and broker truth can disagree."""

    #: At the broker, absent from the projection. The crash-gap signature: the
    #: fill happened and its row never committed. §4 flattens it.
    UNEXPECTED = "unexpected"
    #: In the projection, absent from the broker. The exit happened and its row
    #: never committed — or the Sentinel flattened it while we were down.
    VANISHED = "vanished"
    #: Both sides hold it and the sizes differ. A partial fill whose later legs
    #: are in the gap.
    SIZE = "size"


@dataclasses.dataclass(frozen=True)
class CrashGap:
    """One disagreement between the rebuilt projection and broker truth.

    Frozen and carrying BOTH sizes: a finding that recorded only "they differ"
    could not tell an under-reported position (dangerous — real exposure the
    record does not know about) from an over-reported one (stale, and merely
    wrong).
    """

    kind: GapKind
    trade_id: str
    symbol: str
    projection_size: int
    broker_size: int
    detail: str


def crash_gap(
    projection: Sequence[PositionRow], truth: BrokerTruth
) -> tuple[CrashGap, ...]:
    """§9's crash gap, MEASURED: the rebuilt projection against broker truth.

    Pure. Takes two position sets and returns their disagreements; it decides
    nothing and fires nothing, because §4 owns the disposition and a second
    authority over the same question is how two reconcilers end up disagreeing.

    Broker truth WINS wherever they differ — §4, locked: *"if projection and
    broker truth disagree beyond tolerance, broker wins and we correct."* There
    is no tolerance band on a contract count: a position is a whole number of
    contracts and "close enough" is not a state a futures account can be in.
    """
    ours = {row.trade_id: row for row in projection}
    theirs = {row.trade_id: row for row in truth.positions}
    gaps: list[CrashGap] = []
    for trade_id in sorted(set(theirs) - set(ours)):
        row = theirs[trade_id]
        gaps.append(
            CrashGap(
                kind=GapKind.UNEXPECTED,
                trade_id=trade_id,
                symbol=row.symbol,
                projection_size=0,
                broker_size=row.size,
                detail=(
                    f"broker holds {row.size} {row.symbol} under trade {trade_id} "
                    f"and the rebuilt projection has NO such position — the "
                    f"record is behind reality (§9 crash gap). §4: flatten, never "
                    f"adopt"
                ),
            )
        )
    for trade_id in sorted(set(ours) - set(theirs)):
        row = ours[trade_id]
        gaps.append(
            CrashGap(
                kind=GapKind.VANISHED,
                trade_id=trade_id,
                symbol=row.symbol,
                projection_size=row.size,
                broker_size=0,
                detail=(
                    f"the projection holds {row.size} {row.symbol} under trade "
                    f"{trade_id} and the broker reports none — the exit committed "
                    f"at the venue and its Plane-1 row did not. Broker wins (§4)"
                ),
            )
        )
    for trade_id in sorted(set(ours) & set(theirs)):
        ours_row, theirs_row = ours[trade_id], theirs[trade_id]
        if ours_row.size == theirs_row.size:
            continue
        gaps.append(
            CrashGap(
                kind=GapKind.SIZE,
                trade_id=trade_id,
                symbol=theirs_row.symbol,
                projection_size=ours_row.size,
                broker_size=theirs_row.size,
                detail=(
                    f"trade {trade_id} ({theirs_row.symbol}): the projection says "
                    f"{ours_row.size}, the broker says {theirs_row.size}. A fill "
                    f"leg in the crash gap. Broker wins (§4)"
                ),
            )
        )
    return tuple(gaps)


def unexpected(gaps: Sequence[CrashGap]) -> tuple[CrashGap, ...]:
    """§4's own category: at the broker, UNKNOWN to the record.

    A module function rather than a property on the record below, because `boot`
    itself needs it — the `cold_start_outcome` row names the unexpected trades —
    and a helper only the tests reached would be a verb with no production
    caller, which is the finding `check_uncalled_entry_points` exists to make.

    These are the positions §4 flattens: *"any unexpected open position ⇒ flatten
    to flat before any strategy registers … we never adopt or reason about an
    inherited position."*
    """
    return tuple(gap for gap in gaps if gap.kind is GapKind.UNEXPECTED)


@dataclasses.dataclass(frozen=True)
class BootReconciliation:
    """One whole boot: replay, rebuild, gap, and §4's disposition, in order.

    Every field is something that was MEASURED on this boot. `outcome` is §4's
    existing verdict object and is not restated here — a second copy of
    `admitted` in this record would be the mutable-fact restatement directive 3
    forbids, and the two could drift.
    """

    outcome: ReconcileOutcome
    #: The projection as REBUILT on this boot, from the log alone (§9).
    projection: tuple[PositionRow, ...]
    #: Broker truth as polled BEFORE any flatten fired. The pre-flatten poll is
    #: the only one the gap can be measured against: after the flatten the two
    #: sides agree by construction and the gap would read as zero.
    truth_before: BrokerTruth
    gap: tuple[CrashGap, ...]
    sentinel_rows: tuple[EventRow, ...]
    retroactive_halts: tuple[EventRow, ...]


# pylint: disable=too-many-instance-attributes
# NINE attributes: three injected collaborators (broker, flattener, halt), the
# required Plane-1 sink, and five pieces of the ordering state this class exists
# to hold — the state enum, the admission latch, the last broker truth, the poll
# counter that proves the one-motion query, and the admitted-registration list.
# None is behavioural accretion; each is one field the §4 gate needs to decide.
class ColdStart:
    """§4's cold-start reconciliation. Satisfies the frozen `ColdStartPort`.

    SYNCHRONOUS throughout, for the reason the seam gives: the gate is an ordering
    property and an awaitable admission gate is a window a registration can
    interleave through.

    Deliberately NOT a subclass of `ColdStartPort`. A `Protocol`'s method bodies
    are docstrings, so inheriting it means a verb this class forgot to override
    returns `None` silently — a gate whose `registration_admitted()` answered
    `None` reads as falsey and would look like a working refusal while measuring
    nothing. Conformance is proven by comparing signatures against the port
    instead, which is a measurement rather than a nominal claim.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        broker: BrokerSessionPort,
        flattener: FlattenExecutorPort,
        halt: HaltAlertPort,
        plane1: Plane1Port,
        sentinel_marker: MarkerReplayPort | None = None,
        projection: ProjectionPort | None = None,
        halt_marker: HaltMarker | None = None,
    ) -> None:
        self._broker = broker
        self._flattener = flattener
        self._halt = halt
        #: §12.1:612's replay side. OPTIONAL and defaulting to `None` because a
        #: box that has never run a Sentinel has no marker to replay, and a
        #: required port would force every caller to construct a reader for a
        #: file that does not exist. `None` means the replay is OFF and
        #: `replay_sentinel_marker` says so in its return rather than pretending
        #: it found nothing.
        self._sentinel_marker = sentinel_marker
        self._sentinel_replayed = False
        #: §9: the Limiter is the SOLE writer of Plane 1, and §12.10 books the
        #: cold-start outcome there. Required, never defaulted to a sink — a
        #: reconciler that quietly discarded its own held-in-HALT row would leave
        #: the one paging event with no durable record.
        self._plane1 = plane1
        self._state = ColdStartState.PENDING
        self._admitted = False
        self._last_truth: BrokerTruth | None = None
        #: Counts broker round-trips, so a test can prove `query_truth` pulls both
        #: halves in ONE motion rather than two reads that could tear (§4).
        self._polls = 0
        self._registered: list[str] = []
        #: §9's rebuildable projection. OPTIONAL: a box whose Plane-1
        #: database has never been built has no projection to rebuild, and a
        #: required port would force every caller to construct one for a
        #: table that does not exist. `None` is reported as `absent` in the
        #: cold-start row, never as a zero-row projection.
        self._projection = projection
        #: §12.5:637's marker. OPTIONAL for the same reason: most boots
        #: follow a clean shutdown and have no HALT to recover.
        self._halt_marker = halt_marker
        #: What `boot` learned, merged into the §12.10 cold-start row by
        #: `_book` and cleared immediately after. Empty on a bare
        #: `reconcile`, so that call's row is exactly what it always was.
        self._boot_fields: dict[str, str] = {}

    # -- the frozen port ----------------------------------------------------

    def query_truth(self) -> BrokerTruth:
        """Poll the broker for the true position set and balance, together.

        One round-trip, counted. At cold start the answer IS the record — there is
        no local state to reconcile it against — so the returned `BrokerTruth` is
        stored as the ground truth every later decision reads.
        """
        self._polls += 1
        truth = self._broker.poll_truth()
        self._last_truth = truth
        return truth

    def market_tradable(self) -> bool:
        """May a market order be fired right now? Closed/halted ⇒ False."""
        tradable, _why = self._broker.market_tradable()
        return tradable

    def flatten_to_flat(self, truth: BrokerTruth) -> tuple[FlattenTrigger, ...]:
        """Flatten every inherited position. Never adopt, never reason about.

        The MARKET-TRADABLE guard lives here, at the point of firing: flatten
        fires market orders, so a shut market makes this a REFUSAL, not a blind
        send (§4, D4). An already-flat truth flattens nothing and returns empty —
        never an adoption. Every inherited position closes under `ORPHAN`: it is a
        live position no registered strategy owns, which is definite, not
        uncertain.
        """
        if truth.is_flat:
            return ()
        tradable, why = self._broker.market_tradable()
        if not tradable:
            raise ColdStartError(
                f"refusing to flatten {len(truth.positions)} inherited "
                f"position(s) into a shut market ({why}) — §4's market-tradable "
                "guard: the system does NOT fire market orders into a "
                "closed/halted market; it holds in HALT until tradable"
            )
        return self._flattener.flatten(truth)

    def registration_admitted(self) -> bool:
        """Has the provably-flat assertion passed? Gates every registration."""
        return self._admitted

    # -- the driver and the registration surface ----------------------------

    def replay_sentinel_marker(self, now: float) -> tuple[EventRow, ...]:
        """§12.1:612-613's retroactive booking. Runs at NEXT BOOT, once.

        *"On next boot, cold-start reconciliation reads the marker and books the
        flatten into the real event log retroactively (rows tagged
        `source=sentinel`), then archives the marker."*

        THE ORDER IS THE PROPERTY, and it is the seam's own rule: read, book,
        make the rows DURABLE, and only then archive. Archiving first — or
        archiving on the strength of an `enqueue` that has not fsynced — would
        destroy the only account of an emergency flatten on the exact boot where
        the WAL then failed to reach the disk, which converts a recoverable
        replay into a silent gap in §9's record of money truth.

        An INTERRUPTED act — a `BEFORE` with no `AFTER` — is booked, flagged, and
        never discarded. It is the record of a Sentinel that died mid-flatten and
        it is the single most valuable line the file can hold. This method does
        NOT decide what to do about the position it names: §4's ordinary
        broker-truth reconcile below is the authority on that, it runs on this
        same boot, and inventing a second disposition here would be a second
        authority over the same question.

        Returns the rows booked; empty when there was no marker, which is the
        ordinary case and is not an error.
        """
        if self._sentinel_marker is None:
            return ()
        records = self._sentinel_marker.read_pending()
        if not records:
            self._sentinel_replayed = True
            return ()
        rows = list(sentinel_replay_rows(records, now))
        rows.append(_sentinel_summary_row(records, now))
        for row in rows:
            self._plane1.enqueue(row)
        self._plane1.sync_to_disk()
        self._sentinel_marker.archive()
        self._sentinel_replayed = True
        return tuple(rows)

    def book_retroactive_halts(self, now: float) -> tuple[EventRow, ...]:
        """§12.5:634-638's Limiter-down case. Runs at NEXT BOOT, once.

        Verbatim: *"if a HALT condition arises while the Limiter is unavailable
        (e.g. the Risk Engine itself is the crash-looping process), the system is
        already **fail-closed** — nothing reaches the broker without the Limiter
        — so no separate flag is needed for safety. The `HALT set` row is booked
        retroactively at next boot by cold-start reconciliation, same pattern as
        the Sentinel marker replay (§12.1): Plane-1 completeness holds without a
        second writer."*

        **Read what that says and what it does not.** The retroactive row exists
        for Plane-1 COMPLETENESS. It is NOT what makes the down-Limiter safe —
        the fail-closed architecture already did that, before this method ran and
        whether or not it ever runs. A reader who took this booking for the safety
        mechanism would conclude that a failure to replay leaves the box unsafe,
        and it does not: it leaves the RECORD incomplete, which is a different and
        smaller problem.

        The booking itself is `halt.replay_markers`, which lives beside the marker
        it reads and takes the Limiter's own `Plane1Port` as an argument. §12.5
        names cold-start reconciliation as the thing that calls it, so the CALL is
        here; a second boot-time reader would be the second writer §12.10 forbids.
        `halt.py`'s own module docstring recorded that *"nothing calls
        `replay_markers` at boot, because nothing in this tree HAS a boot"*. This
        is that boot.
        """
        if self._halt_marker is None:
            return ()
        return replay_markers(self._halt_marker, self._plane1, now)

    def boot(self, now: float) -> BootReconciliation:
        """ONE whole cold start, in the order the spec fixes between four sections.

        The order is not a convenience and each step is owed to a different
        paragraph:

        1. **§12.1:612 — the Sentinel marker replays FIRST.** What the Sentinel
           did happened on the PREVIOUS boot; a log whose retroactive rows landed
           after this boot's own reconciliation would read as if the emergency
           followed the recovery.
        2. **§12.5:637 — a HALT that arose while the Limiter was down is booked
           retroactively**, same pattern, same reason, same sole writer.
        3. **§9 — the projection is REBUILT FROM THE LOG**, including the rows
           steps 1 and 2 just added. Rebuilt rather than read: see `ProjectionPort`.
        4. **§9 — the CRASH GAP is measured** against a broker poll taken BEFORE
           anything is flattened. This is the only moment it can be measured: after
           §4 acts the two sides agree by construction and the gap reads as zero.
        5. **§4 — the ordinary reconcile decides and acts**, unchanged. It flattens
           an unexpected position before any registration, holds in HALT on a shut
           market, and books the `cold_start_outcome` row — which now carries the
           four numbers above, so §9's record says what the boot SAW and not only
           what it did.

        Step 5 polls the broker a second time, and that is correct rather than
        wasteful: §4 requires *"a direct broker balance + position poll in the same
        motion"* on EVERY reconciliation event, and the poll after a flatten is
        what turns "we sent a flatten" into "here is the CONFIRMED flat state".
        """
        sentinel_rows = self.replay_sentinel_marker(now)
        retroactive = self.book_retroactive_halts(now)
        rebuilt = self._projection is not None
        projection: tuple[PositionRow, ...] = (
            tuple(self._projection.rebuild()) if self._projection is not None else ()
        )
        truth_before = self.query_truth()
        gap = crash_gap(projection, truth_before)
        #: Merged into the `cold_start_outcome` row by `_book`. `absent` rather
        #: than `0` where there is no projection port at all: "nothing was
        #: rebuilt" and "the rebuild found nothing" are different facts and a
        #: zero would spell them the same way.
        self._boot_fields = {
            "sentinel_rows": str(len(sentinel_rows)),
            "retroactive_halts": str(len(retroactive)),
            "projection_rows": str(len(projection)) if rebuilt else "absent",
            "crash_gap": str(len(gap)),
            "crash_gap_kinds": ",".join(sorted({g.kind.value for g in gap})),
            "crash_gap_trades": ",".join(g.trade_id for g in gap),
            "unexpected_trades": ",".join(g.trade_id for g in unexpected(gap)),
        }
        try:
            outcome = self.reconcile(now)
        finally:
            self._boot_fields = {}
        return BootReconciliation(
            outcome=outcome,
            projection=projection,
            truth_before=truth_before,
            gap=gap,
            sentinel_rows=sentinel_rows,
            retroactive_halts=retroactive,
        )

    def reconcile(self, now: float) -> ReconcileOutcome:
        """Run one cold-start pass and return where it landed.

        Already flat ⇒ assert flat and admit. An unexpected open position on a
        TRADABLE market ⇒ flatten, RE-QUERY broker truth to confirm, admit only on
        a confirmed flat. An open position on a SHUT market ⇒ hold in HALT with the
        loud alert and admit nothing — the flatten waits for the market. Callable
        again from `HELD_IN_HALT`: that re-run is how the held position flattens
        the instant the market becomes tradable (§4, D4).

        §12.1:612 puts the Sentinel marker replay HERE, in cold-start
        reconciliation, and it runs FIRST — before the broker is queried. The
        ordering is chronological rather than convenient: what the Sentinel did
        happened on the PREVIOUS boot, and a Plane-1 log whose retroactive rows
        landed after this boot's own reconciliation would read as if the
        emergency followed the recovery. It runs once; the marker is archived,
        so a second call finds nothing.
        """
        if not self._sentinel_replayed:
            self.replay_sentinel_marker(now)
        truth = self.query_truth()
        if truth.is_flat:
            return self._admit(truth, (), now, "already flat")
        tradable, why = self._broker.market_tradable()
        if not tradable:
            return self._hold(
                truth,
                now,
                f"cold-start found {len(truth.positions)} inherited position(s) "
                f"while the market is NOT tradable ({why}) — holding in HALT and "
                "flattening the instant the market is tradable; NOT firing market "
                "orders into a shut market (§4 market-tradable guard)",
            )
        triggers = self.flatten_to_flat(truth)
        confirmed = self.query_truth()
        if confirmed.is_flat:
            return self._admit(confirmed, triggers, now, "flattened to flat")
        return self._hold(
            confirmed,
            now,
            f"cold-start flatten fired {tuple(t.value for t in triggers)} but the "
            f"broker still reports {len(confirmed.positions)} open position(s) — "
            "refusing to admit registration and holding in HALT (fail closed, "
            "§4 / directive 4: known state beats optimal state)",
        )

    def register(self, strategy_id: str, now: float) -> None:
        """A strategy's registration ATTEMPT. Refused until provably flat.

        This is the surface that makes the gate falsifiable: it is what a strategy
        drives, and it RAISES while not-yet-flat rather than reading a flag and
        hoping the caller checked it. The attempt is the claim — a drill where
        nothing registers proves nothing about a gate (§0a).
        """
        del now  # accepted for call-shape symmetry with the rest of the seam
        if not self._admitted:
            raise RegistrationRefused(
                f"{strategy_id}: registration REFUSED — the cold-start "
                f"provably-flat assertion has not passed (state="
                f"{self._state.value}). §4: no strategy registers until a "
                "provably-flat assertion has passed, and an inherited position is "
                "never adopted, however profitable"
            )
        self._registered.append(strategy_id)

    def registered(self) -> tuple[str, ...]:
        """Every strategy admitted so far. Empty until the gate opens."""
        return tuple(self._registered)

    @property
    def state(self) -> ColdStartState:
        """Where reconciliation stands. For evidence and the outcome record."""
        return self._state

    # -- internals ----------------------------------------------------------

    def _admit(
        self,
        truth: BrokerTruth,
        triggers: tuple[FlattenTrigger, ...],
        now: float,
        phrase: str,
    ) -> ReconcileOutcome:
        """The ONE place registration becomes admissible. Provably flat only."""
        self._state = ColdStartState.FLAT_ASSERTED
        self._admitted = True
        reason = (
            f"cold-start: provably flat ({phrase}); registration admitted "
            f"(§4 V34), broker balance {truth.balance!r}"
        )
        self._book(now, reason)
        return ReconcileOutcome(
            state=self._state,
            truth=truth,
            flattened=triggers,
            admitted=True,
            reason=reason,
        )

    def _hold(self, truth: BrokerTruth, now: float, reason: str) -> ReconcileOutcome:
        """Hold in HALT with the loud alert. Admits NOTHING (§4, directive 4)."""
        self._state = ColdStartState.HELD_IN_HALT
        self._admitted = False
        self._halt.hold_in_halt(reason)
        self._book(now, reason)
        return ReconcileOutcome(
            state=self._state,
            truth=truth,
            flattened=(),
            admitted=False,
            reason=reason,
        )

    def _book(self, now: float, reason: str) -> None:
        """§12.10's cold-start outcome row, on the sole Plane-1 writer (§9).

        Booked under `EventKind.COLD_START` (ARC 029 Stage 2.2). Sub-agent D built
        this against the FROZEN seam, whose `EventKind` had no `COLD_START` member,
        so the outcome rode `BOOT` and the dedicated kind was reported as owed. The
        integrator added `COLD_START` to the seam once this mechanism existed — the
        SPEC-A7 route — and the row now books under its own §12.10 kind.
        """
        self._plane1.enqueue(
            EventRow(
                kind=EventKind.COLD_START,
                ts=now,
                strategy_id=SYSTEM_ACTOR,
                reason=reason,
                fields={
                    "state": self._state.value,
                    "admitted": repr(self._admitted),
                    **self._boot_fields,
                },
            )
        )
