# ARC 040 — ULTRAREVIEW: Limiter — slice 2: GO-timeout (I5)

**Module under audit:** Risk Engine / Limiter (Core 2). RED (ARC 038 pass 1: 2/12 clean, 13 block).
**This slice:** implement **I5, the GO-timeout** — the §14 safety invariant ARC 038 found has NO
implementation. ONE invariant, discharged and re-audited, in the hour.
**Tier:** INTERIOR (the Limiter badge stays RED; this is not the greening slice).
**Predecessor:** ARC 039R (merged; slice 1 = the running loop; HEAD `39b8a45`).
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Target run time:** ~1 hour. **Heartbeat cadence: ~5 minutes.** Split rather than balloon.

---

## THE SLICE

ARC 038's finding: **§14's GO-timeout has no implementation.** A real SIGKILL of the GO holder left
the in-flight lock still HELD **11.0s past a 10s knob**, because no shipped site measures elapsed time
against the timeout. The §4 deadlock-breaker exists as a knob nobody reads. Slice 1 (ARC 039) stood up
the running loop with the in-flight lock as **live state** and a **clock**; THIS slice makes the loop
**enforce the timeout against that clock**.

**One invariant. Do not grow scope.** I5 only. The other 12 invariants (I1–I4, I6–I12) are later
slices.

---

