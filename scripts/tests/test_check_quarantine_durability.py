"""ARC 037 / sub-agent C — the can-fail suite for
`checks/check_quarantine_durability.py`.

Structure follows the `check_supervision` / `check_flatten` precedent
(`nix_check_contract.md` §5.1): non-vacuity FIRST (the real tree passes and the
evidence names what was driven), then plants that must FAIL and NAME their site.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the subject and its
collaborators, perturbs the COPY, and drives the SHIPPED gate's own bytes against
it. `scripts/nixrisk/supervision.py` is read and never written here — and the
final control re-reads its sha256 to prove it.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).

THE FOUR PLANTS ARE THE FOUR §0a DOORS, EACH DRIVEN

  1. the constructor stops reading the book  -> the fresh process says NOT
     quarantined (CHECK-DEBT D3.250, reproduced);
  2. the restore floor is kept in memory only -> the fresh process reports the
     PRE-restore count (D3.251, reproduced);
  3. the refusal reason stops quoting the record, and separately repeats
     D3.250's own false sentence -> the reason arm reddens where the bool would
     not have;
  4. the breaker answers "quarantined" unconditionally -> the NON-VACUITY arm
     reddens, which is the arm proving a green distinguishes the two states.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_quarantine_durability as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SUBJECT_REL = "scripts/nixrisk/supervision.py"

COPIED = (
    "scripts/nixrisk/__init__.py",
    SUBJECT_REL,
    "scripts/nixrisk/halt.py",
    "scripts/nixrisk/seam.py",
    "scripts/risk_config.py",
    "scripts/nixsentinel/__init__.py",
    "scripts/nixsentinel/config.py",
)

#: DERIVED, not enumerated: `risk_config` validates every config it owns, so a
#: hand-written list goes stale the moment another sub-agent adds one and the
#: CONTROL goes CANNOT_MEASURE before a plant is applied. Nothing here is
#: asserted against — it is only what gets copied into the venue.
_RISK_CONFIGS = tuple(
    f"risks/{path.name}" for path in sorted((REPO / "risks").glob("*.json"))
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the breaker and its knobs."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "scripts" / "nixsentinel").mkdir(parents=True)
    (tmp_path / "risks").mkdir(parents=True)
    for rel in (*COPIED, *_RISK_CONFIGS):
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> None:
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _red(result, *, site: str, phrase: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert site in (result.site or ""), result.site
    assert phrase in (result.detail or ""), result.detail


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_PROCESS_BOUNDARY() -> None:
    """NON-VACUITY FIRST: the shipped tree is green, and the evidence names what
    was driven — including the two things a green must NOT be read as."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "ACROSS REAL PROCESS BOUNDARIES" in result.evidence, result.evidence
    assert "a genuinely new interpreter" in result.evidence
    assert "NON-VACUITY" in result.evidence
    assert "D3.250" in result.evidence and "D3.251" in result.evidence
    # The evidence must state what a green does NOT cover.
    assert "WHAT IS NOT MEASURED" in result.evidence
    assert "NO JOIN" in result.evidence, "the score boundary is not printed"


def test_the_COPIED_TREE_also_passes_so_every_plant_below_starts_GREEN(
    home: Path,
) -> None:
    """The venue's own control: every plant below starts from a GREEN copy, so a
    red is the plant's doing and not the copy's."""
    result = _run(home)
    assert result.status is Status.PASS, result


# --------------------------------------------------------------------------
# PLANT 1 — the constructor stops reading the book (D3.250, reproduced)
# --------------------------------------------------------------------------


def test_a_breaker_that_DOES_NOT_FOLD_the_book_at_construction_is_RED(
    home: Path,
) -> None:
    """The exact ARC 036 defect: `_quarantined` is a plain in-process dict, so
    the next supervision process auto-resurrects the strategy."""
    _plant(
        home,
        SUBJECT_REL,
        "        folded = self._quarantine_ledger.state()",
        "        folded = QuarantineState(live={}, floors={}, records_read=0)",
    )

    result = _run(home)

    _red(
        result,
        site="fresh-process-quarantine",
        phrase="answered is_quarantined=False",
    )
    assert "D3.250" in result.detail
    assert "auto-resurrected" in result.detail


# --------------------------------------------------------------------------
# PLANT 2 — the restore floor stays in memory (D3.251, reproduced)
# --------------------------------------------------------------------------


def test_a_RESTORE_FLOOR_that_never_reaches_DISK_is_RED(home: Path) -> None:
    """§12.11:779's counter reset, un-done by the next supervision restart."""
    _plant(
        home,
        SUBJECT_REL,
        "        self._floors: dict[str, float] = dict(folded.floors)",
        "        self._floors: dict[str, float] = {}",
    )

    result = _run(home)

    _red(
        result,
        site="fresh-process-restore-floor",
        phrase="restart(s) after the restore, expected",
    )
    assert "D3.251" in result.detail


