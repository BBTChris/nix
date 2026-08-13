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
# C0302: over the line ceiling since ARC 028 (C2) added the decomposition's own
# arms. Splitting a can-fail suite across files is how a plant loses sight of
# the control it is measured against (§5.1 requires both in one place).
# pylint: disable=too-many-lines
# pylint: disable=invalid-name,protected-access,redefined-outer-name
# pylint: disable=import-outside-toplevel,duplicate-code
# Test names SHOUT the property under test; the ratchet's helpers are private and
# are unit-tested directly because they are where the gate could go blind.

from __future__ import annotations

import json
import re
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


def _row(owner: str = _FIXTURE_LIVE_ARC, **extra: object) -> dict[str, object]:
    """One per-artifact row in the SHIPPED schema (ARC 028 C2)."""
    row: dict[str, object] = {
        "owner": owner,
        # `none` is the true value here: the fixture tree has no scripts/tests/,
        # so nothing names anything, and a row claiming `tests` would be the
        # false claim `_coverage_defects` exists to catch.
        "measured_by": "none",
        "reason": "fixture row",
    }
    row.update(extra)
    return row


def _write_baseline(home: Path, uncovered: list[str], **extra: object) -> None:
    """The fixture baseline, in the schema that SHIPS — not the historical one.

    ARC 028 (C2): v1 survives only as the reader for committed revisions, and it
    has its own test. A suite driving v1 while the tree installs v2 would be
    measuring a program this repository does not ship, which is the distinction
    `binding_census.py` exists to make.
    """
    payload: dict[str, object] = {
        "schema": 2,
        "artifacts": {path: _row() for path in sorted(uncovered)},
    }
    payload.update(extra)
    (home / gate.BASELINE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_baseline(home: Path) -> dict:
    return json.loads((home / gate.BASELINE).read_text(encoding="utf-8"))


def _save_baseline(home: Path, payload: dict) -> None:
    (home / gate.BASELINE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _set_owner(home: Path, owner: str, path: str | None = None) -> None:
    """Point one row's owner — or every row's — at `owner`, uncommitted."""
    payload = _read_baseline(home)
    for key in [path] if path else list(payload["artifacts"]):
        payload["artifacts"][key]["owner"] = owner
    _save_baseline(home, payload)


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
    payload = _read_baseline(repo)
    payload["artifacts"][path] = _row(**({"admitted": arc} if arc is not None else {}))
    _save_baseline(repo, payload)


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
    baseline = _read_baseline(repo)
    dropped = min(baseline["artifacts"])
    del baseline["artifacts"][dropped]
    _save_baseline(repo, baseline)

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
    _set_owner(repo, "the bulk check retrofit arc (ARC 021+), sized in ARC 020")

    result = _run(repo)
    # ARC 028 (C2/§0g): the value DIFFERS from the one committed at HEAD, so this
    # is an ASSIGNMENT and assignments FAIL rather than defer — see
    # `test_a_COMMITTED_range_owner_is_a_DEFERRAL_not_an_assignment_failure`
    # for the same value judged by the read rule.
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"{gate.BASELINE}:artifacts:" in result.detail
    assert ":owner" in result.detail
    assert "RANGE" in result.detail


def test_the_REAL_baselines_owner_is_a_single_arc_AND_THE_GATE_AGREES_WITH_THE_RECORD(
    _pytest_needs_no_fixture=None,
) -> None:
    """The production artifact, pinned against BOTH iterations of the flaw — and
    now against the third, which is that a GUARD CANNOT SURVIVE ITS OWNER'S OWN
    CLOSE-OUT.

    ## Why this control was re-aimed in ARC 027, and what it did NOT give up

    It used to assert `guard_owner_defect(owner, completed) == ""` — *the real
    baseline's owner can still pay.* That is a statement about one happy state,
    and ARC 027 walked into the state where it is false BY CONSTRUCTION:

      * ARC 026 pointed `owner` at `ARC 027`, so that ARC 027 would discharge it.
      * `completed_arcs` derives completion from `##` headings in
        `sessions/SESSION.md`.
      * **Every arc's close-out appends exactly such a heading.** So the instant
        ARC 027 writes its own summary, `ARC 027` is a closed arc and a guard
        naming it is dead — while the ARC 027 re-owning ceiling (2 of 2 used)
        forbids walking the marker forward to ARC 028.

    Three rules, each correct, meeting at a state the old assertion calls a bug.
    It is not a bug: it is the ceiling working. **The general rule it exposes is
    that a guard's owner must always name a FUTURE arc, never the arc in flight**
    — and this one has run out of future. Recorded as D3.40.

    ## What is asserted instead, and why it is STRICTER

    The shape assertion is kept verbatim: a range, or an empty owner, still
    fails here. What replaces the happy-state assertion is a two-directional
    agreement between the gate's verdict on the REAL tree and the live
    completion record:

      * owner CLOSED  -> the gate must be CANNOT_MEASURE, naming its own field
                         and saying ALREADY COMPLETED.
      * owner LIVE    -> the gate must be GUARDED carrying that owner, or PASS
                         if there is nothing left to guard.

    The old form could only ever fail one way and could sit permanently red once
    it did. This one has no permanently-red state and **catches a verdict that
    disagrees with the record in EITHER direction** — including the one the old
    assertion could not see: a gate reporting GUARDED under a dead owner.
    """
    from nixverify.contract import completed_arcs, guard_owner_defect

    payload = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))
    # ARC 028 (C2): one owner per ARTIFACT. The shape rule is asserted for EVERY
    # row rather than for one field, which is the decomposition paying for
    # itself here — a single malformed row can no longer hide behind fifteen
    # well-formed ones.
    owners = {path: row["owner"] for path, row in payload["artifacts"].items()}
    assert owners, "the real baseline holds no rows; this control has no subject"
    completed, error = completed_arcs(REPO)
    assert not error, error
    for path, owner in owners.items():
        assert guard_owner_defect(owner) == "", (path, owner)

    result = _run(REPO)
    dead = {p: o for p, o in owners.items() if guard_owner_defect(o, completed)}
    if dead:
        assert result.status is Status.CANNOT_MEASURE, result
        for path in dead:
            assert f"{gate.BASELINE}:artifacts:{path}:owner" in result.detail, path
        assert "ALREADY COMPLETED" in result.detail, result.detail
    else:
        # ARC 029 / 0.5: a live owner is necessary and no longer sufficient. The
        # re-owning CEILING can escalate GUARDED to FAIL even when every owner is
        # a live arc, so the expected verdict is DERIVED from the committed
        # lineage rather than assumed to be the healthy one.
        from nixverify.contract import (  # pylint: disable=import-outside-toplevel
            GUARD_REOWN_CEILING,
        )

        history = gate._committed_history(REPO)  # pylint: disable=protected-access
        assert not history.error, history.error
        over = {
            path
            for path in owners
            if len(gate._row_lineage(history, path)) - 1  # pylint: disable=protected-access
            > GUARD_REOWN_CEILING
        }
        if over:
            assert result.status is Status.FAIL_NEEDS_OPERATOR, result
            assert "ceiling" in result.detail, result.detail
            for path in over:
                assert path in result.detail, path
        else:
            assert result.status in (Status.GUARDED, Status.PASS), result
            if result.status is Status.GUARDED:
                assert result.guard_owner in set(owners.values()), result


