"""ARC 033 / Stage 1 / B — §6.1b's session-close flatten, DRIVEN across time.

The can-fail suite for `scripts/nixrisk/session.py`. Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md` unless another document is named.

THE FOUR HAZARDS THIS BRIEF NAMES ARE TREATED AS HYPOTHESES AND MEASURED:

* **A flatten test where the deadline never arrives proves nothing.** Every
  firing control here ticks the scheduler at least TWICE — once strictly BEFORE
  the deadline and once at or after it — and asserts the before-tick produced
  `NOT_DUE` with NO broker call, before asserting the after-tick fired. A single
  sampled instant is refused as vacuous by
  `test_the_BEFORE_TICK_really_did_NOTHING_...`.
* **A halted-market test that never halts the market proves nothing.** The venue
  double is driven through `TRADABLE` and `HALTED` in the SAME test, so the
  halted verdict is shown to be a function of the venue state and not a
  constant.
* **A boot validator test that never feeds an invalid set proves nothing.** That
  half lives in `test_risk_config.py`, where the per-symbol inverted pair is fed
  and the rejection message is asserted to NAME the symbol.
* **`ok=True` over a lost bar (ARC 022 F13).** The subject carries no boolean at
  all, which is asserted structurally over `dataclasses.fields`; and the plant
  `_ReportsSuccessFromHavingFired` derives the verdict from *we called fire*
  rather than from broker truth, and is shown to produce `FLAT_CONFIRMED` over a
  position the broker still holds — the exact defect the real derivation cannot
  express.

`debug.md` §7.12 is answered per control in its docstring.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-few-public-methods,too-many-instance-attributes
# pylint: disable=too-many-locals,duplicate-code,wrong-import-position
# missing-class-docstring / too-few-public-methods: the doubles are named after
# the ports they stand in for. too-many-instance-attributes: `Rig` is a record of
# what one control drives — each field is a collaborator an assertion reaches.
# too-many-locals: `_rig`'s locals ARE the collaborator set the scheduler takes.
# invalid-name: the test names are sentences. protected-access: the plants reach
# the scheduler's injected collaborators to build a WRONG variant — that is how a
# falsifier is written. duplicate-code: the fan-out doubles necessarily mirror
# the ports they stand in for, which `test_flatten.py` also stands in for.

from __future__ import annotations

import asyncio
import dataclasses
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "broker"))

from broker_seam import Balance, Position  # pylint: disable=wrong-import-position
from nixrisk.flatten import ProtectiveFlatten
from nixrisk.picture import FinancialPictureBook
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import EventKind, FlattenTrigger, PositionRow, PositionState
from nixrisk.session import (  # pylint: disable=protected-access
    _RESIDUAL_RISK,
    SESSION_REASON,
    SessionFlattener,
    SessionFlattenOutcome,
    SessionFlattenVerdict,
    SessionScheduleError,
    UnknownSessionClose,
    VenueState,
)
from nixrisk.survival import AlertTier

SPEC = REPO / "docs" / "nics_risk_subsystem_spec_v1.3.md"

#: One symbol's session close, and the two instants either side of its §6.1b
#: deadline at a 10-minute lead. Named so every control drives the SAME crossing.
CLOSE = datetime(2026, 8, 20, 21, 0, tzinfo=UTC)
DEADLINE = CLOSE - timedelta(minutes=10)
BEFORE = DEADLINE - timedelta(minutes=1)
AFTER = DEADLINE + timedelta(seconds=1)
NEXT_CLOSE = CLOSE + timedelta(days=1)


# ==========================================================================
# Doubles
# ==========================================================================


class Calendar:
    """§6.1b:340's live calendar, narrowed. Returns the next close at or after."""

    def __init__(self, closes: list[datetime] | None = None) -> None:
        self.closes = sorted(closes or [CLOSE, NEXT_CLOSE])
        self.calls: list[tuple[str, datetime]] = []

    def next_close(self, symbol: str, at: datetime) -> datetime | None:
        self.calls.append((symbol, at))
        for close in self.closes:
            if close >= at:
                return close
        return None


