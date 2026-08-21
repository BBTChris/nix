# ARC 056 — D3.474 fix: make trailing stops arm (the strategy's core loss-cutting)

**Tier: INTERIOR — FUNCTIONAL FIX (not an invariant slice).** Limiter badge **STAYS RED**. **The
invariant count STAYS 11/12** — this discharges **D3.474**, it does not flip an I-invariant. But it
**re-opens the frozen subjects of I2 (reservation release) and I4 (two-phase fill)**, so the arc's
spine is **re-proving those two do not regress** — the C1 discipline (re-prove what you touch),
applied to discharged invariants this time.
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `4601a06` (approximate — ARC 055's write-back).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — re-opening two discharged invariants on the fill path, plus the safety of a
release-on-refusal net. Not a mechanical edit.
**Commit is CHEAP** (052). Cite the trailing-stop authority as **§4:187-196** (which `stops.py`
cites) — **NOT §7.4, which does not exist in frozen v1.3** (§7 → §7.5); the ARC 055 correction.

## Why this arc, and why now

ARC 055 (C1) proved the daemon's stop protective-exit — for a **fixed** stop. Driving the trailing
proof revealed **D3.474: this build cannot arm a trailing stop at all.** Measured live:
`reserve(stop_mode=trailing)` accepts and commits margin; the `on_fill` then **refuses** —
`InvalidStopIntent: a trailing stop needs a trail distance, which the frozen ProposedOrder does not
carry`. `fills.py` calls `arm(report.price, order)` with no trail distance. **The position never
opens and the reservation stays taken (leaks).**

The strategy's entire loss-cutting mechanism is 2-tick Renko + **trailing** stops (§4:187-196). So a
green 12/12 Limiter would still refuse every trailing entry — the module cannot pass sim-validation
(and cannot trade) until this is fixed. It is the mainline case; C2's producers are edge cases. Fix
the mainline first.

## The architect ruling this arc applies (confirm if wrong at the tree)

1. **`ProposedOrder` gains a `trail_ticks` field** (the trail distance), threaded **reserve → fill →
   `arm`**. Additive — fixed stops (which use `stop_ticks`) are unaffected.
2. **`StopBook.arm` accepts a trailing stop** — arms it at the initial trail level (price ∓
   `trail_ticks × tick_size`), from which C1's `maintain` then trails it. Call C1's maintain/breach —
   do not change them.
3. **The refusal path RELEASES the reservation** (no leak) and does **not** open an unprotected
   position — a genuinely un-armable order (e.g. a trailing order that still carries no trail
   distance — malformed) fails closed: reservation released exactly once, position not opened. Same
   family as the D3.372 flatten-not-publish ruling.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Framing.** Echo `TIER = INTERIOR (functional fix, D3.474)`. Confirm clean `= 11/12`, open = 1
   (I1). **State: this discharges D3.474; it does NOT flip an invariant; the count stays 11/12; it
   RE-OPENS I2 and I4 and must re-prove them.**
2. **The two re-proof obligations (the arc's spine).** I2 (every reservation reaches exactly one
   terminal release) and I4 (OPEN only on confirmed fill) are discharged; this arc edits their
   subjects (`ProposedOrder`, `fills.py`) and must **re-prove both hold** — I2's gate and I4's gate
   pass at the end, and the new arm-refusal release is a terminal path I2's census accepts, not a
   leak or a double-release.
3. **Trace the trail-distance SOURCE at S1.** `trail_ticks` must come from somewhere legitimate — a
   GO/reserve field the strategy declares, or a per-strategy immutable config (§4:187-196). If the
   GO/contract does not carry it, note the strategy-contract-v1.2 implication (fold into the pending
   contract deltas) but source the value correctly; do NOT invent a default that silently makes every
   trailing order look armed.
4. **Process + ops lessons (memory #19/#20/#22/#23):** MEASURE the tip with `verify.py` FIRST (055
   closed `94|5|2|0`; `check_arc_status_contract` should now read PASS auditing `arc_055.log` — the
   duty-cycle self-correction, so the 5th fail should clear to `95|4|2|0`-ish; state the measured
   baseline). Scope lint-fix to CHANGED files. `--basetemp` OUTSIDE `~/nix` (`/var/tmp/arc056_pt`).
   Run the two tripwire tests explicitly. `arc_heartbeat.sh` from the start (selfcheck INTO the log —
   054's gap). New config knob ⇒ `_derivations` origin entry. inode gate + basetemp clean; scratch
   DBs at teardown; kill by PID.

## S1 — REPRODUCE D3.474 on the live loop, and trace the source

On a real `limiterd`: `reserve(stop_mode=trailing)` → accepted, margin committed; `on_fill` →
**refused** (`InvalidStopIntent`), position not opened, reservation **still committed** (the leak).
Confirm the exact sites: `ProposedOrder` has no `trail_ticks`; `fills.py` calls `arm(price, order)`
with no trail distance. **Trace where `trail_ticks` should originate** (GO field / reserve payload /
strategy config) so the fix threads a real value, not a fabricated one. **Non-vacuity:** prove a
FIXED stop reserve→fill→arm→opens correctly on the same rig first (so "trailing refuses" is measured
against a working fixed path), and prove the reservation genuinely leaked (committed stays up after
the refusal).

## S2 — THE FIX

* **`ProposedOrder` + `trail_ticks`** — additive field; fixed stops unaffected (assert their payload
  path is byte-equivalent in behavior).
* **Thread it** — the reserve carries `trail_ticks` from its traced source; `fills.py` passes it to
  `arm` when `stop_mode=trailing`.
* **`StopBook.arm` trailing** — arm at price ∓ `trail_ticks × tick_size`; the armed trailing stop is
  now a valid `StopState` that C1's `maintain` trails and `breached` fires (call C1 — do not change
  `stopwatch.py`).
* **Refusal releases** — a trailing order that still cannot arm (no trail distance available) →
  reservation released **exactly once**, position not opened, named. NO leak, NO unprotected open.
* Cite **§4:187-196 / §4 (two-phase) / §3 (reservation lifecycle) / §12.1 (synthetic stop)**. **NO
  retry, NO auto-resend.** **Freeze** C1's `stopwatch.py`/maintain/breach (call, don't change), the
  exit path (`flatten.py`), the onset dispatch (054), the reject/timeout dispatch (053), the
  hot-path files (050), the freshness files (051), the sole-writer seam, the mirror.

