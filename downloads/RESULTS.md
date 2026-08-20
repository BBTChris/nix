
---

## ARC 045 — ULTRAREVIEW: Limiter, slice 7 — I11 onset cancellation (INTERIOR)

**Tip DERIVED, not taken from the brief.** The brief cited `≈4d04bfd`; `git rev-parse HEAD` gave
`e3bef1a` — 044's post-write-back close-out, one commit past its own I2 discharge. Everything below
is frozen and diffed against `e3bef1a`. Banked at **`70a9a31`**.

### S1 — the defect, reproduced before a line moved

`ProtectiveFlatten.cancel_entries_on_onset` **cancelled exactly what it was handed and asserted
nothing about it.** `PendingEntry` carried `client_order_id / strategy_id / symbol` and **no role**;
both `PendingEntriesPort` declarations are `Sequence[object]` / `Sequence[Any]`; neither has a
production implementation (D3.349). So *"every element is a pending ENTRY"* was a promise living in a
docstring, checkable by nothing — and the tree has **no order-role vocabulary at all**: `ProposedOrder`,
`PendingEntry` and `NeutralOrder` all carry `side` (LONG/SHORT, BUY/SELL) and none carries a role.

Driven against a real `ReservationLedger`, a real executor and `StubBrokerOrder`'s real working book,
with 2 symbols, 2 strategies, an open position and its guards staged (non-vacuity asserted first):

* **SELECTIVE — the safety-critical half.** A HALT onset cancelled `c-stop` and `c-exit` **at the
  venue** and reported both on `OnsetCancellation.cancelled` as entries. A real **2-lot MESU6
  position was left OPEN AND UNPROTECTED inside the HALT** — §3:173 is *"exits untouched"* and §14
  gives the protective path zero delivery dependency.
* **COMPLETE.** `blackout.py:1045`'s filter was `getattr(entry, "symbol", None) == symbol`: an entry
  object carrying no `symbol` compared `None != symbol` and was **silently dropped** — never
  cancelled, never named, still working inside the §6.1 window it was not approved for (§3:174).
* **SCOPE.** The executor had **no notion of scope**. Handed an MNQU6 entry under a MESU6
  `BLACKOUT_ONSET` it cancelled the MNQU6 order without complaint; scope lived only in the caller's
  list comprehension.

### S2 — the fix, and the point is that it is not new knowledge

**`reservations.resolve` ALREADY knew.** It answers `_refuse_unknown` for a coid it never took. The
sweep just asked at `resolve` time — **one line after `cancel_order` had already reached the venue** —
and dropped the answer onto `refusals`, where nothing read it.

`ProtectiveFlatten._classify_for_onset` (new, one call site) asks **first**, and derives admission
from `ReservationLedgerPort.outstanding()`. §3's pipeline is *"approve ⇒ TAKE RESERVATION"* and
§3:174 is *"no order may fill inside a window it was not APPROVED for"*, so the cancellable set **is**
the outstanding set. **No broker verb was added** — `BrokerFlattenPort` withholds `query_order_status`
on purpose so §14's zero-wire claim stays legible, and this derivation needs no wire at all.

* **Selective by construction:** `_CANCELLABLE_ROLES = frozenset({OrderRole.ENTRY})` — one named
  site to audit, plant and read. A declared `EXIT`/`PROTECTIVE` is excluded **without consulting the
  ledger**, because refusing to cancel something that says it is a stop is the safe direction
  whatever the money record says. A declared `ENTRY` is **not** trusted; it is still corroborated.
* **Scope is an argument:** `scope=None` = global (HALT), a symbol = that window (§6.1/§6.2/§6.3 are
  per-symbol off the live calendar), read off `Reservation.symbol` — the record that always carries
  one — which is what closes the silent drop at its root.
* **Unclassifiable fails closed AND loud:** never cancelled, NAMED on `OnsetCancellation.unclassified`,
  and `complete` goes False so §12.10:753's HALT row books `onset_sweep=partial` instead of claiming
  a clean sweep. `protected` and `out_of_scope` are correct exclusions and do not count against it.

### S3 — both directions, both onset types, real processes: 18/18

Every in-scope pending entry cancelled and **none survives**; a blackout on ES **does not** cancel
NQ's entry; **not one** exit or protective order touched; and a protective exit **re-driven after a
live HALT still flattens** (§14 — the onset did not disarm it). **The race:** a venue fill between
onset and cancel-landing is **not orphaned** — the cancel is dispatched on onset (the order leaves
the working book inside `HaltFlag.set`), and the §6.1b session-close flatten picks the resulting
3-lot position up, driven end to end. Non-vacuity asserted before every verdict.

### S4 — the gate, EXTENDED not duplicated

`check_flatten` **ARM 3b**. ARM 3 owns the onset **cause**; 3b owns the **selection**; the split is
stated in both, per doctrine C.9. `check_halt` ARM 4 owns the HALT *transition's* use of the sweep and
was left byte-identical. **ARM 3 was green over all of S1's findings** — it asserted
`broker.flatten_calls == []` and that an open *position* survived, and both stay true while every
exit *order* is cancelled, because cancelling an order is not calling `flatten`. That is §0a's shape,
in the half that unprotects a live position.

Completeness is **by derivation over the subject's own `OrderRole`**, never a transcribed list: a
member with no disposition is CANNOT_MEASURE naming it, never PASS (the D3.440 lesson). **BOUND on the
real CLI:** clean **exit 0**; **PLANT A** (an in-scope entry survives) **exit 1** naming `c-a2`/`c-b1`
and the window they can fill in; **PLANT B** (the predicate cancels an exit) **exit 1** naming `c-stop`
and the position left UNPROTECTED; **PLANT C** (an unclassifiable kind) **exit 2** naming `'iceberg'`.

