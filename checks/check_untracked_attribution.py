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

## ARC 030 / Stage 2 A3 — the arm this gate was missing

The arm above answers "is this UNTRACKED path attributable to some commit
somewhere." It never asks the question ARC 029's actual collision was:
**can a COMMIT — already landed, nothing untracked about it — that this
arc's own lineage does not contain still be sitting in the canonical tree's
reachable history, unattributed to any live session?** Before this arc,
nothing here ever ran `git log`/`git branch` against anything but a single
untracked path handed to it by the first arm; a foreign commit that never
touched an untracked file (because it was, itself, the commit) was invisible
end to end.

**MEASURED FIRST, not assumed: `git log --all` is worktree-aware.** A
constructed three-worktree repo (`main`, `wt1`, `wt2`) plus a FOURTH,
DETACHED-HEAD worktree with one commit no branch ref names, proved `git log
--all -- <path>` from `wt1` finds that detached commit — git treats every
LIVE worktree's `HEAD`, branch or not, as an extra root for `--all`/`rev-
list --all`, specifically so `gc`/`prune` cannot eat a worktree's own
uncommitted-to-a-branch history. `--branches` (no `--all`) does NOT — it
saw only real branch tips. This directly falsifies the naive assumption that
a detached-HEAD commit is invisible to git-fact-based attribution while its
worktree is alive; §"the honest boundary" below is about what happens
AFTER that worktree is removed, which is a different, precisely measured
condition.

**The new arm, and why it is NOT `--all` a second time.** Blindly reporting
every commit reachable via `--all` but not from this arc's own HEAD would
redden constantly during completely normal operation: at any moment this
arc's sibling worktrees (`arc-030-stage2-b`, `arc-030-stage2-c`) hold
committed, unmerged, entirely legitimate work on branches this arc's HEAD
does not contain, and much of it touches files also tracked at canonical
HEAD (`CLAUDE.md`, `docs/CHECK-DEBT.md`, `sessions/SESSION.md`, …). Treating
that as an escape would make the gate cry wolf on every concurrent arc,
which is worse than not gating at all (it trains the ignore-and-override
reflex the untracked arm's own docstring warns about). So the new arm
narrows on the one fact the untracked arm's EXPECTED allowlist already
established as the right shape: **a branch backed by a currently LIVE
worktree is attributable to an active session; a branch with commits ahead
of this arc's own HEAD and NO live worktree behind it is not** — the same
"attributed vs. not" split, moved from the file domain to the commit domain.
Scoped further to paths already TRACKED at canonical's current HEAD (a
brand-new file that only exists on a sibling's own branch is that sibling's
future contribution, not a collision with anything canonical holds today).

## §7.12 for the new arm — what would make it PASS while measuring nothing?

1. **No local branches exist besides mine.** The common, healthy state — the
   evidence names how many branches were examined and how many commits found,
   so a PASS over zero examined branches reads as such, not as a clean sweep
   (same posture as the untracked arm's own condition 4).
2. **`git worktree list --porcelain` cannot be parsed and silently yields the
   empty set.** Closed: a parse yielding nothing is legitimate ONLY when the
   raw output was also empty; a non-empty output that fails to parse a single
   `worktree`/`branch` pair is a `git` shape this code does not understand and
   is CANNOT_MEASURE, not a silent "no live worktrees".
3. **A rogue actor stands up a throw-away worktree just long enough for this
   gate to run, to launder a foreign commit as "backed by a live worktree".**
   UNGUARDED and named, not fixed: "live worktree" is a real git fact but not
   an authoritative one — it proves *a* checkout exists right now, not *who*
   created it or *why*. Closing this needs attribution git does not carry
   (which dispatched agent owns which worktree), the same class of gap
   `check_untracked_attribution`'s own NON_CORRECTABLE_REASON names for the
   untracked arm: an instrument that cannot tell "an agent escaped its
   worktree" from "the operator is working" reports and lets a human rule.

## The honest boundary — measured, not asserted (CHECK-DEBT D3.114)

A commit made on a **detached HEAD** in a worktree that is later **removed**
without ever being pointed to by a surviving branch or tag becomes fully
invisible to `--all` — and therefore to this gate, in either arm — the
INSTANT the worktree is removed, even though the commit object is still
physically present in the shared object store (confirmed via `git fsck
--unreachable` after removal) and would be found by `--all` while that
worktree was still alive. Reproduced directly: a four-worktree scratch repo,
one worktree `--detach`ed and given one commit, `git log --all -- <path>`
from a sibling worktree finding it, `git worktree remove --force` on the
detached one, the identical `git log --all` call from the identical sibling
now finding nothing. **No git fact available at gate time recovers this**:
`git branch --contains <sha>` answers "which branches hold a SHA I already
have", the wrong direction for "does anything hold a SHA I don't know to ask
about"; `git fsck --unreachable` finds the dangling object but returns a bare
SHA with no path, branch, or authorship context to attribute it BY, and is
unbounded work over the whole object store, not a targeted query. This is
the residual named in `docs/CHECK-DEBT.md` D3.114 rather than built around:
an honest limit beats a green that measured nothing.
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
import json
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
#: This gate's subject is repository state, not a tracked file — except the
#: exceptions ledger the foreign-commit arm reads (ARC 030 / Stage 2 A3),
#: named here so it is not an uncovered artifact (`check_artifact_gate_
#: coverage`'s ratchet governs every tracked `.py`/`.json`).
SUBJECTS: tuple[str, ...] = ("checks/foreign_branch_exceptions.json",)

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


