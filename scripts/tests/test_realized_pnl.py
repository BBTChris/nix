"""ARC 037 / sub-agent A — the can-fail suite for the realized-P&L wire (D3.220).

Two subjects, and they are only worth anything together:

* `scripts/nixrisk/realized.py` — the arithmetic (pure, total, fails loud);
* `scripts/nixrisk/flatten.py`'s realizing rows — the WRITE, through the one
  `Plane1Port` §9 allows.

Every control asserts the REASON — a named field, a booked status, a message —
never an exception type or a truthy value alone (check contract v2 §11).

§7.12, THE STANDING QUESTION: what would make this suite pass while measuring
nothing?

 1. **The figure could be the PEAK rather than the close.** A trade that only
    ever goes one way cannot tell them apart, so the peak controls drive a
    position that goes GREEN WHILE OPEN and CLOSES RED, assert the written
    figure is the NEGATIVE close, and prove the assertion is falsifiable by
    driving `_PeakWriter` — a `ProtectiveFlatten` subclass that books the peak —
    and observing the same assertion go the other way.
 2. **The figure could be written and never read.** Every writer control ends
    by feeding the row it wrote through `nixscore.ema`'s real extractor and
    requiring the pair key and the EMA to come out of it, so a key the scorer
    does not read is a red here rather than a green in two files.
 3. **The absent case could be a silent zero,** which is the one failure
    `nixscore/ema.py` says makes a blind engine look like a cold start. Driven:
    a Limiter with no facts book books a `realized_status` and NO figure, and
    the scorer's own `MissingRealized` is required to fire and to NAME the key.
 4. **One close could be counted twice.** `protective_exit` and `closed` are
    BOTH realizing types and both are booked for one protective close, so the
    once-only control drives the real sequence and requires exactly one row to
    carry a number.
 5. **The two modules could agree by coincidence.** The constants are asserted
    byte-equal against `nixscore.ema`'s in both directions.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# pylint: disable=too-many-arguments,too-many-positional-arguments
# import-outside-toplevel: `plane1_sink` is imported at the two call sites
# that need it so the row-shaping helper cannot be read as a module-level
# dependency of the arithmetic tests, which import no sink at all.
# pylint: disable=import-outside-toplevel
# pylint: disable=duplicate-code,wrong-import-position
# invalid-name: the test names are sentences. protected-access: the falsifier
# subclass reaches the executor's own books to build a WRONG variant, which is
# how a falsifier is written. duplicate-code: the fan-out doubles necessarily
# mirror the ports flatten.py declares.

from __future__ import annotations

import ast
import datetime as dt
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "broker"))

from broker_seam import Balance, Position
from nixrisk.flatten import CloseAuthority, CloseTarget, ProtectiveFlatten
from nixrisk.picture import FinancialPictureBook
from nixrisk.realized import (
    BANNED_UNREALIZED_FIELDS,
    REALIZED_FIELD,
    STATUS_FIELD,
    SYMBOL_FIELD,
    ImpossibleTradeFact,
    MissingTradeFact,
    RecordedTradeFacts,
    TradeEntry,
    TradeExit,
    TradeFacts,
    realized_fields,
    realized_pnl,
)
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionRow,
    PositionState,
    Side,
)
from nixscore import ema

REALIZED_SOURCE = (REPO / "scripts" / "nixrisk" / "realized.py").read_text(
    encoding="utf-8"
)

#: The trading day every driven row is stamped on — a Wednesday, so
#: `ema.is_trading_day` accepts it and a weekend cannot silently refuse a fold.
DAY = dt.datetime(2026, 8, 12, 18, 30, tzinfo=dt.UTC)
DAY_TS = DAY.timestamp()


# ==========================================================================
# Doubles
# ==========================================================================


class Broker:
    """A `BrokerFlattenPort` whose flatten really removes the position."""

    def __init__(self, *, positions: list[Position], cash: float) -> None:
        self._positions = {p.symbol: p for p in positions}
        self._cash = cash
        self.realize_on_flatten: dict[str, float] = {}
        self.flatten_calls: list[str | None] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)
        for sym in [symbol] if symbol else list(self._positions):
            if sym in self._positions:
                del self._positions[sym]
                self._cash += self.realize_on_flatten.get(sym, 0.0)

    def cancel_order(self, client_order_id: str) -> None:
        del client_order_id

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


@dataclass
class StrategySink:
    """§4 fan-out (a). Records every `closed` notification."""

    closed: list[tuple[str, str, str, bool]] = field(default_factory=list)

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


@dataclass
class ScoringSink:
    """§4 fan-out (d). Records the ACCOUNT-LEVEL realized delta."""

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


class Plane1Recorder:
    """§9's port, recording. Durability is `plane1_sink`'s and is not the subject."""

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


class _PeakWriter(ProtectiveFlatten):
    """THE FALSIFIER: it books the OPEN PEAK instead of the exit fill.

    §6.6:435 forbids exactly this — *"a green open position can reverse before
    it closes"* — and a suite that only ever asserted "the figure is right"
    against a correct writer could not show it would notice. This one prices the
    same trade off `TradeFacts.peak_price`, which the facts book carries
    precisely so the wrong number is CONSTRUCTIBLE.
    """

    def _realized_or_reason(
        self, trade_id: str | None, symbol: str
    ) -> dict[str, str] | str:
        book = self._trade_facts
        facts = None if trade_id is None or book is None else book.facts_for(trade_id)
        if facts is None or facts.peak_price is None:
            return "no peak"
        peak_exit = TradeExit(
            trade_id=facts.exit.trade_id,
            price=facts.peak_price,
            commission=facts.exit.commission,
            fees=facts.exit.fees,
            slippage_cost=facts.exit.slippage_cost,
        )
        figure = realized_pnl(facts.entry, peak_exit)
        return {SYMBOL_FIELD: symbol, REALIZED_FIELD: figure.payload_value}


# ==========================================================================
# Builders
# ==========================================================================


def _facts(
    *,
    trade_id: str = "T-1",
    strategy_id: str = "strat-1",
    symbol: str = "MESU6",
    side: Side = Side.LONG,
    qty: int = 2,
    entry_price: float = 5000.0,
    exit_price: float = 4990.0,
    peak_price: float | None = None,
    point_value: float = 5.0,
    commission_in: float = 0.62,
    commission_out: float = 0.62,
    fees: float = 0.14,
    slippage_cost: float = 2.5,
) -> TradeFacts:
    return TradeFacts(
        entry=TradeEntry(
            trade_id=trade_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=entry_price,
            point_value=point_value,
            commission=commission_in,
        ),
        exit=TradeExit(
            trade_id=trade_id,
            price=exit_price,
            commission=commission_out,
            fees=fees,
            slippage_cost=slippage_cost,
        ),
        peak_price=peak_price,
    )


def _clock() -> float:
    return DAY_TS


def _executor(
    broker: Broker,
    *,
    picture: FinancialPictureBook,
    plane1: Plane1Recorder,
    facts: RecordedTradeFacts | None = None,
    scoring: ScoringSink | None = None,
    cls: type[ProtectiveFlatten] = ProtectiveFlatten,
) -> ProtectiveFlatten:
    return cls(
        broker=broker,
        ledger=ReservationLedger(plane1),
        picture=picture,
        strategy=StrategySink(),
        plane1=plane1,
        scoring=scoring or ScoringSink(),
        trade_facts=facts,
        clock=_clock,
    )


def _book_with(*rows: PositionRow, balance: float = 20344.34) -> FinancialPictureBook:
    book = FinancialPictureBook(balance=balance, deployable_fraction=0.70, sink=None)
    book.commit(balance=balance, positions=list(rows))
    return book


def _row(
    trade_id: str = "T-1", symbol: str = "MESU6", strategy_id: str = "strat-1"
) -> PositionRow:
    return PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id=strategy_id,
        size=2,
        margin=1000.0,
        state=PositionState.OPEN,
        stop_distance=20,
    )


def _partition(rows: list[EventRow]) -> tuple[list[EventRow], list[EventRow]]:
    """Every REALIZING-typed row split into figure-carrying and reason-carrying.

    **NO REALIZING ROW MAY BE SILENT**, and this is the partition that says so.
    `nixscore.ema.realized_closes` REFUSES a realizing-typed row with no figure
    (`MissingRealized`), and `nixrisk.flatten` books TWO realizing-typed rows for
    one protective close — `protective_exit` at the decision and `closed` after
    reconcile — of which exactly one may carry a number or §6.6:438's per-day SUM
    double-counts the trade. So the caller asserts the split is total and folds
    only the figure-carrying half; the other half is required to NAME its reason.
    The tension between the two is real and is recorded as CHECK-DEBT D3.284.
    """
    from nixrisk.plane1_sink import resolve_event_type

    realizing = [
        row for row in rows if resolve_event_type(row.kind) in ema.REALIZING_EVENT_TYPES
    ]
    figures = [row for row in realizing if REALIZED_FIELD in row.fields]
    reasons = [row for row in realizing if STATUS_FIELD in row.fields]
    assert len(figures) + len(reasons) == len(realizing), (
        "a realizing row carries neither a figure nor a reason — it is SILENT, "
        f"which is the one state that must not exist: {[dict(r.fields) for r in realizing]}"
    )
    assert not [row for row in figures if row in reasons]
    return figures, reasons


def _log_row(row: EventRow) -> dict[str, object]:
    """One booked `EventRow` as the log row `nixscore.ema` reads.

    Shaped exactly like `plane1_sink._values_clause` writes it: the payload is
    `fields` plus `event_kind`, `symbol` is lifted into its own column, and the
    event type is the §12.10 name. Built HERE from the row the writer produced,
    so the scorer is fed the writer's own output and not a fixture.
    """
    from nixrisk.plane1_sink import resolve_event_type

    payload = {**dict(row.fields), "event_kind": row.kind.value}
    return {
        "event_id": f"{row.kind.value}-{row.trade_id}",
        "event_type": resolve_event_type(row.kind),
        "strategy_id": row.strategy_id,
        "trade_id": row.trade_id,
        "symbol": payload.get(SYMBOL_FIELD),
        "occurred_at": dt.datetime.fromtimestamp(row.ts, tz=dt.UTC),
        "payload": payload,
    }


# ==========================================================================
# THE ARITHMETIC
# ==========================================================================


def test_the_FORMULA_is_the_FROZEN_SEAM_s_formula_term_by_term() -> None:
    """SEAM (a): `direction × (exit − entry) × qty × point_value − every cost`.

    Asserted term by term rather than against one total, because a total can be
    right while two terms are wrong in opposite directions.
    """
    figure = realized_pnl(
        _facts(exit_price=5010.0).entry, _facts(exit_price=5010.0).exit
    )
    assert figure.gross == pytest.approx(1.0 * (5010.0 - 5000.0) * 2 * 5.0)
    assert figure.gross == pytest.approx(100.0)
    assert figure.commission_in == 0.62
    assert figure.commission_out == 0.62
    assert figure.fees == 0.14
    assert figure.slippage_cost == 2.5
    assert figure.costs == pytest.approx(3.88)
    assert figure.net == pytest.approx(96.12)
    assert figure.gross - figure.costs == pytest.approx(figure.net)


def test_a_SHORT_realizes_the_OPPOSITE_SIGN_of_a_long_on_the_same_prices() -> None:
    """§6.6 ranks the strategy's verdict; a short that fell is a WIN.

    §7.12: a suite driving only longs would pass over a module that ignored
    `side` entirely, because `+1` is the default anyone writes by accident.
    """
    long_facts = _facts(side=Side.LONG, exit_price=4990.0)
    short_facts = _facts(side=Side.SHORT, exit_price=4990.0)
    long_figure = realized_pnl(long_facts.entry, long_facts.exit)
    short_figure = realized_pnl(short_facts.entry, short_facts.exit)
    assert long_figure.gross == pytest.approx(-100.0)
    assert short_figure.gross == pytest.approx(+100.0)
    assert long_figure.net < 0 < short_figure.net
    # The COSTS do not flip with direction — they debit both ways (§6.5:409).
    assert long_figure.costs == short_figure.costs == pytest.approx(3.88)


def test_the_COSTS_are_SUBTRACTED_a_gross_win_can_be_a_realized_LOSS() -> None:
    """§6.5:409-410: commissions and fees *"debit on close"*.

    The driven case is the one that matters: a trade that made money on price
    and lost it on costs. A gross-only scorer would rank this strategy as a
    winner, which is the misranking the cost terms exist to prevent.
    """
    facts = _facts(exit_price=5000.4, qty=1, point_value=5.0, slippage_cost=6.0)
    figure = realized_pnl(facts.entry, facts.exit)
    assert figure.gross == pytest.approx(2.0)
    assert figure.costs == pytest.approx(7.38)
    assert figure.net == pytest.approx(-5.38)
    assert figure.gross > 0 > figure.net


def test_the_PAYLOAD_VALUE_round_trips_the_float_EXACTLY() -> None:
    """`EventRow.fields` is `Mapping[str, str]` on the FROZEN seam, so the figure
    travels as text. `repr` is the shortest round-tripping form; driven on the
    values that break naive formatting rather than asserted."""
    for exit_price in (5000.1, 4999.7, 5000.0 + 1 / 3, 4999.0 + 1e-9):
        facts = _facts(exit_price=exit_price)
        figure = realized_pnl(facts.entry, facts.exit)
        assert float(figure.payload_value) == figure.net, exit_price
    assert (
        float(realized_fields(_facts())[REALIZED_FIELD])
        == realized_pnl(_facts().entry, _facts().exit).net
    )


def test_the_KEY_is_SS6_6_448_s_LOCKED_PAIR_and_not_the_account() -> None:
    """§6.6:448: *"Canonical key = `(strategy_id, symbol)` (v1.3, locked)"*."""
    figure = realized_pnl(_facts().entry, _facts().exit)
    assert figure.key == ("strat-1", "MESU6")


# ==========================================================================
# FAIL CLOSED AND LOUD — every refusal NAMES the field
# ==========================================================================


@pytest.mark.parametrize(
    ("kwargs", "field_named"),
    [
        ({"point_value": None}, "entry.point_value"),
        ({"commission_in": None}, "entry.commission"),
        ({"fees": None}, "exit.fees"),
        ({"slippage_cost": None}, "exit.slippage_cost"),
        ({"exit_price": None}, "exit.price"),
        ({"entry_price": float("nan")}, "entry.price"),
        ({"exit_price": math.inf}, "exit.price"),
        ({"fees": True}, "exit.fees"),
        ({"commission_out": "0.62"}, "exit.commission"),
    ],
)
def test_a_MISSING_or_UNREADABLE_input_RAISES_and_NAMES_THE_FIELD(
    kwargs: dict[str, object], field_named: str
) -> None:
    """Never a silent zero. `nixscore/ema.py`: an absent figure read as a zero
    advance makes a blind engine indistinguishable from a healthy cold start —
    and a WRITER that emits 0.0 disables even the reader's refusal."""
    facts = _facts(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(MissingTradeFact) as caught:
        realized_pnl(facts.entry, facts.exit)
    assert field_named in str(caught.value), caught.value
    assert "trade 'T-1'" in str(caught.value)


@pytest.mark.parametrize("qty", [0, -1, True])
def test_a_NON_POSITIVE_QTY_is_REFUSED_not_priced_as_a_small_loss(qty: object) -> None:
    """A zero-qty 'trade' realizes exactly minus its costs — a number that looks
    like a small loss and is really a missing position."""
    facts = _facts(qty=qty)  # type: ignore[arg-type]
    with pytest.raises(ImpossibleTradeFact) as caught:
        realized_pnl(facts.entry, facts.exit)
    assert "qty=" in str(caught.value) and "whole number of" in str(caught.value)


def test_a_NON_POSITIVE_POINT_VALUE_is_REFUSED_because_the_RANKING_INVERTS() -> None:
    facts = _facts(point_value=-5.0)
    with pytest.raises(ImpossibleTradeFact) as caught:
        realized_pnl(facts.entry, facts.exit)
    assert "point_value=-5.0" in str(caught.value)
    assert "ranking inverts" in str(caught.value)


def test_an_UNATTRIBUTABLE_figure_is_REFUSED_SS6_6_448_keys_on_the_PAIR() -> None:
    facts = _facts(strategy_id="")
    with pytest.raises(MissingTradeFact) as caught:
        realized_pnl(facts.entry, facts.exit)
    assert "§6.6:448" in str(caught.value)


def test_an_EXIT_FROM_A_DIFFERENT_TRADE_is_REFUSED_not_priced() -> None:
    """Two trades' facts crossed produce a number attributed to whichever the
    caller passed first — the misattribution §6.6:448 exists to prevent."""
    entry = _facts(trade_id="T-1").entry
    other_exit = _facts(trade_id="T-2").exit
    with pytest.raises(MissingTradeFact) as caught:
        realized_pnl(entry, other_exit)
    assert "'T-2'" in str(caught.value)


# ==========================================================================
# THE OPEN MARK CANNOT REACH THE ARITHMETIC
# ==========================================================================


def test_a_position_GREEN_WHILE_OPEN_that_CLOSES_RED_realizes_the_CLOSE() -> None:
    """§6.6:435, the sentence in full: *"a green open position can reverse before
    it closes."*

    §7.12: a trade that only ever moves one way cannot distinguish the peak from
    the close, so this one goes +$150 green while open and closes -$100 red.
    Both the SIGN and the MAGNITUDE are asserted against the close.
    """
    facts = _facts(entry_price=5000.0, peak_price=5015.0, exit_price=4990.0)
    peak_figure = realized_pnl(
        facts.entry,
        TradeExit(
            trade_id="T-1", price=5015.0, commission=0.62, fees=0.14, slippage_cost=2.5
        ),
    )
    figure = realized_pnl(facts.entry, facts.exit)
    assert peak_figure.net == pytest.approx(146.12), "the peak really is green"
    assert figure.net == pytest.approx(-103.88), figure.key_facts
    assert figure.net < 0 < peak_figure.net
    assert figure.net != peak_figure.net


def test_realized_pnl_TAKES_NO_PARAMETER_A_MARK_COULD_ARRIVE_THROUGH() -> None:
    """The structural half of the same ban, over the shipped source.

    A drive proves the number is right TODAY; this proves there is no door. The
    function's signature is `(entry, exit_fill)` and its body names no
    mark-shaped identifier — so a later edit that reached for one is a red here
    even if it happened to compute the same number on the driven case.
    """
    tree = ast.parse(REALIZED_SOURCE)
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "realized_pnl"
    )
    params = [a.arg for a in func.args.args] + [a.arg for a in func.args.kwonlyargs]
    assert params == ["entry", "exit_fill"], params
    banned = ("peak", "mark_to_market", "unrealized", "high_water", "mtm", "open_pnl")
    named = {
        node.id.lower() for node in ast.walk(func) if isinstance(node, ast.Name)
    } | {
        node.attr.lower() for node in ast.walk(func) if isinstance(node, ast.Attribute)
    }
    leaked = sorted(name for name in named if any(bad in name for bad in banned))
    assert not leaked, f"realized_pnl reads a mark-shaped name: {leaked}"
    assert "peak_price" in REALIZED_SOURCE, (
        "the falsifier needs a peak to be constructible — if TradeFacts stopped "
        "carrying one, this scan would be over a module that simply never had a "
        "mark, which proves nothing about ignoring one"
    )


