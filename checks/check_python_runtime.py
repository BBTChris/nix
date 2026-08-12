#!/usr/bin/env python3
"""Verify the Python interpreter meets the floor.

Floor component (nix_check_contract.md §3): install.sh owns installation, so
this check detects drift and reports FAIL_NEEDS_OPERATOR — it never attempts
a repair it cannot perform.
"""

from __future__ import annotations

import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 pairs this module's ARC 025 declaration block with the identical block in
# every other retrofitted check. That similarity is the CONTRACT, not copied
# logic: `nix_check_contract.md` §4.4 fixes the seven symbol names, and
# `scripts/nixverify/declarations.py` reads them by AST, so each must be a
# module-level literal assignment under exactly those names in every check. The
# only way to deduplicate them is a shared module the AST reader cannot follow,
# which would defeat the mechanism. Hoisted to module scope because R0801 is
# reported at line 1 (see check_spec_citations.py's note).
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- ARC 025 orchestration declarations (read statically, never imported) ---
#: Nothing has to run before this. It is the bootstrap floor's first member in
#: the plan, but that is the PLAN's fact, not the check's: `nix_check_contract.md`
#: §4.4 — declarations are the check's, scheduling is the plan's.
DEPENDS_ON: tuple[str, ...] = ()
#: Claims NOTHING. It reads `sys.version_info` of the process it is already
#: running in: no file is opened, no socket dialled, no service touched, nothing
#: written anywhere. `()` is a positive claim ("claims nothing") and is what
#: makes this check eligible for a parallel block — a check that simply omitted
#: RESOURCES would be ineligible, never quietly assumed empty.
RESOURCES: tuple[str, ...] = ()
#: One tuple comparison. No timeout constant exists in this module, no poll, no
#: subprocess — so there is no bound for EXPECTED_S to be derived from, and
#: inventing one from an observed run is exactly what §4.4 forbids.
TIME_BOUND = False
#: NON-CORRECTABLE. The subject is the interpreter this check is executing on.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the interpreter this process is running on, and "
    "`install.sh` owns interpreter installation (`nix_check_contract.md` §3). "
    "A repair would have to replace the running interpreter underneath the "
    "engine — the catastrophe check_venv's `_running_from` guard exists to "
    "prevent, one level lower and with no surviving interpreter to recover "
    "from. The verdict is FAIL_NEEDS_OPERATOR by construction, and §4.1 of "
    "that document forbids auto-repairing that status."
)
#: Empty on the facts. The subject is the live interpreter, which is not a
#: repo-relative tracked artifact. Naming a file here to raise
#: check_artifact_gate_coverage's count would be manufacturing coverage for a
#: file this check never opens.
SUBJECTS: tuple[str, ...] = ()

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
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
