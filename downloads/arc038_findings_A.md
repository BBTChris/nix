# ARC 038 sub-agent A — THE GATE WALL

Worktree: `/home/bbt/nix-wt-arc-038-a`   Branch: `arc-038-a`
Interpreter: `/home/bbt/nix-wt-arc-038-a/.venv/bin/python` (CPython 3.14.4)
Invariants assigned: **I1** (nothing reaches broker-order without passing the Limiter),
**I10** (two-phase gate: size-independent before size-dependent),
**I11** (blackout/HALT onset cancels pending ENTRY orders; exits untouched).

Every drive quoted below was executed with the interpreter above. The exploratory
drivers lived in `scratch_a/` and were **collapsed into the committed suite**
`scripts/tests/test_arc038_a_gate_wall.py` and then removed (end-of-arc cleanup);
the outputs pasted below are the real ones from those runs, and the named pytest
control beside each finding reproduces the same drive as a standing control.

Baseline before any change: `pytest scripts/tests -k "risk or limiter or gate or
reservation or flatten or picture or plane1 or halt or blackout or survival or fill
or execution"` = **1198 passed, 1 skipped, 2064 deselected** in 304s.
All six candidate gates PASS on the untouched tree (`check_limiter_gate`,
`check_limiter_seam`, `check_order_path_bans`, `check_blackout_windows`,
`check_halt`, `check_flatten`).

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I1 | mechanical whole-tree enumeration of every direct AND indirect reach to a mutating order verb, then a live attempt to move an order without a `GatePass` | **RESISTED (exit half) / CANNOT-MEASURE (entry half)** — no `place_order` call site exists anywhere in `scripts/nixrisk/`, so the entry dispatch the invariant governs is not built; the flatten/cancel half is reachable from exactly 6 Limiter sites and 0 elsewhere | `check_order_path_bans` | **yes** — its own evidence names the 36 files and 2 dirs it AST-scanned and derives the send-path roster (`cancel_order`, `flatten`, `place_order`) from `ORDER_PORT_VERBS`; it opened `gate.py`, `flatten.py`, `halt.py` by name | **n/a for I1** — that gate bans retry/blocking SHAPES in the order path, it does not assert Limiter-gating. No gate in the tree claims I1. See FA-5 |
| I10 | phase-A DENY vs an independent per-rule invocation recorder; reversed manifest; a rule that LIES about `phase` between reads; qty 0 / negative / NaN driven into the size-dependent rules | **VIOLATION x2** (FA-1, FA-4) | `check_limiter_gate` | **yes** — `non_vacuity()` refuses unless ≥4 phase-A and ≥3 phase-B rules actually ran; measured evidence `drove 8 branch/rule(s): 4 phase-A + 3 phase-B` | **yes after the repair** — the new `arm_partition_is_a_partition` reddens naming `scripts/nixrisk/gate.py:GatePass.__init__[partition]`; it was **GREEN over FA-1 before this arc** (`arm_boot_validation` only tries a CONSTANT bad phase) |
| I11 | a real working ENTRY order at the tree's own vendorless broker, driven across a real EOD window edge and across a HALT edge; a cancel that raises mid-sweep; the fill-vs-cancel race in BOTH orderings; the cause matrix; an unwired sweep | **VIOLATION x3** (FA-2, FA-3, FA-6) | `check_blackout_windows`, `check_halt` | **yes** — 28 denied / 26 permitted drives over 22 real calendar windows; `check_halt` drove 13 transitions, 14 Plane-1 rows, 6 falsifiers, one genuine SIGKILL | **yes after the repair** — see GATE AUDIT. `check_blackout_windows` was green over FA-2 and **says so in its own evidence string** ("NOT measured here: … that a venue order is cancelled on onset"); `check_halt` was green over FA-3 because its onset arm drives ONE entry with a broker that never refuses |

## FINDINGS

### FA-1 — the phase partition is NOT a partition: a rule can be DROPPED from both phases (never runs, the pass APPROVES) or DUPLICATED into both (evaluated twice in one pass)

- **Invariant:** I10 (spec §14:970 via §3:120-131 — *"the Limiter evaluates all
  size-independent rules before size-dependent rules in one pass"*). The module's own
  docstring makes the stronger promise this finding falsifies: *"A rule declaring a
  `phase` that is neither member would be silently dropped by a partition and never
  evaluated — a rule that is in the manifest, is never run, and whose absence looks
  exactly like an approval. **That is rejected at boot, loudly**"* (`gate.py:28-32`).
- **Site:** `scripts/nixrisk/gate.py:672-674` —
  `self._validate(halt, rules)` / `self._phase_a = tuple(r for r in rules if r.phase is Phase.SIZE_INDEPENDENT)` /
  `self._phase_b = tuple(r for r in rules if r.phase is Phase.SIZE_DEPENDENT)`.
  `rule.phase` is a **property, read three separate times** (once inside `_validate`'s
  `isinstance(rule.phase, Phase)` check, then once per partition comprehension) and each
  read is trusted independently. Nothing compares the partition's cardinality to the
  manifest's.
- **Scenario (executed):** `.venv/bin/python scratch_a/probe_liar.py` (now
  `test_arc038_a_gate_wall.py::test_a_PHASE_THAT_FLIPS_is_dispatched_ONCE_by_the_SHIPPED_executor`) — the real
  `default_manifest()` plus one extra rule whose `phase` property returns a **valid
  `Phase` member on every read** but a *different* one on successive reads. Two read
  sequences were driven:
  * `A, B, A` → excluded from `_phase_a` (read 2 said B) **and** from `_phase_b` (read 3 said A);
  * `A, A, B` → included in **both**.
- **Observed:**
  ```
  --- seq ['INDEPENDENT', 'DEPENDENT', 'INDEPENDENT'] ---
     dispatch manifest length: 9 (input length 10)
     'liar' present in dispatch manifest? False
     decision: APPROVE rule: manifest_exhausted
     liar.evaluate ran? False
     *** VIOLATION: a DENYING rule in the manifest was DROPPED and the pass APPROVED ***

  --- seq ['INDEPENDENT', 'INDEPENDENT', 'DEPENDENT'] ---
     dispatch manifest length: 11 (input length 10)
  ```
  The dropped rule returns `Decision.DENY` on every call. It never ran; the pass
  APPROVED and took the reservation. In the dual case the same rule is dispatched
  **twice** in one pass — §3's "ONE authoritative pass" evaluated it two times, and
  `GateOutcome.evaluated`, the tuple the whole ordering proof rests on, carries eleven
  names for a ten-rule manifest.
- **Why the tests did not catch it:** `check_limiter_gate.arm_boot_validation` has a
  case for *"a rule declaring a phase that is NOT a Phase member"* — a **constant**
  `"post-size"` string. Every read returns the same bad value, so the boot refusal
  fires. No arm anywhere reads a rule's `phase` more than once, and no arm compares
  `len(GatePass.manifest)` against the number of rules handed in, so an
  **inconsistent-but-always-valid** phase is outside every existing arm's reach.
  `scripts/tests/test_limiter_gate.py` has the same shape.
- **Status:** **DISCHARGED IN THIS ARC.** `GatePass.__init__` now reads each rule's
  `phase` **exactly once**, into a tuple `_validate` returns, and both partitions are
  built from that tuple — so a rule cannot be dropped, cannot be duplicated, and the
  three former reads can no longer disagree. Standing gate: new arm
  `arm_partition_is_a_partition` in `checks/check_limiter_gate.py`, proven able to fail
  (plant = the three-read partition restored; verdict RED naming
  `scripts/nixrisk/gate.py:GatePass.__init__[partition]`).
- **Debt row:** none owed (discharged in-arc). The *residual* — that `RulePort.phase`
  is a property with no stability contract in the frozen seam — is D3.348.

### FA-2 — a BLACKOUT onset RELEASES the reservation and NEVER cancels the working ENTRY order, so the entry FILLS INSIDE THE WINDOW with its margin already un-reserved

- **Invariant:** I11. Spec §15:995 C4, verbatim: *"C4 **Blackout onset cancels pending
  entry orders.** §3, §6.1."* Spec §3:172-174, verbatim: *"**Blackout/HALT onset ⇒
  Limiter cancels all pending ENTRY orders** (exits untouched) — no order may fill
  inside a window it was not approved for."*
- **Site:** `scripts/nixrisk/blackout.py:945-966` — `BlackoutEvaluator._fire_onset`.
  Its whole body is `self._ledger.release(...)` per matching reservation plus
  `self._onset.on_blackout_onset(...)`. There is **no broker port on the evaluator at
  all** and no call to `ProtectiveFlatten.cancel_entries_on_onset` anywhere in the
  tree's production code (`grep -rn cancel_entries_on_onset scripts/ --include=*.py`
  minus tests: the only production caller is `halt.py:1033`). The HALT half of the same
  one-sentence rule is fully wired (`HaltFlag._sweep_pending_entries`); the blackout
  half is not.
