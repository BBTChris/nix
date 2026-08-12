"""ARC 027 C1-C3 — the drill's own logic, tested without spawning anything.

The expensive end-to-end runs live in the two gate tests. This file drives the
pieces the gates' verdicts rest on: the attribution statistic (which is the whole
answer to *"detection merely FOLLOWED the kill"*), the per-channel report, and
the Plane-2 bookkeeping.

The attribution tests are the interesting ones: they feed the function the
numbers each of the two competing hypotheses would actually produce, and require
it to separate them. A test that only fed it the good case would have shown that
the statistic can say yes.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access,duplicate-code

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "scripts" / "broker"))

import feed_kill_drill as drill  # pylint: disable=wrong-import-position
from broker_seam import (  # pylint: disable=wrong-import-position
    ChannelState,
    FeedChannel,
)


def _trials(pairs: list[tuple[float, float]], channel: str = "tick") -> list[dict]:
    """`[(kill_offset, detect_latency)]` -> the trial records `attribution` reads."""
    return [
        {
            "kill_offset_s": offset,
            "detect_latency_s": {channel: latency},
            "detect_since_start_s": {channel: offset + latency},
        }
        for offset, latency in pairs
    ]


# --------------------------------------------------------------------------
# ATTRIBUTION — the two hypotheses, and the statistic that separates them
# --------------------------------------------------------------------------


def test_a_kill_driven_detector_is_ATTRIBUTED() -> None:
    """Tight `detect - kill`, wide `detect - start`. What a real detector does."""
    stats = drill.attribution(
        _trials([(0.40, 0.190), (0.80, 0.191), (1.20, 0.189), (0.60, 0.192)]), "tick"
    )
    assert stats["refusal"] == ""
    assert stats["attributed"] is True
    assert stats["detect_since_start_stdev_s"] > stats["detect_latency_stdev_s"]


def test_a_TIMER_driven_detector_is_NOT_attributed() -> None:
    """The defect this whole item exists to catch, expressed as its own numbers.

    A detector that fires 1.5 s after the producer STARTED, regardless of when the
    kill happened, produces a tight `detect - start` and a `detect - kill` that
    inherits the entire kill jitter. The statistic must read that as unattributed
    even though every trial "detected after the kill".
    """
    stats = drill.attribution(
        _trials([(0.40, 1.10), (0.80, 0.70), (1.20, 0.30), (0.60, 0.90)]), "tick"
    )
    assert stats["refusal"] == ""
    assert stats["attributed"] is False, (
        "a detector firing at a fixed offset from START was attributed to the KILL: "
        f"{stats}"
    )
    assert stats["ratio"] < 1.0


def test_kill_offsets_that_never_varied_are_a_REFUSAL() -> None:
    """With no spread, both hypotheses predict identical numbers. Not a pass."""
    stats = drill.attribution(
        _trials([(0.50, 0.19), (0.50, 0.19), (0.50, 0.19)]), "tick"
    )
    assert stats["refusal"], stats
    assert "could not have told them apart" in stats["refusal"]
    assert "attributed" not in stats, (
        "a refusal must not also carry a verdict — a caller reading `attributed` "
        "would get a boolean the run did not earn"
    )


def test_a_channel_that_did_not_detect_in_every_trial_is_a_REFUSAL() -> None:
    """A statistic over the trials that happened to fire is a selected sample."""
    trials = _trials([(0.4, 0.19), (0.8, 0.19), (1.2, 0.19)])
    trials[1]["detect_latency_s"] = {}
    trials[1]["detect_since_start_s"] = {}
    stats = drill.attribution(trials, "tick")
    assert stats["refusal"]
    assert "needs a detection in every trial" in stats["refusal"]


def test_two_trials_are_a_REFUSAL_however_clean_they_look() -> None:
    """Two points have a stdev and no power. The floor is structural."""
    stats = drill.attribution(_trials([(0.40, 0.190), (1.20, 0.191)]), "tick")
    assert stats["refusal"]
    assert "at least 3" in stats["refusal"]


# --------------------------------------------------------------------------
# THE PER-CHANNEL REPORT — AMENDMENT 6's uncollapsed verdict
# --------------------------------------------------------------------------


def test_each_channel_is_judged_against_ITS_OWN_threshold() -> None:
    """The same age is fresh on one channel and stale on the other. The point."""
    now = 1000.0
    report = drill.report_for({"tick": now - 0.50, "poll": now - 0.50}, now)
    assert report.channel(FeedChannel.TICK).state is ChannelState.STALE
    assert report.channel(FeedChannel.POLL).state is ChannelState.FRESH
    assert report.stale_channels == (FeedChannel.TICK,)
    assert report.fresh_channels == (FeedChannel.POLL,)


def test_a_channel_with_no_venue_clock_is_CANNOT_MEASURE_never_stale() -> None:
    """`ChannelState`'s third member: an unasked question is not a degradation."""
    report = drill.report_for({"tick": 999.9}, 1000.0)
    assert report.channel(FeedChannel.POLL).state is ChannelState.CANNOT_MEASURE
    assert FeedChannel.POLL not in report.stale_channels


