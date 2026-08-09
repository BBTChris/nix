-- ============================================================================
-- Nix / Crucible — trades schema  (v2)
-- Full trade lifecycle records: backtest, paper, and live.
--
-- Design decisions applied:
--   * Two-level LIST partitioning: trade_source -> symbol
--   * Three source branches: backtest / paper / live (paper is its own branch)
--   * Backtest leaves: UNLOGGED, fillfactor=100, BRIN time indexes
--       (backtest rows are regenerable by design; UNLOGGED truncates on
--        crash recovery — acceptable ONLY for backtest)
--   * Paper/live leaves: WAL-logged, fillfactor=90, btree indexes,
--       updated_at maintained by trigger (rows mutate when exits land)
--   * runs table: every backtest trade belongs to a run (parameters,
--       fill-model version, MC seed, corpus id) — enforced by CHECK.
--       corpus_version_id / strategy_code_hash remain snapshotted per trade
--       so live rows (which have no run) still carry provenance.
--   * initial_stop_price / initial_risk_ticks stored so r_multiple is
--       auditable and MAE can be read relative to the stop
--   * broker_trade_id + partial unique index per execution branch:
--       ingestion is idempotent — replaying a broker feed cannot
--       double-record an execution
--   * Generated columns: holding_period_seconds, gross_pnl, net_pnl are
--       GENERATED ALWAYS ... STORED — inconsistency is structurally
--       impossible, not a code-review concern
--   * Role separation: nix_bt_writer / nix_paper_writer / nix_live_writer /
--       nix_reader. Engines write to their branch parent; privileges are
--       checked on the named table, so the backtest engine physically
--       cannot insert a live row
--   * Tick-denominated values as BIGINT; raw prices retained as NUMERIC
--   * tick_size NUMERIC(12,8) — exact for fractional-tick instruments
--       (ZB 1/32 = 0.03125, ZN 1/64); never float
--   * All market timestamps TIMESTAMPTZ; logic/display tz America/Chicago
--       (DST-aware; resolved CDT/CST abbreviation snapshotted per side)
--   * DEFAULT partitions per branch; check_default_partitions() reports
--       rows that landed there (= symbol skipped onboarding). Run nightly.
--   * One onboarding routine stamps all three branches per symbol
--
-- CONVENTION (deliberate, documented): one row = one round trip.
--   Scale-outs / partial exits live as legs in the fills table; exit_price
--   is the exit VWAP and exit_reason describes the leg that closed the
--   position. If per-leg analytics are ever gating, add a trade_legs table
--   rather than widening this one.
--
-- Validated against PostgreSQL 16.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Enums
-- ----------------------------------------------------------------------------

CREATE TYPE trade_source_enum AS ENUM ('backtest', 'paper', 'live');

CREATE TYPE trade_direction_enum AS ENUM ('long', 'short');

CREATE TYPE entry_status_enum AS ENUM (
    'filled',               -- entry fully filled
    'partial_then_aborted', -- partial fill, remainder aborted/cancelled
    'aborted_broker',       -- broker/exchange reject before any fill (paper/live only)
    'aborted_strategy',     -- cancelled by strategy or kill-switch before fill
    'expired'               -- time-in-force lapsed unfilled
);

CREATE TYPE exit_status_enum AS ENUM (
    'open',                 -- position open, exit not yet resolved
    'filled',
    'partial_then_aborted',
    'aborted_broker',       -- exit rejected with position OPEN: live risk event
    'aborted_strategy',
    'expired',
    'not_applicable'        -- entry never filled; no exit exists
);

CREATE TYPE exit_reason_enum AS ENUM (
    'stop_hit',
    'target_hit',
    'strategy_signal',
    'eod_flatten',
    'risk_kill',
    'manual',
    'unknown'
);

CREATE TYPE slippage_source_enum AS ENUM (
    'modeled',   -- produced by the fill model (backtest)
    'observed'   -- measured from real executions (paper/live)
);

