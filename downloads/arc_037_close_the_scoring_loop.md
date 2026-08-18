# ARC 037 — Close the Scoring Loop (realized-P&L feed · weighting · durable quarantine · Allocator finish)

**Module:** Plane-1 (realized-P&L write) + Scoring (weighting activation) + supervision (durable
quarantine) + Allocator (Scoring-dependent finish) — the wires between modules already built
**Predecessor:** ARC 036 (merged; Scoring engine + D3.205 git-env gate landed, HEAD post-`ec31401`)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking · Stage 1 **wide parallel fan-out (six disjoint sub-agents)** ·
Stage 2 serial integration (the closed loop, driven end to end) · Stage 3 convergence · Phase 4
close-out.

**Verifies:** turns ARC 036's dark Scoring engine into a live loop — records realized P&L, ranks it,
weights sizing on it, survives restart — and finishes the Allocator's Scoring-dependent half, the last
dependency-locked infra step before infra-100.

---

## WHAT CHANGES WITH THIS ARC

ARC 036 built every piece of the scoring loop and wired none of it to production. This arc is
**wiring, not building** — it closes six open seams, each a "built but not connected" gap that 036
measured and named honestly:

1. **D3.220 — nothing writes realized P&L to Plane-1.** The Scoring engine reads a figure the durable
   record does not carry. This is the keystone: without it, everything downstream ranks nothing.
2. **D3.260 — weighting is flat.** `NEUTRAL_WEIGHT=1.0` under both policies; ordering flips correctly
   but sizing is not yet performance-weighted.
3. **D3.263 — FCFS is the live policy** because no production writer publishes the ranking topic and
   no consumer holds it. The RANKED path exists only in gates.
4. **D3.250 / D3.251 — quarantine auto-resurrects.** `CrashLoopBreaker._quarantined` is in-process; a
   fresh breaker over the same ledger reports *not quarantined* (§4:274 says quarantine is not
   auto-resurrected), and `may_relaunch` returns a reason contradicting the ledger. Safety regression.
5. **D3.244 — the RANKED-from-a-corpse exposure.** A dead publisher's mirror stays "populated and
   confident"; 144,699 decisions were ranked from a frozen table over 0.483s. Staleness is detected;
   *liveness* is not — needs a liveness bound, not just a `stale_after_s`.
6. **The Allocator's Scoring-dependent finish** — performance-weighting live, recovery reflection
   complete — the last infra step gated on Scoring existing.

