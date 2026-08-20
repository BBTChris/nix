# ARC 048 — RESULTS

**ULTRAREVIEW: Limiter, slice 8 — I3 exit-path zero-wire independence. TIER = INTERIOR.**

**I3 DISCHARGED. Clean set 7/12 → 8/12 — the first count flip since ARC 045. Limiter STAYS RED.**

---

## 0. The predecessor, derived

The brief gave `≈ 696020c`. `git rev-parse HEAD` gave **`4b418f0`** — one commit further on (047's
own final-measurement commit). All freeze and diff work below binds to `4b418f0`.

## 1. The baseline, MEASURED before anything was written

```
90 passed | 4 failed | 2 cannot measure | 0 skipped | 1 guarded    exit 1     @ 4b418f0
```

047's `89 | 4 | 3 | 1 | 1` **did not survive**: passed 89→90, cannot-measure 3→2, skipped 1→0.
Second consecutive arc in which carrying the predecessor's composition forward would have been
wrong. Named:

| bucket | checks |
|---|---|
| FAIL (4) | `check_ibgateway_service` (ECONNREFUSED), `check_monitor_tui` (ARM3 stale pin), `check_uncalled_entry_points` (21 + 4 rows), `check_untracked_attribution` (`downloads/Pinokio-8.0.40-arm64.dmg`) |
| CANNOT-MEASURE (2) | `check_ibgateway_config`, `check_observed_resource_claims` — both downstream of the dead gateway |
| GUARDED (1) | `check_artifact_gate_coverage` — 8 exclusions |

`Pinokio-8.0.40-arm64.dmg` is **still on disk** and is an operator artifact: this arc neither
created it nor deleted it. It reddens `check_untracked_attribution` until the operator rules.

## 2. S1 — the exit-path CODE is clean, and the finding is that nothing proved it

Derived from the code, not transcribed from §3's prose:

* **trigger vocabulary** — `FlattenTrigger` (`seam.py:608`) declares **7**; `flatten.py:143` refuses
  **1** (`SENTINEL`, R4, raising `TriggerNotFireable`) ⇒ **6 fireable**.
* **protective-exit sites**, by AST shape — `fire` (`flatten.py:664`, §4's untargeted uncertainty
  flatten) and `_arbitrate` (`flatten.py:746`, the targeted per-trade close).

Driven across **6 triggers × 2 target shapes** with the Allocator, the ZMQ/state bus and the Plane-1
delivery wire all DEAD (each double proven to reject first — `ConnectionError`, `EFBIG` errno 27):

```
RESULT: 12/12 trigger×shape drives flattened with EVERYTHING dead
```

ARC 038's **FC1** (disk-critical WAL aborting the flatten) and **FC2** (protective losing a threaded
race) really were discharged. I3's open half is the one **FC5 / D3.373** names: **no instrument
proved it.**

## 3. The defect, REPRODUCED before it was fixed

`check_flatten` drove **1 of the 6** fireable triggers against **1** dead surface. A wire dependency
reachable only from `STALE_PRICE`:

```
=== PLANT A: STALE_PRICE publishes to the wire before flattening
    (flatten.py sha b1fa8256b3a7 -> 895065777a7e)

driven with the wire dead:
  synthetic_stop  flattened=True          calls=['MESU6']  still_open=[]
  stale_price     RAISED ConnectionError  calls=[]         STILL OPEN=['MESU6']

GATE VERDICT WITH PLANT A IN:  rc=0      pass: ...
=== RESTORE: byte-identical=True
```

A real open position, unflattened at the broker, with the gate certifying wire-freedom over it.

## 4. S2 is empty on purpose

**`scripts/nixrisk/flatten.py` is BYTE-IDENTICAL across this arc.** `git hash-object` reads
`d2c825f7f239657f1abb2935f7586cb9e8eddc13` at `4b418f0` and at the bank. There was no exit-path
defect to repair — there was an absent proof. Editing the subject to make a point is the
manufactured green this gate's own `CORRECTABLE = False` exists to forbid.

## 5. S4 — ARM 6, exhaustive wire-freedom. Every input DERIVED, none listed

1. **The trigger set** = the frozen enum minus the **subject's own** `_R4_TRIGGERS`. A list inside
   the gate is exactly what went stale.
2. **The exit sites** = the subject's AST, by shape (`self._broker.flatten(...)` inside
   `ProtectiveFlatten`), never by identifier spelling (D3.426). **Every derived site must have been
   ENTERED** or the proof is incomplete (contract rule 4).
3. **Wire-freedom** = the **live call census** (`sys.setprofile`) of each drive, classified against
   an **ALLOW-set, not merely a ban-list**. §7.12's answer to *what would make this pass while
   measuring nothing* is *a transport nobody listed*, so an unknown module on the exit path is
   **CANNOT_MEASURE naming it**, never a PASS. The allow-set is honest because it was **measured**:
   the shipped exit path enters four module roots across 15 frames.

**The Allocator has no dead double, deliberately.** `ProtectiveFlatten` takes no allocator
collaborator at all, so injecting one to watch it go unused would be a prop, not a measurement
(directive 1). `nixalloc`/`nixbus` are banned in the census, which catches a reach by *any* route.

### The gate, BOUND from four plants

| plant | expected | got | names |
|---|---|---|---|
| **A** wire dependency on an undriven trigger | 1 | **1** | `trigger=stale_price`, `ConnectionError`, `['MESU6'] OPEN at the broker`, `§14:969` — both shapes |
| **B** discretionary beats protective | 1 | **1** | `precedence-reverse` |
| **C** a trigger the derivation cannot classify | 2 | **2** | `margin_call`, "NO disposition" |
| **D** a derived exit site the drive never enters | 1 | **1** | `ProtectiveFlatten.emergency_flatten (flatten.py:679)` |
| plants removed | 0 | **0** | byte-identical restore |

