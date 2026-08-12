#!/usr/bin/env bash
# Name:     nix_status.sh
# Version:  1.2.0
# Objective: At-a-glance health dashboard for Nix, built on top of verify.py's
#            own plugin checks. Unlike titan_status.sh (which probes Titan's
#            subsystems directly), nix_status.sh does NOT reimplement checks —
#            it invokes verify.py in its VERIFY-ONLY mode (never Verify+Repair)
#            and renders verify.py's per-check verdicts as red/yellow/green
#            bubbles, with an overall rollup at the bottom. verify.py remains
#            the single source of truth for node state (elements_v2.md §1.3);
#            this script is strictly an observability wrapper around it.
#
# Usage:
#     bash ~/nix/scripts/nix_status.sh              # Snapshot, exit
#     bash ~/nix/scripts/nix_status.sh --watch      # Refresh every 5s until Ctrl+C
#     bash ~/nix/scripts/nix_status.sh -w 10        # Refresh every 10s
#     bash ~/nix/scripts/nix_status.sh --brief      # Single-line summary
#     bash ~/nix/scripts/nix_status.sh --no-color   # Strip ANSI
#     bash ~/nix/scripts/nix_status.sh --no-splash  # Skip the SSH splash header
#     bash ~/nix/scripts/nix_status.sh --raw FILE   # Also save verify.py's raw output
#
# Checks (each produces a bubble):
#     1. verify.py present + executable
#     2. Python interpreter resolvable (venv preferred, else system python3)
#     3. Verify-only INVOCATION provable from `verify.py --help` — either a
#        mode-style choice (`--mode verify`) or a bare flag (`--no-repair`)
#     4. verify.py run completes within timeout, non-vacuously (>=1 parsed verdict)
#  5..N. One bubble per check verify.py itself reports (name + verdict derived
#        from verify.py's own output — never a hardcoded roster; see §7.4),
#        grouped by verdict — PASS, then FAIL, then WARNING — and ALPHABETICAL
#        by check name WITHIN each group (v1.2.0). No manifest.json dependency,
#        and re-runs over an unchanged tree stay byte-identical, which was the
#        original reason for sorting at all and is now the secondary key.
#
# Doctrine note — why this wrapper refuses to just "run it":
#     VERIFY-AND-CHECKS.md §7.9 (fail closed, fail loud) and the vacuous-pass
#     doctrine both apply here. Two failure modes this script exists to avoid:
#       (a) silently invoking verify.py's default mode, which may REPAIR the
#           node instead of merely reporting on it. Check 3 refuses to run
#           verify.py at all unless a verify-only invocation is PROVEN present
#           in `verify.py --help` output — a derived check, never an assumed
#           flag name.
#       (b) reporting "healthy" having parsed zero check verdicts from
#           verify.py's output (a format change, a crash before first check,
#           etc.). That is the textbook vacuous pass this project's doctrine
#           names explicitly — check 4 treats zero parsed verdicts as FAILED,
#           never as HEALTHY.
#     verify.py's own exit code and its per-check verdicts must agree, judged
#     against verify.py's DOCUMENTED exit mapping (0 pass / 1 fail /
#     2 cannot-measure / 3 guarded, nix_check_contract.md §4.2 + CHECK-A1); a
#     disagreement is reported at the worse of the two, not guessed at.
#
# Exit codes:
#     0 = healthy    (verify.py ran, all checks PASS)
#     1 = degraded   (at least one CANNOT-MEASURE / known-red, no FAIL)
#     2 = failed     (at least one FAIL, or verify.py could not be run at all)
#
# Changelog:
#   v1.2.0  2026-08-12  Three operator-facing changes, no change to how any
#                         verdict is DERIVED:
#                         (1) The SSH splash is rendered at the top, by EXECUTING
#                         /etc/update-motd.d/99-nix-banner rather than by copying
#                         its artwork here. The banner owns the logo, the host
#                         facts and the market clock; a second copy would drift
#                         from it silently, which is the "never restate a mutable
#                         fact" rule (CLAUDE.md core directive 3) applied to
#                         presentation. If the banner is missing or fails, that
#                         is SAID in one dim line, never passed over in silence.
#                         Suppress with --no-splash or NIX_STATUS_SPLASH=0.
#                         (2) Per-check bubbles now group by verdict — PASS, then
#                         FAIL, then WARNING — and stay ALPHABETICAL WITHIN each
#                         group, so re-runs remain byte-identical. The v1.0.0
#                         note below explains why alphabetical mattered; that
#                         property is kept, it is now the secondary key. The four
#                         wrapper bubbles (1-4) are NOT reordered: their sequence
#                         is causal (verify.py present -> interpreter -> proven
#                         verify-only invocation -> run), and shuffling a causal
#                         chain by outcome would make a failure read as though it
#                         happened somewhere it did not.
#                         (3) A SUMMARY block at the bottom tallies what is
#                         actually on screen, counted as the bubbles are
#                         recorded rather than recomputed from a second pass, so
#                         the tally cannot disagree with the list above it.
#   v1.1.0  2026-08-12  Fixes two independent faults that together meant the
#                         dashboard rendered 2 of the 28 registered checks:
#                         (1) the verify-only prover only understood BARE
#                         BOOLEAN flags, but this tree's verify.py spells
#                         verify-only as the value-taking `--mode verify`, so
#                         nothing matched and check 3 refused to run verify.py
#                         at all — the dashboard reported on a run that never
#                         happened. Now derives a mode-style choice as well as
#                         a bare flag, and carries the invocation as ARGV.
#                         (2) the output parser scanned whole lines for
#                         uppercase PASS/FAIL/OK/RED, but render.py emits
#                         `[ok]`/`[FAIL]`/`[??]`/`[--]`/`[GRD]` — 24 of 28
#                         lines matched nothing and were dropped in silence,
#                         and a check's free-text detail could decide its
#                         colour. Verdicts now come from the leading status
#                         marker only, in both of render.py's glyph sets, and
#                         cover all six contract statuses.
#                         Also: exit-code reconciliation now uses verify.py's
#                         documented mapping (rc 2 = cannot-measure, rc 3 =
#                         guarded) instead of calling every non-zero rc a
#                         disagreement, which painted every degraded run red.
#                         Regression tests: scripts/tests/test_nix_status.py.
#   v1.0.0  2026-08-12  Initial version. Structure modeled on titan_status.sh
#                         v1.3.2 (bubble rendering, record()/RESULTS pattern,
#                         --watch/--brief/--no-color, 0/1/2 exit contract).
#                         Content differs by design: nix_status.sh has no
#                         independent probes — every bubble beyond 1-4 is
#                         derived from verify.py's own output, per this
#                         project's "never a second behavioral authority"
#                         rule (elements_v2.md) and the vacuous-pass doctrine
#                         (debug.md §7.3/§7.9). Flag-proof (check 3) and
#                         non-vacuity (check 4) have no titan_status analogue
#                         — they exist because this script wraps another
#                         instrument instead of measuring the system directly.
#                         Per-check bubbles render in alphabetical order by
#                         check name (deliberate: no dependency on checks/
#                         manifest.json's execution order, deterministic
#                         regardless of the order verify.py prints in).

