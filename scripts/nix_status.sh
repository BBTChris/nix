#!/usr/bin/env bash
# Name:     nix_status.sh
# Version:  1.3.0
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
# Live output (v1.3.0):
#     Verdicts are printed AS THEY LAND, under the banner, in the order the
#     checks actually completed:
#         ●   12/30  check_ibgateway_service        4.10s
#     The grouped/sorted dashboard and the SUMMARY still follow at the end. The
#     durations are verify.py's own per-check measurements (engine._timed,
#     perf_counter), never re-derived here; this script recolours them and adds
#     nothing to them.
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
#   v1.3.0  2026-08-12  LIVE OUTPUT. Every verdict now reaches the screen the
#                         moment it is reached, instead of the whole dashboard
#                         appearing after the last check.
#                         The old behaviour was not a rendering choice, it was
#                         verify.py's shape: `main()` ran every block and only
#                         then printed, so a wrapper capturing its output had
#                         nothing to show until the run ended. Measured on this
#                         tree that is ~70s of blank screen, one check alone
#                         accounting for 36s of it.
#                         Three changes, in dependency order:
#                         (1) verify.py grew `--stream` (render.StreamProgress):
#                         one flushed line per verdict, `>>`-prefixed, carrying
#                         the check's name, the registry-derived n/total counter
#                         and the duration the ENGINE measured. It ADDS output —
#                         the end-of-run registry-order block (§6) still prints
#                         unchanged, so nothing that parsed verify.py before
#                         parses differently now.
#                         (2) The banner and the header box are printed BEFORE
#                         the run rather than after it. A header rendered after
#                         the body is not a header, and with live output there
#                         is now a body to head.
#                         (3) This script reads verify.py through a FIFO rather
#                         than a temp file, repainting each `>>` line as a
#                         bubble as it arrives, and echoes its own four wrapper
#                         verdicts as they are recorded. The grouped, sorted
#                         dashboard and the SUMMARY still print at the end, and
#                         are still derived from verify.py's own end block — so
#                         v1.2.0's grouping, its alphabetical secondary key, the
#                         byte-identical re-run property, the duplicate-name
#                         guard and the exit-code reconciliation are all
#                         untouched by the live path.
#                         `--stream` is PROVEN in `verify.py --help` before it
#                         is passed, exactly as the verify-only invocation is
#                         (check 3's doctrine, applied to the second flag). A
#                         verify.py without it degrades to v1.2.0 behaviour and
#                         SAYS so in one line, rather than silently showing
#                         nothing for a minute.
#                         (4) WARNING AND ERROR TEXT IS NEON ORANGE (#FF6600,
#                         the banner's own accent). It was `${DIM}` and nothing
#                         else — and `\033[2m` sets faintness, not colour, so
#                         the text wore the terminal's default foreground. On a
#                         green-on-black profile that made every failure detail
#                         FAINT GREEN: the hardest text on screen to read, in
#                         the colour that means "fine". Verdict bubbles were
#                         always explicit; the messages were not, and inherited
#                         text is unreadable on precisely the profiles nobody
#                         tested. Passes stay dim — a reassurance nobody needs
#                         to read should not compete with a failure that must be.
#                         The orange is TIERED, and that is a fix for the first
#                         attempt at this fix. Written as a bare 24-bit SGR it
#                         made every warning and error message VANISH on this
#                         node's own terminal — TERM=xterm-256color, COLORTERM
#                         unset, no RGB in terminfo, i.e. a 256-colour terminal
#                         that does not parse a truecolor sequence and swallowed
#                         the text behind it. The bytes were there the whole
#                         time; nothing could paint them. Same fault as the
#                         faint green, one costume along: legibility resting on
#                         an untested property of the terminal. The tier is now
#                         derived (COLORTERM, then `tput colors`) with real
#                         fallbacks — #FF6600, xterm-256 208, or bright 93 —
#                         never a degradation to nothing. Force one with
#                         NIX_STATUS_COLOR_TIER where the advertisement lies.
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

