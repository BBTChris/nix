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


#: The synthetic tree's completion record. ARC 026 (B2): the gate now asks
#: whether the baseline's `owner` names an arc that can still discharge the
#: guard, and it derives "which arcs have completed" from `sessions/SESSION.md`.
#: A fixture without one measures the CANNOT_MEASURE path forever, so the
#: throwaway repo carries a real record — and the owner below names an arc that
#: record does NOT close, which is what makes the positive control positive.
_FIXTURE_CLOSED = tuple(range(1, 21))
_FIXTURE_LIVE_ARC = "ARC 021"


def _write_completion_record(home: Path) -> None:
    """A session log and a ledger series table for the throwaway tree."""
    (home / "sessions").mkdir(parents=True, exist_ok=True)
    (home / "docs").mkdir(parents=True, exist_ok=True)
    (home / "sessions" / "SESSION.md").write_text(
        "".join(f"## 2026-01-01 — ARC {n:03d}: closed\n\n" for n in _FIXTURE_CLOSED),
        encoding="utf-8",
    )
    (home / "docs" / "CHECK-DEBT.md").write_text(
        "| date | arc | open | note |\n|---|---|---|---|\n"
        f"| 2026-01-01 | ARC {max(_FIXTURE_CLOSED):03d} | 5 | fixture |\n",
        encoding="utf-8",
    )


def _write_baseline(home: Path, uncovered: list[str], **extra: object) -> None:
    payload: dict[str, object] = {
        "owner": _FIXTURE_LIVE_ARC,
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
    _write_completion_record(home)
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
    assert result.guard_owner == _FIXTURE_LIVE_ARC
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
    baseline["owner"] = "the bulk check retrofit arc (ARC 021+), sized in ARC 020"
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")

    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert f"{gate.BASELINE}:owner" in result.detail
    assert "RANGE" in result.detail


def test_the_REAL_baselines_owner_is_a_single_arc_AND_CAN_STILL_PAY(
    _pytest_needs_no_fixture=None,
) -> None:
    """The production artifact, pinned against BOTH iterations of the flaw.

    ARC 025 pinned the shape. `"ARC 025"` satisfies the shape and ARC 025 has
    since closed with the guard still standing, so shape alone is now known to be
    insufficient — the second assertion is the one that would have caught it.
    Derived from the live completion record, never from a number typed here.
    """
    from nixverify.contract import completed_arcs, guard_owner_defect

    payload = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))
    completed, error = completed_arcs(REPO)
    assert not error, error
    assert guard_owner_defect(payload["owner"]) == "", payload["owner"]
    assert guard_owner_defect(payload["owner"], completed) == "", payload["owner"]


def test_PLANT_a_baseline_owner_that_has_ALREADY_COMPLETED_is_CANNOT_MEASURE(
    repo: Path,
) -> None:
    """THE ARC 026 DEFECT, planted. `ARC 005` is closed in the fixture record.

    The gate must name its own field and say WHY — an operator handed a bare
    CANNOT_MEASURE cannot tell a dead owner from an unreadable file, and those
    have opposite repairs.
    """
    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    baseline["owner"] = "ARC 005"
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")

    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert f"{gate.BASELINE}:owner" in result.detail, result.detail
    assert "ALREADY COMPLETED" in result.detail, result.detail


def test_a_MISSING_completion_record_is_CANNOT_MEASURE_not_a_pass(
    repo: Path,
) -> None:
    """FAIL CLOSED. Without the record the gate cannot tell a live owner from a
    dead one, and 'probably still open' is the assumption that let `ARC 025`
    stand as an owner for a whole arc."""
    (repo / "sessions" / "SESSION.md").unlink()
    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot be judged" in result.detail, result.detail
    assert "SESSION.md" in result.detail, result.detail


def test_an_ADMITTING_arc_that_has_completed_stays_ACCEPTED(repo: Path) -> None:
    """Two tenses, one grammar. A receipt is not a promise (ARC 026 B2).

    `admitted` names the arc that ALREADY admitted a baseline addition. That arc
    completes and the record stays true — so the dischargeability rule must NOT
    reach it, or every honest `admitted` entry reddens at the next arc boundary.
    `ARC 005` is closed in the fixture's record and must be fine here while being
    a defect in `owner` (the test above).
    """
    _admit(repo, "scripts/module_new.py", arc="ARC 005")
    result = _run(repo)
    assert result.status is Status.GUARDED, result.detail


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


