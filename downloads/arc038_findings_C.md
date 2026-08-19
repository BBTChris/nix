# ARC 038 sub-agent C — THE EXIT BRAKE (I3 zero-wire exit · I4 confirmed-fill-only)

Worktree: `/home/bbt/nix-wt-arc-038-c`   Branch: `arc-038-c`
Interpreter: `/home/bbt/nix-wt-arc-038-c/.venv/bin/python` (CPython 3.14.4)
Invariants assigned: **I3** (`§14:969` + `§14:977`), **I4** (`§14:970`)

Quoted verbatim from the frozen authority `docs/nics_risk_subsystem_spec_v1.3.md`:

* `§14:968` — *"Every uncertainty resolves toward **flat**. Known state beats optimal state."*
* `§14:969` — *"The exit/protective path has **zero wire/delivery dependency**."*
* `§14:970` — *"'Open' = **confirmed fill** only. Never optimistic."*
* `§14:977` — *"Detection may live anywhere; **execution of any flatten is Limiter-only**
  (Sentinel excepted, as last resort when the Limiter itself is dead)."*
* `§3:167` — the exit diagram: *"Limiter … → broker-order (in-process, direct call) →
  sender thread → flatten"*, and *"Protective exit always wins over discretionary exit."*
* `§12.4:625` — *"**Disk-critical** (WAL cannot append) ⇒ HALT new entries — no audit
  trail, no new risk. **Open positions remain protected (stops read memory, not disk).**"*

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I3 (zero wire) | real `ipc://` bus peer `SIGKILL`ed **and** publisher socket closed, real Postgres at a dead Unix socket with a group-commit thread failing 10× concurrently, real `/dev/shm` segment unlinked — one at a time and ALL AT ONCE; synthetic stop driven to breach each time | **RESISTED** (flatten observed at the broker seam every arm; worst latency **0.247 ms**) | `check_flatten` | **yes** — plant P1 (a `picture.publish` on the protective path) reddened it | **yes** — named `scripts/nixrisk/flatten.py:fire[zero-wire]` |
| I3 (delivery dependency) | real disk-critical WAL (kernel `EFBIG`, errno 27) with 3 open positions, then with 3 pending entries | **VIOLATION — FC1, DISCHARGED** (before: 1 of 3 flattened, 2 left open; after: 3 of 3, `still_open=[]`) | `check_flatten`, `check_plane1_degraded` | **no** — plant P3 (the exit awaiting its Plane-1 record) left BOTH green, and 93/93 relevant pytest tests passed | **NO — FINDING FC5** |
| I3 (protective > discretionary) | both authorities at one trade, both arrival orders, sequential AND under real threads with the arbiter's read-modify-write window forced open | **VIOLATION — FC2, DISCHARGED** (threaded: recorded winner became `discretionary`, `hard_reset=False`; post-fix protective wins in both orders) | `check_flatten` | **yes** — plant P2 (precedence removed) reddened it | **yes** — named `flatten.py:request_close[precedence-reverse]`; but its contention is single-threaded |
| I4 (confirmed fill only) | placement ack + reservation + working order, NO fill, then the same rig given a real fill (both halves, ack half first) | **RESISTED** (every open-reading surface empty on the ack; all of them fill in on the fill) | `check_execution_ledger`, `check_fill_handler`, `check_fill_seam` | **no** — plant P4 (the `filled_qty <= 0` refusal deleted) left all three green | **NO** for the gates; `scripts/tests/test_execution.py` DOES redden (2 failures) — the property is suite-covered, gate-uncovered |
| I4 (converse: a real fill that does NOT read open) | fill ingested by the ledger, origin write then refused (`UntradableSymbol`); plus duplicate / out-of-order / dropped reports | **VIOLATION — FC3, DISCHARGED** (idempotent re-delivery refused as a contradiction) and **VIOLATION — FC4, BLOCKS** (published picture and Allocator mirror read FLAT over a real filled position) | `check_fill_handler` (drives the sink) | **partially** — the gate drives `LimiterFillSink` but only ever with a NEW `exec_id` (`_LATE_FILL = ("CO-1","e2",1,4)`), never a re-delivery of a seen one | **no arm exists for either** |

## FINDINGS

### FC1 — a disk-critical WAL ABORTS the protective flatten, leaving open positions unflattened

- **Invariant:** I3 — `§14:969` *"The exit/protective path has **zero wire/delivery
  dependency**."* and `§12.4:625` *"Open positions remain protected (stops read memory,
  not disk)."*
- **Site:** `scripts/nixrisk/flatten.py:789` — `self._plane1.enqueue(` inside `_book`,
  reached on the protective path from `flatten.py:569` (`request_close` → `_book`) and
  from `flatten.py:623` (`cancel_entries_on_onset` → `_book`). `Plane1Wal.enqueue`
  (`scripts/nixrisk/wal.py:306`) raises `DiskCritical` in `DISK_CRITICAL`, and
  `Plane1Enqueuer.enqueue` (`scripts/nixrisk/degraded.py:363`) propagates it unchanged
  by documented design (*"Raises what the WAL raises"*).
- **Scenario (executed):** a child process with `signal.SIGXFSZ` ignored and
  `RLIMIT_FSIZE = 4096`, so the KERNEL refuses the WAL append with `EFBIG` — the same
  plant `scripts/plane1_degraded_drill.py` uses. A real `Plane1Wal`, a real
  `Plane1Enqueuer`, a real `ProtectiveFlatten`, and THREE open positions at the broker
  seam. Fill the WAL to `DISK_CRITICAL`, then
  `fire(SYNTHETIC_STOP, symbol=None, targets=[T-0/MESU6, T-1/MNQU6, T-2/MYMU6])`.
  Command: `.venv/bin/python <scratch>/attack_i3_diskcritical.py <wal> --rlimit`
  (control arm: identical, without `--rlimit`).
- **Observed:**

  ```
  CONTROL  {"wal_state":"healthy","accepted_rows":4000,"fire_raised":"",
            "flatten_calls":["MESU6","MNQU6","MYMU6"],"still_open_at_broker":[],
            "outcomes":[true,true,true],"fire_latency_ms":0.074}
  CRITICAL {"wal_state":"disk_critical","accepted_rows":22,
            "wal_refusal":"WAL … could not append 192 bytes: OSError errno=27 File too large",
            "fire_raised":"DiskCritical: WAL … is DISK-CRITICAL (OSError errno=27 …)",
            "flatten_calls":["MESU6"],"still_open_at_broker":["MNQU6","MYMU6"],
            "outcomes":null,"closed_records":["T-0"],"fire_latency_ms":0.024}
  ```

  **Two of three open positions were never flattened**, `fire()` returned no
  `FlattenAction` at all, and the caller cannot tell which targets were closed. The same
  shape on the onset sweep (`attack_i3_onset.py`): `cancel_calls == ["c-1"]`,
  `uncancelled_entries == ["c-2","c-3"]`, `reservations_still_outstanding == ["c-2","c-3"]`
  — so `§3:172`'s *"Blackout/HALT onset ⇒ Limiter cancels all pending ENTRY orders"* also
  aborts, leaving orders working inside a window they were not approved for.
