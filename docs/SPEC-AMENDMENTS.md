# SPEC-AMENDMENTS — pending amendments to the frozen risk spec

**Status: a RECORD, not an authority.** Nothing in this file is spec text. Every entry below
describes behaviour that Nix implements and that `nics_risk_subsystem_spec_v1.3.md` does not
describe. The frozen spec is **not edited** — that is a standing prohibition, and a v1.4 is an
architect action, not an arc's.

## Why this file exists

Two things were happening in the same place and needed separating:

1. Nix sometimes must implement behaviour the frozen spec is **silent** on. The house answer is a
   **declared Nix addition** — the code declares the extension, flags itself as an addition, and
   leaves the frozen spec the authority for everything it does define. `feed_lag()`,
   `MarketDataMode` and `SessionState.UP_DATA_LOSS` are the existing precedent; see the
   `SessionState` docstring in `scripts/broker/broker_seam.py`, which is the reference form.
2. A declared addition is visible **only** where the code declares it. Nothing collected the set,
   and nothing recorded that the architect owes a decision on each one. That is this file.

## The attribution rule this file obeys (CHECK-DEBT D2.17)

D2.17 exists because an **unattributed** citation is how a task brief's own prohibition once
acquired frozen-spec authority: the reader supplies the missing document. So every entry below
names its origin explicitly — **as an operator ruling, and as the arc that issued it** — and every
section reference names the document it belongs to. A ruling here has the authority of an operator
decision, which is real, and is not the authority of the frozen spec.

*(This paragraph said "an operator ruling issued in ARC 020" until ARC 022. It was written when
ARC 020's two were the only entries and it went stale the moment AMENDMENT 3 landed in ARC 021 —
`debug.md` §7.4's third row, a literal describing the current state of the world sitting inside the
rule that forbids exactly that. The arc is now named per entry, in the table each one carries, which
is the only place it can be right.)*

---

## AMENDMENT 1 — startup admission gate discriminates by ownership, not elapsed time

| field | value |
|---|---|
| origin | **Operator ruling, ratified, issued in ARC 020.** Not spec text. |
| implemented by | ARC 020, sub-agent A (item A4) |
| closes | CHECK-DEBT `D1.27(b)` — opened ARC 019 as a **spec gap**, explicitly not a code defect |
| section that would have to say it | **"Boot / known-state discipline"** in `nics_risk_subsystem_spec_v1.3.md` §4 |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

### Ruling, verbatim as issued

> The startup admission gate discriminates by order ownership, not by elapsed time. Events whose
> `client_order_id` is present in the current session's order registry are admitted regardless of
> startup state; all others are refused. This preserves the gate's purpose — rejecting replayed
> history the session did not originate — while permitting a protective exit issued during session
> re-establishment to be observed. Sound **only** where per-order state is cleared at every session
> boundary; a registry carrying entries from a prior session launders a foreign order into ownership.
>
> Section that would have to say it: **§4 "Boot / known-state discipline"**, which gates registration
> on the cold-start query and is silent on a protective exit during session *re-establishment* —
> exactly when one is most likely.

### What the frozen spec says today

`nics_risk_subsystem_spec_v1.3.md` §4 gates **registration** on the cold-start query. It is silent
on a protective exit issued during session **re-establishment**, which is precisely the moment one
is most likely to be needed. ARC 019 measured the consequence and declined to invent the answer:
the fan-out proceeds, and every ack and fill for those orders is refused by a still-closed gate.
`§14` of the same document is honoured literally — nothing blocked — and not in the sense that
matters, because the outcome is unobservable.

### The dependency that makes it sound, stated as a condition

This ruling is sound **only** while per-order state is cleared at every session boundary. That
clearing is CHECK-DEBT `D1.24`, landed in the same arc and deliberately **before** this item.
A registry carrying entries from a prior session converts a conservative time gate into an
ownership gate that can be fooled. **If D1.24's clearing ever regresses, this amendment regresses
with it** — they are one property, not two.

---

## AMENDMENT 2 — protective `flatten` is idempotent within a bounded window

| field | value |
|---|---|
| origin | **Operator ruling, ratified, issued in ARC 020.** Not spec text. |
| implemented by | ARC 020, sub-agent A (item A6) |
| closes | CHECK-DEBT `D1.27(a)` — opened ARC 019 as a **spec gap**, explicitly not a code defect |
| section that would have to say it | **"Exits (dual authority)"** in `nics_risk_subsystem_spec_v1.3.md` §4 |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

### Ruling, verbatim as issued

