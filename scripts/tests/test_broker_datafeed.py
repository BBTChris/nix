"""
test_broker_datafeed.py — adversarial test of the IBKR broker-datafeed adapter
(ARC 021; §9-§11 added ARC 022).

TIER 1 AND TIER 2 ONLY. `debug.md`'s tiers are sequential and Tier 3 is END-OF-MODULE
certification (`debug.md` §5:388-397) — a module that did not exist this morning has no
end-of-module to certify, so no test here is labelled Tier 3 and none attempts one. Tier 3 for
this module is a later arc's.

WHAT THIS SUITE IS BUILT TO CATCH, in the order the arc's obligations fall:

  §1 ROSTER. The §2A broker-datafeed roster derived from the FROZEN SPEC FILE at run time and
     compared against the seam's declared tuples. Neither number is typed into this file.

  §2 FRESHNESS, PROVED WITH A MATRIX AND NOT WITH A PAIR. ONE vendor-blind consumer function,
     ONE threshold, driven across 2 vendors x 3 conditions. The third condition is the
     non-vacuity: a transport-only implementation passes cells (a) and (b) on both vendors and
     fails (c), so dropping (c) would leave a suite that a wrong implementation passes.

  §3 THE ABSENCE PRINCIPLE (`docs/SPEC-AMENDMENTS.md` AMENDMENT 3). Every place the adapter
     could substitute a plausible value for a missing one, asserted to declare instead.

  §4 BAR IMMUTABILITY (`docs/CHECK-DEBT.md` D1.14), with an explicit NON-VACUITY assertion that
     the two payloads genuinely differ — so the test cannot silently degrade into one where the
     second poll returns identical data and proves nothing.

  §5 MULTI-WRITER FIELDS (ARC 020 A8). Every field written by more than one handler has its
     meaning asserted PER WRITER. `avg_price` carried two meanings twice on the order path
     (`docs/CHECK-DEBT.md` D1.29 is the third instance of the shape); a fresh module is the
     cheap moment to prevent a fourth.

  §6 STAGE 0 ABSENCES, declared through capabilities and REFUSED rather than silent.

  §7 IDENTITY. clientId 0 and 1 refused at construction.

  §8 CONTROLS. `HollowBrokerDatafeed` is structurally conformant and behaviourally empty, and
     the assertions that matter MUST fail against it. `debug.md` §7.12's vacuity table lists as
     instance 7 *an order sink passed into the datafeed port* — which survived precisely
     because no feed event was ever driven through it. Every sink here is driven.

  §9 D1.38, THE PORT'S SYNC/ASYNC SPLIT (ARC 022). The property is not "the adapter has async
     methods" — that is shape, and `callable()` already passes shape. It is that ONE declared
     partition governs the Protocol, the adapter and the roster, and that a divergence in
     EITHER direction is named. Both directions have a permanent control, because a gate
     demonstrated able to fail in one direction has been demonstrated in one direction.

  §10 AMENDMENT 4, WHOSE BAR IT IS (ARC 022). A tick-aggregated bar must be UNCONSTRUCTIBLE,
     not merely discouraged, and the refusal is an ALLOWLIST so a member added without an
     argument is refused too. The proof-by-absence half is asserted by AST, not by driving
     ticks and observing no bar — the call-site version would pass an adapter that aggregated
     on a path the test did not drive (`debug.md` §7.6).

  §11 AMENDMENT 3's REFINEMENT (ARC 022). An optional field must name an OBSERVABLE ABSENCE.
     A malformed row and a venue absence must not read the same, and the CONTROL for that
     refusal is the row that omits only `volume` — which must still go through, or the refusal
     test would pass against an adapter that had simply stopped accepting bars.

THE FAKE IS AWKWARD ON PURPOSE. `FakeIBFeed` reproduces the behaviours ARC 013 measured, not a
convenient idealisation: a `reqMarketDataType` request that is GRANTED AS SOMETHING ELSE with no
error, and a subscription that receives no grant callback at all. A polite fake cannot express
the defect the sentinel exists to catch.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   invalid-name
#       FakeIBFeed mirrors ib_async's surface: reqMarketDataType, reqMktData,
#       cancelMktData, connect, disconnect. Renaming them to snake_case would
#       make the fake stop standing in for the thing it fakes.
#   protected-access
#       The tests read `ad._symbols[sym].granted_mode` and call `ad._on_ib_tick`
#       directly. That is deliberate: the grant sentinel and the per-symbol
#       clocks are internal STATE whose correctness IS the property under test,
#       and reading them is direct measurement rather than inference from an
#       output that might mask them (CLAUDE.md directive 2).
#   missing-function-docstring / missing-class-docstring
#       Fake methods are named after the vendor calls they stand in for.
#   unused-argument
#       Fake vendor methods accept the arguments the real ones take.
#   too-many-* / too-many-lines
#       An adversarial driver's size IS its coverage. It is split into named
#       sections; collapsing assertions to satisfy a count deletes tests.
#   too-few-public-methods
#       Two one-method stand-ins drive the poll loop's failure and success arms.
#   too-many-instance-attributes
#       FakeIBFeed's fields are one per vendor behaviour it must be able to
#       express. Trimming them would make the fake unable to represent a defect,
#       which is `debug.md` §7.12 instance 5 exactly.
#   use-implicit-booleaness-not-comparison
#       `== []` is deliberate on every conformance-checker result. `not x` is
#       also true for `None`, so a checker that started returning None instead
#       of a list would pass a `not` assertion while having measured nothing.
#       The comparison asserts the TYPE and the emptiness together.
#   duplicate-code
#       Section banner comments are intentionally identical.
#   disallowed-name
#       `bar` is the domain word for the thing the datafeed port publishes.
#       pylint's default blacklist is foo/bar/baz as METASYNTACTIC placeholders;
#       the same argument `broker_datafeed_ibkr.py` records.
# pylint: disable=invalid-name,protected-access,missing-function-docstring,disallowed-name
# pylint: disable=missing-class-docstring,unused-argument,too-many-locals
# pylint: disable=too-many-statements,too-many-lines,too-few-public-methods
# pylint: disable=too-many-instance-attributes,duplicate-code
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=use-implicit-booleaness-not-comparison
import ast
import enum
import importlib
import inspect
import pathlib
import re
from typing import Protocol

import pytest  # pylint: disable=import-error
from broker_datafeed_ibkr import (
    DATAFEED_CLIENT_ID,
    IB_MARKETDATA_EVIDENCE,
    IB_POLL_LAG_RECORD,
    IB_STAGE0_DELAYED_LAG,
    IB_VOLUME_NOT_REPORTED,
    IBKRBrokerDatafeed,
    PollAttempt,
    Stage0LagRecord,
)

# `ORDER_ASYNC_VERBS` and `BrokerOrderPort` are imported here and that is NOT an invariant 3
# violation. §2A:105-106 forbids a shared OBJECT between the two libraries; `broker_seam.py` is
# the shared CONTRACT both ports are declared in, and §9 below exists precisely to assert that
# the two ports' partitions DIFFER — a property that cannot be stated without naming both. The
# disjointness that is enforced is on the adapter modules' import graphs, and
# `test_no_shared_object_with_the_order_library` is where that is measured.
from broker_seam import (
    BAR_PAYLOAD_FIELDS,
    BAR_REQUIRED_PAYLOAD_FIELDS,
    DATAFEED_ASYNC_VERBS,
    DATAFEED_EVENTS,
    DATAFEED_PORT_VERBS,
    LAG_SAMPLE_FLOOR,
    LAG_WINDOW_MAX_SAMPLES,
    LAG_WINDOW_S,
    ORDER_ASYNC_VERBS,
    PORT_ASYNC_VERBS,
    VENUE_SOURCED_BAR_SOURCES,
    AwaitDivergentBrokerDatafeed,
    Bar,
    BarRevision,
    BarSource,
    BrokerDatafeedPort,
    BrokerNotConnected,
    BrokerOrderPort,
    BrokerUnsupported,
    ChannelState,
    CoroutineDivergentBrokerDatafeed,
    FeedChannel,
    FeedLag,
    FeedPollExhausted,
    FeedState,
    HollowBrokerDatafeed,
    LagAgreement,
    LagProvenance,
    LagWindow,
    LagWindowBound,
    MalformedBarRow,
    MarketDataMode,
    RecordingFeedSink,
    StubBrokerDatafeed,
    check_await_conformance,
    check_structural_conformance,
)

NIX_HOME = pathlib.Path(__file__).resolve().parents[2]
SPEC = NIX_HOME / "docs" / "nics_risk_subsystem_spec_v1.3.md"
BROKER_DIR = NIX_HOME / "scripts" / "broker"

SYM = "MESU6"


def _datafeed_adapter_classes() -> set[type]:
    """Every class under `scripts/broker/` implementing the WHOLE datafeed roster.

    DERIVED FROM THE TREE, never listed (`debug.md` §7.4, first row: a hardcoded list of files
    silently stops covering the one added after it). The AST finds the candidates and the import
    resolves them, so a new adapter joins every assertion in §9 by being written — including one
    added to a module that does not exist today."""
    found: set[type] = set()
    roster = set(DATAFEED_PORT_VERBS)
    for path in sorted(BROKER_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            defined = {
                b.name
                for b in node.body
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            # Subclasses inherit the rest, so the AST test is on the RESOLVED class, not on the
            # class body — the two divergent controls define exactly one verb each.
            module = module or importlib.import_module(path.stem)
            cls = getattr(module, node.name, None)
            if cls is None or not defined & roster:
                continue
            if all(callable(getattr(cls, verb, None)) for verb in roster):
                found.add(cls)
    return found


# ===========================================================================
# THE FAKE — awkward on purpose
# ===========================================================================


class FakeIBFeed:
    """Stands in for ib_async.IB on the market-data surface, with ARC 013's real behaviours.

    `grant_map` is what makes it useful: it maps a REQUESTED marketDataType to the mode the
    venue will actually grant, and `None` means *no grant callback at all*. Both are measured
    behaviours (`sessions/SESSION.md` ARC 013 table): mode 4 was granted as 3, and mode 1
    received no callback and zero ticks. A fake that always grants what was asked cannot
    express either, which is exactly the shape `debug.md` §7.12 instance 5 records — the
    instrument could not represent the difference it was asked to detect.
    """

    def __init__(self, grant_map=None):
        self.connected = False
        self.client_id = None
        self.requested: list[int] = []
        self.subscribed: list[str] = []
        self.cancelled: list[str] = []
        self.grant_map = {} if grant_map is None else grant_map
        self._adapter = None
        self._pending = None

    def bind(self, adapter) -> None:
        """Lets the fake deliver the grant callback the way IBKR does — asynchronously with
        respect to the request, and only when it feels like it."""
        self._adapter = adapter

    def connect(self, host, port, clientId=None):
        self.connected = True
        self.client_id = clientId

    def disconnect(self):
        self.connected = False

    def reqMarketDataType(self, mode_value):
        self.requested.append(mode_value)
        self._pending = mode_value

    def reqMktData(self, symbol):
        self.subscribed.append(symbol)
        granted = self.grant_map.get(self._pending, self._pending)
        if granted is not None and self._adapter is not None:
            self._adapter._on_ib_market_data_type(symbol, granted)

    def cancelMktData(self, symbol):
        self.cancelled.append(symbol)


async def make_adapter(*, grant_map=None, history=None, **kwargs):
    """A connected adapter over a bound fake. Returns (adapter, sink, fake)."""
    sink = RecordingFeedSink()
    fake = FakeIBFeed(grant_map=grant_map)
    ad = IBKRBrokerDatafeed(sink, ib=fake, history_source=history, **kwargs)
    fake.bind(ad)
    await ad.connect()
    return ad, sink, fake


def bar_row(start, *, period_s=60.0, o=1.0, h=2.0, low=0.5, c=1.5, v=10.0):
    return {
        "bar_start_venue_ts": start,
        "period_s": period_s,
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": v,
    }


# ===========================================================================
# §1 — THE ROSTER, DERIVED FROM THE FROZEN SPEC FILE
# ===========================================================================


def _spec_datafeed_block() -> str:
    """The `### broker-datafeed` block of the frozen spec, read at run time.

    Derived, never transcribed (`CLAUDE.md` directive 3). If the spec is ever re-versioned the
    numbers below move with it instead of going stale silently, which is `debug.md` §7.4."""
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("### broker-datafeed")
    end = text.index("\n**Strategy isolation", start)
    return text[start:end]


def _spec_bullets(block: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.startswith("- ")]


def _spec_identifiers(block: str) -> list[str]:
    """Identifiers, not bullets. Only the LEADING backtick span of a bullet is read, so a prose
    mention later in the same bullet cannot be counted as a second declaration — the same rule
    `checks/check_derived_claims.py` applies, reached the same way and deliberately not
    imported (that module lives in `checks/`, which this arc may not write)."""
    names: list[str] = []
    for line in _spec_bullets(block):
        span = re.match(r"-\s+`([^`]+)`", line)
        if span:
            names.extend(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", span.group(1)))
    return names


def _flags_itself_a_nix_addition(source: str, name: str) -> bool:
    """True when `name`'s own def in the seam carries 'nix addition' in its docstring.

    The same rule `checks/check_derived_claims._flagged_addition` applies, reached the same way
    and deliberately NOT imported: that module lives in `checks/`, which this arc may not write,
    and importing a gate into the suite that is supposed to corroborate it independently would
    make the two agree by construction."""
    tree = ast.parse(source)
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
        and "nix addition" in (ast.get_docstring(node) or "").lower()
        for node in ast.walk(tree)
    )


def test_roster_bullets_and_identifiers_disagree_and_both_are_derived():
    """§2A's BULLET count and its IDENTIFIER count are different numbers, on purpose.

    A single bullet — `connect() / disconnect()` — declares TWO identifiers, so counting
    bullets under-reports the contract by exactly the number of slash-joined pairs. Both are
    asserted so a future reader cannot pick whichever supports the claim they are making."""
    block = _spec_datafeed_block()
    bullets = _spec_bullets(block)
    identifiers = _spec_identifiers(block)
    assert len(bullets) == 4, bullets
    assert len(identifiers) == 6, identifiers
    assert identifiers == [
        "connect",
        "disconnect",
        "subscribe",
        "unsubscribe",
        "on_tick",
        "on_feed_status",
    ]
    # The disagreement itself is the property. If a future spec edit made them equal, that is a
    # fact worth failing over rather than passing silently.
    assert len(bullets) != len(identifiers)


def test_seam_roster_is_spec_plus_flagged_additions():
    """Every seam-declared datafeed element is in §2A or is a FLAGGED Nix addition.

    The count is DERIVED from both sides. `check_derived_claims.py` enforces the same balance
    tree-wide; this asserts it for the datafeed half specifically, so a seam edit that adds an
    unflagged element reddens here too and not only in a check the suite does not run."""
    spec = set(_spec_identifiers(_spec_datafeed_block()))
    seam = set(DATAFEED_PORT_VERBS) | set(DATAFEED_EVENTS)
    additions = seam - spec
    assert spec <= seam, f"seam does not declare §2A element(s): {sorted(spec - seam)}"

    # EVERY addition FLAGS ITSELF as one, read out of the seam source. This replaced a literal
    # `== {"feed_lag", "on_bar", "on_bar_revision"}` in ARC 022, when D1.38 added two more and
    # the literal went stale in the same edit — `debug.md` §7.4's first row exactly, and the
    # reason the property to assert is the FLAG rather than the membership. An unflagged
    # addition is what `checks/check_derived_claims.py` counts on the code side and not on the
    # spec side, so this is the same balance asserted where a suite can see it.
    seam_src = (NIX_HOME / "scripts" / "broker" / "broker_seam.py").read_text(
        encoding="utf-8"
    )
    unflagged = [
        name
        for name in sorted(additions)
        if not _flags_itself_a_nix_addition(seam_src, name)
    ]
    assert unflagged == [], (
        f"seam element(s) {unflagged} are outside §2A and do not declare themselves Nix "
        "additions — the spec side cannot count them and the balance reddens"
    )
    assert len(seam) == len(spec) + len(additions)
    # NON-VACUITY: §2A must actually contribute, or "spec plus additions" is "additions".
    assert len(spec) == 6 and len(additions) >= 3


@pytest.mark.asyncio
async def test_adapter_conforms_structurally_and_in_await_ness():
    ad, _, _ = await make_adapter()
    assert check_structural_conformance(ad, DATAFEED_PORT_VERBS) == []
    # callable() is true for `async def` too, so the structural check alone cannot tell a sync
    # verb from a coroutine function. Both are required — ARC 014's finding.
    assert check_await_conformance(ad, BrokerDatafeedPort, DATAFEED_PORT_VERBS) == []
    assert isinstance(ad, BrokerDatafeedPort)


def test_recording_sink_implements_every_declared_event():
    """The sink a test drives must implement the whole event set, or a driven event silently
    goes nowhere. `debug.md` §7.12 instance 7 is exactly this defect one type over."""
    sink = RecordingFeedSink()
    assert check_structural_conformance(sink, DATAFEED_EVENTS) == []


@pytest.mark.asyncio
async def test_no_shared_object_with_the_order_library():
    """§2A:105-106 invariant 3, asserted rather than asserted-in-prose.

    `nics_risk_subsystem_spec_v1.3.md` §2A:105-106: *order and datafeed contracts are disjoint
    — no shared object*. The datafeed module must not reach into the order library at all, and
    the check is on the IMPORT GRAPH because that is where a shared base class or a shared
    error table would show up."""
    source = (NIX_HOME / "scripts" / "broker" / "broker_datafeed_ibkr.py").read_text(
        encoding="utf-8"
    )
    import_lines = [
        ln
        for ln in source.splitlines()
        if ln.startswith(("import ", "from ")) and "#" not in ln.split()[0]
    ]
    offenders = [
        ln for ln in import_lines if "broker_order" in ln or "ibkr_mapping" in ln
    ]
    assert offenders == [], offenders
    ad, _, _ = await make_adapter()
    # And no order verb reachable on the datafeed adapter.
    for verb in (
        "place_order",
        "cancel_order",
        "flatten",
        "get_margin",
        "query_positions",
        "query_balance",
        "query_order_status",
    ):
        assert not hasattr(ad, verb), verb


# ===========================================================================
# §2 — FRESHNESS: ONE CONSUMER, ONE THRESHOLD, SIX CELLS
# ===========================================================================

STALE_BUDGET_S = 30.0
"""The consumer's threshold. ONE value across all six cells — if a cell needed its own, the
interface would not be vendor-blind and the matrix would be proving nothing."""


def consumer_verdict(lag: FeedLag, venue_ts, recv_ts, now) -> str:
    """THE VENDOR-BLIND CONSUMER. One function, no vendor knowledge, used by all six cells.

    This is what capture.py or the Limiter would write. It knows nothing about IBKR, about 600
    seconds, or about which mode was granted — it asks the feed how far behind it is and
    computes excess staleness against its own §12A-derived budget.

    THE TWO WRONG CONSUMERS, written out so the difference is visible rather than asserted:
      `now - venue_ts > BUDGET`  is right on a 0-lag vendor, and calls the healthy Stage 0
        IBKR feed STALE on every single tick — a spurious halt+flatten
        (`nics_risk_subsystem_spec_v1.3.md` §6.4:373-374).
      `now - recv_ts > BUDGET`   is right on both healthy feeds, and calls a WEDGED feed FRESH
        — packets keep arriving, so the receipt clock stays young while the data is dead.
    Neither is used here. `excess_staleness_s` is right in all six cells with one threshold."""
    excess = lag.excess_staleness_s(venue_ts, now)
    if excess is None:
        # CANNOT COMPUTE is not FRESH. Fail closed and loud (`CLAUDE.md` directive 4).
        return "STALE"
    transport = FeedLag.transport_age_s(recv_ts, now)
    if transport is None or transport > STALE_BUDGET_S:
        return "STALE"
    return "STALE" if excess > STALE_BUDGET_S else "FRESH"


def lag_for(declared: float) -> FeedLag:
    """A vendor's lag declaration. The ONLY thing that differs between the two vendor columns."""
    return FeedLag(
        declared_lag_s=declared,
        observed_lag_s=None,
        observed_n=0,
        provenance=LagProvenance.VENDOR_DECLARED,
        granted_mode=MarketDataMode.DELAYED,
    )


