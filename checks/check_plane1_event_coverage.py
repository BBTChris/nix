#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: every §12.10 Plane-1 event type, classified BY DRIVE — one at a time.

ARC 035 / Stage 1 / sub-agent A (A4). Authority:
`docs/nics_risk_subsystem_spec_v1.3.md` §12.10 (the Plane-1 event inventory) and
§9 (*Timestamp + strategy_id + trade_id + reason on every row*).

## THE BRIEF'S SENTENCE, VERBATIM, AND WHAT IT RULES OUT

> *a "logging works" test on one event type generalized is manufactured
> coverage. EACH §12.10 event type is its own drive.*

So there is no representative event here. Every routable type is enqueued into a
real `Plane1Wal`, fsynced, group-committed through the real
`Plane1PostgresSink` into a real scratch database built from the shipped DDL,
and its row is then READ BACK and checked for §9's four per-row fields
INDIVIDUALLY. Eighteen drives, eighteen read-backs, one table.

## THE SECOND TRAP, WHICH IS SUBTLER: TRANSPORT IS NOT PRODUCTION

Constructing an `EventRow` in a gate and pushing it down the path proves the
TRANSPORT works. It says nothing about whether any production code path ever
emits that kind — and reporting the first as though it were the second is the
manufactured coverage the brief forbids, one level up from the one it names.

So each type carries TWO measured columns and the verdict prints both:

* **TRANSPORT** — the drive above actually landed a conforming row.
* **PRODUCER** — some SHIPPED module (`scripts/**.py` minus `scripts/tests/`)
  references `EventKind.<MEMBER>`, found by AST over the tree. DERIVED, never a
  hand-maintained list: sibling sub-agents B, C and D are landing emitters in
  this same arc, and a literal would be stale before the arc closed. ARC 042
  widened this from `scripts/nixrisk/*.py`, which could not see §9's sole
  writer — `scripts/limiterd.py` — at all; see `producer_census`.

Three states result, and each is named PER TYPE in the evidence:

* **DRIVEN** — transported AND produced. Real coverage.
* **TRANSPORT-ONLY** — the path works; nothing in the tree emits it yet.
  Honest, and reported as *NOT YET PRODUCED*.
* **UNROUTABLE** — `scripts/nixrisk/seam.py`'s FROZEN `EventKind` has no member
  for this §12.10 type at all, so the Limiter cannot enqueue it and nothing in
  this tree can record it. Five of the eighteen are in this state and each one's
  reason is enumerated in `nixrisk.plane1_sink.UNROUTABLE_PLANE1_EVENTS`.

## THE RATCHET, AND WHY IT IS DELIBERATELY ASYMMETRIC

A census that nobody checks drifts. So:

* a type becoming **UNROUTABLE** that was not, or **losing** its producer, is a
  FAIL — that is a regression in the money record's coverage;
* a type **gaining** a producer is reported and does NOT fail.

The asymmetry is a decision, not an oversight. Four sub-agents are landing
emitters in parallel in this arc, and a gate that reddened on progress is a gate
that gets switched off. The cost is stated: a silently-added emitter is not
caught HERE. It is caught by `check_plane1_sole_writer`, whose whole subject is
unauthorised authorship — which is the hazard, where "someone made an existing
event type actually work" is not.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **The drive loop could run zero times** — an empty enum, a filtered list, a
   `continue` that skips everything — and "no failures" over nothing is the
   purest vacuous green. *Closed:* the gate requires the enum read out of the
   scratch database to have exactly `EXPECTED_EVENT_TYPES` members and requires
   the number of types actually DRIVEN to meet `MIN_TYPES_DRIVEN`; below either,
   `CANNOT_MEASURE`.
2. **The read-back could be satisfied by the row it just wrote being absent.**
   A `SELECT` returning nothing is not a conforming row. *Closed:* every drive
   asserts exactly ONE row for its natural key and checks the four §9 fields on
   the row it got back, naming the field that was wrong.
3. **The four §9 fields could be checked against the sentinel** `'-'`, which is
   NOT NULL and satisfies the schema. *Closed:* every driven row carries a
   distinctive per-type value in all four, and the read-back asserts the VALUE,
   not merely non-emptiness.
