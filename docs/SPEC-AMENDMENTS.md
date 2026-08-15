# SPEC-AMENDMENTS — pending amendments to the frozen risk spec

**Status: a RECORD, not an authority.** Nothing in this file is spec text. Every entry below
describes behaviour that Nix implements and that `nics_risk_subsystem_spec_v1.3.md` does not
describe. The frozen spec is **not edited** — that is a standing prohibition, and a v1.4 is an
architect action, not an arc's.

**CITATION FORM: `SPEC-A<n>` (ARC 028 / 0.4, architect ruling).** `SPEC-A3` *is* amendment 3 of
this ledger; the number is unchanged and no entry was renumbered. The prefix exists because
**"AMENDMENT 6" was ambiguous across two documents that each hold six** — this ledger and
`CHECK-CONTRACT-AMENDMENTS.md`, which numbers from 1 independently. A bare "AMENDMENT 6" in a
brief, a debt row or a commit message named two different rulings and nothing on disk could tell
them apart. `scripts/tests/test_amendment_ledgers.py` now enforces the prefix and the
**uniqueness of the number within this ledger** — the defect that made this ruling necessary was
two entries issued as `AMENDMENT 5` in this file at once (ARC 022's D1.38 and per-channel
freshness), which nothing detected until a human read both.

The collision is not confined to amendments. **ARC 028 / 0.3 measured the same shape in arc-brief
section labels**: `§0c` on disk means *"a retrofitted check is a new check"* (ARC 025; live, and
enforced as check-contract rule 9 in `CLAUDE.md`), while `§0c` in the ARC 027 and ARC 028 briefs
means the declaration-only binding classifier, which is **withdrawn**. Two rules, one label, both
cited in this tree. See `CHECK-A7`.

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

## SPEC-A1 — startup admission gate discriminates by ownership, not elapsed time

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

## SPEC-A2 — protective `flatten` is idempotent within a bounded window

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

## SPEC-A3 — the seam declares absence; it never substitutes a value for one

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

## SPEC-A3-REFINEMENT (ARC 022) — an optional field must name an observable absence

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

## SPEC-A4 — the datafeed adapter emits bars only where the venue is the bar's source

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

## SPEC-A5 (D1.38) — the broker-datafeed port is async by default

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

## SPEC-A6 — freshness is per-channel

| field | value |
|---|---|
| origin | **Operator ruling, issued in ARC 023.** Not spec text. |
| implemented by | ARC 023, sub-agent A (item A1) |
| closes | Tier 3 finding **F21** (`scripts/tests/test_datafeed_tier3.py` T20) — the §5.2 fit-for-purpose failure ARC 022 refused to invent an answer for, recording *"NO ANSWER IS INVENTED: whether `bar_start_venue_ts` is a freshness stamp, whether a poll-fed symbol is exempt, and whether the two clocks combine are three different rulings."* This is those three rulings |
| section that would have to say it | **§2A's absent freshness-stamp declaration** and **§6.4:371-374** in `nics_risk_subsystem_spec_v1.3.md` |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

> ⚠ **NUMBERING.** The ruling below was issued titled *"AMENDMENT 5"*. That number was already
> taken, on disk, by ARC 022's `AMENDMENT 5 (D1.38)` — the broker-datafeed async port. It is
> recorded here as **AMENDMENT 6** and the ruling's own text is otherwise verbatim, including
> its self-reference. Two entries sharing a number would let the two be cited against each
> other, which is the failure this file's own AMENDMENT 3 REFINEMENT header names as its reason
> for not being a fourth amendment. Reported to the architect as a deviation.

### Ruling, verbatim as issued

