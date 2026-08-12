# ARC 025 — Bulk Retrofit, Observed Disjointness, and the Durability Gate

**Module:** verify.py / checks subsystem
**Predecessor:** ARC 024 (**staged but NOT COMMITTED — see Phase 0**)
**Shape:** mega arc. Phase 0 serial and blocking · Stage 1 three parallel sub-agents ·
Stage 2 serial convergence · Stage 3 doctrine · Phase 4 close-out.

---

## §0a — Self-audit clause (standing)

Before acting on any instruction in this brief, ask: *what would have to be true for this step to
complete successfully while measuring nothing?* Any step whose success is compatible with measuring
nothing is a defect in this brief. Report it, do not silently satisfy it.

## §0b — Architect spellings are non-binding (standing)

Every concrete spelling here — file layouts, flag names, schema shapes, discovery mechanisms — is a
sketch. The **invariants** bind; the spellings do not. If implementing a spelling as written would
degrade an instrument, blind a gate, or make a check report over a subject it never drove, **refuse
it with a measurement**, implement the invariant another way, record the substitution.

Precedent, ARC 024: Stage 3.1's parallel spelling would have put two checks on IBKR port 4002. A
`socket.connect` spy caught it. Refused, and the refusal became a test.

## §0c — A retrofitted check is a new check (standing, ARC 024)

Any check modified here loses its D3.10 binding at the moment of modification. Can-fail must be
re-established against its **real** subject or the check reverts to UNBOUND and says so.

## §0d — Proof of write is not proof of durability (NEW DOCTRINE, this arc)

ARC 024 proved `RESULTS.md` was rewritten — mtime 124 s old, size changed — and every gate reported
green. **The entire arc was staged in the index and absent from history.** An mtime proves a file was
written. It does not prove the work survives. This is the sixth instance of the project's
*git-tracking-state-sets-gate-scope* class, in a new shape: **staged but uncommitted.**

Standing from this arc: the write-back gate proves **HEAD advanced and contains this arc's paths**.

---

## PHASE 0 — Durability (SERIAL, BLOCKING, nothing else starts)

**0.1 — Inventory the staged set.** Print every staged path. Flag anything not belonging to ARC 024.
The set was reported as 30 paths; confirm the number and the membership.

**0.2 — Commit, branch, push, PR, merge** through the normal path. Report the new HEAD.

**0.3 — Re-measure against merged history.** Every ARC 024 gate figure was taken against a working
tree that never became history. Re-run on the merged tree: `verify.py` (expect
`11 passed | 1 failed | 1 cannot measure | 0 skipped | 1 guarded`, exit 1), pytest (expect 438 + 1
skipped + 2 xfailed), pre-commit 8/8, claims harness 13/13 with 2/2 demonstrations, CHECK-DEBT 66.
**Any delta is a finding, not a correction** — report it before proceeding.

**0.4 — Name ruling (operator).** `registry.json` is the file; `manifest_version`,
`nixverify/manifest.py`, `ManifestError`, `load_manifest()`, `--manifest` are the vocabulary.
Architect recommendation: **keep `registry.json`, purge the manifest vocabulary** — ARC 010 renamed
the file and not the identifiers. If the operator has not ruled by execution time, **do not rename
anything**; proceed and leave the vocabulary alone. Retrofit declarations do not depend on the name.

---

## STAGE 1 — Three parallel sub-agents (file sets disjoint by construction)

Sub-agents A, B, C touch non-overlapping paths. **None of them regenerates the execution plan** —
that is Stage 2, serial, because the plan is a shared write target.

### SUB-AGENT A — Wave A retrofit (low risk)

`check_python_runtime` · `check_node_identity` · `check_spec_citations`

Read-only, no socket, no service, static subjects. Per check: full flag surface
(`--correct`/`--install` on its own CLI, default measure-only), `DEPENDS_ON`, `RESOURCES`,
time-bound declaration, Plane-2 emission, §0c re-binding against the real subject.

**A2 — `check_node_identity` is credential-adjacent.** It sits near `state/` at 0600. ARC 024
proposed it for the non-correctable class. **[ARCHITECT RULING — revocable]** Implement it
non-correctable; `--correct`/`--install` refuse loudly and name why.

### SUB-AGENT B — Wave B retrofit (HIGHEST RISK)

