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

import importlib.util
import shutil
import subprocess
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

GATE_REL = "checks/check_allocator_seam.py"
ALLOC_SEAM = "scripts/nixalloc/seam.py"
RISK_SEAM = "scripts/nixrisk/seam.py"

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
        'SEAM_REV = "1.1.0"',
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


# --------------------------------------------------------------------------
# ARC 032 / 0.4 — THE GATE MUST REDDEN ON THE WIDENING ITSELF
#
# The brief's instruction, quoted so the tests below can be read against it:
# "PROVE the seam gate reddens on the widening itself — a renamed or dropped
#  stop_distance must redden it, and MIRRORED_FIELDS must be PINNED to a
#  literal at SEAM_REV, not derived from the dataclass (the derivation is what
#  made ARC 031's first seam gate pass on eight of nine renames)."
#
# MEASURED CORRECTION, and it is why these tests exist as a separate block:
# `MIRRORED_FIELDS` pins `FinancialPicture`'s fields. `stop_distance` is a
# field of `PositionRow` — one level down, inside the `positions` tuple.
# Adding the name to `MIRRORED_FIELDS` would make that tuple disagree with
# `dataclasses.fields(FinancialPicture)` and redden ARM 2 immediately. The pin
# the invariant actually needs is `POSITION_ROW_FIELDS`, which did not exist
# before this arc, because **nothing in this tree pinned the published row's
# schema at all**. The vacuity test below proves that claim rather than
# asserting it: it drives the gate's own bytes at the PRE-WIDENING seam and
# shows a renamed row field passing.
# --------------------------------------------------------------------------


def _row_slice(home: Path) -> tuple[str, int, int]:
    """`(whole file, start, end)` of the Limiter's `PositionRow` block."""
    text = (home / "scripts/nixrisk/seam.py").read_text(encoding="utf-8")
    start = text.index("@dataclass(frozen=True)\nclass PositionRow:")
    end = text.index("@dataclass(frozen=True)\nclass FinancialPicture:", start)
    return text, start, end


def _rename_row_field(home: Path, field: str) -> None:
    """Rename ONE declared field, inside the `PositionRow` block only."""
    text, start, end = _row_slice(home)
    block = text[start:end]
    anchor = f"\n    {field}: "
    assert block.count(anchor) == 1, (
        f"{field!r} appears {block.count(anchor)} times in the PositionRow "
        "block, not once"
    )
    patched = block.replace(anchor, f"\n    {field}_renamed: ")
    (home / "scripts/nixrisk/seam.py").write_text(
        text[:start] + patched + text[end:], encoding="utf-8"
    )


