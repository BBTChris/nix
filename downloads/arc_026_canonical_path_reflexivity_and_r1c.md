# ARC 026 — Canonical Path, Reflexivity, and R1-C

**Module:** checks subsystem (instrument half) + capture.py / §2A transport (product half)
**Predecessor:** ARC 025 (merged, `0f9c5b9`)
**Shape:** mega arc. Phase 0 serial and blocking · Stage 1 three parallel sub-agents ·
Stage 2 serial convergence · Phase 3 close-out.

**Standing note:** four consecutive arcs (022–025) have been instrument work. This arc is
deliberately split — sub-agents A and B discharge the debt ARC 025 created, sub-agent C is the first
product movement since ARC 021. That split is the point of the arc's shape, not an accident of
scheduling.

---

## §0a — Self-audit clause (standing)

Before acting on any instruction here, ask: *what would have to be true for this step to complete
successfully while measuring nothing?* Any step whose success is compatible with measuring nothing is
a defect in this brief. Report it; do not silently satisfy it.

**Precedent, ARC 025:** Stage 2.2's criteria — derive, zero cycles, zero orphans, propose, require
`--commit` — were *all* satisfiable by a plan in which a failed Python runtime no longer halts the
run. The architect wrote success criteria a broken plan could meet. Assume this brief contains at
least one more.

## §0b — Architect spellings are non-binding (standing)

Spellings are sketches; invariants bind. If implementing a spelling as written would degrade an
instrument, blind a gate, or make a check report over a subject it never drove, **refuse it with a
measurement**, implement the invariant another way, record the substitution.

## §0c — Binding survives on the measurement path (RATIFIED, ARC 025 finding 5)

A retrofitted check loses its D3.10 binding when its **measurement path** changes — not when its file
mtime changes. Declaration-only edits with `run()` provably untouched preserve binding.

**Condition of ratification (new, this arc):** the AST classifier that decides "declaration-only" is
now load-bearing for every binding claim in the system. **It must be bound itself.** Apply the
standing question to it: what would have to be true for it to report *declaration-only* while `run()`
changed? Plant that case, prove it fails. Until then no binding that rests on it is trustworthy.

## §0d — Proof of write is not proof of durability (standing, ARC 024 Amendment 4)

The write-back gate proves HEAD advanced and contains this arc's paths. Not mtime. Not size.

## §0e — Proof of measurement is not proof of durable measurement (NEW, this arc)

ARC 025 re-bound four gates with control shas matching either side, two matching banked ARC 023
figures exactly — and committed **zero test files**. Four bindings exist only as prose in
`RESULTS.md`. That is §0d one layer down.

**Standing from this arc: a binding claim requires a committed, runnable artifact that reproduces the
can-fail.** A control sha in a results document is evidence a measurement happened, not an instrument
anyone can re-run. Recorded as D2.30.

---

## PHASE 0 — Canonical path (SERIAL, BLOCKING)

