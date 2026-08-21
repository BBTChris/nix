# ARC 053 — I1 ARC A: reject + pending-timeout dispatch + signal-freshness on reserve

**Tier: INTERIOR.** Limiter badge **STAYS RED**. **This is I1 slice 3 (ARC A of the 4-arc daemon
capstone) — the invariant count STAYS 11/12** (I1 discharges only at ARC D's convergence gate). **No
board redraw for the count.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `.venv/bin/python` → `python3.14` (3.14.4).
**Predecessor: ≈ `143af34` (approximate — ARC 052's write-back).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT.
**Model: Opus 5** — daemon event-loop wiring, the §4 no-auto-resend discipline, and the poll path.
**Commit is CHEAP now** — ARC 052 measured all seven tail daemon files in the testmon fingerprint
(`limiterd.py` 43m47s → 3s). If this arc adds a NEW module file, run `pytest --testmon` once before
committing it (D3.466).

## What this arc wires

ARC 047 measured the I1 tail. Two of its remaining paths are the "resolution" pair, and this arc
wires them:
* **REJECT** (cheap) — `OrderOutcomes.on_reject` EXISTS (044), same shape as `on_cancel`, on the
  `OutcomesPort` the 046 dispatcher already holds. A broker reject exec report → sender completion →
  dispatch → `on_reject` → reservation release. Reuses the 046 mechanism whole.
* **PENDING-TIMEOUT** (moderate — NOT a completion, a POLL) — §4: a pending order past its
  status-query deadline is resolved by **`query_order_status`, NEVER an auto-resend**. Needs a
  per-tick ingress hook (the loop checks `due_for_status_query`) + a `StatusQueryPort`; the response
  resolves — filled → the fill cascade (047), cancelled/rejected → release, **indeterminate/unknown →
  held toward flat (§14), never a resend.**

Plus one bounded entry-side fix folded in per the architect ruling:
* **D3.463 (signal-freshness on RESERVE)** — the recon found `signal_ts` enters via `reserve`, not
  `go`, so this is *reject a stale reserve*: a reserve whose `signal_ts` is older than a configured
  threshold is denied, and the `limiterd.py:1168` `signal_ts = raw.get("signal_ts") or time.time()`
  fallback is killed — **an absent signal instant must read STALE, not NOW** (§17 stale-until-proven-
  fresh, the discipline I12 enforces everywhere else). **BOUNDED & DEFERRABLE:** if this doesn't fit
  cleanly alongside the completion pair (it's a different seam — entry approval, not completion
  resolution), split it to its own named micro-slice rather than muddy the arc. State the call.

## KICKOFF OBLIGATIONS (before Stage 1)

1. **Framing.** Echo `TIER = INTERIOR`, `I1 ARC A (slice 3 of the capstone)`. Confirm clean
   `= 11/12`, open = 1 (I1). **State plainly: this wires reject + pending-timeout (+ the bounded
   D3.463 fix); it does NOT discharge I1; the count stays 11/12 until ARC D.**
2. **The §4 discipline is the safety spine of this arc.** The pending-timeout path **QUERIES, never
   resends.** A poll that resends could double-fill (place the order again while the original is
   still live at the venue) — the single most dangerous defect this arc can introduce. Every
   resolution routes to a handler; none places a new order.
3. **Process + ops lessons (memory #19/#20/#22/#23):** MEASURE the tip with `verify.py` FIRST (052
   closed `94|4|2|0|0` — the guard is now PASS; `check_arc_status_contract` now audits the previous
   arc and should PASS on `arc_052.log`'s marker, the D3.464/465 fix). Scope lint-fix to CHANGED
   files. `--basetemp` OUTSIDE `~/nix` (`/var/tmp/arc053_pt`). Run `test_check_order_path_bans` +
   `test_check_uncalled_entry_points` explicitly. `arc_heartbeat.sh` from the start (marker now tees
   to the log — 052's D3.464 fix). inode gate + basetemp clean; scratch DBs at teardown; kill by PID.

## S1 — REPRODUCE BOTH DISPATCH GAPS on the live loop

Bind to the real loop and the real handlers (`on_reject`, `resolve_pending_timeouts`, both from 044).
* **REJECT:** take a reservation, place the order, have the stub broker push a **reject** exec report
  as a sender completion → **prove the loop does NOT dispatch it** to `on_reject`: the reservation
  does not release, committed stays inflated. (Same gap shape as the 046 cancel reproduce.)
* **PENDING-TIMEOUT:** place an order, advance past its status-query deadline (`due_for_status_query`)
  → **prove nothing polls it**: it hangs indefinitely, never resolved, never released — the
  reservation leaks and the order is a zombie the daemon forgot.
* **Non-vacuity:** prove the reservation was taken and the events genuinely reached the loop /
  the order genuinely passed its deadline, before "not dispatched"/"not polled" means anything.

## S2 — WIRE BOTH (reuse the 046 mechanism for reject; build the poll for timeout)

* **REJECT dispatch:** route a reject exec report through the `CompletionDispatcher` → `on_reject`
  (via the held `OutcomesPort`) → release. This is the cheap reuse — no new port, no new mechanism.
* **PENDING-TIMEOUT poll:** a per-tick hook in the loop checks pending orders for
  `due_for_status_query`; for each due order, call **`query_order_status`** via a new
  `StatusQueryPort`; route the response — `filled` → the fill cascade (047's `FillSinkPort`),
  `cancelled`/`rejected` → release, **`indeterminate`/`unknown` → held toward flat (§14), NEVER a
  resend.** Idempotent (a re-queried order does not double-resolve). **NO `place_order` is reachable
  from this path** — assert it.
* **D3.463 (if in-scope):** the reserve path denies a reserve whose `signal_ts` age exceeds the
  threshold; `signal_ts` absent ⇒ STALE (deny), not `time.time()`. Add the threshold as config.
* Cite **§4 / §2A / §14 / §17**. **NO retry, NO auto-resend.** **Freeze the handler logic**
  (`on_reject`, `resolve_pending_timeouts` — 044, call don't change), the fill path (047), the exit
  path (048), the two-phase state (049), the hot-path (050), the freshness files (051 — except the
  bounded D3.463 reserve check), I2, the sole-writer seam, the mirror.

## S3 — PROVE THE RUNNING DAEMON DOES BOTH (this is I1's shape)

Real `limiterd` + stub broker + real ledger:
* **REJECT:** inject a reject exec report → the loop dispatches → `on_reject` → reservation releases →
  committed falls. Idempotent (re-delivered reject → one release). Via the completion path, not a
  direct call.
* **PENDING-TIMEOUT, each resolution driven:** an order past deadline → the poll queries →
  - `filled` → OPEN + stop armed (the 047 cascade), reservation converts;
  - `cancelled`/`rejected` → reservation releases;
  - `indeterminate`/`unknown` → **held toward flat, and NO new order placed** — assert `place_order`
    was never called on this path (the §4 safety proof, the sharpest assertion in the arc);
  - a re-queried order does not double-resolve.
* Watch past the tick (§0a — one resolution is not proof the next stays query-only). Non-vacuity
  throughout.
* **D3.463 (if in-scope):** a stale reserve is denied; an absent-`signal_ts` reserve is denied (not
  silently dated now); a fresh reserve proceeds.

## S4 — the gate: EXTEND `check_limiter_daemon_dispatch` (046's gate owns daemon-dispatch)

Rule 8 / Part C.9: extend it with the reject + pending-timeout arms — **no new file, no count move**
(unless D3.463 needs its own reserve-freshness gate; state that from a census). Obligations:
* **Reject arm:** the daemon releases on a reject completion (driven via the completion path).
* **Pending-timeout arm:** the daemon polls a due order, queries, and resolves — **and the census
  proves `place_order` is unreachable from the poll path** (the no-resend guarantee, structural +
  driven).
* **The rule-4 plant-both test** (standing boilerplate — a FAIL on one arm + a cannot-measure on
  another, FAIL wins).

**Demonstrated FAIL, each exit 1 (unclassifiable → exit 2) naming the site:**
* **PLANT A** — reject dispatch removed: the daemon receives the reject, reservation does NOT release
  ⇒ `fail`, exit 1.
* **PLANT B** — the pending-timeout poll removed: a due order hangs, never resolved ⇒ `fail`, exit 1,
  names the zombie order and leaked reservation.
* **PLANT C (the dangerous one)** — the poll **resends** (`place_order`) instead of querying: a second
  live order at the venue ⇒ `fail`, exit 1, names the §4 violation and the double-order risk.
* Plants removed ⇒ exit 0. Non-vacuity: real completions/polls processed before any verdict. Exit
  0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: `limiterd.py` (reject dispatch + the pending-timeout poll hook), `completions.py`
(reject parse/route), the new `StatusQueryPort` + its wiring, the reserve signal-freshness (if
in-scope), `check_limiter_daemon_dispatch` + its test, `docs/CHECK-DEBT.md`. **Byte-identical (prove
with `git hash-object`):** the handler logic (`outcomes.py`/`reservations.py` — 044), the fill path
(`fills.py`/`fill_seam.py`), the exit path (`flatten.py`), the two-phase state, the hot-path files,
the freshness files (except the bounded reserve check), the sole-writer seam, `picture.py`/mirror.
Name any `uncalled_entry_points_baseline.json` ratchet movement (handler symbols now called drop off).

## CLOSE-OUT — INTERIOR tier, commit CHEAP (052 paid the tax)

Run: **(b)** DERIVED reverse-dependency closure + the D3.444 by-detection backstop; non-vacuity
proven, RED-before/GREEN-after on this arc's own defect (the pending-timeout zombie, specifically).
**(c)** the gate BOUND from all three plants (A/B/C exit 1, sites named) plus the rule-4 plant-both.
**(d)** CHECK-DEBT + the ARC-TOTAL series row written and re-derived whole (the 050 miss).

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** Reject + pending-timeout wired; **onset** (ARC B, needs `pending_entries()`
  D3.443), **price-poll + stop-maintain + the flatten producers** (ARC C — D3.453/D3.372, the daemon
  has no protective-exit path at all per the recon), and the **convergence gate** (ARC D) remain.
  Count stays 11/12.
* **D3.442 shrinks** — restate which handlers are now daemon-invoked (cancel, fill, reject,
  pending-timeout) vs still owed (onset, protective-flatten).
* If D3.463 was split out, name its micro-slice.
* D3.450, D3.453, D3.372, D3.458, D3.466, D3.467, D3.428, D3.434, D3.438–D3.467, D3.359/360/361/363 —
  standing named debt.

## BADGE VERDICT

**Limiter STAYS RED. Count STAYS 11/12.** I1 path-progress: cancel + fill + reject + pending-timeout
wired (4 of ~6 completion/resolution paths); onset + protective-flatten remain (ARC B/C), convergence
gate is ARC D. **No board redraw.** The badge flips to 12/12 only when ARC D's convergence gate proves
the daemon runs the full invariant set.

## POST-WRITE-BACK RE-MEASURE — MEASURE THE TIP FIRST, then predict the delta (memory #19)

Run `verify.py` at the derived tip, record the real baseline (052 closed `94|4|2|0|0`), THEN predict
only this arc's DELTA:
* extending `check_limiter_daemon_dispatch` (no new file) → `passed` unchanged; a NEW reserve-freshness
  gate for D3.463 (if built) → `passed +1` (state from the census);
* the clean-set stays **11/12** (no flip);
* `check_arc_status_contract` should now PASS auditing `arc_052.log` (the D3.464/465 fix) — confirm;
* `check_uncalled_entry_points` may shrink as `on_reject`/`resolve_pending_timeouts` become daemon-
  called — name the dropped rows;
* account for the guard (now PASS/stable from 052) and whether the `.dmg` was deleted/ignored.
State the predicted delta and the measured baseline it sits on, before the run.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` from the
start (marker tees to the log — 052 fix). Verified watchdog teardown before the marker, matched by
cc's own signature with POSITIVE identification (the D3.465 fix), ignoring `[watchdogd]`. Read
`VERIFY-AND-CHECKS.md` directly when extending the gate.
**After the marker, PUSH: `git push origin` — the I1 tail has begun and origin is 50+ behind (memory
#21, unsafe to defer).**
