# ARC 038 sub-agent B — THE RESERVATION LEDGER (I2: exactly one terminal release)

Worktree: `/home/bbt/nix-wt-arc-038-b`   Branch: `arc-038-b`
Interpreter: `/home/bbt/nix-wt-arc-038-b/.venv/bin/python` (CPython 3.14.4, GIL enabled — `sys._is_gil_enabled()` → `True`)
Invariants assigned: **I2** — `nics_risk_subsystem_spec_v1.3.md` §14:972, *"**Every reservation reaches exactly one terminal release.**"*, with §15 C1:985 (*"committed = open + pending reservations; release on every terminal path (double-spend race closed)"*), §3:111, §6.5:408, §11:579 read directly.

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I2 (leak) | a real `Plane1Wal` made disk-critical by a real `RLIMIT_FSIZE`/EFBIG refusal, driven through the real `GatePass` | **VIOLATION — F-B1, DISCHARGED** | `check_reservation_lifecycle` | yes — it imports `/home/bbt/nix-wt-arc-038-b/scripts/nixrisk/reservations.py` by absolute path, printed from its own `load()` | yes on 4/4 plants, each naming `scripts/nixrisk/reservations.py:<site>` — **but green over F-B1, which it never plants** |
| I2 (leak, per-path) | AST census of every production `resolve`/`release` call site against the frozen `TerminalPath` | **VIOLATION — F-B3, BLOCKS** (3 of 6 paths have no production caller) | `check_reservation_lifecycle` | yes | n/a — the gate drives the LEDGER over all 6 paths and is structurally green over the wiring gap; its own evidence says so, with a stale reason (F-B6) |
| I2 (leak, in the fill path) | plant: keep the IOC cancel, skip only `resolve` | **VIOLATION — F-B2, DISCHARGED** (gate was GREEN over the plant) | `check_fill_handler` | yes — `fills.py` is a declared `SUBJECT` and the gate builds a real `ReservationLedger` + real `IocRemainder` | **NO before this arc; YES after** — ARM TERMINALITY added, 4/4 plants RED naming the site |
| I2 (double release) | fill racing a blackout-onset cancel, real threads, 4,000 iterations, switch interval at its floor | **RESISTED** (0 arithmetic violations) — with a residual: 18/4,000 produced a bare `KeyError` from `resolve` (F-B5, BLOCKS) | `check_reservation_lifecycle` | yes | yes — an absorbed double release and a Σ double-decrement both RED |
| I2 (double release) | partial fill, a sequence of partials summing to the whole, an over-fill, a late reject after a timeout release | **RESISTED** | `check_fill_handler` | yes | yes |
| I2 (the watcher) | Σ float drift vs `AUDIT_TOLERANCE` over a long legitimate drive | **VIOLATION of the instrument — F-B4, BLOCKS** | `check_reservation_lifecycle`'s tolerance/separation arm | yes | yes — a widened tolerance is RED naming `AUDIT_TOLERANCE` |
| I2 (crash) | real `SIGKILL` between the store mutation and the durable §12.10 append, in both orders, against a real `Plane1Wal` | **RESISTED in memory** — restart is flat and nothing comes back twice; residual is F-B7 (no Plane-1 pairing instrument exists) | none exists | n/a | n/a |
| I2 (identity) | id reuse after a terminal release; two orders colliding on one id; empty / whitespace / `None` ids; margin 0, negative, NaN, inf, sub-`MIN_MARGIN`, 1e300 | **RESISTED on every margin and every duplicate**; degenerate ids accepted (F-B6b, recorded) | `check_reservation_lifecycle` + `test_reservations.py` | yes | yes |

---

## FINDINGS

### F-B1 — a `take` whose §12.10 Plane-1 row is REFUSED leaves the reservation held forever, and the gate turns that into a DENY

- **Invariant:** I2 (§14:972, *"Every reservation reaches exactly one terminal release."*). This reservation reaches **zero**.
- **Site:** `scripts/nixrisk/reservations.py:403` `ReservationLedger._book` — the four store writes and `self._sigma += margin` precede `self._emit(EventKind.RESERVATION_TAKEN, …)` with nothing between them, combined with `scripts/nixrisk/gate.py:834-846` — `reservation_id = self._ledger.take(final, now).reservation_id` inside `except Exception as exc: … return self._deny("reservation_ledger", …)`.
- **Scenario (executed):** the real Plane-1 sink is `nixrisk.wal.Plane1Wal`, whose `enqueue` raises `DiskCritical` when the WAL is disk-critical or the append fails with `OSError` (`wal.py:304-320`), and §12.4 makes that a real condition. Driven with a real `Plane1Wal` on a real file under a real kernel refusal — `resource.setrlimit(RLIMIT_FSIZE, (700, hard))` with `SIGXFSZ` ignored so the `write(2)` returns EFBIG instead of killing the process — and the real `GatePass` with the shipped `default_manifest`, six approvable orders:
  `.venv/bin/python scratchpad/arc038b/p5_book_leak.py`
- **Observed:**
  ```
  WAL path=/tmp/arc038b_2702223_.../plane1.wal RLIMIT_FSIZE=700B  wal.state=disk_critical
  alerts fired: [('wal_disk_critical', '...: OSError errno=27 File too large')]
  APPROVED 3: ['c-0', 'c-1', 'c-2']
  DENIED   3: ('c-3','deny','reservation_ledger', 'the §3 reservation could not be taken (DiskCritical: ...')
              ('c-4', …) ('c-5', …)
  ledger.outstanding()   = 6 reservations  [... ('RSV-00000004','c-3',4000.0), ('RSV-00000005','c-4',4000.0), ('RSV-00000006','c-5',4000.0)]
  ledger.total_reserved()= 24000.0
  audit(): aggregate=24000.0 scanned=24000.0 drift=0.0 material=False taken=6 released=0
  *** RESERVATIONS HELD FOR ORDERS THE GATE DENIED: 3 -> [('c-3',4000.0),('c-4',4000.0),('c-5',4000.0)]
  *** Sigma leaked by DENIED orders = 12000.0
  ```
  Three orders were DENIED and never sent, so no fill, cancel, reject, timeout or onset event can ever arrive for them: 12000.0 of margin is committed for the life of the process. It happens once per approval attempt while the disk is critical, so Σ climbs monotonically until §3 Phase B (`committed + proposed < 70% × balance`) denies everything, and it survives the disk recovering — only a restart clears it. `audit()` reports `drift=0.0, material=False` throughout, because a leak breaks no arithmetic identity and §11.7's reconcile is structurally blind to one, exactly as the module's own docstring predicts.
