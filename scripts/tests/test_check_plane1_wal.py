"""`checks/check_plane1_wal.py` — the SHIPPED gate's bytes, driven to every red.

Structure per `docs/nix_check_contract.md` §5.1: non-vacuity FIRST, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. **Every control asserts the REASON** — the site, the named condition or
the field — never the exit code alone (check contract v2 §11).

THE BINDING MECHANISM. `check_plane1_wal.run()` reaches its subject through one
seam, `_import_drill()`, and the gate's own bytes are never touched: a plant is a
`types.SimpleNamespace` whose `run_drill` returns a DOCTORED COPY of a real
drill's observations. The real drill runs exactly ONCE for this module (the
`baseline` fixture) and every plant is a deep copy of its result with one field
changed, so a red here is attributable to that one field and the suite does not
spend a kill drill per control.

Doctrine C.8: no plant touches a production artifact. Nothing below writes to
`scripts/nixrisk/wal.py`, `scripts/wal_kill_drill.py`, or any WAL outside a
`tempfile.mkdtemp` the gate itself makes and removes.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,missing-function-docstring
# `invalid-name`: test names SHOUT the property under measurement, which is the
# house convention (`scripts/tests/test_statebus.py`) and is what makes a red
# line in the suite output readable without opening the file.
# `protected-access`: a can-fail control drives the gate's ARMS and helpers,
# which are private by design — a helper made public so a test could reach it
# would be a surface the gate did not need, invented for the test.
# `redefined-outer-name`: pytest fixtures are injected by name; that IS the API.
# `duplicate-code`: the sys.path bootstrap and the `--correct` refusal probe are
# MANDATED to be identical across suites (`nix_check_contract.md` §4.2).
# `missing-function-docstring`: a handful of one-line controls whose NAME is the
# whole statement; the rest carry docstrings.

from __future__ import annotations

import copy
import os
import signal
import subprocess
import sys
import tempfile
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

# pylint: disable=wrong-import-position
import check_plane1_wal as gate
import wal_kill_drill
from nixverify.contract import Context, Mode, Status
from nixverify.declarations import read_declaration

GATE_FILE = REPO / "checks" / "check_plane1_wal.py"


@pytest.fixture(scope="module")
def baseline() -> Iterator[dict[str, Any]]:
    """ONE real drill: two traced children, three killed/clean children, a rlimit."""
    root = Path(tempfile.mkdtemp(prefix="nixwal-test-"))
    try:
        yield wal_kill_drill.run_drill(root)
    finally:
        gate._remove_tree(root)


def _run(monkeypatch: pytest.MonkeyPatch, observations: dict[str, Any]):
    """Drive the SHIPPED gate against one set of observations."""
    drill = types.SimpleNamespace(run_drill=lambda _root: observations)
    monkeypatch.setattr(gate, "_import_drill", lambda: (drill, ""))
    return gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))


def _plant(baseline: dict[str, Any], **path_values: Any) -> dict[str, Any]:
    """A deep copy with `arm__field=value` overrides. One change per control."""
    doctored = copy.deepcopy(baseline)
    for dotted, value in path_values.items():
        arm, _, field = dotted.partition("__")
        doctored[arm][field] = value
    return doctored


# ---------------------------------------------------------------------------
# NON-VACUITY FIRST — the drill really did the things the gate reports
# ---------------------------------------------------------------------------


def test_the_drill_really_SIGKILLED_a_process_and_the_KERNEL_says_so(
    baseline: dict[str, Any],
) -> None:
    """§0a: a crash-gap test that never crashes measures nothing."""
    crash = baseline["crash"]
    assert crash["reap_status"] == -int(signal.SIGKILL), crash
    assert crash["signal_number"] == 9, crash
    assert baseline["clean"]["reap_status"] == 0, baseline["clean"]


def test_the_drill_really_OBSERVED_the_fsync_SYSCALL_against_the_WAL(
    baseline: dict[str, Any],
) -> None:
    """The syscall, named with the file. Not `Plane1Wal.fsyncs`, not a docstring."""
    traced = baseline["fsync"]
    if not traced["available"]:  # pragma: no cover - strace present on this node
        pytest.skip(traced["reason"])
    assert traced["fsync_count_for_wal"] >= 1, traced
    line = traced["fsync_lines_for_wal"][0]
    assert "fsync(" in line and traced["path"] in line, line
    assert baseline["fsync_control"]["fsync_count_for_wal"] == 0, (
        "the control saw an fsync with sync_to_disk withheld — the matcher "
        "matches anything"
    )


def test_the_drill_really_made_the_KERNEL_refuse_an_append(
    baseline: dict[str, Any],
) -> None:
    """§12.4's disk-critical, produced by RLIMIT_FSIZE and not by a mock."""
    critical = baseline["critical"]
    assert critical["state"] == "disk_critical", critical
    assert "errno=27" in critical["refusal"], critical["refusal"]
    assert critical["accepted"] > 0, "nothing was written before the refusal"


