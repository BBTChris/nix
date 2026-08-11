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
#   too-many-public-methods
#       Crossed 20 in ARC 023 (20 -> 22). The two that crossed it are
#       `freshness()` — AMENDMENT 6's per-channel authority — and the retained
#       observables `unpublished_seals()` / `polled_symbols()` /
#       `last_bar_venue_ts()`, each of which exists because a property that is
#       not readable is a property nothing can gate on (CLAUDE.md directive 1).
#       The available alternative is to make them private and have the tests
#       reach into `_unpublished` and `_polled`, which is the indirection
#       directive 2 forbids and would leave a future gate with nothing to bind
#       to. Merging them into one accessor returning a dict would satisfy the
#       count and reintroduce the two-facts-one-name shape D1.29 records.
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
# pylint: disable=too-many-positional-arguments,too-many-public-methods
# pylint: disable=missing-function-docstring,disallowed-name,too-many-lines
import logging
import time
from collections import deque
from dataclasses import dataclass, field

from broker_seam import (
    BAR_PAYLOAD_FIELDS,
    BAR_REQUIRED_PAYLOAD_FIELDS,
    LAG_SAMPLE_FLOOR,
    LAG_WINDOW_MAX_SAMPLES,
    LAG_WINDOW_S,
    Bar,
    BarRevision,
    BarSource,
    BrokerNotConnected,
    BrokerUnsupported,
    ChannelFreshness,
    ChannelState,
    DatafeedCapabilities,
    DatafeedEventSink,
    FeedChannel,
    FeedLag,
    FeedPollExhausted,
    FeedState,
    FreshnessReport,
    LagProvenance,
    LagWindow,
    LagWindowBound,
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


IB_VOLUME_NOT_REPORTED = -1.0
"""IBKR's own not-reported sentinel on `BarData.volume`. TRANSLATED AT THIS BOUNDARY, not
passed through — `docs/CHECK-DEBT.md` D1.39/D1.40.

WHY IT LIVES HERE AND NOT IN `broker_seam.py`: it is a VENDOR value, and
`nics_risk_subsystem_spec_v1.3.md` §2A:104-105 invariant 2 is *"no vendor type crosses the
line"*. A sentinel is a vendor type wearing a float's clothes: the seam's `Bar.volume` says
`None` means not reported, and `-1.0` means the venue said minus one contract traded. Both
readings cannot be true of one field, so the translation happens on the vendor side of the
boundary — which is this module — and the seam never learns the number.

EVIDENCE GRADE, UNCHANGED BY THE TRANSLATION AND STATED SO IT IS NOT LAUNDERED: the `-1`
sentinel is **IBKR-DOCUMENTED AND HAS NEVER BEEN MEASURED ON THIS SYSTEM** — no bar poll has
run against the live venue in any arc to date. It is `LagProvenance.VENDOR_DECLARED`-grade
evidence, exactly as `broker_seam.Bar.volume`'s docstring records, and **translating it is not
measuring it**. KNOWN-RED, and the marker names the discharge: the tap session in
`downloads/tap_session_runbook.md` is the procedure that would poll real history and observe
whether `-1` arrives. Until it runs, D1.39/D1.40 stay open.

WHAT IS DELIBERATELY NOT TRANSLATED: any other negative volume. IBKR documents ONE sentinel
and this module maps only codes and values this system has evidence for
(`IB_MARKETDATA_EVIDENCE`'s rule, applied to a value rather than an error code). A blanket
`volume < 0 -> None` would give a meaning to values no document assigns one to, which is the
fabrication the boundary exists to stop, in the other direction."""


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
    channel: FeedChannel = FeedChannel.TICK
    """WHICH channel this record measures (AMENDMENT 6). NOT DECORATION — it is what makes the
    tick figure structurally unusable as the poll figure: the constructor refuses a record whose
    `channel` is not the one it is being installed for. ARC 023's brief states the rule in
    prose (*"DO NOT substitute the tick channel's 600.0-601.9 s figure for it"*) and a rule in
    prose is enforced by whoever remembers it (`VERIFY-AND-CHECKS.md` A.5)."""

    provenance: LagProvenance = LagProvenance.PRIOR_ARC
    """THE GRADE OF THIS FIGURE, carried on the record rather than assumed by the reader.
    `PRIOR_ARC` for a measurement an earlier arc banked; `VENDOR_DECLARED` for a number a vendor
    or an operator asserts and nothing in this tree has checked. There is no path by which this
    field becomes `OBSERVED` — that provenance belongs to samples this session collected, and a
    configured record is not one."""

    def as_declared(self) -> tuple[float, str]:
        """(scalar to declare, the detail string that says what the scalar is).

        THE WORDING IS DERIVED FROM `provenance`, never typed per record: a VENDOR_DECLARED
        figure that described itself as a replayed measurement would be the laundering this
        whole grade exists to prevent."""
        if self.provenance is LagProvenance.VENDOR_DECLARED:
            detail = (
                f"VENDOR_DECLARED for the {self.channel.value} channel — a vendor/operator "
                f"claim that NOTHING IN THIS TREE HAS CHECKED. Range {self.low_s}-"
                f"{self.high_s} s, {self.mean_s} s declared. Source: {self.citation}. "
                f"KNOWN-RED: measurement is OWED and the tap that would take it is "
                f"~/nix/downloads/tap_session_runbook.md. It is NOT a measurement, and the "
                f"tick channel's measured figure is NOT a substitute for it."
            )
        else:
            detail = (
                f"{self.arc} measurement of the {self.channel.value} channel, replayed — NOT "
                f"measured this session. Banked record is a RANGE {self.low_s}-{self.high_s} s "
                f"(spread {self.spread_s} s, n={self.n}); {self.mean_s} s is its MEAN. "
                f"Source: {self.citation}. RE-MEASUREMENT IS OWED: no tap session ran in "
                f"ARC 021 (~/nix/downloads/TAP_SESSION.md does not exist)."
            )
        return self.mean_s, detail


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

IB_POLL_LAG_RECORD: Stage0LagRecord | None = None
"""THE POLL CHANNEL'S LAG. **ABSENT**, and the absence is the honest answer, not an omission.

`docs/SPEC-AMENDMENTS.md` AMENDMENT 6 computes excess staleness per channel *"with the
CHANNEL'S OWN lag"*. This module therefore needs a poll-channel figure — and **there is none.**

WHAT IS AND IS NOT AVAILABLE, because the tempting substitutions are all one line away:

  * `IB_STAGE0_DELAYED_LAG` (600.0-601.9 s, ARC 013) measures the **delayed tick STREAM**
    (`reqMarketDataType(3)` + `reqMktData`). It is not this channel's figure and installing it
    here is the substitution AMENDMENT 3 forbids **wearing a plausible number** — which is
    still a substitution. REFUSED STRUCTURALLY, not by comment: `Stage0LagRecord.channel` is
    `TICK` on that record and the constructor refuses a non-`POLL` record for this slot.
  * ARC 010's **624 s** measures `reqHistoricalTicks` staleness — a different API call and a
    different quantity, on the path GAP-D2 exists to say is not a back door. The module
    docstring already records that merging it produces a lag attributed to an arc that never
    computed one.
  * IBKR publishes no figure this tree holds a citation for. A number recalled rather than
    read is not a vendor declaration; it is a fabrication with a vendor's name on it.

SO THE DEFAULT IS `None`, and the consequence is stated rather than hidden: the poll channel
reports `ChannelState.CANNOT_MEASURE`, which is **not** `STALE` and does not drive
`nics_risk_subsystem_spec_v1.3.md` §6.4:373-374's halt-and-flatten. That is the F21 repair —
the defect was a channel that could not be measured reading as a channel that had failed.

**KNOWN-RED. GRADE: `LagProvenance.VENDOR_DECLARED` the moment a figure exists**, never
`OBSERVED` and never `PRIOR_ARC`, because no arc has measured this channel. THE TAP THAT
DISCHARGES IT: `~/nix/downloads/tap_session_runbook.md` — an operator session against the live
Gateway that polls real history and measures `(recv_ts - bar_start_venue_ts)` on the poll path,
exactly as ARC 013 did for the stream. Until it runs, the number is owed and this stays `None`.
An operator may inject one today via `IBKRBrokerDatafeed(poll_lag_record=...)`; it is graded
`VENDOR_DECLARED` on arrival and the adapter never promotes it."""


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
    """THE ATTEMPT SUCCEEDED END TO END: the venue answered AND every row it returned reached
    the sink. **ARC 023 (F13) NARROWED THIS**, and the narrowing is the point.

    It used to mean only *the venue answered*, and it was written BEFORE the rows were
    ingested — so a poll whose consumer raised half way through recorded `ok=True, rows=4` over
    a bar that was sealed, never published and never recoverable. A green attempt record over a
    lost bar is `debug.md` §7.12's own family (the instrument was green and the subject was
    never in scope), arriving inside the product rather than inside an instrument.

    The transport fact did not disappear; it moved to `venue_answered`, because two facts under
    one name is exactly the `avg_price` shape (`docs/CHECK-DEBT.md` D1.29)."""

    error: str = ""
    venue_answered: bool = False
    """THE TRANSPORT FACT, alone: the history source returned without raising. `ok` is this AND
    delivery; this one is what the bounded retry loop is actually about."""

    rows: int = 0
    """Rows the venue returned on this attempt."""

    sealed: int = 0
    """Rows this attempt sealed for the first time."""

    published: int = 0
    """Bars this attempt handed to the sink and that the sink accepted. Includes re-publications
    of seals an EARLIER attempt failed to deliver — see `_publish_sealed`."""

    revised: int = 0
    """`BarRevision`s this attempt published."""

    undelivered: int = 0
    """Seals from THIS attempt's rows that the sink has still not accepted when the attempt
    ended. Non-zero is the F13 loss, named and countable; `ok` is False whenever it is."""

    def __post_init__(self) -> None:
        """`ok` MAY NOT BE ASSERTED OVER A LOSS. Structural, so a future edit to the poll loop
        cannot reintroduce the green-over-a-lost-bar record by forgetting the rule."""
        if self.ok and (self.undelivered or not self.venue_answered):
            raise ValueError(
                f"PollAttempt(seq={self.seq}, {self.symbol}) claims ok=True with "
                f"venue_answered={self.venue_answered} and undelivered={self.undelivered}. "
                "An attempt is ok only where the venue answered AND everything it returned "
                "reached the sink; anything else is a success reported over a lost bar"
            )


@dataclass
class _IngestTally:
    """What ONE ingest actually did, accumulated as it goes. ARC 023, F13.

    MUTABLE AND PASSED IN, deliberately: `_record_response` reads it from a `finally`, so it
    has to hold the PARTIAL result of an ingest that raised. A return value cannot — an
    exception discards it, which is precisely how `ok=True, rows=4` came to stand over a bar
    that never reached the consumer."""

    sealed: int = 0
    published: int = 0
    revised: int = 0
    keys: set[tuple[Symbol, float, float]] = field(default_factory=set)
    """Seal keys this ingest touched. The attempt record intersects it with the outstanding
    publication debt, so `undelivered` counts only bars THIS response was responsible for."""

    newest_bar_venue_ts: float | None = None
    """The newest `bar_start_venue_ts` this ingest saw — the poll channel's freshness stamp
    (AMENDMENT 6). `None` == the response carried no rows."""


@dataclass
class _LagWindowStore:
    """The BOUNDED lag-sample window for one symbol's tick channel. ARC 023, F17.

    WHAT F17 MEASURED, and it is the reason this type exists rather than a list: `lag_samples`
    was an unbounded list and `feed_lag()` recomputed a SESSION-WIDE mean over it on every
    call. The load-bearing observable was wrong IN THE DIRECTION THAT MATTERS — the session
    mean read `AGREES` at 602.97 s while the last 100 packets sat at 900 s, sixty tolerances
    outside, measured at 10,100 ticks. It said the feed agreed while the feed had degraded by
    300 s, and the dilution is arithmetic, so the longer the session had been healthy the
    harder a real degradation was to see.

    THE WINDOW IS BOUNDED BY TIME, NOT BY COUNT, and that is an invariant rather than a
    preference. MEASURED ARC 023: a 100-sample count window spans 222.2 s at ARC 013's measured
    rate (18 ticks / 40 s on MESU6) and 0.000028 s at this box's measured ingest ceiling
    (3,561,839 samples/s). One count cannot mean one thing at both ends of that range, and
    `debug.md` §7.4 names the class — a count is a literal about the current rate.

    MEMORY IS BOUNDED REGARDLESS OF RATE, WHICH A TIME WINDOW ALONE DOES NOT ACHIEVE. MEASURED:
    at the ingest ceiling a pure 60 s window would retain 213,710,318 samples = 20.5 GB. So
    there is a second, COUNT bound — the memory backstop — and **which bound applied is
    reported** on `LagWindow.bound`, because under `COUNT` the retained set spans less than
    `window_s` and the mean answers a narrower question than the consumer asked.

    THE SESSION FIGURE IS RETAINED AND IS INFORMATIONAL. It is a running sum and count, so it
    costs O(1) memory, and it is published on `FeedLag.session_mean_lag_s` under a name of its
    own. **Nothing decides on it** — see that field's docstring for how the separation is
    enforced by absence rather than asserted."""

    window_s: float = LAG_WINDOW_S
    sample_floor: int = LAG_SAMPLE_FLOOR
    max_samples: int = LAG_WINDOW_MAX_SAMPLES

    samples: deque[tuple[float, float]] = field(default_factory=deque)
    """`(recv_ts, lag_s)` newest-last. `recv_ts` is retained because the trim is by TIME and a
    lag value alone cannot say when it was taken."""

    session_sum_s: float = 0.0
    session_n: int = 0
    _time_trimmed: bool = False
    _count_trimmed: bool = False

    def record(self, recv_ts: float, lag_s: float) -> None:
        """Add one sample and re-apply both bounds. O(k) in what falls out, not in what stays.

        THE TIME BOUND IS APPLIED AGAINST THE NEWEST SAMPLE, not against `time.time()`: the
        adapter is driven with injected clocks in every test and by a vendor callback in
        production, and reaching for the wall clock here would make the window's width depend
        on how long the process has been idle rather than on the data (`debug.md` §7.4, and the
        same reasoning `EventLog` records against timestamp logs)."""
        self.samples.append((recv_ts, lag_s))
        self.session_sum_s += lag_s
        self.session_n += 1
        cutoff = recv_ts - self.window_s
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
            self._time_trimmed = True
        while len(self.samples) > self.max_samples:
            self.samples.popleft()
            self._count_trimmed = True

    def bound(self) -> LagWindowBound:
        """WHICH bound decided the retained set. COUNT wins where both applied, because it is
        the one that narrowed the answer below what was asked for."""
        if self._count_trimmed:
            return LagWindowBound.COUNT
        if self._time_trimmed:
            return LagWindowBound.TIME
        return LagWindowBound.WITHIN_BOTH

    def describe(self) -> LagWindow:
        span = (
            self.samples[-1][0] - self.samples[0][0] if len(self.samples) > 1 else None
        )
        return LagWindow(
            window_s=self.window_s,
            sample_floor=self.sample_floor,
            max_samples=self.max_samples,
            n_in_window=len(self.samples),
            span_s=span,
            bound=self.bound(),
        )

    def windowed_mean_s(self) -> float | None:
        """The mean over the window, or `None` BELOW THE FLOOR — never a mean over too few
        samples and never a fall-back to the session figure (AMENDMENT 3). `describe()` still
        reports `n_in_window`, so *too few* stays distinguishable from *none*."""
        if len(self.samples) < self.sample_floor:
            return None
        return sum(lag for _, lag in self.samples) / len(self.samples)

    def session_mean_s(self) -> float | None:
        """INFORMATIONAL. No caller in this module makes a decision on it; it is carried onto
        `FeedLag.session_mean_lag_s` and read by nothing else."""
        return self.session_sum_s / self.session_n if self.session_n else None


@dataclass
class _SymbolPollState:
    """Everything this adapter knows about ONE POLLED SYMBOL. **NOT A SUBSCRIPTION.**

    ARC 023, F12. `poll_history` used to call
    `self._symbols.setdefault(symbol, _SymbolFeedState())`, which MANUFACTURED a subscription
    record for a symbol nobody subscribed. Three consequences, and the third is the harm:
    `_SymbolFeedState` is documented as *"Everything this adapter knows about ONE
    subscription"* and stopped being true; the adapter-wide `granted_mode()` collapsed from a
    real grant to `UNKNOWN` because an unrelated poll widened the set it is pessimistic over;
    and a later `unsubscribe()` put a REAL `cancelMktData` on the wire for a subscription this
    library never made — venue-side activity that is not attributable to any intent of this
    library, on a clientId whose entire argument (`DATAFEED_CLIENT_ID`, and the 0/1 refusals)
    is that it must be.

    **POLLING MUST NOT CREATE SUBSCRIPTION STATE.** What the poll legitimately needs to record
    is a POLL observation, so it is a different type in a different map with a different name,
    and there is no path by which a member of `_polled` reaches `cancelMktData`,
    `granted_mode`, or `reqMktData`. That is the ARC 020 A8 per-writer rule applied to a
    container instead of a field, and it is the same argument `last_poll_recv_ts` already
    carried against being merged with `last_tick_recv_ts` — one map holding two kinds of thing
    carries two meanings depending on which writer created the entry."""

    last_poll_recv_ts: float | None = None
    """LOCAL clock at the last POLL response. MOVED HERE FROM `_SymbolFeedState` in ARC 023:
    it was never a fact about a subscription, and its presence there is what made the poll path
    reach for a subscription record in the first place."""

    last_bar_venue_ts: float | None = None
    """The VENUE's own clock on the newest bar this symbol has been polled for — the poll
    channel's freshness stamp under AMENDMENT 6.

    IT IS `bar_start_venue_ts` AND NOT THE BAR'S CLOSE. The close is `start + period_s`, which
    is computed rather than reported, and a computed timestamp in a venue-timestamp field is
    what §2A:106-107 invariant 4 exists to prevent. Using the open is also the conservative
    direction: it is the older of the two, so the channel reads no fresher than it is."""


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

    lag_window: _LagWindowStore = field(default_factory=_LagWindowStore)
    """(recv_ts - venue_ts) per stream packet that carried BOTH, in a BOUNDED window. Written
    by the tick path only.

    IT WAS `lag_samples: list[float]`, UNBOUNDED, until ARC 023 — see `_LagWindowStore` for
    what F17 measured and why the bound is by time with a count backstop rather than by count.

    THE POLL CLOCK IS NO LONGER IN THIS CLASS. `last_poll_recv_ts` moved to
    `_SymbolPollState` in the same arc (F12): "a poll response arrived" was never a fact about
    a subscription, and holding it here is what made `poll_history` reach for a subscription
    record. The ARC 020 A8 per-writer argument that kept it separate from `last_tick_recv_ts`
    is unchanged and is now enforced by the two clocks living in two different maps."""


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
        poll_lag_record: Stage0LagRecord | None = IB_POLL_LAG_RECORD,
        stale_threshold_s: float = 30.0,
        poll_attempts: int = 3,
        history_source=None,
        lag_window_s: float = LAG_WINDOW_S,
        lag_sample_floor: int = LAG_SAMPLE_FLOOR,
        lag_max_samples: int = LAG_WINDOW_MAX_SAMPLES,
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
        self._require_channel(lag_record, FeedChannel.TICK, "lag_record")
        self._require_channel(poll_lag_record, FeedChannel.POLL, "poll_lag_record")
        self._sink = sink
        self._ib = ib
        self._host, self._port, self._client_id = host, port, client_id
        self._requested_mode = requested_mode
        self._lag_record = lag_record
        self._poll_lag_record = poll_lag_record
        self._stale_threshold_s = stale_threshold_s
        self._poll_attempts = poll_attempts
        self._lag_window_s = lag_window_s
        self._lag_sample_floor = lag_sample_floor
        self._lag_max_samples = lag_max_samples
        # Injected so the whole poll path is drivable with no venue. `None` means the caller
        # must supply one before polling — never a silent no-op that reads as "no data".
        self._history_source = history_source

        self._connected = False
        self._feed_state = FeedState.DOWN
        self._symbols: dict[Symbol, _SymbolFeedState] = {}
        # F12: the poll path's OWN map. A member of this one is not a subscription and can
        # reach neither `cancelMktData` nor `granted_mode`. See `_SymbolPollState`.
        self._polled: dict[Symbol, _SymbolPollState] = {}

        # --- D1.14: the seal store and the revision log -------------------------------
        # A bar is published ONCE per seal key and never rewritten. Both structures are
        # adapter-retained and read back through accessors rather than returned from the
        # verbs, which is `FlattenAttempt`'s construction: the §2A signature stays untouched
        # and the addition is visibly an addition.
        self._sealed: dict[tuple[Symbol, float, float], Bar] = {}
        self._revisions: list[BarRevision] = []
        self._seal_seq = 0
        self._revision_seq = 0

        # F13: seal keys whose bar has been sealed and NOT yet accepted by the sink. A SET OF
        # KEYS and never a second store of `Bar`s — two containers holding the same object is
        # how they drift, and `self._sealed` stays the one home a bar lives in.
        self._unpublished: set[tuple[Symbol, float, float]] = set()

        self._poll_attempt_log: list[PollAttempt] = []
        self._poll_seq = 0

    @staticmethod
    def _require_channel(
        record: Stage0LagRecord | None, channel: FeedChannel, slot: str
    ) -> None:
        """A lag record may only be installed on the channel it measured. **F21's structural
        half**, and the reason it is a refusal rather than a comment:

        the tick channel's 600.0-601.9 s figure is measured, real, and one keyword away from
        the poll slot. Installing it there would make the poll channel read as measured while
        nothing had measured it — `docs/SPEC-AMENDMENTS.md` AMENDMENT 3's substitution wearing
        a plausible number, and a plausible number is still a substitution. `VERIFY-AND-CHECKS`
        A.5: if a rule can be stated as a desired state it should be a check, because a rule in
        prose is enforced by whoever remembers it."""
        if record is not None and record.channel is not channel:
            raise ValueError(
                f"{slot}= carries channel={record.channel.value} and this slot is the "
                f"{channel.value} channel. A figure measured on one channel is not a figure "
                f"about another: {record.arc}'s record measures "
                f"{record.channel.value} at {record.mean_s} s, and installing it here would "
                "report the poll channel as measured when nothing has measured it "
                "(docs/SPEC-AMENDMENTS.md AMENDMENT 3 and AMENDMENT 6)"
            )

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
        state = self._symbols.setdefault(symbol, self._new_feed_state())
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

    def _new_feed_state(self) -> _SymbolFeedState:
        """A subscription record carrying THIS adapter's window configuration.

        The knobs are constructor arguments, so a dataclass default cannot supply them — and a
        `_SymbolFeedState()` built anywhere else would silently get the module defaults instead
        of what the operator configured. One construction site is the fix (`debug.md` §7.4: a
        default copied into a second place is a literal that goes stale silently)."""
        return _SymbolFeedState(
            lag_window=_LagWindowStore(
                window_s=self._lag_window_s,
                sample_floor=self._lag_sample_floor,
                max_samples=self._lag_max_samples,
            )
        )

    def _forget_symbol(self, symbol: Symbol) -> None:
        """Drop a symbol's subscription state. The grant does not survive the subscription.

        POLL STATE IS NOT TOUCHED, and that is F12's boundary in the other direction: what the
        venue answered on a history request is not a fact about a subscription, so cancelling
        a subscription does not un-observe it. `_polled` is dropped by nothing today; a poll
        observation's lifetime is its own question and is not this arc's to answer."""
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
    def feed_lag(
        self, symbol: Symbol | None = None, *, channel: FeedChannel = FeedChannel.TICK
    ) -> FeedLag:
        """How far behind the venue this feed runs ON ONE CHANNEL, with the answer's grade.

        `symbol=None` answers for the adapter as a whole, using every symbol's samples. Both
        parameters are optional and `channel` is keyword-only, so `BrokerDatafeedPort`'s
        zero-argument `feed_lag()` is satisfied unchanged — the same additive construction
        `poll_history`'s `attempts` uses.

        THE CHANNEL PARAMETER IS AMENDMENT 6 (ARC 023). Each channel carries its OWN
        `effective_lag_s`, and one figure cannot be right for two paths whose delays and
        evidence grades differ: the tick channel's is MEASURED (ARC 013) and the poll
        channel's is NOT MEASURED ON THIS SYSTEM AT ALL. `channel` defaults to `TICK` because
        that is what every pre-ARC-023 caller of the zero-argument verb meant, and a default
        that silently changed the meaning of an existing call would be worse than the defect.

        THE FIVE STATES THIS RETURNS, and none of them is a fabricated zero:
          * no lag record for this channel and nothing observed -> UNOBSERVED,
            `declared_lag_s=None` (**the poll channel's state on this system today**)
          * a banked prior-arc figure, nothing observed here -> PRIOR_ARC, agreement
            NOT_OBSERVED, and `detail` carries the citation and the re-measurement obligation
          * a configured figure nothing in this tree has checked -> VENDOR_DECLARED, and it is
            never promoted past that by this adapter
          * enough samples in the WINDOW -> OBSERVED, and the declared figure is CHECKED
            against them, so a divergence becomes `LagAgreement.DIVERGED` off the object
          * samples present but BELOW THE FLOOR -> absence is declared
            (`observed_lag_s=None`), and `window.n_in_window` says how many were held. A mean
            over too few samples is a fabricated confidence and falling back to the
            session-wide figure is F17's defect (AMENDMENT 3).

        THE POLL CHANNEL COLLECTS NO SAMPLES, and that is a statement about this system rather
        than about the design: measuring it means comparing `bar_start_venue_ts` against a
        receipt clock across a real venue poll, which no arc has run. See `IB_POLL_LAG_RECORD`
        for the known-red and the tap that discharges it."""
        record = (
            self._lag_record if channel is FeedChannel.TICK else self._poll_lag_record
        )
        declared, detail = record.as_declared() if record else (None, "")
        declared_provenance = (
            record.provenance if record is not None else LagProvenance.UNOBSERVED
        )
        window = self._lag_window(symbol) if channel is FeedChannel.TICK else None
        observed = window.windowed_mean_s() if window is not None else None
        described = window.describe() if window is not None else None
        session_mean = window.session_mean_s() if window is not None else None
        session_n = window.session_n if window is not None else 0
        if observed is None:
            return FeedLag(
                declared_lag_s=declared,
                observed_lag_s=None,
                observed_n=0,
                provenance=(
                    declared_provenance
                    if declared is not None
                    else LagProvenance.UNOBSERVED
                ),
                granted_mode=self.granted_mode(symbol),
                # BOTH halves, never one OR the other. The declared figure's citation and the
                # reason there is no OBSERVATION are different facts, and `detail or ...` hid
                # the second whenever a record existed — which is every configured adapter, so
                # "no reading because too few samples" was unreadable exactly where it matters.
                detail=" | ".join(
                    part
                    for part in (detail, self._no_reading_detail(channel, described))
                    if part
                ),
                channel=channel,
                window=described,
                session_mean_lag_s=session_mean,
                session_n=session_n,
            )
        return FeedLag(
            declared_lag_s=declared,
            observed_lag_s=observed,
            observed_n=described.n_in_window if described else 0,
            provenance=LagProvenance.OBSERVED,
            granted_mode=self.granted_mode(symbol),
            detail=detail,
            channel=channel,
            window=described,
            session_mean_lag_s=session_mean,
            session_n=session_n,
        )

    @staticmethod
    def _no_reading_detail(channel: FeedChannel, window: LagWindow | None) -> str:
        """Why there is no observed figure — the THREE reasons, kept distinct.

        `debug.md` §7.9: a reading that is absent because nothing arrived and a reading that is
        absent because too little arrived are different facts, and a consumer deciding whether
        to wait or to escalate needs to tell them apart."""
        if window is None:
            return (
                f"no lag record configured for the {channel.value} channel and this adapter "
                f"collects no samples on it"
            )
        if window.n_in_window == 0:
            return "no packet carrying a venue timestamp has arrived in the window"
        return (
            f"{window.n_in_window} sample(s) in the {window.window_s} s window, below the "
            f"floor of {window.sample_floor} — absence declared rather than a mean over too "
            f"few, and NOT a fall-back to the session figure"
        )

    def _lag_window(self, symbol: Symbol | None) -> _LagWindowStore | None:
        """The tick-channel window for one symbol, or a MERGED view for the adapter as a whole.

        THE ADAPTER-WIDE MERGE IS BUILT, NOT AVERAGED-OVER-AVERAGES: samples from every
        subscription are re-windowed together against the newest `recv_ts` of the set, so the
        adapter-wide figure obeys the same time bound and the same floor as a per-symbol one.
        Averaging per-symbol means would weight a symbol with three packets equally with one
        that had three hundred."""
        if symbol is not None:
            state = self._symbols.get(symbol)
            return state.lag_window if state else None
        if not self._symbols:
            return None
        merged = _LagWindowStore(
            window_s=self._lag_window_s,
            sample_floor=self._lag_sample_floor,
            max_samples=self._lag_max_samples,
        )
        # SORTED BY RECEIPT CLOCK BEFORE RECORDING. `record()`'s trim assumes non-decreasing
        # `recv_ts` — true of one symbol's packet stream and false of two streams concatenated,
        # and an out-of-order feed into the trim would drop the wrong end of the window.
        for recv_ts, lag_s in sorted(
            (s for st in self._symbols.values() for s in st.lag_window.samples),
            key=lambda pair: pair[0],
        ):
            merged.record(recv_ts, lag_s)
        # The SESSION figures are the true per-symbol totals, not what survived the merge's
        # window. They are informational and nothing decides on them; restating them from the
        # merged deque would make them a second, quietly different number.
        merged.session_sum_s = sum(
            st.lag_window.session_sum_s for st in self._symbols.values()
        )
        merged.session_n = sum(st.lag_window.session_n for st in self._symbols.values())
        return merged

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
    def freshness(
        self, now: float, symbol: Symbol | None = None
    ) -> tuple[FreshnessReport, ...]:
        """PER-CHANNEL freshness, uncollapsed. **THE AUTHORITY** — `docs/SPEC-AMENDMENTS.md`
        AMENDMENT 6 (operator ruling, ARC 023), and the repair for F21.

        *"Each channel by which the seam observes a symbol carries its own venue timestamp and
        its own `effective_lag_s`. The seam declares WHICH CHANNELS ARE FRESH AND WHICH ARE
        STALE, and does not collapse them into a single boolean. ... The consumer decides which
        channels it requires."*

        WHAT F21 MEASURED, because it is the whole reason this method exists.
        `evaluate_freshness` read `last_tick_venue_ts` **alone**. At Stage 0 there is no tick
        stream — `reqTickByTickData` returns 10189 naming the PRODUCT CLASS (GAP-D1) — so a
        symbol fed entirely by successful, current polls had `excess_staleness_s = None`, which
        the adapter correctly treated as STALE, which
        `nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 turns into *halt new entries AND
        flatten open*. **The module fail-closed on the only margin-class path it has**
        (GAP-D4). A bar's venue timestamp is a venue observation exactly as a tick's is; the
        defect was that only one channel updated the stamp.

        `symbol=None` reports on every symbol this adapter observes on ANY channel — the union
        of subscriptions and polled symbols. A symbol it has never heard of yields a report
        with NO channels, which is a different fact from every channel being stale and reads as
        one (`FreshnessReport.observed_channels` is empty).

        THIS IS THE ONLY PUBLISHER of §2A:92's `on_feed_status` on the freshness path, and the
        state it publishes is derived from the report by `_channel_floor` — see there for the
        one decision the frozen event forces the seam to make and how narrow it is kept."""
        self._require_session("freshness")
        targets = (
            [symbol]
            if symbol is not None
            else sorted(set(self._symbols) | set(self._polled))
        )
        reports = tuple(self._report_for(sym, now) for sym in targets)
        for report in reports:
            # WRITER 4 of _feed_state. MEANING: a session exists AND the data behind it is (not)
            # advancing. This is the ONLY writer entitled to say STALE; connect/disconnect speak
            # only about the session, and conflating the two is how a live socket with a dead
            # feed reads as healthy.
            self._publish_feed_state(
                self._channel_floor(report),
                reason=(
                    f"derived per channel (docs/SPEC-AMENDMENTS.md AMENDMENT 6): "
                    f"{report.summary()}"
                ),
                symbol=report.symbol,
            )
        return reports

    def _report_for(self, symbol: Symbol, now: float) -> FreshnessReport:
        """One symbol's channels. A channel appears IFF this adapter observes the symbol on it,
        so an absent channel means *no relationship*, never *stale*."""
        channels: list[ChannelFreshness] = []
        state = self._symbols.get(symbol)
        if state is not None:
            channels.append(
                self._channel_freshness(
                    symbol,
                    FeedChannel.TICK,
                    state.last_tick_venue_ts,
                    state.last_tick_recv_ts,
                    now,
                )
            )
        polled = self._polled.get(symbol)
        if polled is not None:
            channels.append(
                self._channel_freshness(
                    symbol,
                    FeedChannel.POLL,
                    polled.last_bar_venue_ts,
                    polled.last_poll_recv_ts,
                    now,
                )
            )
        return FreshnessReport(symbol=symbol, now=now, channels=tuple(channels))

    def _channel_freshness(
        self,
        symbol: Symbol,
        channel: FeedChannel,
        venue_ts: float | None,
        recv_ts: float | None,
        now: float,
    ) -> ChannelFreshness:
        """One channel, computed by the EXISTING formula with the CHANNEL'S OWN lag.

        `FeedLag.excess_staleness_s` is unchanged and is still the vendor-blind primitive; all
        that changed is that it is now asked once per channel with that channel's figure
        instead of once per symbol with the tick channel's."""
        lag = self.feed_lag(symbol, channel=channel)
        excess = lag.excess_staleness_s(venue_ts, now)
        if excess is None:
            state = ChannelState.CANNOT_MEASURE
            detail = (
                f"venue_ts is absent on the {channel.value} channel"
                if venue_ts is None
                else f"no effective_lag_s for the {channel.value} channel: {lag.detail}"
            )
        else:
            state = (
                ChannelState.FRESH
                if excess <= self._stale_threshold_s
                else ChannelState.STALE
            )
            detail = ""
        return ChannelFreshness(
            channel=channel,
            venue_ts=venue_ts,
            lag=lag,
            excess_staleness_s=excess,
            threshold_s=self._stale_threshold_s,
            state=state,
            recv_ts=recv_ts,
            detail=detail,
        )

    @staticmethod
    def _channel_floor(report: FreshnessReport) -> FeedState:
        """§2A:92's single `FeedState`, derived from the report. **THE ONE COLLAPSE THE FROZEN
        EVENT FORCES, kept as narrow as it can be made.**

        `nics_risk_subsystem_spec_v1.3.md` §2A:92 declares
        `on_feed_status(up|down|stale, symbol?, reason?)` — one state, and that vocabulary is
        frozen, so the seam cannot emit a per-channel verdict on it. AMENDMENT 6 does not
        license refusing to emit; it licenses refusing to let the emission be the only thing
        available, and `freshness()` returns the report beside every emission.

        THE RULE: **UP where ANY channel is fresh; STALE otherwise.** The seam has no standing
        to prefer one channel over another, so it cannot answer *"is the channel you need
        fresh?"* — it can only answer *"is anything fresh?"*, and a consumer that needs more
        reads the report. Note the direction: the OLD code said STALE while a channel was
        fresh, and §6.4:373-374 makes STALE mean liquidate. Saying UP while a channel a
        particular consumer needs is stale is recoverable by that consumer reading the report;
        saying STALE over a healthy feed is not recoverable by anyone, which is F21.

        A REPORT WITH NO CHANNELS IS STALE, unchanged and deliberately: an adapter with no
        relationship to a symbol has observed nothing, `CLAUDE.md` directive 4 says fail
        closed, and `observed_channels` being empty is what tells a consumer the STALE is an
        absence of evidence rather than evidence of staleness."""
        return FeedState.UP if report.fresh_channels else FeedState.STALE

    def evaluate_freshness(self, now: float, symbol: Symbol | None = None) -> FeedState:
        """§2A:92's single-state summary, DERIVED FROM `freshness()`. **NOT the authority.**

        RETAINED rather than deleted because `nics_risk_subsystem_spec_v1.3.md` §2A:92 declares
        exactly one feed-health state and a consumer wired to that event needs a way to ask for
        it. It is the WORST `_channel_floor` over the symbols in scope, and it collapses — so
        under AMENDMENT 6 it is the summary and `freshness()` is the thing that answers the
        question. Anything that decides on freshness reads the report.

        `capabilities.pushes_feed_status` is False: IBKR reports no feed-health signal, so
        §2A:92's event has to be DERIVED, and saying so is the difference between a declared
        derivation and a fabricated venue signal.

        IT DOES NOT PUBLISH. `freshness()` does, once per symbol; a second emission site here
        would put two `on_feed_status` events on the wire for one question, which is what
        `_publish_feed_state`'s choke-point argument exists to prevent."""
        reports = self.freshness(now, symbol)
        if not reports:
            return self._feed_state
        return (
            FeedState.STALE
            if any(self._channel_floor(r) is FeedState.STALE for r in reports)
            else FeedState.UP
        )

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
            # BOUNDED WINDOW, not an unbounded list (ARC 023, F17). The sample carries its own
            # receipt clock because the window trims by TIME; see `_LagWindowStore`.
            state.lag_window.record(stamp, stamp - venue_ts)
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
                        self._poll_seq,
                        symbol,
                        started,
                        ok=False,
                        error=repr(exc),
                        venue_answered=False,
                    )
                )
                continue
            self._record_response(symbol, rows, started)
            return len(rows)
        raise FeedPollExhausted(
            f"poll_history({symbol}) exhausted {budget} attempt(s) without a response. "
            f"Attempts: {[a.error for a in self._poll_attempt_log[-budget:]]}"
        )

    def _record_response(self, symbol: Symbol, rows, started: float) -> None:
        """The venue answered. Write the poll clock, ingest, and record the attempt.

        THE ATTEMPT RECORD IS WRITTEN AFTER THE INGEST, IN A `finally`, and that ordering is
        F13's second defect. It used to be appended BEFORE `_ingest_history` ran, so a sink
        that raised half way through left `ok=True, rows=4` standing over a bar that was
        sealed, never published and never recoverable. Writing it afterwards is what lets it
        carry what actually happened; `finally` is what makes it get written even when the
        consumer's exception is on its way out, because an attempt that tore is the one a
        reader most needs to see.

        ONE `finally`, NO SECOND BROAD `except`. The module's pylint pragma block records that
        `broad-exception-caught` is permitted at exactly ONE site — the bounded poll loop's
        venue call — and a second one here would swallow the consumer's exception, which must
        propagate (`CLAUDE.md` directive 4, fail closed and LOUD)."""
        polled = self._polled.setdefault(symbol, _SymbolPollState())
        # WRITER of last_poll_recv_ts, and the ONLY one. It lives in `_polled` and not in
        # `_symbols` (F12): a poll must not manufacture a subscription.
        polled.last_poll_recv_ts = time.time()
        acc = _IngestTally()
        try:
            self._ingest_history(symbol, rows, polled.last_poll_recv_ts, acc)
        finally:
            # DERIVED FROM WHAT THE INGEST ACTUALLY TOUCHED, never re-read off `rows`: a row
            # the loop never reached was not sealed and is not owed, and re-deriving keys from
            # the row list inside a `finally` would raise on a malformed row and MASK the
            # consumer's exception on its way out.
            undelivered = len(acc.keys & self._unpublished)
            # MONOTONIC BY SOURCE (`nics_risk_subsystem_spec_v1.3.md` §6.4b, applied to the
            # poll channel's stamp): a later poll that answers with older history does not
            # make the channel younger. Written here rather than in the ingest loop so a torn
            # ingest still advances the stamp for the rows it did read — the venue reported
            # them, and the consumer's exception is not a fact about the venue's clock.
            if acc.newest_bar_venue_ts is not None:
                polled.last_bar_venue_ts = (
                    acc.newest_bar_venue_ts
                    if polled.last_bar_venue_ts is None
                    else max(polled.last_bar_venue_ts, acc.newest_bar_venue_ts)
                )
            self._poll_attempt_log.append(
                PollAttempt(
                    self._poll_seq,
                    symbol,
                    started,
                    ok=not undelivered,
                    venue_answered=True,
                    rows=len(rows),
                    sealed=acc.sealed,
                    published=acc.published,
                    revised=acc.revised,
                    undelivered=undelivered,
                )
            )

    @staticmethod
    def _seal_key(symbol: Symbol, row) -> tuple[Symbol, float, float]:
        """The identity a seal is held under, spelled ONCE so `_ingest_history` and the attempt
        record cannot disagree about which bar a row is."""
        return (symbol, row["bar_start_venue_ts"], row["period_s"])

    def _ingest_history(
        self, symbol: Symbol, rows, recv_ts: float, tally: _IngestTally | None = None
    ) -> None:
        """SEAL AND NEVER REWRITE (`docs/CHECK-DEBT.md` D1.14).

        A row whose seal key is unseen is sealed and published on `on_bar`, exactly once. A row
        whose seal key is already sealed is NEVER written over: if its payload differs, a
        `BarRevision` is published on `on_bar_revision` and retained; if it is identical, it is
        dropped, because an identical re-poll is not a revision and a stream of no-op
        revisions is how a real one becomes invisible.

        SEAL AND **PUBLICATION** ARE NOT SEPARABLE INTO A DEAD END (ARC 023, F13). D1.14's rule
        made the poll path idempotent, which is right, and it also made the PUBLICATION
        unrepeatable, which nobody wrote down: a bar whose `on_bar` raised was sealed, and every
        later poll then recognised it as an identical re-poll and dropped it. Lost from the
        consumer's stream forever, with no revision, no error and no observable naming it.

        THE REPAIR IS A PUBLICATION DEBT, NOT A RE-DERIVATION. `self._unpublished` holds the
        seal keys whose bar the sink has not accepted, and the next poll that reaches the key
        **re-publishes the SEALED OBJECT** — the same `Bar`, with its original `seal_seq`,
        `recv_ts` and payload. Nothing is rebuilt from the row, so D1.14 is intact and a bar
        cannot acquire a second identity. Rebuilding it would have been the tempting fix and it
        is worse than the defect: the retry's row may carry the venue's REVISED values, so a
        re-derived bar would seal a revision as if it were the original and the revision fact —
        the one thing observable only here (AMENDMENT 4) — would vanish. Under this repair the
        revision is still evaluated against the ORIGINAL seal, below, on the same poll.

        WHY THE ADAPTER OWNS THIS AND NOT THE CONSUMER: the re-poll happens HERE. A consumer
        holding only what crossed the seam sees a second bar with the same start time and no
        way to know whether the venue corrected itself or it double-subscribed. Both stories
        exist only at this layer, which is the argument for the rule living here.

        AND THIS IS THE ONLY `Bar(...)` IN THE MODULE — AMENDMENT 4's proof-by-absence half. The
        source is `POLLED_HISTORY` because the venue is the source; nothing here aggregates a
        tick, and `Bar.__post_init__` refuses one that did."""
        acc = _IngestTally() if tally is None else tally
        for row in rows:
            key = self._seal_key(symbol, row)
            acc.keys.add(key)
            acc.newest_bar_venue_ts = max(
                row["bar_start_venue_ts"],
                acc.newest_bar_venue_ts
                if acc.newest_bar_venue_ts is not None
                else row["bar_start_venue_ts"],
            )
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
                    # TRANSLATED AT THE VENDOR BOUNDARY (ARC 023, D1.39/D1.40), not passed
                    # through: IBKR's `-1` is its not-reported sentinel and `Bar.volume`'s
                    # `| None` is justified by exactly that absence. Letting the raw sentinel
                    # cross meant a consumer could read it as "one contract traded, short" —
                    # the substitution AMENDMENT 3 forbids, arriving through the field the
                    # amendment kept optional in order to prevent it. See
                    # `IB_VOLUME_NOT_REPORTED`: translating it is NOT measuring it and the
                    # VENDOR_DECLARED grade is unchanged.
                    volume=self._volume(row),
                    recv_ts=recv_ts,
                    source=BarSource.POLLED_HISTORY,
                    seal_seq=self._seal_seq,
                )
                # THE SEAL AND THE PUBLICATION DEBT ARE WRITTEN TOGETHER. The debt is recorded
                # BEFORE the sink is called, so an `on_bar` that raises leaves the key owed
                # rather than leaving nothing at all — the whole point of F13's repair.
                self._sealed[key] = bar
                self._unpublished.add(key)
                acc.sealed += 1
            else:
                bar = sealed
            # ONE EMISSION SITE FOR BOTH CASES — a bar just sealed and a bar sealed by an
            # earlier poll whose consumer refused it are the same obligation, and giving them
            # two publish sites is two chances for the ordering below to be got wrong in one.
            #
            # THE ORDER IS THE PROPERTY: the sink is called FIRST and the debt is discharged
            # only on the line after it returns. A `finally` around this would discharge the
            # debt on the exception path, which is the defect wearing a repair's clothes.
            #
            # `debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GUARD TO PASS WHILE
            # MEASURING NOTHING? Four conditions, all plantable:
            #   1. `self._unpublished` is never ADDED to, so `discard` has nothing to do and
            #      every attempt records `undelivered=0`. Plant: delete the `add` above.
            #      Caught by the F13 traversal, which asserts a bar sealed under a raising sink
            #      is owed and is re-published on the retry.
            #   2. The `discard` happens BEFORE `on_bar`, so a raising sink still clears the
            #      debt. Plant: swap the two lines. The same traversal catches it, because the
            #      retry then drops the bar as an identical re-poll exactly as before.
            #   3. `on_bar` is called on a sink nobody reads — §7.12's own eighth instance
            #      (ARC 016). The traversals construct the adapter through one path that
            #      returns the very sink it injected, and assert `ad._sink is sink`.
            #   4. The re-publish reads the ROW rather than the seal, so the recovered bar is a
            #      re-derivation wearing the seal's name. Plant: `bar = Bar(...)` here. Caught
            #      by the traversal's IDENTITY assertion (`recovered is owed[0]`), which is why
            #      it asserts identity and not equality.
            if key in self._unpublished:
                self._sink.on_bar(bar)
                self._unpublished.discard(key)
                acc.published += 1
            if sealed is not None and self._maybe_revise(sealed, row, recv_ts):
                acc.revised += 1

    @staticmethod
    def _volume(row) -> float | None:
        """THE VENDOR BOUNDARY for `Bar.volume` (`docs/CHECK-DEBT.md` D1.39/D1.40).

        `.get()` survives here, and only here, among the five payload fields: IBKR genuinely
        returns bars for which volume is not a fact (`whatToShow` = MIDPOINT / BID / ASK), so
        an absent key IS an observable absence and `Bar.volume` keeps its `| None` on that
        strength (AMENDMENT 3's ARC 022 refinement).

        THE TRANSLATION IS THE ARC 023 ADDITION: IBKR reports that same absence on the history
        path as the VALUE `-1`, not as a missing key. Until now nothing translated it, so the
        sentinel crossed the seam as a number — the field kept optional in order to prevent a
        fabricated volume was delivering one. `IB_VOLUME_NOT_REPORTED` carries the evidence
        grade: IBKR-DOCUMENTED, **never measured on this system**, KNOWN-RED against the tap in
        `~/nix/downloads/tap_session_runbook.md`. Translating a declaration does not promote
        it to a measurement."""
        volume = row.get("volume")
        return None if volume == IB_VOLUME_NOT_REPORTED else volume

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

    def _maybe_revise(self, sealed: Bar, row, recv_ts: float) -> bool:
        """Publish a revision iff the venue's new story DIFFERS from the sealed one. Returns
        whether one was published, so the attempt record can count it without re-deriving it.

        THE VOLUME COMPARISON GOES THROUGH THE SAME VENDOR BOUNDARY as the seal
        (`_volume`): a first poll reporting `-1` seals `volume=None`, and a second poll
        reporting `-1` must compare equal to it. Reading the raw row here while the seal held
        the translated value would make every re-poll of a volume-less bar look like a
        revision — the no-op-revision flood `BarRevision.__post_init__` exists to prevent,
        reintroduced by comparing two different representations of one fact."""
        revised = tuple(
            self._volume(row) if name == "volume" else row.get(name)
            for name in BAR_PAYLOAD_FIELDS
        )
        if revised == sealed.payload():
            return False
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
        return True

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

    def unpublished_seals(self) -> tuple[Bar, ...]:
        """Bars SEALED whose `on_bar` the sink has not accepted, oldest seal first. ARC 023,
        F13's observable half.

        The loss used to be undetectable from outside and detectable from inside only by
        comparing `len(sealed_bars())` against a count the adapter did not keep. It is now a
        value, so a consumer, a gate and a test can all read the same fact — and it is EMPTY on
        a healthy adapter, which is what makes a non-empty reading mean something."""
        return tuple(
            sorted(
                (self._sealed[key] for key in self._unpublished),
                key=lambda b: b.seal_seq,
            )
        )

    def polled_symbols(self) -> tuple[Symbol, ...]:
        """Symbols this adapter has POLLED. **Not subscriptions** — see `_SymbolPollState`.

        Readable so the F12 boundary is provable from outside the adapter rather than by
        reaching into `_symbols` and `_polled`: after a poll of an unsubscribed symbol this
        tuple grows and `granted_mode()` does not move."""
        return tuple(sorted(self._polled))

    def last_tick_recv_ts(self, symbol: Symbol) -> float | None:
        state = self._symbols.get(symbol)
        return state.last_tick_recv_ts if state else None

    def last_poll_recv_ts(self, symbol: Symbol) -> float | None:
        """Reads `_polled`, not `_symbols` (ARC 023, F12): a poll clock is not a fact about a
        subscription, and it is available for a symbol that was never subscribed."""
        polled = self._polled.get(symbol)
        return polled.last_poll_recv_ts if polled else None

    def last_bar_venue_ts(self, symbol: Symbol) -> float | None:
        """The POLL channel's freshness stamp — the newest polled bar's venue-sourced open.
        `None` == this symbol has never been polled, or every poll returned nothing."""
        polled = self._polled.get(symbol)
        return polled.last_bar_venue_ts if polled else None
