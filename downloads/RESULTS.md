# ARC 016 RESULTS — commit the broker package; prove gate coverage; re-validate live

**Date:** 2026-08-10 · **Node:** node02 (MS-01) · **Branch:** `arc-016-broker-consolidate`
**Environment for every live result:** IB Gateway 127.0.0.1:4002, clientId=905, paper DUR250018,
MESU6 only, qty 1. Market **OPEN** (Monday 2026-08-10 13:44 CDT; MES trades to 16:00 CT).

---

## Definition of success — every box, against the criterion as written

| # | criterion | verdict |
|---|---|---|
| 1 | `scripts/broker/` and the adapter test tracked; full untracked audit reported | **PASS** |
| 2 | Gate coverage proved by **tracking, not naming**: defect planted, caught by an unqualified `pre-commit run --all-files`, removed, byte-identical | **PASS** |
| 3 | Committed, PR'd, merged to main; commit message covers ARC 014 **and** 015 | **PASS** |
| 4 | `seam_simulate.py` in the pytest suite; both non-vacuity controls still *fail* as controls | **PASS** |
| 5 | The joint gate/`fetchFields` dependency written into the code | **PASS** |
| 6 | D2.8 promoted to doctrine with the standing question and the seven-instance evidence base | **PASS** (with a citation correction — see §2c) |
| 7 | Live: connect, positions, balance, margin verified on clientId=905 with real figures | **PASS** |
| 8 | Live: reconnect proves `_wire_events` idempotency by handler count | **PASS** |
| 9 | Live: order lifecycle on MES — ack-once, per-unit `avg_price`, cancel, status | **PASS** |
| 10 | Live: `flatten()` closes a real position with zero venue queries; venue confirms flat | **PASS** |
| 11 | Ack-synthesis path either observed live or explicitly recorded as offline-proved only | **PASS** — recorded, with a partial live observation |
| 12 | Account confirmed flat at close via fresh venue query | **PASS** |
| 13 | `verify.py` exit 0; Tier-2 gates pass on the now-tracked tree | **PASS** |

---

## Part 1 — tracked, and the gate proved to follow

### 1.1–1.2 What is now tracked, and the audit in full

Committed: `scripts/broker/` (4 files, 2 488 lines), `scripts/tests/test_broker_order.py`
(1 270 lines), and the ARC 014/015 infrastructure that had also never landed — `pyproject.toml`,
`checks/pinned_deps.json`, `directory_structure.md` v1.4.0, `CHECK-DEBT.md`, 163 lines of
`SESSION.md` history, and the ARC 015/016 briefs (following the existing `downloads/arc_*.md`
convention). **Both commits were pushed to origin the moment they existed** — the risk this arc
exists to retire is durability, and that should not wait for a merge.

**Untracked audit — the full list, as required:**

```
A. non-ignored untracked, whole tree            (none)
B. scoped: scripts/ checks/ risks/ databases/ docs/   (none)
```

**Zero.** Stated, not assumed. The *ignored* listing was the informative one and produced a finding:

- **`state/encrypt_credentials.py` is real Python that no gate can see.** `.gitignore` excludes
  `state/` wholesale — correctly, since it holds the hardware UUID and credential JSON — but
  executable code lives there too, so it is untracked and outside `--all-files` for exactly the
  reason D3.2 records. **Failure mode #14 sitting in the tree today.** Opened as **D1.16**; not
  fixed, because the arc forbade behaviour changes and moving credential tooling is not trivial.

