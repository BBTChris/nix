"""ARC 038 / sub-agent E — I8, *"the Limiter is the SOLE Plane-1 writer"*, attacked.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §9:549 (*Persistence Model,
event-sourced* — *"**Limiter = sole writer.** Enqueue → **durable local WAL** →
shared-pool writer → **group-commit** to Postgres. Crash gap healed by startup
reconciliation vs broker truth."*), §12.10:729 (*Plane 1 … **no new writers,
ever***) and §14:965 (locked invariants).

This is an ULTRAREVIEW instrument, not a build-arc suite. Everything here exists
because the ARC 038 audit RAISED it; the findings are written up in
`downloads/arc038_findings_E.md` and each test names the one it stands over.

------------------------------------------------------------------------------
debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS SUITE TO MEASURE NOTHING?
------------------------------------------------------------------------------
1. **The canonicality control could only ever run the PROTECTED half.** ARC 035
   measured that self-mask three times. *Closed:* every control here runs the
   UNPROTECTED half first — `_pre_fix_natural_key`, which is the expression
   `natural_key_for` carried before FE4 was discharged, byte for byte — and
   REQUIRES the bad outcome to appear before requiring it gone. A control that
   never saw the defect would have proven nothing about the fix.
2. **The append-only control could be refused for the wrong reason.** A typo, a
   dead server and a missing table all refuse. *Closed:* SQLSTATE `42501` AND
   `permission denied for table plane1_event_log` are both asserted
   (check-contract rule 11 / `nix_check_contract.md` §18 — never the exit code
   alone).
3. **The crash control could kill a process that had already finished**, so
   "the gap is one-sided" would be a statement about a completed run. *Closed:*
   the child ANNOUNCES on stdout that it has committed its first group and is
   still draining; the kill happens on that line, and the suite asserts
   `WIFSIGNALED` with signal 9 rather than trusting a return code.
4. **The crash control could measure an EMPTY gap.** *Closed:* the gap is
   asserted to be strictly positive before its one-sidedness is judged — an
   empty gap is one-sided for free.
5. **Postgres could be absent**, and every database arm would silently skip.
   *Closed:* `pytest.mark.skipif` names the reason, and the arms that need no
   database (canonicality, the composed statement) still run.
6. **The scratch database could differ from the shipped schema.** *Closed:*
   every database here is built by the SHIPPED `scripts/provision_plane1.py`
   from the SHIPPED `databases/schema/plane1.sql`, and the provisioner's own
   independent re-inspection must report `created` before a row is driven. The
   live `nix_plane1` is never mutated by this file.

Doctrine C.9 boundary, stated so the next author does not add a duplicate: WHO
may write is `check_plane1_sole_writer`; WHICH §12.10 types land is
`check_plane1_event_coverage`; the SQL, the mapping and batch atomicity are
`test_plane1_sink.py`; the fsync syscall is `check_plane1_wal`. What is HERE and
nowhere else is (i) the natural key's CANONICALITY — that one event has one
identity whichever side of the disk it is read from — (ii) the CAUSE of the
log's append-only refusal, run as a both-halves control, and (iii) exactly-once
across a REAL `SIGKILL`.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# House convention: test names SHOUT the property, in the case the contract
# uses. Same disables as the sibling Plane-1 suites.
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
for _path in (str(SCRIPTS),):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position
import provision_plane1  # pylint: disable=import-error
from nixrisk import plane1_sink  # pylint: disable=import-error
from nixrisk.plane1_sink import (  # pylint: disable=import-error
    LIMITER_ROLE,
    LOG_TABLE,
    SQLSTATE_INSUFFICIENT_PRIVILEGE,
    Plane1PostgresSink,
    natural_key_for,
)
from nixrisk.seam import EventKind, EventRow  # pylint: disable=import-error
from nixrisk.wal import (  # pylint: disable=import-error
    GroupCommitWriter,
    Plane1Wal,
    decode_record,
    encode_row,
    recover,
)

SCHEMA_SQL = REPO / "databases" / "schema" / "plane1.sql"

pytestmark = pytest.mark.skipif(
    shutil.which("psql") is None or shutil.which("createdb") is None,
    reason="no local PostgreSQL client; the subject is a live database",
)


def _psql(db: str, sql: str) -> subprocess.CompletedProcess:
    """One psql invocation. VERBOSITY=verbose so the SQLSTATE reaches stderr."""
    return subprocess.run(  # nosec B603,B607 - fixed argv, no shell, PATH tool
        [
            "psql",
            "-d",
            db,
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=verbose",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(name="database")
def _database() -> Iterator[str]:
    """A throwaway Plane-1 database, built by the SHIPPED provisioner."""
    name = provision_plane1.SCRATCH_PREFIX + "a038e_" + uuid.uuid4().hex[:10]
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


# ---------------------------------------------------------------------------
# FE4 — the natural key's CANONICALITY, with the UNPROTECTED half first.
# ---------------------------------------------------------------------------


#: `natural_key_for`'s body EXACTLY as it stood before ARC 038 / sub-agent E's
#: FE4 was discharged. This is the UNPROTECTED half of every canonicality
#: control below, and it is here rather than described because a both-halves
#: control that cannot run its own unprotected half is the ARC 035 self-mask.
def _pre_fix_natural_key(row: EventRow) -> str:
    body = encode_row(row).split(b" ", 1)[1].rstrip(b"\n")
    return f"{row.kind.value}:{hashlib.sha256(body).hexdigest()[:40]}"


#: Every coercion `wal.decode_record` applies on the way back off disk, as a row
#: that TRIPS it. `EventRow`'s annotations forbid each of these values and
#: nothing enforces them, which is why the key had to stop depending on them.
_UNCOERCED_ROWS: tuple[tuple[str, EventRow], ...] = (
    (
        "int ts (annotation says float; decode_record floats it)",
        EventRow(
            kind=EventKind.CLOSED,
            ts=1_755_004_000,  # type: ignore[arg-type]
            strategy_id="S",
            reason="r",
            trade_id="T",
            fields={"symbol": "ES"},
        ),
    ),
    (
        "int field value (decode_record str()s it)",
        EventRow(
            kind=EventKind.CLOSED,
            ts=1_755_004_000.0,
            strategy_id="S",
            reason="r",
            trade_id="T",
            fields={"symbol": "ES", "qty": 5},  # type: ignore[dict-item]
        ),
    ),
    (
        "float field value",
        EventRow(
            kind=EventKind.CLOSED,
            ts=1_755_004_000.0,
            strategy_id="S",
            reason="r",
            trade_id="T",
            fields={"symbol": "ES", "px": 4500.25},  # type: ignore[dict-item]
        ),
    ),
    (
        "bool field value",
        EventRow(
            kind=EventKind.PROTECTIVE_EXIT,
            ts=1_755_004_001.0,
            strategy_id="S",
            reason="r",
            trade_id="T",
            fields={"symbol": "ES", "protective": True},  # type: ignore[dict-item]
        ),
    ),
    (
        "int trade_id (decode_record str()s it)",
        EventRow(
            kind=EventKind.CLOSED,
            ts=1_755_004_002.0,
            strategy_id="S",
            reason="r",
            trade_id=17,  # type: ignore[arg-type]
            fields={"symbol": "ES"},
        ),
    ),
)


def _round_tripped(row: EventRow) -> EventRow:
    """The row as `GroupCommitWriter` will actually hand it to the sink.

    Not a copy and not a re-construction: the REAL codec, out through
    `encode_row` and back through `decode_record`, which is the only path a
    group-commit ever takes (`GroupCommitWriter.drain_once` reads its rows from
    `recover()`, never from memory).
    """
    return decode_record(encode_row(row).rstrip(b"\n"))


def test_the_UNPROTECTED_half_really_produces_TWO_KEYS_for_ONE_EVENT() -> None:
    """The bad outcome must APPEAR, or the fix below is over nothing (§0a)."""
    split = [
        label
        for label, row in _UNCOERCED_ROWS
        if _pre_fix_natural_key(row) != _pre_fix_natural_key(_round_tripped(row))
    ]
    assert split == [label for label, _ in _UNCOERCED_ROWS], (
        "the pre-fix key must give ONE EVENT TWO IDENTITIES for every coercion "
        f"decode_record applies; it only split on {split}. If this list is "
        "short the control below is measuring nothing"
    )


def test_the_natural_key_is_CANONICAL_across_the_WAL_ROUND_TRIP() -> None:
    """FE4, protected half: one event, one identity, whichever side of the disk."""
    for label, row in _UNCOERCED_ROWS:
        assert natural_key_for(row) == natural_key_for(_round_tripped(row)), (
            f"{label}: natural_key_for is not canonical. ON CONFLICT "
            f"(natural_key, occurred_at) DO NOTHING cannot deduplicate a "
            f"re-delivery it does not recognise, so §9's exactly-once record "
            f"would carry the same money event twice"
        )


def test_the_canonicalisation_moves_NO_key_the_annotations_ALLOW() -> None:
    """A fix that changed conforming keys would orphan every banked row."""
    for kind in (EventKind.SIGNAL, EventKind.CLOSED, EventKind.HALT_SET):
        for trade_id in ("t0", None):
            row = EventRow(
                kind=kind,
                ts=1_755_200_000.0,
                strategy_id="s0",
                reason="row 0",
                trade_id=trade_id,
                fields={"symbol": "ES", "qty": "5"},
            )
            assert natural_key_for(row) == _pre_fix_natural_key(row), (
                f"{kind.name}/{trade_id!r}: the canonicalisation must be the "
                f"IDENTITY on every value EventRow's annotations allow, or it "
                f"is a schema migration wearing a bug fix's clothes"
            )


def test_a_REPLAY_of_an_UNCOERCED_row_is_DEDUPLICATED_by_the_REAL_sink(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FE4 end to end, in real Postgres, with the unprotected half first.

    Half one runs the sink with the PRE-FIX key and requires the SAME EVENT to
    land TWICE — a duplicated money row, which is the harm. Half two runs the
    shipped key and requires the replay to land ZERO.
    """
    label, template = _UNCOERCED_ROWS[1]
    assert "int field" in label

    def _at(ts: float) -> EventRow:
        """The same uncoerced event, at a distinct instant per half.

        The halves need distinct `occurred_at` values because the unique index is
        `(natural_key, occurred_at)` and the CANONICAL key of the event equals the
        PRE-FIX key of its own round-trip — which is the defect, and which would
        otherwise make the protected half collide with the unprotected half's
        second row and report a dedup it did not cause.
        """
        return EventRow(
            kind=template.kind,
            ts=ts,
            strategy_id=template.strategy_id,
            reason=template.reason,
            trade_id=template.trade_id,
            fields=dict(template.fields),
        )

    unprotected, replay_u = _at(1_755_600_000.0), _round_tripped(_at(1_755_600_000.0))
    monkeypatch.setattr(plane1_sink, "natural_key_for", _pre_fix_natural_key)
    broken = Plane1PostgresSink(database)
    assert broken.commit([unprotected]) == 1
    assert broken.commit([replay_u]) == 1, (
        "the UNPROTECTED half must DUPLICATE the event — if the pre-fix key "
        "already deduplicated it, this control measures nothing"
    )
    assert broken.rows_deduplicated == 0
    at_unprotected = _psql(
        database,
        "select count(*) from plane1_event_log "
        "where occurred_at = to_timestamp(1755600000.0)",
    ).stdout.strip()
    assert at_unprotected == "2", (
        f"one event, two rows: that is the FE4 harm and the control must see it "
        f"(saw {at_unprotected})"
    )

    monkeypatch.undo()
    protected, replay_p = _at(1_755_600_500.0), _round_tripped(_at(1_755_600_500.0))
    fixed = Plane1PostgresSink(database)
    assert fixed.commit([protected]) == 1, "a fresh event still lands"
    assert fixed.commit([replay_p]) == 0, (
        "the shipped key must recognise the WAL round-trip of the SAME event "
        "and DO NOTHING (§12.4's reconnect heal re-presents buffered records)"
    )
    assert fixed.rows_deduplicated == 1
    at_protected = _psql(
        database,
        "select count(*) from plane1_event_log "
        "where occurred_at = to_timestamp(1755600500.0)",
    ).stdout.strip()
    assert at_protected == "1", (
        f"the protected half must leave exactly ONE row for the one event, "
        f"got {at_protected}"
    )


