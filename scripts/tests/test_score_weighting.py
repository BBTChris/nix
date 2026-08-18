"""ARC 037 / B — §6.6:459's score → sizing weight, driven rather than described.

CHECK-DEBT **D3.260**: `NEUTRAL_WEIGHT` was `1.0` for every contender under both
policies from ARC 031 to ARC 036, so every assertion anybody could write about
`ContentionRanking.weights` passed while measuring nothing. **A weighting test in
which every weight is 1.0 is the defect, not the coverage**, and this file is
built against that shape rather than merely avoiding it.

The reference side is `downloads/ARC037-SEAM-FREEZE.md` SEAM (b) — an ARCHITECT
RULING, because §6.6:459 gives the Allocator the read *"to weight sizing"* and
the frozen risk spec fixes no transform:

    NEUTRAL_WEIGHT = 1.0 ; WEIGHT_STEP = 0.25
    WEIGHT_FLOOR   = 0.60 ; WEIGHT_CEILING = 1.40
    raw(rank, n)    = 1.0 + WEIGHT_STEP * ((n + 1) / 2 - rank)
    weight(rank, n) = min(WEIGHT_CEILING, max(WEIGHT_FLOOR, raw(rank, n)))

**THE CAN-FAIL CONTROLS ARE THE DESIGN.** Every property this file asserts is
expressed as a PREDICATE returning a complaint string, so the same predicate can
be pointed at a deliberately defective stand-in and required to COMPLAIN, naming
the defect. A property asserted only against a correct subject shows that the
subject passes, never that the assertion could fail.
"""
# pylint: disable=invalid-name,redefined-outer-name
# R0903 (too-few-public-methods): every class here is a PORT DOUBLE carrying
# exactly the port's own verb, or the weight-dropping falsifier carrying
# exactly `propose`. A second method added to clear a class-shape threshold
# would make each a worse stand-in for the thing it stands in for.
# pylint: disable=too-few-public-methods
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# suite by requirement.

from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixalloc.contention import (  # pylint: disable=wrong-import-position
    NEUTRAL_WEIGHT,
    WEIGHT_CEILING,
    WEIGHT_FLOOR,
    WEIGHT_STEP,
    Contender,
    rank,
    weight_for,
)
from nixalloc.seam import (  # pylint: disable=wrong-import-position
    ContentionPolicy,
    FinancialPicture,
    MirrorSnapshot,
    MirrorState,
    ProposalOutcome,
    RankingRow,
    Side,
    StopMode,
)
from nixalloc.sizing import (  # pylint: disable=wrong-import-position
    InstrumentSpec,
    SizingAllocator,
    SizingConfigError,
    SizingKnobs,
)

FREEZE = REPO / "downloads" / "ARC037-SEAM-FREEZE.md"

TICK_VALUE = 12.5
MICRO_RATIO = 10
PER_TRADE_RISK = 100.0
STOP_TICKS = 4
#: `(stop 4 + pad 2) * (12.5 / 10)` — the MES dollar risk every size below
#: divides by. Spelled once so a size in a test is arithmetic and not a guess.
MICRO_RISK = (STOP_TICKS + 2) * (TICK_VALUE / MICRO_RATIO)


# --------------------------------------------------------------------------
# THE PREDICATES — each returns a complaint, so each can be pointed at a plant
# --------------------------------------------------------------------------


def weights_are_real(weights: dict[Any, float]) -> str:
    """ "" when the weights carry information. The D3.260 complaint otherwise."""
    values = set(weights.values())
    if values == {NEUTRAL_WEIGHT}:
        return (
            f"every weight is NEUTRAL_WEIGHT {NEUTRAL_WEIGHT!r} — D3.260's exact "
            "shape: an ordering that moves and a weighting that does not"
        )
    if len(values) < 2:
        return f"only {len(values)} distinct weight(s): {sorted(values)}"
    return ""


def sizes_are_moved(sizes: dict[float, int]) -> str:
    """ "" when two ranks produced two SIZES. Not two weights — two sizes."""
    counts = set(sizes.values())
    if len(counts) < 2:
        return (
            f"weights {sorted(sizes)} produced contract count(s) "
            f"{sorted(counts)} — the weight was computed and never applied"
        )
    return ""


