"""ARC 038 / sub-agent E — I12, *"the cap is fed by REAL values"*, attacked.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §6.5:408 (the liquidity
governor and the net-liq survival floor), §7:470 (Sizing Physics), §15
C2/C3:983 (*"C2 Survival floor corrected to **net-liq** … Sizing stays on
cash"*; *"C3 Sizing guards: zero/invalid stop ⇒ deny; **missing margin ⇒
not-tradable**; clamp ≥ 0"*), `nics_risk_subsystem_spec_v1.3.md` §14:965
(*"**Survival is watched on net-liq**"*). Separately,
`docs/nix_check_contract.md` §17 (a safety property proven while its subject is
unavailable is not proven).

Every control here stands over a finding this arc's audit RAISED and DISCHARGED.
The findings, with the executed evidence, are in `downloads/arc038_findings_E.md`
(FE7, FE8, FE9); the residual that was NOT fixed is CHECK-DEBT D3.394/D3.395.

------------------------------------------------------------------------------
debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS SUITE TO MEASURE NOTHING?
------------------------------------------------------------------------------
1. **It could only ever run the PROTECTED half.** ARC 035 measured that
   self-mask three times. *Closed:* every control runs the UNPROTECTED half
   first and REQUIRES the fail-open outcome to reappear. The unprotected half is
   never a description — it is either the pre-fix EXPRESSION, evaluated
   (`_pre_fix_pad_admits`, `_pre_fix_floor_clears`), or the guard NEUTRALISED by
   monkeypatch (`_unpriceable_margin` → `None`).
2. **It could assert one rule and call that the gate.** A rule's verdict is not
   the pass's: `PictureCoherenceRule` runs in phase A and DENIED three of this
   audit's first survival drives before the survival rule was ever reached,
   which would have read as "fail-closed" over a rule that never ran. *Closed:*
   every verdict here comes out of a real `GatePass` built from the real
   `default_manifest`, on a financial picture that is COHERENT BY CONSTRUCTION
   (`committed = sum_open_margin + sum_reservations`), and the control asserts
   the DECIDING RULE'S NAME, not merely the decision.
3. **The control could be satisfied by a deny that arrives for the wrong
   reason.** A rule that raises also denies — `GatePass._dispatch` catches any
   exception and denies naming the rule, which is correct behaviour and NOT what
   these findings were about. *Closed:* check-contract rule 11 — every arm
   asserts the REASON, and specifically that the reason cites the spec clause
   (`§15 C3`, `§6.5`, `§17`) rather than an interpreter error.
4. **The arithmetic could be a coincidence.** A floor the mark happens to clear
   proves nothing about the floor. *Closed:* the survival arms state the
   arithmetic and drive the ADJACENT PAIR — a mark below the floor that must
   DENY and a mark above it that must APPROVE — so the boundary is measured
   rather than assumed.
5. **The `NaN` cases could be unreachable in the first place.** *Closed:*
   `ProposedOrder` and `FinancialPicture` are driven with the poisoned values
   directly, which is possible precisely because neither validates the field —
   and `risk_config`'s own boot rules are driven over a real `ModuleConfig`, so
   the boot half is measured on the shipped validator and not on a copy.

Doctrine C.9 boundary: §3's routing, phase partitioning and the reservation take
are `check_limiter_gate` and `test_limiter_gate.py`; §7:511's per-bucket
correlation cap is `check_allocator_caps`; §12.1's synthetic-stop-only ban is
`check_synthetic_stop_only`. What is HERE and nowhere else is the behaviour of
the two Limiter margin-cap rules and the survival floor when the numbers they
are fed are ZERO, NEGATIVE or NOT NUMBERS.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring,too-few-public-methods
# House convention: test names SHOUT the property, in the case the contract
# uses. Same disables as the sibling gate suites.
import math
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# pylint: disable=wrong-import-position
import risk_config  # pylint: disable=import-error
from nixrisk import gate as gate_mod  # pylint: disable=import-error
from nixrisk.gate import (  # pylint: disable=import-error
    AggregateMarginCapRule,
    DeployableCeilingRule,
    GatePass,
    KnobError,
    SurvivalHeadroomRule,
    default_manifest,
)
from nixrisk.seam import (  # pylint: disable=import-error
    Decision,
    FinancialPicture,
    ProposedOrder,
    Side,
    StopMode,
)

#: §12A:811's numbers, as the config file carries them. Used so the drives are
#: about the SHIPPED envelope rather than a shape invented here.
FRACTION = 0.70
PAD = 0.25


class _Clear:
    """A §6.5 flag port that never flags. Both port shapes, one class."""

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return False, "clear"


class _Free:
    """§4's one-in-flight lock, always free."""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        del strategy_id
        return False, "free"


