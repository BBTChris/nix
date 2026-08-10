"""Unit wiring per VERIFY-AND-CHECKS.md §8, §9.5."""

from pathlib import Path

import pytest  # pylint: disable=import-error

UNITS = Path("/etc/systemd/system")


def _text(name: str) -> str:
    path = UNITS / name
    if not path.is_file():
        pytest.skip(f"{name} not installed on this host")
    return path.read_text(encoding="utf-8")


def test_boot_unit_uses_the_system_interpreter() -> None:
    """§9.5: running from .venv breaks the check that rebuilds .venv."""
    text = _text("nix-verify.service")
    assert "/usr/bin/python3" in text
    assert ".venv/bin/python3" not in text


def test_boot_unit_points_at_the_relocated_engine() -> None:
    """Task 6 moved the engine from ~/nix/verify.py to scripts/verify.py."""
    assert "/home/bbt/nix/scripts/verify.py" in _text("nix-verify.service")


def test_boot_unit_is_unprivileged_and_not_in_maintenance() -> None:
    """§8: a boot can happen mid-session — no disruptive repair."""
    text = _text("nix-verify.service")
    assert "User=bbt" in text
    assert "--privilege user" in text
    assert "--maintenance" not in text


def test_root_unit_runs_as_root_with_maintenance() -> None:
    """§8: the weekly window is where disruptive repairs are permitted."""
    text = _text("nix-verify-root.service")
    assert "User=" not in text or "User=root" in text
    assert "--privilege root" in text
    assert "--maintenance" in text


def test_root_timer_is_saturday_0300_chicago() -> None:
    """Outside any session per the risk spec's no-new-entry window."""
    text = _text("nix-verify-root.timer")
    assert "Sat" in text
    assert "03:00" in text
    assert "America/Chicago" in text
