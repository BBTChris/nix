"""`checks/check_plane1_degraded.py` — the SHIPPED gate's bytes, driven to every red.

Structure per `docs/nix_check_contract.md` §5.1: non-vacuity FIRST, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. **Every control asserts the REASON** — the site, the named condition,
the SQLSTATE — never the exit code alone (check contract v2 §11).

THE BINDING MECHANISM. The real drill runs **once** for this module (the
`baseline` fixture): one `initdb`, three postmaster boots, a `-m immediate`
crash, a `-m fast` control, fourteen trades and two `RLIMIT_FSIZE` children. Every
plant is a `copy.deepcopy` of that result with **one** field changed, driven
through the gate's own `verdict()`, so a red is attributable to that one field
and the suite does not spend a cluster per control.

Doctrine C.8: no plant touches a production artifact. Nothing here writes to
`scripts/nixrisk/degraded.py`, `scripts/plane1_degraded_drill.py`, the system
PostgreSQL cluster, or any database outside the drill's own ephemeral one.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=protected-access,duplicate-code
# `invalid-name`: test names SHOUT the property under measurement.
# `protected-access`: the controls drive the gate's ARMS, which are private by
# design — a helper made public so a test could reach it would be a surface the
# gate did not need, invented for the test.
# `duplicate-code`: the sys.path bootstrap and the `--correct` refusal probe are
# MANDATED to be identical across suites (`nix_check_contract.md` §4.2).
import copy
import subprocess
import sys
import tempfile
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

# pylint: disable=wrong-import-position
import check_plane1_degraded as gate  # pylint: disable=import-error
import plane1_degraded_drill as drill  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error
from nixverify.declarations import read_declaration  # pylint: disable=import-error

GATE_FILE = REPO / "checks" / "check_plane1_degraded.py"

pytestmark = pytest.mark.skipif(
    bool(drill.EphemeralCluster(Path(tempfile.gettempdir()) / "probe").missing()),
    reason="no server-side PostgreSQL binaries; the subject is a real cluster",
)


@pytest.fixture(scope="module")
def baseline() -> Iterator[dict[str, Any]]:
    """ONE real drill: a cluster built, crashed, starved and brought back."""
    root = Path(tempfile.mkdtemp(prefix="nixp1c-test-"))
    try:
        yield drill.run_drill(root)
    finally:
        drill.remove_tree(root)


def _plant(baseline: dict[str, Any]) -> dict[str, Any]:
    """A deep copy to break. Never the fixture itself."""
    return copy.deepcopy(baseline)


def _detail(result) -> str:
    return f"{result.status}: {result.detail}"


# ------------------------------------------------ the drill really did the work


def test_the_drill_really_STOPPED_a_real_postmaster(baseline) -> None:
    """The whole mandate rests on this: a test where Postgres never goes down
    measures neither the buffering nor the continuation."""
    crash = baseline["c1"]["crash"]
    assert crash["mode"] == "immediate"
    assert crash["postmaster_pid"] > 0
    assert crash["pid_alive_after_stop"] is False
    assert crash["socket_present_after_stop"] is False
    assert crash["connect_returncode"] != 0
    assert "socket" in crash["connect_stderr"]


def test_the_drill_really_made_the_KERNEL_refuse_the_append(baseline) -> None:
    """A mock raising OSError proves only that the code has an `except`."""
    critical = baseline["c2_critical"]
    assert critical["state"] == "disk_critical"
    assert "errno=27" in critical["refusal"]
    assert critical["accepted"] > 0


def test_the_drill_really_ran_CRASH_RECOVERY_and_the_control_did_not(baseline) -> None:
    """`recovered()` is only evidence beside a boot that must NOT recover."""
    assert baseline["c3"]["recovery_observed"] is True
    assert (
        baseline["c3"]["graceful_control"]["recovery_observed_after_graceful_stop"]
        is False
    )


def test_a_GRACEFUL_STOP_would_pass_no_rows_lost_VACUOUSLY_REFUTATION(
    baseline,
) -> None:
    """The vacuous claim, demonstrated rather than asserted.

    Change only the shutdown MODE and every row-count field stays exactly as it
    was — because a courteous shutdown loses nothing by construction. A gate that
    checked only "the counts match" would be serenely green over a drill that
    never crashed anything. ARM 1 is what refuses it.
    """
    plant = _plant(baseline)
    plant["c1"]["crash"]["mode"] = "fast"
    assert (
        plant["c3"]["rows_surviving_the_crash"]
        == (baseline["c3"]["rows_surviving_the_crash"])
    )
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, _detail(result)
    assert "BY CONSTRUCTION" in result.detail


# --------------------------------------------------------------- the CONTROL


def test_the_gate_PASSES_on_the_real_drill_and_its_evidence_is_SPECIFIC(
    baseline,
) -> None:
    result = gate.verdict(baseline)
    assert result.status is Status.PASS, _detail(result)
    for marker in (
        "OUTAGE REAL",
        "TRADING CONTINUED",
        "ALERTED",
        "DISK-CRITICAL HALTS",
        "CONTROL",
        "STOP FIRED ANYWAY",
        "CRASH RECOVERY",
        "FLUSHED IN WAL ORDER",
        "EXACTLY ONCE",
    ):
        assert marker in result.evidence, marker


def test_the_evidence_NAMES_the_filesystem_so_the_claim_is_not_over_read(
    baseline,
) -> None:
    """On a tmpfs an fsync is a no-op. The verdict says so rather than implying
    power-loss durability it did not measure."""
    result = gate.verdict(baseline)
    assert "NOT a power cut" in result.evidence
    assert baseline["c1"]["crash"]["datadir_filesystem"] in result.evidence


# ------------------------------------------------------------- ARM 1, the outage


def test_a_postmaster_STILL_ALIVE_after_the_stop_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c1"]["crash"]["pid_alive_after_stop"] = True
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "still in /proc" in result.detail
    assert gate._SITE_CRASH in result.site


def test_a_client_that_STILL_CONNECTED_after_the_stop_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c1"]["crash"]["connect_returncode"] = 0
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "an outage nobody's client noticed" in result.detail


# ---------------------------------------------- ARM 2, the backwards direction


def test_a_gate_that_HALTS_because_POSTGRES_IS_DOWN_reddens(baseline) -> None:
    """§12.4's whole sentence is 'degraded persistence ≠ degraded trading'.

    This is the hazard stated backwards, and it is the one a reasonable engineer
    implements by accident: the record degraded, so stop trading.
    """
    plant = _plant(baseline)
    plant["c1"]["decisions_during_outage"][0] = {
        "client_order_id": "p1c-0007",
        "decision": "deny",
        "rule": "global_halt",
        "reason": "postgres is unreachable",
    }
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "degraded persistence ≠ degraded trading" in result.detail
    assert "stopped business" in result.detail


def test_an_outage_that_BUFFERED_NOTHING_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c1"]["backlog_during_outage"] = 0
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "nothing was buffered" in result.detail


def test_a_gate_that_APPROVED_WITHOUT_RESERVING_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c1"]["reservations_outstanding"] = 0
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "approved nothing real" in result.detail


def test_a_stop_that_NEITHER_MOVED_NOR_FIRED_during_the_outage_reddens(
    baseline,
) -> None:
    plant = _plant(baseline)
    plant["c1"]["stop_breached_during_outage"] = []
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "MOVEMENT and a TRIGGER" in result.detail
    assert gate._SITE_STOPS in result.site


# ---------------------------------------------------------------- ARM 3, §12.9


def test_a_SILENT_postgres_outage_reddens_for_the_MISSING_ALERT(baseline) -> None:
    plant = _plant(baseline)
    plant["c1"]["warning_alerts"] = []
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "silent buffering is how a backlog becomes a surprise" in result.detail


def test_the_postgres_outage_raised_at_the_WRONG_TIER_reddens(baseline) -> None:
    """§12.9's Warning list names this case verbatim; the tier is transcribed."""
    plant = _plant(baseline)
    plant["c1"]["warning_alerts"][0]["tier"] = "info"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "transcribed, not chosen" in result.detail


