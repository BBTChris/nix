"""ARC 031 Stage 1 / C — behaviour of `nixalloc.caps` and `nixalloc.contention`.

C1 (§7:497-515, the correlation-bucket cap), C2 (§6.6:465-468, the FCFS
fallback with the writer absent) and C3 (§2:40 / §6.6:459-460, the authority
boundary), driven against the SHIPPED modules.

THE ONE THING THIS FILE IS BUILT AROUND, because it is the defect the brief
names and it is real: **a cap test with ONE position per bucket never exercises
the SUMMATION.** For a single element `sum(xs) == max(xs)`, so a cap that
returns the largest same-bucket exposure passes such a test perfectly. Every
summation control below therefore drives TWO same-bucket positions, and
`test_a_max_shaped_cap_is_CAUGHT_by_the_same_case` builds the falsifier — a
literal `max()`-based cap — and proves the case discriminates.

Every control asserts the REASON — the named term, the binding constraint, the
fallback's own explanation — never a bare number or a status alone (check
contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixalloc.caps import (
    BucketCapError,
    CapConfig,
    Exposure,
    admit,
    bucket_dollar_risk,
    bucket_for,
    dollar_risk,
    load_cap_config,
    per_contract_dollar_risk,
)
from nixalloc.contention import NEUTRAL_WEIGHT, Contender, fcfs_order, rank
from nixalloc.seam import BUCKET_OF, BindingConstraint, ContentionPolicy, RankingRow

# ---------------------------------------------------------------------------
# Fixtures. The config is SHIPPED, loaded off disk; only the ranking-table
# ports are fakes, and they are fakes because §6.6's writer (the Scoring
# process, R5) does not exist and cannot be driven.
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> CapConfig:
    """The real `risks/` set, loaded through the real loader."""
    return load_cap_config(REPO)


@pytest.fixture
def same_bucket() -> tuple[str, str]:
    """Two symbols the SEAM puts in one bucket. Derived, never typed here."""
    by_bucket: dict[str, list[str]] = {}
    for symbol, bucket in sorted(BUCKET_OF.items()):
        by_bucket.setdefault(bucket.value, []).append(symbol)
    pairs = [members for members in by_bucket.values() if len(members) >= 2]
    assert pairs, (
        "no bucket holds two symbols, so no test in this file can exercise a "
        "SUM — with one exposure per bucket, sum() and max() are equal"
    )
    return pairs[0][0], pairs[0][1]


@pytest.fixture
def foreign(same_bucket: tuple[str, str]) -> str:
    """A symbol in a DIFFERENT bucket from `same_bucket`."""
    home = BUCKET_OF[same_bucket[0]]
    others = [
        symbol for symbol, bucket in sorted(BUCKET_OF.items()) if bucket is not home
    ]
    assert others, (
        "every symbol is in one bucket; the cross-bucket control has no subject"
    )
    return others[0]


class Table:
    """A ranking table with explicit rows. The seam's READ port, faked."""

    def __init__(
        self, rows: dict[tuple[str, str], RankingRow], live: bool = True
    ) -> None:
        self._rows = rows
        self._live = live

    def available(self) -> bool:
        """§6.6:465 — False when the table is absent or stale."""
        return self._live

    def row(self, strategy_id: str, symbol: str) -> RankingRow | None:
        """§6.6:463's O(1) lookup, never math."""
        return self._rows.get((strategy_id, symbol))


class Exploding:
    """A port that throws, the way a just-died publisher actually presents."""

    def available(self) -> bool:
        """The failure mode a just-died publisher actually presents."""
        raise RuntimeError("scoring shared-memory segment is gone")

    def row(self, strategy_id: str, symbol: str) -> RankingRow | None:
        """Unreachable; declared so the fake satisfies the seam's shape."""
        raise RuntimeError(f"unreachable {strategy_id}/{symbol}")


# ===========================================================================
# C1 — the bucket cap, by formula
# ===========================================================================