-- ----------------------------------------------------------------------------
-- runs: one row per evaluation run. Same code + same corpus can be re-run
-- with different parameters / fill-model versions / seeds — run_id is the
-- only handle that uniquely identifies "the trades from this evaluation".
-- Superseded runs are deleted by run_id (FK cascades are deliberate).
-- ----------------------------------------------------------------------------

CREATE TABLE runs (
    run_id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    mc_seed             BIGINT,
    run_kind            trade_source_enum NOT NULL DEFAULT 'backtest',
    strategy_id         TEXT NOT NULL,
    strategy_code_hash  TEXT NOT NULL,
    corpus_version_id   TEXT,
    fill_model_version  TEXT,
    parameters          JSONB,
    notes               TEXT
);

CREATE INDEX runs_strategy ON runs (strategy_id, started_at);

-- ----------------------------------------------------------------------------
-- Parent table
-- Column order: fixed 8-byte -> fixed 4-byte -> 1-byte -> variable-length.
--
-- trade_id uses an explicit sequence DEFAULT rather than GENERATED ALWAYS AS
-- IDENTITY: on PG16, identity does not propagate to partitions, so direct
-- writes to branch parents (role separation) or leaves (bulk COPY) would
-- fail with a null trade_id. A plain DEFAULT is inherited by all partitions.
-- ----------------------------------------------------------------------------

CREATE SEQUENCE trades_trade_id_seq AS BIGINT;

