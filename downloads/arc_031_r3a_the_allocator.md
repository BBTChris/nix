# ARC 031 — R3-A: The Allocator (Sizing Off the Mirror)

**Module:** Allocator (Core 3) — first product arc on the sizing layer
**Predecessor:** ARC 030 (trunk reconciled, `main` @ `9858b37` local)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking (corrections + push decision + seam freeze) · Stage 1 three
parallel sub-agents · Stage 2 serial integration · Stage 3 convergence · Phase 4 close-out.

**Verifies:** advances §13 toward the Allocator objectives. **Reads, never writes** the Limiter's
financial picture — authority stays with the Limiter (§2, §3).

---

## WHAT CHANGES WITH THIS ARC

R2 built the authority side: the Limiter gates, reserves, protects, and publishes ONE atomic
financial-picture snapshot. This arc builds the **permissive** side that reads that snapshot and
*proposes*. The Allocator is a separate process on Core 3, **single-threaded** (§5, lock-free
contention), and does **per-GO work only** — zero per-tick load (§16, upheld).

**The authority split is the invariant this arc cannot cross (§2):** the Allocator is permissive. It
sizes and proposes; it never gates, never reserves, never places, never writes canonical state. Every
number it reads comes from the Limiter's published mirror. A test that has the Allocator compute off
its own copy of balance, or mutate any published field, is the authority violation this arc exists
NOT to introduce.

