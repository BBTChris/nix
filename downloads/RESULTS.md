# ARC 027 — The True Binding State, the Unbound Four, and R1-D — RESULTS

**THE CANONICAL PATH IS `/home/bbt/nix` (absolute).** You are reading a live file at
`/home/bbt/nix/downloads/RESULTS.md`, written by this arc, in the tree every gate measures and the
Samba share `[nix]` serves. Not relocated, nothing beside it deleted.

**Predecessor:** ARC 026 (`f4dab7d`). **This arc:** branch `arc-027-integration`.

---

## THE ONE-PARAGRAPH VERSION

The binding table stopped being *read* and started being *measured*. An instrument now watches every
verdict the real check code produces, in the pytest process and in every child, and classifies it by
the sha256 of the module that produced it. It disagrees with ARC 026's hand-built table in five
places — two rows ARC 026 called UNBOUND are bound, one it called BOUND is bound only by a modified
copy of itself — and the three gates it found `EXERCISED-NEVER-RED` are now bound with committed
artifacts. **Every gate in the population can be shown able to turn red.** Alongside that: §0c is
recommended for withdrawal on measured grounds, the guard-owner ceiling bit on the only guard there
is, the datafeed was killed under 2.6M ticks/s and the detection proven attributable to the death
rather than to a clock, and a **live safety defect was found in the trading-session mutation
interlock** by a sweep nobody aimed at it.

---

## PHASE 0 — THE TRUE BINDING STATE (serial, blocking)

### 0.1 — every binding claim re-derived, five ranges, each proven non-empty

`scripts/nixverify/measurement_path.py` gained a CLI. It **refuses an empty range** — `RangeError`,
exit 2, no table printed, and no override flag — because the §0a hazard is exact: an empty range
classifies every check as declaration-only in silence, and that output is indistinguishable from an
arc that touched nothing.

Second correctness point, not cosmetic: `resolve_imports` decides whether a first-party import
resolves by asking whether the file EXISTS. Passing the live working tree answers that against
*today's* module population, so a helper that existed at ARC 022 and was deleted since would
silently stop being followable and the cross-file arm would go quiet exactly where history is
oldest. **Both revisions are extracted with `git archive` and classified against their own trees.**

Classifier's own binding verified before its output was trusted: `test_measurement_path.py` → 24 passed.

| arc | range (stated) | files changed | checks | preserve a binding |
|---|---|---|---|---|
| ARC 022 | `08d9c56..df36405` | 17 | 12 | **9** |
| ARC 023 | `df36405..2871bc6` | 14 | 12 | **9** |
| ARC 024 | `2871bc6..509159d` | 30 | 14 | **0** |
| ARC 025 | `509159d..0f9c5b9` | 42 | 15 | **0** |
| ARC 026 | `0f9c5b9..f4dab7d` | 67 | 21 | **0** |

**The discriminator, measured** — which shared verdict-path module changed per arc:

```
ARC 022  (none)
ARC 023  (none)
ARC 024  actuation.py contract.py declarations.py engine.py loader.py plane2.py
ARC 025  contract.py declarations.py
ARC 026  _preamble.py actuation.py contract.py engine.py plane2.py
```

`scripts/nixverify/contract.py` changed in ARC 024, 025 **and** 026. Every check imports it
transitively. §0c has preserved nothing for three consecutive arcs, and not by accident.

### 0.2 — the corrected binding table, MEASURED

New, committed with its own can-fail (`test_binding_census.py`, 9 controls):

* `scripts/tests/binding_tracer.py` — a `sys.monitoring` PY_RETURN monitor recording every return of
  `run()` from a check module, in the pytest process **and in every spawned child** (a generated
  `sitecustomize.py` on `PYTHONPATH`), attributed to the nodeid the runner stamps into the
  environment, tagged with the **sha256 of the module that produced the verdict**.
* `scripts/tests/binding_census.py` — runs the committed suite once under it and publishes the table.
  Refuses on zero collection or below a 50-observation floor: an empty census and *"no gate in this
  system can fail"* are the same file.

**THE INSTRUMENT'S OWN §0a DEFECT, MEASURED ON ITS FIRST RUN AND COMMITTED WITH THE FIX.** The first
cut opened its record file with `open()` per observation. `nixverify.observe` hooks the `open` AUDIT
EVENT, so the tracer's own bookkeeping appeared inside the observation window as
`file-write:.../observations.jsonl` and was charged to whichever gate was being observed — **five
controls went red.** The measurement changed the measurement: ARC 026's `.pyc` class, reproduced by
the instrument built to audit it. Fixed at the cause (one descriptor opened at `sitecustomize`
import, *before* the observer arms; `os.write` after, which raises no audit event). Held closed by a
pair — an invisibility test, and a CONTROL that puts `open()` back **inside the callback**, where the
window actually is, and watches the forbidden claim reappear.

