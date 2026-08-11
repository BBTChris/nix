"""Status.GUARDED — check-contract AMENDMENT 1 (ARC 024).

GUARDED is the one status that costs nothing to claim: unlike FAIL it accuses
nobody, and unlike PASS it proves nothing. Left unpoliced it would become the
drawer every awkward verdict is filed in. Its two defining properties are
therefore mechanical — a GUARDED verdict must have MEASURED (evidence) and must
name the arc that discharges it (`guard_owner`) — and the tests below are what
make that policing falsifiable.

The amendment is claimed to be strictly additive. `test_aggregate_exit_*` and in
particular the non-regression pair at the end are the evidence for that claim:
exit codes 0/1/2 must mean exactly what `VERIFY-AND-CHECKS.md` §B.2 gave them
before GUARDED existed.
"""
# pylint: disable=invalid-name,import-outside-toplevel,use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test on purpose; `== ()` is asserted
# rather than `not x` because an empty tuple and a falsey non-tuple are
# different outcomes here; late imports are the sys.path bootstrap this suite
# needs. Each is deliberate, so the pragma is per-file and named.

import io
import time

import pytest  # pylint: disable=import-error
from nixverify.contract import (
    CheckResult,
    Status,
    exit_code_for,
    validate_result,
)
from nixverify.engine import _timed, aggregate_exit  # pylint: disable=protected-access
from nixverify.render import LiveProgress, Theme, render_summary

PLAIN = Theme(colour=False, unicode=False)


def _guarded(**kw: str) -> CheckResult:
    """A well-formed GUARDED result, overridable field by field."""
    fields = {
        "name": "c",
        "site": "checks/check_datafeed.py",
        "evidence": "measured: 3 bars, gap at 09:31",
        "guard_owner": "ARC 025",
    }
    fields.update(kw)
    return CheckResult(status=Status.GUARDED, **fields)  # type: ignore[arg-type]


# -- exit_code_for ----------------------------------------------------------


# §4.2 as amended. The pairs are written as a LITERAL inside the decorator, not
# lifted to a module-level name, and that is not a style choice:
# `check_derived_claims` derives `pytest_collected_tests` by AST and refuses to
# count a parametrize whose argvalues it cannot evaluate statically. Lifting this
# to `_EXIT_CODES = [...]` turned that claim into CANNOT_MEASURE — measured in
# ARC 024, with the gate naming this file. Keep the literal here.
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (Status.PASS, 0),
        (Status.FAIL_REPAIRABLE, 1),
        (Status.FAIL_NEEDS_OPERATOR, 1),
        (Status.CANNOT_MEASURE, 2),
        (Status.SKIPPED, 2),
        (Status.GUARDED, 3),
    ],
)
def test_exit_code_for_covers_all_six_statuses(status: Status, code: int) -> None:
    """§4.2 as amended. 3 is added; 0/1/2 keep their pre-amendment meanings."""
    assert exit_code_for(status) == code


def test_every_status_has_an_exit_code_decision() -> None:
    """A seventh status must not arrive without someone choosing its code.

    `exit_code_for` ends in a bare `return 2`, so a new member added to `Status`
    would silently be treated as cannot-measure rather than reddening anything.
    This pins the count so the addition has to be deliberate.
    """
    assert len(list(Status)) == 6
    assert {exit_code_for(status) for status in Status} == {0, 1, 2, 3}


# -- validate_result, AMENDMENT 1 ------------------------------------------


def test_guarded_without_evidence_is_downgraded_to_cannot_measure() -> None:
    """A deferral that measured nothing is an unmeasured claim with a colour."""
    validated = validate_result(_guarded(evidence=""))
    assert validated.status is Status.CANNOT_MEASURE
    assert "evidence" in validated.detail
    assert "GUARDED" in validated.detail


def test_guarded_with_whitespace_only_evidence_is_downgraded() -> None:
    """Whitespace is not a measurement — the rule strips before testing."""
    assert validate_result(_guarded(evidence="   \n ")).status is Status.CANNOT_MEASURE


