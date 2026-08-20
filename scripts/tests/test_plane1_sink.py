"""`nixrisk.plane1_sink` + `provision_plane1` — the real Postgres end of §9.

ARC 035 / Stage 1 / sub-agent A. The transport's own behaviour, driven; the
GATES' can-fail suites are `test_check_plane1_sole_writer.py`,
`test_check_plane1_event_coverage.py` and `test_check_plane1_hot_path.py`.

The split, stated so it survives the next author (doctrine C.9): anything about
WHO may write belongs to the sole-writer gate; anything about WHICH §12.10 types
land belongs to the coverage gate; anything about the SQL, the mapping, the
natural key, batch atomicity and the provisioner's three outcomes belongs here.

Every database here is a throwaway built from the SHIPPED
`databases/schema/plane1.sql` and dropped in teardown. The live `nix_plane1` is
never mutated.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# House convention: test names SHOUT the property, in the case the contract
# uses. Same disables as the sibling suites.
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
CHECKS = REPO / "checks"
for _path in (str(SCRIPTS), str(CHECKS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position
import provision_plane1  # pylint: disable=import-error
from nixrisk.plane1_sink import (  # pylint: disable=import-error
    EVENT_KIND_TO_PLANE1,
    PLANE1_DB,
    UNMAPPED_EVENT_KINDS,
    UNROUTABLE_PLANE1_EVENTS,
    Plane1PostgresSink,
    SinkError,
    UnmappableEvent,
    max_wal_seq,
    natural_key_for,
    resolve_event_type,
)
from nixrisk.seam import EventKind, EventRow
from nixrisk.wal import GroupCommitWriter, Plane1Wal

SCHEMA_SQL = REPO / "databases" / "schema" / "plane1.sql"

pytestmark = pytest.mark.skipif(
    shutil.which("psql") is None or shutil.which("createdb") is None,
    reason="no local PostgreSQL client; the subject is a live database",
)


def _psql(db: str, sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603,B607 - fixed argv, no shell, PATH tool
        ["psql", "-d", db, "-qAt", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(name="database")
def _database() -> Iterator[str]:
    """A throwaway Plane-1 database, built by the SHIPPED provisioner."""
    name = provision_plane1.SCRATCH_PREFIX + "sink_" + uuid.uuid4().hex[:10]
    outcome, detail = provision_plane1.provision(name, SCHEMA_SQL)
    assert outcome == "created", detail
    try:
        yield name
    finally:
        subprocess.run(  # nosec B603,B607 - fixed argv, no shell, PATH tool
            ["dropdb", "--if-exists", "--force", name],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )


def _row(kind: EventKind = EventKind.SIGNAL, index: int = 0, **over) -> EventRow:
    base = {
        "kind": kind,
        "ts": 1_755_200_000.0 + index,
        "strategy_id": f"s{index}",
        "reason": f"row {index}",
        "trade_id": f"t{index}",
        "fields": {"symbol": "ES"},
    }
    base.update(over)
    return EventRow(**base)  # type: ignore[arg-type]


def _drive(database: str, rows, tmp_path: Path, *, role: str = "nix_limiter"):
    """§9's own path: enqueue -> durable WAL -> group-commit. Never `.commit()`."""
    wal = Plane1Wal(tmp_path / f"{uuid.uuid4().hex[:8]}.wal")
    sink = Plane1PostgresSink(database, role=role)
    writer = GroupCommitWriter(wal, sink, batch_max=256)
    try:
        for row in rows:
            wal.enqueue(row)
        wal.sync_to_disk()
        return writer.drain_once(), sink
    finally:
        wal.close()


# ------------------------------------------------- the two frozen vocabularies