def test_PLANT_a_baseline_owner_that_has_ALREADY_COMPLETED_is_CANNOT_MEASURE(
    repo: Path,
) -> None:
    """THE ARC 026 DEFECT, planted. `ARC 005` is closed in the fixture record.

    The gate must name its own field and say WHY — an operator handed a bare
    CANNOT_MEASURE cannot tell a dead owner from an unreadable file, and those
    have opposite repairs.
    """
    _set_owner(repo, "ARC 005")
    _git(repo, "add", "-A")
    # COMMITTED, so the read rule judges it rather than the §0g assignment rule.
    # The two arms answer the same question at different moments and this test
    # owns the READ one; the assignment one is planted separately below.
    _git(repo, "commit", "-qm", "own the guard from a closed arc")

    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result
    assert f"{gate.BASELINE}:artifacts:" in result.detail, result.detail
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
    _set_owner(repo, arc)
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

    **ARC 028 (C2) — AND THE PER-ROW ANSWER IS NOT UNIFORM, WHICH IS THE POINT.**
    The aggregate reported `2 of 2 re-ownings` for all sixteen artifacts. Read
    per path, thirteen of them carry
    `the bulk check retrofit arc (ARC 025+)... -> ARC 025 -> ARC 027` and are AT
    the ceiling; `scripts/nixverify/measurement_path.py` carries `ARC 025 ->
    ARC 027` and has one left; `scripts/nixverify/gitenv.py` and
    `scripts/nixverify/registry.py` were admitted in ARC 026 under the owner they
    still carry and have never been re-owned at all. That is not the ceiling
    being laundered — every one of those numbers is derived from committed
    blobs, and the short ones are short because those deferrals are YOUNGER.
    Asserted as a distribution rather than as a blanket, because a blanket would
    have to be wrong in one direction or the other.
    """
    history = gate._committed_history(REPO)
    assert not history.error, history.error
    assert len(history.revisions) > 1, "the ratchet's own file has a history"
    # COMMITTED vs COMMITTED, and the asymmetry is ARC 029 / 0.5's finding. This
    # read the WORKING baseline and compared its owner to the last COMMITTED one,
    # which makes any re-owning unlandable: the assertion is false from the moment
    # the file is edited until the commit that would make it true, and pre-commit
    # runs the suite before that commit exists. 0.5 re-pointed sixteen owners off
    # a completed arc — the repair the gate's own verdict demanded — and could not
    # commit it. The lineage is derived from history, so the value it is held
    # against must come from history too.
    head_blob, head_error = gate._git(  # pylint: disable=protected-access
        REPO, "show", f"HEAD:{gate.BASELINE}"
    )
    assert not head_error, head_error
    committed = json.loads(head_blob)
    working = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))
    lengths = []
    for path, row in committed["artifacts"].items():
        lineage = gate._row_lineage(history, path)
        assert lineage, f"{path}: no committed lineage at all"
        assert lineage[-1] == row["owner"], (path, lineage, row["owner"])
        lengths.append(len(lineage))
    # The WORKING tree is still held to the shape rule — one arc identifier, never
    # a range and never a phrase — which is the property `guard_owner_defect`
    # enforces and which must hold whether or not an edit is in flight.
    for path, row in working["artifacts"].items():
        assert re.fullmatch(r"ARC \d+", row["owner"]), (path, row["owner"])
    assert max(lengths) > 1, (
        "no row's lineage exceeds one value, so the derivation is reading the "
        "working tree rather than committed blobs and the ceiling arm is off"
    )


def _touch(repo: Path) -> None:
    """Commit a NEW revision of the baseline that does not change the owner."""
    baseline = _read_baseline(repo)
    baseline["comment"] = [f"revision {len(baseline.get('comment', []))}"]
    _save_baseline(repo, baseline)
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
    path = min(_read_baseline(repo)["artifacts"])
    lineage = gate._row_lineage(gate._committed_history(repo), path)
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
    assert "ceiling 2 applied PER ARTIFACT" in result.evidence, result.evidence
    assert "2 of 2 re-owning(s) used" in result.detail, result.detail
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
    # ARC 028 (C2): the site is now PER ARTIFACT. Every row was re-owned three
    # times, so every row is named — which is the decomposition's whole claim,
    # and it is asserted here rather than trusted.
    rows = sorted(_read_baseline(repo)["artifacts"])
    assert rows, "no rows to re-own"
    for path in rows:
        assert f"{gate.BASELINE}:artifacts:{path}:owner" in result.site, path
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

    **ARC 029 / 0.5 MADE THAT MOVE, and this control now covers both states.**
    Thirteen artifacts were re-pointed off the COMPLETED `ARC 027` to `ARC 030` —
    which the gate's own CANNOT_MEASURE verdict had instructed — and the ceiling
    fired: `... -> 'ARC 025' -> 'ARC 027' -> 'ARC 030'` is the fourth owner, three
    re-ownings, one over. The red is KEPT (D3.104) rather than reverted, because
    reverting restores a completed arc as owner and that is the masking this gate
    exists to refuse. So the assertion is no longer "everything is exactly AT the
    ceiling": it is that nothing has gone DOWN, and that anything OVER is already
    reported as a defect rather than waiting for a further move.
    """
    from nixverify.contract import GUARD_REOWN_CEILING, reowning_defect

    history = gate._committed_history(REPO)
    assert not history.error, history.error
    working = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))
    exhausted = {
        path: gate._row_lineage(history, path)
        for path in working["artifacts"]
        if len(gate._row_lineage(history, path)) - 1 >= GUARD_REOWN_CEILING
    }
    assert exhausted, (
        "NO artifact is at the ceiling any more; if the counts went DOWN the "
        "history was rewritten (CLAUDE.md directive 6) or the decomposition "
        "laundered them, and either is the alarm this test exists to raise"
    )
    for path, lineage in exhausted.items():
        moves = len(lineage) - 1
        if moves == GUARD_REOWN_CEILING:
            assert reowning_defect(lineage) == "", "at the ceiling is not over it"
            assert reowning_defect((*lineage, "ARC 999")) != "", (
                f"{path}: the next re-owning must be a FAIL"
            )
        else:
            # OVER the ceiling — measured in ARC 029 / 0.5, when thirteen of these
            # were re-pointed off the completed ARC 027 to a fourth owner. The
            # ruling's whole point is that this state is not tolerable, so the
            # defect must already be reported rather than waiting for a next move.
            assert moves > GUARD_REOWN_CEILING, (path, lineage)
            assert reowning_defect(lineage) != "", (
                f"{path}: {moves} re-ownings exceeds the ceiling of "
                f"{GUARD_REOWN_CEILING} and the rule reported nothing — the "
                "ceiling is off"
            )


