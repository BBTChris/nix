"""
broker_seam.py — PROTOTYPE of the vendor-neutral broker seam (nics_risk_subsystem_spec_v1.3 §2A).

Purpose: enumerate every command and event in the locked contract as executable code, so the
IBKR mapping can be worked out against something real rather than against prose.

This is a SEAM PROTOTYPE, not an implementation. No ib_async import, no network. The IBKR
adapter below is a mapping skeleton whose job is to make the vendor frictions explicit and
fail loudly where the venue cannot satisfy the contract.

Contract invariants being encoded (§2A "Invariants of the seam"):
  1. command set + event set identical across vendors — an adapter satisfies the
     signature or it isn't done
  2. no vendor type crosses the line — only neutral structs/ids
  3. order and datafeed contracts are DISJOINT — no shared object
  4. all timestamps venue-sourced where a monotonic guard depends on them
  5. the send path is non-blocking regardless of vendor
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only —
# a blanket disable would hide the next real finding (nix_check_contract.md §5.2
# on why widening a gate is the wrong repair).
#
#   missing-class-docstring / missing-function-docstring
#       The neutral value types are Protocol members, enum members and one-line
#       dataclasses whose meaning lives in the module docstring and in the §2A
#       spec they transcribe. A per-member docstring here would restate the
#       spec (CLAUDE.md directive 3) rather than add anything.
#   unused-argument
#       Protocol and Stub signatures must carry the CONTRACT's parameters even
#       where a particular implementation ignores one. Trimming them would make
#       the seam's shape depend on the stub's behaviour, which is backwards.
#   too-many-arguments / too-many-positional-arguments / too-many-instance-attributes
#       on_fill's six parameters and the Stub's state are fixed by §2A, not by
#       this file. The metric is measuring the contract, not the code.
#   invalid-overridden-method
#       AwaitDivergentBrokerOrder overrides an async verb with a sync one ON
#       PURPOSE — that IS the instrument. See its docstring.
#   import-outside-toplevel
#       `inspect` is imported inside check_await_conformance so the conformance
#       harness costs nothing to anyone who only imports the value types.
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=unused-argument,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,invalid-overridden-method
# pylint: disable=import-outside-toplevel
import enum
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# NEUTRAL VALUE TYPES
# No vendor type may cross the seam (invariant 2), so every id and enum here is
# defined by Nix, never re-exported from a vendor SDK.
# ---------------------------------------------------------------------------


class Side(enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(enum.Enum):
    MARKET = "mkt"
    LIMIT = "limit"


class TimeInForce(enum.Enum):
    IOC = "ioc"
    DAY = "day"


class AckStatus(enum.Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SessionState(enum.Enum):
    UP = "up"
    DOWN = "down"


class FeedState(enum.Enum):
    UP = "up"
    DOWN = "down"
    STALE = "stale"


class MarketDataMode(enum.Enum):
    """Not in §2A. Added because ARC 013 measured IBKR silently downgrading a
    delayed-frozen request to delayed. The GRANTED mode must be observable at the
    seam, or a downgrade is invisible to everything above it."""

    REALTIME = 1
    FROZEN = 2
    DELAYED = 3
    DELAYED_FROZEN = 4
    UNKNOWN = 0


# Neutral identifiers. Deliberately str: a vendor int id (IBKR orderId) must be
# mapped, never leaked.
ClientOrderId = str
ExecId = str
Symbol = str


@dataclass(frozen=True)
class NeutralOrder:
    """§2A: {client_order_id, symbol, side, qty, type (mkt/limit), tif (IOC/day), limit_price?}"""

    client_order_id: ClientOrderId
    symbol: Symbol
    side: Side
    qty: int
    order_type: OrderType
    tif: TimeInForce
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError(f"qty must be positive, got {self.qty}")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError("market order must not carry limit_price")


@dataclass(frozen=True)
class BrokerCapabilities:
    """Not in §2A. Added because IBKR cannot satisfy parts of the contract that
    Tradovate can, and the difference must be VISIBLE above the seam rather than
    silently degraded.

    §2A invariant 1 says the command/event set is identical across vendors — that
    holds. What differs is which *paths* are live. Declaring it keeps the promise
    honest: the seam is identical, the venue's coverage of it is not."""

    pushes_margin: bool
    """§2A names on_margin the PRIMARY path and demotes get_margin to fallback.
    IBKR has no per-contract margin push (accountSummary is account-level only),
    so on IBKR the primary path does not exist and the fallback is the only path."""

    venue_sourced_balance_ts: bool
    """See Balance.ts_is_venue_sourced. False on IBKR."""

    native_flatten: bool
    """IBKR has no flatten primitive; it is composed from a position mirror plus
    opposing market orders."""

    realtime_ticks: bool
    """False on this IBKR account: reqTickByTickData returns Err 10189
    ('No market data permissions for CME FUT' — names the product class, so no
    instrument choice reaches it)."""

    def unmet_contract_paths(self) -> list[str]:
        """Names every §2A path this venue cannot serve. Empty == full coverage."""
        unmet = []
        if not self.pushes_margin:
            unmet.append("on_margin (push primary) — poll fallback is the only path")
        if not self.venue_sourced_balance_ts:
            unmet.append("on_balance venue_seq_ts — V27 not honestly satisfiable")
        if not self.native_flatten:
            unmet.append(
                "flatten — composed, not native; needs position mirror to stay non-blocking"
            )
        if not self.realtime_ticks:
            unmet.append("on_tick real-time — delayed/polled only at Stage 0")
        return unmet


