"""ARC 058 / I1 ARC D — FLATTEN COMPLETIONS: the CLOSING fill, reconciled.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named.

------------------------------------------------------------------------------
THE HALF THAT WAS NOT THERE, MEASURED BEFORE IT WAS WRITTEN
------------------------------------------------------------------------------
ARC 055 (C1) made a breached synthetic stop FIRE one protective flatten. ARC 057
(C2) added §14's four uncertainty producers. Both *fire and send*; **neither
closes the book.** Driven end to end on a real `limiterd` at ARC 058 / S1 — a
reserve, an entry fill, a price through the stop, then the flatten's own exec
report handed back through `completions/` — the daemon:

* wrote **no §12.10 `closed` row** (the WAL held `reservation_taken`,
  `reservation_released`, `protective_exit` and nothing else);
* left the §3 row at **`state="open"`**;
* left **`sum_open_margin` at 1000.0** — the capital of a position the venue had
  already closed;
* left the fired stop in `StopWatch.in_flight` (**D3.481**) and armed in
  `StopBook`;
* told the strategy nothing.

And worse than any of those: the closing exec report was dispatched down the
ENTRY path, refused as an `UnapprovedFill` — *"this Limiter holds no approved
order under that id"* — and landed in §14's `unclassified` list, which
`check_uncertainty_flatten` ARM 6 reads as CANNOT_MEASURE. A flatten's own
confirmation was poisoning the gate that owns flattens.

This module is the reconciling half. It is a LIBRARY; `scripts/limiterd.py` is
what gives it a pid, which is the whole shape of I1.

------------------------------------------------------------------------------
WHAT RECOGNISES A CLOSE, AND WHY IT IS DERIVED RATHER THAN DECLARED
------------------------------------------------------------------------------
§2A:74-84's `on_fill` carries no role. It says an order filled; it does not say
whether that order was opening or closing, and **nothing in the wire format ever
will** — the same gap `OrderRole` was minted for on the cancel side (§3:173,
ARC 045). So the classification is DERIVED from three facts this process already
holds, and a fill that fails any of them is NOT a close:

1. **It is a fill.** `on_cancel` and `on_reject` are §3's release paths and
   `nixrisk/outcomes.py` owns them, unchanged.
2. **Its order is not an approved ENTRY.** `TradeOriginPort.origin_for_order`
   is §3/§4's trade<->order join, recorded at approval. An id it knows is an
   entry and belongs to `nixrisk/fills.py`'s cascade — this module never sees it.
3. **This process SENT a protective flatten for that symbol and it is still in
   flight.** That is `FlattenInFlightBook` below, and it is written by the
   daemon at the moment of the send rather than inferred afterwards.

Fact 3 is the load-bearing one and it is deliberately the daemon's own record.
The alternative — reading `ProtectiveFlatten`'s private `_closed` / `_intents`
books — would have made this module depend on the executor's internals and
would still not have covered §4's untargeted uncertainty flatten, which records
no `ClosedRecord` at all. **A fill that satisfies (1) and (2) but not (3) is
NOT adopted**: it is left to the ordinary dispatch, which refuses it by name.
Adopting it would mean this module closing a position off a venue message
nothing in this process asked for, which is exactly the guessing §17 forbids.

------------------------------------------------------------------------------
WHAT A CLOSE DOES, IN THIS ORDER, AND WHY THE ORDER IS THE SAFETY PROPERTY
------------------------------------------------------------------------------
    §3 commit (OPEN -> CLOSED, open margin released)
      -> stops forgotten (StopBook, then StopWatch)
      -> §12.10 `closed` row
      -> §4:203-206 `closed` notify with the FSM hard reset

**The §3 commit is FIRST and it is the authority.** `FinancialPictureBook.commit`
is the sole-writer seam (§9, §12.10) and it REFUSES an incoherent snapshot
(`TornPicture`). If it refuses, the close is REFUSED WHOLE: nothing is forgotten,
no row is booked, the strategy is not told, and the in-flight flatten STAYS
ARMED so a re-delivery or a later reconcile can retry. That direction is
fail-closed — the capital stays committed and the stop stays armed, which is the
conservative error — and the opposite order would have told a strategy it was
flat while §3 still carried the position.

**Everything after the commit is ATTEMPTED AND RECORDED, never raised.** That is
`flatten.ProtectiveFlatten._book`'s FC1 ruling applied one module over: §12.4:625
keeps open positions protected through a WAL that cannot append, and §14:968
resolves every uncertainty toward flat. Losing the audit row while the position
is genuinely closed beats leaving §3 claiming an exposure the venue does not
have. Each failure lands on a public list carrying the port's OWN reason text
(check contract rule 11), never as a count.

**THE `closed` ROW BOOKS NO REALIZED FIGURE, AND THAT IS MEASURED, NOT LAZY.**
`flatten.py` records it at the site: `request_close` books a `protective_exit`
row with `realizing=True`, `nixscore.ema.daily_advances` SUMS every realizing row
in a pair's day, and a second realizing row for the same trade would double that
trade's contribution to §6.6's rank. The guard that stops it (`_realized_booked`)
lives inside `ProtectiveFlatten` and cannot see a row booked from here. So this
module books the terminal `closed` row NON-REALIZING, carrying the two facts the
exec report has that no reconcile poll does — the CLOSE PRICE and the exec id —
plus a `realized_status` naming why no per-trade figure rides it. D3.220's wire
is unchanged and undamaged.

------------------------------------------------------------------------------
IDEMPOTENCY — TWO KEYS, BECAUSE THERE ARE TWO WAYS TO DOUBLE-CLOSE
------------------------------------------------------------------------------
* **The exec report.** §4:214 deduplicates broker events by `(order_id, exec_id)`
  and this module claims that key through the SAME `ExecReportDedup` the entry
  dispatcher uses — not a second book. A re-delivered closing fill is a counted
  DUPLICATE and closes nothing twice.
* **The trade.** A trade whose §3 row is no longer in a LIVE state has no live
  row to close, so recognition finds nothing to attribute and the fill is a
  no-op. This survives a dedup that has evicted the key (it is bounded).

Both are needed: the first stops the same message twice, the second stops two
different messages about one already-closed trade.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from nixrisk.completions import EVENT_FILL, ExecReportDedup, SenderCompletion
from nixrisk.picture import FinancialPictureBook
from nixrisk.positions import EntryOrderOrigins
from nixrisk.realized import STATUS_FIELD, SYMBOL_FIELD
from nixrisk.seam import EventKind, EventRow, PositionRow, PositionState
from nixrisk.stops import StopBook
from nixrisk.stopwatch import StopWatch

SITE = "scripts/nixrisk/closing.py"

#: The §3 states a position must be in for a closing fill to have anything to
#: close. Deliberately NOT imported from `flatten._LIVE_STATES`: that name is
#: private to the executor and `session.py` records the same decision for the
#: same reason. RESERVED and PENDING are excluded because no fill has opened
#: them yet, and CLOSED because it is the state this module produces.
LIVE_STATES: frozenset[PositionState] = frozenset(
    {PositionState.OPEN, PositionState.CLOSING}
)

#: §12.10 row extras this module adds beyond `flatten._book`'s `symbol`. The
#: close PRICE is the fact a fill-driven close has and a reconcile poll does not
#: (§4's reconcile reads broker truth, which carries no execution price), so it
#: rides the terminal row — §12.10:768's own pattern for a per-trade figure.
CLOSE_PRICE_FIELD = "close_price"
EXEC_ID_FIELD = "exec_id"
CLOSING_ORDER_FIELD = "closing_order_id"


class ClosingError(RuntimeError):
    """Base for this module's refusals. Every one names its site."""


