"""ARC 031 / Stage 2 — the three Stage-1 pieces composed, driven end to end.

Stage 1's three sub-agents each built against the frozen seam with their own
doubles, on purpose, so **none of them measured the others**. This module is
where they meet.

2.1 drives one simulated Limiter snapshot through six paths: a clean size, a
headroom-capped size-down, a bucket-capped size-down, a dead-signal drop, a
zero-stop deny, and a stale-mirror refusal.
2.2 drives §4's partial-fill reflection — the over-reserved capital returning
to `deployable` the INSTANT reality comes in under the reservation.
2.3 proves, across every path 2.1 drives, that nothing the Allocator emits
reaches a broker without the Limiter's pass.

**What composing them FOUND, and neither Stage-1 gate could:** §7's cap needs
each held position's stop distance and the published `PositionRow` carries
none (CHECK-DEBT D3.136). The tests below drive the cap with an explicit
out-of-band stop table AND with the honest empty one, and assert that the
second reports `cap_incomplete` rather than a clean ceiling over an empty
bucket.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=too-many-lines
# Over the 1000-line ceiling since ARC 032, and the excess is the BEFORE half of
# D3.136's discharge: checking the pre-widening modules out of git and loading
# them without letting `sys.modules` hand back the widened ones. Splitting it
# into a second module would put the two halves of one measurement in two
# files, which is the thing that makes a before/after drift apart.

from __future__ import annotations

import dataclasses
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent

#: Throwaway checkouts of the pre-widening revision, removed at session end.
_PRE032_TREES: list[Path] = []


@pytest.fixture(scope="session", autouse=True)
def _remove_pre032_checkouts():
    """Delete every temporary pre-widening checkout this module made.

    Session-scoped and autouse so it fires even when the before/after test is
    the only one that ran, and so a suite that leaves work behind on the disk
    is not the arc's cleanup problem later.
    """
    yield
    for root in _PRE032_TREES:
        shutil.rmtree(root, ignore_errors=True)
    _PRE032_TREES.clear()


sys.path.insert(0, str(REPO / "scripts"))

from nixalloc import caps  # pylint: disable=wrong-import-position
from nixalloc.seam import (  # pylint: disable=wrong-import-position
    BindingConstraint,
    CorrelationBucket,
    FinancialPicture,
    MirrorSnapshot,
    MirrorState,
    PositionRow,
    PositionState,
    ProposalOutcome,
    Side,
    StopMode,
)
from nixalloc.sizing import (  # pylint: disable=wrong-import-position
    InstrumentSpec,
    SizingKnobs,
)
from nixalloc.wiring import (  # pylint: disable=wrong-import-position
    AllocatorPathway,
    BucketCapAdapter,
    PublishedExposures,
    port_check,
)

ES = InstrumentSpec(symbol="ES", micro_symbol="MES", tick_value=12.5, micro_ratio=10)
NQ = InstrumentSpec(symbol="NQ", micro_symbol="MNQ", tick_value=5.0, micro_ratio=10)


# pylint: disable=too-few-public-methods,missing-function-docstring
# The doubles stand in for ports the frozen seam already names and documents.
class _Mirror:
    """A `MirrorPort` holding one snapshot. Read-only, no publish verb."""

    def __init__(self, snapshot: MirrorSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> MirrorSnapshot:
        return self._snapshot

    def version(self) -> int:
        picture = self._snapshot.picture
        return -1 if picture is None else picture.version


class _Tradability:
    """The §16 U1 fast-drop cache."""

    def __init__(self, tradable: bool = True, why: str = "open") -> None:
        self._tradable = tradable
        self._why = why

    def tradable(self, symbol: str) -> tuple[bool, str]:
        del symbol
        return self._tradable, self._why


def _row(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    trade_id: str,
    symbol: str,
    size: int,
    *,
    state: PositionState = PositionState.OPEN,
    margin: float = 500.0,
    stop_distance: int = 20,
) -> PositionRow:
    """One published row. ARC 032: `stop_distance` is a PUBLISHED field now.

    It is a keyword with a usable default because most cases here are about
    something else; the cases that are about the cap pass it explicitly, and
    `stop_distance=0` is how this suite drives the pre-widening blindness on
    the wire rather than by withholding a side table that no longer exists.
    """
    return PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id="strat-1",
        size=size,
        margin=margin,
        state=state,
        stop_distance=stop_distance,
    )


def _picture(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    balance: float = 100_000.0,
    committed: float = 10_000.0,
    positions: tuple[PositionRow, ...] = (),
    version: int = 41,
    sum_open: float | None = None,
    sum_res: float = 0.0,
    margins: dict[str, float] | None = None,
) -> FinancialPicture:
    """One published snapshot. `committed` is a FIELD, never a derivation."""
    return FinancialPicture(
        version=version,
        published_ts=1_700_000_000.0,
        balance=balance,
        positions=positions,
        margin_per_contract=MappingProxyType(
            dict(margins if margins is not None else {"ES": 500.0, "MES": 50.0})
        ),
        sum_open_margin=committed if sum_open is None else sum_open,
        sum_reservations=sum_res,
        committed=committed,
        deployable=balance * 0.70 - committed,
    )


def _fresh(picture: FinancialPicture) -> MirrorSnapshot:
    return MirrorSnapshot(
        state=MirrorState.FRESH, picture=picture, reason="complete and stamped"
    )


def _knobs(**overrides: Any) -> SizingKnobs:
    base: dict[str, Any] = {
        "per_trade_risk_usd": 1_000.0,
        "deployable_pct": 0.70,
        "symbol_cap": {"ES": 50, "NQ": 50},
        "slippage_pad_ticks": {"ES": 2, "NQ": 2},
        "micro_full_threshold": 2,
        "quant_tolerance": 0.25,
    }
    base.update(overrides)
    return SizingKnobs(**base)


def _cap_config(ceiling_pct: float = 0.02) -> caps.CapConfig:
    """§7's cap knobs, supplied directly so the cap's ceiling is drivable."""
    return caps.CapConfig(
        bucket_cap_pct=MappingProxyType(
            {
                "equities": ceiling_pct,
                "energy": ceiling_pct,
                "metals": ceiling_pct,
                "rates": ceiling_pct,
            }
        ),
        slippage_pad_ticks=MappingProxyType(
            {"ES": 2.0, "NQ": 2.0, "CL": 2.0, "GC": 2.0, "ZN": 2.0}
        ),
        tick_value_usd=MappingProxyType(
            {"ES": 12.5, "NQ": 5.0, "CL": 10.0, "GC": 10.0, "ZN": 15.625}
        ),
        micro_weight=0.1,
    )


def _pathway(
    snapshot: MirrorSnapshot,
    *,
    tradable: bool = True,
    why: str = "open",
    knobs: SizingKnobs | None = None,
    cap: BucketCapAdapter | None = None,
) -> AllocatorPathway:
    return AllocatorPathway(
        mirror=_Mirror(snapshot),
        tradability=_Tradability(tradable, why),
        instruments={"ES": ES, "NQ": NQ},
        knobs=knobs or _knobs(),
        bucket_cap=cap,
    )


# ==========================================================================
# 2.1 — A GO BECOMES A PROPOSAL, END TO END. Six paths, one snapshot.
# ==========================================================================


def test_21_a_CLEAN_size_carries_its_rationale_and_its_snapshot_version() -> None:
    """The base path. §16 U5: the rationale rides the proposal."""
    picture = _picture()
    report = _pathway(_fresh(picture)).propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    proposal = report.proposal
    assert proposal.outcome is ProposalOutcome.SIZED, proposal
    assert proposal.contracts > 0, proposal
    assert proposal.order is not None
    assert proposal.order.qty == proposal.contracts
    assert proposal.rationale.snapshot_version == picture.version, (
        "§16 U5 requires the INPUT SNAPSHOT to ride the proposal — a rationale "
        "that cannot name the version it sized against is not auditable"
    )
    assert isinstance(proposal.rationale.binding, BindingConstraint), (
        f"the rationale's binding constraint is not one: {proposal.rationale}"
    )


def test_21_a_HEADROOM_capped_size_downs_and_names_headroom_as_binding() -> None:
    """§16 U2: headroom = 0.70 × balance − committed, off the PUBLISHED figure."""
    roomy = _picture(balance=100_000.0, committed=0.0)
    tight = _picture(balance=100_000.0, committed=69_500.0)
    big = _pathway(_fresh(roomy)).propose(
        "strat-1", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
    )
    small = _pathway(_fresh(tight)).propose(
        "strat-1", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
    )
    assert small.proposal.contracts < big.proposal.contracts, (
        f"committed 0 -> {big.proposal.contracts}, committed 69,500 -> "
        f"{small.proposal.contracts}: headroom did not bind"
    )
    assert small.proposal.rationale.binding is BindingConstraint.MARGIN, (
        f"expected the margin term (which headroom feeds) to bind: "
        f"{small.proposal.rationale}"
    )
    assert small.proposal.rationale.headroom < big.proposal.rationale.headroom


def test_21_a_BUCKET_capped_size_down_is_measured_against_the_SUM_of_two() -> None:
    """§7's cap, through the Stage-2 adapter, over TWO same-bucket positions.

    One position per bucket never exercises the summation — sub-agent C's own
    §0a finding, re-driven here through the composed pathway rather than
    through `caps.admit` alone, because the thing under test at THIS level is
    the adapter that turns a published table into exposures.
    """
    held = (_row("T-ES", "ES", 2), _row("T-NQ", "NQ", 3))
    picture = _picture(
        positions=held, margins={"ES": 500.0, "MES": 50.0, "NQ": 400.0, "MNQ": 40.0}
    )
    stops = PublishedExposures()
    # 1.5% of 100,000 = $1,500. The two held positions price at $550 (ES) and
    # $330 (NQ) = $880, leaving $620 of room against a $27.50 micro contract.
    # A cap measured against the SUM admits 22; against max($550) it would
    # admit 34; against the proposal alone it would not bind at all. The three
    # answers differ, which is what makes this case a measurement.
    adapter = BucketCapAdapter(config=_cap_config(0.015), source=stops)

    uncapped = _pathway(_fresh(picture)).propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    capped = _pathway(_fresh(picture), cap=adapter).propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert capped.proposal.contracts < uncapped.proposal.contracts, (
        f"the §7 cap did not bind: uncapped {uncapped.proposal.contracts}, "
        f"capped {capped.proposal.contracts}"
    )
    assert capped.proposal.rationale.binding is BindingConstraint.BUCKET_CAP
    assert capped.proposal.rationale.bucket is CorrelationBucket.EQUITIES
    assert capped.proposal.rationale.bucket_used > 0.0, capped.proposal.rationale
    assert not capped.cap_incomplete, capped.cap_blind

    # THE SUMMATION, at this level: drop ONE of the two held positions and the
    # same proposal must be admitted LARGER. A cap measured against max() or
    # against the proposal alone cannot move here.
    one_held = _picture(
        positions=(held[0],),
        margins={"ES": 500.0, "MES": 50.0, "NQ": 400.0, "MNQ": 40.0},
    )
    lighter = _pathway(
        _fresh(one_held),
        cap=BucketCapAdapter(config=_cap_config(0.015), source=stops),
    ).propose("strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0)
    assert lighter.proposal.contracts > capped.proposal.contracts, (
        "removing one of two same-bucket positions did not loosen the cap, so "
        "the adapter is not summing the bucket"
    )


def test_21_a_DEAD_signal_is_dropped_and_never_sized() -> None:
    """§16 U1: never size a dead signal. The drop carries no size at all."""
    report = _pathway(_fresh(_picture()), tradable=False, why="blackout").propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert report.proposal.outcome is ProposalOutcome.NOT_TRADABLE, report.proposal
    assert report.proposal.contracts == 0
    assert report.proposal.order is None
    assert "blackout" in report.proposal.reason, report.proposal.reason


def test_21_a_ZERO_STOP_is_a_deny_shaped_NO_SIZE_never_a_manufactured_size() -> None:
    """§7:483 — the Limiter denies; the Allocator does not invent a size."""
    report = _pathway(_fresh(_picture())).propose(
        "strat-1", "ES", Side.LONG, 0, StopMode.FIXED, 1.0
    )
    assert report.proposal.outcome is ProposalOutcome.NO_SIZE_DENY, report.proposal
    assert report.proposal.contracts == 0
    assert report.proposal.order is None


def test_21_a_STALE_mirror_REFUSES_to_size_rather_than_sizing_on_a_partial() -> None:
    """§0i / §12.7: a half-built mirror is stale and the pass fast-drops."""
    for state, reason in (
        (MirrorState.EMPTY, "no snapshot has been received"),
        (MirrorState.PARTIAL, "the position table has not arrived"),
        (MirrorState.STALE, "freshness stamp past threshold"),
    ):
        snapshot = MirrorSnapshot(state=state, picture=None, reason=reason)
        report = _pathway(snapshot).propose(
            "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        )
        assert report.proposal.outcome is ProposalOutcome.STALE_MIRROR, (state, report)
        assert report.proposal.contracts == 0
        assert state.value in report.proposal.reason, report.proposal.reason
        assert report.proposal.rationale.snapshot_version < 0, (
            "a refusal must not claim a snapshot version it never read: "
            f"{report.proposal.rationale}"
        )


def test_21_all_six_paths_run_against_ONE_simulated_snapshot() -> None:
    """The composition itself: six outcomes, one picture, no cross-talk."""
    picture = _picture(positions=(_row("T-ES", "ES", 2),))
    stops = PublishedExposures()
    outcomes = {
        "clean": _pathway(_fresh(picture)).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        ),
        "headroom": _pathway(_fresh(_picture(committed=69_900.0))).propose(
            "s", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
        ),
        "bucket": _pathway(
            _fresh(picture),
            cap=BucketCapAdapter(config=_cap_config(0.001), source=stops),
        ).propose("s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0),
        "dead": _pathway(_fresh(picture), tradable=False).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        ),
        "zero_stop": _pathway(_fresh(picture)).propose(
            "s", "ES", Side.LONG, 0, StopMode.FIXED, 1.0
        ),
        "stale": _pathway(MirrorSnapshot()).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        ),
    }
    kinds = {name: r.proposal.outcome for name, r in outcomes.items()}
    assert kinds["clean"] is ProposalOutcome.SIZED, kinds
    assert kinds["dead"] is ProposalOutcome.NOT_TRADABLE, kinds
    assert kinds["zero_stop"] is ProposalOutcome.NO_SIZE_DENY, kinds
    assert kinds["stale"] is ProposalOutcome.STALE_MIRROR, kinds
    assert (
        outcomes["headroom"].proposal.contracts < outcomes["clean"].proposal.contracts
    )
    assert outcomes["bucket"].proposal.contracts < outcomes["clean"].proposal.contracts
    # THREE distinct non-sizing outcomes. A pathway that collapsed them into one
    # "denied" would be unactionable and would hide the stale-mirror class.
    assert len({kinds["dead"], kinds["zero_stop"], kinds["stale"]}) == 3, kinds


# ==========================================================================
# D3.136 — CLOSED IN ARC 032, and the closure is a BEFORE/AFTER measurement
#
# 2.1's instruction, quoted so these tests can be read against it: "prove the
# fail-open is CLOSED in the direction ARC 031 measured — two held same-bucket
# positions with real stop distances, a third proposal capped against their
# true summed dollar-risk, and prove the SAME scenario admitted the third
# BEFORE the widening. The before/after is the measurement; after alone proves
# nothing."
#
# So the BEFORE half is not simulated. `test_the_SAME_scenario_ADMITTED_the_
# third_before_the_widening` checks the pre-widening `wiring.py`, `caps.py`,
# `sizing.py` and both seams out of git and runs them, unmodified, on the same
# numbers. A before/after where the "before" is a hand-written approximation of
# code that no longer exists is a comparison against the author's memory.
# ==========================================================================


def _third_proposal_scenario() -> tuple[tuple[PositionRow, ...], dict[str, float]]:
    """TWO held same-bucket positions with real stop distances, and the knobs.

    Returned from one place so the BEFORE and AFTER halves are provably the
    same scenario: if the two halves each built their own picture, the
    comparison would measure the two fixtures rather than the two code paths.
    """
    held = (
        _row("T-ES", "ES", 2, stop_distance=20),
        _row("T-NQ", "NQ", 3, stop_distance=20),
    )
    margins = {"ES": 500.0, "MES": 50.0, "NQ": 400.0, "MNQ": 40.0}
    return held, margins


def test_the_cap_now_runs_on_the_COMPLETE_bucket() -> None:
    """AFTER: every term real, and `bucket_used` is the true SUM.

    §7: `Σ dollar_risk(open + pending in B) + proposed ≤ bucket_cap_pct(B) ×
    balance`. The two held positions price at (20 + 2) × 12.5 × 2 = $550 (ES)
    and (20 + 2) × 5.0 × 3 = $330 (NQ) — a SUM of $880, which is neither of
    them and is not the larger of them, so the figure asserted below cannot be
    produced by a max-shaped or single-position implementation.
    """
    held, margins = _third_proposal_scenario()
    picture = _picture(positions=held, margins=margins)
    adapter = BucketCapAdapter(config=_cap_config(0.015), source=PublishedExposures())
    report = _pathway(_fresh(picture), cap=adapter).propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert report.cap_complete, (
        f"blind={report.cap_blind} unbucketed={report.cap_unbucketed}"
    )
    used = report.proposal.rationale.bucket_used
    assert used == pytest.approx(880.0), (
        "the bucket must price at the SUM of both held positions. "
        f"$550 would be ES alone, $330 NQ alone, $880 the sum: got {used!r}"
    )
    assert report.proposal.rationale.binding is BindingConstraint.BUCKET_CAP
    assert report.proposal.rationale.bucket is CorrelationBucket.EQUITIES


def test_the_SAME_scenario_ADMITTED_the_third_before_the_widening() -> None:
    """THE BEFORE/AFTER. The pre-widening code is CHECKED OUT AND RUN.

    Not approximated, not described: `git show <base>:scripts/nixalloc/*.py`
    and both seams, loaded by exact path into a throwaway package namespace,
    driven on the numbers `_third_proposal_scenario` supplies to the AFTER half
    one test above.

    The BEFORE half's `PublishedExposures` takes its stop distances from an
    out-of-band map, and on a real snapshot that map is EMPTY — which is
    exactly what production had. So both held positions price at zero, the
    bucket sums to zero, and the third proposal is admitted against an empty
    ceiling.
    """
    before = _pre_widening_modules()
    if before is None:
        pytest.skip("no pre-widening revision reachable from this branch")
        return
    old_seam, old_wiring, old_sizing, old_caps = before

    old_rows = tuple(
        old_seam.PositionRow(
            trade_id=row.trade_id,
            symbol=row.symbol,
            strategy_id=row.strategy_id,
            size=row.size,
            margin=row.margin,
            state=old_seam.PositionState.OPEN,
        )
        for row in _third_proposal_scenario()[0]
    )
    _, margins = _third_proposal_scenario()
    old_picture = old_seam.FinancialPicture(
        version=41,
        published_ts=1_700_000_000.0,
        balance=100_000.0,
        positions=old_rows,
        margin_per_contract=MappingProxyType(margins),
        sum_open_margin=10_000.0,
        sum_reservations=0.0,
        committed=10_000.0,
        deployable=100_000.0 * 0.70 - 10_000.0,
    )
    old_cap = old_wiring.BucketCapAdapter(
        config=old_caps.CapConfig(
            bucket_cap_pct={
                "equities": 0.015,
                "energy": 0.015,
                "metals": 0.015,
                "rates": 0.015,
            },
            slippage_pad_ticks={"ES": 2.0, "MES": 2.0, "NQ": 2.0, "MNQ": 2.0},
            tick_value_usd={"ES": 12.5, "MES": 1.25, "NQ": 5.0, "MNQ": 0.5},
            micro_weight=0.1,
        ),
        # The HONEST production value: nothing published a stop distance, so
        # nothing could be handed one.
        source=old_wiring.PublishedExposures(),
    )
    old_pathway = old_wiring.AllocatorPathway(
        mirror=_OldMirror(
            old_seam.MirrorSnapshot(
                state=old_seam.MirrorState.FRESH,
                picture=old_picture,
                reason="complete and stamped",
            )
        ),
        tradability=_AlwaysTradable(),
        instruments={
            "ES": old_sizing.InstrumentSpec(
                symbol="ES", micro_symbol="MES", tick_value=12.5, micro_ratio=10
            ),
            "NQ": old_sizing.InstrumentSpec(
                symbol="NQ", micro_symbol="MNQ", tick_value=5.0, micro_ratio=10
            ),
        },
        knobs=_old_knobs(old_sizing),
        bucket_cap=old_cap,
    )
    was = old_pathway.propose(
        "strat-1", "ES", old_seam.Side.LONG, 20, old_seam.StopMode.FIXED, 1.0
    )

    held, margins = _third_proposal_scenario()
    now = _pathway(
        _fresh(_picture(positions=held, margins=margins)),
        cap=BucketCapAdapter(config=_cap_config(0.015), source=PublishedExposures()),
    ).propose("strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0)

    # THE MEASUREMENT. Same balance, same two held positions, same stop
    # distances, same ceiling, same proposal — different code.
    assert was.proposal.contracts > now.proposal.contracts, (
        "the widening was supposed to CLOSE a fail-open. The pre-widening "
        f"pathway admitted {was.proposal.contracts} contracts and the widened "
        f"one admitted {now.proposal.contracts}. If the widened one admits the "
        "same or more, the cap did not close and this arc's premise is wrong"
    )
    assert was.proposal.rationale.bucket_used == 0.0, (
        "the BEFORE half was supposed to price the held bucket at ZERO — that "
        "is what made it fail open. It reported "
        f"{was.proposal.rationale.bucket_used!r}, so this control is measuring "
        "something other than what it names"
    )
    assert was.cap_incomplete, (
        "the pre-widening pathway reported a CLEAN cap over an unpriceable "
        "bucket — then D3.136 was worse than recorded, not better"
    )
    assert now.proposal.rationale.bucket_used == pytest.approx(880.0)


def test_a_position_published_with_NO_stop_distance_is_the_ADMITTING_direction() -> (
    None
):
    """The fail-open direction, still driven — on the WIRE, not on a side table.

    D3.136 is closed, but the condition that made it dangerous is a publisher
    emitting a row with no usable distance. That can still happen, so it is
    still measured: `stop_distance=0` on the wire must report INCOMPLETE and
    must admit MORE than the same row priced honestly.
    """
    honest = _picture(positions=(_row("T-ES", "ES", 8, stop_distance=20),))
    silent = _picture(positions=(_row("T-ES", "ES", 8, stop_distance=0),))
    with_price = _pathway(
        _fresh(honest),
        cap=BucketCapAdapter(config=_cap_config(0.02), source=PublishedExposures()),
    ).propose("s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0)
    without = _pathway(
        _fresh(silent),
        cap=BucketCapAdapter(config=_cap_config(0.02), source=PublishedExposures()),
    ).propose("s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0)

    assert without.proposal.contracts > with_price.proposal.contracts, (
        "a held position published with NO stop distance must admit MORE than "
        "one priced honestly — if it admits the same or less the gap is "
        f"conservative: {without.proposal.contracts} vs "
        f"{with_price.proposal.contracts}"
    )
    assert without.cap_incomplete and not with_price.cap_incomplete
    assert set(without.cap_blind) == {"T-ES"}, without.cap_blind
    assert "could NOT be priced" in without.proposal.rationale.note


def test_a_row_in_NO_bucket_is_REPORTED_not_dropped_from_the_sum() -> None:
    """THE SECOND DOOR, found while closing the first.

    §7:498's map is keyed on LOGICAL symbols (`ES`, `NQ`, ...). Nothing pins
    the vocabulary of the published row's `symbol` field, and this tree already
    publishes contract spellings (`ESZ6`, `MESU6`) in its own fixtures. The
    pre-ARC-032 filter was one comprehension — `BUCKET_OF.get(row.symbol) is
    bucket` — so a contract-spelled row matched nothing and left the bucket
    silently, priced at zero by OMISSION. Same admitting direction, different
    door, and reading the stop distance off the row does nothing about it.
    """
    held, margins = _third_proposal_scenario()
    picture = _picture(
        positions=(*held, _row("T-CM", "ESZ6", 4, stop_distance=20)), margins=margins
    )
    adapter = BucketCapAdapter(config=_cap_config(0.015), source=PublishedExposures())
    report = _pathway(_fresh(picture), cap=adapter).propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert "T-CM:ESZ6" in report.cap_unbucketed, report.cap_unbucketed
    assert not report.cap_complete, (
        "a table holding an unbucketable counted row reported a COMPLETE cap"
    )
    assert "in NO bucket" in report.proposal.rationale.note, (
        f"§16 U5's rationale must carry it: {report.proposal.rationale.note}"
    )
    # And the row really was absent from the SUM — proven by the figure, not by
    # the counter, because a counter can be incremented by code that also
    # counted the row.
    assert report.proposal.rationale.bucket_used == pytest.approx(880.0), (
        "the unbucketed row must not have entered the equities SUM: "
        f"{report.proposal.rationale.bucket_used!r}"
    )


class _OldMirror:  # pylint: disable=too-few-public-methods
    """A mirror port for the pre-widening seam. One verb, because it has one."""

    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Any:
        return self._snapshot

    def version(self) -> int:
        picture = self._snapshot.picture
        return -1 if picture is None else picture.version


class _AlwaysTradable:  # pylint: disable=too-few-public-methods
    def tradable(self, symbol: str) -> tuple[bool, str]:
        del symbol
        return True, "tradable"


def _old_knobs(old_sizing: Any) -> Any:
    """The pre-widening `SizingKnobs`, built from THE LIVE ONE'S OWN FIELDS.

    Derived rather than retyped (directive 3). `SizingKnobs` did not change in
    ARC 032, so copying the live values across guarantees the two halves of the
    before/after are sized against identical knobs — a hand-written second copy
    is a place the comparison could silently become a comparison of knobs.
    """
    return old_sizing.SizingKnobs(**dataclasses.asdict(_knobs()))


#: The modules the BEFORE half needs, in dependency order. One tuple, read by
#: both the checkout step and the load step, so the two cannot drift apart.
_PRE032_MODULES = (
    ("nixrisk", "scripts/nixrisk/__init__.py"),
    ("nixrisk.seam", "scripts/nixrisk/seam.py"),
    ("nixalloc", "scripts/nixalloc/__init__.py"),
    ("nixalloc.seam", "scripts/nixalloc/seam.py"),
    ("nixalloc.caps", "scripts/nixalloc/caps.py"),
    ("nixalloc.sizing", "scripts/nixalloc/sizing.py"),
    ("nixalloc.wiring", "scripts/nixalloc/wiring.py"),
)


def _git(*args: str) -> str | None:
    """`git` under the D3.22 scrub. `None` on any non-zero exit.

    `pre-commit` exports `GIT_INDEX_FILE` / `GIT_DIR` into every hook it runs,
    so a bare `subprocess.run(["git", ...])` here would answer about whatever
    started the hook rather than about this repository.
    """
    from nixverify.gitenv import scrubbed_env  # pylint: disable=import-outside-toplevel

    done = subprocess.run(  # nosec B603 B607 - fixed argv, repo-local paths
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_env(),
    )
    return done.stdout if done.returncode == 0 else None


def _pre_widening_revision() -> str | None:
    """The commit BEFORE `POSITION_ROW_FIELDS` landed, or `None`.

    Found by walking history for the commit that introduced the pin and taking
    its parent — never a hard-coded sha, which is the moving anchor doctrine
    C.4 forbids.
    """
    log = _git(
        "log",
        "--format=%H",
        "-S",
        "POSITION_ROW_FIELDS",
        "--",
        "scripts/nixalloc/seam.py",
    )
    if not log:
        return None
    parent = _git("rev-parse", f"{log.split()[-1]}^")
    return parent.strip() if parent else None


def _checkout_pre032(base: str) -> Path | None:
    """Write the pre-widening sources into a throwaway tree. `None` if any miss."""
    root = Path(tempfile.mkdtemp(prefix="nix-pre032-"))
    _PRE032_TREES.append(root)
    for _, rel in _PRE032_MODULES:
        source = _git("show", f"{base}:{rel}")
        if source is None:
            return None
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return root


def _restore_modules(saved: dict[str, Any]) -> None:
    """Put `sys.modules` and the parent-package attributes back, in that order.

    Both halves, because a package attribute set during the load outlives the
    `sys.modules` entry: leaving `nixalloc.seam` bound to the pre-widening
    module on the live `nixalloc` package would poison every test that ran
    after this one, in a way the poisoned test would report as its own bug.
    """
    for name, previous in saved.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    for name, previous in saved.items():
        if previous is None or "." not in name:
            continue
        parent, _, leaf = name.rpartition(".")
        if saved.get(parent) is not None:
            setattr(saved[parent], leaf, previous)


def _install_pre032(name: str, path: Path) -> Any:
    """Load ONE pre-widening module under its real dotted name. `None` on failure.

    Under its REAL name and not a `_pre032.` alias, because
    `nixalloc.seam` executes `from nixrisk.seam import PositionRow` and that
    statement resolves through `sys.modules` by the name the source spells.
    Aliasing would make the import find the LIVE widened seam.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if "." in name:
        parent, _, leaf = name.rpartition(".")
        setattr(sys.modules[parent], leaf, module)
    spec.loader.exec_module(module)
    return module


