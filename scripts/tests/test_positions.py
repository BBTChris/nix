"""ARC 033 / 0.2 — the origin write: the row a confirmed fill first publishes.

Drives `scripts/nixrisk/positions.py` against the SHIPPED `FinancialPictureBook`,
`ExecutionLedger` and `StopBook`. Nothing here is a double for the modules whose
property is under test: the whole claim is that the published `stop_distance` is
the stop book's own figure, and a fake stop book would make that claim about the
fake.

**The two properties no ordinary drive would separate, and how they are:**

* `trade_id == client_order_id` under the DEFAULT binding, so a writer that
  hard-coded the identity produces byte-identical rows. Every join assertion here
  is therefore driven under a NON-IDENTITY mint as well, where the two ids
  differ and a hard-coded identity would publish the wrong key.
* Every trade could share one stop distance, so a wrong join would be invisible.
  The distances are pairwise DISTINCT and the test asserts they are before it
  trusts any comparison.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# suite by requirement.

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk import positions as mod  # pylint: disable=wrong-import-position
from nixrisk.execution import (  # pylint: disable=wrong-import-position
    ExecutionLedger,
    ExecutionReport,
    FillSide,
)
from nixrisk.picture import (  # pylint: disable=wrong-import-position
    FinancialPictureBook,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.stops import StopBook  # pylint: disable=wrong-import-position

TICKS = {"ESZ6": 0.25, "NQZ6": 0.25, "CLZ6": 0.01}
MARGIN = {"ESZ6": 500.0, "NQZ6": 1000.0, "CLZ6": 1700.0}
BALANCE = 100_000.0

#: `(client_order_id, strategy_id, symbol, side, qty, stop_ticks, fill_price)`.
#: The stop distances are PAIRWISE DISTINCT on purpose — see the module
#: docstring — and deliberately unequal to the quantities, so a writer that
#: published `size` where the distance belongs is visible too.
ORDERS: tuple[tuple[str, str, str, Side, int, int, float], ...] = (
    ("CO-1", "strat-es", "ESZ6", Side.LONG, 2, 13, 5000.00),
    ("CO-2", "strat-nq", "NQZ6", Side.SHORT, 3, 27, 18000.00),
    ("CO-3", "strat-cl", "CLZ6", Side.LONG, 1, 41, 70.00),
)


def _order(row: tuple[str, str, str, Side, int, int, float]) -> ProposedOrder:
    coid, strategy, symbol, side, qty, stop_ticks, _price = row
    return ProposedOrder(
        client_order_id=coid,
        strategy_id=strategy,
        symbol=symbol,
        side=side,
        qty=qty,
        margin_per_contract=MARGIN[symbol],
        stop_ticks=stop_ticks,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


def _fill(
    row: tuple[str, str, str, Side, int, int, float],
    *,
    exec_id: str = "x1",
    qty: int | None = None,
    cumulative: int | None = None,
    ts: float = 1001.0,
) -> ExecutionReport:
    coid, _strategy, symbol, side, order_qty, _stop, price = row
    filled = order_qty if qty is None else qty
    return ExecutionReport(
        order_id=coid,
        exec_id=exec_id,
        symbol=symbol,
        side=FillSide.BUY if side is Side.LONG else FillSide.SELL,
        filled_qty=filled,
        price=price,
        cumulative_qty=filled if cumulative is None else cumulative,
        ts=ts,
    )


class Rig:
    """The four real collaborators plus the writer, assembled as production would."""

    def __init__(self, *, mint: mod.TradeIdMint = mod.identity_trade_id) -> None:
        self.book = FinancialPictureBook(
            balance=BALANCE, deployable_fraction=0.70, margin_per_contract=MARGIN
        )
        self.ledger = ExecutionLedger()
        self.stops = StopBook(TICKS)
        self.origins = mod.EntryOrderOrigins(mint=mint)
        self.writer = mod.PositionOriginWriter(
            picture=self.book,
            ledger=self.ledger,
            stops=self.stops,
            origins=self.origins,
        )

    def approve(self, row: tuple[str, str, str, Side, int, int, float]) -> None:
        """Approval: the join is recorded. The Allocator/Limiter's motion."""
        self.origins.record(_order(row))

    def arm(self, row: tuple[str, str, str, Side, int, int, float]) -> None:
        """Confirmed fill: the stop is armed by the stop book (§4), not by us."""
        self.stops.arm(row[6], _order(row))


@pytest.fixture
def rig() -> Rig:
    """A fresh writer over fresh collaborators, under the DEFAULT binding."""
    return Rig()


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the fixture itself must discriminate
# --------------------------------------------------------------------------


