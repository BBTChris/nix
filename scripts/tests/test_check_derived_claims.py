"""`check_derived_claims` — the reflexivity plant, and the second source that repairs it.

ARC 026 / A1 + A2. Discharges CHECK-DEBT **D2.22** (no such file existed) and
the `check_derived_claims` third of **D2.30** (ARC 025 re-bound the gate and
committed no artifact, so the binding was prose).

--------------------------------------------------------------------------
THE DEFECT THIS FILE MEASURES
--------------------------------------------------------------------------
The gate compares two sources per claim. For **nine of its thirteen claims both
sources are probes inside the gate itself**, re-entered as `{self} --probe`, so
the two sides share the gate's parsing helpers. A defect in a shared helper
moves BOTH numbers together and the comparison reports agreement.

(ARC 025 banked that figure as TEN, and the ARC 026 brief inherited it. Nine is
what `derived_claims.json` says, and that file is byte-identical to its ARC 025
revision — see `test_the_reflexivity_census_is_nine_of_thirteen_not_ten`. The
census was restated three times and derived none, which is the defect this very
gate exists to catch, missed because nobody registered it as a claim.)

Three plants, all measured on a scratch copy of this tree, all with the gate's
own exit code and evidence recorded:

  1. `_DISCHARGED` loosened to `\\bdischarg`. The gate exits **1**, naming
     `check_debt_open_items` (31 vs 68) — AND, in the SAME run,
     `broker_order_open_debt_rows` goes 13 -> **2** and
     `broker_datafeed_open_debt_rows` 13 -> **3**, both in silence.
  2. `_roster_hit` short-circuited to False. The gate exits **0** reporting
     `13/13 claim(s) compared`; `broker_order_open_debt_rows` is 13 -> **4**.
  3. `_finding_pairs` lower-cases the grade. The gate exits **0** reporting
     `13/13 claim(s) compared`; `broker_order_element_coverage_v1` is
     **56% -> 0%**.

The first plant is the one that settles the argument: **one plant, one run, both
outcomes.** Where the two sources do not share the helper the comparison
discriminates and names the site; where they do, a nine-row error in a number
this project reports passes as agreement. The blindness is a property of the
claim's construction, not of how hard the plant tried.

--------------------------------------------------------------------------
THE REPAIR, AND WHAT IT DOES NOT COVER
--------------------------------------------------------------------------
`scripts/tests/independent_claims.py` is a second source for six claims,
implemented by regex where the gate uses `ast`, in a file that imports nothing
from the gate. Every plant above is caught by it, and on the unplanted tree it
agrees with the gate on all six — including `broker_order_open_debt_rows`
compared **as a set of row ids**, not as a count (doctrine C.6).

Seven claims are NOT given a second source, and each is marked rather than
implied — `INDEPENDENCE` below is the table, it is asserted, and the reasons are
per claim. Four of the seven already have a genuinely external second source in
the registry (a different program computes the other number) and need nothing
from this file; three would require re-implementing an AST reader with an AST
reader, which is a transcription wearing a second opinion's coat.
"""

from __future__ import annotations

# R0801: see test_check_python_runtime.py. Each instrument's control stands on
# its own file; one shared helper would let a single edit un-bind several.
# pylint: disable=duplicate-code
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, scratch tree only
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# pylint: disable=wrong-import-position
import independent_claims as second  # pylint: disable=import-error

GATE = "checks/check_derived_claims.py"
REGISTRY = REPO / "checks" / "derived_claims.json"