`check_datafeed_bar_seal` · `check_datafeed_granted_mode` · `check_derived_claims` · `check_hook_suite`

**These are the gates ARC 022 and ARC 023 spent two arcs binding.** `check_datafeed_granted_mode` was
rebuilt in 023 after three independent defects; `check_datafeed_bar_seal`'s arm 4 was repaired in the
same arc. §0c unbinds all four the moment they are touched.

**B1 — Control-before, control-after, identical shas.** For each of the four: re-run its banked plant
**before** the retrofit to capture the control sha, retrofit, re-run **after**. The before and after
control shas must match. A mismatch means the retrofit changed the subject, not just the wrapper —
stop and report.

**B2 — The plants are the ARC 021 plants for the two datafeed gates.** They are the only can-fail
evidence those gates have. Re-run both against both settled gates. `__pycache__` purged between
steps; every control restored byte-identical.

**B3 — `check_derived_claims` retrofitting itself is a reflexivity hazard.** It is the instrument that
verifies claims, and it is about to become a claim-bearing subject. **[ARCHITECT RULING — revocable]**
Its can-fail must be demonstrated by a plant that makes it report a *wrong* count, verified by
something other than itself. If no independent verifier exists, that is a finding — say so rather
than letting it grade its own retrofit. ARC 024 already saw this gate catch a parametrize refactor
that broke its own AST count; that was luck of ordering, not architecture.

**B4 — If any of the four cannot be re-bound, it reverts to UNBOUND and says so.** Do not carry a
stale binding forward. Four unbound gates is an honest outcome; four silently-still-green gates is
the defect this project exists to prevent.

### SUB-AGENT C — Instruments and ledger

**C1 — Close D2.27 with a runtime observer.** The row reads: *disjointness is proven over
declarations, never over actual resource use, and no static mechanism can close that gap.* True of
static mechanisms — and ARC 024 already built the dynamic one. The `socket.connect` spy that caught
both Gateway gates dialling 4002 is the instrument.

Promote the one-off into a standing gate: run each check under the observer, capture **observed**
resource use (sockets, file writes, service interaction, subprocess), compare against **declared**
`RESOURCES`, and FAIL on any observed claim the declaration does not make.

This closes the false-declaration residual (D3.16 one level up): a check declaring `RESOURCES = ()`
while dialling 4002 becomes measurable rather than trusted. Ships with a demonstrated FAIL path —
plant an undeclared socket, prove exit 1 naming the check and the endpoint.

