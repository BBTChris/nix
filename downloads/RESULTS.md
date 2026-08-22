# ARC 061 — B12-1: THE SEAM FOUNDATION — RESULTS

**Tier INTERIOR · Module 2's B12 CAPSTONE, arc 1 of ~4 · predecessor `49e09d0` (derived)**
**broker-order STAYS RED · Module 1 GREEN, unchanged**

---

## 0. WHY THIS ARC EXISTS AS A SEPARATE SLICE

ARC 062's brief (B12-2, the event push) was read first and **stopped at its own TASK 0.** All three
preconditions it required were absent, measured rather than inferred:

| TASK 0 condition | measured |
|---|---|
| one canonical seam module object | **two** distinct objects; `DOWN is DOWN` **False** |
| `limiterd` constructs the real adapter | AST over **36** modules: **zero** broker imports; every `IBKRBrokerOrder(` in **test files** |
| `check_broker_seam_wiring` PASS | the file **did not exist** |

B12-1 had never been banked. Wiring events onto that would have meant inventing a construction site
inside the wrong arc. **This arc lays the foundation.**

---

## 1. MEASUREMENT

| | passed | failed | cannot-measure | skipped |
|---|---|---|---|---|
| ARC 060 closed | 99 | 5 | 2 | 0 |
| **ARC 061 baseline** | **100** | **4** | **2** | **0** |
| **ARC 061 predicted** | **101** | **4** | **2** | **0** |

**The baseline IMPROVED, and ARC 060 wrote down why in advance.** `check_arc_status_contract` now
reads `[ok]` against `arc_060.log`. ARC 060 recorded: *"it returns to PASS in ARC 061, which audits
arc_060.log; this arc's duty was to write that log correctly."* **A forward prediction closed by
measurement.**

---

## 2. D3.485 DISCHARGED — REPRODUCED WITH A CONTROL, THEN FIXED, THEN RE-MEASURED

**The reproduction:** with both `scripts/` and `scripts/broker/` on `sys.path`, the seam loaded as
**two** module objects, `SessionState` was two classes, `DOWN is DOWN` was **False**, and the ARC 016
teardown sequence emitted **TWO** `on_session(DOWN)` events — **D1.17 reappearing with the adapter
entirely innocent.**

**The control is the point:** the identical drive under **one** module object emitted **ONE** DOWN. So
the defect is the **double load**, not the guard — the distinction the row was opened to preserve.

**The fix** lives in `broker_order_ibkr.py` (the one module the production path reaches the seam
through, so the frozen seam is untouched) and canonicalises in **both** directions, because either
spelling can arrive first.

**Re-measured across four `sys.path` shapes × both import orders** — adapter-first with both paths,
package-seam-first, `scripts/` alone, `scripts/broker/` alone: **one module object, `DOWN is DOWN`
TRUE, all eight §2A seam types single class objects, exactly one DOWN — every time.**

### A second instrument agreed, and it was not looked for

The Limiter's first import spelling was the **package** one. `mypy` refused it outright:

> *Source file found twice under different module names: `broker_order_ibkr` and `broker.broker_order_ibkr`*

That is **D3.485 restated by a static analyser.** `limiterd.py` therefore imports the broker library
**flat** behind one named `sys.path` insert, so the tree carries **one module name**, and the adapter's
preamble holds the invariant even for a consumer that picks the other spelling.

---

## 3. THE CONSTRUCTION SITE — PROVEN ON A RUNNING PROCESS

`limiterd.main()` constructs `IBKRBrokerOrder` behind `BrokerOrderPort`. Measured on a live daemon:

```
limiterd exit  : 0 (clean stop)
broker_port    : {"class": "IBKRBrokerOrder", "constructed": true,
                  "connected": false, "unrouted": {}}
sockets to 4002: 0
```

`connected: false` is **structural, not a promise**: `ib=None` leaves the adapter no client to dial
with. Before this arc, `limiterd.py` and all 35 `scripts/nixrisk/*.py` imported **no broker module**,
and `flatten.py:212-213`'s *"structurally satisfies this narrower port"* was a claim with **no
instrument behind it**. It is now proven by a gate that derives the verb set from the Protocol.

---

## 4. NO REGRESSION — MEASURED ON BOTH TREES