class Refused(ClosingError):
    """The §3 commit refused, so NOTHING downstream of it ran. Fail-closed."""


# --------------------------------------------------------------------------
# The ports. Frozen, narrow, and each already implemented by a shipped object.
# --------------------------------------------------------------------------


#: WHY THE FOUR BOOKS BELOW ARE TYPED CONCRETELY AND THE TWO SINKS ARE NOT.
#:
#: `flatten.ProtectiveFlatten.__init__` draws exactly this line and this module
#: follows it rather than inventing a second convention: the Limiter's OWN books
#: (`ReservationLedger`, `FinancialPictureBook`) are named by their concrete
#: type, and the §4 FAN-OUT consumers (`StrategyExitSink`, `ScoringSink`,
#: `Plane1Port`) are Protocols, because a fan-out has other implementations and a
#: book has one owner.
#:
#: **AND IT IS MEASURED, NOT ONLY IDIOMATIC.** This module first declared its own
#: `PicturePort` / `StopBookPort` / `StopWatchPort` / `OriginPort` / `DedupPort`
#: Protocols, and `check_uncalled_entry_points` — which resolves a call to the
#: DECLARED type of its receiver — then attributed every one of those calls to
#: the local Protocol. `StopBook.forget` and `StopWatch.forget` stayed UNCALLED
#: through a module that calls both on every close, so D3.481 would have read as
#: unpaid while it was being paid. A port that hides its own caller from the
#: instrument that hunts for callers is a port that makes this arc's work
#: invisible.


