"""ARC 034 / sub-agent C — §4's orphan / strategy-death recovery, ORDER OBSERVED.

The can-fail suite for `scripts/nixrisk/recovery.py`. Every control follows
plant → red (naming the SITE and the REASON) → restore → green, and every
assertion reads the REASON — a recorded step, a `HaltCause`, an alert code, a
published lifecycle state — never an exit code or a bare boolean (check contract
v2 §11).

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.

THE SAFETY PROPERTY IS AN ORDER, AND AN ORDER IS PROVEN BY OBSERVATION
----------------------------------------------------------------------
§4:262-268 flattens FIRST and force-deregisters SECOND, because deregistering
first orphans the position: the sweep is *"swept by `strategy_id`"* and there is
nothing left to sweep by once the registration is gone.

Source order proves nothing about execution order. So every control here reads
`RecoveryJournal` — the append-only list the sequencer writes AS EACH STEP RUNS —
and `_DeregisterFirstSequencer` is a subclass that performs the SAME three calls
in the wrong order and is shown to produce a journal the assertions reject. An
assertion no falsifier can break measures nothing.

THE §0a HAZARDS THIS BRIEF NAMES, TREATED AS HYPOTHESES AND MEASURED:

* **the order could hold vacuously over steps that did nothing.** So the dying
  strategy owns a REAL open position, the broker records the close, and the
  registration is asserted PRESENT at the instant the flatten fires.
* **fail-closed branches undriven because the suite's own doubles cannot produce
  the input.** So the publish sink is driven DEAD (it raises) in one control, and
  the recovery must continue anyway with the failure recorded — because money was
  already safe and stopping would leave the strategy registered (§4:267).
* **`Closed:` claims that are false.** Each §7.12 route named in
  `nixrisk/recovery.py`'s docstring has a control here, and each control names
  the route it closes.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-few-public-methods,too-many-arguments
# pylint: disable=too-many-positional-arguments,duplicate-code
# pylint: disable=use-implicit-booleaness-not-comparison,import-outside-toplevel
# C1803: `x == []` is the assertion here — 'exactly nothing happened' is a
# different claim from 'nothing truthy happened', and the failure message
# shows WHAT was there. C0415: two imports are deliberately local to the one
# control that reads the constant.
# invalid-name: the test names are sentences. protected-access: the falsifier
# reaches the sequencer's own collaborators to build a WRONG variant — that is
# how a falsifier is written. duplicate-code: the doubles here stand in for the
# same frozen ports test_flatten's doubles stand in for; R0801 cannot tell two
# implementations of one Protocol from copied logic.

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import risk_config
from nixalloc import lifecycle
from nixrisk.flatten import ProtectiveFlatten
from nixrisk.gate import GatePass, default_manifest
from nixrisk.halt import HaltFlag
from nixrisk.picture import FinancialPictureBook
from nixrisk.recovery import (
    ORPHAN_REASON,
    HeartbeatMonitor,
    RecoveryError,
    RecoverySequencer,
    RecoveryStep,
    StrategyRegistry,
    heartbeat_from_config,
)
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    Decision,
    EventKind,
    FlattenTrigger,
    PositionRow,
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.supervision import (
    BreakerScope,
    CrashLoopBreaker,
    RestartLedger,
    SupervisionKnobs,
)

DEAD = "strat-dead"
LIVE = "strat-live"


# ==========================================================================
# Doubles — each records the REASON or the ARGUMENTS, never a bare count
# ==========================================================================


class Broker:
    """The §2A flatten verbs. Records WHICH symbols were closed, in order."""

    def __init__(self) -> None:
        self.flatten_calls: list[str | None] = []
        self.cancelled: list[str] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)

    def cancel_order(self, client_order_id: str) -> None:
        self.cancelled.append(client_order_id)


class Sink:
    def __init__(self) -> None:
        self.emitted: list = []

    def emit(self, picture) -> None:
        self.emitted.append(picture)


class DeadSink:
    """The state bus is DOWN. Raises on every publish — §7.12/2 for the publish."""

    def emit(self, picture) -> None:
        del picture
        raise ConnectionError("state bus down")


class Plane1:
    def __init__(self) -> None:
        self.rows: list = []

    def enqueue(self, row) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return len(self.rows)

    def kinds(self) -> list[EventKind]:
        return [row.kind for row in self.rows]


class Plane2:
    def __init__(self) -> None:
        self.lines: list[tuple[str, dict]] = []

    def emit(self, event: str, **fields) -> str:
        self.lines.append((event, dict(fields)))
        return event


class Alerts:
    def __init__(self) -> None:
        self.raised: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        self.raised.append((code, message))

    def codes(self) -> list[str]:
        return [code for code, _ in self.raised]


class StrategySink:
    def __init__(self) -> None:
        self.closed: list[tuple[str, str, str, bool]] = []

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


class Scoring:
    def __init__(self) -> None:
        self.booked: list[dict] = []

    def book_realized(
        self,
        *,
        closed_trades,
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        self.booked.append(
            {
                "closed_trades": tuple(closed_trades),
                "realized_delta": realized_delta,
                "confirmed_balance": confirmed_balance,
                "ts": ts,
            }
        )


class Supervisor:
    """§4:269-271's process lifecycle, recording the ORDER of its own verbs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def kill(self, strategy_id: str) -> str:
        self.calls.append(("kill", strategy_id))
        return f"killed {strategy_id} (§4:269)"

    def relaunch(self, strategy_id: str) -> str:
        self.calls.append(("relaunch", strategy_id))
        return f"relaunched {strategy_id}; it re-registers and boots to flat (§4:271)"


