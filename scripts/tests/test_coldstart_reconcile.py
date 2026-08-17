"""B2 — cold-start reconciliation against broker truth, on a log that is BEHIND.

ARC 035 / Stage 1 / sub-agent B. Subject: `scripts/nixrisk/coldstart.py`'s
`crash_gap` and `ColdStart.boot`. Authority: `docs/nics_risk_subsystem_spec_v1.3.md`
§4 (cold start, the registration gate, the market-tradable guard), §9 (the crash
gap healed by startup reconciliation vs broker truth), §12.1 (Sentinel marker
replay), §12.5 (the Limiter-down HALT booked retroactively at next boot).

The arc brief's §0a, binding on this file:

> *prove reconciliation on a log that is genuinely BEHIND broker truth (a crash
> gap), not one already in agreement.*

**Every drive here starts from a stated disagreement and ASSERTS IT FIRST.** The
pre-assert is not decoration: a reconciliation drive whose two sides already
agreed would measure the identity function, and this is the only place that can
be caught — after `boot()` runs, the two sides agree by construction because §4
flattened the difference.

The second thing this file is written against is the hazard my mandate states
backwards. It says an untradable market *"must not be reported as if it were"*
flattened — true, but the report is not the danger. The danger is a
reconciliation that reads "flatten refused" as "nothing to flatten" and **admits
registration**, which is fail-OPEN into an inherited position. So the untradable
drive asserts `admitted is False` and a `register()` that RAISES, not the wording
of a message.
"""

from __future__ import annotations

# pylint: disable=use-implicit-booleaness-not-comparison
# `assert x == ()` is deliberate here and `not x` is NOT equivalent for these
# assertions: the subjects are tuples whose EMPTINESS is the property under
# test, and `not x` would also pass on None — which is exactly the value a
# reconciler that failed to run would return. The explicit comparison is the
# assertion.
# pylint: disable=too-many-arguments,import-outside-toplevel
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring,too-few-public-methods
# The fakes each declare exactly the ONE verb the port they stand in for
# declares; a second method would be a fake doing two jobs.
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixrisk.coldstart import (  # pylint: disable=import-error
    SOURCE_SENTINEL,
    ColdStart,
    ColdStartState,
    GapKind,
    RegistrationRefused,
    crash_gap,
    unexpected,
)
from nixrisk.halt import (  # pylint: disable=import-error
    SOURCE_REPLAY,
    HaltCause,
    HaltMarker,
)
from nixrisk.seam import (  # pylint: disable=import-error
    BrokerTruth,
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionRow,
    PositionState,
)
from nixsentinel.seam import (  # pylint: disable=import-error
    BrokerAck,
    MarkerPhase,
    MarkerRecord,
    TriggerCause,
)

NOW = 1_700_000_000.0


# --------------------------------------------------------------------- fakes


def position(trade_id: str, symbol: str, size: int, owner: str = "") -> PositionRow:
    return PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id=owner,
        size=size,
        margin=1_000.0 * size,
        state=PositionState.OPEN,
        stop_distance=20,
    )


def truth(*rows: PositionRow, balance: float = 75_000.0) -> BrokerTruth:
    return BrokerTruth(positions=rows, balance=balance, polled_at=NOW)


class FakeBroker:
    """§4's broker truth source. `current` is what the next poll returns."""

    def __init__(self, current: BrokerTruth, tradable: tuple[bool, str]) -> None:
        self.current = current
        self.tradable = tradable
        self.polls = 0

    def poll_truth(self) -> BrokerTruth:
        self.polls += 1
        return self.current

    def market_tradable(self) -> tuple[bool, str]:
        return self.tradable


class FakeFlattener:
    """Limiter-only flatten execution; a successful fire leaves the account flat."""

    def __init__(self, broker: FakeBroker, succeeds: bool = True) -> None:
        self._broker = broker
        self._succeeds = succeeds
        self.calls: list[BrokerTruth] = []

    def flatten(self, seen: BrokerTruth) -> tuple[FlattenTrigger, ...]:
        self.calls.append(seen)
        if self._succeeds:
            self._broker.current = truth(balance=seen.balance)
        return tuple(FlattenTrigger.ORPHAN for _ in seen.positions)


