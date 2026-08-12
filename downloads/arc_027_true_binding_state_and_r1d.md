# ARC 027 — The True Binding State, the Unbound Four, and R1-D

**Module:** checks subsystem + §2A capture/datafeed (product half) + frozen spec fold
**Predecessor:** ARC 026 (merged)
**Canonical path:** `/home/bbt/nix` — repaired in ARC 026, served by Samba `[nix]`, the path every
standing rule already names. **Do not relocate it. Do not delete anything beside it.**
**Shape:** mega arc. Phase 0 serial and blocking · Stage 1 four parallel sub-agents · Stage 2 serial
convergence · Phase 3 close-out.

---

## §0a — Self-audit clause (standing)

Before acting on any instruction here, ask: *what would have to be true for this step to complete
successfully while measuring nothing?* Any step whose success is compatible with measuring nothing is
a defect in this brief. Report it; do not silently satisfy it.

**Precedent, ARC 026 — the architect's worst brief defect to date.** Phase 0 ordered the deletion of a
"shadow tree" that was in fact the original working tree, orphaned when `core.bare` flipped
accidentally mid-ARC-025. Executing it would have destroyed the only copy of the brief being executed
and the operator's live Samba share. The framing was wrong, not merely the instruction. **Assume this
brief contains at least one instruction whose premise is false.**

## §0b — Architect spellings are non-binding (standing)

Spellings are sketches; invariants bind. If implementing a spelling as written would degrade an
instrument, blind a gate, delete its own subject, or make a check report over a subject it never
drove, **refuse it with a measurement**, implement the invariant another way, record the substitution.

ARC 026 refused three spellings correctly: `XPUB` over `PUB` (a `zmq.PUB` socket cannot do
snapshot-on-subscribe — subscriptions never reach the application), the `check_canonical_tree`
predicate that its own remedy deletes, and `git check-ignore` as an exclusion mechanism inside the arc
whose purpose was to stop filtering gate scope on tracking state.

## §0c — SUSPENDED PENDING PHASE 0 (architect withdrawal)

ARC 025 finding 5 proposed, and the architect ratified, that binding survives declaration-only edits
and breaks only on measurement-path changes. **That ratification was taken on evidence that did not
exist:** the AST classifier was ad-hoc and uncommitted, so ten of fifteen binding rulings rested on a
program nobody could run. ARC 026 built it and re-ran it over `45a37fa`→`0f9c5b9`: **0 of 15 classify
as declaration-only**, against the 10 the ruling was taken on — `contract.py`'s `validate_result`
changed and every check's verdict passes through it.

**The rule may still be right. The evidence for its application was not.** §0c is suspended until
Phase 0 re-derives the true binding state. Until then, no binding claim resting on a
declaration-only classification is trustworthy.

## §0d — Proof of write is not proof of durability (standing)

The write-back gate proves HEAD advanced and contains this arc's paths.

## §0e — Proof of measurement is not proof of durable measurement (standing, ARC 026)

A binding claim requires a **committed, runnable artifact** that reproduces the can-fail. A control
sha in a results document is not one.

## §0f — An unclaimed binding attracts no audit (NEW, ARC 026 D3.25)

ARC 026 caught four prose-only bindings ARC 025 *asserted*, then found a fifth **nobody had claimed**:
`check_verify_logging`, green in every arc since ARC 024, never demonstrated capable of red, with no
ledger row saying so. A false claim invites scrutiny; a silent gap invites none.

**Standing: every check carries an explicit binding status with a named artifact or a named owner.
There is no unstated third category.** The §2.4 binding table is now a standing close-out artifact,
built from measured evidence each arc — never carried forward from the previous table.

---

## PHASE 0 — The true binding state (SERIAL, BLOCKING)

**0.1 — Re-derive every binding claim with the committed classifier.** `measurement_path.py` now
exists and is tested. Run it over each arc's diff range from ARC 022 forward, range stated explicitly
per arc. For every check, report: measurement path changed or not, in which arc, and whether a
committed can-fail artifact post-dates that change.

**§0a note on this step:** an empty or wrong diff range produces a clean report while measuring
nothing. State each range, prove each is non-empty, and prove the classifier's own binding holds
before trusting its output.

**0.2 — Publish the corrected binding table.** Expect it to be worse than ARC 026's. **That is the
point.** A table that comes back identical to 026's after suspending the rule that produced it is
evidence the re-derivation did not bite — report that as a finding, not a confirmation.

