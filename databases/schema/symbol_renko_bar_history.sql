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

