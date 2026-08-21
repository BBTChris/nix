# ARC 055 — I1 ARC C1: the stop protective-exit path (poll + maintain + breach → flatten)

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This is I1 slice 6 (ARC C1 — the first of a split
ARC C) — the invariant count STAYS 11/12** (I1 discharges only at ARC D's convergence gate). **No
board redraw for the count.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `58c9582` (approximate — ARC 054's write-back).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — this wires the **self-preservation core** (a position's protective stop actually
firing) into the running daemon; concurrency (hot-path poll vs off-path send) and safety are the
whole arc.
**Commit is CHEAP** (052). New module file ⇒ `pytest --testmon` once first (D3.466). New config knob
⇒ a `_derivations` origin entry, not just `_meta` (the 053 miss).

## The ARC C split (stated up front — memory #22)

ARC C builds the daemon's entire protective-exit path (the recon: the running daemon imports no
`flatten`/`freshness`/`session`; 054 constructed a `ProtectiveFlatten` whose broker has NO `flatten`
verb and whose §4 sinks RAISE, so it cannot fire even in principle). That is two arcs:

* **C1 (THIS arc): the STOP path** — price-poll + stop-maintain (trailing) + breach → a protective
  flatten is **fired and sent** when a synthetic stop is breached. This is the primary protection
  (every filled position has a stop) and discharges **D3.451**. **Needs no architect ruling.**
* **C2 (next): the three UNCERTAINTY producers** — D3.453 (stale-price), D3.372 (not-tradable fill),
  D3.469 (filled-but-undetailed), reusing C1's send machinery. **Applies the architect rulings.**
* **D: flatten COMPLETIONS** (the closing fills come back → §12.10 closed rows → position closes →
  release) **+ the convergence gate** that flips 11/12 → 12/12.

C1 ends at "**a protective flatten is correctly fired and sent to the sender thread**." The closing
fill coming back and the books reconciling is **ARC D**, not this arc.

## What C1 wires — and the two constraints that make it hard

ARC 047 **armed** synthetic stops on fill (`StopBook.arm`). D3.451: they are **never maintained
(trailed) and never breached (fired)** — an armed stop that does nothing is not protection. C1
makes the daemon:
1. **Price-poll (§5:322)** — read the shared-mem price ring on the loop's tick.
2. **Stop-maintain (§7.4, D3.451)** — trail the armed stops toward price, **monotonic — a trailing
   stop only ever tightens, never loosens** (`trail_ticks` immutable §7.4).
3. **Breach → fire** — when price crosses a stop level, fire a protective flatten for that position,
   **exactly once per breach** (mark the position flatten-in-flight; a subsequent tick must NOT
   re-fire — double-flatten is a real defect).
4. **Send** — the flatten reaches the venue via the **in-process, wire-free** exit path (I3), the
   send done off the hot path on the sender thread (§5).

**Constraint 1 — I9 must not break.** The poll + maintain + breach run on the **hot path** (every
tick). I9 (discharged, 050) says the hot path is cache-reads + arithmetic + the O(positions ≤ 5)
stop-eval ONLY — no I/O, no blocking. So the breach **detects and ENQUEUES** the flatten (pure,
non-blocking); the **sender thread SENDS** it (§5 — the hot loop never blocks; blocking I/O lives on
the low-priority sender thread). **C1 must prove I9 still holds over the new hot-path code** — adding
a blocking send to the hot path would silently break a discharged invariant. Re-run / extend
`check_hot_path_purity` over the new poll code.

**Constraint 2 — I3 must not break.** The flatten send is the protective exit; I3 (discharged, 048)
says it has zero wire dependency. C1's send path must stay wire-free (in-process broker call, no
Allocator/ZMQ/state-bus) — re-confirm against `check_flatten` ARM 6.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Framing.** Echo `TIER = INTERIOR`, `I1 ARC C1 (stop path, first of the C split)`. Confirm clean
   `= 11/12`, open = 1 (I1). **State: this wires the stop protective-exit (poll+maintain+breach+send);
   it does NOT discharge I1; the count stays 11/12 until ARC D. The completion path is ARC D.**
