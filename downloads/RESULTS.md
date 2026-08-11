# ARC 021 — R1-B broker-datafeed · RESULTS

**Status: COMPLETE.** Two sub-agents, offline-first, disjoint from broker-order by invariant.
Base `94ac5b5` (verified on `origin/main` after `git fetch`, per §0b).

**No tap session ran.** `~/nix/downloads/TAP_SESSION.md` does not exist. §4 and §5 proceeded with
declared reds, as §0b directs.

---

## 1. THE HEADLINE, AND IT IS NOT THE GREEN

Both gates were built, both bound to the real adapter, both pass. Then **two real D1.13 defects
were planted in the real adapter and BOTH GATES PASSED — and so did all 49 of the adapter's own
tests.**

| plant | what it breaks | gate | pytest (before Phase 4) |
|---|---|---|---|
| delete the sentinel write in `subscribe()` | a RE-subscribe inherits the previous subscription's grant | **PASS** | **49 passed** |
| substitute requested for granted in the adapter-wide accessor | reports the requested mode as the grant — D1.13 verbatim | **PASS** | **49 passed** |

Both gates' can-fail had been proven — six plants, every one failing and naming its site — but
**every plant was against a purpose-built fake**, because the adapter did not exist while the gates
were being written. The gates' structural arms key on the fake's shape: a vendor field read and
written by name, and a `granted_mode=` keyword. The real adapter has neither, because the mode
arrives as a callback parameter into per-symbol state. **Discrimination against a fake did not
transfer to the real subject.**

Recorded as **D3.10** with the plants as evidence. The immediate hole is closed by two pytest cases
added in Phase 4, each proven to fail its own plant and nothing else, four outputs each, controls
restored byte-identical. What stays owed is the gates' own binding — their structural arms still
measure little against this adapter, and the next adapter will present a third shape.

This is the arc's most important result and it exists only because Phase 4 re-ran the plants against
the merged tree rather than trusting two green sub-agent reports.

---

## 2. BOTH GATES REDDENED CORRECT CODE FIRST — doctrine B.4, repaired at the instrument

On first binding, both gates FAILED the real adapter. Both were wrong.

- **`check_datafeed_granted_mode` arm B3** approximates dataflow by intersecting two sets of NAMES.
  Every method call contributes the receiver to both sets, so `self._ib.reqMarketDataType(...)` and
  `granted_mode=self.granted_mode(symbol)` intersected to `{'self'}` — and the gate reported a
  correct adapter as deriving the grant from the request, which is the opposite of what that code
  does. Binding names excluded; plant P3 still fails; nothing added to any suppression list.
- **`check_datafeed_bar_seal` arm 2** recognised only the membership spelling of a seal guard
  (`if key not in store`). The adapter used the lookup-then-sentinel spelling
  (`found = store.get(key)` / `if found is None`), which proves the same property and hashes the key
  once. The gate was taught the second spelling rather than the code being asked to adopt the first.

`VERIFY-AND-CHECKS.md` doctrine B.4: a gate that reddens the correct implementation of its own
subject is BROKEN, not strict. **Neither ban nor behaviour was weakened.** Both residuals are named:
D2.20 (B3 is name-identity, not dataflow) and D2.21 (guard polarity still unchecked, unchanged in
size by the repair rather than introduced by it).

---

## 3. PROHIBITION 3 — did not fire, and the reason is structural

`check_order_path_bans` **exit 0**, scope `5 → 6` files. The datafeed joined via the unconditional
`("scripts/broker",)` anchor floor exactly as predicted. It did not redden, because send-path verbs
derive to `cancel_order` / `flatten` / `place_order` — none of which exists in a datafeed library,
*because invariant 3 keeps them apart*. Invariant 3 is what kept the ban and the spec-mandated poll
retry from colliding. **No scope-boundary repair was needed and no ban was touched.**

---

## 4. INVARIANT 3 — verified at AST level, not accepted on report

**Zero import edges between the two libraries, both directions.**

```
broker_datafeed_ibkr.py -> ['__future__', 'broker_seam', 'dataclasses', 'logging', 'time']
broker_order_ibkr.py    -> ['__future__', 'asyncio', 'broker_order_config', 'broker_seam', ...]
order-library import edges from datafeed: 0
```

