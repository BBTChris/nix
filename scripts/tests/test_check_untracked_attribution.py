"""Tests for `checks/check_untracked_attribution.py` (ARC 029 / 0.3).

The gate exists because ARC 028's escape was caught by LUCK: two artifacts
appeared at `/home/bbt/nix` during a five-sub-agent Stage 1, in no commit on any
branch, and were noticed only because the mandated `git add -A` staged them into
three commit gates that happened to redden on their formatting. A file that was
merely well-formatted would have passed through in silence.

Every control here drives a CONSTRUCTED repository. The gate names
`/home/bbt/nix` in production — deliberately, because the defect is an agent in a
worktree writing into the canonical tree — but a test that measured the live tree
would be reporting on whatever this session happens to have left lying about,
which is D3.100's rule exactly: an instrument whose input is the ambient state
measures the ambient state, not the property.
"""

# pylint: disable=invalid-name,import-outside-toplevel
# Test names SHOUT the property under test, as in every other suite here.

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, test-local paths
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "checks"))
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
# The `sys.path` bootstrap above must run BEFORE these imports — the shape every
# check in this tree uses via `_preamble`.
import check_untracked_attribution as gate  # pylint: disable=import-error
from nixverify.contract import Status
from nixverify.gitenv import scrubbed_env

# pylint: enable=wrong-import-position


def _git(repo: Path, *args: str) -> None:
    """Run git in a test repo under the same scrub the gate uses."""
    subprocess.run(  # nosec B603 B607 - fixed argv, test-local paths
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=scrubbed_env(),
    )


@pytest.fixture(name="repo")
def _repo(tmp_path: Path) -> Path:
    """A real git repository with one committed file and a clean tree."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.py")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _verdict(repo: Path):
    """Run the gate's real evaluation against `repo`, as production would."""
    return gate.evaluate(
        repo, str(repo), gate.attribute(repo, gate.untracked_paths(repo))
    )


def test_a_clean_tree_PASSES_and_says_how_many_paths_it_examined(repo: Path) -> None:
    """A pass over zero paths must be legible as such, not as a clean sweep."""
    result = _verdict(repo)
    assert result.status is Status.PASS
    assert "0 untracked path(s) examined" in result.evidence


