# ARC 037 — Close the Scoring Loop — RESULTS

**Canonical path: `/home/bbt/nix` (absolute).**
**Interpreter: `/home/bbt/nix/.venv/bin/python` (CPython 3.14.4).**
**Predecessor: ARC 036 (81/2/2/0/1). This arc: 87/2/2/0/1, exit 1.**

===RUN SUMMARY: Close the Scoring Loop, Estimated run time: ~9h, completes ~85% of the Scoring-loop wiring stage (six built-but-unconnected seams closed and driven end to end; live venue, the production fill feed, and EMA-span calibration remain out of scope)===

## ARC 037 — Close the Scoring Loop (2026-08-18)

**Canonical path: `/home/bbt/nix` (absolute).** A WIRING arc, not a build arc: ARC 036
built every piece of the scoring loop and wired none of it to production. Six seams,
six blind worktrees, and the merged tree found a defect none of them could see.

### Phase 0 — the baseline held on all four measures, and D3.272 was reproduced

Under `/home/bbt/nix/.venv/bin/python` (CPython 3.14.4): `verify.py`
**81 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded, exit 1**; census
**86 / 86 / 86**; CHECK-DEBT **250 open over 299 rows**; pytest **3049 passed, 2
skipped, 2 xfailed** in 34:50. ARC 036's close byte for byte. **No delta, so no
finding.**

**D3.272 was REPRODUCED rather than described.** Three rows deleted (D3.260/261/262)
and the series row resynced exactly as a bad merge does: `derived:ledger_rows=247`,
`stated:series_table_latest_row=247`, **AGREE=True**. The arithmetic gate is
measurably blind to a lost row.

**0.4 froze three seams before six worktrees could invent three shapes**, and one
hazard was measured before it was frozen rather than after. The brief's standing
warning is that a hazard usually lands backwards; the liveness signal did not, because
it was driven first: `zmq` `EVENT_DISCONNECTED` fires **1.2 ms** after an `ipc://`
publisher is SIGKILLed (libzmq 4.3.5 / pyzmq 27.1.0, this node). That is an
observation of the WRITER, not a timeout.

The realized-P&L freeze refused to mint a §12.10 event type: the inventory has no
realized-P&L row, so the figure rides the rows that already book a realization
(`closed` / `protective_exit` / `sentinel_flatten`) in `payload.realized_pnl`, written
by the Limiter as sole writer (§9). The weight function is ordinal in the RANK, never
in the score — §6.6:461 keeps score computation out of the consumer — neutral 1.0 at
the median rank and on every FCFS route, clamped `[0.60, 1.40]`.

### Stage 1 — six parallel sub-agents, the widest fan-out this project has run

**A — the keystone.** `nixrisk/realized.py` computes realized P&L per closed trade net
of §6.5/§7's modelled costs; `flatten.py` books it on the CLOSED / PROTECTIVE_EXIT rows
through the existing sole writer. Green-while-open then closes-red: peak **+146.12**,
close **−103.88**, and the gate requires the CLOSE. Four plants reddened by name.
A found five things stated backwards, and two matter: **`sentinel_flatten` has no
`EventKind` member**, so a third of the frozen seam is unreachable (D3.283); and
`ema.daily_advances` SUMS a pair's realizing rows while `realized_closes` REFUSES a
realizing row with no figure — so writing both rows double-counts and writing one makes
the log unfoldable. Resolved by booking once with a named `realized_status` on the
other, and recorded rather than papered over.

**B — the weight differs from 1.0.** Two GOs identical but for rank: weights
**1.25 / 0.75**, contracts **16 / 10**, default caller unchanged at 13. The clamp
BINDS at n=8 — `raw(1,8)=1.875 -> 1.4`, `raw(8,8)=0.125 -> 0.6`. Seven neutral routes
each driven and each exactly 1.0. B's own best finding is **D3.295**: with dense ranks,
a seven-way tie at n=8 clamps EVERY contender to the ceiling and inflates the field's
total weighted risk 8.0 -> 11.2.

**C — quarantine survives the process that declared it.** `QuarantineLedger`, fsynced
append-only, folded in at breaker construction. The cap was driven to a trip in pid
2412668 and the verdict read back in **pid 2412669** — a genuinely new interpreter.
The §18 refusal now names the book's own `seq` / `restarts_in_window` / `cap` as the
GATE parsed them out of the JSON, so the reason cannot contradict the record. Restore:
pre 3 -> post 2 same process -> **post 2 fresh process**. **D3.250 and D3.251
discharged.** C also fixed a `bandit (production)` red that had stood since ARC 034.