# ---------------------------------------------------------------------------
# FE1 — the CAUSE of the log's append-only refusal. Both halves, always.
# ---------------------------------------------------------------------------

#: The three verbs `plane1.sql` says no writer may hold. Written as LITERALS
#: rather than interpolated from `LOG_TABLE`: the table name is asserted against
#: the constant separately (below), and a literal keeps bandit's B608 honest
#: instead of buying a `# nosec` on a statement that has no variable in it.
_MUTATIONS: tuple[tuple[str, str], ...] = (
    ("UPDATE", "UPDATE plane1_event_log SET reason = 'rewritten'"),
    ("DELETE", "DELETE FROM plane1_event_log"),
    ("TRUNCATE", "TRUNCATE plane1_event_log"),
)

#: The literals above name the table this suite's subject writes. If the constant
#: and the literals ever part, every mutation arm would be aimed at a table that
#: does not exist and would be "refused" for the wrong reason entirely.
assert LOG_TABLE == "plane1_event_log", LOG_TABLE


def _seed_one_row(database: str, tmp_path: Path) -> None:
    """One row through §9's own path, so there is something to try to rewrite."""
    wal_path = tmp_path / f"seed-{uuid.uuid4().hex[:8]}.wal"
    wal = Plane1Wal(wal_path)
    writer = GroupCommitWriter(wal, Plane1PostgresSink(database))
    try:
        wal.enqueue(
            EventRow(
                kind=EventKind.CLOSED,
                ts=1_755_300_000.0,
                strategy_id="arc038e",
                reason="the row the mutation arms try to rewrite",
                trade_id="arc038e-1",
                fields={"symbol": "ES"},
            )
        )
        wal.sync_to_disk()
        result = writer.drain_once()
        assert result.committed == 1, result.error
    finally:
        wal.close()
        wal_path.unlink(missing_ok=True)