> A protective `flatten` is idempotent with respect to in-flight declared intent. When `flatten` is
> invoked for a symbol whose prior flatten intent is still inside its declared window, the second
> invocation emits **no additional orders** and records the suppressed attempt. The window is
> bounded; on expiry the intent is discarded and a subsequent `flatten` emits normally. **The adapter
> never auto-refires on expiry** — re-invocation is the Limiter's, resolved through the
> pending-timeout machinery §4 already specifies.
>
> Rationale, and the asymmetry that decides it: double emission over a `+2` mirror produces `−4` and
> **creates unintended exposure of opposite sign**, which is categorically worse than under-closing.
> Under-closing leaves a position the protective triggers already know about, and §4's six triggers
> are unconditional — they fire again. Permanent idempotency was rejected because D1.22 shows a
> flatten can return normally and never reach the venue; an adapter that refuses to re-flatten
> because it "already did" would refuse to protect. Resolving whether the first flatten arrived needs
> a venue query, which is async, which the protective path must not block on — **so this cannot be
> made safe at the adapter alone.** The window bounds the damage; expiry escalates rather than
> auto-fires.
>
> Section that would have to say it: **§4 "Exits (dual authority)."** §2A's `flatten` bullet defines
> the verb and is silent on repeat invocation; §4's "one in-flight action per strategy" governs
> strategy signals, not Limiter-side protective exits.

### What the frozen spec says today

In `nics_risk_subsystem_spec_v1.3.md`, the §2A `flatten(symbol | all)` bullet defines the verb as
"market-close a position (protective path; must not block)" and is **silent on repeat invocation**.
§4 lists six *independent* protective triggers, unconditional — so two firing in one cycle is a
designed shape, not a caller error. §4's "one in-flight action per strategy" governs strategy
signals, not Limiter-side protective exits. Neither section currently says what two flattens mean.

### What this amendment deliberately does NOT decide

- **It is not a bounded-queue policy.** Where a queue bound sits and what happens at it is a
  Limiter decision, recorded in CHECK-DEBT `D1.22`.
- **It is not a reconciler.** Intent-versus-outcome is the Limiter's; the adapter's attempt record
  (CHECK-DEBT `D1.28`) is a declaration of intent, never a claim about the venue.
- **It does not make the adapter safe alone.** The ruling says so in its own text. The window
  bounds the damage; it does not resolve whether the first flatten arrived. That resolution needs a
  venue query, which is async, which the protective path must not block on.

### The window duration

The duration is a **tunable**, not a literal. `nics_risk_subsystem_spec_v1.3.md` §12A is the
semantic authority for tunables — names, defaults, and cross-knob boot validation — and the
per-module JSON config is the physical layout. A magic number sitting in the protective path is the
stale-anchor problem `debug.md` §7.4 names. The chosen value, its derivation, and its physical
location are recorded by the implementing arc alongside the code, not here.

---

## AMENDMENT 3 — the seam declares absence; it never substitutes a value for one

| field | value |
|---|---|
| origin | **Operator ruling, issued in ARC 021.** Not spec text. |
| implemented by | ARC 021, sub-agent A (items A2–A5) |
| closes | nothing outright. It **generalises** three decisions already landed (`ARC 014` `ts_is_venue_sourced`, `ARC 017` `UP_DATA_LOSS`, `ARC 020` `D1.29`) and it is the standing rule `CHECK-DEBT D1.29` was waiting on — that row's discharge is "a decision about whether the seam distinguishes 'not reported' from 'zero'", and this is that decision |
| section that would have to say it | **"Invariants of the seam"** in `nics_risk_subsystem_spec_v1.3.md` §2A — a sixth invariant alongside the five at §2A:103-107 |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

### Ruling, verbatim as issued

> **The seam declares absence; it never substitutes a value for one.** Where a venue does not report
> a quantity, the seam expresses *not reported* as a state distinct from any value the quantity could
> take. Fabricating a plausible value — zero for an unreported balance, a local clock for a missing
> venue timestamp, a requested mode for an ungranted one — converts an uncertainty the risk system is
> required to act on into a fact it will act on wrongly.
>
> This generalises three existing decisions: `ts_is_venue_sourced=False` (ARC 014, refusing to
> fabricate a venue timestamp on `AccountValue`), `UP_DATA_LOSS` (ARC 017, refusing to let a lossy
> restore read as clean), and D1.29 (ARC 020, "not reported" distinct from zero on `Balance`).
>
> Origin: operator ruling issued in ARC 021. Not spec text. Pending a v1.4 the architect owns.

### What the frozen spec says today

