<!-- nix_db_schema_spec.md — reconstructed with fenced filename= blocks from the source .docx paragraphs, verbatim content, no edits -->

```python filename=extract_sources.py
#!/usr/bin/env python3
"""Extract every filename=-tagged fenced block from the spec into files."""
import re, os, sys

spec_path = sys.argv[1] if len(sys.argv) > 1 else "nix_db_schema_spec.md"
spec = open(spec_path).read()
for m in re.finditer(r"^``[`]\w+ filename=(\S+)\n(.*?)\n``[`]$", spec,
                     re.S | re.M):
    name, body = m.group(1), m.group(2) + "\n"
    open(name, "w").write(body)
    if name.endswith(".sh"):
        os.chmod(name, 0o755)
    print("extracted", name)

```

```sql filename=trade_history.sql
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

```

```sql filename=symbol_base_bar_history.sql
-- ============================================================================
-- <symbol>_base_bar_history.sql  (v3 — 3-file split, shared base)
--
-- SHARED infrastructure every bar-history database needs, regardless of which
-- representations (renko / m1) it stores. Applied FIRST by
-- provision_symbol_bar_history.sh, before the per-representation files:
--     psql -d es_bar_history -v symbol=ES -v tick_size=0.25 \
--          -v series_kind=continuous_backadjusted -f <symbol>_base_bar_history.sql
--
-- Contains: bar_meta (singleton), ingest_batches, price<->tick conversion
-- helpers, and the cluster-wide nix_bar_writer / nix_bar_reader roles.
-- renko_bricks and candles_m1 both depend on bar_meta + ingest_batches, so
-- these live in one shared file rather than being duplicated per representation
-- (duplication is exactly the drift the regression harness exists to catch).
--
-- (Full audit rationale P1-P4, C1-C4 preserved in spec section 4.)
--
-- Timestamp conventions (still ASSUMED — confirm vs Titan candles_1s):
--   candles_m1.bar_timestamp     = bar OPEN time (start of minute)
--   renko_bricks.brick_timestamp = brick COMPLETION time
-- ============================================================================

\if :{?symbol}
\else
\echo 'ERROR: run with -v symbol=<SYM> -v tick_size=<size> -v series_kind=<kind>'
\quit
\endif

BEGIN;

-- Per-database metadata (single row). tick_size here is what makes integer
-- tick storage work and what the price views/conversion functions read.
-- ----------------------------------------------------------------------------

CREATE TABLE bar_meta (
    symbol          TEXT NOT NULL PRIMARY KEY,
    tick_size       NUMERIC(12,8) NOT NULL CHECK (tick_size > 0),
    -- What kind of price series this database stores. 'unspecified' is a
    -- provisioning placeholder that corpus QA should treat as a finding —
    -- backtest math differs between back-adjusted and raw series, so this
    -- must be resolved before the corpus is trusted.
    series_kind     TEXT NOT NULL DEFAULT 'unspecified' CHECK (series_kind IN (
                        'unspecified',
                        'contract_month',           -- raw per-contract series
                        'continuous_unadjusted',    -- stitched, no adjustment
                        'continuous_backadjusted',  -- subtraction-adjusted
                        'continuous_ratio_adjusted'
                    )),
    roll_convention TEXT,                            -- free-text pointer to the
                                                     -- roll rule used, if any
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes           TEXT
);

INSERT INTO bar_meta (symbol, tick_size, series_kind)
VALUES (:'symbol', :tick_size, :'series_kind');

-- Exactly one meta row, ever
CREATE UNIQUE INDEX bar_meta_singleton ON bar_meta ((true));

-- ----------------------------------------------------------------------------
-- Ingest provenance: one row per ingest batch; every bar row points at one.
-- ----------------------------------------------------------------------------

CREATE TABLE ingest_batches (
    batch_id     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    source       TEXT NOT NULL,        -- vendor / feed / file identifier
    source_hash  TEXT,                 -- file or payload hash for corpus QA
    row_count    BIGINT,
    notes        TEXT
);

-- ----------------------------------------------------------------------------
-- Conversion helpers. price_to_ticks REJECTS prices that don't land on a
-- tick boundary — bad vendor data fails at ingest instead of being stored.
-- ----------------------------------------------------------------------------

CREATE FUNCTION price_to_ticks(p_price NUMERIC)
RETURNS INTEGER LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_ts NUMERIC;
    v    NUMERIC;
BEGIN
    SELECT tick_size INTO STRICT v_ts FROM bar_meta;
    v := p_price / v_ts;
    IF v <> round(v) THEN
        RAISE EXCEPTION 'price % is not aligned to tick_size % (=% ticks)',
            p_price, v_ts, v;
    END IF;
    RETURN round(v)::INTEGER;
END;
$$;

CREATE FUNCTION ticks_to_price(p_ticks INTEGER)
RETURNS NUMERIC LANGUAGE sql STABLE AS $$
    SELECT p_ticks * tick_size FROM bar_meta;
$$;

-- ----------------------------------------------------------------------------
-- Roles (cluster-wide, idempotent). Created here in the base so the
-- per-representation files can GRANT against them unconditionally.
-- ----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nix_bar_writer') THEN
        CREATE ROLE nix_bar_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nix_bar_reader') THEN
        CREATE ROLE nix_bar_reader NOLOGIN;
    END IF;
END;
$$;

-- Base-object grants. Representation tables/views grant themselves in their
-- own files.
GRANT SELECT, INSERT ON ingest_batches TO nix_bar_writer;
GRANT SELECT         ON bar_meta        TO nix_bar_writer;
GRANT USAGE, SELECT ON SEQUENCE ingest_batches_batch_id_seq TO nix_bar_writer;
GRANT SELECT ON ingest_batches, bar_meta TO nix_bar_reader;

COMMIT;

```

```sql filename=symbol_renko_bar_history.sql
-- ============================================================================
-- <symbol>_renko_bar_history.sql  (v3 — 3-file split, renko representation)
--
-- Renko-brick storage for one symbol. Applied AFTER the base file (it depends
-- on bar_meta, ingest_batches, and the nix_bar_* roles created there):
--     psql -d es_bar_history -f <symbol>_renko_bar_history.sql
-- provision_symbol_bar_history.sh stamps the extracted artifact per symbol,
-- e.g. es_renko_bar_history.sql, zb_renko_bar_history.sql.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- renko_bricks — ANY brick size shares this one table (brick_size_ticks is
-- part of the natural key: two size-streams can complete bricks at the same
-- instant). Fully fixed-width rows: one 8-byte column, then seven 4-byte
-- columns, no varlena — the fastest layout Postgres can scan.
-- ----------------------------------------------------------------------------

CREATE TABLE renko_bricks (
    -- ---- fixed 8-byte ------------------------------------------------------
    brick_timestamp       TIMESTAMPTZ(6) NOT NULL,   -- brick COMPLETION time
    -- ---- fixed 4-byte ------------------------------------------------------
    trading_session_date  DATE,                      -- CME session bucket; NULL
                                                     -- until calendar infra
    brick_size_ticks      INTEGER NOT NULL,
    ingest_batch_id       INTEGER NOT NULL REFERENCES ingest_batches (batch_id)
                              ON DELETE CASCADE,  -- delete-by-batch correction:
                                                  -- removing a bad batch removes
                                                  -- exactly its rows, nothing else
    open_ticks            INTEGER NOT NULL,
    high_ticks            INTEGER NOT NULL,
    low_ticks             INTEGER NOT NULL,
    close_ticks           INTEGER NOT NULL,
    volume                INTEGER,                   -- contracts; NULL if feed
                                                     -- doesn't supply it
    -- ---- 1-byte ------------------------------------------------------------
    is_reversal           BOOLEAN,                   -- stamped by the brick
                                                     -- generator; NULL = unknown.
                                                     -- Lets continuity QA treat
                                                     -- reversal-offset opens as
                                                     -- expected, per convention.

    PRIMARY KEY (brick_size_ticks, brick_timestamp),

    CONSTRAINT renko_bricks_size_positive CHECK (brick_size_ticks > 0),
    CONSTRAINT renko_bricks_volume_nonneg CHECK (volume IS NULL OR volume >= 0),
    CONSTRAINT renko_bricks_high_is_max CHECK (
        high_ticks >= open_ticks AND high_ticks >= close_ticks
        AND high_ticks >= low_ticks
    ),
    CONSTRAINT renko_bricks_low_is_min CHECK (
        low_ticks <= open_ticks AND low_ticks <= close_ticks
        AND low_ticks <= high_ticks
    )
) WITH (fillfactor = 100);

CREATE INDEX renko_bricks_session ON renko_bricks (trading_session_date);
CREATE INDEX renko_bricks_batch   ON renko_bricks (ingest_batch_id);

CREATE VIEW renko_bricks_prices AS
SELECT m.symbol,
       b.brick_timestamp,
       b.trading_session_date,
       b.brick_size_ticks,
       b.open_ticks  * m.tick_size AS open_price,
       b.high_ticks  * m.tick_size AS high_price,
       b.low_ticks   * m.tick_size AS low_price,
       b.close_ticks * m.tick_size AS close_price,
       b.volume,
       b.is_reversal,
       b.ingest_batch_id
FROM renko_bricks b CROSS JOIN bar_meta m;

-- ----------------------------------------------------------------------------
-- Renko corpus-QA helper
-- ----------------------------------------------------------------------------

-- Bricks whose open != previous close within one brick-size stream.
-- delta_ticks of exactly +/- brick size may be a legitimate reversal
-- depending on the generator's convention — QA judges; this reports.
CREATE FUNCTION check_renko_continuity(p_size INTEGER)
RETURNS TABLE (brick_timestamp TIMESTAMPTZ, prev_close_ticks INTEGER,
               open_ticks INTEGER, delta_ticks INTEGER, is_reversal BOOLEAN)
LANGUAGE sql STABLE AS $$
    SELECT brick_timestamp, prev_close, open_ticks,
           open_ticks - prev_close, is_reversal
    FROM (
        SELECT brick_timestamp, open_ticks, is_reversal,
               lag(close_ticks) OVER (ORDER BY brick_timestamp) AS prev_close
        FROM renko_bricks
        WHERE brick_size_ticks = p_size
    ) s
    WHERE prev_close IS NOT NULL AND open_ticks <> prev_close;
$$;

-- Grants for the renko objects (roles created in the base file).
GRANT SELECT, INSERT, DELETE ON renko_bricks        TO nix_bar_writer;
GRANT SELECT                 ON renko_bricks_prices  TO nix_bar_writer;
GRANT SELECT ON renko_bricks, renko_bricks_prices    TO nix_bar_reader;

COMMIT;

```

```sql filename=symbol_m1_bar_history.sql
-- ============================================================================
-- <symbol>_m1_bar_history.sql  (v3 — 3-file split, 1-minute representation)
--
-- 1-minute OHLC candle storage for one symbol. Applied AFTER the base file
-- (depends on bar_meta, ingest_batches, and the nix_bar_* roles):
--     psql -d es_bar_history -f <symbol>_m1_bar_history.sql
-- provision_symbol_bar_history.sh stamps the artifact per symbol,
-- e.g. es_m1_bar_history.sql, zb_m1_bar_history.sql.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- candles_m1 — one 1-minute OHLC candle per minute; bar_timestamp is the
-- natural PK. Same fixed-width layout.
-- ----------------------------------------------------------------------------

CREATE TABLE candles_m1 (
    -- ---- fixed 8-byte ------------------------------------------------------
    bar_timestamp         TIMESTAMPTZ(6) NOT NULL PRIMARY KEY,  -- bar OPEN time
    -- ---- fixed 4-byte ------------------------------------------------------
    trading_session_date  DATE,
    ingest_batch_id       INTEGER NOT NULL REFERENCES ingest_batches (batch_id)
                              ON DELETE CASCADE,  -- delete-by-batch correction:
                                                  -- removing a bad batch removes
                                                  -- exactly its rows, nothing else
    open_ticks            INTEGER NOT NULL,
    high_ticks            INTEGER NOT NULL,
    low_ticks             INTEGER NOT NULL,
    close_ticks           INTEGER NOT NULL,
    volume                INTEGER,

    CONSTRAINT candles_m1_minute_aligned CHECK (
        EXTRACT(SECOND FROM bar_timestamp) = 0
    ),
    CONSTRAINT candles_m1_volume_nonneg CHECK (volume IS NULL OR volume >= 0),
    CONSTRAINT candles_m1_high_is_max CHECK (
        high_ticks >= open_ticks AND high_ticks >= close_ticks
        AND high_ticks >= low_ticks
    ),
    CONSTRAINT candles_m1_low_is_min CHECK (
        low_ticks <= open_ticks AND low_ticks <= close_ticks
        AND low_ticks <= high_ticks
    )
) WITH (fillfactor = 100);

CREATE INDEX candles_m1_session ON candles_m1 (trading_session_date);
CREATE INDEX candles_m1_batch   ON candles_m1 (ingest_batch_id);

CREATE VIEW candles_m1_prices AS
SELECT m.symbol,
       c.bar_timestamp,
       c.trading_session_date,
       c.open_ticks  * m.tick_size AS open_price,
       c.high_ticks  * m.tick_size AS high_price,
       c.low_ticks   * m.tick_size AS low_price,
       c.close_ticks * m.tick_size AS close_price,
       c.volume,
       c.ingest_batch_id
FROM candles_m1 c CROSS JOIN bar_meta m;

-- ----------------------------------------------------------------------------
-- M1 corpus-QA helper
-- ----------------------------------------------------------------------------

-- Missing minutes between consecutive candles. Until calendar infrastructure
-- can whitelist session breaks and holidays, legitimate closures will appear
-- here too — treat output as candidates, not verdicts.
CREATE FUNCTION find_candle_gaps(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE (gap_after TIMESTAMPTZ, gap_before TIMESTAMPTZ, missing_minutes BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT bar_timestamp,
           next_ts,
           (EXTRACT(EPOCH FROM (next_ts - bar_timestamp)) / 60)::BIGINT - 1
    FROM (
        SELECT bar_timestamp,
               lead(bar_timestamp) OVER (ORDER BY bar_timestamp) AS next_ts
        FROM candles_m1
        WHERE bar_timestamp BETWEEN p_from AND p_to
    ) s
    WHERE next_ts - bar_timestamp > interval '1 minute';
$$;

-- Grants for the m1 objects (roles created in the base file).
GRANT SELECT, INSERT, DELETE ON candles_m1        TO nix_bar_writer;
GRANT SELECT                 ON candles_m1_prices  TO nix_bar_writer;
GRANT SELECT ON candles_m1, candles_m1_prices      TO nix_bar_reader;

COMMIT;

-- ============================================================================
-- Operational notes (not executed) — apply to both representations
-- ============================================================================
-- Operational notes (not executed)
--
-- Fast ingest path (preferred): convert to ticks upstream, COPY directly
--   into the base table with an ingest_batch_id, then ANALYZE.
--
-- Validated ingest path: INSERT ... SELECT price_to_ticks(open_px), ...
--   — slower, but rejects any price not on a tick boundary.
--
-- Bulk backfill recipe (temporary, reversible WAL skip):
--   ALTER TABLE candles_m1 SET UNLOGGED;
--   COPY ...;
--   ALTER TABLE candles_m1 SET LOGGED;    -- rewrites + WALs once
--   VACUUM ANALYZE candles_m1;            -- sets visibility map ->
--                                         -- enables index-only scans on PK
--
-- Correction workflow:
--   DELETE FROM <table> WHERE ingest_batch_id = <bad>; re-ingest new batch.
--
-- Timezone: ALTER ROLE ... SET timezone = 'America/Chicago' as with
--   trade_history.
-- ============================================================================

```

```sql filename=symbol_bar_history_hub.sql
-- ============================================================================
-- symbol_bar_history_hub.sql — cross-database bar access, applied ONCE to
-- trade_history.
--
-- Resolves the "cross-database queries don't exist natively" gap: one
-- physical database per symbol means no plain JOIN can span symbols. This
-- hub uses postgres_fdw to project every <symbol>_bar_history database's
-- price views into trade_history under schema "bars", with union views on
-- top — so Gate 5/6 analysis can JOIN trades against bars of ANY symbol
-- from the one database where trades already live.
--
--   bars.registry            — which symbols are wired in
--   bars.register_symbol(s)  — wires one symbol: server + user mapping +
--                              foreign tables + rebuilds the union views.
--                              Called automatically by
--                              provision_symbol_bar_history.sh.
--   bars.all_candles_m1      — every symbol's M1 candles, decimal prices,
--   bars.all_renko_bricks      symbol column included (the per-symbol
--                              *_prices views already project it)
--
-- Connection model: local socket, same cluster. The user mapping created
-- here is FOR CURRENT_USER (the DBA applying this file). PRODUCTION NOTE:
-- other roles need their own user mappings (and non-superuser mappings
-- normally require a password in the mapping options) — deliberately NOT
-- created broadly here; a FOR PUBLIC mapping impersonating a superuser
-- would be a privilege-escalation hole.
-- ============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SCHEMA IF NOT EXISTS bars;

CREATE TABLE IF NOT EXISTS bars.registry (
    symbol        TEXT PRIMARY KEY,
    dbname        TEXT NOT NULL,
    server_name   TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- Rebuild the union views from whatever is currently registered.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION bars.rebuild_union_views()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_candles TEXT := '';
    v_bricks  TEXT := '';
    r RECORD;
BEGIN
    FOR r IN SELECT symbol FROM bars.registry ORDER BY symbol LOOP
        IF v_candles <> '' THEN
            v_candles := v_candles || ' UNION ALL ';
            v_bricks  := v_bricks  || ' UNION ALL ';
        END IF;
        v_candles := v_candles || format('SELECT * FROM bars.%I',
                        lower(regexp_replace(r.symbol,'[^A-Za-z0-9]','_','g'))
                        || '_candles_m1');
        v_bricks  := v_bricks  || format('SELECT * FROM bars.%I',
                        lower(regexp_replace(r.symbol,'[^A-Za-z0-9]','_','g'))
                        || '_renko_bricks');
    END LOOP;

    IF v_candles = '' THEN
        RAISE NOTICE 'bars.registry is empty; union views not (re)built';
        RETURN;
    END IF;

    EXECUTE 'CREATE OR REPLACE VIEW bars.all_candles_m1 AS ' || v_candles;
    EXECUTE 'CREATE OR REPLACE VIEW bars.all_renko_bricks AS ' || v_bricks;
END;
$$;

-- ----------------------------------------------------------------------------
-- Register one symbol's bar-history database into the hub. Idempotent:
-- re-running refreshes the foreign tables (schema changes upstream get
-- picked up by re-registering).
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION bars.register_symbol(p_symbol TEXT)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_suffix TEXT := lower(regexp_replace(p_symbol,'[^A-Za-z0-9]','_','g'));
    v_db     TEXT := v_suffix || '_bar_history';
    v_srv    TEXT := 'bar_' || v_suffix;
BEGIN
    EXECUTE format(
        'CREATE SERVER IF NOT EXISTS %I FOREIGN DATA WRAPPER postgres_fdw
         OPTIONS (dbname %L)', v_srv, v_db);
    EXECUTE format(
        'CREATE USER MAPPING IF NOT EXISTS FOR CURRENT_USER SERVER %I',
        v_srv);

    -- union views depend on the foreign tables; drop first, rebuilt below
    DROP VIEW IF EXISTS bars.all_candles_m1;
    DROP VIEW IF EXISTS bars.all_renko_bricks;

    EXECUTE format('DROP FOREIGN TABLE IF EXISTS bars.%I',
                   v_suffix || '_candles_m1');
    EXECUTE format($ft$
        CREATE FOREIGN TABLE bars.%I (
            symbol               TEXT,
            bar_timestamp        TIMESTAMPTZ,
            trading_session_date DATE,
            open_price           NUMERIC,
            high_price           NUMERIC,
            low_price            NUMERIC,
            close_price          NUMERIC,
            volume               INTEGER,
            ingest_batch_id      INTEGER
        ) SERVER %I OPTIONS (schema_name 'public', table_name 'candles_m1_prices')
    $ft$, v_suffix || '_candles_m1', v_srv);

    EXECUTE format('DROP FOREIGN TABLE IF EXISTS bars.%I',
                   v_suffix || '_renko_bricks');
    EXECUTE format($ft$
        CREATE FOREIGN TABLE bars.%I (
            symbol               TEXT,
            brick_timestamp      TIMESTAMPTZ,
            trading_session_date DATE,
            brick_size_ticks     INTEGER,
            open_price           NUMERIC,
            high_price           NUMERIC,
            low_price            NUMERIC,
            close_price          NUMERIC,
            volume               INTEGER,
            is_reversal          BOOLEAN,
            ingest_batch_id      INTEGER
        ) SERVER %I OPTIONS (schema_name 'public', table_name 'renko_bricks_prices')
    $ft$, v_suffix || '_renko_bricks', v_srv);

    INSERT INTO bars.registry (symbol, dbname, server_name)
    VALUES (upper(p_symbol), v_db, v_srv)
    ON CONFLICT (symbol) DO UPDATE
        SET dbname = EXCLUDED.dbname, server_name = EXCLUDED.server_name;

    PERFORM bars.rebuild_union_views();
END;
$$;

COMMIT;

-- ============================================================================
-- Operational notes (not executed)
--
-- Register a symbol manually:   SELECT bars.register_symbol('ES');
--   (provision_symbol_bar_history.sh does this automatically when the hub
--    schema exists in trade_history)
--
-- Gate-5-style cross-database join, all from trade_history:
--   SELECT t.trade_id, t.symbol, c.close_price
--   FROM trades t
--   JOIN bars.all_candles_m1 c
--     ON c.symbol = t.symbol
--    AND c.bar_timestamp = date_trunc('minute', t.entry_timestamp);
--
-- Performance: postgres_fdw pushes down WHERE clauses on symbol/timestamp
-- to the remote database, so filtered queries stay cheap. For heavy
-- corpus-wide scans, prefer filtering the union view by symbol (prunes to
-- one foreign server) or query the per-symbol foreign table directly.
--
-- Reader access: grant per role and create that role's user mapping:
--   GRANT USAGE ON SCHEMA bars TO nix_reader;
--   GRANT SELECT ON ALL TABLES IN SCHEMA bars TO nix_reader;
--   CREATE USER MAPPING FOR nix_reader SERVER bar_es OPTIONS (...);
-- ============================================================================

```

```bash filename=provision_symbol_bar_history.sh
#!/usr/bin/env bash
# Provision a per-symbol bar-history database: <symbol>_bar_history   (v3)
#
# Usage: ./provision_symbol_bar_history.sh ES 0.25 continuous_backadjusted
#        ./provision_symbol_bar_history.sh ZB 0.03125 continuous_backadjusted
#        ./provision_symbol_bar_history.sh 6E 0.00005
#
# v3: the bar schema is split into three ordered files
#       symbol_base_bar_history.sql   (bar_meta, ingest_batches, helpers, roles)
#       symbol_renko_bar_history.sql  (renko_bricks + view + QA)
#       symbol_m1_bar_history.sql     (candles_m1 + view + QA)
# applied base -> renko -> m1 (renko and m1 both depend on the base). For
# provenance, each is stamped to a per-symbol/per-representation artifact
# name before it is applied, e.g. es_base_bar_history.sql,
# es_renko_bar_history.sql, es_m1_bar_history.sql.

set -euo pipefail

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo "Usage: $0 <SYMBOL> <TICK_SIZE> [SERIES_KIND]" >&2
    echo "  e.g. $0 ES 0.25 continuous_backadjusted" >&2
    echo "  SERIES_KIND: contract_month | continuous_unadjusted |" >&2
    echo "               continuous_backadjusted | continuous_ratio_adjusted" >&2
    echo "  (defaults to 'unspecified' — corpus QA will flag it)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYMBOL_UPPER=$(echo "$1" | tr '[:lower:]' '[:upper:]')
DB_SUFFIX=$(echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g')
DB_NAME="${DB_SUFFIX}_bar_history"
TICK_SIZE="$2"
SERIES_KIND="${3:-unspecified}"
TRADE_DB="${TRADE_DB:-trade_history}"

# Per-symbol stamped artifacts (provenance of exactly what was applied)
STAMP_DIR="${STAMP_DIR:-${SCRIPT_DIR}}"
BASE_SRC="${SCRIPT_DIR}/symbol_base_bar_history.sql"
RENKO_SRC="${SCRIPT_DIR}/symbol_renko_bar_history.sql"
M1_SRC="${SCRIPT_DIR}/symbol_m1_bar_history.sql"
BASE_STAMP="${STAMP_DIR}/${DB_SUFFIX}_base_bar_history.sql"
RENKO_STAMP="${STAMP_DIR}/${DB_SUFFIX}_renko_bar_history.sql"
M1_STAMP="${STAMP_DIR}/${DB_SUFFIX}_m1_bar_history.sql"

# tick_size must be a positive decimal number
if ! echo "${TICK_SIZE}" | grep -Eq '^[0-9]*\.?[0-9]+$'; then
    echo "ERROR: tick_size '${TICK_SIZE}' is not a valid decimal" >&2
    exit 1
fi

# require all three source files
for f in "${BASE_SRC}" "${RENKO_SRC}" "${M1_SRC}"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing source file $f (run extract_sources.py first)" >&2
        exit 1
    fi
done

# refuse to clobber an existing database
if psql -lqt | cut -d'|' -f1 | grep -qw "${DB_NAME}"; then
    echo "ERROR: database ${DB_NAME} already exists — refusing to overwrite." >&2
    echo "       Drop it explicitly first if re-provisioning is intended." >&2
    exit 1
fi

echo "Provisioning ${DB_NAME} for ${SYMBOL_UPPER} (tick_size=${TICK_SIZE}, series=${SERIES_KIND})..."

# Stamp per-symbol artifacts with a provenance header, byte-identical DDL below.
stamp() {  # $1=src  $2=dest  $3=representation-label
    { echo "-- STAMPED ARTIFACT: ${SYMBOL_UPPER} ${3} — generated by provision_symbol_bar_history.sh";
      echo "-- source: $(basename "$1")";
      cat "$1"; } > "$2"
}
stamp "${BASE_SRC}"  "${BASE_STAMP}"  base
stamp "${RENKO_SRC}" "${RENKO_STAMP}" renko
stamp "${M1_SRC}"    "${M1_STAMP}"    m1

createdb "${DB_NAME}"

# Apply base -> renko -> m1 in order; base carries the psql -v variables.
if ! psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 \
     -v symbol="${SYMBOL_UPPER}" -v tick_size="${TICK_SIZE}" \
     -v series_kind="${SERIES_KIND}" \
     -f "${BASE_STAMP}"; then
    echo "ERROR: base schema failed — removing empty ${DB_NAME}" >&2
    dropdb "${DB_NAME}"; exit 1
fi
for step in "${RENKO_STAMP}" "${M1_STAMP}"; do
    if ! psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 -f "${step}"; then
        echo "ERROR: $(basename "${step}") failed — removing ${DB_NAME}" >&2
        dropdb "${DB_NAME}"; exit 1
    fi
done

# Auto-register into the FDW hub if it exists in ${TRADE_DB}
if [ "$(psql -d "${TRADE_DB}" -tAc \
        "SELECT 1 FROM pg_namespace WHERE nspname='bars'" 2>/dev/null)" = "1" ]; then
    psql -d "${TRADE_DB}" -v ON_ERROR_STOP=1 \
         -c "SELECT bars.register_symbol('${SYMBOL_UPPER}')" > /dev/null
    echo "Registered ${SYMBOL_UPPER} in ${TRADE_DB} bars hub."
fi

echo "Done: ${DB_NAME} (base + renko + m1; stamped ${DB_SUFFIX}_{base,renko,m1}_bar_history.sql)"

```

```bash filename=validate_schemas.sh
#!/usr/bin/env bash
# ============================================================================
# validate_schemas.sh — runnable regression harness for the Nix/Crucible
# storage layer. This is the executable form of spec §7: every check here
# is a fence that must pass before a schema change ships.
#
# Sandbox model: builds a fully scratch environment (vtest_trade_history +
# vt*_bar_history symbol databases), runs the battery, drops everything.
# Never touches production databases. Roles (nix_*) are cluster-global and
# idempotent in the DDL, so pre-existing roles are fine.
#
# Usage:  validate_schemas.sh [--keep]
#   --keep   leave the scratch databases in place for inspection
#
# Exit: 0 if every check passed, 1 otherwise. Requires: psql/createdb/dropdb
# on PATH with superuser access, python3, and nix_db_schema_spec.md in the
# same directory (the spec is the source of truth; check A extracts any
# missing source files from it and fails on drift in existing ones).
# ============================================================================
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1

VDB="vtest_trade_history"
SYMS_DBS="vt1_bar_history vt2_bar_history vt3_bar_history"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $1"; }

# expect_ok  <label> <db> <sql>   — statement must succeed
expect_ok() {
    if psql -d "$2" -v ON_ERROR_STOP=1 -qAt -c "$3" >/dev/null 2>&1
    then ok "$1"; else bad "$1 (expected success)"; fi
}
# expect_err <label> <db> <sql>   — statement must be rejected
expect_err() {
    if psql -d "$2" -v ON_ERROR_STOP=1 -qAt -c "$3" >/dev/null 2>&1
    then bad "$1 (expected rejection, but succeeded)"; else ok "$1"; fi
}
# expect_val <label> <db> <sql> <expected>  — scalar query must equal value
expect_val() {
    local got; got=$(psql -d "$2" -qAt -c "$3" 2>/dev/null)
    if [ "$got" = "$4" ]; then ok "$1"
    else bad "$1 (expected '$4', got '$got')"; fi
}

teardown() {
    for db in $VDB $SYMS_DBS; do dropdb --if-exists "$db" 2>/dev/null; done
}

echo "=== A. Spec integrity (single-file model: spec is the source of truth) ==="
if python3 - "$SCRIPT_DIR" << 'PY'
import sys, re, os
d = sys.argv[1]
spec = open(f"{d}/nix_db_schema_spec.md").read()
blocks = re.findall(r"^``[`]\w+ filename=(\S+)\n(.*?)\n``[`]$",
                    spec, re.S | re.M)
required = {"trade_history.sql", "symbol_base_bar_history.sql",
            "symbol_renko_bar_history.sql", "symbol_m1_bar_history.sql",
            "symbol_bar_history_hub.sql", "provision_symbol_bar_history.sh",
            "validate_schemas.sh"}
names = {n for n, _ in blocks}
missing_blocks = required - names
if missing_blocks:
    print(f"spec is missing tagged blocks: {sorted(missing_blocks)}")
    sys.exit(1)
rc = 0
for name, body in blocks:
    path = f"{d}/{name}"
    if not os.path.exists(path):
        open(path, "w").write(body + "\n")
        if name.endswith(".sh"):
            os.chmod(path, 0o755)
        print(f"  (extracted missing {name} from spec)")
    elif open(path).read().rstrip("\n") != body.rstrip("\n"):
        print(f"DRIFT: {name} on disk differs from its spec block — "
              f"fold the change back into the spec or re-extract")
        rc = 1
sys.exit(rc)
PY
then ok "spec blocks and extracted files agree"
else bad "spec integrity failure"; fi

echo "=== B. trade_history schema (scratch: $VDB) ==="
teardown
createdb "$VDB" || { bad "createdb $VDB"; exit 1; }
if psql -d "$VDB" -v ON_ERROR_STOP=1 -q -f "$SCRIPT_DIR/trade_history.sql" >/dev/null 2>&1
then ok "trades DDL applies clean"; else bad "trades DDL failed to apply"; teardown; exit 1; fi

expect_ok  "B1 symbol onboarding (all three branches)"          "$VDB" "SELECT create_symbol_partitions('VT1')"
expect_ok  "B2 runs row insert"                                 "$VDB" "INSERT INTO runs (strategy_id, strategy_code_hash, mc_seed, corpus_version_id, fill_model_version, parameters) VALUES ('s1','deadbeef',42,'corpus-0','fm-0','{}'::jsonb)"
expect_err "B3 backtest trade WITHOUT run_id rejected"          "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source) VALUES ('backtest','VT1','s1','long','filled','open',now(),0.25,12.50,100.00,400,1,'modeled')"
expect_ok  "B4 backtest trade WITH run_id accepted"             "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,run_id,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source) VALUES ('backtest','VT1','s1','long','filled','open',now(),1,0.25,12.50,100.00,400,1,'modeled')"
expect_val "B5 sequence propagates into partitions (trade_id)"  "$VDB" "SELECT count(*) FROM trades WHERE trade_id IS NOT NULL" "1"
expect_ok  "B6 live trade with broker id"                       "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,broker_trade_id,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source) VALUES ('live','VT1','s1','long','filled','open',now(),'VX-1',0.25,12.50,100.00,400,1,'observed')"
expect_err "B7 duplicate broker_trade_id rejected (idempotent)" "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,broker_trade_id,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source) VALUES ('live','VT1','s1','short','filled','open',now(),'VX-1',0.25,12.50,100.00,400,1,'observed')"
expect_err "B8 initial_stop pairing CHECK (price w/o ticks)"    "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,run_id,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source,initial_stop_price) VALUES ('backtest','VT1','s1','long','filled','open',now(),1,0.25,12.50,100.00,400,1,'modeled',99.00)"
expect_err "B9 bt writer denied UPDATE (immutability)"          "$VDB" "SET ROLE nix_bt_writer; UPDATE trades_backtest SET strategy_id='x'"
expect_ok  "B10 unonboarded symbol lands in DEFAULT partition"  "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,run_id,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source) VALUES ('backtest','ZZZ','s1','long','filled','open',now(),1,0.25,12.50,100.00,400,1,'modeled')"
expect_val "B11 check_default_partitions reports it"            "$VDB" "SELECT count(*) FROM check_default_partitions()" "1"
expect_ok  "B12 run cascade delete"                             "$VDB" "DELETE FROM runs WHERE run_id=1"
expect_val "B13 cascade removed backtest trades"                "$VDB" "SELECT count(*) FROM trades WHERE trade_source='backtest'" "0"

echo "=== C. bar_history template (scratch symbols VT1/VT2/VT3) ==="
( cd "$SCRIPT_DIR" && TRADE_DB="$VDB" bash provision_symbol_bar_history.sh VT1 0.25 continuous_backadjusted >/dev/null 2>&1 ) \
    && ok "C1 provision VT1 (0.25, backadjusted)" || bad "C1 provision VT1"
( cd "$SCRIPT_DIR" && TRADE_DB="$VDB" bash provision_symbol_bar_history.sh VT2 0.03125 continuous_backadjusted >/dev/null 2>&1 ) \
    && ok "C2 provision VT2 (fractional 1/32 grid)" || bad "C2 provision VT2"
( cd "$SCRIPT_DIR" && TRADE_DB="$VDB" bash provision_symbol_bar_history.sh VT3 0.00005 >/dev/null 2>&1 ) \
    && ok "C3 provision VT3 (no series arg)" || bad "C3 provision VT3"
( cd "$SCRIPT_DIR" && TRADE_DB="$VDB" bash provision_symbol_bar_history.sh VT1 0.25 >/dev/null 2>&1 ) \
    && bad "C4 re-provision existing symbol (expected refusal)" || ok "C4 re-provision refused (no clobber)"
# --- three-file split assertions (v3): base + renko + m1 applied in order ---
expect_val "C4a base+renko+m1 objects all present (4 tables)"        "vt1_bar_history" \
    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename IN ('bar_meta','ingest_batches','renko_bricks','candles_m1')" "4"
expect_val "C4b both price views present"                             "vt1_bar_history" \
    "SELECT count(*) FROM pg_views WHERE schemaname='public' AND viewname IN ('renko_bricks_prices','candles_m1_prices')" "2"
if ls "$SCRIPT_DIR"/vt1_base_bar_history.sql "$SCRIPT_DIR"/vt1_renko_bar_history.sql "$SCRIPT_DIR"/vt1_m1_bar_history.sql >/dev/null 2>&1
then ok "C4c per-symbol stamped artifacts written (vt1_{base,renko,m1})"; else bad "C4c stamped artifacts missing"; fi

expect_val "C5 VT3 series_kind defaults to 'unspecified' (QA flag)" "vt3_bar_history" "SELECT series_kind FROM bar_meta" "unspecified"
expect_err "C6 invalid series_kind rejected"                        "vt1_bar_history" "UPDATE bar_meta SET series_kind='banana'"
expect_err "C7 misaligned price rejected by price_to_ticks"         "vt1_bar_history" "SELECT price_to_ticks(6100.30)"
expect_val "C8 fractional-tick exact roundtrip (118.15625)"         "vt2_bar_history" "SELECT ticks_to_price(price_to_ticks(118.15625)) = 118.15625" "t"

psql -d vt1_bar_history -v ON_ERROR_STOP=1 -q >/dev/null 2>&1 << 'EOF'
INSERT INTO ingest_batches (source, source_hash) VALUES ('harness','vh1');
INSERT INTO candles_m1 (bar_timestamp, ingest_batch_id, open_ticks, high_ticks, low_ticks, close_ticks)
VALUES ('2026-08-06 09:31:00-05',1,400,404,399,403),
       ('2026-08-06 09:33:00-05',1,403,405,402,404);   -- deliberate 09:32 gap
INSERT INTO renko_bricks (brick_timestamp, brick_size_ticks, ingest_batch_id, open_ticks, high_ticks, low_ticks, close_ticks, is_reversal)
VALUES ('2026-08-06 09:31:30-05',4,1,400,404,400,404,false),
       ('2026-08-06 09:34:10-05',4,1,400,404,396,396,true);
EOF
[ $? -eq 0 ] && ok "C9 bar seed data accepted" || bad "C9 bar seed data"
expect_err "C10 non-minute-aligned candle rejected"          "vt1_bar_history" "INSERT INTO candles_m1 (bar_timestamp, ingest_batch_id, open_ticks, high_ticks, low_ticks, close_ticks) VALUES ('2026-08-06 09:35:30-05',1,1,1,1,1)"
expect_val "C11 find_candle_gaps finds the 09:32 hole"       "vt1_bar_history" "SELECT count(*) FROM find_candle_gaps('2026-08-06 09:31:00-05','2026-08-06 09:33:00-05')" "1"
expect_val "C12 renko continuity reports reversal delta"     "vt1_bar_history" "SELECT delta_ticks::text || ':' || is_reversal::text FROM check_renko_continuity(4)" "-4:true"
expect_val "C13 delete-by-batch cascade removes exactly its rows" "vt1_bar_history" "BEGIN; DELETE FROM ingest_batches WHERE batch_id=1; SELECT count(*) FROM candles_m1; ROLLBACK" "0"

echo "=== D. FDW hub (in scratch $VDB) ==="
if psql -d "$VDB" -v ON_ERROR_STOP=1 -q -f "$SCRIPT_DIR/symbol_bar_history_hub.sql" >/dev/null 2>&1
then ok "D1 hub DDL applies clean"; else bad "D1 hub DDL failed"; fi
for s in VT1 VT2 VT3; do
    psql -d "$VDB" -v ON_ERROR_STOP=1 -q -c "SELECT bars.register_symbol('$s')" >/dev/null 2>&1
done
expect_val "D2 registry holds all three symbols"     "$VDB" "SELECT count(*) FROM bars.registry" "3"
expect_val "D3 union view spans symbol databases"    "$VDB" "SELECT count(DISTINCT symbol) FROM bars.all_renko_bricks UNION ALL SELECT count(*) FROM bars.all_candles_m1 LIMIT 1" "1"
expect_val "D4 union candles readable w/ prices"     "$VDB" "SELECT count(*) FROM bars.all_candles_m1 WHERE close_price IS NOT NULL" "2"
expect_ok  "D5 seed live trade for join"             "$VDB" "INSERT INTO trades (trade_source,symbol,strategy_id,direction,entry_status,exit_status,entry_timestamp,broker_trade_id,tick_size,tick_value,entry_price,entry_price_ticks,entry_quantity,slippage_source) VALUES ('live','VT1','s1','long','filled','open','2026-08-06 09:31:22-05','VX-J1',0.25,12.50,100.00,400,1,'observed')"
expect_val "D6 THE cross-database trades-to-bars join" "$VDB" "SELECT count(*) FROM trades t JOIN bars.all_candles_m1 c ON c.symbol=t.symbol AND c.bar_timestamp=date_trunc('minute', t.entry_timestamp) WHERE t.broker_trade_id='VX-J1'" "1"
expect_ok  "D7 re-registration idempotent"           "$VDB" "SELECT bars.register_symbol('VT1')"
expect_val "D8 registry stable after re-register"    "$VDB" "SELECT count(*) FROM bars.registry" "3"
expect_val "D9 union view intact after re-register"  "$VDB" "SELECT count(*) FROM bars.all_candles_m1" "2"

echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
if [ $KEEP -eq 0 ]; then teardown; echo "(scratch databases dropped)"; else echo "(scratch databases kept: $VDB $SYMS_DBS)"; fi
[ $FAIL -eq 0 ] && exit 0 || exit 1

```
