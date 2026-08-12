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
4. **ARC 025 — the baseline could GROW, silently, and rule 3 would not see it.**
   Rule 3 only reddens entries that became covered; nothing stopped a hand adding
   a fresh path to `uncovered` and turning a regression into an accepted one in
   the same motion. *Closed by `_high_water_mark`:* the prior mark is derived from
   the baseline's own **git history** — the tightest revision ever committed —
   and any addition relative to it must name the single arc that admitted it, in
   the file's `admitted` map, validated by the same grammar `guard_owner` uses.
   The mark is deliberately not stored anywhere the addition's author can edit.
5. **ARC 025 — the ratchet itself could go blind.** If git is absent, or the
   baseline has no commit history, or one historical revision will not parse,
   there is no mark. *Closed:* every one of those is `CANNOT_MEASURE` naming the
   reason, and a revision that cannot be read is an ERROR rather than a skip —
   the skipped revision could be exactly the tightest one.

## Why GUARDED rather than FAIL today

The uncovered set is large and known: 12 of 13 checks predate the declaration
mechanism and name nothing. That is a measured deferral with an owner — the bulk
retrofit arc — which is precisely AMENDMENT 1's GUARDED (exit 3), not a failure.
A *new* uncovered artifact is a regression and is a FAIL. So the instrument is a
ratchet: existing debt is guarded and visible; new debt is red.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess  # nosec B404 - git ls-files/log/show, fixed argv, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    guard_owner_defect,
)
from nixverify.declarations import read_all

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

DEPENDS_ON: tuple[str, ...] = ()
#: `()` until ARC 025, when `check_observed_resource_claims` OBSERVED this gate
#: spawning `/usr/bin/git` and reported the empty declaration as false — D2.27's
#: residual caught on the gate that opened it.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
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

#: How far back the ratchet reads. Bounded so the gate's own runtime cannot be
#: set by the length of the repository's history.
_HISTORY_LIMIT = 200


