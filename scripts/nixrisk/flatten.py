"""§3/§4/§14's protective-flatten executor — the Limiter's EXIT half.

ARC 029 / sub-agent B. Built against the FROZEN `scripts/nixrisk/seam.py`
(`FlattenTrigger`, `TerminalPath`, the value types) and the FROZEN §2A broker
seam (`scripts/broker/broker_seam.py`). It changes neither, and re-declares no
frozen type: this module is the BEHAVIOUR the seam deliberately withheld
(seam.py: *"the protective-exit wiring to broker-order ... A Limiter that gates
but cannot exit is not a safety spine yet"*).

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document is
named on the line. `SPEC-A7` cites `docs/SPEC-AMENDMENTS.md`.

------------------------------------------------------------------------------
THE §14 INVARIANTS THIS MODULE IS ACCOUNTABLE TO
------------------------------------------------------------------------------
* **The exit/protective path has ZERO wire/delivery dependency.** §3's exit
  diagram is `Limiter → broker-order (in-process, DIRECT call) → sender thread`.
  So the protective action here is a synchronous in-process method call on the
  broker port and touches NO wire: not the state bus, not ZMQ, not the financial
  picture publish. `fire()` and `request_close()` reach `broker.flatten` / the
  `broker.cancel_order` sync verbs and nothing else. That absence is the property,
  and it is provable only by REMOVING the wire — see `test_flatten.py`.
* **Every uncertainty resolves toward FLAT; known state beats optimal.** §4's
  indeterminate path sends a flatten to be safe even when no position is known to
  exist, and then RECONCILES against broker truth and publishes the CONFIRMED
  state — never merely "we sent a flatten".
* **Detection may live anywhere; EXECUTION of any flatten is Limiter-only**
  (Sentinel excepted). Net-liq detection is sub-agent C, stale-price is the
  datafeed, orphan detection is the heartbeat machinery (R5) — none of them
  EXECUTE. They hand a `FlattenTrigger` to this module, which is the one place a
  flatten is issued.
* **Protective always wins over discretionary** (§4 dual authority). The arbiter
  in `request_close` records the winner per trade and refuses to let a
  discretionary close override a protective one.

------------------------------------------------------------------------------
HONEST LIMITATIONS — carried in the verdicts, never implied away
------------------------------------------------------------------------------
* These stops are **SYNTHETIC** (§12.1): a synthetic stop dies with the process
  holding it. The Sentinel covers that gap and the Sentinel is **R4**; until it
  exists a killed Risk Engine is an unprotected position, and nothing here may be
  read as covering it. That is why `SENTINEL` is REFUSED by `fire()` — the
  Sentinel is not the Limiter and is not this module.
* `SESSION_CLOSE` was REFUSED here through ARC 032 because the session calendar
  that would fire it did not exist. **ARC 033 landed it** — Phase 0.4's calendar
  extensions and `nixrisk/calendar_seam.py`, then Stage 1/B's
  `scripts/nixrisk/session.py`, which is the §6.1b deadline. The trigger is now
  FIREABLE and the refusal is gone; see `_R4_TRIGGERS` for the full note. This
  module still does not DETECT the deadline — `session.py` does, and hands the
  trigger here, the same detection/execution split §14 requires of every other
  trigger.
* `ORPHAN` detection needs the heartbeat machinery (**R5**). This module can
  EXECUTE a flatten given an orphan trigger — the execution is identical — but
  nothing here DETECTS an orphan.

------------------------------------------------------------------------------
THE PLANE-1 EXIT ROWS — on the real port (ARC 029 Stage 2.2)
------------------------------------------------------------------------------
§12.10 books `protective-exit`, `exit-intent`, `closed` and `cancel` on Plane 1.
Sub-agent B built this executor while the seam was FROZEN and its `EventKind`
omitted those members, so B carried the kinds on an interim `ExitEventLog` surface
and reported the gap rather than routing around it — exactly as ARC 028 met the
`HALT_ONSET` gap. Stage 2.2 closed the gap: the integrator added the five exit-half
members to the seam's `EventKind` (the same route SPEC-A7 took for `TerminalPath`,
because the mechanism now exists), and the interim surface COLLAPSED — every exit
row now enqueues through the real `Plane1Port` as an `EventRow` (`_book`), the same
append-only WAL every other Limiter row rides. §9 sole-writer holds: no new writer,
the same port. Reservation releases already went onto real Plane 1 under
`EventKind.RESERVATION_RELEASED`; now the exit-kind rows join them.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nixrisk.picture import FinancialPictureBook
from nixrisk.realized import (
    STATUS_FIELD,
    SYMBOL_FIELD,
    RealizedError,
    TradeFactsBook,
    realized_fields,
)
from nixrisk.reservations import Refusal, ReservationLedger
from nixrisk.seam import (
    EventKind,
    EventRow,
    FinancialPicture,
    FlattenTrigger,
    Plane1Port,
    PositionRow,
    PositionState,
    Reservation,
    TerminalPath,
)

# pylint: disable=too-few-public-methods
# duplicate-code: the ClosedRecord construction here is mirrored by test_flatten's
# expected-value builder (R0801 flags the pair); the test asserting equality
# against a hand-built record is the coverage, not copied logic.
# pylint: disable=duplicate-code
# Every Protocol below is a fan-out surface with exactly the verbs §4's
# reconcile-then-publish names for its consumer; a second method would be a sink
# doing two jobs. The threshold is about behavioural classes accreting state.


# ---------------------------------------------------------------------------
# The trigger vocabulary (B1) — §3's set, transcribed and closed in the seam
# ---------------------------------------------------------------------------
#
# `FlattenTrigger` is the FROZEN enum; this module does not re-spell it. What it
# adds is the partition of that set into what the Limiter fires NOW and what it
# refuses as unbuilt, and the refusal is loud (directive 4) rather than a silent
# no-op that would read as "flattened".

#: Triggers the Limiter cannot fire in this arc, each REFUSED with its own reason.
#: `SENTINEL` is the R4 last-resort executor that runs when the Limiter is DEAD
#: (§14) — by definition not something the live Limiter's own module issues.
#:
#: **`SESSION_CLOSE` LEFT THIS SET IN ARC 033 / Stage 1 / B.** ARC 029 refused it
#: on one stated ground — *"needs the R4 session calendar (§6.1b)"* — and that
#: calendar landed in ARC 033 / Phase 0.4 (`scripts/crucible/calendar.py`'s
#: per-symbol extensions, `nixrisk/calendar_seam.py`'s `WindowSetReadPort` /
#: `RollScheduleReadPort`). The refusal was a statement about an unbuilt
#: mechanism, not a permanent policy, so it expires with the mechanism it named;
#: `scripts/nixrisk/session.py` is the §6.1b deadline that now fires it.
#: `SENTINEL`'s reason has NOT changed and it stays refused.
_R4_TRIGGERS: frozenset[FlattenTrigger] = frozenset({FlattenTrigger.SENTINEL})

#: The onset causes an entry-cancel may release a reservation under. SPEC-A7:
#: `HALT_ONSET` is DISTINCT from `BLACKOUT_ONSET` — booking a HALT cancel as a
#: blackout cancel puts the wrong cause in §9's record of money truth, and booking
#: either as a bare `CANCEL` erases the cause. §3:173 lists both.
_ONSET_CAUSES: frozenset[TerminalPath] = frozenset(
    {TerminalPath.BLACKOUT_ONSET, TerminalPath.HALT_ONSET}
)

#: Position states that represent live exposure the Limiter's mirror is holding.
#: A trade in one of these before a flatten and absent from broker truth after it
#: is a trade the flatten really closed — the §4 "real fill" Scoring books.
_LIVE_STATES: frozenset[PositionState] = frozenset(
    {PositionState.OPEN, PositionState.CLOSING}
)


class FlattenError(RuntimeError):
    """Base for every refusal this executor raises. Never caught internally."""


class TriggerNotFireable(FlattenError):
    """A `FlattenTrigger` the Limiter must not fire in this arc (R4 mechanism)."""


class NotAnOnsetCause(FlattenError):
    """An onset-cancel asked to release under a cause that is not an onset cause."""


# ---------------------------------------------------------------------------
# The broker surface the protective path calls — the ONE async boundary is
# reconcile, and the protective action is SYNC (§2A invariant 5, §14)
# ---------------------------------------------------------------------------


@runtime_checkable
class _BrokerPosition(Protocol):
    """The reconcile read-shape. `Position` in the frozen §2A seam satisfies it."""

    @property
    def symbol(self) -> str:
        """The instrument this position is in."""

    @property
    def net_qty(self) -> int:
        """Signed size; a zero row is not an open position."""

    @property
    def avg_price(self) -> float:
        """Per-unit average price (§2A: never notional)."""


@runtime_checkable
class _BrokerBalance(Protocol):
    """Broker-authoritative balance (§4). `Balance` in the §2A seam satisfies it."""

    @property
    def cash(self) -> float:
        """Cash balance — what sizing is computed on (§15 C2)."""

    @property
    def net_liquidation(self) -> float:
        """Net-liq — what survival is watched on (§15 C2). Never conflate."""


@runtime_checkable
class BrokerFlattenPort(Protocol):
    """The SUBSET of the FROZEN §2A `BrokerOrderPort` the protective path calls.

    NOT a second authority: `scripts/broker/broker_seam.py`'s `BrokerOrderPort`
    is the contract and structurally satisfies this narrower port. It is declared
    narrow (interface segregation) for one reason that is load-bearing here —
    the ZERO-WIRE claim has to be LEGIBLE. `flatten` and `cancel_order` are the
    SYNC verbs §2A invariant 5 forbids blocking, reached by a direct in-process
    call; `query_positions` / `query_balance` are the ASYNC off-hot-path reconcile
    reads (§4). A reader can see from this declaration alone that the protective
    action awaits nothing and therefore needs no running loop and no wire.
    """

    def flatten(self, symbol: str | None = None) -> None:
        """SYNC protective close; `None` means all. §2A: must not block."""

    def cancel_order(self, client_order_id: str) -> None:
        """SYNC cancel of one working order (§2A). Onset cancels pending entries."""

    async def query_positions(self) -> list[_BrokerPosition]:
        """ASYNC reconcile read: broker-authoritative open-position set (§4)."""

    async def query_balance(self) -> _BrokerBalance:
        """ASYNC reconcile read: broker-authoritative balance (§4)."""


# ---------------------------------------------------------------------------
# The §4 reconcile-then-publish fan-out consumers (B5)
# ---------------------------------------------------------------------------


@runtime_checkable
class StrategyExitSink(Protocol):
    """§4 fan-out (a): the owning strategy is told `closed, reason=X`, hard reset."""

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        """Notify the FSM. `hard_reset` frees the one-in-flight slot (§4)."""


@runtime_checkable
class ScoringSink(Protocol):
    """§4 fan-out (d): Scoring books any REAL fill from the flatten as realized P&L.

    This module hands Scoring the FACT — which trades really closed and the
    broker-truth balance delta — and nothing more. The realized-P&L EMA math is
    §6.6 and belongs to the Scoring PROCESS (**R5**, not built); a green here is
    the hand-off, never the computation.
    """

    # too-many-arguments: the fan-out payload §4 names — which trades, the
    # realized delta, the confirmed balance, the stamp. Trimming one would move a
    # field into a nested struct Scoring must read separately.
    def book_realized(  # pylint: disable=too-many-arguments
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        """Book real fills. Empty `closed_trades` ⇒ the flatten hit nothing."""


# ---------------------------------------------------------------------------
# Value records
# ---------------------------------------------------------------------------


class CloseAuthority(enum.Enum):
    """§4's dual exit authority. Protective ALWAYS wins over discretionary."""

    DISCRETIONARY = "discretionary"
    PROTECTIVE = "protective"


