# ARC 042 — ULTRAREVIEW: Limiter, slice 4 — wire the Plane-1 writer + book the GO-timeout row (D3.425)

**Tier: INTERIOR.** Limiter badge **STAYS RED**. Not the greening slice.
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `/home/bbt/nix/.venv/bin/python` →
`/usr/bin/python3.14` (3.14.4).
**Predecessor: ≈ `1abcfd0` (approximate — the 041-T final).** DERIVE the real tip yourself with
`git rev-parse HEAD` and freeze/diff against THAT, never the cited sha (the post-write-back
re-measure commits after the RESULTS HEAD; a diff against the stale sha misattributes 041-T's
write-back to this arc).
**Model: Opus 5** — this wires the money-truth plane (§9 sole writer) and proves durability across a
WAL→Postgres seam. Authority + durability reasoning, not a mechanical edit.

## Scope — writer wiring + D3.425 ONLY. I8 is 043, and the ordering is deliberate.

ARC 040 banked D3.425 with the note "blocked behind I8." **This slice inverts that on purpose:** you
cannot enforce a *sole writer* (I8) that does not yet write. So the writer gets wired first (here),
and **ARC 043 = I8** then proves no *other* process can write. Consequences:
* This slice **does NOT discharge an invariant.** It discharges CHECK-DEBT **D3.425** and lays the
  substrate I8 stands on. **The invariant count stays 4/12.** Say so plainly — do not let a clean
  slice read as an invariant flip.
* limiterd is the **designated** sole writer (§9/§12.10). Wiring IT to write is not creating a second
  writer — it is making the first and only intended writer function. The enforcement that *others*
  are refused is 043.

## The finding — D3.425

**§9** locks the persistence path: *append-only event log, **Limiter = sole writer**, Enqueue →
durable local WAL → shared-pool writer → group-commit to Postgres.* **§12.10** puts **GO-timeout on
Plane 1** (money-gating: ✅ Plane 1, — Plane 2) — "anything that changes or gates money ⇒ Plane-1
row." ARC 040 built the breaker (`_break_go_deadlocks`): it fires, releases the in-flight lock, and
writes to a **runtime record**. But that runtime record is **not §9's evidence plane**, and 040
found **limiterd enqueues no Plane-1 rows at all** — `projection.py` carries the event *name*, and
nothing books it. The row §9 mandates on every GO-timeout is unwritten.

**limiterd's contract boundary (be precise):** §9 makes limiterd responsible for the **enqueue to the
durable local WAL**. The **shared-pool writer** does the group-commit to Postgres downstream. So the
fix is *limiterd enqueues the GO-timeout event to the WAL via the existing sole-writer path*; the row
reaching Postgres is the end-to-end integration, proven separately.

## KICKOFF OBLIGATIONS (before Stage 1 — all mandatory)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive the clean/open invariant set from the tree (038
   register). State: clean `{I5, I6, I7, I10} = 4/12`, open = 8, and that **this slice discharges
   CHECK-DEBT D3.425, not an invariant — count stays 4/12.**
2. **Status via the new tooling (dogfood 041-T).** Kickoff → `scripts/arc_heartbeat.sh selfcheck`
   (prove the emitter before Stage 1). Every pulse/watchdog beat → `arc_heartbeat.sh pulse`; each
   transition → `arc_heartbeat.sh banner --name`. cc hand-formats no beat. Teardown line is EXACTLY
   the CLAUDE.md STATUS EMIT string, on its OWN line — the `[watchdogd]` mention must not share the
   teardown line (that was 041-T's own D-finding; `check_arc_status_contract` will audit this log).
3. **Ops pre-flight.** `df -i /tmp` (or run `checks/check_tmpfs_inode_headroom.py --mount /tmp` now
   that it exists) + clean stale `pytest-of-*` basetemps if no pytest runs.
   **COVERAGE REPORT — expect escalation this time.** `scripts/limiterd.py` is on the runtime gate's
   `uncovered` list (that is what made ARC 040 overrun 2.5×). This slice MUST touch `limiterd.py`, so
   **the commit gate WILL escalate to a full ~3252-test pass — that is unavoidable and is NOT the
   INTERIOR close-out** (the tier defers the close-out pytest, never the commit). State it in the
   kickoff banner and size the ETA to include it. **F6/F7 guard:** never launch a second commit until
   the first's gate process is confirmed dead BY PID (a bounded poll that returns is not proof it
   stopped — that is how 040 corrupted the testmon sqlite). Never `pkill -f`/`pgrep -af` on cc's own
   patterns; kill by captured PID.