**D — the mirror learns the writer is DEAD, not merely old.** Two readers on ONE socket
watched ONE death: the observing reader took **0 RANKED decisions from the corpse over
3.444 ms**; the blind control took **56,166 over 0.458 s**; ARC 036 measured 144,699
over 0.483 s. Order flow answered 134,187 times after the kill with zero order-path
exceptions. A wedged-but-alive publisher fired the second signal. **D found
`check_scoring_fallback`'s ARM WINDOW FORBADE this repair** — it failed any window under
half `stale_after_s`, reasoning that §6.6's condition is the table's age; §6.6:465 says
*"the Scoring process is DOWN **or** its table is STALE"*, two conditions, and the age
was the proxy.

**E — the Allocator's Scoring-dependent finish.** The weight threads from
`ContentionRanking.weights` through `propose_contended` to one sizing call site, and the
§4 lifecycle screen now reflects quarantine. Eight outage routes, every weight exactly
1.0 and every route sized identically to a pathway with no mirror at all. **D3.264
discharged** by a plant the row said was impossible: one table whose `lookup` and
`arbitrate` name different winners, no seam edit required.

**F — a dropped ledger row now reddens.** `check_ledger_row_preservation` compares
D-id SETS over every commit reachable from HEAD (no baseline file exists, so the edit
under judgement cannot reach the comparison set). **On its first run it found a real
loss: D1.8 and D1.9, deleted outright by ARC 011 instead of being marked discharged,
missing for 26 arcs.** Recovered from `git show da28f4c`. F also collapsed the two
`RankingReader` classes and MEASURED the mis-attribution first: renaming
`process.RankingReader.pump` on the pre-collapse tree made `publisher`'s `pump` appear
as a NEW finding, 229 -> 230. **D3.271 and D3.272 discharged.**

### Stage 2 — the merged tree held a defect no branch could see, for the third arc running

**D bolted the liveness repair to a class F deleted.** D added `observe_liveness` /
`_note_message` / `_observe` to `nixscore.process.RankingReader`; F, in a worktree D
could not see, deleted that class as D3.271's duplicate. Both branches green. On the
naive merge `check_mirror_liveness` raises `AttributeError` before measuring anything —
**D3.244 un-repaired behind an instrument that cannot say so.** Resolved by porting D's
observer onto F's survivor, not by resurrecting the duplicate. Recorded as D3.340.

**The ledger lost nothing.** Every conflict was resolved by UNION and checked id by id:
the union of the six parents is **361 D-ids** and the merged file holds **361**. Three
branch-local series rows (B 260, D 259, F 257) were each right on their own worktree
and struck through here — D3.192's shape landing on a figure for the second arc running.

**2.1 the keystone first.** Four real protective closes for TWO strategies on one
symbol, written by the Limiter through `Plane1Wal -> GroupCommitWriter ->
Plane1PostgresSink` into real Postgres and read back by `SELECT`:
`realized_pnl = [-103.88, +796.12]` and `[-203.88, -53.88]`. Folded from THOSE ROWS:
winner EMA **59.756364**, loser **−176.607273**, and the EMA advanced.

**2.2 the loop closes.** `rank_rows` -> published over a REAL `ipc://` socket -> a real
`RankingReader` mirror -> `AllocatorPathway.propose_contended`. Policy
**performance_weighted**, weights **1.125 / 0.875**, sizes **150 and 116 contracts**.
The better realized history sized larger. **No fixture stands anywhere in that chain:
every number traces to a row Postgres returned.**

**2.3 the loop survives death.** Publisher SIGKILLed, reaped −9: the Allocator fell back
to FCFS **0.378 ms** after the kill against a `stale_after_s` of **500 ms** — liveness,
not age, and a bound roughly 1,300x tighter. **29,642 proposals answered** in the second
that followed, every weight exactly 1.0, sizes flat at 133/133, every contender still
SIZED and not one deny. Relaunched: weighting re-engaged and the same **150/116**
returned off persisted realized history.

**A cross-branch join neither agent could measure alone:** E's gate reports that a FRESH
breaker over the same ledger **DID** see the quarantine. On E's own branch it read False.

### Stage 3 — convergence

`--optimize` derived a plan **identical to the live registry**. Census **92 / 92 / 92**.
The observer swept this arc's six new checks in **three orders x two sweeps x both
documented interpreters on a cold bytecode cache — 72 observations — and found no
undeclared claim**. It also found that `check_score_weighting` produced **zero** claims,
so its declaration is unfalsified rather than confirmed (D3.341); the other five
produced 2103, 74, 62, 48 and 1.

### What did NOT land, said plainly

**Nothing fills a `TradeFactsBook` in production**, so on the live box a realizing row
carries a `realized_status` and not a figure (D3.280) — there is no fill feed at all
(D3.281). **No production writer publishes the ranking topic and no production consumer
holds a reader**, so FCFS is still the live policy on the real box and every production
weight is neutral (D3.263 stands). The §12.11 operator transport does not exist —
`restore` is called directly. D3.252's join between supervision and the score store is
still missing. Live venue untested by design; the EMA span is a default awaiting real
realized data to calibrate (§6.6:443); and **the strategy driving these trades is a test
harness, not the production plug-in.**