def bound_binds(position: int, field_size: int, bound: float, high: bool) -> str:
    """ "" when the clamp genuinely BOUND at `position`, by value."""
    raw = 1.0 + WEIGHT_STEP * ((field_size + 1) / 2 - position)
    if (raw <= bound) if high else (raw >= bound):
        return (
            f"raw({position}, {field_size}) == {raw!r} is inside the bound "
            f"{bound!r} — the clamp is decoration at this rank"
        )
    got = weight_for(position, field_size)
    if got != bound:
        return (
            f"raw({position}, {field_size}) == {raw!r} is outside {bound!r} and "
            f"weight_for returned {got!r} — the clamp did not bind"
        )
    return ""


# --------------------------------------------------------------------------
# The population
# --------------------------------------------------------------------------


class _Table:
    """A live `RankingTablePort` over a fixed row set. READ verbs only."""

    def __init__(self, rows: dict[Any, Any], available: bool = True) -> None:
        self._rows = rows
        self._available = available

    def available(self) -> bool:
        """§6.6:465's absent-or-stale predicate."""
        return self._available

    def row(self, strategy_id: str, symbol: str) -> Any:
        """The pair's row, or None."""
        return self._rows.get((strategy_id, symbol))


class _Raising:
    """A port that THROWS — §6.6:467 forbids an outage halting order flow."""

    def available(self) -> bool:
        """Raises, deliberately."""
        raise RuntimeError("planted: probe down")

    def row(self, strategy_id: str, symbol: str) -> Any:
        """Never reached."""
        del strategy_id, symbol
        raise RuntimeError("planted: lookup down")


class _Mirror:
    """A read-only `MirrorPort` double over one published picture."""

    def __init__(self, picture: Any) -> None:
        self._picture = picture

    def snapshot(self) -> Any:
        """One local read."""
        return MirrorSnapshot(
            state=MirrorState.FRESH, picture=self._picture, reason="test fixture"
        )

    def version(self) -> int:
        """The stamp on the held snapshot."""
        return int(self._picture.version)


class _Tradable:
    """The §16 U1 fast-drop cache, permitting everything."""

    def tradable(self, symbol: str) -> tuple[bool, str]:
        """`(tradable, reason)`."""
        del symbol
        return True, ""


class _Dropping:
    """The FALSIFIER allocator: accepts the weight and sizes without it."""

    def __init__(self, real: SizingAllocator) -> None:
        self._real = real

    def propose(self, *args: Any, **kwargs: Any) -> Any:
        """Drop `weight` on the floor."""
        kwargs.pop("weight", None)
        return self._real.propose(*args, **kwargs)


def _field(count: int) -> list[Contender]:
    """Arrival DESCENDS while the scores ascend, so arrival order disagrees."""
    return [
        Contender(strategy_id=f"s{i}", symbol=f"X{i}", arrival_seq=count - i)
        for i in range(1, count + 1)
    ]


def _rows(field: list[Contender], scores: list[float]) -> dict[Any, Any]:
    return {
        c.pair: RankingRow(c.strategy_id, c.symbol, score, 0.0)
        for c, score in zip(field, scores, strict=True)
    }


def _picture(balance: float = 250_000.0, committed: float = 20_000.0) -> Any:
    return FinancialPicture(
        version=937,
        published_ts=1_700_000_000.0,
        balance=balance,
        positions=(),
        margin_per_contract=MappingProxyType({"ES": 500.0, "MES": 50.0}),
        sum_open_margin=committed,
        sum_reservations=0.0,
        committed=committed,
        deployable=balance * 0.70 - committed,
    )


def _knobs(**overrides: Any) -> SizingKnobs:
    base: dict[str, Any] = {
        "per_trade_risk_usd": PER_TRADE_RISK,
        "deployable_pct": 0.70,
        "symbol_cap": {"ES": 50},
        "slippage_pad_ticks": {"ES": 2},
        "micro_full_threshold": 2,
        "quant_tolerance": 0.25,
    }
    base.update(overrides)
    return SizingKnobs(**base)


@pytest.fixture
def allocator() -> SizingAllocator:
    """The shipped sizer over a fresh picture. RISK binds, per §7's key finding."""
    return SizingAllocator(
        mirror=_Mirror(_picture()),
        tradability=_Tradable(),
        instruments={
            "ES": InstrumentSpec(
                symbol="ES",
                micro_symbol="MES",
                tick_value=TICK_VALUE,
                micro_ratio=MICRO_RATIO,
            )
        },
        knobs=_knobs(),
        bucket_cap=None,
    )