`nics_risk_subsystem_spec_v1.3.md` §2A:103-107 lists five invariants of the seam. Invariant 4 — *"all
timestamps are **venue-sourced** where a monotonic guard depends on them"* — is the closest the frozen
document comes, and it is narrower in both directions: it governs **timestamps only**, and it says
where a value must come **from** without saying what to emit when it comes from **nowhere**. ARC 014
hit that gap on `AccountValue`, which carries no timestamp at all, and had to invent
`ts_is_venue_sourced=False` because §2A gave the absence no home. Every subsequent instance has
re-invented the same answer independently. That is the shape of a missing invariant, not of three
unrelated decisions.

### What it cost in ARC 021, recorded because the ruling is ratified and its cost is not measured

- **Every price-shaped field becomes `float | None`.** `Bar.open/high/low/close/volume`, and
  `on_tick`'s `price` and `size`. Each adds a `None` branch at every consumer arithmetic site.
- **The cost lands on a consumer that does not exist yet** — capture.py's bar builder and the
  Limiter's freshness gate. So the implementing arc paid none of it and the bill is real. This is
  the honest statement of the trade, not an argument against it.
- **`FeedLag.excess_staleness_s()` returns `None` for CANNOT-COMPUTE** rather than a number. That is
  the correct answer and it is one more branch at every call site.
- **`poll_history()` raises on exhaustion instead of returning zero rows.** Zero rows is a real
  answer meaning the venue had nothing; a caller now has to handle an exception on the only
  market-data path Stage 0 has.
- **The cheap half:** three of the four instances that motivated the ruling (`UP_DATA_LOSS`,
  `RejectCategory.UNKNOWN`, `OrderStatus.state='indeterminate'`) were already paid for, and the
  ruling costs nothing to state where an enum already exists. It is expensive exactly where a
  **numeric** field is involved, because a number has no spare member to spend.

### What this amendment deliberately does NOT decide

- **It does not say what a consumer must DO about an absence.** Refuse, halt, degrade, or wait is a
  §4 question and belongs to the Limiter. This ruling governs the seam's expression only.
- **It does not retrofit `Balance`.** `CHECK-DEBT D1.29` remains open: its repair is a seam change
  whose consumer half is R2's, and this ruling tells that repair which direction to go rather than
  performing it.

---

## AMENDMENT 3, REFINEMENT (ARC 022) — an optional field must name an observable absence

| field | value |
|---|---|
| origin | **Operator ruling, issued in ARC 022.** Not spec text. A REFINEMENT of AMENDMENT 3, deliberately not a fourth amendment: it narrows the rule above rather than adding one, and a separate entry would let the two be cited against each other |
| implemented by | ARC 022, sub-agent A (item A3) |
| closes | nothing outright. It pays down AMENDMENT 3's **over-application** in ARC 021 |
| section that would have to say it | the same one AMENDMENT 3 names — **"Invariants of the seam"** in `nics_risk_subsystem_spec_v1.3.md` §2A |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

### Refinement, verbatim as issued

> **AMENDMENT 3, REFINEMENT (ARC 022).** The absence principle applies to facts the venue *can fail
> to report*, not to every field as a matter of course. Where a field's presence is structurally
> guaranteed by the existence of its container — a bar that exists has an open — an optional type is
> noise, and its predictable consequence is consumers writing `or 0.0`, which reintroduces the
> substitution the amendment forbids while wearing a null check.
>
> **Each optional field must be justified by an observable absence**: a case where the venue returns
> the container and omits the field. Fields that cannot be absent are not optional.

### What it changed in the code

ARC 021 read AMENDMENT 3 as "every price-shaped field becomes `float | None`" and said so in this
file. Applied to `Bar`, that made all five payload fields optional. Four of them cannot be absent:
`open`, `high`, `low` and `close` **are** the bar. ARC 022 removed their optionality and made
`broker_datafeed_ibkr._ingest_history` **refuse** a row missing one (`MalformedBarRow`) instead of
reading it with `.get()` and manufacturing a `None` the venue never sent — which was AMENDMENT 3's
own defect, arrived at by applying AMENDMENT 3 too widely.

`Bar.volume` kept its optional, with the observable absence stated at the field: IBKR returns
`BarData.volume = -1` — its own not-reported sentinel — for bar types where volume is not a fact
about the bar. **That absence is IBKR-documented and has NOT been measured on this system**; it is
recorded at `VENDOR_DECLARED` grade and the measurement is owed. Every `| None` on a tick or bar
field in `scripts/broker/` was re-checked against this rule in ARC 022 and each survivor carries its
justification in its own docstring.

**Removing a `| None` that no observable absence justifies is this amendment applied CORRECTLY, and
is not a weakening of it.**

---

## AMENDMENT 4 — the datafeed adapter emits bars only where the venue is the bar's source

