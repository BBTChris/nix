#!/usr/bin/env python3
"""Verify the Python interpreter meets the floor.

Floor component (VERIFY-AND-CHECKS.md §3): install.sh owns installation, so
this check detects drift and reports FAIL_NEEDS_OPERATOR — it never attempts
a repair it cannot perform.
"""

from __future__ import annotations

import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_python_runtime"

MINIMUM = (3, 14)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Compare the running interpreter against the floor."""
    actual = sys.version_info[:2]
    version = f"{actual[0]}.{actual[1]}.{sys.version_info.micro}"
    if actual >= MINIMUM:
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=f"sys.version_info={version} at {sys.executable}",
        )
    wanted = f"{MINIMUM[0]}.{MINIMUM[1]}"
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site=f"{sys.executable} (python {version})",
        evidence=f"sys.version_info={version}",
        detail=f"need >= {wanted}; verify.py cannot install its own interpreter "
        f"— re-run install.sh",
    )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.contract import exit_code_for, validate_result

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