def test_the_APPEND_ONLY_refusal_is_caused_by_the_ROLE_and_by_NOTHING_ELSE(
    database: str, tmp_path: Path
) -> None:
    """FE1's control half. §9: *Never overwrite* — enforced by GRANT, on a ROLE.

    `plane1.sql`'s own argument is *"APPEND-ONLY BY PRIVILEGE, NOT BY TRIGGER …
    the writer role is GRANTed SELECT and INSERT … and is granted nothing
    else, ever."* This is that claim measured in BOTH directions, because a
    refusal on its own is also true of a dead server, a renamed table and a
    database nobody can reach:

    * **UNPROTECTED** — the same statements, in the same session, WITHOUT
      assuming the role, must be ACCEPTED. That is what makes the refusal below
      attributable to the role rather than to anything else in the environment.
    * **PROTECTED** — under `SET LOCAL ROLE nix_limiter`, every mutation must be
      refused with SQLSTATE 42501 naming the TABLE.

    The unprotected half is not a hypothetical: it is the identity every process
    in this tree connects as, which is ARC 038 finding FE1 and CHECK-DEBT
    D3.388. This suite does not assert that it SHOULD be accepted — it asserts
    that the refusal is caused by the role, and the unprotected half is how that
    causation is established.
    """
    _seed_one_row(database, tmp_path)

    for verb, statement in _MUTATIONS:
        proc = _psql(database, f"BEGIN; {statement}; ROLLBACK;")
        assert proc.returncode == 0, (
            f"UNPROTECTED half: {verb} on {LOG_TABLE} was refused without any "
            f"role assumed — {proc.stderr.strip()[-300:]}. The PROTECTED half's "
            f"refusal would then be attributable to something other than the "
            f"grant, and this control would be measuring the environment"
        )

    for verb, statement in _MUTATIONS:
        proc = _psql(
            database,
            f"BEGIN; SET LOCAL ROLE {LIMITER_ROLE}; {statement}; ROLLBACK;",
        )
        assert proc.returncode != 0, (
            f"PROTECTED half: {verb} on {LOG_TABLE} SUCCEEDED as "
            f"{LIMITER_ROLE}. §9's 'Never overwrite' is gone"
        )
        assert SQLSTATE_INSUFFICIENT_PRIVILEGE in proc.stderr, (
            f"{verb} was refused but NOT with SQLSTATE "
            f"{SQLSTATE_INSUFFICIENT_PRIVILEGE}: a typo, an absent table and a "
            f"dead server refuse just as loudly — {proc.stderr.strip()[-300:]}"
        )
        assert f"permission denied for table {LOG_TABLE}" in proc.stderr, (
            f"{verb} was refused with the right SQLSTATE for the WRONG OBJECT: "
            f"{proc.stderr.strip()[-300:]}"
        )