# ---------------------------------------------------------------------------
# THE INDEPENDENCE TABLE. Asserted below, never merely written down.
#
#   "external"  — the registry itself names a DIFFERENT PROGRAM for one side.
#   "second"    — this suite supplies an independently-implemented source.
#   "none"      — both sides are probes in the gate, and no honest second
#                 implementation was available. NOT INDEPENDENT, and it says so.
# ---------------------------------------------------------------------------
INDEPENDENCE: dict[str, tuple[str, str]] = {
    "registered_check_count": (
        "second",
        (
            "both sides are gate probes, but the two read different artifacts "
            "(registry.json vs the checks/ glob) and share only `_read`"
        ),
    ),
    "pytest_collected_tests": (
        "external",
        (
            "one side shells to real pytest --collect-only; the genuinely "
            "independent pair the gate already had"
        ),
    ),
    "pinned_dependency_count": (
        "external",
        "one side is check_python_deps.py --print-pins, a different program",
    ),
    "check_debt_open_items": ("second", "both sides are gate probes"),
    "spec_2a_broker_order_elements": ("second", "both sides are gate probes"),
    "arc014_broker_order_classification": (
        "none",
        (
            "three sources, two of which call `_arc014_roster_grades` and all "
            "three of which call `_spec_identifiers`. A second implementation "
            "would be an AST reader re-reading an AST reader; the honest answer "
            "is that this claim's sources cannot fail independently"
        ),
    ),
    "seam_declared_elements": (
        "none",
        (
            "both sides call `_module_tuples` on the same file; the spec side "
            "adds `_spec_identifiers` on top, so they can partially diverge, "
            "which is weaker than independent"
        ),
    ),
    "order_path_scope_files": (
        "external",
        "one side is check_order_path_bans.py --print-scope-count",
    ),
    "broker_order_element_coverage_v1": ("second", "both sides are gate probes"),
    "broker_order_open_debt_rows": ("second", "both sides are gate probes"),
    "spec_2a_broker_datafeed_elements": (
        "none",
        "both sides call `_module_tuples`; same shape as seam_declared_elements",
    ),
    "broker_datafeed_open_debt_rows": ("second", "both sides are gate probes"),
    "datafeed_scope_files": (
        "external",
        "BOTH sides are external CLIs of two different gates",
    ),
}


# ---------------------------------------------------------------------------
# DRIVING THE GATE — externally, as a subprocess, exactly as verify.py does.
# ---------------------------------------------------------------------------


def _env() -> dict[str, str]:
    """D3.22: git honours GIT_DIR / GIT_INDEX_FILE ahead of -C, and pre-commit
    exports GIT_INDEX_FILE. The gate spawns subprocesses; strip them so nothing
    it launches reaches a different repository than the tree under measurement."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run_gate(home: Path) -> tuple[int, str]:
    """The gate's standalone CLI against one home. (exit code, combined output)."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False, scratch tree
        [str(REPO / ".venv" / "bin" / "python"), str(home / GATE), str(home)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(home),
        env=_env(),
    )
    return proc.returncode, proc.stdout + proc.stderr


def claim_part(output: str, claim: str) -> str:
    """The gate's own evidence segment for one claim.

    Anchored on a non-identifier boundary rather than on `str.startswith`: the
    FIRST claim shares its segment with the `13/13 claim(s) compared —` header,
    so a startswith scan silently cannot see `registered_check_count` — which is
    the sort of no-match-reads-as-nothing defect §7.12 condition 4 is about.
    """
    match = re.search(
        rf"(?<![\w.]){re.escape(claim)}[=:].*?(?= \| |$)", output, re.DOTALL
    )
    if match is None:
        raise AssertionError(f"{claim} does not appear in the gate's evidence")
    return match.group(0).strip()


def claim_value(output: str, claim: str) -> int | None:
    """The value the gate's two sources AGREED on, or None when they did not."""
    part = claim_part(output, claim)
    match = re.match(rf"{re.escape(claim)}=(\d+) \[", part)
    return int(match.group(1)) if match else None


def claim_ids(probe: str, home: Path) -> list[str]:
    """The ledger row ids one debt-row probe actually selected."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False, scratch tree
        [
            str(REPO / ".venv" / "bin" / "python"),
            str(home / GATE),
            "--probe",
            probe,
            "--nix-home",
            str(home),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(home),
        env=_env(),
    )
    assert proc.returncode == 0, proc.stderr
    match = re.search(r"selected: ([^;]+)", proc.stderr)
    assert match, proc.stderr
    return [rid.strip() for rid in match.group(1).split(",") if rid.strip() != "NONE"]


# ---------------------------------------------------------------------------
# THE SCRATCH TREE. Doctrine C.8: no plant touches a production artifact.
# ---------------------------------------------------------------------------


@pytest.fixture(name="scratch", scope="module")
def _scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A full copy of the tree, with `.venv` symlinked rather than duplicated.

    Copied rather than planted-and-restored in place because three sub-agents
    and a pre-commit hook may be reading `~/nix` while this runs; ARC 018
    established that a concurrent cross-set write corrupts evidence, not just
    state.
    """
    home = tmp_path_factory.mktemp("derived_claims") / "nix"
    shutil.copytree(
        REPO,
        home,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "*.pyc"),
    )
    (home / ".venv").symlink_to(REPO / ".venv")
    return home


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _purge_pycache(home: Path) -> None:
    for cache in home.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


