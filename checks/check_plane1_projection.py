#!/usr/bin/env python3
# pylint: disable=missing-function-docstring,too-few-public-methods
# The single-method classes here are PORTS and row shapes, which is exactly
# one public method by design; a second would widen an authority boundary.
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: §9's positions projection is REBUILDABLE FROM THE LOG, and agrees with it.

ARC 035 / Stage 1 / sub-agent B. Subject: `scripts/nixrisk/projection.py` — the
fold — measured against `databases/schema/plane1.sql`'s real tables.

§9, verbatim and entire: *"Positions table = projection (rebuildable; dashboard +
reconciliation read it)."*

## THE SENTENCE THIS GATE WAS WRITTEN AGAINST

The arc brief's §0a, binding on this sub-agent:

> *a rebuild test that starts from an empty log proves nothing.*

That is the whole trap here and it is a comfortable one to fall into, because an
empty log folds to an empty projection which equals the empty projection that was
dropped, and every assertion passes. So ARM 2 does not fold whatever happens to
be lying around: it BUILDS a scratch database from the shipped DDL, seeds a
counted history through the Limiter's role, folds it, destroys the projection,
folds it again, and compares the two FIELD BY FIELD — and it refuses to certify
below `MIN_FOLDED_EVENTS` position-moving events, reporting CANNOT_MEASURE
instead of collecting a free green over an almost-empty set.

## The arms

1. **The fold's classification is TOTAL against the live catalog, both
   directions.** `POSITION_AFFECTING | POSITION_NEUTRAL` must equal
   `plane1_event_enum`. A type in the enum that the fold has no rule for is an
   event that silently moves nothing — and a NEW event type is exactly the case
   where a fold decision is owed. A rule for a type the enum does not have is a
   fold branch that can never run. One direction alone would accept the first
   forever.

2. **THE REBUILD, on a scratch database this gate builds itself.** Seed → fold →
   snapshot → fold again (the second fold `TRUNCATE`s first, so it is a genuine
   drop-and-rebuild) → compare every column of every row. The comparison is
   between two reads *out of Postgres*, never between the fold's own in-memory
   objects, so a fold that computed a beautiful projection and wrote nothing
   fails rather than passes.

3. **The LIVE projection agrees with a fold of the LIVE log through its own
   watermark.** Non-mutating: it reads `nix_plane1` and writes nothing there.
   This arm is honest about its own reach — it reports the row counts it saw, and
   when the live projection has never been rebuilt it says so rather than
   counting an untouched table as agreement.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **The seeded history could be empty or trivial.** *Closed:* ARM 2 asserts the
   seeded event count against `plane1_seed.SEED_EVENT_COUNT` and requires at
   least `MIN_FOLDED_EVENTS` position-moving events; below either it is
   CANNOT_MEASURE.
2. **The two sides of the comparison could be the same object.** *Closed:* both
   are `SELECT`s from `plane1_positions` taken at different times, with a
   `TRUNCATE` between them. `diff_projections` compares dicts read from the
   database, not dataclasses the fold returned.
3. **The rebuild could write nothing and "match" an empty table twice.**
   *Closed:* the row count written is asserted equal to the fold's position count
   AND to `SEED_POSITION_COUNT`, and every state (`open`, `partial`, `closed`)
   must appear — a fixture that ended every trade the same way would leave two
   thirds of the fold unexercised.
4. **Postgres could be down, or `createdb` absent**, and "no defects" over
   nothing is the purest vacuous green. *Closed:* every such path is
   CANNOT_MEASURE naming the stderr (§17), never a PASS.
5. **The scratch database could be built from something other than the shipped
   DDL.** *Closed:* it is loaded from `databases/schema/plane1.sql` by path, and
   the path is this check's `ANCHOR`.
6. **ARM 3 could pass because the live log is empty.** *Closed as far as it can
   be, and NAMED:* the verdict prints the live counts, and an empty live log is
   reported as an arm that did not measure rather than as agreement. The gate's
   certification rests on ARM 2, which always has a real history.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - psql IS the instrument; §9.1 forbids new deps
