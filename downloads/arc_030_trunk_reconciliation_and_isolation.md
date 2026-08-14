# ARC 030 — Trunk Reconciliation, Enforced Isolation, and the Coverage Close

**Module:** repository integration + checks subsystem
**Predecessor:** the unmerged stack — `main` has not advanced in roughly eight arcs; ARC 022 through
CRUCIBLE-DEPSPLIT live on branches that were never promoted to trunk.
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking (DISCOVER, do not act) · Phase 1 trunk reconciliation (serial,
one operator ruling) · Stage 2 three parallel sub-agents · Stage 3 convergence · Phase 4 close-out.

**Why this arc exists.** Every recent arc banked to its own branch and none reached `main`. The work is
durable and the history is linear, but there is no authoritative trunk collecting it, which is why the
running record has felt unlocatable. This arc reconciles the stack to `main` first, then lands the
isolation and coverage debts on that clean trunk. **No new product work** — this is consolidation
before R3 (the Allocator).

**Operating mode:** parallel arcs against this machine are DELIBERATE. The goal is not to forbid
parallelism but to make it safe — which is why the stack diverged in the first place, and why sub-agent
A builds real isolation.

---

## §0a — Self-audit clause, applied to THIS brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

**This brief asserts a merge topology the architect has NOT fully verified.** The visible history shows
`arc-crucible-depsplit → arc-crucible-calendar-infra → arc-029-integration`, and `main` far behind — but
whether ARC 022–028's integration branches ever reached `main`, and by what path, is NOT established
from the architect's chair. **Phase 0 MEASURES the true topology and REPORTS it. It changes nothing.**
Every merge decision in Phase 1 derives from what Phase 0 measured, never from this brief's sketch of
the stack. If the measured topology contradicts the description above, the measurement wins and that is
a finding, not an error to reconcile away.

## §0b — Spellings are non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-runnable-artifact · §0f explicit-status-or-owner · §0g owner-names-a-future-arc (standing)

Resolve any rule named by an arc-brief label to its ledger identifier before acting (D3.81).

## §0h — History is durable; do NOT rewrite it (NEW, this arc)

The reconciliation is a FORWARD operation: merges and, where the graph permits, fast-forwards. **No
rebase, no force-push, no history rewrite on any pushed branch.** The deprecated MON-1 commits are
interleaved in `arc-029-integration`; the temptation is to rebase them out. **Refuse it.** Rewriting a
pushed branch to strip commits is how durable work is lost and how a public repo's history forks. If
MON-1's `check_monitor` must not reach trunk, it is removed by a FORWARD commit (delete the check file,
recorded), never by editing the past. Proof of durability is HEAD advancing (§0d); a rewrite that makes
the tree look right while discarding reachable commits is the inverse.

---

## PHASE 0 — Measure the true state (SERIAL, BLOCKING, CHANGES NOTHING)

**0.1 — The topology.** For `main` and every arc branch from 021 forward, report: is it merged into
`main`; if not, what is its merge-base with `main`; what is the linear chain from `main`'s HEAD to
`arc-crucible-depsplit`'s HEAD. Produce the actual graph, not a description of it. The expected shape —
to be confirmed or refuted — is one long unmerged column:
`main → …022–028… → arc-029-integration → calendar-infra → depsplit`.

**0.2 — What is unmerged.** List every commit reachable from `arc-crucible-depsplit` and NOT from
`main`, grouped by arc. This is the set Phase 1 promotes. State its size.

**0.3 — The MON-1 commits.** Identify every deprecated monitor commit interleaved in the chain
(`a9793aa` and siblings, plus `checks/check_monitor.py`, `scripts/monitor.py`, `harness.py`,
`pty_test.py`). Report where they sit in the graph and what depends on them. **Do not remove anything
yet** — Phase 1 rules on disposition.

**0.4 — The current check state, from the current branch.** `verify.py`, pytest, pre-commit, claims,
CHECK-DEBT, census, binding table, on `arc-crucible-depsplit` as it stands. This is the baseline the
reconciled trunk must reproduce or improve. Name every FAIL and every non-PASS by owning arc —
`check_monitor` is MON-1's (deprecated), `check_ibgateway_service` is the tap session.

