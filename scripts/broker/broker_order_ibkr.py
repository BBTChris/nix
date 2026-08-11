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

NON-BLOCKING IS NOW MEASURED, NOT INFERRED (ARC 019 A1). The paragraph above asserted the
send path is non-blocking "because ib.placeOrder and ib.cancelOrder are themselves
non-blocking calls". That was a reading of the vendor's source, not an observation, and
several prior arc briefs went on to ASSUME a sender thread was therefore owed. Nobody had
measured either claim. ARC 019 did.

  METHOD. All four sync send verbs driven against a real `ib_async.IB` whose
  `Client.conn` held a real asyncio transport over a real loopback TCP socket, under four
  socket conditions. 5 reps per cell, `time.perf_counter()` around the verb call only.
  Wall-clock seconds to return, worst observed of 5:

    verb           healthy      silent    full-buf   vanished
    place_order   0.001177    0.001232    0.000834   0.000971
    cancel_order  0.000360    0.000366    0.000275   0.000291
    flatten (N=5) 0.002939    0.002747    0.002617   0.003295
    disconnect    0.000383    0.000436    0.000140   0.000161

  Worst cell in the whole matrix: 0.003295 s. NOTHING BLOCKS. The condition that could
  have blocked — a full send buffer, verified saturated by asserting asyncio had begun
  buffering in userspace — is the FASTEST column, not the slowest.

  DECISION: BUILD NOTHING. No queue, no sender thread. §2A's architecture diagram names a
  "non-blocking, low-priority sender thread" (spec lines 43, 148) and one is not built
  here, because the property that thread exists to provide is already provided twice over
  by machinery this adapter sits on top of: asyncio's transport buffers a write the kernel
  cannot take, and `ib_async.Client.sendMsg` holds its own `_msgQ` in front of that for
  request pacing. A Nix-side sender thread would be a third queue in the same pipe.

  WHAT "NEVER BLOCKS" ACTUALLY COSTS, measured rather than glossed: 200 `place_order`
  calls into an already-full pipe returned in 0.032 s TOTAL (max single call 0.002384 s)
  and left 155 messages in ib_async's queue, 10204 B in asyncio's buffer, and ZERO bytes
  delivered to the peer. So the send path does not block — it absorbs. An order accepted
  by this process is not thereby an order that reached the venue, and no send verb can
  tell the caller which it was. That is not a defect to fix here: §4 resolves it with the
  pending-timeout state machine and `query_order_status`, both of which belong to the
  Limiter, and the one thing this adapter must never do about it is resend.

  NOT V11. §13 objective 11 asks whether the stop loop keeps protecting while the send
  path is stalled. There is no stop loop until R2, so V11 stays KNOWN-RED. What is
  measured above is send-verb behaviour under socket stress against a declared stand-in.

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

  CORRECTION (ARC 020). The last sentence above is STALE and is kept rather than rewritten,
  because a policy paragraph that quietly updates its own factual claim is exactly the shape
  ARC 014 caught in the async paragraph higher up. ARC 017 added ONE bare `create_task`, in
  `_on_data_loss_restore`, with its own justification written at the site: a sync vendor
  callback cannot own a TaskGroup scope, so the policy's actual requirement (no silent
  death) is met by a strong reference plus a done-callback that logs. That remains the only
  task this file creates. ARC 020 added no new ones — every mechanism it landed (terminal
  retention, the flatten idempotency window, the deferred-publish session check) is
  evaluated LAZILY, at a call the caller already made, precisely so that none of them needs
  a timer.

