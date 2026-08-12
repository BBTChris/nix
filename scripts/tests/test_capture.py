"""ARC 026 — the properties `scripts/capture.py` claims (§10, §12.7, §12.10).

What each test proves:

* **The transition rule, not a level.** `FeedStalenessMonitor.observe` emits on
  the FIRST observation with `previous == "unobserved"`, emits NOTHING when the
  same state is seen again, and emits exactly one transition naming `from` and
  `to` when a channel moves. §12.10's inventory row is *staleness TRANSITIONS*;
  a level log at feed-poll rate is the chatty logging that section rejects.
* **AMENDMENT 6, the load-bearing one.** One report carrying TICK and POLL in
  DIFFERENT states produces TWO transitions, one per channel. A per-symbol event
  would satisfy a shape test and would be exactly the collapse the amendment
  forbids.
* **No collapsed boolean anywhere.** `monitor.table()` is
  `{symbol: {channel: state}}` and the per-symbol dict holds channel names only —
  no `is_stale`, no `stale`, no `fresh`.
* **A verdict ships its inputs.** `StalenessTransition.fields()` carries symbol,
  channel, from, to, excess_staleness_s, threshold_s, effective_lag_s, venue_ts
  and lag_provenance, so an operator reading one journal line can recompute the
  verdict instead of being handed it.
* **The process announces itself and its exit.** A `CaptureProcess` driven with
  an injected recording Plane 2 emits `process_start`, one
  `feed_staleness_transition` per transition, and `process_stop`.
* **The tick path is the ring, and only the ring.** `on_tick` with an injected
  writer lands a real tick in real shared memory; with `ring=None` it is a no-op
  rather than an error.
* **The CLI refuses to pretend.** `main([])` returns 2 and says on STDERR that no
  venue session exists, rather than exercising a connect path never observed.

**No test pins the pytest process.** Every `CaptureProcess` is constructed with
`pin=False`, and the one CLI arm that could pin passes `--no-pin` explicitly. The
inputs are the REAL seam types, so `ChannelFreshness.__post_init__`'s refusal of
a verdict that contradicts its own numbers applies to these inputs too — a stub
could feed `capture.py` a state the seam could never produce.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the fixtures are reused by design; the sys.path
# bootstrap is shared with the sibling suites. Each deliberate.

from __future__ import annotations

import os
import secrets
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "scripts" / "broker"))

import capture  # pylint: disable=wrong-import-position
from broker_seam import (  # pylint: disable=wrong-import-position
    ChannelFreshness,
    ChannelState,
    FeedChannel,
    FeedLag,
    FreshnessReport,
    LagProvenance,
    MarketDataMode,
)
from nixbus import price_ring  # pylint: disable=wrong-import-position
from nixverify.plane2 import Plane2  # pylint: disable=wrong-import-position

SYMBOL = "MESU6"
THRESHOLD_S = 5.0
DECLARED_LAG_S = 1.0
#: Inside and outside `THRESHOLD_S`. `ChannelFreshness.__post_init__` refuses any
#: other pairing with these states, which is why they are named rather than
#: inlined per call.
FRESH_EXCESS_S = 0.5
STALE_EXCESS_S = 60.0


class _RecordingPlane2:
    """A `Plane2` stand-in that records instead of opening `/dev/log`.

    Injected rather than monkeypatched: `CaptureProcess` takes its emitter as a
    constructor argument precisely so the emission RULE can be tested without a
    journal, and a test that reached for the real transport would be measuring
    journald as well as the rule.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.closes = 0

    def emit(self, event: str, **fields: Any) -> None:
        """Record one §12.10 event exactly as the real emitter is called."""
        self.events.append((event, dict(fields)))

    def close(self) -> None:
        """Count the release; the real one drops its handler here."""
        self.closes += 1

    def names(self) -> list[str]:
        """Event names, in emission order."""
        return [name for name, _ in self.events]

    def fields_for(self, event: str) -> list[dict[str, Any]]:
        """Every payload emitted under one event name."""
        return [fields for name, fields in self.events if name == event]


