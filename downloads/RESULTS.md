# ARC 044 — ULTRAREVIEW: Limiter, slice 6 — I2: exactly one terminal release

**TIER = INTERIOR.** Predecessor tip **DERIVED** with `git rev-parse HEAD` = **`3c73002`** (the
brief's `≈ b7476a6` was approximate; every freeze and diff here is against `3c73002`).

## VERDICT

**I2 DISCHARGED. Limiter STAYS RED.**
Clean set `{I5, I6, I7, I8, I10} = 5/12` → **`{I2, I5, I6, I7, I8, I10} = 6/12`, open = 6.**
Remaining open: **I1** (instrument the daemon — capstone), **I3, I4, I9, I11, I12**.

## THE DEFECT I2's CHARTER NAMED — and it was NOT the half this brief led with

The 038 register holds seven findings under I2. The **at-most-one** half was already RESISTED (4,000
real-thread iterations, zero arithmetic violations; the gate already bound by four plants). The
blocking half was **F-B3 / D3.358**: the **at-least-one** half failing at the **WIRING**, not in the
ledger. Three of §3:151's six release paths had **no production release site at all**.

Re-measured live at `3c73002` before touching code, non-vacuity asserted first (Σ observed to RISE
by the exact proposed margin):

```
CANCEL / PENDING_TIMEOUT / REJECT   taken RSV-00000001  Σ 0.0 -> 6172.5 (+6172.5)
  production release sites: NONE
  after the terminal event: outstanding=1 Σ=6172.5 released=0 drift=0.0 material=False
5 leaked reservations: Σ=30862.5 scanned=30862.5 drift=0.0 material=False
```

`drift=0.0` over a real leak: a leaked reservation sums into the incremental aggregate and the full
scan identically, so §11.7's reconcile is **structurally blind** to it. The failure mode is a slow
strangle — committed never falls, §3 Phase B eventually denies everything, and it looks like a
market that stopped giving signals.

## THE FIX — `scripts/nixrisk/outcomes.py` (NEW). `reservations.py` NOT touched

`OrderOutcomes`: `on_cancel`, `on_reject`, `resolve_pending_timeouts`. Three **literal** `resolve`
sites, one per path.

* **Why not in the ledger.** The census that measures the wiring scans production modules for a
  `resolve`/`release` call. A ledger booking its own paths would satisfy it with six one-line
  methods — a measurement its own subject can satisfy alone, which is the circularity
  `seam.TerminalPath`'s docstring forbids. `reservations.py` is **byte-identical to `3c73002`**.
* **Why not in `fills.py`.** A cancel that filled nothing, a reject and a timeout carry no quantity
  and no price. `IocRemainder._guard` refuses `filled_qty <= 0` for exactly that reason.
* **The timer is not the event.** §2A:71 / §4:241 / §12A:830 — a pending-order timeout resolves by
  `query_order_status`, **never** a resend. Release hangs off the RESOLUTION: `cancelled`/`rejected`
  release; `working`, `indeterminate`, `unknown`, `filled` and any undeclared state are **HELD**,
  counted and named. Releasing at the deadline would free margin for a live order — the §15 C1 cap
  breach. **NO retry, NO auto-resend**, asserted over the module's call graph.
* **Three literal sites, not one helper.** The first build centralised the call and the census
  correctly refused to credit any of the three (`<unresolved>`). Three literals are also three
  independently plantable sites.

Census after the fix — six paths, empty unreadable bucket:

```
BLACKOUT_ONSET  blackout.py:1062 + flatten.py:805      CANCEL           outcomes.py:305
FILL            fills.py:391                            REJECT           outcomes.py:320
HALT_ONSET      flatten.py:805                          PENDING_TIMEOUT  outcomes.py:400
<unresolved>    none
```

The ARC 038 ratchet **FAILED FIRST in the progress direction** (`production wires [six] and this file
records [three]`) before `WIRED_PATHS` was moved; `UNWIRED_PATHS` is now the empty set and is kept,
not deleted — the assertion over it is what turns a path LOSING its caller back into a loud failure.

## PROOFS — `test_arc044_exactly_one_terminal_release.py`, 22 controls, all green

* **Exhaustive single-release** over the set DERIVED from the tree, not a list. The parametrise
  rosters are read back out of the file's own AST and each must EQUAL the derived set, so the roster
  cannot silently shrink. All six paths driven through their real production surfaces
  (`IocRemainder`, `ProtectiveFlatten` both onset causes, `OrderOutcomes` the three new ones): each
  releases **exactly once**, Σ back to baseline, one RELEASED record with the right cause, store
  empty, `material=False`.
* **No double release under race**, on real objects: partial-fill remainder arriving after the
  cancel (`refused_releases == 1`); pending-timeout vs terminal feedback **in both orders**;
  blackout onset during a pending order (the later sweep issues no query at all — the ledger's TAKEN
  set no longer holds it). Σ compared **bit-identically**, not approximately.
* The two independent censuses in this tree (gate arm, ARC 038 ratchet) are cross-checked against
  each other rather than one being deleted.

## THE GATE — `check_reservation_lifecycle` EXTENDED (rule 8 / doctrine C.9), no second instrument

**ARM WIRING**, three halves: STRUCTURAL (census by shape; a §3 path with no site is a FAIL naming
it), LIVENESS/COMPLETENESS (**CANNOT_MEASURE naming the site** when a terminal-transition call's
cause cannot be read statically), DRIVEN (the handler's own published verbs against the real ledger,
Σ to baseline, a second event leaving Σ bit-identical).

**Not one release path is named in the gate's source** — its own test greps for that. Expected side
from the frozen spec, observed side from the tree, driven side from the census ∩ the module's
`HANDLES` map, cross-checked so a subject cannot shrink its own drive. The stale
`UNBOUND (D3.51) … handlers do not exist yet` sentence (F-B6 / D3.362's class) is gone: the coverage
sentence is regenerated from the census every run.

**BOUND — four real plants on a staged tree, shipped tree sha256 unchanged throughout:**

| plant | exit | named |
|---|---|---|
| **A1** leak — release SITE deleted | **1** | `outcomes.py:wiring[CANCEL]` — no module books CANCEL; committed permanently INFLATED |
| **A2** leak — site present, release ineffective | **1** | `outcomes.py:OrderOutcomes[CANCEL]` — Σ 6172.5 → 6172.5 against a 0.0 baseline; the 6172.5 reserved was not returned |
| **B** absorbed double release | **1** | `outcomes.py:OrderOutcomes[CANCEL]` — a SECOND event moved Σ 0.0 → **−6172.5**; committed UNDER-counts (§15 C1) |
| **C** new terminal site, cause unreadable | **2** | `cannot_measure: late_reject.py:13 … the enumeration is INCOMPLETE and the verdict is unmeasured rather than green` |
| plants removed | **0** | pass |

## FREEZE — against the derived tip `3c73002`

`scripts/nixrisk/outcomes.py` (new) · `checks/check_reservation_lifecycle.py` ·
`scripts/tests/test_arc038_b_reservation_terminality.py` (the ratchet baseline D3.358's own discharge
criterion names) · `scripts/tests/test_arc044_exactly_one_terminal_release.py` (new) ·
`docs/CHECK-DEBT.md` · `checks/gate_coverage_baseline.json` (exclusion owner re-pointed **044 → 045**,
named in advance as the brief required). **Nothing** in the sole-writer seam, `picture.py`/mirror, the
042 booking, `reservations.py`, `fills.py`, `blackout.py`, `flatten.py` or `limiterd.py`.
`limiterd.py` untouched ⇒ incremental commit path.

## CLOSE-OUT (INTERIOR)

* **(b) Derived reverse-dependency closure** — 16 test suites (14 derived + this arc's 2): **269
  passed**; 16 gates constructing the ledger: **16/16 exit 0**. RED-before/GREEN-after proven on this
  arc's own defect by the ratchet failing first.
* **(c)** gate bound from all four plants (A1/A2/B exit 1, C exit 2, sites named).
* **(d)** CHECK-DEBT reconciled: **D3.358 DISCHARGED**; **D3.441** opened (`unknown` venue state is
  HELD, never guessed — over-count direction, nothing re-asks) and **D3.442** opened (no production
  constructor for the handler — the same status the three pre-existing handlers have; the I1
  capstone). **ARC-TOTAL series row written** — `check_derived_claims`:
  `check_debt_open_items=389 [derived:ledger_rows=389, stated:series_table_latest_row=389]`, exit 0.
  No rule-3 row was owed for the new module: it ships in the same arc as its gate and is a declared
  SUBJECT of it.

## RESIDUAL — explicitly NOT claimed

The *value* of a reservation vs actual margin (§6.4) is not I2 and was not touched. D3.359 (the
`AUDIT_TOLERANCE` random walk), D3.360 (the bare `KeyError` under real threads), D3.361 (no Plane-1
`taken`/`released` pairing) and D3.363 (the blank `client_order_id`) stay open — I2-adjacent, none of
them the exactly-one-release property. D3.428, D3.434, D3.438, D3.439, D3.430–D3.433 and D3.440 stand
untouched. **I2's discharge is an invariant flip, not a debt row.**

## POST-WRITE-BACK RE-MEASURE — predicted, then measured at `4d04bfd`

**Predicted `90 | 3 | 2 | 0 | 1`, exit 1. Measured `90 | 3 | 2 | 0 | 1`, exit 1.** S4 extended the
existing V23 owner (rule 8 / C.9) and created no new gate file, so no count moved.

| measurement | pass | fail | cannot-measure | skip | guarded | exit |
|---|---|---|---|---|---|---|
| 043 final (`3c73002`) | 90 | 3 | 2 | 0 | 1 | 1 |
| **044 final (`4d04bfd`)** | **90** | **3** | **2** | **0** | **1** | **1** |

Three standing fails, same three: `check_ibgateway_service`, `check_monitor_tui`,
`check_uncalled_entry_points`. Guarded: `check_artifact_gate_coverage` (exclusion owner re-pointed
**044 → 045**, named in advance).

**The built-but-uncalled detector named this arc's own new module and the red is CARRIED, not
absorbed.** `outcomes.py::OrderOutcomes.on_cancel / ::on_reject / ::resolve_pending_timeouts /
::history / ::OutcomeRecord.released_margin` are reported UNCALLED because no shipped `scripts/` code
constructs the handler yet. They were **not** added to the accepted baseline: the three pre-existing
handlers' equivalents are not in it either, and admitting only this arc's rows would make the
baseline say something about ARC 044 that is untrue of its siblings. That is D3.442, and it is the
ARC 034 / D3.203 precedent. The check was a standing fail before this arc and is one after it.

`check_arc_status_contract`: `pass: arc_044.log: arc=044 pulses=9 teardowns=1 wd_pid=None`.

## BADGE

**Limiter RED.** `{I2, I5, I6, I7, I8, I10} = 6/12` clean, **6 open**: I1 (capstone), I3, I4, I9,
I11, I12.