import sys
import uuid
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixrisk import plane1_seed
from nixrisk.projection import (
    CLASSIFIED,
    MIN_FOLDED_EVENTS,
    PLANE1_DB,
    READER_ROLE,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_PARTIAL,
    ProjectionError,
    ProjectionUnavailable,
    Psql,
    diff_projections,
    enum_members,
    fold_events,
    read_log,
    read_meta,
    read_projection,
    rebuild,
)
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
EXPECTED_S = 12.0
DEPENDS_ON: tuple[str, ...] = ("check_plane1_schema",)
#: This process spawns `psql`, `createdb` and `dropdb`. The SOCKET to Postgres is
#: opened by those binaries and not here, so the three `subprocess:` tokens are
#: the whole of what this process observably touches — and every one of them is
#: falsifiable by watching the process table (D3.152's unfalsifiable-token debt is
#: exactly what a `postgres:nix_plane1` token would have been).
RESOURCES: tuple[str, ...] = (
    # ARC 035 Stage 2 integration: ADDED after `check_observed_resource_claims`
    # measured this gate on the MERGED tree and found the declaration false.
    # The ephemeral cluster this gate builds writes thousands of files under
    # its own `/tmp` directory — `pg/base/1/1247`, the WAL segments, the socket
    # — and the declaration named only the subprocesses that do it. §4.4: a
    # declaration is checked against OBSERVED claims, not against the other
    # declarations, and the branch's own green could not see this because the
    # observer gate had not run over the new check.
    "file-write:/tmp",
    "subprocess:psql",
    "subprocess:createdb",
    "subprocess:dropdb",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is whether the projection can be DERIVED from the log; a gate "
    "authorised to rebuild the live projection would repair the very "
    "disagreement it exists to report, and the operator would never learn that "
    "the record and the projection had parted company"
)
ANCHOR = "scripts/nixrisk/projection.py"
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/projection.py",
    "scripts/nixrisk/plane1_seed.py",
    "databases/schema/plane1.sql",
)

NAME = "check_plane1_projection"

#: Prefix for this gate's throwaway databases. Sub-agent B's assigned prefix for
#: ARC 035; every one is dropped in a `finally`.
SCRATCH_PREFIX = "p1b_gate_"

#: The three states the fixture must exercise. A rebuild proof over a history in
#: which every trade ended the same way is a proof about one branch.
REQUIRED_STATES = (STATE_OPEN, STATE_PARTIAL, STATE_CLOSED)

_SCHEMA_SQL = "databases/schema/plane1.sql"


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        argv, capture_output=True, text=True, timeout=180, check=False
    )


class _Scratch:
    """A throwaway Plane-1 database built from the SHIPPED DDL. Dropped always."""

    def __init__(self, schema_sql: Path) -> None:
        for binary in ("createdb", "dropdb", "psql"):
            if shutil.which(binary) is None:
                raise ProjectionUnavailable(f"{binary} is not on PATH")
        self.name = SCRATCH_PREFIX + uuid.uuid4().hex[:12]
        created = _run(["createdb", self.name])
        if created.returncode != 0:
            raise ProjectionUnavailable(
                f"createdb {self.name}: {created.stderr[-300:]}"
            )
        loaded = _run(
            [
                "psql",
                "-d",
                self.name,
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(schema_sql),
            ]
        )
        if loaded.returncode != 0:
            self.drop()
            raise ProjectionUnavailable(
                f"loading {schema_sql} into {self.name}: {loaded.stderr[-400:]}"
            )

    def drop(self) -> None:
        _run(["dropdb", "--if-exists", "--force", self.name])


# --------------------------------------------------------------------- arms