**Masked-hazard clause (new standing rule, from ARC 024's refusal):** the Gateway is down, so both
Gateway gates get ECONNREFUSED and their collision is invisible. **A safety property proven while its
subject is unavailable is not proven.** Where the observer cannot see a resource because the resource
is unreachable, it returns CANNOT-MEASURE for that check — never PASS.

**C2 — `guard_owner` must pin one arc.** It currently reads
`"the bulk check retrofit arc (ARC 025+), sized in ARC 024 Stage 6.4"`. GUARDED is defined as a marker
naming *the specific* discharging arc; `ARC 025+` is a range. The empty-string fallback
(`discharged by NOBODY — this is a defect`) is good, but a range passes the non-empty test while
failing the requirement. Constrain to a single arc identifier, mechanically validated.

**C3 — The coverage baseline must ratchet one way.** `gate_coverage_baseline.json` accepts 24 of 29
uncovered artifacts. Nothing reported constrains it from growing. **A baseline that can grow silently
is a vacuous pass wearing a config file.** Enforce monotonic non-increase; any addition requires a
named arc and fails loud without one.

**C4 — `broker_order_open_debt_rows` counts mentions, not ownership.** It moved 13→15 with nothing
touching broker-order, because D1.41 and D3.20 legitimately *name* `broker_order_ibkr.py`. Third
contamination of this metric (D2.19 class). Re-derive it by **owning module**, not filename mention.
Report the corrected series alongside the old one for one arc so the discontinuity is visible.

---

## STAGE 2 — Convergence (SERIAL)

**2.1 — Wave C, declare-only.** `check_ibgateway_config` · `check_ibgateway_service`. Both declare
`port:127.0.0.1:4002` **together**, which keeps them sequential automatically (D1.41). Full flag
surface and declarations land; **can-fail re-binding does NOT** — it needs a live authenticated
Gateway, which this arc does not have.

**[ARCHITECT RULING — revocable]** Both revert to UNBOUND and return **GUARDED** with
`guard_owner` naming **the tap session** as the discharging event. That is honest: the property is
real and measured, the binding is deferred, and the owner is a specific named thing rather than a
range. The tap session is now owed by seven arcs.

**2.2 — `--optimize` goes live.** With waves A and B declared, the undeclared population drops from 9
to 2 (the Gateway pair, declared in 2.1) — **zero**. Run `--optimize` for real. Expect it to:
- derive the plan from the folder,
- detect zero cycles,
- detect zero orphans in both directions,
- refuse any parallel block whose members' declared resources intersect,
- write `<plan>.proposed`, and require `--commit`.

**Report the diff between the current plan and the derived one.** That diff is the single most
interesting artifact this arc produces: it is the difference between the plan a human maintained and
the plan the dependency graph implies.

**2.3 — Run the optimized plan and prove the census three ways.** Executed count == plan count ==
disk count. Three-way agreement, not two. A check on disk absent from the plan never runs and its
absence looks like green.

**2.4 — Then run it under C1's observer.** Declared disjointness is now checked against observed
behaviour across a real parallel run. Any block that survives static validation and fails the
observer is the headline of this arc.

---

## STAGE 3 — Doctrine to disk

**3.1 — §0d into the close-out contract.** The write-back gate proves **HEAD advanced and contains
this arc's paths**. Add to `docs/nix_check_contract.md` and to `~/nix/CLAUDE.md`'s check-contract
section. Amendment recorded in `docs/CHECK-CONTRACT-AMENDMENTS.md`.

**3.2 — The masked-hazard rule** (C1) into the same contract: a safety property proven while its
subject is unavailable is not proven; the correct verdict is CANNOT-MEASURE.

**3.3 — The control-asserts-the-reason rule.** From ARC 024: the §2.2 re-verify control initially
passed because the subprocess *crashed* and also returned 1. **Every can-fail control asserts the
reason — message, site, or field — never the exit code alone.** Into the contract, and audit the
existing control population against it: report how many assert only an exit code.

**3.4 — Changelog.** Append to `~/nix/CLAUDE-CHANGELOG.md`. **And commit it** — see §0d.

---

## PHASE 4 — Close-out

1. `verify.py` full run under the optimized plan. Baseline: `check_ibgateway_service` FAIL +
   `check_ibgateway_config` cannot-measure, plus whatever Phase 0.3 settled. A further FAILURE is a
   finding, and so is any further NON-PASS whose cause is not named. **Name every GUARDED check and
   print its `guard_owner` verbatim** — ARC 024 reported a guarded count without naming the check,
   twice.
2. Full pytest, pre-commit all hooks, claims harness, CHECK-DEBT level with the C4 correction shown
   alongside the old series.
3. State the binding status of all 14+ checks: BOUND / UNBOUND / GUARDED / RETIRED, with the owner
   for every non-BOUND row.
4. `git add -A` before every gate measurement — per D2.24, prove the ignore rules resolve per target
   first; do not stage a `state/` symlink into the 0600 credential dir.
5. Write-back gate:
   - Append arc summary to the END of `~/nix/sessions/SESSION.md`
   - **Overwrite** `~/nix/downloads/RESULTS.md`
   - `cat` both as the final action, paste into the response
   - **Prove HEAD advanced and contains this arc's paths** (§0d). Not mtime. Not size. HEAD.
6. Clean up temp files.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Open items returned to the operator

1. **`registry.json` vs `manifest.json`** — still unruled. Architect: keep `registry.json`, purge the
   manifest vocabulary. Phase 0.4 does nothing without a ruling.
2. **Non-correctable class** — 3 implemented, ARC 024 proposed `check_node_identity` + both Gateway
   gates. This arc implements `check_node_identity` as non-correctable (A2). Ratify or narrow.
3. **Wave C's GUARDED owner is the tap session** (2.1). The tap session is an operator task at the
   console, ~40 min, now owed by seven arcs. It also discharges D1.12 reboot capture, D1.33
   marketDataType, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40, and Amendment
   5's poll-channel lag figure. Wave C's binding is the seventh thing waiting on it.