- **Scenario (executed):** `.venv/bin/python scratch_a/drive_i11.py` (now
  `test_arc038_a_gate_wall.py::test_a_BLACKOUT_ONSET_CANCELS_the_working_ENTRY_at_the_venue`) — a real
  `GatePass` + real `ReservationLedger` approve one entry and take its reservation; the
  order is placed at the tree's own vendorless `broker_seam.StubBrokerOrder` (real
  working-order book, real `cancel_order`, real `simulate_fill`); the real
  `SessionWindowSource` generates a real EOD window off the vendored calendar; the real
  `BlackoutEvaluator` is stepped from `window.start - 1s` to `window.start`. Both halves
  ran — the same instant was then reached through a HALT onset as the protected control.
- **Observed:**
  ```
  gate: APPROVE  reservation_id=RSV-00000001
  reserved before onset: 2000.0
  broker working orders : ['c-entry-blackout']
  window under drive    : eod 2026-08-19T20:40:00+00:00 -> 2026-08-19T22:00:00+00:00
  1s BEFORE the window  : blocked=False
  AT the onset instant  : blocked=True
  onsets fired          : 1
  reservations RELEASED : ['RSV-00000001']
  reserved AFTER onset  : 0.0
  broker working orders : ['c-entry-blackout']   <-- still LIVE
  cancels seen by broker: []
  *** FILLED INSIDE THE WINDOW: positions=[('ES', 2)]
  ...
  HALF 2 (PROTECTED, through HALT):
  HaltFlag.set -> action=set booked=True swept=True
  broker working orders : []   <-- CANCELLED
  cannot fill: KeyError('c-entry-halt') — the order is gone from the venue book
  ```
  The blackout onset left the entry live at the venue, it filled inside the window, and
  `Σ reservations` had already gone to `0.0` — so between the release and the fill the
  published `committed` under-counts by the full reservation, which is exactly the
  double-spend §15:987 C1 closed: the freed headroom is available to size another
  symbol while the released order is still going to fill.
- **Why the tests did not catch it:** `scripts/tests/test_blackout.py:612`
  (`test_onset_releases_the_symbols_reservations_once_via_blackout_onset`) carries the
  docstring *"§3: onset cancels PENDING ENTRY orders; the path is the seam's own"* and
  asserts only the ledger release — its rig has **no broker**, so the word *cancels* in
  its own docstring is unmeasurable by construction. `check_blackout_windows` is
  honest rather than wrong: its module docstring and its per-run evidence string both
  say *"NOT measured here: … that a venue order is cancelled on onset (execution is not
  wired)"*. The gap was **declared and unowned** — no `CHECK-DEBT` row exists for it
  (searched: no row in `docs/CHECK-DEBT.md` names blackout-onset venue cancellation),
  so nothing was ever going to discharge it.
- **Status:** **DISCHARGED IN THIS ARC.** `BlackoutEvaluator` gains the same
  both-or-neither onset pair `HaltFlag` already has (`sweep` + `pending`, keyword-only,
  defaulting to `None`, XOR-validated at construction), and `_fire_onset` routes through
  `cancel_entries_on_onset(TerminalPath.BLACKOUT_ONSET, …)` when wired — one path, the
  executor that already books the cancel row and releases under the named cause. When
  unwired the previous ledger-only behaviour is unchanged, so no existing caller moves.
  Control: `scripts/tests/test_arc038_a_gate_wall.py`, both halves, proven able to fail.
- **One DIVERGENCE in the wired path, named because it was measured rather than
  assumed:** the wired sweep releases the reservations of the entries it CANCELS, so a
  reservation with no matching pending entry is no longer released on onset, where the
  old ledger-only path released every reservation for the symbol. Driven both ways:
  ```
  pending book EMPTY (no entry for the reservation):
     cancels=[]  released=()  reserved_after=2000.0
  pending book has the entry:
     cancels=['c-1']  released=('RSV-00000001',)  reserved_after=0.0
  ```
  That is the fail-CLOSED direction and it is the reading §3:150-152 supports: the
  release path is *"blackout-onset **cancellation**"*, so a reservation with nothing to
  cancel has had no cancellation, and keeping its margin committed is correct while the
  order it belongs to may still reach the venue. The unwired path is unchanged, so no
  existing caller moves either way.
- **Debt row:** D3.349 (the wiring exists; **nothing in production constructs a
  `BlackoutEvaluator`, a `HaltFlag` or a `ProtectiveFlatten` at all**, so the sweep is a
  correct mechanism in an object graph nothing roots).

### FA-3 — ONE failing `cancel_order` ABORTS the whole onset sweep: later entries stay live at the venue and FILL inside the HALT, their reservations leak, and NO `halt_set` Plane-1 row is booked at all