**0.3 — Rule on §0c.** With real evidence, state whether the rule survives, needs narrowing (e.g. it
holds except where the changed file is on every check's verdict path), or should be withdrawn.
**Recommend; the architect ratifies.** Do not restore it silently.

**0.4 — Reconcile amendment numbering.** The architect has been saying "Amendment 5" for per-channel
freshness; on disk it is **AMENDMENT 6**. There are two ledgers — `SPEC-AMENDMENTS.md` (frozen risk
spec) and `CHECK-CONTRACT-AMENDMENTS.md` (check contract) — with independent numbering. Report the
true inventory of both, every amendment by number, title, and which document it amends. **Do not
renumber anything** until the architect rules.

**0.5 — Re-measure.** `verify.py`, pytest, pre-commit, claims, CHECK-DEBT, census against the
canonical tree. Expect ARC 026's close: `17 passed | 1 failed | 2 cannot measure | 0 skipped |
1 guarded`, exit 1; pytest 761 + 1 skipped + 2 xfailed; pre-commit 8/8; claims 13/13 with 2/2
demonstrations; CHECK-DEBT 77; census 21 three ways. **Any delta is a finding.**

---

## STAGE 1 — Four parallel sub-agents

File sets disjoint by construction. **None regenerates the execution plan** — that is Stage 2.

### SUB-AGENT A — The unbound and the partial

**A1 — `check_verify_logging` (D3.25), the arc's opening item.** The only gate in the table whose green
has never been shown able to turn red. Its name appears under `scripts/tests/` exactly once, in a
docstring line in `test_plane2.py` — which binds the Plane-2 **emitter**, a different subject. Ship a
committed can-fail artifact that drives the real gate.

**A2 — `check_hook_suite` arms 2–4 (D3.14).** Unassigned since ARC 025. Planting them means editing
`.pre-commit-config.yaml` or perturbing the shared store. **If an arm genuinely cannot be planted
without damaging the shared store, say so per arm and leave it UNBOUND with that reason as its
owner** — a fourth arc of silence is worse than a stated impossibility.

**A3 — `check_order_path_bans` detection can-fail.** Currently PARTIAL: `test_actuation.py` binds the
actuation refusal only. The detection path — the thing that enforces §4's no-retry-on-the-order-path
invariant — has no can-fail. **This is the gate standing over the single most consequential invariant
in the system.**

**A4 — `check_python_deps` real-subject plant.** PARTIAL: 11 tests, 2 fail-asserts, **0 plants**. It
drives fixture states, not the real subject. D3.16 exactly — a gate reporting over something it never
drove.

### SUB-AGENT B — Guards, ledger, and the evidence-verdict split

**B1 — Discharge or re-own `check_artifact_gate_coverage`.** `guard_owner` is `ARC 027`; this arc is
ARC 027. 19 artifacts are accepted as uncovered.

**§0a warning, and it is the heart of this item:** the ratchet enforces monotonic non-increase, so
*lowering the baseline count* satisfies it while covering nothing. D3.19 states the gate proves an
artifact is **named** by a check, never **measured** by one. **An artifact discharged by being named is
not discharged.** Each of the 19 either gets a check that measures it, or stays in the baseline with
an honest owner. Report the split.

**B2 — D2.31, the guard-owner ceiling.** ARC 026 established that an owner naming a *closed* arc is
rejected, but nothing stops an owner being walked forward arc by arc. **[OPERATOR RULING — ceiling is
2]** A guard re-owned twice has been deferred three arcs; the third re-owning escalates to FAIL.
Without it, GUARDED becomes the yellow-forever state it was defined to prevent.

**B3 — D3.21, evidence contradicting its own verdict.** `check_datafeed_bar_seal._drive_seal` returns a
fixed note claiming *"value equality holds"* even when the equality defect fired. Unowned since ARC
025. This is a distinct class from an unread number: the narration is decoupled from the measurement
entirely, so a correct verdict ships with false evidence. **Sweep for the class, do not repair the one
site** — any check whose evidence string is authored independently of the measurement it describes.

**B4 — Spec v1.4.** Fold the amendments into the frozen risk-subsystem spec, subject to 0.4's
numbering ruling. Mechanical fold only, no editorial improvement.

Gate it: every amendment traceable to its landed text, and **no non-amendment text changed**, proven
by diff against frozen v1.3 — not against a working copy, which would compare the file to itself.

### SUB-AGENT C — R1-D, the kill-datafeed-under-load drill

§13 objective 24. Unblocked by ARC 026: both §2A libraries exist, `capture.py` runs, the state bus and
price ring are built and gated.

**C1 — The drill.** Kill the datafeed process under real load and measure what the system does.
**§0a is severe here.** A drill passes while measuring nothing if the datafeed was never actually
under load, was never actually killed, or if the "detection" fires on a timer rather than on the
kill. Prove: real load with a stated rate, a real process death with the PID recorded, and detection
attributable to the death.

**C2 — Per-channel freshness under the drill.** Amendment 6 (per-channel) means the kill produces
per-channel staleness transitions, not one collapsed verdict. Prove each channel reports
independently.

**C3 — Plane-2 events across the kill**, including the events emitted *during* the failure. Per
§12.10 Plane 2 survives a Postgres outage; it must also survive its own process dying. State honestly
what is lost.

**C4 — D1.44, cores 6–19.** §10 assigns cores 0–5; this node has 20. **[ARCHITECT RULING —
revocable]** Reserve 6–19 as unassigned and gate that they stay empty of Nix processes. Isolation is
the point of the core map; a core assigned by nothing is a core anything can drift onto. Cores 4–5
remain the shared pool per §10 — the surplus is not more pool.

**C5 — Gate each** per the standing check-script rule, proving real effective state.

### SUB-AGENT D — The instrument-attribution class

**D1 — Generalise ARC 026's `.pyc` finding.** *A resource claim that moves between checks when the
plan is reordered is an artefact of the instrument, not a property of the check.* Fixed at one site
(`sys.dont_write_bytecode`). **Build the general detector:** run the plan under the observer in at
least two different orders and flag any claim whose attribution moves.

This is the cheapest high-value instrument available right now — it finds a whole class rather than a
site, and ARC 026 proved the class exists on a cold cache.

**D2 — The census-restated-never-derived class.** ARC 026 found the "10 of 13" reflexivity figure
restated in `SESSION.md`, the ledger, and the brief, and derived by none of them. Sweep for other
figures repeated across documents with no derivation, and give each one a source or a debt row.

---

## STAGE 2 — Convergence (SERIAL)

**2.1 — Regenerate the plan.** `--optimize --commit`. Report the diff against the installed plan.

**2.2 — Run under the observer, in at least two orders** (per D1). Every check added this arc is a
fresh candidate for a false declaration; C's drill machinery touches processes, sockets and shared
memory and is the most likely to under-declare.

**2.3 — Census three ways.** Executed == planned == on disk.

**2.4 — The binding table, built from measured evidence** (§0f). Every check: status, committed
artifact, owner for every non-BOUND row. **Not carried forward from ARC 026's table** — that is how
D3.25 stayed invisible for two arcs.

---

## PHASE 3 — Close-out

1. `verify.py` under the regenerated plan. Baseline: `check_ibgateway_service` FAIL +
   `check_ibgateway_config` cannot-measure + `check_observed_resource_claims` cannot-measure. A
   further FAILURE is a finding, and so is any further NON-PASS whose cause is not named. Name every
   GUARDED check and print `guard_owner` verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §2.4 binding table.
4. `git add -A` before every gate measurement — per D2.24 prove ignore rules resolve per target
   first. Per D3.22, `git` honours `GIT_DIR`/`GIT_INDEX_FILE` ahead of `-C`; use the `gitenv.py`
   scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`:
   - Append arc summary to the END of `sessions/SESSION.md`
   - **Overwrite** `downloads/RESULTS.md`
   - `cat` both as the final action, paste into the response
   - **Prove HEAD advanced and contains this arc's paths** (§0d)
   - State the absolute canonical path in the results
6. Clean up temp files.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Open items returned to the operator

1. **The tap session** — operator task at the console, ~40 min, **now owed by nine arcs**. Discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40,
   Amendment 6's poll-channel lag figure, and the two UNBOUND Gateway gates. **It is the only FAIL
   left in `verify.py` and it is a switch.** Plausibly the first exit 0 this project has seen.
2. **§0c** — suspended; Phase 0.3 recommends, architect ratifies.
3. **Amendment numbering** — Phase 0.4 reports, architect rules, then B4 folds.
4. **After this arc: R2, the Limiter.** The safety spine, sole Plane-1 writer, and the consumer that
   discharges most of broker-order's outstanding obligations. It is the largest single product item
   remaining and everything downstream of it is blocked.
