# ARC 059 RESULTS — MODULE 2 (broker-order) OPENING RECON

**TIER = RECON (read-only).** No code change, no invariant flip, no badge move. **Module 1 GREEN
12/12, untouched and re-measured: `97 | 4 | 2 | 0`** — the predicted tuple, met.

**Predecessor DERIVED, not assumed:** brief said `≈ ARC 058's write-back`; `git rev-parse HEAD` =
**`13952451ef6ca55d70b3635487f9634c95fa2e3a`**.

**Deliverable: `downloads/broker_order_recon.md`** — the charter for Module 2's ULTRAREVIEW.
Method: four read-only sub-agents + direct verification by cc of every load-bearing claim.
Claims cc did not re-measure are marked **UNVERIFIED** in the report.

---

## THE THREE HEADLINES

### 1. broker-order is NOT a scaffold — and the error has one source

`broker_order_ibkr.py` is **2361 lines over a real, installed `ib_async 2.1.0`**. All nine §2A verbs
have real bodies. **Zero** `NotImplementedError`, `TODO`, `pass  #`, `BrokerUnsupported` in the file.
The word "scaffold" appears **exactly once** — the class docstring at `:344` — contradicted by the
2000 lines beneath it. That single stale line is where "the broker is a STUB"
(`SESSION.md:8739`) comes from. The true half of that sentence is headline 2.

### 2. THE CAPSTONE — the Limiter and broker-order are not wired to each other. At all.

Verified directly, not inferred:
- `limiterd.py` (258 KB, the daemon that went green) imports **no broker module**.
- All 34 `scripts/nixrisk/*` modules import **no broker module** — 17 hits, every one a docstring.
- `broker_order_ibkr` is imported by **two test files and nothing else**.
- The Limiter declares its own shadow ports (`flatten.py:211`, `fills.py:331`, `outcomes.py:177`)
  and `flatten.py:212-213` **asserts** `BrokerOrderPort` "structurally satisfies" them.
  **Nothing proves that sentence** — a proxy where a property belongs (directive 1).

Producer proven in isolation against a `FakeIB`. Consumer proven in isolation against hand-rolled
test brokers. The two halves share only `Position`/`Balance` types and prose. **No instrument in the
tree spans the seam. Twelve open Limiter debt rows resolve against this one missing transport.**

Per memory #22 I am sizing it now rather than discovering it later: **B12 is a 3–5 arc build.
Module 1's I1 took a 6-arc capstone for the same shape of gap.**

### 3. The module is at ARC-020 maturity; gate pressure on it is ~zero

`broker_order_ibkr.py` unchanged for **336 commits**. Every `scripts/broker/*.py` blob is
**byte-identical to HEAD** (the `Aug 22` mtimes are touches, not edits). Of 103 checks, **one** names
a broker-order artifact for an order-side property — and its subject is a **config file**.
`gate_coverage_baseline.json` has `artifacts: {}` and **no broker path in `rows` or `exclusions`**.

---

## THE REGISTER — B1..B13

**Numbered B, not I, deliberately.** Module 1's `I1..I12` are live and cited by number everywhere; a
second `I4` collides the way `SPEC-A<n>`/`CHECK-A<n>` did before ARC 028 forced the prefixes apart.
**Architect ruling requested** — the ULTRAREVIEW's arc titles will carry these numbers.

| status | n | invariants |
|---|---|---|
| MET+PROVEN at the producer | 6 | B3 ack-never-fill · B4 idempotent fills · B8 query authority/never-resend · B9 session transitions · B10 reject taxonomy · B11 seam declares absence (**= SPEC-A3, PENDING v1.4**) |
| MET, instrument or gate owed | 4 | B1 seam identity · B2 no vendor type crosses · B6 non-blocking send · B7 order/datafeed disjointness |
| MET+PROVEN+GATED | 1 | B13 config-as-data — the module's **only** gated surface |
| NOT MET, venue-gated, correctly declared | 1 | **B5 monotonic-by-source** |
| NOT MET — **THE CAPSTONE** | 1 | **B12 the seam is wired** |

**B5 is the honest red and it is not a defect.** `venue_seq_ts` is written with `time.time()`
(`:1472`, `:2218`) and **never compared**; `on_margin` **never fires** (GAP-3, `pushes_margin=False`).
IBKR supplies no venue timestamp, so the adapter sets `ts_is_venue_sourced=False` and reports V27
CANNOT-MEASURE **rather than falsely green**. Unsatisfiable on IBKR by venue fact. Provable only at
Tradovate, whose user-sync websocket carries a real sequence.

**The brief predicted the "met-in-code, gate the proof" pattern would recur because broker-order is
thin. It recurs — but the module is THICK (5.3k lines) and unusually well-proven at the producer.
What is missing is not proof of production; it is any proof that production reaches a consumer.**

---

## TWO FINDINGS THE AUDIT WOULD OTHERWISE INHERIT SILENTLY

1. **`_tombstones` has no eviction path** (NEW). Written at `:811`, read at three sites, **never
   popped or cleared**; `_clear_session_state` clears eleven structures and pointedly not this one
   (correct — a tombstone must survive the boundary). Its docstring claims supersession by a
   consumer; **no supersession code exists and no public method releases one.** Bounded per
   boundary, unbounded across many. Unlike `_mirror_stale`, **not named in-file as open.**
