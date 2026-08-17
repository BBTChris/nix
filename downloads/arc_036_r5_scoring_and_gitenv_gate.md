# ARC 036 — R5: The Scoring Process (and the git-env standing gate)

**Module:** Scoring process (Core 4–5 shared pool, new) + the Allocator/Limiter O(1) read seam + a
standing repo-safety gate (D3.205)
**Predecessor:** ARC 035 (merged; Plane-1 durable record landed, repo recovered clean, HEAD `0d8ffd4`)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking (the git-env gate is built FIRST, before any worktree spawns) ·
Stage 1 **wide parallel fan-out** (five disjoint sub-agents) · Stage 2 serial integration · Stage 3
convergence · Phase 4 close-out.

**Verifies:** stands up the last dependency-locked infra module — the Scoring process (§6.6) — so the
Allocator's performance-weighted contention has a ranking table to read, and closes the repo-corruption
class (D3.205) with a standing gate before the wide fan-out that follows can re-trigger it.

---

## WHAT CHANGES WITH THIS ARC

Two things, and the ordering between them is deliberate.

1. **The git-env standing gate (D3.205), FIRST.** ARC 035 corrupted the canonical repository because
   `harness.py` made unscrubbed `git` subprocess calls under a hook, and the D3.22 scrub was applied
   per-site (remembered) rather than enforced (gated). It recurred **three times in one arc, twice
   inside the instrument built to police it.** This arc spawns *more* parallel worktrees than any
   before it (20x fan-out), each running git — so the gate that makes a sixth unscrubbed call
   impossible must exist **before** Stage 1, not after. This is Phase 0, blocking.

2. **The Scoring process (§6.6), the body.** A dedicated shared-pool process, **sole writer** of a
   ranking table = **realized-P&L EMA per `(strategy_id, symbol)` pair**, advances per day, EMA span
   default 10 trading days. The Allocator reads it to weight sizing; the Limiter reads it to arbitrate
   contention. Both do **O(1) lookups, never math** — nobody but the Scoring process computes the
   score. **FCFS fallback is locked and load-bearing:** if Scoring is down or its table stale, both
   fall back to first-come-first-served — *ranking is an optimization, never a safety gate; a scoring
   outage must NEVER halt order flow.*

**The distinction that will trip a literal reading:** there is a `strategy_score.py` in the tree (the
Gate 5/6/7 **decision-point evaluator** — DSR, band membership, promotion/re-cert). That is NOT this.
§6.6 Scoring is the **runtime contention EMA** — realized advances per day, smoothed, keyed per pair,
read O(1) on the allocation path. Conflating the evaluator's score with the contention EMA is the
category error to refuse; the evaluator promotes strategies offline, the Scoring process ranks live
pairs for capital contention. Read §6.6 directly.

---

## §0a — Self-audit, this brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

