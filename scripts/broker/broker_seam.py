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
#   too-many-lines
#       Crossed 1000 in ARC 020 and the overage is entirely PROSE. Every Nix
#       ADDITION in this file (RejectCategory, SessionState.UP_DATA_LOSS,
#       SendBacklog, FlattenAttempt, OrderStatus.state's `indeterminate`) is a
#       declared departure from a FROZEN spec, and the declaration is the whole
#       defence: a reader has to be able to check what §2A does and does not say
#       without leaving the file. Deleting that reasoning to satisfy a line count
#       would remove the only thing standing between an addition and a silent
#       redefinition of a locked contract.
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=unused-argument,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,invalid-overridden-method
# pylint: disable=import-outside-toplevel,too-many-lines
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


class RejectCategory(enum.Enum):
    """WHY the venue refused an order, as STRUCTURED state. Declared Nix addition.

    NIX ADDITION (ARC 018), flagged exactly as `feed_lag()`/`MarketDataMode`/
    `SessionState.UP_DATA_LOSS` are. §2A declares `on_ack(client_order_id,
    accepted|rejected, reason?)` — a two-valued status plus one free-text field — and the
    frozen spec CANNOT express the refusal cause anywhere else. The frozen spec is NOT
    edited; the seam declares the addition, names it as one, and §2A remains the authority
    for the two things it does define.

    WHY IT IS OWED (D1.18). Before this arc the IBKR adapter emitted
    `reason=f"{errorCode}: {errorString}"`, so a vendor integer crossed the seam
    (invariant 2: "no vendor type crosses the line"; §2A's framing sentence: "Vendor
    specifics ... live BELOW this line and never leak above it"). The narrow defence —
    an int inside a str is not a vendor *type* — fails on the evidence: the ack `reason`
    is ALREADY consumed programmatically by substring match in this tree, so a consumer
    needing the refusal cause has no structured way to get it and will match on venue
    prose. debug.md §7.4 names that a stale literal anchor, and ARC 017 removed exactly
    this shape from the session path (1100/1101/1102 -> `UP_DATA_LOSS`).

    THE DIVISION OF LABOUR. This enum carries the FACT. `reason` keeps the full
    human-readable text INCLUDING the venue code and any figures in it — error 201's
    margin numbers have real diagnostic value and are not thrown away. `reason` simply
    stops being the only carrier. No IBKR integer, code or spelling is required to
    interpret any member below.

    HOW THE MEMBERS WERE CHOSEN — this is a taxonomy of LIMITER BEHAVIOURS, not a
    re-spelling of IBKR's error list. A category exists only where a consumer would do
    something different; two venue codes leading to the same Limiter action share a
    member. The four below are each anchored to a distinct spec-locked response.

    ENUM IS SPEC-DERIVED; THE MAP IS EVIDENCE-DERIVED. The members are derived from §4's
    Limiter behaviours. Which venue codes reach which member is a separate, strictly
    evidence-gated question owned by the adapter below the seam (see
    `broker_order_ibkr.IB_REJECT_RULES` / `IB_REJECT_EVIDENCE`). As of ARC 018 exactly ONE
    order-rejection code has ever been measured on this system, so three of the four
    members have no mapped code at all. That is reported, not hidden: a declared category
    is not a measured one.

    WHY UNKNOWN IS THE FLOOR AND NEVER `None`. Every REJECTED ack carries a member;
    anything the adapter cannot evidence lands on `UNKNOWN`, never on the nearest
    plausible match. An unknown that reads as a known is worse than an unknown that reads
    as unknown, and it is the failure this structure exists to prevent. `None` is reserved
    for "not a rejection at all" so that `reject_category is None` is exactly equivalent to
    `status is AckStatus.ACCEPTED` — one fact, one spelling, mechanically asserted by
    `ack_category_violation()` below.

    WHY A MEMBER RATHER THAN A FLAG SET. Same reasoning `SessionState.UP_DATA_LOSS`
    records: a defaulted boolean is silently ignorable by an unaware consumer. Here the
    ignorable default reads as "no cause given", which is `UNKNOWN` — the loud, safe
    direction — so the enum stays closed and every member has to be handled explicitly.
    """

    UNKNOWN = "unknown"
    """The adapter cannot evidence a cause. THE FLOOR — never a nearest match.

    LIMITER BEHAVIOUR: treat the refusal as indeterminate. It is not evidence about money,
    about the instrument, or about the venue's availability, so none of the three specific
    responses below may be taken on it. §4's uncertainty discipline applies: resolve toward
    flat, free the in-flight slot, and surface it — a cause we cannot name is an operator
    concern, not something to guess at."""

    INSUFFICIENT_MARGIN = "insufficient_margin"
    """The venue refused on money: the account cannot support the order as sized.

    LIMITER BEHAVIOUR (distinct): our local balance/margin projection DISAGREES WITH VENUE
    TRUTH. §4 (broker-authoritative balance) makes this the one category whose response is
    a reconciliation — pull a direct broker balance + position poll, publish the
    authoritative reading, and correct the projection. Crucially it also forbids the naive
    response: the same trade must not be re-sized against the projection that just proved
    wrong. Nothing about the instrument or the venue is faulty, so neither of the two
    responses below applies."""

    NOT_TRADABLE = "not_tradable"
    """The order as specified cannot be placed here at all: unknown or expired contract,
    an order type/TIF the venue will not take, an instrument this account may not trade.

    LIMITER BEHAVIOUR (distinct): money is not the problem, so re-polling the balance
    changes nothing and time will not fix it. The response is the not-tradable state §4
    already defines for a symbol absent from the margin field set — deny the strategy for
    that symbol and escalate, and for an expired contract hand it to the §7.5 roll path.
    Re-sizing or waiting are both wrong."""

    VENUE_UNAVAILABLE = "venue_unavailable"
    """The venue will not accept orders AT THIS INSTANT: session closed, exchange halt,
    order routing down. Time-varying, and not a statement about the account or the order.

    LIMITER BEHAVIOUR (distinct): this is the condition §4's market-tradable guard is
    written for — hold in HALT with a loud alert and act the instant the market is
    tradable, rather than escalating a permanent fault or denying the symbol forever. It is
    the only category whose correct response is "wait for the condition to clear".

    THIS IS NOT A LICENCE TO RESEND. §4 and §12A are explicit that the system NEVER
    auto-resends a placement; a pending timeout resolves through `query_order_status`. The
    action taken when the market becomes tradable is the Limiter's own protective one
    (§4's guarded flatten-to-flat), not a replay of the order the venue just refused."""


