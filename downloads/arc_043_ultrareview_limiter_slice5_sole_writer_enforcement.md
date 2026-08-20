# ARC 043 — ULTRAREVIEW: Limiter, slice 5 — I8 sole-writer ENFORCEMENT

**Tier: INTERIOR.** Limiter badge **STAYS RED** (this is not the greening slice — invariants remain
open after it). **This slice DISCHARGES AN INVARIANT: I8 → clean set becomes 5/12.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `/home/bbt/nix/.venv/bin/python` →
`/usr/bin/python3.14` (3.14.4).
**Predecessor: ≈ `382cbd4` (approximate — ARC 042's measurement tip).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT, never the cited sha (the post-write-back
re-measure commits after the RESULTS HEAD — 042's cited `1abcfd0` was really `d6dae6f`).
**Model: Opus 5** — sole-writer is THE authority invariant of the whole subsystem; this needs
Postgres privilege reasoning plus an adversarial "can a second writer get in" proof, not an edit.

## The invariant — I8

**§9 / §12.10 lock it: "Limiter = sole writer … No new writers, ever."** §12.7 says raw shared state
would reduce "the single-writer principle to fiction"; §12.1 (Sentinel) and §12.5 (HALT-while-down)
go out of their way to use the **marker-file → cold-start replay** pattern *precisely so they are not
a second Postgres writer* — "sole-writer invariant stands." ARC 038 pass 1 found the invariant is
**convention, not enforcement**: nothing structurally prevents a non-Limiter process (a poller, the
Scoring process, a stray script, a bug) from writing a Plane-1 row. A forged money-truth row would be
indistinguishable from a real one. I8 is unmet until a second writer is **structurally refused**.

**The invariant has two halves, both load-bearing:**
1. **A non-Limiter process attempting to produce a Plane-1 row is REFUSED** — by the database, not by
   good manners. Cooperative mechanisms (an advisory lock only the polite check) are NOT enforcement:
   a rogue `INSERT` bypasses them. Enforcement means the write is *rejected regardless of cooperation*.
2. **The sanctioned writer path still works, in full.** limiterd's own bookings (the ARC-042
   go_timeout row), and the §12.1/§12.5 **marker-replay via cold-start**, must survive — those route
   *through* the Limiter's writer identity, not as independent writers, and enforcement must not
   break them.

## KICKOFF OBLIGATIONS (before Stage 1 — all mandatory)

1. **Tier + count + the D3.434 ruling.** Echo `TIER = INTERIOR`. Derive clean/open from the tree
   (038 register): clean `{I5, I6, I7, I10} = 4/12`, open = 8; **this slice targets I8 → 5/12 if
   discharged.** THEN answer the sequencing question the operator is owed: **read the 038 register
   and state whether ANY of I1–I12 requires full §9 event-booking coverage.** If YES, D3.434 (the ten
   unwired event types) is Limiter-greening-blocking and must be scheduled before greening; if NO,
   D3.434 is Plane-1-module debt and the Limiter can green on its 12 invariants without it. State the
   answer plainly in the kickoff — it is a real operator decision, do not leave it implicit.