class FakeHalt:
    """Holds in HALT with the loud alert, and records that it was asked to."""

    def __init__(self) -> None:
        self.reasons: list[str] = []

    def hold_in_halt(self, reason: str) -> None:
        self.reasons.append(reason)


class RecordingPlane1:
    """The Limiter's own Plane-1 port, recording. NOT a second writer: the rows
    that reach it were built by `ColdStart` and by `halt.replay_markers`, which
    is where §9's sole writer books them."""

    def __init__(self) -> None:
        self.rows: list[EventRow] = []
        self.syncs = 0

    def enqueue(self, row: EventRow) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        self.syncs += 1
        return len(self.rows)

    def pending(self) -> int:
        return 0


class FakeProjection:
    """§9's rebuildable projection, as cold start reads it. Counts its rebuilds."""

    def __init__(self, *rows: PositionRow) -> None:
        self._rows = rows
        self.rebuilds = 0

    def rebuild(self) -> tuple[PositionRow, ...]:
        self.rebuilds += 1
        return self._rows


class FakeSentinelMarker:
    """§12.1's replay side. `read_pending` returns records; `archive` is counted."""

    def __init__(self, *records: MarkerRecord) -> None:
        self._records = records
        self.archived = 0

    def read_pending(self) -> tuple[MarkerRecord, ...]:
        return self._records

    def archive(self) -> None:
        self.archived += 1


def build(
    *,
    broker_positions: tuple[PositionRow, ...] = (),
    projection_positions: tuple[PositionRow, ...] = (),
    tradable: tuple[bool, str] = (True, "regular session"),
    flatten_succeeds: bool = True,
    sentinel: FakeSentinelMarker | None = None,
    halt_marker: HaltMarker | None = None,
):
    broker = FakeBroker(truth(*broker_positions), tradable)
    flattener = FakeFlattener(broker, succeeds=flatten_succeeds)
    halt = FakeHalt()
    plane1 = RecordingPlane1()
    projection = FakeProjection(*projection_positions)
    cold = ColdStart(
        broker,
        flattener,
        halt,
        plane1,
        sentinel_marker=sentinel,
        projection=projection,
        halt_marker=halt_marker,
    )
    return cold, broker, flattener, halt, plane1, projection


# ------------------------------------------------- the gap itself, as a function


def test_the_crash_gap_names_a_position_the_record_never_committed() -> None:
    """§9: the window between the last group-commit and the crash.

    THE DISAGREEMENT, STATED: the projection knows T-A (2 ES). The broker holds
    T-A **and** T-B (3 NQ), because T-B's `filled` row was in the WAL and had not
    reached Postgres when the box died. Asserted before anything reconciles.
    """
    projection = (position("T-A", "ESU6", 2),)
    broker = truth(position("T-A", "ESU6", 2), position("T-B", "NQU6", 3))
    assert {p.trade_id for p in projection} != {p.trade_id for p in broker.positions}

    gaps = crash_gap(projection, broker)
    assert len(gaps) == 1, gaps
    assert gaps[0].kind is GapKind.UNEXPECTED
    assert gaps[0].trade_id == "T-B"
    assert gaps[0].broker_size == 3
    assert gaps[0].projection_size == 0
    assert "behind reality" in gaps[0].detail


def test_the_crash_gap_names_a_position_the_broker_no_longer_holds() -> None:
    """The other direction: the exit reached the venue and its row did not.

    Broker WINS (§4, locked): *"if projection and broker truth disagree beyond
    tolerance, broker wins and we correct."*
    """
    gaps = crash_gap((position("T-A", "ESU6", 2),), truth())
    assert [g.kind for g in gaps] == [GapKind.VANISHED]
    assert gaps[0].projection_size == 2 and gaps[0].broker_size == 0
    assert "Broker wins" in gaps[0].detail


def test_the_crash_gap_names_a_SIZE_disagreement_on_a_shared_trade() -> None:
    """A partial fill whose later leg is in the gap. Both sizes are carried.

    A finding that recorded only "they differ" could not tell an UNDER-reported
    position — real exposure the record does not know about — from a stale
    over-reported one, and only one of those is dangerous.
    """
    gaps = crash_gap((position("T-A", "ESU6", 1),), truth(position("T-A", "ESU6", 3)))
    assert [g.kind for g in gaps] == [GapKind.SIZE]
    assert (gaps[0].projection_size, gaps[0].broker_size) == (1, 3)