def ack_category_violation(
    status: AckStatus, reject_category: RejectCategory | None
) -> str:
    """Return '' if the (status, reject_category) pairing is legal, else the violation.

    The pairing IS the contract: `reject_category is None` must be exactly equivalent to
    `status is AckStatus.ACCEPTED`. Written as a function rather than left to each adapter
    so there is one spelling of the rule, checkable by a test against every emission path
    rather than re-derived per site."""
    if status is AckStatus.REJECTED and reject_category is None:
        return "REJECTED ack carries reject_category=None — UNKNOWN is the floor, never None"
    if status is AckStatus.ACCEPTED and reject_category is not None:
        return (
            f"ACCEPTED ack carries reject_category={reject_category.value} — "
            "None is the only legal value on an acceptance"
        )
    return ""


class SessionState(enum.Enum):
    """Session lifecycle as seen ABOVE the seam. UP/DOWN are §2A. UP_DATA_LOSS is a
    declared Nix addition — see below.

    NIX ADDITION (ARC 017), flagged exactly as `feed_lag()`/`MarketDataMode` are:
    `UP_DATA_LOSS` is NOT in frozen §2A, and the frozen spec CANNOT express it. §2A gives
    on_session a two-valued state plus a free-text `reason`, so the one fact a restored
    session must carry — *did the venue keep our event stream intact across the gap, or
    did we lose events?* — had nowhere to live except that prose string. Before this arc
    both restores emitted plain `UP` and the ONLY difference was the wording of `reason`,
    which made a consumer's correctness depend on substring-matching venue prose. That is
    the stale-literal anchor (debug.md §7.4) sitting on the protective path.

    The frozen spec is not edited. The seam declares the extra state, names it as an
    addition, and the risk spec remains the authority for the two states it does define.

    VENDOR-NEUTRAL BY CONSTRUCTION (invariant 2). This carries the MEANING — "restored,
    our view may have gaps" — not the venue's spelling of it. IBKR says 1101; another
    venue will say something else; neither number crosses this line.

    WHY A THIRD MEMBER RATHER THAN A `data_loss: bool` ALONGSIDE `UP`. Both are readable
    without parsing prose, so the tiebreaker is what happens to a consumer that has NOT
    been updated. A boolean defaults to False, so an unaware consumer reads a lossy
    restore as a clean `UP` and resumes against state it has no reason to distrust —
    the fact is present but silently ignorable, which is the defect this change exists to
    remove. A distinct member cannot be ignored by omission: `state is SessionState.UP`
    is simply False for it, so an unaware consumer does not resume. IBKR precedes 1101
    with 1100, so that consumer is already in DOWN and stays there — it fails toward
    halted, which is the correct direction on the protective path.

    The cost of a third member is the opposite mistake: a consumer that wants "is the
    session usable at all?" writing `is UP` and accidentally excluding a usable session.
    That is why `is_up` and `data_loss` exist below — the two questions a caller can ask
    each have ONE canonical spelling, so neither can be gotten wrong by forgetting a
    member. Identity comparison still distinguishes the three states exactly.
    """

    UP = "up"
    DOWN = "down"
    UP_DATA_LOSS = "up_data_loss"
    """Session restored, but the venue could not guarantee our event stream across the
    gap: fills, cancels or position changes may have happened unobserved. The adapter
    re-reads its own mirror from the venue BEFORE publishing this (see
    IBKRBrokerOrder._on_data_loss_restore) — but events the *consumer* derives its own
    state from (on_fill, on_cancel) cannot be replayed, so the consumer must still
    reconcile anything it holds independently."""

    @property
    def is_up(self) -> bool:
        """True for every state in which a session exists. The canonical spelling of
        'is the session usable', so no caller has to enumerate members."""
        return self in (SessionState.UP, SessionState.UP_DATA_LOSS)

    @property
    def data_loss(self) -> bool:
        """True when our view of the account may have gaps. The canonical spelling of
        'must I reconcile', readable with no reference to `reason` at all."""
        return self is SessionState.UP_DATA_LOSS


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
class DatafeedCapabilities:
    """Which §2A datafeed paths a venue can actually serve. Declared Nix addition (ARC 021).

    NIX ADDITION, flagged exactly as `feed_lag()` is, and DELIBERATELY A SEPARATE OBJECT FROM
    `BrokerCapabilities` rather than four more fields on it.
    `nics_risk_subsystem_spec_v1.3.md` §2A:105-106 invariant 3: *"order and datafeed contracts
    are disjoint — no shared object, so a datafeed fault cannot reach the order library"*. The
    two ports are separate Protocols for that reason and not one Protocol with a flag; a
    capability object shared between the libraries would re-introduce at the declaration layer
    exactly what the port split removes at the call layer, and §13:919-920 objective 24's whole
    subject is proving a datafeed fault leaves the order path undisturbed. Duplication here is
    the design.

    KNOWN OVERLAP, REPORTED RATHER THAN REPAIRED: `BrokerCapabilities.realtime_ticks` above is
    an ORDER-side declaration of a DATAFEED fact, added when no datafeed adapter existed. It is
    a second spelling of `realtime_tick_stream` below and the two can drift. Repairing it means
    editing the order library, which ARC 021 sub-agent A is not the right party to do on a
    datafeed argument.

    WHAT THIS OBJECT IS FOR (`nics_risk_subsystem_spec_v1.3.md` §2A:103-104 invariant 1): the
    command and event SET is identical across vendors, and that holds. What differs is which
    paths are LIVE. A capability that is absent is STATED as absent here, and the adapter
    REFUSES the corresponding call with `BrokerUnsupported` rather than returning silence —
    coverage differences are declared above the seam, never silently degraded."""

    realtime_tick_stream: bool
    """§2A:91 `on_tick` as "the raw firehose". False on this IBKR account: ARC 012 measured
    `reqTickByTickData` -> Err 10189 "No market data permissions for CME FUT", which names the
    PRODUCT CLASS, so no instrument choice reaches around it."""

    delayed_tick_stream: bool
    """`reqMarketDataType(3)` + `reqMktData`. True on IBKR (ARC 013, 18 ticks in 40 s), and the
    only streaming path that exists at Stage 0."""

    polled_history: bool
    """`reqHistoricalTicks` / historical bars. True on IBKR — AND DELAYED BY THE SAME ~10
    MINUTES (ARC 013 re-measured 604 s; ARC 010's own output showed 624 s and went unread). It
    is NOT a real-time back door, and `revisable_history` below is the price of it."""

    revisable_history: bool
    """True when a re-request can return DIFFERENT values for a bar already published. True for
    any polled feed. This is what makes CHECK-DEBT D1.14's seal-and-never-rewrite rule Nix's own
    obligation rather than a venue's, and it does not become False when a real-time feed
    arrives — it becomes False when the history stops being re-requestable, which is a
    different question."""

    venue_sourced_tick_ts: bool
    """§2A:106-107 invariant 4. True on IBKR's delayed stream, which carries
    `delayedLastTimestamp` — the field ARC 013 measured the 600 s lag FROM. Where it were
    False, `venue_ts` would be emitted as `None` and never as a local clock (AMENDMENT 3)."""

    pushes_feed_status: bool
    """§2A:92 `on_feed_status`. False on IBKR: there is no feed-health push. Status transitions
    are derived by this adapter from connection events and from freshness, and the derivation
    is stated rather than passed off as a venue signal."""

    def unmet_contract_paths(self) -> list[str]:
        """Names every §2A datafeed path this venue cannot serve. Empty == full coverage.

        Same shape as `BrokerCapabilities.unmet_contract_paths` and deliberately NOT the same
        function: see the class docstring on invariant 3. A shared helper here is a shared
        object between the two libraries wearing a convenience argument."""
        unmet = []
        if not self.realtime_tick_stream:
            unmet.append(
                "on_tick real-time firehose (§2A:91) — Err 10189 on CME FUT; "
                "delayed stream + polled history are the only paths"
            )
        if not self.venue_sourced_tick_ts:
            unmet.append(
                "venue-sourced tick timestamp (§2A:106-107 invariant 4) — "
                "venue_ts emitted as None, never as a local clock"
            )
        if not self.pushes_feed_status:
            unmet.append(
                "on_feed_status (§2A:92) as a venue push — derived from connection "
                "events and freshness by this adapter, not reported by the venue"
            )
        if self.revisable_history:
            unmet.append(
                "bar immutability is NOT a venue property (CHECK-DEBT D1.14) — "
                "polled history is re-requestable and revisable; the seal is Nix's"
            )
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
    state: str
    """working | filled | cancelled | rejected | unknown | indeterminate.

    `indeterminate` is a NIX ADDITION (ARC 020, D1.24), flagged exactly as
    `feed_lag()`/`MarketDataMode`/`SessionState.UP_DATA_LOSS`/`RejectCategory` are — and it
    is the least invented of them, because §4 "Failure resolution" already NAMES the
    outcome: a pending-timeout query "Resolves confirmed / cancelled / **indeterminate**".
    The frozen spec is not edited; the seam declares the spelling §4 has no field for.

    WHY IT IS OWED, and why `unknown` could not carry it. Before ARC 020 this adapter could
    reach only two of §4's three outcomes. `unknown` is emitted when the adapter holds NO
    record of the id — which is also what it emits for an id that was never placed, so the
    two most different facts in the set ("we never heard of this" and "we placed this and
    cannot tell you what became of it") shared one spelling. A Limiter cannot act on that:
    §4 sends a flatten-on-uncertainty for the second and must not for the first.

      unknown       — this adapter has no record of the id. Not a statement about the
                      venue at all. Safe to mint the id.
      indeterminate — this adapter DID place the order, and the session it lived in is
                      gone, so its venue-side fate is unresolvable from here. §4's
                      flatten-on-uncertainty is the response, and the id must NOT be
                      re-minted while the answer is outstanding.

    `terminal` is False for `indeterminate`: nothing has been resolved, and reporting an
    unresolved order as terminal would be the confident lie in the other direction."""

    cumulative_qty: int