class _DeregisterFirstSequencer(RecoverySequencer):
    """THE FALSIFIER for the ORDER: it deregisters BEFORE it flattens.

    The three calls are the same three calls. Only their EXECUTION order differs,
    which is precisely the mistake source-order review cannot catch and the
    journal can. §4:262-265 says the flatten happens 'while its registration
    still exists'; this one destroys the ownership first.
    """

    def recover(self, strategy_id: str, *, now=None):
        stamp = self._clock() if now is None else float(now)
        self._record(RecoveryStep.DETECT_DEATH, strategy_id, stamp, True, "falsifier")
        self._step_deregister(strategy_id, stamp)
        flattened = self._step_flatten(strategy_id, stamp)
        self._step_publish(strategy_id, stamp)
        return flattened


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture
def limiter_knobs() -> dict:
    """The SHIPPED §12A knobs, read from risks/ — never typed into this file."""
    loaded = risk_config.load_risk_configs(REPO)
    return dict(loaded.modules["limiter"].values)


@pytest.fixture
def supervision_knobs() -> SupervisionKnobs:
    loaded = risk_config.load_risk_configs(REPO)
    return SupervisionKnobs.from_config(loaded.modules["supervision"].values)


class World:  # pylint: disable=too-many-instance-attributes
    """One wired Limiter: registry, heartbeat, real flatten executor, sequencer."""

    def __init__(
        self,
        tmp_path: Path,
        limiter_knobs: dict,
        supervision_knobs: SupervisionKnobs,
        *,
        sink=None,
        cls=RecoverySequencer,
    ) -> None:
        self.sink = sink if sink is not None else Sink()
        self.broker = Broker()
        self.plane1 = Plane1()
        self.plane2 = Plane2()
        self.alerts = Alerts()
        self.strategy = StrategySink()
        self.scoring = Scoring()
        self.supervisor = Supervisor()
        self.book = FinancialPictureBook(
            balance=100_000.0, deployable_fraction=0.70, sink=self.sink
        )
        # The doubles are DELIBERATELY PARTIAL — `Broker` implements the
        # flatten verbs this suite drives and not `query_balance` /
        # `query_positions`, and `Plane1` implements `enqueue` and not
        # `pending()`. mypy sees the protocol gap; the suite never reaches the
        # missing verbs, and widening the doubles to satisfy a type checker
        # would put behaviour in them that nothing here measures. PRE-EXISTING;
        # surfaced by ARC 037 only because mypy type-checks nixrisk.recovery
        # when scripts/nixrisk/supervision.py is in the same hook invocation.
        self.flatten = ProtectiveFlatten(
            broker=self.broker,  # type: ignore[arg-type]
            ledger=ReservationLedger(self.plane1),  # type: ignore[arg-type]
            picture=self.book,
            strategy=self.strategy,
            plane1=self.plane1,  # type: ignore[arg-type]
            scoring=self.scoring,
        )
        self.registry = StrategyRegistry()
        self.heartbeat = heartbeat_from_config(limiter_knobs)
        self.breaker = CrashLoopBreaker(
            knobs=supervision_knobs,
            scope=BreakerScope.STRATEGY,
            ledger=RestartLedger(tmp_path / "restarts.jsonl"),
            alert=self.alerts,
            plane2=self.plane2,
        )
        self.sequencer = cls(
            registry=self.registry,
            heartbeat=self.heartbeat,
            flatten=self.flatten,
            picture=self.book,
            breaker=self.breaker,
            supervisor=self.supervisor,
            plane1=self.plane1,
            plane2=self.plane2,
            alert=self.alerts,
        )

    def admit(self, strategy_id: str, slot: int, now: float = 0.0) -> None:
        self.registry.register(strategy_id, slot=slot, now=now)
        self.heartbeat.arm(strategy_id, now=now)

    def open_position(self, strategy_id: str, trade_id: str, symbol: str) -> None:
        rows = list(self.book.current().positions)
        rows.append(
            PositionRow(
                trade_id=trade_id,
                symbol=symbol,
                strategy_id=strategy_id,
                size=1,
                margin=1000.0,
                state=PositionState.OPEN,
                stop_distance=20,
            )
        )
        self.book.commit(positions=rows)


