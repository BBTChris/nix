"""
test_broker_order.py — adversarial test of the IBKR broker-order adapter.

The FakeIB below reproduces ib_async's real awkward behaviours, not a convenient
idealisation of them. Specifically it reproduces:

  - orderStatus re-emitted on EVERY change (so ack must be deduped)
  - rejections arriving on errorEvent, NOT orderStatus (so the streams must be joined)
  - duplicate execution reports (so (order_id, exec_id) dedupe must hold)
  - whatIfOrder returning an EMPTY OrderState (ARC 012's measured trap)
  - the 1.797e308 double-max sentinel for an unset margin field
  - connectivity codes 1100/1101/1102 with 1101 carrying data loss
  - orderIds resetting across a reconnect (Gateway's daily 03:00 restart)
  - connectAsync REPLAYING HISTORICAL EXECUTIONS (StartupFetch.EXECUTIONS) — ARC 015 §2b
  - contract multipliers, and Position.avgCost reported as COMMISSION-INCLUSIVE
    NOTIONAL while Execution.price is raw per-unit — ARC 015 §2d

A test suite that only exercises the happy path proves the adapter works when the
venue is polite. The venue is not polite.

ARC 015 §2d — WHY THE MULTIPLIER MATTERS HERE. ARC 014 found a real defect: the adapter
wrote IBKR's notional `Position.avgCost` straight into the per-unit `Position.avg_price`
field, so the same field carried two incompatible units depending on which event landed
last (a long 1 MES at 7782.50 reported 38912.50, exactly 5x). The offline suite could not
have caught it: `fut()` had no `multiplier`, so notional and per-unit were numerically
identical, and every mirror assertion checked only `net_qty`. The fake being unable to
REPRESENT a defect is its own debt, and it is paid here — the fake now carries real
multipliers and notional avgCost, the assertions read avg_price, and
`replanted_unit_bug_is_caught()` below re-plants the original defect and proves the
improved suite fails on it. A fake that could not catch the defect it was blind to is not
yet fixed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only —
# a blanket disable on a test file is how a suite stops being checked.
#
#   invalid-name
#       FakeIB MUST mirror ib_async's real surface: connectAsync, placeOrder,
#       reqPositionsAsync, orderStatusEvent, clientId, fetchFields. Renaming any
#       of them to snake_case would make the fake stop standing in for the thing
#       it fakes, and the adapter would no longer run against it. This is the one
#       file where camelCase is REQUIRED for correctness.
#   protected-access
#       The tests read ad._mirror, ad._from_ib, ib.orderStatusEvent._handlers and
#       call ad._on_ib_exec_details directly. That is deliberate: the position
#       mirror and the id map are internal STATE whose correctness is the thing
#       under test, and asserting on them is direct measurement rather than
#       inference from an output that might mask them (CLAUDE.md directive 2).
#   missing-function-docstring / missing-class-docstring
#       FakeIB's methods are named after the vendor calls they stand in for.
#   unused-argument
#       Fake vendor methods must accept the arguments the real ones take, whether
#       or not the fake uses them.
#   too-many-* / too-many-lines
#       An adversarial driver's size IS its coverage. It is already split into
#       named sections; collapsing assertions to satisfy a count would delete
#       tests, which is the opposite of the intent.
#   super-init-not-called
#       RacingIB copies the inner FakeIB's __dict__ on purpose — it must BE the
#       same fake mid-scenario, not a fresh one.
#   import-outside-toplevel
#       ib_async.ib is imported inside the one helper that reads StartupFetch.
#   duplicate-code
#       Section banner comments are intentionally identical.
# pylint: disable=invalid-name,protected-access,missing-function-docstring
# pylint: disable=missing-class-docstring,unused-argument,too-many-locals
# pylint: disable=too-many-statements,too-many-branches,too-many-arguments
# pylint: disable=too-many-positional-arguments,too-many-instance-attributes
# pylint: disable=too-many-lines,super-init-not-called,import-outside-toplevel
# pylint: disable=duplicate-code
import ast
import asyncio
import pathlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MethodType, SimpleNamespace

import pytest  # pylint: disable=import-error
from broker_order_ibkr import (
    IB_REJECT_EVIDENCE,
    IB_REJECT_RULES,
    IBKRBrokerOrder,
)
from broker_seam import (
    ORDER_PORT_VERBS,
    AckStatus,
    AwaitDivergentBrokerOrder,
    BrokerNotConnected,
    BrokerOrderPort,
    BrokerSeamError,
    NeutralOrder,
    OrderType,
    RecordingSink,
    RejectCategory,
    SessionState,
    Side,
    TimeInForce,
    ack_category_violation,
    check_await_conformance,
    check_structural_conformance,
)

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


class Event:
    """Minimal stand-in for ib_async's Event (+= to subscribe, call to emit)."""

    def __init__(self):
        self._handlers = []

    def __iadd__(self, fn):
        self._handlers.append(fn)
        return self

    def emit(self, *a):
        for h in list(self._handlers):
            h(*a)


# ARC 015 §2d: real CME multipliers. IBKR reports these as STRINGS on the contract
# ("5", "50"), which is why the adapter's normaliser parses rather than assumes.
MULTIPLIERS = {"MES": 5, "ES": 50, "MNQ": 2, "NQ": 20}


def multiplier_for(local_symbol: str) -> int:
    """Longest-prefix match, so MESU6 resolves to MES (5) and not ES (50)."""
    for root in sorted(MULTIPLIERS, key=len, reverse=True):
        if local_symbol.startswith(root):
            return MULTIPLIERS[root]
    return 1


def fut(local_symbol: str):
    """A futures contract with a REAL multiplier, as a string — as IBKR sends it.

    Before ARC 015 this had no `multiplier` at all, which made the adapter's
    notional-to-per-unit normalisation a no-op offline and hid a live 5x unit defect.
    """
    return SimpleNamespace(
        localSymbol=local_symbol,
        symbol=local_symbol[:3],
        conId=793356217,
        multiplier=str(multiplier_for(local_symbol)),
    )


def notional_avg_cost(
    local_symbol: str, price: float, commission: float = 0.0
) -> float:
    """IBKR's Position.avgCost for a future, as MEASURED live in ARC 014.

    Two separate frictions, both reproduced:
      1. NOTIONAL — avgCost is price x multiplier, while Execution.price is per-unit.
         Measured: a long 1 MESU6 at 7782.50 reported avgCost 38912.50, exactly 5x.
      2. COMMISSION-INCLUSIVE — avgCost bakes in the commission, Execution.price does
         not. Measured on the same fill: raw price 7773.500 vs avgCost/multiplier
         7773.622. The 0.122 gap is the 0.61 commission divided by the multiplier.

    So avg_price legitimately varies by PROVENANCE — by a fraction of a tick, not by 5x.
    Encoding the wrinkle here means the difference is representable, and a test can assert
    the residual is sub-tick instead of asserting an equality that is simply false.
    """
    return price * multiplier_for(local_symbol) + commission


@dataclass
class FakeIB:
    """Reproduces ib_async 2.1.0's real surface and its real misbehaviours."""

    next_order_id: int = 1
    connected: bool = False
    positions_to_return: list = field(default_factory=list)
    account_values: list = field(default_factory=list)
    whatif_result: object = None
    placed: list = field(default_factory=list)
    cancelled: list = field(default_factory=list)
    # ARC 015 §2b: what connectAsync's startup fetch replays before it returns.
    historical_executions: list = field(default_factory=list)
    historical_order_statuses: list = field(default_factory=list)
    last_fetch_fields: object = None
    connect_count: int = 0
    # ARC 017 A1(b): "the mirror was re-read" must be measured at the VENUE CALL, not
    # inferred from the mirror's contents — contents can be identical before and after
    # and prove nothing. This counter is the direct observable.
    reqpos_calls: int = 0
    reqpos_observer: Callable[[], None] | None = None
    """Called (no args) at the instant reqPositionsAsync is entered. Lets a test capture
    what the sink had ALREADY been told at the moment the venue was queried, which is how
    the 'rebuild precedes the session event' ORDERING is proven rather than assumed."""

    def __post_init__(self):
        self.orderStatusEvent = Event()
        self.execDetailsEvent = Event()
        self.errorEvent = Event()
        self.positionEvent = Event()
        self.accountValueEvent = Event()
        self.disconnectedEvent = Event()

    async def connectAsync(self, host, port, clientId, timeout=10, fetchFields=None):
        """Startup replay happens HERE — before connectAsync returns.

        ib_async's connectAsync awaits reqExecutions/reqAllOpenOrders as part of its
        startup fetch, and the venue's replies are dispatched on the ordinary
        execDetailsEvent/orderStatusEvent while that await is in progress. So a
        historical execution reaches the adapter's live fill handler at connect. That is
        the ARC 015 §2b hazard, and reproducing its TIMING is the whole point: replaying
        after connectAsync returned would test nothing, because the gate is open by then.
        """
        self.connected = True
        self.connect_count += 1
        self.last_fetch_fields = fetchFields
        # Gateway's daily 03:00 auto-restart resets the API order id sequence.
        self.next_order_id = 1
        await asyncio.sleep(0)  # the venue does not answer synchronously
        for trade, fill in self.historical_executions:
            self.execDetailsEvent.emit(trade, fill)
        for trade in self.historical_order_statuses:
            self.orderStatusEvent.emit(trade)

    def disconnect(self):
        self.connected = False

    def placeOrder(self, contract, order):
        order.orderId = self.next_order_id
        self.next_order_id += 1
        trade = SimpleNamespace(
            order=order,
            contract=contract,
            orderStatus=SimpleNamespace(
                status="PendingSubmit", filled=0, remaining=order.totalQuantity
            ),
        )
        self.placed.append((contract, order, trade))
        return trade

    def cancelOrder(self, order, manualCancelOrderTime=""):
        self.cancelled.append(order)

    async def reqPositionsAsync(self):
        self.reqpos_calls += 1
        if self.reqpos_observer is not None:
            self.reqpos_observer()
        await asyncio.sleep(0)  # the venue does not answer synchronously
        return self.positions_to_return

    async def accountSummaryAsync(self):
        return self.account_values

    async def whatIfOrderAsync(self, contract, order):
        if isinstance(self.whatif_result, Exception):
            raise self.whatif_result
        if self.whatif_result == "hang":
            await asyncio.sleep(10)
        return self.whatif_result

    # --- drivers used by tests to simulate venue pushes ---
    def push_status(self, trade, status, filled=0):
        trade.orderStatus.status = status
        trade.orderStatus.filled = filled
        self.orderStatusEvent.emit(trade)

    def make_fill(self, trade, exec_id, shares, price, cum, contract=None, side=None):
        return SimpleNamespace(
            contract=contract or trade.contract,
            execution=SimpleNamespace(
                execId=exec_id,
                orderId=trade.order.orderId,
                shares=shares,
                price=price,
                cumQty=cum,
                **({"side": side} if side else {}),
            ),
        )

    def push_exec(self, trade, exec_id, shares, price, cum, contract=None, side=None):
        self.execDetailsEvent.emit(
            trade, self.make_fill(trade, exec_id, shares, price, cum, contract, side)
        )

    def push_position(self, local_symbol, qty, price, commission=0.0):
        """positionEvent with avgCost as NOTIONAL, as IBKR sends it (ARC 015 §2d)."""
        self.positionEvent.emit(
            SimpleNamespace(
                contract=fut(local_symbol),
                position=qty,
                avgCost=notional_avg_cost(local_symbol, price, commission),
            )
        )

    def position_row(self, local_symbol, qty, price, commission=0.0):
        """A row as reqPositionsAsync returns it — same notional convention."""
        return SimpleNamespace(
            account="DUR250018",
            contract=fut(local_symbol),
            position=qty,
            avgCost=notional_avg_cost(local_symbol, price, commission),
        )

    def push_error(self, reqId, code, msg, contract=None):
        self.errorEvent.emit(reqId, code, msg, contract)


