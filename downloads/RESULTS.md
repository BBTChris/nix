# ARC 029 — R2-B: The Exit Half — **STATUS: COMPLETE (on branch `arc-029-convergence`, pending operator merge)**

**Canonical path:** `/home/bbt/nix`. **Work branch:** `arc-029-convergence` (an isolated worktree at
`/home/bbt/nix-wt-arc-029-convergence`, base `bafe6eb`). **The final merge to
`arc-029-integration` on `/home/bbt/nix` is the operator's step** — see "The concurrent-session
collision" below, which is why the arc was isolated onto its own branch to converge and close out.

---

## HEADLINE

The Limiter can now **exit**. ARC 028 built a gate/reserve/publish/log spine that could not protect
money once committed; this arc built the half that does: **synthetic stops, protective flatten,
net-liq survival watch, cold-start reconciliation, and idempotent execution handling**, each measured
against its own §0a hypotheses rather than assumed, and every protective path fired end-to-end in one
composed simulation. The arc opened with an architect ruling (D3.104) and a mechanism to obey it, and
it closed against a branch a second session was concurrently committing to — handled by isolating the
convergence onto its own worktree.

```
verify.py    28 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded    exit 1  (33 checks)
pytest       1454 passed | 1 skipped | 2 xfailed   (worktree, after the convergence count fix)
binding      32 BOUND | 1 EXERCISED-NEVER-RED  (883 observations)
CHECK-DEBT   151 open (derived:ledger_rows == stated:series_table_latest_row)
plan         --optimize membership IDENTICAL to committed (no drift)
```

**The two FAILs, attributed:** `check_ibgateway_service` is the standing tap-session debt (owed by
fourteen arcs, a hardware switch, not code). `check_monitor` is the **concurrent ARC MON-1 arc's**
check, failing on its own harness — not ARC 029's, and on the shared branch only because that arc's
work is interleaved here. The **one GUARDED** is `check_artifact_gate_coverage` — the D3.104
disposition working exactly as ruled.

---

## PHASE 0 — D3.104, the declared exclusion (committed `6eb4d88`)

The architect ruled OPTION 3 as a HOLDING state for ARC 029 only. The re-owning ceiling (operator
ruling, ceiling of two) fired when 0.5 re-pointed thirteen already-at-ceiling artifacts to a fourth
owner; the marker could not be walked forward and could not be reverted without naming a completed
arc. Those thirteen moved OUT of the guard into a declared, temporary `exclusions` bucket, each with a
written justification, all owned by ARC 030 (the committed bulk-retrofit arc that empties it).

**An exclusion escapes the re-owning ceiling and NOTHING else** (check-contract rule 10, new): still
inside the one-way ratchet (silent growth and acquired coverage are FAILs), still owned by a live arc
(a completed owner is CANNOT_MEASURE, so it cannot outlive ARC 030), still assigned under §0g, and
required to justify itself and declare itself temporary. The ceiling is the one rule lifted, and only
under the recorded ruling — the gate cannot tell an authorized move from a laundering one, which is
why the authorization lives in the ledger (**CHECK-A8**, CHECK-DEBT D3.104) and the contract
(**CLAUDE.md rule 14**, `nix_check_contract.md §19`), per rule 13. Verdict FAIL → GUARDED. Each
exclusion arm planted and driven red on the shipped gate; the real-tree control re-aimed to bank the
disposition.

---

## STAGE 1 — the exit half, four parallel sub-agents (committed `4bd425f`)

Four modules built against the Phase-0.6 frozen seam (none modified it), 93 behavioural can-fail
tests, each MEASURING its brief's hypotheses:

* **`stops.py`** (V33) — `StopBook`: distance→price conversion once at fill; fixed and trailing modes;
  the trailing activation latch proven to ratchet and never jump backward at the activation instant.
  Covered by **`check_synthetic_stop_only`** (§12.1: AST-scans the stop path for any broker-native
  stop order), which the binding census confirms **BOUND**.
* **`flatten.py`** (§3/§14) — `ProtectiveFlatten`: zero-wire fire proven by REMOVING the wire;
  dual-authority precedence proven under a CONSTRUCTED race; onset cancels pending entries under their
  own TerminalPath cause (blackout vs HALT, SPEC-A7); reconcile-then-publish publishes the CONFIRMED
  flat state.
* **`survival.py`** (§6.5/§15 C2) — `SurvivalWatch`: net-liq and cash driven APART so the watch is
  shown to track net-liq while sizing tracks cash; floor breach fires the flatten AND a Critical
  alert; uniform broker-authoritative reconcile, broker-wins at WARNING tier (tiers do not collapse).
* **`coldstart.py`** (V34) — `ColdStart`: the registration gate proven by a REFUSED attempt (not a
  flag read); flatten-before-register; the market-tradable guard proven on BOTH halves (held-in-HALT
  while shut, flattened on reopen); restart = flat even for a winning inherited position.

**Integration findings the gates caught and I resolved by measurement:** `check_order_path_bans`
self-healed its derived scope to `scripts/nixrisk` (the exit modules fire broker orders) — the second
home confirmed in `ORDER_PATH_DIRS`, its scope claim reconciled 6→16; a genuine fan-out in
`flatten.py`'s onset cancel loop reviewed-and-suppressed (broker precedent); its arm(ii) made
package-aware to import the nixrisk package. `flatten/survival/coldstart` admitted to the coverage
baseline as `measured_by=tests` (owner ARC 030), mirroring `gitenv.py` — gate GUARDED, not a proxy
check.

---

## STAGE 2 — integration (committed `6d014c8`, `eac5a00`, and — see collision — bundled into `ec03d06`)

