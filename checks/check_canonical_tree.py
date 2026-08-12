#!/usr/bin/env python3
"""Verify the canonical tree is a live work tree and no orphan tree shadows it.

ARC 026 Phase 0.5. The subject is the failure class that bared this repository:
on 2026-08-12 01:23:25 UTC a sub-agent's `git init`, running with `GIT_DIR`
inherited from the pre-commit hook environment, wrote `core.bare = true` into
`/home/bbt/nix/.git/config`. The working tree did not move and no file was
deleted — git simply stopped calling it a work tree. Every gate's scope
collapsed to whatever the per-arc integration worktree happened to hold, while
the tree at the path every standing rule names sat frozen and invisible.

This is the seventh instance of *git tracking state sets gate scope*, and the
first one at the canonical path. Same root cause as D3.22.

§0b SUBSTITUTION — RECORDED, NOT SILENT
---------------------------------------
The brief spelled this gate as "no untracked working files beside the bare
repo". That predicate is **permanently vacuous under its own fix**: the correct
repair un-bares the repository, after which there is no bare repo for anything
to sit beside, and the gate passes forever while measuring nothing. A gate whose
subject is deleted by the remedy it exists to motivate is furniture (§7.12).

The invariant underneath the spelling is *not* "the bare repo has no
neighbours". It is:

    every filesystem tree holding `scripts/verify.py` is accounted for by a
    REGISTERED git worktree, and the canonical path is one of them.

That is what actually discriminates. An orphaned tree is precisely a tree that
holds the instrument but appears in no worktree's scope — which is exactly what
`/home/bbt/nix` became when `core.bare` flipped, and exactly what a per-arc
sub-agent worktree is NOT. It stays true after the repair, it permits the
legitimate per-arc worktrees Stage 1 depends on, and it fires on the real
historical defect. Verified against that instance: `git worktree list` reported
`/home/bbt/nix (bare)` while `/home/bbt/nix/scripts/verify.py` existed and ran.

§7.12 THE STANDING QUESTION
---------------------------
*What would have to be true for this gate to pass while measuring nothing?*

Four ways, each closed by construction:

1. **No candidate trees found.** If the scan found nothing, the gate would be
   comparing an empty set against an empty set and reporting PASS. Closed: the
   canonical tree itself must appear among the candidates, and its own
   `scripts/verify.py` must be the one this file sits beside. A scan that cannot
   see the instrument it is running from is CANNOT_MEASURE, never PASS.
2. **`git worktree list` fails and yields no registrations.** Every candidate
   would then be unregistered and the gate would FAIL — loud, not vacuous — but
   the inverse (git succeeding and returning nothing while trees exist) is
   CANNOT_MEASURE, because "no registrations" is not the same claim as "no
   orphans".
3. **The scan root is wrong.** Scanning a directory that contains no trees
   passes trivially. Closed by (1): the canonical tree must be *found by the
   scan*, not assumed — if the scan root cannot see the canonical path, the
   scan root is wrong and the verdict is CANNOT_MEASURE.
4. **`core.bare` read from the wrong repository.** `git` honours `GIT_DIR` and
   `GIT_INDEX_FILE` **ahead of `-C`** (D3.22) — the very mechanism that caused
   the defect. A gate reading a hook-injected `GIT_DIR` would report on some
   other repo and pass. Closed: every subprocess here runs under a scrubbed
   environment (`_git_env`), and the scrub is asserted by the committed suite.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) disabled at module scope, ARC 026 / A2, and it is a
# BASELINE REPAIR rather than a new suppression. This gate landed in ARC 026
# Phase 0.5 carrying the pragma only on its `__main__` tail; pylint reports
# R0801 at line 1, so the tail pragma does not reach it and the hook has been
# RED on `--all-files` ever since — measured on the pristine base commit
# (`98106be`), with the pair named as `check_artifact_gate_coverage` vs
# `check_canonical_tree`. The duplicated text is the preamble/declaration block
# that `nix_check_contract.md` §4.2 MANDATES be identical in every check, which
# is the same reason `check_spec_citations`, `check_order_path_bans`,
# `check_hook_suite` and `check_python_runtime` all carry this pragma at module
# scope. Doctrine B.6: a lint gate already failing before an arc starts gets
# that arc's changes blamed on it.
# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. This gate is stdlib-only, shells out to `git`, and
#: reads no artifact any other check produces (§4.4 — declarations are the
#: check's, scheduling is the plan's).
DEPENDS_ON: tuple[str, ...] = ()
#: `git` is claimed because this gate SPAWNS it (three invocations: `worktree
#: list`, `config --get core.bare`, `rev-parse`). The filesystem walk is a
#: read-only stat sweep over directory entries holding nothing another check
#: could contend for, and is deliberately not claimed — the same reasoning
#: `check_node_identity` applied to findmnt/blkid, and the same reasoning the
#: ARC 025 runtime observer OVERTURNED there. Declared here rather than argued:
#: an under-declaration costs correctness, an over-declaration costs only
#: parallelism, and `check_observed_resource_claims` will report on this file
#: like any other. If the observer sees more, the observer is right.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
#: FALSE on the facts. Three git invocations answer in milliseconds; the runtime
#: is dominated by that work, not by waiting on it.
TIME_BOUND = False
#: NON-CORRECTABLE, and this arc is the evidence rather than the assertion.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the two conditions this gate reports have no common mechanical repair, and "
    "the one that looks automatable is the one that destroys data. A bare "
    "canonical path is repaired by unsetting core.bare — safe, and what ARC 019 "
    "and ARC 026 both did by hand. An ORPHANED TREE has no such repair: the only "
    "mechanical 'correction' is deletion, and ARC 026 measured what deletion at "
    "this path costs. /home/bbt/nix is the Samba share [nix] (smb.conf), mounted "
    "live by the operator's workstation, and the orphaned tree held the ONLY "
    "copy on the machine of the arc brief being executed — a scripted delete "
    "would have destroyed its own instructions. An instrument that cannot tell "
    "'stale duplicate' from 'the operator's only copy' must not be given rm. "
    "Report the site, name the condition, let a human look."
)
#: This gate's subject is repository topology, not a tracked file, so it adds
#: nothing to check_artifact_gate_coverage's tracked-artifact arithmetic. Empty
#: because it is TRUE, not to move a count.
SUBJECTS: tuple[str, ...] = ()

NAME = "check_canonical_tree"

#: The canonical path, absolute and stable (ARC 026 Phase 0.4). Every standing
#: rule already names it; the Samba share already serves it; gates already
#: resolve it. It is a constant here rather than derived from `ctx.nix_home`
#: BECAUSE deriving it would defeat the gate: a check that asks the running tree
#: where the canonical tree is will call whatever tree it was launched from
#: canonical, which is the exact confusion this gate exists to detect.
CANONICAL = Path("/home/bbt/nix")

#: `scripts/verify.py` is the marker for "this directory is a Nix tree". It is
#: the instrument itself — the thing the brief requires resolve to exactly one
#: place — so a stray copy of it IS the hazard, not a proxy for one.
INSTRUMENT = Path("scripts") / "verify.py"

#: Where to look for trees. The canonical tree's parent: per-arc worktrees are
#: siblings by project convention (`~/nix-wt-arc-0NN-*`), and the orphan this
#: gate was built for was the canonical path itself.
SCAN_ROOT = CANONICAL.parent


def _git_env() -> dict[str, str]:
    """Environment with git's tree-selecting variables stripped (D3.22).

    `git` honours `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and
    `GIT_COMMON_DIR` **ahead of `-C`**, and `pre-commit` exports them into
    every hook it runs. That precedence is what damaged a sub-agent's worktree
    index in ARC 025 and, one layer up, what bared this repository: a `git`
    invocation that believes it is talking about the tree named on its command
    line while actually talking about whatever the hook environment pointed at.

    A gate that reported on the wrong repository would pass while measuring
    nothing, so the scrub is part of the measurement, not hygiene around it.
    """
    env = dict(os.environ)
    for leaked in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(leaked, None)
    return env


def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run git under a scrubbed environment. Returns (returncode, stdout)."""
    try:
        # nosec B603 B607 - fixed argv, shell=False, no user input. `git` is
        # resolved from PATH deliberately: this gate measures the same `git` the
        # operator and the hooks invoke, and pinning an absolute path would make
        # it report on a binary nothing else in the project uses.
        proc = subprocess.run(  # nosec B603 B607
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=str(cwd),
            env=_git_env(),
        )
    except OSError, subprocess.SubprocessError:
        return -1, ""
    return proc.returncode, proc.stdout.strip()


def registered_worktrees(repo: Path) -> tuple[list[Path], list[Path]]:
    """(worktree paths, bare-marked paths) from `git worktree list --porcelain`.

    The two are separated deliberately. A path git reports as `bare` is NOT a
    work tree — it is the condition this gate fires on — so folding it into the
    registered set would make the gate report PASS on the exact state it exists
    to catch.
    """
    code, out = _git(["worktree", "list", "--porcelain"], cwd=repo)
    if code != 0:
        return [], []
    trees: list[Path] = []
    bare: list[Path] = []
    current: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            current = Path(line[len("worktree ") :].strip())
            trees.append(current)
        elif line.strip() == "bare" and current is not None:
            bare.append(current)
    return trees, bare


def candidate_trees(scan_root: Path) -> list[Path]:
    """Directories directly under `scan_root` that hold `scripts/verify.py`."""
    found: list[Path] = []
    try:
        entries = sorted(scan_root.iterdir())
    except OSError:
        return found
    for entry in entries:
        try:
            if entry.is_dir() and (entry / INSTRUMENT).is_file():
                found.append(entry)
        except OSError:
            continue
    return found


def core_bare(repo: Path) -> str:
    """`core.bare` as git reports it: 'true', 'false', or '' when unset."""
    code, out = _git(["config", "--get", "core.bare"], cwd=repo)
    if code != 0:
        return ""
    return out.strip().lower()


def evaluate(  # pylint: disable=too-many-return-statements
    canonical: Path,
    candidates: list[Path],
    registered: list[Path],
    bare: list[Path],
    bare_setting: str,
) -> CheckResult:
    """Compare topology against the invariant. Pure — hence directly testable."""
    resolved_registered = {p.resolve() for p in registered}
    resolved_bare = {p.resolve() for p in bare}
    canonical_resolved = canonical.resolve()

    # §7.12 closure (1) and (3): the gate must SEE the tree it runs from.
    if canonical_resolved not in {p.resolve() for p in candidates}:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(canonical),
            detail=f"the canonical path did not appear among the {len(candidates)} "
            f"tree(s) the scan found under {SCAN_ROOT} — either the scan root is "
            f"wrong or {canonical / INSTRUMENT} is absent. A scan that cannot see "
            f"the instrument it is running from proves nothing about orphans",
        )

    # §7.12 closure (2): git answering nothing is not git answering 'none'.
    if not registered:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(canonical),
            detail="`git worktree list --porcelain` returned no registrations; "
            "'no answer' is not the same claim as 'no orphans'",
        )

    # The bare-canonical-path condition itself — the ARC 019/026 hazard.
    if bare_setting == "true" or canonical_resolved in resolved_bare:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=str(canonical),
            evidence=f"core.bare={bare_setting or 'unset'}, "
            f"git-reports-bare={canonical_resolved in resolved_bare}",
            detail=f"{canonical} is a BARE repository but holds a working tree "
            f"({canonical / INSTRUMENT} exists). Every gate's scope has collapsed "
            f"to whatever other tree is registered, and this one is invisible to "
            f"all of them. Repair: `git -C {canonical} config --unset core.bare` "
            f"(ARC 019 and ARC 026 precedent). Do NOT delete the tree — ARC 026 "
            f"measured that this path is the live Samba share [nix]",
        )

    orphans = [p for p in candidates if p.resolve() not in resolved_registered]
    if orphans:
        listed = ", ".join(str(p) for p in sorted(orphans))
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=listed,
            evidence=f"{len(orphans)} orphan(s) of {len(candidates)} candidate "
            f"tree(s); {len(registered)} registered worktree(s)",
            detail=f"tree(s) holding {INSTRUMENT} that no registered git worktree "
            f"accounts for: {listed}. An unregistered tree runs the instrument "
            f"while being invisible to every gate that measures it — the failure "
            f"class that bared this repository. Register it, or remove it AFTER "
            f"proving it holds nothing unique (ARC 026 Phase 0.2)",
        )

    return CheckResult(
        name=NAME,
        status=Status.PASS,
        site=str(canonical),
        evidence=f"{len(candidates)} tree(s) holding {INSTRUMENT}, all accounted "
        f"for by {len(registered)} registered worktree(s); canonical={canonical} "
        f"core.bare={bare_setting or 'unset'}",
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure repository topology against the canonical-path invariant."""
    registered, bare = registered_worktrees(CANONICAL)
    return evaluate(
        CANONICAL,
        candidate_trees(SCAN_ROOT),
        registered,
        bare,
        core_bare(CANONICAL),
    )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
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
