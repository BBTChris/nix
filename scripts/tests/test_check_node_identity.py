"""Node identity: stored UUID vs live disk (§10.1).

ARC 025 Wave A. This check was RETROFITTED (declarations + the full actuation
CLI, NON-CORRECTABLE per the A2 ruling), and a retrofitted check is a NEW check
whose can-fail binding does not survive the retrofit. Everything below
`RE-BINDING` re-establishes it against the REAL subject — this box's live
partition UUID — with non-vacuity asserted first, then the plant, then the
control that removes it. Every plant lives in `tmp_path`; nothing here touches
`state/node_identity.json` (doctrine C.8, and that file is 0600 identity
material besides).
"""

# R0801: see the note in test_check_python_runtime.py. Each gate's ARC 025
# re-binding stands on its own file on purpose; one shared helper would let a
# single edit silently un-bind three independent instruments.
# pylint: disable=duplicate-code
import json
import subprocess
import sys
from pathlib import Path

from nixverify.contract import Context, Mode, Status
from nixverify.declarations import read_declaration
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
CHECK_FILE = CHECKS / "check_node_identity.py"

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


# ===========================================================================
# ARC 025 — ORCHESTRATION DECLARATIONS (read statically, never by import)
# ===========================================================================


def test_every_declaration_is_present_and_statically_readable() -> None:
    """§4.4: all seven symbols readable by AST, with no named error.

    `RESOURCES` names the stored identity file at FILE granularity rather than
    the whole `state/` directory — an over-declaration serialises the plan for
    no measured reason, and a future credential gate claiming a different file
    under `state/` is genuinely disjoint from this one.
    """
    declaration = read_declaration(CHECK_FILE)
    assert not declaration.errors, declaration.errors
    for symbol in (
        "DEPENDS_ON",
        "RESOURCES",
        "TIME_BOUND",
        "CORRECTABLE",
        "NON_CORRECTABLE_REASON",
        "SUBJECTS",
    ):
        assert symbol in declaration.declared, f"{symbol} not declared"
    assert not declaration.depends_on
    assert declaration.resources == ("state/node_identity.json",)
    assert declaration.declares_resources is True
    assert declaration.time_bound is False
    assert declaration.expected_s is None
    assert declaration.correctable is False
    assert declaration.non_correctable_reason.strip()
    assert declaration.subjects == ("state/node_identity.json",)


def test_the_declared_resource_is_the_file_the_check_actually_opens() -> None:
    """An under-declaration is a false declaration. The one path this check
    opens is derived here the way `run()` derives it, so the declaration cannot
    drift away from the code without this failing.
    """
    claimed = read_declaration(CHECK_FILE).resources[0]
    # The path `run()` builds, spelled the way `run()` builds it. If either the
    # code or the declaration moves without the other, this fails.
    source = CHECK_FILE.read_text(encoding="utf-8")
    assert 'ctx.nix_home / "state" / "node_identity.json"' in source
    assert claimed == "state/node_identity.json"
    assert (REPO / claimed).is_file(), (
        "the declared resource does not exist on this box — the check would be "
        "measuring nothing"
    )


# ===========================================================================
# RE-BINDING — §0c. NON-VACUITY FIRST (doctrine C.3), then plant, then control.
# ===========================================================================


def test_non_vacuity_both_arms_of_the_comparison_have_a_real_subject() -> None:
    """Doctrine C.3, asserted BEFORE any plant.

    This gate compares two values. If either arm is structurally empty the gate
    is a comparison of nothing with nothing and would pass — or cannot-measure —
    forever. Both are asserted to be live on this box: the stored file exists
    and parses, and `findmnt`/`blkid` actually answer.
    """
    mod = _mod()
    stored, condition = mod._read_state(  # pylint: disable=protected-access
        REPO / "state" / "node_identity.json"
    )
    assert condition == "", condition
    assert stored, "the stored arm is empty — the gate has no subject to compare"
    live = mod.live_uuid()
    assert live, "findmnt/blkid did not answer — the live arm has no subject"