def _lag(channel: FeedChannel) -> FeedLag:
    """One channel's declared lag. `VENDOR_DECLARED`, never a fabricated zero."""
    return FeedLag(
        declared_lag_s=DECLARED_LAG_S,
        observed_lag_s=None,
        observed_n=0,
        provenance=LagProvenance.VENDOR_DECLARED,
        granted_mode=MarketDataMode.DELAYED,
        channel=channel,
    )


def _channel(channel: FeedChannel, state: ChannelState, now: float) -> ChannelFreshness:
    """One channel's freshness, with numbers the seam will accept beside it."""
    excess = {
        ChannelState.FRESH: FRESH_EXCESS_S,
        ChannelState.STALE: STALE_EXCESS_S,
        ChannelState.CANNOT_MEASURE: None,
    }[state]
    return ChannelFreshness(
        channel=channel,
        venue_ts=None if excess is None else now - 1.0,
        lag=_lag(channel),
        excess_staleness_s=excess,
        threshold_s=THRESHOLD_S,
        state=state,
        recv_ts=now,
    )


def _report(
    *states: tuple[FeedChannel, ChannelState],
    symbol: str = SYMBOL,
    now: float | None = None,
) -> FreshnessReport:
    """A real `FreshnessReport` over one or more channels."""
    stamp = time.time() if now is None else now
    return FreshnessReport(
        symbol=symbol,
        now=stamp,
        channels=tuple(_channel(channel, state, stamp) for channel, state in states),
    )


def _purge(segment: str) -> None:
    """Unlink a `/dev/shm` segment if it survived. Never raises — this is teardown.

    Through `price_ring.unlink_segment` rather than a second `PriceRingWriter`:
    on a failing test the incumbent writer is still LIVE and the module would
    correctly REFUSE a second one, so a teardown built that way would bury the
    failure it was cleaning up after.

    And through `price_ring` rather than straight to
    `multiprocessing.shared_memory`, which is what this helper did until
    `checks/check_price_ring.py` caught it: §12.7 makes `price_ring.py` the SOLE
    shared-memory user in Nix, and a test reaching for a segment directly is a
    second one however convenient the reason. The gate reported it as
    `scripts/tests/test_capture.py: shared memory outside §12.7's sole exception
    (line 47: from multiprocessing import shared_memory)`, which is the sweep
    doing exactly its job on code written minutes earlier.
    """
    price_ring.unlink_segment(segment)


@pytest.fixture
def plane() -> _RecordingPlane2:
    """The injected Plane-2 recorder."""
    return _RecordingPlane2()


@pytest.fixture
def ring_name() -> Iterator[str]:
    """A unique `/dev/shm` segment name, unlinked at teardown whatever happens.

    Teardown goes straight to the kernel rather than through a second
    `PriceRingWriter`: on a failing test the incumbent writer is still LIVE, and
    the module would correctly REFUSE the second writer — a teardown that raised
    would bury the failure it was cleaning up after.
    """
    name = f"nix_test_capture_{os.getpid()}_{secrets.token_hex(4)}"
    try:
        yield name
    finally:
        _purge(name)


# --- the transition rule ---------------------------------------------------


def test_the_FIRST_observation_is_a_transition_OUT_OF_UNOBSERVED() -> None:
    """A channel's first reading is the move out of 'no relationship'."""
    monitor = capture.FeedStalenessMonitor()

    moved = monitor.observe(_report((FeedChannel.TICK, ChannelState.FRESH)))

    assert len(moved) == 1, moved
    assert moved[0].previous == capture.UNOBSERVED == "unobserved", moved[0]
    assert moved[0].current is ChannelState.FRESH, moved[0]
    assert moved[0].channel is FeedChannel.TICK, moved[0]
    assert monitor.transitions == 1, monitor.transitions
    assert monitor.observations == 1, monitor.observations


