"""ARC 039 / sub-agent A — §5:322's event loop, driven IN PROCESS.

The library-level half. `checks/` owns the out-of-process gate (sub-agent B):
anything about a real pid, `/proc/<pid>/task`, a signal, or a heartbeat file read
from another process is measured THERE and not here. What belongs here is the
loop's own behaviour when driven directly — the tick, the beat's placement inside
it, the live registry, the sender thread's separateness, and the stop.

The split is stated so the boundary survives the next author (doctrine C.9).

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen risk spec,
unless another document is named on the same line.

EVERY CONTROL READS A REASON (check contract v2 §11)
-----------------------------------------------------
No assertion below is satisfied by an exit code, by a bare `True`, or by "it did
not raise". Where the loop refuses, the control matches the REASON text on the
coordinate it refuses under; where the loop accepts, the control reads the field
that changed. `LimiterLoop.take_in_flight` returns `(accepted, reason)` for
exactly this purpose — a refusal that did not name the `client_order_id` already
holding the lock would tell an operator that something is in flight without
telling them what.

THE FALSIFIERS ARE REAL, NOT RHETORICAL
----------------------------------------
Three of the properties here are ORDERING or OWNERSHIP claims, and an assertion
no falsifier can break measures nothing. So:

  * the single-thread rule is falsified by a real second `threading.Thread`
    calling `tick`, and the refusal must name both idents;
  * "the heartbeat is published by the tick and ONLY by the tick" is falsified
    twice — from a second thread (the `threading.Timer` shape that makes the
    Sentinel blind, §12.1:604) and from the loop's own thread outside a tick;
  * the bounded drain is falsified by submitting far more work than one tick may
    take and counting what the handler actually saw.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# pylint: disable=use-implicit-booleaness-not-comparison
# C1803: `x == ()` is the assertion here — "exactly nothing is held" is a
# different claim from "nothing truthy is held", and the failure message shows
# WHAT was there. The same reasoning test_recovery.py records at its own header.
# invalid-name: the test names are sentences and SHOUT the property.
# protected-access: `_publish_heartbeat` is exactly what a falsifier must reach —
# the whole claim is that it refuses every caller but the tick, and a falsifier
# that could only use the public surface could not try the forbidden call.

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error
from nixrisk.loop import (
    TICKS_PER_HEARTBEAT,
    LimiterLoop,
    LoopError,
    heartbeat_interval_from_config,
    tick_interval_for,
)
from nixrisk.recovery import StrategyRegistry
from nixsentinel.heartbeat import (
    DEFAULT_HEARTBEAT_NAME,
    HeartbeatFile,
    HeartbeatPublisher,
)

#: scripts/tests/ -> ~/nix. Derived from this file's own location, never typed as
#: an absolute path (`docs/debug.md` §7.4: the tree moves and a literal root rots).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Fast enough that a control finishes in milliseconds, slow enough that a tick
#: is not the dominant cost. Never the shipped §12A:832 value — a test that ran
#: on the production cadence would be measuring `time.sleep`.
FAST_HEARTBEAT_S = 0.02


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    (tmp_path / "rt").mkdir()
    return tmp_path / "rt"


def build(runtime: Path, **kwargs: Any) -> LimiterLoop:
    """A loop over a real `HeartbeatPublisher` writing into `runtime`.

    A REAL publisher, not a double: the property under test is that the beat
    reaches the file the Sentinel opens, and a recording double would prove that
    the loop called something.
    """
    publisher = HeartbeatPublisher(runtime / DEFAULT_HEARTBEAT_NAME)
    params: dict[str, Any] = {
        "heartbeat": publisher,
        "heartbeat_interval_s": FAST_HEARTBEAT_S,
        "tick_interval_s": FAST_HEARTBEAT_S / 4,
        # ARC 040. REQUIRED and deliberately without a constructor default: a
        # Limiter that invented its own §12A:831 T would deny GOs a strategy
        # still believes are live, so §4:210-212's breaker has to be stated by
        # whoever builds the loop. The default here is a TEST cadence, large
        # against this file's tick so no test in the file trips the breaker by
        # accident; the tests that exercise the breaker state their own.
        "go_timeout_s": FAST_HEARTBEAT_S * 100,
    }
    params.update(kwargs)
    return LimiterLoop(**params)


# ---------------------------------------------------------------------------
# The tick counter — §5:322's loop actually advancing
# ---------------------------------------------------------------------------


def test_the_tick_counter_advances_once_per_tick(runtime: Path) -> None:
    loop = build(runtime)
    assert loop.tick_count == 0
    assert loop.tick() == 1
    assert loop.tick() == 2
    assert loop.tick_count == 2, "the loop's own counter must be the one that moved"


def test_run_stops_at_max_ticks_and_says_so(runtime: Path) -> None:
    loop = build(runtime, max_ticks=5)
    stop = loop.run()
    assert stop.ticks == 5, f"ran {stop.ticks} ticks, expected exactly 5"
    assert "--max-ticks=5" in stop.reason, stop.reason
    assert "safety stop fired, not a fault" in stop.reason, stop.reason


# ---------------------------------------------------------------------------
# §12.1:604 — the heartbeat is published BY the tick and ONLY by the tick
# ---------------------------------------------------------------------------


def test_the_tick_publishes_the_heartbeat_into_the_file_the_sentinel_reads(
    runtime: Path,
) -> None:
    loop = build(runtime)
    assert HeartbeatFile(runtime / DEFAULT_HEARTBEAT_NAME).read() is None, (
        "absence before the first tick is the Sentinel's cold-boot reading and "
        "must not be manufactured by construction"
    )
    loop.tick()
    beat = HeartbeatFile(runtime / DEFAULT_HEARTBEAT_NAME).read()
    assert beat is not None, "one tick must have produced one beat on disk"
    assert beat.seq == 1
    assert loop.heartbeats_published == 1
    assert loop.heartbeat_seq == beat.seq, (
        "the loop must report the PUBLISHER's seq, not a parallel counter that "
        "could disagree with the file the Sentinel opens"
    )


def test_the_beat_keeps_the_interval_and_not_the_tick_rate(runtime: Path) -> None:
    # Ten ticks inside one heartbeat interval must produce exactly one beat:
    # the cadence is the loop's own monotonic clock, not "once per tick".
    clock = {"now": 1000.0}
    loop = build(
        runtime,
        heartbeat_interval_s=1.0,
        tick_interval_s=0.1,
        monotonic=lambda: clock["now"],
    )
    for _ in range(10):
        loop.tick()
        clock["now"] += 0.1
    assert loop.heartbeats_published == 1, (
        f"{loop.heartbeats_published} beats in one interval — the beat is "
        "following the tick rate, not §12A:832's interval"
    )
    clock["now"] += 1.0
    loop.tick()
    assert loop.heartbeats_published == 2


def test_a_second_thread_may_not_publish_the_heartbeat(runtime: Path) -> None:
    # THE FALSIFIER for the §12.1 catastrophe: a beat published off the loop
    # advances while the loop is wedged, the Sentinel reads a climbing seq, and
    # never fires its emergency flatten — with positions open.
    loop = build(runtime)
    loop.tick()
    caught: list[BaseException] = []

    def _timer_shaped_publisher() -> None:
        try:
            loop._publish_heartbeat()
        except BaseException as exc:  # pylint: disable=broad-except  # noqa: BLE001
            caught.append(exc)

    thread = threading.Thread(target=_timer_shaped_publisher)
    thread.start()
    thread.join(timeout=5.0)

    assert len(caught) == 1, "the off-loop publish must have been refused"
    refusal = caught[0]
    assert isinstance(refusal, LoopError)
    text = str(refusal)
    assert "only the loop thread" in text, text
    assert "§12.1:604" in text, text
    assert "never fires its emergency flatten" in text, text
    assert str(loop._loop_ident) in text, "the refusal must name the owning thread"
    assert loop.heartbeats_published == 1, "the refused beat must not have counted"


def test_the_loop_thread_may_not_publish_outside_a_tick(runtime: Path) -> None:
    loop = build(runtime)
    loop.tick()
    with pytest.raises(LoopError) as excinfo:
        loop._publish_heartbeat()
    text = str(excinfo.value)
    assert "from outside a tick" in text, text
    assert "seq must mean *a tick completed*" in text, text
    assert loop.heartbeats_published == 1


def test_no_beat_may_precede_the_loop(runtime: Path) -> None:
    loop = build(runtime)
    with pytest.raises(LoopError) as excinfo:
        loop._publish_heartbeat()
    assert "before the loop has started" in str(excinfo.value), str(excinfo.value)


def test_every_beat_of_a_full_run_came_from_the_one_loop_thread(runtime: Path) -> None:
    loop = build(runtime, max_ticks=8)
    stop = loop.run()
    assert stop.heartbeats >= 1
    assert loop.heartbeat_publisher_idents == {loop._loop_ident}, (
        f"beats were published by {loop.heartbeat_publisher_idents}, and the "
        f"loop thread is {loop._loop_ident} — a second publisher is the §12.1 "
        "catastrophe named in nixrisk/loop.py's docstring"
    )


def test_the_beat_is_published_last_so_seq_means_a_tick_completed(
    runtime: Path,
) -> None:
    # The handler runs inside the tick and BEFORE the beat. If the beat were
    # published first, the seq visible to a handler would already include this
    # tick's beat; it must not.
    seen: list[int] = []
    loop = build(runtime)
    loop.attach(handler=lambda item: seen.append(loop.heartbeat_seq))
    loop.submit("work")
    loop.tick()
    assert seen == [0], (
        f"the handler saw seq {seen} — the beat was published before the tick's "
        "work, so a published seq would mean 'the loop ENTERED a tick'"
    )
    assert loop.heartbeat_seq == 1


# ---------------------------------------------------------------------------
# §4:208-209 / §3:140 — the one-in-flight lock as the LOOP's live state
# ---------------------------------------------------------------------------


def test_the_registry_is_the_loops_own_attribute_and_it_mutates(runtime: Path) -> None:
    registry = StrategyRegistry()
    loop = build(runtime, registry=registry)
    assert loop.registry is registry, (
        "the loop must HOLD the registry, not build one per call — a per-call "
        "fixture proves the class and proves nothing about the process"
    )
    loop.admit("alpha", now=1.0)
    assert registry.is_registered("alpha"), (
        "the loop mutated something other than the registry it was handed"
    )
    assert loop.registry.registered() == ("alpha",)


def test_a_second_take_for_one_strategy_is_refused_naming_the_holder(
    runtime: Path,
) -> None:
    loop = build(runtime)
    loop.admit("alpha", now=1.0)

    accepted, reason = loop.take_in_flight("alpha", "coid-1")
    assert accepted, reason
    assert "coid-1" in reason and "§4:208" in reason, reason

    accepted, reason = loop.take_in_flight("alpha", "coid-2")
    assert not accepted, "§4:208-209 allows ONE in-flight action per strategy"
    assert "coid-1" in reason, f"the refusal must name the HOLDER: {reason}"
    assert "§4:210" in reason, f"the port's own citation must survive: {reason}"
    assert "§3:140" in reason, f"the PHASE A coordinate must be named: {reason}"
    assert "one-in-flight-per-strategy" in reason, reason
    assert loop.in_flight_holders() == (("alpha", "coid-1"),), (
        "the refused take must not have re-pointed the lock"
    )


def test_a_different_strategy_may_hold_its_own_lock(runtime: Path) -> None:
    loop = build(runtime)
    loop.admit("alpha", now=1.0)
    loop.admit("beta", now=1.0)
    assert loop.take_in_flight("alpha", "coid-a")[0]
    accepted, reason = loop.take_in_flight("beta", "coid-b")
    assert accepted, (
        f"the lock is PER STRATEGY (§4:208); beta was refused for alpha: {reason}"
    )
    assert set(loop.in_flight_holders()) == {("alpha", "coid-a"), ("beta", "coid-b")}


def test_slots_are_derived_from_the_live_registry_and_are_reusable(
    runtime: Path,
) -> None:
    loop = build(runtime)
    assert loop.admit("alpha", now=1.0).slot == 0
    assert loop.admit("beta", now=1.0).slot == 1
    torn_down = loop.registry.force_deregister("alpha")
    assert torn_down.freed_slot == 0, torn_down.reason
    assert loop.admit("gamma", now=1.0).slot == 0, (
        "a freed slot must be reusable — a monotonic counter would leak the "
        "§4:266-268 slot space one death at a time"
    )


def test_the_beat_hints_at_locks_held_because_this_arc_has_no_positions(
    runtime: Path,
) -> None:
    clock = {"now": 500.0}
    loop = build(
        runtime,
        heartbeat_interval_s=1.0,
        tick_interval_s=0.1,
        monotonic=lambda: clock["now"],
    )
    loop.admit("alpha", now=1.0)
    loop.tick()
    first = HeartbeatFile(runtime / DEFAULT_HEARTBEAT_NAME).read()
    assert first is not None and first.positions_open == 0, first
    loop.take_in_flight("alpha", "coid-1")
    clock["now"] += 1.0
    loop.tick()
    beat = HeartbeatFile(runtime / DEFAULT_HEARTBEAT_NAME).read()
    assert beat is not None and beat.positions_open == 1, (
        "§12.1:604 asks for *positions possibly open*; an in-flight order is the "
        "only thing this arc holds that could become one"
    )


# ---------------------------------------------------------------------------
# §5:322 — one thread ticks, and a second one is refused
# ---------------------------------------------------------------------------


def test_a_second_thread_may_not_tick_the_loop(runtime: Path) -> None:
    loop = build(runtime)
    loop.tick()
    caught: list[BaseException] = []

    def _intruder() -> None:
        try:
            loop.tick()
        except BaseException as exc:  # pylint: disable=broad-except  # noqa: BLE001
            caught.append(exc)

    thread = threading.Thread(target=_intruder)
    thread.start()
    thread.join(timeout=5.0)

    assert len(caught) == 1, "the second ticking thread must have been refused"
    text = str(caught[0])
    assert isinstance(caught[0], LoopError)
    assert "§5:322" in text and "SINGLE-THREADED" in text, text
    assert "eliminates" in text and "BY CONSTRUCTION" in text, text
    assert str(loop._loop_ident) in text, "the refusal must name the owning thread"
    assert loop.tick_count == 1, "the refused tick must not have advanced the counter"


def test_a_second_thread_may_not_mutate_the_live_registry(runtime: Path) -> None:
    loop = build(runtime)
    loop.tick()
    loop.admit("alpha", now=1.0)
    caught: list[BaseException] = []

    def _intruder() -> None:
        try:
            loop.take_in_flight("alpha", "coid-x")
        except BaseException as exc:  # pylint: disable=broad-except  # noqa: BLE001
            caught.append(exc)

    thread = threading.Thread(target=_intruder)
    thread.start()
    thread.join(timeout=5.0)

    assert len(caught) == 1
    text = str(caught[0])
    assert "'take_in_flight' called from thread" in text, text
    assert "restores the race the design removed" in text, text
    assert loop.in_flight_holders() == (), "the refused take must not have landed"


# ---------------------------------------------------------------------------
# §5:323 — the low-priority sender thread is a real, separate OS thread
# ---------------------------------------------------------------------------


def test_the_sender_is_a_separate_os_thread_and_the_loop_is_not_niced_with_it(
    runtime: Path,
) -> None:
    loop = build(runtime, max_ticks=1)
    stop = loop.run()
    assert loop.sender.native_id is not None, "the sender never reached its serve loop"
    assert loop.sender.native_id != loop._loop_native_id, (
        f"the sender reported native id {loop.sender.native_id}, the same as the "
        "loop's — §5:323 requires a genuinely separate OS thread"
    )
    assert loop.sender.priority_error == "", loop.sender.priority_error
    assert loop.sender.nice_effective is not None and loop.sender.nice_effective > 0, (
        f"the sender's effective nice is {loop.sender.nice_effective}; §5:323 "
        "calls it a LOW-priority thread and a positive nice is what makes it one"
    )
    assert stop.faults == (), (
        f"starting the sender produced faults: {stop.faults} — the loop's own "
        "nice moved, or the priority could not be set"
    )
    assert stop.sender_joined, "the clean stop must have joined the sender"


def test_the_sender_records_what_the_loop_hands_it(runtime: Path) -> None:
    loop = build(runtime, max_ticks=2)
    loop.sender.start()
    loop.admit("alpha", now=1.0)
    loop.take_in_flight("alpha", "coid-1")
    handoff = loop.hand_to_sender(("alpha", "coid-1"))
    assert handoff.seq == 1
    deadline = time.monotonic() + 5.0
    while loop.sender.handoffs < 1 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert loop.sender.handoffs == 1, "the sender thread never dequeued the handoff"
    ledger = loop.sender.ledger()
    assert [row.payload for row in ledger] == [("alpha", "coid-1")], ledger
    assert loop.sender.stop(), "the sender did not exit on its stop sentinel"


# ---------------------------------------------------------------------------
# The drain, its bound, and the containment of a faulty handler
# ---------------------------------------------------------------------------


def test_one_tick_handles_at_most_max_drain_per_tick_items(runtime: Path) -> None:
    seen: list[object] = []
    loop = build(runtime, handler=seen.append, max_drain_per_tick=5)
    for index in range(200):
        loop.submit(index)
    loop.tick()
    assert len(seen) == 5, (
        f"one tick handled {len(seen)} items — §11:581's discipline is what "
        "stops a flooded inbox holding the tick open past the beat's deadline"
    )
    loop.tick()
    assert len(seen) == 10


def test_a_raising_handler_is_contained_and_named_rather_than_killing_the_loop(
    runtime: Path,
) -> None:
    def _explode(item: object) -> None:
        raise ValueError(f"planted defect on {item!r}")

    loop = build(runtime, handler=_explode)
    loop.submit("command-7")
    loop.tick()
    loop.tick()
    assert loop.tick_count == 2, "the loop must have survived the handler fault"
    faults = loop.faults()
    assert len(faults) == 1, faults
    assert "planted defect on 'command-7'" in faults[0], faults[0]
    assert "ValueError" in faults[0], faults[0]
    assert "remote kill switch" in faults[0], (
        f"the fault must say WHY it was contained: {faults[0]}"
    )


def test_a_raising_ingress_is_contained_and_named(runtime: Path) -> None:
    def _explode(tick: int) -> None:
        raise OSError(f"planted inbox fault on tick {tick}")

    loop = build(runtime, ingress=_explode)
    loop.tick()
    faults = loop.faults()
    assert len(faults) == 1, faults
    assert "ingress raised on tick 1" in faults[0], faults[0]
    assert "planted inbox fault on tick 1" in faults[0], faults[0]
    assert loop.heartbeats_published == 1, (
        "a failing ingress must not stop the beat — a Limiter that went silent "
        "on a bad inbound message would trigger §12.1:604's emergency flatten"
    )


def test_the_ingress_runs_inside_the_tick_and_is_told_which_one(runtime: Path) -> None:
    ticks: list[int] = []
    loop = build(runtime, ingress=ticks.append)
    loop.tick()
    loop.tick()
    assert ticks == [1, 2], (
        f"ingress saw {ticks}; §5:322 puts the inbox read in the loop"
    )


# ---------------------------------------------------------------------------
# stop(), and the documented final state
# ---------------------------------------------------------------------------


def test_stop_ends_the_loop_and_the_final_state_says_why(runtime: Path) -> None:
    loop = build(runtime)
    stopper = threading.Thread(target=lambda: _stop_after(loop, ticks=3))
    stopper.start()
    stop = loop.run()
    stopper.join(timeout=5.0)
    assert stop.ticks >= 3, f"stopped after only {stop.ticks} ticks"
    assert "planted stop" in stop.reason, stop.reason
    assert stop.heartbeats >= 1
    assert stop.last_seq == loop.heartbeat_seq
    assert stop.sender_joined and not stop.sender_alive, (
        "a clean stop must leave no §5:323 sender thread running"
    )


def _stop_after(loop: LimiterLoop, *, ticks: int) -> None:
    """Ask the loop to stop once it has ticked `ticks` times. From ANOTHER thread.

    `stop()` is the one verb deliberately callable off the loop thread — §12.2:617
    delivers `SIGTERM` to the main thread and the handler must be able to reach it
    — so this doubles as the control that it is.
    """
    deadline = time.monotonic() + 5.0
    while loop.tick_count < ticks and time.monotonic() < deadline:
        time.sleep(0.001)
    loop.stop("planted stop from another thread")


def test_a_loop_stopped_before_it_ticked_reports_zero_ticks(runtime: Path) -> None:
    loop = build(runtime)
    loop.stop("planted pre-run stop")
    stop = loop.run()
    assert stop.ticks == 0, (
        "stop() is read at the TOP of the tick, so a loop stopped first must "
        "report having done nothing rather than one tick's worth of work"
    )
    assert stop.heartbeats == 0
    assert "planted pre-run stop" in stop.reason


def test_the_final_state_reports_the_live_registry_and_flatness(runtime: Path) -> None:
    loop = build(runtime, max_ticks=2)
    loop.admit("alpha", now=1.0)
    stop = loop.run()
    assert stop.registrations == ("alpha",)
    assert stop.in_flight == ()
    assert stop.flat, "no lock held means flat in the IN-PROCESS sense §12.2:618 gives"

    loop2 = build(runtime, max_ticks=2)
    loop2.admit("beta", now=1.0)
    loop2.take_in_flight("beta", "coid-9")
    stop2 = loop2.run()
    assert stop2.in_flight == (("beta", "coid-9"),)
    assert not stop2.flat, "a held one-in-flight lock is not a flat process"


# ---------------------------------------------------------------------------
# Boot refusals, and the DERIVED knobs (CLAUDE.md directive 3)
# ---------------------------------------------------------------------------


def test_a_tick_slower_than_the_beat_is_refused_at_construction(runtime: Path) -> None:
    with pytest.raises(LoopError) as excinfo:
        build(runtime, heartbeat_interval_s=0.1, tick_interval_s=0.2)
    text = str(excinfo.value)
    assert "exceeds" in text and "heartbeat_interval_s" in text, text
    assert "systematically late heartbeat" in text, text


def test_a_non_positive_cadence_is_refused_at_construction(runtime: Path) -> None:
    with pytest.raises(LoopError) as excinfo:
        build(runtime, heartbeat_interval_s=0.0)
    assert "§12A:832" in str(excinfo.value), str(excinfo.value)
    with pytest.raises(LoopError) as excinfo:
        build(runtime, tick_interval_s=0.0)
    assert "busy loop" in str(excinfo.value), str(excinfo.value)


def test_a_drain_that_may_handle_nothing_is_refused(runtime: Path) -> None:
    with pytest.raises(LoopError) as excinfo:
        build(runtime, max_drain_per_tick=0)
    assert "beats and never serves" in str(excinfo.value), str(excinfo.value)


def test_attaching_after_the_loop_has_started_is_refused(runtime: Path) -> None:
    loop = build(runtime)
    loop.tick()
    with pytest.raises(LoopError) as excinfo:
        loop.attach(handler=lambda item: None)
    assert "already ticked" in str(excinfo.value), str(excinfo.value)


def test_the_heartbeat_interval_is_read_from_its_one_physical_home(
    runtime: Path,
) -> None:
    del runtime
    # The independent read: this control opens `risks/limiter.config.json` itself
    # rather than asking the same loader twice, so the two sides of the claim have
    # different provenance (`docs/debug.md` §7.4).
    raw = json.loads(
        (REPO_ROOT / "risks" / "limiter.config.json").read_text(encoding="utf-8")
    )
    assert heartbeat_interval_from_config() == float(raw["heartbeat_interval_s"]), (
        "the loop's §12A:832 interval must be the number in "
        "risks/limiter.config.json and not one spelled in the code"
    )


def test_the_tick_cadence_is_derived_from_the_beat_and_is_not_a_knob(
    runtime: Path,
) -> None:
    del runtime
    raw = json.loads(
        (REPO_ROOT / "risks" / "limiter.config.json").read_text(encoding="utf-8")
    )
    assert "tick_interval_s" not in raw, (
        "the tick cadence is a DECLARED NIX ADDITION derived from "
        "heartbeat_interval_s; landing it as a twentieth knob would put a number "
        "in risks/ that §12A does not authorise"
    )
    interval = float(raw["heartbeat_interval_s"])
    assert tick_interval_for(interval) == interval / TICKS_PER_HEARTBEAT