def test_the_sink_NEVER_composes_a_write_without_assuming_the_ROLE(
    database: str,
) -> None:
    """The role is the ONLY boundary the transport has, so it is asserted.

    `_run_psql` passes no `-U`: the connection is whatever the OS user resolves
    to under `pg_hba`, so `SET LOCAL ROLE` is the entire distance between the
    shipped writer and an arbitrary process on the box (FE1). A `commit()` that
    stopped composing it would write the money record under the connecting
    identity, and nothing else in the tree would notice.
    """
    captured: dict[str, str] = {}

    def _spy(_db: str, sql: str, **_kw: object) -> subprocess.CompletedProcess[str]:
        """Intercept the composed statement. No database is touched."""
        captured["sql"] = sql
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    sink = Plane1PostgresSink(database)
    # The transport IS the private `_run_psql`; substituting the public seam
    # would measure a different object. Named rather than reached around.
    original = plane1_sink._run_psql  # pylint: disable=protected-access
    try:
        plane1_sink._run_psql = _spy  # type: ignore[assignment]  # pylint: disable=protected-access
        sink.commit(
            [
                EventRow(
                    kind=EventKind.SIGNAL,
                    ts=1_755_400_000.0,
                    strategy_id="arc038e",
                    reason="statement shape",
                    trade_id="arc038e-2",
                    fields={"symbol": "ES"},
                )
            ]
        )
    finally:
        plane1_sink._run_psql = original  # type: ignore[assignment]  # pylint: disable=protected-access

    statement = captured["sql"]
    assert f"SET LOCAL ROLE {LIMITER_ROLE};" in statement, (
        f"the group-commit statement does not assume the sole writer's role: "
        f"{statement[:200]!r}"
    )
    assert statement.index(f"SET LOCAL ROLE {LIMITER_ROLE};") < statement.index(
        f"INSERT INTO {LOG_TABLE}"
    ), "the role must be assumed BEFORE the INSERT, not after it"
    assert "SET ROLE" not in statement.replace("SET LOCAL ROLE", ""), (
        "a bare `SET ROLE` survives COMMIT, so a pooled connection would "
        "inherit the Limiter's identity for the next statement on it"
    )