**Gitignored rather than committed** (the arc's "check for anything that should not be tracked"):

- `downloads/*.py` — superseded inbound drafts. The landed copies have grown 626→790, 258→525 and
  489→1270 lines, so committing them would plant a **second, stale source of truth** for live code.
- `.testmondata-shm` / `.testmondata-wal` — the bare `.testmondata` rule did not cover the SQLite
  WAL sidecars, and a `git add -A` duly staged them.
- `__pycache__/`, `.DS_Store`, `._*` were already covered.

### 1.3 The gate proof — scope, not invocation

**Non-vacuity first (§7.3), before any plant.** `pre-commit --all-files` derives its file list from
`git ls-files`:

```
at HEAD (untracked = invisible):   (no broker files at all)
after git add:                     scripts/broker/broker_order_ibkr.py
                                   scripts/broker/broker_seam.py
                                   scripts/broker/ibkr_mapping.py
                                   scripts/broker/seam_simulate.py
                                   scripts/tests/test_broker_order.py
```

| step | command | result |
|---|---|---|
| CONTROL | `pre-commit run --all-files` | **8/8 Passed, exit 0** |
| PLANT | `F821` undefined name in `broker_seam.py` | — |
| CAN-FAIL | `pre-commit run --all-files` — **no path named anywhere** | **exit 1** |
| RESTORE | plant removed | **all five files byte-identical (sha256)** |
| CONTROL | `pre-commit run --all-files` | **8/8 Passed, exit 0** |

Three independent hooks failed and **each named the planted site**:

```
ruff    F821 Undefined name `ARC016_THIS_NAME_IS_DELIBERATELY_UNDEFINED`
             --> scripts/broker/broker_seam.py:648:12
pylint  scripts/broker/broker_seam.py:648:11: E0602: Undefined variable ... (undefined-variable)
mypy    scripts/broker/broker_seam.py:648: error: Name "..." is not defined  [name-defined]
        Found 1 error in 1 file (checked 36 source files)
```

A defect that ruff **cannot auto-fix** was chosen deliberately: `ruff-check` runs with `--fix`, so an
unused import would have been silently repaired and the evidence would have been "files were
modified by this hook" rather than a named line. This is a *report*, not a repair.

---

## Part 2 — the cheap debts

### 2a. `seam_simulate.py` into pytest — D1.15 **discharged**

`scripts/tests/test_seam_simulate.py`. **It does not live inside `seam_simulate.py`**, deliberately:
`testpaths = ["scripts/tests"]`, so a `test_*` function added to `scripts/broker/` would have looked
converted and been collected **never** — strictly worse than the honest status quo. The driver stays
runnable standalone.

Controls asserted **verdict-by-verdict**, not inferred from a green aggregate (§7.7):

| control | required behaviour | measured |
|---|---|---|
| `HollowBrokerOrder` | must **FAIL** behaviourally | **9 failures** |
| working `StubBrokerOrder` | must **PASS** | **0 failures** — this is what makes the row above discriminating |
| `AwaitDivergentBrokerOrder` | must be **NAMED** | exactly **1** divergence: `query_positions: port declares async, adapter is sync` |

**The can-fail immediately caught a defect in the brand-new test.** The hollow control was written
with **two separate `RecordingSink` instances** — the adapter emitted into one, the assertions read
the other. Driven against a *working* adapter it **still reported failures**: it could not tell
"hollow" from "behaving", and would have stayed green through the exact regression it exists to
catch. Fixed to share one sink; 4/4 can-fails then demonstrated. Recorded in doctrine as the eighth
instance, and the first found *by applying the new principle*.

### 2b. The joint dependency, written where both are set

ARC 015 framed the `fetchFields` narrowing as "belt and braces over the gate". **That framing is
wrong**, and it is the framing that invites a future author to restore `EXECUTIONS`. Corrected at all
three sites read in isolation: `_startup_fetch_fields()`, the `connect()` docstring, and the line
where the gate opens.

**The gate does not cover `fetchFields`.** `_startup_complete` is set `True` the instant
`connectAsync` returns, and `_rebuild_mirror()` awaits **after** that — so the whole mirror rebuild
runs with the gate **OPEN**. Worse, `_connected` is already `True` there, so a concurrently scheduled
task can call `place_order` inside the same window and populate `_from_ib`; and **IBKR order ids reset
across sessions**, so a replayed *historical* execution can carry an id that now matches a *live*
order → a phantom fill reported to the Limiter.

**`fetchFields` does not cover the gate.** It suppresses one replay source *by name*. The gate is
venue-agnostic, catches whatever a future `ib_async` decides to fetch, and re-arms on every reconnect
for free.

Jointly sufficient. Individually not. Removing either opens a path the other does not close.

### 2c. Promoted to doctrine — `debug.md` v1.2.0

**§7.12 — THE STANDING QUESTION:** *what would have to be true for this to pass while measuring
nothing?* — required of every new gate and **answered in writing, beside the gate**, not in an arc
report. The seven instances are tabulated as the evidence base, each with *what it measured* and
*how it stayed green*, so the principle arrives with proof rather than as an assertion. Also added:
failure mode **#14 — scope set by an external mutable list** (distinct from #2: the gate is
configured exactly as intended and the *list it consults* moved, so no diff to the gate ever
appears). Linked from the trigger table, the §9 per-instrument checklist, and §11.