def test_two_sides_that_AGREE_produce_no_gap_and_that_is_the_control() -> None:
    """The control for every drive above: identical sides yield nothing.

    Without it, a `crash_gap` that returned a finding for every pair would look
    like a working detector in all three tests above.
    """
    same = (position("T-A", "ESU6", 2), position("T-B", "NQU6", 3))
    assert crash_gap(same, truth(*same)) == ()


# ------------------------------------------------------ boot, end to end (§4)


def test_boot_HEALS_a_projection_that_is_behind_broker_truth() -> None:
    """The whole B2 property, on a genuine crash gap.

    Disagreement first, asserted. Then: the projection is rebuilt, the gap is
    named, §4 flattens the unexpected position, the broker CONFIRMS flat, and
    registration is admitted — in that order, with the `cold_start_outcome` row
    carrying the gap.
    """
    known = position("T-A", "ESU6", 2)
    unknown = position("T-B", "NQU6", 3)
    cold, broker, flattener, _halt, plane1, projection = build(
        broker_positions=(known, unknown), projection_positions=(known,)
    )
    assert broker.current.positions != (known,), "the two sides must start APART"

    result = cold.boot(NOW)

    assert projection.rebuilds == 1
    assert [g.trade_id for g in unexpected(result.gap)] == ["T-B"]
    assert result.gap[0].kind is GapKind.UNEXPECTED
    assert flattener.calls, "§4: an unexpected open position is flattened"
    assert result.outcome.state is ColdStartState.FLAT_ASSERTED
    assert result.outcome.admitted is True

    booked = [r for r in plane1.rows if r.kind is EventKind.COLD_START]
    assert booked, plane1.rows
    fields = booked[-1].fields
    assert fields["crash_gap"] == "1"
    assert "T-B" in fields["crash_gap_trades"]
    assert fields["projection_rows"] == "1"


def test_the_unexpected_position_is_flattened_BEFORE_registration_is_admitted() -> None:
    """§4: *"any unexpected open position ⇒ flatten to flat BEFORE any strategy
    registers."*

    "Before" is an ORDERING claim and the only thing that falsifies it is an
    attempt: a `register()` made while the inherited position is still open must
    RAISE, naming the state. Reading `registration_admitted()` would green-light a
    `register()` that ignored the flag.
    """
    unknown = position("T-B", "NQU6", 3)
    cold, _broker, flattener, _halt, _plane1, _projection = build(
        broker_positions=(unknown,)
    )
    with pytest.raises(RegistrationRefused) as before:
        cold.register("strat-nq", NOW)
    assert "provably-flat assertion has not passed" in str(before.value)
    assert flattener.calls == [], "nothing may have been flattened yet"

    cold.boot(NOW)

    assert flattener.calls, "the flatten fired"
    cold.register("strat-nq", NOW)
    assert cold.registered() == ("strat-nq",)


def test_an_UNTRADABLE_market_HOLDS_IN_HALT_and_admits_NOTHING() -> None:
    """The mandate's hazard, driven in its DANGEROUS direction.

    The risk is not a badly worded report. It is a reconciliation that reads
    "flatten refused" as "nothing to flatten" and admits registration against an
    inherited position — fail OPEN. So the assertions are on `admitted is False`,
    on an empty `flattened`, on the flatten executor never having been called,
    and on a `register()` that still raises.
    """
    unknown = position("T-B", "NQU6", 3)
    cold, _broker, flattener, halt, plane1, _projection = build(
        broker_positions=(unknown,), tradable=(False, "weekend: no session")
    )

    result = cold.boot(NOW)

    assert result.outcome.state is ColdStartState.HELD_IN_HALT
    assert result.outcome.admitted is False
    assert result.outcome.flattened == ()
    assert flattener.calls == [], "no market order may have been fired"
    assert halt.reasons and "weekend: no session" in halt.reasons[0]
    with pytest.raises(RegistrationRefused):
        cold.register("strat-nq", NOW)
    # And the gap is still RECORDED even though nothing could be done about it:
    assert [g.trade_id for g in unexpected(result.gap)] == ["T-B"]
    booked = [r for r in plane1.rows if r.kind is EventKind.COLD_START][-1]
    assert booked.fields["crash_gap"] == "1"


