"""ARC 037 / sub-agent E — the unit suite for the two module changes.

Two properties, both in `docs/nics_risk_subsystem_spec_v1.3.md`:

* **E1, §6.6:459** — *"The **Allocator reads** it to weight sizing."*
  `scripts/nixalloc/wiring.py` threads each contender's weight out of
  `ContentionRanking.weights` into the sizing pass, and every FCFS route carries
  exactly `NEUTRAL_WEIGHT`.
* **E2, §4:272-286** — a strategy mid-recovery reads in-flight-closing, and a
  QUARANTINED strategy stays withdrawn from contention after its rows go flat.
  `scripts/nixalloc/lifecycle.py` reflects both.

**WHAT IS DELIBERATELY NOT HERE.** The weight TRANSFORM and its APPLICATION
POINT are sub-agent B's (`nixalloc.contention.weight_for` and
`SizingAllocator.propose(..., weight=)`), built in a parallel worktree this
branch cannot see. Nothing below implements either; where a weight-aware sizing
pass is needed, `_WeightAware` records the keyword and delegates, so what is
under test is the THREAD and never the transform. The end-to-end drive against
B's real code is `checks/check_allocator_weighting.py`, which the integrator
re-drives at Stage 2.

Every assertion names the REASON, never a bare boolean: three different
snapshots produce the same `False` and only the reason tells them apart (§18).
"""
# pylint: disable=invalid-name,redefined-outer-name
# pylint: disable=too-few-public-methods,missing-function-docstring
# pylint: disable=use-implicit-booleaness-not-comparison
# `book.asked == []` is asserted rather than `not book.asked` because an empty
# list and a falsey non-list are different outcomes here: the first says the
# book was never consulted, and that distinction IS the assertion.
# Test names SHOUT the property under test on purpose, and the stand-ins below
# are one-verb doubles for ports the frozen seam already names.

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixalloc import (  # pylint: disable=wrong-import-position
    contention,
    lifecycle,
    wiring,
)
from nixalloc.seam import (  # pylint: disable=wrong-import-position
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
    SizingAllocator,
    SizingKnobs,
)

BALANCE = 10_000_000.0
MARGIN = 500.0
TICK = 5.0
STOP = 8
PAD = 2
RISK_USD = 400.0
NOW = 1_700_000_000.0


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _Tradability:
    def tradable(self, symbol: str) -> tuple[bool, str]:
        del symbol
        return True, "open"


class _Mirror:
    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Any:
        return self._snapshot() if callable(self._snapshot) else self._snapshot

    def version(self) -> int:
        picture = self.snapshot().picture
        return -1 if picture is None else picture.version


class _Book:
    """§4:273's quarantine book, as `QuarantineViewPort` sees it. READ-ONLY."""

    def __init__(self, *subjects: str) -> None:
        self.subjects = set(subjects)
        self.asked: list[str] = []

    def is_quarantined(self, subject: str) -> bool:
        self.asked.append(subject)
        return subject in self.subjects


class _RaisingBook:
    def is_quarantined(self, subject: str) -> bool:
        raise RuntimeError(f"quarantine book unreadable for {subject}")


class _WeightAware:
    """A sizing pass that RECORDS the weight and applies §7:478's scaling.

    Stands in for sub-agent B's half, in TEST CODE ONLY. It applies the weight
    by replacing `per_trade_risk_usd` for the duration of one pass — the frozen
    SEAM (b) application point — so the size it returns is the real
    `SizingAllocator`'s arithmetic over a scaled budget and not a number this
    file invented.
    """

    def __init__(self, inner: SizingAllocator) -> None:
        self._inner = inner
        self.seen: list[float] = []

    def propose(self, *, weight: float = 1.0, **kwargs: Any) -> Any:
        self.seen.append(weight)
        held = self._inner._knobs  # pylint: disable=protected-access
        self._inner._knobs = _replace_risk(  # pylint: disable=protected-access
            held, held.per_trade_risk_usd * weight
        )
        try:
            return self._inner.propose(**kwargs)
        finally:
            self._inner._knobs = held  # pylint: disable=protected-access