def load_branch_exceptions(checks_dir: Path) -> dict[str, str]:
    """`{branch: owning arc}` from `checks/foreign_branch_exceptions.json`.

    Absent file is `{}`, not an error — mirrors `check_python_transitive_
    deps.load_exceptions`: an empty ledger is the common, legitimate state
    (a repo with no stale foreign branches at all), and the file's own
    existence is not this arm's subject.
    """
    path = checks_dir / "foreign_branch_exceptions.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    exceptions = payload.get("exceptions", [])
    if not isinstance(exceptions, list):
        raise TypeError(f"{path}: 'exceptions' must be a list")
    return {
        str(entry["branch"]): str(entry.get("arc", ""))
        for entry in exceptions
        if isinstance(entry, dict) and "branch" in entry
    }


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


#: Header line for the foreign-commit log parse. `COMMIT\t` cannot be
#: confused with a filename `git log --name-only` would ever print (a path
#: component starting with a literal tab is quoted by git, never emitted
#: raw), so it is an unambiguous line-type discriminator without needing a
#: control character.
_LOG_FORMAT = "COMMIT\t%H\t%an\t%aI"


@dataclasses.dataclass(frozen=True)
class ForeignCommit:
    """One commit, on a branch this arc's HEAD does not contain and with no
    live worktree behind it, touching a path canonical HEAD already tracks.
    """

    branch: str
    sha: str
    author: str
    date: str
    path: str


def resolve_head(repo: Path) -> str | None:
    """`HEAD`'s sha at `repo`, or `None` on any git failure."""
    proc = _git(repo, "rev-parse", "HEAD")
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip()


def live_worktree_branches(repo: Path) -> tuple[frozenset[str], str]:
    """Branches currently backed by a live worktree, `(branches, complaint)`.

    `git worktree list --porcelain` blocks look like::

        worktree /path
        HEAD <sha>
        branch refs/heads/<name>

    with a `detached` line instead of `branch` for a worktree not on a
    branch — deliberately not collected here: a detached worktree gives a
    foreign commit nothing to be "backed by" in the sense this arm needs
    (see the module docstring's honest-boundary section — the moment a
    detached worktree is removed its commits stop being visible to
    `--all`-based tooling at all, this arm included).
    """
    proc = _git(repo, "worktree", "list", "--porcelain")
    if proc.returncode != 0:
        return (
            frozenset(),
            f"`git worktree list --porcelain` failed: {proc.stderr.strip()}",
        )
    branches = {
        line[len("branch refs/heads/") :]
        for line in proc.stdout.splitlines()
        if line.startswith("branch refs/heads/")
    }
    if not branches and proc.stdout.strip():
        return (
            frozenset(),
            (
                "`git worktree list --porcelain` produced non-empty output "
                "with no parseable `branch refs/heads/...` line — §7.12 "
                "condition 2"
            ),
        )
    return frozenset(branches), ""


def tracked_at(repo: Path, commit: str) -> frozenset[str] | None:
    """Paths tracked in `commit`'s tree, or `None` on git failure."""
    proc = _git(repo, "ls-tree", "-r", "--name-only", commit)
    if proc.returncode != 0:
        return None
    return frozenset(line.strip() for line in proc.stdout.splitlines() if line.strip())


