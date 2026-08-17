"""ARC 035 / D — the can-fail suite for the §11 item 7 drift-audit gate.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same
population passing. A demonstration missing the last step shows only that a gate
can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds a
throwaway `nix_home` under `tmp_path` holding a COPY of `scripts/nixrisk/` and the
frozen spec, perturbs the COPY, and drives the SHIPPED gate's own bytes against
it. `scripts/nixrisk/drift_audit.py` is read and never written.

**Every control asserts the REASON** — the site and the named condition — never
the exit code or the status alone (check contract v2 §11). Phase 0.4 of this arc
found that one level down: a privilege probe refused with the right SQLSTATE for
the WRONG object would have read as "correctly refused" over a live second writer.

**Every plant asserts its own anchor exists before mutating.** `str.replace` with
no match is a silent no-op, and a plant that plants nothing produces a red that
reads as a gate which failed to detect (`debug.md` §8 #4). It bit twice in Phase 0
of this arc.

**THE CONTROL PLANT IS THE ONE TO READ.** `test_a_detector_that_FIRES_ON_
EVERYTHING_is_caught_by_the_ZERO_DRIFT_CONTROL` widens `classify` so that every
comparison reports drift. Every plant arm in the gate still passes under it —
that plant makes them all fire — and only the zero-drift control arm reddens.
Without that arm the gate would certify a detector with no discrimination at all,
which is the arc brief's §0a stated in its exact inverse.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_drift_audit as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of `nixrisk` and the frozen spec.

    `.venv` / `.venv-dev` are nowhere near this copy and that is deliberate:
    ARC 035 Phase 0 fixed seven fixtures that each copied 58 MB of `.venv-dev`
    into a shared 31 G tmpfs and produced 234 red tests that were the disk and
    not the code. This fixture copies one package directory and one document.
    """
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    shutil.copy(REPO / SPEC, tmp_path / SPEC)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str, rel: str = gate.AUDIT) -> None:
    """Rewrite the COPIED subject. Fails loudly if the anchor moved."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"anchor appears {text.count(old)} times in {rel}, not once — a plant "
        f"that matches nothing plants nothing: {old!r}"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


# The anchors, spelled once. Each is a real line of the shipped subject.
_MATERIAL_FLOOR_ANCHOR = "MATERIAL_FLOOR: Final[float] = MIN_MARGIN"
_NET_LIQ_MEMBER_ANCHOR = '    NET_LIQ_MARK = "net-liq mark"'
_HALT_CALL_ANCHOR = "            self._halt.set(CAUSE, halt_reason, now=stamp)"
_NOISE_GUARD_ANCHOR = "    if magnitude <= NOISE_FLOOR:\n        return (False, False)"
_PLANE2_EMIT_ANCHOR = "            self._plane2.emit(PLANE2_EVENT, **fields)"
_BALANCE_TRUTH_ANCHOR = "        truth.broker.balance,"
_UNMEASURED_ANCHOR = "        measurable=False,\n        unmeasurable_reason=why,"


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real spec, a real audit, real money
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_DRIVEN() -> None:
    """The credibility floor: every §11 item 3 aggregate driven, real margin, real HALTs.

    **The counts are DERIVED, not typed.** The number of aggregates is whatever
    §11 item 3 currently names, read back through the gate's own parser; the number of
    plant drives is a function of that roster. Re-typing today's six would rot on
    the next ruling — the relation is the property.
    """
    result = _run(REPO)
    names, complaint = gate.spec_aggregates(REPO)
    assert complaint == "", complaint
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert (
        f"§11 item 3 running aggregates {len(names)} parsed at run time"
        in result.evidence
    )
    assert f"{len(names)} independent plant drive(s)" in result.evidence
    # The control ran, and it is what makes the plant arms mean anything.
    assert "zero-drift CONTROL run(s) that wrote NOTHING to either plane" in (
        result.evidence
    )
    # The gate says what it does NOT prove, on every run.
    assert "UNBOUND (D3.51)" in result.evidence


def test_the_SPEC_ROSTER_is_PARSED_and_is_not_a_literal_in_the_gate() -> None:
    """The expected set comes from the frozen document, never from the module."""
    names, complaint = gate.spec_aggregates(REPO)
    assert complaint == ""
    assert len(names) >= gate.MIN_AGGREGATES
    joined = " ".join(names).lower()
    for phrase in ("open margin", "reservations", "bucket exposure", "balance"):
        assert phrase in joined, f"§11 item 3's parse lost {phrase!r}: {names!r}"
    # The gate must not carry the roster AS DATA, and *as data* is the precise
    # word: a phrase quoted in a comment or a docstring explains the parse and
    # cannot change what the gate expects, while the same phrase bound to a name
    # IS the expected set. The distinction is drawn by the AST rather than by a
    # substring scan — an earlier version of this assertion scanned raw bytes and
    # reddened over a comment, which would have pushed the fix toward deleting an
    # explanation instead of a literal.
    #
    # Asserted over the phrases the parser actually returned, never over a list
    # typed here: a hard-coded roster in this file would be the very defect the
    # test forbids, one file over.
    tree = ast.parse(Path(gate.__file__).read_text(encoding="utf-8"))
    bound: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        bound += [
            sub.value
            for sub in ast.walk(node.value)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
        ]
    for phrase in names:
        assert phrase not in bound, (
            f"the gate BINDS the aggregate phrase {phrase!r} to a name; a roster "
            "spelled in the gate is a roster that agrees with the module by "
            "construction rather than with the frozen spec"
        )


def test_an_UNPARSABLE_SPEC_is_CANNOT_MEASURE_and_never_a_PASS(home: Path) -> None:
    """§17: no expected set means no comparison, which is not the same as agreement."""
    spec = home / SPEC
    text = spec.read_text(encoding="utf-8")
    anchor = "**Incremental aggregates**"
    assert anchor in text, "the §11 item 3 anchor moved; this plant would plant nothing"
    spec.write_text(text.replace(anchor, "**Running totals**"), encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "§11 item 3" in result.detail and "did not parse" in result.detail


# --------------------------------------------------------------------------
# PLANTS — each breaks ONE declared property, and the RED must NAME it
# --------------------------------------------------------------------------


def test_a_WIDENED_MATERIAL_FLOOR_is_caught_as_a_MAGIC_NUMBER(home: Path) -> None:
    """The threshold stops being derived ⇒ red, naming `MIN_MARGIN`."""
    _plant(home, _MATERIAL_FLOOR_ANCHOR, "MATERIAL_FLOOR: Final[float] = 1.0e9")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "MATERIAL_FLOOR" in result.site
    assert "reservations.MIN_MARGIN" in result.detail
    assert "magic number" in result.detail
    # BOTH halves of ARM FLOORS fire: the identity comparison against the ledger
    # constant, and the STATIC arm that catches the literal itself. The static
    # half is the one that survives a future edit which happens to type the same
    # number the ledger currently holds — identity would go green over that.
    assert "assigned the literal 1000000000.0" in result.detail
    # NOTE, deliberately NOT asserted: that nothing HALTs any more. This gate's
    # plant magnitudes are DERIVED from the subject's own floor (`MATERIAL_FLOOR
    # * 1000`), so widening the floor widens the plant with it and the escalation
    # still fires. That is the right design for the arm — a plant sized in
    # absolute dollars would silently stop being material the day the floor moved
    # — and it means the declaration, not a downstream consequence, is what
    # catches this mutation. Written down because the absence of that assertion
    # would otherwise read as an oversight.


def test_an_AGGREGATE_that_LEAVES_the_ROSTER_is_caught_in_BOTH_directions(
    home: Path,
) -> None:
    """§11 item 7 says EVERY running aggregate. A renamed member is one fewer."""
    _plant(home, _NET_LIQ_MEMBER_ANCHOR, '    NET_LIQ_MARK = "net liquidation"')
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "Aggregate" in result.site
    # Direction 1: the spec names something the audit no longer declares.
    assert "'net-liq mark'" in result.detail
    assert "not reconciled at all" in result.detail
    # Direction 2: the audit declares something the spec does not name.
    assert "'net liquidation'" in result.detail
    assert "FINDING ABOUT THE SPEC OR THE MODULE" in result.detail


def test_MATERIAL_DRIFT_that_never_reaches_the_SETTER_is_caught(home: Path) -> None:
    """D3.178's shape inside the fix for it: the verb defined and never called."""
    _plant(home, _HALT_CALL_ANCHOR, "            pass  # HALT withheld")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "did NOT set the HALT flag" in result.detail
    assert "a report is not a gate on money" in result.detail