def test_the_mapping_is_TOTAL_over_the_frozen_EventKind() -> None:
    """Every `EventKind` member is mapped or explicitly unmapped.

    `scripts/nixrisk/seam.py` is FROZEN and grows a member each time an arc
    builds the machinery that emits it. Without this assertion a new member
    would be silently dropped by the sink — a money transition enqueued into the
    WAL and never recorded. With it, the next arc to touch the seam is forced to
    make a §12.10 routing decision here.
    """
    covered = set(EVENT_KIND_TO_PLANE1) | set(UNMAPPED_EVENT_KINDS)
    assert covered == set(EventKind), sorted(
        kind.name for kind in set(EventKind) - covered
    )


def test_an_UNMAPPED_kind_is_REFUSED_not_laundered() -> None:
    """`EventKind.BOOT` has no §12.10 row. It must raise, not land elsewhere."""
    assert EventKind.BOOT in UNMAPPED_EVENT_KINDS
    with pytest.raises(UnmappableEvent) as caught:
        resolve_event_type(EventKind.BOOT)
    assert "no §12.10 Plane-1 row" in str(caught.value)


def test_the_four_strategy_lifecycle_verbs_fold_onto_ONE_type() -> None:
    """§12.10:757 is ONE row with four verbs; the verb survives in the payload."""
    verbs = (
        EventKind.FORCE_DEREGISTER,
        EventKind.KILL,
        EventKind.RELAUNCH,
        EventKind.QUARANTINE,
    )
    assert {resolve_event_type(v) for v in verbs} == {"strategy_lifecycle"}


def test_the_sink_and_the_schema_gate_name_the_SAME_database() -> None:
    """Two literals is two sources of truth; a disagreement makes both vacuous."""
    import check_plane1_schema  # pylint: disable=import-outside-toplevel

    assert PLANE1_DB == check_plane1_schema.PLANE1_DB
    assert PLANE1_DB == provision_plane1.PLANE1_DB


def test_the_UNROUTABLE_census_is_absent_from_the_mapping() -> None:
    """The declared gap and the mapping must not overlap or the census lies."""
    assert set(UNROUTABLE_PLANE1_EVENTS).isdisjoint(set(EVENT_KIND_TO_PLANE1.values()))
    # 5 -> 4 at ARC 035 Stage 2 integration: `drift_audit` became routable when
    # sub-agent D's `EventKind.DRIFT_AUDIT` and sub-agent A's mapping met on the
    # merged tree. The DISJOINTNESS assertion above is the one that matters and
    # it is what caught the overlap — a member cannot be both mapped and
    # declared-missing, and for one commit it was both.
    #
    # 4 -> 3 at ARC 042 (slice 4): `go_timeout` became routable when
    # `EventKind.GO_TIMEOUT` landed beside the emitter that needed it —
    # `scripts/limiterd.py` enqueues the row when §4:210-212's breaker fires
    # (CHECK-DEBT D3.425). This literal is DELIBERATELY a ratchet: it must be
    # lowered by the arc that builds an emitter, so a member added to the seam
    # with nothing enqueuing it cannot quietly shrink the declared gap.
    assert len(UNROUTABLE_PLANE1_EVENTS) == 3
    assert "go_timeout" not in UNROUTABLE_PLANE1_EVENTS
    assert EVENT_KIND_TO_PLANE1[EventKind.GO_TIMEOUT] == "go_timeout"


# ---------------------------------------------------------- the natural key


def test_the_natural_key_is_CONTENT_derived_not_sequence_derived() -> None:
    """A re-delivery after a restart carries a different `wal_seq`.

    If the key moved with the sequence, the reconnect flush §12.4 promises would
    duplicate every buffered row instead of deduplicating it.
    """
    row = _row(index=7)
    assert natural_key_for(row) == natural_key_for(_row(index=7))
    assert natural_key_for(row) != natural_key_for(_row(index=8))
    assert natural_key_for(row).startswith("signal:")


def test_a_reason_change_alone_changes_the_natural_key() -> None:
    """Two events identical but for their §9 reason are not the same event."""
    assert natural_key_for(_row(index=1)) != natural_key_for(
        _row(index=1, reason="a different rule fired")
    )


