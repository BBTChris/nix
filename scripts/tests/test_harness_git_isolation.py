"""`scripts/harness.py` may not touch the git index of whatever runs it.

ARC 035 / Stage 1 sub-agent C, banked at Stage 2 integration.

## The defect, and why it was invisible for four arcs

`harness.py:build()` makes five `git` subprocess calls to stand up its fixture
repository. Under a git hook, git **exports** `GIT_DIR` and `GIT_INDEX_FILE`
into the hook's environment, and **`git -C <dir>` does not override them** — `-C`
changes the working directory, while repository discovery stops at the inherited
`GIT_DIR`. So `git add -A` inside the fixture wrote the FIXTURE's tree into the
INVOKING repository's index and dropped every other entry from it.

It was dormant because `harness.py` carried a hard-coded
`/home/claude/work/monitor.py` — an absolute path from another machine — and
`sys.exit`ed before `build()` ever ran. **ARC 035 / Phase 0.2 fixed that path,
and the portability fix switched the index-corrupting defect on.** Phase 0.2 also
registered `checks/check_monitor_tui.py`, which EXECUTES `harness.py`, and the
pre-commit runtime gate runs that check — so the defect went from unreachable to
running inside every commit in the same arc.

MEASURED consequence, on a live worktree mid-commit: the index reduced to one
entry, ~430 tracked paths staged as deletions, and `seed.txt` — a string that
exists nowhere but `harness.py` — staged into a repository that has never
contained it. The seven `git ls-files`-based gates below it in the run then
failed their NON-VACUITY floors, because the tree they measure had been emptied.
Seven "regressions" with one cause and none of them in the code they named.

## What this test does, and why the CONTROL is the point

A victim repository is built in a scratch directory and its `.git/index` is
hashed. `harness.py` is then run with `GIT_DIR` and `GIT_INDEX_FILE` pointed at
the victim — exactly what a hook exports — and the index is hashed again.

* **`test_the_UNSCRUBBED_harness_CORRUPTS_the_victim_index`** runs a copy with the
  `env=GIT_ENV` arguments STRIPPED and requires the index to CHANGE. Without this
  half, "the index did not change" would be satisfied by a harness that failed to
  start, by a `git` that is not installed, and by a test that pointed at the wrong
  file. It proves the instrument can see the defect.
* **`test_the_SHIPPED_harness_LEAVES_the_victim_index_BYTE_IDENTICAL`** runs the
  real file and requires the hash to be unchanged.

Both halves point `GIT_DIR` and `GIT_INDEX_FILE` at the victim, so even the
deliberately unscrubbed run cannot reach a real repository. `GIT_WORK_TREE` is
deliberately NOT set — see the comment in `_run_harness_against`; setting it
masks the defect entirely and the first draft of this test passed vacuously
because of it.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Test names spell the OUTCOME they assert in the case the argument uses.
import hashlib
import os
import shutil
import subprocess  # nosec B404 - running git and the harness IS the subject
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))
# pylint: disable=wrong-import-position
from nixverify.gitenv import scrubbed_env

HARNESS = REPO / "scripts" / "harness.py"
MONITOR = REPO / "scripts" / "monitor.py"

#: The five call sites, as they read AFTER the fix. Stripping this suffix is the
#: plant, and its count is asserted so a plant that matches nothing is a loud
#: red rather than a silent no-op (debug.md §8 failure mode #4).
SCRUB_ARG = ", env=GIT_ENV"
EXPECTED_SCRUBBED_CALLS = 5

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is the instrument here"
)


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        # D3.205: was a PRIVATE re-spelling of the scrub (the sixth on the
        # tree). `check_git_env_scrub` derives call sites rather than
        # remembering them, and found it.
        env=scrubbed_env(),
    )
    assert proc.returncode == 0, f"git {args}: {proc.stderr}"


def _victim(tmp_path: Path) -> Path:
    """A real repository with one real tracked file, and a clean index."""
    victim = tmp_path / "victim"
    victim.mkdir()
    _git(victim, "init", "-q", ".")
    _git(victim, "config", "user.email", "t@t")
    _git(victim, "config", "user.name", "t")
    (victim / "important.py").write_text("# a file the victim really tracks\n")
    _git(victim, "add", "-A")
    _git(victim, "commit", "-qm", "base")
    return victim


def _status(victim: Path) -> str:
    """`git status --short` for the victim, under a SCRUBBED environment.

    D3.22, landing on this test's own instrument and caught by the commit gate
    that runs it. Inside a pre-commit hook `GIT_INDEX_FILE` is exported and
    points at the REAL repository; an unscrubbed `git status` run with
    `cwd=victim` therefore compares the REAL repo's index against the VICTIM's
    working tree and reports the entire Nix tree as deleted. The digest
    comparison was already correct and passed; it was this reporting call that
    failed, which is the tidiest possible demonstration that `git -C` and `cwd=`
    are not substitutes for scrubbing the environment.
    """
    return subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "status", "--short"],
        cwd=victim,
        capture_output=True,
        text=True,
        check=False,
        # D3.205: was a PRIVATE re-spelling of the scrub (the sixth on the
        # tree). `check_git_env_scrub` derives call sites rather than
        # remembering them, and found it.
        env=scrubbed_env(),
    ).stdout


def _index_digest(victim: Path) -> str:
    return hashlib.sha256((victim / ".git" / "index").read_bytes()).hexdigest()


def _run_harness_against(victim: Path, harness: Path) -> None:
    """Run `harness` with the victim's git environment exported, as a hook does.

    The harness's own exit code is deliberately NOT asserted: it exits 1 on this
    node because of the ten pinned MON-1 failures (`check_monitor_tui.KNOWN_RED`),
    and this test's subject is the victim's index, not the TUI's verdict.
    """
    # `GIT_DIR` and `GIT_INDEX_FILE` ONLY — deliberately NOT `GIT_WORK_TREE`.
    #
    # MEASURED while writing this test, and it is the reason the both-halves
    # control exists: adding `GIT_WORK_TREE` MASKS the defect completely. With
    # it set, the fixture's `git -C <fixture> add -A` resolves its worktree to
    # the VICTIM and re-adds the victim's own files, so the index comes back
    # byte-identical and the control goes silent — `30d7c773 -> c46768e2` without
    # it, `0df6ce02 -> 0df6ce02` with it, same code, same harness.
    #
    # The first draft of this test set all three and its CONTROL passed
    # vacuously. That is the whole §7.12 question landing on the instrument
    # rather than the subject, and it is what a control is for.
    #
    # Two variables is also the honest shape: a pre-commit hook exports `GIT_DIR`
    # and `GIT_INDEX_FILE`, and that pair alone is what reaches the child.
    env = dict(os.environ)
    env["GIT_DIR"] = str(victim / ".git")
    env["GIT_INDEX_FILE"] = str(victim / ".git" / "index")
    env.pop("GIT_WORK_TREE", None)
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, str(harness)],
        cwd=victim,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=env,
    )
    # NON-VACUITY FLOOR. A harness that failed to start writes nothing to the
    # victim's index either, so "the index did not change" would be satisfied by
    # a broken instrument. `build()` is where the five git calls live, and
    # SCENARIO 1 is the first thing printed after it returns, so its presence is
    # proof the corrupting code path was actually reached.
    assert "SCENARIO 1" in proc.stdout, (
        f"harness {harness} never reached SCENARIO 1, so build() and its five "
        f"git calls never ran and nothing was measured. rc={proc.returncode} "
        f"stdout={proc.stdout[-400:]!r} stderr={proc.stderr[-400:]!r}"
    )


def test_the_shipped_harness_scrubs_all_five_git_calls() -> None:
    """The plant anchor exists, at the count the CONTROL below depends on."""
    source = HARNESS.read_text()
    assert source.count(SCRUB_ARG) == EXPECTED_SCRUBBED_CALLS, (
        f"{SCRUB_ARG!r} appears {source.count(SCRUB_ARG)} times, expected "
        f"{EXPECTED_SCRUBBED_CALLS}. Either a git call lost its scrub, or the "
        f"CONTROL below is planting nothing"
    )


def test_the_UNSCRUBBED_harness_CORRUPTS_the_victim_index(tmp_path: Path) -> None:
    """THE CONTROL. Strip the scrub and the defect comes straight back.

    Without this half the sibling test below is satisfied by a harness that
    never ran. Every `GIT_*` here points at the victim, so the deliberately
    broken copy cannot reach a real repository.
    """
    victim = _victim(tmp_path)
    before = _index_digest(victim)

    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    shutil.copyfile(MONITOR, broken_dir / "monitor.py")
    broken = broken_dir / "harness.py"
    broken.write_text(HARNESS.read_text().replace(SCRUB_ARG, ""))

    _run_harness_against(victim, broken)
    after = _index_digest(victim)

    assert after != before, (
        "the UNSCRUBBED harness left the victim's index byte-identical — the "
        "control cannot see the defect, so the sibling test's green means "
        "nothing. Check that GIT_DIR/GIT_INDEX_FILE really reached the child"
    )
    status = _status(victim)
    assert "seed.txt" in status or "important.py" in status, status


def test_the_SHIPPED_harness_LEAVES_the_victim_index_BYTE_IDENTICAL(
    tmp_path: Path,
) -> None:
    """The fix, measured on the file that actually ships."""
    victim = _victim(tmp_path)
    before = _index_digest(victim)
    _run_harness_against(victim, HARNESS)
    after = _index_digest(victim)
    assert after == before, (
        f"scripts/harness.py mutated the invoking repository's index "
        f"({before[:12]} -> {after[:12]}). D3.22: every subprocess git call "
        f"takes the scrubbed environment, and `git -C` is not a substitute"
    )
    status = _status(victim)
    assert status.strip() == "", f"the victim tree is no longer clean:\n{status}"
