"""Contract types and the non-vacuity rules of nix_check_contract.md §5."""
# pylint: disable=invalid-name
# Test names SHOUT the property under test - RANGE, EMPTY, EVIDENCE are the
# words the contract uses, and lowercasing them would lose the citation.

from nixverify.contract import (
    CheckResult,
    Mode,
    Status,
    exit_code_for,
    guard_owner_defect,
    validate_result,
)


def _guarded(owner: str) -> CheckResult:
    """A GUARDED verdict that measured something, differing only in its owner."""
    return CheckResult(
        name="c", status=Status.GUARDED, evidence="24 uncovered", guard_owner=owner
    )


def test_pass_without_evidence_is_downgraded_to_cannot_measure() -> None:
    """§5: a PASS that measured nothing is vacuous — it must not stand."""
    result = CheckResult(name="c", status=Status.PASS, evidence="")
    validated = validate_result(result)
    assert validated.status is Status.CANNOT_MEASURE
    assert "evidence" in validated.detail


def test_pass_with_evidence_survives() -> None:
    """PASS with evidence is valid — no downgrade."""
    result = CheckResult(name="c", status=Status.PASS, evidence="measured X=1")
    assert validate_result(result).status is Status.PASS


def test_fail_without_site_is_downgraded_to_cannot_measure() -> None:
    """§5: a FAIL that cannot name the defect has not discriminated."""
    result = CheckResult(name="c", status=Status.FAIL_REPAIRABLE, site="")
    validated = validate_result(result)
    assert validated.status is Status.CANNOT_MEASURE
    assert "site" in validated.detail


def test_fail_with_site_survives() -> None:
    """FAIL_REPAIRABLE with site is valid — no downgrade."""
    result = CheckResult(
        name="c", status=Status.FAIL_REPAIRABLE, site="jts.ini:ReadOnlyApi"
    )
    assert validate_result(result).status is Status.FAIL_REPAIRABLE


def test_exit_codes_match_the_contract() -> None:
    """§4.2 — SKIPPED maps to 2, never 0: a check that never ran is not a pass."""
    assert exit_code_for(Status.PASS) == 0
    assert exit_code_for(Status.FAIL_REPAIRABLE) == 1
    assert exit_code_for(Status.FAIL_NEEDS_OPERATOR) == 1
    assert exit_code_for(Status.CANNOT_MEASURE) == 2
    assert exit_code_for(Status.SKIPPED) == 2


def test_modes_are_ordered_install_superset_of_correct_superset_of_verify() -> None:
    """Mode.rank respects the subset ordering: VERIFY ⊂ CORRECT ⊂ INSTALL."""
    assert Mode.VERIFY.rank == 0
    assert Mode.CORRECT.rank == 1
    assert Mode.INSTALL.rank == 2


def test_downgrade_preserves_check_authors_diagnostic() -> None:
    """§5: on downgrade, append engine reason; never discard the check's own detail."""
    result = CheckResult(
        name="c",
        status=Status.PASS,
        evidence="",
        detail="probe timed out after 30s",
    )
    validated = validate_result(result)
    assert validated.status is Status.CANNOT_MEASURE
    assert "evidence" in validated.detail
    assert "probe timed out" in validated.detail


def test_a_single_arc_identifier_is_the_only_accepted_guard_owner() -> None:
    """ARC 025 C2 — §4.1 requires the SPECIFIC discharging arc, so one arc only."""
    assert guard_owner_defect("ARC 025") == ""
    assert validate_result(_guarded("ARC 025")).status is Status.GUARDED


def test_a_guard_owner_naming_a_RANGE_is_rejected_and_the_REASON_says_so() -> None:
    """The exact string that shipped in ARC 024, and the reason it is not an owner.

    `"ARC 025+"` passes a non-empty test and names nobody: every arc in a range
    can point at the next one, which is doctrine B.3's *an owner that cannot pay
    is no owner wearing a name*. The exit code alone would not distinguish this
    from any other downgrade, so the REASON is what is asserted.
    """
    defect = guard_owner_defect("ARC 025+")
    assert "RANGE" in defect, defect
    assert "ARC 025+" in defect, defect
    assert "SPECIFIC" in defect, defect

    validated = validate_result(_guarded("ARC 025+"))
    assert validated.status is Status.CANNOT_MEASURE
    assert "RANGE" in validated.detail
    assert "ARC 025+" in validated.detail


def test_the_ACTUAL_offending_ARC_024_owner_string_is_rejected() -> None:
    """Regression pin on the real value, not on a tidied stand-in."""
    offender = "the bulk check retrofit arc (ARC 025+), sized in ARC 024 Stage 6.4"
    defect = guard_owner_defect(offender)
    assert defect, "this is the string that shipped, and it must not be an owner"
    assert offender in defect
    assert validate_result(_guarded(offender)).status is Status.CANNOT_MEASURE


def test_a_guard_owner_naming_TWO_arcs_is_rejected_as_a_set() -> None:
    """A set is not a range and is equally not one arc; the reason distinguishes them."""
    defect = guard_owner_defect("ARC 025 and ARC 026")
    assert "2 arcs" in defect, defect
    assert "exactly one" in defect, defect


def test_prose_that_mentions_no_arc_at_all_is_rejected_with_the_expected_form() -> None:
    """The reason must tell the author what to type, not merely that they were wrong."""
    defect = guard_owner_defect("the bulk retrofit arc")
    assert "not a single arc identifier" in defect, defect
    assert "ARC NNN" in defect, defect


def test_an_EMPTY_guard_owner_still_reports_the_B3_reason() -> None:
    """The ARC 024 rule is kept, not replaced — it was the right shape."""
    defect = guard_owner_defect("   ")
    assert "no discharging arc named" in defect
    assert "B.3" in defect
    assert validate_result(_guarded("")).status is Status.CANNOT_MEASURE


def test_guarded_still_requires_EVIDENCE_regardless_of_a_valid_owner() -> None:
    """The two GUARDED properties are independent; fixing one must not mask the other."""
    result = CheckResult(
        name="c", status=Status.GUARDED, evidence="", guard_owner="ARC 025"
    )
    validated = validate_result(result)
    assert validated.status is Status.CANNOT_MEASURE
    assert "no evidence recorded" in validated.detail


def test_guarded_exit_code_is_unchanged_by_the_owner_rule() -> None:
    """AMENDMENT 1 stays strictly additive: 0/1/2 untouched, GUARDED is 3."""
    assert exit_code_for(Status.GUARDED) == 3


def test_validate_result_noop_on_cannot_measure() -> None:
    """validate_result is idempotent on CANNOT_MEASURE — no changes."""
    result = CheckResult(
        name="c", status=Status.CANNOT_MEASURE, detail="already unknown"
    )
    validated = validate_result(result)
    assert validated.status is Status.CANNOT_MEASURE
    assert validated.detail == "already unknown"