class Venue:
    """The exchange's tradability, DRIVEABLE. §12.6's input."""

    def __init__(self, state: VenueState = VenueState.TRADABLE) -> None:
        self.state = state
        self.calls: list[tuple[str, datetime]] = []

    def venue_state(self, symbol: str, at: datetime) -> VenueState:
        self.calls.append((symbol, at))
        return self.state


class Broker:
    """A broker whose flatten really moves truth — or REFUSES to, on demand.

    `deaf` is the §4 indeterminate case made concrete: the flatten call lands,
    the venue accepts nothing, and `query_positions` afterwards still shows the
    symbol. A stub whose flatten always works cannot express the residual case
    at all, which is why this double can be told to fail.
    """

    def __init__(self, *, positions: list[Position] | None = None, cash: float) -> None:
        self._positions = {p.symbol: p for p in (positions or [])}
        self._cash = cash
        self.deaf = False
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)
        if self.deaf:
            return
        for sym in [symbol] if symbol else list(self._positions):
            self._positions.pop(sym, None)

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.net_qty != 0]

    async def query_balance(self) -> Balance:
        return Balance(
            cash=self._cash,
            net_liquidation=self._cash,
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=0.0,
        )


class Strategy:
    def __init__(self) -> None:
        self.closed: list[tuple[str, str, str, bool]] = []

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


class Scoring:
    def __init__(self) -> None:
        self.booked: list[tuple[tuple[str, ...], float, float]] = []

    def book_realized(
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        del ts
        self.booked.append((closed_trades, realized_delta, confirmed_balance))


class Plane1:
    def __init__(self) -> None:
        self.rows: list[object] = []

    def enqueue(self, row: object) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)


class Alerts:
    def __init__(self) -> None:
        self.emitted: list[object] = []

    def emit(self, alert: object) -> None:
        self.emitted.append(alert)


class Sink:
    def __init__(self) -> None:
        self.emitted: list[object] = []

    def emit(self, picture: object) -> None:
        self.emitted.append(picture)


@dataclasses.dataclass
class Rig:
    """Everything one control drives, so an assertion can reach any of it."""

    flattener: SessionFlattener
    broker: Broker
    venue: Venue
    calendar: Calendar
    alerts: Alerts
    strategy: Strategy
    plane1: Plane1
    book: FinancialPictureBook


def _rig(
    *,
    open_position: bool = True,
    venue: VenueState = VenueState.TRADABLE,
    lead_min: float = 10,
    cls: type[SessionFlattener] = SessionFlattener,
    symbols: tuple[str, ...] = ("MES",),
) -> Rig:
    """One scheduler over one symbol, with a real `ProtectiveFlatten` beneath it.

    The executor is the REAL one, not a double: the honesty clause's verdict is
    derived from `ConfirmedFlat`, so a fake executor returning a fake
    confirmation would test this suite's own fixture rather than §4's reconcile.
    """
    positions = [Position("MES", 1, 7800.0)] if open_position else []
    broker = Broker(positions=positions, cash=20344.34)
    sink = Sink()
    book = FinancialPictureBook(balance=20344.34, deployable_fraction=0.70, sink=sink)
    if open_position:
        book.commit(
            positions=[
                PositionRow(
                    trade_id="T-1",
                    symbol="MES",
                    strategy_id="S-1",
                    size=1,
                    margin=1200.0,
                    state=PositionState.OPEN,
                    stop_distance=8,
                )
            ]
        )
    plane1 = Plane1()
    strategy = Strategy()
    executor = ProtectiveFlatten(
        broker=broker,
        ledger=ReservationLedger(plane1),
        picture=book,
        strategy=strategy,
        plane1=plane1,
        scoring=Scoring(),
        clock=lambda: 1000.0,
    )
    venue_double = Venue(venue)
    calendar = Calendar()
    alerts = Alerts()
    flattener = cls(
        calendar=calendar,
        venue=venue_double,
        book=book,
        executor=executor,
        alert=alerts,
        lead_min=dict.fromkeys(symbols, lead_min),
        symbols=symbols,
    )
    return Rig(
        flattener=flattener,
        broker=broker,
        venue=venue_double,
        calendar=calendar,
        alerts=alerts,
        strategy=strategy,
        plane1=plane1,
        book=book,
    )


def _tick(rig: Rig, at: datetime):
    return asyncio.run(rig.flattener.tick_async(at))