def test_realized_fields_EMITS_EXACTLY_TWO_KEYS_and_NO_BANNED_ONE() -> None:
    fields = realized_fields(_facts(peak_price=5015.0))
    assert set(fields) == {SYMBOL_FIELD, REALIZED_FIELD}, fields
    assert not set(fields) & BANNED_UNREALIZED_FIELDS


# ==========================================================================
# THE WRITER AND THE READER AGREE — asserted, never assumed
# ==========================================================================


def test_the_WRITER_S_CONSTANTS_are_BYTE_EQUAL_to_the_SCORER_S() -> None:
    """`nixrisk` does not import `nixscore` (the exit path must not depend on the
    ranking optimisation), so the two constants are restated — and the
    restatement is held equal MECHANICALLY rather than by convention."""
    assert REALIZED_FIELD == ema.REALIZED_FIELD
    assert BANNED_UNREALIZED_FIELDS == ema.BANNED_UNREALIZED_FIELDS
    assert REALIZED_FIELD not in BANNED_UNREALIZED_FIELDS
    assert STATUS_FIELD not in ema.BANNED_UNREALIZED_FIELDS
    # And the status key must not be mistakable for the figure.
    assert STATUS_FIELD != REALIZED_FIELD


def test_the_KINDS_the_writer_marks_REALIZING_are_the_SCORER_S_OWN_SET() -> None:
    """The writer books `closed` and `protective_exit`; the scorer's
    `REALIZING_EVENT_TYPES` is `{closed, protective_exit, sentinel_flatten}`.
    The writer's two must be a SUBSET, and `exit_intent` must NOT be in it."""
    from nixrisk.plane1_sink import EVENT_KIND_TO_PLANE1

    written = {
        EVENT_KIND_TO_PLANE1[EventKind.CLOSED],
        EVENT_KIND_TO_PLANE1[EventKind.PROTECTIVE_EXIT],
    }
    assert written <= ema.REALIZING_EVENT_TYPES, written
    assert EVENT_KIND_TO_PLANE1[EventKind.EXIT_INTENT] in ema.NON_REALIZING_EVENT_TYPES


