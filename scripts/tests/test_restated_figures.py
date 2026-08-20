"""Tests for `scripts/tests/restated_figures.py` (ARC 027 / D2).

The load-bearing assertions are the two that prove the answer sheet can say
BOTH things: `9 of 13` must come back AGREES and `512 test functions` must come
back DISAGREES. A table in which nothing can disagree is not an answer sheet,
it is a list of numbers with a green tick painted on.

Every assertion keys on the REASON — the verdict token, the derived value, the
refusal text — never on a bare exit code.
"""
# pylint: disable=invalid-name,use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test, as in every other suite here;
# `== []` is asserted rather than `not x` because pytest prints the offending
# defects on failure and a bare truthiness check prints only `False` — the
# same trade `test_status_contract.py` documents.

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

sys.path.insert(0, str(Path(__file__).resolve().parent))

# pylint: disable=wrong-import-position
# The `sys.path` bootstrap above must run BEFORE this import.
import restated_figures as rf  # pylint: disable=import-error

# pylint: enable=wrong-import-position

# ---------------------------------------------------------------------------
# THE ANSWER SHEET — it must be able to disagree.
# ---------------------------------------------------------------------------


def test_every_adjudicated_figure_has_a_derivation_or_a_debt_row() -> None:
    """The rule the whole module enforces, enforced on the module's own table."""
    for row in rf.ADJUDICATED:
        assert row.derivation is not None or row.debt, row.figure


def test_a_figure_with_neither_a_derivation_nor_a_debt_row_is_refused() -> None:
    """The table cannot quietly acquire an unadjudicated row."""
    with pytest.raises(rf.RefusedError) as excinfo:
        rf.Adjudication(figure="99 widgets", what="nothing", stated=99)
    assert "neither a derivation nor a debt row" in str(excinfo.value)


def test_the_arc026_census_now_derives_and_agrees() -> None:
    """`9 of 13` — the correction that had itself never been derived."""
    derived = rf.reflexive_claims(rf.REPO)
    assert derived == 9, (
        f"the reflexivity census re-derives as {derived}, not the 9 that ARC 026 "
        "corrected the restated 10 to"
    )
    assert rf.registered_claims(rf.REPO) == 13


def test_the_census_derivation_does_not_import_the_gate_it_measures() -> None:
    """Reflexivity is the property under test; a reflexive derivation is no use.

    `check_derived_claims` is the subject. If this derivation went through the
    gate's own probes it would inherit exactly the defect the figure asserts
    about, which is how "10 of 13" survived three documents.
    """
    import ast  # pylint: disable=import-outside-toplevel

    tree = ast.parse(Path(rf.__file__).read_text(encoding="utf-8"))
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "reflexive_claims"
    )
    # AST, not a text scan: the function's own docstring says "never imports the
    # gate", and a text scan matched that sentence instead of the code.
    body = [node for node in fn.body if not isinstance(node, ast.Expr)]
    dumped = "\n".join(ast.dump(node) for node in body)
    assert "Import" not in dumped, dumped
    assert "check_derived_claims" not in dumped, dumped
    assert "derived_claims.json" in dumped


def test_the_arc024_path_count_derives_from_git_history() -> None:
    """`30 paths` / `5,019 insertions` — restated by four surfaces, derived by none."""
    assert rf.arc024_paths(rf.REPO) == 30
    assert rf.arc024_insertions(rf.REPO) == 5019


def test_the_arc025_test_function_audit_disagrees_and_is_owned_by_a_debt_row() -> None:
    """`512 test functions` — the moving anchor, and the proof the sheet can bite."""
    verifications = {v.figure: v for v in rf.verify_all(rf.REPO)}
    check = verifications["512 test functions"]
    assert check.verdict == "DISAGREES", check
    assert check.derived is not None and check.derived > 512, check
    owner = next(r for r in rf.ADJUDICATED if r.figure == "512 test functions")
    assert owner.debt == "D2.39"


