"""ARC 033 / 1C -- unit suite for `scripts/nixrisk/freshness.py`.

`checks/check_staleness.py` is the standing gate and it drives the same module;
this file is the finer-grained companion, and the split follows the one every
other pair in this tree uses: the GATE proves the properties a running system
depends on, in the shape `verify.py` reports; the SUITE covers the boundary
cases and the refusals a gate would be over-broad to carry.

Nothing here is a duplicate instrument (doctrine C.9). The gate asserts *the
detector blocks a dead feed and clears a slow one*; this file asserts what
happens at the exact threshold, at the exact deadline, on a bad config, on a
naive instant, and on a stamp the venue re-sent.
"""
# pylint: disable=invalid-name,redefined-outer-name
# pylint: disable=missing-function-docstring,duplicate-code
# pylint: disable=too-many-arguments,too-many-positional-arguments
# Test NAMES carry the property here (`test_exactly_AT_the_threshold_is_FRESH`);
# where a case needs an argument, the docstring is on the case, not the helper.

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.calendar_seam import (  # pylint: disable=wrong-import-position
    CacheState,
    FreshnessStamp,
)
from nixrisk.freshness import (  # pylint: disable=wrong-import-position
    GLOBAL_FEEDS,
    ClockSkewFlagPort,
    ClockSkewMonitor,
    FreshnessTracker,
    NaiveInstantError,
    RetryLadder,
    SkewObservation,
    SourceMonotonicGuard,
    StalenessFlagPort,
    StalenessPolicy,
    StalenessUsageError,
    feed_key,
)

EPOCH = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)
FEED = "margin"
SYMBOL = "ES"


def _shipped_values() -> dict:
    raw = json.loads(
        (REPO / "risks" / "staleness.config.json").read_text(encoding="utf-8")
    )
    return {k: v for k, v in raw.items() if not k.startswith("_")}


class _Clock:
    def __init__(self) -> None:
        self.now = EPOCH

    def __call__(self) -> datetime:
        return self.now

    def set_ms(self, offset: float) -> datetime:
        self.now = EPOCH + timedelta(milliseconds=offset)
        return self.now


@pytest.fixture
def policy() -> StalenessPolicy:
    return StalenessPolicy.from_values(_shipped_values())


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def tracker(policy: StalenessPolicy, clock: _Clock) -> FreshnessTracker:
    return FreshnessTracker(policy, clock=clock)


# ---------------------------------------------------------------------------
# The policy loads from the SHIPPED config and refuses everything else
# ---------------------------------------------------------------------------


def test_the_policy_derives_its_feed_names_from_the_config_keys(policy) -> None:
    """Feed names are DERIVED, never listed -- directive 3."""
    assert set(policy.feeds) == {"margin", "calendar", "price", "balance"}


def test_the_deadline_is_the_threshold_PLUS_the_retry_ladder(policy) -> None:
    assert policy.deadline_ms(FEED) == policy.threshold_ms(FEED) + policy.retry.total_ms
    assert policy.retry.total_ms > 0


def test_a_feed_with_no_configured_threshold_RAISES(policy) -> None:
    with pytest.raises(StalenessUsageError, match="no §12A threshold"):
        policy.threshold_ms("nonexistent")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"margin_stale_ms": 0}, "non-positive stale threshold"),
        ({"margin_stale_ms": "5000"}, "expected a number"),
        ({"clock_skew_max_ms": -1}, "non-positive skew ceiling"),
        ({"clock_skew_max_ms": None}, "absent or not a number"),
        ({"retry_backoff": None}, "absent or is not an object"),
        ({"retry_backoff": {"attempts": 1}}, "missing 'initial_ms'"),
        (
            {"retry_backoff": {"attempts": 0, "initial_ms": 1, "multiplier": 2}},
            "no rung",
        ),
    ],
)
def test_a_broken_config_RAISES_rather_than_defaulting(mutation, match) -> None:
    """Directive 4 / doctrine C.7: never degraded to defaults."""
    values = _shipped_values() | mutation
    with pytest.raises(StalenessUsageError, match=match):
        StalenessPolicy.from_values(values)


