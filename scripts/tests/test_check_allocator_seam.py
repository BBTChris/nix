"""ARC 031 / 0.6 — the can-fail suite for `checks/check_allocator_seam.py`.

**THE REQUIREMENT THIS FILE EXISTS TO SATISFY** (ARC 031 brief, 0.6; ARC
028/029 precedent): *prove the seam gate actually reddens on a change to EACH
declared property.* A seam gate that stays green on a renamed field or a
dropped version stamp measures nothing, and both arcs found one that did.

So the plants below are enumerated against the seam's OWN declared surface
rather than hand-picked: `test_EVERY_mirrored_field_renamed_in_turn_reddens`
walks `MIRRORED_FIELDS` and plants a rename of each one, and the remaining
tests take the properties a field rename cannot reach — the version stamp, the
shared-object identity, the frozen-ness of each value type, the absence of a
mutating verb, the buckets, the synchronous declaration and the no-behaviour
rule.

**No plant touches a production artifact** (doctrine C.8). Every control builds
a throwaway `nix_home` under `tmp_path` holding COPIES of `nixalloc/seam.py`,
`nixalloc/__init__.py`, `nixrisk/seam.py`, `nixrisk/__init__.py` and the frozen
spec, perturbs a COPY, and drives the SHIPPED gate's own bytes against it.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_allocator_seam as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

COPIED = (
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/__init__.py",
    "docs/nics_risk_subsystem_spec_v1.3.md",
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of both seams and the frozen spec."""
    for rel in COPIED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> None:
    """Rewrite a COPIED file. Fails loudly if the anchor moved or is ambiguous."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{rel}: anchor appears {text.count(old)} times, not once — the plant "
        "would measure something other than what it names"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _picture_slice(home: Path) -> tuple[str, int, int]:
    """`(whole file, start, end)` of the Limiter's `FinancialPicture` block."""
    text = (home / "scripts/nixrisk/seam.py").read_text(encoding="utf-8")
    start = text.index("@dataclass(frozen=True)\nclass FinancialPicture:")
    end = text.index("class FinancialPicturePort", start)
    return text, start, end


def _rename_picture_field(home: Path, field: str) -> None:
    """Rename ONE declared field, inside the `FinancialPicture` block only."""
    text, start, end = _picture_slice(home)
    block = text[start:end]
    anchor = f"\n    {field}: "
    assert block.count(anchor) == 1, (
        f"{field!r} appears {block.count(anchor)} times in the FinancialPicture "
        "block, not once"
    )
    patched = block.replace(anchor, f"\n    {field}_renamed: ")
    (home / "scripts/nixrisk/seam.py").write_text(
        text[:start] + patched + text[end:], encoding="utf-8"
    )


