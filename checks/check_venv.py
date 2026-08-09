#!/usr/bin/env python3
"""Verify (and, in CORRECT/INSTALL, rebuild) the project virtualenv.

Repairable without root: the engine is stdlib-only and runs from the system
interpreter (§9.5), so it can rebuild the venv it does not run from.
"""

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_venv"


def _interpreter(venv: Path) -> Path:
    return venv / "bin" / "python3"


def _running_from(venv: Path) -> bool:
    """True if the current interpreter lives inside the given venv (§9.5).

    A check rebuilding `.venv` while executing on `.venv`'s own interpreter
    deletes the interpreter beneath itself. The engine invariant is "runs
    from /usr/bin/python3", but nothing stops a human invoking it via
    `.venv/bin/python3 verify.py` by hand — this makes the invariant
    self-enforcing rather than a documented hope.
    """
    try:
        Path(sys.executable).resolve().relative_to(venv.resolve())
    except ValueError:
        return False
    return True


def _probe(python: Path) -> str:
    """Return the venv interpreter's version, or '' if it does not answer."""
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(python), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # fmt: skip
        return ""
    return proc.stdout.strip() or proc.stderr.strip()


def _create(venv: Path) -> str:
    """Build the venv with the stdlib module. Returns '' on success."""
    try:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            [sys.executable, "-m", "venv", str(venv)],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{exc!r}"
    return ""


def run(mode: Mode, ctx: Context) -> CheckResult:
    """Prove the venv answers; rebuild it when permitted."""
    venv = ctx.nix_home / ".venv"
    python = _interpreter(venv)
    version = _probe(python) if python.is_file() else ""
    if version:
        return CheckResult(
            name=NAME, status=Status.PASS, evidence=f"{python}: {version}"
        )
    if mode.rank < Mode.CORRECT.rank:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_REPAIRABLE,
            site=str(venv),
            detail="virtualenv absent or its interpreter does not answer",
        )
    if _running_from(venv):
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=str(venv),
            detail=(
                f"engine is running from {sys.executable}, inside the venv it "
                "would rebuild — re-invoke from the system interpreter "
                "(/usr/bin/python3), not .venv/bin/python3 (§9.5)"
            ),
        )
    failure = _create(venv)
    if failure:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_REPAIRABLE,
            site=str(venv),
            detail=f"venv creation failed: {failure}",
        )
    version = _probe(_interpreter(venv))
    if not version:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_REPAIRABLE,
            site=str(venv),
            detail="venv created but its interpreter still does not answer",
        )
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=f"{_interpreter(venv)}: {version}",
        action=f"created {venv}",
    )


if __name__ == "__main__":
    from nixverify.contract import exit_code_for

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