def test_bucket_membership_is_READ_FROM_THE_SEAM_and_never_re_spelled() -> None:
    """§7:498's map lives in `nixalloc.seam`; `caps.py` reads it, never a copy.

    Asserted as an IDENTITY over the seam's own table rather than against a
    list typed here — a second spelling of the membership is free to drift, and
    `check_allocator_seam` already proves the seam's copy is the frozen spec's.
    """
    for symbol, bucket in BUCKET_OF.items():
        assert bucket_for(symbol) is bucket
    assert bucket_for("XYZ") is None, (
        "an unknown symbol was given a bucket — guessing one would put a "
        "symbol-scope decision inside a concentration cap"
    )


def test_the_exposure_unit_is_SPEC_7s_formula(config: CapConfig) -> None:
    """`(stop_ticks + slippage_pad) × tick_value × contracts` (§7:501)."""
    symbol = "ES"
    pad = float(dict(config.slippage_pad_ticks)[symbol])
    tick = float(dict(config.tick_value_usd)[symbol])
    assert dollar_risk(Exposure(symbol, 4, 20), config) == (20 + pad) * tick * 4


def test_a_micro_carries_one_tenth_the_weight_and_it_FALLS_OUT(
    config: CapConfig,
) -> None:
    """§7:502-503: micros count at 1/10, 'their dollar risk falls out naturally'.

    Both spellings of that sentence are asserted to agree: applying the
    configured weight to the FULL contract's tick value, and using a micro
    instrument's own tick value (a tenth of the full one). The equivalence is
    the spec's claim, so it is checked rather than trusted.
    """
    full = per_contract_dollar_risk("ES", 20, config)
    weighted = per_contract_dollar_risk("ES", 20, config, micro=True)
    assert weighted == pytest.approx(full * config.micro_weight)
    micro_native = CapConfig(
        bucket_cap_pct=config.bucket_cap_pct,
        slippage_pad_ticks=config.slippage_pad_ticks,
        tick_value_usd={"ES": float(dict(config.tick_value_usd)["ES"]) / 10.0},
        micro_weight=config.micro_weight,
    )
    assert weighted == pytest.approx(per_contract_dollar_risk("ES", 20, micro_native))


# ---------------------------------------------------------------------------
# §0a — THE SUMMATION. Two same-bucket positions, or nothing is measured.
# ---------------------------------------------------------------------------


