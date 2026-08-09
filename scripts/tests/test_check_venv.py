"""Venv check — the first repairable check (§3)."""

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"


def _run(mode: Mode, home: Path) -> CheckResult:
    loaded = load_check(CHECKS, "check_venv")
    assert loaded.run is not None, loaded.load_error
    return loaded.run(mode, Context(nix_home=home, mode=mode))


def test_passes_against_the_real_venv() -> None:
    """PASS against this repo's own real venv, with evidence recorded."""
    result = _run(Mode.VERIFY, REPO)
    assert result.status is Status.PASS
    assert "python" in result.evidence.lower()


def test_missing_venv_in_verify_mode_reports_without_repairing(
    tmp_path: Path,
) -> None:
    """VERIFY never mutates — it only reports."""
    result = _run(Mode.VERIFY, tmp_path)
    assert result.status is Status.FAIL_REPAIRABLE
    assert str(tmp_path / ".venv") in result.site
    assert not (tmp_path / ".venv").exists()
    assert result.action == ""


def test_correct_mode_creates_the_venv(tmp_path: Path) -> None:
    """CORRECT builds an absent venv and reports the repair in `action`."""
    result = _run(Mode.CORRECT, tmp_path)
    assert result.status is Status.PASS
    assert (tmp_path / ".venv" / "bin" / "python3").exists()
    assert "created" in result.action


def test_correct_mode_is_idempotent(tmp_path: Path) -> None:
    """§4: INSTALL/CORRECT never force-rebuild a correct component."""
    _run(Mode.CORRECT, tmp_path)
    marker = tmp_path / ".venv" / "marker.txt"
    marker.write_text("preserved", encoding="utf-8")
    result = _run(Mode.CORRECT, tmp_path)
    assert result.status is Status.PASS
    # `marker` surviving does not by itself prove no rebuild happened — a bare
    # `python -m venv` (no --clear) on an existing directory would leave it
    # untouched either way. `action == ""` is the assertion that actually
    # detects an unconditional rebuild; see task-8-report.md's mutation test.
    assert marker.read_text(encoding="utf-8") == "preserved"
    assert result.action == ""


def test_correct_mode_refuses_to_rebuild_its_own_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.5: the engine must never rebuild the venv it is running from.

    Simulates the engine having been invoked as `.venv/bin/python3
    verify.py` against a degraded venv: sys.executable resolves inside the
    very venv CORRECT would otherwise rebuild.
    """
    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    fake_python = venv / "bin" / "python3"
    fake_python.write_text("", encoding="utf-8")  # present but does not answer
    monkeypatch.setattr(sys, "executable", str(fake_python))

    result = _run(Mode.CORRECT, tmp_path)

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert result.site == str(venv)
