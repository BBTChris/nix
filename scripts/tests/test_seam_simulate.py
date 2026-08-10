"""test_seam_simulate.py — pytest entry point for the seam simulation (ARC 016 §2a, D1.15).

`scripts/broker/seam_simulate.py` holds 33 assertions and BOTH of the seam's non-vacuity
controls, and until this file existed it was only ever run by hand. **A control that only
runs when someone remembers to run it is not a control** — pre-commit lint-checked
seam_simulate.py on every commit and never once executed it, so a regression that broke
either control would have been invisible at the gate while the gate stayed green. That is
the same failure class the controls themselves exist to catch, one layer up.

WHY THIS FILE RATHER THAN A `test_` FUNCTION INSIDE seam_simulate.py. `test_broker_order.py`
could take its pytest entry point in-place because it already lives under `scripts/tests/`,
which is what `testpaths` points at. seam_simulate.py lives in `scripts/broker/`, so a
`test_*` function added there would never be collected — it would look converted and run
never, which is strictly worse than the honest status quo. The driver stays where it is
(and stays runnable as `python seam_simulate.py`); the collectable entry point lives here.

WHAT IS ASSERTED, AND WHY IT IS NOT JUST "THE SUITE IS GREEN". A green seam_simulate run
already implies the controls behaved, because the driver records their misbehaviour as its
own PASS/FAIL rows. But that is inference from an aggregate, and §7.7 of the debug doctrine
is explicit that aggregates hide exactly this. So the two controls are ALSO driven directly
here, against the same helpers the driver uses, and asserted verdict-by-verdict:

  test_hollow_control_still_fails_behaviourally   HollowBrokerOrder must FAIL
  test_await_divergent_control_still_caught       AwaitDivergentBrokerOrder must be NAMED

If either control silently started passing, the whole-suite test would still go green (the
driver would simply record a FAIL row that... no longer fails), and only these two would
redden. That is the point of writing them separately.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   import-error
#       pytest and the broker package resolve via pyproject's pythonpath
#       (["scripts", "scripts/broker"]) and the matching pylint init-hook.
#       pylint's static resolution cannot see a runtime sys.path entry.
# pylint: disable=import-error
import pytest
from broker_seam import (
    ORDER_PORT_VERBS,
    AwaitDivergentBrokerOrder,
    BrokerOrderPort,
    HollowBrokerOrder,
    RecordingSink,
    StubBrokerOrder,
    check_await_conformance,
    check_structural_conformance,
)
from seam_simulate import behavioural_suite, main, results


@pytest.mark.asyncio
async def test_seam_simulation_suite() -> None:
    """The whole driver, carried by the project suite (D1.15).

    `results` is a module global that accumulates, so it is cleared first — a second
    invocation appending to the first one's rows would make the count assertion below pass
    for the wrong reason, which is failure mode #7 (non-repeatable harness) in the doctrine
    catalogue.

    main() returns an exit code rather than raising, so the code is asserted AND the failed
    rows are named — a bare `assert rc == 0` would report that something failed without
    reporting what.
    """
    results.clear()
    rc = await main()
    failed = [(name, detail) for name, status, detail in results if status == "FAIL"]
    assert not failed, "seam assertions failed:\n" + "\n".join(
        f"  {n} -> {d}" for n, d in failed
    )
    assert rc == 0, f"seam_simulate returned {rc}"
    # Non-vacuity: the suite must have actually run its assertions, not collapsed to a
    # handful. Anchored to a floor, not to the exact count, so adding an assertion does not
    # break it while deleting most of them does (§7.4 — never anchor to something that moves).
    assert len(results) > 25, (
        f"suite collapsed to {len(results)} assertions — non-vacuity"
    )


@pytest.mark.asyncio
async def test_hollow_control_still_fails_behaviourally() -> None:
    """CONTROL 1 — HollowBrokerOrder. Structurally conformant, behaviourally empty.

    It must PASS structural conformance (that is what makes it a control rather than a
    broken class) and FAIL the behavioural suite. If it ever passes the behavioural suite,
    the suite has stopped measuring behaviour and is only measuring shape.
    """
    # ONE sink, shared between the adapter and the suite that observes it. Written as two
    # separate RecordingSink() instances first, and the can-fail demonstration caught it:
    # with the adapter emitting into sink A while the assertions read sink B, the suite
    # reports failures for a WORKING adapter too, because it is observing a sink nothing
    # ever wrote to. That control could not tell "hollow" from "behaving" — it would have
    # stayed green through the exact regression it exists to catch. See
    # test_stub_still_passes_behaviourally, which is what makes the difference detectable.
    sink = RecordingSink()
    hollow = HollowBrokerOrder(sink)

    # Non-vacuity first (§7.3): the control is only meaningful if it is genuinely
    # indistinguishable from a real adapter by shape.
    assert not check_structural_conformance(hollow, ORDER_PORT_VERBS), (
        "Hollow is no longer structurally conformant — it has stopped being a control"
    )
    assert not check_await_conformance(hollow, BrokerOrderPort, ORDER_PORT_VERBS), (
        "Hollow diverges on the sync/async split — it would now fail for a shape reason, "
        "not a behavioural one, and a control that fails for the wrong reason measures nothing"
    )

    failures = await behavioural_suite(hollow, sink)
    assert failures, (
        "HollowBrokerOrder PASSED the behavioural suite — the suite proves nothing"
    )


@pytest.mark.asyncio
async def test_stub_still_passes_behaviourally() -> None:
    """The other half of the control pair. A behavioural suite that everything fails is as
    useless as one that everything passes: without this, `test_hollow_...` above could be
    satisfied by a suite that is simply broken."""
    sink = RecordingSink()
    failures = await behavioural_suite(StubBrokerOrder(sink), sink)
    assert not failures, f"the working Stub failed behavioural assertions: {failures}"


def test_await_divergent_control_still_caught() -> None:
    """CONTROL 2 — AwaitDivergentBrokerOrder, the permanently-kept plant for
    check_await_conformance (D3.3).

    Asserted verdict-by-verdict rather than by count: the checker must report EXACTLY one
    divergence, and it must NAME `query_positions` and both sides of the disagreement. A
    `len(...) == 1` alone would pass if the checker started reporting a different verb.
    """
    divergent = AwaitDivergentBrokerOrder(RecordingSink())

    # Non-vacuity: the divergence must be invisible to structural conformance, or it is not
    # testing the thing check_await_conformance was built for.
    assert not check_structural_conformance(divergent, ORDER_PORT_VERBS), (
        "the planted divergence became structurally visible — check_structural_conformance "
        "would now catch it and this control no longer isolates the await checker"
    )

    diverged = check_await_conformance(divergent, BrokerOrderPort, ORDER_PORT_VERBS)
    assert len(diverged) == 1, f"expected exactly one divergence, got {diverged}"
    assert diverged[0].startswith("query_positions:"), diverged[0]
    assert "port declares async" in diverged[0], diverged[0]
    assert "adapter is sync" in diverged[0], diverged[0]