**Non-perturbation proven, twice:** the traced suite reports `957 passed, 1 skipped, 2 xfailed` —
identical to the untraced baseline.

#### Where the measured table DISAGREES with ARC 026's

| check | ARC 026 said | MEASURED | why it matters |
|---|---|---|---|
| `check_ibgateway_config` | **UNBOUND**, owner = the tap session | **BOUND** | `test_non_loopback_source_that_is_served_is_a_named_defect` drives the shipped gate to FAIL_NEEDS_OPERATOR |
| `check_ibgateway_service` | **UNBOUND**, owner = the tap session | **BOUND** | four committed controls drive the shipped gate red and name the unit |
| `check_derived_claims` | **BOUND** | **BOUND-BY-MODIFIED-GATE** | its four reds come only from a gate whose SOURCE differs from what ships — the plants substitute into the gate's own derivation |
| `check_order_path_bans` · `check_python_deps` · `check_verify_logging` | PARTIAL / PARTIAL / UNBOUND | **EXERCISED-NEVER-RED** | confirmed by measurement rather than by grep |

**The two Gateway rows are the sharpest evidence that §0f is right.** ARC 026 assigned them to the
tap session on the strength of reading. What the tap session actually owes is the **green**
demonstration and the live rejection taxonomy — not the can-fail, which is committed and runs every
arc.

**Stated limit of the instrument:** it answers *did a committed artifact drive this gate to a failing
status*, never *which arm*. `check_hook_suite` reads BOUND while two of its four arms are unplanted.
Sub-agent A reports per arm. Recorded rather than implied.

### 0.3 — RULING ON §0c: **RECOMMEND WITHDRAWAL, WITH A REPLACEMENT.** Architect ratifies.

1. **§0c is inert, and has been since ARC 024.** `contract.py` is on every check's verdict path and
   changed in three consecutive arcs. The classifier returns MEASUREMENT_PATH for every check in
   every arc that touches the check contract — and six amendments landed across those three arcs. **A
   rule whose output is a constant decides nothing.**
2. **The narrowing the brief offers changes no verdict in the measured history.** *"It holds except
   where the changed file is on every check's verdict path"* fires in exactly ARC 024/025/026 — the
   three arcs where §0c already preserves nothing — and never in ARC 022/023, where it already
   preserves 9 of 12. **The narrowing is cosmetic.**
3. **§0c is a proxy for a question that is now directly measurable.** It exists to decide whether a
   binding may be carried forward without re-demonstration. That does not need deciding: pytest
   re-executes the artifacts against the current tree every arc and the census reads the verdict the
   shipped gate actually produced. A demonstration re-run thirty seconds ago needs no rule about
   whether it is still valid.

**RECOMMENDATION.** (a) **Withdraw §0c**; do not restore it. (b) Replace it with §0f as implemented —
binding is established by a committed artifact **observed** driving the shipped gate to a failing
status, re-measured every arc. (c) **Keep `measurement_path.py`** as a *structural* instrument: it is
what proved `contract.py` sits on every check's verdict path, which is finding 1.

### 0.4 — AMENDMENT NUMBERING. **The brief's premise is false.** RENUMBERED NOTHING.

The brief says the "Amendment 5 vs 6" confusion arises because two ledgers number independently.
**That is not where this collision comes from.** Both ledgers do number independently — its own,
separate hazard — but per-channel freshness was issued titled *"AMENDMENT 5"* while 5 was **already
taken inside the same ledger** by ARC 022's `AMENDMENT 5 (D1.38)`. `SPEC-AMENDMENTS.md` records this
in its own AMENDMENT 6 header.

**`docs/SPEC-AMENDMENTS.md`** — amends the frozen risk spec:
1 startup admission gate discriminates by ownership, not elapsed time · 2 protective `flatten` is
idempotent within a bounded window · 3 the seam declares absence; it never substitutes a value for
one · **3-REFINEMENT (ARC 022)** an optional field must name an observable absence · 4 the datafeed
adapter emits bars only where the venue is the bar's source · 5 (D1.38) the broker-datafeed port is
async by default · 6 freshness is per-channel *(issued titled "AMENDMENT 5")*.

**`docs/CHECK-CONTRACT-AMENDMENTS.md`** — amends the check contract:
1 `GUARDED`, a fourth exit code · 2 actuation: verify/correct/install + the independent re-verify ·
3 the coverage trigger broadened · 4 the close-out gate proves durability, not authorship · 5 the
masked hazard, the reason-asserting control, and declared failure policy · 6 the execution plan gets
ONE name.

**Both ledgers hold six.** "Amendment 5" and "Amendment 6" are each ambiguous across the two
documents *as well as* within one of them. Architect rules; B4 folded under the numbering as it
stands on disk.

### 0.5 — RE-MEASURE: **ZERO DELTA** from ARC 026's close

