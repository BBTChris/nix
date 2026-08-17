# ARC 035 — Plane-1: The Durable Record

**Module:** Postgres / Plane-1 (Core 4–5 shared pool) + the Limiter's persistence path (sole writer)
**Predecessor:** ARC 034 (merged; Sentinel + called cap landed)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking · Stage 1 four parallel sub-agents · Stage 2 serial
integration (degraded-persistence + crash-gap drills) · Stage 3 convergence · Phase 4 close-out.

**Verifies:** takes Plane-1 / Postgres from ~42% (WAL + group-commit + Sentinel-marker replay) toward
code+sim-complete: the full append-only event-log schema, the positions projection, cold-start
reconciliation vs broker truth, degraded-persistence discipline (§12.4), and the full-scan drift
audit (§11.7).

---

## WHAT CHANGES WITH THIS ARC

R2 built the WAL + group-commit seam and R4-B added the Sentinel-marker cold-start replay. What's
still missing is the **durable record itself**: the actual Plane-1 schema for every §12.10 event, the
rebuildable positions projection, and the reconciliation that heals a crash gap against broker truth.
This is the un-sexy structural work that turns "we can enqueue events" into "the money truth is
durably recorded and provably rebuildable."

**Two boundaries to hold from the start:**

- **Plane-1 is NOT the analytics DB.** `nix_db_schema_spec.docx` defines the trade-history / candle /
  brick databases (PG16-validated, role-separated, partitioned) — that is the *backtest/evaluation*
  store. Plane-1 is the *live event-sourced log* the Limiter writes at runtime (§9). They are
  different stores with different physics. This arc builds Plane-1; it must not silently conflate the
  two or duplicate the analytics schema. Where the two legitimately meet (e.g. a closed live trade
  eventually landing in trade-history), that seam is declared, not assumed.
- **Limiter is the SOLE writer (§9). No new writers, ever.** Every Plane-1 row originates from the
  Limiter's enqueue → local WAL → shared-pool writer → group-commit path. The shared-pool writer is a
  conduit, not a second author. A test that writes a Plane-1 row from anywhere else is the
  sole-writer violation this arc must not introduce.

---

## §0a — Self-audit, this brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

**The durability trap, stated because ARC 028 already taught it and this arc is where it bites hardest:**
a SIGKILL cannot test fsync — a dead process's dirty pages belong to a living kernel, so a
`--no-sync` WAL that is SIGKILLed still reads back intact and a naive crash test passes while
measuring nothing. **Durability claims in this arc must be proven against a real durability boundary
(fsync verified, or power-loss/container-kill that drops the page cache), never a bare process kill.**
Assume this brief contains at least one durability claim that a process-kill would pass vacuously, and
one hazard stated backwards (six measured backwards across 027–034).

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-artifact-drives-shipped-bytes-red · §0f explicit-status-or-owner, table-rebuilt · §0g owner-names-future-arc · §0h forward-only · §0i mirror-stale-until-proven-fresh · §0j marker-is-last-token (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

---

## PHASE 0 — Corrections, carried rulings, and the schema freeze (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 034's close (state the exact
figures cc banked: verify.py counts, pytest, census, binding floor, CHECK-DEBT). **Any delta is a
finding.** Name every FAIL and every GUARDED check's owner.

**0.2 — The four `artifacts`-row ceiling breach (carried from ARC 034 Phase 0.6).** ARC 034 re-owned
twelve stale ARC 033 guard owners to ARC 035; four `artifacts` rows were already at 2-of-2 and the
commit banked the third move — the D3.120/D3.144 ceiling-breach pattern again. **Discharge by REAL
COVERAGE, not another walk and not an exclusion.** Build the real can-fail for each of the four
artifacts. The ceiling breach is the ledger naming an overdue measurement.

**0.3 — Carried operator rulings (report, then act only where authorized).**
- **Push** `main`→`origin`: re-confirm no divergence, report the count, STOP for operator — do not
  push unilaterally.
- **SPEC-A10 vendor**: still UNRATIFIED. Confirm/name the real calendar vendor or leave the
  conflict gate unbuilt with its reason recorded.
- **Branch protection**: ARC 032's status-checks ruleset is drafted; applying it (and wiring
  `verify.py`/`pytest` as CI status checks first) is the operator's.

