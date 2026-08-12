"""`check_spec_citations` resolves real citations and reddens phantom ones.

ARC 019 / C1. Every assertion here drives the gate's own functions rather than a
reimplementation of them, because a test that re-derives the answer proves the
test, not the gate.

The pytest suite is where the CONTROL half of doctrine C.2 lives permanently:
the arc's can-fail was taken by hand against the real tree, and these tests keep
it reproducible after the plant is gone.
"""

from __future__ import annotations

# R0801: see the note in test_check_python_runtime.py. Each gate's ARC 025
# re-binding stands on its own file on purpose; one shared helper would let a
# single edit silently un-bind three independent instruments.
# pylint: disable=duplicate-code
import ast
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
CHECK_FILE = CHECKS / "check_spec_citations.py"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_spec_citations as gate  # pylint: disable=import-error
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)
from nixverify.declarations import read_declaration  # pylint: disable=import-error

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


# ===========================================================================
# ARC 025 — ORCHESTRATION DECLARATIONS (read statically, never by import)
# ===========================================================================


def test_every_declaration_is_present_and_statically_readable() -> None:
    """§4.4 of `nix_check_contract.md`: all seven symbols readable by AST, with
    no named error. A computed declaration is an error, never a default.
    """
    declaration = read_declaration(CHECK_FILE)
    assert not declaration.errors, declaration.errors
    for symbol in (
        "DEPENDS_ON",
        "RESOURCES",
        "TIME_BOUND",
        "CORRECTABLE",
        "NON_CORRECTABLE_REASON",
        "SUBJECTS",
    ):
        assert symbol in declaration.declared, f"{symbol} not declared"
    assert not declaration.depends_on
    assert not declaration.resources
    assert declaration.declares_resources is True
    assert declaration.time_bound is False
    assert declaration.expected_s is None
    assert declaration.correctable is False
    assert declaration.non_correctable_reason.strip()
    assert declaration.subjects == ("checks/citation_reviewed.json",)


def test_the_empty_resource_claim_is_true_this_gate_writes_nothing() -> None:
    """`RESOURCES = ()` is a positive claim and must be checkable, not trusted.

    Proof by absence (doctrine C.5) rather than by call-site inspection, and
    over the AST rather than the text: a substring scan would fire on the word
    "socket" inside the declaration's own comment, which is a false positive of
    exactly the kind doctrine B.4 calls broken rather than strict.
    """
    tree = ast.parse(CHECK_FILE.read_text(encoding="utf-8"), filename=str(CHECK_FILE))

    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    for module in ("socket", "subprocess", "shutil", "os", "tempfile"):
        assert module not in imported, (
            f"the gate imports {module!r} — RESOURCES=() is not a true claim"
        )

    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    # Non-vacuity for the scan itself: a walk that collected nothing would
    # satisfy every assertion below while having looked at nothing.
    assert "read_text" in called, "the AST scan found no calls — it measured nothing"
    for verb in ("write_text", "write_bytes", "mkdir", "unlink", "rmdir", "open"):
        assert verb not in called, (
            f"the gate calls {verb!r} — RESOURCES=() is not a true claim"
        )


def test_the_declared_subject_is_the_registry_this_gate_validates() -> None:
    """SUBJECTS names an artifact this gate MEASURES, not merely mentions.

    `citation_reviewed.json` is read, its entries are validated (unsigned ones
    become defects) and unmatched ones are reddened as stale — so it is measured
    here in the strong sense. The file is asserted to exist so the declaration
    cannot point at nothing.
    """
    subject = read_declaration(CHECK_FILE).subjects[0]
    assert subject == f"checks/{gate.SUPPRESSIONS_FILE}"
    assert (REPO / subject).is_file()
    loaded = gate.load_suppressions(REPO / subject)
    assert loaded.keys or loaded.defects, (
        "the declared subject contributed neither a usable key nor a defect — "
        "the gate is not actually reading it"
    )


# ===========================================================================
# RE-BINDING — §0c. A retrofitted check is a NEW check.
#
# The plant has to be a governed file, and every governed root on the real tree
# is a production artifact (doctrine C.8 forbids planting there). So the gate is
# pointed at a SYNTHETIC nix_home built from symlinks to the real documents and
# the real governed member, and the plant lands only inside that.
# ===========================================================================


def _synthetic_home(tmp_path: Path) -> Path:
    """A minimal nix_home that satisfies every one of this gate's floors.

    Symlinks, not copies: the heading index, the alias map and the governed
    member must be the REAL artifacts, or the tree the plant is measured against
    is a different tree from the one the gate guards.
    """
    home = tmp_path / "synthetic"
    (home / "docs").mkdir(parents=True)
    (home / "checks").mkdir()
    for document in sorted((REPO / "docs").glob("*.md")):
        (home / "docs" / document.name).symlink_to(document)
    for member in gate.REQUIRED_GOVERNED:
        target = home / member
        if not target.exists():
            target.symlink_to(REPO / member)
    return home


