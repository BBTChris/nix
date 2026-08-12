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


# -- ARC 026 (B2): a guard must name an arc that can still discharge it -----
#
# THE THIRD ITERATION OF ONE FLAW, and the tests are written against the flaw
# rather than against the code:
#   ARC 024 required a non-empty owner. `"ARC 025+"` passed it.
#   ARC 025 required exactly one arc. `"ARC 025"` passed it — and ARC 025 then
#     completed with that guard still standing on the tree.
#   ARC 026 requires the arc to be able to PAY. Shape was never the property;
#     doctrine B.3 asks for the arc that CAN ACTUALLY DISCHARGE the marker.


def test_completed_arcs_reads_the_real_completion_record() -> None:
    """NON-VACUITY, on the real tree, before any plant.

    Asserted as INVARIANTS, never as values: a count or a maximum written here
    would be a literal anchor that goes stale at the close of every arc — which
    is exactly the cadence this predicate operates on (`debug.md` §8 failure
    mode #4). What is asserted is that the record parses, that it is not empty,
    and that it agrees with the ledger's independent per-arc series.
    """
    from pathlib import Path

    from nixverify.contract import completed_arcs

    home = Path(__file__).resolve().parents[2]
    arcs, error = completed_arcs(home)
    assert not error, error
    assert arcs, "the completion record parsed to the empty set"
    assert max(arcs) >= 20, sorted(arcs)  # a floor, not the current value


def test_a_guard_naming_a_COMPLETED_arc_is_downgraded(tmp_path) -> None:
    """THE DEFECT ITSELF. `ARC 001` has closed; it can discharge nothing."""
    from nixverify.contract import completed_arcs

    home = _completion_tree(tmp_path, closed=(1, 2, 3), series_max=3)
    _, error = completed_arcs(home)
    assert not error, error

    validated = validate_result(_guarded(guard_owner="ARC 001"), home)

    assert validated.status is Status.CANNOT_MEASURE, validated.detail
    assert "ALREADY COMPLETED" in validated.detail, validated.detail
    assert "ARC 001" in validated.detail, validated.detail


def test_a_guard_naming_a_LIVE_arc_survives(tmp_path) -> None:
    """THE OTHER HALF. Without it the rule above could simply always fire."""
    home = _completion_tree(tmp_path, closed=(1, 2, 3), series_max=3)
    validated = validate_result(_guarded(guard_owner="ARC 004"), home)
    assert validated.status is Status.GUARDED, validated.detail
    assert validated.detail == "", validated.detail


def test_an_unreadable_completion_record_FAILS_CLOSED(tmp_path) -> None:
    """No record, no verdict. The fail-open reading would switch the arm off."""
    validated = validate_result(_guarded(guard_owner="ARC 999"), tmp_path)
    assert validated.status is Status.CANNOT_MEASURE, validated.detail
    assert "completion record" in validated.detail, validated.detail
    assert "SESSION.md" in validated.detail, validated.detail


def test_a_completion_record_BEHIND_the_ledger_is_CANNOT_MEASURE(tmp_path) -> None:
    """The cross-derivation, and it is TENSE-AWARE rather than a simple floor.

    A session log that under-reports is the failure that would silently let a
    guard point at history. The ledger's series table is the second record that
    catches it — but a series row is written DURING its arc while a session
    summary is appended AT CLOSE, so the newest series row is exempt and every
    older one must be closed. Here rows 5 and 6 are unmatched and 7 is the
    newest, so 5 and 6 are the complaint and 7 is not.
    """
    from nixverify.contract import completed_arcs

    home = _completion_tree(tmp_path, closed=(1, 2), series=(5, 6, 7))
    arcs, error = completed_arcs(home)
    assert not arcs
    assert "UNDER-REPORTING" in error, error
    assert "005, 006" in error, error
    assert "007" not in error, error

    validated = validate_result(_guarded(guard_owner="ARC 009"), home)
    assert validated.status is Status.CANNOT_MEASURE, validated.detail


def test_the_NEWEST_series_row_may_be_the_arc_IN_FLIGHT(tmp_path) -> None:
    """The control for the rule above, and the case that broke its first spelling.

    An arc writes its series row while it is running and appends its session
    summary when it closes, so `series ahead by exactly the newest row` is the
    NORMAL state of every arc in progress. The first spelling of this rule
    treated it as a broken session log and reddened the whole predicate — caught
    by this suite inside the arc that wrote it.
    """
    from nixverify.contract import completed_arcs

    home = _completion_tree(tmp_path, closed=(1, 2, 3), series=(1, 2, 3, 4))
    arcs, error = completed_arcs(home)
    assert not error, error
    assert arcs == frozenset({1, 2, 3}), sorted(arcs)
    assert (
        validate_result(_guarded(guard_owner="ARC 004"), home).status is Status.GUARDED
    )


