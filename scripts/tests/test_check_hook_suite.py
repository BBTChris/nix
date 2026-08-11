"""`check_hook_suite` proves the pre-commit suite is wired in, effectively.

ARC 019 / C2, narrowing CHECK-DEBT D1.10.

Two things these tests are careful about, both learned the hard way in this
project:

  * They NEVER touch `~/nix/.git/hooks/`. That directory is shared by every
    linked worktree, so uninstalling the hook to prove a can-fail would disarm
    the gate for whatever else is committing at the time. ARC 018 established
    that a concurrent cross-set write corrupts evidence, not just state. Every
    negative case here is driven against a THROWAWAY repository built in
    `tmp_path`, and the environment is named in each test — `debug.md` §8
    failure mode #12.

  * They assert the gate's own functions, not a reimplementation. A test that
    re-derives the verdict is a test of the test.
"""

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, shell=False, repo-local
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_hook_suite as gate  # pylint: disable=import-error
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)

CONFIG = REPO / gate.CONFIG_FILE
PRE_COMMIT = REPO / ".venv" / "bin" / "pre-commit"


def _git(cwd: Path, *args: str) -> None:
    """One git command in a throwaway repository. `git` from PATH, as D1.7 has it.

    `env=gate._clean_git_env()` IS THE POINT, not boilerplate. FOUND THE HARD WAY,
    ARC 019: this suite runs inside `pre-commit`, which git invokes with `GIT_DIR`
    and `GIT_INDEX_FILE` exported — and those variables outrank `cwd`. Without the
    strip, `git init` / `git add -A` / `git commit` in `tmp_path` operated on the
    REPOSITORY BEING COMMITTED TO instead, and produced a commit there that
    deleted the tree. The fixture looked isolated and was not. Every git call in
    this module goes through here for that reason.
    """
    subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp_path only
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=gate._clean_git_env(),  # pylint: disable=protected-access
    )


