# ARC 053 — RESULTS (I1 ARC A: reject + pending-timeout dispatch)

**Tier INTERIOR · I1 slice 3 of 4 · predecessor DERIVED `1f5a1e6` · write-back `a7e1fcf` + `9e92a38`.**
**NO INVARIANT FLIP. Count STAYS 11/12 (open: I1). Limiter STAYS RED. No board redraw.**
I1 discharges only at ARC D's convergence gate.

## Verify tuple

| | passed | failed | cannot-measure | skipped | guarded |
|---|---|---|---|---|---|
| baseline, measured at `1f5a1e6` FIRST | 94 | 4 | 2 | 0 | 0 |
| **predicted** | 94 | 4 | 2 | 0 | 0 |
| first re-measure at `a7e1fcf` | 93 | **5** | 2 | 0 | 0 |
| **after the correction `9e92a38`** | **94** | **4** | **2** | **0** | **0** |

**PREDICTION MISSED, THEN REACHED — and the miss is a finding worth more than the hit.**
`check_risks_data_only` went red on my own new knob: *"`signal_max_age_ms`: has no `_derivations`
entry — a knob with no stated origin has its semantics settled HERE, which is exactly the second
authority `risks/` may not become."* The argument for the knob was written, into `_meta` (which
describes the *file*) instead of `_derivations` (where a value states its *origin*). I ran three
gates against the new knob and never ran the one whose subject **is** the config file. Moved
verbatim; re-measured to the predicted tuple. Registered check count unchanged at **100**.

## What was wired

**REJECT** — the cheap half, reusing the ARC 046 mechanism whole. `WIRED_EVENTS` gains `on_reject`,
`OutcomesPort` gains the verb, `_dispatch_reject` is a **literal mirror** of `_dispatch_cancel` so the
two stay independently plantable. `rejects_dispatched` was added in the same edit because `_finish`
counted every non-fill dispatch as a cancel — the new path would have been invisible to the counter
set that exists to name it.

**PENDING-TIMEOUT** — a POLL, not a completion. `StatusQueryPort` already existed (ARC 044) and was
unwired, which is I1's shape exactly. Added: `DirectoryStatusQuery` (one verb, one file read, absent
⇒ the seam's own `unknown`) and `PendingTimeoutPoller`, composed onto the loop's ingress the way
`Plane1Booker` is, running **after** the reads so a terminal completion resolves an order before the
poll would ask the venue about it.

| §4 answer | daemon's resolution | driven |
|---|---|---|
| `cancelled` | RELEASE | ✓ |
| `rejected` | RELEASE | ✓ |
| `working` | HELD | ✓ |
| `indeterminate` | HELD toward flat (§14) | ✓, across 32 further queries |
| `unknown` (no answer on disk) | HELD | ✓ |
| `filled` | **HELD — see D3.469** | ✓ |

## §4's no-resend rule — proven TWICE

* **DRIVEN:** 666 polls, 698 queries, **`resends=0`**, `committed` constant at 1600.0 across 32
  further queries of an `indeterminate` order. That number is the assertion: a second live order
  needs a second reservation.
* **STRUCTURAL:** an AST reachability census from `PendingTimeoutPoller.poll_due` — 14 functions, 39
  distinct calls across `limiterd.py` + `outcomes.py` — reaches **none** of the eight venue-placement
  verbs **derived** from `broker_seam.ORDER_PORT_VERBS`. It runs **before anything is driven**,
  because driving a build that can resend would itself be the act.

## The one thing I did NOT build, and why — D3.469

**The brief specified `filled` → the 047 fill cascade. The seam cannot support it.**
`broker_seam.OrderStatus` has four fields; §2A's `on_fill` needs six, and `exec_id`, `symbol` and
`price` are not among them. Driving it would mean inventing execution data **and** creating a second
conversion site where §4 converts once, at the confirmed fill. `filled` is therefore HELD and counted
separately, conversion stays the exec-report path's, and the residual — a lost exec report leaves the
reservation committed — is **D3.469**, an architect ruling, not an invention.

## D3.463 DISCHARGED

On the **reserve** seam (the 052 recon had already corrected the question). The `or time.time()`
fallback is gone — an absent instant is a **refused** reserve, not one dated at arrival — and
`signal_age_refusal` makes `signal_ts` a STAMP FIELD. **`check_input_freshness` moved
`ProposedOrder` out of its ungated bucket by its own derivation; `ungated_accepted` is now `[]` and
`_ACCEPTED_UNGATED` was shrunk to `{}`.** Ceiling: `signal_max_age_ms` = 5000 ms, a declared Nix
addition, deliberately **not** derived from `pending_ack_timeout_ms` (the two bound different
intervals). Driven both directions: stale DENIED naming its age and the ceiling, absent DENIED naming
§17, neither taking capital, fresh still ACCEPTED.

## The gate — extended, not added (rule 8 / C.9)

`check_limiter_daemon_dispatch`, **no new file, no count move**. 21/21 tests green.

| plant | verdict | named |
|---|---|---|
| **053A** reject left unwired | exit 1 | `THE DAEMON DID NOT RELEASE ON A REJECT`, `DRAINED BY THE LOOP`, `still TAKEN` |
| **053B** poll unhooked from the tick | exit 1 | `ZOMBIE ORDER`, `NOTHING POLLED IT`, `polls=0`, `reservation LEAKS` |
| **053C** the poll RESENDS | exit 1 | `NO-RESEND VIOLATION`, `place_order`, `SECOND LIVE ORDER` |
| rule-4 plant-both | exit 1 | the found defect decides; the blind arm printed as `ALSO UNMEASURED` |
| ban list underivable / closure unreachable | exit 2 | CANNOT_MEASURE — never a pass |

Plants removed ⇒ exit 0, on the same real population.

## Freeze

Byte-identical to `1f5a1e6`: `outcomes.py`, `reservations.py`, `fills.py`, `fill_seam.py`,
`flatten.py`, `positions.py`, `projection.py`, `loop.py`, `wal.py`, `freshness.py`, `gate.py`,
`seam.py`, `plane1_sink.py`, `picture.py`, `nixalloc/mirror.py`. The freshness files did **not** need
the brief's exception — the D3.463 refusal lives in `limiterd.py`.

**Ratchet movement, as asked:** `OrderOutcomes.on_reject` and `.resolve_pending_timeouts` LEFT
`uncalled_entry_points_baseline.json` — the daemon calls them now. A shrink, the one permitted
direction.

## Ledger

**411 open of 481 rows**, re-derived whole (`derived:ledger_rows` = `stated:series_table_latest_row`).
D3.463 discharged; D3.468 (the §4 status surface is a directory nothing in this tree writes) and
D3.469 opened. **D3.442 shrank a second time and is RESTATED, not removed.**

## D3.442 — restated

| §3 path | daemon-invoked? |
|---|---|
| cancel | ✓ ARC 046 |
| fill cascade | ✓ ARC 047 |
| **reject** | **✓ ARC 053** |
| **pending-timeout** | **✓ ARC 053** |
| onset | ✗ — ARC B (needs `pending_entries()`, D3.443) |
| protective flatten | ✗ — ARC C (D3.453 / D3.372; the daemon has no protective-exit path at all) |

## Left for the operator

`downloads/Pinokio-8.0.40-arm64.dmg` is still untracked and still the sole cause of
`check_untracked_attribution`'s FAIL. Third-party macOS installer, not project work; it needs a
provenance ruling (delete, or `.gitignore` with a written reason). Unchanged from ARC 052.

**Next: I1 ARC B** (onset). I1 path-progress: 4 of ~6 resolution paths wired.
