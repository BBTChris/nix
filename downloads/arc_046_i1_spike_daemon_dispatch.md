# ARC 046 — I1 SPIKE: daemon dispatch on one proven path (cancel) + measure the I1 capstone

**Tier: INTERIOR — but this is a SPIKE.** Its PRIMARY deliverable is a **measured estimate of the
full I1 capstone**, produced by wiring exactly ONE already-proven handler end-to-end through the
running daemon. **It does NOT discharge I1. The invariant count STAYS 7/12.** Limiter badge STAYS RED.
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `/home/bbt/nix/.venv/bin/python` →
`/usr/bin/python3.14` (3.14.4).
**Predecessor: ≈ `7671847` (approximate — ARC 045's measurement tip).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT (045's cited `4d04bfd` was really `e3bef1a`; the
post-write-back re-measure commits after the RESULTS HEAD).
**Model: Opus 5** — wiring the authority-central single-threaded loop without breaking §5's
race-elimination discipline, plus the sizing judgment the spike exists to produce.

## Why this arc exists — the question it answers

Five point-fix slices (I5, I7, I8, I2, I11) proved the same thing five times: **the logic is correct,
the running daemon doesn't invoke it.** D3.442 (I2's handlers uncalled), D3.443 (I11's enumeration
source has no production impl) — the terminal-handler surface is defined and proven **about the
library**, not **about the daemon**. That gap IS I1. Its size is currently a *guess* (I estimated
3–4 arcs from one data point). **This spike converts the guess into a number** by building the daemon
dispatch mechanism once, on the cleanest path, and measuring what remains.

**The gap, precisely (§5).** The Limiter is a single-threaded event loop that processes three inputs
serially: shared-mem price poll, ZMQ inbox (GOs), and **sender completions** — the broker's pushed
exec reports (fill / cancel-confirmed / reject) surfaced by the low-priority sender thread. The loop
*receives* completions; it does **not dispatch** a cancel completion to `OrderOutcomes.on_cancel`, so
the reservation the handler would release never releases in the running daemon. The invariant is true
of the handler and false of the daemon.

## KICKOFF OBLIGATIONS (before Stage 1 — all mandatory)

1. **Tier + count + SPIKE framing.** Echo `TIER = INTERIOR`, `SPIKE`. Derive clean/open from the 038
   register: clean `{I2, I5, I6, I7, I8, I10, I11} = 7/12`, open = 5. **State plainly: this slice
   does NOT flip an invariant; I1 stays open; the count stays 7/12; the deliverable is the estimate.**
2. **Status tooling — and the D3.445 fix.** `arc_progress.txt` is **one `key=value` PER LINE**, never
   one space-joined line (045 emitted a false `STALL WARNING` because CLAUDE.md documented the joined
   form while `arc_heartbeat.sh` parses line-by-line — fix the CLAUDE.md STATUS EMIT block in passing,
   it is a one-line correction). Start `tee` first, then `arc_heartbeat.sh selfcheck` into the log;
   write teardown + marker into the run's own log BEFORE the final verify (the 045 ordering lesson).
3. **Ops pre-flight — expect the tax and MEASURE it.** `check_tmpfs_inode_headroom.py --mount /tmp` +
   basetemp clean; scratch DBs cleaned at teardown (D3.437). **`limiterd.py` IS touched here, so the
   commit gate WILL escalate to a full ~3252-test pass** — unavoidable, and it will recur on EVERY I1
   arc. **As part of the spike, report whether `limiterd.py` can be brought under testmon coverage**
   (a daemon integration test that selects on it), because that decides whether the whole I1 capstone
   pays the ~43-min tax per arc or once. F6/F7: no second commit until the first's gate process is
   dead BY PID; never `pkill -f` on cc's own patterns.

## S1 — REPRODUCE THE DAEMON-DISPATCH GAP, on the cancel path, on the live loop

