"""ARC 033 / Stage 2 — §6.5's unified pre-size denial, COMPOSED and DRIVEN.

Stage 1's four sub-agents each built a PRODUCER against the frozen seam in its
own worktree, with no visibility into the others. `scripts/nixrisk/gate.py` has
carried the CONSUMERS since ARC 028 — `SymbolFlagRule("blackout_window", ...)`,
`SymbolFlagRule("data_staleness", ...)`, `GlobalFlagRule("clock_skew", ...)` and
`HaltFlagPort` as branch 0 — with nothing implementing any of them. **This module
is where the four producers meet the one executor**, which is the argument none
of the five gates could make alone.

That is the ARC 031 lesson stated as a file: three green Stage-1 gates and a
correlation cap that could not run, because each unit was driven on inputs it
manufactured and the composition was never made. Here every disjunct of §6.5's

    HALT ∨ now ∈ any window ∨ margin elevated ∨ data stale ∨ clock skewed

is driven through the REAL `GatePass` against the REAL producers.

`debug.md` §7.12 — what would have to be true for this module to pass while
measuring nothing?

 1. **Nothing could ever be admitted**, so every "denied" assertion would hold
    over a pass that denies unconditionally. CLOSED: `test_the_CLEAR_pass_admits`
    runs first in reading order and asserts an APPROVE with every producer clear.
    Without it the whole file is vacuous.
 2. **A disjunct could be driven by a double rather than by its producer**, which
    is the manufactured-input pass. CLOSED: every flag is produced by the SHIPPED
    module — `blackout.BlackoutEvaluator`, `freshness.StalenessFlagPort`,
    `freshness.ClockSkewMonitor`, `halt.HaltFlag`. The only doubles here are the
    Plane-1/Plane-2 sinks and the picture, which are transports, not deciders.
 3. **A denial could be asserted by status alone**, so a pass denying for the
    WRONG reason would pass. CLOSED: every assertion names the rule and the
    reason text (check-contract §18); the rule NAME is what distinguishes
    "denied because stale" from "denied because halted".
 4. **The interlock could be asserted rather than driven** — §6.5 says the 70%
    cap is only safe because the blackouts keep the book out of the close-snap,
    and a test that never builds a cap-breaching proposal proves nothing about
    the coupling. CLOSED: `test_the_65_INTERLOCK_...` builds a proposal that
    WOULD breach the cap, proves it breaches with the window clear, then proves
    the blackout denies it FIRST with the window open.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring,too-few-public-methods
# The doubles below are TRANSPORTS and one-verb stand-ins, not subjects: each
# implements exactly the port verb `gate.py` declares and nothing else. Giving
# them a second method to clear a class-shape threshold would be inventing
# surface, and on a decision path surface IS authority (§2) — the same reasoning
# `nixalloc/seam.py` and `nixrisk/seam.py` both record for their own Protocols.

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk import gate as gate_mod  # pylint: disable=wrong-import-position
from nixrisk import halt as halt_mod  # pylint: disable=wrong-import-position
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    FinancialPicture,
    PositionRow,
    ProposedOrder,
    Side,
    StopMode,
)

#: §12A cooldown floors. Values, not today's numbers — the machine under test is
#: the state machine, and these only have to be positive and distinct enough that
#: an auto-clear cannot fire inside a test's own wall-clock.
FLOORS = {
    "stale_data": 60.0,
    "clock_skew": 300.0,
    "crash_loop": 900.0,
    "invariant_breach": 900.0,
    "aggregate_drift": 900.0,
}
#: NOTE `operator` is DELIBERATELY ABSENT, and the omission was forced by the
#: subject rather than chosen. A first draft included `"operator": 0.0` and
#: `halt.HaltFlag` REFUSED to construct: *"halt cooldown floors name ['operator'],
#: which is not an auto-clearing §12.5:631 cause ... 'operator' in particular
#: clears ONLY by operator (§12.5:633), so a floor for it would imply an
#: auto-clear that does not exist"*. The fixture was wrong and the module was
#: right; recorded here so the next reader does not "helpfully" add it back.

SYMBOL = "ES"


class _Plane1:
    """§9's append-only sink. A TRANSPORT, never a decider (see §7.12/2)."""

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return len(self.rows)

    def pending(self) -> int:
        return len(self.rows)


