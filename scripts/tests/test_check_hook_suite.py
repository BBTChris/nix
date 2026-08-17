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

import hashlib
import shutil
import sqlite3
import subprocess  # nosec B404 - fixed argv, shell=False, repo-local
import sys
from collections.abc import Iterator
from copy import deepcopy
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
            # D3.205: `--git-dir` is the ONE question an inherited `GIT_DIR`
            # answers directly, and this branch only runs in a worktree — the
            # layout this suite exists to distinguish. Gated by
            # `check_git_env_scrub`.
            env=gate._clean_git_env(),  # pylint: disable=protected-access
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
    source = config.read_text(encoding="utf-8")
    # ARC 035: the anchor was `exclude: ^databases/schema/`, which this arc's
    # MON-1 exclusion moved. `str.replace` with no match is a silent no-op, so
    # the plant planted NOTHING and this test failed for "no plant applied"
    # while reading as "the gate did not detect the plant" — debug.md §8 failure
    # mode #4 landing on the test that exists to demonstrate detection. The
    # anchor is now DERIVED from the live config and its presence asserted, so a
    # future config edit reports a stale anchor instead of a confusing red.
    marker = "      - id: complexipy\n"
    assert marker in source, "the complexipy hook entry is gone; anchor is stale"
    head, _, tail = source.partition(marker)
    exclude_line, _, rest = tail.partition("\n")
    assert exclude_line.strip().startswith("exclude:"), (
        f"expected an `exclude:` line directly after the complexipy entry, "
        f"found {exclude_line!r} — the plant would have planted nothing"
    )
    config.write_text(
        head + marker + "        exclude: ^.*$\n" + rest, encoding="utf-8"
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
    source = config.read_text(encoding="utf-8")
    # ARC 035: same stale-anchor repair as the sibling above. The mypy entry's
    # `exclude:` value moved with this arc's MON-1 exclusion, so the literal
    # block below no longer matched and the deletion deleted nothing. The block
    # is now located by its repo URL and cut to the next `- repo:`, and its
    # presence is asserted before the cut.
    start_marker = "  - repo: https://github.com/pre-commit/mirrors-mypy\n"
    assert start_marker in source, "the mypy repo entry is gone; anchor is stale"
    head, _, tail = source.partition(start_marker)
    next_repo = tail.index("\n  - repo: ") + 1
    config.write_text(head + tail[next_repo:], encoding="utf-8")
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


# ===========================================================================
# ARC 027 / A2 — CHECK-DEBT D3.14, ARM BY ARM, AGAINST THE REAL REPOSITORY.
#
# D3.14 says arms 1 and 2 were bound against the real repository in ARC 023 and
# that arms 3 and 4 stay owed. **Everything ARC 023 measured was banked in a
# results document and committed nowhere** — §0e requires a committed, runnable
# artifact and CHECK-DEBT D2.30 is the row for that class. The first test below
# is that artifact. The rest of this section reports, per arm, what could and
# could not be planted, with the measurement behind each answer.
#
# NOTHING SHARED IS WRITTEN. The technique is ARC 023's: a scratch `HOME`
# carrying a `[core] hooksPath` that redirects git's own hook resolution for
# THIS repository, which perturbs the gate's real subject while
# `/home/bbt/nix/.git` is only ever read. `PRE_COMMIT_HOME` is pinned to the
# real store throughout so arms 3 and 4 keep measuring the real environments,
# and the real hook file's sha256 is asserted unchanged either side.
#
# §7.12, asked of this section: what would have to be true for it to pass while
# measuring nothing?
#   1. The scratch HOME could be moving the verdict by itself, in which case the
#      plants prove nothing. CLOSED by the second control, which runs in the
#      scratch HOME with `core.hooksPath` pointed BACK at the real directory and
#      requires PASS — the environment override alone does not move the verdict.
#   2. The gate could be failing because the store went missing along with HOME.
#      CLOSED: `PRE_COMMIT_HOME` is set explicitly and the evidence is asserted
#      to still name eight hooks over the real tracked-file count.
#   3. A plant could leak into the shared repository. CLOSED: the real hook's
#      sha256 is compared before and after, and repository-scope
#      `core.hooksPath` is asserted to remain unset.
# ===========================================================================


#: The store the real hooks resolve into. Read from pre-commit itself rather
#: than written down, so a moved cache does not turn into a stale literal
#: anchor (`debug.md` §8 failure mode #4).
def _real_store_dir() -> str:
    # pylint: disable=import-outside-toplevel,import-error
    # `import-error`: pylint runs under the hook environment, where `pre_commit`
    # is not importable; the interpreter this suite runs under is the venv, where
    # it is. Same pragma, same reason, as `checks/check_hook_suite.py` carries.
    from pre_commit.store import Store

    return Store().directory


def _real_hook_sha() -> str:
    hooks_dir = gate.git_layout(REPO).hooks_dir
    # `hooks_dir` is Optional: `git_layout` returns None for it when the tree is
    # not a git repository. Every caller here is about THIS repository's real
    # installed hook, so a None is a broken premise and must say which one —
    # not a TypeError about the `/` operator (check contract §18).
    assert hooks_dir is not None, (
        f"{REPO} reports no hooks directory — this control is about the REAL "
        "installed hook and there is nothing to take a sha of"
    )
    return hashlib.sha256((hooks_dir / gate.HOOK_TYPE).read_bytes()).hexdigest()


def test_arms_1_and_2_can_fail_against_the_real_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CAN-FAIL, arms 1 and 2, AGAINST THE REAL REPOSITORY. Discharges D2.30's third.

    Four measurements in order, and the order is the point:

      NON-VACUITY — the ambient run resolves the real hooks directory and passes.
      CONTROL     — the same run under a scratch HOME whose `core.hooksPath`
                    points back at the real directory: still PASS, with the
                    override visible in the evidence. This is what excludes the
                    confound that the environment change alone reddens the gate.
      PLANT 1     — `core.hooksPath` at an EMPTY directory. Arm 1: the hook git
                    would run is not there.
      PLANT 2     — THE REAL HOOK FILE, copied byte-for-byte and differing only
                    in its `ARGS` line. Arm 2, and it is the strongest of the
                    set because the subject is genuine `pre-commit` output that
                    is installed, executable, and pre-commit's own — and reads a
                    different config.
      UNPLANT     — the scratch gitconfig removed; PASS returns.
    """
    monkeypatch.setenv("PRE_COMMIT_HOME", _real_store_dir())
    before_sha = _real_hook_sha()
    real_hooks = gate.git_layout(REPO).hooks_dir
    assert real_hooks is not None

    # NON-VACUITY, before anything is perturbed.
    ambient = _run(REPO)
    assert ambient.status is Status.PASS, ambient.detail
    assert "8 hook(s)" in (ambient.evidence or "")

    scratch_home = tmp_path / "home"
    scratch_home.mkdir()
    gitconfig = scratch_home / ".gitconfig"
    monkeypatch.setenv("HOME", str(scratch_home))

    # CONTROL — scratch HOME, hooksPath pointed BACK at the real directory.
    gitconfig.write_text(f"[core]\n\thooksPath = {real_hooks}\n", encoding="utf-8")
    control = _run(REPO)
    assert control.status is Status.PASS, control.detail
    assert f"core.hooksPath={real_hooks}" in (control.evidence or "")

    # PLANT 1 — arm 1.
    empty = tmp_path / "empty"
    empty.mkdir()
    gitconfig.write_text(f"[core]\n\thooksPath = {empty}\n", encoding="utf-8")
    plant1 = _run(REPO)
    assert plant1.status is Status.FAIL_NEEDS_OPERATOR
    assert "no pre-commit hook installed at the path git resolves" in (
        plant1.detail or ""
    )
    assert str(empty) in (plant1.site or "")

    # PLANT 2 — arm 2. The real hook, re-pointed at another config.
    other = tmp_path / "other"
    other.mkdir()
    copied = other / gate.HOOK_TYPE
    copied.write_text(
        (real_hooks / gate.HOOK_TYPE)
        .read_text(encoding="utf-8")
        .replace(f"--config={gate.CONFIG_FILE}", "--config=other-config.yaml"),
        encoding="utf-8",
    )
    copied.chmod(0o755)
    gitconfig.write_text(f"[core]\n\thooksPath = {other}\n", encoding="utf-8")
    plant2 = _run(REPO)
    assert plant2.status is Status.FAIL_NEEDS_OPERATOR
    assert f"installed hook does not name {gate.CONFIG_FILE}" in (plant2.detail or "")
    assert "--config=other-config.yaml" in (plant2.detail or "")
    assert "is_our_script=True" in (plant2.evidence or ""), (
        "the plant stopped being pre-commit's own script, which would make it "
        "an arm-1 plant wearing arm 2's name"
    )

    # UNPLANT.
    gitconfig.unlink()
    assert _run(REPO).status is Status.PASS

    # NOTHING SHARED WAS WRITTEN — shown, not asserted in prose.
    assert _real_hook_sha() == before_sha
    assert gate._git(REPO, "config", "--get", "core.hooksPath") is None  # pylint: disable=protected-access


def test_arm_4_reddens_against_the_real_repository_when_a_pinned_env_is_missing(  # pylint: disable=invalid-name
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CAN-FAIL, ARM 4, AGAINST THE REAL REPOSITORY. **DISCHARGES CHECK-DEBT D3.29.**

    ARC 027 took exactly this plant — `PRE_COMMIT_HOME` at an empty directory,
    against the REAL repository and the REAL config, a real operational state
    that writes nothing shared — and MEASURED the gate returning CANNOT_MEASURE
    *"resolved to ZERO hooks"*: the missing environment emptied the hook set,
    and the vacuity guard judged the empty set before arm 4 could judge its
    cause. That was a reachability defect, not a false green, and D3.29 recorded
    it as such rather than rounding it up to a binding.

    ARC 028 (C3) repaired the ORDER — `repo_defects` runs before
    `_vacuity_complaint` — and this is the same plant re-taken against the
    repaired gate. The assertion is the REASON and the SITE, never the status
    alone: every non-local pinned rev must be named.

    Non-vacuity first, unplant last, and the old CANNOT_MEASURE text is asserted
    ABSENT so a revert of the ordering reddens here instead of quietly restoring
    the shadowing.
    """
    # RESOLVED BEFORE THE PLANT, AND THAT IS NOT STYLE. `_real_store_dir()`
    # asks pre-commit, which reads `PRE_COMMIT_HOME` — so calling it after the
    # plant returns the PLANTED store and the "unplant" would restore nothing.
    # Measured: the first cut of this control did exactly that, and its closing
    # PASS assertion failed with the plant still in force.
    real_store = _real_store_dir()
    monkeypatch.setenv("PRE_COMMIT_HOME", real_store)
    ambient = _run(REPO)
    assert ambient.status is Status.PASS, ambient.detail

    monkeypatch.setenv("PRE_COMMIT_HOME", str(tmp_path / "empty-store"))
    payload = gate.probe(REPO).payload
    assert payload["all_files"] > 0, "the tree lost its tracked files; wrong subject"
    pinned = [row for row in payload["repos"] if not row["local"]]
    assert pinned, "no non-local repo in the config; arm 4 has no subject"
    assert all(row["store_path"] is None for row in pinned), payload["repos"]
    assert payload["hooks"] == [], "the plant did not empty the hook set"
    assert payload["hooks_resolved"] is False

    result = _run(REPO)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "no environment installed for the pinned rev" in (result.detail or "")
    assert "resolved to ZERO hooks" not in (result.detail or ""), (
        "the vacuity guard is shadowing arm 4 again — D3.29 has regressed"
    )
    for row in pinned:
        site = f"{gate.CONFIG_FILE}:{row['repo']}@{row['rev']}"
        assert site in (result.site or ""), (site, result.site)
    assert "will not run in the environment the pin names" not in (
        result.detail or ""
    ), "an unresolved hook set produced a spurious prefix mismatch"

    monkeypatch.setenv("PRE_COMMIT_HOME", real_store)
    assert _run(REPO).status is Status.PASS


def test_arm_4_reddens_when_the_store_row_survives_but_its_directory_does_not(  # pylint: disable=invalid-name
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CAN-FAIL, ARM 4's SECOND STATE — a store row pointing at a deleted environment.

    ARC 027 could only reach *"no row at all"*. A row that EXISTS while its
    directory has been removed — a cleaned cache, a pruned `~/.cache`, a
    partially-restored backup — was invisible twice over: `store_path` was
    truthy so the missing-row branch stayed silent, and
    `_environments_all_present` already treated it as absent so the hook set was
    empty and the vacuity guard answered instead.

    The plant is a REAL pre-commit store: the live `db.db` is COPIED into
    `tmp_path` and every row's path is suffixed, so pre-commit's own reader
    finds genuine rows naming directories that are not there. Nothing shared is
    written — the real store is opened read-only and its own file is asserted
    unchanged by sha256 either side.
    """
    real_store = _real_store_dir()  # before the plant; see the note above
    real_db = Path(real_store) / "db.db"
    if not real_db.is_file():
        pytest.skip(f"no pre-commit store database at {real_db}")
    before = hashlib.sha256(real_db.read_bytes()).hexdigest()

    store = tmp_path / "store"
    store.mkdir()
    shutil.copy2(real_db, store / "db.db")
    with sqlite3.connect(str(store / "db.db")) as conn:
        changed = conn.execute(
            "UPDATE repos SET path = path || '-REMOVED-BY-ARC-028'"
        ).rowcount
    assert changed > 0, "the copied store held no rows; the plant has no subject"

    monkeypatch.setenv("PRE_COMMIT_HOME", str(store))
    payload = gate.probe(REPO).payload
    pinned = [row for row in payload["repos"] if not row["local"]]
    assert pinned and all(row["store_path"] for row in pinned), payload["repos"]
    assert all(not row["store_path_exists"] for row in pinned), payload["repos"]

    result = _run(REPO)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "which is not a directory" in (result.detail or "")
    assert "-REMOVED-BY-ARC-028" in (result.detail or ""), result.detail
    assert "resolved to ZERO hooks" not in (result.detail or "")

    assert hashlib.sha256(real_db.read_bytes()).hexdigest() == before, (
        "the plant wrote to the REAL pre-commit store"
    )
    monkeypatch.setenv("PRE_COMMIT_HOME", real_store)
    assert _run(REPO).status is Status.PASS


def test_arms_3_and_4_decide_correctly_over_the_real_resolved_hook_set() -> None:
    """PREDICATE-LEVEL, AND LABELLED AS SUCH — this does NOT bind arms 3 or 4.

    `hook_set_defects` is driven over the payload the REAL probe produced for
    the REAL repository, with one field moved per case. That is stronger than a
    hand-built dictionary — the hook keys, prefixes, revs and store rows are all
    genuine — and it is weaker than a plant, because nothing made the real
    system enter these states. Under the CHECK-DEBT rule of record a drive that
    does not land in the subject does not bind, so this is recorded as what it
    is and D3.14 stays open on arms 3 and 4.

    It earns its place by covering the three branches no other test reaches:
    the hook-environment-missing branch of arm 3 and both branches of arm 4.
    """
    real = gate.probe(REPO).payload
    assert real["hooks"] and real["repos"], "no real payload to mutate"

    dropped = deepcopy(real)
    dropped["hooks"][0].update({"prefix_exists": False, "always_run": False})
    defects, _ = gate.hook_set_defects(dropped)
    assert any("was never installed" in why for _, why in defects), defects

    zero = deepcopy(real)
    zero["hooks"][0].update({"selected": 0, "always_run": False})
    defects, _ = gate.hook_set_defects(zero)
    assert any("selects ZERO files" in why for _, why in defects), defects

    norow = deepcopy(real)
    next(row for row in norow["repos"] if not row["local"])["store_path"] = None
    defects, _ = gate.hook_set_defects(norow)
    assert any("has no row for it" in why for _, why in defects), defects

    mismatch = deepcopy(real)
    next(row for row in mismatch["repos"] if not row["local"])["store_path"] = (
        "/nonexistent/store/row"
    )
    defects, _ = gate.hook_set_defects(mismatch)
    assert any(
        "will not run in the environment the pin names" in why for _, why in defects
    ), defects


def test_the_real_subject_route_for_arm_3_collapses_and_the_collapse_is_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHY ARM 3 STAYS UNBOUND, measured rather than asserted.

    Arm 3's subject is the hook set `.pre-commit-config.yaml` resolves and the
    files each hook selects over `git ls-files`. Planting it means changing that
    config, and the config is only read from the root the gate is pointed at —
    so the two available venues are:

      * a **copy of the tree**, which is what this test drives. It carries the
        REAL config, and it is not a git repository, so `git.get_all_files()`
        cannot answer and the gate reports CANNOT_MEASURE. Arm 3 has no subject
        there, which is the collapse D3.14 predicted and this pins.
      * **this worktree's own `.pre-commit-config.yaml`**, edited in place. That
        file is the live commit gate of the tree the suite is running inside,
        and the suite runs inside `pre-commit` itself via the `pytest-affected`
        hook. A crash between plant and restore would leave the repository's
        commit gate holding a deliberately broken hook set. REFUSED, and
        recorded as a refusal rather than performed carefully.

    The throwaway-repository plant that DOES exist above
    (`test_a_hook_that_selects_zero_files_fails`) is what the rule of record
    calls a purpose-built fake: it binds the predicate, not the subject.
    **CHECK-DEBT D3.30.**

    **KEPT AFTER ARC 028 (C3) DISCHARGED D3.30, because it is the reason the
    repair has the shape it has.** The collapse pinned here is exactly what
    `real_population` had to overcome, and it names the missing ingredient: not
    the config, which this route already carries, but a git repository for
    `git.get_all_files()` to answer from. A future edit that drops the `git
    init` from that fixture lands back here.
    """
    monkeypatch.setenv("PRE_COMMIT_HOME", _real_store_dir())
    home = tmp_path / "nix"
    home.mkdir()
    (home / gate.CONFIG_FILE).write_text(
        CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "not a git repository" in (result.detail or ""), result.detail


# ===========================================================================
# ARC 028 (C3) — ARM 3 AGAINST THE REAL CONFIGURATION OVER THE REAL POPULATION.
# **DISCHARGES CHECK-DEBT D3.30.**
#
# ARC 027 measured two venues and refused both. The refusals were right and the
# enumeration was incomplete: venue (a) failed because a COPY of the tree is not
# a git repository — which is a missing ingredient, not a law. A copy that IS a
# git repository carries the real `.pre-commit-config.yaml` over the real
# `git ls-files` population, resolves the real store's environments, and
# reproduces the real repository's per-hook selection counts exactly. It differs
# from the subject in location and in nothing else the gate reads, and the
# assertion below says so by comparing the two selection tables rather than by
# claiming equivalence in prose.
#
# What this is NOT: it is not the live commit gate of the tree the suite runs
# inside. Venue (b) stays REFUSED for the reason ARC 027 gave — a crash between
# plant and restore would leave `~/nix` committing through a deliberately broken
# hook set — and this venue makes that refusal cost nothing.
# ===========================================================================


@pytest.fixture(name="real_population")
def _real_population(tmp_path: Path) -> Iterator[Path]:
    """A git repository holding the REAL tracked file set and the REAL config.

    The population comes from `git ls-files` rather than from a directory copy,
    so it is the tracked set the gate's own `git.get_all_files()` reads and not
    a superset carrying build detritus — the two differ, and a hook selecting
    over the wrong one measures a population this repository does not have.
    """
    listing = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
        ["git", "-C", str(REPO), "ls-files", "-z"],
        check=True,
        capture_output=True,
        env=gate._clean_git_env(),  # pylint: disable=protected-access
    ).stdout.decode("utf-8")
    tracked = [rel for rel in listing.split("\0") if rel]
    assert tracked, "git ls-files returned nothing — no population to copy"

    home = tmp_path / "nix"
    for rel in tracked:
        source = REPO / rel
        if not source.is_file():
            continue
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    _git(home, "init", "-q", ".")
    _git(home, "config", "user.email", "arc028@example.invalid")
    _git(home, "config", "user.name", "arc028")
    _git(home, "add", "-A")
    _git(home, "commit", "-qm", "real population", "--no-verify")
    subprocess.run(  # nosec B603 - fixed argv, shell=False, tmp_path only
        [str(PRE_COMMIT), "install"],
        cwd=str(home),
        check=True,
        capture_output=True,
        env=gate._clean_git_env(),  # pylint: disable=protected-access
    )
    assert (home / ".git").is_dir(), "fixture did not create a repository in tmp_path"
    assert gate.git_layout(home).hooks_dir == home / ".git" / "hooks"
    yield home


def test_arm_3_reddens_over_the_real_config_and_the_real_tracked_population(  # pylint: disable=invalid-name
    real_population: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CAN-FAIL, ARM 3. **DISCHARGES CHECK-DEBT D3.30.**

    NON-VACUITY, and it is the load-bearing half: the venue is asserted to
    reproduce the REAL repository's per-hook selection table, hook key by hook
    key. That is what separates this from `test_a_hook_that_selects_zero_files_
    fails`, whose four-file repository can satisfy arm 3 with a `files:` regex
    that would never match anything real.

    THE PLANT is one line of YAML added to a real hook entry — a `files:`
    pattern that matches no path in the tree. That is failure mode #14 in its
    natural form: the hook stays configured, stays installed, resolves its
    pinned environment, and reads nothing, and `pre-commit` prints `Skipped` and
    exits 0 for it.

    UNPLANT, then the config's sha256 asserted identical, then PASS again.
    """
    real_store = _real_store_dir()  # before anything is perturbed
    monkeypatch.setenv("PRE_COMMIT_HOME", real_store)

    here = {
        h["key"]: h["selected"] for h in gate.probe(real_population).payload["hooks"]
    }
    there = {h["key"]: h["selected"] for h in gate.probe(REPO).payload["hooks"]}
    assert here == there, (
        "the venue does not reproduce the real repository's selection table, so "
        f"a plant against it is not a plant against arm 3's subject: {here} != {there}"
    )
    scoped = [
        h for h in gate.probe(real_population).payload["hooks"] if not h["always_run"]
    ]
    assert scoped and all(h["selected"] > 0 for h in scoped)

    control = _run(real_population)
    assert control.status is Status.PASS, control.detail

    config = real_population / gate.CONFIG_FILE
    before = config.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    anchor = "      - id: ruff-check\n"
    assert anchor in before, "the real config no longer declares ruff-check"
    config.write_text(
        before.replace(anchor, anchor + "        files: ^no-such-path-arc-028-c/\n", 1),
        encoding="utf-8",
    )

    planted = _run(real_population)
    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted.detail
    assert "hook selects ZERO files" in (planted.detail or ""), planted.detail
    assert f"{gate.CONFIG_FILE}:ruff-check" in (planted.site or ""), planted.site
    assert "ruff-check=0" in (planted.evidence or ""), planted.evidence

    config.write_text(before, encoding="utf-8")
    assert hashlib.sha256(config.read_bytes()).hexdigest() == before_sha
    assert _run(real_population).status is Status.PASS