- **Why the tests did not catch it:** `DiskCritical` does not appear anywhere in
  `checks/check_flatten.py`, `checks/check_fill_handler.py`, `checks/check_fill_seam.py`,
  `checks/check_execution_ledger.py`, `checks/check_session_flatten.py`,
  `scripts/tests/test_flatten.py`, `scripts/tests/test_fills_and_join.py` or
  `scripts/tests/test_execution.py` (grep: zero hits). Every one of them injects a
  Plane-1 recorder that cannot fail — `test_flatten.py`'s `Plane1Recorder.enqueue` is
  `self.rows.append(row)`. `test_flatten.py`'s zero-wire arm removes the **picture**
  wire only (`DeadPictureSink`), which the exit never touches. See FC5 for the gate half.
- **Status:** **DISCHARGED IN THIS ARC.** `_book` no longer lets a persistence failure
  abort the exit: the enqueue is attempted, and a failure is RECORDED on a new
  observable (`ProtectiveFlatten.unbooked`) instead of propagating. §12.4 is
  explicit that degraded persistence is not degraded trading, and `§14:968` makes flat
  the resolution of every uncertainty — losing the audit row while the position is
  flattened is strictly better than keeping neither. The softening is the one already
  precedented three lines away in this same file (`_realized_or_reason`'s docstring:
  *"§14 makes the protective exit's booking zero-wire and non-optional, so a malformed
  cost fact must not be able to stop the Limiter from recording that a position
  closed"*). Control: `scripts/tests/test_arc038_c_exit_brake.py`, whose can-fail proof
  is the pre-fix behaviour driven against a subclass that restores the propagation.
  **The onset sweep had a SECOND abort source and it was found by re-measuring after
  the fix, not by reading.** With `_book` no longer propagating, the sweep still
  stopped at one cancel. The traceback from the post-fix drive:
  `flatten.py:cancel_entries_on_onset → reservations.py:368 resolve → :441 _settle →
  :498 _emit → degraded.py:378 enqueue → wal.py:307 enqueue` raising `DiskCritical`.
  `reservations.py:_emit` is entitled to decide about ITS OWN row (it names the
  residual, CHECK-DEBT D3.53); it is not entitled to decide whether the other entries
  in the sweep get cancelled, and that decision lives in `cancel_entries_on_onset`.
  So `resolve` is now wrapped PER ENTRY there, recorded on `ProtectiveFlatten.unbooked`, and the
  sweep continues. `reservations.py` is NOT edited — it is another sub-agent's
  invariant this arc, and cross-branch edits are how ARC 037 got its defects.
  Post-fix, both arms:

  ```
  CRITICAL {"wal_state":"disk_critical","fire_raised":"",
            "flatten_calls":["MESU6","MNQU6","MYMU6"],"still_open_at_broker":[],
            "outcomes":[true,true,true],"closed_records":["T-0","T-1","T-2"],
            "fire_latency_ms":0.090}
  CRITICAL (onset) {"raised":"","cancel_calls":["c-1","c-2","c-3"],
            "uncancelled_entries":[],"reported_cancelled":["c-1","c-2","c-3"],
            "reservations_still_outstanding":[]}
  CONTROL  (onset) identical — so the fix did not change the healthy path.
  ```


  **The first shape of this fix was REFUSED by an existing gate, and that refusal
  is the good news.** The observable was written as a `unbooked_rows()` accessor;
  `check_uncalled_entry_points` (via `test_check_uncalled_entry_points.py`) failed
  the commit naming it exactly: *"findings that are neither in the baseline nor in
  ARC 034's named carried set — this is NEW uncalled surface and it is a fresh
  failure: ['scripts/nixrisk/flatten.py::ProtectiveFlatten.unbooked_rows']"*. It
  is right: nothing in shipped code calls it and nothing CAN until D3.368 is
  wired, which is the D3.150 / D3.178 class this whole arc exists to hunt — a verb
  built, gated, and driven by nothing. Its baseline is a one-way ratchet that may
  only shrink, so accepting a new row was not available and would have been the
  wrong move anyway. The observable is now the public attribute
  `ProtectiveFlatten.unbooked`, which is the idiom every other observable in this
  neighbourhood already uses (`writes`, `duplicates`, `refusals`, `enqueued`,
  `fsyncs`) and which adds no callable surface for a caller that does not exist.
  Post-change: `pytest test_arc038_c_exit_brake.py
  test_arc038_c_open_is_confirmed_fill.py test_check_uncalled_entry_points.py -q`
  → **53 passed**.
- **Debt row:** D3.368 (the residual: nothing yet ROUTES `unbooked` into §12.9's
  alert tiers), D3.369 (the `reservations.py:498` abort source, its measured
  consequence, and the ruling owed on whether `_emit` should absorb its own failure
  for every OTHER caller too).

### FC2 — the dual-authority arbiter's read-modify-write loses protective precedence under contention

- **Invariant:** I3 / `§3:172` *"Protective exit always wins over discretionary exit."*
  (`flatten.py`'s own docstring: *"the arbiter in `request_close` … refuses to let a
  discretionary close override a protective one"*.)
- **Site:** `scripts/nixrisk/flatten.py:534` — `prior = self._closed.get(target.trade_id)`
  and `scripts/nixrisk/flatten.py:567` — `self._closed[target.trade_id] = record`. The
  decision is read at 534 and committed at 567 with no mutual exclusion between them.
- **Scenario (executed):** two real `threading.Thread`s calling `request_close` for the
  same `trade_id` with opposite authorities, with `self._closed` replaced by a `dict`
  subclass whose `get` blocks the first reader — so the interleaving is FORCED rather
  than guessed at with a sleep. Both arrival orders driven.
  Command: `.venv/bin/python <scratch>/attack_i3_precedence.py`
- **Observed:** sequential arm (what the shipped tests drive) is correct in both orders.
  Threaded arm, protective completing first:

  ```
  interleaving: ["held:read prior=None", "free:read prior=None",
                 "free:wrote protective", "held:wrote discretionary"]
  final_winner: "discretionary"   hard_reset: false   superseded: null
  ```

  The protective close is erased from the arbiter's record, and `hard_reset=False` means
  §4's one-in-flight slot is never freed for that strategy.
- **Why the tests did not catch it:** `test_flatten.py`'s three precedence controls and
  `check_flatten`'s `precedence` arm drive both orderings **sequentially**. The suite
  docstring says *"precedence is proven only under CONTENTION"* and then defines
  contention as two ordered calls; the read-modify-write window is never opened.
- **Honest reachability:** `§5` mandates a single-threaded Limiter loop, so nothing in
  this tree reaches the interleaving today. Nothing ENFORCES it either —
  `FinancialPictureBook.commit` (`picture.py:350`) has a real second-writer guard for
  exactly this hazard on the picture, and the arbiter has none.
- **Status:** **DISCHARGED IN THIS ARC.** A `threading.Lock` around the arbiter's
  critical section. Blocking, not `acquire(blocking=False)`: a non-blocking refusal
  would let a discretionary close in flight REFUSE a protective one, which is the
  invariant inverted. Uncontended acquire is ~40 ns, so `§11`'s hot path is unaffected,
  and the single-threaded case is bit-for-bit unchanged. The body moved verbatim into
  `_arbitrate` rather than being re-indented in place, so the diff itself shows the fix
  is a SERIALISATION and not a re-decision; `test_the_SEQUENTIAL_precedence_rules_are_
  UNCHANGED_by_the_lock` pins that claim.

  **The fix taught the harness something, and the harness was wrong first.** My first
  contention harness joined the second thread BEFORE releasing the held one. Unlocked
  that works; locked it deadlocks the harness — the second thread is waiting on
  `_arbiter`, the first is waiting on the gate, and my `join(10.0)` returned with the
  thread still alive. Two of three runs failed with *"a contending thread hung"*, which
  I could have "fixed" by widening the timeout and would then have been measuring a
  slow harness. Restructured to a SHORT join, then release, then a generous join — and
  the short join's outcome became a reading in its own right:
  `free_completed_before_release` is `True` unlocked (the interleaving really happened,
  so half one is non-vacuous) and `False` locked (the second thread really was waiting
  on the lock, so the verdict is the lock's and not luck's). With the lock reverted, the
  control now reddens on THAT assertion in both parametrisations, before it even reaches
  the winner.
- **Debt row:** D3.370.

### FC3 — an idempotent broker re-delivery is refused as a CONTRADICTION, because the only shipped adapter re-stamps `ts` per delivery

- **Invariant:** I4 converse — `§14:970` and `§15:1006`'s *"idempotent exec-report
  dedup"*; `execution.py`'s own contract (`§4`, quoted at `execution.py:10`):
  *"broker events are deduplicated by `(order_id, exec_id)` … duplicate or out-of-order
  execution reports"*.
- **Site:** `scripts/nixrisk/fills.py:718` — `ts=self._clock(),` inside
  `LimiterFillSink.on_fill`'s `ExecutionReport(...)` construction. `ts` is a member of
  `_IDENTITY_FIELDS` (`scripts/nixrisk/execution.py:115`), so
  `ExecutionLedger._on_duplicate_key` (`execution.py:474`) sees a disagreement on every
  re-delivery and raises `ContradictoryExecution`.
- **Scenario (executed):** the full entry seam (`ApprovedOrderBook` → `LimiterFillSink`
  → `FillHandler` → `StopBook` / `IocRemainder` / `PositionOriginWriter` → real
  `FinancialPictureBook` over a real `ipc://` bus → real `Plane1Wal`). Deliver one fill,
  then deliver **the byte-identical §2A `on_fill` event again** — the §12.4 reconnect
  case the ledger says it exists for.
  Command: `.venv/bin/python <scratch>/attack_i4.py <dir>`
- **Observed:**

  ```
  duplicate_raised: "ContradictoryExecution: execution ('c-dup','e-1') was already
    reported with different data: ts: 1787095703.778361 then 1787095703.7784965 —
    §4 makes a RE-DELIVERY idempotent, not a rewrite, so this is a broker inconsistency"
  ledger_contradictions: 1     ledger_duplicates: 0
  remainder_refused_releases: 1   re_arms_declined: 1
  replay_with_original_ts: "duplicate"      <-- idempotent when ts is preserved
  ```

  The position is not double-counted (`after_first: 1`, `after_duplicate: 1`), so this
  fails closed on the money — but the handler RAISES on a benign, expected event, and
  the raise happens after the remainder release has already been re-attempted. Any
  adapter loop that treats the exception as fatal drops every LATER exec for that order,
  which understates a real position — `§14:968`'s dangerous direction.
- **Why the tests did not catch it:** `scripts/tests/test_execution.py` proves
  duplicate-immunity thoroughly but at the **ledger**, with hand-built
  `ExecutionReport`s that carry the same `ts` by construction. The only test/gate that
  drives the **sink** is `checks/check_fill_handler.py`, and its re-delivery is
  `_LATE_FILL = ("CO-1", "e2", 1, 4)` — a NEW `exec_id`, i.e. a later fill, never a
  re-delivery of a seen one. So the property is green at the layer that cannot invent a
  `ts` and untested at the layer that does.
- **Status:** **DISCHARGED IN THIS ARC.** `LimiterFillSink` memoizes its receipt stamp
  per `(client_order_id, exec_id)`, so a re-delivery presents the identical report and
  the ledger answers `DUPLICATE`. The fix is in the class that invented the value and
  leaves `_IDENTITY_FIELDS` intact, so a future adapter carrying a real venue timestamp
  still gets the cross-check.
- **Debt row:** D3.371.

### FC4 — a confirmed fill the origin write refuses leaves the published picture and the Allocator mirror reading FLAT, with no escalation record and no Plane-1 trace

- **Invariant:** I4 converse — `§14:970` and `§14:968` *"Every uncertainty resolves
  toward **flat**."*
- **Site:** `scripts/nixrisk/positions.py:547` — `raise UntradableSymbol(` inside `_row`,
  which runs AFTER `scripts/nixrisk/positions.py:470` — `outcome = self._ledger.ingest(report)`
  and after `FillHandler._arm` (`fills.py:626`) has already armed the stop and
  `IocRemainder.release_remainder` has already released the reservation.
- **Scenario (executed):** the same real end-to-end rig, with `margin_per_contract`
  empty for the filled symbol — `§4:198`'s not-tradable condition, reachable mid-session
  from a margin poll that drops a symbol. Deliver a real 2-lot fill.
- **Observed:**

  ```
  raised: "fill c-naked/e-1: symbol 'MESU6' is absent from the published margin field set…"
  position_table_states:          []        <- the Limiter publishes FLAT
  allocator_mirror_open_trades:   []        <- the Allocator's real mirror agrees: FLAT
  exec_ledger_net_qty:            2         <- the fill IS a fact
  ledger_reconcile_vs_published:  [{"derived_net_qty":2,"row_size":0,"drift":2,"agrees":false}]
  stop_book_armed:                ["c-naked"]
  writer_unstopped_records:       0         <- NO escalation record
  wal_row_kinds:                  ["reservation_taken","reservation_released"]  <- no fill trace
  sum_reservations:               2000.0 while reservations_outstanding == []
  ```

  A real 2-lot position exists at the broker; `§3`'s published table and `§12.7`'s
  Allocator mirror both say flat, so `§7`'s correlation/aggregate caps price the held
  exposure at zero and **fail open by admitting more** — D3.136's failure mode under a
  new spelling. `§9`'s durable record has no trace that anything filled. And unlike the
  sibling refusal (`_refuse_unstopped`, `positions.py:507`, which deliberately records an
  `UnstoppedRecord` so *"the condition is recorded where a supervising loop can act on
  it instead of vanishing into a log"*), this path records nothing but a counter. The
  asymmetry is the defect.
- **Why the tests did not catch it:** `checks/check_origin_write.py` and
  `scripts/tests/test_positions.py` assert that the refusal HAPPENS and names its
  reason. Neither then asks what the published picture, the Allocator mirror, or `§9`'s
  record believe afterwards — the refusal is treated as the end of the story rather than
  as the beginning of a state that no longer matches the broker.
- **Status:** **BLOCKS — nothing fixed. This defines ARC 039.** A minimal, local,
  reversible fix does not exist inside the freeze: the repair requires an architect
  ruling on which of two things happens — publish the row anyway with the exposure the
  fill really carries (and what margin figure), or hand `nixrisk.flatten` an
  `UNCERTAINTY` trigger from this site — plus a consumer for whichever surface carries
  it. Inventing either inside a freeze is the feature the freeze forbids. What this arc
  DOES add is the measurement: the drive above is now a standing control
  (`test_arc038_c_open_is_confirmed_fill.py::test_a_REFUSED_ORIGIN_WRITE_leaves_the_PICTURE_and_the_MIRROR_reading_FLAT`)
  that pins the observed state, so the repair has something to move.
- **Debt row:** D3.372.

### FC5 — `check_plane1_degraded` is GREEN over §12.4's *"open positions remain protected"*: it proves DETECTION and never drives EXECUTION

- **Invariant:** I3 / `§12.4:625`.
- **Site:** `scripts/plane1_degraded_drill.py:1160-1163` —

  ```python
      breach_price = armed.level - STOP_TICK
      breached = book.breached(STOP_SYMBOL, breach_price)
  ```

  The C2 arm ends there. `ProtectiveFlatten` is never constructed in the drill; `flatten`
  is never called; no broker seam is present in the child at all.
- **Scenario (executed):** plant P3 — `request_close` books its Plane-1 row BEFORE the
  broker call, which is FC1's worst form (with a disk-critical WAL the flatten never
  happens *at all*, not merely partially). Then run every instrument that claims the
  property.
- **Observed:**

  ```
  === PLANT P3_exit_awaits_its_record in scripts/nixrisk/flatten.py (sha 3386a57f… -> 085b3184…) ===
  --- check_flatten rc=0
  pass: scripts/nixrisk/flatten.py: drove zero-wire fire, dual-authority precedence …
  --- check_plane1_degraded rc=0
  pass: … STOP FIRED ANYWAY: with an append probe raising DiskCritical in the same
        instant, price 4989.75 breached ['p1c-0001'] armed at 4990.0 …
  === RESTORE P3: sha 3386a57f…  byte-identical=YES ===
  ```

  and `pytest test_flatten.py test_check_flatten.py test_degraded.py test_wal.py
  test_exit_integration.py test_session_flatten.py -q` → **93 passed** WITH THE PLANT IN.
  The gate's own evidence string is the confession: *"STOP FIRED ANYWAY … breached
  ['p1c-0001']"* — `breached()` is a pure arithmetic read over in-memory state and
  cannot fail for a disk reason, so asserting it under disk-critical asserts a tautology.
  It is the `CHECK-A7` shape one layer out: not a classifier whose output is a constant,
  but a *subject* whose outcome is independent of the deprivation being applied.
- **Why the tests did not catch it:** they are the thing that did not catch it. The
  drill's honesty note explains why it does NOT read
  `Plane1Wal.protective_exit_allowed()` (an unconditional `True`) and then substitutes a
  subject one step short of the property: the spec sentence is *"open positions remain
  **protected**"*, and a position is protected when it is FLATTENED, not when a
  breach is computed.
- **Status:** **DISCHARGED-BY-GATE (new suite), fix in FC1.** The measurement is added as
  `scripts/tests/test_arc038_c_exit_brake.py`, not as a new `checks/check_*.py`:
  doctrine C.9 forbids a second instrument re-asserting what an existing one asserts,
  and the right STANDING home is a C3 arm inside `scripts/plane1_degraded_drill.py`
  (which already builds the disk-critical child) — recorded as D3.373 rather than done
  here, because the drill is `check_plane1_degraded`'s subject and editing another
  invariant's gate from this branch is how ARC 037 got cross-branch defects.
- **Debt row:** D3.373.

## PROOFS OF RESISTANCE

### RC1 — I3 held against every wire deprivation, one at a time and all at once

- **Attack:** five arms in one process. (a0) control, everything alive. (a1) a real
  child `StateSubscriber` on a real `ipc://` endpoint, `SIGKILL`ed and reaped with `-9`,
  then the publisher socket CLOSED so `StateBusPictureSink.emit` really raises. (a2)
  `PGHOST` pointed at a non-existent Unix socket directory, with real WAL rows made
  durable and a background thread calling `GroupCommitWriter.drain_once()` in a loop
  during the fire — non-vacuity asserted (`assert first.error`). (a3) a real `/dev/shm`
  segment created via `PriceRingWriter` and unlinked, with `segment_exists` proving
  before/after. (a4) all of the above simultaneously. Each arm arms a real `StopBook`
  stop, ticks it, requires `breached()` non-empty (`assert breached, "the drive is
  vacuous"`), then fires and observes the REAL in-process `broker.flatten(symbol)`
  invocation and its arguments.
- **Command + output:** `.venv/bin/python <scratch>/attack_i3_deprive.py <dir>`

  ```
  a0_control_all_alive           flatten_observed [["flatten",["MESU6"]]] still_open [] 0.0740 ms  bus_deltas 1
  a1_bus_peer_SIGKILLED_and_socket_closed
                                 flatten_observed [["flatten",["MESU6"]]] still_open [] 0.1182 ms
                                 peer_reap_status -9   emit_raises "ZMQError"
  a2_postgres_DEAD_SOCKET_mid_group_commit
                                 flatten_observed [["flatten",["MESU6"]]] still_open [] 0.2232 ms
                                 first_drain_error "SinkError: cannot read max(wal_seq) from
                                   nix_plane1.plane1_event_log: psql: error: Unix-domain socket path …"
                                 concurrent_drain_errors 10
  a3_dev_shm_price_ring_UNLINKED flatten_observed [["flatten",["MESU6"]]] still_open [] 0.0498 ms
                                 segment nix_arc038c_2686227  existed_before true  gone_after true
  a4_ALL_AT_ONCE                 flatten_observed [["flatten",["MESU6"]]] still_open [] 0.2469 ms
                                 peer_reap_status -9  shm_gone true  concurrent_drain_errors 10
  ```

- **What this does and does NOT prove:** it proves the exit reaches the broker with the
  state bus, Postgres and `/dev/shm` all unavailable, and that it does so in **0.05–0.25
  ms** — three to four orders of magnitude below any socket timeout, so no arm "fired
  eventually because something timed out". It does NOT prove the exit survives the
  **local WAL** being unwritable: that is FC1, and this matrix deliberately kept the WAL
  healthy so FC1 could not mask the other four deprivations. It also does not speak to
  the Sentinel case (`§14:977`'s exception) — a killed Limiter is R4 and out of scope.

### RC2 — the exit path is DIRECT: no queue, no future, no topic, no event loop, no socket

- **Attack:** two independent instruments over the LIVE call. (1) a `sys.setprofile`
  census of every function entered during `fire()`, reduced to modules. (2) a
  `sys.addaudithook` that RAISES on any `socket.*` / `subprocess.*` / `os.exec*` /
  `os.fork` / `urllib.*` / `ssl.*` audit event while the exit is on the stack, with
  `socket.socket` additionally monkey-patched to raise, and `asyncio.get_running_loop()`
  proven to fail first (no loop exists).
- **Command + output:** `.venv/bin/python <scratch>/attack_i3_direct.py <dir>`

  ```
  profile_census: functions_called 23   banned_module_hits []
    modules_touched ["__main__","dataclasses","enum","json","nixrisk"]
    nixrisk_frames_on_exit_path [degraded.Plane1Enqueuer.enqueue, degraded.natural_key,
      flatten.ProtectiveFlatten._book, …_realized_or_reason, …_realizing_fields,
      …fire, …fire.<locals>.<genexpr>, …request_close, wal.Plane1Wal.enqueue, wal.encode_row]
    flatten_observed [["flatten","MESU6"]]
  profile_census_canfail: socket_frames_detected
    ["socket.socket.__init__","socket.socket._real_close","socket.socket.close"]
  audit_hook: no_running_loop "RuntimeError: no running event loop"   raised ""
    flatten_observed [["flatten","MESU6"],["flatten","MESU6"]]   latency_ms 0.0919
  audit_hook_canfail: raised_on_real_socket
    "WireTouched: the exit path touched the wire: audit event 'socket.__new__'"
  ```

- **What this does and does NOT prove:** it proves, by measurement rather than reading,
  that the shipped exit path enters exactly 23 functions, touches no
  `asyncio`/`queue`/`concurrent`/`threading`/`socket`/`select`/`zmq`/`subprocess`/
  `nixbus`/`nixrisk.picture`/`nixrisk.plane1_sink` frame, and issues no socket,
  subprocess or exec syscall — so there is no enqueue-onto-a-queue, await-a-future,
  publish-to-a-topic or schedule-on-a-loop that a dead dependency could stall. Both
  instruments are shown able to fail on a real wire touch. It does NOT prove the same of
  a FUTURE caller that wraps `fire()`; the census covers the path from `fire` inward.
  It also positively identifies the one delivery dependency that IS on the path —
  `Plane1Wal.enqueue`'s `write(2)` — which is exactly FC1.

### RC3 — I4 held: a placement ack reads open NOWHERE (both halves, ack half first)

- **Attack:** one rig, two halves. Half one: `ApprovedOrderBook.record` +
  `EntryOrderOrigins.record` + `ReservationLedger.take` + a picture commit — an approved,
  reserved, WORKING order, with NO fill — then read all seven surfaces. Half two: the
  same rig given a real §2A `on_fill`, and the same seven surfaces re-read. Plus the two
  direct routes an ack could take into the fill path, driven and required to refuse by name.
- **Command + output:** `.venv/bin/python <scratch>/attack_i4.py <dir>`

  ```
  half1_ACK_ONLY:
    position_table_states        []            position_table_open_trades []
    sum_open_margin              0             sum_reservations 2000.0   committed 2000.0
    reservations_outstanding     ["c-ack-1"]   stop_book_armed  []
    exec_ledger_net_qty          0             exec_ledger_is_flat true
    allocator_mirror_open_trades []            allocator_mirror_committed 2000.0
    wal_row_kinds                ["reservation_taken"]
    writer_writes 0    sink_delivered 0
    refusals.zero_qty_report  "c-ack-1/ack: filled_qty=0 — an execution moves a positive
                               quantity; a zero/negative increment is a fill no arithmetic can see"
    refusals.unapproved_fill  "broker fill never-approved/e1 in 'MESU6': this Limiter holds
                               no approved order under that id, so the fill's SIDE cannot be resolved …"
  half2_CONFIRMED_FILL:
    position_table_states        ["open"]      position_table_open_trades ["c-ack-1"]
    sum_open_margin              2000.0        sum_reservations 0.0      committed 2000.0
    reservations_outstanding     []            stop_book_armed  ["c-ack-1"]
    exec_ledger_net_qty          2             exec_ledger_is_flat false
    allocator_mirror_open_trades ["c-ack-1"]   allocator_mirror_committed 2000.0
    writer_writes 1    sink_delivered 1
  ```

- **What this does and does NOT prove:** the ack half is non-vacuous *because* the fill
  half moves every one of the same seven readings. Specifically: the ack contributes to
  `committed` only through `sum_reservations` (`§3` / `§15 C1`: *committed = Σ open
  margin + Σ pending reservations*), never through `sum_open_margin`
  (`picture.py:114`'s `OPEN_MARGIN_STATES = {OPEN, CLOSING}`); the ack does NOT arm a
  synthetic stop (the arm happens inside `FillHandler._arm`, from the confirmed fill —
  a pre-arm attempt was refused as `DuplicateStop`, which is itself the `§4`
  convert-once property); and the real Allocator mirror on the real `ipc://` wire agrees.
  Mechanically, `PositionState.OPEN` is written at exactly TWO sites in the whole tree
  (`grep -rn "PositionState.OPEN" scripts/ --include=*.py` minus tests/checks):
  `positions.py:560`, reachable only from `on_fill` after a fill was ingested, and
  `projection.py:830`, which reads a Plane-1 projection row. `PositionState.PENDING` and
  `PositionState.RESERVED` have **no writer anywhere in the tree** — so there is no state
  that a placement could set. What this does NOT prove: it says nothing about a *future*
  ack-handling verb, and `FillHandler`'s docstring claim (*"There is no verb here for an
  ack, a pending order or an optimistic position"*) is now measured rather than asserted
  only for the surfaces listed above.

### RC4 — duplicate / out-of-order / dropped exec reports do not corrupt the position

- **Attack:** on the same rig — an exact re-delivery, then `e-3` delivered BEFORE `e-2`,
  then a fill at the broker whose report never arrives.
- **Command + output:** (same script)

  ```
  after_first 1   after_duplicate 1        <- no double count (the raise is FC3)
  after_out_of_order_e3 2  after_late_e2 3 <- order-independent; correct total
  disagreements [(3,2),(2,3)]              <- both cumulative disagreements RECORDED, not swallowed
  dropped_report_published_size 3   dropped_report_exec_ledger 3
  ```

- **What this does and does NOT prove:** the derived position is a symmetric function of
  the unique fill set, so reordering cannot move it, and the venue-vs-ledger cumulative
  disagreement that out-of-order delivery necessarily creates is recorded by name rather
  than dropped. It does NOT prove the DROPPED case is safe: with a 4th real fill at the
  broker and no report, every Limiter-side surface reads 3 and only broker truth knows
  it is 4. Nothing in the Limiter detects that; `ExecutionLedger.reconcile` compares the
  ledger against `§3`'s published rows, not against the broker, so it agrees. Closing
  that is cold-start/orphan reconciliation and is another sub-agent's invariant — stated
  here as a residual, not claimed as covered.

### RC5 — the Plane-1 projection cannot read open on an ack, but for a reason that is a GAP

- **Attack:** a throwaway PostgreSQL database (`nixp1t_arc038c_*`) loaded from
  `databases/schema/plane1.sql`, one hand-written `filled` row for a PARTIAL fill
  (1 of 3), then `projection.read_log` → `fold_events` → `position_rows`.
- **Command + output:** (same script)

  ```
  EventKind_has_FILLED     false
  log_rows                 1
  folded_states            ["partial"]
  position_rows_states     ["open"]
  open_positions_includes  ["partial"]
  ```

- **What this does and does NOT prove:** `projection._HANDLERS` keys on
  `filled`/`cancel`/`closed`/`protective_exit`/`sentinel_flatten` only, and every one of
  those handlers refuses to move a position with `qty_filled == 0` — so no projection row
  can exist without a fill event, and `position_rows`' unconditional
  `state=PositionState.OPEN` cannot manufacture an optimistic open. But the reason no
  `filled` row ever reaches Plane 1 from this tree is that `EventKind` **has no `FILLED`
  member** (measured above; `plane1_sink.EVENT_KIND_TO_PLANE1` cannot map what does not
  exist). So `§9`'s durable record holds no evidence that any position ever opened, and
  the projection is exercised only by hand-written rows. That is a real gap in the
  event-sourced record, adjacent to D3.281, and it is reported rather than counted as a
  guarantee. Separately, `folded_states ["partial"] → position_rows ["open"]` erases the
  *remainder-unresolved* fact when crossing into the seam type; `§4` makes position =
  actual filled quantity, so the SIZE is right and this is not an optimistic open, but a
  consumer cannot tell a resolved position from an unresolved one. Recorded as D3.374.

## GATE AUDIT

### `check_flatten`
- **Claims:** I3 — zero-wire exit, dual-authority precedence, onset-cancel causes,
  reconcile-then-publish. (`pass:` line: *"drove zero-wire fire, dual-authority precedence
  under contention, onset-cancel cause booking + refusal, and reconcile-then-publish …
  4 arms, each with a falsifier proven to lose its property"*.)
- **Scope containment proven by:** plant P1 and plant P2 both flipped it `rc=0 → rc=1`
  and both named `scripts/nixrisk/flatten.py` sites, so the gate really imports and
  drives the worktree's subject. (`PYTHONPATH` is unset in this worktree and
  `nixrisk.flatten.__file__` resolves to `/home/bbt/nix-wt-arc-038-c/…`, printed and
  checked — the D3.344 defeat is ruled out.)
- **Plant P1:** `request_close` publishes the picture before the broker call
  (`self._picture.publish(self._picture.current())` inserted at `flatten.py:556`)
  → **verdict: RED**, naming
  `scripts/nixrisk/flatten.py:fire[zero-wire]: fire() RAISED ConnectionError: state bus
  down / ZMQ unavailable with the wire dead — the protective path has a wire dependency
  (§14: ZERO wire/delivery dependency required)`.
- **Plant P2:** the precedence branch disabled (`if prior is not None and False:`)
  → **verdict: RED**, naming `flatten.py:request_close[precedence-reverse]` three times,
  including *"winner changed to ClosedRecord(… authority=DISCRETIONARY … hard_reset=False
  …)"* and *"broker.flatten('MESU6') was called 2 time(s)"*.
- **Plant P3:** the exit books its Plane-1 row BEFORE calling the broker → **verdict:
  GREEN (FINDING FC5)**. `rc=0`, `pass:` with the identical evidence string.
- **Restore:** `cp` from a pre-plant copy, then `sha256sum`. Every plant restored to
  `3386a57f217b2753e4d6b67a9bf5da1d86a500f4ebc0a75f4d2df615dc223d66`
  (`byte-identical=YES` printed for each), and `git status --short` empty afterwards.
  Gate green again (`rc=0`).

### `check_plane1_degraded`
- **Claims:** `§12.4` in full, including *"Open positions remain protected (stops read
  memory, not disk)"*.
- **Scope containment proven by:** its own evidence — a REAL cluster killed with
  `-m immediate` (postmaster 2739881 absent from `/proc`), a REAL `EFBIG` refusal after
  18 rows, a scratch database, and a stop armed and breached inside the disk-critical
  child. The gate is emphatically not vacuous about *persistence*.
- **Plant P3:** the exit made dependent on its Plane-1 record → **verdict: GREEN
  (FINDING FC5)**. Its C2 arm never constructs `ProtectiveFlatten` and never calls
  `flatten`, so no plant on the exit path can reach it. Its subject under deprivation is
  `StopBook.breached()`, a pure arithmetic read whose outcome is independent of the
  deprivation.
- **Restore:** byte-identical (sha above); gate green again.

### `check_execution_ledger`, `check_fill_handler`, `check_fill_seam`
- **Claims:** I4 — `§4`'s idempotent execution ledger, the fill seam, the fill handler.
- **Scope containment proven by:** all three import and drive the worktree modules
  (`check_fill_handler` builds the real `LimiterFillSink` at `check_fill_handler.py:639`
  and feeds it through `_feed`). Containment of the *subject* is proven; containment of
  the *branch* is what fails below.
- **Plant P4:** the `filled_qty <= 0` refusal deleted from
  `ExecutionReport.__post_init__` (`execution.py:184`) — the one structural control that
  makes a placement ack unrepresentable as a fill, i.e. the exact negation of `§14:970`
  → **all three GREEN (`rc=0`)**. The plant was proven live in the same breath:
  `ExecutionReport(..., filled_qty=0, ...)` constructed successfully and
  `ExecutionLedger.ingest` accepted it (`fill_count=1`).
- **BUT:** `pytest scripts/tests/test_execution.py … -q` under the same plant →
  `2 failed, 108 passed`, naming
  `test_a_report_with_impossible_QUANTITIES_is_refused_at_construction[0-0-filled_qty=0]`.
  So the invariant IS mechanically guarded — by a suite, not by a standing gate. Reported
  as a gate-coverage gap, **not** inflated into an unguarded invariant, and **no new
  `checks/check_*.py`** is added for it: doctrine C.9 forbids a second instrument
  re-asserting what `test_execution.py` already asserts. Recorded as D3.375.
- **Plant for FC3:** none available — there is no arm to plant against. The gate's only
  re-delivery is `_LATE_FILL = ("CO-1","e2",1,4)`, a new `exec_id`. The gap is proven by
  scope inspection plus the executed drive in FC3, and closed by
  `scripts/tests/test_arc038_c_open_is_confirmed_fill.py`.
- **Restore:** `execution.py` restored to
  `d78bf197b1b0572007c7a5e9dd6772b815c823fd8db68bfaf09df54709fe08c7`
  (`byte-identical=YES`); all three gates green again.

### `check_synthetic_stop_only`, `check_session_flatten`
- **Claims:** `§12.1`'s no-broker-side-stop prohibition; `§6.1b`'s session-close flatten.
- **Baseline:** both `rc=0`. `check_synthetic_stop_only` is structurally non-vacuous by
  construction (it proves an ABSENCE — no order-placement verb, no broker import, no
  native stop order-type token on the stop path) and my `sys.setprofile` census is the
  independent confirmation: `stops.py` frames appear on no path that reaches a broker
  verb, and `StopBook` holds no Plane-1 sink at all.
- **Not planted:** neither claims the two properties I was assigned, and planting a
  frozen file to exercise a gate that does not claim my invariant would be a freeze
  violation with no finding behind it. Stated as a deliberate omission rather than
  reported as coverage.

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL

| suite/control | plant used | reddened? | site named | restored green? |
|---|---|---|---|---|
| `test_arc038_c_exit_brake.py::test_the_EXIT_FIRES_EVERY_TARGET_with_the_WAL_DISK_CRITICAL` | `_PropagatingEverything` — a subclass restoring BOTH pre-fix propagations (`_book`'s and the onset sweep's); plus the fix itself reverted in the real subject | **yes** | asserts `errno=27` really came from the kernel and `DiskCritical` from the port BEFORE judging the exit, then `flatten_observed == ["MESU6"]` and `still_open == ["MNQU6","MYMU6"]` pre-fix | yes |
| `test_arc038_c_exit_brake.py::test_the_ONSET_SWEEP_CANCELS_EVERY_ENTRY_with_the_WAL_DISK_CRITICAL` | same subclass — and it must restore BOTH propagations, because this arm's abort came from `reservations.py:498`, not from `_book` | **yes** | `cancel_observed == ["c-1"]` and `reservations_outstanding == ["c-2","c-3"]` pre-fix; post-fix all three plus a `RESERVATION_RELEASED` row on `ProtectiveFlatten.unbooked` | yes |
| `test_arc038_c_exit_brake.py::test_the_UNBOOKED_ROWS_are_RECORDED_and_NAME_the_persistence_reason` | `_AngryPlane1`, raising a NON-`DiskCritical` `OSError` — so the control proves `_book` catches the PORT's failures, not one concrete WAL exception | **yes** | asserts the row's kind, trade_id, symbol AND the port's own reason text; never a count alone (rule 11) | yes — and the healthy half requires `ProtectiveFlatten.unbooked` EMPTY, so non-empty is information |
| `test_arc038_c_exit_brake.py::test_PROTECTIVE_WINS_under_a_REAL_THREADED_RACE_in_BOTH_orders` | `_UnlockedArbiter` — a subclass restoring the pre-fix unlocked read-modify-write; plus the fix itself reverted in the real subject | **yes, in BOTH parametrisations** | `free_completed_before_release is False` (*"the second thread completed while the first was still inside the critical section — the arbiter is NOT serialising, and the verdict below would be luck rather than the lock"*), then the winner assertion naming §3:172 | yes |
| `test_arc038_c_exit_brake.py::test_the_EXIT_PATH_TOUCHES_NO_WIRE_MODULE` (`sys.setprofile` census) | `_WireCoupledFlatten` — publishes the picture on the exit path | **yes** | half one FAILS unless `nixrisk.picture` appears in the census, so a blind census is caught before the subject is judged; half two names every offending frame | yes |
| `test_arc038_c_open_is_confirmed_fill.py::test_an_ACK_reads_OPEN_NOWHERE_and_a_FILL_reads_OPEN_EVERYWHERE` | the pair IS the control: the ack half requires all seven surfaces EMPTY, the fill half requires every one of them to MOVE, and the `_Rig` constructor refuses to proceed unless the real subscription was SEEN (so an empty mirror can never be a transport artefact) | **yes** | names the surface that read open, quoting §14:970 / §15 C1 / §4 per surface | yes |
| `test_arc038_c_open_is_confirmed_fill.py::test_a_RE_DELIVERED_FILL_is_a_DUPLICATE_not_a_CONTRADICTION` | `_PerDeliveryStamp` — a subclass restoring the pre-fix per-delivery stamp; plus the fix itself reverted in the real subject | **yes** | requires `"ts:"` in the raised message, so a contradiction for ANY OTHER reason fails the control rather than satisfying it | yes |
| `test_arc038_c_open_is_confirmed_fill.py::test_a_REFUSED_ORIGIN_WRITE_leaves_the_PICTURE_and_the_MIRROR_reading_FLAT` | pins FC4's observed state; the can-fail half is the CONTROL rig with the margin PRESENT, which must publish the row or the arm is measuring the rig | **yes** | asserts the refusal's text, the ledger's `fill_count`, `drift=2`, and that `unstopped()` is empty — each with a message saying *"if this reddens, FC4 is fixed and THIS assertion is the one to rewrite"* | n/a — it pins a defect, so green means still-broken by design |

Every control asserts a MESSAGE, a SITE or a FIELD — never an exit code (check contract
rule 11, `nix_check_contract.md` §18). Both-halves discipline (ARC 035): each control
runs the UNPROTECTED half first and requires the bad outcome to APPEAR, then the
protected half and requires it GONE.

## WHAT I COULD NOT MEASURE, AND WHY

1. **The Sentinel exception to `§14:977`.** A killed Limiter's last-resort flatten is R4
   and not built (`_R4_TRIGGERS` refuses `SENTINEL` by name). Cannot-measure: the subject
   does not exist. Nothing in this report may be read as covering a dead Limiter.
2. **A stale venue timestamp on a fill.** `§2A`'s `on_fill` event carries no venue
   timestamp at all — `LimiterFillSink` stamps `self._clock()` — so "a fill with a stale
   `venue_ts`" is not representable on the shipped seam. Cannot-measure, with the reason.
   (`Balance.venue_seq_ts` exists but is a balance field, not a fill field.)
3. **The `ReservationLedger.resolve` abort under disk-critical.** The onset sweep has a
   SECOND abort source in `reservations.py`'s own enqueue. In my drive the abort came
   from `_book` (c-1's reservation WAS released before the raise), so the FC1 fix
   restores the sweep in the case I could construct; I did not construct a case where
   `resolve` itself raises mid-sweep, because `reservations.py` is another sub-agent's
   invariant and editing it from this branch is the cross-branch defect ARC 037 measured.
   Recorded as D3.369.
4. **Whether a real broker adapter treats FC3's `ContradictoryExecution` as fatal.** No
   IBKR/Tradovate adapter exists in this tree, so the consequence chain ("the loop dies
   and later execs are lost") is an inference from the raise, not a measurement. The
   raise itself, and the fact that the identical report with the original `ts` returns
   `DUPLICATE`, are both measured.
5. **Production wiring of `ProtectiveFlatten`.** No daemon constructs one (all eight
   construction sites are gates and tests), so every latency figure here is a
   single-process in-line measurement, not a live-system one.
6. **`/dev/shm` as an exit dependency.** `grep -rln "shm|price_ring" scripts/nixrisk/`
   returns nothing — the Limiter's exit path does not use the price ring at all, so the
   unlink arm proves indifference rather than resistance to a dependency that exists.
7. **A pre-existing foreign `/dev/shm` segment.** `nix_drill_0541edc49967_0` appeared in
   `/dev/shm` during this audit and is NOT mine (my segments are `nix_arc038c_<pid>*`,
   all reaped — verified `ls /dev/shm | grep nix` clean after my runs). It is a sibling
   worktree's live drill; I did not unlink it. Flagged for the integrator: it is the
   D3.347 shape.

## FILES I CHANGED (path — why — tied to which finding)

| path | why | finding |
|---|---|---|
| `scripts/nixrisk/flatten.py` | `_book` records a persistence failure instead of propagating it, so a disk-critical WAL cannot abort the exit; a `threading.Lock` makes the arbiter's read-modify-write atomic | **FC1**, **FC2** |
| `scripts/nixrisk/fills.py` | `LimiterFillSink` memoizes its receipt stamp per `(client_order_id, exec_id)` so a re-delivery is byte-identical and dedups | **FC3** |
| `scripts/tests/test_arc038_c_exit_brake.py` | new — the I3 controls, each with its can-fail twin | FC1, FC2, FC5 |
| `scripts/tests/test_arc038_c_open_is_confirmed_fill.py` | new — the I4 controls, both halves | FC3, FC4, RC3 |
| `downloads/arc038_findings_C.md` | this file | — |
| `downloads/arc038_debt_C.md` | ready-to-paste ledger rows D3.368–D3.375 | — |

**Diffed against the frozen SHAs, as the contract says the integrator will.**
`git hash-object` for all 30 files in
`/home/bbt/nix/scratchpad/arc038/frozen_limiter_shas.txt`, compared to the recorded
blob hashes:

```
CHANGED: scripts/nixrisk/fills.py
CHANGED: scripts/nixrisk/flatten.py
```

Two files, both named by a finding written down first, and the other 28 frozen
Limiter modules byte-identical to the freeze — including `reservations.py`, which
FC1's second site runs THROUGH and which I deliberately did not edit.

No `checks/check_*.py` was added. Reason: doctrine C.9 forbids a second instrument
re-asserting what an existing one asserts, and for FC1/FC5 the correct STANDING home is a
new arm inside `scripts/plane1_degraded_drill.py` (already `check_plane1_degraded`'s
subject and already building the disk-critical child) — proposed as D3.373 rather than
done from this branch. `checks/registry.json` is therefore untouched.

## CAN-FAIL, PROVEN THE HARD WAY: EACH FIX REMOVED, EACH SUITE REQUIRED TO REDDEN

Beyond the in-test falsifier halves, each of the three fixes was REVERTED in the real
subject and the suite required to go red naming the reason. Restores verified by
`sha256sum` (`byte-identical=YES` each time) and `git status --short`.

```
=== UNFIX FC1_book_propagates (scripts/nixrisk/flatten.py) ===
>   assert good["fire_raised"] == "", (
        f"the exit raised {good['fire_raised']!r} with the WAL disk-critical — ...
restore byte-identical=YES

=== UNFIX FC2_lock_removed (scripts/nixrisk/flatten.py) ===
E   AssertionError: a discretionary close became the recorded winner over a
    protective one (['held:read prior=None', 'free:read prior=None',
    'free:wrote protective', 'held:wrote discretionary',
    'MainThread:read prior=discretionary']) — §3:172 makes protective ALWAYS win
E   assert <CloseAuthority.DISCRETIONARY: 'discretionary'> is <CloseAuthority.PROTECTIVE: 'protective'>
restore byte-identical=YES

=== UNFIX FC3_per_delivery_stamp (scripts/nixrisk/fills.py) ===
E   nixrisk.execution.ContradictoryExecution: execution ('c-dup', 'e-1') was already
    reported with different data: ts: 1787097666.494944 then 1787097666.994752 …
FAILED …::test_a_RE_DELIVERED_FILL_is_a_DUPLICATE_not_a_CONTRADICTION
restore byte-identical=YES
```

## SUITE AND GATE NUMBERS

Interpreter `/home/bbt/nix-wt-arc-038-c/.venv/bin/python` (CPython 3.14.4).

**My own suites** — `pytest scripts/tests/test_arc038_c_exit_brake.py
scripts/tests/test_arc038_c_open_is_confirmed_fill.py -q` → **16 passed**
(8 + 8). With `test_check_flatten.py` (the re-pointed anchor) → **25 passed**.

**The contract's Limiter selection** —
`pytest scripts/tests -q -k "risk or limiter or gate or reservation or flatten or
picture or plane1 or halt or blackout or survival or fill or execution"`.
First run after the fixes: `1 failed, 1205 passed, 1 skipped, 2072 deselected in
326.08s` — the single failure was `test_check_flatten.py::
test_an_ONSET_CAUSE_COLLAPSED_TO_CANCEL_fails_and_NAMES_the_wrong_cause`, whose
text-plant anchor had gained an indent level from FC1's `try:`. That is a real
consequence of a frozen-file edit and it is recorded rather than quietly patched:
`_plant` asserts its anchor appears EXACTLY ONCE, which is why a stale anchor
reddened instead of planting nothing. Anchor re-pointed, suite → 9 passed.

**Full suite** (required, because frozen files changed): run as the commit's own
`Stage 3 — runtime pass` hook. Six sibling worktrees were running full suites
concurrently, so wall time was dominated by contention rather than by this branch.

**Gates, after the fixes** — all `rc=0`: `check_flatten`, `check_plane1_degraded`,
`check_fill_handler`, `check_fill_seam`, `check_execution_ledger`,
`check_session_flatten`, `check_synthetic_stop_only`, `check_origin_write`,
`check_reservation_lifecycle`, `check_realized_pnl`, `check_allocator_lifecycle`,
`check_orphan_recovery`, `check_sentinel_deadman`.

**Lint hooks on every changed file** — `ruff check`, `ruff format`, `pylint`,
`mypy`, `bandit (production)`, `bandit (tests)`, `complexipy`: all **Passed**.
`flatten.py` crossed pylint's 1000-line default when the reasoning landed
(1075); the `too-many-lines` disable carries its justification inline, following
this tree's own precedent rather than cutting the measured numbers out of the
docstrings.

**Final re-measure, after the last edit** (the discharges, re-driven against the
ORIGINAL attack scripts):

```
FC1 flatten, disk-critical:  wal_state disk_critical  fire_raised ''
                             flatten_calls [MESU6, MNQU6, MYMU6]  still_open []  0.112 ms
FC1 onset,   disk-critical:  raised ''  cancel_calls [c-1,c-2,c-3]
                             uncancelled []  reservations_still_outstanding []
I3 deprivation matrix:       a0 0.0738 ms · a1 0.0808 ms · a2 0.124 ms ·
                             a3 0.1032 ms · a4 ALL_AT_ONCE 0.1103 ms
                             flatten observed, still_open [] in every arm
```

## CLEANUP

Every `/dev/shm` segment I created was named `nix_arc038c_<pid>` and reaped in a
`finally` (`ls /dev/shm | grep nix` shows none of mine). The throwaway Postgres
database `nixp1t_arc038c_*` was dropped (`psql -lqt | grep -c nixp1t_arc038c` →
`0`). Every plant backup (`*.arc038c.bak`, `*.uf`) was restored and removed, each
restore verified by `sha256sum`. All scratch scripts live outside the repo in the
session scratchpad. `git status --short` is empty.

**Not mine, flagged for the integrator:** `/dev/shm` acquired
`nix_drill_0541edc49967_0` and later `nix_drill_9d48ad5ee397_c` DURING this audit.
Neither matches my prefix; they are a sibling worktree's live drill. I did not
unlink them — killing another agent's segment mid-run would be worse than the leak
— but this is the D3.347 shape and the arc that owns them should reap them.

## COMMITS

- `<sha1>` — ARC 038 sub-agent C: the findings file, written BEFORE any fix
- `<sha2>` — ARC 038 sub-agent C: the exit brake — FC1/FC2/FC3 DISCHARGED, FC4/FC5 named

(exact shas: `git log --oneline arc-038-c`)