> ### ⚠ Citation correction — please read
>
> The brief directed this promotion at debt item **D2.8**. **D2.8 is doctrine B.7 — *"no harness
> parses a constant out of a document and asserts the code equals it"*** — which is the
> **derive-never-restate** class, **not** the vacuous-pass class. It remains **open and unassigned**;
> nothing about it was discharged, and a future arc reading "D2.8 was promoted" would find a doctrine
> section with nothing to do with parsing constants out of documents.
>
> The ledger items that actually carry the promoted class are **D1.10** (each hook actually capable
> of failing), **D2.7** (nothing baselined on a pristine tree — bandit scanning nothing is its
> measured instance), **D2.12** (a suite that silently skips a gate reports GREEN) and the whole of
> **D3**, whose header states the principle outright. §7.12 now stands over those.
>
> Recorded in the ledger rather than silently redirected, because **a pointer that reads as
> authoritative while naming the wrong target is itself a stale literal anchor** — §7.4, and the same
> class as the ledger's own miscounted series row.

---

## Part 3 — live re-validation, clientId=905

**28 PASS · 0 FAIL · 2 CANNOT-MEASURE.** Market state: **OPEN**.

### 3a. Read-only

| assertion | measured |
|---|---|
| `connect()` succeeds | **311 ms** |
| `on_session(UP)` emitted | `[('up', None)]` |
| mirror rebuild does not raise | clean, `mirror={}` |
| no ack **or** fill from startup replay — **1st connect** | `acks=[]` `fills=[]` |
| `query_positions()` — account flat | `[]` |
| `query_balance()` real figures | cash **20 334.15**, netliq **20 339.43**, maint 0.00, init 0.00 |
| `ts_is_venue_sourced=False` still set (GAP-2) | `False` |
| `get_margin("MESU6")` via `whatIfOrderAsync` under timeout | **2 449.13 USD/contract in 84 ms** (ARC 012 trap avoided) |

**The zero-qty filter was proved live and NON-VACUOUSLY.** The arc anticipated this might be
unprovable — it was not. The venue **did** emit a `position=0` row on the flat account:

```
venue raw rows : [('MESU6', 0, 0.0)]      <- a genuine zero-qty row
adapter returned: []                       <- filtered
```

This is a *venue* behaviour offline could only assert about, and it reproduced. Criterion met without
needing the "say so if it doesn't occur" escape.

### 3b. The reconnect — what offline genuinely could not prove

Non-vacuity established first: the id map was **populated** before the disconnect
(`_to_ib={'arc016-3b-map': 29}` via a far-off LMT), so "does not carry across" is not empty→empty.

| assertion | measured |
|---|---|
| **`_wire_events` idempotent — handler count per event unchanged** | `{orderStatus 1, execDetails 1, error 2, position 1, accountValue 1, disconnected 1}` — **identical before and after the 2nd connect** |
| id map does not carry across | `_to_ib={}` `_from_ib={}` (was `{'arc016-3b-map': 29}`) |
| no ack from startup replay, 2nd connect | `1 → 1` |
| no fill from startup replay, 2nd connect | `0 → 0` |

The duplicate-handler bug only manifests on a real second connect. It did not manifest.

### 3c. Order lifecycle — MES, qty 1, flat between tests