TRADOVATE_LAG = 0.0
IBKR_STAGE0_LAG = IB_STAGE0_DELAYED_LAG.mean_s  # derived, never typed


# (vendor label, declared lag, condition label, venue_ts, recv_ts, now, expected)
#
# `now` is fixed at 10_000.0 in every cell so the arithmetic is readable. The three conditions:
#   (a) healthy          — a packet just arrived carrying a venue_ts that is exactly `lag` old
#   (b) transport dead   — the last packet arrived 300 s ago and nothing since
#   (c) data-clock stalled — packets STILL ARRIVING (recv_ts is 1 s old) but venue_ts frozen
#                            300 s in the past. THIS IS THE NON-VACUITY CELL.
NOW = 10_000.0
FRESHNESS_MATRIX = [
    ("tradovate", TRADOVATE_LAG, "healthy", NOW - TRADOVATE_LAG, NOW - 1.0, "FRESH"),
    ("tradovate", TRADOVATE_LAG, "transport-dead", NOW - 300.0, NOW - 300.0, "STALE"),
    ("tradovate", TRADOVATE_LAG, "data-stalled", NOW - 300.0, NOW - 1.0, "STALE"),
    (
        "ibkr-stage0",
        IBKR_STAGE0_LAG,
        "healthy",
        NOW - IBKR_STAGE0_LAG,
        NOW - 1.0,
        "FRESH",
    ),
    (
        "ibkr-stage0",
        IBKR_STAGE0_LAG,
        "transport-dead",
        NOW - IBKR_STAGE0_LAG - 300.0,
        NOW - 300.0,
        "STALE",
    ),
    (
        "ibkr-stage0",
        IBKR_STAGE0_LAG,
        "data-stalled",
        NOW - IBKR_STAGE0_LAG - 300.0,
        NOW - 1.0,
        "STALE",
    ),
]


def test_freshness_matrix_two_vendors_three_conditions():
    """2 vendors x 3 conditions, ONE consumer function, ONE threshold. All six must agree.

    COMPARED CELL BY CELL, NOT IN AGGREGATE (`debug.md` §7.7). The two dicts below are keyed by
    (vendor, condition), so a failure names the exact cell and shows the whole table rather than
    reporting "5 of 6". A count would let one cell flip and be absorbed.

    DELIBERATELY NOT `@pytest.mark.parametrize` OVER A NAME. `checks/check_derived_claims.py`'s
    `pytest_collected_tests` claim counts tests by AST and refuses to count a parametrize whose
    argvalues is not a literal sequence — correctly, because it cannot know how many cases a
    name expands to. Parametrising over `FRESHNESS_MATRIX` turned that claim from a comparison
    into a CANNOT_MEASURE, i.e. this suite would have silently disarmed a tree-wide gate to buy
    itself prettier output. Measured, not guessed: the claim went `pytest_collected_tests=242`
    to `NOT MEASURED` on the parametrised version and back to a live comparison on this one."""
    expected = {(row[0], row[2]): row[5] for row in FRESHNESS_MATRIX}
    actual = {
        (vendor, condition): consumer_verdict(lag_for(declared), venue_ts, recv_ts, NOW)
        for vendor, declared, condition, venue_ts, recv_ts, _ in FRESHNESS_MATRIX
    }
    assert actual == expected
    assert len(actual) == 6