# --- ARC 027 (B2): THE RE-OWNING CEILING, CHECK-DEBT D2.31 -------------------
#
# The fourth iteration of one flaw. ARC 024 required a non-empty owner; ARC 025
# required exactly one arc; ARC 026 required that arc to be OPEN. Each rule
# judges the owner value STANDING TODAY, and a marker re-pointed at the next arc
# at every arc boundary passes all three forever while the debt is never paid.
# These tests drive the only arm that judges the SEQUENCE.


def _reown(repo: Path, arc: str) -> None:
    """Re-point the guard at `arc` and COMMIT it — a re-owning, as it really happens.

    The commit is the point. A lineage derived from the working tree is length 1
    by construction, so a fixture that only rewrote the file would exercise a
    ceiling that could never be reached.
    """
    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    baseline["owner"] = arc
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"re-own to {arc}")


def test_NONVACUITY_the_real_trees_owner_lineage_is_derived_from_COMMITTED_blobs() -> (
    None
):
    """Before any plant: the derivation reads history, and history has >1 owner.

    Doctrine C.3. A ceiling measured against a lineage that is always length 1 is
    an arm that is off. The real baseline has been re-owned twice, so the real
    tree is itself the proof that the derivation sees changes the working tree
    cannot show it.
    """
    history = gate._committed_history(REPO)
    assert not history.error, history.error
    assert len(history.revisions) > 1, "the ratchet's own file has a history"
    lineage = gate._owner_lineage(history)
    assert len(lineage) > 1, (
        f"the lineage must be read from committed blobs, not from the working "
        f"tree, which holds exactly one owner: {lineage}"
    )
    working = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))["owner"]
    assert lineage[-1] == working, (lineage, working)


def _touch(repo: Path) -> None:
    """Commit a NEW revision of the baseline that does not change the owner."""
    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    baseline["comment"] = [f"revision {len(baseline.get('comment', []))}"]
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "touch baseline, same owner")


def test_the_lineage_COLLAPSES_consecutive_duplicates_so_a_recommit_is_not_a_reowning(
    repo: Path,
) -> None:
    """Committing the file again without changing the owner is NOT a deferral.

    If it were, the ceiling would be a limit on how often the baseline may be
    touched, which is a different and useless property.
    """
    _touch(repo)  # same owner, new commit, different blob
    _touch(repo)
    lineage = gate._owner_lineage(gate._committed_history(repo))
    assert lineage == (_FIXTURE_LIVE_ARC,), lineage


def test_CONTROL_a_guard_reowned_TWICE_is_still_GUARDED_and_says_how_many_are_left(
    repo: Path,
) -> None:
    """Step 1 of §5.1. TWO re-ownings is the ceiling, not past it.

    This is the positive control the plant below is measured against, and it is
    also the live state of the real tree: `ARC 025+` -> `ARC 025` -> `ARC 027`.
    """
    _reown(repo, "ARC 022")
    _reown(repo, "ARC 023")

    result = _run(repo)
    assert result.status is Status.GUARDED, result
    assert result.guard_owner == "ARC 023"
    assert "2 re-owning(s) of a ceiling of 2" in result.evidence, result.evidence
    assert exit_code_for(result.status) == 3


def test_PLANT_the_THIRD_reowning_escalates_GUARDED_to_FAIL_naming_the_LINEAGE(
    repo: Path,
) -> None:
    """*A guard walked forward forever is an unpaid debt wearing a live owner.*

    The plant is the honest move, which is what makes it the right plant: every
    owner here is a single, well-formed, currently-OPEN arc, so the non-empty
    rule, the single-arc rule and the dischargeability rule are all satisfied at
    every step. Only the ceiling can see it.

    **The REASON is asserted, never the exit code** (contract rule 11): exit 1 is
    also what a regression, a stale baseline and a silent addition produce.
    """
    _reown(repo, "ARC 022")
    _reown(repo, "ARC 023")
    _reown(repo, "ARC 024")  # the third re-owning

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert result.site == f"{gate.BASELINE}:owner", result.site
    assert "RE-OWNED 3 times, exceeding the ceiling of 2" in result.detail, (
        result.detail
    )
    # The lineage itself is in the reason: an operator must be able to see the
    # sequence, because no single value in it is the offender.
    for owner in (_FIXTURE_LIVE_ARC, "ARC 022", "ARC 023", "ARC 024"):
        assert repr(owner) in result.detail, (owner, result.detail)
    assert "may not be walked forward again" in result.detail
    assert exit_code_for(result.status) == 1


