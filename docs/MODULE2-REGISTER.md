# MODULE 2 (broker-order) — THE INVARIANT REGISTER B1..B13

**Status: RATIFIED, ARC 060 (M2-A). This is Module 2's charter.**
Derived by the ARC 059 read-only recon (`downloads/broker_order_recon.md`), ratified here by
architect ruling. Every subsequent Module-2 arc **binds to a B-invariant by number**; an arc that
cannot name the B-row it moves is not a Module-2 arc.

Module 1 (the Limiter) is GREEN and is not re-opened by anything in this document.

---

## 0. THE NAMING RULING — why `B<n>` and not `I<n>`

The ARC 059 brief asked for "its I1..In". The recon used **B1..B13 instead, and the architect
ratified that choice.** Module 1's `I1..I12` are live and cited by number in `sessions/SESSION.md`,
`docs/CHECK-DEBT.md`, gate names and test names. **A second `I4` meaning something else would
collide in every document the way `SPEC-A<n>` and `CHECK-A<n>` collided before ARC 028 forced the
prefixes apart** — and that collision was not hypothetical: a bare "AMENDMENT 6" named two
different rulings in two ledgers.

So: **`I<n>` is Module 1's namespace (the Limiter). `B<n>` is Module 2's namespace
(broker-order).** Cite the prefix always; a bare number is ambiguous across modules.

Where a B-invariant PAIRS with a Limiter invariant, that is stated in the row and the pairing is a
producer/consumer relationship, not an alias: **broker-order PRODUCES what the Limiter CONSUMES.**
B3 pairs I4, B5 pairs I12, B6 pairs I3/I9. The pairing is the whole reason B12 exists.

---

## 1. STATUS VOCABULARY

| status | means |
|---|---|
| **MET+PROVEN** | property holds in code AND a can-fail instrument drives it **at the producer** |
| **MET, GATE OWED** | holds in code; the only proof is a test rather than a registered check, or the proof is a **docstring measurement nothing re-runs** |
| **MET+PROVEN+GATED** | holds, proven, and driven by a registered `verify.py` gate |
| **NOT MET (VENUE-GATED)** | cannot hold on the current venue; correctly declared unmet; provable only elsewhere |
| **NOT MET** | real build owed |

**A docstring measurement is not an instrument.** Core directives 1–2 (prove real properties;
prefer direct measurement over inference) mean a measured number recorded in a comment that nothing
re-runs is evidence about a tree that no longer exists. Moving such a proof into a registered gate
is real work and gets its own arc slice — that is exactly what ARC 060 did for B1/B2/B6.

---

## 2. THE REGISTER

Spec citations resolve against **`docs/nics_risk_subsystem_spec_v1.3.md`** (the frozen, still-cited
authority). `v1.4` is the ARC 027 mechanical fold and **must not be cited yet** — the fold inserts
lines, so every `§x:line` coordinate below the first insertion moves (CHECK-DEBT D3.33).

Evidence citations of the form `broker_seam.py:1813` resolve against the tree at ARC 059's HEAD and
are reproduced from `downloads/broker_order_recon.md`, which holds the full evidence for each row.
**This table is the charter; the recon is the evidence; the live verdict is `verify.py`.** Where
they disagree, the live measurement wins (core directive 5).