Bind to the real sender-completion processing in limiterd's loop. On a running `limiterd` with a stub
broker and a real `ReservationLedger`:
* Take a reservation (committed rises), place the order, then have the stub broker push a **cancel
  exec report** — surfaced as a sender completion the way a real venue cancel would be.
* **Prove the loop does NOT dispatch it** to `OrderOutcomes.on_cancel`: the completion is received
  (or dropped) and the reservation does **not** release — committed stays inflated in the running
  daemon, even though `on_cancel` is proven correct when called directly (ARC 044). That divergence —
  handler-correct, daemon-silent — is I1 in one measurement.
* **Non-vacuity:** prove the reservation was actually taken (committed rose) and the cancel completion
  actually reached the loop, before "not dispatched" means anything.

## S2 — WIRE ONE PATH (build the dispatch MECHANISM once, on cancel)

In the loop's sender-completion handling, dispatch a **cancel** exec report → `OrderOutcomes.on_cancel`
→ the reservation releases. Constraints that make this the reusable mechanism, not a one-off:
* **Serial, in the loop (§5).** No new thread; the dispatch runs in the single-threaded loop so the
  race-elimination guarantee holds. The sender thread surfaces the completion; the loop processes it.
* **Idempotent (§15 exec-report dedup).** A re-delivered cancel completion must NOT double-dispatch —
  that is exactly the double-release I2 forbids, now at the daemon boundary. Dedup by the exec
  report's identity, proven in S3.
* **Call the proven handler; do not change it.** `OrderOutcomes.on_cancel` is I2, discharged — the
  spike WIRES it, it does not touch it. `reservations.py`/`outcomes.py` stay byte-identical.
* Cancel **only** — do NOT wire fill / reject / pending-timeout / onset here. The mechanism is the
  expensive part; the point is to build it once and measure the incremental cost of the rest.
* Cite **§5 / §4 (feedback) / §15**. NO retry, NO auto-resend.

## S3 — PROVE THE RUNNING DAEMON DOES IT (this is I1's shape)

Real `limiterd` + stub broker + real ledger: inject a cancel exec report → **the loop dispatches** →
`on_cancel` → the reservation releases → committed falls → the financial-picture snapshot publishes
the reduced committed. **Prove it is the daemon's loop doing it**, not a direct handler call in the
test (assert the call arrived via the completion path, e.g. the loop tick that consumed it). Then:
* **Idempotency:** re-deliver the identical cancel completion → **exactly one** release, committed
  unchanged on the second — the daemon-level dedup, not just the handler's.
* Watch past the tick (the §0a trap). Non-vacuity throughout.

## S4 — THE MEASUREMENT (the spike's PRIMARY output — be concrete)

Report, as first-class results, not asides:

1. **Wiring cost of this path** — lines added to `limiterd.py`, the new dispatch/parse/dedup code, and
   whether `on_cancel` was callable as-is or needed adaptation (D3.442 answered for real).
2. **The dispatch mechanism's reusability** — now that the completion→handler dispatch + dedup exists,
   is each remaining path just "parse THIS completion type → call THIS handler," or does each need new
   mechanism? State it from the code, not hope.
3. **Enumerate every remaining completion→handler path** and classify each **same-pattern (incremental)**
   vs **different (own reasoning)**: fill → open-margin conversion + release (the central, likely-harder
   one — trade_id mint, §4 two-phase), reject → release, pending-timeout → `resolve`, onset-cancel
   dispatch (I11's `_classify_for_onset`), protective-flatten completions, GO-timeout (already wired,
   042 — confirm). D3.443's enumeration source (`pending_entries()`) has no production impl — note
   where that blocks a path.
4. **`limiterd.py` coverage** — can it be brought under testmon (killing the per-arc ~43-min tax)? If
   yes, that is its own small task worth doing before the rest of I1; if no, say why.
5. **THE I1 ESTIMATE** — the number this spike exists to produce: given mechanism-is-now-built +
   per-path incremental cost × the classified path count + the coverage decision, **how many arcs is
   the full I1 capstone, and in what order?** State it explicitly so the operator can decide whether
   to batch I1 now or finish the point-fixes (I3, I4, I9, I12) first.

