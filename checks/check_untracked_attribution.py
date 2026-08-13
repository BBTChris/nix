#!/usr/bin/env python3
"""Attribute every untracked appearance in the CANONICAL tree.

ARC 029 Phase 0.3, and the finding it answers is not the files.

## The measured instance

ARC 028 Stage 1 dispatched five sub-agents, each told to work only inside its
provisioned worktree. During that window two artifacts — `scripts/nix_status.sh`
(561 lines) and `scripts/tests/test_nix_status.py` (250 lines) — appeared at
`/home/bbt/nix`, in **no commit on any branch**, carrying a test describing
faults in a `v1.0.0` that never existed. No sub-agent reported them.

**They were caught only because the mandated `git add -A` staged them into three
commit gates**, where `ruff format`, `pylint` R1721 and `bandit` B607 reddened on
lines the integrator had never seen. That is the standing rule getting lucky. It
is not a detector, and it fails silently for any file that happens to be clean.

The operator has since ruled that `nix_status.sh` is their own work, which
answers the provenance question D3.99 was opened for. **The second half of that
row is what this gate is for, and the ruling does not touch it: worktree
isolation is REQUESTED, NOT ENFORCED.** Something wrote into the canonical tree
while five agents were told not to, and this arc dispatches four more.

## What is measured, per the brief

For every untracked path in the canonical tree: the **path**, its **mtime**, and
**whether any commit on any branch contains it**. The last is the discriminator.
A path some commit holds is a known artifact in an unusual state; a path no
commit anywhere holds is work that exists only as bytes on a disk, which is
exactly what ARC 024 proved a `git checkout` erases and what D3.99 proved nobody
can attribute after the fact.

## Why the CANONICAL path and not `.`

**This gate names `/home/bbt/nix` and measures it wherever the gate itself is
running.** The subject is a sub-agent, in a worktree, writing into the canonical
tree — so a gate that measured "the tree I am in" would be blind in exactly the
configuration the defect occurs in: every dispatched agent would cheerfully
report its own worktree clean while the canonical tree accumulated unattributed
files. `check_canonical_tree` names the same constant for the same reason.

## §7.12 — what would have to be true for this to PASS while measuring nothing?

1. **`git` answers about the wrong repository.** `GIT_DIR` and `GIT_INDEX_FILE`
   are honoured AHEAD of `-C` (D3.22), and this project has been bitten by
   hook-injected git environment twice. *Closed:* every invocation runs under
   `scrubbed_env`, and the gate asserts `rev-parse --show-toplevel` resolves to
   the canonical path before believing any answer from it.
2. **`--untracked-files=normal` collapses a whole directory to one entry.** A
   sub-agent writing `scripts/newdir/{a,b,c}.py` would appear as a single line,
   and a per-file attribution over it would report on one path and miss two.
   *Closed:* `-uall`, asserted by a test that plants a nested directory.
3. **The expected-path allowlist grows until it covers everything.** *Closed:*
   the allowlist is three narrow anchored globs, every one of them justified in
   `EXPECTED` below, and `test_a_plant_outside_the_allowlist_is_caught` fails the
   day a pattern is widened enough to swallow a plant in `scripts/`.
4. **Nothing is untracked, ever, so the gate is furniture.** That is the healthy
   state and it must not read as strength: the verdict carries the number of
   untracked paths examined, so a PASS over zero paths is legible as such rather
   than as a clean sweep.

## The residual, named rather than implied

**Ignored files are invisible to this gate, and that is failure mode #14.**
`.gitignore` excludes `state/` wholesale, `.venv/`, every `__pycache__`; a
sub-agent writing into any of them is unseen here exactly as it is unseen by
`pre-commit run --all-files`. Adding `--ignored` would drown the signal in
thousands of cache entries and is not the trade. CHECK-DEBT carries the row.
"""

