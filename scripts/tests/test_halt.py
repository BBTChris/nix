"""ARC 033 / Stage 1 / D — the property suite for `scripts/nixrisk/halt.py`.

The gate (`checks/check_halt.py`) drives the seven properties end to end against
real collaborators. This suite is the narrower half: the refusals, the
arithmetic of the §12.5:632 hybrid, the marker codec, and the boot validation —
the cases where the interesting fact is that a call RAISES and NAMES why.

Nothing here writes to a production artifact: every marker file lives under
`tmp_path` (doctrine C.8).
"""
# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=too-few-public-methods,use-implicit-booleaness-not-comparison
# too-few-public-methods: the doubles are one-verb stand-ins for a frozen port's
# single relevant method. use-implicit-booleaness-not-comparison: `== ()` is the
# assertion this suite means — an auto_clear that returned None instead of an
# empty tuple is a DIFFERENT defect from one that cleared nothing, and `not x`
# cannot tell them apart.
# Each test's NAME states the property it drives, which is this suite's whole
# convention; a docstring restating the name would be a second spelling of one
# fact.

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.halt import (  # pylint: disable=wrong-import-position
    AWAITED,
    PRODUCERS,
    SOURCE_LIVE,
    SOURCE_REPLAY,
    ConditionStillActive,
    CooldownNotElapsed,
    HaltCause,
    HaltFlag,
    HaltMarker,
    KnobError,
    MarkerError,
    NotHalted,
    OperatorHaltPersists,
    replay_markers,
)
from nixrisk.seam import EventKind  # pylint: disable=wrong-import-position

#: ARC 034 (D3.195). Two NAMED boots, so the marker's `(boot, seq)` identity can
#: be driven deterministically. Production takes `uuid.uuid4().hex`; these exist
#: only so a test can be two processes.
BOOT_1 = "boot-0000000000000001"
BOOT_2 = "boot-0000000000000002"

FLOORS = {
    "stale_data": 60.0,
    "clock_skew": 300.0,
    "crash_loop": 900.0,
    "invariant_breach": 900.0,
    "aggregate_drift": 900.0,
}


class _Plane1:
    def __init__(self) -> None:
        self.rows: list[Any] = []
        self.syncs = 0

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        self.syncs += 1
        return len(self.rows)

    def pending(self) -> int:
        return len(self.rows)


class _Plane2:
    def __init__(self) -> None:
        self.lines: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event: str, **fields: Any) -> str:
        self.lines.append((event, fields))
        return event


@pytest.fixture
def planes() -> tuple[_Plane1, _Plane2]:
    return _Plane1(), _Plane2()


def _flag(planes: tuple[_Plane1, _Plane2], **kwargs: Any) -> HaltFlag:
    plane1, plane2 = planes
    return HaltFlag(plane1=plane1, plane2=plane2, floors=FLOORS, **kwargs)


# --------------------------------------------------------------------------
# The six setters (§12.5:631)
# --------------------------------------------------------------------------


def test_the_SETTERS_are_exactly_the_SIX_the_frozen_spec_names() -> None:
    assert {cause.value for cause in HaltCause} == {
        "stale_data",
        "clock_skew",
        "crash_loop",
        "invariant_breach",
        "aggregate_drift",
        "operator",
    }


def test_ONLY_operator_is_NOT_auto_clearable() -> None:
    assert [c for c in HaltCause if not c.auto_clearable] == [HaltCause.OPERATOR]


def test_the_FLAG_STARTS_CLEAR_and_a_SET_gates_with_a_REASON(planes) -> None:
    flag = _flag(planes)

    assert flag.is_set() == (False, "")

    flag.set(HaltCause.STALE_DATA, "price feed silent 4200ms", now=10.0)
    halted, why = flag.is_set()

    assert halted
    assert "stale_data" in why and "4200ms" in why


def test_a_SET_WITH_NO_REASON_still_books_a_reason_naming_the_rule(planes) -> None:
    plane1, _ = planes
    _flag(planes).set(HaltCause.CLOCK_SKEW, "   ", now=1.0)

    assert "§12.5:633" in plane1.rows[0].reason


def test_ONE_SET_produces_ONE_row_on_EACH_plane(planes) -> None:
    plane1, plane2 = planes
    _flag(planes).set(HaltCause.OPERATOR, "kill switch", now=1.0)

    assert [row.kind for row in plane1.rows] == [EventKind.HALT_SET]
    assert [event for event, _ in plane2.lines] == ["halt_set"]
    assert plane1.rows[0].fields["source"] == SOURCE_LIVE
    assert plane1.rows[0].fields["retroactive"] == "false"