@dataclass(frozen=True)
class CloseTarget:
    """One trade to close, carrying the identity §4's feedback is tagged with."""

    trade_id: str
    symbol: str
    strategy_id: str


@dataclass(frozen=True)
class PendingEntry:
    """One pending ENTRY order (§3). Onset cancels these; exits are untouched."""

    client_order_id: str
    strategy_id: str
    symbol: str


@dataclass(frozen=True)
class ClosedRecord:  # pylint: disable=too-many-instance-attributes
    # A frozen value type with eight fields, each a distinct fact the §4 feedback
    # and the arbiter need: the trade identity (3), the authority, the reason, the
    # stamp, the FSM verdict, and which authority it superseded. The threshold is
    # about behavioural classes accreting state; this has no behaviour.
    """The authoritative close for one trade: who won, why, and the FSM verdict."""

    trade_id: str
    symbol: str
    strategy_id: str
    authority: CloseAuthority
    reason: str
    closed_ts: float
    hard_reset: bool
    superseded: CloseAuthority | None


@dataclass(frozen=True)
class CloseOutcome:
    """What one `request_close` did. `executed` is whether it issued a flatten."""

    executed: bool
    record: ClosedRecord
    dropped_reason: str = ""


@dataclass(frozen=True)
class FlattenAction:
    """One protective `fire`: the trigger, the targets, and the per-target result.

    A DECLARATION OF INTENT, never a claim about the venue — §4 and the §2A
    `FlattenAttempt` docstring are both explicit that "we sent a flatten" and
    "the position is confirmed flat" are different facts and must not share an
    object. The CONFIRMED fact is `ConfirmedFlat`, produced only by reconcile.
    """

    trigger: FlattenTrigger
    symbol: str | None
    targets: tuple[CloseTarget, ...]
    outcomes: tuple[CloseOutcome, ...]
    fired_ts: float