def test_EVERY_published_ROW_field_renamed_in_turn_reddens(tmp_path: Path) -> None:
    """One plant per pinned row field, enumerated from the seam's own literal.

    Enumerated and not sampled, for the reason ARC 031 measured on the picture:
    a gate proven on one field says nothing about the other six, and the field
    a later arc adds must be covered without anyone remembering to add a test.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    from nixalloc import seam  # pylint: disable=import-outside-toplevel

    fields = seam.POSITION_ROW_FIELDS
    assert "stop_distance" in fields, (
        f"the pin does not carry the field this arc added: {fields}"
    )
    assert len(fields) >= 7, f"the published row shrank unexpectedly: {fields}"

    for index, field in enumerate(fields):
        home = tmp_path / f"row_{index}"
        for rel in COPIED:
            target = home / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, target)
        _rename_row_field(home, field)
        result = _run(home)
        assert result.status is Status.FAIL_NEEDS_OPERATOR, (
            f"renaming published ROW field {field!r} left the seam gate GREEN — "
            f"the gate measures nothing about it: {result}"
        )
        assert field in (result.detail or ""), (
            f"the finding does not name the renamed field {field!r}: {result.detail}"
        )


def test_RENAMING_stop_distance_reddens_naming_the_FAIL_OPEN(home: Path) -> None:
    """The field this arc added, with its own finding and its own reason.

    Renaming it is caught twice and the two findings say different things: the
    schema pin says "the row moved", and `STOP_DISTANCE_FIELD` says "the thing
    that closed D3.136 is gone". Only the second is actionable, which is why it
    is a separate finding rather than one element of a set difference — the
    same argument `VERSION_FIELD` already carries one level up.
    """
    _rename_row_field(home, "stop_distance")
    result = _run(home)
    _red(
        result,
        site_contains="STOP_DISTANCE_FIELD",
        why_contains="FAIL OPEN",
    )
    assert "POSITION_ROW_FIELDS" in (result.site or ""), result.site
    assert "an emptier bucket ADMITS more" in (result.detail or ""), result.detail


def test_DROPPING_stop_distance_from_the_row_reddens(home: Path) -> None:
    """Dropped, not renamed — the case a rename-only suite would miss."""
    text, start, end = _row_slice(home)
    block = text[start:end]
    anchor = "    stop_distance: int\n"
    assert block.count(anchor) == 1, block
    (home / "scripts/nixrisk/seam.py").write_text(
        text[:start] + block.replace(anchor, "") + text[end:], encoding="utf-8"
    )
    result = _run(home)
    _red(result, site_contains="STOP_DISTANCE_FIELD", why_contains="FAIL OPEN")


def test_DROPPING_stop_distance_from_the_PIN_reddens_too(home: Path) -> None:
    """The other direction: the row keeps it, the contract forgets it.

    A pin is a two-sided claim. A suite that only ever perturbs the dataclass
    proves the gate notices the producer moving and says nothing about a
    consumer quietly narrowing what it promises to carry.
    """
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "    #: ARC 032, `SEAM_REV 1.1.0`, `SPEC-A9`. §7:501's exposure unit, for the\n"
        "    #: positions already held.\n"
        '    "stop_distance",\n',
        "",
    )
    result = _run(home)
    _red(
        result,
        site_contains="POSITION_ROW_FIELDS",
        why_contains="does not match the Limiter's own PositionRow",
    )
    assert "missing=['stop_distance']" in (result.detail or ""), result.detail


def test_the_PIN_IS_A_LITERAL_and_a_DERIVATION_would_have_passed(home: Path) -> None:
    """THE VACUITY CONTROL, and it is the reason the pin is spelled out.

    ARC 031's first `MIRRORED_FIELDS` was DERIVED from `dataclasses.fields()`,
    and its can-fail renamed each published field in turn: the gate stayed
    GREEN on eight of nine, because the derivation moved with the rename. This
    plants that exact mistake on THIS arm — it replaces the literal pin with
    the derivation — and asserts the gate then passes on a renamed row field.

    A test that asserts the CORRECT thing reddens proves the arm works. This
    one proves the arm would NOT have worked if it had been written the
    plausible way, which is the claim that is actually in doubt.
    """
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "import enum\n",
        "import dataclasses as _dc\nimport enum\n",
    )
    _plant(
        home,
        "scripts/nixalloc/seam.py",
        "POSITION_ROW_FIELDS: tuple[str, ...] = (",
        "POSITION_ROW_FIELDS: tuple[str, ...] = tuple(\n"
        "    _f.name for _f in _dc.fields(PositionRow)\n"
        ") or (",
    )
    _rename_row_field(home, "margin")
    result = _run(home)
    assert result.status is Status.PASS, (
        "the derived pin was supposed to move with the rename and pass — if it "
        f"reddens, this control is no longer measuring what it names: {result}"
    )


def test_the_PRE_WIDENING_GATE_was_BLIND_to_the_row(tmp_path: Path) -> None:
    """The claim in the arm's own docstring, DRIVEN against the real old bytes.

    "Renaming `PositionRow.margin` changed the published wire and left every
    seam gate green" is a statement about the gate this project shipped before
    ARC 032, so it is measured against **that gate's actual bytes**, checked
    out of git at the arc's base revision — not by mutilating today's gate
    until it looks blind, which would measure the mutilation.

    A first draft did exactly that (deleted the pin from a COPY of today's
    seam) and it FAILED, correctly: with the pin gone the literal reads `()`,
    the comparison is `() != (seven fields)`, and the arm still reddens naming
    the renamed field. Removing a gate's input does not reproduce a gate that
    never had one. Recorded because the failed draft is the more instructive
    half.
    """
    base = _base_revision()
    if base is None:
        pytest.skip("no pre-widening revision on this branch to compare against")
        return
    old_gate_src, old_alloc_seam, old_risk_seam = base

    home = tmp_path / "pre"
    for rel in COPIED:
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    (home / "scripts/nixalloc/seam.py").write_text(old_alloc_seam, encoding="utf-8")
    (home / "scripts/nixrisk/seam.py").write_text(old_risk_seam, encoding="utf-8")

    old_gate_path = tmp_path / "old_check_allocator_seam.py"
    old_gate_path.write_text(old_gate_src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_old_seam_gate", old_gate_path)
    assert spec is not None and spec.loader is not None
    old_gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_gate)

    clean = old_gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert clean.status is Status.PASS, (
        f"the pre-widening gate does not pass on its own pristine seam, so this "
        f"control has no baseline to measure against: {clean}"
    )

    _rename_row_field(home, "margin")
    dirty = old_gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert dirty.status is Status.PASS, (
        "the pre-widening gate DID see a renamed PositionRow field — then the "
        "ARC 032 arm is a duplicate instrument (doctrine C.9), not new "
        f"coverage, and this arc's premise is wrong: {dirty}"
    )


def _base_revision() -> tuple[str, str, str] | None:
    """`(old gate, old allocator seam, old limiter seam)` at the pre-widening rev.

    Resolved by walking this file's own history for the commit that introduced
    `POSITION_ROW_FIELDS` and taking its parent — never a hard-coded sha, which
    is the moving anchor doctrine C.4 forbids. `gitenv.scrubbed_env` per D3.22:
    `pre-commit` exports `GIT_INDEX_FILE`/`GIT_DIR` into every hook it runs, so
    a bare `subprocess.run(["git", ...])` here would answer about whatever
    started the hook.
    """
    from nixverify.gitenv import scrubbed_env  # pylint: disable=import-outside-toplevel

    env = scrubbed_env()

    def git(*args: str) -> str | None:
        done = subprocess.run(  # nosec B603 B607 - fixed argv, repo-local paths
            ["git", "-C", str(REPO), *args],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        return done.stdout if done.returncode == 0 else None

    log = git("log", "--format=%H", "-S", "POSITION_ROW_FIELDS", "--", ALLOC_SEAM)
    if not log:
        return None
    introduced = log.split()[-1]
    parent = git("rev-parse", f"{introduced}^")
    if not parent:
        return None
    base = parent.strip()
    sources = [
        git("show", f"{base}:{rel}") for rel in (GATE_REL, ALLOC_SEAM, RISK_SEAM)
    ]
    if any(source is None for source in sources):
        return None
    return sources[0], sources[1], sources[2]  # type: ignore[return-value]


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
        'SEAM_REV = "1.1.0"',
        f'{duplicate}\n\nSEAM_REV = "1.1.0"',
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
