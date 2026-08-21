# ARC 056 RESULTS — D3.474 discharged: trailing stops arm, trail and fire

**TIER = INTERIOR — FUNCTIONAL FIX.** Limiter badge **STAYS RED**. Count **STAYS 11/12** (open: I1).
Discharges **D3.474**. Does NOT flip an invariant. RE-OPENED and RE-PROVED **I2** and **I4**.

**Predecessor DERIVED:** brief said `≈ 4601a06`; `git rev-parse HEAD` = **`d3ff4a0`**. Frozen against
that.

---

## THE HEADLINE

**The strategy's entire loss-cutting mechanism now works end to end on the daemon.** Before this arc
`reserve(stop_mode=trailing)` was accepted and its margin committed, the fill was then refused whole,
the position never opened and the reservation leaked. A green 12/12 Limiter would still have refused
every trailing entry.

---

## BASELINE — MEASURED FIRST, AND THE BRIEF'S PREDICTION MISSED

`94 passed | 4 failed | 3 cannot-measure | 0 skipped` at `d3ff4a0` (exit 1).

The brief expected `~95|4|2|0`, on the expectation that `check_arc_status_contract` would clear to
PASS auditing `arc_055.log`. **It reads CANNOT-MEASURE: that log carries no
`**** ARC completed ****` marker.** ARC 055 printed the marker to the chat, not into its own log —
the 054 gap, one layer over. This arc's marker is written INTO `arc_056.log`.

| bucket | members |
|---|---|
| FAIL x4 | `check_ibgateway_service` (gateway down), `check_monitor_tui` (ARM3 stale pin), `check_uncalled_entry_points` (21 rows), `check_untracked_attribution` (the `.dmg`) |
| CANNOT-MEASURE x3 | `check_arc_status_contract`, `check_ibgateway_config`, `check_observed_resource_claims` |

---

## S1 — D3.474 REPRODUCED LIVE, AGAINST A WORKING CONTROL

| step | `committed` | `outstanding` | stop | position |
|---|---|---|---|---|
| boot | 0.0 | 0 | — | — |
| FIXED reserve | 1000.0 | 1 | — | — |
| FIXED fill | **0.0** | **0** | armed @ 4998.0 | **OPEN** |
| TRAILING reserve | 1000.0 | 1 | — | — |
| TRAILING fill | **1000.0** | **1 — THE LEAK** | **none** | **not opened** |

`delivered` 1 -> 2 while `handled`/`conversions`/`releases`/`writes` ALL stayed at 1.

### THE TRAIL SOURCE — TRACED, AND THE ANSWER CHANGES THE BRIEF

`docs/nix_strategy_contract_v1.1.md`:175 **already** declares the GO's stop object as
`{"mode":"trailing","initial_ticks":N,"trail_ticks":M}` at `contract_rev 1.1.0`, with :475 requiring
both int >= 1. **The distance was on the wire and was dropped in the projection into `ProposedOrder`.**
So: **NO strategy-contract-v1.2 implication.** Nothing was invented and no default was minted.

---

## S2 — THE FIX (four edits, frozen seam NOT widened)

1. `nixrisk/seam.py` — `ProposedOrder.trail_ticks: int | None = None`. Additive, defaulted, last;
   all 54 construction sites unchanged, every FIXED order untouched.
2. `limiterd.py` — the `reserve` verb carries it from the payload. **`None`, never `or 0`** (a GO
   that sent no trail and one that sent an invalid trail are different refusals — ARC 053's
   `signal_ts` reasoning, one field up), and never defaulted from `stop_ticks`.
3. `nixrisk/stops.py` — `arm` reads `order.trail_ticks` when the caller passes none; the explicit
   argument still wins. **This is why `fill_seam.StopArmPort` (`FILL_SEAM_REV 1.0.0`) is
   byte-identical: the port did not have to be widened to make trailing work.**
4. `nixrisk/fills.py` — a denied conversion runs step 2 and ONLY step 2: released over §3's
   `TerminalPath.FILL` through the SAME verb the success path uses, step 3 never reached, no row
   published, `UnarmableFill` carries the original refusal outward. **No leak AND no unprotected
   open.**

### ONE ARCHITECT RULING CORRECTED — THE BRIEF INVITED IT

The brief said `arm` should anchor a trailing stop at `price -/+ trail_ticks x tick_size`.
**§4:190-196 says the opposite:** a trailing stop is anchored at `fill +/- initial_distance` and
**HOLDS there until the trail would sit tighter**. Anchoring at the trail distance places the stop at
a level the strategy did not choose — tighter than intended whenever `trail < initial`, the ordinary
case — and fires it on the noise the initial distance exists to absorb. `stops.py` already had it
right; the gap was only that nothing fed it. **PLANT C was restated to the spec's property.**

