"""ARC 030 / sub-agent B — the can-fail suite for `checks/check_coldstart.py`.

Structure follows `nix_check_contract.md` §5.1 / `check_reservation_lifecycle`:
non-vacuity FIRST, then plants that must FAIL and NAME their site, then the
plants removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8): every control builds
a throwaway `nix_home` under `tmp_path` holding COPIES of `coldstart.py` and
the frozen `seam.py`, perturbs the COPY, and drives the SHIPPED gate's own
bytes against it.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_coldstart as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "scripts/nixrisk/coldstart.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/__init__.py",
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    for rel in NIXRISK:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    path = home / gate.COLDSTART_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


_REGISTER_GUARD = (
    "        del now  # accepted for call-shape symmetry with the rest of the seam\n"
    "        if not self._admitted:"
)
_MARKET_GUARD = (
    "        tradable, why = self._broker.market_tradable()\n"
    "        if not tradable:\n"
    "            raise ColdStartError("
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_THREE_arms() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "REFUSED attempt" in result.evidence, result.evidence
    assert "flatten-before-register" in result.evidence, result.evidence
    assert "market-tradable guard's two halves" in result.evidence, result.evidence


def test_the_GATE_DECLARES_coldstart_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.COLDSTART_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON


# --------------------------------------------------------------------------
# PLANT 1 — the registration guard removed (always admits)
# --------------------------------------------------------------------------


def test_a_REMOVED_REGISTRATION_GUARD_fails_and_NAMES_the_gate_defect(
    home: Path,
) -> None:
    _plant(
        home,
        _REGISTER_GUARD,
        "        del now  # accepted for call-shape symmetry with the rest of the seam\n"
        "        if False:  # PLANTED: registration guard disabled",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "register[gate]" in result.site, result.site
    assert "did not gate" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — the market-tradable guard removed on flatten_to_flat
# --------------------------------------------------------------------------


def test_a_REMOVED_MARKET_GUARD_fires_into_a_shut_market_and_is_caught(
    home: Path,
) -> None:
    _plant(
        home,
        _MARKET_GUARD,
        "        tradable, why = self._broker.market_tradable()\n"
        "        if False:  # PLANTED: market-tradable guard disabled\n"
        "            raise ColdStartError(",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "market_guard" in result.site, result.site
    assert (
        "fired into a CLOSED market" in result.detail
        or "closed market directly" in result.detail
    ), result.detail


# --------------------------------------------------------------------------
# PLANT 3 — the HALT alert dropped (silent HALT)
# --------------------------------------------------------------------------


def test_a_DROPPED_HALT_ALERT_fails_and_NAMES_the_skipped_alert(home: Path) -> None:
    _plant(
        home,
        "        self._admitted = False\n        self._halt.hold_in_halt(reason)",
        "        self._admitted = False\n        pass  # PLANTED: hold_in_halt never called",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "closed" in result.site, result.site
    assert "HALT alert was skipped" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.COLDSTART_FILE).read_bytes()
    _plant(
        home,
        _REGISTER_GUARD,
        "        del now  # accepted for call-shape symmetry with the rest of the seam\n"
        "        if False:  # PLANTED: registration guard disabled",
    )
    planted = _run(home)
    (home / gate.COLDSTART_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.COLDSTART_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_COLDSTART_MODULE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.COLDSTART_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = sys.modules.get("nixrisk.coldstart")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("nixrisk.coldstart") is real, (
        "the gate left the tmp_path copy of nixrisk.coldstart in sys.modules"
    )
