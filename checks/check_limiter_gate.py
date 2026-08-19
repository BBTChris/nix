#!/usr/bin/env python3
"""Gate: the Limiter's two-phase pass ORDERS BY EXECUTION, not by source order.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *every
size-INDEPENDENT rule has finished before any size-DEPENDENT rule is dispatched,
and the pass says who denied.* No instrument in this tree owned that before —
`check_limiter_seam` reads the seam STATICALLY and says so in its own docstring
("It cannot prove the Limiter's executor honours the phase ordering") — so this
is a new instrument rather than a second opinion. The boundary between the two is
stated in both files: the seam gate judges DECLARATIONS, this one judges a pass
that ran.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless a document is
named on the same line.

------------------------------------------------------------------------------
WHY THIS GATE HAS TO DRIVE REAL OBJECTS
------------------------------------------------------------------------------
A Phase-B rule that runs after a Phase-A denial produces **byte-identical
output** to a correct pass: the denial stands either way, the reason is the same,
the decision is the same. Nothing about the outcome can tell the two apart. So
the measurement cannot be over outputs and cannot be over the manifest listing —
reading a list proves the ORDER SOMEBODY WROTE, and the defect is in the order
something RAN.

This gate therefore constructs real `RulePort` objects that **record their own
invocation** on a shared log, hands them to the real `GatePass`, and reads the
log. It holds two records against each other:

* `GateOutcome.evaluated` — written by the EXECUTOR as it dispatches.
* the rules' own log — written by each RULE as it is entered, plus the HALT
  port as it is read.

Either alone is trusting one side's bookkeeping. An executor that appended a
name it never dispatched, or dispatched a rule it never recorded, moves exactly
one of the two, and ARM 5 is that comparison.

**THE MANIFEST IS HANDED IN SCRAMBLED PHASE ORDER, DELIBERATELY.** A manifest
already sorted A-then-B would be satisfied by an executor that simply iterates
the list, which is the implementation this gate exists to reject. ARM 1 asserts
the handed order and the observed order DIFFER before it asserts anything about
the observed order — a scramble that happened to equal the sorted order would
make the whole arm vacuous.

------------------------------------------------------------------------------
THE O(1) CLAIM IS MEASURED ACROSS FOUR INPUT SIZES OR IT IS NOT MADE
------------------------------------------------------------------------------
"O(1)" asserted about one run is unfalsifiable decoration. §11.3 makes the
checkable version available: Σ open margin, Σ reservations, `committed` and
`deployable` are RUNNING AGGREGATES that arrive precomputed on the snapshot, so
a correct pass never traverses the position table. ARM 6 drives the SHIPPED
`default_manifest` against pictures whose `positions` is a tuple subclass
counting every traversal operation, at |positions| ∈ (1, 64, 512, 4096), and
requires the traversal count to be **zero and identical at all four sizes**. A
rule that re-derived `committed` by summing rows would satisfy every other arm
in this file and produce 1/64/512/4096 here.

`__len__` is counted SEPARATELY and reported rather than judged: `len()` on a
tuple is O(1) and a future rule could legitimately want it, so folding it into
the verdict would redden a correct implementation (doctrine B.4).

**Wall-clock timings are in `evidence` and are NOT an input to any verdict.**
CHECK-DEBT D3.39 is a control in this tree whose verdict became a function of
machine load; a timing ratio here would be the same defect wearing an O(1)
badge. The counting instrument is deterministic and load-independent.

------------------------------------------------------------------------------
WHAT THIS GATE CANNOT PROVE — stated, so no green implies it
------------------------------------------------------------------------------
1. **That the shipped rules are the RIGHT rules.** ARMS 1-5 drive instrumented
   rules; they measure the EXECUTOR. ARM 6 and ARM 7 drive the shipped
   `default_manifest`. Whether `blackout_window`'s cache is ever populated with
   a real calendar is out of this arc entirely and out of this gate.
2. **Anything about exits.** Stop conversion, protective-exit wiring,
   session-close flatten, HALT auto-clear and cold-start reconciliation are not
   built. A Limiter that gates but cannot exit is not a safety spine, and a green
   here is about the gate half only.
3. **Concurrency.** §5 fixes the Limiter as a single-threaded loop and this gate
   drives it serially. It says nothing about a second thread, because there is
   not supposed to be one.
4. **The reservation ledger.** `GatePass` takes a reservation through the frozen
   `ReservationLedgerPort`; this gate uses a recording double for it. The ledger
   implementation is a different module with a different owner.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status, result_from_defects

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text; the only way to
# deduplicate them is a shared helper, which §4.2 forbids.
# R0903 (too-few-public-methods) disabled at module scope. Every class in this
# file is a PORT DOUBLE carrying exactly the port's own verb, or the counting
# tuple. Adding a second method to clear a threshold would make each double a
# worse stand-in for the thing it doubles, which is the opposite of what the
# threshold is for.
# pylint: disable=too-few-public-methods
#
# C0302 (too-many-lines) disabled. The module is over pylint's 1000-line default
# and the split was considered and refused: `nix_check_contract.md` §4.2 requires
# every checks/check_*.py be INDEPENDENTLY RUNNABLE, so the instrumented
# population -- the recording rules, the recording HALT port, the counting
# position table, the ledger double -- cannot move to a helper module without
# breaking that guarantee, and it is the population that makes the seven arms
# more than assertions about a listing. The same disable is carried, for the same
# §4.2 reason, by check_derived_claims, check_order_path_bans,
# check_datafeed_bar_seal and check_datafeed_granted_mode.
# pylint: disable=too-many-lines
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The subject is a stdlib-only module in this tree and
#: is imported by path, not through the venv.
DEPENDS_ON: tuple[str, ...] = ()
#: The subject is loaded by prefixing `<nix_home>/scripts` onto `sys.path` and
#: purging any already-imported `nixrisk*` so the modules come from the tree
#: under measurement rather than from whichever tree imported first. Both are
#: restored afterwards, and both are declared: check contract v2 §12 checks
#: declared claims against OBSERVED ones, so an interpreter mutation left
#: undeclared here would be a finding against this gate.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No socket, no subprocess, no sleep, no poll. Every arm is arithmetic over
#: objects this process constructed.
TIME_BOUND = False
#: NON-CORRECTABLE. The measured side is the executor's dispatch order and the
#: reference side is §3 of a FROZEN spec. A gate empowered to edit the executor
#: into agreement would be writing the implementation it is judging.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is §3 of the frozen risk spec, which is never edited, "
    "and the measured side is the dispatch order of the module under test. An "
    "instrument that could rewrite the executor to agree with the spec would be "
    "authoring the subject it certifies -- the same objection that makes "
    "check_limiter_seam non-correctable."
)
#: Genuinely DRIVEN here, not merely named: every arm constructs objects from
#: this module and executes its `GatePass.evaluate`.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/gate.py",)

NAME = "check_limiter_gate"

GATE = "scripts/nixrisk/gate.py"
SITE = f"{GATE}:GatePass.evaluate"
BOOT_SITE = f"{GATE}:GatePass._validate"

#: Non-vacuity floors (`debug.md` §7.12). Each is a count this gate MUST reach or
#: it has measured nothing and says so rather than passing.
MIN_EVALUATED = 8
MIN_PHASE_A_DRIVEN = 3
MIN_PHASE_B_DRIVEN = 3
MIN_SHIPPED_RULES = 6

#: The position-table sizes ARM 6 characterises the pass across. Four, not one:
#: a single size cannot distinguish a constant from a linear cost, and a claim
#: nobody can refute is decoration.
TABLE_SIZES: tuple[int, ...] = (1, 64, 512, 4096)


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ---------------------------------------------------------------------------
# Loading the subject FROM THE TREE UNDER MEASUREMENT
# ---------------------------------------------------------------------------


class _Subject:  # pylint: disable=too-few-public-methods
    """The `gate` and `seam` modules of one tree, and nothing else.

    Both come from the same tree so the types the gate imported and the types
    this file constructs are the SAME classes. Loading `gate` from a `tmp_path`
    copy while building a `ProposedOrder` from the repo would compare a plant
    against objects it never saw.

    Typed `Any` on purpose: the whole point is that these modules come from a
    tree chosen at run time, so a static type here would be a claim about WHICH
    tree was loaded -- exactly the thing this gate must not assume.
    """

    def __init__(self, gate: Any, seam: Any) -> None:
        self.gate = gate
        self.seam = seam


def load_subject(home: Path) -> tuple[_Subject | None, str]:
    """Import `nixrisk.gate` from `home`. Returns `(subject, complaint)`.

    `sys.modules` is purged of `nixrisk*` before and restored after, because a
    check that ran once against the repo would otherwise hand back the repo's
    module for every subsequent tree — and a plant that is never loaded is a
    plant that cannot fail. The modules survive the purge as live objects; only
    the import cache is put back.
    """
    scripts = home / "scripts"
    if not (scripts / "nixrisk" / "gate.py").is_file():
        return None, f"{GATE} is not on disk under {home} — nothing to drive"
    saved_path = list(sys.path)
    saved_mods = {
        key: value
        for key, value in sys.modules.items()
        if key == "nixrisk" or key.startswith("nixrisk.")
    }
    for key in saved_mods:
        del sys.modules[key]
    sys.path.insert(0, str(scripts.resolve()))
    try:
        seam = importlib.import_module("nixrisk.seam")
        gate = importlib.import_module("nixrisk.gate")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, f"{GATE} would not import from {home}: {type(exc).__name__}: {exc}"
    finally:
        for key in [
            key
            for key in list(sys.modules)
            if key == "nixrisk" or key.startswith("nixrisk.")
        ]:
            del sys.modules[key]
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path
    return _Subject(gate, seam), ""


# ---------------------------------------------------------------------------
# The instrumented population — objects that record their OWN invocation
# ---------------------------------------------------------------------------


class _RecordingRule:
    """A real `RulePort` that appends its name to a shared log when entered.

    The log is the SECOND record. `GateOutcome.evaluated` is the executor's own
    account of what it dispatched; this is the population's account of what was
    called. They are written by different code and compared by ARM 5.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        log: list[str],
        name: str,
        phase: Any,
        seam: Any,
        decision: Any = None,
        reason: str = "",
    ) -> None:
        self._log = log
        self._name = name
        self._phase = phase
        self._seam = seam
        self._decision = decision if decision is not None else seam.Decision.APPROVE
        self._reason = reason

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Any:
        """The declared §3 phase. The executor partitions on THIS, not on order."""
        return self._phase

    def evaluate(self, order: Any, picture: Any) -> Any:
        """Record the invocation, then return the configured verdict."""
        del order, picture
        self._log.append(self._name)
        return self._seam.RuleVerdict(
            rule=self._name, decision=self._decision, reason=self._reason
        )


