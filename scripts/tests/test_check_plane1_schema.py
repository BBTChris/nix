"""`check_plane1_schema` — the DETECTION can-fail, committed rather than banked.

ARC 035 / Phase 0.4. The arc brief's instruction, verbatim:

> **PROVE the schema gate reddens on an append-only violation** (an UPDATE
> grant on the log table must redden it) — a schema gate that only checks
> tables EXIST measures nothing.

`test_an_UPDATE_grant_on_the_log_reddens_the_gate` is that proof, and the
sibling below it is the one that matters almost as much: a grant on a single
PARTITION, which the parent-level catalog read and the parent-level ATTEMPT
both walk straight past.

Every plant builds a REAL scratch Postgres database from the shipped
`databases/schema/plane1.sql`, applies exactly ONE mutation there, and drives
the SHIPPED gate's own `inspect_database` against it. The live `nix_plane1`
database is never mutated. Roles are cluster-global, but GRANTs are per
database, so a scratch grant cannot leak into production.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,missing-function-docstring
# The house convention for can-fail suites: test names spell the
# STATUS they assert (CANNOT_MEASURE, FAIL, STALE_PIN) in the case the
# contract uses, because a reader scanning a failure list needs the
# verdict, not snake_case. Same disables as the sibling suites.
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_plane1_schema as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

SCHEMA_SQL = REPO / "databases" / "schema" / "plane1.sql"

pytestmark = pytest.mark.skipif(
    shutil.which("psql") is None or shutil.which("createdb") is None,
    reason="no local PostgreSQL client; the subject is a live database",
)


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        argv, capture_output=True, text=True, timeout=120, check=False, **kwargs
    )


def _psql(db: str, sql: str) -> subprocess.CompletedProcess:
    return _run(["psql", "-d", db, "-qAt", "-v", "ON_ERROR_STOP=1", "-c", sql])


class _Scratch:
    """A throwaway Plane-1 database built from the shipped DDL."""

    def __init__(self, sql_text: str) -> None:
        self.name = "nixp1t_" + uuid.uuid4().hex[:12]
        created = _run(["createdb", self.name])
        if created.returncode != 0:
            raise RuntimeError(f"createdb {self.name}: {created.stderr}")
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
            "w", suffix=".sql", prefix=self.name, delete=False
        )
        with handle:
            handle.write(sql_text)
        path = Path(handle.name)
        try:
            loaded = _run(
                [
                    "psql",
                    "-d",
                    self.name,
                    "-q",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    str(path),
                ]
            )
            if loaded.returncode != 0:
                raise RuntimeError(f"load {self.name}: {loaded.stderr[-500:]}")
        finally:
            path.unlink(missing_ok=True)

    def sql(self, statement: str) -> None:
        result = _psql(self.name, statement)
        if result.returncode != 0:
            raise RuntimeError(f"{statement[:60]}: {result.stderr[-300:]}")

    def drop(self) -> None:
        _run(["dropdb", "--if-exists", "--force", self.name])


@pytest.fixture(name="scratch")
def _scratch_factory() -> Iterator:
    made: list[_Scratch] = []

    def build(sql_text: str | None = None) -> _Scratch:
        db = _Scratch(sql_text if sql_text is not None else SCHEMA_SQL.read_text())
        made.append(db)
        return db

    yield build
    for db in made:
        db.drop()


# ------------------------------------------------------------- the CONTROL


def test_control_an_unmutated_scratch_database_inspects_clean(scratch) -> None:
    """The shipped DDL, loaded fresh: no defects.

    Without this, every red below could be the harness or a scratch-database
    artefact rather than the plant.
    """
    db = scratch()
    assert gate.inspect_database(db.name) == []


def test_the_shipped_gate_passes_against_the_live_database() -> None:
    """The gate, unmodified, against `nix_plane1` itself."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"Plane-1 database not provisioned here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    assert "SQLSTATE 42501" in result.evidence


# ------------------------------- THE BRIEF'S NAMED PLANT: append-only broken


def test_an_UPDATE_grant_on_the_log_reddens_the_gate(scratch) -> None:
    """`GRANT UPDATE ON plane1_event_log TO nix_limiter`.

    Every table still exists. Every column still exists. The enum is still
    §12.10's. A gate that checked existence would be serenely green over a
    database where the auditable record of money truth can be rewritten by the
    process that writes it.

    Both arms must fire: the CATALOG sees the grant, and the ATTEMPT succeeds
    where it must be refused. Either alone would be a weaker claim — the
    catalog can be read wrong, and an attempt can be refused for the wrong
    reason.
    """
    db = scratch()
    db.sql("GRANT UPDATE ON plane1_event_log TO nix_limiter")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM4") and "HOLDS UPDATE" in d for d in defects), defects
    assert any(
        d.startswith("ARM9") and "SUCCEEDED" in d and "REWRITE" in d for d in defects
    ), defects