def test_the_DRIVE_STOP_DISTANCES_are_PAIRWISE_DISTINCT_or_a_wrong_join_hides() -> None:
    """A shared distance makes a wrong join publish the right number by luck."""
    distances = [row[5] for row in ORDERS]

    assert len(set(distances)) == len(distances), distances
    assert all(distance > 0 for distance in distances)
    # ... and distinct from the quantities, so `size` published as the distance
    # would not coincidentally agree either.
    assert not set(distances) & {row[4] for row in ORDERS}


# --------------------------------------------------------------------------
# THE PROPERTY — the published figure IS the stop book's
# --------------------------------------------------------------------------


def test_the_PUBLISHED_stop_distance_IS_THE_STOP_BOOKS_for_that_trade(rig: Rig) -> None:
    """Per trade, published `stop_distance` == `initial_distance_ticks`."""
    for row in ORDERS:
        rig.approve(row)
        rig.arm(row)
        rig.writer.on_fill(_fill(row))

    published = {row.trade_id: row for row in rig.book.current().positions}
    assert len(published) == len(ORDERS)
    for coid, _strategy, _symbol, _side, _qty, stop_ticks, _price in ORDERS:
        origin = rig.origins.origin_for_order(coid)
        assert origin is not None
        armed = rig.stops.get(coid)
        assert armed is not None
        # Three independent statements of one number: the order's own
        # `stop_ticks`, the stop book's `initial_distance_ticks`, and the
        # published row. The first is what the sizer sized against (§7:476).
        assert armed.initial_distance_ticks == stop_ticks
        assert published[origin.trade_id].stop_distance == stop_ticks


def test_a_WRONG_ROW_would_be_VISIBLE_because_the_distances_DISAGREE(rig: Rig) -> None:
    """The comparison discriminates: no two trades share a distance."""
    for row in ORDERS:
        rig.approve(row)
        rig.arm(row)
        rig.writer.on_fill(_fill(row))

    by_trade = {row.trade_id: row.stop_distance for row in rig.book.current().positions}

    assert len(set(by_trade.values())) == len(by_trade)


def test_the_ROW_RIDES_THE_SAME_SNAPSHOT_as_balance_under_ONE_version(rig: Rig) -> None:
    """§3's atomicity rule: one writer, one version stamp, one commit."""
    row = ORDERS[0]
    rig.approve(row)
    rig.arm(row)
    before = rig.book.current().version

    write = rig.writer.on_fill(_fill(row))

    assert write.published
    assert write.picture.version == before + 1
    assert write.picture is rig.book.current()
    assert write.picture.balance == BALANCE
    assert write.row in write.picture.positions
    # The margin aggregate advanced in the SAME snapshot, which is what makes
    # this a commit rather than a second table.
    assert write.picture.sum_open_margin == pytest.approx(row[4] * MARGIN[row[2]])


def test_the_ROW_carries_the_STATE_and_the_SIGNED_SIZE_the_fill_implies(
    rig: Rig,
) -> None:
    """§4: OPEN is asserted only on fill confirmation; a SHORT signs negative."""
    long_row, short_row = ORDERS[0], ORDERS[1]
    for row in (long_row, short_row):
        rig.approve(row)
        rig.arm(row)
        rig.writer.on_fill(_fill(row))

    rows = {row.trade_id: row for row in rig.book.current().positions}

    assert rows["CO-1"].state is PositionState.OPEN
    assert rows["CO-1"].size == long_row[4]
    assert rows["CO-2"].size == -short_row[4]
    assert rows["CO-2"].margin == pytest.approx(short_row[4] * MARGIN[short_row[2]])


# --------------------------------------------------------------------------
# THE JOIN — a named default, never an identity
# --------------------------------------------------------------------------


def test_a_NON_IDENTITY_MINT_is_HONOURED_end_to_end() -> None:
    """The published key follows the INJECTED policy, not the order id.

    Under the default binding the two are equal, so a writer that hard-coded
    `trade_id = client_order_id` produces byte-identical rows and no drive over
    the default can tell them apart. This one can.
    """
    rig = Rig(mint=lambda order: f"T-{order.client_order_id}-{order.symbol}")
    for row in ORDERS:
        rig.approve(row)
        rig.arm(row)
        rig.writer.on_fill(_fill(row))

    published = {row.trade_id for row in rig.book.current().positions}

    assert published == {f"T-{row[0]}-{row[2]}" for row in ORDERS}
    assert not published & {row[0] for row in ORDERS}
    # The join is still navigable in BOTH directions after the mint changed.
    origin = rig.origins.origin_for_trade("T-CO-1-ESZ6")
    assert origin is not None and origin.client_order_id == "CO-1"


