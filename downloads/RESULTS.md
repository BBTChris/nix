# ARC 047 — I1 slice 2: the FILL completion dispatch (the hard path) + THE I1 ESTIMATE

**TIER = INTERIOR. Limiter badge STAYS RED. Invariant count STAYS 7/12.**
Clean `{I2, I5, I6, I7, I8, I10, I11}` = 7/12, open = 5.
**I1 is a multi-arc capstone. This is path 2 of ~6 (cancel = 046, fill = 047). It does NOT flip the
count.** No board redraw for the count; the payload is S4's number.

**Predecessor tip DERIVED, not taken from the brief.** The brief said `≈ 6f20d38 (approximate)`;
`git rev-parse HEAD` returned **`1d241e2`** (ARC 046's final-measurement commit). Every freeze
assertion and every diff below is against `1d241e2`.

---

## S1 — THE GAP, REPRODUCED ON THE LIVE LOOP (three layers deep, only one of them routing)

A real `limiterd`, a real reservation, a stub broker pushing a §2A `on_fill` into the completions
directory.

**NON-VACUITY, asserted before any verdict:**
* N1 — the reservation was really TAKEN in the running process: `committed 0.0 -> 2000.0`,
  `outstanding = 1`.
* N2 — the STOP INTENT reached the process: the `reserve` command carried `stop_ticks=8`,
  `stop_mode=fixed`, and the daemon ACCEPTED it, so it parsed a valid §4 stop intent into a
  `ProposedOrder`. A stop was convertible from what the process was handed.
* N3 — the fill report reached the LOOP: `consumed = 1`, `last_source` = the file the driver wrote.

**MEASURED:**

| layer | the gap |
|---|---|
| 1 — routing | `on_fill` -> `Disposition.UNWIRED`. `dispatched=0`, `unwired=1`, `last_reason` naming itself. |
| 2 — handler port | **`OrderOutcomes` has NO `on_fill`.** Its own `HANDLES` map books `{CANCEL, REJECT, PENDING_TIMEOUT}`. `TerminalPath.FILL` exists and `outcomes.py` deliberately does not serve it — because §3 says a fill *converts to open-margin*, which is a cascade, not a release. **The `OutcomesPort` the 046 dispatcher holds is structurally incapable of serving a fill.** |
| 3 — collaborators | `limiterd.py` mentioned **ZERO** of `ApprovedOrderBook`, `StopBook`, `IocRemainder`, `PositionOriginWriter`, `EntryOrderOrigins`, `production_origins`, `FillHandler`, `LimiterFillSink`, `ExecutionLedger`, `FinancialPictureBook`. And the `ProposedOrder` built at `reserve` — carrying `stop_ticks` — was **DISCARDED** after `take()`. §4's whole conversion input was thrown away at the approval that created it. |

Consequence, measured: `committed` stayed **2000.0**, `outstanding` stayed **1** (no conversion), no
`trade_id`, no OPEN row, **NO PROTECTIVE STOP** — and the daemon's published state had no key for a
stop, a position or open margin at all, so there was nowhere for a stop to even be seen.

---

## S2 — THE WIRING (and the answer to *is parse -> route enough?*)

**NO. It is not.** Cancel was one call into an object the daemon already held. Fill needed:

* **A SECOND PORT.** `completions.py::FillSinkPort` beside `OutcomesPort` — two verbs, `on_fill` and
  `outcomes()`. The second is not decoration: `on_fill` returns `None` (that shape is
  `broker_seam.OrderEventSink`'s and may not be widened), so a dispatcher holding only `on_fill`
  could count a dispatch and know nothing about what the cascade did. `outcomes()` is §7.12 guard 2
  applied to a verb that cannot return one.
* **NINE process-held collaborators** — `limiterd.py::FillPath`: `FinancialPictureBook`,
  `ExecutionLedger`, `StopBook`, `production_origins()`, `ApprovedOrderBook`, `RecordedCancels`,
  `PositionOriginWriter`, `IocRemainder`, `FillHandler` + `LimiterFillSink`.
* **The approval completed.** `reserve` now HOLDS the order and MINTS the join (the trade<->order
  association, through `production_origins()` which REFUSES `identity_trade_id` — D3.177), and seeds
  §4:198's margin field set plus §3's Σ reservations onto the SAME snapshot.
* **A tick-size map**, boot-loaded and restart-only (`--tick-size ES=0.25`). There is no instrument
  table in `risks/` — `allocator_caps.config.json` holds `tick_value_usd`, the DOLLAR value of a
  tick, not its price increment — and `nixalloc/sizing.py` forbids a hardcoded `tick_size` by name.
* **A published-state surface.** The `status` reply and the runtime/stop record now carry `fills`
  (every armed stop and every §3 row, **enumerated, not counted**) and `picture` (§3's snapshot).
* **§4:203-206's outcome push** (`OpenFeedback`): a `<trade_id>.feedback.json` in the outbox, and
  §4:208's one-in-flight lock RELEASED with outcome `open`.

**THE STOP PLACEMENT WAS ALREADY IN THE HANDLER — this is NOT a blocking finding.** `fills.py`
arms FIRST (`FillStep.ARM_STOP`), releases second, publishes third, and RAISES rather than returning
a partial outcome. `_dispatch_fill` nevertheless re-asserts at the daemon boundary that the outcome
carries an armed `StopState` and an OPEN row, because the cost of the redundancy is one comparison
and the cost of being wrong is a live position nothing protects.

**Nix stops are SYNTHETIC (§12.1).** "The protective stop is placed" means `StopBook` holds a live
`StopState` at `fill -/+ distance x tick_size`. There is no broker-side stop and there must not be.

**FAIL CLOSED, and it is the safe minimum this arc guarantees:** a symbol with no tick size is
NOT-TRADABLE (§4:198), `StopBook.arm` raises BEFORE the remainder is released, and the cascade
refuses whole — **no reservation converts and no position opens.** This process cannot open a
position it has no stop for. Measured (S3 scenario 3).

---

## S3 — THE DAEMON DOES IT, END TO END (every assertion through the completion path)

**Scenario 1 — full fill, then re-delivery.** All PASS:
`committed 0.0 -> 2000.0` (non-vacuity) · fill dispatched from the pushed file (provenance) ·
one §3 row, `state=open`, `trade_id='TRD-00000003-s3-fill'` (**distinct from `client_order_id`**),
`size=2`, `stop_distance=8` · **exactly ONE protective stop, `level=4998.0 = 5000.0 - 8x0.25`,
`anchor=5000.0`** · `unstopped=[]` · ledger Σ reservations `2000 -> 0`, picture Σ reservations
`2000 -> 0`, **picture Σ open margin `0 -> 2000`**, **picture `committed` UNCHANGED at 2000.0 —
same capital, different bucket, which IS the conversion** · OPEN feedback written to the outbox,
tagged `trade_id`, carrying the armed stop level.
Idempotency: re-delivered identical exec report -> still ONE dispatch, ONE stop, ONE row, Σ open
margin unchanged, `handled=1`, and the stop record shows **`reservations.refused = 0`** — the guard
that stopped it was the DAEMON's dedup, not `reservations.py`'s (I2's, which still stands).

**Scenario 2 — partial fills (successive `on_fill`, §4).** All PASS: one stop armed on the FIRST
partial; the WHOLE reservation released on it (§3: converts to open-margin); Σ open margin = the
filled portion only; the IOC remainder cancel issued for the unfilled 3; the SECOND partial
`re_arms_declined=1` and **the stop stays at the FIRST fill's anchor** (no silent re-anchor at a
higher price); one row, size accumulated 2 -> 5; Σ open margin accumulated; exactly one terminal
release; no contained faults.

**Scenario 3 — fail closed.** A symbol with no tick size: reservation taken (non-vacuity), fill
REFUSED naming `UntradableSymbol`/§4:198, **no stop, NO POSITION OPENED, reservation UNTOUCHED**,
tick not killed.

**Scenario 3b — §4:208's lock.** With a real `go` holding the lock: the fill RELEASED it with
outcome `open`, the feedback named the originating strategy, `in flight []` afterwards, and
**§4:210-212's breaker did NOT fire** — a filled order no longer wedges to the GO timeout.

---

## S4 — THE MEASUREMENT, AND THE I1 ARC-COUNT AS A NUMBER

### 1. Fill wiring cost, and daemon-readiness

**ZERO ADAPTATION of the §4 cascade.** Byte-identical across this arc by `git hash-object` against
`1d241e2`: `fills.py`, `stops.py`, `positions.py`, `picture.py`, `execution.py`, `join.py`,
`fill_seam.py`, `outcomes.py`, `reservations.py`, `flatten.py`, `blackout.py`, `loop.py`, `seam.py`,
`recovery.py`, `wal.py`, `plane1_sink.py`.

**So the fill handler AND its stop placement were daemon-ready, exactly as `on_cancel` was. The
DAEMON was not.** The cost is entirely in the process:

| | ARC 046 (cancel) | ARC 047 (fill) |
|---|---|---|
| handler adaptation | zero | **zero** |
| port | reused `OutcomesPort` | **a SECOND port (`FillSinkPort`)** |
| collaborators the daemon had to hold | 1 (`OrderOutcomes`) | **9** |
| approval-time change | none | order HELD + join MINTED + margin field set + Σ seeded |
| boot-time input | none | tick-size map, account balance |
| published-state surface | counters | counters + enumerated stops + enumerated §3 rows + §3 snapshot |
| new code (top-level objects) | — | **~313 code lines / ~217 docstring** across 2 files |
| diff | +953 / 2 files | **+1013 / 2 files** |

### 2. Did the generic mechanism hold?

**Half.** The 046 machinery held completely for *parse, dedup, contain, count, record provenance* —
`ExecReportDedup`, `DispatchLedger`, `CompletionHandler`, `CompletionInbox` and the §4:214 key are
all unchanged in shape and now serve two paths. What did NOT generalise is the **handler port**: one
port cannot cover a release and a conversion, because §3's terminal set is not one kind of event.
The dispatcher is now `route -> {OutcomesPort, FillSinkPort}` and a third kind would add a third.

### 3. THE I1 ARC-COUNT

Remaining paths, classified against the two measured costs:

| path | mechanism | cost |
|---|---|---|
| **reject -> release** | `OrderOutcomes.on_reject` EXISTS, same shape as `on_cancel`, on the port the dispatcher already holds. One tuple member, one branch, one gate arm. | **CHEAPER than cancel** |
| **pending-timeout -> `resolve_pending_timeouts`** | **NOT a completion.** It is a POLL: `due_for_status_query(now)` then resolve. Needs a per-tick ingress hook (the `Plane1Booker.before` shape) and a `StatusQueryPort` the daemon does not have. §12A:830's deadline is already loaded. | new mechanism, moderate |
| **onset-cancel dispatch** | **BLOCKED on D3.443's missing `pending_entries()`** — the daemon cannot enumerate what to cancel. Prerequisite build, then a dispatch. | one arc incl. the prerequisite |
| **protective-flatten completions** | The whole EXIT half: `StopBook.breached` (needs §5:322's price poll, which nothing has wired — D3.451), `forget`, CLOSING fills (`LimiterFillSink` explicitly does not serve them), §12.10 `closed` rows, `flatten.py` (1396 lines). | **the biggest, 2 arcs** |

**THE NUMBER: 4 more arcs after 047. I1 is a 6-arc capstone in total (046, 047, + 4).**
Range 4–5; the whole variance sits in protective-flatten.

* **ARC A** — reject + pending-timeout (both, one arc: reject is ~1/5 of a fill arc).
* **ARC B** — build `pending_entries()` (D3.443), then wire blackout/HALT onset cancellation.
* **ARC C** — §5:322's FIRST loop input: the price poll + `StopBook.maintain` + `breached`. The
  prerequisite for protective-flatten and the discharge of D3.451.
* **ARC D** — protective-flatten completions + the I1 convergence gate covering all six paths.
  **This is the arc that flips 7/12 -> 8/12, in one step.**

### THE SWARM QUESTION: BATCH, not swarm — 2 workers maximum

The tail does **not** decompose into four independent per-path workers, and the reason is
mechanical rather than aesthetic:

* **`check_limiter_daemon_dispatch.py` is ONE file every remaining path must extend** (check
  contract rule 8 / doctrine C.9: the gate that owns daemon-dispatch already exists, so no path may
  open a new one). Four workers = four concurrent edits to one gate. **ARC 036 / D3.272 lost fifteen
  ledger rows to exactly this shape**, and stayed green while doing it.
* **`WIRED_EVENTS` and `dispatch`'s branch ladder** are single lines that reject, onset and flatten
  all move.
* **ARC C is genuinely independent** — a different loop input, different modules, no completion
  route.

**Recommendation: run the completion ladder SERIALLY (A -> B -> D) with ARC C in PARALLEL against
one of them. Two workers, not four.**

**Point-fixes BEFORE the tail.** The I1 tail is ~4 serialised arcs behind one gate file; I3/I4/I9/I12
are independent and each moves the count on its own. Running them first converts wall-clock that
would otherwise be blocked on a merge point into board movement, and gives ARC D more measured
ground to converge over.

### 4. Named cascades this slice touched and does NOT own

* **The Plane-1 `filled` row — D3.434.** `seam.EventKind` has no member for it (*a member lands here
  ONLY when the machinery that emits it exists*), and adding one is a frozen-seam edit.
* **Stop trailing / maintenance (§4:190-196)** — armed here, never ratcheted. **New: D3.451.**
* **The event-driven balance refresh (§6.4b)** — **new: D3.452.**
* **D3.443's `pending_entries()`** — the onset path's prerequisite, unchanged and still owed.

---

## S5 — THE GATE: `check_limiter_daemon_dispatch` EXTENDED (rule 8 — no new file, no count move)

New arms: `_arm_fill`, `_arm_fill_feedback`, `_arm_fill_idempotent`. `SUBJECTS` grew to include
`scripts/nixrisk/fills.py` — the arm that PLACES the stop lives there, and a plant in it must be
able to redden this gate.

**THE SAFETY ARM fires on the PAIR, not either half:** *the capital moved* and *no stop exists* are
each ordinary alone; only together are they the defect. It is evaluated BEFORE every other fill
assertion.

**DEMONSTRATED FAIL — three plants, each applied to real source, each reverted byte-identical:**

| plant | site | exit | the REASON it named |
|---|---|---|---|
| **A** — fill route removed | `scripts/limiterd.py` | **1** | `THE DAEMON DID NOT CONVERT` — drained by the loop (`consumed=2`), `committed still 2100.0`, `Σ open margin 0`, `fills_dispatched=0`; plus `released=1, not 2` and `outstanding=1` at the process boundary |
| **B — THE SAFETY PLANT** — stop placement removed, conversion still runs | **`scripts/nixrisk/fills.py`** | **1** | **`UNPROTECTED POSITION. The daemon RELEASED 2100.0 ... and its stop book holds NO STOP for that order (stops=[], unstopped=[{...}])`** + §12.1's synthetic-stop reasoning |
| **C** — §4:214 dedup defeated | `scripts/nixrisk/completions.py` | **1** | `DOUBLE FILL DISPATCH ... fills_dispatched=2, not 1`; `duplicates=0 — the dedup did not see it`; `handled=2`; `the LEDGER booked 1 refusal` (I2's guard covered, and that is the tell) |

**Plants removed -> exit 0**, with non-vacuous evidence naming the drive, the pid, the source file,
the stop level and both Σ figures.

**A finding the plant produced by accident, now D3.450:** under PLANT B the LEDGER released
(`2100 -> 0`) while §3's picture never advanced — the release runs at step 2 and the commit lives
inside step 3, which raised. The reachable unplanted case is a fill whose venue symbol disagrees
with the approval. Recorded, not repaired: the fix belongs inside `fills.py`'s step order and
`fills.py` is byte-identical across this arc by assertion.

---

## FREEZE

**Diff scope against `1d241e2`:** `scripts/limiterd.py`, `scripts/nixrisk/completions.py`,
`checks/check_limiter_daemon_dispatch.py`, `scripts/tests/test_check_limiter_daemon_dispatch.py`,
`scripts/tests/test_completions.py`, `docs/CHECK-DEBT.md`, **plus two the brief's freeze list did
not name and which are EXPLAINED rather than reverted:**
`checks/uncalled_entry_points_baseline.json` and `scripts/tests/test_check_uncalled_entry_points.py`
— the brief itself required *"watch `check_uncalled_entry_points` shrink ... name which"*, and that
baseline is a ONE-WAY RATCHET whose test FAILS on a silent shrink. Recording the shrink is
mandatory, not optional. **Which rows moved, named:**
`positions.py::PositionOriginWriter.unstopped` and `stops.py::StopBook.stops` LEFT the baseline
(the daemon's published state enumerates both), and `join.py::production_origins` LEFT
`_ARC034_CARRIED` (the daemon's approval calls it, so every minted `trade_id` comes from the
PRODUCTION join). Each `reason` string was rewritten to say what left and why.

**BYTE-IDENTICAL, proven with `git hash-object` vs `1d241e2`:** `outcomes.py`, `reservations.py`
(I2) · `fills.py`, `stops.py`, `positions.py`, `picture.py`, `execution.py`, `join.py`,
`fill_seam.py` (the §4 cascade) · `flatten.py`, `blackout.py` (I11) · `loop.py`, `seam.py`,
`recovery.py`, `wal.py`, `plane1_sink.py` (the sole-writer seam and the mirror). **The cancel path
inside `completions.py` is unchanged line-for-line** — the diff there is additive.

## CLOSE-OUT

* **(b) DERIVED reverse-dependency closure + the D3.444 by-detection backstop** (the import graph is
  blind to subprocess and Protocol callers, so the closure was taken by detection over the changed
  modules): **209 passed, 0 failed** across 12 modules. RED-before / GREEN-after on this arc's own
  defect is PLANT B specifically: the missing stop.
  *Pre-existing and NOT caused by this arc:* `test_arc038_c_open_is_confirmed_fill.py` and
  `test_arc038_f_inflight_lock.py` cannot be collected under `.venv-dev` — `import zmq` in
  `nixbus/statebus.py`, which this arc did not touch (`git diff --stat 1d241e2 -- scripts/nixbus/`
  is empty). `zmq 27.1.0` is present in `.venv` and absent from `.venv-dev`.
* **(c) THE GATE IS BOUND** from all three plants above, each naming its site.
* **TRIPWIRE GUARD (the 044/045 finding):** `test_check_order_path_bans.py` and
  `test_check_uncalled_entry_points.py` were run EXPLICITLY, not left to a testmon selection.
* **(d)** Four CHECK-DEBT rows opened (**D3.449, D3.450, D3.451, D3.452**) and the **ARC 047 series
  row written**: `399`, derived by `check_derived_claims`'s `ledger_rows` over the merged tree, not
  typed and not `395 + 4`. `check_derived_claims` passes **13/13** with
  `check_debt_open_items=399 [derived:ledger_rows=399, stated:series_table_latest_row=399]`.

## RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged. The count STAYS 7/12.** Two of ~6 paths wired (cancel, fill); reject,
  pending-timeout, onset and protective-flatten remain.
* **D3.442 shrinks:** daemon-invoked now — `OrderOutcomes.on_cancel`, `LimiterFillSink.on_fill`,
  `FillHandler.on_fill`, `StopBook.arm`, `IocRemainder.release_remainder`,
  `PositionOriginWriter.on_fill`, `EntryOrderOrigins.record`, `ApprovedOrderBook.record`,
  `ExecutionLedger.ingest`, `FinancialPictureBook.commit`. Still owed — `OrderOutcomes.on_reject`,
  `resolve_pending_timeouts`, `due_for_status_query`, `StopBook.maintain`/`breached`/`forget`,
  everything in `flatten.py`.
* **No order was placed and nothing was sent.** The IOC remainder cancel is RECORDED (D3.449).
* The Plane-1 `filled` row (D3.434), stop trailing (D3.451), the balance refresh (D3.452),
  D3.443's `pending_entries()`, and D3.428/D3.438-D3.441/D3.446-D3.448/D3.359/360/361/363 stand.

## BADGE

**Limiter STAYS RED. Count STAYS 7/12. I1 path-progress: 2 of ~6 wired.**
When I1 fully lands it flips to 8/12 in one step — **ARC D of the four above.**
