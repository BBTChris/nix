# ARC 028 — R2-A: The Limiter Spine — RESULTS

**Canonical path: `/home/bbt/nix`** (absolute; never relocated).
**Branch:** `arc-028-integration`. **Predecessor:** ARC 027 at `99ba93f`.

---

## HEADLINE

The Limiter now **gates, reserves, publishes and logs**. It cannot exit, and no gate in this arc
implies otherwise. Three of the arc's sharpest findings are **refutations of the integrator's own
briefs, each carried by a measurement** — and the fourth is two artifacts in the canonical tree that
no commit on any branch contains.

```
verify.py    26 passed | 1 failed | 3 cannot measure | 0 skipped     exit 1   (30 checks)
pytest       1204 passed, 1 skipped, 2 xfailed
pre-commit   8/8 Passed (--all-files)                                exit 0
claims       13/13 compared, 2/2 demonstrations                      exit 0
CHECK-DEBT   142 open (derived:ledger_rows == stated:series_table_latest_row)
census       30 == 30 == 30      (executed == planned == on disk)
binding      30 BOUND | 0 UNBOUND | 0 BOUND-BY-MODIFIED-GATE   from 816 observations
drift        0 order-dependent, 0 unstable   (3 orders x 2 sweeps, cold cache)
```

**For the first time in this project's history, every registered check is bound to its own shipped
bytes.** `check_derived_claims` was the last gate bound only by a modified copy of itself.

---

## PHASE 0

### 0.1 — the delta was real, and it was not the tree

The working tree was byte-identical to ARC 027's HEAD; pytest gave `953 passed / 4 failed` against
the expected 957. Isolated to the **invocation spelling**:

```
python -m pytest -q -k reserved_cores             ->  4 failed, 12 passed
./.venv/bin/python -m pytest -q -k reserved_cores ->  16 passed
```

Same bytes, same box, same minute. `_mentions_home` refuses to resolve bare words against the cwd —
correctly — but an activated venv spells the interpreter `python`, so no argv token named a path and
**the census could not see its own author**. The gate was right; the enumerator was blind, and
`nix_processes`' docstring had already conceded the miss in prose. A conceded blindness in a §10
safety census is still a blindness.

The predicate written for the case, `/proc/<pid>/exe`, **measurably does not cover it** — the venv
interpreter is a symlink, so the kernel records `/usr/bin/python3.14`. That disproof is banked as a
test so nobody deletes the predicate that does work believing `/proc/exe` covers it. `_runs_tree_venv`
closes it with two kernel facts, both required.

### 0.2 — the narrated figure, and it is worse than the brief states

`77 + 30 − 3 = 104`. The wrong `103` appears **three** times, and the sharp one is `RESULTS.md`:379
and `SESSION.md`:2559, both reading *"the integrated **103** is `check_derived_claims`' own
`derived:ledger_rows`, not a hand count"* — **a figure claiming derivation the gate never produced.**
The ledger's series row was right at 104 all along; only the narration was wrong.

`SESSION.md` was **not** edited (operator ruling; `CLAUDE.md` directive 6). The correction is appended.

**ANSWER TO THE QUESTION ASKED.** The D2 auditor's `SCOPE` **does** list `downloads/RESULTS.md`. Its
**extractor** is blind to the class, and that is the finding:

```
occurrences in RESULTS.md lines 495-505 : 0
_COUNT matches on the header line       : []
_RATIO matches on the header line       : []
```

Two independent causes: `_COUNT` requires a **noun** after the digits, and the reconciling counts are
spelled in **words**; and the auditor detects *cross-document restatement* while this is
*intra-sentence arithmetic*. **D3.82.**

### 0.3 — a refusal with a measurement, and it changed the item

The brief said to withdraw "0c". Measured first: **`0c` on disk is a different rule, and it is live**
— CHECK-DEBT D2.30/D3.20 and `CLAUDE-CHANGELOG`:96 all cite it as *"a retrofitted check is a NEW
check"*, shipping as check-contract **rule 9**. Withdrawing by the label would have deleted it.

The rule actually withdrawn **had no on-disk name at all.** That is the finding: it governed three
arcs' binding verdicts without ever being written into the contract it governed. Its grounds:
`contract.py` sits on every check's verdict path and changed in three consecutive arcs, so the
classifier's output was a **constant**, and a rule whose output is a constant decides nothing.