def _replace_risk(knobs: SizingKnobs, value: float) -> SizingKnobs:
    import dataclasses  # pylint: disable=import-outside-toplevel

    return dataclasses.replace(knobs, per_trade_risk_usd=value)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _picture(positions: tuple[PositionRow, ...] = (), version: int = 41) -> Any:
    return FinancialPicture(
        version=version,
        published_ts=NOW,
        balance=BALANCE,
        positions=positions,
        margin_per_contract={"ES": MARGIN, "MES": MARGIN / 10.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=BALANCE * 0.70,
    )


def _fresh(picture: Any) -> MirrorSnapshot:
    return MirrorSnapshot(
        state=MirrorState.FRESH, picture=picture, reason="complete and stamped"
    )


def _row(trade_id: str, strategy_id: str, state: PositionState) -> PositionRow:
    return PositionRow(
        trade_id=trade_id,
        symbol="ES",
        strategy_id=strategy_id,
        size=1,
        margin=MARGIN,
        state=state,
        stop_distance=STOP,
    )


@pytest.fixture
def knobs() -> SizingKnobs:
    return SizingKnobs(
        per_trade_risk_usd=RISK_USD,
        deployable_pct=0.70,
        symbol_cap={"ES": 500},
        slippage_pad_ticks={"ES": PAD},
        micro_full_threshold=2,
        quant_tolerance=0.25,
    )


def _pathway(knobs: SizingKnobs, **kw: Any) -> Any:
    mirror = kw.pop("mirror", None) or _Mirror(_fresh(_picture()))
    return wiring.AllocatorPathway(
        mirror=mirror,
        tradability=_Tradability(),
        instruments={
            "ES": InstrumentSpec(symbol="ES", micro_symbol="MES", tick_value=TICK)
        },
        knobs=knobs,
        bucket_cap=None,
        **kw,
    )


def _go(strategy_id: str, seq: int = 1, symbol: str = "ES") -> Any:
    return wiring.Go(
        strategy_id=strategy_id,
        symbol=symbol,
        side=Side.LONG,
        stop_ticks=STOP,
        stop_mode=StopMode.FIXED,
        signal_ts=NOW,
        arrival_seq=seq,
    )


# ===========================================================================
# E1 — the weight is threaded
# ===========================================================================


def test_the_weight_reaches_the_sizing_pass_from_the_LONE_GO_entry(knobs) -> None:
    """A race of one is still a race: `propose()` must deliver a weight."""
    pathway = _pathway(knobs)
    aware = _WeightAware(pathway._allocator)  # pylint: disable=protected-access
    pathway._allocator = aware  # pylint: disable=protected-access
    pathway._weight_kwarg = True  # pylint: disable=protected-access
    pathway.propose(
        strategy_id="s1",
        symbol="ES",
        side=Side.LONG,
        stop_ticks=STOP,
        stop_mode=StopMode.FIXED,
        signal_ts=NOW,
    )
    assert aware.seen == [contention.NEUTRAL_WEIGHT], (
        "the lone-GO entry did not deliver §6.6:459's weight into the sizing "
        f"pass; it delivered {aware.seen!r}"
    )


def test_a_DISTINCT_weight_produces_a_DISTINCT_contract_count(knobs) -> None:
    """§6.6:459's whole point: the ordering must move the SIZE, not only the order.

    The weights are supplied by this test — the transform is sub-agent B's — but
    the THREAD, the sizing arithmetic and the count are the shipped ones.
    """
    pathway = _pathway(knobs)
    aware = _WeightAware(pathway._allocator)  # pylint: disable=protected-access
    pathway._allocator = aware  # pylint: disable=protected-access
    pathway._weight_kwarg = True  # pylint: disable=protected-access

    sizes = []
    for weight in (1.125, 0.875, 1.0):
        aware.seen.clear()
        proposal = aware.propose(
            weight=weight,
            strategy_id="s1",
            symbol="ES",
            side=Side.LONG,
            stop_ticks=STOP,
            stop_mode=StopMode.FIXED,
            signal_ts=NOW,
        )
        sizes.append(proposal.contracts)
    assert sizes == [9, 7, 8], (
        "§7:478's risk term is floor(per_trade_risk / per_contract_risk) = "
        f"floor(400/50) = 8 unweighted; weighted 1.125/0.875 it must be 9/7 and "
        f"it was {sizes}"
    )


def test_every_FCFS_route_carries_EXACTLY_the_neutral_weight(knobs) -> None:
    """§6.6:465-466: the fallback is structurally neutral, so it re-sizes nothing."""
    pathway = _pathway(knobs)
    outcome = pathway.propose_contended((_go("s1", 1), _go("s2", 2)), now=NOW)
    weights = [report.score_weight for report in outcome.reports]
    assert weights == [contention.NEUTRAL_WEIGHT, contention.NEUTRAL_WEIGHT], (
        "a race with NO ranking mirror took §6.6:465's FCFS fallback and must "
        f"weight every contender {contention.NEUTRAL_WEIGHT}; it weighted {weights}"
    )
    assert outcome.ranking.is_fallback, outcome.ranking.reason
    assert "1 distinct sizing weight" in outcome.weighting, outcome.weighting


def test_a_missing_pair_row_defaults_to_the_neutral_weight() -> None:
    """`_weight_of` must never default a missing pair to anything but neutral."""
    ranking = contention.ContentionRanking(
        policy=contention.ContentionPolicy.FCFS,
        ordering=(),
        weights={},
        scored=0,
        contenders=0,
        reason="empty",
    )
    got = wiring._weight_of(ranking, ("nobody", "ES"))  # pylint: disable=protected-access
    assert got == contention.NEUTRAL_WEIGHT, (
        f"an absent weight defaulted to {got}; §6.6:455 makes an ABSENT score an "
        "FCFS case, and a default that re-sizes a position is a preference"
    )


def test_a_sizing_pass_that_cannot_take_a_weight_REPORTS_rather_than_raising(
    knobs,
) -> None:
    """The transition state must be visible and must never halt order flow."""
    pathway = _pathway(knobs)
    assert pathway._weight_kwarg is wiring._takes_weight(  # pylint: disable=protected-access
        pathway._allocator.propose  # pylint: disable=protected-access
    )
    outcome = pathway.propose_contended((_go("s1", 1),), now=NOW)
    report = outcome.reports[0]
    assert report.proposal.outcome is ProposalOutcome.SIZED, (
        "a sizing pass that cannot take a weight must still PROPOSE — §6.6:467 "
        f"forbids a scoring condition halting order flow; got {report.proposal.reason}"
    )
    if not wiring._takes_weight(SizingAllocator.propose):  # pylint: disable=protected-access
        assert "COMPUTED and NOT APPLIED" in report.weight_gap, (
            "the shortfall was not reported on the report at all: "
            f"{report.weight_gap!r}"
        )


def test_takes_weight_accepts_a_kwargs_sink_and_refuses_a_bare_pass() -> None:
    """The probe asks the SIGNATURE, so a wrapper counts and a bare pass does not."""

    def bare(strategy_id: str) -> None:
        del strategy_id

    def sink(**kwargs: Any) -> None:
        del kwargs

    def named(strategy_id: str, *, weight: float = 1.0) -> None:
        del strategy_id, weight

    assert wiring._takes_weight(bare) is False  # pylint: disable=protected-access
    assert wiring._takes_weight(sink) is True  # pylint: disable=protected-access
    assert wiring._takes_weight(named) is True  # pylint: disable=protected-access
    assert wiring._takes_weight(object()) is False  # pylint: disable=protected-access


# ===========================================================================
# E2 — the §4 lifecycle screen reflects quarantine as well as closing
# ===========================================================================


def test_a_QUARANTINED_strategy_is_refused_capital_even_when_it_is_FLAT() -> None:
    """§4:274 — quarantine is NOT auto-resurrected. THE DEFECT THIS CLOSES.

    A completed recovery leaves the strategy owning no published row, and until
    ARC 037 the screen answered "flat — it owns no published row", ELIGIBLE.
    """
    picture = _picture()
    book = _Book("s-dead")
    got = lifecycle.eligibility(picture, "s-dead", book)
    assert not got.eligible, (
        "a quarantined strategy holding no row read ELIGIBLE for new capital: "
        f"{got.reason}"
    )
    assert got.quarantined and got.quarantine_observed, got
    assert "QUARANTINED" in got.reason and "§4:272-274" in got.reason, got.reason
    assert book.asked == ["s-dead"], (
        f"the book was consulted {book.asked!r} — a screen that never asks and a "
        "clean book produce the same verdict"
    )


def test_the_quarantine_refusal_OUTRANKS_the_in_flight_closing_one() -> None:
    """Both true at once is the third recovery of a crash loop, and they differ.

    In-flight-closing clears on its own; quarantine does not clear until the
    operator acts. Reporting the transitional one would tell an operator to wait
    for something that will never happen.
    """
    picture = _picture(positions=(_row("T-1", "s-dead", PositionState.CLOSING),))
    got = lifecycle.eligibility(picture, "s-dead", _Book("s-dead"))
    assert not got.eligible and got.quarantined, got
    assert "operator-driven" in got.reason, got.reason
    assert got.observed_states == ("closing",), (
        f"the refusal lost the published states it saw: {got.observed_states!r}"
    )


def test_a_NON_quarantined_strategy_is_unaffected_by_the_book() -> None:
    """Non-vacuity: a screen that refuses everyone proves nothing."""
    got = lifecycle.eligibility(_picture(), "s-live", _Book("s-dead"))
    assert got.eligible, got.reason
    assert got.quarantined is False and got.quarantine_observed is True, got


def test_no_book_at_all_is_the_pre_ARC_037_answer_and_SAYS_SO() -> None:
    """`quarantine_observed` is what tells an unconsulted book from a clean one."""
    got = lifecycle.eligibility(_picture(), "s-dead")
    assert got.eligible, got.reason
    assert got.quarantine_observed is False, (
        "a call with NO quarantine view reported that a book was consulted — "
        "which is the §7.12/1 ambiguity this field exists to close"
    )


def test_an_UNREADABLE_quarantine_book_FAILS_CLOSED() -> None:
    """§4 is a safety screen; §6.6:467's never-halt rule governs SCORING."""
    got = lifecycle.eligibility(_picture(), "s-dead", _RaisingBook())
    assert not got.eligible, (
        "a quarantine book that could not be read ADMITTED capital: "
        f"{got.reason} — a book that cannot be read is not an empty book"
    )
    assert "RuntimeError" in got.reason and "unreadable" in got.reason, got.reason
    assert got.quarantined and got.quarantine_observed, got


def test_the_book_rides_the_VIEW_so_no_caller_can_forget_it_per_contender() -> None:
    """Two contenders in one pass must be screened against the same inputs."""
    view = lifecycle.PictureLifecycle(_picture(), _Book("s-dead"))
    assert not view.eligibility("s-dead").eligible
    assert view.eligibility("s-live").eligible


def test_MirrorLifecycle_PROPAGATES_the_book_through_pin() -> None:
    """`pin()` is the one hop the sizing pass takes; the book must survive it."""
    view = lifecycle.MirrorLifecycle(_Mirror(_fresh(_picture())), _Book("s-dead"))
    pinned = view.pin()
    assert pinned is not None
    assert pinned.quarantine is view.quarantine, (
        "pin() dropped the §4:273 book, so the screen the race actually runs "
        "would not carry it"
    )
    assert not pinned.eligibility("s-dead").eligible
    assert not view.eligibility("s-dead").eligible


def test_the_PATHWAY_denies_a_quarantined_strategy_through_the_real_pass(
    knobs,
) -> None:
    """An eligibility record is a reader; only a PROPOSAL is the wire."""
    book = _Book("s-dead")
    pathway = _pathway(knobs, quarantine=book)
    dead = pathway.propose_contended((_go("s-dead", 1),), now=NOW).reports[0]
    live = pathway.propose_contended((_go("s-live", 1),), now=NOW).reports[0]
    assert dead.proposal.outcome is ProposalOutcome.NO_SIZE_DENY, (
        f"the shipped pathway sized a QUARANTINED strategy: {dead.proposal.reason}"
    )
    assert "QUARANTINED" in dead.proposal.reason, dead.proposal.reason
    assert live.proposal.outcome is ProposalOutcome.SIZED, (
        f"the LIVE strategy was refused off the same snapshot: "
        f"{live.proposal.reason} — §4:273 keeps the rest of the system trading"
    )
    view = pathway._lifecycle  # pylint: disable=protected-access
    assert view.quarantine is book, (
        "the pathway did not fold the book into its default lifecycle view"
    )


def test_an_INJECTED_lifecycle_view_is_not_silently_re_wrapped(knobs) -> None:
    """One property, one authority: a caller's own view owns what it screens on."""
    book = _Book("s-dead")
    injected = lifecycle.PictureLifecycle(_picture())
    pathway = _pathway(knobs, lifecycle=injected, quarantine=book)
    assert pathway._lifecycle is injected  # pylint: disable=protected-access
    assert (
        getattr(pathway._lifecycle, "quarantine", None) is None  # pylint: disable=protected-access
    ), "the pathway re-wrapped an injected view, giving one property two authorities"
    assert pathway._quarantine is book, (  # pylint: disable=protected-access
        "the accepted-and-dropped state must remain READABLE, or a gate cannot "
        "tell it from a pathway that was never given a book"
    )
    assert book.asked == [], (
        f"the injected view somehow consulted the book: {book.asked!r}"
    )


def test_the_module_exposes_NO_recovery_driving_verb() -> None:
    """§2/§4:260-274 — this module REFLECTS recovery; the supervisor drives it."""
    banned = ("quarantine", "restore", "relaunch", "kill", "flatten", "archive")
    exposed = [
        name
        for name in dir(lifecycle)
        if not name.startswith("__")
        for stem in banned
        if name.lstrip("_").lower() == stem
        or name.lstrip("_").lower().startswith(f"{stem}_")
    ]
    assert exposed == [], (
        f"the Allocator's lifecycle module exposes {exposed!r} — a verb it "
        "exposes is authority it has, and §4 gives every one of these to the "
        "Limiter and the supervisor"
    )


def test_the_quarantine_port_has_exactly_ONE_verb_and_it_is_a_QUESTION() -> None:
    """Surface IS authority on this boundary (§2)."""
    verbs = [
        name for name in dir(lifecycle.QuarantineViewPort) if not name.startswith("_")
    ]
    assert verbs == ["is_quarantined"], (
        f"the read-only quarantine port exposes {verbs!r}; anything beyond the "
        "question would let the Allocator act on §4:273's book"
    )