4. **The producer census could be read out of the subject it polices.**
   D3.200's recurring shape. *Closed:* the census is an AST scan of
   `scripts/nixrisk/*.py` for `EventKind.<MEMBER>` — a different artefact from
   both the enum in the database and the mapping in the sink.
5. **The scratch database could differ from the shipped schema.** *Closed:* it
   is built by `scripts/provision_plane1.py` from `databases/schema/plane1.sql`
   itself, and the provisioner's own independent re-inspection must report
   COMPLETE before a single row is driven.
6. **Postgres could be down**, and the whole census would report clean over
   nothing. *Closed:* `CANNOT_MEASURE` naming the failure (§17), never PASS.
"""

from __future__ import annotations

import ast
import shutil
import subprocess  # nosec B404 - psql IS the read-back instrument (§9.1)
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixrisk.plane1_sink import (
    EVENT_KIND_TO_PLANE1,
    UNROUTABLE_PLANE1_EVENTS,
    Plane1PostgresSink,
    natural_key_for,
)
from nixrisk.seam import EventKind, EventRow
from nixrisk.wal import GroupCommitWriter, Plane1Wal
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
EXPECTED_S = 25.0
ON_FAIL = "continue"
DEPENDS_ON: tuple[str, ...] = ("check_plane1_schema",)
#: Spawns `psql` (the read-back), `createdb`/`dropdb` (its own scratch database)
#: and writes a WAL under `/tmp`. Every token is falsifiable by observation.
RESOURCES: tuple[str, ...] = (
    "subprocess:psql",
    "subprocess:createdb",
    "subprocess:dropdb",
    "file-write:/tmp",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is which §12.10 transitions the running code can actually "
    "record. The repair for a missing one is to BUILD the producer, which is an "
    "arc, not a correction a gate can apply"
)
ANCHOR = "databases/schema/plane1.sql"
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/plane1_sink.py",
    "databases/schema/plane1.sql",
)

NAME = "check_plane1_event_coverage"

#: §12.10's inventory size, per the frozen schema spec. Structural, not a moving
#: number: it is the count `check_plane1_schema.SPEC_12_10_PLANE1_EVENTS` is
#: independently pinned to, and a disagreement means one of the two moved.
EXPECTED_EVENT_TYPES: Final[int] = 18

#: Non-vacuity floor for the drive loop. A FLOOR: at least this many §12.10 types
#: must be routable and actually driven, or the census is over an empty set.
MIN_TYPES_DRIVEN: Final[int] = 10

#: Types with NO production emitter today, each with the reason. This is the
#: RATCHET's baseline for the TRANSPORT-ONLY state: a type that becomes
#: unproduced and is not here is a regression and FAILS. A type that GAINS a
#: producer is reported, not failed — see the module docstring on the asymmetry.
EXPECTED_UNPRODUCED: Final[dict[str, str]] = {
    "signal": (
        "the strategy proposal reaching the Limiter. `nixrisk/gate.py` evaluates "
        "it and `nixrisk/seam.py` declares the kind, but no module enqueues a "
        "Plane-1 row for it — the gate seam's own §12.10 rows are unbuilt"
    ),
    "accepted": "the gate's approval row; same gap as `signal`",
    "denied": (
        "the gate's refusal row, which §5 makes the one that must NAME the "
        "blocking rule; same gap as `signal`"
    ),
}

#: The `EventKind` chosen to drive each routable §12.10 type. Where several kinds
#: fold onto one type (§12.10:757's four strategy-lifecycle verbs) the first is
#: driven and the others are covered by the mapping's own exhaustiveness test in
#: `scripts/tests/test_plane1_sink.py` — driving four rows into one type would
#: report four greens for one property.
_DRIVE_KIND: Final[dict[str, EventKind]] = {}
for _kind, _type in EVENT_KIND_TO_PLANE1.items():
    _DRIVE_KIND.setdefault(_type, _kind)


#: Modules that NAME every `EventKind` member without emitting any of them.
#: Counting either would give every member a producer for free, which is D3.200's
#: recurring shape — a gate reading its expected value out of the subject it
#: polices. MEASURED, not anticipated: the first run of this census reported all
#: eighteen types DRIVEN because `plane1_sink.py`'s mapping table mentions every
#: member, and `signal` has no emitter anywhere in the tree.
#:   * `seam.py`        — DEFINES the enum.
#:   * `plane1_sink.py` — MAPS it to `plane1_event_enum`.
NOT_PRODUCERS: Final[frozenset[str]] = frozenset({"seam.py", "plane1_sink.py"})

#: ARC 042. The same exclusion one directory up, and MEASURED the same way.
#: Widening the census to the shipped population (see `producer_census`) swept in
#: `scripts/*_drill.py` — the DRIVERS other gates spawn to create load
#: (`plane1_degraded_drill.py`, `plane1_hotpath_drill.py` and `wal_kill_drill.py`
#: are the subjects of `check_plane1_degraded`, `check_plane1_hot_path` and
#: `check_plane1_wal`). They construct `EventKind.SIGNAL`, `.ACCEPTED` and
#: `.DENIED` rows to have something to push down the path, and counting them
#: flipped exactly those three types from TRANSPORT-ONLY to DRIVEN on the run
#: that widened the glob — three free greens over `EXPECTED_UNPRODUCED`'s three
#: declared gaps, none of which had gained a production emitter. An instrument
#: that manufactures a row so a gate has something to measure is not a producer
#: of that row in the running system; D3.200's shape here is a census reading
#: its own fixtures back as coverage.
#: ARC 043 / D3.435(b) — THE SUFFIX IS GONE, AND WHAT REPLACED IT IS AN
#: ENUMERATION, NOT A SHAPE. The distinction is stated because the brief asked
#: for a shape and a shape was MEASURED AND REJECTED, three times, on this tree:
#:
#:   1. "constant-literal §9 fields" — the drills build their rows with
#:      f-strings over a loop index, so all three read EMITTED alongside
#:      `limiterd.py`. Separates nothing.
#:   2. "creates its own Postgres substrate" (`initdb`/`pg_ctl`/`createdb`/
#:      `provision`, docstrings excluded) — cleanly separates the three Plane-1
#:      drills from `limiterd.py`, `projection.py` and `drift_audit.py`, and
#:      then MISSES `wal_kill_drill.py`, which builds no cluster because its
#:      substrate is a WAL file. That module emits `EventKind.ACCEPTED` and
#:      nothing else, so the miss is exactly one free green — D3.435's own
#:      defect, re-created by its own repair.
#:   3. "spawned by a `checks/check_*.py`" — true of every drill AND of
#:      `scripts/limiterd.py`, which `check_go_timeout` spawns as its subject.
#:      Separates the instruments from the ONE module §9 authorises to be a
#:      producer in precisely the wrong direction.
#:
#: A drill and a daemon are syntactically alike, and that is the finding rather
#: than an obstacle to one. So this is the form the rest of this tree already
#: uses for the same problem — `NOT_PRODUCERS` here, `SQL_AUTHOR_EXEMPT` and
#: `SINK_IMPL_EXEMPT` in `check_plane1_sole_writer` — a path enumerated with the
#: reason it is not a producer.
#:
#: WHAT THIS CLOSES that `DRILL_SUFFIX` did not:
#:   * it cannot CAPTURE by accident. A future `scripts/foo_drill.py` that is a
#:     real producer was silently excluded by the suffix and is counted here.
#:   * it cannot LOSE by rename. `_gate_driver_defects` asserts every path below
#:     still exists and the census is CANNOT_MEASURE if one does not, so a
#:     renamed drill reddens instead of quietly rejoining the producer set.
#: WHAT IT DOES NOT CLOSE, named rather than implied: a NEW instrument added
#: under `scripts/` that emits an `EventKind` counts as a producer until someone
#: enumerates it here, and that is a free green in the silent direction.
#: CHECK-DEBT carries it; no shape measured on this tree closes it.
GATE_DRIVERS: Final[dict[str, str]] = {
    "plane1_crash_drill.py": (
        "check_plane1_crash_gap's driver: stands up an EPHEMERAL PostgreSQL "
        "cluster (initdb + pg_ctl on a private socket) and crashes it. Its rows "
        "exist so the gate has a crash gap to find"
    ),
    "plane1_degraded_drill.py": (
        "check_plane1_degraded's driver: the same ephemeral-cluster shape, "
        "driving §12.4's outage / disk-critical / reconnect ladder"
    ),
    "plane1_hotpath_drill.py": (
        "check_plane1_hot_path's driver for §11 item 6: builds a scratch "
        "database through provision_plane1 and pushes load through the real sink"
    ),
    "wal_kill_drill.py": (
        "check_plane1_wal's driver: fills a WAL in a scratch root and SIGKILLs "
        "the producer to observe fsync. Emits EventKind.ACCEPTED and nothing "
        "else — the one type the substrate shape above would have handed a free "
        "green"
    ),
}


class Unmeasurable(Exception):
    """The subject could not be reached, so nothing was measured (§17)."""


def _psql(database: str, sql: str) -> str:
    binary = shutil.which("psql")
    if binary is None:
        raise Unmeasurable("psql is not on PATH")
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "-d", database, "-qAt", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise Unmeasurable(f"{database}: {proc.stderr.strip()[-300:]}")
    return proc.stdout.strip()


def gate_driver_liveness(home: Path) -> list[str]:
    """ARC 043 / D3.435(b). Every enumerated gate driver must still EXIST.

    The half of the suffix defect an enumeration does not close on its own: a
    renamed or deleted drill would silently drop out of the exclusion and
    rejoin the producer set, which is a free green for whatever kinds it emits.
    A missing path is reported and the caller makes the census CANNOT_MEASURE —
    the enumeration has lost its subject, and §17 forbids certifying a property
    whose subject is unavailable.
    """
    scripts = home / "scripts"
    return [
        f"GATE_DRIVERS names scripts/{name}, which does not exist — the "
        f"exclusion has lost its subject and the census cannot be trusted "
        f"either way (reason on record: {reason[:70]}...)"
        for name, reason in sorted(GATE_DRIVERS.items())
        if not (scripts / name).is_file()
    ]


def producer_census(home: Path) -> dict[str, set[str]]:
    """`EventKind` member -> the SHIPPED modules that reference it.

    DERIVED by AST, never listed. Sibling sub-agents are landing emitters in this
    same arc and a hand-maintained literal would be stale before the arc closed.
    A reference to `EventKind.X` is the strongest static evidence available that
    a module can emit that kind; it does not prove the line is reachable at
    runtime, and `check_uncalled_entry_points` owns reachability.

    ## ARC 042 — THE POPULATION WAS WRONG, AND IT WAS WRONG IN THE ONE DIRECTION
    ## THAT MATTERS

    Until ARC 042 this scanned `scripts/nixrisk/*.py` ONLY. §9 makes **the
    Limiter** the sole Plane-1 writer, and the Limiter as a running process is
    `scripts/limiterd.py` (§2:42) — one directory ABOVE the glob. So the census
    could not see a producer in the only module §9 authorises to be one, and the
    state it reported for a daemon-emitted type was `TRANSPORT-ONLY`: *the path
    works, nothing emits it*, over a tree in which something did.

    MEASURED, not anticipated: ARC 042 wired `limiterd.py` to enqueue §12.10's
    `go_timeout` row and this gate reddened with *"RATCHET: §12.10 type(s) LOST
    their producer: go_timeout"* — a REGRESSION verdict over an arc that had just
    built the emitter. The ratchet was reading its own blind spot as a loss.

    The population is now the SHIPPED one — `scripts/**.py` minus
    `scripts/tests/` — which is the same population `checks/check_go_timeout.py`
    uses for its own reader census, and the population every "does any shipped
    module do X" question in this tree is actually asking about. `NOT_PRODUCERS`
    still excludes the two modules that NAME every member without emitting any,
    and `GATE_DRIVERS` (ARC 043 / D3.435(b), replacing ARC 042's `_drill.py`
    suffix) excludes the gate drivers the wider glob swept in — see its own
    comment for the three free greens that measured, for the three candidate
    SHAPES that were measured and rejected, and for what an enumeration still
    does not close.
    """
    census: dict[str, set[str]] = {}
    scripts = home / "scripts"
    for path in sorted(scripts.rglob("*.py")):
        rel = path.relative_to(scripts)
        if "tests" in rel.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except OSError, SyntaxError, UnicodeDecodeError:
            continue
        if path.name in NOT_PRODUCERS or path.name in GATE_DRIVERS:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "EventKind"
            ):
                census.setdefault(node.attr, set()).add(path.name)
    return census


def _probe_row(event_type: str, kind: EventKind, index: int) -> EventRow:
    """One drive row, distinctive in ALL FOUR §9 fields.

    Distinctive on purpose: the schema's sentinel `'-'` is NOT NULL and would
    satisfy a non-emptiness check, so the read-back asserts the VALUE.

    `index` rather than `hash(event_type)`: `hash` of a str is salted per
    process, so the drive's timestamps would differ run to run and a failure
    would be irreproducible.
    """
    return EventRow(
        kind=kind,
        # A distinct instant per type so two types cannot collide on
        # (natural_key, occurred_at) and mask a missing row as a dedup.
        ts=1_755_100_000.0 + index,
        strategy_id=f"cover-{event_type}",
        reason=f"check_plane1_event_coverage drive of {event_type}",
        trade_id=f"trade-{event_type}",
        fields={"symbol": "ES", "driven_type": event_type},
    )


def _read_back(database: str, event_type: str, row: EventRow) -> tuple[str, list[str]]:
    """One driven type's row, read back and checked field by field.

    Returns `(occurred_at_epoch, defects)`. An empty first element means the
    type did not land: `_drive_all`'s caller classifies it TRANSPORT-FAILED.
    """
    key = natural_key_for(row).replace("'", "''")
    out = _psql(
        database,
        "select event_type, strategy_id, trade_id, reason, "
        "extract(epoch from occurred_at)::text "
        f"from plane1_event_log where natural_key = '{key}'",  # nosec B608
    )
    lines = [line for line in out.splitlines() if line.strip()]
    if len(lines) != 1:
        return "", [
            (
                f"{event_type}: {len(lines)} row(s) read back for its natural key, "
                f"not exactly 1 — the drive did not land"
            )
        ]
    got = lines[0].split("|")
    defects: list[str] = []
    expected: tuple[tuple[str, str], ...] = (
        ("event_type", event_type),
        ("strategy_id", row.strategy_id),
        ("trade_id", row.trade_id or "-"),
        ("reason", row.reason),
    )
    for index, (label, want) in enumerate(expected):
        if got[index] != want:
            defects.append(
                f"{event_type}: the landed row's {label} is {got[index]!r}, not "
                f"{want!r}. §9 requires timestamp + strategy_id + trade_id + "
                f"reason on EVERY row, and a row carrying the wrong one is a row "
                f"an audit cannot follow"
            )
    if not got[4] or float(got[4]) <= 0:
        defects.append(
            f"{event_type}: the landed row carries no usable occurred_at "
            f"({got[4]!r}) — §9's timestamp"
        )
        return "", defects
    return got[4], defects


def _drain_to_exhaustion(writer: GroupCommitWriter, attempts: int) -> str:
    """Group-commit until the backlog clears. Returns a defect string, or `''`.

    Through the real seam, batch by batch — `drain_once` never raises, so a sink
    failure arrives as `CommitResult.error` and stops the drive rather than
    letting a partially-committed log be read back as a census.
    """
    for _ in range(attempts):
        result = writer.drain_once()
        if result.error:
            return (
                f"group-commit FAILED, so no type below was measured: "
                f"{result.error[-300:]}"
            )
        if result.backlog == 0:
            return ""
    return ""


def _drive_all(database: str, tmp: Path) -> tuple[dict[str, str], list[str]]:
    """Drive every routable type end to end. Returns `(landed_by_type, defects)`.

    ONE WAL and ONE writer for the whole set, because that is what production
    does: §9's path is enqueue → durable WAL → group-commit, and eighteen private
    WALs would measure eighteen first-writes rather than a batched log.
    """
    wal_path = tmp / f"coverage-{uuid.uuid4().hex[:8]}.wal"
    wal = Plane1Wal(wal_path)
    sink = Plane1PostgresSink(database)
    writer = GroupCommitWriter(wal, sink, batch_max=4)
    landed: dict[str, str] = {}
    defects: list[str] = []
    try:
        rows = {
            event_type: _probe_row(event_type, kind, index)
            for index, (event_type, kind) in enumerate(sorted(_DRIVE_KIND.items()))
        }
        for row in rows.values():
            wal.enqueue(row)
        wal.sync_to_disk()
        drain_error = _drain_to_exhaustion(writer, len(rows) + 2)
        if drain_error:
            defects.append(drain_error)
            return landed, defects
        for event_type, row in rows.items():
            occurred_at, row_defects = _read_back(database, event_type, row)
            defects += row_defects
            if occurred_at:
                landed[event_type] = occurred_at
    finally:
        wal.close()
        wal_path.unlink(missing_ok=True)
    return landed, defects


def _scratch_database() -> str:
    import provision_plane1  # pylint: disable=import-outside-toplevel

    if shutil.which("psql") is None or shutil.which("createdb") is None:
        raise Unmeasurable("psql/createdb are not on PATH")
    name = provision_plane1.SCRATCH_PREFIX + "coverage_" + uuid.uuid4().hex[:10]
    try:
        outcome, detail = provision_plane1.provision(name, provision_plane1.SCHEMA_SQL)
    except provision_plane1.ProvisionError as exc:
        raise Unmeasurable(f"cannot build a scratch Plane-1 database: {exc}") from exc
    if outcome != "created":
        raise Unmeasurable(f"provisioning {name} returned {outcome}: {detail}")
    return name


def _drop_database(name: str) -> None:
    binary = shutil.which("dropdb")
    if binary is None or not name:
        return
    subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "--if-exists", "--force", name],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _enum_members(database: str) -> list[str]:
    """`plane1_event_enum`'s labels. Raises unless the count is §12.10's."""
    members = sorted(
        line
        for line in _psql(
            database,
            "select e.enumlabel from pg_enum e "
            "join pg_type t on t.oid = e.enumtypid "
            "where t.typname = 'plane1_event_enum'",
        ).splitlines()
        if line.strip()
    )
    if len(members) != EXPECTED_EVENT_TYPES:
        raise Unmeasurable(
            f"plane1_event_enum has {len(members)} member(s), not the "
            f"{EXPECTED_EVENT_TYPES} §12.10 names. The census would be over a "
            f"population that is not the inventory"
        )
    return members


def _produced_types(home: Path) -> set[str]:
    """§12.10 types some module under `scripts/nixrisk/` can emit. AST-derived."""
    census = producer_census(home)
    return {
        EVENT_KIND_TO_PLANE1[kind]
        for kind in EventKind
        if kind.name in census and kind in EVENT_KIND_TO_PLANE1
    }


def _state_of(event_type: str, landed: dict[str, str], produced: set[str]) -> str:
    """One type's census state, or `UNCLASSIFIED` when it is in no bucket."""
    if event_type in UNROUTABLE_PLANE1_EVENTS:
        return "UNROUTABLE"
    if event_type not in _DRIVE_KIND:
        return "UNCLASSIFIED"
    if event_type not in landed:
        return "TRANSPORT-FAILED"
    return "DRIVEN" if event_type in produced else "TRANSPORT-ONLY"


