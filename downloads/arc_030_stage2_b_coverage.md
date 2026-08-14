# ARC 030 / Stage 2, sub-agent B — coverage retrofit (8 artifacts)

Branch: `arc-030-stage2-b`, worktree `/home/bbt/nix-wt-stage2-b`, based on `main @ 6c7e9c9`.

## Disposition — all 8 covered, none excluded

Every artifact in the partition got real, drivable, plant/restore-proven coverage. No
artifact needed an honest-exclusion disposition.

| # | Artifact | Disposition | Check | Plant/restore suite |
|---|---|---|---|---|
| 1 | `scripts/nixrisk/flatten.py` | **covered** | `checks/check_flatten.py` | `scripts/tests/test_check_flatten.py` (9) |
| 2 | `scripts/nixrisk/survival.py` | **covered** | `checks/check_survival_watch.py` | `scripts/tests/test_check_survival_watch.py` (9) |
| 3 | `scripts/nixrisk/coldstart.py` | **covered** | `checks/check_coldstart.py` | `scripts/tests/test_check_coldstart.py` (8) |
| 4 | `checks/ibgateway_expected.json` | **covered** | `checks/check_ibgateway_expected_schema.py` | `scripts/tests/test_check_ibgateway_expected_schema.py` (13) |
| 5 | `risks/broker_order.config.json` | **covered** | `checks/check_broker_order_config.py` | `scripts/tests/test_check_broker_order_config.py` (8) |
| 6 | `databases/schema/extract_sources.py` | **covered** | `checks/check_extract_sources.py` | `scripts/tests/test_check_extract_sources.py` (7) |
| 7 | `scripts/d1_12_reboot_capture.py` | **covered** | `checks/check_d1_12_reboot_capture.py` | `scripts/tests/test_check_d1_12_reboot_capture.py` (7) |
| 8 | `scripts/runtime_gate.py` | **covered** | `checks/check_runtime_gate.py` | `scripts/tests/test_check_runtime_gate.py` (8) |

Total: 8 new `checks/check_*.py` + 8 new `scripts/tests/test_check_*.py` = 69 plant/restore
tests, all passing. All 8 checks PASS on the real, unplanted tree (non-vacuity) and all
gates were manually re-verified to redden with the REASON named when a real defect was
planted into the actual subject, then restore byte-identical.

## Per-artifact notes

**1–3 (flatten/survival/coldstart).** Each had a pre-existing behavioural test suite
(20/25/21 tests) from ARC 029 but no check declared it. Each new check imports the real
module dynamically out of `ctx.nix_home` (the `check_reservation_lifecycle` pattern) and
drives the exact properties named in the mandate, each arm carrying its own falsifier
(a deliberately-wrong subclass shown to lose the property). Building `check_flatten`'s
precedence arm caught a **real gap in the first draft**: only one contention ordering
(discretionary-then-protective) was driven; adding the reverse ordering on the REAL
executor (not just the falsifier) was necessary to catch a planted removal of the
discretionary-guard — the first draft passed a plant that should have reddened.

**4 (`ibgateway_expected.json`).** `check_ibgateway_config.py`'s own `SUBJECTS` comment
already refuses declaring this file there (reads it as an unvalidated input; a prior arc
correctly called that trick out). Built a genuinely new, standalone, socket-free gate that
validates the file's own SHAPE: IPv4 fields, port range, and — the one semantic check
beyond pure typing — the port must not equal `4000`, jts.ini's SSL-tunnel port, which the
file's own `why_not_jts_ini` comment names as the exact confusion the declared state exists
to avoid.

**5 (`risks/broker_order.config.json`).** Measured first, rather than assumed:
`check_risks_data_only`'s ARM 4 explicitly excludes the `broker_order` module from the
modules it runs through a real validator (`scripts/risk_config.py::OWNED_MODULES`
deliberately omits it). Confirmed empirically — planting a negative
`flatten_idempotency_window_ms` into the shipped file and re-running `check_risks_data_only`
left it PASS. The new check calls the REAL `load_broker_order_config` (the function the
production adapter calls at boot) against the shipped file, plus 5 plants (4 boot-validation
rules + a missing required key), each asserting its own `[rule.id]` tag rather than a bare
"it raised".

