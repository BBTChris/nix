# pylint: disable=too-many-locals,too-few-public-methods
# The crash-gap drive names every observation it takes — committed rows,
# buffered rows, pre-crash digest, post-recovery digest, the recovery line
# from the server log — as its own local, because the assertion messages
# quote them individually when the drill fails.
# pylint: disable=duplicate-code
# R0801 must be disabled at the TOP of the file, before the docstring: the
# similarities checker reports at module scope and a pragma further down
# does not reach it. Same placement as check_nixverify_init.py and a dozen
# siblings. What it pairs here is this arc's Plane-1 modules by their shared
# psql helpers, declaration blocks and scratch-cluster fixtures — required by
# §4.2 (every check independently runnable and self-contained), and written
# by four sub-agents in worktrees that could not see each other.
"""B3 — the crash gap at a REAL durability boundary, and B2 healing it.

ARC 035 / Stage 1 / sub-agent B. Subject: `scripts/plane1_crash_drill.py`,
`scripts/nixrisk/projection.py`, `scripts/nixrisk/coldstart.py`. Authority:
`docs/nics_risk_subsystem_spec_v1.3.md` §9, §4.

==============================================================================
WHICH BOUNDARY EACH CLAIM RESTS ON — stated per test, not once at the top
==============================================================================

* `test_committed_rows_SURVIVE...` — **observed fsync** on this cluster's own
  `pg_wal/`, plus a SIGQUIT crash and a WAL recovery. The fsync is the boundary;
  the crash is only what forces the recovery.
* `test_an_fsync_off_cluster_LOSES...` — a **DIFFERENTIAL** between two clusters
  that differ in one setting. This drill predicted the crash would be vacuous —
  that an fsync=off cluster would recover the rows too, because the page cache
  belongs to a living kernel — and the measurement REFUTED that prediction on
  PostgreSQL 18.4. The prediction and the refutation are both recorded, in the
  drill's `predicted` and `measured` fields, because a prediction quietly
  rewritten to match its result is not a measurement.
* `test_the_uncommitted_tail_does_NOT_survive` — the **TRANSACTION** boundary,
  explicitly NOT a durability one. It would pass under a bare `kill -9`. Marked
  as such rather than banked as durability.
* `test_the_local_WAL_keeps_what_Postgres_lost` — `fsync(2)` observed by
  `wal_kill_drill.observe_fsync`, with its both-halves control.

A power-loss claim is made nowhere in this file. An `fsync` that returned is a
syscall the kernel completed; a drive that lies about its write cache is outside
every instrument in this tree.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 pairs this arc's Plane-1 modules by their shared psql helpers and
# scratch-cluster fixtures — required by §4.2, not accidental.
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
import shutil
import sys
import tempfile
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import plane1_crash_drill as drill  # pylint: disable=import-error
import wal_kill_drill  # pylint: disable=import-error
from nixrisk import plane1_seed  # pylint: disable=import-error
from nixrisk.coldstart import (  # pylint: disable=import-error
    ColdStart,
    GapKind,
    crash_gap,
    unexpected,
)
from nixrisk.projection import (  # pylint: disable=import-error
    PostgresProjection,
    fold_events,
    read_log,
    rebuild,
)
from nixrisk.seam import (  # pylint: disable=import-error
    BrokerTruth,
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionRow,
    PositionState,
)
from nixrisk.wal import Plane1Wal, recover  # pylint: disable=import-error

#: The trade whose rows reached Postgres before the crash, and the one whose
#: rows were still in the local WAL when it died. `T-004` is the shipped
#: fixture's still-open CL position; the gap trade is minted here and appears
#: in NO log anywhere, which is what makes it UNEXPECTED at the broker.
COMMITTED_TRADE = "T-004"
GAP_TRADE = "T-GAP"


def _pg_available() -> bool:
    try:
        drill.pg_bin("initdb")
        drill.pg_bin("pg_ctl")
        drill.pg_bin("postgres")
    except RuntimeError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _pg_available(),
    reason="initdb/pg_ctl/postgres are not available; the durability boundary "
    "cannot be built, and an unbuildable boundary is CANNOT_MEASURE, never PASS",
)


@pytest.fixture(name="drilled", scope="module")
def _drilled() -> dict:
    """Every Postgres arm, once. Three ephemeral clusters, all destroyed."""
    return drill.run_drill()


# ------------------------------------------------ the durability boundary itself


def test_the_fsync_is_OBSERVED_on_this_clusters_own_pg_wal(drilled) -> None:
    """A setting is a claim; a syscall is a measurement.

    `synchronous_commit = on` says the commit waits for the WAL to be flushed.
    `strace -y` prints the fd's target, so the arm can tell an fsync of THIS
    cluster's `pg_wal/` from an fsync of anything else the box was doing.
    """
    durable = drilled["durable"]
    if not durable["strace_available"]:
        pytest.skip("strace is not on PATH; the syscall cannot be observed")
    assert durable["wal_fsync_lines_at_commit"] > 0, durable
    assert any("pg_wal" in line for line in durable["wal_fsync_sample"])


def test_the_fsync_CONTROL_shows_the_line_ABSENT_when_the_verb_is_withheld(
    drilled,
) -> None:
    """The other half, without which the arm above passes forever.

    An arm that matched any line in a busy trace is not a detector. `fsync = off`
    is the one setting that suppresses PostgreSQL's durability verb outright, and
    the control requires the line to be ABSENT under it.
    """
    control = drilled["fsync_control"]
    if not control["strace_available"]:
        pytest.skip("strace is not on PATH; the syscall cannot be observed")
    assert control["wal_fsync_lines"] == 0, control


def test_committed_rows_SURVIVE_a_real_crash_and_recover(drilled) -> None:
    """§9's group-commit, at the boundary the fsync arm establishes.

    `pg_ctl -m immediate` is SIGQUIT to the postmaster: no checkpoint, WAL
    recovery on restart. The restarted server must actually report a crash
    recovery — a clean start would mean the crash never happened.
    """
    durable = drilled["durable"]
    assert durable["crash"]["pg_ctl_rc"] == 0, durable["crash"]
    assert durable["crash_recovery_in_server_log"] is True, durable
    assert durable["rows_before_crash"] == drill.COMMITTED_ROWS
    assert durable["rows_after_recovery"] == drill.COMMITTED_ROWS
    assert durable["committed_survived"] is True


def test_the_uncommitted_tail_does_NOT_survive_and_that_is_NOT_a_durability_claim(
    drilled,
) -> None:
    """The near edge of the crash gap. Named for what it is.

    An uncommitted transaction's rows are invisible to every other session before
    the crash and are discarded at recovery **whether or not anything was ever
    fsynced**. This arm rests on the TRANSACTION boundary and would pass under a
    bare `kill -9` of the postmaster. It is worth measuring; it is not evidence
    about fsync, and the drill's own `boundary` field says so.
    """
    durable = drilled["durable"]
    assert (
        durable["rows_visible_to_other_sessions_while_staged"] == drill.COMMITTED_ROWS
    )
    assert durable["uncommitted_survived"] is False
    assert "NOT a durability boundary" in durable["boundary"]


def test_an_fsync_off_cluster_LOSES_what_the_fsync_on_cluster_KEEPS(drilled) -> None:
    """THE §0a FINDING — and it is the OPPOSITE of what this drill predicted.

    The prediction was that `pg_ctl -m immediate` would be vacuous: a process
    crash leaves the page cache with a living kernel, so an `fsync=off` cluster
    should recover the same rows, and a test written against the crash alone
    would be green over a cluster with no durability guarantee at all.

    **Measured on PostgreSQL 18.4, two clusters differing only in their
    durability settings: the contrast cluster comes back without the committed
    rows** — measured three consecutive times as the relation being absent
    entirely. Redo runs and completes; the rows are simply not there. So the
    crash arm DOES discriminate, and the prediction is withdrawn rather than
    reworded.

    **And the reason is not the page cache.** `synchronous_commit = off` returns
    from `COMMIT` before the WAL record leaves PostgreSQL's own **shared WAL
    buffers**, which are shared memory and not the kernel's page cache; `SIGQUIT`
    destroys shared memory. The lost rows were never handed to the kernel, so the
    "a living kernel still owns the dirty pages" reasoning never reached them.
    The prediction was reasoning about the wrong buffer.

    What this still does NOT license is a power-loss claim. Nothing here drops a
    page cache; the durable cluster's rows reached the kernel and were fsynced,
    and no instrument in this tree can say what a disk does after that. The
    primary boundary remains the observed `fdatasync`.

    The assertion is on the DIRECTION, not the amount: how much a cluster with no
    durability guarantee loses is exactly the thing with no guarantee attached.
    """
    contrast = drilled["fsync_off_contrast"]
    assert contrast["fsync"] == "off"
    assert contrast["synchronous_commit"] == "off"
    assert contrast["committed_survived"] is False, contrast
    assert contrast["rows_after_recovery"] != drill.COMMITTED_ROWS, contrast
    assert "SHARED BUFFERS" in drilled["measured"], drilled["measured"]
    # The prediction is on the record beside its refutation.
    assert "VACUOUS" in drilled["predicted"]
    assert "REFUTED" in drilled["measured"]
    assert "power-loss" in drilled["boundary"]

    # And the CONTROL that makes the differential attributable: the same crash on
    # the fsync=on cluster kept every row.
    assert drilled["durable"]["committed_survived"] is True


def test_the_local_WAL_keeps_what_Postgres_lost(tmp_path) -> None:
    """§9's OTHER durability boundary, reused rather than reinvented.

    `wal_kill_drill.observe_fsync` already runs a child under
    `strace -y -e trace=fsync,fdatasync` and requires a line annotated with the
    WAL's OWN path, paired with a control that withholds the sync and requires
    the line to be absent. Both halves are driven here because the crash gap is
    exactly the set of rows that reached THIS file and not Postgres.
    """
    if shutil.which("strace") is None:
        pytest.skip("strace is not on PATH; the syscall cannot be observed")
    synced = wal_kill_drill.observe_fsync(tmp_path, sync=True)
    control = wal_kill_drill.observe_fsync(tmp_path, sync=False)
    assert synced["available"] and control["available"]
    assert synced["fsync_count_for_wal"] > 0, synced
    assert control["fsync_count_for_wal"] == 0, control


# --------------------------------------------- the gap, healed end to end (§4)


def test_the_crash_gap_is_MEASURED_and_HEALED_against_broker_truth() -> None:
    """B2 and B3 joined: the log is genuinely behind, and §4 corrects it.

    THE DISAGREEMENT, BUILT DELIBERATELY. Two trades are enqueued to the
    Limiter's local WAL and fsynced. Only the COMMITTED trade's rows are group-committed to
    Postgres; the GAP trade's are still in the WAL when the server is crashed
    with `pg_ctl -m immediate`. After recovery the rebuilt projection knows the
    first and has never heard of the second — while the broker holds both,
    because the fill really happened at the venue.

    That is §9's crash gap, and §4's disposition is not adoption: the unknown
    position is flattened before any strategy registers.
    """
    wal_path = Path(tempfile.mkdtemp(prefix="p1b-wal-")) / "limiter.wal"
    with drill.ephemeral_cluster(fsync=True, trace=False) as cluster:
        dbname = "p1b_gap"
        psql = cluster.createdb(dbname)
        cluster.load_schema(dbname)

        # The Limiter's own local WAL holds BOTH trades and is fsynced.
        wal = Plane1Wal(wal_path)
        for row in _wal_rows():
            wal.enqueue(row)
        made_durable = wal.sync_to_disk()
        assert made_durable == len(_wal_rows())

        # Group-commit lands ONLY trade A. Trade B is the gap.
        plane1_seed.seed(psql, _trade_a_events())
        before = drill.count_rows(psql)
        assert before == len(_trade_a_events())

        cluster.stop_immediate()
        cluster.start()
        psql = cluster.psql(dbname)

        # The committed rows survived; the gap did not become committed.
        assert drill.count_rows(psql) == before
        folded = fold_events(read_log(psql))
        assert {p.trade_id for p in folded.positions} == {COMMITTED_TRADE}

        # The local WAL still holds what Postgres never received.
        recovered = recover(wal_path)
        assert {r.trade_id for r in recovered.rows} >= {COMMITTED_TRADE, GAP_TRADE}

        projection = PostgresProjection(psql, source="cold start (§4)")
        truth = BrokerTruth(
            positions=(
                PositionRow(
                    COMMITTED_TRADE, "CLU6", "", 3, 0.0, PositionState.OPEN, 15
                ),
                PositionRow(GAP_TRADE, "NQU6", "", 3, 0.0, PositionState.OPEN, 20),
            ),
            balance=75_000.0,
            polled_at=1.0,
        )
        gaps = crash_gap(projection.rebuild(), truth)
        assert [g.trade_id for g in gaps] == [GAP_TRADE], gaps
        assert gaps[0].kind is GapKind.UNEXPECTED
        assert gaps[0].broker_size == 3

        # And §4's disposition, driven through the real reconciler.
        cold, plane1 = _cold_start(truth, projection)
        result = cold.boot(2.0)
        assert result.outcome.admitted is True
        assert [g.trade_id for g in unexpected(result.gap)] == [GAP_TRADE]
        booked = [r for r in plane1 if r.kind is EventKind.COLD_START][-1]
        assert booked.fields["crash_gap"] == "1"
        assert GAP_TRADE in booked.fields["crash_gap_trades"]

        # The projection now matches the log the reconcile left behind.
        report = rebuild(psql, source="post-reconcile")
        assert report.positions_written == 1
    shutil.rmtree(wal_path.parent, ignore_errors=True)


def _wal_rows() -> list[EventRow]:
    return [
        EventRow(
            kind=EventKind.ACCEPTED,
            ts=1.0,
            strategy_id="strat-es",
            reason="gate admitted",
            trade_id=COMMITTED_TRADE,
        ),
        EventRow(
            kind=EventKind.ACCEPTED,
            ts=2.0,
            strategy_id="strat-nq",
            reason="gate admitted",
            trade_id=GAP_TRADE,
        ),
    ]


def _trade_a_events() -> tuple[plane1_seed.EventSpec, ...]:
    return tuple(spec for spec in plane1_seed.SEED_HISTORY if spec.trade_id == "T-004")


def _cold_start(truth: BrokerTruth, projection):
    rows: list[EventRow] = []

    class _Broker:
        current: BrokerTruth

        def poll_truth(self) -> BrokerTruth:
            return self.current

        def market_tradable(self) -> tuple[bool, str]:
            return True, "regular session"

    broker = _Broker()
    broker.current = truth

    class _Flattener:
        def flatten(self, seen: BrokerTruth) -> tuple[FlattenTrigger, ...]:
            broker.current = BrokerTruth(
                positions=(), balance=seen.balance, polled_at=seen.polled_at + 1
            )
            return tuple(FlattenTrigger.ORPHAN for _ in seen.positions)

    class _Halt:
        def hold_in_halt(self, reason: str) -> None:
            rows.append(
                EventRow(
                    kind=EventKind.HALT_SET, ts=0.0, strategy_id="x", reason=reason
                )
            )

    class _Plane1:
        def enqueue(self, row: EventRow) -> None:
            rows.append(row)

        def sync_to_disk(self) -> int:
            return len(rows)

        def pending(self) -> int:
            return 0

    return (
        ColdStart(broker, _Flattener(), _Halt(), _Plane1(), projection=projection),
        rows,
    )