`~/nix` is a **bare** repository. The real tree is a per-arc integration worktree. Beside the bare
repo sits a full **untracked shadow tree** — `checks/`, `scripts/`, `downloads/`, `sessions/` — frozen
at 2026-08-11 23:55 (ARC 024's close-out), invisible to every gate, at the path every standing arc
rule names. `~/nix/scripts/verify.py` is ARC 024's `verify.py` and will run if anything resolves it.

This is the seventh instance of *git tracking state sets gate scope*, and the first one at the
canonical path.

**0.1 — Establish provenance BEFORE deleting anything.** When and why did `~/nix` become bare? What
created the shadow tree? **Report and stop if the answer is not clear from reflog, script, or
history.** If the bare conversion was deliberate there may be a reason the shadow tree exists, and
this brief does not know it.

**0.2 — Prove the shadow tree holds nothing unique.** For every file beneath the shadow tree, prove
its content exists in history or in the live worktree. **Any file that does not is a finding** —
report it, do not delete it, do not merge it.

**0.3 — Delete the shadow tree**, only after 0.1 and 0.2 both clear.

**0.4 — Establish a stable canonical path.** Integration worktrees are per-arc; standing rules cannot
chase them. Provide a fixed path — a `~/nix-wt` symlink repointed per arc, or a fixed `~/nix-work` —
and update every standing rule that names `~/nix/...` to name it.

**[ARCHITECT RULING — revocable]** The write-back path becomes `<canonical>/downloads/RESULTS.md` and
`<canonical>/sessions/SESSION.md`. The operator has been reading a frozen `~/nix/downloads/RESULTS.md`
for three uploads because the rule named a dead file.

**0.5 — Gate it.** `check_canonical_tree.py`: no untracked working files beside the bare repo; the
canonical path resolves to a live worktree; `verify.py` resolves to exactly one location. Ships with
a demonstrated FAIL path — plant a shadow file, prove exit 1 naming it.

**0.6 — Re-measure.** `verify.py`, pytest, pre-commit, claims harness, CHECK-DEBT against the
canonical tree. Expect ARC 025's close: `11 passed | 1 failed | 2 cannot measure | 0 skipped |
1 guarded`, exit 1; pytest 520 + 1 skipped + 2 xfailed; pre-commit 8/8; claims 13/13 with 2/2
demonstrations; CHECK-DEBT 68; census 15 three ways. **Any delta is a finding.**

---

## STAGE 1 — Three parallel sub-agents

File sets disjoint by construction. **None regenerates the execution plan** — that is Stage 2.

### SUB-AGENT A — Reflexivity and durable bindings

**A1 — B3, the deepest finding in ARC 025.** For **10 of `check_derived_claims`'s 13 claims, both
sources are probes inside the gate itself**, invoked as `{self} --probe`. Exactly one source
(`pytest_collector`) is genuinely independent, and it is the only reason the architect's ARC 025
requirement could be satisfied at all. There is no `test_check_derived_claims.py` and no hook runs it
(D2.22).

The instrument that verifies every claim in the system is mostly verifying itself. A defect in a
shared helper moves both sides of a comparison together and the gate stays green.

**Requirement (invariant, not spelling):** each claim's two sources must be able to fail
independently. Implement either a companion suite that drives the gate externally, or a second
externally-implemented source per claim. **Prove independence by measurement:** plant a defect in a
shared helper and demonstrate the comparison still discriminates. If a claim cannot be given an
independent second source, **say so per claim and mark it** — a claim whose two sources cannot
disagree is not a verified claim, and listing them honestly beats implying thirteen.

**A2 — D2.30, the four prose-only bindings.** `check_datafeed_granted_mode`,
`check_datafeed_bar_seal`, `check_derived_claims`, plus the ARC 025 re-bindings. Ship committed,
runnable artifacts that reproduce each can-fail. Per §0e, a binding without one reverts to UNBOUND.
**Four honest UNBOUND rows beat four green rows resting on prose.**

**A3 — Bind the §0c AST classifier** per the ratification condition above.

### SUB-AGENT B — The two rulings and the contaminated metric

**B1 — Purge the manifest vocabulary (operator ruling).** The file stays `registry.json`. The
identifiers go: `manifest_version`, `nixverify/manifest.py`, `ManifestError`, `load_manifest()`,
`--manifest`. ARC 010 renamed the file and stopped; two names for one thing, one layer apart, is the
`ORDERS_OPEN` and `avg_price` class.

Gate it: zero occurrences of manifest-as-identifier outside `docs/CHECK-CONTRACT-AMENDMENTS.md` and
the historical ledger rows.

**B2 — `guard_owner` must name a *dischargeable* arc.** Third iteration of one flaw:
ARC 024 wrote a range (`"ARC 025+"`), which passed the non-empty test. ARC 025 constrained it to a
single identifier — and set it to `'ARC 025'`, **an arc that has now completed while the guard is
still live**. `guard_owner_defect` validates shape, not dischargeability. Add the predicate: the named
arc must not have completed. A guard pointing at history is a known-red marker with no owner.

**B3 — `CHECK-DEBT.md` owning-module column.** Third contamination of
`broker_order_open_debt_rows`, and ARC 025 named the residual precisely: rows are selected on prose
anywhere in the row, so a fourth is possible. The structural close is an owning-module column,
authored per row, never inferred from prose.

ARC 025's finding is worth restating because it is the sharpest example the project has produced:
D1.41 entered the metric because `socket.connect` contains the word *connect* — **the spy that took
ARC 024's measurement contaminated the metric measuring it.**

**B4 — D3.22.** `pre-commit` exports `GIT_INDEX_FILE`, and `git` honours `GIT_DIR`/`GIT_INDEX_FILE`
**ahead of `-C`**. It damaged a sub-agent's own worktree index in ARC 025 before the cause was found.
Repaired in `check_artifact_gate_coverage`; `check_hook_suite` still exposed. Sweep every subprocess
`git` invocation in the check population, not just the two known sites.

### SUB-AGENT C — R1-C, first product movement since ARC 021

Unblocked by ARC 023's Amendment 5 (per-channel freshness), which resolved F21.

**C1 — Process and core map for `capture.py`.** Core 0 OS · Core 1 `capture.py`/broker-datafeed ·
Core 2 Risk Engine/Limiter/broker-order · Core 3 Allocator+strategies · Cores 4–5 shared pool.
Establish the map as verified running state, not configuration intent.

**C2 — ZeroMQ `ipc://` PUB/SUB with snapshot-on-subscribe** for state tables, per §2A transport.

**C3 — The SPSC price firehose ring buffer**, the sole shared-memory exception in the architecture.
Everything else goes over ZMQ. Treat that exception as narrow and prove nothing else uses shared
memory.

**C4 — Gate each of the three** per the standing check-script rule. **Apply §0a hard here:** a
transport gate that passes because no message was ever published, and a core-affinity gate that reads
configuration rather than the running process's actual affinity mask, are the obvious vacuous passes.
Prove real effective state.

**C5 — Amendment 5 obligation.** Per-channel freshness makes §12.10's feed-staleness-transition
events per-channel. `capture.py` is a **process**, so unlike the broker libraries it owes Plane-2
emission directly. Use ARC 024's `SysLogHandler` emitter. Plane 2 never lands in `logs/`;
`capture.py` never writes Plane 1 — the Limiter is the sole Plane-1 writer and it does not exist yet.

---

## STAGE 2 — Convergence (SERIAL)

**2.1 — Regenerate the plan.** `--optimize` with the new checks declared. Report the diff against the
installed plan.

**2.2 — Run under the observer.** ARC 025's headline was seven false declarations on a plan that
passed static validation with zero errors. **Every check added in this arc is a fresh candidate for
the same defect** — including C4's transport gates, which will touch sockets and shared memory and
are the most likely to under-declare.

**2.3 — Census three ways.** Executed == planned == on disk.

**2.4 — Full binding table.** Every check: BOUND / UNBOUND / PARTIAL / GUARDED / RETIRED, with an
owner for every non-BOUND row, and — per §0e — the **committed artifact** backing each BOUND claim.
A BOUND row with no artifact is an UNBOUND row that has not admitted it yet.

---

## PHASE 3 — Close-out

1. `verify.py` under the regenerated plan. Baseline: `check_ibgateway_service` FAIL +
   `check_ibgateway_config` cannot-measure + `check_observed_resource_claims` cannot-measure (masked
   hazard, Gateway down). A further FAILURE is a finding, and so is any further NON-PASS whose cause
   is not named. **Name every GUARDED check and print `guard_owner` verbatim.**
2. Full pytest, pre-commit, claims harness, CHECK-DEBT with B3's owning-module series shown beside the
   old one.
3. The §2.4 binding table.
4. `git add -A` before every gate measurement — per D2.24 prove ignore rules resolve per target
   first; do not stage a `state/` symlink into the 0600 credential dir.
5. Write-back, to the **canonical path established in Phase 0.4**:
   - Append arc summary to the END of `<canonical>/sessions/SESSION.md`
   - **Overwrite** `<canonical>/downloads/RESULTS.md`
   - `cat` both as the final action, paste into the response
   - **Prove HEAD advanced and contains this arc's paths** (§0d)
   - **State the absolute canonical path in the results**, so the operator is not reading a frozen
     file at a stale location for a fourth time
6. Clean up temp files.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Open items returned to the operator

1. **The tap session** — operator task at the console, ~40 min, now owed by seven arcs. Discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33 marketDataType, the live rejection taxonomy, feed-lag
   re-measurement, D1.39/D1.40, Amendment 5's poll-channel lag figure, and Wave C's two UNBOUND
   Gateway gates. Plausibly the first `verify.py` exit 0. The runbook is written and unrun.
2. **`check_hook_suite` arms 3/4** remain UNBOUND, owner D3.14, unassigned. Planting them means
   editing `.pre-commit-config.yaml` or perturbing the shared store.
3. **D3.21** — evidence contradicting its own verdict. `_drive_seal` returns a fixed note claiming
   *"value equality holds"* even when the equality defect fired. Correctly left alone inside arm 4,
   D3.15's discharged subject. Needs an owner.
4. **The §16 write-back check and §18 control auditor** are owed and unwritten (D2.29).
5. **Spec v1.4** folding Amendments 1–5 into the frozen document — architect debt, still owed.