def test_matrix_covers_six_distinct_cells():
    """Non-vacuity of the matrix itself: six cells, two vendors, three conditions, and both
    verdicts represented. A parametrised suite that silently lost half its rows would still
    pass every row it kept."""
    assert len(FRESHNESS_MATRIX) == 6
    assert len({row[0] for row in FRESHNESS_MATRIX}) == 2
    assert len({row[2] for row in FRESHNESS_MATRIX}) == 3
    assert {row[5] for row in FRESHNESS_MATRIX} == {"FRESH", "STALE"}


def test_the_two_wrong_consumers_are_actually_wrong():
    """THE NON-VACUITY OF THE WHOLE §2. If the naive computations happened to be right, the
    primitive would be buying nothing and the matrix would prove nothing.

    So both wrong consumers are RUN, and each is shown to fail on the cell it fails on. This is
    `debug.md` §7.3 — prove non-vacuity before you prove anything else — applied to a design
    argument rather than to a gate."""
    ibkr = lag_for(IBKR_STAGE0_LAG)

    # (i) `now - venue_ts` on a HEALTHY IBKR tick: 600.3 s > 30 s budget -> calls it stale.
    healthy_venue_ts = NOW - IBKR_STAGE0_LAG
    assert (NOW - healthy_venue_ts) > STALE_BUDGET_S
    assert consumer_verdict(ibkr, healthy_venue_ts, NOW - 1.0, NOW) == "FRESH"

    # (ii) `now - recv_ts` on a WEDGED feed: 1 s -> calls dead data fresh.
    wedged_venue_ts = NOW - IBKR_STAGE0_LAG - 300.0
    assert (NOW - (NOW - 1.0)) < STALE_BUDGET_S
    assert consumer_verdict(ibkr, wedged_venue_ts, NOW - 1.0, NOW) == "STALE"


def test_excess_staleness_reduces_to_data_age_on_a_zero_lag_vendor():
    """On a 0-lag vendor the primitive IS raw data-age — that is what makes it vendor-blind."""
    zero = lag_for(0.0)
    assert zero.excess_staleness_s(NOW - 7.0, NOW) == pytest.approx(7.0)
    ibkr = lag_for(IBKR_STAGE0_LAG)
    assert ibkr.excess_staleness_s(NOW - IBKR_STAGE0_LAG - 7.0, NOW) == pytest.approx(
        7.0
    )


@pytest.mark.asyncio
async def test_adapter_freshness_uses_the_same_primitive():
    """The adapter's own derived `on_feed_status` agrees with the vendor-blind consumer.

    `capabilities.pushes_feed_status` is False, so §2A:92's event is DERIVED here. If the
    adapter's derivation and the consumer's computation could disagree, one of them would be
    the real definition and the other decoration."""
    ad, sink, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    now = 10_000.0
    healthy_venue_ts = now - IB_STAGE0_DELAYED_LAG.mean_s
    ad._on_ib_tick(SYM, 7782.5, 1.0, healthy_venue_ts, recv_ts=now - 1.0)
    assert ad.evaluate_freshness(now) is FeedState.UP
    assert sink.feed_statuses[-1][0] is FeedState.UP

    # Same subscription, data clock frozen 300 s: packets are still arriving.
    ad._on_ib_tick(SYM, 7782.5, 1.0, healthy_venue_ts - 300.0, recv_ts=now - 0.5)
    assert ad.evaluate_freshness(now) is FeedState.STALE
    assert sink.feed_statuses[-1][0] is FeedState.STALE


@pytest.mark.asyncio
async def test_freshness_on_a_symbol_that_never_ticked_is_stale_not_fresh():
    """CANNOT COMPUTE fails toward STALE. A symbol with no venue timestamp has no freshness,
    and an unanswerable question is not an answer of 'fresh' (`CLAUDE.md` directive 4)."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    assert ad.evaluate_freshness(10_000.0) is FeedState.STALE


# ===========================================================================
# §3 — THE ABSENCE PRINCIPLE (SPEC-AMENDMENTS.md AMENDMENT 3)
# ===========================================================================


def test_unobserved_lag_is_a_distinct_state_not_a_fabricated_zero():
    """The whole point of restructuring `FeedLag`. A vendorless stub declares NOTHING."""
    stub_lag = StubBrokerDatafeed(RecordingFeedSink()).feed_lag()
    assert stub_lag.declared_lag_s is None
    assert stub_lag.observed_lag_s is None
    assert stub_lag.provenance is LagProvenance.UNOBSERVED
    assert stub_lag.granted_mode is MarketDataMode.UNKNOWN
    assert stub_lag.agreement is LagAgreement.NOT_DECLARED
    # And the consequence a consumer actually feels: no confident number falls out of it.
    assert stub_lag.excess_staleness_s(NOW - 5.0, NOW) is None


@pytest.mark.asyncio
async def test_a_prior_arc_figure_declares_itself_as_one():
    """The Stage 0 figure is a REPLAY of ARC 013's measurement, and says so.

    No tap session ran in ARC 021 (`~/nix/downloads/TAP_SESSION.md` does not exist), so the
    figure must not read as a fresh observation. `agreement is NOT_OBSERVED` is the machine-
    readable half of that; `detail` carries the citation and the re-measurement obligation."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    lag = ad.feed_lag()
    assert lag.provenance is LagProvenance.PRIOR_ARC
    assert lag.observed_lag_s is None and lag.observed_n == 0
    assert lag.agreement is LagAgreement.NOT_OBSERVED
    assert lag.declared_lag_s == IB_STAGE0_DELAYED_LAG.mean_s
    assert "RE-MEASUREMENT IS OWED" in lag.detail
    assert "ARC 013" in lag.detail
    # The banked record is a RANGE and the scalar says which summary of it it is.
    assert f"{IB_STAGE0_DELAYED_LAG.low_s}-{IB_STAGE0_DELAYED_LAG.high_s}" in lag.detail


@pytest.mark.asyncio
async def test_observation_promotes_provenance_and_a_divergence_is_readable():
    """Where the lag CAN be observed, the declared figure is CHECKED — and a divergence is a
    value on the object, not a log line.

    THE PACKET COUNT IS DERIVED FROM THE FLOOR, NOT TYPED (ARC 023, F17, `debug.md` §7.4). The
    window declares `LAG_SAMPLE_FLOOR` and below it this object declares ABSENCE rather than a
    mean; a literal 4 here would have gone stale silently the day the floor moved, which is
    exactly what it did."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    now = 10_000.0
    n = LAG_SAMPLE_FLOOR
    for i in range(n):
        ad._on_ib_tick(SYM, 1.0, 1.0, now - 600.0 - i, recv_ts=now - i)
    lag = ad.feed_lag(SYM)
    assert lag.provenance is LagProvenance.OBSERVED
    assert lag.observed_n == n
    assert lag.observed_lag_s == pytest.approx(600.0)
    assert lag.agreement is LagAgreement.AGREES
    assert lag.divergence_s == pytest.approx(600.0 - IB_STAGE0_DELAYED_LAG.mean_s)
    assert lag.channel is FeedChannel.TICK

    # Now a feed that has fallen far behind its declaration.
    ad2, _, _ = await make_adapter(grant_map={3: 3})
    await ad2.subscribe(SYM)
    for i in range(n):
        ad2._on_ib_tick(SYM, 1.0, 1.0, now - 900.0 - i, recv_ts=now - i)
    diverged = ad2.feed_lag(SYM)
    assert diverged.agreement is LagAgreement.DIVERGED
    assert diverged.divergence_s == pytest.approx(900.0 - IB_STAGE0_DELAYED_LAG.mean_s)
    # OBSERVATION OUTRANKS DECLARATION: the consumer computes against what was measured.
    assert diverged.effective_lag_s == pytest.approx(900.0)


# ===========================================================================
# §3b — ARC 023: THE BOUNDED LAG WINDOW (F17)
# ===========================================================================


@pytest.mark.asyncio
async def test_below_the_floor_the_lag_declares_absence_and_says_how_many_it_held():
    """F17's floor half. Fewer than `LAG_SAMPLE_FLOOR` samples is not a small measurement; it
    is no measurement — and it is DISTINGUISHABLE from having none at all.

    `observed_n=0` with `window.n_in_window=0` says *none*; `observed_n=0` with
    `n_in_window=4` says *too few*. One field cannot say both, which is why the window is
    carried beside the figure (`docs/SPEC-AMENDMENTS.md` AMENDMENT 3)."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    lag = ad.feed_lag(SYM)
    assert lag.window is not None and lag.window.n_in_window == 0
    assert lag.observed_lag_s is None and lag.observed_n == 0

    for i in range(LAG_SAMPLE_FLOOR - 1):
        ad._on_ib_tick(SYM, 1.0, 1.0, NOW - 600.0 + i, recv_ts=NOW + i)
    lag = ad.feed_lag(SYM)
    assert lag.window is not None
    assert lag.window.n_in_window == LAG_SAMPLE_FLOOR - 1
    assert lag.observed_lag_s is None and lag.observed_n == 0
    assert lag.provenance is not LagProvenance.OBSERVED
    assert "below the floor" in lag.detail

    # NO FALL-BACK TO THE SESSION FIGURE, which is the substitution F17 is about. The session
    # mean EXISTS and is a different, separately-named field that nothing decides on.
    assert lag.session_mean_lag_s == pytest.approx(600.0)
    assert (
        lag.effective_lag_s == IB_STAGE0_DELAYED_LAG.mean_s
    )  # the DECLARED one, not it

    ad._on_ib_tick(SYM, 1.0, 1.0, NOW - 600.0, recv_ts=NOW + LAG_SAMPLE_FLOOR)
    assert ad.feed_lag(SYM).observed_n == LAG_SAMPLE_FLOOR


def test_a_lag_reporting_a_mean_over_fewer_than_its_floor_is_unconstructible():
    """THE FLOOR IS STRUCTURAL, so a second adapter cannot reintroduce F17 by forgetting it —
    the construction `Bar.__post_init__` uses for AMENDMENT 4."""
    window = LagWindow(
        window_s=LAG_WINDOW_S,
        sample_floor=LAG_SAMPLE_FLOOR,
        max_samples=LAG_WINDOW_MAX_SAMPLES,
        n_in_window=LAG_SAMPLE_FLOOR - 1,
        span_s=1.0,
        bound=LagWindowBound.WITHIN_BOTH,
    )
    with pytest.raises(ValueError, match="below the floor"):
        FeedLag(
            declared_lag_s=600.3,
            observed_lag_s=600.0,
            observed_n=LAG_SAMPLE_FLOOR - 1,
            provenance=LagProvenance.OBSERVED,
            granted_mode=MarketDataMode.DELAYED,
            window=window,
        )