class _RecordingHalt:
    """The §11.5 HALT flag, recording the moment it is actually read."""

    def __init__(self, log: list[str], token: str, halted: bool = False) -> None:
        self._log = log
        self._token = token
        self._halted = halted

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)` — and a mark on the log at the position it was read."""
        self._log.append(self._token)
        return self._halted, "planted HALT" if self._halted else ""


class _CountingPositions(tuple):  # pylint: disable=too-few-public-methods
    """A position table that counts every ROW it yields.

    Subclassing `tuple` rather than wrapping it keeps `FinancialPicture` a frozen
    dataclass holding a real tuple, so nothing about the subject changes shape to
    accommodate the instrument.

    **Rows, not calls, and that is the difference between a shape measurement and
    a boolean.** Counting `__iter__` INVOCATIONS gives 1 for `sum(r.margin for r
    in positions)` at every table size, which says "somebody iterated" and says
    nothing about cost. Counting rows YIELDED gives 1/64/512/4096 for the same
    defect — a linear shape, visible as a shape, which is the only form in which
    an O(1) claim can be refuted.

    `__len__` is counted apart from traversal — see the module docstring for why
    it is reported and not judged.
    """

    #: Attached by `_counting_positions`. A tuple subclass keeps its `__dict__`
    #: (no `__slots__` here, deliberately) so the tally rides with the table
    #: rather than living in a module global two arms would share.
    tally: dict[str, int]

    def _bump(self, key: str) -> None:
        self.tally[key] = self.tally.get(key, 0) + 1

    def __iter__(self) -> Any:
        for row in tuple.__iter__(self):
            self._bump("traverse")
            yield row

    def __getitem__(self, index: Any) -> Any:
        self._bump("traverse")
        return tuple.__getitem__(self, index)

    def __contains__(self, item: Any) -> bool:
        self._bump("traverse")
        return tuple.__contains__(self, item)

    def __len__(self) -> int:
        self._bump("len")
        return tuple.__len__(self)


def _counting_positions(rows: tuple[Any, ...]) -> _CountingPositions:
    """Build a counting table with a fresh tally attached."""
    table = _CountingPositions(rows)
    table.tally = {}
    return table


class _Reservation:  # pylint: disable=too-few-public-methods
    """The one field `GatePass._settle` reads back off a take."""

    def __init__(self, reservation_id: str) -> None:
        self.reservation_id = reservation_id


class _RecordingLedger:  # pylint: disable=too-few-public-methods
    """A `ReservationLedgerPort` double. Records takes; never leaks a real id."""

    def __init__(self) -> None:
        self.taken: list[int] = []

    def take(self, order: Any, now: float) -> _Reservation:
        """Record the FINAL quantity the pass settled on and hand back an id."""
        del now
        self.taken.append(order.qty)
        return _Reservation(f"res-{len(self.taken)}")


# ---------------------------------------------------------------------------
# Fixtures built from the SUBJECT TREE's own seam types
# ---------------------------------------------------------------------------


def _order(seam: Any, qty: int = 4) -> Any:
    return seam.ProposedOrder(
        client_order_id="gate-probe-1",
        strategy_id="probe",
        symbol="ES",
        side=seam.Side.LONG,
        qty=qty,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture(seam: Any, positions: Any = ()) -> Any:
    """A snapshot with generous room, so no shipped rule denies on the numbers."""
    return seam.FinancialPicture(
        version=7,
        published_ts=1.0,
        balance=1_000_000.0,
        positions=positions,
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=500_000.0,
    )


def _scrambled(subject: _Subject, log: list[str], denier: str = "") -> list[Any]:
    """A manifest in DELIBERATELY WRONG phase order: B, B, A, B, A, A, A.

    The denial, when asked for, is planted on a Phase-A rule that sits LAST in
    the handed order — so an executor that iterated the list would have run three
    Phase-B rules before ever reaching it.
    """
    seam = subject.seam
    phase_a = seam.Phase.SIZE_INDEPENDENT
    phase_b = seam.Phase.SIZE_DEPENDENT
    plan = (
        ("b_one", phase_b),
        ("b_two", phase_b),
        ("a_one", phase_a),
        ("b_three", phase_b),
        ("a_two", phase_a),
        ("a_three", phase_a),
        ("a_four", phase_a),
    )
    rules: list[Any] = []
    for name, phase in plan:
        deny = name == denier
        rules.append(
            _RecordingRule(
                log,
                name,
                phase,
                seam,
                decision=seam.Decision.DENY if deny else None,
                reason=f"planted denial by {name}" if deny else "",
            )
        )
    return rules


def _drive(
    subject: _Subject, rules: list[Any], log: list[str], halted: bool = False
) -> tuple[Any, _RecordingLedger]:
    """One real pass over `rules`, with the HALT port recording on the same log."""
    gate = subject.gate
    halt = _RecordingHalt(log, gate.HALT_RULE, halted)
    ledger = _RecordingLedger()
    passer = gate.GatePass(halt, rules, ledger)
    outcome = passer.evaluate(_order(subject.seam), _picture(subject.seam), 1.0)
    return outcome, ledger


# ---------------------------------------------------------------------------
# ARM 0 — NON-VACUITY. The pass RAN, and both phases are represented.
# ---------------------------------------------------------------------------


def non_vacuity(subject: _Subject) -> tuple[str, str]:
    """`(evidence, complaint)`. A complaint is CANNOT_MEASURE, never a PASS."""
    log: list[str] = []
    rules = _scrambled(subject, log)
    outcome, _ = _drive(subject, rules, log)
    seam = subject.seam
    ran_a = [
        rule.name
        for rule in rules
        if rule.phase is seam.Phase.SIZE_INDEPENDENT and rule.name in log
    ]
    ran_b = [
        rule.name
        for rule in rules
        if rule.phase is seam.Phase.SIZE_DEPENDENT and rule.name in log
    ]
    if outcome.decision is not seam.Decision.APPROVE:
        return "", (
            f"the unobstructed drive returned {outcome.decision} via "
            f"{outcome.rule!r} ({outcome.reason}) instead of APPROVE — every "
            "ordering arm below is about a pass that reached the end of the "
            "manifest, and this one did not"
        )
    if len(outcome.evaluated) < MIN_EVALUATED:
        return "", (
            f"only {len(outcome.evaluated)} branch/rule(s) evaluated "
            f"({', '.join(outcome.evaluated) or 'none'}), below the floor of "
            f"{MIN_EVALUATED} — a latency or ordering claim over a pass that "
            "barely ran measures nothing"
        )
    if len(ran_a) < MIN_PHASE_A_DRIVEN or len(ran_b) < MIN_PHASE_B_DRIVEN:
        return "", (
            f"{len(ran_a)} size-independent and {len(ran_b)} size-dependent "
            f"rule(s) actually ran, below the floors "
            f"({MIN_PHASE_A_DRIVEN}/{MIN_PHASE_B_DRIVEN}) — an ordering property "
            "over one phase is not an ordering property"
        )
    return (
        f"drove {len(outcome.evaluated)} branch/rule(s): {len(ran_a)} phase-A + "
        f"{len(ran_b)} phase-B, decision {outcome.decision.value}"
    ), ""


# ---------------------------------------------------------------------------
# ARM 1 — EXECUTION ORDER, observed. Phase A is exhausted before phase B starts.
# ---------------------------------------------------------------------------


def arm_ordering(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Hand the manifest in the wrong phase order; read what actually ran.

    THE DISCRIMINATING-POWER GUARD IS A PROPERTY OF THE FIXTURE, NOT OF THE RUN,
    AND THE FIRST SPELLING OF IT GOT THAT WRONG. The obvious guard — *refuse if
    the handed order equals the observed order* — was written, and the arc's own
    source-order plant immediately turned this gate's sharpest FAIL into a
    CANNOT_MEASURE: an executor that iterates the manifest makes handed and
    observed identical BY BEING THE DEFECT. A guard whose trigger condition is
    the defect is a gate that goes quiet exactly when it matters.

    The correct question is asked of the fixture alone, before anything runs:
    *is the manifest this arm hands over already grouped phase-A-then-phase-B?*
    If it is, the arm cannot discriminate and says so. If it is not, whatever the
    executor does next is attributable.
    """
    seam = subject.seam
    log: list[str] = []
    rules = _scrambled(subject, log)
    handed = [rule.name for rule in rules]
    phase_of = {rule.name: rule.phase for rule in rules}
    rank = {seam.Phase.SIZE_INDEPENDENT: 0, seam.Phase.SIZE_DEPENDENT: 1}
    handed_ranks = [rank[phase_of[name]] for name in handed]
    if handed_ranks == sorted(handed_ranks):
        return [], (
            f"the manifest handed to this arm is ALREADY grouped phase-A-then-"
            f"phase-B ({handed}), so an executor that merely iterates the list "
            "would satisfy it. The fixture must scramble the phases or this arm "
            "has no discriminating power"
        )

    outcome, _ = _drive(subject, rules, log)
    ran = [name for name in log if name != subject.gate.HALT_RULE]
    defects: list[tuple[str, str]] = []
    seen_b = [
        index
        for index, name in enumerate(ran)
        if phase_of[name] is seam.Phase.SIZE_DEPENDENT
    ]
    late_a = [
        (index, name)
        for index, name in enumerate(ran)
        if phase_of[name] is seam.Phase.SIZE_INDEPENDENT
        and seen_b
        and index > seen_b[0]
    ]
    for index, name in late_a:
        defects.append(
            (
                SITE,
                (
                    f"size-INDEPENDENT rule {name!r} executed at position {index}, "
                    f"AFTER size-DEPENDENT rule {ran[seen_b[0]]!r} at position "
                    f"{seen_b[0]}. §3 fixes all phase-A rules before any phase-B rule "
                    f"in one pass. Observed execution order: {ran}"
                ),
            )
        )
    if tuple(outcome.evaluated)[1:] != tuple(ran):
        defects.append(
            (
                SITE,
                (
                    "the executor's own record and the rules' record disagree on the "
                    f"unobstructed pass: evaluated={list(outcome.evaluated)[1:]} vs "
                    f"observed={ran}"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 2 — a phase-A DENIAL stops the pass dead. No phase-B rule may run.
# ---------------------------------------------------------------------------


def arm_fail_fast(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """§5: first deny halts all further dispatch; blocking rule named."""
    seam = subject.seam
    log: list[str] = []
    rules = _scrambled(subject, log, denier="a_two")
    outcome, ledger = _drive(subject, rules, log)
    phase_of = {rule.name: rule.phase for rule in rules}
    ran = [name for name in log if name != subject.gate.HALT_RULE]

    if "a_two" not in ran:
        return [], (
            "the planted denier never executed, so this arm asserts nothing "
            f"about fail-fast. Observed: {ran}"
        )
    defects: list[tuple[str, str]] = []
    leaked = [name for name in ran if phase_of[name] is seam.Phase.SIZE_DEPENDENT]
    if leaked:
        defects.append(
            (
                SITE,
                (
                    f"size-DEPENDENT rule(s) {leaked} executed even though the "
                    "size-INDEPENDENT rule 'a_two' denied. §3's phase order and §5's "
                    "global fail-fast are both violated, and the OUTPUT of this pass "
                    f"is identical to a correct one. Observed execution order: {ran}"
                ),
            )
        )
    after = ran[ran.index("a_two") + 1 :]
    if after:
        defects.append(
            (
                SITE,
                (
                    f"{len(after)} rule(s) {after} executed AFTER the denial by "
                    "'a_two' — §5: 'first deny halts all further dispatch'"
                ),
            )
        )
    if outcome.rule != "a_two":
        defects.append(
            (
                SITE,
                (
                    f"the denial is attributed to {outcome.rule!r}, not to the rule "
                    "that denied ('a_two'). §3: 'deny (rule named, fail-fast)'; §5: "
                    "'blocking rule named'"
                ),
            )
        )
    if "planted denial by a_two" not in outcome.reason:
        defects.append(
            (
                SITE,
                (
                    f"the denial reason {outcome.reason!r} is not the denying rule's "
                    "own reason — a generic denial is one the operator cannot act on "
                    "and the event log cannot reconstruct"
                ),
            )
        )
    if outcome.phase is not seam.Phase.SIZE_INDEPENDENT:
        defects.append(
            (SITE, f"the denial is reported in phase {outcome.phase!r}, not phase A")
        )
    if ledger.taken:
        defects.append(
            (
                f"{GATE}:GatePass._settle",
                (
                    f"a reservation was taken ({ledger.taken}) on a DENIED proposal — "
                    "§3 takes a reservation at APPROVAL only"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 3 — HALT is read FIRST, and a HALT pass dispatches no rule at all.
# ---------------------------------------------------------------------------


def arm_halt_first(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """§11.5: 'Global HALT flag — first atomic read in pre-gate'. §3: branch 0."""
    gate = subject.gate
    seam = subject.seam
    token = gate.HALT_RULE
    defects: list[tuple[str, str]] = []

    clear_log: list[str] = []
    clear_outcome, _ = _drive(subject, _scrambled(subject, clear_log), clear_log)
    if token not in clear_log:
        return [], (
            "the HALT port was never read on an unobstructed pass, so this arm "
            "has nothing to place — the drive did not reach the pre-gate"
        )
    if clear_log.index(token) != 0:
        defects.append(
            (
                SITE,
                (
                    f"the HALT flag was read at position {clear_log.index(token)} of "
                    f"the observed sequence {clear_log}, not FIRST. §11.5 makes it the "
                    "first atomic read in the pre-gate and §3 calls it branch 0; a "
                    "HALT read behind other rules means work happened during a HALT"
                ),
            )
        )
    if clear_outcome.evaluated and clear_outcome.evaluated[0] != token:
        defects.append(
            (
                SITE,
                (
                    f"GateOutcome.evaluated opens with {clear_outcome.evaluated[0]!r}, "
                    f"not {token!r} — branch 0 is not on the record of every pass"
                ),
            )
        )

    halt_log: list[str] = []
    halt_outcome, _ = _drive(
        subject, _scrambled(subject, halt_log, denier="a_two"), halt_log, halted=True
    )
    dispatched = [name for name in halt_log if name != token]
    if dispatched:
        defects.append(
            (
                SITE,
                (
                    f"{len(dispatched)} rule(s) {dispatched} were dispatched while the "
                    "global HALT flag was SET. Branch 0 must return before the manifest "
                    "is touched"
                ),
            )
        )
    if halt_outcome.rule != token or halt_outcome.decision is not seam.Decision.DENY:
        defects.append(
            (
                SITE,
                (
                    f"a set HALT produced decision {halt_outcome.decision!r} via "
                    f"{halt_outcome.rule!r}; expected a DENY named {token!r}"
                ),
            )
        )
    if tuple(halt_outcome.evaluated) != (token,):
        defects.append(
            (
                SITE,
                (
                    f"a HALT pass recorded {list(halt_outcome.evaluated)} as evaluated; "
                    f"expected exactly ({token!r},)"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 5 — the executor's record and the population's record must agree.
# ---------------------------------------------------------------------------


def arm_records_agree(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Neither record is trusted alone. An executor that lies moves exactly one."""
    defects: list[tuple[str, str]] = []
    scenarios = (
        ("unobstructed", ""),
        ("phase-A denial", "a_two"),
        ("phase-B denial", "b_two"),
    )
    checked = 0
    for label, denier in scenarios:
        log: list[str] = []
        outcome, _ = _drive(subject, _scrambled(subject, log, denier=denier), log)
        checked += 1
        if tuple(outcome.evaluated) != tuple(log):
            defects.append(
                (
                    SITE,
                    (
                        f"[{label}] GateOutcome.evaluated={list(outcome.evaluated)} but "
                        f"the rules and the HALT port recorded {log}. The executor's "
                        "account of what it dispatched is not what ran; one of the two "
                        "is fabricated and `evaluated` is the only field that can "
                        "distinguish a correct pass from a mis-ordered one"
                    ),
                )
            )
    if checked < len(scenarios):
        return [], f"only {checked} of {len(scenarios)} scenarios were driven"
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 6 — the O(1) SHAPE, measured across four position-table sizes.
# ---------------------------------------------------------------------------


def _shipped_manifest(subject: _Subject) -> tuple[Any, ...]:
    """The real `default_manifest`, wired to always-clear ports and real knobs."""
    gate = subject.gate

    class _Clear:  # pylint: disable=too-few-public-methods
        """Every §11.1 cache, unblocked."""

        def read(self, symbol: str | None = None) -> tuple[bool, str]:
            """`(blocked, reason)`."""
            del symbol
            return False, ""

        def in_flight(self, strategy_id: str) -> tuple[bool, str]:
            """`(locked, reason)`."""
            del strategy_id
            return False, ""

    class _NetLiq:  # pylint: disable=too-few-public-methods
        """A fresh, comfortable §6.5 mark."""

        def mark(self) -> tuple[float, bool]:
            """`(net_liq, fresh)`."""
            return 10_000_000.0, True

    clear = _Clear()
    return gate.default_manifest(
        blackout=clear,
        tradability=clear,
        staleness=clear,
        clock_skew=clear,
        in_flight=clear,
        net_liq=_NetLiq(),
        deployable_fraction=0.70,
        survival_safety_pad=0.10,
        coherence_tolerance=1e-6,
    )


def _measure_shape(
    passer: Any, subject: _Subject
) -> tuple[list[tuple[int, int, int, float]], str]:
    """One pass per table size. `(rows, complaint)` — a complaint is never a PASS.

    Split out of `arm_hot_path` so the SHAPE is taken in one place: a reader
    checking that the same pass object and the same order are reused across every
    size — which is what makes the four readings comparable — should not have to
    trace that through the verdict logic beside it.
    """
    seam = subject.seam
    row = seam.PositionRow(
        trade_id="t",
        symbol="ES",
        strategy_id="probe",
        size=1,
        margin=1.0,
        state=seam.PositionState.OPEN,
        stop_distance=20,
    )
    order = _order(seam)
    shape: list[tuple[int, int, int, float]] = []
    for size in TABLE_SIZES:
        table = _counting_positions(tuple(row for _ in range(size)))
        started = time.perf_counter_ns()
        outcome = passer.evaluate(order, _picture(seam, table), 1.0)
        elapsed = (time.perf_counter_ns() - started) / 1000.0
        if outcome.decision is not seam.Decision.APPROVE:
            return [], (
                f"the shipped manifest denied the hot-path probe at |positions|="
                f"{size} via {outcome.rule!r} ({outcome.reason}) — the shape would "
                "be measured over a pass that stopped early"
            )
        tally = table.tally
        shape.append((size, tally.get("traverse", 0), tally.get("len", 0), elapsed))
    return shape, ""


def arm_hot_path(subject: _Subject) -> tuple[list[tuple[str, str]], str, str]:
    """`(defects, evidence, complaint)` — traversal count vs |positions|."""
    gate = subject.gate
    rules = _shipped_manifest(subject)
    if len(rules) < MIN_SHIPPED_RULES:
        return (
            [],
            "",
            (
                f"the shipped manifest holds {len(rules)} rule(s), below the floor of "
                f"{MIN_SHIPPED_RULES} — a shape measured over an almost-empty pass "
                "characterises nothing"
            ),
        )
    phases = {rule.phase for rule in rules}
    if len(phases) < 2:
        return (
            [],
            "",
            (
                "the shipped manifest declares one phase only, so a hot-path shape "
                "over it says nothing about the size-dependent half"
            ),
        )

    shape, complaint = _measure_shape(gate.GatePass(_ClearHalt(), list(rules)), subject)
    if complaint:
        return [], "", complaint

    traversals = [entry[1] for entry in shape]
    evidence = (
        "hot-path shape (|positions|, traversals, len-calls, us): "
        + "; ".join(f"({s}, {t}, {ln}, {us:.1f})" for s, t, ln, us in shape)
        + " — us figures are EVIDENCE ONLY and never an input to this verdict "
        "(CHECK-DEBT D3.39: a control whose verdict is a function of machine load)"
    )
    defects: list[tuple[str, str]] = []
    if any(traversals) or len(set(traversals)) != 1:
        defects.append(
            (
                f"{GATE}:default_manifest",
                (
                    f"the pass TRAVERSES the position table: counts {traversals} at "
                    f"sizes {list(TABLE_SIZES)}. §11.3 keeps Σ open margin, Σ "
                    "reservations, committed and deployable as running aggregates "
                    "precomputed on the snapshot, so a correct pass reads fields and "
                    "never rows — the O(1) claim in §11 is false for this manifest"
                ),
            )
        )
    return defects, evidence, ""


class _ClearHalt:  # pylint: disable=too-few-public-methods
    """A HALT flag that is never set. Used where HALT is not the subject."""

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`."""
        return False, ""


# ---------------------------------------------------------------------------
# ARM 7 — the boot validation that keeps a rule from being silently dropped.
# ---------------------------------------------------------------------------


def arm_boot_validation(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """A manifest the partition would silently DROP must be refused at boot."""
    gate = subject.gate
    seam = subject.seam
    log: list[str] = []
    phase_a = seam.Phase.SIZE_INDEPENDENT
    phase_b = seam.Phase.SIZE_DEPENDENT

    def rule(name: str, phase: Any) -> Any:
        return _RecordingRule(log, name, phase, seam)

    cases: tuple[tuple[str, list[Any], str], ...] = (
        ("an EMPTY manifest", [], "approves every proposal"),
        (
            "a manifest with NO size-dependent rule",
            [rule("a_one", phase_a)],
            "never checks committed margin (§3 phase B)",
        ),
        (
            "a manifest with NO size-independent rule",
            [rule("b_one", phase_b)],
            "never checks HALT-adjacent tradability (§3 phase A)",
        ),
        (
            "a rule declaring a phase that is NOT a Phase member",
            [rule("a_one", phase_a), rule("b_one", phase_b), rule("x", "post-size")],
            (
                "would be dropped by the partition and never evaluated, which looks "
                "exactly like a rule that approved"
            ),
        ),
        (
            "a manifest with DUPLICATE rule names",
            [rule("a_one", phase_a), rule("b_one", phase_b), rule("a_one", phase_a)],
            "makes §3's 'rule named' attribution ambiguous",
        ),
    )
    defects: list[tuple[str, str]] = []
    for label, manifest, why in cases:
        try:
            gate.GatePass(_ClearHalt(), manifest)
        except gate.UndispatchableManifest:
            continue
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            defects.append(
                (
                    BOOT_SITE,
                    (
                        f"{label} raised {type(exc).__name__} rather than UndispatchableManifest: "
                        f"{exc} — the refusal must be the named one so a caller can "
                        "tell a bad manifest from a bad port"
                    ),
                )
            )
            continue
        defects.append(
            (BOOT_SITE, f"{label} was ACCEPTED at boot; such a manifest {why}")
        )
    return defects, ""


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ARM 8 — THE PARTITION IS A PARTITION. Every rule handed in is dispatched
# exactly once. ARC 038 / A (FA-1).
# ---------------------------------------------------------------------------

#: The site ARM 8 names. Separate from `BOOT_SITE` because the defect it finds is
#: not a boot refusal that failed to fire — it is the partition itself losing or
#: duplicating a member.
PARTITION_SITE = f"{GATE}:GatePass.__init__[partition]"


class _PhaseFlipRule:
    """A rule whose `phase` answers a DIFFERENT valid `Phase` on successive reads.

    NOT a hypothetical. `RulePort.phase` is a PROPERTY, so every read is a fresh
    call, and the frozen seam gives it no stability contract — a rule computing its
    phase from a knob, a cache or a clock satisfies the port exactly as written.
    ARM 7's bad-phase case uses a CONSTANT non-`Phase` value, which every read
    agrees on, so it cannot reach this.

    MEASURED, which is why this arm exists: with the partition re-reading
    `rule.phase` after `_validate` had already read it, the read sequence
    `A, B, A` DROPPED this rule from both phases — nine dispatched from a
    ten-rule manifest, a rule that always DENIES never ran, and the pass APPROVED
    and took the reservation — while `A, A, B` put it in BOTH and dispatched it
    TWICE inside §3's one authoritative pass (eleven names from ten rules).
    """

    def __init__(self, log: list[str], name: str, sequence: tuple[Any, ...], seam: Any):
        self._log = log
        self._name = name
        self._sequence = sequence
        self._reads = 0
        self._seam = seam

    @property
    def name(self) -> str:
        """The identifier a denial is reported under."""
        return self._name

    @property
    def phase(self) -> Any:
        """A valid `Phase` on every read, and not the SAME one on every read."""
        self._reads += 1
        return self._sequence[min(self._reads - 1, len(self._sequence) - 1)]

    @property
    def reads(self) -> int:
        """How many times the executor read the declaration. Evidence, not a verdict."""
        return self._reads

    def evaluate(self, order: Any, picture: Any) -> Any:
        """Record the invocation and DENY — so being skipped is visible in the outcome."""
        del order, picture
        self._log.append(self._name)
        return self._seam.RuleVerdict(
            rule=self._name,
            decision=self._seam.Decision.DENY,
            reason="planted denial by the phase-flipping rule",
        )


def arm_partition_is_a_partition(  # pylint: disable=too-many-locals
    subject: _Subject,
) -> tuple[list[tuple[str, str]], str]:
    # R0914: twenty locals, and each is one side of a comparison this arm makes —
    # the handed roster, the dispatched roster, the flip sequence, the outcome, the
    # missing set and the duplicated set. Bundling them into a struct to satisfy a
    # counter would hide which pair disagreed, which is the whole report.
    """Every rule handed to `GatePass` is dispatched EXACTLY ONCE.

    The precondition of every ordering arm above, and none of them can see it: a
    rule DROPPED from both phases produces the same empty phase-B record as a
    correct Phase-A denial, and a rule dispatched twice still runs in the right
    phase. The only observable is CARDINALITY — the dispatch manifest against the
    manifest handed in, and the invocation log against the rule set.

    Both flip directions are driven, because they fail in opposite directions and
    a single sequence would only ever catch one.
    """
    gate = gate_module = subject.gate
    seam = subject.seam
    phase_a = seam.Phase.SIZE_INDEPENDENT
    phase_b = seam.Phase.SIZE_DEPENDENT
    defects: list[tuple[str, str]] = []
    driven = 0
    for label, sequence in (
        ("dropped-from-both", (phase_a, phase_b, phase_a, phase_b, phase_a)),
        ("duplicated-into-both", (phase_a, phase_a, phase_b, phase_a, phase_b)),
    ):
        log: list[str] = []
        base = _scrambled(subject, log)
        flipper = _PhaseFlipRule(log, "phase_flipper", sequence, seam)
        handed = [*base, flipper]
        try:
            passer = gate_module.GatePass(
                _RecordingHalt(log, gate.HALT_RULE, False), handed
            )
        except gate_module.UndispatchableManifest:
            # A boot refusal is a legitimate way to hold this property — the rule
            # never reaches a partition at all. Not a defect; not a measurement of
            # the partition either, so it is not counted as driven.
            continue
        driven += 1
        dispatched = tuple(passer.manifest)
        expected = tuple(rule.name for rule in handed)
        if len(dispatched) != len(expected):
            defects.append(
                (
                    PARTITION_SITE,
                    (
                        f"[{label}] {len(expected)} rule(s) were handed to GatePass and "
                        f"{len(dispatched)} were partitioned into the dispatch manifest "
                        f"{list(dispatched)} after {flipper.reads} read(s) of "
                        "`phase`. §3 fixes ONE authoritative pass over the manifest: a "
                        "rule LOST by the partition never runs and its absence looks "
                        "exactly like an approval, and a rule DUPLICATED by it is "
                        "evaluated twice in a pass the spec calls one"
                    ),
                )
            )
        if sorted(dispatched) != sorted(expected):
            missing = sorted(set(expected) - set(dispatched))
            extra = sorted(name for name in dispatched if dispatched.count(name) > 1)
            defects.append(
                (
                    PARTITION_SITE,
                    (
                        f"[{label}] the dispatch manifest is not the manifest handed "
                        f"in: DROPPED={missing} DUPLICATED={extra}"
                    ),
                )
            )
        outcome = passer.evaluate(_order(seam), _picture(seam), 1.0)
        if flipper.name not in outcome.evaluated:
            defects.append(
                (
                    PARTITION_SITE,
                    (
                        f"[{label}] {flipper.name!r} was in the manifest and does not "
                        f"appear in GateOutcome.evaluated={list(outcome.evaluated)}; it "
                        f"DENIES on every call and the pass returned "
                        f"{outcome.decision} via {outcome.rule!r}"
                    ),
                )
            )
        if tuple(outcome.evaluated).count(flipper.name) > 1:
            defects.append(
                (
                    PARTITION_SITE,
                    (
                        f"[{label}] {flipper.name!r} appears "
                        f"{tuple(outcome.evaluated).count(flipper.name)} times in one "
                        f"pass: evaluated={list(outcome.evaluated)}"
                    ),
                )
            )
    if driven < 1:
        return [], (
            "no flip sequence reached a partition — every one was refused at boot, "
            "so this arm measured the boot validation and not the partition"
        )
    return defects, ""


def _measure(subject: _Subject) -> CheckResult:
    """Every arm, in order. A non-vacuity complaint is CANNOT_MEASURE."""
    floor, complaint = non_vacuity(subject)
    if complaint:
        return _cannot_measure(f"{complaint} (§5.3: an empty scope is never a PASS)")

    defects: list[tuple[str, str]] = []
    for arm in (
        arm_ordering,
        arm_fail_fast,
        arm_halt_first,
        arm_records_agree,
        arm_boot_validation,
        arm_partition_is_a_partition,
    ):
        found, refusal = arm(subject)
        if refusal:
            return _cannot_measure(f"{arm.__name__}: {refusal}")
        defects.extend(found)

    hot, shape_evidence, refusal = arm_hot_path(subject)
    if refusal:
        return _cannot_measure(f"arm_hot_path: {refusal}")
    defects.extend(hot)

    evidence = (
        f"{floor}; manifest handed in scrambled phase order and execution order "
        f"read from the rules' OWN invocation log; {shape_evidence}"
    )
    return result_from_defects(NAME, defects, evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the shipped `GatePass` and read what actually ran. Never repairs."""
    try:
        subject, complaint = load_subject(ctx.nix_home)
        if complaint or subject is None:
            return _cannot_measure(
                complaint
                or f"{GATE}: neither a subject nor a complaint — the gate's own "
                "pre-flight returned nothing, which is never a verdict"
            )
        return _measure(subject)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
