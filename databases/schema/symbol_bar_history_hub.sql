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