# ==========================================================================
# THE WRITE — driven through the real ProtectiveFlatten
# ==========================================================================


async def _drive_close(
    facts: TradeFacts | None,
    *,
    cls: type[ProtectiveFlatten] = ProtectiveFlatten,
    realize_cash: float = -103.88,
) -> tuple[Plane1Recorder, ScoringSink, object]:
    """One real protective close of T-1, reconciled. Returns the booked rows.

    **The facts are recorded AFTER `request_close` and BEFORE reconcile**, which
    is the real sequence and not a convenience: at protective-exit time no exit
    fill is confirmed (§4), so the facts book cannot yet answer. The other
    ordering — facts already known when the exit fires, as after a §12.1 marker
    replay — is driven by its own control below.
    """
    plane1 = Plane1Recorder()
    broker = Broker(
        positions=[Position(symbol="MESU6", net_qty=2, avg_price=5000.0)],
        cash=20344.34,
    )
    broker.realize_on_flatten["MESU6"] = realize_cash
    scoring = ScoringSink()
    book = None if facts is None else RecordedTradeFacts()
    executor = _executor(
        broker,
        picture=_book_with(_row()),
        plane1=plane1,
        facts=book,
        scoring=scoring,
        cls=cls,
    )
    executor.request_close(
        CloseTarget(trade_id="T-1", symbol="MESU6", strategy_id="strat-1"),
        CloseAuthority.PROTECTIVE,
        "synthetic stop",
    )
    if book is not None and facts is not None:
        book.record(facts)
    confirmed = await executor.reconcile_and_publish()
    return plane1, scoring, confirmed