def test_the_seven_versus_eight_hook_disagreement_is_a_noun_not_an_error() -> None:
    """Both figures are true of different denominators, and both are derived."""
    assert rf.precommit_hook_invocations(rf.REPO) == 8
    assert rf.precommit_hook_ids(rf.REPO) == 7
    assert rf.precommit_hook_invocations(rf.REPO) != rf.precommit_hook_ids(rf.REPO)


def test_verify_all_refuses_a_table_with_nothing_to_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§7.12 #4. A verifier that verifies nothing passes by measuring nothing."""
    monkeypatch.setattr(
        rf,
        "ADJUDICATED",
        (rf.Adjudication(figure="x", what="x", stated=1, debt="D2.41"),),
    )
    with pytest.raises(rf.RefusedError) as excinfo:
        rf.verify_all(rf.REPO)
    assert "nothing to verify" in str(excinfo.value)


# ---------------------------------------------------------------------------
# THE ENUMERATOR — it must start from the documents.
# ---------------------------------------------------------------------------


def test_the_sweep_finds_the_known_restated_figures() -> None:
    """Non-vacuity, on the actual tree: the figures ARC 026 named must be there."""
    groups = rf.cross_document(rf.figures(rf.REPO))
    assert len(groups) >= rf.MIN_CREDIBLE_FIGURES, len(groups)
    keys = set(groups)
    assert ("8/8", "ratio") in keys
    assert ("13/13", "ratio") in keys
    assert ("30", "path") in keys
    assert ("512", "test") in keys


def test_a_missing_scope_entry_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 #2. A scope that silently shrinks reports clean over what it dropped."""
    monkeypatch.setattr(rf, "SCOPE", ("docs/NOT-A-FILE.md",))
    with pytest.raises(rf.RefusedError) as excinfo:
        rf.scope_paths(tmp_path)
    message = str(excinfo.value)
    assert "NOT-A-FILE.md" in message and "silently shrinks" in message


def test_the_extractor_refuses_a_below_floor_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 #1. Finding almost nothing is an extractor that stopped matching."""
    (tmp_path / "CLAUDE.md").write_text("nothing numeric here\n", encoding="utf-8")
    monkeypatch.setattr(rf, "SCOPE", ("CLAUDE.md",))
    assert rf.main(["--home", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    "line",
    [
        "a retrofitted check loses its D3.10 binding at the moment",  # debt-row id
        "the brief writes §13 objective N for 1-23",  # section reference
        "bumped to v1.3.0 with 3 amendments",  # semantic version
        "ARC 010/011 gateway work",  # zero-padded arc numbers
        "see sessions/SESSION.md:1514 rows",  # a line reference
    ],
)
def test_tokens_that_only_look_like_figures_are_excluded(line: str) -> None:
    """The noise table, exercised directly — it is where over-matching would hide."""
    found = list(
        rf._line_figures(  # pylint: disable=protected-access
            Path("/x"), Path("/x/CLAUDE.md"), 1, line, False
        )
    )
    assert not found, [f"{o.figure} {o.noun}" for o in found]


def test_a_real_figure_on_a_line_that_also_mentions_an_arc_survives() -> None:
    """The noise window is TIGHT so a mention elsewhere cannot suppress a figure.

    A wide window would let `ARC 025` anywhere on a 400-character ledger row
    silence every count on that row — a gate narrowing its own scope, which is
    the exact defect class this project keeps meeting.
    """
    line = "opened ARC 025 (C), open. The gate now compares 13 claims against ..."
    found = list(
        rf._line_figures(  # pylint: disable=protected-access
            Path("/x"), Path("/x/docs/CHECK-DEBT.md"), 1, line, False
        )
    )
    assert [(o.figure, o.noun) for o in found] == [("13", "claim")], found


# ---------------------------------------------------------------------------
# HISTORY versus CONTROL SURFACE — the line, asserted.
# ---------------------------------------------------------------------------


def test_a_dated_measurement_is_history_even_inside_a_live_document() -> None:
    """Directive 6: a record of what was measured then stays true forever."""
    assert rf.classify_occurrence(
        "Audited, ARC 025, by AST over the whole suite - 512 test functions", False
    )
    assert rf.classify_occurrence("MEASURED 2026-08-12: the unit is present", False)


def test_an_undated_figure_in_a_live_document_is_a_control_surface() -> None:
    """A figure a reader would act on today is not history."""
    assert not rf.classify_occurrence(
        "the gate compares 13 claims and 2 demonstrations", False
    )


def test_every_arc_brief_is_history_throughout() -> None:
    """`downloads/arc_0*.md` are banked records; nothing in them is a defect."""
    briefs = sorted(rf.REPO.glob("downloads/arc_0*.md"))
    assert len(briefs) >= 10, briefs
    for brief in briefs:
        assert rf._is_historical(rf.REPO, brief), brief  # pylint: disable=W0212
    assert not rf._is_historical(  # pylint: disable=protected-access
        rf.REPO, rf.REPO / "docs" / "CHECK-DEBT.md"
    )


# ---------------------------------------------------------------------------
# ARC 029 / 0.2 — D3.82's own blind spot, in both halves.
#
# D3.82 recorded that this auditor's extractor is measurably blind to counts
# spelled in words, and the class then recurred TWICE MORE inside the documents
# reporting the finding. The two arms below are what closes it: worded numerals,
# and a stated total reconciled against an enumeration in the SAME passage.
#
# The second arm reaches a class `cross_document` cannot see by construction —
# that group needs a figure restated in ANOTHER FILE, and a row that contradicts
# ITSELF never leaves the line it is written on.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "figure"),
    [
        ("thirty-seven rows opened", "37"),
        ("forty-one findings", "41"),
        ("twenty-nine claims", "29"),
        ("nine checks", "9"),
        ("ninety-nine tests", "99"),
    ],
)
def test_worded_counts_are_extracted_and_NORMALISED_TO_DIGITS(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, figure: str
) -> None:
    """A worded figure must arrive as its VALUE, not as its spelling.

    Normalisation is the whole point: it is what lets `thirty-seven opened` in
    one document and `37 rows` in another land in a single `cross_document`
    group instead of passing each other unseen.
    """
    (tmp_path / "CLAUDE.md").write_text(text + "\n", encoding="utf-8")
    monkeypatch.setattr(rf, "SCOPE", ("CLAUDE.md",))
    assert figure in {occurrence.figure for occurrence in rf.figures(tmp_path)}