@pytest.fixture
def world(tmp_path: Path, limiter_knobs: dict, supervision_knobs) -> World:
    built = World(tmp_path, limiter_knobs, supervision_knobs)
    built.admit(DEAD, slot=1)
    built.admit(LIVE, slot=2)
    built.open_position(DEAD, "T-dead", "MESU6")
    built.open_position(LIVE, "T-live", "MNQU6")
    return built


# ==========================================================================
# C2a — the STRATEGY heartbeat: miss ⇒ ONE CYCLE ⇒ second miss ⇒ dead
# ==========================================================================


def test_ONE_miss_is_NOT_death_because_4_260_waits_EXACTLY_ONE_CYCLE(
    limiter_knobs: dict,
) -> None:
    """§4:260 — 'heartbeat miss ⇒ wait exactly one cycle (1s)'. §7.12/1: the
    not-dead branch is driven, so a monitor that killed on the first miss fails
    here. The knobs come from risks/limiter.config.json, not from a literal."""
    monitor = heartbeat_from_config(limiter_knobs)
    monitor.arm("s", now=0.0)

    verdict = monitor.miss("s", now=1.0)

    assert verdict.consecutive_misses == 1
    assert verdict.presumed_dead is False, verdict.reason
    assert "within the grace" in verdict.reason
    assert monitor.presumed_dead(1.0) == ()


def test_a_SECOND_CONSECUTIVE_miss_PRESUMES_DEATH(limiter_knobs: dict) -> None:
    """§4:261 — 'a second consecutive miss ⇒ strategy presumed dead'."""
    monitor = heartbeat_from_config(limiter_knobs)
    monitor.arm("s", now=0.0)
    monitor.miss("s", now=1.0)

    verdict = monitor.miss("s", now=2.0)

    assert verdict.consecutive_misses == monitor.grace_cycles + 1
    assert verdict.presumed_dead is True, verdict.reason
    assert "PRESUMED DEAD" in verdict.reason
    assert "SECOND consecutive miss" in verdict.reason
    assert monitor.presumed_dead(2.0) == ("s",)


