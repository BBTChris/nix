"""The `owning module` column — ARC 026 (B3), the structural close of a four-time defect.

`check_derived_claims`'s depth metrics used to select ledger rows by scanning the
WHOLE ROW TEXT for module basenames and roster identifiers. It was contaminated
four times; each repair narrowed the vocabulary and none changed the mechanism,
so a fifth contamination was one wording away. The sharpest instance: D1.41
entered the broker-order metric because `socket.connect` contains the word
`connect` — the spy that took ARC 024's measurement contaminated the metric
measuring it.

Selection is now the AUTHORED `owning module` column and nothing else.

WHAT THIS SUITE PROVES, and the third item is the one that matters most:

1. **The column parses and the metric is non-vacuous on the REAL ledger.**
2. **Prose is no longer load-bearing.** A row reworded to contain every word the
   old mechanism keyed on does not move the count. That is the property the
   repair exists to buy, and it is asserted directly rather than inferred from
   the mechanism's shape.
3. **The parser FAILS CLOSED.** An unattributed row, an unknown token, a missing
   vocabulary table and a missing tally row are each a loud `ProbeError` naming
   the row — never a silent exclusion. A lenient parser would rebuild, one layer
   down, exactly the failure this column replaces: a row leaving a count with
   nobody noticing.

NO PLANT TOUCHES THE PRODUCTION LEDGER (doctrine C.8). Every plant is written
into a COPY under `tmp_path`; `docs/CHECK-DEBT.md` is append-only banked evidence
and ARC 025's permanent-synthetic-row incident is what editing it in place costs.
"""

