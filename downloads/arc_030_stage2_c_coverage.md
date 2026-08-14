# ARC 030 Stage 2 / sub-agent C — coverage retrofit part 2, filesystem-walk class

Worktree: `/home/bbt/nix-wt-stage2-c`, branch `arc-030-stage2-c`, based on `main @ 6c7e9c9`.

## C1/C2 — per-artifact disposition (the 8-artifact partition)

Partition: `checks/_preamble.py`, `scripts/nixverify/{__init__,actuation,contract,engine,loader,optimize,render}.py`.

| artifact | disposition | evidence |
|---|---|---|
| `checks/_preamble.py` | **RETIRED from exclusions.** New `checks/check_preamble_shim.py` + `scripts/tests/test_check_preamble_shim.py` (13 tests). | AST-scans the shim for its documented two-line contract: `sys.dont_write_bytecode = True` and `sys.path.append(scripts_dir)` (never `insert`, per `loader.py`'s own stdlib-shadow hazard). Data-driven, same house style as `check_synthetic_stop_only`. Drive: `scan_preamble_source` is a pure function over source text, exercised against 4 synthetic variants (correct, missing bytecode guard, missing path append, `insert` instead of `append`) proving it reddens each; non-vacuity proven by scanning the real file (0 defects) and running the full `run()` against the real tree (`PASS`). |
| `scripts/nixverify/__init__.py` | **RETIRED from exclusions.** New `checks/check_nixverify_init.py` + `scripts/tests/test_check_nixverify_init.py` (12 tests). | The hardest of the 8, per the brief. Property: `__all__` is coherent with the `from nixverify.X import name` statements — every exported name is actually bound by an import, every imported name is in `__all__`, and every imported name actually exists as a module-level binding in the sibling it claims to come from (the real failure mode: a name removed from `contract.py` while `__init__.py` still imports it breaks `import nixverify` for every check in the tree, before that check's own `run()` runs at all). **Isolation**: `scan_init_coherence` is a pure function over SOURCE TEXT for `__init__.py` AND text for each sibling — never imports, never executes, never mutates any file, including the live `__init__.py` this very check (and its own test) is running under. Drive: 9 synthetic-source cases (stale export, phantom export, missing `__all__` entry, missing sibling file, empty `__all__`, unparseable source, plus 3 end-to-end `run()` plant/restore cases against a scratch `nix_home`); non-vacuity proven against the real file (0 defects, `run()` → `PASS`). |
| `scripts/nixverify/actuation.py` | Left excluded, justification refined. | Already exercised by 4 pytest modules. A `checks/check_*.py` re-asserting the same behaviour (e.g. the exit-code contract, already parametrized in `test_status_contract.py`) would be the second instrument doctrine C.9 forbids — not new coverage. |
| `scripts/nixverify/contract.py` | Left excluded, justification refined. | 35 test modules already drive `Status`/`CheckResult`/`validate_result`/guard-owner rules, including an exhaustive parametrization of `exit_code_for` over all six `Status` values. Building a check for the same mapping is a duplicate instrument. |
| `scripts/nixverify/engine.py` | Left excluded, justification refined. | Block execution/gating/aggregation already driven by `test_engine.py`, `test_cli.py`, `test_status_contract.py`. |
| `scripts/nixverify/loader.py` | Left excluded, justification refined. | `load_check`'s own contract (a bad module is captured, never raised) is already driven directly against synthetic scratch modules by 11 test modules. |
| `scripts/nixverify/optimize.py` | Left excluded, justification refined. | The cycle/orphan/undeclared-dependency/non-disjoint-parallel refusal rules are already driven by `test_optimize.py` against synthetic scratch check folders. (Also: a check that shells out to `verify.py --optimize` to test the tool the current run is itself using is its own hazard — noted, not built.) |
| `scripts/nixverify/render.py` | Left excluded, justification refined. | Rendering behaviour driven by 3 test modules. One property they do NOT drive — that `render.py` imports no `nixverify.plane2`/syslog symbol, the §1.3 presentation-never-enters-the-journal separation — was confirmed TRUE by direct inspection this arc and recorded in the exclusion rather than turned into a single-property proxy check. |

**Why 6 of 8 stayed excluded, honestly.** `checks/_preamble.py` and `scripts/nixverify/__init__.py` were **NAMED BY NOTHING before this arc** — zero assertions anywhere, per the pre-existing exclusion text itself. The other six already carry substantial pytest coverage (4–35 test modules each). Building a `checks/check_*.py` that re-drives an ALREADY-tested property is not "new coverage" by this project's own established doctrine (C.9, one instrument per property) — the prior arcs' exclusion text for these six already says so in as many words ("a check that re-drove it would be a second instrument for a property the suite already owns"). Manufacturing six more check files that assert the same things pytest already asserts would satisfy the coverage gate's SUBJECTS-counting mechanism while adding no real measurement — exactly the D3.19 class this arc's own brief warns against twice. I looked for a genuinely non-overlapping property on each of the six (documented per-row above) rather than skipping the exercise.

**Before/after bucket-size delta, honestly reported:** `exclusions` bucket in `checks/gate_coverage_baseline.json`: **13 → 11** (my two retirals; the other 5 rows — `checks/ibgateway_expected.json`, `databases/schema/extract_sources.py`, `risks/broker_order.config.json`, `scripts/d1_12_reboot_capture.py`, `scripts/runtime_gate.py` — are sub-agent B's partition, untouched by me). Of MY 8, 2 retired, 6 remain excluded with refined justifications.

## C3 — filesystem-walk audit (CHECK-DEBT D3.110)

Every `checks/check_*.py` grepped for `rglob`/`os.walk`/`.iterdir(`/`glob.glob`/`.glob(`. **14 files walk the filesystem.** (`check_untracked_attribution` does NOT — it is git-status-based, D3.103's separate blind spot; the D3.110 row's opened text wrongly named it as one to audit, corrected in the discharge.)

| check | verdict | reason |
|---|---|---|
| `check_price_ring` | already safe | Fixed ARC 029: `_SKIP_DIRS` includes `.claude`, `._` name-filtered. |
| `check_datafeed_bar_seal` | already safe (+ hardened) | `._` name-filtered already; `SKIP_DIRS` defensively widened this arc (`.claude`/`.venv-dev`/`node_modules`) though unreachable under `SCAN_ROOTS=("scripts",)` today. |
| `check_datafeed_granted_mode` | already safe (+ hardened) | Same as above. |
| `check_order_path_bans` | already safe (+ hardened) | `_parse_all`'s `except SyntaxError, UnicodeDecodeError` already survives a sidecar without crashing. `SKIP_DIRS` widened, `._` name-filter added to `_candidate_files` and `_files_under` for hygiene (count sites, not crash sites). |
| `check_risks_data_only` | already safe | `json.loads(path.read_text(...))` wrapped in `except (OSError, ValueError)`; `UnicodeDecodeError` IS a `ValueError`. Confirmed by inspection. |
| `check_capture_plane2` | already safe | `read_text(..., errors="replace")` — never raises. |
| `check_verify_logging` | already safe | Same pattern. |
| `check_canonical_tree` | already safe | Single-level `iterdir()` gated on a marker file (`scripts/verify.py` presence); no content read. |
| `check_plane1_wal` | already safe | Single-level `iterdir()` on a scratch dir the check created itself (`_remove_tree`), not the live tree. |
| `check_picture_atomicity` | already safe | Same `_remove_tree` pattern. |
| `check_state_bus` | already safe | Same `_remove_tree` pattern. |
| `check_derived_claims` (2 sites) | already safe | `glob("check_*.py")`/`glob("test_*.py")` patterns exclude `._` prefixes by construction. |
| `check_spec_citations` | **REAL GAP, FIXED** | `SCAN_ROOTS = (".",)` — the whole tree — and `SKIP_DIRS` lacked `.claude`. A live sub-agent worktree's `docs/*.md` would be scanned and its citations double-counted/misattributed against a copy that is not canonical — the exact class `check_price_ring` was measured failing on in ARC 029. Fixed: `.claude` (+ `.venv-dev`, `node_modules`) added to `SKIP_DIRS`. |
| `check_artifact_gate_coverage` (`_named_by_tests`) | **REAL GAP, FIXED** | `.glob("*.py")` under `scripts/tests/` + `read_text(encoding="utf-8")` caught only `OSError`. `UnicodeDecodeError` (raised by `read_text` on an AppleDouble sidecar) is a `ValueError`, not caught — **CONFIRMED reproducible**: planted `._test_imports.py` with AppleDouble magic bytes crashes it pre-fix. Fixed: `._` name-filter added, `except` widened to `(OSError, UnicodeDecodeError)`. |
| `check_derived_claims` (`_p_order_path_anchor_files`, count site) | hygiene fix | `rglob("*.py")` would count an AppleDouble sidecar as a real file (miscounting a DERIVED claim — not a crash, since this site only counts filenames). `._` filter added. |

**Tests added, both with proven non-vacuity** (fix temporarily reverted, crash/pollution reproduced, fix restored, re-verified green):
- `scripts/tests/test_check_spec_citations.py`: `test_scan_tree_survives_an_appledouble_sidecar`, `test_scan_tree_skips_claude_worktree_pollution` (32 tests total in the file, all green).
- `scripts/tests/test_check_artifact_gate_coverage.py`: `test_named_by_tests_survives_an_appledouble_sidecar` (51 tests total in the file, all green — including the pre-existing `test_the_REAL_TREES_THIRTEEN_ceiling_tripped_artifacts_are_the_D3104_EXCLUSION`, updated from `== 13` to `== 11` to reflect this arc's two retirals, with the reasoning stated in its own docstring rather than silently changed).

CHECK-DEBT D3.110 marked **`discharged ARC 030`**.

## C4 — CHECK-DEBT count reconciliation

`check_derived_claims`'s own `check_debt_open_items` probe, run on this worktree after all edits:

```
check_debt_open_items: DISAGREEMENT derived:ledger_rows=152, stated:series_table_latest_row=153
```

This is **expected, not a defect**: the series table's latest committed row (`| 2026-08-14 | ARC 030 | 153 | INTERIM FIGURE (Phase 1 only) ... |`) predates this sub-agent's work. My work discharged exactly **one** row (D3.110) and opened zero, so the derived count drops by exactly one: **153 → 152**. I did not add a new series-table row myself: per this ledger's own established convention (ARC 026/027/029 — every sub-agent states its own BRANCH figure in its own report and the integrator re-derives ONE row at Stage 2/3 convergence after all branches, including sub-agent B's separate `docs/CHECK-DEBT.md` edits in a sibling worktree, are merged), adding a premature dated row from just this branch risks colliding with B's own edits to the same file and duplicating what the integrator will re-derive anyway. **For the integrator:** fold sub-agent C's `153 → 152` (net −1, D3.110 discharged, zero opened) together with sub-agent B's own reported delta into the Stage 2 convergence row.

Self-check against D3.82-class narration risk: the number stated above (152) is `check_derived_claims`'s own `derived:ledger_rows` output, read directly, not hand-counted or asserted from memory.

## Verify / test evidence

- `checks/registry.json`: 2 lines added (`check_preamble_shim`, `check_nixverify_init` registered into `level-0` by `verify.py --optimize --commit` after a manual orphan-removing add — the tool's own `derive_plan` treats a brand-new check as an "orphan" against the registry it is about to update, so the documented workflow is: hand-add the check name to unblock the orphan rule, then `--optimize --commit` normalizes placement/ordering). Diff is 2 insertions only — no reordering of the other 34 pre-existing entries.
- `verify.py` full run (this worktree, after symlinking `.venv`/`.venv-dev` at the worktree root to the canonical interpreters — both gitignored, read-only, nothing rebuilt, purely so the 14 checks that were halting behind `check_venv`'s "no `.venv` at this path" could actually run instead of reporting skipped): **30 passed | 3 failed | 2 cannot measure | 0 skipped | 1 guarded**, vs. the pre-existing baseline (verified via `git stash -u` with the same symlinks in place) of **29 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded**. The delta is exactly `+2 passed` (`check_preamble_shim`, `check_nixverify_init`, both `[ok]`) and `+1 failed`: `check_derived_claims` now reports `check_debt_open_items: sources disagree — derived:ledger_rows=152, stated:series_table_latest_row=153` — which is not a regression, it is the DIRECT, EXPECTED, and already-documented consequence of legitimately discharging D3.110 (see C4 above): the series table's latest committed row still says 153 because it predates this branch, and will be corrected at Stage 2/3 integration. The 2 pre-existing FAILs (`check_ibgateway_service`, `check_node_identity`) and 2 CANNOT_MEASURE (`check_ibgateway_config`, `check_observed_resource_claims`, both downstream of the same unreachable `127.0.0.1:4002` — no live IBGateway on this node) are unchanged and are node/environment artifacts, not this arc's subject, matching the brief's own "pre-existing check_ibgateway_service FAIL + 2 CANNOT-MEASURE are not your concern."
- `scripts/tests/`: full suite has 8 pre-existing collection errors unrelated to any file this sub-agent touched (`test_capture.py`, `test_check_capture_plane2.py`, `test_check_picture_atomicity.py`, `test_check_state_bus.py`, `test_crucible_calendar_gen.py`, `test_feed_kill_drill.py`, `test_picture.py`, `test_statebus.py` — missing `zmq`/`pandas_market_calendars` in this worktree's `.venv-dev`), confirmed identical with and without my changes via `git stash -u` / `--co` (collection-only). All touched test files pass in full, individually verified: `test_check_preamble_shim.py` (13/13), `test_check_nixverify_init.py` (12/12), `test_check_spec_citations.py` (32/32), `test_check_artifact_gate_coverage.py` (51/51), and `test_check_order_path_bans.py`/`test_check_datafeed_bar_seal.py`/`test_check_datafeed_granted_mode.py`/`test_check_derived_claims.py` each individually diffed against a `git stash -u` baseline and found to fail on the EXACT SAME test names with and without my changes (all `.venv/bin/python`-subprocess-path issues: this worktree, by design per the brief, has no `.venv` of its own).

  A full-tree `scripts/tests/` run was attempted twice for additional rigor and both were killed before completion (~4+ min/run) once the ROOT CAUSE of the bulk of the failures was found and confirmed environmental: **`pytest_asyncio` is not installed in the canonical `.venv-dev`** (`ModuleNotFoundError: No module named 'pytest_asyncio'`, confirmed by direct import), so every `@pytest.mark.asyncio` test across the whole tree — `test_broker_datafeed.py`, `test_broker_tier3.py`, `test_datafeed_tier3.py`, `test_exit_integration.py`, `test_flatten.py`, `test_seam_simulate.py` and more, none of them files this sub-agent touched — collects the mark, prints `PytestUnknownMarkWarning`, and runs the coroutine as an un-awaited object, failing on assertion. This is a canonical-environment gap (not this worktree's, not this branch's, not fixable by a sub-agent instructed not to rebuild the canonical venvs) and pre-dates this arc; `pyproject.toml` declares `asyncio_mode = "strict"` and the dependency IS pinned in `checks/pinned_deps.json` per CHECK-DEBT's own text, so the gap is between what's declared and what's installed — a finding worth flagging to the integrator, not a regression to chase down here.

  A worktree-local `.venv`/`.venv-dev` symlink to the canonical interpreters was added (both gitignored, read-only targets, nothing rebuilt) purely so `verify.py`'s `check_venv`-gated block would run instead of halting 14 checks as skipped — see the `verify.py` comparison above, which IS a clean, complete, before/after diff and the more meaningful evidence for this arc's actual subject.

## Files touched

New:
- `checks/check_preamble_shim.py`, `scripts/tests/test_check_preamble_shim.py`
- `checks/check_nixverify_init.py`, `scripts/tests/test_check_nixverify_init.py`

Modified:
- `checks/check_spec_citations.py`, `checks/check_artifact_gate_coverage.py` (C3 real fixes)
- `checks/check_order_path_bans.py`, `checks/check_datafeed_bar_seal.py`, `checks/check_datafeed_granted_mode.py`, `checks/check_derived_claims.py` (C3 defensive hardening)
- `checks/gate_coverage_baseline.json` (2 rows retired, 6 justifications refined — surgical, no reformatting)
- `checks/registry.json` (2 checks registered)
- `docs/CHECK-DEBT.md` (D3.110 discharged)
- `scripts/tests/test_check_spec_citations.py`, `scripts/tests/test_check_artifact_gate_coverage.py` (new plant/restore tests; one pre-existing count assertion updated `13 → 11`)

## Cleanup

No temporary/scratch files left in the repo. All plants in tests use `tmp_path` (pytest-managed, auto-cleaned) or pure in-memory source text — nothing was written to or mutated in the live tree by any test.