* **2.2 EventKind amendment + Plane-1 collapse** (`6d014c8`). The frozen seam's `EventKind` gained the
  five exit-half members (`PROTECTIVE_EXIT`, `EXIT_INTENT`, `CLOSED`, `CANCEL`, `COLD_START`) once the
  mechanism existed — the SPEC-A7 route. `flatten.py`'s interim `ExitEventLog` was DELETED; every exit
  row now enqueues through the real `Plane1Port` as an `EventRow`. §9 sole-writer holds. `coldstart`
  books under `COLD_START` instead of borrowing `BOOT`.
* **2.1 + 2.4 the integration simulation** (`eac5a00`). `test_exit_integration.py` (10 tests) composes
  the four modules — one simulated broker, ONE Plane-1 writer — and drives each fireable trigger end
  to end: synthetic-stop, net-liq-floor, uncertainty, onset (HALT + blackout, both the CANCEL and
  RESERVATION_RELEASED rows on the one writer). §2.4 DRIVEN: `SESSION_CLOSE` and `SENTINEL` refused
  loudly (R4); `STALE_PRICE`/`ORPHAN` detection declared, not driven. Also: filesystem-walking gates
  taught to skip `.claude/` agent worktrees.
* **2.3 idempotent execution handling** (`execution.py`, in `ec03d06`). Position = Σ signed_qty over
  the SET of unique `(order_id, exec_id)` fills — immunity to duplicate AND out-of-order delivery is a
  property of the type, not a discipline. 23 tests; the §0a hypothesis ("a dedup test that never
  delivers a duplicate measures nothing") MEASURED with a planted dedup-less accumulator shown vacuous
  on a clean stream and divergent on the same stream duplicated. Contradictory same-key re-deliveries
  fail closed.

---

## STAGE 3 — convergence (this branch)

* **3.1** plan `--optimize`: membership **IDENTICAL** to committed, 33 checks. No drift.
* **3.4** binding census: **32 BOUND, 1 EXERCISED-NEVER-RED** (`check_untracked_attribution`), 883
  observations. `check_synthetic_stop_only` BOUND; the retrofitted `check_order_path_bans` stayed
  BOUND (its drive test still exercises it to RED). The standing figure moved 30→32 BOUND, explained
  by the two new bound checks (`check_synthetic_stop_only` this arc, `check_monitor` from ARC MON-1).
* full pytest surfaced ONE stale banked figure — `test_the_control_passes...` asserted `arm(ii)
  imported 15`, now **16** because Stage 2.3 added `execution.py` to the nixrisk package the
  order-path gate scans. Corrected; suite green.

---

## CHECK-DEBT — 145 → 151 this arc

Opened D3.101–D3.104 (Phase 0), D3.105–D3.108 (Stage 1: the three admitted exit modules' owed checks +
the stale-worktree-base provisioning finding), D3.109–D3.110 (Stage 2: the execution ledger's owed
check + two seam questions; the filesystem-walking-gate class vs `.claude` worktrees and AppleDouble
sidecars). Discharged D3.55 (SPEC-A7). `check_derived_claims`' `derived:ledger_rows` == `stated`.

---

## THE CONCURRENT-SESSION COLLISION — why this arc is on its own branch

Mid-arc, a **second Claude session ran a separate "ARC MON-1" arc on the same branch and shared git
index** (monitor tooling: `monitor.py`, `harness.py`, `check_monitor`, its own SESSION/RESULTS
write-back). The two sessions collided: Stage 2.3's staged work landed inside the other session's
commit `ec03d06` rather than its own message; pre-commit stashes reverted the other's uncommitted
edits (restored from patch each time); commit gates timed out. **No ARC 029 work was lost** — every
artifact is durable in the shared history — but convergence needs a STABLE tree to measure against, so
per the operator's decision the remaining Stage 3 + Phase 4 was moved onto an **isolated worktree
branch** (`arc-029-convergence`), where the measurements above are stable. The other session
meanwhile advanced `arc-029-integration` to `ba41431+`.

Two junk classes the collision surfaced were cleaned/hardened: 45 macOS AppleDouble `._*` sidecars a
Mac/Samba transfer dropped (they crash `rglob`-walking gates on non-UTF-8 bytes), and `.claude/`
worktree pollution of filesystem-walking gates. `check_price_ring`, `check_datafeed_granted_mode` and
`check_datafeed_bar_seal` were hardened; the broader class is CHECK-DEBT D3.110.

---

## OPEN TO THE OPERATOR / ARCHITECT

1. **MERGE `arc-029-convergence` into `arc-029-integration` on `/home/bbt/nix`.** This is the step that
   lands ARC 029 on the canonical path; it was isolated to keep convergence measurements stable while a
   second session held the branch. Expect a SESSION.md / RESULTS.md merge with ARC MON-1's write-back.
2. **`check_monitor` is FAILING** (harness exited 1) — that is ARC MON-1's check, surfaced here only
   because its work shares the branch. Its arc owns it.
3. **The tap session** — still the standing `check_ibgateway_service` FAIL, owed by fourteen arcs.
4. **D3.104 exclusion is TEMPORARY**, owned by ARC 030 (the bulk-retrofit arc: real per-artifact
   coverage for the thirteen, empty the bucket, drive the gate green by measurement).
5. **Seam questions (D3.109):** does `ExecutionReport`/`ExecutionLedgerPort` belong in the frozen seam
   by the `reservations.py` precedent; is `PositionRow.size` signed. And v1.4 remains deliberately not
   authority (D3.33), now also carrying the Stage-2.2 EventKind additions as an implementation fact.
