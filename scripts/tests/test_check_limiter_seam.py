"""ARC 028 / 0.6 — the standing gate over the frozen Limiter seam.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then plants
that must FAIL and NAME their site, then the plants removed and the same
population passing. A demonstration missing the last step shows only that a gate
can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds a
throwaway `nix_home` under `tmp_path` holding a COPY of the real seam and the
real frozen spec, perturbs the copy, and drives the SHIPPED gate against it. The
real `scripts/nixrisk/seam.py` and the frozen spec are read and never written.

**Every control asserts the REASON** — the site and the named condition — never
the exit code alone (check contract v2 §11).
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

import check_limiter_seam as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of the real seam and the real spec."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    shutil.copy(REPO / gate.SEAM, tmp_path / gate.SEAM)
    shutil.copy(REPO / gate.SPEC, tmp_path / gate.SPEC)
    # ARC 029 / 0.4: the roster has two sources now, so the fixture carries both.
    shutil.copy(REPO / gate.AMENDMENTS, tmp_path / gate.AMENDMENTS)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _seam(home: Path) -> Path:
    return home / gate.SEAM


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real reference side and a real subject
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_compared() -> None:
    """The credibility floor: both sides non-empty, and the count is in evidence."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "§3 release paths 6 == TerminalPath members 6" in result.evidence, (
        result.evidence
    )
    assert "callable(s) classified" in result.evidence, result.evidence


def test_the_EXPECTED_SET_is_PARSED_FROM_THE_SPEC_and_is_not_a_constant_here() -> None:
    """If the expected set were hardcoded, editing the spec could not move it."""
    parsed, complaint = gate.spec_terminal_paths(REPO)

    assert complaint == "", complaint
    assert parsed == {
        "FILL",
        "CANCEL",
        "REJECT",
        "PENDING_TIMEOUT",
        "BLACKOUT_ONSET",
        # SPEC-A7 (ARC 029 / 0.4). Present because a RULING put it in the
        # effective roster, which is the frozen sentence unioned with
        # SPEC-AMENDMENTS.md -- not because the seam declares it.
        "HALT_ONSET",
    }, f"§3 parsed to {sorted(parsed)}"
    source = Path(gate.__file__).read_text(encoding="utf-8")
    for member in sorted(parsed):
        assert f'"{member}"' not in source, (
            f"{member} appears as a literal in the gate's own source — the "
            "expected side would then be a constant, and the comparison would be "
            "the gate agreeing with itself"
        )


# --------------------------------------------------------------------------
# THE PLANTS — each must FAIL, and NAME the site and the condition
# --------------------------------------------------------------------------


def test_an_ENUM_MEMBER_THE_SPEC_DOES_NOT_NAME_fails_and_says_it_is_a_SPEC_FINDING(
    home: Path,
) -> None:
    """B2's circularity guard, mechanised: the code may not extend the path set."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            '    FILL = "fill"',
            '    FILL = "fill"\n    EXPIRY_SWEEP = "expiry_sweep"',
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "TerminalPath.EXPIRY_SWEEP" in result.site, result.site
    assert "FINDING ABOUT THE SPEC" in result.detail, result.detail


def test_a_SPEC_PATH_THE_SEAM_DROPS_fails_and_NAMES_the_missing_member(
    home: Path,
) -> None:
    """The other direction: a release path the ledger could never report."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            '    BLACKOUT_ONSET = "blackout_onset"\n', ""
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "BLACKOUT_ONSET" in result.detail, result.detail
    assert "the seam does not" in result.detail, result.detail