@dataclasses.dataclass
class _LogCommit:
    """One parsed `--name-only` log record. Mutable: `paths` accumulates as
    the parser walks the commit's file list. A typed record rather than a
    dict for the same reason `Attribution` is one above: a `dict[str,
    object]` makes `.paths`'s element type unverifiable to both mypy and
    pylint, which is exactly the E1136 pylint raised against the dict form
    this replaced.
    """

    sha: str
    author: str
    date: str
    paths: list[str] = dataclasses.field(default_factory=list)


def _parse_name_only_log(output: str) -> list[_LogCommit]:
    """Parse `--name-only --pretty=format:{_LOG_FORMAT}` output into records."""
    commits: list[_LogCommit] = []
    current: _LogCommit | None = None
    for line in output.splitlines():
        if line.startswith("COMMIT\t"):
            if current is not None:
                commits.append(current)
            _, sha, author, date = line.split("\t", 3)
            current = _LogCommit(sha=sha, author=author, date=date)
        elif line.strip() and current is not None:
            current.paths.append(line.strip())
    if current is not None:
        commits.append(current)
    return commits


def _one_branch_findings(
    repo: Path, branch: str, own_head: str, tracked: frozenset[str]
) -> list[ForeignCommit] | None:
    """`foreign_branch_commits`'s per-branch arm, split out to keep both
    functions under the project's complexity ceiling (doctrine: a nested
    loop-of-loops-of-conditionals is exactly the shape a reviewer stops
    trusting, cognitive-complexity score or not). `None` on git failure,
    same contract as the caller.
    """
    proc = _git(
        repo,
        "log",
        branch,
        "--not",
        own_head,
        "--name-only",
        f"--pretty=format:{_LOG_FORMAT}",
    )
    if proc.returncode != 0:
        return None
    return [
        ForeignCommit(
            branch=branch,
            sha=commit.sha[:12],
            author=commit.author,
            date=commit.date,
            path=path,
        )
        for commit in _parse_name_only_log(proc.stdout)
        for path in commit.paths
        if path in tracked
    ]


def foreign_branch_commits(
    repo: Path,
    own_head: str,
    live_branches: frozenset[str],
    tracked: frozenset[str],
) -> list[ForeignCommit] | None:
    """Commits reachable from a non-live LOCAL branch, not from `own_head`,
    touching a path `tracked` already names. `None` on git failure — a
    branch enumeration or log call that cannot answer is CANNOT_MEASURE for
    this whole arm, never a silent "found nothing" (§17).
    """
    branches_proc = _git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/heads"
    )
    if branches_proc.returncode != 0:
        return None
    findings: list[ForeignCommit] = []
    for raw in branches_proc.stdout.splitlines():
        branch = raw.strip()
        if not branch or branch in live_branches:
            continue
        one = _one_branch_findings(repo, branch, own_head, tracked)
        if one is None:
            return None
        findings.extend(one)
    return findings