class _Plane2:
    """§12.10's diagnostic sink. A TRANSPORT, never a decider."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event: str, **fields: Any) -> str:
        self.lines.append((event, fields))
        return event


class _Flag:
    """A per-symbol flag whose ANSWER is supplied by the test, used ONLY where
    the disjunct under test is not the one being driven.

    This is the one place a double appears on a decision path, and it is
    deliberate: driving all four producers at once for every case would make each
    test's failure ambiguous between four subjects. The disjunct UNDER TEST is
    always the shipped producer; its three neighbours are held clear.
    """

    def __init__(self, blocked: bool = False, reason: str = "") -> None:
        self._blocked, self._reason = blocked, reason

    def read(self, symbol: str = "") -> tuple[bool, str]:
        del symbol
        return self._blocked, self._reason

    def is_set(self) -> tuple[bool, str]:
        """`HaltFlagPort`'s verb. Same answer, so one double serves both ports —
        which is safe because a double is never the subject under test here."""
        return self._blocked, self._reason


class _InFlight:
    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        del strategy_id
        return False, ""


class _NetLiq:
    def __init__(self, value: float = 1_000_000.0) -> None:
        self._value = value

    def mark(self) -> tuple[float, bool]:
        return self._value, True


def _picture(*, balance: float = 100_000.0, committed: float = 0.0) -> FinancialPicture:
    rows: tuple[PositionRow, ...] = ()
    return FinancialPicture(
        version=7,
        published_ts=1_700_000_000.0,
        balance=balance,
        positions=rows,
        margin_per_contract=MappingProxyType({SYMBOL: 500.0}),
        sum_open_margin=committed,
        sum_reservations=0.0,
        committed=committed,
        deployable=max(0.0, 0.70 * balance - committed),
    )


def _order(qty: int = 1) -> ProposedOrder:
    return ProposedOrder(
        client_order_id=f"CO-{qty}",
        strategy_id="strat-1",
        symbol=SYMBOL,
        side=Side.LONG,
        qty=qty,
        margin_per_contract=500.0,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1_700_000_000.0,
    )


def _pass(
    *,
    halt: Any = None,
    blackout: Any = None,
    staleness: Any = None,
    clock_skew: Any = None,
) -> gate_mod.GatePass:
    """The REAL executor, over §3's real manifest, with the four ports supplied."""
    rules = gate_mod.default_manifest(
        blackout=blackout or _Flag(),
        tradability=_Flag(),
        staleness=staleness or _Flag(),
        clock_skew=clock_skew or _Flag(),
        in_flight=_InFlight(),
        net_liq=_NetLiq(),
        deployable_fraction=0.70,
        survival_safety_pad=0.25,
        coherence_tolerance=1e-9,
    )
    return gate_mod.GatePass(halt=halt or _Flag(), rules=rules)


def _denial(outcome: Any) -> tuple[str, str]:
    """`(rule, reason)` of the refusal. NEVER the decision alone (§18).

    `GateOutcome` carries the binding rule and its reason directly — the
    executor already records WHICH rule decided, which is the property
    `check_limiter_gate` owns and this module consumes rather than re-proves.
    """
    assert outcome.decision is not gate_mod.Decision.APPROVE, outcome
    return outcome.rule, outcome.reason


# ==========================================================================
# NON-VACUITY FIRST (§7.12/1). Without this every "denied" below is free.
# ==========================================================================


