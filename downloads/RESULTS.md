# ARC 057 RESULTS — I1 ARC C2: §14's four uncertainty flatten producers

**TIER = INTERIOR.** Limiter badge **STAYS RED**. Count **STAYS 11/12** (open: I1). This arc does
**NOT** discharge I1 — only **ARC D** (flatten completions + the convergence gate) remains.
Discharges **D3.453 · D3.372 (flatten half) · D3.469 · D3.475**. Opens **D3.478 · D3.479 · D3.480 · D3.481**.

**Predecessor DERIVED, not assumed:** the brief said `≈ eb2e853`; `git rev-parse HEAD` = **`5757f35`**
(eb2e853 is ARC 056's CODE commit, 5757f35 its post-write-back re-measure on top). Everything below is
frozen and diffed against **5757f35**.

---

## THE HEADLINE

**D3.442's protective-flatten path is now FULLY WIRED.** ARC 055 (C1) gave the daemon the STOP
protective exit — a breached synthetic stop fires one flatten. This arc gives it the other half of
§14's sentence: the four conditions under which this process holds, or the venue holds, a position it
**cannot protect or cannot account for**, each firing ONE `ProtectiveFlatten` with
`reason = uncertainty` through C1's already-proven send machinery.

All four detectors already existed. **Not one had a producer.** Measured on a live `limiterd` at S1,
before a line of this arc was written — every one of them ended in the same reading, `flattened = []`:

| condition | debt | the position, S1, BEFORE | S3, AFTER |
|---|---|---|---|
| stale open position | D3.453 | OPEN §3 row, feed silent 3.0s against a 2.0s threshold, untouched | ONE flatten, `trigger=stale_price`, `2049ms old against 2000ms` |
| not-tradable fill | D3.372 | `write_refusals=1`, `positions=[]`, `writes=0` — §3 reads FLAT over a real venue position | ONE flatten of `MNQU6`, `trigger=uncertainty` |
| undetailed poll fill | D3.469 | venue says `filled`, HELD across 62 queries, reservation committed forever | HOLD for a bounded window, then ONE flatten |
| un-armable fill, venue half | D3.475 | `arm_refusals=1`, capital returned (056's half), `stops=[]`, no flatten | ONE flatten naming the order |

Every "AFTER" carries `executed=[True]`, `reason=uncertainty`, and a `sent_on_native_id` equal to
§5:323's sender thread and **not** the loop's.

---

## WHAT WAS BUILT, AND WHAT WAS NOT TOUCHED

`scripts/limiterd.py` gains four objects and nothing else changes shape:

* **`UncertaintyCondition`** — the CLOSED, DERIVED set of §14's four conditions. The gate reads this
  enum by AST; it holds no copy of its own.
* **`UncertaintyWatch`** — DETECTS and ENQUEUES. Holds no broker, no executor, no Plane-1 sink and no
  clock, so *this object cannot send* is a property of the TYPE. Its only per-tick half is the
  stale-open scan, bounded by §15's `O(positions ≤ 5)/tick`; the other three are event-driven at the
  sites that already observe them.
* **`UncertaintyDriver`** — FIRES, on §5:323's sender thread. Holds the **SAME** `ProtectiveFlatten`
  §3:173's onset sweep and C1's stop exit already share, so §4's dual-authority arbiter keeps reading
  and writing **ONE** `_closed` book.
* **`ProtectiveSenders`** — `LimiterLoop.attach` takes one `sender_send` and there are now two
  producers behind it. Routed by PAYLOAD TYPE, never by a flag: each driver's `send` returns
  immediately on a payload that is not its own frozen dataclass.

**C1 IS CALLED, NOT CHANGED — asserted with `git hash-object` against `5757f35`, not claimed.**
`stopwatch.py` · `flatten.py` · `fills.py` · `stops.py` · `seam.py` · `freshness.py` · `outcomes.py` ·
`reservations.py` · `positions.py` · `picture.py` · `completions.py` · `loop.py` · `execution.py` ·
`join.py` · `calendar_seam.py` · `wal.py` — **all sixteen BYTE-IDENTICAL.** The freeze list expected
the detection seams to appear in the diff; they do not, because the producers read them and change
none of them.

**The diff is four files:** `scripts/limiterd.py`, `risks/limiter.config.json` (one new knob + its
`_derivations` entry), `checks/registry.json` (one line), `docs/CHECK-DEBT.md` — plus two new files,
`checks/check_uncertainty_flatten.py` and `scripts/tests/test_check_uncertainty_flatten.py`.

---

## THE THREE RULINGS THIS ARC MADE, EACH STATED RATHER THAN SLIPPED IN

**1 — D3.469 HOLDS FIRST. It does not flatten on detection.** A `filled` status answer whose
execution report has not arrived is overwhelmingly the *delayed-but-valid* case: §2A's `on_fill` is a
push, pushes arrive late, and §12.4's reconnect makes a re-delivery expected. Flattening on the status
answer kills a healthy position — not a safe direction, a **different failure**. So the answer is a
bounded hold: `exec_report_reconcile_ms` (a DECLARED NIX ADDITION with its own `_derivations` entry —
§12A's `PENDING_ACK_TIMEOUT_MS` bounds an un-acked order and `FILL_TIMEOUT` a working one, and
neither is this quantity, which starts *after* the venue said `filled`). **Both branches measured**:
the real exec report inside the window CONVERTS and no flatten fires across 8s past the deadline; the
deadline expiring first fires exactly one. PLANT B proves the ordering is gated.

**2 — A FEED NEVER OBSERVED IS NOT FLATTENED, and the narrowing is PUBLISHED.**
`FreshnessTracker.reading` answers `CacheState.EMPTY` with `blocked=True` for a key nothing has ever
been seen on — §17's stale-until-proven-fresh, and the right answer for a GATE deciding whether to
admit new capital. It is the **wrong** trigger for a flatten in THIS build: D3.473 records that this
daemon has no capture feed at all, so EMPTY is every symbol's state in a build with nothing
publishing, and firing on it would flatten every position in the tree on the ground that the feed
nobody wired is not sending. That is the absence of a feed reported as a position hazard. So the
producer fires on STALE — observed, then quiet — and every EMPTY open symbol is NAMED in
`status.uncertainty.unpriced_positions`. **CHECK-DEBT D3.478 owns the other half.**

**3 — D3.372's SYMPTOM IS CLOSED; ITS ROOT IS SEPARATED, NOT CLOSED WITH IT.** The row asked for an
architect ruling on which surface carries the condition — *publish the row anyway (with what margin
figure?) or hand `nixrisk.flatten` an `UNCERTAINTY` trigger from this site*. The brief ruled the
second and this is it. The daemon will still ACCEPT a `reserve`, COMMIT its margin and let the venue
fill in a symbol §3's picture has no margin scale for. **That is now D3.480**, a row of its own, so
the symptom's closure cannot read as the cause's.

---

## THE GATE — `check_uncertainty_flatten`, +1 PASSED

**Census, run before it was written.** `check_flatten`'s `SUBJECTS` is `("nixrisk/flatten.py",)` — it
owns the EXECUTOR as a LIBRARY and spawns no daemon. `check_stop_maintenance` owns §4:187-196's TRAIL
and the `SYNTHETIC_STOP` breach path — a different condition class: a stop that breached is a position
that WAS protected. `check_limiter_daemon_dispatch` owns the fill/reject/timeout DISPATCH — it
measures that the cascade RAN, and says nothing about what §14 owes a position the cascade REFUSED.
So the pair *daemon's uncertainty-producer set, and its completeness* is genuinely unowned, and
doctrine C.9 is respected rather than argued around.

Six arms: **1** each producer fires, driven through a real `limiterd` (never a direct call) · **2**
fire-once across ≥20 further scans with the condition still standing · **3** D3.469's BOTH branches ·
**4** producer completeness **BY DERIVATION** (the set read out of `limiterd.py`'s own AST and out of
the running process; the gate holds no copy) · **5** I9 and I3 over this arc's NEW code · **6** an
unclassifiable refused fill is CANNOT_MEASURE naming it, never PASS.

**ARM 5, measured:** the stale-open scan over §15's worst case — five OPEN rows, all stale, all
detected — entered only `['__main__','enum','limiterd','nixrisk.freshness','nixrisk.picture',
'nixrisk.positions']`. No I/O root, no transport root. The send entered no banned transport root.

### DEMONSTRATED FAILS — four REAL source plants against the SHIPPED gate

Each is an edit to `scripts/limiterd.py`, the gate driven against it, the file restored and its
`sha256` compared before and after (**`5e65a1d82f726a31` both sides — IDENTICAL**).

| plant | exit | what the gate said |
|---|---|---|
| **A** — a producer detects but does not fire | **1** | *UNPROTECTED POSITION. The `stale_open` condition (D3.453) was ESTABLISHED on a live daemon and NO §14 protective flatten was fired for it within 25.0s … `detected={'stale_open': 1}` `sends=0` `flattened=[]`* |
| **B** — D3.469 flattens too eagerly | **1** | *D3.469 FIRED AT THE INSTANT ITS WINDOW OPENED … the ruling is HOLD then decide — the delayed exec report is the common case* |
| **C** — double-flatten | **1** | *`stale_open` (D3.453) fired 3 protective flattens for ONE condition* |
| **D** — a fifth condition with no producer | **2** | *declares uncertainty condition(s) `['orphaned_position']` that this gate has no drive for, so their producers are UNMEASURED* |

**PLANT B's verdict is a correction this arc made to its own gate.** It first exited **2**, because
the eager fire tripped a precondition raise in the establisher and a defect downgraded to
CANNOT_MEASURE is a defect that never names itself. The raise was moved into ARM 3 as a finding; the
reason is recorded at the site.

**Plants removed ⇒ exit 0.** 13 pytest controls in
`scripts/tests/test_check_uncertainty_flatten.py`, including the **rule-4 plant-both** and a proof
that the gate holds NO copy of the condition set — driven by changing the subject to a set sharing
not one name with the shipped four, and requiring the derivation to answer with the invented names.

---

## A DEFECT THIS ARC FOUND IN ITSELF, AND THE CONTROL IT ADDED

The D3.469 sweep raised `AttributeError` — the firing was built from `TradeOrigin.symbol`, and
`TradeOrigin` has three fields of which the instrument is deliberately not one. **The loop's own
ingress containment swallowed it**, so the window was deleted, no flatten was enqueued, and the next
poll re-opened it. The daemon reported `windows_opened` climbing 1 → 2 → 3 with
`detected.undetailed_poll_fill` at **0** and `suppressed` at **0**: a producer that had silently
stopped producing, visible only because two counters disagreed. The symbol now comes from the
APPROVAL — the only authority in the room that holds one — and the sweep is contained **with a
recorded `last_error`** that the gate reads as a finding. Containment without a reason is how that
happens.

---

## PROCESS

* Baseline **MEASURED FIRST** at `5757f35`: `95 | 4 | 2 | 0`. Memory #27's prediction **MET** —
  `check_arc_status_contract` now PASSES auditing `arc_056.log`, clearing exactly one cannot-measure
  from ARC 056's `94|4|3|0`.
* `arc_heartbeat.sh` from kickoff; **both** the selfcheck line and the completion marker tee'd into
  `scratchpad/arc_logs/arc_057.log` (the recurring D3.464 gap).
* `--basetemp=/var/tmp/arc057_pt`, OUTSIDE `~/nix` (D3.462, project memory).
* Lint scoped to the CHANGED files, never `ruff .` — 8 findings, all this arc's, all fixed, clean.
* Tripwires run EXPLICITLY: `test_check_order_path_bans` + `test_check_uncalled_entry_points`.
* **Close-out (b) — the DERIVED reverse-dependency closure + the D3.444 by-detection backstop:
  106 modules, `2151 passed | 2 failed | 2 skipped | 2 xfailed` in 589s.** The closure is DERIVED
  (every test module that imports OR NAMES the changed artifacts and the detectors they read — the
  by-detection half, because the import graph is blind to a subprocess caller). **Both failures are
  PRE-EXISTING and neither is this arc's:** `test_PLANT_053B` is **D3.477 verbatim** (its plant anchor
  drifted at ARC 055 and the brief lists the row unchanged), and
  `test_the_LIVE_BASELINE_accepts_EXACTLY_what_the_LIVE_TREE_measures` fails on
  `stopwatch.py::StopWatch.forget`, which is in the `5757f35` baseline `verify.py` output taken
  BEFORE this arc touched anything and whose file is byte-identical here.
* **Close-out (c):** the gate BOUND from all four plants plus the rule-4 plant-both, and at the merged
  tree `check_hot_path_purity` **PASS**, `check_flatten` **PASS**, `check_stop_maintenance` **PASS**,
  `check_limiter_daemon_dispatch` **PASS**, `check_fill_handler` **PASS** — I9 and I3 not regressed by
  the new per-tick scan or the new sends.
* **Close-out (d):** CHECK-DEBT reconciled — 4 discharged, 3 opened — and the **ARC 057 series row
  re-derived WHOLE at 415** off `check_derived_claims`'s own `derived:ledger_rows`, never 416 plus
  arithmetic. `check_derived_claims` exit 0 (13/13 claims, 102 checks registered, 416 ledger rows).
* `checks/registry.json`: the new gate was **hand-added and then the derivation was made to agree**
  with it — `verify.py --optimize` refuses to derive a plan while an orphan check exists, and
  reported *derived plan is identical to the live registry* before `--commit` installed it.
* `check_uncalled_entry_points` **UNMOVED**: 170 uncalled, ratchet high-water 170, 21+4+3 rows,
  *55 measured and 25 render* — identical to the baseline in every counter. The brief expected a
  shrink; there is none, because the producers call no previously-uncalled entry point.

### THE TWO REDS THIS ARC BANKED OVER, AND THE PROOF THEY ARE NOT ITS OWN

The pre-commit runtime gate refused the first bank. Two of the selected tests failed, and **both
reproduce byte-for-byte at the derived tip `5757f35` in a CLEAN GIT WORKTREE, before a line of this
arc exists** — run there deliberately rather than argued from a diff:

* `test_check_limiter_daemon_dispatch::test_PLANT_053B` — **D3.477 verbatim**, the row the brief
  lists as unchanged: *the plant's anchor is not unique in scripts/limiterd.py (0 occurrences)*.
* `test_check_uncalled_entry_points::test_the_LIVE_BASELINE_accepts_EXACTLY_what_the_LIVE_TREE_measures`
  — `stopwatch.py::StopWatch.forget`, uncalled since ARC 055, and `stopwatch.py` is byte-identical
  here. **Nothing named it, so this arc opens D3.481** rather than silencing the red: WIRE IT is
  ARC D's work, DELETE IT removes the mechanism D needs, and ADMIT IT BY NAME would GROW a one-way
  ratchet the gate itself calls a suppression file.

Neither surfaced at ARC 056's bank because that commit ran `mode=incremental SELECTED=1`; this arc's
change selects both. **The first commit attempt also ran a 49m23s `full-escalated
(SCOPE-BLIND:changed-but-uncovered:...)` pass** because the two NEW files had no `.testmondata`
fingerprint — D3.466's shape on new artifacts. Fingerprinting them took the gate to
`mode=incremental SELECTED=11` in 8.23s, which is the ARC 052 remedy applied rather than re-derived.
Eight further `test_check_picture_atomicity` failures in that full pass are load artifacts of a
3631-test run — that module passes 23/23 standalone on this tree, and its gate PASSES under
`verify.py`.

---
## POST-WRITE-BACK RE-MEASURE — THE PREDICTION MISSED, AND THE MISS IS THE FINDING

**Predicted `96 | 4 | 2 | 0`. First measured at `51622ec`: `95 | 4 | 3 | 0`.** The new gate PASSED
standalone and came back **CANNOT_MEASURE under `verify.py`**, with its own sentence:

```
check_uncertainty_flatten  gate raised StalenessUsageError:
  admit('price:ES') was handed FreshnessStamp, not a FreshnessStamp
```

`FreshnessStamp is not FreshnessStamp` is **two module objects for one file in one interpreter**.
`verify.py` runs every check in a single process and several checks load their subject out of
`ctx.nix_home` by explicit path rather than by name, so an `isinstance` across the two copies is
False. That is **D3.224's *one tree per interpreter*** landing on a frozen value type — and the arm
that tripped it was ARM 5, the only place this gate imported anything from its own subject.

**Fixed by removing the class, not the instance.** ARM 5's tracer now runs in a **fresh interpreter**
(`_TRACE_SOURCE`, a subprocess), so this gate shares no interpreter with its subject at all and
§7.12 #5's caveat about one in-process import is gone rather than softened. The measurement that
forced it is recorded at the site.

**RE-MEASURED after the fix: `96 | 4 | 2 | 0`, `check_uncertainty_flatten [ok]` — the predicted
tuple.** The four FAILs are the same four the baseline carried, all environmental or inherited
(`check_ibgateway_service`, `check_monitor_tui`, `check_uncalled_entry_points`,
`check_untracked_attribution` on the `.dmg`), and the two cannot-measures are the standing
`check_ibgateway_config` / `check_observed_resource_claims` pair behind the unreachable port.

**A gate that passes alone and fails in the suite is a gate that measured one tree and was asked
about another. Standalone green is not the verdict; `verify.py`'s is.**

---

## RESIDUAL — EXPLICITLY NOT CLAIMED

* **I1 is NOT discharged. The count STAYS 11/12.** Only **ARC D** remains: the closing fills coming
  back → §12.10 `closed` rows → the position closing → §3's release, and the convergence gate that
  flips 11/12 → 12/12. A flatten fired here is **IN FLIGHT** until D reconciles it, and the fire-once
  mark is what stops the next tick re-firing it in the meantime.
* **D3.478 / D3.479 / D3.480** — this arc's own three narrowings, named above.
* **D3.476** (`nixalloc/sizing.py` has no trail distance), **D3.473 / D3.470 / D3.468** (real prices /
  onset detection / status-directory producers), **D3.477** (the inherited drifted test) — unchanged.
* No board redraw for the count. Tail annotation only: **all producers wired; only ARC D —
  completions + convergence — remains.**
