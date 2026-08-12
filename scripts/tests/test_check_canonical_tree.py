"""ARC 026 Phase 0.5 — the standing gate over canonical-path topology.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. A demonstration missing the last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8). The real-git plants
build genuine repositories under `tmp_path` and redirect the gate's two module
constants at them; the tests that read the real tree only READ it. Redirecting
the constants is the only way to plant against `CANONICAL`, which is hardcoded
on purpose — a gate that asked the running tree where the canonical tree is
would call whatever tree launched it canonical, the exact confusion it exists
to detect.

**Every control here asserts the REASON** — the site, the named condition, or
the field — never the exit code alone (check contract v2 §11). An exit code is
a shared namespace: the detector firing, the instrument breaking, and the
interpreter refusing to start all reach the same integer.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=duplicate-code
# Test names SHOUT the property; fixtures are reused by design; the sys.path
# bootstrap forces late imports. Each deliberate, so the pragma is named.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_canonical_tree as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    CheckResult,
    Context,
    Mode,
    Status,
)
from nixverify.gitenv import scrubbed_env  # pylint: disable=wrong-import-position

GATE_FILE = REPO / "checks" / "check_canonical_tree.py"


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Real git, scrubbed environment, for building fixture repositories.

    ARC 026 (B4): the scrub is `nixverify.gitenv.scrubbed_env`, the one the gate
    itself now uses, rather than a fourth private copy of the variable list. This
    fixture's copy named FOUR variables while the gate named six — a harness that
    could redirect itself while the gate could not is measuring a different
    program from the one that ships. The identity goes through `extra`, AFTER the
    scrub, because `git commit` needs it and it must be visible at the call site.
    """
    env = scrubbed_env(
        extra={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
    )
    return subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp_path only
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _instrument(tree: Path) -> None:
    """Give a directory the marker that makes it look like a Nix tree."""
    (tree / "scripts").mkdir(parents=True, exist_ok=True)
    (tree / "scripts" / "verify.py").write_text("# stand-in\n", encoding="utf-8")


@pytest.fixture
def real_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A REAL git repository with a real work tree, wired as the canonical path.

    Not a mock: `git worktree list --porcelain` is genuinely invoked against
    this repo, so the parsing under test faces git's actual output format.
    """
    scan_root = tmp_path / "home"
    canonical = scan_root / "nix"
    canonical.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], cwd=canonical)
    _instrument(canonical)
    _git(["add", "-A"], cwd=canonical)
    _git(["commit", "-q", "-m", "fixture"], cwd=canonical)
    monkeypatch.setattr(gate, "CANONICAL", canonical)
    monkeypatch.setattr(gate, "SCAN_ROOT", scan_root)
    return canonical


def _run(tree: Path) -> CheckResult:
    """Drive the gate's real run() against the redirected constants."""
    return gate.run(Mode.VERIFY, Context(nix_home=tree, mode=Mode.VERIFY))


# --- non-vacuity ---------------------------------------------------------


def test_healthy_topology_PASSES_and_the_population_is_not_empty(
    real_tree: Path,
) -> None:
    """Non-vacuity: the gate sees a real tree before any plant is introduced."""
    result = _run(real_tree)
    assert result.status is Status.PASS, result.detail
    # The evidence must prove it actually FOUND something, not that it found
    # nothing and called the empty set clean.
    assert "1 tree(s)" in result.evidence, result.evidence
    assert "registered worktree(s)" in result.evidence, result.evidence


def test_the_real_canonical_path_is_the_documented_absolute_path() -> None:
    """The constant is the stable path ARC 026 Phase 0.4 established."""
    assert gate.CANONICAL == Path("/home/bbt/nix")
    assert gate.SCAN_ROOT == Path("/home/bbt")


# --- plant 1: the orphan tree (the failure class that bared this repo) ----


def test_an_ORPHAN_TREE_fails_and_NAMES_the_orphan_path(real_tree: Path) -> None:
    """Plant: a tree holding the instrument that no worktree accounts for."""
    orphan = real_tree.parent / "nix-orphan"
    orphan.mkdir()
    _instrument(orphan)

    result = _run(real_tree)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    # THE REASON, not the status: the orphan must be named at its site.
    assert str(orphan) in result.site, result.site
    assert str(orphan) in result.detail, result.detail
    assert "no registered git worktree accounts for" in result.detail
    # And it must not counsel deletion, which is what ARC 026 proved costly.
    assert "proving it holds nothing unique" in result.detail


def test_removing_the_orphan_restores_PASS_on_the_same_population(
    real_tree: Path,
) -> None:
    """Unplant: without the last step this shows only that a gate can fail."""
    orphan = real_tree.parent / "nix-orphan"
    orphan.mkdir()
    _instrument(orphan)
    assert _run(real_tree).status is Status.FAIL_NEEDS_OPERATOR

    (orphan / "scripts" / "verify.py").unlink()

    restored = _run(real_tree)
    assert restored.status is Status.PASS, restored.detail


def test_a_REGISTERED_worktree_holding_the_instrument_is_NOT_an_orphan(
    real_tree: Path,
) -> None:
    """The gate must permit the per-arc worktrees Stage 1 depends on.

    This is the discrimination that matters: a sibling tree holding
    `scripts/verify.py` is a FINDING when unregistered and FINE when
    registered. If the gate could not tell those apart it would either ban
    legitimate sub-agent worktrees or miss every orphan.
    """
    sibling = real_tree.parent / "nix-wt-arc-999-a"
    _git(["worktree", "add", "-q", "-b", "arc-999-a", str(sibling)], cwd=real_tree)
    assert (sibling / "scripts" / "verify.py").is_file()

    result = _run(real_tree)

    assert result.status is Status.PASS, result.detail
    assert "2 tree(s)" in result.evidence, result.evidence


# --- plant 2: the bare canonical path (the ARC 019 / ARC 026 hazard) ------


def test_a_BARE_canonical_path_fails_and_NAMES_core_bare_and_the_repair(
    real_tree: Path,
) -> None:
    """Plant the exact condition that bared this repository on 2026-08-12."""
    _git(["config", "core.bare", "true"], cwd=real_tree)

    result = _run(real_tree)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert str(real_tree) in result.site, result.site
    # THE REASON: the condition named, and the repair named.
    assert "core.bare=true" in result.evidence, result.evidence
    assert "BARE repository but holds a working tree" in result.detail
    assert "config --unset core.bare" in result.detail
    # It must actively warn against the delete that ARC 026 refused.
    assert "Do NOT delete the tree" in result.detail


def test_unsetting_core_bare_restores_PASS(real_tree: Path) -> None:
    """Unplant: the documented repair returns the population to clean."""
    _git(["config", "core.bare", "true"], cwd=real_tree)
    assert _run(real_tree).status is Status.FAIL_NEEDS_OPERATOR

    _git(["config", "--unset", "core.bare"], cwd=real_tree)

    restored = _run(real_tree)
    assert restored.status is Status.PASS, restored.detail


# --- §7.12 closures: the ways this gate could pass while measuring nothing -


def test_a_scan_that_cannot_see_the_canonical_tree_is_CANNOT_MEASURE(
    real_tree: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§7.12 closure (1)/(3): an empty scan must never read as clean."""
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    monkeypatch.setattr(gate, "SCAN_ROOT", empty)

    result = _run(real_tree)

    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "did not appear among" in result.detail
    assert "proves nothing about orphans" in result.detail


def test_git_returning_no_registrations_is_CANNOT_MEASURE_not_PASS() -> None:
    """§7.12 closure (2): 'no answer' is not the claim 'no orphans'."""
    canonical = Path("/home/bbt/nix")
    result = gate.evaluate(canonical, [canonical], [], [], "")

    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "not the same claim as" in result.detail


def test_a_bare_MARKED_worktree_fails_even_when_the_setting_reads_unset() -> None:
    """Belt and braces: git's own `bare` marker is honoured independently.

    `core.bare` and git's porcelain `bare` line are two sources for one fact.
    Trusting only the setting would miss a repo git considers bare for another
    reason, and folding the bare path into the registered set would make the
    gate PASS on the state it exists to catch.
    """
    canonical = Path("/home/bbt/nix")
    result = gate.evaluate(canonical, [canonical], [canonical], [canonical], "")

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "git-reports-bare=True" in result.evidence, result.evidence


# --- D3.22: the precedence defect that caused the arc ---------------------


def test_git_env_STRIPS_every_tree_selecting_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§7.12 closure (4). git honours these AHEAD of `-C`/`cwd` (D3.22)."""
    leaked = {
        "GIT_DIR": "/decoy/.git",
        "GIT_WORK_TREE": "/decoy",
        "GIT_INDEX_FILE": "/decoy/.git/index",
        "GIT_COMMON_DIR": "/decoy/.git",
        "GIT_OBJECT_DIRECTORY": "/decoy/.git/objects",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/decoy/.git/objects",
    }
    for key, value in leaked.items():
        monkeypatch.setenv(key, value)

    env = gate._git_env()  # pylint: disable=protected-access

    for key in leaked:
        assert key not in env, f"{key} survived the scrub — D3.22 is live again"
    # Non-git environment must survive, or the scrub is a blunt instrument.
    assert "PATH" in env


def test_the_gate_measures_the_RIGHT_repo_under_a_hostile_GIT_DIR(
    real_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end-to-end form of D3.22, with a REAL decoy repository.

    This is the case that bared this repository, reproduced: a git invocation
    that believes it is talking about the tree named on its command line while
    a hook-exported `GIT_DIR` points somewhere else. Without the scrub the gate
    reports on the decoy and its verdict is meaningless.
    """
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=decoy)
    _git(["config", "core.bare", "true"], cwd=decoy)
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))

    result = _run(real_tree)

    # The decoy is bare. If the leak were honoured this would FAIL on the
    # decoy's setting; the scrub means we measure the real tree, which is clean.
    assert result.status is Status.PASS, (
        f"GIT_DIR leaked into the measurement — the gate reported on the decoy: "
        f"{result.detail}"
    )
    assert str(real_tree) in result.site, result.site


# --- declarations ---------------------------------------------------------


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """Check contract v2 §6: declarations are read by AST, never by import."""
    from nixverify.declarations import read_all

    declared = read_all(REPO / "checks")[gate.NAME]
    assert declared.resources == ("subprocess:git",), declared.resources
    assert declared.depends_on == ()
    assert declared.correctable is False
    # Read by AST, so the reason must survive statically — a refusal whose
    # reason only exists at runtime cannot be audited by the plan builder.
    assert "must not be given rm" in declared.non_correctable_reason
    assert declared.errors == (), declared.errors


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """Non-correctable by declaration; the refusal must name the reason."""
    assert gate.CORRECTABLE is False
    assert "must not be given rm" in gate.NON_CORRECTABLE_REASON
    proc = subprocess.run(
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        check=False,
    )
    # THE REASON, not the exit code. The refusal is written to STDERR — asserted
    # against the stream it actually uses, because a control that greps the
    # wrong stream passes vacuously the moment the message moves.
    assert "REFUSED" in proc.stderr, proc.stderr
    assert "NON-CORRECTABLE" in proc.stderr, proc.stderr
    assert "must not be given rm" in proc.stderr, proc.stderr
    assert proc.returncode == 1, proc.returncode
