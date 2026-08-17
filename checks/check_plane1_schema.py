#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: Plane 1 is append-only BY PRIVILEGE, and its inventory is §12.10's.

ARC 035 / Phase 0.4. Subject: the live `nix_plane1` database built by
`databases/schema/plane1.sql`, frozen in `docs/nix_plane1_schema_spec.md`.

## THE SENTENCE THE ARC BRIEF WROTE THIS GATE AGAINST

> *a schema gate that only checks tables EXIST measures nothing.*

That is correct and it is the easy trap here, because "the tables are there" is
the cheapest thing to assert about a database and it looks like coverage. Eight
of this gate's nine arms would still pass on a database where the Limiter role
held `UPDATE` on the event log — i.e. on a database where Plane 1 is not
append-only at all and §9's entire guarantee is gone. So the load-bearing arms
are 4 and 9, and arm 9 is the one that cannot be argued with:

* **ARM 4 reads the CATALOG.** `has_table_privilege` for `nix_limiter` and
  `nix_reader` against the log parent AND every partition, in both directions:
  INSERT/SELECT must be present, and UPDATE/DELETE/TRUNCATE must be ABSENT.
  Partitions individually, because a grant on a partitioned parent does not
  govern a statement that names a child directly — `UPDATE
  plane1_event_log_2026_08 SET ...` is checked against the CHILD's grants, and
  a gate that only inspected the parent would call that hole append-only.
* **ARM 9 makes the ATTEMPT.** `SET ROLE nix_limiter; UPDATE plane1_event_log
  ...` must be refused with **SQLSTATE 42501**, and `SET ROLE nix_reader;
  INSERT ...` likewise. Check-contract rule 11: the SQLSTATE is asserted, never
  merely "psql exited non-zero" — a syntax error, a missing table, a dead
  server and a refused privilege all exit non-zero, and only one of them is
  evidence about privileges. This is the §9 sole-writer property proven the way
  the brief demands: *refused by privilege, not merely absent from the code.*

`SET ROLE` is a real privilege drop even from a superuser session (`current_user`
becomes the target role and the executor checks against it), so the attempt is
made against the real privilege system and not a simulation of one.

## The other arms

2. every object in the frozen spec exists (tables, partitions, sequence, types);
3. §9's *"Timestamp + strategy_id + trade_id + reason on every row"* is
   structural — those columns exist and are NOT NULL, so a row missing one
   cannot be inserted rather than being caught later by a reader;
5. **no trigger and no rule on the log.** A `BEFORE UPDATE` trigger that raises
   is the mechanism this schema deliberately did NOT use, and its presence
   would be worse than useless: it would make the weak guarantee look like the
   strong one to anyone reading the DDL, while a superuser `ALTER TABLE ...
   DISABLE TRIGGER` or `session_replication_role = replica` walks straight past
   it, and TRUNCATE never fires it at all;
6. the exactly-once unique index on `(natural_key, occurred_at)` exists;
7. the PROJECTION is writable by the Limiter. The opposite direction on
   purpose: §9 calls the positions table *rebuildable*, and a rebuild needs
   DELETE/TRUNCATE. A gate that only ever demanded fewer privileges could be
   satisfied by revoking everything, which would leave a database that is
   beautifully append-only and cannot be reconciled;
8. `plane1_projection_meta` holds exactly one row and names its watermark.

## ARM 3 — the inventory, compared in BOTH directions

`plane1_event_enum`'s members against `SPEC_12_10_PLANE1_EVENTS`, which is
transcribed from §12.10's table (every row carrying a Plane-1 tick, and no
other). A member missing from the type is an event that CANNOT BE RECORDED. A
member present in the type and absent from §12.10 is an unaudited money event
that someone can write. Both are FAILs. A one-directional comparison would
accept the second forever.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **The database could be absent or Postgres down**, and "no defects found"
   over nothing is the purest vacuous green. *Closed:* unreachable server, or
   an absent database, is `CANNOT_MEASURE` naming the psql stderr — §17, never
   a PASS.
