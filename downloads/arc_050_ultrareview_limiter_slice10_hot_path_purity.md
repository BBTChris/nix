# ARC 050 — ULTRAREVIEW: Limiter, slice 10 — I9 hot-path purity (cache reads + arithmetic only)

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This slice DISCHARGES AN INVARIANT: I9 → 10/12.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `67ce36f` (approximate — ARC 049's final re-measure commit).** DERIVE the real tip
with `git rev-parse HEAD` and freeze/diff against THAT (049's cited `b462121` was really `e6835fb`).
**Model: Opus 5** — an ABSENCE proof (nothing expensive/blocking/I/O on the gate hot path). Not a
mechanical edit.

## The invariant — I9

**§11 (cross-cutting invariant): "Entry pathway = cache reads + arithmetic only; everything expensive
lives on pollers / event-handlers updating caches and running aggregates."** §5: each rule is an
in-process library, **"lightweight, non-blocking, side-effect-free"**, "no per-eval import, no wire";
**"hot loop never blocks"** (blocking I/O is confined to the low-priority sender thread, which
releases the GIL). §15 audited-unchanged: **O(1) hot-path claims hold with running aggregates;
stop-eval is O(positions ≤ 5)/tick** — the one bounded loop that IS allowed.

**The hot path** = the Limiter's per-GO gate decision (the evaluate/gate call the loop makes on each
GO from the ZMQ inbox) **and** the per-tick handler (stop-eval + running-aggregate maintenance).
**The property, two-sided:**
1. **ONLY cache reads + arithmetic (+ the bounded O(≤5) stop-eval).** Permitted: O(1) cache/dict/
   attribute reads of precomputed values (tradability, Σ aggregates, net-liq mark, balance, HALT
   flag, ranking table), arithmetic, bounded loops over positions (≤5). §11.1–11.5, 11.9.
2. **NOTHING EXPENSIVE, BLOCKING, OR I/O.** Forbidden on the hot path: file/socket/DB I/O, a lock
   acquire that can block, `sleep`, a **per-eval import** (§5), or heavy/unbounded compute that
   §11 places OFF the hot path — group-commit event-log writes (§11.6), the full-scan reconcile
   audit (§11.7), EMA/score math (§11.9, Scoring process owns it), margin (re)computation. The hot
   path READS what pollers/event-handlers precomputed; it does not COMPUTE them.

**Scope / daemon-vs-library line.** I9 proves the hot-path CODE is pure — structurally and driven at
the library level (call the gate/tick handlers under load, trace, prove no forbidden op). The daemon
running the loop per-tick is 042/046/047; do not re-wire it here.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive clean/open from the register: clean
   `{I2, I3, I4, I5, I6, I7, I8, I10, I11} = 9/12`, open = 3. **This slice targets I9 → 10/12 (redraw
   the board on bank).** Read I9's actual 038 charter; bind S1 to the defect it names — **I3 and I4
   were met-in-code with only the proof missing; I9 may be the same, or a real I/O-on-hot-path
   defect.** Do not assume; reproduce.
2. **Gate ownership — census FIRST (the I4 lesson).** Before assuming which gate to extend, census
   the gates: if NO gate owns hot-path purity, a **NEW** `check_hot_path_purity` gate is correct and
   `passed` moves **+1** (doctrine C.9 forbids a second instrument for an OWNED property, but a new
   property gets its own gate). State the ownership finding and the predicted delta BEFORE the run —
   049's brief wrongly assumed an owner existed; cc corrected it.
3. **Process lessons (memory #20/#22):** DIAGNOSE BY READING — if the commit stalls, read the failing
   hook's own output before any environmental theory. Scope lint-fix to CHANGED files, never
   `ruff … .`. Run `test_check_order_path_bans` + `test_check_uncalled_entry_points` explicitly
   (tripwire guard). Progress file one `key=value` per line; `arc_heartbeat.sh` from the start, tee'd
   to `scratchpad/arc_logs/arc_050.log` (the now-fixed D3.455 path).
4. **Re-measure baseline — MEASURE, don't carry (memory #19).** Run `verify.py` at the derived tip
   FIRST; record the real baseline (049 closed `91|4|2|0|1` at `67ce36f`, but the tee makes
   `check_arc_status_contract` read cannot-measure at THIS arc's baseline and PASS at re-measure
   auditing arc_049 — the 049 pattern; predict accordingly). Note whether
   `downloads/Pinokio-8.0.40-arm64.dmg` is still present.
5. **Ops pre-flight.** inode gate + basetemp clean; scratch DBs at teardown; kill by PID, never
   `pkill -f`.

## S1 — REPRODUCE FIRST: derive the hot-path entry points, trace them under load

**Derive from the code the hot-path entry points** — the functions the loop calls per-GO (the gate
decision) and per-tick (stop-eval + aggregate maintenance) — not a transcribed list. Then, on real
objects under a realistic tick/GO load:
* **Trace** the hot path (a call census via `sys.setprofile` / an I/O counter) and record every
  operation it performs transitively: does it only read caches + do arithmetic (+ the ≤5 stop-eval),
  or does it hit a forbidden op — a file/socket/DB call, a blocking lock, a per-eval import, or a
  heavy compute §11 places off-path?
* **Reproduce the defect I9's charter names** — an I/O or blocking op on the hot path, a per-eval
  import, a re-computation of a precomputed aggregate, or the absence of a gate proving purity. If
  met-in-code (the I3/I4 pattern), say so — the fix is then the PROOF; **do NOT edit the subject to
  manufacture a green** (`CORRECTABLE=False`).
* **Non-vacuity:** prove the hot path was actually EXERCISED under the trace (real GOs gated, real
  ticks handled) before "no forbidden op" means anything — a trace over an unexercised path is vacuous.

## S2 — THE FIX (or the proof, if met-in-code)

* If a forbidden op is on the hot path, **move it off** — to a poller/event-handler that updates a
  cache the hot path then reads (§11's architecture). The hot path reads; it does not compute or block.
* If S1 finds the code already pure (I3/I4 pattern), **S2 is empty by design** — `git hash-object`
  proves the hot-path files byte-identical, and the arc's work is the gate. Say so.
* Cite **§11 / §5 / §15**. **NO retry, NO auto-resend.** **Freeze everything else** — the fill path
  (047), the exit path (048), the two-phase state (049), I2's release logic, the sole-writer seam,
  the mirror. Any new helper ships its call site.

## S3 — BOTH DIRECTIONS, under load, on real objects

**(a) PURITY.** Drive the hot path (per-GO gate + per-tick handler) under a realistic load and prove
its transitive call census contains ONLY the allowed set (cache reads, arithmetic, O(≤5) stop-eval)
— **the absence proof.** Completeness is the obligation (rule 4): assert the set of hot-path entry
points traced equals the set the loop calls per-GO/per-tick in the code; a new hot-path callee added
later with a forbidden op is the exact defect.

**(b) OFF-PATH EXPENSIVE WORK STILL HAPPENS.** Prove the expensive work §11 moves off the hot path
still runs where it should — group-commit writes occur (off-path), the full-scan reconcile runs
(off-path), the ranking read is O(1) with the EMA computed elsewhere — so "pure hot path" is not
achieved by silently dropping required work. (Purity that skipped the group-commit would be a
different bug.)

**Non-vacuity:** each direction asserts the path was exercised under real load before the verdict.
Watch past the tick (§0a — one clean trace is not proof the next GO stays pure).

## S4 — the gate (census ownership first; ALLOW-set, not a ban-list)

Census the gates (S1 obligation 2). If unowned, build `check_hot_path_purity` (+1); if an owner
exists, extend it (rule 8). The obligations that make it non-vacuous:
* **Hot-path entry points DERIVED from the loop's call sites** (by shape — what the loop dispatches
  per-GO/per-tick — not a spelled list), traced transitively.
* **Purity by an ALLOW-set, not a ban-list** (the I3 ARM-6 pattern — §7.12's "what makes this pass
  while measuring nothing" answer is *an expensive op nobody thought to ban*): the hot path may enter
  ONLY the measured allowed operations; **an operation outside the allow-set ⇒ CANNOT_MEASURE naming
  it**, never PASS. The allow-set is honest because MEASURED against the shipped pure path.
* **Driven under load**, not just static — a forbidden op reachable only at runtime (a lazy import, a
  conditional I/O) must be caught by the trace.

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (I/O on the hot path)** — insert a file/socket/log write into the gate decision: the
  trace catches a forbidden syscall ⇒ `fail`, exit 1, names the op and the hot-path site.
* **PLANT B (blocking / per-eval import)** — a blocking lock or a per-eval import on the hot path ⇒
  `fail`, exit 1 (a blocking op wedges the single-threaded loop — §5).
* **PLANT C (unclassifiable op)** — a hot-path operation the allow-set census cannot classify ⇒
  `CANNOT_MEASURE`, exit 2, naming it.
* Plants removed ⇒ exit 0. Non-vacuity: the hot path really exercised under load before any verdict.
  Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the hot-path code IF changed (name the functions; byte-identical if met-in-code),
the hot-path gate + its test, and `docs/CHECK-DEBT.md`. **Byte-identical (prove with
`git hash-object`):** the fill path, the exit path (`flatten.py`), the two-phase state
(`positions.py`/`projection.py`), `outcomes.py`/`reservations.py` (I2), the sole-writer seam,
`picture.py`/mirror. Name any `uncalled_entry_points_baseline.json` ratchet movement (the 047/049
precedent — and watch the cross-gate AST-read hazard 049 found: read `_HANDLERS`-style dicts with
`ast.iter_fields`, not a bare `.keys`, so this gate does not erode another's ratchet). Explain or
revert any wider path.

## CLOSE-OUT — INTERIOR tier

Full pytest + census DEFERRED to greening. Run: **(b)** DERIVED reverse-dependency closure + the
D3.444 by-detection backstop; non-vacuity proven, RED-before/GREEN-after on this arc's own defect
(a forbidden op on the hot path, specifically). **(c)** the gate BOUND from all three plants (A/B
exit 1, C exit 2, sites named). **(d)** CHECK-DEBT reconciled + the ARC-TOTAL series row written.

## RESIDUAL — explicitly NOT claimed

* The daemon running the hot path per-tick is 042/046/047; I9 proves the code is pure.
* **D3.372** (not-tradable confirmed fill — architect-ruled: an UNCERTAINTY protective flatten, root
  fix = deny-at-approval, folds into I1 ARC C) — not this arc.
* **D3.450** (`fills.py` release-before-commit torn state) — `fills.py` frozen here.
* **D3.453** (STALE_PRICE flatten producer — I1 ARC C) — not this arc.
* **D3.104** (the 8 `gate_coverage` exclusions re-pointed 5 arcs running — pay-down candidate, not
  perpetual re-point).
* D3.428, D3.434, D3.438–D3.443, D3.446–D3.457, D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED — clean set becomes `{I2, I3, I4, I5, I6, I7, I8, I9, I10, I11} = 10/12`,
open = 2** (`I1`, `I12`), if I9 is discharged. **Redraw the board on bank.** After this only **I12**
(freshness) and the **I1** daemon capstone remain before greening.

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived predecessor tip, record the real baseline, THEN predict only this
arc's DELTA:
* if `check_hot_path_purity` is a NEW gate file → `passed +1` (memory #18 exception); if it extends
  an existing owner → no count move. **State which, from the census, before the run.**
* the clean-set flips **9/12 → 10/12** (badge axis, separate from the verify tuple);
* `check_arc_status_contract` reads cannot-measure at THIS arc's baseline (the tee makes arc_050.log
  exist in flight) and PASS auditing arc_049 at re-measure — the 049 pattern; reflect it;
* account for the guard re-point (050 → 051) and whether the `.dmg` was deleted.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start, pulse+motion, ~5-min cadence, STALL WARNING after ~15 min no motion, GIT WINS over prose.
Verified watchdog teardown before the marker, matched by cc's own signature, ignoring `[watchdogd]`.
Read `VERIFY-AND-CHECKS.md` directly when building/extending the gate.
**After the marker, PUSH: `git push origin` — I9 banking is a milestone and origin is 49+ behind
(memory #21: push after every badge flip, unsafe to defer).**
