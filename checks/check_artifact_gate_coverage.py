#!/usr/bin/env python3
"""Gate: every tracked module and config artifact is NAMED by some check.

ARC 024 §2.7. AMENDMENT 3 broadens the coverage trigger from *every environment
change owes a check* to *any module or setting written to disk or changed owes a
check*. A doctrine that broad is unenforceable as prose and would rot into a
slogan, so it gets an instrument.

## READ THIS BEFORE TRUSTING A GREEN FROM THIS GATE

**This gate ships UNBOUND per D3.10 and says so in its own verdict.**

It proves that **some check NAMES the artifact**. That is strictly weaker than
**some check MEASURES the artifact**, and the gap between those two sentences is
D3.16 exactly — a gate that reported PASS across two arcs over a method it never
executed. A check can add a path to its `SUBJECTS` tuple and never open the file.
This gate cannot see that class of defect and must not be read as if it could.

Binding it — proving the named subject is actually driven — is a named future
arc. Until then its green means *declared*, never *covered*.

## debug.md §7.12 — the standing question

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The artifact set could be empty.** A `git ls-files` that returns nothing —
   wrong cwd, git absent, a tree with no tracked files — yields "zero artifacts,
   zero uncovered, PASS", which is the purest possible vacuous green. *Closed:*
   an empty artifact set is CANNOT_MEASURE, and a set smaller than
   `MIN_CREDIBLE_ARTIFACTS` is CANNOT_MEASURE, because this repo cannot honestly
   have three source files.
2. **The declared-subject set could be empty and the artifact set could also be
   empty**, for the same reason. Same closure.
3. **The baseline could absorb everything forever.** A ratchet whose baseline
   only ever grows is a suppression list wearing a ratchet's name. *Closed by the
   STALE-BASELINE rule:* an entry in the baseline that is now covered is a FAIL,
   not a shrug. The baseline can only tighten.

## Why GUARDED rather than FAIL today

The uncovered set is large and known: 12 of 13 checks predate the declaration
mechanism and name nothing. That is a measured deferral with an owner — the bulk
retrofit arc — which is precisely AMENDMENT 1's GUARDED (exit 3), not a failure.
A *new* uncovered artifact is a regression and is a FAIL. So the instrument is a
ratchet: existing debt is guarded and visible; new debt is red.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - git ls-files, fixed argv, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
)
from nixverify.declarations import read_all

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = ()
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "coverage is closed by writing checks, not by an instrument editing "
    "declarations to satisfy itself — a gate that could add its own SUBJECTS "
    "entries would be manufacturing its own green"
)
SUBJECTS: tuple[str, ...] = (
    "checks/gate_coverage_baseline.json",
    "scripts/nixverify/declarations.py",
)

NAME = "check_artifact_gate_coverage"
GIT = "/usr/bin/git"
BASELINE = "checks/gate_coverage_baseline.json"

#: Below this, the enumeration is not credible and the gate refuses to report.
#: Anchored to a floor, not to the current count — a threshold equal to today's
#: number would be a moving anchor that reddens the moment a file is added.
MIN_CREDIBLE_ARTIFACTS = 20

#: What counts as a "module or setting written to disk". Test modules are
#: excluded: a test is not a settable artifact, it IS the measurement.
_INCLUDE_SUFFIXES = (".py", ".json")
_EXCLUDE_PREFIXES = ("scripts/tests/", "checks/check_", "downloads/", "docs/")


def _tracked_artifacts(home: Path) -> tuple[list[str], str]:
    """Enumerate tracked module/config artifacts. Returns (paths, error)."""
    if not Path(GIT).exists():
        return [], f"{GIT} not present"
    try:
        proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
            [GIT, "-C", str(home), "ls-files"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"git ls-files failed: {exc!r}"
    if proc.returncode != 0:
        return [], f"git ls-files exit {proc.returncode}"
    found = [
        line
        for line in proc.stdout.splitlines()
        if line.endswith(_INCLUDE_SUFFIXES) and not line.startswith(_EXCLUDE_PREFIXES)
    ]
    return sorted(found), ""


def _declared_subjects(home: Path) -> set[str]:
    """Union of every SUBJECTS entry across the check population."""
    return {
        subject
        for decl in read_all(home / "checks").values()
        for subject in decl.subjects
    }


def _load_baseline(home: Path) -> tuple[set[str], str, str]:
    """Return (accepted-uncovered, owner-arc, error)."""
    path = home / BASELINE
    if not path.is_file():
        return set(), "", f"{BASELINE} absent"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return set(), "", f"{BASELINE} unreadable: {exc!r}"
    return set(payload.get("uncovered", [])), str(payload.get("owner", "")), ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Compare tracked artifacts against declared subjects, and ratchet."""
    home = Path(ctx.nix_home)
    artifacts, error = _tracked_artifacts(home)
    if error:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
    if len(artifacts) < MIN_CREDIBLE_ARTIFACTS:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"only {len(artifacts)} tracked artifact(s) enumerated, below the "
                f"credibility floor of {MIN_CREDIBLE_ARTIFACTS} — an empty or tiny "
                "enumeration would make every artifact trivially covered"
            ),
        )

    declared = _declared_subjects(home)
    uncovered = {path for path in artifacts if path not in declared}
    baseline, owner, baseline_error = _load_baseline(home)
    evidence = (
        f"{len(artifacts)} tracked artifact(s); {len(declared)} declared subject(s); "
        f"{len(uncovered)} uncovered; baseline accepts {len(baseline)}. "
        "UNBOUND (D3.10): proves an artifact is NAMED by a check, never that it is "
        "MEASURED by one — do not read this verdict as coverage."
    )

    if baseline_error:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, detail=baseline_error
        )

    # -- Regression: something uncovered that the baseline never accepted. ---
    regressions = sorted(uncovered - baseline)
    # -- Rot: the baseline still lists something that is now covered. --------
    stale = sorted(baseline - uncovered)

    defects: list[tuple[str, str]] = []
    for path in regressions[:20]:
        defects.append((path, "no check declares this artifact as a SUBJECT"))
    for path in stale[:20]:
        defects.append(
            (
                f"{BASELINE}:{path}",
                (
                    "baseline still accepts this artifact as uncovered, but a "
                    "check now declares it — tighten the baseline (a ratchet "
                    "may only shrink)"
                ),
            )
        )
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in defects),
            evidence=evidence,
            detail="; ".join(f"{site}: {why}" for site, why in defects),
        )

    if uncovered:
        # AMENDMENT 1: measured subject, known-red marker, named owner.
        return CheckResult(
            name=NAME,
            status=Status.GUARDED,
            evidence=evidence,
            guard_owner=owner or "unassigned",
            detail=(
                f"{len(uncovered)} artifact(s) accepted as uncovered by "
                f"{BASELINE}, discharged by {owner or 'NOBODY — this is a defect'}"
            ),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
