"""ARC 028 / A4 — the can-fail for the standing gate over the Limiter's pass.

Structure follows `nix_check_contract.md` §5.1: NON-VACUITY FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same
population passing. A demonstration missing the last step shows only that a gate
can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds
a throwaway `nix_home` under `tmp_path` holding a COPY of `scripts/nixrisk/`,
perturbs the COPY's `gate.py`, and drives the SHIPPED gate against it. The real
`scripts/nixrisk/gate.py` is read and never written, and each plant is followed
in the SAME test by a restore-and-re-run control, so an ambient cause could not
produce the red.

**Every control asserts the REASON** — the site and the named condition — never
the exit code or the status alone (check contract v2 §11). Each plant below
asserts on the specific sentence its arm emits, so a red produced by a different
arm cannot be mistaken for the one being demonstrated.

THE PLANTS ARE THE DESIGN. Each is one answer to `debug.md` §7.12's standing
question — *what would have to be true for this gate to PASS while measuring
nothing?* — expressed as a change to the subject that a reading pass would call
plausible:

  1. the executor iterates the manifest in SOURCE order (the defect whose output
     is byte-identical to a correct pass);
  2. a denial does not halt dispatch (§5's global fail-fast gone);
  3. the HALT flag is read after phase A rather than first (§11.5);
  4. a size-dependent rule re-derives an aggregate by SUMMING THE POSITION TABLE
     (§11.3's running aggregates ignored) — the O(1) claim, refuted as a shape;
  5. the executor records a rule it never dispatched (the bookkeeping this gate
     otherwise trusts);
  6. the boot validation that stops a rule being silently dropped is removed.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_limiter_gate as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of the real `scripts/nixrisk/` package."""
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _subject(home: Path) -> Path:
    return home / gate.GATE


def _plant(home: Path, old: str, new: str) -> str:
    """Swap one exact fragment in the COPY, returning the pristine source.

    The replacement is asserted to have landed. A plant that silently matched
    nothing produces a green that looks like a control and proves nothing — the
    same vacuity this whole file is about, one level up.
    """
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    assert old in pristine, f"plant fragment not found in {gate.GATE}:\n{old}"
    path.write_text(pristine.replace(old, new, 1), encoding="utf-8")
    return pristine


def _restore(home: Path, pristine: str) -> None:
    _subject(home).write_text(pristine, encoding="utf-8")


