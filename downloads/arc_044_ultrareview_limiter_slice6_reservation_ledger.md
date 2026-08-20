# ARC 044 — ULTRAREVIEW: Limiter, slice 6 — I2 reservation ledger: exactly one terminal release

**Tier: INTERIOR.** Limiter badge **STAYS RED** (invariants remain open after it).
**This slice DISCHARGES AN INVARIANT: I2 → clean set becomes 6/12.**
**Canonical path `/home/bbt/nix`** (absolute). Interpreter `/home/bbt/nix/.venv/bin/python` →
`/usr/bin/python3.14` (3.14.4).
**Predecessor: ≈ `b7476a6` (approximate — ARC 043's measurement tip).** DERIVE the real tip with
`git rev-parse HEAD` and freeze/diff against THAT, never the cited sha (043's cited `382cbd4` was
really `2417e2a`; the post-write-back re-measure commits after the RESULTS HEAD).
**Model: Opus 5** — this is an ABSENCE proof (no leak path exists across *every* terminal and failure
path) plus race reasoning (partial-fill cancel, timeout-vs-feedback, blackout-during-pending). Not a
mechanical edit.

## The invariant — I2

**§14 locks it: "Every reservation reaches exactly one terminal release."** §3: `committed = Σ open
margin + Σ PENDING RESERVATIONS`, released on fill / cancel / reject / pending-timeout / blackout-
onset — *"No leak paths."* §15 C1 records this closed a **double-spend race**. V23 is the standing
objective: *every reservation reaches exactly one terminal release across all failure paths.*

**"Exactly one" is two-sided — both halves load-bearing:**
1. **AT LEAST ONE (no leak).** A reservation not released on some terminal path permanently inflates
   `Σ reservations` ⇒ `committed` never falls ⇒ deployable liquidity shrinks monotonically ⇒ the
   system slowly denies all entries. A strangle bug that looks like "the market just isn't giving
   signals."
2. **AT MOST ONE (no double-release).** A reservation released twice (e.g. pending-timeout fires
   *and then* terminal feedback arrives) under-counts `committed` ⇒ the gate approves against
   headroom that is already spent ⇒ cap breach. This is the double-spend race C1 named.

## KICKOFF OBLIGATIONS (before Stage 1 — all mandatory)

1. **Tier + count.** Echo `TIER = INTERIOR`. Derive clean/open from the 038 register: clean
   `{I5, I6, I7, I8, I10} = 5/12`, open = 7; **this slice targets I2 → 6/12 if discharged.** Read
   I2's actual 038 charter text and bind S1 to the specific defect it names — do not assume the
   defect from this brief; the brief's framing is the property, the register holds the finding (I7
   turned out half-already-fixed; I2 may too).
2. **Status via the tooling (dogfood).** kickoff → `scripts/arc_heartbeat.sh selfcheck` (and make the
   self-verify line land in the *tee'd log*, not just the terminal — 043's re-measure caught the
   selfcheck emitting before tee began; start tee first). pulses → `pulse`; transitions → `banner`.
   Teardown line exact, on its own line, no `[watchdogd]` on it. Write the teardown + marker into the
   run's own log *before* the final verify measurement (043's ordering fix) so
   `check_arc_status_contract` can read this arc's log at re-measure, with the marker still the last
   token printed to the operator.
3. **Ops pre-flight.** `checks/check_tmpfs_inode_headroom.py --mount /tmp` + clean stale basetemps.
   Coverage report: name which module owns the reservation ledger (`Σ reservations` / the release
   sites — expected a `nixrisk` aggregates/picture module, NOT `limiterd.py`) and whether the touched
   files are on the `uncovered` list. If `limiterd.py` is untouched the commit takes the incremental
   path (state it). Clean this arc's scratch DBs at teardown (D3.437 — do not add orphans). F6/F7:
   no second commit until the first's gate process is dead BY PID; never `pkill -f` on cc's own
   patterns.

## S1 — REPRODUCE FIRST, and ENUMERATE the terminal paths from the code, not from memory

