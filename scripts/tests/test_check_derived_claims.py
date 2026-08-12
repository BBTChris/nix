"""`check_derived_claims` — the reflexivity plant, and the second source that repairs it.

ARC 026 / A1 + A2. Discharges CHECK-DEBT **D2.22** (no such file existed) and
the `check_derived_claims` third of **D2.30** (ARC 025 re-bound the gate and
committed no artifact, so the binding was prose).

**RE-DERIVED AT STAGE 2 AGAINST SUB-AGENT B's REWRITE.** B3 replaced the debt
metric's prose-based row selection with an AUTHORED `owning module` column and
rewrote the gate (-519/+355). Three of this file's plants targeted helpers that
no longer exist. Every plant below was re-measured against B's implementation
rather than re-pointed until it passed, and **one of the answers changed** — see
"WHAT B's COLUMN CLOSED".

--------------------------------------------------------------------------
THE DEFECT THIS FILE MEASURES
--------------------------------------------------------------------------
The gate compares two sources per claim. For **nine of its thirteen claims both
sources are probes inside the gate itself**, re-entered as `{self} --probe`, so
the two sides share the gate's parsing helpers. A defect in a shared helper
moves BOTH numbers together and the comparison reports agreement.

(ARC 025 banked that figure as TEN, and the ARC 026 brief inherited it. Nine is
what `derived_claims.json` says — see
`test_the_reflexivity_census_is_nine_of_thirteen_not_ten`. B3 changed which
claims are reflexive without changing the count: the two debt claims left the
set and nothing joined it.)

--------------------------------------------------------------------------
WHAT B's COLUMN CLOSED — and it is a real structural gain, stated plainly
--------------------------------------------------------------------------
Before B3, `_DISCHARGED` loosened to `\bdischarg` reddened
`check_debt_open_items` (31 vs 68) while `broker_order_open_debt_rows` went
13 -> **2** and `broker_datafeed_open_debt_rows` 13 -> **3** IN SILENCE, because
both sources of both claims built their row set through `_open_debt_rows`.

After B3 the same plant reddens **all three**: the derived side scans the
column, the stated side reads an authored per-module tally that never touches
`_DISCHARGED`, so `broker_order_open_debt_rows` reports
`derived:ledger_column=1` against `stated:stated_module_tally=9`.
**B's structural repair closed this part of the reflexivity hole**, and
`test_the_authored_column_closed_the_hole_this_plant_used_to_walk_through`
pins it so a revert reddens rather than quietly restoring the blindness.

--------------------------------------------------------------------------
WHAT IS STILL SILENT — measured on B's tree, not inherited
--------------------------------------------------------------------------
  1. `_finding_pairs` lower-cases the grade -> exit **0**, `13/13 claim(s)
     compared`, `broker_order_element_coverage_v1` **56% -> 0%**.
  2. `_clean_fraction` off by one -> exit **0**, `13/13 compared`, the same
     claim **56% -> 50%**. A second, subtler shape of the same blindness, and
     the replacement for the retired `_roster_hit` plant.
  3. `_spec_identifiers` truncated -> exit **0**, `13/13 compared`,
     `arc014_broker_order_classification` **16 -> 15** with ALL THREE of its
     sources moving together. Three sources are not three opinions.
  4. `_module_tuples` truncated -> exit **0**, `13/13 compared`,
     `spec_2a_broker_datafeed_elements` **11 -> 9**.

RETIRED, NOT DELETED SILENTLY: the `_roster_hit` plant (13 -> 4, invisible).
`_roster_hit`, `_broker_order_scoped` and `_order_path_basenames` were deleted
by B3 along with the prose rule they implemented. The property it demonstrated
— *a helper shared by both sources of one claim moves both numbers together* —
is carried by plants 1-4 above, and the specific claim it demonstrated on is now
covered by the column's own second source. See
`test_the_retired_roster_hit_plant_has_no_helper_left_to_target`, which asserts
the helpers are actually gone rather than taking this paragraph's word for it.

--------------------------------------------------------------------------
THE REPAIR, AND WHAT IT DOES NOT COVER
--------------------------------------------------------------------------
`scripts/tests/independent_claims.py` is a second source for **eight** claims,
implemented by regex where the gate uses `ast`, in a file that imports nothing
from the gate. Every plant above is caught by it, and on the unplanted tree it
agrees with the gate on all eight — including `broker_order_open_debt_rows`
compared **as a set of row ids**, not as a count (doctrine C.6).

Five claims are NOT given a second source, and each is marked rather than
implied — `INDEPENDENCE` below is the table, it is asserted against the
registry, and the reasons are per claim.
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
        "second",
        (
            "THREE sources and none of them is an opinion: all three call "
            "`_spec_identifiers`, and truncating it moves 16 -> 15 -> 15 -> 15 "
            "with the gate reporting agreement. Given a second source ARC 026 "
            "after that was measured"
        ),
    ),
    "seam_declared_elements": (
        "none",
        (
            "both sides call `_module_tuples` on the same file; the spec side "
            "adds `_spec_identifiers` on top, so they diverge under some plants "
            "and not others, which is weaker than independent"
        ),
    ),
    "order_path_scope_files": (
        "external",
        "one side is check_order_path_bans.py --print-scope-count",
    ),
    "broker_order_element_coverage_v1": (
        "second",
        (
            "both sides are gate probes sharing `_arc014_findings` and "
            "`_clean_fraction`; silent under two separate plants"
        ),
    ),
    "broker_order_open_debt_rows": (
        "second",
        (
            "ARC 026 / B3: derived row scan over the AUTHORED column vs the "
            "ledger's stated per-module tally. The two no longer share a helper "
            "below `_read`, so this pair is now genuinely independent — measured, "
            "not assumed. The second source is kept as a third opinion and as the "
            "row-by-row comparison the counts cannot make"
        ),
    ),
    "spec_2a_broker_datafeed_elements": (
        "second",
        (
            "both sides call `_module_tuples`; truncating it moves 11 -> 9 on "
            "both sides in silence. Given a second source ARC 026"
        ),
    ),
    "broker_datafeed_open_debt_rows": (
        "second",
        "ARC 026 / B3: same column-vs-tally pair as its order counterpart",
    ),
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

    RE-TARGETED at B3's column probe. Two counts agreeing while two different
    rows were selected is a failure a count cannot see, and the authored column
    makes that MORE likely rather than less: a mis-typed token moves a row from
    one module to another and both tallies can still be right in total.
    """
    gate_ids = claim_ids("broker_order_debt_rows_ledger", REPO)
    mine = second.rows_by_module(REPO)["broker-order"]
    assert sorted(gate_ids) == sorted(mine), (gate_ids, mine)
    assert gate_ids, "an empty selection would make this comparison vacuous"


