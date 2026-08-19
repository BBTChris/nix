# ARC 039 — ULTRAREVIEW: Limiter — slice 1: the minimal runtime loop

**Module under audit:** Risk Engine / Limiter (Core 2). Still RED (ARC 038 pass 1: 2/12 clean, 13 block).
**This arc's slice:** ONE thing — stand up the minimal **running Limiter process** (§5 single-threaded
event loop + §12.1 heartbeat) that ARC 038's deepest finding said does not exist. **No other slice.**
**Predecessor:** ARC 038 (merged; HEAD `a382298`).
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Target run time:** ~1 hour. **Heartbeat cadence: ~5 minutes.** If the slice can't close in ~1h, split
it — do NOT let it balloon.
**Shape:** small. Phase 0 (freeze + baseline) · Stage 1 (build the minimal loop — 1–2 sub-agents at most)
· Stage 2 (prove it runs, ticks, holds the lock, dies) · Phase 4 close-out. No wide fan-out; the slice
does not decompose into six disjoint pieces and a ~1h arc does not need them.

---

## WHY THIS SLICE, FIRST

ARC 038's deepest finding: *"every invariant proven here is proven about a LIBRARY, not about a running
daemon — there is no Limiter process."* Several blockers (I5 GO-timeout, I9 hot-path-under-load, I7
atomicity-under-concurrent-readers) are properties of **behaviour in a live process over time** and
**cannot be proven against imported functions** — a timeout has no meaning without a clock ticking in a
running loop. So the substrate must exist before the behaviours that depend on it can be audited.

**This arc builds that substrate and nothing else.** It stands up the minimal Risk Engine runtime: a
single-threaded event loop (§5) that ticks on a defined cadence, holds the one-in-flight-per-strategy
lock as live state, exposes a heartbeat the Sentinel could watch (§12.1), and can be started and killed
as a real OS process. **It does NOT fix GO-timeout** (that is slice 2) — it makes GO-timeout *provable*
by giving it a live clock and a real process to kill. Scope discipline: if it isn't required to have a
minimal running, tickable, killable Limiter loop, it is not in this arc.

**Daemon-vs-library, resolved for the phase:** the ULTRAREVIEW of the Limiter proceeds against a **real
running process** from here on. This slice is the decision made concrete — the remaining Limiter slices
audit the daemon, not the library.

---

## §0a — self-audit, this slice
*What would make this pass while measuring nothing?* A "loop" that is really a function called once in a
test; a "heartbeat" that is a variable set once, never advanced by the loop itself; a "kill" that stops
a thread but not a process (so `pgrep` never saw a process to begin with); a lock "held" as a test
fixture rather than as state the running loop owns. **Every proof here must be against a real OS process
observed via `pgrep`/`/proc`, killed with a real signal, its heartbeat advancing on the loop's own
clock — not a library call in the test's own interpreter.** The §0a hazard for this slice: proving the
loop "works" by importing it and calling `.tick()` once, which measures the function, not the daemon.

## §0b–§0j standing (resolve labels to ledger ids).

---

## PHASE 0 — Freeze + baseline (SERIAL, short)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 038's close: verify.py
`87 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded`, exit 1; pytest 3367; binding
BOUND=79; CHECK-DEBT 371. **Any delta is a finding.** Discharge or re-own `check_artifact_gate_coverage`
(owner ARC 039 per the 038 write-back).

**0.2 — Freeze scope.** The only production code this arc adds is the minimal runtime loop and its
entrypoint. It touches NO invariant logic — it does not fix I5/I7/I8/etc. A change to gate/reservation/
exit logic in this arc is out of scope and itself a finding. Record the frozen SHAs.

**0.3 — Read the spec directly** for §5 (threading model: single-threaded Limiter loop + low-priority
sender thread), §2/§2A (Risk Engine process container; broker-order in-process; the command surface the
loop drives), §12.1 (the heartbeat the Sentinel watches), §12.2 (systemd supervision), §11 (the loop's
tick does cache-reads + arithmetic only — the hot-path discipline the loop must not violate even now).

---

## STAGE 1 — Build the minimal runtime loop (small; 1–2 sub-agents max)

**S1.1 — The loop.** A single-threaded event loop (§5) for the Risk Engine / Limiter that:
- **Ticks** on a defined cadence, advancing a monotonic loop counter and a **heartbeat timestamp** on
  its own clock every tick (§12.1 — this is the signal the Sentinel watches for liveness).
- **Owns the one-in-flight-per-strategy lock as live state** — a real structure the running loop holds
  and mutates, not a per-call fixture. (This arc does NOT add the timeout that releases it — slice 2 —
  it just makes the lock a property of the running loop so slice 2 has something real to time out.)
- **Drains an input queue** (GO/feedback/tick events) and a **low-priority sender thread** stub (§5) —
  the sender need not place real orders this arc; it must exist as the separate low-priority thread the
  threading model specifies, so later slices audit the real structure.
- **Exposes a clean start and a clean death** — starts as an OS process, runs, and on SIGKILL/SIGTERM
  leaves the documented state (per §12.2 supervision + boot-flatten: restart = flat).

