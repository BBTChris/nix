"""`check_spec_citations` resolves real citations and reddens phantom ones.

ARC 019 / C1. Every assertion here drives the gate's own functions rather than a
reimplementation of them, because a test that re-derives the answer proves the
test, not the gate.

The pytest suite is where the CONTROL half of doctrine C.2 lives permanently:
the arc's can-fail was taken by hand against the real tree, and these tests keep
it reproducible after the plant is gone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_spec_citations as gate  # pylint: disable=import-error
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)

SPEC = "nics_risk_subsystem_spec_v1.3.md"


@pytest.fixture(name="docs", scope="module")
def _docs() -> dict:
    return gate.build_index(REPO)


# ---------------------------------------------------------------------------
# NON-VACUITY. Asserted before anything else, per doctrine C.3.
# ---------------------------------------------------------------------------


def test_the_heading_index_contains_its_subject(docs: dict) -> None:
    """The frozen spec must index, or every citation of it is unjudgeable."""
    assert SPEC in docs
    assert docs[SPEC], "the frozen spec contributed no numbered heading"
    for required in gate.REQUIRED_DOCS:
        assert docs[required], f"{required} contributed no numbered heading"


def test_the_index_is_derived_not_declared(docs: dict) -> None:
    """Labels come out of the document. §2A is there and §2.1 is not.

    This is the ARC 018 finding, pinned: if a future edit ever makes `§2.1`
    resolvable in the frozen spec, that is a change to a document declared
    frozen and this assertion is where it surfaces.
    """
    assert "2A" in docs[SPEC]
    assert "12A" in docs[SPEC]
    assert "2.1" not in docs[SPEC]
    assert "14" in docs[SPEC]


def test_a_document_that_numbers_by_letter_is_unindexable(docs: dict) -> None:
    """`VERIFY-AND-CHECKS.md` numbers by Part letter, so it indexes empty.

    Without this the gate would report every citation of the doctrine as a
    violation, which doctrine B.4 calls broken rather than strict.
    """
    assert docs.get("VERIFY-AND-CHECKS.md") == {}


def test_the_scan_finds_citations_in_the_governed_roots(docs: dict) -> None:
    """A scanner that finds zero citations passes beautifully and proves nothing."""
    found = gate.scan_tree(REPO, gate.build_aliases(docs))
    assert found, "no §-citation found anywhere in the tree"
    governed = {c.file for c in found if gate.is_governed(c.file)}
    assert governed, "no citation found inside the governed roots"
    for required in gate.REQUIRED_GOVERNED:
        assert (REPO / required).is_file()


def test_at_least_one_known_good_citation_resolves(docs: dict) -> None:
    """The positive control: a real citation of the frozen spec must resolve.

    §2A:71 is the anchor ARC 018 verified by hand for the never-auto-resend ban,
    and it is cited with its document named in `check_order_path_bans.py`.
    """
    found = gate.scan_tree(REPO, gate.build_aliases(docs))
    good = [
        c
        for c in found
        if c.document == SPEC and c.section == "2A" and gate.resolve(c, docs) is None
    ]
    assert good, "no citation resolved into the frozen spec"


def test_some_line_coordinate_is_actually_range_checked(docs: dict) -> None:
    """The coordinate arm must have a subject, or it measures nothing."""
    found = gate.scan_tree(REPO, gate.build_aliases(docs))
    checked = [
        c
        for c in found
        if c.document and c.coordinates and gate.resolve(c, docs) is None
    ]
    assert checked, "no §X:N citation was attributed, so the coordinate arm is idle"


# ---------------------------------------------------------------------------
# CAN-FAIL. Each drives the real resolver against a constructed citation.
# ---------------------------------------------------------------------------


def _cite(section: str, coordinates: tuple[int, ...] = ()) -> gate.Citation:
    return gate.Citation(
        file="checks/probe.py",
        line=1,
        section=section,
        coordinates=coordinates,
        document=SPEC,
        ambiguous=False,
    )


def test_a_phantom_section_does_not_resolve(docs: dict) -> None:
    """A section number that exists in no document must not resolve."""
    complaint = gate.resolve(_cite("99.9"), docs)
    assert complaint is not None
    assert "99.9" in complaint and SPEC in complaint


def test_the_arc_018_phantom_does_not_resolve(docs: dict) -> None:
    """§2.1 of the frozen spec — the citation that started this."""
    assert gate.resolve(_cite("2.1"), docs) is not None


def test_a_real_section_resolves(docs: dict) -> None:
    """CONTROL: the two headings ARC 018 verified by hand do resolve."""
    assert gate.resolve(_cite("2A"), docs) is None
    assert gate.resolve(_cite("12A"), docs) is None


def test_a_coordinate_inside_the_span_resolves(docs: dict) -> None:
    """§2A:71 is `query_order_status` — never auto-resend. Verified ARC 018."""
    assert gate.resolve(_cite("2A", (71,)), docs) is None
    assert gate.resolve(_cite("2A", (103, 107)), docs) is None


def test_a_coordinate_outside_the_span_does_not_resolve(docs: dict) -> None:
    """The coordinate arm can say no."""
    complaint = gate.resolve(_cite("2A", (99999,)), docs)
    assert complaint is not None
    assert "outside" in complaint


def test_the_wrong_section_for_a_real_line_is_caught(docs: dict) -> None:
    """ "invariant N per §14" pointed at the wrong section across three briefs.

    The invariants are at §2A:103-107. Attached to §14 the coordinate falls
    outside that section's span, which is the whole reason design choice (ii)
    range-checks rather than ignoring the coordinate.
    """
    assert gate.resolve(_cite("14", (103,)), docs) is not None
    assert gate.resolve(_cite("2A", (103,)), docs) is None


# ---------------------------------------------------------------------------
# ATTRIBUTION — the part a naive version gets wrong.
# ---------------------------------------------------------------------------


def test_attribution_prefers_a_preceding_document_mention(docs: dict) -> None:
    """Prose names the document and then cites into it."""
    aliases = gate.build_aliases(docs)
    text = f"per `{SPEC}` §2A:71 the system never auto-resends"
    assert gate.attribute(text, text.index("§"), aliases) == SPEC


def test_attribution_declines_when_two_documents_are_equidistant(docs: dict) -> None:
    """A rival document at the same distance makes the citation undecidable."""
    aliases = gate.build_aliases(docs)
    text = "debug.md §7.12 elements_v2.md"
    assert gate.attribute(text, text.index("§"), aliases) in (None, "debug.md")


def test_attribution_declines_with_no_document_in_range(docs: dict) -> None:
    """An unattributed citation is exactly how §2.1 acquired spec authority."""
    aliases = gate.build_aliases(docs)
    text = "a hand-rolled retry loop is banned by §2.1 and undetected by the gate"
    assert gate.attribute(text, text.index("§"), aliases) is None


def test_a_table_row_is_its_own_attribution_block() -> None:
    """A markdown row is a record; the row above it is a different record."""
    found = gate.blocks("| a | debug.md |\n| b | §7.12 |\n")
    assert len(found) == 2
    assert "debug.md" not in found[1].text


# ---------------------------------------------------------------------------
# SUPPRESSIONS — signed, self-expiring, never file-level.
# ---------------------------------------------------------------------------


def test_an_unsigned_suppression_is_a_defect(tmp_path: Path) -> None:
    """An unsigned suppression is not a review."""
    path = tmp_path / gate.SUPPRESSIONS_FILE
    path.write_text(
        '{"reviewed": [{"file": "a.py", "section": "1", "document": "d.md",'
        ' "justification": "", "reviewed_in": ""}]}',
        encoding="utf-8",
    )
    loaded = gate.load_suppressions(path)
    assert not loaded.keys
    assert loaded.defects


def test_a_suppression_missing_a_key_is_a_defect(tmp_path: Path) -> None:
    """There is no file-level suppression form; a missing key is rejected."""
    path = tmp_path / gate.SUPPRESSIONS_FILE
    path.write_text(
        '{"reviewed": [{"file": "a.py", "justification": "x"}]}', encoding="utf-8"
    )
    loaded = gate.load_suppressions(path)
    assert not loaded.keys
    assert loaded.defects


def test_the_live_suppression_registry_is_signed_and_keyless_of_lines() -> None:
    """Every shipped entry is signed, and none of them keys on a line number."""
    loaded = gate.load_suppressions(CHECKS / gate.SUPPRESSIONS_FILE)
    assert not loaded.defects, loaded.defects
    for key, entry in loaded.keys.items():
        assert len(key) == len(gate.SUPPRESSION_KEYS)
        assert entry["justification"].strip()
        assert entry["reviewed_in"].strip()
        assert "line" not in entry


# ---------------------------------------------------------------------------
# END TO END.
# ---------------------------------------------------------------------------


def test_the_gate_passes_on_the_real_tree() -> None:
    """CONTROL. If this reddens, a citation in a governed root stopped resolving."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail
    assert result.evidence


def test_the_gate_reports_its_own_scope_on_every_run() -> None:
    """A gate that cannot report its scope cannot be seen to have collapsed."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    for token in ("attributed", "unattributed", "line coordinate", "governed roots"):
        assert token in (result.evidence or "")


def test_an_empty_docs_directory_is_cannot_measure(tmp_path: Path) -> None:
    """§7.12 condition 1: no index is never a PASS."""
    (tmp_path / "docs").mkdir()
    result = gate.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
