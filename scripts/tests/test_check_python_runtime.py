"""First real check: the floor, which cannot repair itself (§3)."""

import subprocess
import sys
from pathlib import Path

from nixverify.contract import Context, Mode, Status
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"


def _ctx(mode: Mode = Mode.VERIFY) -> Context:
    """Build a Context rooted at the real repo, for the given mode."""
    return Context(nix_home=REPO, mode=mode)


def test_passes_on_this_interpreter_with_evidence() -> None:
    """PASS on the interpreter running the test, with evidence recorded."""
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.run is not None, loaded.load_error
    result = loaded.run(Mode.VERIFY, _ctx())
    assert result.status is Status.PASS
    assert str(sys.version_info.major) in result.evidence


def test_reports_needs_operator_when_below_floor(monkeypatch) -> None:
    """§4.1: verify.py cannot apt-install its own interpreter."""
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.run is not None
    import check_python_runtime as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(mod, "MINIMUM", (99, 0))
    result = mod.run(Mode.CORRECT, _ctx(Mode.CORRECT))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert result.site


def test_standalone_invocation_honours_the_exit_contract() -> None:
    """§4.2: the module is independently runnable."""
    proc = subprocess.run(
        [sys.executable, str(CHECKS / "check_python_runtime.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_declares_user_privilege_and_is_not_disruptive() -> None:
    """Metadata reflects §4/§8: this check is user-privileged, non-disruptive."""
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.privilege == "user"
    assert loaded.disruptive is False
    assert loaded.interactive is False
