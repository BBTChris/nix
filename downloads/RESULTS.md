# ARC 054 — I1 ARC B: onset dispatch. `pending_entries()` built, the daemon's onset sweep wired.

**TIER: INTERIOR · Limiter STAYS RED · count STAYS 11/12 · no board redraw · I1 NOT discharged.**
Predecessor tip **DERIVED**: `git rev-parse HEAD` = **`24da438`** (the brief's "≈ 9e92a38" was ARC
053's fix commit, one behind its own write-back). Everything frozen and diffed against `24da438`.

## THE BASELINE WAS NOT WHAT THE BRIEF SAID — read this first

`verify.py` at `24da438`: **`93 passed | 4 failed | 3 cannot measure | 0 skipped`**, exit 1.
The brief recorded `94|4|2|0|0` for ARC 053's close. The one row of difference:

    [??] check_arc_status_contract  arc_053.log - ARC 053: no ARC-completed marker in log:
                                                  run did not reach close-out

The ARC 052 "the marker tees to the log" fix did **not** take effect for ARC 053's own log. This is
the D3.464 shape recurring. Every delta below sits on the **measured** 93|4|3|0, not on the reported one.

## What was wrong (S1, measured on the live loop)

| gap | evidence |
|---|---|
| **no production `pending_entries()`** (D3.443/D3.349) | `grep -rn "def pending_entries"` over the whole tree: **5 sites — 2 Protocol declarations, 3 test/check doubles, ZERO producers.** And nothing in production constructs a `HaltFlag` or a `BlackoutEvaluator`, so the two shipped call sites can never fire |
| **no onset dispatch at all** | the daemon serves `['register','go','status','resolve','reserve']` — `blackout_onset` and `halt` are *unknown verb*; signal files sit unconsumed |
| **consequence, driven** | 4 gate-approved entries staged over 2 symbols × 2 strategies + a real open position with an armed stop at 4998.0 → both onsets driven → **committed 7000.0 → 7000.0, outstanding 3 → 3, zero cancels.** Every entry survived, still working inside the window |

## What was built (S2) — and what was NOT touched

* **`limiterd.PendingEntryBook.pending_entries()`** — D3.443's producer, **complete by DERIVATION**:
  one entry per OUTSTANDING reservation in §11.3's ledger, **plus** one per holder of §4:208's
  in-flight lock that holds no reservation. The second source is the load-bearing half — such an
  order can still fill — and it is handed over as `InFlightOnly`, deliberately carrying no `role`
  and no `symbol`, so **I11's own `_classify_for_onset` decides** and buckets it `unclassified`.
* **`limiterd.OnsetWatch`** — reads `DIR/onset/state.json` on the loop's own tick, holds the prior
  state, fires **once per `False → True` transition**: per-symbol for blackout (`scope=<symbol>`),
  once globally for HALT (`scope=None`). Composed AHEAD of the ingress reads.
* The daemon now constructs a real **`flatten.ProtectiveFlatten`** over the process's one ledger and
  one picture. Its broker has exactly one verb — measured, `hasattr(broker, "flatten")` is **False**
  — so the sweep cannot flatten even in principle. Its §4 fan-out sinks **RAISE**, so ARC C's
  unwired protective-exit path cannot run silently.

**FREEZE HELD**, proven with `git hash-object` against `24da438`: **23 files byte-identical**,
including `flatten.py`, `blackout.py`, `outcomes.py`, `reservations.py`, `fills.py`, `halt.py`,
`seam.py`, `broker_seam.py`. The whole diff is **three files + `docs/CHECK-DEBT.md`**.

## What was proven (S3, watched past the tick)

| claim | measurement |
|---|---|
| BLACKOUT onset, **per-symbol** | handed all 4, `scope='ES'`, cancelled `es-1, es-2` — **none survives** |
| **scope** — another symbol untouched | `nq-1, nq-2` → `out_of_scope` with the executor's reason, **still pending after** |
| **release** (the 044 path) | RSV-1/RSV-2 released, **committed 7500.0 → 2500.0**, `complete=True` |
| **selective** — exits untouched | protective stop `es-fill` still armed **at 4998.0**, position still open |
| **edge-triggered** | 61 further polls in the same blackout → `blackout_onsets` still 1, one sweep |
| HALT onset, **global** | `scope=None`, cancelled `nq-1, nq-2`, **committed 2500.0 → 0.0, outstanding 0**; stop still at 4998.0 |
| **re-entry — *which*?** | **EDGE-TRIGGERED *and* IDEMPOTENT**: 3rd sweep `handed=[] cancelled=[] released=[] refusals=[]`; the ledger refuses a second release |
| **completeness (absence proof)** | in every sweep `handed` == `cancelled` ∪ `out_of_scope` ∪ `protected` ∪ `unclassified`, nothing unaccounted |
| **CANNOT-MEASURE arm live** | a lock-holder with no reservation → enumerated (`role: null`), swept, `unclassified` naming it, **`complete: false`** |

## The gate (S4) — one owner, four plants

Census: DISPATCH → `check_limiter_daemon_dispatch` (046); SELECTION already in `check_flatten` ARM 3b
(045). **No new gate** (doctrine C.9); the onset arm extended the dispatch's owner and `flatten.py`
was added to its SUBJECTS. The arm declares the onset from **outside the process** — never by calling
the sweep.

* **PLANT A (no sweep)** → exit 1, names `['cdd-onset-a1','cdd-onset-a2']` surviving and the ES window
* **PLANT B (incomplete enumeration)** → exit 1, *"INCOMPLETE ENUMERATION: `['cdd-onset-a2']` hold OUTSTANDING §3 reservations"*
* **PLANT B2 (omission its own report HIDES)** → exit 1 four ways, incl. Σ 3600.0 → 2700.0 vs expected 1800.0. **Σ over the TAKEN set is a number `pending_entries()` cannot edit**
* **PLANT C (over-broad)** → exit 1 in **two forms**: a venue cancel of a protective order is caught by the census *before* driving; the form §12.1's SYNTHETIC stop actually takes (`StopBook.forget`, invisible to that census) is caught by the driven arm — *"before `{'cdd-fill-1': 4998.0}`, after `{}`. The OPEN position(s) `{'TRD-…': 'ES'}` were left unprotected inside the window"*

Plants removed ⇒ **exit 0**, green evidence carries `*** PROTECTIVE BOOK UNCHANGED across both
onsets ***`.

**FOUND AND FIXED, NOT CARRIED:** the gate's own `Drive` wrote command/completion/status files
non-atomically while the daemon scans every 0.02 s. Measured: the daemon read `cdd0012.json` **empty**
and the FILL arm then reported a conversion that had happened. All four writers now use `os.replace`.

## Close-out

* **442 tests green** — derived reverse-dependency closure + the D3.444 by-detection backstop over the
  NEW structural edge `limiterd → nixrisk.flatten`.
* **Ratchet did NOT move:** 1210 entry points judged vs 1203, all 7 new ones CALLED; UNCALLED 171,
  GATE-ONLY 53, both unchanged. The predicted shrink did not occur and could not have:
  `cancel_entries_on_onset` already had shipped callers — what it lacked was a **process**.
* **CHECK-DEBT: D3.443 DISCHARGED. D3.442 shrank a third time (restated, not removed). D3.470/471/472
  opened.** ARC TOTAL **413**, read off the instrument (413 of 484 rows), RED against the stale 411
  before the edit and GREEN after.

## Residual — explicitly NOT claimed

* **The daemon DISPATCHES an onset; it does not DETECT one (D3.470).** §6.1's `BlackoutEvaluator`
  needs §6.4's window cache and the vendored calendar; §12.5's `HaltFlag` needs the cooldown floors,
  a marker and a Plane-2 emitter. Neither is constructible here and neither was half-built. **No green
  may be read as *the daemon knows when a window opens*.**
* **D3.471** — an onset arriving while the state file is unreadable is MISSED; counted and published,
  never silent, never invented in either direction.
* **D3.472** — the no-resend census now over-approximates into `OnsetWatch`; its ban claim stays scoped
  to two modules. `place_order` remains unreachable and separately driven.
* **I1 is NOT discharged.** Only the **protective flatten** remains (ARC C — D3.453/D3.372/D3.469),
  then ARC D's convergence gate flips 11/12 → 12/12.

**BADGE: Limiter STAYS RED · count STAYS 11/12 · no board redraw · I1 path-progress 5 of 6 wired
(cancel · fill · reject · pending-timeout · onset). D3.442 restated: only protective flatten owed.**