def test_the_report_carries_the_numbers_behind_every_verdict() -> None:
    """A verdict whose inputs are stripped cannot be recomputed by an operator."""
    now = 1000.0
    entry = drill.report_for({"tick": now - 0.05, "poll": now - 0.05}, now).channel(
        FeedChannel.TICK
    )
    assert entry.excess_staleness_s == pytest.approx(0.05)
    assert entry.threshold_s == drill.THRESHOLD_S[FeedChannel.TICK]
    assert entry.lag.effective_lag_s == 0.0
    assert entry.recv_ts == now


def test_the_two_thresholds_are_far_enough_apart_to_be_distinguishable() -> None:
    """The gate's `MIN_CHANNEL_GAP_S` is only meaningful if this holds."""
    gap = drill.THRESHOLD_S[FeedChannel.POLL] - drill.THRESHOLD_S[FeedChannel.TICK]
    assert gap > 0.5, (
        f"the channel thresholds differ by only {gap}s — equal-ish thresholds make "
        "simultaneous transitions correct and destroy the per-channel proof"
    )


# --------------------------------------------------------------------------
# PLANE-2 BOOKKEEPING
# --------------------------------------------------------------------------


def test_a_seq_the_bus_saw_and_the_journal_lacks_is_reported_as_LOST() -> None:
    """The comparison is between two independent transports, not one's opinion."""
    arm = drill._plane2_arm(
        {"pid": 7, "bus_max_seq": 5, "killed": True}, {1, 2, 4, 5}, set()
    )
    assert arm["lost_below_bus_max"] == [3]
    assert arm["bus_compared"] is True


def test_an_arm_with_no_bus_record_says_so_rather_than_reporting_a_clean_sheet() -> (
    None
):
    """The clean-exit control runs with no observer; empty must not read as clean."""
    arm = drill._plane2_arm(
        {"pid": 8, "bus_max_seq": 0, "killed": False}, {1, 2}, set()
    )
    assert arm["bus_compared"] is False
    assert arm["lost_below_bus_max"] == []
    assert arm["beyond_bus_max"] == []


def test_lifecycle_events_are_read_off_the_line_not_assumed() -> None:
    """`process_stop` presence comes from the journal text, per PID."""
    arm = drill._plane2_arm(
        {"pid": 9, "bus_max_seq": 2, "killed": False},
        {1, 2},
        {"process_start", "process_stop"},
    )
    assert arm["process_start_in_journal"] is True
    assert arm["process_stop_in_journal"] is True


def test_the_field_splitter_handles_a_real_section_12_10_line() -> None:
    """A quoted value with spaces must not break the `key=value` split."""
    line = (
        "ts=2026-08-12T10:00:00.000000Z proc=capture.py event=drill_heartbeat "
        "nonce=abc seq=41 ring_seq=99"
    )
    fields = drill._fields(line)
    assert fields["proc"] == "capture.py"
    assert fields["event"] == "drill_heartbeat"
    assert fields["seq"] == "41"


# --------------------------------------------------------------------------
# CONSTANTS THAT THE GATES' VERDICTS REST ON
# --------------------------------------------------------------------------


def test_the_attribution_ratio_and_jitter_floor_are_stated_not_implicit() -> None:
    """Both are read by `check_feed_kill_drill`; a silent default would hide them."""
    assert drill.ATTRIBUTION_RATIO >= 3.0
    assert 0.0 < drill.MIN_JITTER_S < (drill.KILL_MAX_S - drill.KILL_MIN_S)


def test_the_producer_symbol_and_topic_do_not_collide_with_capture_pys_table() -> None:
    """The drill owns `tbl.drill_heartbeat`; `capture.py` owns `tbl.feed_status`."""
    import capture

    assert drill.TOPIC_HEARTBEAT != capture.TOPIC_FEED_STATUS
    assert drill.TOPIC_HEARTBEAT.startswith("tbl.")
