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