@dataclass(frozen=True)
class SendBacklog:
    """How much this adapter is ABSORBING on the send path. Declared Nix addition (ARC 020).

    NIX ADDITION (ARC 020 A7, D1.22), flagged exactly as `feed_lag()` is. Not in §2A, and
    §2A cannot express it: the seam declares the send path "non-blocking" (invariant 5) and
    says nothing about what non-blocking COSTS.

    WHY IT IS OWED — measured, not argued. ARC 019 drove 200 `place_order` calls into a
    verified-saturated pipe. All 200 returned normally, in 0.032 s total, leaving 155
    messages in `ib_async.Client._msgQ`, 10204 B in asyncio's transport buffer, and ZERO
    bytes delivered to the peer. So the send path does not block — it ABSORBS, and no send
    verb can tell the caller which of its orders reached the venue. Without this value a
    consumer has to infer absorption from silence, and silence is also what a healthy quiet
    session looks like.

    WHAT THIS IS NOT. It is NOT a resolution of D1.22: §4 resolves that with the
    pending-timeout state machine plus `query_order_status`, both the Limiter's, and the
    repair is NEVER a resend (§2A:71, §4:241, §12A:830). It is NOT a bounded-queue policy
    either — where the bound sits and what happens at it is a Limiter decision recorded in
    D1.22, and nothing here enforces one.

    NOT ADDED TO `ORDER_PORT_VERBS`, deliberately. A port verb binds EVERY vendor, and
    whether Tradovate can report its own queue depth is unmeasured; declaring the obligation
    from one venue's internals would be inventing a cross-vendor requirement from a sample
    of one. It is adapter-observable state in the same sense `_mirror_stale` is, and its
    promotion to the port is a `BrokerCapabilities` question for the second vendor.

    `measured` is the CANNOT-MEASURE floor (debug.md §7.9, failure mode #10): a zero-depth
    healthy pipe and a vendor whose internals could not be read must never be the same
    reading. When `measured` is False both counts are None, never 0."""

    vendor_queue_depth: int | None
    """Messages the vendor client is holding in front of the transport. `None` == could not
    be read."""

    transport_write_buffer_bytes: int | None
    """Bytes asyncio's transport has buffered in userspace because the kernel would not take
    them. `None` == could not be read."""

    measured: bool
    """False == CANNOT MEASURE. Never confuse with an idle pipe."""

    detail: str = ""
    """Why a reading is absent, when it is. Human channel only — never parsed."""


@dataclass(frozen=True)
class FlattenIntent:
    """One symbol's leg of a protective flatten: what the adapter DECIDED to send.

    Part of the ARC 020 A6 attempt record (D1.28). A declaration of INTENT, not a claim
    about the venue — D1.22 is exactly why those two cannot be the same object."""

    symbol: Symbol
    side: Side
    qty: int
    client_order_id: ClientOrderId