def test_a_RESET_of_a_LIVE_cause_is_NOT_a_transition_and_books_NOTHING(planes) -> None:
    plane1, _ = planes
    flag = _flag(planes)
    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)

    repeat = flag.set(HaltCause.STALE_DATA, "still silent", now=2.0)

    assert repeat.booked is False
    assert repeat.action == "reaffirmed"
    assert len(plane1.rows) == 1


def test_a_SECOND_CAUSE_keeps_the_flag_SET_when_the_FIRST_clears(planes) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.OPERATOR, "kill switch", now=1.0)
    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)
    flag.condition_cleared(HaltCause.STALE_DATA, 2.0)

    flag.auto_clear(1e9)

    halted, why = flag.is_set()
    assert halted, "a stale-data clear wiped an operator HALT"
    assert "operator" in why


# --------------------------------------------------------------------------
# The hybrid auto-clear (§12.5:632) and the operator-only clear (§12.5:633)
# --------------------------------------------------------------------------


def test_a_CLEAR_before_the_CONDITION_cleared_is_REFUSED_and_names_the_hybrid(
    planes,
) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)

    with pytest.raises(ConditionStillActive) as exc:
        flag.clear(HaltCause.STALE_DATA, "premature", now=1e9)

    assert "condition-clear" in str(exc.value)


def test_a_CLEAR_before_the_FLOOR_ran_is_REFUSED_and_names_the_floor(planes) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)
    flag.condition_cleared(HaltCause.STALE_DATA, 100.0)

    with pytest.raises(CooldownNotElapsed) as exc:
        flag.clear(HaltCause.STALE_DATA, "too soon", now=100.0 + 59.0)

    assert "floor" in str(exc.value)


def test_the_FLOOR_runs_from_the_LATER_of_set_and_condition_clear(planes) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.STALE_DATA, "silent", now=1000.0)
    flag.condition_cleared(HaltCause.STALE_DATA, 2000.0)

    assert flag.eligible_at(HaltCause.STALE_DATA) == 2000.0 + FLOORS["stale_data"]


def test_a_CONDITION_THAT_RE_ARMS_cancels_the_pending_clear(planes) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)
    flag.condition_cleared(HaltCause.STALE_DATA, 2.0)
    flag.condition_returned(HaltCause.STALE_DATA)

    assert flag.eligible_at(HaltCause.STALE_DATA) is None
    assert flag.auto_clear(1e9) == ()
    assert flag.is_set()[0]


def test_the_AUTO_CLEAR_fires_once_BOTH_halves_hold_and_books_the_row(planes) -> None:
    plane1, plane2 = planes
    flag = _flag(planes)
    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)
    flag.condition_cleared(HaltCause.STALE_DATA, 100.0)

    assert flag.auto_clear(100.0 + 59.9) == ()
    made = flag.auto_clear(100.0 + FLOORS["stale_data"])

    assert [t.cause for t in made] == [HaltCause.STALE_DATA]
    assert flag.is_set() == (False, "")
    assert plane1.rows[-1].kind is EventKind.HALT_CLEARED
    assert plane2.lines[-1][0] == "halt_cleared"


def test_an_OPERATOR_HALT_survives_an_auto_clear_sweep_at_the_end_of_time(
    planes,
) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.OPERATOR, "kill switch", now=1.0)

    assert flag.auto_clear(1e12) == ()
    assert flag.is_set()[0]


def test_condition_cleared_on_an_OPERATOR_HALT_is_REFUSED(planes) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.OPERATOR, "kill switch", now=1.0)

    with pytest.raises(OperatorHaltPersists) as exc:
        flag.condition_cleared(HaltCause.OPERATOR, 2.0)

    assert "only by operator" in str(exc.value)


def test_the_AUTO_CLEAR_ROUTE_refuses_an_OPERATOR_HALT_by_name(planes) -> None:
    flag = _flag(planes)
    flag.set(HaltCause.OPERATOR, "kill switch", now=1.0)

    with pytest.raises(OperatorHaltPersists) as exc:
        flag.clear(HaltCause.OPERATOR, "auto", now=1e12)

    assert "clear_by_operator" in str(exc.value)