def _propose(alloc: Any, **kwargs: Any) -> Any:
    return alloc.propose(
        "s1", "ES", Side.LONG, STOP_TICKS, StopMode.FIXED, 1.5, **kwargs
    )


# --------------------------------------------------------------------------
# THE TRANSFORM — the literals are the ARCHITECT'S
# --------------------------------------------------------------------------


def test_the_four_LITERALS_are_the_ARCHITECT_RULINGS_and_not_this_trees() -> None:
    """§6.6:459 fixes no transform, so the numbers must come from the ruling."""
    text = FREEZE.read_text(encoding="utf-8")
    ruled = {
        name: float(raw)
        for name, raw in re.findall(
            r"^\s*(NEUTRAL_WEIGHT|WEIGHT_STEP|WEIGHT_FLOOR|WEIGHT_CEILING)\s*=\s*"
            r"([0-9]+\.[0-9]+)\s*$",
            text,
            re.MULTILINE,
        )
    }

    assert len(ruled) == 4, ruled
    assert ruled == {
        "NEUTRAL_WEIGHT": NEUTRAL_WEIGHT,
        "WEIGHT_STEP": WEIGHT_STEP,
        "WEIGHT_FLOOR": WEIGHT_FLOOR,
        "WEIGHT_CEILING": WEIGHT_CEILING,
    }, f"the module disagrees with {FREEZE.name} SEAM (b): {ruled}"


def test_the_transform_is_NEUTRAL_AT_THE_MEDIAN_RANK_and_moves_either_side() -> None:
    """`raw == 1.0` exactly at `(n + 1) / 2`, so a field is centred, not lifted."""
    assert weight_for(2, 3) == NEUTRAL_WEIGHT
    assert weight_for(3, 5) == NEUTRAL_WEIGHT
    assert weight_for(1, 3) == 1.25
    assert weight_for(3, 3) == 0.75
    assert weight_for(1, 3) > weight_for(2, 3) > weight_for(3, 3)


def test_a_FIELD_OF_ONE_is_exactly_NEUTRAL_and_falls_out_of_the_arithmetic() -> None:
    """A single contender had no race and must not be re-sized by one."""
    assert weight_for(1, 1) == NEUTRAL_WEIGHT


def test_the_CEILING_and_the_FLOOR_both_BIND_at_n_equals_8() -> None:
    """SEAM (b): `raw(1, 8) = 1.875` and `raw(8, 8) = 0.125`. Both, by value."""
    assert bound_binds(1, 8, WEIGHT_CEILING, high=True) == ""
    assert bound_binds(8, 8, WEIGHT_FLOOR, high=False) == ""
    assert weight_for(1, 8) == WEIGHT_CEILING
    assert weight_for(8, 8) == WEIGHT_FLOOR
    assert 1.0 + WEIGHT_STEP * ((8 + 1) / 2 - 1) == 1.875
    assert 1.0 + WEIGHT_STEP * ((8 + 1) / 2 - 8) == 0.125


def test_a_RANK_OUTSIDE_THE_FIELD_is_REFUSED_and_never_clamped() -> None:
    """Directive 4: fail closed and loud. A clamped rank sizes off a guess."""
    for bad in ((0, 3), (4, 3), (1, 0), (-1, 5)):
        with pytest.raises(ValueError, match="outside 1.."):
            weight_for(*bad)
    for wrong_type in ((1.5, 3), (True, 3), (1, "3")):
        with pytest.raises(TypeError, match="must be ints"):
            weight_for(*wrong_type)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# THE RANKING — real weights, and the FCFS routes still exactly neutral
# --------------------------------------------------------------------------


def test_a_THREE_WAY_RACE_carries_THREE_DISTINCT_weights_best_first() -> None:
    """§6.6:431 'feed the winners', measured as an inequality between weights."""
    field = _field(3)
    ranking = rank(field, _Table(_rows(field, [9.0, 3.0, 6.0])))

    assert ranking.policy is ContentionPolicy.PERFORMANCE_WEIGHTED
    assert weights_are_real(dict(ranking.weights)) == ""
    assert set(ranking.weights.values()) == {1.25, 1.0, 0.75}
    best, worst = ranking.ordering[0], ranking.ordering[-1]
    assert ranking.weights[best.pair] == 1.25
    assert ranking.weights[worst.pair] == 0.75


