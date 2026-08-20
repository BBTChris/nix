# ARC 042 — ULTRAREVIEW: Limiter, slice 4 — the Plane-1 GO-timeout row (D3.425)

**TIER: INTERIOR. Limiter badge STAYS RED. Invariant count UNCHANGED at 4/12.**
This slice discharged CHECK-DEBT **D3.425**, not an invariant. Clean =
`{I5, I6, I7, I10}` = 4/12, open = 8 — derived from the 038 register as updated by 040 (I5) and
041 (I7). Nothing here moved that set, and a clean slice must not read as an invariant flip.

**Predecessor.** The brief cited ≈`1abcfd0`. The derived tip was **`d6dae6f`** (041-T's final
measurement commit, which lands after the RESULTS HEAD). Everything below is frozen and diffed
against `d6dae6f`.

## The ordering was inverted on purpose

ARC 040 banked D3.425 with the note *"blocked behind I8."* **You cannot enforce a sole writer that
does not write.** So the writer was wired here and **I8 became ARC 043**. limiterd is §9's
*designated* sole writer; making it function is not creating a second one.

## S1 — D3.425 reproduced on a live daemon, before a line changed

A real `limiterd`, a registered strategy, a GO admitted and abandoned:

* the lock was observed **HELD** after the GO (non-vacuity of the drive itself);
* the breaker **fired at 2.049 s** against `T = 2.0 s` and the §4:208 lock came off — ARC 040's
  behaviour re-confirmed, not re-fixed;
* `limiter.runtime.json` carried the firing: 1 row, `released=true`, `resent=false`;
* `SELECT ... FROM nix_plane1.plane1_event_log WHERE event_type='go_timeout' AND strategy_id=…`
  returned **0**;
* the runtime directory contained **no WAL file at all** — the daemon booked *nothing*, of any
  §9 type;
* **non-vacuity of the absence:** a control row inserted in a transaction was seen by the *same*
  SELECT (`IN-TXN count=1`) and gone after `ROLLBACK` (`0`). The query can find the row; there was
  no row to find.

## S2 — the wiring

`scripts/limiterd.py` gained `Plane1Booker`, and nothing else in this tree gained a writer.

* It **CALLS** the existing `nixrisk.wal.Plane1Wal`. The library was **not modified** and is
  cleanly daemon-callable (`Plane1Wal(path)`), so there is **no not-daemon-ready finding**.
* `EventKind.GO_TIMEOUT` landed in `scripts/nixrisk/seam.py` under that enum's own stated rule —
  *a member lands ONLY when the machinery that emits it exists* — and `plane1_sink.py` maps it.
  Its `UNROUTABLE_PLANE1_EVENTS` census went **4 → 3**, the one direction that map documents.
  `projection.py` needed **no change**: it already classified `go_timeout` as POSITION_NEUTRAL.
* **§4:240-241 expressed as code order:** the firing key is recorded **BEFORE** the enqueue is
  attempted. A booking that raises is counted and reported, never retried — a retry is how one
  intended row becomes two.
* The booking runs from the loop's ingress hook (the only hook limiterd owns inside the tick), so
  it books the previous tick's firings — bounded by one tick, provably lossless, and `main` books
  once more after `run()` returns to catch a clean stop's last tick. `nixrisk/loop.py` was **not
  touched**: §4:210-212's breaker is risk-path source.

## S3 — both directions, real `limiterd` + real WAL + real Postgres. 26/26 assertions.

**(a) breaker fires ⇒ exactly one row.**

| assertion | measured |
|---|---|
| WAL created at boot | `plane1.wal` in the runtime dir |
| row reached the WAL **while the process was still running** | 1 row |
| stop record | `firings_seen=1, booked=1, refused=0, wal_enqueued=1, wal_durable=1` |
| durable, not merely written | `wal_durable=1` — an `fsync`, not a page-cache write |
| **idempotence** | **1 row after 256 ticks**, WAL intact |
| §9 `strategy_id` | matches THIS firing |
| §9 `reason` | the breaker's own `§4:210-212 GO-timeout FIRED …` sentence |
| §9 `ts` | inside `[boot_ts, stopped_ts]` of THIS process |
| §9 `trade_id` | **ABSENT** — no open, so no trade was ever minted; the sink writes the schema's `'-'` |
| the row is this firing's | `client_order_id`, `fired_tick`, `elapsed_s` all match the record |
| §4:240-241 | `resent=false` in the row |