**The keystone ordering:** D3.220 (realized-P&L write) must land first in integration, because
weighting, the live RANKED path, and the Allocator finish all consume the figure it produces. Building
the consumers before the producer is the exact "built but uncalled" class this project keeps catching
— so Stage 1 builds them in parallel (they're disjoint), but Stage 2 drives the producer first and
proves each consumer against a *real* realized figure, not a fixture.

---

## §0a — Self-audit, this brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

This arc is all wiring, and wiring is where "green while measuring nothing" lives most densely: a
weight applied but never differing from 1.0, a realized figure written to a column nothing reads, a
quarantine made durable in a table supervision never consults, a liveness bound that never observes a
dead publisher. **Every seam this arc closes must be proven by a driven end-to-end effect, not by the
seam's existence.** Assume at least one of the six "fixes" lands as a wire to nowhere, and one hazard
stated backwards (036 alone had the realized-P&L source, the FCFS danger, and the shared-memory seam
all backwards — measure before relying).

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-artifact-drives-shipped-bytes-red · §0f explicit-status-or-owner, table-rebuilt · §0g owner-names-future-arc · §0h forward-only · §0i mirror-stale-until-proven-fresh · §0j marker-is-last-token (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

---

## PHASE 0 — Corrections, rulings, seam freeze (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 036's close: verify.py
`81 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded`, exit 1; pytest 3049; census 86
three ways; binding BOUND=74; CHECK-DEBT 250. **Any delta is a finding.** Name every FAIL and the
guard's owner (ARC 037 now owns `check_artifact_gate_coverage`, re-pointed at 036 close per D3.273 —
this arc must discharge or re-own it, not let it self-expire).

**0.2 — Carried integrator debt from ARC 036.**
- **D3.272 (open) — `check_derived_claims` is blind to a lost ledger row** (delete rows + re-derive
  count agree perfectly). Build the row-preservation gate: a merge/edit that drops a ledger row must
  redden, proven by planting a deletion and confirming the gate names the missing D-number. This is
  the class that silently cost fifteen rows in 036.
- **D3.271 — two `RankingReader` classes in one package; the instrument credits one's call sites to
  the other.** Disambiguate; prove the uncalled-entrypoint sweep attributes call sites to the correct
  class.

**0.3 — Carried operator rulings (report; act only where authorized).** Push (`main` now ~30+ ahead /
0 behind, clean FF — re-confirm, report, STOP; strongly worth doing this cycle after two clean
closes); SPEC-A10 vendor (UNRATIFIED); branch protection (drafted ruleset, operator applies).

**0.4 — Freeze three seams.** (a) The **realized-P&L event** on Plane-1 (which §12.10 row carries it,
computed where, written by the sole writer at which lifecycle transition — closed/protective-exit);
(b) the **weight function** seam (how a pair's rank becomes a sizing multiplier, bounded, with a
declared neutral point); (c) the **durable-quarantine** seam (the fsynced ledger supervision consults
on breaker construction). **Prove each seam gate reddens** on: a realized figure written but not read;
a weight that never differs from neutral; a quarantine durable in a table the breaker never queries.

---

## STAGE 1 — Wide parallel fan-out (SIX disjoint sub-agents)

Each from its own provisioned worktree + own git index + isolated venv (ARC 030 isolation). D3.192
holds and is now larger: six worktrees adding to shared package homes → up to five conflicts on shared
literals, resolved at merge against the merged tree. **The integrator audits the merged tree for
defects each blind branch was green over** — 036 Stage 2 caught the `sys.modules.clear()` gate that was
green while breaking four successors, and lost fifteen ledger rows in a conflict hunk. More parallelism
buys speed at the cost of merge-audit surface; the audit is not optional.

### SUB-AGENT A — The realized-P&L write (D3.220, the keystone)

**A1 — Compute realized P&L at trade close** (net of the modeled costs the sizing path already knows —
commission + fees + slippage, per §7), at the closed / protective-exit lifecycle transition, and write
it as a Plane-1 row via the **Limiter sole writer** (§9 — no new writer; the Limiter books it like
every other money-truth row). §0a: prove the figure is *realized* (closed trades only, never an open
mark — §6.6 locks this) by driving a position that goes green while open then closes red, and proving
the written figure is the close, not the peak.

**A2 — Prove Scoring can now read it.** The engine A-built in 036 reads realized P&L from Plane-1;
drive a real close and prove the EMA advances off the written row, not a fixture. This is the wire
D3.220 named missing.

### SUB-AGENT B — Weighting activation (D3.260)

**B1 — Rank → sizing multiplier.** Replace `NEUTRAL_WEIGHT=1.0`-always with the real weight function
frozen in 0.4: a higher-ranked pair sizes up (within bounds), a lower-ranked pair sizes down, neutral
at the declared point (cold-start / absent score → weight 1.0, preserving FCFS neutrality). §0a: prove
the weight *differs from 1.0 under real ranking* — a weighting test where every weight is 1.0 passes
while changing nothing (the D3.260 shape exactly). Drive two ranked pairs and prove distinct sizes.

**B2 — Bounds are real.** The multiplier is clamped (no unbounded upsizing off a thin early sample —
§6.6 cautions early realized samples are thin). Prove the clamp binds by driving an extreme rank.

### SUB-AGENT C — Durable quarantine (D3.250 / D3.251, safety regression)

**C1 — Quarantine survives breaker reconstruction.** Move `_quarantined` and the restore counter from
in-process dicts to the fsynced ledger supervision already writes. A NEW `CrashLoopBreaker` over the
same ledger must report the strategy STILL quarantined (§4:274 — not auto-resurrected). §0a: prove by
constructing a fresh breaker over a ledger with a quarantined strategy and confirming `may_relaunch`
refuses with a reason that *agrees* with the ledger (D3.250 was the reason contradicting the ledger).

**C2 — Restore is durable too.** The §12.11 quarantine-restore verb (restart-to-flat, score rows
return, counter reset) must persist across breaker reconstruction — prove the counter reset survives,
not just the quarantine flag.

### SUB-AGENT D — Mirror liveness bound (D3.244)

**D1 — A dead publisher's mirror must go UNRANKED, not stay confident.** Staleness (age) is detected;
liveness (is the writer alive?) is not. Add a liveness signal — a publisher heartbeat/sequence the
mirror tracks — so that a mirror whose writer is dead falls to FCFS *promptly*, bounding the
"RANKED-from-a-corpse" window rather than letting it scale with `stale_after_s`. §0a: prove by killing
the publisher and measuring the count of RANKED decisions AFTER the kill drops to a bounded small
number (not the 144,699/0.483s of 036), and that order flow still never halts (the FCFS invariant
holds — liveness makes it fall back *sooner*, never fail).

### SUB-AGENT E — The Allocator's Scoring-dependent finish

**E1 — Performance-weighting live** — the Allocator's sizing now consumes B's weight in production, not
just the ordering flip 036 proved. Drive the full sizing path with real ranks and prove sizes reflect
performance, then prove FCFS-neutral sizing when Scoring is down (weight → 1.0).

**E2 — Recovery reflection complete (§4).** The remaining Allocator lifecycle-reflection work: a
strategy mid-recovery reads in-flight-closing, and now also reflects quarantine/restore state (C) and
score-persistence (036 D) correctly through the mirror. Prove through a real death→recovery→restore
cycle, not injected state.

### SUB-AGENT F — Row-preservation gate + instrument debt

**F1 — Build the D3.272 row-preservation gate** from 0.2 (a dropped ledger row must redden).
**F2 — The uncalled-entrypoint sweep** (standing) over this arc's new wires: every seam closed here
must have a real caller on both ends — the realized-P&L writer is called at close, the weight is read
by the Allocator, the durable quarantine is consulted by the breaker, the liveness bound is observed by
the mirror. A wire built but not called is the exact class this arc exists to close, so the sweep is
load-bearing here.
**F3 — CHECK-DEBT reconciliation** with the derived-vs-narrated arithmetic gate (D3.82).

---

## STAGE 2 — Integration: the closed loop, driven end to end (SERIAL)

**2.1 — The keystone first.** Drive a real trade to close → realized P&L computed and written to
Plane-1 by the sole writer → Scoring's EMA advances off the written row. Prove the producer feeds the
consumer with a real figure. Everything below depends on this, so it runs first.

**2.2 — The loop closes.** Two strategies accumulate real realized history → Scoring ranks the pairs →
the Allocator weights sizing on the rank (distinct sizes, B) → a contention is arbitrated by the live
RANKED path (not FCFS) → the outcome books its Plane-1 rows. The full `realized P&L → rank → weight →
size → outcome` circuit, driven, with no fixture standing in for the realized figure.

**2.3 — The loop survives death.** Kill Scoring → FCFS takes over promptly via the liveness bound (D,
bounded RANKED-from-corpse window) → order flow continues → Scoring relaunches → scores resume from
persisted history (036 D1) → weighting re-engages. Then a strategy crash-loops → quarantined durably
(C) → survives a supervision restart → restore returns its rows and resets its counter. The §6.6 + §4
degrade-and-recover paths, measured whole against real processes.

**2.4 — State honestly what remains.** Live-venue untested by design; the EMA span is a default
awaiting real realized data to calibrate (§6.6); the reference strategy driving these trades is a test
harness, not the production plug-in. Say it in the verdicts.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice, under both documented interpreters.
The realized-P&L writer, the weight function, the durable-quarantine ledger, and the liveness heartbeat
are new resource surfaces — fresh false-declaration candidates.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f). BOUND floor = ARC 036's 74; any new
check UNBOUND or ENR is a finding named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk, stating the interpreter. Baseline: `check_ibgateway_service` FAIL (tap
   session) + `check_uncalled_entry_points` standing state + the standing cannot-measures. A further
   FAILURE is a finding; any further NON-PASS whose cause is not named is a finding. Name every GUARDED
   check and print its owner verbatim; discharge or re-own `check_artifact_gate_coverage` (0.1).
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 ignore rules resolve per target first; per
   D3.205/D3.22 every subprocess `git` call uses the `gitenv.py` scrub (now gated).
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; run any predicted post-write-back re-measure and BANK it BEFORE the marker
   (§0j); `cat` both as the final action; **prove HEAD advanced** (§0d); state the absolute canonical
   path.