def test_guarded_without_guard_owner_is_downgraded_to_cannot_measure() -> None:
    """CHECK-DEBT.md B.3: a deferral with no owner is no owner wearing a name."""
    validated = validate_result(_guarded(guard_owner=""))
    assert validated.status is Status.CANNOT_MEASURE
    assert "arc" in validated.detail.lower()
    assert "owner" in validated.detail.lower()


def test_guarded_with_evidence_and_owner_passes_through_unchanged() -> None:
    """The positive arm: without it the two rules above could be vacuous."""
    result = _guarded()
    validated = validate_result(result)
    assert validated.status is Status.GUARDED
    assert validated.guard_owner == "ARC 025"
    assert validated.detail == ""  # nothing appended when nothing was rejected


def test_guarded_downgrade_preserves_the_checks_own_detail() -> None:
    """§5: the downgrade path is where an operator most needs the check's account."""
    validated = validate_result(_guarded(guard_owner="", detail="roll window unset"))
    assert validated.status is Status.CANNOT_MEASURE
    assert "roll window unset" in validated.detail


def test_pre_existing_pass_without_evidence_rule_still_holds() -> None:
    """Non-regression: AMENDMENT 1 must not have loosened the §5 PASS rule."""
    validated = validate_result(CheckResult(name="c", status=Status.PASS, evidence=""))
    assert validated.status is Status.CANNOT_MEASURE
    assert "evidence" in validated.detail


def test_pre_existing_fail_without_site_rule_still_holds() -> None:
    """Non-regression: AMENDMENT 1 must not have loosened the §5 FAIL rule."""
    validated = validate_result(
        CheckResult(name="c", status=Status.FAIL_NEEDS_OPERATOR, site="")
    )
    assert validated.status is Status.CANNOT_MEASURE
    assert "site" in validated.detail


# -- aggregate_exit dominance: FAIL > CANNOT-MEASURE > GUARDED > PASS -------


def test_aggregate_exit_fail_dominates_guarded_and_cannot_measure() -> None:
    """A real failure out-ranks every softer state, in any combination."""
    results = [
        CheckResult("a", Status.PASS, evidence="e"),
        _guarded(),
        CheckResult("c", Status.CANNOT_MEASURE),
        CheckResult("d", Status.FAIL_REPAIRABLE, site="s"),
    ]
    assert aggregate_exit(results) == 1


def test_aggregate_exit_cannot_measure_dominates_guarded() -> None:
    """The ruling's direction: a gate that went blind out-shouts a known-red deferral.

    A cannot-measure carries no information about its subject; a GUARDED verdict
    carries a measurement AND an owner. Ranking the informative state higher
    would defeat what §B.2's exit 2 exists to prevent.
    """
    results = [
        CheckResult("a", Status.PASS, evidence="e"),
        _guarded(),
        CheckResult("c", Status.CANNOT_MEASURE),
    ]
    assert aggregate_exit(results) == 2


def test_aggregate_exit_guarded_alone_is_three() -> None:
    """No failure and nothing unmeasured, but certification is withheld."""
    results = [CheckResult("a", Status.PASS, evidence="e"), _guarded()]
    assert aggregate_exit(results) == 3


def test_aggregate_exit_all_pass_is_zero() -> None:
    """Test that an all-PASS run exits 0."""
    results = [CheckResult(f"c{i}", Status.PASS, evidence="e") for i in range(5)]
    assert aggregate_exit(results) == 0


def test_aggregate_exit_skipped_counts_as_two() -> None:
    """§4.2: a check that never ran is not a pass, and outranks GUARDED."""
    assert aggregate_exit([CheckResult("a", Status.SKIPPED)]) == 2
    assert aggregate_exit([_guarded(), CheckResult("a", Status.SKIPPED)]) == 2


# -- Non-regression: with no GUARDED present, the aggregate is unchanged ----


def test_aggregate_exit_is_bit_identical_on_a_guarded_free_run() -> None:
    """The banked ARC 023 shape — 10 passed | 1 failed | 1 cannot measure — exits 1.

    This is the amendment's own claim under test: no check on this tree emits
    GUARDED, so the aggregate must be indistinguishable from the pre-amendment
    function for every list that contains none.
    """
    results = [CheckResult(f"p{i}", Status.PASS, evidence="e") for i in range(10)]
    results.append(CheckResult("f", Status.FAIL_NEEDS_OPERATOR, site="s"))
    results.append(CheckResult("u", Status.CANNOT_MEASURE))
    assert not any(r.status is Status.GUARDED for r in results)
    assert aggregate_exit(results) == 1


