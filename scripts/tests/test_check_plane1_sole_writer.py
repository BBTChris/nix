"""`check_plane1_sole_writer` — the DETECTION can-fail, committed not banked.

ARC 035 / Stage 1 / sub-agent A. §12.10: *Limiter sole writer. No new writers,
EVER.* This suite plants a second writer — five different shapes of one — and
requires the SHIPPED gate to name each.

Every plant applies to a COPY of `scripts/` and `checks/` in a scratch tree, or
to a throwaway Plane-1 database, and every one asserts its ANCHOR exists before
mutating: `str.replace` with no match is a silent no-op, and a plant that
matches nothing plants nothing while its red reads as a gate that failed to
detect (debug.md §8 #4). The copy never includes `.venv` or `.venv-dev`.

Each block carries an UNMUTATED CONTROL. Without one a red is not attributable
to the plant.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
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
import check_plane1_sole_writer as gate  # pylint: disable=import-error
import provision_plane1  # pylint: disable=import-error
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)

SCHEMA_SQL = REPO / "databases" / "schema" / "plane1.sql"

_HAS_PG = shutil.which("psql") is not None and shutil.which("createdb") is not None


@pytest.fixture(name="tree")
def _tree(tmp_path) -> Path:
    """A copy of the two scanned roots. NEVER `.venv` — see the arc's Phase 0.

    `shutil.ignore_patterns` matches EXACTLY: `".venv"` does not match
    `.venv-dev`. Seven fixtures copied 58 MB of `.venv-dev` each into a 31 G
    shared tmpfs this arc and produced 234 red tests across twenty unrelated
    subjects. Only `scripts/` and `checks/` are copied here, and neither
    contains a venv.
    """
    root = tmp_path / "tree"
    root.mkdir()
    for name in ("scripts", "checks"):
        shutil.copytree(
            REPO / name,
            root / name,
            ignore=shutil.ignore_patterns("__pycache__", ".venv", ".venv-dev"),
        )
    return root


@pytest.fixture(name="database")
def _database() -> Iterator[str]:
    if not _HAS_PG:
        pytest.skip("no local PostgreSQL client")
    name = provision_plane1.SCRATCH_PREFIX + "swtest_" + uuid.uuid4().hex[:10]
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


def _psql(db: str, sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603,B607 - fixed argv, no shell, PATH tool
        ["psql", "-d", db, "-qAt", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


# --------------------------------------------------------------- THE CONTROLS


def test_control_the_UNMUTATED_tree_scans_clean(tree) -> None:
    """The shipped tree: no unauthorised author.

    Without this, every red below could be the harness rather than the plant.
    """
    defects, counts = gate.scan_authorship(tree)
    assert not defects, defects
    assert counts["files"] >= gate.MIN_FILES_SCANNED
    assert counts["eventrow_sites"] >= gate.MIN_EVENTROW_SITES
    assert counts["enqueue_sites"] >= gate.MIN_ENQUEUE_SITES
    assert counts["unresolved"] == 0


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_control_the_shipped_gate_PASSES_against_this_tree() -> None:
    """The gate, unmodified, end to end — including the real privilege attempt."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"Plane-1 subject not reachable here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    assert "REFUSED" in result.evidence
    assert "42501" in result.evidence