2. **Status via the tooling (dogfood).** kickoff → `scripts/arc_heartbeat.sh selfcheck`; pulses/beats
   → `pulse`; transitions → `banner --name`. Teardown line EXACTLY the CLAUDE.md STATUS EMIT string
   on its OWN line — no `[watchdogd]` on it (041-T's D-finding). `check_arc_status_contract` will
   audit this log.
3. **Ops pre-flight.** `checks/check_tmpfs_inode_headroom.py --mount /tmp` + clean stale basetemps.
   **Coverage report:** determine which process actually holds the INSERT-capable Plane-1 connection
   (limiterd? `plane1_sink.py`? a shared-pool writer?) and whether the files this slice will touch are
   on the runtime gate's `uncovered` list. If `limiterd.py` is touched, **the commit gate escalates
   to a full pass (~43 min, unavoidable — the tier defers the close-out suite, not the commit)** —
   size the ETA and say so. If only `plane1_sink.py` + a migration + the gate move, it may not
   escalate; report which. **Also note the 60 orphaned `nixp1t_*` scratch DBs (D3.437)** at pre-flight
   — do NOT bulk-drop them (operator action), but confirm this slice's scratch DBs are cleaned at
   teardown so it adds none. **F6/F7:** never launch a second commit until the first's gate process is
   dead BY PID; never `pkill -f`/`pgrep -af` on cc's own patterns.

## S1 — REPRODUCE "convention, not enforcement" FIRST, before a line changes

Bind to the REAL topology: the real Plane-1 event-log table, the real connection/role the writer uses
today, and the real WAL. On the live cluster:

* Stand up a **second process that is NOT the Limiter** (a plain script with an ordinary DB
  connection) and have it **produce a Plane-1 row** — INSERT into the event-log table (and/or enqueue
  to the WAL, whichever surface a rogue writer could reach). Show the row **lands** and is
  indistinguishable from a legitimate one. That success IS I8's defect.
* **Non-vacuity of the reproduction:** prove the row genuinely landed in the real Plane-1 table (SELECT
  it back), and prove the second process is genuinely not the Limiter (different role/pid/identity) —
  a "second writer" that is actually the Limiter's own connection proves nothing.
* Record which surfaces a rogue writer can reach: direct Postgres `INSERT`, WAL append, or both. The
  enforcement in S2 must close **every** surface S1 finds open.

## S2 — THE ENFORCEMENT (structural, database-level)

Make a non-Limiter write **structurally refused**. Strongly prefer **Postgres role/grant** as true
enforcement over any cooperative mechanism:

* **REVOKE** `INSERT` (and `UPDATE`/`DELETE` — the log is append-only, §9 "never overwrite") on the
  Plane-1 event-log table from `PUBLIC` and every non-writer role; **GRANT** it only to the
  **writer role**, which the sanctioned writer process connects as. A rogue `INSERT` from any other
  role then fails with a permission error at the database — enforcement that does not depend on the
  rogue being polite.
* If a role/grant migration framework does not exist in this tree (Plane-1 was "WAL + group-commit,
  no schema" at one point), **that gap is a finding** — report the real DDL/migration surface, use it
  if it exists, and if establishing it would balloon the slice, implement the strongest enforcement
  the tree supports now and NAME the rest as debt rather than widening. A **BEFORE-INSERT trigger**
  rejecting writes whose `current_user`/session identity is not the writer is acceptable hardening
  (the group-commit is off the hot path, §11.6, so trigger cost is fine) but grants are the primary.
* **The sanctioned paths must survive** (prove in S3): limiterd's go_timeout booking (042), and the
  §12.1/§12.5 marker-replay via cold-start — the writer role must be held by the Limiter's writer
  process AND its cold-start path (same identity). The Sentinel is NOT a Postgres writer (marker file
  only), so it is untouched — confirm that, don't "fix" it.
* Cite **§9 / §12.10** in the change. **Freeze everything else:** no risk-gate seam, no mirror seam
  (I7), no change to the 042 go_timeout booking logic, no wiring of the other ten §9 event types
  (D3.434 — not this arc).

## S3 — BOTH DIRECTIONS, on the real cluster

**(a) a non-Limiter write is REFUSED, and no row lands.** Re-run S1's rogue writer against every
surface it reached; each is now rejected (permission denied / trigger reject), and a SELECT confirms
**no forged row exists**. Prove refusal on **every** surface S1 found open, not just the first.

**(b) the sanctioned path is UNBROKEN.** The Limiter's go_timeout booking still lands one row
(re-drive ARC 042's scenario end-to-end), the read-back matches, and the §12.1/§12.5 marker-replay via
cold-start still books retroactively. Enforcement that also blocks the legitimate writer is a
regression, not a fix — prove it did not.

**Non-vacuity:** the refusal proof must show the rogue write WOULD have succeeded absent enforcement
(it did in S1) and is now refused — a "refused" that was never actually attempted, or attempted
against an empty/wrong table, proves nothing. CANNOT-MEASURE over a false PASS.

## S4 — the gate (extend `check_plane1_sole_writer`, per rule 8)

A `check_plane1_sole_writer` gate already exists (its B.7 pylint precedent was cited in ARC 042) and
already declares the sole-writer property its subject — **extend it**, do not build a second (Part
C.9 / rule 8). Also fold in **D3.435**: ARC 042 found its producer census "could not see §9's sole
writer at all," and the repair handed three types a free green off a `*_drill.py` **filename-suffix**
match (D3.426's class). If this gate is that census, fix the suffix-match to a **shape** match here.

The gate must **prove real effective state, not a catalog proxy** (rule 2): it **attempts a rogue
`INSERT` as a non-writer identity and asserts it is refused** — reading `pg_catalog` grants alone is a
proxy that a trigger or a mis-scoped grant could pass while a real write still succeeds. Two arms:

* **STATIC/CONFIG** — the writer-role grant is exclusive (no non-writer role holds `INSERT`), derived
  from the live catalog, asserted as the invariant not a snapshot (rule 5).
* **LIVE** — spins a non-writer connection, attempts the INSERT, asserts refusal; then asserts the
  sanctioned writer still succeeds. Its scratch DB is cleaned at teardown (D3.437 discipline).

**Demonstrated FAIL, each exit 1 naming the site:**
* **PLANT A** — GRANT `INSERT` back to a non-writer role (038's exact "convention only" state): the
  rogue write succeeds ⇒ gate `fail`, exit 1, names the over-broad grant and shows the forged row.
* **PLANT B** — enforcement present but the sanctioned writer's grant dropped: the Limiter's own
  booking is refused ⇒ gate `fail`, exit 1 (enforcement that breaks the real writer is also a fail).
* Plants removed ⇒ `pass`, exit 0.

**Non-vacuity asserted (rule 4):** the LIVE arm must prove it actually attempted a write as a genuine
non-writer identity and that the table is the real Plane-1 table before "refused" counts as PASS.
Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the migration/DDL (grants ± trigger), the writer-role connection in whichever process
holds it (`plane1_sink.py` and/or `limiterd.py` — name it), the extended `check_plane1_sole_writer`
gate + its test, and `docs/CHECK-DEBT.md`. **Nothing** in the risk-gate seams, `picture.py`/mirror,
the 042 go_timeout booking, the WAL library internals, or unrelated. Explain or revert any wider path.

## CLOSE-OUT — INTERIOR tier

Full pytest + full census **DEFERRED to the greening slice.** If `limiterd.py` is touched the COMMIT
gate escalates to a full pass regardless (state it). Run: **(b)** the DERIVED reverse-dependency
closure (non-vacuity proven — contains the sole-writer gate's and the writer process's dependents,
RED-before/GREEN-after on this arc's own defect; cost-aware shell-out exclusions by detection);
**(c)** the extended gate BOUND from both real FAIL plants (exit 1, sites named); **(d)** CHECK-DEBT
reconciled — I8's discharge is an invariant flip, not a debt row, but note D3.435's fix and any
residual (e.g. role-migration-framework debt if the DDL surface was thin).

## RESIDUAL — explicitly NOT claimed

* **D3.434** — the ten unwired §9 event types. Its scheduling is the kickoff ruling above; either way
  it is NOT discharged here.
* **D3.436** (SIGKILL crash-gap between fire and booking) and **D3.437** (orphaned scratch DBs — the
  operator `dropdb` sweep) remain; the gate's own scratch DB must not add to D3.437.
* **D3.428** (the `_current`-advanced-on-publish-failure ruling) — awaits the architect, different
  seam.
* D3.430 / D3.431 / D3.432 / D3.433 — standing named debt, not this slice.

## BADGE VERDICT

**Limiter STAYS RED — but the clean set becomes `{I5, I6, I7, I8, I10} = 5/12`, open = 7**, if I8 is
discharged (both halves: a non-Limiter write refused on every open surface, the sanctioned path
proven unbroken, gated with a demonstrated FAIL). This is the first invariant flip since ARC 041.
Redraw the board on bank. Next depends on the D3.434 ruling and the remaining open invariants.

## POST-WRITE-BACK RE-MEASURE — predict, then measure at the derived tip

Default prediction **unchanged from 042's final** — extending `check_plane1_sole_writer` moves no
count (rule 8 / Part C.9): `verify.py` `90 | 3 | 2 | 0 | 1`, exit 1. Predict `passed+1` **only** if S4
genuinely creates a new gate file (it should not — the owner exists). The three standing fails
(`check_ibgateway_service`, `check_uncalled_entry_points`, `check_monitor_tui`) unchanged. Watch the
`guarded`/`cannot-measure` line for the arc-boundary exclusion re-point (owner 043 → the next arc),
the same maintenance 041/042 did — name it in advance, not as a surprise.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` (dogfood),
pulse+motion, ~5-min cadence holding inside any long op / the full-suite commit, STALL WARNING after
~15 min no motion, GIT WINS over prose. Verified watchdog teardown before the marker, matched by cc's
own signature, ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending the gate.
