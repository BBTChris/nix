# ARC 054 — I1 ARC B: onset dispatch — build pending_entries() + wire the daemon's onset-cancel sweep

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This is I1 slice 4 (ARC B of the 4-arc daemon
capstone) — the invariant count STAYS 11/12** (I1 discharges only at ARC D's convergence gate). **No
board redraw for the count.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `9e92a38` (approximate — ARC 053's write-back).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — a completeness/absence proof (every pending entry enumerated and cancelled on
onset) plus the safety-critical selectivity (exits untouched) at the daemon level.
**Commit is CHEAP** (052 paid the tax). If a NEW module file is added, run `pytest --testmon` once
before committing it (D3.466). Any NEW config knob needs a `_derivations` origin entry, not just a
`_meta` note (the 053 miss).

## What this arc wires — and its prerequisite

ARC 045 proved I11's onset-cancel **selection** at the library level (blackout/HALT onset cancels all
pending ENTRY orders; exits untouched; `_classify_for_onset` derives admission from the reservation
ledger). ARC 044 wired the reservation **release** on the `BLACKOUT_ONSET`/`HALT_ONSET` paths. **The
running daemon invokes neither** — and it can't, because the sweep's enumeration source has no
production implementation:

* **PREREQUISITE — build `pending_entries()` (D3.443).** The onset sweep iterates the currently-pending
  entry orders; that enumeration is a docstring promise with no producer (D3.349 lineage). Build the
  production `pending_entries()` from the daemon's own order tracking — **complete** (every pending
  entry, derived from order state: PENDING × role ENTRY), so the sweep can never miss one.