Recorded as **CHECK-A7**; `CLAUDE.md` gains **rule 13** — *a rule that decides a check's verdict is
written here and recorded in the ledger, or it does not bind; arc-brief section labels are per-arc,
collide across arcs, and are not ledger identifiers.* **D3.81.** The debt row demonstrates its own
claim: written with the section glyph it drove `check_spec_citations` exit 0 → exit 1 on its own line.

### 0.4 — the premise was partly stale, said rather than worked around

The intra-ledger `AMENDMENT 5` collision was **already repaired on disk by ARC 027**. What was owed
was the mechanism: prefixes `SPEC-A<n>` / `CHECK-A<n>` (numbers unchanged, nothing renumbered,
SPEC-A5's `(D1.38)` attribution restored after the first pass dropped it), plus
`test_amendment_ledgers.py` enforcing prefix, per-ledger uniqueness, disjointness and refinement
exclusion. Driven red both ways against the real ledger, restored byte-identically (sha256 verified).

`check_derived_claims` **refused that file's first spelling by name**: *"parametrize argvalues is not
a literal sequence — the AST count cannot be trusted."* A module-level constant is not a literal
either (measured). The argvalues are inline, and the guard **re-parses this module's own source by
AST** rather than checking a mirror constant — a guard that checks a copy of the thing is the defect
it exists to catch.

### 0.5 — the guard decomposed (delivered by sub-agent C)

**Owner not re-pointed, ceiling not raised, nothing discharged by naming.** 16 per-artifact rows,
each with its own owner and ceiling; verdict CANNOT_MEASURE **per row**, sixteen times. §0g
implemented mechanically as `guard_owner_assignment_defect` — **rejected at write time**, not only at
read. The lineage-laundering defect was closed and planted: reading only the new schema would have
given every row a lineage of length 1 and reset the ceiling **by changing a file format**.

**What the split revealed that the aggregate hid:** 13 rows at the ceiling, `measurement_path.py` at
1, `gitenv.py` and `registry.py` never re-owned — and **4 artifacts named by nothing, not the 2 the
brief claimed.** The fourth is the `nixverify` package initialiser, executed by every import and
asserted about nowhere.

### 0.6 — the seam frozen

`scripts/nixrisk/seam.py`: types and ports, no behaviour. **Every gate verb SYNCHRONOUS**, argued
from the spec — §5's single-threaded loop eliminates fill-vs-tick races by construction, so an
awaitable `evaluate` is a declared suspension point inside one authoritative pass; Plane 1 splits a
synchronous non-durable `enqueue` from the drain because §12.4 needs exactly that split to keep
trading through a Postgres outage. `TerminalPath` transcribed from §3 and **closed**.

`check_limiter_seam` parses §3's release sentence **out of the frozen spec at run time**, and a
control asserts no member appears as a literal in the gate's own source. **The coverage ratchet is
why the gate exists now rather than later — it correctly FAILED the commit on two new uncovered
artifacts.**

---

## STAGE 1

### A — the two-phase gate pass

Ordering is a property of the **executor**, not the list: `GatePass` partitions by declared phase at
boot, and **handing it the manifest reversed does not move execution order.** Proved by observation —
real rule objects appending their own name to a shared log, handed in scrambled order (B,B,A,B,A,A,A),
`GateOutcome.evaluated` compared against the rules' own log so an executor that fabricates a record
moves exactly one of the two. HALT is `evaluated[0]` on **every** pass, so §11.5 is checkable from any
outcome, not only a denial.

**A's own §0a finding:** the discriminating-power guard was first spelled *"refuse if handed ==
observed order"*, and **the source-order plant turned the gate's sharpest FAIL into CANNOT_MEASURE**
— an executor that iterates the manifest makes handed and observed identical *by being the defect*.

**The O(1) claim was made only as a shape.** Rows yielded at |positions| ∈ (1, 64, 512, 4096) →
`(1,0,0) (64,0,0) (512,0,0) (4096,0,0)`; the planted summing defect reports `[1,64,512,4096]` **while
the pass still approves** — nothing but the shape sees it. Wall-clock printed, never a verdict input.

### B — the reservation lifecycle, and a hazard stated backwards

> **A double release is the LOUD one.** It breaks `Σ == fsum(TAKEN)` at the instant it happens, so
> §11.7's mandated standing reconcile reports it next cycle. **A leak breaks no identity at all** — it
> sums into the incremental aggregate and the full scan identically, drift is exactly `0.0` forever,
> and §11.7 is **structurally blind** to it.

The brief's other half — invisible to a *naive leak test* — is confirmed, and proved by driving the
planted ledger and showing `outstanding() == ()` holds under the double release. B2's circularity is
closed mechanically: the path set comes from the spec parser, and **no release-path name appears
anywhere in the gate's source**, asserted against the file's own bytes.

**FINDING ABOUT THE SPEC — D3.55, needs an architect ruling.** §3:151 fixes the terminal set with
*blackout-onset cancellation*; §3:173, twenty-two lines later, says *"Blackout/**HALT** onset ⇒
Limiter cancels all pending ENTRY orders"*. In this spec's own taxonomy they are not synonyms — §3's
Phase A lists the HALT flag separately from the blackouts, HALT is §12.5, blackouts are §6.1–6.3. A
Limiter cancelling entries on HALT onset must release those reservations and has only bad options:
book them as `BLACKOUT_ONSET` (a Plane-1 row naming the wrong cause), as `CANCEL` (cause erased), or
add a member the seam gate would correctly redden. **No member was added.**

### C — instrument debt

**C1 — `check_derived_claims` is BOUND.** The hedge that a shipped-bytes control might not be
constructible was refused with three, each perturbing a real SUBJECT with the gate's sha256 asserted
unchanged either side.

**C2** — see 0.5. **C3 — D3.29/D3.30 discharged:** arm 4's unreachability was **ordering, not
detection**; `repo_defects` now runs before the vacuity complaint and ARC 027's own plant that could
not fire gives exit 1 naming all five pinned revs. A second arm-4 state was found and closed.
**C4 — D3.39 discharged, and the premise was half false:** `statebus.service()` returns the instant
it answers, so the 500 ms budget **was never being spent** (every failing call returned in
0.1–23.6 ms) and raising it was refused with that measurement. Worse, the original staging made the
check **vacuous** — with both subscribers connected back-to-back, clearing `XPUB_VERBOSE` still
completed both mirrors. Arrival is now the terminator; staging is sequential.

### D — `risks/` as data

29 §12A knobs across five per-module configs, module ownership derived from §2's authority table and
§10's core map. **The count is derived, not transcribed:** the gate locates §12A at run time, takes
the span, extracts backticked `UPPER_SNAKE` tokens, and reads each cited line back out of the frozen
file to confirm it carries that name; controls assert no knob name and no count literal appears in
the gate's source, and the derivation is proved by adding a knob to a **copy** of the spec.

**D refused a hazard stated backwards:** *"a code path keyed off a config value"* is what config
**is** — a blackout threshold keying a gate is correct. The real hazard is the inverse, **a config
value naming a code path**, and the gate bans that direction: no strings in value position at all, so
an eval'able expression, module path or dispatch key cannot be a knob.

D also refused the trigger of `broker_order.config.json`'s `obligation_when_R2_lands` while honouring
its substance — landing `risks/limiter.config.json` would itself have created the second home the
clause forbids, so both mirrored knobs were removed and are now **read** from the Limiter's config.

**Four of D's eight debt rows are spec gaps found by EXECUTING §12A rather than reading it**,
including the one invariant §12A calls boot-validated comparing against a `pad` §12A never names.

---

## STAGE 2 — the financial picture and Plane 1

**Atomicity is a property of the type, not a discipline the writer is asked to keep.** The book's
entire state is one immutable `FinancialPicture`; a mutation builds a new one and rebinds one name,
so a reader does one attribute load and holds a whole self-consistent object. No lock — §11 forbids
one on the entry path. A second writer is **refused**, not serialised.

**Proven under a real race, with the detector proven first.** Writer thread against reader thread,
terminating on **arrival** (reads × distinct version stamps), never on a clock (D3.39), at
`switchinterval=1e-5`. **Two plants run before the subject is judged at all, and each must tear or
the verdict is CANNOT_MEASURE:**

| arm | tears / reads |
|---|---|
| `_TwoReadConsumer` — §3's forbidden two reads, consumer side | **1996 / 2000 (99.8%)** |
| `_TwoAttributeBook` — two attributes, two stores, publisher side | **34–98 / 2000 (2–5%)** |
| **subject** — 2000 reads across 64 distinct versions | **0** |

The evidence line prints the weaker plant's rate beside the zero, so *0 tears* carries **stated
power**. **The detector had to be built twice:** the obvious coherence predicate is provably blind to
§3's actual tear, because a publisher reading balance at generation *k* and the table at *k+1* then
deriving consistently emits a snapshot every predicate accepts — `balance` is an independent input
nothing else constrains. A generation link was planted instead, and the blind spot is **asserted in a
test that fails the day it stops being true** (D3.95).

**Fsync proven as an observed syscall, with its file named:** `strace -f -y -e trace=fsync,fdatasync`
requiring `fsync(3</tmp/nixwal-…/fsync.wal>) = 0`; the identical child with `sync_to_disk` withheld
produces **0** matching lines. **Crash gap proven with a process that really died**, kernel-reaped
`-9`; the clean-exit control reaps 0. **Disk-critical produced by the kernel**, not a mock:
`RLIMIT_FSIZE` + `SIGXFSZ` → 28 rows accepted then `OSError errno=27`.

### The brief's §0a hazard was stated backwards, and it is refuted with a measurement

> **A SIGKILL cannot test fsync.** The same producer run with `--no-sync` (`fsyncs=0`,
> `durable_bytes=0`), genuinely SIGKILLed and genuinely reaped `-9`, leaves **4128 rows / 624,092
> bytes fully readable.** A killed process's dirty pages belong to a still-running kernel. **A
> durability gate built on the kill alone is green on a WAL with the fsync deleted.**

Banked as a permanent control; the gate prints both figures on every run — *"durable prefix 32 vs
4128 readable"*. **D3.93.**

Found by the instrument: the wire schema key was `_schema`, which `statebus._decode` strips —
**18,970,932 bytes carried, zero pictures decoded**, reported CANNOT_MEASURE rather than agreement.

---

## THREE OF MY OWN DEFECTS, EVERY ONE FOUND BY A SUB-AGENT REFUTING ME

1. **The seam gate did not guard the seam's most-argued property.** I told all four sub-agents
   `check_limiter_seam` would redden on a sync/async change. Measured against the shipped bytes: all
   four ledger verbs rewritten `async def` → **PASS, empty detail**; a deleted `ProposedOrder` field →
   **PASS**. ARM 3 now exists, and building it produced **four more of my own**, each found by a plant
   failing to plant: `Plane1Port` carries a **digit** and my class pattern was `[A-Z][A-Za-z]*`, so
   the port this arc argues hardest about was outside the comparison; the floor **discarded defects
   already observed** to report that it could not measure (§17 — a positively-observed defect outranks
   masking); a port named only as `Class.verb` could be deleted outright and still pass, and the first
   repair then **suppressed the bare-named case**; and `{...} | ports - set(classes)` — `-` binds
   tighter than `|`, so the gate reported **every** declared port missing.
2. **The Phase 0 repair reintroduced its own defect one directory over.** A, B and C each
   independently reported it; two proved it pre-existing by stashing their whole diff at base.
   `_runs_tree_venv` asked `is_relative_to(nix_home)`, false in every provisioned worktree because
   `.venv` is a symlink and `activate` bakes the primary path. **I had replaced a verdict that was a
   function of invocation *spelling* with one that was a function of invocation *environment*.**
3. **That repair's own cost, recorded rather than left to be found (D3.84).** With two trees live the
   primary census attributed 8 processes, **3 of them a sibling worktree's**, every one via the `venv`
   predicate and none via `argv`. The two predicates in one union now disagree about tree identity.
   A repair exists (conjoin `cwd`) and would redden the control whose child is spawned with `cwd="/"`
   precisely to prove argv-independence; re-aiming it on a **third** change to a safety census mid-arc
   is the move the doctrine warns about. The honest closure is D1.42's — join the units to
   `nix-trading.slice` and the kernel answers per tree.

---

## CONVERGENCE, AND TWO ARTIFACTS NOBODY COULD ATTRIBUTE

**3.1** Plan regenerated: **identical to the live registry**, `added: []`, `removed: []`, block
structure identical, 4 blocks / 30 checks. That matters this arc: five branches hand-added checks and
`registry.json` conflicted twice. A hand-merge of a **derived** file is meaningless, so the union was
only a way to reach parseable JSON — the derivation then confirmed it independently.
**3.2** Observer in three orders, cold cache, each swept twice, 7 `__pycache__` trees cleared per
sweep, 62 raw claims per sweep: **0 order-dependent, 0 unstable.**
**3.3** Census **30 == 30 == 30**.
**3.4** Binding table rebuilt from **816 measured observations**, never carried forward.

### D3.99 — two artifacts in the canonical tree that no commit contains

`scripts/nix_status.sh` (561 lines) and `scripts/tests/test_nix_status.py` (250 lines) were on disk at
`/home/bbt/nix`, staged by the mandated `git add -A`, and broke three commit gates — **which is the
only reason they were noticed.** Provenance measured four ways, all negative:

* `git log --all -- <both paths>` → nothing
* `git cat-file -e HEAD:<path>` → *exists on disk, but not in HEAD*
* `git grep -l nix_status HEAD` → nothing **committed** references either
* working-tree grep → only the two files themselves, a closed self-referential pair

They did not exist at arc start (the opening `git status --short` showed exactly one untracked path,
the arc brief). Timestamps fall inside the Stage 1 window. No sub-agent reported them, and all five
were told explicitly to work only inside their provisioned worktrees. The test's docstring claims
`nix_status.sh` v1.0.0 *shipped* with two faults and rendered 2 of 28 checks — **v1.0.0 is in no
commit either**, so it reports a defect in an artifact that never shipped.

**NOT ADOPTED.** Unattributable work is not merged into a safety spine on the strength of a plausible
docstring. Nothing durable was lost, and both files are preserved with their sha256 so an operator can
restore them deliberately. **This is ARC 024's failure class inverted, and it is why the write-back
gate exists.**

---

## §3.4 BINDING TABLE — all 30 checks, from 816 MEASURED observations

**BOUND = a committed artifact was observed driving the SHIPPED gate's own bytes to a failing
status.** `CANNOT_MEASURE` and `GUARDED` are reported, never counted as a can-fail (§17).

| # | check | verdict | shipped-gate statuses observed |
|---|---|---|---|
| 1 | `check_artifact_gate_coverage` | **BOUND** | CM:17, FAIL:20, GRD:9 |
| 2 | `check_canonical_tree` | **BOUND** | CM:1, FAIL:4, PASS:12 |
| 3 | `check_capture_plane2` | **BOUND** | CM:4, FAIL:2, PASS:12 |
| 4 | `check_core_map` | **BOUND** | CM:3, FAIL:6, PASS:11 |
| 5 | `check_datafeed_bar_seal` | **BOUND** | FAIL:2, PASS:51 |
| 6 | `check_datafeed_granted_mode` | **BOUND** | FAIL:3, PASS:9 |
| 7 | `check_derived_claims` | **BOUND** | FAIL:3, PASS:12 — **was BOUND-BY-MODIFIED-GATE** |
| 8 | `check_feed_kill_drill` | **BOUND** | CM:2, FAIL:8, PASS:9 |
| 9 | `check_hook_suite` | **BOUND** | CM:2, FAIL:9, PASS:21 — arms 3–4 now bound |
| 10 | `check_ibgateway_config` | **BOUND** | CM:12, FAIL:1, PASS:2 |
| 11 | `check_ibgateway_service` | **BOUND** | CM:2, FAIL:12, PASS:2 |
| 12 | `check_limiter_gate` | **BOUND** | CM:3, FAIL:6, PASS:16 — **new, ARC 028 A** |
| 13 | `check_limiter_seam` | **BOUND** | CM:4, FAIL:8, PASS:9 — **new, ARC 028 Phase 0** |
| 14 | `check_name_coherence` | **BOUND** | CM:3, FAIL:8, PASS:16 |
| 15 | `check_node_identity` | **BOUND** | FAIL:2, PASS:10 |
| 16 | `check_observed_resource_claims` | **BOUND** | CM:8, FAIL:3, PASS:1 |
| 17 | `check_order_path_bans` | **BOUND** | CM:1, FAIL:12, PASS:20 |
| 18 | `check_picture_atomicity` | **BOUND** | CM:3, FAIL:6, PASS:10 — **new, ARC 028 S2** |
| 19 | `check_plane1_wal` | **BOUND** | CM:3, FAIL:12, PASS:10 — **new, ARC 028 S2** |
| 20 | `check_plane2_across_kill` | **BOUND** | CM:5, FAIL:3, PASS:8 |
| 21 | `check_price_ring` | **BOUND** | CM:4, FAIL:6, PASS:11 |
| 22 | `check_python_deps` | **BOUND** | CM:1, FAIL_REPAIRABLE:2, PASS:11 |
| 23 | `check_python_runtime` | **BOUND** | FAIL:2, PASS:13 |
| 24 | `check_reservation_lifecycle` | **BOUND** | CM:4, FAIL:6, PASS:11 — **new, ARC 028 B** |
| 25 | `check_reserved_cores` | **BOUND** | CM:2, FAIL:1, PASS:8 |
| 26 | `check_risks_data_only` | **BOUND** | CM:4, FAIL:18, PASS:9 — **new, ARC 028 D** |
| 27 | `check_spec_citations` | **BOUND** | CM:1, FAIL:1, PASS:13 |
| 28 | `check_state_bus` | **BOUND** | CM:4, FAIL:5, PASS:12 |
| 29 | `check_venv` | **BOUND** | CM:1, FAIL:2, FAIL_REPAIRABLE:1, PASS:12 |
| 30 | `check_verify_logging` | **BOUND** | FAIL:6, PASS:13 |

**30 BOUND · 0 BOUND-BY-MODIFIED-GATE · 0 EXERCISED-NEVER-RED · 0 UNBOUND.**

---

## EVERY NON-PASS NAMED — all four are the stated baseline, and nothing else

| verdict | check | cause |
|---|---|---|
| FAIL | `check_ibgateway_service` | `127.0.0.1:4002` ECONNREFUSED — Gateway down (baseline; the tap session) |
| cannot-measure | `check_ibgateway_config` | no API endpoint at `127.0.0.1:4002`; not a misconfiguration (§4.1) |
| cannot-measure | `check_observed_resource_claims` | masked hazard — downstream of the two above did not execute, so remaining resource use is UNOBSERVED. §17: never PASS |
| cannot-measure | `check_artifact_gate_coverage` | **16 per-artifact rows, sixteen times.** Until an artifact is genuinely MEASURED, CANNOT_MEASURE is the honest verdict — not forced green, and nothing discharged by being named (D3.19) |

**GUARDED checks: none.** **No further FAILURE, and no further non-PASS whose cause is not named.**

---

## LEDGER

**CHECK-DEBT 104 → 142.** Thirty-seven opened, three discharged, and the figure is
`check_derived_claims`' own `derived:ledger_rows` agreeing with
`stated:series_table_latest_row` — never a hand count. Five branch figures were written during the
arc (A 111, C 107, D 112, the integrator's Phase-0 107, Stage 2 forbidden to touch it) and **every one
said in its own cell that it was a branch figure.**

**Discharged, each with its own re-measurement: D3.29, D3.30, D3.39.**
**Opened (37): D3.41–D3.47 (A) · D3.51–D3.56 (B) · D3.61–D3.66 (C) · D3.71–D3.78 (D) · D3.81–D3.84
(Phase 0 and integration) · D3.91–D3.98 (Stage 2) · D3.99 (convergence) · D3.100 (close-out).** Thirty of the
thirty-seven were opened by an instrument, by a plant that failed to plant, or by a sub-agent refuting
a stated premise with a measurement.

---

## EXPLICITLY NOT IN THIS ARC — and no gate implies otherwise

Stop conversion and trailing maintenance · protective-exit wiring to broker-order · session-close
flatten · full HALT semantics and auto-clear · cold-start reconciliation · full Postgres schema
integration (the Plane-1 sink is a list in memory) · the group-commit cursor's durability across a
restart · cross-process picture delivery · power-loss durability · the Sentinel · Scoring and the
ranking table · the Allocator.

**A Limiter that gates, reserves, publishes and logs but CANNOT EXIT is not a safety spine yet.**
Both new Stage 2 gate docstrings say so in their own words, and §13 objective V24 stays open (D1.47).

---

## RETURNED TO THE OPERATOR / ARCHITECT

1. **D3.55 — needs a ruling.** §3's terminal set names *blackout-onset cancellation*; §3:173 says
   *Blackout/**HALT** onset*. They are not synonyms in this spec's taxonomy. Until it is ruled, a
   Limiter cancelling entries on HALT onset cannot book a Plane-1 row naming the right cause.
2. **D3.99 — provenance.** Two artifacts, 811 lines, in the canonical tree and in no commit. Not
   adopted; preserved. Needs a ruling on where they came from before any of it is merged.
3. **The tap session** — operator task at the console, ~40 min, now owed by **twelve** arcs. Still the
   only FAIL in `verify.py`, and it is a switch.
4. **D3.81** — a rule that decided binding verdicts for three arcs and was never written into the
   contract it governed. `CLAUDE.md` rule 13 now forbids the shape; the ledger records the instance.
5. **v1.4 still deliberately not authority** (D3.33) — unchanged this arc.

===RUN SUMMARY: ARC 028 — R2-A: The Limiter Spine, Estimated run time: 5h 20m, completes ~30% of the Risk Engine / Limiter module (Core 2) and ~8% of the whole project (the gate pass, reservation lifecycle, atomic financial picture and Plane-1 WAL exist and are bound; the protective-exit half, HALT semantics and cold-start reconciliation do not)===
