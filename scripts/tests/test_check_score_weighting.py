"""ARC 037 / B — the can-fail for the standing gate over §6.6:459's score weight.

Structure follows `nix_check_contract.md` §5.1: NON-VACUITY FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same tree
green. A demonstration missing the last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds
a throwaway `nix_home` under `tmp_path` holding COPIES of `scripts/nixalloc/`,
`scripts/nixrisk/`, `scripts/risk_config.py`, `risks/` and the architect ruling
`downloads/ARC037-SEAM-FREEZE.md`, perturbs the COPY, and drives the SHIPPED
gate against it. The real modules are read and never written, and each plant is
followed in the SAME test by a restore-and-re-run control, so an ambient cause
could not have produced the red.

**Every control asserts the REASON** — the site and the named condition — never
the exit code or the status alone (check contract v2 §11).

THE PLANTS ARE THE DESIGN. Each is one answer to `debug.md` §7.12's standing
question — *what would have to be true for this gate to PASS while measuring
nothing?* — expressed as a change to the subject a reading pass would call
plausible:

  1. the weights are pinned back to `NEUTRAL_WEIGHT` (CHECK-DEBT D3.260's exact
     shape: the ordering still moves, the weighting does not);
  2. the weight is computed, recorded on the rationale, and never multiplied
     into the risk budget — a defect no assertion over `weights` can see;
  3. the clamp is removed, so the bounds become decoration;
  4. a literal is changed away from the architect ruling the freeze fixes;
  5. the weight reaches the MARGIN term — a capital-safety ceiling scaled by a
     performance score, the one defect here that costs money;
  6. the out-of-bounds guard CLAMPS instead of refusing, so a broken caller
     looks correct;
  7. a declared NEUTRAL route stops being neutral, so FCFS re-sizes a race that
     never happened;
  8. the architect ruling itself is removed — a refusal, never a pass.
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

import check_score_weighting as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of every artifact the gate reads."""
    shutil.copytree(REPO / "scripts" / "nixalloc", tmp_path / "scripts" / "nixalloc")
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    shutil.copy2(REPO / "scripts" / "risk_config.py", tmp_path / "scripts")
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    (tmp_path / "downloads").mkdir()
    shutil.copy2(REPO / gate.FREEZE, tmp_path / gate.FREEZE)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> str:
    """Swap one exact fragment in a COPIED file, returning the pristine source.

    The replacement is asserted to have landed AND to be unambiguous. A plant
    that silently matched nothing produces a green that looks like a control
    and proves nothing — the same vacuity this whole file is about, one level
    up.
    """
    path = home / rel
    pristine = path.read_text(encoding="utf-8")
    assert pristine.count(old) == 1, f"plant anchor is not unique in {rel}:\n{old}"
    path.write_text(pristine.replace(old, new, 1), encoding="utf-8")
    return pristine


def _restore(home: Path, rel: str, pristine: str) -> None:
    (home / rel).write_text(pristine, encoding="utf-8")


def _control(home: Path) -> None:
    """§5.1 step 6. Without this a plant only shows the gate CAN go red."""
    result = _run(home)
    assert result.status is Status.PASS, result
    assert "ARCHITECT RULING" in result.evidence, result.evidence