def _load_pre032(root: Path) -> dict[str, Any] | None:
    """Load the checked-out tree by EXACT PATH, then put `sys.modules` back.

    EVERY pre-widening module stays installed for the WHOLE load and is
    restored only at the end. Restoring after each one — the first draft — meant
    `nixalloc.seam`'s own `from nixrisk.seam import PositionRow` resolved
    against the LIVE widened module, so the "before" half was silently the
    "after" half. The non-vacuity assertion in the caller caught it.
    """
    loaded: dict[str, Any] = {}
    saved = {name: sys.modules.get(name) for name, _ in _PRE032_MODULES}
    try:
        for name, rel in _PRE032_MODULES:
            module = _install_pre032(name, root / rel)
            if module is None:
                return None
            loaded[name] = module
    finally:
        _restore_modules(saved)
    return loaded


def _pre_widening_modules() -> tuple[Any, Any, Any, Any] | None:
    """`(alloc seam, wiring, sizing, caps)` as they were BEFORE the widening.

    Split into three helpers — find the revision, check it out, load it — for
    the ordinary reason, and one that matters here: the load step's
    `sys.modules` bookkeeping is the part that can silently turn this control
    into a comparison of the widened code against itself, and it is easier to
    read when it is not wrapped in filesystem work.
    """
    base = _pre_widening_revision()
    if base is None:
        return None
    root = _checkout_pre032(base)
    if root is None:
        return None
    loaded = _load_pre032(root)
    if loaded is None:
        return None
    # NON-VACUITY: the loaded seam must be the NARROW one, or this whole
    # control is comparing the widened code against itself.
    assert "stop_distance" not in {
        f.name for f in dataclasses.fields(loaded["nixalloc.seam"].PositionRow)
    }, "the 'pre-widening' PositionRow already carries stop_distance"
    return (
        loaded["nixalloc.seam"],
        loaded["nixalloc.wiring"],
        loaded["nixalloc.sizing"],
        loaded["nixalloc.caps"],
    )