# ==========================================================================
# NON-VACUITY — the deadline really is crossed, and the before-tick did nothing
# ==========================================================================


def test_the_DEADLINE_is_SESSION_CLOSE_minus_the_PER_SYMBOL_LEAD() -> None:
    """§6.1b:340's arithmetic, and it is per-symbol.

    `debug.md` §7.12: this could pass over a constant only if the lead were
    ignored, so two DIFFERENT leads are driven and the two deadlines asserted to
    differ by exactly the lead difference.
    """
    ten = _rig(lead_min=10).flattener
    twenty = _rig(lead_min=20).flattener

    close_a, deadline_a = ten.deadline("MES", BEFORE)
    close_b, deadline_b = twenty.deadline("MES", BEFORE)

    assert close_a == close_b == CLOSE
    assert deadline_a == CLOSE - timedelta(minutes=10)
    assert deadline_b == CLOSE - timedelta(minutes=20)
    assert deadline_a - deadline_b == timedelta(minutes=10)


def test_the_BEFORE_TICK_really_did_NOTHING_and_the_AFTER_TICK_FIRED() -> None:
    """THE DRIVE ACROSS THE DEADLINE. The hazard this brief names first.

    `debug.md` §7.12: a flatten suite passes while measuring nothing if the
    deadline never arrives — every tick is `NOT_DUE`, no broker call is ever
    made, and every assertion about firing is vacuously skipped. Closed by
    asserting BOTH sides of one crossing in one control: before, `NOT_DUE` and
    an EMPTY broker call list; after, a fired verdict and a real call.
    """
    rig = _rig()

    before = _tick(rig, BEFORE)

    assert [o.verdict for o in before.outcomes] == [SessionFlattenVerdict.NOT_DUE]
    assert not rig.broker.flatten_calls, rig.broker.flatten_calls
    assert before.fired == ()
    assert before.evaluated == 1

    after = _tick(rig, AFTER)

    assert [o.verdict for o in after.outcomes] == [SessionFlattenVerdict.FLAT_CONFIRMED]
    assert rig.broker.flatten_calls == ["MES"], rig.broker.flatten_calls
    assert len(after.fired) == 1


def test_a_PRE_DEADLINE_TICK_reads_NEITHER_the_VENUE_nor_the_BOOK() -> None:
    """NOT_DUE is decided by the clock alone (§6.1b:340).

    A pre-deadline tick that polled the venue would make §12.6's input a
    function of tick cadence, and a suite could then "prove" the halted path by
    polling early. Asserted on the double's own call log.
    """
    rig = _rig()

    _tick(rig, BEFORE)

    assert not rig.venue.calls, rig.venue.calls


# ==========================================================================
# THE CLEAN FIRE — §6.1b:342's reason, §6.1b:353's Info tier
# ==========================================================================


def test_the_CLEAN_FIRE_reaches_the_STRATEGY_as_reason_SESSION() -> None:
    """§6.1b:352 — *strategy receives `closed, reason=session`*, verbatim.

    `debug.md` §7.12: could pass over any reason string if only "a close was
    notified" were asserted. Closed by comparing to the spec's WORD and by
    asserting it differs from the trigger's own name, which is the string the
    executor would have derived on its own.
    """
    rig = _rig()
    _tick(rig, BEFORE)

    _tick(rig, AFTER)

    assert rig.strategy.closed, "the §4 fan-out never told the strategy anything"
    trade_id, strategy_id, reason, hard_reset = rig.strategy.closed[-1]
    assert (trade_id, strategy_id) == ("T-1", "S-1")
    assert reason == SESSION_REASON == "session", reason
    assert reason != FlattenTrigger.SESSION_CLOSE.value
    assert hard_reset is True, "§6.1b:352 frees the one-in-flight slot"


def test_the_CLEAN_FIRE_books_a_PLANE_1_row_carrying_the_SESSION_reason() -> None:
    """§9's record of money truth keeps §6.1b's word, not a derived one."""
    rig = _rig()
    _tick(rig, BEFORE)

    _tick(rig, AFTER)

    kinds = {getattr(row, "kind", None) for row in rig.plane1.rows}
    assert EventKind.PROTECTIVE_EXIT in kinds, kinds
    assert EventKind.CLOSED in kinds, kinds
    reasons = {getattr(row, "reason", "") for row in rig.plane1.rows}
    assert SESSION_REASON in reasons, reasons