def test_a_BEAT_between_two_misses_RESETS_the_run_so_they_are_not_CONSECUTIVE(
    limiter_knobs: dict,
) -> None:
    """CONSECUTIVE is the load-bearing word. A monitor written against 'no beat
    for 2s' cannot tell miss-beat-miss from miss-miss, and would flatten a LIVE
    strategy's positions. This is the control that separates the two."""
    monitor = heartbeat_from_config(limiter_knobs)
    monitor.arm("s", now=0.0)
    monitor.miss("s", now=1.0)
    monitor.beat("s", now=1.5)

    verdict = monitor.miss("s", now=2.5)

    assert verdict.consecutive_misses == 1, verdict.reason
    assert verdict.presumed_dead is False, verdict.reason
    assert monitor.presumed_dead(2.5) == ()


def test_a_grace_of_ZERO_cycles_is_REFUSED_naming_what_it_would_cost() -> None:
    """§12A:832 and risks/limiter.config.json's
    `liveness.heartbeat_grace_at_least_one_cycle`: a grace of zero makes ONE
    dropped beat a strategy death, and a strategy death flattens positions."""
    with pytest.raises(RecoveryError) as caught:
        HeartbeatMonitor(interval_s=1.0, grace_cycles=0)

    assert "must be >= 1" in str(caught.value)
    assert "a strategy death flattens positions" in str(caught.value)


def test_an_UNARMED_strategy_is_never_reported_dead(limiter_knobs: dict) -> None:
    """§7.12/3: a monitor that reported on strategies it was never told about
    would 'detect the death' of every process that has never existed."""
    monitor = heartbeat_from_config(limiter_knobs)

    assert monitor.armed() == ()
    assert monitor.presumed_dead(99.0) == ()
    with pytest.raises(RecoveryError) as caught:
        monitor.miss("ghost", now=1.0)
    assert "is not armed" in str(caught.value)


# ==========================================================================
# C2b — THE ORDER. Observed, never asserted from the source.
# ==========================================================================


def test_the_OBSERVED_STEP_SEQUENCE_is_FLATTEN_then_DEREGISTER_then_KILL_RELAUNCH(
    world: World,
) -> None:
    """§4:262-274's strict order, read off the journal the sequencer wrote AS
    EACH STEP RAN. This is the deliverable: not that the calls are in the file in
    this order, but that they EXECUTED in it."""
    outcome = world.sequencer.recover(DEAD, now=100.0)

    assert [step.value for step in outcome.sequence] == [
        "detect_death",
        "flatten",
        "publish_in_flight_closing",
        "force_deregister",
        "kill",
        "relaunch",
    ], [(s.seq, s.step.value, s.detail) for s in outcome.steps]
    flatten_at = world.sequencer.journal.index_of(RecoveryStep.FLATTEN, DEAD)
    dereg_at = world.sequencer.journal.index_of(RecoveryStep.FORCE_DEREGISTER, DEAD)
    assert 0 <= flatten_at < dereg_at, outcome.reason
    assert world.supervisor.calls == [("kill", DEAD), ("relaunch", DEAD)]


def test_the_FLATTEN_really_CLOSED_a_REAL_position_while_STILL_OWNED(
    world: World,
) -> None:
    """§7.12/5 — the order must not hold vacuously over two steps that did
    nothing. The dying strategy owns a real OPEN row; the broker records the
    close; and the recorded step states the registration was still PRESENT."""
    outcome = world.sequencer.recover(DEAD, now=100.0)

    assert outcome.flattened_trades == ("T-dead",), outcome.reason
    assert world.broker.flatten_calls == ["MESU6"], world.broker.flatten_calls
    step = next(s for s in outcome.steps if s.step is RecoveryStep.FLATTEN)
    assert "registration was STILL PRESENT" in step.detail
    assert "is_registered=True" in step.detail
    assert f"FlattenTrigger.{FlattenTrigger.ORPHAN.name}" in step.detail
    record = world.flatten.closed_record("T-dead")
    assert record is not None and record.reason == ORPHAN_REASON
    assert record.hard_reset is True, "a protective close hard-resets the FSM (§4)"