verify.py 17p/1f/2cm/0s/1g exit 1 · pytest 761+1+2 · pre-commit 8/8 · claims 13/13 with 2/2 demos ·
CHECK-DEBT 77 · census 21 three ways. All identical. Stage 1 proceeded.

---

## §0a DEFECTS FOUND IN THIS BRIEF

1. **0.4's premise is false** (above) — the collision is intra-ledger, not cross-ledger.
2. **"Do NOT regenerate the plan" and "full pytest green" are mutually unreachable** (found by C). An
   unregistered check makes `test_end_to_end` red *and* makes `check_derived_claims` red
   (`checks_glob != registry_json`), so pre-commit blocks the commit and the "committed work"
   deliverable is unreachable too. C hand-added its three names to the existing sequential block and
   had `--optimize` (no `--commit`) validate it: **IDENTICAL TO DERIVED PLAN**. Independently
   confirmed at Stage 2.1 — my regeneration produced a byte-equivalent plan, added `[]`, removed `[]`.
3. **"§13 objective 24" is not dischargeable and the brief names it as the item** (found by C). V24's
   criterion is *"prove the **order path** is undisturbed (latency + zero missed exits)"*. §10's Core
   2 Risk Engine does not exist. There is no order path to disturb. Everything built covers the
   datafeed half, and both drill gates say so in their own verdicts. **D1.47.**
4. **My §0a warning to D was inverted, and D measured it** (found by D). I warned that running the
   plan twice in the same order finds nothing. Measured: a same-order pair produces **12 spurious
   findings out of 23 claims**, because `tempfile` and `secrets.token_hex(8)` names differ between
   any two runs. **The same-order sweep is the baseline that makes the detector work at all.**
5. **"`check_hook_suite` arms 2–4 have never been planted" is false** (found by A). Arms 2 and 3 both
   have committed can-fails against the throwaway repo, and D3.14 records arms 1–2 bound against the
   real repository in ARC 023 — as prose. A committed that prose as a test.
6. **My dispatch said `guard_owner: ARC 027` for the coverage baseline** (found by B). The field on
   disk is `owner`. They are distinct concepts in `contract.py` — a forward obligation versus a
   backward receipt.
7. **"Ship a committed can-fail" is satisfiable while measuring nothing** (found by A) — a test
   asserting only a non-zero exit satisfies every word of it. Closed by making every assertion name
   the site or the sentence.
8. **B4 is the brief's own vacuous-success path** (found by B): write a perfect fold, cite it
   nowhere, gate it with nothing — full success, nothing measured.

---

## STAGE 1

### A — the unbound and the partial. **`EXERCISED-NEVER-RED` went to zero.**

```
BEFORE 2ef4585   check_order_path_bans  EXERCISED-NEVER-RED  PASS:7
                 check_python_deps      EXERCISED-NEVER-RED  CANNOT_MEASURE:1,PASS:8
                 check_verify_logging   EXERCISED-NEVER-RED  PASS:7
AFTER  660150f   check_order_path_bans  BOUND  CANNOT_MEASURE:1,FAIL_NEEDS_OPERATOR:9,PASS:11
                 check_python_deps      BOUND  CANNOT_MEASURE:1,FAIL_REPAIRABLE:2,PASS:11
                 check_verify_logging   BOUND  FAIL_NEEDS_OPERATOR:6,PASS:13
```

**A1, D3.25 discharged.** Five plants against the real subject. Plant 1 **edits no file**:
`NIX_PLANE2_DISABLED` is `plane2.DISABLE_ENV`, whose docstring has said since ARC 024 that it exists
so the gate can drive a control — **nothing committed had ever driven it.**

**A3** — nine reds against real subjects: `import tenacity` into `broker_order_ibkr.py`, `import
backoff` into `broker_datafeed_ibkr.py` (rule-of-record clause 2, second subject), a
`run_until_complete` reachable by import into `broker_seam.py` **paired with a test pinning that the
same call inside `__main__` stays ADVISORY** — the ARC 017 calibration, held in both directions.

**A2, and this is the honest half.** Arms 3 and 4 stay UNBOUND **with measured reasons as their
owners**, which is what the brief asked for instead of a fourth arc of silence:

* **Arm 4 is unbindable, proven by attempting the plant.** With `PRE_COMMIT_HOME` pointed at an empty
  directory the gate returns **CANNOT_MEASURE, never FAIL**: `_probe_payload` consults
  `_environments_all_present` before `all_hooks`, so zero hooks becomes a vacuity complaint one layer
  up and arm 4's own branch is unreachable by any plant. Not a false green — a **reachability defect
  that costs the operator the site name**. **D3.29.**
* **Arm 3** — both real-subject venues measured and refused: a tree copy is not a git repo (the gate
  correctly says so), and editing this worktree's `.pre-commit-config.yaml` means editing the live
  commit gate of the tree the suite runs inside, under `pre-commit` itself. **D3.30.**

### B — guards, the ledger, and the evidence-verdict split