set -uo pipefail

# ─── CONFIG ─────────────────────────────────────────────────────────
NIX_HOME="${NIX_HOME:-$HOME/nix}"
VERIFY_PY="${NIX_VERIFY_PY:-$NIX_HOME/scripts/verify.py}"

TIMEOUT_S="${NIX_STATUS_TIMEOUT:-300}"
HELP_TIMEOUT_S="${NIX_STATUS_HELP_TIMEOUT:-30}"
LOCK_FILE="${NIX_STATUS_LOCK:-${TMPDIR:-/tmp}/nix_status.$(id -u).lock}"

FORCE_FLAG="${NIX_VERIFY_FLAG:-}"          # explicit override, still verified
FORCE_UNSAFE="${NIX_VERIFY_FLAG_FORCE:-0}" # 1 = accept override without --help proof

# Verify-only can be spelled two ways, and v1.0.0 only knew one of them.
#
#   (a) a CHOICE of a mode-style option — `--mode {verify,correct,install}`,
#       which is what this tree's verify.py actually exposes; or
#   (b) a bare boolean flag — `--verify-only`, `--no-repair`, ...
#
# Both are derived from `verify.py --help`, never assumed (VERIFY-AND-CHECKS.md
# §7.4: never anchor to something that moves). Form (a) is tried first because
# a mode-style CLI usually has no boolean synonym, and it is the shape that
# carries a *default* — the default being `verify` is exactly why omitting the
# argument would still be unsafe to rely on: a later verify.py could change it.
#
# v1.0.0 held only the (b) roster, so `--mode verify` matched nothing, check 3
# fired its refusal, and the dashboard reported on a run that never happened.
MODE_CHOICE_PREFS=(verify verify-only check check-only report report-only audit dry-run)
CANDIDATE_FLAGS=(
    --verify-only --verify --check-only --check --no-repair --norepair
    --dry-run --dryrun --report-only --summary --quick
)

