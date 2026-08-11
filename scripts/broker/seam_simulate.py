"""
seam_simulate.py — adversarial exercise of the seam prototype.

Three jobs:
  1. STRUCTURAL conformance — does the adapter have every verb?
  2. AWAIT conformance — is each verb on the side of the sync/async split the port
     declares? (ARC 015. callable() cannot tell an `async def` from a `def`, so (1)
     alone passes an adapter that hands the caller un-awaited coroutine objects.)
  3. BEHAVIOURAL conformance — does it actually DO anything?

HollowBrokerOrder is the control for (3). It passes (1) and (2) and MUST fail (3). If the
behavioural suite passes Hollow, the suite proves nothing — that's the non-vacuity check.

AwaitDivergentBrokerOrder is the control for (2): one deliberately-diverging verb, so the
await checker is demonstrably capable of failing and of NAMING the verb it failed on.

Run: python seam_simulate.py   (exit 0 == all green)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   missing-function-docstring
#       record()/expect_raises() are two-line driver helpers.
#   broad-exception-caught
#       expect_raises must report "raised something else" as a FAILED assertion
#       rather than let it propagate and abort the driver. See its comment.
#   import-outside-toplevel
#       ibkr_mapping is imported inside the section that exercises it, so the
#       seam sections above still run if the mapping skeleton is broken.
#   duplicate-code
#       The section banner comments are intentionally identical.
#   use-implicit-booleaness-not-comparison
#       `== []` / `!= []` is deliberate on every conformance-checker result, and
#       it is the same rule both suites apply. `not x` and `bool(x)` are also
#       satisfied by `None`, so a checker that started returning None instead of
#       a list would pass a truthiness assertion while having measured nothing.
#       The comparison asserts the TYPE and the emptiness together.
# pylint: disable=missing-function-docstring,broad-exception-caught
# pylint: disable=import-outside-toplevel,duplicate-code
# pylint: disable=use-implicit-booleaness-not-comparison
import asyncio
import sys

from broker_seam import (
    DATAFEED_ASYNC_VERBS,
    DATAFEED_EVENTS,
    DATAFEED_PORT_VERBS,
    ORDER_EVENTS,
    ORDER_PORT_VERBS,
    AckStatus,
    AwaitDivergentBrokerDatafeed,
    AwaitDivergentBrokerOrder,
    BrokerDatafeedPort,
    BrokerNotConnected,
    BrokerOrderPort,
    CoroutineDivergentBrokerDatafeed,
    HollowBrokerDatafeed,
    HollowBrokerOrder,
    NeutralOrder,
    OrderType,
    RecordingFeedSink,
    RecordingSink,
    Side,
    StubBrokerDatafeed,
    StubBrokerOrder,
    TimeInForce,
    check_await_conformance,
    check_structural_conformance,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))


def expect_raises(exc_type, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except exc_type:
        return True
    except Exception:  # noqa: BLE001 — the broad catch IS the assertion
        # "raised something else" must be reported as FAILURE, not propagate. Narrowing
        # this would let an unexpected exception escape and abort the whole driver at
        # the first surprise instead of recording which assertion was surprised.
        return False
    return False


async def expect_raises_async(exc_type, coro_fn, *a, **kw) -> bool:
    """`expect_raises` for a coroutine verb.

    Needed because the ARC 015 split makes four verbs coroutines: calling one without
    awaiting it raises NOTHING (it returns a coroutine object and emits a RuntimeWarning
    at GC), so the sync expect_raises would report FAIL — or, for a `not expect_raises`
    assertion, would report a false PASS. The await is what makes the assertion real.
    """
    try:
        await coro_fn(*a, **kw)
    except exc_type:
        return True
    except Exception:  # noqa: BLE001 — see expect_raises
        return False
    return False


async def _behaviour_order_path(adapter, s: RecordingSink) -> list[str]:
    """connect -> place -> ack -> status -> fills. Returns failed assertion names."""
    failed = []
    await adapter.connect()
    if not s.sessions:
        failed.append("connect emits on_session")

    order = NeutralOrder("c-100", "MES", Side.BUY, 2, OrderType.MARKET, TimeInForce.DAY)
    adapter.place_order(order)
    if not s.acks:
        failed.append("place_order emits on_ack")
    elif s.acks[-1][1] is not AckStatus.ACCEPTED:
        failed.append("ack is ACCEPTED")

    st = adapter.query_order_status("c-100")
    if st.state != "working":
        failed.append("status is working after place")

    # Fill assertions. NOTE: gating these on hasattr(simulate_fill) let Hollow SKIP
    # them entirely — a hole found by reading the control's failure list and noticing
    # the fill assertions were absent rather than failed. An adapter that cannot be
    # driven to a fill FAILS; it does not opt out.
    if not hasattr(adapter, "simulate_fill"):
        failed.append("adapter can be driven to a fill (no opt-out)")
        return failed

    adapter.simulate_fill("c-100", 1, 7785.0)
    if not s.fills:
        failed.append("fill emits on_fill")
    elif s.fills[-1][5] != 1:
        failed.append("cumulative_qty tracks partial")
    adapter.simulate_fill("c-100", 1, 7785.5)
    if not s.fills or s.fills[-1][5] != 2:
        failed.append("cumulative_qty reaches full")
    if not adapter.query_order_status("c-100").terminal:
        failed.append("status terminal after full fill")
    return failed


async def _behaviour_position_path(adapter) -> list[str]:
    """The position must exist, then flatten must actually clear it."""
    failed = []
    pos = await adapter.query_positions()
    if not pos:
        failed.append("position exists after fill")
    elif pos[0].net_qty != 2:
        failed.append("position net_qty correct")

    # NON-VACUITY PRECONDITION. "flatten clears position" is meaningless if there was
    # no position to clear — Hollow passed it by always returning []. Assert the
    # subject is in scope BEFORE asserting the behaviour, per the check doctrine.
    had_position = bool(await adapter.query_positions())
    adapter.flatten("MES")
    if not had_position:
        failed.append("flatten assertion is non-vacuous (a position existed to clear)")
    elif await adapter.query_positions():
        failed.append("flatten clears position")
    return failed


async def _behaviour_account_path(adapter) -> list[str]:
    """Balance and margin must return something real, not a zeroed placeholder."""
    failed = []
    bal = await adapter.query_balance()
    if bal.net_liquidation <= 0:
        failed.append("balance is non-trivial")
    if bal.venue_seq_ts <= 0:
        failed.append("balance carries venue_seq_ts")
    if await adapter.get_margin("MES") <= 0:
        failed.append("get_margin returns a real figure")
    return failed


async def behavioural_suite(adapter, s: RecordingSink) -> list[str]:
    """Returns list of failed assertion names. Empty == behaviourally conformant.

    Split into three paths in ARC 015 (order / position / account) so no single
    function carries the whole contract's branching. The order matters and is not
    incidental: the position path asserts against the state the order path created.
    """
    failed = await _behaviour_order_path(adapter, s)
    failed += await _behaviour_position_path(adapter)
    failed += await _behaviour_account_path(adapter)
    return failed


async def _section_structural() -> None:
    """Shape conformance. Stub and Hollow must BOTH pass — that is the point."""
    # -----------------------------------------------------------------------
    # 1. STRUCTURAL — both Stub and Hollow must pass. That's the point.
    # -----------------------------------------------------------------------
    sink = RecordingSink()
    stub = StubBrokerOrder(sink)
    hollow = HollowBrokerOrder(sink)
    feed_sink_missing = check_structural_conformance(sink, ORDER_EVENTS)

    record(
        "struct: Stub has all order verbs",
        not check_structural_conformance(stub, ORDER_PORT_VERBS),
    )
    record(
        "struct: Hollow has all order verbs (CONTROL — must pass)",
        not check_structural_conformance(hollow, ORDER_PORT_VERBS),
    )
    record("struct: RecordingSink implements all order events", not feed_sink_missing)
    record(
        "struct: StubDatafeed has all datafeed verbs",
        not check_structural_conformance(
            StubBrokerDatafeed(RecordingFeedSink()), DATAFEED_PORT_VERBS
        ),
    )

    # runtime_checkable Protocol only checks method presence, not signatures — assert we know that
    record("struct: Stub isinstance BrokerOrderPort", isinstance(stub, BrokerOrderPort))
    record(
        "struct: Hollow ALSO isinstance BrokerOrderPort (proves isinstance is shape-only)",
        isinstance(hollow, BrokerOrderPort),
    )


async def _section_await_conformance() -> None:
    """The ARC 015 split, plus the planted divergence that proves the gate can fail."""
    # Built locally rather than shared with _section_structural: the sections are
    # independent by design, and a conformance subject carried between them would make a
    # later assertion depend on state an earlier one happened to leave behind.
    stub = StubBrokerOrder(RecordingSink())
    hollow = HollowBrokerOrder(RecordingSink())
    # -----------------------------------------------------------------------
    # 1b. AWAIT CONFORMANCE (ARC 015) — the split must hold, and the checker
    #     must be capable of failing. A gate nobody has seen fail is not a gate.
    # -----------------------------------------------------------------------
    record(
        "await: Stub matches the port's sync/async split",
        not check_await_conformance(stub, BrokerOrderPort, ORDER_PORT_VERBS),
        str(check_await_conformance(stub, BrokerOrderPort, ORDER_PORT_VERBS)),
    )
    record(
        "await: Hollow matches the split too (control stays shape-conformant)",
        not check_await_conformance(hollow, BrokerOrderPort, ORDER_PORT_VERBS),
        str(check_await_conformance(hollow, BrokerOrderPort, ORDER_PORT_VERBS)),
    )

    # The planted divergence. Structurally identical to Hollow; exactly one verb on the
    # wrong side of the split.
    divergent = AwaitDivergentBrokerOrder(RecordingSink())
    record(
        "await: the planted divergence is STRUCTURALLY invisible (so struct alone is not enough)",
        not check_structural_conformance(divergent, ORDER_PORT_VERBS),
    )
    diverged = check_await_conformance(divergent, BrokerOrderPort, ORDER_PORT_VERBS)
    record(
        "NON-VACUITY: await checker FAILS on the planted divergence",
        len(diverged) == 1,
        str(diverged),
    )
    record(
        "NON-VACUITY: await checker NAMES the offending verb (query_positions)",
        len(diverged) == 1
        and diverged[0].startswith("query_positions:")
        and "port declares async" in diverged[0]
        and "adapter is sync" in diverged[0],
        str(diverged),
    )


async def _section_datafeed_await_conformance() -> None:
    """The ARC 022 D1.38 split on the DATAFEED port, and BOTH planted divergences.

    A SEPARATE SECTION from the order one because the two ports are disjoint
    (`nics_risk_subsystem_spec_v1.3.md` §2A:105-106 invariant 3) and a section that built
    subjects for both would make one port's result depend on the other's objects.

    TWO PLANTS, NOT ONE. The order port has demonstrated only the async-declared-implemented-sync
    direction since ARC 015. A gate shown able to fail in one direction has been shown able to
    fail in one direction — and the OTHER direction is the one `debug.md` §7.12 instance 4
    records. Both are driven here.
    """
    stub = StubBrokerDatafeed(RecordingFeedSink())
    hollow = HollowBrokerDatafeed(RecordingFeedSink())

    record(
        "await-feed: StubDatafeed matches the port's sync/async split",
        not check_await_conformance(stub, BrokerDatafeedPort, DATAFEED_PORT_VERBS),
        str(check_await_conformance(stub, BrokerDatafeedPort, DATAFEED_PORT_VERBS)),
    )
    record(
        "await-feed: HollowDatafeed matches the split too (control stays shape-conformant)",
        not check_await_conformance(hollow, BrokerDatafeedPort, DATAFEED_PORT_VERBS),
        str(check_await_conformance(hollow, BrokerDatafeedPort, DATAFEED_PORT_VERBS)),
    )
    record(
        # NON-VACUITY OF THE PARTITION ITSELF (`debug.md` §7.3). Every assertion below compares
        # two things that would agree trivially if the port declared nothing async or nothing
        # sync — the pre-ARC-022 world, in which this whole section would have been green over
        # a uniformly-sync port. Both halves must be non-empty or the split is not a split.
        "await-feed: NON-VACUITY — the declared split has BOTH a sync and an async half",
        bool(DATAFEED_ASYNC_VERBS)
        and bool(set(DATAFEED_PORT_VERBS) - DATAFEED_ASYNC_VERBS),
        f"async={sorted(DATAFEED_ASYNC_VERBS)} "
        f"sync={sorted(set(DATAFEED_PORT_VERBS) - DATAFEED_ASYNC_VERBS)}",
    )

    # PLANT 1 — an ASYNC-declared verb implemented SYNC.
    sync_plant = AwaitDivergentBrokerDatafeed(RecordingFeedSink())
    record(
        "await-feed: plant 1 is STRUCTURALLY invisible (so struct alone is not enough)",
        not check_structural_conformance(sync_plant, DATAFEED_PORT_VERBS),
    )
    d1 = check_await_conformance(sync_plant, BrokerDatafeedPort, DATAFEED_PORT_VERBS)
    record(
        "NON-VACUITY: await checker FAILS on an async verb implemented sync, and NAMES it",
        len(d1) == 1
        and d1[0].startswith("subscribe:")
        and "port declares async" in d1[0]
        and "adapter is sync" in d1[0],
        str(d1),
    )

    # PLANT 2 — a SYNC-declared verb implemented ASYNC. The direction ARC 015 never
    # instrumented, and the one that hands a caller an un-awaited coroutine object.
    async_plant = CoroutineDivergentBrokerDatafeed(RecordingFeedSink())
    record(
        "await-feed: plant 2 is STRUCTURALLY invisible too",
        not check_structural_conformance(async_plant, DATAFEED_PORT_VERBS),
    )
    d2 = check_await_conformance(async_plant, BrokerDatafeedPort, DATAFEED_PORT_VERBS)
    record(
        "NON-VACUITY: await checker FAILS on a sync verb implemented async, and NAMES it",
        len(d2) == 1
        and d2[0].startswith("feed_lag:")
        and "port declares sync" in d2[0]
        and "adapter is async" in d2[0],
        str(d2),
    )
    record(
        # The two plants must be caught for DIFFERENT reasons, or one instrument is standing
        # in for two and the second direction is unmeasured (`debug.md` §7.7 — verdict by
        # verdict, never in aggregate: "two failures" is the aggregate that hides a duplicate).
        "await-feed: the two plants are caught on DIFFERENT verbs and in OPPOSITE directions",
        len(d1) == 1 and len(d2) == 1 and d1[0].split(":")[0] != d2[0].split(":")[0],
        f"{d1} vs {d2}",
    )
    record(
        # CONDITION A of the standing question, driven rather than asserted in prose.
        "NON-VACUITY: an EMPTY roster is reported as vacuous, not passed",
        # `!= []` and not `bool(...)` on purpose (the same rule both suites apply): `bool` is
        # also False for `None`, so a checker that started returning None would satisfy a
        # truthiness assertion while having measured nothing. This compares the TYPE and the
        # emptiness together.
        check_await_conformance(stub, BrokerDatafeedPort, ()) != [],
        str(check_await_conformance(stub, BrokerDatafeedPort, ())),
    )


async def _section_type_validation() -> None:
    """Malformed neutral orders must never reach a venue."""
    # -----------------------------------------------------------------------
    # 2. NEUTRAL TYPE VALIDATION — malformed orders must not reach a venue
    # -----------------------------------------------------------------------
    record(
        "type: qty<=0 rejected",
        expect_raises(
            ValueError,
            NeutralOrder,
            "c1",
            "MES",
            Side.BUY,
            0,
            OrderType.MARKET,
            TimeInForce.DAY,
        ),
    )
    record(
        "type: limit without price rejected",
        expect_raises(
            ValueError,
            NeutralOrder,
            "c1",
            "MES",
            Side.BUY,
            1,
            OrderType.LIMIT,
            TimeInForce.DAY,
        ),
    )
    record(
        "type: market WITH price rejected",
        expect_raises(
            ValueError,
            NeutralOrder,
            "c1",
            "MES",
            Side.BUY,
            1,
            OrderType.MARKET,
            TimeInForce.DAY,
            7785.0,
        ),
    )
    record(
        "type: valid market order accepted",
        not expect_raises(
            Exception,
            NeutralOrder,
            "c1",
            "MES",
            Side.BUY,
            1,
            OrderType.MARKET,
            TimeInForce.DAY,
        ),
    )


async def _section_session_discipline() -> None:
    """Every verb refuses without a session; the async ones must be awaited to see it."""
    # -----------------------------------------------------------------------
    # 3. SESSION DISCIPLINE — every verb must refuse without a session
    # -----------------------------------------------------------------------
    cold = StubBrokerOrder(RecordingSink())
    o = NeutralOrder("c-cold", "MES", Side.BUY, 1, OrderType.MARKET, TimeInForce.DAY)
    record(
        "session: place_order refuses when down",
        expect_raises(BrokerNotConnected, cold.place_order, o),
    )
    record(
        "session: flatten refuses when down",
        expect_raises(BrokerNotConnected, cold.flatten),
    )
    record(
        "session: query_positions refuses when down",
        await expect_raises_async(BrokerNotConnected, cold.query_positions),
    )
    record(
        "session: get_margin refuses when down",
        await expect_raises_async(BrokerNotConnected, cold.get_margin, "MES"),
    )


async def _section_behavioural() -> None:
    """Stub must pass the behavioural suite; Hollow — the control — MUST fail it."""
    # -----------------------------------------------------------------------
    # 4. BEHAVIOURAL — Stub must pass, Hollow MUST FAIL

    s_stub = RecordingSink()
    stub2 = StubBrokerOrder(s_stub)
    stub_failures = await behavioural_suite(stub2, s_stub)
    record(
        "behaviour: Stub passes all behavioural assertions",
        not stub_failures,
        str(stub_failures),
    )

    s_hollow = RecordingSink()
    hollow2 = HollowBrokerOrder(s_hollow)
    hollow_failures = await behavioural_suite(hollow2, s_hollow)
    record(
        "NON-VACUITY: Hollow FAILS behavioural assertions (control)",
        len(hollow_failures) > 0,
        f"{len(hollow_failures)} failures: {hollow_failures}",
    )


async def _section_idempotency() -> None:
    """The (order_id, exec_id) key, per §4, replayed rather than inspected."""
    # -----------------------------------------------------------------------
    # 5. IDEMPOTENCY — the (order_id, exec_id) key, per §4
    # -----------------------------------------------------------------------
    s_idem = RecordingSink()
    idem = StubBrokerOrder(s_idem)
    await idem.connect()
    idem.place_order(
        NeutralOrder("c-idem", "MES", Side.BUY, 5, OrderType.MARKET, TimeInForce.DAY)
    )
    idem.simulate_fill("c-idem", 1, 7785.0)
    first_count = len(s_idem.fills)

    # ACTUALLY replay the duplicate rather than inspecting the set. The venue re-sending an
    # execution report is the real scenario §4 demands immunity to; checking that a key is
    # present proves the set works, not that the dedup does.
    idem._exec_seq -= 1  # force the next call to regenerate the SAME exec_id
    idem.simulate_fill("c-idem", 1, 7785.0)
    record(
        "idempotency: duplicate (order_id, exec_id) emits NO second event",
        len(s_idem.fills) == first_count,
        f"before={first_count} after={len(s_idem.fills)}",
    )

    # and a genuinely distinct exec must still get through — otherwise dedup is
    # just "drop everything"
    idem.simulate_fill("c-idem", 1, 7786.0)
    record(
        "idempotency: a DISTINCT exec still produces an event (dedup isn't a black hole)",
        len(s_idem.fills) == first_count + 1,
        f"expected={first_count + 1} got={len(s_idem.fills)}",
    )


async def _section_disjointness() -> None:
    """Invariant 3: the order and datafeed contracts share no object."""
    stub = StubBrokerOrder(RecordingSink())
    # -----------------------------------------------------------------------
    # 6. DISJOINTNESS — invariant 3: order and datafeed share no object
    # -----------------------------------------------------------------------
    order_attrs = set(ORDER_PORT_VERBS)
    feed_attrs = set(DATAFEED_PORT_VERBS)
    overlap = order_attrs & feed_attrs
    record(
        "disjoint: only connect/disconnect overlap between ports",
        overlap == {"connect", "disconnect"},
        f"overlap={sorted(overlap)}",
    )

    df = StubBrokerDatafeed(RecordingFeedSink())
    record(
        "disjoint: datafeed has NO order verbs",
        all(
            not hasattr(df, v)
            for v in ("place_order", "cancel_order", "flatten", "get_margin")
        ),
    )
    # DERIVED FROM THE ROSTERS, not typed (`debug.md` §7.4). This was the literal
    # `("subscribe", "unsubscribe", "feed_lag")` until ARC 022 — a hardcoded list that a later
    # change adds a verb to without the check ever noticing, which is the first row of that
    # table. D1.38 added `poll_history` and `granted_mode` to the datafeed roster and the
    # literal would have gone on asserting the same three.
    feed_only = sorted(set(DATAFEED_PORT_VERBS) - set(ORDER_PORT_VERBS))
    record(
        "disjoint: order adapter has NO feed verbs",
        bool(feed_only) and all(not hasattr(stub, v) for v in feed_only),
        f"feed-only verbs checked: {feed_only}",
    )
    record(
        "disjoint: datafeed event set is disjoint from the order event set",
        not (set(ORDER_EVENTS) & set(DATAFEED_EVENTS)),
    )


async def _section_ibkr_skeleton() -> None:
    """Mapping skeleton: GAPs refuse loudly, and it holds the same split."""
    # -----------------------------------------------------------------------
    # 7. IBKR MAPPING SKELETON — gaps must REFUSE, not silently degrade
    # -----------------------------------------------------------------------
    from broker_seam import BrokerUnsupported
    from ibkr_mapping import IBKRDatafeedAdapter, IBKROrderAdapter

    ib_order = IBKROrderAdapter(RecordingSink())
    # A FEED sink, not an ORDER sink. It was `RecordingSink()` until ARC 022, which is
    # `debug.md` §7.12's vacuity instance 7 verbatim — *an order sink passed into the datafeed
    # port* — surviving here for exactly the reason that instance survived: the only assertion
    # made against this object expects a refusal, so no feed event was ever driven through the
    # sink and its wrong type could not surface.
    ib_feed = IBKRDatafeedAdapter(RecordingFeedSink())

    record(
        "ibkr: struct conformance (all verbs present)",
        not check_structural_conformance(ib_order, ORDER_PORT_VERBS),
    )
    record(
        "ibkr: mapping skeleton matches the port's sync/async split",
        not check_await_conformance(ib_order, BrokerOrderPort, ORDER_PORT_VERBS),
        str(check_await_conformance(ib_order, BrokerOrderPort, ORDER_PORT_VERBS)),
    )
    record(
        "ibkr: flatten REFUSES loudly (GAP, not silent degrade)",
        expect_raises(BrokerUnsupported, ib_order.flatten, "MES"),
    )
    record(
        "ibkr: mapping skeleton matches the DATAFEED port's sync/async split",
        not check_await_conformance(ib_feed, BrokerDatafeedPort, DATAFEED_PORT_VERBS),
        str(check_await_conformance(ib_feed, BrokerDatafeedPort, DATAFEED_PORT_VERBS)),
    )
    record(
        # AWAITED (ARC 022). `subscribe` is a coroutine function under D1.38, and calling one
        # without awaiting raises NOTHING — it returns a coroutine object — so the sync
        # `expect_raises` would have reported FAIL here and, on a `not expect_raises`
        # assertion, a false PASS. This is the mirror image of the ARC 015 defect and the
        # reason `expect_raises_async` exists.
        "ibkr: datafeed subscribe REFUSES loudly (GAP)",
        await expect_raises_async(BrokerUnsupported, ib_feed.subscribe, "MES"),
    )
    record(
        "ibkr: datafeed poll_history raises NotImplementedError carrying the mapping",
        await expect_raises_async(NotImplementedError, ib_feed.poll_history, "MES"),
    )
    record(
        "ibkr: clientId=0 rejected at construction",
        expect_raises(ValueError, IBKROrderAdapter, RecordingSink(), client_id=0),
    )
    record(
        "ibkr: mappable verbs raise NotImplementedError carrying the mapping",
        await expect_raises_async(NotImplementedError, ib_order.query_positions),
    )


def _report() -> int:
    """Print the result table and the mapping summary. Returns the exit code."""
    # -----------------------------------------------------------------------
    # REPORT
    # -----------------------------------------------------------------------
    print("=" * 92)
    print("SEAM PROTOTYPE — ADVERSARIAL SIMULATION")
    print("=" * 92)
    for name, status, detail in results:
        mark = "OK " if status == PASS else "XX "
        print(f"  {mark}{name}")
        if detail and status == FAIL or detail and "NON-VACUITY" in name:
            print(f"       -> {detail}")

    failed = [r for r in results if r[1] == FAIL]
    print("-" * 92)
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    print()
    print("=" * 92)
    print("IBKR MAPPING")
    print("=" * 92)
    from ibkr_mapping import summarise

    summarise()
    return 1 if failed else 0


async def main() -> int:
    """Drive every section in order, then report.

    Split out of one long linear driver in ARC 015. Each section builds its own
    adapters and sinks, so they are independent and a failure names its section.
    """
    await _section_structural()
    await _section_await_conformance()
    await _section_datafeed_await_conformance()
    await _section_type_validation()
    await _section_session_discipline()
    await _section_behavioural()
    await _section_idempotency()
    await _section_disjointness()
    await _section_ibkr_skeleton()
    return _report()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
