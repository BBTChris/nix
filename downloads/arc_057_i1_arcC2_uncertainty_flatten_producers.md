# ARC 057 — I1 ARC C2: the uncertainty flatten producers (every unprotectable position → §14 flat)

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This is I1 slice 7 (ARC C2 — second of the C
split) — the invariant count STAYS 11/12** (I1 discharges only at ARC D's convergence gate). **No
board redraw for the count.** On bank, **D3.442's protective-flatten path is fully wired** (C1 the
stop producer, C2 the uncertainty producers); only ARC D (completions + convergence) remains.
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `eb2e853` (approximate — ARC 056's write-back).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — the "flatten what you cannot protect" producers; §14 is the safety spine.
**Commit is CHEAP** (052). Cite trailing authority as **§4:187-196** (not §7.4). New config knob ⇒ a
`_derivations` origin entry.

## The invariant this serves — §14

**§14: every uncertainty resolves toward flat.** C1 wired the STOP protective-exit (a breached stop →
flatten). This arc wires the **four uncertainty producers** — the conditions where the daemon holds
(or the venue holds) a position it **cannot protect or cannot account for**, each of which must fire a
protective flatten (`reason = uncertainty`) through **C1's already-proven send machinery**
(`ProtectiveFlatten` → sender thread, off the hot path (I9), wire-free (I3)). All four have been
detected and named by prior arcs; none has a flatten producer:

1. **D3.453 — stale open position.** §6.4's flatten-open half: an OPEN position whose price feed has
   gone stale past threshold cannot be managed → flatten it. (I12 built the stale *detection*
   ; the flatten-open producer is owed.)
2. **D3.372 — not-tradable confirmed fill.** A fill whose origin-write is refused (`UntradableSymbol`,
   §4:198) → a real venue position with no stop → flatten (the architect ruling: flatten, don't
   publish; root fix = deny-at-approval, noted, not this arc).
3. **D3.469 — poll-discovered filled-but-undetailed.** The pending-timeout poll (053) sees `filled`
   but the status seam can't carry the exec detail to convert. Ruling: HOLD for a **bounded
   reconciliation window** (the real exec-report normally arrives and converts); on window expiry →
   flatten (an unaccountable filled position).
4. **D3.475 — un-armable fill's VENUE half.** ARC 056 releases the reservation on an un-armable
   trailing fill, but a real venue position with no synthetic stop can remain → flatten (§14). The
   reservation half is closed; this is the venue half.

**Common shape:** detect the condition (all four detectors already exist) → fire ONE
`uncertainty` protective flatten for the affected position via C1's machinery → fire-once →
off-hot-path, wire-free. **The producers are the work; the send is C1's.**

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Framing.** Echo `TIER = INTERIOR`, `I1 ARC C2 (uncertainty producers, second of the C split)`.
   Confirm clean `= 11/12`, open = 1 (I1). **State: this wires the four uncertainty flatten
   producers; it does NOT discharge I1; the count stays 11/12 until ARC D. On bank, D3.442's
   protective-flatten is fully wired.**
2. **§14 is the safety spine.** Every one of the four is a real position that is unprotected or
   unaccountable; the producer's job is to resolve it toward flat. A producer that detects but does
   not fire leaves an unprotected live position — the exact hazard.
3. **Reuse C1, do not change it.** `stopwatch.py`/`ProtectiveFlatten`/the sender-thread send are
   proven (055) and frozen here — the producers CALL them. One shared `ProtectiveFlatten` and one
   `_closed` book (054), so §4's arbiter stays single.
4. **The D3.469 reconciliation window may be the moderate part** — if it balloons (it's a §4-poll
   timer interaction), split it to its own named micro-slice and land the other three; state the call.
5. **Process + ops lessons (memory #19/#20/#22/#23/#25/#27):** MEASURE the tip with `verify.py` FIRST
   (056 closed `94|4|3|0`; **predict `check_arc_status_contract` from `arc_056.log`'s completeness —
   056 wrote its marker into its log, so expect PASS auditing `arc_056.log`, clearing one cannot-
   measure to ~`95|4|2|0`; state the measured value**). Scope lint-fix to CHANGED files. `--basetemp`
   OUTSIDE `~/nix` (`/var/tmp/arc057_pt`). Run the two tripwire tests explicitly. `arc_heartbeat.sh`
   from the start — tee BOTH the selfcheck line AND the completion marker INTO `arc_057.log` (the
   recurring D3.464 gap). inode gate + basetemp clean; scratch DBs at teardown; kill by PID.

## S1 — REPRODUCE all four gaps on the live loop

Each detector exists; none fires a flatten. On a real `limiterd`, drive each condition and prove the
uncertain position survives unflattened:
* **stale-open:** an OPEN position, its symbol's price stamp aged past threshold → prove nothing
  flattens it (I12 denies new entries; the open position is untouched — D3.453).
* **not-tradable fill:** a confirmed fill on a symbol whose origin-write refuses → prove the venue
  position is not flattened (D3.372).
* **undetailed poll-fill:** the pending-timeout poll resolves `filled` without exec detail → prove
  nothing reconciles or flattens (D3.469).
* **un-armable venue half:** an un-armable trailing fill (056 released the reservation) → prove a
  venue position can remain with no stop and no flatten (D3.475).
* **Non-vacuity:** prove each is a REAL open/venue position and the condition genuinely holds before
  "not flattened" means anything.

## S2 — WIRE THE FOUR PRODUCERS (each → one uncertainty flatten via C1)

* Each producer, on its condition, fires **one** `ProtectiveFlatten` with `reason = uncertainty` for
  the affected position, enqueued to the sender thread (off the hot path, I9; wire-free, I3).
  **Fire-once** per condition (the C1 flatten-in-flight discipline).
* **D3.469 specifically:** on poll `filled`-without-detail, HOLD and set a bounded reconciliation
  deadline; if the real exec-report arrives first → convert normally (cancel the pending flatten); if
  the deadline expires first → flatten. Do NOT flatten immediately (the delayed-but-valid case is the
  common one).
* Cite **§14 / §6.4 / §4:198 / §4**. **NO retry, NO auto-resend.** **Freeze** C1's
  `stopwatch.py`/`ProtectiveFlatten`/send (call, don't change), the fill path (056), the two-phase
  state, I2's release, the freshness *detection* (051 — call it, don't change), the sole-writer seam,
  the mirror. The producers live in the daemon (`limiterd.py`) + their detection seams.

## S3 — PROVE EACH FIRES ON THE DAEMON (watched past the tick)

Real `limiterd` + stub broker (with `flatten`) + real ledger, each condition driven:
* each of the four → **exactly one** `uncertainty` protective flatten for the affected position,
  `executed=[true]`, sent on the sender thread's tid (off the hot path), wire-free;
* **fire-once:** the condition persisting across N further ticks does not re-fire;
* **D3.469 both branches:** exec-report-arrives-first → convert, no flatten; deadline-first → flatten;
* **the shared arbiter:** a position that is both onset-swept and uncertainty-flattened resolves once
  (one `_closed` book, §4);
* **I9/I3 preserved:** any new per-tick detection (the stale-open scan) stays hot-path-pure (O(≤5)
  positions, no I/O); the sends stay wire-free.
* Watch past the tick. Non-vacuity throughout.

## S4 — the gate (extend the flatten/dispatch owners; producer completeness)

Census: the flatten SEND/producers belong to `check_limiter_daemon_dispatch` (dispatch) and/or
`check_stop_maintenance` (the daemon's flatten machinery, 055); §14's uncertainty semantics may touch
`check_flatten`. Extend the right owner(s) (rule 8 / C.9); a genuinely new uncertainty-producer
property may need its own gate (+1 — state from the census). Obligations:
* **each of the four producers fires** on its condition (driven, via the daemon — not a direct call);
* **producer completeness by derivation** — the set of uncertainty conditions the daemon flattens
  equals the set named (D3.453/372/469/475); a fifth unprotectable condition added later without a
  producer is the exact defect, so assert the set, and a condition it can't classify ⇒
  CANNOT_MEASURE naming it;
* **the rule-4 plant-both test.**

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (a producer that detects but does not fire)** — the stale-open (or any one) condition
  holds, no flatten ⇒ `fail`, exit 1, names the unprotected position and the condition.
* **PLANT B (D3.469 flattens too eagerly)** — the flatten fires before the reconciliation deadline,
  killing a position whose exec-report was merely delayed ⇒ `fail`, exit 1.
* **PLANT C (double-flatten)** — a condition re-fires ⇒ `fail`, exit 1.
* **PLANT D (incomplete producer set)** — a named uncertainty condition with no producer ⇒ `fail`
  (or CANNOT_MEASURE if unclassifiable), naming it.
* Plants removed ⇒ exit 0. Non-vacuity: a real unprotected position before any verdict. Exit 0/1/2;
  fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `limiterd.py` (the four producers + the stale-open scan + the D3.469 window), the
detection seams they read (name them), the gate(s) + tests, `docs/CHECK-DEBT.md`. **Byte-identical
(prove with `git hash-object`):** C1's `stopwatch.py`/`ProtectiveFlatten`/`flatten.py` (call, don't
change), the fill path (`fills.py`/`seam.py`/`stops.py` from 056), the freshness *detection*
(`freshness.py` — called, not changed), I2's `outcomes.py`/`reservations.py`, the two-phase state,
the sole-writer seam, `picture.py`/mirror. Name any `uncalled_entry_points_baseline.json` movement
(the flatten machinery symbols become producer-called — a shrink).

## CLOSE-OUT — INTERIOR tier, commit CHEAP

Run: **(b)** DERIVED reverse-dependency closure + the D3.444 by-detection backstop; non-vacuity
proven, RED-before/GREEN-after on this arc's own defect (an uncertain position surviving unflattened,
specifically). **(c)** the gate(s) BOUND from all plants (A/B/C/D) plus the rule-4 plant-both, **AND
`check_hot_path_purity` + `check_flatten` shown PASS at the merged tree** (I9/I3 not regressed by the
new stale-open scan and sends). **(d)** CHECK-DEBT + the ARC-TOTAL series row re-derived whole.

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** Only **ARC D** remains — flatten COMPLETIONS (the closing fills come back
  → §12.10 `closed` rows → position closes → release) + the **convergence gate** that flips 11/12 →
  12/12. Count stays 11/12.
* **D3.442's protective-flatten is now FULLY wired** (stop C1 + uncertainty C2); restate it.
* **D3.372's root fix (deny-at-approval for not-tradable)** — noted, belongs wherever the tick-size
  approval check lives; C2 flattens the symptom per §14, it does not add the approval-deny.
* **D3.476** (`nixalloc/sizing.py` no trail distance — Allocator module), **D3.473/470/468** (real
  prices / onset detection / status-directory producers — later modules), **D3.477** (inherited
  drifted test) — unchanged.
* D3.458, D3.450, D3.466/467/471/472, D3.428, D3.434, D3.438–D3.477, D3.359/360/361/363 — standing debt.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 11/12.** On bank: D3.442's protective-flatten fully wired; **ARC D is
the only thing between the Limiter and 12/12.** No board redraw for the count (nudge the tail
annotation: "all producers wired; only ARC D — completions + convergence — remains").

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19/#27)

Run `verify.py` at the derived tip, record the baseline (056 closed `94|4|3|0`; **predict
`check_arc_status_contract` PASS auditing `arc_056.log` — memory #27 — so the baseline likely reads
`95|4|2|0`; state the measured value**), THEN predict this arc's DELTA:
* a NEW uncertainty-producer gate (if genuinely unowned) → `passed +1`; extending existing owners →
  no count move. **State which from the census.**
* the clean-set stays **11/12** (no flip); I9/I3 gates stay PASS (no-regression).
* account for the guard's stable state and the `.dmg`.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start, tee-ing BOTH the selfcheck line AND the marker into `arc_057.log` (memory #27). Verified
watchdog teardown before the marker, matched by cc's own signature with POSITIVE identification
(D3.465), ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when touching a gate.
**After the marker, PUSH: `git push origin` — all protective-flatten producers are now in the daemon
and origin is 50+ behind (memory #21, unsafe to defer).**