def test_the_ORDER_CONTROL_is_FALSIFIABLE_a_DEREGISTER_FIRST_sequencer_LOSES_it(
    tmp_path: Path, limiter_knobs: dict, supervision_knobs
) -> None:
    """THE CAN-FAIL TWIN. Same three calls, wrong EXECUTION order. It orphans the
    position: at the moment the sweep runs the registration is already gone, so
    nothing is closed and the broker is never reached."""
    broken = World(
        tmp_path, limiter_knobs, supervision_knobs, cls=_DeregisterFirstSequencer
    )
    broken.admit(DEAD, slot=1)
    broken.open_position(DEAD, "T-dead", "MESU6")

    flattened = broken.sequencer.recover(DEAD, now=100.0)

    sequence = [s.value for s in broken.sequencer.journal.sequence(DEAD)]
    assert sequence.index("force_deregister") < sequence.index("flatten"), sequence
    assert flattened == (), (
        "the deregister-first falsifier still closed a position — it no longer "
        "falsifies, and the order assertion above would be vacuous"
    )
    assert broken.broker.flatten_calls == [], (
        "the falsifier reached the broker anyway; the ORPHANING did not happen"
    )
    step = next(
        s
        for s in broken.sequencer.journal.entries(DEAD)
        if s.step is RecoveryStep.FLATTEN
    )
    assert step.ok is False, step.detail
    assert "ORPHANED" in step.detail
    assert "no owner to sweep by" in step.detail
    assert "deregistering before flattening costs" in step.detail
    # The position SURVIVES the recovery unclosed, and the published table now
    # says CLOSING about a trade no broker call was ever made for — the orphan
    # is a live position wearing a state nothing produced. That is the cost the
    # §4:262-268 order buys, and it is observable rather than argued.
    survivor = [
        row for row in broken.book.current().positions if row.trade_id == "T-dead"
    ]
    assert len(survivor) == 1, "the falsifier's orphan is not observable"
    assert survivor[0].state is PositionState.CLOSING, survivor[0]
    assert broken.broker.flatten_calls == [], (
        "a CLOSING row was published for a trade the broker was never asked to "
        "close — the orphan"
    )


def test_FORCE_DEREGISTER_tears_down_ALL_FOUR_things_4_266_names(
    world: World,
) -> None:
    """§4:266-268 — 'one-in-flight lock, pending state, slot, registration.
    Nothing stale may survive the death.' §7.12/6: four separate observed facts,
    then the registry is RE-READ to prove nothing survived."""
    world.registry.take_in_flight(DEAD, "c-dead-1")
    assert world.registry.in_flight(DEAD)[0] is True

    outcome = world.sequencer.recover(DEAD, now=100.0)

    dereg = outcome.deregistration
    assert dereg is not None and dereg.had_registration
    assert dereg.released_in_flight == "c-dead-1", dereg.reason
    assert dereg.dropped_pending == ("c-dead-1",), dereg.reason
    assert dereg.freed_slot == 1, dereg.reason
    # Re-read: nothing stale survived.
    assert world.registry.get(DEAD) is None
    assert world.registry.is_registered(DEAD) is False
    assert world.registry.in_flight(DEAD) == (False, f"{DEAD}: no order in flight")
    assert DEAD not in world.heartbeat.armed(), (
        "§4:267 — a lingering registration would leave the Limiter expecting "
        "heartbeats; the monitor must have been disarmed"
    )
    assert world.registry.registered() == (LIVE,)


def test_recovering_an_ALREADY_DEREGISTERED_strategy_is_REFUSED(world: World) -> None:
    """The fail-closed branch, driven. §4:262-265 flattens 'while its
    registration still exists'; recovering after deregistration is the orphaned
    state the order exists to prevent, not a recovery of it."""
    world.registry.force_deregister(DEAD)

    with pytest.raises(RecoveryError) as caught:
        world.sequencer.recover(DEAD, now=100.0)

    assert "holds no registration" in str(caught.value)
    assert "unambiguous known owner" in str(caught.value)
    assert world.broker.flatten_calls == []


