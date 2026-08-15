"""ARC 032 Stage 1 / C — unit suite for `scripts/nixalloc/lifecycle.py`.

The property: **capital eligibility follows the PUBLISHED per-position lifecycle
state** (`docs/nics_risk_subsystem_spec_v1.3.md` §4:284-286 — *"a strategy
mid-recovery reads as in-flight-closing, NOT normal-and-available, so it is
never counted eligible for new capital while dying"*).

These are the module's own rules driven directly. The TRANSITION — the same rule
driven across a moving snapshot sequence produced by the real Limiter-side
producer and consumed through the real mirror over a real socket — is
`checks/check_allocator_lifecycle.py` ARM 2, because a transition proven only
against pictures this file constructs is a transition proven against this file.
`test_the_eligibility_VALUE_moves_with_the_published_state` below is the
in-process shadow of that arm and is deliberately not a substitute for it.

Every assertion names the REASON, never a bare boolean: three different
snapshots produce the same `False` and only the reason tells them apart (§18).
"""
# pylint: disable=invalid-name,redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test on purpose. `== ()` is asserted
# rather than `not x` because an empty tuple and a falsey non-tuple are
# different outcomes here, and the distinction is the assertion.
# pylint: disable=too-few-public-methods,too-many-arguments
# The stand-ins below are one-verb doubles for a frozen port, and `_row`
# takes exactly the published row's own fields — see its docstring for why
# there is ONE constructor in this file rather than fifteen.

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixalloc import contention, lifecycle  # pylint: disable=wrong-import-position
from nixalloc.seam import (  # pylint: disable=wrong-import-position
    FinancialPicture,
    MirrorSnapshot,
    MirrorState,
    PositionRow,
    PositionState,
)

DYING = "strat-dying"
HEALTHY = "strat-healthy"
SYMBOL = "MESU6"


def _row(
    trade_id: str,
    *,
    state: PositionState = PositionState.OPEN,
    strategy_id: str = DYING,
    symbol: str = SYMBOL,
    size: int = 2,
    margin: float = 2_000.0,
) -> PositionRow:
    """THE one `PositionRow` constructor in this file.

    One helper and not a scattered constructor because the published row is
    being widened in this same arc (`nixalloc/seam.py` records the planned
    `SEAM_REV 1.1.0`): a widening should cost one edit here, not fifteen.
    """
    return PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id=strategy_id,
        size=size,
        margin=margin,
        state=state,
        # ARC 032 / Phase 0.4 landed the widening this helper was written in
        # anticipation of, and it cost exactly the one edit the docstring
        # promised. A positive literal and not 0: this suite is about §4's
        # lifecycle screen, and a row that reads as UNPRICED to §7's cap would
        # make an unrelated finding ride along with every eligibility case.
        stop_distance=20,
    )


def _picture(*rows: PositionRow, version: int = 1) -> FinancialPicture:
    """One published snapshot carrying `rows`. Aggregates kept self-consistent."""
    open_margin = sum(
        row.margin
        for row in rows
        if row.state in (PositionState.OPEN, PositionState.CLOSING)
    )
    return FinancialPicture(
        version=version,
        published_ts=1_000.0,
        balance=100_000.0,
        positions=rows,
        margin_per_contract=MappingProxyType({SYMBOL: 1_000.0}),
        sum_open_margin=open_margin,
        sum_reservations=0.0,
        committed=open_margin,
        deployable=70_000.0 - open_margin,
    )


def _contenders() -> list[contention.Contender]:
    """The dying strategy arrives FIRST, so FCFS would put it at the head."""
    return [
        contention.Contender(strategy_id=DYING, symbol=SYMBOL, arrival_seq=1),
        contention.Contender(strategy_id=HEALTHY, symbol=SYMBOL, arrival_seq=2),
    ]


# ==========================================================================
# The rule itself (§4:284-286)
# ==========================================================================


def test_the_screened_set_is_CLOSING_and_NOT_closed() -> None:
    """A completed close is not a close IN FLIGHT.

    §4:283 makes the finished flatten `positions→closed`, so admitting `CLOSED`
    into the screened set would refuse capital to a strategy that is flat — the
    wrong direction for a permissive component (§2), and one no gate that only
    drove the closing case would ever notice.
    """
    assert lifecycle.IN_FLIGHT_CLOSING == frozenset({PositionState.CLOSING})
    assert PositionState.CLOSED not in lifecycle.IN_FLIGHT_CLOSING


