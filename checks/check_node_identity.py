#!/usr/bin/env python3
"""Verify the stored node identity still matches this hardware.

The node is identified by the v4 UUID of the primary volume (§10.1). A
mismatch means a cloned VM, a swapped disk, or a restore onto different
hardware — never something to auto-"repair", so it reports
FAIL_NEEDS_OPERATOR.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
# No repair() exists at all — a mismatch is FAIL_NEEDS_OPERATOR in every
# mode, never auto-fixed (§4.1: "the engine cannot invent an account
# number" applies just as much to hardware identity as to a credential).
# DISRUPTIVE describes what a check's repair *does* (§8's boot-vs-weekly
# gate exists to protect service restarts and package swaps); a check with
# no repair path performs no action under any mode, so there is nothing for
# DISRUPTIVE to gate. False is correct on the facts, not by default.
DISRUPTIVE = False

NAME = "check_node_identity"


def _command(argv: list[str]) -> str:
    """Run a fixed command, returning stripped stdout or '' on any failure."""
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            argv, capture_output=True, text=True, timeout=30, check=True
        )
    # PEP 758 (Python 3.14): unparenthesized multi-type except without an
    # `as` binding is valid syntax, not a Python-2 leftover — this is
    # ruff-format's canonical output for the no-`as` case (see
    # check_python_deps.py for the same pattern).
    except OSError, subprocess.SubprocessError:
        return ""
    return proc.stdout.strip()


def live_uuid() -> str:
    """UUID of the filesystem mounted at /. '' if it cannot be determined."""
    device = _command(["findmnt", "-n", "-o", "SOURCE", "/"])
    if not device:
        return ""
    return _command(["blkid", "-s", "UUID", "-o", "value", device])


def stored_uuid(path: Path) -> str:
    """UUID recorded at install time. '' if absent or unreadable.

    Reads "primary_partition_uuid" — the key install.sh actually writes
    (install.sh:43), not "root_uuid". Verified against the on-disk
    state/node_identity.json produced by ARC 006/008's install run.
    """
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return ""
    return str(payload.get("primary_partition_uuid", ""))


def evaluate(stored: str, live: str, path: Path) -> CheckResult:
    """Compare the two. Pure — hence directly testable."""
    if not stored:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=str(path),
            detail="no stored node identity — re-run install.sh",
        )
    if not live:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail="findmnt/blkid did not answer — live UUID unknown",
        )
    if stored != live:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=str(path),
            evidence=f"live={live}",
            detail=f"stored {stored} != live {live} — cloned VM, swapped disk, "
            f"or restore onto different hardware",
        )
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=f"stored == live == {live}",
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Read both values and compare."""
    path = ctx.nix_home / "state" / "node_identity.json"
    return evaluate(stored_uuid(path), live_uuid(), path)


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
if __name__ == "__main__":  # pylint: disable=duplicate-code
    from nixverify.contract import exit_code_for

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