def _red(result, site_contains: str, why_contains: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert site_contains in result.site, result.site
    assert why_contains in result.detail, result.detail


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real subject and the pathway RAN
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_actually_ran() -> None:
    """The credibility floor: the shipped modules, driven, with real numbers."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "distinct contract counts out of the real" in result.evidence
    assert "pinned-to-NEUTRAL_WEIGHT falsifier was driven and caught" in result.evidence
    assert "weight-dropping falsifier was driven and caught" in result.evidence
    assert "each shown OUTSIDE its bound before" in result.evidence
    assert (
        "NOT proven: that any production caller passes a weight" in result.evidence
    ), "a green must never imply the weight is wired in production"


def test_the_COPY_IS_A_REAL_SUBJECT_AND_PASSES_BEFORE_ANY_PLANT(home: Path) -> None:
    """Scope containment (§5.3): the fixture is the thing being perturbed."""
    subject, complaint = gate.load_subject(home)

    assert complaint == "", complaint
    assert subject is not None
    assert subject.contention.__file__.startswith(str(home))
    assert subject.sizing.__file__.startswith(str(home))
    _control(home)


def test_a_TREE_WITHOUT_THE_SUBJECT_IS_CANNOT_MEASURE_NEVER_PASS(
    tmp_path: Path,
) -> None:
    """Doctrine B.2 / §5.3: an absent subject is never a green."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "is not on disk" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE PLANTS — each must FAIL or refuse, NAME its site, then be controlled
# --------------------------------------------------------------------------


def test_a_WEIGHTING_PINNED_BACK_TO_NEUTRAL_fails_naming_the_constant(
    home: Path,
) -> None:
    """PLANT 1 — D3.260 restored: the ordering moves, the weighting does not."""
    pristine = _plant(
        home,
        gate.CONTENTION,
        "    weights = {\n"
        "        pair: weight_for(position, field_size) for pair, position in "
        "ranks.items()\n"
        "    }",
        "    weights = dict.fromkeys(ranks, NEUTRAL_WEIGHT)",
    )

    result = _run(home)

    _red(result, gate.RANK_SITE, "every weight is NEUTRAL_WEIGHT")
    assert "D3.260" in result.detail, result.detail

    _restore(home, gate.CONTENTION, pristine)
    _control(home)


def test_a_weight_COMPUTED_AND_NEVER_APPLIED_fails_on_the_SIZE(home: Path) -> None:
    """PLANT 2 — the defect `weights` cannot see: recorded, never multiplied."""
    pristine = _plant(
        home,
        gate.SIZING,
        "        weighted_risk_usd = knobs.per_trade_risk_usd * weight",
        "        weighted_risk_usd = knobs.per_trade_risk_usd",
    )

    result = _run(home)

    _red(result, gate.SIZE_SITE, "the weight was computed and never applied")
    assert "identical in every input but their RANK" in result.detail, result.detail

    _restore(home, gate.SIZING, pristine)
    _control(home)


def test_a_CLAMP_THAT_DOES_NOT_BIND_fails_at_the_reachable_rank(home: Path) -> None:
    """PLANT 3 — §7.12/3: the bounds become decoration nobody can reach."""
    pristine = _plant(
        home,
        gate.CONTENTION,
        "    return min(WEIGHT_CEILING, max(WEIGHT_FLOOR, _raw_weight(rank, n)))",
        "    return _raw_weight(rank, n)",
    )

    result = _run(home)

    _red(result, gate.TRANSFORM_SITE, "the clamp did not bind")
    assert "1.875" in result.detail, result.detail

    _restore(home, gate.CONTENTION, pristine)
    _control(home)


def test_a_LITERAL_THIS_TREE_CHOSE_FOR_ITSELF_fails_against_the_ruling(
    home: Path,
) -> None:
    """PLANT 4 — §6.6:459 fixes no transform, so the numbers are not ours."""
    pristine = _plant(home, gate.CONTENTION, "WEIGHT_STEP = 0.25", "WEIGHT_STEP = 0.3")

    result = _run(home)

    _red(result, f"{gate.CONTENTION}:WEIGHT_STEP", "the architect ruling in")
    assert gate.FREEZE in result.detail, result.detail
    assert "FROZEN SPEC FIXES NO TRANSFORM" in result.detail, result.detail

    _restore(home, gate.CONTENTION, pristine)
    _control(home)


def test_a_weight_that_reaches_the_MARGIN_CEILING_fails(home: Path) -> None:
    """PLANT 5 — the direction that must not exist, and the one that costs money."""
    pristine = _plant(
        home,
        gate.SIZING,
        "            margin=margin_contracts(headroom, live_margin),",
        "            margin=margin_contracts(headroom * weight, live_margin),",
    )

    result = _run(home)

    _red(result, gate.SIZE_SITE, "the direction that must not exist")
    assert "CAPITAL-SAFETY ceilings" in result.detail, result.detail

    _restore(home, gate.SIZING, pristine)
    _control(home)


def test_a_GUARD_THAT_CLAMPS_INSTEAD_OF_REFUSING_fails(home: Path) -> None:
    """PLANT 6 — a silent clamp makes a broken caller look correct (directive 4)."""
    pristine = _plant(
        home,
        gate.SIZING,
        "    complaint = _weight_complaint(weight)\n    if not complaint:\n"
        "        return float(weight)",
        "    complaint = _weight_complaint(weight)\n    if complaint or not complaint:\n"
        "        return min(WEIGHT_CEILING, max(WEIGHT_FLOOR, float(weight)))",
    )

    result = _run(home)

    _red(result, gate.GUARD_SITE, "was ACCEPTED and sized")
    assert "off a number nobody chose" in result.detail, result.detail

    _restore(home, gate.SIZING, pristine)
    _control(home)


def test_a_NEUTRAL_ROUTE_THAT_STOPS_BEING_NEUTRAL_fails(home: Path) -> None:
    """PLANT 7 — FCFS re-sizing a race that never happened (§6.6:455/466)."""
    pristine = _plant(
        home,
        gate.CONTENTION,
        "        weights={contender.pair: NEUTRAL_WEIGHT for contender in ordered},",
        "        weights={contender.pair: WEIGHT_CEILING for contender in ordered},",
    )

    result = _run(home)

    _red(result, gate.RANK_SITE, "rather than exactly")
    assert "structurally neutral" in result.detail, result.detail

    _restore(home, gate.CONTENTION, pristine)
    _control(home)


def test_the_ARCHITECT_RULING_REMOVED_IS_A_REFUSAL_NOT_A_PASS(home: Path) -> None:
    """§5.3: a gate that cannot read its reference side certifies nothing."""
    (home / gate.FREEZE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "arm_frozen_literals" in result.detail, result.detail
    assert "is absent under" in result.detail, result.detail


def test_a_RULING_WHOSE_SEAM_B_SECTION_MOVED_IS_A_REFUSAL(home: Path) -> None:
    """§7.12/2: an empty expected set agrees with anything, so it must refuse."""
    doc = home / gate.FREEZE
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("## SEAM (b)", "## SEAM (b-old)", 1),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "holds no '## SEAM (b)' section" in result.detail, result.detail
