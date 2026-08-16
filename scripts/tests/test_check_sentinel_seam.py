"""ARC 034 / 0.6 — the can-fail suite for the Sentinel seam gate.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then one plant
per DECLARED PROPERTY that must FAIL and NAME its site, then the plants removed
and the same population passing. A demonstration missing the last step shows only
that a gate can fail.

**THE BRIEF'S OWN SENTENCE IS THE REQUIREMENT THIS FILE EXISTS TO MEET:** *prove
each seam gate reddens on a change to each declared property — a gate that passes
on a renamed field or a dropped marker field measures nothing.* Both of those
exact cases are here as their own controls
(`test_a_RENAMED_MarkerRecord_FIELD_reddens_and_NAMES_the_field` and
`test_a_DROPPED_MarkerRecord_FIELD_reddens_and_NAMES_the_field`), because ARC
028 measured a seam gate PASSING on a deleted field and ARC 034 / 0.5 measured
declared floors that were arithmetic identities. A frozen declaration nothing can
falsify is documentation.

**No plant touches a production artifact** (doctrine C.8, CHECK-DEBT D3.189).
Every can-fail builds a throwaway `nix_home` under `tmp_path` holding COPIES of
the real seam and the real frozen spec, perturbs the COPY, and drives the SHIPPED
gate's own bytes against it. `scripts/nixsentinel/seam.py` and
`docs/nics_risk_subsystem_spec_v1.3.md` are read and never written — a test that
transiently edits a production module leaves residue indistinguishable from a
real defect when the run is killed.

**Every control asserts the REASON** — a substring of `site` or `detail` naming
WHAT was wrong — never the status alone (check contract v2 §11 / §18).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_sentinel_seam as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: Everything the gate reads, copied into the throwaway tree. The spec is
#: ARM 1's and ARM 2's REFERENCE side; the package `__init__` is a subject the
#: gate refuses without.
_COPIED = (gate.SEAM, gate.PACKAGE_INIT, gate.SPEC)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the real seam and the real spec."""
    (tmp_path / "scripts" / "nixsentinel").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    for rel in _COPIED:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str, *, rel: str | None = None) -> None:
    """Perturb the COPY, asserting the anchor really was there.

    The assertion is the load-bearing half: a plant whose anchor has drifted
    silently mutates nothing, the gate stays green, and the control reports that
    the gate reddens on a change it never saw — a suite measuring itself.
    """
    path = home / (rel or gate.SEAM)
    source = path.read_text(encoding="utf-8")
    assert old in source, f"the plant anchor {old!r} is not in {rel or gate.SEAM}"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real reference side and a real subject
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_compared() -> None:
    """The credibility floor: both sides non-empty, and the figures are reported."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "§12.1 phrases 4" in result.evidence, result.evidence
    assert "MarkerPhase BEFORE, AFTER" in result.evidence, result.evidence
    assert "all synchronous" in result.evidence, result.evidence


def test_the_EXPECTED_SET_is_PARSED_FROM_THE_SPEC_and_is_not_a_constant_here() -> None:
    """If the expected side were hardcoded, editing the spec could not move it."""
    phrases, detail = gate.spec_marker_phrases(REPO)

    assert phrases == ("timestamp", "trigger cause", "symbols", "broker acks"), phrases
    assert "§12.1 names 4" in detail, detail
    assert gate.spec_declares_both_sides(REPO) is True


def test_the_GATE_DECLARES_the_seam_as_a_SUBJECT_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent."""
    assert gate.SEAM in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the frozen spec is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


# --------------------------------------------------------------------------
# THE PLANTS — one per DECLARED PROPERTY. Each must FAIL and NAME the reason.
# --------------------------------------------------------------------------


def test_a_DROPPED_MarkerRecord_FIELD_reddens_and_NAMES_the_field(home: Path) -> None:
    """§12.1 enumerates `broker acks`; a record without them cannot be replayed.

    ARC 028's measured blind spot, in this seam: a seam gate PASSED on a deleted
    field. `acks` is the field whose absence hurts most — a refused close and a
    completed one become indistinguishable, which is exactly the difference
    between "the account is flat" and "the venue said no".
    """
    _plant(home, "    acks: tuple[BrokerAck, ...]\n", "")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "MarkerRecord" in result.site, result.site
    assert "'broker acks'" in result.detail, result.detail
    assert "no 'acks' field" in result.detail, result.detail