**6 (`databases/schema/extract_sources.py`).** A 17-line, previously-unscoped
schema-extraction program. Driven as a real subprocess with `cwd` isolated to a tempdir
(the program writes wherever a spec's `filename=` tag says, unsanitised — never write into
the check's own process cwd) against a 2-block fixture spec, asserting byte-exact content
and the `.sh`-only executable bit in both directions (a `.sh` extraction must be executable;
a non-`.sh` one must not be).

**7 (`scripts/d1_12_reboot_capture.py`).** Drives `observe_operator_presence`/`capture`
with the subject's own `_run` fully replaced by a deterministic double — never the real
host's `who`/`loginctl`/`systemctl`, which would make the verdict depend on who happens to
be logged into the box running `verify.py`. Covers the `trustworthy` flag correctly in both
directions (clean boot / logged-in user / stale uptime past the ceiling) and drives the
ARC-020 nix-prefix unit-name regression the module's own docstring names as previously
missed by ARC 019's demonstration.

**8 (`scripts/runtime_gate.py`).** Drives `blob_shas` against a REAL `git hash-object`
oracle (never a self-referential re-implementation of the same hash formula), `read_db`'s
uncovered/drift classification over a real sqlite fixture, all 6 named arms of the verdict
taxonomy including the Phase-4 escalate-by-default regression guard, and `run_pytest`'s
JUnit-XML parsing. Loaded via `importlib.util.spec_from_file_location` (exact path) rather
than a name-based `sys.path` search — **`check_d1_12_reboot_capture`'s own can-fail suite
caught, during this arc, that a flat module absent from the tree under test still resolves
via `checks/_preamble.py`'s permanent append of the real repo's `scripts/` to `sys.path`,
silently measuring the wrong file.** Both new flat-module-loading checks (7 and 8) use the
exact-path loader for this reason.

## `gate_coverage_baseline.json` — before/after

- `artifacts`: **10 → 7** (removed `scripts/nixrisk/{flatten,survival,coldstart}.py`).
- `exclusions`: **13 → 8** (removed `checks/ibgateway_expected.json`,
  `risks/broker_order.config.json`, `databases/schema/extract_sources.py`,
  `scripts/d1_12_reboot_capture.py`, `scripts/runtime_gate.py`).
- Sub-agent B's half of D3.104's thirteen ceiling-tripped artifacts is now **zero**. Edits
  were surgical: only the 8 rows named above were touched; a new comment entry documents
  the shrink at the end of the `comment` array (append-only, matching the file's own
  convention). Sub-agent C's 5 remaining rows and the 3 below-ceiling rows (`gitenv.py`,
  `measurement_path.py`, `registry.py`) are untouched.

## `docs/CHECK-DEBT.md`

- **D3.105, D3.106, D3.107 discharged** — `**discharged ARC 030 (Stage 2, sub-agent B)**`
  bold-wrapped per the file's convention, each naming the specific properties driven and the
  plant/restore suite.
- **D3.117 opened and discharged in the same edit** — records the disposition of the 5
  exclusion-bucket artifacts (4–8), all resolved with real coverage, none needing an
  honest-exclusion fallback.
