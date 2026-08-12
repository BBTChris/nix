# ARC 025 RESULTS — Bulk Retrofit, Observed Disjointness, and the Durability Gate

**2026-08-12 · verify.py / checks subsystem · mega arc**
**Branch `arc-025-integration` → merged to `main`. Sub-agents A `ae33de9`, B `2dbb8de`, C `65c2b86`.**

---

## 1. `verify.py` under the optimized plan — every non-PASS named

```
[ok]   check_python_runtime
[GRD]  check_artifact_gate_coverage   19 artifact(s) accepted as uncovered, discharged by ARC 025
[ok]   check_datafeed_bar_seal
[??]   check_ibgateway_config         no API endpoint at 127.0.0.1:4002 — ConnectionRefusedError
[FAIL] check_ibgateway_service        127.0.0.1:4002 (nix-ibgateway.service): API not reachable
[ok]   check_node_identity
[??]   check_observed_resource_claims masked-hazard clause: both Gateway gates UNOBSERVED past ECONNREFUSED
[ok]   check_spec_citations
[ok]   check_verify_logging
[ok]   check_venv
[ok]   check_datafeed_granted_mode
[ok]   check_derived_claims
[ok]   check_hook_suite
[ok]   check_order_path_bans
[ok]   check_python_deps

11 passed | 1 failed | 2 cannot measure | 0 skipped | 1 guarded    exit 1
```

**No further FAILURE beyond the stated baseline.** Every non-PASS has a named cause:

| verdict | check | cause |
|---|---|---|
| FAIL | `check_ibgateway_service` | Gateway down — the stated baseline |
| cannot-measure | `check_ibgateway_config` | Gateway down — the stated baseline |
| cannot-measure | `check_observed_resource_claims` | **its own §17 masked-hazard clause firing** — it cannot observe either Gateway gate past ECONNREFUSED, and a safety property proven while its subject is unavailable is not proven. This is the clause biting, not an inert gate |
| **GUARDED** | **`check_artifact_gate_coverage`** | **`guard_owner` verbatim: `'ARC 025'`** |

**The GUARDED check is named and its `guard_owner` is printed verbatim** — `'ARC 025'`, read off the
`CheckResult`, not off the source. At arc start it read
`"the bulk check retrofit arc (ARC 025+), sized in ARC 024 Stage 6.4"`: a **range**, which passed
ARC 024's non-empty test while satisfying no requirement. It is now constrained to exactly `ARC NNN`
and mechanically validated by `nixverify.contract.guard_owner_defect`, enforced in three consumers
from one function so they cannot drift.

## 2. Full gate battery

| gate | result |
|---|---|
| pytest | **520 passed, 1 skipped, 2 xfailed** |
| pre-commit (all hooks) | **8/8 Passed** |
| claims harness | **13/13 compared, 2/2 demonstrations re-executed** |
| CHECK-DEBT | **68** (`derived:ledger_rows` == `stated:series_table_latest_row`) |
| census | **executed == planned == on disk == 15**, three ways |
| can-fail controls | **68 over a driven subject; 0 assert an exit code alone** |

### C4 — `broker_order_open_debt_rows` corrected series shown beside the old

| anchor | ARC 020 | ARC 021 | ARC 022 | ARC 023 | ARC 024 |
|---|---|---|---|---|---|
| **old rule** (filename mention) | 11 | 13 | 13 | 13 | **15** |
| **corrected** (owning module) | 11 | 13 | 13 | 13 | **13** |

Re-derived at every anchor against the historical tree, not recomputed from today's. Identical
everywhere before ARC 024, removing exactly `{D1.41, D3.20}` there. **ARC 024's movement was 0, not
+2.** D1.41 was selected purely because `socket.connect` contains the word `connect` — **the spy that
took ARC 024's measurement contaminated the metric measuring it.** Third repair of this metric
(D2.19 class). Residual named: D1/D2 rows are still selected on prose anywhere in the row, so a
fourth contamination is possible; the only structural close is an owning-module column in
`CHECK-DEBT.md`.

## 3. Binding status — all 15 checks, owner for every non-BOUND row

