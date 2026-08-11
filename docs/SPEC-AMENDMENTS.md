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
names its origin explicitly as an **operator ruling issued in ARC 020**, and every section
reference names the document it belongs to. A ruling here has the authority of an operator
decision — which is real, and is not the authority of the frozen spec.

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

## Standing note for the architect

Both amendments were issued as operator rulings **because ARC 019 refused to invent them.** That
refusal was correct and is the reason both arrive here with their rationale intact rather than as
undocumented behaviour discovered later. Each ruling states not only what to do but the asymmetry
that decides it, which is what a v1.4 needs in order to be written without re-deriving the argument.

Neither amendment is retroactive. Neither confers frozen-spec authority on anything in this file.
