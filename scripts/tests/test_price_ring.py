"""ARC 026 — the properties `scripts/nixbus/price_ring.py` claims (§12.7's exception).

What each test proves:

* **Round-trip fidelity.** `price`, `size`, `venue_ts_ns` and `symbol_id` come
  back exactly as published, in publication order, with contiguous sequence
  numbers. `venue_ts_ns` is an integer on the wire, so a nanosecond stamp does
  not acquire float rounding on the way through.
* **Overrun is COUNTED, never absorbed.** Publishing `capacity + N` recovers
  exactly `capacity` ticks and exactly `N` drops, and `poll` hands the drop count
  back SEPARATELY from the ticks — a consumer cannot take the ticks without being
  handed the gap.
* **A non-power-of-two capacity is refused, naming the capacity**, because the
  reader's mask arithmetic and the writer's would disagree and the symptom would
  be impossible prices rather than an error.
* **STRICTLY ONE WRITER.** A second writer while the incumbent is LIVE is refused
  with the incumbent's `pid=` in the message; a DEAD incumbent's segment is
  reclaimed instead, which is the third state a two-state check gets wrong.
* **A foreign segment is refused naming magic/version**, so a reader can never
  interpret arbitrary bytes as prices.
* **`segment_exists` is KERNEL state** — true while the segment is alive in
  `/dev/shm`, false after `close(unlink=True)`.
* **`from_start` is the difference between a replay and a tail**: a reader
  attached with `from_start=True` sees ticks published before it existed; the
  default reader does not, and both are explicit rather than incidental.

Every segment name carries `os.getpid()` and a random suffix, and every segment
is unlinked in a fixture `finally`, so no `/dev/shm` garbage survives a run and
no test can collide with the production `nix_price_ring`.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the fixtures are reused by design; the sys.path
# bootstrap is shared with the sibling suites. Each deliberate.

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Iterator
from multiprocessing import shared_memory
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixbus import price_ring  # pylint: disable=wrong-import-position
from nixbus.price_ring import (  # pylint: disable=wrong-import-position
    PriceRingError,
    PriceRingReader,
    PriceRingWriter,
)

#: A capacity small enough that overrun is reachable in a few publishes and still
#: a power of two, which the writer requires.
SMALL = 8

#: One tick, chosen so every field is exactly representable and distinguishable:
#: a nanosecond stamp too large for a float to hold without loss, a price with a
#: fractional tick, and a size that is not the price.
VENUE_TS_NS = 1_700_000_000_123_456_789
PRICE = 5432.25
SIZE = 3.0
SYMBOL_ID = 7


def _purge(name: str) -> None:
    """Unlink a segment if it still exists. Never raises — this is teardown."""
    try:
        stale = shared_memory.SharedMemory(name=name, create=False, track=False)
    except OSError, ValueError:
        return
    try:
        stale.unlink()
    except FileNotFoundError, OSError:
        pass
    finally:
        stale.close()


def _stamp_writer_pid(segment: str, pid: int) -> None:
    """Rewrite a live segment's header so it names `pid` as its writer.

    The plant for the abandoned-segment state: PID 0 is never a live process, so
    a segment carrying it is exactly what a crashed `capture.py` leaves behind.
    The header is rewritten through the module's OWN struct, so a change to the
    layout breaks this plant loudly instead of leaving it writing at a stale
    offset.
    """
    # pylint: disable=protected-access
    remains = shared_memory.SharedMemory(name=segment, create=False, track=False)
    try:
        price_ring._HEADER.pack_into(
            remains.buf,
            0,
            price_ring._MAGIC,
            1,
            SMALL,
            price_ring.SLOT_SIZE,
            pid,
            0,
            0,
        )
    finally:
        remains.close()


@pytest.fixture
def segments() -> Iterator[list[str]]:
    """Hands out unique segment names and unlinks every one at teardown."""
    names: list[str] = []
    try:
        yield names
    finally:
        for name in names:
            _purge(name)


@pytest.fixture
def name(segments: list[str]) -> str:
    """One unique segment name, registered for teardown."""
    unique = f"nix_test_ring_{os.getpid()}_{secrets.token_hex(4)}"
    segments.append(unique)
    return unique


@pytest.fixture
def closing() -> Iterator[list[PriceRingWriter | PriceRingReader]]:
    """Every writer and reader a test opens is detached here, even on failure."""
    opened: list[PriceRingWriter | PriceRingReader] = []
    try:
        yield opened
    finally:
        for item in reversed(opened):
            item.close()


# --- round-trip ------------------------------------------------------------


def test_a_published_TICK_round_trips_FIELD_FOR_FIELD_and_IN_ORDER(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """Prices only, and every field of a price, preserved exactly."""
    writer = PriceRingWriter(name, SMALL)
    closing.append(writer)
    reader = PriceRingReader(name)
    closing.append(reader)

    for offset in range(3):
        writer.publish(SYMBOL_ID + offset, PRICE + offset, SIZE, VENUE_TS_NS + offset)

    ticks, dropped = reader.poll()

    assert dropped == 0, f"{dropped} drop(s) on a ring that never wrapped"
    assert len(ticks) == 3, ticks
    assert [t.seq for t in ticks] == [0, 1, 2], [t.seq for t in ticks]
    assert [t.symbol_id for t in ticks] == [7, 8, 9], ticks
    assert [t.price for t in ticks] == [PRICE, PRICE + 1, PRICE + 2], ticks
    assert [t.size for t in ticks] == [SIZE] * 3, ticks
    # The integer nanosecond stamp is the one a float would have rounded.
    assert [t.venue_ts_ns for t in ticks] == [
        VENUE_TS_NS,
        VENUE_TS_NS + 1,
        VENUE_TS_NS + 2,
    ], ticks
    assert writer.write_seq == 3, writer.write_seq
    assert writer.published == 3, writer.published


def test_an_OVERRUN_reports_EXACTLY_the_ticks_kept_and_EXACTLY_the_ticks_LOST(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """A ring that dropped silently would be worse than useless on the hot path."""
    overrun = 3
    writer = PriceRingWriter(name, SMALL)
    closing.append(writer)
    reader = PriceRingReader(name, from_start=True)
    closing.append(reader)

    for seq in range(SMALL + overrun):
        writer.publish(SYMBOL_ID, PRICE + seq, SIZE, VENUE_TS_NS + seq)

    ticks, dropped = reader.poll()

    assert len(ticks) == SMALL, f"recovered {len(ticks)}, capacity is {SMALL}"
    assert dropped == overrun, f"reported {dropped} drop(s), lost {overrun}"
    # The drop count is returned SEPARATELY: it is not len(ticks) arithmetic.
    assert reader.dropped == overrun, reader.dropped
    # And what survived is the TAIL — the oldest ticks are the ones recycled.
    assert [t.seq for t in ticks] == list(range(overrun, SMALL + overrun)), ticks
    assert ticks[0].price == PRICE + overrun, ticks[0]


def test_a_SECOND_poll_after_an_overrun_reports_ZERO_further_drops(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """The gap is reported once, per call — never re-reported as a running total."""
    writer = PriceRingWriter(name, SMALL)
    closing.append(writer)
    reader = PriceRingReader(name, from_start=True)
    closing.append(reader)
    for seq in range(SMALL + 2):
        writer.publish(SYMBOL_ID, PRICE, SIZE, VENUE_TS_NS + seq)
    _, first = reader.poll()
    assert first == 2, first

    ticks, second = reader.poll()

    assert not ticks, f"a second poll re-delivered {len(ticks)} tick(s)"
    assert second == 0, f"the same {second} drop(s) were reported twice"


# --- refusals, each naming its reason --------------------------------------


@pytest.mark.parametrize("capacity", [7, 0, 1, 100])
def test_a_NON_POWER_OF_TWO_capacity_is_refused_NAMING_the_capacity(
    name: str, capacity: int
) -> None:
    """The mask arithmetic requires it; the symptom otherwise is a bad price."""
    with pytest.raises(PriceRingError, match=f"capacity {capacity} is not a power"):
        PriceRingWriter(name, capacity)
    assert not price_ring.segment_exists(name), "a refused writer created a segment"


def test_a_SECOND_WRITER_over_a_LIVE_one_is_REFUSED_naming_the_incumbent_PID(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """§12.7's *strictly one writer by construction*, held against this process.

    The incumbent here is THIS process, which is the case a naive check waves
    through: a second `PriceRingWriter` on one ring is the same violation whoever
    opened it.
    """
    incumbent = PriceRingWriter(name, SMALL)
    closing.append(incumbent)

    with pytest.raises(PriceRingError, match="STRICTLY ONE WRITER") as refusal:
        PriceRingWriter(name, SMALL)

    # THE REASON: the incumbent is NAMED, so an operator knows who holds it.
    assert f"pid={os.getpid()}" in str(refusal.value), str(refusal.value)
    assert repr(name) in str(refusal.value), str(refusal.value)
    # Unplant: the incumbent is untouched and still the writer.
    assert incumbent.publish(SYMBOL_ID, PRICE, SIZE, VENUE_TS_NS) == 0


def test_a_reader_on_a_segment_that_is_NOT_A_PRICE_RING_is_REFUSED(
    segments: list[str],
) -> None:
    """Plant: a real shared segment of zeros. Unlinked in the `finally`.

    A reader that accepted this would present zeroed bytes as prices, which is
    the failure this header exists to make impossible.
    """
    foreign = f"nix_test_foreign_{os.getpid()}_{secrets.token_hex(4)}"
    segments.append(foreign)
    segment = shared_memory.SharedMemory(
        name=foreign, create=True, size=4096, track=False
    )
    try:
        segment.buf[:] = bytes(len(segment.buf))

        with pytest.raises(PriceRingError, match="is not a v1 price ring") as refusal:
            PriceRingReader(foreign)

        # THE REASON: which field disqualified the segment.
        assert "magic=" in str(refusal.value), str(refusal.value)
        assert "version=0" in str(refusal.value), str(refusal.value)
        assert "slot_size=0" in str(refusal.value), str(refusal.value)
    finally:
        segment.close()


def test_a_reader_on_a_MISSING_segment_is_REFUSED_naming_the_segment(
    name: str,
) -> None:
    """Nothing to attach to is a named condition, not an obscure OSError."""
    assert not price_ring.segment_exists(name)
    with pytest.raises(PriceRingError, match=f"shared segment {name!r}"):
        PriceRingReader(name)


# --- kernel state, and what a reader is entitled to see --------------------


def test_segment_exists_tracks_DEV_SHM_and_flips_FALSE_after_unlink(
    name: str,
) -> None:
    """Kernel state, read from `/dev/shm`, not this module's own bookkeeping."""
    assert not price_ring.segment_exists(name), "the plant is not clean"
    writer = PriceRingWriter(name, SMALL)
    try:
        assert price_ring.segment_exists(name), "no segment appeared in /dev/shm"
        assert (price_ring.SHM_DIR / name).exists(), "the module's path disagrees"
    finally:
        writer.close(unlink=True)

    assert not price_ring.segment_exists(name), "the segment outlived its unlink"