2. **Two documented defects pass their own test unconditionally.** `test_broker_order.py:3090`
   (F-A8-2, no ordering guard on `net_qty`) and `:3128` (F-A8-1, `Balance` fields meaning different
   things per writer — "a confident lie" against §14) are `record()` calls that always pass while
   documenting unrepaired defects. **An arc that greens the suite has not repaired them.**

---

## ⚠ THE MARGIN-REGIME DELTA FAILS ITS OWN TREE-CONFORMANCE CHECK

The delta calls the regime blackout *"the only genuinely new concept"* and lists the normal-intraday
reference as a piece to build. **The comparison is already written** — `nixrisk/blackout.py:888-915`:
`:891` is M1's reference · `:894` the live figure · `:908-910`
`ceiling = baseline.level * (1.0 + margin_elevated_pct)` is M2 + M5's tolerance band · `:896-905`
absent ⇒ blackout, citing check-contract §17, is M3's fail-closed. The knob exists at
`risks/limiter.config.json:23`.

**Against the tree the new build reduces to three items, none of which is the comparison:** a real
**producer** for `margin_per_contract` (D3.381) · the onset **detector** (D3.470) · **§12A
ratification** of `margin_elevated_pct`.

⇒ **Do not ratify M1–M5 as worded** — it would book already-written code as new work. The delta asked
for exactly this check at `:111` and fails it. Its unification of D3.480 with itself is sound and
should be kept: **one margin-validity check, three outcomes.**

**Spelling mismatch, worth a row:** §2A spells the field `venue_seq_ts`;
`grep -rn venue_seq_ts scripts/nixrisk/` returns **zero** — the Limiter spells it `venue_ts`
(`survival.py:184`) and `source_seq` (`freshness.py:465-470`). D3.121 already records that its two
guards *"cannot bind on the real wire"*.

---

## PROPOSED ULTRAREVIEW SEQUENCE (honest sizing)

| arc | subject | size |
|---|---|---|
| **M2-A** | Register ratification + cheap instruments: B1's **superset check, empty-roster vacuity guard, and a signature/arity comparison — none exists in the tree today**; move B2/B6 proofs from tests to registered checks; re-measure suspected-stale D1.17 / D1.31 / D1.22 | SMALL, 1 arc |
| **M2-B** | The §13-obj-11 stalled-socket re-measurement gate (the measurement lives in a **docstring**; §13 calls this objective *critical*) | SMALL-MED, **⚠ SPIKE FIRST** |
| **M2-C** | **THE CAPSTONE** — the transport layer: D3.468 status writer, D3.446 completions writer, D3.449 IOC remainder send, a production construction site. Closes I1's entry half | **LARGE, 3–5 arcs** |
| **M2-D** | Margin field-set producer + the unified three-outcome margin-validity check | MED, 2 arcs |
| **M2-E** | Bounded state + residual findings (`_tombstones`, T8/T15, D1.29/D1.30) | MED, 1–2 arcs |
| **M2-F** | Tradovate adapter — **B1 and B5 become provable for the first time at N=2** | venue-gated, Stage 1 |

**Three spikes flagged.** The stalled-socket harness · **the transport shape** — `limiterd.py:2104-2111`
argues for the directory on *narrowest-surface* grounds while D3.468's discharge says it becomes
*"an adapter rather than a directory reader"*; **these point in opposite directions and want an
architect ruling before M2-C is briefed** · the instrument table D3.480 needs, absent from `risks/`.

---

## IBKR PAPER-ONLY — AND SIM-VALIDATION ALREADY DOES NOT DEPEND ON IT

`dev_and_services_plan.md:97-98`, `:246-248`: IBKR permanently paper-only Stage 0; Tradovate demo
Stage 1-2, **live from Stage 3** (micros), Stage 4 (minis); the two vendor cutovers are independent
gates (R6). **The no-live-session property is already held and must be protected, not built:**
`StubBrokerOrder` implements all nine verbs with no vendor import and no socket; `seam_simulate.py`
is fully offline; the real adapter is driven against a `FakeIB`. **All 36 broker tests ran green with
no IBKR session** (`36 passed in 0.60s`; basetemp outside `~/nix`).

Seam identity is **partly** testable offline today: add B1's superset check + vacuity guard and the
*nominal* half of §2A invariant 1 becomes a real cross-vendor gate needing no venue. Behavioural
identity needs Tradovate. **B5 must not be scheduled against IBKR at all.**

---

## THE HONEST PREDICTION

M2-A/B/E are audit-shaped and will move the badge quickly, because the module is already well built.
**They will also mislead if reported alone: greening eleven of thirteen while B12 stands means the
module is proven to produce correctly into nothing. Module 2 must not be badged green on any set
that excludes B12.**

---

## OBLIGATIONS

**READ-ONLY CONFIRMED** — no tracked code change; every `scripts/broker/*.py` worktree blob
byte-identical to its HEAD blob. **Module 1 re-measured ONCE: `97 | 4 | 2 | 0`, exit 1.**
**Push state: `origin/main == HEAD` before this arc — the green Module 1 was already pushed
(0 unpushed commits). Memory #21's standing risk was NOT live at ARC 059's start.**
**Waypoint deviation disclosed:** total fixed at 8 at kickoff, never moved; the four parallel
sub-agents ran as sub-steps 2.1–2.4 inside stage 2 rather than as four stages (the denominator would
have been 11). The never-moves-mid-run rule is the stronger one, so the deviation is recorded.
