# pylint: disable=too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-positional-arguments
# `EventSpec` mirrors a `plane1_event_log` ROW, which has twelve columns in
# the schema frozen at Phase 0.4, and the builders take one argument per
# column so a fixture states every field it means. Collapsing them into a
# dict would move the field names out of the type and into strings.
# pylint: disable=duplicate-code
# R0801 must be disabled at the TOP of the file, before the docstring: the
# similarities checker reports at module scope and a pragma further down
# does not reach it. Same placement as check_nixverify_init.py and a dozen
# siblings. What it pairs here is this arc's Plane-1 modules by their shared
# psql helpers, declaration blocks and scratch-cluster fixtures — required by
# §4.2 (every check independently runnable and self-contained), and written
# by four sub-agents in worktrees that could not see each other.
"""The FIXTURE CONDUIT: real Plane-1 rows in a SCRATCH log, under the Limiter's role.

ARC 035 / Stage 1 / sub-agent B. Authority: `docs/nics_risk_subsystem_spec_v1.3.md`
§9, §12.10; schema `databases/schema/plane1.sql`.

------------------------------------------------------------------------------
WHY THIS EXISTS AND WHY IT IS NOT A SECOND WRITER (§12.10: no new writers, ever)
------------------------------------------------------------------------------
B1's proof needs a log with REAL history to fold — the arc brief's §0a says so in
as many words: *"an empty-log rebuild proves nothing."* Producing that history
means getting rows into `plane1_event_log`, and §12.10 says the Limiter is the
sole writer and there are no new ones, EVER — including in a test fixture.

Three things keep this inside that rule, and the third is the one that matters:

1. **Identity.** Every INSERT here runs under `SET ROLE nix_limiter`. That is a
   real privilege drop even from a superuser session — `current_user` becomes the
   role and the executor checks every statement against it — so these rows carry
   the Limiter's database identity and no other. A second *author* would be a
   different role, and `check_plane1_schema` ARM 9 proves by attempt that any
   other role is refused with SQLSTATE 42501.
2. **Scope.** `seed()` REFUSES to run against `nix_plane1`. Not by convention: by
   an explicit check that raises. A fixture that could write the production
   record would be a second writer in practice however it was labelled.
3. **Honesty about what it is NOT.** This is a conduit, not the Limiter's write
   path. The real path is `enqueue -> durable local WAL -> shared-pool writer ->
   group-commit` (§9), and the Postgres end of it is ARC 035 sub-agent A's commit
   sink. When that sink exists, the tests here should seed through IT and this
   module should shrink to the history it declares. Until then, seeding through
   the role is the closest a fixture can get, and saying so is the point.

**And the gap under all three, stated plainly:** `nixrisk/seam.py`'s `EventKind`
CANNOT emit a `filled` row at all — its own docstring lists `filled` among the
members *"STILL OMITTED … (no emitting code)"*. `filled` is the event the
positions projection is mostly a fold OF. So the history below is not "what the
Limiter would have written"; it is what the SCHEMA authorises and what §9's
inventory names, written under the Limiter's role because no Limiter code path
produces it yet. B1 proves the fold. It does not prove the wiring, and no green
here may be read as proving the wiring.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import dataclasses
import json
from collections.abc import Mapping, Sequence

from nixrisk.projection import PLANE1_DB, WRITER_ROLE, ProjectionError, Psql

#: Timestamps live inside the 2026-08 monthly partition the shipped DDL declares,
#: so the seed exercises a RANGE partition rather than the DEFAULT catch-all. A
#: fixture that only ever landed in DEFAULT would leave the partition routing —
#: and its per-partition grants — unexercised.
_DAY = "2026-08-17"


@dataclasses.dataclass(frozen=True)
class EventSpec:
    """One row to seed. `event_id` is explicit ONLY where the test needs it.

    Left `None`, the sequence assigns it — which is what production does, and is
    what makes `event_id` commit order rather than enqueue order. Set, it lets a
    test build a log whose `event_id` order is deliberately not its `wal_seq`
    order, which is the fold's ordering property made falsifiable.
    """

    wal_seq: int
    event_type: str
    strategy_id: str
    trade_id: str
    reason: str
    symbol: str | None = None
    payload: Mapping[str, str] = dataclasses.field(default_factory=dict)
    minute: int = 0
    event_id: int | None = None

    @property
    def occurred_at(self) -> str:
        """`occurred_at` — TRADE TIME, the partition key (schema spec §2.2)."""
        return f"{_DAY} {9 + self.minute // 60:02d}:{self.minute % 60:02d}:00+00"

    @property
    def natural_key(self) -> str:
        """The exactly-once key. Unique per seeded event, by construction."""
        return f"seed-{self.wal_seq:04d}-{self.event_type}"


def _fill(
    wal_seq: int,
    trade: str,
    strategy: str,
    symbol: str,
    side: str,
    qty: int,
    requested: int,
    price: str,
    stop: str,
    minute: int,
) -> EventSpec:
    return EventSpec(
        wal_seq=wal_seq,
        event_type="filled",
        strategy_id=strategy,
        trade_id=trade,
        reason=f"broker fill confirmation {qty}@{price}",
        symbol=symbol,
        minute=minute,
        payload={
            "qty": str(qty),
            "qty_requested": str(requested),
            "price": price,
            "side": side,
            "stop_distance": stop,
        },
    )


def _plain(
    wal_seq: int,
    event_type: str,
    strategy: str,
    trade: str,
    reason: str,
    minute: int,
    symbol: str | None = None,
    **payload: str,
) -> EventSpec:
    return EventSpec(
        wal_seq=wal_seq,
        event_type=event_type,
        strategy_id=strategy,
        trade_id=trade,
        reason=reason,
        symbol=symbol,
        minute=minute,
        payload=payload,
    )


#: §9's documented "this event has no trade" sentinel.
NO_TRADE = "-"

#: ---------------------------------------------------------------------------
#: THE HISTORY. Real open / partial / closed, and the counts are asserted.
#: ---------------------------------------------------------------------------
#:
#: Eight `trade_id`s, six of which reach a position; thirty-nine events, thirteen
#: of which move a position. Every projection state is represented — `open`,
#: `partial` AND `closed` — because a fixture in which every trade ends the same
#: way would leave two thirds of the fold's state machine unexercised, and a
#: rebuild that "matched" would be matching on the one branch it took.
#:
#: What is deliberately in here:
#:   * a round trip that opens and closes (T-001);
#:   * a PARTIAL fill whose remainder is IOC-cancelled, leaving a smaller OPEN
#:     position (T-002) — §4's *"position = actual filled qty"*;
#:   * a SCALE-OUT: two protective exits taking size off before a close (T-003);
#:   * a trade still fully OPEN at the end of the log (T-004);
#:   * a DENIED signal that must produce no position at all (T-005);
#:   * a §12.1 SENTINEL FLATTEN closing a live position (T-006);
#:   * a partial fill still UNRESOLVED, so the projection ends in `partial`
#:     (T-007);
#:   * a GO-timeout that never filled (T-008);
#:   * system rows carrying the `'-'` sentinel: HALT set/cleared, operator
#:     action, strategy lifecycle, drift audit, cold-start outcome.
SEED_HISTORY: tuple[EventSpec, ...] = (
    # -- T-001 ES long: a whole round trip -----------------------------------
    _plain(1, "signal", "strat-es", "T-001", "entry proposal", 0, "ESU6"),
    _plain(2, "accepted", "strat-es", "T-001", "gate admitted", 1, "ESU6"),
    _plain(3, "reservation_taken", "strat-es", "T-001", "margin reserved", 1, "ESU6"),
    _fill(4, "T-001", "strat-es", "ESU6", "long", 2, 2, "5000.25", "12", 2),
    _plain(
        5, "reservation_released", "strat-es", "T-001", "reservation freed", 2, "ESU6"
    ),
    _plain(6, "exit_intent", "strat-es", "T-001", "edge spent", 30, "ESU6"),
    _plain(7, "closed", "strat-es", "T-001", "round trip complete", 31, "ESU6"),
    # -- T-002 NQ short: partial fill, remainder cancelled, still open --------
    _plain(8, "signal", "strat-nq", "T-002", "entry proposal", 5, "NQU6"),
    _plain(9, "accepted", "strat-nq", "T-002", "gate admitted", 5, "NQU6"),
    _fill(10, "T-002", "strat-nq", "NQU6", "short", 1, 3, "18000.50", "20", 6),
    _fill(11, "T-002", "strat-nq", "NQU6", "short", 1, 3, "18001.00", "20", 6),
    _plain(
        12,
        "cancel",
        "strat-nq",
        "T-002",
        "IOC remainder cancelled; position is the actual filled qty (§4)",
        7,
        "NQU6",
    ),
    # -- T-003 ES long: scale-out then close ---------------------------------
    _plain(13, "signal", "strat-es", "T-003", "entry proposal", 10, "ESU6"),
    _plain(14, "accepted", "strat-es", "T-003", "gate admitted", 10, "ESU6"),
    _fill(15, "T-003", "strat-es", "ESU6", "long", 4, 4, "4999.00", "10", 11),
    _plain(
        16,
        "protective_exit",
        "strat-es",
        "T-003",
        "trail tightened; scale-out 1",
        20,
        "ESU6",
        qty="1",
    ),
    _plain(
        17,
        "protective_exit",
        "strat-es",
        "T-003",
        "trail tightened; scale-out 2",
        22,
        "ESU6",
        qty="1",
    ),
    _plain(18, "closed", "strat-es", "T-003", "round trip complete", 25, "ESU6"),
    # -- T-004 CL long: still open at the end of the log ---------------------
    _plain(19, "signal", "strat-cl", "T-004", "entry proposal", 12, "CLU6"),
    _plain(20, "accepted", "strat-cl", "T-004", "gate admitted", 12, "CLU6"),
    _fill(21, "T-004", "strat-cl", "CLU6", "long", 3, 3, "78.42", "15", 13),
    # -- T-005 GC: denied, so no position may exist --------------------------
    _plain(22, "signal", "strat-gc", "T-005", "entry proposal", 14, "GCZ6"),
    _plain(
        23, "denied", "strat-gc", "T-005", "correlation bucket cap (§7)", 14, "GCZ6"
    ),
    # -- T-006 ES long: closed by the §12.1 Sentinel -------------------------
    _plain(24, "signal", "strat-es", "T-006", "entry proposal", 16, "ESU6"),
    _plain(25, "accepted", "strat-es", "T-006", "gate admitted", 16, "ESU6"),
    _fill(26, "T-006", "strat-es", "ESU6", "long", 2, 2, "5010.75", "8", 17),
    _plain(
        27,
        "sentinel_flatten",
        "strat-es",
        "T-006",
        "retroactive: the §12.1 Sentinel flattened while the Limiter was dead",
        40,
        "ESU6",
        source="sentinel",
        retroactive="true",
    ),
    # -- T-007 NQ long: partial fill, remainder UNRESOLVED -> state 'partial' -
    _plain(28, "signal", "strat-nq", "T-007", "entry proposal", 18, "NQU6"),
    _plain(29, "accepted", "strat-nq", "T-007", "gate admitted", 18, "NQU6"),
    _fill(30, "T-007", "strat-nq", "NQU6", "long", 1, 2, "18100.25", "25", 19),
    # -- system rows: the '-' sentinel, §9's "no trade" ----------------------
    _plain(31, "halt_set", "__system__", NO_TRADE, "stale-data HALT set", 41),
    _plain(32, "halt_cleared", "__system__", NO_TRADE, "condition cleared", 45),
    _plain(
        33,
        "cold_start_outcome",
        "__system__",
        NO_TRADE,
        "cold start: provably flat, registration admitted",
        46,
    ),
    _plain(34, "operator_action", "__system__", NO_TRADE, "operator cleared HALT", 47),
    _plain(
        35,
        "strategy_lifecycle",
        "strat-nq",
        NO_TRADE,
        "force-deregister after heartbeat loss",
        48,
    ),
    _plain(
        36,
        "drift_audit",
        "__system__",
        NO_TRADE,
        "full-scan audit: no material drift",
        49,
    ),
    # -- T-008: a GO that timed out and never filled -------------------------
    _plain(37, "signal", "strat-gc", "T-008", "entry proposal", 50, "GCZ6"),
    _plain(
        38,
        "go_timeout",
        "strat-gc",
        "T-008",
        "no sized/denied feedback within T; treated as denied (§4)",
        51,
        "GCZ6",
    ),
    _plain(
        39,
        "reservation_released",
        "strat-nq",
        "T-002",
        "over-reservation freed",
        8,
        "NQU6",
    ),
)

#: Asserted in the tests and in the gate rather than trusted. A fixture that
#: silently shrinks is the way a rebuild proof quietly becomes vacuous.
SEED_EVENT_COUNT = 39
SEED_POSITION_COUNT = 6
SEED_TRADE_IDS = 8


def _rows_json(events: Sequence[EventSpec]) -> str:
    return json.dumps(
        [
            {
                "event_id": spec.event_id,
                "occurred_at": spec.occurred_at,
                "event_type": spec.event_type,
                "strategy_id": spec.strategy_id,
                "trade_id": spec.trade_id,
                "reason": spec.reason,
                "symbol": spec.symbol,
                "wal_seq": spec.wal_seq,
                "natural_key": spec.natural_key,
                "payload": dict(spec.payload),
            }
            for spec in events
        ]
    )


def seed(psql: Psql, events: Sequence[EventSpec] | None = None) -> int:
    """INSERT `events` into `psql`'s log AS `nix_limiter`. Returns rows written.

    REFUSES the production database. Point 2 of the module docstring: a fixture
    that could write `nix_plane1` would be a second writer whatever it was
    called, and a raise is the only version of that rule the database cannot be
    talked out of from here.

    `event_id` is supplied only where a spec names it; otherwise the column's
    `DEFAULT nextval(...)` runs, which is what production does — and which
    requires the `USAGE` grant on `plane1_event_id_seq` that the shipped DDL
    issues. A seed that always supplied the id would never exercise that grant.
    """
    if psql.dbname == PLANE1_DB:
        raise ProjectionError(
            f"refusing to seed {PLANE1_DB!r}: it is the live Plane-1 record and "
            f"§12.10 admits no writer but the Limiter. Build a scratch database "
            f"from databases/schema/plane1.sql instead"
        )
    events = SEED_HISTORY if events is None else events
    payload = _rows_json(events)
    fence = "$p1seed$"
    if fence in payload:  # pragma: no cover - defensive
        raise ProjectionError("seed payload contains its own dollar-quote tag")
    # nosec B608 - the only interpolation is the module constant WRITER_ROLE.
    # Every ROW value travels as JSON through a `$p1seed$` dollar-quoted literal
    # and is unpacked server-side by `jsonb_to_recordset`, which is why the
    # fence collision above is checked and raises: the values never become SQL
    # text at all. That is a stronger position than escaping would be.
    statement = (  # nosec B608
        "BEGIN;\n"
        f"SET ROLE {WRITER_ROLE};\n"
        "INSERT INTO plane1_event_log "
        "(event_id, occurred_at, event_type, strategy_id, trade_id, reason, "
        " symbol, wal_seq, natural_key, payload)\n"
        "SELECT coalesce(s.event_id, nextval('plane1_event_id_seq')), "
        "s.occurred_at, s.event_type, s.strategy_id, s.trade_id, s.reason, "
        "s.symbol, s.wal_seq, s.natural_key, s.payload\n"
        "FROM json_to_recordset(" + fence + payload + fence + ") AS s("  # nosec B608
        "event_id bigint, occurred_at timestamptz, event_type plane1_event_enum, "
        "strategy_id text, trade_id text, reason text, symbol text, "
        "wal_seq bigint, natural_key text, payload jsonb)\n"
        "ORDER BY s.wal_seq;\n"
        "COMMIT;\n"
    )
    rc, _out, err = psql.run(statement, verbose=True)
    if rc != 0:
        raise ProjectionError(f"seed failed on {psql.dbname}: {err[-500:]}")
    return len(events)
