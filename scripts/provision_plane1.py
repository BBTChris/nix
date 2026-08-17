#!/usr/bin/env python3
"""Provision the Plane-1 database from `databases/schema/plane1.sql`, idempotently.

ARC 035 / Stage 1 / sub-agent A. The migration half of A1: the database can be
created from the frozen DDL reproducibly, by a runner that can be re-run.

## THE IDEMPOTENCE IS IN THE RUNNER, NOT IN THE DDL — DELIBERATELY

`plane1.sql` is not idempotent and must not be made so. `CREATE TYPE
plane1_event_enum` cannot be wrapped in `IF NOT EXISTS`, and an
`ALTER TYPE … ADD VALUE IF NOT EXISTS` rewrite would let a partially-migrated
type pass for a complete one — which is the exact failure this arc's schema gate
exists to catch. The role block is already `IF NOT EXISTS` because roles are
CLUSTER-global and shared with a live analytics store; everything else is
per-database and belongs to a database this runner either creates or leaves
alone.

## THREE OUTCOMES, AND THE THIRD IS A REFUSAL

A provisioner whose "idempotent" means *silently do nothing when something is
already there* is worse than one that fails: a HALF-applied database — the log
table present, the projection missing, a partition never created — would read
as "already provisioned" forever, and the first row that fell outside every
range partition would be LOST at runtime. So the state is classified before
anything is written:

* **ABSENT** — no such database. Create it, apply the DDL, re-inspect, report.
* **COMPLETE** — every object the frozen spec names is present. Report and
  touch nothing. This is the re-run case and it is a no-op by MEASUREMENT, not
  by assumption.
* **INCOMPLETE** — the database exists and is missing objects. **Refuse**,
  naming every missing object. Repairing it would mean running DDL against a
  database whose actual state is unknown, and the safe repair (drop and
  recreate) is a data-destroying operation this script will never perform on a
  store whose entire purpose is to be the durable record.

The verification after an apply is a FRESH inspection through a new psql
process, not the return value of the apply (check-contract rule 2: *a return
value from the correcting path is not a verification*).

## WHAT THIS IS NOT

Not a migration FRAMEWORK. There is one version of this schema and no upgrade
path yet; inventing a version table would be a mechanism with nothing to
migrate. When the schema versions, the version column goes in
`plane1_projection_meta` and this runner grows a step list — recorded as the
obvious next move rather than pre-built.

Not a partition manager. `plane1_event_log` has a DEFAULT catch-all so a row
outside every range is EVIDENCE rather than a loss, and adding next month's
partition is a separate, schedulable job.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import argparse
import re
import shutil
import subprocess  # nosec B404 - psql/createdb ARE the instrument (§9.1)
import sys
from pathlib import Path
from typing import Final

REPO: Final[Path] = Path(__file__).resolve().parents[1]
SCHEMA_SQL: Final[Path] = REPO / "databases" / "schema" / "plane1.sql"

#: The live Plane-1 database. Same literal as `nixrisk.plane1_sink.PLANE1_DB`
#: and `checks/check_plane1_schema.PLANE1_DB`.
PLANE1_DB: Final[str] = "nix_plane1"

#: Every object the frozen schema spec names, by catalog kind. A database
#: missing ANY of these is INCOMPLETE. Transcribed from the DDL's own
#: declarations rather than queried out of the DDL text, so a rewrite of the SQL
#: that silently dropped an object is caught here instead of agreeing with itself.
REQUIRED_TABLES: Final[tuple[str, ...]] = (
    "plane1_event_log",
    "plane1_event_log_default",
    "plane1_positions",
    "plane1_projection_meta",
)
REQUIRED_TYPES: Final[tuple[str, ...]] = (
    "plane1_event_enum",
    "plane1_position_state_enum",
)
REQUIRED_SEQUENCES: Final[tuple[str, ...]] = ("plane1_event_id_seq",)
REQUIRED_INDEXES: Final[tuple[str, ...]] = ("plane1_event_log_natural_key_uq",)

#: Prefix for every throwaway Plane-1 database this arc's instruments build.
#: ARC 035 Stage 1 allocated one prefix per parallel sub-agent so a leaked
#: database is attributable and a cleanup sweep cannot take a sibling's with it.
#: Sub-agent A's is `p1a_`. The integrator may rename this ONE constant; nothing
#: else spells the prefix.
SCRATCH_PREFIX: Final[str] = "p1a_"

#: An unquoted PostgreSQL identifier. A database name reaches `pg_database`'s
#: predicate as a string literal and reaches `createdb`/`psql -d` as an ARGV
#: element, never as SQL text — but the literal is composed, so the name is
#: validated rather than escaped-and-hoped. `# nosec B608` on the one composed
#: predicate is argued by this constant: nothing that fails this shape reaches it.
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

STATE_ABSENT: Final[str] = "ABSENT"
STATE_COMPLETE: Final[str] = "COMPLETE"
STATE_INCOMPLETE: Final[str] = "INCOMPLETE"


class ProvisionError(RuntimeError):
    """Provisioning could not proceed. Always names what was seen."""


def _tool(name: str) -> str:
    binary = shutil.which(name)
    if binary is None:
        raise ProvisionError(f"{name} is not on PATH")
    return binary


def _run(argv: list[str], timeout: float = 300.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )


def _psql(database: str, sql: str) -> tuple[int, str, str]:
    proc = _run(
        [_tool("psql"), "-d", database, "-qAt", "-v", "ON_ERROR_STOP=1", "-c", sql]
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def database_exists(database: str) -> bool:
    """Does the cluster hold this database? Raises if the cluster is unreachable."""
    if not _IDENTIFIER.match(database):
        raise ProvisionError(
            f"database {database!r} is not a bare PostgreSQL identifier; refused "
            f"before any statement is composed"
        )
    rc, out, err = _psql(
        "postgres",
        f"select 1 from pg_database where datname = '{database}'",  # nosec B608
    )
    if rc != 0:
        raise ProvisionError(f"cannot reach the cluster: {err[-300:]}")
    return out.strip() == "1"


def missing_objects(database: str) -> list[str]:
    """Every frozen-spec object absent from `database`. Empty means COMPLETE."""
    missing: list[str] = []
    checks = (
        (
            "table",
            REQUIRED_TABLES,
            "select tablename from pg_tables where schemaname='public'",
        ),
        (
            "type",
            REQUIRED_TYPES,
            (
                "select t.typname from pg_type t "
                "join pg_namespace n on n.oid=t.typnamespace "
                "where n.nspname='public'"
            ),
        ),
        (
            "sequence",
            REQUIRED_SEQUENCES,
            "select sequencename from pg_sequences where schemaname='public'",
        ),
        (
            "index",
            REQUIRED_INDEXES,
            "select indexname from pg_indexes where schemaname='public'",
        ),
    )
    for kind, required, query in checks:
        rc, out, err = _psql(database, query)
        if rc != 0:
            raise ProvisionError(f"cannot inspect {database} for {kind}s: {err[-300:]}")
        present = {line.strip() for line in out.splitlines() if line.strip()}
        missing += [f"{kind} {name}" for name in required if name not in present]
    return missing


def classify(database: str) -> tuple[str, list[str]]:
    """`(state, missing)` — ABSENT, COMPLETE or INCOMPLETE. Reads only."""
    if not database_exists(database):
        return STATE_ABSENT, []
    missing = missing_objects(database)
    return (STATE_COMPLETE if not missing else STATE_INCOMPLETE), missing


def apply_schema(database: str, schema: Path) -> None:
    """Create the database and load the DDL. Never called on an existing one."""
    created = _run([_tool("createdb"), database])
    if created.returncode != 0:
        raise ProvisionError(f"createdb {database}: {created.stderr.strip()[-300:]}")
    loaded = _run(
        [
            _tool("psql"),
            "-d",
            database,
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(schema),
        ]
    )
    if loaded.returncode != 0:
        raise ProvisionError(
            f"applying {schema} to {database} FAILED and the database was left "
            f"in place for inspection rather than dropped: "
            f"{loaded.stderr.strip()[-500:]}"
        )


def provision(database: str, schema: Path, *, dry_run: bool = False) -> tuple[str, str]:
    """Bring `database` to the frozen schema. Returns `(outcome, detail)`.

    Outcomes: `created`, `already-provisioned`, `refused-incomplete`,
    `would-create` / `would-skip` / `would-refuse` under `--dry-run`.
    """
    if not schema.is_file():
        raise ProvisionError(f"schema file {schema} does not exist")
    state, missing = classify(database)
    if state == STATE_COMPLETE:
        return (
            "would-skip" if dry_run else "already-provisioned",
            (
                f"{database} already carries every object the frozen schema "
                f"names; nothing was written"
            ),
        )
    if state == STATE_INCOMPLETE:
        return (
            "would-refuse" if dry_run else "refused-incomplete",
            f"{database} EXISTS and is missing {len(missing)} object(s): "
            + ", ".join(missing)
            + ". Refused: applying the DDL over a partially-migrated database "
            "would fail on the first CREATE that already exists and leave the "
            "state even less knowable, and the only safe repair drops a store "
            "whose whole purpose is to be the durable record. Inspect it, or "
            "provision a fresh database name",
        )
    if dry_run:
        return (
            "would-create",
            f"{database} does not exist; would createdb and apply {schema}",
        )
    apply_schema(database, schema)
    # Check-contract rule 2: the verdict after a mutation is a FRESH,
    # independent re-measurement's, never the return value of the path that
    # made the change.
    state, missing = classify(database)
    if state != STATE_COMPLETE:
        raise ProvisionError(
            f"{database} was created and {schema} applied, but the independent "
            f"re-inspection still reports {state} missing: "
            + (", ".join(missing) or "(nothing — classification disagreed with itself)")
        )
    return "created", f"{database} created from {schema} and verified COMPLETE"


def main(argv: list[str] | None = None) -> int:
    """CLI. Exit 0 provisioned-or-already-there, 1 refused, 2 cannot-measure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", default=PLANE1_DB)
    parser.add_argument("--schema", type=Path, default=SCHEMA_SQL)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="classify and report; write nothing",
    )
    args = parser.parse_args(argv)
    try:
        outcome, detail = provision(args.database, args.schema, dry_run=args.dry_run)
    except ProvisionError as exc:
        print(f"CANNOT-PROVISION: {exc}")
        return 2
    print(f"{outcome.upper()}: {detail}")
    return 1 if outcome in {"refused-incomplete", "would-refuse"} else 0


if __name__ == "__main__":
    sys.exit(main())