def test_non_vacuity_the_synthetic_tree_contains_the_gates_subject(
    tmp_path: Path,
) -> None:
    """Doctrine C.3, asserted BEFORE the plant. The scope contains the subject.

    Four separate containments, because the gate has four ways to be looking at
    nothing: no heading index, no citations at all, no citation inside a
    governed root, and no citation resolving into the frozen spec.
    """
    home = _synthetic_home(tmp_path)
    docs = gate.build_index(home)
    for required in gate.REQUIRED_DOCS:
        assert docs.get(required), f"{required} contributed no numbered heading"

    found = gate.scan_tree(home, gate.build_aliases(docs))
    assert found, "the synthetic tree holds no §-citation at all"
    governed = {c.file for c in found if gate.is_governed(c.file)}
    assert governed, "the synthetic tree holds no citation inside a governed root"
    resolved = {
        c.document
        for c in found
        if c.document and docs[c.document] and gate.resolve(c, docs) is None
    }
    for required in gate.REQUIRED_DOCS:
        assert required in resolved, f"no citation resolved into {required}"


def test_plant_and_control_a_phantom_citation_in_a_governed_file(
    tmp_path: Path,
) -> None:
    """PLANT then CONTROL, in one test so neither half can be read alone.

    §99.9 is a heading in no document in `docs/`, and the plant names the frozen
    spec beside it so the gate's attribution has something to bind to — which is
    the exact shape of the ARC 018 defect this instrument was built for.
    """
    home = _synthetic_home(tmp_path)

    # -- CONTROL, first half: the synthetic tree is green before the plant. --
    clean = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert clean.status is Status.PASS, clean.detail

    # -- PLANT -------------------------------------------------------------
    planted_file = home / "checks" / "planted_phantom_citation.py"
    planted_file.write_text(
        "# ARC 025 sub-agent A can-fail plant: nics_risk_subsystem_spec_v1.3.md "
        "§99.9\n# is not a heading in that frozen document.\n",
        encoding="utf-8",
    )
    planted = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert planted.status is Status.FAIL_NEEDS_OPERATOR
    # THE SITE — doctrine C.2 requires the gate to name where. Not the status.
    assert "checks/planted_phantom_citation.py" in planted.site, planted.site
    assert "§99.9" in planted.site, planted.site
    # THE REASON — which section, in which document, and what that document
    # actually holds instead.
    assert "§99.9 is not a heading in nics_risk_subsystem_spec_v1.3.md" in (
        planted.detail
    ), planted.detail
    # And it did not redden anything else in the process.
    assert planted.site.count(";") == 0, planted.site

    # -- REMOVE THE PLANT — the control half. ------------------------------
    planted_file.unlink()
    restored = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert restored.status is Status.PASS, restored.detail
    assert restored.evidence


def test_the_same_plant_outside_a_governed_root_is_a_survey_note_not_a_failure(
    tmp_path: Path,
) -> None:
    """The severity boundary itself, bound. Identical text, ungoverned path.

    Without this, a FAIL from the test above could equally be produced by a gate
    that reddens every non-resolution everywhere — which is doctrine B.4's
    broken-rather-than-strict, and would make `GOVERNED_ROOTS` decorative.
    """
    home = _synthetic_home(tmp_path)
    (home / "scripts").mkdir()
    (home / "scripts" / "ungoverned_phantom.py").write_text(
        "# ARC 025 sub-agent A can-fail plant: nics_risk_subsystem_spec_v1.3.md "
        "§99.9\n# is not a heading in that frozen document.\n",
        encoding="utf-8",
    )
    result = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail
    # It is NOT ignored: it is counted and named in evidence on every run.
    assert "SURVEY scripts/ungoverned_phantom.py:1 §99.9" in result.evidence


# ===========================================================================
# ACTUATION — the flag surface, and the refusal that must name its reason.
# ===========================================================================


def test_a_flagless_invocation_is_measure_only(tmp_path: Path) -> None:
    """§4.3 of `nix_check_contract.md`: the default is verify, and a flagless
    check never mutates. Measured on a synthetic home so a mutation would show.
    """
    home = _synthetic_home(tmp_path)
    before = {
        str(p.relative_to(home)): p.read_bytes()
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }
    proc = subprocess.run(
        [sys.executable, str(CHECK_FILE), str(home)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith("pass:"), proc.stdout
    after = {
        str(p.relative_to(home)): p.read_bytes()
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }
    assert after == before, "a flagless run mutated its target"


def test_correct_and_install_refuse_and_name_the_declared_reason() -> None:
    """§2.3: the refusal must name its reason, and the assertion is on the
    reason TEXT — read from the declaration so the two cannot drift apart.

    Exit code alone is not evidence: ARC 024's re-verify control passed because
    the subprocess CRASHED and also returned 1.
    """
    reason = read_declaration(CHECK_FILE).non_correctable_reason
    assert reason.strip()
    for verb in ("--correct", "--install"):
        proc = subprocess.run(
            [sys.executable, str(CHECK_FILE), verb],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "NON-CORRECTABLE" in proc.stderr, proc.stderr
        assert f"refuses {verb}" in proc.stderr, proc.stderr
        assert reason in proc.stderr, proc.stderr
        assert "manufacturing" in proc.stderr, proc.stderr