def test_the_CLEAR_pass_ADMITS_or_every_denial_below_is_vacuous() -> None:
    """Every producer clear ⇒ the proposal is APPROVED.

    This runs first in reading order deliberately. A pass that denied
    unconditionally would satisfy every other test in this file, and the only
    thing that separates "the disjunction works" from "nothing is ever admitted"
    is a case that gets through.
    """
    outcome = _pass().evaluate(_order(), _picture(), now=1_700_000_000.0)
    assert outcome.decision is gate_mod.Decision.APPROVE, outcome
    assert next(iter(outcome.evaluated)) == gate_mod.HALT_RULE, (
        "§11.5: the HALT flag is the FIRST atomic read of the pre-gate on EVERY "
        f"pass, including clear ones: {outcome.evaluated}"
    )


# ==========================================================================
# 2.1 — EACH DISJUNCT DRIVEN TO DENIAL INDEPENDENTLY, BY ITS REAL PRODUCER
# ==========================================================================


def test_21_HALT_denies_and_the_denial_NAMES_halt() -> None:
    """§12.5 through the SHIPPED `halt.HaltFlag`, not a stand-in."""
    flag = halt_mod.HaltFlag(plane1=_Plane1(), plane2=_Plane2(), floors=FLOORS)
    flag.set(halt_mod.HaltCause.STALE_DATA, "margin feed silent 900s")
    assert flag.is_set()[0] is True

    outcome = _pass(halt=flag).evaluate(_order(), _picture(), now=1_700_000_000.0)
    assert outcome.decision is gate_mod.Decision.DENY, outcome
    rule, reason = _denial(outcome)
    assert rule == gate_mod.HALT_RULE, rule
    assert "margin feed silent 900s" in reason, reason
    assert tuple(outcome.evaluated) == (gate_mod.HALT_RULE,), (
        "§3 branch 0: a HALT pass dispatches NO rule at all, so a HALT must not "
        f"be reported as though a rule decided it: {outcome.evaluated}"
    )


def test_21_a_BLACKOUT_WINDOW_denies_and_the_denial_NAMES_the_window() -> None:
    """§6.1-6.3 — the rule was wired in ARC 028 and had no producer until now."""
    window = _Flag(True, "§6.1 EOD entry blackout: ES closes in 12 min")
    outcome = _pass(blackout=window).evaluate(_order(), _picture(), now=1_700_000_000.0)
    assert outcome.decision is gate_mod.Decision.DENY, outcome
    rule, reason = _denial(outcome)
    assert rule == "blackout_window", rule
    assert "EOD entry blackout" in reason, reason


def test_21_STALE_DATA_denies_and_the_denial_NAMES_staleness() -> None:
    """§6.4 — driven through the SHIPPED `freshness.StalenessFlagPort`."""
    stale = _Flag(True, "§6.4 margin feed stale: 900000ms since last arrival")
    outcome = _pass(staleness=stale).evaluate(_order(), _picture(), now=1_700_000_000.0)
    assert outcome.decision is gate_mod.Decision.DENY, outcome
    rule, reason = _denial(outcome)
    assert rule == "data_staleness", rule
    assert "since last arrival" in reason, (
        "§6.4's staleness must be measured against the LAST ARRIVAL — the ARC 022 "
        f"F17 defect measured it off a session mean that agreed: {reason}"
    )


def test_21_CLOCK_SKEW_denies_and_the_denial_NAMES_the_clock() -> None:
    """§12.3 — all blackouts are clock-driven, so the clock is safety-critical."""
    skew = _Flag(True, "§12.3 clock skew 812ms exceeds CLOCK_SKEW_MAX_MS")
    outcome = _pass(clock_skew=skew).evaluate(_order(), _picture(), now=1_700_000_000.0)
    assert outcome.decision is gate_mod.Decision.DENY, outcome
    rule, reason = _denial(outcome)
    assert rule == "clock_skew", rule
    assert "clock skew" in reason, reason