def test_a_dead_strategy_owning_NOTHING_gets_NO_UNTARGETED_FLATTEN(
    tmp_path: Path, limiter_knobs: dict, supervision_knobs
) -> None:
    """The hazard stated backwards if it were missed: an untargeted flatten
    reaches `broker.flatten(None)`, which closes EVERY symbol. Recovering a
    strategy that held nothing must not close another strategy's position."""
    built = World(tmp_path, limiter_knobs, supervision_knobs)
    built.admit(DEAD, slot=1)
    built.admit(LIVE, slot=2)
    built.open_position(LIVE, "T-live", "MNQU6")

    outcome = built.sequencer.recover(DEAD, now=100.0)

    assert outcome.flattened_trades == ()
    assert built.broker.flatten_calls == [], built.broker.flatten_calls
    step = next(s for s in outcome.steps if s.step is RecoveryStep.FLATTEN)
    assert "NO untargeted flatten was issued" in step.detail
    assert "closes EVERY symbol" in step.detail
    live_rows = [
        row
        for row in built.book.current().positions
        if row.strategy_id == LIVE and row.state is PositionState.OPEN
    ]
    assert len(live_rows) == 1, "the live strategy's position was disturbed"


def test_the_STRATEGY_LIFECYCLE_rows_reach_PLANE_1(world: World) -> None:
    """§12.10:757 routes 'strategy lifecycle (register / force-deregister / kill /
    relaunch / quarantine / restore)' to Plane 1 AND Plane 2. The rows ride the
    Limiter's existing sole-writer port — no new writer (§9)."""
    world.sequencer.recover(DEAD, now=100.0)

    kinds = world.plane1.kinds()
    for kind in (EventKind.FORCE_DEREGISTER, EventKind.KILL, EventKind.RELAUNCH):
        assert kind in kinds, kinds
    lifecycle_rows = [
        row
        for row in world.plane1.rows
        if row.kind in (EventKind.FORCE_DEREGISTER, EventKind.KILL, EventKind.RELAUNCH)
    ]
    assert all(row.strategy_id == DEAD for row in lifecycle_rows)
    assert all(row.reason for row in lifecycle_rows), "a row with no reason (§9)"
    assert [event for event, _ in world.plane2.lines].count("orphan-recovery") == 1


# ==========================================================================
# C4 — the Allocator reads IN-FLIGHT-CLOSING through a REAL death
# ==========================================================================


def test_a_REAL_DEATH_publishes_the_dying_strategy_as_IN_FLIGHT_CLOSING(
    world: World,
) -> None:
    """§4:281-286 (locked) — 'a strategy mid-recovery reads as in-flight-closing,
    NOT normal-and-available, so it is never counted eligible for new capital
    while dying.'

    Driven through a REAL death, not a state injection: the picture read here is
    the one the recovery itself published, and `nixalloc.lifecycle` — the shipped
    Allocator screen — is what answers. CHECK-DEBT D3.155 asked for exactly a
    HEARTBEAT-originated closing row rather than a halted-market one.
    """
    before = lifecycle.eligibility(world.book.current(), DEAD)
    assert before.eligible is True, before.reason

    outcome = world.sequencer.recover(DEAD, now=100.0)

    published = world.book.current()
    assert outcome.published_version == published.version
    after = lifecycle.eligibility(published, DEAD)
    assert after.eligible is False, after.reason
    assert after.closing_trades == ("T-dead",), after.reason
    assert "IN-FLIGHT-CLOSING" in after.reason
    assert "never counted eligible for new capital while dying" in after.reason
    assert world.sink.emitted, "nothing reached the Allocator mirror's wire"
    assert world.sink.emitted[-1].version == published.version


def test_the_OTHER_strategy_stays_ELIGIBLE_through_the_death(world: World) -> None:
    """The non-vacuity floor for the control above, and it is not an identity: the
    SAME published snapshot must answer differently for the two strategies. A
    screen that refused everyone would pass the previous test and be useless."""
    world.sequencer.recover(DEAD, now=100.0)

    published = world.book.current()
    live = lifecycle.eligibility(published, LIVE)

    assert live.eligible is True, live.reason
    assert live.observed_states == ("open",), live.reason
    assert lifecycle.eligibility(published, DEAD).eligible is False