@pytest.mark.asyncio
async def test_the_window_is_bounded_by_time_and_the_bound_that_applied_is_readable():
    """F17's window half, and BOTH bounds, because a time window alone is not memory-bounded.

    MEASURED ARC 023: at this box's ingest ceiling (3,561,839 samples/s) a pure 60 s window
    would retain 213,710,318 samples = 20.5 GB, so a count backstop is required — and WHICH
    bound applied has to be readable, because under `COUNT` the retained set spans less than
    `window_s` and the mean answers a narrower question than was asked."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    # Two full window-widths of samples, one per second, at the ARC 013 lag.
    span = int(LAG_WINDOW_S * 2)
    for i in range(span):
        ad._on_ib_tick(SYM, 1.0, 1.0, float(i), recv_ts=float(i) + 600.0)
    win = ad.feed_lag(SYM).window
    assert win is not None
    assert win.bound is LagWindowBound.TIME
    # THE RELATION, not a literal: nothing older than the window survives, and the retained
    # span cannot exceed the width that was asked for.
    assert win.n_in_window < span
    assert win.span_s is not None and win.span_s <= LAG_WINDOW_S

    # THE COUNT BACKSTOP, driven by configuring it small rather than by ingesting 20 GB.
    tight, _, _ = await make_adapter(grant_map={3: 3}, lag_max_samples=LAG_SAMPLE_FLOOR)
    await tight.subscribe(SYM)
    for i in range(LAG_SAMPLE_FLOOR * 4):
        tight._on_ib_tick(SYM, 1.0, 1.0, float(i), recv_ts=float(i) * 0.001 + 600.0)
    tight_win = tight.feed_lag(SYM).window
    assert tight_win is not None
    assert tight_win.bound is LagWindowBound.COUNT
    assert tight_win.n_in_window == LAG_SAMPLE_FLOOR
    # And the span it now covers is SHORTER than the window it was asked for — the fact the
    # `COUNT` member exists to make readable.
    assert tight_win.span_s is not None and tight_win.span_s < LAG_WINDOW_S


@pytest.mark.asyncio
async def test_a_recent_degradation_is_visible_where_the_session_mean_hides_it():
    """F17's LOAD-BEARING half: the observable was wrong in the direction that matters.

    It said the feed AGREED while the feed had fallen 300 s further behind. The relation
    asserted here is the repair — the windowed figure follows the recent packets and the
    session figure, which nothing decides on, still shows the dilution."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    healthy = 400
    for i in range(healthy):  # one packet per second, healthy, well past the window
        ad._on_ib_tick(SYM, 1.0, 1.0, float(i), recv_ts=float(i) + 600.0)
    assert ad.feed_lag(SYM).agreement is LagAgreement.AGREES

    # The feed degrades by 300 s. One window's worth of degraded packets, same rate.
    degraded = int(LAG_WINDOW_S)
    for i in range(healthy, healthy + degraded):
        ad._on_ib_tick(SYM, 1.0, 1.0, float(i), recv_ts=float(i) + 900.0)
    lag = ad.feed_lag(SYM)
    assert lag.agreement is LagAgreement.DIVERGED
    assert lag.observed_lag_s == pytest.approx(900.0)
    # THE SESSION FIGURE STILL DILUTES — kept, informational, and read by no decision.
    assert lag.session_mean_lag_s is not None
    assert lag.session_mean_lag_s < lag.observed_lag_s
    assert lag.effective_lag_s == pytest.approx(lag.observed_lag_s)


def test_feedlag_refuses_to_be_constructed_incoherently():
    """A value with no samples, or samples with no value, is not a state this object may hold."""
    with pytest.raises(ValueError, match="disagree"):
        FeedLag(
            declared_lag_s=1.0,
            observed_lag_s=5.0,
            observed_n=0,
            provenance=LagProvenance.OBSERVED,
            granted_mode=MarketDataMode.DELAYED,
        )
    with pytest.raises(ValueError, match="does not declare itself observed"):
        FeedLag(
            declared_lag_s=1.0,
            observed_lag_s=5.0,
            observed_n=3,
            provenance=LagProvenance.PRIOR_ARC,
            granted_mode=MarketDataMode.DELAYED,
        )
    with pytest.raises(ValueError, match="provenance for a figure that does not exist"):
        FeedLag(
            declared_lag_s=None,
            observed_lag_s=None,
            observed_n=0,
            provenance=LagProvenance.VENDOR_DECLARED,
            granted_mode=MarketDataMode.UNKNOWN,
        )


@pytest.mark.asyncio
async def test_absent_tick_fields_are_declared_not_defaulted():
    """A packet with no size and no venue timestamp emits None for both, and the LOCAL receipt
    clock is NOT substituted into the venue field (§2A:106-107 invariant 4)."""
    ad, sink, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    ad._on_ib_tick(SYM, None, None, None, recv_ts=123.0)
    symbol, price, size, venue_ts, recv_ts = sink.ticks[-1]
    assert (symbol, price, size, venue_ts) == (SYM, None, None, None)
    assert recv_ts == 123.0
    # An absent venue timestamp contributes NO lag sample — a fabricated 0 sample here would
    # be a measurement of nothing entering a mean.
    assert ad.feed_lag(SYM).observed_lag_s is None


@pytest.mark.asyncio
async def test_absent_bar_fields_are_declared_not_defaulted():
    """A bar the venue reported no volume for reports no volume. 0.0 is a real volume."""
    row = bar_row(1000.0)
    del row["volume"]
    ad, sink, _ = await make_adapter(grant_map={3: 3}, history=lambda s: [row])
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    assert sink.bars[-1].volume is None


@pytest.mark.asyncio
async def test_no_grant_callback_reports_unknown_never_the_requested_mode():
    """ARC 013's measured trap, encoded. `ib_async`'s `Ticker.marketDataType` DEFAULTS to 1, so
    an unset field is indistinguishable from a real-time grant unless it is sentinelled."""
    ad, _, _ = await make_adapter(grant_map={3: None})  # request 3, venue says nothing
    await ad.subscribe(SYM)
    assert ad.granted_mode(SYM) is MarketDataMode.UNKNOWN
    assert "NO GRANT CALLBACK" in ad.granted_mode_divergence(SYM)
    assert ad.feed_lag(SYM).granted_mode is MarketDataMode.UNKNOWN


@pytest.mark.asyncio
async def test_silent_downgrade_is_a_readable_finding():
    """`docs/CHECK-DEBT.md` D1.13: assert the GRANTED marketDataType and FAIL on a silent
    downgrade. ARC 013 measured mode 4 requested and mode 3 granted, with no error."""
    ad, _, _ = await make_adapter(
        grant_map={4: 3}, requested_mode=MarketDataMode.DELAYED_FROZEN
    )
    await ad.subscribe(SYM)
    assert ad.granted_mode(SYM) is MarketDataMode.DELAYED
    finding = ad.granted_mode_divergence(SYM)
    assert "SILENT DOWNGRADE" in finding
    assert "DELAYED_FROZEN" in finding and "DELAYED" in finding


@pytest.mark.asyncio
async def test_a_grant_the_adapter_cannot_interpret_lands_on_unknown():
    """An unrecognised mode is never coerced to the requested one. An unknown that reads as a
    known is worse than one that reads as unknown."""
    ad, _, _ = await make_adapter(grant_map={3: 77})
    await ad.subscribe(SYM)
    assert ad.granted_mode(SYM) is MarketDataMode.UNKNOWN


@pytest.mark.asyncio
async def test_mixed_grants_report_unknown_rather_than_one_of_them():
    """Two subscriptions granted different modes have no single mode, and reporting one of them
    adapter-wide would be a fabricated value."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    ad._symbols["OTHER"] = ad._symbols[SYM].__class__(
        granted_mode=MarketDataMode.DELAYED_FROZEN
    )
    assert ad.granted_mode() is MarketDataMode.UNKNOWN


@pytest.mark.asyncio
async def test_exhausted_poll_raises_rather_than_returning_zero_rows():
    """'The venue had nothing' and 'we could not reach the venue' must never read the same."""

    class AlwaysFails:
        def __call__(self, symbol):
            raise TimeoutError("no response")

    ad, _, _ = await make_adapter(
        grant_map={3: 3}, history=AlwaysFails(), poll_attempts=3
    )
    await ad.subscribe(SYM)
    with pytest.raises(FeedPollExhausted, match="exhausted 3 attempt"):
        await ad.poll_history(SYM)
    attempts = ad.poll_attempts()
    assert len(attempts) == 3 and all(not a.ok for a in attempts)
    assert all("TimeoutError" in a.error for a in attempts)


@pytest.mark.asyncio
async def test_bounded_poll_retries_and_then_succeeds():
    """The retry §6.4:373-374 mandates: it must actually retry, or the bound is decoration."""

    class FailsThenWorks:
        def __init__(self):
            self.calls = 0

        def __call__(self, symbol):
            self.calls += 1
            if self.calls < 3:
                raise OSError("transient")
            return [bar_row(1000.0)]

    source = FailsThenWorks()
    ad, sink, _ = await make_adapter(grant_map={3: 3}, history=source, poll_attempts=3)
    await ad.subscribe(SYM)
    assert await ad.poll_history(SYM) == 1
    assert source.calls == 3
    assert [a.ok for a in ad.poll_attempts()] == [False, False, True]
    assert len(sink.bars) == 1


def test_a_zero_attempt_budget_is_refused():
    """A poll budget of zero would make the only Stage 0 market-data path a silent no-op."""
    with pytest.raises(ValueError, match="floor is 1 attempt"):
        IBKRBrokerDatafeed(RecordingFeedSink(), poll_attempts=0)


@pytest.mark.asyncio
async def test_poll_without_a_history_source_refuses_rather_than_returning_nothing():
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    with pytest.raises(BrokerUnsupported, match="no history source"):
        await ad.poll_history(SYM)


# ===========================================================================
# §4 — BAR IMMUTABILITY (CHECK-DEBT D1.14)
# ===========================================================================


@pytest.mark.asyncio
async def test_a_sealed_bar_is_never_rewritten_and_the_revision_is_observable():
    """SEAL AND NEVER REWRITE, with the revision surfaced as its own event.

    The pathway, declared per `debug.md` §4 STAGE 4:
      PRECONDITIONS  — a subscribed symbol and a history source under test control.
      END STATE      — after a second poll returning DIFFERENT values for the same bar, the
                       published bar is byte-for-byte what it was, AND a consumer has learned
                       that the venue's story changed.
      OBSERVABLES    — `sink.bars` (unchanged, still length 1), the sealed bar's payload
                       (identical to the first poll's), `sink.bar_revisions` (length 1 naming
                       the differing fields), and the arrival ORDER in `sink.sequence`.
    'The call did not raise' is not one of those, deliberately."""
    first = bar_row(1000.0, c=1.5, v=10.0)
    revised = bar_row(1000.0, c=1.7, v=12.0)
    polls = [[first], [revised]]
    ad, sink, _ = await make_adapter(grant_map={3: 3}, history=lambda s: polls.pop(0))
    await ad.subscribe(SYM)

    await ad.poll_history(SYM)
    published = sink.bars[0]
    payload_before = published.payload()
    assert len(sink.bars) == 1

    # NON-VACUITY, ASSERTED EXPLICITLY AND FIRST. A test whose second poll returns identical
    # data proves nothing, and would pass against an adapter with no seal at all. This
    # assertion is what stops this test silently degrading into that one.
    assert tuple(first[f] for f in BAR_PAYLOAD_FIELDS) != tuple(
        revised[f] for f in BAR_PAYLOAD_FIELDS
    ), "the two polls must genuinely differ or this test measures nothing"

    await ad.poll_history(SYM)

    # THE BAR IS UNCHANGED — not re-emitted, not mutated, same object, same payload.
    assert len(sink.bars) == 1
    assert sink.bars[0] is published
    assert published.payload() == payload_before
    assert ad.sealed_bar(SYM, 1000.0, 60.0).payload() == payload_before

    # THE REVISION IS OBSERVABLE, on its own event and in the retained record.
    assert len(sink.bar_revisions) == 1
    rev = sink.bar_revisions[0]
    assert isinstance(rev, BarRevision)
    assert rev.sealed is published
    assert set(rev.differing_fields) == {"close", "volume"}
    assert rev.revised_payload == tuple(revised[f] for f in BAR_PAYLOAD_FIELDS)
    assert ad.bar_revisions() == (rev,)

    # AND IT DID NOT ARRIVE LOOKING LIKE NEW DATA — that is the D1.14 defect, and the ordering
    # is the observable for it.
    assert sink.sequence.count("on_bar") == 1
    assert sink.sequence[-1] == "on_bar_revision"


@pytest.mark.asyncio
async def test_an_identical_repoll_is_not_a_revision():
    """A stream of no-op 'revisions' is how a real one becomes invisible."""
    row = bar_row(1000.0)
    ad, sink, _ = await make_adapter(grant_map={3: 3}, history=lambda s: [dict(row)])
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    await ad.poll_history(SYM)
    assert len(sink.bars) == 1
    assert sink.bar_revisions == []
    assert ad.bar_revisions() == ()


def test_bar_revision_refuses_to_exist_without_a_difference():
    """The type itself enforces it, so no future call site can construct a hollow revision."""
    sealed = Bar(
        symbol=SYM,
        bar_start_venue_ts=1000.0,
        period_s=60.0,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
        recv_ts=5.0,
        source=BarSource.POLLED_HISTORY,
        seal_seq=1,
    )
    with pytest.raises(ValueError, match="no differing field"):
        BarRevision(
            sealed=sealed,
            revised_payload=sealed.payload(),
            differing_fields=(),
            recv_ts=6.0,
            revision_seq=1,
        )
    with pytest.raises(ValueError, match="equals the sealed payload"):
        BarRevision(
            sealed=sealed,
            revised_payload=sealed.payload(),
            differing_fields=("close",),
            recv_ts=6.0,
            revision_seq=1,
        )


@pytest.mark.asyncio
async def test_distinct_bars_are_distinct_seals():
    """The seal key is (symbol, bar_start, period). Two periods opening at the same instant are
    two bars, and collapsing them would make one silently overwrite the other."""
    rows = [bar_row(1000.0, period_s=60.0), bar_row(1000.0, period_s=300.0)]
    ad, sink, _ = await make_adapter(grant_map={3: 3}, history=lambda s: rows)
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    assert len(sink.bars) == 2
    assert {b.period_s for b in sink.bars} == {60.0, 300.0}
    assert sink.bar_revisions == []


@pytest.mark.asyncio
async def test_sealed_bars_carry_both_clocks_and_their_source():
    """A consumer must be able to compute BOTH ages on a bar without knowing the vendor, and to
    know whether its history is revisable at all."""
    ad, sink, _ = await make_adapter(
        grant_map={3: 3}, history=lambda s: [bar_row(1000.0)]
    )
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    sealed = sink.bars[0]
    assert sealed.bar_start_venue_ts == 1000.0  # venue clock
    assert sealed.recv_ts > 0.0  # local clock, separate field
    assert sealed.source is BarSource.POLLED_HISTORY
    assert sealed.seal_key == (SYM, 1000.0, 60.0)


# ===========================================================================
# §5 — MULTI-WRITER FIELDS: ONE ASSERTION PER WRITER (ARC 020 A8)
# ===========================================================================
#
# Two fields in this adapter are written by more than one handler. Each writer's MEANING is
# asserted separately below, because that is the only thing that would have caught the
# `avg_price` incidents: both writers were individually plausible, and only a test that pinned
# each writer's meaning could expose that they disagreed.
#
# A third candidate was PREVENTED rather than asserted: "the last time we heard from the venue
# about this symbol" has two natural writers — a stream packet and a poll response — with
# genuinely different meanings, so it is TWO FIELDS (`last_tick_recv_ts`, `last_poll_recv_ts`)
# and not one. `test_the_two_receipt_clocks_are_not_one_field` pins that decision.


@pytest.mark.asyncio
async def test_granted_mode_writer_1_subscribe_means_no_callback_yet():
    """WRITER 1 — `subscribe()`. MEANING: 'no grant callback has been received', which is NOT
    'the venue granted UNKNOWN' and NOT the requested mode."""
    ad, _, _ = await make_adapter(grant_map={3: None})
    await ad.subscribe(SYM)
    assert ad._symbols[SYM].granted_mode is MarketDataMode.UNKNOWN
    assert ad._symbols[SYM].requested_mode is MarketDataMode.DELAYED
    assert "NO GRANT CALLBACK" in ad.granted_mode_divergence(SYM)


@pytest.mark.asyncio
async def test_granted_mode_writer_2_venue_callback_means_the_mode_in_effect():
    """WRITER 2 — `_on_ib_market_data_type()`. MEANING: the venue affirmatively said which mode
    it is serving. The ONLY writer entitled to report an actual mode."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    assert ad._symbols[SYM].granted_mode is MarketDataMode.DELAYED
    assert ad.granted_mode_divergence(SYM) == ""