def test_the_CLEAN_FIRE_alerts_at_INFO_and_states_NO_residual_risk() -> None:
    """§6.1b:353 — *Info-tier on clean fire*. And a clean fire has no residual."""
    rig = _rig()
    _tick(rig, BEFORE)

    sweep = _tick(rig, AFTER)
    outcome = sweep.outcomes[0]

    assert outcome.verdict is SessionFlattenVerdict.FLAT_CONFIRMED
    assert outcome.exposure_rides is False
    assert outcome.residual_risk == "", outcome.residual_risk
    assert outcome.alert is not None
    assert outcome.alert.tier is AlertTier.INFO, outcome.alert


def test_NOTHING_OPEN_is_a_DISTINCT_verdict_from_FLAT_CONFIRMED() -> None:
    """`debug.md` §7.12 answer 3: an always-empty book must not mint the
    confirmed verdict for free. The two facts are told apart by the pre-fire
    book, and an empty book never reaches the broker at all."""
    rig = _rig(open_position=False)
    _tick(rig, BEFORE)

    sweep = _tick(rig, AFTER)

    assert sweep.outcomes[0].verdict is SessionFlattenVerdict.NOTHING_OPEN
    assert not rig.broker.flatten_calls, rig.broker.flatten_calls


# ==========================================================================
# §12.6 — THE HONESTY CLAUSE. Two riding verdicts, both driven.
# ==========================================================================


def test_a_HALTED_MARKET_at_the_DEADLINE_RIDES_and_pages_CRITICAL() -> None:
    """§12.6:641-642 + §6.1b:349-351, driven with the market ACTUALLY HALTED.

    `debug.md` §7.12: a halted-market control that never halts the market proves
    nothing, so this drives the SAME rig through `TRADABLE` (before the
    deadline, where nothing fires) and then `HALTED` at the deadline — and
    asserts NO order was sent, because §4:231-235 forbids firing into a shut
    venue and §12.6 says a halted market cannot be flattened by any design.
    """
    rig = _rig()
    assert rig.venue.state is VenueState.TRADABLE
    _tick(rig, BEFORE)

    rig.venue.state = VenueState.HALTED  # THE MARKET HALTS.
    sweep = _tick(rig, AFTER)
    outcome = sweep.outcomes[0]

    assert outcome.verdict is SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED
    assert outcome.exposure_rides is True
    assert not rig.broker.flatten_calls, (
        "an order was fired into a HALTED venue — §4's market-tradable guard"
    )
    assert outcome.confirmed is None, "no order was sent, so no reconcile happened"
    assert outcome.venue is VenueState.HALTED
    assert outcome.alert is not None
    assert outcome.alert.tier is AlertTier.CRITICAL, outcome.alert
    assert "cannot be flattened by any design" in outcome.residual_risk
    assert "DOES NOT HOLD" in outcome.residual_risk
    assert outcome.alert.snapshot["exposure_rides"] == "true"
    assert "RESIDUAL RISK" in outcome.alert.detail, outcome.alert.detail


@pytest.mark.parametrize(
    "state", [VenueState.HALTED, VenueState.CLOSED, VenueState.UNKNOWN]
)
def test_EVERY_NON_TRADABLE_VENUE_STATE_fails_CLOSED(state: VenueState) -> None:
    """`UNKNOWN` is treated exactly as halted (§4: *guarded, never blind*).

    The interesting member is `UNKNOWN`: a scheduler that fired when it could
    not read the venue would be firing blind, and one that reported a clean
    flatten would be the F13 defect with a different input.
    """
    rig = _rig()
    _tick(rig, BEFORE)

    rig.venue.state = state
    sweep = _tick(rig, AFTER)

    assert (
        sweep.outcomes[0].verdict is SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED
    )
    assert not rig.broker.flatten_calls