@dataclass(frozen=True)
class FlattenSuppression:
    """One symbol's leg that was NOT sent, because a prior intent was still inside its
    declared idempotency window (ARC 020 A6, operator-ratified)."""

    symbol: Symbol
    prior_client_order_id: ClientOrderId
    prior_attempt_seq: int
    age_ms: float
    window_ms: int


@dataclass(frozen=True)
class FlattenAttempt:
    """THE OBSERVABLE ATTEMPT RECORD — what a `flatten()` call did, and did not do.

    NIX ADDITION (ARC 020 A6, D1.28), flagged exactly as `feed_lag()` is. §2A defines
    `flatten(symbol | all)` as "market-close a position (protective path; must not block)"
    and gives it no return value and no event. So the one question the protective path most
    needs to answer — *did it do the thing?* — had nowhere to live.

    WHY IT IS OWED. ARC 019 measured three ways a `flatten` can fail to achieve its purpose
    while telling the caller nothing: an under-sized close after a fill raced the mirror
    snapshot (observed mirror `+2` against a `SELL 1`); a `flatten(symbol)` on an unheld
    symbol that returns None, places nothing, raises nothing and logs nothing, so
    "already flat" and "the mirror has lost this position" are indistinguishable
    (debug.md failure mode #11, doctrine C.7); and, after ARC 020, a leg deliberately
    suppressed by the idempotency window, which is a NEW way to send nothing and therefore
    owes a NEW observable in the same motion.

    THE PATTERN IS `place_order`'s, not a signature change. `place_order` retains its vendor
    receipt locally (`self._trades[cid] = trade`) rather than returning it, because §2A
    declares the verb `-> None` and invariant 2 forbids the receipt crossing the seam. The
    same shape applies here: `flatten()` stays `-> None`, and the record is retained locally
    and read back through an accessor. The §2A signature is untouched, so this is visibly an
    addition rather than a redefinition.

    WHAT THIS IS NOT: the reconciler. Comparing this INTENT against venue OUTCOME is §4's
    "reconciles against broker truth afterward and publishes whichever is real", and that
    belongs to the Limiter. This record is the input that reconciliation currently has no
    way to obtain, and nothing more."""

    seq: int
    """Monotonic per-adapter attempt number. Lets a consumer tell two attempts apart even
    when their contents are identical — which, for a repeat protective flatten, they are."""

    requested_symbol: Symbol | None
    """Exactly what the caller asked for. `None` == flatten-all, preserved rather than
    expanded, because "flatten everything and there was nothing" and "flatten MESU6 and
    there was nothing" are different facts."""

    monotonic_ts: float
    """`time.monotonic()` at the attempt. Monotonic, not wall clock: this is compared
    against other attempts, and §12.3 clock integrity makes wall-clock deltas unsafe."""

    intents: tuple[FlattenIntent, ...]
    """Legs the adapter handed to the send path. NOT legs the venue accepted (D1.22)."""

    suppressed: tuple[FlattenSuppression, ...]
    """Legs deliberately NOT sent because a prior intent was still inside its window."""

    no_position: tuple[Symbol, ...]
    """Symbols asked for that the mirror did not hold. The D1.28(b) observable: this is
    what "already flat, OR the mirror has lost it" looks like when it is written down
    instead of being silence. Read it WITH `mirror_stale` — that flag is which of the two
    worlds the adapter may be in, and it is the reason this tuple is not just a no-op."""

    failures: tuple[tuple[Symbol, str], ...]
    """Legs whose send RAISED. The protective path continues past one symbol's failure and
    then raises once with the full picture; this is that picture, retained."""

    mirror_stale: bool
    """`_mirror_stale` AT ATTEMPT TIME. The sizing input's own trustworthiness, captured
    with the sizing rather than left to be re-read later when it may have changed."""

    @property
    def emitted_anything(self) -> bool:
        """True if any leg reached the send path. The cheapest honest question a consumer
        can ask, spelled once here so no caller has to re-derive it from three tuples."""
        return bool(self.intents)

    @property
    def is_silent_no_op(self) -> bool:
        """True when the attempt sent nothing, suppressed nothing and failed on nothing —
        i.e. every requested symbol was simply not held. THIS IS THE CASE D1.28(b) NAMES,
        and it is now a readable property rather than an absence of evidence."""
        return not self.intents and not self.suppressed and not self.failures


class LagProvenance(enum.Enum):
    """WHERE a `FeedLag.declared_lag_s` came from. Declared Nix addition (ARC 021).

    NIX ADDITION (ARC 021, D1.13/D1.14 neighbourhood), flagged exactly as `feed_lag()`
    is. It exists because the old `FeedLag.measured: bool` could express only two of the
    four states this system actually occupies, and the two it could not express are the
    two that matter:

      * a lag figure carried forward from a PRIOR ARC's measurement, which is evidence
        but is not evidence about *this* session or *this* subscription; and
      * a vendor that declares nothing at all, which under a bool renders as
        `measured=False, declared_lag_s=0.0` — a fabricated zero, i.e. the exact defect
        `docs/SPEC-AMENDMENTS.md` AMENDMENT 3 forbids.

    A bool plus one float cannot separate "0.0 because the vendor is real-time" from
    "0.0 because nobody looked". This enum makes the difference a member, so an unaware
    consumer cannot read the second as the first by omission — the same argument
    `SessionState.UP_DATA_LOSS` records against a defaulted boolean."""

    UNOBSERVED = "unobserved"
    """Nothing about the lag has been observed, here or anywhere. THE FLOOR. Pairs with
    `declared_lag_s is None`: there is no figure, and none is invented."""

    VENDOR_DECLARED = "vendor_declared"
    """The figure is a configuration/vendor claim that this adapter has NOT checked.
    A real number, with no measurement behind it in this tree."""

    PRIOR_ARC = "prior_arc"
    """The figure is a MEASUREMENT, banked by an earlier arc, replayed here. Honest about
    what it is: evidence about the venue at a past moment, not about this session. Use
    `detail` to carry the citation."""

    OBSERVED = "observed"
    """Measured by this adapter, in this session, from packets it received. The only
    provenance under which `observed_lag_s` is not None."""