def evaluate(  # pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
    repo: Path,
    toplevel: str,
    rows: list[Attribution],
    foreign: list[ForeignCommit] | None = None,
    foreign_complaint: str = "",
    branch_exceptions: dict[str, str] | None = None,
) -> CheckResult:
    """Verdict from the attribution table AND the foreign-commit arm.

    Unattributed-untracked and unattributed-committed are both red; either
    arm being unable to measure is CANNOT_MEASURE for the whole gate, never
    a partial PASS (§17: a subject the gate could not reach is not proven
    clean by the arm that DID answer). A foreign commit whose BRANCH matches
    `branch_exceptions` (`checks/foreign_branch_exceptions.json`) is GUARDED
    rather than FAIL — a real, already-measured, named condition awaiting an
    operator decision, not a false positive to hide (§4.1 AMENDMENT 1).
    """
    if toplevel != str(repo):
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(repo),
            detail=f"git resolved the toplevel to {toplevel!r}, not {repo} — the "
            "answer would be about another repository, and a safety property "
            "proven against the wrong subject is not proven (§17)",
        )
    if foreign_complaint:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(repo),
            detail=f"the cross-branch-commit arm (ARC 030 / Stage 2 A3) could "
            f"not measure: {foreign_complaint}",
        )

    foreign = foreign or []
    branch_exceptions = branch_exceptions or {}
    unguarded = [f for f in foreign if f.branch not in branch_exceptions]
    guarded = [f for f in foreign if f.branch in branch_exceptions]
    unattributed = [row for row in rows if not row.expected and row.commits == 0]
    examined = len(rows)

    if unattributed or unguarded:
        parts = []
        sites = [row.path for row in unattributed]
        if unattributed:
            listed = ", ".join(
                f"{row.path} (mtime {row.mtime}, in NO commit on any branch)"
                for row in unattributed
            )
            parts.append(
                f"work exists in the canonical tree that no commit on any "
                f"branch contains: {listed}. A file's presence on disk is "
                f"evidence of nothing and `git checkout` erases it (ARC 024); "
                f"if a dispatched agent wrote this, worktree isolation was "
                f"requested and not enforced (D3.99)"
            )
        if unguarded:
            sites.extend(sorted({f.path for f in unguarded}))
            flisted = ", ".join(
                f"{f.branch}:{f.sha} touches {f.path} (author {f.author}, "
                f"{f.date}), no live worktree behind {f.branch}, not in "
                f"foreign_branch_exceptions.json"
                for f in unguarded
            )
            parts.append(
                f"{len(unguarded)} commit(s) exist on a branch this arc's "
                f"HEAD does not contain, touching path(s) canonical HEAD "
                f"already tracks, with no LIVE worktree currently backing "
                f"that branch (ARC 030 / Stage 2 A3 — the ARC 029 collision "
                f"vector): {flisted}"
            )
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=", ".join(sites),
            evidence=f"{len(unattributed)} unattributed of {examined} "
            f"untracked path(s) examined; {len(unguarded)} unguarded foreign "
            f"committed write(s) found ({len(guarded)} guarded)",
            detail="; ".join(parts) + ". Rule on provenance before adopting it",
        )

    if guarded:
        owners = sorted({branch_exceptions[f.branch] for f in guarded})
        glisted = ", ".join(f"{f.branch}:{f.sha} touches {f.path}" for f in guarded)
        return CheckResult(
            name=NAME,
            status=Status.GUARDED,
            site=", ".join(sorted({f.path for f in guarded})),
            evidence=f"{examined} untracked path(s) examined, 0 unattributed; "
            f"{len(guarded)} foreign committed write(s), all matched to a "
            f"named exception in foreign_branch_exceptions.json: {glisted}",
            detail="every foreign commit found is on a branch listed in "
            "foreign_branch_exceptions.json with its own justification; an "
            "operator decision (delete/merge the branch) still discharges "
            "this, it is not silently adopted",
            guard_owner=owners[0] if len(owners) == 1 else "; ".join(owners),
        )

    return CheckResult(
        name=NAME,
        status=Status.PASS,
        site=str(repo),
        evidence=f"{examined} untracked path(s) examined, "
        f"{sum(1 for row in rows if row.expected)} expected, "
        f"{sum(1 for row in rows if row.commits)} attributed to a commit on "
        f"some branch; 0 unattributed; 0 foreign committed writes (branch/"
        f"commit arm)",
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Attribute every untracked appearance AND every foreign committed
    write in the canonical tree.
    """
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
    rows = attribute(CANONICAL, untracked_paths(CANONICAL))

    own_head = resolve_head(ctx.nix_home)
    if own_head is None:
        return evaluate(
            CANONICAL,
            toplevel,
            rows,
            foreign_complaint=f"could not resolve HEAD at {ctx.nix_home} — this "
            "arc's own lineage is the reference point the arm compares every "
            "other branch's commits against",
        )
    live_branches, live_complaint = live_worktree_branches(CANONICAL)
    if live_complaint:
        return evaluate(CANONICAL, toplevel, rows, foreign_complaint=live_complaint)
    canonical_head = resolve_head(CANONICAL)
    tracked = tracked_at(CANONICAL, canonical_head) if canonical_head else None
    if canonical_head is None or tracked is None:
        return evaluate(
            CANONICAL,
            toplevel,
            rows,
            foreign_complaint=f"could not enumerate paths tracked at "
            f"{CANONICAL}'s current HEAD",
        )
    foreign = foreign_branch_commits(CANONICAL, own_head, live_branches, tracked)
    if foreign is None:
        return evaluate(
            CANONICAL,
            toplevel,
            rows,
            foreign_complaint="`git for-each-ref refs/heads` or a branch's "
            "`git log` did not answer",
        )
    exceptions = load_branch_exceptions(Path(__file__).resolve().parent)
    return evaluate(
        CANONICAL, toplevel, rows, foreign=foreign, branch_exceptions=exceptions
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