def test_a_FLATTEN_THE_BROKER_IGNORED_is_UNCONFIRMED_not_CONFIRMED() -> None:
    """§4's indeterminate path resolving to NOT flat — the second riding verdict.

    The venue looked tradable, the order WAS sent, and broker truth afterwards
    still shows the symbol. This is the exact shape of ARC 022's F13 (`ok=True`
    over a lost bar): the action happened, and the world did not change. The
    verdict is derived from `query_positions`, so it cannot say confirmed.
    """
    rig = _rig()
    rig.broker.deaf = True  # the venue accepts the order and does nothing
    _tick(rig, BEFORE)

    sweep = _tick(rig, AFTER)
    outcome = sweep.outcomes[0]

    assert rig.broker.flatten_calls == ["MES"], "the order really was sent"
    assert outcome.verdict is SessionFlattenVerdict.EXPOSURE_RIDES_UNCONFIRMED
    assert outcome.exposure_rides is True
    assert outcome.confirmed is not None, "a reconcile DID happen here"
    assert outcome.confirmed.is_flat is False
    assert outcome.alert is not None
    assert outcome.alert.tier is AlertTier.CRITICAL
    assert "STILL shows this symbol" in outcome.residual_risk


def test_the_TWO_RIDING_VERDICTS_are_DISTINGUISHABLE_from_each_other() -> None:
    """A caller must be able to tell "never sent" from "sent and ignored".

    They are different operator actions — one waits for reopen, the other
    escalates to the broker — so collapsing them into one "failed" member would
    lose the only fact that decides what to do next.
    """
    halted = _rig()
    _tick(halted, BEFORE)
    halted.venue.state = VenueState.HALTED
    halted_outcome = _tick(halted, AFTER).outcomes[0]

    deaf = _rig()
    deaf.broker.deaf = True
    _tick(deaf, BEFORE)
    deaf_outcome = _tick(deaf, AFTER).outcomes[0]

    assert halted_outcome.verdict is not deaf_outcome.verdict
    assert halted_outcome.residual_risk != deaf_outcome.residual_risk
    assert halted_outcome.confirmed is None and deaf_outcome.confirmed is not None
    both = {halted_outcome.verdict, deaf_outcome.verdict}
    assert len(both) == 2, both
    assert all(v.exposure_rides for v in both)
    assert all(v.alert_tier is AlertTier.CRITICAL for v in both)


def test_a_RIDING_VERDICT_is_DISTINGUISHABLE_from_a_CLEAN_FLATTEN() -> None:
    """The property the brief asks for, asserted on FOUR independent channels.

    A caller with any one of these can tell the cases apart, which is what makes
    the honesty structural rather than a matter of reading the docstring.
    """
    clean = _rig()
    _tick(clean, BEFORE)
    clean_outcome = _tick(clean, AFTER).outcomes[0]

    halted = _rig()
    _tick(halted, BEFORE)
    halted.venue.state = VenueState.HALTED
    riding = _tick(halted, AFTER).outcomes[0]

    assert clean_outcome.verdict is not riding.verdict  # 1: the member
    assert clean_outcome.exposure_rides != riding.exposure_rides  # 2: the predicate
    assert bool(clean_outcome.residual_risk) != bool(riding.residual_risk)  # 3
    assert clean_outcome.alert.tier is not riding.alert.tier  # 4: the §12.9 tier


# ==========================================================================
# THE F13 SHAPE — no boolean exists, and the plant that invents one FAILS
# ==========================================================================


def test_the_OUTCOME_carries_NO_BOOLEAN_SUCCESS_FIELD_at_all() -> None:
    """ARC 022 F13 closed by ABSENCE, measured on the dataclass's own fields.

    `debug.md` §7.12: a suite could assert "the verdict is right" forever while
    a stray `ok: bool = True` sat beside it and every caller read that instead.
    Closed by walking the declared fields.
    """
    names = {field.name for field in dataclasses.fields(SessionFlattenOutcome)}

    for banned in ("ok", "success", "succeeded", "flattened", "done", "passed"):
        assert banned not in names, f"{banned!r} is a success flag on the outcome"
    assert "verdict" in names and "residual_risk" in names, names


def test_EVERY_RIDING_VERDICT_carries_a_RESIDUAL_RISK_SENTENCE() -> None:
    """§12.6 requires the residual risk be documented honestly, and the outcome
    is where the reader meets it. Enumerated over the enum so a SIXTH member
    cannot be added without landing on one side of this."""
    for verdict in SessionFlattenVerdict:
        text = _RESIDUAL_RISK.get(verdict, "")
        if verdict.exposure_rides:
            assert text, f"{verdict} rides exposure and states no residual risk"
            assert "§12.6" in text or "§4" in text, text
        else:
            assert not text, f"{verdict} does not ride and yet states a residual"