@pytest.mark.parametrize(
    "text", ["Thirty opened", "the thirty-six new rows", "thirty-six of them"]
)
def test_the_NOUN_ADJACENCY_RULE_is_pinned_for_worded_counts_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    """The worded arm obeys `_COUNT`'s rule exactly: number, then a closed noun.

    So `Thirty opened` (a verb), `thirty-six new rows` (an adjective in the way)
    and `thirty-six of them` (no noun at all) are NOT figures to this extractor,
    and that boundary is asserted rather than left to be discovered.

    **It is also why the second arm exists.** Every one of these shapes appears
    in the measured defect, and the intra-sentence reconciliation reads them
    through `_STATED_OPENED` / `_STATED_OF_THE` — which key on the words that say
    what is being counted, not on a noun table. The two arms are complementary,
    and neither alone would have found the ARC 028 row.
    """
    (tmp_path / "CLAUDE.md").write_text(text + "\n", encoding="utf-8")
    monkeypatch.setattr(rf, "SCOPE", ("CLAUDE.md",))
    assert [o for o in rf.figures(tmp_path) if o.figure in {"30", "36"}] == []


def test_a_WORDED_and_a_DIGIT_restatement_land_in_ONE_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured defect, as a test: one figure, two spellings, two files."""
    (tmp_path / "CLAUDE.md").write_text("thirty-seven rows\n", encoding="utf-8")
    (tmp_path / "SESSION.md").write_text("37 rows in the ledger\n", encoding="utf-8")
    monkeypatch.setattr(rf, "SCOPE", ("CLAUDE.md", "SESSION.md"))
    groups = rf.cross_document(rf.figures(tmp_path))
    assert ("37", "row") in groups, groups
    assert len({row.path for row in groups[("37", "row")]}) == 2


def test_the_WORD_CEILING_is_stated_and_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ninety-nine is the documented ceiling, so the boundary is pinned.

    A reader must not have to discover the limit by being wrong about it: above
    the ceiling the extractor is blind, which is the very property this arm
    exists to remove, so the edge is asserted rather than described.
    """
    (tmp_path / "CLAUDE.md").write_text(
        "ninety-nine rows and one hundred rows\n", encoding="utf-8"
    )
    monkeypatch.setattr(rf, "SCOPE", ("CLAUDE.md",))
    figures = {occurrence.figure for occurrence in rf.figures(tmp_path)}
    assert "99" in figures
    assert "100" not in figures