> **AMENDMENT 5 — freshness is per-channel.** Each channel by which the seam observes a symbol
> carries its own venue timestamp and its own `effective_lag_s`. The seam declares **which
> channels are fresh and which are stale**, and does not collapse them into a single boolean.
> Excess staleness is computed per channel by the existing formula,
> `excess_staleness_s = (now − venue_ts) − effective_lag_s`, with the channel's own lag.
>
> The consumer decides which channels it requires. A consumer that requires ticks is entitled to
> halt when the tick channel is stale; the **seam** is not entitled to decide that on its behalf.
>
> Rationale: `evaluate_freshness` reads `last_tick_venue_ts` alone. At Stage 0 no tick stream
> exists — `reqTickByTickData` returns 10189 naming the product class — so a symbol fed entirely
> by successful, current polls is permanently STALE and drives §6.4's halt-and-flatten. **The
> module fail-closes on the only margin-class path it has.** A bar's venue timestamp is a venue
> observation exactly as a tick's is; the defect is that only one channel updates the stamp.
>
> This is Amendment 3's absence principle applied to freshness: the seam reports what it observed
> per channel and substitutes nothing — including not substituting a collapsed verdict for the
> observations that produced it.
>
> Sections that would have to say it: §2A's absent freshness-stamp declaration, and §6.4:371-374.
> Origin: operator ruling issued in ARC 023. Not spec text. Pending a v1.4 the architect owns.

### What the frozen spec says today

`nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 reads *"Allocator/Limiter **read caches only**.
**Stale (freshness stamp past threshold, after retry/backoff) ⇒ halt new entries AND flatten
open.** Detection = system; execution = Limiter."* — **"the freshness stamp"**, singular, on the
assumption that a symbol is observed one way. §2A:86-92 declares four datafeed commands and two
events and no freshness stamp at all, so it declares neither one stamp nor several. AMENDMENT 4
gave the polled bar an owner in ARC 022 and deliberately gave it no freshness role.

### How it is ENFORCED, which is the part that is not documentation

- `broker_seam.FeedChannel` (`TICK` / `POLL`) and `broker_seam.ChannelState`
  (`FRESH` / `STALE` / **`CANNOT_MEASURE`**) are new declared Nix additions.
  `CANNOT_MEASURE` is `debug.md` §7.9's third column made into a value: F21 existed because a
  question that could not be asked read as a feed that had failed.
- `FeedState` is **not** extended. §2A:92 declares `on_feed_status(up|down|stale, …)` and that
  vocabulary is frozen; a fourth member would be a silent redefinition of a locked event.
- `broker_seam.FreshnessReport` carries `fresh_channels` / `stale_channels` /
  `cannot_measure_channels` and **deliberately no `is_fresh`, `is_stale` or `state`**. The
  absence is the enforcement — a boolean there is the collapse the ruling forbids and is the
  property every consumer would reach for first. A test asserts the absence by name.
- `ChannelFreshness.__post_init__` refuses a `state` that contradicts the numbers beside it, so a
  verdict cannot disagree with the `venue_ts` and `effective_lag_s` that produced it.
- `IBKRBrokerDatafeed.freshness()` is the authority and the only publisher; `evaluate_freshness()`
  is retained as §2A:92's single-state summary, derived from the report, documented as not the
  authority.
- **The poll channel's `effective_lag_s` is NOT MEASURED on this system**, and the substitution is
  refused *structurally*: `Stage0LagRecord` carries a `channel`, and the adapter's constructor
  refuses a record installed on a channel it did not measure. Installing the tick channel's
  measured 600.0–601.9 s figure on the poll slot raises. See the deviation note below.

### What this amendment deliberately does NOT decide

- **It does not say which channels a consumer must require.** That is the ruling's own point and
  it is a Limiter question.
- **It does not give the poll channel a lag figure.** None exists; see below.

### DEVIATION REPORTED (ARC 023, sub-agent A) — the poll channel's grade

The brief directed: *"Grade it **VENDOR_DECLARED** with a known-red marker naming the tap, exactly
as `Bar.volume` was graded in ARC 022."* The grade and the marker are implemented exactly as
directed. **A default figure is not**, and the refusal is the amendment applied to itself:

`LagProvenance.VENDOR_DECLARED` requires a real number (`FeedLag.__post_init__` refuses a
provenance for a figure that does not exist), and **no number for this channel exists** —
`IB_STAGE0_DELAYED_LAG` measures the tick stream, ARC 010's 624 s measures `reqHistoricalTicks`
staleness on a different call, and this tree holds no citable IBKR declaration for the history
path. Typing one from memory would be the same substitution sourced from the author instead of
from the tick channel. So `IB_POLL_LAG_RECORD` is `None`, the channel reads `CANNOT_MEASURE`
under its own name, the constructor accepts an operator-supplied figure and grades it
`VENDOR_DECLARED` on arrival without ever promoting it, and the known-red marker names
`~/nix/downloads/tap_session_runbook.md` as the discharge.

**Consequence, stated rather than hidden:** on this system today the §2A:92 summary for a
poll-only symbol is still `STALE`, because no channel can be shown fresh. What changed is that
the report now says *why* — `cannot_measure=['tick','poll']`, not `stale=[…]` — so a consumer can
distinguish an unanswerable question from a failed feed, which is the whole of F21. The
measurement is owed and the amendment names who owes it.

---

## SPEC-A7 — HALT onset is a DISTINCT terminal path, not blackout onset

| field | value |
|---|---|
| origin | **Architect ruling, issued in ARC 029 (brief §0.4).** Not spec text. |
| implemented by | ARC 029, Phase 0.4 |
| closes | CHECK-DEBT **D3.55** — opened ARC 028 (B) as a finding ABOUT THE SPEC and deliberately not absorbed: §3's terminal set named one trigger and §3's own prose named two |
| section that would have to say it | **§3:151-152** (the `released on:` sentence) in `nics_risk_subsystem_spec_v1.3.md`, with **§3:173** as the corroborating prose |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |
| terminal-path additions | `HALT_ONSET` |

### Ruling, verbatim as issued

> **§3:151's terminal set names *blackout-onset cancellation*; §3:173 says *Blackout/**HALT**
> onset*. They are not synonyms in this spec's taxonomy** — Phase A lists the HALT flag separately
> from the blackouts, HALT is §12.5 with six setters, blackouts are §6.1–6.3 and clear on schedule.
>
> **Decisive:** `CANCEL` is already a member *alongside* `BLACKOUT_ONSET`, so the spec has already
> decided that cancellation cause is worth distinguishing. **Add `HALT_ONSET` as a distinct
> terminal path.** Amend as **SPEC-A7**; do not edit the frozen document in place.

### What the frozen spec says today

§3:151-152 fixes the lifecycle as *"taken at approval → released on: fill (converts to
open-margin), cancel, reject, pending-timeout resolution, blackout-onset cancellation. No leak
paths."* Twenty-two lines later §3:173 reads *"**Blackout/HALT onset ⇒ Limiter cancels all pending
ENTRY orders** (exits untouched)"* — the same action, from two triggers, one of which the terminal
set does not name.

### Why the three alternatives were all wrong, which is what makes this a ruling and not a tidy-up

D3.55 enumerated what a Limiter cancelling pending entries on HALT onset could do with those
reservations, and every option was a defect:

  * book them as `BLACKOUT_ONSET` — a Plane-1 row naming the **wrong cause**, in §9's record of
    money truth;
  * book them as `CANCEL` — the cause **erased**, which is the same loss one level quieter;
  * add an enum member — which `check_limiter_seam` ARM 1 would correctly redden as *"declared but
    NOT named by §3"*.

ARC 028 took the fourth option and **reported it**, adding no member and widening no path, because
B2's standing rule is that a terminal state the spec does not name is a finding, never a member
quietly added to make a sweep green. This ruling is the answer that was owed.

### How the gate reads this amendment, and why that mechanism had to be built

**`check_limiter_seam.spec_terminal_paths` parsed the frozen spec and NOTHING ELSE**, so an
amendment recorded here was invisible to it: adding `HALT_ONSET` would have reddened the gate
forever as an unspecced member, and the only way to green it would have been to edit the frozen
document — precisely what the ruling forbids. The derivation now returns the **effective** roster,
the frozen §3 sentence UNIONED with the `terminal-path additions` row of every amendment in this
file. The row above is that machine-readable surface. It is parsed, never typed into the gate, so
this file remains the single source and a future amendment needs no code change.

**The ordering was measured, not assumed** (ARC 029 / 0.4): with this amendment recorded and the
member not yet added, the seam gate reddened naming `HALT_ONSET` as a path §3 names and the seam
does not declare. It went green only when the member landed. Both directions are pinned by tests.

---

## SPEC-A8 — instrument selection is PRIOR to `min(risk, margin, symbol_cap)`, and is a function of the risk-ideal alone

| field | value |
|---|---|
| origin | **Architect ruling, issued in ARC 031 (Phase 5).** Not spec text. |
| implemented by | **Nothing new — this ratifies what shipped.** `scripts/nixalloc/sizing.py` (ARC 031, Stage 1, sub-agent B) already implements §7's order and said so in its own module docstring at the moment of the choice |
| closes | CHECK-DEBT **D3.126** — opened ARC 031 (Stage 1, sub-agent B) **by the author of the choice, in the same motion as the choice**, as a finding ABOUT THE SPEC rather than a decision made quietly |
| section that would have to say it | **§3:132-133** (the Allocator sizing pipeline) in `nics_risk_subsystem_spec_v1.3.md`, which now points at **§7:488-493** as the governing text |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |
| governing text | **§7:488-493.** §3:132-133 is amended to CITE it, not to restate it — one source, per core directive 3 |

### Ruling, as issued

> **Adopt §7's instrument-selection ordering.** Selection is prior to `min(risk, margin, symbol_cap)`
> and a function of the **risk-ideal alone**, because `margin_contracts` divides by live per-symbol
> margin and `symbol_cap` is per-instrument — **neither term is defined until the instrument is
> known.** §3:132's order denies valid trades before micros are considered and is the incoherent one.
>
> Amend, do **not** edit the frozen doc in place: record **SPEC-A8**, and §3:132 points at §7's
> pipeline. Mechanical fold, ratifying what shipped.

### What the frozen spec says today — both sentences, verbatim

**§3:132-133**, the pipeline diagram:

> ```
> size = min(risk_contracts, margin_contracts, symbol_cap)
>      → instrument selection (§7: single-instrument preference) → FCFS / static-priority → correlation cap
> ```

— selection **after** the `min`.

**§7:488-493**, the selection rule:

> **Instrument selection (deterministic, single-instrument preference — v1.2):** compute ideal size
> in micro units (MES etc. = 1/10). **One instrument per trade** [...] Rule: if risk-ideal quantizes
> acceptably to fulls (≥ threshold fulls, quantization error ≤ tolerance) ⇒ fulls only; otherwise
> micros only.

— selection as a function of the **risk-ideal**, and therefore **before** the other two terms.

One document, two orders, and nothing on disk could tell an implementer which one governed. That is
what D3.126 recorded rather than resolved.

### Why §7 is the coherent one — measured, not preferred

Two independent reasons, and the first is decisive on its own:

1. **The other two terms are UNDEFINED until the instrument is known.** `margin_contracts =
   floor(max(0, headroom_$) / live_margin_per_contract)` divides by the **live per-symbol** margin,
   and ES margin is not MES margin. `symbol_cap` is a **per-instrument** ceiling. Under §3's literal
   order the `min` must be evaluated before its own inputs exist. §7's order has no such circularity:
   the risk term `floor(per_trade_risk_$ / ((stop_ticks + slippage_pad) × tick_value))` is computable
   in micro units from the stop intent alone, which is exactly what §7:488 says to compute.

2. **§3's order DENIES VALID TRADES, silently.** A risk-ideal of 0.6 fulls floors to `0`, `min(...)`
   is `0`, and §3:134 (*"size 0 ⇒ deny"*) rejects the proposal **before micros are ever considered** —
   defeating the granularity micros exist to provide. The denial is indistinguishable, in the sizing
   rationale, from an honest risk-bound denial.

**Where the two orders AGREE, stated because it bounds the blast radius:** on every input where the
full contract is selected, the two pipelines produce identical output. Nothing observable separates
them there. The divergence is confined to the sub-one-full band — which is precisely the band micros
were added for, and precisely why the wrong order is not a harmless ambiguity.

### The pipeline as amended

```
risk-ideal (micro units)  ← §7:488, from the stop intent alone
   ↓