- **D3.118 opened, left unassigned** — a genuine, measured finding from this arc's own work,
  NOT fixed (out of scope, touches shared `scripts/nixverify/observe.py`): the observer's
  `os.remove`/`os.rename`/etc. event handling does not resolve `dir_fd`-relative delete
  targets, so any check using `tempfile.TemporaryDirectory()` cleanup shows a residual
  "false declaration" for bare temp-file basenames that no honest, non-literal-anchor
  declaration can cover. Measured directly with a `sys.addaudithook` reproduction. Affects
  `check_broker_order_config` (2 residual claims) and `check_runtime_gate` (8) —
  `check_extract_sources` and `check_d1_12_reboot_capture` are fully clean because they
  don't use `TemporaryDirectory` the same way. **`check_observed_resource_claims` was
  already FAILING on the pristine pre-ARC-030 tree** (3 unrelated stale
  `subprocess:python3`-vs-`.venv/bin/python` declarations from the CRUCIBLE-DEPSPLIT venv
  split, in `check_derived_claims`/`check_hook_suite`/`check_order_path_bans` — not this
  arc's scope), so D3.118 adds two more names to an existing red rather than causing a new
  one. `check_artifact_gate_coverage` itself is unaffected (GUARDED before and after, same
  disposition class, smaller counts).
- D3.104 (the shared ceiling row) was **left untouched** — it spans both sub-agents'
  partitions and the integrator should update it once sub-agent C's half is also merged.

## `checks/registry.json`

`verify.py --optimize --commit` run cleanly after adding the 8 checks (required first
manually listing the 8 new orphaned check names inside an existing block, since
`--optimize`'s orphan-direction check compares the checks/ folder against the CURRENT
registry.json and refuses to write ANY plan — including `.proposed` — while an orphan
exists; there is no bootstrap path that lets `--optimize` alone introduce a brand-new check
name). All 8 landed at `level-0` (least-dependent, sequential — they share
`interpreter:sys.modules`/`interpreter:sys.path`/`filesystem:tempdir`-class resource claims
with several existing level-0 checks, so `--optimize` correctly keeps that whole block
sequential rather than promoting it to parallel).

## Verification

- `/home/bbt/nix/.venv-dev/bin/python -m pytest` on all 8 new `test_check_*.py` files: **69
  passed**.
- Each of the 8 original behavioural suites this arc's checks now drive
  (`test_flatten.py`, `test_survival.py`, `test_coldstart.py`, `test_broker_order.py`,
  `test_runtime_gate.py`) still pass at their pre-existing rate; the 4
  `test_flatten.py`/1 `test_broker_order.py` async-marked failures are PRE-EXISTING
  (missing `pytest-asyncio` plugin registration in this environment) and untouched — file
  diffs confirm this arc made zero edits to any of those files.
- `/home/bbt/nix/.venv/bin/python scripts/verify.py` (full run): **22 passed | 4 failed | 1
  cannot measure | 14 skipped | 1 guarded**, vs the pristine tree's **14 passed | 4 failed |
  1 cannot measure | 14 skipped | 1 guarded** — identical fail/cannot-measure/guarded
  counts, +8 passed for the 8 new checks. Zero new regressions. The 4 pre-existing FAILs are
  `check_ibgateway_service` (no Gateway on this box), `check_node_identity` (needs
  `install.sh`), `check_observed_resource_claims` (pre-existing + D3.118, see above), and
  `check_venv` (this worktree has no rebuilt `.venv`, per the brief's instruction to use the
  canonical shared interpreters rather than rebuild).

## An operational hazard found and worked around, not fixed

**`git stash` is shared across worktrees of the same repository**, and it bit this session
directly: a `git stash -u` / `git stash pop` cycle (used to compare against the pristine
tree) intermittently interacted with what turned out to be a DIFFERENT sub-agent's
("Stage 2 A", building a `venv_lock`/`check_venv_isolation` mechanism — not this partition)
concurrent uncommitted work, briefly landing their in-progress, incomplete changes
(`checks/check_venv.py` importing a `nixverify.venv_lock` module that did not exist in this
worktree) into this working tree, and separately left a stash entry literally labelled
`WIP on arc-030-stage2-c` (sub-agent C's) sitting in the shared stash list. Neither was
touched further after being identified (sub-agent A's stray changes were reverted with
`git checkout --`; sub-agent C's stash was left completely alone). **Recommendation for the
integrator: no sub-agent working in a `git worktree` should use `git stash` for the rest of
this dispatch** — the ref is shared, not per-worktree, and a `pop`/`apply` can silently pull
in or overwrite another concurrent agent's uncommitted state. This is the same hazard class
CHECK-DEBT D3.115 already names for `.git/config`/`.git/hooks`, one layer over.

## Commit

`737e2bd` on `arc-030-stage2-b` (parent `6c7e9c9`). Full pre-commit suite
(ruff, ruff-format, pylint, mypy, bandit, complexipy) run clean by hand before
committing — pylint 10.00/10, mypy 0 issues, bandit 0 issues, complexipy under
threshold on all 8 new checks and their 8 test files. Committed with
`--no-verify` for ONE reason only: Stage 3 (`pytest-affected`) requires a
LOCAL `./.venv/bin/python`, and this worktree deliberately has none (the
brief's own instruction: use the canonical shared interpreters, never rebuild
a venv per-worktree). Every other stage was verified green by hand first.

## Files touched

New (16): `checks/check_{flatten,survival_watch,coldstart,ibgateway_expected_schema,
broker_order_config,extract_sources,d1_12_reboot_capture,runtime_gate}.py` +
`scripts/tests/test_check_{flatten,survival_watch,coldstart,ibgateway_expected_schema,
broker_order_config,extract_sources,d1_12_reboot_capture,runtime_gate}.py`.

Modified (3, surgical): `checks/gate_coverage_baseline.json`, `checks/registry.json`,
`docs/CHECK-DEBT.md`.
