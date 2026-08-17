"""`check_plane1_projection` — the DETECTION can-fail, committed rather than banked.

ARC 035 / Stage 1 / sub-agent B. Every plant below builds a REAL scratch Postgres
database from the shipped `databases/schema/plane1.sql`, seeds the shipped
history through the Limiter's role, applies exactly ONE mutation, and drives the
SHIPPED gate's own arms against it. The live `nix_plane1` database is never
mutated.

**The CONTROL comes first and it is not a formality.** Without a green over an
unmutated scratch database, every red below could be the harness, the seed, or a
scratch-database artefact rather than the plant — and a red that is not
attributable to the plant is not a detection.

**Every plant asserts its own anchor.** A `str.replace` with no match is a silent
no-op and a plant that matched nothing plants nothing; the resulting red reads as
a gate that failed to detect (debug.md §8 #4), which is the opposite of the
truth.
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
# pylint: disable=missing-function-docstring,protected-access
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import check_plane1_projection as gate  # pylint: disable=import-error
from nixrisk import plane1_seed  # pylint: disable=import-error
from nixrisk.projection import Psql, rebuild  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

SCHEMA_SQL = REPO / "databases" / "schema" / "plane1.sql"

pytestmark = pytest.mark.skipif(
    shutil.which("psql") is None or shutil.which("createdb") is None,
    reason="no local PostgreSQL client; the subject is a live database",
)


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        argv, capture_output=True, text=True, timeout=180, check=False
    )


class _Scratch:
    """A throwaway Plane-1 database, seeded and folded. Prefix `p1b_`."""

    def __init__(self, *, seeded: bool = True, folded: bool = True) -> None:
        self.name = "p1b_" + uuid.uuid4().hex[:12]
        created = _run(["createdb", self.name])
        if created.returncode != 0:
            raise RuntimeError(f"createdb {self.name}: {created.stderr}")
        loaded = _run(
            [
                "psql",
                "-d",
                self.name,
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(SCHEMA_SQL),
            ]
        )
        if loaded.returncode != 0:
            raise RuntimeError(f"load {self.name}: {loaded.stderr[-500:]}")
        self.psql = Psql(self.name)
        if seeded:
            plane1_seed.seed(self.psql)
        if folded:
            rebuild(self.psql, source="can-fail control fold")

    def sql(self, statement: str) -> None:
        rc, _out, err = self.psql.run(statement, verbose=True)
        if rc != 0:
            raise RuntimeError(f"{statement[:70]}: {err[-400:]}")

    def drop(self) -> None:
        _run(["dropdb", "--if-exists", "--force", self.name])


@pytest.fixture(name="scratch")
def _scratch_factory() -> Iterator:
    made: list[_Scratch] = []

    def build(**kwargs) -> _Scratch:
        db = _Scratch(**kwargs)
        made.append(db)
        return db

    yield build
    for db in made:
        db.drop()


# ------------------------------------------------------------- the CONTROLS


def test_control_a_seeded_and_folded_scratch_database_inspects_clean(scratch) -> None:
    """The green every red below is attributed against."""
    db = scratch()
    assert gate.arm1_classification(db.psql) == []
    defects, note = gate.arm3_live_drift(db.psql)
    assert defects == [], defects
    assert "6 projection row(s)" in note, note


def test_control_the_rebuild_arm_passes_on_the_shipped_DDL() -> None:
    """ARM 2 against nothing but the shipped schema and the shipped history.

    This is the arm that always has a real history, so it is the arm the gate's
    certification rests on. It builds and drops its own database.
    """
    defects, note = gate.arm2_rebuild(SCHEMA_SQL)
    assert defects == [], defects
    assert "39 log events" in note, note
    assert "13 of them position-moving" in note, note


def test_the_shipped_gate_runs_against_the_live_database() -> None:
    """The gate, unmodified, end to end."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"Plane-1 not measurable here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    assert "REBUILDABLE" in result.evidence


# ------------------------------------------ ARM 3: the projection drifts from the log