2. **The two do-not-break invariants.** I9 (hot-path purity) and I3 (exit-path wire-freedom) are
   discharged; C1's new hot-path poll and send path must preserve both — this arc RE-PROVES them over
   its own new code, it does not get to assume them.
3. **Process + ops lessons (memory #19/#20/#22/#23):** MEASURE the tip with `verify.py` FIRST (054
   closed `93|4|3|0`; `check_arc_status_contract` should now read PASS auditing `arc_054.log` at this
   baseline — the D3.464 duty-cycle self-correction). Scope lint-fix to CHANGED files. `--basetemp`
   OUTSIDE `~/nix` (`/var/tmp/arc055_pt`). Run the two tripwire tests explicitly. `arc_heartbeat.sh`
   from the start. inode gate + basetemp clean; scratch DBs at teardown; kill by PID.

## S1 — REPRODUCE on the live loop: armed stops that do nothing

Bind to the real loop, the armed stops (047), and I3's `ProtectiveFlatten` (048, wire-free — call,
don't change). On a running `limiterd` with a filled position and an armed stop at a known level:
* **No maintain:** advance price favorably → prove the stop does **not** trail (stays at the arm
  level, D3.451).
* **No breach:** advance price **through** the stop level → prove **nothing fires**: no protective
  flatten, the position stays open with price past its stop — the position is effectively unprotected
  in the running daemon even though the stop is "armed."
* **Non-vacuity:** prove the stop was genuinely armed at a real level and price genuinely crossed it,
  before "did not fire" means anything.

## S2 — WIRE poll + maintain + breach + send

* **Poll (§5:322):** read the price ring on the tick — a cache read, hot-path-pure (I9).
* **Maintain (§7.4):** trail each armed stop toward price, **monotonic** — a helper that can loosen a
  stop is the defect; the trail only tightens. O(positions ≤ 5)/tick (§15).
* **Breach:** price crossing a stop ⇒ fire a protective flatten for that position, **once** — mark
  the position flatten-in-flight so the next tick does not re-fire. Enqueue to the sender thread;
  **do not block the hot loop** (§5, I9).