@dataclass(frozen=True)
class OnsetCancellation:
    """One onset's entry-cancel sweep: what was cancelled and released under `cause`."""

    cause: TerminalPath
    cancelled: tuple[str, ...]
    released: tuple[Reservation, ...]
    refusals: tuple[Refusal, ...]


@dataclass(frozen=True)
class ConfirmedFlat:
    """§4's CONFIRMED state — broker truth AFTER the flatten, published atomically.

    `picture` is what went on the wire to the Allocator mirror, and its `balance`
    is the broker-authoritative reading (§4: *"broker wins and we correct"*), NOT
    the pre-flatten projection. `closed_trades` are trades the Limiter's mirror
    held live that broker truth no longer shows — the real fills. `is_flat` is the
    honesty flag: if the broker still shows exposure (a halted market could not be
    flattened, §12.6), this is False and the published picture says so.
    """

    picture: FinancialPicture
    confirmed_balance: float
    projection_balance: float
    closed_trades: tuple[str, ...]
    realized_delta: float
    is_flat: bool


@dataclass(frozen=True)
class _Intent:
    """A per-symbol protective intent, so reconcile can attribute an untargeted
    close (the §4 uncertainty flatten fires with no known trade)."""

    trigger: FlattenTrigger
    reason: str
    ts: float


