# ARC 052 — RESULTS (TOOLING/PREP; no invariant flip)

**Predecessor DERIVED `9a96eab` · write-back `143af34` · re-measure banked on top.**
**Count STAYS 11/12 (open: I1). Limiter STAYS RED. No board redraw.**

## Verify tuple

| | passed | failed | cannot-measure | skipped | guarded |
|---|---|---|---|---|---|
| baseline, measured at `9a96eab` FIRST | 92 | 5 | 2 | 0 | 1 |
| **predicted before the run** | 94 | 4 | 2 | 0 | 0 |
| **measured at the merged tree** | **94** | **4** | **2** | **0** | **0** |

**PREDICTION HIT.** Registered check count unchanged at **100** — this arc added tests and a ruling,
not gates.

**The baseline did not match the brief** (`92 | 4 | 3 | 0 | 1` was expected). One cannot-measure had
become a FAIL with nothing in the tree changed. Finding out why produced D3.465.

## TASK 1 — the tax was already paid for its own subject; this arc MEASURED it

Seven I1-tail daemon files enumerated and all seven found ALREADY in `.testmondata`'s `file_fp`
(`scope=401 known_in_fp=390 UNCOVERED=11`, none of the eleven a tail file). **No coverage test was
added because none was owed.** Per-file no-op commit, tree reset to `9a96eab` each time:

| file | before (ARC 046, banked) | after (ARC 052, measured) |
|---|---|---|
| `scripts/limiterd.py` | **43m47s**, `full-escalated(SCOPE-BLIND:changed-but-uncovered:limiterd.py)` | **3s**, `mode=incremental MEASURED-PASS` |
| `nixrisk/completions.py` · `fills.py` · `fill_seam.py` · `freshness.py` · `gate.py` | — | **2s each**, `mode=incremental MEASURED-PASS` |
| `nixrisk/flatten.py` | — | **3s**, `mode=incremental MEASURED-PASS` |

**Non-vacuity:** the same probe on an uncovered file returns `SCOPE-BLIND … exit 2` — the probe can
still see the tax. **No file still escalates. The pre-pay did not FAIL for any of the seven.**

Opened while measuring: **D3.466** (eleven files still unfingerprinted; a NEW module inherits this on
its first commit unless `pytest --testmon` is run once before committing it — the cheap workaround,
measured) and **D3.467** (`runtime_gate.py`'s `SELECTOR-BROKEN`/`NOTHING-SELECTED` arms are
unreachable: `selected` counts a test that skips unconditionally, so `selected == 0` is never true).

## TASK 2 — D3.104 RESOLVED. All 8 dispositions named.

Not another re-point. The owner had walked `ARC 030 → … → 052`, the last six consecutive close-outs,
each recording it was *"arc-boundary maintenance, not progress"*. **The finding: this was never
overdue work — it is a debt with no payer.** All eight are `scripts/nixverify/*`, each with a
dedicated test module, and doctrine C.9 forbids the second instrument a gate over them would be.

**Disposition for all eight: PERMANENT under `CHECK-A11`** — no owner, no known-red marker, so no
re-point is possible next arc or ever. Per artifact, and what each now measures:

| artifact | witnesses (resolved every run) | witnessed property |
|---|---|---|
| `nixverify/actuation.py` | `test_actuation.py`, `test_check_standalone_nonvacuity.py` | flag parsing, the measure-only default, CORRECTABLE/`validate_result` mapping |
| `nixverify/contract.py` | `test_contract.py` | `CheckResult`/`Status`/`Mode`, `validate_result`, the `completed_arcs`/`guard_owner_defect` owner algebra |
| `nixverify/engine.py` | `test_engine.py`, `test_cli.py`, `test_status_contract.py` | block ordering, resource disjointness, `ON_FAIL` halting, status precedence |
| `nixverify/gitenv.py` | `test_gitenv_hostile.py`, `test_check_git_env_scrub.py`, `test_harness_git_isolation.py` | the `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` scrub, driven hostile |
| `nixverify/loader.py` | `test_loader.py`, `test_runner_coverage.py` | AST-only reading of `DEPENDS_ON`/`RESOURCES`/`ON_FAIL`, the shadowed-`run` adapter |
| `nixverify/optimize.py` | `test_optimize.py` | cycles, orphans both directions, undeclared deps, non-disjoint blocks ⇒ no plan written |
| `nixverify/registry.py` | `test_registry.py`, `test_check_name_coherence.py` | `registry.json` as master plan; parse, block membership, `--commit` |
| `nixverify/render.py` | `test_render.py`, `test_nix_status.py`, `test_stream_progress.py` | presentation only, and that it never enters the journal |