def test_TIED_SCORES_SHARE_A_RANK_and_therefore_SHARE_A_WEIGHT() -> None:
    """§6.6:455 makes equal scores an FCFS case — FCFS between them is neutral."""
    field = _field(3)
    ranking = rank(field, _Table(_rows(field, [9.0, 9.0, 1.0])))

    assert ranking.policy is ContentionPolicy.PERFORMANCE_WEIGHTED
    tied = {ranking.weights[field[0].pair], ranking.weights[field[1].pair]}
    assert len(tied) == 1, ranking.weights
    assert ranking.weights[field[2].pair] < tied.pop()


def test_the_REASON_NAMES_THE_BOUND_that_bound_a_weight() -> None:
    """§18: a clamp nobody can read is a clamp nobody can audit."""
    field = _field(8)
    ranking = rank(field, _Table(_rows(field, [float(80 - 10 * i) for i in range(8)])))

    assert WEIGHT_CEILING in set(ranking.weights.values())
    assert WEIGHT_FLOOR in set(ranking.weights.values())
    assert "WEIGHT_CEILING" in ranking.reason
    assert "WEIGHT_FLOOR" in ranking.reason
    assert "1.875" in ranking.reason
    assert "0.125" in ranking.reason


@pytest.mark.parametrize(
    "label",
    ["no port", "unavailable", "raises", "absent row", "tied", "cold start", "solo"],
)
def test_EVERY_DECLARED_NEUTRAL_ROUTE_is_exactly_NEUTRAL_WEIGHT(label: str) -> None:
    """Seven routes, driven ONE AT A TIME (§6.6:455/466 — neutral is a SIZE too).

    Parametrised rather than looped so a route that stops reaching the fallback
    fails as its own named test instead of hiding inside a passing aggregate.
    """
    trio = _field(3)
    live = _rows(trio, [9.0, 3.0, 6.0])
    absent = {k: v for k, v in live.items() if k != trio[1].pair}
    solo = _field(1)
    routes: dict[str, tuple[list[Contender], Any]] = {
        "no port": (trio, None),
        "unavailable": (trio, _Table(live, available=False)),
        "raises": (trio, _Raising()),
        "absent row": (trio, _Table(absent)),
        "tied": (trio, _Table(_rows(trio, [4.0, 4.0, 4.0]))),
        "cold start": (trio, _Table({})),
        "solo": (solo, _Table(_rows(solo, [7.0]))),
    }
    field, table = routes[label]

    ranking = rank(field, table)

    assert ranking.policy is ContentionPolicy.FCFS, ranking.reason
    assert set(ranking.weights.values()) == {NEUTRAL_WEIGHT}, ranking.weights
    assert ranking.reason.strip(), "§18: a fallback with no reason"


# --------------------------------------------------------------------------
# THE SIZE — the property that separates a weight from a number
# --------------------------------------------------------------------------


def test_TWO_GOs_DIFFERING_ONLY_IN_RANK_produce_TWO_DISTINCT_SIZES(
    allocator: SizingAllocator,
) -> None:
    """The whole of D3.260: not two weights — two CONTRACT COUNTS."""
    best, worst = weight_for(1, 3), weight_for(3, 3)
    sizes = {w: _propose(allocator, weight=w).contracts for w in (best, worst)}

    assert sizes_are_moved(sizes) == "", sizes
    assert sizes[best] == math.floor(PER_TRADE_RISK * best / MICRO_RISK) == 16
    assert sizes[worst] == math.floor(PER_TRADE_RISK * worst / MICRO_RISK) == 10
    assert sizes[best] > sizes[worst]


def test_the_APPLIED_weight_RIDES_the_rationale_the_Limiter_audits(
    allocator: SizingAllocator,
) -> None:
    """§16 U5: an audit record naming a weight the arithmetic did not use is worse."""
    proposal = _propose(allocator, weight=WEIGHT_CEILING)

    assert proposal.outcome is ProposalOutcome.SIZED
    assert proposal.rationale.score_weight == WEIGHT_CEILING
    assert "score weight 1.4 applied" in proposal.rationale.note
    assert "margin/cap/bucket UNWEIGHTED" in proposal.rationale.note


def test_an_EXISTING_CALLER_that_passes_NO_weight_sizes_exactly_as_before(
    allocator: SizingAllocator,
) -> None:
    """The parameter is keyword-only with a neutral default: nothing regressed."""
    assert (
        _propose(allocator).contracts
        == _propose(allocator, weight=NEUTRAL_WEIGHT).contracts
        == math.floor(PER_TRADE_RISK / MICRO_RISK)
        == 13
    )