Duplicated rather than imported, each argued at the site: connection lifecycle, the single-emission
choke point, the evidence-gated error table, the retained-observable accessor, the clientId refusal.

**Three extractions considered and REFUSED**, none performed, none escalated:
1. `IB_ERR_CONN_LOST` / `IB_INFO_CODES` — same 1100/1101/1102 integers, **different meanings**. The
   order library reads 1101 as *our position mirror may have missed events*; the datafeed must read
   it as *our subscriptions may have been dropped and the grant re-negotiated*. A shared table forces
   one meaning on both — the `avg_price` defect at module scale.
2. `ibkr_mapping.py` — read, never imported; it carries the order mapping too.
3. `BrokerCapabilities` — a separate `DatafeedCapabilities` instead, on the same argument that makes
   the two ports separate Protocols.

**clientId 2**, decided and argued. 905 rejected because IBKR refuses a duplicate clientId, so a
diagnostic probe run against a live capture would displace the production feed — a diagnostics action
reaching a production data path, which is the coupling V24 exists to disprove. A distinct clientId is
a distinct TCP session: **invariant 3 realised at the transport layer, not only in the type system.**

---

## 5. FEEDLAG — the decision the arc turned on

Shape: `declared_lag_s: float|None`, `observed_lag_s: float|None`, `observed_n`, `provenance`
(UNOBSERVED / VENDOR_DECLARED / PRIOR_ARC / OBSERVED), `granted_mode`, `divergence_tolerance_s`.
Agreement is a readable finding (NOT_DECLARED / NOT_OBSERVED / AGREES / **DIVERGED**). Every tick and
bar carries `recv_ts` alongside `venue_ts`.

Vendor-blind primitive: **`excess_staleness_s = (now - venue_ts) - effective_lag_s`**. On a 0-lag
vendor it reduces to raw data-age; on IBKR a healthy 600 s tick yields ~0.3. Same consumer, same
threshold, right answer on both. Returns `None` for cannot-compute, never 0.0 — which would be the
healthiest possible answer to a question that could not be asked.

**Proven as a 2×3 matrix, and the third condition is the non-vacuity:**

| vendor | healthy | transport dead | data-clock stalled |
|---|---|---|---|
| Tradovate-shaped (0.0) | FRESH | STALE | STALE |
| IBKR Stage 0 (~600) | FRESH | STALE | STALE |

A transport-only implementation was **planted** and failed exactly the two `data-stalled` cells,
passing the other four. Both naive consumers are additionally *executed* in the suite and shown
failing on their own cell, so the design argument is asserted rather than only written down.

**Lag provenance corrected.** The brief attributes 600.3 s to **ARC 010**; the tree attributes it to
**ARC 013** (`sessions/SESSION.md:622`, `broker_seam.py`, CHECK-DEBT D1.13). Further, the banked
record is a **range** — `600.0–601.9 s, spread 1.9 s, n=8` — and the scalar 600.3 appears only in
derived copies. Carried as a range with the mean named as a summary, `provenance=PRIOR_ARC`,
`agreement=NOT_OBSERVED`, and re-measurement recorded as owed (D1.33). ARC 010 does have a real
624 s figure — `reqHistoricalTicks` staleness, visible in its own output and never computed. The
brief appears to have merged the two.

---

## 6. THE ABSENCE PRINCIPLE (AMENDMENT 3) — and what it costs

Recorded **verbatim** in `docs/SPEC-AMENDMENTS.md` as AMENDMENT 3, in AMENDMENTS 1–2's format,
attributed as an operator ruling issued in ARC 021, **not spec text**, pending a v1.4.

Applied throughout: `FeedLag`'s two `float|None` terms, all tick fields and all five OHLCV fields
`| None`, the `UNKNOWN` grant sentinel, `excess_staleness_s -> None`, and `poll_history` **raising**
on exhaustion rather than returning zero rows — *the venue had nothing* and *we could not reach the
venue* must not read the same. It also **fixed a live instance of the defect it forbids**:
`StubBrokerDatafeed.feed_lag()` was returning `declared_lag_s=0.0, measured=False,
granted_mode=REALTIME` — three fabrications in the one object built to prevent them.