| # | invariant (testable property) | spec citation | status at ratification | gate |
|---|---|---|---|---|
| **B1** | **Seam identity across vendors.** Every adapter claiming `BrokerOrderPort` exposes *exactly* the nine `ORDER_PORT_VERBS` — no fewer **and no more** — with the declared sync/async partition and matching signatures; every sink exposes exactly the seven `ORDER_EVENTS`. | §2A:103-104 (inv. 1); V25 | MET (IBKR side), **INSTRUMENT INCOMPLETE** | `check_broker_seam_identity` (ARC 060) — **IBKR-side signature conformance only** |
| **B2** | **No vendor type crosses the line.** No type, id, or payload originating in the vendor SDK appears above §2A; all identifiers are neutral. | §2A:104-105 (inv. 2) | MET+PROVEN, gate owed | `check_no_vendor_type_leak` (ARC 060) |
| **B3** | **ack-never-fill.** `place_order` yields no fill information; the ack is a separate event and *always precedes* any fill or cancel for that order. | §2A:65-66; pairs Limiter **I4** | MET+PROVEN (producer) | — (consumer half is B12) |
| **B4** | **Idempotent execution.** `on_fill` deduped by `(client_order_id, exec_id)`; partials arrive as successive events carrying the venue's cumulative qty; dedup state is bounded. | §2A:76-77; §4:214 | MET+PROVEN, one unbounded structure (`_tombstones` has no eviction path) | — |
| **B5** | **Monotonic-by-source.** `on_balance`/`on_margin` carry a **venue**-sourced timestamp, and a late or duplicate push is **discarded**, per key. | §2A:106-107 (inv. 4); §6.4b:398-404; V27; pairs Limiter **I12** | **NOT MET — VENUE-GATED. SEE §3.** | — (unsatisfiable on IBKR) |
| **B6** | **Non-blocking send; `flatten` must not block.** No send verb blocks the caller under any socket condition. | §2A:107 (inv. 5); **§13 obj 11 (line 904, "critical")**; pairs Limiter **I3/I9** | MET+MEASURED, re-measure owed | `check_nonblocking_send` (ARC 060) |
| **B7** | **Order/datafeed disjointness.** No shared object between the order and datafeed contracts, so a datafeed fault cannot reach the order path. | §2A:105-106 (inv. 3); V24 | MET at the object level; 3 residuals (D1.37, D3.8, `PORT_ASYNC_VERBS`) | — (V24 proper needs a process split that does not exist) |
| **B8** | **Query authority + never-auto-resend.** `query_positions`/`query_balance` are venue reads and are cold-start ground truth; `query_order_status` is a local read that issues no send, ever. | §2A:69-71; §4 | MET+PROVEN, **transport owed (D3.468)** | never-resend gated by `check_order_path_bans` |
| **B9** | **Session transitions.** `on_session` fires on transitions only, from one site, and never announces an UP-class state over a session the adapter knows is dead. | §2A:84 | MET+PROVEN (producer) | — (`UP_DATA_LOSS` covered by SPEC-A3) |
| **B10** | **Rejection taxonomy is neutral and evidence-gated.** Every rejection carries a neutral category; a category may be added only with a citation to something measured on this system. | §2A:75; D1.18 (discharged ARC 018) | MET+PROVEN, **one row deep** (table has exactly one entry, 201) | — (useful expansion is Tradovate's) |
| **B11** | **The seam declares absence; it never substitutes a value for one.** Where the venue cannot satisfy a contract path, the adapter declares it machine-readably rather than degrading silently. | **SPEC-A3** (`docs/SPEC-AMENDMENTS.md:155`) — *"a sixth invariant alongside the five at §2A:103-107"*, **status PENDING v1.4, architect-owned** | MET+PROVEN | — (owed by the architect: ratify SPEC-A3 into v1.4) |
| **B12** | **THE SEAM IS WIRED.** The Limiter's narrowed ports are *proven* structurally satisfied by the frozen §2A port/sink, and something in production constructs an adapter and hands it to the Limiter. | §2A:62-84; §14 *"Nothing reaches broker-order without passing the Limiter"*; V25 | **NOT MET — NOT EVEN DECLARED. THE CAPSTONE. SEE §3.** | — |
| **B13** | **Config is data, boot-validated, restart-only.** Every knob loads from JSON with no defaults; cross-knob ordering is validated before use; a bad or absent config is a loud failure, never a degrade. | §12A:830; §12.11 lifecycle | **MET+PROVEN+GATED** | `check_broker_order_config` |

---

## 3. THE TWO ROWS NO FUTURE ARC MAY MISTAKE FOR OWED-NOW WORK

This section exists because both rows read as "NOT MET", and a future arc scanning the status column
for red would pick them up as the next thing to build. **Neither is.**

### B5 — NOT MET, and NOT FIXABLE HERE. It is VENUE-GATED.

`venue_seq_ts` is written with **`time.time()`** (`broker_order_ibkr.py:1472`, `:2218`) and is
**never compared anywhere** — no guard, no high-water mark. Both sites already flag
`ts_is_venue_sourced=False`; `capabilities.venue_sourced_balance_ts=False`; and
`unmet_contract_paths()` emits *"on_balance venue_seq_ts — V27 not honestly satisfiable"*.

**The declaration is CORRECT and the refusal to fabricate a venue timestamp is the right call.**
IBKR does not supply a per-key venue sequence. An arc that "fixes" B5 on IBKR can only do so by
inventing a timestamp, which is the precise failure B11 exists to prevent — it would convert an
honest declared absence into a confident lie.

Compounding it: **§2A's PRIMARY margin path has no producer at all — `on_margin` never fires**
(D3.381). And the field is spelled three different ways across the tree — §2A says `venue_seq_ts`,
`nixrisk/survival.py:184` says `venue_ts`, `nixrisk/freshness.py:465-470` says `source_seq` — so
the monotonic guards **cannot bind on the real wire** even once a producer exists (D3.121).

**B5 discharges at Tradovate, not before.** Owed before then: nothing in broker-order. Owed by the
venue cutover: the producer, the field-name reconciliation, and only then the guard.

### B12 — NOT MET, and it is THE CAPSTONE. 3–5 arcs, not one.

**`limiterd.py` and all of `scripts/nixrisk/` import NO broker module.** The real adapter is
imported by **two test files only**. `nixrisk/flatten.py:212-213` *asserts* structural satisfaction
with **no instrument behind the assertion**.

The size of B12 is not one wiring commit. **Twelve Limiter-owned debt rows are all waiting on the
same missing transport layer:** D3.352, D3.468, D3.446, D3.449, D3.350, D3.381, D3.121, D3.480,
D3.470, D3.371/D3.479, D3.469, D3.358.

**THE BADGE RULE THAT FOLLOWS FROM B12, and it is binding:**
> **Module 2 MUST NOT be badged green on any set of invariants that excludes B12.**
> A module proven to produce correctly **into nothing** is not green. broker-order is unusually
> well-proven *at the producer* — six MET+PROVEN rows — and that is precisely the trap: every one
> of those proofs is a statement about production that no consumer has ever received.

---

## 4. WHAT ARC 060 (M2-A) DISCHARGED — THE CHEAP SET, AND ONLY THAT

ARC 060 moved **three** invariants from test-only or docstring-only proofs to **registered
`verify.py` gates**. It modified **no** broker-order subject file: it GATES the module, it does not
change it. Every `scripts/broker/*` and `risks/broker_order.config.json` path was proven
byte-identical with `git hash-object` across the arc.

| invariant | before ARC 060 | after ARC 060 |
|---|---|---|
| **B1** | roster conformance checked by `broker_seam.check_structural_conformance`, which reports **missing only** — superset-blind, no vacuity guard, and **no signature/arity comparison existed anywhere in the tree** | `check_broker_seam_identity`: exact set equality (no fewer **and no more**), signature/arity match **derived by shape** from the Protocol, a real-class vacuity guard, and CANNOT_MEASURE on any verb it cannot classify |
| **B2** | proven by `test_broker_order.py` only — a test, not a registered gate | `check_no_vendor_type_leak` |
| **B6** | measured once, and **the measurement lived in a docstring that nothing re-ran** | `check_nonblocking_send` |

**B1's scope fence, stated so no later arc over-reads it:** ARC 060 discharges B1 **for the IBKR
signature only**. *Identity ACROSS vendors is not provable with N=1 adapter* — it needs a second
real adapter to compare against, which is **M2-F (the venue cutover)**. The gate proves the IBKR
adapter conforms to the declared seam; it does not and cannot prove the seam is vendor-neutral in
the sense §2A:103-104 finally requires.

**ARC 060 did NOT touch B12 or B5.** The badge stays **RED**.

---

## 5. HOW A MODULE-2 ARC BINDS TO THIS REGISTER

1. Name the **B-number(s)** the arc moves, in the brief and in the commit subject.
2. State the **status transition** being attempted (e.g. `MET, GATE OWED` → `MET+PROVEN+GATED`).
3. If the arc ships a gate, the gate is **bound from a demonstrated FAIL** and carries the
   check-contract rule-4 plant-both control — a gate that has never failed proves nothing.
4. If the arc changes a subject file, it says so; if it only gates, it proves the subject
   **byte-identical** with `git hash-object`.
5. Update this table's status column **in the same arc that moves the invariant** — a charter whose
   status column lags is the moving-anchor failure (`debug.md` §8 #4).

**This table's status column is a RATIFICATION-TIME snapshot maintained by rule 5 above. It is not
the live verdict.** The live verdict is `verify.py` over `checks/registry.json`, and the live debt
is `docs/CHECK-DEBT.md`. Where this document and a measurement disagree, **the measurement wins**
(core directive 5) and this document is the thing that gets corrected.
