"""ARC 037 / sub-agent E — the can-fail suite for `check_allocator_weighting.py`.

Non-vacuity first (the real tree reaches a verdict, and a COPY of it reaches the
SAME one), then one plant per arm into a COPY under `tmp_path`, each of which
must FAIL and NAME its site and its reason, then the plant removed and the same
tree back to where it started.

**No plant touches a production artifact** (doctrine C.8). The `home` fixture
copies `scripts/` (minus the test suite, the Crucible and the broker adapters,
none of which the gate imports) and `risks/`, so a plant edits the copy while the
SHIPPED gate's own bytes are driven against it. The real tree is only ever READ.

**The copy is a TREE COPY and not a hand-maintained file list, deliberately.**
This gate imports the Allocator, the risk engine's recovery and supervision
modules, the scoring seam, the state bus and `risk_config`, and the transitive
closure of those moves whenever any of them gains an import. A hand list would go
stale silently and turn every plant below into "cannot load out of /tmp/…",
which reads as a green plant and is the failure mode
`test_check_scoring_consumption.py::test_00` exists to make loud. `test_00` here
closes the same hole from the other side: it requires the COPY to reach the same
status as the real tree before any plant is trusted.

**Every plant is a defect in a SUBJECT, not in the gate's own arithmetic**, and
each leaves a different arm as the only one that notices:

| plant | what it breaks | arm that must catch it |
|---|---|---|
| `_weight_of` pinned to neutral | the weight reaches sizing and moves nothing | weighted size |
| the weight keyword deleted from the call | the wire is built and never called | caller |
| `contention.NEUTRAL_WEIGHT` moved off 1.0 | the FCFS fallback re-sizes | outage |
| the quarantine check removed from `eligibility` | §4:274 unreflected | real cycle |
| the pathway stops folding in the book | §4:281-283's visibility | real cycle |
| `_pairwise` never reports a divergence | the cross-check is decorative | two readers |

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_allocator_weighting as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    CheckResult,
    Context,
    Mode,
    Status,
    guard_owner_defect,
)

#: Directories under `scripts/` the gate never imports. Excluded so the copy is
#: ~4 MB rather than ~19 MB; each is named so a future reader can see that the
#: exclusion is about SIZE and not about hiding a dependency.
SKIP = ("tests", "crucible", "broker", "__pycache__")

WIRING = "scripts/nixalloc/wiring.py"
LIFECYCLE = "scripts/nixalloc/lifecycle.py"
CONTENTION = "scripts/nixalloc/contention.py"


@pytest.fixture
def home(tmp_path: Path) -> Iterator[Path]:
    """A writable COPY of everything the gate imports. The real tree is READ."""
    (tmp_path / "scripts").mkdir()
    for child in sorted((REPO / "scripts").iterdir()):
        if child.name in SKIP:
            continue
        if child.is_dir():
            shutil.copytree(
                child,
                tmp_path / "scripts" / child.name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        else:
            shutil.copy2(child, tmp_path / "scripts" / child.name)
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    yield tmp_path


def _run(home: Path) -> CheckResult:
    """Drive the SHIPPED gate against `home`."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _patch(home: Path, rel: str, old: str, new: str) -> None:
    """Plant one edit into the COPY. Fails loudly if the anchor moved."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"the plant anchor is not unique in {rel} ({text.count(old)} hits) — the "
        "subject moved and this control would silently stop planting anything"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _detail(result: CheckResult) -> str:
    """The site and the reason, so every assertion below names both (§18)."""
    return f"{result.site} :: {result.detail}"


# ===========================================================================
# NON-VACUITY
# ===========================================================================


def test_00_the_COPY_reaches_the_same_verdict_as_the_real_tree(home: Path) -> None:
    """If the copy cannot be measured, every plant below is a green over nothing."""
    real = _run(REPO)
    copied = _run(home)
    assert copied.status is not Status.CANNOT_MEASURE, (
        f"the gate could not measure its own COPY: {_detail(copied)}"
    )
    assert copied.status is real.status, (
        f"the copy reached {copied.status} where the real tree reaches "
        f"{real.status} — the copy is not the subject. copy: {_detail(copied)}"
    )
    assert real.status in (Status.PASS, Status.GUARDED), (
        f"the real tree is not in a measurable state: {_detail(real)}"
    )


def test_a_GUARDED_verdict_names_a_single_dischargeable_arc() -> None:
    """§4.1: a deferral with no owner is the drawer everything awkward goes in."""
    result = _run(REPO)
    if result.status is not Status.GUARDED:
        pytest.skip("SEAM (b) is whole on this tree; the guard has lifted")
    assert guard_owner_defect(result.guard_owner) == "", result.guard_owner
    assert "sub-agent B" in result.detail, result.detail
    assert "RE-DRIVE" in result.detail, (
        f"the guard does not tell the integrator what to do with it: {result.detail}"
    )


def test_every_arm_proves_it_can_fail_on_a_planted_answer() -> None:
    """The controls run on every invocation; this asserts they all bind."""
    label, why = gate.arms_can_fail()
    assert label == "", f"{label} could not fail on a planted answer: {why}"
    assert len(gate._CONTROLS) >= 8, gate._CONTROLS  # pylint: disable=protected-access


# ===========================================================================
# PLANT 1 — the weight reaches sizing and moves nothing
# ===========================================================================


def test_a_weight_pinned_to_NEUTRAL_reddens_the_weighted_size_arm(home: Path) -> None:
    """PLANT: `_weight_of` pinned to the neutral constant."""
    _patch(
        home,
        WIRING,
        "    return float(ranking.weights.get(pair, contention.NEUTRAL_WEIGHT))",
        "    del pair\n    return float(contention.NEUTRAL_WEIGHT)",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "ONE contract count" in result.detail, _detail(result)
    assert "propose_contended[weighted-size]" in result.site, _detail(result)


# ===========================================================================
# PLANT 2 — the wire is built and never called
# ===========================================================================


def test_deleting_the_weight_keyword_from_the_call_site_reddens_the_caller_arm(
    home: Path,
) -> None:
    """PLANT: the dict emptied while `**extra` stays on the call."""
    _patch(
        home,
        WIRING,
        "        extra = {WEIGHT_KWARG: weight} if self._weight_kwarg else {}",
        "        extra: dict[str, float] = {}",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "NO call site" in result.detail, _detail(result)
    assert "built-but-uncalled" in result.detail, _detail(result)


# ===========================================================================
# PLANT 3 — the FCFS fallback stops being neutral
# ===========================================================================


def test_a_non_neutral_FCFS_fallback_reddens_the_outage_arm(home: Path) -> None:
    """PLANT: §6.6:466's structurally neutral fallback re-sizing a position."""
    _patch(home, CONTENTION, "NEUTRAL_WEIGHT = 1.0", "NEUTRAL_WEIGHT = 1.125")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "not exactly 1.0" in result.detail, _detail(result)
    assert "structurally neutral" in result.detail, _detail(result)