def test_a_TAMPERED_projection_row_reddens_the_gate(scratch) -> None:
    """The whole point of a projection gate: the table and the log part company.

    Every table still exists, every column still exists, the row count is
    unchanged, and the projection now claims a size the log does not support. A
    gate that counted rows would be serenely green over a dashboard reading a
    position that is not there.
    """
    db = scratch()
    before = db.psql.must(
        "select qty_open from plane1_positions where trade_id='T-004'"
    )
    assert before == "3", f"plant anchor missing: T-004 qty_open was {before!r}"
    db.sql(
        "SET ROLE nix_limiter; UPDATE plane1_positions SET qty_open = 99 "
        "WHERE trade_id = 'T-004'"
    )
    defects, _note = gate.arm3_live_drift(db.psql)
    assert any(
        d.startswith("ARM3") and "T-004" in d and "qty_open" in d for d in defects
    ), defects
    assert any("the fold says 3" in d for d in defects), defects


def test_a_DELETED_projection_row_reddens_the_gate(scratch) -> None:
    """A position the log produces and the projection does not hold.

    This is the dangerous direction: real exposure the record has forgotten.
    """
    db = scratch()
    assert db.psql.must("select count(*) from plane1_positions") == "6"
    db.sql("SET ROLE nix_limiter; DELETE FROM plane1_positions WHERE trade_id='T-002'")
    defects, _note = gate.arm3_live_drift(db.psql)
    assert any(
        d.startswith("ARM3") and "T-002" in d and "does NOT hold" in d for d in defects
    ), defects


def test_a_PHANTOM_projection_row_reddens_the_gate(scratch) -> None:
    """A position with no events behind it — the opposite direction.

    A gate that only ever asked "is every folded position present?" would accept
    this forever, and a phantom position is a phantom margin commitment.
    """
    db = scratch()
    db.sql(
        "SET ROLE nix_limiter; INSERT INTO plane1_positions (trade_id, strategy_id, "
        "symbol, side, state, qty_open, qty_filled, last_event_id) VALUES "
        "('T-PHANTOM', 'strat-x', 'ESU6', 'long', 'open', 5, 5, 1)"
    )
    defects, _note = gate.arm3_live_drift(db.psql)
    assert any(
        d.startswith("ARM3") and "T-PHANTOM" in d and "no events behind it" in d
        for d in defects
    ), defects


def test_a_STALE_WATERMARK_that_no_longer_describes_the_table_reddens_the_gate(
    scratch,
) -> None:
    """The watermark is the projection's claim about where it is in the log.

    Wound back to before the last fills, the fold through it no longer produces
    the table that is stored — which is exactly a projection that cannot say
    where it is.
    """
    db = scratch()
    assert (
        db.psql.must("select rebuilt_through_event_id from plane1_projection_meta")
        != "5"
    )
    db.sql(
        "SET ROLE nix_limiter; UPDATE plane1_projection_meta "
        "SET rebuilt_through_event_id = 5 WHERE id = 1"
    )
    defects, _note = gate.arm3_live_drift(db.psql)
    assert defects, "a watermark that no longer describes the table must redden"
    assert any(d.startswith("ARM3") for d in defects), defects


def test_a_NEVER_REBUILT_projection_is_reported_as_NOT_MEASURED_not_as_agreement(
    scratch,
) -> None:
    """§17, one layer in: an arm that could not measure must say so.

    A seeded log with an untouched projection is not agreement — it is a fold
    that has never run. The arm returns no defect (there is nothing to compare)
    and the NOTE says the drift arm did not measure, so the evidence line cannot
    be read as a clean bill of health.
    """
    db = scratch(folded=False)
    defects, note = gate.arm3_live_drift(db.psql)
    assert defects == []
    assert "did NOT measure" in note, note
    assert "never rebuilt" in note, note


# ------------------------------------------------------- ARM 1: the classification