- **Invariant:** I11 (§3:172-174 *"cancels **all** pending ENTRY orders"*), and it takes
  §12.10:753 (*HALT set/cleared + cause → Plane 1 AND Plane 2*) down with it.
- **Site (two, one cause):**
  * `scripts/nixrisk/flatten.py:614` — `self._broker.cancel_order(entry.client_order_id)`
    inside `for entry in pending:` with **no guard**. The first refusal propagates out of
    the loop, so entries after it are never attempted and their `ledger.resolve` never runs.
  * `scripts/nixrisk/halt.py:795` — `swept = self._sweep_pending_entries()` sits
    **before** `self._book(EventKind.HALT_SET, …)` and before
    `self._marker.record_booked(...)`. An exception from the sweep therefore skips both.
- **Scenario (executed):** `.venv/bin/python scratch_a/drive_i11b.py` (now
  `test_arc038_a_gate_wall.py::test_a_REFUSED_CANCEL_does_not_ABORT_the_onset_sweep`
  and `::test_a_PARTIAL_sweep_still_books_the_HALT_SET_row`) — three real
  working entry orders at `StubBrokerOrder`, three real reservations, the real
  `ProtectiveFlatten` wired into a real `HaltFlag`; `cancel_order("c-2")` raises
  `BrokerNotConnected`, which is exactly what the shipped adapters raise
  (`broker_seam.py:1952` / `broker_order_ibkr.py:1099` `_require_session`) when the
  session is down — and a session that is down is a *leading cause* of the very HALT
  being declared (`HaltCause.STALE_DATA`). The (b1) baseline half ran first with a
  cooperative broker and showed the good outcome, so the control discriminates.
- **Observed:**
  ```
  (b1) BASELINE: all three cancels succeed
    set -> booked=True swept=True
    working after sweep : []          reserved after sweep: 0.0
    HALT_SET rows booked: ['halt_set']   CANCEL rows booked  : 3

  (b2) THE ATTACK: the SECOND cancel raises (a dead broker session)
    working before      : ['c-1', 'c-2', 'c-3']    reserved before: 6000.0
    set() RAISED BrokerNotConnected: cancel_order called with no session (c-2)
    is_set() now        : True   (money IS gated)
    working AFTER       : ['c-2', 'c-3']
    reserved AFTER      : 4000.0
    HALT_SET rows booked: []  <-- §12.10:753 owed a row
    CANCEL rows booked  : 1 of 3
    entries that FILLED inside the HALT window: ['c-2', 'c-3']
    broker positions    : [('ES', 4)]
  ```
  Four contracts of exposure opened inside a declared HALT, and §9's record contains no
  row saying the HALT was ever declared.
  A compounding measurement from the same drive: **a second HALT cause does not
  re-sweep**, so an entry that survived a failed sweep is never swept again —
  `2nd cause: booked=True swept=False working=['c-late']`.
- **Why the tests did not catch it:** `check_halt._onset_defects` (`checks/check_halt.py:887`)
  drives **one** pending entry (`pending = (PendingEntry("COID-1", …),)`) against
  `_Broker`, a double whose `cancel_order` records and never raises, and asserts
  `broker.cancel_calls == ["COID-1"]`. With one entry there is no "later entry", and
  with a cooperative broker there is no refusal. `scripts/tests/test_flatten.py:614`
  and `test_exit_integration.py:464` have the same two properties.
  `check_order_path_bans` reviewed this exact loop and signed a suppression for it
  (`ADVISORY flatten.py:614 … FAN-OUT, NOT RETRY`) — correctly, because it is not a
  retry; that review asked whether the loop re-sends, never whether it *completes*.
- **Status:** **DISCHARGED IN THIS ARC.** (i) `cancel_entries_on_onset` now attempts
  **every** entry: a broker refusal is caught per entry, recorded on the returned
  `OnsetCancellation.failures` (a new field with a default, so no caller moves) and
  booked as its own Plane-1 `CANCEL` row naming the failure, and the sweep continues.
  (ii) `HaltFlag._sweep_pending_entries` reports `ran` / `partial` / `not_wired` instead
  of a bool, so a sweep that could not finish rides the `onset_sweep` field rather than
  vanishing, and the `halt_set` row and the `record_booked` marker are reached in every
  case. Fail-closed is preserved and strengthened: the HALT stands, the record exists,
  the survivors are NAMED. Controls in `scripts/tests/test_arc038_a_gate_wall.py`, both
  halves, proven able to fail.
- **Debt row:** D3.350 (nothing re-attempts a *failed* cancel, and a second HALT cause
  does not re-sweep — a surviving entry stays live until an operator sees the `partial`
  field. Discharge = the pending-entry reaper the Limiter loop does not have yet).

### FA-4 — the gate never validates the PROPOSAL: `qty=0` and `qty=-5` are APPROVED, and a `SIZE_DOWN` to zero contracts is admitted as an approval

- **Invariant:** I10, and §3:127-131 verbatim — the Allocator line is
  *"clamp ≥ 0"* … *"size = min(risk_contracts, margin_contracts, symbol_cap)"* …
  *"**→ size 0 ⇒ deny.**"* §3:117-119 puts the authoritative answer at the Limiter
  (*"the rare race … is caught authoritatively at the Limiter"*), so a degenerate
  proposal reaching the gate must be denied there, not approved there.
- **Site:** `scripts/nixrisk/gate.py:727` — `GatePass.evaluate` reads the HALT flag and
  dispatches straight into the manifest; nothing anywhere validates `order.qty` or
  `order.margin_per_contract`. And `scripts/nixrisk/gate.py:911` — `_verdict_defect`'s
  `if not 0 <= verdict.sized_qty < order.qty:` **admits `sized_qty == 0`**, i.e. a clamp
  to zero contracts, which §5 makes a DENY.
- **Scenario (executed):** `.venv/bin/python scratch_a/probe_i10.py` (now
  `test_arc038_a_gate_wall.py::test_a_NON_POSITIVE_QUANTITY_is_DENIED_by_the_gate_and_NOT_by_the_ledger`) — the real
  `default_manifest()` behind a real `GatePass`, driven with `qty=0` and `qty=-5`
  against a fully permissive picture, first with **no ledger** and then with a real
  `ReservationLedger`.