**S1.2 — The heartbeat is real.** Prove the heartbeat advances *because the loop ticked*, not because a
test set it — read it from outside the process (file/socket/ZMQ per §12.1's intent) and watch it climb
while the loop runs, then stop climbing the instant the process is killed. This is the Sentinel's
liveness signal; if it advances without the loop, the Sentinel would be blind to a dead Limiter (the
exact §12.1 catastrophe), so the check must prove loop-driven advancement.

*(One sub-agent can build the loop + sender-thread skeleton; a second, if used, builds the
heartbeat-exposure + the check. No wider fan-out — this is a ~1h slice.)*

---

## STAGE 2 — Prove it runs, ticks, holds, and dies (SERIAL, the whole point)

**2.1 — It is a real process.** Start it; `pgrep`/`/proc` sees a live process on its own PID; the loop
counter advances; the heartbeat timestamp advances on the loop's clock. Measured from outside the
process, not asserted from inside the test interpreter.

**2.2 — It holds the lock as live state.** Drive a GO in; the running loop marks that strategy
in-flight; a second GO for the same strategy is refused-with-reason **by the running loop**, not by a
library function. (No timeout yet — just prove the lock is live state the loop owns.)

**2.3 — It dies clean.** Real SIGKILL → `pgrep` shows the process gone, the heartbeat stops advancing
(so a watcher can detect death), and the documented restart-is-flat property holds on relaunch. This is
the hook slice 2 (GO-timeout) and a future Sentinel-integration slice both build on.

**2.4 — The check ships with a demonstrated FAIL.** `check_limiter_loop_alive` (or extend an existing
liveness gate — do not duplicate): plant the defect (a heartbeat that advances without the loop; a loop
that isn't a separate process) and confirm the gate reddens and names the site; remove the plant,
confirm it passes; prove non-vacuity (the gate's scope actually contains a running loop) before trusting
green. Exit-code contract 0/1/2, fail closed.

**2.5 — State plainly what this slice did and did NOT do.** It stood up the loop; it did NOT implement
GO-timeout, did NOT enforce sole-writer, did NOT fix the torn-state — those are later slices. The
Limiter badge STAYS RED. Name slice 2 = GO-timeout (I5) against this now-running loop.

---

## PHASE 4 — Close-out (short)

1. `verify.py` on trunk, stating the interpreter. Baseline: `check_ibgateway_service` FAIL (tap) +
   `check_uncalled_entry_points` standing + standing cannot-measures. A further FAILURE or unnamed
   non-pass is a finding. Name every GUARDED check + owner.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. Binding table: the new `check_limiter_loop_alive` must be BOUND (observed producing a real FAIL under
   its plant) or it is a vacuous gate. BOUND floor = 79.
4. `git add -A` before every measurement; D2.24 ignore-per-target; D3.205/D3.22 gitenv scrub on every
   subprocess git call.
5. Write-back to `/home/bbt/nix`: append to END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; run any predicted post-write-back re-measure and BANK it BEFORE the marker
   (§0j); `cat` both as the final action; **prove HEAD advanced** (§0d); state the absolute path.
6. Clean up temp files and any worktrees (prove `git worktree list` shows only `/home/bbt/nix`).
7. **Badge verdict, explicit:** Limiter stays RED; print the running-loop result and name slice 2.
8. **Per §0j: `**** ARC completed ****` is the LAST token, printed once, nothing after it.**

**WAYPOINTS + HEARTBEAT (both required; ~5-MIN cadence this phase).** Echo the total stage count at
kickoff. Boxed stage banner at each phase/stage/sub-agent: `ARC 039 · Limiter-loop/<Stage> — STAGE
<k>/<total>: <name>` + `~elapsed in · ~eta left`. **AND** a PROGRESS HEARTBEAT at least every **~5
minutes** of wall-clock (not 10): `[ARC 039 ▓▓▓░░░ 40% · stage 2/5 · proving loop liveness via pgrep ·
22m elapsed · ~30m left]` — overall-arc %, monotonic. **Any single operation estimated >5 min must be
polled for its own internal progress and re-emit the heartbeat every ~5 min from that live progress — a
>~5-min silent gap during any operation is a rule violation** (the ARC 038 binding-census silence must
not recur). Each heartbeat re-derived from LIVE state at emit time, never a cached summary. Tag `—
PAUSED, awaiting operator` on any stop. Both rules recorded in `~/nix/CLAUDE.md`.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the Limiter ULTRAREVIEW forward (parenthetical)>===`

---

## Explicitly NOT in this arc

GO-timeout implementation (I5 — slice 2, the very next arc, against this running loop) · any other
invariant (I1–I12) · sole-writer enforcement (I8) · the torn-state fix (I7) · any module other than the
Limiter · real order placement through the sender · Sentinel integration (a later slice) · new features.
An ULTRAREVIEW slice that grows past its one property has stopped being a ~1h slice.

---

## Open items returned to the operator / architect

1. **Push** — `main` is ~42 ahead of origin after ARC 038 (038's audit commits landed after the 037
   push). Clean fast-forward; worth pushing to back up the audit history.
2. **The tap session** — still the only code-independent FAIL.
3. **SPEC-A10 vendor · branch protection** — operator/outward-facing.
4. **The Limiter slice queue after this loop lands:** slice 2 = GO-timeout (I5) · then I7 torn-state +
   I8 sole-writer · then I2/I11 release bugs · then I1 instrument + the Plane-1 gate-family de-vacuum
   (I9/I12/FG1). Each a ~1h slice, staying on the Limiter until every finding discharges and the badge
   goes green — then broker-order.