@dataclass(frozen=True)
class Position:
    symbol: Symbol
    net_qty: int  # signed; negative = short
    avg_price: float
    """PER-UNIT price, in the instrument's quote units — NEVER notional.

    Stated because IBKR's Position.avgCost is notional (price x multiplier) while its
    Execution.price is per-unit, and ARC 014 measured both being written into this one
    field: a long 1 MESU6 filled at 7782.50 reported avgCost 38912.50, exactly 5x. An
    adapter MUST normalise before it gets here. A vendor whose native figure is notional
    divides by the multiplier; it does not redefine the field."""


@dataclass(frozen=True)
class Balance:
    """§2A query_balance: authoritative cash balance + margin figures.
    venue_seq_ts feeds the monotonic-by-source guard (V27)."""

    cash: float
    net_liquidation: float
    maint_margin: float
    init_margin: float
    venue_seq_ts: float
    ts_is_venue_sourced: bool = True
    """VERIFIED against ib_async 2.1.0: AccountValue._fields is
    ('account','tag','value','currency','modelCode') — there is NO timestamp.

    §2A invariant 4 requires venue-sourced timestamps where a monotonic guard depends
    on them, and V27 requires proving an out-of-order late poll is discarded. On IBKR
    that cannot be honestly satisfied: only local receipt time is available, so the
    guard would be testing OUR clock, not the venue's ordering.

    Rather than fabricate a venue timestamp, the adapter sets this False and the guard
    above can degrade knowingly. Tradovate's user-sync websocket carries a real venue
    sequence, so it sets True. V27 is then honestly reportable as CANNOT-MEASURE at
    Stage 0 instead of falsely green."""


@dataclass(frozen=True)
class OrderStatus:
    client_order_id: ClientOrderId
    terminal: bool
    state: str  # working | filled | cancelled | rejected | unknown
    cumulative_qty: int


@dataclass(frozen=True)
class FeedLag:
    """Not in §2A. ARC 013 measured a steady 600.3s pipeline delay on the Stage 0
    IBKR feed. Session-gating and staleness logic must be able to ask the feed how
    far behind it is, or every bar looks stale at Stage 0 and fresh in prod for
    reasons unrelated to correctness. Tradovate/DataBento report 0.0."""

    declared_lag_s: float
    measured: bool
    granted_mode: MarketDataMode


# ---------------------------------------------------------------------------
# EVENT SINKS
# §2A is a push/callback model — no polling on the hot path. The sink is what the
# Limiter (order) or capture.py (datafeed) implements.
# ---------------------------------------------------------------------------