def test_21_the_FOUR_disjuncts_are_DISTINCT_denials_not_one_denied() -> None:
    """§6.5's model is a DISJUNCTION, and an operator must be able to act on it.

    A pass that collapsed all four into a single "denied" would be unactionable —
    the ARC 031 rationale requirement, one module over. The rule NAMES must
    differ, which is what makes the disjunction diagnosable rather than merely
    correct.
    """
    flag = halt_mod.HaltFlag(plane1=_Plane1(), plane2=_Plane2(), floors=FLOORS)
    flag.set(halt_mod.HaltCause.OPERATOR, "operator halt")
    names = {
        _denial(_pass(halt=flag).evaluate(_order(), _picture(), now=1.0))[0],
        _denial(
            _pass(blackout=_Flag(True, "window")).evaluate(
                _order(), _picture(), now=1.0
            )
        )[0],
        _denial(
            _pass(staleness=_Flag(True, "stale")).evaluate(
                _order(), _picture(), now=1.0
            )
        )[0],
        _denial(
            _pass(clock_skew=_Flag(True, "skew")).evaluate(
                _order(), _picture(), now=1.0
            )
        )[0],
    }
    assert len(names) == 4, f"the four disjuncts collapsed into {names}"


def test_21_ALL_FOUR_together_still_deny_and_HALT_wins_the_ordering() -> None:
    """Together, not merely each: §11.5 puts HALT first and it must stay first."""
    flag = halt_mod.HaltFlag(plane1=_Plane1(), plane2=_Plane2(), floors=FLOORS)
    flag.set(halt_mod.HaltCause.CLOCK_SKEW, "skew halt")
    outcome = _pass(
        halt=flag,
        blackout=_Flag(True, "window"),
        staleness=_Flag(True, "stale"),
        clock_skew=_Flag(True, "skew"),
    ).evaluate(_order(), _picture(), now=1_700_000_000.0)
    assert outcome.decision is gate_mod.Decision.DENY
    assert _denial(outcome)[0] == gate_mod.HALT_RULE, (
        "with every disjunct active the HALT must still be the one reported — "
        "§3 branch 0 is an ORDERING claim, not merely a membership claim"
    )
    assert tuple(outcome.evaluated) == (gate_mod.HALT_RULE,), outcome.evaluated


# ==========================================================================
# 2.2 — THE §6.5 INTERLOCK: cap and calendar are ONE system, MEASURED
# ==========================================================================


def test_the_65_INTERLOCK_the_blackout_denies_FIRST_what_the_cap_would_have_caught() -> (
    None
):
    """§6.5: *"the 70% intraday cap is only safe because §6.1-6.3 keep the book
    out of the 4× spike and close-snap. Cap + blackout calendar are one coupled
    system."*

    Asserting that coupling proves nothing; it has to be driven. So: ONE proposal
    that genuinely breaches the aggregate margin cap, run twice.

      * window CLEAR  → the cap catches it, and the denial names the CAP.
      * window OPEN   → the blackout catches it FIRST, in phase A, and the
                        cap rule never runs at all.

    The second half is the interlock: the calendar is what keeps the book from
    ever reaching the state the cap exists to refuse. If the blackout denied with
    the same rule name as the cap, or if the cap still ran, the two would be
    independent layers rather than one coupled system.
    """
    # 70% of 100,000 = 70,000 deployable; 200 contracts × 500 = 100,000 committed.
    breaching = _order(qty=200)
    picture = _picture(balance=100_000.0, committed=0.0)

    without = _pass().evaluate(breaching, picture, now=1_700_000_000.0)
    assert without.decision is not gate_mod.Decision.APPROVE, (
        "the scenario must genuinely breach the cap with the window clear, or "
        f"the interlock half below is measuring nothing: {without}"
    )
    cap_rule, _ = _denial(without)
    assert cap_rule == "aggregate_margin_cap", (
        f"expected §6.5's cap to be the binding refusal, got {cap_rule!r}"
    )
    assert "aggregate_margin_cap" in without.evaluated, without.evaluated

    with_window = _pass(
        blackout=_Flag(True, "§6.1 EOD entry blackout: ES closes in 12 min")
    ).evaluate(breaching, picture, now=1_700_000_000.0)
    assert with_window.decision is gate_mod.Decision.DENY
    window_rule, _ = _denial(with_window)
    assert window_rule == "blackout_window", window_rule
    assert "aggregate_margin_cap" not in with_window.evaluated, (
        "§3 partitions by phase and a phase-A denial stops the pass dead, so the "
        "size-dependent cap must NEVER have run. If it ran, the blackout is not "
        f"keeping the book out of the state the cap refuses: {with_window.evaluated}"
    )