# ------------------------------------------------------- the write, end to end


def test_a_group_commit_lands_every_row_through_the_REAL_seam(
    database, tmp_path
) -> None:
    rows = [_row(index=i) for i in range(5)]
    result, sink = _drive(database, rows, tmp_path)
    assert result.ok, result.error
    assert result.committed == 5
    assert sink.rows_landed == 5
    banked = _psql(database, "select count(*) from plane1_event_log")
    assert banked.stdout.strip() == "5", banked.stderr


def test_every_landed_row_carries_the_FOUR_SPEC9_fields(database, tmp_path) -> None:
    """§9: *timestamp + strategy_id + trade_id + reason on every row.*"""
    result, _ = _drive(database, [_row(index=3)], tmp_path)
    assert result.ok, result.error
    got = _psql(
        database,
        "select strategy_id, trade_id, reason, "
        "extract(epoch from occurred_at)::text, symbol, payload->>'event_kind' "
        "from plane1_event_log",
    )
    fields = got.stdout.strip().split("|")
    assert fields[0] == "s3"
    assert fields[1] == "t3"
    assert fields[2] == "row 3"
    assert float(fields[3]) == pytest.approx(1_755_200_003.0)
    assert fields[4] == "ES"
    assert fields[5] == "signal"


def test_a_None_trade_id_lands_as_the_documented_SENTINEL(database, tmp_path) -> None:
    """`trade_id` is optional in the TYPE (a denial never opened a trade).

    The column is NOT NULL by design, with `'-'` as the documented "absent"
    sentinel, so "absent" and "lost" cannot be confused by a reader.
    """
    result, _ = _drive(database, [_row(index=0, trade_id=None)], tmp_path)
    assert result.ok, result.error
    got = _psql(database, "select trade_id from plane1_event_log")
    assert got.stdout.strip() == "-"


def test_the_BATCH_IS_ATOMIC_a_bad_row_lands_NONE_of_them(database, tmp_path) -> None:
    """One transaction per group-commit, proven by the all-or-nothing outcome.

    The plant is a blank `reason`, which the schema's own CHECK constraint
    refuses, placed in the MIDDLE of the batch. A per-row INSERT loop would land
    the first two and leave a half-written group behind — which is what makes
    the crash gap two-sided and §9's ordering unsound.
    """
    rows = [_row(index=0), _row(index=1), _row(index=2, reason=""), _row(index=3)]
    result, _ = _drive(database, rows, tmp_path)
    assert not result.ok
    assert "plane1_event_log_reason_nonblank" in result.error, result.error
    banked = _psql(database, "select count(*) from plane1_event_log")
    assert banked.stdout.strip() == "0", "a partial group survived the failure"


def test_a_REDELIVERED_group_is_DEDUPLICATED_not_duplicated(database, tmp_path) -> None:
    """§12.4's reconnect heal claims exactly-once. This is the mechanism.

    Two independent writers, two WALs, the same logical rows — which is exactly
    what a buffered flush after a restart looks like.
    """
    rows = [_row(index=i) for i in range(4)]
    first, _ = _drive(database, rows, tmp_path)
    assert first.committed == 4
    second, sink = _drive(database, rows, tmp_path)
    assert second.ok, second.error
    assert sink.rows_landed == 0
    assert sink.rows_deduplicated == 4
    banked = _psql(database, "select count(*) from plane1_event_log")
    assert banked.stdout.strip() == "4"


def test_wal_seq_RESUMES_from_the_log_not_from_zero(database, tmp_path) -> None:
    """A restarted writer must not re-number over the record it already banked."""
    _drive(database, [_row(index=i) for i in range(3)], tmp_path)
    assert max_wal_seq(database) == 2
    _drive(database, [_row(index=i) for i in range(10, 13)], tmp_path)
    got = _psql(database, "select wal_seq from plane1_event_log order by wal_seq")
    assert got.stdout.split() == ["0", "1", "2", "3", "4", "5"]