class ExitSinkPort(Protocol):  # pylint: disable=too-few-public-methods
    """§4 fan-out (a): the strategy `closed` notify with the FSM verdict."""

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        """Tell the owning FSM the trade is closed."""


class Plane1Port(Protocol):  # pylint: disable=too-few-public-methods
    """§9's write path. The Limiter is the SOLE writer; no new writers, ever."""

    def enqueue(self, row: EventRow) -> None:
        """Append one row. Bounded, hot-path-safe, NOT durable."""


class ArbiterPort(Protocol):  # pylint: disable=too-few-public-methods
    """§4's close arbiter, read-only. `closed_record` is its PUBLIC accessor."""

    def closed_record(self, trade_id: str) -> Any:
        """The authoritative close for one trade, or None."""


# --------------------------------------------------------------------------
# What the daemon SENT — fact 3 of the recognition
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InFlightFlatten:
    """ONE protective flatten this process SENT and has not yet reconciled.

    A DECLARATION OF WHAT WAS SENT, never a claim about the venue — the same
    distinction `flatten.FlattenAction` draws against `ConfirmedFlat`, and the
    reason this type exists at all: the closing fill is the venue's answer, and
    an answer can only be matched against a question somebody recorded asking.

    `trade_id` and `strategy_id` are EMPTY STRINGS for §4's untargeted
    uncertainty flatten — *"a flatten sent to be safe with no known trade"* —
    exactly as `limiterd.UncertaintyFiring` leaves them. An empty `trade_id` is
    not a missing field; it routes attribution to the symbol's live §3 rows.
    """

    key: str
    symbol: str
    trade_id: str
    strategy_id: str
    reason: str
    trigger: str
    sent_ts: float