# ==========================================================================
# 2.2 — PARTIAL-FILL REFLECTION (§4). The mirror reflects; it does not act.
# ==========================================================================


def test_22_over_reserved_capital_returns_to_deployable_THE_INSTANT_it_is_republished() -> (
    None
):
    """§4: on fill confirmation the Limiter republishes with the TRUE filled
    size and the unfilled reservation released. The Allocator's mirror shows
    the capital back in `deployable` on the next snapshot — not on a delay,
    and not because the Allocator computed anything.

    Driven as TWO published versions of one trade, because a single snapshot
    cannot show a change. The Allocator's only role is that its next pass
    sizes larger; it never releases anything itself.
    """
    reserved = _picture(
        version=41,
        committed=10_000.0,
        sum_res=10_000.0,
        sum_open=0.0,
        positions=(
            _row("T-1", "ES", 20, state=PositionState.RESERVED, margin=10_000.0),
        ),
    )
    # Reality came in UNDER the reservation: 5 of 20 filled, 15 released.
    filled = _picture(
        version=42,
        committed=2_500.0,
        sum_res=0.0,
        sum_open=2_500.0,
        positions=(_row("T-1", "ES", 5, state=PositionState.OPEN, margin=2_500.0),),
    )
    assert filled.deployable > reserved.deployable, (
        "the fixture does not model a release at all: deployable "
        f"{reserved.deployable} -> {filled.deployable}"
    )

    before = _pathway(_fresh(reserved)).propose(
        "strat-2", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
    )
    after = _pathway(_fresh(filled)).propose(
        "strat-2", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
    )
    assert after.proposal.rationale.headroom > before.proposal.rationale.headroom, (
        "the released reservation did not reach the Allocator's headroom: "
        f"{before.proposal.rationale.headroom} -> "
        f"{after.proposal.rationale.headroom}"
    )
    assert after.proposal.rationale.snapshot_version == 42
    assert before.proposal.rationale.snapshot_version == 41, (
        "each pass must name the version it sized against, or the reflection "
        "cannot be attributed to a republish"
    )
    # THE AUTHORITY HALF: the Allocator reflected and did not act. The position
    # row it read is unchanged, and nothing it emitted names a release.
    assert filled.positions[0].size == 5
    assert "releas" not in after.proposal.reason.lower()


