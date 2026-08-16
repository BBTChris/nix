"""ARC 033 / 1C -- unit suite for `scripts/nixrisk/pollers.py`.

`checks/check_pollers.py` is the standing gate over the same module. The split
is the one every gate/suite pair in this tree uses: the GATE proves the
properties a running system depends on, in the shape `verify.py` reports; this
SUITE covers the refusals, the loop, and the boundary cases a gate would be
over-broad to carry.

Not a duplicate instrument (C.9). The gate asserts *the demotion widens the
cadence and re-promotes on silence*; this file asserts what `run` does with the
cadence it is given, what each constructor refuses, and what a push carrying an
older stamp than the cache holds does to the published snapshot.
"""
# pylint: disable=invalid-name,redefined-outer-name
# pylint: disable=missing-function-docstring,duplicate-code,unused-argument

from __future__ import annotations

import asyncio
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
    MarginBaseline,
    MarginBaselineReadPort,
    MarginPollerPort,
    Window,
    WindowKind,
    WindowSet,
)
from nixrisk.freshness import (  # pylint: disable=wrong-import-position
    FreshnessTracker,
    StalenessPolicy,
)
from nixrisk.pollers import (  # pylint: disable=wrong-import-position
    CALENDAR_FEED,
    MARGIN_FEED,
    CalendarPoller,
    MarginPoller,
    PollerMode,
    PollerUsageError,
    PushDemotion,
    StampedBaseline,
    StampedWindowSet,
)

EPOCH = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)
SYMBOLS = ("ES", "NQ")


class _Clock:
    def __init__(self) -> None:
        self.now = EPOCH

    def __call__(self) -> datetime:
        return self.now

    def set_ms(self, offset: float) -> datetime:
        self.now = EPOCH + timedelta(milliseconds=offset)
        return self.now


def _values() -> dict:
    raw = json.loads(
        (REPO / "risks" / "staleness.config.json").read_text(encoding="utf-8")
    )
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def policy() -> StalenessPolicy:
    return StalenessPolicy.from_values(_values())


@pytest.fixture
def tracker(policy: StalenessPolicy, clock: _Clock) -> FreshnessTracker:
    return FreshnessTracker(policy, clock=clock)


@pytest.fixture
def demotion(clock: _Clock) -> PushDemotion:
    return PushDemotion(
        poll_interval_ms=10.0, audit_interval_ms=40.0, push_idle_ms=100.0, clock=clock
    )


def _rows(at: datetime, seq: int, symbols=SYMBOLS) -> list[StampedBaseline]:
    return [
        StampedBaseline(
            baseline=MarginBaseline(symbol=sym, level=1000.0 + seq, accepted_at=at),
            stamp=FreshnessStamp(feed=MARGIN_FEED, as_of=at, source_seq=seq),
        )
        for sym in symbols
    ]


def _margin(tracker, demotion, clock, symbols=SYMBOLS, sink=None):
    state = {"seq": 0}

    async def fetch() -> list[StampedBaseline]:
        state["seq"] += 1
        return _rows(clock(), state["seq"], symbols)

    return MarginPoller(fetch=fetch, tracker=tracker, demotion=demotion, sink=sink)


def _calendar(tracker, demotion, clock, symbols=SYMBOLS, sink=None):
    return CalendarPoller(
        symbols=list(symbols),
        build=lambda s: (
            Window(
                kind=WindowKind.EOD,
                symbol=s,
                start=clock(),
                end=clock() + timedelta(minutes=20),
                entry_only=True,
                source="unit suite",
            ),
        ),
        stamp_for=lambda s: FreshnessStamp(
            feed=CALENDAR_FEED, as_of=clock(), source_seq=1
        ),
        tracker=tracker,
        clock=clock,
        demotion=demotion,
        sink=sink,
    )


# ---------------------------------------------------------------------------
# Construction refusals -- never degraded to a default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"poll_interval_ms": 0.0}, "must be positive"),
        ({"audit_interval_ms": 10.0}, "changed a NAME"),
        ({"audit_interval_ms": 5.0}, "changed a NAME"),
        ({"push_idle_ms": 0.0}, "must be positive"),
    ],
)
def test_PushDemotion_refuses_a_configuration_that_cannot_demote(
    clock, kwargs, match
) -> None:
    base = {
        "poll_interval_ms": 10.0,
        "audit_interval_ms": 40.0,
        "push_idle_ms": 100.0,
        "clock": clock,
    }
    with pytest.raises(PollerUsageError, match=match):
        PushDemotion(**(base | kwargs))


