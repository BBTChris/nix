# ARC 045 — ULTRAREVIEW: Limiter, slice 7 — I11 onset cancellation (entries cancelled, exits untouched)

**Tier: INTERIOR.** Limiter badge **STAYS RED** (invariants remain open after it).
**This slice DISCHARGES AN INVARIANT: I11 → clean set becomes 7/12.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `/home/bbt/nix/.venv/bin/python` →
`/usr/bin/python3.14` (3.14.4).
**Predecessor: ≈ `4d04bfd` (approximate — ARC 044's measurement tip).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT, never the cited sha (044's cited `b7476a6` was
really `3c73002`; the post-write-back re-measure commits after the RESULTS HEAD).
**Model: Opus 5** — completeness (an absence proof: no pending entry survives onset), selectivity
(no exit is ever cancelled), and a venue-side race. Not a mechanical edit.

## The invariant — I11

**§3 / §6.1 / §15 C4:** *"Blackout/HALT onset ⇒ Limiter cancels all pending ENTRY orders (exits
untouched) — no order may fill inside a window it was not approved for."* Three halves, all
load-bearing:

1. **COMPLETE.** On onset, **every** pending entry order in scope is cancelled — none survives. HALT
   onset = **global** (all strategies/symbols); a per-symbol blackout (EOD/EOW/news/roll) = **that
   symbol's** pending entries. A missed entry is an order that fills in a window it was not approved
   for.
2. **SELECTIVE — the safety-critical half.** **ONLY entry orders.** Pending exits and protective
   orders (synthetic stops, session-close flatten, net-liq flatten) are **NOT** cancelled. Cancelling
   a protective exit during a blackout leaves an open position unprotected inside the window. During
   **HALT** especially: HALT stops new **entries**, but §14's exit/protective path has zero delivery
   dependency and **must still fire** — an open position in a HALT still needs its stop.
3. **THE RACE.** The cancel is issued on onset immediately; the Limiter's single-threaded loop (§5)
   serializes its *own* fill-vs-cancel ordering, so the residual race is **venue-side** — a pending
   entry filling at the venue between the cancel being sent and the venue processing it. When the
   cancel loses that race, the raced-in fill must be **subject to the window's rules** (flattened at
   the session-close deadline for EOD/EOW, held-under-buffer/flattened-on-breach for margin), **never
   orphaned or left un-managed**. Best-effort cancel + the window backstop is the enforcement of "no
   order fills in a window it was not approved for."

## KICKOFF OBLIGATIONS (before Stage 1 — all mandatory)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive clean/open from the 038 register: clean
   `{I2, I5, I6, I7, I8, I10} = 6/12`, open = 6; **this slice targets I11 → 7/12 if discharged.**
   Read I11's actual 038 charter and bind S1 to the specific defect it names — the brief gives the
   property; the register holds the finding (I5 was unimplemented, I7 half-fixed, I2 was a wiring
   gap — I11 may be any of these).
2. **Coupling note — do NOT re-touch I2.** ARC 044 wired the reservation *release* on blackout/HALT
   onset (`blackout.py:1062` + `flatten.py:805`, `HALT_ONSET flatten.py:805`). I11 audits the
   *cancellation* that triggers that release — the entry-selection and completeness, not the release
   arithmetic. **Freeze the reservation-release logic (I2, done); change only the cancel selection.**
3. **Status via the tooling (dogfood).** Start `tee` FIRST, then `scripts/arc_heartbeat.sh selfcheck`
   so the self-verify line lands in the tee'd log (044 got this right — keep it). pulses → `pulse`;
   transitions → `banner`. Teardown line exact, on its own line, no `[watchdogd]` on it; write
   teardown + marker into the run's own log *before* the final verify measurement, marker still the
   last token to the operator.
4. **Ops pre-flight.** `checks/check_tmpfs_inode_headroom.py --mount /tmp` + clean stale basetemps.
   Coverage report: the onset-cancel path is expected in `flatten.py` / `blackout.py` (`nixrisk`,
   covered), NOT `limiterd.py` — confirm, and state whether the commit takes the incremental path.
   Clean this arc's scratch DBs at teardown (D3.437). F6/F7: no second commit until the first's gate
   process is dead BY PID; never `pkill -f` on cc's own patterns.

## S1 — REPRODUCE FIRST, both onset types, before a line changes

Bind to the real onset-cancel path. On a live limiter, set up a scope that makes all three halves
observable at once:
* pending **entry** orders (≥1 per symbol, across ≥2 symbols and ≥2 strategies);
* a pending **exit** / a protective stop on an **open** position (the selectivity control);
* then trigger **blackout onset** (per-symbol) AND, separately, **HALT onset** (global).

Measure: which pending entries were cancelled, which survived, and — critically — **whether any exit
or protective order was touched.** Reproduce the defect I11's charter names (a missed entry, a
cancelled exit, an un-wired onset path, or no race backstop). If already fixed, say so and re-target
to the open half.

**Non-vacuity:** prove the setup actually created cancellable pending entries AND at least one exit/
protective order — "all entries cancelled, exits untouched" over a scope with no entries or no exits
is vacuous. Assert the counts before the onset.

## S2 — THE FIX

* **Complete:** the onset cancels every in-scope pending entry — scope = global for HALT, that symbol
  for a per-symbol blackout. Derive the "pending entry" set from order state, not a hand-list.
* **Selective:** the cancel predicate targets **entry** orders only, by order role/kind — exits and
  protective orders are excluded **by construction**, and the exclusion is asserted, not assumed.
  This is the half a wrong predicate silently breaks.
* **Race backstop:** a fill that races in after the cancel is issued is left in a managed state the
  window's rules act on (session-close flatten / margin hold-or-flatten), not orphaned. Confirm the
  cancel is dispatched on onset **before** the loop returns to normal processing.