def test_EVERY_RIDING_VERDICT_maps_to_CRITICAL_and_no_other_does() -> None:
    """§6.1b:353's tier split, enumerated rather than sampled."""
    for verdict in SessionFlattenVerdict:
        expected = AlertTier.CRITICAL if verdict.exposure_rides else AlertTier.INFO
        assert verdict.alert_tier is expected, verdict


class _ReportsSuccessFromHavingFired(SessionFlattener):
    """THE PLANT. Derives the verdict from *we called fire*, not from broker truth.

    This is ARC 022's F13 transplanted into this module: the action is performed,
    the result is assumed. It is a subclass — the plant lives in the SUBJECT
    (doctrine C.8) — and it overrides only the derivation, so everything else
    about the drive is identical to the real one.
    """

    async def _evaluate(self, symbol, at, close, deadline):  # type: ignore[override]
        if at < deadline:
            return self._outcome(
                symbol,
                close,
                deadline,
                SessionFlattenVerdict.NOT_DUE,
            )
        targets = self._open_targets(symbol)
        venue = self._venue.venue_state(symbol, at)
        if not targets:
            return self._outcome(
                symbol,
                close,
                deadline,
                SessionFlattenVerdict.NOTHING_OPEN,
                venue=venue,
            )
        self._executor.fire(
            FlattenTrigger.SESSION_CLOSE,
            symbol=symbol,
            targets=targets,
            reason="session",
        )
        confirmed = await self._executor.reconcile_and_publish()
        # THE DEFECT: the verdict follows the CALL, never the broker.
        return self._outcome(
            symbol,
            close,
            deadline,
            SessionFlattenVerdict.FLAT_CONFIRMED,
            targets,
            venue=venue,
            confirmed=confirmed,
        )


def test_the_PLANT_that_reports_SUCCESS_FROM_HAVING_FIRED_really_LIES() -> None:
    """The falsifier must LOSE the property, or the control above measures nothing.

    Driven over the SAME deaf broker the real scheduler calls
    `EXPOSURE_RIDES_UNCONFIRMED` on. The plant answers `FLAT_CONFIRMED` while
    the broker still holds the position and, worse, pages INFO. If this ever
    stops lying, the assertion in
    `test_a_FLATTEN_THE_BROKER_IGNORED_...` is no longer a discriminator and
    THIS control is the one that says so.
    """
    plant = _rig(cls=_ReportsSuccessFromHavingFired)
    plant.broker.deaf = True
    _tick(plant, BEFORE)

    outcome = _tick(plant, AFTER).outcomes[0]

    assert outcome.verdict is SessionFlattenVerdict.FLAT_CONFIRMED, (
        "the plant no longer falsifies — it stopped reporting success over a "
        "position the broker still holds"
    )
    assert outcome.exposure_rides is False
    assert outcome.alert.tier is AlertTier.INFO
    assert outcome.residual_risk == ""
    # And the ground truth the plant ignored: the position is STILL THERE.
    assert asyncio.run(plant.broker.query_positions()), "the fixture is not deaf"
    assert outcome.confirmed is not None and outcome.confirmed.is_flat is False, (
        "even the plant's own ConfirmedFlat says NOT flat — the verdict "
        "contradicts the object it was handed"
    )


# ==========================================================================
# THE LATCH, THE LOUD REFUSALS, AND §12.3
# ==========================================================================