def test_max_wal_seq_on_an_EMPTY_log_is_minus_one(database) -> None:
    assert max_wal_seq(database) == -1
    assert Plane1PostgresSink(database).next_wal_seq() == 0


def test_a_QUOTE_in_a_reason_does_not_break_the_statement(database, tmp_path) -> None:
    """The SQL is composed as text; the escaping has to be real."""
    nasty = "denied by rule 'x'; DROP TABLE plane1_event_log; --"
    result, _ = _drive(database, [_row(index=0, reason=nasty)], tmp_path)
    assert result.ok, result.error
    got = _psql(database, "select reason from plane1_event_log")
    assert got.stdout.strip() == nasty
    still = _psql(database, "select count(*) from plane1_event_log")
    assert still.returncode == 0, "the log table did not survive the statement"


def test_a_sink_against_an_ABSENT_database_raises_SinkError() -> None:
    """A dead sink is a RESULT for §12.4, and it must carry what psql said.

    `.commit()` directly rather than through the seam: the subject here is the
    TRANSPORT's error reporting, and `drain_once` deliberately swallows the
    exception into a `CommitResult` (§12.4's outage-is-a-result). The seam-level
    version of this claim is driven in `test_check_plane1_sole_writer.py`.
    """
    sink = Plane1PostgresSink("p1a_definitely_absent_" + uuid.uuid4().hex[:8])
    with pytest.raises(SinkError) as caught:
        sink.commit([_row()])
    assert "SQLSTATE" in str(caught.value) or "does not exist" in str(caught.value)


# --------------------------------------------------------------- the provisioner


def test_provision_creates_and_INDEPENDENTLY_verifies() -> None:
    name = provision_plane1.SCRATCH_PREFIX + "prov_" + uuid.uuid4().hex[:10]
    try:
        outcome, detail = provision_plane1.provision(name, SCHEMA_SQL)
        assert outcome == "created", detail
        assert provision_plane1.classify(name) == (provision_plane1.STATE_COMPLETE, [])
    finally:
        subprocess.run(  # nosec B603,B607 - fixed argv, no shell, PATH tool
            ["dropdb", "--if-exists", "--force", name],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )


def test_provision_is_IDEMPOTENT_on_a_COMPLETE_database(database) -> None:
    """The re-run case is a no-op BY MEASUREMENT, not by assumption."""
    outcome, detail = provision_plane1.provision(database, SCHEMA_SQL)
    assert outcome == "already-provisioned", detail
    assert "nothing was written" in detail


def test_provision_REFUSES_an_INCOMPLETE_database(database) -> None:
    """The outcome that matters: a half-applied store is refused, not repaired.

    A provisioner that silently no-opped here would read "already provisioned"
    forever over a database missing a partition, and the first row falling
    outside every range would be LOST at runtime.
    """
    dropped = _psql(database, "DROP TABLE plane1_positions")
    assert dropped.returncode == 0, dropped.stderr
    outcome, detail = provision_plane1.provision(database, SCHEMA_SQL)
    assert outcome == "refused-incomplete", detail
    assert "table plane1_positions" in detail
    assert "Refused" in detail


def test_provision_dry_run_WRITES_NOTHING() -> None:
    name = provision_plane1.SCRATCH_PREFIX + "dry_" + uuid.uuid4().hex[:10]
    outcome, _ = provision_plane1.provision(name, SCHEMA_SQL, dry_run=True)
    assert outcome == "would-create"
    assert not provision_plane1.database_exists(name)


def test_provision_names_a_MISSING_SCHEMA_FILE_rather_than_creating_an_empty_db(
    tmp_path,
) -> None:
    with pytest.raises(provision_plane1.ProvisionError) as caught:
        provision_plane1.provision("p1a_never", tmp_path / "absent.sql")
    assert "does not exist" in str(caught.value)