# Node02 is a fixed, known target (Ubuntu 26.04 headless per dev_and_services_
# plan.md) — unlike titan_status.sh, there is no cross-platform stat/date
# dialect to detect here. GNU coreutils semantics are assumed throughout.

# ─── COLORS ─────────────────────────────────────────────────────────
BOLD="\033[1m"
DIM="\033[2m"
RED="\033[91m"
YELLOW="\033[93m"
GREEN="\033[92m"
RESET="\033[0m"

# ─── ARG PARSING ────────────────────────────────────────────────────
WATCH=0
WATCH_INTERVAL=5
BRIEF=0
# The SSH splash. Default ON; NIX_STATUS_SPLASH=0 or --no-splash turns it off.
# --brief never renders it: a single-line summary exists to be grepped and piped,
# and eleven lines of logo above it would defeat the only reason it exists.
SPLASH=${NIX_STATUS_SPLASH:-1}
# The banner is EXECUTED, never transcribed. It owns the logo, the host facts and
# the market clock; a copy here would drift from it in silence.
SPLASH_SCRIPT="${NIX_STATUS_SPLASH_SCRIPT:-/etc/update-motd.d/99-nix-banner}"
# Hard bound on the splash. It shells out to `ip`, `df` and a market clock; a
# hung call there must never hold the dashboard.
SPLASH_TIMEOUT_S="${NIX_STATUS_SPLASH_TIMEOUT:-10}"
RAW_OUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --watch|-w)
            WATCH=1
            if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
                WATCH_INTERVAL="$2"
                (( WATCH_INTERVAL < 1 )) && WATCH_INTERVAL=1
                shift 2
            else
                shift
            fi
            ;;
        --brief|-b)
            BRIEF=1
            shift
            ;;
        --no-color)
            BOLD=""; DIM=""; RED=""; YELLOW=""; GREEN=""; RESET=""
            shift
            ;;
        --no-splash)
            SPLASH=0
            shift
            ;;
        --raw)
            [[ $# -ge 2 ]] || { echo "nix_status: --raw needs a path" >&2; exit 2; }
            RAW_OUT="$2"
            shift 2
            ;;
        -t|--timeout)
            [[ $# -ge 2 ]] || { echo "nix_status: --timeout needs seconds" >&2; exit 2; }
            TIMEOUT_S="$2"
            shift 2
            ;;
        -h|--help)
            cat <<EOF
nix_status.sh v1.1.0 — verify.py verify-only wrapper + health dashboard

Usage:
    bash nix_status.sh              Snapshot, exit
    bash nix_status.sh --watch      Refresh every 5s until Ctrl+C
    bash nix_status.sh -w 10        Refresh every 10s (min 1)
    bash nix_status.sh --brief      Single-line summary
    bash nix_status.sh --no-color   Strip ANSI
    bash nix_status.sh --no-splash  Skip the SSH splash header
    bash nix_status.sh --raw FILE   Also save verify.py's raw output to FILE

Exit codes:
    0  healthy    (verify.py ran, all checks PASS)
    1  degraded   (at least one CANNOT-MEASURE / known-red, no FAIL)
    2  failed     (at least one FAIL, or verify.py could not be run at all)

Environment overrides:
    NIX_HOME                default \$HOME/nix
    NIX_VERIFY_PY            path to verify.py (default \$NIX_HOME/scripts/verify.py)
    NIX_PYTHON               interpreter (else \$NIX_HOME/.venv/bin/python, else python3)
    NIX_VERIFY_FLAG          force the verify-only invocation; may be several
                             tokens ("--mode verify"). Its first token is still
                             checked against --help
    NIX_VERIFY_FLAG_FORCE    1 = accept NIX_VERIFY_FLAG without --help proof
    NIX_STATUS_TIMEOUT       verify.py run timeout, seconds (default 300)
    NIX_STATUS_HELP_TIMEOUT  verify.py --help timeout, seconds (default 30)
    NIX_STATUS_LOCK          lock file path (default /tmp/nix_status.<uid>.lock)
    NIX_STATUS_SPLASH        0 = never render the SSH splash header
    NIX_STATUS_SPLASH_SCRIPT path to the splash (default the MOTD banner)
EOF
            exit 0
            ;;
        --version)
            echo "nix_status.sh 1.2.0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1 (use --help for usage)" >&2
            exit 2
            ;;
    esac
done
[[ "$TIMEOUT_S" =~ ^[0-9]+$ ]] || { echo "nix_status: --timeout must be an integer" >&2; exit 2; }

# ─── STATUS TRACKING ────────────────────────────────────────────────
WORST_STATUS=0
RESULTS=()
STATUS_WORD=([0]="healthy" [1]="degraded" [2]="failed")

# Display order for the per-check bubbles: PASS, then FAIL, then WARNING.
# This is a SORT KEY ONLY and deliberately not the severity order — severity is
# `WORST_STATUS`, which still ranks FAIL(2) above WARNING(1) above PASS(0) and
# decides the exit code. Conflating the two would be the bug: reordering the
# display must never be able to move the verdict.
STATUS_RANK=([0]=0 [2]=1 [1]=2)

# The summary is counted HERE, as each bubble is recorded, rather than by
# re-reading RESULTS afterwards. A second pass over rendered strings would be a
# second derivation of the same fact, and the two could disagree — which is
# exactly the defect class this tree sweeps for. One increment, one source.
STATUS_COUNT=([0]=0 [1]=0 [2]=0)

record() {
    local st="$1" label="$2" detail="$3" bubble
    case "$st" in
        0) bubble="${GREEN}●${RESET}" ;;
        1) bubble="${YELLOW}●${RESET}" ;;
        2) bubble="${RED}●${RESET}" ;;
    esac
    local label_fmt
    label_fmt="$(printf '%-28s' "$label")"
    RESULTS+=("  ${bubble}  ${BOLD}${label_fmt}${RESET}  ${DIM}${detail}${RESET}")
    STATUS_COUNT[$st]=$(( STATUS_COUNT[$st] + 1 ))
    (( st > WORST_STATUS )) && WORST_STATUS="$st"
}

