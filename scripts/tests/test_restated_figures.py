"""Tests for `scripts/tests/restated_figures.py` (ARC 027 / D2).

The load-bearing assertions are the two that prove the answer sheet can say
BOTH things: `9 of 13` must come back AGREES and `512 test functions` must come
back DISAGREES. A table in which nothing can disagree is not an answer sheet,
it is a list of numbers with a green tick painted on.

Every assertion keys on the REASON — the verdict token, the derived value, the
refusal text — never on a bare exit code.
"""

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