CREATE TABLE trades (
    -- ---- fixed 8-byte ------------------------------------------------------
    trade_id                BIGINT NOT NULL DEFAULT nextval('trades_trade_id_seq'),
    run_id                  BIGINT REFERENCES runs (run_id) ON DELETE CASCADE,

    signal_timestamp        TIMESTAMPTZ,          -- market time (America/Chicago logic)
    entry_timestamp         TIMESTAMPTZ,
    exit_timestamp          TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),  -- system provenance
    updated_at              TIMESTAMPTZ,          -- trigger-maintained, paper/live only

    entry_price_ticks       BIGINT,               -- entry_price / tick_size
    exit_price_ticks        BIGINT,
    gross_pnl_ticks         BIGINT,               -- (exit-entry) ticks x direction x qty
    mfe_ticks               BIGINT,               -- max favorable excursion
    mae_ticks               BIGINT,               -- max adverse excursion
    slippage_entry_ticks    BIGINT,               -- vs reference/signal price
    slippage_exit_ticks     BIGINT,
    initial_risk_ticks      BIGINT,               -- stop-defined risk at entry;
                                                  -- makes r_multiple auditable and
                                                  -- MAE readable relative to stop

    entry_order_id          BIGINT,               -- -> orders table
    exit_order_id           BIGINT,

    holding_period_seconds  BIGINT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (exit_timestamp - entry_timestamp))::BIGINT
    ) STORED,

    -- ---- fixed 4-byte ------------------------------------------------------
    trade_source            trade_source_enum NOT NULL,
    direction               trade_direction_enum NOT NULL,
    entry_status            entry_status_enum NOT NULL,
    exit_status             exit_status_enum  NOT NULL DEFAULT 'open',
    exit_reason             exit_reason_enum,
    slippage_source         slippage_source_enum,

    entry_quantity          INTEGER,
    exit_quantity           INTEGER,
    renko_brick_size_ticks  INTEGER,              -- required when is_renko

    trading_session_date    DATE,                 -- CME session bucket; populated by
                                                  -- calendar infra (per-symbol session
                                                  -- boundaries). Nullable until then.

    -- ---- 1-byte ------------------------------------------------------------
    is_renko                BOOLEAN NOT NULL DEFAULT false,

    -- ---- variable-length ---------------------------------------------------
    symbol                  TEXT NOT NULL,        -- continuous symbol (partition key)
    contract_month          TEXT,                 -- physical contract traded (e.g. ESU6)
    strategy_id             TEXT NOT NULL,
    account_id              TEXT,
    broker_trade_id         TEXT,                 -- broker/exchange execution id;
                                                  -- idempotency key for paper/live
                                                  -- ingestion (unique per branch)

    tick_size               NUMERIC(12,8),        -- snapshot; exact fractional ticks
    tick_value              NUMERIC(12,4),        -- USD per tick, snapshot
    entry_price             NUMERIC(18,8),        -- raw price (broker reconciliation)
    exit_price              NUMERIC(18,8),        -- exit VWAP if scaled out
    initial_stop_price      NUMERIC(18,8),        -- stop at entry (audits initial_risk_ticks)
    commission_total        NUMERIC(12,4),
    exchange_fee_total      NUMERIC(12,4),

    gross_pnl               NUMERIC(18,4) GENERATED ALWAYS AS (
        gross_pnl_ticks * tick_value
    ) STORED,
    net_pnl                 NUMERIC(18,4) GENERATED ALWAYS AS (
        gross_pnl_ticks * tick_value
        - COALESCE(commission_total, 0) - COALESCE(exchange_fee_total, 0)
    ) STORED,

    r_multiple              NUMERIC(10,4),        -- net vs initial stop-defined risk

    entry_tz_abbrev         TEXT,                 -- resolved 'CDT'/'CST' at entry
    exit_tz_abbrev          TEXT,

    corpus_version_id       TEXT,                 -- per-trade snapshot (runs is
    strategy_code_hash      TEXT,                 --  authoritative for backtest)

    -- ---- keys & invariants -------------------------------------------------
    PRIMARY KEY (trade_id, trade_source, symbol),

    -- Every backtest trade belongs to a run
    CONSTRAINT trades_backtest_requires_run CHECK (
        trade_source <> 'backtest' OR run_id IS NOT NULL
    ),

    -- Broker aborts cannot exist in backtest (no broker in the loop)
    CONSTRAINT trades_no_broker_abort_in_backtest CHECK (
        trade_source <> 'backtest'
        OR (entry_status <> 'aborted_broker' AND exit_status <> 'aborted_broker')
    ),

    -- Renko trades must snapshot their brick size
    CONSTRAINT trades_renko_brick_required CHECK (
        NOT is_renko OR renko_brick_size_ticks IS NOT NULL
    ),

    -- Slippage origin discipline: backtest slippage is modeled, never observed
    CONSTRAINT trades_slippage_origin CHECK (
        slippage_source IS NULL
        OR (trade_source =  'backtest' AND slippage_source = 'modeled')
        OR (trade_source <> 'backtest' AND slippage_source = 'observed')
    ),

    -- If the entry never filled, there is no exit and no execution data
    CONSTRAINT trades_unfilled_entry_shape CHECK (
        entry_status IN ('filled', 'partial_then_aborted')
        OR (exit_status = 'not_applicable' AND entry_price IS NULL
            AND entry_price_ticks IS NULL AND gross_pnl_ticks IS NULL)
    ),

    -- If a stop was recorded, its tick-risk must be recorded too (and vice versa)
    CONSTRAINT trades_stop_pair CHECK (
        (initial_stop_price IS NULL) = (initial_risk_ticks IS NULL)
    )
) PARTITION BY LIST (trade_source);

ALTER SEQUENCE trades_trade_id_seq OWNED BY trades.trade_id;

-- ----------------------------------------------------------------------------
-- Source branches (level 1), each sub-partitioned by symbol (level 2)
-- ----------------------------------------------------------------------------

CREATE TABLE trades_backtest PARTITION OF trades
    FOR VALUES IN ('backtest')
    PARTITION BY LIST (symbol);

CREATE TABLE trades_paper PARTITION OF trades
    FOR VALUES IN ('paper')
    PARTITION BY LIST (symbol);

CREATE TABLE trades_live PARTITION OF trades
    FOR VALUES IN ('live')
    PARTITION BY LIST (symbol);

-- ----------------------------------------------------------------------------
-- Partitioned indexes (cascade to every current & future leaf)
--   backtest: BRIN — inserts arrive ~chronologically; tiny index, fast
--             time-range scans over millions of rows
--   paper/live: btree — small partitions, point/range lookups, open-trade scans
-- ----------------------------------------------------------------------------