| # | check | status | evidence / owner |
|---|---|---|---|
| 1 | `check_python_runtime` | **BOUND** | `MINIMUM → (99,0)`; FAIL naming site + `need >= 99.0`; plus a control-on-the-control proving a *wrong* reason yields the *same* exit 1 |
| 2 | `check_venv` | **BOUND** | ARC 024 binding survives — declaration-only edit, `run()` provably untouched |
| 3 | `check_node_identity` | **BOUND** | planted `deadbeef-…` UUID in tmp; FAIL naming site, both UUIDs, and `cloned VM`. Non-correctable refusal asserted on its **reason text**, and proven to precede the session interlock |
| 4 | `check_verify_logging` | **BOUND** | ARC 024 binding survives — declaration-only edit |
| 5 | `check_python_deps` | **BOUND** | ARC 024 binding survives — declaration-only edit |
| 6 | `check_ibgateway_config` | **UNBOUND** | **owner: the tap session.** Declared and given the actuation surface this arc; re-binding needs a live authenticated Gateway |
| 7 | `check_ibgateway_service` | **UNBOUND** | **owner: the tap session.** Same |
| 8 | `check_order_path_bans` | **BOUND** | ARC 024 binding survives — declaration-only edit |
| 9 | `check_spec_citations` | **BOUND** | phantom `§99.9` planted in a synthetic home symlinked to the REAL docs; FAIL naming site + *"is not a heading in"*; severity boundary bound separately |
| 10 | `check_hook_suite` | **PARTIAL — arms 1/2 BOUND, arms 3/4 UNBOUND** | **owner: D3.14** (unassigned). Planting arms 3/4 means editing `.pre-commit-config.yaml` or perturbing the shared store. Arms 1/2: `core.hooksPath` → empty dir in a scratch `$HOME`, exit 1 naming the resolved path, with a confound-excluding second control |
| 11 | `check_datafeed_granted_mode` | **BOUND** *(evidence not durable — D2.30)* | ARC 021 plant 1; exit 1 naming `granted_mode(GATE-PROBE-A)@re-subscribed-after-1`. Control sha matches the banked ARC 023 figure |
| 12 | `check_datafeed_bar_seal` | **BOUND** *(evidence not durable — D2.30)* | `FeedLag` → `eq=False`; exit 1 naming `broker_seam.py:FeedLag` |
| 13 | `check_artifact_gate_coverage` | **GUARDED live** · ratchet + owner arms **BOUND** · coverage claim **UNBOUND** | **owner (coverage claim): D3.19** — it proves an artifact is NAMED, never MEASURED, and says so in every verdict. Ratchet re-bound from scratch, 18 tests, five plants each naming its site |
| 14 | `check_derived_claims` | **BOUND** *(evidence not durable — D2.30)* | banked series row `66 → 47`; exit 1 naming `derived_claims.json:check_debt_open_items`. **See §5 — B3 reflexivity** |
| 15 | `check_observed_resource_claims` | **BOUND** (new this arc) | planted undeclared socket; exit 1 naming **the check AND the endpoint**; control with the port declared → exit 0. Masked hazard proven on a synthetic *and* on the real Gateway pair |

**Tally: 11 BOUND · 2 UNBOUND · 1 PARTIAL · 1 GUARDED-with-BOUND-ratchet · 0 RETIRED.**

## 4. THE HEADLINE — the observer caught what static validation passed

`--optimize` derived a plan with zero errors, zero cycles and zero orphans. Then the runtime observer
ran against that plan and found **seven false declarations** across its first two runs — three of them
in checks ARC 024 had already retrofitted and signed off:

| check | OBSERVED | had DECLARED |
|---|---|---|
| `check_order_path_bans` | `subprocess:.venv/bin/python3` | `()` — beside the comment *"reads source files only … writes nothing"* |
| `check_verify_logging` | `file-write:checks/.plane2_control_<nonce>` | `journal` only |
| `check_artifact_gate_coverage` | `subprocess:git` | `()` |
| `check_derived_claims` | `subprocess:/usr/bin/python3` | `venv` only |
| `check_hook_suite` | `subprocess:git` | `git-hooks, pre-commit-store, venv` |
| `check_node_identity` | `subprocess:blkid`, `subprocess:findmnt` | `state/node_identity.json` only |

The first matters most: `check_venv` claims `venv` and **rebuilds it under `--correct`**, so a plan
believing `()` could have co-scheduled `check_order_path_bans` with the check deleting its
interpreter.

