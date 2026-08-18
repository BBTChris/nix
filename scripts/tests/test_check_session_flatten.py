"""ARC 033 / Stage 1 / B — the can-fail suite for `checks/check_session_flatten.py`.

Structure follows `nix_check_contract.md` §5.1 / the `check_flatten` precedent:
non-vacuity FIRST (the real tree passes), then plants that must FAIL and NAME
their site, then the plants removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of `session.py`, its
collaborators and `risks/`, perturbs the COPY, and drives the SHIPPED gate's own
bytes against it. Nothing under `scripts/nixrisk/` or `risks/` is written.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# missing-function-docstring: the declaration controls are named after the
# declaration they read; a docstring would restate the name.

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_session_flatten as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/session.py",
    "scripts/nixrisk/flatten.py",
    # ARC 037 (D3.220): flatten.py imports the realized-P&L arithmetic, so a
    # scratch tree without it cannot import the subject at all.
    "scripts/nixrisk/realized.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/reservations.py",
    "scripts/nixrisk/survival.py",
    "scripts/nixrisk/wal.py",
)
BROKER = ("scripts/broker/broker_seam.py",)
SCRIPTS = ("scripts/risk_config.py",)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the scheduler, its seams and risks/."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in NIXRISK + BROKER + SCRIPTS:
        source = REPO / rel
        if source.is_file():
            shutil.copy(source, tmp_path / rel)
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str, rel: str = gate.SESSION_FILE) -> None:
    """Rewrite a COPIED source file. Fails loudly if the anchor moved."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_PASSES_and_the_EVIDENCE_names_every_arm(home: Path) -> None:
    """A plant suite over a gate that never passes proves only that it fails."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "ACROSS itself" in result.evidence, result.evidence
    assert "ACTUALLY HALTED" in result.evidence, result.evidence
    assert "INVERTED per-symbol pair" in result.evidence, result.evidence
    assert "reason=session" in result.evidence, result.evidence


def test_the_GATE_DECLARES_its_SUBJECTS_so_coverage_is_real() -> None:
    assert gate.SESSION_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CONFIG_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, (
        "the §6.1b backstop is never edited into agreement"
    )
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


def test_an_ABSENT_SUBJECT_is_CANNOT_MEASURE_never_PASS(tmp_path: Path) -> None:
    """§17: a safety property proven while its subject is unavailable is not proven.

    The interesting half is WHY it cannot measure. `sys.path` in this process
    already carries the canonical tree, so an empty `nix_home` does not produce
    an `ImportError` — it produces a SUCCESSFUL import of the SHIPPED module,
    which would have made the gate drive one file while naming another. The
    origin check catches exactly that and says which path it got.
    """
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "is OUTSIDE" in result.detail, result.detail
    assert "not the one named" in result.detail, result.detail
    assert "§17" in result.detail, result.detail


def test_a_TRULY_ABSENT_TREE_with_NO_FALLBACK_is_also_CANNOT_MEASURE(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other unavailability: no importable subject anywhere. Still not a PASS."""
    # Derived from REPO, never a literal path: `debug.md` §7.4 — the tree moves
    # (a worktree, another operator's home) and a hard-coded root rots silently.
    canonical = str(REPO / "scripts")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != canonical])
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "§17" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 1 — the deadline never arrives
# --------------------------------------------------------------------------