# ------------------------------------------- ARM A: the PRIVILEGE, by attempt


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_a_SECOND_WRITER_grant_reddens_the_gate(database, tmp_path) -> None:
    """`GRANT INSERT ON plane1_event_log TO nix_reader` — the whole violation.

    This is the shape a well-meaning dashboard change takes, and it is what
    "refused by privilege, not merely absent from the code" means: the SHIPPED
    SINK, run under the reader's identity, now really writes.
    """
    for table in (
        "plane1_event_log",
        "plane1_event_log_2026_08",
        "plane1_event_log_2026_09",
        "plane1_event_log_default",
    ):
        granted = _psql(database, f"GRANT INSERT ON {table} TO nix_reader")
        assert granted.returncode == 0, granted.stderr
    granted = _psql(
        database, "GRANT USAGE ON SEQUENCE plane1_event_id_seq TO nix_reader"
    )
    assert granted.returncode == 0, granted.stderr

    defects, _evidence = gate.attempt_privilege(tmp_path, database)
    assert any("group-committed" in d and "nix_reader" in d for d in defects), defects
    assert any("no new writers, EVER" in d for d in defects), defects


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_a_LIMITER_with_no_INSERT_is_CANNOT_MEASURE_not_a_clean_refusal(
    database, tmp_path
) -> None:
    """Hazard 3 of the §7.12 list, driven.

    Revoke the Limiter's own INSERT and "the reader was refused" becomes true —
    of a database nobody can write. The gate must say it measured nothing rather
    than collect a free green.
    """
    for table in (
        "plane1_event_log",
        "plane1_event_log_2026_08",
        "plane1_event_log_2026_09",
        "plane1_event_log_default",
    ):
        revoked = _psql(database, f"REVOKE INSERT ON {table} FROM nix_limiter")
        assert revoked.returncode == 0, revoked.stderr
    with pytest.raises(gate.Unmeasurable) as caught:
        gate.attempt_privilege(tmp_path, database)
    assert "CONTROL" in str(caught.value)
    assert "no rights at all" in str(caught.value)


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_control_the_UNMUTATED_database_produces_no_ARM_A_defect(
    database, tmp_path
) -> None:
    defects, evidence = gate.attempt_privilege(tmp_path, database)
    assert not defects, defects
    assert any("REFUSED" in line for line in evidence), evidence


# --------------------------------------------- ARM B: the AUTHORSHIP, static


def test_a_ROGUE_SQL_AUTHOR_reddens_the_gate(tree) -> None:
    """A module composing its own `INSERT INTO plane1_event_log`.

    The dashboard-writes-an-audit-row shape. The database would refuse it today;
    the point of finding it statically is that the refusal happens at 03:00 in
    production and this happens at commit time.
    """
    # Assembled, so the literal never appears whole in THIS file — otherwise
    # the can-fail suite would itself be a B1 hit and the plant would be
    # indistinguishable from the harness (debug.md §8 #4, one layer over).
    rogue_sql = "INSERT INTO plane1_" + "event_log (reason) VALUES (%s)"
    planted = tree / "scripts" / "nixrisk" / "rogue_reporter.py"
    planted.write_text(
        '"""A second author."""\n'
        "\n"
        "def report(cur, reason):\n"
        f'    cur.execute("{rogue_sql}", (reason,))\n'
    )
    assert rogue_sql in planted.read_text(), "plant did not apply"
    defects, _ = gate.scan_authorship(tree)
    assert any(d.startswith("ARM B1") and "rogue_reporter.py" in d for d in defects), (
        defects
    )


def test_a_SECOND_SINK_IMPLEMENTATION_reddens_the_gate(tree) -> None:
    """A new `commit(self, rows, …)`: the object that turns rows into INSERTs."""
    planted = tree / "scripts" / "nixrisk" / "other_sink.py"
    planted.write_text(
        '"""A second sink."""\n'
        "\n"
        "class OtherSink:\n"
        "    def commit(self, rows):\n"
        "        return len(rows)\n"
    )
    defects, _ = gate.scan_authorship(tree)
    assert any(d.startswith("ARM B2") and "other_sink.py" in d for d in defects), (
        defects
    )


def test_a_commit_that_is_NOT_a_sink_does_NOT_redden_the_gate(tree) -> None:
    """The false-positive control. `picture.py` and `recovery.py` both define a
    `commit` and neither is a Plane-1 sink; a name-only match would report two
    permanent false positives and the gate would be edited to death."""
    planted = tree / "scripts" / "nixrisk" / "other_commit.py"
    planted.write_text(
        '"""Not a sink."""\n'
        "\n"
        "class Snapshot:\n"
        "    def commit(self, **changes):\n"
        "        return changes\n"
    )
    defects, _ = gate.scan_authorship(tree)
    assert not any(d.startswith("ARM B2") for d in defects), defects