def test_a_DEAD_writers_segment_is_RECLAIMED_rather_than_blocking_forever(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """The third state: a crashed capture.py must not disable the firehose.

    The plant writes a header naming PID 0 — never a live process — into a real
    segment, which is the on-disk remains of a writer that died. A two-state
    check ('is there a segment?') refuses here and leaves a condition with no
    defined exit.
    """
    abandoned = PriceRingWriter(name, SMALL)
    abandoned.close(unlink=False)
    _stamp_writer_pid(name, 0)
    assert price_ring.segment_exists(name), "the plant did not survive"

    successor = PriceRingWriter(name, SMALL)
    closing.append(successor)

    assert successor.publish(SYMBOL_ID, PRICE, SIZE, VENUE_TS_NS) == 0
    reader = PriceRingReader(name, from_start=True)
    closing.append(reader)
    ticks, dropped = reader.poll()
    assert dropped == 0, dropped
    assert [t.price for t in ticks] == [PRICE], ticks


def test_from_start_REPLAYS_and_the_DEFAULT_reader_TAILS(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """Two readers, one segment, two entitlements — both explicit."""
    writer = PriceRingWriter(name, SMALL)
    closing.append(writer)
    writer.publish(SYMBOL_ID, PRICE, SIZE, VENUE_TS_NS)
    writer.publish(SYMBOL_ID, PRICE + 1, SIZE, VENUE_TS_NS + 1)

    replay = PriceRingReader(name, from_start=True)
    closing.append(replay)
    tail = PriceRingReader(name)
    closing.append(tail)

    replayed, replay_dropped = replay.poll()
    tailed, tail_dropped = tail.poll()

    assert [t.price for t in replayed] == [PRICE, PRICE + 1], replayed
    assert replay_dropped == 0, replay_dropped
    assert not tailed, "the default reader saw ticks published before it attached"
    assert tail_dropped == 0, tail_dropped
    # And the tailing reader IS live: the next tick reaches it.
    writer.publish(SYMBOL_ID, PRICE + 2, SIZE, VENUE_TS_NS + 2)
    later, _ = tail.poll()
    assert [t.price for t in later] == [PRICE + 2], later


def test_poll_HONOURS_max_items_and_leaves_the_rest_for_the_next_call(
    name: str, closing: list[PriceRingWriter | PriceRingReader]
) -> None:
    """A bounded drain: the hot path must never be forced into an unbounded loop."""
    writer = PriceRingWriter(name, SMALL)
    closing.append(writer)
    reader = PriceRingReader(name)
    closing.append(reader)
    for seq in range(4):
        writer.publish(SYMBOL_ID, PRICE + seq, SIZE, VENUE_TS_NS + seq)

    first, _ = reader.poll(max_items=2)
    second, _ = reader.poll(max_items=2)

    assert [t.seq for t in first] == [0, 1], first
    assert [t.seq for t in second] == [2, 3], second


# --- the two review findings, each pinned by a test -------------------------


def test_a_FOREIGN_segment_is_NEVER_UNLINKED_and_the_refusal_says_so(
    name: str,
) -> None:
    """The delete path may only delete something this module IDENTIFIED.

    Found in review, ARC 026: `_incumbent` returned `(0, False)` for a bad magic
    exactly as it did for a dead writer, so `_claim_segment` unlinked it. A
    `PriceRingWriter` starting on a name occupied by some other program's shared
    memory would have silently destroyed it. This is the one path in the module
    that deletes data, and it is now the one path that refuses what it cannot
    name.
    """
    foreign = shared_memory.SharedMemory(name=name, create=True, size=512, track=False)
    try:
        with pytest.raises(PriceRingError, match="is NOT a v1 price ring"):
            PriceRingWriter(name, SMALL)
        assert price_ring.segment_exists(name), "the foreign segment was destroyed"
        refusal = price_ring.unlink_segment(name)
        assert "refusing to unlink shared memory this module did not create" in refusal
        assert price_ring.segment_exists(name), "unlink_segment destroyed it anyway"
    finally:
        foreign.close()
        foreign.unlink()


def test_unlink_segment_RECLAIMS_our_own_and_is_SILENT_on_an_absent_one(
    name: str,
) -> None:
    """The sanctioned teardown path: it removes a real ring and no-ops on nothing."""
    writer = PriceRingWriter(name, SMALL)
    writer.close(unlink=False)
    assert price_ring.segment_exists(name)

    assert price_ring.unlink_segment(name) == ""
    assert not price_ring.segment_exists(name)
    assert price_ring.unlink_segment(name) == "", "an absent segment is not an error"