def _red(result, *, site_contains: str, why_contains: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL_NEEDS_OPERATOR, got {result.status!r}: {result.detail}"
    )
    assert site_contains in (result.site or ""), (
        f"site {result.site!r} does not name {site_contains!r}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_tree_and_the_COPY_both_pass(home: Path) -> None:
    """A gate that cannot pass on a clean seam measures nothing on a dirty one."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
    assert "IDENTICAL OBJECTS" in (live.evidence or ""), live.evidence
    copied = _run(home)
    assert copied.status is Status.PASS, copied.detail


def test_the_gate_DECLARES_both_seam_artifacts_as_subjects() -> None:
    """Coverage is what SUBJECTS names; the ratchet can see nothing else."""
    assert set(gate.SUBJECTS) == {
        "scripts/nixalloc/seam.py",
        "scripts/nixalloc/__init__.py",
    }, gate.SUBJECTS
    assert gate.CORRECTABLE is False


def test_a_MISSING_seam_is_cannot_measure_never_a_PASS(tmp_path: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "never a PASS" in (result.detail or ""), result.detail


def test_the_gate_reads_the_tree_it_was_GIVEN_not_the_live_repo(home: Path) -> None:
    """`_preamble` appends the REAL scripts/ to sys.path forever.

    A name-based import would resolve `nixrisk.seam` — and, worse, the
    Allocator seam's own `from nixrisk.seam import ...` — against the live
    repository, and every plant below would be measuring the pristine tree.
    """
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        'SEAM_REV = "1.0.0"',
        'SEAM_REV = "9.9.9-planted"',
    )
    result = _run(home)
    assert "9.9.9-planted" in (result.evidence or ""), (
        f"the gate reported the live tree's seam_rev, not the copy's: {result}"
    )


# --------------------------------------------------------------------------
# EVERY DECLARED PROPERTY OF THE MIRRORED SNAPSHOT, ONE PLANT EACH
# --------------------------------------------------------------------------


def test_EVERY_mirrored_field_renamed_in_turn_reddens(tmp_path: Path) -> None:
    """The 0.6 requirement, enumerated rather than sampled.

    One plant per declared field, derived from the seam's own
    `MIRRORED_FIELDS` — so a field ADDED to the published snapshot in a later
    arc is automatically covered here and cannot slip in untested.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    from nixalloc import seam  # pylint: disable=import-outside-toplevel

    fields = seam.MIRRORED_FIELDS
    assert len(fields) >= 8, f"the published snapshot shrank unexpectedly: {fields}"

    for index, field in enumerate(fields):
        home = tmp_path / f"case_{index}"
        for rel in COPIED:
            target = home / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, target)
        # Rename the field on the LIMITER's side, INSIDE the FinancialPicture
        # class body only — several of these names (`version`, `symbol`) also
        # appear on sibling dataclasses, and a whole-file replace would plant
        # somewhere other than where it says. The Allocator derives its
        # mirrored set from that dataclass, so a rename there is exactly the
        # "a renamed field must not pass" case, and the derivation is what
        # makes it visible instead of silently agreeing.
        _rename_picture_field(home, field)
        result = _run(home)
        assert result.status is Status.FAIL_NEEDS_OPERATOR, (
            f"renaming published field {field!r} left the seam gate GREEN — "
            f"the gate measures nothing about it: {result}"
        )
        assert field in (result.detail or ""), (
            f"the finding does not name the renamed field {field!r}: {result.detail}"
        )


def test_DROPPING_the_version_stamp_reddens_with_its_own_finding(home: Path) -> None:
    """The stamp is not one field among nine; §3's atomicity turns on it."""
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        'VERSION_FIELD = "version"',
        'VERSION_FIELD = ""',
    )
    result = _run(home)
    _red(
        result,
        site_contains="VERSION_FIELD",
        why_contains="makes a torn read unobservable rather than impossible",
    )


# --------------------------------------------------------------------------
# THE PROPERTIES A FIELD RENAME CANNOT REACH
# --------------------------------------------------------------------------


def test_a_LOCAL_REDEFINITION_of_the_snapshot_reddens_even_when_identical(
    home: Path,
) -> None:
    """The shape-vs-identity distinction, driven with a BYTE-IDENTICAL copy.

    This is the plant a shape comparison passes. §6.4 says both readers take
    "the same versioned row — identical bytes BY CONSTRUCTION"; a second
    dataclass with every field spelled the same is identical by inspection
    only, and inspection is what stops happening.
    """
    text, start, end = _picture_slice(home)
    duplicate = text[start:end].rstrip() + "\n"
    # Placed AFTER the import block and BEFORE `MIRRORED_FIELDS`, so the local
    # definition shadows the imported one exactly the way a well-meaning
    # "let's declare our own copy" edit would — same fields, same order, same
    # bytes, and a different object.
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        'SEAM_REV = "1.0.0"',
        f'{duplicate}\n\nSEAM_REV = "1.0.0"',
    )
    result = _run(home)
    _red(
        result,
        site_contains="FinancialPicture",
        why_contains="is a DIFFERENT object",
    )
    assert "identical bytes BY CONSTRUCTION" in (result.detail or ""), result.detail


def test_an_UNFROZEN_value_type_reddens(home: Path) -> None:
    """A mutable mirror holder is a write to canonical state with no message."""
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "@dataclass(frozen=True)\nclass MirrorSnapshot:",
        "@dataclass\nclass MirrorSnapshot:",
    )
    result = _run(home)
    _red(
        result,
        site_contains="MirrorSnapshot",
        why_contains="a MUTABLE value type on the consumer side",
    )