2. **The partition list could be empty**, so ARM 4's per-partition loop would
   run zero times and report clean. *Closed:* `MIN_PARTITIONS` requires the
   catch-all DEFAULT plus at least one range partition, or CANNOT_MEASURE.
3. **ARM 9 could pass because the statement failed for the wrong reason** — a
   typo'd table name refuses just as loudly as a privilege. *Closed:* the
   SQLSTATE must be exactly `42501`; anything else, including success, is a
   defect naming what actually came back.
4. **ARM 9's control could be missing** — if the Limiter could not INSERT
   either, then "UPDATE refused" would be true of a role with no rights at all
   and would say nothing about append-only. *Closed:* ARM 9 first performs a
   real INSERT as `nix_limiter` into a scratch-safe row and requires it to
   SUCCEED, then rolls it back. Refusal is only evidence next to a permission
   that works.
5. **The gate could inspect a DIFFERENT database from the one the Limiter
   writes.** *Closed as far as it can be, and NAMED:* the database name is a
   module constant checked against the frozen spec's own name, and the verdict
   prints it. What this gate cannot see is a Limiter configured to point
   somewhere else at runtime; that is a wiring property, not a schema property,
   and it belongs to the sole-writer gate rather than here.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 - psql IS the instrument; §9.1 forbids new deps
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
EXPECTED_S = 8.0
DEPENDS_ON: tuple[str, ...] = ()
#: This process spawns `psql`; the SOCKET to Postgres is opened by psql, not
#: here, so `subprocess:psql` is the whole of what this process observably
#: touches. A `postgres:nix_plane1` token was considered and REFUSED: no
#: observation could ever falsify it, which is exactly the unfalsifiable-token
#: debt D3.152 already records against 24 checks. Contention with any future
#: Plane-1 check is carried by the shared `subprocess:psql` claim, which the
#: planner already reads as non-disjoint.
RESOURCES: tuple[str, ...] = ("subprocess:psql",)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the privilege grant that IS the append-only guarantee; a "
    "gate authorised to re-issue grants could repair a tampered database into "
    "agreement with itself and report a green over the tampering"
)
ANCHOR = "databases/schema/plane1.sql"
SUBJECTS: tuple[str, ...] = (
    "databases/schema/plane1.sql",
    "docs/nix_plane1_schema_spec.md",
)

NAME = "check_plane1_schema"

# EVERY `# nosec B608` IN THIS FILE, ARGUED ONCE HERE RATHER THAN EIGHT TIMES.
# Bandit flags f-string SQL as a possible injection vector, which is the right
# default. Every interpolation in this file is a MODULE-LEVEL CONSTANT declared
# above — `LOG_TABLE`, `WRITER_ROLE`, `READER_ROLE`, `PLANE1_DB` — and the
# queries read `pg_catalog` / `information_schema`. No value reaches these
# strings from a caller, an environment variable, a file, or a database row.
# The one function that takes a caller-supplied name, `inspect_database(dbname)`,
# passes it to `psql -d` as an ARGV ELEMENT and never into SQL text.

#: The live Plane-1 database. Separate from `trade_history` on purpose — see
#: the schema file's boundary note.
PLANE1_DB = "nix_plane1"

#: §12.10's event inventory, every row carrying a Plane-1 tick. Transcribed,
#: not derived: deriving it from the enum under test would be the gate reading
#: its expected value out of the subject it polices — the recurring shape
#: ARC 034's audit found in all six gates it read (D3.200).
SPEC_12_10_PLANE1_EVENTS: frozenset[str] = frozenset(
    {
        "signal",
        "accepted",
        "denied",
        "filled",
        "exit_intent",
        "closed",
        "protective_exit",
        "reservation_taken",
        "reservation_released",
        "cancel",
        "go_timeout",
        "drift_audit",
        "sentinel_flatten",
        "halt_set",
        "halt_cleared",
        "operator_action",
        "strategy_lifecycle",
        "cold_start_outcome",
    }
)

LOG_TABLE = "plane1_event_log"
WRITER_ROLE = "nix_limiter"
READER_ROLE = "nix_reader"

