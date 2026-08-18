# ARC 036 — RESULTS

**Arc:** R5 the Scoring process (§6.6) + the D3.205 git-env standing gate
**Canonical path:** `/home/bbt/nix` (absolute)
**Interpreter for every figure:** `/home/bbt/nix/.venv/bin/python` (Python 3.14.4)
**Predecessor:** ARC 035 (`0d8ffd4`) · **This arc:** Phase 0 `a9bce2d` → Stage 2 `ec31401` → write-back

## 2026-08-18 — ARC 036: R5 the Scoring process (§6.6), and the D3.205 git-env standing gate

**Canonical path: `/home/bbt/nix` (absolute).** Interpreter for every figure below:
`/home/bbt/nix/.venv/bin/python`, Python 3.14.4.

### Phase 0 — the blocking gate, and a brief corrected against the frozen spec

`check_git_env_scrub` derives every `git` subprocess call in the tracked tree by AST on
every run and asserts each routes through `nixverify.gitenv.scrubbed_env`. There is no
accepted-call-site list in the file: a new unscrubbed call reddens it with nobody
remembering anything. That is the whole difference from D3.22, a correct rule applied
per site from memory that recurred three times in one arc.

**Its first run over a tree everyone believed clean reported fourteen sites, six real.**
`scripts/monitor.py:838` had no `env=` at all and is executed by `check_monitor_tui`
inside every commit — the ARC 035 outage's shape, one file over. `check_runtime_gate.py`
ran its `git hash-object` ORACLE on an inherited environment. Two test modules carried a
fifth and sixth private re-spelling of the scrub as a dict comprehension.

**Then it reddened on itself.** Its own `_git` helper took `env` as a parameter, so the
call site read `env=env` and no reader could tell the scrubbed half from the unscrubbed
one. The helper now scrubs internally; `MARKER_SCOPE` is an ENUMERATED pair of paths
rather than a directory rule, because widening it to `checks/` would have bought the
green by making every gate eligible for a one-line silencer.

Both halves are driven and the D3.205 plant with them: an unscrubbed `git add -A` under
GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE MUST corrupt a throwaway victim's index and the same
argv through the scrub must leave it byte-identical — and **if the corruption half stops
corrupting the gate FAILS naming the control BLIND**. The whole routine re-runs with the
three variables planted into what the fixtures inherit, which is where the defect hid.

`check_observed_resource_claims` then corrected the gate's own `RESOURCES`: it shipped
claiming `("subprocess:git",)` on the reasoning that its TemporaryDirectory needed no
claim, and the observer reported thirty real `file-write:/tmp/gitenv-gate-*` uses.

**The seam was frozen against §12.7, not against the brief.** The brief asked for a
"shared-memory sole-writer publish". §6.6:459 does say "in shared memory" — but §12.7 is
LOCKED, later, NAMES the ranking table §6.6 among the tables it governs, and says *"Mirror
model, NOT raw shared memory … raw shared state tables would let multiple processes touch
the same bytes — reintroducing locks, races, and torn reads, and reducing the
single-writer principle to fiction."* Its sole exception is the price firehose, "prices
only, never financial state". Building the brief's version would have reintroduced that
surface **while still passing a sole-writer test**. `scripts/nixscore/seam.py` therefore
carries no bytes of its own and rides `nixbus.statebus`.

**A plant caught the seam gate blind and the gate was repaired, not the plant.** Breaking
`fresh()` to `return self._applied_at is not None` — a mirror that calls a dead table
fresh forever — left every arm green because `arbitrate` computes age inline. `fresh()` is
now driven from both sides of the boundary plus never-fed.

Provenance, measured: three untracked artifacts trace to commit `f139c57`; the root
`status_board_leaderboard_spec.md` was byte-identical to the `docs/` copy (sha256
`b4452bc3`) and was deleted, recoverable. `DASHBOARD_PY_TECHNICAL_REFERENCE.md` (a prior
system's dashboard — Titan Control 2.0, node01, macOS) and `Nix_Logo_Package.zip` are in
NO commit on any branch and were **tracked rather than deleted**, because tracking is
reversible and deleting an unbacked file is not.

### Stage 1 — five sub-agents, five worktrees, five things measured

**A — the EMA engine.** Span derived from `risks/scoring.config.json`, proven by writing
two configs (3 and 20) and showing the same advance smooths differently; two plants, one
AST and one keyword-arg invisible to the AST arm, each redden it. Ranking proven on two
axes that DISAGREE: 1000/day on 20 closes beats 400/day on 400 closes while close counts
run 20:1 the other way; then a sharper pair with identical totals AND identical counts,
separated only by when. §12.11 restart-only proven by killing a process holding a live
engine while its config changed underneath it.

**A's headline is a finding: nothing in this tree writes a realized P&L figure.** The
brief said the engine "reads closed-trade realized P&L from Plane-1 (the durable record
ARC 035 landed)". Plane-1 carries none — measured against the frozen schema and by grep,
consistent with ARC 035's own D3.213. The engine is built and correct and its input does
not exist (D3.220).

