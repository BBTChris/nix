"""ARC 029 Stage 2.1 — every protective path fires in ONE simulation, end to end.

R2's stated done-when. Stage 1 proved each exit-half module in ISOLATION; this
file COMPOSES them — one simulated broker, ONE Plane-1 writer, the real
`StopBook`, `SurvivalWatch` and `ProtectiveFlatten` wired together — and drives
each of B1's FIREABLE triggers through the whole path: detection -> Limiter-only
execution -> the §12.10 Plane-1 row(s) it produces -> (where the path reconciles)
the CONFIRMED flat state. The seams BETWEEN the modules are what is measured here,
which no isolated suite can see.

§0a — the hypotheses this file refuses to assume:
* **A "simulation" where the detector never actually breaches measures nothing.**
  Every path drives a REAL breach/trigger — a price through a stop, a reading below
  the net-liq floor, an onset with pending entries — and asserts the flatten FIRED
  and the exact Plane-1 rows, never merely that a call returned.
* **The §9 sole-writer property is only visible when two producers share one
  sink.** The reservation ledger and the flatten executor write to the SAME
  `Plane1Recorder`, and the onset path asserts BOTH a `CANCEL` row and a
  `RESERVATION_RELEASED` row land on that one writer under the same cause.

WHAT THE EXIT HALF STILL CANNOT DO — asserted here, not implied away (§2.4):
* `SESSION_CLOSE` and `SENTINEL` are REFUSED (R4); the refusal is driven, so the
  gap cannot read as "flattened". A killed Risk Engine is an unprotected position
  until the Sentinel (R4) — these stops are synthetic and die with the process
  (§12.1). This file wires only the triggers whose DETECTION exists (synthetic
  stop, net-liq floor, uncertainty, onset); `STALE_PRICE` (datafeed) and `ORPHAN`
  (heartbeat, R5) detection live elsewhere and are declared, not driven.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# pylint: disable=missing-class-docstring,too-many-instance-attributes
# invalid-name: test names are sentences. protected-access: the tests seed the
# executor's own picture mirror to stand up an open book. missing-*-docstring /
# too-few-public-methods: the sinks are one-verb stand-ins named after the ports
# they mirror. too-many-instance-attributes: `Rig` bundles the wired collaborators,
# which is the integration's subject, not behavioural accretion.

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "broker"))

# pylint: disable=wrong-import-position
from broker_seam import Balance, Position
from nixrisk.flatten import (
    CloseTarget,
    NotAnOnsetCause,
    PendingEntry,
    ProtectiveFlatten,
    TriggerNotFireable,
)
from nixrisk.picture import FinancialPictureBook, PictureSink
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionRow,
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)
from nixrisk.stops import StopBook
from nixrisk.survival import (
    Alert,
    AlertTier,
    BrokerReading,
    SurvivalWatch,
)

# ==========================================================================
# ONE broker for the whole exit half, and ONE Plane-1 writer
# ==========================================================================


class SimBroker:
    """A broker that satisfies BOTH `BrokerFlattenPort` (flatten path) and
    `BrokerReconcilePort` (survival's poll) from ONE position/balance truth.

    The whole point of the integration harness: the flatten executor and the
    survival watch reconcile against the SAME broker, so a flatten one fires is a
    position the other stops seeing. A per-module stub could not show that.
    """

    def __init__(self, *, positions: list[Position], cash: float) -> None:
        self._positions: dict[str, Position] = {p.symbol: p for p in positions}
        self._cash = cash
        self._net_liq = cash + sum(0.0 for _ in positions)
        self.realize_on_flatten: dict[str, float] = {}
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []
        self._venue_ts = 0.0

    # -- BrokerFlattenPort (flatten.py) ------------------------------------
    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)
        for sym in [symbol] if symbol else list(self._positions):
            if sym is not None and sym in self._positions:
                del self._positions[sym]
                self._cash += self.realize_on_flatten.get(sym, 0.0)
        self._net_liq = self._cash  # flat => net-liq collapses to cash

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.net_qty != 0]

    async def query_balance(self) -> Balance:
        return Balance(
            cash=self._cash,
            net_liquidation=self._net_liq,
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=0.0,
        )

    # -- BrokerReconcilePort (survival.py) ---------------------------------
    def poll(self) -> BrokerReading:
        self._venue_ts += 1.0
        rows = tuple(
            PositionRow(
                trade_id=f"T-{sym}",
                symbol=sym,
                strategy_id="strat-1",
                size=abs(p.net_qty),
                margin=1000.0,
                state=PositionState.OPEN,
            )
            for sym, p in self._positions.items()
        )
        return BrokerReading(
            cash=self._cash,
            net_liq=self._net_liq,
            positions=rows,
            venue_ts=self._venue_ts,
        )


class Plane1Recorder:
    """§9 Plane-1 sink. ONE per simulation — reservation ledger AND flatten share it."""

    def __init__(self) -> None:
        self.rows: list[EventRow] = []

    def enqueue(self, row: EventRow) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)

    def of(self, kind: EventKind) -> list[EventRow]:
        return [row for row in self.rows if row.kind is kind]


@dataclass
class StrategySink:
    closed: list[tuple[str, str, str, bool]] = field(default_factory=list)

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


@dataclass
class Scoring:
    booked: list[tuple[tuple[str, ...], float, float]] = field(default_factory=list)

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


@dataclass
class MirrorSink:
    emitted: list[object] = field(default_factory=list)

    def emit(self, picture: object) -> None:
        self.emitted.append(picture)


@dataclass
class Alerts:
    seen: list[Alert] = field(default_factory=list)

    def emit(self, alert: Alert) -> None:
        self.seen.append(alert)

    def of(self, tier: AlertTier) -> list[Alert]:
        return [a for a in self.seen if a.tier is tier]


class FireAdapter:
    """The seam between DETECTION and EXECUTION (survival -> flatten).

    `SurvivalWatch` detects a net-liq breach and hands the trigger to a
    `FlattenExecutor`; this adapter routes that in-process call to the real
    `ProtectiveFlatten.fire`. It is the wiring §14 describes — detection may live
    anywhere, execution is the Limiter's — made concrete for the simulation.
    """

    def __init__(self, executor: ProtectiveFlatten) -> None:
        self._executor = executor
        self.fired: list[tuple[FlattenTrigger, str]] = []

    def flatten(self, trigger: FlattenTrigger, reason: str) -> None:
        self.fired.append((trigger, reason))
        self._executor.fire(trigger)  # symbol=None => flatten the whole book


_T = 1000.0


def _clock() -> float:
    global _T  # pylint: disable=global-statement
    _T += 1.0
    return _T


def _book(sink: PictureSink | None, *, balance: float) -> FinancialPictureBook:
    return FinancialPictureBook(balance=balance, deployable_fraction=0.70, sink=sink)


def _order(coid: str, symbol: str = "MESU6") -> ProposedOrder:
    return ProposedOrder(
        client_order_id=coid,
        strategy_id="strat-1",
        symbol=symbol,
        side=Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


@dataclass
class Rig:
    broker: SimBroker
    plane1: Plane1Recorder
    ledger: ReservationLedger
    executor: ProtectiveFlatten
    strategy: StrategySink
    scoring: Scoring
    mirror: MirrorSink
    alerts: Alerts


def _rig(*, positions: list[Position], cash: float) -> Rig:
    """The whole exit half, wired to ONE broker and ONE Plane-1 writer."""
    broker = SimBroker(positions=positions, cash=cash)
    plane1 = Plane1Recorder()
    ledger = ReservationLedger(plane1)  # writes RESERVATION_* to the SAME plane1
    mirror = MirrorSink()
    strategy = StrategySink()
    scoring = Scoring()
    executor = ProtectiveFlatten(
        broker=broker,
        ledger=ledger,
        picture=_book(mirror, balance=cash),
        strategy=strategy,
        plane1=plane1,
        scoring=scoring,
        clock=_clock,
    )
    return Rig(broker, plane1, ledger, executor, strategy, scoring, mirror, Alerts())


# ==========================================================================
# NON-VACUITY — the rig actually holds an open book before any trigger fires
# ==========================================================================


def test_NONVACUITY_the_wired_rig_starts_with_a_REAL_open_position() -> None:
    rig = _rig(positions=[Position("MESU6", 1, 7800.0)], cash=20000.0)
    reading = rig.broker.poll()
    assert reading.positions, "the simulation must start with a position to flatten"
    assert reading.net_liq == 20000.0


# ==========================================================================
# PATH 1 — synthetic stop: a price through the stop closes the trade
# ==========================================================================


@pytest.mark.asyncio
async def test_SYNTHETIC_STOP_a_price_through_the_stop_flattens_and_books_the_rows() -> (
    None
):
    """Detection (StopBook.breached) -> execution (fire) -> §12.10 rows -> confirmed."""
    rig = _rig(positions=[Position("MESU6", 1, 7800.0)], cash=20000.0)
    stops = StopBook(tick_size={"MESU6": 0.25})
    order = _order("c-1")
    stops.arm(7800.0, order)  # fixed stop 20 ticks below 7800 => 7795.0
    # The Limiter's mirror holds the open position, so reconcile can SEE it close.
    rig.executor._picture.commit(  # pylint: disable=protected-access
        balance=20000.0,
        positions=[
            PositionRow(
                trade_id="T-MESU6",
                symbol="MESU6",
                strategy_id="strat-1",
                size=1,
                margin=1000.0,
                state=PositionState.OPEN,
            )
        ],
    )

    breached = stops.breached("MESU6", 7794.0)  # price through the stop
    assert breached, "the stop must actually be breached — a no-breach path is vacuous"

    action = rig.executor.fire(
        FlattenTrigger.SYNTHETIC_STOP,
        targets=[CloseTarget("T-MESU6", "MESU6", "strat-1")],
    )
    assert action.trigger is FlattenTrigger.SYNTHETIC_STOP
    assert rig.broker.flatten_calls, "the exit did not reach the broker"
    stops.forget("c-1")

    confirmed = await rig.executor.reconcile_and_publish()
    assert confirmed.is_flat, confirmed
    # §12.10: a protective exit books a protective-exit row and a closed row.
    assert rig.plane1.of(EventKind.PROTECTIVE_EXIT), rig.plane1.rows
    assert rig.plane1.of(EventKind.CLOSED), rig.plane1.rows
    assert rig.strategy.closed[-1][3] is True, "protective close must hard-reset FSM"


# ==========================================================================
# PATH 2 — net-liq floor: a reading below the floor fires flatten + Critical
# ==========================================================================


@pytest.mark.asyncio
async def test_NET_LIQ_FLOOR_a_reading_below_the_floor_fires_the_flatten_and_a_CRITICAL() -> (
    None
):
    """DETECTION (SurvivalWatch) wired to EXECUTION (fire) through FireAdapter."""
    rig = _rig(positions=[Position("MESU6", 1, 7800.0)], cash=9000.0)
    adapter = FireAdapter(rig.executor)
    watch = SurvivalWatch(
        safety_pad=0.10,
        broker=rig.broker,
        flatten=adapter,
        alert=rig.alerts,
        tolerance=1.0,
        clock=_clock,
    )
    # floor = Σ open margin (1000) × (1 + 0.10) = 1100. Drive net-liq BELOW it.
    # `mark` IS the standing per-tick watch: it evaluates and fires on the breach.
    outcome = watch.mark(cash=9000.0, net_liq=1000.0, sum_open_margin=1000.0)

    assert outcome.reading.breached, "the reading must be below the floor"
    assert outcome.fired, "the mark must fire the flatten on the breach"
    # The latch suppresses a re-fire while the breach persists (no duplicate exit).
    assert watch.check().fired is False, "a persisting breach must not re-fire"
    assert adapter.fired and adapter.fired[-1][0] is FlattenTrigger.NET_LIQ_FLOOR
    assert rig.broker.flatten_calls, "the flatten did not reach the broker"
    # §12.9: the breach pages CRITICAL, carrying the snapshot — not just a code.
    crit = rig.alerts.of(AlertTier.CRITICAL)
    assert crit, rig.alerts.seen
    assert crit[-1].snapshot, "a Critical alert must carry the snapshot values"

    confirmed = await rig.executor.reconcile_and_publish()
    assert confirmed.is_flat, confirmed


def test_NET_LIQ_a_reading_ABOVE_the_floor_does_NOT_fire_the_flatten() -> None:
    """The other side of the floor — a non-breach must not fire (both directions)."""
    rig = _rig(positions=[Position("MESU6", 1, 7800.0)], cash=20000.0)
    adapter = FireAdapter(rig.executor)
    watch = SurvivalWatch(
        safety_pad=0.10,
        broker=rig.broker,
        flatten=adapter,
        alert=rig.alerts,
        tolerance=1.0,
        clock=_clock,
    )
    watch.mark(cash=20000.0, net_liq=20000.0, sum_open_margin=1000.0)
    outcome = watch.check()
    assert not outcome.reading.breached
    assert not outcome.fired
    assert not adapter.fired
    assert not rig.alerts.of(AlertTier.CRITICAL)


# ==========================================================================
# PATH 3 — uncertainty: flatten-to-be-safe, reconcile, publish CONFIRMED
# ==========================================================================


@pytest.mark.asyncio
async def test_UNCERTAINTY_flatten_then_publish_the_CONFIRMED_state_not_the_intent() -> (
    None
):
    rig = _rig(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    rig.broker.realize_on_flatten["MESU6"] = 500.0  # broker truth differs from intent
    # Seed the picture mirror with the open position so reconcile can confirm it closed.
    rig.executor._picture.commit(  # pylint: disable=protected-access
        balance=20344.34,
        positions=[
            PositionRow(
                trade_id="T-MESU6",
                symbol="MESU6",
                strategy_id="strat-1",
                size=1,
                margin=1000.0,
                state=PositionState.OPEN,
            )
        ],
    )

    rig.executor.fire(
        FlattenTrigger.UNCERTAINTY,
        symbol="MESU6",
        targets=[CloseTarget("T-MESU6", "MESU6", "strat-1")],
    )
    confirmed = await rig.executor.reconcile_and_publish()

    assert confirmed.is_flat, confirmed
    # The published balance is broker truth AFTER the flatten, never the projection.
    assert confirmed.confirmed_balance == 20844.34, confirmed
    assert confirmed.projection_balance == 20344.34, confirmed
    assert confirmed.confirmed_balance != confirmed.projection_balance
    assert rig.mirror.emitted, "the confirmed state was never published to the mirror"


# ==========================================================================
# PATH 4 — onset: cancels pending ENTRIES and releases under the NAMED cause,
# and both rows land on the ONE Plane-1 writer (§9 sole writer)
# ==========================================================================


@pytest.mark.parametrize(
    ("cause", "coid"),
    [(TerminalPath.HALT_ONSET, "c-halt"), (TerminalPath.BLACKOUT_ONSET, "c-blk")],
)
def test_ONSET_cancels_pending_entries_and_releases_under_its_OWN_cause(
    cause: TerminalPath, coid: str
) -> None:
    rig = _rig(positions=[], cash=20000.0)
    rig.ledger.take(_order(coid), _clock())  # a reservation to release
    pending = [PendingEntry(coid, "strat-1", "MESU6")]

    result = rig.executor.cancel_entries_on_onset(cause, pending)

    assert coid in rig.broker.cancel_calls, "the entry cancel did not reach the broker"
    assert result.cancelled == (coid,), result
    # §9 sole writer: BOTH the cancel row and the reservation-release row are on
    # the ONE plane1, and the release names THIS onset cause, never a bare CANCEL.
    cancels = rig.plane1.of(EventKind.CANCEL)
    releases = rig.plane1.of(EventKind.RESERVATION_RELEASED)
    assert cancels and cancels[-1].fields["symbol"] == "MESU6", rig.plane1.rows
    assert releases, rig.plane1.rows
    assert cause.value in releases[-1].reason, releases[-1]


def test_ONSET_a_NON_onset_cause_is_REFUSED_naming_the_wrong_cause_hazard() -> None:
    rig = _rig(positions=[], cash=20000.0)

    with pytest.raises(NotAnOnsetCause) as exc:
        rig.executor.cancel_entries_on_onset(
            TerminalPath.CANCEL, [PendingEntry("c-x", "strat-1", "MESU6")]
        )
    assert "onset" in str(exc.value)


# ==========================================================================
# §2.4 — WHAT THE EXIT HALF STILL CANNOT DO, driven so the gap cannot hide
# ==========================================================================


@pytest.mark.parametrize(
    "trigger", [FlattenTrigger.SESSION_CLOSE, FlattenTrigger.SENTINEL]
)
def test_R4_triggers_are_REFUSED_not_silently_no_opped(
    trigger: FlattenTrigger,
) -> None:
    """§2.4: SESSION_CLOSE (R4 calendar) and SENTINEL (R4) are refused LOUDLY.

    A silent no-op would read as "flattened" — the one thing a protective path
    may never do. The refusal is the honest statement that the mechanism is unbuilt.
    """
    rig = _rig(positions=[Position("MESU6", 1, 7800.0)], cash=20000.0)

    with pytest.raises(TriggerNotFireable) as exc:
        rig.executor.fire(trigger)
    assert "R4" in str(exc.value) or "does not fire" in str(exc.value)
    assert not rig.broker.flatten_calls, "an R4 refusal must not reach the broker"