@pytest.fixture(name="plant")
def _plant(scratch: Path) -> Iterator[Callable[[str, str], None]]:
    """Plant one substitution into the gate, then restore it byte-identically.

    Both halves of doctrine C.2 live in this fixture: the caller measures with
    the plant in, and the teardown asserts the control came back with the SAME
    sha256 it went in with. `__pycache__` is purged either side, because a
    stale `.pyc` would let the unplanted tree keep running planted code.
    """
    target = scratch / GATE
    before = target.read_text(encoding="utf-8")
    before_sha = _sha(target)

    def _apply(old: str, new: str) -> None:
        assert old in before, f"plant anchor is not in the gate: {old[:60]!r}"
        _purge_pycache(scratch)
        target.write_text(before.replace(old, new, 1), encoding="utf-8")
        assert _sha(target) != before_sha, "the plant changed nothing"

    yield _apply
    _purge_pycache(scratch)
    target.write_text(before, encoding="utf-8")
    assert _sha(target) == before_sha, "the control was not restored byte-identically"


# ===========================================================================
# NON-VACUITY — asserted before any plant (doctrine C.3).
# ===========================================================================


def test_the_independence_table_covers_every_registered_claim() -> None:
    """The table is compared against the registry, so it cannot silently drift.

    A hand-written table naming twelve claims while the registry holds thirteen
    is failure mode #14, and it would be invisible: the missing claim would
    simply never be discussed.
    """
    registered = [claim["id"] for claim in json.loads(REGISTRY.read_text())["claims"]]
    assert sorted(INDEPENDENCE) == sorted(registered)
    assert len(registered) == 13


def test_the_reflexivity_census_is_nine_of_thirteen_not_ten() -> None:
    """The census, DERIVED from the registry — and it CORRECTS the banked figure.

    ARC 025 banked *"for 10 of its 13 claims BOTH sources are probes inside the
    gate itself"*, and that sentence is now in `sessions/SESSION.md`, in
    CHECK-DEBT's ARC 025 series row, and in the ARC 026 brief. Re-derived from
    `derived_claims.json` — which is **byte-identical to its ARC 025 revision**,
    so nothing has moved under it — the answer is **9**. Twelve claims have at
    least one internal source; nine have two.

    The figure was restated three times and derived none, inside the arc whose
    subject is a gate that exists to stop exactly that (doctrine B.7). It is
    registered here as an assertion rather than corrected in prose, so the next
    restatement reddens something.
    """
    claims = json.loads(REGISTRY.read_text())["claims"]
    internal = [c["id"] for c in claims if all("probe" in s for s in c["sources"])]
    partial = [c["id"] for c in claims if any("probe" in s for s in c["sources"])]
    assert len(internal) == 9, internal
    assert len(partial) == 12, partial
    for claim in internal:
        assert INDEPENDENCE[claim][0] in {"second", "none"}, (
            f"{claim} has both sources inside the gate but the table calls it external"
        )


def test_the_second_source_agrees_with_the_gate_on_the_unplanted_tree() -> None:
    """The positive control. A second source that never agrees proves nothing."""
    exit_code, output = run_gate(REPO)
    assert exit_code == 0, output[:2000]
    for claim, derive in second.SOURCES.items():
        assert INDEPENDENCE[claim][0] == "second", claim
        assert claim_value(output, claim) == derive(REPO), (
            f"{claim}: the gate and the independent source disagree on the "
            f"REAL tree — one of them is wrong and this suite cannot say which"
        )


def test_the_debt_row_selection_agrees_row_by_row_not_merely_in_total() -> None:
    """Doctrine C.6: a refactor once preserved the output SET and changed its ORDER.

    Two counts agreeing while two different rows were selected is the failure
    that measurement caught, so the comparison is over the ids.
    """
    gate_ids = claim_ids("broker_order_debt_rows_spec", REPO)
    mine = second.order_debt_rows(REPO, second.spec_roster(REPO, "broker-order"))
    assert sorted(gate_ids) == sorted(mine), (gate_ids, mine)
    assert gate_ids, "an empty selection would make this comparison vacuous"


# ===========================================================================
# THE PLANTS. Each names the SHARED HELPER it moves and asserts the REASON
# (§18) — a value, a claim id, or a site — never an exit code alone.
# ===========================================================================