def test_a_calendar_poller_over_no_symbols_is_refused(tracker, demotion, clock) -> None:
    """An empty window set reads exactly like a clear one to §6.5's rule."""
    with pytest.raises(PollerUsageError, match="empty window set"):
        _calendar(tracker, demotion, clock, symbols=())


def test_an_empty_margin_reading_is_refused(tracker, demotion, clock) -> None:
    async def fetch() -> list:
        return []

    poller = MarginPoller(fetch=fetch, tracker=tracker, demotion=demotion)
    with pytest.raises(PollerUsageError, match="carried NO rows"):
        asyncio.run(poller.poll_once())


def test_a_row_carrying_the_WRONG_feed_is_refused(tracker, demotion, clock) -> None:
    async def fetch() -> list:
        return [
            StampedBaseline(
                baseline=MarginBaseline("ES", 1.0, clock()),
                stamp=FreshnessStamp(feed="price", as_of=clock(), source_seq=1),
            )
        ]

    poller = MarginPoller(fetch=fetch, tracker=tracker, demotion=demotion)
    with pytest.raises(PollerUsageError, match="carries feed 'price'"):
        asyncio.run(poller.poll_once())


# ---------------------------------------------------------------------------
# The ports the seam declared
# ---------------------------------------------------------------------------


def test_the_margin_poller_satisfies_both_of_its_declared_ports(
    tracker, demotion, clock
) -> None:
    poller = _margin(tracker, demotion, clock)
    assert isinstance(poller, MarginPollerPort)
    assert isinstance(poller, MarginBaselineReadPort)


def test_a_published_row_is_a_BASELINE_and_never_a_live_figure(
    tracker, demotion, clock
) -> None:
    """§6.4's v1.3 lock, from the cache's side."""
    poller = _margin(tracker, demotion, clock)
    asyncio.run(poller.poll_once())
    assert poller.published()
    assert all(isinstance(row, MarginBaseline) for row in poller.published())


def test_the_calendar_poller_publishes_one_window_set_per_symbol(
    tracker, demotion, clock
) -> None:
    poller = _calendar(tracker, demotion, clock)
    asyncio.run(poller.refresh())
    assert {s.symbol for s in poller.published()} == set(SYMBOLS)
    assert all(isinstance(s, WindowSet) for s in poller.published())
    assert poller.windows("ES") is not None
    assert poller.windows("XX") is None


# ---------------------------------------------------------------------------
# §6.4 push-preferred
# ---------------------------------------------------------------------------


def test_a_push_demotes_and_silence_re_promotes(tracker, demotion, clock) -> None:
    poller = _margin(tracker, demotion, clock)
    assert poller.mode is PollerMode.PRIMARY
    at = clock.set_ms(1.0)
    assert poller.on_push(_rows(at, 5), at) == len(SYMBOLS)
    assert poller.mode is PollerMode.FALLBACK_AUDIT
    assert demotion.interval_ms() == 40.0
    clock.set_ms(1000.0)
    assert poller.mode is PollerMode.PRIMARY
    assert demotion.interval_ms() == 10.0
    assert demotion.demotions == 1
    assert demotion.promotions == 1


def test_a_poll_taken_while_demoted_counts_as_an_AUDIT(
    tracker, demotion, clock
) -> None:
    poller = _margin(tracker, demotion, clock)
    at = clock.set_ms(1.0)
    poller.on_push(_rows(at, 5), at)
    clock.set_ms(2.0)
    asyncio.run(poller.poll_once())
    assert poller.audit_polls == 1
    assert poller.polls == 1


def test_a_slow_poll_landing_behind_a_fresher_push_is_DROPPED(
    tracker, demotion, clock
) -> None:
    """§6.4b's own parenthetical, measured on the producer."""
    poller = _margin(tracker, demotion, clock)
    fresh_at = clock.set_ms(10_000.0)
    poller.on_push(_rows(fresh_at, 90), fresh_at)
    level = poller.baseline("ES").level

    stale_at = clock.set_ms(0.0)
    before = tracker.guard.discarded_older
    poller.on_push(_rows(stale_at, 1), stale_at)
    assert tracker.guard.discarded_older == before + len(SYMBOLS)
    assert poller.baseline("ES").level == level


# ---------------------------------------------------------------------------
# Cache-level verdicts
# ---------------------------------------------------------------------------


def test_a_cache_that_never_published_is_EMPTY(tracker, demotion, clock) -> None:
    poller = _margin(tracker, demotion, clock)
    assert poller.state() is CacheState.EMPTY
    assert poller.freshness() is None


