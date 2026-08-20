# ARC 049 — RESULTS — Limiter slice 9: I4, two-phase entry (OPEN only on confirmed fill)

**Tier: INTERIOR. Limiter STAYS RED. I4 DISCHARGED: 8/12 -> 9/12.**
**Predecessor tip DERIVED: `e6835fb`** (the brief's ≈`b462121` is 048's I3 commit, not the tip).

## Headline

**I4 was MET IN CODE. The defect was the PROOF, and the proof is now a gate.** Five sites in the
shipped tree originate `OPEN`, all five behind a confirmed fill, and the eight-surface drive is
unchanged from ARC 038: an ack opens nothing, a fill opens everything. What was missing was an
absence proof that could survive the next edit — and the standing one could not.

## S1 — the defect, reproduced on a copy

`test_arc038_c_open_is_confirmed_fill.py::test_OPEN_is_WRITTEN_at_EXACTLY_TWO_SITES_and_PENDING_at_NONE`
derives the OPEN-setter set by `grep -rn "state=PositionState.OPEN"` and asserts the set of MODULES.
Planted into a throwaway copy: a phantom path publishing §3's row with `state=_ENTRY_STATE`, where
`_ENTRY_STATE = PositionState.OPEN` sits at module level.

* the standing control: **GREEN**, `sites == {positions.py, projection.py}` still holds
* the by-shape census: **5 originators -> 6**, naming `positions.py::publish_on_ack`

It is also module-granular (`projection.py`'s three `build.state = STATE_OPEN` transitions were
outside its match entirely) and it is a pytest control, so **`verify.py` had no arm for I4 at all.**

## S2 — empty by design, proven byte-identical

Twelve frozen paths, `git hash-object` before and after, all IDENTICAL: `positions.py`,
`projection.py`, `picture.py`, `seam.py`, `completions.py`, `fills.py`, `limiterd.py`, `flatten.py`,
`outcomes.py`, `reservations.py`, `nixalloc/mirror.py`, `execution.py`. `CORRECTABLE = False`.

## S3/S4 — `checks/check_two_phase_entry.py`

**ARCHITECT DECISION NEEDED / TAKEN — the brief's premise was false.** It asked me to find and
EXTEND "the gate that owns the entry-state / two-phase discipline". Censused across all 98 gates:
**no gate owns it.** `check_execution_ledger` owns the ledger's arithmetic and says in its own text
that nothing there proves the state model calls it; `check_fill_handler` owns the fill motion;
`check_origin_write` owns `stop_distance`'s value; `check_plane1_projection` owns rebuildability;
`check_limiter_gate`'s "two-phase" is §3's gate-wall, a different property under the same words.
Doctrine C.9 forbids a SECOND instrument for an OWNED property; this one was unowned, and folding it
into any of those four would have merged two properties against §5.5. **So a NEW gate, and `passed`
moves +1** — a departure from the brief's predicted delta, stated before the run.

* value domain **DERIVED** from `seam.py`'s enum, not spelled; aliases resolved to a fixpoint, so
  `PositionState.OPEN`, `PositionState("open")`, `STATE_OPEN`, `"open"`, ternaries and local names
  all resolve alike (D3.426)
* three-way fail-closed: ORIGINATOR / TRANSPORT / **UNCLASSIFIABLE => CANNOT_MEASURE naming it**
* each accepted originator carries a **named structural precondition re-derived from the AST every
  run** (`_row` only from `on_fill` which ingests first; `_on_fill` bound to `EVENT_FILLED` alone;
  the two projection handlers refuse BEFORE the transition — the order is checked; `fold_events`
  still filters `qty_filled > 0`), keyed by `(module, function)`, never by line number
* driven on real objects with non-vacuity asserted first, and **watched past the tick** (a REJECT
  release after the ack, every surface re-read)

### Demonstrated FAIL

| plant | verdict | exit |
|---|---|---|
| A (driven) — ack publishes optimistically | FAIL — `PHANTOM POSITION … ['phantom-0'] reading OPEN` | 1 |
| A (static) — same defect through an alias | FAIL — `UNDECLARED OPEN-SETTER in publish_on_ack` | 1 |
| B — confirmed fill never reaches OPEN | FAIL — `UNPROTECTED REAL POSITION … ['c-fill-1:pending:2']` | 1 |
| B (gate) — `qty_filled == 0` refusal removed | FAIL — invisible to every drive; derived statically | 1 |
| C — unresolvable `state` expression | CANNOT_MEASURE naming it | 2 |
| plants removed | PASS — 100 modules, 5 originators, 3 drives | 0 |

**A gate defect the plant found:** PLANT A made the ack arm RED and the fill arm unmeasurable, and
the first draft returned the refusal — light-blue over a measured phantom. Rule 4 orders
Fail > Cannot-measure for exactly this; unmeasured arms now ride alongside the FAIL, not instead.

## D3.455 — DISCHARGED