def test_the_DEFAULT_BINDING_is_the_ENTRY_ORDER_and_says_so() -> None:
    """`identity_trade_id` is the documented default, applied by construction."""
    origins = mod.EntryOrderOrigins()

    origin = origins.record(_order(ORDERS[0]))

    assert origin.trade_id == ORDERS[0][0] == origin.client_order_id
    assert origin.strategy_id == ORDERS[0][1]
    assert "DEFAULT BINDING" in (mod.identity_trade_id.__doc__ or "")


def test_a_COLLIDING_MINT_is_REFUSED_naming_BOTH_orders() -> None:
    """§3 keys the table BY trade_id; two orders under one key is not keyed."""
    origins = mod.EntryOrderOrigins(mint=lambda order: "T-CONSTANT")
    origins.record(_order(ORDERS[0]))

    with pytest.raises(mod.DuplicateOrigin) as caught:
        origins.record(_order(ORDERS[1]))

    message = str(caught.value)
    assert "T-CONSTANT" in message
    assert ORDERS[0][0] in message and ORDERS[1][0] in message


def test_RE_RECORDING_ONE_ORDER_is_REFUSED_naming_the_live_trade() -> None:
    """§4 mints a trade_id ONCE at open; a second record re-keys a live trade."""
    origins = mod.EntryOrderOrigins()
    origins.record(_order(ORDERS[0]))

    with pytest.raises(mod.DuplicateOrigin) as caught:
        origins.record(_order(ORDERS[0]))

    assert "already opened trade" in str(caught.value)


def test_a_MINT_returning_a_BLANK_KEY_is_REFUSED() -> None:
    """A blank trade_id collides every row in a table keyed by it."""
    origins = mod.EntryOrderOrigins(mint=lambda order: "")

    with pytest.raises(mod.DuplicateOrigin) as caught:
        origins.record(_order(ORDERS[0]))

    assert "not a usable trade_id" in str(caught.value)


def test_EntryOrderOrigins_SATISFIES_the_declared_seam_PORT() -> None:
    """The port is the surface; conformance is measured, not asserted in prose."""
    from nixrisk.seam import TradeOriginPort  # pylint: disable=import-outside-toplevel

    assert isinstance(mod.EntryOrderOrigins(), TradeOriginPort)


def test_the_SHIPPED_StopBook_SATISFIES_the_lookup_PORT() -> None:
    """`StopBook.get` is the read-only surface this writer consumes, unchanged."""
    assert isinstance(StopBook(TICKS), mod.StopLookupPort)


# --------------------------------------------------------------------------
# FAIL CLOSED — the refusals, each asserting its REASON
# --------------------------------------------------------------------------


def test_a_FILL_WITH_NO_ARMED_STOP_PUBLISHES_NOTHING_and_says_why(rig: Rig) -> None:
    """The D3.136 fail-open, refused: no defaulted distance, no zero, no row."""
    row = ORDERS[0]
    rig.approve(row)  # approved and filled, but the stop was never armed
    before = rig.book.current()

    with pytest.raises(mod.UnstoppedFill) as caught:
        rig.writer.on_fill(_fill(row))

    message = str(caught.value)
    assert "NO ARMED STOP" in message
    assert row[0] in message and "trade" in message
    assert "zero dollar risk" in message and "ADMIT MORE" in message
    # Nothing published, and the version did not move: a refusal is not a commit.
    after = rig.book.current()
    assert after is before and after.positions == ()
    assert rig.writer.refusals == 1 and rig.writer.writes == 0


def test_the_REFUSED_FILL_is_STILL_BOOKED_in_the_ledger_and_RECORDED(rig: Rig) -> None:
    """§4: the fill is a fact the system reports, never a negotiation."""
    row = ORDERS[0]
    rig.approve(row)

    with pytest.raises(mod.UnstoppedFill):
        rig.writer.on_fill(_fill(row))

    assert rig.ledger.position(row[2]).net_qty == row[4]
    recorded = rig.writer.unstopped()
    assert len(recorded) == 1
    assert recorded[0].client_order_id == row[0]
    assert recorded[0].trade_id == row[0]
    assert recorded[0].filled_qty == row[4]


def test_a_FILL_FOR_AN_UNRECORDED_ORDER_is_REFUSED_naming_the_join(rig: Rig) -> None:
    """No origin ⇒ no key. Refused rather than minting one at the fill."""
    row = ORDERS[0]
    rig.arm(row)

    with pytest.raises(mod.UnknownTrade) as caught:
        rig.writer.on_fill(_fill(row))

    message = str(caught.value)
    assert "TradeOrigin" in message and row[0] in message
    assert rig.book.current().positions == ()