@pytest.mark.parametrize(
    ("label", "balance", "cap", "risk"),
    [("margin", 400.0, 50, PER_TRADE_RISK), ("symbol cap", 250_000.0, 1, 1_000.0)],
)
def test_a_CAPITAL_SAFETY_CEILING_sizes_IDENTICALLY_at_both_bounds(
    label: str, balance: float, cap: int, risk: float
) -> None:
    """The direction that must not exist: a safety ceiling scaled by performance."""
    alloc = SizingAllocator(
        mirror=_Mirror(_picture(balance=balance, committed=0.0)),
        tradability=_Tradable(),
        instruments={
            "ES": InstrumentSpec(
                symbol="ES",
                micro_symbol="MES",
                tick_value=TICK_VALUE,
                micro_ratio=MICRO_RATIO,
            )
        },
        knobs=_knobs(per_trade_risk_usd=risk, symbol_cap={"ES": cap}),
        bucket_cap=None,
    )

    low = _propose(alloc, weight=WEIGHT_FLOOR)
    high = _propose(alloc, weight=WEIGHT_CEILING)

    assert low.rationale.binding is high.rationale.binding, label
    assert low.rationale.binding.value in {"margin", "symbol_cap"}, label
    assert low.contracts == high.contracts, (label, low.contracts, high.contracts)


@pytest.mark.parametrize(
    ("value", "condition"),
    [
        (math.nan, "not finite"),
        (0.0, "not positive"),
        (-1.0, "not positive"),
        (WEIGHT_CEILING + 0.01, "outside the frozen bounds"),
        (WEIGHT_FLOOR - 0.01, "outside the frozen bounds"),
        ("1.0", "not a real number"),
        (True, "not a real number"),
    ],
)
def test_an_ILLEGAL_weight_is_REFUSED_naming_the_CONDITION_never_clamped(
    allocator: SizingAllocator, value: Any, condition: str
) -> None:
    """§18 + directive 4. A clamp would make a broken caller look correct."""
    with pytest.raises(SizingConfigError) as caught:
        _propose(allocator, weight=value)

    assert condition in str(caught.value), str(caught.value)
    assert "SizingAllocator.propose" in str(caught.value)


# --------------------------------------------------------------------------
# THE CAN-FAIL CONTROLS — each predicate above, pointed at a real defect
# --------------------------------------------------------------------------


def test_CANFAIL_a_weighting_PINNED_TO_NEUTRAL_is_caught_naming_the_constant() -> None:
    """PLANT 1 — the D3.260 shape itself, driven through the live predicate."""
    field = _field(3)
    pinned = {c.pair: NEUTRAL_WEIGHT for c in field}

    complaint = weights_are_real(pinned)

    assert "NEUTRAL_WEIGHT" in complaint, complaint
    assert "D3.260" in complaint, complaint
    # …and the same predicate is silent on the real subject, or the plant
    # proved only that the predicate always complains.
    real = rank(field, _Table(_rows(field, [9.0, 3.0, 6.0])))
    assert weights_are_real(dict(real.weights)) == ""


def test_CANFAIL_a_weight_COMPUTED_AND_NEVER_APPLIED_is_caught(
    allocator: SizingAllocator,
) -> None:
    """PLANT 2 — the allocator that accepts the weight and drops it."""
    best, worst = weight_for(1, 3), weight_for(3, 3)
    dropped = {
        w: _propose(_Dropping(allocator), weight=w).contracts for w in (best, worst)
    }

    complaint = sizes_are_moved(dropped)

    assert "computed and never applied" in complaint, complaint
    assert set(dropped.values()) == {13}, dropped
    real = {w: _propose(allocator, weight=w).contracts for w in (best, worst)}
    assert sizes_are_moved(real) == ""


def test_CANFAIL_a_clamp_that_DOES_NOT_BIND_is_caught_at_both_ends() -> None:
    """PLANT 3 — the clamp removed, driven through the live bound predicate."""
    unclamped = 1.0 + WEIGHT_STEP * ((8 + 1) / 2 - 1)

    assert unclamped == 1.875
    assert unclamped != weight_for(1, 8), "the shipped transform did not clamp"
    # The predicate refuses a rank where the bound is NOT outside — the
    # decoration case §7.12/3 asks about.
    assert "decoration at this rank" in bound_binds(2, 3, WEIGHT_CEILING, high=True)
    assert bound_binds(1, 8, WEIGHT_CEILING, high=True) == ""