def test_BEHAVIOUR_IN_THE_SEAM_fails_and_NAMES_THE_LINE_it_is_on(
    home: Path,
) -> None:
    """The second-authority failure mode, caught at the point it starts."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8")
        + (
            "\n\ndef deployable_after(picture: FinancialPicture) -> float:\n"
            '    """A rule. This does not belong in a declaration."""\n'
            "    total = 0.0\n"
            "    for row in picture.positions:\n"
            "        total += row.margin\n"
            "    return picture.balance - total\n"
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "deployable_after" in result.site, result.site
    assert "statements after the docstring" in result.detail, result.detail


def test_a_SEAM_THAT_REACHES_THE_WORLD_fails_and_NAMES_THE_MODULE(
    home: Path,
) -> None:
    """An import is enough: the seam declares shape and touches nothing."""
    seam = _seam(home)
    seam.write_text(
        "import socket\n" + seam.read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "imports socket" in result.detail, result.detail


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent side is not agreement
# --------------------------------------------------------------------------


def test_a_SPEC_WHOSE_SENTENCE_MOVED_is_CANNOT_MEASURE_and_NEVER_a_PASS(
    home: Path,
) -> None:
    """§5.3: an empty scope is never a PASS. The gate must say it lost its side."""
    spec = home / gate.SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("released on:", "freed upon:"),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "no 'released on:' sentence" in result.detail, result.detail
    assert "empty expected set would compare green" in result.detail, result.detail


def test_an_ABSENT_SEAM_is_CANNOT_MEASURE_and_names_the_missing_path(
    home: Path,
) -> None:
    """A gate whose subject is gone measured nothing (§17)."""
    _seam(home).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.SEAM in result.detail, result.detail


def test_a_SEAM_WITH_NO_TerminalPath_is_CANNOT_MEASURE_not_a_silent_agreement(
    home: Path,
) -> None:
    """Both sides must exist. A missing measured side is not an empty diff."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            "class TerminalPath(enum.Enum):", "class _RetiredTerminalPath(enum.Enum):"
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "the measured side is absent" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_SAME_COPIED_TREE_passes_once_every_plant_is_gone(home: Path) -> None:
    """Without this the gate is only known to be able to fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "0 carrying behaviour" in result.evidence, result.evidence


def test_the_GATE_DECLARES_the_seam_as_a_SUBJECT_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent."""
    assert gate.SEAM in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the frozen spec is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


# --------------------------------------------------------------------------
# ARM 3 — the sync/async DECLARATION, added because it was REFUTED
#
# ARC 028's sub-agent B measured these very bytes and found them silent: all
# four `ReservationLedgerPort` verbs rewritten `def` -> `async def` PASSED with
# empty detail, and a deleted `ProposedOrder` field PASSED. The seam's
# most-argued property was guarded by prose. These controls are the repair, and
# they are written as plants rather than as an assertion about the gate's source.
# --------------------------------------------------------------------------


def test_an_ASYNC_GATE_VERB_fails_and_NAMES_the_verb_and_the_RACE(
    home: Path,
) -> None:
    """The refuted case, verbatim: the ledger's verbs made awaitable."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            "    def take(self, order: ProposedOrder, now: float) -> Reservation:",
            "    async def take(self, order: ProposedOrder, now: float) -> Reservation:",
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ReservationLedgerPort.take" in result.site, result.site
    assert "`async def` while the seam DECLARES it synchronous" in result.detail, (
        result.detail
    )
    assert "fill-vs-tick race" in result.detail, result.detail


def test_a_VERB_THE_DECLARATION_NAMES_AND_THE_CODE_DROPS_fails(home: Path) -> None:
    """A declaration governing a verb nothing has is a declaration about nothing."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            "    def publish(self, picture: FinancialPicture) -> None:",
            "    def emit(self, picture: FinancialPicture) -> None:",
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "FinancialPicturePort.publish" in result.site, result.site
    assert "absent from the class" in result.detail, result.detail


def test_a_PORT_THE_DECLARATION_NAMES_AND_THE_SEAM_DROPS_is_named(home: Path) -> None:
    """Deleting a whole port must not read as universal agreement."""
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            "class Plane1Port(Protocol):", "class _RetiredPlane1Port(Protocol):"
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "Plane1Port" in result.site, result.site
    assert "NOT DEFINED" in result.detail, result.detail


