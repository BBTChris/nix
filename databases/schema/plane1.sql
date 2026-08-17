-- ============================================================================
-- Nix — PLANE 1: the durable financial record  (v1.0.0, ARC 035 / Phase 0.4)
--
-- Authority: docs/nics_risk_subsystem_spec_v1.3.md §9 (Persistence Model,
-- event-sourced) and §12.10 (two-plane model, Plane 1 = Postgres append-only,
-- Limiter sole writer, NO NEW WRITERS, EVER).
-- Frozen companion spec: docs/nix_plane1_schema_spec.md.
--
-- ----------------------------------------------------------------------------
-- THIS IS NOT THE ANALYTICS DATABASE, AND THE BOUNDARY IS STRUCTURAL
-- ----------------------------------------------------------------------------
-- `nix_db_schema_spec.docx` / `trade_history.sql` define the backtest /
-- paper / live trade-history store: one row per ROUND TRIP, rows that MUTATE
-- when exits land (`updated_at` maintained by trigger), regenerable backtest
-- leaves that are deliberately UNLOGGED. That store is for evaluation.
--
-- Plane 1 is the opposite object in every one of those dimensions: one row per
-- TRANSITION, rows that never mutate at all, and nothing in it is regenerable
-- because it IS the record. Sharing a database would put a store whose writer
-- role holds UPDATE beside a store whose entire safety property is that no
-- writer holds UPDATE — and a privilege model is only as strong as the
-- smallest grant in the database it lives in.
--
-- THE SEAM, DECLARED RATHER THAN ASSUMED (§8, and the brief's instruction):
-- a closed LIVE trade eventually appears in `trade_history.trades_live_<sym>`.
-- That migration is a READ of Plane 1 and a WRITE to the analytics store, by
-- an analytics-side job that does not exist yet. It is NOT a Plane-1 writer,
-- it is NOT this arc, and nothing here performs it. What this file guarantees
-- is only that the read side is possible: a closed trade's full transition
-- history is recoverable from `plane1_event_log` by `trade_id`.
--
-- ----------------------------------------------------------------------------
-- APPEND-ONLY BY PRIVILEGE, NOT BY TRIGGER
-- ----------------------------------------------------------------------------
-- A BEFORE UPDATE trigger that raises is a rule the table's owner can drop, a
-- superuser can disable with one ALTER TABLE, and `session_replication_role =
-- replica` skips wholesale. It also protects nothing against TRUNCATE. The
-- grant is checked by the executor on every statement and there is no
-- equivalent bypass short of re-granting, which is a catalog change a gate can
-- see. So: the writer role is GRANTed SELECT and INSERT on the log and is
-- granted nothing else, ever. There is no trigger on the log and there must
-- not be one — a trigger would make the weaker mechanism look like the
-- guarantee.
--
-- Validated live against PostgreSQL 18.4 on this node (the analytics spec's
-- "validated against PostgreSQL 16" refers to a different store and a
-- different cluster generation; see the schema spec's version note).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Roles. Cluster-global and idempotent, exactly like the analytics DDL.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nix_limiter') THEN
        CREATE ROLE nix_limiter NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nix_reader') THEN
        CREATE ROLE nix_reader NOLOGIN;
    END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- The §12.10 Plane-1 event inventory, as a type.
--
-- EXACTLY the rows of §12.10's table that carry a Plane-1 tick, and nothing
-- else. Members are not a superset "for convenience": an event type that can
-- be written but is not in the spec's inventory is an unaudited money event,
-- and an inventory member with no enum value is an event that cannot be
-- recorded at all. `check_plane1_schema` compares this type against the
-- inventory in BOTH directions for that reason.
--
-- Plane-2-only events (crash-loop counts, heartbeat loss, blackout open/close,
-- feed staleness, monotonic-guard discards, alerts, systemd process events)
-- are deliberately ABSENT. They are diagnostic, they belong in journald, and
-- §12.10 is explicit that Plane 2 is never a reconciliation input.
-- ----------------------------------------------------------------------------
CREATE TYPE plane1_event_enum AS ENUM (
    -- trade lifecycle (§9, §3)
    'signal',               -- strategy proposal reached the Limiter
    'accepted',             -- gate admitted; order released to broker-order
    'denied',               -- gate refused; `reason` carries the deciding rule
    'filled',               -- confirmed fill (price captured AT the fill, §9)
    'exit_intent',          -- exit decided, not yet confirmed
    'closed',               -- round trip complete; final trail level rides here
    'protective_exit',      -- stop / session-close / risk-kill exit
    -- capital reservation (§3, §6)
    'reservation_taken',
    'reservation_released',
    -- order-path terminals (§12.10 "added")
    'cancel',               -- incl. IOC remainder-cancel on partial fill
    'go_timeout',
    -- system transitions that GATE money (§12.10 "anything that changes or
    -- gates money gets a Plane-1 row")
    'drift_audit',          -- §11.7 full-scan reconciliation finding
    'sentinel_flatten',     -- §12.1, booked via marker replay at cold start
    'halt_set',             -- §12.5; Limiter-down case booked retroactively
    'halt_cleared',
    'operator_action',      -- §12.11 authenticated verbs
    'strategy_lifecycle',   -- register/force-deregister/kill/relaunch/
                            -- quarantine/restore
    'cold_start_outcome'    -- §4 reconciliation result
);

-- ----------------------------------------------------------------------------
-- The event id sequence.
--
-- An EXPLICIT sequence, not GENERATED ... AS IDENTITY. The analytics store
-- learned this the hard way: identity columns on a PARTITIONED table are a
-- property of the parent that partitions do not inherit usefully, and the
-- grant that makes `nextval()` work for a non-owner writer has to be issued on
-- the sequence by name. Naming it means the grant can be named too.
-- ----------------------------------------------------------------------------
CREATE SEQUENCE plane1_event_id_seq AS BIGINT START WITH 1 INCREMENT BY 1;

-- ----------------------------------------------------------------------------
-- plane1_event_log — THE record. One row per transition. Never overwritten.
-- ----------------------------------------------------------------------------
CREATE TABLE plane1_event_log (
    event_id      BIGINT      NOT NULL DEFAULT nextval('plane1_event_id_seq'),

    -- §9: "Timestamp + strategy_id + trade_id + reason on every row."
    -- Two timestamps, because they answer different questions and conflating
    -- them is how a crash gap becomes invisible:
    --   occurred_at — when the transition happened, stamped by the Limiter at
    --                 enqueue, carried through the WAL. This is trade time.
    --   recorded_at — when the row actually landed in Postgres at group-commit.
    -- `recorded_at - occurred_at` IS the commit lag, and after a crash the
    -- widest gap in `occurred_at` with no rows either side is the crash gap
    -- that cold-start reconciliation has to heal against broker truth.
    occurred_at   TIMESTAMPTZ NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    event_type    plane1_event_enum NOT NULL,

    -- NOT NULL, with documented sentinels rather than NULLs. A NULL here would
    -- mean "unknown", and none of these are ever unknown: a HALT set by the
    -- operator genuinely has no trade, which is a different fact from a filled
    -- row whose trade_id was lost. The sentinels are '-' for both fields and
    -- the CHECK below forbids empty strings, so "absent" and "blank" cannot be
    -- confused.
    strategy_id   TEXT        NOT NULL,
    trade_id      TEXT        NOT NULL,
    reason        TEXT        NOT NULL,

    symbol        TEXT,       -- NULL only for genuinely symbol-less events

    -- Ordering and idempotency.
    --   wal_seq     — the local WAL record number this row came from. The WAL
    --                 is the only place ordering is authoritative; Postgres
    --                 commit order under group-commit is batch order, and
    --                 event_id is assigned at INSERT, not at enqueue.
    --   natural_key — the event's identity for exactly-once replay. A
    --                 reconnect flush that re-delivers a buffered record
    --                 presents the same (natural_key, occurred_at) pair and is
    --                 refused by the unique index rather than duplicated.
    wal_seq       BIGINT      NOT NULL,
    natural_key   TEXT        NOT NULL,

    payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT plane1_event_log_strategy_id_nonblank CHECK (strategy_id <> ''),
    CONSTRAINT plane1_event_log_trade_id_nonblank    CHECK (trade_id <> ''),
    CONSTRAINT plane1_event_log_reason_nonblank      CHECK (reason <> ''),
    CONSTRAINT plane1_event_log_wal_seq_positive     CHECK (wal_seq >= 0)
) PARTITION BY RANGE (occurred_at);

-- A unique index on a partitioned table must contain the partition key, so
-- exactly-once is enforced per (natural_key, occurred_at). That is the right
-- grain anyway: the same logical event replayed carries its own original
-- occurred_at out of the WAL, so a duplicate delivery collides. Two DIFFERENT
-- events sharing a natural key at different instants are, by construction, not
-- the same event.
CREATE UNIQUE INDEX plane1_event_log_natural_key_uq
    ON plane1_event_log (natural_key, occurred_at);

CREATE INDEX plane1_event_log_trade_idx ON plane1_event_log (trade_id, occurred_at);
CREATE INDEX plane1_event_log_type_idx  ON plane1_event_log (event_type, occurred_at);
CREATE INDEX plane1_event_log_wal_idx   ON plane1_event_log (wal_seq);

-- Partitions. Monthly ranges plus a DEFAULT catch-all: the analytics store's
-- own convention, and for its reason — a row that lands in DEFAULT is not
-- lost, it is EVIDENCE that partition onboarding was skipped. Losing a Plane-1
-- row to a missing partition would be the worst failure this file can have.
CREATE TABLE plane1_event_log_2026_08 PARTITION OF plane1_event_log
    FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');
CREATE TABLE plane1_event_log_2026_09 PARTITION OF plane1_event_log
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');
CREATE TABLE plane1_event_log_default PARTITION OF plane1_event_log DEFAULT;

-- ----------------------------------------------------------------------------
-- plane1_positions — the PROJECTION (§9: "Positions table = projection
-- (rebuildable; dashboard + reconciliation read it)").
--
-- Derived state. It may be TRUNCATEd and rebuilt from `plane1_event_log`
-- alone at any time, and that is exactly why the writer role holds UPDATE and
-- DELETE here and holds neither on the log. The asymmetry is the design: the
-- log is the truth, this is a cache of a fold over it.
-- ----------------------------------------------------------------------------
CREATE TYPE plane1_position_state_enum AS ENUM ('open', 'partial', 'closed');

CREATE TABLE plane1_positions (
    trade_id          TEXT        PRIMARY KEY,
    strategy_id       TEXT        NOT NULL,
    symbol            TEXT        NOT NULL,
    side              TEXT        NOT NULL CHECK (side IN ('long', 'short')),
    state             plane1_position_state_enum NOT NULL,
    qty_open          BIGINT      NOT NULL CHECK (qty_open >= 0),
    qty_filled        BIGINT      NOT NULL CHECK (qty_filled >= 0),
    avg_entry_price   NUMERIC(18,8),
    stop_distance     NUMERIC(18,8),
    opened_at         TIMESTAMPTZ,
    closed_at         TIMESTAMPTZ,
    -- The fold's watermark. A projection that cannot say WHERE it is in the
    -- log is a projection nobody can reconcile against.
    last_event_id     BIGINT      NOT NULL,
    CONSTRAINT plane1_positions_closed_is_flat
        CHECK (state <> 'closed' OR qty_open = 0)
);

CREATE INDEX plane1_positions_strategy_idx ON plane1_positions (strategy_id);
CREATE INDEX plane1_positions_state_idx    ON plane1_positions (state);

-- ----------------------------------------------------------------------------
-- plane1_projection_meta — one row, naming how far the projection is folded.
--
-- Single-row by CHECK constraint rather than by convention: "there is one row"
-- enforced by a comment is a claim, enforced by `id = 1` is a fact.
-- ----------------------------------------------------------------------------
CREATE TABLE plane1_projection_meta (
    id                       SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    rebuilt_through_event_id BIGINT      NOT NULL DEFAULT 0,
    rebuilt_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    rebuild_source           TEXT        NOT NULL DEFAULT 'never rebuilt'
);
INSERT INTO plane1_projection_meta (id) VALUES (1);

-- ============================================================================
-- PRIVILEGES — the append-only guarantee lives here and nowhere else.
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO nix_limiter, nix_reader;

-- THE LOG: the sole writer may add rows and read them. It may not change one,
-- delete one, or empty the table. Named one privilege at a time rather than
-- `GRANT ALL` minus revokes, so the grant list IS the audit.
GRANT SELECT, INSERT ON plane1_event_log                TO nix_limiter;
GRANT SELECT, INSERT ON plane1_event_log_2026_08        TO nix_limiter;
GRANT SELECT, INSERT ON plane1_event_log_2026_09        TO nix_limiter;
GRANT SELECT, INSERT ON plane1_event_log_default        TO nix_limiter;
GRANT USAGE  ON SEQUENCE plane1_event_id_seq            TO nix_limiter;

GRANT SELECT ON plane1_event_log                        TO nix_reader;
GRANT SELECT ON plane1_event_log_2026_08                TO nix_reader;
GRANT SELECT ON plane1_event_log_2026_09                TO nix_reader;
GRANT SELECT ON plane1_event_log_default                TO nix_reader;

-- THE PROJECTION: derived, so the writer owns it completely. Rebuilding it
-- REQUIRES delete/truncate; withholding those would make §9's "rebuildable"
-- false.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON plane1_positions        TO nix_limiter;
GRANT SELECT, INSERT, UPDATE, DELETE           ON plane1_projection_meta  TO nix_limiter;
GRANT SELECT ON plane1_positions       TO nix_reader;
GRANT SELECT ON plane1_projection_meta TO nix_reader;

-- Future partitions. A monthly partition added next year by the owner would
-- otherwise carry no grant at all, and the Limiter would start failing to
-- insert on the first day of that month — a failure whose cause is a missing
-- GRANT six months earlier. Default privileges close the ordinary case; the
-- schema gate still checks EVERY partition individually, because a default
-- privilege is a rule about future objects and not a statement about existing
-- ones.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT ON TABLES TO nix_limiter;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO nix_reader;

COMMIT;