## S3 — PROVE IT END-TO-END, and RE-PROVE I2 + I4

* **Trailing lifecycle works (the fix):** `reserve(trailing)` → `on_fill` → a trailing stop arms at
  the trail level → OPEN + reservation converts → C1's `maintain` trails it monotonically → a breach
  fires one protective flatten (the FULL trailing loss-cut, end to end on the daemon).
* **Fixed stops unregressed:** a fixed-stop reserve→fill→arm→open→trail-N/A→breach still behaves
  exactly as ARC 047/055 proved (the additive field changed nothing for fixed).
* **RE-PROVE I4:** the trailing fill asserts OPEN **only** on the confirmed fill, never on ack — the
  two-phase discipline holds through the new arm path.
* **RE-PROVE I2:** a trailing entry reaches **exactly one** terminal release — via the successful
  open (reservation→open-margin) OR via the arm-refusal release — never a leak, never a double. Drive
  the malformed-trailing case and prove the arm-refusal releases exactly once.
* Watch past the tick. Non-vacuity throughout.

## S4 — the gate (census; and re-run I2/I4's gates for no-regression)

Census: the arm belongs to `check_fill_handler` / a stop-arm owner; I2 is `check_reservation_lifecycle`;
I4 is `check_two_phase_entry`. Extend the arm owner with the trailing-arm property (rule 8), and
**re-run `check_reservation_lifecycle` and `check_two_phase_entry` to prove no regression** (they must
still PASS, and I2's must accept the arm-refusal release as a legitimate terminal path). A genuinely
new trailing-arm property may need its own gate (+1 — state from the census). Include the rule-4
plant-both test.

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (D3.474 reproduced)** — `trail_ticks` not threaded: a trailing fill refuses, position
  never opens ⇒ `fail`, exit 1, names the refused trailing order.
* **PLANT B (the leak — the I2 safety net)** — the arm-refusal does NOT release: the reservation
  leaks ⇒ `fail`, exit 1, names the leaked reservation and inflated committed.
* **PLANT C (wrong trail level)** — the trailing stop armed at the wrong level (not price ∓
  `trail_ticks × tick_size`) ⇒ `fail`, exit 1, §4:187-196 named.
* Plants removed ⇒ exit 0. Non-vacuity: a real trailing reserve→fill before any verdict. Exit 0/1/2;
  fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `ProposedOrder`'s module (the `+trail_ticks` field — name it), `fills.py` (the arm
threading + the refusal release), `stops.py` (`arm` accepts trailing), the reserve path (carries
`trail_ticks`), the arm gate + its test, `docs/CHECK-DEBT.md`. **Byte-identical (prove with
`git hash-object`):** C1's `stopwatch.py`/`limiterd.py` stop-wiring (call, don't change), the exit
path (`flatten.py`), the onset dispatch (054 additions), the two-phase state gate's SUBJECT
(`positions.py`/`projection.py` — I4's OPEN-setter logic is unchanged; only the fill's arm path
moves), `outcomes.py`/`reservations.py` **unless** the arm-refusal release legitimately needs a new
site there (if so, name it and prove I2's census accepts it), the sole-writer seam, the freshness
files, the hot-path files. Name any `uncalled_entry_points_baseline.json` movement.

## CLOSE-OUT — INTERIOR tier, commit CHEAP

Run: **(b)** DERIVED reverse-dependency closure + the D3.444 by-detection backstop; non-vacuity
proven, RED-before/GREEN-after on the trailing-refusal defect. **(c)** the arm gate BOUND from all
three plants + the rule-4 plant-both, **AND `check_reservation_lifecycle` + `check_two_phase_entry`
shown PASS at the merged tree** (the no-regression proof — this is the arc's most important close-out
item). **(d)** CHECK-DEBT + the ARC-TOTAL series row written and re-derived whole.

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** C2 (the three uncertainty producers, D3.453/372/469 — now on a fill path
  that arms trailing stops) and D (flatten completions + the convergence gate) remain. Count stays
  11/12.
* **D3.474 discharged.** If sourcing `trail_ticks` required a strategy-contract field, name the
  contract-v1.2 implication (fold into the pending contract deltas) but do not block on it if the
  value is available from strategy config.
* **D3.473** (the ring is command-fed, not a real capture feed — broker-datafeed), **D3.470** (onset
  detection is later-module), **D3.468** (status directory has no producer) — unchanged.
* D3.453/372/469 (C2), D3.458, D3.450, D3.466/467/471/472, D3.428, D3.434, D3.438–D3.474,
  D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 11/12.** This discharges D3.474 (trailing stops arm end-to-end) and
re-proves I2/I4 unregressed. **No board redraw for the count** (clear the D3.474 flag on the tail
annotation). Remaining to green: **C2** (the three producers) → **D** (completions + convergence →
12/12) → greening.

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived tip, record the baseline (055 closed `94|5|2|0`; expect the 5th fail —
`check_arc_status_contract` — to clear to PASS auditing `arc_055.log`, so baseline ~`95|4|2|0`; STATE
the measured value), THEN predict only this arc's DELTA:
* a NEW trailing-arm gate (if genuinely unowned) → `passed +1`; extending the arm owner → no count
  move. **State which from the census.**
* the clean-set stays **11/12** (no flip); I2/I4 gates stay PASS (the no-regression proof);
* account for the guard's stable state and the `.dmg`.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start (selfcheck into the log). Verified watchdog teardown before the marker, matched by cc's own
signature with POSITIVE identification (D3.465), ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md`
directly when touching a gate.
**After the marker, PUSH: `git push origin` — the strategy's core loss-cutting now works and origin
is 50+ behind (memory #21, unsafe to defer).**