- **Why the tests did not catch it:** `scripts/tests/test_limiter_gate.py::test_a_LEDGER_THAT_CANNOT_TAKE_turns_an_APPROVAL_into_a_DENY` drives this exact condition — and with a FAKE ledger (`Ledger(explode=True)`) that raises on the FIRST line of `take`, before anything is booked. It then asserts only the DENY, the rule name and the word "over-commitment". The real ledger's partial mutation is invisible to a double that has no stores. `check_reservation_lifecycle` never plants a raising Plane-1 sink; its §7.12 list asks what would make it pass while measuring nothing and does not include "the sink refuses". CHECK-DEBT D3.53 records the atomicity gap for `_settle` (the RELEASE direction, "failure direction undecided") and explicitly never analyses `_book`, nor names the `gate.py` DENY that turns it into a permanent leak.
- **Status:** **DISCHARGED IN THIS ARC.** `_book` is now all-or-nothing: Σ is saved, the mutation happens, the emit runs inside a `try`, and on any exception the two store writes are undone and Σ is restored **by assignment** (not by `-= margin`, which would not return to the same bits and would inject the very drift §11.7 watches). `_settle`'s deliberate mutate-then-record order is untouched — that is D3.53's ruling and the permissive direction the spec chose. Re-measured: leaked Σ 12000.0 → **0.0**; `check_reservation_lifecycle` still green; `check_fill_handler` still green.
  Controls, and the proof they can fail: `scripts/tests/test_arc038_b_reservation_terminality.py` runs the UNPROTECTED half first (`PreRepairLedger`, which reconstructs the pre-repair behaviour from the parent's own pieces rather than copying its body) and **requires the leak to appear** — `outstanding()==1`, Σ=4938.0, `drift==0.0`; then the repaired half requires it gone with Σ compared bit-identically. Reverting the repair in the real module reddens exactly three controls, each naming the reason:
  ```
  FAILED …::test_a_REFUSED_PLANE1_APPEND_TAKES_NOTHING
  FAILED …::test_a_WITHDRAWN_TAKE_frees_the_CLIENT_ORDER_ID_for_a_retry
  FAILED …::test_the_REAL_PLANE1_WAL_under_a_REAL_KERNEL_REFUSAL_takes_nothing
  E  AssertionError: a take whose §12.10 row was refused left a reservation behind …
  E  assert ['c-held', 'c-refused'] == ['c-held']
  E  nixrisk.reservations.DuplicateReservation: c-1: already holds live reservation RSV-00000001 …
  E  AssertionError: the real WAL accepted 2 take row(s) and the ledger holds 6 reservation(s) …
  3 failed, 8 passed
  ```
- **Debt row:** none opened — discharged. (D3.53 stays open for the `_settle` direction it actually names.)

### F-B2 — `check_fill_handler` was GREEN over a planted §14 leak in its own declared subject

- **Invariant:** I2 (§14:972) as the shipped fill path implements it.
- **Site:** `checks/check_fill_handler.py` — every arm (`sequence_defects`, `ordering_defects`, `causation_defects`, `partial_defects`, `_cancel_defects`, `once_defects`, `cap_defects`, `conformance_defects`) and `grep` for `total_reserved|sum_reservations|\.releases|refused_releases|outstanding()|RELEASE_REMAINDER|cancels_issued|over_fills` over the file returned **nothing**. The gate builds a real `ReservationLedger` (`:627`) and a real `IocRemainder` (`:628`) and takes real reservations in `_approve` (`:645`), then never reads any of it back.
- **Scenario (executed):** plant into the real `scripts/nixrisk/fills.py` — keep `_cancel_if_short` (so the IOC cancel still fires and `_cancel_defects` sees nothing wrong) and skip only the `resolve` call for every partial fill:
  ```python
  if filled_qty < requested_qty:
      return self._reservations.total_reserved()
  resolution = self._reservations.resolve(client_order_id, TerminalPath.FILL, …)
  ```
  then `.venv/bin/python checks/check_fill_handler.py`.
- **Observed:** **`rc=0`, `pass:`** — and the evidence string went on saying `steps observed per first fill [ARM_STOP+RELEASE_REMAINDER+ORIGIN_WRITE]`, `4 full three-step sequence(s)`, `2 order(s) filled SHORT with 2 IOC cancel(s)`, while the gate's own module docstring claims (`:65-66`) *"an IOC cancel is issued for the short orders and NOT for the fully-filled ones, **and the reservation is released**"*. `FillStep.RELEASE_REMAINDER` is appended by `fills.py::FillHandler.on_fill` unconditionally, so the step tuple is a description of that function's source and not of the ledger's state — the exact failure mode `_arm`'s own docstring warns about for `ARM_STOP`, one step over.
- **Why the tests did not catch it:** `partial_defects` asks three questions — the reported filled/requested pair, the published row size, and the cancel count — all of which the plant leaves correct. Nothing anywhere asserted the money moved. And a leak breaks no arithmetic identity, so `reservations.audit()` would not have caught it either.
- **Status:** **DISCHARGED IN THIS ARC** by pointing the existing gate at the gap (doctrine C.9: no second instrument). `checks/check_fill_handler.py` gains **ARM TERMINALITY** with its own drive: all four orders approved FIRST, then filled one at a time, so Σ descends `12900 → 10900 → 7900 → 4500 → 0` and each step is one specific margin. The gate's existing `_run_drive` interleaves approve/fill, so Σ is 0.0 after every fill and a trajectory read off it would be `0 == 0` at every step — the vacuity `debug.md` §7.12 asks about, which is why the arm runs its own drive. It also reads the real ledger's `outstanding()`, `released()` (exactly one record per order, `released_via is FILL`), `audit()` (`material`, `released == taken`), and `IocRemainder.releases / refused_releases / over_fills`. New non-vacuity floor `MIN_SIGMA_STEPS = 3`, strictly below today's 4. Evidence now carries `§14 over the shipped path: 4 Σ step(s) each falling by exactly the reserved margin, 12900.00 of margin proven returned`.
  Proof the new arm can fail — four plants, each RED, each naming the site, each restored byte-identical (sha256 compared) and green again:
  | plant | verdict | site + reason named |
  |---|---|---|
  | pure leak (cancel fires, release skipped) | RED | `…fills.py:IocRemainder.release_remainder[CO-1/sigma]: the fill moved Σ from 12900.0 to 12900.0 — by 0.0, against the 2000.0 this order reserved … A step of 0.0 is a LEAK` |
  | release skipped on every fill | RED | same site; `0 Σ step(s)`, `0.00 of margin proven returned` |
  | wrong terminal cause (`FILL` → `CANCEL`) | RED | `…[CO-1/records]: CO-1 was released via TerminalPath.CANCEL — §3 releases a filled entry's reservation under FILL … puts the wrong one in §9's record of money truth` |
  | Σ double-decrement in `_settle` | RED | `…[CO-1/sigma]: the fill moved Σ from 12900.0 to 8900.0 — by 4000.0, against the 2000.0 this order reserved` |
- **Debt row:** none opened — discharged.

### F-B3 — three of the six terminal paths the frozen seam declares have NO production release site at all

- **Invariant:** I2. §3:151 (transcribed into `seam.py:242-244`): *"taken at approval → released on: fill (converts to open-margin), cancel, reject, pending-timeout resolution, blackout-onset cancellation. **No leak paths.**"*
- **Site:** the absence. AST census over `scripts/nixrisk/*.py` minus tests, resolving the one non-literal `via`:
  | path | production release site |
  |---|---|
  | `FILL` | `fills.py:391` `resolve(client_order_id, TerminalPath.FILL, …)` |
  | `BLACKOUT_ONSET` | `blackout.py:952` `release(reservation_id, TerminalPath.BLACKOUT_ONSET, …)` |
  | `HALT_ONSET` | `flatten.py:615` `resolve(entry.client_order_id, cause, …)`, driven by `halt.py:1034`; `flatten.py:139` `_ONSET_CAUSES` constrains `cause` to `{BLACKOUT_ONSET, HALT_ONSET}` |
  | `CANCEL` | **NONE** |
  | `REJECT` | **NONE** |
  | `PENDING_TIMEOUT` | **NONE** |
- **Scenario (executed):** `.venv/bin/python scratchpad/arc038b/p1_pathcensus.py`, then the reachable consequence driven directly: an IOC entry that fills **nothing**. `IocRemainder._guard` (`fills.py:416`) refuses `filled_qty <= 0`, so:
  ```
  ===== 3c. ZERO fill (order fully cancelled at the venue): 0 of 5 =====
    REFUSED: InvalidRemainder: c-1: filled_qty=0 of requested_qty=5 — §4's remainder is …
    outstanding=1 sigma=6172.5 released=0 audit.material=False drift=0.0
  ```
- **Observed:** the whole proposed margin stays committed with no release path in existence, and §11.7's reconcile reports `drift=0.0`. `ExecutionReport` carries no status field — the fill path is fill-only — so there is no surface on which a reject or a GO-timeout could arrive.
- **Why the tests did not catch it:** every existing control drives the LEDGER, where all six paths work. `check_reservation_lifecycle` parses the six paths from the frozen spec and drives all six through `resolve` itself, so it is green over the wiring. Its evidence names the residual as D3.51 — **and D3.51's stated justification is now false**: it says *"those handlers do not exist … so there is no code to drive and nothing to plant into"*, and `fills.py`, `blackout.py` and `flatten.py`/`halt.py` now exist and call the ledger. A stale exemption covering a gap that has partly closed is the exact ARC 034 class.
- **Status:** **BLOCKS.** Not dischargeable inside the freeze — the repair is new production event handlers (reject, GO-timeout, IOC full-cancel), which is a build arc. What IS shipped is the standing ratchet: `test_the_PRODUCTION_RELEASE_PATH_SET_matches_the_RECORDED_baseline` records `WIRED_PATHS = {FILL, BLACKOUT_ONSET, HALT_ONSET}` and `UNWIRED_PATHS = {CANCEL, REJECT, PENDING_TIMEOUT}` and fails in **both** directions — a path that gains a caller fails asking for the baseline to move, a path that loses one fails as a leak. Its own can-fail proof runs both ways too: a staged module booking `TerminalPath.REJECT` must be SEEN (`sites["REJECT"] == ["rejects.py:3"]`), and `fills.py` with its `FILL` argument replaced must drop FILL and surface as `<unresolved>`.
- **Debt row:** **D3.358**.

### F-B4 — `AUDIT_TOLERANCE` is not a bound: Σ's float drift becomes "material" on pure noise, and the module's stated bound is wrong by four orders

- **Invariant:** I2's watcher. §11.7: *"periodic full-scan audit reconciles every running aggregate vs ground truth (drift ⇒ audit event; material drift ⇒ HALT)"*.
- **Site:** `scripts/nixrisk/reservations.py:243` `LedgerAudit.material` → `return abs(self.drift) > self.tolerance` with `AUDIT_TOLERANCE = 1e-9`; the false claims are at `:64` (*"That drift is real, it is bounded at ~1e-13 for account-scale figures"*) and `:242` (*"§11.7: material drift ⇒ HALT"*).
- **Scenario (executed):** `scratchpad/arc038b/p2_drift.py` — 1–5 concurrent reservations (`CLAUDE.md`'s stated scope), margins uniform on 1200–24000 (ES-to-NQ-scale initial margin), every take released exactly once, **no defect anywhere**, `audit()` read after every operation. Six seeds.
- **Observed:**
  ```
  seed=1729 MATERIAL DRIFT at op 28381: drift=1.0186340659856796e-09 aggregate=188792.45848537193 scanned=188792.4584853709
  seed=1  ops 9034   |drift|=1.0186340659856796e-09
  seed=2  ops 36872  |drift|=1.0477378964424133e-09
  seed=3  ops 19064  |drift|=1.0040821507573128e-09
  seed=4  ops 54716  |drift|=1.0186340659856796e-09
  seed=5  ops 25596  |drift|=1.0040821507573128e-09
  ```
  `_sigma` is an incremental aggregate whose lifetime is the process's, so its representation error is a **random walk that grows without limit**, while the tolerance is a fixed absolute floor. The docstring's 1e-13 is exceeded by four orders. A symmetric `+x` then `-x` at a fixed anchor is exact (measured: 4e6 such operations at five anchors produced `|drift| = 0.0`), so the mechanism is specifically the unordered mixing of different magnitudes — i.e. ordinary trading.
  The severity is bounded and stated: the module that ACTUALLY escalates to HALT is `drift_audit.py`, whose three-band scheme puts 1e-9 at `NOISE_FLOOR` and `MATERIAL_FLOOR` at 1e-3 (`MIN_MARGIN`), so this is **not** a false HALT — it is a false `material=True` from `LedgerAudit`, whose own docstring names HALT as the consequence. Two thresholds six orders apart share one phrase over one subject.
- **Why the tests did not catch it:** `test_reservations.py::test_SIGMA_is_a_RUNNING_AGGREGATE_and_not_a_SCAN_of_the_store` asserts `0.0 < abs(audit.drift) <= AUDIT_TOLERANCE` — over **three** operations. The property under test there is that the drift is non-zero (which proves Σ is incremental, not derived); the bound is asserted incidentally and is never driven past a handful of operations. Nothing anywhere drives the aggregate long enough for the walk to matter.
- **Status:** **BLOCKS**, deliberately. `material ⇒ HALT` is a rule that decides a verdict, so widening or relativising the floor is a `CHECK-A<n>` architect ruling and not a sub-agent's edit — and `check_reservation_lifecycle` refuses any subject whose tolerance exceeds its own 1e-9, so a unilateral widening would redden the gate. The measurement is shipped as a control that requires the crossing (a falsifiable direction: if the drift really were bounded, the control fails and the row can be closed), paired with a control proving the floor is too TIGHT rather than too loose — a double release of the smallest admissible reservation is 1e6 × the tolerance and is still caught.
- **Debt row:** **D3.359**.

### F-B5 — under real concurrency `resolve` raises a bare `KeyError`, not a `Refusal`, and that aborts `flatten`'s onset sweep

- **Invariant:** I2. §15 C1:985 — *"release on every terminal path (double-spend race closed)"*.
- **Site:** `scripts/nixrisk/reservations.py:365-367` — `reservation_id = self._by_order.get(client_order_id)` then `self._settle(self._live[reservation_id], …)`. `_settle` deletes `_live` first and `_by_order` second, so between the two `del`s `_by_order` names an id `_live` no longer holds.
- **Scenario (executed):** `scratchpad/arc038b/p4_race.py` — a fill (`resolve` on the client_order_id, `fills.py`'s shape) racing a blackout-onset cancel (`release` on the reservation_id, `blackout.py`'s shape) on ONE reservation. Real `threading.Thread`s, a real `threading.Barrier(2)`, `sys.setswitchinterval(1e-9)` to maximise interleaving, 4,000 iterations, the full invariant asserted after every one.
- **Observed:**
  ```
  iterations driven: 4000   switchinterval=0.0
  outcome classes:
      3976  ('Reservation', 'Resolution')      # one settled, one refused
        18  ('KeyError',    'Resolution')      # <-- a bare KeyError out of resolve()
         5  ('DoubleRelease','Resolution')
         1  ('Resolution',  'UnknownReservation')
  invariant violations: 0
  ```
  The §14 arithmetic held in all 4,000 — one RELEASED record, Σ back to 0.0, nothing outstanding, `material=False` — because `del self._live[…]` is `_settle`'s first statement and only one thread can win it. But `resolve` is documented as *"Releases, or REFUSES and says why"*, and a `KeyError` is neither: no `RefusalKind`, no reason, not recorded in `refusals()`, indistinguishable from an instrument fault (check contract v2 §11). `flatten.cancel_entries_on_onset` calls `resolve` inside its per-entry loop, so the exception aborts the sweep and the remaining pending entries are neither cancelled nor released — a partial onset, i.e. a leak on the tail.
- **Why the tests did not catch it:** there is no threaded control anywhere over the ledger. The declared model (§11) is a single-threaded Limiter loop, so the class was reasoned about rather than driven.
- **Status:** **BLOCKS** (recorded, not repaired). No production caller reaches it today — `asyncio` is cooperative and cannot interleave inside a synchronous `_settle`, and no `nixrisk` module starts a thread that touches the ledger. A lock on §11's hot path needs its own ruling, and the alternative repair (collapsing the lookup to one `dict` read) changes the four-index design §11 exists to enforce. Shipped instead: a 600-iteration real-thread control asserting the arithmetic, whose own can-fail proof introduces the footprint a won race would leave (Σ decremented twice) and requires `material=True` and `drift == -margin`.
- **Debt row:** **D3.360**.

### F-B6 — both ledger gates print, on every run, that the Limiter's event handlers "do not exist yet"

- **Invariant:** directive 5 (verified on-disk state outranks stale documentation) applied to I2's coverage claim.
- **Site:** `checks/check_reservation_lifecycle.py`'s evidence — `UNBOUND (D3.51): drives the LEDGER, never the Limiter's event handlers, which do not exist yet` — and `checks/check_execution_ledger.py`'s — `UNBOUND: drives the LEDGER, never the Limiter's broker-event handlers, which do not exist yet (the D3.51 residual, one module over)`. The same sentence is also in each gate's module docstring and in `reservations.py`'s closing paragraph.
- **Scenario (executed):** run both gates and read the evidence; census the handlers.
- **Observed:** three handlers exist and call the ledger (`fills.py:391`, `blackout.py:952`, `flatten.py:615`). The false half runs in the direction that EXCUSES coverage, which is precisely the D3.19 failure the evidence string exists to prevent: a stale `UNBOUND` under-claims in a way nobody re-checks, and it is the sentence a reader uses to decide whether the wiring gap is known.
- **Why the tests did not catch it:** nothing derives the UNBOUND text from a measurement; it is a literal string, and no control compares it against the tree.
- **Status:** **DISCHARGED IN THIS ARC** for the evidence strings (both gates now name the measured state — three paths wired, three unwired, D3.358). The CLASS — an UNBOUND claim that is a literal rather than a derivation — is recorded, because the same restatement exists in three more places.
- **Debt row:** **D3.362**.

### F-B6b — `take` accepts an empty, whitespace-only or `None` `client_order_id` as an identity

- **Invariant:** I2's identity. `client_order_id` is what `_refuse_duplicate`, `_by_order` and `_order_terminal` key on.
- **Site:** `scripts/nixrisk/reservations.py:307` `take` — the margin guard is complete and there is no identity guard beside it.
- **Scenario / Observed:** `''`, `'   '`, `'\n'` and `None` are all accepted (`RSV-00000001`, Σ=6172.5 each), and the **real** `Plane1Wal` encodes and appends every one, including a `client_order_id` containing an embedded newline. `EventRow.fields` is typed `Mapping[str, str]` and receives `None`. The duplicate guards themselves work: reuse after a terminal release is refused naming the path taken, and two different orders colliding on one id are refused naming the live reservation.
- **Status:** **BLOCKS** (a hardening gap, not a §14 violation — deliberately not inflated). **Debt row: D3.363.**

### F-B7 — nothing pairs Plane 1's `reservation_taken` rows against its `reservation_released` rows

- **Invariant:** I2's only leak detector. `reservations.py`'s own module docstring: *"only an EXTERNAL record of which orders reached a terminal outcome catches the leak"*.
- **Site:** the absence. `reservation_taken` appears in `check_plane1_schema.py` (a kind name in a schema list), `plane1_sink.py`, `plane1_seed.py`, `projection.py`, `seam.py` — **no reader pairs the two kinds, and no check counts them.**
- **Scenario (executed):** `scratchpad/arc038b/p8_crash.py` — a real `Plane1Wal`, a child process, and a real `SIGKILL` (`os.kill(getpid(), SIGKILL)`) fired from inside `enqueue`, i.e. after the ledger's stores and Σ are mutated and before the durable append, in both orders.
- **Observed:** child `rc=-9` asserted in all three episodes.
  ```
  before_taken_row     : WAL 0 bytes,   taken=0 released=0 unpaired=0
  before_released_row  : WAL 239 bytes, taken=1 released=0 unpaired=1
  after_release_no_fsync: WAL 478 bytes, taken=1 released=1 unpaired=0  (pending=2, no fsync)
  RESTART (fresh ledger, nothing seeds it): outstanding=0 sigma=0.0  in all three
  ```
  §14's *"Restart = flat, always"* holds in memory — nothing in `coldstart.py`, `recovery.py` or `plane1_seed.py` reconstructs the reservation ledger, so a killed reservation comes back neither once nor twice. The residual is durable: the record of money truth keeps an unpaired `reservation_taken` forever and nothing reconciles it. (The `after_release_no_fsync` episode also proves `Plane1Wal`'s `buffering=0` claim: 478 bytes survived a `SIGKILL` with `pending=2` and no fsync — the crash gap for a SIGKILL is exactly zero.)
- **Status:** **BLOCKS.** The repair is a Plane-1 reconciler — new production code, outside this arc's freeze. It is also the instrument that would have caught F-B1 and D3.358 in production rather than in an audit.
- **Debt row:** **D3.361**.

---

## PROOFS OF RESISTANCE

### R-B1 — I2 held under the §15 C1 double-spend race, 4,000 real-thread iterations
- **Attack:** a fill and a blackout-onset cancel on ONE reservation, concurrently, in the two shapes production actually uses (`resolve` keyed on the client_order_id; `release` keyed on the reservation_id). Real threads, real `threading.Barrier(2)` so both callers enter the critical section together, `sys.setswitchinterval(1e-9)` (reported as `0.0`) to force maximum interleaving, 4,000 iterations, a fresh ledger each time, the full invariant re-asserted after every iteration.
- **Command + output:** `.venv/bin/python scratchpad/arc038b/p4_race.py`
  ```
  iterations driven: 4000   switchinterval=0.0
  outcome classes (sorted type names of the two calls' results):
       3976  ('Reservation', 'Resolution')
         18  ('KeyError', 'Resolution')
          5  ('DoubleRelease', 'Resolution')
          1  ('Resolution', 'UnknownReservation')
  invariant violations: 0
  ```
  Four distinct interleavings were actually reached, not one — the two clean orderings plus the two windows inside `_settle` — and in every one of the 4,000: exactly one RELEASED record, `outstanding()` empty, `total_reserved() == 0.0`, `audit().material is False`.
- **What this does and does NOT prove:** it proves the double-decrement cannot happen, and the reason is structural rather than lucky — `del self._live[live.reservation_id]` is `_settle`'s first mutation and `dict.__delitem__` on a missing key raises, so the second caller cannot reach `self._sigma -= live.margin`. It does **not** prove the ledger is thread-safe: 18 of 4,000 escaped a bare `KeyError` (F-B5), and it does not cover a free-threaded build (this interpreter reports `sys._is_gil_enabled() → True`).

### R-B2 — the partial fill, the sequence of partials, and the over-fill each release exactly once
- **Attack:** `.venv/bin/python scratchpad/arc038b/p6_partial_identity.py` against the real `IocRemainder` + real `ReservationLedger`.
- **Command + output:**
  ```
  3a. 2 of 5: taken margin=6172.5 -> sigma=0.0 cancels=['c-1'] releases=1 refused=0 outstanding=0
      audit: LedgerAudit(aggregate=0.0, scanned=0.0, outstanding=0, taken=1, released=1, refused=0)
  3b. cumulative 2 then 4 then 5:
      cum=2: sigma=0.0 releases=1 refused=0 cancels=1 released_records=1
      cum=4: sigma=0.0 releases=1 refused=1 cancels=2 released_records=1
      cum=5: sigma=0.0 releases=1 refused=2 cancels=2 released_records=1
      final released()=[('RSV-00000001','fill')]   zombie check: outstanding=() sigma=0.0
  3d. over-fill 7 of 5: sigma=0.0 over_fills=1 cancels=[] releases=1 released=1
  ```
- **What this does and does NOT prove:** §4's arithmetic is right and the reservation is released **whole** at the fill instant, not proportionally — which is what §3's *"converts to open-margin"* requires, since the filled portion re-appears as `PositionRow.margin` on the very snapshot the release rides. Three successive partials produce exactly one release, two recorded refusals, and no zero-quantity zombie. It does **not** prove the filled portion is actually counted as open margin on that snapshot — that is D3.181's open question, one module over.

### R-B3 — a late reject after a timeout release is REFUSED, is distinguishable, and does not move Σ
- **Command + output:**
  ```
  timeout release accepted=True  sigma_after_release=0.0
  late reject accepted=False kind=ALREADY_TERMINAL already_via=PENDING_TIMEOUT requested=REJECT
  reason=c-1: reservation RSV-00000001 already released via pending_timeout; refusing a second
         release via reject (§14: exactly one terminal release). Σ is unchanged
  sigma unchanged by the refusal: 0.0 -> 0.0  same=True
  refusals recorded=1  released records=1
  DISTINGUISHABLE: Resolution.accepted=False vs True
  ```
- **What this does and does NOT prove:** the refusal names the path already taken, is recorded in `refusals()`, and is structurally distinguishable from a release (`Resolution.accepted`, and the two are separate fields, not a nullable one). It does **not** prove the refusal is visible in the auditable record: the Plane-1 rows for that drive were `['RESERVATION_TAKEN','RESERVATION_RELEASED']` and nothing else — the refused event has no row, which is **CHECK-DEBT D3.52**, already open. Nor is it reached in production, since `PENDING_TIMEOUT` and `REJECT` have no callers (F-B3).

### R-B4 — the identity and margin guards
- **Command + output:**
  ```
  reuse after terminal: REFUSED — c-1: already reached terminal path TerminalPath.FILL —
                        a client_order_id is minted once and never reused
  id collision:         REFUSED — c-x: already holds live reservation RSV-00000001 — §4 allows
                        one in-flight action per strategy, so a second take is a defect
  per_contract=0.0      -> InvalidReservation (… not a finite figure at or above MIN_MARGIN 0.001)
  per_contract=-1000.0  -> InvalidReservation (margin -5000.0 …)
  per_contract=nan      -> InvalidReservation
  per_contract=inf      -> InvalidReservation
  per_contract=0.0001   -> InvalidReservation   (below MIN_MARGIN)
  per_contract=0.001    -> ACCEPTED margin=0.001 (exactly MIN_MARGIN)
  ```
  And the `DuplicateReservation` from a colliding id reaches `gate.py`'s `except Exception` and becomes a DENY attributed to `reservation_ledger` — fail-closed, verified in the F-B1 drive.
- **What this does and does NOT prove:** §15 C3's guards are complete on the margin side and both duplicate directions are refused with the reason named. It does **not** cover the identity itself (F-B6b) and there is no upper margin guard — `1e300 × 5` is accepted and Σ becomes `5e300` — though §3 Phase B denies long before `take` at those magnitudes, so that half is unreachable and is stated rather than claimed.

### R-B5 — `check_reservation_lifecycle` is a real gate: 4 of 4 plants RED, each naming the site
- **Attack + output** (each plant restored byte-identical, sha256 compared, and green again):
  | plant | verdict | site named |
  |---|---|---|
  | `_settle` skips the release for `BLACKOUT_ONSET` | RED | `reservations.py:resolve[BLACKOUT_ONSET]: … a release via BLACKOUT_ONSET moved Σ by 0.0, not by the reserved 3703.5 — a LEAK` + `RSV-00000001 is still in the TAKEN set` + `Plane 1 carries 0 reservation_released row(s) … expected 1` |
  | `_refuse_duplicate` decrements Σ (an absorbed double release) | RED | `reservations.py:resolve[BLACKOUT_ONSET+duplicate]: Σ moved from 4320.25 to 616.75 on a duplicate terminal event — a DOUBLE RELEASE` + `§11.7 reconcile … drift -3703.5` |
  | `AUDIT_TOLERANCE` widened 1e-9 → 1e-2 | RED | `reservations.py:AUDIT_TOLERANCE: 0.01 is wider than this gate's 1e-09 — a subject that sets its own drift floor can absorb a real double release and still report material=False` |
  | `release()` returns instead of raising `DoubleRelease` | RED | `release(RSV-00000001, TerminalPath.CANCEL) RETURNED after that reservation was already released via BLACKOUT_ONSET. The frozen ReservationLedgerPort declares it 'Raises on unknown id and on double release'` |
- **What this does and does NOT prove:** the gate discriminates leak from double, names the direction and the magnitude, and cannot be widened its way to green. It does **not** see F-B1 (it never plants a raising Plane-1 sink) and it is structurally green over F-B3 (it drives all six paths through the ledger itself, so the wiring gap is outside its scope — which it says in its own evidence, with a reason that is now stale, F-B6).

---

## GATE AUDIT

### check_reservation_lifecycle
- **Claims:** I2 over `scripts/nixrisk/reservations.py`, across §3's spec-parsed terminal-path set. `SUBJECTS = ("scripts/nixrisk/reservations.py",)`.
- **Scope containment proven by:** direct measurement, not inference — `g.load(Path("/home/bbt/nix-wt-arc-038-b"))` printed
  ```
  gate imported reservations from: /home/bbt/nix-wt-arc-038-b/scripts/nixrisk/reservations.py
  gate imported seam from        : /home/bbt/nix-wt-arc-038-b/scripts/nixrisk/seam.py
  SUBJECTS declared              : ('scripts/nixrisk/reservations.py',)
  gate's own MIN_MARGIN read     : 0.001   AUDIT_TOLERANCE: 1e-09
  ```
  plus behavioural containment: four plants in that file each moved the verdict.
- **Plant → verdict:** all four RED with the site named — see R-B5. Baseline `rc=0`; planted `rc=1` (`fail_needs_operator`); the gate's `site` field carried `scripts/nixrisk/reservations.py:<function>[<path>]` in every case.
- **Restore:** byte-identical proven by sha256 — baseline `3419457dda02552b15fc0507f58c21adf348771b12f090cd57ca9f11eb136a47`, and the same digest after each restore; gate green again after each.
- **The gap it is green over:** F-B1 (a refused Plane-1 append was in the shipped tree, and the gate was green) and F-B3 (three paths with no production caller). Its `NON_CORRECTABLE_REASON` and its §7.12 list are both strong; neither asks "what if the sink refuses".

### check_fill_handler
- **Claims:** `SUBJECTS = ("scripts/nixrisk/fills.py", "scripts/nixrisk/join.py")`; docstring claims *"the reservation is released"*.
- **Scope containment proven by:** `fills.py` is a declared subject and the gate constructs a real `ReservationLedger` and a real `IocRemainder` and takes real reservations; two plants in `fills.py` moved the verdict before this arc's change (the off-by-one and the both-halves skip).
- **Plant → verdict, BEFORE this arc:** the pure-leak plant (IOC cancel retained, `resolve` skipped) → **GREEN. A FINDING.** F-B2.
- **Plant → verdict, AFTER ARM TERMINALITY:** four plants RED, each naming the site and the direction — see F-B2's table.
- **Restore:** `fills.py` sha256 `978cb73f9088ad4ecc31061bcd52a08cbec01e2e06586d07bbdedac5cee90484` before and after every episode; gate green again each time.

### check_execution_ledger
- **Claims:** `SUBJECTS = ("scripts/nixrisk/execution.py",)` — the exec-report ledger, not the reservation one.
- **Scope containment:** it does **not** declare `fills.py` and it does not touch the reservation ledger. Both `fills.py` plants left it GREEN — correctly, because the subject is not in its scope. **No finding**; recording it so the green is not read as coverage.
- **The one thing it does carry about reservation terminality** is the stale UNBOUND sentence (F-B6), now corrected.

---

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL

`scripts/tests/test_arc038_b_reservation_terminality.py` — 11 controls, `11 passed in 0.63s`.

| suite/control | plant used | reddened? | site named | restored green? |
|---|---|---|---|---|
| `test_a_REFUSED_PLANE1_APPEND_LEAKS_…_BEFORE_the_repair` (the unprotected half) | none needed — it IS the unprotected half, and it REQUIRES the leak to appear | n/a (it fails if the leak does NOT appear) | `outstanding()==1`, Σ=4938.0, `drift==0.0` asserted with the reason | n/a |
| `test_a_REFUSED_PLANE1_APPEND_TAKES_NOTHING` | the F-B1 repair reverted in the real module | YES | `a take whose §12.10 row was refused left a reservation behind …` / `assert ['c-held','c-refused'] == ['c-held']` | YES |
| `test_a_WITHDRAWN_TAKE_frees_the_CLIENT_ORDER_ID_for_a_retry` | same | YES | `DuplicateReservation: c-1: already holds live reservation RSV-00000001` | YES |
| `test_the_REAL_PLANE1_WAL_under_a_REAL_KERNEL_REFUSAL_takes_nothing` | same | YES | `the real WAL accepted 2 take row(s) and the ledger holds 6 reservation(s)` | YES |
| `test_the_PRODUCTION_RELEASE_PATH_SET_matches_the_RECORDED_baseline` | see the two census can-fail controls below | — | names the moved path set and every site | — |
| `test_the_CENSUS_SEES_a_release_site_APPEAR` | a staged module booking `TerminalPath.REJECT` | n/a — it REQUIRES the census to see it | `sites["REJECT"] == ["rejects.py:3"]` | n/a |
| `test_the_CENSUS_SEES_a_release_site_DISAPPEAR` | `fills.py` with `TerminalPath.FILL` replaced by `None` | n/a — it REQUIRES `FILL` to drop out and `<unresolved>` to appear | both asserted | n/a |
| `test_SIGMA_DRIFT_CROSSES_the_AUDIT_TOLERANCE_…` | the falsifiable direction IS the assertion — it requires the crossing | n/a | reports the op count and compares against the docstring's 1e-13 | n/a |
| `test_the_TOLERANCE_still_CANNOT_HIDE_the_smallest_double_release` | a `MIN_MARGIN` double-decrement introduced directly | n/a — requires `material is True` and `drift == -MIN_MARGIN` | both asserted | n/a |
| `test_a_FILL_RACING_a_BLACKOUT_CANCEL_releases_EXACTLY_ONCE` | 600 real-thread iterations | n/a | every assertion carries the outcome map | n/a |
| `test_the_RACE_CONTROL_would_SEE_a_double_release` | Σ decremented twice for one commitment — the footprint a won race would leave | n/a — requires `material is True`, `drift == -margin`, `total_reserved() == -margin` | asserted | n/a |

Both self-deceptions the contract names were ruled out explicitly:
- **D3.344 (inherited `PYTHONPATH`):** the real-WAL control's child gets an explicit `env=` built by **filtering** `/home/bbt/nix/scripts` out of `PYTHONPATH` and keeping everything else (so the binding census's `sitecustomize` survives), and the child **prints the `__file__` it imported**, which is asserted equal to the worktree path. The same scrub is applied to every subprocess `git` call (`GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` removed, D3.205/D3.22).
- **ARC 035 (controls masking themselves):** F-B1's control runs the UNPROTECTED half first and requires the leak to appear before the protected half requires it gone.
- **Check contract rule 11:** every control asserts a message, a field or the arithmetic. No control anywhere in the suite asserts an exit code alone.