def test_a_SIGKILL_alone_would_PASS_a_WAL_that_NEVER_FSYNCED_REFUTATION(
    tmp_path: Path,
) -> None:
    """Why ARM 1 exists, measured rather than argued.

    A SIGKILL is not a power cut. The killed process's dirty pages belong to a
    kernel that is still running, so a crash-gap drill can report perfect
    recovery against a WAL whose durability verb was never called once.

    MEASURED: the drill's own producer child, run with `--no-sync` so
    `sync_to_disk` never executes (`fsyncs=0`, `durable_bytes=0`), then really
    SIGKILLed and really reaped `-9` — and every row it ever enqueued is still
    readable off the disk. A gate that proved durability by killing a process
    would be green on a WAL with the fsync deleted.
    """
    path = tmp_path / "nosync.wal"
    argv = wal_kill_drill._child_argv(
        "--produce", path, hold_s=-1.0, torn=False, no_sync=True
    )
    proc, hello = wal_kill_drill._spawn(argv)
    try:
        time.sleep(wal_kill_drill.KILL_AFTER_S)
        os.kill(proc.pid, signal.SIGKILL)
        status = proc.wait(timeout=wal_kill_drill.REAP_TIMEOUT_S)
    finally:
        if proc.poll() is None:  # pragma: no cover - only if the kill missed
            proc.kill()
            proc.wait(timeout=wal_kill_drill.REAP_TIMEOUT_S)

    assert status == -int(signal.SIGKILL), status
    assert hello["fsyncs"] == 0 and hello["durable_bytes"] == 0, hello
    recovered = wal_kill_drill.recover(path)
    assert len(recovered.rows) > gate.MIN_DURABLE_ROWS, recovered
    assert recovered.bytes_read > 0, recovered
    # The durable PREFIX, by contrast, is empty — which is the honest figure and
    # the one the gate's evidence prints beside the readable count.
    assert not wal_kill_drill.recover(path, hello["durable_bytes"]).rows


