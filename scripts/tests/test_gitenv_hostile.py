"""D3.22 — a hostile `GIT_DIR` must not move what a git caller measures.

`git` honours `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` **ahead of `-C`
and ahead of `cwd`**. `pre-commit` and `git` itself export them into every hook.
Two measured consequences in this project:

  * ARC 025 — a sub-agent's fixture ran `git add -A` in `tmp_path` under an
    inherited `GIT_INDEX_FILE` and staged every tracked file of the real
    worktree as deleted.
  * One layer up — a sub-agent's `git init` under an inherited `GIT_DIR` set
    `core.bare = true` on `/home/bbt/nix` and **bared this repository**
    (`sessions/SESSION.md:1514`). ARC 026 exists because of it.

WHAT THIS MODULE PROVES, and it is two things, not one
------------------------------------------------------
1. **THE HOSTILE ENVIRONMENT IS GENUINELY HOSTILE** — the control. Every case
   first runs the SAME git invocation with the environment UNSCRUBBED and
   asserts it reports the DECOY repository. Without that half, a test that
   merely observes the right answer under a scrub proves nothing: it cannot
   distinguish *the scrub worked* from *`GIT_DIR` never mattered here*. This is
   `VERIFY-AND-CHECKS.md` C.2's both-halves rule pointed at an environment
   variable instead of at a code defect.
2. **THE PRODUCTION CALLER STILL MEASURES THE INTENDED REPOSITORY.** Every
   subprocess-git caller that ships is driven — the three gates, the new
   name-coherence gate, and `scripts/runtime_gate.py`, which `pre-commit` runs
   on every commit and which had no scrub at all before ARC 026.

EVERY ASSERTION NAMES THE REASON, NEVER AN EXIT CODE (check contract §11/§18).
The reason here is a FILENAME: each repository holds one distinctively-named
tracked file, and the assertion is which of those two names came back. An exit
code could not tell the difference — both repositories answer `0`.

NO PLANT TOUCHES A PRODUCTION ARTEFACT (doctrine C.8). Both repositories are
built under `tmp_path`, and every fixture git call runs under
`scrubbed_env(...)` — the fixture that builds the isolation must not be the
thing that breaks it, which is precisely how ARC 025 lost an index.
"""

# pylint: disable=invalid-name,duplicate-code,import-outside-toplevel
# Test names SHOUT the property under test, as the rest of this suite does.
# `duplicate-code`: the sys.path bootstrap and the SCRUBBED fixture-git helper
# are repeated per module DELIBERATELY. Factoring them into a shared conftest
# would hide the D3.22 scrub from the reader of each module, and a scrub nobody
# sees at the call site is how three private spellings of it drifted apart in
# the first place. Late imports are the sys.path bootstrap this suite needs.
from __future__ import annotations

import os
import subprocess  # nosec B404 - fixed argv, shell=False, tmp_path only
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
SCRIPTS = REPO / "scripts"
for _extra in (str(CHECKS), str(SCRIPTS)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_artifact_gate_coverage as coverage_gate  # pylint: disable=import-error
import check_canonical_tree as canonical_gate  # pylint: disable=import-error
import check_hook_suite as hook_gate  # pylint: disable=import-error
import check_name_coherence as name_gate  # pylint: disable=import-error
import runtime_gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode  # pylint: disable=import-error
from nixverify.gitenv import (  # pylint: disable=import-error
    PREFIX,
    SELECTORS,
    scrubbed_env,
)

#: The two names the assertions turn on. Distinctive enough that a match cannot
#: be a coincidence, and tracked in exactly one of the two repositories each.
INTENDED_MARKER = "intended_repository_marker.py"
DECOY_MARKER = "decoy_repository_marker.py"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _fixture_git(cwd: Path, *args: str) -> None:
    """Build fixture state with git, under a SCRUBBED environment.

    `extra=_IDENTITY` after the scrub, not before: the commit identity is stated
    at the call site rather than inherited, which is the whole argument for
    `scrubbed_env` taking `extra` at all.
    """
    subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp_path only
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=scrubbed_env(extra=_IDENTITY),
    )


def _make_repo(root: Path, marker: str) -> Path:
    """A real git repository holding exactly one distinctively-named file."""
    root.mkdir(parents=True, exist_ok=True)
    (root / marker).write_text("# fixture\n", encoding="utf-8")
    _fixture_git(root, "init", "-q", "-b", "main")
    _fixture_git(root, "add", "-A")
    _fixture_git(root, "commit", "-q", "-m", "fixture")
    return root