def test_aggregate_exit_all_pass_guarded_free_run_is_still_zero() -> None:
    """The other half of the non-regression pair: a green run stayed green."""
    results = [CheckResult(f"p{i}", Status.PASS, evidence="e") for i in range(12)]
    assert aggregate_exit(results) == 0


def test_aggregate_exit_of_no_results_is_zero() -> None:
    """Boundary: an empty list has no failure, nothing unmeasured, no deferral."""
    assert aggregate_exit([]) == 0


# -- render_summary: the guarded segment ------------------------------------


def test_summary_omits_the_guarded_segment_when_nothing_is_guarded() -> None:
    """The banked close-out triple must not silently widen on every run."""
    results = [
        CheckResult("a", Status.PASS, evidence="e"),
        CheckResult("b", Status.FAIL_REPAIRABLE, site="s"),
        CheckResult("c", Status.CANNOT_MEASURE),
    ]
    text = render_summary(results, 1, PLAIN)
    assert "guarded" not in text
    assert "1 passed" in text
    assert "1 failed" in text
    assert "1 cannot measure" in text
    assert "exit 1" in text


def test_summary_includes_the_guarded_segment_when_one_is_guarded() -> None:
    """Loud when it exists, invisible when it does not."""
    results = [CheckResult("a", Status.PASS, evidence="e"), _guarded()]
    text = render_summary(results, 3, PLAIN)
    assert "1 guarded" in text
    assert "exit 3" in text


def test_summary_guarded_segment_carries_no_escape_codes_without_colour() -> None:
    """§12 degradation: the segment is appended painted, and paint is a no-op here."""
    text = render_summary([_guarded()], 3, PLAIN)
    assert "\x1b[" not in text


# -- LiveProgress: §1.3 degradation ----------------------------------------


def test_live_progress_writes_nothing_on_a_non_tty() -> None:
    """Non-TTY means NOTHING, not "no colour".

    The pre-ARC-024 output was the plain result block alone, and it must stay
    byte-identical when stdout is a pipe, a file or a systemd unit — a stray
    \\r or \\x1b[2K in a captured log is the whole regression this guards.
    """
    stream = io.StringIO()
    progress = LiveProgress(stream, PLAIN, total=2)
    progress.start()
    progress.check_start("check_venv")
    progress.check_verdict(CheckResult("check_venv", Status.PASS, evidence="e"))
    progress.check_start("check_node_identity")
    progress.check_verdict(_guarded(name="check_node_identity"))
    progress.stop()
    assert stream.getvalue() == ""


def test_live_progress_stop_is_idempotent_on_a_non_tty() -> None:
    """stop() runs on every exit path, including twice."""
    stream = io.StringIO()
    progress = LiveProgress(stream, PLAIN, total=1)
    progress.stop()
    progress.stop()
    assert stream.getvalue() == ""


# -- engine._timed ----------------------------------------------------------


def test_timed_stamps_a_positive_duration_on_the_result() -> None:
    """duration_s is reported, so it must be real — and never negative.

    `perf_counter` rather than wall time precisely so an NTP or DST step cannot
    put a negative duration in the journal. The sleep is what makes "positive"
    a measurement rather than a rounding accident (duration_s rounds to 4dp).
    """

    def _run() -> CheckResult:
        time.sleep(0.01)
        return CheckResult("c", Status.PASS, evidence="e")

    result = _timed(_run)
    assert result.duration_s > 0.0
    assert result.duration_s >= 0.01
    assert result.duration_s < 5.0


def test_timed_returns_the_same_result_object_it_was_given() -> None:
    """The stamp is a mutation, not a copy — the check's own fields survive."""
    original = CheckResult("c", Status.GUARDED, evidence="e", guard_owner="ARC 025")
    result = _timed(lambda: original)
    assert result is original
    assert result.status is Status.GUARDED
    assert result.guard_owner == "ARC 025"
