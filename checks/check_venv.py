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

    On `OSError` (permission denied on an intermediate component, a symlink
    cycle) the two possible mistakes are not symmetric: refusing wrongly
    costs the operator a re-invocation from the system interpreter;
    permitting wrongly rebuilds the interpreter executing this check — the
    exact catastrophe this guard exists to prevent (CLAUDE.md directive 4,
    fail closed and loud). So an inability to determine where we are
    running from must be treated as "assume we are running from it" and
    return `True`, never `False` — do not "simplify" this back to `False`.
    """
    try:
        venv_resolved = venv.resolve()
        if Path(sys.prefix).resolve() == venv_resolved:
            return True
        return venv_resolved in Path(sys.executable).absolute().parents
    except OSError:
        return True


def _probe(python: Path) -> str | None:
    """Return the venv interpreter's version.

    `''` means the interpreter would not execute at all — genuinely
    broken, a correct FAIL_REPAIRABLE. `None` means a timeout: we could
    not tell whether it answers, which is not evidence that it is broken
    (§4.1, Task 9 review Finding 3) — the interpreter might be fine but
    slow or hung. `check=False` means the only exceptions this can raise
    are an exec failure (OSError, e.g. missing/non-executable file) or a
    timeout (subprocess.TimeoutExpired, a SubprocessError); a nonzero exit
    code does not raise here, so the two exception types map cleanly onto
    the two distinct meanings.
    """
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(python), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    except OSError:
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


def run(  # pylint: disable=too-many-return-statements
    mode: Mode, ctx: Context
) -> CheckResult:
    """Prove the venv answers; rebuild it when permitted.

    Eight returns is eight sequential guard clauses (probe once, act on
    what it said; rebuild if permitted; probe again, act on that), not
    branching complexity — each one a distinct, named outcome the check
    contract requires (§4.1's five statuses, hit from two probe sites).
    Collapsing them into fewer returns would trade a linear, easy-to-audit
    shape for nested conditionals around a security-relevant repair path.
    """
    venv = ctx.nix_home / ".venv"
    python = _interpreter(venv)
    version = _probe(python) if python.is_file() else ""
    if version:
        return CheckResult(
            name=NAME, status=Status.PASS, evidence=f"{python}: {version}"
        )
    if version is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"{python}: probe timed out — could not measure (§4.1)",
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
    if version is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"{_interpreter(venv)}: created, but the post-build probe "
            "timed out — could not measure (§4.1)",
        )
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


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
if __name__ == "__main__":  # pylint: disable=duplicate-code
    from nixverify.contract import exit_code_for

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