@pytest.mark.asyncio
async def test_granted_mode_writer_3_disconnect_means_the_grant_died_with_the_session():
    """WRITER 3 — `disconnect()`. MEANING: the session that granted this is gone, so the grant
    is gone. Retaining it across a boundary is `docs/CHECK-DEBT.md` D1.24's shape."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    assert ad._symbols[SYM].granted_mode is MarketDataMode.DELAYED
    await ad.disconnect()
    assert ad._symbols[SYM].granted_mode is MarketDataMode.UNKNOWN


@pytest.mark.asyncio
async def test_resubscribe_rearms_the_sentinel_rather_than_inheriting_the_old_grant():
    """A SECOND `subscribe()` for a symbol that already holds a grant must re-arm the
    sentinel BEFORE the new request, so the new subscription's grant is measured rather
    than inherited from the previous one.

    WHY THIS TEST EXISTS, and it is not hypothetical: `_SymbolFeedState.granted_mode`
    already DEFAULTS to `UNKNOWN`, so on a first subscribe the explicit sentinel write in
    `subscribe()` changes nothing and deleting it is invisible. `setdefault` returns the
    EXISTING state on a re-subscribe, so without that write a symbol re-subscribed against
    a venue that grants nothing keeps reporting the mode a previous subscription was
    granted — a grant that never happened for this subscription, which is D1.13's defect
    reached by a different road.

    MEASURED IN ARC 021 PHASE 4, not theorised. Deleting the sentinel write from
    `subscribe()` was planted against the real adapter and BOTH the D1.13 gate and all 49
    tests passed. This test and its sibling below are what that plant now fails."""
    ad, _, fake = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    assert ad._symbols[SYM].granted_mode is MarketDataMode.DELAYED

    # Same symbol, but the venue now returns NO grant callback (ARC 013 measured exactly
    # this for mode 1: error 354, zero ticks, no callback).
    fake.grant_map = {3: None}
    await ad.subscribe(SYM)
    assert ad._symbols[SYM].granted_mode is MarketDataMode.UNKNOWN, (
        "a re-subscribe inherited the previous subscription's grant — the sentinel was "
        "not re-armed, so an ungranted subscription reports a mode it was never given"
    )
    assert "NO GRANT CALLBACK" in ad.granted_mode_divergence(SYM)


@pytest.mark.asyncio
async def test_adapter_wide_granted_mode_reports_the_grant_never_the_request():
    """`granted_mode()` with no symbol must report what was GRANTED across the
    subscriptions, never what was requested — including when the venue silently
    downgrades, which is the ARC 013 measurement D1.13 exists to catch.

    The per-symbol branch is asserted by the WRITER 2 test above; this asserts the
    ADAPTER-WIDE branch, which is a separate code path and was separately unprotected.
    MEASURED IN ARC 021 PHASE 4: substituting `requested_mode` for `granted_mode` in that
    branch was planted against the real adapter and both the gate and all 49 tests
    passed."""
    ad, _, _ = await make_adapter(
        grant_map={4: 3}, requested_mode=MarketDataMode.DELAYED_FROZEN
    )
    await ad.subscribe(SYM)
    assert ad.granted_mode() is MarketDataMode.DELAYED, (
        "adapter-wide granted_mode did not report the GRANTED mode"
    )
    assert ad.granted_mode() is not MarketDataMode.DELAYED_FROZEN, (
        "adapter-wide granted_mode reported the REQUESTED mode — that the request was "
        "made is not evidence of what was granted"
    )
    # Non-vacuity: the two modes must actually differ, or the assertion above is
    # satisfied by them being the same value rather than by the adapter being correct.
    assert MarketDataMode.DELAYED is not MarketDataMode.DELAYED_FROZEN


@pytest.mark.asyncio
async def test_feed_state_writer_1_connect_speaks_only_about_the_session():
    """WRITER 1 — `connect()`. MEANING: a session exists. NOT a claim that data is fresh."""
    ad, sink, _ = await make_adapter()
    assert ad.feed_state() is FeedState.UP
    assert sink.feed_statuses[0] == (FeedState.UP, None, "session established")


@pytest.mark.asyncio
async def test_feed_state_writer_2_disconnect_means_no_session_not_stale_data():
    """WRITER 2 — `disconnect()`. MEANING: no session. DOWN and STALE are different facts and a
    consumer's response to them differs."""
    ad, sink, _ = await make_adapter()
    await ad.disconnect()
    assert ad.feed_state() is FeedState.DOWN
    assert sink.feed_statuses[-1] == (FeedState.DOWN, None, "requested")


@pytest.mark.asyncio
async def test_feed_state_writer_3_evaluate_freshness_is_the_only_writer_of_stale():
    """WRITER 3 — `evaluate_freshness()`. MEANING: a session exists AND the data behind it is
    (not) advancing. It is the only writer entitled to say STALE; conflating that with the
    session writers is how a live socket with a dead feed reads as healthy."""
    ad, sink, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    assert ad.evaluate_freshness(10_000.0) is FeedState.STALE
    state, _symbol, reason = sink.feed_statuses[-1]
    assert state is FeedState.STALE
    # ARC 023 (AMENDMENT 6): the reason is the PER-CHANNEL summary, derived from the report
    # rather than restated, so the event text cannot disagree with the object it summarises.
    assert "AMENDMENT 6" in reason and "cannot_measure=['tick']" in reason
    # And the session writers never emit STALE, on any path.
    session_states = [
        s
        for s, _, why in sink.feed_statuses
        if why in ("session established", "requested")
    ]
    assert FeedState.STALE not in session_states


@pytest.mark.asyncio
async def test_the_two_receipt_clocks_are_not_one_field():
    """The PREVENTED multi-writer field, pinned so a later refactor cannot merge them.

    A live stream with a dead poller and a dead stream with a live poller are opposite
    conditions. One field written by both handlers would carry two meanings depending on which
    wrote last — the `avg_price` shape, whose third instance `docs/CHECK-DEBT.md` D1.29
    records."""
    ad, _, _ = await make_adapter(grant_map={3: 3}, history=lambda s: [bar_row(1000.0)])
    await ad.subscribe(SYM)
    ad._on_ib_tick(SYM, 1.0, 1.0, 900.0, recv_ts=111.0)
    assert ad.last_tick_recv_ts(SYM) == 111.0
    assert ad.last_poll_recv_ts(SYM) is None
    await ad.poll_history(SYM)
    assert ad.last_tick_recv_ts(SYM) == 111.0  # untouched by the poll
    assert ad.last_poll_recv_ts(SYM) is not None


# ===========================================================================
# §6 — STAGE 0 ABSENCES, DECLARED AND REFUSED
# ===========================================================================


def test_capabilities_declare_every_stage0_absence():
    caps = IBKRBrokerDatafeed.CAPABILITIES
    assert caps.realtime_tick_stream is False  # GAP-D1
    assert caps.delayed_tick_stream is True  # GAP-D3
    assert caps.polled_history is True  # GAP-D2
    assert caps.revisable_history is True  # GAP-D5
    assert caps.venue_sourced_tick_ts is True
    assert caps.pushes_feed_status is False  # GAP-D4
    unmet = caps.unmet_contract_paths()
    # THREE, not four: `venue_sourced_tick_ts` is True on this venue (the delayed stream
    # carries `delayedLastTimestamp`, which is the field ARC 013 measured the lag FROM), so
    # that path is MET and correctly absent from the list. Asserting the exact length is what
    # makes a future capability flip visible rather than absorbed.
    assert len(unmet) == 3, unmet
    assert any("real-time firehose" in u for u in unmet)
    assert any("on_feed_status" in u for u in unmet)
    assert any("D1.14" in u for u in unmet)