# ===========================================================================
# ARC 028 (C2) — THE DECOMPOSITION. ARCHITECT RULING against CHECK-DEBT D3.40.
#
# **A RETROFITTED CHECK IS A NEW CHECK** (check contract v2, rule 9). This arc
# replaced one guard over sixteen artifacts with one guard PER artifact, added a
# `measured_by` claim that is checked, and added the §0g assignment arm. Every
# arm above was re-measured against the new shape rather than re-pointed until
# it passed; the arms below are the new ones, each planted.
#
# §7.12, asked of this section: what would have to be true for the decomposition
# to "succeed" while measuring nothing? The file could simply have more rows in
# it, and a test could assert the row count. That is a measurement of a text
# edit. So no test here counts rows: every one of them PERTURBS a row and
# requires the gate to go non-green NAMING THAT ROW.
# ===========================================================================


def _declare_in_flight(home: Path, arc: int) -> None:
    """Append a series row for `arc`, which the session log does not close.

    That is exactly the shape of a live arc in this repository — the ledger's
    series row is written DURING the arc, the session heading AT CLOSE — so it
    is what `contract.in_flight_arc` reads. Without it the fixture has no arc in
    flight and the §0g arm is correctly inert.
    """
    ledger = home / "docs" / "CHECK-DEBT.md"
    ledger.write_text(
        ledger.read_text(encoding="utf-8")
        + f"| 2026-01-02 | ARC {arc:03d} | 6 | in flight |\n",
        encoding="utf-8",
    )