**Where it is expensive, reported because the ruling is ratified but its cost was never measured:**
every price-shaped field becomes `float|None`, adding a `None` branch at every consumer arithmetic
site — **and the cost lands entirely on consumers that do not exist yet**. This arc paid none of it.
The bill is real and unmeasured (D1.36 area, tracked). It is cheap exactly where an enum already
exists and expensive exactly where a *number* is involved, because a number has no spare member.

---

## 7. BAR IMMUTABILITY (D1.14)

Seal key `(symbol, bar_start_venue_ts, period_s)`. An unseen key publishes once on `on_bar`; a
sealed key is never written over. A differing re-poll publishes `BarRevision` on its **own event**,
not a flag on `on_bar` — a defaulted flag is silently ignorable, and the ignorable default here
reads as *ordinary new data*, which is D1.14's defect verbatim. `BarRevision.__post_init__` refuses
to exist with empty `differing_fields` or a payload equal to the sealed one, so a hollow revision
cannot be constructed by any future call site.

**Non-vacuity asserted first**: the test asserts the two payloads are unequal *before* re-polling, so
it cannot degrade into one whose second poll returns identical data.

---

## 8. COUNTS — all derived, none typed

| measure | baseline `94ac5b5` | final | delta | derived from |
|---|---|---|---|---|
| pytest | 242 | **293** | **+51** | `pytest_collector` ∧ `source_ast` |
| registered checks | 10 | **12** | +2 | `checks_glob` ∧ `registry_json` |
| claims compared | 10/10 | **13/13** | +3 | `check_derived_claims` |
| CHECK-DEBT rows | 40 | **53** | **+13** | `ledger_rows` ∧ series row |
| pre-commit | 8/8 | **8/8** | 0 | hook suite |
| `seam_declared_elements` | 23 | **25** | +2 | `spec_plus_flagged` ∧ `seam_code_total` |
| `order_path_scope_files` | 5 | **6** | +1 | `gate_derived_scope` ∧ anchor |

**Datafeed roster, all three counts derived from §2A directly:**
**4 bullets · 6 identifiers · 9 including flagged Nix additions** (`feed_lag`, plus `on_bar` and
`on_bar_revision` added this arc). The bullet/identifier disagreement is real —
`connect() / disconnect()` is one bullet declaring two identifiers. No disagreement was found
between spec and seam.

### Coverage — level and delta distinguishable

- **broker-order element coverage: 56 → 56, delta 0.** Derived `spec_denominator` ∧ stated
  `seam_denominator`. **Expected not to move and did not** — this arc did not touch broker-order.
- **broker-order depth (`broker_order_open_debt_rows`): 11 → 16, delta +5 — AND THIS IS
  CONTAMINATION, NOT WORK.** Nothing touched broker-order. Rows naming `ibkr_mapping.py`, a file
  hosting both §2A adapters, are claimed by the order-side rule's module-basename half. Measured, not
  worked around; recorded as **D2.19**.
- **broker-datafeed element coverage: NO FIGURE EXISTS, deliberately.** It needs a grade tally this
  module has never had. Registering a number without one would have invented a denominator. What was
  registered instead is `spec_2a_broker_datafeed_elements = 9`, cross-derived.
- **broker-datafeed depth (`broker_datafeed_open_debt_rows`): new, 10.** **A FLOOR ON OUTSTANDING
  OBLIGATIONS, NEVER A FRACTION OF THEM** — the only honest denominator would be *how much do we
  trust this module*, which is unknowable, and a percent over an unknowable denominator is a
  confidence score wearing arithmetic.

---

## 9. FIVE RAW GATES

```
verify.py            10 passed | 1 failed | 1 cannot measure | 0 skipped   exit 1
pytest               293 passed
pre-commit           8/8 Passed
check_derived_claims 13/13 claim(s) compared                              exit 0
check_spec_citations                                                      exit 0
```

**`verify.py` exit 1 is the ACCEPTED BASELINE and there is no third failure.** The single failure is
`check_ibgateway_service`, with `check_ibgateway_config` cannot-measure, both from the IB Gateway's
daily session expiry (it expired at 03:00:04 UTC with `status=0/SUCCESS` — not a crash, not code).
Both new gates report **[ok]**, bound to the real adapter.

---

## 10. §0a — CONTRADICTIONS FOUND IN THE BRIEF (reported, not reconciled)

The architect asked for these by name. Four, one of them sharp:

1. **`debug.md §5` is Tier 3, not Tiers 1–2.** §4/A6 says *"Tier 1 and Tier 2. Per `debug.md` §5"* —
   but `debug.md:388` is `## 5. TIER 3 — END-OF-MODULE CERTIFICATION`. Tier 1 is §3, Tier 2 is §4,
   the tier overview is §2.1. **A6's citation points at precisely the section prohibition 6
   forbids.** Sub-agent A followed the intent and refused Tier 3; a literal reader would have built
   the one thing the arc bans.
2. **The lag is attributed to ARC 010; the tree says ARC 013**, and the banked figure is a range, not
   the scalar 600.3. (§5 above.)
3. **The brief violates its own §0a rule.** §0a states §13 numbers objectives 1–23 plainly and adopts
   the `V` prefix at V24, so the brief writes *"§13 objective N"* for 1–23 only. It then writes
   *"§13 objective 24"* twice. Verified: the spec's line 919 is `V24`. The substantive claim is
   correct — V24's text is *"kill/reconnect the datafeed under load and prove the order path is
   undisturbed"* — only the citation form contradicts the rule stated fourteen lines earlier.
4. **10189 vs 354 is NOT a contradiction** — resolved rather than reported. `reqTickByTickData` is a
   real-time-only path and returns **10189**; `reqMarketDataType(1)` + `reqMktData` returns **354**
   with no grant callback. Both banked, both encoded, each attributed to its own call.

**Also found, in the tree rather than the brief:**
- A pylint suppression in the new adapter disabled `import-outside-toplevel` with a five-line
  rationale describing a lazy `ib_async` import. **There is no such import** — the vendor client is
  injected. `debug.md` §7.4's stale-anchor class, banked on day one. Removed, not reworded.
- The seal gate's new `too-many-lines` disable was written with a rationale **measured for that
  file** rather than copied from its sibling, where the copied claim (*"exceeds 1000 even with all
  docstring prose removed"*) would have been **false** — 1039 total against 820 without. Copying it
  would have committed the same defect in the act of citing doctrine.
- **`pre-commit run --all-files` does not scan untracked files.** Sub-agent B measured this live:
  all 8 hooks reported green over its new gates for the entire build, and ~30 findings appeared the
  moment they were `git add`ed. **The brief's Phase 4 step 6 is not a valid gate over untracked
  work.** Every run reported here was made with everything tracked.

---

## 11. WHAT IS EXPLICITLY NOT DONE

- **No Tier 3.** Tiers are sequential; a module written this morning has no Tier 3. **ARC 022.**
- **No live IBKR measurement.** Everything is offline against a fake. D1.13's live half is
  **D1.33**, worded as *re-confirm on a current session* rather than *never observed*, because
  ARC 013 already measured the sentinel and the silent 4→3 downgrade on this account and banked it.
- **V24 remains KNOWN-RED.** Two distinct clientIds is the precondition; nothing has killed the
  datafeed under load and measured the order path. **R1-D.**
- **`on_bar` / `on_bar_revision` widen a LOCKED signature** and are flagged Nix additions awaiting an
  architect ruling (**D1.36**). §2A declares two datafeed events and says capture builds bars. The
  argument for adding them is written at the site; it is not this arc's to ratify.
- No Limiter, no Allocator, no `capture.py` wiring, no consumer. No config JSON (**D1.35**).

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.**

---

## 12. FOR THE ARCHITECT

1. **Ratify or overturn `on_bar` / `on_bar_revision`** (D1.36). If overturned, the seal and its
   revision event move to `capture.py` and D1.14's adapter half moves with them.
2. **AMENDMENT 3 is recorded and pending a v1.4**, with its cost stated and unpaid.
3. **D1.38** — the datafeed port's sync/async split has never been argued as ARC 015 argued the
   order port's. A port change binds every vendor; it is not an adapter's call.
4. **D3.10 is the transferable lesson**: can-fail against a purpose-built fake proves the gate can
   discriminate, not that it discriminates *against the real subject*. Both gates passed two real
   planted defects. Consider requiring, as a standing rule, that a gate's can-fail be re-run against
   its first real subject before the debt it covers is called narrowed.
5. **The next tap discharges D1.33** and the owed lag re-measurement. `tap_session_runbook.md` is
   still valid and unrun; D1.12's reboot capture is also still unfired.