@pytest.mark.asyncio
async def test_the_CLOSED_row_CARRIES_the_realized_figure_and_the_PAIR() -> None:
    """D3.220, the keystone: the durable record now carries what §6.6 reads."""
    expected = realized_pnl(_facts().entry, _facts().exit)

    plane1, _, _ = await _drive_close(_facts(peak_price=5015.0))

    closed = plane1.of(EventKind.CLOSED)
    assert len(closed) == 1, plane1.rows
    row = closed[0]
    assert row.fields[SYMBOL_FIELD] == "MESU6"
    assert row.strategy_id == "strat-1"
    assert float(row.fields[REALIZED_FIELD]) == expected.net
    assert float(row.fields[REALIZED_FIELD]) == pytest.approx(-103.88)
    assert STATUS_FIELD not in row.fields


@pytest.mark.asyncio
async def test_the_WRITTEN_ROW_FEEDS_THE_SCORER_and_the_EMA_ADVANCES() -> None:
    """Written-but-not-read is the failure this closes. The row the writer
    produced is fed through `nixscore.ema`'s REAL extractor and fold."""
    plane1, _, _ = await _drive_close(_facts())

    figures, reasons = _partition(plane1.rows)
    assert len(figures) == 1 and len(reasons) == 1
    closes = ema.realized_closes([_log_row(row) for row in figures])
    assert len(closes) == 1, [c.event_type for c in closes]
    assert closes[0].key == ("strat-1", "MESU6")
    scored = ema.score_pairs(closes, 10, DAY.date())
    assert set(scored) == {("strat-1", "MESU6")}
    score = scored[("strat-1", "MESU6")]
    assert score.realized_ema == pytest.approx(-103.88)
    assert score.realized_ema != 0.0, "a zero EMA is a cold start, not a measurement"
    assert score.closes_observed == 1