**0.5 — Worktrees and live arcs.** `git worktree list`. Any worktree other than the canonical one is a
live or abandoned parallel arc; report each and whether its branch is in the unmerged set. A parallel
arc mutating the tree during this reconciliation is the ARC 029 collision — this arc must know what
else is running before it merges anything.

**STOP after 0.5. Report the full picture and the proposed reconciliation order. Phase 1 proceeds only
on the measured graph.**

---

## PHASE 1 — Reconcile to trunk (SERIAL, ONE OPERATOR RULING)

**The operator has confirmed the Crucible line (calendar-infra + depsplit) is KEPT.** It merges to
trunk with the rest.

**1.1 — Promote the stack to `main` in dependency order**, oldest unmerged first, each a forward merge.
Where the graph genuinely permits a fast-forward, a fast-forward is fine; where it does not, a true
merge commit — and do not narrate one as the other (ARC 029 called a two-parent merge a fast-forward;
harmless there, but it is the narration-vs-reality class). After each promotion, `main` must still
build: run `verify.py` and pytest at each step, and stop on any regression that is not a
pre-existing, owned FAIL.

**1.2 — MON-1 disposition (§0h — forward only).** `check_monitor` is deprecated and currently FAILS.
**[ARCHITECT RULING — revocable]** Do NOT rebase it out. Bring the commits to trunk with the rest so
history stays intact, then in a FORWARD commit remove `check_monitor` from the registry and delete the
check file (the monitor scripts themselves are harmless and may stay as untracked-or-tracked tooling —
operator's call, but they must not trip `check_artifact_gate_coverage`, so if tracked they need
coverage or an exclusion). The result: trunk history contains the monitor work, trunk's verify.py does
not run a deprecated failing check. Record the deprecation in CHECK-DEBT with the reason.

**1.3 — One authoritative HEAD.** After promotion, `main` is the trunk again and
`arc-crucible-depsplit`'s work is reachable from it. Report the new `main` HEAD and prove the unmerged
set from 0.2 is now empty.

---

## STAGE 2 — Three parallel sub-agents (from PROVISIONED WORKTREES, on the reconciled trunk)

### SUB-AGENT A — Isolation, enforced (index AND environment)

**A1 — Per-worktree git index.** Each concurrent arc runs against its own worktree and its own index,
never the shared canonical index. ARC 029's collision was a shared index — one session's staged work
landed in another's commit. Remove the shared mutable surface.

**A2 — Environment isolation (the CRUCIBLE lesson).** CRUCIBLE-DEPSPLIT rebuilt `.venv` from scratch
while other arcs could run. Worktree/index isolation does NOT cover the shared Python environment —
every gate on the box resolves through `.venv`. Either each concurrent arc gets its own venv, or venv
mutation is serialised behind a lock a gate can observe. **Prove the hazard before fixing it:** a gate
run against a half-rebuilt `.venv` reports artifact failures; show it, then show the fix removes it.
CRUCIBLE's `.venv`/`.venv-dev` split is the structural start — gate that the split cannot silently
re-merge.

**A3 — `check_untracked_attribution`'s real binding.** EXERCISED-NEVER-RED because it cannot see a
commit on another branch — the exact ARC 029 vector. Extend it: a write to the canonical tree from
outside the current arc's lineage, whether untracked, staged, OR committed on a branch this arc's HEAD
does not contain, reddens and is named. Prove the can-fail by committing a file on a side branch. If a
cross-branch commit cannot be attributed by any `git` fact available at gate time, say so WITH the
measurement and record the boundary — an honest limit beats a green that means nothing. A test that
only stages an untracked file re-proves the arm that already worked.

**A4 — Gate the isolation mechanism itself.** Prove two arcs in two worktrees cannot write each other's
index or corrupt each other's venv. Demonstrated failure path: without the mechanism, worktree 1's
staged file is visible to worktree 2's commit; with it, it is not.

### SUB-AGENT B — Coverage retrofit, part 1