def test_a_RESTORE_that_DELETES_the_quarantine_record_is_RED(home: Path) -> None:
    """Directive 6. A book that erased the quarantine to express the restore
    would change the answer — and would also destroy the operator's own record,
    which is why the arm asserts BOTH records remain rather than 'it moved'."""
    _plant(
        home,
        SUBJECT_REL,
        "        record = self._quarantine_ledger.record_restore(\n"
        "            subject, floor, operator=operator, counter_floor=floor\n"
        "        )",
        "        self._quarantine_ledger.path.write_text('')\n"
        "        record = self._quarantine_ledger.record_restore(\n"
        "            subject, floor, operator=operator, counter_floor=floor\n"
        "        )",
    )

    result = _run(home)

    _red(
        result,
        site="fresh-process-restore-floor",
        phrase="append, never rewrite",
    )


# --------------------------------------------------------------------------
# PLANT 3 — the REASON stops agreeing with the book (D3.250's second half)
# --------------------------------------------------------------------------


def test_a_REFUSAL_that_does_NOT_QUOTE_the_records_SEQ_is_RED(home: Path) -> None:
    """The bool is unchanged and correct; only the reason moves. A control that
    asserted the exit code or `allowed is False` would be green over this."""
    _plant(
        home,
        SUBJECT_REL,
        'f"seq={record.seq} in {book} (ts={record.ts!r}), which holds "',
        'f"in {book}, which holds "',
    )

    result = _run(home)

    _red(
        result,
        site="may_relaunch-reason",
        phrase="does not carry the book's own seq=",
    )
    assert "read by THIS GATE out of" in result.detail


def test_a_REFUSAL_that_REPEATS_D3_250s_FALSE_SENTENCE_is_RED(home: Path) -> None:
    """The measured defect, put back verbatim: a refusal saying the cap 'has not
    been reached' on an object whose book holds the cap."""
    _plant(
        home,
        SUBJECT_REL,
        'f"{record.cap} over {record.window_s}s — {record.reason}. §4:274 "',
        'f"{record.cap} over {record.window_s}s; the §4:272 cap has not been '
        'reached — {record.reason}. §4:274 "',
    )

    result = _run(home)

    _red(
        result,
        site="may_relaunch-reason",
        phrase="this is CHECK-DEBT D3.250's exact string",
    )


def test_a_QUARANTINE_recorded_under_the_WRONG_KIND_is_RED(home: Path) -> None:
    """The book is written, the fold still works, and the operator's own book
    does not say 'quarantine'. The gate reads the FILE, so it sees this."""
    _plant(
        home,
        SUBJECT_REL,
        'QUARANTINE_KIND: Final[str] = "quarantine"',
        'QUARANTINE_KIND: Final[str] = "quarantine-DEFECT"',
    )

    result = _run(home)

    _red(
        result,
        site="may_relaunch-reason",
        phrase="NO 'quarantine' record after the cap was driven to a trip",
    )


# --------------------------------------------------------------------------
# PLANT 4 — the NON-VACUITY arm is the one that catches a constant
# --------------------------------------------------------------------------


def test_a_breaker_that_answers_QUARANTINED_UNCONDITIONALLY_is_RED(
    home: Path,
) -> None:
    """§0a/4: a gate that cannot distinguish the two states of one book measured
    nothing. This plant PASSES arm 1 and must still be caught."""
    _plant(
        home,
        SUBJECT_REL,
        '        """§4:273 — is this subject left dead and flat, awaiting the operator?"""\n'
        "        return subject in self._quarantined",
        '        """§4:273 — is this subject left dead and flat, awaiting the operator?"""\n'
        "        return True",
    )

    result = _run(home)

    _red(
        result,
        site="non-vacuity",
        phrase="answered is_quarantined=True",
    )
    assert "cannot say NOT-quarantined proves nothing" in result.detail


# --------------------------------------------------------------------------
# THE INSTRUMENT'S OWN FAILURE MODES
# --------------------------------------------------------------------------


def test_an_UNIMPORTABLE_subject_is_CANNOT_MEASURE_and_never_a_PASS(
    tmp_path: Path,
) -> None:
    """§17: a safety property proven while its subject is unavailable is not
    proven, and the absence of the config is named."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "risks/supervision.config.json" in (result.detail or ""), result.detail


def test_a_DRIVER_that_RAISES_is_a_FINDING_and_never_a_SKIPPED_ASSERTION(
    home: Path,
) -> None:
    """§7.12/6: the driver's silence must not read as agreement."""
    _plant(
        home,
        SUBJECT_REL,
        "class CrashLoopBreaker:  # pylint: disable=too-many-instance-attributes",
        "raise RuntimeError('planted import-time failure')\n\n\n"
        "class CrashLoopBreaker:  # pylint: disable=too-many-instance-attributes",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "planted import-time failure" in (result.detail or ""), result.detail


def test_the_PRODUCTION_SUBJECT_is_BYTE_IDENTICAL_after_every_plant() -> None:
    """Doctrine C.8: no plant above touched a production artifact. Measured by
    sha256 rather than asserted in prose."""
    digest = hashlib.sha256((REPO / SUBJECT_REL).read_bytes()).hexdigest()
    again = hashlib.sha256((REPO / SUBJECT_REL).read_bytes()).hexdigest()

    assert digest == again
    result = _run(REPO)
    assert result.status is Status.PASS, result
    assert hashlib.sha256((REPO / SUBJECT_REL).read_bytes()).hexdigest() == digest, (
        "the gate MUTATED its own subject"
    )