**A fourth control caught the gate's own defect.** PLANT C's early `return` short-circuited the arm, so
a tree carrying *both* a new role member and a real incompleteness reported CANNOT_MEASURE and the
violation went unnamed — contract rule 4 (Fail > Cannot-measure) inverted. Found by
`test_PLANT_C_and_a_REAL_FAIL_TOGETHER_report_the_FAIL`, not by reasoning, and fixed.

### FREEZE

Diff vs `e3bef1a` is six paths: `flatten.py`, `blackout.py`, `check_flatten.py`,
`test_check_flatten.py`, `CHECK-DEBT.md`, and `gate_coverage_baseline.json` (the arc-boundary
exclusion re-point the brief mandated). **Byte-identical to `e3bef1a`:** `reservations.py`,
`picture.py`, `halt.py`, `fills.py`, `outcomes.py`, `seam.py`, `session.py`, `limiterd.py`,
`check_halt.py`, `check_blackout_windows.py`, `check_reservation_lifecycle.py` — proven by
`git hash-object` against `git rev-parse e3bef1a:<path>`, not asserted.

### Close-out

**(b)** DERIVED reverse-dependency closure by AST import-graph inversion over the four changed `.py`
files: **16 files, 11 of them tests**. Non-vacuity: it contains `flatten.py`, `blackout.py`, the gate
and its can-fail suite, plus `test_arc038_a_gate_wall`, `test_arc044_exactly_one_terminal_release`
and `test_exit_integration`. **RED-before / GREEN-after** on this arc's own defect, both layers:
behaviourally, S1 against `e3bef1a` cancelled the protective stop; instrumentally, the NEW gate
driven against `e3bef1a`'s own `flatten.py` answers **CANNOT_MEASURE — *"the subject declares no
`OrderRole`, so entry-vs-exit is not expressible in order state"*** — never a PASS. **362 passed** over
the closure plus six suites added **by detection** (`test_halt`, `test_check_halt`,
`test_check_blackout_windows`, `test_check_reservation_lifecycle`, `test_check_order_path_bans`,
`test_arc038_b_reservation_terminality`), because `halt.py` calls the changed method and the closure
cannot see it — D3.444. One failure, `test_check_order_path_bans::test_the_control_passes_and_its_
evidence_names_what_it_read`, **proven PRE-EXISTING**: driven in a worktree at `e3bef1a` it fails
identically (37 order-path modules against a pinned 36). No cost-aware exclusion was needed.

**(c)** The gate is BOUND from all three plants, each naming its site: A/B exit 1, C exit 2.

**(d)** CHECK-DEBT reconciled; **series row written, 389 → 392, derived**. **I11's discharge is an
invariant flip, not a debt row.** Opened **D3.443** (admission is derived, ENUMERATION is still the
book's, and no production `pending_entries()` exists), **D3.444** (the import-graph closure is blind
to `halt.py` — a Protocol is not an import edge), **D3.445** (`CLAUDE.md` documents `arc_progress.txt`
as one space-joined line; `arc_heartbeat.sh` parses one key=value per line, so the DOCUMENTED format
renders `stage ?/?` and a confident **false** `STALL WARNING` over a run that is advancing — measured
on two consecutive beats at this arc's own kickoff). **D3.354 neither re-opened nor discharged:** the
raced-in fill still books `HALT_ONSET` where §3:150-152 says a fill converts to open margin; the
release arithmetic was frozen on purpose, and what is added is the proof the position is not orphaned.
The eight CHECK-A8/A9 exclusions re-owned **045 → 046 before this write-back**.

### RESIDUAL — explicitly NOT claimed

The window backstops themselves are their own machinery: I11 proves a raced-in fill **reaches**
§6.1b's session-close flatten, not that §6.1b or §6.3's margin hold/flatten is itself audited.
D3.354 (the onset-cause booking on a filled entry) and D3.443 (book completeness) stand. Standing
named debt untouched: D3.442 (daemon-wiring = I1 capstone), D3.441, D3.428, D3.434, D3.438, D3.439,
D3.430–D3.433, D3.440, D3.359/360/361/363.

### Post-write-back re-measure — the prediction MISSED BY ONE, and the miss was this run's own ordering

Predicted `90 | 3 | 2 | 0 | 1`. **First measurement at `70a9a31`: `89 | 3 | 3 | 0 | 1`, exit 1.**
The extra cannot-measure was **`check_arc_status_contract`** — *"no ARC-completed marker in log: run
did not reach close-out"*. CLAUDE.md orders the teardown + marker into the run's own log **before** the
final verify; this run measured first. Corrected in place, and the gate then passes
(`pulses=11 teardowns=1 wd_pid=165`). **The prediction was right about the tree and wrong about the
instrument reading this run's own log, and it is recorded as missed rather than re-fitted after the
fact.** Three standing FAILs unchanged: `check_ibgateway_service`, `check_monitor_tui`,
`check_uncalled_entry_points`. Extending the existing gate moved no registered-check count: 96, as
predicted.

### BADGE

**Limiter STAYS RED.** clean = `{I2, I5, I6, I7, I8, I10, I11}` = **7/12**, open = **5**:
**I1** (daemon-wiring capstone), **I3**, **I4**, **I9**, **I12**.