**B1 — Eight of the sixteen** artifacts get real per-artifact can-fail coverage: a check driving the
artifact to an observable wrong state and reddening, a committed runnable artifact (§0e), non-vacuity
proven before the plant, reason asserted not exit code. **The sixteen** = the thirteen D3.104
ceiling-tripped artifacts + the three ARC 029 exit modules (`flatten.py`, `survival.py`,
`coldstart.py`) admitted `measured_by=tests`. Partition by SHAPE, not count — one harness serves
several like-shaped plants; state the partition first.

**B2 — Each artifact leaves the exclusion the moment its real check binds.** The bucket shrinks as a
measured consequence, never by lowering a number. The ARC 025 ratchet still forbids silent growth.

### SUB-AGENT C — Coverage retrofit part 2, and the filesystem-walk class

**C1 — The other eight**, same contract. The hardest are the "executed by every import" shapes
(`scripts/nixverify/__init__.py`): a plant there changes the environment under every gate, so it must be
provably isolated or it reddens the whole suite. Where an artifact has no drivable failing state, **that
is a finding about the artifact** — keep it excluded with an honest owner; do not manufacture a plant
that measures nothing.

**C2 — The coverage gate moves off GUARDED toward PASS only to the extent coverage is real.** Any
honestly-uncovered artifact leaves the gate GUARDED with a shrunken, justified exclusion and a named
owner. GUARDED is the honest verdict, not a failure to reach green.

**C3 — Generalise the AppleDouble/`.claude` filesystem-walk hardening (D3.110).** ARC 029 hardened three
gates against `._*` sidecars and `.claude/` worktree pollution that crash `rglob` walks on non-UTF-8
bytes. Prove EVERY filesystem-walking gate skips both classes or fails loud with the path named. A gate
that dies on a sidecar is CANNOT-MEASURE reported as a stack trace — the worst verdict shape.

**C4 — CHECK-DEBT reconciliation.** Discharge every D3.10x row this arc closes. Report the derived count
against the stated series row; a narrated total disagreeing with its enumeration is the D3.82 class and
the auditor must catch it in this arc's own results.

---

## STAGE 3 — Convergence (SERIAL)

**3.1** Regenerate the plan (`--optimize --commit`) on trunk; report the diff.
**3.2** Observer in at least three orders on a cold cache, each swept twice — up to sixteen new checks,
every one a fresh false-declaration candidate.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f), not carried forward. The retrofits should
raise the BOUND floor; any landing UNBOUND or EXERCISED-NEVER-RED is a finding named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk. Baseline: `check_ibgateway_service` FAIL (tap session) + the standing
   cannot-measures. **`check_monitor` should be GONE, not failing** (1.2). A further FAILURE is a
   finding, and so is any further NON-PASS whose cause is not named. Name every GUARDED check and print
   its owner verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table WITH the coverage disposition: how many of sixteen bound real, how many remain
   honestly excluded, the exclusion's new size and every owner.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   per D3.22 use the `gitenv.py` scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`, **on the reconciled trunk**: append to the END of
   `sessions/SESSION.md`; **overwrite** `downloads/RESULTS.md`; `cat` both as the final action; **prove
   HEAD advanced AND that `main` is the authoritative trunk with the unmerged set empty** (§0d + 1.3);
   state the absolute canonical path.
6. Clean up temp files and remove abandoned worktrees/throwaway branches created by this arc.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The tap session (operator, hardware) · any R2/R3 product work · rewriting history to strip MON-1
(§0h — forward removal only) · the monitor tooling's own revival (deprecated; if it returns it is a
future arc that adopts A's isolation).

---

## Open items returned to the operator / architect

1. **The tap session** — operator task at the console, ~40 min, owed by fifteen arcs. Discharges D1.12
   reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl` precondition
   invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40, SPEC-A6's
   poll-channel lag figure, D1.50, and the two Gateway gates' green. The only code-independent FAIL.
2. **Seam questions (D3.109)** — does `ExecutionReport`/`ExecutionLedgerPort` belong in the frozen seam;
   is `PositionRow.size` signed. Architect debt.
3. **v1.4 remains deliberately not authority** (D3.33), now carrying SPEC-A7 and the EventKind additions.
4. **After this arc: R3, the Allocator** — first consumer of the Limiter's financial picture. It builds
   on a reconciled trunk with the isolation and coverage debts closed.