_DISCHARGED_ANCHOR = (
    '_DISCHARGED = re.compile(r"\\*\\*[^*]*\\bdischarged ARC \\d+", re.IGNORECASE)'
)
_ROSTER_HIT_ANCHOR = "    for name in roster:\n        for match in re.finditer("
_GRADE_ANCHOR = "            pairs.append((str(verb.value), str(grade.value)))"


def test_a_discharged_regex_defect_discriminates_where_the_sources_differ(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 1, first half: the plant is REAL and the gate can still say no.

    `check_debt_open_items` pairs `_p_check_debt_open_count` (which uses
    `_DISCHARGED`) against `_p_check_debt_series_latest` (which does not), so
    only one side moves and the gate reddens naming the claim.
    """
    plant(_DISCHARGED_ANCHOR, '_DISCHARGED = re.compile(r"\\bdischarg", re.IGNORECASE)')
    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    part = claim_part(output, "check_debt_open_items")
    assert "DISAGREEMENT" in part, part
    assert "derived:ledger_rows=31" in part, part
    assert "stated:series_table_latest_row=68" in part, part


def test_the_same_defect_is_invisible_where_both_sources_share_the_helper(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 1, second half — THE DELIVERABLE.

    The identical plant. `broker_order_open_debt_rows` and
    `broker_datafeed_open_debt_rows` both build their row set with
    `_open_debt_rows`, which is `_DISCHARGED`'s other caller, so BOTH sources of
    both claims move together. The gate reports agreement on a number that lost
    eleven of its thirteen rows, and the independent source is what says so.
    """
    plant(_DISCHARGED_ANCHOR, '_DISCHARGED = re.compile(r"\\bdischarg", re.IGNORECASE)')
    _, output = run_gate(scratch)

    for claim, planted, honest in (
        ("broker_order_open_debt_rows", 2, 13),
        ("broker_datafeed_open_debt_rows", 3, 13),
    ):
        part = claim_part(output, claim)
        assert "DISAGREEMENT" not in part, (
            f"{claim} discriminated — the reflexivity finding has been repaired "
            f"and this control must be re-derived: {part}"
        )
        assert claim_value(output, claim) == planted, part
        assert second.SOURCES[claim](scratch) == honest, (
            "the independent source moved with the plant, so it is not "
            "independent after all"
        )


def test_a_roster_hit_defect_is_invisible_to_both_sources(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 2. `_roster_hit` is called by `_broker_order_scoped`, which IS both
    sources of `broker_order_open_debt_rows` — they differ only in the roster
    passed in. Nine of thirteen rows vanish and the gate exits 0."""
    plant(
        _ROSTER_HIT_ANCHOR,
        "    if roster:\n        return False\n" + _ROSTER_HIT_ANCHOR,
    )
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    assert "13/13 claim(s) compared" in output, output[:200]
    assert claim_value(output, "broker_order_open_debt_rows") == 4
    assert second.broker_order_open_debt_rows(scratch) == 13, (
        "the independent source did not hold its ground under the plant"
    )


def test_a_grade_defect_silently_zeroes_the_headline_coverage_number(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 3, and it is the most expensive one to have missed.

    `broker_order_element_coverage_v1` is the number this project reports as
    broker-order element coverage. Both its sources take their grades from
    `_arc014_findings`/`_finding_pairs`. Lower-casing the grade makes nothing
    match `"CLEAN"`, the level collapses **56% -> 0%**, and the gate reports
    `pass: 13/13 claim(s) compared`.
    """
    plant(
        _GRADE_ANCHOR,
        "            pairs.append((str(verb.value), str(grade.value).lower()))",
    )
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    part = claim_part(output, "broker_order_element_coverage_v1")
    assert "DISAGREEMENT" not in part, part
    assert claim_value(output, "broker_order_element_coverage_v1") == 0, part
    assert second.broker_order_element_coverage_v1(scratch) == 56, (
        "the independent source read the grades through the same defect"
    )


def test_the_control_is_green_again_once_every_plant_is_gone(scratch: Path) -> None:
    """Doctrine C.2's other half, on the tree every plant above ran against.

    Ordered last by name so it observes the fixture teardowns. If a plant ever
    survived its test, this is where it surfaces.
    """
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    assert "13/13 claim(s) compared" in output
    assert "2/2 demonstration(s) re-executed" in output