def test_only_HEADINGS_count_as_a_close_out(tmp_path) -> None:
    """A citation is not a completion.

    Arc summaries cite other arcs constantly. If body prose counted, an arc
    would be marked complete because somebody mentioned it — and the marker on
    a live arc would go red for a reason nobody could see.
    """
    from nixverify.contract import completed_arcs

    home = _completion_tree(tmp_path, closed=(1,), series_max=1)
    (home / "sessions" / "SESSION.md").write_text(
        "## 2026-01-01 — ARC 001: closed\n\nBody prose citing ARC 002 and ARC 003.\n",
        encoding="utf-8",
    )
    arcs, error = completed_arcs(home)
    assert not error, error
    assert arcs == frozenset({1}), sorted(arcs)


def test_the_admitting_arc_keeps_SHAPE_ONLY_validation() -> None:
    """Two tenses, one grammar (ARC 026 B2).

    `guard_owner` is a PROMISE — a completed arc disqualifies it. An `admitted`
    entry in `check_artifact_gate_coverage`'s baseline is a RECEIPT — the arc
    that already admitted a path — and a completed arc is the normal value there
    for every entry once its arc closes. The same call with and without
    `completed` must therefore give different answers, or the distinction is not
    implemented.
    """
    from nixverify.contract import guard_owner_defect

    assert guard_owner_defect("ARC 025") == ""
    assert "ALREADY COMPLETED" in guard_owner_defect("ARC 025", frozenset({25}))


def test_the_ENGINE_path_has_the_dischargeability_arm_switched_on(tmp_path) -> None:
    """An arm live only when a caller remembers an argument is an arm that is off.

    This drives the real engine — `run_blocks` over a real check module on disk —
    rather than calling `validate_result` directly, because every assertion above
    would pass unchanged against an engine that never passes `home`. That is the
    §7.12 question aimed at this arm: it could be perfectly correct and never run.
    """
    from pathlib import Path

    from nixverify.contract import Context, Mode
    from nixverify.engine import run_blocks
    from nixverify.registry import Block

    home = _completion_tree(tmp_path, closed=(1, 2, 3), series_max=3)
    checks = home / "checks"
    checks.mkdir()
    (checks / "check_stale_guard.py").write_text(
        "from nixverify.contract import CheckResult, Status\n"
        "PRIVILEGE = 'user'\n"
        "INTERACTIVE = False\n"
        "DISRUPTIVE = False\n"
        "def run(mode, ctx):\n"
        "    return CheckResult(name='check_stale_guard', status=Status.GUARDED,\n"
        "                       evidence='measured', guard_owner='ARC 002')\n",
        encoding="utf-8",
    )
    ctx = Context(nix_home=home, mode=Mode.VERIFY)
    results = run_blocks((Block(name="b", checks=("check_stale_guard",)),), checks, ctx)
    assert len(results) == 1
    assert results[0].status is Status.CANNOT_MEASURE, results[0].detail
    assert "ALREADY COMPLETED" in results[0].detail, results[0].detail
    assert isinstance(Path(home), Path)


def _completion_tree(tmp_path, closed, series_max=None, series=None):
    """A throwaway tree carrying a session log and a ledger series table.

    Never the real tree: a plant that edited `sessions/SESSION.md` would be
    rewriting banked evidence (`CLAUDE.md` directive 6) and doctrine C.8's
    permanent-synthetic-row incident is what that costs.
    """
    home = tmp_path / "home"
    (home / "sessions").mkdir(parents=True)
    (home / "docs").mkdir()
    (home / "sessions" / "SESSION.md").write_text(
        "".join(f"## 2026-01-01 — ARC {n:03d}: closed\n\n" for n in closed),
        encoding="utf-8",
    )
    rows = series if series is not None else (series_max,)
    (home / "docs" / "CHECK-DEBT.md").write_text(
        "| date | arc | open | note |\n|---|---|---|---|\n"
        + "".join(f"| 2026-01-01 | ARC {n:03d} | 5 | fixture |\n" for n in rows),
        encoding="utf-8",
    )
    return home
