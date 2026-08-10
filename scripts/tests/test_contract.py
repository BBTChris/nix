"""Contract types and the non-vacuity rules of nix_check_contract.md §5."""

from nixverify.contract import (
    CheckResult,
    Mode,
    Status,
    exit_code_for,
    validate_result,
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


def test_validate_result_noop_on_cannot_measure() -> None:
    """validate_result is idempotent on CANNOT_MEASURE — no changes."""
    result = CheckResult(
        name="c", status=Status.CANNOT_MEASURE, detail="already unknown"
    )
    validated = validate_result(result)
    assert validated.status is Status.CANNOT_MEASURE
    assert validated.detail == "already unknown"