@pytest.mark.asyncio
async def test_a_PEAK_WRITING_LIMITER_IS_CAUGHT_the_assertion_is_FALSIFIABLE() -> None:
    """The both-halves control for the green-while-open case.

    `_PeakWriter` books the peak. Same trade, same facts, same drive — and the
    written figure comes out POSITIVE where the shipped writer's is negative.
    Without this, "the figure is the close" is a claim about a writer that was
    never shown capable of writing anything else.
    """
    honest, _, _ = await _drive_close(_facts(peak_price=5015.0))
    peaked, _, _ = await _drive_close(_facts(peak_price=5015.0), cls=_PeakWriter)

    honest_value = float(honest.of(EventKind.CLOSED)[0].fields[REALIZED_FIELD])
    peaked_value = float(peaked.of(EventKind.CLOSED)[0].fields[REALIZED_FIELD])
    assert honest_value == pytest.approx(-103.88)
    assert peaked_value == pytest.approx(146.12)
    assert honest_value < 0 < peaked_value
    # And the scorer would have ranked the loser as a winner.
    honest_ema = ema.score_pairs(
        ema.realized_closes([_log_row(r) for r in _partition(honest.rows)[0]]),
        10,
        DAY.date(),
    )[("strat-1", "MESU6")].realized_ema
    peaked_ema = ema.score_pairs(
        ema.realized_closes([_log_row(r) for r in _partition(peaked.rows)[0]]),
        10,
        DAY.date(),
    )[("strat-1", "MESU6")].realized_ema
    assert honest_ema < 0 < peaked_ema