@pytest.mark.asyncio
async def test_the_realtime_path_refuses_loudly_and_names_both_error_codes():
    """A consumer must not be able to call a path that does not exist and receive silence.

    Both measured codes appear, attributed to their own API call — they are not two accounts of
    one event: `reqTickByTickData` -> 10189 (ARC 012), `reqMarketDataType(1)`+`reqMktData` ->
    354 with no grant callback (ARC 013)."""
    ad, _, _ = await make_adapter(grant_map={3: 3})
    with pytest.raises(BrokerUnsupported) as exc:
        ad.request_realtime_ticks(SYM)
    message = str(exc.value)
    assert "10189" in message and "354" in message
    assert "PRODUCT CLASS" in message
    # GAP-D2 is named AT THE PLACE SOMEBODY WOULD TRY IT.
    assert "reqHistoricalTicks is NOT a back door" in message
    assert "624" in message and "604" in message


@pytest.mark.asyncio
async def test_subscribing_in_realtime_mode_refuses_rather_than_degrading():
    """A silent degrade to delayed would be the contract rotting exactly as
    `ibkr_mapping.py`'s header warns."""
    ad, _, _ = await make_adapter(
        grant_map={3: 3}, requested_mode=MarketDataMode.REALTIME
    )
    with pytest.raises(BrokerUnsupported, match="GAP-D1"):
        await ad.subscribe(SYM)


def test_every_mapped_error_code_carries_measured_evidence():
    """A declaration is not evidence. The same gate `broker_order_ibkr.IB_REJECT_EVIDENCE`
    carries, reached independently on this side of invariant 3."""
    assert set(IB_MARKETDATA_EVIDENCE) == {10189, 354, 10167}
    for code, evidence in IB_MARKETDATA_EVIDENCE.items():
        assert "MEASURED" in evidence, code
        assert "ARC 01" in evidence, code
        assert "SESSION.md" in evidence or "CHECK-DEBT.md" in evidence, code


@pytest.mark.asyncio
async def test_verbs_refuse_without_a_session():
    ad = IBKRBrokerDatafeed(RecordingFeedSink(), ib=FakeIBFeed())
    with pytest.raises(BrokerNotConnected, match="subscribe"):
        await ad.subscribe(SYM)
    with pytest.raises(BrokerNotConnected, match="poll_history"):
        await ad.poll_history(SYM)


@pytest.mark.asyncio
async def test_connect_without_a_client_refuses_rather_than_pretending():
    ad = IBKRBrokerDatafeed(RecordingFeedSink())
    with pytest.raises(BrokerNotConnected, match="no ib_async.IB supplied"):
        await ad.connect()


# ===========================================================================
# §7 — IDENTITY
# ===========================================================================


@pytest.mark.parametrize("bad", [0, 1])
def test_reserved_client_ids_are_refused_at_construction(bad):
    with pytest.raises(ValueError, match=f"clientId={bad} refused"):
        IBKRBrokerDatafeed(RecordingFeedSink(), client_id=bad)


@pytest.mark.asyncio
async def test_the_production_client_id_is_declared_and_used():
    assert DATAFEED_CLIENT_ID == 2
    _ad, _, fake = await make_adapter()
    assert fake.client_id == DATAFEED_CLIENT_ID
    # And it is not the order path's. A shared id would put both libraries on ONE IBKR
    # connection, which is §2A:105-106 invariant 3 false at the transport layer.
    assert DATAFEED_CLIENT_ID != 1


# ===========================================================================
# §8 — CONTROLS: the assertions must be able to FAIL
# ===========================================================================


def test_hollow_control_is_structurally_indistinguishable():
    """The control's job is to pass every SHAPE check. If it failed one, it would be failing
    for the wrong reason and would have stopped measuring what it was built to measure."""
    hollow = HollowBrokerDatafeed(RecordingFeedSink())
    assert check_structural_conformance(hollow, DATAFEED_PORT_VERBS) == []
    assert (
        check_await_conformance(hollow, BrokerDatafeedPort, DATAFEED_PORT_VERBS) == []
    )


def test_hollow_control_fails_the_absence_assertions():
    """AND behaviourally empty. Its `feed_lag()` returns a fully-populated, plausible object —
    declared 0.0, granted REALTIME — which is precisely the pre-ARC-021 stub's answer and
    precisely what AMENDMENT 3 forbids. A suite that only checked the TYPE would pass it."""
    lag = HollowBrokerDatafeed(RecordingFeedSink()).feed_lag()
    assert isinstance(lag, FeedLag)  # shape: indistinguishable
    # behaviour: it fabricates, and every absence assertion in §3 rejects it.
    assert lag.declared_lag_s == 0.0
    assert lag.provenance is not LagProvenance.UNOBSERVED
    assert lag.granted_mode is MarketDataMode.REALTIME
    assert lag.agreement is LagAgreement.NOT_OBSERVED
    # THE CONSEQUENCE, which is the whole point: it hands a consumer a confident number for a
    # quantity nothing measured.
    assert lag.excess_staleness_s(NOW - 5.0, NOW) == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_hollow_control_emits_nothing():
    """Driven, not merely constructed — `debug.md` §7.12 instance 7 survived because no feed
    event was ever driven through the sink."""
    sink = RecordingFeedSink()
    hollow = HollowBrokerDatafeed(sink)
    await hollow.connect()
    await hollow.subscribe(SYM)
    await hollow.disconnect()
    assert sink.sequence == []
    # The real adapter, driven identically, does emit.
    ad, real_sink, _ = await make_adapter(grant_map={3: 3})
    await ad.subscribe(SYM)
    await ad.disconnect()
    assert real_sink.sequence == ["on_feed_status", "on_feed_status"]


# ===========================================================================
# §9 — D1.38: THE PORT'S SYNC/ASYNC SPLIT (ARC 022)
#
# The port went from five verbs, all sync, to seven on a declared split. The property
# under test is not "the adapter has async methods" — that is shape, and `callable()`
# already passes shape. It is that ONE declared partition governs the Protocol, the
# adapter and the roster, and that a divergence in EITHER direction is named.
# ===========================================================================


def test_the_declared_partition_covers_the_roster_and_has_two_non_empty_halves():
    """NON-VACUITY OF EVERY §9 ASSERTION BELOW (`debug.md` §7.3), asserted first.

    Every comparison in this section is between the Protocol and `DATAFEED_ASYNC_VERBS`. If the
    partition were empty, or the whole roster, both sides would agree trivially and the section
    would be green over a port that had made no decision — which is the pre-ARC-022 port
    exactly, and it passed `check_await_conformance` for two arcs while doing so."""
    roster = set(DATAFEED_PORT_VERBS)
    assert DATAFEED_ASYNC_VERBS <= roster, sorted(DATAFEED_ASYNC_VERBS - roster)
    sync_half = roster - DATAFEED_ASYNC_VERBS
    assert DATAFEED_ASYNC_VERBS and sync_half, (
        f"the split has an empty half — async={sorted(DATAFEED_ASYNC_VERBS)} "
        f"sync={sorted(sync_half)}"
    )
    # The ruling's own division: the wire verbs await, the retained observables do not.
    assert sync_half == {"feed_lag", "granted_mode"}


def test_the_protocol_and_the_declared_partition_agree_verb_by_verb():
    """The Protocol's own `iscoroutinefunction` truth against the ONE declared constant.

    COMPARED VERB BY VERB, NOT AS TWO SETS (`debug.md` §7.7): an aggregate `len(async) == 5`
    survives any swap that keeps the count. `check_await_conformance` makes the same comparison
    internally; this asserts it from outside the gate so the gate is not the only witness to its
    own scope."""
    verdicts = {
        verb: inspect.iscoroutinefunction(getattr(BrokerDatafeedPort, verb))
        for verb in DATAFEED_PORT_VERBS
    }
    expected = {verb: verb in DATAFEED_ASYNC_VERBS for verb in DATAFEED_PORT_VERBS}
    assert verdicts == expected


def test_the_datafeed_split_is_not_the_order_split():
    """The two ports disagree about `disconnect`, and that disagreement is the ruling.

    If both ports happened to draw the line in the same place, `PORT_ASYNC_VERBS` would be one
    constant wearing two names and nothing here would be proving that the partition is looked up
    PER PORT. `disconnect` is the verb that separates them: sync on the order path because a
    protective sequence must not await (§2A:107 invariant 5), async on the datafeed because
    nothing there is protective."""
    assert "disconnect" in DATAFEED_ASYNC_VERBS
    assert "disconnect" not in ORDER_ASYNC_VERBS
    assert PORT_ASYNC_VERBS[BrokerDatafeedPort] is DATAFEED_ASYNC_VERBS
    assert PORT_ASYNC_VERBS[BrokerOrderPort] is ORDER_ASYNC_VERBS


@pytest.mark.asyncio
async def test_every_wire_verb_is_actually_awaitable_on_the_real_adapter():
    """DRIVEN, not inspected. `iscoroutinefunction` is a declaration check and this section is
    otherwise all declaration; a verb could satisfy every assertion above and still be
    un-awaitable in practice. Each wire verb is therefore awaited against the real adapter."""
    ad, _, _ = await make_adapter(grant_map={3: 3}, history=lambda s: [bar_row(1000.0)])
    assert await ad.subscribe(SYM) is None
    assert await ad.poll_history(SYM) == 1
    assert await ad.unsubscribe(SYM) is None
    assert await ad.disconnect() is None


def test_the_await_checker_names_an_async_verb_implemented_sync():
    """CAN-FAIL, DIRECTION 1. `AwaitDivergentBrokerDatafeed` is the permanent plant (§7.2 — a
    plant never touches a production artifact where a control class can carry it)."""
    plant = AwaitDivergentBrokerDatafeed(RecordingFeedSink())
    # STRUCTURALLY INVISIBLE — which is why the structural checker is not enough.
    assert check_structural_conformance(plant, DATAFEED_PORT_VERBS) == []
    diverged = check_await_conformance(plant, BrokerDatafeedPort, DATAFEED_PORT_VERBS)
    assert len(diverged) == 1, diverged
    assert diverged[0].startswith("subscribe:")
    assert "port declares async" in diverged[0] and "adapter is sync" in diverged[0]


def test_the_await_checker_names_a_sync_verb_implemented_async():
    """CAN-FAIL, DIRECTION 2 — the direction ARC 015 never instrumented.

    `debug.md` §7.12 instance 4 is this direction: an `async def` passing a sync-declared port,
    handing the caller an un-awaited coroutine object instead of a value. A gate demonstrated
    able to fail in one direction has been demonstrated in one direction."""
    plant = CoroutineDivergentBrokerDatafeed(RecordingFeedSink())
    assert check_structural_conformance(plant, DATAFEED_PORT_VERBS) == []
    diverged = check_await_conformance(plant, BrokerDatafeedPort, DATAFEED_PORT_VERBS)
    assert len(diverged) == 1, diverged
    assert diverged[0].startswith("feed_lag:")
    assert "port declares sync" in diverged[0] and "adapter is async" in diverged[0]
    # AND THE CONSEQUENCE, driven rather than asserted: an unaware caller gets an object it
    # cannot use. This is what the declaration check is a proxy for, so it is measured once.
    result = plant.feed_lag()
    assert not isinstance(result, FeedLag)
    assert inspect.iscoroutine(result)
    # `no-member` below: pylint reads the RETURN ANNOTATION and believes this is a `FeedLag`,
    # which is exactly the mistake a human reader makes and exactly what the two assertions
    # above disprove — the object is a coroutine, and `.close()` is a coroutine method.
    # Suppressed on this line only, with the assertions standing as its evidence.
    result.close()  # pylint: disable=no-member  # never awaited; closed so GC does not warn


def test_the_two_plants_are_caught_on_different_verbs():
    """Verdict by verdict (`debug.md` §7.7). 'Both plants failed' is the aggregate that would
    hide one instrument standing in for two."""
    d1 = check_await_conformance(
        AwaitDivergentBrokerDatafeed(RecordingFeedSink()),
        BrokerDatafeedPort,
        DATAFEED_PORT_VERBS,
    )
    d2 = check_await_conformance(
        CoroutineDivergentBrokerDatafeed(RecordingFeedSink()),
        BrokerDatafeedPort,
        DATAFEED_PORT_VERBS,
    )
    assert d1[0].split(":")[0] != d2[0].split(":")[0]