def test_an_UPDATE_grant_on_ONE_PARTITION_reddens_the_gate(scratch) -> None:
    """The hole the per-partition loop exists for.

    PostgreSQL checks privileges on the table the statement NAMES. `UPDATE
    plane1_event_log SET ...` is checked against the parent and is still
    refused — so ARM 9, which names the parent, does not fire here at all.
    `UPDATE plane1_event_log_2026_08 SET ...` is checked against the CHILD and
    succeeds. A gate that inspected only the parent would call this database
    append-only, and it is not.
    """
    db = scratch()
    db.sql("GRANT UPDATE ON plane1_event_log_2026_08 TO nix_limiter")
    defects = gate.inspect_database(db.name)
    assert any(
        d.startswith("ARM4") and "plane1_event_log_2026_08" in d for d in defects
    ), defects
    # And the demonstration that the parent-level attempt is blind to it:
    direct = _psql(
        db.name,
        "SET ROLE nix_limiter; UPDATE plane1_event_log_2026_08 SET reason='t'",
    )
    assert direct.returncode == 0, direct.stderr
    via_parent = _psql(
        db.name, "SET ROLE nix_limiter; UPDATE plane1_event_log SET reason='t'"
    )
    assert via_parent.returncode != 0
    assert "permission denied" in via_parent.stderr


def test_a_DELETE_grant_reddens_the_gate(scratch) -> None:
    """Erasing a banked row is the same class as rewriting one."""
    db = scratch()
    db.sql("GRANT DELETE ON plane1_event_log TO nix_limiter")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM4") and "HOLDS DELETE" in d for d in defects), defects
    assert any("ERASE" in d for d in defects), defects


def test_a_TRUNCATE_grant_reddens_the_gate(scratch) -> None:
    """TRUNCATE is the one a BEFORE-UPDATE trigger would never have caught."""
    db = scratch()
    db.sql("GRANT TRUNCATE ON plane1_event_log TO nix_limiter")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM4") and "HOLDS TRUNCATE" in d for d in defects), defects
    assert any("EMPTY the record" in d for d in defects), defects


def test_a_SECOND_WRITER_reddens_the_gate(scratch) -> None:
    """§12.10: *Limiter sole writer. No new writers, ever.*

    An INSERT grant to the reader role is the whole violation in one statement,
    and it is the shape a well-meaning dashboard change would take.
    """
    db = scratch()
    db.sql("GRANT INSERT ON plane1_event_log TO nix_reader")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM4") and "HOLDS INSERT" in d for d in defects), defects
    assert any("SECOND WRITER" in d for d in defects), defects


# ---------------------------------------------------- the inventory, ARM 3


def test_an_event_type_MISSING_from_the_enum_reddens_the_gate(scratch) -> None:
    """§12.10 names an event the schema cannot record.

    Planted in the DDL text, because an enum member cannot be dropped. This is
    the direction that would let a money-gating transition be silently
    unrecordable — the Limiter would raise on insert, at runtime, in production.
    """
    original = SCHEMA_SQL.read_text()
    anchor = [
        line for line in original.splitlines() if line.strip().startswith("'halt_set',")
    ]
    assert len(anchor) == 1, f"plant anchor appears {len(anchor)} times, not once"
    text = original.replace(anchor[0] + "\n", "", 1)
    assert "'halt_set'," not in text, "plant did not apply"
    db = scratch(text)
    defects = gate.inspect_database(db.name)
    assert any(
        d.startswith("ARM3") and "cannot record" in d and "halt_set" in d
        for d in defects
    ), defects


def test_an_event_type_NOT_IN_the_spec_reddens_the_gate(scratch) -> None:
    """The other direction: a writable event type §12.10 never authorised.

    A one-directional comparison would accept this forever, and it is the
    likelier drift — adding an enum member is a one-line convenience.
    """
    db = scratch()
    db.sql("ALTER TYPE plane1_event_enum ADD VALUE 'quiet_adjustment'")
    defects = gate.inspect_database(db.name)
    assert any(
        d.startswith("ARM3") and "does not list" in d and "quiet_adjustment" in d
        for d in defects
    ), defects
    assert any("unaudited money event" in d for d in defects), defects