CREATE INDEX trades_backtest_entry_ts_brin
    ON trades_backtest USING brin (entry_timestamp);
CREATE INDEX trades_backtest_session_brin
    ON trades_backtest USING brin (trading_session_date);
CREATE INDEX trades_backtest_strategy
    ON trades_backtest (strategy_id, entry_timestamp);
CREATE INDEX trades_backtest_run
    ON trades_backtest (run_id);

CREATE INDEX trades_paper_entry_ts  ON trades_paper (entry_timestamp);
CREATE INDEX trades_paper_session   ON trades_paper (trading_session_date);
CREATE INDEX trades_paper_strategy  ON trades_paper (strategy_id, entry_timestamp);
CREATE INDEX trades_paper_open      ON trades_paper (exit_status)
    WHERE exit_status = 'open';

CREATE INDEX trades_live_entry_ts   ON trades_live (entry_timestamp);
CREATE INDEX trades_live_session    ON trades_live (trading_session_date);
CREATE INDEX trades_live_strategy   ON trades_live (strategy_id, entry_timestamp);
CREATE INDEX trades_live_open       ON trades_live (exit_status)
    WHERE exit_status = 'open';

-- Idempotent ingestion: a broker execution id can be recorded at most once
-- per branch. (Unique indexes on partitioned tables must include the
-- partition key, hence symbol.) NULLs are permitted and unconstrained.
CREATE UNIQUE INDEX trades_paper_broker_id_uq
    ON trades_paper (symbol, broker_trade_id)
    WHERE broker_trade_id IS NOT NULL;
CREATE UNIQUE INDEX trades_live_broker_id_uq
    ON trades_live (symbol, broker_trade_id)
    WHERE broker_trade_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- updated_at trigger — execution branches only. Backtest rows are immutable
-- (fillfactor 100); no trigger there keeps that honest.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trades_paper_touch BEFORE UPDATE ON trades_paper
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trades_live_touch BEFORE UPDATE ON trades_live
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ----------------------------------------------------------------------------
-- Symbol onboarding: ONE routine stamps all three branches so they cannot
-- drift out of sync. Applies UNLOGGED + fillfactor=100 to the backtest leaf,
-- fillfactor=90 to paper/live leaves. Partitioned indexes attach automatically.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION create_symbol_partitions(p_symbol TEXT)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_suffix TEXT := lower(regexp_replace(p_symbol, '[^A-Za-z0-9]', '_', 'g'));
BEGIN
    -- backtest: UNLOGGED (regenerable), immutable rows -> fillfactor 100
    EXECUTE format(
        'CREATE UNLOGGED TABLE IF NOT EXISTS trades_backtest_%s
             PARTITION OF trades_backtest FOR VALUES IN (%L)
             WITH (fillfactor = 100)',
        v_suffix, p_symbol);

    -- paper: WAL-logged, updated in place -> fillfactor 90
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS trades_paper_%s
             PARTITION OF trades_paper FOR VALUES IN (%L)
             WITH (fillfactor = 90)',
        v_suffix, p_symbol);

    -- live: WAL-logged, updated in place -> fillfactor 90
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS trades_live_%s
             PARTITION OF trades_live FOR VALUES IN (%L)
             WITH (fillfactor = 90)',
        v_suffix, p_symbol);
END;
$$;

-- ----------------------------------------------------------------------------
-- Initial symbol set — extend at corpus-build onboarding time
-- ----------------------------------------------------------------------------

SELECT create_symbol_partitions('ES');
SELECT create_symbol_partitions('NQ');
SELECT create_symbol_partitions('CL');
SELECT create_symbol_partitions('GC');
SELECT create_symbol_partitions('ZB');   -- fractional-tick check: 1/32

-- ----------------------------------------------------------------------------
-- DEFAULT catch-alls + nightly check.
-- A row landing in a DEFAULT partition means a symbol skipped onboarding.
-- ----------------------------------------------------------------------------

