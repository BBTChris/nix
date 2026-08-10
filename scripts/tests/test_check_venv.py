"""Venv check — the first repairable check (§3)."""

import subprocess
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

    Builds a REAL venv so `bin/python3` is a genuine symlink to the system
    interpreter, exactly as every real venv is. A guard built on
    `Path.resolve()` alone follows that symlink straight out of the venv to
    e.g. `/usr/bin/python3.14` and never notices it was "inside" anything —
    this is the bug the guard exists to catch, so the fixture must model
    the real filesystem shape or the test proves nothing. (An earlier
    version of this test replaced the symlink with a plain file to force a
    probe failure — that destroys the exact symlink-escaping shape the
    guard has to survive and made the test pass against the buggy code for
    the wrong reason.)

    The venv's answer is broken by re-pointing the symlink at a
    *nonexistent* target rather than removing the symlink — it stays a
    symlink (`is_symlink()` True) but is dangling (`exists()` False), so
    the probe still fails and CORRECT still reaches the rebuild path, while
    `Path.resolve()` still chases it to a path outside the venv exactly as
    a live symlink would. `sys.prefix`/`sys.executable` are monkeypatched
    to simulate the engine having been invoked as `.venv/bin/python3
    verify.py` against its own degraded venv.
    """
    venv = tmp_path / ".venv"
    subprocess.run(  # nosec B603 - fixed argv, shell=False, test fixture
        [sys.executable, "-m", "venv", str(venv)],
        check=True,
        timeout=300,
    )
    interpreter = venv / "bin" / "python3"
    assert interpreter.is_symlink(), "fixture must model the real venv symlink layout"

    interpreter.unlink()
    interpreter.symlink_to("/nonexistent/python3")
    assert interpreter.is_symlink()
    assert not interpreter.exists()  # dangling: probe fails, resolve() still escapes

    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(sys, "executable", str(interpreter))

    result = _run(Mode.CORRECT, tmp_path)

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert result.site == str(venv)
    # Direct proof the venv was not rebuilt, not an inference from status —
    # a reordering that reached _create() before this guard would still
    # report FAIL_NEEDS_OPERATOR-shaped-looking failures in other ways, but
    # would not leave the fixture's exact dangling symlink untouched.
    assert interpreter.is_symlink()
    assert interpreter.readlink() == Path("/nonexistent/python3")
    assert not interpreter.exists()


def test_correct_mode_rebuilds_when_running_from_the_system_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The self-rebuild guard must not block legitimate repair.

    Models the correct, expected invocation shape explicitly (rather than
    relying on however this test happens to be invoked) — engine running
    from the system interpreter, against an unrelated tmp_path venv — and
    asserts CORRECT actually rebuilds it. A guard that fires too eagerly
    here would block all real repair, which is a worse failure than the
    self-rebuild bug it exists to prevent.
    """
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(sys, "prefix", "/usr")

    result = _run(Mode.CORRECT, tmp_path)

    assert result.status is Status.PASS
    assert "created" in result.action
    assert (tmp_path / ".venv" / "bin" / "python3").exists()


def test_running_from_fails_closed_when_location_is_undeterminable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLAUDE.md directive 4: fail closed and loud.

    An OSError from Path.resolve() (permission denied on an intermediate
    component, ELOOP on a symlink cycle) must make the guard *refuse*, not
    *permit*. The two costs are asymmetric: refusing wrongly costs the
    operator a re-invocation; permitting wrongly rebuilds the interpreter
    executing the check — the exact catastrophe the guard exists to
    prevent. "I cannot tell where I am running from" must resolve toward
    "assume I am running from the venv", never the opposite.

    Path.resolve() is deliberately non-strict and, verified directly, does
    not raise for either a symlink cycle or a permission-denied
    intermediate directory on this system (`os.path.realpath`'s
    best-effort design swallows both). Contriving a real filesystem
    condition that reliably raises is impractical, so this patches
    Path.resolve directly to force the branch under test — applied only
    after load_check() has already imported the module (loader.py itself
    calls path.resolve() while locating the check file).
    """
    loaded = load_check(CHECKS, "check_venv")
    assert loaded.run is not None, loaded.load_error

    def _raise(self: Path, *_args: object, **_kwargs: object) -> Path:
        raise OSError(f"simulated: cannot resolve {self}")

    monkeypatch.setattr(Path, "resolve", _raise)

    result = loaded.run(Mode.CORRECT, Context(nix_home=tmp_path, mode=Mode.CORRECT))

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert result.site == str(tmp_path / ".venv")
    assert not (tmp_path / ".venv").exists()  # refused before ever attempting _create()


def test_probe_timeout_is_cannot_measure_not_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 9 review, Finding 3 (§4.1): a timeout means we could not tell
    whether the interpreter answers — it might be fine but slow or hung.
    Collapsing that into "broken" (FAIL_REPAIRABLE) would send --correct
    into a venv rebuild against an interpreter that may be perfectly
    healthy. Only a genuine exec failure (missing/non-executable
    interpreter) is a correct FAIL — that path is untouched by this test.
    """
    loaded = load_check(CHECKS, "check_venv")
    assert loaded.run is not None, loaded.load_error
    import check_venv as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    interpreter = venv / "bin" / "python3"
    interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    interpreter.chmod(0o755)

    def _timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(cmd="python3", timeout=15)

    monkeypatch.setattr(mod.subprocess, "run", _timeout)

    result = loaded.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))

    assert result.status is Status.CANNOT_MEASURE