@pytest.fixture(name="scratch")
def _scratch(tmp_path: Path) -> Path:
    """A throwaway repository carrying the real config and a few tracked files.

    Never `~/nix`: see the module docstring. The hook environments it resolves
    are the ones already in pre-commit's store for the pinned revs, so nothing
    here reaches the network.
    """
    repo = tmp_path / "scratch"
    (repo / "scripts" / "tests").mkdir(parents=True)
    (repo / gate.CONFIG_FILE).write_text(
        CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (repo / "pyproject.toml").write_text(
        (REPO / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (repo / "scripts" / "a.py").write_text('"""x."""\n', encoding="utf-8")
    (repo / "scripts" / "tests" / "test_a.py").write_text(
        '"""x."""\n', encoding="utf-8"
    )
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "arc019@example.invalid")
    _git(repo, "config", "user.name", "arc019")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "scratch", "--no-verify")
    subprocess.run(  # nosec B603 - fixed argv, shell=False, tmp_path only
        [str(PRE_COMMIT), "install"],
        cwd=str(repo),
        check=True,
        capture_output=True,
        env=gate._clean_git_env(),  # pylint: disable=protected-access
    )
    # NON-VACUITY FOR THE ISOLATION ITSELF. Assert the fixture built a repository
    # in tmp_path and not somewhere else, before any test trusts it. Without this
    # the fixture could silently operate on the caller's repository again and
    # every test below would keep passing while measuring the wrong tree.
    assert (repo / ".git").is_dir(), "fixture did not create a repository in tmp_path"
    assert gate.git_layout(repo).hooks_dir == repo / ".git" / "hooks"
    return repo


def _run(home: Path):
    """The gate's verdict for one repository root."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


# ---------------------------------------------------------------------------
# NON-VACUITY, asserted before any plant (doctrine C.3).
# ---------------------------------------------------------------------------


def test_the_probe_answers_about_the_real_tree() -> None:
    """The venv-side probe must produce a structured answer, not an empty one."""
    answer = gate.probe(REPO)
    assert not answer.complaint, answer.complaint
    assert not answer.payload.get("error"), answer.payload.get("error")
    assert answer.payload["hooks"], "zero hooks resolved — the gate has no subject"
    assert answer.payload["all_files"] > 0


def test_the_expected_hook_set_is_derived_from_the_config() -> None:
    """Every hook in the config file appears in the resolved set, by key.

    The keys are read out of the YAML text independently of pre-commit's
    resolver, so this asserts the two agree rather than asserting a snapshot
    list — a snapshot is the failure mode this gate exists to close.
    """
    text = CONFIG.read_text(encoding="utf-8")
    declared = {
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.strip().startswith(("- id:", "alias:"))
    }
    resolved = {h["key"] for h in gate.probe(REPO).payload["hooks"]}
    resolved |= {h["id"] for h in gate.probe(REPO).payload["hooks"]}
    missing = declared - resolved
    assert not missing, f"declared in the config but never resolved: {missing}"


def test_at_least_one_hook_is_file_scoped_and_selection_checked() -> None:
    """§7.12 condition 5: an all-`always_run` suite leaves arm 3 with no subject."""
    hooks = gate.probe(REPO).payload["hooks"]
    scoped = [h for h in hooks if not h["always_run"]]
    assert scoped, "no file-scoped hook — the zero-selection detector has no subject"
    assert all(h["selected"] > 0 for h in scoped), [
        h["key"] for h in scoped if h["selected"] == 0
    ]


# ---------------------------------------------------------------------------
# ARM 1 — the hooks path, in BOTH layouts. This is the worktree question.
# ---------------------------------------------------------------------------


def test_git_queries_ignore_an_inherited_GIT_DIR(  # pylint: disable=invalid-name
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REGRESSION, ARC 019. `GIT_DIR` in the environment must not steer the gate.

    git exports `GIT_DIR` into every hook it runs, and it outranks `cwd`. A gate
    that inherited it would answer about whichever repository started the hook
    while its evidence line named `nix_home` — a false GREEN with a mechanism,
    and the exact defect that made this suite commit against the worktree.

    The control is the second half: with the variable set, the answer must be
    unchanged, and `_clean_git_env` must actually have dropped it.
    """
    expected = gate.git_layout(scratch).hooks_dir
    monkeypatch.setenv("GIT_DIR", str(REPO / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(REPO / ".git" / "index"))
    assert "GIT_DIR" not in gate._clean_git_env()  # pylint: disable=protected-access
    assert gate.git_layout(scratch).hooks_dir == expected


def test_the_hooks_path_comes_from_git_and_exists(scratch: Path) -> None:
    """Both layouts resolve a real hooks directory, and both are named as such."""
    for home in (REPO, scratch):
        layout = gate.git_layout(home)
        assert layout.hooks_dir is not None
        assert layout.hooks_dir.is_dir(), layout.hooks_dir
        assert layout.layout in ("repo", "worktree")


def test_the_layout_resolves_to_the_hooks_dir_git_will_use() -> None:
    """In a linked worktree the hooks live in the COMMON dir, not the private one.

    A gate that composed `<git-dir>/hooks` itself would look at a directory that
    does not exist in every worktree. This asserts git's answer is used, whichever
    layout the suite happens to be running in — and it is written to assert
    something in BOTH, so it cannot pass by never taking a branch.
    """
    layout = gate.git_layout(REPO)
    assert layout.hooks_dir is not None
    assert (layout.hooks_dir / gate.HOOK_TYPE).is_file()
    if layout.layout == "worktree":
        private = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["git", "rev-parse", "--git-dir"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert not (Path(private) / "hooks" / gate.HOOK_TYPE).is_file()


def test_a_repository_with_no_installed_hook_fails(scratch: Path) -> None:
    """CAN-FAIL, arm 1. Never run against ~/nix — see the module docstring."""
    assert _run(scratch).status is Status.PASS
    (scratch / ".git" / "hooks" / gate.HOOK_TYPE).unlink()
    result = _run(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "no pre-commit hook installed" in (result.detail or "")
    assert gate.HOOK_TYPE in (result.site or "")


def test_an_overwritten_hook_fails(scratch: Path) -> None:
    """CAN-FAIL, arm 1. A real, executable hook that is not pre-commit's."""
    hook = scratch / ".git" / "hooks" / gate.HOOK_TYPE
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)
    result = _run(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "NOT pre-commit's own script" in (result.detail or "")


def test_a_hook_pointing_at_another_config_fails(scratch: Path) -> None:
    """CAN-FAIL, arm 2. Installed, ours, executable — and reading a different file."""
    hook = scratch / ".git" / "hooks" / gate.HOOK_TYPE
    hook.write_text(
        hook.read_text(encoding="utf-8").replace(
            f"--config={gate.CONFIG_FILE}", "--config=elsewhere.yaml"
        ),
        encoding="utf-8",
    )
    result = _run(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "different file" in (result.detail or "")


def test_control_the_restored_scratch_repo_passes(scratch: Path) -> None:
    """CONTROL for all three arm-1/2 plants above, in the same environment."""
    result = _run(scratch)
    assert result.status is Status.PASS, result.detail


# ---------------------------------------------------------------------------
# ARM 3 — a hook silently dropped, and the case that is NOT detectable.
# ---------------------------------------------------------------------------


def test_a_hook_that_selects_zero_files_fails(scratch: Path) -> None:
    """CAN-FAIL, arm 3. `exclude` widened until the hook reads nothing.

    This is the "silently dropped" shape that is actually checkable: the hook
    stays configured and installed, pre-commit prints `Skipped`, and exits 0.
    """
    config = scratch / gate.CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "      - id: complexipy\n        exclude: ^databases/schema/\n",
            "      - id: complexipy\n        exclude: ^.*$\n",
        ),
        encoding="utf-8",
    )
    result = _run(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "selects ZERO files" in (result.detail or "")
    assert "complexipy" in (result.site or "")


def test_deleting_a_hook_entry_is_not_detected_and_that_is_stated(
    scratch: Path,
) -> None:
    """THE NAMED GAP, asserted so it cannot quietly change without notice.

    "No hook has been dropped" is not checkable against the config, because the
    config IS the authority for what is configured: delete the entry and both
    sides of any config-derived comparison lose it together. The gate stays
    green and the hook count in `evidence` falls, which is readable but is not a
    verdict. Recorded here as a test rather than as prose so that if a future
    arc DOES make it detectable, this test fails and the claim gets updated.
    """
    config = scratch / gate.CONFIG_FILE
    before = len(gate.probe(scratch).payload["hooks"])
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  - repo: https://github.com/pre-commit/mirrors-mypy\n"
            "    rev: v1.18.2\n"
            "    hooks:\n"
            "      - id: mypy\n"
            "        exclude: ^databases/schema/\n",
            "",
        ),
        encoding="utf-8",
    )
    after = len(gate.probe(scratch).payload["hooks"])
    assert after == before - 1, "the mypy entry was not actually removed"
    assert _run(scratch).status is Status.PASS


# ---------------------------------------------------------------------------
# ARM 4 — the pinned environment, and the cached-sibling visibility.
# ---------------------------------------------------------------------------


def test_every_pinned_repo_has_an_installed_environment() -> None:
    """Arm 4: each hook resolves into the store row keyed to the rev the pin names."""
    for repo in gate.probe(REPO).payload["repos"]:
        if repo["local"]:
            continue
        assert repo["store_path"], f"no environment for {repo['repo']}@{repo['rev']}"
        assert Path(repo["store_path"]).is_dir()
        assert repo["store_path"] in repo["hook_prefixes"], repo


def test_resident_sibling_environments_are_named_not_hidden() -> None:
    """The cached-bandit visibility half of the D1.10 answer.

    ARC 018 measured a pre-ARC-010 bandit environment still resident and still
    able to reproduce the ARC 006 vacuum. This gate cannot prove the PINNED
    environment is non-vacuous — that needs a per-hook canary and is CHECK-DEBT
    D3.7 — but a sibling environment is no longer something only a person who
    went looking knows about.
    """
    result = _run(REPO)
    siblings = [r for r in gate.probe(REPO).payload["repos"] if r["other_revs"]]
    if siblings:
        assert "RESIDENT-SIBLING" in (result.evidence or "")
        assert "D3.7" in (result.evidence or "")


# ---------------------------------------------------------------------------
# END TO END and CANNOT-MEASURE.
# ---------------------------------------------------------------------------


def test_the_gate_passes_on_the_real_tree() -> None:
    """CONTROL. If this reddens, the suite stopped being wired in as configured."""
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail


def test_the_gate_reports_the_environment_it_measured_in() -> None:
    """Failure mode #12: a proof taken in one environment presented as another."""
    evidence = _run(REPO).evidence or ""
    assert "layout=" in evidence
    assert "hooks_dir=" in evidence
    assert "core.hooksPath=" in evidence


def test_a_missing_config_is_cannot_measure(tmp_path: Path) -> None:
    """Doctrine B.2: exit 2, never 1 — a gate that measured nothing is not a FAIL."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert gate.CONFIG_FILE in (result.detail or "")