def test_RE_OBSERVING_the_SAME_STATE_emits_NOTHING(plane: _RecordingPlane2) -> None:
    """THE CONTROL for the transition rule: a level log emits here, this must not.

    Driven through `CaptureProcess` as well as the monitor, because the emission
    is what §12.10 constrains and a monitor that stayed quiet while the process
    emitted anyway would satisfy a monitor-only test.
    """
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), pin=False)
    report = _report((FeedChannel.TICK, ChannelState.FRESH))

    first = process.observe_freshness(report)
    again = process.observe_freshness(report)

    assert len(first) == 1, first
    assert not again, f"an unchanged channel emitted {len(again)} transition(s)"
    assert process.monitor.observations == 2, "the second report was never read"
    assert process.monitor.transitions == 1, process.monitor.transitions
    assert plane.names() == ["feed_staleness_transition"], plane.names()


def test_a_CHANGE_emits_EXACTLY_ONE_transition_naming_FROM_and_TO() -> None:
    """The move is reported once, and it carries both ends of the move."""
    monitor = capture.FeedStalenessMonitor()
    monitor.observe(_report((FeedChannel.TICK, ChannelState.FRESH)))

    moved = monitor.observe(_report((FeedChannel.TICK, ChannelState.STALE)))

    assert len(moved) == 1, moved
    assert moved[0].previous == "fresh", moved[0]
    assert moved[0].current is ChannelState.STALE, moved[0]
    assert moved[0].fields()["from"] == "fresh", moved[0].fields()
    assert moved[0].fields()["to"] == "stale", moved[0].fields()
    assert monitor.state_of(SYMBOL, FeedChannel.TICK) == "stale"


def test_TWO_CHANNELS_in_DIFFERENT_STATES_produce_TWO_transitions(
    plane: _RecordingPlane2,
) -> None:
    """AMENDMENT 6, and it is the load-bearing property of this file.

    One symbol, two channels, two lags, two states. A per-symbol event would
    collapse them and silently decide for the channel it did not measure.
    """
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), pin=False)

    moved = process.observe_freshness(
        _report(
            (FeedChannel.TICK, ChannelState.FRESH),
            (FeedChannel.POLL, ChannelState.STALE),
        )
    )

    assert len(moved) == 2, f"{len(moved)} transition(s) for two moved channels"
    assert {t.channel for t in moved} == {FeedChannel.TICK, FeedChannel.POLL}
    by_channel = {t.channel: t for t in moved}
    assert by_channel[FeedChannel.TICK].current is ChannelState.FRESH
    assert by_channel[FeedChannel.POLL].current is ChannelState.STALE
    # One Plane-2 event PER CHANNEL, each naming its own channel.
    emitted = plane.fields_for("feed_staleness_transition")
    assert len(emitted) == 2, plane.names()
    assert sorted(f["channel"] for f in emitted) == ["poll", "tick"], emitted
    assert sorted(f["to"] for f in emitted) == ["fresh", "stale"], emitted


def test_ONE_CHANNEL_MOVING_does_not_re_emit_the_channel_that_STAYED(
    plane: _RecordingPlane2,
) -> None:
    """Per-channel state, so per-channel silence when a channel does not move."""
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), pin=False)
    both = (
        (FeedChannel.TICK, ChannelState.FRESH),
        (FeedChannel.POLL, ChannelState.STALE),
    )
    assert len(process.observe_freshness(_report(*both))) == 2

    moved = process.observe_freshness(
        _report(
            (FeedChannel.TICK, ChannelState.FRESH),
            (FeedChannel.POLL, ChannelState.CANNOT_MEASURE),
        )
    )

    assert [t.channel for t in moved] == [FeedChannel.POLL], moved
    assert moved[0].previous == "stale", moved[0]
    assert moved[0].current is ChannelState.CANNOT_MEASURE, moved[0]
    assert process.monitor.state_of(SYMBOL, FeedChannel.TICK) == "fresh"