def test_an_UNROUTED_EventRow_construction_reddens_the_gate(tree) -> None:
    """A Plane-1 row built with no syntactic route to `enqueue`."""
    planted = tree / "scripts" / "nixrisk" / "loose_row.py"
    planted.write_text(
        '"""A row that goes somewhere else."""\n'
        "\n"
        "from nixrisk.seam import EventKind, EventRow\n"
        "\n"
        "def stash(bus):\n"
        "    bus.publish(EventRow(kind=EventKind.SIGNAL, ts=0.0,\n"
        '                         strategy_id="s", reason="r"))\n'
    )
    defects, _ = gate.scan_authorship(tree)
    assert any(d.startswith("ARM B3") and "loose_row.py" in d for d in defects), defects
    assert any("may reach Plane 1 by another door" in d for d in defects), defects


def test_removing_the_ONLY_enqueue_from_a_producer_reddens_the_gate(tree) -> None:
    """The regression shape: an existing emitter loses its route.

    The anchor is asserted before the mutation, and asserted GONE after it — a
    `str.replace` that matched nothing would leave a green that reads as
    "the gate saw no defect" when the truth is "there was no defect to see".
    """
    target = tree / "scripts" / "nixrisk" / "reservations.py"
    text = target.read_text()
    anchor = "self._plane1.enqueue("
    assert text.count(anchor) == 1, f"anchor appears {text.count(anchor)} times, not 1"
    mutated = text.replace(anchor, "self._elsewhere.publish(", 1)
    assert anchor not in mutated, "plant did not apply"
    target.write_text(mutated)
    defects, _ = gate.scan_authorship(tree)
    assert any(d.startswith("ARM B3") and "reservations.py" in d for d in defects), (
        defects
    )


# ----------------------------------------------------------- vacuity and §17


