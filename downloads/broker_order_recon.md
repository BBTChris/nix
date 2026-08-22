# ARC 059 — MODULE 2 (broker-order) OPENING RECON

**TIER = RECON (read-only).** No code change, no invariant flip, no badge move. Module 1 stays GREEN
(12/12) and untouched. This document is the **charter for Module 2's ULTRAREVIEW**.

**Predecessor DERIVED, not assumed:** the brief said `≈ ARC 058's write-back`; `git rev-parse HEAD` =
**`13952451ef6ca55d70b3635487f9634c95fa2e3a`** (`1395245`, "ARC 058: the post-write-back re-measure —
97|4|2|0"). Everything below is measured against that tree.

**Interpreter** `.venv/bin/python` → Python 3.14.4. **`ib_async 2.1.0` is installed and importable.**

**Method.** Four read-only sub-agents (2.1 seam · 2.2 IBKR adapter · 2.3 tests/checks · 2.4
debts/consumers) plus direct verification by cc of every load-bearing claim. Where a claim is an
agent's and cc did not re-measure it, it is marked **UNVERIFIED**. Evidence is `file:line` and
`git hash-object`, never assertion.

---

## 0. THE HEADLINE — three findings, in order of consequence

**1. The brief's own framing is wrong in the module's favour, and wrong in a way that matters.**
broker-order is **not a scaffold**. `broker_order_ibkr.py` is a 2361-line adapter over a real,
installed `ib_async 2.1.0`, with every one of §2A's nine verbs carrying a real body: zero
`NotImplementedError`, zero `TODO`, zero `pass  #`, zero `BrokerUnsupported` in the whole file. The
word "scaffold" appears **exactly once** — the class docstring at `broker_order_ibkr.py:344`
(`"""§2A broker-order, IBKR scaffold."""`) — and it is contradicted by the 2000 lines beneath it.
That one stale line is the source of "the broker is a STUB" as carried in `sessions/SESSION.md:8739`.
*What is true* in that sentence is the second finding, not the first.

**2. THE CAPSTONE — the Limiter and broker-order are not wired to each other. At all.**
Verified by cc directly:

```
$ grep -rn '^\s*\(from\|import\).*\(broker_seam\|broker_order\)' scripts/nixrisk/   →  EMPTY
$ grep -n  '^\s*\(import\|from\) .*broker'  scripts/limiterd.py                     →  EMPTY
$ grep -rn '^\s*\(from broker_order_ibkr\|import broker_order_ibkr\)' --include=*.py .
    scripts/tests/test_broker_tier3.py:199
    scripts/tests/test_broker_order.py:88
    scripts/tests/test_broker_order.py:768
```

`limiterd.py` (258 KB, the daemon that went green) imports **no broker module**. Every one of the 34
`scripts/nixrisk/*` modules imports **no broker module** — all 17 hits are docstring citations. The
real IBKR adapter is imported by **two test files and nothing else**. The Limiter instead declares
its own narrowed shadow ports — `nixrisk/flatten.py:211 BrokerFlattenPort`, `nixrisk/fills.py:331
CancelPort`, `nixrisk/outcomes.py:177 StatusQueryPort` — and `flatten.py:212-213` *asserts* that
"`broker_seam.py`'s `BrokerOrderPort` … structurally satisfies this narrower port."
**Nothing anywhere proves that sentence.** It is a proxy standing where a property belongs
(directive 1). The producer is proven in isolation against a `FakeIB`; the consumer is proven in
isolation against hand-rolled test brokers; the two halves share only value-object *types*
(`Position`, `Balance`) and prose.

This is Module 2's exact analogue of Module 1's daemon-vs-library gap. **Per memory #22 — size the
hard piece up front — I am naming it now: B12 is the capstone, and it is a multi-arc build, not an
audit finding.** It is already half-recorded as `CHECK-DEBT.md:861` (D3.352: *"I1 … has NO
instrument, and its ENTRY half has no subject: there is no `place_order` call site in
`scripts/nixrisk/` at all"*).

**3. The module has almost no gate pressure on it.** Of 103 checks in `checks/`, exactly **one**
names a broker-order artifact as a SUBJECT for an order-side property
(`check_broker_order_config`, `registry.json:27`), and its subject is a **config file**, not
behaviour. `checks/gate_coverage_baseline.json` has `artifacts: {}` — verified by cc — and its
`exclusions` map holds eight `scripts/nixverify/*` paths and **no broker path in either bucket**.
The coverage ratchet exerts **zero** pressure on `scripts/broker/*`. What real proof exists lives in
two *test* files, not gates.

---

## TASK 1 — THE CODE-STATE SURVEY

### 1.1 The artifacts, with hashes (all byte-identical to HEAD)

| path | lines | `git hash-object` | last commit touching it |
|---|---|---|---|
| `scripts/broker/broker_seam.py` | 2641 | `cfedc5face75c8780d473bbec4f4ee44ef48953e` | `3e9a0ea` ARC 023 (2026-08-11) |
| `scripts/broker/broker_order_ibkr.py` | 2361 | `e669feb9c69585f955302d0fbb5901f486d32804` | `e7fb0b0` **ARC 020** (2026-08-11) |
| `scripts/broker/broker_order_config.py` | 253 | `4e6f2f22d5fea3dbe0757c61d97c36df4d6eac31` | `618d45e` ARC 028 D (2026-08-12) |
| `scripts/broker/seam_simulate.py` | 653 | `d8a50abdd903135c1019b5cfba576bceeff8ed0f` | `7ce54b9` ARC 022 |
| `scripts/broker/ibkr_mapping.py` | 369 | `26ecd8c2c8b94da567d66b8ab280b9d6e0764fef` | `7ce54b9` ARC 022 |
| `scripts/broker/broker_datafeed_ibkr.py` | 1872 | `1755800e862dff9dc1ea2d4e3508fc5671d331c0` | `3e9a0ea` ARC 023 |

**Every worktree blob equals its HEAD blob** (cc verified each with `git rev-parse HEAD:<path>`), so
the file mtimes of `Aug 22 00:36` are touches, not edits — a real risk to note, because an mtime
reads as recency and this module's true recency is ARC 020.

**`broker_order_ibkr.py` has not changed in 336 commits** (`git rev-list --count e7fb0b0..HEAD`).
Arcs 021–058 were Limiter, datafeed and check work. **Module 2's code is at ARC-020-era maturity
while its consumer went through 38 further arcs.** That asymmetry is the single best predictor of
where the ULTRAREVIEW will find drift.

### 1.2 EXISTS and is genuinely exercised — at the producer

Driven by two instruments, both against the **real** `IBKRBrokerOrder` with a `FakeIB` standing in
for the vendor SDK (the fake replaces *ib_async*, not the adapter — so the adapter is the subject):

- `scripts/tests/test_broker_order.py` — 3401 lines, hash `f33cb546ed894cdc1d624aeb03f53e6d6af9a774`.
  **One** collectable pytest function (`:3375`) driving 23 `_section_*` coroutines and
  **190 `record()` properties**.
- `scripts/tests/test_broker_tier3.py` — 1988 lines, hash `4e0ec0ccaa1b4f2efab17c1a930e70ca3cb48278`,
  **23 pytest functions**, 111 asserts, all producer-side.

Measured now by cc (basetemp outside `~/nix` per memory — the tree-copying tests fill the disk):

```
$ .venv/bin/python -m pytest scripts/tests/test_broker_order.py scripts/tests/test_broker_tier3.py \
    scripts/tests/test_seam_simulate.py scripts/tests/test_check_broker_order_config.py \
    -q --no-header -p no:cacheprovider --basetemp=/tmp/claude-1000/arc059-pytest
36 passed in 0.60s
```

Genuinely exercised, with the strongest evidence in the module — **five permanently re-planted
historical defects**, which is the only class of evidence that proves a suite *has been seen to
fail*: the ARC 014 `avg_price` unit bug (`test_broker_order.py:2638`), a partial-fill double-count
and a cancel-discards-filled-portion defect (`:2594`, `:2601`), the await divergence
(`:527`), and a banned-retry-import plant recorded in `gate_coverage_baseline.json:59`
(exit 0 → exit 1 naming `'<file>:<line> <mod>: banned retry library'`).

By surface: **ack/fill two-phase** (`:1864-1894`, §2c parameterised — ack precedes fill, exactly one
ack, synthesised acks carry provenance) · **fill idempotency** (`:622` dup emits nothing, `:630` a
distinct exec still delivered — dedupe is not a black hole) · **flatten** (`:642` fires without
querying the venue, `:1416` continues past a failing symbol and names it) · **session** (`:2730`
AST-proves `on_session` has exactly ONE emission site, `:2781` no UP-class state over a known-dead
session) · **startup ownership gate** (`:1716-1830`) · **reject taxonomy neutrality** (`:892`,
`:944`, `:957` — no structured field contains a digit) · **zero-qty position filtering** (`:1538`) ·
**query_order_status three outcomes** (`:3250`).

### 1.3 EXISTS but is unproven **at the broker-order level**

The distinction the brief asked for, and it separates cleanly into three classes:

**(a) Proven about the Limiter's CONSUMPTION, with broker behaviour authored by the test.** In
`test_flatten.py`, `test_exit_integration.py`, `test_session_flatten.py`, `test_realized_pnl.py`,
only the **value objects** `Balance, Position` are imported from `broker_seam`; each file defines its
own broker. `test_flatten.py:98-107` says so outright: *"Deliberately NOT `StubBrokerOrder`: this
suite's whole subject is that broker truth AFTER a flatten differs from the pre-flatten
projection."* **If `broker_order_ibkr.py`'s `flatten` were replaced with `pass`, every one of these
still passes.** These prove nothing about broker-order.

**(b) Proven about the seam's DECLARATIONS, about neither side.** `test_seam_simulate.py` and
`seam_simulate.py` (653 lines, 44 `record()` properties) — cc verified that
`grep 'broker_order_ibkr\|IBKRBrokerOrder' scripts/broker/seam_simulate.py` returns **nothing**.
Its subjects are `broker_seam.py`'s own doubles (`StubBrokerOrder`, `HollowBrokerOrder`,
`AwaitDivergentBrokerOrder`) and `ibkr_mapping.py`'s refusing skeleton. It proves the port
declaration is well-formed and that the conformance checkers can fail. It proves **nothing** about
production behaviour. It needs no venue and is offline.

**(c) The Limiter's own gate-wall proof, where the broker is the observable surface.**
`test_arc038_a_gate_wall.py:22-25` is honest about it: *"**The subject is a double.**"*
`StubBrokerOrder` is the fixture; the Limiter's gate wall is the subject.

**Consequence, stated plainly:** *nothing in the tree tests that the Limiter correctly consumes what
`broker_order_ibkr.py` actually produces.* There is no instrument spanning the seam.

### 1.4 UNBUILT — the specific gaps

The file marks nothing with `TODO`/`NotImplementedError`. The owed work is named in prose, which is
better discipline and worse discoverability. Exhaustively:

**Structurally impossible on IBKR, declared machine-readably rather than faked** (`CAPABILITIES` at
`broker_order_ibkr.py:346-351`, surfaced by `BrokerCapabilities.unmet_contract_paths()` at
`broker_seam.py:347`):

| gap | line | consequence |
|---|---|---|
| GAP-1 no native flatten | `:13-16` | `native_flatten=False`; composed from a live mirror + opposing MKT |
| GAP-2 no venue balance timestamp | `:18-21` | `venue_sourced_balance_ts=False`; **§2A invariant 4 / V27 unsatisfiable — reported CANNOT-MEASURE, never falsely green** |
| GAP-3 no per-contract margin push | `:22-25` | `pushes_margin=False`; **`on_margin` never fires from this adapter** — cc verified `sink.on_margin` has zero call sites |
| GAP-4 no realtime ticks | `:27-28` | datafeed's concern |

**Deferred to the consumer that did not exist** (`:138-141`, verbatim): *"the Limiter's
pending-timeout state machine, any consumer of the flatten attempt record, any reconciliation of
intent against venue outcome, and any bounded-queue policy."* Plus `_mirror_stale` has **no
consumer** (`:409-425`) and `last_flatten_attempt` has **no consumer half** (`:1349-1355`).

**Deliberately not built, with the reason** — the sender thread (`:66-71`), any retry on the order
path (`:86-98`), the §4 market-tradable guard inside `flatten` (`:1118-1121`, correctly the
Limiter's), auto-refire on flatten expiry (`:1194-1197`).

**One growth path with no bound, and it is a NEW finding.** `_tombstones` (`:482`) is written at
`:811` and read at `:1039`, `:1100`, `:1499` — and cc verified it is **never popped, discarded, or
cleared anywhere in the file**. `_clear_session_state` (`:834-848`) clears eleven structures and
pointedly not this one — which is *correct*, since a tombstone's whole purpose is to survive the
boundary. The docstring (`:792-795`) claims it "is superseded the moment a consumer resolves the
order" — **no supersession code exists, and no public method releases a tombstone.** Bounded per
boundary; unbounded across many. Unlike `_mirror_stale` this is **not** named as an open item
in-file. It is adjacent to two recorded findings — `test_broker_tier3.py:1307` (T8, cid never
released) and `:1892` (T15, per-order state never released).

### 1.5 A caution about `ibkr_mapping.py`

It is a **paper artifact, not an adapter** — *"NOT AN IMPLEMENTATION. No ib_async import, no
network"* (`:1-15`). Its `IBKROrderAdapter` raises on every verb by design. It is imported only by
`seam_simulate.py` (`:556`, `:628`). The real adapter deliberately does **not** import it
(`broker_datafeed_ibkr.py:39-43`: *"is READ, never imported"*). It hosts **both** order and datafeed
skeletons in one module, which `CHECK-DEBT.md:500` (D2.19) records as corrupting debt attribution
for both libraries. **Do not let an ULTRAREVIEW arc mistake it for the adapter.**

---

## TASK 2 — THE INVARIANT REGISTER (THE CHARTER)

### Naming decision, flagged for the architect

The brief says "its I1..In". **I have used B1..B13 instead.** Module 1's `I1..I12` are live and cited
by number in `SESSION.md`, `CHECK-DEBT.md`, gates and test names; a second `I4` meaning something
else would collide in every document the way `SPEC-A<n>`/`CHECK-A<n>` collided before ARC 028 forced
the prefixes apart. If the architect prefers `I<n>`, the mapping is positional and trivial — but
please rule, because the ULTRAREVIEW's arc titles will carry these numbers.

### Status vocabulary

- **MET+PROVEN** — property holds in code AND a can-fail instrument drives it at the producer.
- **MET, GATE OWED** — holds in code; the only proof is a test, not a registered check, or the
  proof is a docstring measurement nothing re-runs.
- **NOT MET (VENUE-GATED)** — cannot hold on IBKR; correctly declared unmet; provable only on
  Tradovate.
- **OWED** — real build.

### The register

| # | invariant (testable property) | spec citation | status | evidence / what is owed |
|---|---|---|---|---|
| **B1** | **Seam identity across vendors.** Every adapter claiming `BrokerOrderPort` exposes *exactly* the nine `ORDER_PORT_VERBS` — no fewer **and no more** — with the declared sync/async partition; every sink exposes exactly the seven `ORDER_EVENTS`. | §2A:103-104 (inv. 1); V25 | **MET, INSTRUMENT INCOMPLETE** | Rosters `broker_seam.py:1813` / `:1825` / `:1884`; the roster is declared the authority over docstrings (`:1809-1812`). IBKR adapter passes both checks (`test_broker_order.py:496`, `:509`). **Owed:** (a) `check_structural_conformance` (`:2285`) reports *missing* only — **superset-blind**, so an adapter with ten extra vendor verbs passes, and "identical" is unprovable; (b) it has **no empty-roster vacuity guard**, unlike `check_await_conformance` (`:2445-2451`) — an emptied roster returns a clean pass over nothing; (c) **no signature/arity comparison exists anywhere in the tree** (no `inspect` in the function; cc verified); (d) **N=1 real adapter** — identity across vendors is not provable until a second exists. |
| **B2** | **No vendor type crosses the line.** No type, id, or payload originating in the vendor SDK appears above §2A; all identifiers are neutral. | §2A:104-105 (inv. 2) | **MET+PROVEN, GATE OWED** | `broker_seam.py` imports stdlib only (`:57-61`); `ClientOrderId/ExecId/Symbol = str` (`:293-295`) with the comment *"a vendor int id (IBKR orderId) must be mapped, never leaked"*; the vendor `Trade` is retained internally and never returned (`broker_order_ibkr.py:1069`, `:1077`); `_Tombstone` deliberately holds no ib `Order`, no ib `Trade`, no vendor id (`:299-314`). Proven: no `RejectCategory` name/value and no structured field contains a digit (`test_broker_order.py:892`, `:944`, `:957`). D1.18 discharged ARC 018. **One declared hole:** `on_ack.reason` deliberately keeps the venue's own code+text (`broker_seam.py:1528-1530`) — ratified in prose, **carried by no ledger row**. **Owed:** the proof is a test, not a registered gate. |
| **B3** | **ack-never-fill.** `place_order` yields no fill information; the ack is a separate event and *always precedes* any fill or cancel for that order. | §2A:65-66; pairs Limiter **I4** | **MET+PROVEN (producer)** | `place_order(self, order) -> None` with **zero `return` statements** (`:1026-1081`). Ordering is explicit: `_ensure_acked` (`:1687`) synthesises the ack first so *"the Limiter can never observe a fill or a cancel before the ack"* (`:1673-1677`). Proven `:1864-1894`, `:1910`, and per-order under interleaving (`test_broker_tier3.py:1382`). **The producer half is the strongest item in the register.** **Owed:** the consumer half — the Limiter has **no `on_ack` handler** (`nixrisk/completions.py:33-34`, `:160-167`). |
| **B4** | **Idempotent execution.** `on_fill` deduped by `(client_order_id, exec_id)`; partials arrive as successive events carrying the venue's cumulative qty; dedup state is bounded. | §2A:76-77; §4:214 | **MET+PROVEN, one unbounded structure** | `_seen_execs: set[tuple[ClientOrderId, ExecId]]` keyed on the **neutral** id (`:399`); guard at `:1931-1935` sits *before* ack synthesis so a replay cannot re-trigger it; `cum = int(fill.execution.cumQty)` (`:1947`) emitted at `:1979`. Bounded two ways: retention-window eviction (`:1824-1825`) and session clear (`:841`), with the window boot-validated to outlast both §4 timeouts (`broker_order_config.py:165-176`). Proven `:622`/`:630` + two re-planted defects. **Owed:** `_tombstones` has **no eviction path** (§1.4 above) — a NEW finding. |
| **B5** | **Monotonic-by-source.** `on_balance`/`on_margin` carry a **venue**-sourced timestamp, and a late or duplicate push is **discarded**, per key. | §2A:106-107 (inv. 4); **§6.4b:398-404** ("required"); V27; pairs Limiter **I12** | **NOT MET (VENUE-GATED) — correctly declared** | `venue_seq_ts` is written with **`time.time()`** at `:1472` and `:2218` and **never compared anywhere** (cc verified: no guard, no high-water mark). Both sites flag `ts_is_venue_sourced=False`; `capabilities.venue_sourced_balance_ts=False` (`:348`); `unmet_contract_paths()` emits *"on_balance venue_seq_ts — V27 not honestly satisfiable"* (`broker_seam.py:351-352`). **`on_margin` never fires at all** (GAP-3) — §2A's *primary* margin path has no producer. The refusal to fabricate is the right call (`broker_seam.py:477-486`). **This is the register's honest red, and it is not fixable on IBKR.** |
| **B6** | **Non-blocking send; `flatten` must not block.** No send verb blocks the caller under any socket condition. | §2A:107 (inv. 5); **§13 obj 11 (line 904, "critical")**; pairs Limiter **I3/I9** | **MET+MEASURED, RE-MEASURE OWED** | No thread, no queue, no lock, no `sleep` in the adapter — **deliberately** (`:66-71`): asyncio's transport and `ib_async.Client._msgQ` already buffer, and a Nix thread would be a third queue in one pipe. Measured matrix (`:53-64`) across healthy / silent-peer / full-buffer / peer-vanished: **worst cell 0.003295 s**. `flatten` reads `_mirror` from memory (`:1214`), never the wire; fan-out max 0.00889 s at N=20 (`:1130-1134`). **Owed:** (a) **the measurement lives in a docstring and no gate re-runs it** — a comment is not an instrument (directives 1–2), and §13 obj 11 is the one objective the spec calls *critical*; (b) the honest limit is stated in-file (`:1565-1568`): 200 `place_order` into a saturated pipe returned in 0.032 s with **zero bytes delivered**. **Non-blocking ≠ delivered**, and D1.22 (*a send verb cannot tell the caller whether the order reached the venue*) is **narrowed by ARC 020 A7, not discharged**. |
| **B7** | **Order/datafeed disjointness.** No shared object between the order and datafeed contracts, so a datafeed fault cannot reach the order path. | §2A:105-106 (inv. 3); V24 | **MET at the object level; 3 residuals** | Separate `Protocol`s, no shared base (`:1517`, `:1581`, `:1657`, `:1721`); separate capability objects with a **deliberately duplicated** helper rather than a shared one (`:427-430`); no lock, queue or runtime global shared. Proven `seam_simulate.py:519-544`; per-port lookup asserted by `is` identity (`test_broker_datafeed.py:1475`). **Residuals:** (i) `PORT_ASYNC_VERBS` (`:1900`) is a module-level **mutable dict keyed by both ports** — declaration-layer only, read solely by the conformance harness (`:2311`), never on a hot path, but it is an **unflagged exception** to the rule `:369-375` states; (ii) `BrokerCapabilities.realtime_ticks` (`:341`) is an ORDER-side declaration of a DATAFEED fact — self-flagged `:376-380`, **D1.37**; (iii) shared *type* definitions (`Symbol`, `BrokerSeamError` subclasses). **V24 proper — separate processes on separate cores, kill the feed under load — is UNPROVEN: no process split exists.** |
| **B8** | **Query authority + never-auto-resend.** `query_positions`/`query_balance` are venue reads and are cold-start ground truth; `query_order_status` is a local read that issues no send, ever. | §2A:69-71; §4 | **MET+PROVEN, TRANSPORT OWED** | `reqPositionsAsync` (`:1405`) with the zero-qty filter (`:1419-1420`, a real measured defect — IBKR emits `position=0` as a *no-longer-held* notification and the idiom `if await query_positions(): halt()` would see a phantom), a stale-read seq guard (`:1429-1439`) and a fills-landed-in-flight guard (`:1446-1453`). `accountSummaryAsync` (`:1458`). `query_order_status` (`:1498-1520`) makes **no venue call of any kind** and returns §4's three outcomes incl. `indeterminate`. Never-resend is **structural, not policy**: tombstoned ids refused (`:1050-1055`, `:1102-1108`), flatten expiry *discarded not refired* (`:1292-1293`), `disconnect` attempted exactly once (`:989`), and retry libraries are **banned by a registered gate** (`check_order_path_bans`, `registry.json:168`). **Owed: D3.468 — the answer has no transport** (below). |
| **B9** | **Session transitions.** `on_session` fires on transitions only, from one site, and never announces an UP-class state over a session the adapter knows is dead. | §2A:84 | **MET+PROVEN (producer)** | Single choke point `_publish_session` (`:850-907`) — **AST-proven** to be the only emission site in `scripts/broker/` (`test_broker_order.py:2730`, `:2736`). Two fail-closed rules at `:884-905`. Four cooperating state fields incl. a monotonic `_session_seq` epoch (`:477`), so a dead session's in-flight reconcile cannot publish over a new one (`:2157`; proven `test_broker_tier3.py:1605`). `UP_DATA_LOSS` is a declared Nix addition covered by **SPEC-A3**. **Owed:** consumer half absent; and **D1.17 (one `disconnect()` emits TWO DOWN events, measured live ARC 016) reads OPEN but predates the `:884-905` non-transition suppression — it is very likely stale. RE-MEASURE, do not assume either way.** |
| **B10** | **Rejection taxonomy is neutral and evidence-gated.** Every rejection carries a neutral category; a category may be added only with a citation to something measured on this system. | §2A:75; D1.18 (discharged ARC 018) | **MET+PROVEN, ONE ROW DEEP** | `ib_reject_category` (`:329-340`), first-rule-wins, unmatched ⇒ `UNKNOWN` *"never the nearest plausible member"*. Gated by construction: every code in `IB_REJECT_RULES` must appear in `IB_REJECT_EVIDENCE` and a test asserts it (`:252-255`). Pairing `reject_category is None iff ACCEPTED` is mechanically enforced (`broker_seam.py:194-212`) and asserted both ways (`test_broker_order.py:988`-`:1005`). **The honest limit, stated in-file (`:256-258`): the table has exactly ONE entry (201), and three of four categories have no mapped code — *"That is the finding, not a placeholder."*** Expansion is venue-time-gated, and since IBKR is paper-only forever, the useful expansion is **Tradovate's**. |
| **B11** | **The seam declares absence; it never substitutes a value for one.** Where the venue cannot satisfy a contract path, the adapter declares it machine-readably rather than degrading silently. | **SPEC-A3** (`docs/SPEC-AMENDMENTS.md:155`) — *"a sixth invariant alongside the five at §2A:103-107"*, **status PENDING v1.4, architect-owned** | **MET+PROVEN** | `BrokerCapabilities` (`broker_seam.py:320`) + `unmet_contract_paths()` (`:347`); four gaps declared (`broker_order_ibkr.py:346-351`), asserted at `test_broker_order.py:500`. `ibkr_mapping.py` raises `BrokerUnsupported` rather than degrading (`:285-291`). `get_margin` **raises** on timeout rather than returning a stale figure (`:1544-1548`). `SendBacklog.measured` enforces a cannot-measure-is-not-zero floor (`:1620`). **This is the module's best design property and it is the mechanism that makes invariant 1 survivable** — a vendor that *cannot* satisfy a path declares it instead of lying. **Owed: nothing in code. Owed by the architect: ratify SPEC-A3 into v1.4.** |
| **B12** | **THE SEAM IS WIRED.** The Limiter's narrowed ports are *proven* structurally satisfied by the frozen §2A port/sink, and something in production constructs an adapter and hands it to the Limiter. | §2A:62-84; §14 *"Nothing reaches broker-order without passing the Limiter"*; V25 | **NOT MET — NOT EVEN DECLARED. ⇒ THE CAPSTONE** | Verified by cc: `limiterd.py` and all of `scripts/nixrisk/` import **no broker module**; the real adapter is imported by **two test files only**. `nixrisk/flatten.py:212-213` *asserts* structural satisfaction with **no instrument**. `CHECK-DEBT.md:861` (D3.352): I1's entry half *"has no subject: there is no `place_order` call site in `scripts/nixrisk/` at all."* Also unwired: `on_ack`/`on_position`/`on_balance`/`on_margin`/`on_session` are declared and unhandled (`completions.py:33-34`, `:160-167`); `fills.py:133-135` states *"`LimiterFillSink` is **NOT** a complete `OrderEventSink`, and it must not be presented as one."* **Multi-arc build. See Task 4 sizing.** |
| **B13** | **Config is data, boot-validated, restart-only.** Every knob loads from JSON with no defaults; cross-knob ordering is validated before use; a bad or absent config is a loud failure, never a degrade. | §12A:830; §12.11 lifecycle | **MET+PROVEN+GATED** — the **only** gated broker-order surface | `BrokerOrderConfig` (`broker_order_config.py:98-127`), five fields, **no defaults** (`:48-49`); validation runs inside `__post_init__` so *"construction and validation are one motion"* (`:46`); four `BOOT_RULE_IDS` (`:86-91`); `BrokerConfigError` — *"Never degraded to defaults"* (`:94-95`). The two Limiter-owned knobs are **read from `risks/limiter.config.json`, never restated** (`:74-79`) — directive 3 honoured mechanically. Gated by `check_broker_order_config` (`registry.json:27`) with 8 tests incl. **four rule-naming can-fails** (`test_check_broker_order_config.py:82`, `:98`, `:119`, `:159`). **Owed:** D1.31 (the config restates two Limiter-owned §12A knobs) reads OPEN — but `:74-79` appears to have *fixed* it in ARC 028. **RE-MEASURE; likely stale.** |

### Register summary

| status | count | invariants |
|---|---|---|
| MET+PROVEN at the producer | 6 | B3, B4, B8, B9, B10, B11 |
| MET, instrument or gate owed | 4 | B1, B2, B6, B7 |
| MET+PROVEN+GATED | 1 | B13 |
| NOT MET, venue-gated (correctly declared) | 1 | B5 |
| NOT MET — the capstone | 1 | **B12** |

**The brief predicted the "met-in-code, gate the proof" pattern would recur heavily because
broker-order is thin. It does — but the reason is not thinness.** broker-order is *thick* (5.3k
lines of adapter + seam) and unusually well-proven **at the producer**. What is missing is not
proof of production; it is **any proof that production reaches a consumer**. That is one invariant
(B12), not eleven, and it is worth more than the other twelve combined.

---

## TASK 3 — THE INHERITED DEBT MAP

### 3.1 D3.468 — the pending-timeout status directory has no producer

**Maps to B8** (query authority) as a **transport build**, not an audit.

`CHECK-DEBT.md:967`, module `limiter`, owner **unassigned**, OPEN. The reader is not in `nixrisk/`
— it is `limiterd.py:2166 DirectoryStatusQuery`, reading `DIR/status/<id>.json` (`:2197-2222`), wired
at `:4703` and polled by `PendingTimeoutPoller` (`:2243`) at `:4825`. The row's own words: *"the poll
runs every tick, queries every overdue order, and will answer `unknown` forever until something
writes those files."*

**broker-order already produces the correct answer** — `query_order_status` (`:1476-1520`) returns
§4's three outcomes with no venue call and no resend. **What is owed is the pipe, not the logic.**
The row names the discharge: *"the vendor-integration arc that gives `scripts/broker`'s adapter a
place to publish `query_order_status` answers into, at which point this class becomes an adapter
rather than a directory reader."*

Its twin: **D3.446** — `DIR/completions/` has the same shape; the §5:323 sender that would write exec
reports does not exist. The row explicitly expects **one arc to discharge both**. Add **D3.449** (the
§4 IOC remainder cancel is *recorded and never sent*, `nixrisk/fills.py:499`) — three symptoms of one
missing transport layer.

⇒ **These three are one build: the Limiter↔broker-order transport. It is B12's first arc.**

### 3.2 D3.480 — not-tradable deny-at-approval

**Maps to B12** (the wiring) plus a **new margin-validity check**; it is *not* a broker-order-internal
invariant.

`CHECK-DEBT.md:979`, owner **unassigned**, OPEN. Spec basis is real and plural: §3:128 (*fast-drop
guard: symbol absent from margin cache ⇒ not-tradable*), §4:198, §7:483, §15 C3:990.

The gap is exactly locatable:
- **At approval** the Limiter reads `order.margin_per_contract` **off the proposal**
  (`nixrisk/gate.py:503`) and only rejects a non-positive/non-finite *number*
  (`:510`, `:1063`). It **never asks the published margin cache whether the symbol is present.**
  (And D3.382 records that the `<= 0.0` guard at `:403-414` lets a **NaN** through.)
- **At the origin write** the absent case *is* caught — `nixrisk/positions.py:543-553` raises
  `UntradableSymbol` — but by then the fill is ingested and the only remedy is a flatten, which is
  a venue round trip and a realized cost.

⇒ broker-order owes **the margin field set itself**: nothing feeds `FinancialPicture.margin_per_contract`
(`nixrisk/seam.py:446`) today — **D3.381**. Until a producer exists, the deny cannot be written
against anything.

### 3.3 The margin-regime delta — ⚠ **the delta's central claim does not survive contact with the tree**

`downloads/broker_order_margin_regime_delta.md` is explicitly **"PROPOSAL / captured design intent"**
(`:1-4`), to be ratified at Module 2 planning, and it closes by asking for exactly this check:
*"Confirm against the tree at that module's recon (tree-conformance unverified here)"* (`:111`).
Doing so:

The delta says the regime blackout is *"the only genuinely new concept"* (`:7-9`) and lists the
normal-intraday reference as a piece to build (`:64`). **The comparison is already written.**
cc verified `scripts/nixrisk/blackout.py:888-915`:

- `:891` `baseline = self._effective_baseline(symbol, state)` — that **is** M1's reference;
- `:894` `live = self._picture.current().margin_per_contract.get(symbol)` — the live figure;
- `:908-910` `ceiling = baseline.level * (1.0 + self._knobs.margin_elevated_pct)` /
  `if live > ceiling:` — that **is** M2 plus M5's tolerance band;
- `:896-905` `live is None` ⇒ **blackout**, citing check-contract §17 — that **is** M3's fail-closed;
- the knob exists: `risks/limiter.config.json:23 "margin_elevated_pct": 0.1`, self-documented at
  `:60` as *"NOT a §12A knob, and its absence is a finding rather than an omission"* — so **M1's
  §12A ratification is genuinely owed**;
- the reference cache exists: `nixrisk/calendar_seam.py:352 MarginBaseline` / `:427
  MarginBaselineReadPort`, produced by `nixrisk/pollers.py MarginPoller`.

**Against the tree the delta's new build reduces to three items, none of which is the comparison:**
1. a **real producer** for live `margin_per_contract` — broker-order's `on_margin`/`get_margin`
   (**B5**; today `on_margin` never fires and nothing feeds the picture — **D3.381**);
2. a real producer for the **onset transition** — `BlackoutEvaluator` (**D3.470**);
3. **ratify** `margin_elevated_pct` and the baseline source into §12A.

The delta's own unification of D3.480 with itself is sound and should be kept: **one margin-validity
check, three outcomes — absent ⇒ not-tradable (D3.480) · elevated ⇒ blackout (this delta) ·
present & normal ⇒ tradable, size per §3** (`:84-94`). Its scope fence (*"No Limiter re-open"*,
`:100-104`) holds: all three items are producer-side.

**Recommendation: do not ratify M1–M5 as worded.** Re-word against `blackout.py:888-968` first, or
the ratification will book already-written code as new work.

**One more mismatch, worth a row.** §2A and the delta both spell the field **`venue_seq_ts`**.
`grep -rn 'venue_seq_ts' scripts/nixrisk/` returns **zero**; the Limiter spells it `venue_ts`
(`survival.py:184`) and `source_seq` (`freshness.py:465-470`). Two guards exist Limiter-side
(`survival.py:516-528`, `freshness.py:435-470`) and **D3.121** records that they *"cannot bind on the
real wire"* because the published picture carries no per-key venue timestamp. A seam whose two sides
spell its key differently is a defect waiting for the first integration arc.

### 3.4 The venue cutover

| fact | source |
|---|---|
| **IBKR is permanently paper-only Stage 0** | `dev_and_services_plan.md:97-98`, restated `:246-248` |
| Tradovate demo at **Stage 1–2**; Tradovate **live from Stage 3** (micros), Stage 4 (minis) | `:182-198` |
| The two vendor cutovers (datafeed, broker) are **independent gates** per arc R6 | `:182-198`; §12B:886-889 |
| Stage 0 **is** for plumbing: connection handling, reconnect, session recovery, order-lifecycle mechanics against a paper account | `:115-118` |
| Stage 0 **forbids**: latency measurements of any kind, fill realism, slippage, strategy performance, any claim about edge | `:104-113` |
| The binding seam constraint: *"the vendor-neutral interface must encode no assumption that holds only for a delayed or polled feed … is a Stage 0 artifact leaking into a permanent interface, and is a defect"* | `:137-140` |
| `clientId 1` is **reserved for the live Risk Engine process — "not yet built; connect nothing else on 1"** | `:174-180` |
| MES margin 3,503.59 · ES 35,035.87 · net liq 20,344.34 ⇒ **MES is the Stage-0 instrument** | `:146-161` |

**What is scaffold-only vs what a real adapter owes.** The IBKR adapter is *not* scaffold-only — it
is a complete Stage-0 adapter whose four declared gaps are venue facts, not omissions. **A real
Tradovate adapter owes exactly the nine verbs and seven events, plus the two things IBKR cannot
give: a genuine `venue_seq_ts` on balance/margin (which its user-sync websocket does carry —
`broker_seam.py:477-486`) and a live `on_margin` push.** Those two are precisely B5, so **B5 flips
from NOT MET to provable at the Tradovate arc and not before.**

**Is seam identity testable without a live venue? Partly, and that is the actionable answer.**
- **Testable offline now:** structural + await conformance against any adapter object, including a
  refusing skeleton (`seam_simulate.py:567-570` already does this against
  `ibkr_mapping.IBKROrderAdapter`). Add the superset check and the vacuity guard from B1 and the
  *nominal* half of invariant 1 becomes a real cross-vendor gate that needs no venue.
- **Not testable offline:** that a Tradovate adapter's verbs *behave* identically. That needs a
  Tradovate demo session (Stage 1).
- **Critically: sim-validation must not depend on a live IBKR session, and today it does not.**
  `StubBrokerOrder` (`broker_seam.py:1929`) implements all nine verbs with no vendor import and no
  socket — *"prove the contract is satisfiable without a venue, so seam tests don't need IBKR up"*
  (`:1924-1925`). `seam_simulate.py` is fully offline. `test_broker_order.py`/`test_broker_tier3.py`
  drive the real adapter against a `FakeIB`. **All 36 tests above ran with no IBKR session.** This
  property is already held and must be protected, not built.

### 3.5 The complete broker-facing debt map

**Producer-side rows (`owning module` = broker-order/seam), mapped to the register:**

| row | subject | → |
|---|---|---|
| D1.17 | one `disconnect()` emits TWO `on_session(DOWN)` | **B9** — likely stale, RE-MEASURE |
| D1.19 | ack provenance (venue vs synthesised) carried only as free text | **B3** |
| D1.20 | `_mirror_stale` latches across a successful reconnect | **B8** (consumer half ⇒ B12) |
| D1.22 | a send verb cannot tell the caller the order reached the venue | **B6** — narrowed ARC 020 A7, **not discharged** |
| D1.27 | two `flatten()` sequences have no specified correct behaviour — **SPEC GAP, not a code defect** | **B6** — needs an architect ruling |
| D1.28 | the protective path cannot report it failed its purpose | **B6/B12** — adapter half done, consumer half untouched |
| D1.29 | `Balance.cash`/`maint_margin`/`init_margin` mean different things per writer | **B2/B11** — *"a confident lie"* against §14, recorded at `test_broker_order.py:3128` as **F-A8-1** |
| D1.30 | no ordering guard between `positionEvent` and fill-derived `net_qty` | **B4/B5** — recorded as **F-A8-2** (`:3090`); needs a venue sequence IBKR does not supply |
| D1.31 | config restates two Limiter-owned §12A knobs | **B13** — likely stale (ARC 028), RE-MEASURE |
| D1.37 | `realtime_ticks` / `realtime_tick_stream` are two spellings of one fact | **B7** |
| D3.8 | `RecordingSink.sequence` cross-stream ordering observable | **B7** |
| D2.19 | `ibkr_mapping.py`'s shared basename corrupts debt attribution for both libraries | §1.5 |
| *discharged* | D1.15 (ARC 016) · D1.18 (018) · D1.23, D1.24, D1.25, D1.26 (020) | — |

**Limiter-owned rows blocking on a broker-order producer — the producer-vs-consumer gap proper.**
All map to **B12**: D3.352 (I1 has no instrument, entry half has no subject) · D3.468 (status
directory) · D3.446 (completions directory) · D3.449 (IOC remainder never sent) · D3.350 (nothing
re-attempts a refused cancel) · D3.381 (`BrokerTruth` carries one unlabelled balance; nothing feeds
the financial picture) · D3.121 (no per-key venue timestamp ⇒ §6.4b cannot bind on the real wire) ·
D3.480 (deny-at-approval) · D3.470 (onset dispatched, not detected) · D3.371/D3.479 (`on_fill`
carries neither a side nor a source timestamp; the Limiter invents both — `fills.py:818`, `:863-874`)
· D3.469 (`OrderStatus` has 4 fields, `on_fill` needs 6) · D3.358 (three of six declared terminal
paths have zero production release sites).

**Twelve Limiter rows are waiting on one missing transport layer.** That is the real size of B12,
and it is why it is the capstone rather than an arc.

---

## TASK 4 — THE PROPOSED ULTRAREVIEW SEQUENCE + HONEST SIZING

### 4.1 The authority-first ordering principle

Module 1's audit began without a map and paid for it (memory #22). The map now says: **broker-order's
producer surface is largely proven; its consumer seam does not exist.** So the ordering is *not*
"audit everything, then build". It is: **cheap instruments first to convert MET→PROVEN and to make
the register measurable; then the one real build; then the venue-gated remainder.**

### 4.2 The sequence

| arc | subject | invariants | size (basis) | notes |
|---|---|---|---|---|
| **M2-A** | **Register ratification + the cheap instruments.** Land B1's three missing controls (superset check, empty-roster vacuity guard, and a signature/arity comparison — none exists in the tree today); put B2 and B6 behind *registered checks* rather than tests; re-measure the three suspected-stale rows (D1.17, D1.31, and D1.22's narrowing). | B1, B2, B6, B9, B13 | **SMALL — 1 arc.** Basis: the instruments are ~200 lines against a well-factored roster; the plants already exist as `HollowBrokerOrder`/`AwaitDivergentBrokerOrder`. | Should also add `scripts/broker/*` rows to `gate_coverage_baseline.json`, which today exerts **zero** pressure on the module. |
| **M2-B** | **The §13-obj-11 re-measurement gate.** Turn `broker_order_ibkr.py:53-64`'s docstring measurement into an instrument that re-runs: the four socket conditions, the flatten fan-out, and the absorbed-not-blocked finding (`:1565-1568`). | B6 (+ Limiter I3/I9 pairing) | **SMALL-MEDIUM — 1 arc, but SPIKE FIRST.** ⚠ | **FLAGGED FOR A MEASURING SPIKE.** Reproducing "full send buffer" and "peer vanished" deterministically in a gate — as opposed to once, by hand, in ARC 019 — is the unknown. Spike the socket harness before an arc depends on it. §13 calls this objective *critical*. |
| **M2-C** | **THE CAPSTONE — the transport layer.** Give the adapter a place to publish into and the Limiter a dispatcher: the `DIR/status/` writer (D3.468), the `DIR/completions/` writer (D3.446), the IOC remainder send (D3.449), and a production construction site that hands a real port to the Limiter. Closes I1's entry half. | **B12**, B3 (consumer half), B8 | **LARGE — 3–5 arcs. MEASURED, not estimated:** twelve open Limiter debt rows resolve against it (§3.5); the Limiter's four shadow ports must each be reconciled with the frozen §2A port; `limiterd.py` is 258 KB and currently imports no broker module. | ⚠ **Compare to Module 1's I1, which took a 6-arc capstone (ARC 053→058) for the *same shape* of gap.** Do not brief this as one arc. |
| **M2-D** | **The margin field-set producer + the unified margin-validity check.** `on_margin`/`get_margin` feeding `FinancialPicture.margin_per_contract`, with per-key `venue_seq_ts`; then the three-outcome check (absent ⇒ not-tradable · elevated ⇒ blackout · normal ⇒ size per §3). | B5 (partial), D3.480, D3.381, D3.121, the delta | **MEDIUM — 2 arcs.** | **Re-word the delta against `blackout.py:888-968` BEFORE ratifying M1–M5** (§3.3) — the comparison is already built; only the producer, the onset detector (D3.470) and the §12A ratification are new. Resolve the `venue_seq_ts`/`venue_ts`/`source_seq` spelling first. |
| **M2-E** | **Bounded state + the residual findings.** `_tombstones` eviction (new finding, §1.4), T8/T15 unbounded per-order state, D1.29/D1.30 (F-A8-1/F-A8-2, both currently recorded as *passing* `record()` calls that document unrepaired defects), D1.19, D1.20, D1.37, D3.8. | B4, B7, B2 | **MEDIUM — 1–2 arcs.** | Note the trap: `test_broker_order.py:3090` and `:3128` are `record()` calls that **pass unconditionally** while documenting real defects. An arc that greens the suite has not repaired them. |
| **M2-F** | **The Tradovate adapter + seam identity proven at N=2.** The second adapter, then B1's identity claim and B5's monotonic guard become provable for the first time. | B1 (full), **B5 (full)**, B10, V25, V27 | **LARGE — venue-gated, Stage 1.** Not sizeable now. | **Blocks on a Tradovate demo account (`dev_and_services_plan.md:182-198`, Stage 1).** Do not schedule against IBKR: it is paper-only permanently, and B5 is *unsatisfiable* there by venue fact, not by defect. |

### 4.3 Where the gaps sit

- **Producer-vs-consumer** — the dominant gap, and it is **M2-C**. Everything in `scripts/broker/` is
  a producer with no consumer; everything in `scripts/nixrisk/` is a consumer with a hand-rolled
  producer. Both halves are green in isolation. Neither has ever met the other.
- **Daemon-vs-library** — broker-order is a library by *design* (§2:43, in-process in the Risk
  Engine), so this is not the same defect Module 1 had. But it has never been *instantiated by a
  daemon*, which is the same *measurement* problem: nothing proves the construction path works.
  Resolved by M2-C, not separately.
- **Instrument-vs-property** — B1's structural check, B6's docstring measurement, and B12's
  "structurally satisfies" assertion are all proxies where properties belong. M2-A and M2-B.
- **Venue-gated** — B5 and B10 cannot advance on IBKR at all. Say so in the arc briefs so a future
  arc does not burn itself trying.

### 4.4 Pieces wanting a measuring spike before an arc depends on them

1. ⚠ **The stalled-socket harness (M2-B).** Deterministic full-send-buffer and vanished-peer
   conditions inside a gate. Measured once by hand; never automated.
2. ⚠ **The transport shape (M2-C).** Directory-based vs in-process callback. `limiterd.py:2104-2111`
   argues for the directory on *narrowest-surface* grounds; D3.468 says the discharge makes it *"an
   adapter rather than a directory reader."* **These two point in opposite directions and the
   architect should rule before M2-C is briefed.** A spike that wires `StubBrokerOrder` to a live
   `limiterd` end-to-end would settle it cheaply and would also produce the first-ever
   cross-seam instrument.
3. ⚠ **The instrument table (M2-D).** D3.480's discharge needs one and *"there is no instrument
   table in `risks/`"* — the same absence D3.473 and `--tick-size` stand on. Its scope is unmeasured.

### 4.5 The honest prediction

M2-A, M2-B and M2-E are audit-shaped and will move the badge quickly, because the module is already
well-built. **They will also be misleading if reported alone:** greening eleven of thirteen
invariants while B12 stands means the module is proven to produce correctly into nothing.
**Module 2 should not be badged green on any set that excludes B12.**

---

## OBLIGATIONS

**READ-ONLY CONFIRMED.** `git status --short` shows **no tracked change** — the only entries are
untracked files under `downloads/` (this report, the two briefs, an unrelated `.dmg`). Every
`scripts/broker/*.py` worktree blob is byte-identical to its HEAD blob (§1.1). No gate ran in a
mutating mode; the pytest invocation used `--basetemp=/tmp/claude-1000/arc059-pytest`, outside
`~/nix`, per the standing disk-fill lesson.

**Module 1 re-measure:** `verify.py` run once — result recorded in `RESULTS.md` and `SESSION.md`.

**Waypoint deviation, disclosed:** the total stage count was fixed at kickoff as **8** and did not
move. The four parallel sub-agents ran as sub-steps **2.1–2.4** inside stage 2 rather than as four
separate stages. The standing rule counts sub-agents as stages; had I counted them the denominator
would have been 11. I kept the announced denominator because the rule that it *never moves mid-run*
is the stronger one, and I am recording the deviation rather than letting the banner imply a
count I did not use.

**Marked UNVERIFIED (claims cc did not independently re-measure):**
- the 8 CLEAN / 7 FRICTION / 4 GAP split of `ibkr_mapping.FINDINGS` (the total of 19 was verified);
- whether `PORT_ASYNC_VERBS` is ever *mutated* by any consumer (read-only use within
  `broker_seam.py` was verified);
- whether `runtime_gate.py`'s `--testmon` selection actually reaches `test_seam_simulate.py` on a
  given run;
- whether any signature/arity conformance instrument exists outside `scripts/broker/` (searched by
  caller and by roster constant; not exhaustively);
- **D1.17 and D1.31 are asserted *likely stale* on structural grounds only — neither was
  re-measured. Treat both as open until M2-A measures them.**
