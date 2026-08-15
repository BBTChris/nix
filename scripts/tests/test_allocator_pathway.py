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

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
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


def _row(
    trade_id: str,
    symbol: str,
    size: int,
    *,
    state: PositionState = PositionState.OPEN,
    margin: float = 500.0,
) -> PositionRow:
    return PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id="strat-1",
        size=size,
        margin=margin,
        state=state,
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
    stops = PublishedExposures(stop_ticks_by_trade={"T-ES": 20, "T-NQ": 20})
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
    stops = PublishedExposures(stop_ticks_by_trade={"T-ES": 20})
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
# D3.136 — the gap the composition found, driven in both directions
# ==========================================================================


def test_the_cap_over_an_UNPRICEABLE_bucket_reports_INCOMPLETE_not_a_ceiling() -> None:
    """The published row carries no stop distance, so the bucket is unpriceable.

    This is the honest production state today: `PublishedExposures` with an
    empty stop table prices NOTHING, and a cap computed over an empty bucket
    would admit the full proposal while a real bucket might be full. The
    pathway must SAY so rather than return a clean ceiling.
    """
    picture = _picture(positions=(_row("T-ES", "ES", 2), _row("T-NQ", "NQ", 3)))
    adapter = BucketCapAdapter(config=_cap_config(0.02), source=PublishedExposures())
    report = _pathway(_fresh(picture), cap=adapter).propose(
        "strat-1", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert report.cap_incomplete, (
        "two held equities positions could not be priced and the pathway "
        "reported a clean cap — that is the false-green D3.136 names"
    )
    assert set(report.cap_blind) == {"T-ES", "T-NQ"}, report.cap_blind
    assert "could NOT be priced" in report.proposal.rationale.note, (
        f"§16 U5's rationale must carry the blindness: {report.proposal.rationale.note}"
    )


def test_a_position_priced_at_ZERO_would_be_the_admitting_direction() -> None:
    """Why unpriced rows are REPORTED and not silently valued at zero.

    A row valued at zero risk makes the bucket look emptier than it is, and an
    emptier bucket ADMITS more. Driven as a comparison so the direction is a
    measurement rather than a claim.
    """
    picture = _picture(positions=(_row("T-ES", "ES", 8),))
    priced = BucketCapAdapter(
        config=_cap_config(0.02),
        source=PublishedExposures(stop_ticks_by_trade={"T-ES": 40}),
    )
    blind = BucketCapAdapter(config=_cap_config(0.02), source=PublishedExposures())
    with_price = _pathway(_fresh(picture), cap=priced).propose(
        "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    without = _pathway(_fresh(picture), cap=blind).propose(
        "s", "ES", Side.LONG, 20, StopMode.FIXED, 1.0
    )
    assert without.proposal.contracts >= with_price.proposal.contracts, (
        "pricing a held position at zero must never ADMIT LESS than pricing it "
        "honestly — if it did, the gap would be conservative and D3.136 would "
        "be a nuisance rather than a hazard"
    )
    assert without.cap_incomplete and not with_price.cap_incomplete


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
    stops = PublishedExposures(stop_ticks_by_trade={"T-ES": 20})
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
        source=PublishedExposures(stop_ticks_by_trade={"T-ES": 20}),
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