class OrderEventSink(Protocol):
    """Events pushed to the Limiter. §2A broker-order events."""

    def on_ack(
        self,
        client_order_id: ClientOrderId,
        status: AckStatus,
        reason: str | None = None,
    ) -> None: ...

    def on_fill(
        self,
        client_order_id: ClientOrderId,
        exec_id: ExecId,
        symbol: Symbol,
        filled_qty: int,
        price: float,
        cumulative_qty: int,
    ) -> None:
        """Idempotent by (client_order_id, exec_id). Partials arrive as successive events."""

    def on_cancel(self, client_order_id: ClientOrderId, done_qty: int) -> None: ...

    def on_balance(self, balance: Balance) -> None:
        """Balance carries venue_seq_ts for the monotonic-by-source guard."""

    def on_margin(
        self, symbol: Symbol, margin_per_contract: float, venue_seq_ts: float
    ) -> None:
        """PRIMARY path per §2A; get_margin() is the poll fallback."""

    def on_position(self, symbol: Symbol, net_qty: int, avg_price: float) -> None: ...

    def on_session(self, state: SessionState, reason: str | None = None) -> None: ...


class DatafeedEventSink(Protocol):
    """Events pushed to capture.py. §2A broker-datafeed events."""

    def on_tick(
        self, symbol: Symbol, price: float, size: float, venue_ts: float
    ) -> None:
        """Raw firehose. capture.py builds bars — never broker-order."""

    def on_feed_status(
        self, state: FeedState, symbol: Symbol | None = None, reason: str | None = None
    ) -> None: ...


# ---------------------------------------------------------------------------
# THE TWO PORTS
# Invariant 3: disjoint. No shared object, so a datafeed fault cannot reach the
# order library. They are separate Protocols on purpose, not one with a flag.
# ---------------------------------------------------------------------------


@runtime_checkable
class BrokerOrderPort(Protocol):
    """§2A broker-order — commands called by the Limiter ONLY.
    In-process library inside the Risk Engine, Core 2.

    THE SPLIT (ARC 015, operator-ratified). This port is deliberately NOT uniformly
    sync or uniformly async. Every verb is declared on one side of a single question:
    *does this verb sit on the hot send path?*

      SYNC  — place_order, cancel_order, flatten, disconnect, query_order_status
        These either return no result (the ack arrives on on_ack, §2A) or read state
        the adapter already holds. Invariant 5 requires the send path be non-blocking,
        and `flatten` MUST NOT BLOCK (§2A protective path) — ARC 014 measured it at
        0.6 ms with zero venue queries. Declaring them sync is what keeps them that way:
        an `await` in these signatures is an invitation to put a round trip behind one.
        `query_order_status` is sync because it reads a cached `Trade.orderStatus`; it
        makes no venue call.

      ASYNC — connect, query_positions, query_balance, get_margin
        All off the hot path. `query_positions` is cold-start reconciliation (§4);
        `get_margin` is the poll fallback and already needs an explicit timeout. Each
        genuinely round-trips to the venue, so the await is honest.

    REJECTED ALTERNATIVE, recorded so it is not relitigated: keeping the port fully sync
    and having the adapter schedule the venue calls onto the loop. That resolves to
    either `run_until_complete` (blocks — violates invariant 5) or returning futures (an
    async contract wearing a sync signature, which is worse than declaring it). The IBKR
    adapter's docstring asserted this scheduling was already happening; it was not, and
    the claim was deleted in ARC 015.

    Enforcement is mechanical, not conventional: `check_await_conformance()` compares
    each adapter verb's coroutine-ness against this Protocol and reports any divergence.
    `check_structural_conformance()` alone CANNOT — `callable()` is true for `async def`
    too, so a coroutine-returning verb passes a sync-declared port and hands the caller
    an un-awaited coroutine object instead of a value."""

    async def connect(self) -> None: ...
    def disconnect(self) -> None: ...

    def place_order(self, order: NeutralOrder) -> None:
        """Submit. Returns an accepted/rejected ack via on_ack — NEVER a fill.
        Must be non-blocking (invariant 5)."""

    def cancel_order(self, client_order_id: ClientOrderId) -> None: ...

    def flatten(self, symbol: Symbol | None = None) -> None:
        """Market-close a position; None means all. Protective path — MUST NOT BLOCK."""

    async def query_positions(self) -> list[Position]:
        """Authoritative open-position set. Cold-start ground truth (§4)."""

    async def query_balance(self) -> Balance: ...

    def query_order_status(self, client_order_id: ClientOrderId) -> OrderStatus:
        """Pending-timeout resolution. NEVER auto-resend.

        Sync by contract: it reads state the adapter already holds. If a vendor ever
        forces a venue round trip here, that is a CONTRACT change to be argued, not a
        signature to quietly flip — the §4 pending-timeout path calls this."""

    async def get_margin(self, symbol: Symbol) -> float:
        """Poll FALLBACK for live per-symbol margin. Primary is the on_margin push."""