def test_flatten_to_flat_REFUSES_a_shut_market_rather_than_returning_empty() -> None:
    """R2-B's guard, re-driven at the primitive.

    It RAISES rather than returning `()`, so a caller that reached it directly
    cannot mistake a refusal for "there was nothing to close" — which is the
    exact confusion the fail-open direction needs.
    """
    from nixrisk.coldstart import (
        ColdStartError,  # pylint: disable=import-outside-toplevel
    )

    cold, _broker, flattener, _halt, _plane1, _projection = build(
        tradable=(False, "exchange halt")
    )
    with pytest.raises(ColdStartError) as excinfo:
        cold.flatten_to_flat(truth(position("T-B", "NQU6", 3)))
    assert "shut market" in str(excinfo.value)
    assert "exchange halt" in str(excinfo.value)
    assert flattener.calls == []


def test_a_flatten_that_does_not_reach_flat_still_admits_NOTHING() -> None:
    """Directive 4 / §4: known state beats optimal state.

    The flatten fired and the broker still reports the position. Fail closed.
    """
    cold, _broker, _flattener, halt, _plane1, _projection = build(
        broker_positions=(position("T-B", "NQU6", 3),), flatten_succeeds=False
    )
    result = cold.boot(NOW)
    assert result.outcome.state is ColdStartState.HELD_IN_HALT
    assert result.outcome.admitted is False
    assert halt.reasons


# --------------------------------------------- §12.5 — the HALT booked at boot


def test_a_HALT_that_arose_while_the_Limiter_was_DOWN_is_booked_at_next_boot(
    tmp_path,
) -> None:
    """§12.5, verbatim: *"The `HALT set` row is booked retroactively at next boot
    by cold-start reconciliation, same pattern as the Sentinel marker replay
    (§12.1): Plane-1 completeness holds without a second writer."*

    Two things are asserted and they are different claims. (a) The row lands,
    tagged `source=marker_replay` / `retroactive=true`, carrying the time the
    HALT HAPPENED and not the boot time. (b) It rides the SAME `Plane1Port` every
    other row does — `halt.replay_markers` takes the port as an argument, so
    there is no second author anywhere in the path.

    §12.5's own reasoning is the reason no second FLAG is needed: while the
    Limiter is down *"the system is already fail-closed — nothing reaches the
    broker without the Limiter"*. The retroactive row is for Plane-1
    COMPLETENESS, not for safety, and this test does not pretend otherwise.
    """
    marker = HaltMarker(tmp_path / "halt.marker")
    marker.record_set(
        HaltCause.CRASH_LOOP,
        "3 restarts in the window; relaunch stopped (§12.2)",
        ts=NOW - 3600.0,
        seq=1,
        boot="boot-that-died",
    )
    cold, _broker, _flattener, _halt, plane1, _projection = build(halt_marker=marker)

    result = cold.boot(NOW)

    assert len(result.retroactive_halts) == 1
    row = result.retroactive_halts[0]
    assert row.kind is EventKind.HALT_SET
    assert row.fields["source"] == SOURCE_REPLAY
    assert row.fields["retroactive"] == "true"
    assert row.ts == NOW - 3600.0, "the row carries when the HALT HAPPENED"
    assert row.fields["cause"] == HaltCause.CRASH_LOOP.value
    assert row in plane1.rows
    assert not (tmp_path / "halt.marker").exists(), "the marker is archived"


def test_a_HALT_that_DID_reach_Plane_1_is_not_booked_twice(tmp_path) -> None:
    """The control for the test above. Without it, "the row landed" would also be
    true of an implementation that books every marker every boot, and §9's
    append-only log would carry two HALTs where one happened."""
    marker = HaltMarker(tmp_path / "halt.marker")
    marker.record_set(HaltCause.STALE_DATA, "feed stale", NOW - 10.0, 1, "boot-a")
    marker.record_booked(HaltCause.STALE_DATA, NOW - 9.0, 1, "boot-a")
    cold, _broker, _flattener, _halt, _plane1, _projection = build(halt_marker=marker)
    assert cold.boot(NOW).retroactive_halts == ()


