"""ARC 028 / A — the Limiter pass's own behaviour, rule by rule.

`test_check_limiter_gate.py` is the CAN-FAIL for the standing gate: it plants
defects in a copy of `scripts/nixrisk/gate.py` and proves the instrument
discriminates. This module is the other half — the module's own arithmetic,
its fail-closed paths, and the boot refusals — driven directly.

The split is stated so the boundary survives the next author (doctrine C.9):
anything about DISPATCH ORDER, the HALT position or the hot-path shape belongs to
the check and is measured there; anything about what an individual rule DECIDES
belongs here.

Every §-citation is to `docs/nics_risk_subsystem_spec_v1.3.md`.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=too-few-public-methods
# Every helper class here is a PORT DOUBLE with the port's own single verb;
# adding a second method to satisfy a threshold would make the double a worse
# stand-in for the thing it doubles.
# Test names SHOUT the property.

from __future__ import annotations

import dataclasses

import pytest  # pylint: disable=import-error
from nixrisk.gate import (
    HALT_RULE,
    PASS_COMPLETE,
    AggregateMarginCapRule,
    DeployableCeilingRule,
    GatePass,
    KnobError,
    PictureCoherenceRule,
    SurvivalHeadroomRule,
    SymbolFlagRule,
    UndispatchableManifest,
    default_manifest,
)
from nixrisk.seam import (
    Decision,
    FinancialPicture,
    Phase,
    PositionRow,
    PositionState,
    ProposedOrder,
    Reservation,
    ReservationState,
    RulePort,
    RuleVerdict,
    Side,
    StopMode,
    TerminalPath,
)

FRACTION = 0.70
SAFETY_PAD = 0.10
TOLERANCE = 1e-6


class Flag:
    """Every §11.1-shaped port in one object: symbol, global, in-flight."""

    def __init__(self, blocked: bool = False, reason: str = "") -> None:
        self.value = (blocked, reason)

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        """`(blocked, reason)`."""
        del symbol
        return self.value

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`."""
        return self.value

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)`."""
        del strategy_id
        return self.value


class NetLiq:
    """§6.5's mark."""

    def __init__(self, value: float = 10_000_000.0, fresh: bool = True) -> None:
        self.value = value
        self.fresh = fresh

    def mark(self) -> tuple[float, bool]:
        """`(net_liq, fresh)`."""
        return self.value, self.fresh


class Ledger:
    """A `ReservationLedgerPort` recording the quantity actually reserved.

    All four verbs are implemented rather than only `take`. A double that
    satisfies half a port is a double that stops satisfying it the day the
    subject calls the other half, and the type checker would be the only thing
    that noticed -- if the parameter were widened to silence it, not even that.
    """

    def __init__(self, explode: bool = False) -> None:
        self.taken: list[int] = []
        self.explode = explode
        self.live: dict[str, Reservation] = {}

    def take(self, order: ProposedOrder, now: float) -> Reservation:
        """Record and hand back a reservation, or refuse."""
        if self.explode:
            raise RuntimeError("ledger is full")
        self.taken.append(order.qty)
        reservation = Reservation(
            reservation_id=f"res-{len(self.taken)}",
            client_order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            margin=order.proposed_margin,
            state=ReservationState.TAKEN,
            taken_ts=now,
        )
        self.live[reservation.reservation_id] = reservation
        return reservation

    def release(
        self, reservation_id: str, via: TerminalPath, now: float
    ) -> Reservation:
        """Release exactly once. The gate never calls this; the port declares it."""
        held = self.live.pop(reservation_id)
        return dataclasses.replace(
            held, state=ReservationState.RELEASED, released_ts=now, released_via=via
        )

    def outstanding(self) -> tuple[Reservation, ...]:
        """Every reservation currently TAKEN."""
        return tuple(self.live.values())

    def total_reserved(self) -> float:
        """§11.3's running aggregate over the TAKEN set."""
        return sum(row.margin for row in self.live.values())


def order(qty: int = 4, margin: float = 1000.0) -> ProposedOrder:
    """A well-formed proposal."""
    return ProposedOrder(
        client_order_id="c1",
        strategy_id="s1",
        symbol="ES",
        side=Side.LONG,
        qty=qty,
        margin_per_contract=margin,
        stop_ticks=40,
        stop_mode=StopMode.FIXED,
        signal_ts=1.0,
    )


def picture(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    balance: float = 1_000_000.0,
    open_margin: float = 0.0,
    reservations: float = 0.0,
    committed: float | None = None,
    deployable: float = 500_000.0,
    positions: tuple[PositionRow, ...] = (),
) -> FinancialPicture:
    """One §3 snapshot. `committed` defaults to its own §3 definition."""
    return FinancialPicture(
        version=1,
        published_ts=1.0,
        balance=balance,
        positions=positions,
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=open_margin,
        sum_reservations=reservations,
        committed=open_margin + reservations if committed is None else committed,
        deployable=deployable,
    )


def manifest() -> tuple[RulePort, ...]:
    """The shipped §3 rule set, every port clear and every knob in range."""
    clear = Flag()
    return default_manifest(
        blackout=clear,
        tradability=clear,
        staleness=clear,
        clock_skew=clear,
        in_flight=clear,
        net_liq=NetLiq(),
        deployable_fraction=FRACTION,
        survival_safety_pad=SAFETY_PAD,
        coherence_tolerance=TOLERANCE,
    )


# --------------------------------------------------------------------------
# The happy path, and the record it leaves
# --------------------------------------------------------------------------


def test_a_CLEAN_PASS_APPROVES_and_evaluates_EVERY_rule_plus_branch_zero() -> None:
    """The floor: nothing is skipped when nothing objects."""
    rules = manifest()
    ledger = Ledger()

    outcome = GatePass(Flag(), list(rules), ledger).evaluate(order(), picture(), 1.0)

    assert outcome.decision is Decision.APPROVE, outcome
    assert outcome.rule == PASS_COMPLETE
    assert outcome.evaluated[0] == HALT_RULE
    assert list(outcome.evaluated[1:]) == [rule.name for rule in rules]
    assert ledger.taken == [4], "§3 takes the reservation at approval"
    assert outcome.reservation_id == "res-1"


def test_the_MANIFEST_property_reports_DISPATCH_order_not_construction_order() -> None:
    """Phase A names first, whatever order the rules were handed in."""
    rules = list(manifest())
    passer = GatePass(Flag(), list(reversed(rules)))

    names = passer.manifest
    phases = {rule.name: rule.phase for rule in rules}

    assert [phases[name] for name in names] == sorted(
        (phases[name] for name in names),
        key=lambda p: 0 if p is Phase.SIZE_INDEPENDENT else 1,
    ), names


# --------------------------------------------------------------------------
# §3 branch 0 and the phase-A rules
# --------------------------------------------------------------------------


def test_a_SET_HALT_DENIES_before_any_rule_is_dispatched() -> None:
    """§11.5: the first atomic read. §3: branch 0."""
    outcome = GatePass(Flag(True, "operator HALT"), list(manifest())).evaluate(
        order(), picture(), 1.0
    )

    assert outcome.decision is Decision.DENY
    assert outcome.rule == HALT_RULE
    assert outcome.reason == "operator HALT"
    assert outcome.evaluated == (HALT_RULE,)


def test_a_BLOCKED_CACHE_WITH_NO_REASON_still_denies_and_NAMES_the_cache() -> None:
    """§11.1's contract is `(bool, reason)`; a broken cache may not go quiet."""
    verdict = SymbolFlagRule("blackout_window", Flag(True, ""), "§6.1").evaluate(
        order(), picture()
    )

    assert verdict.decision is Decision.DENY
    assert verdict.rule == "blackout_window"
    assert "no reason" in verdict.reason
    assert "§6.1" in verdict.reason


def test_a_PHASE_A_DENIAL_names_the_rule_and_reports_phase_A() -> None:
    """§3: 'deny (rule named, fail-fast)'."""
    clear = Flag()
    rules = default_manifest(
        blackout=clear,
        tradability=Flag(True, "ES outside session"),
        staleness=clear,
        clock_skew=clear,
        in_flight=clear,
        net_liq=NetLiq(),
        deployable_fraction=FRACTION,
        survival_safety_pad=SAFETY_PAD,
        coherence_tolerance=TOLERANCE,
    )
    ledger = Ledger()

    outcome = GatePass(Flag(), list(rules), ledger).evaluate(order(), picture(), 1.0)

    assert outcome.decision is Decision.DENY
    assert outcome.rule == "tradability"
    assert outcome.reason == "ES outside session"
    assert outcome.phase is Phase.SIZE_INDEPENDENT
    assert "picture_coherence" not in outcome.evaluated, outcome.evaluated
    assert not ledger.taken, "a denied proposal reserves nothing"


# --------------------------------------------------------------------------
# §6.5 — the size-dependent arithmetic
# --------------------------------------------------------------------------


def test_the_AGGREGATE_CAP_is_STRICT_at_the_boundary() -> None:
    """§6.5: `committed + proposed < 70% × balance`. Equality is NOT admitted."""
    rule = AggregateMarginCapRule("aggregate_margin_cap", FRACTION)
    exact = picture(balance=10_000.0, open_margin=6_000.0)

    verdict = rule.evaluate(order(qty=1, margin=1_000.0), exact)

    assert verdict.decision is not Decision.APPROVE, (
        "6000 + 1000 == 0.70 x 10000 exactly, and §6.5's cap is strict"
    )


def test_the_AGGREGATE_CAP_SIZES_DOWN_to_what_fits_rather_than_denying() -> None:
    """§5: size-down is distinct from deny; §3 gives the Allocator's own formula."""
    rule = AggregateMarginCapRule("aggregate_margin_cap", FRACTION)
    tight = picture(balance=10_000.0, open_margin=3_500.0)

    verdict = rule.evaluate(order(qty=6, margin=1_000.0), tight)

    assert verdict.decision is Decision.SIZE_DOWN, verdict
    assert verdict.sized_qty == 3, verdict
    assert tight.committed + verdict.sized_qty * 1_000.0 < FRACTION * 10_000.0


def test_a_ZERO_FIT_is_a_DENY_and_never_a_SIZE_DOWN_to_zero() -> None:
    """A clamp to nothing is a refusal, and §3 spells refusals `deny`."""
    rule = AggregateMarginCapRule("aggregate_margin_cap", FRACTION)
    full = picture(balance=10_000.0, open_margin=7_000.0)

    verdict = rule.evaluate(order(qty=6, margin=1_000.0), full)

    assert verdict.decision is Decision.DENY, verdict
    assert verdict.sized_qty is None


def test_the_SMALLEST_SIZE_DOWN_BINDS_and_the_RESERVATION_is_for_THAT_size() -> None:
    """Two clamps in one pass: the tighter wins and the ledger sees the final qty."""
    clear = Flag()
    rules = default_manifest(
        blackout=clear,
        tradability=clear,
        staleness=clear,
        clock_skew=clear,
        in_flight=clear,
        net_liq=NetLiq(),
        deployable_fraction=FRACTION,
        survival_safety_pad=SAFETY_PAD,
        coherence_tolerance=TOLERANCE,
    )
    ledger = Ledger()
    # cap allows 3 (0.70 x 10000 - 3500 = 3500); deployable allows 2.
    snapshot = picture(balance=10_000.0, open_margin=3_500.0, deployable=2_000.0)

    outcome = GatePass(Flag(), list(rules), ledger).evaluate(
        order(qty=6, margin=1_000.0), snapshot, 9.0
    )

    assert outcome.decision is Decision.SIZE_DOWN, outcome
    assert outcome.sized_qty == 2, outcome
    assert outcome.rule == "deployable_ceiling", outcome
    assert ledger.taken == [2], "reserving the PROPOSED size would over-commit"


def test_a_STALE_NET_LIQ_MARK_DENIES_rather_than_trusting_the_last_number() -> None:
    """§17: a safety property proven while its subject is unavailable is not proven."""
    rule = SurvivalHeadroomRule("survival_headroom", NetLiq(fresh=False), SAFETY_PAD)

    verdict = rule.evaluate(order(), picture())

    assert verdict.decision is Decision.DENY
    assert "STALE" in verdict.reason
    assert "§17" in verdict.reason


def test_the_SURVIVAL_FLOOR_is_PROJECTED_and_not_taken_on_TODAYS_open_margin() -> None:
    """§3: 'projected net-liq impact leaves floor intact'."""
    rule = SurvivalHeadroomRule("survival_headroom", NetLiq(10_900.0), SAFETY_PAD)
    snapshot = picture(open_margin=6_000.0)

    on_current = rule.evaluate(order(qty=0, margin=1_000.0), snapshot)
    projected = rule.evaluate(order(qty=4, margin=1_000.0), snapshot)

    assert on_current.decision is Decision.APPROVE, "6000 x 1.1 = 6600 <= 10900"
    assert projected.decision is Decision.DENY, "10000 x 1.1 = 11000 > 10900"
    assert "survival floor" in projected.reason


def test_an_INCOHERENT_PICTURE_DENIES_and_NAMES_ALL_THREE_FIGURES() -> None:
    """§3 defines committed; §11.3 keeps all three independently, so they drift."""
    rule = PictureCoherenceRule("picture_coherence", TOLERANCE)
    torn = picture(open_margin=1_000.0, reservations=500.0, committed=1_200.0)

    verdict = rule.evaluate(order(), torn)

    assert verdict.decision is Decision.DENY
    for figure in ("1200.0", "1000.0", "500.0"):
        assert figure in verdict.reason, verdict.reason


def test_the_DEPLOYABLE_CEILING_reads_the_PUBLISHED_value_and_never_re_derives_it() -> (
    None
):
    """§11.4 precomputes it on account-state change; this module is not a second author."""
    rule = DeployableCeilingRule("deployable_ceiling")
    snapshot = picture(balance=1_000_000.0, deployable=1_500.0)

    verdict = rule.evaluate(order(qty=4, margin=1_000.0), snapshot)

    assert verdict.decision is Decision.SIZE_DOWN
    assert verdict.sized_qty == 1, "1500 published deployable, 1000 per contract"


def test_the_HOT_PATH_NEVER_TOUCHES_THE_POSITION_TABLE() -> None:
    """§11.3: every gate check reads a running aggregate, never the rows."""
    rows = tuple(
        PositionRow(
            trade_id=f"t{index}",
            symbol="ES",
            strategy_id="s1",
            size=1,
            margin=1_000.0,
            state=PositionState.OPEN,
        )
        for index in range(64)
    )
    # sum_open_margin says 0 while the rows say 64000. A rule that read the rows
    # would deny or size down; a rule that reads the aggregate approves.
    outcome = GatePass(Flag(), list(manifest())).evaluate(
        order(), picture(positions=rows), 1.0
    )

    assert outcome.decision is Decision.APPROVE, outcome


# --------------------------------------------------------------------------
# Fail-closed: a rule that misbehaves may never produce an approval
# --------------------------------------------------------------------------


class _Rogue:
    """A rule with a configurable defect. Every one of these is fail-closed."""

    def __init__(self, name: str, phase: Phase, verdict: RuleVerdict | None) -> None:
        self._name = name
        self._phase = phase
        self._verdict = verdict

    @property
    def name(self) -> str:
        """Rule identity."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Declared phase."""
        return self._phase

    def evaluate(
        self, order_: ProposedOrder, picture_: FinancialPicture
    ) -> RuleVerdict:
        """Return the configured verdict, or raise if there is none."""
        del order_, picture_
        if self._verdict is None:
            raise ZeroDivisionError("rule blew up")
        return self._verdict


def _with(rogue: _Rogue) -> GatePass:
    other = (
        Phase.SIZE_DEPENDENT
        if rogue.phase is Phase.SIZE_INDEPENDENT
        else Phase.SIZE_INDEPENDENT
    )
    filler = _Rogue("filler", other, RuleVerdict("filler", Decision.APPROVE, ""))
    return GatePass(Flag(), [rogue, filler])


@pytest.mark.parametrize(
    ("verdict", "fragment"),
    [
        (RuleVerdict("someone_else", Decision.DENY, "no"), "misattributes itself"),
        (RuleVerdict("rogue", Decision.DENY, "   "), "empty reason"),
        (RuleVerdict("rogue", Decision.SIZE_DOWN, "x", 9), "a clamp must reduce"),
        (RuleVerdict("rogue", Decision.SIZE_DOWN, "x", None), "names no quantity"),
        (None, "rule raised ZeroDivisionError"),
    ],
)
def test_a_MALFORMED_VERDICT_becomes_a_DENY_NAMING_THE_RULE(
    verdict: RuleVerdict | None, fragment: str
) -> None:
    """Directive 4: fail closed and loud. None of these may reach an approval."""
    outcome = _with(_Rogue("rogue", Phase.SIZE_DEPENDENT, verdict)).evaluate(
        order(qty=4), picture(), 1.0
    )

    assert outcome.decision is Decision.DENY, outcome
    assert outcome.rule == "rogue", outcome
    assert fragment in outcome.reason, outcome.reason


def test_a_SIZE_INDEPENDENT_rule_that_SIZES_DOWN_is_a_CONTRACT_VIOLATION() -> None:
    """§3 puts every quantity-dependent rule in phase B. A phase-A clamp is a defect."""
    rogue = _Rogue(
        "rogue",
        Phase.SIZE_INDEPENDENT,
        RuleVerdict("rogue", Decision.SIZE_DOWN, "x", 1),
    )

    outcome = _with(rogue).evaluate(order(qty=4), picture(), 1.0)

    assert outcome.decision is Decision.DENY
    assert "size-INDEPENDENT rule returned SIZE_DOWN" in outcome.reason


def test_a_LEDGER_THAT_CANNOT_TAKE_turns_an_APPROVAL_into_a_DENY() -> None:
    """An approval whose margin is unreserved is invisible to the next pass."""
    outcome = GatePass(Flag(), list(manifest()), Ledger(explode=True)).evaluate(
        order(), picture(), 1.0
    )

    assert outcome.decision is Decision.DENY
    assert outcome.rule == "reservation_ledger"
    assert "over-commitment" in outcome.reason


# --------------------------------------------------------------------------
# §12A boot validation — refusals at construction, never in a pass
# --------------------------------------------------------------------------


def test_an_EMPTY_MANIFEST_is_REFUSED_at_boot() -> None:
    """§5's default posture makes a gate with no rules approve everything."""
    with pytest.raises(UndispatchableManifest, match="empty manifest"):
        GatePass(Flag(), [])


def test_a_MANIFEST_MISSING_A_PHASE_is_REFUSED_at_boot() -> None:
    """A pass whose phase B is empty checks committed margin never."""
    only_a = _Rogue("a", Phase.SIZE_INDEPENDENT, RuleVerdict("a", Decision.APPROVE, ""))

    with pytest.raises(UndispatchableManifest, match="SIZE_DEPENDENT"):
        GatePass(Flag(), [only_a])


def test_a_RULE_WITH_AN_UNKNOWN_PHASE_is_REFUSED_rather_than_DROPPED() -> None:
    """The partition would silently skip it, which looks exactly like an approval."""
    bad = _Rogue("x", "post-size", RuleVerdict("x", Decision.APPROVE, ""))  # type: ignore[arg-type]
    good_a = _Rogue("a", Phase.SIZE_INDEPENDENT, RuleVerdict("a", Decision.APPROVE, ""))
    good_b = _Rogue("b", Phase.SIZE_DEPENDENT, RuleVerdict("b", Decision.APPROVE, ""))

    with pytest.raises(UndispatchableManifest, match="not a Phase member"):
        GatePass(Flag(), [good_a, good_b, bad])


def test_DUPLICATE_RULE_NAMES_are_REFUSED_because_a_denial_must_be_attributable() -> (
    None
):
    """§3 and §5 both require the blocking rule NAMED."""
    a_one = _Rogue("a", Phase.SIZE_INDEPENDENT, RuleVerdict("a", Decision.APPROVE, ""))
    a_two = _Rogue("a", Phase.SIZE_INDEPENDENT, RuleVerdict("a", Decision.APPROVE, ""))
    b_one = _Rogue("b", Phase.SIZE_DEPENDENT, RuleVerdict("b", Decision.APPROVE, ""))

    with pytest.raises(UndispatchableManifest, match="repeats the name"):
        GatePass(Flag(), [a_one, a_two, b_one])


def test_a_NON_RULE_IN_THE_MANIFEST_is_REFUSED_at_boot() -> None:
    """`RulePort` conformance is checked, not assumed."""
    good = _Rogue("a", Phase.SIZE_INDEPENDENT, RuleVerdict("a", Decision.APPROVE, ""))

    with pytest.raises(UndispatchableManifest, match="does not satisfy RulePort"):
        GatePass(Flag(), [good, "not a rule"])  # type: ignore[list-item]


def test_a_HALT_PORT_THAT_CANNOT_BE_READ_is_REFUSED_at_boot() -> None:
    """A pre-gate that cannot see HALT approves during a HALT."""
    good_a = _Rogue("a", Phase.SIZE_INDEPENDENT, RuleVerdict("a", Decision.APPROVE, ""))
    good_b = _Rogue("b", Phase.SIZE_DEPENDENT, RuleVerdict("b", Decision.APPROVE, ""))

    with pytest.raises(UndispatchableManifest, match="declares no is_set"):
        GatePass(object(), [good_a, good_b])  # type: ignore[arg-type]


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.5])
def test_an_OUT_OF_RANGE_DEPLOYABLE_FRACTION_is_REFUSED(fraction: float) -> None:
    """§12A owns the number; this module refuses one it cannot trade under."""
    with pytest.raises(KnobError, match="deployable fraction"):
        AggregateMarginCapRule("aggregate_margin_cap", fraction)


def test_a_NEGATIVE_SAFETY_PAD_is_REFUSED_because_it_moves_the_floor_DOWN() -> None:
    """§6.5's pad exists to stay ABOVE the broker's own liquidation trigger."""
    with pytest.raises(KnobError, match="safety pad"):
        SurvivalHeadroomRule("survival_headroom", NetLiq(), -0.01)


def test_a_NEGATIVE_COHERENCE_TOLERANCE_is_REFUSED() -> None:
    """A negative tolerance would redden every snapshot, including correct ones."""
    with pytest.raises(KnobError, match="tolerance"):
        PictureCoherenceRule("picture_coherence", -1.0)


def test_THERE_IS_NO_DEFAULT_TUNABLE_anywhere_in_the_manifest_factory() -> None:
    """§12A is the semantic authority; a default here would be a second one."""
    with pytest.raises(TypeError):
        default_manifest(  # type: ignore[call-arg]  # pylint: disable=missing-kwoa
            blackout=Flag(),
            tradability=Flag(),
            staleness=Flag(),
            clock_skew=Flag(),
            in_flight=Flag(),
            net_liq=NetLiq(),
        )