#: §9: "Timestamp + strategy_id + trade_id + reason on every row."
REQUIRED_LOG_COLUMNS: tuple[str, ...] = (
    "occurred_at",
    "recorded_at",
    "event_type",
    "strategy_id",
    "trade_id",
    "reason",
    "wal_seq",
    "natural_key",
)
#: Of those, the ones §9 makes mandatory PER ROW, enforced structurally.
NOT_NULL_LOG_COLUMNS: tuple[str, ...] = (
    "occurred_at",
    "event_type",
    "strategy_id",
    "trade_id",
    "reason",
)

REQUIRED_TABLES: tuple[str, ...] = (
    "plane1_event_log",
    "plane1_positions",
    "plane1_projection_meta",
)
#: The DEFAULT catch-all plus at least one range partition. Below this the
#: per-partition loop is not measuring a population.
MIN_PARTITIONS = 2

#: `insufficient_privilege`. The only SQLSTATE that is evidence about grants.
SQLSTATE_INSUFFICIENT_PRIVILEGE = "42501"

#: psql under `VERBOSITY=verbose` prints the SQLSTATE as the first field of the
#: severity line — `ERROR:  42501: permission denied for table ...`. The
#: `SQLSTATE ...` spelling is what other client libraries emit; both are
#: matched so the arm is not hostage to one client's formatting, and NEITHER is
#: a bare five-character scan (a message containing an uppercase token would
#: otherwise satisfy it).
_SQLSTATE_RE = re.compile(
    r"(?:SQLSTATE[:\s]+|^(?:ERROR|FATAL|PANIC):\s+)([0-9][0-9A-Z]{4})\b",
    re.MULTILINE,
)


class PsqlUnavailable(Exception):
    """Postgres could not be reached at all — §17, never a PASS."""


def _psql(
    dbname: str, sql: str, *, verbose_errors: bool = False
) -> tuple[int, str, str]:
    """Run one SQL string. Returns `(rc, stdout, stderr)`.

    `verbose_errors` turns on psql's VERBOSITY so the SQLSTATE appears in
    stderr — without it psql prints the message only, and a message is prose
    while a SQLSTATE is a contract.
    """
    binary = shutil.which("psql")
    if binary is None:
        raise PsqlUnavailable("psql is not on PATH")
    argv = [binary, "-d", dbname, "-qAt", "-v", "ON_ERROR_STOP=1"]
    if verbose_errors:
        argv += ["-v", "VERBOSITY=verbose"]
    argv += ["-c", sql]
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        argv, capture_output=True, text=True, timeout=60, check=False
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _query(dbname: str, sql: str) -> list[list[str]]:
    """A SELECT that must succeed. Anything else is a measurement failure."""
    rc, out, err = _psql(dbname, sql)
    if rc != 0:
        raise PsqlUnavailable(f"{dbname}: {sql.strip()[:60]}... -> rc={rc}: {err}")
    return [line.split("|") for line in out.splitlines() if line]


def _sqlstate(stderr: str) -> str:
    match = _SQLSTATE_RE.search(stderr)
    return match.group(1) if match else ""


# --------------------------------------------------------------------- arms


def _arm2_objects(dbname: str) -> tuple[list[str], list[str]]:
    """Tables, partitions, sequence and types exist. Returns (defects, parts)."""
    defects: list[str] = []
    tables = {
        row[0]
        for row in _query(
            dbname,
            "select tablename from pg_tables where schemaname='public'",
        )
    }
    for required in REQUIRED_TABLES:
        if required not in tables:
            defects.append(f"ARM2: table {required} is absent from {dbname}")
    partitions = sorted(
        row[0]
        for row in _query(
            dbname,
            "select c.relname from pg_inherits i "
            "join pg_class c on c.oid = i.inhrelid "
            "join pg_class p on p.oid = i.inhparent "
            f"where p.relname = '{LOG_TABLE}'",  # nosec B608
        )
    )
    if not any(p.endswith("_default") for p in partitions):
        defects.append(
            f"ARM2: {LOG_TABLE} has no DEFAULT partition; a row whose "
            f"occurred_at falls outside every range would be REJECTED, and "
            f"losing a Plane-1 row to a missing partition is the worst "
            f"failure this schema can have"
        )
    sequences = {
        row[0]
        for row in _query(
            dbname, "select sequencename from pg_sequences where schemaname='public'"
        )
    }
    if "plane1_event_id_seq" not in sequences:
        defects.append(
            "ARM2: the explicit sequence plane1_event_id_seq is absent — an "
            "IDENTITY column on a partitioned table cannot be granted to a "
            "non-owner writer by name"
        )
    return defects, partitions