def test_no_halt_marker_at_all_books_nothing_and_is_not_an_error(tmp_path) -> None:
    """The ordinary case: a box whose Limiter never died mid-HALT."""
    cold, _broker, _flattener, _halt, _plane1, _projection = build(
        halt_marker=HaltMarker(tmp_path / "absent.marker")
    )
    assert cold.boot(NOW).retroactive_halts == ()


# ------------------------------------------- §12.1 — the Sentinel, in the same pass


def _sentinel_records() -> tuple[MarkerRecord, ...]:
    before = MarkerRecord(
        schema=1,
        phase=MarkerPhase.BEFORE,
        ts=NOW - 900.0,
        cause=TriggerCause.HEARTBEAT_LOST,
        symbols=("ESU6",),
        acks=(),
        sentinel_pid=4242,
        heartbeat_age_s=3.5,
    )
    after = MarkerRecord(
        schema=1,
        phase=MarkerPhase.AFTER,
        ts=NOW - 899.0,
        cause=TriggerCause.HEARTBEAT_LOST,
        symbols=("ESU6",),
        acks=(BrokerAck(symbol="ESU6", ok=True, detail="filled 2 @ market"),),
        sentinel_pid=4242,
        heartbeat_age_s=3.5,
    )
    return (before, after)


def test_the_Sentinel_marker_replays_INTO_THE_SAME_reconciliation(tmp_path) -> None:
    """§12.1:612 puts the replay in cold-start reconciliation, and it runs FIRST.

    Chronology, not convenience: what the Sentinel did happened on the PREVIOUS
    boot, so a log whose retroactive rows landed after this boot's own
    reconciliation would read as if the emergency followed the recovery. The
    assertion is on the ORDER of the rows in the sole writer's queue.
    """
    del tmp_path
    sentinel = FakeSentinelMarker(*_sentinel_records())
    cold, _broker, _flattener, _halt, plane1, _projection = build(sentinel=sentinel)

    result = cold.boot(NOW)

    assert result.sentinel_rows, "the marker replayed"
    assert sentinel.archived == 1
    tagged = [r for r in plane1.rows if r.fields.get("source") == SOURCE_SENTINEL]
    assert tagged, plane1.rows
    exits = [r for r in tagged if r.kind is EventKind.PROTECTIVE_EXIT]
    assert exits and exits[0].fields["trigger"] == FlattenTrigger.SENTINEL.value
    kinds = [r.kind for r in plane1.rows]
    assert kinds.index(EventKind.PROTECTIVE_EXIT) < kinds.index(EventKind.COLD_START)


def test_the_boot_row_records_every_half_of_the_pass(tmp_path) -> None:
    """One `cold_start_outcome` row that names the marker replay, the retroactive
    HALT, the rebuilt projection and the gap — so an operator reading §9's record
    can reconstruct the boot without the code."""
    marker = HaltMarker(tmp_path / "halt.marker")
    marker.record_set(HaltCause.OPERATOR, "operator HALT", NOW - 60.0, 1, "old-boot")
    known = position("T-A", "ESU6", 2)
    unknown = position("T-B", "NQU6", 3)
    cold, _broker, _flattener, _halt, plane1, _projection = build(
        broker_positions=(known, unknown),
        projection_positions=(known,),
        sentinel=FakeSentinelMarker(*_sentinel_records()),
        halt_marker=marker,
    )

    cold.boot(NOW)

    row = [r for r in plane1.rows if r.kind is EventKind.COLD_START][-1]
    assert row.fields["sentinel_rows"] != "0"
    assert row.fields["retroactive_halts"] == "1"
    assert row.fields["projection_rows"] == "1"
    assert row.fields["crash_gap"] == "1"
    assert row.fields["crash_gap_kinds"] == GapKind.UNEXPECTED.value


def test_a_boot_with_no_projection_port_still_reconciles_and_says_so() -> None:
    """The port is OPTIONAL — a box whose projection has never been built.

    It must not silently report a zero-row projection as agreement: the field
    says `absent`, which is a different fact from `0`.
    """
    broker = FakeBroker(truth(), (True, "open"))
    plane1 = RecordingPlane1()
    cold = ColdStart(broker, FakeFlattener(broker), FakeHalt(), plane1)
    result = cold.boot(NOW)
    assert result.projection == ()
    assert result.gap == ()
    row = [r for r in plane1.rows if r.kind is EventKind.COLD_START][-1]
    assert row.fields["projection_rows"] == "absent"