# ─── HELPERS ────────────────────────────────────────────────────────
strip_ansi() { sed -E 's/\x1B\[[0-9;?]*[A-Za-z]//g; s/\r$//'; }

pick_python() {
    if [[ -n "${NIX_PYTHON:-}" ]]; then printf '%s' "$NIX_PYTHON"; return; fi
    if [[ -x "$NIX_HOME/.venv/bin/python" ]]; then printf '%s' "$NIX_HOME/.venv/bin/python"; return; fi
    command -v python3 2>/dev/null
}

# ─── CHECKS ─────────────────────────────────────────────────────────

_TMPDIR=""
_PYBIN=""
_VERIFY_ARGV=()     # the proven verify-only invocation, as ARGV (may be 2 tokens)
_RUN_TXT=""
_RUN_RC=""

# 1. verify.py presence
check_verify_binary() {
    if [[ ! -f "$VERIFY_PY" ]]; then
        record 2 "verify.py" "not found at ${VERIFY_PY}"
        return 1
    fi
    if [[ ! -r "$VERIFY_PY" ]]; then
        record 2 "verify.py" "found but not readable: ${VERIFY_PY}"
        return 1
    fi
    record 0 "verify.py" "${VERIFY_PY}"
    return 0
}

# 2. Python interpreter
check_python() {
    _PYBIN="$(pick_python)"
    if [[ -z "$_PYBIN" || ! -x "$_PYBIN" ]]; then
        record 2 "Python interpreter" "none found (set NIX_PYTHON)"
        return 1
    fi
    record 0 "Python interpreter" "$_PYBIN"
    return 0
}

