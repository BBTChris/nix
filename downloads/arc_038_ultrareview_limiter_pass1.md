# ARC 038 — ULTRAREVIEW: Risk Engine / Limiter (pass 1)

**Module under audit:** Risk Engine / Limiter (Core 2) — the authority module. FROZEN for this arc.
**Predecessor:** ARC 037 (merged & pushed; infra code+sim complete, HEAD `f059ea4`, origin in sync)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Phase:** ULTRAREVIEW (post-infra-100). This is the FIRST deep-audit arc. **No new features.**
**Shape:** Phase 0 serial · Stage 1 **wide parallel adversarial fan-out** (each sub-agent attacks a
different locked invariant) · Stage 2 serial reconcile + re-audit the merged findings · Stage 3
convergence · Phase 4 close-out.

**Badge rule (standing, memory #14):** the Limiter's status-board badge flips red ✗ → green ✓ **only
when every finding this audit surfaces is DISCHARGED, not deferred.** If pass 1 surfaces blocking
findings, the Limiter stays RED and ARC 039 is **ULTRAREVIEW: Limiter pass 2** on the SAME module.
We do not advance to broker-order until the Limiter is fully clean. ULTRAREVIEW findings may NOT be
banked forward — that is the whole difference from a build arc.

---

## WHAT THIS ARC IS

ARC 038 does not build. It **attacks a frozen Limiter** and asks, of every locked invariant in §14 and
every gate/reservation/exit/authority claim the module makes: *what would have to be true for this to
hold in the tests while being false in reality?* The Limiter passed a **design** ULTRAREVIEW already
(§16, the "locked, ULTRAREVIEW-2" tags). This is the **implementation** ULTRAREVIEW: does the built
code actually enforce what the design hardened, under adversarial conditions, in a real interpreter?

**Method (per operator standing rule):** deep adversarial audit in a REAL interpreter — `asyncio.run`,
real subprocesses, `pgrep`/`/proc` for liveness, real SIGKILL for death, real Postgres for the record.
No mental walkthroughs; no `FakeIB`-only proofs where a real boundary is available. Every invariant is
driven to its edge and its corner, and the "measures nothing" question is asked of each existing gate
that claims to protect it.

**The audit targets — §14's locked invariants, plus the money-truth seams:**

| # | invariant / claim (§14, §3, §4, §6.5, §9, §11) | the thing to break |
|---|---|---|
| I1 | Nothing reaches broker-order without passing the Limiter | a path to the sender that skips the gate |
| I2 | Every reservation reaches exactly ONE terminal release | a leak path or a double-release |
| I3 | The exit/protective path has ZERO wire/delivery dependency | a hidden dependency that stalls the flatten |
| I4 | "Open" = confirmed fill only, never optimistic | a state that reads OPEN on a placement ack |
| I5 | One in-flight per strategy, and it can never wedge (GO-timeout) | a wedge that survives the timeout |
| I6 | Survival on net-liq; sizing on cash — never conflated | a path that sizes on net-liq or survives on cash |
| I7 | The financial-picture snapshot is ATOMIC (balance+table together) | a reader that sees a torn/stale-fresh mix |
| I8 | Limiter is the SOLE Plane-1 writer | a second writer, or a write that skips the WAL |
| I9 | Hot path = cache reads + arithmetic only | a synchronous I/O or compute on the gate path |
| I10 | Two-phase gate: size-independent (A) before size-dependent (B) | a size-dependent rule evaluated on a dead signal |
| I11 | Blackout/HALT onset cancels pending ENTRY orders (exits untouched) | an entry that fills inside a window it wasn't approved for |
| I12 | The cap is fed by REAL values (D3.178 closed in 034) | the cap pricing a stale/wrong/zero distance |

---

## §0a — the audit's own honesty clause

The audit instrument is itself under audit. ARC 037 caught a gate measuring **production code while
reporting on a staged tree** (inherited `PYTHONPATH`), and 035 caught controls masking themselves
three times. **So every audit control this arc writes must prove it CAN fail** — plant the exact
violation of the invariant, confirm the audit reddens and names the site, remove the plant, confirm it
passes. An audit that never sees the invariant broken has measured nothing, and in an ULTRAREVIEW that
is the cardinal sin. Assume at least one existing Limiter gate is green over a real gap (the project
has found one nearly every arc), and audit the gate, not just the code it claims to cover.

## §0b–§0j standing (resolve labels to ledger ids, D3.81).

---

## PHASE 0 — Freeze, baseline, and the audit contract (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk, stating the interpreter.** Expect ARC 037's close: verify.py
`87 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded`, exit 1; pytest 3258; census 92
three ways; binding BOUND=79; CHECK-DEBT 309. **Any delta is a finding.** Discharge or re-own
`check_artifact_gate_coverage` (owner ARC 038 per D3.342).

**0.2 — FREEZE the Limiter.** No production Limiter code changes in Stage 1 except to **discharge a
finding this audit raises** (an ULTRAREVIEW may fix what it breaks — that is the point — but it may not
add features or refactor for taste). Record the frozen SHA of every Limiter file under audit; a Stage-1
change to a frozen file that is not tied to a named finding is itself a finding.

**0.3 — The audit contract.** For each invariant I1–I12, the assigned sub-agent must produce: (a) a
**red-team attempt** — a real adversarial scenario that tries to violate it in a live interpreter;
(b) either a **reproduced violation** (a finding, with the exact site) or a **proof of resistance**
(the invariant held, shown by the attack failing to break it, not by the attack being absent); and (c)
an audit of the **existing gate** that claims to cover it — does that gate redden when the invariant is
planted-broken? Non-vacuity first: prove the gate's scope contains its subject before trusting green.

---

## STAGE 1 — Wide parallel adversarial fan-out (attack surfaces, one invariant-cluster each)

Each sub-agent from its own worktree + index + venv (ARC 030 isolation). These are **read-mostly
audits** — most produce findings + audit-strengthening, not module rewrites — so the D3.192 shared-
literal conflict surface is smaller than a build arc, but the merge still collects findings and the
integrator still re-audits the merged tree (Stage 2). Partition by invariant cluster:

### SUB-AGENT A — The gate wall (I1, I10, I11)
Attack "nothing reaches the broker without passing the Limiter." Try every path to the sender thread —
exit path, operator flatten, Sentinel, retry, reconnect — and prove each either passes the gate or is
the one authorized exception (exit/Sentinel). Attack the two-phase ordering: force a size-dependent
rule to evaluate on a signal the size-independent phase should have dropped. Attack I11: drive an entry
order pending at blackout/HALT onset and prove it is cancelled, never filled inside the window.

### SUB-AGENT B — The reservation ledger (I2)
Attack "every reservation reaches exactly one terminal release." Drive every terminal path — fill,
cancel, reject, pending-timeout, blackout-onset cancellation — and prove exactly one release each.
Then adversarially: concurrent terminal events on one reservation (fill racing a blackout cancel),
partial fill (release the unfilled portion, not the whole), a reject arriving after a timeout already
released. Hunt a double-release and a leak. This is the §15 C1 double-spend race — prove it stays
closed under real concurrency, not the single-threaded happy path.

### SUB-AGENT C — The exit brake (I3, I4)
Attack "the exit path has zero wire dependency" and "open = confirmed fill only." Kill every
dependency the exit path might secretly hold (the state bus, Postgres, the Allocator mirror, the price
cache) and prove the synthetic-stop flatten still fires via the in-process direct call. Attack I4:
find any state transition that reads OPEN on a placement ack rather than a confirmed fill (the
optimistic-open bug the invariant forbids). Drive protective-vs-discretionary and prove protective
always wins.

### SUB-AGENT D — Money-truth accounting (I6, I7)
Attack "survival on net-liq, sizing on cash" — trace every sizing computation and prove it reads cash,
every survival/floor check and prove it reads net-liq; hunt a single conflation. Attack I7 atomicity:
drive a reader (the Allocator mirror) concurrent with a balance+table publish and prove it can NEVER
see a stale-balance / fresh-commitment mix (or vice versa) — the torn-snapshot the atomicity rule
forbids. This is the highest-value break in the module: a headroom computed off a torn snapshot is a
survival-floor violation waiting to happen.

### SUB-AGENT E — The sole writer and the record (I8, I12)
Attack "Limiter is sole Plane-1 writer." Try to write a Plane-1 row from a non-Limiter identity (the
037 realized-P&L path, the Sentinel marker, any other) and prove it is refused/absent-by-construction.
Attack I12: prove the cap prices the REAL stop_distance from a real fill (034's close), and hunt any
path where the cap could price a zero/stale/wrong distance — the fail-open-cap class (031) at the
implementation level. Prove the WAL → group-commit path has no write that skips the WAL.

### SUB-AGENT F — Liveness, wedge, and the hot path (I5, I9)
Attack "one in-flight per strategy, never wedges." Kill the Allocator holding a GO and prove GO-timeout
resets the strategy to flat-and-free; try to wedge the in-flight lock (lost message, double GO, timeout
racing a late feedback) and prove it can't. Attack I9: instrument the hot gate path under load and prove
it does cache-reads-and-arithmetic only — no synchronous Postgres write, no EMA computation, no blocking
I/O. Drive gate evaluations concurrent with group-commit and prove the gate never blocks on the commit.

### SUB-AGENT G — The audit instrument itself (§0a, cross-cutting)
While A–F attack invariants, G audits the **gates that already claim to cover them.** For each existing
`check_*` that guards a Limiter invariant, plant the invariant-violation and confirm the gate reddens
and names the site; if it stays green, that gate measured nothing (a finding, the 037/035 class).
Specifically re-audit under the staged-tree / `PYTHONPATH` condition 037 found, and the both-halves-
control-can-fail condition 035 found. G is the reason this is pass 1 of possibly several.

---

## STAGE 2 — Reconcile and re-audit the merged tree (SERIAL)

**2.1 — Collect and dedupe findings** from A–G into one ledger section: each finding = invariant,
site, the adversarial scenario that surfaced it, and whether it is DISCHARGED in this arc or blocks.
**2.2 — Re-audit the merged tree** for the cross-branch defect class the last three arcs all hit (a
fix on one branch bolted to a thing another branch changed; a gate green while breaking a successor).
Run the full audit suite on the merged tree, not just per-branch.
**2.3 — The discharge bar.** For each finding: is it fixed, with a control that proves the fix AND can
fail? A finding "understood but not fixed" does NOT clear — it keeps the Limiter RED and defines pass 2.
State plainly which invariants are proven-clean and which are not.
**2.4 — The verdict on the badge.** Either: every I1–I12 clean and every existing gate proven non-
vacuous ⇒ Limiter badge flips green ✓; OR one or more findings block ⇒ Limiter stays RED, and name
exactly what ARC 039 (Limiter pass 2) must discharge.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff.
**3.2** Observer sweep of any new audit checks (≥3 orders, 2 sweeps, both interpreters, cold cache) —
and specifically re-run under the staged-tree condition 037 flagged.
**3.3** Census three ways.
**3.4** Binding table rebuilt (§0f). BOUND floor = ARC 037's 79; every new audit check must be BOUND
(observed producing a real FAIL under its plant) or it is itself a vacuous gate.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk, stating the interpreter. Baseline: `check_ibgateway_service` FAIL (tap) +
   `check_uncalled_entry_points` standing + the standing cannot-measures. A further FAILURE is a
   finding; any further NON-PASS whose cause is unnamed is a finding. Name every GUARDED check + owner.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every measurement; D2.24 ignore-rules-per-target; D3.205/D3.22 gitenv scrub on
   every subprocess git call.
5. Write-back to `/home/bbt/nix`: append to END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; run any predicted post-write-back re-measure and BANK it BEFORE the marker
   (§0j); `cat` both as the final action; **prove HEAD advanced** (§0d); state the absolute path.
6. Clean up temp files and all worktrees (prove `git worktree list` shows only `/home/bbt/nix`).
7. **The badge verdict, explicit:** print whether the Limiter's ULTRAREVIEW badge flips green ✓ or
   stays RED, and if RED, the exact finding list ARC 039 must discharge.
8. **Per §0j: `**** ARC completed ****` is the LAST token, printed once, nothing after it.**

**WAYPOINTS + HEARTBEAT (standing, both required).** At kickoff echo the total stage count once. At the
start of every phase/stage/sub-agent/convergence step print a boxed banner —
`ARC 038 · Limiter-ULTRAREVIEW/<Stage> — STAGE <k>/<total>: <name>` + `~elapsed in · ~eta left` —
tagged `— PAUSED, awaiting operator` on any stop. **AND** within any long-running stage print a
PROGRESS HEARTBEAT at least every ~10 minutes of wall-clock (or at each meaningful sub-step): a compact
one-line ticker — overall-arc % (monotonic, stages done + fractional current-stage progress), current
stage k/total, what's happening now, elapsed, and projected time remaining / finish
(e.g. `[ARC 038 ▓▓▓▓░░░░ 47% · stage 5/12 · attacking I7 atomicity · 2h38m elapsed · ~3h left]`).
Print a heartbeat before and after any long silent operation (a big sweep, a merge) so there is never a
>~10min silent gap. Both rules are recorded in `~/nix/CLAUDE.md`.

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the ULTRAREVIEW phase forward (parenthetical)>===`

---

## Explicitly NOT in this arc

New features of any kind · any module other than the Limiter (broker-order is ULTRAREVIEW #2, next) ·
the production fill feed / ranking publish (reference-strategy phase, post-ULTRAREVIEW) · the dashboard
· the strategy plug-in · backup/DR · the tap session. An ULTRAREVIEW that grows scope beyond its one
module has stopped being a deep audit.

---

## Open items returned to the operator / architect

1. **The tap session** — console task, ~40 min, still the only code-independent FAIL.
2. **SPEC-A10 vendor · branch protection** — operator/outward-facing. (Push is DONE — origin in sync
   at `f059ea4` as of ARC 037.) Branch-protection note: the last push bypassed the PR-only rule via
   admin; the drafted status-checks-required ruleset needs CI wiring first.
3. **Backup/DR (`elements_v2.md` §4)** — gated safety property, peripherals phase.
4. **The ULTRAREVIEW sequence after the Limiter is green:** 2 broker-order · 3 broker-datafeed ·
   4 Sentinel · 5 Postgres/Plane-1 (fold the power-cut boundary 90→100 here) · 6 Scoring · 7 Allocator
   · 8 Pollers+Calendar · 9 verify.py/checks (the instrument, audited LAST). Serial, one module held
   until clean, per standing rule.