**THE FINDING NOBODY AIMED AT: a live safety defect in the trading-session mutation interlock.**
`nixverify.actuation.session_state` swallowed a per-unit `systemctl show` failure and returned
`"inactive"` — **the only verdict `permits_mutation` grants** — carrying evidence reading *"(measured,
not assumed)"*. An unprobed unit opened the interlock under a string asserting the measurement it had
just discarded. Now `unknown`, fail-closed, naming the units; two further non-raising routes to the
same hole closed with it. **It surfaced from B3's sweep for the CLASS** — evidence authored
independently of the measurement it describes — which is why sweeping was the instruction rather than
repairing D3.21's one site. Four true positives across 21 checks and 12 modules.

**B2 — the ceiling bit on the only guard there is, in this arc, not a future one.** Derived from the
baseline's committed git history (extending `_high_water_mark`, not a second mechanism), the live
lineage measures `the bulk check retrofit arc (ARC 025+)` → `ARC 025` → `ARC 027` = **two
re-ownings**. `owner` was deliberately **left unchanged**: re-pointing it at ARC 028 is the exact move
the ceiling forbids. The verdict now prints it — `2 of 2 permitted re-owning(s) used`.

**B1 — 19 → 16, and no count was lowered by naming.** Three artifacts genuinely MEASURED (a planted
banned import flips `check_order_path_bans` red naming `<file>:<line>`, control restored
byte-identically, with a **negative control** outside the derived scope proving the gate is not
simply always-red). Sixteen remain with a per-artifact reason. Two of those are covered by **nothing
at all** — `databases/schema/extract_sources.py` and `scripts/d1_12_reboot_capture.py`: 0 checks, 0
tests. **No path was added to a `SUBJECTS` tuple to make the count fall.**

**B refused to ship a gate for the B3 class, on numbers.** It built the strongest decidable rule,
measured it over-firing >4× on the real population, and — disqualifying — found it **still fires on
`_drive_seal` after the repair**, because the repair changed data flow and the rule reads control
flow. *A rule that cannot tell a defect from its own fix does not encode the property.* The
enumerator ships runnable with a test that re-measures the refusal every run.

**B4 — v1.4 folded**, all seven ledger entries verbatim inside `BEGIN/END FOLDED` markers,
traceability proven **against the committed blob `aaa6a28`** — the only commit that has ever touched
the risk spec — not against a working copy. 18 tests, including a plant showing one character changed
outside a folded block breaks the identity. Two refusals: the §2A list growth AMENDMENTS 4/5 *imply*
but supply no verbatim bullets for (authoring an event signature is editorial, **D3.32**), and
promoting v1.4 to cited authority, because the fold inserts lines and moves every `§x:line`
coordinate the governed roots cite (**D3.33**).

### C — R1-D: the datafeed died, and the detection is about the death

```
trial 0  pid=1219215  SIGKILL(9)  reap=-9  reap_latency=3.3ms
         rate=2,599,846 ticks/s   seq_span=1,559,293   kill_offset=0.5964s
         TRANSITION tick fresh->stale excess=0.2020 (threshold 0.2)
         TRANSITION poll fresh->stale excess=0.9036 (threshold 0.9)
```

**The rate is reconstructed downstream by a separate process from `PriceRingReader.read_seq`** — the
ring's own sequence numbers in shared memory. No number the producer asserted about itself is an input.

**Attribution, the core of C1.** A control arm alone cannot separate *followed* from *caused*, so the
kill offset is **randomised per trial** and the drill reports which clock detection tracks:

```
poll: kill_offset_stdev=0.3460s  detect-kill stdev=0.0039s  detect-start stdev=0.3509s  ratio=91.1
tick: kill_offset_stdev=0.3460s  detect-kill stdev=0.0046s  detect-start stdev=0.3505s  ratio=76.7
CONTROL (no kill)   3.15s @ 2,626,660 ticks/s — stale transitions: []
STARVE (poll clock frozen, process ALIVE) — stale: ['poll']
```

A timer-driven detector predicts the **opposite** ordering of those two standard deviations, and
`test_a_TIMER_driven_detector_is_NOT_attributed` feeds the statistic that hypothesis's own numbers
and requires it to say no. **Resolution bound: 5 ms**, stated in the gate's own evidence.

**C2, per-channel:** two deliberately unequal thresholds (0.20 s / 0.90 s) going stale **0.698–0.703 s
apart**, each tracking its own — plus a starve arm that freezes one channel's venue clock with the
process alive and moves exactly that channel. No collapsed timer produces either.