def test_22_the_release_is_visible_WITHOUT_the_allocator_recomputing_committed() -> (
    None
):
    """The reflection is a READ of a published field, not a derivation.

    Plant a republished snapshot whose `committed` says the capital came back
    while its own rows still say otherwise. The Allocator must follow the
    PUBLISHED figure — that is §16 U2's one source of truth, and it is also
    what makes the reflection instant rather than dependent on row bookkeeping.
    """
    published_release = _picture(
        version=43,
        committed=0.0,
        sum_res=0.0,
        sum_open=0.0,
        positions=(_row("T-1", "ES", 20, state=PositionState.OPEN, margin=10_000.0),),
    )
    report = _pathway(_fresh(published_release)).propose(
        "strat-2", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
    )
    expected = 0.70 * published_release.balance - published_release.committed
    assert report.proposal.rationale.headroom == expected, (
        "headroom followed the position rows instead of the published "
        f"committed figure: {report.proposal.rationale.headroom} != {expected}"
    )


# ==========================================================================
# 2.3 — EVERY OUTPUT IS A PROPOSAL, NEVER AN ORDER (§2)
# ==========================================================================


def test_23_no_path_emits_anything_that_reaches_a_broker() -> None:
    """The authority invariant at the SEAM, across all of 2.1's paths."""
    picture = _picture(positions=(_row("T-ES", "ES", 2),))
    stops = PublishedExposures()
    reports = [
        _pathway(_fresh(picture)).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        ),
        _pathway(_fresh(_picture(committed=69_900.0))).propose(
            "s", "ES", Side.LONG, 2, StopMode.FIXED, 1.0
        ),
        _pathway(
            _fresh(picture),
            cap=BucketCapAdapter(config=_cap_config(0.001), source=stops),
        ).propose("s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0),
        _pathway(_fresh(picture), tradable=False).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        ),
        _pathway(_fresh(picture)).propose("s", "ES", Side.LONG, 0, StopMode.FIXED, 1.0),
        _pathway(MirrorSnapshot()).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        ),
    ]
    assert len(reports) == 6
    for report in reports:
        assert report.reaches_broker is False, report
        assert report.proposal.reaches_broker is False, report.proposal
        order = report.proposal.order
        # A ProposedOrder is the LIMITER's type and carries no venue field. The
        # attempt is the proof: there is no attribute a broker adapter reads.
        if order is not None:
            for venue_field in ("venue", "account", "route", "exchange", "session"):
                assert not hasattr(order, venue_field), (
                    f"ProposedOrder grew {venue_field!r} — the Allocator's output "
                    "would be routable without the Limiter's pass (§2)"
                )


