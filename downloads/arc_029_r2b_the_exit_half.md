# ARC 029 — R2-B: The Exit Half

**Module:** Risk Engine / Limiter (Core 2) — the protective path
**Predecessor:** ARC 028 (merged)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** mega arc. Phase 0 serial and blocking · Stage 1 four parallel sub-agents · Stage 2 serial
integration · Stage 3 convergence · Phase 4 close-out.

**Verifies:** V33 (stops), V34 (cold-start). Advances §13 objective 24 by supplying the order path it
has been blocked on (D1.47).

---

## WHAT CHANGES WITH THIS ARC

ARC 028 built a Limiter that gates, reserves, publishes and logs — and **cannot exit**. Every gate in
that arc said so. This arc builds the half that protects money once it is committed.

§14's locked invariants that this arc is directly accountable to:

- **Every uncertainty resolves toward flat.** Known state beats optimal state.
- **The exit/protective path has zero wire/delivery dependency.**
- **Restart = flat, always.**
- **Detection may live anywhere; execution of any flatten is Limiter-only** (Sentinel excepted).
- **Survival is watched on net-liq; sizing is computed on cash. Never conflate.**

**One honest limitation to carry in the verdicts from the start:** these stops are *synthetic*, held
in the Limiter's memory by deliberate design (§12.1 — *this is our software, not a broker-side stop;
that prohibition stands*). A synthetic stop dies with the process that holds it. The Sentinel is what
covers that gap and the Sentinel is **R4**. Until it exists, a killed Risk Engine is an unprotected
position, and no gate in this arc may imply otherwise.

---

## §0a — Self-audit clause, with an amendment the architect owes

*What would have to be true for this step to complete successfully while measuring nothing?* Report
any step whose success is compatible with measuring nothing.

**AMENDMENT, and it is about the architect's reliability, not the agent's.** Across ARC 027 and ARC
028, **four** hazards stated in these briefs were measured and found **backwards**:

| stated | measured |
|---|---|
| a same-order observer pair finds nothing | it produces 12 spurious findings of 23 claims and is the baseline that makes the detector work |
| a double release is the dangerous one, invisible to a naive leak test | the double release is the **loud** one — it breaks `Σ == fsum(TAKEN)` instantly; **the leak** breaks no identity at all and §11.7 is structurally blind to it |
| a crash-gap test that never crashes measures nothing | **a SIGKILL cannot test fsync at all** — `--no-sync`, genuinely killed, leaves 4128 rows readable, because a dead process's dirty pages belong to a living kernel |
| the hazard is a code path keyed off a config value | that is what config **is**; the real hazard is the inverse |

**Standing: every hazard direction stated in an architect brief is a HYPOTHESIS, not a finding.**
Measure it before relying on it, and if it is backwards, say so with the measurement. This brief
states several. Treat every one of them that way.

## §0b — Architect spellings are non-binding (standing)

Spellings are sketches; invariants bind. Refuse with a measurement anything that would degrade an
instrument, blind a gate, or make a check report over a subject it never drove.

**And per ARC 028 D3.81:** arc-brief section labels are **per-arc and collide across arcs**. `§0c` in
a brief is not the on-disk rule `0c`. If this brief names a rule by a label, resolve it to the ledger
identifier before acting — withdrawing by label nearly deleted a live rule last arc.

## §0d–§0g (standing, unchanged)

**§0d** the write-back gate proves HEAD advanced and contains this arc's paths. **§0e** binding
requires a committed runnable artifact observed driving the shipped gate's own bytes to a failing
status. **§0f** every check carries an explicit status with a named artifact or owner; the binding
table is rebuilt, never carried forward. **§0g** a guard's owner names an arc that can still
discharge it, validated at assignment.

---

## PHASE 0 — Corrections, isolation, and the exit seam (SERIAL, BLOCKING)