class _NoHalt:
    """§12.5's HALT flag, never set."""

    def is_set(self) -> tuple[bool, str]:
        return False, ""


class _Mark:
    """A `NetLiqMarkPort`. `(net_liq, fresh)` on demand — including nonsense."""

    def __init__(self, value: float, fresh: bool = True) -> None:
        self.value = value
        self.fresh = fresh

    def mark(self) -> tuple[float, bool]:
        return self.value, self.fresh


def _manifest(
    *, net_liq: float = 1_000_000.0, fresh: bool = True, pad: float = PAD
) -> tuple[object, ...]:
    """§3's real rule set, from the real factory. Never a hand-built subset."""
    return default_manifest(
        blackout=_Clear(),
        tradability=_Clear(),
        staleness=_Clear(),
        clock_skew=_Clear(),
        in_flight=_Free(),
        net_liq=_Mark(net_liq, fresh),
        deployable_fraction=FRACTION,
        survival_safety_pad=pad,
        coherence_tolerance=1.0,
    )


def _order(qty: int = 1, mpc: float = 1000.0, stop_ticks: int = 20) -> ProposedOrder:
    return ProposedOrder(
        client_order_id="arc038e-1",
        strategy_id="arc038e",
        symbol="ES",
        side=Side.LONG,
        qty=qty,
        margin_per_contract=mpc,
        stop_ticks=stop_ticks,
        stop_mode=StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture(
    *, balance: float = 100_000.0, sum_open: float = 0.0, deployable: float = 70_000.0
) -> FinancialPicture:
    """COHERENT BY CONSTRUCTION — see §7.12 answer 2.

    `committed = sum_open_margin + sum_reservations` exactly, so
    `PictureCoherenceRule` (phase A) cannot deny before the phase-B rule under
    test has run. Three of this audit's first survival drives were masked that
    way and read as fail-closed over a rule that never executed.
    """
    return FinancialPicture(
        version=1,
        published_ts=1.0,
        balance=balance,
        positions=(),
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=sum_open,
        sum_reservations=0.0,
        committed=sum_open,
        deployable=deployable,
    )


def _pass(**manifest_kw: object):
    return GatePass(_NoHalt(), _manifest(**manifest_kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FE6 (not fixed — D3.392) — the cap is BLIND to the stop distance, measured.
# ---------------------------------------------------------------------------


def test_the_MARGIN_CAP_is_BLIND_to_the_STOP_DISTANCE_and_that_is_MEASURED() -> None:
    """D3.392, pinned as a figure rather than left as a claim.

    §7:481 makes `risk_$` a function of the stop; §7:501 prices bucket exposure
    from the distance. The Limiter's cap reads neither. This does NOT assert the
    blindness is CORRECT — that is an architect's ruling (D3.392). It asserts
    that the blindness is TOTAL, so the day a distance does reach the cap, this
    test reddens and the ruling is forced rather than drifted into.
    """
    rule = AggregateMarginCapRule("aggregate_margin_cap", FRACTION)
    verdicts = [
        rule.evaluate(_order(qty=100, stop_ticks=ticks), _picture())
        for ticks in (1, 20, 1_000_000)
    ]
    assert all(v.decision is Decision.SIZE_DOWN for v in verdicts)
    sized = {v.sized_qty for v in verdicts}
    assert sized == {69}, (
        f"a stop distance swung 1 -> 1_000_000 moved the cap's answer to "
        f"{sorted(s for s in sized if s is not None)}. If a distance now reaches "
        f"the cap, D3.392's ruling has landed and this test must be rewritten to "
        f"assert the new arithmetic — not deleted"
    )


# ---------------------------------------------------------------------------
# FE7 — §15 C3, *"missing margin ⇒ not-tradable"*. Both halves.
# ---------------------------------------------------------------------------

_UNPRICEABLE: tuple[float, ...] = (0.0, -1000.0, float("nan"), float("inf"))


def test_the_UNPROTECTED_half_really_APPROVES_a_hundred_UNPRICEABLE_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fail-open must APPEAR, or the guard below is over nothing (§0a).

    The guard is NEUTRALISED — patched to report every margin priceable — which
    reproduces the pre-fix code path exactly: the dollar figure is `<= 0`, so
    `committed + proposed < cap` clears on the cheapest branch.
    """
    monkeypatch.setattr(gate_mod, "_unpriceable_margin", lambda rule, order: None)
    approved = []
    for mpc in (0.0, -1000.0):
        outcome = _pass().evaluate(_order(qty=100, mpc=mpc), _picture(), 1.0)
        approved.append((mpc, outcome.decision, outcome.rule))
    assert all(d is Decision.APPROVE for _, d, _ in approved), (
        f"with the §15 C3 guard neutralised the pass must APPROVE, reproducing "
        f"the measured fail-open; got {approved}. If it denies anyway, some other "
        f"rule is doing this work and the guard below proves nothing"
    )
    assert {rule for _, _, rule in approved} == {"manifest_exhausted"}


def test_an_UNPRICEABLE_margin_is_DENIED_by_the_CAP_naming_SPEC15_C3() -> None:
    """FE7, protected half. §15 C3: *missing margin ⇒ not-tradable*."""
    control = _pass().evaluate(_order(qty=100, mpc=1000.0), _picture(), 1.0)
    assert control.decision is Decision.SIZE_DOWN, (
        f"the CONTROL must reach the cap and clamp — a priceable margin that did "
        f"not size down means the drive is not exercising the cap at all: "
        f"{control.decision.name} by {control.rule!r}"
    )
    assert control.rule == "aggregate_margin_cap"

    for mpc in _UNPRICEABLE:
        outcome = _pass().evaluate(_order(qty=100, mpc=mpc), _picture(), 1.0)
        assert outcome.decision is Decision.DENY, (
            f"margin_per_contract={mpc!r} produced {outcome.decision.name} by "
            f"{outcome.rule!r}. §15 C3 makes a missing margin NOT-TRADABLE, and "
            f"§2:35 makes the Limiter prohibitive — it may not accept a number "
            f"the permissive Allocator supplied without pricing it"
        )
        assert outcome.rule == "aggregate_margin_cap", outcome.rule
        assert "§15 C3" in outcome.reason, (
            f"denied for the wrong reason: {outcome.reason[:200]!r}. A rule that "
            f"RAISES also denies (GatePass catches it), and that deny names an "
            f"interpreter error rather than the spec clause — rule 11"
        )
        assert repr(mpc) in outcome.reason, (
            f"the reason must carry the offending value; got {outcome.reason[:200]!r}"
        )


def test_the_DEPLOYABLE_CEILING_refuses_an_UNPRICEABLE_margin_TOO() -> None:
    """Both §3 phase-B margin rules, not just the first one reached.

    Driven as the RULE rather than through the pass, because the aggregate cap
    denies first inside a full pass and would mask this one entirely — the same
    masking §7.12 answer 2 records.
    """
    rule = DeployableCeilingRule("deployable_ceiling")
    assert (
        rule.evaluate(_order(qty=1, mpc=1000.0), _picture()).decision
        is Decision.APPROVE
    )
    for mpc in _UNPRICEABLE:
        verdict = rule.evaluate(_order(qty=100, mpc=mpc), _picture())
        assert verdict.decision is Decision.DENY, (
            f"deployable_ceiling admitted margin_per_contract={mpc!r}: "
            f"{verdict.decision.name}"
        )
        assert "§15 C3" in verdict.reason


# ---------------------------------------------------------------------------
# FE8 — a fresh NaN net-liq mark. Both halves.
# ---------------------------------------------------------------------------

#: §6.5's survival arithmetic, spelled out so the boundary is measured and not
#: assumed: `sum_open_margin = 50_000`, one contract at `1000` ⇒
#: `projected = 51_000`; pad `0.25` ⇒ `floor = 63_750`.
_SUM_OPEN = 50_000.0
_PROJECTED = _SUM_OPEN + 1000.0
_FLOOR = _PROJECTED * (1.0 + PAD)


def _pre_fix_floor_clears(net_liq: float) -> bool:
    """The pre-fix decision, as an expression: did `net_liq < floor` CLEAR?

    This is the whole of the old guard. Evaluated rather than described, because
    a control whose unprotected half is a sentence has not run it.
    """
    return not net_liq < _FLOOR


def test_the_arithmetic_of_the_SURVIVAL_FLOOR_is_what_this_suite_says_it_is() -> None:
    """The adjacent pair. Without it a clearing mark proves nothing (§7.12 4)."""
    assert _FLOOR == pytest.approx(63_750.0)
    below = _pass(net_liq=_FLOOR - 1.0).evaluate(
        _order(1), _picture(sum_open=_SUM_OPEN), 1.0
    )
    assert below.decision is Decision.DENY and below.rule == "survival_headroom"
    assert "§6.5 survival floor" in below.reason
    above = _pass(net_liq=_FLOOR + 1.0).evaluate(
        _order(1), _picture(sum_open=_SUM_OPEN), 1.0
    )
    assert above.decision is Decision.APPROVE, (
        f"a mark ONE DOLLAR above the floor must pass, or the floor is not where "
        f"this suite says: {above.decision.name} by {above.rule!r}"
    )


def test_the_UNPROTECTED_half_really_CLEARS_the_floor_on_a_NaN_mark() -> None:
    """The fail-open must APPEAR. `NaN < floor` is False, so control fell through."""
    assert _pre_fix_floor_clears(float("nan")), (
        "the pre-fix comparison must CLEAR on a NaN mark — that is the FE8 harm. "
        "If it denies, the arm below is measuring nothing"
    )
    assert not _pre_fix_floor_clears(_FLOOR - 1.0), (
        "and it must still deny a genuinely-too-small mark, or the unprotected "
        "half is broken rather than permissive"
    )


def test_a_NaN_net_liq_mark_is_DENIED_even_though_it_is_FRESH() -> None:
    """FE8, protected half. §17: unavailable subject ⇒ not proven ⇒ deny."""
    for value in (float("nan"),):
        outcome = _pass(net_liq=value).evaluate(
            _order(1), _picture(sum_open=_SUM_OPEN), 1.0
        )
        assert outcome.decision is Decision.DENY, (
            f"a FRESH net-liq mark of {value!r} cleared §6.5's survival floor: "
            f"{outcome.decision.name} by {outcome.rule!r}. §14 watches survival "
            f"on net-liq, and a mark that is not a number is not a reading"
        )
        assert outcome.rule == "survival_headroom", outcome.rule
        assert "§17" in outcome.reason and "not a number" in outcome.reason, (
            f"denied for the wrong reason: {outcome.reason[:200]!r}"
        )


def test_the_STALE_arm_still_denies_and_is_a_DIFFERENT_branch() -> None:
    """A NaN is not a stale mark: the feed is alive and the number is rubbish.

    Asserted as two DISTINCT reasons because folding them would let a future
    edit satisfy one branch and delete the other.
    """
    stale = _pass(net_liq=1_000_000.0, fresh=False).evaluate(
        _order(1), _picture(sum_open=_SUM_OPEN), 1.0
    )
    assert stale.decision is Decision.DENY and stale.rule == "survival_headroom"
    assert "STALE or absent" in stale.reason
    nan = _pass(net_liq=float("nan")).evaluate(
        _order(1), _picture(sum_open=_SUM_OPEN), 1.0
    )
    assert "STALE or absent" not in nan.reason, (
        "the NaN branch must not be reported as staleness — an operator acting on "
        "'the feed stopped' would restart a feed that never stopped"
    )


# ---------------------------------------------------------------------------
# FE9 — a non-finite survival pad, at the rule AND at boot. Both halves.
# ---------------------------------------------------------------------------


def _pre_fix_pad_admits(pad: float) -> bool:
    """The pre-fix constructor guard, as an expression: was `pad` ADMITTED?"""
    return not pad < 0.0


def test_the_UNPROTECTED_half_really_ADMITS_a_NaN_survival_pad() -> None:
    """`NaN < 0.0` is False, so the old ordering guard let it through (§0a)."""
    assert _pre_fix_pad_admits(float("nan")), "the FE9 harm must be reproducible"
    assert _pre_fix_pad_admits(float("inf"))
    assert not _pre_fix_pad_admits(-1.0), (
        "and the old guard must still have caught a negative pad, or the "
        "unprotected half is not the guard that shipped"
    )


def test_a_NON_FINITE_survival_pad_is_REFUSED_at_CONSTRUCTION() -> None:
    """FE9, protected half. A NaN pad makes the floor NaN and every check False."""
    assert SurvivalHeadroomRule("survival_headroom", _Mark(1.0), 0.0)
    assert SurvivalHeadroomRule("survival_headroom", _Mark(1.0), PAD)
    for pad in (-1.0, float("nan"), float("inf")):
        with pytest.raises(KnobError) as caught:
            SurvivalHeadroomRule("survival_headroom", _Mark(1.0), pad)
        assert repr(pad) in str(caught.value), (
            f"the refusal must name the offending pad: {caught.value}"
        )
        assert "finite" in str(caught.value)


def test_a_NON_FINITE_scalar_KNOB_is_REJECTED_AT_BOOT_by_the_SHIPPED_rule() -> None:
    """FE9's boot half, driven over the shipped `risk_config` validators.

    Measured before the fix: `netliq_safety_pad = nan`, `= inf` and
    `ledger_drift_tolerance_usd = nan` were ALL accepted, because
    `_positive_scalars` used `leaf <= 0` (which NaN passes) and `_pct_range` only
    inspects keys ending `_pct`. The pair is asserted here so a repair to one
    cannot silently drop the other.
    """
    base = {
        "deployable_pct": 0.70,
        "agg_margin_cap_pct": 0.70,
        "netliq_safety_pad": 0.25,
        "ledger_drift_tolerance_usd": 1.0,
    }

    def _problems(knob: str, value: float) -> list[str]:
        values = dict(base)
        values[knob] = value
        loaded = {
            "limiter": risk_config.ModuleConfig(
                module="limiter",
                source=Path("risks/limiter.config.json"),
                values=values,
            )
        }
        # pylint: disable=protected-access
        return risk_config._positive_scalars(loaded) + risk_config._pct_range(loaded)

    assert not _problems("netliq_safety_pad", 0.25), (
        "the CONTROL must pass: a sane knob set that failed would make every "
        "rejection below true of any config at all"
    )
    for knob in ("netliq_safety_pad", "ledger_drift_tolerance_usd"):
        for value in (float("nan"), float("inf")):
            problems = _problems(knob, value)
            assert problems, (
                f"limiter.{knob}={value!r} was ACCEPTED AT BOOT. A non-finite "
                f"knob passes every ordering comparison a validator can make, "
                f"so it reaches the rule that reads it and disables whatever "
                f"comparison that rule performs (§12A:801-802)"
            )
            assert any(
                "not FINITE" in problem and knob in problem for problem in problems
            ), f"rejected without naming finiteness or the knob: {problems}"
    # The pre-fix predicate, RUN: this is WHY an inequality could not do it.
    # PLW0177 says "use math.isnan instead" and is right everywhere except here,
    # where the comparison against NaN IS the subject: the whole finding is that
    # `leaf <= 0` silently admits NaN, and asserting it with `math.isnan` would
    # assert something else entirely.
    # pylint: disable-next=unnecessary-negation
    assert not float("nan") <= 0, (  # noqa: PLW0177
        "NaN <= 0 is False — that was the whole defect"
    )
    assert math.isfinite(0.25) and not math.isfinite(float("nan"))