@pytest.mark.asyncio
async def test_ONE_CLOSE_IS_BOOKED_ONCE_the_second_realizing_row_SAYS_WHY() -> None:
    """`protective_exit` AND `closed` are both realizing types and both are
    booked for one protective close. `ema.daily_advances` SUMS a pair's rows for
    the day, so two figures would double the trade's contribution to the rank."""
    plane1, _, _ = await _drive_close(_facts())

    carrying = [row for row in plane1.rows if REALIZED_FIELD in row.fields]
    assert len(carrying) == 1, [(r.kind.value, dict(r.fields)) for r in plane1.rows]
    assert carrying[0].kind is EventKind.CLOSED

    exits = plane1.of(EventKind.PROTECTIVE_EXIT)
    assert len(exits) == 1
    assert REALIZED_FIELD not in exits[0].fields
    assert "no confirmed exit fill" in exits[0].fields[STATUS_FIELD]

    # And the fold sees ONE advance, not two.
    figures, reasons = _partition(plane1.rows)
    assert [row.kind for row in figures] == [EventKind.CLOSED]
    assert [row.kind for row in reasons] == [EventKind.PROTECTIVE_EXIT]
    closes = ema.realized_closes([_log_row(row) for row in figures])
    assert len(closes) == 1, [(c.event_type, c.realized) for c in closes]