# ===========================================================================
# PLANT 4 — §4:274 goes unreflected
# ===========================================================================


def test_removing_the_quarantine_check_reddens_the_real_cycle_arm(
    home: Path,
) -> None:
    """PLANT: §4:272-274 unreflected once the dying rows go flat."""
    _patch(
        home,
        LIFECYCLE,
        "    refuse, detail = _withdrawal_verdict(quarantine, strategy_id)",
        "    refuse, detail = False, ''",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "reads ELIGIBLE" in result.detail, _detail(result)
    assert "NOT auto-resurrected" in result.detail, _detail(result)
    assert "only a proposal is the wire" in result.detail, (
        "the arm reddened on the eligibility RECORD alone — a reader is not the "
        f"wire, and the pathway's own proposal must move too: {_detail(result)}"
    )


def test_a_pathway_that_drops_the_book_reddens_the_real_cycle_arm(
    home: Path,
) -> None:
    """PLANT: the book accepted at the pathway and never reaching the screen."""
    _patch(
        home,
        WIRING,
        "            lifecycle_mod.MirrorLifecycle(mirror, quarantine)",
        "            lifecycle_mod.MirrorLifecycle(mirror)",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "carries NO §4:273 quarantine book" in result.detail, _detail(result)


# ===========================================================================
# PLANT 5 — a scoring outage denies (§6.6:467's forbidden direction)
# ===========================================================================


def test_an_outage_that_DENIES_reddens_the_outage_arm(home: Path) -> None:
    """The hazard, planted where it would actually be written."""
    _patch(
        home,
        WIRING,
        "        ranking = contention.rank(contenders, self._ranking)",
        (
            "        ranking = contention.rank(contenders, self._ranking)\n"
            "        if ranking.is_fallback:\n"
            "            ranking = dataclasses.replace(ranking, ordering=())"
        ),
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "was HALTED" in result.detail, _detail(result)
    assert "<no proposal at all>" in result.detail, (
        "the real cycle read a HALTED GO as some other outcome — a GO that "
        f"produced no report at all is its own fault: {_detail(result)}"
    )
    assert "the SUBJECT raised IndexError" in result.detail, (
        "shipped code that could not complete a GO was filed as an instrument "
        f"failure rather than as a subject defect (§17): {_detail(result)}"
    )


# ===========================================================================
# PLANT 6 — the two-reader disagreement detector goes silent (D3.264)
# ===========================================================================


def test_a_SILENT_disagreement_detector_reddens_the_two_reader_arm(
    home: Path,
) -> None:
    """The detector ARC 036 shipped and never planted a divergence into."""
    _patch(
        home,
        WIRING,
        "        if verdict.winner == head:",
        "        if True:  # planted: the cross-check never reports",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "stayed EMPTY" in result.detail, _detail(result)
    assert "_pairwise" in result.site, _detail(result)


# ===========================================================================
# THE PLANT COMES OUT
# ===========================================================================


def test_the_same_tree_is_green_again_once_the_plant_is_removed(home: Path) -> None:
    """A control that cannot be un-planted proves the copy, not the plant."""
    before = _run(home)
    _patch(home, CONTENTION, "NEUTRAL_WEIGHT = 1.0", "NEUTRAL_WEIGHT = 1.125")
    planted = _run(home)
    _patch(home, CONTENTION, "NEUTRAL_WEIGHT = 1.125", "NEUTRAL_WEIGHT = 1.0")
    after = _run(home)
    assert planted.status is Status.FAIL_NEEDS_OPERATOR, _detail(planted)
    assert after.status is before.status, (
        f"the tree did not return to {before.status} after the plant was "
        f"removed: {_detail(after)}"
    )


# ===========================================================================
# THE SUBJECT IS UNAVAILABLE — §17, never a PASS
# ===========================================================================


def test_an_absent_subject_is_CANNOT_MEASURE_and_never_a_PASS(
    tmp_path: Path,
) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = _run(tmp_path / "nothing-here")
    assert result.status is Status.CANNOT_MEASURE, _detail(result)
    assert "cannot load" in result.detail or "resolved to" in result.detail, _detail(
        result
    )