- **Observed:**
  ```
  === PROBE 1: qty<=0 proposals, NO ledger wired ===
    qty=  0  decision=APPROVE   rule='manifest_exhausted' sized=None
    qty= -5  decision=APPROVE   rule='manifest_exhausted' sized=None

  === PROBE 2: qty<0 WITH a real ReservationLedger ===
    decision=DENY rule='reservation_ledger'
    reason=the §3 reservation could not be taken (InvalidReservation: c-neg: proposed
           margin -5000.0 is not a finite figure at or above MIN_MARGIN 0.001 …)
  ```
  Two distinct wrongs. With no ledger (`GatePass(halt, rules)` — the constructor's own
  default, and the shape `scripts/plane1_hotpath_drill.py:235` uses) a **negative-quantity
  order is APPROVED**, and `proposed_margin = qty × mpc` is then *negative*, so every
  Phase-B rule gets *easier*: the cap sees `committed − 5000 < cap`, the survival floor
  drops, the deployable ceiling passes trivially. With a ledger the order is denied — but
  by the **ledger's `MIN_MARGIN`**, attributed to `reservation_ledger`, which is §3's
  *"deny (rule named, fail-fast)"* naming the wrong thing: the fault is the proposal, and
  an operator reading the record is told the persistence layer refused.
  NaN was also driven and fails closed correctly (`int(nan // mpc)` raises inside
  `_largest_fit`, the broad catch in `_dispatch` converts it to a DENY naming the rule).
- **Why the tests did not catch it:** every existing gate/suite drives a positive
  quantity. `scripts/tests/test_limiter_gate.py:370` is the only `qty=0` in the tree and
  it calls `SurvivalHeadroomRule.evaluate` **directly**, never `GatePass.evaluate`, and
  uses it as a fixture for the projection arithmetic rather than as a degenerate
  proposal. `check_limiter_gate._order()` defaults to `qty=4` and is never called with
  anything ≤ 0.
- **Status:** **DISCHARGED IN THIS ARC.** A pre-gate proposal check runs immediately
  after §11.5's HALT read (so `evaluated[0] is HALT_RULE` still holds on every pass) and
  DENIES a non-positive quantity or a non-finite/negative `margin_per_contract` under
  its own named branch `PROPOSAL_RULE = "proposal_shape"`, quoting §3's `size 0 ⇒ deny`.
  `_verdict_defect` now requires `1 <= sized_qty < order.qty`. No in-tree rule can
  produce a zero clamp (`_size_down_or_deny` already returns DENY at `fits <= 0`), so
  nothing shipped moves. Control in `scripts/tests/test_arc038_a_gate_wall.py`.
- **Debt row:** D3.351 (`GatePass`'s `ledger` argument is still OPTIONAL, so a gate that
  APPROVES and reserves nothing remains constructible — the D3.47 residual, restated
  with a second consumer).

### FA-5 — NO instrument in the tree claims I1, and the entry half of I1 has no subject