# Neon orange — #FF6600, the same value the MOTD banner uses for its own accent
# (`C_PINK`, /etc/update-motd.d/99-nix-banner). Warning and error MESSAGE TEXT is
# painted with it.
#
# THREE TIERS, DETECTED, because the 24-bit form is not universally safe and this
# was measured the hard way. Written first as a bare `\033[1;38;2;255;102;0m`, it
# made every warning and error message VANISH on this node's own terminal:
# `TERM=xterm-256color`, `COLORTERM` unset, no `RGB`/`setrgbf` in terminfo — a
# 256-colour terminal, which does not parse a truecolor SGR and swallowed the
# text that followed it. The bytes were present the whole time (`cat -v` showed
# them); nothing could paint them.
#
# That is the same fault as the faint green one directory up in this comment, in
# a new costume: text whose legibility depends on an untested property of the
# terminal. So the tier is DERIVED from what the terminal advertises —
# `COLORTERM` first, `tput colors` second — and the fallbacks are real colours
# rather than a silent degradation to nothing. `NIX_STATUS_COLOR_TIER` forces one
# where the advertisement is wrong in either direction.
#
# What it replaces, and why the old rendering was a real defect rather than a
# taste question: detail text was printed as `${DIM}` and NOTHING ELSE. `\033[2m`
# sets faintness, not a colour, so the text came out in the terminal's default
# foreground — which on this operator's profile is green. The dimmed detail of a
# FAIL therefore rendered as FAINT GREEN: the least legible colour on the screen
# carrying the most urgent text, in the one hue that reads as "fine".
#
# The general fault is inheritance. A line that says something is broken must
# state its own colour, or it wears whichever palette the terminal happened to
# be holding — and the message is unreadable on exactly the profiles nobody
# tested. Verdict colours were always explicit; the message text was not.
case "${NIX_STATUS_COLOR_TIER:-auto}" in
    truecolor) ORANGE="\033[1;38;2;255;102;0m" ;;   # #FF6600 exactly
    256)       ORANGE="\033[1;38;5;208m" ;;         # xterm-256 nearest neon orange
    16)        ORANGE="\033[1;93m" ;;               # bright yellow/orange, 16-colour safe
    *)
        _tput_colors="$(tput colors 2>/dev/null || echo 0)"
        [[ "$_tput_colors" =~ ^[0-9]+$ ]] || _tput_colors=0
        if [[ "${COLORTERM:-}" == "truecolor" || "${COLORTERM:-}" == "24bit" ]]; then
            ORANGE="\033[1;38;2;255;102;0m"
        elif (( _tput_colors >= 256 )); then
            ORANGE="\033[1;38;5;208m"
        else
            ORANGE="\033[1;93m"
        fi
        unset _tput_colors
        ;;
esac

# ─── ARG PARSING ────────────────────────────────────────────────────
WATCH=0
WATCH_INTERVAL=5
BRIEF=0
# Live output. Default ON; NIX_STATUS_LIVE=0 or --no-live turns it off and
# restores v1.2.0's behaviour exactly (silence during the run, everything at the
# end). --brief forces it off further down: a single-line summary exists to be
# grepped, and thirty progress lines above it would defeat that.
LIVE=${NIX_STATUS_LIVE:-1}
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
            BOLD=""; DIM=""; RED=""; YELLOW=""; GREEN=""; RESET=""; ORANGE=""
            shift
            ;;
        --no-splash)
            SPLASH=0
            shift
            ;;
        --no-live)
            LIVE=0
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
nix_status.sh v1.3.0 — verify.py verify-only wrapper + health dashboard

Usage:
    bash nix_status.sh              Snapshot, exit
    bash nix_status.sh --watch      Refresh every 5s until Ctrl+C
    bash nix_status.sh -w 10        Refresh every 10s (min 1)
    bash nix_status.sh --brief      Single-line summary
    bash nix_status.sh --no-color   Strip ANSI
    bash nix_status.sh --no-splash  Skip the SSH splash header
    bash nix_status.sh --no-live    Don't print verdicts as they land
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
    NIX_STATUS_LIVE          0 = never print verdicts as they land
    NIX_STATUS_COLOR_TIER    auto (default) | truecolor | 256 | 16 — which
                             orange is emitted for warning/error text
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
(( BRIEF == 1 )) && LIVE=0

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

# Live echo. While this is 1, `record` prints the bubble it just appended as
# well as banking it — so the four wrapper verdicts appear as they are reached
# rather than after verify.py's run.
#
# It is turned OFF before `parse_and_record_checks`, and that is the whole
# subtlety of the live path: those bubbles were ALREADY shown live, streamed
# from verify.py as each check finished. Leaving the echo on would print the
# same thirty verdicts a second time, and the second copy would be the sorted
# one — which reads as a second, disagreeing run rather than a recap.
LIVE_ECHO=0