@pytest.mark.asyncio
async def test_the_SECOND_row_names_DOUBLE_COUNT_when_the_FIGURE_ALREADY_LANDED() -> (
    None
):
    """The other ordering: the facts are known BEFORE the protective exit fires
    (a marker replay, §12.1). Then `protective_exit` carries the figure and the
    `closed` row must refuse to repeat it, naming the hazard."""
    book = RecordedTradeFacts()
    book.record(_facts())
    plane1 = Plane1Recorder()
    broker = Broker(
        positions=[Position(symbol="MESU6", net_qty=2, avg_price=5000.0)],
        cash=20344.34,
    )
    executor = _executor(broker, picture=_book_with(_row()), plane1=plane1, facts=book)
    executor.request_close(
        CloseTarget(trade_id="T-1", symbol="MESU6", strategy_id="strat-1"),
        CloseAuthority.PROTECTIVE,
        "synthetic stop",
    )
    await executor.reconcile_and_publish()

    exits = plane1.of(EventKind.PROTECTIVE_EXIT)
    closed = plane1.of(EventKind.CLOSED)
    assert REALIZED_FIELD in exits[0].fields, dict(exits[0].fields)
    assert REALIZED_FIELD not in closed[0].fields
    assert "DOUBLE-COUNT" in closed[0].fields[STATUS_FIELD]
    assert "'protective_exit'" in closed[0].fields[STATUS_FIELD]


@pytest.mark.asyncio
async def test_an_EXIT_INTENT_row_carries_NO_FIGURE_it_books_NO_REALIZATION() -> None:
    """A discretionary close books `exit_intent`, which the scorer classifies
    NON-realizing: the position it names is still open until a fill says
    otherwise, so any P&L on it would be a mark (§6.6:435)."""
    book = RecordedTradeFacts()
    book.record(_facts())
    plane1 = Plane1Recorder()
    broker = Broker(
        positions=[Position(symbol="MESU6", net_qty=2, avg_price=5000.0)],
        cash=20344.34,
    )
    executor = _executor(broker, picture=_book_with(_row()), plane1=plane1, facts=book)
    executor.request_close(
        CloseTarget(trade_id="T-1", symbol="MESU6", strategy_id="strat-1"),
        CloseAuthority.DISCRETIONARY,
        "edge spent",
    )
    intents = plane1.of(EventKind.EXIT_INTENT)
    assert len(intents) == 1
    assert REALIZED_FIELD not in intents[0].fields
    assert STATUS_FIELD not in intents[0].fields
    assert set(intents[0].fields) == {SYMBOL_FIELD}


# ==========================================================================
# THE ABSENT CASE — a STATUS, never a zero
# ==========================================================================


@pytest.mark.asyncio
async def test_NO_FACTS_BOOK_books_a_STATUS_and_NEVER_A_ZERO() -> None:
    """The production state of this tree: no fill feed, so no facts. The row
    must say so in the durable record and must NOT carry a number."""
    plane1, _, _ = await _drive_close(None)
    closed = plane1.of(EventKind.CLOSED)[0]
    assert REALIZED_FIELD not in closed.fields
    assert "no TradeFactsBook" in closed.fields[STATUS_FIELD]
    assert "D3.281" in closed.fields[STATUS_FIELD]
    for value in closed.fields.values():
        assert value not in {"0", "0.0", "0.00"}, closed.fields


@pytest.mark.asyncio
async def test_a_FIGURELESS_ROW_is_REFUSED_BY_NAME_at_the_SCORER() -> None:
    """`MissingRealized` must fire and must NAME the key. This is the negative
    half of the end-to-end claim: the reader is reading THIS key."""
    plane1, _, _ = await _drive_close(None)
    assert _partition(plane1.rows) == (
        [],
        plane1.of(EventKind.PROTECTIVE_EXIT) + plane1.of(EventKind.CLOSED),
    ), "nothing carried a figure, by construction"
    rows = [_log_row(row) for row in plane1.rows]
    with pytest.raises(ema.MissingRealized) as caught:
        ema.realized_closes(rows)
    assert REALIZED_FIELD in str(caught.value)
    assert "realized_pnl" in str(caught.value)


@pytest.mark.asyncio
async def test_a_FACTS_BOOK_ANSWERING_FOR_THE_WRONG_SYMBOL_is_REFUSED() -> None:
    """§6.6:448 keys on the pair, so a mismatched symbol is a misattribution —
    and it would be an INVISIBLE one, because the figure would look fine."""
    plane1, _, _ = await _drive_close(_facts(symbol="NQU6"))
    closed = plane1.of(EventKind.CLOSED)[0]
    assert REALIZED_FIELD not in closed.fields
    assert "'NQU6'" in closed.fields[STATUS_FIELD]
    assert "misattribution" in closed.fields[STATUS_FIELD]