**C3, Plane 2 across the kill — what survived and what is lost.** Every heartbeat `seq` the state bus
proved the producer emitted was in the journal: **zero lost, every killed arm**, proven by comparing
two independent transports (`/dev/log` and ZeroMQ) both written by the dead producer and read by a
surviving process. **Lost, and named: `process_stop` never happens.** SIGKILL runs no code, so the
journal's last word about a killed `capture.py` is an ordinary heartbeat and **an operator reading
Plane 2 alone cannot distinguish killed from hung from idle.** That absence is *attributable*: the
clean-exit control in the same run **does** emit `process_stop`, and if it did not the gate returns
CANNOT_MEASURE rather than claiming a finding it did not earn. Not bounded, and said so in the
verdict: the bus is a **lower** bound — records written after the producer's last successful `sendto`
leave no trace outside the dead process.

**C's own gate refused itself, correctly.** A real run hit `kill offsets varied by only 0.0262s
(floor 0.08s)`. Three i.i.d. draws from a 0.9 s window fall under the jitter floor a few percent of
the time, and **a gate that reddens at random is a coin toss**. Two changes: the refusal is
CANNOT_MEASURE per §17 (*"I could not tell the two hypotheses apart"* is not a failure of the
subject), and offsets are **stratified** — one uniform draw per band — so every offset stays
unpredictable while the spread gains a floor. 300 draws asserted to clear it.

**C4, cores 6–19 — the spelling refused with a measurement.** "Stay EMPTY of Nix processes" is red on
every run *because of the gate's own runner*: `nix-trading.slice`'s `cgroup.procs` is empty (D1.42),
so every Nix process runs at mask `0-19`, and a live run records `4 of 4 Nix process(es) run unpinned
… 3 of them LAST SCHEDULED on a reserved core` — the occupants being `verify.py` itself and its
shells. Implemented as **"no Nix process is ASSIGNED to a reserved core"**, occupancy reported with
PIDs. It FAILs on a pinned process whose mask touches 6–19, a slice member likewise, a slice cpuset
admitting 6–19, and `SPEC_ASSIGNED[SHARED_POOL] != {4,5}` — the *surplus is not more pool*
enforcement. **D1.46** closes it by pinning things, not by editing the gate.

### D — the instrument-attribution class

**Orders used, stated:** permuted **within a registry block only**, blocks kept in plan order, after
asserting from `DEPENDS_ON` that no block member depends on another — `plan-order`,
`reversed-within-block`, `shuffled-seed-0`, each swept twice. **Cold cache**, 6 `__pycache__` trees
cleared before every sweep, counted and printed. Symlinked roots never followed.

**Stage 2.2 result on the integrated 24-check plan: 0 order-dependent, 0 unstable**, 44 raw claims
per sweep, ~32 s each. ARC 026's `_preamble.py` fix holds. `check_observed_resource_claims` is
excluded by the same self-exclusion it applies to itself, declared as `SELF_EXECUTING`.

**The detector is seen to fire** — two committed controls runnable from the module's own
`--self-test`: a shared on-disk cache (first runner pays), and ARC 026's own lazy-import shape,
reproducing `file-write:…cpython-314.pyc.<NONCE>` and naming both checks.

Two instrument defects found underneath:

* **`check_observed_resource_claims` is structurally blind to this class** — it sweeps
  `sorted(declarations)`, one fixed order, every run.
* **`observe.py` filters `.pyc` noise on one path and not the other.** `_on_open` applies
  `_WRITE_NOISE`; `_on_path` — which receives `os.rename`, importlib's atomic write — does not. Present
  since ARC 025, and **why ARC 026 saw the claim at all.**

D also caught two defects in its own instrument before shipping: a comparator that scored a claim
seen in one order against an empty-but-"agreeing" baseline (`∅ == ∅` is not a stable attribution),
and a negative control that filtered by substring, matched no rule, removed nothing, and passed
against an intact table.

**D2 — 38 cross-document groups over 258 occurrences, enumerated from the DOCUMENTS, not the
registry.** `512 test functions → 782` **disagrees**, and the auditor D2.29 records as deleted is now
committed. ARC 025's `30 paths / 5,019 insertions` is confirmed exact — nothing had ever written
back. **ARC 026's own correction of the reflexivity figure to 9 had itself never been derived**; it
now is. The history line is drawn explicitly: whole `downloads/arc_0*.md` and any occurrence its own
sentence dates to a past measurement is HISTORY and never edited; an undated figure in `CLAUDE.md`,
`CHECK-DEBT.md` or the contract docs is a live control surface.

---

## STAGE 2 — CONVERGENCE

**2.1** Plan regenerated `--optimize --commit`. **Diff against the installed plan: none** — same four
blocks, `added: []`, `removed: []`, 24 checks. That independently confirms C's §0b substitution.

**2.2** Observer in three orders on a cold cache (above): **0 order-dependent, 0 unstable**, including
C's three new drill gates — the ones the brief called most likely to under-declare.

**2.3 Census three ways: 24 == 24 == 24** (executed == planned == on disk).

**2.4** The binding table below, built from 639 observations of this tree, **not carried forward**.

### Integration corrections, attributed

* **`docs/CHECK-DEBT.md` conflicts resolved by reading both texts, never by trusting the IDs.** A's
  **discharge** of D3.25 beat D's untouched base copy of the same row; the four reserved ID blocks
  were disjoint as designed and were unioned.
* **D2.31 and D3.21 marked discharged AT INTEGRATION** — B repaired both subjects and updated neither
  row. The correction is attributed inside each row, with D3.21's residual stated rather than folded
  in: its own deferral condition (*re-take D3.15's discharge evidence*) was **not** met.
* **Every sub-agent wrote a BRANCH figure for the series row and said so** (A 81 · B 82 · D 85 ·
  C 87). None let a branch stand as the arc's total. The integrated **103** is
  `check_derived_claims`'s own `derived:ledger_rows`, not a hand count.
* **Two failures existed only at integration**, and they are ARC 026 finding 4 recurring: R0801
  duplicate-code between `feed_kill_drill.py` and the broker modules, and five `Optional` narrowings —
  **whole-tree properties invisible to the commit-scoped hook every sub-agent ran.** Both repaired;
  the Optionals now assert the reason by name rather than failing with an `AttributeError`.

---

## §2.4 BINDING TABLE — all 24 checks, from 639 MEASURED observations

**BOUND = a committed artifact was observed driving the SHIPPED gate's own bytes to a failing
status.** `CANNOT_MEASURE` and `GUARDED` are reported but never counted as a can-fail: §17 — a
property proven while its subject is unavailable is not proven.

| # | check | verdict | shipped-gate statuses observed | committed artifact / owner |
|---|---|---|---|---|
| 1 | `check_artifact_gate_coverage` | **BOUND** | CM:9, FAIL:12, GRD:12 | `test_check_artifact_gate_coverage.py` |
| 2 | `check_canonical_tree` | **BOUND** | CM:1, FAIL:4, PASS:12 | `test_check_canonical_tree.py` |
| 3 | `check_capture_plane2` | **BOUND** | CM:4, FAIL:2, PASS:12 | `test_check_capture_plane2.py` |
| 4 | `check_core_map` | **BOUND** | CM:3, FAIL:6, PASS:11 | `test_check_core_map.py` |
| 5 | `check_datafeed_bar_seal` | **BOUND** | FAIL:2, PASS:41 | `test_check_datafeed_bar_seal.py` |
| 6 | `check_datafeed_granted_mode` | **BOUND** | FAIL:3, PASS:9 | `test_check_datafeed_granted_mode.py` |
| 7 | `check_derived_claims` | **BOUND-BY-MODIFIED-GATE** | PASS:10 (modified: FAIL:4, PASS:2) | **owner: unassigned.** Its plants substitute into the gate's own derivation, so no committed control drives the SHIPPED bytes red |
| 8 | `check_feed_kill_drill` | **BOUND** | CM:2, FAIL:8, PASS:9 | `test_check_feed_kill_drill.py` — ARC 027 C |
| 9 | `check_hook_suite` | **BOUND** | CM:3, FAIL:6, PASS:16 | `test_check_hook_suite.py`; **arms 3–4 UNBOUND per arm, D3.29/D3.30** |
| 10 | `check_ibgateway_config` | **BOUND** | CM:12, FAIL:1, PASS:2 | `test_check_ibgateway_config.py` |
| 11 | `check_ibgateway_service` | **BOUND** | CM:2, FAIL:12, PASS:2 | `test_check_ibgateway_service.py` + 2 more |
| 12 | `check_name_coherence` | **BOUND** | CM:3, FAIL:8, PASS:16 | `test_check_name_coherence.py` |
| 13 | `check_node_identity` | **BOUND** | FAIL:2, PASS:10 | `test_check_node_identity.py` |
| 14 | `check_observed_resource_claims` | **BOUND** | CM:8, FAIL:3, PASS:1 | `test_check_observed_resource_claims.py` |
| 15 | `check_order_path_bans` | **BOUND** | CM:1, FAIL:12, PASS:20 | `test_check_order_path_bans.py` + `..._drive.py` — ARC 027 A/B |
| 16 | `check_plane2_across_kill` | **BOUND** | CM:5, FAIL:3, PASS:8 | `test_check_plane2_across_kill.py` — ARC 027 C |
| 17 | `check_price_ring` | **BOUND** | CM:4, FAIL:6, PASS:11 | `test_check_price_ring.py` |
| 18 | `check_python_deps` | **BOUND** | CM:1, FAIL_REPAIRABLE:2, PASS:11 | `test_check_python_deps.py` — ARC 027 A |
| 19 | `check_python_runtime` | **BOUND** | FAIL:2, PASS:13 | `test_check_python_runtime.py` |
| 20 | `check_reserved_cores` | **BOUND** | CM:2, FAIL:1, PASS:8 | `test_check_reserved_cores.py` — ARC 027 C |
| 21 | `check_spec_citations` | **BOUND** | CM:1, FAIL:1, PASS:13 | `test_check_spec_citations.py` |
| 22 | `check_state_bus` | **BOUND** | CM:4, FAIL:5, PASS:12 | `test_check_state_bus.py` |
| 23 | `check_venv` | **BOUND** | CM:1, FAIL:2, FAIL_REPAIRABLE:1, PASS:12 | `test_check_venv.py` |
| 24 | `check_verify_logging` | **BOUND** | FAIL:6, PASS:13 | `test_check_verify_logging.py` — ARC 027 A, **D3.25 discharged** |

**23 BOUND · 1 BOUND-BY-MODIFIED-GATE · 0 EXERCISED-NEVER-RED · 0 UNBOUND.**

Row 1's live verdict is now CANNOT_MEASURE (D3.40) — that is the gate's verdict about the *tree*, not
about its own binding. Its can-fail is committed and was observed firing 12 times.

---

## PHASE 3 — CLOSE-OUT MEASUREMENTS

Taken on `/home/bbt/nix`, `__pycache__` purged first, `git add -A` before each.

```
verify.py    20 passed | 1 failed | 3 cannot measure | 0 skipped | 0 guarded     exit 1
pytest       957 passed, 1 skipped, 2 xfailed
pre-commit   8/8 Passed  (--all-files)                                            exit 0
claims       13/13 compared, 2/2 demonstrations                                   exit 0
CHECK-DEBT   104 open  (derived:ledger_rows=104 == stated:series_table_latest_row=104)
census       24 == 24 == 24   (executed == planned == on disk)
binding      23 BOUND | 1 BOUND-BY-MODIFIED-GATE   from 639 observations
```

**The guarded verdict became a cannot-measure DURING THE WRITE-BACK, and that is the arc's last
finding.** Measured before the append: `20 | 1 | 2 | 0 | 1 guarded`. Measured after: `20 | 1 | 3 | 0 |
0 guarded`. **The non-PASS count did not change — only the class of one verdict.**

**Every non-PASS named. They are exactly the three the brief specified as baseline, and nothing else.**

| verdict | check | cause |
|---|---|---|
| FAIL | `check_ibgateway_service` | `127.0.0.1:4002` ECONNREFUSED — Gateway down (baseline) |
| cannot-measure | `check_ibgateway_config` | no API endpoint at `127.0.0.1:4002`; not a misconfiguration (§4.1) |
| cannot-measure | `check_observed_resource_claims` | masked hazard — downstream of the two gates above did not execute, so remaining resource use is UNOBSERVED. §17: never PASS |
| cannot-measure | `check_artifact_gate_coverage` | **the guard expired at write-back.** Verbatim: `checks/gate_coverage_baseline.json:owner — 'ARC 027' has ALREADY COMPLETED — its close-out summary is in sessions/SESSION.md. A guard may only name an arc that can still discharge it (doctrine B.3: an owner that cannot pay is no owner wearing a name). Re-point the marker at a live arc or take the red`. Evidence carries `committed owner lineage 3 value(s) = 2 re-owning(s) of a ceiling of 2` |

**GUARDED checks: none.** The one that was guarded is the row above.

**No further FAILURE. No further non-PASS whose cause is not named.** Three new checks joined and all
three passed; the accepted-uncovered set fell 19 → 16.

### D3.40 — a guard cannot survive its owner's own close-out. **This blocked the arc, and it is the ceiling working.**

Three rules, each individually correct, meet at a state none of them anticipated:

1. ARC 026 (B2) pointed `owner` at **`ARC 027`** so that ARC 027 would discharge it.
2. `contract.completed_arcs` derives completion from `##` headings in `sessions/SESSION.md` — and
   **every arc's close-out appends exactly such a heading.** The instant this arc wrote its summary,
   `ARC 027` became a CLOSED arc and a guard naming it became dead.