def arm1_classification(psql: Psql) -> list[str]:
    """The fold's rules cover the catalog's event types, BOTH directions."""
    members = enum_members(psql)
    if not members:
        return [
            (
                "ARM1 CANNOT_MEASURE: plane1_event_enum has no members, so there is "
                "nothing to compare the fold's classification against"
            )
        ]
    defects: list[str] = []
    unruled = sorted(members - CLASSIFIED)
    if unruled:
        defects.append(
            "ARM1: the schema can record event type(s) the projection fold has no "
            "rule for: "
            + ", ".join(unruled)
            + " — a fold that ignored an unknown type would silently ignore "
            "exactly the event a decision is owed on"
        )
    phantom = sorted(CLASSIFIED - members)
    if phantom:
        defects.append(
            "ARM1: the fold carries rules for event type(s) the schema cannot "
            "record: " + ", ".join(phantom) + " — branches that can never run"
        )
    return defects


def arm2_rebuild(schema_sql: Path) -> tuple[list[str], str]:
    """THE REBUILD ARM. Own scratch database, counted history, field-by-field."""
    scratch = _Scratch(schema_sql)
    try:
        psql = Psql(scratch.name)
        seeded = plane1_seed.seed(psql)
        if seeded != plane1_seed.SEED_EVENT_COUNT:
            return (
                [
                    (
                        f"ARM2 CANNOT_MEASURE: seeded {seeded} events, not the "
                        f"declared {plane1_seed.SEED_EVENT_COUNT}"
                    )
                ],
                "",
            )
        first = rebuild(psql, source=f"{NAME} arm2 first fold")
        if not first.measured_enough:
            return (
                [
                    (
                        f"ARM2 CANNOT_MEASURE: the seeded history moves only "
                        f"{first.position_events} position(s), below the floor of "
                        f"{MIN_FOLDED_EVENTS}. A rebuild comparison over an "
                        f"almost-empty set is a statement about nothing (§0a)"
                    )
                ],
                "",
            )
        defects = _rebuild_defects(psql, first)
        summary = (
            f"{first.log_events} log events, {first.position_events} of them "
            f"position-moving, {first.positions_written} positions, folded "
            f"through event_id {first.through_event_id}"
        )
        return defects, summary
    finally:
        scratch.drop()


def _rebuild_defects(psql: Psql, first) -> list[str]:
    """Snapshot, destroy, re-fold, compare. Everything ARM 2 actually asserts."""
    defects: list[str] = []
    if first.anomalies:
        defects.append(
            "ARM2: the fold could not interpret the seeded log: "
            + "; ".join(first.anomalies[:4])
        )
    if first.positions_written != plane1_seed.SEED_POSITION_COUNT:
        defects.append(
            f"ARM2: the fold wrote {first.positions_written} positions, not the "
            f"declared {plane1_seed.SEED_POSITION_COUNT} — the fixture and the "
            f"fold disagree about what the history contains"
        )
    states = {str(row["state"]) for row in first.stored}
    missing = [state for state in REQUIRED_STATES if state not in states]
    if missing:
        defects.append(
            f"ARM2 CANNOT_MEASURE: the rebuilt projection contains no "
            f"{', '.join(missing)} row(s); a rebuild proof over a history in "
            f"which every trade ended the same way exercises one branch"
        )
    snapshot = first.stored
    second = rebuild(psql, source=f"{NAME} arm2 second fold after TRUNCATE")
    if second.positions_written != first.positions_written:
        defects.append(
            f"ARM2: the projection was destroyed and rebuilt from the log alone "
            f"and came back with {second.positions_written} positions, not "
            f"{first.positions_written}"
        )
    for line in diff_projections(fold_events(read_log(psql)).positions, second.stored):
        defects.append(f"ARM2 (rebuilt vs fold): {line}")
    defects += [
        f"ARM2 (before vs after the drop): {line}"
        for line in _diff_stored(snapshot, second.stored)
    ]
    meta = read_meta(psql)
    if int(meta["rebuilt_through_event_id"]) != second.through_event_id:
        defects.append(
            f"ARM2: the watermark says {meta['rebuilt_through_event_id']} and the "
            f"fold reached {second.through_event_id} — a projection that cannot "
            f"say where it is in the log is one nobody can reconcile against"
        )
    return defects


