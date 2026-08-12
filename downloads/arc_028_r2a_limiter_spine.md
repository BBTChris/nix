# ARC 028 — R2-A: The Limiter Spine

**Module:** Risk Engine / Limiter (Core 2) — first product arc on the safety spine
**Predecessor:** ARC 027 (merged)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** mega arc. Phase 0 serial and blocking · Stage 1 four parallel sub-agents · Stage 2 serial
(depends on Stage 1) · Stage 3 convergence · Phase 4 close-out.

---

## WHAT CHANGES WITH THIS ARC

Every arc to date built instruments, or built libraries that talk to a broker. **This arc writes the
code that decides whether an order exists at all.** The Limiter is the firewall and the exit brake
(§10, Core 2), the sole writer of financial truth (§9), and the only thing standing between a
strategy's intent and the venue. Nothing reaches the broker without it (§12.5).

The standing correctness→reliability→optimization order applies with no exceptions, and the
vacuous-pass doctrine matters more here than anywhere it has been applied so far: **a gate that
approves because it never evaluated is indistinguishable, in output, from a gate that approved
correctly.**

---

## §0a — Self-audit clause (standing)

*What would have to be true for this step to complete successfully while measuring nothing?* Any step
whose success is compatible with measuring nothing is a defect in this brief. Report it; do not
silently satisfy it.

**Precedent, ARC 027:** the architect's §0a warning to sub-agent D was **inverted** — a same-order
observer pair was called useless, and measurement showed it produces 12 spurious findings out of 23
claims and is the baseline that makes the detector work at all. **Assume this brief contains at least
one instruction whose premise is false, and at least one whose stated hazard runs backwards.**

## §0b — Architect spellings are non-binding (standing)

Spellings are sketches; invariants bind. Refuse with a measurement anything that would degrade an
instrument, blind a gate, delete its own subject, or make a check report over a subject it never
drove.

## §0c — WITHDRAWN (ratified, ARC 027 finding 0.3)

Binding no longer turns on a declaration-only classification. `contract.py` sits on every check's
verdict path and changed in three consecutive arcs, so the rule's output was a constant, and a rule
whose output is a constant decides nothing. **Do not restore it.** `measurement_path.py` is retained
as a *structural* instrument — it is what proved the finding.

## §0d — Proof of write is not proof of durability (standing)

The write-back gate proves HEAD advanced and contains this arc's paths.

## §0e — Binding requires a committed, runnable artifact (standing)

Observed driving the **shipped** gate's own bytes to a failing status. A control sha in a results
document is not one.

## §0f — An unclaimed binding attracts no audit (standing)

Every check carries an explicit status with a named artifact or a named owner. No unstated third
category. The binding table is rebuilt from measured evidence every arc, never carried forward.

## §0g — A guard's owner names a FUTURE arc (NEW, ARC 027 D3.40)

Three individually correct rules collided: ARC 026 pointed an owner at ARC 027; `completed_arcs`
derives completion from `##` headings in `SESSION.md`; every close-out writes one. **The guard died
the instant the arc that owned it banked itself.**

Standing: an owner names an arc that can still discharge it, **validated at assignment, not only at
read.** Assigning an owner to the arc in flight is rejected at write time.

---

## PHASE 0 — Corrections and the frozen seam (SERIAL, BLOCKING)

