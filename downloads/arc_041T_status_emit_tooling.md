# ARC 041-T — STATUS-EMIT TOOLING: heartbeat script + status-contract gate + CLAUDE.md

**Tier: TOOLING (dev/CI).** Not a Limiter slice. Touches NO invariant, NO trading-path code, does
NOT move the Limiter badge. Runs **between Limiter slices** — after ARC 041 banks, before ARC 042.
**Canonical path `/home/bbt/nix`.** Interpreter `/home/bbt/nix/.venv/bin/python` (3.14.4).
**Model: Sonnet 5** (install + wire + verify; no concurrency/authority reasoning).

## Why

cc keeps reconstructing the heartbeat format from priors on long runs (context compaction drops the
exact spec), producing a 65-line banner per beat and burying the compact ticker. Fix: move the format
out of memory and into code cc **calls**, and add a gate that **measures** that the operator was kept
informed and the watchdog was torn down. Also discharge the standing CHECK-DEBT candidate from 039R:
nothing measures tmpfs inode headroom, so a run dies confusingly ("No space left" with 16 GB free)
when /tmp runs out of inodes. Four drop-ins, all pre-validated in a real interpreter — do not rewrite
them, install and wire them.

## Files (provided, validated — install verbatim)

1. **`scripts/arc_heartbeat.sh`** (chmod +x) — the single source of truth for the pulse/banner
   format. Subcommands `pulse` (one line), `banner` (boxed, stage transitions only), `selfcheck`
   (kickoff self-verify). Reads `$NIX_SCRATCH/arc_progress.txt`; derives HEAD live; tracks
   motion/stall; ASCII rules; `[watchdogd]`-safe teardown wording. Already unit-exercised across
   healthy / no-motion / stall / stale / empty-field / banner / selfcheck pathways.
2. **`checks/check_arc_status_contract.py`** — verify.py gate. Audits an arc log: FAILS on missing
   heartbeat/self-verify evidence OR a cc watchdog left alive after the completion marker; CANNOT-
   MEASURE if the log never reached close-out (non-vacuous). Derives arc id + watchdog pid from the
   log (no literal anchor). Ships a `--selftest` (7 cases incl. two `[watchdogd]` false-positive
   guards) — its demonstrated FAIL is built in.
3. **`checks/check_tmpfs_inode_headroom.py`** — verify.py gate. `df -i` on `/tmp`; FAILS when inode
   use >= ceiling (default 90%) OR free inodes < floor (default 20000); CANNOT-MEASURE on a mount
   with no inode limit ('-') or unparseable df. Derives the invariant (headroom %), never a
   snapshotted total (rule 5). Ships a `--selftest` (8 cases incl. the exact 039R exhausted state ->
   FAIL, boundary at the ceiling, df line-wrap, and non-vacuity that the parser extracts a real usage
   before any FAIL is trusted).
4. **`CLAUDE.md` STATUS EMIT block** — append verbatim under the Status Contract section.

## Steps

1. **Drop the two files** at the paths above; `chmod +x scripts/arc_heartbeat.sh`.
2. **BIND the gate from its own FAIL:** run `python check_arc_status_contract.py --selftest` — must
   print `SELF-TEST PASS` and exit 0. This is the demonstrated-FAIL evidence (rule 3); do not
   construct an exit code.
3. **Prove emitter↔reader parity (the second-implementation trap):** produce a real pulse via
   `scripts/arc_heartbeat.sh selfcheck` into a scratch log, add a marker + a
   `WATCHDOG TEARDOWN: confirmed dead (... / arc_heartbeat)` line, and run the gate `--log` against
   it — must PASS with `pulses>=1`. If the gate's `RE_PULSE` does not match the script's real
   output, they silently disagree; catch it here, not in production.
4. **Register `check_arc_status_contract`** in the `checks` JSON execution map. **Read
   `VERIFY-AND-CHECKS.md` directly** and decide its invocation per that contract: default `--log` to
   the latest arc session log; when no fresh completed-arc log exists, it returns **CANNOT-MEASURE
   (exit 2)**, not FAIL — confirm whether it belongs in the periodic sweep or is close-out-invoked.
   **Expect verify's cannot-measure count may tick up in the bare periodic sweep** (no fresh arc log)
   while it PASSES at an arc's close-out against that arc's real log. State which you wired.
4b. **BIND + register `check_tmpfs_inode_headroom`:** run `--selftest` (must print SELF-TEST PASS,
   exit 0 — its demonstrated FAIL is the 039R exhausted-inode plant), then a live
   `check_tmpfs_inode_headroom.py --mount /tmp` on node02 (expect PASS after the kickoff basetemp
   clean). Register it in the checks map as a PERIODIC gate (it measures live node state every sweep,
   unlike the arc-log gate). It should add one PASS to the periodic count on a healthy box.
5. **Append the CLAUDE.md block** verbatim.
6. **Rewire the standing arc prompt** (record in CLAUDE.md): kickoff calls `arc_heartbeat.sh
   selfcheck`; the watchdog beat and every in-stage pulse call `arc_heartbeat.sh pulse`; stage
   transitions call `arc_heartbeat.sh banner`. cc no longer hand-formats a beat.
7. **Close-out (TOOLING tier):** `verify.py` on trunk (state the full 5-tuple and how it moved — two
   gates added: `check_tmpfs_inode_headroom` should add +1 PASS periodic; `check_arc_status_contract`
   may add +1 cannot-measure in the bare sweep, per step 4). Both gates' `--selftest` green; the
   emitter↔reader parity check green. No full pytest / census — this touches no trading-path code and
   no invariant. **Reconcile CHECK-DEBT: the 039R `check_tmpfs_inode_headroom` candidate is now
   DISCHARGED** (name it in the series). Append a short SESSION.md note; overwrite RESULTS.md; `cat`
   both; then `**** ARC completed ****`.

## Standing obligations

Stage banners + one-line pulses via the new script (dogfood it on this very run — this arc's own
heartbeats must come from `arc_heartbeat.sh`). Verified watchdog teardown before the marker, matched
by cc's own signature, ignoring `[watchdogd]`. Never `pkill -f`/`pgrep -af` on cc's own patterns.

## Not in scope

No Limiter code, no invariant, no badge change. I8 / D3.425 remain ARC 042. This is tooling that
makes the *next* arcs observable and measured; it is deliberately small.