### Stage 3.4 — the binding census found a defect in the instrument that measures binding

`check_mirror_liveness` read **EXERCISED-NEVER-RED over sixteen observations, every
one PASS**, for a gate whose suite reddens on 29 arms. The cause was not the gate.
`_run_staged` in two suites inherited the parent's environment, and
`binding_census.py` sets `PYTHONPATH` to the REAL tree so its tracer reaches every
child — so the staged gate imported `nixscore` from `/home/bbt/nix/scripts` instead
of from the staged copy and **every plant in both files was defeated: the gate
measured production code while reporting on a staged tree, and passed.**

Proven by driving ONE staged, planted tree twice and changing nothing but the
environment: **`PYTHONPATH` unset -> RED, plant detected; `PYTHONPATH` set to the
real `scripts/` -> GREEN, plant defeated.** D3.205's class one layer over.

**The first repair was too broad, and the census caught that too.** Replacing
`PYTHONPATH` outright also dropped the census's `sitecustomize` directory — the only
way its tracer reaches a child — so the staged runs stopped being OBSERVED and
`check_scoring_fallback` went BOUND -> EXERCISED-NEVER-RED. Correct plants,
invisible to the instrument. Narrowed to filter the real-tree entries and keep every
other inherited one, then driven with a decoy sitedir on the parent's path: plant
RED, sitedir preserved in the child, real tree absent.

**Three completed census runs, and the number moved with the repair:**

| run | condition | BOUND |
|---|---|---|
| 1 | plants defeated, staged runs traced | 78 |
| 3 | plants correct, staged runs UNTRACED | 77 |
| **4** | **plants correct, staged runs traced** | **79** |

`check_mirror_liveness` and `check_scoring_fallback` are BOUND in run 4 (3 and 4
observed reds). BOUND floor was ARC 036's 74. Of this arc's six new checks, five are
**BOUND**; `check_realized_pnl` reads EXERCISED-NEVER-RED because its plants call the
arm functions directly and never produce a `CheckResult` for the tracer — recorded as
D3.345 rather than left as a number.

**A leaked `/dev/shm` segment cost a whole census run** (D3.347): fourteen
`nix_drill_*` segments survived runs killed while waiting, a later `test_price_ring`
opened one and blocked in `futex_do_wait` forever, and the census died at 83% having
produced nothing. Space was never the constraint — 2.9 MB of 31 GB. Cleaned and
re-driven under the same tracer: 16 passed in 0.05 s.

### Close-out

`verify.py` on trunk under `/home/bbt/nix/.venv/bin/python` (CPython 3.14.4):
**87 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded, exit 1**
(ARC 036 closed at 81/2/2/0/1; +6 new checks, all passing). The two FAILs are the
standing ones — `check_ibgateway_service`, the tap-session failure and the only
code-independent one, and `check_uncalled_entry_points`, its standing state.
**No further FAILURE and no further non-pass whose cause is not named.**

GUARDED: `check_artifact_gate_coverage`, owner **ARC 038** — re-pointed at close-out
because §0g would otherwise ship a marker owned by an arc that can no longer
discharge (D3.342, and the owner chain is now eight arcs long). Full pytest
**3258 passed, 3 skipped, 2 xfailed, zero failures**. Census three ways:
**92 checks on disk / 92 in the registry / 92 executed**; `--optimize` derived a plan
**identical to the live registry**. CHECK-DEBT **250 -> 309**.

### Post-write-back re-measure (ARC 037), banked before the marker

D3.343's prediction, stated before `sessions/SESSION.md` named this arc complete.

`sessions/SESSION.md` now names ARC 037 complete, so the D3.40/D3.144 guard-owner
transition is **live, not hypothetical**: `nixverify.contract.completed_arcs`
returns an empty error and reports `37 in arcs = True`, highest **37**. That is the
mechanism running against this arc's own summary — the condition D3.343 was written
to be falsified by.

**D3.343's prediction, stated before the write-back, HELD in both halves:**

| | predicted | measured after |
|---|---|---|
| `check_artifact_gate_coverage` | GUARDED, unchanged | **guarded (exit 3), 120 tracked / 119 declared / 8 uncovered** |
| `verify.py` | 87 / 2 / 2 / 0 / 1, exit 1 | **87 passed / 2 failed / 2 cannot measure / 0 skipped / 1 guarded, exit 1** |

The guard survived because D3.342 re-pointed its eight exclusions ARC 037 -> ARC 038
*before* the write-back. Had they been left naming ARC 037, this re-measure would
have read GUARDED -> CANNOT_MEASURE and the guarded count would have gone 1 -> 0.
**A re-measure taken after the fact and then described is not a test of anything**,
which is why the row was banked first.