def test_a_config_with_no_stale_threshold_at_all_RAISES() -> None:
    values = {k: v for k, v in _shipped_values().items() if not k.endswith("_stale_ms")}
    with pytest.raises(StalenessUsageError, match="declares nothing stale, ever"):
        StalenessPolicy.from_values(values)


def test_the_retry_ladder_total_is_the_geometric_sum() -> None:
    ladder = RetryLadder(attempts=3, initial_ms=100.0, multiplier=2.0)
    assert ladder.total_ms == pytest.approx(100.0 + 200.0 + 400.0)


# ---------------------------------------------------------------------------
# THE MEASURE: time since last arrival, at the exact boundaries
# ---------------------------------------------------------------------------


def _observe(tracker, clock, offset_ms, seq=1, feed=FEED, symbol=SYMBOL):
    at = clock.set_ms(offset_ms)
    return tracker.observe(FreshnessStamp(feed=feed, as_of=at, source_seq=seq), symbol)


def test_exactly_AT_the_threshold_is_FRESH(tracker, clock, policy) -> None:
    """`<=` by declaration: the threshold is the last fresh instant."""
    _observe(tracker, clock, 0.0)
    clock.set_ms(policy.threshold_ms(FEED))
    reading = tracker.reading(FEED, SYMBOL)
    assert reading.state is CacheState.FRESH
    assert reading.blocked is False


def test_one_ms_PAST_the_threshold_is_STALE_but_not_yet_blocked(
    tracker, clock, policy
) -> None:
    _observe(tracker, clock, 0.0)
    clock.set_ms(policy.threshold_ms(FEED) + 1.0)
    reading = tracker.reading(FEED, SYMBOL)
    assert reading.state is CacheState.STALE
    assert reading.blocked is False
    assert "retry/backoff" in reading.reason


def test_exactly_AT_the_deadline_is_still_not_blocked(tracker, clock, policy) -> None:
    _observe(tracker, clock, 0.0)
    clock.set_ms(policy.deadline_ms(FEED))
    assert tracker.reading(FEED, SYMBOL).blocked is False


def test_one_ms_PAST_the_deadline_blocks(tracker, clock, policy) -> None:
    _observe(tracker, clock, 0.0)
    clock.set_ms(policy.deadline_ms(FEED) + 1.0)
    reading = tracker.reading(FEED, SYMBOL)
    assert reading.blocked is True
    assert "LAST ARRIVAL" in reading.reason
    assert "halt" in reading.reason


def test_a_FRESH_arrival_during_the_retry_window_clears_the_condition(
    tracker, clock, policy
) -> None:
    """The retries are not a countdown to a halt; a recovered feed is fresh."""
    _observe(tracker, clock, 0.0)
    clock.set_ms(policy.threshold_ms(FEED) + 1.0)
    assert tracker.reading(FEED, SYMBOL).state is CacheState.STALE
    _observe(tracker, clock, policy.threshold_ms(FEED) + 2.0, seq=2)
    assert tracker.reading(FEED, SYMBOL).state is CacheState.FRESH


def test_a_never_observed_key_is_EMPTY_and_BLOCKS(tracker) -> None:
    reading = tracker.reading(FEED, SYMBOL)
    assert reading.state is CacheState.EMPTY
    assert reading.blocked is True
    assert reading.age_ms is None
    assert "NEVER" in reading.reason


def test_a_source_stamp_AHEAD_of_the_clock_beyond_the_skew_ceiling_BLOCKS(
    tracker, clock, policy
) -> None:
    """A future-dated stamp never ages, so the property would be INVERTED."""
    _observe(tracker, clock, policy.clock_skew_max_ms * 10.0)
    clock.set_ms(0.0)
    reading = tracker.reading(FEED, SYMBOL)
    assert reading.blocked is True
    assert "AHEAD" in reading.reason


def test_a_source_stamp_a_LITTLE_ahead_is_tolerated(tracker, clock, policy) -> None:
    """Inside CLOCK_SKEW_MAX_MS is ordinary clock disagreement, not a fault."""
    _observe(tracker, clock, policy.clock_skew_max_ms / 2.0)
    clock.set_ms(0.0)
    assert tracker.reading(FEED, SYMBOL).state is CacheState.FRESH