## §0a — self-audit, this slice
*What would make this pass while measuring nothing?* A timeout that never fires (the knob still unread,
038's exact bug, but now with a green test beside it); a release that fires on EVERY GO including
healthy ones (order flow shredded, but "the timeout works!"); a gate green over the knob-present-but-
unread state that IS 038's bug. **The fix must be proven in BOTH directions: it fires on a real kill,
and it does NOT fire on a GO that got normal feedback.** Reproduce the defect before fixing it — a fix
for a defect you didn't first measure is measuring nothing.

## §0b–§0j standing (resolve labels to ledger ids).

---

## PHASE 0 — Pre-flight, kickoff, freeze, baseline (SERIAL, short)

**0.0 — OPS-HYGIENE PRE-FLIGHT (before anything).** Check `df -i /tmp` inode headroom; if no pytest is
running, clean stale `pytest-of-*/` basetemps (ARC 039R died with "No space left" at 16GB free because
tmpfs was OUT OF INODES — ~1M held by 32 leaked basetemps). Report headroom before/after.

**0.1 — STATUS CONTRACT KICKOFF.** Echo total stage count (fixed) + declare TIER: INTERIOR. Stand up
the BACKGROUND HEARTBEAT WATCHDOG on its own ~5-min timer (independent process; emits from live state;
survives a blocked foreground). **SELF-VERIFY it** — read its output back, prove ≥1 heartbeat before
proceeding. Capture its REAL pid from its own self-report (setsid re-forks; `$!` names the wrapper, not
the daemon — the 039R trap). The main run writes stage+op-% to `scratchpad/arc_progress.txt` stamped
with arc id 040 + a monotonic timestamp; the watchdog verifies the stamp is THIS arc and advancing
(else "STALE PROGRESS FILE"). Heartbeats show overall-% AND motion; ≥3 still intervals ⇒ STALL WARNING;
~5-min cadence holds INSIDE any long op (poll its %, re-emit).

**0.2 — OPS HYGIENE (standing, every step).** NEVER `pkill -f` / `pgrep -af` on cc's own process-name
patterns — it matches cc's OWN wrapper shell and has killed the pipeline three times (038/039/039R).
Kill BY PID from the daemon's self-report; filter the wrapper when searching. The kernel thread
`[watchdogd]` is ALWAYS present, root-owned, NOT cc's watchdog — never try to kill it, never treat it as
a leak; match cc's watchdog by its `watchdog.py` signature.

**0.3 — Re-measure on trunk, stating the interpreter.** Expect ARC 039R's close: verify.py
`88 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded`, exit 1; HEAD `39b8a45`; ledger 376.
**Any delta is a finding.** Discharge or re-own `check_artifact_gate_coverage` (owner ARC 040 per 039R).

**0.4 — FREEZE.** The only production change this slice makes is the GO-timeout enforcement in the loop
+ its gate. A change to any other invariant's logic is out of scope and itself a finding. Record the
frozen SHAs of every Limiter file.

**0.5 — Read the spec directly:** §4 (GO contract, one-in-flight-per-strategy, the GO-timeout /
deadlock-breaker, the no-retry/no-auto-resend rule), §5 (the single-threaded loop this runs in), §12.1
(the heartbeat clock).

---

## THE WORK

**S1 — Reproduce 038's finding FIRST, against the live loop.** Drive a GO into the running `limiterd`,
SIGKILL the GO holder (the Allocator side) by PID, and MEASURE that the in-flight lock is still held
past the timeout knob (038 measured 11.0s past 10s). Confirm the defect is real and present **before**
fixing it.

**S2 — Implement the GO-timeout.** The single-threaded loop (§5) measures elapsed wall-clock since each
GO was admitted, against the §4 timeout knob; when a GO exceeds it with no terminal feedback, the loop
breaks the deadlock — **releases the in-flight lock and returns the strategy to flat-and-free** (§4's
deadlock-breaker). Elapsed time is measured on the loop's own clock (the slice-1 heartbeat clock), not
a wall-clock read at a random call site. **NO retry, NO auto-resend (§4 forbids it)** — the timeout
RELEASES, it does not re-place. A retry here silently converts one intended order into two.

**S3 — Prove the fix against a REAL kill, both directions.** (a) Repeat S1: GO admitted, holder
SIGKILLed → prove the lock is released within the knob (not 11s past it), the strategy is flat-and-free,
order flow is not wedged. (b) Prove it does NOT fire early: a GO that gets normal terminal feedback
before the timeout is untouched — no false release. Both directions, or the invariant isn't proven.

**S4 — Ship `check_go_timeout` with a demonstrated FAIL.** Plant the defect (the timeout knob present
but unread — exactly 038's real state) and confirm the gate reddens and NAMES the unread site; remove
the plant, confirm it passes; prove non-vacuity (the gate's scope contains a real running loop with a
real admitted GO) before trusting green. Exit 0/1/2, fail closed, assert the REASON not the exit code.

---

## INTERIOR-TIER CLOSE-OUT (cost-aware — target ~15min)

**(a)** verify.py on trunk, stating the interpreter — must hold `88/2/2/0/1`. Any delta a finding,
named. Baseline: `check_ibgateway_service` FAIL (tap) + `check_uncalled_entry_points` standing + the
standing cannot-measures.

**(b)** The DERIVED reverse-dependency test closure ONLY — derive from the tree (grep imports) the
tests exercising the changed files (`loop.py`, `limiterd.py`, `check_go_timeout.py` + any GO / in-flight-
lock tests), plus their importers. PROVE the closure is non-vacuous (it actually contains the changed
files' dependents) before trusting green. **COST-AWARE:** DETECT any test that itself shells out to
verify.py / the binding census / the full suite (e.g. `test_end_to_end` ran a full `verify.py --verbose`
and blew 039R's budget) and EXCLUDE it (defer to the greening slice) or explicitly time-box it. Do NOT
run the full ~3400 pytest or the full binding census.

**(c)** Confirm `check_go_timeout` is BOUND from its observed real FAIL.

**(d)** CHECK-DEBT reconcile.

---

## WRITE-BACK & BANK

1. Append the slice summary to the END of `sessions/SESSION.md`.
2. **OVERWRITE** `downloads/RESULTS.md`. RECORD that this was INTERIOR tier (full pytest + full census
   DEFERRED to the Limiter's greening slice, per the tiered rule) — a stated decision, not a silent
   skip.
3. Re-point `check_artifact_gate_coverage` exclusions ARC 040 → ARC 041 BEFORE the write-back (the
   guard-survival pattern).
4. Run any predicted post-write-back re-measure and BANK it BEFORE the marker (§0j). `cat` both files as
   the final action. Prove HEAD advanced past `39b8a45` (§0d). State the absolute canonical path.
5. **VERIFIED WATCHDOG TEARDOWN:** kill cc's watchdog by its captured pid and PROVE IT DIED — `pgrep`
   for cc's `watchdog.py` signature is empty (IGNORE the kernel `[watchdogd]`, always present, not cc's)
   — BEFORE the marker. Startup was self-verified, so teardown is too.
6. Clean up temp files and any worktrees (`git worktree list` shows only `/home/bbt/nix`).

**BADGE VERDICT:** Limiter STAYS RED — I5 discharged, but 11 more invariants open from 038's pass 1.
Name what's discharged (I5) and what slice 3 targets (I7 commit-before-validate torn state + I8 sole-
writer enforcement — the next blockers).

**Per §0j: `**** ARC completed ****` is the LAST token, printed once, nothing after it.**

---

## Explicitly NOT in this arc

Any invariant other than I5 · new features · any module other than the Limiter · the production fill
feed / ranking publish · the dashboard · the strategy plug-in · backup/DR · the tap session · the full
pytest / full census (deferred to the greening slice). An ULTRAREVIEW slice that grows past its one
invariant has stopped being a ~1h slice.

---

## Open items returned to the operator / architect

1. **Push** — `main` is ahead of origin after the 039/039R commits. Clean fast-forward; worth backing up
   the audit history.
2. **The tap session** — still the only code-independent FAIL.
3. **SPEC-A10 vendor · branch protection** — operator/outward-facing.
4. **The `check_tmpfs_inode_headroom` gate** (CHECK-DEBT candidate from 039R — nothing measures inode
   headroom, so a run dies confusingly with "No space left" while disk space is free). Build it in a
   future slice or fold into the greening slice's full close-out.
5. **The Limiter slice queue after I5:** slice 3 = I7 torn-state + I8 sole-writer · then I2/I11 release
   bugs · then I1 instrument + the Plane-1 gate-family de-vacuum (I9/I12/FG1). Each a ~1h interior
   slice, staying on the Limiter until every finding discharges and the GREENING slice (full close-out)
   flips the badge green.
