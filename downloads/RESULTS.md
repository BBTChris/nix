# ARC 030 — Trunk Reconciliation, Enforced Isolation, and the Coverage Close

**Canonical path:** `/home/bbt/nix` (absolute, unmoved). **Final `main` HEAD:** `9858b37`.
**`origin/main`:** still `0f9c5b9` — local `main` is 92 commits ahead, **not pushed**. Outward-facing;
left for explicit operator confirmation rather than pushed unilaterally.

---

## PHASE 0 — measured, changed nothing

The brief asserted a topology the architect had not fully verified (§0a). Measured instead:

- **`main` already contained ARC 022–025** (PR #25 merge, `0f9c5b9`). The real unmerged column
  started at **ARC 026**, not 022 — a finding, reported to the operator before any merge.
- The unmerged set was a **clean, linear, single-parent, 81-commit chain**:
  `main → 026(+17) → 027(+11) → 028(+20) → 029-integration(+30, incl. interleaved MON-1) →
  calendar-infra(+1) → depsplit(+2)`. No forks, no divergent branches to reconcile.
- MON-1 commits (`42fb3fd`, `b7f5b79`) sit inside `arc-029-integration`'s first-parent chain.
  `check_monitor` FAILED for real on the pre-arc branch tip (harness glyph/ETA mismatches).
- Baseline `verify.py` on `arc-crucible-depsplit`: **29 passed | 3 failed | 2 cannot-measure |
  1 guarded**. FAILs: `check_ibgateway_service` (tap session, owned), `check_monitor` (deprecated),
  `check_untracked_attribution` (real untracked cruft — `.ua/` graphify cache, `scripts/m.sh`,
  incidental to this session, not any arc's work).
- Only the canonical worktree existed. Zero live parallel-arc collision risk.

**Operator confirmed:** proceed on the measured topology (not the brief's 022 assumption); delete
the untracked cruft before gating.

---

## PHASE 1 — reconciled

Six forward promotions, oldest-unmerged-first, each a genuine fast-forward (verified, not narrated),
`verify.py` + `pytest` gated at every step (full suite at three checkpoints given ~9–10 min/run;
intermediate-commit `verify.py` runs were confounded by testing old checkouts against today's
filesystem — `.venv-dev` and AppleDouble sidecars didn't exist when those commits were made — treated
as environment noise, not regressions, and **fed directly into Stage 2 A2/C3 as real evidence**).

`main` landed at `6c7e9c9` after **MON-1 disposition (1.2, §0h forward-only)**: `checks/check_monitor.py`
deleted, removed from `checks/registry.json` by hand (`--optimize` refuses to silently drop an
orphan — loud by design), its three scripts admitted to the coverage ratchet (CHECK-DEBT D3.113,
opened+discharged same motion, net 0). History kept intact — MON-1's commits reached trunk via the
ordinary fast-forward, never rebased out.

**1.3 confirmed:** unmerged set from the six-branch stack is **`0`**; all six branches are ancestors
of `main`. Final Phase 1 `pytest`: **1498 passed, 2 skipped, 2 xfailed, exit 0.**

---

## STAGE 2 — three parallel sub-agents, provisioned worktrees off the reconciled trunk

### A — Isolation, enforced

| item | finding | mechanism built |
|---|---|---|
| A1 | `git worktree add` genuinely gives per-worktree index/HEAD — proven, not assumed. **Gap found:** `.git/config`/`.git/hooks` are shared across all worktrees (D3.115, currently unexercised) | — |
| A2 | Reproduced the CRUCIBLE-DEPSPLIT half-rebuilt-`.venv` hazard directly: a gate against a mutating venv reports spurious artifact failures | `scripts/nixverify/venv_lock.py` (flock, non-blocking), wired into `check_venv`/`check_python_deps`/`check_python_transitive_deps` (mutation → CANNOT_MEASURE, never a false verdict); new `checks/check_venv_isolation.py` gates the `.venv`/`.venv-dev` split against silent re-merge |
| A3 | `check_untracked_attribution` extended with a foreign-commit arm — **found two real, pre-existing, never-merged stray branches** (`docs/arc002-results`, `docs/arc005-writeback`) touching tracked paths. Honest boundary named: a detached-HEAD commit whose worktree is later removed becomes unattributable (D3.114, unassigned — no git fact recovers it) | `checks/foreign_branch_exceptions.json` |
| A4 | **Live, unplanned collision, not simulated:** `refs/stash` is ONE ref shared across all worktrees — sub-agent A's own `git stash` raced sub-agent B's concurrent one, one worktree's stash briefly went missing. Recovered via `git fsck --unreachable` + verified byte-identical (D3.119, unassigned — ordinary tooling, not gated) | the single strongest confirmation of Stage 2's own premise: isolation is real work, not a checkbox |

Also found a third, ungated environment surface: `pre-commit`'s own per-hook venvs (D3.116, unassigned, out of A's mandate).

### B — Coverage retrofit, 8 of 16 (all covered, zero exclusions needed)

| artifact | check | tests |
|---|---|---|
| `scripts/nixrisk/flatten.py` | `check_flatten.py` | 9 |
| `scripts/nixrisk/survival.py` | `check_survival_watch.py` | 9 |
| `scripts/nixrisk/coldstart.py` | `check_coldstart.py` | 8 |
| `checks/ibgateway_expected.json` | `check_ibgateway_expected_schema.py` | 13 |
| `risks/broker_order.config.json` | `check_broker_order_config.py` | 8 |
| `databases/schema/extract_sources.py` | `check_extract_sources.py` | 7 |
| `scripts/d1_12_reboot_capture.py` | `check_d1_12_reboot_capture.py` | 7 |
| `scripts/runtime_gate.py` | `check_runtime_gate.py` | 8 |

Discharged D3.105–107. Opened D3.118 — a real `nixverify.observe` `dir_fd`-resolution gap producing
two false resource-claim positives; left `unassigned` rather than papered over with a literal-token
anchor doctrine C.4 forbids.

### C — Coverage retrofit, 8 of 16 (2 covered, 6 honestly excluded) + filesystem-walk hardening

| artifact | disposition |
|---|---|
| `checks/_preamble.py` | **covered** — `check_preamble_shim.py`, 13 tests |
| `scripts/nixverify/__init__.py` | **covered** — `check_nixverify_init.py`, 12 tests (the "executed by every import" case) |
| `actuation.py`, `contract.py`, `engine.py`, `loader.py`, `optimize.py`, `render.py` | **honestly excluded** — each already carries 3–35 pytest modules of real coverage; a `checks/check_*.py` re-driving the same property is doctrine C.9's forbidden second instrument, not new coverage |

**C3 (D3.110, discharged):** audited all 14 filesystem-walking checks for the AppleDouble/`.claude`
sidecar-crash class. Two real gaps found and fixed (`check_spec_citations`'s missing `.claude` in
`SKIP_DIRS`; `check_artifact_gate_coverage`'s `_named_by_tests` crashing on a non-UTF-8 sidecar,
confirmed reproducible before the fix). The rest were confirmed already safe by construction.

---

## STAGE 3 — convergence

Merged all three branches into `main`. JSON-object auto-merges landed clean; hand-spliced two
additive `comment`-array conflicts (both sides' text kept) and **one genuine cross-worktree
CHECK-DEBT numbering collision** — sub-agents A and B independently opened "D3.117" from separate
worktrees with no visibility into each other. Caught at integration, A's renumbered to **D3.119**.
Fixed a real AST-probe break (`check_derived_claims`' `pytest_collected_tests` prober cannot count a
non-literal `parametrize` — A's new test used `sorted(gate.DEV_ONLY_MARKERS)`; literal-ized it with a
drift-guard test). Regenerated `registry.json` (`--optimize --commit`, clean, 45 checks).

**Proactively re-pointed ten legacy `ARC 030`-owned coverage rows to `ARC 031`** before this arc's
own close-out could strand them (once `sessions/SESSION.md` names ARC 030 complete, `guard_owner_defect`'s
read-time check degrades any row it still owns — D3.40's mechanism). Nine landed safely. **One,
`scripts/nixverify/measurement_path.py`, was already AT its re-owning ceiling with zero headroom** —
the re-point burned a third, irreversible re-owning into committed history. §0h means that commit
cannot be un-made. **Taken as a genuine, self-caused, named FAIL** (CHECK-DEBT **D3.120**, `owner:
unassigned` — naming a future arc would repeat the mistake, not discharge it) rather than hidden.

Also caught and reverted: `pre-commit run --all-files`, run to verify the fix above, silently
rewrote MON-1's three byte-frozen architect artifacts (`scripts/{monitor,harness,pty_test}.py`) via
`ruff-format`. Restored to `HEAD` before it landed in any commit — never shipped.

**Real binding census** (`scripts/tests/binding_census.py`, full suite traced, 1068 observations,
`.venv`'s interpreter — `.venv-dev` lacks `zmq` and silently drops zmq-dependent test modules, a
real tooling finding worth noting for future census runs):

**43 BOUND / 2 EXERCISED-NEVER-RED / 0 UNBOUND**, of 45 registered checks.

- EXERCISED-NEVER-RED: `check_crucible_calendar` (only ever observed PASS in this suite run — no
  can-fail path exercised by the traced tests), `check_untracked_attribution` (only ever observed
  GUARDED — the two real stray branches keep it there whenever it runs against the live repo).

CHECK-DEBT series row re-derived twice as new debt landed (153 → 154 → 155), each time reconciling
a hand-tally against `check_derived_claims`' own `derived:ledger_rows` rather than typing a number —
one hand-tally error (missed B's D3.105–107 discharges) caught and corrected in place.

---

## Coverage disposition — the sixteen

| | count |
|---|---|
| Bound to real per-artifact checks this arc | **10 / 16** (B: 8/8, C: 2/8) |
| Honestly excluded, justified, owned | **6 / 16** (all C's: the six `nixverify` modules doctrine C.9 forbids duplicating) |
| `check_artifact_gate_coverage` exclusion bucket | 13 → **6** |

Every excluded artifact carries: `justification` (specific, not boilerplate), `temporary: true`,
`owner: ARC 031` (re-pointed from the stale `ARC 030` this same Stage, verified against the
per-artifact re-owning ceiling before landing — see D3.120 for the one exception).

---

## PHASE 4 CLOSE-OUT

**1 — `verify.py` on trunk (`9858b37`):**

```
40 passed | 3 failed | 1 cannot measure | 0 skipped | 1 guarded          exit 1
```

| verdict | check | owner / status |
|---|---|---|
| FAIL | `check_ibgateway_service` | pre-existing, tap session (out of this arc's scope) |
| FAIL | `check_observed_resource_claims` | D3.118, **owner unassigned** — real `dir_fd`-resolution gap in `nixverify.observe`, understood, deliberately not papered over |
| FAIL | `check_artifact_gate_coverage` | D3.120, **owner unassigned** — this arc's own self-caused ceiling breach on `measurement_path.py`, named honestly; discharge = real coverage for that one module, or a new `CHECK-A<n>` ruling moving it to exclusions |
| CANNOT-MEASURE | `check_ibgateway_config` | pre-existing, same tap-session root cause |
| GUARDED | `check_untracked_attribution` | owner `ARC 031` (both branches in `foreign_branch_exceptions.json`) — an operator decision to delete or merge the two stray branches discharges it |

`check_monitor`: **gone**, not failing, as required by 1.2.

**2 — Full pytest:** `1620 passed, 2 skipped, 2 xfailed, exit 0`. Pre-commit: passes on every diff-scoped
commit made this arc (confirmed at every commit in this arc's log). `pre-commit run --all-files`
surfaces large pre-existing, out-of-scope repo-wide lint debt (e.g. MON-1's byte-frozen architect
artifacts, deliberately never ruff-clean by their own original commit's `--no-verify`) — not a
regression from this arc, not attempted to be cleared here. Claims harness: `check_derived_claims`
green, 0 restatements, all figures re-derived not typed. CHECK-DEBT: series row `155`, agrees with
the tool.

**3 — Binding table with coverage disposition:** see above — **10/16 bound real, 6/16 honestly
excluded** (owner ARC 031, justified, temporary), exclusion bucket 13→6. Full binding census:
**43 BOUND / 2 EXERCISED-NEVER-RED / 0 UNBOUND** of 45 registered checks.

**4 — `git add -A` before every gate measurement:** done throughout; ignore-rule resolution
(D2.24) held (`._*`/`.DS_Store` correctly gitignored and correctly the subject of D3.103's named,
pre-existing blind spot — reproduced live during Phase 1, not hypothetical). `gitenv.py`'s scrub
(D3.22) is the standing mechanism every `verify.py`-internal subprocess `git` call already routes
through; this session's own interactive `git` calls (merges, commits) are the operator/integrator's,
outside that scrub's scope by design.

**5 — Write-back, on the reconciled trunk:** appended to the end of `sessions/SESSION.md`;
**this file overwritten**. `cat` of both, and the durability proof, is the next action in this
session's response.

**6 — Clean-up:** three Stage 2 worktrees (`nix-wt-stage2-{a,b,c}`) and their branches removed after
merge. No other temp files created by this arc remain.

**7 — HEAD advanced, `main` authoritative:** `main` at `9858b37`; unmerged set from the reconciled
stack: **empty**. `origin/main` not yet pushed (outward-facing action, left for explicit operator
confirmation).

**8 — Canonical path:** `/home/bbt/nix` (absolute).

---

## Open items returned to the operator / architect

1. **Push `main` to `origin/main`?** 92 commits ahead, clean fast-forward from the remote's
   perspective (need to confirm no remote-side divergence before pushing).
2. **`docs/arc002-results` / `docs/arc005-writeback`** — two real, pre-existing, stray branches
   found by Stage 2 A3, currently GUARDED via a named exception. Recommend delete (superseded
   `RESULTS.md` snapshots, no unique content) or leave GUARDED indefinitely — operator's call.
3. **D3.120 (`measurement_path.py` ceiling breach)** — needs either real per-artifact coverage or an
   architect ruling extending D3.104/CHECK-A8's exclusion mechanism to cover it (a new `CHECK-A<n>`).
4. **D3.118 (`nixverify.observe` `dir_fd` gap)** — real but structural; fixing it properly needs
   `/proc/self/fd/<n>` resolution, Linux-specific, matches this project's scope, not attempted here.
5. **The tap session** — untouched, as instructed. Still the only code-independent FAIL.
6. **After this arc: R3, the Allocator** — now has a reconciled trunk to build on.

===RUN SUMMARY: ARC 030 — Trunk Reconciliation, Enforced Isolation, and the Coverage Close, Estimated run time: ~5 hours, completes ~25-30% (check-subsystem module: isolation now real and gated, coverage 0/16→10/16 real with the rest honestly excluded); ~10-15% (whole project: clears the "no authoritative trunk" blocker every subsequent arc, starting with R3, depended on)===