def test_a_SYMBOL_ABSENT_FROM_THE_MARGIN_SET_is_REFUSED_as_NOT_TRADABLE() -> None:
    """§4:198 — a guessed margin figure enters `committed`."""
    rig = Rig()
    rig.book = FinancialPictureBook(
        balance=BALANCE, deployable_fraction=0.70, margin_per_contract={"NQZ6": 1000.0}
    )
    rig.writer = mod.PositionOriginWriter(
        picture=rig.book, ledger=rig.ledger, stops=rig.stops, origins=rig.origins
    )
    row = ORDERS[0]
    rig.approve(row)
    rig.arm(row)

    with pytest.raises(mod.UntradableSymbol) as caught:
        rig.writer.on_fill(_fill(row))

    assert "NOT-TRADABLE" in str(caught.value)
    assert row[2] in str(caught.value)


# --------------------------------------------------------------------------
# DOCTRINE C.9 — position comes from the LEDGER, never re-derived here
# --------------------------------------------------------------------------


def test_TWO_PARTIAL_FILLS_produce_ONE_ROW_carrying_the_CUMULATIVE_size(
    rig: Rig,
) -> None:
    """§4's partial-fill rule: position = actual filled qty, from §4's ledger."""
    row = ("CO-1", "strat-es", "ESZ6", Side.LONG, 5, 13, 5000.00)
    rig.approve(row)
    rig.arm(row)

    first = rig.writer.on_fill(_fill(row, exec_id="p1", qty=2, cumulative=2))
    second = rig.writer.on_fill(_fill(row, exec_id="p2", qty=3, cumulative=5))

    assert first.row.size == 2
    assert second.row.size == 5
    published = rig.book.current().positions
    assert len(published) == 1  # ONE row: §3's table is keyed by trade_id
    assert published[0].size == 5
    assert published[0].stop_distance == row[5]
    assert published[0].margin == pytest.approx(5 * MARGIN[row[2]])


def test_a_RE_DELIVERED_FILL_DOES_NOT_MOVE_THE_PUBLISHED_TABLE(rig: Rig) -> None:
    """§4 makes a re-delivery idempotent; a version bump would be a real change."""
    row = ORDERS[0]
    rig.approve(row)
    rig.arm(row)
    report = _fill(row)
    rig.writer.on_fill(report)
    after_first = rig.book.current()

    write = rig.writer.on_fill(report)

    assert write.disposition is mod.WriteDisposition.DUPLICATE
    assert rig.book.current() is after_first
    assert rig.book.current().version == after_first.version
    assert len(rig.book.current().positions) == 1
    assert rig.writer.writes == 1 and rig.writer.duplicates == 1


def test_SUM_RESERVATIONS_is_a_PASS_THROUGH_landing_under_ONE_version(
    rig: Rig,
) -> None:
    """§3's lifecycle releases ON FILL; the release rides the same commit."""
    row = ORDERS[0]
    rig.approve(row)
    rig.arm(row)
    rig.book.commit(sum_reservations=row[4] * MARGIN[row[2]])
    before = rig.book.current()
    assert before.sum_reservations > 0

    write = rig.writer.on_fill(_fill(row), sum_reservations=0.0)

    assert write.picture.sum_reservations == 0.0
    assert write.picture.sum_open_margin == pytest.approx(row[4] * MARGIN[row[2]])
    assert write.picture.version == before.version + 1


def test_LEFT_ALONE_the_RESERVATION_FIGURE_CARRIES_FORWARD_conservatively(
    rig: Rig,
) -> None:
    """The documented residual, driven so it is a measured fact, not a claim."""
    row = ORDERS[0]
    rig.approve(row)
    rig.arm(row)
    reserved = row[4] * MARGIN[row[2]]
    rig.book.commit(sum_reservations=reserved)

    write = rig.writer.on_fill(_fill(row))

    # Both terms present: `committed` DOUBLE-COUNTS the filled portion, which
    # errs toward LESS deployable capital. Conservative, still wrong, owed.
    assert write.picture.sum_reservations == pytest.approx(reserved)
    assert write.picture.committed == pytest.approx(2 * reserved)


# --------------------------------------------------------------------------
# WHAT THIS MODULE MUST NOT DO
# --------------------------------------------------------------------------


def test_the_WRITER_NEVER_ARMS_A_STOP_so_the_two_sides_stay_INDEPENDENT() -> None:
    """A writer that armed would compare a figure against one it produced.

    Read structurally rather than by substring: the module's own prose NAMES
    `StopBook` (it has to — it says why it declares a narrower port instead),
    and a grep over the whole file would be answered by the docstring.
    """
    import ast  # pylint: disable=import-outside-toplevel

    tree = ast.parse(
        (REPO / "scripts/nixrisk/positions.py").read_text(encoding="utf-8")
    )
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "nixrisk.stops" not in imported
    assert "arm" not in called
