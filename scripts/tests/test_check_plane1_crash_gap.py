"""`check_plane1_crash_gap` — the DETECTION can-fail, committed rather than banked.

ARC 035 / Stage 1 / sub-agent B. Every plant below takes a **REAL drill result**
— two ephemeral PostgreSQL clusters really built, really crashed with
`pg_ctl -m immediate`, really traced — and mutates exactly ONE field before
driving the SHIPPED `inspect_drill` against it. That is why the drill is run once
in a module-scoped fixture and deep-copied per plant: a fabricated dict would
prove the arms can read a dict, and nothing about the boundary.

**The CONTROL is first and it is load-bearing.** Without a green over the
unmutated drill result, every red below could be the fixture rather than the
plant.

The system cluster is never touched. Every cluster the drill builds is its own,
created with `initdb` under a private socket directory with
`listen_addresses = ''`, and destroyed on the way out.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 pairs this arc's Plane-1 modules by their shared psql helpers and
# scratch-cluster fixtures — required by §4.2, not accidental.
# pylint: disable=use-implicit-booleaness-not-comparison
# `== []` / `== ()` is the assertion, not a style choice: these subjects
# are defect LISTS, and `not x` would also pass on the None a gate that
# failed to run returns. The explicit comparison distinguishes "measured
# and clean" from "did not measure", which is the whole of §17.
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
import copy
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import check_plane1_crash_gap as gate  # pylint: disable=import-error
import plane1_crash_drill as drill  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error


def _pg_available() -> bool:
    try:
        for binary in ("initdb", "pg_ctl", "postgres", "psql"):
            drill.pg_bin(binary)
    except RuntimeError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _pg_available() or shutil.which("strace") is None,
    reason="initdb/pg_ctl/postgres/strace unavailable; an unbuildable or "
    "unobservable durability boundary is CANNOT_MEASURE, never PASS",
)


@pytest.fixture(name="real", scope="module")
def _real() -> dict:
    """ONE real drill: two crashed clusters plus the fsync=off control."""
    return drill.run_drill()


@pytest.fixture(name="plant")
def _plant(real):
    def build(**_unused) -> dict:
        return copy.deepcopy(real)

    return build


# ------------------------------------------------------------- the CONTROL


def test_control_a_real_unmutated_drill_inspects_clean(real) -> None:
    """The green every red below is attributed against."""
    assert gate.inspect_drill(copy.deepcopy(real)) == [], gate.inspect_drill(
        copy.deepcopy(real)
    )


def test_the_shipped_gate_passes_end_to_end() -> None:
    """The gate, unmodified, building and crashing its own clusters."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"boundary not buildable here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    assert "DISCRIMINATES" in result.evidence
    assert "No power-loss claim" in result.evidence


# ------------------------------------------------------ ARM 1: the syscall


def test_an_UNOBSERVED_fsync_reddens_the_gate(plant) -> None:
    """`synchronous_commit = on` is a setting; the syscall is the measurement."""
    result = plant()
    assert result["durable"]["wal_fsync_lines_at_commit"] > 0, "plant anchor absent"
    result["durable"]["wal_fsync_lines_at_commit"] = 0
    defects = gate.inspect_drill(result)
    assert any(d.startswith("ARM1") and "no fsync" in d for d in defects), defects


def test_a_CONTROL_that_also_fsyncs_reddens_the_gate(plant) -> None:
    """The absent half is what gives the present half meaning.

    If the `fsync = off` cluster also shows pg_wal fsyncs, then "we matched an
    fsync line" is satisfied by any fsync anywhere in a busy trace, and arm 1 has
    stopped being a detector.
    """
    result = plant()
    assert result["fsync_control"]["wal_fsync_lines"] == 0, "plant anchor absent"
    result["fsync_control"]["wal_fsync_lines"] = 7
    defects = gate.inspect_drill(result)
    assert any(d.startswith("ARM1 CONTROL") for d in defects), defects


def test_an_ABSENT_strace_is_CANNOT_MEASURE_not_a_skipped_arm(plant) -> None:
    """§17: a safety property proven while its subject is unobservable is not
    proven. The arm must say it measured nothing, not quietly pass the rest."""
    result = plant()
    result["durable"]["strace_available"] = False
    defects = gate.inspect_drill(result)
    assert any("ARM1 CANNOT_MEASURE" in d for d in defects), defects
    assert any("unobserved syscall" in d for d in defects), defects


# ------------------------------------------------------- ARM 2: the crash


def test_COMMITTED_ROWS_THAT_DO_NOT_COME_BACK_redden_the_gate(plant) -> None:
    """§9's group-commit is the durable record of money truth."""
    result = plant()
    assert result["durable"]["committed_survived"] is True, "plant anchor absent"
    result["durable"]["committed_survived"] = False
    result["durable"]["rows_after_recovery"] = 3
    defects = gate.inspect_drill(result)
    assert any(
        d.startswith("ARM2") and "COMMITTED rows survived" in d for d in defects
    ), defects


