"""ARC 055 / I1 ARC C1 — the can-fail suite for `nixrisk/stopwatch.py`.

Non-vacuity first (the shipped poll ratchets, breaches and enqueues), then the
properties stated as plants: a trail that loosens, a breach that re-fires, a
poll that reaches something expensive. Every control asserts the REASON — the
value, the count, the named condition — never a bare boolean (check contract
v2 rule 11).
"""
# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring

from __future__ import annotations

import dataclasses
import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.seam import (  # pylint: disable=wrong-import-position
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.stops import StopBook  # pylint: disable=wrong-import-position
from nixrisk.stopwatch import (  # pylint: disable=wrong-import-position
    RING_SYMBOL_CAP,
    BreachFiring,
    PriceRing,
    PriceRingFull,
    StopWatch,
)

SYM, TICK, FILL = "ES", 0.25, 5000.0
STOP_TICKS, TRAIL_TICKS = 8, 4
LEVEL = FILL - STOP_TICKS * TICK


def _order(cid: str, mode: StopMode = StopMode.FIXED) -> ProposedOrder:
    return ProposedOrder(
        strategy_id="t-stopwatch",
        client_order_id=cid,
        symbol=SYM,
        side=Side.LONG,
        qty=2,
        margin_per_contract=500.0,
        stop_ticks=STOP_TICKS,
        stop_mode=mode,
        signal_ts=time.time(),
    )


@pytest.fixture
def rig() -> tuple[PriceRing, StopBook, StopWatch]:
    book = StopBook({SYM: TICK})
    ring = PriceRing()
    return ring, book, StopWatch(ring, book)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_POLL_RATCHETS_a_trailing_stop_toward_price(rig) -> None:
    ring, book, watch = rig
    armed = book.arm(FILL, _order("a", StopMode.TRAILING), trail_ticks=TRAIL_TICKS)
    assert armed.level == LEVEL, armed

    ring.publish(SYM, FILL + 3.0)
    assert watch.poll(1) == 0, "a favourable move must not breach"
    assert book.get("a").level == FILL + 3.0 - TRAIL_TICKS * TICK
    assert book.get("a").activated is True
    assert watch.maintained == 1, watch.maintained


def test_the_POLL_ENQUEUES_a_breach_and_marks_the_position(rig) -> None:
    ring, book, watch = rig
    book.arm(FILL, _order("a"))
    ring.publish(SYM, LEVEL - TICK)
    assert watch.poll(7) == 1
    fired = watch.drain()
    assert len(fired) == 1
    assert fired[0] == BreachFiring(
        client_order_id="a",
        symbol=SYM,
        side=Side.LONG,
        level=LEVEL,
        price=LEVEL - TICK,
        tick=7,
    ), fired[0]
    assert watch.in_flight() == ("a",)
    assert watch.drain() == (), "a drained firing must not be handed over twice"


def test_a_price_ABOVE_the_stop_does_NOT_breach(rig) -> None:
    ring, book, watch = rig
    book.arm(FILL, _order("a"))
    ring.publish(SYM, LEVEL + 5.0)
    assert watch.poll(1) == 0
    assert watch.breaches == 0 and watch.drain() == ()


def test_a_price_EXACTLY_AT_the_level_IS_a_breach(rig) -> None:
    """§4: a trade that prints exactly at the stop has hit it."""
    ring, book, watch = rig
    book.arm(FILL, _order("a"))
    ring.publish(SYM, LEVEL)
    assert watch.poll(1) == 1, "an inclusive breach is the spec's rule"


# --------------------------------------------------------------------------
# THE PROPERTIES, AS PLANTS
# --------------------------------------------------------------------------


def test_FIRE_ONCE_a_breached_position_does_not_refire_across_many_ticks(rig) -> None:
    ring, book, watch = rig
    book.arm(FILL, _order("a"))
    ring.publish(SYM, LEVEL - TICK)
    assert watch.poll(1) == 1
    watch.drain()
    for tick in range(2, 60):
        ring.publish(SYM, LEVEL - TICK * tick)
        assert watch.poll(tick) == 0, f"tick {tick} re-fired a flatten-in-flight stop"
    assert watch.breaches == 1, watch.breaches
    assert watch.suppressed == 58, watch.suppressed
    assert watch.drain() == ()


def test_the_TRAIL_NEVER_LOOSENS_on_a_descending_walk(rig) -> None:
    """§4:190-196 — the ratchet never gives ground back."""
    ring, book, watch = rig
    book.arm(FILL, _order("a", StopMode.TRAILING), trail_ticks=TRAIL_TICKS)
    ring.publish(SYM, FILL + 3.0)
    watch.poll(1)
    trailed = book.get("a").level
    assert trailed > LEVEL, (trailed, LEVEL)

    levels = []
    for step in range(1, 10):
        price = FILL + 3.0 - step * TICK
        if price <= trailed:
            break
        ring.publish(SYM, price)
        watch.poll(10 + step)
        levels.append(book.get("a").level)
    assert len(levels) >= 2, levels
    assert levels == [trailed] * len(levels), levels
    assert book.get("a").high_water == FILL + 3.0, book.get("a").high_water
    assert watch.breaches == 0, "a walk above the trail must not breach"


def test_forget_RELEASES_the_mark_so_a_reused_id_can_fire_again(rig) -> None:
    ring, book, watch = rig
    book.arm(FILL, _order("a"))
    ring.publish(SYM, LEVEL - TICK)
    watch.poll(1)
    watch.drain()
    released = watch.forget("a")
    assert released is not None and released.client_order_id == "a"
    assert watch.in_flight() == ()
    assert watch.forget("never-breached") is None, "sparse book: silent on unknown"


def test_a_FIXED_stop_is_never_moved_by_the_poll(rig) -> None:
    """§4:188 — fixed is anchored once and static forever."""
    ring, book, watch = rig
    book.arm(FILL, _order("a"))
    for step in range(1, 20):
        ring.publish(SYM, FILL + step)
        watch.poll(step)
    assert book.get("a").level == LEVEL, book.get("a")
    assert watch.maintained == 0, watch.maintained


# --------------------------------------------------------------------------
# THE RING
# --------------------------------------------------------------------------


def test_the_RING_REFUSES_a_sixth_symbol_rather_than_evicting_one() -> None:
    ring = PriceRing()
    for i in range(RING_SYMBOL_CAP):
        ring.publish(f"S{i}", 100.0 + i)
    with pytest.raises(PriceRingFull) as exc:
        ring.publish("SIXTH", 1.0)
    assert "SIXTH" in str(exc.value) and str(RING_SYMBOL_CAP) in str(exc.value)
    assert len(ring.symbols()) == RING_SYMBOL_CAP
    assert ring.head("S0") is not None, "no existing symbol may be evicted"


def test_the_RING_head_is_the_NEWEST_price_and_seq_is_monotonic() -> None:
    ring = PriceRing()
    first = ring.publish(SYM, 1.0)
    second = ring.publish(SYM, 2.0)
    assert second.seq > first.seq
    assert ring.head(SYM) == second
    assert ring.head("NOPE") is None
    assert ring.published() == 2


# --------------------------------------------------------------------------
# THE STRUCTURAL GUARANTEES
# --------------------------------------------------------------------------


def test_the_WATCH_HOLDS_NO_BROKER_NO_SINK_AND_NO_CLOCK() -> None:
    """It cannot send, log or stamp — a property of the type, not a discipline."""
    watch = StopWatch(PriceRing(), StopBook({SYM: TICK}))
    held = [type(v).__module__ for v in vars(watch).values()]
    assert not [m for m in held if m.startswith("nixrisk.flatten")], held
    assert not hasattr(watch, "_broker") and not hasattr(watch, "_clock"), vars(watch)
    assert not hasattr(watch, "_plane1"), vars(watch)


def test_a_BreachFiring_carries_NO_TIMESTAMP() -> None:
    """A clock read on the hot path is the thing ARM 3c of the I9 gate refuses."""
    fields = {f.name for f in dataclasses.fields(BreachFiring)}
    assert not [f for f in fields if "ts" in f or "time" in f], fields