class LagAgreement(enum.Enum):
    """Whether a DECLARED lag survived contact with an OBSERVED one. Declared Nix addition.

    NIX ADDITION (ARC 021). The task the frozen spec never sets: `nics_risk_subsystem_spec_v1.3.md`
    §2A:86-92 declares no lag concept at all, so it also declares no way to say that the
    configured figure and the measured figure disagree. Without a member for it, a
    divergence has only two homes — a log line nothing reads, or silence.

    IT IS AN ENUM AND NOT A `bool diverged`, on the `UP_DATA_LOSS` argument: a boolean
    defaults to False and an unaware consumer reads "never compared" as "agrees". Here the
    two not-compared cases are their own members and `agreement is LagAgreement.AGREES` is
    simply False for both, so an unaware consumer fails toward distrusting the figure."""

    NOT_DECLARED = "not_declared"
    """No declared figure exists, so there is nothing to check. Not a pass."""

    NOT_OBSERVED = "not_observed"
    """A declared figure exists and has NOT been checked against observation. Not a pass —
    this is the honest reading of every Stage 0 lag that was banked by a prior arc."""

    AGREES = "agrees"
    """Observed and declared are within `divergence_tolerance_s`."""

    DIVERGED = "diverged"
    """Observed and declared differ by more than `divergence_tolerance_s`. A FINDING the
    consumer reads off the object — never a log line — because the configured figure is an
    input to every freshness computation downstream of it."""


@dataclass(frozen=True)
class FeedLag:
    """How far behind the venue's own clock this feed runs, WITH the provenance of the answer.

    NIX ADDITION (declared by ARC 013, restructured ARC 021), flagged exactly as
    `MarketDataMode` and `SessionState.UP_DATA_LOSS` are. `nics_risk_subsystem_spec_v1.3.md`
    §2A:86-92 gives broker-datafeed four commands and two events and no lag concept, and the
    frozen spec cannot express one. Session-gating and staleness logic must be able to ask the
    feed how far behind it is, or every bar looks stale at Stage 0 and fresh in production for
    reasons unrelated to correctness.

    THE MEASUREMENT, cited rather than restated. ARC 013 measured the Stage 0 IBKR delayed
    stream on MESU6 at **600.0-601.9 s, spread 1.9 s, n=8** (`sessions/SESSION.md` ARC 013
    table; `docs/dev_and_services_plan.md` records the same row with the mean, 600.3 s). The
    RANGE is the banked record and the mean is a summary of it. A separate ARC 010 figure —
    624 s, `reqHistoricalTicks` staleness — measures a DIFFERENT thing and is not this number;
    conflating the two is how "the ARC 010 lag" entered circulation. Tradovate and DataBento
    are expected to report 0.0, and that expectation is `VENDOR_DECLARED`, not measured.

    WHY THE OLD SHAPE WAS REPLACED, recorded so it is not relitigated. It was
    `(declared_lag_s: float, measured: bool, granted_mode)`. Three defects, all one defect:

      1. `measured=False` forced `declared_lag_s` to hold SOMETHING, and
         `StubBrokerDatafeed` held `0.0`. A fabricated zero on a lag is not a small lie: it
         is the difference between "this venue is real-time" and "nobody has looked", and a
         consumer computing freshness cannot tell them apart. AMENDMENT 3 in
         `docs/SPEC-AMENDMENTS.md` names exactly this.
      2. A bool cannot say WHERE a figure came from, so a value banked by a prior arc and a
         value measured five seconds ago read identically.
      3. There was nowhere to put a DISAGREEMENT between the configured figure and the
         observed one, so a drifting venue would be invisible above the seam.

    THE VENDOR-BLIND PRIMITIVE IS `excess_staleness_s()`, and it is the whole point of this
    object. See its docstring for why neither `now - venue_ts` nor `now - recv_ts` is
    correct on its own, and why this one is correct on both vendors with one threshold."""

    declared_lag_s: float | None
    """The configured/claimed pipeline delay in seconds. `None` == NOT REPORTED — never 0.0
    standing in for an absence (AMENDMENT 3). 0.0 means a venue that genuinely claims no
    delay."""

    observed_lag_s: float | None
    """The delay this adapter MEASURED from packets, `None` == not observed. Distinct from
    0.0 for the same reason as above, and the CANNOT-MEASURE floor `debug.md` §7.9 requires."""

    observed_n: int
    """How many samples `observed_lag_s` rests on. Zero if and only if `observed_lag_s` is
    None — asserted by `__post_init__`, because a mean over an unstated sample count is the
    shape ARC 013's own 1.9 s spread exists to argue against."""

    provenance: LagProvenance
    """Where `declared_lag_s` came from. THE FLOOR IS `UNOBSERVED`, never a nearest match."""

    granted_mode: MarketDataMode
    """The mode IBKR actually GRANTED, never the mode requested. `MarketDataMode.UNKNOWN` is
    the floor: ARC 013 measured `ib_async`'s `Ticker.marketDataType` DEFAULTING to 1, so an
    unset field is indistinguishable from a real-time grant unless it is sentinelled first."""

    divergence_tolerance_s: float = 5.0
    """How far observed may sit from declared before `agreement` reads DIVERGED. Default is
    derived from the measured spread, not chosen: ARC 013's widest banked spread on this feed
    is mode 4's 600.1-604.9 s, i.e. 4.8 s, so 5.0 s is the smallest round tolerance that does
    not call a feed behaving exactly as measured a divergence. A consumer with a §12A
    `PRICE_STALE_MS` budget of its own supplies its own value."""

    detail: str = ""
    """Why a reading is absent, or the citation behind a `PRIOR_ARC` figure. Human channel
    only — never parsed. Nothing a consumer acts on may live here (`debug.md` §7.4)."""

    def __post_init__(self) -> None:
        if (self.observed_lag_s is None) != (self.observed_n == 0):
            raise ValueError(
                f"observed_lag_s={self.observed_lag_s!r} and observed_n={self.observed_n} "
                "disagree: a sample count without a value, or a value without samples"
            )
        if (
            self.observed_lag_s is not None
            and self.provenance is not LagProvenance.OBSERVED
        ):
            raise ValueError(
                f"observed_lag_s is set but provenance is {self.provenance.value} — an "
                "observation that does not declare itself observed is unattributable"
            )
        if (
            self.declared_lag_s is None
            and self.provenance is not LagProvenance.UNOBSERVED
        ):
            raise ValueError(
                f"declared_lag_s is None but provenance is {self.provenance.value} — a "
                "provenance for a figure that does not exist"
            )

    @property
    def effective_lag_s(self) -> float | None:
        """The figure a consumer should compute against, or `None` if there is none.

        OBSERVATION OUTRANKS DECLARATION (CLAUDE.md directive 2, prefer direct measurement),
        so this returns `observed_lag_s` when it exists and `declared_lag_s` otherwise. It
        returns `None` rather than 0.0 when neither exists, which is what forces
        `excess_staleness_s` to answer `None` instead of a confident wrong number."""
        return (
            self.observed_lag_s
            if self.observed_lag_s is not None
            else self.declared_lag_s
        )

    @property
    def agreement(self) -> LagAgreement:
        """Whether the declared figure survived contact with observation. THE FINDING."""
        if self.declared_lag_s is None:
            return LagAgreement.NOT_DECLARED
        if self.observed_lag_s is None:
            return LagAgreement.NOT_OBSERVED
        if abs(self.observed_lag_s - self.declared_lag_s) > self.divergence_tolerance_s:
            return LagAgreement.DIVERGED
        return LagAgreement.AGREES

    @property
    def divergence_s(self) -> float | None:
        """`observed - declared`, or `None` when either side is absent. Signed on purpose: a
        feed that has fallen FURTHER behind and one that has caught up are different facts."""
        if self.declared_lag_s is None or self.observed_lag_s is None:
            return None
        return self.observed_lag_s - self.declared_lag_s

    def excess_staleness_s(self, venue_ts: float | None, now: float) -> float | None:
        """THE VENDOR-BLIND FRESHNESS PRIMITIVE: `(now - venue_ts) - effective_lag_s`.

        `None` == CANNOT COMPUTE, which is either an absent `venue_ts` or an unknown lag.
        Never 0.0 for either, because 0.0 is the healthiest possible answer and would read as
        a pass.

        WHY THE TWO OBVIOUS COMPUTATIONS ARE BOTH WRONG, stated here so neither is written by
        a consumer who has not thought about it:

          `now - venue_ts` against a fixed threshold is correct on a 0-lag vendor and WRONG on
          the Stage 0 IBKR feed, where a perfectly healthy tick is ~600 s old by construction
          (ARC 013, see the class docstring). That consumer calls a healthy feed stale, and
          `nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 makes stale mean *halt new entries
          AND flatten open* — so the error direction is a spurious liquidation.

          `now - recv_ts` is correct on both healthy feeds and WRONG on a wedged one: a feed
          that keeps delivering packets whose `venue_ts` has stopped advancing has a fresh
          receipt clock and dead data. That consumer trades on a frozen market.

        THIS ONE IS CORRECT ON ALL THREE. On a 0-lag vendor it reduces to raw data-age. On the
        Stage 0 IBKR feed a healthy tick measured at 600.3 s yields ~0.3. Transport death and a
        frozen data clock BOTH make it grow, because `now` advances while `venue_ts` does not.
        Same consumer code, same threshold, right answer on both vendors and in both faults —
        which is `nics_risk_subsystem_spec_v1.3.md` §2A:103-104 invariant 1 (the seam is
        identical across vendors) applied to a quantity §2A does not name.

        WHAT IT IS NOT: a verdict. The threshold is a §12A tunable (`PRICE_STALE_MS`) owned by
        the consumer, and `nics_risk_subsystem_spec_v1.3.md` §6.4:373 puts the halt+flatten
        decision on the Limiter. This returns a NUMBER and takes no view."""
        lag = self.effective_lag_s
        if venue_ts is None or lag is None:
            return None
        return (now - venue_ts) - lag

    @staticmethod
    def transport_age_s(recv_ts: float | None, now: float) -> float | None:
        """How long since a packet last ARRIVED, `None` if none ever has.

        The companion half of `excess_staleness_s`, and it is carried separately rather than
        folded in because the two distinguish the two faults: transport age alone rises when
        the socket dies and stays flat on a wedged feed, and excess staleness rises in both.
        A consumer that wants to name WHICH fault it is has to be able to read both, which is
        why every emission below carries `recv_ts` alongside `venue_ts`."""
        return None if recv_ts is None else now - recv_ts