def test_an_empty_roster_is_reported_vacuous_rather_than_passed():
    """§7.12 CONDITION A, driven. An empty `verbs` is the likeliest way this gate passes having
    compared nothing, because every caller reads its roster from a constant elsewhere."""
    verdict = check_await_conformance(
        StubBrokerDatafeed(RecordingFeedSink()), BrokerDatafeedPort, ()
    )
    assert len(verdict) == 1 and verdict[0].startswith("VACUOUS:")


def test_a_roster_verb_the_protocol_does_not_declare_is_a_defect():
    """§7.12 CONDITION E, and the hole ARC 021 sat in.

    `poll_history` and `granted_mode` were on the IBKR adapter and absent from both the Protocol
    and the roster for the whole of ARC 021, and this checker reported clean throughout because
    `if want is None: continue` skipped anything the Protocol did not declare. A verb the roster
    names and the Protocol does not is now a defect rather than a gap in the scan."""
    verdict = check_await_conformance(
        StubBrokerDatafeed(RecordingFeedSink()),
        BrokerDatafeedPort,
        (*DATAFEED_PORT_VERBS, "no_such_verb"),
    )
    assert len(verdict) == 1, verdict
    assert verdict[0].startswith("no_such_verb:") and "NOT DECLARED" in verdict[0]


def test_a_port_with_no_declared_partition_says_so_rather_than_passing_quietly():
    """§7.12 CONDITION C. A future third port added without a `PORT_ASYNC_VERBS` entry gets
    ARC 014's behaviour and nothing more — which is legitimate, and must not be silent."""

    class UnregisteredPort(Protocol):
        def feed_lag(self) -> FeedLag: ...

    verdict = check_await_conformance(
        StubBrokerDatafeed(RecordingFeedSink()), UnregisteredPort, ("feed_lag",)
    )
    assert any(v.startswith("NOT PARTITION-CHECKED:") for v in verdict), verdict


def test_every_datafeed_adapter_in_the_tree_conforms_to_the_split():
    """DERIVED FROM THE TREE, NOT LISTED (`debug.md` §7.4, first row). A hardcoded list of
    adapters stops covering the next one somebody writes. The subjects are every class under
    `scripts/broker/` carrying the whole roster, which is how a new adapter joins this test by
    being written."""
    subjects = _datafeed_adapter_classes()
    # NON-VACUITY: the derivation must find the adapters that exist, or this passes over an
    # empty set. Four are known to exist today; more is fine, fewer is the defect.
    assert len(subjects) >= 4, sorted(c.__name__ for c in subjects)
    assert {"IBKRBrokerDatafeed", "StubBrokerDatafeed"} <= {
        c.__name__ for c in subjects
    }
    for cls in sorted(subjects, key=lambda c: c.__name__):
        # The two permanent plants are EXPECTED to diverge — that is their whole job.
        if cls.__name__.endswith("DivergentBrokerDatafeed"):
            continue
        bad = check_await_conformance(cls, BrokerDatafeedPort, DATAFEED_PORT_VERBS)
        assert bad == [], f"{cls.__name__}: {bad}"


# ===========================================================================
# §10 — AMENDMENT 4: WHOSE BAR IS IT (ARC 022)
# ===========================================================================


def test_a_tick_aggregated_bar_is_unconstructible():
    """AMENDMENT 4 ENFORCED, not documented. The refusal is in the TYPE, so no call site —
    present or future, adapter or consumer — can build one."""
    with pytest.raises(ValueError, match="AMENDMENT 4"):
        Bar(
            symbol=SYM,
            bar_start_venue_ts=1000.0,
            period_s=60.0,
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            recv_ts=5.0,
            source=BarSource.TICK_AGGREGATED,
            seal_seq=1,
        )


def test_the_refusal_is_an_allowlist_so_an_unargued_new_source_is_refused_too():
    """FAIL CLOSED (`CLAUDE.md` directive 4). A blacklist would admit every member nobody
    thought to blacklist; the allowlist refuses one that was never argued.

    Driven with a stand-in member rather than by editing the enum — a plant never touches a
    production artifact (`debug.md` §7.2) — and the stand-in is enough because
    `Bar.__post_init__` tests MEMBERSHIP of `VENUE_SOURCED_BAR_SOURCES`, not identity with
    `TICK_AGGREGATED`."""
    unargued = enum.Enum("BarSourceLater", {"DERIVED_FROM_QUOTES": "derived"})
    assert unargued.DERIVED_FROM_QUOTES not in VENUE_SOURCED_BAR_SOURCES
    with pytest.raises(ValueError, match="AMENDMENT 4"):
        Bar(
            symbol=SYM,
            bar_start_venue_ts=1000.0,
            period_s=60.0,
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            recv_ts=5.0,
            source=unargued.DERIVED_FROM_QUOTES,
            seal_seq=1,
        )


def test_both_venue_sourced_members_are_accepted():
    """NON-VACUITY of the two tests above: if `Bar` refused EVERY source they would pass while
    the type was simply broken, and `debug.md` failure mode #1 is a plant and a control
    returning the same verdict."""
    for source in sorted(VENUE_SOURCED_BAR_SOURCES, key=lambda s: s.value):
        bar = Bar(
            symbol=SYM,
            bar_start_venue_ts=1000.0,
            period_s=60.0,
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            recv_ts=5.0,
            source=source,
            seal_seq=1,
        )
        assert bar.source is source
    assert {
        BarSource.POLLED_HISTORY,
        BarSource.VENUE_STREAM,
    } == VENUE_SOURCED_BAR_SOURCES


def test_the_adapter_derives_no_bar_from_ticks():
    """PROOF BY ABSENCE (`debug.md` §7.6), the other half of AMENDMENT 4's enforcement.

    The type refuses a tick-aggregated bar; this asserts the adapter never tries. Driving a
    stream of ticks and observing no bar would be the call-site version of the check and would
    pass an adapter that aggregated on a path this test did not drive. Instead: the module
    contains exactly ONE `Bar(...)` construction, and it is on the poll path."""
    source = (NIX_HOME / "scripts" / "broker" / "broker_datafeed_ibkr.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    constructions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Bar"
    ]
    assert len(constructions) == 1, [n.lineno for n in constructions]
    enclosing = [
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(n is constructions[0] for n in ast.walk(fn))
    ]
    assert "_ingest_history" in enclosing, enclosing


@pytest.mark.asyncio
async def test_a_polled_bar_declares_the_venue_as_its_source():
    """The positive half: what the adapter DOES publish carries venue provenance."""
    ad, sink, _ = await make_adapter(
        grant_map={3: 3}, history=lambda s: [bar_row(1000.0)]
    )
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    assert sink.bars[0].source is BarSource.POLLED_HISTORY
    assert sink.bars[0].source in VENUE_SOURCED_BAR_SOURCES


# ===========================================================================
# §11 — AMENDMENT 3's REFINEMENT: AN OPTIONAL NEEDS AN OBSERVABLE ABSENCE (ARC 022)
# ===========================================================================


def test_the_four_structural_payload_fields_admit_no_none():
    """The refinement, read off the type. `open/high/low/close` are the bar; a venue with no
    open has no bar to return, so no observable absence justifies an optional and the optional
    is gone. `volume` keeps its own, justified at the field."""
    assert BAR_REQUIRED_PAYLOAD_FIELDS == ("open", "high", "low", "close")
    # DERIVED FROM THE ANNOTATIONS, so the constant cannot drift from the type it describes.
    for name in BAR_REQUIRED_PAYLOAD_FIELDS:
        assert "None" not in str(Bar.__annotations__[name]), name
    assert "None" in str(Bar.__annotations__["volume"])
    # And the two halves partition the payload — no field is in neither.
    assert set(BAR_REQUIRED_PAYLOAD_FIELDS) | {"volume"} == set(BAR_PAYLOAD_FIELDS)


@pytest.mark.asyncio
async def test_a_row_missing_a_structural_field_is_refused_not_defaulted():
    """A MALFORMED ROW and a VENUE ABSENCE must not read the same.

    ARC 021 read these four with `.get()`, so a row without an open produced a bar with
    `open=None` — an absence the venue never declared, manufactured by the reader. That is the
    substitution AMENDMENT 3 forbids, arrived at by applying AMENDMENT 3 too widely."""
    for missing in BAR_REQUIRED_PAYLOAD_FIELDS:
        row = bar_row(1000.0)
        del row[missing]
        ad, sink, _ = await make_adapter(grant_map={3: 3}, history=lambda s, r=row: [r])
        await ad.subscribe(SYM)
        with pytest.raises(MalformedBarRow, match=missing):
            await ad.poll_history(SYM)
        assert sink.bars == [], missing


@pytest.mark.asyncio
async def test_a_row_missing_only_volume_is_still_a_bar():
    """NON-VACUITY of the refusal above (`debug.md` §7.1's CONTROL half): if `_require_ohlc`
    refused every incomplete row, the test above would pass against an adapter that had simply
    stopped accepting bars. Volume's absence is the case that must still go through."""
    row = bar_row(1000.0)
    del row["volume"]
    ad, sink, _ = await make_adapter(grant_map={3: 3}, history=lambda s: [row])
    await ad.subscribe(SYM)
    assert await ad.poll_history(SYM) == 1
    assert sink.bars[-1].volume is None
    assert sink.bars[-1].open == 1.0


def test_zero_volume_and_absent_volume_remain_different_facts():
    """The reason `volume` kept its optional. 0.0 is a real volume — a bar in which nothing
    traded — and `None` is a bar for which the venue reports no volume at all. A consumer
    reading `bar.volume or 0.0` collapses them, which is what the optional exists to prevent."""

    def bar_with(volume):
        return Bar(
            symbol=SYM,
            bar_start_venue_ts=1000.0,
            period_s=60.0,
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=volume,
            recv_ts=5.0,
            source=BarSource.POLLED_HISTORY,
            seal_seq=1,
        )

    assert bar_with(0.0).payload() != bar_with(None).payload()
    # And a revision between them is a REAL revision, not a no-op.
    revision = BarRevision(
        sealed=bar_with(None),
        revised_payload=bar_with(0.0).payload(),
        differing_fields=("volume",),
        recv_ts=6.0,
        revision_seq=1,
    )
    assert revision.differing_fields == ("volume",)


# ===========================================================================
# §12 — ARC 023: AMENDMENT 6 (freshness is per-channel), F13, F12, D1.39/D1.40
# ===========================================================================


@pytest.mark.asyncio
async def test_a_symbol_fed_only_by_polling_is_not_reported_stale():
    """F21, THE REPAIR. `evaluate_freshness` read `last_tick_venue_ts` alone, so a symbol fed
    entirely by successful, current polls was permanently STALE — and
    `nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 makes STALE mean *halt new entries AND
    flatten open*. The module fail-closed on the only margin-class path Stage 0 has (GAP-D4).

    THE REPAIR IS NOT "call it fresh". It is that the two channels are reported SEPARATELY, so
    a poll channel that cannot be measured reads as CANNOT_MEASURE and not as a failure, and a
    poll channel that CAN be measured reads on its own evidence."""
    now = 1000.0
    ad, _, _ = await make_adapter(
        grant_map={3: 3}, history=lambda s: [bar_row(now - 1.0)]
    )
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    report = ad.freshness(now, SYM)[0]

    # BOTH channels are reported, and neither is collapsed into the other.
    assert report.observed_channels == (FeedChannel.TICK, FeedChannel.POLL)
    tick = report.channel(FeedChannel.TICK)
    poll = report.channel(FeedChannel.POLL)
    assert tick is not None and poll is not None

    # THE TICK CHANNEL: no packet has ever arrived, so it cannot be measured — NOT stale.
    assert tick.venue_ts is None
    assert tick.state is ChannelState.CANNOT_MEASURE

    # THE POLL CHANNEL: a real, current venue timestamp, and NO lag figure on this system —
    # so the honest answer is CANNOT_MEASURE and it is distinguishable from a degraded feed.
    assert poll.venue_ts == now - 1.0
    assert poll.lag.channel is FeedChannel.POLL
    assert poll.lag.provenance is LagProvenance.UNOBSERVED
    assert poll.state is ChannelState.CANNOT_MEASURE
    assert report.stale_channels == ()

    # AND THE POINT: the two channels' lags are DIFFERENT objects with different grades. The
    # tick channel's measured figure is not reported as the poll channel's.
    assert tick.lag.declared_lag_s == IB_STAGE0_DELAYED_LAG.mean_s
    assert poll.lag.declared_lag_s is None


