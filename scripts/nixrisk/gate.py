"""The Limiter's ONE authoritative pass over the rule manifest (§3, §5, §11).

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 028 / sub-agent A. Built against `nixrisk.seam`, which is FROZEN: this module
implements `RulePort` and produces `GateOutcome`, and changes neither.

------------------------------------------------------------------------------
THE INVARIANT THIS MODULE EXISTS TO HOLD — and why source order cannot hold it
------------------------------------------------------------------------------
§3 locks the order: **all size-INDEPENDENT rules evaluate before any
size-DEPENDENT rule, in one pass.** A gate that satisfies that by listing the
rules in the right order in a file proves nothing about what executes, and a
Phase-B rule that runs after a Phase-A denial produces *byte-identical output* to
a correct pass on every input where the Phase-A denial stands. It is a
correctness defect no output comparison can see.

So the ordering here is **not** a property of the manifest's source order. The
executor PARTITIONS the manifest by each rule's own `phase` declaration at boot
(§5: rules are "loaded once, bound at boot") and dispatches Phase A to
exhaustion before Phase B is touched. Hand this class a manifest in reverse
phase order and the execution order is unchanged — which is the only version of
this invariant that can be measured. `GateOutcome.evaluated` records the names
**in the order they actually ran**, appended by this executor at the moment it
dispatches each rule, and `checks/check_limiter_gate.py` drives real rule objects
that record their own invocation on an independent log and compares the two.

A rule declaring a `phase` that is neither member would be silently dropped by a
partition and never evaluated — a rule that is in the manifest, is never run, and
whose absence looks exactly like an approval. That is rejected at boot, loudly,
rather than discovered as a quiet green.

------------------------------------------------------------------------------
BRANCH 0 — the HALT flag is read BEFORE the manifest, not first IN it
------------------------------------------------------------------------------
§3 calls the global HALT flag "branch 0" and §11.5 calls it "first atomic read in
pre-gate". Pre-gate is not the manifest, so HALT is read by this executor before
any rule object is dispatched, and it is not a `RulePort` — a manifest that could
omit it, reorder it, or place it behind a blackout rule would make §11.5 an
authoring convention. `evaluated[0]` is `HALT_RULE` on **every** pass, including
the passes where HALT is clear, which is what makes the property checkable from
any outcome rather than only from the denial case.

------------------------------------------------------------------------------
HOT-PATH DISCIPLINE (§11) — what is arithmetic here and what is not
------------------------------------------------------------------------------
§11 fixes the entry pathway as "cache reads + arithmetic only". Concretely, in
this module:

* No rule iterates `FinancialPicture.positions`. Σ open margin, Σ reservations,
  `committed` and `deployable` are §11.3/§11.4 running aggregates that arrive
  precomputed on the snapshot, and the size-dependent rules read those fields.
  This is the falsifiable half of the O(1) claim: `check_limiter_gate.py` counts
  position-table touches across four table sizes and requires the count to be
  zero and constant. A rule that re-derived `committed` by summing rows would
  pass every behavioural test in this arc and fail that one.
* Phase-A rules are `(bool, reason)` cache reads — §11.1's tradability-cache
  shape, generalised. The window arithmetic, the calendar and the staleness
  stamps live on pollers, which is §11's whole construction, and **populating
  those caches is NOT in this arc.**
* The phase partition, the boot validation and the duplicate-name check happen
  once, in `__init__`. Nothing derived from the manifest is computed per pass.

------------------------------------------------------------------------------
TUNABLES ARE ARGUMENTS, NOT CONSTANTS — §12A
------------------------------------------------------------------------------
`CLAUDE.md`: §12A is the *semantic* authority for tunables and per-module JSON is
the *physical* layout. A `0.70` default written here would be a second authority
that silently wins whenever a caller forgets the config, so the deployable
fraction, the safety pad and the coherence tolerance are **required** constructor
arguments with no defaults. They are range-validated at construction (§12A
cross-knob boot validation, restart-only lifecycle); an out-of-range knob is a
refusal to construct, not a pass that trades on a bad number.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO — stated, so no green here implies it
------------------------------------------------------------------------------
Stop conversion and trailing maintenance (§4), protective-exit wiring to
broker-order, session-close flatten (§6.1b), full HALT semantics and auto-clear
(§12.5), cold-start reconciliation, the Sentinel (§12.1), Scoring (§6.6), the
Allocator, the §5 manifest FILE loader, and populating any of the caches the
Phase-A rules read. **A Limiter that gates but cannot exit is not a safety spine
yet.** This module gates. It cannot exit.

Two findings about the spec/seam boundary were recorded rather than papered over
and are carried as CHECK-DEBT rows; see `SurvivalHeadroomRule` and
`DeployableCeilingRule`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from nixrisk.seam import (
    Decision,
    FinancialPicture,
    GateOutcome,
    Phase,
    ProposedOrder,
    ReservationLedgerPort,
    RulePort,
    RuleVerdict,
)

#: The name branch 0 denies under. Not a `RulePort` and deliberately not
#: manifest-supplied — see the module docstring.
HALT_RULE = "global_halt"

#: The `rule` an APPROVE carries. §5's default posture is "accept unless a rule
#: blocks", so an approval is the absence of an objection and has no author. A
#: sentinel naming *the whole manifest ran* is honest where naming the last rule
#: evaluated would read as an attribution it is not.
#:
#: `# nosec B105` — bandit's hardcoded-password heuristic keys on the substring
#: `PASS` in the NAME, not on the value. Renaming the constant to satisfy a
#: scanner would rename the field every approval carries; the same one-line,
#: named suppression `nixverify.contract.Status.PASS` already uses.
PASS_COMPLETE = "manifest_exhausted"  # nosec B105


# R0903 (too-few-public-methods) disabled at module scope. Every class below is
# either a single-verb `Protocol` -- a DECLARATION with exactly the surface §11
# gives it, where a second method would be a port doing two jobs -- or a frozen
# value type. The threshold is about behavioural classes that should have been
# functions; a port declaring one O(1) read is the shape the spec asks for.
# pylint: disable=too-few-public-methods
# pylint: disable=too-many-lines
# ARC 038 / sub-agent E. The module crossed the 1000-line default when FE7/FE8/
# FE9's guards landed, and the overflow is DOCSTRING, not code: the three guards
# are eleven lines of `if`, and the measured numbers beside them (which drive
# produced which APPROVE, against which control) are the part a future arc cannot
# re-derive from the code. Same rationale, in the same words, as `halt.py:173`,
# `recovery.py:134`, `supervision.py:162` and `drift_audit.py:1`. Splitting the
# file to satisfy a line count would put §3's rule set in one module and the
# executor that partitions it in another.

# ---------------------------------------------------------------------------
# The O(1) read ports the Phase-A rules stand on (§11.1)
# ---------------------------------------------------------------------------
#
# Every one is `(blocked, reason)` — §11.1's `tradable[symbol]=(bool,reason)`
# generalised. The reason travels WITH the flag rather than being reconstructed
# by the rule, because §3 requires a denial to be actionable and only the poller
# that set the flag knows which window, which stamp, or which skew caused it.


@runtime_checkable
class HaltFlagPort(Protocol):
    """§11.5's global HALT flag. One atomic read, no arguments, no I/O."""

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`. The first read of the pre-gate on every pass."""


@runtime_checkable
class SymbolFlagPort(Protocol):
    """A per-symbol §11.1 cache: blackout windows, tradability, staleness."""

    def read(self, symbol: str) -> tuple[bool, str]:
        """`(blocked, reason)` for one symbol. O(1) — a dict lookup, never a scan."""


@runtime_checkable
class GlobalFlagPort(Protocol):
    """A process-wide flag with no symbol dimension — §12.3's clock skew."""

    def read(self) -> tuple[bool, str]:
        """`(blocked, reason)`."""


@runtime_checkable
class InFlightPort(Protocol):
    """§3's one-in-flight-per-strategy lock."""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)` for one strategy."""


@runtime_checkable
class NetLiqMarkPort(Protocol):
    """§6.5's net-liq mark, maintained per tick off the price cache.

    `fresh` is not decoration. §6.5 marks net-liq incrementally per tick, so a
    mark whose feed stopped is a stale number that still reads as a comfortable
    figure. `nix_check_contract.md` §17 — a safety property proven while its
    subject is unavailable is not proven — applies to a rule exactly as it does
    to a gate, and `SurvivalHeadroomRule` denies rather than trusting it.
    """

    def mark(self) -> tuple[float, bool]:
        """`(net_liq, fresh)`."""


class UndispatchableManifest(RuntimeError):
    """A manifest that cannot be dispatched safely. Raised at boot, never in a pass.

    Every condition it carries is one under which the pass would run and produce
    a plausible verdict while some rule never executed. Directive 4: fail closed
    and loud, at the moment the defect exists, not at the moment it costs money.

    ------------------------------------------------------------------------
    WHY THE ODD NAME — a MEASURED collision, not a stylistic choice
    ------------------------------------------------------------------------
    The obvious name is the `Manifest` + `Error` compound, and it was the first
    one written. It made `check_name_coherence` RED across eighteen sites, and
    that gate is right: ARC 026 (B1) banned that exact spelling because it named
    the check-runner's EXECUTION PLAN, an artifact whose one name is `registry`.
    (The banned spelling is not written out anywhere in this module, including
    here — the ban is a substring match and only the gate's own file and its
    control are exempt from it.)

    The gate's own docstring states the premise the ban rests on — each banned
    spelling "names the execution plan and nothing else" — and this module is the
    first code in the tree to want the identifier for the OTHER thing: §5's rule
    manifest, which the frozen spec names in its own section title. The premise
    is now false for one entry in that list.

    **The repair is here and not there.** Adding `scripts/nixrisk/` to that gate's
    exemptions would blind it to a whole package to make one red go green, which
    is doctrine B.4's named wrong move; narrowing the ban would weaken a live
    instrument for a naming convenience. Renaming one exception is minimal, local
    and reversible (directive 7), and the word *manifest* still appears freely in
    this module's prose and messages — the ban is over identifier spellings, not
    over English. The collision itself is recorded as CHECK-DEBT so a future arc
    can decide whether that ban list wants a domain qualifier, rather than
    rediscovering it.
    """


class KnobError(ValueError):
    """A §12A tunable outside its admissible range. Raised at construction."""


# ---------------------------------------------------------------------------
# PHASE A — size-INDEPENDENT rules (§3)
# ---------------------------------------------------------------------------


def _blocked(rule: str, reason: str, citation: str) -> RuleVerdict:
    """A denial that always carries a reason, even when the cache supplied none.

    §11.1's contract is `(bool, reason)`. A cache that returns `True` with an
    empty string has broken it, and the tempting handling — pass the empty reason
    through — produces exactly the generic denial §3 forbids: the operator is
    told the trade was refused and not what refused it.
    """
    detail = reason.strip() or (
        f"{rule}: the cache reported BLOCKED with no reason, which breaks §11.1's "
        f"(bool, reason) contract — denying on the flag and naming the cache "
        f"({citation})"
    )
    return RuleVerdict(rule=rule, decision=Decision.DENY, reason=detail)


def _clear(rule: str) -> RuleVerdict:
    """A rule that does not object. §5: accept unless a rule blocks."""
    return RuleVerdict(rule=rule, decision=Decision.APPROVE, reason="")


class SymbolFlagRule:
    """One §3 Phase-A bullet backed by a per-symbol §11.1 cache.

    Parameterised rather than three near-identical classes because §6.5's unified
    model is one disjunction — `HALT ∨ now ∈ any window ∨ margin elevated ∨ data
    stale ∨ clock skewed` — and says outright that **"new blackout types are data
    (a window), not code."** A class per window type would be the code the spec
    says not to write; the DATA is the cache and the identity is the name.
    """

    def __init__(self, name: str, port: SymbolFlagPort, citation: str) -> None:
        self._name = name
        self._port = port
        self._citation = citation

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-independent: the answer does not depend on `order.qty`."""
        return Phase.SIZE_INDEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """One dict lookup keyed by symbol. `picture` is deliberately unread."""
        del picture  # size-independent by construction, not by discipline
        blocked, reason = self._port.read(order.symbol)
        if blocked:
            return _blocked(self._name, reason, self._citation)
        return _clear(self._name)