CREATE UNLOGGED TABLE trades_backtest_default PARTITION OF trades_backtest DEFAULT;
CREATE          TABLE trades_paper_default    PARTITION OF trades_paper    DEFAULT;
CREATE          TABLE trades_live_default     PARTITION OF trades_live     DEFAULT;

-- Run nightly; any row returned = a symbol needs create_symbol_partitions().
CREATE OR REPLACE FUNCTION check_default_partitions()
RETURNS TABLE (leaf TEXT, symbol TEXT, row_count BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT 'trades_backtest_default', t.symbol, count(*)
      FROM trades_backtest_default t GROUP BY t.symbol
    UNION ALL
    SELECT 'trades_paper_default', t.symbol, count(*)
      FROM trades_paper_default t GROUP BY t.symbol
    UNION ALL
    SELECT 'trades_live_default', t.symbol, count(*)
      FROM trades_live_default t GROUP BY t.symbol;
$$;

-- ----------------------------------------------------------------------------
-- Role separation. Privileges are checked on the table NAMED in the query,
-- so each engine writes to its branch parent and physically cannot touch
-- another branch. Backtest rows are immutable: no UPDATE grant; DELETE is
-- granted for superseding runs (normally via runs FK cascade).
-- ----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nix_bt_writer') THEN
        CREATE ROLE nix_bt_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nix_paper_writer') THEN
        CREATE ROLE nix_paper_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nix_live_writer') THEN
        CREATE ROLE nix_live_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nix_reader') THEN
        CREATE ROLE nix_reader NOLOGIN;
    END IF;
END;
$$;

GRANT SELECT, INSERT, DELETE          ON trades_backtest TO nix_bt_writer;
GRANT SELECT, INSERT, UPDATE, DELETE  ON runs            TO nix_bt_writer;
-- Needed for currval()/lastval() on the runs identity sequence.
-- (Prefer INSERT ... RETURNING run_id, which needs no sequence privilege.)
GRANT USAGE, SELECT ON SEQUENCE runs_run_id_seq TO nix_bt_writer;

GRANT SELECT, INSERT, UPDATE          ON trades_paper    TO nix_paper_writer;
GRANT SELECT                          ON runs            TO nix_paper_writer;

GRANT SELECT, INSERT, UPDATE          ON trades_live     TO nix_live_writer;
GRANT SELECT                          ON runs            TO nix_live_writer;

GRANT SELECT ON trades, runs TO nix_reader;

-- All writers need the trade_id sequence for direct branch/leaf writes
GRANT USAGE ON SEQUENCE trades_trade_id_seq
    TO nix_bt_writer, nix_paper_writer, nix_live_writer;

COMMIT;

-- ============================================================================
-- Operational notes (not executed)
--
-- Bulk loads (Gate 5 runs):
--   COPY directly into the target leaf (e.g. trades_backtest_es) to skip
--   partition routing, then ANALYZE the leaf — autovacuum lags bulk loads.
--   Note: generated columns are computed on COPY too; do not include them
--   in the column list.
--
-- Superseding a run:
--   DELETE FROM runs WHERE run_id = ...;  -- trades cascade via FK
--
-- Partition pruning:
--   Queries must carry trade_source and symbol as literals or stable params
--   in WHERE, or Postgres scans every leaf. Make this a query-layer convention.
--
-- Timezone:
--   ALTER ROLE nix_app SET timezone = 'America/Chicago';
--   TIMESTAMPTZ then renders in CME time (CDT/CST auto-resolved) everywhere.
--
-- Roles:
--   Grant the writer roles to the actual login users of each engine, e.g.
--   GRANT nix_bt_writer TO crucible_engine;
--
-- UNLOGGED caveat (deliberate):
--   Backtest leaves truncate on crash recovery and are not replicated.
--   Acceptable because backtest output is regenerable from corpus + run
--   provenance. If that ever stops being true: ALTER TABLE ... SET LOGGED.
-- ============================================================================