def test_the_PUBLISH_sits_AFTER_the_FLATTEN_so_a_DEAD_WIRE_cannot_stop_the_EXIT(
    tmp_path: Path, limiter_knobs: dict, supervision_knobs
) -> None:
    """§14's zero-wire exit, driven by REMOVING the wire — §7.12/2 for the
    publish. The bus raises on every publish. The flatten must still have reached
    the broker, the recovery must still have completed, and the failed publish
    must be RECORDED rather than swallowed."""
    dead_wire = World(tmp_path, limiter_knobs, supervision_knobs)
    dead_wire.admit(DEAD, slot=1)
    dead_wire.open_position(DEAD, "T-dead", "MESU6")
    dead_wire.book._sink = DeadSink()  # the wire goes down AFTER the setup publish

    outcome = dead_wire.sequencer.recover(DEAD, now=100.0)

    assert dead_wire.broker.flatten_calls == ["MESU6"], (
        "the exit did not fire with the wire down — it has a wire dependency"
    )
    publish = next(
        s for s in outcome.steps if s.step is RecoveryStep.PUBLISH_IN_FLIGHT_CLOSING
    )
    assert publish.ok is False, publish.detail
    assert "ConnectionError" in publish.detail and "state bus down" in publish.detail
    assert "recovery CONTINUES" in publish.detail
    assert outcome.published_version is None
    assert outcome.deregistration is not None and outcome.deregistration.complete
    assert outcome.relaunched is True, (
        "the recovery stopped at the failed publish, leaving the dead strategy "
        "registered — §4:267's lingering registration"
    )


# ==========================================================================
# C3 — the crash-loop cap QUARANTINES, and the rest keeps trading
# ==========================================================================


def _crash_loop(world: World, strategy_id: str, times: int, slot: int) -> list:
    outcomes = []
    for i in range(times):
        if not world.registry.is_registered(strategy_id):
            world.admit(strategy_id, slot=slot, now=200.0 + i)
        outcomes.append(world.sequencer.recover(strategy_id, now=200.0 + i))
    return outcomes


def test_the_CAP_stops_RELAUNCHING_and_QUARANTINES_the_strategy(
    world: World, supervision_knobs
) -> None:
    """§4:272-274 — 'after 3 restarts within a window, stop relaunching. The
    strategy is quarantined — left dead and flat, alert raised.'"""
    outcomes = _crash_loop(world, DEAD, supervision_knobs.crash_loop_max, slot=1)

    early = outcomes[:-1]
    assert all(o.relaunched and not o.quarantined for o in early), [
        o.reason for o in early
    ]
    final = outcomes[-1]
    assert final.quarantined and not final.relaunched, final.reason
    assert final.sequence[-1] is RecoveryStep.QUARANTINE, final.reason
    assert RecoveryStep.RELAUNCH not in final.sequence
    assert world.supervisor.calls[-1] == ("kill", DEAD), (
        "§4:272 says stop RELAUNCHING, not stop killing — leaving a half-dead "
        "process alive is the orphan state the rule exists to end"
    )
    assert "recovery.quarantine" in world.alerts.codes()
    quarantine_alert = next(
        msg for code, msg in world.alerts.raised if code == "recovery.quarantine"
    )
    assert "left DEAD AND FLAT" in quarantine_alert
    assert "the rest of the system keeps trading" in quarantine_alert
    assert EventKind.QUARANTINE in world.plane1.kinds()


