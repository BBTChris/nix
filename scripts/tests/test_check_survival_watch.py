"""ARC 030 / sub-agent B — the can-fail suite for `checks/check_survival_watch.py`.

Structure follows `nix_check_contract.md` §5.1 / `check_reservation_lifecycle`:
non-vacuity FIRST, then plants that must FAIL and NAME their site, then the
plants removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8): every control builds
a throwaway `nix_home` under `tmp_path` holding COPIES of `survival.py` and its
frozen collaborators (`seam.py`, `picture.py`), perturbs the COPY, and drives
the SHIPPED gate's own bytes against it.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Each test's NAME states the property it drives, which is this suite's
# whole convention; a docstring restating the name would be the second
# spelling of one fact. Pre-existing across this file and surfaced only
# when ARC 031 changed it — pylint runs per changed file.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_survival_watch as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "scripts/nixrisk/survival.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
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
    path = home / gate.SURVIVAL_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


_LATCH_ANCHOR = (
    "        if self._fired:\n"
    "            return WatchOutcome(reading, breached=True, fired=False, source=source)"
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_THREE_arms() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "non-conflation" in result.evidence, result.evidence
    assert "re-fire latch" in result.evidence, result.evidence
    assert "uniform broker-authoritative reconcile" in result.evidence, result.evidence


def test_the_GATE_DECLARES_survival_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.SURVIVAL_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON


# --------------------------------------------------------------------------
# PLANT 1 — conflate the breach predicate onto CASH instead of NET_LIQ
# --------------------------------------------------------------------------


def test_a_CASH_CONFLATED_BREACH_PREDICATE_fails_and_NAMES_the_field(
    home: Path,
) -> None:
    _plant(
        home,
        "        reading = self.read()\n        breached = reading.breached\n",
        "        reading = self.read()\n"
        "        breached = reading.cash < reading.floor  # PLANTED: cash, not net_liq\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "nonconflation" in result.site, result.site
    assert "not reading net_liq" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — the re-fire latch removed
# --------------------------------------------------------------------------


def test_a_REMOVED_LATCH_fires_on_EVERY_breach_and_is_caught(home: Path) -> None:
    _plant(
        home,
        _LATCH_ANCHOR,
        "        if False:  # PLANTED: latch disabled\n"
        "            return WatchOutcome(reading, breached=True, fired=False, source=source)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "breach_latch" in result.site, result.site
    assert "did not suppress" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — drift correction booked as CRITICAL instead of WARNING
# --------------------------------------------------------------------------


def test_a_DRIFT_BOOKED_CRITICAL_fails_and_NAMES_the_tier_collapse(home: Path) -> None:
    _plant(
        home,
        "            Alert(\n"
        "                tier=AlertTier.WARNING,\n"
        "                event=DRIFT_EVENT,",
        "            Alert(\n"
        "                tier=AlertTier.CRITICAL,  # PLANTED: tier collapsed\n"
        "                event=DRIFT_EVENT,",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "reconcile" in result.site, result.site
    assert (
        "expected exactly 1 Warning alert on drift, got 0" in result.detail
        or "tiers collapsed" in result.detail
    ), result.detail


# --------------------------------------------------------------------------
# PLANT 4 — the monotonic-by-source guard removed
# --------------------------------------------------------------------------


def test_a_REMOVED_MONOTONIC_GUARD_APPLIES_a_stale_poll_and_is_caught(
    home: Path,
) -> None:
    _plant(
        home,
        "        if self._last_venue_ts is not None and venue_ts <= self._last_venue_ts:",
        "        if False:  # PLANTED: monotonic guard disabled",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "stale" in result.site, result.site
    assert "applied" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.SURVIVAL_FILE).read_bytes()
    _plant(
        home,
        _LATCH_ANCHOR,
        "        if False:  # PLANTED: latch disabled\n"
        "            return WatchOutcome(reading, breached=True, fired=False, source=source)",
    )
    planted = _run(home)
    (home / gate.SURVIVAL_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.SURVIVAL_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_SURVIVAL_MODULE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.SURVIVAL_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = sys.modules.get("nixrisk.survival")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("nixrisk.survival") is real, (
        "the gate left the tmp_path copy of nixrisk.survival in sys.modules"
    )


# ==========================================================================
# CHECK-DEBT D3.124 (ARC 031) — a name-based import measures the LIVE tree
# ==========================================================================


def test_an_EMPTY_tree_is_CANNOT_MEASURE_and_was_a_PASS_before_this_guard(
    tmp_path: Path,
) -> None:
    """The defect, and it was live and shipped until ARC 031 Stage 3.

    `checks/_preamble.py` appends the REAL repository's `scripts/` to
    `sys.path` permanently, so `importlib.import_module("nixrisk.survival")`
    walks past the empty `home/scripts` this gate inserts and finds the live
    module. Measured directly, in a fresh interpreter against a fresh empty
    directory: this gate returned **PASS over a tree containing nothing**.
    """
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, (
        f"an empty tree produced {result.status!r} — if this is PASS the gate "
        f"is measuring the live repository again: {result.evidence}"
    )
    assert "resolved OUTSIDE" in (result.detail or ""), result.detail
    assert "D3.124" in (result.detail or ""), result.detail


def test_the_provenance_guard_ACCEPTS_a_real_copied_tree(home: Path) -> None:
    """The guard must not reject the honest case, or it would be a blanket refusal."""
    result = _run(home)
    assert result.status is Status.PASS, result.detail
    module, error = gate.load(home)
    assert module is not None, error
    assert str(home) in str(Path(module.survival.__file__ or "").resolve())
