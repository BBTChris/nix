"""
ibkr_mapping.py — PROTOTYPE: mapping each §2A neutral verb/event onto ib_async.

NOT AN IMPLEMENTATION. No ib_async import, no network. This is the mapping worked out
against the real contract so the frictions surface now, on paper, instead of mid-build.

Every verb carries a MAPPING annotation. Where IBKR cannot satisfy the contract, the
method raises BrokerUnsupported rather than silently degrading — a silent degrade is
exactly how "swap is config, not code" (§2A invariant 1) rots into a lie.

Findings are graded:
  CLEAN     — direct mapping, no friction
  FRICTION  — mappable but with a trap that must be handled explicitly
  GAP       — IBKR cannot satisfy the contract as written; needs an architectural answer
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   missing-class-docstring / missing-function-docstring
#       Every method in the skeleton raises, carrying its MAPPING string as the
#       exception message — that string IS the documentation, and it is the form
#       the caller actually sees.
#   unused-argument
#       The skeleton's signatures must match the port exactly; that is the whole
#       point of a structural conformance subject.
# pylint: disable=missing-class-docstring,missing-function-docstring,unused-argument
from dataclasses import dataclass

from broker_seam import (
    Balance,
    BrokerUnsupported,
    ClientOrderId,
    FeedLag,
    MarketDataMode,
    NeutralOrder,
    OrderStatus,
    Position,
    Symbol,
)


@dataclass(frozen=True)
class Finding:
    verb: str
    grade: str  # CLEAN | FRICTION | GAP
    ibkr_call: str
    note: str


FINDINGS: tuple[Finding, ...] = (
    # ---------------- broker-order commands ----------------
    Finding(
        "connect / disconnect",
        "CLEAN",
        "IB.connectAsync(host, port, clientId) / IB.disconnect()",
        "clientId=1 reserved for Risk Engine, 905 diagnostics, 0 permanently excluded "
        "(0 implicitly adopts manually-placed TWS orders — order-ownership ambiguity the "
        "mission scope forbids). Gateway socket is UNAUTHENTICATED: anything reaching "
        "127.0.0.1:4002 can trade. Host security IS account security.",
    ),
    Finding(
        "place_order",
        "FRICTION",
        "IB.placeOrder(contract, order) -> Trade",
        "IBKR returns a Trade object SYNCHRONOUSLY; the contract says place_order returns "
        "an ack via on_ack and NEVER a fill. So the Trade return must be swallowed inside "
        "the adapter and the ack raised from the orderStatus callback instead. Leaking the "
        "Trade upward would put a vendor type across the seam (invariant 2).",
    ),
    Finding(
        "client_order_id mapping",
        "FRICTION",
        "Order.orderId (int) <-> ClientOrderId (str)",
        "IBKR ids are ints from a per-session sequence; neutral ids are opaque strings. "
        "Needs a bidirectional map owned by the adapter. IBKR's sequence RESETS across "
        "Gateway restarts (and there is a 'Reset API order ID sequence' button in the GUI), "
        "so the map must not be assumed stable across the daily 03:00 auto-restart.",
    ),
    Finding(
        "cancel_order",
        "CLEAN",
        "IB.cancelOrder(order)",
        "Requires the Order object, not just the id — the adapter's id map must retain it.",
    ),
    Finding(
        "flatten(symbol | all)",
        "GAP",
        "no native call",
        "IBKR has NO flatten primitive. Must be composed: query positions, then place "
        "opposing MKT orders. But §2A says flatten is the protective path and MUST NOT "
        "BLOCK — and a compose-from-query is inherently two round trips. Needs an explicit "
        "design answer: likely maintain a live position mirror so flatten never has to "
        "query first. Also §4's market-tradable guard applies: flatten fires market orders, "
        "so a closed market must HALT+alert, never fire into a shut venue.",
    ),
    Finding(
        "query_positions",
        "CLEAN",
        "IB.reqPositionsAsync() / IB.positions()",
        "Cold-start ground truth (§4). At cold start the broker's answer IS the record.",
    ),
    Finding(
        "query_balance",
        "FRICTION",
        "IB.accountSummaryAsync() / accountValues()",
        "Values arrive as tagged strings ('NetLiquidation', 'MaintMarginReq') requiring "
        "parse + unit handling. See the on_balance GAP below for the timestamp problem.",
    ),
    Finding(
        "query_order_status",
        "CLEAN",
        "Trade.orderStatus / IB.reqAllOpenOrdersAsync()",
        "Contract mandates: resolve pending timeouts, NEVER auto-resend.",
    ),
    Finding(
        "get_margin(symbol)",
        "FRICTION",
        "IB.whatIfOrderAsync(contract, order)",
        "MEASURED TRAP (ARC 012): the SYNC ib.whatIfOrder() returns an empty OrderState "
        "with initMarginChange=None — its internal wait expires before IB answers. The "
        "asymmetry is what makes it dangerous: a REJECTED order leaves an err 201 carrying "
        "the margin number, so empty costs nothing; an AFFORDABLE order has no error, so "
        "empty reads as 'undetermined' with nothing to correct it. MUST use "
        "whatIfOrderAsync awaited under an explicit timeout (45s worked).",
    ),
    # ---------------- broker-order events ----------------
    Finding(
        "on_ack",
        "CLEAN",
        "IB.orderStatusEvent -> status in {PreSubmitted, Submitted} | errorEvent",
        "Rejection reasons arrive on errorEvent, not orderStatus — the adapter must join "
        "the two streams to produce one neutral ack.",
    ),
    Finding(
        "on_fill",
        "CLEAN",
        "IB.execDetailsEvent -> Execution.execId",
        "IBKR execId is natively unique and stable, so the contract's idempotency key "
        "(order_id, exec_id) maps directly. This is the cleanest mapping in the set.",
    ),
    Finding(
        "on_cancel",
        "CLEAN",
        "IB.orderStatusEvent -> status == 'Cancelled'",
        "done_qty from Trade.orderStatus.filled.",
    ),
    Finding(
        "on_balance(venue_seq_ts)",
        "GAP",
        "IB.accountValueEvent",
        "**IBKR does not supply a venue-sourced timestamp on account value updates.** "
        "§2A invariant 4 requires venue-sourced timestamps where a monotonic guard depends "
        "on them, and V27 explicitly requires proving an out-of-order late poll is "
        "discarded. With only local receipt time, the guard is testing OUR clock, not the "
        "venue's ordering — which is precisely the guarantee V27 exists to establish. "
        "Needs an architectural answer before R3.",
    ),
    Finding(
        "on_margin(symbol, ...)",
        "GAP",
        "no per-symbol margin push exists",
        "§2A names on_margin the PRIMARY path and demotes get_margin to fallback/audit. "
        "IBKR has no per-contract margin push — accountSummary carries ACCOUNT-level margin "
        "only. So on IBKR the primary path DOES NOT EXIST and the fallback is the only "
        "path. Tradovate's user-sync websocket is what §2A was written against. Consequence: "
        "Stage 0 exercises a poll-shaped margin path, and the push path is UNTESTED until "
        "cutover — the seam must not let that asymmetry leak upward.",
    ),
    Finding(
        "on_position",
        "CLEAN",
        "IB.positionEvent",
        "Unsolicited position updates. §4: position state derives from cumulative fills, "
        "so this is corroboration, not the primary source.",
    ),
    Finding(
        "on_session",
        "FRICTION",
        "IB.connectedEvent / disconnectedEvent + error 1100/1101/1102",
        "Connectivity truth is split across two event streams and three error codes: "
        "1100 = connectivity lost, 1101 = restored WITH data loss, 1102 = restored "
        "WITHOUT data loss. 1101 vs 1102 matters — 1101 means our position mirror may have "
        "missed events and must re-reconcile. Collapsing both into 'up' would silently "
        "discard that. Predecessor lesson: broker `connected` state was computed and NEVER "
        "published anywhere a check could read it, so nothing could distinguish connected "
        "from disconnected. Do not rebuild that gap — on_session must be observable.",
    ),
    # ---------------- broker-datafeed ----------------
    Finding(
        "subscribe / on_tick",
        "GAP",
        "reqTickByTickData -> Err 10189 on this account",
        "MEASURED (ARC 012/013): no real-time tick stream. reqTickByTickData fails with "
        "10189 'No market data permissions for CME FUT' — names the PRODUCT CLASS, not the "
        "contract, so no instrument choice reaches it. The working paths are "
        "reqMarketDataType(3)+reqMktData (delayed stream) and reqHistoricalTicks (polled, "
        "ALSO ~10min delayed). So Stage 0's feed is delayed AND polled/quote-shaped, not a "
        "real-time trade firehose. on_tick's shape (price,size,venue_ts) is satisfiable "
        "from delayed reqMktData, but the SEMANTICS differ from what prod will deliver.",
    ),
    Finding(
        "feed_lag",
        "FRICTION",
        "Ticker.marketDataType + delayedLastTimestamp",
        "MEASURED (ARC 013): steady 600.3s (spread 1.9s over n=8). Two traps. (1) IBKR "
        "SILENTLY DOWNGRADES: requesting mode 4 was granted as 3. (2) ib_async's "
        "Ticker.marketDataType DEFAULTS TO 1, so an unset field is indistinguishable from a "
        "real-time grant — a naive read reports 'real-time granted' for a subscription "
        "returning zero ticks and error 354. Sentinel the field to 0 after subscribing so "
        "only a genuine callback can move it. NEVER infer the mode from the request.",
    ),
    Finding(
        "symbol resolution",
        "FRICTION",
        "IB.qualifyContractsAsync(Future(...))",
        "Neutral Symbol -> IBKR conId requires a resolution layer the contract doesn't "
        "mention. Front-month expiry changes: MESU6 conId=793356217 expires 20260918. "
        "Contract rolls are scheduled for R4 but the ADAPTER needs a resolution cache from "
        "R1, or every verb pays a qualify round-trip.",
    ),
)


class IBKROrderAdapter:
    """Mapping skeleton. Every method documents its mapping; GAP methods raise.

    Carries the ARC 015 sync/async split (see BrokerOrderPort) even though every verb
    raises: the skeleton is a structural conformance subject, and check_await_conformance()
    is run against it. A skeleton left sync while the port went async would report a
    divergence for every query verb and drown the one that matters.
    """

    def __init__(
        self, sink, *, host: str = "127.0.0.1", port: int = 4002, client_id: int = 1
    ):
        if client_id == 0:
            raise ValueError(
                "clientId=0 is permanently excluded: it implicitly adopts manually-placed "
                "TWS orders, creating the order-ownership ambiguity the mission scope forbids"
            )
        self._sink = sink
        self._host, self._port, self._client_id = host, port, client_id
        self._id_map: dict[ClientOrderId, int] = {}
        self._rev_map: dict[int, ClientOrderId] = {}

    # --- mappable ---
    async def connect(self) -> None:
        raise NotImplementedError("MAPPING: IB.connectAsync(host, port, clientId)")

    def disconnect(self) -> None:
        raise NotImplementedError("MAPPING: IB.disconnect()")

    def place_order(self, order: NeutralOrder) -> None:
        raise NotImplementedError(
            "MAPPING: IB.placeOrder(contract, order) -> Trade. Swallow the Trade; "
            "raise on_ack from orderStatusEvent, joined with errorEvent for reject reasons."
        )

    def cancel_order(self, client_order_id: ClientOrderId) -> None:
        raise NotImplementedError(
            "MAPPING: IB.cancelOrder(order) — needs Order from id map"
        )

    async def query_positions(self) -> list[Position]:
        raise NotImplementedError("MAPPING: IB.reqPositionsAsync()")

    async def query_balance(self) -> Balance:
        raise NotImplementedError(
            "MAPPING: IB.accountSummaryAsync(); parse tagged strings. "
            "WARNING: no venue_seq_ts available — see GAP on_balance."
        )

    def query_order_status(self, client_order_id: ClientOrderId) -> OrderStatus:
        raise NotImplementedError("MAPPING: Trade.orderStatus. NEVER auto-resend.")

    async def get_margin(self, symbol: Symbol) -> float:
        raise NotImplementedError(
            "MAPPING: await IB.whatIfOrderAsync(...) under explicit timeout. "
            "The SYNC whatIfOrder() silently returns empty — see FRICTION get_margin."
        )

    # --- gaps: refuse rather than degrade ---
    def flatten(self, symbol: Symbol | None = None) -> None:
        raise BrokerUnsupported(
            "IBKR has no flatten primitive. Composing it from query+opposing-MKT violates "
            "the must-not-block requirement of the protective path. Needs a live position "
            "mirror so flatten never queries first. See GAP flatten."
        )


class IBKRDatafeedAdapter:
    """Mapping skeleton for the datafeed port. Every method documents its mapping; GAPs raise.

    Carries the ARC 022 D1.38 sync/async split (see `BrokerDatafeedPort`) even though every verb
    raises, for the reason `IBKROrderAdapter` above records for the ARC 015 split: the skeleton
    is a conformance subject and `check_await_conformance()` is run against it. A skeleton left
    sync while the port went async would report a divergence for every wire verb and drown the
    one that matters.
    """

    def __init__(
        self, sink, *, host: str = "127.0.0.1", port: int = 4002, client_id: int = 2
    ):
        self._sink = sink
        self._granted_mode = MarketDataMode.UNKNOWN

    async def connect(self) -> None:
        raise NotImplementedError(
            "MAPPING: IB.connectAsync() — SEPARATE session from order path"
        )

    async def disconnect(self) -> None:
        raise NotImplementedError("MAPPING: IB.disconnect()")

    async def subscribe(self, symbol: Symbol) -> None:
        raise BrokerUnsupported(
            "reqTickByTickData returns Err 10189 on this account (no CME FUT real-time "
            "permission). The available paths are reqMarketDataType(3)+reqMktData (delayed) "
            "and reqHistoricalTicks (polled, also delayed). Neither is a real-time trade "
            "firehose. See GAP subscribe/on_tick."
        )

    async def unsubscribe(self, symbol: Symbol) -> None:
        raise NotImplementedError("MAPPING: IB.cancelMktData(contract)")

    async def poll_history(self, symbol: Symbol) -> int:
        raise NotImplementedError(
            "MAPPING: IB.reqHistoricalData(...) — and it is DELAYED by the same ~10 minutes as "
            "the stream (ARC 010 measured 624 s on reqHistoricalTicks, ARC 013 re-measured "
            "604 s). Not a real-time back door. Rows seal via broker_seam.Bar; a re-poll that "
            "contradicts a sealed bar publishes on_bar_revision, never on_bar (D1.14)."
        )

    def feed_lag(self) -> FeedLag:
        raise NotImplementedError(
            "MAPPING: read GRANTED Ticker.marketDataType (sentinel to 0 first — it defaults "
            "to 1) and measure delayedLastTimestamp vs receipt. Measured 600.3s at Stage 0."
        )

    def granted_mode(self) -> MarketDataMode:
        raise NotImplementedError(
            "MAPPING: read Ticker.marketDataType AFTER sentinelling it to 0 — ARC 013 measured "
            "ib_async defaulting it to 1, so an unset field reports a real-time grant that "
            "never happened. Never infer the mode from the request (D1.13)."
        )


def summarise() -> None:
    by_grade: dict[str, list[Finding]] = {"CLEAN": [], "FRICTION": [], "GAP": []}
    for f in FINDINGS:
        by_grade[f.grade].append(f)
    print(f"{'VERB / EVENT':<28} {'GRADE':<9} IBKR CALL")
    print("-" * 100)
    for grade in ("GAP", "FRICTION", "CLEAN"):
        for f in by_grade[grade]:
            print(f"{f.verb:<28} {f.grade:<9} {f.ibkr_call}")
    print("-" * 100)
    print(
        f"CLEAN {len(by_grade['CLEAN'])}  |  "
        f"FRICTION {len(by_grade['FRICTION'])}  |  "
        f"GAP {len(by_grade['GAP'])}   (total {len(FINDINGS)})"
    )


if __name__ == "__main__":
    summarise()