def test_an_UNATTRIBUTED_file_is_caught_with_its_path_and_mtime(repo: Path) -> None:
    """The measured defect, as a test: bytes on a disk, in no commit anywhere."""
    (repo / "scripts").mkdir()
    (repo / "scripts" / "nix_status.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    result = _verdict(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "scripts/nix_status.sh" in result.site
    assert "in NO commit on any branch" in result.detail
    # The mtime is one of the three facts the brief requires, so it is asserted
    # rather than assumed to be in there somewhere.
    assert "mtime 20" in result.detail


def test_a_file_COMMITTED_ON_ANOTHER_BRANCH_is_attributed_not_red(repo: Path) -> None:
    """`--all` is the discriminator, and this is what it buys.

    A sub-agent's file committed on its own unmerged branch is ATTRIBUTABLE —
    somebody's history holds it — which is a different condition from work that
    exists only on a disk. Without `--all` this would read as an escape and the
    gate would cry wolf on every legitimate parallel branch.
    """
    _git(repo, "checkout", "-q", "-b", "sub-agent-a")
    (repo / "agent_work.py").write_text("y = 2\n", encoding="utf-8")
    _git(repo, "add", "agent_work.py")
    _git(repo, "commit", "-q", "-m", "agent work")
    _git(repo, "checkout", "-q", "main")
    # Now recreate it as an untracked file on main: some commit holds this path.
    (repo / "agent_work.py").write_text("y = 2\n", encoding="utf-8")

    rows = gate.attribute(repo, gate.untracked_paths(repo))
    assert [row.path for row in rows] == ["agent_work.py"]
    assert rows[0].commits >= 1
    assert _verdict(repo).status is Status.PASS


@pytest.mark.parametrize(
    "path",
    ["downloads/arc_029_r2b_the_exit_half.md", "checks/registry.json.proposed"],
)
def test_an_EXPECTED_path_carries_its_own_provenance(repo: Path, path: str) -> None:
    """The allowlist, exercised on the two shapes that legitimately appear."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("content\n", encoding="utf-8")
    assert _verdict(repo).status is Status.PASS


def test_a_plant_OUTSIDE_the_allowlist_is_caught(repo: Path) -> None:
    """The allowlist must not be wide enough to swallow a real escape.

    This fails the day a pattern is broadened — which is the §7.12 answer for
    "the allowlist could grow until it covers everything".
    """
    (repo / "downloads").mkdir()
    # Adjacent to an allowlisted glob and deliberately not matching it.
    (repo / "downloads" / "notes.md").write_text("x\n", encoding="utf-8")
    assert _verdict(repo).status is Status.FAIL_NEEDS_OPERATOR


def test_a_STAGED_but_UNCOMMITTED_file_is_still_an_appearance(repo: Path) -> None:
    """ARC 024's exact failure, and `git add` must not be able to silence a gate.

    ARC 024 PASSED ITS CLOSE-OUT with thirty paths staged and never committed: an
    mtime proved they had been written, while a `git checkout` would have erased
    every one. `git status --porcelain` reports that state as `A `, not `??`.

    Measured on this gate, against itself, while it was being built: staging the
    new check silenced it. That matters more than it looks, because the standing
    close-out rule runs `git add -A` BEFORE every gate measurement — so a detector
    keyed on `??` alone would be switched off by the very procedure meant to
    expose the work. The index is not the record; HEAD's tree is.
    """
    (repo / "escaped.py").write_text("w = 3\n", encoding="utf-8")
    _git(repo, "add", "escaped.py")
    assert gate.untracked_paths(repo) == ["escaped.py"]
    result = _verdict(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "escaped.py" in result.site


def test_a_NESTED_DIRECTORY_is_enumerated_PER_FILE(repo: Path) -> None:
    """`-uall`, never `normal`.

    With `--untracked-files=normal` git reports the DIRECTORY as one entry, so a
    per-file attribution over it would report one path and miss the rest — a gate
    that says "1 unattributed" when there are three is understating an escape.
    """
    nest = repo / "scripts" / "newdir"
    nest.mkdir(parents=True)
    for name in ("a.py", "b.py", "c.py"):
        (nest / name).write_text("z = 0\n", encoding="utf-8")
    found = gate.untracked_paths(repo)
    assert sorted(found) == [
        "scripts/newdir/a.py",
        "scripts/newdir/b.py",
        "scripts/newdir/c.py",
    ]


def test_a_TOPLEVEL_MISMATCH_is_CANNOT_MEASURE_never_a_pass() -> None:
    """§17: a property proven against the wrong subject is not proven.

    `GIT_DIR`/`GIT_INDEX_FILE` outrank `-C` and have bitten this project twice
    (D3.22, and the `core.bare` incident). If git answers about another
    repository the verdict must be unmeasurable, not green.
    """
    result = gate.evaluate(Path("/home/bbt/nix"), "/somewhere/else", [])
    assert result.status is Status.CANNOT_MEASURE
    assert "another repository" in result.detail


def test_the_gate_names_the_CANONICAL_PATH_and_not_the_CWD() -> None:
    """The subject is an agent in a worktree writing into the canonical tree.

    A gate measuring "the tree I am in" would be blind in exactly that
    configuration: every dispatched agent would report its own worktree clean
    while the canonical tree accumulated unattributed files. Pinned as a
    constant so the property cannot be refactored away quietly.
    """
    assert gate.CANONICAL == Path("/home/bbt/nix")
    source = Path(gate.__file__).read_text(encoding="utf-8")
    assert "Path.cwd()" not in source


def test_every_git_call_runs_under_a_SCRUBBED_environment() -> None:
    """D3.22: `-C` alone does not protect against an inherited `GIT_DIR`."""
    source = Path(gate.__file__).read_text(encoding="utf-8")
    assert "env=scrubbed_env()" in source
    assert source.count("subprocess.run") == 1, (
        "every git invocation must go through the single scrubbed helper"
    )


# ===========================================================================
# ARC 030 / Stage 2 A3 — the foreign-commit arm (the ARC 029 collision vector
# the untracked arm alone cannot see: a WRITE already committed, on a branch
# this arc's HEAD does not contain).
# ===========================================================================


def _own_head(repo: Path) -> str:
    head = gate.resolve_head(repo)
    assert head is not None
    return head


def test_a_LIVE_worktree_branchs_commit_is_NOT_a_foreign_finding(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The common, healthy state: a sibling arc's worktree is still checked
    out on its own branch with unmerged commits touching a shared tracked
    file — exactly what running THIS arm from within a live multi-arc
    dispatch looks like every day. It must not redden.
    """
    wt = tmp_path_factory.mktemp("wt")
    _git(repo, "worktree", "add", "-q", "-b", "sibling-arc", str(wt), "main")
    (wt / "tracked.py").write_text("x = 2\n", encoding="utf-8")
    _git(wt, "add", "tracked.py")
    _git(wt, "commit", "-q", "-m", "sibling work")

    own_head = _own_head(repo)
    live, complaint = gate.live_worktree_branches(repo)
    assert not complaint
    assert "sibling-arc" in live
    tracked = gate.tracked_at(repo, own_head)
    assert tracked is not None

    findings = gate.foreign_branch_commits(repo, own_head, live, tracked)
    assert findings == []


def test_a_NON_LIVE_branchs_commit_on_a_TRACKED_path_IS_a_foreign_finding(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The defect shape: identical commit to the test above, but the
    worktree backing that branch has since been torn down (the ordinary
    end-of-dispatch cleanup) — so the branch is no longer "live", and its
    commit against an already-tracked file is exactly what this arm exists
    to name.
    """
    wt = tmp_path_factory.mktemp("wt2")
    _git(repo, "worktree", "add", "-q", "-b", "stray-arc", str(wt), "main")
    (wt / "tracked.py").write_text("x = 3\n", encoding="utf-8")
    _git(wt, "add", "tracked.py")
    _git(wt, "commit", "-q", "-m", "stray work")
    _git(repo, "worktree", "remove", "--force", str(wt))

    own_head = _own_head(repo)
    live, complaint = gate.live_worktree_branches(repo)
    assert not complaint
    assert "stray-arc" not in live
    tracked = gate.tracked_at(repo, own_head)
    assert tracked is not None

    findings = gate.foreign_branch_commits(repo, own_head, live, tracked)
    assert findings is not None
    assert len(findings) == 1
    assert findings[0].branch == "stray-arc"
    assert findings[0].path == "tracked.py"
    assert findings[0].author == "t"


def test_a_NON_LIVE_branchs_NEW_file_is_NOT_reported_only_TRACKED_paths_are(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A sibling's own brand-new file (not yet in canonical's tree) is that
    sibling's future contribution, not a collision with anything canonical
    holds today — reporting it would make every normal sibling arc's net-new
    work redden, which is the noise this arm's design deliberately avoids
    (module docstring, "why NOT `--all` a second time").
    """
    wt = tmp_path_factory.mktemp("wt3")
    _git(repo, "worktree", "add", "-q", "-b", "stray-new-file", str(wt), "main")
    (wt / "brand_new.py").write_text("y = 1\n", encoding="utf-8")
    _git(wt, "add", "brand_new.py")
    _git(wt, "commit", "-q", "-m", "new work")
    _git(repo, "worktree", "remove", "--force", str(wt))

    own_head = _own_head(repo)
    live, _ = gate.live_worktree_branches(repo)
    tracked = gate.tracked_at(repo, own_head)
    assert tracked is not None
    assert "brand_new.py" not in tracked

    findings = gate.foreign_branch_commits(repo, own_head, live, tracked)
    assert findings == []


def test_evaluate_reports_a_FOREIGN_COMMIT_as_FAIL_NEEDS_OPERATOR(repo: Path) -> None:
    """`evaluate()`'s own composition of the two arms, driven directly."""
    finding = gate.ForeignCommit(
        branch="stray-arc",
        sha="deadbeefcafe",
        author="someone",
        date="2026-08-14T00:00:00-05:00",
        path="tracked.py",
    )
    result = gate.evaluate(repo, str(repo), [], foreign=[finding])
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "stray-arc" in result.detail
    assert "tracked.py" in result.site
    assert "ARC 029 collision vector" in result.detail


def test_evaluate_PASS_names_ZERO_foreign_commits_explicitly(repo: Path) -> None:
    """A PASS over zero foreign commits must be legible as such, not implied."""
    result = gate.evaluate(repo, str(repo), [], foreign=[])
    assert result.status is Status.PASS
    assert "0 foreign committed writes" in result.evidence


def test_a_foreign_complaint_is_CANNOT_MEASURE_never_a_silent_pass(
    repo: Path,
) -> None:
    """§17: the arm being unable to answer must sink the WHOLE gate's
    verdict, not just be dropped — a PASS composed from one arm that
    answered and one that could not is a PASS about half the subject.
    """
    result = gate.evaluate(
        repo, str(repo), [], foreign_complaint="git for-each-ref did not answer"
    )
    assert result.status is Status.CANNOT_MEASURE
    assert "did not answer" in result.detail


# ---------------------------------------------------------------------------
# THE HONEST BOUNDARY, MEASURED DIRECTLY (CHECK-DEBT D3.114): a commit on a
# DETACHED HEAD, in a worktree later removed without ever being named by a
# branch, is invisible to `--all` — and therefore to this arm — the instant
# the worktree is removed, even though the object is still physically
# present. Reproduced here as a committed, re-runnable proof, not merely
# asserted in prose.
# ---------------------------------------------------------------------------


def test_a_DETACHED_worktree_commit_IS_visible_via_ALL_while_it_lives(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """First, falsify the naive assumption: `git log --all` is worktree-
    aware, and finds a detached-HEAD commit while its worktree still exists
    — this is NOT the boundary (the module docstring is explicit about why).
    """
    wt = tmp_path_factory.mktemp("wt4")
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), "main")
    (wt / "detached_only.py").write_text("x = 9\n", encoding="utf-8")
    _git(wt, "add", "detached_only.py")
    _git(wt, "commit", "-q", "-m", "detached edit")

    # sees it: --all is worktree-aware. Must be a path NOT already present at
    # `main`'s own HEAD, or the base commit itself would satisfy the query
    # regardless of whether the detached commit is visible.
    assert gate.commits_containing(repo, "detached_only.py")

    _git(repo, "worktree", "remove", "--force", str(wt))


def test_a_DETACHED_worktree_commit_becomes_INVISIBLE_the_instant_its_worktree_is_removed(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The actual boundary. Identical setup to the test above, but this time
    the commit's sha is captured BEFORE removal and re-checked after: still
    a real object in the store (`git cat-file -t` succeeds), no longer found
    by ANY git-fact-based query this module has, including `--all`. This is
    why D3.114 is recorded rather than "solved" — no query available at gate
    time recovers a path/branch/author for a dangling object.
    """
    wt = tmp_path_factory.mktemp("wt5")
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), "main")
    (wt / "orphan_only.py").write_text("x = 10\n", encoding="utf-8")
    _git(wt, "add", "orphan_only.py")
    _git(wt, "commit", "-q", "-m", "orphaned detached edit")
    sha = _own_head(wt)

    assert gate.commits_containing(repo, "orphan_only.py")  # visible before removal

    _git(repo, "worktree", "remove", "--force", str(wt))

    assert not gate.commits_containing(repo, "orphan_only.py"), (
        "the object must still be unreachable, not merely renamed — asserted "
        "below by direct cat-file, not inferred from this alone"
    )
    # The object is still PHYSICALLY present (not yet gc'd) — this is a
    # visibility gap, not data loss, and that distinction is the whole point
    # of recording it as CHECK-DEBT rather than claiming it cannot happen.
    cat = subprocess.run(  # nosec B603 B607 - fixed argv, test-local paths
        ["git", "-C", str(repo), "cat-file", "-t", sha],
        capture_output=True,
        text=True,
        env=scrubbed_env(),
        check=False,
    )
    assert cat.returncode == 0
    assert cat.stdout.strip() == "commit"

    # And the foreign-commit arm, which is BUILT on `--all`-equivalent
    # reachability (`for-each-ref` + `--not`), inherits the identical blind
    # spot: nothing names this commit because no branch ever did.
    own_head = _own_head(repo)
    live, _ = gate.live_worktree_branches(repo)
    tracked = gate.tracked_at(repo, own_head)
    assert tracked is not None
    findings = gate.foreign_branch_commits(repo, own_head, live, tracked)
    assert findings == []