@pytest.mark.parametrize(
    "state", [PositionState.RESERVED, PositionState.PENDING, PositionState.OPEN]
)
def test_a_LIVE_but_not_closing_strategy_is_ELIGIBLE(state: PositionState) -> None:
    """Reserved, pending and open are normal-and-available (§3:157)."""
    verdict = lifecycle.eligibility(_picture(_row("T1", state=state)), DYING)
    assert verdict.eligible is True
    assert state.value in verdict.reason
    assert verdict.closing_trades == ()


def test_a_strategy_with_a_CLOSING_row_is_REFUSED_and_the_reason_names_it() -> None:
    """§4:284-286, the whole rule, and §18's reason on the refusal."""
    picture = _picture(
        _row("T1", state=PositionState.OPEN),
        _row("T2", state=PositionState.CLOSING),
        version=9,
    )
    verdict = lifecycle.eligibility(picture, DYING)
    assert verdict.eligible is False
    assert verdict.closing_trades == ("T2",)
    assert verdict.snapshot_version == 9
    assert "T2" in verdict.reason
    assert "IN-FLIGHT-CLOSING" in verdict.reason
    assert "§4:284-286" in verdict.reason
    assert "never counted eligible for new capital while dying" in verdict.reason


def test_ONE_closing_row_among_several_refuses_the_whole_strategy() -> None:
    """§4:285 refuses the STRATEGY, not the position — half dying is dying."""
    picture = _picture(
        _row("T1", state=PositionState.OPEN),
        _row("T2", state=PositionState.RESERVED),
        _row("T3", state=PositionState.CLOSING),
    )
    verdict = lifecycle.eligibility(picture, DYING)
    assert verdict.eligible is False
    assert verdict.rows == 3
    assert verdict.observed_states == ("closing", "open", "reserved")


def test_a_FLAT_strategy_is_eligible_and_the_reason_says_FLAT_not_screened() -> None:
    """§7.12/1: "no closing row" is true vacuously for a strategy with no rows."""
    verdict = lifecycle.eligibility(_picture(), DYING)
    assert verdict.eligible is True
    assert verdict.rows == 0
    assert "owns no published row" in verdict.reason


def test_the_refusal_is_PER_STRATEGY_and_never_per_picture() -> None:
    """A co-tenant on the same snapshot must not be refused by proximity.

    Without this, a screen that refused every strategy the moment ANY row was
    closing would pass every test that only watched the dying one — and would
    stop the whole book trading on one strategy's recovery.
    """
    picture = _picture(
        _row("T1", state=PositionState.CLOSING),
        _row("T2", state=PositionState.OPEN, strategy_id=HEALTHY),
    )
    assert lifecycle.eligibility(picture, DYING).eligible is False
    assert lifecycle.eligibility(picture, HEALTHY).eligible is True


def test_the_eligibility_VALUE_moves_with_the_published_state() -> None:
    """The transition, in process: eligible -> refused -> eligible again.

    The falsifier a constant screen cannot survive. A gate that only ever saw
    step one would pass against `return True`; one that only saw step two would
    pass against `return False`.
    """
    sequence = [
        _picture(_row("T1", state=PositionState.OPEN), version=1),
        _picture(_row("T1", state=PositionState.CLOSING), version=2),
        _picture(version=3),
    ]
    verdicts = [lifecycle.eligibility(picture, DYING) for picture in sequence]
    assert [verdict.eligible for verdict in verdicts] == [True, False, True]
    assert [verdict.snapshot_version for verdict in verdicts] == [1, 2, 3]
    assert len({verdict.reason for verdict in verdicts}) == len(verdicts)


def test_eligibility_by_strategy_names_only_strategies_the_table_carries() -> None:
    """§2: registration is the Limiter's, so this never invents a strategy."""
    picture = _picture(
        _row("T1", state=PositionState.CLOSING),
        _row("T2", state=PositionState.OPEN, strategy_id=HEALTHY),
    )
    report = lifecycle.eligibility_by_strategy(picture)
    assert set(report) == {DYING, HEALTHY}
    assert report[DYING].eligible is False
    assert report[HEALTHY].eligible is True


def test_strategy_rows_reads_only_the_owning_strategys_rows() -> None:
    """§3:159 keys the published row by trade_id and carries the strategy_id."""
    picture = _picture(
        _row("T1"),
        _row("T2", strategy_id=HEALTHY),
        _row("T3", state=PositionState.OPEN),
    )
    assert {row.trade_id for row in lifecycle.strategy_rows(picture, DYING)} == {
        "T1",
        "T3",
    }


