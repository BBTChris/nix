# ARC 041 — ULTRAREVIEW: Limiter, slice 3 of many — commit-before-validate torn state (I7)

**Tier: INTERIOR.** The Limiter badge **STAYS RED**. This is not the greening slice.
**Canonical path: `/home/bbt/nix`** (absolute — never relocate).
**Predecessor: ARC 040, HEAD `a70a2c4`.**
Interpreter for every measurement: `/home/bbt/nix/.venv/bin/python` → `/usr/bin/python3.14`
(Python 3.14.4).
**Model: Opus 5** (torn-state / atomicity reasoning + adversarial gate design — this is an
authority-boundary invariant, not a mechanical edit).

**Scope note — I7 ONLY.** I8 (sole-writer enforcement) and the D3.425 Plane-1 `go_timeout` row it
unblocks are a DIFFERENT seam (durable WAL, not the in-memory mirror) and are **ARC 042**. This arc
does not touch `limiterd`'s Plane-1 writer, `projection.py`, or the WAL. If the fix appears to
require the Plane-1 seam, STOP and report — that is the signal the split was wrong, not a licence to
widen the arc.

---

## The invariant

**I7 — the in-memory canonical picture must never hold, nor publish, a state its own validation
would reject.** ARC 038 pass 1 found `commit()` stored `_current` **before** `publish()` validated:
a window exists in which the Limiter's canonical in-memory state (`_current`, the thing snapshots
and reads are served from) holds a state that the writer's own publish path would refuse to emit. A
consumer reading `_current` — or a **snapshot-on-subscribe** landing in that window — receives a
picture the writer itself considers invalid.

**Spec anchors (cite these in the fix, verbatim line refs from the tree):**
* **§3 ATOMICITY RULE** — "balance and the position table publish together as one snapshot … so the
  Allocator can never compute headroom off a stale balance + fresh commitment … **every consumer
  reads a self-consistent picture**."
* **§12.7** — mirror model; a consumer "**never sizes on a half-built mirror** (mirror incomplete ⇒
  treated as stale ⇒ fast-drop/deny)"; raw torn state would reduce "the single-writer principle to
  fiction."
* **§9 / architecture table** — Limiter is **sole writer of canonical position state**; **two-phase
  gate**; single-threaded event loop + sender thread.

The invariant has TWO halves, and both are load-bearing:
1. **`_current` never advances to a state that fails validation.** Validation gates the promotion,
   not the reverse.
2. **What `publish()` emits equals what `commit()` promoted** — no divergence, no double-advance, no
   emit of a state `_current` does not hold. Balance and table move as one (§3).

---

## KICKOFF OBLIGATIONS (before Stage 1 — all mandatory, per the Status Contract)

1. **Tier + count declaration.** Echo: `TIER = INTERIOR`. Then **derive the authoritative
   open-invariant count from the tree** (the ARC 038 invariant register — read it from the actual
   test/SESSION artifact that pins I1–I12, e.g. `scripts/tests/test_arc038_*`; do NOT trust a prose
   number). State: clean set, open set, and this slice's target (I7). **Reconcile the ARC 040
   RESULTS "eleven invariants remain" line against the tree and record the corrected count in
   SESSION.md** — 040 wrote a number that does not match `clean={I5,I6,I10}`. This is a
   don't-anchor-to-a-moving-value fix, not a footnote.
2. **Self-verifying heartbeat watchdog.** Start it, then **prove it emitted ≥1 heartbeat** (read its
   output back) before Stage 1. Match it later by its OWN signature (its `watchdog.py` path / the
   arc-stamped pid it self-reports) — **NOT** a bare `pgrep watchdog` (that matches the kernel
   thread `[watchdogd]`, pid ~165, root-owned, always present, not yours — do not kill it, do not
   treat it as a leak).
