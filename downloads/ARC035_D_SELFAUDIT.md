# ARC 035 · Stage 1 · SUB-AGENT D — §0a self-audit

**Branch:** `arc-035-d` · **Worktree:** `/home/bbt/nix-wt-arc-035-d` · **Canonical tree:** `/home/bbt/nix`
**Mandate:** D1 the §11.7 full-scan drift audit · D2 the uncalled-entrypoint sweep · D3 CHECK-DEBT
reconciliation.

Written and committed **before** the code, per the common brief §2 — ARC 033 and ARC 034 both lost
their sub-agents' reasoning to a session cap that killed them with the work staged and unbanked
(D3.191). An mtime is not history. This file is updated as I learn; every update is committed.

---

## THE QUESTION

> *What would have to be true for my deliverable to complete successfully while measuring nothing?*

Answered condition by condition, per deliverable. Each condition is a thing someone could plant.

---

## D1 — the full-scan drift audit (§11.7, §12.5)

§11.7 verbatim: *"Periodic **full-scan audit** reconciles every running aggregate vs ground truth
(drift ⇒ audit event; material drift ⇒ HALT)."* §11.3 names the running aggregates: *"Σ open margin,
**Σ reservations**, bucket exposure, **net-liq mark**, **balance**, per-position table."* §12.5 names
`aggregate-drift` as one of six HALT setters.

### D1.a — THE ZERO-DRIFT VACUITY. *The system under test has no drift, so the detector never fires.*

This is the brief's own §0a and it is the primary hazard. A full-scan audit written against a
correct system reports `drift = 0.0` on every aggregate, every arm passes, and **not one line of the
detection or escalation path is executed**.

**Closed by:** the gate plants a divergence in each aggregate independently and requires the audit to
catch it, NAME it (which aggregate, by how much, signed), and escalate correctly. A zero-drift
CONTROL arm runs alongside and must be SILENT — no rows, no HALT — because a detector that fires on
everything would pass the plant arms and fail nothing.

### D1.b — THE SELF-COMPARISON. *Both sides of the reconcile are the same arithmetic over the same data.*

The worst version of this defect, and it already has precedent in this tree:
`check_reservation_lifecycle`'s ARM SIGMA exists precisely because *"if `total_reserved()` were
computed FROM the store, the two sides of that reconcile would be the same arithmetic over the same
data and drift would be 0.0 over any defect at all."*

The same trap, one level up: if my audit computes the "running" value by folding the ground-truth
rows, every drift is identically zero, every plant is invisible, and the audit is furniture that
reports perfect health forever.

**Closed by:** the running side is read from the *published* `FinancialPicture` (§11.3's incremental
aggregates) and the ground-truth side is recomputed by `math.fsum` over the projection rows and the
broker poll. They are different objects from different producers. A **static (AST) arm** in the gate
asserts the audit never derives one side from the other — it reddens if the scan function reads the
picture's aggregate fields, or if the running side is recomputed locally.

### D1.c — THE UNJUSTIFIABLE THRESHOLD. *"Material" is a number nobody can defend.*

A magic constant makes the HALT arm a test of that constant, not of §11.7. Worse, a threshold tuned
against an observed run is an anchor that moves (debug.md §7.4) — the tree already records that
lesson at `reservations.AUDIT_TOLERANCE`.

**Closed by:** materiality is **DERIVED from two constants that were already set by measurement in
this tree**, and is not typed by me:

| band | condition | §11.7 consequence |
|---|---|---|
| noise | `abs(drift) <= reservations.AUDIT_TOLERANCE` (`1e-9`) | nothing. Float representation, not a lost commitment. |
| drift | `AUDIT_TOLERANCE < abs(drift) < reservations.MIN_MARGIN` (`1e-3`) | **audit event, both planes.** A real disagreement, but strictly smaller than the smallest commitment the ledger will admit — so it cannot BE a lost or duplicated commitment. |
| material | `abs(drift) >= reservations.MIN_MARGIN` | **audit event + HALT(`AGGREGATE_DRIFT`).** The drift is at least the size of one whole admissible commitment: something the system can hold has gone missing or been counted twice. |

The defence in one sentence: **material means "large enough to be a whole commitment", and the
smallest whole commitment this system admits is `MIN_MARGIN`, which `reservations.py` set by
measurement (its first value, `1e-6`, reddened `check_reservation_lifecycle`'s separation floor
because `1e-9 × 1000` is `1.0000000000000002e-06` in binary floating point).** Both figures are
IMPORTED, never restated (directive 3), so if either moves the audit's band moves with it.