# ---------------------------------------------------------------------------
# §12.3 -- all internal time is UTC
# ---------------------------------------------------------------------------


def test_a_NAIVE_source_stamp_is_refused(tracker) -> None:
    with pytest.raises(NaiveInstantError, match="NAIVE"):
        tracker.observe(
            FreshnessStamp(feed=FEED, as_of=EPOCH.replace(tzinfo=None)), SYMBOL
        )


def test_an_OFFSET_source_stamp_is_refused(tracker) -> None:
    offset = EPOCH.astimezone(timezone_plus_two())
    with pytest.raises(NaiveInstantError, match="non-zero UTC offset"):
        tracker.observe(FreshnessStamp(feed=FEED, as_of=offset), SYMBOL)


def timezone_plus_two():
    """A fixed +02:00 zone. Built here rather than imported from `zoneinfo`:
    the point is the OFFSET, and a named zone would drag DST into the test."""
    from datetime import timezone  # pylint: disable=import-outside-toplevel

    return timezone(timedelta(hours=2))


def test_a_NAIVE_clock_is_refused(policy) -> None:
    tracker = FreshnessTracker(policy, clock=lambda: EPOCH.replace(tzinfo=None))
    tracker.observe(FreshnessStamp(feed=FEED, as_of=EPOCH), SYMBOL)
    with pytest.raises(NaiveInstantError):
        tracker.reading(FEED, SYMBOL)


# ---------------------------------------------------------------------------
# §6.4b -- MONOTONIC BY SOURCE, per key
# ---------------------------------------------------------------------------


def test_an_older_reading_is_DISCARDED_and_COUNTED() -> None:
    guard = SourceMonotonicGuard()
    newer = FreshnessStamp(feed=FEED, as_of=EPOCH + timedelta(seconds=10), source_seq=2)
    older = FreshnessStamp(feed=FEED, as_of=EPOCH, source_seq=1)
    assert guard.admit("k", newer) is True
    assert guard.admit("k", older) is False
    assert guard.discarded_older == 1
    assert guard.admitted == 1
    assert guard.held("k") is newer


def test_an_IDENTICAL_reading_is_not_newer() -> None:
    guard = SourceMonotonicGuard()
    stamp = FreshnessStamp(feed=FEED, as_of=EPOCH, source_seq=1)
    assert guard.admit("k", stamp) is True
    assert guard.admit("k", stamp) is False


def test_an_equal_instant_is_broken_by_the_venue_SEQUENCE() -> None:
    guard = SourceMonotonicGuard()
    first = FreshnessStamp(feed=FEED, as_of=EPOCH, source_seq=1)
    second = FreshnessStamp(feed=FEED, as_of=EPOCH, source_seq=2)
    assert guard.admit("k", first) is True
    assert guard.admit("k", second) is True
    assert guard.held("k") is second


def test_an_equal_instant_with_NO_sequence_is_discarded() -> None:
    """Without a tie-break there is no evidence the reading is newer."""
    guard = SourceMonotonicGuard()
    first = FreshnessStamp(feed=FEED, as_of=EPOCH)
    second = FreshnessStamp(feed=FEED, as_of=EPOCH)
    assert guard.admit("k", first) is True
    assert guard.admit("k", second) is False


def test_the_guard_is_PER_KEY(tracker, clock) -> None:
    _observe(tracker, clock, 10_000.0, seq=2, symbol="ES")
    _observe(tracker, clock, 10_000.0, seq=2, symbol="NQ")
    _observe(tracker, clock, 0.0, seq=1, symbol="ES")
    assert tracker.held(FEED, "NQ").as_of == EPOCH + timedelta(seconds=10)
    assert tracker.held(FEED, "ES").as_of == EPOCH + timedelta(seconds=10)


def test_an_unstamped_reading_RAISES_rather_than_degrading() -> None:
    """Unlike the consumer-side mirror, this seam CONSTRUCTS its stamps."""
    guard = SourceMonotonicGuard()
    with pytest.raises(StalenessUsageError, match="defect in the producer"):
        guard.admit("k", object())  # type: ignore[arg-type]


def test_the_key_shape_separates_global_feeds_from_per_symbol_ones() -> None:
    assert "balance" in GLOBAL_FEEDS
    assert feed_key("balance", "ES") == "balance"
    assert feed_key("margin", "ES") == "margin:ES"


