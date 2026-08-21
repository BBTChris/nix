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
#   teardown -> the WATCHDOG TEARDOWN line, in the form the reader can actually see.
#   marker   -> the completion marker, PRINTED AND RECORDED in ONE call (D3.464).
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
o_arc=""; o_stage=""; o_total=""; o_op=""; o_pct=""; o_name=""; o_pid=""
while [ $# -gt 0 ]; do
  case "$1" in
    pulse|banner|selfcheck|teardown|marker) CMD="$1"; shift;;
    --arc)   o_arc="$2";   shift 2;;
    --stage) o_stage="$2"; shift 2;;
    --total) o_total="$2"; shift 2;;
    --op)    o_op="$2";    shift 2;;
    --pct)   o_pct="$2";   shift 2;;
    --name)  o_name="$2";  shift 2;;   # short stage name, banner only
    --pid)   o_pid="$2";   shift 2;;   # cc's own watchdog pid, teardown only
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

# ---- D3.464 / D3.465: THE TEARDOWN LINE AND THE MARKER, EMITTED BY THE SCRIPT
#
# TWO DEFECTS, ONE CAUSE — cc hand-formatted the two lines that close an arc, and
# a format that lives in cc's memory drifts (the whole reason this file exists).
#
# D3.464, MEASURED ARC 051: `arc_050.log` carries NO `**** ARC completed ****`.
#   The run reached close-out and printed the marker to the CHAT; the log is
#   written by this script and the marker never passed through it, so
#   `check_arc_status_contract` read CANNOT-MEASURE ("run did not reach
#   close-out") on a run that had. `marker` below closes it the small way the
#   debt row named: the marker cannot be emitted without landing in the log,
#   because printing it and recording it are the same call.
#
# D3.465, MEASURED ARC 052 at 9a96eab: `arc_051.log` carries BOTH the marker and
#   a teardown line, and the gate still read FAIL with `teardowns=0`. `CLAUDE.md`
#   tells cc to prove the teardown while disclaiming the root-owned kernel thread
#   `[watchdogd]`, and cc wrote both on ONE line; the reader's kernel-thread veto
#   is line-scoped, so the disclaimer took the whole line out. The contract's own
#   prescribed sentence was unreadable by the gate that checks it. Repaired on
#   BOTH sides and each repair stands alone: the reader now requires a POSITIVE
#   cc-watchdog signature instead of vetoing on a mention (see the check), and
#   this emitter puts the disclaimer on its OWN line so the two facts never share
#   one.
#
# `marker` FAILS CLOSED. It refuses to print if this arc's log holds no teardown
# line carrying cc's own signature, and prints a named refusal instead. The
# marker is a certificate over a state (§16.4 / CHECK-A10); a certificate issued
# before the instrument was proven dead is the thing the gate exists to catch,
# and the emitter is the last place it can be caught cheaply.
WD_SIG_TEXT="arc_heartbeat"          # cc's OWN watchdog signature, positive ID
KERNEL_WD_NOTE="The root-owned kernel thread [watchdogd] is NOT cc's, cannot be killed, and is NOT a leak."

# WHAT `teardown` DOES NOT DO, and why the omission is deliberate: it does NOT
# scan for cc's watchdog. This file is the source of truth for the FORMAT, not
# for the fact — its own header says cc calls it and never re-invents the format,
# and detection is a different job. An in-emitter scan was written and MEASURED
# ARC 052: `pgrep -af arc_heartbeat` matches the shell that is invoking this very
# script, and under a tool harness it also matches a SIBLING wrapper whose command
# line merely names the script, so the arm reported WATCHDOG STILL ALIVE against
# its own caller. A detector that fires on its own invocation is worse than no
# detector, because its false positive is loud and looks authoritative.
#
# So cc performs the scan (`ps -eo pid,ppid,user,args` matched to cc's OWN
# signature, ignoring the root-owned `[watchdogd]`, exactly as `CLAUDE.md` says)
# and calls this to render the sentence. `check_arc_status_contract --live` keeps
# the independent process check, on the reader's side, where it belongs.

emit_teardown() {
  local pid="${o_pid:-}"
  if [ -n "$pid" ]; then
    printf 'WATCHDOG TEARDOWN: confirmed dead (pid %s / %s)\n' "$pid" "$WD_SIG_TEXT"
  else
    printf 'WATCHDOG TEARDOWN: confirmed dead (no %s process owned by cc is alive; cc matched its own signature with ps -eo pid,ppid,user,args and found none)\n' "$WD_SIG_TEXT"
  fi
  # SEPARATE LINE, and that is the D3.465 repair on this side: the disclaimer is
  # a fact about a DIFFERENT process and must not share a line with the claim.
  printf '%s\n' "$KERNEL_WD_NOTE"
}

emit_marker() {
  local log="$ARC_LOG_DIR/arc_${arc}.log"
  if [ -z "$arc" ]; then
    printf 'MARKER REFUSED: no arc id in %s — a marker filed under no arc certifies nothing\n' "$PROG" >&2
    return 2
  fi
  if ! grep -q "WATCHDOG TEARDOWN: confirmed.*$WD_SIG_TEXT" "$log" 2>/dev/null; then
    printf 'MARKER REFUSED: %s holds no teardown line naming the watchdog signature %s that cc runs its own watchdog under.\n' "$log" "$WD_SIG_TEXT" >&2
    printf 'Run: scripts/arc_heartbeat.sh teardown   (the marker certifies a torn-down state; it cannot precede the proof)\n' >&2
    return 2
  fi
  # PRINTED AND RECORDED IN ONE CALL. This is D3.464 closed: there is no path
  # through this function that shows the operator a marker the log did not get.
  printf '**** ARC completed ****\n' | record
}

# ---- D3.455: THE EMITTER WRITES ITS OWN LOG --------------------------------
# ARC 048 ran the emitter from kickoff and never redirected it, so
# `check_arc_status_contract` audited a COMPLETED arc's log while a different
# arc was running -- green for the wrong subject. The tee lived in cc's memory
# of the brief, and prose degrades (the D3.445/D3.447 class). It lives here now:
# a beat cannot be emitted without being recorded. The log is named from the
# progress file's OWN arc id, so a beat is never filed under another arc's name.
# Failure to open the log NEVER suppresses the beat -- the operator's line is
# the primary duty and the recording is the secondary one.
ARC_LOG_DIR="${ARC_LOG_DIR:-$NIX_SCRATCH/arc_logs}"
record() {  # stdin -> stdout, and append to this arc's own log if we can name it
  if [ -z "$arc" ] || ! mkdir -p "$ARC_LOG_DIR" 2>/dev/null; then cat; return; fi
  tee -a "$ARC_LOG_DIR/arc_${arc}.log" 2>/dev/null || cat
}

case "$CMD" in
  pulse)  emit_pulse | record;;
  banner) emit_banner | record;;
  selfcheck)
    out="$(emit_pulse)"
    if [ -n "$out" ]; then
      { printf '%s\n' "$out"
        printf 'HEARTBEAT SELF-VERIFY: ok (emitter produced a pulse)\n'; } | record
      exit 0
    else
      printf 'HEARTBEAT SELF-VERIFY: FAILED (emitter produced nothing)\n' >&2
      exit 2
    fi
    ;;
  teardown) emit_teardown | record;;
  marker)   emit_marker;;
  *) printf 'usage: arc_heartbeat.sh {pulse|banner|selfcheck|teardown|marker} [--arc N --stage k --total T --op S --pct P --name S --pid N]\n' >&2; exit 2;;
esac
