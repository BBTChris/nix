"""ARC 031 / B — the can-fail for the standing gate over the Allocator's sizing.

Structure follows `nix_check_contract.md` §5.1: NON-VACUITY FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same tree
green. A demonstration missing the last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds
a throwaway `nix_home` under `tmp_path` holding COPIES of `scripts/nixalloc/`,
`scripts/nixrisk/`, `scripts/risk_config.py` and `risks/`, perturbs the COPY,
and drives the SHIPPED gate against it. The real
`scripts/nixalloc/sizing.py` is read and never written, and each plant is
followed in the SAME test by a restore-and-re-run control, so an ambient cause
could not have produced the red.

**Every control asserts the REASON** — the site and the named condition — never
the exit code or the status alone (check contract v2 §11). Each plant asserts on
the specific sentence its arm emits, so a red produced by a different arm cannot
be mistaken for the one being demonstrated.

THE PLANTS ARE THE DESIGN. Each is one answer to `debug.md` §7.12's standing
question — *what would have to be true for this gate to PASS while measuring
nothing?* — expressed as a change to the subject a reading pass would call
plausible:

  1. the fast-drop runs AFTER the mirror read (the defect whose PROPOSAL is
     byte-identical to a correct pass — same outcome, same reason, same zero);
  2. `committed` is re-derived from the position rows rather than read from the
     published snapshot (the correction U2 exists to make);
  3. an invalid stop intent is sized anyway instead of denied;
  4. the slippage pad falls out of the dollar-risk denominator;
  5. the fulls branch of the single-instrument rule becomes unreachable, so the
     rule is only ever exercised on one side;
  6. the order carries a margin figure that is not the published row's, so the
     gate — which divides by the ORDER's copy — is on a different number;
  7. the deployable fraction is carved into the module instead of read from the
     one file that owns it.
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

import check_allocator_sizing as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of every module the gate loads."""
    shutil.copytree(REPO / "scripts" / "nixalloc", tmp_path / "scripts" / "nixalloc")
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    shutil.copy2(REPO / "scripts" / "risk_config.py", tmp_path / "scripts")
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _subject(home: Path) -> Path:
    return home / gate.SIZING


def _plant(home: Path, old: str, new: str) -> str:
    """Swap one exact fragment in the COPY, returning the pristine source.

    The replacement is asserted to have landed. A plant that silently matched
    nothing produces a green that looks like a control and proves nothing — the
    same vacuity this whole file is about, one level up.
    """
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    assert old in pristine, f"plant fragment not found in {gate.SIZING}:\n{old}"
    path.write_text(pristine.replace(old, new, 1), encoding="utf-8")
    return pristine


def _restore(home: Path, pristine: str) -> None:
    _subject(home).write_text(pristine, encoding="utf-8")