3. ARC 027's own ceiling reports `2 of 2 permitted re-owning(s) used`, so walking the marker to
   ARC 028 is the one move explicitly forbidden.

**The general rule this exposes: a guard's owner must always name a FUTURE arc, never the arc in
flight.** No arc before this one hit it, because no arc before this one owned its own guard at
write-back time.

**What was deliberately NOT done:** `owner` was not re-pointed (the forbidden move); the 16 remaining
artifacts were not discharged by being NAMED (B1's trap, and D3.19 already records that naming is not
measuring); the exclusion list was not widened to make the count fall. The committed control
`test_the_REAL_baselines_owner_is_a_single_arc_AND_CAN_STILL_PAY` reddened — correctly — and was
**re-aimed, not weakened**: from *the owner can still pay* (one happy state, permanently red once
false) to a two-directional agreement between the gate's verdict on the real tree and the live
completion record. The shape assertion is kept verbatim. The new form is stricter: it also catches a
**GUARDED verdict standing under a DEAD owner**, which the old form could not see. **Closing D3.40
needs an operator ruling** on what a guard does when its ceiling expires and its debt is genuinely
not dischargeable by the instrument that owns it.

### One failure seen once, characterised rather than averaged over

The first full traced suite reported `1 failed, 956 passed`:
`test_statebus.py::test_TWO_SUBSCRIBERS_are_BOTH_served_because_XPUB_VERBOSE_is_set`, *"1 snapshot(s)
for 2 subscribers"*. **Measured, not inferred:** it passes 3/3 traced and 3/3 untraced in isolation,
passed the plain full suite, and passed a second full traced suite — so it is neither a tracer
perturbation nor deterministic. It is a **wall-clock budget** in a suite that now contains
`check_feed_kill_drill` and its ~2.6M ticks/s producers. Opened as **D3.39** rather than re-run and
forgotten: the property is real and worth holding — without `XPUB_VERBOSE` libzmq delivers only the
FIRST subscribe for a topic, so a second dashboard mirrors an empty table forever, which looks
exactly like a quiet feed — and **a control that reddens under load teaches the operator to
disbelieve it.**

