"""ARC 027 C1/C2 — the standing gate over the kill-datafeed-under-load drill.

Two kinds of test, and the split is deliberate:

* **One end-to-end run of the SHIPPED gate against a REAL drill** — real child
  processes, a real SIGKILL, real shared memory, a real ZeroMQ bus. It is the
  slowest test in this file by an order of magnitude and it is the only one that
  proves the gate's method executes at all. A suite of arm tests over crafted
  inputs would be `docs/CHECK-DEBT.md` D3.16 exactly: a gate reporting PASS over
  a method nothing ever ran.
* **Per-arm can-fails over a crafted drill result.** Each starts from a result
  the gate accepts and breaks ONE thing, so a red is attributable to that arm and
  not to the fixture. The gate's `_drive` is monkeypatched: the PLANT here is the
  drill's evidence record, and no production artifact is touched (doctrine C.8).

**Every control asserts the REASON** — the named condition, in the verdict's own
detail — never the exit code alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access,duplicate-code
# pylint: disable=use-implicit-booleaness-not-comparison
# `errors == ()` asserts the TYPE and the emptiness together, the same
# convention `scripts/tests/test_declarations.py` adopts: `not x` is also
# satisfied by `None`, so a reader that started returning None would pass a
# truthiness assertion while having measured nothing.
# `protected-access`: the can-fails drive the gate's ARMS, which are private by
# design; a public arm would be a surface invented for the test.

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_feed_kill_drill as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_feed_kill_drill.py"

FAILING = (Status.FAIL_NEEDS_OPERATOR, Status.FAIL_REPAIRABLE)


def _ctx() -> Context:
    return Context(nix_home=REPO, mode=Mode.VERIFY)


def _trial(index: int, offset: float, tick: float, poll: float) -> dict[str, Any]:
    """One trial record in the shape the drill actually emits."""
    return {
        "trial": index,
        "pid": 40000 + index,
        "signal": "SIGKILL",
        "signal_number": 9,
        "reap_status": -9,
        "kill_offset_s": offset,
        "observed_tick_rate_hz": 2_500_000.0,
        "drained_tick_rate_hz": 20_000.0,
        "detect_latency_s": {"tick": tick, "poll": poll},
        "detect_since_start_s": {"tick": offset + tick, "poll": offset + poll},
        "transitions": [],
    }


def _passing() -> dict[str, Any]:
    """A drill result the gate accepts. Every can-fail below breaks ONE field."""
    trials = [
        _trial(0, 0.40, 0.190, 0.890),
        _trial(1, 0.80, 0.191, 0.892),
        _trial(2, 1.20, 0.189, 0.888),
    ]
    return {
        "observer_resolution_ms": 5,
        "attribution_ratio": 3.0,
        "thresholds_s": {"tick": 0.2, "poll": 0.9},
        "trials": trials,
        "attribution": {
            channel: {
                "channel": channel,
                "refusal": "",
                "n": 3,
                "kill_offset_stdev_s": 0.4,
                "detect_latency_mean_s": 0.19,
                "detect_latency_stdev_s": 0.001,
                "detect_since_start_stdev_s": 0.4,
                "ratio": 400.0,
                "attributed": True,
            }
            for channel in ("tick", "poll")
        },
        "control": {
            "observed_tick_rate_hz": 2_400_000.0,
            "held_s": 3.2,
            "transitions": [],
        },
        "starve": {
            "starved_channel": "poll",
            "held_s": 1.5,
            "transitions": [
                {"channel": "poll", "from": "fresh", "to": "stale"},
            ],
        },
    }


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch):
    """Return a function that installs a crafted drill result and runs the gate."""

    def _run(mutate) -> Any:
        result = _passing()
        mutate(result)
        monkeypatch.setattr(gate, "_drive", lambda drill: copy.deepcopy(result))
        return gate.run(Mode.VERIFY, _ctx())

    return _run


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the crafted result the can-fails start from must PASS
# --------------------------------------------------------------------------


def test_the_unbroken_drill_result_passes(planted) -> None:
    """Without this, every red below could be the fixture rather than the arm."""
    result = planted(lambda _: None)
    assert result.status is Status.PASS, result.detail
    assert "LOAD MEASURED" in result.evidence
    assert "ATTRIBUTION tick" in result.evidence


# --------------------------------------------------------------------------
# THE REAL THING — the shipped gate, a real kill, a real ring, a real bus
# --------------------------------------------------------------------------


def test_the_shipped_gate_drives_a_REAL_kill_and_reports_rate_pid_and_signal() -> None:
    """The one test that proves the method runs. Slow on purpose.

    A gate whose arms are only ever exercised over crafted dictionaries is a gate
    whose method has never been executed — `docs/CHECK-DEBT.md` D3.16. This drives
    `run()` with nothing patched.
    """
    if not (REPO / ".venv" / "bin" / "python3").is_file():
        pytest.skip("no venv interpreter")
    result = gate.run(Mode.VERIFY, _ctx())
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"the drill could not run here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    assert "ticks/s" in result.evidence, "no measured rate in the evidence"
    assert "SIGKILL reaped=-9" in result.evidence, "no reaped wait status"
    assert "NON-VACUITY" not in result.evidence  # that word belongs to another gate
    assert "INDEPENDENCE" in result.evidence, "no per-channel independence arm ran"


# --------------------------------------------------------------------------
# PER-ARM CAN-FAILS — each breaks ONE property and must name it
# --------------------------------------------------------------------------


def test_a_feed_that_was_never_under_load_FAILS_arm_1(planted) -> None:
    """§0a defect 1: a drill over an idle producer proves nothing stopped."""
    result = planted(
        lambda r: r["trials"][1].__setitem__("observed_tick_rate_hz", 12.0)
    )
    assert result.status in FAILING, result.detail
    assert "below the" in result.detail and "Hz floor" in result.detail
    assert "price_ring" in result.site


def test_a_process_that_did_not_die_of_the_signal_FAILS_arm_2(planted) -> None:
    """§0a defect 2: the KERNEL's wait status is the evidence, not the intent."""
    result = planted(lambda r: r["trials"][2].__setitem__("reap_status", 0))
    assert result.status in FAILING, result.detail
    assert "reaped with status 0, not -9" in result.detail
    assert "pid=40002" in result.detail


