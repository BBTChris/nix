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