def test_the_cache_is_as_stale_as_its_STALEST_key(
    tracker, demotion, clock, policy
) -> None:
    poller = _margin(tracker, demotion, clock)
    at0 = clock.set_ms(0.0)
    poller.on_push(_rows(at0, 1), at0)
    at1 = clock.set_ms(policy.threshold_ms(MARGIN_FEED) * 50.0)
    poller.on_push(_rows(at1, 2, symbols=("ES",)), at1)
    assert poller.state() is CacheState.STALE
    assert poller.freshness().as_of == at0


def test_the_calendar_cache_reports_its_own_feed(tracker, demotion, clock) -> None:
    poller = _calendar(tracker, demotion, clock)
    asyncio.run(poller.refresh())
    assert poller.state() is CacheState.FRESH
    assert poller.freshness().feed == CALENDAR_FEED


# ---------------------------------------------------------------------------
# §12.7 publish
# ---------------------------------------------------------------------------


def test_the_sink_receives_the_published_snapshot(tracker, demotion, clock) -> None:
    seen: list[tuple] = []
    poller = _margin(tracker, demotion, clock, sink=seen.append)
    asyncio.run(poller.poll_once())
    assert len(seen) == 1
    assert seen[0] == poller.published()


def test_publishing_takes_a_COPY_of_the_callers_sequence(
    tracker, demotion, clock
) -> None:
    poller = _margin(tracker, demotion, clock)
    rows = [MarginBaseline("ES", 1.0, clock())]
    poller.publish(tuple(rows))
    rows.clear()
    assert len(poller.published()) == 1


def test_the_calendar_push_path_also_goes_through_the_guard(
    tracker, demotion, clock
) -> None:
    poller = _calendar(tracker, demotion, clock)
    fresh_at = clock.set_ms(10_000.0)
    fresh = tuple(
        StampedWindowSet(
            window_set=WindowSet(symbol=s, windows=(), generated_at=fresh_at),
            stamp=FreshnessStamp(feed=CALENDAR_FEED, as_of=fresh_at, source_seq=2),
        )
        for s in SYMBOLS
    )
    assert poller.on_push(fresh, fresh_at) == len(SYMBOLS)
    stale_at = clock.set_ms(0.0)
    stale = tuple(
        StampedWindowSet(
            window_set=WindowSet(symbol=s, windows=(), generated_at=stale_at),
            stamp=FreshnessStamp(feed=CALENDAR_FEED, as_of=stale_at, source_seq=1),
        )
        for s in SYMBOLS
    )
    assert poller.on_push(stale, stale_at) == 0


# ---------------------------------------------------------------------------
# §10 -- the shared-pool loop
# ---------------------------------------------------------------------------


def test_run_stops_at_max_cycles(tracker, demotion, clock) -> None:
    poller = _margin(tracker, demotion, clock)

    async def drive() -> int:
        return await poller.run(stop=asyncio.Event(), max_cycles=3)

    assert asyncio.run(drive()) == 3
    assert poller.polls == 3


def test_run_returns_immediately_when_stop_is_already_set(
    tracker, demotion, clock
) -> None:
    poller = _margin(tracker, demotion, clock)

    async def drive() -> int:
        stop = asyncio.Event()
        stop.set()
        return await poller.run(stop=stop, max_cycles=10)

    assert asyncio.run(drive()) == 0
    assert poller.polls == 0


def test_the_refresh_yields_ONCE_PER_SYMBOL(tracker, demotion, clock) -> None:
    """The §6.4 DURATION argument, measured rather than asserted in a comment."""
    symbols = tuple(f"S{i:02d}" for i in range(25))
    poller = _calendar(tracker, demotion, clock, symbols=symbols)
    ticks = {"n": 0}

    async def drive() -> None:
        running = True

        async def ticker() -> None:
            while running:
                ticks["n"] += 1
                await asyncio.sleep(0)

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0)
        start = ticks["n"]
        await poller.refresh()
        ticks["during"] = ticks["n"] - start
        running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(drive())
    assert poller.yields == len(symbols)
    assert ticks["during"] >= len(symbols) - 1


def test_a_hung_margin_fetch_does_not_stop_the_calendar(
    tracker, demotion, clock
) -> None:
    """§6.4 CONTAINMENT: one suspended coroutine, not one blocked pool worker."""

    async def drive() -> tuple[int, bool]:
        gate = asyncio.Event()

        async def hang() -> list:
            await gate.wait()
            return _rows(clock(), 1)

        hung = MarginPoller(fetch=hang, tracker=tracker, demotion=demotion)
        calendar = _calendar(tracker, demotion, clock)
        task = asyncio.create_task(hung.poll_once())
        await asyncio.sleep(0)
        await calendar.refresh()
        still_hung = not task.done()
        gate.set()
        await task
        return calendar.publishes, still_hung

    publishes, still_hung = asyncio.run(drive())
    assert publishes == 1
    assert still_hung is True