def test_an_alert_carrying_NO_SNAPSHOT_reddens(baseline) -> None:
    """§12.9: alerts carry the cause and the snapshot 'not just a code'."""
    plant = _plant(baseline)
    plant["c1"]["warning_alerts"][0]["snapshot"].pop("backlog_rows")
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "without logging into the box" in result.detail


# ------------------------------------------------------ ARM 4/5, disk-critical


def test_a_DISK_CRITICAL_wal_whose_GATE_STILL_APPROVES_reddens(baseline) -> None:
    """The WAL reporting disk-critical to nobody is the defect this arm exists for."""
    plant = _plant(baseline)
    plant["c2_critical"]["gate_decision"] = "approve"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "no audit trail, no new risk" in result.detail
    assert gate._SITE_GATE in result.site


def test_a_denial_that_DOES_NOT_NAME_THE_CAUSE_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c2_critical"]["gate_reason"] = "denied"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "must NAME the rule and carry the errno" in result.detail


def test_a_disk_critical_alert_QUIETER_than_the_outage_alert_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c2_critical"]["alerts"][0]["tier"] = "warning"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "cannot be quieter than the non-halting one" in result.detail


def test_a_CONTROL_that_ALSO_DENIES_reddens_because_the_arm_cannot_discriminate(
    baseline,
) -> None:
    """A gate that denies everything satisfies ARM 4 and is worthless."""
    plant = _plant(baseline)
    plant["c2_control"]["gate_decision"] = "deny"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "THE CONTROL FAILED" in result.detail
    assert "a gate that denies everything" in result.detail