**B — the ranking table over §12.7's real transport.** `ipc://` bind is **NOT exclusive**:
a second publisher on a live endpoint succeeds. So the transport contributes NOTHING to
sole-writer; the identity stamp at the consumer is the entire mechanism (D3.232). Proven
by killing the real publisher (rc −9) and letting an impostor rebind: the surviving SUB
auto-reconnected and delivered 16 impostor messages / 5,737 bytes, all refused,
`foreign_rejected` 0→16, `applied` frozen at 7, and the impostor's deliberately REVERSED
table did not flip the winner. Concurrency: 2,113,317 reads overlapping 136,590 writes
across 243 table generations — the two-lookup path **tore 49 times**, the single-capture
view **0**. Backpressure: 4,000 publishes in 0.039 s, worst `publish()` 0.128 ms.

**C — the FCFS fallback, killed for real.** pid SIGKILLed mid-contention, reaped **−9**,
`/proc` gone, against a SIGTERM control reaping **7** — so "died" cannot be satisfied by
"exited". 135,436 RANKED decisions before the kill and 340,712 after; worst
inter-decision gap **3.287 ms**, and the gap straddling the kill instant is the same
3.287 ms; zero order-path exceptions. **Order flow did not halt.**

**C found the number that is not in the spec: 144,699 decisions were RANKED from a dead
process's frozen table over a 0.483 s window.** The subscriber socket outlives the
publisher, so the mirror stays complete, populated and confident, and the exposure scales
linearly with `stale_after_s`. The brief framed the danger as the fallback failing to
answer; it always answers. The real exposure is that it answers RANKED, from a corpse
(D3.244).

**D — the score outlives its process.** Writer pid wrote four pairs at nonce-derived EMAs
and SIGKILLed itself (`returncode == −9`); a different pid read back byte-identical
values while a cold-start control in the same reader held 0 pairs. Quarantine archived
exactly `alpha`'s two pairs and left exactly `beta`'s and `gamma`'s — set equality both
ways, over a fixture the gate REFUSES to judge unless it is genuinely entangled. Archived
is distinguishable from absent. Atomicity: 10 outside SIGKILLs into churning victims
across **10,447 durable writes**, every post-kill store parsed, every seeded pair on
exactly one side.

**D found supervision auto-resurrecting quarantine.** `CrashLoopBreaker._quarantined` is
an in-process dict: three restarts ⇒ quarantined; a NEW breaker over the same fsynced
ledger ⇒ **not** quarantined, while `restarts_in_window` still returns 3 at a cap of 3.
§4:274 says quarantine is not auto-resurrected. Worse, `may_relaunch` returns a §18 reason
that contradicts the ledger it just read (D3.250). The §12.11 restore counter-reset is
in-memory too (D3.251).

**E — the Allocator READS the table, and the flip flips.** Two strategies GO on ES with
headroom 17,500 and margin 12,000/contract: EMA 900 vs 100 ⇒ A sized 1 contract, B
`zero_after_clamp`; **ranking reversed ⇒ B sized, A clamped.** Non-vacuity measured first:
each contender alone sizes 1 contract, so capital genuinely could not satisfy both. Seven
outage routes driven — no mirror, never-fed, stale, foreign writer, absent row, tied EMAs,
and a mirror raising on every verb — every one produced a proposal per contender in
arrival order with the head still sized. **No route can produce a deny.**

E found a raising mirror KILLING the race (§6.6:467-468 violated by the module citing it)
and the port and the seam reading one table against two clocks. Both repaired.

### Stage 2 — the merged tree found a gate that was green while it broke four others

`check_scoring_consumption` ended its loader in
`finally: sys.modules.clear(); sys.modules.update(saved_modules)`. That is not a restore,
it is an **eviction of every module imported since the snapshot, including C extensions**.
Under `verify.py` it runs before four bus-driving gates; `zmq` had not yet been imported
when the snapshot was taken, so the clear dropped it, the next `import zmq`
**re-initialised the Cython backend while libzmq's loaded state persisted**, and a SECOND
`zmq.error.Again` class appeared. `StatePublisher.service`'s entirely correct
`except zmq.Again:` could not catch what the backend raised.

> **raised cls id 365732624 vs caught cls id 366035056, SAME: False**