# Finds a mode-style option whose CHOICE SET contains a verify-only choice,
# e.g. `--mode {verify,correct,install}` -> "--mode verify". Prints the two
# tokens, or nothing. Reads a whitespace-flattened help text, because argparse
# wraps `--mode` and its brace onto separate lines whenever the terminal is
# narrow — matching the unflattened text would work on one width and not
# another, which is the same class of bug as anchoring to a moving value.
derive_mode_invocation() {
    local flat="$1" want opt choices choice
    for want in "${MODE_CHOICE_PREFS[@]}"; do
        while read -r opt choices; do
            [[ -z "$opt" ]] && continue
            local IFS=,
            for choice in $choices; do
                if [[ "$choice" == "$want" ]]; then
                    printf '%s\n%s\n' "$opt" "$choice"
                    return 0
                fi
            done
        done < <(grep -oE -- '--[a-z][a-z0-9-]* \{[^}]*\}' <<<"$flat" |
                 sed -E 's/^(--[a-z0-9-]+) \{([^}]*)\}$/\1 \2/')
    done
    return 1
}

# 3. Verify-only invocation — proven, never assumed (see Doctrine note above)
check_verify_only_flag() {
    local help_txt rc=0
    help_txt="$(mktemp "${_TMPDIR}/help.XXXXXX")"
    timeout -k 5 "$HELP_TIMEOUT_S" "$_PYBIN" "$VERIFY_PY" --help </dev/null >"$help_txt" 2>&1 || rc=$?
    if [[ ! -s "$help_txt" ]]; then
        record 2 "Verify-only mode" "verify.py --help produced no output (rc=$rc) — cannot prove a safe invocation exists"
        return 1
    fi
    local help_plain help_flat
    help_plain="$(strip_ansi <"$help_txt")"
    help_flat="$(tr '\n' ' ' <<<"$help_plain" | tr -s ' ')"

    # Explicit override. Accepts multiple tokens ("--mode verify"); its FIRST
    # token is what must be provable in --help.
    if [[ -n "$FORCE_FLAG" ]]; then
        local -a forced=()
        read -r -a forced <<<"$FORCE_FLAG"
        if (( ${#forced[@]} == 0 )); then
            record 2 "Verify-only mode" "NIX_VERIFY_FLAG is set but empty"
            return 1
        fi
        if [[ "$FORCE_UNSAFE" == "1" ]] || grep -qw -- "${forced[0]}" <<<"$help_plain"; then
            _VERIFY_ARGV=("${forced[@]}")
            record 0 "Verify-only mode" "${_VERIFY_ARGV[*]} (forced via NIX_VERIFY_FLAG)"
            return 0
        fi
        record 2 "Verify-only mode" "NIX_VERIFY_FLAG='${FORCE_FLAG}' not present in --help (set NIX_VERIFY_FLAG_FORCE=1 to override)"
        return 1
    fi

    # (a) mode-style option with a verify-only choice
    local -a derived=()
    mapfile -t derived < <(derive_mode_invocation "$help_flat")
    if (( ${#derived[@]} == 2 )); then
        _VERIFY_ARGV=("${derived[0]}" "${derived[1]}")
        record 0 "Verify-only mode" "${_VERIFY_ARGV[*]}"
        return 0
    fi

    # (b) bare boolean flag
    local f
    for f in "${CANDIDATE_FLAGS[@]}"; do
        if grep -qw -- "$f" <<<"$help_plain"; then
            _VERIFY_ARGV=("$f")
            record 0 "Verify-only mode" "$f"
            return 0
        fi
    done
    record 2 "Verify-only mode" "no verify-only mode or no-repair flag found in --help — refusing to invoke verify.py (would risk Verify+Repair)"
    return 1
}

# 4. Run verify.py and parse its checks into dynamic bubbles
check_verify_run() {
    _RUN_TXT="$(mktemp "${_TMPDIR}/run.XXXXXX")"

    exec 9>"$LOCK_FILE" 2>/dev/null
    if command -v flock >/dev/null 2>&1; then
        if ! flock -n 9; then
            record 2 "verify.py run" "another nix_status run holds the lock (${LOCK_FILE})"
            return 1
        fi
    fi

    local start end elapsed rc=0
    start=$(date -u +%s)
    timeout -k 10 "$TIMEOUT_S" "$_PYBIN" "$VERIFY_PY" "${_VERIFY_ARGV[@]}" \
        </dev/null >"$_RUN_TXT" 2>&1 || rc=$?
    end=$(date -u +%s)
    elapsed=$(( end - start ))
    _RUN_RC="$rc"

    [[ -n "$RAW_OUT" ]] && cp -f "$_RUN_TXT" "$RAW_OUT" 2>/dev/null

    if [[ $rc -eq 124 || $rc -eq 137 ]]; then
        record 2 "verify.py run" "exceeded ${TIMEOUT_S}s and was killed (rc=$rc) — no verdict"
        return 1
    fi

    record 0 "verify.py run" "${VERIFY_PY} ${_VERIFY_ARGV[*]} — ${elapsed}s, rc=${rc}"

    parse_and_record_checks
}

# Parses verify.py's own PASS/FAIL/CANNOT-MEASURE lines into bubbles. Names
# and counts are derived from the run's output every time — never a
# hardcoded roster (VERIFY-AND-CHECKS.md §7.4). Checks are collected first
# and rendered in ALPHABETICAL ORDER by check name (Chris's call — no
# manifest.json dependency), independent of whatever order verify.py
# happened to print them in. Sort is stable and case-sensitive (LC_ALL=C)
# so re-runs against unchanged output are byte-identical (debug.md §7.7:
# compare verdict-by-verdict, never let an aggregate/order swap hide).
parse_and_record_checks() {
    local n_seen=0
    local line verdict name
    # Each entry: "<name>\t<verdict>\t<line>" — NUL-free names/lines assumed
    # (verify.py output is text); sorted on the name field only.
    local -a entries=()

    local marker rest
    while IFS= read -r raw; do
        line="$(strip_ansi <<<"$raw")"
        [[ -z "${line// }" ]] && continue

        # The verdict is read from the LEADING STATUS MARKER and from nothing
        # else. Both of render.py's glyph sets are accepted (ASCII when the
        # stream is a pipe — which is always, here — Unicode when it is a UTF-8
        # tty), and the marker must be the first field on the line.
        #
        # v1.0.0 instead scanned the whole line for uppercase words PASS / FAIL
        # / OK / RED / CANNOT-MEASURE. That was wrong twice over: the real
        # markers are `[ok]`/`[FAIL]`/`[??]`/`[--]`/`[GRD]`, so 24 of 28 checks
        # matched nothing and were dropped in silence; and a check's free-text
        # DETAIL could decide its colour, so a passing check whose message
        # mentioned a failure it had ruled out was painted red. Anchoring on the
        # first field makes prose structurally unable to reach the verdict.
        read -r marker rest <<<"$line"
        case "$marker" in
            '[ok]'|'✔')             verdict=0 ;;   # PASS
            '[FAIL]'|'✖')           verdict=2 ;;   # FAIL_REPAIRABLE / _NEEDS_OPERATOR
            '[??]'|'⚠')             verdict=1 ;;   # CANNOT_MEASURE
            '[--]'|'·')             verdict=1 ;;   # SKIPPED — never ran, never a pass
            '[GRD]'|'◐')            verdict=1 ;;   # GUARDED (CHECK-A1): withholds certification
            *) continue ;;
        esac

        # The name is the field after the marker; render.py's `_line()` puts it
        # there and pads it. Fall back to a check_-shaped token anywhere on the
        # line, then to a placeholder, so an unparsed name is still a visible
        # bubble rather than a silently missing one.
        read -r name _ <<<"$rest"
        if [[ -z "$name" ]]; then
            if [[ "$line" =~ (check_[A-Za-z0-9_.-]+) ]]; then
                name="${BASH_REMATCH[1]}"
            else
                name="(unnamed check)"
            fi
        fi

        # Detail is what verify.py said MINUS the marker and the name, both of
        # which the bubble already carries. Truncation is what makes this worth
        # doing: 60 characters of "[ok]   check_ibgateway_service 127.0.0..."
        # is mostly a restatement, and the part that gets cut is the only part
        # an operator needs.
        local detail="${rest#"$name"}"
        detail="${detail#"${detail%%[![:space:]]*}"}"
        # Field 1 is the DISPLAY RANK (PASS/FAIL/WARNING), field 2 the name.
        # Carrying the rank as its own field keeps the sort a plain two-key
        # `sort` rather than a hand-rolled comparison, and keeps the verdict
        # itself (field 3) untouched by anything the display does.
        entries+=("${STATUS_RANK[$verdict]}"$'\t'"${name}"$'\t'"${verdict}"$'\t'"$(printf '%.72s' "$detail")")
        n_seen=$((n_seen + 1))
    done <"$_RUN_TXT"

    if (( n_seen == 0 )); then
        record 2 "Parse coverage" "zero check verdicts parsed from verify.py output (rc=${_RUN_RC}) — refusing to report healthy on nothing"
        return 1
    fi

    # Duplicate-name guard: two entries sharing a name after normalization
    # would silently merge in review — surface it rather than hide it.
    local dupes
    dupes="$(printf '%s\n' "${entries[@]}" | cut -f2 | LC_ALL=C sort | uniq -d)"
    if [[ -n "$dupes" ]]; then
        record 1 "Parse coverage" "duplicate check name(s) after normalization: $(tr '\n' ',' <<<"$dupes" | sed 's/,$//') — names may be colliding"
    fi

    # PASS, then FAIL, then WARNING (-k1,1n on the rank), and ALPHABETICAL
    # within each group (-k2,2 on the name). The secondary key is what keeps two
    # runs over an unchanged tree byte-identical — v1.0.0's reason for sorting at
    # all, kept intact and demoted rather than dropped.
    local sorted_line erank ename everdict eline
    while IFS= read -r sorted_line; do
        [[ -z "$sorted_line" ]] && continue
        # shellcheck disable=SC2034  # `erank` exists to CONSUME field 1, the
        # sort key. Reading into `_` would work and would hide which field it
        # is, which is the thing a later reader needs to know.
        IFS=$'\t' read -r erank ename everdict eline <<<"$sorted_line"
        record "$everdict" "$ename" "$eline"
    done < <(printf '%s\n' "${entries[@]}" | LC_ALL=C sort -t $'\t' -k1,1n -k2,2)

    # Reconcile verify.py's exit code against what we parsed, using verify.py's
    # DOCUMENTED mapping (nix_check_contract.md §4.2 as amended by CHECK-A1):
    #   0 pass · 1 fail · 2 cannot-measure/skipped · 3 guarded
    # v1.0.0 treated any non-zero rc as a disagreement, which painted every
    # legitimately degraded run — rc=2 with a cannot-measure, rc=3 with a
    # guarded check — as FAILED. An unknown rc still fails closed and loud.
    local rc_status
    case "$_RUN_RC" in
        0) rc_status=0 ;;
        1) rc_status=2 ;;
        2) rc_status=1 ;;
        3) rc_status=1 ;;
        *) rc_status=2 ;;
    esac
    if (( rc_status != WORST_STATUS )); then
        local worse=$rc_status
        (( WORST_STATUS > worse )) && worse=$WORST_STATUS
        record "$worse" "verify.py exit code" \
            "rc=${_RUN_RC} implies ${STATUS_WORD[$rc_status]}, parsed verdicts reached ${STATUS_WORD[$WORST_STATUS]} — reported at the worse of the two"
    fi
    return 0
}