**0.4 — Freeze the Plane-1 schema.** The append-only event-log schema for the full §12.10 inventory:
one row per transition (signal, accepted, denied, filled, exit-intent, closed, protective-exit,
reservation taken/released, cancel incl. IOC remainder, GO-timeout, HALT set/cleared, operator
action, strategy lifecycle, cold-start-outcome, sentinel-flatten via marker replay). Every row carries
timestamp + strategy_id + trade_id + reason (§9). Declare: append-only enforced by **privilege not
trigger** (the analytics-DB lesson — writer role has INSERT, no UPDATE/DELETE on the log), the
positions **projection** table as derived/rebuildable, and the WAL→group-commit→Postgres path. **Prove
the schema gate reddens on a violation of append-only** (an UPDATE grant on the log table must redden
it) — a schema gate that only checks tables *exist* measures nothing.

---

## STAGE 1 — Four parallel sub-agents

### SUB-AGENT A — The event-log schema and the sole writer (§9, §12.10)

**A1 — The schema lands**, migration-based, PG-validated (reuse the `nix_db_schema_spec.docx`
discipline: explicit sequences not IDENTITY on partitions, role grants that actually let `nextval()`
run, DEFAULT partitions as catch-alls). Append-only enforced by role privilege.

**A2 — Sole-writer, proven by attempt (§9).** Every row originates from the Limiter's enqueue path.
Prove a write attempt from a non-Limiter identity is refused by privilege — not merely absent from the
code. "Absent from the code" is the vacuous version; a refused INSERT from the reader/other role is the
measured one.

**A3 — Group-commit off the hot path (§11.6).** WAL-buffered, batched commit; prove the hot gate path
does no synchronous Postgres write (the entry pathway is cache-reads-and-arithmetic only, §11). §0a: a
latency test on an idle system proves nothing about hot-path isolation — drive writes concurrent with
gate evaluations and prove the gate never blocks on the commit.

**A4 — Every §12.10 Plane-1 event actually writes a row.** Enumerate the inventory; drive each event
and prove its row lands with the required fields. A "logging works" test that exercises one event type
and generalizes is the manufactured-coverage class — each event type is its own drive.

### SUB-AGENT B — Cold-start reconciliation and the projection (§9, §4)

**B1 — The positions projection is rebuildable from the log.** Positions table = projection (§9); prove
it can be dropped and **rebuilt from the event log alone** to a state that matches the pre-drop
projection. §0a: a rebuild test that starts from an empty log proves nothing — rebuild from a log with
real open/partial/closed history and prove the projection matches.

**B2 — Cold-start reconciliation vs broker truth (§4, §9).** On boot the Limiter queries the broker
(authoritative positions + balance) and reconciles against the rebuilt projection. Crash gap between
last group-commit and the crash is healed here. Generalise the Sentinel-marker replay (§12.1) into the
same reconciliation: markers replay, HALT-while-down books retroactively (§12.5), unexpected positions
flatten-to-flat before registration (§4, the market-tradable guard from R2-B still applies). **§0a:**
prove reconciliation on a log that is genuinely BEHIND broker truth (a crash gap), not one already in
agreement.

**B3 — The crash gap, measured at a real durability boundary.** The window between the last
group-commit and a crash is the classic gap. Prove what is and isn't recovered — committed rows
survive, the uncommitted tail is reconstructed from broker truth — using a real fsync/power-loss
boundary per §0a, not a SIGKILL that leaves the page cache intact.

### SUB-AGENT C — Degraded persistence (§12.4)

**C1 — Postgres outage ⇒ WAL buffers, trading continues, operator alerted.** Kill Postgres mid-trade
and prove the Limiter keeps gating/reserving/protecting off memory + local WAL, buffering rows, with a
Warning alert (§12.9). Trading does NOT stop because the *record* degraded. **§0a:** a test where
Postgres never goes down measures neither the buffering nor the continuation.

**C2 — Disk-critical ⇒ HALT new entries.** When the local WAL itself cannot append (disk full/failed),
there is no audit trail for new risk, so new entries HALT — but **open positions stay protected**
(stops read memory, not disk). Prove both halves: new entries refused, existing stops still fire.
§0a: prove disk-critical is detected at the real failure (a full/failed WAL device), not simulated by a
flag.