def _control(home: Path) -> None:
    """§5.1 step 6. Without this a plant only shows the gate CAN go red."""
    result = _run(home)
    assert result.status is Status.PASS, result
    assert "phase-A" in result.evidence and "phase-B" in result.evidence, (
        result.evidence
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real subject and the pass RAN
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_actually_ran() -> None:
    """The credibility floor: a real pass, both phases, and the shape measured."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "4 phase-A + 3 phase-B" in result.evidence, result.evidence
    assert "hot-path shape (|positions|, traversals, len-calls, us)" in result.evidence
    for size in gate.TABLE_SIZES:
        assert f"({size}, 0, " in result.evidence, (
            f"|positions|={size} is missing from the shape measurement — an O(1) "
            f"claim taken at fewer than {len(gate.TABLE_SIZES)} sizes is not a shape"
        )


def test_the_MANIFEST_IS_HANDED_IN_A_DIFFERENT_ORDER_THAN_IT_RUNS(home: Path) -> None:
    """Scope containment (§5.3): the arm's discriminating power is real.

    If the handed order equalled the observed order, ARM 1 would be satisfied by
    an executor that merely iterates the list — the implementation it exists to
    reject. This asserts the scramble is a scramble, from the gate's own fixture.
    """
    subject, complaint = gate.load_subject(home)
    assert complaint == "", complaint
    assert subject is not None

    log: list[str] = []
    rules = gate._scrambled(subject, log)  # pylint: disable=protected-access
    handed = [rule.name for rule in rules]
    gate._drive(subject, rules, log)  # pylint: disable=protected-access
    ran = [name for name in log if name != subject.gate.HALT_RULE]

    assert handed != ran, handed
    assert handed[0].startswith("b_"), handed
    assert ran[0].startswith("a_"), ran


# --------------------------------------------------------------------------
# THE PLANTS — each must FAIL, NAME its site, and be followed by its control
# --------------------------------------------------------------------------


def test_an_executor_that_RUNS_THE_MANIFEST_IN_SOURCE_ORDER_fails(home: Path) -> None:
    """PLANT 1 — the defect whose output is byte-identical to a correct pass."""
    pristine = _plant(
        home,
        # RE-POINTED, ARC 038 / A (FA-1). The partition it names moved when
        # `_validate` began RETURNING the phase it read so the partition could
        # stop re-reading `rule.phase` — a re-read that could drop a rule from
        # both phases or place it in both. The PLANT is unchanged in meaning (the
        # executor runs the manifest in source order); only the fragment it
        # swaps is re-pointed, which is the D3.189 hazard of a plant keyed to a
        # source literal, handled by re-pointing rather than by loosening.
        "        self._phase_a = tuple(\n"
        "            rule\n"
        "            for rule, phase in zip(rules, declared, strict=True)\n"
        "            if phase is Phase.SIZE_INDEPENDENT\n"
        "        )\n"
        "        self._phase_b = tuple(\n"
        "            rule\n"
        "            for rule, phase in zip(rules, declared, strict=True)\n"
        "            if phase is Phase.SIZE_DEPENDENT\n"
        "        )",
        "        self._phase_a = tuple(rules)\n        self._phase_b = ()",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "executed at position" in result.detail, result.detail
    assert "AFTER size-DEPENDENT rule" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_DENIAL_THAT_DOES_NOT_HALT_DISPATCH_fails_and_names_fail_fast(
    home: Path,
) -> None:
    """PLANT 2 — §5: 'first deny halts all further dispatch'."""
    pristine = _plant(
        home,
        "            if verdict.decision is Decision.DENY:\n"
        "                return _Dispatch(\n"
        "                    outcome=GateOutcome(\n"
        "                        decision=Decision.DENY,\n"
        "                        rule=rule.name,\n"
        "                        reason=verdict.reason,\n"
        "                        phase=phase,\n"
        "                        evaluated=tuple(evaluated),\n"
        "                    )\n"
        "                )\n",
        "            if verdict.decision is Decision.DENY:\n                continue\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "executed AFTER the denial by 'a_two'" in result.detail, result.detail
    assert "first deny halts all further dispatch" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_HALT_READ_THAT_IS_NOT_FIRST_fails_and_names_the_position(
    home: Path,
) -> None:
    """PLANT 3 — §11.5's 'first atomic read in pre-gate', moved behind phase A."""
    pristine = _plant(
        home,
        "        evaluated: list[str] = [HALT_RULE]\n"
        "        halted, why = self._halt.is_set()\n",
        "        evaluated: list[str] = [HALT_RULE]\n"
        "        for _probe in self._phase_a:\n"
        "            _probe.evaluate(order, picture)\n"
        "        halted, why = self._halt.is_set()\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "not FIRST" in result.detail, result.detail
    assert "first atomic read in the pre-gate" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_RULE_THAT_SUMS_THE_POSITION_TABLE_fails_and_reports_a_LINEAR_SHAPE(
    home: Path,
) -> None:
    """PLANT 4 — §11.3's running aggregates re-derived on the hot path.

    This is the one plant whose finding is a SHAPE rather than an event: the
    counts must track the table sizes, which is what makes the O(1) claim
    falsifiable rather than decorative. The pass still APPROVES — the plant does
    not change a single verdict — so nothing but the shape can see it.
    """
    pristine = _plant(
        home,
        "        room = cap - picture.committed\n",
        "        room = cap - picture.committed - sum(\n"
        "            row.margin for row in picture.positions\n"
        "        )\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"{gate.GATE}:default_manifest" in result.site, result.site
    assert "the pass TRAVERSES the position table" in result.detail, result.detail
    assert str(list(gate.TABLE_SIZES)) in result.detail, result.detail
    assert f"counts {list(gate.TABLE_SIZES)}" in result.detail, (
        "the reported traversal counts must EQUAL the table sizes — a linear "
        f"shape. Got: {result.detail}"
    )

    _restore(home, pristine)
    _control(home)


def test_an_EXECUTOR_THAT_RECORDS_A_RULE_IT_NEVER_RAN_fails(home: Path) -> None:
    """PLANT 5 — the bookkeeping every other arm reads, caught by the second record."""
    pristine = _plant(
        home,
        "        binding: RuleVerdict | None = None\n        for rule in rules:\n",
        "        binding: RuleVerdict | None = None\n"
        "        if rules:\n"
        '            evaluated.append("phantom_rule")\n'
        "        for rule in rules:\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "phantom_rule" in result.detail, result.detail
    assert "is not what ran" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_MANIFEST_WITH_A_MISSING_PHASE_ACCEPTED_AT_BOOT_fails(home: Path) -> None:
    """PLANT 6 — the boot refusal that stops a rule being silently dropped."""
    pristine = _plant(
        home,
        "        for phase in Phase:\n",
        "        for phase in ():\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.BOOT_SITE in result.site, result.site
    assert "was ACCEPTED at boot" in result.detail, result.detail
    assert "never checks committed margin" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent or unloadable subject is not agreement
# --------------------------------------------------------------------------


def test_an_ABSENT_GATE_MODULE_is_CANNOT_MEASURE_and_names_the_missing_path(
    home: Path,
) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    _subject(home).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.GATE in result.detail, result.detail
    assert "nothing to drive" in result.detail, result.detail


def test_a_GATE_MODULE_THAT_WILL_NOT_IMPORT_is_CANNOT_MEASURE_naming_the_error(
    home: Path,
) -> None:
    """A broken subject is unknown, never green — and the REASON is named."""
    _subject(home).write_text("this is not python(", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "would not import" in result.detail, result.detail
    assert "SyntaxError" in result.detail, result.detail


def test_a_PASS_THAT_NEVER_REACHES_THE_END_OF_THE_MANIFEST_is_CANNOT_MEASURE(
    home: Path,
) -> None:
    """Non-vacuity, planted: an ordering claim over a pass that stopped early.

    The plant makes branch 0 deny unconditionally, so ARM 0's unobstructed drive
    returns DENY after one branch. Every ordering arm below it would then be
    reasoning about a pass that dispatched nothing, and the honest verdict is
    'unknown' — not a PASS, and not a FAIL naming an ordering defect that was
    never observed (doctrine B.2).
    """
    pristine = _plant(
        home,
        "        halted, why = self._halt.is_set()\n        if halted:\n",
        "        halted, why = self._halt.is_set()\n"
        '        halted, why = True, "planted unconditional halt"\n'
        "        if halted:\n",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "instead of APPROVE" in result.detail, result.detail
    assert "an empty scope is never a PASS" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


# --------------------------------------------------------------------------
# THE THIRD STEP — every plant gone, the same population passing
# --------------------------------------------------------------------------


def test_the_SAME_COPIED_TREE_passes_once_every_plant_is_gone(home: Path) -> None:
    """Without this the gate is only known to be able to fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "decision approve" in result.evidence, result.evidence


def test_the_GATE_DECLARES_the_module_as_a_SUBJECT_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent."""
    assert gate.GATE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the frozen spec is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"
    assert len(gate.TABLE_SIZES) >= 3, (
        "an O(1) claim needs a SHAPE across at least three input sizes; fewer "
        "cannot distinguish a constant from a line"
    )


def test_LOADING_A_SUBJECT_LEAVES_sys_modules_AND_sys_path_AS_IT_FOUND_THEM(
    home: Path,
) -> None:
    """The declared `interpreter:*` claims are transient, and that is checkable.

    A loader that left the tmp tree on `sys.path` would silently shadow the
    repo's own `nixrisk` for every later check in the same process — and the
    plant tests above would then all be driving whichever tree loaded first.
    """
    before_path = list(sys.path)
    before_mods = sorted(k for k in sys.modules if k.startswith("nixrisk"))

    subject, complaint = gate.load_subject(home)

    assert complaint == "", complaint
    assert subject is not None
    assert sys.path == before_path
    assert sorted(k for k in sys.modules if k.startswith("nixrisk")) == before_mods