* **Send:** the daemon's broker gains a real `flatten` verb (054 measured `hasattr==False`); wire the
  send fan-out for the flatten path (the **completion** sinks stay raising — that's ARC D). The send
  is the in-process wire-free path (I3).
* Cite **§5 / §7.4 / §4 / §12.1 / §15**. **NO retry, NO auto-resend.** **Freeze** I3's
  `ProtectiveFlatten`/`flatten.py` (call, don't change), the onset dispatch (054), the fill path
  (047), reject/timeout (053), I2's release, the two-phase state, the freshness files, the sole-writer
  seam, the mirror. The three uncertainty producers (D3.453/372/469) are **C2, not here**.

## S3 — PROVE THE DAEMON DOES IT (watched past the tick)

Real `limiterd` + stub broker (now with a `flatten` verb) + real ledger:
* **Breach fires:** armed stop, price crosses → exactly one protective flatten fired for that
  position, sent via the in-process broker (assert the send happened off the hot path).
* **Trailing is monotonic:** price moves favorably → the stop tightens; price then retraces (but not
  to the trailed level) → the stop does **not** loosen; price crosses the trailed level → breach
  fires. §7.4.
* **Fire-once:** a breached position marked flatten-in-flight does **not** re-fire on the next tick
  (no double-flatten) — assert one flatten per breach across N further ticks.
* **I9 preserved:** the poll + maintain + breach transitively perform only cache-reads + arithmetic +
  the O(≤5) stop-eval — **no I/O, no blocking, on the hot path** (trace it; the send is off-path on
  the sender thread). **I3 preserved:** the send touches no wire.
* Watch past the tick (§0a). Non-vacuity throughout.

## S4 — the gate (census; and re-prove I9/I3 over the new code)

Census the owners: stop-maintenance/breach is new; the daemon SEND is dispatch
(`check_limiter_daemon_dispatch`); wire-freedom is `check_flatten` ARM 6 (I3); hot-path purity is
`check_hot_path_purity` (I9). Extend the right owners (rule 8 / C.9); a genuinely new
stop-maintenance property may need `check_stop_maintenance` (+1 — state from the census). Obligations:
* **The daemon fires a protective flatten on breach** (driven, via the loop's poll — not a direct
  call), **exactly once per breach** (the fire-once / no-double-flatten assertion).
* **The trail is monotonic** (a loosening trail is a FAIL).
* **I9 re-proven over the new poll code** (the hot path stays pure — the new poll must appear in
  `check_hot_path_purity`'s allow-set census or it is CANNOT_MEASURE) and **I3 re-proven** (the send
  is wire-free).
* **The rule-4 plant-both test** (standing boilerplate).

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A (the dangerous one — breach not fired)** — the poll misses a breach: price past the stop,
  no flatten, position open ⇒ `fail`, exit 1, names the unprotected position and the breached level.
* **PLANT B (loosening trail)** — the maintain moves a stop AWAY from price ⇒ `fail`, exit 1, §7.4
  named.
* **PLANT C (double-flatten)** — a breached position re-fires next tick ⇒ `fail`, exit 1, names the
  second flatten.
* **PLANT D (I9 broken)** — an I/O/blocking op inserted on the poll path ⇒ `check_hot_path_purity`
  catches it (this arc must not silently break a discharged invariant).
* Plants removed ⇒ exit 0. Non-vacuity: a real armed stop, a real breach, before any verdict. Exit
  0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `limiterd.py` (the poll + maintain + breach dispatch + the send wiring), `StopBook`
maintain/breached (name the module/functions — likely `stops.py`), the broker `flatten` verb wiring,
the new/extended gate(s) + tests, `docs/CHECK-DEBT.md`. **Byte-identical (prove with `git hash-object`):**
I3's `flatten.py`/`ProtectiveFlatten` (call, don't change), the onset dispatch (054), I2's
`outcomes.py`/`reservations.py`, the fill path, reject/timeout (053), the two-phase state, the
freshness files, the sole-writer seam, `picture.py`/mirror. Name any `uncalled_entry_points_baseline.json`
ratchet movement.

## CLOSE-OUT — INTERIOR tier, commit CHEAP

Run: **(b)** DERIVED reverse-dependency closure + the D3.444 by-detection backstop (the new
`limiterd → stops`/`flatten` edges); non-vacuity proven, RED-before/GREEN-after on this arc's own
defect (a breach not firing, specifically). **(c)** the gate(s) BOUND from all four plants (A/B/C
exit 1, D via the I9 gate) plus the rule-4 plant-both. **(d)** CHECK-DEBT + the ARC-TOTAL series row
written and re-derived whole.

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** The stop path is wired; the **three uncertainty producers** (C2 —
  D3.453/372/469) and the **flatten completions + convergence gate** (D) remain. Count stays 11/12.
* **The completion path is ARC D** — C1 fires and sends; the closing fill coming back, the §12.10
  closed row, the position close, and the release are D. A flatten sent by C1 is in-flight until D
  reconciles it; C1's fire-once prevents re-fire in the interim.
* **D3.451 discharged** (stops now maintained + breached). **D3.470** (the daemon dispatches onset
  but does not DETECT it — detection is later-module work) unchanged.
* D3.372/453/469 (C2), D3.458, D3.468, D3.466/467/471/472, D3.450, D3.428, D3.434, D3.438–D3.472,
  D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 11/12.** I1 path-progress: cancel + fill + reject + pending-timeout
+ onset + **stop protective-exit** wired; the uncertainty producers (C2) and the convergence gate (D)
remain. **No board redraw** (nudge the tail annotation: "stop-exit wired; C2 producers + D next").

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived tip, record the baseline (054 closed `93|4|3|0`; expect
`check_arc_status_contract` PASS on `arc_054.log` now — the duty-cycle self-correction, so baseline
may read `94|4|2|0`), THEN predict only this arc's DELTA:
* a NEW `check_stop_maintenance` gate (if genuinely unowned) → `passed +1`; extending existing owners
  → no count move. **State which from the census.**
* the clean-set stays **11/12** (no flip);
* account for the guard's stable state and the `.dmg`.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start. Verified watchdog teardown before the marker, matched by cc's own signature with POSITIVE
identification (D3.465), ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when
building/extending a gate.
**After the marker, PUSH: `git push origin` — the stop protective-exit is now in the daemon and
origin is 50+ behind (memory #21, unsafe to defer).**