class GlobalFlagRule:
    """A §3 Phase-A bullet with no symbol dimension — §12.3's clock-skew halt."""

    def __init__(self, name: str, port: GlobalFlagPort, citation: str) -> None:
        self._name = name
        self._port = port
        self._citation = citation

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-independent."""
        return Phase.SIZE_INDEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """One atomic read. Neither argument is consulted."""
        del order, picture
        blocked, reason = self._port.read()
        if blocked:
            return _blocked(self._name, reason, self._citation)
        return _clear(self._name)


class InFlightLockRule:
    """§3's one-in-flight-per-strategy lock, keyed by `strategy_id`.

    Keyed by strategy and not by symbol on purpose: `CLAUDE.md` fixes the
    operating scope at one strategy per instrument, so the two keys coincide
    today — and the spec says *per-strategy*, so the day they stop coinciding the
    rule is already right rather than quietly wrong.
    """

    def __init__(self, name: str, port: InFlightPort) -> None:
        self._name = name
        self._port = port

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-independent."""
        return Phase.SIZE_INDEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """One lookup keyed by strategy."""
        del picture
        locked, reason = self._port.in_flight(order.strategy_id)
        if locked:
            return _blocked(self._name, reason, "§3 one-in-flight-per-strategy")
        return _clear(self._name)