def test_an_EMPTY_TREE_is_CANNOT_MEASURE_not_a_PASS(tmp_path) -> None:
    """The purest vacuous green: 'no unauthorised writer' over zero files."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "checks").mkdir()
    result = gate.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "non-vacuity floor" in result.detail


def test_a_MISMATCHED_database_literal_reddens_ARM_C(tree) -> None:
    """The wiring hazard `check_plane1_schema` §7.12 hazard 5 handed over."""
    target = tree / "checks" / "check_plane1_schema.py"
    text = target.read_text()
    anchor = 'PLANE1_DB = "nix_plane1"'
    assert text.count(anchor) == 1, f"anchor appears {text.count(anchor)} times, not 1"
    mutated = text.replace(anchor, 'PLANE1_DB = "somewhere_else"', 1)
    assert 'PLANE1_DB = "somewhere_else"' in mutated, "plant did not apply"
    target.write_text(mutated)
    defects = gate.wiring_defects(tree)
    assert any("somewhere_else" in d for d in defects), defects


def test_control_ARM_C_is_clean_on_the_real_tree() -> None:
    assert not gate.wiring_defects(REPO)


def test_the_gate_declares_its_own_scan_roots() -> None:
    """The scope of a scan is part of its result (§7.12 answer 2)."""
    assert gate.SCAN_ROOTS == ("scripts", "checks")


# --------------------------------------------------------------- ARM D (ARC 043)
#
# I8's half. ARM A drives the shipped sink as a role that DECLARES itself a
# non-writer and observes 42501 — a cooperative probe, and it has always passed.
# ARM D measures the identity ARM A assumes away: a process that declares
# nothing. These tests drive the SHIPPED arm, never a reimplementation of it.


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_control_ARM_D_is_clean_against_the_ENFORCED_live_record() -> None:
    """The real `nix_plane1`, with the enforcement installed: no ARM D defect.

    The control for every plant below. Without it a green ARM D would also be
    true of a record nobody can reach.
    """
    try:
        defects, evidence = gate.ambient_enforcement()
    except gate.Unmeasurable as exc:
        pytest.skip(f"the live Plane-1 record is not measurable here: {exc}")
    assert not defects, defects
    # NON-VACUITY: a clean ARM D must have actually attempted all three
    # identities, or "no defects" is a statement about an arm that did nothing.
    joined = " ".join(evidence)
    assert "CONTROL:" in joined and "AMBIENT:" in joined and "NON-WRITER:" in joined, (
        evidence
    )


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_an_UNENFORCED_database_reddens_ARM_D(database) -> None:
    """THE PLANT, and it needs no privileged edit to arm.

    A scratch database carries the shipped DDL — and therefore the shipped
    GRANTS — but no `pg_hba.conf` block, because those are per-database and the
    fragment names `nix_plane1` alone. So a scratch database IS the pre-ARC-043
    world in miniature: correct grants, ambient superuser access, sole writer by
    convention. Pointing the SHIPPED arm at one must produce the ambient defect,
    naming the forged row it would have banked.

    This is the plant `test_a_SECOND_WRITER_grant_reddens_the_gate` above cannot
    reach: that one grants INSERT to a declared non-writer, which is the
    cooperative surface. This one declares nothing at all.
    """
    defects, _evidence = gate.ambient_enforcement(database)
    ambient = [d for d in defects if "AMBIENT identity wrote" in d]
    assert ambient, f"ARM D did not fire on an unenforced database: {defects}"
    assert "no role declared at all" in ambient[0], ambient
    assert "CONVENTION here, not enforcement" in ambient[0], ambient


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_ARM_D_writes_NOTHING_durable_to_the_database_it_probes(database) -> None:
    """Every ARM D attempt is `BEGIN … ROLLBACK` with an explicit `event_id`.

    Measured rather than read off the SQL: the arm is run against a database
    where the ambient INSERT SUCCEEDS (so the write path is genuinely exercised
    — a rollback nobody reached would prove nothing), and the table must be
    empty afterwards and the sequence unmoved. A gate that forges a money row
    to prove money rows cannot be forged has already done the damage.
    """
    before = _psql(
        database,
        "select count(*), last_value from plane1_event_log, plane1_event_id_seq",
    ).stdout.strip()
    defects, _evidence = gate.ambient_enforcement(database)
    assert any("AMBIENT identity wrote" in d for d in defects), (
        "the write path was not exercised, so the rollback proves nothing"
    )
    after = _psql(
        database,
        "select count(*), last_value from plane1_event_log, plane1_event_id_seq",
    ).stdout.strip()
    assert before == after, f"ARM D left durable state behind: {before!r} -> {after!r}"


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_ARM_D_is_CANNOT_MEASURE_against_an_ABSENT_database() -> None:
    """§17: an unreachable subject is never a PASS."""
    absent = "p1a_definitely_absent_" + uuid.uuid4().hex[:8]
    with pytest.raises(gate.Unmeasurable) as excinfo:
        gate.ambient_enforcement(absent)
    assert absent in str(excinfo.value)


def test_the_gate_DECLARES_the_live_record_it_now_dials() -> None:
    """Check-contract rule 12: a declared resource set is checked against the
    observed one. ARM D dials `nix_plane1` on every run, so the token that was
    previously refused as unfalsifiable is now owed."""
    assert "postgres:nix_plane1" in gate.RESOURCES, gate.RESOURCES


def test_the_gate_DECLARES_the_enforcement_artifacts_as_SUBJECTS() -> None:
    """Both halves of the enforcement decide this gate's verdict, so both are
    SUBJECTS — an artifact that decides a verdict and is declared by nothing is
    what `check_artifact_gate_coverage` exists to catch."""
    for path in (
        "databases/schema/plane1_enforcement.sql",
        "databases/schema/plane1_hba.conf",
    ):
        assert path in gate.SUBJECTS, gate.SUBJECTS
        assert (REPO / path).is_file(), f"{path} is declared but absent"
