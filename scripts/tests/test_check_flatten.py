"""ARC 030 / sub-agent B — the can-fail suite for `checks/check_flatten.py`.

Structure follows `nix_check_contract.md` §5.1 / the `check_reservation_lifecycle`
precedent: non-vacuity FIRST (the real tree passes), then plants that must FAIL
and NAME their site, then the plants removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of `flatten.py` and its
frozen collaborators (`seam.py`, `picture.py`, `reservations.py`,
`broker_seam.py`), perturbs the COPY, and drives the SHIPPED gate's own bytes
against it. `scripts/nixrisk/flatten.py` is read and never written by this suite.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# missing-function-docstring: the helpers below are named after what they do
# to one file (`_run`, `_plant`) and a docstring would restate the name. Added
# ARC 037/A: measured PRE-EXISTING on the untouched tree (pylint exit 16 over
# this file alone), surfaced by an unrelated one-line change bringing the file
# into a commit's hook scope.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_flatten as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "scripts/nixrisk/flatten.py",
    # ARC 037 (D3.220): flatten.py imports the realized-P&L arithmetic, so a
    # scratch tree without it cannot import the subject at all.
    "scripts/nixrisk/realized.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/reservations.py",
    "scripts/nixrisk/__init__.py",
)
BROKER = ("scripts/broker/broker_seam.py",)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the executor and its frozen seams."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in NIXRISK + BROKER:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    """Rewrite the COPIED flatten.py. Fails loudly if the anchor moved."""
    path = home / gate.FLATTEN_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# The precedence guard the reverse-ordering arm depends on — a real line of the
# shipped executor.
_DISCRETIONARY_GUARD = (
    "        prior = self._closed.get(target.trade_id)\n"
    "        if prior is not None:\n"
    "            if authority is CloseAuthority.DISCRETIONARY:"
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_FOUR_arms() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "zero-wire fire" in result.evidence, result.evidence
    assert "dual-authority precedence" in result.evidence, result.evidence
    assert "onset-cancel" in result.evidence, result.evidence
    assert "reconcile-then-publish" in result.evidence, result.evidence


def test_the_GATE_DECLARES_flatten_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.FLATTEN_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the exit path is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


# --------------------------------------------------------------------------
# PLANT 1 — zero-wire: couple the exit to the wire
# --------------------------------------------------------------------------


def test_a_WIRE_COUPLED_FIRE_fails_and_NAMES_the_wire_dependency(home: Path) -> None:
    """Publishing before flattening reddens the zero-wire arm: the dead sink
    raises before the broker is ever reached."""
    _plant(
        home,
        "        if trigger in _R4_TRIGGERS:",
        "        self._picture.publish(self._picture.current())\n"
        "        if trigger in _R4_TRIGGERS:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "fire[zero-wire]" in result.site, result.site
    assert "wire dependency" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — precedence: the discretionary-cannot-override guard removed
# --------------------------------------------------------------------------


def test_a_REMOVED_PRECEDENCE_GUARD_fails_and_NAMES_the_reverse_ordering(
    home: Path,
) -> None:
    """With the DISCRETIONARY guard gone, a discretionary close arriving after a
    protective one for the same trade EXECUTES and overwrites the winner — the
    exact hazard §4's 'protective always wins' forbids."""
    _plant(
        home,
        _DISCRETIONARY_GUARD,
        "        prior = self._closed.get(target.trade_id)\n"
        "        if False:  # PLANTED: discretionary guard disabled\n"
        "            if authority is CloseAuthority.DISCRETIONARY:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "precedence-reverse" in result.site, result.site
    assert "must be DROPPED" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — onset: collapse HALT_ONSET to a bare CANCEL
# --------------------------------------------------------------------------


def test_an_ONSET_CAUSE_COLLAPSED_TO_CANCEL_fails_and_NAMES_the_wrong_cause(
    home: Path,
) -> None:
    """SPEC-A7: booking a HALT-onset release under a shared CANCEL erases which
    onset released the capital. The plant forces every onset release via CANCEL."""
    # ARC 038 / C (FC1): the release is now inside a `try:` in
    # `cancel_entries_on_onset` — a persistence failure out of `resolve` may not
    # abort the sweep (§3:172 cancels ALL pending entries) — so the anchor gained
    # one indent level. `_plant` asserts the anchor appears exactly once, so a
    # stale anchor reddens LOUDLY rather than planting nothing, which is why this
    # was caught by the suite and not by a reviewer.
    _plant(
        home,
        "                resolution = self._ledger.resolve(\n"
        "                    entry.client_order_id, cause, now, reason=cause.value\n"
        "                )",
        "                resolution = self._ledger.resolve(\n"
        "                    entry.client_order_id, TerminalPath.CANCEL, now, "
        "reason=cause.value\n"
        "                )",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "onset" in result.site, result.site
    assert "released via" in result.detail, result.detail
    assert "not HALT_ONSET" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 — reconcile-then-publish: publish the pre-flatten INTENT
# --------------------------------------------------------------------------


def test_RECONCILE_PUBLISHING_THE_INTENT_fails_and_NAMES_the_wrong_balance(
    home: Path,
) -> None:
    """A `reconcile_and_publish` that commits the pre-flatten projection balance
    instead of broker truth reddens the confirmed-state arm."""
    _plant(
        home,
        "        realized_delta = balance.cash - projection.balance\n"
        "        rows = self._confirmed_rows(projection, held_symbols)\n"
        "\n"
        "        picture = self._picture.commit(\n"
        "            balance=balance.cash,",
        "        realized_delta = balance.cash - projection.balance\n"
        "        rows = self._confirmed_rows(projection, held_symbols)\n"
        "\n"
        "        picture = self._picture.commit(\n"
        "            balance=projection.balance,  # PLANTED: publishes the intent",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "reconcile_and_publish" in result.site, result.site
    assert "broker truth" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.FLATTEN_FILE).read_bytes()
    _plant(
        home,
        _DISCRETIONARY_GUARD,
        "        prior = self._closed.get(target.trade_id)\n"
        "        if False:  # PLANTED: discretionary guard disabled\n"
        "            if authority is CloseAuthority.DISCRETIONARY:",
    )
    planted = _run(home)
    (home / gate.FLATTEN_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.FLATTEN_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent subject is not agreement
# --------------------------------------------------------------------------


def test_an_ABSENT_FLATTEN_MODULE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.FLATTEN_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = sys.modules.get("nixrisk.flatten")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("nixrisk.flatten") is real, (
        "the gate left the tmp_path copy of nixrisk.flatten in sys.modules"
    )
