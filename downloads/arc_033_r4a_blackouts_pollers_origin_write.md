# ARC 033 — R4-A: Blackouts, Pollers, and the Origin Write

**Module:** Risk Engine / Limiter (Core 2) — the blackout calendar and clock-driven safety windows +
shared-pool pollers · plus the Allocator seam corrections R3-B left open
**Predecessor:** ARC 032 (merged; `SEAM_REV 1.1.0`; cap closed)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking · Stage 1 four parallel sub-agents · Stage 2 serial
integration · Stage 3 convergence · Phase 4 close-out.

**Verifies:** advances the non-stop §12 objectives (R4). **Scope: R4-A, not all of R4.** In: the
blackout calendar (EOD/EOW/news-margin/roll), session-close flatten (§6.1b), the live-margin +
calendar pollers with stale⇒halt+flatten, contract rolls (§7.5), and HALT semantics (§12.5). OUT and
stated in the verdicts: the Sentinel deadman (§12.1) and supervision/crash-loop breaker (§12.2) —
those are R4-B, and they need the heartbeat machinery R5 also touches. Say the deferrals in the gates.

---

## WHAT CHANGES WITH THIS ARC

R2 built the exit half; R3 built sizing and closed the fail-open cap. **This arc builds the calendar
of times the system must not trade, and the pollers that feed it** — the coupled other half of §6.5's
70% cap (the cap is only safe because the blackouts keep the book out of the close-snap and the 4×
margin spike; cap + blackout calendar are ONE system, §6.5 interlock).

Two carried corrections land first, because R3-B proved the field travels but not that it's fed:

- **D3.150 — the origin write.** Nothing in production yet *chooses* a `stop_distance`. ARC 032 proved
  the field publishes and mirrors atomically; it did not prove any value on it is real. Until the
  Limiter's fill path writes the sizer's own `stop_ticks` onto the row it publishes, the closed cap is
  pricing held positions off a field nothing populates. **The cap is plumbed but unfed. This arc feeds
  it.**
- **D3.144 — `execution.py` at the re-owning ceiling.** Same shape as D3.120: real coverage, not
  another walk.

---

## §0a — Self-audit, this brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

