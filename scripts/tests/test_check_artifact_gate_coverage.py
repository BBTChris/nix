"""ARC 025 C2/C3 — re-binding `check_artifact_gate_coverage` after its retrofit.

**A RETROFITTED CHECK IS A NEW CHECK** (check contract v2 rule 9). This arc added
a git-derived ratchet and a validated owner to this gate, so its ARC 024 can-fail
does not survive and is re-established here from scratch: non-vacuity first, then
each arm planted and shown to FAIL naming its site, then the plant removed and the
same population passing.

**No plant touches a production artifact** (doctrine C.8): every plant lands in a
throwaway git repository under `tmp_path`. The two tests that touch the real tree
only READ it.
"""
# pylint: disable=invalid-name,protected-access,redefined-outer-name
# pylint: disable=import-outside-toplevel,duplicate-code
# Test names SHOUT the property under test; the ratchet's helpers are private and
# are unit-tested directly because they are where the gate could go blind.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_artifact_gate_coverage as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
    exit_code_for,
)

GATE_FILE = REPO / "checks" / "check_artifact_gate_coverage.py"
GIT = "/usr/bin/git"


def _git(home: Path, *args: str) -> None:
    """Run git against `home` and NOTHING else.

    `env=gate.git_env()` is not decoration. Without it this helper rewrote THIS
    worktree's real index: pre-commit exports `GIT_INDEX_FILE`, git honours it
    ahead of `-C`, and `git add -A` in a throwaway repo staged that repo's tree
    over the live one. The harness runs git exactly the way the gate does, so a
    hazard can never be invisible on one side and live on the other.
    """
    subprocess.run(
        [GIT, "-C", str(home), *args],
        check=True,
        capture_output=True,
        env=gate.git_env(),
    )


