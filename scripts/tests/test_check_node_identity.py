"""Node identity: stored UUID vs live disk (§10.1)."""

import json
from pathlib import Path

from nixverify.contract import Context, Mode, Status
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"

UUID_A = "3f9c1a7e-8b22-4d1e-9f03-7a5c2e114db6"
UUID_B = "00000000-1111-2222-3333-444444444444"


def _mod():
    """Load check_node_identity for direct access to evaluate()/stored_uuid()."""
    loaded = load_check(CHECKS, "check_node_identity")
    assert loaded.run is not None, loaded.load_error
    import check_node_identity as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    return mod


def _state(tmp_path: Path, uuid: str) -> Path:
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    # install.sh (verified on-disk, ARC 006/008) writes the key
    # "primary_partition_uuid" — not "root_uuid". This fixture mirrors the
    # real writer so the test exercises the real on-disk contract.
    (state / "node_identity.json").write_text(
        json.dumps({"primary_partition_uuid": uuid}), encoding="utf-8"
    )
    return tmp_path


def test_matching_uuid_passes_with_both_values_as_evidence(tmp_path: Path) -> None:
    """Stored == live: PASS, with the UUID recorded as evidence (§5)."""
    mod = _mod()
    result = mod.evaluate(UUID_A, UUID_A, tmp_path / "state" / "node_identity.json")
    assert result.status is Status.PASS
    assert UUID_A in result.evidence


def test_mismatch_fails_and_names_both_uuids(tmp_path: Path) -> None:
    """Detects a cloned VM, swapped disk, or restore onto other hardware."""
    mod = _mod()
    result = mod.evaluate(UUID_A, UUID_B, tmp_path / "state" / "node_identity.json")
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert UUID_A in result.detail
    assert UUID_B in result.detail
    assert result.site


def test_unreadable_live_uuid_is_cannot_measure_not_fail(tmp_path: Path) -> None:
    """§4.1: if blkid cannot answer, the truth is unknown — not wrong."""
    mod = _mod()
    result = mod.evaluate(UUID_A, "", tmp_path / "state" / "node_identity.json")
    assert result.status is Status.CANNOT_MEASURE


def test_absent_state_file_needs_operator(tmp_path: Path) -> None:
    """No stored identity: the engine cannot invent one — re-run install.sh."""
    mod = _mod()
    result = mod.evaluate("", UUID_A, tmp_path / "state" / "node_identity.json")
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "install.sh" in result.detail


def test_stored_uuid_reads_the_real_install_sh_key(tmp_path: Path) -> None:
    """stored_uuid() must read the key install.sh actually writes.

    install.sh (checked on-disk) writes "primary_partition_uuid", not
    "root_uuid" — this pins that contract so a future edit to either side
    is caught here rather than silently diverging again.
    """
    mod = _mod()
    state_path = _state(tmp_path, UUID_A)
    assert mod.stored_uuid(state_path / "state" / "node_identity.json") == UUID_A


def test_runs_against_the_real_node() -> None:
    """Live: this box's state/node_identity.json is known-good (verified
    on-disk, ARC 006/008) and matches live hardware, so the real outcome
    must be PASS. Asserting a tuple of 3 of the 5 possible statuses — the
    only 3 this check can ever produce — proves nothing; it always passes
    regardless of whether the check is correct. Assert the actual state.
    """
    loaded = load_check(CHECKS, "check_node_identity")
    assert loaded.run is not None
    result = loaded.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS
    assert result.evidence


def test_corrupt_file_non_utf8_bytes_is_distinguished_from_absent(
    tmp_path: Path,
) -> None:
    """UnicodeDecodeError (from read_text on non-UTF-8 bytes) is a ValueError,
    missed by the prior `except OSError, json.JSONDecodeError`. It must not
    escape run() — and the resulting FAIL must say "corrupt", never "no
    stored node identity" (§10.1: present-but-broken is not absent).
    """
    mod = _mod()
    path = tmp_path / "state" / "node_identity.json"
    path.parent.mkdir()
    path.write_bytes(b"\xff\xfe\x00\x01not utf-8")

    stored, condition = mod._read_state(path)  # pylint: disable=protected-access
    assert stored == ""
    assert condition.startswith("corrupt")

    result = mod.evaluate(stored, UUID_A, path, condition)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert result.site
    assert "corrupt" in result.detail
    assert "no stored node identity" not in result.detail


def test_corrupt_file_non_object_payload_is_distinguished_from_absent(
    tmp_path: Path,
) -> None:
    """Valid JSON that is not an object (e.g. a list) previously raised
    AttributeError from `payload.get(...)` — must be caught, not escape.
    """
    mod = _mod()
    path = tmp_path / "state" / "node_identity.json"
    path.parent.mkdir()
    path.write_text("[1, 2, 3]", encoding="utf-8")

    stored, condition = mod._read_state(path)  # pylint: disable=protected-access
    assert stored == ""
    assert condition.startswith("corrupt")

    result = mod.evaluate(stored, UUID_A, path, condition)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "corrupt" in result.detail
    assert "no stored node identity" not in result.detail


def test_corrupt_file_truncated_json_is_distinguished_from_absent(
    tmp_path: Path,
) -> None:
    """Truncated JSON (e.g. a write interrupted mid-flush) is json.JSONDecodeError."""
    mod = _mod()
    path = tmp_path / "state" / "node_identity.json"
    path.parent.mkdir()
    path.write_text('{"primary_partition_uuid": "abc', encoding="utf-8")

    stored, condition = mod._read_state(path)  # pylint: disable=protected-access
    assert stored == ""
    assert condition.startswith("corrupt")

    result = mod.evaluate(stored, UUID_A, path, condition)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "corrupt" in result.detail


def test_absent_file_still_reports_absent_not_corrupt(tmp_path: Path) -> None:
    """Control: a genuinely absent file must keep the original wording —
    only a present-but-broken file gets the new "corrupt" wording.
    """
    mod = _mod()
    path = tmp_path / "state" / "node_identity.json"

    stored, condition = mod._read_state(path)  # pylint: disable=protected-access
    assert stored == ""
    assert condition == "absent"

    result = mod.evaluate(stored, UUID_A, path, condition)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "install.sh" in result.detail
    assert "corrupt" not in result.detail


def test_run_end_to_end_on_corrupt_file_does_not_report_cannot_measure(
    tmp_path: Path,
) -> None:
    """Regression for I3: previously the exception escaped run(), the engine
    downgraded it to CANNOT_MEASURE, and SuccessExitStatus=0 2 made the boot
    unit report success — the one check that detects a cloned VM or swapped
    disk silently stopped detecting anything. This proves run() itself
    handles the corruption directly, never raising.
    """
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "node_identity.json").write_bytes(b"\xff\xfe")
    loaded = load_check(CHECKS, "check_node_identity")
    assert loaded.run is not None
    result = loaded.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "corrupt" in result.detail