instrument selection (§7:488-493: fulls only, or micros only — never both)
   ↓
size = min(risk_contracts, margin_contracts, symbol_cap)   ← now all three terms are DEFINED
   ↓
FCFS / static-priority  →  correlation cap (§7:498-506)
   ↓
size 0 ⇒ deny. Else proposed order (carries sizing rationale: binding constraint + input snapshot).
```

§3:132-133 is amended to **point at §7**, not to duplicate it. Restating §7's rule inside §3 is the
mutable-fact restatement core directive 3 forbids, and is how the two sentences drifted apart in the
first place.

### What this amendment does NOT do

* **It does not edit the frozen document.** §3:132-133 stands as written in
  `nics_risk_subsystem_spec_v1.3.md`; this entry is the amendment of record, exactly as SPEC-A1–A7
  are, and a v1.4 is an architect action.
* **It does not change one line of shipped code, and that is the point of calling it a mechanical
  fold.** `scripts/nixalloc/sizing.py` already implements this order. `checks/check_allocator_pathway`
  and the Stage-1 suites are unchanged and stay green — no re-measure is owed, because nothing moved.
* **It adds no machine-readable row, and unlike SPEC-A7 it does not need one.** SPEC-A7 carries a
  `terminal-path additions` row because `check_limiter_seam` derives an *effective roster* by parsing
  the frozen §3 sentence UNIONED with this ledger, and an unparsed amendment would have reddened that
  gate forever. No gate in this tree derives a pipeline ORDER from spec text — the order is expressed
  in `sizing.py`'s control flow and driven by the pathway gate — so there is nothing here for a parser
  to read, and inventing a surface no instrument consumes would be decoration.
* **It does not touch the correlation cap's input problem.** §7's cap still cannot be computed from
  the published financial picture; that is CHECK-DEBT **D3.136**, ruled separately (OPTION A —
  `stop_distance` on the published `PositionRow`, a `SEAM_REV` bump, built by R3-B).

---

## SPEC-A9 — the published position row carries the STOP DISTANCE; §3:159's enumeration gains a sixth field

| field | value |
|---|---|
| origin | **Architect ruling, issued in ARC 031 (Phase 5) as OPTION A on CHECK-DEBT D3.136.** Not spec text. |
| implemented by | **ARC 032 (R3-B), Phase 0.4** — `nixrisk.seam.PositionRow.stop_distance`, `nixrisk.picture` both codec directions, `WIRE_SCHEMA 1 -> 2`, `nixalloc.seam.SEAM_REV 1.0.0 -> 1.1.0` |
| closes | CHECK-DEBT **D3.136** — §7's correlation-bucket cap could not be computed from the published financial picture, and failed OPEN while it could not |
| section that would have to say it | **§3:159** (`per-position rows keyed by trade_id: symbol, strategy_id, size, margin, state`) in `nics_risk_subsystem_spec_v1.3.md`, with **§7:501** as the clause that forces it and **§6.4** as the clause that forbids the alternative |
| status | **PENDING** a v1.4 of `nics_risk_subsystem_spec_v1.3.md`, which the architect owns |

**NO `terminal-path additions` ROW, and its absence is deliberate — MEASURED, not
reasoned.** The first draft of this table carried
`| terminal-path additions | *(none — this amendment adds no TerminalPath member)* |`,
on the reasonable-sounding argument that stating "none" is more explicit than omitting the row.
`check_limiter_seam` then FAILED: *"§3 names a release path TERMINALPATH that the seam does not
declare"*. The gate derives the EFFECTIVE terminal-path roster by parsing the frozen §3 sentence
UNIONED with this row across every amendment here (the mechanism SPEC-A7 had to build), and it read
the prose "adds no `TerminalPath` member" as a path named `TERMINALPATH`. The row is machine-read,
so the only correct way to say "this amendment adds none" is to not have the row — which is what
SPEC-A8 does, and this is the second amendment in a row for which that is true.

### Ruling, verbatim as issued (ARC 031, Phase 5)

> **OPTION A.** `PositionRow` gains **`stop_distance`**. §7:501 prices bucket exposure as
> `(stop_ticks + slippage_pad) × tick_value × contracts`, so applying the correlation cap to
> positions ALREADY held needs each one's stop distance — and the published row carries none, so
> today an unpriced position values at ZERO, the bucket reads EMPTIER than it is, and the cap
> **FAILS OPEN** by admitting more.
>
> The ruling picked the SKEW-FREE fix. `stop_distance` rides the **same versioned snapshot** as
> `balance` and `positions` — one more field under ONE writer and ONE version stamp (§6.4b's
> principle). It is explicitly NOT the stop-book read: the stop book is a SECOND table, and joining
> it to this one is the cross-table skew §6.4 forbids in the same breath as it fixes one snapshot.

### What the frozen spec says today

§3:159 enumerates the row: *"per-position rows keyed by trade_id: **symbol, strategy_id, size,
margin, state**"*. Five fields after the key. **`stop_distance` is a sixth**, and that is why this
amendment exists rather than the change simply landing: §3:159 is a closed enumeration inside the
frozen document, and an implementation that quietly adds a field to it is an implementation
disagreeing with the spec without saying so.

Eight lines up, §3:157 fixes the row's purpose as *"every position in whatever state it is in"* and
§3:162's ATOMICITY RULE fixes *"balance and the position table publish together as one snapshot —
never two separate reads"*. Both are satisfied by the addition and neither authorises it; the
authorisation is the ruling above.

### Why the alternative was refused BY NAME, which is what makes this a ruling

There were exactly two input paths for §7:501's stop distance and both were closed:

* **Option B — read the Limiter's stop book as a second table** (`StopState.initial_distance_ticks`,
  keyed by `client_order_id`). That is the cross-table skew **§6.4** refuses in the same sentence
  that fixes one snapshot — *"independent tables tick on independent clocks"* — and it was
  unavailable anyway, because nothing publishes the stop book.
* **Option A — put the distance on the published row.** A change to the one snapshot §3 makes
  atomic, therefore a `SEAM_REV` bump and an architect ruling rather than an implementation detail.

The asymmetry that decides it, and it is a *direction* rather than a preference: the cap is a
**safety input that was failing OPEN**. An unpriced position reads as zero risk, the bucket looks
emptier than it is, and an emptier bucket **admits more**. Incomplete in the permissive direction is
not the same defect as incomplete.

### What this amendment deliberately does NOT decide

* **It does not make the row a general-purpose carrier.** One field, forced by one clause of §7,
  under the same writer and the same version stamp. §2's authority split is untouched: the Limiter
  is still the sole writer and the Allocator still only reads.
* **It does not touch §6.4b's per-key venue stamps.** The published picture still carries none, the
  Allocator's mirror still degrades to a whole-snapshot recency guard, and that is still CHECK-DEBT
  **D3.121**. A `SEAM_REV` that moved for this reason is not evidence D3.121 was addressed, and
  `scripts/nixalloc/mirror.py` says so at the paragraph that would otherwise be read as a claim.
* **It does not decide the field's PROVENANCE inside the Limiter.** `stop_distance` is the tick
  distance the position was sized against; which of the Limiter's own structures the writer reads it
  from is the writer's business and is not a wire property.

### How this amendment is ENFORCED, which is the part that is not documentation

The mechanism is `nixalloc.seam.POSITION_ROW_FIELDS` plus `STOP_DISTANCE_FIELD`, and it had to be
BUILT, because **nothing in this tree pinned the published row's schema at all**.
`check_limiter_seam` pins the nine field names of `FinancialPicture` with their §3 reasons;
`check_allocator_seam` ARM 2 compared `MIRRORED_FIELDS` against `dataclasses.fields(FinancialPicture)`.
Neither named one field of `PositionRow`. So before ARC 032, renaming `PositionRow.margin` or
deleting `PositionRow.state` changed the published wire and left every seam gate green.

That claim is DRIVEN, not asserted:
`test_the_PRE_WIDENING_GATE_was_BLIND_to_the_row` checks the pre-widening gate's own bytes out of
git, runs them against a copy of the pre-widening seam with `PositionRow.margin` renamed, and
asserts that gate **passes**. `test_EVERY_published_ROW_field_renamed_in_turn_reddens` then walks
`POSITION_ROW_FIELDS` and proves today's gate reddens on each one, and
`test_RENAMING_stop_distance_reddens_naming_the_FAIL_OPEN` proves the stop-distance finding names
the fail-open rather than reporting a generic schema drift.

**One sentence of the ARC 031 ruling was wrong on the facts and is corrected rather than repeated.**
It said *"`nixalloc.seam.MIRRORED_FIELDS` gains it"*. `MIRRORED_FIELDS` pins `FinancialPicture`'s
fields; `stop_distance` is a field of `PositionRow`, one level down inside the `positions` tuple.
Adding the name there would have made the tuple disagree with
`dataclasses.fields(FinancialPicture)` and reddened the gate on the spot. The invariant the sentence
was reaching for — *the published row's schema is pinned to a literal at `SEAM_REV`* — is honoured
by `POSITION_ROW_FIELDS`. The spelling was a sketch; the invariant binds (§0b).

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
