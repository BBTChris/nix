"""`check_plane1_hot_path` + `plane1_hotpath_drill` — the §11 item 6 can-fail.

ARC 035 / Stage 1 / sub-agent A (A3). The arc brief's §0a:

> *an idle-system latency test proves NOTHING about hot-path isolation.*

Two halves, and they measure different things:

* the DRILL is driven for real once, and its own CONTROL is checked — the
  synchronous arm must actually be inflated by the delay it was given, or the
  instrument cannot see blocking and no green from it means anything;
* the GATE's `judge()` is driven over DOCTORED measurements, because
  manufacturing a genuinely blocking hot path on a real machine for each hazard
  would be slow, flaky, and would test the plant rather than the judgement.

Both halves carry an unmutated control.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
CHECKS = REPO / "checks"
for _path in (str(SCRIPTS), str(CHECKS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position
import check_plane1_hot_path as gate  # pylint: disable=import-error
import plane1_hotpath_drill as drill  # pylint: disable=import-error


def _measurement(**over: object) -> dict:
    """A synthetic drill result in the shape the drill really produces.

    The numbers are the RELATION the gate judges: a 5 ms delay, a gate that
    costs tens of microseconds concurrently, and a control that costs the whole
    delay when the sink is inline.
    """
    result: dict[str, object] = {
        "delay_s": 0.005,
        "baseline": {"n": 2000, "p50_us": 20.0, "p99_us": 40.0, "max_us": 90.0},
        "concurrent": {
            "n": 2000,
            "p50_us": 22.0,
            "p99_us": 60.0,
            "max_us": 300.0,
            "commits_during_hot_loop": 9,
            "rows_committed": 72,
        },
        "synchronous_control": {
            "n": 300,
            "p50_us": 5200.0,
            "p99_us": 5600.0,
            "max_us": 7000.0,
            "commits_during_hot_loop": 300,
            "rows_committed": 300,
        },
        "postgres": {
            "arm": "postgres",
            "available": True,
            "n": 2000,
            "p50_us": 21.0,
            "p99_us": 55.0,
            "max_us": 400.0,
            "groups_during_hot_loop": 6,
            "rows_landed": 300,
        },
    }
    for key, value in over.items():
        current = result.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            result[key] = {**current, **value}
        else:
            result[key] = value
    return result


# ------------------------------------------------------------- THE CONTROL


def test_control_a_well_separated_measurement_PASSES() -> None:
    """Without this, every red below could be the synthetic shape itself."""
    unmeasurable, defects, evidence = gate.judge(_measurement())
    assert not unmeasurable, unmeasurable
    assert not defects, defects
    assert any("instrument DOES see blocking" in line for line in evidence), evidence


# -------------------------------------------------- THE §7.12 HAZARDS, driven


def test_a_CONTROL_that_does_not_inflate_is_CANNOT_MEASURE_not_a_PASS() -> None:
    """The hazard the whole design turns on.

    If a deliberately slow sink placed DIRECTLY on the hot path does not move
    the number, the timing is not measuring the hot path — so the concurrent
    arm's small figure is about a timer, not about §11 item 6. That must never be a
    green.
    """
    doctored = _measurement(synchronous_control={"p99_us": 45.0})
    unmeasurable, _defects, _evidence = gate.judge(doctored)
    assert any("THE CONTROL FAILED" in u for u in unmeasurable), unmeasurable
    assert any("cannot discriminate" in u for u in unmeasurable), unmeasurable


def test_NO_OVERLAP_is_CANNOT_MEASURE_not_a_PASS() -> None:
    """The §0a itself: a hot loop that finished before any commit landed.

    "The gate did not block" is then trivially true and measures an idle system.
    """
    doctored = _measurement(concurrent={"commits_during_hot_loop": 0})
    unmeasurable, _defects, _evidence = gate.judge(doctored)
    assert any("never actually concurrent" in u for u in unmeasurable), unmeasurable


def test_a_GATE_THAT_BLOCKS_reddens_the_check() -> None:
    """The property itself: the concurrent arm pays a share of the commit."""
    doctored = _measurement(concurrent={"p99_us": 4800.0})
    unmeasurable, defects, _evidence = gate.judge(doctored)
    assert not unmeasurable, unmeasurable
    assert any("§11 item 6" in d and "above" in d for d in defects), defects


def test_a_gate_that_merely_DEGRADES_against_baseline_reddens_the_check() -> None:
    """Below the absolute ceiling and still visibly worse than doing nothing.

    This is the arm that catches a partial dependency — a lock held a little too
    long — which the absolute ceiling alone would wave through.
    """
    doctored = _measurement(concurrent={"p99_us": 460.0})
    unmeasurable, defects, _evidence = gate.judge(doctored)
    assert not unmeasurable, unmeasurable
    assert any("rose from" in d for d in defects), defects


def test_a_POSTGRES_ARM_that_never_committed_reddens_the_check() -> None:
    """An arm present in the output that measured nothing about the real sink."""
    doctored = _measurement(postgres={"groups_during_hot_loop": 0, "rows_landed": 0})
    _unmeasurable, defects, _evidence = gate.judge(doctored)
    assert any("never committed" in d for d in defects), defects


def test_an_UNAVAILABLE_postgres_arm_is_NAMED_not_silently_dropped() -> None:
    """§17: a skipped arm the reader cannot see is a skipped arm nobody counts."""
    doctored = _measurement(
        postgres={"available": False, "error": "planted: no cluster here"}
    )
    unmeasurable, defects, evidence = gate.judge(doctored)
    assert not unmeasurable and not defects
    assert any("SKIPPED and NAMED" in line for line in evidence), evidence
    assert any("planted: no cluster here" in line for line in evidence), evidence


def test_the_judgement_does_not_MUTATE_its_input() -> None:
    """A judge that edited the measurement could not be re-run over it."""
    measurement = _measurement()
    before = copy.deepcopy(measurement)
    gate.judge(measurement)
    assert measurement == before


# ------------------------------------------------ THE DRILL, driven for real


def test_the_REAL_drill_shows_the_gate_is_off_the_commit_path(tmp_path) -> None:
    """One real run of the shipped drill, judged by the shipped gate.

    Reduced iteration counts so the suite stays usable; the RELATION is the
    claim and it does not depend on n. The control arm is asserted FIRST — if
    the inline slow sink is not visible in the timing here, this box cannot
    measure the property, and the test says so rather than passing.
    """
    delay_us = drill.DEFAULT_DELAY_S * 1_000_000.0
    result = drill.run_drill(
        tmp_path,
        iterations=400,
        control_iterations=40,
        delay_s=drill.DEFAULT_DELAY_S,
    )
    control = result["synchronous_control"]
    concurrent = result["concurrent"]
    baseline = result["baseline"]
    assert control["p99_us"] > 0.5 * delay_us, (
        f"the INLINE slow sink did not show up in the timing "
        f"(p99 {control['p99_us']:.1f}us against a {delay_us:.0f}us delay) — "
        f"this box cannot discriminate, so nothing below would mean anything"
    )
    assert concurrent["commits_during_hot_loop"] >= gate.MIN_OVERLAP_COMMITS, (
        f"only {concurrent['commits_during_hot_loop']} commit(s) overlapped the "
        f"hot loop"
    )
    assert concurrent["p99_us"] < gate.CONCURRENT_CEILING * delay_us, concurrent
    assert concurrent["p99_us"] < gate.CONCURRENT_VS_BASELINE_MAX * max(
        baseline["p99_us"], 1e-6
    ), (baseline, concurrent)
    unmeasurable, defects, _evidence = gate.judge(result)
    assert not unmeasurable, unmeasurable
    assert not defects, defects


def test_the_SLOW_SINK_really_sleeps() -> None:
    """The floor under hazard 3: a zero delay would satisfy everything vacuously."""
    import time  # pylint: disable=import-outside-toplevel

    sink = drill.SlowSink(0.02)
    start = time.perf_counter()
    sink.commit([drill._row(0)])  # pylint: disable=protected-access
    assert time.perf_counter() - start >= 0.02
    assert sink.commits == 1