**0.1 — Re-measure.** `verify.py`, pytest, pre-commit, claims, CHECK-DEBT, census, binding table
against the canonical tree. Expect ARC 027's close: `20 passed | 1 failed | 3 cannot measure |
0 skipped | 0 guarded`, exit 1; pytest 957 + 1 skipped + 2 xfailed; pre-commit 8/8; claims 13/13 with
2/2 demonstrations; CHECK-DEBT 104 derived; census 24 three ways; 23 BOUND + 1
BOUND-BY-MODIFIED-GATE. **Any delta is a finding.**

**0.2 — A stated figure contradicts its own derivation, inside ARC 027's results.** The debt section
reads `77 → 103 (+26)` while stating *thirty opened, three discharged*; that is **+27**, and
`77 + 27 = 104`, which is what the derived figure says two hundred lines earlier. **Both numbers in
that header are wrong.** This is the exact class sub-agent D swept for in the same arc — a figure
narrated rather than derived — appearing in the document that reported the sweep. Correct the
narrated figure, and report whether the D2 auditor's scope covers `RESULTS.md` headers; if it does
not, that is the finding.

**0.3 — §0c withdrawal to disk.** Amend the check contract, the ledger, and `CLAUDE.md`. The rule is
withdrawn, not narrowed. Record the measured grounds, not the conclusion alone.

**0.4 — Amendment numbering (architect ruling).** Disk is authority: per-channel freshness is
**AMENDMENT 6** in `SPEC-AMENDMENTS.md`; the architect has been saying 5 and will use 6. Two fixes:
a **uniqueness gate inside each ledger** (ARC 022's `AMENDMENT 5 (D1.38)` and per-channel freshness
were both issued as 5 in the same document), and a **ledger prefix** — `SPEC-A6` / `CHECK-A6` — since
"Amendment 6" is currently ambiguous across two documents that each hold six.

**0.5 — D3.40, the expired guard (architect ruling).** Do **not** raise the ceiling and do **not**
re-point `owner` at ARC 028 — that is the forbidden move and the ceiling is working.

The defect is that **one guard covers sixteen artifacts**: one owner, one ceiling, sixteen unrelated
debts, so the ceiling is blunt by construction. **Decompose** — each uncovered artifact gets its own
row, its own owner, and its own ceiling. Then re-owning means something per item, and the two
artifacts covered by nothing at all (`databases/schema/extract_sources.py`,
`scripts/d1_12_reboot_capture.py`) stop hiding inside an aggregate. Until an artifact is genuinely
measured, CANNOT_MEASURE is the honest verdict — **do not force it green.**

**0.6 — Freeze the seam.** Stage 1's sub-agents are disjoint only if the interfaces between gate,
reservation ledger, and financial picture are settled first. Land the type/port declarations, and
nothing else, before Stage 1 dispatches. Per §2A precedent, declare which verbs are synchronous and
which are asynchronous, and state the reasoning.

---

## STAGE 1 — Four parallel sub-agents

### SUB-AGENT A — The two-phase gate pass (§3, §11)

**A1 — Phase ordering is an invariant, not an implementation detail.** §3 locks one authoritative
pass: **Phase A, size-INDEPENDENT rules first** (global HALT flag branch 0 · EOD/EOW/news-margin/
roll-day blackouts · session boundary · post-open warmup · stale-data halt · clock-skew halt ·
one-in-flight-per-strategy lock), **then Phase B, size-DEPENDENT** (committed = Σ open margin +
Σ pending reservations · committed + proposed < 70% × balance · survival headroom leaves the floor
intact per §6.5 · buffer/deployable ceiling fit).

**§0a on this item, and it is the sharpest in the arc:** a gate that reads source order proves
nothing about execution order. **Prove by observation that no size-dependent rule evaluates once a
size-independent rule has denied** — a Phase-B rule that runs after a Phase-A denial is a correctness
defect that produces identical output.

**A2 — Deny names the rule, fail-fast (§3).** Every denial carries the specific rule that denied it.
A denial with a generic reason is a denial the operator cannot act on and the event log cannot
reconstruct.

**A3 — Hot-path discipline (§11).** The entry pathway is cache reads and arithmetic only. HALT is the
**first atomic read** in the pre-gate. Tradability is O(1). Aggregates are maintained incrementally,
never computed in the pass.

**§0a:** a latency gate passes trivially if the pass never ran, and an O(1) claim is unfalsifiable
without a shape measurement across input sizes.

**A4 — Gate it.** Prove real effective behaviour: the ordering, the named denial, and the first-read
HALT.

### SUB-AGENT B — The reservation lifecycle (§3)

**B1 — The state machine.** `taken at approval → released on: fill (converts to open-margin), cancel,
reject, pending-timeout resolution, blackout-onset cancellation.` §3 states the invariant plainly:
**no leak paths.**

**B2 — Enumerate terminal paths from the SPEC, not from the implementation.** Deriving the path set
from the code and then proving the code releases on every path in that set is circular and will pass
while measuring nothing. The spec's list is the authority; if the implementation has a terminal path
the spec does not name, that is a **finding about the spec**, reported, not silently added.

**B3 — Both directions.** A leaked reservation permanently reduces deployable capital and eventually
blocks all trading. A **double release** under-counts committed margin and lets the system
over-commit — the more dangerous of the two, and the one a naive leak test does not see.

**B4 — Gate it**, with plants for both directions.

### SUB-AGENT C — Instrument debt

**C1 — `check_derived_claims`, the last unbound thing.** BOUND-BY-MODIFIED-GATE: its four reds come
only from a gate whose source differs from what ships, because the plants substitute into the gate's
own derivation. Needs a control that drives the **shipped bytes** red by perturbing a SUBJECT.

**C2 — Apply 0.5's decomposition** to the coverage baseline; give the two zero-coverage artifacts
real coverage or honest per-artifact owners.

**C3 — D3.29/D3.30**, `check_hook_suite` arms 3–4. Arm 4's defect branch is unreachable by any plant
because `_probe_payload` consults `_environments_all_present` first, so zero hooks becomes a vacuity
complaint one layer up. That is a reachability defect costing the operator the site name — repair the
reachability, then plant it.

**C4 — D3.39**, the control that reddens under wall-clock load. Characterised, not averaged over. The
property is real — without `XPUB_VERBOSE` libzmq delivers only the first subscribe for a topic, so a
second dashboard mirrors an empty table forever, which looks exactly like a quiet feed. **A control
that reddens under load teaches the operator to disbelieve it**, so fix the budget, not the
assertion.

### SUB-AGENT D — `risks/` as data, never a second authority

`directory_structure.md` pins `risks/` as *"data-role expression of the risk spec + §12A knobs; never
a second behavioral authority."*

**D1 — Land the §12A knobs as data**, with the behavioural rules staying in the Limiter's code.

**D2 — Gate the boundary.** The failure mode is specific and this project has seen its shape before:
a rules library that begins as data and accrues behaviour becomes a second authority that can
disagree with the spec, and the disagreement is silent. Prove that `risks/` contains no behaviour.

**D3 — Config is boot-loaded, restart-only** (§12.11) — no hot-reload, config version stamped into
the boot event.

---

## STAGE 2 — The financial picture and Plane 1 (SERIAL, depends on Stage 1)

**2.1 — ONE atomic snapshot (§3, v1.3, and the atomicity rule is the point).** The Limiter publishes
balance, per-position rows keyed by `trade_id` (symbol, strategy_id, size, margin, state), live
per-symbol current margin, Σ open margin, Σ reservations, committed, and deployable — **as one
snapshot with one version stamp**, never two reads.

§3's stated reason: so the Allocator can never compute headroom off a stale balance and a fresh
commitment, or the reverse. **§0a: atomicity is unfalsifiable without concurrency.** A publisher
observed only by a reader that never races it proves nothing.

**2.2 — Transport is the existing state bus** (§12.7): ZeroMQ PUB/SUB, mirror model,
**snapshot-on-subscribe mandatory, not polish**. Built and gated in ARC 026; ARC 027's `XPUB_VERBOSE`
finding applies directly — a mirror that misses its snapshot looks exactly like a quiet feed. A
consumer's mirror that is incomplete is treated as **stale ⇒ fast-drop/deny until the snapshot
lands**, never sized on.

**2.3 — Plane-1 WAL seam (§9).** `enqueue → durable local WAL → shared-pool writer → group-commit to
Postgres`, off the hot path. **The Limiter is the sole writer; no new writers, ever.**

Scope: land the WAL and the group-commit seam. Full Postgres schema integration and cold-start
reconciliation are **not** in this arc — say so in the verdicts rather than implying coverage.

**§0a:** a WAL is durable only if it fsyncs; a durability gate passes trivially against a write that
never left the page cache, and a crash-gap test that never crashes measures nothing.

**2.4 — Degraded persistence ≠ degraded trading (§12.4).** Postgres outage ⇒ WAL buffers, trading
continues, operator alerted. Disk-critical ⇒ HALT new entries. Open positions stay protected because
stops read memory, not disk. Gate the distinction; it is the difference between a bad afternoon and a
stopped business.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in at least three orders on a cold cache. Every check added this arc is a fresh
candidate for a false declaration; the Limiter's gates touch shared memory, ZMQ and the filesystem
and are the most likely to under-declare.
**3.3** Census three ways.
**3.4** The binding table, rebuilt from measured observations (§0f). Not carried forward.

---

## PHASE 4 — Close-out

1. `verify.py` under the regenerated plan. Baseline: `check_ibgateway_service` FAIL +
   `check_ibgateway_config` cannot-measure + `check_observed_resource_claims` cannot-measure +
   `check_artifact_gate_coverage` cannot-measure (D3.40, until 0.5's decomposition lands). A further
   FAILURE is a finding, and so is any further NON-PASS whose cause is not named. Name every GUARDED
   check and print its owner verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   per D3.22 use the `gitenv.py` scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; `cat` both as the final action; **prove HEAD advanced** (§0d); state the
   absolute canonical path.
6. Clean up temp files.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

Stop conversion and trailing maintenance (§4 — needs the GO contract and fills) · protective-exit
wiring to broker-order · session-close flatten (R4) · full HALT semantics and auto-clear · cold-start
reconciliation · the Sentinel · Scoring and the ranking table · the Allocator.

**Say so in the verdicts.** A Limiter that gates but cannot exit is not a safety spine yet, and the
gates must not imply otherwise.

---

## Open items returned to the operator / architect

1. **The tap session** — operator task at the console, ~40 min, **owed by eleven arcs**. Discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement,
   D1.39/D1.40, AMENDMENT 6's poll-channel lag figure, D1.50. **It is the only FAIL in `verify.py`
   and it is a switch.** It owes the two Gateway gates' *green*, not their can-fails — those are
   committed and measured BOUND.
2. **§13 objective 24 cannot close until the Risk Engine exists** (D1.47). This arc is the first
   instalment of that dependency; V24 still needs the order path, which arrives with the
   protective-exit wiring in a later R2 arc.
3. **v1.4 exists and is deliberately not authority** (D3.33) — promoting it moves every `§x:line`
   coordinate the governed roots cite. Architect debt.
4. **`attribution_drift.py` stays a harness** (D3.36) — registering it nests six 32-second sweeps
   inside a 60-second per-check timeout, which is permanently CANNOT_MEASURE. Concurred.