### RED-before / GREEN-after — the sharpest evidence in the arc

With PLANT A on the **real** file, ARC 038's own control **passed** while both new controls
**failed**:

```
1 passed   test_the_EXIT_PATH_TOUCHES_NO_WIRE_MODULE      <- BLIND to this defect
2 failed   test_EVERY_FIREABLE_TRIGGER_FLATTENS_with_EVERYTHING_DEAD[targeted]
                                                          [untargeted]
RESTORED sha d2c825f7f239…  byte-identical: YES
```

That is FC5 as a measurement rather than a claim: the old control cannot see it; the new one can.

## 6. Freeze

| path | state |
|---|---|
| `scripts/nixrisk/flatten.py` | **byte-identical** (the subject itself needed no change) |
| `completions.py`, `fills.py`, `limiterd.py` (047's fill path) | byte-identical |
| `outcomes.py`, `reservations.py` (I2) | byte-identical |
| `picture.py` / mirror | byte-identical |

Diff is: `checks/check_flatten.py` (ARM 6 + its §7.12 answer), `scripts/tests/test_check_flatten.py`
(+6 controls), `scripts/tests/test_arc038_c_exit_brake.py` (+4 controls),
`docs/CHECK-DEBT.md`, `checks/gate_coverage_baseline.json` (owner re-point only, 16 lines), and the
arc brief.

**The `uncalled_entry_points` ratchet did NOT move, and did not need to.** The gate measures 54,
rendering 25 (21 + 4) — identical to baseline. This arc changed no shipped call graph.

## 7. Debt

* **D3.453 opened** — `FlattenTrigger.STALE_PRICE` is a §3 protective trigger **nothing in this tree
  ever fires**: `grep -rn STALE_PRICE` hits exactly two lines (the enum member, and a parametrize
  list in a test). `freshness.py` detects staleness and blocks NEW ENTRIES; §6.4's other half —
  flatten what is already open — has no implementation. Structurally invisible to
  `check_uncalled_entry_points`, which hunts uncalled entry points, not unreachable enum members
  with no producer. Wiring it needs the §6.4 staleness-to-flatten policy — an architect ruling.
* **D3.454 opened** — the allow-set is a measured property of today's path; widening it requires a
  written non-transport reason in the same commit as the code that needed it.
* **D3.373 STAYS OPEN, deliberately not claimed.** Its subject is `check_plane1_degraded`'s C2
  tautology, untouched here. I3's property is now gated in a *different* gate; marking the row
  discharged would be a false claim about `plane1_degraded_drill.py`.
* **ARC 048 series row = 401**, derived by `check_derived_claims`'s `derived:ledger_rows`.

## 8. Badge

**I3 DISCHARGED.** Clean `{I2, I3, I5, I6, I7, I8, I10, I11} = 8/12`, open = 4: **I1** (the daemon
capstone, ~4 arcs), **I4**, **I9**, **I12**. **Limiter STAYS RED.**

### Explicitly NOT claimed

* The daemon **firing** protective-flatten completions (`StopBook.breached` off the price poll) —
  **I1 ARC C/D**, D3.451. I3 proves the exit-path CODE carries no wire; the daemon-level firing is
  the capstone.
* **D3.450** (the `fills.py` release-before-commit torn state) stays — `fills.py` frozen here.
* D3.373, D3.428, D3.434, D3.438–D3.443, D3.446–D3.452 — standing named debt.

---

## 9. THE FINAL MEASUREMENT

```
90 passed | 4 failed | 2 cannot measure | 0 skipped | 1 guarded    exit 1    @ b462121
```

**PREDICTION HIT** — identical to the measured baseline at `4b418f0`, which is exactly the predicted
delta. Extending `check_flatten` creates no new gate file, so `passed` does not move; the badge axis
(7/12 -> 8/12) is separate from the verify tuple. The level was MEASURED at the derived tip before
the delta was predicted, which is the discipline ARC 047 failed and named.

**One pass in this tuple is green for the wrong reason, and it is this arc's own defect.**
`check_arc_status_contract` reports `[ok]` against `scratchpad/arc_logs/arc_047.log` — a COMPLETED
arc's log — because `arc_048.log` did not exist when the check ran (position 7 in the plan, executed
minutes before the log was created at stage 14). That is **D3.455** visible inside the banked
measurement, not merely described by it. It is recorded as measured and NOT claimed as evidence
about ARC 048.

**The mid-arc prediction revision was the error, not the original.** After creating `arc_048.log`
this arc revised its prediction to `89 | 4 | 3 | 0 | 1`, reasoning the new log would take
`check_arc_status_contract` to cannot-measure. Wrong: the check had already executed. A mid-run
change to a check's subject does not retroactively change a verdict already recorded in the same
run.

Standing and untouched by this arc: `check_ibgateway_service` FAIL + `check_ibgateway_config` /
`check_observed_resource_claims` CANNOT-MEASURE (gateway down, not a misconfiguration, §4.1);
`check_monitor_tui` FAIL (ARM3 stale pin); `check_uncalled_entry_points` FAIL at 54/25, baseline
byte-identical; `check_untracked_attribution` FAIL on the operator's `Pinokio-8.0.40-arm64.dmg`.
`check_artifact_gate_coverage` GUARDED, exclusions now `-> ARC 049`.

**Ledger 402** (derived). **D3.455 opened by the write-back against this arc's own process** — the
heartbeat emitter ran from kickoff but was never tee'd to `arc_logs/arc_048.log`. The ARC 048 series
row at 401 is struck and superseded by 402, the ARC 039 / D3.424 convention.