# ─── ORCHESTRATION ──────────────────────────────────────────────────
run_all_checks() {
    WORST_STATUS=0
    RESULTS=()
    _TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/nix_status.XXXXXX")"

    if check_verify_binary && check_python && check_verify_only_flag; then
        check_verify_run
    fi

    rm -rf "$_TMPDIR" 2>/dev/null
}

# The SSH splash, EXECUTED rather than transcribed.
#
# The banner at /etc/update-motd.d/99-nix-banner already owns the NIX logo, the
# host identity, the uptime, the CME session clock and the utilisation bars, and
# it is regenerated per login. Copying its artwork in here would mean two
# renderers of one set of facts, drifting apart with nobody watching — the same
# "never restate a mutable fact" rule this script already obeys by refusing to
# reimplement verify.py's checks.
#
# It is deliberately NOT allowed to break the dashboard. It runs read-only in a
# subshell with a hard timeout, its exit status is ignored, and a failure or an
# absence produces one dim line SAYING SO. A splash that silently rendered
# nothing would leave an operator unsure whether the header was suppressed,
# broken, or never configured.
SPLASH_RENDERED=0
render_splash() {
    SPLASH_RENDERED=0
    (( SPLASH == 1 )) || return 0
    if [[ ! -x "$SPLASH_SCRIPT" ]]; then
        echo -e "  ${DIM}(splash: ${SPLASH_SCRIPT} not present or not executable — header skipped)${RESET}"
        return 0
    fi
    local out rc=0
    out="$(timeout -k 2 "${SPLASH_TIMEOUT_S}" "$SPLASH_SCRIPT" 2>/dev/null)" || rc=$?
    if [[ -z "${out//[[:space:]]/}" ]]; then
        echo -e "  ${DIM}(splash: ${SPLASH_SCRIPT} produced no output (rc=${rc}) — header skipped)${RESET}"
        return 0
    fi
    # --no-color empties RESET; that is the signal to strip the banner's own
    # escapes too, or the flag would be honoured by this script and ignored by
    # the thing it embeds.
    SPLASH_RENDERED=1
    if [[ -z "$RESET" ]]; then
        strip_ansi <<<"$out"
    else
        printf '%s\n' "$out"
    fi
}