def test_a_CONTROL_that_ALSO_GOES_CRITICAL_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c2_control"]["state"] = "disk_critical"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "discriminates nothing" in result.detail


# ---------------------------------------------------- ARM 6, the faked half


def test_a_stop_tested_while_the_WAL_WAS_HEALTHY_reddens(baseline) -> None:
    """Without the append probe, 'the stop fired' is about a healthy system."""
    plant = _plant(baseline)
    plant["c2_critical"]["append_probe_raised"] = ""
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "not DiskCritical" in result.detail


def test_an_open_position_LEFT_UNPROTECTED_by_a_full_disk_reddens(baseline) -> None:
    """The half of §12.4 that is worse than the halting half.

    Halting new entries and ALSO blocking the exit leaves the book unhedged
    exactly when the system is least able to report it.
    """
    plant = _plant(baseline)
    plant["c2_critical"]["breached_ids"] = []
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "breached NOTHING" in result.detail
    assert "unhedged" in result.detail


# ------------------------------------------------- ARM 7, the crash and recovery


def test_a_restart_that_NEVER_RECOVERED_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["recovery_observed"] = False
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "indistinguishable from a clean one" in result.detail


def test_a_RECOVERY_CONTROL_that_ALSO_RECOVERS_reddens(baseline) -> None:
    """If a graceful stop recovers too, 'recovery observed' matches anything."""
    plant = _plant(baseline)
    plant["c3"]["graceful_control"]["recovery_observed_after_graceful_stop"] = True
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "matches anything and discriminates nothing" in result.detail


def test_a_COMMITTED_ROW_LOST_TO_THE_CRASH_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["rows_surviving_the_crash"] -= 1
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "hole in the auditable record of money truth" in result.detail


# ------------------------------------------------------- ARM 8, ordering


def test_a_backlog_that_NEVER_DRAINS_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["backlog_after_flush"] = 7
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "a shredder with a delay" in result.detail


def test_a_flush_in_the_WRONG_ORDER_reddens_and_names_the_AUTHORITY(baseline) -> None:
    """The WAL is the only place ordering is authoritative (§2.2)."""
    plant = _plant(baseline)
    plant["c3"]["order_matches_wal"] = False
    plant["c3"]["order_in_postgres"] = list(reversed(plant["c3"]["order_in_postgres"]))
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "commit order is BATCH order" in result.detail
    assert gate._SITE_ORDER in result.site


def test_a_GAP_in_the_committed_wal_seq_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["wal_seq_contiguous"] = False
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "enqueued and never landed" in result.detail


def test_ROWS_LOST_between_the_WAL_and_postgres_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["rows_after_flush"] -= 2
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "no rows lost" in result.detail


# --------------------------------------------------- ARM 9, the planted duplicate


def test_NO_DUPLICATE_PLANTED_reddens_because_dedup_was_never_exercised(
    baseline,
) -> None:
    plant = _plant(baseline)
    plant["c3"]["duplicate_rows_offered"] = 0
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "exercises no unique index" in result.detail


def test_a_re_delivery_that_DUPLICATED_the_rows_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["duplicate_rows_inserted"] = 4
    plant["c3"]["rows_after_redelivery"] = plant["c3"]["rows_after_flush"] + 4
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "a duplicated Plane-1 row is a duplicated record of money" in result.detail


