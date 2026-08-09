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
    """True if the current interpreter belongs to the given venv (§9.5).

    A check rebuilding `.venv` while executing on `.venv`'s own interpreter
    deletes the interpreter beneath itself. The engine invariant is "runs
    from /usr/bin/python3", but nothing stops a human invoking it via
    `.venv/bin/python3 verify.py` by hand — this makes the invariant
    self-enforcing rather than a documented hope.

    `venv/bin/python3` is a symlink to the system interpreter in every real
    venv, so `Path(sys.executable).resolve()` chases it straight back out
    to e.g. `/usr/bin/python3.14` — the exact opposite of what "inside the
    venv" means here. Two signals instead, either sufficient:

    1. `sys.prefix` is the venv root itself for any process running under a
       venv's interpreter, and is not derived by resolving the interpreter
       path, so it never chases that symlink.
    2. Containment of the *unresolved* executable path under the venv
       directory — a second, independent signal for layouts where
       `sys.prefix` is unusual.
    """
    try:
        venv_resolved = venv.resolve()
        if Path(sys.prefix).resolve() == venv_resolved:
            return True
        return venv_resolved in Path(sys.executable).absolute().parents
    except OSError:
        return False


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
    except OSError, subprocess.SubprocessError:
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