@pytest.mark.parametrize(
    "verb",
    ["publish", "write_balance", "set_version", "update", "take", "commit_row"],
)
def test_a_MUTATING_verb_on_a_consumer_port_reddens(home: Path, verb: str) -> None:
    """One plant per mutation stem the gate claims to catch.

    Parametrized because a stem list is exactly the kind of declaration that
    rots: a misspelled entry matches nothing and the arm goes quiet without
    changing its verdict on the clean tree.
    """
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "    def snapshot(self) -> MirrorSnapshot:",
        f"    def {verb}(self, value: object) -> None:\n"
        f'        """Planted mutating verb."""\n\n'
        "    def snapshot(self) -> MirrorSnapshot:",
    )
    result = _run(home)
    _red(
        result,
        site_contains=f"MirrorPort.{verb}",
        why_contains="declares the mutating verb",
    )


def test_a_CHANGED_correlation_bucket_reddens_against_the_frozen_spec(
    home: Path,
) -> None:
    """§7's buckets are the spec's; the seam does not get a vote."""
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        '    "CL": CorrelationBucket.ENERGY,',
        '    "CL": CorrelationBucket.METALS,',
    )
    result = _run(home)
    _red(result, site_contains="BUCKET_OF", why_contains="§7's locked sentence")


def test_a_bucket_the_SPEC_gained_and_the_seam_did_not_reddens(home: Path) -> None:
    """The comparison runs both ways, so the spec is the authority, not the seam."""
    _plant(
        home,
        "docs/nics_risk_subsystem_spec_v1.3.md",
        "rates {ZN} (static;",
        "rates {ZN}, grains {ZC} (static;",
    )
    result = _run(home)
    _red(result, site_contains="BUCKET_OF", why_contains="ZC")


def test_a_MOVED_spec_anchor_is_CANNOT_MEASURE_not_agreement(home: Path) -> None:
    """§7.12/2 — an unmatched anchor yields an EMPTY expected set."""
    _plant(
        home,
        "docs/nics_risk_subsystem_spec_v1.3.md",
        "  - **Buckets:** equities",
        "  - **Groupings:** equities",
    )
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "did not match its anchor" in (result.detail or ""), result.detail
    assert "report agreement" in (result.detail or ""), result.detail


def test_an_ASYNC_verb_reddens(home: Path) -> None:
    """The seam declares every verb synchronous and gives a reason per verb."""
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "    def snapshot(self) -> MirrorSnapshot:",
        "    async def snapshot(self) -> MirrorSnapshot:",
    )
    result = _run(home)
    _red(result, site_contains="snapshot", why_contains="declared `async def`")


def test_BEHAVIOUR_in_the_seam_reddens(home: Path) -> None:
    """A boundary that decides anything is a second authority."""
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "        return self.state is MirrorState.FRESH and self.picture is not None",
        "        if self.state is MirrorState.PARTIAL:\n"
        "            return True\n"
        "        return self.state is MirrorState.FRESH and self.picture is not None",
    )
    result = _run(home)
    _red(result, site_contains="sizeable", why_contains="that is a rule")


def test_the_RANKING_port_declares_no_writer(home: Path) -> None:
    """§6.6: nobody but the Scoring process COMPUTES the score (R5, absent)."""
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "    def available(self) -> bool:",
        "    def publish_row(self, row: RankingRow) -> None:\n"
        '        """Planted writer."""\n\n'
        "    def available(self) -> bool:",
    )
    result = _run(home)
    _red(
        result,
        site_contains="RankingTablePort.publish_row",
        why_contains="the Allocator permissive",
    )


# --------------------------------------------------------------------------
# RESTORE
# --------------------------------------------------------------------------


def test_the_plant_REMOVED_returns_the_same_tree_to_green(home: Path) -> None:
    """A red that does not clear on repair is a broken gate, not a finding."""
    original = (home / "scripts/nixalloc/seam.py").read_text(encoding="utf-8")
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "@dataclass(frozen=True)\nclass MirrorSnapshot:",
        "@dataclass\nclass MirrorSnapshot:",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / "scripts/nixalloc/seam.py").write_text(original, encoding="utf-8")
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail
    assert (home / "scripts/nixalloc/seam.py").read_bytes() == (
        REPO / "scripts/nixalloc/seam.py"
    ).read_bytes()