@runtime_checkable
class BrokerDatafeedPort(Protocol):
    """§2A broker-datafeed — commands called by capture.py ONLY.
    Library inside the capture.py process, Core 1."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def subscribe(self, symbol: Symbol) -> None: ...
    def unsubscribe(self, symbol: Symbol) -> None: ...

    def feed_lag(self) -> FeedLag:
        """Nix addition. See FeedLag."""


# The roster is the authority, not the docstrings. A predecessor system had a
# BrokerPort docstring claiming "the 12 verbs" while the roster held 15; the
# docstring was stale and the roster was right. Assert against these.
ORDER_PORT_VERBS: tuple[str, ...] = (
    "connect",
    "disconnect",
    "place_order",
    "cancel_order",
    "flatten",
    "query_positions",
    "query_balance",
    "query_order_status",
    "get_margin",
)

ORDER_EVENTS: tuple[str, ...] = (
    "on_ack",
    "on_fill",
    "on_cancel",
    "on_balance",
    "on_margin",
    "on_position",
    "on_session",
)

DATAFEED_PORT_VERBS: tuple[str, ...] = (
    "connect",
    "disconnect",
    "subscribe",
    "unsubscribe",
    "feed_lag",
)

DATAFEED_EVENTS: tuple[str, ...] = ("on_tick", "on_feed_status")


# ---------------------------------------------------------------------------
# STUB — vendorless. Must satisfy every verb with zero failures.
# Its job is to prove the contract is satisfiable without a venue, so seam tests
# don't need IBKR up.
# ---------------------------------------------------------------------------


class StubBrokerOrder:
    """Vendorless in-memory order adapter. Deterministic, no network."""

    def __init__(self, sink: OrderEventSink, *, margin_per_contract: float = 3503.59):
        self._sink = sink
        self._connected = False
        self._positions: dict[Symbol, Position] = {}
        self._working: dict[ClientOrderId, NeutralOrder] = {}
        self._status: dict[ClientOrderId, OrderStatus] = {}
        self._seen_execs: set[tuple[ClientOrderId, ExecId]] = set()
        self._margin = margin_per_contract
        self._exec_seq = 0

    async def connect(self) -> None:
        self._connected = True
        self._sink.on_session(SessionState.UP)

    def disconnect(self) -> None:
        self._connected = False
        self._sink.on_session(SessionState.DOWN, reason="requested")

    def _require_session(self, verb: str) -> None:
        if not self._connected:
            raise BrokerNotConnected(f"{verb} called with no session")

    def place_order(self, order: NeutralOrder) -> None:
        self._require_session("place_order")
        self._working[order.client_order_id] = order
        self._status[order.client_order_id] = OrderStatus(
            order.client_order_id, terminal=False, state="working", cumulative_qty=0
        )
        self._sink.on_ack(order.client_order_id, AckStatus.ACCEPTED)

    def simulate_fill(
        self, client_order_id: ClientOrderId, qty: int, price: float
    ) -> None:
        """Test hook — not part of the port."""
        order = self._working[client_order_id]
        self._exec_seq += 1
        exec_id = f"stub-exec-{self._exec_seq}"
        key = (client_order_id, exec_id)
        if key in self._seen_execs:
            return  # idempotent by (order_id, exec_id)
        self._seen_execs.add(key)

        prior = self._status[client_order_id].cumulative_qty
        cumulative = prior + qty
        self._status[client_order_id] = OrderStatus(
            client_order_id,
            terminal=cumulative >= order.qty,
            state="filled" if cumulative >= order.qty else "working",
            cumulative_qty=cumulative,
        )

        signed = qty if order.side is Side.BUY else -qty
        existing = self._positions.get(order.symbol)
        if existing is None:
            self._positions[order.symbol] = Position(order.symbol, signed, price)
        else:
            new_qty = existing.net_qty + signed
            if new_qty == 0:
                del self._positions[order.symbol]
            else:
                self._positions[order.symbol] = Position(order.symbol, new_qty, price)

        self._sink.on_fill(
            client_order_id, exec_id, order.symbol, qty, price, cumulative
        )
        pos = self._positions.get(order.symbol)
        self._sink.on_position(
            order.symbol, pos.net_qty if pos else 0, pos.avg_price if pos else 0.0
        )

    def cancel_order(self, client_order_id: ClientOrderId) -> None:
        self._require_session("cancel_order")
        st = self._status.get(client_order_id)
        done = st.cumulative_qty if st else 0
        self._status[client_order_id] = OrderStatus(
            client_order_id, terminal=True, state="cancelled", cumulative_qty=done
        )
        self._working.pop(client_order_id, None)
        self._sink.on_cancel(client_order_id, done)

    def flatten(self, symbol: Symbol | None = None) -> None:
        self._require_session("flatten")
        targets = [symbol] if symbol else list(self._positions.keys())
        for sym in targets:
            pos = self._positions.get(sym)
            if not pos:
                continue
            del self._positions[sym]
            self._sink.on_position(sym, 0, 0.0)

    async def query_positions(self) -> list[Position]:
        self._require_session("query_positions")
        # Zero-qty rows never enter self._positions (simulate_fill deletes on flat), so
        # the returned list and the internal record cannot disagree — the same property
        # the IBKR adapter has to establish by filtering (ARC 015 §2a).
        return [p for p in self._positions.values() if p.net_qty != 0]

    async def query_balance(self) -> Balance:
        self._require_session("query_balance")
        return Balance(
            cash=20344.34,
            net_liquidation=20344.34,
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=time.time(),
        )

    def query_order_status(self, client_order_id: ClientOrderId) -> OrderStatus:
        self._require_session("query_order_status")
        return self._status.get(
            client_order_id,
            OrderStatus(
                client_order_id, terminal=False, state="unknown", cumulative_qty=0
            ),
        )

    async def get_margin(self, symbol: Symbol) -> float:
        self._require_session("get_margin")
        return self._margin


class StubBrokerDatafeed:
    def __init__(self, sink: DatafeedEventSink):
        self._sink = sink
        self._connected = False
        self._subs: set[Symbol] = set()

    def connect(self) -> None:
        self._connected = True
        self._sink.on_feed_status(FeedState.UP)

    def disconnect(self) -> None:
        self._connected = False
        self._sink.on_feed_status(FeedState.DOWN, reason="requested")

    def subscribe(self, symbol: Symbol) -> None:
        if not self._connected:
            raise BrokerNotConnected("subscribe called with no session")
        self._subs.add(symbol)

    def unsubscribe(self, symbol: Symbol) -> None:
        self._subs.discard(symbol)

    def feed_lag(self) -> FeedLag:
        return FeedLag(
            declared_lag_s=0.0, measured=False, granted_mode=MarketDataMode.REALTIME
        )

    def simulate_tick(
        self, symbol: Symbol, price: float, size: float, venue_ts: float
    ) -> None:
        """Test hook — not part of the port."""
        if symbol in self._subs:
            self._sink.on_tick(symbol, price, size, venue_ts)


# ---------------------------------------------------------------------------
# HOLLOW — the CONTROL.
# Structurally conformant (every verb present, right signature) but behaviourally
# empty. A conformance test that passes HOLLOW is not testing behaviour, only shape.
# This is the non-vacuity instrument for the seam suite.
# ---------------------------------------------------------------------------


class HollowBrokerOrder:
    """Satisfies the shape. Does nothing. MUST fail behavioural assertions.

    Converted to the ARC 015 sync/async split ALONG WITH the real adapters, deliberately.
    The control's job is to be structurally indistinguishable from a working adapter and
    behaviourally empty; if it were left sync while the port went async it would start
    failing `check_await_conformance()` for a shape reason, and a control that fails for
    the wrong reason has stopped measuring what it was built to measure. It still returns
    nothing real from every verb — that is what the behavioural suite must catch."""

    def __init__(self, sink: OrderEventSink, **_: object):
        self._sink = sink

    async def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def place_order(self, order: NeutralOrder) -> None: ...
    def cancel_order(self, client_order_id: ClientOrderId) -> None: ...
    def flatten(self, symbol: Symbol | None = None) -> None: ...
    async def query_positions(self) -> list[Position]:
        return []

    async def query_balance(self) -> Balance:
        return Balance(0.0, 0.0, 0.0, 0.0, 0.0)

    def query_order_status(self, client_order_id: ClientOrderId) -> OrderStatus:
        return OrderStatus(
            client_order_id, terminal=False, state="unknown", cumulative_qty=0
        )

    async def get_margin(self, symbol: Symbol) -> float:
        return 0.0


# ---------------------------------------------------------------------------
# EXCEPTIONS — neutral. A vendor exception must never escape the adapter.
# ---------------------------------------------------------------------------


class BrokerSeamError(Exception):
    """Base. Every vendor exception is translated into one of these subclasses."""


class BrokerNotConnected(BrokerSeamError): ...


class BrokerRejected(BrokerSeamError): ...


class BrokerUnsupported(BrokerSeamError):
    """The venue cannot satisfy this part of the contract. Raised loudly rather
    than silently degraded — a silent degrade is how a contract rots."""


class SymbolNotResolved(BrokerSeamError): ...


# ---------------------------------------------------------------------------
# CONFORMANCE HARNESS
# ---------------------------------------------------------------------------


def check_structural_conformance(adapter: object, verbs: Iterable[str]) -> list[str]:
    """Returns list of missing/non-callable verbs. Empty list == structurally conformant.

    NOTE: callable() is true for an `async def` too, so this check alone CANNOT tell a
    sync verb from a coroutine function that returns an un-awaited coroutine object.
    Pair it with check_await_conformance() — see ARC 014."""
    missing = []
    for verb in verbs:
        attr = getattr(adapter, verb, None)
        if attr is None or not callable(attr):
            missing.append(verb)
    return missing


def check_await_conformance(
    adapter: object, port: type, verbs: Iterable[str]
) -> list[str]:
    """Returns verbs whose sync/async-ness DISAGREES with the port's declaration.

    Added in ARC 014. check_structural_conformance() passes an `async def` verb against a
    sync-declared port, because callable() cannot tell them apart — so an adapter could be
    reported fully conformant while every query verb hands the caller an un-awaited
    coroutine instead of a value. That is the same shape as the HOLLOW control: right
    shape, wrong behaviour, green light.

    A divergence here is a CONTRACT question, not a bug to paper over: the port decides
    which verbs are hot-path sync and which are awaited. This function only makes the
    disagreement visible so it cannot be settled by accident.

    ARC 015 settled the question — see BrokerOrderPort's docstring for the split and the
    rejected alternative — so from here on this function is the enforcement of a decision
    rather than the reporting of an open one. Its own non-vacuity instrument is
    AwaitDivergentBrokerOrder below: a gate that cannot fail proves nothing."""
    import inspect

    bad = []
    for verb in verbs:
        want = getattr(port, verb, None)
        got = getattr(adapter, verb, None)
        if want is None or got is None:
            continue
        want_async = inspect.iscoroutinefunction(want)
        got_async = inspect.iscoroutinefunction(got)
        if want_async != got_async:
            bad.append(
                f"{verb}: port declares {'async' if want_async else 'sync'}, "
                f"adapter is {'async' if got_async else 'sync'}"
            )
    return bad


class AwaitDivergentBrokerOrder(HollowBrokerOrder):
    """NON-VACUITY INSTRUMENT for check_await_conformance() — the planted divergence,
    kept rather than thrown away.

    check_await_conformance() is a gate, and a gate nobody has ever seen fail is
    indistinguishable from a gate that cannot fail. ARC 015 required the demonstration:
    plant one divergence, confirm the checker NAMES the verb, remove the plant. Removing
    the plant also removes the evidence, and the next author has to take the
    demonstration on trust — so the plant lives here permanently instead, as a class
    whose entire purpose is to be caught.

    The divergence is exactly one verb: `query_positions` is re-declared SYNC while
    BrokerOrderPort declares it async. Everything else is inherited from the Hollow
    control and conforms. So the expected report is precisely one entry, naming
    `query_positions` — which is the assertion the suites make. If a future edit makes
    the port fully sync again, this class stops diverging and its test fails loudly
    rather than silently passing."""

    def query_positions(self) -> list[Position]:  # type: ignore[override]  # deliberate divergence
        return []


@dataclass
class RecordingFeedSink:
    """A DatafeedEventSink that records. The datafeed counterpart of RecordingSink.

    Added in ARC 015 because the seam suite was passing `None` and then a `RecordingSink`
    into StubBrokerDatafeed — the second of which is an ORDER sink and does not implement
    `on_feed_status` at all. Invariant 3 says the two contracts are disjoint; borrowing
    the order sink for the feed port quietly asserted the opposite, and only survived
    because the assertions never drove a feed event through it."""

    ticks: list[tuple] = field(default_factory=list)
    feed_statuses: list[tuple] = field(default_factory=list)

    def on_tick(self, symbol, price, size, venue_ts):
        self.ticks.append((symbol, price, size, venue_ts))

    def on_feed_status(self, state, symbol=None, reason=None):
        self.feed_statuses.append((state, symbol, reason))


@dataclass
class RecordingSink:
    """An OrderEventSink that records. Used by the behavioural assertions."""

    acks: list[tuple] = field(default_factory=list)
    fills: list[tuple] = field(default_factory=list)
    cancels: list[tuple] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)
    margins: list[tuple] = field(default_factory=list)
    positions: list[tuple] = field(default_factory=list)
    sessions: list[tuple] = field(default_factory=list)

    sequence: list[str] = field(default_factory=list)
    """Every event in ARRIVAL ORDER, across all seven streams.

    Added in ARC 015 for the missing-ack race (§2c). The per-stream lists above cannot
    express 'the ack preceded the fill' — that is a cross-stream ordering property, and
    an adapter that emits the fill first would satisfy every per-stream assertion. The
    guarantee being proved is an ordering one, so the observable has to be an ordering."""

    def on_ack(self, client_order_id, status, reason=None):
        self.acks.append((client_order_id, status, reason))
        self.sequence.append("on_ack")

    def on_fill(
        self, client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty
    ):
        self.fills.append(
            (client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty)
        )
        self.sequence.append("on_fill")

    def on_cancel(self, client_order_id, done_qty):
        self.cancels.append((client_order_id, done_qty))
        self.sequence.append("on_cancel")

    def on_balance(self, balance):
        self.balances.append(balance)
        self.sequence.append("on_balance")

    def on_margin(self, symbol, margin_per_contract, venue_seq_ts):
        self.margins.append((symbol, margin_per_contract, venue_seq_ts))
        self.sequence.append("on_margin")

    def on_position(self, symbol, net_qty, avg_price):
        self.positions.append((symbol, net_qty, avg_price))
        self.sequence.append("on_position")

    def on_session(self, state, reason=None):
        self.sessions.append((state, reason))
        self.sequence.append("on_session")