* **THEN — wire the onset → sweep dispatch.** The daemon detects onset (edge-triggered:
  not-blackout → blackout **per-symbol**, not-halt → halt **global**) and invokes the onset-cancel
  sweep (I11's `cancel_entries_on_onset`/`_classify_for_onset`, proven — call, don't change) over
  `pending_entries()` → cancels all pending entries (selective, exits untouched) → releases their
  reservations (044's onset paths).

**The two safety halves, both from I11, now proven at the DAEMON level:**
1. **COMPLETE** — the daemon cancels **every** in-scope pending entry on onset; a missed entry fills
   inside a window it was not approved for (§3). `pending_entries()` completeness is what guarantees
   this — an entry the enumeration misses is an entry the sweep never sees.
2. **SELECTIVE (safety-critical)** — the daemon cancels **only** entries; pending exits and protective
   orders are untouched and still fire (§14). I11 proved the selection; ARC B proves the daemon's
   invocation preserves it. Cancelling a stop on onset unprotects a live position — the 045 live bug,
   which must not reappear at the daemon boundary.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Framing.** Echo `TIER = INTERIOR`, `I1 ARC B (slice 4 of the capstone)`. Confirm clean `= 11/12`,
   open = 1 (I1). **State: this builds `pending_entries()` + wires the onset sweep; it does NOT
   discharge I1; the count stays 11/12 until ARC D.**
2. **Scope of onset.** Blackout onset is **per-symbol** (a symbol entering its EOD/EOW/news/roll
   window — the sweep cancels that symbol's pending entries only); HALT onset is **global** (all
   pending entries). Edge-triggered — fire once per onset transition, not every tick while the state
   persists (idempotent if it does re-fire, but prove it's edge-driven).
3. **Process + ops lessons (memory #19/#20/#22/#23):** MEASURE the tip with `verify.py` FIRST (053
   closed `94|4|2|0|0`). Scope lint-fix to CHANGED files. `--basetemp` OUTSIDE `~/nix`
   (`/var/tmp/arc054_pt`). Run `test_check_order_path_bans` + `test_check_uncalled_entry_points`
   explicitly. `arc_heartbeat.sh` from the start (marker tees to the log — 052 fix). inode gate +
   basetemp clean; scratch DBs at teardown; kill by PID.

## S1 — REPRODUCE BOTH GAPS on the live loop

Bind to the real loop, I11's selection (`flatten.py`/`blackout.py`, 045), and 044's onset release.
* **`pending_entries()` absent/incomplete:** show the sweep has no production enumeration to iterate —
  a `Sequence[object]` promise with no producer (D3.443). Stage pending entries and show the daemon
  cannot enumerate them for the sweep.
* **Onset dispatch absent:** drive a blackout onset (per-symbol) and a HALT onset (global) with pending
  entries + a pending exit/protective order staged → **prove the daemon does NOT sweep**: pending
  entries survive the onset, still working inside the window; and confirm what the daemon does to the
  exit (it must end up untouched, but show the dispatch isn't happening at all).
* **Non-vacuity:** prove the staged entries were genuinely pending and the onset genuinely fired,
  before "not swept" means anything; stage a real exit so "exits untouched" is measured against
  something.

## S2 — BUILD THE ENUMERATION, THEN WIRE THE SWEEP

* **`pending_entries()`** — derive the pending-entry set from the daemon's order state (PENDING ×
  role ENTRY), complete by construction; not a hand-list. Its completeness is the load-bearing
  property — an entry it omits is an entry the sweep never cancels.
* **Onset dispatch** — the loop detects the onset transition (per-symbol blackout / global HALT),
  invokes `cancel_entries_on_onset` over `pending_entries()` (scoped correctly), and the release runs
  on the 044 path. Edge-triggered. **Call I11's selection and I2's release — do NOT re-implement or
  edit them** (`flatten.py`/`blackout.py` and `outcomes.py`/`reservations.py` stay byte-identical).
* Cite **§3 / §6.1 / §15 C4 / §14**. **NO retry, NO auto-resend.** **Freeze** the fill path (047), the
  reject/timeout dispatch (053), the exit-path code (048), the two-phase state (049), the hot-path
  (050), the freshness files (051), I2's release logic (044), the sole-writer seam, the mirror.

## S3 — PROVE THE DAEMON DOES IT, both onset types

Real `limiterd` + stub broker + real ledger, with pending entries (≥2 symbols, ≥2 strategies) + a
pending exit + a protective stop on an open position staged:
* **Blackout onset (per-symbol):** the daemon enumerates that symbol's pending entries via
  `pending_entries()`, cancels **all** of them (none survives), leaves **another symbol's** entries
  untouched (scope), leaves the exit/protective order untouched, releases the cancelled entries'
  reservations (044).
* **HALT onset (global):** every pending entry across all symbols cancelled; exits/protective still
  fire (re-drive a protective exit after HALT onset — it flattens, §14).
* **Completeness (the absence proof):** assert the set the daemon swept equals `pending_entries()`
  equals the pending-entry set in the order state — a pending entry that exists but wasn't swept is
  the exact defect.
* **Edge-triggered:** the sweep fires once on the onset transition; a subsequent tick in the same
  blackout does not re-sweep (or re-sweeps idempotently — prove which).
* Watch past the tick. Non-vacuity throughout.

## S4 — the gate (census: dispatch vs selection; completeness by derivation)

Census the owners: the daemon DISPATCH of the sweep belongs to `check_limiter_daemon_dispatch`
(046's gate); I11's SELECTION already lives in `check_flatten` ARM 3b (045) — do NOT duplicate it.
**Extend `check_limiter_daemon_dispatch`** with the onset arm (rule 8 / C.9), and if
`pending_entries()` completeness needs a home, extend the owner rather than build a second. The
obligations:
* **The daemon sweeps on onset** — driven, via the loop's onset detection, not a direct call.
* **`pending_entries()` completeness by DERIVATION** — the swept set equals the pending-entry set in
  order state; an entry kind the enumeration can't classify ⇒ **CANNOT_MEASURE naming it**, never
  PASS (the I2/I12 completeness lesson).
* **The rule-4 plant-both test** (standing boilerplate).

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (no sweep)** — onset dispatch removed: pending entries survive onset ⇒ `fail`, exit 1,
  names the surviving entry and the window it can now fill in.
* **PLANT B (incomplete enumeration)** — `pending_entries()` misses a pending entry: it survives the
  sweep ⇒ `fail`, exit 1, names the missed entry.
* **PLANT C (over-broad — the dangerous one)** — the daemon's sweep cancels an exit/protective order
  ⇒ `fail`, exit 1, names the cancelled protective order and the position it left unprotected.
* Plants removed ⇒ exit 0. Non-vacuity: real pending entries + a real exit staged before any verdict.
  Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `limiterd.py` (onset dispatch), the `pending_entries()` implementation (name the
module/function), `check_limiter_daemon_dispatch` + its test (and `check_flatten` only if
`pending_entries()` completeness extends it), `docs/CHECK-DEBT.md`. **Byte-identical (prove with
`git hash-object`):** I11's selection (`flatten.py`/`blackout.py` — call, don't change), I2's release
(`outcomes.py`/`reservations.py`), the fill path, the reject/timeout dispatch (053), the exit-path
code, the two-phase state, the hot-path files, the freshness files, the sole-writer seam,
`picture.py`/mirror. Name any `uncalled_entry_points_baseline.json` ratchet movement (I11's selection
symbols become daemon-called — a shrink).

## CLOSE-OUT — INTERIOR tier, commit CHEAP

Run: **(b)** DERIVED reverse-dependency closure + the D3.444 by-detection backstop; non-vacuity
proven, RED-before/GREEN-after on this arc's own defect (a pending entry surviving onset,
specifically). **(c)** the gate BOUND from all three plants (A/B/C exit 1, sites named) plus the
rule-4 plant-both. **(d)** CHECK-DEBT + the ARC-TOTAL series row written and re-derived whole.

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** Onset wired; **protective flatten** (ARC C — D3.453/D3.372/D3.469, the
  daemon has no protective-exit path at all) and the **convergence gate** (ARC D) remain. Count
  stays 11/12.
* **D3.442 shrinks a third time** — restate: cancel/fill/reject/pending-timeout/**onset** daemon-
  invoked; only **protective flatten** still owed (ARC C).
* **D3.468** (the status directory has no producer — future broker-order module) — unchanged.
* ARC C's three flatten producers — **D3.453** (stale price), **D3.372** (not-tradable fill),
  **D3.469** (poll-discovered filled-but-undetailed → bounded reconciliation → UNCERTAINTY flatten,
  the architect ruling) — are ARC C, not this arc.
* D3.450, D3.458, D3.466, D3.467, D3.428, D3.434, D3.438–D3.469, D3.359/360/361/363 — standing debt.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 11/12.** I1 path-progress: cancel + fill + reject + pending-timeout
+ **onset** wired (5 of ~6); only protective flatten remains (ARC C), then the convergence gate (ARC
D) flips 11/12 → 12/12. **No board redraw** (nudge the tail annotation to "5 of 6 wired").

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived tip, record the baseline (053 closed `94|4|2|0|0`), THEN predict only
this arc's DELTA:
* extending `check_limiter_daemon_dispatch` (no new file) → `passed` unchanged; a NEW gate for
  `pending_entries()` completeness (only if genuinely unowned) → `passed +1` (state from the census);
* the clean-set stays **11/12** (no flip);
* `check_uncalled_entry_points` may shrink as I11's selection symbols become daemon-called — name the
  dropped rows;
* `check_arc_status_contract` should PASS auditing `arc_053.log` (the 052 fix); account for the
  guard's stable state and the `.dmg`.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start (marker tees to the log). Verified watchdog teardown before the marker, matched by cc's own
signature with POSITIVE identification (D3.465 fix), ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md`
directly when extending the gate.
**After the marker, PUSH: `git push origin` — the I1 tail is at 5 of 6 and origin is 50+ behind
(memory #21, unsafe to defer).**