# ---------------------------------------------------------------------------
# §9's crash gap, driven with a REAL SIGKILL.
# ---------------------------------------------------------------------------

_WRITER_CHILD = textwrap.dedent(
    """
    import os, sys, time
    from nixrisk.wal import Plane1Wal, GroupCommitWriter
    from nixrisk.plane1_sink import Plane1PostgresSink
    from nixrisk.seam import EventKind, EventRow
    db, wal_path, total, batch = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    wal = Plane1Wal(wal_path)
    writer = GroupCommitWriter(wal, Plane1PostgresSink(db), batch_max=batch)
    for i in range(total):
        wal.enqueue(EventRow(kind=EventKind.CLOSED, ts=1755500000.0 + i,
                             strategy_id="KILLDRILL", reason="row %d" % i,
                             trade_id="KD-%d" % i, fields={"symbol": "ES"}))
    wal.sync_to_disk()
    result = writer.drain_once()
    print("COMMITTED %d STILL-DRAINING" % result.committed, flush=True)
    while True:
        writer.drain_once()
        time.sleep(0.05)
    """
)


# Twenty-two locals, of which the load-bearing ones are the FOUR measured
# quantities the assertions compare — durable rows, banked rows, the gap, and
# the two key sets. Splitting them into helpers would put the SIGKILL in one
# frame and the reconciliation in another, and the whole property is that those
# two observations are of the same run.
# pylint: disable-next=too-many-locals
def test_the_CRASH_GAP_is_ONE_SIDED_and_EXACTLY_ONCE_survives_a_REAL_SIGKILL(
    database: str, tmp_path: Path
) -> None:
    """§9's *"crash gap healed by startup reconciliation"*, attacked with `-9`.

    The forbidden direction is a row POSTGRES holds that the WAL lost: it would
    mean a group-commit ran ahead of the fsync, and no reconciliation could ever
    find it. The permitted direction — rows on disk Postgres has not seen — is
    the gap itself, and a restarted writer with a zero cursor re-presents ALL of
    them, so exactly-once is carried entirely by the content-derived natural
    key. Both halves are asserted here.
    """
    wal_path = tmp_path / f"kill-{os.getpid()}.wal"
    env = dict(os.environ)
    keep = [
        part
        for part in env.get("PYTHONPATH", "").split(":")
        if part and Path(part).resolve() != SCRIPTS.resolve()
    ]
    # D3.344: an EXPLICIT env, with the real tree's scripts/ replaced by this
    # tree's and every other entry (the binding census's sitecustomize among
    # them) kept. A wholesale replacement makes the run invisible to the census.
    env["PYTHONPATH"] = ":".join([str(SCRIPTS)] + keep)

    # The child must OUTLIVE its `with` block: the whole point is to SIGKILL it
    # from here and then reconcile, which a context manager's implicit wait
    # would deadlock on.
    # pylint: disable-next=consider-using-with
    child = subprocess.Popen(  # nosec B603 - fixed argv, no shell
        [
            sys.executable,
            "-c",
            _WRITER_CHILD,
            database,
            str(wal_path),
            "12",
            "4",
        ],
        env=env,
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        announced = ""
        assert child.stdout is not None
        for line in child.stdout:
            announced = line.strip()
            if "STILL-DRAINING" in announced:
                break
        assert "STILL-DRAINING" in announced, (
            f"the child never announced a committed group, so the kill would "
            f"land on a process that had not started writing: {announced!r} "
            f"stderr={child.stderr.read()[-400:] if child.stderr else ''}"
        )
        os.kill(child.pid, signal.SIGKILL)
        _pid, status = os.waitpid(child.pid, 0)
    finally:
        if child.poll() is None:  # pragma: no cover - belt and braces
            os.kill(child.pid, signal.SIGKILL)
            os.waitpid(child.pid, 0)
        for stream in (child.stdout, child.stderr):
            if stream is not None:
                stream.close()

    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL, (
        f"the child must have died of a real SIGKILL, not exited: status={status}"
    )

    on_disk = recover(wal_path)
    assert on_disk.intact, (
        f"the WAL was fsynced before the kill, so nothing should be torn or "
        f"corrupt: torn={on_disk.torn_tail_bytes}B corrupt={on_disk.corrupt_records}"
    )
    banked = int(
        _psql(database, "select count(*) from plane1_event_log").stdout.strip()
    )
    gap = len(on_disk.rows) - banked
    assert gap > 0, (
        f"{len(on_disk.rows)} durable row(s) and {banked} banked leaves no gap "
        f"to judge; an empty gap is one-sided for free (§7.12 answer 4)"
    )

    wal_keys = {natural_key_for(row) for row in on_disk.rows}
    pg_keys = set(
        _psql(database, "select natural_key from plane1_event_log").stdout.split()
    )
    assert not pg_keys - wal_keys, (
        f"FORBIDDEN DIRECTION: Postgres holds {sorted(pg_keys - wal_keys)} which "
        f"the durable WAL does not. A group-commit ran ahead of the fsync and no "
        f"reconciliation vs broker truth could ever find it (§9)"
    )

    # The restart. Cursor zero, so every durable row is re-presented.
    restarted_wal = Plane1Wal(wal_path)
    restarted_wal.durable_bytes = wal_path.stat().st_size
    sink = Plane1PostgresSink(database)
    writer = GroupCommitWriter(restarted_wal, sink, batch_max=256)
    try:
        assert writer.cursor == 0
        assert writer.durable_rows() == len(on_disk.rows)
        result = writer.drain_once()
        assert not result.error, result.error
    finally:
        restarted_wal.close()
        wal_path.unlink(missing_ok=True)

    assert sink.rows_deduplicated == banked, (
        f"the heal re-presented every durable row, so exactly the {banked} "
        f"already banked must have been deduplicated, not "
        f"{sink.rows_deduplicated}"
    )
    duplicated = _psql(
        database,
        "select count(*) from (select natural_key from plane1_event_log "
        "group by natural_key having count(*) > 1) t",
    ).stdout.strip()
    assert duplicated == "0", (
        f"{duplicated} natural key(s) appear twice after the heal — §9's record "
        f"is no longer exactly-once"
    )
    total = int(_psql(database, "select count(*) from plane1_event_log").stdout.strip())
    assert total == len(on_disk.rows), (
        f"the healed record holds {total} row(s) against {len(on_disk.rows)} "
        f"durable on the WAL"
    )