def test_the_DECLARATION_SECTION_GOING_MISSING_is_CANNOT_MEASURE(home: Path) -> None:
    """§5.3 again: a reference side that vanished is not universal agreement.

    Without this floor, deleting the docstring's declaration section would make
    every verb unnamed, the comparison empty, and the gate green — the exact
    shape ARM 1's spec-sentence floor exists to prevent, one layer over.
    """
    seam = _seam(home)
    text = seam.read_text(encoding="utf-8")
    body = text.split('"""', 2)[2]
    seam.write_text('"""The seam."""\n' + body, encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "sync/async declaration reached only" in result.detail, result.detail
    assert result.site == "", (
        "a CANNOT_MEASURE carrying a site would mean the gate observed a defect "
        "and reported that it observed nothing"
    )


def test_a_BARE_NAMED_PORT_the_seam_drops_is_ALSO_named_not_just_counted(
    home: Path,
) -> None:
    """The other half of the same hole, and it bit the first repair.

    `ReservationLedgerPort` is named in the declaration WITHOUT a verb, while
    `Plane1Port` is named only as `Plane1Port.enqueue`. Two spellings, two code
    paths, and the first repair suppressed this one — deleting the ledger port
    fell through to a CANNOT_MEASURE about the floor that named no port at all.
    A gate that knows which port vanished must say which port vanished.
    """
    seam = _seam(home)
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            "class ReservationLedgerPort(Protocol):",
            "class _RetiredLedgerPort(Protocol):",
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ReservationLedgerPort" in result.site, result.site
    assert "NOT DEFINED" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARC 029 / 0.4 — SPEC-A7, and the mechanism that had to exist to obey it.
#
# The frozen spec is never edited. So a ruling that ADDS a terminal path had
# nowhere to be seen from: `spec_terminal_paths` read the frozen document and
# nothing else, which put SPEC-A7's `HALT_ONSET` in an impossible position —
# adding the member reddens ARM 1 as "declared but NOT named by §3" forever, and
# the only way to green it would be to edit the document the rule protects.
#
# The reference side is now the EFFECTIVE roster: frozen sentence UNION ledger
# additions. These controls pin both halves and both failure directions.
# --------------------------------------------------------------------------


def test_the_AMENDED_PATH_IS_NOT_IN_THE_FROZEN_SENTENCE(home: Path) -> None:
    """The premise, asserted rather than assumed.

    If `HALT_ONSET` were somehow already in §3's sentence, every control below
    would pass without the union existing at all — the union would be decoration
    and this suite would be proving nothing about it.
    """
    frozen = (home / gate.SPEC).read_text(encoding="utf-8")
    match = gate._RELEASE_SENTENCE.search(frozen)  # pylint: disable=protected-access
    assert match is not None
    assert "halt" not in match.group("paths").lower(), match.group("paths")


def test_the_EFFECTIVE_ROSTER_IS_THE_UNION_OF_BOTH_SOURCES(home: Path) -> None:
    """SPEC-A7's member arrives from the LEDGER, not from the frozen spec."""
    amended, complaint = gate.amended_terminal_paths(home)
    assert complaint == "", complaint
    assert "HALT_ONSET" in amended

    effective, complaint = gate.spec_terminal_paths(home)
    assert complaint == "", complaint
    assert amended <= effective, (amended, effective)
    assert "BLACKOUT_ONSET" in effective, "the frozen half of the union went missing"


def test_WITHOUT_THE_RULING_the_member_is_an_UNSPECCED_PATH(home: Path) -> None:
    """The ordering the brief required, driven in reverse.

    Strip the ruling and the seam's `HALT_ONSET` becomes exactly what ARC 028
    refused to create: a member the spec does not name. The gate must say so in
    those words, because B2's rule is that such a member is a FINDING ABOUT THE
    SPEC and never a quiet addition to make a sweep green.
    """
    ledger = home / gate.AMENDMENTS
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "| terminal-path additions | `HALT_ONSET` |", ""
        ),
        encoding="utf-8",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "HALT_ONSET" in result.detail, result.detail
    assert "FINDING ABOUT THE SPEC" in result.detail, result.detail


def test_a_MALFORMED_additions_row_is_a_COMPLAINT_not_an_empty_set(home: Path) -> None:
    """An amendment nobody can parse must not read as one that adds nothing.

    This is the vacuity that would matter most: a ruling lands, its row is
    mistyped, the gate silently derives the OLD roster and reports green over a
    seam that is now missing a path the architect required.
    """
    ledger = home / gate.AMENDMENTS
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "| terminal-path additions | `HALT_ONSET` |",
            "| terminal-path additions | HALT_ONSET |",
        ),
        encoding="utf-8",
    )
    _, complaint = gate.amended_terminal_paths(home)
    assert "names no member in backticks" in complaint, complaint
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result