* Cite **§3 / §6.1 / §15 C4 / §14** (exits always fire). **NO retry, NO auto-resend** (§4). **Freeze
  everything else** — the reservation-release logic (I2), the sole-writer seam (I8), the mirror seam
  (I7), the 042 booking. Any new helper ships with its call site.

## S3 — BOTH DIRECTIONS, both onset types, on real processes

**(a) COMPLETE + SELECTIVE.** On blackout onset (per-symbol) and HALT onset (global), with pending
entries + pending exits + protective stops all present:
* **every** in-scope pending entry is cancelled — enumerate the pending-entry set and prove none
  survives (the completeness absence proof; scope correct: HALT global, blackout per-symbol, and a
  blackout on symbol A does **not** cancel symbol B's entries);
* **not one** exit or protective order is cancelled — enumerate every exit/protective order and prove
  each is untouched and **still able to fire** (re-drive a protective exit after HALT onset and prove
  it flattens — §14).
* **Non-vacuity:** assert the pending-entry set and the exit set were both non-empty before onset.

**(b) THE RACE.** A pending entry that fills at the venue between onset and cancel-landing is **not
orphaned** — it lands in a state the window's backstop manages (prove the session-close flatten or the
margin rule picks it up), and the cancel was dispatched immediately on onset. Watch past the window
opening (the §0a trap — an order not-yet-filled isn't proof it won't).

## S4 — the gate (extend the existing owner; completeness by derivation)

Find the gate that owns blackout/HALT-onset behaviour (a `check_blackout*` / `check_halt*` /
`check_onset*` gate) and **extend it** (rule 8 / Part C.9), do not build a second. Two obligations
make it non-vacuous:

* **Completeness by derivation, not a path list** (the I2/D3.440 lesson): the gate derives the
  "pending entry" set from order state and proves the onset leaves none — if it can only check a
  fixed list of order kinds, it must go **CANNOT_MEASURE naming an entry kind it cannot classify**,
  never PASS, so a new entry kind that survives onset is caught as unmeasured.
* **Selectivity is a named arm:** it asserts **no** exit/protective order is ever cancelled, driven
  live against a real protective order.

**Demonstrated FAIL, each exit 1 (C exit 2) naming the site:**
* **PLANT A (incomplete)** — an in-scope pending entry survives onset ⇒ `fail`, exit 1, names the
  surviving entry and the window it can now fill in.
* **PLANT B (over-broad — the dangerous one)** — the predicate cancels an exit/protective order ⇒
  `fail`, exit 1, names the cancelled protective order and the position it left unprotected.
* **PLANT C (unclassifiable entry kind)** — an order the completeness arm cannot classify ⇒
  `CANNOT_MEASURE`, exit 2, naming it, never PASS.
* Plants removed ⇒ `pass`, exit 0.

**Non-vacuity asserted (rule 4):** the gate proves it staged real in-scope entries AND a real exit
before any verdict. Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the onset-cancel selection logic (`flatten.py` / `blackout.py` — name the exact
functions), the extended onset gate + its test, and `docs/CHECK-DEBT.md`. **Nothing** in the
reservation-release logic (I2), the sole-writer seam, `picture.py`/mirror, the 042 booking, or
`limiterd.py`. Explain or revert any wider path.

## CLOSE-OUT — INTERIOR tier

Full pytest + full census **DEFERRED to greening.** Run: **(b)** DERIVED reverse-dependency closure
(non-vacuity proven — contains the onset module's dependents and the gate's test, RED-before/
GREEN-after on this arc's own defect; cost-aware shell-out exclusions by detection); **(c)** the
extended gate BOUND from all three plants (A/B exit 1, C exit 2, sites named); **(d)** CHECK-DEBT
reconciled — **write the ARC-TOTAL series row** (do not repeat 043's skip). I11's discharge is an
invariant flip, not a debt row; name any residual (e.g. if the race backstop for a given blackout
type is owed elsewhere, name it rather than claim it).

## RESIDUAL — explicitly NOT claimed

* The window backstops themselves (session-close flatten §6.1b, margin hold/flatten §6.3) are their
  own machinery — I11 proves a raced-in fill *reaches* them, not that each backstop is itself
  audited. Name any that need their own slice.
* **D3.442 (daemon-wiring = I1 capstone), D3.441, D3.428, D3.434, D3.438, D3.439, D3.430–D3.433,
  D3.440, D3.359/360/361/363** — standing named debt, not this slice.

## BADGE VERDICT

**Limiter STAYS RED — clean set becomes `{I2, I5, I6, I7, I8, I10, I11} = 7/12`, open = 5**, if I11
is discharged (complete + selective cancellation on both onset types, race backstop proven, gated
with a demonstrated FAIL incl. the completeness CANNOT_MEASURE arm). **Redraw the board on bank.**
Remaining open: **I1** (daemon-wiring capstone), **I3, I4, I9, I12**.

## POST-WRITE-BACK RE-MEASURE — predict, then measure at the derived tip

Default prediction **unchanged from 044's final** — extending the existing onset gate moves no count
(rule 8 / Part C.9): `verify.py` `90 | 3 | 2 | 0 | 1`, exit 1. Predict `passed+1` **only** if S4
genuinely creates a new gate file (it should not). Three standing fails unchanged. Name the
arc-boundary exclusion re-point (045 → next arc) in advance, and write the ARC series row so
`check_derived_claims` does not fire.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` (dogfood),
pulse+motion, ~5-min cadence holding inside any long op, STALL WARNING after ~15 min no motion, GIT
WINS over prose. Verified watchdog teardown before the marker, matched by cc's own signature,
ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending the gate.