def test_the_HISTORICAL_v1_READER_is_what_stops_the_split_LAUNDERING_the_ceiling(
    repo: Path,
) -> None:
    """**THE §0a DEFECT FOR THIS STEP, PLANTED AND MEASURED.**

    A decomposition that read only the new schema would give every row a lineage
    of length 1 — nought re-ownings — and a ceiling built over an arc would be
    reset by a change of file format. Nothing else in this suite would notice:
    the row count would be right, every row would be well-formed, and the gate
    would be a cheerful GUARDED.

    The fixture reproduces the real migration exactly: a history committed under
    the FLAT schema, re-owned to the ceiling, then a working tree rewritten into
    the per-artifact schema. The assertion is that the ceiling still bites.
    """
    payload = _read_baseline(repo)
    paths = sorted(payload["artifacts"])

    # A v1 history: three flat revisions, two re-ownings, exactly like the real
    # file's `ARC 025+ -> ARC 025 -> ARC 027`.
    for arc in (_FIXTURE_LIVE_ARC, "ARC 022", "ARC 023"):
        _save_baseline(repo, {"owner": arc, "uncovered": paths, "admitted": {}})
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"flat schema owned by {arc}")

    history = gate._committed_history(repo)
    assert history.revisions[-1][1].schema == 1, "the history must be flat here"
    for path in paths:
        assert gate._row_lineage(history, path) == (
            _FIXTURE_LIVE_ARC,
            "ARC 022",
            "ARC 023",
        ), path

    # Now the migration: same set, same owners, per-artifact shape.
    _save_baseline(
        repo, {"schema": 2, "artifacts": {p: _row("ARC 023") for p in paths}}
    )
    assert _read_baseline(repo)["schema"] == 2
    control = _run(repo)
    assert control.status is Status.GUARDED, control.detail
    assert "2 of 2 re-owning(s) used" in control.detail, control.detail

    # And the third re-owning is still a FAIL, per row, after the migration.
    _set_owner(repo, "ARC 024")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the third re-owning, in the new schema")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "RE-OWNED 3 times" in result.detail, result.detail
    for path in paths:
        assert f"{gate.BASELINE}:artifacts:{path}:owner" in result.site, path