By the row's OWN stated mechanism: `arc_heartbeat.sh` writes its own log by default (twelve lines),
named from the progress file's `arc=` line, so a beat cannot be emitted without being recorded and
never under another arc's name. **Plus** the durable half: `check_arc_status_contract` excludes the
RUNNING arc's log by name, audits the immediately-previous arc, and NAMES it —
`AUDITED ARC 048 (arc_048.log): arc=048 pulses=9 teardowns=1 wd_pid=434005`. Nothing older inside the
freshness window is CANNOT_MEASURE naming what is missing, never a fall-back pass. 8 tests including
the demonstrated FAIL. **D3.433's one-arc-late cadence is unchanged and still open.**

## NOT CLAIMED — needs an architect ruling

**D3.372 stands and is why I4's discharge is narrower than I4's sentence.** A confirmed fill whose
origin write is REFUSED (`UntradableSymbol`, §4:198) leaves §3's table and §12.7's mirror reading
FLAT over a real position and records only a counter — a real *confirmed fills ⊄ OPEN* case. The new
gate drives the ACCEPTING path and **names this refusal as out of scope in its evidence on every
run**, so no green covers it. Owner re-pointed ARC 039 (ten arcs stale) -> ARC 050+. **The ruling
still owed: WHICH surface carries the not-tradable condition** — publish the row anyway (with what
margin figure?) or hand `nixrisk.flatten` an `UNCERTAINTY` trigger from that site, plus a consumer.

Also not claimed: the pending-timeout resolution (`query_order_status`, never an auto-resend) is the
POLL path = **I1 ARC A**. D3.450 and D3.453 stand untouched.

## A pre-existing red found by the write-back, and fixed

The pre-commit gate refused the commit on `test_restated_figures::test_the_LIVE_LEDGER_no_longer_
contradicts_itself`. **Already red on trunk** (verified by stashing this arc's write-back files and
re-deriving), carried as `recorded_failures=1`. **ARC 047's row is CORRECT; the instrument was
wrong**: `restated_figures` ended the `Opened:` passage on `". "` and that row closes `…balance).**`
— a period against bold markup, no space — so the segment ran on and counted `(D3.177)`, cited two
sentences later, as a fifth opening. The SAME failure mode `_segment`'s docstring already records for
ARC 020, under a different spelling; `discharged_count` already stopped at `"**"`, and the asymmetry
was the defect. Fixed by adding `".**"` to the stop set: **live-ledger defects 2 -> 0**, no other
row's reconciliation moved, bound by two new tests (the bold sentence end stops the passage; the
narrowed stop still REFUTES a wrong total). 41 -> 43 tests. ARC 047's banked row was NOT edited and
`--no-verify` was NOT used.

**One more thing the gates caught on each other, worth keeping.** The new gate read `_HANDLERS` with
`node.value.keys`, and `check_uncalled_entry_points` resolves a public entry point BY RECEIVER TYPE:
a bare `.keys` on an expression it cannot type moved a real finding —
`freshness.py::SourceMonotonicGuard.keys` — from `uncalled` to `cannot_resolve`, which its own
baseline arm correctly reported as a stale row. **A new instrument was eroding an existing one's
ratchet as a side effect of how it SPELLS an AST read.** Rewritten to `ast.iter_fields`, and the
reason is in the code beside it. `check_uncalled_entry_points` is back to its byte-identical
baseline, 54 measured / 25 rendered.

## Ledger

**+1 net.** OPENED: **D3.456** (the census scopes bare `.state =` to modules naming a state value;
a cross-module alias is outside it — stated where the boundary is drawn), **D3.457**
(`projection.py::position_rows` stamps OPEN on every stored row unconditionally; safe only because
`fold_events` filters upstream, which the gate now re-derives every run). DISCHARGED: **D3.455**.
**Series row 403**, read off `check_derived_claims`'s `derived:ledger_rows`, never typed.
The eight `gate_coverage_baseline.json` exclusions re-pointed 049 -> 050 before close-out, with the
reason recorded: **fourth consecutive arc of boundary maintenance on the same eight artifacts** —
D3.104's overdue-work case carried, not paid.

## Measurement

* **BASELINE at `e6835fb`: `89 | 4 | 3 | 0 | 1`, exit 1.** Not 048's closing `90 | 4 | 2 | 0 | 1`,
  and the difference is this arc's own kickoff: the D3.455 tee creates `arc_049.log` before Stage 1,
  so `check_arc_status_contract` (which took the NEWEST log) read a run in flight. 048's `[ok]` over
  `arc_047.log` and this `[??]` over `arc_049.log` are the same defect from its two sides.
* **PREDICTED: `91 | 4 | 2 | 0 | 1`** — +1 for the new gate file, +1/-1 for
  `check_arc_status_contract` flipping to PASS under the patch. 97 -> 98 checks.
* **RE-MEASURED: appended below at the close-out, forward-only.**

## BADGE

**I4 DISCHARGED. Clean `{I2, I3, I4, I5, I6, I7, I8, I10, I11} = 9/12`, open = 3
(`I1`, `I9`, `I12`). Limiter STAYS RED.** Three-quarters of the module. Remaining: **I1** (the
4-arc daemon capstone), **I9**, **I12** — then greening.