def test_every_open_row_carries_a_valid_owning_module_token() -> None:
    """B3's fail-closed promise, re-measured by a reader that is not B3's.

    The column's whole claim is that an unattributed row is a LOUD error rather
    than a silent exclusion. This asserts it from outside the gate: the
    independent grouper raises on a stray row, so reaching a full grouping at
    all is the measurement.
    """
    grouped = second.rows_by_module(REPO)
    attributed = sum(len(ids) for ids in grouped.values())
    assert attributed == second.check_debt_open_items(REPO), (
        "some open row escaped the column without either reader complaining"
    )
    assert set(second.stated_tally(REPO)) <= set(grouped)


# ===========================================================================
# THE PLANTS. Each names the SHARED HELPER it moves and asserts the REASON
# (§18) — a value, a claim id, or a site — never an exit code alone.
# ===========================================================================

_DISCHARGED_ANCHOR = (
    '_DISCHARGED = re.compile(r"\\*\\*[^*]*\\bdischarged ARC \\d+", re.IGNORECASE)'
)
_DISCHARGED_PLANT = '_DISCHARGED = re.compile(r"\\bdischarg", re.IGNORECASE)'
_GRADE_ANCHOR = "            pairs.append((str(verb.value), str(grade.value)))"
_CLEAN_ANCHOR = (
    '    clean = sum(1 for name in roster if grades.get(name) == "CLEAN")\n'
    "    return clean, len(roster), 100 * clean // len(roster)"
)
_SPEC_ANCHOR = (
    "    if not names:\n"
    '        raise ProbeError(f"no §2A identifiers found under {heading!r}")\n'
    "    return names"
)
_TUPLES_ANCHOR = "    missing = [w for w in wanted if w not in out]"