def test_ONLY_clear_by_operator_clears_an_OPERATOR_HALT(planes) -> None:
    plane1, _ = planes
    flag = _flag(planes)
    flag.set(HaltCause.OPERATOR, "kill switch", now=1.0)

    transition = flag.clear_by_operator(
        HaltCause.OPERATOR, "operator restored", now=2.0
    )

    assert flag.is_set() == (False, "")
    assert transition.action == "HALT clear"
    assert plane1.rows[-1].fields["by_operator"] == "True"


def test_clearing_a_cause_that_is_NOT_SET_is_refused(planes) -> None:
    with pytest.raises(NotHalted):
        _flag(planes).clear(HaltCause.STALE_DATA, "nothing to clear", now=1.0)


# --------------------------------------------------------------------------
# Boot validation of the §12.5:632 floors
# --------------------------------------------------------------------------


def test_a_FLOOR_for_OPERATOR_is_REFUSED_at_construction(planes) -> None:
    plane1, plane2 = planes

    with pytest.raises(KnobError) as exc:
        HaltFlag(plane1=plane1, plane2=plane2, floors={**FLOORS, "operator": 60})

    assert "operator" in str(exc.value)


def test_a_MISSING_FLOOR_is_REFUSED_because_it_would_read_as_zero(planes) -> None:
    plane1, plane2 = planes
    short = {k: v for k, v in FLOORS.items() if k != "crash_loop"}

    with pytest.raises(KnobError) as exc:
        HaltFlag(plane1=plane1, plane2=plane2, floors=short)

    assert "crash_loop" in str(exc.value)


@pytest.mark.parametrize("bad", [0, -1, True, "60"])
def test_a_NON_POSITIVE_or_NON_NUMERIC_floor_is_REFUSED(planes, bad) -> None:
    plane1, plane2 = planes

    with pytest.raises(KnobError):
        HaltFlag(plane1=plane1, plane2=plane2, floors={**FLOORS, "stale_data": bad})


def test_the_SHIPPED_CONFIG_constructs_the_machine(planes) -> None:
    raw = json.loads((REPO / "risks/limiter.config.json").read_text(encoding="utf-8"))
    plane1, plane2 = planes

    flag = HaltFlag(plane1=plane1, plane2=plane2, floors=raw["halt_cooldown_floor_s"])

    assert set(flag.floors) == {c for c in HaltCause if c.auto_clearable}


def test_the_ONSET_SWEEP_needs_BOTH_halves_or_NEITHER(planes) -> None:
    plane1, plane2 = planes

    class _Sweep:
        def cancel_entries_on_onset(self, cause, pending):
            return (cause, pending)

    with pytest.raises(KnobError) as exc:
        HaltFlag(plane1=plane1, plane2=plane2, floors=FLOORS, onset=_Sweep())

    assert "pending" in str(exc.value)


def test_an_UNWIRED_SWEEP_says_so_on_the_row_rather_than_silently(planes) -> None:
    plane1, _ = planes
    flag = _flag(planes)

    flag.set(HaltCause.STALE_DATA, "silent", now=1.0)

    assert flag.sweep_wired is False
    assert plane1.rows[0].fields["onset_sweep"] == "not_wired"


def test_the_SWEEP_runs_on_the_ONSET_EDGE_ONLY(planes) -> None:
    plane1, plane2 = planes
    calls: list[Any] = []

    class _Sweep:
        def cancel_entries_on_onset(self, cause, pending):
            calls.append((cause, tuple(pending)))

    class _Book:
        def pending_entries(self):
            return ("COID-1",)

    flag = HaltFlag(
        plane1=plane1,
        plane2=plane2,
        floors=FLOORS,
        onset=_Sweep(),
        pending=_Book(),
    )
    first = flag.set(HaltCause.STALE_DATA, "silent", now=1.0)
    second = flag.set(HaltCause.CLOCK_SKEW, "skew", now=2.0)

    assert first.swept is True
    assert second.swept is False
    assert len(calls) == 1
    assert calls[0][0].value == "halt_onset"


# --------------------------------------------------------------------------
# The §12.1-pattern marker and the §12.5:637 retroactive booking
# --------------------------------------------------------------------------


def test_the_MARKER_records_the_SET_before_the_row_reaches_plane_1(
    tmp_path: Path, planes
) -> None:
    plane1, plane2 = planes
    order: list[str] = []

    class _Watching(_Plane1):
        def enqueue(self, row: Any) -> None:
            order.append("plane1")
            super().enqueue(row)

    class _WatchingMarker(HaltMarker):
        def record_set(self, cause, reason, ts, seq, boot):
            order.append("marker")
            super().record_set(cause, reason, ts, seq, boot)

    del plane1
    flag = HaltFlag(
        plane1=_Watching(),
        plane2=plane2,
        floors=FLOORS,
        marker=_WatchingMarker(tmp_path / "halt.marker"),
    )
    flag.set(HaltCause.CRASH_LOOP, "3 restarts in 60s", now=5.0)

    assert order[:2] == ["marker", "plane1"], (
        "the marker must be written BEFORE the row is booked, or a process that "
        "dies in between leaves nothing for §12.5:637 to recover"
    )