Bind to the real reservation ledger. First **derive the complete set of terminal paths from the
tree** — every code site where a reservation ends its life — rather than trusting any list (this
brief's included). The known families, as a checklist to VERIFY the derivation against, not to
substitute for it:
* full fill (reservation → open margin);
* **partial fill** (the unfilled remainder's reservation released the instant reality comes in under
  it — § partial-fill v1.3);
* cancel; reject; pending-timeout resolution; blackout-onset cancellation;
* **recovery/quarantine flatten** (strategy death → positions closed, reservations released — §
  strategy lifecycle).

Then, on a live limiter:
* Drive each derived terminal path and record whether the reservation releases **exactly once** —
  `Σ reservations` and `committed` return to their pre-reservation values, once.
* **Find the defect I2's charter names** — a path that leaks (never releases), a race that
  double-releases, or the absence of any gate proving exhaustiveness. Reproduce it against the live
  ledger before touching code. If the charter's defect is already fixed (the I7 precedent), say so
  and re-target to the open half.
* **Non-vacuity:** prove a reservation was actually TAKEN (committed rose by the proposed margin)
  before any "released" is meaningful — a release measured against a reservation that never existed
  proves nothing.

## S2 — THE FIX

Guarantee **exactly one** terminal release per reservation:
* **No leak:** every terminal path releases. If a path is missing its release, add it.
* **No double-release:** a reservation carries terminal-state identity such that the *first* terminal
  event releases and any later one is a recorded no-op — **released-exactly-once, not
  released-again**. Prove the race cannot double-count (the timeout-vs-feedback and partial-fill
  cancel races specifically).
* Cite **§14 / §3 / §15 C1**. **NO retry, NO auto-resend** (§4). **Freeze everything else** — nothing
  in the sole-writer seam (I8, done), the mirror seam (I7), the go_timeout booking (042), or
  unrelated. Any new helper ships with its call site (no built-but-uncalled — the recurring trap).

## S3 — BOTH DIRECTIONS, with the exhaustive-path enumeration proven complete

**(a) EXHAUSTIVE single-release.** Drive **every** derived terminal path and prove each releases
exactly once — `committed` returns to baseline, `Σ reservations` to zero, no leak, on every path.
**The enumeration's completeness is itself the proof obligation** (rule 4 non-vacuity): assert the
set of paths driven equals the set of terminal-transition sites in the code — a future terminal path
added without a release is the exact defect this invariant exists to forbid, so the proof must be
over the derived set, not a fixed list.

**(b) NO double-release under race.** Drive the races on real processes: partial-fill remainder
filling after the cancel; pending-timeout firing then terminal feedback arriving; blackout-onset
during a pending order. Prove **exactly one** release each — `committed` never under-counts, no cap
breach. Watch past the race window (the §0a trap: one release now doesn't prove not-two-later).

**Non-vacuity:** every direction asserts a real reservation was taken and the ledger really moved
before the release verdict is trusted.

## S4 — the gate (extend the existing owner; make it an ABSENCE proof, not a path list)

V23 names a reservation-leak property test — **find its owner** (a `check_reservation*` /
property-test gate) and **extend it** (rule 8 / Part C.9), do not build a second. The gate's core
obligation, and the thing that makes it non-vacuous:

* **It enumerates terminal paths BY DERIVATION from the code (by shape — a reservation transitioning
  to a terminal state), not by a hand-list.** A gate that checks only the paths someone listed is
  blind to the next path that forgets to release — which is exactly I2's failure mode. If a true
  shape-derivation isn't achievable (the D3.440 lesson — a drill and a daemon look alike), use an
  explicit enumeration WITH a liveness arm that goes CANNOT_MEASURE if a terminal-transition site
  exists that the enumeration doesn't name — so a new leak path is caught as "unmeasured," never
  silently passed.
* Drive each path live; assert exactly-one-release; assert the ledger returns to baseline.

**Demonstrated FAIL, each exit 1 naming the site:**
* **PLANT A (leak)** — disable release on one terminal path: `Σ reservations` never returns to
  baseline ⇒ gate `fail`, exit 1, names the leaking path and shows committed inflated.
* **PLANT B (double-release)** — release twice on one path: `committed` under-counts ⇒ gate `fail`,
  exit 1, names the double-release.
* **PLANT C (new unmeasured path)** — add a terminal-transition site the enumeration doesn't name:
  gate `CANNOT_MEASURE` (exit 2) naming the unnamed site, NEVER PASS — the enumeration-completeness
  arm proving it is not blind.
* Plants removed ⇒ `pass`, exit 0.

**Non-vacuity asserted (rule 4):** the gate proves it actually took a reservation and drove a real
terminal path before any verdict. Exit 0/1/2; no uncaught exception collapses to 1; fail closed.

## FREEZE — assert against the derived tip

Diff shows only: the reservation-ledger module (the release fix), the extended reservation gate + its
test, and `docs/CHECK-DEBT.md`. **Nothing** in the sole-writer seam, `picture.py`/mirror (unless the
ledger *is* in the picture module — then name the exact functions and keep the change to the
release logic), the 042 booking, or unrelated. Explain or revert any wider path.

## CLOSE-OUT — INTERIOR tier

Full pytest + full census **DEFERRED to greening.** Run: **(b)** DERIVED reverse-dependency closure
(non-vacuity proven — contains the ledger module's dependents and the reservation gate's test,
RED-before/GREEN-after on this arc's own defect; cost-aware shell-out exclusions by detection);
**(c)** the extended gate BOUND from all three real FAIL plants (A/B exit 1, C exit 2, sites named);
**(d)** CHECK-DEBT reconciled — **write the ARC-TOTAL series row** (043's re-measure missed because
the close-out skipped it; `check_derived_claims` caught it — do not repeat that). I2's discharge is
an invariant flip, not a debt row; name any residual.

## RESIDUAL — explicitly NOT claimed

* Any reservation concern outside the exactly-one-release property (e.g. the *value* of a reservation
  vs actual margin — a §6.4 margin-transport concern) is not I2 and is not touched.
* **D3.428** (the `_current`-advanced-on-publish-failure ruling) — awaits the architect, different
  seam. **D3.434** (ten unwired §9 events) — Plane-1-module debt, ruled non-greening-blocking in 043.
  **D3.438 / D3.439** (OS-user impersonation; latent WAL surface) — deferred, Plane-1/provisioning.
  D3.430 / D3.431 / D3.432 / D3.433 / D3.440 — standing named debt, not this slice.

## BADGE VERDICT

**Limiter STAYS RED — clean set becomes `{I5, I6, I7, I8, I2, I10} = 6/12`, open = 6**, if I2 is
discharged (exhaustive single-release proven across every derived terminal path, no double-release
under race, gated with a demonstrated FAIL incl. the enumeration-completeness arm). **Redraw the
board on bank.** Remaining open: I1 (instrument the daemon — capstone), I3, I4, I9, I11, I12.

## POST-WRITE-BACK RE-MEASURE — predict, then measure at the derived tip

Default prediction **unchanged from 043's final** — extending the existing reservation gate moves no
count (rule 8 / Part C.9): `verify.py` `90 | 3 | 2 | 0 | 1`, exit 1. Predict `passed+1` **only** if S4
genuinely creates a new gate file (it should not). Three standing fails unchanged. Name the
arc-boundary exclusion re-point (044 → next arc) in advance, and **write the ARC series row in the
close-out** so `check_derived_claims` does not fire on a skipped ledger-arithmetic row (043's miss).

## STANDARD OBLIGATIONS

Append summary to `~/nix/sessions/SESSION.md`; **overwrite** `~/nix/downloads/RESULTS.md`; `cat` both
last and paste their state before `**** ARC completed ****`. Status via `arc_heartbeat.sh` (dogfood),
pulse+motion, ~5-min cadence holding inside any long op, STALL WARNING after ~15 min no motion, GIT
WINS over prose. Verified watchdog teardown before the marker, matched by cc's own signature,
ignoring `[watchdogd]`. Read `VERIFY-AND-CHECKS.md` directly when extending the gate.