3. **Ops pre-flight.**
   * `df -i /tmp` — confirm inode headroom; clean stale `pytest-of-*/` basetemps if no pytest is
     running (039R died with 16 GB free but 0 inodes).
   * **Coverage-of-touched-files report (NEW, from 040's overrun).** Before any edit, list the files
     this slice will touch and check each against the runtime commit gate's `uncovered` list. **State
     in the kickoff banner whether the commit will select real tests or ESCALATE to a full pass**, so
     the run-time estimate is honest. `picture.py`-class core logic is expected covered (unlike
     `limiterd.py` in 040); if any touched file is uncovered, say so and expect the full-suite commit
     cost.
   * **F6/F7 double-commit guard.** If a commit's runtime gate escalates, **do not launch a second
     commit until the first's gate process is confirmed dead BY PID** (from its own process tree) —
     a bounded poll that *returns* is not evidence the thing it polled has *stopped* (that is how
     040 corrupted the testmon sqlite with two concurrent writers). Never `pkill -f` / `pgrep -af` on
     cc's own patterns; kill by captured PID only.

---

## S1 — REPRODUCE THE TORN WINDOW FIRST, on the live loop, before a line changes

Bind to the **real** `commit()`/`publish()`/`_current` in the Limiter picture module (expected
`scripts/nixrisk/picture.py` — confirm the real path and cite real line numbers). Reproduce 038's
exact finding against a **running process / real loop**, not a mental walkthrough:

* Stand up the real canonical picture inside the real event loop.
* Drive a `commit()` whose subsequent `publish()` validation **FAILS** (construct the exact
  validation-failing condition the code checks — an incomplete/incoherent snapshot: e.g. balance
  advanced but the position table not, or a version-stamp mismatch, whatever `publish()` actually
  asserts). If publish today asserts *nothing* meaningful, that absence IS the finding — record it.
* **Prove a reader observes `_current` in the rejected interim state** — subscribe / snapshot-on-
  subscribe / direct `_current` read in the window, and show the observed picture is one `publish()`
  itself refuses. Print the torn read next to the validation verdict, samples first, verdict after
  (the 040 S3a lesson: a verdict that contradicts the samples above it is a parse bug — use bounded
  parsing).

**Non-vacuity of the reproduction:** prove the validation path is genuinely reachable and genuinely
rejects — a reproduction that never triggers a rejecting publish has proven nothing.

---

## S2 — THE IMPLEMENTATION

Reorder so **validation gates promotion**. The minimal, spec-faithful shape:

* **Validate the candidate snapshot BEFORE `_current` advances.** Either validate-then-promote, or
  stage → validate → atomically promote. `_current` only ever moves to a state that passed
  validation. On failure: `_current` is **unchanged** (old valid state retained), the operation is
  denied/rolled back with the reason named, and **nothing is published**.
* **Publish emits exactly the promoted `_current`** — same version stamp, balance + table as one
  snapshot (§3). No path emits a state `_current` does not hold; no double-advance.
* **Atomicity is part of the fix, not a separate one:** a reader can never catch balance advanced
  with the table not, or vice versa. If the current structure allows a two-step publish, close it.
* **Freeze everything else.** No new writer. No Plane-1 / WAL / `projection.py` touch (that is I8 /
  042). No change to any other invariant's logic. `git diff --stat a70a2c4` outside the picture
  module + the new gate + its test must be empty of unrelated logic.
* **Any new helper ships with its call site.** The recurring Limiter defect is built-but-uncalled
  (I5 was a knob read by nothing). A staging/promote helper with no caller is the same defect in a
  new spot — `check_uncalled_entry_points` must not gain a row.
* **NO retry, NO auto-resend** anywhere on this path (§4) — a failed publish is denied, not
  re-attempted.

---

## S3 — PROVEN IN BOTH DIRECTIONS, on real processes

**(a) Validation-failing commit ⇒ no advance, no torn read.** Same scenario as S1 after the fix:
`_current` does **not** move, the old valid state is retained and readable, the operation is denied
with its reason, and **no subscriber ever observes the rejected state** across the whole window
(sample continuously through it, not once). Print `_current` before == after.

**(b) Valid commit ⇒ advance exactly once, published == committed, atomic.** A well-formed commit
promotes `_current` once, and the published snapshot **equals** `_current` field-for-field with one
version stamp; balance and table are observed to move together (no sample catches a half-advanced
picture). Then **watch past the operation** to prove no delayed second emit / no drift — the §0a
trap (stopping at success proves only "not diverged *yet*").

**Non-vacuity:** direction (a) is only meaningful if a rejecting publish actually fired; assert it
did. A run that watched only well-formed commits returns CANNOT_MEASURE for (a), never PASS.

---

## S4 — `checks/check_commit_publish_atomicity.py`, demonstrated FAIL in BOTH arms

Two arms, because neither alone is the check:

* **STATIC arm** — AST proof that in the real `commit()`/`publish()` path, **validation dominates
  the `_current` store** (the validating call is on every path that reaches the promotion, and the
  promotion is not reachable without it). Not a substring/spelling match — 040's D3.426 was a gate
  that matched an identifier's *spelling* and passed a vacuous plant. Assert the ordering as a
  structural property of the AST, derived from the tree.
* **LIVE arm** — drive a real picture: force a validation-failing commit and assert (i) `_current`
  unchanged, (ii) no reader observes the rejected state, then a well-formed commit and assert
  published == committed and atomic.

**Demonstrated FAIL, both plants, each naming the site:**
* **PLANT A** — reorder to store `_current` before validating (038's exact defect). Gate must
  `fail`, **exit 1**, name the picture module and report the observed torn read.
* **PLANT B** — make `publish()` emit a state `_current` does not hold (divergence / double-advance),
  or split the balance+table publish so a torn read is observable. Gate must `fail`, **exit 1**, name
  the site and report the divergence/torn read.
* **Plants removed** ⇒ `pass`, **exit 0**.

**Non-vacuity asserted, not assumed (rule 4 / §17):** the LIVE arm must REQUIRE that a rejecting
publish actually fired and that a reader actually sampled the window before any "no torn read" may
count as PASS — else CANNOT_MEASURE (exit 2), never PASS. Prove the gate's scope contains its subject
before the plant.

**The gate's own escape (debug.md Tier-2 Stage 2):** can this gate be made to pass by editing
something it also reads? If the static arm reads the same symbol the fix defines, a rename defeats it
— derive the anchor, don't write it down. Record the answer in the arc log.

**Exit-code contract:** 0 PASS / 1 FAIL / 2 CANNOT-MEASURE; no uncaught subprocess exception may
collapse to 1; fail closed and loud.

---

## FREEZE — assert it

`git diff --stat a70a2c4` shows **only**: the picture module (the reorder), `checks/check_commit_
publish_atomicity.py` (new), and the one test file that pins I7. Any test file that necessarily
changed because the fix invalidated it is named with why. Nothing in `limiterd.py`, `projection.py`,
`loop.py`, `recovery.py`, or the WAL. If the diff is wider, explain every extra path or revert it.

---

## CLOSE-OUT — INTERIOR tier (a STATED decision, not a silent skip)

**Full ~3400-test pytest and the full binding census are DEFERRED to the Limiter's greening slice.**
Run instead:

* **(b) DERIVED reverse-dependency closure** — grep importers of the changed files; run that closure.
  **Prove non-vacuity before trusting green:** the closure must contain the direct dependents of the
  picture module (name them) and they must be RED-before / GREEN-after the fix. **COST-AWARE
  EXCLUSIONS, named by detection not guess:** scan the closure for any test that itself shells out to
  `verify.py` / the binding census / the full suite (the 039R `test_end_to_end` trap, the 040
  `test_check_*` traps) and EXCLUDE or explicitly time-box it — a "cheap" closure hiding a
  whole-suite-equivalent has re-inherited the cost the tier exists to avoid.
* **(c)** `check_commit_publish_atomicity` is **BOUND from its observed real FAIL** — two planted
  defects, each exit 1 with the site named, not a constructed exit code.
* **(d)** CHECK-DEBT reconciled: discharge what this slice closes, name residuals, open new debt
  explicitly (do not absorb).

---

## RESIDUAL — explicitly NOT claimed as done

* **I8 (sole-writer enforcement) and D3.425 (the `go_timeout` Plane-1 row) remain open** — ARC 042.
  This slice does not touch the durable-write seam.
* If S1 finds `publish()` validates **nothing** meaningful today (so the "torn window" is really
  "there is no validation to be before or after"), that is a LARGER finding than a reorder — record
  it, discharge what is in scope (establish real validation + correct ordering), and name any part
  that must bank to a later slice rather than silently widening this one.

---

## BADGE VERDICT

**If I7 discharged:** clean set becomes **{I5, I6, I10, I7} = 4/12**, open = 8. **Badge STAYS RED.**
Next: **ARC 042 = I8 (sole-writer enforcement) + D3.425 (Plane-1 `go_timeout` row).**

---

## POST-WRITE-BACK RE-MEASURE — state the prediction BEFORE the run

The D3.40/D3.144 guard-owner transition fires when SESSION.md names the arc complete, so re-measure
is ORDERED after write-back. Predict, then measure at the new HEAD:

| term | predicted |
|---|---|
| verify.py | `90 \| 2 \| 2 \| 0 \| 1`, exit 1 — the new gate is the 90th check, `[ok]`; 89→90 passed is the whole delta |
| the two FAILs | the standing pair only (`check_ibgateway_service` tap + `check_uncalled_entry_points`) — no new uncalled entry point from this slice |
| new entry points | any staging/promote helper has a shipped call site ⇒ 0 occurrences in the uncalled run |

A one-invariant slice should move `passed` by exactly one and nothing else. If more moved, find out
why before banking.

---

## STANDARD ARC OBLIGATIONS (unchanged)

* Append the arc summary to `~/nix/sessions/SESSION.md`; **overwrite** (not append)
  `~/nix/downloads/RESULTS.md` with THIS arc's results; `cat` both as the last action and paste
  their state into the response before declaring `**** ARC completed ****`.
* Stage banners (echo fixed total stage count once at kickoff; boxed banner per stage; PAUSED tag on
  any stop). Heartbeats: overall-arc %, pulse + motion (git HEAD / stage / op-% advancing), ~5-min
  cadence that HOLDS inside any single long operation, STALL WARNING after ~15 min no motion,
  live-derived (GIT WINS over prose).
* **Verified teardown:** tear the heartbeat watchdog down at close-out BEFORE the marker and PROVE
  it died — matched by cc's OWN watchdog signature, ignoring the kernel `[watchdogd]`.
* Build/extend gates per `VERIFY-AND-CHECKS.md` (read it directly, not a paraphrase).