# -- the intra-sentence arithmetic arm --------------------------------------

_ROW = (
    "| 2026-08-12 | ARC 099 | 50 | **{delta}** — {narration}. "
    "Opened: D3.41-D3.47 (A) · D3.51-D3.56 (B) · D3.99 (late). "
    "**Discharged: D3.29, D3.30 and D3.39, each re-measured.** Commentary "
    "mentioning D3.12 and D3.13 after the fact.\n"
)


#: The same row with its discharges narrated in PROSE instead of enumerated —
#: the shape that produced three false positives before `discharged_count` knew
#: how to read it.
_ROW_NO_LIST = (
    "| 2026-08-12 | ARC 099 | 50 | **{delta}** — {narration}. "
    "Opened: D3.41-D3.47 (A) · D3.51-D3.56 (B) · D3.99 (late). Commentary.\n"
)


def _defects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, row: str) -> list:
    (tmp_path / "CHECK-DEBT.md").write_text(row, encoding="utf-8")
    monkeypatch.setattr(rf, "SCOPE", ("CHECK-DEBT.md",))
    return rf.enumeration_defects(tmp_path)


def test_a_stated_total_its_own_enumeration_REFUTES_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """14 ids enumerated, `thirteen opened` narrated. One passage, both facts."""
    row = _ROW.format(delta="+11", narration="thirteen opened, three discharged")
    found = _defects(tmp_path, monkeypatch, row)
    opened = [d for d in found if d.kind == "opened"]
    assert opened, found
    assert (opened[0].stated, opened[0].derived) == (13, 14)


def test_the_enumeration_STOPS_at_its_own_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ids mentioned in later commentary are not openings.

    Measured: without the sentence stop, the `Opened:` segment ran on through the
    row's closing prose and swept up every id there — ARC 020's three openings
    read as seven, and the arm reported a defect in a correct row.
    """
    row = _ROW.format(delta="+11", narration="fourteen opened, three discharged")
    assert _defects(tmp_path, monkeypatch, row) == []


#: The LIVE shape that defeated the sentence stop, ARC 049. Its `Opened:`
#: enumeration ends `…(late).**` — a period against BOLD MARKUP, with no space
#: after it — which is how ARC 047's real row is written and why the `". "` stop
#: never fired on it.
_ROW_BOLD_SENTENCE_END = (
    "| 2026-08-12 | ARC 099 | 50 | **{delta}** — {narration}. "
    "**Opened: D3.41-D3.47 (A) · D3.51-D3.56 (B) · D3.99 (late).** Commentary "
    "mentioning D3.12 and D3.13 after the fact. "
    "**Discharged: D3.29, D3.30 and D3.39, each re-measured.**\n"
)


def test_the_enumeration_STOPS_at_a_BOLD_sentence_end_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`).**` ends the passage as surely as `). ` does. ARC 049, MEASURED LIVE.

    The stop set knew one spelling of a sentence end. ARC 047's row closes its
    enumeration `…balance).**`, so the segment ran on and counted `(D3.177)` —
    cited two sentences later as the join that refuses `identity_trade_id` — as
    a fifth opening. A correct row read as self-contradicting, which is the
    false-positive direction and the one that erodes an instrument's standing.

    This is the SAME failure mode `_segment`'s docstring already records for
    ARC 020, recurring under a different spelling. The row below is the live
    shape reduced: fourteen ids enumerated under a BOLD `Opened:` heading, two
    more cited in the commentary after it.
    """
    row = _ROW_BOLD_SENTENCE_END.format(
        delta="+11", narration="fourteen opened, three discharged"
    )
    assert _defects(tmp_path, monkeypatch, row) == []


