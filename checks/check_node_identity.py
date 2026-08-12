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

# --- ARC 025 orchestration declarations (read statically, never imported) ---
#: Nothing must run first. The registry puts this after the bootstrap floor,
#: but that is ordering the PLAN chose, not a causal dependency this check has:
#: it is stdlib-only and does not need the venv (`nix_check_contract.md` §4.4 —
#: declarations are the check's, scheduling is the plan's).
DEPENDS_ON: tuple[str, ...] = ()
#: The one artifact this check opens. Named at FILE granularity rather than as
#: the whole `state/` directory on purpose: a future credential gate that claims
#: a different file under `state/` is genuinely disjoint from this one, and
#: claiming the directory would serialise the two for no measured reason.
#: `findmnt` and `blkid` are deliberately NOT claimed — they are read-only
#: kernel/device queries holding nothing another check could contend for, and an
#: over-declaration costs parallelism without buying safety.
#: ARC 025 Stage 2.4 — CORRECTED BY THE RUNTIME OBSERVER, against this check's
#: own written reasoning. Wave A declared only the JSON file and argued in its
#: report that `findmnt`/`blkid` were "read-only kernel/device queries holding
#: nothing another check could contend for", so they were deliberately NOT
#: declared. `check_observed_resource_claims` then OBSERVED both on the real
#: tree and reported the declaration as false.
#:
#: The argument was about CONTENTION and it is defensible on those terms. The
#: declaration is not a contention model, it is a statement of what the check
#: touches, and this project fails closed: an under-declaration costs
#: correctness, an over-declaration costs only parallelism. Neither program is
#: claimed by any other check, so declaring them costs nothing measurable here.
#:
#: This is the whole point of D2.27 closing — a human's plausible reasoning
#: about resource use was checked against what the process actually did, and
#: reality won.
RESOURCES: tuple[str, ...] = (
    "state/node_identity.json",
    "subprocess:findmnt",
    "subprocess:blkid",
)
#: FALSE on the facts. The two subprocesses carry a 30 s ceiling each, but a
#: ceiling is not a bound this check PAYS: findmnt and blkid answer in
#: milliseconds and the runtime is dominated by that work, not by waiting.
#: TIME_BOUND describes a check whose duration IS its bound — check_verify_logging
#: polling journald — which this is not, so no EXPECTED_S is declared either.
TIME_BOUND = False
#: NON-CORRECTABLE — [ARCHITECT RULING, ARC 025 A2, revocable].
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is credential-adjacent identity material: "
    "state/node_identity.json sits in the 0600 `state/` directory that "
    "`nix_check_contract.md` §11 governs, and §4.3 of that document names "
    "credentials and `state/` as members of the non-correctable class. A "
    "'correction' here could only mean the engine SYNTHESISING a hardware "
    "identity — overwriting the stored UUID with whatever the live disk "
    "currently reports — which does not repair the finding, it erases it. A "
    "mismatch means a cloned VM, a swapped disk, or a restore onto different "
    "hardware, and each of those is a fact an operator must see, not a "
    "divergence an instrument may reconcile in its own favour."
)
#: The stored identity file is what this check measures. It is untracked (the
#: `state/` tree is gitignored) so it adds nothing to
#: check_artifact_gate_coverage's tracked-artifact arithmetic; it is declared
#: because it is TRUE, not to move a count.
SUBJECTS: tuple[str, ...] = ("state/node_identity.json",)

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


def _read_state(path: Path) -> tuple[str, str]:
    """Read the stored UUID, distinguishing *why* it might be missing.

    Returns (uuid, condition). condition is "" on success, "absent" if the
    file does not exist at all, or "corrupt: <reason>" if it exists but
    could not be read/parsed as a JSON object. §10.1: a present-but-
    unparseable file is a different operator-facing condition than an
    absent one and must be reported as such, not folded into "no stored
    node identity" wording that tells the operator to re-run install.sh
    fresh when the real problem is a damaged file.

    Mirrors scripts/nixverify/manifest.py's handling of the identical
    read-decode-parse operation: OSError (unreadable), UnicodeDecodeError
    (read_text on non-UTF-8 bytes — a ValueError, not caught by the prior
    `except OSError, json.JSONDecodeError`), and json.JSONDecodeError
    (malformed JSON) are all "corrupt", never allowed to escape as an
    uncaught exception. A payload that parses but is not a JSON object
    (e.g. a list) is guarded explicitly so `.get()` below cannot raise
    AttributeError on valid-but-wrong-shaped JSON.
    """
    if not path.is_file():
        return "", "absent"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return "", f"corrupt: {exc!r}"
    if not isinstance(payload, dict):
        return "", f"corrupt: expected a JSON object, got {type(payload).__name__}"
    return str(payload.get("primary_partition_uuid", "")), ""


def stored_uuid(path: Path) -> str:
    """UUID recorded at install time. '' if absent, corrupt, or missing the key.

    Reads "primary_partition_uuid" — the key install.sh actually writes
    (install.sh:43), not "root_uuid". Verified against the on-disk
    state/node_identity.json produced by ARC 006/008's install run.

    Convenience wrapper over `_read_state()` for callers that only need the
    value, not the absent-vs-corrupt distinction (§10.1) — `run()` calls
    `_read_state()` directly for that.
    """
    return _read_state(path)[0]


def evaluate(stored: str, live: str, path: Path, condition: str = "") -> CheckResult:
    """Compare the two. Pure — hence directly testable.

    `condition` (from `_read_state()`) distinguishes why `stored` is empty:
    "absent" (no file — re-run install.sh) vs a "corrupt: ..." reason (a
    file exists but could not be parsed — a different condition, §10.1).
    Defaults to "" (treated as absent) so existing direct callers that only
    care about the UUID comparison need not supply it.
    """
    if not stored:
        if condition.startswith("corrupt"):
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=str(path),
                detail=f"stored node identity file is present but unparseable "
                f"({condition}) — this is not an absent file; investigate "
                f"before re-running install.sh",
            )
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
    stored, condition = _read_state(path)
    return evaluate(stored, live_uuid(), path, condition)


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