| field | value |
|---|---|
| origin | **Operator ruling, issued in ARC 022.** Not spec text. |
| implemented by | ARC 022, sub-agent A (item A2) |
| closes | nothing outright. It **scopes** the `on_bar` / `on_bar_revision` events ARC 021 declared, which arrived without a stated ownership boundary against capture.py |
| section that would have to say it | **§2A's broker-datafeed event declaration** in `nics_risk_subsystem_spec_v1.3.md` (§2A:90-92) |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

### Ruling, verbatim as issued

> The datafeed adapter emits bars **only where the venue is the bar's source.** A bar obtained by
> polling venue history is the adapter's to publish and to seal, because the revision fact — the
> venue returning a different value for a bar already published — is observable only at the poll and
> cannot be reconstructed downstream. **A bar derived by aggregating ticks is `capture.py`'s, and the
> adapter never derives one.**
>
> Rationale: §2A declares two datafeed events and assigns bar construction to capture, on the
> assumption of a real-time tick stream capture aggregates. At Stage 0 that stream does not exist —
> `reqTickByTickData` returns 10189 naming the *product class*, and `reqHistoricalTicks` carries the
> same ~600 s delay — so the bar is a venue primitive, not a derived artefact. Where both a tick
> stream and venue bars exist, the boundary above still holds, and the two sources must not both
> produce the same bar: two components owning one artefact with different provenance is the
> `avg_price` defect at module scale.
>
> Section that would have to say it: §2A's broker-datafeed event declaration.
> Origin: operator ruling issued in ARC 022. Not spec text. Pending a v1.4.

### What the frozen spec says today

`nics_risk_subsystem_spec_v1.3.md` §2A:91: *"`on_tick(symbol, price, size, venue_ts)` — the raw
firehose; capture builds bars, never broker-order."* The sentence assigns bar construction and names
one prohibition, and it is written on the assumption that the firehose exists. ARC 012 measured that
it does not on this account. §2A declares no bar event at all, so it also declares no boundary
between a bar the venue reported and a bar Nix computed — and once ARC 021 had to add `on_bar`,
that boundary had to be drawn by somebody.

### How it is ENFORCED, which is the part that is not documentation

- `broker_seam.BarSource` gained `TICK_AGGREGATED`, a member that **exists only to be refused**. A
  prohibition with no name cannot be tested, and the next author reaching for a tick-derived bar
  would otherwise find nothing at all and add the member without meeting the argument.
- `broker_seam.Bar.__post_init__` raises for any source outside `VENUE_SOURCED_BAR_SOURCES` — the
  technique `BarRevision.__post_init__` already uses against a hollow revision. A tick-aggregated bar
  is **unconstructible**, by the adapter or by anyone else.
- The refusal is an **allowlist, not a blacklist**: a future `BarSource` member added without an
  argument is refused rather than admitted (`CLAUDE.md` directive 4).
- Proof by absence (`debug.md` §7.6) is the other half: `broker_datafeed_ibkr.py` contains exactly
  one `Bar(...)` construction and it is inside `_ingest_history`, on the poll path. A test asserts
  that by AST rather than by driving ticks and observing no bar, because the call-site version would
  pass an adapter that aggregated on a path the test did not drive.
- `BarSource.STREAM_BUILT` was renamed `VENUE_STREAM`. Under this ruling the one distinction the enum
  carries is *did the venue produce these numbers* — and "stream built" reads as the forbidden case
  while meaning the permitted one.

### What this amendment deliberately does NOT decide

- **It does not give capture.py's bar a home at this seam.** capture.py's aggregate is a real and
  necessary artefact; it is built ABOVE the seam from `on_tick` and does not cross it. This ruling
  says the seam `Bar` is not that object.
- **It does not decide what happens when both a tick stream and venue bars exist.** The boundary is
  stated; which source a consumer prefers when it has two is a capture.py question.

---

## AMENDMENT 5 (D1.38) — the broker-datafeed port is async by default

| field | value |
|---|---|
| origin | **Operator ruling, issued in ARC 022.** Not spec text. |
| implemented by | ARC 022, sub-agent A (item A1) |
| closes | the obligation ARC 021 left open in `broker_datafeed_ibkr.py`'s ASYNC SURFACE section — *"the datafeed port has never been argued ... a port change binds every vendor"*. That refusal was correct; this is the ruling it was waiting for |
| section that would have to say it | **§2A's broker-datafeed command declaration** in `nics_risk_subsystem_spec_v1.3.md` (§2A:87-89), which declares four commands and takes no view on awaitability |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

### Ruling, verbatim as issued