**Precedent, ARC 032:** the atomicity re-proof would have passed while measuring nothing if the new
field were not *in* the torn-read assertion — a re-proof racing only the old fields proves the old row
still works. It caught the split because the field was in the assertion. **Every blackout gate in this
arc has the same trap:** a window test where `now` is never inside the window, a stale⇒halt test where
the feed is never actually stale, a roll test where identity never actually shifts. **Assume this
brief contains at least one manufactured-input pass and one hazard stated backwards** (five of mine
have measured backwards across 027–032).

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-artifact-drives-shipped-bytes-red · §0f explicit-status-or-owner, table-rebuilt · §0g owner-names-future-arc · §0h forward-only · §0i mirror-stale-until-proven-fresh (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

## §0j — The completion marker is the LAST token (NEW, this arc)

`**** ARC completed ****` means the banked state is final and nothing followed it. **Nothing prints
after it — no re-measure, no cat, no summary.** ARC 032 ran the predicted guard-owner re-measure
*after* the marker, producing two "final" figures and certifying a state that then changed. If a
post-write-back re-measure is required (e.g. the D3.40 guard-owner transition when `SESSION.md` names
the arc complete), it runs and is reported and **banked BEFORE the marker**, and the marker prints
once, last. If the arc cannot reach a state where the marker is last, it does NOT print it — it
reports `STATUS: IN FLIGHT` and names what is still moving. Record in `nix_check_contract.md` and
`CLAUDE.md`.

---

## PHASE 0 — Corrections and the calendar-data freeze (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 032's post-write-back close:
`verify.py` `48 passed | 1 failed | 3 cannot measure | 0 skipped | 0 guarded`, exit 1 (the guarded row
went CANNOT_MEASURE on the D3.144 transition); and the pre-write-back `48 | 1 | 2 | 0 | 1`. State both
and which is which. pytest, claims, CHECK-DEBT, census, binding table. **Any delta beyond the D3.144
transition is a finding.**

**0.2 — D3.150, the origin write (the cap's real completion).** The Limiter's fill path writes the
sizer's own `stop_ticks` onto the `PositionRow` it publishes, so the closed cap prices held positions
off a real value, not a field nothing populates. Build the gate that **reddens when a published
`stop_distance` disagrees with the stop book's for the same trade** — the field being present is not
the field being right. **§0a:** a gate that only checks the field is non-null passes on a wrong value;
it must compare against the authoritative stop book per trade.

**0.3 — D3.144, `execution.py` coverage.** Real per-artifact can-fail (like D3.120's discharge), not a
`CHECK-A<n>` exclusion. `execution.py` is the idempotent-execution ledger — position = Σ signed_qty
over unique `(order_id, exec_id)`. Drive it to a wrong position on a planted duplicate/out-of-order
stream and prove the gate reddens naming the site. Discharges D3.144, clears
`check_artifact_gate_coverage` from CANNOT_MEASURE.

**0.4 — Freeze the calendar as DATA, not code (§6, the locked principle).** New blackout types are
**data — a window** — never code (§6.5). The per-symbol session table (SOD/EOD/maintenance,
holiday early-close overrides, roll schedule) is versioned, auditable infrastructure that corrupts
every downstream decision if wrong. Freeze its schema: per-symbol, UTC-canonical storage, exchange-
local derived at evaluation via the IANA tzdb (never stored Central — "normalized to Central" is how
DST bugs are born). Declare the poller ports (margin fast, calendar slow) sync/async with reasoning.
**Prove the schema gate reddens on a stored-Central timestamp** — the exact defect the rule forbids.

---

## STAGE 1 — Four parallel sub-agents

### SUB-AGENT A — The blackout calendar (§6.1, §6.2, §6.3, pre-size)

**A1 — EOD entry blackout (§6.1):** no new entry from 15–20 min before a symbol's session close
through its next open; entry-only, exits still fire; per-symbol via the live calendar; onset cancels
pending ENTRY orders (§3). **A2 — EOW (§6.2):** Friday-close−30min through Sunday open; widest active
leading edge wins (window union). **A3 — news/margin (§6.3), asymmetric edges:** leading edge = clock
(20 min before a scheduled event); trailing edge = **live margin** (hold until margin returns to
baseline + min-time floor), which also catches unscheduled spikes for free; **anti-lockout
baseline-re-acceptance** — stable-elevated beyond a period becomes the new baseline with an operator
alert, so a permanent broker hike never locks the system out forever.

**§0a, the window trap:** every window test must drive `now` genuinely inside the window AND genuinely
outside it, and prove entry is blocked inside and permitted outside. A test with `now` fixed outside
proves nothing. The union (A2) needs two overlapping windows where the widest edge actually wins over
a narrower one, not one window.

**A4 — Calendar source conflict (locked, Econoday live vs historical):** for live decisions the live
source wins on disagreement; disagreements are **logged as flagged events, never silently resolved**.
Gate that a disagreement produces a flagged record, not a silent pick.

### SUB-AGENT B — Session-close flatten and contract rolls (§6.1b, §7.5)

**B1 — Session-close flatten (§6.1b), enforced by construction.** At `SESSION_FLATTEN_LEAD_MIN` before
each symbol's close, the Limiter force-flattens all open positions in that symbol, `reason=session`
(the protective-exit reason from §3). **The ordering invariant is boot-validated:**
`SESSION_FLATTEN_LEAD_MIN < EOD_BLACKOUT_MIN − pad` per symbol — the entry blackout must lead the
flatten deadline, and config validation **rejects** any per-symbol set violating it. **§0a:** prove
the boot validator actually rejects a violating set — a validator that accepts everything is the
vacuous case; plant an inverted pair and prove boot fails naming the symbol.

**B2 — The market-halted honesty clause (§6.1b, §12.6).** A halted market cannot be flattened — at the
deadline, exposure rides, and a **Critical alert** fires. Do not pretend a flatten into a shut market
succeeded (the ARC 022 F13 `ok=True over a lost bar` class). Prove the halted path alerts and does not
report a phantom success.

**B3 — Contract rolls (§7.5).** Front-month = volume leader; roll schedule from the calendar poller;
all symbol-keyed subsystems switch identity **atomically at a defined roll instant**; roll-day entry
blackout (a window, data); intraday-only means no position spans the roll. Prove the atomic switch —
a non-atomic roll where one subsystem lags is a torn identity, the §12.7 class one layer over.

### SUB-AGENT C — Pollers and stale⇒halt+flatten (§6.4, §12.3)

**C1 — Margin poller (fast) → margin cache; calendar poller (slow) → per-symbol window set.** Both on
the shared pool. Allocator/Limiter read caches only. Push-preferred: if the venue delivers
account/margin/position events, event-driven is primary and polling demotes to fallback/audit.

**C2 — Stale ⇒ halt new entries AND flatten open (§6.4).** Freshness stamp past threshold, after
retry/backoff, halts entries and flattens. **§0a, the hazard ARC 022 F17 got backwards:** prove
staleness fires on a genuinely stale feed, and prove it does NOT fire on a slow-but-fresh one — a
staleness test where the feed is never stale, or where "stale" is measured off a session mean that
agrees while the last packets are 900s out (the exact F17 defect), measures nothing. Time-bounded
window, not count.

**C3 — Clock integrity (§12.3).** All blackouts are clock-driven, so the clock is safety-critical:
skew past threshold ⇒ stale-class HALT. All internal time UTC; the calendar poller converts
exchange-local (incl. DST) exactly once at window generation. Prove a skewed clock HALTs.

### SUB-AGENT D — HALT semantics (§12.5)

**D1 — Setters and auto-clear.** Setters: stale-data, clock-skew, crash-loop, invariant breach,
aggregate-drift, operator. Auto-set conditions auto-clear on condition-clear + minimum floor
(cooldown). **Operator HALT clears only by operator.** Every set/clear is an audited Plane-1 event
with reason.

**D2 — The fail-closed Limiter-down case (§12.5, §12.1 pattern).** If a HALT condition arises while the
Limiter is unavailable, the system is already fail-closed — nothing reaches the broker without the
Limiter — so the `HALT set` row is booked **retroactively at next boot** by cold-start reconciliation,
same marker-replay pattern as the Sentinel. **§0a:** prove the retroactive booking actually happens —
a test that never kills the Limiter never exercises the retroactive path.

**D3 — HALT gates entry, never exit.** A HALT blocks new entries; protective exits still fire (§3, the
exit path has zero dependency on the entry path). Prove an exit fires under HALT.

---

## STAGE 2 — Integration (SERIAL)

**2.1 — The unified pre-size denial (§6.5).** Entry denied if
`HALT ∨ now ∈ any window ∨ margin elevated ∨ data stale ∨ clock skewed`. Compose all four sub-agents
against one simulated clock+calendar+margin state and drive each disjunct to denial independently,
then together. Prove the denial names the specific condition (the ARC 031 rationale requirement).

**2.2 — The §6.5 interlock, proven.** The 70% cap is only safe because the blackouts keep the book out
of the close-snap and the 4× spike. Prove the coupling: a scenario that would breach the cap without
the blackout is prevented by the blackout firing first. This is the "cap + calendar are one system"
claim, measured rather than asserted.

**2.3 — Plane-1 rows for the new events (§12.10).** blackout opened/closed, roll seam, session-flatten,
HALT set/cleared with reason — Limiter sole writer, no new writers. The retroactive bookings (D2)
land tagged `source=cold-start`.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice, under both documented interpreters
(D3.140). New pollers touch shared-pool state and timers — fresh false-declaration candidates.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f), not carried forward. BOUND floor 48;
any new check UNBOUND or ENR is a finding named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk, stating the interpreter. Baseline: `check_ibgateway_service` FAIL (tap
   session) + the standing cannot-measures. `check_artifact_gate_coverage` should be OFF
   CANNOT_MEASURE (D3.144 discharged). A further FAILURE is a finding; any further NON-PASS whose
   cause is not named is a finding. Name every GUARDED check and print its owner verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   per D3.22 use the `gitenv.py` scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; run any predicted post-write-back re-measure (D3.40 transitions) and BANK
   it; `cat` both as the final action; **prove HEAD advanced** (§0d).
6. Clean up temp files and any worktrees/branches this arc created.
7. **Per §0j: `**** ARC completed ****` is the LAST token, printed once, with nothing after it.** If a
   stable marker-last state can't be reached, report `STATUS: IN FLIGHT` and name what is moving.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The Sentinel deadman (§12.1) and supervision/crash-loop breaker (§12.2) — R4-B · the Scoring process
and recovery machinery (R5) · performance-weighted contention (R5) · the strategy FSM · the tap
session · changing branch protection (operator/GitHub). Say the deferrals in the verdicts. A blackout
calendar without the Sentinel is not the full non-stop guarantee — a killed Risk Engine is still an
unprotected position until R4-B, and the gates must not imply otherwise.

---

## Open items returned to the operator / architect

1. **Branch protection** — ARC 032's 0.3 drafted the status-checks ruleset; whether to apply it (and
   wire `verify.py`/`pytest` as CI status checks first) is the operator's, outward-facing.
2. **The tap session** — operator task, ~40 min, owed by nineteen arcs. Discharges D1.12 reboot
   capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl` precondition
   invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40, SPEC-A6's
   poll-channel lag figure, D1.50, the two Gateway gates' green, and now D3.149 (the Gateway-down
   masking of any declaration added while the port is dead). Only code-independent FAIL.
3. **`registry.json` vs `manifest.json`** — still an open operator ruling, untouched.
4. **v1.4 fold + D3.33** — amendments now run to SPEC-A9; the v1.4 file holds seven; re-pointing every
   `§x:line` citation below the first insertion is still owed. Architect debt.
5. **After this arc: R4-B** — the Sentinel deadman and supervision/crash-loop breaker (needs the
   heartbeat machinery), then R5 (Scoring, feedback recovery, observability) which lights up
   performance-weighted contention and the recovery states the Allocator already reflects.