def test_an_unknown_feed_defaults_to_PER_SYMBOL_which_fails_closed() -> None:
    """A global feed mistakenly keyed per symbol reads EMPTY and BLOCKS."""
    assert feed_key("brand_new_feed", "ES") == "brand_new_feed:ES"


def test_observing_a_feed_with_no_threshold_RAISES(tracker) -> None:
    with pytest.raises(StalenessUsageError, match="no §12A threshold"):
        tracker.observe(FreshnessStamp(feed="unknown", as_of=EPOCH), SYMBOL)


# ---------------------------------------------------------------------------
# The two ports
# ---------------------------------------------------------------------------


def test_the_flag_port_names_EVERY_blocking_feed(tracker, clock, policy) -> None:
    """§3: a denial must be actionable; naming one dead feed of three is not."""
    port = StalenessFlagPort(tracker)
    for feed in policy.feeds:
        _observe(tracker, clock, 0.0, feed=feed)
    clock.set_ms(max(policy.deadline_ms(f) for f in policy.feeds) + 1.0)
    blocked, reason = port.read(SYMBOL)
    assert blocked is True
    for feed in policy.feeds:
        assert repr(feed) in reason


def test_the_flag_port_is_clear_when_every_feed_is_fresh(
    tracker, clock, policy
) -> None:
    port = StalenessFlagPort(tracker)
    for feed in policy.feeds:
        _observe(tracker, clock, 0.0, feed=feed)
    clock.set_ms(0.0)
    assert port.read(SYMBOL) == (False, "")


def test_the_clock_port_alias_is_the_same_object() -> None:
    assert ClockSkewFlagPort is ClockSkewMonitor


def test_an_unobserved_clock_BLOCKS(policy, clock) -> None:
    monitor = ClockSkewMonitor(policy, clock=clock, observation_max_age_ms=1000.0)
    blocked, reason = monitor.read()
    assert blocked is True
    assert "NO skew observation" in reason


def test_a_good_clock_does_NOT_block(policy, clock) -> None:
    monitor = ClockSkewMonitor(policy, clock=clock, observation_max_age_ms=1000.0)
    now = clock.set_ms(0.0)
    monitor.observe(
        SkewObservation(
            local=now,
            reference=now - timedelta(milliseconds=policy.clock_skew_max_ms / 2),
            source="exchange",
            observed_at=now,
        )
    )
    assert monitor.read() == (False, "")


@pytest.mark.parametrize("direction", [1, -1])
def test_a_skewed_clock_BLOCKS_in_either_direction(policy, clock, direction) -> None:
    monitor = ClockSkewMonitor(policy, clock=clock, observation_max_age_ms=1000.0)
    now = clock.set_ms(0.0)
    monitor.observe(
        SkewObservation(
            local=now,
            reference=now
            - direction * timedelta(milliseconds=policy.clock_skew_max_ms * 3),
            source="exchange",
            observed_at=now,
        )
    )
    blocked, reason = monitor.read()
    assert blocked is True
    assert "stale-class HALT" in reason
    assert ("AHEAD of" if direction > 0 else "BEHIND") in reason


def test_an_AGED_skew_observation_BLOCKS(policy, clock) -> None:
    monitor = ClockSkewMonitor(policy, clock=clock, observation_max_age_ms=1000.0)
    now = clock.set_ms(0.0)
    monitor.observe(
        SkewObservation(local=now, reference=now, source="exchange", observed_at=now)
    )
    clock.set_ms(1001.0)
    blocked, reason = monitor.read()
    assert blocked is True
    assert "holding ceiling" in reason


def test_the_observation_ceiling_has_NO_default(policy, clock) -> None:
    """`AllocatorMirror.max_age_s`'s refusal: a ceiling with a default is a
    ceiling nobody chose."""
    with pytest.raises(TypeError):
        ClockSkewMonitor(  # type: ignore[call-arg]  # pylint: disable=missing-kwoa
            policy, clock=clock
        )
    with pytest.raises(StalenessUsageError, match="must be positive"):
        ClockSkewMonitor(policy, clock=clock, observation_max_age_ms=0.0)