@pytest.mark.asyncio
async def test_a_MALFORMED_FACT_records_the_REFUSAL_and_does_NOT_STOP_THE_EXIT() -> (
    None
):
    """§14: the protective exit's booking is zero-wire and non-optional. A bad
    cost fact must not be able to stop the Limiter recording that a position
    closed — so the refusal's own text rides onto the row instead."""
    plane1, _, _ = await _drive_close(_facts(fees=float("nan")))
    closed = plane1.of(EventKind.CLOSED)[0]
    assert REALIZED_FIELD not in closed.fields
    assert closed.fields[STATUS_FIELD].startswith("refused: ")
    assert "exit.fees" in closed.fields[STATUS_FIELD]


# ==========================================================================
# THE ACCOUNT DELTA IS NOT THE FIGURE
# ==========================================================================


@pytest.mark.asyncio
async def test_TWO_TRADES_CLOSING_TOGETHER_get_TWO_ATTRIBUTED_FIGURES() -> None:
    """`ScoringSink.book_realized` carries ONE account-level delta for both
    closes. §6.6:448 needs one figure PER PAIR, and no arithmetic recovers two
    numbers from their sum — which is exactly why this arc wrote a second path
    rather than reusing that one."""
    book = RecordedTradeFacts()
    plane1 = Plane1Recorder()
    broker = Broker(
        positions=[
            Position(symbol="MESU6", net_qty=2, avg_price=5000.0),
            Position(symbol="MNQU6", net_qty=2, avg_price=5000.0),
        ],
        cash=20344.34,
    )
    broker.realize_on_flatten["MESU6"] = -103.88
    broker.realize_on_flatten["MNQU6"] = 116.12
    scoring = ScoringSink()
    executor = _executor(
        broker,
        picture=_book_with(
            _row("T-1", "MESU6", "strat-1"), _row("T-2", "MNQU6", "strat-2")
        ),
        plane1=plane1,
        facts=book,
        scoring=scoring,
    )
    executor.fire(
        FlattenTrigger.NET_LIQ_FLOOR,
        targets=[
            CloseTarget(trade_id="T-1", symbol="MESU6", strategy_id="strat-1"),
            CloseTarget(trade_id="T-2", symbol="MNQU6", strategy_id="strat-2"),
        ],
    )
    # The fills confirm, and only then can the book answer (§4).
    book.record(_facts(trade_id="T-1", symbol="MESU6", exit_price=4990.0))
    book.record(
        _facts(
            trade_id="T-2",
            symbol="MNQU6",
            strategy_id="strat-2",
            exit_price=5030.0,
            point_value=2.0,
        )
    )
    confirmed = await executor.reconcile_and_publish()

    carrying, deferred = _partition(plane1.rows)
    assert len(carrying) == 2 and len(deferred) == 2, plane1.rows
    figures = {
        row.fields[SYMBOL_FIELD]: float(row.fields[REALIZED_FIELD]) for row in carrying
    }
    assert set(figures) == {"MESU6", "MNQU6"}, figures
    assert figures["MESU6"] == pytest.approx(-103.88)
    assert figures["MNQU6"] == pytest.approx(116.12)
    # The account delta is their SUM and is attributable to NEITHER pair.
    assert confirmed.realized_delta == pytest.approx(12.24)
    assert scoring.booked[0][1] == pytest.approx(12.24)
    for value in figures.values():
        assert value != pytest.approx(confirmed.realized_delta)
    # And the scorer keys them apart.
    scored = ema.score_pairs(
        ema.realized_closes([_log_row(row) for row in _partition(plane1.rows)[0]]),
        10,
        DAY.date(),
    )
    assert set(scored) == {("strat-1", "MESU6"), ("strat-2", "MNQU6")}
    assert scored[("strat-1", "MESU6")].realized_ema < 0
    assert scored[("strat-2", "MNQU6")].realized_ema > 0


# ==========================================================================
# THE BOOK
# ==========================================================================


def test_the_FACTS_BOOK_answers_NONE_for_a_trade_it_has_never_seen() -> None:
    """`None` is a real answer — *no confirmed exit fill* — and the writer turns
    it into a named status rather than into a zero."""
    book = RecordedTradeFacts()
    assert book.facts_for("T-1") is None
    assert len(book) == 0
    book.record(_facts())
    assert len(book) == 1
    found = book.facts_for("T-1")
    assert found is not None
    assert found.trade_id == "T-1"