**Scope discipline — this is R3-A, not all of R3.** In: the mirror consumer, the sizing pathway, the
correlation-bucket cap, and FCFS contention. OUT, and stated in the verdicts: the Scoring process and
performance-weighted contention (that is R5 — this arc wires the FCFS fallback and the ranking-table
READ seam, but the table's writer does not exist yet); blackout/calendar pollers (R4); the strategy
FSM (separate module). Say so in the gates rather than implying coverage.

---

## §0a — Self-audit, applied to this brief first

*What would have to be true for this step to complete successfully while measuring nothing?* Report
any step whose success is compatible with measuring nothing.

**Precedent, ARC 030:** the brief asserted the unmerged stack started at ARC 022; measurement showed
`main` already held 022–025 and the column started at 026. The measurement won and it was a finding.
**Assume this brief contains at least one false premise and at least one hazard stated backwards** —
four of my hazard directions have been measured backwards across ARCs 027–029.

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-runnable-artifact drives shipped bytes red · §0f explicit-status-or-owner, table rebuilt · §0g owner-names-a-future-arc · §0h forward-only-no-rewrite (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

## §0i — The mirror is stale-until-proven-fresh (NEW, this arc)

§12.7 / §3: a consumer's mirror is built by snapshot-on-subscribe, and **a half-built mirror is
stale**. The Allocator must treat an incomplete or unstamped mirror as stale and **fast-drop / refuse
to size**, never size on a partial picture. This is the consumer-side twin of the Limiter's atomicity
rule, and ARC 027's `XPUB_VERBOSE` finding applies directly — a mirror that silently misses its
snapshot looks exactly like a quiet, healthy feed.

---

## PHASE 0 — Corrections, the push decision, and the mirror seam (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk.** Expect ARC 030's close: `verify.py` `40 passed | 3 failed |
1 cannot measure | 0 skipped | 1 guarded`, exit 1, 45 checks; pytest 1620 + 2 skipped + 2 xfailed;
claims green; CHECK-DEBT 155 derived; binding 43 BOUND / 2 EXERCISED-NEVER-RED / 0 UNBOUND. **Any
delta is a finding.** Name every FAIL by owner.

**0.2 — The push decision (operator ruling required, do not act without it).** `main` is 92 commits
ahead of `origin/main` and unpushed. **[RECOMMEND]** push, after confirming no remote divergence:
`git fetch` then prove `git log origin/main..main` counts 92 and `git log main..origin/main` is empty.
A trunk that exists only on node02's disk is one hardware failure from re-stranding eight arcs. **This
is outward-facing on a public repo — cc reports the divergence check and STOPS for the operator; it
does not push unilaterally.**

**0.3 — D3.120, the self-caused ceiling breach (architect ruling).** `measurement_path.py` tripped its
re-owning ceiling during ARC 030's pre-close re-point. **Discharge by REAL COVERAGE, not by extending
the exclusion.** `measurement_path.py` is the classifier that proved the §0c withdrawal — it is
load-bearing enough to deserve a real can-fail, not an exemption. Build `check_measurement_path.py`:
drive the classifier to a wrong classification on a planted subject, prove it reddens and names the
site. The ceiling breach was the ledger flagging an overdue measurement, not an overdue escape hatch.

**0.4 — D3.118, the `nixverify.observe` `dir_fd` gap.** Real, structural, Linux-specific — needs
`/proc/self/fd/<n>` resolution. Fix it properly or, if it genuinely can't land this arc, keep it
`check_observed_resource_claims` FAIL with a named owner and the specific mechanism recorded. **Do not
paper it with a literal-token anchor** (doctrine C.4).

**0.5 — Stray-branch cleanup.** `docs/arc002-results`, `docs/arc005-writeback` — superseded RESULTS
snapshots holding `check_untracked_attribution` at GUARDED. **[ARCHITECT RULING]** delete them (no
unique content); the guard discharges to PASS when they're gone. Prove the discharge, don't assert it.

**0.6 — Freeze the mirror seam.** Types and ports for the financial-picture consumer: the snapshot
schema the Allocator mirrors (balance, per-position rows keyed by `trade_id`, per-symbol current
margin, Σ open margin, Σ reservations, committed, deployable — §3/§6.4), the version stamp, and the
ranking-table READ port (FCFS fallback wired, writer absent). Declare sync/async per verb with the
reasoning. **Per ARC 028/029, prove the seam gate actually reddens on a change to each declared
property** — a seam gate that passes on a renamed field or a dropped stamp measures nothing.

---

## STAGE 1 — Three parallel sub-agents

### SUB-AGENT A — The mirror consumer (§3, §12.7, §6.4b)

**A1 — Snapshot-on-subscribe mirror.** The Allocator subscribes to the Limiter's PUB/SUB snapshot and
mirrors it continuously: balance + full per-position table + per-symbol margin + Σ open margin +
Σ reservations + committed + deployable, all under one version stamp. **Atomicity is unfalsifiable
without concurrency (§0a):** prove balance and the position table update together by racing a reader
against a mid-publish writer and showing the reader never sees a half-applied snapshot.

**A2 — Half-built mirror = stale (§0i).** On subscribe/reconnect, until the snapshot is complete and
stamped, the mirror is stale and the Allocator fast-drops. Prove the can-fail: deliver a partial
snapshot, show the Allocator refuses to size rather than sizing on it. The `XPUB_VERBOSE` class — a
missed snapshot that looks like a quiet feed — is the exact hazard.

**A3 — Monotonic-by-source balance guard (§6.4b).** Hybrid refresh: event-driven on money-moving
events plus slow poll, reconciled so balance never regresses — discard any reading older than the one
held, by venue timestamp/sequence. **Hypothesis to measure:** a test where readings arrive in order
proves nothing about the guard. Deliver an out-of-order (older) reading and prove it is discarded.

**A4 — Read-only, proven by attempt (§2 authority).** The Allocator never writes a published field.
Prove it: a write attempt against the mirror is refused or structurally impossible, not merely absent
from the code. "Absent from the code" is the vacuous version; an attempted mutation that fails is the
measured one.

### SUB-AGENT B — The sizing pathway (§3, §7, §16 U1/U2)

**B1 — Single-pass ordering (§16 U1, the anti-ping-pong invariant).** Strategy → Allocator → Risk
Engine → broker. The Allocator does NOT round-trip through the Limiter. Inside the Allocator:
**fast-drop against the tradability cache first** (never size a dead signal), THEN size, THEN emit the
proposal carrying its sizing rationale (binding constraint + input snapshot, §16 U5) for the Limiter's
event log. **§0a:** a gate reading source order proves nothing about execution order — prove by
observation that a dead signal is dropped before any sizing arithmetic runs.

**B2 — Headroom = 0.70 × balance − committed (§16 U2).** Committed = Σ open margin + Σ reservations,
read from the mirror — one source of truth, no recomputation. This kills the size-down churn v1.1 had
at the gate. The Allocator sizes *within* headroom; the Limiter's Phase B re-checks it (the Allocator
is permissive, the Limiter authoritative — the re-check is the guarantee, not redundancy).

**B3 — Sizing guards (§15 C3, §7).** Zero/invalid stop distance ⇒ the proposal is a deny-shaped
no-size (the Limiter denies; the Allocator does not manufacture a size). Missing margin ⇒ not-tradable.
Clamp contracts ≥ 0. Slippage pad in the dollar-risk figure. **Single-instrument preference (§16 U4):**
full contract, not mixed micro legs.

**B4 — Margin-contracts sizing reads the same versioned row as the gate (§6.4b).** The Allocator sizes
on margin AND balance AND headroom "in one breath" — all from the one snapshot, so no cross-table skew.
Prove the Allocator and the Limiter's gate read identical bytes for the same version stamp.

### SUB-AGENT C — Correlation-bucket cap and FCFS contention (§7, §6.6)

**C1 — The bucket cap, by formula (§7, locked).** Exposure in **dollar risk** =
`(stop_ticks + slippage_pad) × tick_value × contracts`, micros at 1/10. Cap is **same-bucket only**:
`Σ dollar_risk(open + pending in bucket) + proposed ≤ bucket_cap_pct × balance`. Buckets: equities
{ES,NQ}, energy {CL}, metals {GC}, rates {ZN}. Different buckets do not constrain each other here.
**§0a:** a cap test with one position per bucket never exercises the summation — drive two same-bucket
positions and prove the proposed third is capped against their sum, not against itself.

**C2 — FCFS contention (§6.6 fallback), writer-absent.** When proposals compete for capital that can't
satisfy all, the winner is chosen by realized-P&L EMA from the ranking table — **which does not exist
yet (R5).** This arc wires the READ seam and the **FCFS fallback**: absent or equal scores ⇒
first-come-first-served, and order flow never stalls. Prove the fallback fires when the table is
absent — that is the state the whole system runs in until R5.

**C3 — Contention is the Limiter's to arbitrate, not the Allocator's (§6.6).** The Allocator reads the
ranking to *weight sizing*; the *Limiter* reads it to *arbitrate* when a shared resource can't satisfy
every proposal. Keep the authority boundary: the Allocator does not decide the winner of a contention
race. State honestly in the gate what is the Allocator's here vs deferred to the Limiter/Scoring.

---

## STAGE 2 — Integration (SERIAL)

**2.1 — A GO becomes a proposal, end to end.** Compose the mirror consumer, the sizing pathway, and
the caps against one simulated Limiter snapshot: a GO arrives, tradability fast-drop runs, sizing reads
the mirror, the bucket cap and headroom apply, and a proposal (or a no-size/deny) is emitted carrying
its rationale. Drive: a clean size, a headroom-capped size-down, a bucket-capped size-down, a
dead-signal drop, a zero-stop deny, and a stale-mirror refusal.

**2.2 — Partial-fill reflection (§4).** On fill confirmation the Limiter republishes with true filled
size and the unfilled reservation released; prove the Allocator's mirror shows the over-reserved
capital returning to deployable **the instant reality comes in under the reservation**, not on a delay.
This is a mirror-consumer property — the Allocator reflects, it does not act.

**2.3 — Every Allocator output is a proposal, never an order (§2 authority, the integration-level
check).** Across all of 2.1's paths, prove nothing the Allocator emits reaches the broker without the
Limiter's pass. The authority invariant holds at the seam, not just in each unit.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice — the Allocator's mirror consumer
touches ZMQ and shared read state and is a fresh false-declaration candidate.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f), not carried forward. The BOUND floor is
43; new Allocator checks should raise it, and any landing UNBOUND or EXERCISED-NEVER-RED is a finding
named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk. Baseline: `check_ibgateway_service` FAIL (tap session) + any of D3.118/D3.120
   still open with named owners + the standing cannot-measure. A further FAILURE is a finding, and so
   is any further NON-PASS whose cause is not named. Name every GUARDED check and print its owner
   verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   per D3.22 use the `gitenv.py` scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; `cat` both as the final action; **prove HEAD advanced** (§0d); state the
   absolute canonical path.
6. Clean up temp files and any worktrees/branches this arc created.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The Scoring process and performance-weighted contention (R5 — only the FCFS fallback and the
ranking-table READ seam land here) · blackout/calendar pollers (R4) · the strategy FSM (separate
module) · the tap session (operator, hardware) · pushing `origin/main` unilaterally (0.2 is an
operator ruling). Say the deferrals in the verdicts — an Allocator that sizes but whose contention
winner is FCFS-only is not the full §6.6 design yet, and the gates must not imply otherwise.

---

## Open items returned to the operator / architect

1. **Push `main`?** 0.2 — operator ruling, outward-facing, public repo.
2. **The tap session** — operator task at the console, ~40 min, owed by sixteen arcs. Discharges D1.12
   reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl` precondition
   invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40, SPEC-A6's
   poll-channel lag figure, D1.50, the two Gateway gates' green. The only code-independent FAIL.
3. **Seam questions (D3.109)** — does `ExecutionReport`/`ExecutionLedgerPort` belong in the frozen
   seam; is `PositionRow.size` signed. Architect debt, now touching the Allocator's mirror schema.
4. **v1.4 remains deliberately not authority** (D3.33), now carrying SPEC-A7 and the EventKind
   additions.
5. **After this arc: R3-B** — the remaining Allocator surface (per-strategy state reflection through
   recovery, the in-flight-closing transitional state) and then R4 blackouts.