---

## S3 — PROVEN END TO END, I2 AND I4 RE-PROVEN

**A. THE FULL TRAILING LOSS-CUT.** armed **4998.0** (INITIAL distance) with `trail_distance_ticks=4`
-> `committed` 1000.0 -> 0.0, `outstanding` 1 -> 0, position **OPEN** -> 12 ticks of advance ratcheted
`level` **4999.25 -> 5002.0**, monotonically non-decreasing, `activated` latched -> a breach of the
**TRAILED** level fired **EXACTLY ONE** protective flatten: `fires=1 sends=1 breaches=1
executed=[true]` across 125 polls and 8 further ticks past the level, `refusals=[]`. **The firing
names 5002.0, not the armed 4998.0.**

**B. FIXED UNREGRESSED.** Identical to ARC 047/055.

**C. I2 ON THE NEW PATH.** Malformed trailing -> arm refused and NAMED -> **released EXACTLY ONCE**
(1000.0 -> 0.0, outstanding 1 -> 0), `refused_releases=0`, **no stop, no position** (`writes` 2 not 3,
`handled` 2 while `delivered` 3). Three reservations, three releases.

**I4.** No stop and no §3 row precede the confirmed fill in either drive.

---

## S4 — THE GATE: EXTENDED, NOT ADDED (census)

`check_fill_handler` owns *a fill calls arm*; doctrine C.9 forbids a second instrument over it.
**Extended per rule 8 — no new gate, no count move.** ARM TRAILING, **BOUND from four plants**, each
exit 1 naming its site: **A** trail un-threaded (D3.474 reproduced) · **B** refusal does not release
(the leak, names I2) · **B'** refusal releases twice (rule 4's other direction) · **C** armed at the
trail distance (§4:190-196). Plants removed -> PASS. 31/31 tests.

**NO-REGRESSION PROOF (the arc's most important close-out item), at the merged tree:**
`check_reservation_lifecycle` **PASS** · `check_two_phase_entry` **PASS** · `check_stop_maintenance`
**PASS** · `check_limiter_daemon_dispatch` **PASS** · `check_origin_write` **PASS** ·
`check_order_path_bans` **PASS**. `check_uncalled_entry_points`: **55 measured before, 55 after** —
zero new uncalled surface, baseline byte-identical.

---

## FREEZE — `git hash-object`, not a claim

Diff: `seam.py`, `stops.py`, `fills.py`, `limiterd.py`, `check_fill_handler.py`,
`test_check_fill_handler.py`, `docs/CHECK-DEBT.md`. **Byte-identical:** `stopwatch.py`, `flatten.py`,
`positions.py`, `projection.py`, `outcomes.py`, `reservations.py`, `completions.py`, `fill_seam.py`,
`freshness.py`, `execution.py`, `picture.py`, `join.py`, `gate.py`, `nixalloc/sizing.py`,
`uncalled_entry_points_baseline.json`, `gate_coverage_baseline.json`, `registry.json`.
**C1's stop-wiring untouched** — the five `limiterd.py` hunks are all in `FillPath` and
`CommandHandler._reserve`; the only `StopWatch` line in the entire diff is a docstring.

---

## CHECK-DEBT — ARC TOTAL 416 (derived, not typed)

* **D3.474 DISCHARGED.**
* **D3.475 OPENED** — the reservation half is closed, the VENUE half is not: an un-armable fill
  leaves a real position at the broker with no synthetic stop, and §14 makes the flatten
  `nixrisk.flatten`'s. Named, loud in the daemon's `unarmable` block, routed to **ARC C2**.
* **D3.476 OPENED** — `nixalloc/sizing.py` carries no trail distance and is not wired into
  `limiterd`; named rather than half-threaded, and its hash proves it untouched.
* **D3.477 OPENED** — `test_PLANT_053B`'s anchor drifted at ARC 055; **proven inherited** by running
  it in a clean worktree at `d3ff4a0`, where it fails identically.

416 is `derived:ledger_rows` read off `check_derived_claims` over the merged tree — **not 414 plus
arithmetic, which would have said 417**. `check_derived_claims` PASS.

---

## RESIDUAL — NOT CLAIMED

**I1 is NOT discharged.** C2 (D3.453/372/469) then D (completions + convergence -> 12/12) then
greening. Count stays 11/12, badge stays RED. D3.473/470/468 unchanged. No green here may be read as
*the Limiter is receiving real prices* or *a live broker event reaches this handler*.