record() {
    local st="$1" label="$2" detail="$3" bubble msg
    # The BUBBLE keeps the three-colour verdict language (green/yellow/red) —
    # that is the thing an operator scans. The MESSAGE is what changed: dim for a
    # pass, where the text is a reassurance nobody needs to read, and neon orange
    # for a warning or a failure, where the text is the entire point of the line.
    case "$st" in
        0) bubble="${GREEN}●${RESET}";  msg="${DIM}${detail}${RESET}" ;;
        1) bubble="${YELLOW}●${RESET}"; msg="${ORANGE}${detail}${RESET}" ;;
        2) bubble="${RED}●${RESET}";    msg="${ORANGE}${detail}${RESET}" ;;
    esac
    local label_fmt
    label_fmt="$(printf '%-28s' "$label")"
    RESULTS+=("  ${bubble}  ${BOLD}${label_fmt}${RESET}  ${msg}")
    (( LIVE_ECHO == 1 )) && echo -e "${RESULTS[-1]}"
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
_STREAM_ARGV=()     # `--stream`, only once PROVEN present in --help
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

    # The live-output flag is DERIVED from the same --help text, on the same
    # terms as the verify-only invocation below: proven present or not passed.
    # An assumed `--stream` would make verify.py exit 2 on an unknown argument
    # and this script would report the node as unmeasurable — a wrapper's guess
    # about its instrument masquerading as a verdict about the machine.
    #
    # Its absence is not a failure of anything. It costs the live rendering and
    # nothing else, so it says so in one dim line and the run proceeds.
    if (( LIVE == 1 )); then
        if grep -qw -- '--stream' <<<"$help_plain"; then
            _STREAM_ARGV=(--stream)
        else
            echo -e "  ${ORANGE}(live: this verify.py has no --stream — verdicts will appear together when the run ends)${RESET}"
        fi
    fi

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