def test_TWO_same_bucket_positions_are_SUMMED_not_maxed(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """The heart of C1. `used` is the SUM, and the sum is not the larger member."""
    first, second = same_bucket
    exposures = [Exposure(first, 2, 20), Exposure(second, 3, 20)]
    each = [dollar_risk(e, config) for e in exposures]
    total, largest = sum(each), max(each)
    assert total > largest, (
        "the two exposures are equal, so this case cannot tell a sum from a "
        f"maximum: {each}"
    )
    used, contributors = bucket_dollar_risk(exposures, BUCKET_OF[first], config)
    assert contributors == 2, (
        f"summed {contributors} exposure(s); the case is built on two, and at "
        "one exposure sum() and max() are the same number"
    )
    assert used == pytest.approx(total), (
        f"reported {used} for the bucket; the SUM of {each} is {total} and the "
        f"largest single member is {largest}"
    )


def test_the_THIRD_proposal_is_capped_against_the_SUM_of_the_first_two(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """§7:511 applied to a book that already holds two same-bucket positions."""
    first, second = same_bucket
    exposures = [Exposure(first, 2, 20), Exposure(second, 3, 20)]
    balance = 100_000.0
    decision = admit(first, 5, 20, exposures, balance, config)
    ceiling = float(dict(config.bucket_cap_pct)[BUCKET_OF[first].value]) * balance
    per = per_contract_dollar_risk(first, 20, config)
    total = sum(dollar_risk(e, config) for e in exposures)
    expected = max(0, int((ceiling - total) // per)) if ceiling > total else 0
    assert decision.admitted_contracts == expected, decision.reason
    assert decision.used_dollar_risk == pytest.approx(total), decision.reason
    assert decision.contributors == 2, decision.reason
    assert "sum over 2 same-bucket exposure(s)" in decision.reason


def test_a_max_shaped_cap_is_CAUGHT_by_the_same_case(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """THE FALSIFIER. A cap that maxes instead of summing gives a DIFFERENT answer.

    This is the evidence that the two tests above could have failed. The wrong
    implementation is written out here and driven on the identical inputs; if
    it produced the same number, the case would prove nothing and this test
    says so in its own assertion message.
    """
    first, second = same_bucket
    exposures = [Exposure(first, 2, 20), Exposure(second, 3, 20)]
    balance = 100_000.0
    per = per_contract_dollar_risk(first, 20, config)
    ceiling = float(dict(config.bucket_cap_pct)[BUCKET_OF[first].value]) * balance

    def wrong_used() -> float:
        """The classic defect: cap against the LARGEST member, not the sum."""
        return max(dollar_risk(e, config) for e in exposures)

    def fits(used: float) -> int:
        return max(0, int((ceiling - used) // per)) if ceiling > used else 0

    right = admit(first, 5, 20, exposures, balance, config)
    assert fits(wrong_used()) != fits(right.used_dollar_risk), (
        "the max()-shaped cap admits the same size as the sum-shaped one here, "
        "so this case does not discriminate and the summation is unproven"
    )
    assert right.admitted_contracts == fits(right.used_dollar_risk)
    assert right.admitted_contracts != fits(wrong_used())


def test_the_sum_is_over_THREE_positions_too(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """Not just pairwise: every same-bucket exposure enters the sum."""
    first, second = same_bucket
    exposures = [
        Exposure(first, 1, 10),
        Exposure(second, 1, 10),
        Exposure(first, 1, 30),
    ]
    used, contributors = bucket_dollar_risk(exposures, BUCKET_OF[first], config)
    assert contributors == 3
    assert used == pytest.approx(sum(dollar_risk(e, config) for e in exposures))


# ---------------------------------------------------------------------------
# SAME-BUCKET ONLY — the positive control (§7:505-510)
# ---------------------------------------------------------------------------


def test_a_huge_position_in_ANOTHER_bucket_does_not_shrink_this_one(
    config: CapConfig, same_bucket: tuple[str, str], foreign: str
) -> None:
    """§7:505-510. Cross-bucket exposure is the §6.5 layers' job, not this rule."""
    first, _ = same_bucket
    alone = admit(first, 3, 20, [], 100_000.0, config)
    enormous = [Exposure(foreign, 500, 200)]
    beside = admit(first, 3, 20, enormous, 100_000.0, config)
    assert dollar_risk(enormous[0], config) > alone.ceiling_dollar_risk * 100, (
        "the foreign position is not large enough for this control to mean "
        "anything — it must dwarf the ceiling it is proving it cannot touch"
    )
    assert beside.admitted_contracts == alone.admitted_contracts, beside.reason
    assert beside.used_dollar_risk == alone.used_dollar_risk == 0.0
    assert beside.contributors == 0, beside.reason


def test_the_foreign_bucket_HAS_its_own_ceiling_and_that_one_does_bind(
    config: CapConfig, foreign: str
) -> None:
    """The other half of the control: the cap is not simply inert on that symbol."""
    enormous = [Exposure(foreign, 500, 200)]
    decision = admit(foreign, 1, 20, enormous, 100_000.0, config)
    assert decision.admitted_contracts == 0, decision.reason
    assert decision.binding is BindingConstraint.BUCKET_CAP
    assert decision.contributors == 1, decision.reason


# ---------------------------------------------------------------------------
# Size down toward the ceiling, then deny at zero (§7:514)
# ---------------------------------------------------------------------------


def test_a_partial_fit_is_SIZED_DOWN_and_not_denied(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """§7:514: 'size-down toward the ceiling, then deny at zero' — the first half."""
    first, _ = same_bucket
    per = per_contract_dollar_risk(first, 20, config)
    pct = float(dict(config.bucket_cap_pct)[BUCKET_OF[first].value])
    decision = admit(first, 5, 20, [], (per * 3.5) / pct, config)
    assert decision.admitted_contracts == 3, decision.reason
    assert decision.sized_down is True
    assert decision.denied is False
    assert decision.binding is BindingConstraint.BUCKET_CAP
    assert "sized down toward the ceiling" in decision.reason


def test_a_no_fit_is_DENIED_at_zero(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """§7:514's second half. Never rounded up to the smallest tradeable size."""
    first, _ = same_bucket
    per = per_contract_dollar_risk(first, 20, config)
    pct = float(dict(config.bucket_cap_pct)[BUCKET_OF[first].value])
    decision = admit(first, 5, 20, [], (per * 0.5) / pct, config)
    assert decision.admitted_contracts == 0
    assert decision.denied is True
    assert "DENIED at zero" in decision.reason


def test_a_proposal_that_fits_WHOLE_is_not_touched(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """A cap that always shrinks is as wrong as one that never does."""
    first, _ = same_bucket
    decision = admit(first, 2, 20, [], 10_000_000.0, config)
    assert decision.admitted_contracts == 2
    assert decision.binding is BindingConstraint.NONE
    assert "admitted whole" in decision.reason


def test_an_exactly_full_bucket_admits_nothing_more(
    config: CapConfig, same_bucket: tuple[str, str]
) -> None:
    """The boundary: headroom of exactly zero is a deny, not a rounding case."""
    first, _ = same_bucket
    per = per_contract_dollar_risk(first, 20, config)
    pct = float(dict(config.bucket_cap_pct)[BUCKET_OF[first].value])
    balance = (per * 2) / pct
    decision = admit(first, 1, 20, [Exposure(first, 2, 20)], balance, config)
    assert decision.ceiling_dollar_risk == pytest.approx(decision.used_dollar_risk)
    assert decision.admitted_contracts == 0, decision.reason


# ---------------------------------------------------------------------------
# Fail closed and loud (§7:483, CLAUDE.md directive 4)
# ---------------------------------------------------------------------------


def test_an_unbucketed_symbol_RAISES_rather_than_sailing_through(
    config: CapConfig,
) -> None:
    """§7:483 — an unresolvable symbol is not-tradable, never silently admitted."""
    with pytest.raises(BucketCapError) as caught:
        admit("XYZ", 1, 20, [], 100_000.0, config)
    assert "places it in no correlation bucket" in str(caught.value)


def test_a_zero_stop_intent_RAISES(config: CapConfig) -> None:
    """§7:483 — invalid/zero stop intent is a DENY; no size is invented."""
    with pytest.raises(BucketCapError) as caught:
        admit("ES", 1, 0, [], 100_000.0, config)
    assert "invalid/zero stop intent" in str(caught.value)


def test_a_missing_tick_value_RAISES_rather_than_defaulting(
    config: CapConfig,
) -> None:
    """Doctrine C.7: a defaulted ceiling is a ceiling nobody set."""
    stripped = CapConfig(
        bucket_cap_pct=config.bucket_cap_pct,
        slippage_pad_ticks=config.slippage_pad_ticks,
        tick_value_usd={},
        micro_weight=config.micro_weight,
    )
    with pytest.raises(BucketCapError) as caught:
        per_contract_dollar_risk("ES", 20, stripped)
    assert "never defaulted" in str(caught.value)


def test_the_shipped_config_passes_its_OWN_declared_boot_rules() -> None:
    """The `_boot_validation` ids are rules that RUN, not prose (§12A:801)."""
    config = load_cap_config(REPO)
    assert set(BUCKET_OF) <= set(config.tick_value_usd)
    assert 0 < config.micro_weight <= 1


# ===========================================================================
# C2 — FCFS contention with the writer absent (§6.6:465-468)
# ===========================================================================


def _race() -> list[Contender]:
    """Three contenders whose ARRIVAL order disagrees with their alphabet.

    §7.12: an FCFS answer that coincides with alphabetical order proves
    nothing, so the arrival sequence is built to disagree with it and each
    control asserts that disagreement before asserting the answer.
    """
    return [
        Contender(strategy_id="s2", symbol="GC", arrival_seq=1),
        Contender(strategy_id="s3", symbol="ZN", arrival_seq=2),
        Contender(strategy_id="s1", symbol="CL", arrival_seq=3),
    ]


def test_the_race_used_by_every_FCFS_control_DISAGREES_with_the_alphabet() -> None:
    """The non-vacuity of every FCFS control below it (§7.12/2).

    An FCFS answer that coincides with the alphabet — in EITHER direction —
    proves nothing, because a cap that sorted by symbol would pass it. So the
    arrival order is asserted to be neither, and the strategy ids are asserted
    not to be in order either, before any control reads an ordering.
    """
    symbols = [c.symbol for c in _race()]
    assert symbols != sorted(symbols), "arrival order is alphabetical ascending"
    assert symbols != sorted(symbols, reverse=True), (
        "arrival order is alphabetical descending"
    )
    strategies = [c.strategy_id for c in _race()]
    assert strategies != sorted(strategies)
    assert strategies != sorted(strategies, reverse=True)


def test_an_ABSENT_table_falls_back_to_FCFS_by_ARRIVAL() -> None:
    """§6.6:465 — and this is the state the whole system is in until R5."""
    ranking = rank(_race(), None)
    assert ranking.policy is ContentionPolicy.FCFS
    assert ranking.is_fallback is True
    assert [c.symbol for c in ranking.ordering] == ["GC", "ZN", "CL"]
    assert "Scoring process is R5" in ranking.reason
    assert ranking.scored == 0


def test_a_table_that_reports_itself_UNAVAILABLE_falls_back_to_FCFS() -> None:
    """Present-but-stale: `available()` False is the seam's stale signal."""
    rows = {c.pair: RankingRow(c.strategy_id, c.symbol, 9.0, 0.0) for c in _race()}
    ranking = rank(_race(), Table(rows, live=False))
    assert ranking.policy is ContentionPolicy.FCFS
    assert [c.symbol for c in ranking.ordering] == ["GC", "ZN", "CL"]
    assert "unavailable (absent or stale)" in ranking.reason


def test_a_STALE_ROW_is_treated_as_absent_when_an_age_is_supplied() -> None:
    """§6.6:455 — a row past threshold is an absent score, so FCFS."""
    rows = {
        c.pair: RankingRow(c.strategy_id, c.symbol, float(i), 0.0)
        for i, c in enumerate(_race())
    }
    ranking = rank(_race(), Table(rows), max_age_s=5.0, now=1_000.0)
    assert ranking.policy is ContentionPolicy.FCFS
    assert "have a live ranking row" in ranking.reason
    assert [c.symbol for c in ranking.ordering] == ["GC", "ZN", "CL"]


def test_a_table_that_RAISES_never_halts_order_flow() -> None:
    """§6.6:467-468 — a scoring outage must NEVER halt order flow."""
    ranking = rank(_race(), Exploding())
    assert ranking.policy is ContentionPolicy.FCFS
    assert [c.symbol for c in ranking.ordering] == ["GC", "ZN", "CL"]
    assert "RuntimeError" in ranking.reason
    assert "shared-memory segment is gone" in ranking.reason


def test_EQUAL_scores_fall_back_to_FCFS() -> None:
    """§6.6:455 — equal scores are the cold-start case, and cold start is FCFS."""
    rows = {c.pair: RankingRow(c.strategy_id, c.symbol, 4.25, 0.0) for c in _race()}
    ranking = rank(_race(), Table(rows))
    assert ranking.policy is ContentionPolicy.FCFS
    assert [c.symbol for c in ranking.ordering] == ["GC", "ZN", "CL"]
    assert "is equal" in ranking.reason


def test_a_PARTIAL_table_falls_back_rather_than_ranking_the_scored_pair_first() -> None:
    """One live row among three is an ABSENT-score case, not a partial order."""
    race = _race()
    rows = {race[2].pair: RankingRow(race[2].strategy_id, race[2].symbol, 99.0, 0.0)}
    ranking = rank(race, Table(rows))
    assert ranking.policy is ContentionPolicy.FCFS
    assert [c.symbol for c in ranking.ordering] == ["GC", "ZN", "CL"]
    assert "1 of 3 contender(s) have a live ranking row" in ranking.reason


def test_DIFFERENT_scores_move_the_ordering_so_the_READ_seam_is_real() -> None:
    """Without this, a module that never called the port would look identical."""
    race = _race()
    scores = {"GC": 1.0, "ZN": 3.0, "CL": 2.0}
    rows = {
        c.pair: RankingRow(c.strategy_id, c.symbol, scores[c.symbol], 0.0) for c in race
    }
    ranking = rank(race, Table(rows))
    assert ranking.policy is ContentionPolicy.PERFORMANCE_WEIGHTED
    assert ranking.is_fallback is False
    ordering = [c.symbol for c in ranking.ordering]
    assert ordering == ["ZN", "CL", "GC"]
    assert ordering != sorted(ordering), (
        "the score order is alphabetical, so it proves nothing"
    )
    assert ordering != sorted(ordering, reverse=True)
    assert [c.symbol for c in ranking.ordering] != [c.symbol for c in race]
    assert ranking.scored == 3


def test_the_performance_ordering_breaks_TIES_on_arrival() -> None:
    """§6.6:455's equal-score rule, applied inside a larger field."""
    race = _race()
    scores = {"ZN": 1.0, "GC": 1.0, "CL": 5.0}
    rows = {
        c.pair: RankingRow(c.strategy_id, c.symbol, scores[c.symbol], 0.0) for c in race
    }
    ranking = rank(race, Table(rows))
    assert [c.symbol for c in ranking.ordering] == ["CL", "GC", "ZN"]


def test_FCFS_is_structurally_neutral_and_favours_no_symbol() -> None:
    """§6.6:466. Rename every symbol; the arrival ordering is unchanged."""
    race = _race()
    renamed = [
        Contender(strategy_id=c.strategy_id, symbol=f"A{i}", arrival_seq=c.arrival_seq)
        for i, c in enumerate(race)
    ]
    assert [c.arrival_seq for c in fcfs_order(race)] == [
        c.arrival_seq for c in fcfs_order(renamed)
    ]
    reversed_alphabet = [
        Contender(strategy_id=c.strategy_id, symbol=s, arrival_seq=c.arrival_seq)
        for c, s in zip(race, ["ZZ", "MM", "AA"], strict=True)
    ]
    assert [c.arrival_seq for c in fcfs_order(reversed_alphabet)] == [1, 2, 3]


def test_FCFS_follows_ARRIVAL_and_not_the_order_it_was_handed() -> None:
    """A shuffled input with the same arrival stamps yields the same answer."""
    race = _race()
    shuffled = [race[2], race[0], race[1]]
    assert [c.symbol for c in fcfs_order(shuffled)] == [
        c.symbol for c in fcfs_order(race)
    ]
    assert [c.symbol for c in fcfs_order(shuffled)] == ["GC", "ZN", "CL"]


def test_the_fallback_is_DETERMINISTIC_across_repeated_calls() -> None:
    """§6.6:466 — 'deterministic' is a property, so it is measured."""
    race = _race()
    answers = {tuple(c.symbol for c in rank(race, None).ordering) for _ in range(50)}
    assert answers == {("GC", "ZN", "CL")}


def test_every_absent_shaped_port_reaches_the_SAME_ordering() -> None:
    """Three different outages, one ordering, three different reasons (§18)."""
    race = _race()
    rows = {c.pair: RankingRow(c.strategy_id, c.symbol, 3.0, 0.0) for c in race}
    ports = [None, Table(rows, live=False), Exploding(), Table({})]
    orderings = {tuple(c.symbol for c in rank(race, p).ordering) for p in ports}
    reasons = {rank(race, p).reason for p in ports}
    assert orderings == {("GC", "ZN", "CL")}
    assert len(reasons) == len(ports), f"outages are indistinguishable: {reasons}"


def test_the_fallback_returns_IMMEDIATELY_rather_than_waiting() -> None:
    """§6.6:468 — an absent table must never become an unbounded wait."""
    import time  # pylint: disable=import-outside-toplevel

    started = time.monotonic()
    for _ in range(1_000):
        rank(_race(), None)
    assert time.monotonic() - started < 1.0


def test_an_empty_race_reports_that_it_ranked_NOTHING() -> None:
    """§7.12/1 — an empty race is not a correct answer, it is no measurement."""
    ranking = rank([], None)
    assert not ranking.ordering
    assert ranking.contenders == 0


# ===========================================================================
# C3 — the authority boundary (§2:40, §6.6:459-460)
# ===========================================================================

#: Verbs whose presence would make the Allocator award a shared resource.
AWARD_VERBS = (
    "award",
    "winner",
    "win",
    "grant",
    "allocate",
    "assign",
    "arbitrate",
    "settle",
    "reserve",
    "commit",
    "claim",
)


def test_the_contention_module_exposes_NO_verb_that_awards_anything() -> None:
    """BY ATTEMPT: reach for each verb on the shipped module and find nothing."""
    import nixalloc.contention as module  # pylint: disable=import-outside-toplevel

    for verb in AWARD_VERBS:
        assert getattr(module, verb, None) is None, (
            f"{verb!r} exists on the Allocator's contention module — §6.6:459-460 "
            "gives arbitration to the LIMITER, and §2:40 makes the Allocator "
            "permissive"
        )


def test_the_ranking_object_exposes_NO_winner() -> None:
    """The same boundary one level down: a ranking is an ORDERING, not a verdict."""
    ranking = rank(_race(), None)
    for verb in AWARD_VERBS:
        assert getattr(ranking, verb, None) is None, (
            f"ContentionRanking.{verb} exists — the Allocator would be naming a "
            "winner, which §6.6:459-460 gives to the Limiter"
        )


def test_the_weights_are_REAL_under_PERFORMANCE_and_NEUTRAL_under_FCFS() -> None:
    """ARC 037 / D3.260: the transform landed, and FCFS stayed neutral.

    This assertion is the INVERSE of the one it replaces, which read "the
    weights are NEUTRAL under both policies and say so" and was true until the
    score -> sizing-weight transform existed. It is rewritten rather than
    deleted because the property it guards did not go away: **FCFS must still
    be exactly neutral**, and now something else must not be.
    """
    race = _race()
    scores = {"GC": 1.0, "ZN": 3.0, "CL": 2.0}
    rows = {
        c.pair: RankingRow(c.strategy_id, c.symbol, scores[c.symbol], 0.0) for c in race
    }
    weighted = rank(race, Table(rows))
    fallback = rank(race, None)
    assert len(set(weighted.weights.values())) == 3, weighted.weights
    assert set(weighted.weights.values()) == {0.75, 1.0, 1.25}, weighted.weights
    assert set(fallback.weights.values()) == {NEUTRAL_WEIGHT}, fallback.weights
    assert "ORDINAL IN THE DENSE RANK" in weighted.reason
    assert "ADVISORY" in weighted.reason


def test_nothing_in_the_contention_module_computes_an_EMA() -> None:
    """§6.6:461 — nobody but the Scoring process COMPUTES the score."""
    source = (REPO / "scripts/nixalloc/contention.py").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    for banned in ("math.exp", "** ", "alpha", "smoothing"):
        assert banned not in body.rsplit('"""', maxsplit=1)[-1], (
            f"{banned!r} appears in the executable body — computing the EMA is "
            "the allocation judgment §6.6:461-463 keeps out of the consumer"
        )