def test_a_RENAMED_MarkerRecord_FIELD_reddens_and_NAMES_the_field(home: Path) -> None:
    """THE BRIEF'S NAMED FAILURE MODE: *a gate that passes on a renamed field
    measures nothing.*

    `ts` -> `timestamp_utc` is the renaming that looks most like an improvement
    and is the one a reviewer is least likely to stop: nothing fails to import,
    the record still carries a time, and §12.1's enumerated `timestamp` is still
    conceptually present. The gate must still redden, because the field NAME is
    what a cold-start replayer reads.
    """
    _plant(
        home,
        "    ts: float\n    cause: TriggerCause",
        "    timestamp_utc: float\n    cause: TriggerCause",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "MarkerRecord" in result.site, result.site
    assert "'timestamp'" in result.detail, result.detail
    assert "no 'ts' field" in result.detail, result.detail


def test_a_REMOVED_MarkerPhase_MEMBER_reddens_and_NAMES_BEFORE(home: Path) -> None:
    """§12.1 writes the marker *before and after* acting. One side is not both.

    Without `BEFORE` a mid-flatten death is indistinguishable from a Sentinel
    that never woke, and cold-start would reconcile a partially flattened account
    against an event log that never heard of the attempt.
    """
    _plant(home, '    BEFORE = "before"\n', "")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "MarkerPhase" in result.site, result.site
    assert "'BEFORE'" in result.detail, result.detail
    assert "before AND after acting" in result.detail, result.detail


def test_an_ASYNC_VERB_reddens_and_NAMES_the_verb_and_the_DIVERGENCE(
    home: Path,
) -> None:
    """Every verb in this seam is SYNCHRONOUS as a reasoned divergence from §2A.

    An `async def` here would require the Sentinel process to host an asyncio
    loop in the exact scenario that already killed the Risk Engine. Reversing
    that ruling silently is what this arm refuses.
    """
    _plant(
        home,
        "    def append(self, record: MarkerRecord) -> None:",
        "    async def append(self, record: MarkerRecord) -> None:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    # NAMED IN `detail`, NOT IN `site`, and that asymmetry is recorded rather
    # than papered over: ARM 5 and ARM 6 build `SEAM:Port.verb` sites, while
    # ARM 4 builds `SEAM:lineno` and puts the verb in the reason. Asserting
    # `site + detail` is the honest reading of "the verdict names the verb";
    # tightening ARM 4's site to match its siblings is an edit to a gate this
    # phase froze, so it is reported and not made here.
    assert "append" in result.site + result.detail, (result.site, result.detail)
    assert "is `async def`" in result.detail, result.detail
    assert "no event loop" in result.detail, result.detail


def test_an_ORDER_PLACING_VERB_on_the_broker_port_reddens_and_NAMES_S14(
    home: Path,
) -> None:
    """§14's authority boundary, expressed as a type and held as a property.

    The Sentinel may observe exposure and close it. A `place_order` verb makes it
    a SECOND trading authority, and §14 permits exactly one exception to
    Limiter-only execution — an emergency FLATTEN when the Limiter is dead.
    """
    _plant(
        home,
        '        """Establish this process\'s own session. Raises if it cannot."""\n',
        '        """Establish this process\'s own session. Raises if it cannot."""\n'
        "\n"
        "    def place_order(self, symbol: str, size: int) -> None:\n"
        '        """A second trading authority. Not authorised."""\n',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SentinelBrokerPort.place_order" in result.site, result.site
    assert "'place'" in result.detail, result.detail
    assert "§14 permits the Sentinel ONE" in result.detail, result.detail


def test_an_UNAUTHORISED_BUT_UNBANNED_VERB_still_reddens(home: Path) -> None:
    """The half a stem list cannot reach, and the reason the roster is closed.

    `query_account` contains no banned stem — it does not open, size, amend or
    route anything, and a reader could argue it is harmless. It is still a
    WIDENED SESSION PORT, and a widened session is a widened authority whatever
    it is called. Without this control the boundary would be exactly as strong as
    the imagination of whoever wrote the stem list.
    """
    _plant(
        home,
        '        """Establish this process\'s own session. Raises if it cannot."""\n',
        '        """Establish this process\'s own session. Raises if it cannot."""\n'
        "\n"
        "    def query_account(self) -> float:\n"
        '        """Not one of the four §12.1 authorises."""\n',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SentinelBrokerPort.query_account" in result.site, result.site
    assert "not one of the four" in result.detail, result.detail


def test_a_RENAMED_BROKER_PORT_reddens_because_the_BOUNDARY_IS_UNHELD(
    home: Path,
) -> None:
    """A port that vanished must not read as a boundary with nothing crossing it.

    RENAMED rather than deleted, deliberately: deleting the class takes four
    verbs with it and the run falls below `MIN_DECLARED_VERBS`, so the verdict
    would be CANNOT_MEASURE about a floor and would name no port. Renaming keeps
    every count intact and isolates the property — ARM 5's subject is gone while
    the seam is otherwise the same size.
    """
    _plant(
        home,
        "class SentinelBrokerPort(Protocol):",
        "class _RetiredSentinelBrokerPort(Protocol):",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SentinelBrokerPort is not declared" in result.detail, result.detail
    assert "nothing holding the boundary" in result.detail, result.detail


def test_BEHAVIOUR_INSIDE_A_PORT_METHOD_reddens_and_NAMES_the_verb(
    home: Path,
) -> None:
    """The other half of ARM 3, and the half an import ban cannot reach.

    A statement in a `Protocol` method body needs no forbidden import and calls
    no forbidden builtin — `self._path.unlink()` is ordinary Python. It is still
    behaviour, and behaviour in a seam is how a declaration becomes a second
    authority that can silently disagree with the spec.
    """
    _plant(
        home,
        '        """Retire the replayed marker. Called only after the rows are '
        'booked."""\n',
        '        """Retire the replayed marker. Called only after the rows are '
        'booked."""\n        self._path.unlink()\n',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "archive" in result.site + result.detail, (result.site, result.detail)
    assert "behaviour, not a declaration" in result.detail, result.detail


def test_a_REWINDING_WRITER_VERB_reddens_and_NAMES_the_BEFORE_record(
    home: Path,
) -> None:
    """Append-only is a DECLARED property, not an implementation habit.

    A writer that can rewind could erase a `BEFORE` record on its way to dying,
    which is precisely the evidence §12.1's fix exists to keep. Directive 6 one
    layer up: append history, never rewrite banked evidence.
    """
    _plant(
        home,
        "    def append(self, record: MarkerRecord) -> None:\n",
        '    def truncate(self) -> None:\n        """Not append-only."""\n\n'
        "    def append(self, record: MarkerRecord) -> None:\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "MarkerWriterPort.truncate" in result.site, result.site
    assert "'truncate'" in result.detail, result.detail
    assert "erase a BEFORE record" in result.detail, result.detail


def test_BEHAVIOUR_IN_THE_SEAM_reddens_and_NAMES_THE_MODULE(home: Path) -> None:
    """An import is enough: a seam declares shape and touches nothing.

    Behaviour in a seam is how a declaration becomes a second authority that can
    silently disagree with the spec.
    """
    _plant(home, "import enum\n", "import enum\nimport os\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "imports os" in result.detail, result.detail
    assert "does not act" in result.detail, result.detail


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent reference side is not agreement
# --------------------------------------------------------------------------


def test_a_RENAMED_SPEC_SENTENCE_is_CANNOT_MEASURE_and_NEVER_a_PASS(
    home: Path,
) -> None:
    """The floor working, and it is the vacuity that would matter most.

    ARM 1's expected side is PARSED out of §12.1's own sentence. Rename that
    sentence and the expected set is empty — and an empty expected set agrees
    with every possible `MarkerRecord`, including one with no fields at all. The
    gate must refuse rather than report that emptiness as agreement.
    """
    _plant(
        home,
        "append-only marker file",
        "append-only breadcrumb file",
        rel=gate.SPEC,
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "contents parenthetical yielded 0 phrase(s)" in result.detail, result.detail
    assert f"below the floor of {gate.MIN_SPEC_PHRASES}" in result.detail, result.detail
    assert result.site == "", (
        "a CANNOT_MEASURE carrying a site would mean the gate observed a defect "
        "and reported that it observed nothing"
    )


def test_an_ABSENT_SEAM_is_CANNOT_MEASURE_and_names_the_missing_path(
    home: Path,
) -> None:
    """A gate whose subject is gone measured nothing (§17)."""
    (home / gate.SEAM).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.SEAM in result.detail, result.detail
    assert "unreadable" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_UNPLANTED_COPY_is_GREEN_so_every_RED_above_is_the_PLANT(
    home: Path,
) -> None:
    """The control without which every red above could be an artefact.

    A scratch tree assembled by this fixture could redden the gate all by itself
    — a missing file, a mangled copy, a path the gate resolves differently — and
    then every plant above would be measuring the harness rather than the
    mutation. This is the same copied tree, unmutated.
    """
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "9 callables" in result.evidence, result.evidence