@pytest.mark.asyncio
async def test_a_poll_channel_with_a_declared_lag_reads_fresh_on_its_own_evidence():
    """The other half of F21: given a figure FOR THAT CHANNEL, the poll channel is measurable
    and reads fresh on current data. Without this arm, "the poll channel is CANNOT_MEASURE" is
    indistinguishable from "the poll channel can never read anything else"."""
    now = 1000.0
    declared = Stage0LagRecord(
        low_s=600.0,
        high_s=600.0,
        mean_s=600.0,
        spread_s=0.0,
        n=0,
        arc="none",
        citation="operator-supplied for this test; NOT a measurement of this system",
        channel=FeedChannel.POLL,
        provenance=LagProvenance.VENDOR_DECLARED,
    )
    ad, _, _ = await make_adapter(
        grant_map={3: 3},
        history=lambda s: [bar_row(now - 600.0)],
        poll_lag_record=declared,
    )
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    report = ad.freshness(now, SYM)[0]
    poll = report.channel(FeedChannel.POLL)
    assert poll is not None
    assert poll.state is ChannelState.FRESH
    assert report.fresh_channels == (FeedChannel.POLL,)
    # THE GRADE IS NEVER PROMOTED. A configured figure stays VENDOR_DECLARED however it is
    # used, and its detail says the measurement is owed and names the tap that would take it.
    assert poll.lag.provenance is LagProvenance.VENDOR_DECLARED
    assert "KNOWN-RED" in poll.lag.detail
    assert "tap_session_runbook.md" in poll.lag.detail


def test_the_poll_channel_has_no_lag_figure_on_this_system():
    """THE KNOWN-RED, asserted rather than only written down. `IB_POLL_LAG_RECORD` is `None`
    because no arc has measured the poll channel; a figure appearing here without the tap
    having run is what this assertion exists to catch."""
    assert IB_POLL_LAG_RECORD is None


@pytest.mark.asyncio
async def test_the_tick_channels_measured_figure_cannot_be_installed_on_the_poll_channel():
    """AMENDMENT 3, ENFORCED RATHER THAN REQUESTED. The tick channel's 600.0-601.9 s figure is
    measured, real, and one keyword away from the poll slot; installing it there would report
    the poll channel as measured when nothing has measured it. A plausible number is still a
    substitution."""
    with pytest.raises(
        ValueError, match="channel=tick and this slot is the poll channel"
    ):
        IBKRBrokerDatafeed(RecordingFeedSink(), poll_lag_record=IB_STAGE0_DELAYED_LAG)
    # And the mirror, so the guard is not one-directional.
    poll_record = Stage0LagRecord(
        low_s=1.0,
        high_s=1.0,
        mean_s=1.0,
        spread_s=0.0,
        n=0,
        arc="none",
        citation="test",
        channel=FeedChannel.POLL,
        provenance=LagProvenance.VENDOR_DECLARED,
    )
    with pytest.raises(
        ValueError, match="channel=poll and this slot is the tick channel"
    ):
        IBKRBrokerDatafeed(RecordingFeedSink(), lag_record=poll_record)


@pytest.mark.asyncio
async def test_the_report_carries_no_collapsed_verdict():
    """AMENDMENT 6's prohibition, proved BY ABSENCE (`debug.md` §7.6) rather than by a call
    site. The seam *"does not collapse them into a single boolean"*, so the report type must
    not carry one — a boolean here is the property every consumer would reach for first."""
    now = 1000.0
    ad, _, _ = await make_adapter(
        grant_map={3: 3}, history=lambda s: [bar_row(now - 1.0)]
    )
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    report = ad.freshness(now, SYM)[0]
    banned = {
        "is_fresh",
        "is_stale",
        "fresh",
        "stale",
        "state",
        "verdict",
        "feed_state",
    }
    present = {name for name in banned if hasattr(report, name)}
    assert not present, (
        f"FreshnessReport carries a collapsed verdict {sorted(present)} — AMENDMENT 6 puts "
        "that decision on the consumer, and a property here is the collapse the ruling forbids"
    )
    # The three tuples that replace it are all present and they partition the channels.
    partition = (
        report.fresh_channels + report.stale_channels + report.cannot_measure_channels
    )
    assert sorted(partition, key=lambda c: c.value) == sorted(
        report.observed_channels, key=lambda c: c.value
    )


@pytest.mark.asyncio
async def test_a_sealed_bar_the_sink_refused_is_owed_and_is_republished_not_rederived():
    """F13. A sink that raised left a bar SEALED and UNPUBLISHED, and every later poll dropped
    it as an identical re-poll: lost forever, with no revision, no error, and an attempt record
    saying `ok=True, rows=4`.

    THE REPAIR IS A PUBLICATION DEBT AND NOT A RE-DERIVATION. D1.14's seal-and-never-rewrite is
    intact: the retry re-publishes the SEALED OBJECT, with its original `seal_seq` and payload,
    so a bar cannot acquire a second identity and a revision arriving on the retry is still
    evaluated against the ORIGINAL seal."""

    class Refuses(RecordingFeedSink):
        limit: int = 2

        def on_bar(self, sealed):
            if len(self.bars) >= self.limit:
                raise RuntimeError("consumer refused the bar")
            super().on_bar(sealed)

    rows = [bar_row(100.0), bar_row(160.0), bar_row(220.0), bar_row(280.0)]
    sink = Refuses()
    fake = FakeIBFeed(grant_map={3: 3})
    ad = IBKRBrokerDatafeed(sink, ib=fake, history_source=lambda s: list(rows))
    fake.bind(ad)
    await ad.connect()
    await ad.subscribe(SYM)

    with pytest.raises(RuntimeError):
        await ad.poll_history(SYM)

    # NON-VACUITY: a side effect really landed before the failure.
    assert len(ad.sealed_bars()) == 3 and len(sink.bars) == 2

    # DEFECT 1 CLOSED: the loss is a VALUE, not an absence of evidence.
    owed = ad.unpublished_seals()
    assert [b.seal_key for b in owed] == [(SYM, 220.0, 60.0)]

    # DEFECT 2 CLOSED: the attempt cannot claim success over it.
    attempt = ad.poll_attempts()[-1]
    assert attempt.ok is False
    assert (
        attempt.venue_answered is True
    )  # the venue DID answer — two facts, two fields
    assert (attempt.rows, attempt.sealed, attempt.published, attempt.undelivered) == (
        4,
        3,
        2,
        1,
    )

    sink.limit = 99  # the consumer recovers
    assert await ad.poll_history(SYM) == 4

    # THE BAR IS RECOVERED, AND IT IS THE SAME OBJECT — re-published, never rebuilt.
    assert ad.unpublished_seals() == ()
    published = {b.seal_key for b in sink.bars}
    assert {b.seal_key for b in ad.sealed_bars()} == published
    recovered = next(b for b in sink.bars if b.seal_key == (SYM, 220.0, 60.0))
    assert recovered is owed[0]
    assert recovered.seal_seq == owed[0].seal_seq
    # And no duplicate crossed: four keys, four bars, one seal each.
    assert len(sink.bars) == len({b.seal_key for b in sink.bars}) == 4
    assert sink.bar_revisions == []
    assert ad.poll_attempts()[-1].ok is True


def test_a_poll_attempt_cannot_be_constructed_green_over_a_loss():
    """F13's second defect, STRUCTURAL. `ok=True` over an undelivered bar is unconstructible,
    so a later edit to the poll loop cannot reintroduce the green-over-a-lost-bar record by
    forgetting the rule (the construction `Bar.__post_init__` uses for AMENDMENT 4)."""
    with pytest.raises(ValueError, match="success reported over a lost bar"):
        PollAttempt(1, SYM, 0.0, ok=True, venue_answered=True, rows=4, undelivered=1)
    with pytest.raises(ValueError, match="success reported over a lost bar"):
        PollAttempt(1, SYM, 0.0, ok=True, venue_answered=False)


@pytest.mark.asyncio
async def test_polling_creates_no_subscription_state_and_no_wire_message():
    """F12. `poll_history` called `self._symbols.setdefault(...)`, manufacturing a subscription
    record for a symbol nobody subscribed — so the adapter-wide grant collapsed, and a later
    `unsubscribe` put a REAL `cancelMktData` on the wire for a subscription this library never
    made. Venue-side activity that is attributable to no intent of this library, on a clientId
    whose entire argument is that it must be."""
    other = "NQZ6"
    ad, _, fake = await make_adapter(
        grant_map={3: 3}, history=lambda s: [bar_row(100.0)]
    )
    await ad.subscribe(SYM)
    assert (
        ad.granted_mode() is MarketDataMode.DELAYED
    )  # non-vacuity: a real grant is held

    await ad.poll_history(other)

    # NO SUBSCRIPTION STATE. The poll is recorded, and it is recorded as a POLL.
    assert other not in ad._symbols
    assert ad.polled_symbols() == (other,)
    assert ad.last_poll_recv_ts(other) is not None
    # The adapter-wide grant is untouched: the poll did not widen the set it is pessimistic over.
    assert ad.granted_mode() is MarketDataMode.DELAYED
    assert ad.granted_mode(other) is MarketDataMode.UNKNOWN

    # NO WIRE MESSAGE. `unsubscribe` of a symbol that was only ever polled sends nothing.
    await ad.unsubscribe(other)
    assert fake.cancelled == []
    assert other not in fake.subscribed

    # AND THE CONTROL: a symbol that WAS subscribed still gets its cancel, so this is not
    # "unsubscribe no longer works".
    await ad.unsubscribe(SYM)
    assert fake.cancelled == [SYM]


@pytest.mark.asyncio
async def test_the_ibkr_not_reported_volume_sentinel_is_translated_at_the_boundary():
    """D1.39/D1.40. IBKR's `-1` is its not-reported sentinel and it is what justifies
    `Bar.volume`'s `| None` under AMENDMENT 3's ARC 022 refinement — but nothing translated it,
    so the raw sentinel crossed the seam as a number and a consumer doing arithmetic could read
    it as *one contract traded, short*. The field kept optional to prevent a fabricated volume
    was delivering one.

    THE GRADE IS UNCHANGED BY THE TRANSLATION and that is stated, not implied: the sentinel is
    IBKR-DOCUMENTED and has never been measured on this system. Translating it is not measuring
    it."""
    ad, sink, _ = await make_adapter(
        grant_map={3: 3},
        history=lambda s: [bar_row(100.0, v=IB_VOLUME_NOT_REPORTED)],
    )
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    assert sink.bars[0].volume is None

    # NOT A BLANKET RULE: only the ONE documented sentinel is translated. A value no document
    # assigns a meaning to does not acquire one here.
    ad2, sink2, _ = await make_adapter(
        grant_map={3: 3}, history=lambda s: [bar_row(200.0, v=-2.0)]
    )
    await ad2.subscribe(SYM)
    await ad2.poll_history(SYM)
    assert sink2.bars[0].volume == -2.0

    # AND A RE-POLL OF THE SENTINEL IS NOT A REVISION. The comparison goes through the same
    # boundary as the seal, so `-1` twice is one bar and no revision — not the no-op revision
    # flood `BarRevision.__post_init__` exists to prevent.
    await ad.poll_history(SYM)
    assert sink.bar_revisions == []
    assert len(sink.bars) == 1