#: The helpers B3 deleted. Named here so the retirement of the `_roster_hit`
#: plant is an assertion rather than a claim in a docstring.
_DELETED_BY_B3 = ("_roster_hit", "_broker_order_scoped", "_order_path_basenames")


def test_the_retired_roster_hit_plant_has_no_helper_left_to_target(
    scratch: Path,
) -> None:
    """The plant was RETIRED because its subject was deleted, not because it failed.

    ARC 026 / A1 planted `_roster_hit` short-circuited to False and measured
    `broker_order_open_debt_rows` 13 -> 4 with the gate exiting 0. B3 then
    replaced the prose selection rule wholesale. Deleting a control silently
    because the code moved is how a suite stops meaning anything, so the
    retirement is asserted: these three helpers must actually be absent.
    """
    source = (scratch / GATE).read_text(encoding="utf-8")
    present = [name for name in _DELETED_BY_B3 if f"def {name}(" in source]
    assert not present, (
        f"{present} still exist — the `_roster_hit` plant was retired on the "
        "grounds that B3 deleted them, and that reason is no longer true"
    )


def test_a_discharged_regex_defect_discriminates_where_the_sources_differ(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 1, first half: the plant is REAL and the gate can still say no.

    `check_debt_open_items` pairs `_p_check_debt_open_count` (which uses
    `_DISCHARGED`) against `_p_check_debt_series_latest` (which does not), so
    only one side moves and the gate reddens naming the claim.

    ARC 026 Stage 2 — THE EXPECTATION IS DERIVED, NOT RESTATED. This control
    first asserted `derived:ledger_rows=31` and `stated:...=69` as literals.
    Both are functions of how many rows the ledger happens to hold, so the
    control broke the moment sub-agent C's seven rows merged (36 and 76) —
    inside the arc whose own brief warns about moving anchors, in the suite
    for the gate that exists to stop numbers being restated. Updating the
    literals to 36 and 76 would re-arm the identical trap for the next arc that
    opens a row. The PROPERTY is directional, so it is asserted directionally:
    the plant widens `_DISCHARGED`, so strictly MORE rows read as discharged
    and strictly FEWER as open, on the derived side only.
    """

    def _number(pattern: str, text: str) -> int:
        """The one integer `pattern` names, or a loud failure naming the text.

        A regex that does not match must not silently become 0 — a control that
        compares two zeros passes while measuring nothing.
        """
        found = re.search(pattern, text)
        assert found is not None, f"{pattern!r} did not match: {text[:2000]}"
        return int(found.group(1))

    clean_exit, clean_output = run_gate(scratch)
    assert clean_exit == 0, clean_output[:2000]
    open_rows = _number(r"check_debt_open_items=(\d+)", clean_output)
    # Non-vacuity: a ledger with no open rows could not show a decrease.
    assert open_rows > 0, clean_output[:2000]

    plant(_DISCHARGED_ANCHOR, _DISCHARGED_PLANT)
    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    part = claim_part(output, "check_debt_open_items")
    assert "DISAGREEMENT" in part, part

    derived = _number(r"derived:ledger_rows=(\d+)", part)
    stated = _number(r"stated:series_table_latest_row=(\d+)", part)
    # The side that does NOT use `_DISCHARGED` must not have moved...
    assert stated == open_rows, f"{stated} != unplanted {open_rows}: {part}"
    # ...and the side that does must have fallen. Equality would mean the plant
    # was inert, which is the failure mode a literal comparison hides.
    assert derived < stated, f"the plant moved nothing: {part}"


def test_the_authored_column_closed_the_hole_this_plant_used_to_walk_through(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 1, second half — AND THE ANSWER CHANGED AT STAGE 2.

    BEFORE B3 this identical plant was INVISIBLE on both debt claims:
    `broker_order_open_debt_rows` 13 -> 2 and its datafeed counterpart 13 -> 3,
    gate exit 1 but naming only `check_debt_open_items`. Both sources of both
    claims built their row set through `_open_debt_rows`, so both moved together.

    AFTER B3 the derived side scans the authored column and the STATED side
    reads a hand-written per-module tally that never touches `_DISCHARGED`. The
    same plant now reddens both claims and names both numbers. B's structural
    repair closed this part of the reflexivity hole, and this test is the pin:
    if the column is ever reverted to a prose scan on both sides, this reddens
    instead of the blindness quietly coming back.
    """
    plant(_DISCHARGED_ANCHOR, _DISCHARGED_PLANT)
    _, output = run_gate(scratch)

    for claim, stated in (
        ("broker_order_open_debt_rows", 9),
        ("broker_datafeed_open_debt_rows", 7),
    ):
        part = claim_part(output, claim)
        assert "DISAGREEMENT" in part, (
            f"{claim} stayed silent under the `_DISCHARGED` plant — B3's "
            f"column-versus-tally independence has regressed: {part}"
        )
        assert "derived:ledger_column=1" in part, part
        assert f"stated:stated_module_tally={stated}" in part, part
        assert second.SOURCES[claim](scratch) == stated, (
            "the independent source moved with the plant, so it is not "
            "independent after all"
        )


def test_a_grade_defect_silently_zeroes_the_headline_coverage_number(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 2, and it is the most expensive one to have missed.

    `broker_order_element_coverage_v1` is the number this project reports as
    broker-order element coverage. Both its sources take their grades from
    `_arc014_findings`/`_finding_pairs`. Lower-casing the grade makes nothing
    match `"CLEAN"`, the level collapses **56% -> 0%**, and the gate reports
    `pass: 13/13 claim(s) compared`. Unchanged by B3.
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


def test_an_arithmetic_defect_in_the_shared_percent_is_invisible(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 3 — the replacement for the retired `_roster_hit` plant.

    `_clean_fraction` computes the percent for BOTH sources of the coverage
    claim; only the roster and grade map differ. One off-by-one moves the
    reported level **56% -> 50%** with the gate exiting 0 on `13/13 compared`.

    Deliberately subtler than plant 2: a collapse to zero would be noticed by a
    human reading the evidence line, and a six-point drift would not.
    """
    plant(
        _CLEAN_ANCHOR,
        '    clean = sum(1 for name in roster if grades.get(name) == "CLEAN")\n'
        "    clean = max(clean - 1, 0)\n"
        "    return clean, len(roster), 100 * clean // len(roster)",
    )
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    assert "13/13 claim(s) compared" in output
    assert claim_value(output, "broker_order_element_coverage_v1") == 50
    assert second.broker_order_element_coverage_v1(scratch) == 56


def test_three_sources_are_not_three_opinions(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 4. `arc014_broker_order_classification` carries THREE sources.

    All three call `_spec_identifiers`. Truncating the §2A roster by one moves
    16 -> 15 on every one of them and the gate reports agreement — while the
    SAME plant reddens four other claims, which is what proves the plant real.
    A claim's source count is not its independence.
    """
    plant(_SPEC_ANCHOR, _SPEC_ANCHOR + "[:-1]")
    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    assert "DISAGREEMENT" in claim_part(output, "spec_2a_broker_order_elements")

    part = claim_part(output, "arc014_broker_order_classification")
    assert "DISAGREEMENT" not in part, part
    assert claim_value(output, "arc014_broker_order_classification") == 15, part
    assert second.arc014_broker_order_classification(scratch) == 16


def test_a_module_tuple_defect_is_invisible_to_the_datafeed_element_claim(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """PLANT 5. Both sources of `spec_2a_broker_datafeed_elements` read the seam
    through `_module_tuples`; dropping one element from each declared tuple moves
    11 -> 9 on both sides in silence, while reddening three other claims."""
    plant(
        _TUPLES_ANCHOR,
        "    out = {k: (v[:-1] if v else v) for k, v in out.items()}\n"
        + _TUPLES_ANCHOR,
    )
    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    assert "DISAGREEMENT" in claim_part(output, "seam_declared_elements")

    part = claim_part(output, "spec_2a_broker_datafeed_elements")
    assert "DISAGREEMENT" not in part, part
    assert claim_value(output, "spec_2a_broker_datafeed_elements") == 9, part
    assert second.spec_2a_broker_datafeed_elements(scratch) == 11


# ===========================================================================
# ARC 028 (C1) — THE SHIPPED-BYTES BINDING. CHECK-DEBT D3.41.
#
# Every plant above substitutes into `checks/check_derived_claims.py` ITSELF.
# `scripts/tests/binding_census.py` sha256s the module that produced each
# verdict and compares it against the shipped file, so all four reds this suite
# produced were attributed to a **modified gate** — a program this repository
# does not install — and the §2.4 binding table carried
# `check_derived_claims  BOUND-BY-MODIFIED-GATE  PASS:10 (modified: FAIL:4)`.
# That is the whole of the row: the gate's own reflexivity was measured and its
# CAN-FAIL was not.
#
# THE BRIEF'S PREMISE WAS THAT SUCH A CONTROL MIGHT NOT BE CONSTRUCTIBLE. IT IS,
# AND THE REASON IS ONE LINE OF THE GATE: `run()` resolves the registry as
# `Path(__file__).resolve().parent / REGISTRY`, and every source and probe is
# resolved against `ctx.nix_home`. So a copy of the tree with the gate left
# BYTE-IDENTICAL is the shipped program measuring a perturbed subject, which is
# exactly what §0e asks for and what the plants above could never be.
#
# Three perturbations, none of them touching the gate:
#
#   * `checks/derived_claims.json` — THE DECLARED SUBJECT. §7.12 condition 5.
#   * `checks/registry.json`       — a real artifact two sources read
#                                    independently; the defect is a registered
#                                    check with no file on disk.
#   * `docs/CHECK-DEBT.md`         — a document RESTATING a number the ledger
#                                    also derives. The gate's whole purpose.
#
# Each asserts the REASON (§18): the claim id, the site, and the two values —
# never the exit code alone. Each restores the file byte-identically, and
# `test_the_control_is_green_again_once_every_plant_is_gone` runs after all of
# them over the same tree.
# ===========================================================================


@pytest.fixture(name="subject_plant")
def _subject_plant(scratch: Path) -> Iterator[Callable[[str, str, str], None]]:
    """Perturb a SUBJECT in the scratch tree; leave the gate byte-identical.

    The gate's own sha256 is captured before and after and asserted UNCHANGED —
    that assertion is what makes the resulting red a shipped-bytes binding
    rather than a fifth modified-gate red, and it is checked here rather than
    left to the census to notice.
    """
    gate_sha = _sha(scratch / GATE)
    touched: list[tuple[Path, str]] = []

    def _apply(rel: str, old: str, new: str) -> None:
        target = scratch / rel
        before = target.read_text(encoding="utf-8")
        assert old in before, f"plant anchor is not in {rel}: {old[:60]!r}"
        touched.append((target, before))
        _purge_pycache(scratch)
        target.write_text(before.replace(old, new, 1), encoding="utf-8")
        assert _sha(scratch / GATE) == gate_sha, (
            "the subject plant moved the GATE — this would be a modified-gate red"
        )

    yield _apply
    _purge_pycache(scratch)
    for target, before in reversed(touched):
        target.write_text(before, encoding="utf-8")
    assert _sha(scratch / GATE) == gate_sha


def test_the_shipped_gate_reddens_when_its_DECLARED_SUBJECT_names_a_missing_file(  # pylint: disable=invalid-name
    scratch: Path, subject_plant: Callable[[str, str, str], None]
) -> None:
    """SHIPPED-BYTES PLANT 1 — `checks/derived_claims.json`, the declared SUBJECT.

    §7.12 condition 5: *a registry entry points at a file that no longer exists
    and the entry is skipped*. The gate's answer is that a missing file is a
    FAIL, explicitly — a stale registry is a defect IN the instrument and the
    instrument must say so. Nothing above ever drove that branch with the
    shipped program.

    The perturbation is a one-token edit to the registry's own `files` list, so
    the claim still has two sources and still runs; what changes is that one of
    them names a path this tree does not hold.
    """
    subject_plant(
        "checks/derived_claims.json",
        '"checks/registry.json"',
        '"checks/registry-DELETED-BY-ARC-028.json"',
    )
    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    assert "derived_claims.json:registered_check_count/registry_json" in output, output[
        :2000
    ]
    assert "missing file(s): checks/registry-DELETED-BY-ARC-028.json" in output, output[
        :2000
    ]


def test_the_shipped_gate_reddens_when_two_sources_of_a_claim_DISAGREE(  # pylint: disable=invalid-name
    scratch: Path, subject_plant: Callable[[str, str, str], None]
) -> None:
    """SHIPPED-BYTES PLANT 2 — `checks/registry.json`, the master execution plan.

    The perturbation is a REAL operational defect rather than a synthetic one: a
    check name registered in the execution plan with no `checks/check_*.py` on
    disk. `verify.py` would try to run a program that is not there.

    `registered_check_count` is the one claim whose two sources are structurally
    independent inside the gate — one parses `registry.json`, the other globs
    the folder — so this is the disagreement arm driven end to end by the
    shipped bytes, naming the claim, the site and BOTH values.
    """
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    before = claim_value(output, "registered_check_count")
    assert isinstance(before, int) and before > 0

    subject_plant(
        "checks/registry.json",
        '"check_artifact_gate_coverage",',
        '"check_artifact_gate_coverage",\n        "check_planted_by_arc_028_c",',
    )
    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    part = claim_part(output, "registered_check_count")
    assert "DISAGREEMENT" in part, part
    assert f"derived:registry_json={before + 1}" in part, part
    assert f"derived:checks_glob={before}" in part, part
    assert "derived_claims.json:registered_check_count: sources disagree" in output


def test_the_shipped_gate_reddens_when_a_DOCUMENT_RESTATES_A_WRONG_NUMBER(  # pylint: disable=invalid-name
    scratch: Path, subject_plant: Callable[[str, str, str], None]
) -> None:
    """SHIPPED-BYTES PLANT 3 — the derive-never-restate class, on a real document.

    `check_debt_open_items` compares the ledger's OPEN rows, derived row by row,
    against the number the ledger's own series table RESTATES in its newest row.
    That is doctrine B.7's exact defect shape, and it is the reason this gate
    exists. The plant moves the restated figure and leaves the rows alone.

    The stated side is what moves, and the assertion says so: a plant that moved
    both sides together would be reproducing the reflexivity defect the first
    half of this file measures, and would prove nothing about the gate.
    """
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    derived = claim_value(output, "check_debt_open_items")
    assert isinstance(derived, int) and derived > 0

    row = re.search(
        rf"^\|\s*\d{{4}}-\d{{2}}-\d{{2}}\s*\|\s*ARC \d+\s*\|\s*{derived}\s*\|",
        (scratch / "docs" / "CHECK-DEBT.md").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert row is not None, "no series row states the derived open count"
    subject_plant(
        "docs/CHECK-DEBT.md",
        row.group(0),
        row.group(0).replace(f"| {derived} |", "| 4242 |"),
    )

    exit_code, output = run_gate(scratch)
    assert exit_code == 1, output[:2000]
    part = claim_part(output, "check_debt_open_items")
    assert "DISAGREEMENT" in part, part
    assert f"derived:ledger_rows={derived}" in part, part
    assert "stated:series_table_latest_row=4242" in part, part


def test_the_control_is_green_again_once_every_plant_is_gone(scratch: Path) -> None:
    """Doctrine C.2's other half, on the tree every plant above ran against.

    Ordered last by name so it observes the fixture teardowns. If a plant ever
    survived its test, this is where it surfaces.
    """
    exit_code, output = run_gate(scratch)
    assert exit_code == 0, output[:2000]
    assert "13/13 claim(s) compared" in output
    assert "2/2 demonstration(s) re-executed" in output
