"""
broker_datafeed_ibkr.py — IBKR implementation of the §2A broker-datafeed contract.

In-process library inside capture.py (Core 1). Called by capture.py ONLY.
Section citations name their document: `nics_risk_subsystem_spec_v1.3.md` §2A:86-92 is the
broker-datafeed subsection of the frozen risk spec, and every `§` below carries its document.

==============================================================================
INVARIANT 3 IS THE REASON THIS FILE DUPLICATES CODE. READ THIS BEFORE REFACTORING.
==============================================================================
`nics_risk_subsystem_spec_v1.3.md` §2A:105-106, verbatim: *"(3) **order and datafeed contracts
are disjoint** — no shared object, so a datafeed fault cannot reach the order library"*.

`broker_order_ibkr.py` already contains connection handling, session-state publishing, IBKR
error-code mapping and reconnect logic. Everything in this file that resembles one of those was
written independently and MUST STAY independent. Extracting a shared base class, a mixin, a
connection manager, a reconnect helper or an error-mapping table would look like good
engineering at the moment it happened and would destroy the property the spec is buying:

  * the two libraries run in DIFFERENT PROCESSES on DIFFERENT CORES
    (`nics_risk_subsystem_spec_v1.3.md` §13:919-920, objective 24: *"broker-order /
    broker-datafeed run in separate processes on separate cores; kill/reconnect the datafeed
    under load and prove the order path is undisturbed"*). A shared object cannot be shared
    across a process boundary anyway — what would be shared is shared SOURCE, and shared
    source is a shared failure mode: one edit changes both, one regression reaches both.
  * objective 24's drill becomes unprovable. Whatever the drill measures, a reader can always
    answer "but they import the same connection manager", and no amount of running the drill
    settles it.
  * they must fail INDEPENDENTLY by requirement. Duplication between the two libraries is the
    design, not debt.

WHAT IS NOT A VIOLATION: importing from `broker_seam.py`. The seam is the shared CONTRACT both
ports are declared in — `nics_risk_subsystem_spec_v1.3.md` §2A:53-58 is one seam with two
libraries behind it — and invariant 3's subject is shared IMPLEMENTATION, not the vocabulary
the two contracts are written in. The two ports are separate Protocols in that file for exactly
this reason.

WHAT WAS CONSIDERED AND REFUSED, so it is not relitigated:
  * `ibkr_mapping.py` is READ, never imported. Its `Finding` rows for `subscribe / on_tick` and
    `feed_lag` are the evidence this file's tables restate — but that module also carries the
    ORDER mapping, and importing it to reach two datafeed rows would put the order library's
    mapping table on the datafeed's import graph. The two evidence strings are duplicated
    below, with their own citations, and `ibkr_mapping.py` stays a paper artefact.
  * `broker_order_ibkr.IB_ERR_CONN_LOST` / `IB_INFO_CODES` cover the same 1100/1101/1102 codes
    this file needs. NOT imported. The order library's reading of 1101 is *"our POSITION MIRROR
    may have missed events"*; this library's reading is *"our SUBSCRIPTIONS may have been
    dropped and the granted mode may have been re-negotiated"*. Same integers, different
    meanings, different responses — a shared table would force one meaning on both, which is
    the `avg_price` defect (`docs/CHECK-DEBT.md` D1.29 records its third instance) at module
    scale.
  * `broker_seam.BrokerCapabilities` was NOT extended with datafeed fields. See
    `DatafeedCapabilities` in `broker_seam.py` for that argument.

==============================================================================
CLIENT ID — DECIDED, NOT DEFAULTED
==============================================================================
Production broker-datafeed uses **clientId 2**. `DATAFEED_CLIENT_ID` below is the declaration
and the constructor REFUSES 0 and 1.

  0 is PERMANENTLY EXCLUDED. It implicitly adopts manually-placed TWS orders, creating the
    order-ownership ambiguity `CLAUDE.md`'s mission scope forbids. Refused at construction, on
    the datafeed as on the order path, even though this library places no orders — because the
    reason it is excluded is a property of the SOCKET, not of what this library intends to do
    with it.
  1 is RESERVED for the Risk Engine's broker-order session. Refused.
  905 is DIAGNOSTICS, and sharing it is the option that has to be argued rather than fallen
    into. It is REJECTED, for three reasons and the first is decisive:
      (a) IBKR refuses a second connection on an in-use clientId. So a diagnostic probe run
          while capture is live either fails or displaces the live feed. That makes a
          diagnostics action able to reach a production data path, which is the coupling
          `nics_risk_subsystem_spec_v1.3.md` §13:919-920 objective 24 is written to disprove —
          one directory over from the order path, and it would be found by the drill rather
          than before it.
      (b) IBKR attributes API activity per clientId. Sharing makes the venue-side record
          ambiguous about which process did what, and a shared audit identity is the same
          class of defect as a shared object: two facts wearing one name.
      (c) 905 exists to be used by a human at an arbitrary moment. A production feed's identity
          must be one nobody reaches for casually.
  2 is FREE, adjacent to 1, and is what `ibkr_mapping.py`'s datafeed skeleton already assumed —
    recorded as corroboration, not as authority.

THE SESSION IS SEPARATE, AND THAT IS THE POINT. A distinct clientId is a distinct IBKR API
session over a distinct TCP connection to the same gateway. That is invariant 3 realised at the
transport layer: the datafeed's socket can die, be killed, or be reconnected without any packet
crossing the order path's socket. Sharing a clientId with broker-order would put both libraries
on one connection and make objective 24 fail by construction.

==============================================================================
WHAT STAGE 0 FORBIDS — ENCODED IN `CAPABILITIES`, NOT ONLY DOCUMENTED
==============================================================================
Five declared gaps, each following `broker_order_ibkr.py`'s four-GAP pattern. Each is a
`DatafeedCapabilities` field, each unmet path is named by `unmet_contract_paths()`, and each
absent path REFUSES with `BrokerUnsupported` rather than returning silence.

  GAP-D1 NO REAL-TIME TICK STREAM. Two measurements, two different API calls, both real —
    this was mistaken for a contradiction and is not one:
      `reqTickByTickData` -> **Err 10189** "No market data permissions for CME FUT" (ARC 012,
        `sessions/SESSION.md`). It is a REAL-TIME-ONLY request path, which is why 10189 is what
        came back. The error names the PRODUCT CLASS, so no instrument choice reaches around
        it: MES is CME FUT exactly as ES is.
      `reqMarketDataType(1)` + `reqMktData` -> **error 354**, NO grant callback at all, 0 ticks
        in 40 s (ARC 013, `sessions/SESSION.md` ARC 013 table; `docs/CHECK-DEBT.md` D1.13
        records this one).
    DECISION: `capabilities.realtime_tick_stream=False`. `request_realtime_ticks()` exists
    solely to refuse loudly, naming both codes, so a consumer cannot call the path and receive
    silence.

  GAP-D2 `reqHistoricalTicks` IS NOT A REAL-TIME BACK DOOR. It is delayed by the SAME ~10
    minutes. ARC 010's own output showed it (newest historical tick 09:29:30 against a
    connection at 09:39:54 = 624 s) and nobody read it — `debug.md` §7.12's vacuity table lists
    that as instance 3, *measured and printed, never asserted on*. ARC 013 re-measured 604 s.
    DECISION: the refusal message for GAP-D1 names this explicitly, at the place a future
    reader would try it, because it WILL look like a way around 10189.

  GAP-D3 DELAYED STREAMING WORKS, AND THE GRANT MUST BE READ, NEVER THE REQUEST.
    `reqMarketDataType(3)` + `reqMktData` delivered 18 ticks in 40 s (ARC 013). Two traps, both
    measured: IBKR SILENTLY DOWNGRADED a request for mode 4 to mode 3; and `ib_async`'s
    `Ticker.marketDataType` DEFAULTS TO 1, so an unset field is indistinguishable from a
    real-time grant. DECISION: the granted mode is sentinelled to `MarketDataMode.UNKNOWN` at
    subscribe and only a genuine venue callback moves it, and a downgrade is a readable finding
    (`granted_mode_divergence`), not a log line. This is `docs/CHECK-DEBT.md` D1.13's owed
    behaviour: *assert the granted marketDataType and FAIL on a silent downgrade*.

  GAP-D4 THE POLL FALLBACK IS THE ONLY MARGIN-CLASS PATH, AND IT IS OUTSIDE THE ORDER PATH.
    `nics_risk_subsystem_spec_v1.3.md` §2A:87-89 declares a push model for the datafeed and
    §6.4:371-372 declares push-preferred with polling demoted to fallback. On IBKR the push
    does not exist for feed health at all (`pushes_feed_status=False`), so the poll is the
    only path and stays untested against a real push until Tradovate. RETRY IS MANDATED HERE,
    not banned: §12A:827 `RETRY_BACKOFF` — *"retry policy before declaring stale"*; §6.4:373-374
    — *"Stale (freshness stamp past threshold, **after retry/backoff**) ⇒ halt new entries AND
    flatten open"*; §13:900 — *"retry/backoff before 'stale'"*. `poll_history()` therefore
    carries an EXPLICIT BOUNDED LOOP and no retry library: `tenacity`, `backoff` and `retrying`
    are banned outright in this tree by `checks/check_order_path_bans.py`, whose anchor floor is
    `scripts/broker` unconditionally, so this file is in that gate's scope from the moment it
    exists. Nothing here calls `asyncio.run`, `run_until_complete` or `run_forever`.

  GAP-D5 POLLED HISTORY IS REVISABLE. `docs/CHECK-DEBT.md` D1.14. A later poll can return
    different values for a bar already published, and *the revision arrives looking exactly like
    new data*. DECISION: seal and never rewrite — see `_ingest_history`.

==============================================================================
THE ABSENCE PRINCIPLE (`docs/SPEC-AMENDMENTS.md` AMENDMENT 3, operator ruling, ARC 021)
==============================================================================
*The seam declares absence; it never substitutes a value for one.* Applied throughout: a tick
with no size emits `size=None` and not 0.0; a bar with no volume emits `volume=None`; a
subscription with no grant callback reports `MarketDataMode.UNKNOWN` and not the mode requested;
an unobserved lag reports `LagProvenance.UNOBSERVED` and not 0.0; a venue that supplies no
timestamp gets `venue_ts=None` and never this machine's clock.

WHERE IT IS EXPENSIVE, recorded because the ruling is ratified and its cost is not yet measured:
every price field becomes `float | None`, so every consumer arithmetic site acquires a None
branch it did not have. The cost lands on the CONSUMER, which does not exist yet (capture.py's
bar builder, the Limiter's freshness gate), so this file pays none of it and the bill is real.
`FeedLag.excess_staleness_s` returning `None` for CANNOT-COMPUTE is the same trade: it is the
correct answer and it is one more branch at every call site.

AMENDMENT 3'S REFINEMENT (ARC 022) NARROWED THAT, and the paragraph above is what it was
narrowed against. *The absence principle applies to facts the venue CAN FAIL TO REPORT, not to
every field as a matter of course.* Where presence is structurally guaranteed by the existence of
the container — a bar that exists has an open — an optional type is noise, and its predictable
consequence is a consumer writing `or 0.0`, which reintroduces the substitution the amendment
forbids while wearing a null check. So `Bar.open/high/low/close` LOST their `| None` in ARC 022
and `_ingest_history` REFUSES a row missing one instead of defaulting it. `Bar.volume`,
`on_tick`'s `price`/`size`/`venue_ts`, and every `FeedLag` figure keep theirs, each with the
observable absence that justifies it written at the field. Removing an optional no observable
absence justifies is this amendment applied CORRECTLY; it is not a weakening of it.

==============================================================================
WHOSE BAR IS IT (`docs/SPEC-AMENDMENTS.md` AMENDMENT 4, operator ruling, ARC 022)
==============================================================================
*The datafeed adapter emits bars only where the VENUE is the bar's source.* A bar obtained by
polling venue history is this adapter's to publish and to seal, because the revision fact — the
venue returning a different value for a bar already published — is observable ONLY at the poll
and cannot be reconstructed downstream. **A bar derived by aggregating ticks is capture.py's, and
this adapter never derives one.**

ENFORCED, NOT DOCUMENTED. `broker_seam.Bar.__post_init__` refuses any source outside
`VENUE_SOURCED_BAR_SOURCES`, so `BarSource.TICK_AGGREGATED` is unconstructible — the same
technique `BarRevision.__post_init__` uses against a hollow revision. Proof by absence (`debug.md`
§7.6) is the other half and is checkable here: this module contains no tick-to-bar aggregation at
all. `_on_ib_tick` writes two clocks and a lag sample and forwards the packet; it never
accumulates one, and the only `Bar(...)` construction in the file is inside `_ingest_history`,
on the poll path, with `source=BarSource.POLLED_HISTORY`.

==============================================================================
ASYNC SURFACE — SETTLED BY OPERATOR RULING (ARC 022, D1.38)
==============================================================================
THIS SECTION USED TO SAY the opposite, and the change is the point. ARC 021 recorded: *"`
BrokerDatafeedPort` declares EVERY verb sync, and this adapter matches it ... This file does NOT
change the port unilaterally — a port change binds every vendor — so `connect()` drives
`ib.connect(...)`, `ib_async`'s own synchronous facade, and the obligation to argue the port's
split is reported rather than pre-empted."* That refusal was correct and the obligation it left
open is now discharged, by an operator ruling rather than by this file deciding for every vendor.

THE RULING: the broker-datafeed port is ASYNC BY DEFAULT. `connect`, `disconnect`, `subscribe`,
`unsubscribe` and `poll_history` touch the wire and are coroutine functions; `feed_lag` and
`granted_mode` read retained observables with no round trip and stay synchronous. The full text,
its rationale and its attribution are in `docs/SPEC-AMENDMENTS.md`; the split is declared once in
`broker_seam.DATAFEED_ASYNC_VERBS` and enforced by `broker_seam.check_await_conformance()`.

WHAT IS STILL OWED HERE, named rather than papered over: `connect()` is now `async def` and still
calls `self._ib.connect(...)`, the injected client's synchronous facade. Binding it to
`ib_async`'s `connectAsync` is the honest completion of the change and is NOT done in this arc,
because no live session was driven in it and swapping a vendor call this file has never executed
against the venue would be an unmeasured claim about `ib_async`'s behaviour — the class of thing
`IB_MARKETDATA_EVIDENCE` exists to refuse. The async SIGNATURE is what makes that swap a local
edit instead of a port change, which is the whole reason to take the signature first.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only — a
# blanket disable would hide the next real finding.
#
#   missing-function-docstring
#       Trivial accessors (capabilities, sealed_bars, bar_revisions,
#       poll_attempts, the two receipt-clock readers) whose behaviour is stated
#       in the class and module docstrings and, for the two clocks, at length on
#       `_SymbolFeedState`.
#   disallowed-name
#       `bar` is the domain word for the thing this module publishes. pylint's
#       default blacklist is foo/bar/baz as METASYNTACTIC placeholders; here it
#       names a §2A concept, and renaming it to avoid a lint would make the code
#       read further from the spec it implements.
#   invalid-name
#       `_on_ib_error`'s parameters are ib_async's callback signature (reqId,
#       errorCode, errorString). They are the vendor's documented contract and
#       renaming them to snake_case makes this handler harder to check against
#       the SDK, which is the one thing every line here is verified against.
#   broad-exception-caught
#       ONE site: the bounded poll loop. A vendor may raise anything, and the
#       poll fallback's whole purpose is to survive one bad response and try
#       again before declaring stale (§6.4:373-374). Narrowing it converts a
#       degraded read into an outage on the only market-data path Stage 0 has.
#       Every caught exception is RETAINED in a PollAttempt record, so nothing
#       is swallowed.
#   unused-argument
#       Vendor callbacks are called with parameters this adapter does not need
#       (errorEvent's `contract`). They stay in the signature because ib_async
#       passes them positionally.
#   too-many-instance-attributes
#       The per-symbol grant map, the seal store, the revision log, the lag
#       samples and the two receipt clocks are each required by a named
#       obligation (D1.13, D1.14, invariant 4, AMENDMENT 3). Merging them to
#       satisfy a count would make the state harder to reason about.
#   too-many-arguments / too-many-positional-arguments
#       §2A fixes on_tick's shape; the constructor's knobs are the §12A tunables
#       this module owns. The metric is measuring the contract.
# ARC 021 PHASE 4: `import-outside-toplevel` was suppressed here with a rationale
# describing a lazy `ib_async` import "inside the one method that needs it". THERE IS NO
# SUCH IMPORT — this module imports only `broker_seam` and stdlib, and the vendor client
# is INJECTED (`connect()` refuses to construct one, see its BrokerNotConnected message).
# The suppression covered code that does not exist and its comment asserted something
# untrue about the module it sat in, which is `debug.md` §7.4's stale-anchor class banked
# on day one. Both are removed rather than reworded; the injection design is documented
# at `connect()`, which is where a reader meets it.
#   too-many-lines
#       Crossed 1000 in ARC 022 (1000 -> 1083) and the overage is ENTIRELY PROSE:
#       AMENDMENT 4's ownership boundary, AMENDMENT 3's refinement and the reversal
#       of this file's own ARC 021 ASYNC SURFACE section — which asserted the
#       opposite of what is now true and is quoted verbatim so the change is
#       legible rather than silent. `broker_seam.py` carries the same suppression
#       for the same reason, and the reason is the same one: every declared
#       departure from a FROZEN spec has its declaration as its whole defence, and
#       a reader has to be able to check what §2A does and does not say without
#       leaving the file. Deleting that reasoning to satisfy a line count would
#       remove the only thing standing between an addition and a silent
#       redefinition of a locked contract. Splitting the module is the OTHER
#       available answer and it is refused for a stronger reason: the second file
#       would be a shared datafeed helper, which is precisely the invariant-3
#       extraction the header block above refuses.
# pylint: disable=invalid-name,broad-exception-caught,unused-argument
# pylint: disable=too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=missing-function-docstring,disallowed-name,too-many-lines
import logging
import time
from dataclasses import dataclass, field

from broker_seam import (
    BAR_PAYLOAD_FIELDS,
    BAR_REQUIRED_PAYLOAD_FIELDS,
    Bar,
    BarRevision,
    BarSource,
    BrokerNotConnected,
    BrokerUnsupported,
    DatafeedCapabilities,
    DatafeedEventSink,
    FeedLag,
    FeedPollExhausted,
    FeedState,
    LagProvenance,
    MalformedBarRow,
    MarketDataMode,
    Symbol,
)

log = logging.getLogger("nix.broker_datafeed.ibkr")

# ---------------------------------------------------------------------------
# IDENTITY
# ---------------------------------------------------------------------------
DATAFEED_CLIENT_ID = 2
"""Production broker-datafeed clientId. The argument is in the module docstring."""


def resolve_granted_mode(mode_value: int) -> MarketDataMode:
    """Map a RAW VENDOR mode integer to the neutral enum. The whole of D1.13's rule,
    in one pure function.

    LIFTED TO MODULE LEVEL IN ARC 021 PHASE 4 (CHECK-DEBT D1.32). This logic lived
    inline inside `_on_ib_market_data_type`, where it was correct but unreachable:
    `check_datafeed_granted_mode`'s arm B1 proves the three-way distinction by
    EXECUTING the observer over vendor values 0/1/3, and an observer reachable only
    through a bound method that wants a `Symbol` cannot be executed with a vendor
    integer. The gate reported CANNOT_MEASURE naming the site — honest, and it left
    D1.13's gate unbound to the only adapter it exists to check.

    Nothing here is weakened to satisfy a gate: the mapping is byte-for-byte the one
    that was inline and behaviour on every input is unchanged. What changed is that the
    property is now OBSERVABLE — CLAUDE.md directive 1, prove properties not proxies.

    THE THREE LEGS THIS EXISTS TO MAKE DRIVABLE, and why each matters:
      0 -> UNKNOWN   the SENTINEL. `subscribe()` writes 0 before the request, so a
                     grant callback that never arrives stays readable as absent. ARC 013
                     measured `ib_async`'s `Ticker.marketDataType` DEFAULTING to 1, so
                     an unsentinelled field reports a real-time grant that never happened.
      1 -> REALTIME  a GENUINE grant of real-time, which must be distinguishable from
                     the sentinel above. Collapsing these two reproduces the defect.
      3 -> DELAYED   what Stage 0 actually gets, including when 4 was requested — ARC 013
                     measured the silent 4->3 downgrade with no error raised.

    An unrecognised value is UNKNOWN, never coerced to the requested mode and never to
    REALTIME: an unknown that reads as a known is the failure the floor exists to prevent
    (AMENDMENT 3, the absence principle).

    DELIBERATELY PURE — it does not log. The caller holds the `symbol` that makes a
    warning worth reading, and a gate driving this over three legs should not emit
    warnings as a side effect of being measured."""
    try:
        return MarketDataMode(mode_value)
    except ValueError:
        return MarketDataMode.UNKNOWN


RESERVED_CLIENT_IDS: dict[int, str] = {
    0: (
        "permanently excluded — clientId 0 implicitly adopts manually-placed TWS orders, "
        "creating the order-ownership ambiguity the mission scope forbids. The exclusion is a "
        "property of the socket, not of what this library intends to do with it"
    ),
    1: (
        "reserved for the Risk Engine's broker-order session — sharing it would put both "
        "libraries on ONE IBKR connection and make §2A:105-106 invariant 3 false at the "
        "transport layer"
    ),
}
"""ids this adapter REFUSES at construction, each with the reason the refusal carries. 905 is
deliberately absent: it is diagnostics, it is rejected by argument rather than by refusal, and
a caller who insists may still pass it — the constructor's job is to make the two UNUSABLE ids
unusable, not to enumerate every id somebody should not choose."""

# ---------------------------------------------------------------------------
# MEASURED VENUE FACTS — the evidence half.
#
# EVIDENCE-GATED BY CONSTRUCTION, the same discipline `broker_order_ibkr.py`'s
# IB_REJECT_EVIDENCE carries and reached independently (invariant 3): every code this adapter
# gives a MEANING to must appear here with a citation to something measured on this system. A
# declaration is not evidence, and IBKR's published error list is not this system.
# ---------------------------------------------------------------------------

IB_MARKETDATA_EVIDENCE: dict[int, str] = {
    10189: (
        "MEASURED ARC 012 on MESU6, reproduced from ARC 010 on ES. `reqTickByTickData` "
        "returns 'No market data permissions for CME FUT'. sessions/SESSION.md ARC 012 "
        "section: 'reqTickByTickData on MES returns Err 10189'. The string names the PRODUCT "
        "CLASS, not the contract, so instrument selection cannot reach around it."
    ),
    354: (
        "MEASURED ARC 013 on MESU6, requested marketDataType 1. 'Requested market data is not "
        "subscribed. Delayed market data is available.' Accompanied by ZERO ticks in 40 s and "
        "NO marketDataType grant callback at all — verified by sentinelling "
        "Ticker.marketDataType to 0 after subscribing and observing it never move. "
        "sessions/SESSION.md ARC 013 table; docs/CHECK-DEBT.md D1.13."
    ),
    10167: (
        "MEASURED ARC 013 on MESU6, requested marketDataType 3 and 4. 'Requested market data "
        "is not subscribed. Displaying delayed market data.' This is the INFORMATIONAL "
        "companion of a WORKING delayed subscription (18 and 19 ticks per 40 s respectively), "
        "not a failure. sessions/SESSION.md ARC 013 table."
    ),
}

IB_ERR_NO_REALTIME_PERMISSION = 10189
IB_ERR_NOT_SUBSCRIBED_DELAYED_AVAILABLE = 354
IB_ERR_DISPLAYING_DELAYED = 10167


@dataclass(frozen=True)
class Stage0LagRecord:
    """The banked Stage 0 lag measurement, carried as a RANGE with its sample count.

    NOT A SCALAR, deliberately. `sessions/SESSION.md`'s ARC 013 table records
    `600.0-601.9 s, spread 1.9 s, n=8` for requested=3/granted=3; the mean 600.3 s appears in
    `docs/dev_and_services_plan.md`'s copy of the same row. A point value carried alone loses
    the spread, and the spread is what makes it a steady pipeline delay rather than one stale
    first tick — which was ARC 013's actual finding.

    ATTRIBUTION, because it has been got wrong: this is **ARC 013's** measurement. A separate
    **624 s** figure from ARC 010 measures `reqHistoricalTicks` staleness — a different call
    and a different quantity — and merging the two produces a lag figure attributed to an arc
    that never computed one."""

    low_s: float
    high_s: float
    mean_s: float
    spread_s: float
    n: int
    arc: str
    citation: str

    def as_declared(self) -> tuple[float, str]:
        """(scalar to declare, the detail string that says what the scalar is)."""
        return self.mean_s, (
            f"{self.arc} measurement, replayed — NOT measured this session. Banked record is a "
            f"RANGE {self.low_s}-{self.high_s} s (spread {self.spread_s} s, n={self.n}); "
            f"{self.mean_s} s is its MEAN. Source: {self.citation}. "
            f"RE-MEASUREMENT IS OWED: no tap session ran in ARC 021 "
            f"(~/nix/downloads/TAP_SESSION.md does not exist)."
        )


IB_STAGE0_DELAYED_LAG = Stage0LagRecord(
    low_s=600.0,
    high_s=601.9,
    mean_s=600.3,
    spread_s=1.9,
    n=8,
    arc="ARC 013",
    citation="sessions/SESSION.md ARC 013 table; docs/dev_and_services_plan.md same row",
)

IB_STAGE0_DELAYED_FROZEN_LAG = Stage0LagRecord(
    low_s=600.1,
    high_s=604.9,
    mean_s=600.6,
    spread_s=4.8,
    n=9,
    arc="ARC 013",
    citation="sessions/SESSION.md ARC 013 table (requested 4, GRANTED 3 — see GAP-D3)",
)
"""The mode-4 row. Kept because its 4.8 s spread is where `FeedLag.divergence_tolerance_s`'s
default of 5.0 s is derived from, and because the row itself IS the silent-downgrade evidence:
mode 4 was requested and mode 3 was granted."""


@dataclass(frozen=True)
class PollAttempt:
    """One attempt of the bounded poll loop, retained rather than logged.

    `nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 makes retry/backoff the thing that happens
    BEFORE a feed is declared stale, so how many attempts it took and why each failed is an
    input to that decision and not diagnostic colour. A consumer that cannot see the attempts
    cannot tell a feed that answered first time from one that answered on the last."""

    seq: int
    symbol: Symbol
    started_ts: float
    ok: bool
    error: str = ""
    rows: int = 0


@dataclass
class _SymbolFeedState:
    """Everything this adapter knows about ONE subscription.

    Per-symbol rather than global because `nics_risk_subsystem_spec_v1.3.md` §2A:92 gives
    `on_feed_status` an optional `symbol?`, i.e. the contract already contemplates per-symbol
    feed health. A global-only view cannot express one wedged symbol on a live connection."""

    granted_mode: MarketDataMode = MarketDataMode.UNKNOWN
    """THE GRANT, never the request. `UNKNOWN` is the floor and the sentinel — see GAP-D3."""

    requested_mode: MarketDataMode = MarketDataMode.UNKNOWN
    """What was asked for. Retained ONLY so a downgrade can be named; never reported as the
    mode in effect."""

    last_tick_recv_ts: float | None = None
    """LOCAL clock at the last STREAM packet. `None` == none has ever arrived."""

    last_tick_venue_ts: float | None = None
    """The venue's own clock on the last stream packet. `None` == the venue supplied none, or
    none has arrived. Never this machine's clock (AMENDMENT 3, and §2A:106-107 invariant 4)."""

    last_poll_recv_ts: float | None = None
    """LOCAL clock at the last POLL response.

    DELIBERATELY NOT MERGED WITH `last_tick_recv_ts`, and this is the ARC 020 A8 per-writer
    rule applied BEFORE the defect rather than after it. "A stream packet arrived" and "a poll
    response arrived" are different facts with different consequences — a live stream with a
    dead poller and a dead stream with a live poller are opposite conditions — and one field
    written by both handlers would carry two meanings depending on which wrote last. That is
    exactly the `avg_price` shape, whose third instance `docs/CHECK-DEBT.md` D1.29 records. The
    cheap moment to prevent a fourth is before either writer exists."""

    lag_samples: list[float] = field(default_factory=list)
    """(recv_ts - venue_ts) per stream packet that carried BOTH. Written by the tick path
    only."""


class IBKRBrokerDatafeed:
    """§2A broker-datafeed, IBKR Stage 0 implementation.

    Satisfies `broker_seam.BrokerDatafeedPort` — seven verbs on the ARC 022 D1.38 split, five
    async (the wire) and two sync (retained observables) — plus the adapter-local additions this
    venue's shape requires. Nothing in this class is imported by, or imports,
    `broker_order_ibkr.py`.
    """

    CAPABILITIES = DatafeedCapabilities(
        realtime_tick_stream=False,  # GAP-D1: Err 10189 / error 354
        delayed_tick_stream=True,  # GAP-D3: reqMarketDataType(3) + reqMktData
        polled_history=True,  # GAP-D2: works, and is ALSO ~10 min delayed
        revisable_history=True,  # GAP-D5: D1.14, the seal is Nix's obligation
        venue_sourced_tick_ts=True,  # delayedLastTimestamp; the field ARC 013 measured from
        pushes_feed_status=False,  # GAP-D4: derived here, not reported by the venue
    )

    def __init__(
        self,
        sink: DatafeedEventSink,
        *,
        ib=None,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = DATAFEED_CLIENT_ID,
        requested_mode: MarketDataMode = MarketDataMode.DELAYED,
        lag_record: Stage0LagRecord | None = IB_STAGE0_DELAYED_LAG,
        stale_threshold_s: float = 30.0,
        poll_attempts: int = 3,
        history_source=None,
    ):
        if client_id in RESERVED_CLIENT_IDS:
            raise ValueError(
                f"clientId={client_id} refused for broker-datafeed: "
                f"{RESERVED_CLIENT_IDS[client_id]}. Use {DATAFEED_CLIENT_ID}."
            )
        if poll_attempts < 1:
            raise ValueError(
                f"poll_attempts={poll_attempts} would make the poll fallback — the ONLY "
                "market-data path at Stage 0 — do nothing. §6.4:373-374 requires "
                "retry/backoff BEFORE declaring stale, so the floor is 1 attempt"
            )
        self._sink = sink
        self._ib = ib
        self._host, self._port, self._client_id = host, port, client_id
        self._requested_mode = requested_mode
        self._lag_record = lag_record
        self._stale_threshold_s = stale_threshold_s
        self._poll_attempts = poll_attempts
        # Injected so the whole poll path is drivable with no venue. `None` means the caller
        # must supply one before polling — never a silent no-op that reads as "no data".
        self._history_source = history_source

        self._connected = False
        self._feed_state = FeedState.DOWN
        self._symbols: dict[Symbol, _SymbolFeedState] = {}

        # --- D1.14: the seal store and the revision log -------------------------------
        # A bar is published ONCE per seal key and never rewritten. Both structures are
        # adapter-retained and read back through accessors rather than returned from the
        # verbs, which is `FlattenAttempt`'s construction: the §2A signature stays untouched
        # and the addition is visibly an addition.
        self._sealed: dict[tuple[Symbol, float, float], Bar] = {}
        self._revisions: list[BarRevision] = []
        self._seal_seq = 0
        self._revision_seq = 0

        self._poll_attempt_log: list[PollAttempt] = []
        self._poll_seq = 0

    # ------------------------------------------------------------------
    # DECLARATIONS
    # ------------------------------------------------------------------
    def capabilities(self) -> DatafeedCapabilities:
        return self.CAPABILITIES

    # ------------------------------------------------------------------
    # §2A:88 connect / disconnect
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Establish the venue session. ASYNC, as `BrokerDatafeedPort` now declares it (D1.38).

        It still drives `self._ib.connect(...)` rather than `connectAsync` — see the module
        docstring's ASYNC SURFACE section for why that swap is owed and deliberately not made in
        the arc that changed the signature."""
        if self._ib is None:
            raise BrokerNotConnected(
                "connect() called with no ib_async.IB supplied. This adapter takes an "
                "injected client so the whole surface is drivable offline; it does not "
                "construct one silently"
            )
        self._ib.connect(self._host, self._port, clientId=self._client_id)
        self._connected = True
        # WRITER 1 of _feed_state. MEANING: a session exists. It is NOT a claim that any
        # symbol is fresh — nothing has been subscribed yet, so freshness is undefined and
        # `evaluate_freshness` is the only writer allowed to say STALE.
        self._publish_feed_state(FeedState.UP, reason="session established")

    async def disconnect(self) -> None:
        """Tear the session down. Clears every per-symbol grant — see `_forget_symbol`.

        ASYNC on this port and SYNC on the order port, which is not an inconsistency: an order
        disconnect can be part of a protective sequence and §2A:107 invariant 5 forbids it
        awaiting, and nothing on this port is ever protective (D1.38)."""
        if self._ib is not None and self._connected:
            self._ib.disconnect()
        self._connected = False
        for state in self._symbols.values():
            # WRITER 3 of granted_mode. MEANING: the session that granted this is gone, so
            # the grant is gone with it. Retaining a grant across a session boundary is the
            # shape `docs/CHECK-DEBT.md` D1.24 records on the order path — state outliving
            # the session it was true in.
            state.granted_mode = MarketDataMode.UNKNOWN
        # WRITER 2 of _feed_state. MEANING: no session. Not a staleness claim.
        self._publish_feed_state(FeedState.DOWN, reason="requested")

    def _require_session(self, verb: str) -> None:
        if not self._connected:
            raise BrokerNotConnected(f"{verb} called with no session")

    # ------------------------------------------------------------------
    # §2A:89 subscribe / unsubscribe
    # ------------------------------------------------------------------
    async def subscribe(self, symbol: Symbol) -> None:
        """Subscribe to the DELAYED stream. Refuses to request a mode this venue cannot grant.

        THE SENTINEL IS THE POINT (GAP-D3, `docs/CHECK-DEBT.md` D1.13). `granted_mode` is set
        to `UNKNOWN` here, BEFORE the request, and only `_on_ib_market_data_type` may move it.
        ARC 013 measured `ib_async`'s `Ticker.marketDataType` defaulting to 1, so a naive read
        reports "real-time granted" for a subscription that returned zero ticks and error 354.
        Sentinelling first makes an absent callback readable as an absent callback."""
        self._require_session("subscribe")
        if self._requested_mode is MarketDataMode.REALTIME:
            raise BrokerUnsupported(self._realtime_refusal(symbol))
        state = self._symbols.setdefault(symbol, _SymbolFeedState())
        # WRITER 1 of granted_mode. MEANING: "no grant callback has been received for this
        # subscription". NOT "the venue granted UNKNOWN" and NOT the requested mode.
        state.granted_mode = MarketDataMode.UNKNOWN
        state.requested_mode = self._requested_mode
        if self._ib is not None:
            self._ib.reqMarketDataType(self._requested_mode.value)
            self._ib.reqMktData(symbol)

    async def unsubscribe(self, symbol: Symbol) -> None:
        """Cancel the subscription. Idempotent: unsubscribing an unheld symbol is not an error,
        because `nics_risk_subsystem_spec_v1.3.md` §2A:89 declares no precondition on it."""
        if self._ib is not None and self._connected and symbol in self._symbols:
            self._ib.cancelMktData(symbol)
        self._forget_symbol(symbol)

    def _forget_symbol(self, symbol: Symbol) -> None:
        """Drop a symbol's subscription state. The grant does not survive the subscription."""
        self._symbols.pop(symbol, None)

    def request_realtime_ticks(self, symbol: Symbol) -> None:
        """The real-time path. EXISTS ONLY TO REFUSE, and refuses loudly.

        A capability that is absent must be STATED as absent, and a consumer must not be able
        to call a path that does not exist and receive silence. Without this method a caller
        reaching for `reqTickByTickData` finds nothing at all on the adapter and concludes the
        feature is unbuilt rather than unavailable — two different facts."""
        raise BrokerUnsupported(self._realtime_refusal(symbol))

    def _realtime_refusal(self, symbol: Symbol) -> str:
        """The refusal text. One spelling, so the two call sites cannot disagree.

        It names GAP-D2 deliberately: `reqHistoricalTicks` is the first thing a reader reaches
        for after seeing 10189, and it is not a way around it."""
        return (
            f"GAP-D1: no real-time tick stream on this account, so {symbol} cannot be served "
            f"real-time by any request. reqTickByTickData -> Err "
            f"{IB_ERR_NO_REALTIME_PERMISSION} ('No market data permissions for CME FUT' — the "
            f"PRODUCT CLASS, so no instrument choice reaches around it); "
            f"reqMarketDataType(1)+reqMktData -> error "
            f"{IB_ERR_NOT_SUBSCRIBED_DELAYED_AVAILABLE} with NO grant callback and 0 ticks in "
            f"40 s. GAP-D2: reqHistoricalTicks is NOT a back door — it is delayed by the same "
            f"~10 minutes (ARC 010 624 s, unread at the time; ARC 013 re-measured 604 s). The "
            f"working paths are reqMarketDataType(3)+reqMktData and polled history, both "
            f"delayed. Real-time is an account-level subscription changed only in IBKR Account "
            f"Management, and docs/dev_and_services_plan.md records the decision NOT to buy one."
        )

    # ------------------------------------------------------------------
    # §2A Nix addition: feed_lag
    # ------------------------------------------------------------------
    def feed_lag(self, symbol: Symbol | None = None) -> FeedLag:
        """How far behind the venue this feed runs, WITH the provenance of the answer.

        `symbol=None` answers for the adapter as a whole, using every symbol's samples. The
        parameter is optional so the port's zero-argument signature is satisfied unchanged.

        THE FOUR STATES THIS RETURNS, and none of them is a fabricated zero:
          * no lag record configured and nothing observed -> UNOBSERVED, `declared_lag_s=None`
          * a banked prior-arc figure, nothing observed here -> PRIOR_ARC, agreement
            NOT_OBSERVED, and `detail` carries the citation and the re-measurement obligation
          * samples collected -> OBSERVED, and the declared figure is CHECKED against them, so
            a divergence becomes `LagAgreement.DIVERGED`, readable off the object
          * a venue that declares a figure this adapter has not checked -> VENDOR_DECLARED"""
        samples = self._lag_samples(symbol)
        declared, detail = (
            self._lag_record.as_declared() if self._lag_record else (None, "")
        )
        if not samples:
            provenance = (
                LagProvenance.PRIOR_ARC
                if declared is not None
                else LagProvenance.UNOBSERVED
            )
            return FeedLag(
                declared_lag_s=declared,
                observed_lag_s=None,
                observed_n=0,
                provenance=provenance,
                granted_mode=self.granted_mode(symbol),
                detail=detail
                or "no lag record configured and no packet carrying a venue timestamp",
            )
        return FeedLag(
            declared_lag_s=declared,
            observed_lag_s=sum(samples) / len(samples),
            observed_n=len(samples),
            provenance=LagProvenance.OBSERVED,
            granted_mode=self.granted_mode(symbol),
            detail=detail,
        )

    def _lag_samples(self, symbol: Symbol | None) -> list[float]:
        if symbol is not None:
            state = self._symbols.get(symbol)
            return list(state.lag_samples) if state else []
        return [s for st in self._symbols.values() for s in st.lag_samples]

    def granted_mode(self, symbol: Symbol | None = None) -> MarketDataMode:
        """The mode the venue GRANTED. `UNKNOWN` is the floor, never the requested mode.

        With `symbol=None` this is the adapter-wide answer, and it is deliberately the
        PESSIMISTIC one: if any subscription is ungranted the answer is `UNKNOWN`, and if two
        subscriptions were granted different modes the answer is `UNKNOWN` rather than one of
        them. A single mode reported for a set that does not share one is a fabricated
        value."""
        if symbol is not None:
            state = self._symbols.get(symbol)
            return state.granted_mode if state else MarketDataMode.UNKNOWN
        modes = {st.granted_mode for st in self._symbols.values()}
        return modes.pop() if len(modes) == 1 else MarketDataMode.UNKNOWN

    def granted_mode_divergence(self, symbol: Symbol) -> str:
        """'' when the grant matches the request, else the divergence, as a READABLE finding.

        `docs/CHECK-DEBT.md` D1.13's owed behaviour: *assert the granted marketDataType and
        FAIL on a silent downgrade — never infer the mode from the request.* ARC 013 measured
        mode 4 being granted as mode 3 with no error and no notice. A log line would satisfy
        nobody; this is a value a gate and a consumer can both read."""
        state = self._symbols.get(symbol)
        if state is None:
            return f"{symbol} is not subscribed"
        if state.granted_mode is MarketDataMode.UNKNOWN:
            return (
                f"{symbol}: requested {state.requested_mode.name}, NO GRANT CALLBACK received "
                f"— the mode in effect is unknown and must not be assumed to be the requested "
                f"one (ARC 013 measured ib_async's Ticker.marketDataType defaulting to 1)"
            )
        if state.granted_mode is not state.requested_mode:
            return (
                f"{symbol}: SILENT DOWNGRADE — requested {state.requested_mode.name} "
                f"({state.requested_mode.value}), venue granted {state.granted_mode.name} "
                f"({state.granted_mode.value})"
            )
        return ""

    # ------------------------------------------------------------------
    # FRESHNESS — derived here, because the venue pushes none (GAP-D4)
    # ------------------------------------------------------------------
    def evaluate_freshness(self, now: float, symbol: Symbol | None = None) -> FeedState:
        """Derive and publish feed health from excess staleness. The ONLY writer of STALE.

        `capabilities.pushes_feed_status` is False: IBKR reports no feed-health signal, so
        `nics_risk_subsystem_spec_v1.3.md` §2A:92's `on_feed_status` has to be DERIVED, and
        saying so is the difference between a declared derivation and a fabricated venue
        signal.

        THE COMPUTATION IS `FeedLag.excess_staleness_s`, i.e. `(now - venue_ts) - lag`, and it
        is vendor-blind by construction: the same threshold is correct on a 0-lag venue and on
        the Stage 0 IBKR feed. `None` (cannot compute) is treated as STALE — fail closed and
        loud (`CLAUDE.md` directive 4): a freshness question this adapter cannot answer is not
        an answer of 'fresh'."""
        self._require_session("evaluate_freshness")
        targets = [symbol] if symbol is not None else list(self._symbols)
        if not targets:
            return self._feed_state
        worst = FeedState.UP
        for sym in targets:
            state = self._symbols.get(sym)
            # Per-symbol lag, not an adapter-wide one: two subscriptions can be granted
            # different modes (see `granted_mode`), and averaging their samples would produce
            # a lag figure true of neither.
            excess = (
                self.feed_lag(sym).excess_staleness_s(state.last_tick_venue_ts, now)
                if state
                else None
            )
            if excess is None or excess > self._stale_threshold_s:
                worst = FeedState.STALE
        # WRITER 4 of _feed_state. MEANING: a session exists AND the data behind it is (not)
        # advancing. This is the ONLY writer entitled to say STALE; connect/disconnect speak
        # only about the session, and conflating the two is how a live socket with a dead feed
        # reads as healthy.
        self._publish_feed_state(
            worst,
            reason=f"derived from excess staleness over {len(targets)} symbol(s)",
            symbol=symbol,
        )
        return worst

    def _publish_feed_state(
        self, state: FeedState, *, reason: str, symbol: Symbol | None = None
    ) -> None:
        """The ONE emission site for `on_feed_status`.

        A choke point rather than four call sites, on the same reasoning ARC 020 A3 recorded
        for `_publish_session` on the order path — reached independently here, and NOT by
        importing that method (see the invariant 3 block). Four writers with four emission
        sites is four chances for one of them to publish a state it is not entitled to."""
        self._feed_state = state
        self._sink.on_feed_status(state, symbol, reason)

    def feed_state(self) -> FeedState:
        """The last published feed state. Observable, not a log line."""
        return self._feed_state

    # ------------------------------------------------------------------
    # STREAM PATH — §2A:91 on_tick
    # ------------------------------------------------------------------
    def _on_ib_tick(
        self,
        symbol: Symbol,
        price: float | None,
        size: float | None,
        venue_ts: float | None,
        recv_ts: float | None = None,
    ) -> None:
        """One delayed-stream packet. THE ONLY WRITER of the tick clocks and the lag samples.

        ABSENCE IS PASSED THROUGH, NEVER FILLED IN (`docs/SPEC-AMENDMENTS.md` AMENDMENT 3). A
        packet with no size emits `size=None`; a packet with no venue timestamp emits
        `venue_ts=None` and this machine's clock is NOT substituted, because
        `nics_risk_subsystem_spec_v1.3.md` §2A:106-107 invariant 4 governs that field and a
        local clock wearing a venue field's name is the fabrication the amendment names.

        `recv_ts` IS ALWAYS PRESENT, because it is a fact about US: the packet arrived, and the
        moment it arrived is not in doubt. It is what lets a consumer tell a dead transport
        from a wedged feed — see `FeedLag.excess_staleness_s`."""
        state = self._symbols.get(symbol)
        if state is None:
            return  # not ours: another subscription, or one already cancelled
        stamp = time.time() if recv_ts is None else recv_ts
        state.last_tick_recv_ts = stamp
        if venue_ts is not None:
            state.last_tick_venue_ts = venue_ts
            state.lag_samples.append(stamp - venue_ts)
        self._sink.on_tick(symbol, price, size, venue_ts, recv_ts=stamp)

    def _on_ib_market_data_type(self, symbol: Symbol, mode_value: int) -> None:
        """The venue's GRANT callback. WRITER 2 of `granted_mode`, and the only one that may
        report an actual mode.

        MEANING: the venue affirmatively told us which mode it is serving. That is the only
        thing that moves this field off `UNKNOWN`, which is what makes an absent callback
        readable (GAP-D3)."""
        state = self._symbols.get(symbol)
        if state is None:
            return
        # The mapping is `resolve_granted_mode` (module level, D1.32) rather than inline,
        # so the three-way rule this writer depends on is drivable by a gate instead of
        # being sealed inside a vendor callback. Behaviour is unchanged.
        granted = resolve_granted_mode(mode_value)
        if (
            granted is MarketDataMode.UNKNOWN
            and mode_value != MarketDataMode.UNKNOWN.value
        ):
            # An unrecognised mode is NOT coerced to the requested one, nor to REALTIME. It is
            # an unknown, and an unknown that reads as a known is the failure the floor exists
            # to prevent. Logged here, not in the pure resolver, because `symbol` is what
            # makes the line worth reading.
            log.warning("unrecognised marketDataType %r for %s", mode_value, symbol)
        state.granted_mode = granted

    def _on_ib_error(self, reqId, errorCode, errorString, contract=None) -> None:
        """Market-data errors. Maps ONLY codes this system has measured.

        The evidence gate is `IB_MARKETDATA_EVIDENCE`: a code absent from it gets no meaning
        here, however plausible IBKR's documentation makes one. Note that
        `IB_ERR_DISPLAYING_DELAYED` (10167) is the informational companion of a WORKING
        subscription and must never be read as a failure — ARC 013 measured it alongside 18
        ticks in 40 s."""
        if errorCode == IB_ERR_DISPLAYING_DELAYED:
            log.info("delayed data in effect (%s): %s", errorCode, errorString)
            return
        if errorCode in (
            IB_ERR_NO_REALTIME_PERMISSION,
            IB_ERR_NOT_SUBSCRIBED_DELAYED_AVAILABLE,
        ):
            log.warning(
                "real-time refused (%s): %s | evidence: %s",
                errorCode,
                errorString,
                IB_MARKETDATA_EVIDENCE[errorCode],
            )
            return
        log.warning("unmapped market-data error %s: %s", errorCode, errorString)

    # ------------------------------------------------------------------
    # POLL PATH — GAP-D4, and D1.14's seal
    # ------------------------------------------------------------------
    async def poll_history(self, symbol: Symbol, *, attempts: int | None = None) -> int:
        """Poll historical bars. Returns the number of rows the venue returned.

        ASYNC (D1.38): it round-trips to the venue, repeatedly and by design. `attempts` is an
        adapter-local knob and is keyword-only, so `BrokerDatafeedPort`'s declared shape
        `poll_history(symbol) -> int` is satisfied unchanged — the same additive construction
        `on_ack`'s `reject_category` uses.

        THE BOUNDED LOOP IS SPEC-MANDATED, NOT A LAPSE. `nics_risk_subsystem_spec_v1.3.md`
        §6.4:373-374 requires retry/backoff BEFORE a feed is declared stale, §12A:827 names the
        `RETRY_BACKOFF` tunable, and §13:900 repeats it. This is a POLLER, which is outside the
        order path — `checks/check_order_path_bans.py`'s own docstring records that the
        boundary between banned and required is one directory wide, and that a gate reddening
        spec-mandated poller behaviour is repaired at its SCOPE and never at the ban.

        WHAT IS STILL FORBIDDEN HERE AND IS NOT DONE: no `tenacity`, no `backoff`, no
        `retrying`, no `asyncio.run`, no `run_until_complete`, no `run_forever`, and no retry
        of any send verb — this library has none, and that is invariant 3 doing its job.

        EXHAUSTION RAISES. It does not return 0 rows, because 0 rows is a real answer meaning
        the venue had nothing, and 'the venue had nothing' must never be the same reading as
        'we could not reach the venue' (AMENDMENT 3, and `debug.md` §7.9)."""
        self._require_session("poll_history")
        if self._history_source is None:
            raise BrokerUnsupported(
                "poll_history() called with no history source. Returning zero rows here would "
                "make 'not wired up' indistinguishable from 'the venue had nothing'"
            )
        budget = self._poll_attempts if attempts is None else attempts
        for _ in range(budget):
            self._poll_seq += 1
            started = time.time()
            try:
                rows = list(self._history_source(symbol))
            except Exception as exc:  # noqa: BLE001  # see the module pragma block
                self._poll_attempt_log.append(
                    PollAttempt(
                        self._poll_seq, symbol, started, ok=False, error=repr(exc)
                    )
                )
                continue
            self._poll_attempt_log.append(
                PollAttempt(self._poll_seq, symbol, started, ok=True, rows=len(rows))
            )
            # WRITER of last_poll_recv_ts, and the ONLY one. See _SymbolFeedState for why this
            # is not the same field as last_tick_recv_ts.
            state = self._symbols.setdefault(symbol, _SymbolFeedState())
            state.last_poll_recv_ts = time.time()
            self._ingest_history(symbol, rows, state.last_poll_recv_ts)
            return len(rows)
        raise FeedPollExhausted(
            f"poll_history({symbol}) exhausted {budget} attempt(s) without a response. "
            f"Attempts: {[a.error for a in self._poll_attempt_log[-budget:]]}"
        )

    def _ingest_history(self, symbol: Symbol, rows, recv_ts: float) -> None:
        """SEAL AND NEVER REWRITE (`docs/CHECK-DEBT.md` D1.14).

        A row whose seal key is unseen is sealed and published on `on_bar`, exactly once. A row
        whose seal key is already sealed is NEVER written over: if its payload differs, a
        `BarRevision` is published on `on_bar_revision` and retained; if it is identical, it is
        dropped, because an identical re-poll is not a revision and a stream of no-op
        revisions is how a real one becomes invisible.

        WHY THE ADAPTER OWNS THIS AND NOT THE CONSUMER: the re-poll happens HERE. A consumer
        holding only what crossed the seam sees a second bar with the same start time and no
        way to know whether the venue corrected itself or it double-subscribed. Both stories
        exist only at this layer, which is the argument for the rule living here.

        AND THIS IS THE ONLY `Bar(...)` IN THE MODULE — AMENDMENT 4's proof-by-absence half. The
        source is `POLLED_HISTORY` because the venue is the source; nothing here aggregates a
        tick, and `Bar.__post_init__` refuses one that did."""
        for row in rows:
            key = (symbol, row["bar_start_venue_ts"], row["period_s"])
            sealed = self._sealed.get(key)
            if sealed is None:
                self._seal_seq += 1
                bar = Bar(
                    symbol=symbol,
                    bar_start_venue_ts=row["bar_start_venue_ts"],
                    period_s=row["period_s"],
                    # SUBSCRIPTED, NOT `.get()` — AMENDMENT 3's ARC 022 refinement. These four
                    # are the bar; a row that omits one is MALFORMED, and `_require_ohlc` says
                    # so by name rather than letting a bare KeyError name a dict access. ARC 021
                    # wrote `.get()` here, which turned a malformed row into a bar with a null
                    # open — an absence the venue never declared, manufactured by the reader.
                    **self._require_ohlc(symbol, row),
                    # `.get()` SURVIVES on volume, and only on volume: IBKR genuinely returns
                    # bars for which volume is not a fact (see `Bar.volume`).
                    volume=row.get("volume"),
                    recv_ts=recv_ts,
                    source=BarSource.POLLED_HISTORY,
                    seal_seq=self._seal_seq,
                )
                self._sealed[key] = bar
                self._sink.on_bar(bar)
                continue
            self._maybe_revise(sealed, row, recv_ts)

    @staticmethod
    def _require_ohlc(symbol: Symbol, row) -> dict[str, float]:
        """The four structurally-guaranteed payload fields, or a loud refusal.

        `docs/SPEC-AMENDMENTS.md` AMENDMENT 3 REFINEMENT (ARC 022): an optional type is
        justified by an OBSERVABLE ABSENCE, and there is none here — a venue that has no open
        has no bar to return. So a row without one is not a bar with an absent open; it is a
        MALFORMED ROW, and the two must not read the same. Refusing is `CLAUDE.md` directive 4
        (fail closed and loud) applied to the reader rather than to the type: `Bar` already
        refuses to hold `None` in these fields, and this is where the refusal acquires the
        symbol, the field name and the bar's start time that make it diagnosable."""
        missing = [f for f in BAR_REQUIRED_PAYLOAD_FIELDS if row.get(f) is None]
        if missing:
            raise MalformedBarRow(
                f"{symbol} bar at {row.get('bar_start_venue_ts')!r}: missing "
                f"{', '.join(missing)}. These four are the bar and their presence is "
                "structurally guaranteed by a bar existing, so an absence here is a malformed "
                "row and NOT a venue absence (docs/SPEC-AMENDMENTS.md AMENDMENT 3, ARC 022 "
                "refinement). Nothing is defaulted: a null open manufactured by this reader "
                "would be exactly the substitution the amendment forbids."
            )
        return {f: row[f] for f in BAR_REQUIRED_PAYLOAD_FIELDS}

    def _maybe_revise(self, sealed: Bar, row, recv_ts: float) -> None:
        """Publish a revision iff the venue's new story DIFFERS from the sealed one."""
        revised = tuple(row.get(name) for name in BAR_PAYLOAD_FIELDS)
        if revised == sealed.payload():
            return
        differing = tuple(
            name
            for name, was, now in zip(
                BAR_PAYLOAD_FIELDS, sealed.payload(), revised, strict=True
            )
            if was != now
        )
        self._revision_seq += 1
        revision = BarRevision(
            sealed=sealed,
            revised_payload=revised,
            differing_fields=differing,
            recv_ts=recv_ts,
            revision_seq=self._revision_seq,
        )
        self._revisions.append(revision)
        self._sink.on_bar_revision(revision)

    # ------------------------------------------------------------------
    # RETAINED OBSERVABLES — the FlattenAttempt construction
    # ------------------------------------------------------------------
    def sealed_bar(self, symbol: Symbol, bar_start_venue_ts: float, period_s: float):
        """The sealed bar for a key, or `None`. `None` means never published — not empty."""
        return self._sealed.get((symbol, bar_start_venue_ts, period_s))

    def sealed_bars(self) -> tuple[Bar, ...]:
        return tuple(sorted(self._sealed.values(), key=lambda b: b.seal_seq))

    def bar_revisions(self) -> tuple[BarRevision, ...]:
        """Every revision, retained. Observable even where no sink was listening — the same
        reason `FlattenAttempt` is retained rather than returned."""
        return tuple(self._revisions)

    def poll_attempts(self) -> tuple[PollAttempt, ...]:
        return tuple(self._poll_attempt_log)

    def last_tick_recv_ts(self, symbol: Symbol) -> float | None:
        state = self._symbols.get(symbol)
        return state.last_tick_recv_ts if state else None

    def last_poll_recv_ts(self, symbol: Symbol) -> float | None:
        state = self._symbols.get(symbol)
        return state.last_poll_recv_ts if state else None