# ---------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------


class ProtectiveFlatten:  # pylint: disable=too-many-instance-attributes
    # Eight collaborators + two small books. Each collaborator is one §4 fan-out
    # consumer or one frozen port the Limiter owns; `_closed` and `_intents` are
    # the arbiter's memory. The threshold is about behavioural classes accreting
    # incidental state — these are exactly the surfaces §3/§4 name and no more.
    """§3/§4/§14's protective-flatten executor. EXECUTION is Limiter-only (§14).

    Single instance, owned by the Limiter's single-threaded loop (§5). The
    protective verbs (`fire`, `request_close`, `cancel_entries_on_onset`) are
    SYNCHRONOUS and zero-wire; `reconcile_and_publish` is the one async,
    off-hot-path verb, because §4's reconcile reads broker truth over the async
    §2A query verbs and human-scale event frequency makes the await honest.
    """

    # too-many-arguments: seven injected collaborators, each a frozen port the
    # Limiter owns or a §4 fan-out consumer. They are keyword-only and have no
    # defaults except the clock — a protective executor that silently defaulted a
    # sink would fan out into a black hole.
    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        broker: BrokerFlattenPort,
        ledger: ReservationLedger,
        picture: FinancialPictureBook,
        strategy: StrategyExitSink,
        plane1: Plane1Port,
        scoring: ScoringSink,
        trade_facts: TradeFactsBook | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._broker = broker
        self._ledger = ledger
        self._picture = picture
        self._strategy = strategy
        #: §9: the Limiter is the SOLE Plane-1 writer. ARC 029 Stage 2.2 collapsed
        #: the interim ExitEventLog onto this real port once EventKind gained the
        #: exit-half members — no new writer, the same append-only WAL every other
        #: Limiter row rides.
        self._plane1 = plane1
        self._scoring = scoring
        #: ARC 037 / D3.220. Where the per-trade realized figure's INPUTS come
        #: from. Defaulted to `None` rather than required, and that is a
        #: measured choice rather than a convenience: eight construction sites
        #: exist across this tree's tests and gates, NO production code path
        #: fills a facts book (this tree has no fill feed — `EventKind` still
        #: has no `filled` member), and a required argument would have made
        #: every one of them pass a book with nothing in it. A book that is
        #: absent produces a `realized_status` on the row naming its absence;
        #: it NEVER produces a zero, which is the failure mode
        #: `nixscore/ema.py`'s docstring spends a paragraph on.
        self._trade_facts = trade_facts
        self._clock = clock
        #: trade_id -> the authoritative close. The arbiter's ground truth (§4).
        self._closed: dict[str, ClosedRecord] = {}
        #: symbol -> the active protective intent, for attributing an untargeted
        #: uncertainty flatten at reconcile time.
        self._intents: dict[str, _Intent] = {}
        #: trade_id -> the §12.10 event type whose row already carried this
        #: trade's realized figure. ONE figure per closed trade, and the second
        #: realizing row for the same trade says so instead of repeating it —
        #: `nixscore.ema.daily_advances` SUMS every realizing row in a pair's
        #: day, so a protective exit and its confirming `closed` row both
        #: carrying the number would double the trade's contribution to §6.6's
        #: rank. Measured on the shipped path: `request_close` books
        #: `protective_exit` and `reconcile_and_publish` books `closed` for the
        #: same trade_id.
        self._realized_booked: dict[str, str] = {}

    # -- B2 / B3: the protective action and the dual-authority arbiter --------

    def fire(
        self,
        trigger: FlattenTrigger,
        *,
        symbol: str | None = None,
        targets: Sequence[CloseTarget] = (),
        reason: str | None = None,
    ) -> FlattenAction:
        """Fire a protective flatten. ZERO wire: a direct in-process broker call.

        Refuses an R4 trigger loudly (`SENTINEL`) rather than no-op'ing, so an
        unbuilt mechanism can never read as "flattened". For a trigger with known
        targets each is closed under PROTECTIVE authority; for the §4 uncertainty
        case — a flatten sent to be safe with no known trade — the symbol is
        flattened at the broker and the intent recorded so reconcile can attribute
        whatever it turns out to have closed.

        `reason` is OPTIONAL and defaults to the string this method has always
        derived from the trigger name. It exists (ARC 033 / Stage 1 / B) because
        §6.1b:352 fixes the word the strategy must receive — *"strategy receives
        `closed, reason=session`"* — and the derived string is `protective flatten
        (trigger=session_close)`, a DIFFERENT string. A caller that has a
        spec-named reason passes it; every other caller is unchanged. The reason
        rides through `request_close` into the §4 fan-out and onto the Plane-1
        row, so the word §6.1b names is the word §9's record keeps.

        The broker call is `flatten`, a SYNC §2A verb reached in-process. Nothing
        on this path publishes a picture, touches the state bus, or awaits, which
        is the whole of the §14 zero-wire property and is why the exit fires when
        the wire is down. `test_flatten.py` proves it by removing the wire.
        """
        if trigger in _R4_TRIGGERS:
            raise TriggerNotFireable(
                f"{trigger.value}: the Limiter does not fire this trigger in this "
                "arc. SENTINEL is the R4 last-resort executor that runs only when "
                "the Limiter is DEAD (§14), so the live Limiter never issues it. "
                "Declared in the frozen FlattenTrigger vocabulary, refused here — "
                "not a no-op"
            )
        now = self._clock()
        if reason is None:
            reason = f"protective flatten (trigger={trigger.value})"
        if symbol is not None:
            self._intents[symbol] = _Intent(trigger, reason, now)
        if not targets:
            # §4 uncertainty: send a flatten to be safe even with no known trade.
            self._broker.flatten(symbol)
        outcomes = tuple(
            self.request_close(target, CloseAuthority.PROTECTIVE, reason)
            for target in targets
        )
        return FlattenAction(
            trigger=trigger,
            symbol=symbol,
            targets=tuple(targets),
            outcomes=outcomes,
            fired_ts=now,
        )

    def request_close(
        self, target: CloseTarget, authority: CloseAuthority, reason: str
    ) -> CloseOutcome:
        """§4's dual-authority arbiter. Protective ALWAYS wins over discretionary.

        The one place a flatten is decided AND issued for a trade, so precedence
        is a property of this method rather than a convention spread across call
        sites. The rules, and each is a way the wrong authority could win:

        * a DISCRETIONARY close of a trade already closed (by either authority) is
          DROPPED — the discretionary path never overrides, so a strategy's
          edge-spent exit cannot undo or relabel a protective one;
        * a second PROTECTIVE close of an already-protective trade is DROPPED as a
          redundant double-close (the position is already flat);
        * a PROTECTIVE close of a trade a discretionary exit already took OVERRIDES
          it: the broker flatten is unconditional (§4) and the recorded winner
          becomes PROTECTIVE with `superseded=DISCRETIONARY`.

        `hard_reset` is True exactly for a protective win — §4: the FSM
        hard-resets to flat and the one-in-flight slot is freed. The broker
        `flatten` is the same zero-wire in-process call `fire` uses.
        """
        prior = self._closed.get(target.trade_id)
        if prior is not None:
            if authority is CloseAuthority.DISCRETIONARY:
                return CloseOutcome(
                    executed=False,
                    record=prior,
                    dropped_reason=(
                        f"trade {target.trade_id} already closed by "
                        f"{prior.authority.value}; a discretionary exit does not "
                        "override (§4: protective always wins)"
                    ),
                )
            if prior.authority is CloseAuthority.PROTECTIVE:
                return CloseOutcome(
                    executed=False,
                    record=prior,
                    dropped_reason=(
                        f"trade {target.trade_id} already protectively closed via "
                        f"'{prior.reason}'; refusing a redundant double-close"
                    ),
                )
        # Execute: the zero-wire protective/close action.
        self._broker.flatten(target.symbol)
        record = ClosedRecord(
            trade_id=target.trade_id,
            symbol=target.symbol,
            strategy_id=target.strategy_id,
            authority=authority,
            reason=reason,
            closed_ts=self._clock(),
            hard_reset=authority is CloseAuthority.PROTECTIVE,
            superseded=prior.authority if prior is not None else None,
        )
        self._closed[target.trade_id] = record
        protective = authority is CloseAuthority.PROTECTIVE
        self._book(
            kind=(EventKind.PROTECTIVE_EXIT if protective else EventKind.EXIT_INTENT),
            trade_id=target.trade_id,
            strategy_id=target.strategy_id,
            symbol=target.symbol,
            reason=reason,
            ts=record.closed_ts,
            # `protective_exit` BOOKS a realization; `exit_intent` does not.
            # `nixscore.ema` classifies them exactly that way — an intent is a
            # decision, and the position it names is still open until a fill
            # says otherwise, so its P&L would be a mark (§6.6:435).
            realizing=protective,
        )
        return CloseOutcome(executed=True, record=record)

    # -- B4: onset cancels pending ENTRY orders, exits untouched ---------------

    def cancel_entries_on_onset(
        self, cause: TerminalPath, pending: Sequence[PendingEntry]
    ) -> OnsetCancellation:
        """§3: Blackout/HALT onset cancels all pending ENTRY orders; exits untouched.

        Each cancelled entry releases its reservation under its OWN named cause
        (SPEC-A7): a HALT-onset cancel books `HALT_ONSET`, a blackout-onset cancel
        books `BLACKOUT_ONSET`, and neither collapses to a bare `CANCEL` — §9's
        record of money truth would otherwise lose which onset released the
        capital. The reservation release goes through the real ledger onto the
        real Plane 1 (`EventKind.RESERVATION_RELEASED`); the cancel row is booked
        under `EventKind.CANCEL` onto that same Plane 1 (Stage 2.2).

        This method calls `cancel_order` ONLY. It never calls `flatten`, because
        §3 says exits are untouched — a pending ENTRY is a window a fill has not
        entered, and cancelling it is not closing a position.
        """
        if cause not in _ONSET_CAUSES:
            raise NotAnOnsetCause(
                f"{cause.value} is not an onset cause. An entry-cancel releases "
                "under BLACKOUT_ONSET or HALT_ONSET only (SPEC-A7); booking it as "
                f"{cause.value} would put the wrong cause in §9's money record"
            )
        now = self._clock()
        cancelled: list[str] = []
        released: list[Reservation] = []
        refusals: list[Refusal] = []
        for entry in pending:
            self._broker.cancel_order(entry.client_order_id)
            resolution = self._ledger.resolve(
                entry.client_order_id, cause, now, reason=cause.value
            )
            if resolution.released is not None:
                released.append(resolution.released)
            if resolution.refusal is not None:
                refusals.append(resolution.refusal)
            cancelled.append(entry.client_order_id)
            self._book(
                kind=EventKind.CANCEL,
                trade_id=None,
                strategy_id=entry.strategy_id,
                symbol=entry.symbol,
                reason=f"{cause.value} onset entry-cancel",
                ts=now,
            )
        return OnsetCancellation(
            cause=cause,
            cancelled=tuple(cancelled),
            released=tuple(released),
            refusals=tuple(refusals),
        )

    # -- B5: reconcile-then-publish the CONFIRMED state ------------------------

    async def reconcile_and_publish(self) -> ConfirmedFlat:
        """§4: reconcile against broker truth AFTER a flatten, publish the CONFIRMED
        state — never merely "we sent a flatten".

        A flatten may hit nothing OR close a real position, and the two are only
        told apart by broker truth. So this pulls a DIRECT broker
        balance + position poll in the same motion (§4: *"broker-authoritative
        balance on EVERY reconciliation"*) and builds the published snapshot from
        that poll, not from the pre-flatten projection. The pre-flatten picture is
        the Limiter's own mirror; a trade it held live that the broker no longer
        shows is a real fill, and the balance delta is what Scoring books.

        The snapshot is published atomically (one version, §3 atomicity) to the
        Allocator mirror, and the confirmed fact fans out to strategy, event log
        and Scoring off that one canonical source (§4).

        ASYNC because `query_positions`/`query_balance` are the §2A async verbs and
        this runs off the hot path. It is NOT on the zero-wire protective path —
        the flatten already fired synchronously; this is the after.
        """
        projection = self._picture.current()
        positions = await self._broker.query_positions()
        balance = await self._broker.query_balance()

        held_symbols = {pos.symbol for pos in positions if pos.net_qty != 0}
        closed_trades = tuple(
            row.trade_id
            for row in projection.positions
            if row.state in _LIVE_STATES and row.symbol not in held_symbols
        )
        realized_delta = balance.cash - projection.balance
        rows = self._confirmed_rows(projection, held_symbols)

        picture = self._picture.commit(
            balance=balance.cash,
            positions=rows,
            sum_reservations=self._ledger.total_reserved(),
        )

        now = self._clock()
        self._fan_out(projection, closed_trades, now)
        self._scoring.book_realized(
            closed_trades=closed_trades,
            realized_delta=realized_delta,
            confirmed_balance=balance.cash,
            ts=now,
        )
        return ConfirmedFlat(
            picture=picture,
            confirmed_balance=balance.cash,
            projection_balance=projection.balance,
            closed_trades=closed_trades,
            realized_delta=realized_delta,
            is_flat=not rows,
        )

    def _confirmed_rows(
        self, projection: FinancialPicture, held_symbols: set[str]
    ) -> tuple[PositionRow, ...]:
        """The position table broker truth confirms. Empty on a clean flatten.

        A symbol the broker still shows is one the flatten could not close (a
        halted market, §12.6) — the honesty case. Its row is carried from the
        Limiter's own mirror updated to CLOSING, because the metadata (trade_id,
        strategy_id, margin) lives there and not in the broker's per-symbol view;
        a broker-shown symbol the mirror never knew is a cold-start/orphan concern
        (sub-agent D) and is deliberately not adopted here.
        """
        return tuple(
            PositionRow(
                trade_id=row.trade_id,
                symbol=row.symbol,
                strategy_id=row.strategy_id,
                size=row.size,
                margin=row.margin,
                state=PositionState.CLOSING,
                # CARRIED from the mirror's row, never re-derived and never a
                # literal (ARC 032). This constructor exists to move a row to
                # CLOSING and change nothing else; inventing a stop distance
                # here would make the Limiter publish a §7:501 exposure figure
                # that no sizing pass ever computed.
                stop_distance=row.stop_distance,
            )
            for row in projection.positions
            if row.symbol in held_symbols
        )

    def _fan_out(
        self, projection: FinancialPicture, closed_trades: tuple[str, ...], now: float
    ) -> None:
        """§4 fan-out (a) + (c): strategy `closed` notify and the event-log row.

        The reason and the hard-reset verdict come from the arbiter's record where
        the close was targeted; an unattributed uncertainty flatten falls back to
        the per-symbol intent, and last to a bare reconcile reason so a real close
        is never reported without one.
        """
        by_trade = {row.trade_id: row for row in projection.positions}
        for trade_id in closed_trades:
            record = self._closed.get(trade_id)
            row = by_trade[trade_id]
            reason, hard_reset = self._attribution(record, row.symbol)
            self._strategy.on_closed(
                trade_id, row.strategy_id, reason, hard_reset=hard_reset
            )
            self._book(
                kind=EventKind.CLOSED,
                trade_id=trade_id,
                strategy_id=row.strategy_id,
                symbol=row.symbol,
                reason=reason,
                ts=now,
                # §9's terminal round trip, and the row §6.6 actually ranks on.
                # It is booked AFTER reconcile against broker truth, which is
                # why it — and not the protective-exit row that preceded it —
                # is normally the one carrying the figure: at exit-intent time
                # no exit fill is confirmed and the facts book has nothing.
                realizing=True,
            )

    # too-many-arguments: §9 requires timestamp + strategy_id + trade_id + reason
    # on every row, and §12.10 adds the kind and the symbol. The count is the
    # frozen row shape, not this method's design.
    def _book(  # pylint: disable=too-many-arguments
        self,
        *,
        kind: EventKind,
        trade_id: str | None,
        strategy_id: str,
        symbol: str,
        reason: str,
        ts: float,
        realizing: bool = False,
    ) -> None:
        """One §12.10 exit row onto Plane 1 (Limiter sole writer, §9).

        ARC 029 Stage 2.2: the interim `ExitEventLog` collapsed here once the seam
        gained the exit-half `EventKind` members. `EventRow` carries trade_id /
        strategy_id / reason natively; the symbol rides `fields`, which is where
        §12.10's per-row extras live (the reservation-release rows already do this).
        Bounded and hot-path-safe: `enqueue` appends to the WAL and returns without
        durability, so booking an exit row adds no wire dependency to the exit path.

        ARC 037 (D3.220): a row booked with `realizing=True` also carries the
        trade's REALIZED P&L, or a `realized_status` naming why it does not.
        No new event type, no new writer and no new port — the figure rides the
        `closed` / `protective_exit` rows this method already books, which is
        §12.10:768's own pattern for a per-trade figure.
        """
        self._plane1.enqueue(
            EventRow(
                kind=kind,
                ts=ts,
                strategy_id=strategy_id,
                reason=reason,
                trade_id=trade_id,
                fields=(
                    self._realizing_fields(kind, trade_id, symbol)
                    if realizing
                    else {SYMBOL_FIELD: symbol}
                ),
            )
        )

    # -- ARC 037 / D3.220: the realized figure the durable record did not carry -

    def _realizing_fields(
        self, kind: EventKind, trade_id: str | None, symbol: str
    ) -> dict[str, str]:
        """The `fields` of a row that BOOKS A REALIZATION (§6.6:435, SEAM (a)).

        `closed` and `protective_exit` are two of
        `nixscore.ema.REALIZING_EVENT_TYPES`, and §12.10:768's own pattern —
        *"the final trail level rides the `closed` row"* — is what this follows:
        a per-trade figure rides its terminal row, and no §12.10 event type is
        minted for it.

        Either the row carries `realized_pnl` or it carries a `realized_status`
        saying WHY it does not. There is no third outcome and there is never a
        placeholder number: `nixscore.ema` refuses a realizing row with no
        figure BY NAME (`MissingRealized`), and that refusal is the only thing
        standing between a blind scorer and a scorer that looks like a healthy
        cold start. A zero here would disable it permanently.
        """
        outcome = self._realized_or_reason(trade_id, symbol)
        if isinstance(outcome, str):
            return {SYMBOL_FIELD: symbol, STATUS_FIELD: outcome}
        self._realized_booked[str(trade_id)] = kind.value
        return outcome

    # too-many-return-statements: SEVEN returns, six of which are a DISTINCT
    # named reason a figure can be legitimately absent. Collapsing them into a
    # single exit with an accumulated variable would not remove a branch; it
    # would remove the one thing check contract rule 11 asks for — a reason
    # that names ITS OWN condition — and the row's `realized_status` is that
    # reason, written into §9's durable record.
    def _realized_or_reason(  # pylint: disable=too-many-return-statements
        self, trade_id: str | None, symbol: str
    ) -> dict[str, str] | str:
        """This trade's realizing `fields`, or the REASON there are none.

        Every branch here is a way the figure can be legitimately absent, and
        each one is written into §9's record rather than swallowed. A
        `RealizedError` is caught and recorded rather than raised, and that is
        the one deliberate softening on this path: §14 makes the protective
        exit's booking zero-wire and non-optional, so a malformed cost fact must
        not be able to stop the Limiter from recording that a position closed.
        The refusal's own text rides onto the row, so nothing is lost — the
        reason is durable, and the scorer still refuses the row by name.
        """
        if trade_id is None:
            return (
                "no trade_id on this realizing row, so there is no round trip to "
                "price and no pair to attribute it to (§6.6:448)"
            )
        booked = self._realized_booked.get(trade_id)
        if booked is not None:
            return (
                f"already booked on this trade's {booked!r} row; a second figure "
                "would DOUBLE-COUNT one close, because §6.6:438's per-day "
                "reduction SUMS every realizing row a pair produced that day"
            )
        if self._trade_facts is None:
            return (
                "no TradeFactsBook is wired into this Limiter, so the exit "
                "fill's price and costs are not knowable here (CHECK-DEBT "
                "D3.281: this tree has no fill feed)"
            )
        facts = self._trade_facts.facts_for(trade_id)
        if facts is None:
            return (
                "no confirmed exit fill for this trade yet — §4 keeps 'we sent a "
                "flatten' and 'the position is confirmed flat' apart, and a "
                "figure computed from an unconfirmed exit is a mark"
            )
        if facts.entry.symbol != symbol:
            return (
                f"the facts book answered for symbol {facts.entry.symbol!r} on "
                f"trade {trade_id!r}, but this row closes {symbol!r} — §6.6:448 "
                "keys on the pair, so a mismatched symbol is a misattribution"
            )
        try:
            return realized_fields(facts)
        except RealizedError as exc:
            return f"refused: {exc}"

    def _attribution(
        self, record: ClosedRecord | None, symbol: str
    ) -> tuple[str, bool]:
        """The `(reason, hard_reset)` a confirmed close is reported under."""
        if record is not None:
            return record.reason, record.hard_reset
        intent = self._intents.get(symbol)
        if intent is not None:
            # A protective flatten always hard-resets the FSM (§4).
            return intent.reason, True
        return "reconciled flat against broker truth (§4)", True

    # -- readable state --------------------------------------------------------

    def closed_record(self, trade_id: str) -> ClosedRecord | None:
        """The authoritative close for a trade, or None. The arbiter's verdict."""
        return self._closed.get(trade_id)
