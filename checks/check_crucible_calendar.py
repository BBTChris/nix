#!/usr/bin/env python3
"""check_crucible_calendar -- verify.py gate: the vendored CME calendar
artifact is present, hash-honest, and the runtime module reads it without a
calendar library or network dependency.

PROPERTY PROVEN (real, effective, on THIS host):
  `scripts/crucible/calendar_data/cme_calendar_{sessions,reconciliation}.csv`
  independently hash to the value stamped in
  `cme_calendar_provenance.json` (§ARC CRUCIBLE-CALENDAR-INFRA Success #8:
  "a downstream stamp can resolve to exact calendar bytes"), AND
  `scripts/crucible/calendar.py` imports cleanly and answers for all six
  locked product groups WITHOUT importing a calendar library (Success #1).

EXIT / STATUS CONTRACT (nix_check_contract.md §4.2):
  PASS (0)            artifact present, hash matches provenance, runtime
                       module imports clean and answers for all six groups,
                       static scan finds no calendar-lib/network import
  FAIL (1)             hash mismatch (tampered/stale artifact), a group
                       missing from the runtime module's answer, or a
                       forbidden import found -- a measured violation, sited
  CANNOT_MEASURE (2)  artifact or runtime module absent -- the subject
                       cannot be observed, so its behaviour cannot be
                       measured (§17)

NON-VACUITY:
  The core assertion recomputes the artifact's sha256 INDEPENDENTLY of the
  stamp that claims it (same pattern as check_monitor's reported-vs-disk
  compare) -- a hand-edited artifact whose provenance stamp was not
  regenerated to match is exactly what this catches; a fixed literal never
  could.

NON-CORRECTABLE:
  The subject is a build-time-generated artifact. "Correcting" it here would
  mean invoking the generator (network + a dev-only calendar library) from
  an unattended boot-time gate to make its own verdict true by construction
  -- the same reasoning check_monitor's NON_CORRECTABLE_REASON gives for not
  editing the tool it measures. Drift is FAIL-and-report; regeneration is a
  human-invoked `scripts/crucible/calendar_gen.py` run, reviewed and
  committed like any other source change.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported; §4.4) ---
#: Nothing else produces or depends on this subsystem yet.
DEPENDS_ON: tuple[str, ...] = ()
#: Read-only file reads plus an in-process import of a stdlib-only module --
#: nothing another check contends for.
RESOURCES: tuple[str, ...] = ()
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the build-time-generated calendar artifact; a repair "
    "that regenerated it here would invoke a dev-only calendar library "
    "and (per the generator's own network-sourced reconciliation) is a "
    "human-reviewed action, not an unattended boot-time correction -- "
    "identical reasoning to check_monitor's refusal to edit its subject"
)
#: The artifact files and the runtime module this gate verifies together, plus
#: the two sibling artifacts (the package marker and the generator this gate
#: does not import but whose OUTPUT it hash-verifies) that
#: check_artifact_gate_coverage would otherwise count as uncovered tracked
#: artifacts under scripts/crucible/. NAMED, not MEASURED, exactly as this
#: gate's own module docstring already says of itself (D3.10) --
#: `calendar_gen.py` is exercised by scripts/tests/test_crucible_calendar_gen.py,
#: not by this check.
SUBJECTS: tuple[str, ...] = (
    "scripts/crucible/__init__.py",
    "scripts/crucible/calendar.py",
    "scripts/crucible/calendar_gen.py",
    "scripts/crucible/calendar_data/cme_calendar_sessions.csv",
    "scripts/crucible/calendar_data/cme_calendar_reconciliation.csv",
    "scripts/crucible/calendar_data/cme_calendar_provenance.json",
    "sessions/crucible_calendar_checkpoint.json",
)

NAME = "check_crucible_calendar"

# The locked-groups tuple and the forbidden-imports set below are both
# deliberately re-declared in scripts/tests/test_crucible_calendar.py rather
# than imported from here: an independent second implementation of Success
# #1 is the point (a bug in this gate's own definitions would otherwise go
# unnoticed by a test that shares them) -- mirrors the reasoning
# check_monitor.py gives for duplicating its __main__ block.
# pylint: disable=duplicate-code
LOCKED_GROUPS = (
    "agriculturals",
    "energy",
    "equity_index",
    "fx",
    "interest_rates",
    "metals",
)
FORBIDDEN_IMPORTS = {
    "pandas_market_calendars",
    "pandas",
    "exchange_calendars",
    "socket",
    "http",
    "urllib",
    "requests",
}


def _static_forbidden_imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported & FORBIDDEN_IMPORTS


def _missing_subjects(paths: tuple[Path, ...]) -> CheckResult | None:
    missing = [p.name for p in paths if not p.is_file()]
    if not missing:
        return None
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=(
            f"crucible calendar subject(s) absent: {', '.join(missing)} "
            "-- cannot be measured (§17)"
        ),
    )


def _static_scan_result(calendar_module: Path) -> CheckResult | None:
    """Success #1 PROOF 2. None if clean."""
    forbidden = _static_forbidden_imports(calendar_module)
    if not forbidden:
        return None
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site=f"{NAME}:calendar.py imports",
        evidence=f"runtime module imports forbidden module(s): {sorted(forbidden)}",
        detail=(
            "scripts/crucible/calendar.py must be network-free and "
            f"calendar-library-free at import time; found: {sorted(forbidden)}"
        ),
    )