def test_a_CLEAN_START_instead_of_a_CRASH_RECOVERY_reddens_the_gate(plant) -> None:
    """A crash test whose server did not crash measures an ordinary restart."""
    result = plant()
    assert result["durable"]["crash_recovery_in_server_log"] is True, "plant anchor"
    result["durable"]["crash_recovery_in_server_log"] = False
    defects = gate.inspect_drill(result)
    assert any(d.startswith("ARM2") and "no crash recovery" in d for d in defects), (
        defects
    )


def test_TOO_FEW_COMMITTED_ROWS_is_CANNOT_MEASURE(plant) -> None:
    """'They all came back' over a set small enough to be an accident."""
    result = plant()
    result["durable"]["rows_before_crash"] = 1
    defects = gate.inspect_drill(result)
    assert any(
        "ARM2 CANNOT_MEASURE" in d and "below the floor" in d for d in defects
    ), defects


# -------------------------------------------------- ARM 3: the uncommitted tail


def test_an_UNCOMMITTED_TAIL_THAT_SURVIVES_reddens_the_gate(plant) -> None:
    """An uncommitted write becoming durable is a torn record: the log would hold
    transitions the system never decided."""
    result = plant()
    assert result["durable"]["uncommitted_survived"] is False, "plant anchor absent"
    result["durable"]["uncommitted_survived"] = True
    defects = gate.inspect_drill(result)
    assert any(
        d.startswith("ARM3") and "never committed SURVIVED" in d for d in defects
    ), defects


def test_a_LOST_DISCLAIMER_on_the_transaction_boundary_reddens_the_gate(plant) -> None:
    """The disclaimer is part of the result, not commentary about it.

    The uncommitted-tail arm would pass under a bare `kill -9`. A JSON blob that
    lost the sentence saying so would be read as a durability measurement, which
    is the one thing it is not.
    """
    result = plant()
    result["durable"]["boundary"] = "committed rows survived the crash"
    defects = gate.inspect_drill(result)
    assert any(d.startswith("ARM3") and "boundary" in d for d in defects), defects


# ------------------------------- ARM 4: the arm this gate exists for


def test_a_CRASH_TEST_THAT_STOPS_DISCRIMINATING_reddens_the_gate(plant) -> None:
    """THE VACUITY ARM.

    If the `fsync = off` cluster survives the crash exactly as the `fsync = on`
    one does, then `pg_ctl -m immediate` no longer distinguishes a durable
    cluster from a cluster with no durability guarantee at all — which is the arc
    brief's own §0a failure, in the instrument rather than in the subject. This
    gate calls that a defect **of the instrument** and says so, instead of
    collecting one more green.
    """
    result = plant()
    assert result["durable"]["committed_survived"] is True
    assert result["fsync_off_contrast"]["committed_survived"] is False, "plant anchor"
    result["fsync_off_contrast"]["committed_survived"] = True
    defects = gate.inspect_drill(result)
    assert any(d.startswith("ARM4") and "VACUOUS" in d for d in defects), defects
    assert any("stopped discriminating" in d for d in defects), defects


def test_a_LOST_POWER_LOSS_DISCLAIMER_reddens_the_gate(plant) -> None:
    """Nothing in the drill drops a page cache, and the result must keep saying so."""
    result = plant()
    result["boundary"] = "durable"
    defects = gate.inspect_drill(result)
    assert any(d.startswith("ARM4") and "power loss" in d for d in defects), defects


def test_the_gate_declares_falsifiable_resources() -> None:
    """D3.152: a token no observation could contradict is not a declaration."""
    # RE-BANKED at ARC 035 Stage 2 integration. `check_observed_resource_claims`
    # ran over this gate on the MERGED tree and found the declaration FALSE: the
    # ephemeral cluster writes thousands of files under its own /tmp directory
    # and the branch declared only the subprocesses that do it. §4.4 is explicit
    # that a declaration is checked against OBSERVED claims and not against the
    # other declarations, which is exactly why the branch's own green could not
    # see this. Every token below still names something the process table or the
    # filesystem can contradict (D3.152).
    assert gate.RESOURCES == (
        "file-write:/tmp",
        "subprocess:createdb",
        "subprocess:pg_isready",
        "subprocess:initdb",
        "subprocess:pg_ctl",
        "subprocess:postgres",
        "subprocess:psql",
        "subprocess:strace",
    )
    assert gate.CORRECTABLE is False
    assert gate.SUBJECTS == ("scripts/plane1_crash_drill.py",)