def test_an_UNBOOKED_MARKER_replays_TAGGED_and_KEEPS_the_original_stamp(
    tmp_path: Path,
) -> None:
    marker = HaltMarker(tmp_path / "halt.marker")
    marker.record_set(HaltCause.CRASH_LOOP, "3 restarts in 60s", 1234.5, 1, BOOT_1)
    plane1 = _Plane1()

    rows = replay_markers(marker, plane1, 999999.0)

    assert len(rows) == 1
    row = rows[0]
    assert row.kind is EventKind.HALT_SET
    assert row.ts == 1234.5, "a retroactive row must carry WHEN the HALT happened"
    assert row.fields["source"] == SOURCE_REPLAY
    assert row.fields["retroactive"] == "true"
    assert row.fields["booked_at"] == repr(999999.0)
    assert plane1.syncs == 1


def test_a_BOOKED_MARKER_replays_NOTHING_so_the_log_never_doubles(
    tmp_path: Path,
) -> None:
    marker = HaltMarker(tmp_path / "halt.marker")
    marker.record_set(HaltCause.OPERATOR, "kill switch", 10.0, 1, BOOT_1)
    marker.record_booked(HaltCause.OPERATOR, 10.0, 1, BOOT_1)
    plane1 = _Plane1()

    assert replay_markers(marker, plane1, 20.0) == ()
    assert plane1.rows == []


def test_the_MARKER_is_ARCHIVED_so_a_SECOND_boot_replays_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "halt.marker"
    marker = HaltMarker(path)
    marker.record_set(HaltCause.STALE_DATA, "silent", 1.0, 1, BOOT_1)
    plane1 = _Plane1()

    replay_markers(marker, plane1, 2.0)

    assert not path.exists()
    assert list(tmp_path.glob("halt.marker.*.replayed"))
    assert replay_markers(HaltMarker(path), plane1, 3.0) == ()


def test_TWO_BOOTS_sharing_a_SEQ_do_not_suppress_each_other(tmp_path: Path) -> None:
    """ARC 034 (D3.195). §12.5:637's Plane-1 completeness across a restart.

    THE DEFECT THIS DRIVES, and it is a money path. The marker file is
    append-only ACROSS PROCESSES — the case §12.5:634 describes is the Limiter
    being the dead process — while `HaltFlag._seq` is a per-instance counter
    starting at 0. So boot 1's first HALT and boot 2's first HALT both wrote
    `seq=1`, `replay_markers` matched `set` against `booked` on `seq` alone,
    and boot 1's `booked` therefore booked boot 2's UNBOOKED `set` out of
    existence. `marker.archive` then renamed the file away, so the row was not
    merely unbooked, it was unrecoverable.

    The scenario below is the minimum that exhibits it: boot 1 declares a HALT
    that DOES reach Plane 1 (set + booked), boot 2 declares a DIFFERENT HALT
    that does NOT (set only), and both carry `seq=1`.
    """
    path = tmp_path / "halt.marker"
    marker = HaltMarker(path)
    marker.record_set(HaltCause.OPERATOR, "kill switch", 10.0, 1, BOOT_1)
    marker.record_booked(HaltCause.OPERATOR, 10.0, 1, BOOT_1)
    marker.record_set(HaltCause.CLOCK_SKEW, "ntp stepped 4s", 20.0, 1, BOOT_2)

    plane1 = _Plane1()
    rows = replay_markers(HaltMarker(path), plane1, 30.0)

    assert len(rows) == 1, (
        "boot 2's unbooked HALT must replay; on `seq` alone boot 1's `booked` "
        f"suppressed it and this returned 0 rows (got {len(rows)})"
    )
    row = rows[0]
    assert row.fields["cause"] == HaltCause.CLOCK_SKEW.value, (
        "the replayed row must be boot 2's HALT, not boot 1's — matching on "
        f"`seq` alone cannot tell them apart (got {row.fields['cause']!r})"
    )
    assert row.ts == 20.0, "the retroactive row carries WHEN the HALT happened"
    assert row.fields["boot"] == BOOT_2, (
        "the replayed row must name the boot that DECLARED it, so §9's reader "
        "can attribute it to the process that saw the condition"
    )
    assert row.fields["seq"] == "1", "the per-boot counter is unchanged"