def test_the_BOLD_stop_still_REFUTES_a_wrong_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop must narrow the passage, not blind the arm (doctrine C.2)."""
    row = _ROW_BOLD_SENTENCE_END.format(
        delta="+11", narration="thirteen opened, three discharged"
    )
    found = [d for d in _defects(tmp_path, monkeypatch, row) if d.kind == "opened"]
    assert found and (found[0].stated, found[0].derived) == (13, 14), found


def test_the_SUBSET_numerator_is_never_reconciled_as_a_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`N of the M new rows` states one total and one subset.

    Reconciling the subset would manufacture a finding out of a sentence telling
    the truth — which is how the first spelling of this arm behaved.
    """
    row = _ROW.format(
        delta="+11", narration="nine of the fourteen new rows came from an instrument"
    )
    assert _defects(tmp_path, monkeypatch, row) == []


def test_the_SUBSET_DENOMINATOR_is_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The M in `N of the M new rows` IS a total claim, and is checked."""
    row = _ROW.format(
        delta="+11", narration="nine of the twelve new rows came from an instrument"
    )
    found = [d for d in _defects(tmp_path, monkeypatch, row) if d.kind == "opened"]
    assert found and (found[0].stated, found[0].derived) == (12, 14)


def test_ADJACENCY_keeps_a_distant_number_from_answering_for_the_noun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loose window let any number on a 400-character row be the total.

    Measured with a thirty-character window: `**-1** — four discharged, three
    opened` was read as a claim that ONE row was opened.
    """
    row = _ROW.format(delta="+11", narration="four discharged, fourteen opened")
    assert _defects(tmp_path, monkeypatch, row) == []


@pytest.mark.parametrize(
    "narration",
    [
        "fourteen opened, three discharged",
        "fourteen opened, none discharged",
        "fourteen opened and no rows were discharged",
    ],
)
def test_the_DISCHARGE_COUNT_is_read_in_every_shape_these_rows_use(
    narration: str,
) -> None:
    """Three shapes, one derivation — and the false positives they caused.

    A derivation that knew only the enumerated `Discharged:` list read `ten
    opened, one discharged` as ZERO discharges and reported a delta defect in a
    row whose arithmetic was correct: three false positives (ARC 022, ARC 025,
    ARC 027) against one true one.
    """
    line = _ROW_NO_LIST.format(delta="+0", narration=narration)
    count = rf.discharged_count(line)
    assert count is not None
    assert count == (3 if "three" in narration else 0)


def test_a_discharge_count_that_CANNOT_be_derived_ABSTAINS(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`None` is a first-class answer: a count that cannot be read is not zero.

    The delta arm must stay silent rather than invent a derivation, because a
    confident wrong answer here is worse than an admitted gap.
    """
    row = (
        "| 2026-08-12 | ARC 099 | 50 | **+99** — some rows moved. "
        "Opened: D3.41-D3.47 (A) · D3.51-D3.56 (B) · D3.99 (late). Commentary.\n"
    )
    assert rf.discharged_count(row) is None
    assert [d for d in _defects(tmp_path, monkeypatch, row) if d.kind == "delta"] == []


def test_a_stated_DELTA_its_enumerations_refute_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """14 opened - 3 discharged = +11, and the row claims +9."""
    row = _ROW.format(delta="+9", narration="fourteen opened, three discharged")
    found = [d for d in _defects(tmp_path, monkeypatch, row) if d.kind == "delta"]
    assert found and (found[0].stated, found[0].derived) == (9, 11)


def test_the_LIVE_LEDGER_no_longer_contradicts_itself() -> None:
    """The regression control for ARC 029 / 0.2's correction.

    The ARC 028 series row narrated `+36` and `thirty-six new rows` while its own
    enumeration gives 41 opened and 3 discharged — 41 - 3 = 38. Both were
    corrected in place WITH the correction annotated, and this test is what stops
    the class recurring for a fourth time.
    """
    defects = rf.enumeration_defects(rf.REPO)
    assert defects == [], [
        f"{d.path}:{d.line} [{d.kind}] stated {d.stated}, enumeration {d.derived}"
        for d in defects
    ]