def classify(home: str | Path) -> tuple[dict[str, str], list[str], list[str]]:
    """The whole census. Returns `(state_by_type, defects, notes)`.

    Split out of `run` and parameterised by tree so the can-fail suite can drive
    the SHIPPED classification against a mutated copy.
    """
    home = Path(home)
    database = _scratch_database()
    try:
        members = _enum_members(database)
        scratch = Path(tempfile.mkdtemp(prefix="nixp1cv-"))
        try:
            landed, defects = _drive_all(database, scratch)
        finally:
            for leftover in scratch.glob("*"):
                leftover.unlink(missing_ok=True)
            scratch.rmdir()
        produced = _produced_types(home)
        state = {
            event_type: _state_of(event_type, landed, produced)
            for event_type in members
        }
        defects += [
            (
                f"{event_type}: the schema can record it, nixrisk.plane1_sink maps "
                f"no EventKind to it, and it is not enumerated in "
                f"UNROUTABLE_PLANE1_EVENTS. An event type in neither the mapping "
                f"nor the declared gap is an unaudited hole in the money record"
            )
            for event_type, value in state.items()
            if value == "UNCLASSIFIED"
        ]
        return state, defects, []
    finally:
        _drop_database(database)


def ratchet_defects(state: dict[str, str]) -> tuple[list[str], list[str]]:
    """The one-way ratchet over the census. Returns `(defects, notes)`."""
    defects: list[str] = []
    notes: list[str] = []
    unroutable = {t for t, s in state.items() if s == "UNROUTABLE"}
    unexpected = sorted(unroutable - set(UNROUTABLE_PLANE1_EVENTS))
    if unexpected:
        defects.append(
            "RATCHET: §12.10 type(s) became UNROUTABLE without being enumerated: "
            + ", ".join(unexpected)
        )
    repaired = sorted(set(UNROUTABLE_PLANE1_EVENTS) - unroutable)
    if repaired:
        notes.append(
            "type(s) that gained an EventKind since the baseline (lower the "
            "enumeration in nixrisk.plane1_sink): " + ", ".join(repaired)
        )
    unproduced = {t for t, s in state.items() if s == "TRANSPORT-ONLY"}
    newly_unproduced = sorted(unproduced - set(EXPECTED_UNPRODUCED))
    if newly_unproduced:
        defects.append(
            "RATCHET: §12.10 type(s) LOST their producer: "
            + ", ".join(newly_unproduced)
            + ". A type that could be emitted and no longer can is a regression "
            "in what the money record covers"
        )
    gained = sorted(set(EXPECTED_UNPRODUCED) - unproduced - {"__none__"})
    gained = [t for t in gained if state.get(t) == "DRIVEN"]
    if gained:
        notes.append(
            "type(s) that GAINED a producer (progress; update "
            "EXPECTED_UNPRODUCED when convenient): " + ", ".join(gained)
        )
    return defects, notes


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive every §12.10 event type and classify it, one at a time."""
    try:
        # ARC 043 / D3.435(b): the exclusion's own subjects come first. An
        # enumeration that names a path which no longer exists is not a
        # narrower census, it is a census whose exclusion silently stopped
        # applying — §17, CANNOT_MEASURE rather than a PASS over it.
        stale = gate_driver_liveness(ctx.nix_home)
        if stale:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=ANCHOR,
                detail="; ".join(stale),
            )
        state, defects, notes = classify(ctx.nix_home)
        driven = sum(1 for s in state.values() if s in {"DRIVEN", "TRANSPORT-ONLY"})
        if driven < MIN_TYPES_DRIVEN:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=ANCHOR,
                detail=(
                    f"non-vacuity floor: {driven} §12.10 type(s) were actually "
                    f"driven end to end, against a floor of {MIN_TYPES_DRIVEN}. A "
                    f"census over a near-empty set would report coverage of "
                    f"nothing (§17). Defects seen so far: "
                    + ("; ".join(defects) or "none")
                ),
            )
        ratchet, ratchet_notes = ratchet_defects(state)
        defects += ratchet
        notes += ratchet_notes
        table = "; ".join(f"{t}={state[t]}" for t in sorted(state))
        summary = {
            label: sum(1 for s in state.values() if s == label)
            for label in ("DRIVEN", "TRANSPORT-ONLY", "UNROUTABLE")
        }
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=f"{len(defects)} coverage defect(s). {table}",
                detail="; ".join(defects + notes),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"{len(state)} §12.10 event type(s), each its own drive through "
                f"enqueue -> WAL -> group-commit -> Postgres and read back "
                f"individually for §9's four per-row fields: "
                f"{summary['DRIVEN']} DRIVEN (transported AND produced), "
                f"{summary['TRANSPORT-ONLY']} TRANSPORT-ONLY (the path works; "
                f"NOT YET PRODUCED by any module), {summary['UNROUTABLE']} "
                f"UNROUTABLE (the FROZEN EventKind has no member, so the Limiter "
                f"cannot enqueue them at all). {table}"
                + (f". Notes: {'; '.join(notes)}" if notes else "")
            ),
        )
    except Unmeasurable as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
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