def test_the_CLI_exits_1_on_the_third_reowning_and_prints_the_CEILING_reason(
    repo: Path,
) -> None:
    """§0e: the can-fail is reproduced by a committed, runnable artifact."""
    _reown(repo, "ARC 022")
    _reown(repo, "ARC 023")
    _reown(repo, "ARC 024")

    proc = _cli(repo)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 1, combined
    assert "RE-OWNED 3 times" in combined, combined
    assert "CHECK-DEBT D2.31" in combined, combined


def test_the_ceiling_CANNOT_be_reset_by_editing_the_WORKING_TREE_baseline(
    repo: Path,
) -> None:
    """The whole design claim, driven: the record is out of the editor's reach.

    An author who has exhausted the ceiling and wants a green has exactly one
    lever on this file — the file itself. Rewriting `owner`, deleting the
    `admitted` map, rewriting the whole payload: none of it touches the committed
    blobs the lineage is read from, and the FAIL survives every one.
    """
    _reown(repo, "ARC 022")
    _reown(repo, "ARC 023")
    _reown(repo, "ARC 024")
    assert _run(repo).status is Status.FAIL_NEEDS_OPERATOR

    baseline = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    baseline["owner"] = _FIXTURE_LIVE_ARC  # back to the original owner, uncommitted
    baseline["reownings"] = 0  # the field a naive design would have trusted
    (repo / gate.BASELINE).write_text(json.dumps(baseline), encoding="utf-8")

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        "the ceiling must be derived from committed history, not from any field "
        "in the file being judged"
    )
    assert "RE-OWNED 3 times" in result.detail, result.detail


def test_an_UNREADABLE_historical_revision_is_an_ERROR_not_a_skipped_reowning(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skipped revision could be exactly the one that changed the owner.

    Silently dropping it makes the lineage shorter, which makes the ceiling
    further away — the failure always points the safe-looking direction, which is
    why it must be an error rather than a `continue`.
    """
    _reown(repo, "ARC 022")
    real_git = gate._git

    def _blind(home: Path, *args: str) -> tuple[str, str]:
        if args and args[0] == "show":
            return "", "git show exit 128"
        return real_git(home, *args)

    monkeypatch.setattr(gate, "_git", _blind)
    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot establish the high-water mark" in result.detail, result.detail


def test_a_TRUNCATED_history_under_the_ceiling_is_CANNOT_MEASURE_never_GUARDED(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The limit truncates from the OLD end, which is where early owners live.

    A truncated lineage is a LOWER BOUND. Under the ceiling that proves nothing,
    so it may not stand as a deferral; over the ceiling it is still conclusive,
    which is why the ceiling arm is tested first. Both directions are driven —
    this test and the one below.
    """
    monkeypatch.setattr(gate, "_HISTORY_LIMIT", 1)
    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "LOWER BOUND" in result.detail, result.detail
    assert "TRUNCATED" in result.evidence, result.evidence


def test_a_TRUNCATED_history_ALREADY_over_the_ceiling_still_FAILS(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lower bound that already exceeds the ceiling has exceeded it."""
    _reown(repo, "ARC 022")
    _reown(repo, "ARC 023")
    _reown(repo, "ARC 024")
    monkeypatch.setattr(gate, "_HISTORY_LIMIT", 4)  # drops the oldest revision

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "RE-OWNED" in result.detail, result.detail


def test_the_LIVE_guard_on_the_real_tree_has_EXHAUSTED_its_ceiling() -> None:
    """The finding, banked as an assertion so it cannot quietly stop being true.

    This is not a hypothetical limit installed for a future offender. The one
    live guard in this repository has been re-owned TWICE — `the bulk check
    retrofit arc (ARC 025+)...` -> `ARC 025` -> `ARC 027` — and is therefore AT
    the ceiling. ARC 028 cannot re-point it: that move is the third re-owning and
    this gate now FAILs on it. The guard gets discharged or it goes red.
    """
    history = gate._committed_history(REPO)
    assert not history.error, history.error
    lineage = gate._owner_lineage(history)
    from nixverify.contract import GUARD_REOWN_CEILING, reowning_defect

    assert len(lineage) - 1 == GUARD_REOWN_CEILING, (
        f"the live guard's re-owning count has moved off the ceiling; if it went "
        f"UP this test is the alarm, and if it went DOWN the history was "
        f"rewritten (CLAUDE.md directive 6): {lineage}"
    )
    assert reowning_defect(lineage) == "", "at the ceiling is not over it"
    assert reowning_defect((*lineage, "ARC 028")) != "", (
        "the next re-owning must be a FAIL"
    )