def _arm3_inventory(dbname: str) -> list[str]:
    """The event enum equals §12.10's Plane-1 inventory, both directions."""
    members = {
        row[0]
        for row in _query(
            dbname,
            "select e.enumlabel from pg_enum e join pg_type t on t.oid=e.enumtypid "
            "where t.typname='plane1_event_enum'",
        )
    }
    if not members:
        return [
            (
                "ARM3: plane1_event_enum has no members (or does not exist) — "
                "nothing to compare against §12.10"
            )
        ]
    defects: list[str] = []
    missing = sorted(SPEC_12_10_PLANE1_EVENTS - members)
    if missing:
        defects.append(
            "ARM3: §12.10 names Plane-1 event(s) the schema cannot record: "
            + ", ".join(missing)
        )
    extra = sorted(members - SPEC_12_10_PLANE1_EVENTS)
    if extra:
        defects.append(
            "ARM3: the schema can record event type(s) §12.10 does not list: "
            + ", ".join(extra)
            + " — an unaudited money event someone can write"
        )
    return defects


def _arm4_privileges(dbname: str, partitions: list[str]) -> list[str]:
    """THE APPEND-ONLY ARM. Catalog side. Parent AND every partition."""
    defects: list[str] = []
    targets = [LOG_TABLE, *partitions]
    for table in targets:
        rows = _query(
            dbname,
            "select "
            f"has_table_privilege('{WRITER_ROLE}','{table}','SELECT'), "
            f"has_table_privilege('{WRITER_ROLE}','{table}','INSERT'), "
            f"has_table_privilege('{WRITER_ROLE}','{table}','UPDATE'), "
            f"has_table_privilege('{WRITER_ROLE}','{table}','DELETE'), "
            f"has_table_privilege('{WRITER_ROLE}','{table}','TRUNCATE'), "
            f"has_table_privilege('{READER_ROLE}','{table}','SELECT'), "
            f"has_table_privilege('{READER_ROLE}','{table}','INSERT')",  # nosec B608
        )
        sel, ins, upd, dele, trunc, rsel, rins = (v == "t" for v in rows[0])
        if not sel or not ins:
            defects.append(
                f"ARM4: {WRITER_ROLE} lacks SELECT/INSERT on {table} "
                f"(select={sel} insert={ins}) — the sole writer cannot write, "
                f"so append-only here is vacuous"
            )
        for name, held in (("UPDATE", upd), ("DELETE", dele), ("TRUNCATE", trunc)):
            if held:
                defects.append(
                    f"ARM4: {WRITER_ROLE} HOLDS {name} on {table}. §9 makes "
                    f"Plane 1 append-only and §12.10 makes it the auditable "
                    f"record of money truth; a writer that can {name} a row "
                    f"can rewrite the record of what was traded"
                )
        if not rsel:
            defects.append(f"ARM4: {READER_ROLE} lacks SELECT on {table}")
        if rins:
            defects.append(
                f"ARM4: {READER_ROLE} HOLDS INSERT on {table} — §12.10's "
                f"'Limiter sole writer, no new writers, ever' is violated by "
                f"the grant itself"
            )
    return defects