def test_PLANT_a_row_that_CANNOT_SAY_WHY_it_is_uncovered_FAILS_naming_it(
    repo: Path,
) -> None:
    """A row with no `reason` is a suppression entry wearing a per-artifact shape."""
    payload = _read_baseline(repo)
    victim = sorted(payload["artifacts"])[3]
    payload["artifacts"][victim]["reason"] = "   "
    _save_baseline(repo, payload)

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert f"{gate.BASELINE}:artifacts:{victim}" in result.site, result.site
    assert "no `reason`" in result.detail, result.detail
    assert result.detail.count("no `reason`") == 1, (
        "exactly one row was perturbed; the arm must not implicate the others"
    )


def test_PLANT_an_UNCLASSIFIED_row_FAILS_naming_the_row_and_the_allowed_values(
    repo: Path,
) -> None:
    """`measured_by` is the field that separates 'the suite reaches it' from
    'nothing in this repository names it'. A row that declines to answer is the
    aggregate wearing a per-artifact shape, and it must not pass."""
    payload = _read_baseline(repo)
    victim = sorted(payload["artifacts"])[5]
    payload["artifacts"][victim]["measured_by"] = "sort of"
    _save_baseline(repo, payload)

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert f"{gate.BASELINE}:artifacts:{victim}" in result.site, result.site
    assert "'sort of'" in result.detail, result.detail
    assert "['tests', 'none']" in result.detail, result.detail


def test_PLANT_a_FALSE_claim_of_test_coverage_FAILS_naming_the_row(
    repo: Path,
) -> None:
    """The claim is CHECKED, in the direction that flatters the row.

    `measured_by: tests` on an artifact no test module names is the same species
    of defect as a check adding a path to `SUBJECTS` and never opening the file
    (D3.16) — a declaration standing in for a measurement. The fixture tree has
    no `scripts/tests/`, so nothing names anything, and the claim is false.
    """
    payload = _read_baseline(repo)
    victim = sorted(payload["artifacts"])[1]
    payload["artifacts"][victim]["measured_by"] = "tests"
    _save_baseline(repo, payload)

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert f"{gate.BASELINE}:artifacts:{victim}:measured_by" in result.site, result.site
    assert "the claim is false" in result.detail, result.detail