**C3 — Reconnect heals.** When Postgres returns, the buffered WAL flushes in order via group-commit,
no rows lost, no rows duplicated (idempotent by the event's natural key). Prove ordering and
exactly-once against a real outage-then-reconnect, with a duplicate delivery planted (the §4 dedup
class one layer over).

### SUB-AGENT D — Drift audit (§11.7) and instrument debt

**D1 — Full-scan reconciliation (§11.7).** Periodically reconcile every running aggregate (Σ open
margin, Σ reservations, bucket exposure, net-liq, balance, positions) against ground truth (the log
projection + broker poll). Drift ⇒ audit event (Plane-1 + Plane-2); **material drift ⇒ HALT** (§12.5
setter). §0a: a drift audit on a system with zero drift never exercises the detector — plant a
divergence between a running aggregate and ground truth and prove it is caught, named, and HALTs on
material size.

**D2 — Discharge D3.191 residue / the uncalled-entrypoint sweep** (D2 from ARC 034, generalised): any
Plane-1 writer verb or reconciliation hook with zero production callers is a finding. The schema
existing is not the schema being written to.

**D3 — CHECK-DEBT reconciliation** with the derived-vs-narrated arithmetic gate (D3.82) over this arc's
own results.

---

## STAGE 2 — Integration (SERIAL)

**2.1 — The full crash-and-recover drill.** Trade → group-commit some rows → crash at a real
durability boundary → boot → cold-start rebuilds the projection, reconciles vs broker truth, replays
any Sentinel marker, books retroactive HALT if any, flattens unexpected positions before registration.
End to end, with the Plane-1 rows each step produces.

**2.2 — The degraded-persistence drill.** Postgres down mid-trade → WAL buffers, trading continues,
Warning alert → disk-critical → HALT new entries, open stops still fire → Postgres back → buffered
flush in order, exactly-once. The §12.4 ladder, measured end to end.

**2.3 — Sole-writer holds across all of it.** Through every path above, prove no row entered Plane-1
from anything but the Limiter's enqueue path. The one invariant that must survive schema, projection,
degradation, and reconciliation.

**2.4 — State honestly what remains.** R5 Scoring reads Plane-1 (realized P&L) but is not built; the
backup/DR policy (`elements_v2.md` §4 — pg_dump rotation, Backblaze B2, monthly restore dry-run) is a
later arc; live-venue is untested by design. Say it in the verdicts.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice, under both documented interpreters.
The Postgres connection, the WAL device, and the migration runner are new resource surfaces — fresh
false-declaration candidates.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f). BOUND floor = ARC 034's figure; any new
check UNBOUND or ENR is a finding named with its reason.

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
convergence step print a boxed banner — `ARC 035 · <Module>/<Stage> — STAGE <k>/<total>: <name>` + an
`~elapsed in · ~eta left` line — tagged `— PAUSED, awaiting operator` on any stop-for-ruling. Standing
rule; confirm it is recorded in `~/nix/CLAUDE.md`.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

R5 Scoring / EMA / ranking (reads Plane-1, not built) · the backup/DR policy (`elements_v2.md` §4 —
pg_dump rotation, Backblaze B2, monthly restore dry-run — a later peripherals arc) · the analytics
trade-history/candle/brick databases (`nix_db_schema_spec.docx` — separate store; only the seam where
a closed live trade migrates there is declared) · the dashboard · the strategy FSM · the tap session ·
changing branch protection. Say the deferrals in the verdicts.

---

## Open items returned to the operator / architect

1. **The tap session** — operator task at the console, ~40 min, owed by twenty-one arcs. Discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement,
   D1.39/D1.40, SPEC-A6's poll-channel lag figure, D1.50, the two Gateway gates' green. Only
   code-independent FAIL.
2. **Push · SPEC-A10 vendor · branch protection** (0.3) — all operator/outward-facing, still open.
3. **Backup/DR (`elements_v2.md` §4)** — a gated safety property (backup ran, produced a non-empty
   artifact, is restorable), owed as a peripherals-phase arc. Flag it so it is not forgotten — a
   backup that silently stops is the "green while measuring nothing" class.
4. **v1.4 fold + D3.33** — amendments now run to SPEC-A10; the v1.4 file lags; re-pointing every
   `§x:line` citation is owed. Architect debt.
5. **After this arc: R5 Scoring** — the last dependency-locked infra module (reads Plane-1, unblocks
   the Allocator's Scoring-dependent finish), then the Allocator finish → infra-100 → ULTRAREVIEW pass.