Four gates that pass alone reported `Again: Resource temporarily unavailable`. **The
offending gate was GREEN throughout — it damaged only its successors**, which is why no
branch could see it. File descriptors, threads, fork/RLIMIT_NPROC, the tmpfs, zmq module
identity and stale bytecode were each ruled out by measurement first. Fixed at the cause;
`verify.py` 75/3/**7**/0/1 → 80/3/**2**/0/1 (D3.270).

**The integrator's own error is recorded as D3.272.** My conflict resolution silently
dropped fifteen ledger rows — C's, D's and E's — because on three merges the series row
and that branch's rows sat in one hunk. **`check_derived_claims` was GREEN across the
loss**: deleting rows and re-deriving the count agree perfectly, so the gate can catch a
stale figure but never a lost row. Found by accident when an unrelated edit could not
locate D3.253. Recovered from the branches. The class stays open.

**D3.214 was paid in full inside the arc that opened it.** All seven caller-less seam
entry points now have shipped callers; `_ARC036_PHASE0_CARRIED` is the empty tuple, kept
rather than deleted because the `vanished` assertion is what made the carry binding. Four
branches each shrank it to a DIFFERENT set — C to 3, E to a different 3, B to 2, D not at
all — every one right on its worktree and none right on the merge.

**D3.231 discharged** (the frozen seam's torn read, repaired although unreachable under
today's single-threaded consumer contract) and **D3.253 discharged** (a bare `[:25]` hid
32 of 57 findings from the integrator who was reading it at the time).

### D3.205 closed under the exact condition that triggered it

Five worktrees, each running git. `core.bare = false` on the canonical tree **and on all
five**. 49 git invocations across 347 tracked modules: 47 scrubbed, 2 declared controls.
Canonical index intact at 472 tracked files.

### Close-out

`verify.py` on trunk under `/home/bbt/nix/.venv/bin/python`:
**81 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded, exit 1**
(ARC 035 closed at 73/3/2/0/1). The two FAILs are `check_ibgateway_service` — the standing
tap-session failure, the only code-independent one — and `check_uncalled_entry_points`,
its standing state, whose carried set lives in a suite that is 62/62 green. **No further
FAILURE, and no further non-pass whose cause is not named.**

GUARDED: `check_artifact_gate_coverage`, owner **ARC 037** — re-pointed from ARC 036 at
close-out because §0g would otherwise ship a marker owned by an arc that can no longer
discharge (D3.273). Full pytest **3049 passed, 2 skipped, 2 xfailed, zero failures**.
Binding census: **BOUND=74**, and all seven of this arc's new checks are BOUND — each
observed producing a real FAIL under a plant. Census three ways: 86 checks on disk / 86 in
the registry / 86 executed. CHECK-DEBT **222 → 250**.

### What did NOT land, said plainly

Nothing writes realized P&L, so the EMA has no production input (D3.220). Nothing feeds
the mirror in production — no subscriber holds the `ranking` topic and no writer publishes
it — so **FCFS remains the live policy** and the RANKED path is exercised only by gates
(D3.263). Ordering landed; **weighting did not** — `NEUTRAL_WEIGHT` is still 1.0 under
both policies (D3.260). The store is built and not wired to supervision's quarantine
transition (D3.252). Two classes named `RankingReader` survive in one package, and the
tree's own instrument credits one's call sites to the other (D3.271). Live venue untested
by design; the EMA span is a default awaiting real realized data.

### Post-write-back re-measure (ARC 036), banked before the marker

`sessions/SESSION.md` now names ARC 036 complete, so the D3.40/D3.144 guard-owner
transition is **live, not hypothetical**: `nixverify.contract.completed_arcs` returns an
empty error and reports `36 in arcs = True`, highest 36. That is the mechanism running
against this arc's own summary — the condition D3.274 was written to be falsified by.

**D3.274's prediction, stated before the write-back, HELD in both halves:**

| | predicted | measured after |
|---|---|---|
| `check_artifact_gate_coverage` | GUARDED, unchanged | **guarded** |
| `verify.py` | 81 / 2 / 2 / 0 / 1, exit 1 | **81 passed / 2 failed / 2 cannot measure / 0 skipped / 1 guarded, exit 1** |

The guard survived because D3.273 re-pointed its eight exclusions ARC 036 → ARC 037
*before* the write-back. Had they been left naming ARC 036, this re-measure would have
read GUARDED → CANNOT_MEASURE and the guarded count would have gone 1 → 0 — which is the
transition ARC 034 measured the absence of, and the reason the prediction is worth
writing down first. **A re-measure taken after the fact and then described is not a test
of anything.**