def test_23_the_pathway_exposes_NO_verb_that_places_reserves_or_publishes() -> None:
    """Proven by ATTEMPT: the verb is absent from the composed object too."""
    pathway = _pathway(_fresh(_picture()))
    for verb in (
        "place",
        "submit",
        "send",
        "reserve",
        "release",
        "publish",
        "write",
        "commit",
        "flatten",
        "cancel",
    ):
        assert getattr(pathway, verb, None) is None, (
            f"AllocatorPathway exposes {verb!r} — §2 makes the Allocator "
            "permissive, and a verb it exposes is authority it has"
        )


def test_23_the_adapter_still_satisfies_the_port_it_was_built_for() -> None:
    """An `isinstance` the interpreter performs, not a claim this file makes."""
    adapter = BucketCapAdapter(config=_cap_config(), source=PublishedExposures())
    pathway = _pathway(_fresh(_picture()), cap=adapter)
    assert port_check(pathway) is adapter
    assert port_check(_pathway(_fresh(_picture()))) is None


def test_23_a_cap_that_RAISES_denies_rather_than_killing_the_pass() -> None:
    """§6.6's own rule generalised: a component outage must never halt flow.

    `caps.admit` fails closed and loud — correct for a formula, fatal for a hot
    path. The adapter converts each refusal into an admitted-zero verdict
    naming it, and the pass still returns a proposal.
    """
    picture = _picture(positions=(_row("T-ES", "ES", 2),))
    adapter = BucketCapAdapter(
        config=_cap_config(),
        source=PublishedExposures(),
    )

    class _Exploding:
        def exposures(self, picture: Any, bucket: Any) -> Any:
            del picture, bucket
            raise caps.BucketCapError("planted refusal")

    adapter_raising = BucketCapAdapter(config=_cap_config(), source=_Exploding())
    ok = _pathway(_fresh(picture), cap=adapter).propose(
        "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert ok.proposal.outcome is ProposalOutcome.SIZED
    try:
        boom = _pathway(_fresh(picture), cap=adapter_raising).propose(
            "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
        )
    except caps.BucketCapError:  # pragma: no cover - the failure this asserts
        raise AssertionError(
            "a raising exposure source killed the sizing pass — the Allocator "
            "must deny, never die, when a component refuses"
        ) from None
    assert boom.proposal.contracts == 0, boom.proposal