def test_channels_that_go_stale_together_FAIL_arm_3(planted) -> None:
    """AMENDMENT 6: simultaneous channels are what one collapsed timer produces."""
    result = planted(
        lambda r: r["trials"][0]["detect_latency_s"].__setitem__("poll", 0.195)
    )
    assert result.status in FAILING, result.detail
    assert "compatible with one collapsed timer" in result.detail
    assert "FeedStalenessMonitor" in result.site


def test_only_one_channel_transitioning_under_the_kill_FAILS_arm_3(planted) -> None:
    """A per-channel report in which a channel never moved is not per-channel."""
    result = planted(lambda r: r["trials"][1]["detect_latency_s"].pop("poll"))
    assert result.status in FAILING, result.detail
    assert "AMENDMENT 6 requires" in result.detail


def test_detection_that_tracks_the_WALL_CLOCK_FAILS_arm_4(planted) -> None:
    """§0a defect 3, the trap this item exists to catch: a timer-driven detector.

    The numbers here are what a timer produces: `detect - start` is tight (it is
    the timer's period) and `detect - kill` inherits the kill jitter. The gate must
    read that ordering as UNATTRIBUTED.
    """

    def _timer(result: dict[str, Any]) -> None:
        for channel in ("tick", "poll"):
            stats = result["attribution"][channel]
            stats.update(
                detect_latency_stdev_s=0.40,
                detect_since_start_stdev_s=0.002,
                ratio=0.005,
                attributed=False,
            )

    result = planted(_timer)
    assert result.status in FAILING, result.detail
    assert "detection is not" in result.detail and "tracking the death" in result.detail
    assert "attribution" in result.site