# ==========================================================================
# FAIL CLOSED on the mirror (§12.7)
# ==========================================================================


@pytest.mark.parametrize(
    "state", [MirrorState.EMPTY, MirrorState.PARTIAL, MirrorState.STALE]
)
def test_a_mirror_that_is_not_FRESH_REFUSES_and_names_the_state(
    state: MirrorState,
) -> None:
    """§12.7 never sizes on a half-built mirror; an unread mirror never admits."""
    snapshot = MirrorSnapshot(state=state, picture=None, reason="planted")
    verdict = lifecycle.eligibility_from_mirror(snapshot, DYING)
    assert verdict.eligible is False
    assert state.value.upper() in verdict.reason
    assert "planted" in verdict.reason
    assert verdict.snapshot_version is None


def test_a_STALE_mirror_still_holding_a_picture_REFUSES() -> None:
    """The dangerous case: a picture IS held and it is past the ceiling (§6.4).

    Reading the held picture anyway is the "carry on with the last value"
    §6.4 forbids by name, and it is the branch a `picture is None` test misses.
    """
    snapshot = MirrorSnapshot(
        state=MirrorState.STALE, picture=_picture(_row("T1")), reason="aged out"
    )
    assert lifecycle.eligibility_from_mirror(snapshot, DYING).eligible is False


def test_a_FRESH_mirror_delegates_to_the_same_rule() -> None:
    """One rule, two entry points — never a second freshness or screening rule."""
    picture = _picture(_row("T1", state=PositionState.CLOSING), version=4)
    snapshot = MirrorSnapshot(state=MirrorState.FRESH, picture=picture, reason="fresh")
    assert lifecycle.eligibility_from_mirror(snapshot, DYING) == lifecycle.eligibility(
        picture, DYING
    )


class _Mirror:
    """A `MirrorPort` returning a scripted snapshot, and counting its reads."""

    def __init__(self, snapshot: MirrorSnapshot) -> None:
        self._snapshot = snapshot
        self.reads = 0

    def snapshot(self) -> MirrorSnapshot:
        """The scripted snapshot, and one more read on the counter."""
        self.reads += 1
        return self._snapshot

    def version(self) -> int:
        """Negative when nothing is held — the seam's own contract."""
        return -1 if self._snapshot.picture is None else self._snapshot.picture.version


def test_MirrorLifecycle_pin_takes_ONE_read_and_pins_the_version() -> None:
    """Two contenders in one race must be screened against ONE version (§3)."""
    picture = _picture(_row("T1", state=PositionState.CLOSING), version=6)
    mirror = _Mirror(MirrorSnapshot(MirrorState.FRESH, picture, "fresh"))
    pinned = lifecycle.MirrorLifecycle(mirror).pin()
    assert pinned is not None
    assert mirror.reads == 1
    assert pinned.eligibility(DYING).snapshot_version == 6
    assert pinned.eligibility(HEALTHY).snapshot_version == 6
    assert mirror.reads == 1, "pinning re-read the mirror per contender"


def test_MirrorLifecycle_pin_returns_None_when_there_is_nothing_FRESH() -> None:
    """A pin over a stale mirror would pin a picture §6.4 says to refuse."""
    mirror = _Mirror(MirrorSnapshot(MirrorState.EMPTY, None, "never heard"))
    assert lifecycle.MirrorLifecycle(mirror).pin() is None
    assert lifecycle.MirrorLifecycle(mirror).eligibility(DYING).eligible is False


# ==========================================================================
# The contention screen (§4 in front of §6.6)
# ==========================================================================


def test_rank_eligible_drops_the_dying_and_keeps_the_healthy() -> None:
    """The screen is not "refuse everything", and the refusal carries its reason."""
    picture = _picture(
        _row("T1", state=PositionState.CLOSING),
        _row("T2", state=PositionState.OPEN, strategy_id=HEALTHY),
        version=11,
    )
    ranking = contention.rank_eligible(
        _contenders(), None, lifecycle.PictureLifecycle(picture)
    )
    assert [item.strategy_id for item in ranking.ordering] == [HEALTHY]
    assert [item.contender.strategy_id for item in ranking.refused] == [DYING]
    assert ranking.refused[0].snapshot_version == 11
    assert "T1" in ranking.refused[0].reason
    assert ranking.screened == 2