render_full() {
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    # The splash owns the blank line that separates it from the status block, so
    # suppressing it leaves one blank line here rather than two.
    render_splash && [[ "$SPLASH_RENDERED" == "1" ]] && echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════════════════${RESET}"
    echo -e "${BOLD}  NIX — STATUS  ${DIM}${ts}${RESET}"
    echo -e "${BOLD}═══════════════════════════════════════════════════════════${RESET}"
    echo ""
    for line in "${RESULTS[@]}"; do
        echo -e "$line"
    done
    echo ""
    echo -e "${BOLD}───────────────────────────────────────────────────────────${RESET}"
    echo -e "  ${BOLD}SUMMARY${RESET}"
    # Counted in record(), as each bubble was appended — never recomputed here.
    # A second pass over the rendered strings would be a second derivation of one
    # fact, and the tally could then disagree with the list directly above it.
    local total=$(( STATUS_COUNT[0] + STATUS_COUNT[1] + STATUS_COUNT[2] ))
    printf '    %b●%b  %-9s %3d\n' "$GREEN"  "$RESET" "PASS"    "${STATUS_COUNT[0]}"
    printf '    %b●%b  %-9s %3d\n' "$RED"    "$RESET" "FAIL"    "${STATUS_COUNT[2]}"
    printf '    %b●%b  %-9s %3d\n' "$YELLOW" "$RESET" "WARNING" "${STATUS_COUNT[1]}"
    printf '       %-9s %3d\n' "TOTAL" "$total"
    echo ""
    case "$WORST_STATUS" in
        0) echo -e "  ${GREEN}●${RESET}  ${BOLD}OVERALL:  HEALTHY${RESET}" ;;
        1) echo -e "  ${YELLOW}●${RESET}  ${BOLD}OVERALL:  DEGRADED${RESET}  ${DIM}(cannot-measure/known-red — investigate)${RESET}" ;;
        2) echo -e "  ${RED}●${RESET}  ${BOLD}OVERALL:  FAILED${RESET}  ${DIM}(red flags — take action)${RESET}" ;;
    esac
    echo ""
}

render_brief() {
    local bubble label
    case "$WORST_STATUS" in
        0) bubble="${GREEN}●${RESET}"; label="HEALTHY" ;;
        1) bubble="${YELLOW}●${RESET}"; label="DEGRADED" ;;
        2) bubble="${RED}●${RESET}"; label="FAILED" ;;
    esac
    echo -e "NIX ${bubble} ${label}"
}

# ─── MAIN ───────────────────────────────────────────────────────────
if (( WATCH == 1 )); then
    trap 'tput cnorm 2>/dev/null; echo ""; exit 0' INT TERM
    tput civis 2>/dev/null
    while true; do
        clear
        run_all_checks
        render_full
        echo -e "  ${DIM}refreshing every ${WATCH_INTERVAL}s — Ctrl+C to exit${RESET}"
        sleep "$WATCH_INTERVAL"
    done
else
    run_all_checks
    if (( BRIEF == 1 )); then
        render_brief
    else
        render_full
    fi
    exit "$WORST_STATUS"
fi