def test_an_ABSENT_LEDGER_is_CANNOT_MEASURE_never_a_PASS(home: Path) -> None:
    """Half a roster compares green against the wrong set, not against no set."""
    (home / gate.AMENDMENTS).unlink()
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "SPEC-AMENDMENTS" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARC 029 / 0.6 — THE EXIT SEAM, and one plant per DECLARED PROPERTY.
#
# The brief required this explicitly, because ARC 028 measured the gap: that
# arc's seam gate PASSED on all four ledger verbs rewritten `async def` and on a
# DELETED FIELD. A frozen declaration nothing can falsify is documentation.
#
# Every case below mutates the seam in the copied tree and asserts the gate goes
# red naming the thing that moved. A property with no row here is a property this
# gate does not actually hold.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        # ARM 4 — the §3 exit-trigger set, both directions.
        ('    ORPHAN = "orphan"\n', "", "ORPHAN"),
        (
            '    SENTINEL = "sentinel"\n',
            '    SENTINEL = "sentinel"\n    INVENTED = "invented"\n',
            "INVENTED",
        ),
        # ARM 5 — a required field deleted. ARC 028's exact blind spot.
        ("    net_liq: float\n", "", "net_liq"),
        ("    cash: float\n", "", "cash"),
        ("    initial_distance_ticks: int\n", "", "initial_distance_ticks"),
        ("    trail_distance_ticks: int\n", "", "trail_distance_ticks"),
        ("    anchor: float\n", "", "anchor"),
        ("    activated: bool\n", "", "activated"),
        (
            (
                "    positions: tuple[PositionRow, ...]\n    balance: float\n"
                "    polled_at: float\n"
            ),
            "    balance: float\n    polled_at: float\n",
            "positions",
        ),
        (
            "    balance: float\n    polled_at: float\n",
            "    polled_at: float\n",
            "balance",
        ),
        # ARM 5 over the PRE-EXISTING atomic snapshot — §3 enumerates these, and
        # until 0.6 deleting one was silent.
        ("    sum_open_margin: float\n", "", "sum_open_margin"),
        ("    sum_reservations: float\n", "", "sum_reservations"),
        ("    deployable: float\n", "", "deployable"),
        # ARM 3 — an exit-path verb rewritten asynchronous, one per new port.
        (
            "    def maintain(self, symbol: str, price: float)",
            "    async def maintain(self, symbol: str, price: float)",
            "maintain",
        ),
        (
            "    def read(self) -> SurvivalReading:",
            "    async def read(self) -> SurvivalReading:",
            "read",
        ),
        (
            "    def query_truth(self) -> BrokerTruth:",
            "    async def query_truth(self) -> BrokerTruth:",
            "query_truth",
        ),
        (
            "    def registration_admitted(self) -> bool:",
            "    async def registration_admitted(self) -> bool:",
            "registration_admitted",
        ),
    ],
    ids=[
        "trigger-deleted",
        "trigger-unspecced",
        "field-net_liq",
        "field-cash",
        "field-initial_distance",
        "field-trail_distance",
        "field-anchor",
        "field-activated",
        "field-positions",
        "field-balance",
        "picture-sum_open_margin",
        "picture-sum_reservations",
        "picture-deployable",
        "async-StopBookPort.maintain",
        "async-SurvivalWatchPort.read",
        "async-ColdStartPort.query_truth",
        "async-ColdStartPort.registration_admitted",
    ],
)
def test_EVERY_DECLARED_EXIT_PROPERTY_reddens_the_gate(
    home: Path, old: str, new: str, expected: str
) -> None:
    """One plant per declared property; each must be NAMED in the verdict.

    Naming matters as much as reddening: a gate that says "something changed"
    sends a reader to diff a 700-line file, and the value of this instrument is
    that it says WHICH member, WHICH field, WHICH verb (doctrine C.2).
    """
    seam = _seam(home)
    source = seam.read_text(encoding="utf-8")
    assert old in source, f"the plant anchor {old!r} is not in the seam"
    seam.write_text(source.replace(old, new, 1), encoding="utf-8")

    result = _run(home)

    assert result.status is not Status.PASS, (
        f"the seam gate PASSED with {expected} changed — this declared property "
        "is not held by any arm, which is ARC 028's finding recurring"
    )
    assert expected in (result.site + result.detail), (
        f"the gate reddened without naming {expected}: {result.site} {result.detail}"
    )


def test_the_UNPLANTED_copy_is_GREEN_so_the_matrix_measures_the_plants(
    home: Path,
) -> None:
    """The control for the matrix above: the same tree, unmutated, passes.

    Without it every row could be reddening on something the copy does to the
    tree rather than on the plant — the matrix would be measuring the fixture.
    """
    assert _run(home).status is Status.PASS, _run(home)