# pylint: disable=duplicate-code
# R0801 pairs this module's §4.4 declaration preamble with every other check that
# shells out to git. THE DUPLICATION CANNOT BE FACTORED OUT AND THAT IS THE
# DESIGN: `PRIVILEGE`, `DEPENDS_ON`, `RESOURCES` and the rest are read
# STATICALLY, by AST, without importing the check (check contract §4.4), so a
# shared base module would be invisible to that reader.
from __future__ import annotations

import dataclasses
import fnmatch
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
import time
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import scrubbed_env

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first: this gate reads repository state and no artifact any
#: other check produces.
DEPENDS_ON: tuple[str, ...] = ()
#: `git` is claimed because this gate SPAWNS it. The `stat` of each untracked
#: path is a read-only filesystem read holding nothing another check contends
#: for, and is deliberately not claimed — the same call `check_canonical_tree`
#: makes, and `check_observed_resource_claims` will report on this file like any
#: other. If the observer sees more, the observer is right.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
#: FALSE on the facts: two git invocations plus one `git log` per untracked path.
#: On a healthy tree that is a handful of milliseconds.
TIME_BOUND = False
#: NON-CORRECTABLE, and the reason is the whole point of the gate. The only
#: mechanical "corrections" available are to commit the file or delete it. Both
#: are catastrophic as automation: committing adopts unattributable work into a
#: safety spine on the strength of its existence, which is the disposition D3.99
#: was opened to REFUSE; deleting destroys the only copy, which ARC 026 measured
#: the cost of at this exact path (the orphaned tree held the only copy of the
#: arc brief being executed). An instrument that cannot tell "an agent escaped
#: its worktree" from "the operator is working" must not be given `git rm`.
#: Report the path, the mtime and the attribution; let a human rule.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the two available repairs are `git add` and `rm`, and both are wrong as "
    "automation: adopting unattributable work into a safety spine is the "
    "disposition D3.99 exists to refuse, and deleting may destroy the only copy "
    "on the machine. The gate reports path, mtime and attribution; an operator "
    "rules on provenance"
)
#: This gate's subject is repository state, not a tracked file.
SUBJECTS: tuple[str, ...] = ()

NAME = "check_untracked_attribution"

#: The canonical path, absolute and stable. Measured wherever this gate runs —
#: see the module docstring: a gate that measured "the tree I am in" would be
#: blind in precisely the configuration the defect occurs in.
CANONICAL = Path("/home/bbt/nix")