**§12.4 durability — proven END TO END, not deferred.** A Postgres-unavailable window left the
group-commit refused, `backlog=1`, state **`sink_degraded`** (buffers and trades on — *not*
`disk_critical`), and the WAL record intact on disk. When the database returned, **the same
buffered row group-committed** (`committed=1`) and read back out of Postgres matching
`event_type` / `strategy_id` / `trade_id='-'` / `occurred_at` / `client_order_id` / `reason`, at
**exactly one row**. The read-back's own non-vacuity: the identical SELECT returns 0 for a strategy
that never ran. *The outage-replay proof is not owed — it was taken.*

**(b) healthy GO ⇒ no row.** A GO resolved by §4:203-206 terminal feedback, watched **5 s past
resolution** (256 ticks): zero firings, `booked=0`, `refused=0`, **zero rows in the WAL**.

## S4 — the gate: the owner was measured, not assumed

The brief predicted a Plane-1 gate. **The measured owner of this property is
`checks/check_go_timeout.py`** — the only gate that drives a real breaker firing. `check_plane1_*`
owns transport, durability and authorship; none drives a firing, and the property *a FIRED
GO-timeout produces exactly one Plane-1 row* cannot be measured without one. A new
`check_plane1_go_timeout` would have to spawn a second `limiterd` and re-drive the breaker this
gate already drives — the duplicate instrument **doctrine C.9 forbids**. So it was **extended**:
**no new gate file, count unmoved.**