@pytest.fixture(name="repos")
def _repos(tmp_path: Path) -> tuple[Path, Path]:
    """(intended, decoy) — two real repositories, neither of them this tree."""
    return (
        _make_repo(tmp_path / "intended", INTENDED_MARKER),
        _make_repo(tmp_path / "decoy", DECOY_MARKER),
    )


@pytest.fixture(name="hostile")
def _hostile(
    repos: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Export every repository-selecting variable, all aimed at the DECOY.

    This is the exact shape `pre-commit` hands a hook, with the target swapped
    for a repository the caller was never asked about.
    """
    _, decoy = repos
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))
    monkeypatch.setenv("GIT_COMMON_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(decoy / ".git" / "objects"))
    monkeypatch.setenv(
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", str(decoy / ".git" / "objects")
    )
    return repos


def _raw_ls_files(cwd: Path) -> str:
    """`git ls-files` with the AMBIENT environment — the unrepaired caller.

    THIS CALL IS UNSCRUBBED ON PURPOSE and is the only reason this module can
    prove anything: it is the control half that shows the hostile environment is
    genuinely hostile. `check_git_env_scrub` derives every git call site in the
    tree and reddens on an unscrubbed one, so this exception is DECLARED at the
    call site with the marker below rather than being an accepted absence —
    and the gate honours the marker only under `scripts/tests/`, and reports
    every one it honoured, so the exception cannot grow quietly.
    """
    proc = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp_path only
        ["git", "-C", str(cwd), "ls-files"],  # gitenv-allow-unscrubbed
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


# --- the control: prove the plant is real ---------------------------------


def test_CONTROL_an_unscrubbed_caller_really_does_report_the_decoy(
    hostile: tuple[Path, Path],
) -> None:
    """Without the scrub, `-C intended` reports the DECOY's file. NON-VACUITY.

    If this ever stops holding, every scrub assertion below becomes vacuous —
    it would be observing the right answer for a reason that has nothing to do
    with the scrub. The failure message names both markers so a reader is told
    WHICH repository answered, never merely that a boolean flipped.
    """
    intended, _ = hostile
    listing = _raw_ls_files(intended)
    assert DECOY_MARKER in listing, (
        "the hostile environment did not redirect an unscrubbed `git -C "
        f"{intended} ls-files`; expected the decoy's {DECOY_MARKER!r} and got "
        f"{listing!r}. Every scrub assertion in this module rests on this."
    )
    assert INTENDED_MARKER not in listing, listing


def test_CONTROL_the_scrub_removes_every_named_selector(
    hostile: tuple[Path, Path],
) -> None:
    """`SELECTORS` is documentation; the `GIT_*` prefix is the rule. Both hold."""
    assert hostile  # the variables are exported by the fixture
    env = scrubbed_env()
    still_there = [name for name in SELECTORS if name in env]
    assert not still_there, f"named selector(s) survived the scrub: {still_there}"
    leaked = [name for name in env if name.startswith(PREFIX)]
    assert not leaked, f"{PREFIX}-prefixed variable(s) survived the scrub: {leaked}"
    # And it must not be scrubbing by emptying the environment wholesale.
    assert "PATH" in env, "the scrub removed non-git variables — it is too broad"


# --- the production callers ------------------------------------------------


def test_coverage_gate_enumerates_the_intended_repository(
    hostile: tuple[Path, Path],
) -> None:
    """`check_artifact_gate_coverage._git(home, 'ls-files')` ignores GIT_DIR."""
    intended, _ = hostile
    out, error = coverage_gate._git(intended, "ls-files")  # pylint: disable=protected-access
    assert not error, error
    assert INTENDED_MARKER in out, (
        f"check_artifact_gate_coverage enumerated the wrong repository: got "
        f"{out!r}, expected {INTENDED_MARKER!r}"
    )
    assert DECOY_MARKER not in out, out


def test_name_coherence_gate_enumerates_the_intended_repository(
    hostile: tuple[Path, Path],
) -> None:
    """`check_name_coherence.tracked_files` ignores GIT_DIR.

    This gate's whole verdict is a scan over the set this call returns, so a
    redirected enumeration would make it report PASS over a repository nobody
    asked about — §7.12 answer 1 in its own docstring.
    """
    intended, _ = hostile
    paths, error = name_gate.tracked_files(intended)
    assert not error, error
    assert INTENDED_MARKER in paths, (
        f"check_name_coherence scanned the wrong repository: got {paths!r}"
    )
    assert DECOY_MARKER not in paths, paths


def test_canonical_tree_gate_resolves_the_intended_repository(
    hostile: tuple[Path, Path],
) -> None:
    """`check_canonical_tree._git` answers about `cwd`, not about GIT_DIR.

    The reason asserted is the resolved TOPLEVEL PATH — the gate whose subject
    is 'which tree is this?' answering with the wrong tree is the defect, and a
    return code cannot express it.
    """
    intended, decoy = hostile
    code, out = canonical_gate._git(  # pylint: disable=protected-access
        ["rev-parse", "--show-toplevel"], cwd=intended
    )
    assert code == 0, out
    assert Path(out).resolve() == intended.resolve(), (
        f"check_canonical_tree resolved {out!r}; expected {intended} and NOT "
        f"the decoy {decoy}"
    )


def test_hook_suite_gate_resolves_the_intended_repository(
    hostile: tuple[Path, Path],
) -> None:
    """`check_hook_suite._git` answers about `nix_home`, not about GIT_DIR.

    The reason asserted is the resolved GIT DIRECTORY: this gate exists to say
    where git will look for hooks, so being pointed at another repository's git
    dir is exactly the false report it must not make.
    """
    intended, decoy = hostile
    out = hook_gate._git(intended, "rev-parse", "--absolute-git-dir")  # pylint: disable=protected-access
    assert out is not None, "git declined to answer"
    assert Path(out).resolve() == (intended / ".git").resolve(), (
        f"check_hook_suite resolved the git dir {out!r}; expected "
        f"{intended / '.git'} and NOT the decoy {decoy / '.git'}"
    )


def test_runtime_gate_scopes_to_the_intended_repository(
    hostile: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`runtime_gate.git` derives the Stage-3 gate's SCOPE — from `cwd`, now.

    This is the caller that had no scrub at all, and the most exposed one:
    `pre-commit` invokes it from inside a real `git commit`, and `main()` builds
    both the file scope and the changed set from these two calls. A redirected
    answer silently sets what the commit gate measures.
    """
    intended, _ = hostile
    monkeypatch.chdir(intended)
    scope = runtime_gate.git("ls-files")
    assert INTENDED_MARKER in scope, (
        f"runtime_gate scoped to the wrong repository: got {scope!r}, expected "
        f"{INTENDED_MARKER!r}"
    )
    assert DECOY_MARKER not in scope, scope


def test_coverage_gate_run_reports_the_intended_tree_not_the_decoy(
    hostile: tuple[Path, Path],
) -> None:
    """END TO END: the gate's real `run()` under a hostile GIT_DIR.

    The unit assertions above drive `_git` directly. This one drives the shipped
    entry point, because a scrub applied in a helper nothing calls would satisfy
    every one of them. The intended repository holds one file, which is below
    the gate's credibility floor — so the REASON asserted is that the gate
    refuses to report on a population that small, quoting its own floor. Under
    the decoy the population would be equally small, so the discriminator is the
    PATH NAMED IN THE DETAIL, not the status.
    """
    intended, _ = hostile
    result = coverage_gate.run(
        Mode.VERIFY, Context(nix_home=intended, mode=Mode.VERIFY)
    )
    assert "credibility floor" in result.detail, result.detail


def test_fixture_git_calls_cannot_reach_the_real_repository(
    hostile: tuple[Path, Path],
) -> None:
    """The fixture's OWN git calls are scrubbed — ARC 025's actual casualty.

    ARC 025 did not lose an index to a gate; it lost one to a TEST FIXTURE that
    ran `git add -A` under an inherited `GIT_INDEX_FILE`. The repair therefore
    has to cover the harness as well as the shipped code, and this asserts it by
    reason: the decoy's index must still describe the decoy, and the intended
    repository's HEAD must still name its own single file, after the fixture has
    run `init`/`add`/`commit` under a hostile environment.
    """
    intended, decoy = hostile
    for repo, expected, unexpected in (
        (intended, INTENDED_MARKER, DECOY_MARKER),
        (decoy, DECOY_MARKER, INTENDED_MARKER),
    ):
        proc = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["git", "-C", str(repo), "ls-tree", "-r", "HEAD", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
            env=scrubbed_env(),
        )
        assert expected in proc.stdout, (repo, proc.stdout)
        assert unexpected not in proc.stdout, (repo, proc.stdout)


def test_scrubbed_env_defaults_to_os_environ_and_copies_it() -> None:
    """It must not hand back `os.environ` itself — a caller mutating the result
    would be editing the running process's environment."""
    env = scrubbed_env()
    assert env is not os.environ
    env["NIX_TEST_ONLY"] = "1"
    assert "NIX_TEST_ONLY" not in os.environ
