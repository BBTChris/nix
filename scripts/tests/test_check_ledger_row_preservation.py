"""`checks/check_ledger_row_preservation.py` — CAN-FAIL, on real git repositories.

ARC 037 / sub-agent F. CHECK-DEBT D3.272.

Every plant here DELETES A ROW and requires the gate to go RED **naming the
D-number**. A gate that answered "a row is missing" would satisfy an exit-code
assertion and be useless to the person who has to put the row back, so every
assertion in this file is on the REASON (check contract §18) and the exit code
is checked as well, never instead.

The fixtures are real git repositories built under `tmp_path`, because the
gate's whole evidence set is committed git objects and a fake would be a
different instrument. `_git` runs on the SCRUBBED environment for the reason
`docs/CHECK-DEBT.md` D3.22 records: `pre-commit` exports `GIT_INDEX_FILE`, git
honours it ahead of `-C`, and a throwaway `git add -A` once staged a scratch
tree over this worktree's real index.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=missing-function-docstring
# pylint: disable=duplicate-code,use-implicit-booleaness-not-comparison

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_ledger_row_preservation as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
    exit_code_for,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)
from nixverify.gitenv import scrubbed_env  # pylint: disable=wrong-import-position

GATE_FILE = REPO / "checks" / "check_ledger_row_preservation.py"
GIT = "/usr/bin/git"

#: Enough rows to clear `MIN_UNION_IDS`, and enough commits to clear
#: `MIN_REVISIONS`. Both floors are real and a fixture that cannot clear them
#: would test the CANNOT_MEASURE arm forever without saying so.
_ROWS = gate.MIN_UNION_IDS + 60
_COMMITS = gate.MIN_REVISIONS + 5


def _git(home: Path, *args: str) -> None:
    subprocess.run(
        [GIT, "-C", str(home), *args],
        check=True,
        capture_output=True,
        env=scrubbed_env(
            extra={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
            }
        ),
    )


def _row(index: int) -> str:
    return (
        f"| D3.{index} | subject number {index} that is long enough to clear the "
        f"hollow-row floor | ARC 001 | unassigned | verify |\n"
    )


def _ledger(ids: list[int]) -> str:
    head = "# CHECK-DEBT\n\n| # | subject | changed in | owner | owning module |\n"
    head += "|---|---|---|---|---|\n"
    return head + "".join(_row(index) for index in ids)


def _write(home: Path, ids: list[int]) -> None:
    (home / "docs").mkdir(parents=True, exist_ok=True)
    (home / gate.LEDGER).write_text(_ledger(ids), encoding="utf-8")


def _build(home: Path) -> Path:
    """A repository whose ledger GREW, commit by commit, exactly as the real one did."""
    home.mkdir(parents=True)
    _git(home, "init", "-q")
    _git(home, "config", "user.email", "t@example.com")
    _git(home, "config", "user.name", "t")
    per_commit = max(1, _ROWS // _COMMITS)
    ids: list[int] = []
    for step in range(_COMMITS):
        ids += list(range(len(ids) + 1, len(ids) + 1 + per_commit))
        _write(home, ids)
        _git(home, "add", "-A")
        _git(home, "commit", "-qm", f"step {step}")
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _build(tmp_path / "repo")


def _ctx(home: Path) -> Context:
    return Context(nix_home=home, mode=Mode.VERIFY)


def _live_ids(home: Path) -> list[int]:
    text = (home / gate.LEDGER).read_text(encoding="utf-8")
    return sorted(int(name.split(".")[1]) for name in gate.strict_ids(text))


def _drop(home: Path, *victims: str) -> None:
    """Delete rows from the working ledger. The plant, every time."""
    text = (home / gate.LEDGER).read_text(encoding="utf-8")
    kept = [
        line
        for line in text.splitlines(keepends=True)
        if not any(line.startswith(f"| {victim} |") for victim in victims)
    ]
    (home / gate.LEDGER).write_text("".join(kept), encoding="utf-8")


# ---------------------------------------------------------------------------
# THE UN-BROKEN HALF. A fixture that cannot go green proves nothing about a red.
# ---------------------------------------------------------------------------


def test_an_intact_ledger_passes_and_says_what_it_compared(repo: Path) -> None:
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert exit_code_for(result.status) == 0
    assert "committed revision(s)" in result.evidence
    assert "NO baseline file" in result.evidence
    assert str(_ROWS) in result.evidence or "row id(s)" in result.evidence


# ---------------------------------------------------------------------------
# THE PLANTS. Every one deletes a row; every assertion is on the D-NUMBER.
# ---------------------------------------------------------------------------


def test_ONE_deleted_row_reddens_and_the_refusal_NAMES_the_D_number(
    repo: Path,
) -> None:
    """The whole point of the gate, and the whole point of this file."""
    victim = f"D3.{_live_ids(repo)[-3]}"
    _drop(repo, victim)
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert exit_code_for(result.status) == 1
    assert victim in result.detail, (
        "the refusal did not NAME the missing row — 'a row is missing' is not a "
        f"reason anyone can act on: {result.detail!r}"
    )
    assert victim in result.site
    assert "append-only" in result.detail


def test_a_deletion_that_is_ALREADY_COMMITTED_still_reddens(repo: Path) -> None:
    """§7.12 door 2 — the D3.272 case exactly.

    ARC 036's fifteen rows were lost BY A COMMIT (the merge itself), so anything
    comparing the working tree against `HEAD` sees a clean tree. This gate unions
    over every commit reachable from `HEAD`, so the row survives in an ancestor
    blob and the finding survives with it.
    """
    victim = f"D3.{_live_ids(repo)[4]}"
    _drop(repo, victim)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "silently drop a row, exactly as a merge would")
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert victim in result.detail, (
        "a COMMITTED deletion went unseen — this is the D3.272 shape and the "
        f"whole reason the comparison is over history and not over HEAD: {result.detail!r}"
    )


def test_a_MERGE_that_drops_one_parents_rows_reddens_naming_every_one(
    repo: Path,
) -> None:
    """D3.272 REPRODUCED: two branches, and the merge keeps only ours.

    This is the integrator's resolver, staged. Branch `theirs` appends three
    rows; the merge takes OURS for the ledger; the three ids exist in a commit
    reachable from the merge and in no other. Every one must be named.
    """
    base_ids = _live_ids(repo)
    _git(repo, "checkout", "-q", "-b", "theirs")
    theirs = base_ids + [900, 901, 902]
    _write(repo, theirs)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "sub-agent rows")
    _git(repo, "checkout", "-q", "-")
    _write(repo, base_ids + [800])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "integrator rows")
    # `-s ours` is literally the resolver D3.272 records: keep our ledger, take
    # the branch. Every gate on the merged tree is green and three rows are gone.
    _git(repo, "merge", "-q", "-s", "ours", "-m", "merge theirs", "theirs")
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    for lost in ("D3.900", "D3.901", "D3.902"):
        assert lost in result.detail, (
            f"{lost} was dropped by the merge and the gate did not name it: "
            f"{result.detail!r}"
        )
    assert "D3.800" not in result.detail, (
        "a row that was never lost was reported missing — the gate manufactures "
        "findings and its reds are worth as little as its greens"
    )


def test_FIFTEEN_deleted_rows_are_all_named_not_summarised(repo: Path) -> None:
    """The real instance was fifteen. A finding list that truncates is D3.253."""
    victims = [f"D3.{index}" for index in _live_ids(repo)[10:25]]
    assert len(victims) == 15
    _drop(repo, *victims)
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    missing = [victim for victim in victims if victim not in result.detail]
    assert not missing, f"named {15 - len(missing)} of 15; silent about {missing}"


def test_a_row_HOLLOWED_but_kept_by_id_is_reported(repo: Path) -> None:
    """§7.12 door 7 — an id ratchet is satisfied by an id with nothing behind it."""
    victim = f"D3.{_live_ids(repo)[2]}"
    text = (repo / gate.LEDGER).read_text(encoding="utf-8")
    gutted = "".join(
        f"| {victim} |  |\n" if line.startswith(f"| {victim} |") else line
        for line in text.splitlines(keepends=True)
    )
    (repo / gate.LEDGER).write_text(gutted, encoding="utf-8")
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert victim in result.detail
    assert "under the" in result.detail and "floor" in result.detail


def test_an_id_the_ROW_GRAMMAR_cannot_see_is_reported(repo: Path) -> None:
    """§7.12 door 4c — one regex on both sides is a silent no-op.

    A `D4.x` row is invisible to the strict grammar. Both sides of the comparison
    use that grammar, so the row could be deleted tomorrow and nothing would move.
    The looser second grammar catches the drift at the moment it lands.
    """
    text = (repo / gate.LEDGER).read_text(encoding="utf-8")
    (repo / gate.LEDGER).write_text(
        text
        + "| D4.1 | a major number the strict grammar does not know | ARC 1 | x | y |\n",
        encoding="utf-8",
    )
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "D4.1" in result.detail
    assert "ROW GRAMMAR" in result.detail


# ---------------------------------------------------------------------------
# THE VACUITY DOORS. Every one must be CANNOT_MEASURE and never PASS.
# ---------------------------------------------------------------------------


def test_a_missing_ledger_is_CANNOT_MEASURE(tmp_path: Path) -> None:
    result = gate.run(Mode.VERIFY, _ctx(tmp_path))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert exit_code_for(result.status) == 2
    assert gate.LEDGER in result.detail


def test_a_directory_that_is_NOT_A_REPOSITORY_is_CANNOT_MEASURE(
    tmp_path: Path,
) -> None:
    """§7.12 door 3 — a failing git call must never read as 'nothing to compare'."""
    home = tmp_path / "bare"
    _write(home, list(range(1, _ROWS + 1)))
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "git could not answer" in result.detail


def test_a_TRUNCATED_history_is_CANNOT_MEASURE_not_PASS(tmp_path: Path) -> None:
    """§7.12 door 6 — a rewritten or shallow history has nothing to ratchet against."""
    home = tmp_path / "shallow"
    home.mkdir(parents=True)
    _git(home, "init", "-q")
    _git(home, "config", "user.email", "t@example.com")
    _git(home, "config", "user.name", "t")
    _write(home, list(range(1, _ROWS + 1)))
    _git(home, "add", "-A")
    _git(home, "commit", "-qm", "the only commit there has ever been")
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "below the" in result.detail
    assert str(gate.MIN_REVISIONS) in result.detail


def test_an_EMPTY_ledger_is_CANNOT_MEASURE_not_PASS(repo: Path) -> None:
    """The purest vacuous green: nothing extracted, so nothing can be missing."""
    (repo / gate.LEDGER).write_text("# CHECK-DEBT\n\nnothing here\n", encoding="utf-8")
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "self-control" in result.detail
    assert "extractor" in result.detail


def test_a_BROKEN_ROW_GRAMMAR_is_CANNOT_MEASURE_not_PASS(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 door 4a, driven — THE nastiest way this gate could be green.

    One regex feeds both sides. Break it and the two sides agree about nothing,
    the difference is empty, and a naive gate reports a clean ledger. The
    every-run planted-deletion self-control is what stops that, and this test
    proves the self-control is what is doing the work rather than being decoration.
    """
    import re  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(gate, "_ROW", re.compile(r"^\|\s*(ZZZ\d+)\s*\|", re.MULTILINE))
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.CANNOT_MEASURE, (
        f"a grammar that matches NOTHING produced {result.status} — the gate "
        "compared an empty set against an empty set and called it agreement"
    )
    assert "self-control" in result.detail