def _write_baseline(home: Path, uncovered: list[str], **extra: object) -> None:
    payload: dict[str, object] = {
        "owner": "ARC 025",
        "uncovered": sorted(uncovered),
        "admitted": {},
    }
    payload.update(extra)
    (home / gate.BASELINE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build(home: Path, *, commit_baseline: bool = True) -> Path:
    """A throwaway git repo with a credible artifact population, one commit deep.

    Enough tracked `.py`/`.json` artifacts to clear MIN_CREDIBLE_ARTIFACTS, one
    check that declares SUBJECTS so the covered/uncovered split is real, and — by
    default — a committed baseline so the ratchet has a high-water mark.
    """
    (home / "checks").mkdir(parents=True)
    (home / "scripts").mkdir(parents=True)
    artifacts = [f"scripts/module_{index:02d}.py" for index in range(25)]
    for path in artifacts:
        (home / path).write_text("x = 1\n", encoding="utf-8")
    (home / "checks" / "check_one.py").write_text(
        "DEPENDS_ON = ()\nRESOURCES = ()\n"
        f'SUBJECTS = ("scripts/module_00.py", "{gate.BASELINE}")\n',
        encoding="utf-8",
    )
    _write_baseline(home, artifacts[1:])
    _git(home, "init", "-q")
    _git(home, "config", "user.email", "t@example.com")
    _git(home, "config", "user.name", "t")
    if commit_baseline:
        _git(home, "add", "-A")
    else:
        _git(home, "add", "scripts", "checks/check_one.py")
    _git(home, "commit", "-qm", "baseline")
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """The default population: baseline committed, so the ratchet has a mark."""
    return _build(tmp_path / "repo")


def _admit(repo: Path, path: str, arc: str | None = None) -> None:
    """Land a genuinely NEW uncovered artifact and accept it into the baseline.

    The realistic shape of the attack C3 closes: a file lands, nobody writes a
    check for it, and the accepted set quietly widens by one. `arc` is the entry
    written into `admitted`; `None` writes none at all, which is the silent case.
    """
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text("z = 3\n", encoding="utf-8")
    _git(repo, "add", "-A")
    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    baseline["uncovered"] = sorted([*baseline["uncovered"], path])
    if arc is not None:
        baseline["admitted"] = {path: arc}
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")


def _run(home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _cli(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_FILE), str(home)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


# --- NON-VACUITY, BEFORE ANY PLANT (doctrine C.3, §5.3) ---------------------


def test_NONVACUITY_the_gates_scope_contains_its_own_subject_on_the_real_tree() -> None:
    """The gate must be able to SEE the baseline it ratchets, and the mark it uses.

    Doctrine C.3's incident is a rule whose inherited scope made it structurally
    unable to see the file it was written about. Asserted here against the real
    tree: the baseline is inside the enumerated artifact set, and the high-water
    mark resolves to a real commit.
    """
    artifacts, error = gate._tracked_artifacts(REPO)
    assert not error, error
    assert gate.BASELINE in artifacts, (
        "the gate must enumerate the very file its ratchet judges"
    )
    mark, sha, mark_error = gate._high_water_mark(REPO)
    assert not mark_error, mark_error
    assert len(sha) == 40, sha
    assert mark, "the high-water mark must be a real, non-empty committed set"


def test_CONTROL_the_clean_synthetic_repo_is_GUARDED_with_a_single_arc_owner(
    repo: Path,
) -> None:
    """Step 1 and step 6 of §5.1: the state every plant below is measured against."""
    result = _run(repo)
    assert result.status is Status.GUARDED, result
    assert result.guard_owner == "ARC 025"
    assert "high-water mark" in result.evidence
    assert exit_code_for(result.status) == 3


# --- C3: THE RATCHET --------------------------------------------------------


def test_PLANT_a_SILENT_addition_to_the_baseline_FAILS_naming_the_path(
    repo: Path,
) -> None:
    """*A baseline that can grow silently is a vacuous pass wearing a config file.*

    The addition here is the tempting one: a path that IS genuinely uncovered, so
    every pre-ARC-025 rule is satisfied — no regression (it is in the baseline
    now), no staleness (no check declares it). Only the ratchet sees it.
    """
    _admit(repo, "scripts/brand_new.py")

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"{gate.BASELINE}:admitted:scripts/brand_new.py" in result.site, result.site
    assert "ADDED to the accepted-uncovered set" in result.detail
    assert "a ratchet may only shrink" in result.detail
    assert "no discharging arc named" in result.detail
    assert "no check declares this artifact as a SUBJECT" not in result.detail, (
        "the baseline DOES accept it, so the pre-ARC-025 regression arm is silent — "
        "only the ratchet can see this, which is the whole point of C3"
    )


def test_PLANT_an_addition_admitted_by_a_RANGE_fails_with_the_RANGE_reason(
    repo: Path,
) -> None:
    """`"any ADDITION requires a named arc"` means ONE arc, by the same grammar.

    One function decides what an arc is (`contract.guard_owner_defect`), so the
    ratchet and `validate_result` cannot drift apart about it.
    """
    _admit(repo, "scripts/brand_new.py", "ARC 025+")

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "scripts/brand_new.py" in result.site
    assert "RANGE" in result.detail, result.detail
    assert "ARC 025+" in result.detail


def test_CONTROL_the_same_addition_with_a_single_named_arc_is_ACCEPTED(
    repo: Path,
) -> None:
    """The other half of the control: the ratchet permits an OWNED addition."""
    _admit(repo, "scripts/brand_new.py", "ARC 026")

    result = _run(repo)
    assert result.status is Status.GUARDED, result


def test_the_accepted_set_may_SHRINK_freely(repo: Path) -> None:
    """A ratchet that blocked tightening would be the opposite instrument."""
    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    dropped = baseline["uncovered"][0]
    baseline["uncovered"] = baseline["uncovered"][1:]
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")

    result = _run(repo)
    # The dropped path is now uncovered-and-unaccepted, i.e. a regression — which
    # is the pre-existing arm firing, not the ratchet blocking the shrink.
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert dropped in result.site
    assert "no check declares this artifact as a SUBJECT" in result.detail
    assert "a ratchet may only shrink" not in result.detail


def test_the_HIGH_WATER_MARK_CANNOT_be_edited_away_by_COMMITTING_the_addition(
    repo: Path,
) -> None:
    """**The laundering attack, and the reason the mark is a minimum over history.**

    `HEAD` alone would make this ratchet decorative: add the entry, commit, and one
    commit later the addition IS the prior state. The mark is the TIGHTEST revision
    the file has ever been committed with, so the laundry cycle has no effect —
    and moving it would mean rewriting banked history, which `CLAUDE.md` directive
    6 forbids and which changes every downstream sha.
    """
    _admit(repo, "scripts/brand_new.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "quietly widen the baseline")

    mark, sha, error = gate._high_water_mark(repo)
    assert not error, error
    assert "scripts/brand_new.py" not in mark, (
        "committing the addition must not turn it into the prior mark"
    )
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "scripts/brand_new.py" in result.site
    assert sha[:12] in result.detail


def test_a_baseline_with_NO_COMMIT_HISTORY_is_CANNOT_MEASURE(tmp_path: Path) -> None:
    """§7.12 closure 5: no mark means the growth question is unanswerable.

    An uncommitted baseline would otherwise be the cheapest possible defeat of
    this ratchet — no history, no prior mark, nothing to compare against. Never
    PASS on the half it can still see; the same discipline the masked-hazard rule
    applies to an unreachable subject.
    """
    home = _build(tmp_path / "nohist", commit_baseline=False)
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "no commit history" in result.detail
    assert "cannot be shown not to have grown" in result.detail
    assert exit_code_for(result.status) == 2


def test_an_UNREADABLE_historical_revision_is_an_ERROR_never_a_SKIP(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A silently skipped revision could be exactly the tightest one.

    That is this project's recurring defect class — a tracking state quietly
    setting a gate's scope — pointed at time rather than at a file list.
    """
    real = gate._git

    def broken(home: Path, *args: str) -> tuple[str, str]:
        if args and args[0] == "show":
            return "", "git show exit 128"
        return real(home, *args)

    monkeypatch.setattr(gate, "_git", broken)
    _, _, error = gate._high_water_mark(repo)
    assert "cannot establish the high-water mark" in error, error

    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result


def test_a_historical_revision_that_will_not_PARSE_is_also_an_ERROR(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable JSON in history is the same hole as an unreadable blob."""
    real = gate._git

    def corrupt(home: Path, *args: str) -> tuple[str, str]:
        if args and args[0] == "show":
            return "not json at all", ""
        return real(home, *args)

    monkeypatch.setattr(gate, "_git", corrupt)
    _, _, error = gate._high_water_mark(repo)
    assert "cannot establish the mark" in error, error


# --- C2: THE OWNER, ON THIS GATE --------------------------------------------


def test_a_baseline_owner_that_names_a_RANGE_is_CANNOT_MEASURE_naming_the_field(
    repo: Path,
) -> None:
    """The gate reports its own baseline as the offender, not the engine generically."""
    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    baseline["owner"] = "the bulk check retrofit arc (ARC 025+), sized in ARC 024"
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")

    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert f"{gate.BASELINE}:owner" in result.detail
    assert "RANGE" in result.detail


def test_the_REAL_baselines_owner_is_a_single_arc(
    _pytest_needs_no_fixture=None,
) -> None:
    """The production artifact this arc repaired, pinned so it cannot regress."""
    from nixverify.contract import guard_owner_defect

    payload = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))
    assert guard_owner_defect(payload["owner"]) == "", payload["owner"]


# --- THE PRE-EXISTING ARMS, RE-ESTABLISHED AFTER THE RETROFIT ---------------


def test_PLANT_a_REGRESSION_fails_naming_the_uncovered_artifact(repo: Path) -> None:
    """Arm 1 re-bound: a new uncovered artifact the baseline never accepted."""
    (repo / "scripts" / "unregistered.py").write_text("y = 2\n", encoding="utf-8")
    _git(repo, "add", "-A")

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "scripts/unregistered.py" in result.site
    assert "no check declares this artifact as a SUBJECT" in result.detail


def test_PLANT_a_STALE_baseline_entry_fails_naming_it(repo: Path) -> None:
    """Arm 2 re-bound: the baseline still accepts something a check now declares."""
    (repo / "checks" / "check_one.py").write_text(
        "DEPENDS_ON = ()\nRESOURCES = ()\n"
        'SUBJECTS = ("scripts/module_00.py", "scripts/module_01.py")\n',
        encoding="utf-8",
    )
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"{gate.BASELINE}:scripts/module_01.py" in result.site
    assert "tighten the baseline" in result.detail


def test_a_TINY_artifact_set_is_CANNOT_MEASURE(tmp_path: Path) -> None:
    """§7.12 closure 1, unchanged by the retrofit and re-proven after it."""
    (tmp_path / "checks").mkdir()
    _git(tmp_path, "init", "-q")
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "credibility floor" in result.detail


def test_the_CLI_exits_1_on_a_silent_addition_and_prints_the_path_and_the_reason(
    repo: Path,
) -> None:
    """The demonstrated FAIL path an operator sees — exit code AND the reason."""
    _admit(repo, "scripts/brand_new.py")

    proc = _cli(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "scripts/brand_new.py" in combined, combined
    assert "a ratchet may only shrink" in combined, combined


def test_the_gate_enumerates_the_DIRECTORY_IT_WAS_GIVEN_not_GIT_DIR(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambient `GIT_DIR` must not redirect this gate onto another repository.

    Git honours `GIT_DIR`/`GIT_INDEX_FILE` AHEAD of `-C`, so a gate run from
    inside a pre-commit hook or a rebase would enumerate whatever repository the
    outer operation was working on — and report a perfectly confident verdict
    about the wrong tree. Measured in this arc when the ORIGINAL version of this
    test file rewrote this worktree's own index.
    """
    monkeypatch.setenv("GIT_DIR", str(REPO / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(REPO))
    artifacts, error = gate._tracked_artifacts(repo)
    assert not error, error
    assert "scripts/module_00.py" in artifacts, artifacts
    assert gate.BASELINE in artifacts
    assert "scripts/verify.py" not in artifacts, (
        "GIT_DIR redirected the gate onto the real repository"
    )
    assert _run(repo).status is Status.GUARDED


def test_this_gates_declarations_are_literals_and_now_name_its_subprocess() -> None:
    """§4.4, plus the false declaration `check_observed_resource_claims` caught."""
    from nixverify.declarations import read_all

    declaration = read_all(REPO / "checks")[gate.NAME]
    assert declaration.errors == (), declaration.errors
    assert "subprocess:git" in declaration.resources, declaration.resources
    assert gate.BASELINE in declaration.subjects