**The `check_node_identity` pair is the one that justifies the mechanism.** It was **argued, not
overlooked** — Wave A reasoned in writing that `findmnt`/`blkid` are read-only kernel queries
contending with nothing. The argument is about CONTENTION; a declaration states what a check TOUCHES;
this project fails closed. **A human's plausible reasoning was checked against what the process
actually did, and reality won.** That is the entire content of closing D2.27.

## 5. Findings returned to the architect

1. **The brief's Phase 0 premise was VOID.** ARC 024 was already committed and merged (`HEAD`
   `509159d`, all 30 paths in history via PRs #23 and #24). Phase 0.2 was a no-op. Phase 0.3
   reproduced all five figures exactly.
2. **`--optimize` was silently dropping failure policy** — and this is a §0a defect in the brief:
   Stage 2.2's stated criteria (derive, zero cycles, zero orphans, propose, require `--commit`) were
   ALL satisfiable by a plan in which a failed Python runtime no longer halts the run. Fixed with a
   declared `ON_FAIL`; the obvious repair was measured and refused because it is worse than the
   defect.
3. **B3 REFLEXIVITY — the finding stands, and it is worse than assumed.** For **10 of
   `check_derived_claims`'s 13 claims, BOTH sources are probes inside the gate itself**, invoked as
   `{self} --probe`. An external checker would have to re-enter the gate; a defect in a shared helper
   moves both sides together. There is no `test_check_derived_claims.py` and no hook runs it (D2.22).
   **Exactly one source is genuinely independent** (`pytest_collector`, which shells to real pytest),
   and it is the only reason the architect's requirement could be satisfied at all. **The architect is
   right that ARC 024's catch was luck of ordering.** Structural repair — a companion suite, or a
   second externally-implemented source per claim — is owed and unbuilt.
4. **D2.30, this arc's honesty row.** Wave B re-bound four gates with control shas matching either
   side, two matching banked ARC 023 figures exactly — and committed **zero test files**. Four
   bindings exist only as prose; the next retrofit starts its can-fail from zero again.
5. **§0c is ambiguous for declaration-only edits and I made a revocable ruling.** Applied literally it
   unbinds every check whose module-level `ON_FAIL` literal was added. An AST classifier over the
   arc's diff shows 5 checks had their MEASUREMENT PATH modified (all re-bound) and 10 had
   declaration-only edits with `run()` provably untouched. **Ruling: §0c binds on the measurement
   path, not the file's mtime.** Ratify or narrow.
6. **A fifth *ambient state sets gate scope* instance**: `git` honours `GIT_DIR`/`GIT_INDEX_FILE`
   **ahead of `-C`**, and `pre-commit` exports `GIT_INDEX_FILE`. It damaged a sub-agent's own worktree
   index before the cause was found. Repaired in `check_artifact_gate_coverage`; `check_hook_suite`
   still exposed (D3.22).
7. **D3.21 — a run whose EVIDENCE contradicts its own VERDICT.** `check_datafeed_bar_seal._drive_seal`
   returns a fixed note claiming *"value equality holds"* even when the equality defect fired.
   Deliberately not half-fixed: it is inside arm 4, D3.15's discharged subject.
8. **Open item 8 of AMENDMENT 4 DISCHARGED** — the `FORCE_COLOR` fragility. Note the provenance: it
   was already recorded and owed to this arc, not newly discovered here.

## 6. Still open to the operator

1. **`registry.json` vs `manifest.json` — UNRULED.** Nothing renamed in either direction, per
   instruction. The vocabulary (`manifest_version`, `nixverify/manifest.py`, `ManifestError`,
   `load_manifest()`, `--manifest`) is untouched and still disagrees with the filename.
2. **The non-correctable class now has 12 members.** `check_node_identity` implemented as
   non-correctable per the A2 ruling, with the refusal proven on its reason text. Ratify or narrow.
3. **Wave C's binding is the seventh thing owed to the tap session** — an operator task at the
   console, ~40 min.
4. **The §16 write-back check and the §18 control auditor are both owed and unwritten** (D2.29).

---

`===RUN SUMMARY: ARC 025 — Bulk Retrofit, Observed Disjointness, and the Durability Gate, Estimated run time: 3h 10m, completes ~85% of the check-subsystem stage (the orchestration surface is live and self-derived, disjointness is proven against observed behaviour rather than declarations, and 11 of 15 gates are bound — the residue is the tap-session bindings and four non-durable Wave B controls) / ~12% of the whole project===`