def _hash_check(
    sessions_file: Path, reconciliation_file: Path, provenance_file: Path
) -> tuple[str, CheckResult | None]:
    """Success #8 NON-VACUOUS hash proof. Returns (recomputed_hash, failure_or_None)."""
    recomputed = hashlib.sha256(
        sessions_file.read_bytes() + reconciliation_file.read_bytes()
    ).hexdigest()
    try:
        provenance = json.loads(provenance_file.read_text())
    except json.JSONDecodeError as exc:
        failure = CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=f"{NAME}:provenance",
            evidence=f"provenance stamp is not valid JSON: {exc}",
            detail=str(provenance_file),
        )
        return recomputed, failure
    stamped = provenance.get("content_hash_sha256")
    if stamped != recomputed:
        failure = CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=f"{NAME}:{provenance_file}",
            evidence=(
                f"HASH MISMATCH: provenance stamps {stamped!r}, "
                f"independently recomputed {recomputed!r}"
            ),
            detail=(
                "the vendored artifact was edited (or the stamp was) without "
                "regenerating both together -- rerun scripts/crucible/calendar_gen.py"
            ),
        )
        return recomputed, failure
    return recomputed, None


def _behavioral_check(nix_home: Path) -> tuple[tuple[str, ...], CheckResult | None]:
    """Runtime module answers for all six locked groups. Returns (groups, failure_or_None)."""
    sys.path.insert(0, str(nix_home / "scripts"))
    try:
        # pylint: disable-next=import-outside-toplevel
        from crucible import calendar as cal
    except ImportError as exc:
        failure = CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=f"{NAME}:import",
            evidence=f"runtime module failed to import: {exc}",
            detail=str(exc),
        )
        return (), failure
    cal._load.cache_clear()  # pylint: disable=protected-access
    groups = cal.known_product_groups()
    if set(groups) != set(LOCKED_GROUPS):
        failure = CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=f"{NAME}:groups",
            evidence=f"runtime module reports groups {groups}, locked set is {LOCKED_GROUPS}",
            detail="the vendored artifact must carry exactly the six locked product groups",
        )
        return groups, failure
    return groups, None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the artifact is hash-honest and the runtime module is clean."""
    try:
        crucible = Path(ctx.nix_home) / "scripts" / "crucible"
        calendar_module = crucible / "calendar.py"
        data_dir = crucible / "calendar_data"
        sessions_file = data_dir / "cme_calendar_sessions.csv"
        reconciliation_file = data_dir / "cme_calendar_reconciliation.csv"
        provenance_file = data_dir / "cme_calendar_provenance.json"

        missing_result = _missing_subjects(
            (calendar_module, sessions_file, reconciliation_file, provenance_file)
        )
        if missing_result is not None:
            return missing_result

        scan_result = _static_scan_result(calendar_module)
        if scan_result is not None:
            return scan_result

        recomputed, hash_failure = _hash_check(
            sessions_file, reconciliation_file, provenance_file
        )
        if hash_failure is not None:
            return hash_failure

        groups, behavior_failure = _behavioral_check(Path(ctx.nix_home))
        if behavior_failure is not None:
            return behavior_failure

        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"artifact hash-honest (sha256 {recomputed[:12]}..., matches "
                f"provenance), runtime module clean of {sorted(FORBIDDEN_IMPORTS)}, "
                f"answers for all {len(groups)} locked product groups"
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
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