## S5 — the gate (seed the daemon-dispatch instrument)

Nothing currently proves the **daemon invokes a handler on a real completion** — that is the I1 gap,
so apply rule 8 honestly: if an existing gate can own "the loop dispatches a cancel completion →
release," extend it; if this is a genuinely new property (it likely is), create
`check_limiter_daemon_dispatch` and **predict `passed+1`**. Either way it seeds the I1 gate with the
cancel path; the full I1 extends it to every path.

* **DRIVEN arm:** a real `limiterd` loop consumes a cancel completion and the reservation releases —
  asserted via the completion path, not a direct call.
* **Demonstrated FAIL:** **PLANT A** — remove the dispatch call: the daemon receives the cancel and
  the reservation does NOT release ⇒ `fail`, exit 1, naming the loop site and the inflated committed.
  **PLANT B** — defeat the dedup: a re-delivered completion double-releases ⇒ `fail`, exit 1.
  Plants removed ⇒ exit 0.
* **Non-vacuity:** the gate proves a real completion was processed by the loop before any verdict.
  Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `limiterd.py` (the dispatch), a minimal dispatch/dedup helper if needed, the
daemon-dispatch gate + its test, and `docs/CHECK-DEBT.md`. **Byte-identical (prove with
`git hash-object`):** `outcomes.py`, `reservations.py` (I2 untouched), `flatten.py`/`blackout.py`
(I11 untouched), `picture.py`/mirror, the sole-writer seam, the 042 booking. Only the DISPATCH is new.

## CLOSE-OUT — INTERIOR tier, commit ESCALATES (state it)

`limiterd.py` is uncovered ⇒ the commit runs a full pass regardless of tier. Run: **(b)** DERIVED
reverse-dependency closure — and heed **D3.444**: the AST import-graph closure is blind to
Protocol-dispatched callers (`halt.py` was invisible in 045), so **run the by-detection backstop and
name what it adds**; non-vacuity proven, RED-before/GREEN-after on this arc's own defect. **(c)** the
gate BOUND from both plants. **(d)** CHECK-DEBT + the ARC-TOTAL series row (do not skip it).

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** One completion path (cancel) is wired; the rest (fill, reject,
  pending-timeout, onset, protective-flatten) are not. The count stays 7/12.
* **D3.442 shrinks, it does not close** — the cancel handler is now daemon-invoked; the OTHER handlers
  remain uncalled. Re-state D3.442 precisely to reflect what is now wired vs still owed.
* D3.443 (enumeration source), D3.428, D3.434, D3.438, D3.439, D3.430–D3.433, D3.440, D3.441,
  D3.359/360/361/363 — standing named debt, not this slice.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 7/12** — this spike wires one path and sizes I1; it does not flip an
invariant. **No board redraw** (nothing on the leaderboard moved). The deliverable is S4's estimate.

## POST-WRITE-BACK RE-MEASURE — predict, then measure at the derived tip

Predict `passed+1` (**`91 | 3 | 2 | 0 | 1`**) **if** a new `check_limiter_daemon_dispatch` gate file
is created — which is the likely outcome, since no gate owns daemon-dispatch. If S5 instead extends an
existing gate, predict `90 | 3 | 2 | 0 | 1` unchanged. **State which before the run.** Three standing
fails unchanged (`check_ibgateway_service`, `check_monitor_tui`, `check_uncalled_entry_points` — the
last shrinks by the cancel-handler rows now called, so watch whether its row count drops). Name the
arc-boundary exclusion re-point (046 → next) in advance; write the series row.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` (dogfood,
progress file one-key=value-per-line), pulse+motion, ~5-min cadence holding inside the full-suite
commit, STALL WARNING after ~15 min no motion, GIT WINS over prose. Verified watchdog teardown before
the marker, matched by cc's own signature, ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md`
directly when building/extending the gate.