| assertion | measured |
|---|---|
| ack via the event stream **exactly once** | 1 ack |
| ack **precedes** fill in arrival order | `['on_ack:arc016-3c-buy:accepted', 'on_fill:...:1@7772.5']` |
| `on_fill` carries `cumQty` | `filled_qty=1 cumulative_qty=1` |
| **`avg_price` per-unit, not notional** | see below |
| **`flatten()` returns without blocking** | **0.292 ms** |
| **`flatten()` — zero `reqPositionsAsync` during the call** | **0** (wrapped and counted) |
| venue confirms flat after `flatten()` | fresh query → `[('MESU6', 0)]` |
| far-off LMT → `query_order_status` | `working`, non-terminal |
| `cancel_order` → `on_cancel` → status | `cancelled`, terminal |

**`avg_price` re-proved live against a *derived* anchor, not a literal band:**

```
fill price (Execution, per-unit)  7772.50
venue avgCost (Position, notional) 38863.11
multiplier                             5
avgCost / multiplier              7772.6220
adapter Position.avg_price        7772.6220   <- matches
the ARC 014 defect would have reported 38863.11
```

The residual 0.122 gap between fill price and `avgCost/mult` is the commission, exactly as ARC 014
measured — a fraction of a tick, not 5×.

### The two CANNOT-MEASURE results — stated, not implied

**1. `PendingSubmit → Filled` with no intermediate state was NOT observed.** Both fills went
`PreSubmitted → Filled`:

```
observed venue status sequences: {31: ['PreSubmitted','Filled'],
                                  32: ['PreSubmitted','Filled'],
                                  33: ['Submitted','PendingCancel','Cancelled']}
```

Not manufactured, per scope ("observe, do not force"). **For that trigger the synthesis path remains
offline-proved only.**

**But it is not untested live.** An earlier run of the identical harness *did* fire the synthesis, via
the `Cancelled` trigger rather than the `Filled` one:

```
no venue ack seen for arc016-3b-map before Cancelled — synthesised ACCEPTED (§2c)
('arc016-3b-map', AckStatus.ACCEPTED, 'synthesised: Cancelled arrived with no prior ack')
```

The second run did not reproduce it. **That difference is itself the evidence**: the §2c race is real
and timing-dependent, which is precisely the argument for synthesising rather than trusting that a
venue ack always arrives first.

**2. D1.17 — one requested `disconnect()` emits TWO `on_session(DOWN)` events.**

```
[('down', 'transport disconnected'),   <- _on_ib_disconnected, via ib_async's disconnectedEvent
 ('down', 'requested')]                <- disconnect() itself
```

Acks are deduped through `_ack_once`; **session events are not deduped at all.** Benign if the
Limiter treats DOWN as an idempotent *level*, a defect if it ever counts *edges*. Note the two carry
different reasons, so the provenance channel is intact and the fix is **not** simply "drop one" — §4
wants an unrequested drop distinguishable from a requested one. Not fixed here: the arc forbade
behaviour changes. **Discharge with the Limiter**, which owns that contract.

**Account confirmed FLAT by a fresh venue query at close**; the `finally` cleanup ran.

---

## Gates

```
verify.py                6 passed | 0 failed | 0 cannot measure | 0 skipped   exit 0
pytest (full, not -testmon)                              159 passed
pre-commit run --all-files       8/8 Passed  exit 0  — for the first time this
                                 includes scripts/broker/
```

Suites: project pytest 155 → **159**. Debt **26 → 27** (D1.15 discharged; D1.16, D1.17 opened) —
recounted mechanically, not by hand, per the ledger's own lesson.

---

## Findings for claude.ai

1. **The D2.8 citation is wrong** (§2c above). Substance delivered; the pointer needs correcting in
   whatever the brief was generated from, or the next arc inherits it.
2. **`state/encrypt_credentials.py` is invisible to every gate** (D1.16). This is the same class the
   arc was written about, still live in the tree. Needs an arc to move code out of `state/` while
   leaving the data behind — do **not** un-ignore `state/`.
3. **`disconnect()` emits two DOWN events** (D1.17). Needs a Limiter-side decision on edge vs level
   before it is "fixed" in the adapter.
4. **The series table had silently skipped two arcs** — ARC 014 and ARC 015 added no row at all.
   Reconstructed mechanically. A ledger that stops being written is indistinguishable from one with
   nothing to report.
5. **ARC 013's commit was also unmerged**, stranded on `arc-013-delayed-feed`. It rides to `main` in
   this PR, so nothing is left behind.