# --- the published table ---------------------------------------------------


def test_the_table_is_SYMBOL_then_CHANNEL_then_STATE_with_NO_COLLAPSED_BOOLEAN(
    plane: _RecordingPlane2,
) -> None:
    """A consumer must NAME the channel it requires in order to get an answer."""
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), pin=False)
    process.observe_freshness(
        _report(
            (FeedChannel.TICK, ChannelState.FRESH),
            (FeedChannel.POLL, ChannelState.STALE),
        )
    )
    process.observe_freshness(
        _report((FeedChannel.TICK, ChannelState.STALE), symbol="MNQU6")
    )

    table = process.monitor.table()

    assert table == {
        "MESU6": {"tick": "fresh", "poll": "stale"},
        "MNQU6": {"tick": "stale"},
    }, table
    for symbol, channels in table.items():
        for forbidden in ("is_stale", "stale", "fresh", "state", "cannot_measure"):
            assert forbidden not in channels, (
                f"{symbol} carries a collapsed {forbidden}"
            )
        assert set(channels) <= {c.value for c in FeedChannel}, channels


def test_an_UNOBSERVED_channel_reads_as_UNOBSERVED_not_as_a_VERDICT() -> None:
    """'We have never looked' is not a `ChannelState` and must not become one."""
    monitor = capture.FeedStalenessMonitor()

    assert monitor.state_of(SYMBOL, FeedChannel.POLL) == "unobserved"
    assert capture.UNOBSERVED not in {state.value for state in ChannelState}
    assert not monitor.table(), monitor.table()


def test_a_transition_carries_EVERY_INPUT_to_the_verdict_it_reports() -> None:
    """A verdict with its reasoning stripped cannot be recomputed from the journal."""
    monitor = capture.FeedStalenessMonitor()
    now = time.time()

    moved = monitor.observe(_report((FeedChannel.TICK, ChannelState.FRESH), now=now))

    fields = moved[0].fields()
    assert set(fields) == {
        "symbol",
        "channel",
        "from",
        "to",
        "excess_staleness_s",
        "threshold_s",
        "effective_lag_s",
        "venue_ts",
        "lag_provenance",
    }, sorted(fields)
    assert fields["symbol"] == SYMBOL, fields
    assert fields["channel"] == "tick", fields
    assert fields["from"] == "unobserved", fields
    assert fields["to"] == "fresh", fields
    assert fields["excess_staleness_s"] == f"{FRESH_EXCESS_S:.3f}", fields
    assert fields["threshold_s"] == f"{THRESHOLD_S:.3f}", fields
    assert fields["effective_lag_s"] == f"{DECLARED_LAG_S:.3f}", fields
    assert fields["venue_ts"] == f"{now - 1.0:.6f}", fields
    assert fields["lag_provenance"] == "vendor_declared", fields


def test_a_CANNOT_MEASURE_transition_reports_a_DASH_and_never_a_FABRICATED_ZERO() -> (
    None
):
    """An absent number renders as `-`; `0.000` would read as a measurement."""
    monitor = capture.FeedStalenessMonitor()

    moved = monitor.observe(_report((FeedChannel.POLL, ChannelState.CANNOT_MEASURE)))

    fields = moved[0].fields()
    assert fields["to"] == "cannot_measure", fields
    assert fields["excess_staleness_s"] == "-", fields
    assert fields["venue_ts"] == "-", fields
    assert fields["channel"] == "poll", fields


# --- the process object ----------------------------------------------------