def test_PLANT_a_STALE_claim_that_NOTHING_measures_it_FAILS_when_something_does(
    repo: Path,
) -> None:
    """The other direction, and it matters as much.

    A row that says nothing measures it, while a test module names it, is how an
    artifact that HAS acquired coverage keeps its place in the accepted set. The
    plant writes a real test module naming a real row, and leaves the row's
    claim alone.
    """
    payload = _read_baseline(repo)
    victim = sorted(payload["artifacts"])[2]
    assert payload["artifacts"][victim]["measured_by"] == "none"

    tests = repo / "scripts" / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_victim.py").write_text(
        f'"""x."""\n\n\ndef test_it() -> None:\n    assert "{victim}"\n',
        encoding="utf-8",
    )
    _git(repo, "add", "-A")

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert f"{gate.BASELINE}:artifacts:{victim}:measured_by" in result.site, result.site
    assert "the row is stale and understates" in result.detail, result.detail
    assert "scripts/tests/test_victim.py" in result.detail, result.detail


def test_the_classifier_matches_by_IMPORTABLE_NAME_and_never_by_a_PACKAGE(
    repo: Path,
) -> None:
    """Two properties, and the second is the one that keeps the answer honest.

    A test module imports `nixverify.gitenv`; it never writes the file path. A
    path-only classifier would call ten thoroughly-driven modules
    named-by-nothing, which is a FALSE RED that would make the distinction
    worthless. So the dotted name matches too.

    `__init__.py` is excluded from that, deliberately: its package name is in
    every `from nixverify... import` line in the tree, so a dotted match would
    mark it covered on the strength of imports of its SIBLINGS.
    """
    assert gate._importable_name("scripts/nixverify/gitenv.py") == "nixverify.gitenv"
    assert gate._importable_name("checks/_preamble.py") == "_preamble"
    assert gate._importable_name("scripts/runtime_gate.py") == "runtime_gate"
    # A FICTIONAL path on purpose. The first spelling of this line used a REAL
    # baseline row, and the classifier — which counts any textual mention —
    # promptly reported that row as named by a test module, reddening the gate
    # on the real tree. The instrument became the artefact. Recorded as
    # CHECK-DEBT D3.62 rather than papered over with an exclusion for this file.
    assert gate._importable_name("checks/no_such_expected.json") == ""
    assert gate._importable_name("scripts/somepackage/__init__.py") == "", (
        "a package __init__ must not be matched by its package name"
    )

    tests = repo / "scripts" / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_imports.py").write_text(
        '"""x."""\n\nfrom module_07 import thing\n', encoding="utf-8"
    )
    named = gate._named_by_tests(repo, ["scripts/module_07.py", "scripts/module_08.py"])
    assert named["scripts/module_07.py"] == ["scripts/tests/test_imports.py"]
    assert named["scripts/module_08.py"] == []


def test_NONVACUITY_the_classifier_DISCRIMINATES_on_the_real_tree() -> None:
    """A classifier that answered the same thing for every row would be vacuous.

    Asserted against the REAL baseline: some rows are named by test modules and
    some are named by nothing at all, so the field carries information. This is
    also where the ARC 028 brief was CORRECTED — it said two artifacts are
    covered by nothing; measured, it is FOUR, and the fourth is the `nixverify`
    package initialiser — EXECUTED by every import in this repository and
    ASSERTED ABOUT nowhere. Its path is deliberately not written out here: the
    classifier counts any textual mention, so naming a `none` row in this file
    would make the row read as covered BY THIS FILE. Measured the hard way, and
    recorded as CHECK-DEBT D3.62.
    """
    payload = json.loads((REPO / gate.BASELINE).read_text(encoding="utf-8"))
    named = gate._named_by_tests(REPO, sorted(payload["artifacts"]))
    unnamed = sorted(path for path, hits in named.items() if not hits)

    # THE LIVE-TREE ARM: every row's stored classification agrees with what the
    # classifier derives right now. This is the invariant that stays meaningful
    # however healthy the tree becomes.
    for path, row in payload["artifacts"].items():
        expected = "none" if path in unnamed else "tests"
        assert row["measured_by"] == expected, (path, row["measured_by"], expected)


