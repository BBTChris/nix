"""
broker_order_ibkr.py — IBKR implementation of the §2A broker-order contract.

In-process library inside the Risk Engine (Core 2). Called by the Limiter ONLY.

Every ib_async call and field name below was VERIFIED against ib_async 2.1.0 (the version
pinned on node02), not recalled. Verification notes are inline where a fact is
non-obvious or was measured empirically.

DESIGN DECISIONS on the four gaps the mapping exercise surfaced. All four are stated
here rather than buried, because each is cheap to overturn now and expensive later:

  GAP-1 flatten: IBKR has no flatten primitive, and §2A says the protective path MUST
    NOT BLOCK. Composing it from query_positions() would cost a round trip on the
    protective path. DECISION: maintain a live position mirror fed by positionEvent and
    fills, so flatten reads memory and fires opposing MKT orders immediately.

  GAP-2 balance timestamp: AccountValue carries no timestamp (verified: _fields is
    ('account','tag','value','currency','modelCode')). DECISION: do not fabricate one.
    Set Balance.ts_is_venue_sourced=False so the monotonic guard degrades knowingly and
    V27 reports CANNOT-MEASURE at Stage 0 rather than falsely green.

  GAP-3 margin push: no per-contract push exists on IBKR. DECISION: declare
    capabilities.pushes_margin=False. on_margin never fires from this adapter; the
    Limiter must poll get_margin. The asymmetry is visible, not hidden.

  GAP-4 real-time ticks: not this adapter's concern (datafeed is a separate library,
    §2A invariant 3 — disjoint). Recorded in capabilities for completeness only.

ASYNC SURFACE (ARC 015). This adapter presents the split declared by BrokerOrderPort:
`connect`, `query_positions`, `query_balance` and `get_margin` are coroutines; everything
else — `place_order`, `cancel_order`, `flatten`, `disconnect`, `query_order_status` — is
plain sync and makes no venue round trip. The send path is non-blocking (invariant 5)
because `ib.placeOrder` and `ib.cancelOrder` are themselves non-blocking calls that hand
the request to the loop's writer and return, NOT because anything here schedules work.

  An earlier version of this docstring claimed "the sync surface the Limiter sees is
  satisfied by scheduling onto the loop, never by blocking it." That was false: no such
  scheduling existed anywhere in this file, and the async verbs were already `async def`
  and had to be awaited. ARC 014 found the claim; ARC 015 deleted it. It is recorded here
  rather than erased because a docstring that described a mechanism the code did not have
  is the failure mode this file is most exposed to — every gap decision below is a claim
  about behaviour that only a reader can check.

RETRY POLICY — DO NOT ADD ONE TO THE ORDER PATH. No `tenacity`, no `backoff`, no
hand-rolled loop, no decorator on `place_order`, `cancel_order` or `flatten`. §4 is
explicit: a pending timeout is resolved by QUERYING order status, and the system NEVER
auto-resends. A retry wrapper around a submit turns one intended order into two live
orders and there is no way to tell them apart afterwards — the venue accepted both. The
failure this protects against is not hypothetical politeness: a socket write that raises
AFTER the request reached the venue is indistinguishable, from inside this process, from
one that never left. That is precisely why `place_order` rolls back its registration and
re-raises instead of retrying: the DECISION to send again belongs to the Limiter, which
owns the pending-timeout state machine and can call `query_order_status` first.
Retry is admissible only on genuinely idempotent reads — `query_balance`, `get_margin` —
and even there it must not convert a CANNOT-MEASURE into a stale value; `get_margin`
raises rather than returning a previous figure, and that must stay true.

CONCURRENCY POLICY: if supervised background work is ever added here, use
`asyncio.TaskGroup` (Python 3.14.4 is installed), never a bare `create_task`. A task that
dies silently in the background on the order path is a lost fill or a lost cancel. As of
ARC 015 this file creates no tasks at all — the policy is recorded before the first one,
not after.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   invalid-name
#       _on_ib_error's parameters are ib_async's callback signature (reqId,
#       errorCode, errorString). The names are the vendor's documented contract
#       and renaming them to snake_case would make this handler harder to check
#       against the SDK, which is the one thing every line here is verified
#       against.
#   missing-function-docstring
#       Trivial accessors (capabilities, disconnect) whose behaviour is stated
#       in the class and module docstrings above.
#   broad-exception-caught
#       Two sites, both deliberate and both commented: flatten must not abandon
#       the remaining symbols on the PROTECTIVE path, and _rebuild_mirror must
#       not kill connect(). Narrowing either would convert a degraded state into
#       an outage.
#   unused-argument
#       Vendor callbacks are called with parameters this adapter does not need
#       (errorEvent's `contract`, execDetailsEvent's `trade`). They stay in the
#       signature because ib_async passes them positionally.
#   too-many-instance-attributes / too-many-arguments / too-many-locals
#       The id map, the mirror, the exec ledger and the two ack dedupe sets are
#       each required by a named §2A/§4 guarantee. Merging them to satisfy a
#       count would make the state harder to reason about, not easier.
#   import-outside-toplevel
#       ib_async is imported lazily and BY NAME inside the two methods that need
#       it, so a missing or renamed vendor symbol fails loudly at the call site
#       rather than making this whole module unimportable in offline tests.
# pylint: disable=invalid-name,missing-function-docstring,broad-exception-caught
# pylint: disable=unused-argument,too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-locals,import-outside-toplevel
import asyncio
import itertools
import logging
import time
from typing import Any

from broker_seam import (
    AckStatus,
    Balance,
    BrokerCapabilities,
    BrokerNotConnected,
    BrokerSeamError,
    ClientOrderId,
    ExecId,
    NeutralOrder,
    OrderEventSink,
    OrderStatus,
    OrderType,
    Position,
    SessionState,
    Side,
    Symbol,
    SymbolNotResolved,
    TimeInForce,
)

log = logging.getLogger("nix.broker_order.ibkr")

# VERIFIED ib_async 2.1.0: OrderStatus.DoneStates / ActiveStates
IB_DONE_STATES = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}
IB_ACTIVE_STATES = {
    "PendingSubmit",
    "ApiPending",
    "PreSubmitted",
    "Submitted",
    "ApiUpdate",
    "ValidationError",
}
IB_ACK_STATES = {"PreSubmitted", "Submitted"}

# IBKR connectivity error codes. 1101 vs 1102 is load-bearing: 1101 means the session
# was restored WITH data loss, so our mirror may have missed events and must
# re-reconcile. Collapsing both into "up" would silently discard that.
IB_ERR_CONN_LOST = 1100
IB_ERR_CONN_RESTORED_DATA_LOST = 1101
IB_ERR_CONN_RESTORED_DATA_OK = 1102
# Codes that are informational noise, not order rejections.
IB_INFO_CODES = {2104, 2106, 2107, 2108, 2119, 2158, 1102}


class IBKRBrokerOrder:
    """§2A broker-order, IBKR scaffold."""

    CAPABILITIES = BrokerCapabilities(
        pushes_margin=False,
        venue_sourced_balance_ts=False,
        native_flatten=False,
        realtime_ticks=False,
    )

    def __init__(
        self,
        sink: OrderEventSink,
        *,
        ib=None,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
        margin_timeout_s: float = 45.0,
        contract_resolver=None,
    ):
        # clientId 0 implicitly adopts manually-placed TWS orders, creating exactly the
        # order-ownership ambiguity the mission scope forbids. Refuse at construction.
        if client_id == 0:
            raise ValueError(
                "clientId=0 is permanently excluded: it implicitly adopts manually-placed "
                "TWS orders. Use 1 (Risk Engine) or 905 (diagnostics)."
            )
        self._sink = sink
        self._ib = ib  # injected; None means caller must supply before connect()
        self._host, self._port, self._client_id = host, port, client_id
        self._margin_timeout_s = margin_timeout_s
        self._resolve_contract = contract_resolver

        # --- id mapping (FRICTION) ---
        # IBKR orderIds are ints from a per-session sequence that RESETS across Gateway
        # restarts (and there is a "Reset API order ID sequence" button in the GUI).
        # Gateway auto-restarts daily at 03:00, so this map must never be assumed to
        # survive a session. It is rebuilt on connect.
        self._to_ib: dict[ClientOrderId, int] = {}
        self._from_ib: dict[int, ClientOrderId] = {}
        self._orders: dict[ClientOrderId, Any] = {}  # neutral id -> ib Order
        # `Any`, not `object`: these hold VENDOR types (ib_async Order/Trade) that must
        # never cross the seam (invariant 2). Typing them `object` made every field read
        # a type error while adding no safety — the seam's guarantee is that they stay
        # inside this class, and that is enforced by the return types of the port, not
        # by pretending we do not know their shape.
        self._trades: dict[ClientOrderId, Any] = {}  # neutral id -> ib Trade
        self._neutral: dict[ClientOrderId, NeutralOrder] = {}

        # --- idempotency (§4: dedupe by (order_id, exec_id)) ---
        self._seen_execs: set[tuple[ClientOrderId, ExecId]] = set()

        # --- position mirror (GAP-1) ---
        # flatten() reads this, never the wire, so the protective path never round-trips.
        self._mirror: dict[Symbol, Position] = {}

        # --- ack dedupe: IBKR re-emits orderStatus on every change ---
        self._acked: set[ClientOrderId] = set()
        self._cancelled: set[ClientOrderId] = set()

        self._connected = False
        self._flatten_seq = itertools.count(1)

        # --- startup-replay gate (ARC 015 §2b) ---
        # False for the whole of connect(); order-path events arriving in that window are
        # the venue replaying HISTORY, not reporting our activity. See _startup_open().
        self._startup_complete = False
        # Which IB instance this adapter's handlers are already registered on. ib_async's
        # Event uses `+=`, so calling _wire_events() once per connect() would register a
        # SECOND copy of every handler after the Gateway's 03:00 restart, and a third
        # after the next one. The dedupe sets would hide the duplicate ack and the
        # duplicate fill, so nothing would look wrong until an un-deduped path appeared.
        self._wired_ib: object | None = None

    # ------------------------------------------------------------------ session

    async def connect(self) -> None:
        """Establish the session. Async by contract — this is the one verb that is
        allowed to take as long as the venue takes.

        ARC 015 §2b — STARTUP EXECUTION REPLAY. ib_async's connectAsync defaults to
        fetchFields=StartupFetchALL, which includes EXECUTIONS: on connect it issues
        reqExecutions and the venue replays the account's HISTORICAL executions, which
        ib_async dispatches on execDetailsEvent — straight into _on_ib_exec_details, the
        fill handler the Limiter is downstream of. Before this arc those replays were
        dropped only because self._from_ib happened to be empty at that moment. That is
        luck, not design: it depended on the id map being cleared AFTER connectAsync, so
        a reconnect carrying a stale map from the previous session could have matched a
        historical execution to a live neutral id and reported a phantom fill.

        MECHANISM OF RECORD — a connect-scoped gate. `self._startup_complete` is set
        False at the TOP of this method and True the instant connectAsync returns; the
        two order-path handlers (_on_ib_order_status, _on_ib_exec_details) refuse while
        it is closed. Chosen over the alternatives because it is venue-agnostic (it
        catches any startup replay, whatever ib_async decides to fetch, including
        anything a future ib_async version adds) and because it is scoped to the CALL,
        so it re-arms on every reconnect for free — no separate reconnect path to
        maintain, which matters given the Gateway restarts daily at 03:00.

        Belt and braces at the source: fetchFields drops EXECUTIONS so the replay is not
        requested in the first place. The gate is the guarantee; this only reduces what
        has to be caught. Nothing here reads ib.fills()/ib.executions() — the adapter
        keeps its own (order_id, exec_id) ledger — so dropping the fetch costs nothing.

        WHY THE GATE OPENS BEFORE THE MIRROR REBUILD, not after: _rebuild_mirror() awaits
        reqPositionsAsync, and a GENUINE fill can land during that await (that is the D3
        race the suite already covers). Holding the gate closed across it would drop a
        real fill to close a historical one. There is no await between connectAsync
        returning and the gate opening, so the loop cannot dispatch anything into the
        window — the two statements are atomic with respect to event delivery.

        Position and account-value events are NOT gated: startup position snapshots are
        exactly what the mirror wants, and they carry no order identity to confuse.
        """
        if self._ib is None:
            raise BrokerSeamError("no IB instance injected")

        self._startup_complete = False
        # Session boundary invalidates every IBKR-side id. Cleared BEFORE connectAsync,
        # not after: the venue's startup replay arrives DURING connectAsync, and a map
        # still holding last session's ids is exactly what would let a replayed event be
        # mistaken for one of ours. The gate above already refuses these, so this is the
        # second of two independent reasons a stale id cannot match.
        self._to_ib.clear()
        self._from_ib.clear()
        self._acked.clear()
        self._cancelled.clear()

        self._wire_events()
        await self._ib.connectAsync(
            host=self._host,
            port=self._port,
            clientId=self._client_id,
            timeout=10,
            fetchFields=self._startup_fetch_fields(),
        )
        # No await between here and the gate opening — see the docstring.
        self._connected = True
        self._startup_complete = True

        await self._rebuild_mirror()
        self._sink.on_session(SessionState.UP)

    @staticmethod
    def _startup_fetch_fields():
        """StartupFetchALL minus EXECUTIONS — see connect().

        Imported lazily and by name so that if ib_async ever renames or removes the flag
        the failure is a loud ImportError at connect time, not a silently-restored
        historical execution replay.
        """
        from ib_async.ib import (  # pylint: disable=import-error
            StartupFetch,
            StartupFetchALL,
        )

        return StartupFetchALL & ~StartupFetch.EXECUTIONS

    def disconnect(self) -> None:
        self._connected = False
        # Close the gate too: between disconnect and the next connect, any order-path
        # event still in flight belongs to a session that no longer exists.
        self._startup_complete = False
        if self._ib is not None:
            self._ib.disconnect()
        self._sink.on_session(SessionState.DOWN, reason="requested")

    def _require_session(self, verb: str) -> None:
        if not self._connected:
            raise BrokerNotConnected(f"{verb} called with no session")

    def _wire_events(self) -> None:
        """Register once per IB instance, not once per connect() — see _wired_ib."""
        ib = self._ib
        if self._wired_ib is ib:
            return
        ib.orderStatusEvent += self._on_ib_order_status
        ib.execDetailsEvent += self._on_ib_exec_details
        ib.errorEvent += self._on_ib_error
        ib.positionEvent += self._on_ib_position
        ib.accountValueEvent += self._on_ib_account_value
        ib.disconnectedEvent += self._on_ib_disconnected
        self._wired_ib = ib

    # ------------------------------------------------------------------ commands

    def place_order(self, order: NeutralOrder) -> None:
        """§2A: returns an accepted/rejected ack via on_ack, NEVER a fill.

        ib.placeOrder returns a Trade SYNCHRONOUSLY. That Trade is a vendor type and
        must not cross the seam (invariant 2), so it is retained internally and the ack
        is raised from orderStatusEvent instead.
        """
        self._require_session("place_order")
        if order.client_order_id in self._neutral:
            raise BrokerSeamError(f"duplicate client_order_id {order.client_order_id}")

        contract = self._contract_for(order.symbol)
        ib_order = self._build_ib_order(order)

        # DEFECT FIX (ordering): register the neutral order BEFORE placing. ib_async
        # dispatches events from the loop, and an execution report arriving before the
        # id map was populated would find no mapping and be discarded as "foreign" —
        # a silently dropped fill on the order path. Registering first makes the window
        # unreachable. The orderId itself is only known after placeOrder assigns it,
        # so that half of the map is completed immediately after.
        self._neutral[order.client_order_id] = order
        self._orders[order.client_order_id] = ib_order
        try:
            trade = self._ib.placeOrder(contract, ib_order)  # non-blocking
        except Exception:
            # Roll back the pre-registration so a failed placement doesn't poison the
            # duplicate-id guard and block a legitimate retry under the same id.
            self._neutral.pop(order.client_order_id, None)
            self._orders.pop(order.client_order_id, None)
            raise

        self._trades[order.client_order_id] = trade
        ib_id = getattr(ib_order, "orderId", None)
        if ib_id is not None:
            self._to_ib[order.client_order_id] = ib_id
            self._from_ib[ib_id] = order.client_order_id

    def cancel_order(self, client_order_id: ClientOrderId) -> None:
        self._require_session("cancel_order")
        ib_order = self._orders.get(client_order_id)
        if ib_order is None:
            raise BrokerSeamError(f"unknown client_order_id {client_order_id}")
        self._ib.cancelOrder(ib_order)  # VERIFIED: takes the Order, not the id

    def flatten(self, symbol: Symbol | None = None) -> None:
        """GAP-1. Protective path — MUST NOT BLOCK, so this reads the mirror and fires
        immediately rather than querying positions first.

        §4 market-tradable guard is deliberately NOT implemented here: flatten fires
        market orders, and the decision to hold in HALT rather than fire into a shut
        market belongs to the Limiter, which owns session state. This library is
        'dumb hands' (§2) — it does not decide when it is safe to act.
        """
        self._require_session("flatten")
        targets = [symbol] if symbol else list(self._mirror.keys())
        failures: list[tuple[Symbol, str]] = []
        for sym in targets:
            pos = self._mirror.get(sym)
            if pos is None or pos.net_qty == 0:
                continue
            side = Side.SELL if pos.net_qty > 0 else Side.BUY
            try:
                self.place_order(
                    NeutralOrder(
                        client_order_id=f"flat-{sym}-{next(self._flatten_seq)}",
                        symbol=sym,
                        side=side,
                        qty=abs(pos.net_qty),
                        order_type=OrderType.MARKET,
                        tif=TimeInForce.IOC,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # DEFECT FIX: one symbol failing must not abandon the rest. This is the
                # PROTECTIVE path — silently stopping after symbol 1 of 3 would leave
                # real positions open while the caller believes a flatten was issued.
                # Collect and continue, then raise once with the full picture.
                log.error("flatten failed for %s: %s", sym, exc)
                failures.append((sym, str(exc)))
        if failures:
            raise BrokerSeamError(
                "flatten incomplete — these symbols were NOT flattened: "
                + "; ".join(f"{s}: {e}" for s, e in failures)
            )

    async def query_positions(self) -> list[Position]:
        """§4 cold-start ground truth. At cold start the broker's answer IS the record."""
        self._require_session("query_positions")
        # DEFECT FIX (race): the earlier version assigned the mirror wholesale from the
        # await's result. A fill landing between the request and the assignment would be
        # silently erased — on the protective path, that means flatten could later read
        # a mirror that has forgotten a real position. Snapshot the exec-dedupe set
        # across the await; if any fill arrived meanwhile, keep the event-derived mirror
        # (fills are the §4 primary source) and treat the venue snapshot as corroboration.
        execs_before = len(self._seen_execs)
        raw = await self._ib.reqPositionsAsync()
        out: list[Position] = []
        for p in raw:
            # VERIFIED Position._fields == ('account','contract','position','avgCost')
            qty = int(p.position)
            # DEFECT FIX (ARC 015 §2a): IBKR reports a position=0 row for a symbol that
            # was traded and is now flat — it is a "no longer held" notification, not a
            # holding. The mirror always filtered these; the RETURNED LIST did not, so
            # the two disagreed about the same account. This call is §4 cold-start ground
            # truth, and the natural caller idiom is `if await broker.query_positions():
            # halt()` — a truthiness test that a zero-qty row silently satisfies. A
            # phantom position at cold start either blocks a legitimate start or triggers
            # a flatten of nothing. Filter at the ONE place both consumers are built
            # from, so no future edit can reintroduce the divergence.
            if qty == 0:
                continue
            sym = self._symbol_for(p.contract)
            out.append(
                Position(sym, qty, self._avg_price_from_cost(p.contract, p.avgCost))
            )

        if len(self._seen_execs) == execs_before:
            self._mirror = {p.symbol: p for p in out}
        else:
            log.warning(
                "fills landed during query_positions — keeping event-derived mirror; "
                "venue snapshot returned %d positions",
                len(out),
            )
        return out

    async def query_balance(self) -> Balance:
        self._require_session("query_balance")
        values = await self._ib.accountSummaryAsync()
        tags = {v.tag: v.value for v in values}

        def num(tag: str) -> float:
            try:
                return float(tags.get(tag, 0.0))
            except TypeError, ValueError:
                return 0.0

        return Balance(
            cash=num("TotalCashValue"),
            net_liquidation=num("NetLiquidation"),
            maint_margin=num("MaintMarginReq"),
            init_margin=num("FullInitMarginReq"),
            venue_seq_ts=time.time(),
            ts_is_venue_sourced=False,  # GAP-2: honest, not fabricated
        )

    def query_order_status(self, client_order_id: ClientOrderId) -> OrderStatus:
        """§4: resolve pending timeouts. NEVER auto-resend."""
        self._require_session("query_order_status")
        trade = self._trades.get(client_order_id)
        if trade is None:
            return OrderStatus(
                client_order_id, terminal=False, state="unknown", cumulative_qty=0
            )
        st = trade.orderStatus
        return OrderStatus(
            client_order_id=client_order_id,
            terminal=st.status in IB_DONE_STATES,
            state=self._neutral_state(st.status),
            cumulative_qty=int(st.filled),
        )

    async def get_margin(self, symbol: Symbol) -> float:
        """Poll fallback (the only path on IBKR — see GAP-3).

        MEASURED TRAP (ARC 012): the SYNC ib.whatIfOrder() returns an empty OrderState
        with initMarginChange=None because its internal wait expires before IB answers.
        The asymmetry is what makes it dangerous — a REJECTED order leaves an err 201
        carrying the margin figure, so empty costs nothing; an AFFORDABLE order has no
        error, so empty reads as 'undetermined' with nothing to correct it. Use the
        async form under an explicit timeout.
        """
        self._require_session("get_margin")
        contract = self._contract_for(symbol)
        probe = self._build_ib_order(
            NeutralOrder(
                "whatif-probe", symbol, Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY
            )
        )
        try:
            state = await asyncio.wait_for(
                self._ib.whatIfOrderAsync(contract, probe),
                timeout=self._margin_timeout_s,
            )
        except TimeoutError as exc:
            raise BrokerSeamError(
                f"whatIfOrderAsync timed out after {self._margin_timeout_s}s for {symbol} — "
                "CANNOT MEASURE, not zero margin"
            ) from exc

        raw = getattr(state, "initMarginChange", None)
        if raw is None or raw in ("", "1.7976931348623157E308"):
            # That sentinel is IBKR's double-max 'unset'. Treating it as a number would
            # silently produce an absurd margin.
            raise BrokerSeamError(
                f"whatIfOrder returned no initMarginChange for {symbol} — CANNOT MEASURE"
            )
        return abs(float(raw))

    def capabilities(self) -> BrokerCapabilities:
        return self.CAPABILITIES

    # ------------------------------------------------------------------ ib events

    def _ack_once(
        self, cid: ClientOrderId, status: AckStatus, reason: str | None = None
    ) -> bool:
        """Emit at most one ack per order. Returns True if this call emitted it.

        The single gate every ack path goes through — the venue's own PreSubmitted/
        Submitted, the errorEvent rejection, and the §2c synthesis all land here and
        share one dedupe set, so no two of them can both fire for the same order.
        """
        if cid in self._acked:
            return False
        self._acked.add(cid)
        self._sink.on_ack(cid, status, reason=reason)
        return True

    def _ensure_acked(self, cid: ClientOrderId, trigger: str) -> None:
        """Synthesise the missing ACCEPTED ack (ARC 015 §2c). No-op if already acked.

        THE RACE. _on_ib_order_status acks only on PreSubmitted/Submitted. A marketable
        order can go PendingSubmit -> Filled with neither state ever being emitted, which
        produces NO ACK AT ALL — and the Limiter, which treats the ack as the signal that
        an order became live, waits forever on an order that has already filled. Worse
        than waiting: it observes a FILL for an order it never saw accepted, a state its
        machine has no branch for.

        Live evidence is one sample, not a proof of impossibility: ARC 014 measured the
        venue emitting PreSubmitted then Filled 44 ms apart. 44 ms is the width of the
        window we happened to get, not a guarantee there is always one.

        THE GATE. Any event that PROVES the venue accepted the order — a fill, or a
        transition into a terminal state that implies it was live — synthesises the ack
        first, so the Limiter can never observe a fill or a cancel before the ack.
        Ordering, not just presence, is the guarantee: callers are entitled to assume
        acceptance precedes everything else about an order.

        DELIBERATELY NOT SYNTHESISED for 'Inactive'/'ValidationError'. Those are terminal
        WITHOUT acceptance — the order was refused — and IBKR delivers the reason on
        errorEvent, which raises a REJECTED ack through _on_ib_error. Synthesising
        ACCEPTED there would invent an acceptance that never happened, which is the
        opposite defect and a worse one. If the error has already landed, cid is in
        self._acked and this is a no-op anyway; the dedupe set is shared on purpose so
        the two paths cannot both fire.
        """
        emitted = self._ack_once(
            cid,
            AckStatus.ACCEPTED,
            reason=f"synthesised: {trigger} arrived with no prior ack",
        )
        if emitted:
            # Loud, because it means the venue never sent an acceptance we could observe
            # — worth seeing in the log even though the contract is now honoured.
            log.warning(
                "no venue ack seen for %s before %s — synthesised ACCEPTED (§2c)",
                cid,
                trigger,
            )

    def _on_ib_order_status(self, trade) -> None:
        """IBKR re-emits orderStatus on every change, so ack and cancel are deduped."""
        if not self._startup_complete:
            return  # ARC 015 §2b: startup replay of a previous session's orders
        ib_id = trade.order.orderId
        cid = self._from_ib.get(ib_id)
        if cid is None:
            return  # not ours (another clientId, or a manual TWS order)
        status = trade.orderStatus.status

        if status in IB_ACK_STATES:
            # A GENUINE venue acceptance. Emitted with no reason string, deliberately:
            # `reason` is the provenance channel, and marking a real ack "synthesised"
            # would destroy the very distinction §2c's synthesis needs to stay auditable.
            self._ack_once(cid, AckStatus.ACCEPTED)
        elif status == "Filled":
            # Terminal and unambiguously accepted. The fill event itself may arrive
            # before or after this one; whichever is first synthesises the ack.
            self._ensure_acked(cid, "Filled")
        elif status in ("Cancelled", "ApiCancelled"):
            # A cancel implies the order was live long enough to cancel.
            self._ensure_acked(cid, status)
            if cid not in self._cancelled:
                self._cancelled.add(cid)
                self._sink.on_cancel(cid, int(trade.orderStatus.filled))

    def _on_ib_exec_details(self, trade, fill) -> None:
        """§4 idempotent by (order_id, exec_id).

        VERIFIED Execution fields include execId and cumQty, so the contract's
        cumulative_qty maps directly — this is the cleanest mapping in the set.
        """
        if not self._startup_complete:
            # ARC 015 §2b: connectAsync's startup fetch replays HISTORICAL executions on
            # this same event. Dropping them here is the deliberate mechanism; previously
            # they were dropped only because the id map happened to be empty.
            return
        ib_id = fill.execution.orderId
        cid = self._from_ib.get(ib_id)
        if cid is None:
            return
        exec_id: ExecId = fill.execution.execId
        key = (cid, exec_id)
        if key in self._seen_execs:
            return  # duplicate or out-of-order execution report
        self._seen_execs.add(key)

        # ARC 015 §2c. A fill is proof the venue accepted the order, so if no ack has been
        # seen yet, raise it BEFORE on_fill. Placed after the idempotency check so a
        # replayed duplicate cannot re-trigger anything, and before EVERY on_fill path
        # below (including the no-local-record early return) so the ordering guarantee
        # holds on all of them.
        self._ensure_acked(cid, "fill")

        sym = self._symbol_for(fill.contract)
        shares = int(fill.execution.shares)
        price = float(fill.execution.price)
        cum = int(fill.execution.cumQty)

        # DEFECT FIX (direction provenance): the earlier version inferred direction from
        # OUR record of the order (self._neutral[cid].side), falling back to SELL when
        # the record was missing — which silently mis-signs any fill for an order we
        # didn't place in this session. VERIFIED: Execution carries its own `side`
        # ('BOT'/'SLD'), so take direction from the venue's own report of what happened
        # rather than from our belief about what we asked for. Falls back to our record
        # only if the venue field is absent.
        venue_side = getattr(fill.execution, "side", None)
        if venue_side in ("BOT", "SLD"):
            signed = shares if venue_side == "BOT" else -shares
        else:
            neutral = self._neutral.get(cid)
            if neutral is None:
                log.error(
                    "fill for %s has no venue side and no local record — mirror not updated",
                    cid,
                )
                self._sink.on_fill(cid, exec_id, sym, shares, price, cum)
                return
            signed = shares if neutral.side is Side.BUY else -shares

        prior = self._mirror.get(sym)
        new_qty = (prior.net_qty if prior else 0) + signed
        if new_qty == 0:
            self._mirror.pop(sym, None)
        else:
            self._mirror[sym] = Position(sym, new_qty, price)

        self._sink.on_fill(cid, exec_id, sym, shares, price, cum)

    def _on_ib_error(self, reqId, errorCode, errorString, contract=None) -> None:
        """Rejections arrive here, not on orderStatus — the two streams must be joined
        to produce one neutral ack. Connectivity codes are also here."""
        if errorCode == IB_ERR_CONN_LOST:
            self._sink.on_session(SessionState.DOWN, reason=f"1100 {errorString}")
            return
        if errorCode == IB_ERR_CONN_RESTORED_DATA_LOST:
            # Load-bearing: our mirror may have missed events. Surface the data loss so
            # the Limiter re-reconciles rather than trusting a stale mirror.
            self._sink.on_session(
                SessionState.UP, reason="1101 restored WITH DATA LOSS — reconcile"
            )
            return
        if errorCode == IB_ERR_CONN_RESTORED_DATA_OK:
            self._sink.on_session(SessionState.UP, reason="1102 restored, no data loss")
            return
        if errorCode in IB_INFO_CODES:
            return

        cid = self._from_ib.get(reqId)
        if cid is not None:
            # Same one-ack gate as the accept paths (§2c): whichever stream reaches an
            # order first owns its ack. A REJECTED here therefore blocks the synthesis of
            # a later ACCEPTED on an Inactive/Cancelled transition, and vice versa.
            self._ack_once(
                cid, AckStatus.REJECTED, reason=f"{errorCode}: {errorString}"
            )

    def _on_ib_position(self, position) -> None:
        sym = self._symbol_for(position.contract)
        qty = int(position.position)
        avg_price = self._avg_price_from_cost(position.contract, position.avgCost)
        if qty == 0:
            self._mirror.pop(sym, None)
        else:
            self._mirror[sym] = Position(sym, qty, avg_price)
        self._sink.on_position(sym, qty, avg_price)

    def _on_ib_account_value(self, value) -> None:
        """GAP-2: no venue timestamp exists on AccountValue, so on_balance is only
        emitted on tags that matter and is flagged non-venue-sourced."""
        if value.tag != "NetLiquidation":
            return
        try:
            netliq = float(value.value)
        except TypeError, ValueError:
            return
        self._sink.on_balance(
            Balance(
                cash=0.0,
                net_liquidation=netliq,
                maint_margin=0.0,
                init_margin=0.0,
                venue_seq_ts=time.time(),
                ts_is_venue_sourced=False,
            )
        )

    def _on_ib_disconnected(self) -> None:
        self._connected = False
        # An unrequested drop is a session boundary just as much as disconnect() is: the
        # next connect() will replay history, and the gate must already be shut when it
        # does. Closing it here means the gate is correct even if the reconnect is driven
        # by something that never called disconnect().
        self._startup_complete = False
        self._sink.on_session(SessionState.DOWN, reason="transport disconnected")

    # ------------------------------------------------------------------ helpers

    async def _rebuild_mirror(self) -> None:
        try:
            await self.query_positions()
        except Exception as exc:  # noqa: BLE001 — mirror rebuild must not kill connect
            log.warning("mirror rebuild failed on connect: %s", exc)

    def _contract_for(self, symbol: Symbol):
        if self._resolve_contract is None:
            raise SymbolNotResolved(f"no contract resolver configured for {symbol}")
        contract = self._resolve_contract(symbol)
        if contract is None:
            raise SymbolNotResolved(f"resolver returned nothing for {symbol}")
        return contract

    def _symbol_for(self, contract) -> Symbol:
        # str() rather than a bare getattr chain: Symbol is a neutral str id, and a
        # vendor field of some other type reaching the mirror as a dict key would make
        # two spellings of the same symbol look like two positions.
        return str(
            getattr(contract, "localSymbol", None) or getattr(contract, "symbol", "?")
        )

    @staticmethod
    def _avg_price_from_cost(contract, avg_cost: float) -> float:
        """MEASURED (ARC 014, live MESU6): IBKR's Position.avgCost for a FUTURE is
        NOTIONAL — price x multiplier — while Execution.price is per-unit. A long 1
        MES filled at 7782.50 reported avgCost 38912.50, exactly 5x.

        Both used to be written straight into Position.avg_price, so the field carried
        two incompatible units depending on which event landed last. Normalise every
        venue-sourced cost to a per-unit price here so the field has ONE meaning.

        RESIDUAL, also measured live: avgCost is COMMISSION-INCLUSIVE while
        Execution.price is raw. The same fill reported price 7773.50 and avgCost/mult
        7773.622 — a 0.122 gap that is exactly the 0.61 commission divided by the
        multiplier. So avg_price still varies by provenance, but by a fraction of a tick
        rather than by 5x. Anything needing raw-vs-net execution price must read the
        Execution, not the mirror.
        """
        try:
            mult = float(getattr(contract, "multiplier", "") or 1)
        except TypeError, ValueError:
            mult = 1.0
        if mult <= 0:
            mult = 1.0
        return float(avg_cost) / mult

    def _build_ib_order(self, order: NeutralOrder):
        from ib_async import (  # pylint: disable=import-error
            LimitOrder,
            MarketOrder,
        )

        action = "BUY" if order.side is Side.BUY else "SELL"
        tif = "IOC" if order.tif is TimeInForce.IOC else "DAY"
        if order.order_type is OrderType.MARKET:
            o = MarketOrder(action, order.qty)
        else:
            o = LimitOrder(action, order.qty, order.limit_price)
        o.tif = tif
        return o

    @staticmethod
    def _neutral_state(ib_status: str) -> str:
        if ib_status == "Filled":
            return "filled"
        if ib_status in ("Cancelled", "ApiCancelled"):
            return "cancelled"
        if ib_status in ("Inactive", "ValidationError"):
            return "rejected"
        if ib_status in IB_ACTIVE_STATES:
            return "working"
        return "unknown"
