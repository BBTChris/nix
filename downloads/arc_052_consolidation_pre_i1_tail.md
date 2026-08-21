# ARC 052 — CONSOLIDATION / pre-pay before the I1 tail (no invariant flip)

**Tier: TOOLING / PREP.** **This arc DISCHARGES NO INVARIANT. The count STAYS 11/12. No board
redraw.** Its job is to pay the known taxes and clear the accumulated debt so the four I1 daemon arcs
(A/B/C/D) run clean. Limiter badge STAYS RED.
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `6d26c2f` (approximate — ARC 051's write-back commit).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT.
**Model: Sonnet 5** (default — this is mechanical prep, not concurrency/absence/authority reasoning;
the I1 tail A–D returns to **Opus 5**). Escalate only if the D3.104 resolution turns out to need
authority reasoning.

## Why this arc exists (memory #21: pre-pay known taxes before the work that triggers them)

The I1 tail touches `limiterd.py` and its sibling daemon files on all four arcs. Left unprepared,
each can re-hit the ~44-min commit escalation (the 046 saga) and each inherits debt that is now a
ceiling being walked, not held. One focused arc pays it all down so the capstone is a build, not a
fight. **Nothing here changes any invariant subject — every invariant file stays byte-identical.**

## KICKOFF OBLIGATIONS (before the tasks)

1. **Framing.** Echo `TIER = TOOLING/PREP`, `NO INVARIANT FLIP`, `count stays 11/12`. Derive the
   clean set to confirm: `{I2, I3, I4, I5, I6, I7, I8, I9, I10, I11, I12} = 11/12`, open = 1 (I1).
2. **Process + ops lessons (memory #19/#20/#22/#23):** MEASURE the predecessor tip with `verify.py`
   FIRST (record the real baseline — 051 closed `92|4|3|0|1`, and note the `check_arc_status_contract`
   cannot-measure on `arc_051.log`'s predecessor is exactly what Task 3 fixes). Scope lint-fix to
   CHANGED files, never `ruff … .`. `--basetemp` OUTSIDE `~/nix` (`/var/tmp/arc052_pt`, D3.462).
   Run `test_check_order_path_bans` + `test_check_uncalled_entry_points` explicitly. `arc_heartbeat.sh`
   from the start, tee'd to `arc_052.log`, progress file one `key=value` per line. inode gate +
   basetemp clean; scratch DBs at teardown; kill by PID, never `pkill -f`.

## TASK 1 (PRIMARY) — testmon-cover the I1 daemon files, and PROVE the tax is paid

The one that matters most. Do NOT let the others crowd it out.
1. **Enumerate the daemon files the I1 tail will touch** — derive from the tail plan: `limiterd.py`
   (covered by S4.4/046), `completions.py` (touched by 047 — confirm covered), and any sibling the
   dispatch mechanism spans (the fill/completion seam files, a new dispatch/parse helper if one is
   planned). List them explicitly.
2. **Check each against the testmon fingerprint** (`.testmondata` `file_fp`). For any file NOT in the
   fingerprint, add a **minimal coverage test** (the S4.4 pattern — a test that imports and lightly
   exercises the module so it enters the fingerprint). The coverage need only break the escalation;
   the tail arcs add real behavioural coverage via their own dispatch tests.
3. **PROVE it worked — this is the deliverable, not the test files.** For each daemon file, make a
   trivial whitespace/no-op change, `git commit` it, and **measure the commit wall-time** — it must
   take the INCREMENTAL path (~seconds), not the ~44-min full-suite escalation. Revert the no-op
   commits (or fold into one throwaway that's then reset). Report the measured before/after: "a
   commit touching `<file>` was Nmin, is now Nsec." If any daemon file still escalates after the
   coverage test, the pre-pay FAILED for that file — say so, don't claim it paid.

## TASK 2 (bounded) — pay down D3.104: the 8 gate_coverage exclusions

The `check_artifact_gate_coverage` guard's 8 exclusions have been re-pointed SIX consecutive arcs.
That is a ceiling walked, not a debt held. For **each** of the 8:
* **Resolve it** — gate the artifact properly (so it no longer needs excluding), OR remove it if
  obsolete, OR give it a **PERMANENT documented disposition** (a stable exclusion with a written
  reason and a known-red marker naming the specific future arc that will gate it, per check-contract
  rule 7) — NOT another per-arc re-point.
* The goal: after this arc, `check_artifact_gate_coverage` is either PASS, or GUARDED with a
  **stable** exclusion set that does not require re-pointing next arc.
* If some genuinely cannot be resolved until the I1 tail builds their subject, mark those with the
  specific arc (ARC A/B/C/D) and reason — a named future gate, not a floating re-point.
* **Do not** resolve an exclusion by weakening a gate or hiding a real gap. A resolution that greens
  the guard by measuring less is the failure mode; state what each resolution now measures.

## TASK 3 (bounded) — fix D3.464: the marker-tee gap (Claude's status tooling)

`check_arc_status_contract` reads CANNOT-MEASURE on the previous arc's log when the
`**** ARC completed ****` marker was printed to chat but never written to `arc_NNN.log`. Fix the
ROOT: the completion marker must be **written to `arc_NNN.log` (tee'd) as part of the teardown
sequence**, not only echoed — so a completed arc's log always carries its marker.
* Patch `arc_heartbeat.sh` (the teardown path) and/or the run protocol so the marker lands in the log
  file, positioned per §16.4 (marker last token to the operator, but present in the log).
* **Demonstrated FAIL / fix proof:** a completed-arc log WITHOUT the marker ⇒ gate CANNOT-MEASURE
  naming the missing marker (unchanged — that half is correct); a completed-arc log WITH the marker
  (produced by the fixed teardown) ⇒ gate PASS naming the arc. Show both.
* This does not retroactively repair `arc_050.log`/`arc_051.log` (banked, directive 6) — it makes
  every FUTURE arc's marker land, so the one-arc-lag cannot-measure stops recurring from ARC 052 on.

## TASK 4 (report only, no code) — ARC C flatten-producer reconnaissance

Produce a short recon report (a doc, `~/nix/downloads/arc_c_flatten_recon.md`) so the architect can
write ARC C as a build, not a design-and-build. Survey and report — DO NOT wire:
* **D3.453 (STALE_PRICE producer):** where `freshness.py`'s stale determination lives, and the exact
  seam where it would trigger a protective flatten of an already-open position (§6.4's flatten-open
  half). What exists vs what ARC C must build.
* **D3.372 (not-tradable confirmed fill):** the `UntradableSymbol`/§4:198 site (from 047), and where
  an UNCERTAINTY protective-flatten trigger + its consumer would hook (the architect ruling: flatten,
  don't publish; root fix = deny-at-approval).
* For each: the exact modules/functions, what's already present (the flatten machinery I3 proved
  wire-free, the OrderRole/trigger vocabulary from 045), and an estimated ARC C build scope.
* Also note the **D3.463 signal_ts** fix belongs to ARC A (reject-a-stale-GO + kill the
  `or time.time()` fallback) — confirm the `limiterd.py:1168` site and the GO ingress path for ARC A.

## FREEZE — assert against the derived tip

Diff shows only: the new minimal coverage test(s) (Task 1), the `check_artifact_gate_coverage`
resolution + `gate_coverage_baseline.json` (Task 2), `arc_heartbeat.sh` / `check_arc_status_contract`
+ its test (Task 3), `docs/CHECK-DEBT.md`, and `downloads/arc_c_flatten_recon.md` (Task 4).
**Byte-identical (prove with `git hash-object`) — EVERY invariant subject:** the fill path, the exit
path (`flatten.py`), the two-phase state (`positions.py`/`projection.py`), the hot-path files
(`loop.py`/`wal.py`), the freshness files (`freshness.py`/`gate.py`), `outcomes.py`/`reservations.py`
(I2), the sole-writer seam, `picture.py`/mirror. **This arc touches no invariant code**; if any
invariant file moves, that is a freeze violation — explain or revert.

## CLOSE-OUT — TOOLING tier (no badge, no invariant)

No full-suite/greening obligation. Verify the four tasks concretely: **(1)** the measured
incremental-commit times per daemon file (the tax-paid proof); **(2)** `check_artifact_gate_coverage`
state after — PASS or a stable non-re-pointed GUARDED, with each of the 8 dispositions named;
**(3)** the D3.464 fix shown both ways (log without marker → cannot-measure; log with → pass);
**(4)** the recon report exists and is complete. **CHECK-DEBT reconciled + the ARC-TOTAL series row
written and re-derived whole** off `check_derived_claims` (do not skip — the 050 miss). Any gate
touched (Task 2/3) is BOUND by a demonstrated FAIL.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 11/12. NO board redraw.** This arc pays the tax and clears the
debt; it flips nothing. On bank, the four I1 arcs (A/B/C/D) are cleared to run without re-hitting the
escalation, D3.104 stops being walked, the status gate stops lagging, and ARC C has its build plan.
**Next after this: I1 ARC A** (reject + timeout + the D3.463 signal_ts fix).

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived tip, record the baseline, THEN predict this arc's DELTA:
* Task 1 adds TEST files, not gates → registered-check count unchanged (100); the `passed` count for
  gate additions does not move.
* Task 2 may move `check_artifact_gate_coverage` GUARDED → PASS (if the 8 are resolved) — predict the
  guarded/passed shift from what you actually resolved.
* Task 3 clears `check_arc_status_contract`'s cannot-measure for FUTURE arcs; at THIS re-measure it
  audits `arc_051.log` — predict PASS if 051's log carries its marker, cannot-measure if not (state
  which from the log).
* account for the guard re-point (052 → ARC A) if Task 2 leaves any exclusion, and whether the `.dmg`
  was deleted.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start (and Task 3 makes the marker land in the log). Verified watchdog teardown before the marker,
matched by cc's own signature, ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when
touching a gate.
**After the marker, PUSH: `git push origin` — origin is 50+ behind and the ARC 050 disk near-miss
makes it unsafe to defer (memory #21).**