def _arm5_no_trigger(dbname: str) -> list[str]:
    """No trigger and no rule on the log."""
    defects: list[str] = []
    triggers = _query(
        dbname,
        "select t.tgname from pg_trigger t join pg_class c on c.oid=t.tgrelid "
        f"where c.relname like '{LOG_TABLE}%' and not t.tgisinternal",  # nosec B608
    )
    if triggers:
        defects.append(
            "ARM5: the event log carries trigger(s) "
            + ", ".join(sorted(row[0] for row in triggers))
            + ". Append-only is enforced by PRIVILEGE here; a trigger makes "
            "the weaker mechanism look like the guarantee — it is skipped by "
            "session_replication_role, disabled by one ALTER TABLE, and never "
            "fires on TRUNCATE at all"
        )
    rules = _query(
        dbname,
        "select r.rulename from pg_rules r "
        f"where r.schemaname='public' and r.tablename like '{LOG_TABLE}%'",  # nosec B608
    )
    if rules:
        defects.append(
            "ARM5: the event log carries rewrite rule(s) "
            + ", ".join(sorted(row[0] for row in rules))
            + " — a rule can silently redirect or discard an INSERT"
        )
    return defects


def _arm3b_columns(dbname: str) -> list[str]:
    """§9's per-row requirements are STRUCTURAL, not conventional."""
    rows = _query(
        dbname,
        "select column_name, is_nullable from information_schema.columns "
        f"where table_schema='public' and table_name='{LOG_TABLE}'",  # nosec B608
    )
    present = {row[0]: row[1] for row in rows}
    defects: list[str] = []
    for column in REQUIRED_LOG_COLUMNS:
        if column not in present:
            defects.append(f"ARM3b: {LOG_TABLE} has no column {column!r}")
    for column in NOT_NULL_LOG_COLUMNS:
        if present.get(column) == "YES":
            defects.append(
                f"ARM3b: {LOG_TABLE}.{column} is NULLABLE. §9 requires "
                f"timestamp + strategy_id + trade_id + reason on EVERY row; a "
                f"nullable column makes that a convention a caller can skip "
                f"rather than a constraint the database refuses"
            )
    return defects


def _arm6_exactly_once(dbname: str) -> list[str]:
    """The unique index replay dedup rides on."""
    rows = _query(
        dbname,
        "select indexdef from pg_indexes "
        f"where schemaname='public' and tablename='{LOG_TABLE}'",  # nosec B608
    )
    definitions = [row[0] for row in rows]
    if not any(
        "UNIQUE" in d and "natural_key" in d and "occurred_at" in d for d in definitions
    ):
        return [
            (
                "ARM6: no UNIQUE index on (natural_key, occurred_at). A reconnect "
                "flush that re-delivers a buffered WAL record would DUPLICATE the "
                "row instead of being refused, and §12.4's reconnect heal claims "
                "exactly-once"
            )
        ]
    return []


def _arm7_projection_is_rebuildable(dbname: str) -> list[str]:
    """The OPPOSITE direction: the projection must be writable."""
    rows = _query(
        dbname,
        "select "
        f"has_table_privilege('{WRITER_ROLE}','plane1_positions','DELETE'), "
        f"has_table_privilege('{WRITER_ROLE}','plane1_positions','INSERT'), "
        f"has_table_privilege('{WRITER_ROLE}','plane1_positions','UPDATE'), "
        f"has_table_privilege('{WRITER_ROLE}','plane1_projection_meta','UPDATE')",  # nosec B608
    )
    dele, ins, upd, meta = (v == "t" for v in rows[0])
    if not (dele and ins and upd and meta):
        return [
            (
                f"ARM7: the projection is not rebuildable by {WRITER_ROLE} "
                f"(positions delete={dele} insert={ins} update={upd}, "
                f"meta update={meta}). §9 calls the positions table a rebuildable "
                f"PROJECTION; a rebuild is a DELETE and a re-fold. A schema that "
                f"withheld these would be beautifully append-only and impossible "
                f"to reconcile"
            )
        ]
    return []


def _arm8_meta_singleton(dbname: str) -> list[str]:
    rows = _query(dbname, "select count(*) from plane1_projection_meta")
    if rows[0][0] != "1":
        return [
            (
                f"ARM8: plane1_projection_meta holds {rows[0][0]} row(s), not 1 — "
                f"the projection's watermark has no single answer"
            )
        ]
    return []


