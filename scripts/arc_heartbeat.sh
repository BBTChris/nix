#!/usr/bin/env bash
# arc_heartbeat.sh — the SINGLE SOURCE OF TRUTH for ARC status emit format.
#
# Why this exists: cc kept reconstructing the heartbeat format from priors during
# long runs (context compaction drops the exact spec), producing a 65-line banner
# on every beat instead of the compact ticker. Format that lives in cc's memory
# drifts; format that lives in CODE does not. cc CALLS this; it never re-invents it.
#
# Subcommands:
#   pulse    -> the ONE-LINE ticker. Emit at ~5-min cadence WITHIN a stage.
#   banner   -> the boxed multi-line banner. Emit ONLY at a stage transition.
#   selfcheck-> emit one pulse and confirm it was produced (watchdog self-verify).
#
# State/inputs (Status Contract, D3.244 class):
#   Reads the progress file (default $NIX_SCRATCH/arc_progress.txt), key=value lines:
#     arc=041  start=<epoch>  ts=<epoch>  stage=5  total=15  op=<text>  pct=<0-100>
#   The main run WRITES this each stage/sub-step, stamped with THIS arc + a monotonic ts.
#   Args override file values. HEAD is derived live from git (git wins over prose).
#   Motion is tracked in a sidecar state file so "no forward motion" reads as STALL,
#   not as healthy.
#
# Absence semantics (never confidently wrong):
#   - progress file missing / arc mismatch / ts not advancing -> "STALE PROGRESS FILE"
#   - >=3 consecutive no-motion pulses -> "STALL WARNING"
#
# Exit: 0 on a normal emit; 2 if it could not emit (so a watchdog self-check can tell).
set -uo pipefail

NIX_HOME="${NIX_HOME:-/home/bbt/nix}"
NIX_SCRATCH="${NIX_SCRATCH:-$NIX_HOME/scratchpad}"
PROG="${ARC_PROGRESS:-$NIX_SCRATCH/arc_progress.txt}"
STATE="${ARC_HB_STATE:-$NIX_SCRATCH/.arc_hb_state}"
STALL_AFTER="${ARC_STALL_AFTER:-3}"   # consecutive no-motion pulses before STALL

BAR_W=8                                # progress-bar cells
FILL='#'; EMPTY='-'                    # ASCII bar — box-drawing chars misrender/fold

# ---- arg overrides (all optional; file supplies the rest) --------------------
o_arc=""; o_stage=""; o_total=""; o_op=""; o_pct=""; o_name=""
while [ $# -gt 0 ]; do
  case "$1" in
    pulse|banner|selfcheck) CMD="$1"; shift;;
    --arc)   o_arc="$2";   shift 2;;
    --stage) o_stage="$2"; shift 2;;
    --total) o_total="$2"; shift 2;;
    --op)    o_op="$2";    shift 2;;
    --pct)   o_pct="$2";   shift 2;;
    --name)  o_name="$2";  shift 2;;   # short stage name, banner only
    --progress) PROG="$2"; shift 2;;
    --state)    STATE="$2"; shift 2;;
    *) shift;;
  esac
done
CMD="${CMD:-pulse}"

# ---- read progress file (key=value; last value wins) -------------------------
f_arc=""; f_start=""; f_ts=""; f_stage=""; f_total=""; f_op=""; f_pct=""
if [ -f "$PROG" ]; then
  while IFS='=' read -r k v; do
    case "$k" in
      arc)   f_arc="$v";;
      start) f_start="$v";;
      ts)    f_ts="$v";;
      stage) f_stage="$v";;
      total) f_total="$v";;
      op)    f_op="$v";;
      pct)   f_pct="$v";;
    esac
  done < "$PROG"
fi

arc="${o_arc:-$f_arc}"
stage="${o_stage:-$f_stage}"
total="${o_total:-$f_total}"
op="${o_op:-$f_op}"
pct="${o_pct:-$f_pct}"
name="${o_name:-$op}"

# ---- derive live HEAD (git truth) --------------------------------------------
head_short="$(cd "$NIX_HOME" 2>/dev/null && git rev-parse --short HEAD 2>/dev/null)"
[ -z "$head_short" ] && head_short="nogit"

now="$(date +%s)"

# ---- helpers -----------------------------------------------------------------
is_uint() { case "$1" in ''|*[!0-9]*) return 1;; *) return 0;; esac; }

fmt_dur() { # seconds -> "1h03m" / "12m" / "45s"
  local s="$1"; is_uint "$s" || { printf '?'; return; }
  local h=$((s/3600)) m=$(((s%3600)/60)) sec=$((s%60))
  if [ "$h" -gt 0 ]; then printf '%dh%02dm' "$h" "$m"
  elif [ "$m" -gt 0 ]; then printf '%dm' "$m"
  else printf '%ds' "$sec"; fi
}

make_bar() {
  local p="$1"; is_uint "$p" || p=0
  [ "$p" -gt 100 ] && p=100
  local fills=$(( (p*BAR_W + 50) / 100 )); local i=0 out=""
  while [ "$i" -lt "$BAR_W" ]; do
    if [ "$i" -lt "$fills" ]; then out="$out$FILL"; else out="$out$EMPTY"; fi
    i=$((i+1))
  done
  printf '%s' "$out"
}