An identical `register → reserve → go → on_fill` drive was run against a **clean worktree at
`49e09d0`** and against this tree.

| | result |
|---|---|
| `fills`, `reservations`, `flat` | **exactly equal** on both trees |
| the fill | **delivered** on both; stop arm refused on both |
| the uncertainty flatten | **byte-identical** `unarmable_fill` detail string on both |
| Module 1's 14 invariant gates | **14 / 14 PASS** at the merged tree |
| ARC 060's 3 cheap-set gates | **3 / 3 PASS** |
| frozen paths | **0 of 44 changed** |
| `limiterd.py` | **206 insertions, ZERO deletions** — purely additive |

**An honest correction:** my comparison script first printed *"the only difference is `broker_port`"*.
That was **false** — eleven keys differ. I inspected every one: all are wall-clock timestamps,
runtime-directory paths, OS thread/process ids, or tick counters differing **by one** because the
daemon ran a fraction longer. The corrected claim is narrower and stronger: **the construction changed
no behaviour the daemon records.**

---

## 5. `check_broker_seam_wiring` — THE FIRST CROSS-SEAM GATE

Proves: one seam module object · identity-safe seam types (**50**, derived by shape) · the construction
site (by **calling** it) · port satisfaction (derived from the Protocol, D3.426) · **no live connect**.

**BOUND from four plants, driven on the REAL tree and restored byte-identical:**

| plant | verdict | what it named |
|---|---|---|
| **A** canonicalisation stripped | exit 1 | both module ids, all **50** split seam types, and `DEAD IDENTITY GUARD: … emitted 2 on_session(DOWN) … where §2A permits exactly 1` |
| **B** construction site removed | exit 1 | `NO CONSTRUCTION SITE: scripts/limiterd.py exposes no callable construct_broker_order_port()` |
| **C** a §2A verb renamed away | exit 1 | `UNSATISFIED VERB 'get_margin'` + `NOT A BrokerOrderPort` |
| **D** a socket dial on the construction path | exit 1 | `LIVE CONNECT … socket.socket.connect(('127.0.0.1', 4002))` |

Plants removed → exit 0. Two fail-open holes in the gate's **own first draft** were found by its suite
and closed (a constructor returning `None` scored PASS; a stand-in with no `_ib` scored CANNOT_MEASURE
instead of FAIL).

---

## 6. UNCALLED-RATCHET MOVEMENT — IT RE-FOUND A KNOWN GAP FROM A NEW DIRECTION

**Added:** `scripts/limiterd.py::UnwiredOrderEventSink.on_margin` (`uncalled`, ARC 061).

Measured per event: of the seven §2A sink events, **six have emitters in shipped code and `on_margin`
has ZERO** — `on_ack` 2, `on_fill` 3, `on_cancel` 2, `on_balance` 1, **`on_margin` 0**, `on_position` 3,
`on_session` 3. That is **D3.381 / the ARC 059 recon's GAP-3** (*"`on_margin` never fires at all — §2A's
primary margin path has no producer"*), surfaced independently the moment a **complete**
`OrderEventSink` first existed in production code. It leaves the baseline when a producer exists, not
when B12-2 wires the sinks.

**`IBKRBrokerOrder.connect`/`.disconnect` deliberately did NOT leave the `gate_only` bucket.** This arc
constructs and never connects, so their departure would have signalled this arc's **forbidden act**.

---

## 7. RESIDUAL — EXPLICITLY NOT CLAIMED

* **B12 is NOT discharged.** Events are not wired (B12-2), the directory poll is not replaced (B12-3),
  and the end-to-end seam proof + discharging gate (B12-4) remain. **broker-order stays RED.**
* **No live venue, ever, in this arc.** The adapter is unconnected; the cutover is M2-F. IBKR is
  paper-only permanently.
* **B5 venue-gated**; **D1.31 / D1.22** residuals continue to point at B12; **D3.486 / D3.487** standing.

**Ledger 419 → 418** (one discharged, none opened), read off `derived:ledger_rows`; tally
`broker-order 11 → 10` by the same instrument.

**Module 2 status: B12 — seam canonical + adapter constructed + first cross-seam gate. Event wiring
(B12-2) is next, and its TASK 0 will now pass.**