# Repaints one streamed verdict as a bubble, the moment it arrives.
#
# The line is verify.py's, and every FACT on it is verify.py's: the status
# marker, the check name, the n/total counter (derived from its registry) and
# the duration (measured by its engine with perf_counter). This function maps
# the marker to a colour and re-columnises. It computes no timing of its own —
# a second stopwatch here would be a second authority on the same number, and
# the two would disagree the moment either changed.
#
# Anything that is not a `>>` line is verify.py's ordinary output (the
# end-of-run block, warnings, tracebacks) and is banked to `_RUN_TXT` for the
# real parse without being painted twice.
render_live_line() {
    local plain sentinel marker name counter dur bubble
    plain="$(strip_ansi <<<"$1")"
    read -r sentinel marker name counter dur _ <<<"$plain"
    [[ "$sentinel" == ">>" ]] || return 0
    local text
    case "$marker" in
        '[ok]'|'✔')   bubble="${GREEN}●${RESET}";  text="${DIM}" ;;
        '[FAIL]'|'✖') bubble="${RED}●${RESET}";    text="${ORANGE}" ;;
        '[??]'|'⚠'|'[--]'|'·'|'[GRD]'|'◐') bubble="${YELLOW}●${RESET}"; text="${ORANGE}" ;;
        *) return 0 ;;
    esac
    # Same rule as `record`: a live line that is not a pass names its own colour
    # rather than inheriting the terminal's.
    printf '  %b  %b%7s  %-30s %8s%b\n' "$bubble" "$text" "$counter" "$name" "$dur" "$RESET"
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

    if (( LIVE == 1 && ${#_STREAM_ARGV[@]} > 0 )); then
        # Read verify.py through a FIFO rather than a file, so every line can be
        # acted on the instant it is written while the complete output still
        # lands in `_RUN_TXT` for the end-of-run parse. Both consumers see every
        # byte; neither waits for the other.
        #
        # The rc goes through a FILE, not a pipeline. `cmd | while read` would
        # put the loop in a subshell and lose both the exit status and every
        # variable the loop set — the classic bash trap, and here it would cost
        # the exit-code reconciliation that decides the overall verdict.
        local fifo="${_TMPDIR}/stream.fifo" rcf="${_TMPDIR}/rc"
        mkfifo "$fifo" 2>/dev/null || {
            record 2 "verify.py run" "cannot create FIFO in ${_TMPDIR}"
            return 1
        }
        (
            timeout -k 10 "$TIMEOUT_S" "$_PYBIN" "$VERIFY_PY" \
                "${_VERIFY_ARGV[@]}" "${_STREAM_ARGV[@]}" </dev/null >"$fifo" 2>&1
            echo $? >"$rcf"
        ) &
        local raw
        while IFS= read -r raw; do
            printf '%s\n' "$raw" >>"$_RUN_TXT"
            render_live_line "$raw"
        done <"$fifo"
        wait
        # A missing rc file means the subshell died before it could write one —
        # unmeasurable, not zero. Failing closed here matters: an rc silently
        # defaulted to 0 would reconcile as "healthy" against whatever was
        # parsed.
        rc="$(cat "$rcf" 2>/dev/null)"
        [[ "$rc" =~ ^[0-9]+$ ]] || rc=2
    else
        timeout -k 10 "$TIMEOUT_S" "$_PYBIN" "$VERIFY_PY" "${_VERIFY_ARGV[@]}" \
            </dev/null >"$_RUN_TXT" 2>&1 || rc=$?
    fi

    end=$(date -u +%s)
    elapsed=$(( end - start ))
    _RUN_RC="$rc"

    [[ -n "$RAW_OUT" ]] && cp -f "$_RUN_TXT" "$RAW_OUT" 2>/dev/null

    if [[ $rc -eq 124 || $rc -eq 137 ]]; then
        record 2 "verify.py run" "exceeded ${TIMEOUT_S}s and was killed (rc=$rc) — no verdict"
        return 1
    fi

    record 0 "verify.py run" "${VERIFY_PY} ${_VERIFY_ARGV[*]} — ${elapsed}s, rc=${rc}"

    # Everything below was already on screen, live. The grouped dashboard is a
    # recap, not a second announcement — see LIVE_ECHO's note.
    LIVE_ECHO=0
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
    STATUS_COUNT=([0]=0 [1]=0 [2]=0)
    _STREAM_ARGV=()
    # Live from the first wrapper verdict, not merely from verify.py's first
    # check: checks 1-3 are the ones that decide whether verify.py runs at all,
    # so on a broken node they are the ONLY verdicts there will ever be. Holding
    # them back until the end would keep the screen blank in exactly the case
    # where something is already known to be wrong.
    LIVE_ECHO=$LIVE
    _TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/nix_status.XXXXXX")"

    if check_verify_binary && check_python && check_verify_only_flag; then
        check_verify_run
    fi

    LIVE_ECHO=0
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
        echo -e "  ${ORANGE}(splash: ${SPLASH_SCRIPT} not present or not executable — header skipped)${RESET}"
        return 0
    fi
    local out rc=0
    out="$(timeout -k 2 "${SPLASH_TIMEOUT_S}" "$SPLASH_SCRIPT" 2>/dev/null)" || rc=$?
    if [[ -z "${out//[[:space:]]/}" ]]; then
        echo -e "  ${ORANGE}(splash: ${SPLASH_SCRIPT} produced no output (rc=${rc}) — header skipped)${RESET}"
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

# The banner and the header box, printed BEFORE the checks run.
#
# v1.2.0 rendered these at the end, with everything else, because there was
# nothing to head — the screen stayed empty until the run finished and then
# filled in one motion. With live verdicts there IS a body, and a header printed
# after its body is not a header. Its timestamp is now the run's START, which is
# also the more useful of the two: it is the time the measurements were taken
# from, not the time the last one happened to return.
render_header() {
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
}

# The grouped dashboard and the tally, printed after the run.
#
# Under live output this is a RECAP: every verdict in it has already been on
# screen once, in completion order. It earns its place by being the sorted,
# grouped view — PASS/FAIL/WARNING, alphabetical within each group — which
# completion order cannot give and which is what makes two runs over an
# unchanged tree comparable line by line.
render_body() {
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
    # Same rule as everywhere else: the two words that report trouble state their
    # own colour. HEALTHY stays unpainted — it is the only one that may safely
    # look like whatever the terminal looks like.
    case "$WORST_STATUS" in
        0) bubble="${GREEN}●${RESET}"; label="HEALTHY" ;;
        1) bubble="${YELLOW}●${RESET}"; label="${ORANGE}DEGRADED${RESET}" ;;
        2) bubble="${RED}●${RESET}"; label="${ORANGE}FAILED${RESET}" ;;
    esac
    echo -e "NIX ${bubble} ${label}"
}

# ─── MAIN ───────────────────────────────────────────────────────────
if (( WATCH == 1 )); then
    # The cursor is hidden for the WHOLE cycle, live output included. It is a
    # scrolling log now rather than an in-place repaint, and a block cursor
    # trailing each line as it lands is the one thing that would make it read as
    # an editor rather than a report.
    trap 'tput cnorm 2>/dev/null; echo ""; exit 0' INT TERM
    tput civis 2>/dev/null
    while true; do
        clear
        render_header
        run_all_checks
        render_body
        echo -e "  ${DIM}refreshing every ${WATCH_INTERVAL}s — Ctrl+C to exit${RESET}"
        sleep "$WATCH_INTERVAL"
    done
else
    if (( BRIEF == 1 )); then
        # Nothing is printed before the summary line. `LIVE` is already 0 here,
        # so the run is silent and the single line is the entire output — which
        # is the only reason --brief exists.
        run_all_checks
        render_brief
    else
        render_header
        run_all_checks
        render_body
    fi
    exit "$WORST_STATUS"
fi