### CHECK-DEBT: 77 → 103 (+26). Thirty opened, three discharged.

Discharged: **D3.25** (A1), **D2.31** and **D3.21** (B2/B3, marked at integration). Opened:
D3.26–D3.30 (A) · D2.34/D2.35, D3.31–D3.33 (B) · D1.46–D1.55 (C) · D2.39–D2.41, D3.34–D3.38 (D) ·
D3.39 and **D3.40** (integration). **The rise is the point.** Doctrine A.7's counter-example is the predecessor
system's monotonic 95 → ~190 across seventeen arcs; the target is per-arc movement. Twenty-three of the
thirty were opened by an instrument or by an **attempted plant that failed to plant** — D3.29
exists because arm 4's defect branch was found unreachable *by trying to reach it*, which no reading
pass produces.

---

## OPEN ITEMS RETURNED TO THE OPERATOR / ARCHITECT

1. **The tap session** — operator task at the console, ~40 min, **now owed by ten arcs.** It discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40,
   Amendment 6's poll-channel lag figure, and C's D1.50 (a real venue clock). **It is the only FAIL
   left in `verify.py` and it is a switch.** Correction to ARC 026's framing: it does **not** owe the
   two Gateway gates' can-fails — those are committed and measured BOUND. It owes their *green*.
