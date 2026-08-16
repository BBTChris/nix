# ARC 034 — R4-B: The Sentinel and the Called Cap

**Module:** Sentinel (Core 4–5 shared pool, new) + Risk Engine / Limiter (Core 2, the fill handler
that finally *calls* the origin write) + supervision
**Predecessor:** ARC 033 (merged; R4-A blackouts/pollers landed)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking · Stage 1 four parallel sub-agents · Stage 2 serial
integration (the non-stop guarantee is proven here) · Stage 3 convergence · Phase 4 close-out.

**Verifies:** completes the non-stop §12 objectives (Sentinel, supervision, orphan recovery) and
closes D3.150/D3.178 — the cap that has been priced off an uncalled field since ARC 032 finally gets
its origin write called at fill.

---

## WHAT CHANGES WITH THIS ARC

This is the arc that removes the last "a killed Risk Engine is an unprotected position" caveat every
arc since R2-B has carried. Two things land:

1. **The Sentinel (§12.1)** — the tiny independent deadman that flattens via its *own* broker session
   when the Limiter's heartbeat is lost. It is the one component whose whole purpose is to act when
   the rest of the system is dead, so it is deliberately dumb, dependency-minimal, and on a separate
   code path (minimal common-mode failure). With it, the synthetic-stop gap (a stop dies with the
   process holding it) finally has a net.