6. Clean up temp files and all six worktrees/branches (prove `git worktree list` shows only
   `/home/bbt/nix`).
7. **Per §0j: `**** ARC completed ****` is the LAST token, printed once, nothing after it.** If a
   stable marker-last state can't be reached, report `STATUS: IN FLIGHT` and name what is moving.

**WAYPOINTS.** At kickoff echo the total stage count once; at the start of every phase/stage/sub-agent/
convergence step print a boxed banner — `ARC 037 · <Module>/<Stage> — STAGE <k>/<total>: <name>` + an
`~elapsed in · ~eta left` line — tagged `— PAUSED, awaiting operator` on any stop-for-ruling. Standing
rule; confirm it is recorded in `~/nix/CLAUDE.md`.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The dashboard's Panel C rendering (auxiliary) · the Gate 5/6/7 decision-point evaluator
`strategy_score.py` (offline promotion scorer — do not conflate with the runtime EMA) · the strategy
FSM (plug-in) · backup/DR · the tap session · changing branch protection · calibrating the EMA span
(needs real realized data). Say the deferrals in the verdicts.

---

## Open items returned to the operator / architect

1. **The tap session** — console task, ~40 min, owed by twenty-four arcs. Discharges D1.12 reboot
   capture (ARMED, unfired — do not SSH within 5 min of reboot), the live rejection taxonomy, feed-lag,
   SPEC-A6 poll-lag, both Gateway gates. Only code-independent FAIL.
2. **Push · SPEC-A10 vendor · branch protection** (0.3) — operator/outward-facing.
3. **Backup/DR (`elements_v2.md` §4)** — gated safety property, peripherals-phase arc.
4. **v1.4 fold + D3.33** — the v1.4 file lags the amendment run; re-point every `§x:line` citation.
5. **After this arc: infra-100 is in reach.** With the scoring loop closed and the Allocator finished,
   every core module is code+debug+sim complete — then the **ULTRAREVIEW pass** (one deep-audit arc per
   module, 0/9 → flipping badges green), then the **reference strategy + signal-parity gate**, then
   **IBKR end-to-end**. This is the last major infra build; what follows is audit and validation.
