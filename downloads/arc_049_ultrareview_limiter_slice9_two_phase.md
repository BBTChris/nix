# ARC 049 — ULTRAREVIEW: Limiter, slice 9 — I4 two-phase: OPEN only on confirmed fill

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This slice DISCHARGES AN INVARIANT: I4 → 9/12.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `b462121` (approximate — ARC 048's final re-measure commit).** DERIVE the real tip
with `git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — an ABSENCE proof (no path asserts OPEN except on confirmed fill) guarding against
a phantom position. Not a mechanical edit.
**Secondary, bounded:** fold in the **D3.455** fix to `check_arc_status_contract` (below). If it
balloons, DEFER it (named) and keep I4 focused — I4 is the primary.

## The invariant — I4

**§4:** *"Two-phase entry states: `PENDING` (placement accepted) → `OPEN` (fill CONFIRMED). Open is
asserted ONLY on broker fill confirmation — never on placement ack, never optimistically."* **§2A:**
`place_order` returns an ack *"never a fill"*; `on_ack(accepted|rejected)` is the ack, `on_fill` is
the confirmation; **position state derives from cumulative fills** (§4 idempotent execution).

**Two halves, both load-bearing, both a real risk:**
1. **NO PREMATURE OPEN.** No path asserts `OPEN` on an ack, on placement, or optimistically. An
   acked-but-unfilled order is `PENDING`. A premature `OPEN` is a **phantom position** — committed
   margin and sizing math for a position that does not exist, and a protective stop armed on nothing.
2. **OPEN ON EVERY CONFIRMED FILL.** A confirmed fill transitions `PENDING → OPEN` (ARC 047 wired
   this for the daemon fill path). A fill that leaves the state stuck in `PENDING` is a **real
   unprotected position** the system thinks isn't open. The invariant is that `OPEN` tracks confirmed
   fills EXACTLY — no more (half 1), no less (half 2).

**Scope / daemon-vs-library line.** I4 proves the STATE-MODEL code asserts `OPEN` only on confirmed
fill — structurally and driven, at the library level. The pending-timeout resolution of an
acked-but-unfilled order (`PENDING → confirmed/cancelled/indeterminate`, §4, via `query_order_status`,
never auto-resend) is a POLL path = **I1 ARC A**, not this arc. Prove the OPEN-setter discipline; do
not wire the timeout poll here.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive clean/open from the register: clean
   `{I2, I3, I5, I6, I7, I8, I10, I11} = 8/12`, open = 4. **This slice targets I4 → 9/12 (redraw the
   board on bank).** Read I4's actual 038 charter; bind S1 to the defect it names (I3 was met-in-code
   with only the proof missing — I4 may be the same, or a real premature-OPEN path).
2. **The D3.455 fixes (status tooling — bitten 043/045/048):**
   - **Proximate:** run `arc_heartbeat.sh` from the start AND **tee it to `scratchpad/arc_logs/arc_049.log`
     from the first emit** — 048's emitter ran but was never written to the file, so
     `check_arc_status_contract` read a *stale* completed arc's log and reported `[ok]` for the wrong
     reason.
   - **Durable (bounded sub-task):** patch `check_arc_status_contract` so it **NAMES the arc whose log
     it audited** in its verdict line, and audits the **immediately-previous completed arc's** log
     specifically — **CANNOT_MEASURE naming the missing log if that arc's log is absent**, rather than
     silently falling back to an older log and passing. This preserves the D3.433 duty cycle (it
     audits the *previous* arc, correctly) while making a `[ok]` unambiguous about which arc it
     concerns. Ship it with a demonstrated FAIL (plant: the expected previous-arc log absent ⇒
     CANNOT_MEASURE naming it, NOT a pass on an older one). **If this exceeds ~30 lines + a test,
     DEFER it as D3.455 and do only the proximate tee fix** — do not let it balloon I4.
3. **The 046/047/048 process lessons:** progress file one `key=value` per line; scope lint-fix to
   CHANGED files never `ruff … .`; run `test_check_order_path_bans` + `test_check_uncalled_entry_points`
   explicitly (tripwire guard).
4. **Re-measure baseline — MEASURE, don't carry (memory #19).** Run `verify.py` at the derived
   predecessor tip FIRST; record the real baseline (048 closed `90|4|2|0|1`). Note whether
   `downloads/Pinokio-8.0.40-arm64.dmg` is still present (reddens `check_untracked_attribution`).
5. **Ops pre-flight.** inode gate + basetemp clean; scratch DBs at teardown; kill by PID, never
   `pkill -f` on cc's own patterns.

## S1 — REPRODUCE FIRST: enumerate every OPEN-setter, prove only fill-confirmation sets it

**Derive from the code the complete set of sites that transition a position/order state to `OPEN`.**
Then, on real objects:
* Drive an **ack** (`on_ack(accepted)`) for a pending order → assert the state is `PENDING`, **NOT
  `OPEN`** (no phantom). Drive a **reject** (`on_ack(rejected)`) → `PENDING` resolves toward
  aborted/flat, never `OPEN`. Drive a **confirmed fill** (`on_fill`) → `OPEN`.
* **Reproduce the defect I4's charter names** — a path that sets `OPEN` on ack/placement/optimistically
  (the phantom), a confirmed fill that leaves state stuck `PENDING`, or the absence of a gate proving
  the discipline. If met-in-code (the I3 pattern), say so — the fix is then the PROOF, and **do not
  edit the subject to manufacture a green** (the I3 discipline: `CORRECTABLE=False` forbids it).
* **Non-vacuity:** prove an order was really placed and really acked (state genuinely `PENDING`)
  before "ack did not set OPEN" means anything, and that a fill genuinely confirms `OPEN` — so the
  two-phase transition is exercised, not asserted over an empty state.

## S2 — THE FIX (or the proof, if met-in-code)

* Ensure the **only** `OPEN`-setter is the confirmed-fill path; the ack path sets/leaves `PENDING`;
  reject/expire resolve toward flat, never `OPEN`. If a premature-OPEN path exists, remove it.
* If S1 finds the code already correct (I3 pattern), **S2 is empty by design** — `git hash-object`
  proves the state-model file byte-identical, and the arc's work is the gate. Say so explicitly.
* Cite **§4 / §2A / §14** (uncertainty → flat, never optimistic-open). **NO retry, NO auto-resend.**
  **Freeze everything else** — the fill path (047), the exit path (048 `flatten.py`), I2's release
  logic, the sole-writer seam, the mirror, the onset seam (I11). Any new helper ships its call site.

## S3 — BOTH DIRECTIONS, on real objects

**(a) NO PREMATURE OPEN.** Ack → `PENDING`; reject → aborted/flat; placement alone → `PENDING`;
optimistic paths absent. Enumerate every OPEN-setter and prove the ONLY one reachable without a
confirmed fill is none (the absence proof). **Completeness is the obligation** (rule 4): assert the
set of OPEN-setting sites equals the derived set; a new one added later without the fill gate is the
exact phantom defect.

**(b) OPEN ON CONFIRMED FILL.** A confirmed `on_fill` → `PENDING → OPEN`, exactly once, deriving from
cumulative fills (idempotent — a re-delivered fill does not double-open). Partial: successive fills
accumulate, state `OPEN` on the first confirmed fill, size cumulative.

**Non-vacuity:** each direction asserts the order was really pending and the event really arrived
before the verdict. Watch past the tick (§0a — a state not-yet-OPEN is not proof it won't wrongly
open on the next event).

## S4 — the gate (find the two-phase/state owner; OPEN-setter discipline by derivation)

Find the gate that owns the entry-state / two-phase discipline (a `check_state*` / `check_two_phase*`
/ `check_open*` gate) and **extend it** (rule 8 / Part C.9) — this is a DIFFERENT gate than
`check_flatten` (I3), so no collision. The obligations:
* **The OPEN-setter set is DERIVED from the code** (by shape — a state transition to `OPEN` — not by
  identifier spelling, D3.426), and the gate proves the only reachable OPEN-setter requires a
  confirmed fill. An OPEN-setter it cannot classify ⇒ **CANNOT_MEASURE naming it**, never PASS.
* **Driven:** ack → not-OPEN; fill → OPEN; re-delivered fill → not double-open.

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (phantom)** — a path asserts `OPEN` on ack: an acked-but-unfilled order reads `OPEN` ⇒
  `fail`, exit 1, names the premature-OPEN site and the phantom position (committed margin for
  nothing).
* **PLANT B (stuck pending)** — a confirmed fill does not transition to `OPEN`: a real fill reads
  `PENDING` ⇒ `fail`, exit 1, names the unprotected real position.
* **PLANT C (unclassifiable OPEN-setter)** — a state-to-OPEN site the derivation can't classify ⇒
  `CANNOT_MEASURE`, exit 2, naming it.
* Plants removed ⇒ exit 0. Non-vacuity: a real order really pending, a real event, before any
  verdict. Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the state-model code IF changed (name the functions; byte-identical if met-in-code),
the two-phase gate + its test, **`check_arc_status_contract` + its test (the D3.455 patch)**, and
`docs/CHECK-DEBT.md`. **Byte-identical (prove with `git hash-object`):** the fill path
(`completions.py`/`fills.py`/`limiterd.py`), the exit path (`flatten.py`, 048), `outcomes.py`/
`reservations.py` (I2), the sole-writer seam, `picture.py`/mirror. Name any `uncalled_entry_points_
baseline.json` ratchet movement (the 047 precedent). Explain or revert any wider path.

## CLOSE-OUT — INTERIOR tier

Full pytest + census DEFERRED to greening. Run: **(b)** DERIVED reverse-dependency closure + the
D3.444 by-detection backstop; non-vacuity proven, RED-before/GREEN-after on this arc's own defect
(PLANT A phantom, specifically). **(c)** BOTH touched gates BOUND from their real FAIL plants (the
two-phase gate A/B/C; `check_arc_status_contract`'s D3.455 demonstrated-fail if applied). **(d)**
CHECK-DEBT reconciled + the ARC-TOTAL series row written (do not skip).

## RESIDUAL — explicitly NOT claimed

* Pending-timeout resolution (`PENDING → confirmed/cancelled/indeterminate` via `query_order_status`)
  is the POLL path = **I1 ARC A**, not this arc.
* **D3.450** (the `fills.py` release-before-commit torn state, 047) stays — `fills.py` frozen here.
* **D3.453** (STALE_PRICE flatten has no producer — the architect-ruled §6.4 build) folds into I1
  ARC C, not this arc.
* If the D3.455 durable patch was deferred, it stands as named debt with the proximate tee fix done.
* D3.428, D3.434, D3.438–D3.443, D3.446–D3.455, D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED — clean set becomes `{I2, I3, I4, I5, I6, I7, I8, I10, I11} = 9/12`, open = 3**,
if I4 is discharged. **Redraw the board on bank.** Remaining open: **I1** (4-arc capstone), **I9, I12**
— then greening. Three-quarters of the module.

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived predecessor tip, record the real baseline, THEN predict only this
arc's DELTA:
* the two-phase gate + the `check_arc_status_contract` patch both EXTEND existing gates (no new file)
  → the `passed` count is **unchanged from the measured baseline** for gate additions;
* **but account for `check_arc_status_contract`'s OWN verdict changing** — the D3.455 patch makes it
  audit the previous arc by name; predict whether it lands PASS (a clean previous-arc log) or
  CANNOT_MEASURE (its expected log absent), and reflect that in the tuple rather than assuming the
  old false `[ok]`;
* the clean-set flips **8/12 → 9/12** (badge axis, separate from the verify tuple);
* account for the guard re-point (049 → 050), and whether the `.dmg` was deleted.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start, tee'd to `arc_049.log` (D3.455 proximate fix), pulse+motion, ~5-min cadence, STALL WARNING
after ~15 min no motion, GIT WINS over prose. Verified watchdog teardown before the marker, matched by
cc's own signature, ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending gates.