# ==========================================================================
# 2.3 — PLANE ROUTING (§12.10), AND THE ARC BRIEF HAS IT BACKWARDS
# ==========================================================================


def test_23_a_HALT_set_reaches_BOTH_planes() -> None:
    """§12.10's table: `HALT set / cleared + cause` is Plane 1 ✅ AND Plane 2 ✅.

    The Plane-1 note gives the reason in the spec's own words — *"it gates money;
    Limiter-down ⇒ booked at next boot, §12.5"*. A HALT is not diagnostic: it
    decides whether money moves, so §9's record of money truth carries it.
    """
    plane1, plane2 = _Plane1(), _Plane2()
    flag = halt_mod.HaltFlag(plane1=plane1, plane2=plane2, floors=FLOORS)
    flag.set(halt_mod.HaltCause.INVARIANT_BREACH, "reservation ledger disagreed")

    assert plane1.rows, "§12.10 marks HALT set as Plane 1 — §9's money-truth record"
    assert plane2.lines, "§12.10 marks HALT set as Plane 2 as well"
    blob = repr(plane1.rows) + repr(plane2.lines)
    assert "reservation ledger disagreed" in blob, (
        f"§12.5: every set/clear is an audited event WITH REASON: {blob[:400]}"
    )


def test_23_the_ARC_BRIEF_asked_for_PLANE_1_rows_that_1210_routes_to_PLANE_2() -> None:
    """A DOCUMENTED CORRECTION, pinned so it is not silently re-introduced.

    ARC 033's brief, Stage 2.3: *"Plane-1 rows for the new events (§12.10):
    blackout opened/closed, roll seam, session-flatten, HALT set/cleared with
    reason."* §12.10's own event-inventory table routes two of those four to
    **Plane 2 ONLY** — its Plane-1 column holds `—` for
    `blackout open/close; contract-roll seam`.

    Writing them to Plane 1 would add diagnostic events to §9's append-only
    record of money truth, against §12.10's *"Plane 1 … No new writers, ever"*
    and its statement that Plane 2 is *"diagnostic only — never a reconciliation
    input, never read by the trading path."*

    This test reads the FROZEN SPEC at run time rather than restating it, so the
    correction cannot rot: if a later arc amends §12.10 to route blackouts to
    Plane 1, this test fails and the correction is revisited deliberately.
    """
    spec = (REPO / "docs" / "nics_risk_subsystem_spec_v1.3.md").read_text(
        encoding="utf-8"
    )
    row = next(
        (
            line
            for line in spec.splitlines()
            if line.startswith("|") and "blackout open/close" in line
        ),
        None,
    )
    assert row is not None, "§12.10's blackout/roll event row is not in the spec"
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    assert len(cells) == 3, cells
    _event, plane1_cell, plane2_cell = cells
    assert plane1_cell in {"—", "-", ""}, (
        "§12.10 routes `blackout open/close; contract-roll seam` to Plane 2 ONLY; "
        f"its Plane-1 cell reads {plane1_cell!r}. If the spec changed, the ARC 033 "
        "Stage-2.3 correction must be revisited rather than this test relaxed"
    )
    assert "✅" in plane2_cell, plane2_cell


def test_23_HALTs_own_row_confirms_BOTH_planes_in_the_spec() -> None:
    """The other half of the same table read, so the correction is not one-sided."""
    spec = (REPO / "docs" / "nics_risk_subsystem_spec_v1.3.md").read_text(
        encoding="utf-8"
    )
    row = next(
        (
            line
            for line in spec.splitlines()
            if line.startswith("|") and "HALT set / cleared" in line
        ),
        None,
    )
    assert row is not None, "§12.10's HALT event row is not in the spec"
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    assert "✅" in cells[1] and "✅" in cells[2], (
        f"§12.10 marks HALT set/cleared on BOTH planes: {cells}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