**0.1 — Re-measure.** Expect ARC 028's close: `26 passed | 1 failed | 3 cannot measure | 0 skipped`,
exit 1, 30 checks; pytest 1204 + 1 skipped + 2 xfailed; pre-commit 8/8; claims 13/13 with 2/2
demonstrations; CHECK-DEBT 142 derived; census 30 three ways; 30 BOUND. **Any delta is a finding.**

**0.2 — The narration defect recurred inside the arc that fixed it.** ARC 028's ledger reads
*"Thirty-seven opened"*; its own enumeration is `D3.41–47 · 51–56 · 61–66 · 71–78 · 81–84 · 91–98 ·
99 · 100` = **41**, and `104 + 41 − 3 = 142`, which is the derived figure. Thirty-seven gives 138.

**D3.82 is therefore confirmed twice in consecutive arcs, both times in the document reporting the
finding, and it is this arc's opening item.** Extend the auditor's extractor to the class it named as
its own blind spot: counts spelled in words, and **intra-sentence arithmetic** — a stated total
reconciled against an enumeration in the same passage. Correct the narrated figure; do not edit
`SESSION.md` (operator ruling, `CLAUDE.md` directive 6).

**0.3 — D3.99, and this must land BEFORE any parallel dispatch.** Two artifacts, 811 lines, in the
canonical tree and in no commit on any branch, appearing inside ARC 028's Stage 1 window, unreported
by any of five sub-agents, carrying a test that describes faults in a `v1.0.0` that never existed.

**[ARCHITECT RULING]** Not adopted, not restored; preserved with sha256 for deliberate operator
action. **The finding is not the files — it is that worktree isolation is requested, not enforced.**
Five sub-agents were told to stay in their provisioned worktrees and something wrote to
`/home/bbt/nix`. That is a boundary declared rather than measured, inside the agent harness itself,
and this arc dispatches four more sub-agents.

Build the gate: untracked appearances in the canonical tree are **attributed** — path, mtime, and
whether any commit on any branch contains them. They were caught last arc only because `git add -A`
staged them into three commit gates; that is the standing rule getting lucky, not a detector.