def test_the_gate_PASSES_on_the_real_drill_and_its_evidence_is_SPECIFIC(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """Step 1 and step 6 of §5.1 — the control for every plant below."""
    result = _run(monkeypatch, baseline)
    assert result.status is Status.PASS, (result.status, result.detail)
    assert "FSYNC OBSERVED" in result.evidence, result.evidence
    assert "SIGKILL reaped -9" in result.evidence, result.evidence
    assert "§12.4 DISTINCTION HELD" in result.evidence, result.evidence
    assert "TORN TAIL" in result.evidence, result.evidence


def test_the_evidence_reports_the_GAP_between_readable_and_DURABLE(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """A SIGKILL is not a power cut, and the gate must not let a green imply it."""
    result = _run(monkeypatch, baseline)
    assert "says nothing about a power cut" in result.evidence, result.evidence
    assert (
        baseline["crash"]["recovered_rows"] > baseline["crash"]["durable_prefix_rows"]
    ), "the page cache kept nothing beyond the fsync — the gap claim needs a gap"


# ---------------------------------------------------------------------------
# ARM 1 — the fsync, and its control
# ---------------------------------------------------------------------------


def test_NO_FSYNC_reddens_and_names_sync_to_disk(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(
        monkeypatch,
        _plant(baseline, fsync__fsync_count_for_wal=0, fsync__fsync_lines_for_wal=[]),
    )
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert gate._SITE_FSYNC in result.site, result.site
    assert "NOT ONE fsync/fdatasync" in result.detail, result.detail


def test_a_CONTROL_that_also_fsyncs_reddens_because_the_arm_cannot_discriminate(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """If the withheld-sync child also shows an fsync, the matcher is worthless."""
    result = _run(monkeypatch, _plant(baseline, fsync_control__fsync_count_for_wal=3))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "THE CONTROL FAILED" in result.detail, result.detail
    assert "matcher that matches anything" in result.detail, result.detail


def test_strace_UNAVAILABLE_is_CANNOT_MEASURE_and_never_PASS(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """§17: a property proven while its instrument is unavailable is not proven."""
    monkeypatch.setattr(gate.shutil, "which", lambda _name: None)
    result = _run(
        monkeypatch,
        _plant(baseline, fsync__available=False, fsync__reason="planted absence"),
    )
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "deliberately never PASS" in result.detail, result.detail


# ---------------------------------------------------------------------------
# ARM 2 — the death, and its control
# ---------------------------------------------------------------------------


def test_a_CLEAN_EXIT_masquerading_as_a_kill_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(monkeypatch, _plant(baseline, crash__reap_status=0))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "os.kill(pid, SIGKILL)" in result.site, result.site
    assert "did not die of the signal" in result.detail, result.detail


def test_a_CONTROL_that_also_dies_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(monkeypatch, _plant(baseline, clean__reap_status=-9))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "THE CONTROL FAILED" in result.detail, result.detail


def test_an_EMPTY_recovered_WAL_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """§5.3: an empty scope is never a PASS."""
    result = _run(monkeypatch, _plant(baseline, crash__recovered_rows=0))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "deliberately never PASS" in result.detail, result.detail


# ---------------------------------------------------------------------------
# ARM 3 — the torn tail
# ---------------------------------------------------------------------------


def test_a_recovery_reader_NEVER_SHOWN_DAMAGE_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(monkeypatch, _plant(baseline, crash_torn__torn_tail_bytes=0))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "wal.py:recover" in result.site, result.site
    assert "never shown damage" in result.detail, result.detail


def test_a_torn_tail_that_COSTS_the_durable_rows_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(monkeypatch, _plant(baseline, crash_torn__corrupt_records=4))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "corrupt record(s)" in result.detail, result.detail


# ---------------------------------------------------------------------------
# ARM 4 / ARM 5 — §12.4's two failures, and the DISTINCTION between them
# ---------------------------------------------------------------------------


def test_a_DISK_CRITICAL_wal_that_still_admits_entries_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(monkeypatch, _plant(baseline, critical__admits_new_entries=True))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "admits_new_entries" in result.site, result.site
    assert "no audit trail, no new risk" in result.detail, result.detail


def test_a_DISK_CRITICAL_wal_that_BLOCKS_THE_EXIT_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """The one answer that must never depend on the disk."""
    result = _run(
        monkeypatch, _plant(baseline, critical__protective_exit_allowed=False)
    )
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "protective_exit_allowed" in result.site, result.site
    assert "stops read memory, not disk" in result.detail, result.detail


def test_a_SINK_outage_that_HALTS_TRADING_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """*Degraded persistence ≠ degraded trading.* The sharpest of the five."""
    result = _run(monkeypatch, _plant(baseline, outage__admits_new_entries=False))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "admits_new_entries" in result.site, result.site
    assert "stopped business" in result.detail, result.detail


def test_a_SILENT_sink_outage_reddens_for_the_MISSING_ALERT(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    result = _run(monkeypatch, _plant(baseline, outage__alerts=[]))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "no operator alert fired" in result.detail, result.detail


def test_a_backlog_that_NEVER_DRAINS_reddens(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    doctored = copy.deepcopy(baseline)
    doctored["outage"]["restored"]["backlog"] = 5
    result = _run(monkeypatch, doctored)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "a shredder with a delay" in result.detail, result.detail


def test_UNPLANTING_restores_PASS_on_the_same_population(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """§5.1 step 6 — the control that attributes every red above to its plant."""
    assert _run(monkeypatch, _plant(baseline, crash__reap_status=0)).status is (
        Status.FAIL_NEEDS_OPERATOR
    )
    assert _run(monkeypatch, baseline).status is Status.PASS


# ---------------------------------------------------------------------------
# Declarations and actuation
# ---------------------------------------------------------------------------


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_venv",), declaration.depends_on
    assert "subprocess:strace" in declaration.resources, declaration.resources
    assert "file-write:/tmp" in declaration.resources, declaration.resources
    assert declaration.subjects == (
        "scripts/nixrisk/wal.py",
        "scripts/wal_kill_drill.py",
    ), declaration.subjects


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "under measurement" in combined, combined


def test_an_unimportable_subject_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctrine B.2: a gate that could not reach its subject measured nothing."""
    monkeypatch.setattr(gate, "_import_drill", lambda: (None, "planted: no drill"))
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "planted: no drill" in result.detail, result.detail