def test_kill_offsets_that_never_varied_are_CANNOT_MEASURE_not_a_pass(
    planted,
) -> None:
    """With no spread the two hypotheses predict identical numbers.

    CANNOT_MEASURE, deliberately not FAIL: an instrument with no power has said
    nothing about its subject either way (`nix_check_contract.md` §17). It is
    also not a PASS, which is the half that matters.
    """

    def _no_jitter(result: dict[str, Any]) -> None:
        result["attribution"]["tick"] = {
            "channel": "tick",
            "refusal": "kill offsets varied by only 0.0001s (floor 0.08s) — with no "
            "spread a kill-driven detector and a timer-driven one predict the SAME "
            "numbers, so this run could not have told them apart",
        }

    result = planted(_no_jitter)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "could not have told them apart" in result.detail
    assert "attribution" in result.detail


def test_stratified_kill_offsets_ALWAYS_clear_the_jitter_floor() -> None:
    """The refusal above must be unreachable by chance, or the gate is a coin toss.

    MEASURED, and this test exists because it happened: three i.i.d. draws from
    the 0.9 s window produced `kill offsets varied by only 0.0262s` on a real run
    of the shipped gate. Stratification puts a floor under the spread; 300 draws
    of the real sampler are required to clear `MIN_JITTER_S` every time.
    """
    import statistics

    import feed_kill_drill as drill

    worst = min(
        statistics.stdev(drill.stratified_offsets(gate.TRIALS)) for _ in range(300)
    )
    assert worst > drill.MIN_JITTER_S, (
        f"the tightest of 300 stratified draws had stdev {worst:.4f}s, at or below "
        f"the {drill.MIN_JITTER_S}s floor — the gate would refuse itself at random"
    )
    for offset in drill.stratified_offsets(gate.TRIALS):
        assert drill.KILL_MIN_S <= offset <= drill.KILL_MAX_S


def test_a_detector_that_fires_without_a_kill_FAILS_arm_5(planted) -> None:
    """The CONTROL arm. A detector that fires unprompted makes every red useless."""
    result = planted(
        lambda r: r["control"]["transitions"].append(
            {"channel": "tick", "from": "fresh", "to": "stale"}
        )
    )
    assert result.status in FAILING, result.detail
    assert "never killed and still produced" in result.detail
    assert "_hold" in result.site


def test_a_silent_control_over_an_idle_producer_FAILS_arm_5(planted) -> None:
    """A quiet detector over a producer that was not producing proves nothing."""
    result = planted(lambda r: r["control"].__setitem__("observed_tick_rate_hz", 3.0))
    assert result.status in FAILING, result.detail
    assert "control arm observed" in result.detail


def test_starving_one_channel_that_moves_BOTH_FAILS_arm_6(planted) -> None:
    """The independence proof: one starved clock may move exactly one channel."""
    result = planted(
        lambda r: r["starve"]["transitions"].append(
            {"channel": "tick", "from": "fresh", "to": "stale"}
        )
    )
    assert result.status in FAILING, result.detail
    assert "report independently" in result.detail
    assert "_hold" in result.site


def test_a_short_run_is_CANNOT_MEASURE_not_a_weaker_pass(planted) -> None:
    """Fewer trials than claimed is a WRONG statistic, not a softer one."""
    result = planted(lambda r: r["trials"].pop())
    assert result.status is Status.CANNOT_MEASURE
    assert "trial(s) completed" in result.detail


# --------------------------------------------------------------------------
# DECLARATIONS
# --------------------------------------------------------------------------


def test_the_gate_declares_what_the_plan_needs() -> None:
    """Every claim this gate makes is one the drill demonstrably makes."""
    declaration = read_declaration(GATE_FILE)
    assert declaration.errors == ()
    assert declaration.depends_on == ("check_venv",)
    assert set(declaration.resources) == {
        "subprocess:python3",
        "subprocess:python",
        "file-write:/tmp",
        "zmq-ipc",
        "shm",
        "cpu-affinity",
    }
    assert declaration.on_fail == "continue"
    assert "scripts/feed_kill_drill.py" in declaration.subjects