def test_NONVACUITY_the_classifier_DISCRIMINATES_on_a_CONSTRUCTED_tree(
    tmp_path: Path,
) -> None:
    """The discrimination proof, moved off the live tree — ARC 029 / 0.5.

    **This control used to assert that the REAL baseline contained at least one
    row named by nothing, and 0.5 broke it by covering the last one.** That is
    the wrong dependency: a non-vacuity arm anchored to a DEFECT in the live tree
    dies exactly when the tree improves, so the suite would have punished the
    repair and the cheapest way back to green would have been to un-cover an
    artifact. Measured, in this arc, by it happening.

    The property — the classifier answers differently for a named path and an
    unnamed one, so the field carries information — is proven here against a
    CONSTRUCTED tree that holds both cases by construction. D3.100's rule again:
    an instrument whose input is the ambient state measures the ambient state.
    """
    tests_dir = tmp_path / "scripts" / "tests"
    tests_dir.mkdir(parents=True)
    (tmp_path / "some_module.py").parent.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_names_one.py").write_text(
        '"""A control that names some_module.py and nothing else."""\n',
        encoding="utf-8",
    )

    named = gate._named_by_tests(  # pylint: disable=protected-access
        tmp_path, ["some_module.py", "never_mentioned_anywhere.py"]
    )
    assert named["some_module.py"], "a path a test module names read as unnamed"
    assert not named["never_mentioned_anywhere.py"], (
        "a path NO test module mentions read as named — the classifier says yes "
        "to everything and the field carries no information"
    )


def test_PLANT_assigning_the_guard_to_the_ARC_IN_FLIGHT_is_REJECTED_naming_the_row(
    repo: Path,
) -> None:
    """**STANDING RULE §0g, and it is CHECK-DEBT D3.40's general rule made
    mechanical.**

    ARC 026 pointed this guard at `ARC 027` and every read-time rule accepted it,
    because at the moment of writing `ARC 027` had not closed. It closed by
    appending its own summary, and the guard was dead the same day. No rule that
    judges a value at READ time can see that.

    The plant is the honest-looking move: a single, well-formed, currently-OPEN
    arc — the arc doing the writing. The read rule passes it. §0g does not.
    """
    live = int(_FIXTURE_LIVE_ARC.split()[1])
    _declare_in_flight(repo, live)
    from nixverify.contract import in_flight_arc

    assert in_flight_arc(repo) == (live, ""), in_flight_arc(repo)

    victim = sorted(_read_baseline(repo)["artifacts"])[4]
    _set_owner(repo, _FIXTURE_LIVE_ARC, path=victim)  # unchanged: still committed
    control = _run(repo)
    assert control.status is Status.GUARDED, control.detail

    _set_owner(repo, "ARC 022", path=victim)  # a DIFFERENT live arc — fine
    assert _run(repo).status is Status.GUARDED

    _set_owner(repo, _FIXTURE_LIVE_ARC, path=victim)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "back to the committed owner")
    # Now ASSIGN the arc in flight to a row that did not name it.
    other = sorted(_read_baseline(repo)["artifacts"])[6]
    _set_owner(repo, _FIXTURE_LIVE_ARC, path=other)
    assert _run(repo).status is Status.GUARDED, (
        "the value was already that; no assignment"
    )

    _set_owner(repo, "ARC 022", path=other)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "own it from another arc")
    _set_owner(repo, _FIXTURE_LIVE_ARC, path=other)

    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert f"{gate.BASELINE}:artifacts:{other}:owner" in result.site, result.site
    assert "is the arc IN FLIGHT" in result.detail, result.detail
    assert "CHECK-DEBT D3.40" in result.detail, result.detail
    assert exit_code_for(result.status) == 1