def test_the_DEADLINE_FIRES_ONCE_PER_SESSION_and_REARMS_on_the_NEXT_close() -> None:
    """`debug.md` §7.12 answer 4: a latch that never re-arms silently disables
    the backstop from day two. Keyed by `(symbol, session_close)`, so the next
    session's close is a different key."""
    rig = _rig()
    _tick(rig, BEFORE)
    _tick(rig, AFTER)
    assert rig.broker.flatten_calls == ["MES"]

    again = _tick(rig, AFTER + timedelta(minutes=1))

    assert again.suppressed == ("MES",), again.suppressed
    assert again.outcomes == ()
    assert rig.broker.flatten_calls == ["MES"], "the latch let a second flatten out"

    # Re-open a position and cross the NEXT session's deadline.
    rig.book.commit(
        positions=[
            PositionRow(
                trade_id="T-2",
                symbol="MES",
                strategy_id="S-1",
                size=1,
                margin=1200.0,
                state=PositionState.OPEN,
                stop_distance=8,
            )
        ]
    )
    next_deadline = NEXT_CLOSE - timedelta(minutes=10) + timedelta(seconds=1)
    rearmed = _tick(rig, next_deadline)

    assert rearmed.suppressed == (), rearmed.suppressed
    assert rearmed.outcomes[0].session_close == NEXT_CLOSE
    assert rig.broker.flatten_calls == ["MES", "MES"], rig.broker.flatten_calls


def test_a_SYMBOL_WITH_NO_SESSION_CLOSE_is_a_LOUD_REFUSAL_not_a_SKIP() -> None:
    """A managed symbol with no deadline has no backstop (directive 4).

    `debug.md` §7.12 answer 2: skipping it quietly would let a sweep report an
    all-clear over an unprotected book, which is the worst available failure.
    """
    rig = _rig()
    rig.calendar.closes = []

    with pytest.raises(UnknownSessionClose) as caught:
        _tick(rig, AFTER)

    assert "MES" in str(caught.value), caught.value
    assert "no §6.1b" in str(caught.value) or "backstop" in str(caught.value)


def test_a_MANAGED_SYMBOL_WITH_NO_LEAD_is_REFUSED_at_CONSTRUCTION() -> None:
    """A missing tunable is never defaulted (directive 4, `RiskConfigError`'s rule)."""
    with pytest.raises(SessionScheduleError) as caught:
        SessionFlattener(
            calendar=Calendar(),
            venue=Venue(),
            book=FinancialPictureBook(balance=1.0, deployable_fraction=0.7),
            executor=None,  # type: ignore[arg-type]  # refused before use
            alert=Alerts(),
            lead_min={"MES": 10},
            symbols=("MES", "MNQ"),
        )

    assert "MNQ" in str(caught.value), caught.value
    assert "backstop" in str(caught.value), caught.value


def test_a_NAIVE_INSTANT_is_REFUSED_never_ASSUMED_UTC() -> None:
    """§12.3: all internal time is UTC, converted exactly once at generation.

    Localising a naive instant here would be a SECOND conversion, against
    whatever tzdb this process happens to hold.
    """
    # Derived by STRIPPING the zone off the aware instant every other control
    # drives, rather than constructed: the two are then the same moment, so the
    # refusal is provably about the ZONE and not about the value.
    naive = AFTER.replace(tzinfo=None)
    rig = _rig()

    with pytest.raises(SessionScheduleError) as caught:
        _tick(rig, naive)

    assert "naive" in str(caught.value), caught.value
    assert "§12.3" in str(caught.value), caught.value


def test_a_SWEEP_REPORTS_WHAT_IT_EVALUATED_so_ZERO_is_VISIBLE() -> None:
    """`debug.md` §7.12 answer 2 made structural: a sweep over nothing says so."""
    rig = _rig(symbols=("MES",))

    sweep = _tick(rig, BEFORE)

    assert sweep.evaluated == 1, sweep
    assert sweep.at == BEFORE


def test_the_SPEC_SENTENCE_this_module_implements_is_STILL_IN_THE_FROZEN_SPEC() -> None:
    """The citations are load-bearing; a moved clause must redden something.

    Parsed from the frozen document rather than restated here, so this control
    is a comparison against the source of truth and not against itself.
    """
    # Whitespace-normalised: the frozen document hard-wraps at ~98 columns, so a
    # clause that spans a line break is one sentence with a newline inside it.
    text = " ".join(SPEC.read_text(encoding="utf-8").split())

    assert "SESSION_FLATTEN_LEAD_MIN` before each symbol's session close" in text
    assert "a halted market cannot be flattened by any design" in text
    assert "exposure rides until reopen" in text
    assert "Info-tier on clean fire" in text
    assert "`SESSION_FLATTEN_LEAD_MIN < EOD_BLACKOUT_MIN − pad` per symbol" in text