2. **The called cap (D3.150/D3.178).** ARC 032 proved `stop_distance` publishes atomically; ARC 033
   built the origin write and gated it — but `StopBook.arm`/`on_fill` have **zero production
   callers**, so the closed cap still prices held positions off a field nothing populates. This arc
   wires the Limiter's fill handler to arm the stop and call the origin write, so the cap prices real
   values. *A mechanism landed is not a mechanism called* (D3.178's own words).

**Authority note, and it is the subtle invariant of the arc (§14, §10):** *execution of any flatten
is Limiter-only — the Sentinel excepted.* The Sentinel is the single authorized exception, and only
because it fires precisely when the Limiter cannot. Building a second flatten authority is the exact
thing the architecture forbids everywhere else; the Sentinel earns it by triviality + acting only in
the Limiter's absence. Do not let its existence blur the rule for anything else.

---

## §0a — Self-audit, this brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

**Precedent, ARC 033:** the §6.5 rules had been wired to four producer ports that did not exist since
ARC 028 — a proven executor over absent inputs. And the cap's origin write is *built but uncalled*
right now, which is the same class one layer over: a gate green over a mechanism nothing invokes.
**Assume this brief contains at least one "built but never called" gap and one hazard stated
backwards** (five measured backwards across 027–033; the fail-open cap direction was a sixth).

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-artifact-drives-shipped-bytes-red · §0f explicit-status-or-owner, table-rebuilt · §0g owner-names-future-arc · §0h forward-only · §0i mirror-stale-until-proven-fresh · §0j marker-is-last-token (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

---

## PHASE 0 — Corrections, carried rulings, and the seam freeze (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 033's close: `verify.py`
`57 passed | 1 failed | 2 cannot measure | 0 skipped | 1 guarded`, exit 1; pytest 2343 + skips +
xfails; census 61 three ways; binding 59 BOUND / 0 UNBOUND; CHECK-DEBT 201 derived twice. **Any delta
is a finding.** Name every FAIL and the guard's owner.

**0.2 — Push (operator ruling, do not act without it).** `main` was ~105 ahead of `origin/main` at
ARC 033 close and still local. **[RECOMMEND]** push, after re-confirming no remote divergence
(`git fetch`; prove `git log origin/main..main` = the current count and `git log main..origin/main`
is empty). Outward-facing, public repo — report the divergence check and STOP for the operator; do
not push unilaterally.

**0.3 — D3.177, the trade↔order join (architect ruling).** `StopState`/`ProposedOrder`/`Reservation`
and §4's exec dedup key on `client_order_id`; `PositionRow` and the picture key on `trade_id`; nothing
joins them, so "the published `stop_distance` for the same trade" was not expressible. **[ARCHITECT
RULING — revocable] Keep them DISTINCT with an explicit, gated join — do NOT collapse to equality.**
Collapsing is the identity shortcut that hides skew (ARC 033 shipped the surface precisely because a
hard-coded equality is invisible). Land the join map (Limiter-owned, one authoritative direction) and
gate that every published `trade_id` resolves to exactly one `client_order_id` and back. §0a: a join
gate that only checks non-null passes on a wrong mapping — it must prove the round-trip.

**0.4 — SPEC-A10 vendor (operator ruling).** ARC 033 recorded the calendar vendor as **UNRATIFIED**
because "Econoday" appeared only in an architect brief with no ledger authority. **Confirm the real
calendar vendor or name it.** Until ratified, the calendar-source-conflict gate stays unbuilt with its
reason recorded (there is one source, so a conflict cannot occur) — do not manufacture a second source
to make a gate fire.

**0.5 — D3.191, the §0a audit of the four rescued modules.** Four Stage-1 modules from ARC 033 were
banked with their code measured but their authors' own §0a self-audits lost to the session cap. Run
the §0a review pass now — for each of the four, ask directly: what would make its gate pass while
measuring nothing? Bank findings as debt or discharge them. Until audited they are green-but-unaudited;
this closes that.

**0.6 — Freeze two seams.** (a) The **Sentinel seam**: its own broker session interface, the
heartbeat it watches, and the local append-only marker-file format (§12.1). (b) The **fill-handler
seam**: where the Limiter's `on_fill` arms the stop and calls the origin write (D3.178). Declare
sync/async per verb with reasoning. Per ARC 028/029/033, **prove each seam gate reddens on a change to
each declared property** — a seam gate that passes on a renamed field or a dropped marker field
measures nothing.

---

## STAGE 1 — Four parallel sub-agents

### SUB-AGENT A — The called cap (D3.150/D3.178) and the join (D3.177)

**A1 — Wire the fill handler.** On confirmed fill, the Limiter's `on_fill`: sets position to actual
filled qty, **arms the synthetic stop** (converts the GO's tick distance → absolute price at the
confirmed fill, §4), and **calls the origin write** so the published `PositionRow.stop_distance`
carries the real value. This is the caller D3.178 said was missing.

**A2 — Prove the cap now prices real values, end to end.** The origin-write gate from ARC 033 reddens
on a wrong value; now prove a *fill* produces a *correct* value that the *bucket cap* then prices.
**§0a, sharp:** a test that calls `arm` directly re-proves the mechanism ARC 033 already built — the
new thing is that a **fill** calls it. Drive an actual fill through `on_fill` and prove the stop is
armed and the field populated as a consequence, not by a direct `arm` call.

**A3 — The join (D3.177)** per 0.3: the Limiter-owned `trade_id ↔ client_order_id` map, gated for
round-trip uniqueness. Every published trade resolves to exactly one order and back.

**A4 — Partial-fill interaction (§4).** On partial fill the position is the actual filled qty, the
remainder is IOC-cancelled, the reservation for the unfilled portion releases, and the armed stop
operates on the **real filled size**. Prove the stop arms against filled size, not requested size —
arming against the requested size is a silent over-stop.

### SUB-AGENT B — The Sentinel deadman (§12.1)

**B1 — The watchdog.** Tiny independent process in the shared pool, dependency-minimal, separate code
path. Watches the Risk-Engine heartbeat. **Heartbeat lost AND positions possibly open ⇒ emergency
flatten-all via its OWN broker session + operator alert.** It does not share the Limiter's session,
caches, or code — common-mode failure is the enemy.

**B2 — The marker-replay durability fix (§12.1, the v1.3 gap).** The Sentinel fires exactly when the
sole event-log writer (Limiter) is dead, so its flatten would be the least-recorded action in the
system. It writes a **local append-only marker file** (timestamp, trigger cause, symbols, broker acks)
**before and after** acting — no Postgres, no shared writer. On next boot, cold-start reconciliation
reads the marker and books the flatten into Plane-1 retroactively (`source=sentinel`), then archives
the marker. **§0a, the absence proof:** prove the marker is written *before* the flatten (so a Sentinel
that dies mid-flatten still leaves a record), and prove cold-start replays it. A test where the
Sentinel never fires, or never dies mid-act, measures neither half.

**B3 — The deadman fires only when it should.** Heartbeat lost AND positions possibly open — both
conditions. Prove it does NOT flatten on a heartbeat blip with no open positions (nuisance flatten is
its own hazard), and DOES flatten when the Limiter is genuinely dead with positions open. **This is
the arc's headline and it requires actually killing the Limiter** — a Sentinel tested only with a live
Limiter has never done its job.

**B4 — Authority boundary (§14).** The Sentinel is the ONE flatten exception. Prove nothing else in
the arc gains independent flatten authority, and that the Sentinel acts only on heartbeat-loss — it
does not arbitrate, size, or gate. It flattens and alerts; that is all.

### SUB-AGENT C — Supervision, crash-loop, orphan recovery (§12.2, §4)

**C1 — systemd supervision + crash-loop breaker (§12.2).** Every process systemd-managed with a
restart policy. **N restarts in M minutes ⇒ HALT + operator alert** — never blind restart-into-trading.
Boot-flatten makes any single restart safe by design. **§0a:** prove the breaker actually trips — a
test that never crash-loops never exercises the cap; drive N+1 restarts in the window and prove HALT.

**C2 — Orphan / strategy-death recovery, in strict order (§4, locked).** Heartbeat miss ⇒ wait exactly
one cycle (1s); second consecutive miss ⇒ presumed dead. Then, in order: **(1) flatten first** (close
positions owned by that `strategy_id` while its registration still exists, so each has an unambiguous
owner), **(2) force-deregister** in the Risk Engine (tear down one-in-flight lock, pending, slot,
registration — nothing stale survives), **(3) kill + relaunch** (re-registers, boots to flat). **§0a:**
the order is the safety property — prove flatten happens *before* deregister (deregistering first
orphans the position), by observing the sequence, not asserting it.

**C3 — Crash-loop cap → quarantine (§4, locked).** After 3 restarts within the window, stop
relaunching: strategy **quarantined — left dead and flat, alert raised** — while the rest keeps
trading. Not auto-resurrected; return is operator-driven. Score handling (persist-across-death vs
archive-on-quarantine) is **R5, not this arc** — C wires the lifecycle transitions and states the
Scoring boundary; it does not implement the EMA persistence.

**C4 — Allocator reflection of recovery (§4).** Every recovery action must reach the Allocator via the
mirrored snapshot as the correct lifecycle state — a strategy mid-recovery reads **in-flight-closing,
not normal-and-available** (this already landed in ARC 032's C1; here prove it holds through a *real*
death/recovery, not a simulated state injection).

### SUB-AGENT D — Instrument debt and the audit close

**D1 — Discharge the D3.191 findings** from 0.5 into real coverage or honest owners.

**D2 — The "built but uncalled" detector (generalise D3.178).** ARC 033's cap origin-write sat built
and gated with zero callers, invisible until someone asked. Build the general check: a
public/contract entry point (an `arm`, an `on_fill` hook, a declared seam verb) with **zero call sites
in shipped code** is a finding — named, with the entry point and the arc that should call it. This is
the D3.16 "gate never drives its subject" class at the *production* level rather than the test level,
and it is exactly the gap that let the cap ship unfed.

**D3 — CHECK-DEBT reconciliation** with the derived-vs-narrated arithmetic gate (D3.82) covering this
arc's own results.

---

## STAGE 2 — Integration: the non-stop guarantee (SERIAL)

**2.1 — The kill drill, for real (§12.1, the done-when).** Kill the Risk Engine with positions open
and prove the Sentinel flattens via its own session, writes its marker, and alerts — then prove
cold-start replays the marker into Plane-1 on next boot. This is R4's stated done-when: *Sentinel
flattens on a killed Risk Engine.* Record the PID killed and attribute the flatten to the death.

**2.2 — The full recovery drill.** A strategy death → one-cycle grace → flatten → deregister → relaunch
→ boots flat; then a crash-loop → quarantine → rest of system keeps trading. End to end, with the
Plane-1 and Plane-2 rows each step produces (§12.10).

**2.3 — The cap, fed by a real fill.** A GO → proposal → gate → fill → `on_fill` arms the stop and
writes the origin → the bucket cap prices the held position off the real `stop_distance`. The
D3.150/D3.178 loop closed end to end, driven by a fill, not a direct call.

**2.4 — State honestly what remains.** Scoring/EMA persistence is R5; the dashboard is post-infra;
live-venue is untested by design. Say it in the verdicts — a non-stop guarantee proven in sim is not
proven live, and the gates must not imply otherwise.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice, under both documented interpreters.
The Sentinel's own broker session and marker file are new resource surfaces — fresh false-declaration
candidates.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f). BOUND floor 59; any new check UNBOUND
or ENR is a finding named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk, stating the interpreter. Baseline: `check_ibgateway_service` FAIL (tap
   session) + the standing cannot-measures. A further FAILURE is a finding; any further NON-PASS whose
   cause is not named is a finding. Name every GUARDED check and print its owner verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   per D3.22 use the `gitenv.py` scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; run any predicted post-write-back re-measure and BANK it BEFORE the marker
   (§0j); `cat` both as the final action; **prove HEAD advanced** (§0d); state the absolute canonical
   path.
6. Clean up temp files and any worktrees/branches this arc created.
7. **Per §0j: `**** ARC completed ****` is the LAST token, printed once, nothing after it.** If a
   stable marker-last state can't be reached, report `STATUS: IN FLIGHT` and name what is moving.

**WAYPOINTS.** At kickoff echo the total stage count once; at the start of every phase/stage/sub-agent/
convergence step print a boxed banner —
`ARC 034 · <Module>/<Stage> — STAGE <k>/<total>: <name>` + an `~elapsed in · ~eta left` line — and tag
it `— PAUSED, awaiting operator` on any stop-for-ruling. This is a standing rule; also confirm it is
recorded in `~/nix/CLAUDE.md`.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The Scoring process and EMA persistence / archive-on-quarantine (R5 — C wires lifecycle, states the
boundary) · performance-weighted contention (R5) · the dashboard (post-infra) · the strategy FSM
(plug-in) · full Postgres schema + cold-start beyond the Sentinel-marker replay (a later arc) · the
tap session · changing branch protection. Say the deferrals in the verdicts.

---

## Open items returned to the operator / architect

1. **The tap session** — operator task at the console, ~40 min, owed by twenty arcs. Discharges D1.12
   reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl` precondition
   invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40, SPEC-A6's
   poll-channel lag figure, D1.50, the two Gateway gates' green. Only code-independent FAIL.
2. **Push** (0.2), **SPEC-A10 vendor** (0.4), **branch protection** (ARC 032's drafted status-checks
   ruleset) — all operator/outward-facing, still open.
3. **v1.4 fold + D3.33** — amendments now run to SPEC-A10; the v1.4 file lags; re-pointing every
   `§x:line` citation is owed. Architect debt.
4. **After this arc: infrastructure is materially non-stop-complete.** What remains for infra-100:
   Postgres full schema + cold-start (Plane-1 to 100), R5 Scoring (unblocks the Allocator's last
   piece and closes the recovery loop C wired here), then the Allocator's Scoring-dependent finish.
   Then the ULTRAREVIEW pass, the reference strategy, and IBKR end-to-end — per the roadmap.