def test_a_marker_record_with_NO_BOOT_ID_is_REFUSED_and_never_defaulted(
    tmp_path: Path,
) -> None:
    """ARC 034 (D3.195). A missing identity is loud, not an empty shared one.

    Defaulting the absent field to `""` would put every such record into ONE
    identity space and quietly rebuild the collision the field exists to
    prevent — the failure would look exactly like a working replay.
    """
    path = tmp_path / "halt.marker"
    path.write_text(
        '{"cause":"operator","reason":"r","rec":"set","seq":1,"ts":1.0}\n',
        encoding="utf-8",
    )
    with pytest.raises(MarkerError) as exc:
        HaltMarker(path).entries()
    assert "refusing to skip" in str(exc.value), str(exc.value)
    assert "boot" in str(exc.value), (
        "the refusal must name the MISSING FIELD, not merely the line number — "
        f"an exit code is a shared namespace (got {exc.value!r})"
    )


def test_a_LIVE_HALT_marker_pair_carries_ONE_boot_id_per_process(
    tmp_path: Path, planes
) -> None:
    """The machine's own writes carry its boot id, and two machines differ."""
    plane1, plane2 = planes
    del plane1
    first = HaltFlag(
        plane1=_Plane1(),
        plane2=plane2,
        floors=FLOORS,
        marker=HaltMarker(tmp_path / "halt.marker"),
    )
    first.set(HaltCause.OPERATOR, "kill switch", now=5.0)
    second = HaltFlag(
        plane1=_Plane1(),
        plane2=plane2,
        floors=FLOORS,
        marker=HaltMarker(tmp_path / "halt.marker"),
    )
    second.set(HaltCause.CLOCK_SKEW, "ntp stepped", now=6.0)

    entries = HaltMarker(tmp_path / "halt.marker").entries()
    seqs = {entry.seq for entry in entries}
    boots = {entry.boot for entry in entries}
    assert seqs == {1}, f"premise: both processes wrote seq=1 ({seqs})"
    assert len(boots) == 2, (
        "two HaltFlag instances must not share a boot id, or `(boot, seq)` is "
        f"no more of an identity than `seq` was ({boots})"
    )
    assert all(len(boot) >= 16 for boot in boots), (
        f"a guessable boot id rebuilds the collision it prevents ({boots})"
    )


def test_a_DAMAGED_MARKER_RECORD_is_reported_and_never_skipped(tmp_path: Path) -> None:
    path = tmp_path / "halt.marker"
    marker = HaltMarker(path)
    marker.record_set(HaltCause.STALE_DATA, "silent", 1.0, 1, BOOT_1)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    with pytest.raises(MarkerError) as exc:
        marker.entries()

    assert "refusing to skip" in str(exc.value)


def test_an_ABSENT_MARKER_is_the_ORDINARY_case_and_is_not_an_error(
    tmp_path: Path,
) -> None:
    plane1 = _Plane1()

    assert replay_markers(HaltMarker(tmp_path / "none"), plane1, 1.0) == ()
    assert plane1.rows == []


def test_the_LIVE_PATH_writes_BOTH_marker_halves(tmp_path: Path, planes) -> None:
    plane1, plane2 = planes
    marker = HaltMarker(tmp_path / "halt.marker")
    flag = HaltFlag(plane1=plane1, plane2=plane2, floors=FLOORS, marker=marker)

    flag.set(HaltCause.AGGREGATE_DRIFT, "drift +900", now=1.0)

    assert [entry.rec for entry in marker.entries()] == ["set", "booked"]
    assert replay_markers(marker, plane1, 2.0) == ()


# --------------------------------------------------------------------------
# The producer claims are the SUBJECT's, and they are non-empty
# --------------------------------------------------------------------------


def test_the_PRODUCER_and_AWAITED_maps_together_cover_every_cause() -> None:
    covered = set(PRODUCERS) | set(AWAITED)

    assert covered == set(HaltCause)


def test_CRASH_LOOP_is_declared_AWAITED_because_supervision_is_R4B() -> None:
    assert HaltCause.CRASH_LOOP not in PRODUCERS
    assert HaltCause.CRASH_LOOP in AWAITED
    assert not any((REPO / rel).exists() for rel in AWAITED[HaltCause.CRASH_LOOP])