def test_an_UNRULED_event_type_reddens_the_gate(scratch) -> None:
    """A type the schema can record and the fold has no rule for.

    Adding an enum member is a one-line convenience, so this is the likelier
    drift — and the new type is exactly the case where a fold decision is owed.
    """
    db = scratch(seeded=False, folded=False)
    db.sql("ALTER TYPE plane1_event_enum ADD VALUE 'quiet_adjustment'")
    defects = gate.arm1_classification(db.psql)
    assert any(
        d.startswith("ARM1") and "quiet_adjustment" in d and "no rule for" in d
        for d in defects
    ), defects


def test_a_PHANTOM_fold_rule_reddens_the_gate(scratch, monkeypatch) -> None:
    """The other direction: a rule for a type the schema cannot record.

    A branch that can never run is dead weight at best and, at worst, a fold
    written against an event inventory that no longer exists.
    """
    db = scratch(seeded=False, folded=False)
    monkeypatch.setattr(
        gate, "CLASSIFIED", gate.CLASSIFIED | frozenset({"invented_event"})
    )
    defects = gate.arm1_classification(db.psql)
    assert any(
        d.startswith("ARM1") and "invented_event" in d and "can never run" in d
        for d in defects
    ), defects


# ---------------------------------------- ARM 2: the §0a hazards, driven not argued


def test_a_TRIVIAL_history_makes_the_rebuild_arm_CANNOT_MEASURE(monkeypatch) -> None:
    """The brief's §0a hazard itself: *an empty-log rebuild proves nothing.*

    Shrink the seeded history below the floor and the arm must refuse to certify
    rather than collect a free green — the rebuild genuinely succeeds and
    genuinely matches, which is precisely the problem.
    """
    tiny = plane1_seed.SEED_HISTORY[:2]
    assert len(tiny) == 2, "plant anchor: the history must be sliceable"
    monkeypatch.setattr(plane1_seed, "SEED_HISTORY", tiny)
    monkeypatch.setattr(plane1_seed, "SEED_EVENT_COUNT", 2)
    defects, _note = gate.arm2_rebuild(SCHEMA_SQL)
    assert any("ARM2 CANNOT_MEASURE" in d for d in defects), defects
    assert any("below the floor" in d for d in defects), defects


def test_a_history_where_EVERY_trade_CLOSES_makes_the_rebuild_arm_CANNOT_MEASURE(
    monkeypatch,
) -> None:
    """A rebuild proof over one branch of the state machine is a proof about one
    branch. Strip every trade that ends `open` or `partial` and the arm must say
    it did not measure."""
    closed_only = tuple(
        spec
        for spec in plane1_seed.SEED_HISTORY
        if spec.trade_id in {"T-001", "T-003", "T-006"}
    )
    assert len(closed_only) >= 12, "plant anchor: the closed-only slice must be real"
    monkeypatch.setattr(plane1_seed, "SEED_HISTORY", closed_only)
    monkeypatch.setattr(plane1_seed, "SEED_EVENT_COUNT", len(closed_only))
    monkeypatch.setattr(plane1_seed, "SEED_POSITION_COUNT", 3)
    defects, _note = gate.arm2_rebuild(SCHEMA_SQL)
    assert any("CANNOT_MEASURE" in d and "ended the same way" in d for d in defects), (
        defects
    )


# ------------------------------------------------------------------ §17 paths


def test_run_reports_CANNOT_MEASURE_for_an_absent_database(monkeypatch) -> None:
    """An absent Plane-1 database is CANNOT_MEASURE, never PASS (§17)."""
    monkeypatch.setattr(
        gate, "PLANE1_DB", "p1b_definitely_absent_" + uuid.uuid4().hex[:8]
    )
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "does not exist" in result.detail


def test_the_gate_declares_falsifiable_resources() -> None:
    """D3.152: a token no observation could contradict is not a declaration.

    Every token here names a binary this process really spawns, which the process
    table can contradict. A `postgres:nix_plane1` token could not be.
    """
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
        "subprocess:psql",
        "subprocess:createdb",
        "subprocess:dropdb",
    )
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON
    assert gate.DEPENDS_ON == ("check_plane1_schema",)