class FlattenInFlightBook:
    """Every protective flatten SENT and not yet reconciled, in send order.

    Written by the daemon at the send site and read here. It is the daemon's own
    record rather than a read of `ProtectiveFlatten`'s internals for two reasons
    stated in the module docstring, and one more: §5:323 puts the send on the
    sender thread while the completion is drained on §5:322's loop thread, so
    the two halves are genuinely two events and the book is what joins them.

    BOUNDED. A flatten whose closing fill never arrives would otherwise
    accumulate forever, and an unbounded book on a daemon that runs for weeks is
    a leak with a §12 name. The oldest entry is dropped and COUNTED, never
    silently — `dropped` is read into the daemon's published record.
    """

    def __init__(self, max_entries: int = 256) -> None:
        self._entries: deque[InFlightFlatten] = deque(maxlen=max(1, max_entries))
        #: Entries evicted by the bound. A non-zero value means a protective
        #: flatten was sent whose confirmation this process can no longer
        #: attribute — recorded because §17 makes an unobservable subject a
        #: `cannot measure`, not a pass.
        self.dropped = 0
        #: Every arm, ever. The non-vacuity counter: *did the daemon send
        #: anything at all* is not answerable from the live deque.
        self.armed = 0
        #: Every discharge, ever.
        self.discharged = 0

    def arm(  # pylint: disable=too-many-arguments
        self,
        *,
        key: str,
        symbol: str,
        trade_id: str,
        strategy_id: str,
        reason: str,
        trigger: str,
        at: float,
    ) -> InFlightFlatten:
        """Record ONE sent protective flatten. Called from the send, never here."""
        if len(self._entries) == self._entries.maxlen:
            self.dropped += 1
        entry = InFlightFlatten(
            key=key,
            symbol=symbol,
            trade_id=trade_id,
            strategy_id=strategy_id,
            reason=reason,
            trigger=trigger,
            sent_ts=at,
        )
        self._entries.append(entry)
        self.armed += 1
        return entry

    def for_symbol(self, symbol: str) -> tuple[InFlightFlatten, ...]:
        """Every un-reconciled flatten sent for one symbol, OLDEST FIRST."""
        return tuple(entry for entry in self._entries if entry.symbol == symbol)

    def discharge(self, entry: InFlightFlatten) -> bool:
        """Drop one reconciled flatten. False if it was already gone."""
        try:
            self._entries.remove(entry)
        except ValueError:
            return False
        self.discharged += 1
        return True

    def in_flight(self) -> tuple[InFlightFlatten, ...]:
        """Everything sent and not yet reconciled, oldest first."""
        return tuple(self._entries)

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block."""
        return {
            "armed": self.armed,
            "discharged": self.discharged,
            "dropped": self.dropped,
            # Through the ACCESSOR, not the deque: `in_flight()` is what an
            # outside reader is told to call, and a record that reached past it
            # would leave the one public verb with no caller in shipped code.
            "in_flight": [
                {
                    "key": entry.key,
                    "symbol": entry.symbol,
                    "trade_id": entry.trade_id,
                    "trigger": entry.trigger,
                    "sent_ts": entry.sent_ts,
                }
                for entry in self.in_flight()
            ],
        }


@dataclass(frozen=True)
class ClosingOutcome:  # pylint: disable=too-many-instance-attributes
    # NINE fields and every one is a distinct fact a reader outside the process
    # needs by name: what closed, under what identity, at what price, what the
    # release actually was, and which of the four fan-outs did not happen.
    # Collapsing any of them into a boolean would make the safety question —
    # *is the capital back and is the stop gone* — unanswerable from the record.
    """What ONE closing fill did. Read off the objects, never counted here."""

    trade_id: str
    symbol: str
    strategy_id: str
    close_price: float
    reason: str
    hard_reset: bool
    #: §3's Σ open margin AFTER the commit, off the picture the commit returned.
    #: Check contract rule 2 one layer down: the return of a mutating call is not
    #: a verification, so this is the WRITER's own published figure and not this
    #: module's arithmetic.
    open_margin_after: float
    #: The ENTRY order whose synthetic stop this close retired, or "" when the
    #: join held none (§4's untargeted uncertainty flatten can reach that state).
    entry_order_id: str
    #: Each fan-out that did NOT happen, with the port's own reason (rule 11).
    failures: tuple[str, ...] = ()


class ClosingFillHandler:  # pylint: disable=too-many-instance-attributes
    # NINE collaborators, and the count IS the measurement, exactly as
    # `limiterd.FillPath` records for the entry side: §4's close is a fan-out
    # over four independent consumers (§3's table, §4's two stop books, §9's
    # WAL, §4:203-206's strategy channel) plus the three books that identify the
    # trade. A facade over them would hide the cost this class exists to report.
    """§4's CLOSE, driven by the closing fill. CALLS; never re-implements.

    Every consumer below is a shipped object this arc did not edit — §3's
    picture book, §4's `StopBook`, C1's `StopWatch`, §3's origin join, §9's WAL,
    §4:214's dedup — and the whole change is that a closing exec report now
    reaches them. That sentence is ARC 046's and ARC 047's about their own
    halves, and it is the shape of I1.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        picture: FinancialPictureBook,
        stops: StopBook,
        stop_watch: StopWatch,
        origins: EntryOrderOrigins,
        dedup: ExecReportDedup,
        strategy: ExitSinkPort,
        plane1: Plane1Port,
        in_flight: FlattenInFlightBook,
        arbiter: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._picture = picture
        self._stops = stops
        self._stop_watch = stop_watch
        self._origins = origins
        self._dedup = dedup
        self._strategy = strategy
        self._plane1 = plane1
        self._in_flight = in_flight
        #: OPTIONAL, and the option is a real reading rather than a convenience:
        #: §4's arbiter holds the AUTHORITATIVE reason and FSM verdict for a
        #: TARGETED close (`request_close`), and a build without it falls back to
        #: the reason the daemon recorded at the send. Both are real answers; the
        #: arbiter's is the better one because it is the one §4 arbitrated.
        self._arbiter = arbiter
        self._clock = clock
        #: Every close, oldest first. Evidence, never the hot path.
        self.closes: list[ClosingOutcome] = []
        #: Closing fills refused for a reason that is not "this is not a close" —
        #: an ambiguous attribution, a §3 commit that refused. NAMED, never
        #: counted (check contract rule 11).
        self.refusals: list[str] = []
        #: Re-delivered closing fills §4:214 deduplicated. Counted separately
        #: from `closes` because *closed once* and *asked twice* are two facts.
        self.duplicates = 0
        #: Fan-outs that failed AFTER the §3 commit. See the module docstring on
        #: why they are recorded rather than raised (FC1's ruling, one module on).
        self.unbooked: list[str] = []

    # -- recognition --------------------------------------------------------

    # R0911 refused with a reason: EIGHT returns, and each is one of the eight
    # distinguishable answers to *is this exec report a close this process asked
    # for* — not a fill, an approved entry, nothing in flight for the symbol, no
    # live row, a targeted match, a targeted miss, a sole-row attribution, and an
    # ambiguous one. Collapsing any pair would merge two readings this module
    # exists to keep apart, and the ambiguous case in particular must stay its
    # own exit because it RECORDS a refusal on the way out.
    def recognize(  # pylint: disable=too-many-return-statements
        self, completion: SenderCompletion
    ) -> InFlightFlatten | None:
        """Is this exec report a CLOSE this process asked for? DERIVED, never told.

        Returns the in-flight flatten it completes, or `None` — and `None` is not
        a refusal: it means *not mine*, and the caller hands the completion to
        the ordinary §3 dispatch, whose behaviour is unchanged. The three facts
        and why each is necessary are in the module docstring.
        """
        if completion.event != EVENT_FILL:
            return None
        if self._origins.origin_for_order(completion.client_order_id) is not None:
            # An approved ENTRY. `nixrisk/fills.py`'s cascade owns it.
            return None
        candidates = self._in_flight.for_symbol(completion.symbol)
        if not candidates:
            return None
        live = self._live_rows(completion.symbol)
        if not live:
            # The flatten was sent and this symbol has no live §3 row: either it
            # is already closed (the idempotent case) or this process never held
            # one (§4's untargeted uncertainty flatten against a venue position
            # the Limiter cannot see — D3.372). Nothing to close either way.
            return None
        for entry in candidates:
            if entry.trade_id:
                if any(row.trade_id == entry.trade_id for row in live):
                    return entry
                continue
            # An UNTARGETED §4 uncertainty flatten. Attribution is by symbol,
            # and it is refused rather than guessed when the symbol carries more
            # than one live trade: closing the wrong trade_id would release the
            # wrong capital and retire the wrong stop, and §17 fails closed.
            if len(live) == 1:
                return entry
            self.refusals.append(
                f"{SITE}: a closing fill arrived for {completion.symbol!r} "
                f"({completion.client_order_id}/{completion.exec_id}) against an "
                f"UNTARGETED protective flatten (trigger={entry.trigger!r}), and "
                f"this process holds {len(live)} live §3 rows in that symbol "
                f"({sorted(row.trade_id for row in live)}). §4 tags feedback BY "
                "trade id so it cannot be applied to the wrong position; refusing "
                "to guess which one the venue closed. NOT closed, NOT discharged"
            )
            return None
        return None

    # -- the close ----------------------------------------------------------

    def close(self, completion: SenderCompletion) -> ClosingOutcome | None:
        """Reconcile ONE closing fill, or return `None` if it is not one.

        The order of the four consumers is the safety property and is argued in
        the module docstring. This method RAISES only `Refused`, and only from
        the §3 commit; every later failure is recorded on `unbooked`.
        """
        entry = self.recognize(completion)
        if entry is None:
            return None
        if not self._dedup.claim((completion.client_order_id, completion.exec_id)):
            self.duplicates += 1
            self.refusals.append(
                f"{SITE}: exec report "
                f"({completion.client_order_id}, {completion.exec_id}) was "
                "already dispatched. §4:214 deduplicates broker events by "
                "(order_id, exec_id); a second close would release the same "
                "open margin twice and retire a stop that is already gone"
            )
            return None
        row = self._row_for(entry, completion.symbol)
        if row is None:  # pragma: no cover - `recognize` proved one exists
            self.refusals.append(
                f"{SITE}: the §3 row for trade {entry.trade_id!r} vanished "
                "between recognition and close"
            )
            return None
        reason, hard_reset = self._attribution(entry, row.trade_id)

        # (1) §3 — THE AUTHORITY. OPEN/CLOSING -> CLOSED, which is what releases
        # the open margin: `picture.OPEN_MARGIN_STATES` excludes CLOSED, so the
        # Σ is re-derived DOWN by the writer rather than adjusted by anyone here.
        # A refusal aborts the whole close and leaves the flatten armed.
        try:
            published = self._picture.commit(
                positions=tuple(
                    replace(current, state=PositionState.CLOSED)
                    if current.trade_id == row.trade_id
                    else current
                    for current in self._picture.current().positions
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.refusals.append(
                f"{SITE}: §3 REFUSED the close of trade {row.trade_id!r} in "
                f"{row.symbol!r}: {type(exc).__name__}: {exc}. NOTHING "
                "downstream ran — the stop is still armed, no §12.10 row was "
                "booked, the strategy was not told and the protective flatten "
                "stays IN FLIGHT. The venue may be flat and this process is not "
                "claiming otherwise"
            )
            raise Refused(self.refusals[-1]) from exc

        now = self._clock()
        failures: list[str] = []
        entry_order = self._entry_order(row.trade_id)

        # (2) §4's two stop books. The synthetic stop belongs to the ENTRY order
        # and dies with the position it protected; C1's fire-once mark dies with
        # it for the same reason (D3.481: `StopWatch.forget` is the ONLY release,
        # and until this arc nothing in shipped code called it).
        self._forget_stops(entry_order, failures)

        # (3) §9/§12.10's terminal row. Contained: see the module docstring.
        self._book_closed(
            row=row,
            completion=completion,
            reason=reason,
            ts=now,
            failures=failures,
        )

        # (4) §4:203-206's `closed` outcome with §4's FSM hard reset to flat.
        try:
            self._strategy.on_closed(
                row.trade_id, row.strategy_id, reason, hard_reset=hard_reset
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            failures.append(
                f"{SITE}: §4:203-206's `closed` notify for trade "
                f"{row.trade_id!r} was NOT delivered: {type(exc).__name__}: "
                f"{exc}. The position IS closed and its capital IS released; the "
                "strategy was not told and its FSM was not hard-reset to flat"
            )

        self._in_flight.discharge(entry)
        outcome = ClosingOutcome(
            trade_id=row.trade_id,
            symbol=row.symbol,
            strategy_id=row.strategy_id,
            close_price=completion.price,
            reason=reason,
            hard_reset=hard_reset,
            open_margin_after=float(getattr(published, "sum_open_margin", 0.0)),
            entry_order_id=entry_order,
            failures=tuple(failures),
        )
        self.unbooked.extend(failures)
        self.closes.append(outcome)
        return outcome

    # -- internals ----------------------------------------------------------

    def _live_rows(self, symbol: str) -> tuple[PositionRow, ...]:
        """§3's live rows in one symbol, off the ONE published table."""
        return tuple(
            row
            for row in self._picture.current().positions
            if row.symbol == symbol and row.state in LIVE_STATES
        )

    def _row_for(self, entry: InFlightFlatten, symbol: str) -> PositionRow | None:
        """The single §3 row this close targets."""
        live = self._live_rows(symbol)
        if entry.trade_id:
            return next((row for row in live if row.trade_id == entry.trade_id), None)
        return live[0] if len(live) == 1 else None

    def _attribution(self, entry: InFlightFlatten, trade_id: str) -> tuple[str, bool]:
        """§6.1b:352's WORD and §4's FSM verdict, from the best authority present.

        §4's arbiter is asked FIRST where one is wired: `request_close` is the
        one place a close is DECIDED, it records the reason it decided under and
        whether the FSM hard-resets, and re-deriving either here would be the
        system choosing the same fact twice. The daemon's own send record is the
        fallback, and it is a real answer rather than a default — §4's untargeted
        uncertainty flatten never reaches the arbiter at all.
        """
        if self._arbiter is not None:
            record = self._arbiter.closed_record(trade_id)
            if record is not None:
                return str(record.reason), bool(record.hard_reset)
        # A protective flatten is the only thing this book ever records, and §4
        # hard-resets the FSM to flat on a protective win.
        return entry.reason, True

    def _entry_order(self, trade_id: str) -> str:
        """The ENTRY order that opened this trade, off §3/§4's join. `""` if none."""
        origin = self._origins.origin_for_trade(trade_id)
        return "" if origin is None else str(getattr(origin, "client_order_id", ""))

    def _forget_stops(self, entry_order: str, failures: list[str]) -> None:
        """Retire §4's synthetic stop and C1's fire-once mark. Contained.

        `StopBook.forget` is LOUD on an unknown id — *"a forget for a stop that
        does not exist is a keying defect, not a no-op"* — so it is asked only
        where the book says one is armed, and the ABSENCE is recorded rather
        than swallowed: a position that closed with no stop in the book is the
        unprotected-position condition §14 exists for, arriving late.

        `StopWatch.forget` is silent by design (its book is SPARSE — only orders
        that actually breached), so it is called unconditionally and its return
        value says whether a mark was really released.
        """
        if not entry_order:
            failures.append(
                f"{SITE}: this close retired NO synthetic stop — §3/§4's join "
                "holds no entry order for the trade, so there is no key to "
                "forget under. A stop armed against that order (if any) is still "
                "live in `StopBook`"
            )
            return
        try:
            if self._stops.get(entry_order) is None:
                failures.append(
                    f"{SITE}: no synthetic stop was armed for entry order "
                    f"{entry_order!r} when its position closed. §12.1 makes the "
                    "stop Limiter-held, so this position was closed while "
                    "nothing in this process was protecting it"
                )
            else:
                self._stops.forget(entry_order)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            failures.append(
                f"{SITE}: §4's stop for {entry_order!r} was NOT retired: "
                f"{type(exc).__name__}: {exc}"
            )
        try:
            self._stop_watch.forget(entry_order)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            failures.append(
                f"{SITE}: C1's fire-once mark for {entry_order!r} was NOT "
                f"released (D3.481): {type(exc).__name__}: {exc}"
            )

    def _book_closed(
        self,
        *,
        row: PositionRow,
        completion: SenderCompletion,
        reason: str,
        ts: float,
        failures: list[str],
    ) -> None:
        """§12.10's terminal `closed` row, NON-REALIZING. See the module docstring."""
        event = EventRow(
            kind=EventKind.CLOSED,
            ts=ts,
            strategy_id=row.strategy_id,
            reason=reason,
            trade_id=row.trade_id,
            fields={
                SYMBOL_FIELD: row.symbol,
                CLOSE_PRICE_FIELD: repr(float(completion.price)),
                EXEC_ID_FIELD: completion.exec_id,
                CLOSING_ORDER_FIELD: completion.client_order_id,
                STATUS_FIELD: (
                    "no per-trade realized figure rides this row: §4's "
                    "`protective_exit` row already booked this trade's "
                    "realization and nixscore.ema SUMS every realizing row in a "
                    "pair's day, so a second one would double the trade's "
                    "contribution to §6.6's rank"
                ),
            },
        )
        try:
            self._plane1.enqueue(event)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            failures.append(
                f"{SITE}: §12.10's `closed` row for trade {row.trade_id!r} was "
                f"NOT appended: {type(exc).__name__}: {exc}. The position IS "
                "closed and its capital IS released; §9's record does not say so"
            )

    # -- evidence -----------------------------------------------------------

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. ENUMERATED where a name is owed.

        `closes` is a list and not a count for `limiterd.FillPath.record`'s
        reason: the safety question is *was THIS trade's capital released and
        THIS trade's stop retired*, and no total can answer it.
        """
        return {
            "closes": [
                {
                    "trade_id": outcome.trade_id,
                    "symbol": outcome.symbol,
                    "strategy_id": outcome.strategy_id,
                    "close_price": outcome.close_price,
                    "reason": outcome.reason,
                    "hard_reset": outcome.hard_reset,
                    "open_margin_after": outcome.open_margin_after,
                    "entry_order_id": outcome.entry_order_id,
                    "failures": list(outcome.failures),
                }
                for outcome in self.closes
            ],
            "closed": len(self.closes),
            "duplicates": self.duplicates,
            "refusals": list(self.refusals),
            "unbooked": list(self.unbooked),
            "flattens": self._in_flight.record(),
        }