## WHAT I COULD NOT MEASURE, AND WHY

1. **A free-threaded (`--disable-gil`) interpreter.** This venv is `CPython 3.14.4 … [GCC 15.2.0]` with `sys._is_gil_enabled() → True`. The race result (R-B1) rests on `dict.__delitem__` being atomic under the GIL; under a no-GIL build that reasoning would need re-driving. **Cannot-measure**, no such build present.
2. **Real Postgres as the Plane-1 record.** The reservation ledger's Plane-1 boundary is `nixrisk.wal.Plane1Wal` — a local WAL file — and that is the boundary I drove, with real `write(2)`s, real `OSError` EFBIG, real `SIGKILL` and real byte counts read back off disk. `plane1_sink.py`'s shared-pool half (the Postgres side) is reached through `GroupCommitWriter` and is not on the ledger's `enqueue` path, so it is not the boundary this invariant crosses. No Postgres claim is made either way.
3. **Whether a leaked reservation actually starves the account in a running system.** That needs §3 Phase B driven against a climbing Σ over a session, which is the Limiter-loop arc that does not exist. The arithmetic consequence is stated from the formula, not measured end to end.
4. **Whether `client_order_id` can be blank in production.** That depends on `nix_strategy_contract_v1.1.md` §3–4 registration validation, which is the strategy seam and outside this invariant's scope. F-B6b records the ledger's own silence, not the system's.
5. **A GO-timeout end to end.** §15 C6's timeout has no implementation to drive (`plane1_seed.py` and `projection.py` know the `go_timeout` event KIND; no module produces one), which is the same absence F-B3 measures.