#: Untracked paths that are EXPECTED and carry their own provenance. Three narrow
#: anchored globs, each justified:
#:
#: * `downloads/arc_0*.md` — the arc brief. Delivered by the architect, by hand,
#:   and deliberately never committed until close-out. ARC 028's opening
#:   `git status --short` showed exactly this one path.
#: * `checks/*.json.proposed` — `verify.py --optimize` writes a PROPOSAL and
#:   requires `--commit` to install it. An uncommitted proposal is the mechanism
#:   working, not an escape.
#: * `downloads/RESULTS.md` — overwritten every arc by mandate and committed at
#:   close-out; untracked only in the window before an arc's first write-back.
#:
#: A pattern added here must name why, because every addition is a hole. The
#: allowlist is asserted by test, not trusted.
EXPECTED: tuple[str, ...] = (
    "downloads/arc_0*.md",
    "checks/*.json.proposed",
    "downloads/RESULTS.md",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git under a SCRUBBED environment. `-C` alone is not enough (D3.22)."""
    return subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=scrubbed_env(),
    )


def untracked_paths(repo: Path) -> list[str]:
    """Every path that has APPEARED without being committed. `-uall` (§7.12 #2).

    **Two porcelain states, not one, and the second is ARC 024's exact failure.**
    `??` is an untracked file. `A ` is a file that has been `git add`ed and never
    committed — and ARC 024 PASSED ITS CLOSE-OUT with thirty paths in precisely
    that state, where an mtime proved they had been written while a `git checkout`
    would have erased every one.

    Measured while building this gate, on itself: staging the new check silenced
    it. A detector for "work that exists only as bytes on a disk" that a single
    `git add` turns off would be worse than none, because the mandated
    `git add -A` before every gate measurement RUNS THAT COMMAND for you. The
    index is not the record; `HEAD`'s tree is.
    """
    proc = _git(repo, "status", "--porcelain", "-uall")
    if proc.returncode != 0:
        return []
    return [
        line[3:].strip().strip('"')
        for line in proc.stdout.splitlines()
        if line[:2] in ("??", "A ", "AM")
    ]


def commits_containing(repo: Path, path: str) -> list[str]:
    """Commits on ANY branch whose tree holds `path`. Empty means unattributed.

    `--all` is the load-bearing flag: a file committed on a sub-agent's own
    branch and never merged is ATTRIBUTABLE — somebody's history holds it — and
    is a different condition from work that exists only as bytes on a disk.
    """
    proc = _git(repo, "log", "--all", "--oneline", "--", path)
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def is_expected(path: str) -> bool:
    """Does this path match an EXPECTED glob? Anchored, never a substring."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXPECTED)


@dataclasses.dataclass(frozen=True)
class Attribution:
    """One untracked path with the brief's triple, plus its allowlist verdict.

    A typed record rather than a dict: the verdict below arithmetics over
    `commits`, and a `dict[str, object]` makes that arithmetic unverifiable —
    mypy cannot tell a count from a path, so a comparison against the wrong key
    would type-check and be wrong at runtime.
    """

    path: str
    mtime: str
    commits: int
    expected: bool


def attribute(repo: Path, paths: list[str]) -> list[Attribution]:
    """Path, mtime and attribution for each untracked path — the brief's triple."""
    rows: list[Attribution] = []
    for path in sorted(paths):
        target = repo / path
        try:
            mtime = target.stat().st_mtime
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        except OSError:
            stamp = "unreadable"
        rows.append(
            Attribution(
                path=path,
                mtime=stamp,
                commits=len(commits_containing(repo, path)),
                expected=is_expected(path),
            )
        )
    return rows


def evaluate(repo: Path, toplevel: str, rows: list[Attribution]) -> CheckResult:
    """Verdict from the attribution table. Unattributed and unexpected is red."""
    if toplevel != str(repo):
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(repo),
            detail=f"git resolved the toplevel to {toplevel!r}, not {repo} — the "
            "answer would be about another repository, and a safety property "
            "proven against the wrong subject is not proven (§17)",
        )

    unattributed = [row for row in rows if not row.expected and row.commits == 0]
    examined = len(rows)
    if unattributed:
        listed = ", ".join(
            f"{row.path} (mtime {row.mtime}, in NO commit on any branch)"
            for row in unattributed
        )
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=", ".join(row.path for row in unattributed),
            evidence=f"{len(unattributed)} unattributed of {examined} untracked "
            f"path(s) examined in {repo}",
            detail=f"work exists in the canonical tree that no commit on any "
            f"branch contains: {listed}. A file's presence on disk is evidence of "
            f"nothing and `git checkout` erases it (ARC 024); if a dispatched "
            f"agent wrote this, worktree isolation was requested and not enforced "
            f"(D3.99). Rule on provenance before adopting it",
        )

    return CheckResult(
        name=NAME,
        status=Status.PASS,
        site=str(repo),
        evidence=f"{examined} untracked path(s) examined, "
        f"{sum(1 for row in rows if row.expected)} expected, "
        f"{sum(1 for row in rows if row.commits)} attributed to a commit on "
        f"some branch; 0 unattributed",
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Attribute every untracked appearance in the canonical tree."""
    if not (CANONICAL / ".git").exists():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(CANONICAL),
            detail=f"{CANONICAL} holds no .git — the canonical tree is not "
            "readable from here, and an unobservable subject is never a pass "
            "(§17)",
        )
    toplevel = _git(CANONICAL, "rev-parse", "--show-toplevel").stdout.strip()
    return evaluate(
        CANONICAL, toplevel, attribute(CANONICAL, untracked_paths(CANONICAL))
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