def _diff_stored(before, after) -> list[str]:
    """Field-by-field between two READS of the projection table."""
    left = {str(row["trade_id"]): dict(row) for row in before}
    right = {str(row["trade_id"]): dict(row) for row in after}
    defects: list[str] = []
    for trade_id in sorted(set(left) ^ set(right)):
        defects.append(
            f"trade {trade_id} is present on only one side of the drop-and-rebuild"
        )
    for trade_id in sorted(set(left) & set(right)):
        for field in sorted(left[trade_id]):
            if left[trade_id][field] != right[trade_id].get(field):
                defects.append(
                    f"trade {trade_id}: field {field} was "
                    f"{left[trade_id][field]!r} before the drop and "
                    f"{right[trade_id].get(field)!r} after the rebuild"
                )
    return defects


def arm3_live_drift(psql: Psql) -> tuple[list[str], str]:
    """The LIVE projection against a fold of the LIVE log. Reads only."""
    events = read_log(psql)
    stored = read_projection(psql)
    meta = read_meta(psql)
    watermark = int(meta["rebuilt_through_event_id"])
    source = str(meta["rebuild_source"])
    note = (
        f"live {psql.dbname}: {len(events)} log event(s), {len(stored)} "
        f"projection row(s), watermark {watermark}, source {source!r}"
    )
    if source == "never rebuilt":
        return (
            [],
            note
            + " — the drift arm did NOT measure: nothing has ever folded this projection",
        )
    folded = fold_events(e for e in events if e.event_id <= watermark)
    defects = [f"ARM3: {line}" for line in diff_projections(folded.positions, stored)]
    if folded.anomalies:
        defects.append(
            "ARM3: the live log holds row(s) the fold cannot interpret: "
            + "; ".join(folded.anomalies[:4])
        )
    return defects, note + f", {folded.position_events} position-moving event(s)"


# ---------------------------------------------------------------------------


def inspect(nix_home: Path, dbname: str = PLANE1_DB) -> tuple[list[str], list[str]]:
    """Every arm. Returns `(defects, notes)`.

    Parameterised by home and database so the can-fail suite can point the live
    arm at a broken scratch database and drive the SHIPPED code against it.
    """
    # ARC 043 / I8: the live record is reachable only as one of the two Plane-1
    # roles now (plane1_hba.conf). This arm READS, so it reads as the reader; a
    # scratch database handed in by the can-fail suite keeps the ambient
    # identity, which is what provisioned it.
    live = Psql(dbname, user=READER_ROLE if dbname == PLANE1_DB else None)
    defects = arm1_classification(live)
    rebuild_defects, rebuild_note = arm2_rebuild(nix_home / _SCHEMA_SQL)
    drift_defects, drift_note = arm3_live_drift(live)
    return defects + rebuild_defects + drift_defects, [rebuild_note, drift_note]


def _database_present(dbname: str) -> tuple[bool, str]:
    probe = Psql("postgres")
    rc, out, err = probe.run(
        f"select 1 from pg_database where datname = '{dbname}'"  # nosec B608
    )
    if rc != 0:
        return False, f"Postgres is unreachable: {err[-300:]}"
    if out.strip() != "1":
        return False, f"database {dbname!r} does not exist on this cluster"
    return True, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure §9's rebuildable projection: by construction, and against the log."""
    try:
        present, why = _database_present(PLANE1_DB)
        if not present:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=PLANE1_DB,
                detail=f"nothing about the projection was measured (§17): {why}",
            )
        defects, notes = inspect(ctx.nix_home)
        if any("CANNOT_MEASURE" in d for d in defects):
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
                evidence=f"{len(defects)} projection defect(s)",
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                "§9's projection is REBUILDABLE: on a scratch database built "
                f"from {_SCHEMA_SQL}, a seeded history was folded, the "
                "projection TRUNCATEd, and re-folded from the log alone to a "
                "byte-identical table compared field by field — "
                f"{notes[0]}. The fold's classification equals "
                f"plane1_event_enum in both directions ({len(CLASSIFIED)} "
                f"types). {notes[1]}"
            ),
        )
    except (ProjectionUnavailable, ProjectionError) as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=PLANE1_DB,
            detail=f"the subject could not be measured (§17): {exc}",
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