## FILES I CHANGED

| path | why | finding |
|---|---|---|
| `scripts/nixrisk/reservations.py` | `_book` made all-or-nothing: Σ saved, mutation, emit inside a `try`, and on any exception the two store writes undone and Σ restored **by assignment**. Plus the docstring stating the measurement and naming the drive. `_settle` untouched (D3.53's ruling). | F-B1 |
| `checks/check_fill_handler.py` | **ARM TERMINALITY** added — its own drive (approve all, then fill one at a time) so the Σ trajectory is non-degenerate; reads `total_reserved()`, `outstanding()`, `released()`, `audit()` and `IocRemainder.releases/refused_releases/over_fills`; new `MIN_SIGMA_STEPS = 3` floor; evidence extended with the Σ figures. Reasoned `too-many-locals` disables in the file's own idiom. | F-B2 |
| `checks/check_reservation_lifecycle.py`, `checks/check_execution_ledger.py` | the stale `UNBOUND … handlers … do not exist yet` evidence replaced with the measured state (three paths wired, three unwired, D3.358). | F-B6 |
| `scripts/tests/test_arc038_b_reservation_terminality.py` | **new** — 11 controls, all four attacks above, each with its can-fail proof. | F-B1, F-B3, F-B4, F-B5 |
| `downloads/arc038_findings_B.md`, `downloads/arc038_debt_B.md` | the deliverables. | — |

Nothing else was touched. `docs/CHECK-DEBT.md`, `sessions/SESSION.md`, `downloads/RESULTS.md`, `checks/gate_coverage_baseline.json`, `CLAUDE.md`, both spec versions and every sibling worktree are unmodified.

## TWO EXISTING INSTRUMENTS CAUGHT *ME*, AND BOTH CORRECTIONS ARE IN

Recorded because an audit that reports only what it found in others is not under
audit itself (§0a).

1. **`check_uncalled_entry_points`' live-baseline ratchet caught ARM TERMINALITY's
   first spelling.** It called `ledger.audit()` where `ledger = drive.reservations`
   is typed `Any`, so the call was credited to EVERY class in the tree carrying a
   public `audit` — and the ratchet reddened with
   `baseline rows that are no longer findings: ['scripts/nixrisk/execution.py::ExecutionLedger.audit', 'scripts/nixrisk/reservations.py::ReservationLedger.audit']`.
   My gate change had silently moved a row out of a DIFFERENT module's measured
   population, which is exactly what `drift_audit.py::_is_material` documents and
   forbids. **Repaired by removing the call**, not by moving the baseline: the arm
   now computes §11.7's reconcile itself, from `total_reserved()` against a
   `math.fsum` over `outstanding()` — the two independent pieces of arithmetic
   §11.7 requires. That is also the stronger form: a gate that asks the subject
   whether it agrees with itself has asked the subject. No shared baseline file
   was touched.
2. **`test_check_reservation_lifecycle.py::test_the_PATH_SET_is_PARSED_FROM_THE_SPEC_and_appears_NOWHERE_in_the_gate`
   caught F-B6's first wording.** It asserts that no `TerminalPath` member name
   appears anywhere in that gate's source, so the expected side cannot become a
   constant the gate chose. My corrected evidence string named the three unwired
   paths and reddened it. **Repaired by stating the COUNT and pointing at D3.358
   for the enumeration**, which is the derive-never-restate answer as well as the
   one the control wanted; the gate's source is now member-name-free again, proven
   mechanically (`member names present in the gate's source: NONE`).

3. **`bandit` and `complexipy` in the hook suite** rejected the first spellings on
   their own terms: `random.Random` under B311 (annotated `# nosec B311` with the
   reason — a reproducible drive, not a secret) and two functions over the
   cognitive-complexity ceiling. `terminality_defects` was split by QUESTION — the
   Σ trajectory, the ledger's release records, §11.7's reconcile plus the
   component's counters — so a single leak or double release must surface in at
   least two of the three, which makes the green more than one arm's opinion. All
   four plants re-verified RED after the split, each restored byte-identical.

## SUITE NUMBERS

- Limiter-relevant selection (contract step 3):
  `.venv/bin/python -m pytest scripts/tests -q -k "risk or limiter or gate or reservation or flatten or picture or plane1 or halt or blackout or survival or fill or execution"`
  → **1208 passed, 1 skipped, 2064 deselected** (the one failure in the first pass
  was F-B6's path-literal wording, above; re-run clean after the repair).
- My own suite: `scripts/tests/test_arc038_b_reservation_terminality.py` → **11 passed**.
- The four gates in scope, all green standalone: `check_reservation_lifecycle` (0),
  `check_fill_handler` (0), `check_execution_ledger` (0), and their can-fail suites
  `test_check_reservation_lifecycle` + `test_check_execution_ledger` +
  `test_check_fill_handler` + `test_reservations` + mine → **97 passed**.
- A frozen file changed, so the FULL suite was run — numbers in the final report.

## COMMITS

See `git log --oneline arc-038-b ^f059ea4`.