def test_a_NULLABLE_reason_reddens_the_gate(scratch) -> None:
    """§9 requires a reason on EVERY row.

    Nullable makes that a convention a caller can skip. The row would still
    exist, still be append-only, and still be useless for an audit — *"denied"*
    with no reason names no rule.
    """
    db = scratch()
    db.sql("ALTER TABLE plane1_event_log ALTER COLUMN reason DROP NOT NULL")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM3b") and "reason is NULLABLE" in d for d in defects), (
        defects
    )


# ------------------------------------------------- triggers, index, ARM 5/6


def test_a_TRIGGER_on_the_log_reddens_the_gate(scratch) -> None:
    """The weaker mechanism masquerading as the guarantee.

    A `BEFORE UPDATE ... RAISE` trigger looks like append-only enforcement to
    anyone reading the DDL. It is skipped by `session_replication_role`,
    removed by one `ALTER TABLE ... DISABLE TRIGGER`, and never fires on
    TRUNCATE. Its presence here would be actively misleading, so it is a
    defect even though it adds a restriction rather than removing one.
    """
    db = scratch()
    db.sql(
        "CREATE FUNCTION p1_no_update() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'append only'; END $$"
    )
    db.sql(
        "CREATE TRIGGER p1_no_update_trg BEFORE UPDATE ON plane1_event_log_2026_08 "
        "FOR EACH ROW EXECUTE FUNCTION p1_no_update()"
    )
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM5") and "trigger" in d for d in defects), defects


def test_dropping_the_exactly_once_index_reddens_the_gate(scratch) -> None:
    """§12.4's reconnect heal claims exactly-once; the index is the mechanism."""
    db = scratch()
    db.sql("DROP INDEX plane1_event_log_natural_key_uq")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM6") and "DUPLICATE" in d for d in defects), defects


# ------------------------------------- the OPPOSITE direction, ARM 7 and §17


def test_an_UNREBUILDABLE_projection_reddens_the_gate(scratch) -> None:
    """Over-restriction is a defect too.

    A gate that only ever demanded FEWER privileges could be satisfied by
    revoking everything — a database that is perfectly append-only and cannot
    be reconciled. §9 calls the positions table rebuildable; a rebuild is a
    DELETE and a re-fold.
    """
    db = scratch()
    db.sql("REVOKE DELETE ON plane1_positions FROM nix_limiter")
    defects = gate.inspect_database(db.name)
    assert any(d.startswith("ARM7") and "not rebuildable" in d for d in defects), (
        defects
    )


def test_a_writer_with_NO_rights_is_CANNOT_MEASURE_not_a_clean_refusal(
    scratch,
) -> None:
    """Hazard 4 of the §7.12 list, driven.

    Revoke INSERT from the Limiter and every ARM 9 refusal below it becomes
    true — of a role with no rights at all. "UPDATE was refused" is only
    evidence about append-only next to an INSERT that WORKS. The gate must say
    it measured nothing rather than collect four free greens.
    """
    db = scratch()
    db.sql("REVOKE INSERT ON plane1_event_log FROM nix_limiter")
    db.sql("REVOKE INSERT ON plane1_event_log_2026_08 FROM nix_limiter")
    db.sql("REVOKE INSERT ON plane1_event_log_2026_09 FROM nix_limiter")
    db.sql("REVOKE INSERT ON plane1_event_log_default FROM nix_limiter")
    defects = gate.inspect_database(db.name)
    assert any("ARM9 CANNOT_MEASURE" in d for d in defects), defects
    assert any("no rights at all" in d for d in defects), defects


def test_run_reports_CANNOT_MEASURE_for_an_absent_database(monkeypatch) -> None:
    """An absent Plane-1 database is CANNOT_MEASURE, never PASS (§17)."""
    monkeypatch.setattr(
        gate, "PLANE1_DB", "nixp1_definitely_absent_" + uuid.uuid4().hex[:8]
    )
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "does not exist" in result.detail


def test_the_inventory_is_transcribed_not_derived() -> None:
    """The §12.10 inventory is a literal in the gate, at the recorded size.

    D3.200's recurring shape is a gate reading its expected value out of the
    subject it polices. This assertion is what makes that a testable claim: if
    someone ever replaces the frozen set with a query against
    `plane1_event_enum`, the count stops being independent and this test is
    where the argument has to be re-made.
    """
    assert len(gate.SPEC_12_10_PLANE1_EVENTS) == 18
    assert "halt_set" in gate.SPEC_12_10_PLANE1_EVENTS
    assert "blackout_open" not in gate.SPEC_12_10_PLANE1_EVENTS  # Plane 2 only