**The FCFS-fallback trap:** the fallback is the safety-relevant half. A Scoring process that is never
taken down never exercises the fallback, so a test suite that only drives the happy path proves the
optimization and leaves the *survival* property (order flow continues when Scoring dies)
**unmeasured** — while every gate is green. Assume this brief contains at least one property whose
only real test requires killing the Scoring process, and one hazard stated backwards (the fail-open
cap, the uncalled origin write, and the armed-corruption were each a hazard the brief had backwards;
six-plus measured backwards across 027–035).

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-artifact-drives-shipped-bytes-red · §0f explicit-status-or-owner, table-rebuilt · §0g owner-names-future-arc · §0h forward-only · §0i mirror-stale-until-proven-fresh · §0j marker-is-last-token (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

---

## PHASE 0 — The git-env gate, corrections, rulings, seam freeze (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 035's close: verify.py
`73 passed | 3 failed | 2 cannot measure | 0 skipped | 1 guarded`, exit 1; binding BOUND=60 / ENR=1 /
UNBOUND=0; CHECK-DEBT 220. **Any delta is a finding.** Name every FAIL and the guard's owner.

**0.2 — THE D3.205 GIT-ENV STANDING GATE (build this before anything spawns a worktree).**
`check_git_env_scrub`: every subprocess `git` invocation in shipped code (`scripts/`, `checks/`,
tooling) must route through the `gitenv.py` scrub that neutralises inherited `GIT_DIR`,
`GIT_INDEX_FILE`, `GIT_WORK_TREE` (the three that made `git -C` insufficient under a hook). The gate:
- **Derives the call-site list from the tree** (§0f — no snapshotted list; grep the AST/source for
  `git` subprocess calls and assert each resolves through the scrub), so a *new* unscrubbed call added
  later reddens it.
- **Ships a both-halves control** (the D3.205 lesson exactly): an unscrubbed call must **corrupt a
  throwaway victim** repo (prove the gate's subject is real), and the scrubbed call must leave the
  victim's index **byte-identical** (prove the fix). Per §7.12/D3.205: the control's own harness must
  itself be scrubbed — writing this test is where the defect masked itself twice, so the control must
  demonstrate it *can* fail (plant an unscrubbed call, watch it corrupt; plant `GIT_WORK_TREE` export,
  watch the control go silent — and gate against that silence).
- **Non-vacuity:** assert the scanned scope actually contains ≥1 git call before trusting a green.

This gate is the whole reason Phase 0 is blocking: it must be green before Stage 1's wide fan-out
runs git across many worktrees.

**0.3 — Carried operator rulings (report; act only where authorized).** Push (`main` 26 ahead / 0
behind, clean fast-forward — re-confirm, report, STOP for operator); SPEC-A10 vendor (still
UNRATIFIED); branch protection (drafted ruleset, operator applies); provenance on the five untracked
artifacts in the canonical tree (name each; classify keep-and-track vs remove).

**0.4 — Freeze the Scoring seam (§6.6).** The ranking-table shape (`(strategy_id, symbol)` → realized
EMA + rank), the **shared-memory** publish (Scoring is sole writer; Allocator + Limiter mirror
read-only, snapshot-on-subscribe, freshness-stamped per §12.7), the **O(1) read contract** (readers
look up, never compute), and the **FCFS fallback trigger** (table absent OR stale-past-threshold).
Declare sync/async per verb. **Prove the seam gate reddens** on: a reader that computes instead of
looks up; a fallback that stalls instead of returning FCFS; a second writer to the ranking table.

---

## STAGE 1 — Wide parallel fan-out (FIVE disjoint sub-agents)

Each from its own provisioned worktree + own git index + isolated venv (ARC 030 isolation). D3.192
holds: N worktrees adding modules to one package home produce N−1 conflicts on shared literals
(registry, order-path list) — resolved at merge against the merged tree, and the integrator audits
the merged tree for defects each blind branch was green over (ARC 035 Stage 2 caught four).

### SUB-AGENT A — The EMA engine (§6.6 measurement)

**A1 — Realized-P&L only, per day, EMA-smoothed.** Reads **closed-trade realized P&L from Plane-1**
(the durable record ARC 035 landed) — never unrealized/open marks (a green open position can reverse;
§6.6 locks realized-only). One realized number per `(strategy_id, symbol)` per day; EMA span =
`SCORE_EMA_SPAN_DAYS` (default 10, a tunable, **not** a carved constant — derive from config).

**A2 — Prove it ranks completed decisions, not activity.** §6.6 locks "advances per day" so a
hyperactive symbol can't dominate by trading more often. Drive two pairs — one with few large
realized wins, one with many tiny ones — and prove the ranking reflects realized productivity per
day, not trade count. §0a: an EMA test on a single pair proves the math, not the *ranking*; rank is a
comparison, so drive ≥2 pairs.

### SUB-AGENT B — The ranking table + the O(1) read seam (§6.6, §12.7)

**B1 — Sole-writer ranking table in shared memory**, published PUB/SUB mirror model, snapshot-on-
subscribe, freshness-stamped (§12.7). Scoring is the only writer; prove a write from any other
identity is refused/absent-by-construction (the sole-writer proof, measured not asserted).

**B2 — O(1) reads, no hot-path math.** The Allocator and Limiter read the precomputed rank; neither
computes an EMA. Prove the hot gate path does a table lookup only (consistent with the
margin/tradability cache pattern) — a reader that recomputes is the §11 hot-path violation. Drive
reads concurrent with writes and prove no torn read and no reader-side computation.

### SUB-AGENT C — The FCFS fallback (§6.6, LOCKED, safety-relevant)

**C1 — Scoring down OR table stale ⇒ FCFS, never a stall.** Kill the Scoring process mid-contention
and prove both Allocator and Limiter fall back to first-come-first-served — deterministic,
structurally neutral (favours no symbol), needing no computation at the instant a process just died.
**Order flow does NOT halt.** This is the §6.6-locked invariant: *ranking is an optimization, never a
safety gate.* §0a: the fallback is the whole safety point — prove it by actually killing Scoring and
by a genuinely stale table, not by a flag that simulates "down."

**C2 — Stale detection is real.** The table is "stale" past a freshness threshold (§12.7); prove the
threshold is measured against real staleness, not a proxy, and that a stale-but-present table triggers
FCFS just as an absent one does (a stale table read as fresh is the silent failure).

### SUB-AGENT D — Score lifecycle: persistence across death, quarantine archival (§6.6, §4)

**D1 — Score persists across process death.** The score is keyed to the `(strategy_id, symbol)` pair,
not the process (§6.6) — so a strategy that dies and relaunches (the ARC 034 recovery path) resumes
with its EMA history intact. Prove the row survives a kill/relaunch and is NOT reset to cold-start.

**D2 — Quarantine archives exactly that strategy's rows.** When a strategy is quarantined (ARC 034
crash-loop cap), its ranking rows are **archived, not destroyed** (§6.6), and quarantine-restore
(§12.11 verb) returns them with the counter reset. Prove archival removes exactly that strategy's
pairs and no others, and that restore rehydrates them.

### SUB-AGENT E — Allocator consumption + instrument debt

**E1 — The Allocator actually READS the table (close the "built but uncalled" class).** ARC 033's cap
shipped built-but-uncalled; this arc must not ship a ranking table nothing consumes. Wire the
Allocator's performance-weighted contention to read the pair-rows and prove a **contention outcome
changes** when the ranking changes — drive two strategies GO on one symbol and prove the higher-ranked
pair wins, then flip the ranking and prove the outcome flips. (Full Allocator recovery-reflection
finish remains a later arc; this proves consumption, the dependency this arc exists to unblock.)

**E2 — The uncalled-entrypoint sweep** (D2 from ARC 034/035, standing): the ranking table's writer
verbs and the readers' lookup hooks must have real callers. A table written but never read, or a
reader hook never invoked, is a finding.

**E3 — CHECK-DEBT reconciliation** with the derived-vs-narrated arithmetic gate (D3.82) over this
arc's own results.

---

## STAGE 2 — Integration (SERIAL)

**2.1 — The contention drill, end to end.** Two strategies GO on one symbol with only enough
liquidity for one → the Limiter arbitrates by reading the ranking table → the higher-realized pair
wins → the outcome books its Plane-1 rows. Then the same with the Allocator weighting sizing off the
table. Prove the O(1)-read path never computed an EMA.

**2.2 — The fallback drill, end to end.** Kill Scoring mid-contention → FCFS takes over → order flow
continues uninterrupted → Warning alert fires (Scoring down ⇒ FCFS, §12.9) → Scoring relaunches →
scores resume from persisted history (D1). The §6.6 degrade-and-recover path, measured whole.

**2.3 — The git-env gate holds across the wide fan-out.** Prove that across the five worktrees this
arc spawned and merged, no unscrubbed git call ran and the canonical tree's `core.bare` stayed
`false` throughout. The D3.205 class, proven closed under the exact condition (many parallel
worktrees) that triggered it.

**2.4 — State honestly what remains.** The Allocator's Scoring-dependent finish (recovery reflection,
full performance-weighting) is a later arc; live-venue untested by design; the EMA span is a default
awaiting real realized data to calibrate (§6.6 caution: early realized samples are thin). Say it in
the verdicts.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice, under both documented interpreters.
The Scoring process, its shared-memory ranking table, and the readers' mirrors are new resource
surfaces — fresh false-declaration candidates.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f). BOUND floor = ARC 035's figure; any
new check UNBOUND or ENR is a finding named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk, stating the interpreter. Baseline: `check_ibgateway_service` FAIL (tap
   session) + the standing cannot-measures. A further FAILURE is a finding; any further NON-PASS whose
   cause is not named is a finding. Name every GUARDED check and print its owner verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   **per D3.205/D3.22 every subprocess `git` call uses the `gitenv.py` scrub — now gated by 0.2.**
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; run any predicted post-write-back re-measure and BANK it BEFORE the marker
   (§0j); `cat` both as the final action; **prove HEAD advanced** (§0d); state the absolute canonical
   path.