* **ARM 3, STATIC, by shape.** A function that calls `.go_timeouts()` must also call `.enqueue(…)`,
  and its class must build the row under the GO-timeout kind. **Not one Nix identifier is spelled**
  (D3.426's lesson) — a test renames `Booker`/`book_new_firings`/`_row_for`/`_wal` and the arm still
  passes.
* **ARM 4, LIVE.** Reads the WAL the drive's own process left, at the path *the process reported*,
  and refuses a WAL outside the drive's own directory as CANNOT_MEASURE.

**Demonstrated FAIL — two real plants in the real tree, driven against a real `limiterd`:**

* **PLANT A** (booking no-op'd — ARC 040's exact state): **exit 1**. The static arm named *both*
  ledger readers (`_dispatch():343`, `book_new_firings():511`) and the live arm reported the gap:
  *"the RUNTIME RECORD has the firing and the EVIDENCE PLANE does not"*, plus the counter lie the
  plant exposed (`booked=1` against `wal_enqueued=0`).
* **PLANT B** (idempotence guard removed): **exit 1**, *"1 firing(s) produced **156**
  `go_timeout` row(s)"*.
* **Plants removed: exit 0.**

**A defect the plants found in the gate itself:** the first PLANT A run named `_dispatch` — the
*status verb*, which reads the ledger only to report a count — as "the fire path". The arm now
names every ledger reader and says outright that a function which only REPORTS the ledger is not a
booking; a regression test pins it.

**Binding made durable.** `check_go_timeout` had **no test at all**. Check contract v2 rule 9 makes
a retrofitted check a new check whose can-fail binding must be re-established, and a binding that
lives only in a transcript is gone next arc. `scripts/tests/test_check_go_timeout_plane1.py` —
**11 tests, all passing** — re-drives both plants against the SHIPPED arms, each paired with its
unplanted control so a matcher that fires on everything fails too.

## FREEZE — asserted against the derived tip `d6dae6f`

```
checks/check_go_timeout.py                    the extended owner (ARMs 3 + 4)
checks/check_plane1_event_coverage.py         the census blind spot, repaired
checks/gate_coverage_baseline.json            exclusion owners ARC 042 -> 043
docs/CHECK-DEBT.md                            D3.425 discharged; D3.434-437 opened
scripts/limiterd.py                           the enqueue on fire (Plane1Booker)
scripts/nixrisk/plane1_sink.py                the GO_TIMEOUT mapping; unroutable 4 -> 3
scripts/nixrisk/seam.py                       EventKind.GO_TIMEOUT
scripts/tests/test_check_go_timeout_plane1.py the can-fail binding (new)
```

**Three paths are WIDER than the brief predicted, and each is explained rather than waved
through:**

1. **`seam.py` + `plane1_sink.py`.** The brief anticipated *"a minimal booking helper if
   `projection.py` owns the event name."* Measured: **`projection.py` does not own it and needed no
   change.** The seam owns the *kind* (`EventKind` had **no `GO_TIMEOUT` member** — the enqueue had
   nothing to enqueue) and `plane1_sink` owns the *mapping*. Both were the minimum required to make
   `Plane1Port.enqueue` accept the row, and both moved in the direction their own docstrings say
   they move.
2. **`check_plane1_event_coverage.py`.** Not a second arm claiming the property — a **repair to a
   gate this arc's change made red for a wrong reason** (see D3.435).
3. **`gate_coverage_baseline.json`.** Arc-boundary maintenance, the same bump ARC 041 made: an
   exclusion owned by a COMPLETED arc reads CANNOT_MEASURE, and ARC 042 completes at this
   write-back. Stated as maintenance, not progress.

**NOTHING** in `picture.py`, the mirror seam (I7), the I8 enforcement seam, `nixrisk/wal.py`,
`nixrisk/loop.py`, `nixrisk/recovery.py`, `nixrisk/projection.py`, or any unrelated path.

## CHECK-DEBT

* **D3.425 — DISCHARGED**, with the ruling written and the "blocked behind I8" note corrected.
* **D3.434** *(the brief's named residual)* — limiterd books **one** §9 type and owes ten more.
  Before this arc it booked none. Not silently widened; sized so a green `go_timeout` cannot read
  as a booked event surface.
* **D3.435** — the producer census could not see §9's sole writer **at all**, and its repair then
  handed three types a free green off `*_drill.py` gate drivers. Both measured on this arc's own
  instrument; the residual is that the drill exclusion matches a **filename suffix**, a spelling
  and not a shape — D3.426's class, one layer out.
* **D3.436** — a firing lost to `SIGKILL` between the breaker and the next booking has no row.
  §9's crash gap; the reconciliation that heals it is not built.
* **D3.437** — **60 orphaned `nixp1t_*` scratch databases** in the live cluster, measured at
  pre-flight, older than this arc. Not swept: a bulk `dropdb` on a live cluster is an operator
  action, not a slice's side effect. D3.423's class on a different resource.

Ledger **382 → 385** (+4, −1), re-derived whole by
`check_derived_claims._p_check_debt_open_count`, never by arithmetic on the previous figure.

## Explicitly NOT claimed

* **I8 (sole-writer enforcement) = ARC 043** — it now has a writer to enforce.
* D3.428 (the `_current`-advanced-on-publish-failure ruling) — awaits the architect, untouched.
* D3.430 / D3.431 / D3.432 / D3.433 — standing named debt, not this slice.

## CLOSE-OUT — INTERIOR tier, with the commit escalation taken

**(b) DERIVED reverse-dependency closure.** AST import-graph inversion over the five changed
source files (never a hand list): closure = **209 files, 104 of them tests**. **15 excluded
COST-AWARE BY DETECTION** — each found by a marker in its own source (`verify.py`, `--optimize`,
`registry.json`, `check_artifact_gate_coverage`), never by name. **89 test files run.**

*Non-vacuity of the closure*, asserted before it was believed — it contains the new gate's own
can-fail test, the sink mapping's exhaustiveness test, the census gate's test, the `go_timeout`
token census, and the loop test. All five present.

*RED-before / GREEN-after*, on the very defect this arc fixed: with PLANT A re-installed the
closure's control test **FAILED** (`test_the_STATIC_arm_PASSES_the_real_shipped_limiterd`); plant
removed, **11/11 green**.

First full closure pass: **1720 passed, 6 failed** — and all six were **this arc's own ratchets
firing correctly**, not breakage:
* `test_plane1_sink::test_the_UNROUTABLE_five_are_absent_from_the_mapping` — the census literal
  pinned 4 and it is now 3. Lowered deliberately (that is what the ratchet is for), and the test
  renamed off the count it kept re-pinning.
* five in `test_check_debt_owning_module` — two new rows carried an owning-module token
  (`environment`) outside the legal vocabulary. Re-pointed to `verify`, matching D3.423's and
  D3.426's precedent for environment and instrument findings.

Both files re-run green (21 + 10). The authoritative GREEN-after is the **commit gate's own full
pass**, a strict superset of the closure — escalated because `scripts/limiterd.py` is on the
uncovered list, which the INTERIOR tier does not defer.

**(c) The gate is BOUND** from two observed real FAILs at exit 1, each naming its site, and the
binding is now durable in an 11-test can-fail suite.

## THE COMMIT GATE — escalated, and it found real work

`scripts/limiterd.py` is on the runtime gate's uncovered list, so the commit escalated to a full
pass. It ran **43 minutes** and **Passed** — but the first attempt was **rejected**, and by the
static hooks rather than the tests:

| hook | what it found | repair |
|---|---|---|
| ruff check / format | 3 auto-fixable + 3 files unformatted | applied |
| pylint | `E0401` (pytest), wrong-import-position, SHOUTY names, protected-access in the new test | header rewritten to the **house convention** the sibling suites use (`import check_go_timeout as GATE`), replacing an `importlib` path-load |
| pylint | `C0302` (gate 1054/1000 lines), `R0914` (`main` 17/15 locals) | disabled **with the reasoning beside the code**, following `check_plane1_sole_writer.py`'s B.7 precedent |
| pylint | `C0325` parens after `not` | extracted `inside_life` |
| complexipy | `_judge_plane1` = **16** against a ceiling of 15 | **split into `_judge_plane1` (9) + `_judge_plane1_fields` (7)** |

**The complexity counter was right and is worth recording as a finding, not a chore:**
`_judge_plane1` was doing two jobs — owning the PRECONDITIONS (is there a firing, is there a WAL, is
it this run's, how many rows) and READING one row field by field. The split is the same argument
`_judge_record`/`_judge_rows` already make in that file. Re-verified after every reformat: pylint
**10.00/10 exit 0**, ruff clean, 32 tests green, and the gate itself still **exit 0** on a fresh
real drive.

**Banked: `e286052`**, 10 files, +1243 −43, all eight hooks Passed.

## POST-WRITE-BACK RE-MEASURE — predicted BEFORE the run

**Prediction: `90 | 3 | 2 | 0 | 1`, exit 1 — UNCHANGED from 041-T's final.** Extending an existing
gate moves no count (rule 8 / Part C.9), and **S4 created no new gate file**, so the brief's
conditional `passed+1` does **not** apply. The three standing fails (`check_ibgateway_service`,
`check_uncalled_entry_points`, `check_monitor_tui`) are predicted unchanged; the wiring adds a call
site, so no new uncalled entry point.

One dependency is named in advance rather than discovered: `check_artifact_gate_coverage`'s eight
exclusions were owned by **ARC 042**, and an exclusion owned by a COMPLETED arc reads
CANNOT_MEASURE. This arc names itself complete at this write-back, so the owners were re-pointed to
**ARC 043** — without which the prediction would be `90 | 3 | 3 | 0 | 0`, guarded → cannot-measure.
Stated as the arc-boundary maintenance it is, not as progress.

*(measured figures recorded below, forward-only, after the merged tree is measured)*