> The broker-datafeed port is **async by default**. Verbs that touch the wire — `connect`,
> `disconnect`, `subscribe`, `unsubscribe`, `poll_history` — are coroutine functions. Verbs that read
> retained observables without a round-trip — `feed_lag`, `granted_mode` — are synchronous.
>
> Rationale: the broker-order port's synchronous send path exists solely because a protective action
> must not await (the non-blocking invariant). **The datafeed has no protective path**, so the
> exception that justified sync does not apply to it, and the default inverts. Defaulting async
> prevents ARC 015's defect in mirror image — there, an `async def` passed a sync port because
> `callable()` cannot tell them apart; here, the risk is a sync signature concealing a round-trip.
>
> Origin: operator ruling issued in ARC 022. Not spec text. Pending a v1.4 the architect owns.

### What the frozen spec says today

`nics_risk_subsystem_spec_v1.3.md` §2A:87-89 lists `connect() / disconnect()` and
`subscribe(symbol) / unsubscribe(symbol)` and says nothing about awaitability — for either port. The
order port's split is likewise not spec text: it is ARC 015's operator-ratified decision, defended by
§2A:107 invariant 5 (*the send path is non-blocking regardless of vendor*). This ruling is the same
kind of decision for the second library, and it reaches the opposite default because invariant 5 has
no datafeed counterpart.

### What changed in the code

- `BrokerDatafeedPort` went from **five verbs, all sync** to **seven on a declared split**:
  `poll_history` and `granted_mode` were promoted from adapter-private methods to port verbs, each
  flagged as a Nix addition in its own docstring, and `DATAFEED_PORT_VERBS` grew with them.
- The partition is declared **once per port** — `ORDER_ASYNC_VERBS` and `DATAFEED_ASYNC_VERBS`, bound
  to their Protocols by `PORT_ASYNC_VERBS`. The sync half is derived by subtraction from the roster,
  so no verb name is typed twice.
- `check_await_conformance()` was **extended, not duplicated** (`nix_check_contract.md` check-rule 8).
  It now makes three both-directional comparisons: adapter vs Protocol (ARC 014's), Protocol vs the
  declared partition (new — without it, an unintended Protocol edit silently becomes the new ground
  truth), and roster ⊆ Protocol (new — a roster verb the Protocol did not declare used to be skipped
  silently, which is how `poll_history` sat outside the contract through the whole of ARC 021).
- Two permanent non-vacuity controls were added beside `AwaitDivergentBrokerOrder`:
  `AwaitDivergentBrokerDatafeed` (an async verb implemented sync) and
  `CoroutineDivergentBrokerDatafeed` (a sync verb implemented async — **the direction ARC 015 never
  instrumented**, and the one `debug.md` §7.12 instance 4 records).
- Every datafeed adapter in the tree was converted: `IBKRBrokerDatafeed`, `StubBrokerDatafeed`,
  `HollowBrokerDatafeed`, `ibkr_mapping.IBKRDatafeedAdapter`.

`disconnect` now sits on **opposite sides of the two ports**, and that is the ruling rather than an
oversight: an order-path disconnect can be part of a protective sequence and must not await; a
datafeed disconnect is an ordinary wire teardown.

### What this amendment deliberately does NOT decide

- **It does not bind `connect()` to `ib_async.connectAsync`.** `IBKRBrokerDatafeed.connect` is now
  `async def` and still drives the injected client's synchronous `connect(...)`. No live session ran
  in ARC 022, and swapping a vendor call this file has never executed against the venue would be an
  unmeasured claim. The async signature is what makes that swap a local edit instead of a port change.
- **It does not promote `send_backlog()` to the order port.** That remains a `BrokerCapabilities`
  question for vendor two, per `CHECK-DEBT D1.22`.

---

## Standing note for the architect

Every ruling in this file was issued **because the arc that met the gap refused to invent the
answer** — AMENDMENTS 1 and 2 because ARC 019 refused, AMENDMENT 5 (D1.38) because ARC 021 refused
to change a port that binds every vendor and said so in the adapter's own docstring. That refusal
was correct each time, and it is the reason each ruling arrives here with its rationale intact
rather than as undocumented behaviour discovered later. Each states not only what to do but the
asymmetry that decides it, which is what a v1.4 needs in order to be written without re-deriving the
argument.

*(This paragraph said "Both amendments" until ARC 022, and had been wrong since ARC 021 added a
third. Same failure class as the attribution paragraph above, one section apart: a count of a set
this file grows. It now names the mechanism rather than the number.)*

No amendment here is retroactive. None confers frozen-spec authority on anything in this file. The
frozen spec is **not edited**; a v1.4 is an architect action.