def _control(home: Path) -> None:
    """§5.1 step 6. Without this a plant only shows the gate CAN go red."""
    result = _run(home)
    assert result.status is Status.PASS, result
    assert "OWN arithmetic recorders" in result.evidence, result.evidence


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real subject and the pass RAN
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_actually_ran() -> None:
    """The credibility floor: the shipped module, driven, with both branches."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "OWN arithmetic recorders, not from source order" in result.evidence
    assert "sizes-first falsifier was driven and caught" in result.evidence
    assert "both fulls and micros branches reached" in result.evidence
    assert "correlation-bucket cap was NOT exercised" in result.evidence, (
        "a green must never imply §7 bucket-cap coverage this gate does not have"
    )


def test_the_COPY_IS_A_REAL_SUBJECT_AND_PASSES_BEFORE_ANY_PLANT(home: Path) -> None:
    """Scope containment (§5.3): the fixture is the thing being perturbed."""
    subject, complaint = gate.load_subject(home)

    assert complaint == "", complaint
    assert subject is not None
    assert subject.sizing.__file__.startswith(str(home)), subject.sizing.__file__
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


def test_a_FASTDROP_THAT_RUNS_AFTER_THE_MIRROR_READ_fails(home: Path) -> None:
    """PLANT 1 — the defect whose PROPOSAL is byte-identical to a correct pass."""
    pristine = _plant(
        home,
        "        drop = self._fast_drop(strategy_id, symbol)\n"
        "        if drop is not None:\n"
        "            return drop\n"
        "        snapshot = self._mirror.snapshot()\n",
        "        snapshot = self._mirror.snapshot()\n"
        "        drop = self._fast_drop(strategy_id, symbol)\n"
        "        if drop is not None:\n"
        "            return drop\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "a dead signal ran" in result.detail, result.detail
    assert "sized before it was known to be dead" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_COMMITTED_RE_DERIVED_FROM_THE_POSITION_ROWS_fails(home: Path) -> None:
    """PLANT 2 — §16 U2's correction undone: the aggregate recomputed downstream."""
    pristine = _plant(
        home,
        "    return deployable_pct * picture.balance - picture.committed",
        "    return deployable_pct * picture.balance - sum(\n"
        "        r.margin for r in picture.positions\n"
        "    )",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.ARITH_SITE in result.site, result.site
    assert "one source of truth, lost" in result.detail, result.detail
    assert "row(s) out of the position table" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_an_INVALID_STOP_THAT_IS_SIZED_ANYWAY_fails(home: Path) -> None:
    """PLANT 3 — §15 C3: the Allocator must not manufacture a size to deny."""
    pristine = _plant(
        home,
        "        if stop_ticks <= 0:",
        "        if stop_ticks <= -(10**9):",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "must not manufacture a size to make it deniable" in result.detail

    _restore(home, pristine)
    _control(home)


def test_a_SLIPPAGE_PAD_DROPPED_FROM_THE_DENOMINATOR_fails(home: Path) -> None:
    """PLANT 4 — §7:481: `risk_$` is honest only if sized against stop + slippage."""
    pristine = _plant(
        home,
        "    return max(0, stop_ticks + slippage_pad_ticks) * tick_value",
        "    del slippage_pad_ticks\n    return max(0, stop_ticks) * tick_value",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.ARITH_SITE in result.site, result.site
    assert "the pad is not inside" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_SINGLE_INSTRUMENT_RULE_WITH_ONE_UNREACHABLE_BRANCH_refuses(
    home: Path,
) -> None:
    """PLANT 5 — §7.12 route 6, made concrete: the fulls branch becomes dead code.

    The verdict here is CANNOT_MEASURE rather than FAIL, and deliberately so:
    a rule whose second branch never fires has not been shown WRONG, it has been
    shown UNMEASURED, and `nix_check_contract.md` §5.3 makes an empty scope a
    refusal rather than a pass. What matters for §0e is that the shipped bytes
    stop producing a green.
    """
    pristine = _plant(
        home,
        "        whole_fulls >= knobs.micro_full_threshold\n"
        "        and quant_error <= knobs.quant_tolerance",
        "        whole_fulls < 0\n        and quant_error <= knobs.quant_tolerance",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "arm_single_instrument" in result.detail, result.detail
    assert "has two branches" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_an_ORDER_CARRYING_A_MARGIN_THAT_IS_NOT_THE_PUBLISHED_ROWS_fails(
    home: Path,
) -> None:
    """PLANT 6 — the gate divides by the ORDER's copy, so the copy must be the row."""
    pristine = _plant(
        home,
        "                margin_per_contract=terms.margin_per_contract,",
        "                margin_per_contract=terms.margin_per_contract * 2,",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.SITE in result.site, result.site
    assert "the two readers are on different numbers" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_DEPLOYABLE_FRACTION_CARVED_INTO_THE_MODULE_fails(home: Path) -> None:
    """PLANT 7 — §12A owns the number; a second physical home can disagree."""
    pristine = _plant(
        home,
        "        headroom = headroom_usd(picture, knobs.deployable_pct)",
        "        headroom = 0.70 * picture.balance - picture.committed",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.CONFIG_SITE in result.site, result.site
    assert "carved deployable fraction" in result.detail, result.detail

    _restore(home, pristine)
    _control(home)


def test_a_KNOB_HOME_REMOVED_IS_A_REFUSAL_NOT_A_PASS(home: Path) -> None:
    """§5.3 again: the knob arm cannot certify a file it could not read."""
    (home / "risks" / "limiter.config.json").unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "arm_knob_is_read" in result.detail, result.detail
    assert "is absent" in result.detail, result.detail