def test_a_detector_that_FIRES_ON_EVERYTHING_is_caught_by_the_ZERO_DRIFT_CONTROL(
    home: Path,
) -> None:
    """Remove the noise floor and EVERY comparison reports drift.

    Every plant arm in the gate still passes under this mutation — a detector
    that fires on everything catches every plant. The zero-drift control is the
    only arm that can see it, and this test is the proof that the control is
    load-bearing rather than decorative.
    """
    _plant(
        home,
        _NOISE_GUARD_ANCHOR,
        "    if magnitude < 0.0:\n        return (False, False)",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "the CONTROL scan found drift over a book where every aggregate agrees" in (
        result.detail
    )
    assert "fires on everything" in result.detail


def test_an_UNSCANNABLE_AGGREGATE_SCORED_AS_AGREEING_is_caught(home: Path) -> None:
    """§17: 'I could not look' must never be spelled the same way as 'they agree'."""
    _plant(
        home,
        _UNMEASURED_ANCHOR,
        "        measurable=True,\n        unmeasurable_reason=why,",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "nix_check_contract.md §17" in result.detail
    assert "the worst available default" in result.detail


def test_a_DRIFT_EVENT_that_lands_on_ONE_PLANE_is_caught(home: Path) -> None:
    """§12.10:751 ticks drift-audit in both columns; Plane 2 survives §12.4."""
    _plant(home, _PLANE2_EMIT_ANCHOR, "            pass  # Plane 2 withheld")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "no Plane-2 line named 'drift_audit'" in result.detail
    assert "§12.10:751 ticks this event in BOTH planes" in result.detail


def test_a_SELF_COMPARISON_is_caught_by_the_SEPARATION_ARM(home: Path) -> None:
    """Compare the running balance with itself and it agrees over any defect.

    This is `check_reservation_lifecycle`'s ARM SIGMA one level up, and it is the
    single most dangerous mutation available: the audit still runs, still writes
    rows for the other aggregates, and reports the balance perfectly healthy for
    ever.
    """
    _plant(home, _BALANCE_TRUTH_ANCHOR, "        running.picture.balance,")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "still report no drift" in result.detail
    assert "'BALANCE'" in result.detail
    assert "wired to a constant or to its own ground truth" in result.detail


def test_a_PLANT_WITH_NO_ANCHOR_FAILS_LOUDLY_rather_than_planting_nothing(
    home: Path,
) -> None:
    """The guard on every plant above, asserted directly (debug.md §8 #4)."""
    with pytest.raises(AssertionError, match="a plant that matches nothing"):
        _plant(home, "this string is not in the subject", "irrelevant")


# --------------------------------------------------------------------------
# THE LAST STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_UNMUTATED_COPY_of_the_same_tree_PASSES(home: Path) -> None:
    """Without the control a red is not attributable to the plant.

    Same fixture, same copy mechanics, same gate bytes, nothing perturbed.
    """
    result = _run(home)
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "zero-drift CONTROL run(s) that wrote NOTHING" in result.evidence


def test_the_SUBJECT_is_never_written_by_this_suite(home: Path) -> None:
    """Doctrine C.8, asserted rather than assumed: production bytes are unchanged."""
    _plant(home, _HALT_CALL_ANCHOR, "            pass  # HALT withheld")
    _run(home)
    assert (REPO / gate.AUDIT).read_text(encoding="utf-8") != (
        (home / gate.AUDIT).read_text(encoding="utf-8")
    )
    assert _HALT_CALL_ANCHOR in (REPO / gate.AUDIT).read_text(encoding="utf-8")