2. **§0c — suspended; 0.3 recommends WITHDRAWAL with a replacement. Architect ratifies. Not restored.**
3. **Amendment numbering** — 0.4's inventory is above; the collision is intra-ledger. Architect rules;
   nothing renumbered.
4. **`check_artifact_gate_coverage`'s guard EXPIRED at this arc's write-back (D3.40) and is now
   CANNOT_MEASURE.** ARC 028 cannot walk `owner` forward — the ceiling is at 2 of 2 — and it cannot
   be discharged by naming. **This needs an operator ruling**, and it is the one open item that
   changes a live verdict rather than a document.
5. **`check_derived_claims` is the last unbound thing** — bound only by a modified copy of itself.
   Needs a control that drives the shipped bytes red by perturbing a SUBJECT.
6. **Two artifacts are covered by nothing at all** — `databases/schema/extract_sources.py` and
   `scripts/d1_12_reboot_capture.py`: 0 checks, 0 tests.
7. **D3.36** — registration decision for `attribution_drift.py`. D recommends keeping it a per-arc
   harness and measured why: registering it nests six sweeps inside `observe.PER_CHECK_TIMEOUT_S =
   60s` against 32 s/sweep — permanently CANNOT_MEASURE. **I concur; it stays a harness.**
8. **v1.4 exists and is deliberately NOT authority** (D3.33). Promoting it moves every `§x:line`
   coordinate the governed roots cite. Architect debt.
9. **§13 objective 24 cannot close** until the Risk Engine exists (D1.47); reconnect is undrilled
   (D1.49).

---

## WHAT THE OPERATOR SHOULD TAKE FROM THIS ARC

**The most dangerous thing found was not on the agenda.** `session_state` returning `"inactive"` from a
swallowed `systemctl` failure — under evidence claiming it was measured — is the safety interlock that
decides whether a remediation pass may mutate the box while a session may be running. It was found by
a sweep aimed at *narration that disagrees with its verdict*, not by anyone looking for it. That is
the argument for sweeping classes instead of repairing sites, stated as a measurement.

**The second lesson is that instruments keep being the thing that is wrong.** The census reproduced
the very perturbation class it was built to audit, on its first run. My own §0a warning to D was
inverted and D's measurement proved it. ARC 026's correction of a figure had itself never been
derived. Two integration failures were whole-tree properties invisible to every sub-agent's
commit-scoped hook — the same class ARC 026 recorded one arc earlier.

**ARC 027 closes at exit 1 and says so.** The only FAIL is a Gateway that is switched off. Every one
of the 24 gates standing over this system has now been *observed* turning red.
