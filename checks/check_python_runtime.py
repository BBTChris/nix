#!/usr/bin/env python3
"""Verify the Python interpreter meets the floor.

Floor component (VERIFY-AND-CHECKS.md §3): install.sh owns installation, so
this check detects drift and reports FAIL_NEEDS_OPERATOR — it never attempts
a repair it cannot perform.
"""

from __future__ import annotations

import sys

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

MINIMUM = (3, 14)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Compare the running interpreter against the floor."""
    actual = sys.version_info[:2]
    version = f"{actual[0]}.{actual[1]}.{sys.version_info.micro}"
    if actual >= MINIMUM:
        return CheckResult(
            name="check_python_runtime",
            status=Status.PASS,
            evidence=f"sys.version_info={version} at {sys.executable}",
        )
    wanted = f"{MINIMUM[0]}.{MINIMUM[1]}"
    return CheckResult(
        name="check_python_runtime",
        status=Status.FAIL_NEEDS_OPERATOR,
        site=f"{sys.executable} (python {version})",
        evidence=f"sys.version_info={version}",
        detail=f"need >= {wanted}; verify.py cannot install its own interpreter "
        f"— re-run install.sh",
    )


if __name__ == "__main__":
    from pathlib import Path

    from nixverify.contract import exit_code_for

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