def _arm9_by_attempt(dbname: str) -> list[str]:
    """THE ATTEMPT. Privilege proven by refusal, with the SQLSTATE asserted."""
    defects: list[str] = []

    # The CONTROL first (hazard 4): a refusal only means something beside a
    # permission that WORKS. Rolled back, so the gate writes nothing durable.
    rc, _out, err = _psql(
        dbname,
        "BEGIN; SET ROLE nix_limiter; "
        "INSERT INTO plane1_event_log "
        "(occurred_at, event_type, strategy_id, trade_id, reason, wal_seq, "
        " natural_key) VALUES "
        "(now(), 'signal', 'gate-control', 'gate-control', "
        " 'check_plane1_schema ARM9 control', 0, "
        " 'check_plane1_schema-arm9-control'); ROLLBACK;",
        verbose_errors=True,
    )
    if rc != 0:
        return [
            (
                f"ARM9 CANNOT_MEASURE: the control INSERT as {WRITER_ROLE} FAILED "
                f"(rc={rc}, sqlstate={_sqlstate(err) or 'none'}): {err[-300:]}. "
                f"Every refusal below would then be true of a role with no rights "
                f"at all, which is not evidence about append-only"
            )
        ]

    # Each attempt names the object whose grant it is testing. MEASURED, not
    # assumed, and found by this gate's own can-fail suite: an INSERT probe as
    # `nix_reader` against a database where the reader really DID hold INSERT
    # on the log was still refused with SQLSTATE 42501 — because the reader
    # lacks USAGE on `plane1_event_id_seq`, which the `event_id` DEFAULT calls,
    # and a sequence refusal carries the SAME SQLSTATE. Asserting the SQLSTATE
    # alone would have reported "correctly refused" over a live second writer.
    # That is check-contract rule 11 recurring one level down: the code was
    # right and the OBJECT was wrong, so the object is asserted too.
    attempts = (
        (
            WRITER_ROLE,
            "UPDATE plane1_event_log SET reason = 'tampered by the gate'",
            f"table {LOG_TABLE}",
            "the sole writer can REWRITE a banked row",
        ),
        (
            WRITER_ROLE,
            "DELETE FROM plane1_event_log",
            f"table {LOG_TABLE}",
            "the sole writer can ERASE banked rows",
        ),
        (
            WRITER_ROLE,
            "TRUNCATE plane1_event_log",
            f"table {LOG_TABLE}",
            "the sole writer can EMPTY the record",
        ),
        (
            READER_ROLE,
            # `event_id` is supplied explicitly so the row does NOT call
            # nextval(): the probe must be refused by the TABLE grant, and a
            # sequence refusal would mask a reader that can really write.
            (
                "INSERT INTO plane1_event_log (event_id, occurred_at, event_type, "
                "strategy_id, trade_id, reason, wal_seq, natural_key) VALUES "
                "(-1, now(), 'signal', 'x', 'x', 'x', 0, 'gate-second-writer-probe')"
            ),
            f"table {LOG_TABLE}",
            "a SECOND WRITER exists — §12.10's 'no new writers, ever'",
        ),
    )
    for role, statement, expected_object, consequence in attempts:
        rc, _out, err = _psql(
            dbname,
            f"BEGIN; SET ROLE {role}; {statement}; ROLLBACK;",
            verbose_errors=True,
        )
        if rc == 0:
            defects.append(
                f"ARM9: `{statement[:48]}...` as {role} SUCCEEDED — {consequence}"
            )
            continue
        state = _sqlstate(err)
        if state != SQLSTATE_INSUFFICIENT_PRIVILEGE:
            defects.append(
                f"ARM9: `{statement[:48]}...` as {role} was refused with "
                f"SQLSTATE {state or 'NONE REPORTED'}, not "
                f"{SQLSTATE_INSUFFICIENT_PRIVILEGE} (insufficient_privilege). "
                f"A refusal for the wrong reason is not evidence about "
                f"grants — a typo, an absent table and a dead server all "
                f"refuse just as loudly. stderr: {err[-200:]}"
            )
        elif f"permission denied for {expected_object}" not in err:
            defects.append(
                f"ARM9: `{statement[:48]}...` as {role} was refused with the "
                f"right SQLSTATE for the WRONG OBJECT — expected "
                f"'permission denied for {expected_object}', got: "
                f"{err[-200:]}. A sequence, a schema and a table all refuse "
                f"with 42501, and only the table's refusal is evidence about "
                f"{consequence}"
            )
    return defects