## S1 — REPRODUCE D3.425 FIRST, on the live daemon, before a line changes

Bind to the real sites: limiterd's loop (the ARC-040 breaker `_break_go_deadlocks`), the real
sole-writer / WAL library, and the real Plane-1 event-log table. On a **running `limiterd`**:

* Register a strategy, admit a GO, abandon it, let the breaker fire (040's mechanism). Confirm the
  lock releases (that is 040's discharged behaviour — re-confirm, do not re-fix).
* **Prove NO Plane-1 GO-timeout row exists** for that firing: SELECT the event-log table and show the
  row is absent, while the runtime record shows the firing. The gap between "runtime record has it"
  and "Plane-1 does not" IS D3.425.
* **Non-vacuity of the absence:** prove the SELECT is against the real Plane-1 table and WOULD find a
  GO-timeout row if one were booked — insert a control row (different event type, or a hand-booked
  GO-timeout via the writer) and show the query surfaces it, then roll it back. An "absent" proven by
  a query that can never return anything is worth nothing.

## S2 — THE WIRING (limiterd → WAL, via the EXISTING sole-writer path)

On breaker fire, limiterd **enqueues a GO-timeout event to the durable local WAL through the writer
library that already exists** (the one ARC 037's loop used). Event fields per §9: timestamp,
`strategy_id`, `trade_id` (if one was minted), `reason=go_timeout`. Then:

* **Do NOT build a second writer.** Sole-writer is the whole point — if the existing writer API is
  not callable from the daemon (entangled with the 037 harness or the picture), **that is a finding**
  (the writer is not daemon-ready): report it, book only what is cleanly bookable, and name the rest
  as debt rather than widening this arc into a writer rewrite.
* **NO retry, NO auto-resend** (§4): one firing = one enqueue = one row. A re-tick that sees the lock
  already broken must not enqueue a second row — prove idempotence in S3.
* **Freeze everything else.** Nothing in the commit/publish mirror seam (I7, done), nothing in the
  sole-writer ENFORCEMENT seam (I8, 043), no other §9 event type wired here (see residual). If
  `projection.py` needs a minimal booking helper because it owns the event name, that is allowed and
  named; the WAL/writer library itself should be CALLED, not modified (if it must be modified, that
  is the not-daemon-ready finding).

## S3 — BOTH DIRECTIONS, real `limiterd` + real WAL + real Postgres

**(a) breaker fires ⇒ exactly one Plane-1 GO-timeout row, correct fields.**
* The event lands in the **durable local WAL** (limiterd's contract boundary) — prove it there
  first.
* End-to-end: with the shared-pool writer up, the row reaches **Postgres**; SELECT it back and match
  `strategy_id` / `trade_id` / `reason` / `ts` to the firing that produced it (not a leftover).
* **Idempotence:** the breaker firing plus any subsequent ticks produce **one** row, not N. Prove it.
* **Durability (§12.4):** show the enqueue survives a Postgres-unavailable window — WAL buffers, and
  the row is delivered when the writer drains — or, if that is out of reach in-slice, prove the WAL
  record exists pre-group-commit and name the outage-replay proof as owed to the Plane-1 module's own
  audit rather than claiming it.

**(b) breaker does NOT fire (healthy GO, normal feedback) ⇒ no GO-timeout row booked.** Drive a GO
resolved normally, watch past the resolution, and show zero GO-timeout rows in Plane-1. No spurious
bookings.

**Non-vacuity:** the read-back must prove it is reading the real Plane-1 table and that the row is the
one THIS firing produced — else CANNOT-MEASURE, never PASS.

## S4 — the gate (extend the existing Plane-1 owner, per rule 8)

**Find the existing owner first.** A gate that already owns "money-gating events are durably booked
to Plane-1" (an event-log / projection / Plane-1 completeness check) is the place these arms land —
`VERIFY-AND-CHECKS.md` Part C.9 / rule 8 forbid a second instrument over one property. **Extend it**
to assert: *a fired GO-timeout produces exactly one Plane-1 row with the §9 fields.* Only if NO gate
owns the property do you create `check_plane1_go_timeout` — and then predict +1 (see re-measure).

Two arms:
* **STATIC** — the breaker's fire path reaches a booking call to the sole-writer enqueue (structural,
  by shape, not by identifier spelling — the D3.426 lesson).
* **LIVE** — drive a real firing, assert the row lands with matching fields; drive a healthy GO,
  assert none.

**Demonstrated FAIL, each exit 1 naming the site:**
* **PLANT A** — the booking call removed / no-op'd (040's exact state): breaker fires, lock releases,
  **no Plane-1 row**. Gate `fail`, exit 1, names limiterd's fire path and reports the runtime-record/
  Plane-1 gap.
* **PLANT B** — a duplicate enqueue on re-tick: gate `fail`, exit 1, reports N rows for one firing.
* Plants removed ⇒ `pass`, exit 0.

**Non-vacuity asserted (rule 4):** the LIVE arm must REQUIRE that a breaker firing actually occurred
and the SELECT scope is the real table before "row present" counts as PASS or "row absent" as FAIL.
Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert it

`git diff --stat <derived tip>` shows only: `scripts/limiterd.py` (the enqueue on fire), a minimal
booking helper if `projection.py` owns the event name, the extended Plane-1 gate + its test, and
`docs/CHECK-DEBT.md`. **Nothing** in `picture.py`, the mirror seam, the I8 enforcement seam, the
WAL/writer library, or unrelated. Explain or revert any wider path.

## CLOSE-OUT — INTERIOR tier, with the commit-escalation stated

Full ~3400-test pytest and the full binding census **DEFERRED to the greening slice**. BUT: because
`limiterd.py` is uncovered, **the COMMIT gate escalates to a full pass — that runs regardless of
tier** (the tier defers the close-out suite, not the commit). Run:
* **(b) DERIVED reverse-dependency closure** of the changed files — prove non-vacuity (it contains
  limiterd's and the gate's direct dependents; RED-before / GREEN-after). Cost-aware exclusion by
  detection of any test that shells out to verify.py/census/full-suite.
* **(c)** the extended gate BOUND from its observed real FAIL (both plants, exit 1, sites named).
* **(d)** CHECK-DEBT: **D3.425 DISCHARGED** with the ruling written; open/name residuals (below).

## RESIDUAL — explicitly NOT claimed

* **The broader Plane-1 booking gap.** If S1 confirms limiterd books NO §9 event types, then the
  other money-gating rows (accepted / denied / filled / closed / reservation / cancel / HALT /
  operator-action / strategy-lifecycle / cold-start) are ALSO unwritten by the daemon. This slice
  wires **only GO-timeout**. Name the rest as debt (a new D3.4xx) belonging to the Plane-1 module's
  own ULTRAREVIEW or a dedicated build slice — do NOT silently widen 042 into wiring the whole
  event surface.
* **I8 (sole-writer ENFORCEMENT) = ARC 043** — now has a writer to enforce.
* **D3.428** (the `_current`-advanced-on-publish-failure ruling) — awaits the architect; different
  seam, untouched here.
* D3.430 (byte-headroom arm), D3.431 (`check_monitor_tui` out-of-tree), D3.432 (plan-vs-declaration
  drift), D3.433 (status-gate duty cycle) — standing named debt, not this slice.

## BADGE VERDICT

**Limiter STAYS RED.** D3.425 discharged; the Plane-1 writer substrate wired. **Invariant count
unchanged at 4/12.** Next: **ARC 043 = I8 (sole-writer enforcement)** — prove no non-Limiter process
can write Plane-1, which this slice's writer now makes meaningful to enforce.

## POST-WRITE-BACK RE-MEASURE — predict, then measure at the derived tip

Default prediction **unchanged from 041-T's final** — extending an existing Plane-1 gate moves NO
count (rule 8 / Part C.9): `verify.py` `90 | 3 | 2 | 0 | 1`, exit 1. Predict `passed+1` **only** if
S4 genuinely creates a new gate file because no existing gate owns the property — state which, before
the run. The three standing fails (`check_ibgateway_service`, `check_uncalled_entry_points`,
`check_monitor_tui`) unchanged; the wiring adds a call site so no new uncalled entry point.

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` (dogfood),
pulse+motion, ~5-min cadence holding inside the full-suite commit, STALL WARNING after ~15 min no
motion, GIT WINS over prose. Verified watchdog teardown before the marker, matched by cc's own
signature, ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending the gate.