# ---------------------------------------------------------------------------
# PHASE B — size-DEPENDENT rules (§3, §6.5)
# ---------------------------------------------------------------------------


def _largest_fit(room: float, margin_per_contract: float, cap_is_strict: bool) -> int:
    """How many contracts fit in `room`. Floor, then one strict-inequality step.

    §6.5's aggregate cap is `< 70% × balance` — STRICT. `room // mpc` can land
    exactly on the cap, so the floor alone would approve the one size that sits
    ON the boundary the spec excludes. One subtraction fixes it and keeps the
    computation O(1); a loop would be the same answer with an unbounded shape.
    """
    if margin_per_contract <= 0.0:
        return 0
    fits = int(room // margin_per_contract)
    if fits > 0 and cap_is_strict and fits * margin_per_contract >= room:
        fits -= 1
    return max(fits, 0)


def _size_down_or_deny(
    rule: str, fits: int, order: ProposedOrder, why: str
) -> RuleVerdict:
    """Turn a computed fit into §3's `size-down` or its `deny`. Never into an approve."""
    if fits <= 0:
        return RuleVerdict(
            rule=rule, decision=Decision.DENY, reason=f"{why}; 0 contracts fit"
        )
    return RuleVerdict(
        rule=rule,
        decision=Decision.SIZE_DOWN,
        reason=f"{why}; clamped {order.qty} -> {fits} contract(s)",
        sized_qty=fits,
    )


class PictureCoherenceRule:
    """§3's own definition of `committed`, checked against the snapshot carrying it.

    §3: `committed = Σ open margin + Σ PENDING RESERVATIONS`. §11.3 keeps all
    three as independently-maintained running aggregates and §11.7 requires a
    periodic audit because running aggregates DRIFT. The audit is periodic; this
    is the same comparison for the price of two additions, taken on the snapshot
    the pass is about to size against.

    It denies rather than logging, because the alternative is to size against a
    picture whose own fields disagree — and the drift direction that matters
    (`committed` low) is the one that silently buys room the account does not
    have. §11.7 escalates material drift to HALT; declaring HALT is §12.5 and is
    not this arc, so this rule refuses the trade and names the three figures.
    """

    def __init__(self, name: str, tolerance: float) -> None:
        if tolerance < 0.0:
            raise KnobError(f"{name}: tolerance must be >= 0, got {tolerance!r}")
        self._name = name
        self._tolerance = tolerance

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-DEPENDENT: it guards the aggregates the sizing rules read."""
        return Phase.SIZE_DEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """Two field reads and an addition. The position table is never touched."""
        del order
        expected = picture.sum_open_margin + picture.sum_reservations
        drift = picture.committed - expected
        if abs(drift) > self._tolerance:
            return RuleVerdict(
                rule=self._name,
                decision=Decision.DENY,
                reason=(
                    f"§3 committed drift {drift:+.6f} exceeds tolerance "
                    f"{self._tolerance}: published committed={picture.committed!r} "
                    f"but sum_open_margin={picture.sum_open_margin!r} + "
                    f"sum_reservations={picture.sum_reservations!r} = {expected!r} "
                    f"(picture version {picture.version})"
                ),
            )
        return _clear(self._name)


def _unpriceable_margin(rule: str, order: ProposedOrder) -> RuleVerdict | None:
    """§15 C3's *"missing margin ⇒ not-tradable"*, as a DENY. `None` when priceable.

    ARC 038 / sub-agent E — FE7. Both margin rules compare a DOLLAR figure
    (`proposed_margin` = `qty × margin_per_contract`) against a cap, so a
    `margin_per_contract <= 0` prices the order at nothing and clears on the
    CHEAPEST branch. Measured through the FULL pass: a hundred contracts at `0.0`
    and at `-1000.0` both came out `APPROVE / manifest_exhausted`, against a
    control at `1000.0` that came out `SIZE_DOWN / aggregate_margin_cap`. The
    `<= 0.0` guard in `_largest_fit` is reached only once the cap has ALREADY
    bitten, so it reads as coverage without being any. §2:35 makes the Limiter
    **prohibitive** and `ProposedOrder` validates nothing, so the number cannot
    be taken on the permissive Allocator's word. Non-finite is refused with zero:
    `NaN` passes every ordering comparison and would otherwise raise inside
    `int(NaN)`, a deny naming an interpreter error rather than §15 C3.
    """
    mpc = order.margin_per_contract
    if math.isfinite(mpc) and mpc > 0.0:
        return None
    return RuleVerdict(
        rule=rule,
        decision=Decision.DENY,
        reason=(
            f"§15 C3 missing margin ⇒ NOT-TRADABLE: margin_per_contract={mpc!r} "
            f"for {order.symbol!r} is not a positive finite number, so the "
            f"proposed margin {order.proposed_margin!r} prices this order at "
            f"nothing and every cap it meets clears trivially. An order whose "
            f"margin the Limiter cannot price is one it cannot cap"
        ),
    )


class AggregateMarginCapRule:
    """§6.5's hard aggregate cap: `committed + proposed < fraction × balance`.

    The one rule in the manifest that can SIZE DOWN, and it is the one §3 gives
    the arithmetic for. The Allocator already sized against
    `headroom = 0.70 × balance − COMMITTED` read from the Limiter's published
    cache; between that read and this evaluation another strategy's fill can move
    `committed`. §3 calls that race "trivial wasted sizing, correct outcome" and
    puts the authoritative answer here. Clamping to what now fits IS the correct
    outcome, and §5 says size-down is distinct from deny — so a race that leaves
    room for four contracts of the six proposed sends four.

    `fraction` has no default. §12A owns the number.
    """

    def __init__(self, name: str, fraction: float) -> None:
        if not 0.0 < fraction <= 1.0:
            raise KnobError(
                f"{name}: deployable fraction must be in (0, 1], got {fraction!r} "
                "(§6.5's single number; §12A owns its value)"
            )
        self._name = name
        self._fraction = fraction

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-DEPENDENT: `proposed_margin` is a function of `order.qty`."""
        return Phase.SIZE_DEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """Four reads and a comparison. Aggregates arrive precomputed (§11.3)."""
        unpriceable = _unpriceable_margin(self._name, order)
        if unpriceable is not None:
            return unpriceable
        cap = self._fraction * picture.balance
        room = cap - picture.committed
        proposed = order.proposed_margin
        if picture.committed + proposed < cap:
            return _clear(self._name)
        why = (
            f"§6.5 cap: committed {picture.committed!r} + proposed {proposed!r} "
            f"is not < {self._fraction:.4g} x balance {picture.balance!r} = {cap!r}"
        )
        if room <= 0.0:
            return RuleVerdict(
                rule=self._name, decision=Decision.DENY, reason=f"{why}; no room at all"
            )
        return _size_down_or_deny(
            self._name, _largest_fit(room, order.margin_per_contract, True), order, why
        )


class SurvivalHeadroomRule:
    """§3 Phase B: "projected net-liq impact leaves floor intact (§6.5)".

    §6.5's floor is `net_liq < Σ open margin × (1 + safety_pad)` and the entry
    question is the PROJECTED one: the entry adds `proposed_margin` to Σ open
    margin the moment it fills, so the test is taken against
    `(sum_open_margin + proposed) × (1 + safety_pad)`.

    ------------------------------------------------------------------------
    A FINDING ABOUT THE SEAM, REPORTED RATHER THAN ROUTED AROUND — CHECK-DEBT
    ------------------------------------------------------------------------
    `FinancialPicture` carries no `net_liq`, and §11.3 lists "net-liq mark" as a
    running aggregate alongside the ones it does carry. So this rule reads its
    mark from a SECOND source, and `RulePort`'s own docstring says a rule "may
    not fetch, await, or read a second snapshot, because a rule that reads twice
    can straddle a version boundary".

    The tension is real and is not resolved here. What is defensible: §6.5 marks
    net-liq **per tick** off the price cache, which is a different cadence from
    §3's financial-picture publish, so the two could not share a version stamp
    even if the field existed. What is not defensible is pretending the seam
    already accommodates that. The seam is FROZEN and was not edited; the gap is
    recorded as a debt row naming this rule, and until it is settled this rule
    reads a scalar mark and NOT a snapshot.

    The stale arm is the fail-closed half: `nix_check_contract.md` §17 —
    a safety property proven while its subject is unavailable is not proven.
    """

    def __init__(self, name: str, port: NetLiqMarkPort, safety_pad: float) -> None:
        # ARC 038 / sub-agent E — FE9. `isfinite` beside the ordering test: NaN
        # passes every ordering comparison, so the original `pad < 0.0` ADMITTED
        # a NaN pad, the floor became NaN, and `net_liq < NaN` is False for every
        # mark — the floor was silently OFF at every size. Measured: the case
        # that DENIES at pad 0.25 (net_liq 60 000, floor 63 750) came out APPROVE
        # at pad NaN. `inf` goes with it — an infinite floor denies everything,
        # which is §14's anti-lockout invariant in a knob's clothes.
        if not math.isfinite(safety_pad) or safety_pad < 0.0:
            raise KnobError(
                f"{name}: safety pad must be a finite number >= 0, got "
                f"{safety_pad!r} — a negative pad places the floor BELOW Σ open "
                "margin, which is the broker's own liquidation trigger and the "
                "thing §6.5 exists to stay above; a NaN pad makes the floor NaN "
                "and every comparison against it False, which turns the floor "
                "OFF while every gate over it stays green"
            )
        self._name = name
        self._port = port
        self._safety_pad = safety_pad

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-DEPENDENT: the projection adds `proposed_margin`."""
        return Phase.SIZE_DEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """One scalar read plus two multiplications."""
        net_liq, fresh = self._port.mark()
        if not fresh:
            return RuleVerdict(
                rule=self._name,
                decision=Decision.DENY,
                reason=(
                    "§6.5 net-liq mark is STALE or absent, so the survival floor "
                    "cannot be evaluated. Denying: a safety property proven while "
                    "its subject is unavailable is not proven "
                    "(nix_check_contract.md §17), and the mark is the only reading "
                    "that stands between this account and a broker liquidation"
                ),
            )
        if not math.isfinite(net_liq):
            # ARC 038 / sub-agent E — FE8. The `fresh` arm catches a STALE or
            # ABSENT mark; this catches one present, FRESH and not a number.
            # `NaN < floor` is False, so control fell through to `_clear` —
            # measured: `(NaN, True)` came out of the full pass as APPROVE. A
            # separate branch because a NaN is not stale: the feed is alive and
            # the number is rubbish.
            return RuleVerdict(
                rule=self._name,
                decision=Decision.DENY,
                reason=(
                    f"§6.5 net-liq mark is {net_liq!r} — present and fresh, and "
                    f"not a number. Every comparison against it is False, so the "
                    f"survival floor would be CLEARED by a reading that says "
                    f"nothing. Denying: a safety property proven while its "
                    f"subject is unavailable is not proven (§17)"
                ),
            )
        projected = picture.sum_open_margin + order.proposed_margin
        floor = projected * (1.0 + self._safety_pad)
        if net_liq < floor:
            return RuleVerdict(
                rule=self._name,
                decision=Decision.DENY,
                reason=(
                    f"§6.5 survival floor: net_liq {net_liq!r} < projected "
                    f"Σ open margin {projected!r} x (1 + {self._safety_pad!r}) = "
                    f"{floor!r} — the entry would put the account inside its own "
                    "force-flatten band before it filled"
                ),
            )
        return _clear(self._name)


class DeployableCeilingRule:
    """§3 Phase B: "buffer/deployable ceiling fit", against §11.4's precomputed value.

    ------------------------------------------------------------------------
    THE REDUNDANCY IS REAL, IS NOT AN ACCIDENT, AND IS RECORDED — CHECK-DEBT
    ------------------------------------------------------------------------
    If the publisher defines `deployable = fraction × balance − committed`, then
    `proposed ≤ deployable` and `committed + proposed < fraction × balance` are
    the SAME inequality up to strictness, and this rule can never be the binding
    constraint. §3 nevertheless lists them as two separate Phase-B bullets and
    describes `deployable` only as "uncommitted (deployable) liquidity", which is
    also consistent with `balance − committed`. The spec does not say which.

    Both were considered and neither was chosen silently. This rule fits against
    the PUBLISHED `deployable` — §11.4 precomputes it "on account-state change
    only", so reading it is what §11 asks for, and re-deriving it here would make
    this module a second authority for a number the publisher owns. The cost is
    that under the first reading this rule is dead weight; the benefit is that
    under the second reading it is the only rule enforcing the 30% buffer, and a
    disagreement between the two definitions shows up as this rule denying an
    order the cap approved — which is a visible, attributable event rather than a
    silent choice made in this file.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Phase:
        """Size-DEPENDENT."""
        return Phase.SIZE_DEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """One field read and a comparison."""
        unpriceable = _unpriceable_margin(self._name, order)
        if unpriceable is not None:
            return unpriceable
        proposed = order.proposed_margin
        if proposed <= picture.deployable:
            return _clear(self._name)
        why = (
            f"§11.4 deployable ceiling: proposed margin {proposed!r} exceeds "
            f"published deployable {picture.deployable!r} (picture version "
            f"{picture.version})"
        )
        if picture.deployable <= 0.0:
            return RuleVerdict(
                rule=self._name,
                decision=Decision.DENY,
                reason=f"{why}; nothing deployable",
            )
        return _size_down_or_deny(
            self._name,
            _largest_fit(picture.deployable, order.margin_per_contract, False),
            order,
            why,
        )


# ---------------------------------------------------------------------------
# The executor (§3, §5)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Dispatch:
    """One phase's result: either a terminal outcome, or the binding size-down.

    A tuple return would be two positional `None`s at every call site and the
    reader would have to remember which is which; the mistake that costs money
    here is treating "no outcome" as "approve", so the two are named.
    """

    outcome: GateOutcome | None = None
    binding: RuleVerdict | None = None


class GatePass:
    """§3's ONE authoritative pass. Single-threaded, synchronous, no I/O (§5, §11).

    Construct once at boot. `evaluate` is the whole hot path: one atomic HALT
    read, then Phase A to exhaustion, then Phase B, then — on an approval or a
    size-down — the §3 reservation take.
    """

    def __init__(
        self,
        halt: HaltFlagPort,
        rules: Sequence[RulePort],
        ledger: ReservationLedgerPort | None = None,
    ) -> None:
        """Validate the manifest and partition it by DECLARED phase, once.

        Every rejection below is a manifest under which the pass would run,
        return a plausible verdict, and have skipped a rule.
        """
        self._halt = halt
        self._ledger = ledger
        self._validate(halt, rules)
        self._phase_a = tuple(r for r in rules if r.phase is Phase.SIZE_INDEPENDENT)
        self._phase_b = tuple(r for r in rules if r.phase is Phase.SIZE_DEPENDENT)

    @staticmethod
    def _validate(halt: HaltFlagPort, rules: Sequence[RulePort]) -> None:
        """§12A boot validation for the manifest. Raises `UndispatchableManifest`."""
        if not hasattr(halt, "is_set"):
            raise UndispatchableManifest(
                "the HALT port declares no is_set() — §11.5's first atomic read "
                "has nothing to read, and a pre-gate that cannot see HALT is a "
                "pre-gate that approves during a HALT"
            )
        if not rules:
            raise UndispatchableManifest(
                "empty manifest: §5's default posture is accept-unless-a-rule-blocks, "
                "so a gate with no rules approves every proposal. Refused at boot"
            )
        seen: set[str] = set()
        for index, rule in enumerate(rules):
            if not isinstance(rule, RulePort):
                raise UndispatchableManifest(
                    f"manifest[{index}] does not satisfy RulePort (needs name, "
                    f"phase, evaluate): {type(rule).__name__}"
                )
            if not isinstance(rule.phase, Phase):
                raise UndispatchableManifest(
                    f"manifest[{index}] {rule.name!r} declares phase "
                    f"{rule.phase!r}, which is not a Phase member — the partition "
                    "would DROP it, and a rule that is in the manifest and never "
                    "runs is indistinguishable from a rule that approved"
                )
            if rule.name in seen:
                raise UndispatchableManifest(
                    f"manifest[{index}] repeats the name {rule.name!r} — §3 and §5 "
                    "both require a denial to NAME the blocking rule, and a "
                    "duplicated name makes that attribution ambiguous"
                )
            if not rule.name.strip():
                raise UndispatchableManifest(f"manifest[{index}] has a blank name")
            seen.add(rule.name)
        for phase in Phase:
            if not any(rule.phase is phase for rule in rules):
                raise UndispatchableManifest(
                    f"manifest declares no rule in phase {phase.name} — §3 fixes a "
                    "TWO-phase pass, and a pass whose phase B is empty checks "
                    "committed margin never while looking exactly like one that does"
                )

    @property
    def manifest(self) -> tuple[str, ...]:
        """Rule names in DISPATCH order — phase A then phase B. For evidence only."""
        return tuple(r.name for r in self._phase_a) + tuple(
            r.name for r in self._phase_b
        )

    def evaluate(
        self, order: ProposedOrder, picture: FinancialPicture, now: float
    ) -> GateOutcome:
        """One pass. Returns §3's approve / size-down / deny, rule always named."""
        evaluated: list[str] = [HALT_RULE]
        halted, why = self._halt.is_set()
        if halted:
            return GateOutcome(
                decision=Decision.DENY,
                rule=HALT_RULE,
                reason=why.strip() or "global HALT flag is set (§3 branch 0, §12.5)",
                phase=Phase.SIZE_INDEPENDENT,
                evaluated=tuple(evaluated),
            )

        first = self._dispatch(
            self._phase_a, Phase.SIZE_INDEPENDENT, order, picture, evaluated
        )
        if first.outcome is not None:
            return first.outcome
        second = self._dispatch(
            self._phase_b, Phase.SIZE_DEPENDENT, order, picture, evaluated
        )
        if second.outcome is not None:
            return second.outcome
        return self._settle(order, second.binding, tuple(evaluated), now)

    def _dispatch(
        self,
        rules: tuple[RulePort, ...],
        phase: Phase,
        order: ProposedOrder,
        picture: FinancialPicture,
        evaluated: list[str],
    ) -> _Dispatch:
        """Run one phase. First DENY halts ALL further dispatch (§5 fail-fast)."""
        binding: RuleVerdict | None = None
        for rule in rules:
            # Recorded BEFORE the call so a rule that raises still appears in the
            # record. A rule missing from `evaluated` must mean it never ran.
            evaluated.append(rule.name)
            try:
                verdict = rule.evaluate(order, picture)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                return _Dispatch(
                    outcome=self._deny(
                        rule.name,
                        f"rule raised {type(exc).__name__}: {exc} — a rule that "
                        "cannot answer has not approved (§5: side-effect-free, "
                        "non-blocking; directive 4: fail closed)",
                        phase,
                        evaluated,
                    )
                )
            defect = _verdict_defect(rule, verdict, phase, order)
            if defect:
                return _Dispatch(
                    outcome=self._deny(rule.name, defect, phase, evaluated)
                )
            if verdict.decision is Decision.DENY:
                return _Dispatch(
                    outcome=GateOutcome(
                        decision=Decision.DENY,
                        rule=rule.name,
                        reason=verdict.reason,
                        phase=phase,
                        evaluated=tuple(evaluated),
                    )
                )
            if verdict.decision is Decision.SIZE_DOWN and (
                binding is None or (verdict.sized_qty or 0) < (binding.sized_qty or 0)
            ):
                binding = verdict
        return _Dispatch(binding=binding)

    @staticmethod
    def _deny(
        rule: str, reason: str, phase: Phase, evaluated: list[str]
    ) -> GateOutcome:
        """A denial attributed to a named rule."""
        return GateOutcome(
            decision=Decision.DENY,
            rule=rule,
            reason=reason,
            phase=phase,
            evaluated=tuple(evaluated),
        )

    def _settle(
        self,
        order: ProposedOrder,
        binding: RuleVerdict | None,
        evaluated: tuple[str, ...],
        now: float,
    ) -> GateOutcome:
        """No rule blocked. Take the §3 reservation and report the outcome.

        §3: "approve ⇒ TAKE RESERVATION (proposed margin)". The reservation is
        for the FINAL quantity, so a size-down reserves what will actually be
        sent — reserving the proposed size would over-commit by the clamp, and
        over-commitment is the thing Phase B exists to prevent.
        """
        sized = None if binding is None else binding.sized_qty
        final = order if sized is None else dataclasses.replace(order, qty=sized)
        reservation_id: str | None = None
        if self._ledger is not None:
            try:
                reservation_id = self._ledger.take(final, now).reservation_id
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                return self._deny(
                    "reservation_ledger",
                    f"the §3 reservation could not be taken ({type(exc).__name__}: "
                    f"{exc}) — an approval whose margin is not reserved is an "
                    "approval the next pass cannot see, which is the over-commitment "
                    "Phase B exists to prevent",
                    Phase.SIZE_DEPENDENT,
                    list(evaluated),
                )
        if binding is not None:
            return GateOutcome(
                decision=Decision.SIZE_DOWN,
                rule=binding.rule,
                reason=binding.reason,
                phase=Phase.SIZE_DEPENDENT,
                evaluated=evaluated,
                sized_qty=sized,
                reservation_id=reservation_id,
            )
        return GateOutcome(
            decision=Decision.APPROVE,
            rule=PASS_COMPLETE,
            reason=(
                f"{len(evaluated)} branch/rule(s) evaluated, none blocked "
                "(§5 default posture: accept unless a rule blocks)"
            ),
            phase=Phase.SIZE_DEPENDENT,
            evaluated=evaluated,
            reservation_id=reservation_id,
        )


def _verdict_defect(  # pylint: disable=too-many-return-statements
    rule: RulePort, verdict: RuleVerdict, phase: Phase, order: ProposedOrder
) -> str:
    """Why this verdict may not be honoured as returned, or `''`.

    Each condition is a way a rule can produce a verdict the executor would
    otherwise act on incorrectly, and every one of them fails CLOSED — the caller
    turns a non-empty return into a DENY naming the rule.
    """
    if verdict.rule != rule.name:
        return (
            f"verdict is attributed to {verdict.rule!r} but was produced by "
            f"{rule.name!r} — §3 requires the BLOCKING RULE NAMED, and a verdict "
            "that misattributes itself breaks the only record of who denied"
        )
    if verdict.decision is Decision.DENY and not verdict.reason.strip():
        return (
            "denied with an empty reason — §3's 'deny (rule named, fail-fast)' is "
            "a denial an operator can act on, and a generic denial cannot be "
            "reconstructed from the event log"
        )
    if verdict.decision is not Decision.SIZE_DOWN:
        return ""
    if phase is Phase.SIZE_INDEPENDENT:
        return (
            "a size-INDEPENDENT rule returned SIZE_DOWN. §3 puts every rule that "
            "can depend on quantity in phase B; a phase-A rule sizing an order is "
            "either mis-declared or reading a quantity it must not read"
        )
    if verdict.sized_qty is None:
        return "SIZE_DOWN with sized_qty=None — a clamp that names no quantity"
    if not 0 <= verdict.sized_qty < order.qty:
        return (
            f"SIZE_DOWN to {verdict.sized_qty} against a proposal of {order.qty} — "
            "a clamp must reduce; §5 makes size-down distinct from deny and "
            "neither of them may INCREASE a proposal"
        )
    return ""


def default_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    blackout: SymbolFlagPort,
    tradability: SymbolFlagPort,
    staleness: SymbolFlagPort,
    clock_skew: GlobalFlagPort,
    in_flight: InFlightPort,
    net_liq: NetLiqMarkPort,
    deployable_fraction: float,
    survival_safety_pad: float,
    coherence_tolerance: float,
) -> tuple[RulePort, ...]:
    """§3's rule set, in §3's own bullet order, from ports and §12A knobs.

    This is a MANIFEST, not the manifest loader. §5 makes the manifest a loadable
    file and that loader is not in this arc — building one would need the §12A
    per-module JSON that `risks/` owns, and a half-built loader would make the
    gap look addressed. What this function guarantees is that the rule set the
    executor is normally handed is derived from §3's bullets in one place.

    The order here is §5's "cheapest-and-most-decisive first" within each phase.
    It is NOT what makes phase A run before phase B — `GatePass` partitions by
    declared phase, so this ordering could be reversed without changing which
    phase runs first, and `checks/check_limiter_gate.py` proves that by reversing
    it and observing.
    """
    return (
        SymbolFlagRule(
            "blackout_window", blackout, "§6.1-6.3 EOD/EOW/news-margin/roll-day"
        ),
        SymbolFlagRule(
            "tradability",
            tradability,
            "§11.1 tradable[symbol], §3 session boundary + post-open warmup",
        ),
        SymbolFlagRule("data_staleness", staleness, "§6.4 stale-data halt"),
        GlobalFlagRule("clock_skew", clock_skew, "§12.3 clock integrity"),
        InFlightLockRule("in_flight_lock", in_flight),
        PictureCoherenceRule("picture_coherence", coherence_tolerance),
        AggregateMarginCapRule("aggregate_margin_cap", deployable_fraction),
        SurvivalHeadroomRule("survival_headroom", net_liq, survival_safety_pad),
        DeployableCeilingRule("deployable_ceiling"),
    )