**Nothing was greened by measuring less.** Before this arc the claim *"pytest measures it"* lived
only in prose nobody read; now `covered_by` is resolved on every run in both directions, with this
gate's own test module refused by name (it names every baseline path, so counting it would make the
arm vacuous for every entry at once). The one-way ratchet is untouched and was re-planted.

**Result: `check_artifact_gate_coverage` GUARDED → PASS**, all eight enumerated in `evidence` on
every run. Nine can-fail plants demonstrated live against the real baseline and restored
(`sha256` identical, control re-passes); ten banked as tests.

## TASK 3 — D3.464 fixed, shown both ways; D3.465 found and fixed beside it

```
(A) MARKER REFUSED while no teardown line names cc's watchdog      -> exit 2, nothing written
(B) completed-arc log WITHOUT the marker  -> [CANNOT-MEASURE] no ARC-completed marker in log
(C) `arc_heartbeat.sh marker`             -> prints AND tees; grep -c 'ARC completed' = 1
(D) completed-arc log WITH the marker     -> [PASS] arc_status_contract arc=999 pulses=2 teardowns=1
```

**D3.465, the baseline anomaly:** `arc_051.log` carried the marker AND the teardown, in the right
order, and the gate read `FAIL teardowns=0`. `CLAUDE.md` tells cc to prove the teardown *while
disclaiming* `[watchdogd]`; the reader's kernel-thread veto is line-scoped and discarded the whole
line — **obeying the contract was the way to fail the gate that checks it**. It also reported
`wd_pid=165`, the kernel thread's pid, as cc's. Repaired on both sides: the reader now requires
POSITIVE identification (strictly stronger — a teardown naming nothing used to pass and now FAILs)
and the emitter puts the disclaimer on its own line. Banked logs not retouched (directive 6).

## TASK 4 — recon delivered

`downloads/arc_c_flatten_recon.md` (654 lines). **`limiterd.py` imports no `gate`, `flatten`,
`freshness` or `session` — the running daemon has no protective-exit path at all.**
`session.py::SessionFlattener` is ARC C's template; `flatten.py::ProtectiveFlatten` is complete and
wire-free; ARC C adds no `OrderRole`/trigger enum member, which is why `check_uncalled_entry_points`
is blind to both gaps. **Correction for the architect: the `go` verb never carries `signal_ts`** — it
enters only via `reserve` — so ARC A's "reject a stale GO" is "reject a stale RESERVE" in this build,
or `COMMAND_SCHEMA` must bump. Est. ARC C: ~4 classes, ~15 methods, 1 module, 1 new gate, 7 extended.

## Freeze

Every invariant subject byte-identical to `9a96eab` by `git hash-object`. Declared additions to the
brief's diff list: `docs/CHECK-CONTRACT-AMENDMENTS.md`, `CLAUDE.md`, `CLAUDE-CHANGELOG.md` — rule 13
makes them a precondition of `CHECK-A11` binding at all.

## Ledger

**410 open of 479 rows**, re-derived whole off `check_derived_claims` (`derived:ledger_rows=410` =
`stated:series_table_latest_row=410`). +0 net: three opened (D3.465/466/467), three discharged
(D3.104/464/465).

## Left for the operator

`downloads/Pinokio-8.0.40-arm64.dmg` is still untracked and still the sole subject of
`check_untracked_attribution`'s FAIL. It is a third-party macOS installer on a headless Ubuntu box —
not project work, and not something this arc will delete on an operator's behalf. **It needs a
provenance ruling: delete it, or `.gitignore` it with a written reason.**

**Next: I1 ARC A** (reject + timeout + the D3.463 `signal_ts` fix — see the recon's §4 correction).