def resolver(symbol: str):
    return fut(symbol)


def new_adapter(**kw):
    sink = RecordingSink()
    ib = FakeIB()
    ad = IBKRBrokerOrder(sink, ib=ib, contract_resolver=resolver, client_id=905, **kw)
    return ad, ib, sink


# ---------------------------------------------------------------------------
# ARC 015 §2d — the avg_price assertions, isolated so they can be run TWICE:
# once against the real adapter (must pass) and once with the original unit bug
# re-planted (must fail). Same instrument, two subjects — the HollowBrokerOrder
# pattern applied to a defect instead of to an adapter.
# ---------------------------------------------------------------------------

MES_PRICE = 7773.50  # MEASURED live, ARC 014
MES_COMMISSION = 0.61  # MEASURED live, ARC 014
MES_AVG_FROM_COST = 7773.622  # MEASURED live: avgCost / multiplier
ES_PRICE = 5000.00
ES_COMMISSION = 2.20


async def avg_price_assertions() -> list[str]:
    """Returns failed assertion names. Empty == avg_price carries per-unit price.

    Every assertion here is one the pre-ARC-014 adapter FAILS, and one the pre-ARC-015
    fake could not have expressed — because without a multiplier on the contract,
    notional and per-unit are the same number.
    """
    failed: list[str] = []
    ad, ib, sink = new_adapter()
    await ad.connect()

    # --- positionEvent path: notional in, per-unit out -------------------------
    ib.push_position("MESU6", 1, MES_PRICE, MES_COMMISSION)
    mirrored = ad._mirror.get("MESU6")
    if mirrored is None:
        failed.append("positionEvent reaches the mirror at all")
    else:
        if abs(mirrored.avg_price - MES_AVG_FROM_COST) > 0.001:
            failed.append(
                f"mirror avg_price is per-unit ({mirrored.avg_price} != {MES_AVG_FROM_COST})"
            )
        # The unit defect's signature: 5x the real price. Named separately so a failure
        # report says WHICH way it is wrong.
        if (
            abs(
                mirrored.avg_price
                - notional_avg_cost("MESU6", MES_PRICE, MES_COMMISSION)
            )
            < 0.001
        ):
            failed.append("mirror avg_price is NOTIONAL — the ARC 014 unit defect")
        # Provenance residual must be sub-tick (MES tick = 0.25), not a factor of 5.
        if abs(mirrored.avg_price - MES_PRICE) >= 0.25:
            failed.append(
                f"avg_price within one tick of the raw execution price "
                f"(gap {abs(mirrored.avg_price - MES_PRICE)})"
            )

    if not sink.positions:
        failed.append("on_position emitted")
    elif abs(sink.positions[-1][2] - MES_AVG_FROM_COST) > 0.001:
        failed.append(f"on_position avg_price is per-unit ({sink.positions[-1][2]})")

    # --- a DIFFERENT multiplier, so a hardcoded 5 cannot pass ------------------
    ib.push_position("ESU6", -2, ES_PRICE, ES_COMMISSION)
    es = ad._mirror.get("ESU6")
    es_expected = notional_avg_cost("ESU6", ES_PRICE, ES_COMMISSION) / 50
    if es is None:
        failed.append("ES position reaches the mirror")
    elif abs(es.avg_price - es_expected) > 0.001:
        failed.append(f"ES avg_price normalised by ITS OWN multiplier ({es.avg_price})")

    # --- query_positions path: same field, same unit ---------------------------
    ib.positions_to_return = [ib.position_row("MESU6", 1, MES_PRICE, MES_COMMISSION)]
    returned = await ad.query_positions()
    if not returned:
        failed.append("query_positions returns the row")
    elif abs(returned[0].avg_price - MES_AVG_FROM_COST) > 0.001:
        failed.append(
            f"query_positions avg_price is per-unit ({returned[0].avg_price})"
        )

    # --- the fill path is already per-unit and must NOT be divided -------------
    ad.place_order(
        NeutralOrder("c-avg", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    t = ib.placed[-1][2]
    ib.push_exec(t, "e-avg-1", 1, MES_PRICE, 1, side="BOT")
    if not sink.fills:
        failed.append("fill emitted")
    elif abs(sink.fills[-1][4] - MES_PRICE) > 0.001:
        failed.append(
            f"Execution.price passes through RAW, undivided ({sink.fills[-1][4]})"
        )
    return failed


async def replanted_unit_bug_is_caught() -> tuple[bool, list[str]]:
    """Re-plant ARC 014's original defect and check the suite now catches it.

    The plant is the exact pre-fix code: write IBKR's notional avgCost straight into the
    per-unit avg_price field, no division by the multiplier. If avg_price_assertions()
    still comes back empty under this mutation, the suite is decorative and this returns
    False. Restored in `finally`, so a failure mid-way cannot leave the defect in place
    for the rest of the session.
    """
    original = IBKRBrokerOrder.__dict__["_avg_price_from_cost"]
    # Replacing a method on the class IS the experiment; the ignores are the specific
    # method-assign code, not a bare silencer. A mutation test that could not mutate
    # would be exactly the vacuity it exists to detect.
    IBKRBrokerOrder._avg_price_from_cost = staticmethod(  # type: ignore[method-assign]
        lambda contract, avg_cost: float(avg_cost)  # the ARC 014 defect, verbatim
    )
    try:
        caught = await avg_price_assertions()
    finally:
        IBKRBrokerOrder._avg_price_from_cost = original  # type: ignore[method-assign]
    return bool(caught), caught


async def _section_structural_and_await() -> None:
    """Shape and split conformance, plus the clientId=0 construction guard."""
    # ---------------------------------------------------------------- structural
    ad, _ib, _sink = new_adapter()
    record(
        "struct: adapter has every §2A order verb",
        not check_structural_conformance(ad, ORDER_PORT_VERBS),
    )
    record(
        "struct: capabilities names the unmet contract paths",
        len(ad.capabilities().unmet_contract_paths()) == 4,
        str(ad.capabilities().unmet_contract_paths()),
    )

    # ARC 015 Part 1: the adapter must sit on the side of the split the port declares.
    # structural conformance alone cannot see this — callable() is true for async def.
    await_bad = check_await_conformance(ad, BrokerOrderPort, ORDER_PORT_VERBS)
    record(
        "await: IBKR adapter matches the port's sync/async split",
        not await_bad,
        str(await_bad),
    )

    # NON-VACUITY for the line above. A gate that has never been seen to fail is
    # indistinguishable from one that cannot. AwaitDivergentBrokerOrder is the planted
    # divergence kept permanently rather than demonstrated once and deleted: exactly one
    # verb (query_positions) sits on the wrong side of the split, everything else
    # conforms. It is also STRUCTURALLY invisible, which is the reason
    # check_structural_conformance() is not sufficient on its own.
    divergent = AwaitDivergentBrokerOrder(RecordingSink())
    record(
        "await: the planted divergence passes STRUCTURAL conformance (shape hides it)",
        not check_structural_conformance(divergent, ORDER_PORT_VERBS),
    )
    diverged = check_await_conformance(divergent, BrokerOrderPort, ORDER_PORT_VERBS)
    record(
        "NON-VACUITY: check_await_conformance FAILS on the planted divergence",
        len(diverged) == 1,
        str(diverged),
    )
    record(
        "NON-VACUITY: it NAMES the offending verb and both sides of the disagreement",
        len(diverged) == 1
        and diverged[0].startswith("query_positions:")
        and "port declares async" in diverged[0]
        and "adapter is sync" in diverged[0],
        str(diverged),
    )

    # clientId 0 must be refused at construction
    try:
        IBKRBrokerOrder(RecordingSink(), ib=FakeIB(), client_id=0)
        record("guard: clientId=0 refused", False, "constructed without error")
    except ValueError:
        record("guard: clientId=0 refused", True)


async def _section_session_discipline() -> None:
    """Every verb must refuse without a session — sync and awaited alike."""
    # ---------------------------------------------------------------- session discipline
    cold, _, _ = new_adapter()
    o = NeutralOrder("c1", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    for verb, call in (
        ("place_order", lambda: cold.place_order(o)),
        ("cancel_order", lambda: cold.cancel_order("c1")),
        ("flatten", cold.flatten),
        ("query_order_status", lambda: cold.query_order_status("c1")),
    ):
        try:
            call()
            record(f"session: {verb} refuses when down", False, "no exception")
        except BrokerNotConnected:
            record(f"session: {verb} refuses when down", True)

    # The async verbs refuse too — and must be AWAITED to find out. Calling one without
    # awaiting raises nothing at all, which is exactly the failure mode the ARC 015 split
    # makes visible instead of silent.
    for verb, coro in (
        ("query_positions", cold.query_positions()),
        ("query_balance", cold.query_balance()),
        ("get_margin", cold.get_margin("MESU6")),
    ):
        try:
            await coro
            record(
                f"session: {verb} refuses when down (awaited)", False, "no exception"
            )
        except BrokerNotConnected:
            record(f"session: {verb} refuses when down (awaited)", True)


async def _section_order_lifecycle() -> None:
    """connect -> ack -> fills -> mirror -> flatten, on one adapter and one session."""
    # ---------------------------------------------------------------- connect
    ad, ib, sink = new_adapter()
    await ad.connect()
    record(
        "connect: emits on_session UP",
        bool(sink.sessions) and sink.sessions[-1][0] is SessionState.UP,
    )

    # ---------------------------------------------------------------- ack path
    ad.place_order(
        NeutralOrder("c-1", "MESU6", Side.BUY, 2, OrderType.MARKET, TimeInForce.DAY)
    )
    trade = ib.placed[-1][2]
    record("place_order: no ack before venue confirms", not sink.acks)

    ib.push_status(trade, "PreSubmitted")
    record(
        "ack: PreSubmitted produces exactly one ACCEPTED",
        len(sink.acks) == 1 and sink.acks[0][1] is AckStatus.ACCEPTED,
    )

    # IBKR re-emits orderStatus on every change — must NOT produce a second ack
    ib.push_status(trade, "Submitted")
    ib.push_status(trade, "Submitted")
    record(
        "ack: re-emitted orderStatus does NOT duplicate the ack",
        len(sink.acks) == 1,
        f"acks={len(sink.acks)}",
    )

    # ---------------------------------------------------------------- fills + idempotency
    ib.push_exec(trade, "0000e0d5.68a1b2c3.01.01", 1, 7785.0, 1)
    record("fill: emits on_fill", len(sink.fills) == 1)
    record("fill: cumulative_qty carried from Execution.cumQty", sink.fills[-1][5] == 1)

    # duplicate execution report — the real scenario §4 demands immunity to
    ib.push_exec(trade, "0000e0d5.68a1b2c3.01.01", 1, 7785.0, 1)
    record(
        "IDEMPOTENCY: duplicate (order_id, exec_id) emits nothing",
        len(sink.fills) == 1,
        f"fills={len(sink.fills)}",
    )

    # a genuinely distinct exec must still get through — dedupe is not a black hole
    ib.push_exec(trade, "0000e0d5.68a1b2c3.01.02", 1, 7785.5, 2)
    record(
        "IDEMPOTENCY: distinct exec still delivered",
        len(sink.fills) == 2,
        f"fills={len(sink.fills)}",
    )

    # ---------------------------------------------------------------- position mirror
    record("mirror: tracks net qty from fills", ad._mirror.get("MESU6").net_qty == 2)

    # ---------------------------------------------------------------- flatten (GAP-1)
    before = len(ib.placed)
    ad.flatten("MESU6")
    record(
        "flatten: fires an opposing order without querying the venue",
        len(ib.placed) == before + 1,
    )
    _flat_contract, flat_order, _ = ib.placed[-1]
    record(
        "flatten: opposing side (long 2 -> SELL 2)",
        flat_order.action == "SELL" and flat_order.totalQuantity == 2,
        f"{flat_order.action} {flat_order.totalQuantity}",
    )
    record("flatten: uses IOC market order", flat_order.tif == "IOC")

    # flatten on a symbol with no position must be a no-op, not an error or a phantom order
    before = len(ib.placed)
    ad.flatten("ZZZZ")
    record("flatten: no position -> no order, no exception", len(ib.placed) == before)


async def _section_rejection_paths() -> None:
    """Rejections arrive on errorEvent; informational codes are not rejections."""
    # ---------------------------------------------------------------- rejection path
    ad2, ib2, sink2 = new_adapter()
    await ad2.connect()
    ad2.place_order(
        NeutralOrder("c-rej", "ESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    t2 = ib2.placed[-1][2]
    # Real IBKR: rejection arrives on errorEvent, NOT orderStatus
    ib2.push_error(
        t2.order.orderId,
        201,
        "Order rejected - reason:YOUR ORDER IS NOT ACCEPTED. NET LIQ [20299.32] "
        "MUST EXCEED THE MARGIN REQ [35035.87]",
    )
    record(
        "reject: errorEvent produces a REJECTED ack (streams joined)",
        len(sink2.acks) == 1 and sink2.acks[0][1] is AckStatus.REJECTED,
    )
    record(
        "reject: reason carries the venue text", "35035.87" in (sink2.acks[0][2] or "")
    )

    # ARC 015 §2c guard against the OPPOSITE defect: a rejected order that then goes
    # Inactive must NOT have an ACCEPTED ack synthesised on top of its REJECTED one.
    ib2.push_status(t2, "Inactive")
    record(
        "ack: Inactive after a rejection does NOT synthesise an ACCEPTED ack",
        len(sink2.acks) == 1 and sink2.acks[0][1] is AckStatus.REJECTED,
        str(sink2.acks),
    )

    # ...and an order that goes straight to Inactive with no error at all gets NO ack,
    # because Inactive is terminal WITHOUT acceptance.
    ad2b, ib2b, sink2b = new_adapter()
    await ad2b.connect()
    ad2b.place_order(
        NeutralOrder("c-ina", "ESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    ib2b.push_status(ib2b.placed[-1][2], "Inactive")
    record(
        "ack: bare Inactive synthesises NOTHING (terminal without acceptance)",
        not sink2b.acks,
        str(sink2b.acks),
    )

    # informational codes must NOT be mistaken for rejections
    ad3, ib3, sink3 = new_adapter()
    await ad3.connect()
    ad3.place_order(
        NeutralOrder("c-info", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    t3 = ib3.placed[-1][2]
    ib3.push_error(t3.order.orderId, 2104, "Market data farm connection is OK:usfuture")
    ib3.push_error(t3.order.orderId, 2119, "Market data farm is connecting:usfuture")
    record("reject: informational codes (2104/2119) are NOT rejections", not sink3.acks)


# ---------------------------------------------------------------------------
# ARC 018 / D1.18 — the neutral rejection taxonomy.
# ---------------------------------------------------------------------------

# (errorCode, errorString, expected RejectCategory). Every row is either a code this
# system has MEASURED, or a deliberately-unmapped code whose only correct answer is
# UNKNOWN. Nothing here is a guess at what IBKR "probably" returns: the unmapped rows do
# not depend on their text being accurate, because the assertion on them is that the
# adapter declines to interpret them.
REJECT_CASES: tuple[tuple[int, str, RejectCategory], ...] = (
    # MEASURED, ARC 010/012 (see IB_REJECT_EVIDENCE[201]). The one mapped rejection this
    # system has ever observed, and the only row that proves the taxonomy is not
    # uniformly UNKNOWN.
    (
        201,
        (
            "Order rejected - reason:YOUR ORDER IS NOT ACCEPTED. NET LIQ [20299.32] "
            "MUST EXCEED THE MARGIN REQ [35035.87]"
        ),
        RejectCategory.INSUFFICIENT_MARGIN,
    ),
    # 201 is a WRAPPER code. A 201 whose text is not the measured money text must NOT
    # inherit INSUFFICIENT_MARGIN — that is the "unknown wearing a known's clothes"
    # failure, and it is the reason the rule carries substrings at all.
    (
        201,
        "Order rejected - reason:some other refusal entirely",
        RejectCategory.UNKNOWN,
    ),
    # Unmapped codes. No evidence exists for these on this system, so the taxonomy owes
    # them UNKNOWN and nothing else.
    (
        200,
        "No security definition has been found for the request",
        RejectCategory.UNKNOWN,
    ),
    (10147, "OrderId that needs to be cancelled is not found", RejectCategory.UNKNOWN),
    (999999, "a code that does not exist", RejectCategory.UNKNOWN),
)


def _reject_site() -> str:
    """Name the mapper's real location, DERIVED from the object — never typed.

    A can-fail demonstration is only useful if the failure names where to look, and a
    hand-typed path is a §7.4 anchor that rots the first time the function moves.
    """
    import inspect

    import broker_order_ibkr as adapter_mod

    fn = adapter_mod.ib_reject_category
    return (
        f"{inspect.getsourcefile(fn)}:{inspect.getsourcelines(fn)[1]} "
        f"{fn.__qualname__}() + IB_REJECT_RULES"
    )


def _call_emits_rejected(node: ast.AST) -> bool:
    """True if `node` is an ack emission carrying the literal `AckStatus.REJECTED`."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in ("on_ack", "_ack_once"):
        return False
    args = list(node.args) + [kw.value for kw in node.keywords]
    return any(isinstance(a, ast.Attribute) and a.attr == "REJECTED" for a in args)


def _rejection_sites_in(tree: ast.AST, filename: str) -> list[str]:
    """Enclosing function names in one parsed module that emit a REJECTED ack."""
    return [
        f"{filename}::{fn.name}"
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(_call_emits_rejected(n) for n in ast.walk(fn))
    ]


def _rejection_emission_sites() -> list[str]:
    """AST-scan scripts/broker/ for every call that emits a REJECTED ack.

    DERIVED, not restated. The taxonomy assertions below drive ONE rejection path, and a
    second path added later would be structurally invisible to them — the vacuous-control
    shape (debug.md §7.12) one level up: the test would keep passing while an untested
    rejection emitted no category at all. So the set of emission sites is recomputed from
    the source on every run and compared against what this suite claims to cover.

    NAMED GAP: it matches only calls that pass the literal `AckStatus.REJECTED`. A site
    that passes the status in a variable is invisible here. That is accepted rather than
    papered over — the alternative is dataflow analysis, and this catches the shape a new
    rejection path actually takes.
    """
    broker_dir = pathlib.Path(__file__).resolve().parent.parent / "broker"
    sites: list[str] = []
    for path in sorted(broker_dir.glob("*.py")):
        sites += _rejection_sites_in(
            ast.parse(path.read_text(encoding="utf-8")), path.name
        )
    return sorted(set(sites))


# The emission sites this suite drives. Compared against the AST scan above, so a new
# rejection path fails loudly here instead of shipping untested.
COVERED_REJECTION_SITES = ["broker_order_ibkr.py::_on_ib_error"]


def _structured_payload(status: AckStatus, category: RejectCategory | None) -> str:
    """Every STRUCTURED field of an ack, flattened to one string.

    Both the member NAME and the member VALUE, because a consumer can read either and
    invariant 2 has to hold for both spellings.
    """
    parts = [status.name, str(status.value), repr(status)]
    if category is not None:
        parts += [category.name, str(category.value), repr(category)]
    return "|".join(parts)


async def _drive_rejection(code: int, text: str):
    """Place one order, refuse it with (code, text), return the single ack tuple."""
    ad, ib, sink = new_adapter()
    await ad.connect()
    ad.place_order(
        NeutralOrder(
            f"c-rc-{code}", "ESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY
        )
    )
    ib.push_error(ib.placed[-1][2].order.orderId, code, text)
    return sink.acks


async def _section_reject_taxonomy() -> None:
    """ARC 018 / D1.18 — the refusal cause as structured, vendor-neutral state.

    What is being proved, in order: the mapping table cannot grow without evidence; the
    suite covers every rejection emission site in the tree; the taxonomy actually fires
    (non-vacuity); no IBKR spelling reaches any structured field (invariant 2, asserted
    mechanically); and the human channel still carries the venue code and its figures.
    """
    # ------------------------------------------------- the mapping table is evidence-gated
    unevidenced = [
        code
        for code, _needles, _cat in IB_REJECT_RULES
        if not IB_REJECT_EVIDENCE.get(code)
    ]
    record(
        "taxonomy: every mapped IBKR code carries a written evidence citation",
        not unevidenced,
        f"unevidenced codes={unevidenced} — a declaration is not evidence",
    )

    # ------------------------------------------------- coverage of every emission site
    found_sites = _rejection_emission_sites()
    record(
        "taxonomy: the suite covers EVERY REJECTED-ack emission site in scripts/broker/",
        found_sites == COVERED_REJECTION_SITES,
        f"found={found_sites} covered={COVERED_REJECTION_SITES} — a new rejection path "
        "must be driven here before it ships",
    )
    record(
        "taxonomy: NON-VACUITY — at least one emission site exists to cover",
        len(found_sites) >= 1,
        f"found={found_sites} (an empty scan would make the assertion above vacuous)",
    )

    # ------------------------------------------------- no digit in ANY member, ever
    digit_members = [
        m.name
        for m in RejectCategory
        if any(c.isdigit() for c in m.name) or any(c.isdigit() for c in str(m.value))
    ]
    record(
        "INVARIANT 2: no RejectCategory member name or value contains a digit",
        not digit_members,
        f"members carrying digits={digit_members} — a venue code in the taxonomy itself",
    )

    # ------------------------------------------------- drive every case
    observed: list[RejectCategory] = []
    for code, text, expected in REJECT_CASES:
        acks = await _drive_rejection(code, text)
        # The expectation is part of the label because code 201 appears TWICE with two
        # different correct answers — that pair is the whole point of the wrapper-code
        # argument, and two identically-named rows would hide which one moved.
        label = f"code {code} -> {expected.name}"

        # Reachability BEFORE any assertion about content — a taxonomy asserted on a path
        # that never fires is the vacuous control (§7.12).
        if len(acks) != 1:
            record(
                f"taxonomy ({label}): the rejection path is REACHABLE (exactly one ack)",
                False,
                f"acks={acks}",
            )
            continue
        record(
            f"taxonomy ({label}): the rejection path is REACHABLE (exactly one ack)",
            True,
        )

        _cid, status, reason, category = acks[0]
        observed.append(category)

        record(
            f"taxonomy ({label}): status is REJECTED",
            status is AckStatus.REJECTED,
            str(acks[0]),
        )
        record(
            f"taxonomy ({label}): category is {expected.name}, never a nearest match",
            category is expected,
            f"got={category} expected={expected} — see {_reject_site()}",
        )
        record(
            f"taxonomy ({label}): the (status, category) pairing is legal",
            ack_category_violation(status, category) == "",
            ack_category_violation(status, category),
        )

        # THE MECHANICAL INVARIANT-2 ASSERTION. Two independent forms: this venue's code
        # must not appear anywhere in the structured payload, AND the payload must contain
        # no digit at all — the second catches a code this case does not happen to drive.
        payload = _structured_payload(status, category)
        record(
            f"INVARIANT 2 ({label}): the venue code appears in NO structured field",
            str(code) not in payload,
            f"payload={payload!r}",
        )
        record(
            f"INVARIANT 2 ({label}): no structured field contains any digit",
            not any(c.isdigit() for c in payload),
            f"payload={payload!r}",
        )

        # ...and the human channel is UNCHANGED. `reason` deliberately still carries the
        # venue's code and text; the fix is that it is no longer the only carrier.
        record(
            f"taxonomy ({label}): `reason` still carries the venue code (human channel)",
            str(code) in (reason or ""),
            f"reason={reason!r}",
        )

    # Non-vacuity of the taxonomy ITSELF, and the can-fail target. A mapper collapsed to a
    # single category satisfies every per-case assertion that expects UNKNOWN; only this
    # one notices, so it is the one that has to name the site.
    distinct = set(observed)
    record(
        "NON-VACUITY: the taxonomy is not collapsed — >1 category observed, and at least "
        "one is a MAPPED category rather than UNKNOWN",
        len(distinct) > 1 and distinct - {RejectCategory.UNKNOWN} != set(),
        f"observed={sorted(c.name for c in distinct)} over {len(REJECT_CASES)} driven "
        f"rejections — SITE: {_reject_site()}",
    )
    record(
        "taxonomy: the evidenced 201 margin rejection maps to INSUFFICIENT_MARGIN — "
        f"SITE: {_reject_site()}",
        RejectCategory.INSUFFICIENT_MARGIN in distinct,
        f"observed={sorted(c.name for c in distinct)}",
    )

    # ------------------------------------------------- the ACCEPTED half of the pairing
    adA, ibA, sinkA = new_adapter()
    await adA.connect()
    adA.place_order(
        NeutralOrder("c-acc", "ESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    ibA.push_status(ibA.placed[-1][2], "PreSubmitted")
    record(
        "taxonomy: an ACCEPTED ack carries reject_category=None (the pairing, both ways)",
        len(sinkA.acks) == 1
        and sinkA.acks[0][1] is AckStatus.ACCEPTED
        and sinkA.acks[0][3] is None,
        str(sinkA.acks),
    )

    # ------------------------------------------------- UNKNOWN is the floor, never None
    adU, _ibU, sinkU = new_adapter()
    await adU.connect()
    adU._ack_once("c-floor", AckStatus.REJECTED)  # no category supplied at all
    record(
        "taxonomy: a REJECTED ack emitted with NO category is coerced to UNKNOWN, not None",
        len(sinkU.acks) == 1 and sinkU.acks[0][3] is RejectCategory.UNKNOWN,
        str(sinkU.acks),
    )
    record(
        "taxonomy: ack_category_violation CAN fail (REJECTED + None is named a violation)",
        ack_category_violation(AckStatus.REJECTED, None) != ""
        and ack_category_violation(AckStatus.ACCEPTED, RejectCategory.UNKNOWN) != ""
        and ack_category_violation(AckStatus.ACCEPTED, None) == "",
        "the pairing validator must reject both bad pairings and accept the good one",
    )


async def _section_connectivity() -> None:
    """ARC 017 A1 — 1100/1101/1102 as STRUCTURED state, and the 1101 self-reconciliation.

    The defect this section now measures: before ARC 017 both restores emitted plain
    `SessionState.UP` and differed only in the wording of `reason`, and the adapter did
    NOT re-read its mirror on a lossy restore — it emitted and returned. `flatten()` reads
    that mirror as ground truth with zero venue queries, so one reconnect with data loss
    made the protective path confidently wrong. Two properties are asserted:

      (a) the two restores are distinguishable WITHOUT READING `reason` at all
      (b) the lossy one re-reads the mirror, and does so BEFORE publishing the state
    """
    # ------------------------------------------------------------- 1100 / 1102 (no loss)
    ad4, ib4, sink4 = new_adapter()
    await ad4.connect()
    n0 = len(sink4.sessions)
    rebuilds_after_connect = ad4._mirror_rebuilds
    reqpos_after_connect = ib4.reqpos_calls

    ib4.push_error(-1, 1100, "Connectivity between IB and TWS has been lost")
    ib4.push_error(-1, 1102, "Connectivity restored - data maintained")
    await asyncio.sleep(0)  # give any scheduled work a chance to run — see 1101 below
    await asyncio.sleep(0)
    states = [s[0] for s in sink4.sessions[n0:]]
    reasons = [s[1] for s in sink4.sessions[n0:]]
    record("session: connection lost -> DOWN", states[0] is SessionState.DOWN)
    record("session: clean restore -> UP", states[1] is SessionState.UP)
    record(
        "A1(b): a CLEAN restore does NOT rebuild the mirror (the two stay asymmetric)",
        ad4._mirror_rebuilds == rebuilds_after_connect
        and ib4.reqpos_calls == reqpos_after_connect,
        f"rebuilds {rebuilds_after_connect}->{ad4._mirror_rebuilds} "
        f"reqpos {reqpos_after_connect}->{ib4.reqpos_calls}",
    )

    # ------------------------------------------------- 1101 (data loss) — NON-VACUITY
    # The mirror is populated with a position the venue will CONTRADICT before the data
    # loss is injected. Without this the rebuild would be empty -> empty and "the mirror
    # was re-read" would be unfalsifiable: every assertion below would hold for an adapter
    # that did nothing at all.
    adL, ibL, sinkL = new_adapter()
    await adL.connect()
    ibL.push_position("MESU6", 2, 7773.50)  # mirror now believes: long 2 MES
    record(
        "NON-VACUITY A1(b): mirror is POPULATED before the data loss is injected",
        adL._mirror.get("MESU6") is not None and adL._mirror["MESU6"].net_qty == 2,
        f"mirror={ {k: v.net_qty for k, v in adL._mirror.items()} }",
    )

    # The venue's truth is DIFFERENT from what the mirror holds — that difference is what
    # a real 1101 means (we were blind while it changed), and it is what makes a re-read
    # observable in the mirror's CONTENTS as well as in the call count.
    ibL.positions_to_return = [ibL.position_row("MNQU6", -1, 20000.00)]
    rebuilds_before = adL._mirror_rebuilds
    reqpos_before = ibL.reqpos_calls
    sessions_before = len(sinkL.sessions)

    # ORDERING INSTRUMENT: capture how many session events the sink had been given at the
    # instant the venue was queried. Proving "rebuild happened" is not the guarantee;
    # the guarantee is that no consumer ever sees the restore over a stale mirror.
    seen_at_venue_call: list[int] = []
    ibL.reqpos_observer = lambda: seen_at_venue_call.append(len(sinkL.sessions))

    ibL.push_error(-1, 1101, "Connectivity restored - data lost")

    record(
        "A1(b): the session event is NOT published synchronously with the data loss",
        len(sinkL.sessions) == sessions_before,
        f"sessions {sessions_before} -> {len(sinkL.sessions)}",
    )
    for _ in range(4):  # let the scheduled re-read run to completion
        await asyncio.sleep(0)

    record(
        "A1(b): data loss triggers a mirror rebuild — the venue was re-queried",
        adL._mirror_rebuilds == rebuilds_before + 1
        and ibL.reqpos_calls == reqpos_before + 1,
        f"rebuilds {rebuilds_before}->{adL._mirror_rebuilds} "
        f"reqpos {reqpos_before}->{ibL.reqpos_calls}",
    )
    record(
        "A1(b): the mirror was actually RE-READ — stale contents replaced by venue truth",
        "MESU6" not in adL._mirror
        and adL._mirror.get("MNQU6") is not None
        and adL._mirror["MNQU6"].net_qty == -1,
        f"mirror={ {k: v.net_qty for k, v in adL._mirror.items()} }",
    )
    record(
        "A1(b): the rebuild PRECEDES the session event — no consumer sees UP over a "
        "stale mirror",
        seen_at_venue_call == [sessions_before],
        f"session count at venue-call time={seen_at_venue_call}, "
        f"before={sessions_before}",
    )
    record(
        "A1(b): the mirror is no longer flagged stale once the re-read lands",
        adL._mirror_stale is False,
    )

    # ------------------------------------------------- (a) structured, not prose
    lossy = sinkL.sessions[-1]
    lossy_state, lossy_reason = lossy[0], lossy[1]
    clean_state = states[1]
    record(
        "A1(a): a lossy restore is DISTINGUISHABLE from a clean one without reading "
        "`reason` — the states are not equal",
        lossy_state is not clean_state,
        f"lossy={lossy_state} clean={clean_state}",
    )
    record(
        "A1(a): the fact is a readable FIELD — state.data_loss, no string parsing",
        lossy_state.data_loss is True and clean_state.data_loss is False,
        f"lossy.data_loss={lossy_state.data_loss} clean.data_loss={clean_state.data_loss}",
    )
    record(
        "A1(a): both restores still report a live session (state.is_up), so a lossy "
        "restore is not mistaken for a disconnect",
        lossy_state.is_up is True
        and clean_state.is_up is True
        and SessionState.DOWN.is_up is False,
    )
    record(
        "A1(a): an UNAWARE consumer's `is SessionState.UP` does NOT resume on a lossy "
        "restore (fails toward halted)",
        (lossy_state is SessionState.UP) is False,
        str(lossy_state),
    )
    # Invariant 2: the seam carries the MEANING, never the venue's spelling of it.
    all_session_reasons = [r for _, r in sinkL.sessions + sink4.sessions if r]
    record(
        "A1(a)/invariant 2: no IBKR error code crosses the seam in any session reason",
        not any(
            code in reason
            for reason in all_session_reasons
            for code in ("1100", "1101", "1102")
        ),
        str(all_session_reasons),
    )
    record(
        "A1(a): `reason` survives as human-readable colour, it is just no longer the "
        "carrier",
        bool(lossy_reason) and "1101" not in lossy_reason,
        f"reason={lossy_reason!r}",
    )
    record(
        "A1(a): the reasons of the two restores are still distinct prose (colour kept)",
        lossy_reason != reasons[1],
        f"lossy={lossy_reason!r} clean={reasons[1]!r}",
    )

    # ---- DEGRADED PATH 1: the venue refuses the re-read -----------------------------
    # A rebuild that fails must still publish, and must publish that it failed. Silence
    # here would leave the Limiter believing the session is simply down, and a plain
    # UP_DATA_LOSS would claim a re-read that did not happen.
    adF, ibF, sinkF = new_adapter()
    await adF.connect()
    ibF.push_position("MESU6", 2, 7773.50)

    async def _venue_refuses():
        raise BrokerSeamError("reqPositions refused")

    ibF.reqPositionsAsync = _venue_refuses
    sessions_before_f = len(sinkF.sessions)
    ibF.push_error(-1, 1101, "Connectivity restored - data lost")
    for _ in range(4):
        await asyncio.sleep(0)
    record(
        "A1(b) degraded: a FAILED re-read still publishes the data-loss state — the "
        "Limiter is never left uninformed",
        len(sinkF.sessions) == sessions_before_f + 1
        and sinkF.sessions[-1][0] is SessionState.UP_DATA_LOSS,
        str(sinkF.sessions[sessions_before_f:]),
    )
    record(
        "A1(b) degraded: the mirror stays FLAGGED stale when the re-read failed, and "
        "the reason says so — no false claim of reconciliation",
        adF._mirror_stale is True and "FAILED" in (sinkF.sessions[-1][1] or ""),
        f"stale={adF._mirror_stale} reason={sinkF.sessions[-1][1]!r}",
    )

    # ---- DEGRADED PATH 2: no event loop to schedule the re-read on -------------------
    # The bridge from a SYNC vendor callback to an async re-read is a scheduled task, so
    # the one thing that can remove it is having no loop. Forbidden alternatives
    # (asyncio.run / run_until_complete) are not available as a fallback — invariant 5 —
    # so the adapter must degrade LOUDLY rather than swallow the event.
    adN, ibN, sinkN = new_adapter()
    await adN.connect()
    sessions_before_n = len(sinkN.sessions)
    real_get_running_loop = asyncio.get_running_loop

    def _no_loop():
        raise RuntimeError("no running event loop")

    asyncio.get_running_loop = _no_loop
    try:
        ibN.push_error(-1, 1101, "Connectivity restored - data lost")
    finally:
        asyncio.get_running_loop = real_get_running_loop
    record(
        "A1(b) degraded: with NO event loop the data-loss state is still published "
        "SYNCHRONOUSLY — the event is never swallowed",
        len(sinkN.sessions) == sessions_before_n + 1
        and sinkN.sessions[-1][0] is SessionState.UP_DATA_LOSS,
        str(sinkN.sessions[sessions_before_n:]),
    )
    record(
        "A1(b) degraded: and it says the mirror could NOT be re-read, rather than "
        "claiming a reconciliation that never ran",
        "could NOT be re-read" in (sinkN.sessions[-1][1] or "")
        and adN._mirror_stale is True,
        f"stale={adN._mirror_stale} reason={sinkN.sessions[-1][1]!r}",
    )


async def _section_margin() -> None:
    """ARC 012's measured whatIfOrder traps, and the no-stale-fallback rule."""
    # ---------------------------------------------------------------- get_margin (ARC 012 trap)
    ad5, ib5, _ = new_adapter(margin_timeout_s=0.2)
    await ad5.connect()

    ib5.whatif_result = SimpleNamespace(initMarginChange="3503.59")
    m = await ad5.get_margin("MESU6")
    record("margin: real figure returned", abs(m - 3503.59) < 0.01, str(m))

    # ARC 012's measured trap: empty OrderState. Must raise, not return 0.
    ib5.whatif_result = SimpleNamespace(initMarginChange=None)
    try:
        await ad5.get_margin("MESU6")
        record(
            "margin: empty OrderState raises rather than returning 0",
            False,
            "returned quietly",
        )
    except BrokerSeamError as exc:
        record(
            "margin: empty OrderState raises rather than returning 0",
            "CANNOT MEASURE" in str(exc),
        )

    # IBKR's double-max sentinel must not be parsed as a number
    ib5.whatif_result = SimpleNamespace(initMarginChange="1.7976931348623157E308")
    try:
        await ad5.get_margin("MESU6")
        record("margin: double-max sentinel rejected", False, "parsed as a real number")
    except BrokerSeamError:
        record("margin: double-max sentinel rejected", True)

    # timeout must be CANNOT MEASURE, not zero
    ib5.whatif_result = "hang"
    try:
        await ad5.get_margin("MESU6")
        record("margin: timeout raises CANNOT MEASURE", False, "returned")
    except BrokerSeamError as exc:
        record("margin: timeout raises CANNOT MEASURE", "CANNOT MEASURE" in str(exc))

    # ARC 015 Part 3: retry is FORBIDDEN on the order path, and a CANNOT-MEASURE must
    # never be papered over with a previous figure. Assert the second call after a
    # successful one still raises rather than serving a cached value.
    ib5.whatif_result = SimpleNamespace(initMarginChange=None)
    try:
        await ad5.get_margin("MESU6")
        record(
            "margin: a prior success is NOT served as a fallback on a later failure",
            False,
            "returned a stale figure",
        )
    except BrokerSeamError:
        record(
            "margin: a prior success is NOT served as a fallback on a later failure",
            True,
        )


async def _section_balance() -> None:
    """GAP-2 provenance and tagged-string parsing."""
    # ---------------------------------------------------------------- balance provenance (GAP-2)
    ad6, ib6, _sink6 = new_adapter()
    ib6.account_values = [
        SimpleNamespace(tag="NetLiquidation", value="20344.34"),
        SimpleNamespace(tag="TotalCashValue", value="20344.34"),
        SimpleNamespace(tag="MaintMarginReq", value="0.00"),
        SimpleNamespace(tag="FullInitMarginReq", value="0.00"),
    ]
    await ad6.connect()
    bal = await ad6.query_balance()
    record("balance: parses tagged strings", abs(bal.net_liquidation - 20344.34) < 0.01)
    record(
        "GAP-2: balance flagged NOT venue-sourced (V27 honestly unmet)",
        bal.ts_is_venue_sourced is False,
    )

    # unparseable value must not crash the whole balance read
    ib6.account_values = [SimpleNamespace(tag="NetLiquidation", value="n/a")]
    bal2 = await ad6.query_balance()
    record(
        "balance: unparseable value degrades to 0, does not raise",
        bal2.net_liquidation == 0.0,
    )


async def _section_id_map_across_restart() -> None:
    """Gateway's 03:00 restart: id collision, map clearing, single event wiring."""
    # ---------------------------------------------------------------- id map across restart
    ad7, ib7, _sink7 = new_adapter()
    await ad7.connect()
    ad7.place_order(
        NeutralOrder("c-a", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    first_id = ib7.placed[-1][1].orderId
    ad7.disconnect()
    await ad7.connect()  # Gateway restarted; sequence resets to 1
    ad7.place_order(
        NeutralOrder("c-b", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    second_id = ib7.placed[-1][1].orderId
    record(
        "id map: venue ids collide across a Gateway restart (the hazard is real)",
        first_id == second_id,
        f"{first_id} == {second_id}",
    )
    record(
        "id map: adapter cleared the stale map on reconnect, so no cross-session mixup",
        ad7._from_ib.get(second_id) == "c-b",
        str(ad7._from_ib),
    )

    # ARC 015 §2b: ib_async's Event uses `+=`. Wiring once per connect() would leave two
    # copies of every handler after the 03:00 restart and three after the next. The
    # dedupe sets would hide the duplicate ack and the duplicate fill, so the only honest
    # observable is the handler count itself.
    record(
        "reconnect: event handlers registered exactly ONCE across two connects",
        len(ib7.orderStatusEvent._handlers) == 1
        and len(ib7.execDetailsEvent._handlers) == 1
        and len(ib7.positionEvent._handlers) == 1,
        f"status={len(ib7.orderStatusEvent._handlers)} "
        f"exec={len(ib7.execDetailsEvent._handlers)} "
        f"pos={len(ib7.positionEvent._handlers)}",
    )


async def _section_guards_and_isolation() -> None:
    """Duplicate client_order_id, and another clientId's order staying out."""
    # ---------------------------------------------------------------- duplicate cid
    ad8, _ib8, _ = new_adapter()
    await ad8.connect()
    dup = NeutralOrder("c-dup", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    ad8.place_order(dup)
    try:
        ad8.place_order(dup)
        record("guard: duplicate client_order_id refused", False, "accepted twice")
    except BrokerSeamError:
        record("guard: duplicate client_order_id refused", True)

    # ---------------------------------------------------------------- foreign order isolation
    ad9, ib9, sink9 = new_adapter()
    await ad9.connect()
    foreign = SimpleNamespace(
        order=SimpleNamespace(orderId=9999),
        contract=fut("MESU6"),
        orderStatus=SimpleNamespace(status="Submitted", filled=0, remaining=1),
    )
    ib9.push_status(foreign, "Submitted")
    ib9.push_exec(foreign, "foreign-exec-1", 1, 7785.0, 1)
    record(
        "isolation: another clientId's order produces no events on our sink",
        not sink9.acks and not sink9.fills,
    )


async def _section_defect_regressions() -> None:
    """D1-D4 from review, plus the no-auto-resend rule (ARC 015 Part 3)."""
    # ---------------------------------------------------------------- DEFECT REGRESSIONS
    # Each of these was written against a defect actually found in review. They fail on
    # the pre-fix adapter — that is what makes them worth having.

    # D1: flatten must not abandon remaining symbols when one fails (PROTECTIVE PATH)
    adA, ibA, _sinkA = new_adapter()
    await adA.connect()

    def partial_resolver(sym):
        if sym == "BADSYM":
            return None  # resolver returns nothing -> SymbolNotResolved
        return fut(sym)

    adA._resolve_contract = partial_resolver
    from broker_seam import Position as P

    adA._mirror = {
        "MESU6": P("MESU6", 2, 7785.0),
        "BADSYM": P("BADSYM", 1, 100.0),
        "MNQU6": P("MNQU6", -3, 20000.0),
    }
    placed_before = len(ibA.placed)
    msg = ""
    try:
        adA.flatten()
        raised = False
    except BrokerSeamError as exc:
        raised = True
        msg = str(exc)
    flattened_syms = [c.localSymbol for c, o, t in ibA.placed[placed_before:]]
    record(
        "D1: flatten continues past a failing symbol (2 of 3 still fired)",
        len(flattened_syms) == 2
        and "MESU6" in flattened_syms
        and "MNQU6" in flattened_syms,
        f"fired={flattened_syms}",
    )
    record(
        "D1: flatten raises afterwards naming the symbol it could NOT flatten",
        raised and "BADSYM" in msg,
        msg if raised else "did not raise",
    )

    # D2: direction must come from Execution.side, not from our own record
    adB, ibB, _sinkB = new_adapter()
    await adB.connect()
    adB.place_order(
        NeutralOrder("c-side", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    tB = ibB.placed[-1][2]
    # Venue reports a SELL execution against an order we recorded as BUY. The venue is
    # the authority on what actually happened.
    ibB.push_exec(tB, "e-side-1", 1, 7785.0, 1, contract=fut("MESU6"), side="SLD")
    record(
        "D2: mirror follows Execution.side (SLD -> short), not our BUY record",
        adB._mirror.get("MESU6").net_qty == -1,
        str(adB._mirror.get("MESU6")),
    )

    # D3: a fill landing during query_positions must not be erased
    adC, ibC, _sinkC = new_adapter()
    await adC.connect()
    adC.place_order(
        NeutralOrder("c-race", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    tC = ibC.placed[-1][2]

    class RacingIB(FakeIB):
        """reqPositionsAsync yields, and a fill lands during the yield."""

        def __init__(self, inner, trade):
            self.__dict__.update(inner.__dict__)
            self._trade = trade

        async def reqPositionsAsync(self):
            await asyncio.sleep(0)  # yield — this is the window
            adC._on_ib_exec_details(
                self._trade,
                SimpleNamespace(
                    contract=fut("MESU6"),
                    execution=SimpleNamespace(
                        execId="e-race-1",
                        orderId=self._trade.order.orderId,
                        shares=1,
                        price=7785.0,
                        cumQty=1,
                        side="BOT",
                    ),
                ),
            )
            return []  # venue snapshot says FLAT — stale by the time we read it

    adC._ib = RacingIB(ibC, tC)
    await adC.query_positions()
    record(
        "D3: fill during query_positions is NOT erased by the stale venue snapshot",
        adC._mirror.get("MESU6") is not None and adC._mirror["MESU6"].net_qty == 1,
        f"mirror={adC._mirror}",
    )

    # D4: a failed placement must not poison the duplicate-id guard
    adD, ibD, _sinkD = new_adapter()
    await adD.connect()
    adD._resolve_contract = fut

    def boom(contract, order):
        raise RuntimeError("venue refused the socket write")

    ibD.placeOrder = boom
    ordD = NeutralOrder(
        "c-retry", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY
    )
    try:
        adD.place_order(ordD)
    except RuntimeError:
        pass
    ibD.placeOrder = MethodType(FakeIB.placeOrder, ibD)  # restore
    try:
        adD.place_order(ordD)  # same id — legitimate retry after a failed write
        record("D4: failed placement rolls back, so the same id can be retried", True)
    except BrokerSeamError as exc:
        record(
            "D4: failed placement rolls back, so the same id can be retried",
            False,
            str(exc),
        )

    # ARC 015 Part 3: the rollback above is a ROLLBACK, not a resend. Nothing in the
    # adapter may re-submit on its own — §4 says a pending timeout is resolved by
    # querying status and the system NEVER auto-resends. One failed write must leave
    # exactly zero orders at the venue.
    record(
        "NO-RETRY: a failed placement leaves ZERO orders at the venue (no auto-resend)",
        len(ibD.placed) == 1,
        f"placed={len(ibD.placed)} (1 == only the explicit retry)",
    )


async def _section_zero_qty_positions() -> None:
    """ARC 015 §2a — zero-qty rows must not reach the returned list."""
    # ---------------------------------------------------------------- ARC 015 §2a
    # query_positions must not return zero-qty rows. IBKR emits a position=0 row after a
    # round trip; the mirror always filtered them, the returned list did not, so the two
    # disagreed about the same account. §4 makes this call cold-start GROUND TRUTH, and
    # `if await broker.query_positions(): halt()` is the natural caller idiom.
    adZ, ibZ, _sinkZ = new_adapter()
    await adZ.connect()
    ibZ.positions_to_return = [
        ibZ.position_row("MESU6", 0, 7773.50),  # round-tripped, now flat
        ibZ.position_row("MNQU6", -1, 20000.00),
    ]
    rows = await adZ.query_positions()
    record(
        "§2a: zero-qty rows filtered from the RETURNED list",
        all(p.net_qty != 0 for p in rows),
        str(rows),
    )
    record(
        "§2a: the real position still comes back (filter is not a black hole)",
        len(rows) == 1 and rows[0].symbol == "MNQU6",
        str(rows),
    )
    record(
        "§2a: returned list and mirror agree on the symbol set",
        {p.symbol for p in rows} == set(adZ._mirror),
        f"returned={sorted(p.symbol for p in rows)} mirror={sorted(adZ._mirror)}",
    )
    record(
        "§2a: a caller's truthiness test sees FLAT when the account is flat",
        not await _flat_account_rows(adZ, ibZ),
    )


async def _section_startup_replay() -> None:
    """ARC 015 §2b — historical executions at connect are ignored by design."""
    # ---------------------------------------------------------------- ARC 015 §2b
    # A historical execution delivered at connect must be ignored BY DESIGN. Built as a
    # RECONNECT so the id map from the previous session is exactly what the replayed
    # execution would have matched — the "dropped only because _from_ib happened to be
    # empty" accident, made unreachable.
    adH, ibH, sinkH = new_adapter()
    await adH.connect()
    adH.place_order(
        NeutralOrder("c-hist", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    tH = ibH.placed[-1][2]
    historical_id = tH.order.orderId
    adH.disconnect()

    # The venue will replay this at the next connect, under the SAME orderId the sequence
    # reissues after the Gateway's 03:00 restart.
    ibH.historical_executions = [
        (tH, ibH.make_fill(tH, "hist-exec-1", 1, 7000.0, 1, side="BOT"))
    ]
    ibH.historical_order_statuses = [tH]
    tH.orderStatus.status = "Filled"
    tH.orderStatus.filled = 1
    fills_before = len(sinkH.fills)
    acks_before = len(sinkH.acks)
    await adH.connect()
    record(
        "§2b: historical execution replayed at connect produces NO fill",
        len(sinkH.fills) == fills_before,
        f"before={fills_before} after={len(sinkH.fills)}",
    )
    record(
        "§2b: historical orderStatus replayed at connect produces NO ack",
        len(sinkH.acks) == acks_before,
        f"before={acks_before} after={len(sinkH.acks)}",
    )
    record(
        "§2b: it is ignored BY DESIGN — the id map would otherwise have matched",
        historical_id == 1 and ibH.connect_count == 2,
        f"historical_id={historical_id} connects={ibH.connect_count}",
    )
    fetch_ok, fetch_detail = _fetch_narrowed_to_positions_and_account(
        ibH.last_fetch_fields
    )
    record(
        "A2: connectAsync asked for POSITIONS+ACCOUNT_UPDATES+SUB_ACCOUNT_UPDATES only — "
        "EXECUTIONS, ORDERS_OPEN and ORDERS_COMPLETE all ABSENT (enum evaluated, not read)",
        fetch_ok,
        fetch_detail,
    )
    record(
        "§2b: the gate is OPEN again after connect (a real fill still lands)",
        await _live_fill_still_works(adH, ibH, sinkH),
    )

    # ...and it survives ANOTHER reconnect, because the gate is scoped to the call.
    adH.disconnect()
    ibH.historical_executions = [
        (tH, ibH.make_fill(tH, "hist-exec-2", 1, 7000.0, 1, side="BOT"))
    ]
    fills_before = len(sinkH.fills)
    await adH.connect()
    record(
        "§2b: still ignored on the SECOND reconnect (survives the 03:00 restart, twice)",
        len(sinkH.fills) == fills_before,
        f"before={fills_before} after={len(sinkH.fills)}",
    )


async def _section_startup_window() -> None:
    """ARC 017 A3 — the startup gate must be closed for the WHOLE rebuild interval.

    THE WINDOW, as the ARC 017 probe traced it on main @ 92f9f17:

        self._connected = True
        self._startup_complete = True      <- gate opened HERE
        await self._rebuild_mirror()       <- reqPositionsAsync: a real loop yield
        self._sink.on_session(UP)

    All three conditions a phantom fill needs held simultaneously across that await —
    session live, gate open, mirror not yet trustworthy — and there is no Lock, Semaphore
    or re-entrancy guard anywhere in the adapter. `_require_session` gates only on
    `_connected`, which is already True. So a `place_order` scheduled concurrently with
    connect() populates `_from_ib`, and because IBKR order ids RESET across sessions a
    replayed historical execution can carry an id that now MATCHES a live order — reaching
    `_ensure_acked` and `on_fill`.

    This section reproduces exactly that, by injecting at the instant the venue is
    queried, which is inside the rebuild await. The `reqpos_observer` hook is what makes
    the timing real rather than approximated: injecting before or after connect() would
    test nothing, because the gate's whole behaviour is defined by that interval.
    """
    adW, ibW, sinkW = new_adapter()
    probe: dict = {"ran": False}

    def inject_during_rebuild() -> None:
        """Runs synchronously at the top of reqPositionsAsync — i.e. INSIDE connect()'s
        _rebuild_mirror await."""
        if probe["ran"]:
            return  # only the connect-time rebuild, not later reconciliations
        probe["ran"] = True
        # A concurrently-scheduled place_order. This is what makes the replayed id match.
        adW.place_order(
            NeutralOrder(
                "c-window", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY
            )
        )
        t = ibW.placed[-1][2]
        probe["trade"] = t
        # The three conditions, recorded AT the moment of injection rather than inferred.
        probe["connected"] = adW._connected
        probe["gate_open"] = adW._startup_complete
        probe["id_matches"] = t.order.orderId in adW._from_ib
        ibW.push_exec(t, "e-window-1", 1, 7785.0, 1, side="BOT")
        ibW.push_status(t, "Filled", filled=1)

    ibW.reqpos_observer = inject_during_rebuild
    fills_before, acks_before = len(sinkW.fills), len(sinkW.acks)
    await adW.connect()
    ibW.reqpos_observer = None

    # ---- NON-VACUITY, before any claim that something was caught -------------------
    record(
        "NON-VACUITY A3: the injection actually RAN, inside the rebuild await",
        probe["ran"],
        "reqpos_observer never fired — nothing was ever injected",
    )
    record(
        "NON-VACUITY A3: the session was LIVE at injection time (place_order succeeded, "
        "so _require_session let it through)",
        probe.get("connected") is True,
    )
    record(
        "NON-VACUITY A3: the injected event MATCHED a live order id — it is not being "
        "dropped by the id map, which would prove nothing about the gate",
        probe.get("id_matches") is True,
        f"_from_ib={adW._from_ib}",
    )
    record(
        "A3: the gate was CLOSED during the rebuild (this is the fix)",
        probe.get("gate_open") is False,
        f"_startup_complete at injection time={probe.get('gate_open')}",
    )

    # ---- the property itself ------------------------------------------------------
    record(
        "A3: an execDetails injected DURING the mirror rebuild produces NO on_fill",
        len(sinkW.fills) == fills_before,
        f"fills {fills_before} -> {len(sinkW.fills)}: {sinkW.fills}",
    )
    record(
        "A3: it produces NO on_ack either — _ensure_acked is not reached",
        len(sinkW.acks) == acks_before,
        f"acks {acks_before} -> {len(sinkW.acks)}: {sinkW.acks}",
    )
    record(
        "A3: nothing at all escaped to the order path during connect()",
        [e for e in sinkW.sequence if e in ("on_ack", "on_fill", "on_cancel")] == [],
        str(sinkW.sequence),
    )

    # ---- the handler IS reachable in this harness ---------------------------------
    # §7.12's standing question: a test that passes because nothing was ever dispatched
    # measures nothing. The SAME handler, driven the SAME way on the SAME order, must
    # produce a fill once the gate has opened.
    t = probe["trade"]
    fills_before = len(sinkW.fills)
    ibW.push_exec(t, "e-window-2", 1, 7785.0, 1, side="BOT")
    record(
        "NON-VACUITY A3: the exec handler is REACHABLE — the same push after connect() "
        "DOES produce a fill",
        len(sinkW.fills) == fills_before + 1,
        f"fills {fills_before} -> {len(sinkW.fills)}",
    )
    record(
        "A3: the gate OPENS — connect() finished with it open, so real fills land",
        adW._startup_complete is True,
    )

    # ---- re-arming across a reconnect ---------------------------------------------
    adW.disconnect()
    record(
        "A3: the gate re-arms on disconnect (closed again before the next session)",
        adW._startup_complete is False,
    )
    probe2: dict = {"ran": False}

    def inject_on_reconnect() -> None:
        if probe2["ran"]:
            return
        probe2["ran"] = True
        adW.place_order(
            NeutralOrder(
                "c-window-2", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY
            )
        )
        t2 = ibW.placed[-1][2]
        probe2["gate_open"] = adW._startup_complete
        probe2["id_matches"] = t2.order.orderId in adW._from_ib
        ibW.push_exec(t2, "e-window-3", 1, 7785.0, 1, side="BOT")

    ibW.reqpos_observer = inject_on_reconnect
    fills_before, acks_before = len(sinkW.fills), len(sinkW.acks)
    await adW.connect()
    ibW.reqpos_observer = None
    record(
        "NON-VACUITY A3: the reconnect injection ran and matched a live id",
        probe2["ran"] and probe2.get("id_matches") is True,
    )
    record(
        "A3: the gate is closed across the rebuild ON RECONNECT too — no fill, no ack",
        len(sinkW.fills) == fills_before and len(sinkW.acks) == acks_before,
        f"fills {fills_before}->{len(sinkW.fills)} acks {acks_before}->{len(sinkW.acks)}",
    )


async def _section_ack_race() -> None:
    """ARC 015 §2c — the ack must precede the fill on PendingSubmit -> Filled."""
    # ---------------------------------------------------------------- ARC 015 §2c
    # The missing-ack race. A market order can go PendingSubmit -> Filled with neither
    # PreSubmitted nor Submitted ever emitted, so the ack-only-on-those-states rule
    # produced NO ack and the Limiter waited forever on an order that had already filled.
    # Both event orderings are driven, because IBKR does not guarantee which lands first.
    for label, order_first in (
        ("exec before status", True),
        ("status before exec", False),
    ):
        adR, ibR, sinkR = new_adapter()
        await adR.connect()
        adR.place_order(
            NeutralOrder(
                f"c-race-{int(order_first)}",
                "MESU6",
                Side.BUY,
                1,
                OrderType.MARKET,
                TimeInForce.DAY,
            )
        )
        tR = ibR.placed[-1][2]
        ibR.push_status(tR, "PendingSubmit")  # the ONLY pre-terminal state seen
        record(
            f"§2c ({label}): PendingSubmit alone still produces no ack", not sinkR.acks
        )
        if order_first:
            ibR.push_exec(tR, "e-race-1", 1, 7785.0, 1, side="BOT")
            ibR.push_status(tR, "Filled", filled=1)
        else:
            ibR.push_status(tR, "Filled", filled=1)
            ibR.push_exec(tR, "e-race-1", 1, 7785.0, 1, side="BOT")
        record(
            f"§2c ({label}): an ack IS raised for a PendingSubmit -> Filled order",
            len(sinkR.acks) == 1 and sinkR.acks[0][1] is AckStatus.ACCEPTED,
            str(sinkR.acks),
        )
        record(
            f"§2c ({label}): the ack PRECEDES the fill in arrival order",
            "on_ack" in sinkR.sequence
            and "on_fill" in sinkR.sequence
            and sinkR.sequence.index("on_ack") < sinkR.sequence.index("on_fill"),
            str(sinkR.sequence),
        )
        # Indexing guarded deliberately: with the synthesis removed there is NO ack, and
        # a bare sinkR.acks[0] turns the whole driver into one IndexError that names
        # nothing. Verified by re-running the suite against that exact mutation — a test
        # that aborts instead of reporting is a worse instrument than one that fails.
        record(
            f"§2c ({label}): the synthesised ack says so, so provenance is not lost",
            bool(sinkR.acks) and "synthesised" in (sinkR.acks[0][2] or ""),
            str(sinkR.acks),
        )
        record(
            f"§2c ({label}): exactly ONE ack — synthesis does not double up",
            sinkR.sequence.count("on_ack") == 1,
            str(sinkR.sequence),
        )

    # A cancel with no prior ack must also be preceded by one.
    adX, ibX, sinkX = new_adapter()
    await adX.connect()
    adX.place_order(
        NeutralOrder("c-cxl", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    tX = ibX.placed[-1][2]
    ibX.push_status(tX, "Cancelled", filled=0)
    # Filtered to the two order-path events: connect legitimately emits on_session first,
    # and the guarantee being asserted is the ack/cancel ORDER, not the whole stream.
    record(
        "§2c: a cancel with no prior ack synthesises the ack FIRST",
        [e for e in sinkX.sequence if e in ("on_ack", "on_cancel")]
        == ["on_ack", "on_cancel"],
        str(sinkX.sequence),
    )

    # And the normal path must be untouched: PreSubmitted then Filled = ONE real ack.
    adY, ibY, sinkY = new_adapter()
    await adY.connect()
    adY.place_order(
        NeutralOrder("c-norm", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    tY = ibY.placed[-1][2]
    ibY.push_status(tY, "PreSubmitted")
    ibY.push_exec(tY, "e-norm-1", 1, 7785.0, 1, side="BOT")
    ibY.push_status(tY, "Filled", filled=1)
    record(
        "§2c: the normal PreSubmitted -> Filled path still yields exactly one real ack",
        sinkY.sequence.count("on_ack") == 1
        and bool(sinkY.acks)
        and "synthesised" not in (sinkY.acks[0][2] or ""),
        str(sinkY.acks),
    )


async def _section_avg_price_fidelity() -> None:
    """ARC 015 §2d — per-unit avg_price, and the re-planted unit bug."""
    # ---------------------------------------------------------------- ARC 015 §2d
    # avg_price fidelity, then the re-planted defect. See the module docstring.
    avg_failures = await avg_price_assertions()
    record(
        "§2d: avg_price is per-unit on every path (mirror, on_position, query_positions)",
        not avg_failures,
        str(avg_failures),
    )

    caught, caught_detail = await replanted_unit_bug_is_caught()
    record(
        "NON-VACUITY §2d: the RE-PLANTED ARC 014 unit bug is CAUGHT by this suite",
        caught,
        f"caught {len(caught_detail)}: {caught_detail}",
    )
    record(
        "§2d: the plant was removed — assertions pass again afterwards",
        not await avg_price_assertions(),
    )


async def _report() -> None:
    """Print the result table; exit non-zero if anything failed."""
    # ---------------------------------------------------------------- report
    print("=" * 92)
    print("IBKR broker-order ADAPTER — ADVERSARIAL TEST")
    print("=" * 92)
    for name, ok, detail in results:
        print(f"  {'OK ' if ok else 'XX '}{name}")
        if detail and not ok or detail and "NON-VACUITY" in name:
            print(f"       -> {detail}")
    failed = [r for r in results if not r[1]]
    print("-" * 92)
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        sys.exit(1)


async def main() -> None:
    """Drive every section in order. Split out of one long linear driver in ARC
    015: the sections are independent (each builds its own adapter and sink) and the
    complexity ceiling was the prompt, but the readable win is that a failure now
    names the section it came from.
    """
    await _section_structural_and_await()
    await _section_session_discipline()
    await _section_order_lifecycle()
    await _section_rejection_paths()
    await _section_reject_taxonomy()
    await _section_connectivity()
    await _section_margin()
    await _section_balance()
    await _section_id_map_across_restart()
    await _section_guards_and_isolation()
    await _section_defect_regressions()
    await _section_zero_qty_positions()
    await _section_startup_replay()
    await _section_startup_window()
    await _section_ack_race()
    await _section_avg_price_fidelity()
    await _report()


async def _flat_account_rows(adapter, ib) -> list:
    """Every row zero-qty: the caller's `if await query_positions(): halt()` must see []."""
    ib.positions_to_return = [ib.position_row("MESU6", 0, 7773.50)]
    return await adapter.query_positions()


def _fetch_narrowed_to_positions_and_account(fetch_fields) -> tuple[bool, str]:
    """ARC 017 A2. Asserts the RESOLVED flag value, evaluated from ib_async's own enum —
    never by reading the adapter's source line, which would only prove the source says
    what it says.

    Returns (ok, detail). Three flags must be ABSENT (EXECUTIONS, ORDERS_OPEN,
    ORDERS_COMPLETE) and three PRESENT — asserting only absence would be satisfied by a
    fetch of nothing at all, which is the vacuous pass.
    """
    from ib_async.ib import StartupFetch  # pylint: disable=import-error

    if fetch_fields is None:
        return False, "connectAsync was called with fetchFields=None (vendor default)"
    banned = ("EXECUTIONS", "ORDERS_OPEN", "ORDERS_COMPLETE")
    wanted = ("POSITIONS", "ACCOUNT_UPDATES", "SUB_ACCOUNT_UPDATES")
    present = {m.name for m in StartupFetch if fetch_fields & m}
    ok = not (present & set(banned)) and set(wanted) <= present
    return (
        ok,
        f"resolved={sorted(present)} banned_present={sorted(present & set(banned))}",
    )


async def _live_fill_still_works(adapter, ib, sink) -> bool:
    """The gate must OPEN. A gate that never opens drops every real fill instead."""
    before = len(sink.fills)
    adapter.place_order(
        NeutralOrder("c-live", "MESU6", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    )
    t = ib.placed[-1][2]
    ib.push_exec(t, "e-live-1", 1, 7785.0, 1, side="BOT")
    return len(sink.fills) == before + 1


@pytest.mark.asyncio
async def test_ibkr_broker_order_adapter() -> None:
    """pytest entry point, added when this driver was landed into the project suite
    (ARC 014). The module was written as a standalone `python test_broker_order.py`
    driver; wrapping rather than restructuring keeps it runnable both ways.

    ARC 015: now an `async def` under pytest-asyncio rather than a sync test calling
    asyncio.run(). The adapter's port is half coroutines, so the test that exercises it
    belongs on the event loop the same way its caller will be — and pytest-asyncio is the
    industry-standard way to say so. main() still calls sys.exit(1) on failure, so
    SystemExit is caught and the assertion is made against `results`; that way pytest
    reports WHICH assertions failed rather than just a non-zero exit."""
    results.clear()
    try:
        await main()
    except SystemExit:
        pass
    failed = [(n, d) for n, ok, d in results if not ok]
    assert not failed, "adapter assertions failed:\n" + "\n".join(
        f"  {n} -> {d}" for n, d in failed
    )
    assert len(results) > 30, (
        f"suite collapsed to {len(results)} assertions — non-vacuity"
    )


if __name__ == "__main__":
    asyncio.run(main())