def test_a_QUARANTINED_strategy_does_NOT_stop_ANOTHER_strategy_being_APPROVED(
    world: World, supervision_knobs, limiter_knobs: dict
) -> None:
    """§4:273's 'while the rest of the system keeps trading', DRIVEN through the
    real §3 gate pass — not asserted.

    The live strategy's proposal is evaluated by a REAL `GatePass` over the
    SHIPPED `default_manifest`, with the REAL `StrategyRegistry` as the
    one-in-flight port and a REAL `HaltFlag` as branch 0. A quarantine that had
    declared a platform HALT, or had left the dead strategy's in-flight lock
    behind on a shared port, would deny here.
    """
    _crash_loop(world, DEAD, supervision_knobs.crash_loop_max, slot=1)
    assert world.breaker.is_quarantined(DEAD)

    halt = HaltFlag(
        plane1=Plane1(),  # type: ignore[arg-type]  # partial double; see World
        plane2=Plane2(),
        floors=limiter_knobs["halt_cooldown_floor_s"],
    )
    assert halt.is_set() == (False, ""), (
        "§4:273 — quarantining ONE strategy declared a platform-wide HALT"
    )
    clear = _Clear()
    gate = GatePass(
        halt,
        list(
            default_manifest(
                blackout=clear,
                tradability=clear,
                staleness=clear,
                clock_skew=clear,
                in_flight=world.registry,
                net_liq=_NetLiq(),
                deployable_fraction=0.70,
                survival_safety_pad=0.10,
                coherence_tolerance=1e-6,
            )
        ),
        _Ledger(),
    )

    outcome = gate.evaluate(_order(LIVE), world.book.current(), 300.0)

    assert outcome.decision is Decision.APPROVE, (outcome.rule, outcome.reason)


def test_the_QUARANTINE_alert_states_the_UNWIRED_SCORING_BOUNDARY(
    world: World, supervision_knobs
) -> None:
    """A green here must not imply scoring works. §4:275-280's persist-across-
    crash / archive-on-quarantine rule has a MECHANISM in this tree and no JOIN
    to this transition, and the alert an operator reads must say so.

    RENAMED AND RE-POINTED ARC 037 (CHECK-DEBT D3.252): the boundary asserted
    "Scoring does not exist in this tree", which was false on disk from ARC 036
    onward — and false in a string that ships to the operator.
    """
    from nixrisk.supervision import (
        SCORE_BOUNDARY,  # pylint: disable=import-outside-toplevel
    )

    _crash_loop(world, DEAD, supervision_knobs.crash_loop_max, slot=1)

    breaker_alert = next(
        msg for code, msg in world.alerts.raised if code == "supervision.quarantine"
    )
    assert SCORE_BOUNDARY in breaker_alert
    assert "NO JOIN" in SCORE_BOUNDARY
    assert "ScoreStore.archive_strategy" in SCORE_BOUNDARY
    assert "ScoreStore.restore_strategy" in SCORE_BOUNDARY
    assert "Scoring does not exist" not in SCORE_BOUNDARY, (
        "the boundary claims the score store is absent while "
        "scripts/nixscore/store.py is on disk — D3.252's first half"
    )


# ==========================================================================
# Small doubles for the real gate drive
# ==========================================================================


class _Clear:
    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        return False, ""


class _NetLiq:
    def mark(self) -> tuple[float, bool]:
        return 10_000_000.0, True


class _Ledger:
    def __init__(self) -> None:
        self.taken: list[int] = []
        self.live: dict = {}

    def take(self, order, now: float):
        from nixrisk.seam import (  # pylint: disable=import-outside-toplevel
            Reservation,
            ReservationState,
        )

        self.taken.append(order.qty)
        reservation = Reservation(
            reservation_id=f"res-{len(self.taken)}",
            client_order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            margin=order.proposed_margin,
            state=ReservationState.TAKEN,
            taken_ts=now,
        )
        self.live[reservation.reservation_id] = reservation
        return reservation

    def release(self, reservation_id: str, via, now: float):
        import dataclasses  # pylint: disable=import-outside-toplevel

        from nixrisk.seam import (  # pylint: disable=import-outside-toplevel
            ReservationState,
        )

        held = self.live.pop(reservation_id)
        return dataclasses.replace(
            held, state=ReservationState.RELEASED, released_ts=now, released_via=via
        )

    def outstanding(self):
        return tuple(self.live.values())

    def total_reserved(self) -> float:
        return sum(row.margin for row in self.live.values())


def _order(strategy_id: str) -> ProposedOrder:
    return ProposedOrder(
        client_order_id="c-live-1",
        strategy_id=strategy_id,
        symbol="MNQU6",
        side=Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=StopMode.FIXED,
        signal_ts=1.0,
    )
