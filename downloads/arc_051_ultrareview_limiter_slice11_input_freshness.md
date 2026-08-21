# ARC 051 — ULTRAREVIEW: Limiter, slice 11 — I12 input freshness (never act on stale/out-of-order/half-built)

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This slice DISCHARGES AN INVARIANT: I12 → 11/12
— the LAST point-fix; only the I1 daemon capstone remains after it.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `ffd6b69` (approximate — ARC 050's final re-measure commit).** DERIVE the real tip
with `git rev-parse HEAD` and freeze/diff against THAT (050's cited `67ce36f` was really `89e0e2a`).
**Model: Opus 5** — an absence proof (no stale/out-of-order/half-built input is ever acted on) over
the freshness discipline. Not a mechanical edit.

## The invariant — I12

**§6.4:** *"Stale (freshness stamp past threshold, after retry/backoff) ⇒ halt new entries AND
flatten open. Detection = system; execution = Limiter."* **§6.4b / V27:** balance/margin reconciled
by a **monotonic-by-source guard** (venue timestamp/sequence; **discard any reading older than the
one held** so it never regresses). **§12.7 / V31:** freshness stamps ride each update; a **half-built
mirror ⇒ treated as stale ⇒ fast-drop/deny until the snapshot lands.** §3 fast-drop reads **own
staleness stamps** before sizing/wire.

**Three deny-side failure modes, all load-bearing, all provable now:**
1. **STALE ⇒ deny.** An input whose freshness stamp is past threshold (after retry/backoff) is
   fast-dropped — the gate halts new entries rather than acting on stale price/margin/balance.
2. **OUT-OF-ORDER ⇒ discarded (never regress).** A reading older than the one currently held is
   discarded by the monotonic-by-source guard; balance/margin never regresses on a late/duplicate
   poll (V27).
3. **HALF-BUILT ⇒ stale.** A mirror still rebuilding after restart/subscribe is treated as stale and
   fast-dropped until its snapshot lands (V31) — the gate never sizes on a partial mirror.

**Scope / daemon-vs-library line.** I12 proves the freshness-detection CODE is correct — the
staleness determination, the monotonic guard (`freshness.py`/`SourceMonotonicGuard`), the fast-drop,
the half-built detection — structurally and driven at the library level. Two things are explicitly
NOT this arc: (a) the **flatten-open half** of §6.4 (STALE_PRICE producer) is **D3.453 = I1 ARC C**;
(b) one-version cross-table coherence (V32, no fresh-margin/stale-balance skew) is the atomic-snapshot
property (I7-adjacent) — name it if it intersects, do not re-litigate it here.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive clean/open: clean
   `{I2, I3, I4, I5, I6, I7, I8, I9, I10, I11} = 10/12`, open = 2. **This slice targets I12 → 11/12
   (redraw the board on bank); after it only I1 remains.** Read I12's actual 038 charter; bind S1 to
   the defect it names — **I3/I4/I9 were met-in-code with only the proof missing; I12 may be the same,
   or a real freshness gap (a stale input acted on, a monotonic-guard hole, a half-built mirror
   sized on).** Reproduce, don't assume.
2. **Gate ownership census FIRST (the I4/I9 lesson).** Census the gates: a `check_freshness*` /
   `check_monotonic*` / `check_snapshot*` may own part of this. If the freshness property as a whole
   is unowned, a NEW `check_input_freshness` gate is correct and `passed +1`; if an owner exists,
   extend it (rule 8). State the ownership finding and the predicted delta BEFORE the run.
3. **NEW gate-authoring boilerplate (the recurring rule-4 bug — hit 045/049/050×2).** Every gate this
   arc ships/extends must include a test that plants a defect producing a **FAIL on one arm AND a
   CANNOT_MEASURE on another simultaneously**, and proves the **FAIL wins** (rule 4: Fail >
   Cannot-measure; judge unclassifiable LAST). This ordering has been gotten wrong in four
   consecutive gate first-drafts — bake the test in from the start.
4. **Process + ops lessons (memory #20/#22/#23):** DIAGNOSE BY READING (read the failing hook before
   any environmental theory). Scope lint-fix to CHANGED files, never `ruff … .`. Run
   `test_check_order_path_bans` + `test_check_uncalled_entry_points` explicitly. Read `_HANDLERS`-style
   dicts with `ast.iter_fields`, never a bare `.keys` (the 049 cross-gate hazard). **pytest
   `--basetemp` OUTSIDE `~/nix` (e.g. `/var/tmp/arc051_pt`)** — a basetemp inside the tree recurses
   through the tree-copying tests (D3.462 filled the disk to 100% in 050). Progress file one
   `key=value` per line; `arc_heartbeat.sh` from the start, tee'd to `arc_051.log`.
5. **Re-measure baseline — MEASURE, don't carry (memory #19).** Run `verify.py` at the derived tip
   FIRST; record the real baseline (050 closed `92|4|2|0|1` at `ffd6b69`). Note the `.dmg` state
   (`check_untracked_attribution`).

## S1 — REPRODUCE FIRST: derive every gate input, drive stale / out-of-order / half-built

**Derive from the code the complete set of inputs the gate acts on** — price (ring), margin/balance/
picture (the versioned snapshot mirror), tradability, calendar — and the freshness/version stamp each
carries. Then, on real objects:
* **STALE:** feed an input with a freshness stamp past threshold (after retry/backoff) → assert the
  gate **fast-drops** (halts new entries), does not size on it.
* **OUT-OF-ORDER:** feed a reading older than the one held (V27) → assert the monotonic guard
  **discards** it; the held value does not regress.
* **HALF-BUILT:** feed a mirror mid-rebuild (snapshot not yet landed, V31) → assert it is treated as
  **stale** (fast-drop/deny) until complete.
* **Reproduce the defect I12's charter names** — a stale input acted on, a monotonic-guard gap
  (a late reading regresses the value), a half-built mirror sized on, or the absence of a gate
  proving the discipline. If met-in-code (the I3/I4/I9 pattern), say so — the fix is the PROOF; **do
  NOT edit the subject to manufacture a green** (`CORRECTABLE=False`).
* **Non-vacuity:** prove the gate ACTS on a FRESH input in the healthy case first (so "fast-drops the
  stale one" measures a real refusal, not a gate that drops everything), and that the stamps used
  are the real ones the gate reads.

## S2 — THE FIX (or the proof, if met-in-code)

* If a stale/out-of-order/half-built input can be acted on, close it: the fast-drop reads the
  freshness stamp; the monotonic guard discards older-than-held; the half-built mirror reads stale.
* If S1 finds the code already correct (I3/I4/I9 pattern), **S2 is empty by design** — `git
  hash-object` proves the freshness files byte-identical, and the arc's work is the gate. Say so.
* Cite **§6.4 / §6.4b / §12.7 / §3 / V27 / V31**. **NO retry beyond the §6.4 retry/backoff that
  PRECEDES the stale verdict** (the stale determination already includes it; do not add another).
  **Freeze everything else** — the fill path (047), the exit path (048), the two-phase state (049),
  the hot-path files (050), I2's release logic, the sole-writer seam, the mirror internals. Any new
  helper ships its call site.

## S3 — BOTH DIRECTIONS, on real objects

**(a) NEVER ACT ON A BAD INPUT.** Across all three modes (stale, out-of-order, half-built), and
across every derived gate input, prove the gate refuses/discards — the absence proof. **Completeness
is the obligation** (rule 4): assert the set of freshness-checked inputs equals the set of inputs the
gate acts on; an input added later without a freshness check is the exact defect.

**(b) ACT ON A FRESH, IN-ORDER, COMPLETE INPUT.** A fresh input within threshold, a newer-than-held
reading, a fully-landed mirror → the gate proceeds normally. Freshness must not be achieved by
denying everything (a gate that always fast-drops is safe and useless).

**Non-vacuity:** each direction asserts the input was real and its stamp was the one the gate reads,
before the verdict. Watch past the tick (§0a — one stale drop is not proof the next reading is
handled).

## S4 — the gate (census ownership first; freshness-check completeness by derivation)

Per S1 obligation 2. The obligations that make it non-vacuous:
* **The freshness-checked-input set is DERIVED from the code** (by shape — an input the gate reads
  that carries a stamp — not a spelled list); an input the census can't classify ⇒ **CANNOT_MEASURE
  naming it**, never PASS.
* **All three modes driven on real objects:** stale (past threshold) ⇒ deny; out-of-order ⇒
  discarded/no-regress; half-built ⇒ stale.
* **The rule-4 plant-both test** (kickoff obligation 3) is present.

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (stale acted on)** — a stale input the gate sizes on ⇒ `fail`, exit 1, names the input
  and the stale stamp it ignored.
* **PLANT B (regress)** — remove the monotonic guard's discard so a late reading regresses the held
  value ⇒ `fail`, exit 1, names the regressed value.
* **PLANT C (half-built sized on)** — a mid-rebuild mirror the gate acts on ⇒ `fail`, exit 1.
* **PLANT D (unclassifiable input)** — a gate input the freshness census can't classify ⇒
  `CANNOT_MEASURE`, exit 2, naming it.
* Plants removed ⇒ exit 0. Non-vacuity: a real fresh input acted on, before any verdict. Exit 0/1/2;
  no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the freshness code IF changed (name the functions; byte-identical if met-in-code),
the freshness gate + its test, and `docs/CHECK-DEBT.md`. **Byte-identical (prove with
`git hash-object`):** the fill path, the exit path (`flatten.py`), the two-phase state
(`positions.py`/`projection.py`), the hot-path files (050), `outcomes.py`/`reservations.py` (I2),
the sole-writer seam, `picture.py`/mirror. Name any `uncalled_entry_points_baseline.json` ratchet
movement. Explain or revert any wider path.

## CLOSE-OUT — INTERIOR tier

Full pytest + census DEFERRED to greening. Run: **(b)** DERIVED reverse-dependency closure + the
D3.444 by-detection backstop; non-vacuity proven, RED-before/GREEN-after on this arc's own defect
(a stale input acted on, specifically). **(c)** the gate BOUND from all four plants (A/B/C exit 1,
D exit 2, sites named) plus the rule-4 plant-both test. **(d)** CHECK-DEBT reconciled + **the
ARC-TOTAL series row written and re-derived whole off `check_derived_claims`** (050's re-measure
missed on a skipped series row — do not repeat: append debt rows AND move the series row in the same
close-out).

## RESIDUAL — explicitly NOT claimed

* The **flatten-open half** of §6.4 (STALE_PRICE producer) is **D3.453 = I1 ARC C** — I12 proves
  stale ⇒ deny (halt new entries); the flatten of an already-open position on stale is the capstone.
* One-version cross-table coherence (V32) is the atomic-snapshot property — name it if it intersects,
  do not re-litigate.
* **D3.372** (not-tradable fill → UNCERTAINTY flatten, architect-ruled) — I1 ARC C.
* **D3.458** (WAL write resolved-by-design per the architect ruling), **D3.450**, **D3.104** (8
  exclusions — pay-down candidate, now 5 arcs re-pointed) — standing named debt.
* D3.428, D3.434, D3.438–D3.462, D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED — clean set becomes `{I2, I3, I4, I5, I6, I7, I8, I9, I10, I11, I12} = 11/12`,
open = 1 (`I1` — the daemon-wiring capstone, ~4 arcs)**, if I12 is discharged. **Redraw the board on
bank. This is the LAST point-fix — after it, the ONLY thing between the Limiter and a green badge is
the I1 tail + the greening close-out.** Recommend a pre-pay/consolidation arc next (cover the
`limiterd.py`-class daemon files under testmon + pay down D3.104 + finalize the ARC C flatten-producer
plan) BEFORE ARC A, per the pre-pay-the-tax discipline.

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived tip, record the real baseline, THEN predict only this arc's DELTA:
* if the freshness gate is a NEW file → `passed +1`; if it extends an owner → no count move.
  **State which, from the census, before the run.**
* the clean-set flips **10/12 → 11/12** (badge axis, separate from the verify tuple);
* `check_arc_status_contract` audits arc_050 and PASSES at both baseline and re-measure (the fixed
  D3.455 behaviour — it excludes the running arc's log and names the previous);
* account for the guard re-point (051 → the next arc) and whether the `.dmg` was deleted.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start, pulse+motion, ~5-min cadence, STALL WARNING after ~15 min no motion, GIT WINS over prose.
Verified watchdog teardown before the marker, matched by cc's own signature, ignoring `[watchdogd]`.
Read `VERIFY-AND-CHECKS.md` directly when building/extending the gate.
**After the marker, PUSH: `git push origin` — I12 banking is a milestone and origin is 50+ behind
(memory #21: push after every badge flip, unsafe to defer; the ARC 050 disk near-miss makes it
louder, not quieter).**