class BarSource(enum.Enum):
    """How a bar reached this seam. Declared Nix addition (ARC 021).

    Load-bearing for D1.14: `POLLED_HISTORY` is re-requestable and therefore revisable, and
    `STREAM_BUILT` is not. A consumer that must know whether its history can change under it
    reads this rather than knowing which vendor it is talking to."""

    POLLED_HISTORY = "polled_history"
    STREAM_BUILT = "stream_built"


@dataclass(frozen=True)
class Bar:
    """One SEALED bar. Declared Nix addition (ARC 021, CHECK-DEBT D1.14).

    NIX ADDITION, flagged exactly as `feed_lag()` is. `nics_risk_subsystem_spec_v1.3.md`
    §2A:91 says on_tick is "the raw firehose; capture builds bars, never broker-order", so
    §2A gives broker-datafeed no bar concept at all.

    WHY ONE IS OWED ANYWAY, and this is the argument to check rather than take on trust: at
    Stage 0 the tick firehose DOES NOT EXIST. ARC 012 measured `reqTickByTickData` returning
    Err 10189 ("No market data permissions for CME FUT"), and ARC 013 measured
    `reqMarketDataType(1)` receiving error 354 and no grant callback at all. What the venue
    will actually hand over on the history path is BARS. An adapter that insisted on §2A's
    tick shape would have to synthesise ticks from an OHLC aggregate — inventing trades at
    prices and sizes that no venue ever reported, which is precisely the fabrication
    `docs/SPEC-AMENDMENTS.md` AMENDMENT 3 forbids. Declaring the bar is the honest option;
    faking the tick is not.

    §2A's SENTENCE IS NOT VIOLATED. Its subject is *"never broker-order"* — the prohibition is
    on the ORDER library building bars, and `nics_risk_subsystem_spec_v1.3.md` §2A:86 puts
    broker-datafeed in-process INSIDE capture.py, which is the process §2A names as the bar
    builder. What crosses this seam is what the venue said, sealed; the transform library's
    Renko/M1 construction (§2A:98) is unaffected and still capture.py's.

    EVERY PRICE FIELD IS `float | None`. AMENDMENT 3 again: a venue that reports no volume for
    a bar reports no volume. Zero is a real volume and means something else."""

    symbol: Symbol
    bar_start_venue_ts: float
    """The venue's own bar-open timestamp. HALF THE SEAL KEY, and venue-sourced by
    requirement — `nics_risk_subsystem_spec_v1.3.md` §2A:106-107 invariant 4. A local clock
    here would make two adapters disagree about which bar they are talking about."""

    period_s: float
    """The other half of the seal key. Without it a 1-minute and a 5-minute bar opening at the
    same instant are the same bar."""

    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None

    recv_ts: float
    """LOCAL receipt time. Not venue-sourced and never claimed to be — it is the transport
    clock `FeedLag.transport_age_s` reads, and mixing it with `bar_start_venue_ts` is the
    error this pair of fields exists to prevent."""

    source: BarSource
    seal_seq: int
    """Monotonic per-adapter publication number. Lets a consumer order two seals whose
    contents are identical, and lets a revision name the seal it contradicts."""

    @property
    def seal_key(self) -> tuple[Symbol, float, float]:
        """The identity a seal is held under. Spelled once here so no caller re-derives it."""
        return (self.symbol, self.bar_start_venue_ts, self.period_s)

    def payload(self) -> tuple[float | None, ...]:
        """The five values a re-poll could contradict. NOT the timestamps or the sequence —
        those are about the delivery, not about what the venue claims happened."""
        return (self.open, self.high, self.low, self.close, self.volume)


