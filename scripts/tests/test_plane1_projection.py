"""B1 — §9's positions projection is REBUILDABLE FROM THE LOG. Driven, not asserted.

ARC 035 / Stage 1 / sub-agent B. Subject: `scripts/nixrisk/projection.py`.

§9, verbatim: *"Positions table = projection (rebuildable; dashboard +
reconciliation read it)."*

The arc brief's §0a, binding on this file:

> *a rebuild test that starts from an empty log proves nothing — rebuild from a
> log with real open/partial/closed history and prove the projection matches.*

So the history here is counted and asserted (`scripts/nixrisk/plane1_seed.py`:
**39 events, 8 trade_ids, 13 position-moving events, 6 positions**, and all three
projection states appear), the drop is a real one — `TRUNCATE` in the shipped
path and a full `DROP TABLE` + re-create from the shipped DDL in the strong
variant — and the comparison is FIELD BY FIELD between two reads out of
Postgres, never between the fold's own objects.

`test_an_EMPTY_log_rebuild_is_not_evidence` is the §0a hazard itself made into a
test: the empty rebuild does "succeed" and does "match", and the only thing that
distinguishes it from the real one is `RebuildReport.measured_enough`.
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
# House convention for these suites: test names spell the property in the case
# the contract uses, because a reader scanning a failure list needs the claim.
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixrisk import plane1_seed  # pylint: disable=import-error
from nixrisk.plane1_seed import (  # pylint: disable=import-error
    SEED_EVENT_COUNT,
    SEED_HISTORY,
    SEED_POSITION_COUNT,
    SEED_TRADE_IDS,
    EventSpec,
    seed,
)
from nixrisk.projection import (  # pylint: disable=import-error
    CLASSIFIED,
    MIN_FOLDED_EVENTS,
    PLANE1_DB,
    POSITION_AFFECTING,
    POSITION_NEUTRAL,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_PARTIAL,
    LogEvent,
    ProjectionError,
    Psql,
    diff_projections,
    enum_members,
    fold_events,
    read_log,
    read_meta,
    read_projection,
    rebuild,
)

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
    """A throwaway Plane-1 database built from the SHIPPED DDL. Prefix `p1b_`."""

    def __init__(self) -> None:
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

    def sql(self, statement: str) -> None:
        rc, _out, err = self.psql.run(statement, verbose=True)
        if rc != 0:
            raise RuntimeError(f"{statement[:70]}: {err[-400:]}")

    def drop(self) -> None:
        _run(["dropdb", "--if-exists", "--force", self.name])


@pytest.fixture(name="scratch")
def _scratch_factory() -> Iterator:
    made: list[_Scratch] = []

    def build(*, history: tuple[EventSpec, ...] | None = SEED_HISTORY) -> _Scratch:
        db = _Scratch()
        made.append(db)
        if history:
            seed(db.psql, history)
        return db

    yield build
    for db in made:
        db.drop()


# ---------------------------------------------------------- the history itself


def test_the_seeded_history_is_REAL_and_its_size_is_asserted(scratch) -> None:
    """§0a: 'an empty-log rebuild proves nothing'. This is what stops that.

    The counts are asserted rather than described, so a fixture that silently
    shrinks — the way a rebuild proof quietly becomes vacuous — reddens here
    before it can pass anywhere else.
    """
    db = scratch()
    events = read_log(db.psql)
    assert len(events) == SEED_EVENT_COUNT == 39
    assert len({e.trade_id for e in events} - {"-"}) == SEED_TRADE_IDS == 8
    result = fold_events(events)
    assert result.position_events == 13, result.position_events
    assert result.position_events >= MIN_FOLDED_EVENTS
    assert len(result.positions) == SEED_POSITION_COUNT == 6
    assert result.anomalies == (), result.anomalies
    states = {p.state for p in result.positions}
    assert states == {STATE_OPEN, STATE_PARTIAL, STATE_CLOSED}, states


def test_the_fold_computes_the_states_the_history_describes(scratch) -> None:
    """Open / partial / closed, per trade, with the §4 partial-fill rule applied.

    Spelled out per trade rather than by a count, because "six positions" is
    also true of six wrong positions.
    """
    db = scratch()
    by_trade = {p.trade_id: p for p in fold_events(read_log(db.psql)).positions}

    round_trip = by_trade["T-001"]
    assert (round_trip.state, round_trip.qty_open, round_trip.qty_filled) == (
        STATE_CLOSED,
        0,
        2,
    )
    assert str(round_trip.avg_entry_price) == "5000.25000000"

    # §4: a partial fill sets the position to the ACTUAL FILLED QTY and the
    # remainder is cancelled — 2 of 3, resolved, so OPEN at 2 and not PARTIAL.
    partial_then_cancelled = by_trade["T-002"]
    assert partial_then_cancelled.state == STATE_OPEN
    assert partial_then_cancelled.qty_open == 2
    assert str(partial_then_cancelled.avg_entry_price) == "18000.75000000"

    # Two protective scale-outs then a close: 4 filled, 0 open, CLOSED.
    scaled_out = by_trade["T-003"]
    assert (scaled_out.state, scaled_out.qty_filled, scaled_out.qty_open) == (
        STATE_CLOSED,
        4,
        0,
    )

    still_open = by_trade["T-004"]
    assert (still_open.state, still_open.qty_open) == (STATE_OPEN, 3)

    # §12.1's Sentinel flatten closes a live position.
    sentinel_closed = by_trade["T-006"]
    assert sentinel_closed.state == STATE_CLOSED
    assert sentinel_closed.qty_open == 0

    # A partial fill whose remainder is NOT yet resolved stays PARTIAL.
    unresolved = by_trade["T-007"]
    assert (unresolved.state, unresolved.qty_filled, unresolved.qty_open) == (
        STATE_PARTIAL,
        1,
        1,
    )

    # A DENIED signal and a GO-timeout produce no position at all.
    assert "T-005" not in by_trade
    assert "T-008" not in by_trade


# ----------------------------------------------------- THE REBUILD, the point


def test_the_projection_is_TRUNCATED_and_rebuilt_from_the_log_alone(scratch) -> None:
    """§9's `rebuildable`, driven: snapshot, destroy, re-fold, compare each field.

    Both sides of the comparison are `SELECT`s out of `plane1_positions` — never
    the fold's in-memory objects — so a fold that computed a perfect projection
    and wrote nothing fails here instead of passing.
    """
    db = scratch()
    first = rebuild(db.psql, source="test first fold")
    assert first.measured_enough
    assert first.positions_written == SEED_POSITION_COUNT
    before = read_projection(db.psql)
    assert len(before) == SEED_POSITION_COUNT

    second = rebuild(db.psql, source="test rebuild after TRUNCATE")
    after = read_projection(db.psql)

    assert second.positions_written == first.positions_written
    assert _field_by_field(before, after) == []
    assert diff_projections(fold_events(read_log(db.psql)).positions, after) == []
    meta = read_meta(db.psql)
    assert int(meta["rebuilt_through_event_id"]) == second.through_event_id
    assert meta["rebuild_source"] == "test rebuild after TRUNCATE"


def test_the_projection_survives_a_real_DROP_TABLE_and_rebuilds_identically(
    scratch,
) -> None:
    """The STRONG version of the drop.

    `TRUNCATE` is the privileged path §9's *rebuildable* actually grants the
    Limiter, and it is what the shipped rebuild uses. But a `TRUNCATE` leaves the
    relation, its defaults and its constraints in place, so it cannot rule out a
    projection that holds state the log does not. A `DROP TABLE` followed by a
    re-create from the SHIPPED DDL can, and that is what this drives.
    """
    db = scratch()
    rebuild(db.psql, source="pre-drop fold")
    before = read_projection(db.psql)
    assert len(before) == SEED_POSITION_COUNT

    ddl = _positions_ddl()
    db.sql("DROP TABLE plane1_positions")
    db.sql(ddl)
    db.sql(
        "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON plane1_positions "
        "TO nix_limiter; GRANT SELECT ON plane1_positions TO nix_reader"
    )
    assert read_projection(db.psql) == ()

    rebuild(db.psql, source="post-drop fold")
    assert _field_by_field(before, read_projection(db.psql)) == []


def test_an_EMPTY_log_rebuild_is_not_evidence(scratch) -> None:
    """The §0a hazard, made into a test rather than avoided by a comment.

    The empty rebuild genuinely succeeds and genuinely "matches" — that is the
    whole problem. `measured_enough` is the only thing that tells the two apart,
    and the shipped gate refuses to certify below it.
    """
    db = scratch(history=None)
    report = rebuild(db.psql, source="empty")
    assert report.positions_written == 0
    assert report.log_events == 0
    assert report.position_events == 0
    assert read_projection(db.psql) == ()
    # It "matched". And it is not evidence:
    assert report.measured_enough is False
    assert MIN_FOLDED_EVENTS > 0


def test_the_fold_orders_by_wal_seq_and_NOT_by_event_id(scratch) -> None:
    """The schema spec §2.2: *the WAL is the only place ordering is authoritative*.

    `event_id` is assigned at INSERT, so under group-commit a buffered batch can
    commit AFTER rows that happened later. Here the `event_id` order is the exact
    reverse of the `wal_seq` order; a fold keyed on `event_id` would close the
    position before it opened.
    """
    history = tuple(
        dataclasses_replace(spec, event_id=10_000 - spec.wal_seq)
        for spec in SEED_HISTORY
    )
    db = scratch(history=history)
    events = read_log(db.psql)
    ids = [e.event_id for e in sorted(events, key=lambda e: e.wal_seq)]
    assert ids == sorted(ids, reverse=True), "the plant did not invert event_id"

    result = fold_events(events)
    assert result.anomalies == (), result.anomalies
    by_trade = {p.trade_id: p for p in result.positions}
    assert by_trade["T-002"].qty_open == 2
    assert by_trade["T-003"].state == STATE_CLOSED
    assert by_trade["T-007"].state == STATE_PARTIAL


def test_the_fold_is_PURE_and_reads_no_database(scratch) -> None:
    """Twice over the same rows is twice the same answer, with no I/O between.

    A fold that read `plane1_positions` while rebuilding `plane1_positions` would
    be seeded by the thing it claims to derive, and every rebuild would match.
    """
    db = scratch()
    events = read_log(db.psql)
    assert (
        fold_events(events).positions == fold_events(list(reversed(events))).positions
    )


# ----------------------------------------------- the fold's own failure modes


def test_an_exit_before_any_fill_is_an_ANOMALY_not_a_silent_skip(scratch) -> None:
    """A log the fold cannot interpret is a finding about the RECORD.

    A fold that skipped uninterpretable rows would turn a corrupt log into a
    clean-looking projection, which is the failure this projection exists to make
    impossible.
    """
    db = scratch(
        history=(
            EventSpec(
                wal_seq=1,
                event_type="protective_exit",
                strategy_id="strat-es",
                trade_id="T-999",
                reason="an exit for a trade that never opened",
                symbol="ESU6",
                minute=1,
            ),
        )
    )
    result = fold_events(read_log(db.psql))
    assert result.positions == ()
    assert any("never filled" in a for a in result.anomalies), result.anomalies


def test_a_position_event_carrying_the_no_trade_sentinel_is_an_ANOMALY(
    scratch,
) -> None:
    """`'-'` means *this event has no trade*; a fill with no trade is unattributable."""
    db = scratch(
        history=(
            EventSpec(
                wal_seq=1,
                event_type="filled",
                strategy_id="strat-es",
                trade_id="-",
                reason="a fill with no trade",
                symbol="ESU6",
                minute=1,
                payload={"qty": "1", "price": "1.0", "side": "long"},
            ),
        )
    )
    result = fold_events(read_log(db.psql))
    assert result.positions == ()
    assert any("cannot be attributed" in a for a in result.anomalies), result.anomalies


def test_the_folds_classification_equals_the_schema_enum_BOTH_directions(
    scratch,
) -> None:
    """A type the fold has no rule for is an event that silently moves nothing.

    And a rule for a type the schema cannot record is a branch that can never
    run. One direction alone would accept the first forever — which is the
    likelier drift, because adding an enum member is a one-line convenience.
    """
    db = scratch(history=None)
    members = enum_members(db.psql)
    assert members == CLASSIFIED, {
        "in the schema, unruled by the fold": sorted(members - CLASSIFIED),
        "ruled by the fold, absent from the schema": sorted(CLASSIFIED - members),
    }
    assert POSITION_AFFECTING & POSITION_NEUTRAL == frozenset()
    assert len(members) == 18


# ------------------------------------------------- the sole-writer boundaries


def test_the_seed_REFUSES_the_live_plane1_database() -> None:
    """§12.10: a fixture that could write the production record IS a second writer.

    Not by convention — by a raise. The message must name the database and the
    rule, so a reader learns WHY rather than only that it was refused.
    """
    with pytest.raises(ProjectionError) as excinfo:
        seed(Psql(PLANE1_DB), SEED_HISTORY)
    assert PLANE1_DB in str(excinfo.value)
    assert "sole" in str(excinfo.value) or "Limiter" in str(excinfo.value)


def test_the_rebuild_writes_as_nix_limiter_and_CANNOT_write_the_log(scratch) -> None:
    """The asymmetry the rebuild depends on, proven by ATTEMPT in this database.

    `check_plane1_schema` ARM 9 proves this on the shipped DDL. It is re-driven
    here because §9's *rebuildable* and §9's *append-only* are the two halves of
    one grant, and a scratch database where the rebuild works is exactly where a
    reviewer would want to know the log is still shut.
    """
    db = scratch()
    rebuild(db.psql, source="privilege drive")
    assert len(read_projection(db.psql)) == SEED_POSITION_COUNT

    rc, _out, err = db.psql.run(
        "BEGIN; SET ROLE nix_limiter; TRUNCATE plane1_event_log; ROLLBACK;",
        verbose=True,
    )
    assert rc != 0
    assert "42501" in err, err[-300:]
    assert "permission denied for table plane1_event_log" in err, err[-300:]


# ------------------------------------------------------------------- helpers


def dataclasses_replace(spec: EventSpec, **changes) -> EventSpec:
    import dataclasses  # pylint: disable=import-outside-toplevel

    return dataclasses.replace(spec, **changes)


def _field_by_field(before, after) -> list[str]:
    left = {str(row["trade_id"]): dict(row) for row in before}
    right = {str(row["trade_id"]): dict(row) for row in after}
    defects = [f"trade {t} on only one side" for t in sorted(set(left) ^ set(right))]
    for trade_id in sorted(set(left) & set(right)):
        for field in sorted(left[trade_id]):
            if left[trade_id][field] != right[trade_id].get(field):
                defects.append(
                    f"trade {trade_id}.{field}: {left[trade_id][field]!r} -> "
                    f"{right[trade_id].get(field)!r}"
                )
    return defects


def _positions_ddl() -> str:
    """The `plane1_positions` DDL, sliced out of the SHIPPED schema file.

    Both slice anchors are asserted to appear exactly once before the slice is
    taken. A plant — or a slice — that matched nothing is a silent no-op, and the
    resulting red would read as a gate that failed to detect (debug.md §8 #4).
    """
    text = SCHEMA_SQL.read_text()
    start = "CREATE TABLE plane1_positions ("
    end = "CREATE INDEX plane1_positions_state_idx    ON plane1_positions (state);"
    assert text.count(start) == 1, f"slice anchor {start!r} is not unique"
    assert text.count(end) == 1, f"slice anchor {end!r} is not unique"
    return text[text.index(start) : text.index(end) + len(end)]


def test_a_LogEvent_orders_on_wal_seq_first() -> None:
    """The ordering key itself, so the property is not only implied by a fixture."""
    early = LogEvent(
        event_id=99,
        wal_seq=1,
        occurred_at="2026-08-17 09:00:00+00",
        event_type="signal",
        strategy_id="s",
        trade_id="T",
        reason="r",
        symbol=None,
        natural_key="a",
        payload={},
    )
    late = LogEvent(
        **{**early.__dict__, "event_id": 1, "wal_seq": 2, "natural_key": "b"}
    )
    assert min([late, early], key=lambda e: e.order_key) is early


def test_plane1_seed_declares_the_counts_it_ships() -> None:
    """The declared constants and the literal history cannot drift apart."""
    assert len(plane1_seed.SEED_HISTORY) == plane1_seed.SEED_EVENT_COUNT
    assert len({s.natural_key for s in SEED_HISTORY}) == SEED_EVENT_COUNT
    assert len({s.wal_seq for s in SEED_HISTORY}) == SEED_EVENT_COUNT