def test_without_a_closing_row_rank_eligible_matches_rank_exactly() -> None:
    """A screen that changed the ORDER would be a second §6.6 rule (C.9)."""
    picture = _picture(_row("T1", state=PositionState.OPEN))
    screened = contention.rank_eligible(
        _contenders(), None, lifecycle.PictureLifecycle(picture)
    )
    plain = contention.rank(_contenders(), None)
    assert [c.strategy_id for c in screened.ordering] == [
        c.strategy_id for c in plain.ordering
    ]
    assert screened.policy is plain.policy
    assert screened.refused == ()


def test_rank_leaves_refused_EMPTY_because_it_screens_NOTHING() -> None:
    """An empty `refused` from `rank` means "nothing was screened", not "all passed"."""
    assert contention.rank(_contenders(), None).refused == ()
    assert contention.rank(_contenders(), None).screened == 2


def test_a_lifecycle_view_that_RAISES_refuses_rather_than_propagating() -> None:
    """Fail closed: an unanswerable safety screen must never admit (§12.7)."""

    class _Broken:
        """A `LifecycleViewPort` whose picture cannot be read at all."""

        def eligibility(self, strategy_id: str):
            """Never answers. §12.7's unreadable mirror, one layer up."""
            raise RuntimeError(f"segment gone for {strategy_id}")

    ranking = contention.rank_eligible(_contenders(), None, _Broken())
    assert ranking.ordering == ()
    assert len(ranking.refused) == 2
    assert "RuntimeError" in ranking.refused[0].reason
    assert "REFUSES capital rather than admitting it" in ranking.refused[0].reason
    assert ranking.refused[0].verdict is None
    assert ranking.refused[0].snapshot_version is None


def test_the_lifecycle_argument_is_REQUIRED_and_has_no_default() -> None:
    """§7.12/4: a forgotten screen must not be spelled like an absent one."""
    with pytest.raises(TypeError):
        contention.rank_eligible(  # pylint: disable=no-value-for-parameter
            _contenders(),
            None,  # type: ignore[call-arg]
        )


def test_the_screen_beats_FCFS_rather_than_being_overridden_by_it() -> None:
    """The dying contender arrived FIRST, so FCFS would hand it the head."""
    open_picture = _picture(_row("T1", state=PositionState.OPEN))
    leading = contention.rank_eligible(
        _contenders(), None, lifecycle.PictureLifecycle(open_picture)
    )
    assert leading.ordering[0].strategy_id == DYING, "FCFS did not put it first"
    dying_picture = _picture(_row("T1", state=PositionState.CLOSING))
    screened = contention.rank_eligible(
        _contenders(), None, lifecycle.PictureLifecycle(dying_picture)
    )
    assert DYING not in [item.strategy_id for item in screened.ordering]


# ==========================================================================
# The boundary: reflects, never drives (§2, §4:260-274)
# ==========================================================================


@pytest.mark.parametrize(
    "verb",
    ["flatten", "deregister", "kill", "relaunch", "quarantine", "heartbeat", "archive"],
)
def test_the_module_exposes_NO_recovery_driving_verb(verb: str) -> None:
    """§4:260-274 gives every one of these to the Limiter and the supervisor."""
    exposed = [name.lstrip("_").lower() for name in dir(lifecycle)]
    assert not [
        name for name in exposed if name == verb or name.startswith(f"{verb}_")
    ], f"the Allocator's lifecycle module exposes a {verb!r} verb"


def test_the_module_states_BOTH_boundaries_in_ONE_place_each() -> None:
    """Directive 3: the gate PRINTS these constants rather than restating them."""
    assert "R5" in lifecycle.RECOVERY_PRODUCER
    assert "flatten.py" in lifecycle.RECOVERY_PRODUCER
    assert "DOES NOT EXIST" in lifecycle.RECOVERY_PRODUCER
    assert "Scoring process" in lifecycle.SCORE_BOUNDARY
    assert "no persistence, no archive and no EMA" in lifecycle.SCORE_BOUNDARY


def test_the_module_answers_the_standing_question_in_its_docstring() -> None:
    """`debug.md` §7.12 is required of every gate at the point it is built."""
    doc = lifecycle.__doc__ or ""
    assert "THE STANDING QUESTION" in doc
    assert doc.count("CLOSED") >= 3, "a route with no mechanism is not closed"