@dataclass(frozen=True)
class BarRevision:
    """The venue told a DIFFERENT story about a bar that was already published (D1.14).

    NIX ADDITION (ARC 021), flagged exactly as `feed_lag()` is.

    WHY IT IS OWED. `docs/dev_and_services_plan.md` records the Stage 0 shape as delayed AND
    polled, and polled history is re-requestable: a later poll can return different values for
    a bar a consumer has already written down. Two responses are available and only one is
    defensible. Rewriting the published bar makes every downstream consumer's history
    unreproducible and does it silently, because *the revision arrives looking exactly like new
    data*. Dropping it silently discards the venue's correction. So the bar is SEALED and the
    contradiction is published as its own event — the consumer learns that the venue's story
    changed and decides what that is worth, which is a decision the adapter has no standing
    to make.

    `differing_fields` IS NON-EMPTY BY CONSTRUCTION (`__post_init__`). An identical re-poll is
    not a revision and must never be reported as one: a stream of no-op "revisions" is how a
    real one becomes invisible, and a test whose second poll returns identical data would
    prove nothing (`debug.md` §7.3 — prove non-vacuity first)."""

    sealed: Bar
    """The published bar, UNCHANGED. Carried whole so a consumer can diff without having kept
    its own copy."""

    revised_payload: tuple[float | None, ...]
    """What the later poll said instead, in `Bar.payload()` order."""

    differing_fields: tuple[str, ...]
    """Which of open/high/low/close/volume differ. Never empty."""

    recv_ts: float
    revision_seq: int

    def __post_init__(self) -> None:
        if not self.differing_fields:
            raise ValueError(
                "BarRevision with no differing field — an identical re-poll is not a "
                "revision, and reporting one would bury the real ones"
            )
        if self.revised_payload == self.sealed.payload():
            raise ValueError(
                "BarRevision whose revised payload equals the sealed payload — "
                "differing_fields and the payloads disagree"
            )


BAR_PAYLOAD_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
"""The field names `Bar.payload()` returns, in order. Derived from once, never retyped:
`BarRevision.differing_fields` and every consumer diff index into this."""


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
        *,
        reject_category: RejectCategory | None = None,
    ) -> None:
        """`status` and `reject_category` are the whole fact. `reason` is human-readable
        colour ONLY — and, unlike the session path, it is deliberately NOT vendor-neutral:
        it keeps the venue's own code and text because that is where error 201's margin
        figures live and a debugger needs them.

        ARC 018 (D1.18): a consumer must never have to read `reason` to learn anything it
        acts on. Before this arc the refusal cause existed only inside that string, so a
        consumer needing it had to substring-match venue prose — debug.md §7.4's stale
        literal anchor, and the same defect ARC 017 removed from `on_session`.
        `RejectCategory` carries the cause; `reason` is free to change wording, and free to
        contain vendor spelling, without breaking anyone.

        `reject_category` is keyword-only and additive on purpose: §2A's positional shape
        `(client_order_id, accepted|rejected, reason?)` is untouched, so this is visibly a
        Nix addition rather than a redefinition of the locked signature.

        THE PAIRING IS PART OF THE CONTRACT: `reject_category is None` iff `status is
        ACCEPTED`. Every rejection carries a category, `UNKNOWN` being the floor. See
        `ack_category_violation()`."""

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

    def on_session(self, state: SessionState, reason: str | None = None) -> None:
        """`state` is the whole fact. `reason` is human-readable colour ONLY.

        ARC 017: a consumer must never have to read `reason` to learn anything it acts
        on — in particular it must not substring-match for data loss. `SessionState`
        carries that (`state.data_loss` / `state.is_up`), and `reason` is free to change
        wording without breaking anyone. `reason` is also vendor-neutral on the session
        path: no venue error code crosses this line (invariant 2)."""


class DatafeedEventSink(Protocol):
    """Events pushed to capture.py. §2A broker-datafeed events, plus two declared additions."""

    def on_tick(
        self,
        symbol: Symbol,
        price: float | None,
        size: float | None,
        venue_ts: float | None,
        *,
        recv_ts: float,
    ) -> None:
        """Raw firehose (`nics_risk_subsystem_spec_v1.3.md` §2A:91). capture.py builds bars.

        `recv_ts` IS A NIX ADDITION and it is keyword-only and additive on purpose: §2A:91's
        positional shape `(symbol, price, size, venue_ts)` is untouched, so this is visibly an
        addition rather than a redefinition of the locked signature — the same construction
        `on_ack`'s `reject_category` uses.

        WHY IT IS OWED. `venue_ts` alone cannot distinguish a dead transport from a wedged
        feed, and a consumer holding only `venue_ts` has exactly two computations available and
        both are wrong on one of the two vendors — the argument is written out in full at
        `FeedLag.excess_staleness_s`. `recv_ts` is the LOCAL receipt clock and is never
        confused with a venue clock; §2A:106-107 invariant 4 governs `venue_ts`, and this field
        is deliberately outside it.

        `price`, `size` and `venue_ts` are `| None` per `docs/SPEC-AMENDMENTS.md` AMENDMENT 3:
        a venue that reports no size reports no size, and 0.0 is a real size."""

    def on_bar(self, sealed: Bar) -> None:
        """A SEALED bar. NIX ADDITION (ARC 021) — see `Bar` for why one is owed at Stage 0.

        Published exactly once per `Bar.seal_key`. A later poll that contradicts it arrives on
        `on_bar_revision`, never here, so a consumer cannot mistake a correction for new data
        (CHECK-DEBT D1.14)."""

    def on_bar_revision(self, revision: BarRevision) -> None:
        """The venue contradicted an already-sealed bar. NIX ADDITION (ARC 021, D1.14).

        A SEPARATE EVENT rather than a flag on `on_bar`, on the `SessionState.UP_DATA_LOSS`
        argument: a defaulted flag is silently ignorable by an unaware consumer, and the
        ignorable default here reads as "this is ordinary new data" — which is the exact defect.
        A distinct event cannot be ignored by omission."""

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