def test_a_COMMITTED_dead_owner_DEFERS_while_ASSIGNING_one_now_FAILS(
    repo: Path,
) -> None:
    """The two arms answer the same question at different MOMENTS, and the
    difference in verdict is the rule, not an inconsistency.

    A dead owner already in the committed file is a debt somebody left behind:
    CANNOT_MEASURE, certification withheld. The same value being written NOW is
    somebody creating that debt in this working tree, with the record in front
    of them: FAIL. An instrument that gave both the same colour could not tell
    an inherited problem from one being made.
    """
    victim = min(_read_baseline(repo)["artifacts"])

    _set_owner(repo, "ARC 005", path=victim)
    assigning = _run(repo)
    assert assigning.status is Status.FAIL_NEEDS_OPERATOR, assigning.detail
    assert "ALREADY COMPLETED" in assigning.detail, assigning.detail
    assert f"{gate.BASELINE}:artifacts:{victim}:owner" in assigning.site

    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "commit the dead owner")
    inherited = _run(repo)
    assert inherited.status is Status.CANNOT_MEASURE, inherited.detail
    assert "ALREADY COMPLETED" in inherited.detail, inherited.detail


def test_the_REAL_TREES_in_flight_arc_would_be_REFUSED_as_an_owner_TODAY() -> None:
    """§0g against the REAL records — and it must survive its own close-out.

    Doctrine C.8 forbids planting into `checks/gate_coverage_baseline.json`, so
    the drive above lands in a throwaway repository. What is asserted HERE is
    that the rule is not inert.

    ## Why this control was re-aimed, and it is D3.40 RECURRING INSIDE D3.40'S FIX

    Its first spelling asserted `in_flight_arc(REPO) is not None` — *the real
    records identify a running arc, and naming it would be refused.* MEASURED at
    ARC 028's own close-out: that assertion is **false by construction, for every
    arc, forever.** `in_flight_arc` derives the running arc as the newest series
    row the session log does not close; the close-out APPENDS the `##` heading
    that closes it. So the control went red at the write-back of the very arc
    that built it.

    That is precisely the shape D3.40 recorded one layer down — a guard whose
    input is derived from the close-out record cannot survive the close-out — and
    it reappeared **inside the mechanism written to prevent it**. Recorded as
    D3.100 rather than quietly patched, because the recurrence is the finding.

    ## What is asserted instead, and why it is STRICTER

    Two arms, and neither can be satisfied by the other:

      * The rule is driven against a **constructed** in-flight arc, so the §0g
        arm is exercised on every run in every phase of every arc — mid-arc and
        at close-out alike. The old form exercised it only mid-arc, which is the
        half of the cycle where nobody is reading.
      * The real records are still read, and `in_flight_arc` must ANSWER — an
        error is a failure, because "which arc is running" being unanswerable is
        the reading that turns §0g off. When it answers *an* arc, naming that arc
        must be refused. When it answers *none* — the between-arcs and close-out
        state — that is reported, not asserted away, and it is not a defect.
    """
    from nixverify.contract import (
        completed_arcs,
        guard_owner_assignment_defect,
        guard_owner_defect,
        in_flight_arc,
    )

    completed, completion_error = completed_arcs(REPO)
    assert not completion_error, completion_error
    assert completed, "no completed arc parsed from the session log — scope is empty"

    # ARM 1 -- the rule itself, exercised unconditionally against a CONSTRUCTED
    # in-flight arc. This is what keeps §0g bound at close-out.
    synthetic = max(completed) + 1
    defect = guard_owner_assignment_defect(f"ARC {synthetic:03d}", completed, synthetic)
    assert "is the arc IN FLIGHT" in defect, defect
    # And the READ rule does not catch it, which is why §0g had to exist at all.
    assert guard_owner_defect(f"ARC {synthetic:03d}", completed) == "", (
        "the read rule already refuses an in-flight owner, which would make the "
        "write-time rule redundant -- §0g exists because it does not"
    )

    # ARM 2 -- the real records must ANSWER the question, whatever the answer.
    live, error = in_flight_arc(REPO)
    assert not error, (
        f"in_flight_arc could not answer: {error}. An unanswerable 'which arc is "
        "running' must never be read as 'none is' -- that reading is what turns "
        "the §0g rule off silently"
    )
    if live is not None:
        assert "is the arc IN FLIGHT" in guard_owner_assignment_defect(
            f"ARC {live:03d}", completed, live
        ), f"ARC {live:03d} is in flight and naming it as an owner was permitted"