def test_a_comparison_that_MANUFACTURES_findings_is_CANNOT_MEASURE(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 door 4b — the plant alone would pass for a constant non-empty answer."""
    monkeypatch.setattr(gate, "missing_ids", lambda historical, working: ["D3.999999"])
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "self-control" in result.detail


def test_the_gate_measures_the_repository_it_was_pointed_at(repo: Path) -> None:
    """§7.12 door 9 — the evidence names the toplevel git actually answered for."""
    result = gate.run(Mode.VERIFY, _ctx(repo))
    assert result.status is Status.PASS, result.detail
    assert str(repo.resolve()) in result.evidence


# ---------------------------------------------------------------------------
# THE SHIPPED TREE, and the contract
# ---------------------------------------------------------------------------


def test_the_shipped_ledger_has_lost_nothing() -> None:
    """The only assertion here that is about the REAL ledger.

    It reddened the first time it ran: `D1.8` and `D1.9` were deleted outright by
    ARC 011 instead of being marked discharged in place, and had been gone for
    twenty-six arcs. Both were recovered from `git show da28f4c:docs/CHECK-DEBT.md`
    in ARC 037 — see their rows, and CHECK-DEBT D3.330.
    """
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"


def test_declarations_are_present_and_honest() -> None:
    """§4.4's declaration set, read the way `verify.py` reads it: statically."""
    declared = read_declaration(GATE_FILE)
    assert declared.errors == ()
    assert declared.depends_on == ()
    assert declared.resources == ("subprocess:git",)
    assert declared.on_fail == "continue"
    assert declared.correctable is False
    assert declared.non_correctable_reason.strip()
    assert declared.subjects == ("docs/CHECK-DEBT.md",)


def test_the_gate_is_in_the_registry() -> None:
    """An orphan check never runs and nothing says so (§3.4)."""
    import json  # pylint: disable=import-outside-toplevel

    registry = json.loads(
        (REPO / "checks" / "registry.json").read_text(encoding="utf-8")
    )
    named = {name for block in registry["blocks"] for name in block["checks"]}
    assert gate.NAME in named


def test_the_standalone_CLI_refuses_to_mutate() -> None:
    """Default is measure-only, and `--correct` is REFUSED with a reason (§2.1)."""
    verify = subprocess.run(
        [sys.executable, str(GATE_FILE), str(REPO)],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert verify.returncode == 0, f"{verify.stdout!r} {verify.stderr!r}"
    correct = subprocess.run(
        [sys.executable, str(GATE_FILE), "--correct", str(REPO)],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert correct.returncode == 1
    assert "REFUSED" in correct.stderr
    assert "evidence ledger" in correct.stderr


def test_no_write_path_exists_in_this_gate() -> None:
    """§7.12 door 1, structurally: a gate that can write can regenerate its evidence."""
    source = GATE_FILE.read_text(encoding="utf-8")
    for banned in ("write_text(", "open(", "shutil.", "os.remove", "unlink("):
        assert banned not in source.replace("read_text(", ""), (
            f"{banned!r} appears in the gate — the comparison set is committed "
            "git objects precisely so the instrument cannot author its own green"
        )