def _tracked_artifacts(home: Path) -> tuple[list[str], str]:
    """Enumerate tracked module/config artifacts. Returns (paths, error)."""
    listing, error = _git(home, "ls-files")
    if error:
        return [], error
    found = [
        line
        for line in listing.splitlines()
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


@dataclasses.dataclass(frozen=True)
class Baseline:
    """The ratchet file, parsed. `error` non-empty means it could not be read."""

    uncovered: frozenset[str] = frozenset()
    owner: str = ""
    #: path -> the single arc that admitted it. ARC 025; see `_ratchet_defects`.
    admitted: dict[str, str] = dataclasses.field(default_factory=dict)
    error: str = ""


def _parse_baseline(text: str, where: str) -> Baseline:
    """Parse baseline JSON. Shared by the working tree and by `git show`."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return Baseline(error=f"{where} unreadable: {exc!r}")
    if not isinstance(payload, dict):
        return Baseline(error=f"{where} is not a JSON object")
    admitted = payload.get("admitted", {})
    return Baseline(
        uncovered=frozenset(str(item) for item in payload.get("uncovered", [])),
        owner=str(payload.get("owner", "")),
        admitted=(
            {str(k): str(v) for k, v in admitted.items()}
            if isinstance(admitted, dict)
            else {}
        ),
    )


def _load_baseline(home: Path) -> Baseline:
    """Read the baseline as it stands in the WORKING TREE."""
    path = home / BASELINE
    if not path.is_file():
        return Baseline(error=f"{BASELINE} absent")
    try:
        return _parse_baseline(path.read_text(encoding="utf-8"), BASELINE)
    except OSError as exc:
        return Baseline(error=f"{BASELINE} unreadable: {exc!r}")


#: Git honours every one of these AHEAD of `-C`. A caller invoked from inside
#: another git operation — a pre-commit hook, a rebase, a filter-branch — has them
#: exported, and this gate would then enumerate a DIFFERENT repository and a
#: DIFFERENT index from the directory it was handed, silently.
#:
#: **MEASURED IN THIS ARC, NOT ANTICIPATED.** ARC 025 C's own test suite ran
#: `git add` inside a throwaway repo under `tmp_path` while pre-commit had
#: `GIT_INDEX_FILE` exported, and git wrote the throwaway tree into THIS
#: worktree's real index — every tracked file staged as deleted. The tests were
#: the visible casualty; the gate has the same exposure and is the reason this
#: constant lives here rather than in the test harness. It is the project's
#: recurring defect class (an ambient tracking state silently setting a gate's
#: scope) arriving through the environment instead of through a config file.
_GIT_ENV_BLOCKED = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_PREFIX",
)


def git_env() -> dict[str, str]:
    """`os.environ` with every repository-selecting `GIT_*` variable removed.

    Exported so the test harness runs git the same way the gate does — a harness
    that could redirect itself while the gate could not would be measuring a
    different program from the one that ships.
    """
    return {
        key: value for key, value in os.environ.items() if key not in _GIT_ENV_BLOCKED
    }


def _git(home: Path, *args: str) -> tuple[str, str]:
    """Run one git command against `home` and NOTHING else. Returns (stdout, error)."""
    if not Path(GIT).exists():
        return "", f"{GIT} not present"
    try:
        proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
            [GIT, "-C", str(home), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"git {args[0]} failed: {exc!r}"
    if proc.returncode != 0:
        return "", f"git {' '.join(args)} exit {proc.returncode}"
    return proc.stdout, ""


def _high_water_mark(home: Path) -> tuple[frozenset[str], str, str]:
    """The TIGHTEST accepted set this baseline has ever been COMMITTED with.

    Returns `(set, sha, error)`.

    ## Where the high-water mark lives, and why it lives there

    A ratchet needs a prior mark to ratchet against, and the tempting place to put
    it is a `previous_count` field in this same file — which the same hand edits
    in the same motion as the addition it excuses, making the ratchet decorative.
    A second config file is the same object with an extra filename.

    **So the mark is not stored at all. It is DERIVED from git history**, which is
    the one record on this box that the edit being judged provably cannot reach:
    `git show <sha>:<path>` reads the committed tree, not the working tree, and
    moving a committed revision means rewriting history — which `CLAUDE.md`
    directive 6 forbids outright and which changes every downstream sha, so it
    cannot be done quietly. Doctrine B.7's self-enforcing pattern, pointed at
    time instead of at a document.

    **The mark is the minimum over the WHOLE history, not `HEAD`.** `HEAD` alone
    would let an addition be laundered by committing it: one commit later the
    addition IS the prior mark. The minimum-over-history has no such laundry
    cycle — the tightest revision stays the tightest forever.

    **A revision that cannot be read is an ERROR, never a skip.** A silently
    skipped revision might be exactly the tightest one, and a high-water mark that
    quietly rises is the vacuous pass this gate exists to refuse.
    """
    listing, error = _git(
        home, "log", f"-{_HISTORY_LIMIT}", "--format=%H", "--", BASELINE
    )
    if error:
        return frozenset(), "", error
    shas = [line.strip() for line in listing.splitlines() if line.strip()]
    if not shas:
        return (
            frozenset(),
            "",
            (
                f"{BASELINE} has no commit history — the ratchet has nothing to ratchet "
                "against, so the accepted set cannot be shown not to have grown"
            ),
        )
    best: frozenset[str] | None = None
    best_sha = ""
    for sha in reversed(shas):  # oldest first, so ties keep the earliest mark
        blob, blob_error = _git(home, "show", f"{sha}:{BASELINE}")
        if blob_error:
            return (
                frozenset(),
                "",
                f"{blob_error} — cannot establish the high-water mark",
            )
        revision = _parse_baseline(blob, f"{BASELINE}@{sha[:12]}")
        if revision.error:
            return frozenset(), "", f"{revision.error} — cannot establish the mark"
        if best is None or len(revision.uncovered) < len(best):
            best, best_sha = revision.uncovered, sha
    return (best or frozenset()), best_sha, ""


def _ratchet_defects(
    baseline: Baseline, mark: frozenset[str], sha: str
) -> list[tuple[str, str]]:
    """Every accepted entry added since the tightest committed revision, unadmitted.

    The set may SHRINK freely — that is the whole point of a ratchet. An ADDITION
    is permitted only when the baseline names the single arc that admitted it, in
    `admitted`, under the SAME grammar `validate_result` enforces on `guard_owner`
    (one function, two consumers). An addition with no arc, or with a range, is a
    LOUD FAIL naming the path and the reason.
    """
    defects: list[tuple[str, str]] = []
    for path in sorted(baseline.uncovered - mark):
        defect = guard_owner_defect(baseline.admitted.get(path, ""))
        if defect:
            defects.append(
                (
                    f"{BASELINE}:admitted:{path}",
                    (
                        f"{path!r} was ADDED to the accepted-uncovered set since the "
                        f"tightest committed revision {sha[:12]} ({len(mark)} "
                        f"entries); a ratchet may only shrink, and an addition "
                        f"requires a named arc in `admitted` — {defect}"
                    ),
                )
            )
    return defects


def run(  # pylint: disable=unused-argument,too-many-locals,too-many-return-statements
    mode: Mode, ctx: Context
) -> CheckResult:
    """Compare tracked artifacts against declared subjects, and ratchet.

    Eight returns is eight guard clauses, each a distinct named outcome the
    contract requires: four things that make the measurement impossible (no git,
    too few artifacts, an unreadable baseline, no high-water mark), then the
    defect verdict, the owner defect, the guarded deferral, and the pass. The
    locals are the sets the ratchet arms compare. Nesting them to satisfy a
    counter would trade a linear, auditable shape for conditionals inside the
    instrument that decides whether this repo's coverage debt may grow.
    """
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
    baseline = _load_baseline(home)
    if baseline.error:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, detail=baseline.error
        )

    mark, mark_sha, mark_error = _high_water_mark(home)
    if mark_error:
        # The ratchet's prior mark is what makes a green mean anything. Without
        # it the gate can still see regressions but cannot see the baseline
        # growing, which is the whole of C3 — so it reports what it could not
        # measure rather than passing on the half it could.
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=mark_error)

    evidence = (
        f"{len(artifacts)} tracked artifact(s); {len(declared)} declared subject(s); "
        f"{len(uncovered)} uncovered; baseline accepts {len(baseline.uncovered)}; "
        f"ratchet high-water mark {len(mark)} at committed revision "
        f"{mark_sha[:12]}. "
        "UNBOUND (D3.10): proves an artifact is NAMED by a check, never that it is "
        "MEASURED by one — do not read this verdict as coverage."
    )

    # -- Regression: something uncovered that the baseline never accepted. ---
    regressions = sorted(uncovered - baseline.uncovered)
    # -- Rot: the baseline still lists something that is now covered. --------
    stale = sorted(baseline.uncovered - uncovered)

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
    # -- ARC 025: the baseline may not GROW without a named arc. -------------
    defects.extend(_ratchet_defects(baseline, mark, mark_sha)[:20])
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in defects),
            evidence=evidence,
            detail="; ".join(f"{site}: {why}" for site, why in defects),
        )

    if uncovered:
        # AMENDMENT 1: measured subject, known-red marker, named owner. ARC 025:
        # the owner is validated HERE as well as in `validate_result`, so an
        # operator reading this gate is told the baseline's `owner` field is the
        # offender rather than being handed the engine's generic downgrade.
        owner_defect = guard_owner_defect(baseline.owner)
        if owner_defect:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                evidence=evidence,
                detail=f"{BASELINE}:owner — {owner_defect}",
            )
        return CheckResult(
            name=NAME,
            status=Status.GUARDED,
            evidence=evidence,
            guard_owner=baseline.owner.strip(),
            detail=(
                f"{len(uncovered)} artifact(s) accepted as uncovered by "
                f"{BASELINE}, discharged by {baseline.owner.strip()}"
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
