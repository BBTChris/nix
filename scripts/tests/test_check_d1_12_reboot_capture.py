"""ARC 030 / sub-agent B — can-fail suite for `checks/check_d1_12_reboot_capture.py`.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same
tree passing again.

No plant touches `scripts/d1_12_reboot_capture.py` in place (doctrine C.8):
every control builds a throwaway `nix_home` under `tmp_path` holding a COPY.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(REPO / "checks"))

import check_d1_12_reboot_capture as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir(parents=True)
    shutil.copy(REPO / gate.CAPTURE_FILE, tmp_path / gate.CAPTURE_FILE)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    path = home / gate.CAPTURE_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


_WHO_ANCHOR = (
    "    if who_rc != 0:\n"
    '        reasons.append(f"`who` did not run (rc={who_rc}); login state unverifiable")\n'
    "    elif who_out:\n"
    '        reasons.append(f"a user was logged in at capture: {who_out!r}")'
)

_UNITS_ANCHOR = 'for unit in ("nix-xvfb.service", "nix-ibgateway.service"):'


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "who-blind falsifier" in result.evidence, result.evidence


def test_the_GATE_DECLARES_the_script_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.CAPTURE_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False


# --------------------------------------------------------------------------
# PLANT 1 — the `who` check dropped from operator-presence
# --------------------------------------------------------------------------


def test_a_DROPPED_WHO_CHECK_fails_and_NAMES_the_defect(home: Path) -> None:
    _plant(
        home,
        _WHO_ANCHOR,
        "    if who_rc != 0:\n"
        "        pass  # PLANTED: who-logged-in case dropped\n"
        "    elif False:\n"
        "        reasons.append('unreachable')",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "observe_operator_presence" in result.site, result.site
    assert "untouched=False" in result.detail or "untouched=True" in result.detail, (
        result.detail
    )


# --------------------------------------------------------------------------
# PLANT 2 — the unit names regress to the pre-ARC-020 unprefixed spelling
# --------------------------------------------------------------------------


def test_UNPREFIXED_UNIT_NAMES_fail_and_NAME_the_regression(home: Path) -> None:
    _plant(
        home,
        _UNITS_ANCHOR,
        'for unit in ("xvfb.service", "ibgateway.service"):  # PLANTED: ARC 020 regression',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "capture[units]" in result.site, result.site
    assert "not-found" in result.detail or "unexpected unit name" in result.detail, (
        result.detail
    )


# --------------------------------------------------------------------------
# THE THIRD STEP — plant removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.CAPTURE_FILE).read_bytes()
    _plant(
        home,
        _UNITS_ANCHOR,
        'for unit in ("xvfb.service", "ibgateway.service"):  # PLANTED: ARC 020 regression',
    )

    planted = _run(home)
    (home / gate.CAPTURE_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.CAPTURE_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_MODULE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.CAPTURE_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "not present under" in result.detail, result.detail


def test_the_GATE_NEVER_LEAKS_THE_TMP_PATH_COPY_INTO_sys_modules(home: Path) -> None:
    """`load()` uses `spec_from_file_location` and never registers the loaded
    module under its bare name — a plant on a copy must not contaminate any
    later `import d1_12_reboot_capture` a DIFFERENT check or test performs."""
    sys.modules.pop(gate.CAPTURE_MODULE, None)

    _run(home)

    assert gate.CAPTURE_MODULE not in sys.modules, (
        "the gate registered the tmp_path copy under the bare module name"
    )