**0.4 — SPEC-A7 (architect ruling on D3.55).** §3:151's terminal set names *blackout-onset
cancellation*; §3:173 says *Blackout/**HALT** onset*. **They are not synonyms in this spec's
taxonomy** — Phase A lists the HALT flag separately from the blackouts, HALT is §12.5 with six
setters, blackouts are §6.1–6.3 and clear on schedule.

**Decisive:** `CANCEL` is already a member *alongside* `BLACKOUT_ONSET`, so the spec has already
decided that cancellation cause is worth distinguishing. **Add `HALT_ONSET` as a distinct terminal
path.** Amend as **SPEC-A7**; do not edit the frozen document in place. The seam gate should redden
until the member lands — report if it does not.

**0.5 — Four zero-coverage artifacts** (ARC 028 0.5 found four, not the two the brief claimed):
`databases/schema/extract_sources.py`, `scripts/d1_12_reboot_capture.py`, and the `nixverify` package
initialiser executed by every import and asserted about nowhere. Real coverage or honest per-artifact
owners. **Nothing discharged by being named** (D3.19).

**0.6 — Freeze the exit seam.** Types and ports for stop state, the protective-flatten trigger set,
the net-liq watch, and cold-start reconciliation. Declare sync/async per verb with the reasoning, per
§5's single-threaded loop. Land declarations only; no behaviour. **Per ARC 028's finding, prove the
seam gate actually reddens on a change to each declared property** — last arc's seam gate passed on
all four ledger verbs rewritten `async def` and on a deleted field.

---

## STAGE 1 — Four parallel sub-agents

### SUB-AGENT A — Synthetic stops (§4, V33)

**A1 — Conversion happens once, at confirmed fill.** The GO carries stop intent as a tick
**DISTANCE, never an absolute price** — the strategy signals before it knows its fill, so distance
stays valid through slippage. The Limiter converts distance → absolute price **once the fill is
confirmed**, so a stop can never land on the wrong side of entry. Missing, zero or invalid distance
⇒ **deny** (§3 ingress guard, §15 C3).

**A2 — `fixed`:** anchored once at `fill ± initial_distance`, static thereafter. Compute-once-at-fill.

**A3 — `trailing`, and the activation rule is the subtle part.** Two distances: `initial_distance`
(where the stop first sits) and `trail_distance` (the gap behind the high-water mark). The stop
**holds at the initial level until price advances far enough that the trail distance would sit
tighter than the initial stop**, and only then begins trailing — so it **only ever moves in the
strategy's favour and never jumps backward at activation**. Once trailing it ratchets behind the HWM
every tick and never gives ground back.

**§0a, stated as hypotheses to be measured:** *never moves backward* is trivially satisfied by a stop
that never moves at all — prove it does ratchet. A trailing test whose price path never reaches the
activation threshold exercises only the fixed case under another name. And the activation instant is
where a backward jump would hide.

**A4 — Per-tick maintenance reads the price cache** (§11, hot path = cache reads and arithmetic).
Per-tick ratchets are **not** logged (§12.10 — chatty, derivable); the final trail level rides the
`closed` row.

**A5 — Gate the prohibition.** *This is our software, not a broker-side stop — that prohibition
stands* (§12.1). Prove no code path places a broker-native stop order. Related in spirit to
`check_order_path_bans`; extend rather than duplicate.

### SUB-AGENT B — Protective flatten and the trigger set (§3, §14)

**B1 — The trigger set from §3, transcribed and closed:** synthetic stop · stale price · net-liq
floor · session close · uncertainty · orphan · sentinel. Session close is **R4**; declare the trigger,
do not build its calendar.

**B2 — Zero wire dependency is the invariant, and absence is provable only by removal.** §14 requires
the protective path to have zero wire/delivery dependency: Limiter → broker-order **in-process,
direct call** → sender thread. **Prove it by removing the wire** — the state bus down, ZMQ
unavailable, the picture unpublishable — and showing the exit still fires. A test with the transport
healthy cannot see this property.

**B3 — Protective always wins over discretionary**, and the strategy is notified `closed, reason=X`
with a hard FSM reset. **A sequential test proves precedence only if the two were actually in
contention** — construct the race.

**B4 — Onset cancels pending ENTRY orders, exits untouched** (§3). No order may fill inside a window
it was not approved for. With SPEC-A7 this covers both blackout and HALT onset, each releasing its
reservation under its own named cause.

**B5 — Flatten-on-uncertainty and reconcile-then-publish** (§4). Indeterminate ⇒ send a flatten to be
safe; the flatten may hit nothing **or** close a real position, so the Limiter reconciles against
broker truth afterward and publishes **the confirmed state** — *"here is the CONFIRMED flat state"*,
never merely *"we sent a flatten"*. Fan-out to strategy, Allocator mirror, event log, Scoring.

### SUB-AGENT C — Net-liq survival watch (§6.5, §14, §15 C2)

**C1 — Survival is watched on net-liq; sizing is computed on cash. Never conflate.** §15 C2 records
why: cash does not erode with price, and the broker liquidates on net-liq.

**§0a, hypothesis:** a test where net-liq equals cash proves nothing about the distinction. **Drive
them apart** — an open position with unrealized P&L — and prove the watch tracks net-liq while sizing
tracks cash.

**C2 — Floor breach fires protective flatten** and a Critical alert (§12.9). The projected net-liq
impact leaving the floor intact is already Phase B's headroom rule from ARC 028; this is the standing
watch on the open book, not the pre-trade check.

**C3 — Broker-authoritative balance on every reconciliation** (§4, v1.3 locked). Every reconciliation
event pulls a direct broker balance **and** position poll in the same motion; the fresh authoritative
reading publishes atomically. Uniform on every event — no *"is this ambiguous enough?"* branch. If the
projection and broker truth disagree beyond tolerance, **broker wins and we correct.** Monotonic-by-
source guard still applies.

### SUB-AGENT D — Cold-start reconciliation (§4, V34)

**D1 — At cold start local state is empty and trustless.** The Limiter **actively queries the broker**
the moment broker-order has a session: true open-position set + balance = ground truth. At cold start
the broker's answer *is* the record, not a reconciliation against one.

**D2 — The query gates registration.** No strategy registers until a provably-flat assertion has
passed. **§0a, hypothesis:** *gates registration* is unfalsifiable unless something attempts to
register — prove a registration **attempt** is refused, not that none occurred.

**D3 — Any unexpected open position ⇒ flatten to flat before any strategy registers.** Never adopt,
never reason about an inherited position. Flat is the only known-good state.

**D4 — The market-tradable guard.** Flatten fires market orders. If the box comes up to an open
position while the market is **closed or halted**, the system does **not** fire into a shut market —
it **holds in HALT with a loud alert** and flattens the instant the market is tradable.
**Hypothesis:** a drill with the market always open measures neither half. Prove both — held in HALT
while closed, and flattened on reopen.

**D5 — Restart = flat, always.** No resume of a prior position, even a winning one.

---

## STAGE 2 — Integration (SERIAL)

**2.1 — Every protective path fires in simulation.** That is R2's stated done-when. Each of B1's
triggers, end to end, with the Plane-1 rows each produces.

**2.2 — Plane-1 rows for the exit half** (§12.10): protective-exit, closed, cancels including IOC
remainder-cancel on partial fill, reservation released under its correct cause. Limiter sole writer;
no new writers, ever.

**2.3 — Idempotent execution handling** (§4): broker events deduplicated by `(order_id, exec_id)`;
position state derives from cumulative fills, immune to duplicate or out-of-order execution reports.
**Hypothesis:** a dedup test that never delivers a duplicate measures nothing.

**2.4 — State honestly what the exit half still cannot do.** The Sentinel does not exist, so a killed
Risk Engine is an unprotected position. Session-close flatten is R4. Orphan recovery needs the
heartbeat machinery. Say it in the gates' own verdicts.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in at least three orders, cold cache, each swept twice.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f). Not carried forward. **30 BOUND is
the standing figure to hold** — any new check that lands UNBOUND is a finding, not a default.

---

## PHASE 4 — Close-out

1. `verify.py` under the regenerated plan. Baseline: `check_ibgateway_service` FAIL +
   `check_ibgateway_config` cannot-measure + `check_observed_resource_claims` cannot-measure +
   `check_artifact_gate_coverage` cannot-measure. A further FAILURE is a finding, and so is any
   further NON-PASS whose cause is not named.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT — **with the total reconciled against its own
   enumeration** (0.2).
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

The Sentinel (R4) · session-close flatten's calendar (R4) · blackout window generation and the
pollers (R4) · full HALT auto-clear and cooldown discipline (R4) · strategy-death heartbeat detection
(R5) · Scoring (R5) · the Allocator (R3) · full Postgres schema integration · the group-commit
cursor's durability across restart.

---

## Open items returned to the operator / architect

1. **The tap session** — operator task at the console, ~40 min, **owed by thirteen arcs**. Discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement,
   D1.39/D1.40, SPEC-A6's poll-channel lag figure, D1.50. **Still the only FAIL in `verify.py`, and
   it is a switch.**
2. **D3.99 provenance** — 811 lines from nowhere. 0.3 rules on adoption and builds the gate; **where
   they came from is still unanswered** and the answer matters more than the files.
3. **v1.4 remains deliberately not authority** (D3.33) — promoting it moves every `§x:line`
   coordinate the governed roots cite. Architect debt, now carrying SPEC-A7.
4. **§13 objective 24** becomes dischargeable once this arc's order path exists (D1.47) — the V24
   drill itself is not in this arc.
