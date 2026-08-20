# ARC 047 — I1 slice 2: the fill completion dispatch (the hard path) + the I1 estimate

**Tier: INTERIOR.** Limiter badge **STAYS RED**. This is **I1 slice 2 of a multi-arc capstone** —
**the invariant count STAYS 7/12** (I1 discharges only when the daemon runs the full invariant set;
this wires path 2 of ~6). **No board redraw** for the count; track I1 path-progress instead.
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `6f20d38` (approximate — ARC 046's final re-measure commit).** DERIVE the real tip
with `git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — §4 two-phase, the stop conversion/placement cascade, and the sizing judgment that
finally produces the I1 arc-count 046 deferred.

## Why this arc, and what it must produce

ARC 046 wired the *cancel* path (cheap — `on_cancel` was daemon-ready, a simple release) and built a
generic `CompletionDispatcher`, but **honestly refused to state the I1 arc-count** because cancel's
cost can't predict fill's: fill is the central, likely-hardest path. **This arc builds fill and, from
cancel-cost + fill-cost together, states the I1 estimate as a number** (046's deferred S4 point 5).

## The path — fill is a CASCADE, not a release (§2A / §4 / §3 / §9)

`on_fill(client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty)` — idempotent by
`(order_id, exec_id)`, partial fills arrive as successive events. On a confirmed fill the Limiter must:
1. Assert **OPEN** (§4 two-phase — only on broker fill confirmation, never on ack).
2. **Mint `trade_id`** (§4 — at open; tags all subsequent feedback).
3. Capture the **fill price** (§9).
4. **Convert the stop intent (tick DISTANCE) → absolute price at the confirmed fill, and PLACE the
   protective stop** (§4 — the Limiter validates, converts, places, maintains). **SAFETY-CRITICAL:**
   a fill that opens a position without placing its stop is an unprotected position inside the very
   hazard I11 guards. This is the half that makes fill hard and the half a "release-only" wiring
   would silently skip.
5. **Convert the reservation → open-margin** (§3 lifecycle — fill converts, not just frees) and update
   the financial picture (position row keyed by `trade_id`, Σ open margin, committed).
6. Push **OPEN feedback** to the strategy FSM, tagged `trade_id`.
7. **Partial fill:** successive `on_fill`; the unfilled remainder's reservation handled per I2/044
   (`IocRemainder`).

**Explicitly OUT of scope (name, do not wire):** the Plane-1 `filled` row (§12.10) is D3.434 /
Plane-1-module territory; the event-driven balance refresh (§6.4b) beyond what the picture needs.
Wire the completion cascade; name the Plane-1 booking as owed elsewhere.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Tier + count + I1 framing.** Echo `TIER = INTERIOR`. Derive clean/open: clean
   `{I2, I5, I6, I7, I8, I10, I11} = 7/12`, open = 5. **State plainly: I1 is a multi-arc capstone;
   this is path 2 of ~6; it does NOT flip the count; 7/12 holds until I1 fully lands.**
2. **The 046 lessons, applied — all four:**
   - **Run `arc_heartbeat.sh` from the START of the session** (selfcheck → banner → pulses into
     `scratchpad/arc_logs/arc_047.log`), not just at write-back — 046's `check_arc_status_contract`
     read cannot-measure because the session ran the heartbeat protocol zero times until the end.
   - **Progress file: ONE `key=value` PER LINE** (D3.445, fixed in the CLAUDE.md STATUS EMIT block —
     confirm the fix is in the tree).
   - **Confirm the S4.4 testmon fingerprint holds** — `scripts/limiterd.py` should still carry a row
     in `.testmondata`'s `file_fp` table, so this fill change commits on the TARGETED path (~seconds,
     not 44 min). If the fingerprint is gone, re-apply before committing.
   - **Scope any lint-fix to the CHANGED files, never `ruff … .` repo-wide** — 046's repo-wide run
     reformatted ARC-035-excluded files, Python fenced inside `nix_db_schema_spec.md`, and a downloads
     brief (all reverted). Fix only what this arc touched.
3. **Tripwire-selection guard (the 044/045 finding).** A testmon-SELECTED commit can skip a tripwire
   test — `test_check_order_path_bans`' module-count rode two arcs stale that way. Before the real
   commit, **run the relevant tripwire/count tests explicitly** (or confirm the selection includes
   them) so this arc's changes don't hide drift.
4. **Ops pre-flight.** `check_tmpfs_inode_headroom.py --mount /tmp` + basetemp clean; scratch DBs
   cleaned at teardown (D3.437). F6/F7: kill by PID, never `pkill -f` on cc's own patterns.

## S1 — REPRODUCE THE FILL DISPATCH GAP, on the live loop

Bind to the real fill handler (`fills.py` / the `on_fill` handler / `IocRemainder`). On a running
`limiterd` with a reservation taken and an order pending:
* the stub broker pushes a **fill** exec report, drained by the loop → **prove the fill handler is not
  invoked**: no OPEN assertion, no `trade_id`, no reservation→open-margin conversion, and **no
  protective stop placed** — committed still reflects a reservation, and the position (if any) is
  unprotected. That gap, especially the missing stop, IS the fill half of I1.
* **Non-vacuity:** prove a reservation was taken and the fill report actually reached the loop, and
  that a stop *would* be placeable (the stop intent is present on the pending order) — so "no stop
  placed" measures a real omission, not an absent input.

## S2 — WIRE THE FILL COMPLETION (reuse the 046 mechanism; measure whether it suffices)

Dispatch a **fill** exec report through the `CompletionDispatcher` → the fill handler → the full
cascade (OPEN, `trade_id`, price capture, **stop conversion + placement**, reservation→open-margin,
picture update, FSM feedback). The measurements that matter:
* **Is the fill handler daemon-ready like `on_cancel` was, or does it need adaptation?** If the stop
  conversion/placement is not wired into the handler the daemon calls, **that is a BLOCKING finding,
  surfaced prominently — the daemon must not create unprotected positions.** Wire the stop placement
  if tractable in-slice; if it is a large separate cascade, say so, wire the safe minimum (no
  unprotected position ever), and name the remainder as a blocking sub-path — do NOT silently defer
  the stop.
* **Is "parse fill → route to handler" enough, or does fill need new mechanism?** Report it from the
  code — this is what tells us whether the remaining paths are cheap.
* **Idempotent** by `(order_id, exec_id)` (§2A) — a re-delivered fill must not double-convert. Dedup
  at the daemon boundary (the 046 pattern), proven in S3.
* Cite **§2A / §4 / §3 / §9**. NO retry, NO auto-resend. Freeze the cancel path (046), the I2 release
  logic, the sole-writer seam, the mirror, the onset seam.

## S3 — PROVE THE DAEMON DOES IT END-TO-END (with the stop check as a first-class assertion)

Real `limiterd` + stub broker + real ledger: inject a fill exec report → the loop dispatches → and
assert, via the completion path (not a direct call):
* **OPEN** asserted, `trade_id` minted, fill **price** captured;
* the reservation **converted to open-margin** (committed reflects open margin, not a reservation);
* **a protective stop order exists at `fill ± distance`** — the safety assertion; an open position
  with no placed stop is a FAIL, not a pass;
* FSM feedback pushed, tagged `trade_id`.
Then:
* **Idempotency:** re-deliver the identical fill → exactly one conversion, one stop, committed
  unchanged on the second.
* **Partial fill:** successive `on_fill` events convert cumulatively; the unfilled remainder's
  reservation is handled (I2/044) — one stop for the open portion, no double-book.
* Watch past the tick (§0a). Non-vacuity before every verdict.

## S4 — THE MEASUREMENT + THE I1 ESTIMATE (the deliverable 046 deferred)

State, concretely:
1. **Fill wiring cost** — LOC, new dispatch/parse, and crucially **whether the fill handler +
   stop placement were daemon-ready or needed adaptation** (contrast with cancel's zero-adaptation).
2. **Did the generic mechanism hold** — was fill "parse → route," or did it need new mechanism?
3. **THE I1 ARC-COUNT, as a number.** With cancel-cost (cheap, 046) and fill-cost (measured here)
   both known, classify the remaining four paths — reject → release, pending-timeout → `resolve`,
   onset-cancel dispatch (blocked on D3.443's missing `pending_entries()` — note it), protective-
   flatten completions — and **state how many arcs the rest of I1 is, and whether the tail decomposes
   into independent per-path workers** (the swarm question). This is the number that decides
   batch-vs-swarm and whether the point-fixes (I3/I4/I9/I12) come before or after.
4. **Named cascades** — the Plane-1 `filled` row (D3.434) and any stop-maintenance/trailing machinery
   (§4 trailing ratchet) that fill touches but this slice does not own.

## S5 — the gate: EXTEND `check_limiter_daemon_dispatch` (046's gate owns daemon-dispatch)

Rule 8 / Part C.9: 046 created the gate; fill is another daemon-dispatch path → **extend it, no new
file, no count move**. Add a **fill arm**: the daemon converts a fill completion → open-margin **AND
places the protective stop**. Demonstrated FAIL, each exit 1 naming the site:
* **PLANT A** — fill dispatch removed: the loop drains the fill, no conversion, committed wrong.
* **PLANT B (the safety plant)** — conversion happens but the stop placement is removed: an OPEN
  position exists with **no stop order** ⇒ `fail`, naming the unprotected position. This arm is the
  point of the slice.
* **PLANT C** — dedup defeated: a re-delivered fill double-converts.
* Plants removed ⇒ exit 0. Non-vacuity: a real fill processed by the loop before any verdict. Exit
  0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `limiterd.py` (fill dispatch), `completions.py` (fill parse/route), the fill handler
+ stop-placement wiring if adapted (name the functions), `check_limiter_daemon_dispatch` + its test,
`docs/CHECK-DEBT.md`. **Byte-identical (prove with `git hash-object`):** the cancel path, I2's
`outcomes.py`/`reservations.py`, `flatten.py`/`blackout.py` (I11), `picture.py`/mirror, the
sole-writer seam. Explain or revert any wider path.

## CLOSE-OUT — INTERIOR, commit now CHEAP (S4.4)

Full pytest + census DEFERRED to greening. Run: **(b)** DERIVED reverse-dependency closure + the
by-detection backstop (D3.444 — import-graph blind to Protocol-dispatched callers); non-vacuity
proven, RED-before/GREEN-after on this arc's own defect (the missing stop, specifically). **(c)** the
gate BOUND from all three plants (A/B/C, sites named). **(d)** CHECK-DEBT + the ARC-TOTAL series row
(do not skip it — 044/046 both had a series-row miss caught by `check_derived_claims`).

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** Two of ~6 paths wired (cancel, fill); reject, pending-timeout, onset,
  protective-flatten remain. **Count stays 7/12.**
* **D3.442 shrinks further** — restate precisely which handlers are now daemon-invoked vs still owed.
* The Plane-1 `filled` row (D3.434), stop trailing/maintenance (§4), and D3.443's `pending_entries()`
  gap — named, not this slice.
* D3.428, D3.434, D3.438–D3.441, D3.446–D3.448, D3.359/360/361/363 — standing named debt.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 7/12.** I1 path-progress: **2 of ~6 wired.** No board redraw for the
count; the payload is S4's I1 arc-count. When I1 fully lands (all paths + the daemon-dispatch gate
covering them), it flips to 8/12 in one step.

## POST-WRITE-BACK RE-MEASURE — predict, then measure at the derived tip

Extending `check_limiter_daemon_dispatch` (not a new file) moves no count: predict
**`91 | 3 | 2 | 0 | 1`, exit 1**, unchanged from 046's final. Three standing fails unchanged (the
IB-Gateway chain + `check_monitor_tui`); watch `check_uncalled_entry_points` shrink again as fill's
handler symbols become called (name which drop). Name the arc-boundary exclusion re-point (047 →
next) in advance; write the series row.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start (dogfood), pulse+motion, ~5-min cadence, STALL WARNING after ~15 min no motion, GIT WINS over
prose. Verified watchdog teardown before the marker, matched by cc's own signature, ignoring
`[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending the gate.