**Integer-valued aggregates get no noise floor at all,** and that is a separate defensible claim: the
noise floor exists because a float sum of decimals is not exact. Contract counts are integers and
integer arithmetic is exact, so any non-zero difference in the per-position table — a row present on
one side and absent on the other, a size mismatch, a state mismatch — is a REAL difference and is
material by construction. A tolerance on an integer count would be a tolerance for losing positions.

### D1.d — THE ONE-AGGREGATE GENERALISATION. *One aggregate is reconciled; the others are named in a docstring.*

§11.7 says *every* running aggregate. A test that plants drift in `balance`, catches it, and
generalises to the other five is the manufactured-coverage class the brief names at A4 (*"a 'logging
works' test that exercises one event type and generalizes"*).

**Closed by:** the gate drives **one independent plant per aggregate** and requires each to be caught
and named individually. The aggregate roster is not a literal in the gate — it is read from the
audit's own declared roster AND cross-checked against §11.3's sentence parsed out of the frozen spec
at run time, so an aggregate dropped from the audit cannot shrink what the gate expects. A roster
below the spec's count is CANNOT_MEASURE, never PASS over a set it silently shrank.

### D1.e — THE UNREACHED HALT. *The audit reports material drift and nothing halts.*

D3.178's shape: a verb defined, never called. An audit that classifies drift as material, writes a
row saying so, and never touches the HALT machine has implemented the reporting half of §11.7 and
skipped the half that protects money.

**Closed by:** the HALT arm asserts against the **`HaltFlag`'s own observable state** — `is_set()`
returns `(True, ...)` and `AGGREGATE_DRIFT in flag.active` — not against a return value from the
audit and not against a mock's call count. And the sub-material arm asserts the flag is **still
clear**, because a detector that halts on everything also passes the material arm.

### D1.f — THE EXIT-CODE-ONLY CONTROL. *A red is asserted by its integer, not its reason.*

Check contract v2 §11, and Phase 0.4 of this arc caught it one level down (SQLSTATE 42501 on the
wrong object). A can-fail that asserts `status is FAIL` proves the gate produced a red, not that it
produced THIS red.

**Closed by:** every can-fail assertion in `scripts/tests/test_check_drift_audit.py` matches the
`site` and a substring of the `detail` naming the planted aggregate and the planted magnitude.

### D1.g — THE PLANT THAT PLANTS NOTHING. *`str.replace` with no match is a silent no-op.*

Bit twice in Phase 0 of this arc. A plant that matches nothing produces a green that reads as a gate
that failed to detect (debug.md §8 #4) — or, inverted, a red that reads as a successful plant.

**Closed by:** `_plant()` asserts `text.count(anchor) == 1` before writing, exactly as
`test_check_reservation_lifecycle.py` does.

### D1.h — THE DURABILITY CLAIM A PROCESS-KILL WOULD PASS VACUOUSLY.

The brief instructs me to assume one exists in my mandate and to name it. **Named:** my mandate says
the audit's ground truth is *"the Plane-1 log projection … plus a broker poll"*. Reading
`plane1_positions` **after a crash** and calling the result "ground truth" is a durability claim, and
a SIGKILL of a `psql` client — or of the Limiter — proves nothing about it: the rows are in the
server's buffers and a living kernel hands them back intact.

**How I close it:** *I do not make that claim.* This deliverable's audit reconciles against whatever
the projection currently says; it does not assert that the projection survived a crash. That
assertion belongs to B3 and to Stage 2.1 and is measured at `pg_ctl -m immediate` on an ephemeral
cluster, not here. Recorded as a **declared non-claim** rather than a silently weak one. See
"WHAT I DO NOT CLAIM" below.

### D1.i — THE BACKWARDS HAZARD.

The brief instructs me to assume one exists. **Candidate found, and it is in my own mandate's
phrasing**, not in the spec: my mandate states §12.10's table *"marks drift-audit as the one event
that is ✅ in both"* planes. Read against the frozen spec that is false in the direction that
matters — §12.10's table has **six** rows ticked in both planes (drift-audit, Sentinel deadman
flatten, HALT set/cleared, operator control actions, strategy lifecycle, cold-start reconciliation
outcome). Believing drift-audit is uniquely dual-plane would make a gate that asserts "exactly one
dual-plane event" go green today and red the moment anything else is wired — a gate anchored to a
misreading. I write the both-planes requirement for drift-audit and assert nothing about uniqueness.
Reported to the integrator per the common brief §1.

### D1.j — THE SEAM HAS NO `DRIFT_AUDIT` MEMBER.

`seam.EventKind` carries no `DRIFT_AUDIT` today, and its docstring states the governing rule: *"A
member lands here ONLY when the machinery that emits it exists."* The mechanism is exactly what D1
builds, so the member lands **with** it. `plane1.sql`'s `plane1_event_enum` already carries
`drift_audit`, so the schema side needs no change — the gap is seam-side only. If I emitted a
drift-audit row under a borrowed kind, the row would be unfindable by type and §12.10's inventory
drive would count it as a different event.

### D1.k — CROSS-BRANCH ASSUMPTIONS (stated, not assumed silently).

Sub-agents A, B and C are building in worktrees I cannot see. My audit therefore:

- takes ground truth through a **small declared port** (`GroundTruthPort` / a frozen
  `ProjectedPosition` record), not by importing B's projection module, which does not exist on my
  branch. When B's projection lands, the integrator wires it to the port; the port's shape is the
  contract and it is deliberately tiny.
- takes the Plane-1 sink through the **already-frozen `seam.Plane1Port`** and Plane 2 through the
  same `Plane2Port` Protocol shape `halt.py` and `supervision.py` already declare — so it introduces
  **no new writer** (§12.10: *"no new writers, ever"*). The audit enqueues through the Limiter's
  existing path; it does not open a connection, and nothing in my deliverable inserts into Postgres.

---

## D2 — the uncalled-entrypoint sweep

### D2.a — THE SWEEP IS RUN ON A BRANCH THAT CANNOT SEE THE SUBJECT.

Three sibling worktrees are adding exactly the class of artifact this sweep hunts — Plane-1 writer
verbs and reconciliation hooks. A sweep on `arc-035-d` alone is **structurally partial** and a clean
result here is not a clean result for the arc.

**Closed by:** saying so, in the report and in the debt row, and naming the exact command the
integrator must re-run on the merged tree. Not closed by widening anything.

### D2.b — THE DETECTOR ABSORBS ITS OWN ARC'S GROWTH.

The move ARC 034 explicitly refused: adding this arc's new uncalled surface to
`checks/uncalled_entry_points_baseline.json` makes the gate green and the finding vanish. The gate
offers three outs — wire it, delete it, or admit it by name in the ledger. Absorbing is not one.

**Closed by:** I do not touch the baseline. New uncalled surface is admitted **by name** in a debt
row.

### D2.c — MY OWN DELIVERABLE IS THE FINDING.

The audit I build in D1 is itself a reconciliation hook. If nothing calls it, D1 has built D3.178's
shape *inside the fix for D3.178* — which is precisely what my mandate warns about.

**Closed by:** stating the caller status of every symbol I add, honestly, in the report and in a debt
row. There is no Limiter loop in this tree to schedule a periodic audit from (§11.7 says
*periodic*), so an honest UNBOUND/uncalled admission is the correct outcome, not a fabricated
caller.

---

## D3 — CHECK-DEBT reconciliation

### D3.a — THE COLLIDING ROW NUMBER.

ARC 030 had exactly this: three sub-agents each opened their own `D3.117` blind. I cannot see the
other three branches' rows.

**Closed by:** I write **no** final series row. My rows go to `downloads/ARC035_D_DEBT_ROWS.md` as
PROPOSED text with no committed number, and the integrator assigns numbers once all four branches
are visible.

### D3.b — THE NARRATED FIGURE.

D3.82: the ledger's series-table figure must be DERIVED from a row scan, never typed, and
`check_derived_claims` compares them on every run. A hand-typed count is green until the next row
lands.

**Closed by:** I state the derivation mechanism for the integrator and type no count.

### D3.c — THE ASSUMED DEBT.

My mandate hands me four candidate rows "if you agree they are real (verify, don't assume)". Writing
all four because they were suggested is restating a brief, not measuring a tree.

**Closed by:** each of the four is verified against the tree before it is proposed, with the evidence
quoted; any that is already covered by an existing row is reported as such and NOT re-opened.

---

## WHAT I DO NOT CLAIM (declared non-claims, so the integrator does not read silence as coverage)

1. **No durability claim.** Nothing in my deliverable proves any row survives a crash. Ground truth
   is read as-is. Crash-gap durability is B3 / Stage 2.1, at `pg_ctl -m immediate`.
2. **No production wiring claim.** §11.7 says *periodic*. There is no Limiter run-loop in this tree
   to schedule the audit from, so the audit is driven by its gate and by tests and by nothing else.
   That is a D2 finding about my own work and it is reported as one, not hidden.
3. **No claim about the real `nix_plane1` database.** My gate is pure-Python over the audit module
   and touches no cluster. Treating `nix_plane1` as read-only, per the common brief.
4. **No claim that the aggregates I reconcile are the ones production maintains.** I reconcile the
   fields the frozen `seam.FinancialPicture` publishes. Bucket exposure and net-liq mark are NOT
   fields of that snapshot — they are derived (via `nixalloc.caps`) and held elsewhere
   (`nixrisk.survival`). How I handle that gap is recorded in the report; where a §11.3 aggregate has
   no producer on this branch, the audit reports it CANNOT_MEASURE by name rather than scoring it
   zero-drift, because a missing aggregate that reads as "agrees perfectly" is the worst possible
   default (§17: a safety property proven while its subject is unavailable is not proven).

---

## UPDATE LOG

- **entry 1** — written before any code, from a full read of the common brief, the arc brief, the
  frozen risk spec §9/§11/§12.1/§12.4/§12.5/§12.10, `docs/nix_plane1_schema_spec.md`,
  `databases/schema/plane1.sql`, and the existing `nixrisk` seam / halt / reservations / picture /
  survival / coldstart surface. Committed before the deliverable.

- **entry 2** — after the build, and the first attempt to bank entry 1 FAILED its commit gate, which
  is the reason this entry exists rather than a clean second commit. Seven tests came back red in a
  25-minute run. Two were real and five were an artefact, and telling them apart took a bisect:

  1. **`test_check_artifact_gate_coverage::test_NONVACUITY_..._COMMITTED_blobs` — REAL and
     PRE-EXISTING at `HEAD`.** Phase 0.2 of this arc discharged the last four `artifacts` rows by
     real coverage — the right outcome — which emptied the bucket the test's non-vacuity floor was
     taken over, so `max([])` raised `ValueError`. Reproduced at pure `HEAD` with my own files moved
     aside, so it is not mine. **Repaired**, and the repair is the point: the floor now runs over the
     COMMITTED HISTORY rather than over `HEAD`'s bucket, because an arm whose subject can be emptied
     by the very repair it certifies is an arm that switches itself off exactly when the debt is
     paid.
  2. **`test_check_order_path_bans` — REAL and MINE.** That test keeps a deliberate LITERAL module
     count (D3.192: two ARC 034 branches each wrote "25 -> 27" and both were locally right and
     globally wrong). 29 → 30 for `drift_audit.py`, with a loud note that the integrator must re-bank
     on the merged tree, and a re-scan confirming the module adds no banned call, banned module or
     retry shape.
  3. **The other five were CONCURRENCY.** Three sibling worktrees were running `pre-commit` against
     the same shared `/home/bbt/nix/.git` at the same time, and the aftermath left this worktree's
     INDEX showing all 429 tracked files as staged deletions while the files sat untouched on disk.
     Repaired with `git reset`. All five pass standalone. **Recorded because it is a live measurement
     hazard for this arc's integrator: a red produced by a neighbour's `git stash` is
     indistinguishable, in the log, from a red produced by the code.**

  Two further findings the build produced, both about instruments changing each other's populations:

  - **`checks/check_uncalled_entry_points.py` reported `halt.py::HaltFlag.active` and
    `reservations.py::LedgerAudit.material` as having ACQUIRED coverage** — a rot FAIL in two modules
    this branch does not touch. Neither was true. The gate resolves a call site by the receiver's
    TYPE, and both attributions came from unresolvable receivers: my gate called `flag.active()`, and
    my module read `r.material` inside two comprehensions whose loop variable has no resolvable type.
    **Fixed at the cause in both places rather than by editing the baseline** — the gate now asserts
    the HALT cause off the AUDITED Plane-1 row (which is a stronger assertion: §12.5:633 is about the
    audited event, and an in-memory cause that never reached Plane 1 would satisfy `active()` and
    fail the spec), and the module filters through an annotated predicate. Both rot defects are gone.
    Removing the two baseline rows would have been the cheap fix and would have recorded false
    coverage of two genuinely uncalled verbs.
  - **My own module adds SIX uncalled entry points**, and they are admitted BY NAME in
    `_ARC035_D_CARRIED` in `test_check_uncalled_entry_points.py` — never in
    `checks/uncalled_entry_points_baseline.json`. The gate stays RED on them, which is the honest
    state. This is D2.c above, confirmed by measurement rather than predicted: the fix for D3.178
    does contain D3.178's shape, and it is reported rather than hidden.

  **Nothing in the self-audit above was falsified by the build.** The one thing it under-stated is
  D1.k: the cross-branch assumption is not only about B's projection module. `plane1_positions`
  carries **no margin column at all**, so Σ open margin's ground truth has to be reconstructed from
  the running side's margin cache — a real weakening of the separation rule, declared in the module
  docstring and carried as a proposed debt row rather than left implicit.