WHAT ARC 020 CHANGED, in one place so a reader is not made to reconstruct it (details are at
each site):

  A1 · SESSION-SCOPED PER-ORDER STATE (D1.24). Every per-order map is cleared at BOTH ends
    of a session boundary. An order that was TERMINAL is discarded and its neutral id is
    released; one that was IN FLIGHT is TOMBSTONED, and `query_order_status` reports it
    `indeterminate` — §4's third outcome, which this adapter previously could not reach.
    Within a session, terminal orders are released after `terminal_order_retention_ms`.
  A2 · A CANCELLED `connect()` UNWINDS (D1.23). `except BaseException` — the class
    `CancelledError` actually belongs to — plus a re-raise. The adapter refuses orders
    afterwards, observably.
  A3 · ONE SESSION-EVENT EMISSION SITE (D1.25). `_publish_session` is the choke point; a
    deferred publish re-checks the SESSION EPOCH it was scheduled in, not merely liveness.
  A4 · THE STARTUP GATE DISCRIMINATES BY OWNERSHIP (D1.27(b), operator ruling). Sound only
    because A1 clears the registry at every boundary — see `_startup_admits`.
  A5 · READ-VS-READ ORDERING GUARD ON THE MIRROR (D1.26). A monotonic sequence per read;
    no lock, because a lock would put waiting in front of the protective path's input.
  A6 · FLATTEN IDEMPOTENCY WINDOW + ATTEMPT RECORD (D1.27(a)/D1.28, operator ruling). The
    window is a §12A-derived tunable in `risks/broker_order.config.json`, never a literal.
  A7 · SEND BACKLOG IS OBSERVABLE (D1.22, observability half ONLY). See `send_backlog`.

  WHAT ARC 020 DID NOT BUILD, and it is deliberate in every case: the Limiter's
  pending-timeout state machine, any consumer of the flatten attempt record, any
  reconciliation of intent against venue outcome, and any bounded-queue policy. All four
  are R2's, and three of them are the reason D1.22 says the repair is never a resend.
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
#   too-many-lines
#       Crossed 1000 in ARC 017 and the overage is entirely PROSE. Every design
#       decision in this file is a claim about behaviour a reader has to be able
#       to check — the §2b joint-sufficiency framing was wrong for two arcs
#       precisely because nobody could check it against a shorter note. Deleting
#       the reasoning to satisfy a line count would trade the one defence this
#       file has against its own worst failure mode for a metric.
# pylint: disable=invalid-name,missing-function-docstring,broad-exception-caught
# pylint: disable=unused-argument,too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-locals,import-outside-toplevel,too-many-lines
import asyncio
import itertools
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from broker_order_config import BrokerOrderConfig, load_broker_order_config
from broker_seam import (
    AckStatus,
    Balance,
    BrokerCapabilities,
    BrokerNotConnected,
    BrokerSeamError,
    ClientOrderId,
    ExecId,
    FlattenAttempt,
    FlattenIntent,
    FlattenSuppression,
    NeutralOrder,
    OrderEventSink,
    OrderStatus,
    OrderType,
    Position,
    RejectCategory,
    SendBacklog,
    SessionState,
    Side,
    Symbol,
    SymbolNotResolved,
    TimeInForce,
    ack_category_violation,
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

# ---------------------------------------------------------------------------
# REJECTION TAXONOMY — the vendor half (ARC 018, D1.18)
#
# This is the ONLY place an IBKR error code is allowed to mean something. §2A: "Vendor
# specifics ... live BELOW this line and never leak above it. All identifiers are
# vendor-neutral; the adapter maps them to venue IDs internally." Mapping venue codes to
# a neutral fact is precisely the adapter's job; what invariant 2 forbids is the code
# itself travelling upward, which after this arc it no longer does.
#
# EVIDENCE-GATED BY CONSTRUCTION. Every code in IB_REJECT_RULES must also appear in
# IB_REJECT_EVIDENCE with a citation to something measured on this system. A test asserts
# that (test_broker_order.py), so a mapping cannot be added from memory of IBKR's
# published error list — this project's rule is that a declaration is not evidence.
# AS OF ARC 018 THE TABLE HAS EXACTLY ONE ENTRY. Three of RejectCategory's four members
# have no mapped code at all, because only one order-rejection code has ever been measured
# here. Everything else lands on UNKNOWN. That is the finding, not a placeholder.
# ---------------------------------------------------------------------------

IB_REJECT_EVIDENCE: dict[int, str] = {
    201: (
        "Measured live on clientId=905. ARC 010 established a whatIf order reaching "
        "IBKR's margin engine returns err 201 (sessions/SESSION.md:457, "
        "docs/CHECK-DEBT.md D1.11). ARC 012 measured the rejection text carrying the "
        "margin figure — 'NET LIQ [20299.32] MUST EXCEED THE MARGIN REQ [35035.87]' — "
        "and read the requirement back out of it (sessions/SESSION.md:569, :594; "
        "docs/dev_and_services_plan.md:157 'contracts affordable 0 — rejected, err 201'). "
        "Reproduced offline in test_broker_order.py::_section_rejection_paths."
    ),
}

# (errorCode, required lowercase substrings of errorString, category).
#
# WHY THE TEXT IS PART OF THE RULE, AND WHY THAT IS NOT §7.4's DEFECT. IBKR's 201 is a
# WRAPPER — literally "Order rejected - reason:<text>" — so the code alone does not name a
# cause. Keying INSUFFICIENT_MARGIN on 201 by itself would make every 201, whatever its
# text, read as a money problem: an unknown wearing a known's clothes, the exact failure
# the UNKNOWN floor exists to prevent. So the substrings are load-bearing.
#
# debug.md §7.4 forbids anchoring on a literal that can move — and it is a rule about
# CONSUMERS, above the seam, where venue prose is not supposed to be visible at all. Here
# the anchor sits below the seam in the one component whose job is to know venue
# spellings, and its drift behaviour is safe by construction: if IBKR rewords the message
# the rule stops matching and the result is UNKNOWN. It degrades to "we cannot tell",
# never to a confident wrong answer. Both substrings are taken from the measured sample
# cited above; nothing here is generalised from IBKR documentation.
IB_REJECT_RULES: tuple[tuple[int, tuple[str, ...], RejectCategory], ...] = (
    (201, ("margin", "net liq"), RejectCategory.INSUFFICIENT_MARGIN),
)


#: Neutral states that mean "this order can never change again". §4's pending-timeout
#: query resolves to confirmed / cancelled / indeterminate; the first two are these.
TERMINAL_NEUTRAL_STATES = frozenset({"filled", "cancelled", "rejected"})


@dataclass(frozen=True)
class _Tombstone:
    """What survives a session boundary for an order whose fate the boundary made unknowable.

    ARC 020 A1 (D1.24). This is the ANSWER to "what happens to state for orders that were
    genuinely in flight when the session dropped", and it is deliberately NOT the order's
    state — it is the smallest record that lets `query_order_status` say `indeterminate`
    without saying anything it cannot back.

    WHAT IT DOES NOT HOLD, and why each absence is load-bearing:
      - no ib `Order` object. That object carries `orderId`, which is what `cancel_order`
        puts on the wire, and the venue re-issues that integer to a DIFFERENT order in the
        next session. Keeping it is exactly D1.24's measured defect.
      - no ib `Trade`. Its `orderStatus` is a snapshot of a session that no longer exists;
        returning it verbatim is how a dead order reported `working` forever.
      - no vendor id mapping. A tombstoned order is unaddressable by construction.
    """

    client_order_id: ClientOrderId
    last_known_state: str
    """The neutral state as of the last event this adapter saw, for context only. It is
    NOT what `query_order_status` returns — the answer is always `indeterminate`, because
    what was true when the socket died is not evidence about what is true now."""
    cumulative_qty: int
    """Cumulative filled qty this adapter had OBSERVED. A floor on what was done, never a
    claim that nothing more was."""
    session_seq: int
    """Which session it belonged to. Lets a consumer tell one dead session's orders from
    another's without this adapter having to keep either session."""


def ib_reject_category(error_code: int, error_string: str) -> RejectCategory:
    """Map an IBKR (code, text) rejection onto the neutral taxonomy. First rule wins.

    Anything unmatched is UNKNOWN — never the nearest plausible member. The function is
    module-level and pure so a test can drive it over a code set directly, rather than
    only through the event path.
    """
    haystack = (error_string or "").lower()
    for code, needles, category in IB_REJECT_RULES:
        if error_code == code and all(n in haystack for n in needles):
            return category
    return RejectCategory.UNKNOWN


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
        config: BrokerOrderConfig | None = None,
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
        # §12A/§12.11: boot-loaded, restart-only. Injected in tests, read from
        # risks/broker_order.config.json otherwise — see broker_order_config.py for why
        # there is no default-on-missing path.
        self._cfg = config if config is not None else load_broker_order_config()

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
        # True while the mirror is known to be possibly-behind the venue: set on a
        # data-loss restore, cleared when the re-read comes back. Observable state, not a
        # log line, because "is the protective path's input trustworthy" is a fact a test
        # and an operator both need to read (ARC 017 A1).
        #
        # ARC 018 B4 — NOTE FOR R2 (the Limiter). Re-confirmed observable and correct at
        # all three write sites (init False; True the moment a data-loss restore arrives;
        # `not rebuilt` after the re-read resolves), and read by three assertions in
        # test_broker_order.py. It still has NO consumer, because the Limiter does not
        # exist yet; this records what that consumer will be REQUIRED to do, written now
        # rather than reconstructed later. `flatten()` is §2A's protective path and reads
        # this mirror instead of the wire, so §14's "the exit path has zero wire
        # dependency" is only as strong as the mirror behind it — `_mirror_stale is True`
        # means the sizing input for a protective flatten may be missing a position, or
        # holding one already closed. The consumer is therefore required to (1) treat True
        # as a HALT-class condition for NEW entries — it is §4's uncertainty, and every
        # uncertainty resolves toward flat; (2) NOT treat True as a reason to skip a
        # protective flatten — firing against a suspect mirror still beats not firing, and
        # §4's indeterminate path already reconciles against broker truth afterward and
        # publishes the CONFIRMED state; (3) pair it with the `UP_DATA_LOSS` session event
        # rather than substituting for it — the session member is the edge, this flag is
        # the level, and only the level survives a missed event.
        # THE LATCH (D1.20) IS FIXED — ARC 019 A3. ARC 018 recorded it here as a known gap:
        # `connect()` discarded `_rebuild_mirror()`'s verdict and never wrote this flag, so
        # a re-read that failed once stayed True across a full reconnect that DID rebuild.
        # Safe direction, but a one-way door. `connect()` now derives both this flag and
        # the published session state from the verdict — see the comment there.
        #
        # WHAT REMAINS OPEN IS THE CONSUMER HALF, and it stays named rather than built: the
        # Limiter does not exist until R2, and building a consumer for a flag nobody reads
        # would be inventing the requirement rather than meeting it. The obligations, as
        # written in ARC 018 while the reasoning was fresh and re-confirmed in ARC 019, are
        # that a consumer must (1) treat True as a HALT-class condition for NEW entries —
        # it is §4's uncertainty, and every uncertainty resolves toward flat; (2) NOT treat
        # True as a reason to skip a protective flatten — firing against a suspect mirror
        # still beats not firing, and §4's indeterminate path reconciles against broker
        # truth afterward; (3) pair it with the `UP_DATA_LOSS` session event rather than
        # substituting for it — the session member is the edge, this flag is the level, and
        # only the level survives a missed event.
        self._mirror_stale = False
        # Monotonic count of rebuild ATTEMPTS. Exists so "the mirror was re-read" is
        # directly measurable rather than inferred from the mirror's contents — which can
        # be identical before and after and prove nothing (the empty->empty trap).
        self._mirror_rebuilds = 0
        # Strong refs to in-flight reconcile tasks: asyncio only holds a weak reference,
        # so an untracked task can be collected mid-await and the rebuild simply never
        # happens. See _on_data_loss_restore.
        self._reconcile_tasks: set = set()

        # --- ack dedupe: IBKR re-emits orderStatus on every change ---
        self._acked: set[ClientOrderId] = set()
        self._cancelled: set[ClientOrderId] = set()

        # --- session-boundary discipline (ARC 020 A1, D1.24) ---------------------------
        # THE RULE, stated once here and enforced by _clear_session_state():
        #   ALL per-order state is SESSION-SCOPED. It is created inside a session and it
        #   dies with that session. Nothing per-order crosses a boundary except a
        #   _Tombstone, which is deliberately not per-order STATE — it is a record that
        #   per-order state used to exist and its fate is unknowable.
        #
        # WHERE THE CLEARING HAPPENS — BOTH ENDS, and the asymmetry is the point.
        #   TEARDOWN (disconnect / disconnectedEvent / an abandoned connect) is where the
        #     state is RELEASED, because that is the instant it stops describing anything.
        #     Waiting for the next connect() would leave a live `Order` object addressable
        #     for an unbounded interval — the Gateway restarts at 03:00 and nothing
        #     guarantees a reconnect follows promptly.
        #   CONNECT is where it is cleared AGAIN, before `connectAsync`, and that
        #     repetition is not redundancy: the venue's startup replay is dispatched from
        #     INSIDE connectAsync, so the map must be provably empty at that moment, and a
        #     process that was constructed and connected without ever having disconnected
        #     has no teardown to have cleared it. Belt and braces on the one boundary where
        #     a stale id becomes a live foreign order's id.
        # A single-ended design fails on whichever end it omits, so neither is omitted.
        self._session_seq = 0
        """Monotonic session counter. Incremented on every boundary in BOTH directions, so
        it changes on teardown as well as on establishment. This is the token a deferred
        publish re-checks (ARC 020 A3) — a bare `_connected` bool cannot tell 'still the
        session I was scheduled in' from 'a different session that happens to also be up'."""
        self._tombstones: dict[ClientOrderId, _Tombstone] = {}

        # --- terminal-order retention (ARC 020 A1(ii), D1.24) --------------------------
        # Per-order state for a TERMINAL order is released after
        # `terminal_order_retention_ms`. Pruning is LAZY and amortised O(1): terminal
        # orders are appended to a deque in terminal order — which is monotonic in time —
        # so expiry is a popleft-while-expired, never a scan. No timer, no task: a
        # background timer on the order path is the thing the module's concurrency policy
        # exists to avoid, and a sweep that only runs when the module is already doing
        # order work cannot fall behind the thing it is bounding.
        self._retire_queue: deque[tuple[float, ClientOrderId]] = deque()
        self._terminal: set[ClientOrderId] = set()

        # --- flatten idempotency + attempt record (ARC 020 A6, D1.27a / D1.28) ---------
        self._flatten_intent: dict[Symbol, tuple[ClientOrderId, float, int]] = {}
        """symbol -> (client_order_id, monotonic_ts, attempt_seq) of the last flatten leg
        actually emitted for that symbol. Bounded by the number of symbols, which the
        mission scope caps at 1-5."""
        self._flatten_attempts: deque[FlattenAttempt] = deque(
            maxlen=self._cfg.flatten_attempt_log_depth
        )
        self._flatten_attempt_seq = itertools.count(1)

        # --- read-vs-read ordering guard on the mirror (ARC 020 A5, D1.26) -------------
        self._reqpos_seq = itertools.count(1)
        self._mirror_applied_seq = 0
        """The sequence number of the newest `query_positions` that has RESOLVED. A read
        that resolves with a lower number is stale and must not touch `_mirror`."""

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

        # --- session-event emission (ARC 020 A2/A3) ------------------------------------
        self._last_published_session: SessionState | None = None
        """The last state `_publish_session` actually emitted. `None` == nothing has ever
        been published, which is NOT the same as DOWN: §2A defines `on_session` as
        connectivity TRANSITIONS, and a first-ever DOWN is not a transition."""
        self._prior_from_ib: dict[int, ClientOrderId] = {}
        """The PREVIOUS session's vendor-id map, retained for DIAGNOSTICS ONLY.

        Read by exactly one place — `_log_gated_drop` — so that an event arriving after a
        teardown can still be NAMED in the log rather than dropped anonymously. It is
        never consulted by the admission gate, never by `cancel_order`, and never by any
        handler that emits. That separation is the whole point: D1.24's defect was a stale
        mapping being USED, and the cure is not to forget the mapping but to make the copy
        that survives structurally incapable of addressing anything."""

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

        At the source: fetchFields asks for POSITIONS + ACCOUNT_UPDATES +
        SUB_ACCOUNT_UPDATES and nothing else, so neither the execution replay nor the
        order replay is requested in the first place. Nothing in this adapter reads the
        order fetches — verified in ARC 017 by deriving every `self._ib.<attr>` the file
        touches from its AST: connectAsync, placeOrder, cancelOrder, reqPositionsAsync,
        accountSummaryAsync, whatIfOrderAsync, disconnect. No `ib.orders()`, `ib.trades()`,
        `ib.fills()`, `ib.executions()`, `reqAllOpenOrders` or `reqCompletedOrders`
        anywhere. `query_order_status` reads the `Trade` that `placeOrder` handed back, not
        a fetched one, so dropping the order fetches costs this adapter nothing.

        WHEN THE GATE OPENS — CORRECTED IN ARC 017. It opens AFTER `_rebuild_mirror()`
        completes, not before it.

          The previous ordering set `_startup_complete = True` the instant connectAsync
          returned and then awaited the rebuild, so the entire rebuild ran with the gate
          OPEN while `_connected` was also already True. All three conditions a phantom
          fill needs held simultaneously across a real loop yield, and there is no mutual
          exclusion of any kind in this adapter. A concurrently-scheduled `place_order`
          could populate `_from_ib` inside that window, and because IBKR order ids RESET
          across sessions, a replayed HISTORICAL report could carry an id that now matched
          a live order — a phantom fill delivered to the Limiter.

          The old ordering was justified on the grounds that a GENUINE fill could land
          during the rebuild and would be dropped. That argument does not survive being
          checked: `_from_ib` is cleared at the top of this method, so at the moment the
          rebuild runs the adapter knows of NO live order at all. The only way one can
          exist is a caller placing an order concurrently with connect() — which §4's
          cold-start ordering forbids, since the position set is not yet reconciled. So
          the gate now closes a window that was reachable and forfeits nothing that was.
          And should a caller do it anyway, the drop is LOUD rather than silent: both
          gated handlers log at error level when the event they refuse carries an id this
          adapter recognises. Startup replay never trips that — `_from_ib` is empty.

        RELATIONSHIP TO fetchFields — the ARC 016 "joint sufficiency" framing was WRONG
        and is corrected here. ARC 016 asserted the gate and the fetchFields narrowing
        were jointly sufficient and individually insufficient. Two things were wrong with
        that:

          1. It claimed the gate did not cover fetchFields, and gave the gate's premature
             opening as the reason. That reason is now gone — the gate is closed for the
             whole of connect(), so it covers any startup replay dispatched before
             connectAsync returns, whatever ib_async decides to fetch.
          2. Its symmetry claim was never true even in ARC 016. It was argued for
             EXECUTIONS only. ORDERS_COMPLETE replays completed orders onto
             orderStatusEvent -> _on_ib_order_status, whose Filled and Cancelled branches
             reach `_ensure_acked` and `on_cancel` — gate-covered, and NOT covered by a
             narrowing that only dropped EXECUTIONS. The order half of the surface was
             asserted to be jointly protected while only one of the two mechanisms
             actually touched it.

        The honest statement is asymmetric, so state it asymmetrically: the GATE is the
        mechanism of record — venue-agnostic, scoped to the call, re-arming free on every
        reconnect, and covering executions and order statuses alike. The fetchFields
        narrowing is DEFENCE IN DEPTH at the source: it stops Nix asking for data it would
        only have to discard, so a future regression in the gate has less to catch. It is
        not a substitute for the gate and the gate is not a reason to widen it back.

        Position and account-value events are NOT gated: startup position snapshots are
        exactly what the mirror wants, and they carry no order identity to confuse.
        """
        if self._ib is None:
            raise BrokerSeamError("no IB instance injected")

        self._startup_complete = False
        # Session boundary invalidates every IBKR-side id. Cleared BEFORE connectAsync,
        # not after: the venue's startup replay arrives DURING connectAsync, and a map
        # still holding last session's ids is exactly what would let a replayed event be
        # mistaken for one of ours.
        #
        # ARC 020 A1/A4 — THIS ORDERING IS NOW LOad-BEARING TWICE OVER, and the second
        # reason is what makes A4's ownership gate safe. Because `_from_ib` is empty when
        # `connectAsync` runs, and because the venue's replay is dispatched from INSIDE
        # `connectAsync`, every id that can be in `_from_ib` during the startup window was
        # minted by a `place_order` in THIS session, AFTER the replay had already been
        # dispatched. So "the id is in the current registry" is not merely evidence of
        # ownership — in this window it is proof of it, and the ARC 017 collision (a
        # replayed historical report carrying an id that now matches a live order) is
        # unreachable rather than merely unlikely. See `_startup_admits`.
        self._clear_session_state("connect")

        self._wire_events()
        try:
            await self._ib.connectAsync(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                timeout=10,
                fetchFields=self._startup_fetch_fields(),
            )
            # _connected must be True here and not later: _rebuild_mirror() goes through
            # query_positions(), which calls _require_session(). The gate is a SEPARATE
            # flag precisely so these two can open at different moments.
            self._connected = True
            rebuilt = await self._rebuild_mirror()
        except BaseException as exc:
            # ARC 020 A2 — D1.23. BaseException, NOT Exception, and the difference is the
            # whole defect: `asyncio.CancelledError` derives from BaseException, so every
            # `except Exception` in this file misses it. Any caller bounding this verb with
            # `asyncio.wait_for` — the ordinary way to bound a call the docstring above
            # describes as "allowed to take as long as the venue takes" — cancels it, and
            # before this arc NOTHING unwound `_connected`. Measured blast radius: a
            # subsequent `place_order` SUCCEEDED and reached the venue while the startup
            # gate stayed shut, so every ack and every fill for it was discarded, and no
            # `on_session` had ever been published. The order path was live and mute.
            #
            # AND IT IS RE-RAISED. Swallowing a CancelledError breaks task-cancellation
            # semantics — the awaiting task would never learn it was cancelled and
            # `wait_for` would return normally from a call that did not complete. That is a
            # different defect and a worse one, so the handler unwinds and re-raises,
            # touching neither the exception nor its traceback.
            self._abandon_session(exc)
            raise

        # ARC 017 A3. The gate stays CLOSED across the rebuild — see WHEN THE GATE OPENS.
        #
        # ARC 019 A3/A4 — THE VERDICT IS HONOURED. Before this arc `connect()` discarded
        # `_rebuild_mirror()`'s return value entirely, which produced two defects at once:
        #
        #   D1.20, the LATCH. `_mirror_stale` was never written here, so a re-read that
        #     failed once stayed True across a full reconnect that DID rebuild
        #     successfully. It failed toward "suspect" — the safe direction — but it was a
        #     ONE-WAY DOOR: a consumer gating new entries on it would never resume trading.
        #
        #   The louder half: a rebuild that FAILED still published plain `SessionState.UP`.
        #     That is the adapter reporting a healthy session over a mirror it did not
        #     rebuild, on the cold-start path §4 designates as ground truth — the fail-OPEN
        #     direction, and the exact question ARC 019 A4 asked of every UP emission.
        #
        # Both are the same missing assignment. The state published is now derived from the
        # verdict rather than asserted independently of it, and `UP_DATA_LOSS` is reused
        # rather than invented: ARC 017 built it for precisely this fact — "the session
        # exists, our view of the account may have gaps." `state.is_up` stays True, so a
        # consumer asking "is the session usable" is unaffected; `state.data_loss` becomes
        # True, so a consumer asking "must I reconcile" is told the truth.
        #
        # THE RESULTING INVARIANT, asserted mechanically over every emission site in
        # test_broker_order.py: plain `SessionState.UP` is published ONLY while
        # `_mirror_stale` is False. There is no path to a clean UP over a suspect mirror.
        self._mirror_stale = not rebuilt
        self._startup_complete = True
        if rebuilt:
            self._publish_session(SessionState.UP)
        else:
            self._publish_session(
                SessionState.UP_DATA_LOSS,
                reason=(
                    "session established but the cold-start position re-read FAILED — "
                    "mirror suspect"
                ),
            )

    @staticmethod
    def _startup_fetch_fields():
        """Ask the venue for POSITIONS + ACCOUNT_UPDATES + SUB_ACCOUNT_UPDATES, and
        nothing else. Operator-ratified in ARC 017.

        BUILT UP FROM THE MEMBERS WE WANT, not subtracted from StartupFetchALL. Subtraction
        is anchored to a value that moves: whatever a future ib_async adds to ALL arrives
        switched ON, and the only defence would be someone noticing. Naming the three
        members means a new fetch source arrives OFF and has to be argued for. That is the
        same reasoning as debug.md §7.4 — never anchor to something that moves — applied
        to a vendor's enum instead of to a document.

        WHAT WAS DROPPED AND WHY IT COSTS NOTHING:
          EXECUTIONS       replays the account's historical fills onto execDetailsEvent —
                           straight into the live fill handler. Nothing here reads
                           ib.fills()/ib.executions(); the adapter keeps its own
                           (order_id, exec_id) ledger.
          ORDERS_OPEN      \\ replay completed/open orders onto orderStatusEvent, whose
          ORDERS_COMPLETE  / Filled and Cancelled branches reach _ensure_acked and
                           on_cancel. Nothing here reads ib.orders()/ib.trades() or calls
                           reqAllOpenOrders/reqCompletedOrders — verified in ARC 017 by
                           deriving every self._ib attribute from this file's AST.
                           `query_order_status` reads the Trade placeOrder returned.

        This is DEFENCE IN DEPTH, not half of a joint guarantee. ARC 016's "jointly
        sufficient, individually insufficient" framing is corrected in connect(): the gate
        is now closed for the whole of connect() and is the mechanism of record. This
        narrowing means Nix does not ask for data it would only discard. Widening it back
        does not become safe just because the gate exists.

        Imported lazily and by name so that if ib_async ever renames or removes a flag the
        failure is a loud ImportError at connect time, not a silently-restored replay.
        """
        from ib_async.ib import StartupFetch  # pylint: disable=import-error

        return (
            StartupFetch.POSITIONS
            | StartupFetch.ACCOUNT_UPDATES
            | StartupFetch.SUB_ACCOUNT_UPDATES
        )

    # ---------------------------------------------- session-scoped state (ARC 020 A1)

    def _clear_session_state(self, boundary: str) -> None:
        """Release EVERY per-order map, leaving a tombstone for each order still in flight.

        ARC 020 A1 — D1.24, and this is the half that stops a cancel putting a live foreign
        order's `orderId` on the wire. Before this arc `connect()` cleared `_to_ib`,
        `_from_ib`, `_acked` and `_cancelled` — and not `_orders`, `_trades`, `_neutral` or
        `_seen_execs`. `_orders` holds the ib `Order` OBJECT, which carries `orderId` as an
        attribute, and `cancel_order` sends that object. So the one piece of state that
        actually reaches the wire was the piece the session-boundary reasoning did not
        cover. No race was needed: place, 03:00 Gateway restart, place, cancel the first.

        THE PARTITION, and the case the architect singled out as owing a real answer:

          TERMINAL orders (filled / cancelled / rejected) are DISCARDED OUTRIGHT. Their
            outcome is known and recorded; §4's pending-timeout query has nothing left to
            resolve for them, and their neutral ids are RELEASED — which directly narrows
            the T3-08 surprise that a Limiter minting deterministic ids was blocked after a
            restart on an id that means nothing at the venue. For every order that closed
            cleanly, it now is not.

          NON-TERMINAL orders — the ones GENUINELY IN FLIGHT WHEN THE SESSION DROPPED — are
            TOMBSTONED. Clearing state for an order that was live when the socket died is
            not the same act as clearing a closed one, and treating them alike would be a
            confident lie in one direction or the other:
              - keep the state, and `query_order_status` answers `working` forever about a
                session that no longer exists (D1.24's measured symptom (b));
              - drop the state, and it answers `unknown`, which is this adapter's spelling
                of "never heard of it" — an invitation to re-mint the id of an order that
                may be live at the venue.
            §4 "Failure resolution" names exactly three outcomes and the third is
            **indeterminate**. That is what this order IS, and the tombstone exists so the
            adapter can say so. See `_Tombstone` and `query_order_status`.

        THE TOMBSTONE IS NOT A LEAK. It is bounded by the number of orders that were
        in flight at one boundary, not by the number of orders ever placed; it holds no
        vendor object; and it is superseded the moment a consumer resolves the order (§4's
        flatten-on-uncertainty), at which point re-minting the id is legitimate.
        """
        in_flight: list[ClientOrderId] = []
        for cid in self._neutral:
            if cid not in self._terminal:
                in_flight.append(cid)

        for cid in in_flight:
            trade = self._trades.get(cid)
            cum = 0
            state = "unknown"
            if trade is not None:
                st = getattr(trade, "orderStatus", None)
                if st is not None:
                    cum = int(getattr(st, "filled", 0) or 0)
                    state = self._neutral_state(getattr(st, "status", ""))
            self._tombstones[cid] = _Tombstone(
                client_order_id=cid,
                last_known_state=state,
                cumulative_qty=cum,
                session_seq=self._session_seq,
            )

        if in_flight:
            log.warning(
                "session boundary (%s): %d order(s) were IN FLIGHT and their venue-side "
                "fate is now unresolvable from here — %s. query_order_status reports them "
                "'indeterminate' (§4 Failure resolution); resolve via §4's "
                "flatten-on-uncertainty, NEVER by resending (§4:241)",
                boundary,
                len(in_flight),
                sorted(in_flight),
            )

        # DIAGNOSTICS ONLY, and structurally unable to address anything — see
        # `_prior_from_ib`. Taken before the clear so `_log_gated_drop` can still NAME a
        # post-teardown event instead of dropping it anonymously.
        self._prior_from_ib = dict(self._from_ib)

        self._to_ib.clear()
        self._from_ib.clear()
        self._acked.clear()
        self._cancelled.clear()
        self._orders.clear()
        self._trades.clear()
        self._neutral.clear()
        self._seen_execs.clear()
        self._terminal.clear()
        self._retire_queue.clear()
        # The protective path's declared intent is session-scoped too: an intent recorded
        # against a session that is gone cannot suppress anything in the next one, and a
        # flatten suppressed by a dead session's intent is a flatten that did not happen.
        self._flatten_intent.clear()
        self._session_seq += 1

    def _publish_session(self, state: SessionState, reason: str | None = None) -> None:
        """THE ONE PLACE `on_session` IS EMITTED. Every path goes through here.

        ARC 020 A3 — this is the same shape `_ack_once` has for acks, and it exists for the
        same reason: an invariant asserted at one site is a habit, an invariant asserted at
        the ONLY site is a mechanism. ARC 019 closed "plain UP over an unrebuilt mirror" by
        deriving the state from the rebuild verdict at each site; D1.25 then arrived by a
        different route — a deferred task publishing `UP_DATA_LOSS` over a session
        `disconnect()` had already torn down — because there were still several sites and
        the new one did not know about the rule. So the rule moves to the choke point.

        TWO RULES, both fail-CLOSED:

          1. NO UP-CLASS STATE OVER A DEAD SESSION. `SessionState.is_up` is documented as
             "the canonical spelling of 'is the session usable'", so publishing any of it
             while `_connected` is False makes the canonical spelling wrong — and it fails
             toward RESUMING, the direction §14 forbids ("Every uncertainty resolves toward
             flat"). Refused and logged at error level, never emitted.

          2. A DOWN THAT IS NOT A TRANSITION IS NOT PUBLISHED. §2A defines `on_session`
             as "connectivity **transitions**" (D1.28(c)): `disconnect()` called twice, or
             called on an adapter that never had a session, used to emit a DOWN each time,
             reporting a change that did not occur to a consumer whose §4 cold-start is
             driven by this edge. UP-class states are NOT suppressed this way — a repeated
             UP_DATA_LOSS carries a fresh reconciliation obligation each time, so collapsing
             those would lose a fact rather than a duplicate.

        §7.12 — what would have to be true for this to pass while gating nothing? The
        `_connected` it reads could be stale, i.e. set False only AFTER the publish. Both
        teardown paths therefore set `_connected = False` BEFORE calling here, and
        `test_broker_order.py` asserts the invariant by wrapping the SINK — outside this
        method — so a gate that stopped gating would be observed at the consumer, not
        self-reported.
        """
        if state.is_up and not self._connected:
            log.error(
                "REFUSED to publish %s over a session this adapter knows is down "
                "(_connected=False, reason=%r). §14: every uncertainty resolves toward "
                "flat, and an UP-class state here would resolve it toward resuming",
                state.value,
                reason,
            )
            return
        if state is SessionState.DOWN and self._last_published_session in (
            None,
            SessionState.DOWN,
        ):
            # Not a transition — nics_risk_subsystem_spec_v1.3.md §2A defines on_session
            # as connectivity TRANSITIONS. Logged at debug volume only: this is the
            # ordinary shape of a double teardown, not an anomaly.
            log.debug(
                "suppressed a non-transition DOWN (last published=%s, reason=%r)",
                self._last_published_session,
                reason,
            )
            return
        self._last_published_session = state
        self._sink.on_session(state, reason=reason)

    def _abandon_session(self, exc: BaseException) -> None:
        """Unwind a `connect()` that did not complete. ARC 020 A2, D1.23.

        The adapter must end this in a state that REFUSES ORDERS. `_require_session` gates
        on `_connected`, so clearing it is what makes the refusal real and observable: a
        caller that goes on to `place_order` gets `BrokerNotConnected` rather than a
        successful send into a channel whose replies are discarded.

        The session event is published through `_publish_session`, so a reconnect that was
        cancelled after a previously-UP session produces a genuine DOWN edge — the consumer
        IS told — while a first-ever connect that never announced anything produces nothing,
        because a DOWN there is not a transition and §2A says this event is transitions.
        The caller of a first-ever connect is not left uninformed either way: the exception
        it is about to receive is the notification.

        `_mirror_stale` is set True rather than left: the rebuild's verdict was never
        computed, so the mirror behind `flatten()` is exactly the "possibly-behind the
        venue" state that flag exists to name.
        """
        self._connected = False
        self._startup_complete = False
        self._mirror_stale = True
        self._clear_session_state("abandoned connect")
        log.error(
            "connect() did not complete (%s: %s) — the session is UNWOUND and this "
            "adapter now refuses order-path verbs. Nothing was resent and nothing is "
            "retried (§4:241)",
            type(exc).__name__,
            exc,
        )
        self._publish_session(
            SessionState.DOWN,
            reason=f"connect() abandoned: {type(exc).__name__}: {exc}",
        )

    def disconnect(self) -> None:
        """Tear the session down and publish DOWN on the TRANSITION.

        ARC 020 A6/D1.28(c) — "ALWAYS", which is what this said until this arc, was one
        word too strong. §2A defines `on_session(up|down, reason?)` as "connectivity
        **transitions**", and this verb emitted a DOWN on every call including when there
        had never been a session, so a consumer counting edges — and §4's cold-start is
        driven by this edge — saw events reporting no change. The teardown itself is still
        unconditional and still best-effort; only the EMISSION is now edge-correct, and it
        is enforced at the single choke point rather than here (see `_publish_session`).
        The direction of the old defect was safe (fails toward halted), which is why this is
        a correction rather than an alarm.

        ARC 020 A1 — the teardown is also where per-order state is RELEASED. See
        `_clear_session_state` for the partition (terminal discarded, in-flight tombstoned)
        and for why waiting until the next `connect()` was not good enough.

        ARC 019 A1 — MEASURED, not reasoned. Driving this verb against a real ib_async
        client over a real asyncio transport whose peer had vanished (RST, no FIN)
        produced, at 0.000079630 s:

            OSError: [Errno 107] Transport endpoint is not connected
              broker_order_ibkr.disconnect -> ib.IB.disconnect -> client.Client.disconnect
              -> connection.Connection.disconnect -> transport.write_eof()
              -> selector_events._SelectorSocketTransport.write_eof()
              -> self._sock.shutdown(socket.SHUT_WR)

        The exception escaped from the middle of this method, so `on_session(DOWN)` was
        never reached: `_connected` and `_startup_complete` were already False — the
        adapter knew it was down — while the SINK had been told nothing at all. Measured
        directly: sink.sessions before=0 after=0.

        That is the fail-OPEN direction on the session path, and it fires in exactly the
        condition where the notification matters most. The consumer is left believing a
        session is live that this adapter has already dismantled, and §4's "every
        uncertainty resolves toward flat" cannot run because no uncertainty was reported.

        WHY THE VENDOR CALL IS WRAPPED AND NOT MADE CONDITIONAL. There is no pre-check
        that would help: whether the socket is still writable is not knowable before
        attempting it, and asking would be a TOCTOU race against the very peer that has
        already gone. The teardown is best-effort by nature — the local state has already
        been dropped by the time it runs — so a vendor failure to shut a socket that is
        gone anyway must not suppress the one fact the consumer needs. Logged loudly, and
        the reason carries it, so a failed teardown is visible rather than swallowed.

        NOT A RETRY. The vendor call is attempted exactly once and never re-issued.
        """
        self._connected = False
        # Close the gate too: between disconnect and the next connect, any order-path
        # event still in flight belongs to a session that no longer exists.
        self._startup_complete = False
        self._clear_session_state("disconnect")
        reason = "requested"
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception as exc:  # noqa: BLE001 — see WHY THE VENDOR CALL IS WRAPPED
                log.error(
                    "vendor disconnect raised (session is down regardless): %s", exc
                )
                reason = f"requested; vendor teardown raised: {exc}"
        self._publish_session(SessionState.DOWN, reason=reason)

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
        # ARC 020 A1(ii). The one place in the module that is guaranteed to run when order
        # work is happening, and therefore the right place to sweep. No timer, no task.
        self._prune_retired()
        if order.client_order_id in self._neutral:
            raise BrokerSeamError(f"duplicate client_order_id {order.client_order_id}")
        tomb = self._tombstones.get(order.client_order_id)
        if tomb is not None:
            # ARC 020 A1. Distinct from the duplicate guard above and it says so, because
            # the two mean different things to a Limiter minting deterministic ids: a
            # duplicate is "you already used this in THIS session"; this is "an order under
            # this id was in flight when a session dropped and its venue-side fate is still
            # unresolved". Re-minting it would make two orders — one possibly live at the
            # venue, one certainly live — indistinguishable in the ack stream, which is the
            # ambiguity §4's pending-timeout resolution exists to remove. Terminal orders'
            # ids ARE released at the boundary, so this refusal covers only the ids that
            # genuinely cannot be reused yet.
            raise BrokerSeamError(
                f"client_order_id {order.client_order_id} belongs to an order that was "
                f"IN FLIGHT when session {tomb.session_seq} ended; query_order_status "
                "reports it 'indeterminate' (§4). Resolve it before re-minting the id — "
                "never resend under it (§4:241)"
            )

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
        """§2A: cancel a working order, addressed by the NEUTRAL id.

        ARC 020 A1 — D1.24(a), the measured defect this refusal closes. `_orders` used to
        survive `connect()` while `_to_ib`/`_from_ib` were cleared, and `_orders` holds the
        ib `Order` OBJECT, which carries `orderId`. IBKR re-issues that integer from a
        per-session sequence, so `cancel_order` on a pre-restart neutral id put a LIVE
        FOREIGN ORDER'S `orderId` on the wire. No race was required: place, 03:00 restart,
        place, cancel the first. §2A invariant 2 makes the neutral-to-venue mapping this
        adapter's sole responsibility, and a mapping the adapter has itself declared invalid
        is not one it may keep using.

        The state is now released at the boundary, so a stale id no longer resolves to an
        `Order` at all — the refusal below is what the caller sees instead, and a tombstoned
        id gets a refusal that NAMES the reason rather than the generic "unknown".
        """
        self._require_session("cancel_order")
        tomb = self._tombstones.get(client_order_id)
        if tomb is not None:
            raise BrokerSeamError(
                f"cannot cancel {client_order_id}: it belongs to session "
                f"{tomb.session_seq}, which has ended. Its venue-side id is meaningless in "
                "this session and sending it would target whichever order the venue has "
                "since assigned that id to. Resolve via query_order_status ('indeterminate'"
                ") and §4's flatten-on-uncertainty"
            )
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

        THE FAN-OUT, MEASURED (ARC 019 A1). This loop issues one send per SYMBOL, so any
        per-call cost multiplies by the number of open positions — on the path §14:969
        guarantees has "zero wire/delivery dependency". If a send could block, this verb
        would block N times over, and the 0.6 ms mirror read in front of it would be
        decoration. So it was measured rather than argued, against a real ib_async client
        over a real socket, worst observed of 5 reps, seconds:

            N=1      N=5      N=20
            0.00097  0.00294  0.00708    healthy
            0.00103  0.00289  0.00889    peer accepts, never responds
            0.00120  0.00251  0.00695    send buffer FULL
            0.00095  0.00345  0.00868    peer vanished (RST, no FIN)

        TWO THINGS THE NUMBERS SAY, and the second matters more than the first.

          Cost scales LINEARLY with N — roughly 0.35 ms per symbol. It is real and it is
          worth knowing, but at this project's declared scope of 1-5 concurrent
          instruments the whole fan-out completes inside 3.5 ms.

          The socket's condition does not appear in the numbers AT ALL. Read the table by
          column instead of by row: the four conditions are indistinguishable at every N,
          and the full-buffer column is if anything the fastest. That is the protective-path
          guarantee holding — the cost here is serialisation and dict work, and a dead peer
          costs exactly what a healthy one costs because nothing in this loop waits on the
          wire. The 0.6 ms figure ARC 014 quoted was measured against FakeIB, which does no
          serialisation; against the real vendor serialiser at N=5 it is ~2.9 ms, and that
          correction is the honest one to carry forward.

        WHAT IS STILL NOT PROVEN HERE: that the orders this loop hands off ARRIVE. They are
        accepted by asyncio's buffer and ib_async's queue whether or not the peer is
        reachable — see the module docstring. `flatten` returning is proof that the
        protective path was not blocked, never proof that the position was closed.

        ===================================================================================
        IDEMPOTENCY (ARC 020 A6, D1.27(a)). OPERATOR RULING, RATIFIED — verbatim:

          > A protective `flatten` is idempotent with respect to in-flight declared intent.
          > When `flatten` is invoked for a symbol whose prior flatten intent is still
          > inside its declared window, the second invocation emits **no additional orders**
          > and records the suppressed attempt. The window is bounded; on expiry the intent
          > is discarded and a subsequent `flatten` emits normally. **The adapter never
          > auto-refires on expiry** — re-invocation is the Limiter's, resolved through the
          > pending-timeout machinery §4 already specifies.
          >
          > Rationale, and the asymmetry that decides it: double emission over a `+2` mirror
          > produces `−4` and **creates unintended exposure of opposite sign**, which is
          > categorically worse than under-closing. Under-closing leaves a position the
          > protective triggers already know about, and §4's six triggers are unconditional
          > — they fire again. Permanent idempotency was rejected because D1.22 shows a
          > flatten can return normally and never reach the venue; an adapter that refuses
          > to re-flatten because it "already did" would refuse to protect. Resolving
          > whether the first flatten arrived needs a venue query, which is async, which the
          > protective path must not block on — **so this cannot be made safe at the adapter
          > alone.** The window bounds the damage; expiry escalates rather than auto-fires.
          >
          > Section that would have to say it: **§4 "Exits (dual authority)."** §2A's
          > `flatten` bullet defines the verb and is silent on repeat invocation; §4's "one
          > in-flight action per strategy" governs strategy signals, not Limiter-side
          > protective exits.

        WHY THE MIRROR ALONE COULD NOT PROVIDE THIS. `place_order` does not decrement the
        mirror — only a FILL does — so two flattens over one `+2` mirror both size from `+2`
        and emit `−4`. The intent record is the missing half: it is what the adapter DECIDED,
        held for a bounded time, alongside what the venue has CONFIRMED.

        THE WINDOW IS `flatten_idempotency_window_ms`, DERIVED from
        nics_risk_subsystem_spec_v1.3.md §12A:830's `PENDING_ACK_TIMEOUT_MS` and
        boot-validated against it — never a literal here, which would be debug.md §7.4's
        anchor problem sitting on the exit path. See
        `risks/broker_order.config.json` for the derivation in full.

        EXPIRY IS LAZY AND PASSIVE. It is evaluated when `flatten` is next called and at no
        other time. There is no timer, no task and no auto-refire: "the adapter never
        auto-refires on expiry" is not merely policy here, it is the absence of any
        mechanism that could.

        ===================================================================================
        THE ATTEMPT RECORD (ARC 020 A6, D1.28). Every invocation appends a `FlattenAttempt`
        naming what was emitted, what was suppressed, what was asked for and not held, what
        raised, and how trustworthy the mirror it sized from was. Read it with
        `last_flatten_attempt()`. It follows `place_order`'s local-receipt pattern — the
        §2A `-> None` signature is untouched and the record is retained internally — and it
        is a declaration of INTENT, never a claim about the venue (D1.22). Comparing intent
        against outcome is §4's reconciliation and belongs to the Limiter.
        """
        self._require_session("flatten")
        seq = next(self._flatten_attempt_seq)
        now = time.monotonic()
        window_s = self._cfg.flatten_idempotency_window_ms / 1000.0
        mirror_stale_at_attempt = self._mirror_stale

        targets = [symbol] if symbol else list(self._mirror.keys())
        intents: list[FlattenIntent] = []
        suppressed: list[FlattenSuppression] = []
        no_position: list[Symbol] = []
        failures: list[tuple[Symbol, str]] = []

        for sym in targets:
            pos = self._mirror.get(sym)
            if pos is None or pos.net_qty == 0:
                # D1.28(b): "already flat" and "the mirror has lost this position" are the
                # same silence to a caller. They are still the same FACT here — the adapter
                # genuinely cannot tell them apart — but the fact is now written down, and
                # `mirror_stale` on the record is which of the two worlds it may be in.
                no_position.append(sym)
                continue
            sup = self._suppression_for(sym, now, window_s)
            if sup is not None:
                suppressed.append(sup)
                continue
            intent, failure = self._emit_flatten_leg(sym, pos, now, seq)
            if failure is not None:
                failures.append(failure)
            if intent is not None:
                intents.append(intent)

        attempt = FlattenAttempt(
            seq=seq,
            requested_symbol=symbol,
            monotonic_ts=now,
            intents=tuple(intents),
            suppressed=tuple(suppressed),
            no_position=tuple(no_position),
            failures=tuple(failures),
            mirror_stale=mirror_stale_at_attempt,
        )
        self._flatten_attempts.append(attempt)

        if no_position and not intents and not suppressed and not failures:
            # LOUD, not silent (debug.md failure mode #11, doctrine C.7). Deliberately NOT
            # an exception: §4's flatten-on-uncertainty explicitly "may hit nothing OR close
            # a real position", so a protective flatten that finds nothing is a designed
            # outcome and raising would make the safe case look like a fault. The repair
            # failure mode #11 actually asks for is an OBSERVABLE, and that is the record.
            log.warning(
                "flatten(%s) placed nothing: the mirror holds no position for %s. "
                "mirror_stale=%s — if True, 'already flat' and 'the mirror has lost this "
                "position' are indistinguishable from here and the caller owns the "
                "reconciliation (§4). Attempt #%d recorded",
                symbol if symbol else "all",
                sorted(no_position),
                mirror_stale_at_attempt,
                seq,
            )

        if failures:
            raise BrokerSeamError(
                "flatten incomplete — these symbols were NOT flattened: "
                + "; ".join(f"{s}: {e}" for s, e in failures)
            )

    def _suppression_for(
        self, sym: Symbol, now: float, window_s: float
    ) -> FlattenSuppression | None:
        """The idempotency decision for ONE symbol. Returns the suppression, or None to
        proceed. Split out of `flatten` so the ruling's logic is readable — and testable —
        as one thing rather than as three nested branches inside the fan-out.

        EXPIRY IS EVALUATED HERE AND NOWHERE ELSE, which is what makes "the adapter never
        auto-refires on expiry" structural rather than a promise: there is no other caller,
        no timer and no task, so an expired intent can only ever be noticed by a `flatten`
        the Limiter itself issued.
        """
        prior = self._flatten_intent.get(sym)
        if prior is None:
            return None
        prior_cid, prior_ts, prior_seq = prior
        age = now - prior_ts
        if age >= window_s:
            # Expired. DISCARDED, not refired — see the ruling in `flatten`.
            self._flatten_intent.pop(sym, None)
            return None
        log.warning(
            "flatten(%s) SUPPRESSED: intent %s from attempt #%d is %.1f ms old and the "
            "window is %d ms. No additional order was emitted (ARC 020 A6). On expiry the "
            "intent is discarded; this adapter never auto-refires — re-invocation is the "
            "Limiter's",
            sym,
            prior_cid,
            prior_seq,
            age * 1000.0,
            self._cfg.flatten_idempotency_window_ms,
        )
        return FlattenSuppression(
            symbol=sym,
            prior_client_order_id=prior_cid,
            prior_attempt_seq=prior_seq,
            age_ms=age * 1000.0,
            window_ms=self._cfg.flatten_idempotency_window_ms,
        )

    def _emit_flatten_leg(
        self, sym: Symbol, pos: Position, now: float, seq: int
    ) -> tuple[FlattenIntent | None, tuple[Symbol, str] | None]:
        """Send ONE opposing market order and record the intent. Returns (intent, failure);
        exactly one of the two is not None."""
        side = Side.SELL if pos.net_qty > 0 else Side.BUY
        qty = abs(pos.net_qty)
        cid = f"flat-{sym}-{next(self._flatten_seq)}"
        try:
            self.place_order(
                NeutralOrder(
                    client_order_id=cid,
                    symbol=sym,
                    side=side,
                    qty=qty,
                    order_type=OrderType.MARKET,
                    tif=TimeInForce.IOC,
                )
            )
        except Exception as exc:  # noqa: BLE001
            # DEFECT FIX: one symbol failing must not abandon the rest. This is the
            # PROTECTIVE path — silently stopping after symbol 1 of 3 would leave real
            # positions open while the caller believes a flatten was issued. The caller
            # collects and continues, then raises once with the full picture.
            log.error("flatten failed for %s: %s", sym, exc)
            return None, (sym, str(exc))
        # Recorded ONLY on a send that did not raise. An intent that never reached the send
        # path must not suppress the next attempt — that would be the adapter refusing to
        # protect on the strength of something it did not do.
        self._flatten_intent[sym] = (cid, now, seq)
        return FlattenIntent(symbol=sym, side=side, qty=qty, client_order_id=cid), None

    def last_flatten_attempt(self) -> FlattenAttempt | None:
        """The most recent `FlattenAttempt`, or None if `flatten` has never been called.

        ARC 020 A6/D1.28. THE CONSUMER HALF IS NOT BUILT HERE and is recorded instead: the
        Limiter must (1) treat `attempt.suppressed` as "a protective action was requested
        and deliberately not sent", which is NOT the same as "it was sent"; (2) treat
        `attempt.is_silent_no_op` together with `attempt.mirror_stale` as the
        flatten-on-uncertainty trigger §4 already defines; and (3) reconcile
        `attempt.intents` against venue truth, because this record is INTENT and D1.22
        proves intent and arrival are different facts."""
        return self._flatten_attempts[-1] if self._flatten_attempts else None

    def flatten_attempts(self) -> tuple[FlattenAttempt, ...]:
        """The bounded attempt ring, oldest first. Depth is `flatten_attempt_log_depth`
        (config), so this observable cannot become the unbounded growth D1.24 was about."""
        return tuple(self._flatten_attempts)

    async def query_positions(self) -> list[Position]:
        """§4 cold-start ground truth. At cold start the broker's answer IS the record.

        ARC 020 A5 — D1.26, THE READ-VS-READ ORDERING GUARD. `self._mirror` was assigned
        wholesale with no ordering guard at all, so a read ISSUED first and COMPLETED last
        overwrote a newer venue-confirmed state; ARC 019 observed `mirror={}` after the
        venue had already confirmed `+3`, on the protective path's only input. This is not a
        shape a caller has to invent — the module produces it itself: `_on_data_loss_restore`
        schedules a read on a bare task while a caller's cold-start read (which §4 makes
        MANDATORY) may already be in flight.

        THE CHOICE: A MONOTONIC SEQUENCE ON EACH READ, WITH STALE RESULTS DISCARDED.
        Every call takes a number before it awaits; on resolution it applies to `_mirror`
        only if its number is the highest that has yet resolved. The rejected alternative
        was SERIALISING the reads behind a lock, and the reason it was rejected is the
        protective path: a lock makes a read WAIT for another read, so `_rebuild_mirror`'s
        completion — and with it `_mirror_stale`'s clearing, which is what `flatten` sizes
        against — becomes dependent on an unrelated caller's round trip. §2A says `flatten`
        must not block, and the honest way to keep that true is to add no waiting anywhere
        the protective path's input is produced.

        AND IT ADDS NO AWAIT TO THE PROTECTIVE PATH ITSELF. `flatten()` does not call this
        method and never has — it reads `_mirror` from memory. The guard is `next()` on an
        `itertools.count` and one integer comparison, both on the ALREADY-async read path,
        and nothing was added between `flatten` and the mirror.

        THE RETURNED LIST IS NOT GUARDED, deliberately. A caller that awaited this call
        asked for the snapshot IT requested and gets exactly that, stale or not; the guard
        protects the SHARED field, which is the thing two readers can corrupt for each
        other. Conflating the two would silently hand a caller someone else's answer.
        """
        self._require_session("query_positions")
        # Taken BEFORE the await, so it orders reads by ISSUE. Ordering by completion would
        # be the defect itself — the later-completing read is exactly the one that must lose.
        seq = next(self._reqpos_seq)
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

        # A5: a read that was superseded while it was in flight must not touch the shared
        # mirror. `<=` and not `<`: the seq is unique per call, so equality is unreachable
        # and writing `<` would be a claim about uniqueness made twice in two places.
        if seq <= self._mirror_applied_seq:
            log.warning(
                "query_positions #%d resolved AFTER a newer read (#%d) had already "
                "resolved — its %d-position snapshot is stale and is NOT applied to the "
                "mirror. flatten() reads that mirror (§14: the exit path has zero wire "
                "dependency, so it is only as good as this field)",
                seq,
                self._mirror_applied_seq,
                len(out),
            )
            return out

        # The sequence advances on RESOLUTION, not on application — including when the
        # fills guard below declines to apply. The skip is itself a newer decision about
        # this field, so an older read resolving afterwards must not overwrite it either.
        self._mirror_applied_seq = seq

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
        """§4: resolve pending timeouts. NEVER auto-resend.

        ARC 020 A1 — D1.24(b). §4 "Failure resolution" names exactly three outcomes for
        this query: "Resolves confirmed / cancelled / **indeterminate**". Before this arc
        the adapter could reach two of them. `_trades` survived a session boundary, so the
        cached `Trade.orderStatus` from a dead session was returned verbatim —
        `state="working"`, `terminal=False`, no staleness marker of any kind — and a Limiter
        polling this to resolve a pending timeout was told, forever, that an order in a
        session that no longer existed was still working. The one branch that could express
        uncertainty (`state="unknown"`) was reachable only when the trade was ABSENT, which
        was precisely the case a surviving `_trades` guaranteed would not happen.

        THE THREE ANSWERS THIS VERB CAN NOW GIVE, and the difference between the last two:
          a live order      — its real state, from the Trade this session's placeOrder
                              returned.
          `indeterminate`   — this adapter DID place it, and the session it lived in ended
                              before it reached a terminal state. Its venue-side fate is
                              unresolvable from here. `cumulative_qty` is the floor this
                              adapter observed, never a claim that nothing more filled.
          `unknown`         — no record at all. Not a statement about the venue.
        """
        self._require_session("query_order_status")
        tomb = self._tombstones.get(client_order_id)
        if tomb is not None:
            # NOT `terminal=True`: nothing has been resolved. And not the last-known state
            # either — what was true when the socket died is not evidence about now.
            return OrderStatus(
                client_order_id,
                terminal=False,
                state="indeterminate",
                cumulative_qty=tomb.cumulative_qty,
            )
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

    def send_backlog(self) -> SendBacklog:
        """How much this adapter is currently ABSORBING on the send path. ARC 020 A7.

        D1.22, and ONLY the observability half of it. ARC 019 measured 200 `place_order`
        calls into a verified-saturated pipe: all returned normally in 0.032 s total,
        leaving 155 messages in `ib_async.Client._msgQ`, 10204 B in asyncio's transport
        buffer, and ZERO bytes delivered to the peer. The send path does not block — it
        absorbs — and no send verb can tell the caller which of its orders reached the
        venue. Without this reading a consumer must infer absorption from SILENCE, and
        silence is also what a healthy quiet session looks like.

        WHAT THIS DOES NOT DO, deliberately and by instruction:
          - it does not RESOLVE D1.22. §4 resolves it with the pending-timeout state
            machine plus `query_order_status`, both the Limiter's, and the repair is NEVER
            a resend (§2A:71, §4:241, §12A:830).
          - it does not implement a BOUNDED-QUEUE POLICY. Where the bound sits and what
            happens when it is reached is a Limiter decision recorded in D1.22. Nothing
            here refuses, drops, blocks or backs off on any depth.
          - it does not appear in `ORDER_PORT_VERBS`. A port verb binds every vendor, and
            whether Tradovate can report its own queue depth is unmeasured — see
            `SendBacklog`.

        CANNOT-MEASURE IS NOT ZERO (debug.md §7.9, failure mode #10). Both figures come
        from vendor and asyncio internals that a version bump can move. Every read is
        defensive and a failed read yields `None` with `measured=False`, never `0` — a
        healthy idle pipe and an unreadable one must never produce the same answer. This
        method NEVER raises: it is diagnostic, and a diagnostic that can take down the
        caller is a worse defect than the blindness it was built to cure.
        """
        depth: int | None = None
        buffered: int | None = None
        notes: list[str] = []

        try:
            client = getattr(self._ib, "client", None)
            msg_q = getattr(client, "_msgQ", None)
            if msg_q is not None:
                depth = len(msg_q)
            else:
                notes.append(
                    "no client._msgQ (vendor internals moved, or not connected)"
                )
        except Exception as exc:  # noqa: BLE001 — a diagnostic must never raise
            notes.append(f"queue depth unreadable: {exc}")

        try:
            conn: Any = getattr(getattr(self._ib, "client", None), "conn", None)
            transport: Any = getattr(conn, "transport", None)
            if transport is None or not hasattr(transport, "get_write_buffer_size"):
                notes.append("no transport.get_write_buffer_size (no live transport)")
            else:
                buffered = int(transport.get_write_buffer_size())
        except Exception as exc:  # noqa: BLE001 — a diagnostic must never raise
            notes.append(f"write buffer unreadable: {exc}")

        return SendBacklog(
            vendor_queue_depth=depth,
            transport_write_buffer_bytes=buffered,
            measured=depth is not None or buffered is not None,
            detail="; ".join(notes),
        )

    # ------------------------------------------------------------------ ib events

    def _ack_once(
        self,
        cid: ClientOrderId,
        status: AckStatus,
        reason: str | None = None,
        reject_category: RejectCategory | None = None,
    ) -> bool:
        """Emit at most one ack per order. Returns True if this call emitted it.

        The single gate every ack path goes through — the venue's own PreSubmitted/
        Submitted, the errorEvent rejection, and the §2c synthesis all land here and
        share one dedupe set, so no two of them can both fire for the same order.

        ARC 018: it is also the single place the (status, reject_category) pairing is
        enforced, so no emission path can bypass it. A REJECTED ack arriving without a
        category is COERCED to UNKNOWN and logged at error level rather than raised:
        `_on_ib_error` is a sync vendor callback dispatched from the event loop, and an
        exception thrown out of it would take the event stream down on the order path to
        punish a defect whose safe resolution is already defined. Fail loud, not fatal —
        and the loud value is the honest one.
        """
        if cid in self._acked:
            return False
        violation = ack_category_violation(status, reject_category)
        if violation:
            log.error("ack contract violated for %s: %s", cid, violation)
            reject_category = (
                RejectCategory.UNKNOWN if status is AckStatus.REJECTED else None
            )
        self._acked.add(cid)
        self._sink.on_ack(cid, status, reason=reason, reject_category=reject_category)
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

    def _startup_admits(self, ib_id) -> bool:
        """THE STARTUP ADMISSION GATE. Discriminates by OWNERSHIP, not by elapsed time.

        OPERATOR RULING, RATIFIED (ARC 020 A4, D1.27(b)) — recorded verbatim:

          > The startup admission gate discriminates by order ownership, not by elapsed
          > time. Events whose `client_order_id` is present in the current session's order
          > registry are admitted regardless of startup state; all others are refused. This
          > preserves the gate's purpose — rejecting replayed history the session did not
          > originate — while permitting a protective exit issued during session
          > re-establishment to be observed. Sound **only** where per-order state is cleared
          > at every session boundary; a registry carrying entries from a prior session
          > launders a foreign order into ownership.
          >
          > Section that would have to say it: **§4 "Boot / known-state discipline"**, which
          > gates registration on the cold-start query and is silent on a protective exit
          > during session *re-establishment* — exactly when one is most likely.

        WHAT CHANGED, AND WHAT DID NOT. ARC 017 already built this filter — `cid is None`
        two lines below each call site was guard 2. What changes is which guard is
        PRIMARY. Time was; ownership is. Nothing about a replayed historical execution
        becomes admissible: `_from_ib` is cleared before `connectAsync` and the venue's
        replay is dispatched from inside it, so no replayed id can be in the registry.

        WHY THE OLD GATE HAD TO GO. It was correct about replay and wrong about everything
        else in the same window. ARC 019 measured a protective `flatten()` fired during a
        reconnect — the moment a stop is MOST likely to have been hit, since the session was
        down — placing its market orders successfully while every ack and every fill for
        them was refused by the shut gate. §14's "the exit/protective path has zero
        wire/delivery dependency" was honoured literally (nothing blocked) and violated in
        the sense that matters: the outcome of the protective action was unobservable.

        WHY IT IS SAFE, stated as the property it depends on rather than as a reassurance.
        The gate is now only as sound as `_clear_session_state`. Two conditions, and both
        are asserted in the suites rather than assumed:

          1. `_from_ib` is EMPTY at `connectAsync` — cleared at the top of `connect()`,
             AND at every teardown. So during the startup window every entry in it was put
             there by a `place_order` in THIS session, after the replay was dispatched.
          2. A pre-boundary neutral id can never re-enter it, because the ib `Order` objects
             that carried the old vendor ids are released at the boundary and a tombstoned
             id is refused by `place_order`.

        If either ever stops holding, this stops being an ownership gate and becomes a gate
        that can be FOOLED — which is precisely why A1 was a prerequisite for A4 and not a
        neighbour of it.

        NOT A WEAKENING OF `_startup_complete`. The flag still exists and still opens at the
        same instant; it is simply no longer the only question asked. An event with no
        matching live id in the startup window is refused exactly as before.
        """
        if self._startup_complete:
            return True
        return ib_id in self._from_ib

    # ------------------------------------------- terminal retention (ARC 020 A1(ii))

    def _mark_terminal(self, cid: ClientOrderId) -> None:
        """Record that an order can never change again, and schedule its release.

        ARC 020 A1(ii) — D1.24's retention policy, which the debt row is explicit is "a §4
        question, not a free deletion": *how long must a terminal order stay queryable
        through `query_order_status`?*

        THE ANSWER, and where it comes from. §4 "Failure resolution" resolves a pending
        timeout by QUERYING order status, never by resending. So the floor is set by the
        longest interval the Limiter can still be waiting before it asks —
        `PENDING_ACK_TIMEOUT_MS` and `FILL_TIMEOUT` (§12A:830). A terminal order released
        before that window closes would answer `unknown` to the query §4 mandates, and
        `unknown` means "never heard of it", which would send the Limiter down the
        mint-a-new-id path for an order that had in fact filled. So retention is
        `terminal_order_retention_ms`, boot-validated to exceed BOTH (see
        broker_order_config.py) and DERIVED from them rather than picked.

        THE SECOND REASON THE WINDOW IS NOT ZERO, which is not about the query at all: §4
        "Partial fill" says "if the cancel loses the race and the remainder fills, position
        state reflects cumulative reality". That is an execution arriving AFTER a terminal
        transition. Releasing at the instant of terminality would drop it — `_from_ib` would
        no longer map its vendor id and `_on_ib_exec_details` would discard it as foreign.

        WHY `_seen_execs` MAY GO WITH THE REST. Its job is (order_id, exec_id) idempotency.
        Once the vendor id mapping is released, a replayed execution for that order is
        refused one step earlier — `cid is None` — so the dedupe is subsumed rather than
        lost. The two must therefore be released TOGETHER and never separately, which is why
        there is one release site and not several.

        PRUNING IS LAZY AND AMORTISED O(1). Terminal transitions are appended to a deque and
        are monotonic in time, so expiry is popleft-while-expired. There is no timer and no
        task: a background timer on the order path is what this module's concurrency policy
        exists to prevent, and a sweep that runs only when the module is already doing order
        work cannot fall behind the thing it bounds.
        """
        if cid in self._terminal or cid not in self._neutral:
            return
        self._terminal.add(cid)
        self._retire_queue.append((time.monotonic(), cid))

    def _prune_retired(self) -> None:
        """Release per-order state for terminal orders past the retention window."""
        cutoff = time.monotonic() - (self._cfg.terminal_order_retention_ms / 1000.0)
        while self._retire_queue and self._retire_queue[0][0] <= cutoff:
            _ts, cid = self._retire_queue.popleft()
            self._release_order(cid)

    def _release_order(self, cid: ClientOrderId) -> None:
        """Drop EVERY trace of one order. The single release site — see `_mark_terminal`.

        The `_seen_execs` scan is linear in the size of that set, and that is affordable
        for exactly the reason this method exists: after A1(ii) the set is bounded by the
        RETENTION WINDOW rather than by process lifetime, so it holds the executions of one
        window's worth of orders — at the declared scope of 1-5 instruments, a handful. A
        second per-order index would remove the scan and add a second structure holding the
        same fact, which is the shape D1.24 was opened about.
        """
        self._terminal.discard(cid)
        self._neutral.pop(cid, None)
        self._orders.pop(cid, None)
        self._trades.pop(cid, None)
        self._acked.discard(cid)
        self._cancelled.discard(cid)
        ib_id = self._to_ib.pop(cid, None)
        if ib_id is not None:
            self._from_ib.pop(ib_id, None)
        for key in [k for k in self._seen_execs if k[0] == cid]:
            self._seen_execs.discard(key)

    def _log_gated_drop(self, kind: str, ib_id) -> None:
        """A refusal by the startup gate is silent by design — startup replay is noise and
        `_from_ib` is empty across the whole window, so nothing is lost.

        The ONE case that is not noise is an event whose id this adapter recognises, and it
        is made LOUD: a real event refused must never be indistinguishable from replay
        noise. Closing the gate across the mirror rebuild (ARC 017 A3) makes that drop
        possible where before it was a phantom fill instead.

        `_startup_complete` is False in TWO windows, not one, and the cause differs
        (ARC 019 sub-agent B, T3-03). `_connected` discriminates them: during connect() it
        is already True (set before the rebuild is awaited), and after disconnect() it is
        False. Naming the connect()-side cause on the teardown side told the operator to
        hunt a §4 cold-start ordering violation that cannot have occurred.

        ARC 020 A1/A4 — WHICH MAP EACH BRANCH READS, and why they are different maps.
          The CONNECT-side branch reads the LIVE registry `_from_ib`. After A4 that branch
            is unreachable by construction — an id in the live registry is ADMITTED now, so
            it never reaches this function. It is kept, and kept loud, because it is the
            assertion that the ownership gate is doing what it claims: if this ever fires,
            the gate and the registry have disagreed and that is a finding, not noise.
          The DISCONNECT-side branch reads `_prior_from_ib`, the previous session's map,
            because A1 clears the live one at teardown. Without that copy this drop would be
            anonymous — the operator would learn an execution was refused and not WHICH
            order — and losing the name of a post-teardown fill is exactly the diagnostic
            ARC 019 repaired. The copy is diagnostics-only and cannot address anything.
        """
        if self._connected and ib_id in self._from_ib:
            log.error(
                "startup gate refused a %s for %s, which is a LIVE order in this "
                "session — an order was placed concurrently with connect(), violating "
                "§4 cold-start ordering. The event was DROPPED. NOTE: after ARC 020 A4 "
                "this branch should be UNREACHABLE (an owned id is admitted); reaching it "
                "means the admission gate and the order registry disagree.",
                kind,
                self._from_ib[ib_id],
            )
        elif not self._connected and ib_id in self._prior_from_ib:
            log.error(
                "startup gate refused a %s for %s, which was a LIVE order in the session "
                "that has just ended — it arrived after disconnect() tore the session "
                "down, so the venue's view and ours have diverged and this order's "
                "outcome is UNKNOWN to us. The event was DROPPED; query_order_status now "
                "reports it 'indeterminate' (§4:241 — never auto-resend).",
                kind,
                self._prior_from_ib[ib_id],
            )

    def _on_ib_order_status(self, trade) -> None:
        """IBKR re-emits orderStatus on every change, so ack and cancel are deduped."""
        if not self._startup_admits(trade.order.orderId):
            # §2b, gate closed and this event is NOT one of ours (ARC 017 A3, ARC 020 A4).
            # This is the venue replaying history, not reporting our activity.
            # ORDERS_OPEN/ORDERS_COMPLETE are no longer requested either, so this should
            # now be unreachable at startup — it stays because the gate is the mechanism of
            # record and must not depend on what a future ib_async decides to fetch.
            self._log_gated_drop("orderStatus", trade.order.orderId)
            return
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
            self._mark_terminal(cid)
        elif status in ("Cancelled", "ApiCancelled"):
            # A cancel implies the order was live long enough to cancel.
            self._ensure_acked(cid, status)
            if cid not in self._cancelled:
                self._cancelled.add(cid)
                self._sink.on_cancel(cid, int(trade.orderStatus.filled))
            self._mark_terminal(cid)
        elif status in ("Inactive", "ValidationError"):
            # Terminal WITHOUT acceptance — the order was refused. No ack is synthesised
            # here (see _ensure_acked); the errorEvent raises the REJECTED one. But it is
            # terminal, and terminal is what schedules the release (ARC 020 A1(ii)).
            self._mark_terminal(cid)

    def _on_ib_exec_details(self, trade, fill) -> None:
        """§4 idempotent by (order_id, exec_id).

        VERIFIED Execution fields include execId and cumQty, so the contract's
        cumulative_qty maps directly — this is the cleanest mapping in the set.
        """
        if not self._startup_admits(fill.execution.orderId):
            # §2b, gate closed and this execution is NOT one of ours (ARC 017 A3, ARC 020
            # A4). Dropping here is the deliberate mechanism; before ARC 015 they were
            # dropped only because the id map happened to be empty, and before ARC 017 the
            # gate reopened before the rebuild had finished.
            self._log_gated_drop("execution", fill.execution.orderId)
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
            self._mirror[sym] = Position(
                sym, new_qty, self._blend_avg_price(prior, signed, price, new_qty)
            )

        self._sink.on_fill(cid, exec_id, sym, shares, price, cum)

    def _on_ib_error(self, reqId, errorCode, errorString, contract=None) -> None:
        """Rejections arrive here, not on orderStatus — the two streams must be joined
        to produce one neutral ack. Connectivity codes are also here."""
        if errorCode == IB_ERR_CONN_LOST:
            # The venue's numeric code is LOGGED (inside the adapter) and not published:
            # invariant 2 — no vendor spelling crosses the seam. See _on_data_loss_restore.
            log.warning("IBKR %d: %s", errorCode, errorString)
            self._publish_session(SessionState.DOWN, reason="connection to venue lost")
            return
        if errorCode == IB_ERR_CONN_RESTORED_DATA_LOST:
            self._on_data_loss_restore(errorString)
            return
        if errorCode == IB_ERR_CONN_RESTORED_DATA_OK:
            log.info("IBKR %d: %s", errorCode, errorString)
            # No data loss ACROSS THIS GAP: our mirror missed nothing while the venue was
            # away, so there is nothing to re-read. Deliberately NOT rebuilt — see
            # _on_data_loss_restore for why the two restores must stay asymmetric.
            #
            # ARC 019 A4. But a clean restore is a statement about THIS gap only. It says
            # nothing about a re-read that failed EARLIER, and it does not repair one: the
            # venue guaranteeing continuity across the last five seconds cannot un-fail a
            # cold-start `reqPositions` that never answered. Publishing plain `UP` here
            # while `_mirror_stale` is True would let a suspect mirror be laundered clean
            # by an unrelated reconnect — the one remaining path to "UP over a mirror this
            # adapter did not rebuild", and the last one A4 was asked to close.
            #
            # So the LEVEL wins over the EDGE. This is the same asymmetry the flag was
            # built for (see _mirror_stale): the session member is the edge, the flag is
            # the level, and only the level survives a missed event.
            if self._mirror_stale:
                self._publish_session(
                    SessionState.UP_DATA_LOSS,
                    reason=(
                        "session restored with the event stream intact, but the position "
                        "mirror was ALREADY suspect from an earlier failed re-read"
                    ),
                )
                return
            self._publish_session(
                SessionState.UP, reason="session restored, event stream intact"
            )
            return
        if errorCode in IB_INFO_CODES:
            return

        cid = self._from_ib.get(reqId)
        if cid is not None:
            # Same one-ack gate as the accept paths (§2c): whichever stream reaches an
            # order first owns its ack. A REJECTED here therefore blocks the synthesis of
            # a later ACCEPTED on an Inactive/Cancelled transition, and vice versa.
            # TWO CHANNELS, ONE EVENT (ARC 018, D1.18).
            #   reject_category — the FACT, vendor-neutral, structured, always present.
            #     Readable with no reference to any IBKR spelling.
            #   reason — the human channel, DELIBERATELY still carrying the venue's code
            #     and text. 201's margin figures are the most useful diagnostic this path
            #     produces and are not thrown away; the code simply stops being the only
            #     way to learn why the order was refused.
            emitted = self._ack_once(
                cid,
                AckStatus.REJECTED,
                reason=f"{errorCode}: {errorString}",
                reject_category=ib_reject_category(errorCode, errorString),
            )
            if emitted:
                # A rejection is terminal (§4: confirmed / cancelled — this order will
                # never work). Only on the emitting call: a late error against an order
                # already acked ACCEPTED is not evidence of anything terminal, and ARC 019
                # measured exactly that shape (IBKR 10147 arriving after a fill).
                self._mark_terminal(cid)

    # ---------------------------------------------------- data-loss self-reconciliation

    def _on_data_loss_restore(self, detail: str) -> None:
        """ARC 017 A1(b). The session came back and the venue could NOT guarantee our
        event stream across the gap. Re-read the mirror from the venue BEFORE publishing
        the session state.

        WHY THE ADAPTER DOES THIS ITSELF, and why it is not the adapter making a trading
        decision. The mirror is the adapter's OWN state, not a view of the Limiter's. It
        is the sole input to `flatten()`, which §2A designates the protective path and
        which ARC 014 measured at 0.6 ms with ZERO venue queries — it reads memory and
        fires. §14's "the exit path has no wire dependency" guarantee is therefore only
        as good as the mirror behind it. Before this arc the adapter emitted UP and
        returned, leaving `_rebuild_mirror()` un-run: one reconnect with data loss and
        `flatten()` would fire opposing orders sized from a mirror that could be missing
        an entire position, or holding one that was closed while we were blind. Not a
        rare shape — it needs no coincidence at all, just one 1101.

        The adapter is not deciding whether to trade, halt or reconcile; that stays with
        the Limiter, and `UP_DATA_LOSS` is exactly how it is told to. The adapter is
        refusing to PUBLISH a state it already knows may be backed by stale memory.

        ORDERING IS THE GUARANTEE, not merely the rebuild. The session event is emitted
        from inside `_revalidate_then_publish` AFTER the venue answers, so there is no
        instant at which a consumer has been told the session is up while this adapter is
        still holding a mirror it knows is suspect.

        WHY A TASK, AND WHY THAT IS NOT A PROHIBITED BLOCKING WAIT. `errorEvent` is a SYNC
        vendor callback dispatched from the loop; `_rebuild_mirror()` is a coroutine. The
        three ways to bridge that are `asyncio.run`/`run_until_complete` (both forbidden —
        invariant 5, and both deadlock from inside a running loop anyway), doing nothing
        (the defect), or scheduling. Scheduling is the only admissible one. This is NOT a
        retry: it runs exactly once per 1101, resends no order, and re-reads a read-only
        endpoint.

        WHY A BARE `create_task` HERE DESPITE THE MODULE'S TaskGroup POLICY. That policy
        exists so a background task cannot die silently on the order path, and it assumes
        an async caller that can own a scope. A sync vendor callback cannot own one. The
        policy's actual requirement is met by other means: the task is held in
        `_reconcile_tasks` so it cannot be garbage-collected mid-flight, and a done
        callback re-raises nothing but LOGS any exception at error level, so the failure
        mode the policy guards against — a silent death — is not reachable.
        """
        self._mirror_stale = True
        log.warning(
            "IBKR %d: %s — event stream not guaranteed across the gap; re-reading "
            "position mirror before publishing session state",
            IB_ERR_CONN_RESTORED_DATA_LOST,
            detail,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop to schedule on. Fail LOUD and publish the fact rather than a state
            # we cannot back: the consumer is told the session is up AND that our view has
            # gaps, so it can reconcile even though we could not.
            log.error(
                "data-loss restore arrived with no running event loop — mirror NOT "
                "re-read; publishing UP_DATA_LOSS with the mirror still suspect"
            )
            self._publish_session(
                SessionState.UP_DATA_LOSS,
                reason="session restored with gaps; mirror could NOT be re-read",
            )
            return

        # ARC 020 A3 — the session this publish belongs to is captured HERE, at SCHEDULE
        # time, and re-checked at PUBLISH time. See _revalidate_then_publish.
        task = loop.create_task(self._revalidate_then_publish(self._session_seq))
        self._reconcile_tasks.add(task)
        task.add_done_callback(self._reconcile_tasks.discard)
        task.add_done_callback(self._log_reconcile_failure)

    async def _revalidate_then_publish(self, scheduled_in_session: int) -> None:
        """Re-read, THEN publish — and only if the session it was scheduled for still exists.

        ARC 020 A3 — D1.25. Before this arc this coroutine published unconditionally. It is
        scheduled from `_on_data_loss_restore`, which returns immediately, so an arbitrary
        amount of the loop runs before the publish lands; a `disconnect()` in that gap was
        enough to put `UP_DATA_LOSS` (`is_up=True`) on the sink over a session the adapter
        had already torn down, observed with `_connected=False`. It failed toward
        RESUMING — the direction §14 forbids.

        TWO DISTINCT DEFECTS WERE IN THAT ONE LINE, and both are fixed:

          THE PUBLISH WAS NOT GATED ON THE SESSION. Fixed by the epoch token below. A bare
            `if self._connected` would not have been enough: it cannot distinguish "the
            session I was scheduled in" from "a DIFFERENT session that is also up", and a
            reconnect inside the gap is the ordinary shape here — 1101 means the transport
            has been flapping. `_session_seq` moves on EVERY boundary in both directions,
            so an equal token is proof of identity, not merely of liveness.

          THE VERDICT ONLY SELECTED THE REASON STRING. `rebuilt` chose between two pieces
            of prose and never gated WHETHER to publish. It now gates the publish: a rebuild
            that failed while the session went away publishes nothing at all, and a rebuild
            that failed while the session survived still publishes UP_DATA_LOSS, because
            "the session is up and our view has gaps" is exactly the fact that state exists
            to carry and is still true.

        The choke point (`_publish_session`) enforces the same invariant a second time and
        independently, from the other side — it refuses any UP-class state while
        `_connected` is False whatever the caller believes. Two mechanisms, and the one
        here is the specific one: it also refuses across a reconnect, which the choke point
        by itself cannot see.
        """
        rebuilt = await self._rebuild_mirror()
        if self._session_seq != scheduled_in_session or not self._connected:
            # DO NOT publish. Nothing about a session that no longer exists is publishable,
            # and `_mirror_stale` is deliberately left alone: this rebuild's verdict is
            # about a session that is gone, so writing it would launder a dead session's
            # answer onto a live one's flag. The next connect() computes its own.
            log.warning(
                "data-loss reconcile completed for session %d but the adapter is now in "
                "session %d (connected=%s) — the publish is REFUSED. rebuilt=%s. The "
                "session boundary already published its own state; §4's cold-start re-read "
                "is what resolves the mirror now",
                scheduled_in_session,
                self._session_seq,
                self._connected,
                rebuilt,
            )
            return
        self._mirror_stale = not rebuilt
        self._publish_session(
            SessionState.UP_DATA_LOSS,
            reason=(
                "session restored with gaps; position mirror re-read from venue"
                if rebuilt
                else "session restored with gaps; mirror re-read FAILED — mirror suspect"
            ),
        )

    @staticmethod
    def _log_reconcile_failure(task) -> None:
        """A reconcile task that dies silently is a mirror nobody knows is stale."""
        if task.cancelled():
            log.error("data-loss mirror re-read was CANCELLED — mirror still suspect")
            return
        exc = task.exception()
        if exc is not None:
            log.error("data-loss mirror re-read raised: %s", exc)

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
        # ARC 020 A1 — and per-order state must be released here for the same reason. This
        # is the boundary a Gateway restart actually arrives on: nobody called disconnect().
        self._clear_session_state("transport disconnected")
        self._publish_session(SessionState.DOWN, reason="transport disconnected")

    # ------------------------------------------------------------------ helpers

    async def _rebuild_mirror(self) -> bool:
        """Re-read the venue's position set into the mirror. True == the venue answered.

        Returns a verdict rather than None (ARC 017): both callers now need to know
        whether the mirror they are about to stand behind is venue-backed or is still the
        pre-existing memory. Swallowing the exception is still right — a failed rebuild
        must not kill connect(), and must not stop the data-loss session event from
        reaching the Limiter — but swallowing it *and* reporting nothing was how a stale
        mirror became indistinguishable from a fresh one.
        """
        self._mirror_rebuilds += 1
        try:
            await self.query_positions()
            return True
        except Exception as exc:  # noqa: BLE001 — mirror rebuild must not kill connect
            log.warning("mirror rebuild failed: %s", exc)
            return False

    @staticmethod
    def _blend_avg_price(
        prior: Position | None, signed: int, price: float, new_qty: int
    ) -> float:
        """Weighted-average cost basis across successive (partial) fills.

        FOUND BY ARC 019 A2, and it is ARC 014's defect a second time in the same field.
        The fill path used to write `Position(sym, new_qty, price)` — the LAST execution's
        price — into a field named `avg_price`. A 5-lot filling 2@7000, 2@7010, 1@7020
        left the mirror claiming an average of 7020 when it is 7008.0. Partial fills at one
        price hid it completely, which is why nothing caught it until partials were driven.

        WHY IT MATTERS RATHER THAN BEING COSMETIC: `positionEvent` writes a GENUINE
        venue-computed average into this same field (normalised per-unit by
        `_avg_price_from_cost`). So before this fix `avg_price` meant "true average" or
        "most recent fill price" depending purely on which event happened to land last —
        exactly the two-meanings-one-field shape ARC 014 found with notional-vs-per-unit,
        and the same repair: give the field ONE meaning at every write site.

        THE THREE CASES, and why reducing is not a blend:
          ADDING to a position — blend by absolute size. The new lot joins the old.
          REDUCING without crossing zero — the cost basis of what REMAINS is unchanged.
            Blending here would let a closing trade rewrite the entry price of the shares
            it did not close, which is simply wrong: closing realises P&L, it does not
            re-price inventory.
          CROSSING through zero — the old position is gone and a new one in the opposite
            direction was opened at this fill's price. Nothing of the old basis survives.

        `new_qty == 0` never reaches here: the caller pops the symbol instead, because a
        flat position has no cost basis to carry.
        """
        if prior is None or prior.net_qty == 0:
            return price
        if (prior.net_qty > 0) == (signed > 0):
            total = abs(prior.net_qty) + abs(signed)
            return (abs(prior.net_qty) * prior.avg_price + abs(signed) * price) / total
        if (prior.net_qty > 0) == (new_qty > 0):
            return prior.avg_price
        return price

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