# elapsed / eta
elapsed_s=""; eta_txt="~?"
if is_uint "$f_start"; then elapsed_s=$(( now - f_start )); [ "$elapsed_s" -lt 0 ] && elapsed_s=0; fi
if is_uint "$pct" && [ "${pct:-0}" -gt 0 ] && [ "${pct:-0}" -lt 100 ] && [ -n "$elapsed_s" ]; then
  eta_txt="~$(fmt_dur $(( elapsed_s * (100 - pct) / pct )) )"
elif [ "${pct:-0}" = "100" ]; then eta_txt="~done"; fi
elapsed_txt="$( [ -n "$elapsed_s" ] && fmt_dur "$elapsed_s" || printf '?' )"

# ---- freshness + motion ------------------------------------------------------
# STALE if: no progress file, arc mismatch, or ts not advancing vs last emit.
stale_reason=""
if [ ! -f "$PROG" ]; then stale_reason="no progress file"; fi
if [ -n "$o_arc" ] && [ -n "$f_arc" ] && [ "$o_arc" != "$f_arc" ]; then
  stale_reason="progress file is for arc $f_arc, expected $o_arc"
fi

# load last state
l_head=""; l_stage=""; l_pct=""; l_ts=""; l_nomotion=0
if [ -f "$STATE" ]; then
  while IFS='=' read -r k v; do
    case "$k" in
      head) l_head="$v";; stage) l_stage="$v";; pct) l_pct="$v";;
      ts) l_ts="$v";; nomotion) l_nomotion="$v";;
    esac
  done < "$STATE"
fi

# motion = did HEAD, stage, or pct advance since last emit?
motion="ADVANCED"; nomotion="$l_nomotion"
if [ "$head_short" = "$l_head" ] && [ "$stage" = "$l_stage" ] && [ "$pct" = "$l_pct" ]; then
  motion="no motion"; nomotion=$(( l_nomotion + 1 ))
else
  motion="ADVANCED"; nomotion=0
fi

# ts advancing check (progress file must move if the run is alive)
if [ -z "$stale_reason" ] && is_uint "$f_ts" && is_uint "$l_ts" && [ "$f_ts" = "$l_ts" ] && [ "$motion" = "no motion" ]; then
  : # ts frozen AND no motion -> reinforces stall; handled below
fi

# persist state (best-effort; scratch may be read-only in a probe)
mkdir -p "$(dirname "$STATE")" 2>/dev/null
{ printf 'head=%s\nstage=%s\npct=%s\nts=%s\nnomotion=%s\n' \
    "$head_short" "${stage:-}" "${pct:-}" "${f_ts:-}" "$nomotion"; } > "$STATE" 2>/dev/null || true

# ---- emit --------------------------------------------------------------------
bar="$(make_bar "${pct:-0}")"
arc_lbl="ARC ${arc:-?}"
stage_lbl="stage ${stage:-?}/${total:-?}"

emit_pulse() {
  if [ -n "$stale_reason" ]; then
    printf '[%s %s ??%% %s - STALE PROGRESS FILE: %s - HEAD %s]\n' \
      "$arc_lbl" "$bar" "$stage_lbl" "$stale_reason" "$head_short"
    return
  fi
  local warn=""
  if [ "$motion" = "no motion" ] && [ "$nomotion" -ge "$STALL_AFTER" ]; then
    warn=" - STALL WARNING: no motion in ${nomotion} intervals, current op = ${op:-?}"
  fi
  # ONE line. First line of stdout is the ticker.
  printf '[%s %s %s%% %s - %s - %s - %s - HEAD %s %s%s]\n' \
    "$arc_lbl" "$bar" "${pct:-0}" "$stage_lbl" "${op:-?}" \
    "$elapsed_txt" "$eta_txt" "$head_short" "$motion" "$warn"
}

emit_banner() {
  local rule; rule="$(printf '=%.0s' $(seq 1 68))"
  printf '%s\n' "$rule"
  printf ' %s - STAGE %s/%s: %s\n' "$arc_lbl" "${stage:-?}" "${total:-?}" "${name:-?}"
  if [ -n "$stale_reason" ]; then
    printf ' STALE PROGRESS FILE: %s - HEAD %s\n' "$stale_reason" "$head_short"
  else
    printf ' ~%s in - %s left (rough) - HEAD %s\n' "$elapsed_txt" "$eta_txt" "$head_short"
  fi
  printf '%s\n' "$rule"
}

case "$CMD" in
  pulse)  emit_pulse;;
  banner) emit_banner;;
  selfcheck)
    out="$(emit_pulse)"
    if [ -n "$out" ]; then
      printf '%s\n' "$out"
      printf 'HEARTBEAT SELF-VERIFY: ok (emitter produced a pulse)\n'
      exit 0
    else
      printf 'HEARTBEAT SELF-VERIFY: FAILED (emitter produced nothing)\n' >&2
      exit 2
    fi
    ;;
  *) printf 'usage: arc_heartbeat.sh {pulse|banner|selfcheck} [--arc N --stage k --total T --op S --pct P --name S]\n' >&2; exit 2;;
esac