# pylint: disable=invalid-name,duplicate-code,import-outside-toplevel
# Test names SHOUT the property under test, as the rest of this suite does.
# `duplicate-code`: the sys.path bootstrap and the SCRUBBED fixture-git helper
# are repeated per module DELIBERATELY. Factoring them into a shared conftest
# would hide the D3.22 scrub from the reader of each module, and a scrub nobody
# sees at the call site is how three private spellings of it drifted apart in
# the first place. Late imports are the sys.path bootstrap this suite needs.
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
SCRIPTS = REPO / "scripts"
for _extra in (str(CHECKS), str(SCRIPTS)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position,protected-access
import check_derived_claims as gate  # pylint: disable=import-error

LEDGER = "docs/CHECK-DEBT.md"


@pytest.fixture(name="tree")
def _tree(tmp_path: Path) -> Path:
    """A tmp tree holding a COPY of the real ledger. Never the real one."""
    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    shutil.copy2(REPO / LEDGER, home / LEDGER)
    return home


def _edit(home: Path, old: str, new: str) -> None:
    path = home / LEDGER
    text = path.read_text(encoding="utf-8")
    assert old in text, f"plant anchor not found: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- non-vacuity, on the real ledger, before any plant --------------------


def test_NON_VACUITY_the_real_ledger_attributes_every_open_row() -> None:
    """Every open row carries a valid token, and the population is not empty.

    Asserted as invariants: no count is written here. The ledger's open figure
    moves at the close of every arc, and a literal would be the moving anchor
    (`debug.md` §8 failure mode #4) that this project has caught five times.
    """
    grouped = gate._open_rows_by_module(REPO)
    assert grouped, "the vocabulary parsed to nothing"
    assert sum(len(ids) for ids in grouped.values()) > 1
    assert grouped["broker-order"], "no row is attributed to broker-order"
    assert grouped["broker-datafeed"], "no row is attributed to broker-datafeed"


def test_the_derived_scan_and_the_STATED_tally_agree_on_the_real_ledger() -> None:
    """The claim's two sources, checked here as well as by the gate.

    They are genuinely two: one counts rows, the other reads a table a person
    maintains. If they were both derived from the column the claim could not
    fail, which is the vacuity the tally exists to prevent.
    """
    for module, derived, stated in (
        (
            "broker-order",
            gate._p_broker_order_debt_rows_ledger,
            gate._p_broker_order_debt_rows_tally,
        ),
        (
            "broker-datafeed",
            gate._p_datafeed_debt_rows_ledger,
            gate._p_datafeed_debt_rows_tally,
        ),
    ):
        left, left_detail = derived(REPO)
        right, _ = stated(REPO)
        assert left == right, (
            f"{module}: derived {left} != stated {right}\n{left_detail}"
        )


# --- THE PROPERTY THE REPAIR BUYS ------------------------------------------


def test_PROSE_IS_NO_LONGER_LOAD_BEARING(tree: Path) -> None:
    """THE HEADLINE ASSERTION. Reword a row; the count must not move.

    The plant is deliberately the worst case the old mechanism could face: a row
    owned by `verify` is rewritten to name `broker_order_ibkr.py`, `flatten`,
    `socket.connect` and `ibkr_mapping.py` — every category of term the four
    historical contaminations keyed on, including the literal `socket.connect`
    of D1.41. Under the old rule this row would have entered the broker-order
    metric. Under the column it cannot, because its token still reads `verify`.
    """
    before, _ = gate._p_broker_order_debt_rows_ledger(tree)
    _edit(
        tree,
        "| D2.28 | §17 |",
        "| D2.28 | §17 — see `broker_order_ibkr.py`, `ibkr_mapping.py`, "
        "`flatten`, `socket.connect`, `disconnect`, `place_order` |",
    )
    after, detail = gate._p_broker_order_debt_rows_ledger(tree)
    assert after == before, f"prose moved the count {before} -> {after}\n{detail}"
    assert "D2.28" not in detail, detail


def test_CONTROL_changing_the_COLUMN_does_move_the_count(tree: Path) -> None:
    """The other half. Without it the test above only proves the gate is inert.

    One token edited, one row moved, and the reason is asserted — the row id must
    appear in the selection detail, not merely a number one higher.
    """
    before, _ = gate._p_broker_order_debt_rows_ledger(tree)
    _edit(tree, "| D2.28 | §17 |", "| D2.28 | §17 |")
    path = tree / LEDGER
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("| D2.28 |"):
            lines[index] = (
                line.rstrip()[:-1].rstrip().rsplit("|", 1)[0] + "| broker-order |"
            )
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    after, detail = gate._p_broker_order_debt_rows_ledger(tree)
    assert after == before + 1, detail
    assert "D2.28" in detail, detail


# --- FAIL CLOSED -----------------------------------------------------------


def test_an_open_row_with_NO_COLUMN_is_a_LOUD_ERROR(tree: Path) -> None:
    """A silent exclusion here is the exact defect the column replaces."""
    path = tree / LEDGER
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("| D2.28 |"):
            lines[index] = line.rstrip()[:-1].rstrip().rsplit("|", 1)[0] + "|"
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(gate.ProbeError) as caught:
        gate._p_broker_order_debt_rows_ledger(tree)
    assert "D2.28" in str(caught.value), caught.value
    assert "owning module" in str(caught.value), caught.value


def test_an_UNKNOWN_token_is_a_LOUD_ERROR_naming_the_row(tree: Path) -> None:
    """A typo must not quietly remove a row from every module's count."""
    path = tree / LEDGER
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("| D2.28 |"):
            lines[index] = (
                line.rstrip()[:-1].rstrip().rsplit("|", 1)[0] + "| brokerorder |"
            )
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(gate.ProbeError) as caught:
        gate._p_broker_order_debt_rows_ledger(tree)
    assert "D2.28=brokerorder" in str(caught.value), caught.value


def test_a_MISSING_vocabulary_table_is_a_LOUD_ERROR(tree: Path) -> None:
    """With no legal tokens every row is rejected, and a count over a rejected
    population is not a count."""
    path = tree / LEDGER
    kept = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("| `")
    ]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    with pytest.raises(gate.ProbeError) as caught:
        gate._p_broker_order_debt_rows_ledger(tree)
    assert "vocabulary" in str(caught.value), caught.value


def test_a_MISSING_tally_row_is_a_LOUD_ERROR_not_a_zero(tree: Path) -> None:
    """An absent stated row would read as zero, and zero is a claim."""
    _edit(tree, "| broker-order | 9 |", "")
    with pytest.raises(gate.ProbeError) as caught:
        gate._p_broker_order_debt_rows_tally(tree)
    assert "broker-order" in str(caught.value), caught.value


def test_a_WRONG_tally_makes_the_two_sources_DISAGREE(tree: Path) -> None:
    """The B.7 self-enforcing pattern: add a row, forget the tally, go RED."""
    _edit(tree, "| broker-order | 9 |", "| broker-order | 8 |")
    derived, _ = gate._p_broker_order_debt_rows_ledger(tree)
    stated, _ = gate._p_broker_order_debt_rows_tally(tree)
    assert derived != stated, (derived, stated)


def test_a_tally_naming_a_token_the_vocabulary_lacks_is_a_LOUD_ERROR(
    tree: Path,
) -> None:
    """The tally and the vocabulary are two halves of one rule and must agree."""
    _edit(tree, "| broker-order | 9 |", "| broker-order | 9 |\n| invented | 4 |")
    with pytest.raises(gate.ProbeError) as caught:
        gate._p_broker_order_debt_rows_tally(tree)
    assert "invented" in str(caught.value), caught.value
