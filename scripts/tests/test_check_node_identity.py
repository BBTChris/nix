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
    """Live: this box either matches, or has no state file yet."""
    loaded = load_check(CHECKS, "check_node_identity")
    assert loaded.run is not None
    result = loaded.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status in (
        Status.PASS,
        Status.FAIL_NEEDS_OPERATOR,
        Status.CANNOT_MEASURE,
    )