def test_a_DEADLINE_THAT_NEVER_ARRIVES_is_caught_by_the_DEADLINE_arm(
    home: Path,
) -> None:
    """The arm's whole reason for existing: an idle scheduler must not be green."""
    _plant(
        home,
        "        if at < deadline:",
        "        if True:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:deadline" in result.site, result.site
    assert "expected FLAT_CONFIRMED" in result.detail, result.detail


def test_a_DEADLINE_THAT_ALWAYS_FIRES_is_caught_by_the_SAME_arm(home: Path) -> None:
    """The other direction: a scheduler that flattens on every tick is not a
    deadline, and the PRE-deadline half of the drive is what sees it."""
    _plant(
        home,
        "        if at < deadline:",
        "        if False:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:deadline" in result.site, result.site
    assert "BEFORE the deadline" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — §6.1b:352's reason is dropped
# --------------------------------------------------------------------------


def test_a_DROPPED_SESSION_REASON_reddens_and_NAMES_the_word(home: Path) -> None:
    """§6.1b:352 fixes the word the strategy receives. A derived one is not it."""
    _plant(home, 'SESSION_REASON = "session"', 'SESSION_REASON = "flatten"')

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:deadline" in result.site, result.site
    assert "§6.1b:352 fixes the word" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — the §12.6 honesty clause, defeated three ways
# --------------------------------------------------------------------------


def test_FIRING_INTO_A_HALTED_VENUE_reddens_and_NAMES_the_GUARD(home: Path) -> None:
    """§4:231-235 — the system does not fire orders into a shut market."""
    _plant(
        home,
        "        if venue is not VenueState.TRADABLE:",
        "        if False:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:halted" in result.site, result.site
    assert "market-tradable guard" in result.detail, result.detail


def test_a_PHANTOM_SUCCESS_over_a_POSITION_THE_BROKER_STILL_HOLDS_reddens(
    home: Path,
) -> None:
    """ARC 022's F13, planted directly: the verdict follows the CALL, not truth.

    `_verdict_after_fire` is rewritten to ignore broker truth entirely. This is
    the specific defect this stage was asked to make impossible, and the control
    is that the gate SEES it.
    """
    _plant(
        home,
        "    still_held = any(row.symbol == symbol for row in confirmed.picture.positions)",
        "    still_held = False",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:halted" in result.site, result.site
    assert "indeterminate path resolving to NOT flat" in result.detail, result.detail


def test_COLLAPSING_THE_RIDING_VERDICT_TO_INFO_reddens_and_NAMES_the_TIER(
    home: Path,
) -> None:
    """§6.1b:353 — failure paths land in the existing CRITICAL machinery."""
    _plant(
        home,
        "        return AlertTier.CRITICAL if self.exposure_rides else AlertTier.INFO",
        "        return AlertTier.INFO",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:halted" in result.site, result.site
    assert "expected CRITICAL" in result.detail, result.detail


def test_DROPPING_THE_RESIDUAL_RISK_SENTENCE_reddens(home: Path) -> None:
    """§12.6 requires the residual risk be documented honestly, on the outcome."""
    _plant(
        home,
        '            residual_risk=_RESIDUAL_RISK.get(verdict, ""),',
        '            residual_risk="",',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:halted" in result.site, result.site
    assert "states NO residual risk" in result.detail, result.detail


def test_COLLAPSING_THE_TWO_RIDING_VERDICTS_INTO_ONE_reddens(home: Path) -> None:
    """'Never sent' and 'sent and ignored' are different operator actions."""
    _plant(
        home,
        "        return SessionFlattenVerdict.EXPOSURE_RIDES_UNCONFIRMED",
        "        return SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "session.py:halted" in result.site, result.site
    assert "collapse to one verdict" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 — the boot validator stops judging per symbol
# --------------------------------------------------------------------------


def test_a_VALIDATOR_THAT_STOPPED_JUDGING_PER_SYMBOL_reddens(home: Path) -> None:
    """§6.1b:348 — config validation rejects any PER-SYMBOL set violating it.

    The plant neuters exactly the widening: the override maps are read as empty,
    so only the global pair is judged, and the inverted ES row loads.
    """
    _plant(
        home,
        "    lead_overrides = _override(cfg, _LEAD_BY_SYMBOL)",
        "    lead_overrides = {}",
        rel="scripts/risk_config.py",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ordering.session_flatten_before_eod_blackout" in result.site, result.site
    assert "INVERTED per-symbol pair" in result.detail, result.detail
    assert "LOADED" in result.detail, result.detail


def test_a_REJECTION_THAT_DOES_NOT_NAME_THE_SYMBOL_reddens(home: Path) -> None:
    """'the config is invalid' is not an operator instruction (doctrine C.2)."""
    _plant(
        home,
        'f"symbol {symbol}: session_flatten_lead_min={lead} is not < "',
        'f"the ordering invariant is violated; lead={lead} is not < "',
        rel="scripts/risk_config.py",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ordering.session_flatten_before_eod_blackout" in result.site, result.site
    assert "does not NAME the symbol" in result.detail, result.detail


def test_REMOVING_THE_PER_SYMBOL_OVERRIDE_MAP_reddens_the_CONFIG_arm(
    home: Path,
) -> None:
    """A per-symbol invariant with no per-symbol HOME is not validated.

    The map is legitimately EMPTY on the shipped tree (deviations only), so the
    plant DELETES the key rather than emptying it — the difference between "no
    symbol deviates" and "there is nowhere for a deviation to live" is the whole
    point, and a gate that confused them would redden the shipped config.
    """
    path = home / "risks" / "limiter.config.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["session_flatten_lead_min_by_symbol"]
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "carries no session_flatten_lead_min_by_symbol map" in result.detail, (
        result.detail
    )
    assert "PER SYMBOL" in result.detail, result.detail


def test_an_EMPTY_OVERRIDE_MAP_is_the_SHIPPED_SHAPE_and_still_PASSES(
    home: Path,
) -> None:
    """The other direction, and it matters: empty is not a defect.

    A gate that required rows would push an operator to write five copies of the
    global default into the override table — the restatement directive 3 forbids
    — just to keep the instrument quiet.
    """
    path = home / "risks" / "limiter.config.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["session_flatten_lead_min_by_symbol"] == {}, "the fixture is not shipped"

    assert _run(home).status is Status.PASS


# --------------------------------------------------------------------------
# THE PLANTS REMOVED — the same tree passes again
# --------------------------------------------------------------------------


def test_the_SAME_TREE_PASSES_ONCE_the_PLANT_IS_REMOVED(home: Path) -> None:
    """Closes the loop: the reds above are the plant's, not the fixture's."""
    _plant(home, "        if at < deadline:", "        if True:")
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR

    _plant(home, "        if True:", "        if at < deadline:")

    assert _run(home).status is Status.PASS