6. Clean up temp files and all five worktrees/branches this arc created (prove `git worktree list`
   shows only `/home/bbt/nix`).
7. **Per §0j: `**** ARC completed ****` is the LAST token, printed once, nothing after it.** If a
   stable marker-last state can't be reached, report `STATUS: IN FLIGHT` and name what is moving.

**WAYPOINTS.** At kickoff echo the total stage count once; at the start of every phase/stage/sub-agent/
convergence step print a boxed banner — `ARC 036 · <Module>/<Stage> — STAGE <k>/<total>: <name>` + an
`~elapsed in · ~eta left` line — tagged `— PAUSED, awaiting operator` on any stop-for-ruling. Standing
rule; confirm it is recorded in `~/nix/CLAUDE.md`.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The Allocator's full Scoring-dependent finish (recovery reflection + complete performance-weighting —
a later arc; E proves consumption only) · the Gate 5/6/7 decision-point evaluator `strategy_score.py`
(offline promotion scorer — a different artifact, do not touch or conflate) · the dashboard's Panel C
rendering (auxiliary) · the strategy FSM (plug-in) · backup/DR · the tap session · changing branch
protection. Say the deferrals in the verdicts.

---

## Open items returned to the operator / architect

1. **The tap session** — console task, ~40 min, owed by twenty-three arcs. Discharges D1.12 reboot
   capture (ARMED, unfired — do not SSH within 5 min of reboot), D1.33, live rejection taxonomy,
   feed-lag, D1.39/D1.40, SPEC-A6 poll-lag, D1.50, both Gateway gates. Only code-independent FAIL.
2. **Push · SPEC-A10 vendor · branch protection · five-artifact provenance** (0.3) — operator/
   outward-facing.
3. **Backup/DR (`elements_v2.md` §4)** — gated safety property, peripherals-phase arc.
4. **v1.4 fold + D3.33** — amendments run to SPEC-A10; the v1.4 file lags; re-point every `§x:line`
   citation. Architect debt.
5. **After this arc: the Allocator's Scoring-dependent finish is the last dependency-locked infra
   step** → infra-100 → the ULTRAREVIEW pass (0/9 badges) → reference strategy + signal-parity gate →
   IBKR end-to-end.