# ---------------------------------------------------------------------------


def inspect_database(dbname: str) -> list[str]:
    """Every arm against `dbname`. Returns defects.

    Named and parameterised by database so the can-fail suite can build a
    scratch copy, break ONE declared property there, and drive the SHIPPED
    arms against the broken database.
    """
    defects, partitions = _arm2_objects(dbname)
    if len(partitions) < MIN_PARTITIONS:
        return defects + [
            (
                f"CANNOT_MEASURE: {LOG_TABLE} has {len(partitions)} partition(s), "
                f"below the floor of {MIN_PARTITIONS}. ARM4's per-partition loop "
                f"would report clean over an empty population"
            )
        ]
    defects += _arm3_inventory(dbname)
    defects += _arm3b_columns(dbname)
    defects += _arm4_privileges(dbname, partitions)
    defects += _arm5_no_trigger(dbname)
    defects += _arm6_exactly_once(dbname)
    defects += _arm7_projection_is_rebuildable(dbname)
    defects += _arm8_meta_singleton(dbname)
    defects += _arm9_by_attempt(dbname)
    return defects


# Seven returns, one per DISTINGUISHABLE outcome: server unreachable, database
# absent, an unmeasurable arm, a defect set, a clean pass, and the two exception
# paths. Collapsing them into a single exit would mean carrying a status variable
# through the whole function, and §17's whole point is that "unreachable" and
# "measured and clean" must not travel the same path.
# pylint: disable=too-many-return-statements
def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure the live Plane-1 database against the frozen schema."""
    try:
        rc, _out, err = _psql("postgres", "select 1")
        if rc != 0:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=PLANE1_DB,
                detail=(
                    f"Postgres is unreachable, so nothing about Plane 1 was "
                    f"measured (§17, never a PASS): {err[-300:]}"
                ),
            )
        rc, out, err = _psql(
            "postgres",
            f"select 1 from pg_database where datname = '{PLANE1_DB}'",  # nosec B608
        )
        if rc != 0 or out.strip() != "1":
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=PLANE1_DB,
                detail=(
                    f"database {PLANE1_DB!r} does not exist on this cluster; "
                    f"apply {ANCHOR}. Nothing was measured (§17)"
                ),
            )
        defects = inspect_database(PLANE1_DB)
        unmeasurable = [d for d in defects if "CANNOT_MEASURE" in d]
        if unmeasurable:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=PLANE1_DB,
                detail="; ".join(defects),
            )
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=PLANE1_DB,
                evidence=f"{PLANE1_DB}: {len(defects)} schema/privilege defect(s)",
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"{PLANE1_DB}: append-only proven BY PRIVILEGE on the log "
                f"parent and every partition, and BY ATTEMPT — UPDATE, DELETE "
                f"and TRUNCATE as {WRITER_ROLE} and INSERT as {READER_ROLE} "
                f"all refused with SQLSTATE "
                f"{SQLSTATE_INSUFFICIENT_PRIVILEGE}, against a control INSERT "
                f"that succeeds. {len(SPEC_12_10_PLANE1_EVENTS)} §12.10 event "
                f"types, compared both ways. No trigger and no rule on the "
                f"log. The projection stays rebuildable"
            ),
        )
    except PsqlUnavailable as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=PLANE1_DB,
            detail=f"the subject could not be reached, so nothing was measured (§17): {exc}",
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py (§4.2).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
