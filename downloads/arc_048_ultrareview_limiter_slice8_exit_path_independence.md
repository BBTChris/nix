# ARC 048 — ULTRAREVIEW: Limiter, slice 8 — I3 exit-path zero-wire independence

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This slice DISCHARGES AN INVARIANT: I3 → 8/12**
(first count flip since ARC 045 — the two I1 arcs did not move it).
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `696020c` (approximate — ARC 047's final re-measure commit).** DERIVE the real tip
with `git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — an ABSENCE proof (no wire dependency exists in the exit path) over the
self-preservation core. Not a mechanical edit.

## Why point-fixes now, and I3 first

ARC 047 measured the I1 tail as **4 more arcs, serial behind one gate file — batch, not swarm**, and
recommended the independent point-fixes (I3/I4/I9/I12) FIRST: each moves the count on its own and
none is blocked on the I1 merge point. **I3 is the highest-safety of the four** and is warm from 047
(which armed the synthetic stops); I3 proves the path that FIRES them cannot be starved by a dead
wire.

## The invariant — I3

**§1 Goal: "The exit/protective path has ZERO wire dependency"** — "every open position is protected
by a mechanism that never depends on the network being healthy." **§3:** every protective trigger
(*synthetic stop / stale price / net-liq floor / session close / uncertainty / orphan / sentinel*) →
**broker-order (in-process, DIRECT call)** → flatten; "**Exit never routes through Allocator.
Protective exit always wins.**" **§4:** the Limiter's protective exit is **unconditional**; strategy
notified `closed, reason=X`, FSM hard-resets to flat. **§2:** broker-order is in-process precisely
because of *"triviality + exit-path criticality."*

**Three halves, all load-bearing:**
1. **NO WIRE in the exit path.** Every protective trigger reaches `flatten` via a direct in-process
   `broker-order` call — **no ZMQ publish, no Allocator round-trip, no state-bus read, no wait on any
   external delivery.** A hidden wire dependency anywhere in the exit path is the defect.
2. **UNCONDITIONAL / always wins.** The protective exit is never gated by, delayed by, or contingent
   on anything external, and wins over a discretionary exit.
3. **SURVIVES EVERYTHING EXTERNAL DEAD.** With the Allocator dead, ZMQ down, and the state bus
   silent, the exit path still flattens through the in-process broker seam.

**Scope boundary (the daemon-vs-library line, per the ULTRAREVIEW structure).** I3 proves the exit
**path code** is wire-free — structurally and driven at the library level. The running daemon
actually **firing** protective-flatten completions (StopBook.breached off the price poll, the
protective-flatten completion route) is **I1 ARC C/D** (D3.451), not this arc. Prove the code carries
no wire; do not wire the daemon here.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive clean/open from the 038 register: clean
   `{I2, I5, I6, I7, I8, I10, I11} = 7/12`, open = 5. **This slice targets I3 → 8/12 (a real count
   flip; redraw the board on bank).** Read I3's actual 038 charter and bind S1 to the defect it names
   (I5 was unimplemented, I7/I2 were half-done — I3 may be any of these).
2. **The 046/047 process lessons, all applied:**
   - `arc_heartbeat.sh` from the START of the session (selfcheck → banner → pulses into
     `scratchpad/arc_logs/arc_048.log`), not just at write-back.
   - Progress file **one `key=value` per line** (D3.445).
   - Confirm the S4.4 testmon fingerprint holds (`scripts/limiterd.py` in `.testmondata` — though I3
     likely does NOT touch `limiterd.py`, so the commit is incremental regardless; confirm).
   - **Scope any lint-fix to CHANGED files, never `ruff … .` repo-wide** (047's collateral).
   - **Tripwire guard:** run `test_check_order_path_bans` and `test_check_uncalled_entry_points`
     EXPLICITLY, not via testmon selection (the 044/045 stale-tripwire finding).
3. **Re-measure baseline — MEASURE, do not carry (memory-#19 / §D3.102 lesson, the ARC 047 miss).**
   Run `verify.py` at the DERIVED predecessor tip FIRST and record the real baseline; 047's final
   `89|4|3|1|1` composition is NOT to be assumed. In particular note whether
   `downloads/Pinokio-8.0.40-arm64.dmg` is still present (it reddens `check_untracked_attribution`
   until the operator deletes it) — its state is part of the measured baseline, not this arc's doing.
4. **Ops pre-flight.** inode gate + basetemp clean; scratch DBs at teardown (D3.437); kill by PID,
   never `pkill -f` on cc's own patterns.

## S1 — REPRODUCE FIRST: enumerate the protective triggers, drive each with the wire DEAD

**Derive the complete set of protective triggers from the code** (§3's list is the checklist to
verify the derivation against, not to substitute): synthetic stop, stale price, net-liq floor,
session-close flatten, uncertainty/indeterminate flatten, orphan flatten, sentinel/deadman, plus
cold-start flatten-to-flat. Then, on real objects with the **Allocator, ZMQ, and the state bus
mocked DEAD** (unreachable, not merely idle):
* Drive each trigger and record whether it still reaches `broker-order.flatten` via the in-process
  direct call — or whether it publishes/reads/waits on a dead wire and **fails to flatten**.
* **Reproduce the defect I3's charter names** — a trigger with a hidden wire dependency, an exit that
  routes through the Allocator, or the absence of a gate proving wire-freedom. If already clean, say
  so and re-target to the open half.
* **Non-vacuity:** prove each trigger DOES flatten in the healthy case first, so "fails with the wire
  dead" measures a real dependency, not an absent trigger. And prove the wire was genuinely dead
  (the mock rejects, doesn't silently pass).

## S2 — THE FIX

* **Remove every wire dependency from the exit path.** Each protective trigger → `broker-order.flatten`
  is a direct in-process call; no ZMQ, no Allocator, no state-bus read, no delivery wait on that path.
* **Unconditional:** the protective exit is not gated on any external state; it wins over discretionary.
* Cite **§1 / §3 / §4 / §14 / §2**. **NO retry, NO auto-resend** on the exit path (a flatten that must
  not block — §2A `flatten` "must not block"). **Freeze everything else** — the fill path (047), the
  I2 release logic, the sole-writer seam, the mirror, the onset-cancel seam (I11). Any new helper
  ships with its call site.

## S3 — BOTH DIRECTIONS, everything external dead

**(a) EXHAUSTIVE wire-freedom.** With Allocator + ZMQ + state bus dead, drive **every** derived
protective trigger and prove each flattens through the in-process broker seam — the absence proof.
**Completeness is the obligation** (rule 4): assert the set of triggers driven equals the set of
protective-exit sites in the code; a trigger added later with a wire dependency is the exact defect,
so the proof is over the derived set, not a fixed list.

**(b) PROTECTIVE ALWAYS WINS.** A discretionary exit and a protective trigger contend → the protective
wins, the strategy is notified `closed, reason=X`, the FSM hard-resets to flat. And a protective exit
fires even mid-blackout/HALT (exits are untouched by onset — the I11 boundary, re-confirmed here).

**Non-vacuity:** every direction asserts the trigger fired and the wire was dead before the verdict.
Watch past the flatten (§0a — a flatten sent is not a flatten confirmed; §4's indeterminate path
reconciles against broker truth, so assert the CONFIRMED-flat semantics where they apply).

## S4 — the gate (extend the exit-path owner; wire-freedom by derivation)

Find the gate that owns the exit/protective path (`check_flatten` — extended in ARC 045 for I11's
onset selection — or a `check_exit_path` gate) and **extend it** (rule 8 / Part C.9), no second
instrument. Two obligations:
* **Wire-freedom is proven by DERIVATION** — the exit path contains no ZMQ / Allocator / state-bus
  call, asserted structurally (by shape, not by identifier spelling — the D3.426 lesson) AND driven
  (each trigger flattens with the wire dead). If a trigger's classification can't be read statically,
  **CANNOT_MEASURE naming it**, never PASS (the I2/I11 completeness lesson).
* **Driven with the wire dead**, per trigger, against the real in-process broker seam.

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (wire dependency)** — make one protective trigger publish to ZMQ / route through the
  Allocator and wait: with the wire dead it fails to flatten ⇒ `fail`, exit 1, names the trigger and
  the wire it now depends on, and the open position it left unflattened.
* **PLANT B (discretionary beats protective)** — invert the contention so discretionary wins ⇒
  `fail`, exit 1.
* **PLANT C (new unclassifiable trigger)** — a protective site the derivation can't classify ⇒
  `CANNOT_MEASURE`, exit 2, naming it.
* Plants removed ⇒ exit 0. Non-vacuity: a real trigger driven with a real dead wire before any
  verdict. Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the exit-path code (`flatten.py` and the protective-trigger sites — name the
functions), the extended exit-path gate + its test, and `docs/CHECK-DEBT.md`. **Byte-identical
(prove with `git hash-object`):** the fill path (`completions.py`/`fills.py`/`limiterd.py` from 047),
`outcomes.py`/`reservations.py` (I2), the sole-writer seam, `picture.py`/mirror. Explain or revert
any wider path — including the `uncalled_entry_points_baseline.json` ratchet if this arc changes what
is called (name which rows moved and why, per the 047 precedent).

## CLOSE-OUT — INTERIOR tier

Full pytest + census DEFERRED to greening. Run: **(b)** DERIVED reverse-dependency closure + the
D3.444 by-detection backstop (import graph blind to Protocol/subprocess callers); non-vacuity proven,
RED-before/GREEN-after on this arc's own defect (a trigger failing with the wire dead, specifically).
**(c)** the gate BOUND from all three plants (A/B exit 1, C exit 2, sites named). **(d)** CHECK-DEBT
reconciled + the ARC-TOTAL series row written (do not skip — 044/046 both had a series-row miss).

## RESIDUAL — explicitly NOT claimed

* The daemon FIRING protective-flatten completions (StopBook.breached off the price poll, the
  protective-flatten route) is **I1 ARC C/D** (D3.451) — I3 proves the exit-path code is wire-free;
  the daemon-level firing is the capstone.
* **D3.450** (the `fills.py` release-before-commit torn state found in 047) stays — `fills.py` is
  frozen here too; it is fixed when `fills.py` is next opened (likely ARC D).
* D3.428, D3.434, D3.438–D3.443, D3.446–D3.452, D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED — clean set becomes `{I2, I3, I5, I6, I7, I8, I10, I11} = 8/12`, open = 4**, if
I3 is discharged (exhaustive wire-freedom across every derived trigger, protective-always-wins,
gated with a demonstrated FAIL incl. the CANNOT_MEASURE completeness arm). **First count flip since
ARC 045 — redraw the board on bank.** Remaining open: **I1** (daemon-wiring capstone, 4 arcs), **I4,
I9, I12**.

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Do NOT carry a composition forward. Run `verify.py` at the derived predecessor tip, record the real
baseline (pass/fail/cannot/skip/guard), THEN predict only this arc's DELTA on top of it:
* extending `check_flatten` (not a new file) adds **no check** → the `passed` count is **unchanged
  from the measured baseline** (predict `passed+1` only if S4 genuinely creates a new gate file — it
  should not);
* the clean-set flips **7/12 → 8/12** — that is the badge axis, separate from the verify tuple;
* account for the arc-boundary guard re-point (`check_artifact_gate_coverage` owner 048 → 049),
  `check_arc_status_contract` reading cannot-measure by construction at re-measure, and whether
  `Pinokio-8.0.40-arm64.dmg` was deleted (its `check_untracked_attribution` red clears if so).
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start (dogfood), pulse+motion, ~5-min cadence, STALL WARNING after ~15 min no motion, GIT WINS over
prose. Verified watchdog teardown before the marker, matched by cc's own signature, ignoring
`[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending the gate.