def test_plant_and_control_against_the_live_partition_uuid(tmp_path: Path) -> None:
    """PLANT then CONTROL, in one test so neither half can be read alone.

    The plant is on the REAL subject: a stored identity that disagrees with what
    this box's disk actually reports. The control writes the true live UUID into
    the same tmp file and shows the gate goes green again — which is what
    distinguishes *detects the mismatch* from *always fails*.

    C.8: both halves live entirely in `tmp_path`. The production
    `state/node_identity.json` is never opened for writing by this test.
    """
    mod = _mod()
    live = mod.live_uuid()
    assert live, "no live UUID — cannot bind this gate on this box"
    wrong = "deadbeef-0000-0000-0000-000000000000"
    assert wrong != live

    stored_at = tmp_path / "state" / "node_identity.json"

    # -- PLANT: a stored identity that is not this hardware. ----------------
    _state(tmp_path, wrong)
    planted = mod.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert planted.status is Status.FAIL_NEEDS_OPERATOR
    # THE SITE, and THE REASON — never the status alone.
    assert planted.site == str(stored_at), planted.site
    assert wrong in planted.detail, planted.detail
    assert live in planted.detail, planted.detail
    assert "cloned VM" in planted.detail, planted.detail
    assert live in planted.evidence, planted.evidence

    # -- REMOVE THE PLANT — the control half. ------------------------------
    _state(tmp_path, live)
    restored = mod.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert restored.status is Status.PASS, restored.detail
    assert live in restored.evidence


# ===========================================================================
# ACTUATION — the A2 ruling: NON-CORRECTABLE, and the refusal names its reason.
# ===========================================================================


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_a_flagless_invocation_is_measure_only_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """§4.3: default is verify, and a flagless check never mutates.

    Measured rather than asserted: a byte-for-byte snapshot of the target home
    before and after, plus the file listing, so a created file is caught as well
    as a modified one.
    """
    mod = _mod()
    live = mod.live_uuid()
    assert live
    _state(tmp_path, live)
    before = _snapshot(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(CHECK_FILE), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith("pass:"), proc.stdout
    assert _snapshot(tmp_path) == before, "a flagless run mutated its target"


def test_correct_and_install_refuse_and_name_the_declared_reason(
    tmp_path: Path,
) -> None:
    """A2 [ARCHITECT RULING]: identity material under 0600 `state/` is
    NON-CORRECTABLE and the engine must not synthesise a hardware identity.

    The assertion is on the REASON TEXT, read from the declaration so the test
    and the check cannot drift apart, plus the two phrases that carry the
    ruling's actual content. Exit code alone cannot tell a working refusal from
    a crash that also returns 1 (ARC 024's measured precedent).
    """
    reason = read_declaration(CHECK_FILE).non_correctable_reason
    assert reason.strip()
    before = _snapshot(tmp_path)
    for verb in ("--correct", "--install"):
        proc = subprocess.run(
            [sys.executable, str(CHECK_FILE), str(tmp_path), verb],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "NON-CORRECTABLE" in proc.stderr, proc.stderr
        assert f"refuses {verb}" in proc.stderr, proc.stderr
        assert reason in proc.stderr, proc.stderr
        assert "SYNTHESISING a hardware identity" in proc.stderr, proc.stderr
        assert "state/node_identity.json" in proc.stderr, proc.stderr
    assert _snapshot(tmp_path) == before, "a refused mutation still wrote something"


def test_the_refusal_precedes_the_session_interlock() -> None:
    """§4.3: the per-check refusal is evaluated BEFORE the session interlock.

    Otherwise an operator on a quiet box learns "no session is running" and
    infers, wrongly, that correction would have been available. Asserted on the
    text: the refusal names identity material, not the trading slice.
    """
    proc = subprocess.run(
        [sys.executable, str(CHECK_FILE), "--correct"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "NON-CORRECTABLE" in proc.stderr
    assert "nix-trading.slice" not in proc.stderr, proc.stderr