def test_a_PLAIN_re_INSERT_that_SUCCEEDED_reddens(baseline) -> None:
    """`ON CONFLICT DO NOTHING` looks identical on a table with no index at all."""
    plant = _plant(baseline)
    plant["c3"]["duplicate_probe"]["returncode"] = 0
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "with no unique index at all the flush path looks identical" in result.detail


def test_a_duplicate_refused_for_the_WRONG_REASON_reddens(baseline) -> None:
    """A typo, an absent table and a dead server all refuse just as loudly."""
    plant = _plant(baseline)
    plant["c3"]["duplicate_probe"]["sqlstate"] = "42501"
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "not 23505 (unique_violation)" in result.detail


def test_a_duplicate_refused_for_the_WRONG_KEY_reddens(baseline) -> None:
    """23505 is a shared namespace — `plane1_positions_pkey` is one too.

    Phase 0.4 of this arc found the same shape one level down: the right SQLSTATE
    for the wrong OBJECT would have reported 'correctly refused' over a live
    second writer.
    """
    plant = _plant(baseline)
    plant["c3"]["duplicate_probe"]["stderr"] = (
        "ERROR:  23505: duplicate key value violates unique constraint "
        '"plane1_positions_pkey"\nDETAIL:  Key (trade_id)=(T1) already exists.'
    )
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "23505 is a shared namespace" in result.detail


def test_a_PROBE_that_WROTE_TO_THE_SUBJECT_reddens(baseline) -> None:
    plant = _plant(baseline)
    plant["c3"]["rows_after_probe"] = plant["c3"]["rows_after_flush"] + 1
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "a gate that writes to its subject is not measuring it" in result.detail


# ------------------------------------------------------------------ §17 and floors


def test_an_UNBUILDABLE_cluster_is_CANNOT_MEASURE_and_never_PASS() -> None:
    result = gate.verdict(
        {"available": False, "reason": "missing PostgreSQL binaries ['initdb']"}
    )
    assert result.status is Status.CANNOT_MEASURE
    assert "deliberately never PASS" in result.detail


def test_a_C2_CHILD_that_DIED_is_CANNOT_MEASURE(baseline) -> None:
    plant = _plant(baseline)
    plant["c2_critical"]["reap_status"] = 1
    result = gate.verdict(plant)
    assert result.status is Status.CANNOT_MEASURE
    assert "cannot be read as a measurement" in result.detail


def test_TOO_FEW_COMMITTED_ROWS_reddens_as_a_statement_about_a_small_set(
    baseline,
) -> None:
    plant = _plant(baseline)
    plant["c3"]["rows_committed_before_outage"] = 1
    result = gate.verdict(plant)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "statement about a small set" in result.detail


def test_an_unimportable_subject_is_CANNOT_MEASURE(monkeypatch) -> None:
    monkeypatch.setattr(gate, "_import_drill", lambda: (None, "planted import failure"))
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "planted import failure" in result.detail


def test_a_drill_that_RAISES_is_CANNOT_MEASURE(monkeypatch) -> None:
    def explode(_root):
        raise RuntimeError("planted drill failure")

    monkeypatch.setattr(
        gate,
        "_import_drill",
        lambda: (
            types.SimpleNamespace(run_drill=explode, remove_tree=drill.remove_tree),
            "",
        ),
    )
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "planted drill failure" in result.detail


# ------------------------------------------------------- unplanting, and the shape


def test_UNPLANTING_restores_PASS_on_the_SAME_population(baseline) -> None:
    """Without this, a red above could be the harness rather than the plant."""
    plant = _plant(baseline)
    plant["c2_critical"]["gate_decision"] = "approve"
    assert gate.verdict(plant).status is Status.FAIL_NEEDS_OPERATOR
    plant["c2_critical"]["gate_decision"] = baseline["c2_critical"]["gate_decision"]
    assert gate.verdict(plant).status is Status.PASS


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement.

    The RESOURCES claims in particular must be TRUE and FALSIFIABLE (D3.152): a
    check that spawns `pg_ctl` and declares nothing is not trusted, it is
    unmeasured.
    """
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_venv",), declaration.depends_on
    for claim in (
        "subprocess:initdb",
        "subprocess:pg_ctl",
        "subprocess:psql",
        "subprocess:createdb",
        "file-write:/tmp",
    ):
        assert claim in declaration.resources, (claim, declaration.resources)
    assert declaration.subjects == (
        "scripts/nixrisk/degraded.py",
        "scripts/plane1_degraded_drill.py",
    ), declaration.subjects


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "under measurement" in combined, combined