- **Invariant:** I1 (§14:966 *"Nothing reaches broker-order without passing the
  Limiter"*).
- **Site:** absence. `grep -rn "Nothing reaches broker-order"` over the whole tree
  returns **only** the frozen spec. `checks/check_order_path_bans.py` is the only gate
  whose scope is "the order path", and the property it owns is a different one, stated in
  its own first line: *"the order path contains no retry machinery and no loop-blocking
  call."*
- **Scenario (executed):** `.venv/bin/python scratch_a/enumerate_order_paths.py` and
  `scratch_a/i1_indirect.py` (both now
  `test_arc038_a_gate_wall.py::test_the_ORDER_PORT_REACH_SET_is_exactly_the_LIMITER_and_the_ADAPTER`) — every `.py` under `scripts/` parsed (274 files, **0
  skipped for SyntaxError**, so the enumeration's completeness is measured and not
  claimed), the mutating-verb roster **derived** from `broker_seam.ORDER_PORT_VERBS`
  minus the read-only verbs (so a verb added to the port joins fail-closed), and every
  call, every `getattr(x, "<verb>")`, and every non-call attribute load of a verb name
  recorded.
- **Observed:** 84 call sites of `place_order` / `cancel_order` / `flatten`. 74 in
  `scripts/tests/`. Of the 10 in production: 4 in `scripts/broker/` (the adapter itself
  and its own conformance driver) and **6 in `scripts/nixrisk/`** —
  `coldstart.py:713`, `fills.py:443`, `flatten.py:499`, `flatten.py:556`,
  `flatten.py:614`, `survival.py:549`. **Zero** anywhere else; zero in
  `scripts/nixsentinel/` (the §14 exception is declared but does not itself call the
  order port). Indirect reaches: **zero** `getattr` reaches; 3 non-call attribute loads,
  all inside `scripts/broker/seam_simulate.py` (bound methods handed to that file's own
  `expect_raises`); 15 verb-name string literals, 14 inside `scripts/broker/` (the
  roster and `_require_session` labels) and one benign step-name enum member at
  `scripts/nixrisk/recovery.py:506`.
  **And no `place_order` call site exists in `scripts/nixrisk/` at all.** The Limiter
  gates and it exits; it has no entry dispatcher. `GateOutcome` carries no order and no
  quantity except `sized_qty`, and nothing in the tree consumes a `GateOutcome` and
  dispatches: the only production consumers are the two Plane-1 drills, and
  `scripts/plane1_hotpath_drill.py:295,351,388,483` **discard the return value
  entirely** — the shape of an unchecked gate verdict, harmless only because those call
  sites place no order.
- **Why the tests did not catch it:** there is nothing to catch. This is a structural
  measurement, not a defect: the invariant's entry half has no subject in this tree.
- **Status:** **BLOCKS — nothing fixed, and nothing should be.** Building an entry
  dispatcher is a feature and the freeze forbids it. What is owed is that the
  enumeration above becomes standing rather than a one-off: the moment a `place_order`
  call site appears outside `scripts/broker/`, something must require it to sit behind a
  `GatePass`. Recorded as D3.352, with the enumeration itself landed as a real control
  (`scripts/tests/test_arc038_a_gate_wall.py::test_the_ORDER_PORT_REACH_SET_is_exactly_the_LIMITER_and_the_ADAPTER`)
  so the roster is asserted now and reddens the day it grows.
- **Debt row:** D3.352.

### FA-6 — an onset sweep that reaches an ALREADY-FILLED entry releases its reservation under the ONSET cause, so `committed` drops by the margin of a REAL position

- **Invariant:** I11 (§3:172-174), and it takes §3:150-152's release taxonomy with it:
  *"taken at approval → released on: **fill (converts to open-margin)**, cancel, reject,
  pending-timeout resolution, blackout-onset cancellation."*
- **Site:** `scripts/nixrisk/flatten.py:614-621` — the sweep calls
  `self._broker.cancel_order(...)` and then `self._ledger.resolve(coid, cause, …)`
  unconditionally, with no reading of whether the order is still working. The sweep's
  only defence is its caller's book: `PendingEntriesPort.pending_entries`' docstring is
  *"Every pending ENTRY order"*, so a filled order is out of contract — but there is no
  production implementation of that book (D3.349), so the precondition is unverifiable.
- **Scenario (executed):** the fill-vs-onset-cancel RACE, driven in BOTH orderings
  against `StubBrokerOrder`'s real working book and real terminal states.
- **Observed:**
  ```
  ORDERING 1: the onset cancel lands FIRST, the fill arrives after
    cancelled=('c-race',) failures=() complete=True
    reserved after: 0.0   working: []
    fill AFTER cancel: refused ('c-race') -> no exposure, reservation released once
    status: OrderStatus(..., terminal=True, state='cancelled', cumulative_qty=0)

  ORDERING 2: the FILL lands first, the onset cancel arrives after
    filled first. working: ['c-race2']  positions: [('ES', 2)]
    cancelled=('c-race2',) failures=() complete=True
    released=['RSV-00000001'] refusals=()
    reserved after: 0.0
    status: OrderStatus(..., terminal=True, state='cancelled', cumulative_qty=2)
    positions STILL held: [('ES', 2)]
  ```
  ORDERING 1 is clean. ORDERING 2 leaves a REAL 2-contract position while
  `Σ reservations` has gone to `0.0` and §9's row says the release cause was
  `HALT_ONSET` — not `FILL`. Two consequences: `committed` momentarily under-counts by
  the position's full margin (the §15:987 C1 shape again, from the other side), and the
  fill handler that would later release under `FILL` and convert to open margin now
  hits the ledger's `DoubleRelease` refusal instead. The reservation still reaches
  EXACTLY ONE terminal release, which is why I1/I11's own arithmetic holds — the defect
  is the CAUSE and the accounting, not a leak.
- **Why the tests did not catch it:** no existing control drives a sweep over an entry
  that already filled. `check_halt._onset_defects`, `check_flatten`'s onset arm,
  `test_flatten.py:614` and `test_exit_integration.py:464` all construct the pending set
  by hand from orders that never filled, which is the book keeping its own contract by
  construction.
- **Status:** **BLOCKS — nothing fixed, and the freeze is the reason.** The two fixes
  available are both outside a minimal, local, reversible change: (a) read the order's
  status before cancelling, which needs `query_order_status` on
  `BrokerFlattenPort` — a port declared narrow ON PURPOSE so the zero-wire claim stays
  legible (`flatten.py:205-215`), and widening it to fix an accounting cause would trade
  a §14 property for a §9 one; (b) make the fill handler win the book race, which is the
  Limiter event loop D3.349 says does not exist. What this arc did instead is assert the
  half that HOLDS as a standing control
  (`test_arc038_a_gate_wall.py::test_the_ONSET_CANCEL_and_a_FILL_are_SAFE_in_BOTH_ORDERINGS`,
  which requires exactly-one release in both orderings) with the mis-booked cause named
  in its docstring, so the residual is measured rather than implied.
- **Debt row:** D3.354.

## PROOFS OF RESISTANCE

### RA1 — I10 held: a Phase-A DENY enters NO Phase-B `evaluate`

- **Attack:** every rule in the real `default_manifest()` wrapped in a recorder that
  appends `(name, phase)` to an **independent** log at the moment its `evaluate` is
  entered — so the claim is not read off `GateOutcome.evaluated`, the field the executor
  itself writes. `data_staleness` (Phase A, 3rd in dispatch order) forced to BLOCKED.
- **Command + output:** `.venv/bin/python scratch_a/probe_i10.py`
  ```
  === PROBE 3: phase-A DENY must stop ALL phase-B evaluate() entries ===
    decision: DENY rule: data_staleness
    independently recorded evaluate() entries: [('blackout_window', 'SIZE_INDEPENDENT'),
      ('tradability', 'SIZE_INDEPENDENT'), ('data_staleness', 'SIZE_INDEPENDENT')]
    PHASE-B ENTRIES AFTER PHASE-A DENY: [] -> HELD
    outcome.evaluated: ('global_halt', 'blackout_window', 'tradability', 'data_staleness')

  === PROBE 4: manifest handed in REVERSE phase order ===
    recorded: ['SIZE_INDEPENDENT', 'SIZE_INDEPENDENT', 'SIZE_INDEPENDENT']
    first B index vs last A index: None 2
  ```
- **What this does and does NOT prove:** it proves the *executed* order is phase-A-then-B
  and that a Phase-A denial is terminal for the whole pass, on a manifest handed over in
  **reverse** phase order, measured on a log the executor does not write. It does **not**
  prove the partition contains every rule handed in — that is exactly FA-1, which this
  arm cannot see because a *dropped* rule also produces zero Phase-B entries.

### RA2 — I10 held: a POISONED PICTURE does not become an approval

- **Attack:** every float field of `FinancialPicture` poisoned in turn (`balance`,
  `committed`, `deployable`, `sum_open_margin` = NaN, then `+inf`, then a torn picture
  whose `committed` disagrees with its own inputs) driven through the real
  `default_manifest` behind a real `GatePass`. Then `margin_per_contract` poisoned on
  the PROPOSAL side.
- **Command + output** (`.venv/bin/python`, shipped modules):
  ```
  balance=NaN                    -> DENY      rule='aggregate_margin_cap'
      reason=rule raised ValueError: cannot convert float NaN to integer — a rule
             that cannot answer has not approved
  committed=NaN                  -> DENY      rule='aggregate_margin_cap'
  deployable=NaN                 -> DENY      rule='deployable_ceiling'
  sum_open=NaN                   -> DENY      rule='aggregate_margin_cap'
  balance=+inf                   -> APPROVE   rule='manifest_exhausted'
  torn: committed != open+res    -> DENY      rule='picture_coherence'
      reason=§3 committed drift -300.000000 exceeds tolerance 0.01: published
             committed=1200.0 but sum_open_margin=1000.0 + sum_reservations=500.0
  mpc=NaN   -> DENY  rule='proposal_shape'
  mpc=-1.0  -> DENY  rule='proposal_shape'
  mpc=+inf  -> DENY  rule='proposal_shape'
  ```
  `balance=+inf` APPROVES — an infinite balance passes `committed + proposed <
  0.70 × inf` trivially. **It cannot be published**, and that was measured rather than
  assumed: `FinancialPictureBook` is the sole writer (§9/§12.7) and refuses it —
  ```
  balance=inf: REFUSED by the publisher: TornPicture: refusing to publish version 2:
    balance is inf — a snapshot carrying NaN/Inf gates money on it; deployable is inf …
  balance=nan: REFUSED by the publisher: TornPicture: refusing to publish version 3: …
  ```
- **What this does and does NOT prove:** it proves no poisoned picture field the sole
  publisher can emit becomes an approval, and that the four NaN cases fail closed at the
  gate as defence in depth even though the publisher would have stopped them. It does
  **NOT** prove the gate is self-sufficient: `+inf` is caught only by the publisher, and
  `RulePort.evaluate` takes whatever picture it is handed. Two named residuals — the
  DENY reason for a NaN names `ValueError`, not *"the picture carried NaN"*, and the
  gate would approve an `+inf` balance from any future second publisher. Not raised as
  a finding: the only writer refuses it, the seam makes a second writer a design
  violation `picture.py` already raises `ConcurrentWriter` for, and inventing a second
  finiteness authority inside `gate.py` would be the duplicate-authority move directive
  3 forbids.

### RA3 — I11 held: the HALT half of §3:173 cancels at the venue, and exits are untouched

- **Attack:** the same instant FA-2 breaks, reached through `HaltFlag.set` with the
  sweep wired; then every `HaltCause` driven in turn.
- **Command + output:** `.venv/bin/python scratch_a/drive_i11.py`,
  `scratch_a/drive_i11b.py`
  ```
  HaltFlag.set -> action=set booked=True swept=True
  broker working orders : []   <-- CANCELLED
  cannot fill: KeyError('c-entry-halt') — the order is gone from the venue book

  (c) THE CAUSE MATRIX — does every HaltCause sweep?
    stale_data         swept=True  working_after=[]
    clock_skew         swept=True  working_after=[]
    crash_loop         swept=True  working_after=[]
    invariant_breach   swept=True  working_after=[]
    aggregate_drift    swept=True  working_after=[]
    operator           swept=True  working_after=[]
  ```
  **All six §12.5:631 causes sweep**, so there is no non-sweeping cause to argue about;
  `NotAnOnsetCause` guards the *`TerminalPath`* the release is booked under, not the
  `HaltCause`, and `check_flatten` already drives its refusal. No `flatten` is issued by
  the sweep (`cancel_entries_on_onset` calls `cancel_order` only) — measured by
  `check_halt._onset_defects`' `broker.flatten_calls` assertion and re-measured here.
- **What this does and does NOT prove:** it proves the wired HALT sweep really removes
  the order from a venue book that can otherwise fill it. It does **not** prove any of
  it happens in production — see D3.349: nothing constructs a `HaltFlag`.

### RA4 — I11: an UNWIRED sweep is representable, and it is VISIBLE

- **Attack:** `HaltFlag(plane1, plane2, floors)` with no `onset`/`pending`, then a HALT
  set with entries live.
- **Command + output:**
  ```
  sweep_wired() = False
  set -> action=set booked=True swept=False
  Plane-1 row fields  : onset_sweep='not_wired'
  ```
  The XOR in `__init__` (`gate.py`'s sibling at `halt.py:729`) makes half-wiring
  impossible, and the no-wiring case is stamped on §9's row rather than silent.
- **What this does and does NOT prove:** it proves the condition is *recorded*. It does
  **not** prove anything notices: `set()` returns `action="set", booked=True`, no
  exception is raised, and no gate requires `onset_sweep == "ran"` of a production
  construction — because there is no production construction (D3.349). A HALT declared
  with entries live is therefore representable, reported as a success to its caller, and
  discoverable only by reading the Plane-1 field.

## GATE AUDIT

### check_limiter_gate
- **Claims:** I10 — §3's two-phase ordering, HALT-first, fail-fast, hot-path shape, boot
  validation. `SUBJECTS = ("scripts/nixrisk/gate.py",)`.
- **Scope containment proven by:** its own `non_vacuity()` floor, measured on this
  worktree: `drove 8 branch/rule(s): 4 phase-A + 3 phase-B, decision approve`, with
  `MIN_PHASE_A_DRIVEN`/`MIN_PHASE_B_DRIVEN` refusing a CANNOT_MEASURE-worthy pass. It
  loads the subject dynamically out of `ctx.nix_home` and drives real rule objects.
- **Plant (FA-1's own defect, restored into a STAGED copy of `scripts/nixrisk/`):**
  `__init__` put back to `self._validate(halt, rules)` + the two re-reading
  comprehensions. The child was proven to have imported the STAGED module before any
  verdict was believed (D3.344):
  ```
  child imported gate.py from: <staged>/scripts/nixrisk/gate.py
  STATUS: fail_needs_operator
  SITE  : scripts/nixrisk/gate.py:GatePass.__init__[partition]  (x5)
  DETAIL: [dropped-from-both] 8 rule(s) were handed to GatePass and 7 were partitioned
          into the dispatch manifest ['a_one','a_two','a_three','a_four','b_one',
          'b_two','b_three'] after 3 read(s) of `phase`. ...
  DETAIL: [dropped-from-both] the dispatch manifest is not the manifest handed in:
          DROPPED=['phase_flipper'] DUPLICATED=[]
  DETAIL: [dropped-from-both] 'phase_flipper' was in the manifest and does not appear
          in GateOutcome.evaluated=['global_halt','a_one',...,'b_three']
  DETAIL: [duplicated-into-both] 8 rule(s) were handed to GatePass and 9 were
          partitioned into the dispatch manifest [...,'phase_flipper',...,
          'phase_flipper'] after 3 read(s) of `phase`.
  DETAIL: [duplicated-into-both] ... DROPPED=[] DUPLICATED=['phase_flipper',
          'phase_flipper']
  ```
- **AND THE FINDING THE CONTRACT PREDICTED, MEASURED.** The SAME planted tree, run
  with ARC 038's arm neutralised so that exactly the six pre-existing arms execute:
  ```
  PLANTED TREE, ARC 038's arm removed -> STATUS: pass
  evidence: drove 8 branch/rule(s): 4 phase-A + 3 phase-B, decision approve; manifest
            handed in scrambled phase order and execution order read from the rules'
            OWN invocation log; hot...
  ```
  **`check_limiter_gate` was GREEN over FA-1**, with its full evidence string intact.
  `arm_boot_validation` tries a CONSTANT non-`Phase` value, which every read agrees on;
  `arm_ordering`, `arm_fail_fast`, `arm_halt_first` and `arm_records_agree` all read
  the rule set they handed over and never its cardinality after partitioning. This is
  the "assume at least one existing Limiter gate is green over a real gap" case, and it
  is the sharpest arm in the gate that was blind to it.
- **Restore:** byte-identical, proven by `sha256` compare against the shipped module
  (`restore byte-identical to the shipped module? True 10e99c2b0c46f60a`); verdict
  `pass` again with the arm present.

### check_blackout_windows
- **Claims:** §6.1–§6.3 windows, the margin arm, §3's onset record.
  `SUBJECTS = ("scripts/nixrisk/blackout.py",)`.
- **Scope containment proven by:** `28 drive(s) DENIED and 26 PERMITTED across symbols
  ['CL','ES'], over 22 windows generated from the vendored calendar (5944 break rows)`.
  Non-vacuous for what it measures.
- **Plant:** none needed to establish the finding — the gate **declares** the gap in its
  own docstring (`checks/check_blackout_windows.py:137`) and in its per-run evidence
  string: *"NOT measured here: … that a venue order is cancelled on onset"*. That is a
  gate green over a real gap **with the gap written on its face**, and the defect is
  that no ledger row and no arc ever owned it.
- **Restore / repair chosen:** the property is now measured by a pytest control rather
  than by extending this gate, and the reason is doctrine C.9: proving *the venue order
  is cancelled* requires a broker double, a reservation ledger and the flatten executor
  in one rig, which is `check_flatten`'s and `check_halt`'s composition, not this gate's
  read-only window scope. Extending it would have grown a window gate into an execution
  gate. The residual — that `verify.py` on a box that never runs pytest cannot see it —
  is D3.353 and is the D3.10/D3.190 asymmetry, named rather than hidden.

### check_halt
- **Claims:** §12.5's six setters, §12.10's plane routing, HALT-gates-ENTRY-never-EXIT,
  the §3:173 onset sweep, marker replay across a genuine SIGKILL.
  `SUBJECTS = ("scripts/nixrisk/halt.py",)`.
- **Scope containment proven by:** `13 transitions, 14 Plane-1 rows, 6 falsifiers
  caught, 1 genuine SIGKILL, 7 arms` — and its onset arm asserts a real
  `broker.cancel_calls`, so it is not vacuous for the happy path.
- **Plant (FA-3):** make `StubBrokerOrder.cancel_order` raise for the *second* of three
  pending entries → **`check_halt` stays GREEN**, because `_onset_defects` is handed
  exactly one entry (`checks/check_halt.py:995`) and a `_Broker` double that cannot
  refuse. Verified by inspection of the arm and by the drive above producing the
  violation while the gate passes.
- **Restore / repair chosen:** the multi-entry + refusing-broker case is landed as a
  pytest control rather than as a `check_halt` arm, for the same C.9 reason — and
  because the repair spans `flatten.py` and `halt.py` together, which is the composition
  `test_exit_integration.py` already owns. D3.353 covers the runner-visibility residual.

### check_order_path_bans
- **Claims:** no retry machinery and no loop-blocking call in the order path. NOT I1.
- **Scope containment proven by:** its evidence names all 36 files and both derived
  dirs, and the send-path roster it derived (`['cancel_order','flatten','place_order']`)
  is the same set my enumeration derived independently from `ORDER_PORT_VERBS` — two
  derivations, one answer.
- **Plant:** not planted. It is not the gate for I1 and re-planting a retry into it would
  re-measure D2.14, which `scripts/tests/test_check_order_path_bans_drive.py` already
  owns (and D3.189 records the hazard of mutating a production module to do it). Stated
  rather than skipped silently.

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL

| suite/control | plant used | reddened? | site named | restored green? |
|---|---|---|---|---|
| `test_arc038_a_gate_wall.py::test_the_PARTITION_dispatches_EVERY_rule_EXACTLY_ONCE` | in-test: a `phase` property returning `A,B,A` across reads, against a re-created three-read `GatePass` subclass | yes | `gate.py:GatePass.__init__[partition]` | yes |
| `…::test_a_NON_POSITIVE_QUANTITY_is_DENIED_by_the_gate_and_NOT_by_the_ledger` | in-test: the pre-gate branch bypassed by driving the manifest directly | yes | `gate.py:GatePass.evaluate[proposal]` | yes |
| `…::test_a_BLACKOUT_ONSET_CANCELS_the_working_ENTRY_at_the_venue` | both halves: the UNWIRED evaluator (old behaviour) must show the fill inside the window; the WIRED one must show it gone | yes | `blackout.py:BlackoutEvaluator._fire_onset` | yes |
| `…::test_a_REFUSED_CANCEL_does_not_ABORT_the_onset_sweep` | both halves: a broker refusing entry 2 of 3, against the pre-repair loop and the repaired one | yes | `flatten.py:cancel_entries_on_onset[failure]` | yes |
| `…::test_a_PARTIAL_sweep_still_books_the_HALT_SET_row` | both halves | yes | `halt.py:HaltFlag.set[book]` | yes |
| `…::test_the_ONSET_CANCEL_and_a_FILL_are_SAFE_in_BOTH_ORDERINGS` | both orderings driven; ordering 2 must show the position REAL and the release booked under the onset cause (FA-6's residual, named not hidden) | yes | `flatten.py:cancel_entries_on_onset[race]` | yes |
| `…::test_the_ORDER_PORT_REACH_SET_is_exactly_the_LIMITER_and_the_ADAPTER` | in-test: a synthetic module string containing `broker.place_order(...)` outside both dirs | yes | the synthetic path | yes |
| `checks/check_limiter_gate.py::arm_partition_is_a_partition` | the three-read partition restored in `gate.py` | yes | `scripts/nixrisk/gate.py:GatePass.__init__[partition]` | yes |

## WHAT I COULD NOT MEASURE, AND WHY

1. **I1's entry half.** There is no `place_order` call site in `scripts/nixrisk/` and no
   consumer of a `GateOutcome` that dispatches, so "an order reaching broker-order
   without a `GatePass`" has no subject to attack. Cannot-measure, stated as such
   (FA-5 / D3.352), not a Pass.
2. **Anything in a running process.** No daemon constructs a `GatePass`, a `HaltFlag`, a
   `BlackoutEvaluator` or a `ProtectiveFlatten` (`grep -rn` over `scripts/` minus tests:
   the only `GatePass(` sites are the two Plane-1 drills). Every measurement here is of a
   library composed by me. The wiring debt is D3.349.
3. **A real venue.** `StubBrokerOrder` is the tree's own vendorless conformance subject,
   not IBKR. It gave me a real working-order book, a real cancel and a real fill race,
   which is what the I11 attacks need; it cannot tell me what a real venue does with a
   cancel that arrives in the same millisecond as a fill. The IBKR adapter path needs a
   live gateway this box does not have — Cannot-measure, and `docs/CHECK-DEBT.md`
   already carries the Tier-3 rows for it.
4. **Real Postgres / Plane 1 on disk.** My drives used in-memory `Plane1Port` doubles.
   The invariants I was assigned are about order flow and rule ordering, not §9
   durability; `check_plane1_*` and D3.51 own that boundary. Stated so no green here
   implies it.
5. **A genuinely SIMULTANEOUS fill/cancel, rather than the two orderings.**
   `StubBrokerOrder` is single-threaded, so I drove both ORDERINGS sequentially
   (cancel-then-fill and fill-then-cancel) and reported what each produced — ordering 1
   clean, ordering 2 the FA-6 mis-booked cause. That is the strongest form of the attack
   this boundary supports and it found a real defect, but it is not a true interleaving:
   a simultaneity test needs the threaded IBKR adapter, which is
   `test_broker_tier3.py`'s subject and was already driven there
   (`test_t2_flatten_against_an_arriving_fill`, `test_t3_cancel_after_fill_reaches_the_wire`).
   Cannot-measure for the interleaving; MEASURED for both orderings.

## FILES I CHANGED  (path — why — which finding)

| path | why | finding |
|---|---|---|
| `scripts/nixrisk/gate.py` | `_validate` now RETURNS each rule's phase, read exactly ONCE, and `__init__` partitions from that tuple instead of re-reading `rule.phase` twice more | FA-1 |
| `scripts/nixrisk/gate.py` | new pre-gate branch `PROPOSAL_RULE` + `_proposal_defect`, read after §11.5's HALT read, denying a non-positive `qty` or a non-finite/negative `margin_per_contract`; `_verdict_defect`'s SIZE_DOWN floor moved from `0 <=` to `1 <=` | FA-4 |
| `scripts/nixrisk/flatten.py` | `cancel_entries_on_onset` attempts EVERY entry: a broker refusal is caught per entry, recorded on the new `OnsetCancellation.failures` (defaulted field) and booked as its own Plane-1 `CANCEL` row, and the sweep continues; new `OnsetCancellation.complete` property | FA-3(i) |
| `scripts/nixrisk/halt.py` | `_sweep_pending_entries` returns one of `SWEEP_RAN` / `SWEEP_PARTIAL` / `SWEEP_NOT_WIRED` instead of a bool and no longer lets an exception escape `set()`, so §12.10:753's `halt_set` row and the marker's `booked` record are reached in every case; `HaltTransition.sweep` added beside `swept`; `SWEEP_SKIPPED` replaces the bool that used to mislabel a second-cause transition as `not_wired` | FA-3(ii) |
| `scripts/nixrisk/blackout.py` | `BlackoutEvaluator` gains the both-or-neither `sweep` / `pending` pair (keyword-only, defaulted, XOR-validated at construction) and `_fire_onset` routes through `cancel_entries_on_onset(BLACKOUT_ONSET, …)` when wired; new `OnsetSweepPort` / `PendingEntriesPort` declarations; unwired behaviour byte-for-byte unchanged | FA-2 |
| `checks/check_limiter_gate.py` | new `arm_partition_is_a_partition` + `PARTITION_SITE` + `_PhaseFlipRule`, registered in `_measure`'s arm tuple: every rule handed to `GatePass` must be dispatched exactly once, both flip directions driven | FA-1 (standing gate) |
| `scripts/tests/test_check_limiter_gate.py` | PLANT 1's source fragment RE-POINTED to the new partition text. Meaning unchanged (the executor runs the manifest in source order); the D3.189 hazard of a plant keyed to a source literal, handled by re-pointing rather than by loosening the match | FA-1 |
| `scripts/tests/test_arc038_a_gate_wall.py` | NEW — 14 controls, every behavioural one both-halves, all six findings under control | FA-1..FA-5 |
| `downloads/arc038_findings_A.md`, `downloads/arc038_debt_A.md` | the deliverables | — |

Files NOT touched, deliberately: `docs/nics_risk_subsystem_spec_v1.3.md` and `_v1.4.md`,
`scripts/nixrisk/seam.py` (frozen — D3.348 is the seam-side residual it forced),
`docs/CHECK-DEBT.md`, `sessions/SESSION.md`, `downloads/RESULTS.md`,
`checks/gate_coverage_baseline.json`, `CLAUDE.md`, `checks/registry.json` (no new
check was added, so nothing to register).

## SUITE NUMBERS

Interpreter `/home/bbt/nix-wt-arc-038-a/.venv/bin/python` (CPython 3.14.4), `-p no:randomly`.

| run | result |
|---|---|
| baseline, Limiter selection, BEFORE any change | **1198 passed, 1 skipped, 2064 deselected** (304s) |
| FULL suite on the COMMITTED tree (`a89342a`) — frozen files were touched, so the full suite is owed | **3273 passed, 3 skipped, 2 xfailed** in 2197.40s (0:36:37) |
| FULL suite one commit-attempt earlier, run by the pre-commit runtime gate itself | **3272 passed, 3 skipped, 2 xfailed** in 2224.28s (0:37:04); `RUNTIME-GATE scope: in_scope_files=368 uncovered=0 drift=0 alien_env=0 SELECTED=3277` / `RUNTIME-GATE verdict: MEASURED-PASS`. That attempt did NOT land — two hooks failed and both failures were mine: `complexipy` at `_reach`, and Stage 3's *files were modified by this hook* because I edited the findings file WHILE the hook was running. Recorded rather than quietly retried; the +1 between the two runs is this arc's own race control |
| `scripts/tests/test_arc038_a_gate_wall.py` (new) | **15 passed** |
| the four fixes REVERTED via `git stash push -- scripts/nixrisk/*.py`, same suite | **14 failed, 1 passed** — the one pass is the reach-set control, which is independent of these repairs. This is the can-fail proof for the whole file, and it was run THREE times (after the initial repairs, after the `_executor` refactor, and after the `_classify` split) so a later edit could not have quietly removed a control's teeth |
| gates on the COMMITTED tree, all exit 0 | `check_limiter_gate`, `check_limiter_seam`, `check_order_path_bans`, `check_blackout_windows`, `check_halt`, `check_flatten`, `check_reservation_lifecycle` |

Lint on every changed file, using the PINNED pre-commit environments (not the venv):
`ruff check` **All checks passed**, `ruff format --check` **7 files already formatted**,
`pylint` **10.00/10**, `mypy` **Success: no issues found in 7 source files**,
`bandit -c pyproject.toml` **0 issues at every severity and confidence**,
`complexipy` **exit 0 on every changed file** — and it FAILED first, at `_reach` = 15 and then 16, which is how the classification came out of the walk loop into `_classify`; the hook is the reason the final shape is flat rather than nested.


## COMMITS

| sha | subject |
|---|---|
| `a89342a` | ARC 038 sub-agent A (THE GATE WALL): five Limiter defects reproduced, four discharged, and one existing gate measured GREEN over one of them |
| `<this file's own update>` | ARC 038 A: the post-commit re-measure — the full suite on the committed tree, and the two hook failures that were mine |

One substantive commit rather than one per finding, and the reason is the box:
`pre-commit`'s Stage 3 runs the FULL suite on every commit and took 37 minutes under
six sibling worktrees committing at once, so five commits would have been three
hours of contention for no extra evidence. Every finding is separable by path — the
FILES I CHANGED table above maps each one — and the commit message enumerates all six.

`git status --short` is EMPTY on `a89342a`, and `git ls-tree -r HEAD --name-only`
contains all nine paths this sub-agent touched:
`checks/check_limiter_gate.py`, `downloads/arc038_debt_A.md`,
`downloads/arc038_findings_A.md`, `scripts/nixrisk/blackout.py`,
`scripts/nixrisk/flatten.py`, `scripts/nixrisk/gate.py`, `scripts/nixrisk/halt.py`,
`scripts/tests/test_arc038_a_gate_wall.py`, `scripts/tests/test_check_limiter_gate.py`.
The `scratch_a/` exploratory drivers were removed at the end of the arc; each is
named beside the pytest control that carries its drive forward.
