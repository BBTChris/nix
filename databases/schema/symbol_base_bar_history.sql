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