DATAFEED_EVENTS: tuple[str, ...] = (
    "on_tick",
    "on_feed_status",
    # Declared Nix additions (ARC 021). Each is flagged as one in its own docstring on
    # DatafeedEventSink above, which is what `checks/check_derived_claims.py` reads to
    # keep `seam_declared_elements` balanced: an element the seam declares that §2A does
    # not define and whose docstring does not name it an addition is counted by the code
    # side and not by the spec side, and the claim reddens. The flag is load-bearing.
    "on_bar",
    "on_bar_revision",
)


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
        """A VENDORLESS stub declares no lag. It does not declare zero.

        ARC 021 CORRECTION. This returned `FeedLag(declared_lag_s=0.0, measured=False,
        granted_mode=REALTIME)` — three fabrications in one object, and the object exists to
        prevent exactly that. `0.0` was a fabricated value for a quantity nothing had measured;
        `REALTIME` was a granted mode nobody granted, which is the shape ARC 013 measured
        `ib_async` producing by default and which `MarketDataMode.UNKNOWN` exists as the floor
        for; and a consumer computing `excess_staleness_s` against that object would have got a
        confident number off a stub. `docs/SPEC-AMENDMENTS.md` AMENDMENT 3 names the class."""
        return FeedLag(
            declared_lag_s=None,
            observed_lag_s=None,
            observed_n=0,
            provenance=LagProvenance.UNOBSERVED,
            granted_mode=MarketDataMode.UNKNOWN,
            detail="vendorless stub: no venue, so no lag has been declared or observed",
        )

    def simulate_tick(
        self,
        symbol: Symbol,
        price: float | None,
        size: float | None,
        venue_ts: float | None,
        *,
        recv_ts: float | None = None,
    ) -> None:
        """Test hook — not part of the port."""
        if symbol in self._subs:
            self._sink.on_tick(
                symbol,
                price,
                size,
                venue_ts,
                recv_ts=time.time() if recv_ts is None else recv_ts,
            )


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


class HollowBrokerDatafeed:
    """Satisfies the datafeed shape. Does nothing. MUST fail behavioural assertions.

    The datafeed counterpart of `HollowBrokerOrder`, added ARC 021 because the feed side had no
    control at all — `debug.md` §7.12's table records instance 7 as *an order sink passed into
    the datafeed port*, which survived precisely because no feed event was ever driven through
    it. A conformance suite with no control cannot tell "the adapter works" from "the assertions
    are shape-only".

    ITS `feed_lag` IS THE INTERESTING PART. It returns a FULLY-POPULATED, PLAUSIBLE object —
    declared 0.0, granted REALTIME — which is exactly the pre-ARC-021 stub's answer and exactly
    what AMENDMENT 3 forbids. So a suite that only checks `feed_lag()` returns a `FeedLag` passes
    this class, and a suite that checks the ABSENCE is declared does not. That discrimination is
    what the control measures."""

    def __init__(self, sink: DatafeedEventSink, **_: object):
        self._sink = sink

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def subscribe(self, symbol: Symbol) -> None: ...
    def unsubscribe(self, symbol: Symbol) -> None: ...

    def feed_lag(self) -> FeedLag:
        return FeedLag(
            declared_lag_s=0.0,
            observed_lag_s=None,
            observed_n=0,
            provenance=LagProvenance.VENDOR_DECLARED,
            granted_mode=MarketDataMode.REALTIME,
            detail="HOLLOW CONTROL — a plausible answer with nothing behind it",
        )


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


class FeedPollExhausted(BrokerSeamError):
    """A bounded poll spent its whole attempt budget without a response. Nix addition (ARC 021).

    A DISTINCT class rather than reusing `BrokerNotConnected`, because the two are different
    facts with different responses: the session may be perfectly alive and the venue simply not
    answering this request. Returning zero rows instead would make "the venue had nothing" and
    "we could not reach the venue" the same reading, which is the AMENDMENT 3 failure on the
    only market-data path Stage 0 has."""


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
    bars: list[Bar] = field(default_factory=list)
    bar_revisions: list[BarRevision] = field(default_factory=list)

    sequence: list[str] = field(default_factory=list)
    """Every feed event in ARRIVAL ORDER, across all four streams. The datafeed counterpart of
    `RecordingSink.sequence`, and owed for the same reason: "the seal preceded the revision" is
    a cross-stream ordering property, and the per-stream lists cannot express it."""

    def on_tick(self, symbol, price, size, venue_ts, *, recv_ts):
        # APPENDED, not inserted (same discipline as RecordingSink.on_ack): existing
        # assertions read ticks[i][3] for venue_ts, so recv_ts goes on the end.
        self.ticks.append((symbol, price, size, venue_ts, recv_ts))
        self.sequence.append("on_tick")

    def on_bar(self, sealed):
        self.bars.append(sealed)
        self.sequence.append("on_bar")

    def on_bar_revision(self, revision):
        self.bar_revisions.append(revision)
        self.sequence.append("on_bar_revision")

    def on_feed_status(self, state, symbol=None, reason=None):
        self.feed_statuses.append((state, symbol, reason))
        self.sequence.append("on_feed_status")


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

    def on_ack(self, client_order_id, status, reason=None, *, reject_category=None):
        # APPENDED, not inserted (ARC 018): existing assertions read acks[i][1] for status
        # and acks[i][2] for reason, here and in the two test suites. A four-tuple keeps
        # every one of those indices meaning what it meant, so adding the structured field
        # cannot quietly change what an old assertion is looking at.
        self.acks.append((client_order_id, status, reason, reject_category))
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