def test_the_PROCESS_announces_START_then_its_TRANSITIONS_then_STOP(
    plane: _RecordingPlane2,
) -> None:
    """§12.10: each process writes its own events, including its own lifecycle."""
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), pin=False)

    reading = process.start()
    process.observe_freshness(
        _report(
            (FeedChannel.TICK, ChannelState.FRESH),
            (FeedChannel.POLL, ChannelState.STALE),
        )
    )
    process.close()

    assert plane.names() == [
        "process_start",
        "feed_staleness_transition",
        "feed_staleness_transition",
        "process_stop",
    ], plane.names()
    start = plane.fields_for("process_start")[0]
    assert start["pid"] == os.getpid(), start
    assert start["role"] == "capture", start
    assert start["pinned"] is False, "a test must never pin the runner"
    assert start["affinity_readers_agree"] is True, start
    # The announced mask is the KERNEL's, rendered the kernel's way — the reading
    # `start()` returned, not the set it hoped for.
    assert start["cores"] == capture.format_cpu_list(reading.mask), start
    assert reading.mask, "an empty mask would make the announcement vacuous"
    stop = plane.fields_for("process_stop")[0]
    assert stop["transitions"] == 2, stop
    assert stop["ticks_written"] == 0, stop
    assert plane.closes == 1, plane.closes


def test_on_tick_lands_a_REAL_TICK_in_the_INJECTED_RING(ring_name: str) -> None:
    """§12.7's sole shared-memory exception, driven end to end through the process."""
    plane = _RecordingPlane2()
    writer = price_ring.PriceRingWriter(ring_name, 8)
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), ring=writer, pin=False)
    reader = price_ring.PriceRingReader(ring_name)
    try:
        process.on_tick(7, 5432.25, 3.0, 1_700_000_000_123_456_789)

        ticks, dropped = reader.poll()
        assert dropped == 0, dropped
        assert len(ticks) == 1, ticks
        assert ticks[0].symbol_id == 7, ticks[0]
        assert ticks[0].price == 5432.25, ticks[0]
        assert ticks[0].venue_ts_ns == 1_700_000_000_123_456_789, ticks[0]
        assert process.ticks_written == 1, process.ticks_written
        # NO Plane-2 event per tick: §12.10 keeps per-tick chatter out of the log.
        assert plane.names() == [], plane.names()
    finally:
        reader.close()
        process.close()


def test_on_tick_with_NO_RING_is_a_NO_OP_rather_than_an_ERROR(
    plane: _RecordingPlane2,
) -> None:
    """A `CaptureProcess` with no ring is still a real process."""
    process = capture.CaptureProcess(plane2=cast(Plane2, plane), pin=False)

    process.on_tick(7, 5432.25, 3.0, 1_700_000_000_123_456_789)

    assert process.ticks_written == 0, process.ticks_written
    assert plane.names() == [], plane.names()
    assert process.service(0) == 0, "no publisher means nothing to service"
    assert process.refresh() == 0, "no publisher means nothing to refresh"


# --- the CLI ---------------------------------------------------------------


def test_main_with_NO_ARGS_REFUSES_and_names_the_MISSING_VENUE_SESSION(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A connect path written against a session never observed is an unmeasured
    claim, so the CLI says so instead of returning a number that reads as work."""
    code = capture.main([])

    captured = capsys.readouterr()
    assert code == 2, code
    # THE REASON, on the stream it actually uses.
    assert "no venue session exists on this node" in captured.err, captured.err
    assert "unmeasured claim" in captured.err, captured.err
    assert "--self-report" in captured.err, captured.err
    assert captured.out == "", captured.out


def test_the_SELF_REPORT_control_arm_reports_affinity_WITHOUT_setting_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--no-pin` is the CONTROL arm's invocation, and it is what keeps this test
    safe: the pinning arm belongs in a spawned child (`checks/check_core_map.py`),
    never in the process running the suite."""
    before = os.sched_getaffinity(0)

    code = capture.main(["--self-report", "--no-pin", "--hold-s", "0"])

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert f'"pid": {os.getpid()}' in captured.out, captured.out
    assert '"pinned": false' in captured.out, captured.out
    assert '"agree": true' in captured.out, captured.out
    assert os.sched_getaffinity(0) == before, "the CONTROL arm repinned the runner"
