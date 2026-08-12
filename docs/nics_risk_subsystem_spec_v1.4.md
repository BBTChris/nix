<!-- NIX ARC 027 (B4): MECHANICAL FOLD of docs/SPEC-AMENDMENTS.md into v1.3.
     Every byte outside a `FOLDED ...` block is byte-identical to frozen v1.3 as
     committed at aaa6a28f06f071d99411fec925a3d678cfbe66c6, and that identity is
     PROVEN on every pytest run by scripts/tests/test_spec_v14_fold.py, which
     strips the folded blocks and diffs the remainder against the committed blob.
     NOTHING was reworded, renumbered, improved or tidied. The amendments are
     reproduced with the numbering as it stands on disk, INCLUDING AMENDMENT 6's
     self-reference to "AMENDMENT 5" — see the NUMBERING note in that block's
     source entry. What was REFUSED, and why, is in test_spec_v14_fold.py. -->

# NICS — Risk Subsystem Specification (v1.3)
### Allocator + Risk Engine (Limiter + broker-order) + Scoring Process
*(project formerly drafted as "Io"; renamed NICS)*

**Project:** NICS (autonomous intraday futures trading — Tradovate / CME)
**Subsystem:** Risk (Allocator, Limiter, broker-order) + Scoring process + supporting data/persistence seams
**Status:** Design-locked v1.3 (broker split, full-financial-picture publish, performance-weighted contention added), pending CC verification objectives
**Author role:** Architect (design authority). Execution by Claude Code (CC) on node02.
**Platform baseline:** Headless Ubuntu 26.04 LTS, 6-core QuantVPS, co-located with Tradovate.
**Changelog:** §15 (audit), §16 (ULTRAREVIEW), §17 (v1.3 session).

---

## 1. Purpose & Goal

**Purpose.** Define the risk subsystem that stands between a strategy's trade intent and the
broker, such that no order is ever placed that violates account-survival constraints, and every
open position is protected by a mechanism that never depends on the network being healthy.

**Goal.** A permissive sizing layer (Allocator) and an authoritative firewall (Risk Engine =
Limiter + in-process broker) that together guarantee:

- No order reaches the broker without passing the Limiter (invariant).
- Every uncertainty resolves toward **flat** — known state beats optimal state.
- The exit/protective path has **zero wire dependency**.
- The hot path performs **cache reads + arithmetic only**.
- **Non-stop operation:** every failure mode has a defined degrade-and-recover path; no failure
  silently stops the system, and no transient condition can lock it out permanently (§12).

**Non-goals (this spec).** Strategy signal logic; Renko/candle transform internals (own spec);
DataBento/IBKR vendor integration internals (own spec). Referenced only at their seams.

---

## 2. Component Model & Authority Split

| Component | Process / Placement | Authority | Owns |
|---|---|---|---|
| **Strategy FSM** | separate process, Core 3 | signal only | emits GO (direction, symbol, strategy_id, signal_ts; stop as tick **distance** + **stop_mode** fixed/trailing, trailing carries initial + trail distances — §4); owns discretionary exit intent; **GO-timeout** (§4) |
| **Allocator** | **separate process (ZMQ)**, Core 3 | **permissive** | margin-aware sizing off a mirrored **full financial-picture table** (balance + positions + reservations), static caps, **performance-weighted** + FCFS-fallback contention, correlation caps; *proposes*. **Single-threaded** (§5) |
| **Risk Engine** | **process container**, Core 2 (isolated) | **prohibitive** | holds Limiter + broker-order |
| — **Limiter** | in Risk Engine | GO/NO-GO + placement | rule manifest, two-phase gate, **margin reservations**, synthetic stops, protective flatten, **net-liq survival watch**, sole event-log writer, canonical position state. **Single-threaded event loop + sender thread** (§5) |
| — **broker-order** | **in-process library** in Risk Engine | dumb hands | execution + account mgmt (orders, fills, positions, margin, **account balance**) via non-blocking, low-priority sender thread. Vendor-neutral: IBKR (scaffold) → Tradovate (prod) |
| **broker-datafeed** | **library inside capture.py process**, Core 1 | dumb ingress | streaming market data only. Vendor-neutral: IBKR (scaffold) → DataBento (prod). Fully isolated from order path by process + core boundary |
| **Scoring** | **separate process**, shared pool | advisory (sole writer of ranking table) | computes realized-P&L EMA **per (strategy_id, symbol) pair** (§6.6), publishes ranking table read by Allocator (sizing weight) and Limiter (contention arbitration). Never computes on either hot path |
| **Sentinel** | tiny independent process, shared pool | last-resort | deadman watchdog: Risk-Engine heartbeat lost + positions open ⇒ emergency flatten via own broker session (§12.1) |

**Principle.** In-process placement is earned by *triviality + exit-path criticality* (broker-order).
Logic-heavy, entry-path components are separate processes for fault isolation (Allocator).

---

## 2A. Broker Abstraction Contract (vendor-neutral seam — v1.3, locked)

The vendor-neutral promise ("swap is config, not code") holds ONLY if both libraries satisfy an
**identical method-and-event signature** that IBKR (scaffold) and Tradovate/DataBento (prod) each
implement behind. Each library has two directions: **commands we call in**, and **events it pushes
out** (push/callback model — no polling on the hot path; matches the push-preferred design). Vendor
specifics (auth, wire format, reconnect) live BELOW this line and never leak above it. All identifiers
are vendor-neutral; the adapter maps them to venue IDs internally.

### broker-order (execution + account) — in-process in the Risk Engine
**Commands (called by the Limiter only):**
- `connect() / disconnect()` — establish/tear down the venue session.
- `place_order(neutral_order)` — submit; `neutral_order` = {client_order_id, symbol, side, qty,
  type (mkt/limit), tif (IOC/day), limit_price?}. Returns an accepted/rejected ack, never a fill.
- `cancel_order(client_order_id)` — cancel a working order.
- `flatten(symbol | all)` — market-close a position (protective path; must not block).
- `query_positions()` — authoritative open-position set (cold-start ground truth).
- `query_balance()` — authoritative cash balance + margin figures.
- `query_order_status(client_order_id)` — pending-timeout resolution (never auto-resend).
- `get_margin(symbol)` — **poll-fallback** for live per-symbol current margin (feeds the unified
  snapshot); primary path is the `on_margin` push below (push-preferred, poll demotes to fallback/audit).
**Events (pushed to the Limiter):**
- `on_ack(client_order_id, accepted|rejected, reason?)`
- `on_fill(client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty)` — idempotent by
  (order_id, exec_id); partial fills arrive as successive events.
- `on_cancel(client_order_id, done_qty)`
- `on_balance(balance, venue_seq_ts)` — carries venue timestamp for the monotonic-by-source guard.
- `on_margin(symbol, margin_per_contract, venue_seq_ts)` — pushed live per-symbol margin (primary
  path when the venue's user-sync websocket delivers it); folded into the unified snapshot. Carries
  venue timestamp so a late push is discarded by the monotonic-by-source guard.
- `on_position(symbol, net_qty, avg_price)` — unsolicited position updates when the venue pushes them.
- `on_session(up|down, reason?)` — connectivity transitions (drives cold-start / Sentinel).

### broker-datafeed (streaming market data only) — in-process in capture.py
**Commands (called by capture.py only):**
- `connect() / disconnect()`
- `subscribe(symbol) / unsubscribe(symbol)`

<!-- BEGIN FOLDED AMENDMENT 5 (D1.38) -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 321-331; target: §2A broker-datafeed COMMAND declaration -->
**FOLDED AMENDMENT 5 (D1.38) — the broker-datafeed port is async by default**

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
<!-- END FOLDED AMENDMENT 5 (D1.38) -->

**Events (pushed to capture.py):**
- `on_tick(symbol, price, size, venue_ts)` — the raw firehose; capture builds bars, never broker-order.
- `on_feed_status(up|down|stale, symbol?, reason?)` — drives the stale⇒halt+flatten path.

<!-- BEGIN FOLDED AMENDMENT 4 -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 255-270; target: §2A broker-datafeed EVENT declaration -->
**FOLDED AMENDMENT 4 — the datafeed adapter emits bars only where the venue is the bar's source**

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
<!-- END FOLDED AMENDMENT 4 -->


**Strategy isolation from broker seams (invariant):** a strategy touches **neither** library.
Outbound it emits only a **GO** to the Allocator and receives its own trade's lifecycle feedback
(sized / denied / pending / open / closed) — it never calls broker-order, never places/cancels;
placement and protective action are the Limiter's job. Inbound it consumes **built bars/bricks from
capture.py** (Renko + M1 via the shared transform library) — **not** raw ticks from broker-datafeed.
So a strategy sees exactly two vendor-agnostic interfaces — bars/bricks in, own-trade feedback back —
both a layer removed from anything broker-specific, which is what lets IBKR↔Tradovate↔DataBento swap
without a strategy ever knowing.

**Invariants of the seam:** (1) command set + event set are **identical across vendors** — the
adapter satisfies the signature or it isn't done; (2) **no vendor type crosses the line** — only
neutral structs/ids; (3) **order and datafeed contracts are disjoint** — no shared object, so a
datafeed fault cannot reach the order library; (4) all timestamps are **venue-sourced** where a
monotonic guard depends on them; (5) the send path is **non-blocking** regardless of vendor.

<!-- BEGIN FOLDED AMENDMENT 3, REFINEMENT (ARC 022) -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 213-220; target: §2A "Invariants of the seam" -->
**FOLDED AMENDMENT 3, REFINEMENT (ARC 022) — an optional field must name an observable absence**

> **AMENDMENT 3, REFINEMENT (ARC 022).** The absence principle applies to facts the venue *can fail
> to report*, not to every field as a matter of course. Where a field's presence is structurally
> guaranteed by the existence of its container — a bar that exists has an open — an optional type is
> noise, and its predictable consequence is consumers writing `or 0.0`, which reintroduces the
> substitution the amendment forbids while wearing a null check.
>
> **Each optional field must be justified by an observable absence**: a case where the venue returns
> the container and omits the field. Fields that cannot be absent are not optional.
<!-- END FOLDED AMENDMENT 3, REFINEMENT (ARC 022) -->


<!-- BEGIN FOLDED AMENDMENT 3 -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 151-161; target: §2A "Invariants of the seam" (a sixth invariant) -->
**FOLDED AMENDMENT 3 — the seam declares absence; it never substitutes a value for one**

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
<!-- END FOLDED AMENDMENT 3 -->


---

## 3. Canonical Trade Pathway (Single-Pass Routing, Two-Phase Rule Logic)

**Physical routing is SINGLE-PASS** — the message never ping-pongs between cores:
`Strategy → Allocator → Risk Engine → broker`. Two ZMQ hops total.
The **two-phase rule logic survives inside the manifest**: the Limiter evaluates all size-independent
rules *before* size-dependent rules in one pass (both are O(1) flag/aggregate reads, so nothing is
gained by a physical round-trip). The "never size a dead signal" efficiency is delivered by the
Allocator's **fast-drop**, which reads the *same* tradability cache permissively at ingress; the rare
race (state flips between fast-drop and Limiter check) is caught authoritatively at the Limiter —
trivial wasted sizing, correct outcome.

```
Strategy (GO: direction, symbol, strategy_id, signal_ts; stop = tick distance + stop_mode {fixed | trailing[initial,trail]})
   │        [strategy arms GO-timeout: no feedback within T ⇒ treat as denied, reset]
   ▼
Allocator  (single pass: permissive pre-check + sizing — cache reads + arithmetic; clamp ≥ 0)
   FAST-DROP: HALT flag · tradable[symbol] · own staleness stamps  ⇒ drop before sizing/wire
   guard: invalid/missing stop intent ⇒ deny · symbol absent from margin cache ⇒ not-tradable
   risk_contracts   = floor( per_trade_risk_$ / ((stop_ticks + slippage_pad) × tick_value) )
   margin_contracts = floor( max(0, headroom_$) / live_margin_per_contract )
        where headroom_$ = 0.70 × balance − COMMITTED (open + reservations, Limiter-published cache)
   size = min(risk_contracts, margin_contracts, symbol_cap)
        → instrument selection (§7: single-instrument preference) → FCFS / static-priority → correlation cap
   → size 0 ⇒ deny. Else proposed order (carries sizing rationale: binding constraint + input snapshot).
   ▼
Risk Engine / Limiter  (ONE authoritative pass over the manifest)
   PHASE A — size-INDEPENDENT rules first:
   • global HALT flag (branch 0)
   • EOD · EOW · news/margin · roll-day blackouts · session boundary · post-open warmup
   • stale-data halt · clock-skew halt · one-in-flight-per-strategy lock
   PHASE B — size-DEPENDENT rules (against COMMITTED margin):
   • committed = Σ open margin + Σ PENDING RESERVATIONS
   • committed + proposed < 70% × balance
   • survival headroom: projected net-liq impact leaves floor intact (§6.5)
   • buffer/deployable ceiling fit
   → approve ⇒ TAKE RESERVATION (proposed margin) / size-down / deny (rule named, fail-fast)
   ▼
broker-order (in-process) → non-blocking sender thread → venue (IBKR scaffold / Tradovate prod)

RESERVATION LIFECYCLE (state machine — release on EVERY terminal path):
   taken at approval → released on: fill (converts to open-margin), cancel, reject,
   pending-timeout resolution, blackout-onset cancellation. No leak paths.

FULL FINANCIAL-PICTURE PUBLISH (v1.3 — Limiter is sole writer):
   The Limiter publishes ONE atomic snapshot the Allocator mirrors continuously — NOT just a
   committed-margin scalar. The Allocator holds complete financial situational awareness at all
   times, every position in whatever state it is in (reserved / pending / open / closing / closed):
     • account BALANCE (live)
     • per-position rows keyed by trade_id: symbol, strategy_id, size, margin, state
     • live per-symbol CURRENT MARGIN (one field set, same writer/version — §6.4)
     • Σ open margin · Σ reservations · committed · uncommitted (deployable) liquidity
   ATOMICITY RULE: balance and the position table publish together as one snapshot — never two
   separate reads — so the Allocator can never compute headroom off a stale balance + fresh
   commitment (or vice versa). Every consumer reads a self-consistent picture.
```

**EXIT / PROTECTIVE PATH (zero wire dependency):**
```
Limiter (synthetic stop / stale price / net-liq floor / session close / uncertainty / orphan / sentinel)
   → broker-order (in-process, direct call) → sender thread → flatten
```
Exit never routes through Allocator. Protective exit always wins over discretionary exit.
**Blackout/HALT onset ⇒ Limiter cancels all pending ENTRY orders** (exits untouched) — no order may
fill inside a window it was not approved for.

---

## 4. State Model

**GO message contract (v1.3, strategy → Allocator).** The GO is the trust boundary between a
lightweight strategy process and the sizing/gating machinery. Fields:
- `direction` (long/short), `symbol`, `strategy_id`, `signal_ts` (strategy clock).
- **Stop intent expressed as a tick DISTANCE, never an absolute price** — the strategy signals
  before it knows the real fill, so distance stays valid through slippage; the Limiter converts
  distance → absolute price **once the fill is confirmed**, so a stop can never land on the wrong
  side of entry. Distance in **ticks** (instrument tick = the price unit).
- **`stop_mode` ∈ {fixed, trailing}** — the STRATEGY chooses per-signal; not a system-wide policy.
  - **fixed:** stop anchored **once** at `fill ± initial_distance`; thereafter static
    (compute-once-at-fill).
  - **trailing:** carries **two** distances — `initial_distance` (where the stop first sits at the
    fill) and a separate `trail_distance` (the gap maintained behind the high-water mark). The stop
    **holds at the initial level until price advances far enough that the trail distance would sit
    tighter than the initial stop**, and only then begins trailing — so the stop **only ever moves
    in the strategy's favour and never jumps backward at activation**. Once trailing, it ratchets
    behind the high-water mark every tick (Limiter recomputes vs the price cache) and never gives
    ground back.
- **Validation / authority:** the **Limiter** validates the stop intent (missing/zero/invalid
  distance ⇒ deny; §3 ingress guard); symbol absent from the margin field set ⇒ not-tradable. The
  strategy proposes; the Limiter is the sole authority that converts, places, and maintains the stop.

**Two-phase entry states:** `PENDING` (placement accepted) → `OPEN` (fill **confirmed**, real price).
"Open" is asserted **only** on broker fill confirmation — never on placement ack, never optimistically.

**Feedback (full):** every outcome (sized / denied / pending / open / closed / rejected /
protective-flatten) is pushed to the originating strategy FSM, tagged with **trade_id** (minted by
Limiter at open) to prevent cross-position mis-application.

**Concurrency:** **one in-flight action per strategy.** While an order is pending, the strategy's
next signal is rejected-with-reason until resolution.
**GO-timeout (deadlock breaker):** if a strategy receives no sized/denied feedback within T of
emitting GO (e.g. Allocator died holding it), it treats the GO as denied and resets to flat-and-free.
The in-flight lock can never wedge on a lost message.

**Idempotent execution handling:** broker events are deduplicated by (order_id, exec_id); position
state derives from cumulative fills — immune to duplicate or out-of-order execution reports.

**Exits (dual authority):**
- Strategy = discretionary exit (edge spent) → routes **direct to Limiter** (skips Allocator).
- Limiter = protective exit (stop / stale / floor / session / uncertainty / orphan) → unconditional.
- Protective always wins; strategy is notified `closed, reason=X`; FSM hard-resets to flat.

<!-- BEGIN FOLDED AMENDMENT 2 -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 90-109; target: §4 "Exits (dual authority)" -->
**FOLDED AMENDMENT 2 — protective `flatten` is idempotent within a bounded window**

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
<!-- END FOLDED AMENDMENT 2 -->


**Boot / known-state discipline:**
- **System cold-start (v1.3, locked):** on start the local state is empty and trustless — nothing to
  infer from, so the Limiter **actively queries the broker** the moment broker-order has a session:
  the **true open-position set + balance = ground truth** (not a reconciliation against our record;
  at cold start the broker's answer *is* the record). This mandatory query **gates registration** —
  no strategy registers until a provably-flat assertion has passed. Then:
  - **Already flat** ⇒ assert flat, proceed to allow registration.
  - **Any unexpected open position ⇒ flatten to flat before any strategy registers.** We never adopt
    or reason about an inherited position; flat is the only known-good state.
  - **Market-tradable guard:** flatten fires market orders, so it needs an open, tradable market. If
    the box comes up to an open position while the market is **closed/halted** (weekend, session
    gap), the system does **NOT** fire orders into a shut market — it **holds in HALT with a loud
    alert** and flattens the instant the market is tradable. Flatten-to-flat stays the rule; it is
    guarded, never blind.
- **Strategy start:** boots to flat — requests flat, Limiter reconciles vs broker truth & confirms.
- **Restart = flat, always.** No "resume prior position," even a winning one.

<!-- BEGIN FOLDED AMENDMENT 1 -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 48-57; target: §4 "Boot / known-state discipline" -->
**FOLDED AMENDMENT 1 — startup admission gate discriminates by ownership, not elapsed time**

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
<!-- END FOLDED AMENDMENT 1 -->


**Failure resolution (all resolve toward flat):**
- **Pending timeout** (FIX-style): placement-ack ~1–2s, fill timeout order-type-dependent → Limiter
  issues order-status query, never auto-resends. Resolves confirmed / cancelled / **indeterminate**.
- **Indeterminate ⇒ flatten-on-uncertainty.** We don't know if a position exists, so we send a
  flatten to be safe. Because the flatten may hit nothing OR close a real position, the Limiter
  **reconciles against broker truth afterward** and publishes whichever is real — the broadcast is
  "here is the CONFIRMED flat state", not merely "we sent a flatten". That confirmed state fans out
  to ALL consumers off the one canonical source: (a) owning **strategy** → `closed, reason=X`,
  hard-reset to flat, one-in-flight slot freed; (b) **Allocator mirror** → reservation released,
  position leaves table, balance/liquidity recompute (no ghost sizing); (c) **event log** (sole
  writer = Limiter); (d) **Scoring process** → any real fill from the flatten books as realized P&L.

- **Broker-authoritative balance on EVERY reconciliation (v1.3, locked):** the broker is the source
  of truth for liquidity; our running balance is a fast local *projection*. EVERY reconciliation
  event (indeterminate, orphan, protective flatten, partial-fill resolution, any fill/close) pulls a
  **direct broker balance + position poll** in the same motion, and the fresh authoritative reading
  is published atomically. Uniform behaviour on every event (no "is this ambiguous enough?" branch);
  cost is trivial (human-scale event frequency, off hot path). If projection and broker truth
  disagree beyond tolerance, **broker wins and we correct**. Monotonic-by-source guard still applies.
  The periodic poll (§6.4b) remains underneath for quiet periods and money moved outside trade flow.

- **Orphan / strategy-death recovery (v1.3, locked):** heartbeat miss ⇒ wait **exactly one cycle
  (1s)**; a second consecutive miss ⇒ strategy presumed dead. Recovery runs **safety-before-restart,
  in strict order**:
  1. **Flatten first** — close any open positions owned by that strategy (swept by `strategy_id`)
     while its registration still exists, so each position has an unambiguous known owner. A dead
     strategy holding a live position is the dangerous state; money is made safe immediately, before
     any process-lifecycle work.
  2. **Force-deregister in the Risk Engine** — the Limiter tears down ALL state keyed to that
     strategy: one-in-flight lock, pending state, slot, registration. Nothing stale may survive the
     death (a lingering registration would leave the Limiter expecting heartbeats / holding a slot).
  3. **Kill + relaunch** — process is killed and relaunched; it re-registers and **boots to flat**
     like any cold start — a genuinely new registration, not a half-cleared old one.
  - **Crash-loop cap (locked):** after **3** restarts within a window (window = tunable variable),
    stop relaunching. The strategy is **quarantined — left dead and flat, alert raised** — while the
    rest of the system keeps trading. Quarantine is NOT auto-resurrected; return is operator-driven.
  - **Score handling across death (locked):** a normal crash-restart **persists** the strategy's
    realized-P&L history (score keyed by strategy×symbol, not by process instance; a crash is not a
    trade and never books a phantom zero/loss — only real fills from the recovery flatten count). On
    **quarantine**, the strategy is **removed from the live ranking table** so it can no longer win a
    contention tiebreak for capital it can't use; its realized history is **archived, not destroyed**
    (recoverable if the operator deliberately brings it back).
  - **Allocator visibility throughout (locked):** every recovery action reaches the Allocator via the
    same mirrored snapshot — flatten (positions→closed, reservations released, capital returns to
    deployable), deregistration (strategy leaves active set), quarantine (withdrawn from contention).
    The **transitional state is visible too**: a strategy mid-recovery reads as **in-flight-closing**,
    NOT normal-and-available, so it is never counted eligible for new capital while dying. (This is
    why the published table carries per-position lifecycle state, not just aggregates.)
- **Partial fill (v1.3, locked):** the fill is a **fact the system reports, never a negotiation.**
  Limiter sets position = **actual filled qty**, cancels the unfilled remainder (IOC-style), and
  **informs the strategy** — the strategy's **FSM owns a state that handles being smaller than it
  asked for** (manage the fill it got; the Limiter never auto-tops-up to chase the shortfall). Stop
  and exit logic operate on the real filled size. **Allocator reflection is real-time:** on fill
  confirmation the Limiter publishes the atomic snapshot with the true filled size, the real
  committed margin, and the **reservation for the unfilled portion released** — so the Allocator's
  mirror shows the true (e.g. 2-contract) position and the over-reserved capital returns to
  deployable **the instant reality comes in under the reservation**, not on a delay. If the cancel
  loses the race and the remainder fills, position state reflects cumulative reality; the reservation
  covered full size, so no cap breach either way.
- **Stale price / stale margin ⇒ halt new entries + flatten open** (§6.4).

**Post-protective cooldown (hybrid: condition-clear AND minimum-time floor, per-strategy):**
- Discretionary exit → none. Ordinary stop → short. Feed/uncertainty/stale → longer.
  Margin/session → longest or until condition clears. Manifest-owned, tunable offline.

---

## 5. Rule Manifest, Executor & Threading Model

**Plugin model.** Each rule = an in-process library (loaded once, bound at boot — no per-eval import,
no wire). Lightweight, non-blocking, side-effect-free.

**Manifest (loadable file) = source of truth** for which rules run, order, and phase
(`pre-size` / `post-size`). Ordered **stages**; a stage is a single rule or a **parallel block**
(sequential lists running concurrently). No parallelism declared ⇒ degrades to a plain sequential
list — same executor, no special-casing.

**Executor semantics:** sequential by default, cheapest-and-most-decisive first; parallel only for
genuinely-slow independent rules; **fail-fast globally** (first deny halts all further dispatch;
in-flight results discarded; blocking rule named). Default posture: accept unless a rule blocks.
Size-down is distinct from deny.

**Threading model (explicit — race-class elimination):**
- **Limiter = single-threaded event loop** (shared-mem price poll + ZMQ inbox + sender completions,
  processed serially) + **one low-priority sender thread** (blocking I/O, releases GIL; hung socket
  contained; hot loop never blocks). Serial processing eliminates fill-vs-tick races by construction.
- **Allocator = single-threaded.** Serialization **is** the contention mechanism: FCFS = socket
  arrival order; static priority breaks ties only within a batched wakeup. Zero locks.

---

## 6. Financial & Blackout Rules (locked)

### 6.1 EOD entry blackout (pre-size)
No new entry from **15–20 min before that symbol's session close** through its **next session open**.
Entry-only; exits still fire. Per-symbol via live calendar. Global default **20 min**, per-symbol
override; lead exceeds the **session-close flatten deadline (§6.1b)** with pad (equity-index margin
snap 3:45 PM CST). **Onset cancels pending entry orders** (§3).

### 6.1b Session-close flatten — the intraday-only enforcement (v1.3, locked)
The *never-hold-overnight* mandate is enforced **by construction**, not by convention:
- At **`SESSION_FLATTEN_LEAD_MIN` before each symbol's session close** (same live calendar as §6.1,
  clock-driven UTC per §12.3), the **Limiter force-flattens all open positions in that symbol**,
  `reason=session` — the protective-exit reason already anticipated in §3; this defines its trigger.
- **Backstop, not the plan:** strategies should exit discretionarily well before. The deadline
  guarantees a position lifecycle **cannot cross a session boundary**, regardless of strategy
  behavior.
- **Ordering invariant (boot-validated):** `SESSION_FLATTEN_LEAD_MIN < EOD_BLACKOUT_MIN − pad`
  per symbol — the entry blackout must lead the flatten deadline (the relationship §6.1 references).
  Config validation **rejects** any per-symbol set violating it.
- **Failure ladder = existing machinery:** flatten indeterminate → §4 flatten-on-uncertainty +
  reconcile-then-publish-confirmed-truth. Market halted at the deadline → §12.6 honesty clause
  (a halted market cannot be flattened; exposure rides; **Critical alert**). Standard fanout:
  strategy receives `closed, reason=session`, hard-reset, slot freed; Scoring books real fills.
- **Alerting:** Info-tier on clean fire; failure paths land in the existing Critical machinery.

### 6.2 EOW blackout (pre-size)
No new entry from **30 min before Friday close** through **Sunday session open**. Widest active
leading edge wins (window union). Per-symbol (equity-index ref: 3:30 PM CST Fri → 5:00 PM CST Sun).

### 6.3 News / margin-event blackout (pre-size, asymmetric edges)
- **Leading edge = clock (predictive):** block **20 min before** a scheduled margin-affecting event.
- **Trailing edge = live margin (reactive):** hold until margin returns to baseline (+ min-time floor).
  Also catches **unscheduled** spikes for free.
- **Baseline re-acceptance (anti-lockout):** if margin holds stable-elevated beyond a defined period
  (regime shift, not spike), accept the new level as baseline — alert operator; sizing shrinks
  naturally via `margin_contracts`. A permanent broker hike must never lock the system out forever.
- **Open positions:** hold-through under buffer protection; flatten only on real breach.

### 6.4 Live-margin & calendar pollers + stale ⇒ halt+flatten
- **Margin poller** (fast, seconds) → margin cache. **Calendar poller** (slow, minutes) → per-symbol
  window set (sessions, econ events, **roll schedule**, holidays/half-days). Both on shared pool.
- **Push-preferred:** if Tradovate's user-sync websocket delivers account/margin/position events,
  event-driven updates are primary and polling demotes to fallback/audit (CC-verify).
- Allocator/Limiter **read caches only**. **Stale (freshness stamp past threshold, after
  retry/backoff) ⇒ halt new entries AND flatten open.** Detection = system; execution = Limiter.

<!-- BEGIN FOLDED AMENDMENT 6 -->
<!-- source: docs/SPEC-AMENDMENTS.md lines 396-416; target: §2A (no freshness-stamp declaration exists) and §6.4:371-374 -->
**FOLDED AMENDMENT 6 — freshness is per-channel (ISSUED titled "AMENDMENT 5" — see NUMBERING below)**

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
<!-- END FOLDED AMENDMENT 6 -->

- **Live per-symbol margin transport (v1.3, locked):** live current margin per symbol is **NOT a
  separate table or its own shared-memory block.** broker-order brings it in; the Limiter folds it
  into the **one unified financial-picture snapshot** (§3 / §6.4b) as an added per-symbol field
  set, under **one writer and one version stamp** covering balance + positions + reservations +
  per-symbol margin together. Both the Allocator (margin-contracts sizing) and the Limiter
  (size-dependent gate) read the **same versioned row** from their per-process read-only mirror —
  identical bytes by construction, readers only. **Why not a standalone margin table:** the Allocator
  sizes on margin AND balance AND headroom in one breath; independent tables tick on independent
  clocks, so a sizing pass could read fresh margin against slightly stale balance — cross-table skew,
  the same split-brain we removed for balance, reintroduced at a new seam. One snapshot = every field
  internally coherent, not merely each field coherent within itself. **Why not raw shared memory
  here:** margin moves on the scale of seconds, not microseconds — letting the Allocator/dashboards
  read into the Limiter's live memory across cores would put reader traffic on the writer's cache
  lines right on the hot gate for zero freshness benefit; publish-and-mirror keeps the hot path
  clean. (The per-tick price firehose remains the sole raw-shared-memory exception — §10, §12.7.)

### 6.4b Account-balance refresh (hybrid — v1.3)
Balance originates at the venue: **venue → broker-order → Limiter → published snapshot → Allocator
mirror**. Two triggers keep it both sharp and honest:
- **Event-driven:** every money-moving trade event (confirmed fill, close, commission debit) causes
  broker-order to forward a fresh balance immediately — real-time accuracy exactly when it matters.
- **Periodic poll:** a slow background refresh catches everything events don't (funding, fees,
  overnight adjustments, broker-side corrections/sweeps outside the order flow).
- **MONOTONIC-BY-SOURCE guard (required — applies to ALL venue-sourced state):** every reading from
  the venue — **balance, per-symbol margin, and position/quantity updates** (`on_balance`,
  `on_margin`, `on_position`, and the values returned by cold-start/reconciliation queries) — carries
  the venue's own timestamp/sequence number. The Limiter accepts a new value for a given key ONLY if
  it is newer than the one it holds; anything older is **discarded, not applied**. Ordering is by
  source-of-truth time, never by arrival time, and the guard is **per key** (per symbol for margin,
  per instrument for position) so a late update on one key can never regress another. No venue-sourced
  field can go backwards and mislead sizing, gating, or reconciliation. (Direct reconciliation polls
  are themselves timestamped, so a slow poll landing after a fresher push is dropped, not applied.)

### 6.5 Liquidity governor (mixed) — corrected
- **Sizing denominator = realized/cash liquidity** (deterministic; changes on fills **and
  commissions/fees**, which debit on close). Unrealized value **excluded from sizing**, always.
- **30% buffer / 70% deployable** — single number.
- **Aggregate margin cap (hard, 100% of the time):**
  `Σ committed intraday margin (open + pending reservations + proposed) < 70% × balance`.
- **Survival watch (continuous, corrected):** the broker liquidates on **net-liq vs maintenance
  margin** — cash does not erode with price; unrealized loss does. The Limiter marks **net-liq =
  cash ± unrealized** incrementally per tick (O(positions), from the price cache) and force-flattens
  when `net_liq < Σ open margin × (1 + safety_pad)` — **before** Tradovate's trigger ($25/$50 fees).
  We never let the broker liquidate us.
- **Ledger reconcile:** account poller vs internal fill-ledger; drift beyond tolerance ⇒ audit event.
- Interlock: the 70% intraday cap is only safe because §6.1–6.3 keep the book out of the 4× spike and
  close-snap. Cap + blackout calendar are one coupled system.

**Unified model:** entry denied if
`HALT ∨ now ∈ any window ∨ margin elevated ∨ data stale ∨ clock skewed` (pre-size), plus the
size-dependent governor (post-size). New blackout types are **data (a window)**, not code.

---

### 6.6 Performance-weighted contention (Scoring process — v1.3)
When multiple strategies' proposals arrive close together and shared capital (liquidity/margin)
cannot satisfy them all, the winner is chosen by **recent realized productivity**, not by arrival
order or a static priority. Feed the winners.

**Measurement (locked):**
- **Realized P&L only** — closed trades. Unrealized/paper gains never steer capital (a green open
  position can reverse before it closes). Realized P&L is the strategy's *actual verdict* — it
  entered, managed, and exited — so ranking on it ranks completed strategy decisions.
- **Advances per DAY** — one realized number per symbol per day (keeps symbols comparable; a
  hyperactive symbol can't dominate purely by trading more often).
- **EMA-smoothed** — recent days weighted more, older days fade continuously (no hard week/older
  cliff). The resulting per-symbol score is the ranking key.
- **EMA span = variable `SCORE_EMA_SPAN_DAYS`, default 10 trading days** (~2 weeks), tunable —
  calibrated on the box once real realized data exists; NOT a carved constant. (Caution: early
  realized samples are thin — a handful of closed trades per symbol per day — so the number matters
  less than accumulating enough history to trust it.)

**Ownership & authority (locked):**
- **Canonical key = `(strategy_id, symbol)` (v1.3, locked):** one row per pair, realized-P&L EMA per
  pair. This is the only keying under which the rest of the design is simultaneously true: score
  **persists across process death** (keyed to the pair, not the process — §4) and **quarantine
  removes exactly that strategy's rows** (archived, not destroyed). Any per-symbol figure is a
  **derived display aggregate**, never the stored unit.
- **Arbitration = compare the competing pairs' rows:** two strategies GO on one symbol ⇒ compare the
  two pair-rows; two symbols compete for the last liquidity ⇒ compare each contender's own pair-row.
  Equal or absent scores (e.g. cold-start, no history) ⇒ **FCFS**, the existing neutral fallback.
  Still O(1) lookups; no math on any hot path.
- A **dedicated Scoring process** (shared pool, Core 4–5) is the **sole writer** of a continuously
  updated **ranking table** in shared memory.
- The **Allocator reads** it to weight sizing. The **Limiter reads** it to arbitrate contention when
  a shared resource can't satisfy every proposal at once (e.g. two symbols, liquidity for one).
- **Nobody but the Scoring process COMPUTES the score.** Reading a precomputed rank to break a tie
  is *enforcement* and is legitimate for the Limiter; computing the EMA / defining "productive" is
  the allocation judgment that stays out of the gate. Both hot paths do an **O(1) table lookup**,
  never math — consistent with the margin/tradability cache pattern.
- **FALLBACK (locked):** if the Scoring process is down or its table is stale, both Allocator and
  Limiter fall back to **first-come-first-served** — deterministic, structurally neutral (favors no
  symbol), needs no computation at the moment a process just died. Ranking is an optimization, never
  a safety gate: a scoring outage must NEVER halt order flow.

## 7. Sizing Physics (Spot→Futures Port)

Futures sizing: **discrete whole contracts**, fixed $/point per symbol, two decoupled constraints
(risk vs margin), live exchange-dollar margin.

```
risk_contracts   = floor( per_trade_risk_$ / ((stop_ticks + slippage_pad) × tick_value) )
margin_contracts = floor( max(0, headroom_$) / live_margin_per_contract )
size = min(risk_contracts, margin_contracts, symbol_cap) → variant selection → contention → correlation cap
```

- **Slippage pad:** stops gap through (news spikes) — `risk_$` is honest only if sized against
  stop + expected slippage. Pad per-symbol, CC-calibrated.
- **Guards:** invalid/zero stop intent ⇒ deny; symbol missing from margin cache ⇒ not-tradable;
  every term clamps ≥ 0 (no negative-floor artifacts).
- **Key finding:** Tradovate day margins (ES $500 / MES $50 / NQ $1,000 / MNQ $100; CL ~$1,700 /
  GC ~$1,650 / ZN ~$206 — peer-broker estimates, CC-verify) are ~40–50× under CME initial ⇒
  **risk binds intraday, not margin**; the margin term fires only near close-snap and news spikes.
- **Instrument selection (deterministic, single-instrument preference — v1.2):** compute ideal size
  in micro units (MES etc. = 1/10). **One instrument per trade** — no mixed full+micro legs in v1:
  micros carry proportionally higher commission per unit exposure (10 micro RTs ≈ 2–4× one full RT)
  and a mixed entry doubles order lifecycles (two partial-fill paths) on the hot path. Rule: if
  risk-ideal quantizes acceptably to fulls (≥ threshold fulls, quantization error ≤ tolerance) ⇒
  fulls only; otherwise micros only. Correlation buckets count micros at 1/10 weight. Thresholds
  per-symbol config, CC-calibrated for commission-vs-granularity tradeoff.
- **Symbol scope:** up to 5 top-liquid (ES, NQ, CL, GC, ZN); ES/NQ ~0.9 correlated ⇒ bucket caps
  (equities/energy/metals/rates).
- **Correlation-bucket cap (v1.3, locked — combination formula):**
  - **Buckets:** equities {ES, NQ}, energy {CL}, metals {GC}, rates {ZN} (static; §16 — dynamic
    correlation stays out of the hot path).
  - **Exposure unit = DOLLAR RISK** — the same `per_trade_risk_$` the sizer already computes
    (`(stop_ticks + slippage_pad) × tick_value × contracts`), the true apples-to-apples measure of
    what is lost if correlated positions go against you together. Micros count at **1/10** weight
    (their dollar risk falls out naturally). NOT contract count (meaningless across ES vs NQ), NOT
    margin (measures capital tied up, not risk taken).
  - **SAME-BUCKET ONLY.** The cap constrains concentration **within** one bucket; positions in
    **different** buckets do **not** limit each other through this rule (different buckets are, by
    construction, not strongly correlated). Cross-bucket total exposure is still bounded — by the
    portfolio-wide layers already locked (70% deployable liquidity, aggregate margin cap, net-liq
    survival floor, §6.5). Two layers, two jobs: correlation = within-bucket concentration; capital
    -at-risk = portfolio-wide.
  - **Cap basis = PERCENT OF BALANCE** (scales with the account, no manual re-tune):
    `Σ dollar_risk(open + pending in bucket B) + proposed_dollar_risk ≤ bucket_cap_pct(B) × balance`.
    A proposal in bucket B is admitted only if it keeps B's total dollar risk at/under B's ceiling;
    otherwise size-down toward the ceiling, then deny at zero. Per-bucket `bucket_cap_pct` is config,
    CC-calibrated.
- **Synthetic margin ceiling:** deployment capped well below what cheap intraday margin allows.

### 7.5 Contract rolls (new — was missing)
- Futures expire; front-month identity shifts days before expiry as volume migrates.
- **Front-month = volume leader** per the liquidity principle; roll schedule sourced by the calendar
  poller; all symbol-keyed subsystems (capture, backfill, margin cache, calendar, Renko state,
  positions) switch identity **atomically at a defined roll instant**.
- **Roll-day entry blackout** for the affected symbol (a window — data, not code). Intraday-only
  means no position ever spans the roll.
- **Renko/backfill continuity:** the brick series is per-contract; the roll seam is a defined
  boundary (no phantom bricks stitched across contracts). Historical continuity handled by the
  transform library's seam mechanism.

---

## 8. Data / Persistence Seams (referenced, not owned here)

- **capture.py** (Core 1): live ticks → **shared transform library** → Renko + M1 → **shared memory**
  (single-writer / many-reader; strategies read bricks, Limiter reads last-price). Feeds backfill
  over ZMQ (slow Postgres never backpressures capture).
- **backfill** (shared pool): persist live bricks/candles; on gap/downtime pull historical, form
  Renko+M1 via the **same shared library**, backfill Postgres.
- **Vendor = DataBento (prod) / IBKR (scaffold). Broker = Tradovate = broker-order only (via broker-datafeed vendor split).** Ticks never
  source from Tradovate.

**HARD RULES (Luna mid-divergence prevention):**
1. Brick/candle formation is **ONE shared library** — live == historical **by construction**.
2. **Renko is path-dependent** — running state hands across the live↔historical seam (and the roll
   seam, §7.5) or phantom bricks form. Regression-tested against the exact Luna failure.
3. Shared memory: single-writer, lock-free readers (ring buffer / seqlock) — no torn reads.

---

## 9. Persistence Model (event-sourced)

- **Append-only event log** — one row per transition (signal, accepted, filled, exit-intent, closed,
  denied, protective-exit, reservation taken/released, **cancel** (incl. IOC remainder-cancel),
  **GO-timeout**, **HALT set/cleared**, **operator action**, **strategy lifecycle**, **cold-start
  reconciliation outcome**, **sentinel-flatten (marker replay, §12.1)**). Never overwrite.
  Timestamp + strategy_id + trade_id + reason on every row. Full inventory + plane mapping: §12.10.
- **Positions table = projection** (rebuildable; dashboard + reconciliation read it).
- **Limiter = sole writer.** Enqueue → **durable local WAL** → shared-pool writer → **group-commit**
  to Postgres. Crash gap healed by startup reconciliation vs broker truth.
- Fill price captured at **fill event**.

---

## 10. Process / Core Map (locked)

| Core | Assignment | Notes |
|---|---|---|
| 0 | OS/kernel + interrupts | isolcpus/nohz_full/IRQ affinity for the rest |
| 1 | capture.py (hosts **broker-datafeed** library) | isolated, elevated — tick firehose; datafeed crash/reconnect cannot touch order path |
| 2 | **Risk Engine (Limiter + broker-order)** | isolated, highest priority — firewall + exit brake |
| 3 | Allocator + strategy processes | isolated |
| 4–5 | shared pool | Postgres, pollers, backfill, logging, ZMQ proxy, dashboards, health, **Sentinel**, **Scoring process** |

**Transport asymmetry:** shared memory for hot readers; ZMQ for the persistence sink. **Inbound**
broker connectivity may be a separate process (cache buffers it); **outbound** exit connectivity
cannot (nothing buffers a send) ⇒ broker-order in-process, async sender.

---

## 11. Performance & Hot-Path Discipline (cross-cutting invariant)

Entry pathway = **cache reads + arithmetic only**; everything expensive lives on pollers /
event-handlers updating caches and running aggregates.

1. **Tradability cache** `tradable[symbol]=(bool,reason)` updated on state change ⇒ pre-gate O(1).
2. **Fast-drop at ingress** (Allocator reads tradability first; Limiter re-read = the guarantee).
3. **Incremental aggregates** — Σ open margin, **Σ reservations**, bucket exposure, **net-liq mark**,
   **balance**, per-position table maintained as running values on fill/close/tick ⇒ all gate checks
   O(1). Published as ONE atomic financial-picture snapshot (§3) mirrored by the Allocator.
4. **Precompute deployable** on account-state change only.
5. **Global HALT flag** — first atomic read in pre-gate.
6. **Group-commit** event-log writes off hot path (WAL-buffered).
7. Periodic **full-scan audit** reconciles every running aggregate vs ground truth (drift ⇒ audit
   event; material drift ⇒ HALT).
8. **Push-preferred updates** (websocket user-sync) over polling where the API supports it.
9. **Ranking-table lookup only** — Scoring process (§6.6) owns all EMA math off-hot-path; Allocator
   and Limiter do O(1) reads; stale/absent table ⇒ FCFS fallback, never a stall.

---

## 12. Non-Stop Operation (new)

### 12.1 Sentinel (last-resort deadman)
Tiny, dependency-minimal independent process (shared pool). Watches the Risk-Engine heartbeat.
Heartbeat lost **and** positions possibly open ⇒ emergency flatten-all via its **own** broker
session + operator alert. Deliberately dumb, separate code path (minimal common-mode failure).
This is our software, not a broker-side stop — that prohibition stands.

**Durable record (v1.3 fix — the sole-writer gap):** the Sentinel fires precisely when the sole
event-log writer (Limiter) is dead, so its flatten would otherwise be the least-recorded action in
the system. Fix: the Sentinel writes a **local append-only marker file** (timestamp, trigger cause,
symbols, broker acks) *before and after* acting — no Postgres, no shared writer, nothing to fail.
On next boot, **cold-start reconciliation reads the marker** and books the flatten into the real
event log retroactively (rows tagged `source=sentinel`), then archives the marker. Sole-writer
invariant stands; the catastrophic path gains a durable record.

### 12.2 Supervision & crash-loop breaker
Every process systemd-managed with restart policy. **N restarts in M minutes ⇒ HALT + operator
alert** — never blind restart-into-trading. Boot-flatten makes any single restart safe by design.

### 12.3 Clock integrity
All blackouts are clock-driven ⇒ the clock is safety-critical. chrony sync + continuous skew monitor
against exchange/vendor timestamps; skew > threshold ⇒ stale-class HALT. **All internal time is
UTC**; the calendar poller converts exchange-local (incl. DST) exactly once at window generation.

### 12.4 Degraded persistence ≠ degraded trading
Postgres outage: WAL buffers, trading continues, operator alerted. **Disk-critical** (WAL cannot
append) ⇒ HALT new entries — no audit trail, no new risk. Open positions remain protected (stops
read memory, not disk).

### 12.5 HALT semantics
Setters: stale-data, clock-skew, crash-loop, invariant breach, aggregate-drift, operator.
Auto-set conditions may **auto-clear** on condition-clear + minimum floor (cooldown discipline).
**Operator HALT clears only by operator.** Every set/clear is an audited event with reason.
**Limiter-down case (v1.3):** if a HALT condition arises while the Limiter is unavailable (e.g.
the Risk Engine itself is the crash-looping process), the system is already **fail-closed** —
nothing reaches the broker without the Limiter — so no separate flag is needed for safety. The
`HALT set` row is **booked retroactively at next boot by cold-start reconciliation**, same pattern
as the Sentinel marker replay (§12.1): Plane-1 completeness holds without a second writer.

### 12.6 Exchange halts / circuit breakers
Exchange halt or limit-lock = blackout window + alert. Residual risk documented honestly: a halted
market cannot be flattened by any design; exposure rides until reopen, then protective rules act.

### 12.7 Cache distribution & restart rebuild — state-table transport (LOCKED v1.3)
**Standard mechanism for ALL state tables** (financial picture §3, ranking table §6.6,
tradability, margin/calendar caches): **ZeroMQ plain PUB/SUB + snapshot-on-subscribe, mirror
model.** Locked; no heavier delivery-guarantee layer (the snapshot already provides correctness —
added complexity buys nothing at this scale).

- **Mirror model, NOT raw shared memory.** Each owning process (Limiter → financial picture;
  Scoring → ranking; pollers → their caches) holds the real table in **its own memory** and
  publishes an **atomic snapshot** outward. Every consumer keeps a **private read-only mirror** it
  never writes. Raw shared state tables would let multiple processes touch the same bytes —
  reintroducing locks, races, and torn reads, and reducing the single-writer principle to fiction.
- **Transport = ZeroMQ PUB/SUB** — brokerless (no message-server process to run or crash),
  publisher binds, consumers (Allocator, Limiter, strategies, dashboards) subscribe; updates fan
  out; freshness stamps ride each update; O(1) local reads, no cross-core contention.
- **Slow-joiner mitigation = snapshot-on-subscribe (mandatory, not polish):** plain PUB/SUB is
  fire-and-forget — a subscriber that isn't ready can miss messages. Publishers therefore emit a
  **full snapshot on subscribe** (plus periodic full-state refresh), so a restarted consumer is
  correct within seconds — it never waits for organic deltas and never sizes on a half-built
  mirror (mirror incomplete ⇒ treated as stale ⇒ fast-drop/deny until snapshot lands).
- **Sole exception — the price firehose:** capture.py → Risk Engine per-tick bars/prices stay on
  the **shared-memory single-writer ring buffer** (§10) — even ZeroMQ overhead is too much per
  tick. Strictly one writer by construction; prices only, never financial state.
- **Rule of thumb (NICS-wide):** hot per-tick single-writer data → shared-memory ring buffer;
  stateful tables → publish-and-mirror over ZeroMQ. Ownership and the single-writer guarantee stay
  airtight in both.

### 12.8 Anti-lockout review
Every blocking condition must have a defined exit: blackouts end by calendar; margin gates by
baseline-return or re-acceptance (§6.3); stale by feed recovery; HALT per §12.5. **No condition may
block trading forever without an operator decision.** (Soak test: §13.)

### 12.9 Observability — dashboards & alerting (v1.3, locked)
Read-only surface only — every panel consumes the **published snapshots** (financial picture,
ranking, tradability, health) via their read-only mirrors; **no dashboard ever writes state or
touches the hot path**. Dashboards live on the shared pool (Core 4–5), subscribe like any other
consumer, and get **snapshot-on-subscribe** so a freshly opened dashboard is correct immediately.

**Panel A — Money & safety (the "is my money safe" glance):**
- Live **balance**, **net-liq mark**, **Σ open margin**, and the **survival-floor headroom**
  (net-liq vs the force-flatten threshold) — the single most important number, shown with margin to
  spare / danger colouring.
- **Deployable liquidity** (70% cap headroom): committed vs remaining, and the aggregate-margin-cap
  utilisation as a percentage.
- **Per-bucket correlation load:** each bucket's Σ dollar risk vs its `bucket_cap_pct × balance`.
- **Day realized P&L** (the same realized figure that feeds Scoring) and open unrealized (display
  only — never a sizing input).

**Panel B — Positions & orders (the live book):**
- The **per-position table** straight from the snapshot: trade_id, symbol, strategy, size, entry,
  live stop (and, for trailing stops, current trail level vs high-water mark), margin, **lifecycle
  state** (reserved / pending / open / closing / closed), unrealized.
- **In-flight orders:** pending placements with age against the pending-timeout, partial-fill
  progress (filled vs requested), and any active reservations.

**Panel C — Strategies & scoring:**
- Per strategy: **state** (flat / in-flight / open / cooling-down / dead / quarantined), one-in-flight
  slot status, heartbeat freshness, restart count within the crash-loop window.
- **Ranking table** from the Scoring process: realized-P&L EMA and rank **per (strategy, symbol)
  pair**, with the per-symbol aggregate as a derived display row; a clear flag when Scoring is down
  and contention has fallen back to **FCFS**.

**Panel D — System & data health:**
- **Freshness stamps** for every critical feed: price firehose, live margin, calendar, balance —
  each with time-since-update against its stale threshold.
- **Process/core liveness:** capture.py (broker-datafeed), Risk Engine (broker-order), Allocator,
  Scoring, Sentinel, Postgres — up/down + heartbeat age, mapped to their cores.
- **HALT state** and its cause (stale / clock-skew / crash-loop / invariant / operator), plus which
  blackout windows are currently open (EOD / EOW / news-margin / roll).
- **Broker-session health:** connectivity, send-path latency, exec-report push-vs-poll mode,
  clock-skew vs venue time.

**Alerting tier (push, not glance) — things that must reach the operator unattended:**
- **Critical (page immediately):** survival-floor breach / protective flatten fired; Sentinel
  deadman fired; cold-start found an unexpected position (esp. held-in-HALT because market closed);
  broker session lost with positions open; HALT set by invariant breach.
- **Warning:** any feed stale ⇒ entries halted; strategy quarantined (crash-loop cap hit); Scoring
  down ⇒ FCFS fallback; aggregate-drift audit event; Postgres down ⇒ degraded persistence.
- **Info:** blackout window opened/closed; contract-roll seam; strategy restarted (below cap).
- Alerts carry the **cause and the relevant snapshot values**, not just a code, so the operator can
  triage without logging into the box. Alert transport is CC-defined (§13).

**Boundary (invariant):** observability is strictly read-only. It must never become a control path
— no dashboard button issues an order or clears a HALT; operator control is a separate, explicit,
authenticated path, never the monitoring surface.

### 12.10 Operational logging — two-plane model (v1.3, locked)

An events-of-interest audit found the Postgres event log covers **trade lifecycle only**; a long
tail of operational events (HALT transitions, strategy lifecycle, feed/session state, blackouts,
guard discards) had **no durable record anywhere**. Resolution: two planes, strictly separated.

- **Plane 1 — Financial event log (unchanged).** Postgres append-only, **Limiter sole writer**
  (§9). The auditable record of money truth. No new writers, ever.
- **Plane 2 — Operational log (new): journald/syslog via systemd.** Every process is already
  systemd-managed, so stdout→journald routing is free. Each process writes its **own** structured
  one-line events (UTC timestamp, process, event, key=value fields). No shared-writer problem:
  this plane is **diagnostic only — never a reconciliation input, never read by the trading path.**
  It survives Postgres outages (§12.4), giving continuity of record exactly when Plane 1 degrades.

**Event inventory — every event of interest and its plane(s):**

| Event | Plane 1 (event log) | Plane 2 (ops log) |
|---|---|---|
| signal / accepted / denied / filled / exit-intent / closed / protective-exit | ✅ | — |
| reservation taken / released | ✅ | — |
| cancels (incl. IOC remainder-cancel on partial fill) | ✅ *(added)* | — |
| GO-timeout | ✅ *(added)* | — |
| drift-audit event | ✅ | ✅ |
| Sentinel deadman flatten | ✅ *(via marker replay, §12.1)* | ✅ *(marker file)* |
| HALT set / cleared + cause | ✅ *(added — it gates money; Limiter-down ⇒ booked at next boot, §12.5)* | ✅ |
| operator control actions (HALT clear, quarantine restore) | ✅ *(added)* | ✅ |
| strategy lifecycle (register / force-deregister / kill / relaunch / quarantine / restore) | ✅ *(added)* | ✅ |
| crash-loop count / cap hit; heartbeat loss / orphan detect | — | ✅ |
| cold-start reconciliation outcome (unexpected position, held-in-HALT) | ✅ *(added)* | ✅ |
| blackout open/close; contract-roll seam | — | ✅ |
| feed staleness transitions; broker session lost/restored | — | ✅ |
| monotonic-guard discards (stale balance/margin/position dropped) | — | ✅ *(count + last-dropped)* |
| alerts (all tiers) | — | ✅ *(every alert also written — alert transport can fail; the log cannot)* |
| process start/stop/restart (systemd) | — | ✅ *(free)* |

**Rules.** Anything that *changes or gates money* gets a Plane-1 row (that's why HALT, operator
actions, strategy lifecycle, cold-start outcomes, cancels, and GO-timeouts were added). Anything
purely diagnostic stays Plane-2 only. Alerts are notifications *about* logged events, never a
substitute for logging. Per-tick trailing-stop ratchets are **not** logged (chatty, derivable);
the final trail level rides the `closed` row.

### 12.11 Operator control path — verbs & config lifecycle (v1.3, locked)

**The verb set is closed — exactly four:**
1. **`HALT set` / `HALT clear`** — operator-HALT clears only by operator (§12.5).
2. **`flatten-all`** — routes through the Limiter's existing protective-exit machinery,
   `reason=operator`. No special path; the operator's kill-switch is the same code that already
   protects money.
3. **`quarantine-restore`** — relaunch via supervision, re-register, **boots to flat** like any
   start; archived score rows return to the live ranking table (§6.6); crash-loop counter resets.
4. **`config-reload`** — a supervised **restart**, nothing else (see lifecycle below).

Anything else the operator wants is not a verb — it is an edit to config or code, taken through
restart.

**Transport:** authenticated messages to the **owning process** — financial verbs land at the
Limiter, which books the Plane-1 `operator action` row (§12.10 inventory); lifecycle verbs land at
supervision. Never via the dashboard — the §12.9 read-only boundary stands.

**Config lifecycle (locked): boot-loaded, restart-only.** No hot-reload — a mid-session change
would let two decisions inside one open trade read different tunables. Restart is already safe by
design (boot-flatten + cold-start reconciliation), so `config-reload` *is* a restart. The **config
version is stamped into the boot event** (Plane-1), so every subsequent row is traceable to the
exact tunable set it ran under. §6.3's baseline re-acceptance remains the sole runtime-adaptive
value — explicitly *state*, not config.

---

## 12A. Configuration Parameters (single source of truth for tunables)

Every knob referenced inline elsewhere lives here with its default and meaning. Values marked
**CC-calibrate** are placeholders until measured on node02 (see §13); the parameter name is stable.
**Lifecycle (§12.11): values load at boot; changes take effect only through restart.** Boot
validation (incl. the §6.1b ordering invariant) rejects an invalid set before any strategy registers.

**Risk / sizing**
- `PER_TRADE_RISK_$` — dollars risked per trade (sizing numerator). CC-calibrate.
- `SLIPPAGE_PAD_TICKS` — per-symbol pad added to stop distance so `risk_$` is honest through spikes.
- `SYMBOL_CAP` — per-symbol max contracts. CC-calibrate.
- `MICRO_FULL_THRESHOLD` / `QUANT_TOLERANCE` — fulls-vs-micros selection (§7). CC-calibrate.

**Liquidity / survival (§6.5)**
- `DEPLOYABLE_PCT` = 0.70 (30% buffer). `AGG_MARGIN_CAP_PCT` = 0.70 of balance.
- `NETLIQ_SAFETY_PAD` — force-flatten fires at `net_liq < Σ open margin × (1 + pad)`, ahead of broker.
- `LEDGER_DRIFT_TOLERANCE` — reconcile drift that raises an audit event.

**Correlation (§7)**
- `BUCKET_CAP_PCT[bucket]` — per-bucket ceiling as fraction of balance (equities/energy/metals/rates).

**Blackouts (§6.1–6.3)**
- `EOD_BLACKOUT_MIN` = 20 (per-symbol override); equity-index margin snap ref **3:45 PM CST**.
- `SESSION_FLATTEN_LEAD_MIN` = 10 (per-symbol override) — session-close force-flatten lead (§6.1b).
  CC-calibrate vs observed close liquidity/slippage. Boot-validated `< EOD_BLACKOUT_MIN − pad`.
- `EOW_BLACKOUT_MIN` = 30 before Friday close. `NEWS_BLACKOUT_MIN` = 20 before scheduled event.

**Feeds / staleness (§6.4, §12.3)**
- `MARGIN_STALE_MS`, `CALENDAR_STALE_MS`, `PRICE_STALE_MS`, `BALANCE_STALE_MS` — per-feed stale
  thresholds (stale ⇒ halt+flatten). `CLOCK_SKEW_MAX_MS` — skew that forces stale-class HALT.
- `RETRY_BACKOFF` — retry policy before declaring stale.

**Timeouts / liveness (§4, §12)**
- `PENDING_ACK_TIMEOUT_MS` (~1–2s) / `FILL_TIMEOUT` (order-type-dependent) — status query, never resend.
- `GO_TIMEOUT_T` — strategy resets to flat-and-free if no feedback within T. CC-calibrate.
- `HEARTBEAT_INTERVAL` = 1s; `HEARTBEAT_MISS_GRACE` = 1 cycle before presumed-dead.
- `CRASH_LOOP_MAX` = 3 restarts; `CRASH_LOOP_WINDOW` — window over which they count. CC-calibrate.

**Scoring (§6.6)**
- `SCORE_EMA_SPAN_DAYS` = 10 trading days (~2 weeks), tunable.

**Cooldown (§4)**
- `COOLDOWN_MIN_TIME` floor + condition-clear (hybrid), per exit class. CC-calibrate.

---

## 12B. Build Sequencing — Risk Subsystem Arcs (mega-arcs for Claude Code)

Ordering principle: **scaffold the seams first, prove the safety spine before any strategy trades,
layer optimisation last.** Every arc is sized as large as **file-set disjointness** safely allows;
sub-agents run in parallel where trees don't collide; each arc opens with **Phase 0** baselining
(registered gates, prove_* harnesses, lint) on a pristine tree, and closes on measurable pass
criteria. All development runs behind the **IBKR scaffold** — plumbing only; strategy validity waits
for DataBento. Each arc carries its PROGRESS in the title block (module + overall, from% → to%).

**ARC R1 — Seams & skeleton (mega).** broker-order + broker-datafeed vendor-neutral libraries behind
the IBKR scaffold; process/core map (Core 1 capture, Core 2 Risk Engine, Core 3 Allocator, 4–5 pool);
ZeroMQ pub/sub bus + snapshot-on-subscribe; shared-memory price ring buffer. **Done when:** processes
launch pinned to cores, a tick flows capture→ring→Risk Engine, and a stub snapshot mirrors to a
consumer. Verifies V24–V25, V26 (transport), V31 (slow-joiner).

**ARC R2 — Limiter safety spine (mega).** Canonical position state; two-phase rule manifest (size-
independent → size-dependent); synthetic stops (fixed + trailing) with per-tick maintenance;
protective flatten; net-liq survival watch; event-sourced log (sole writer) + WAL/Postgres
projection; cold-start broker reconciliation with market-tradable guard. **Done when:** every
protective path fires correctly in simulation and cold-start asserts provably-flat before
registration. Verifies V33 (stops), V34 (cold-start).

**ARC R3 — Allocator, sizing & financial picture (mega).** Permissive sizing (risk/margin/cap);
single-instrument selection; the unified atomic financial-picture snapshot (balance + positions +
reservations + per-symbol margin); hybrid balance refresh with monotonic-by-source guard;
correlation-bucket caps; liquidity governor. **Done when:** a GO sizes end-to-end, the gate reads one
coherent snapshot, and reservations release correctly on partial fills. Verifies V26 (coherence),
V27 (balance guard), V32 (margin coherence), V35 (correlation).

**ARC R4 — Blackouts, pollers & non-stop (mega).** EOD/EOW/news-margin blackout calendar;
**session-close flatten (§6.1b)**; live-margin
+ calendar pollers with stale⇒halt+flatten; contract rolls; Sentinel deadman; supervision + crash-
loop breaker; clock integrity; HALT semantics; anti-lockout. **Done when:** every blocking condition
has a proven exit and Sentinel flattens on a killed Risk Engine. Verifies the non-stop §12 objectives.

**ARC R5 — Scoring, feedback recovery & observability (mega).** Scoring process (per-day realized-P&L
EMA, ranking table) with FCFS fallback; strategy-death recovery (flatten→deregister→relaunch,
quarantine, score archive); full feedback broadcast; read-only dashboards + three-tier alerting.
**Done when:** killing Scoring keeps order flow on FCFS, a strategy-death drill recovers cleanly, and
dashboards render from mirrors only. Verifies V28, V29–V30 (recovery), V36 (observability).

**ARC R6 — Hardening & soak (mega, gate to prod-vendor cutover).** Full Tier-2 heavy gate across the
subsystem; multi-day soak; burst/backpressure drills; reservation-leak property tests; latency
benchmarks. **Done when:** the whole §13 objective bank is green under soak. This arc gates the two
independent cutovers (IBKR→Tradovate, IBKR→DataBento), each its own follow-on arc.

---

## 13. CC Verification Objectives (measure on node02 — never assume)

1. `productMarginItems` batch behavior + achievable poll cadence.
2. Live CL/GC/ZN day margins (peer-broker figures are estimates).
3. Per-symbol close-snap + session/Fri/Sun times from live calendar.
4. Tradovate margin-event calendar: API-accessible, or external econ feed required?
5. Per-symbol margin baseline + elevation threshold + **stable-elevated re-acceptance period**.
6. Balance/liquidity endpoint + cadence; Σ open margin readable live; **net-liq mark vs broker's
   own net-liq: reconcile within tolerance**.
7. Staleness thresholds from measured round-trips; retry/backoff before "stale".
8. Execution reports: push (subscribe) vs poll; latency envelope; **user-sync websocket existence**.
9. Partial-fill + remainder-cancel behavior on marketable orders.
10. Strategy heartbeat + orphan detection latency; **GO-timeout T calibration**.
11. broker-order send path non-blocking under stalled socket (stop loop keeps protecting) — critical.
12. ZMQ transport (inproc/ipc/tcp) within entry budget under 3-symbol burst.
13. Live vs backfilled Renko/M1 bit-identical across seam (Luna regression).
14. Shared-memory ring buffer under burst: no torn reads / starvation.
15. End-to-end entry latency proven cache-reads+arithmetic.
16. Running aggregates (incl. reservations, net-liq) reconcile vs full-scan audit.
17. Service audit/mask on headless 26.04 (kept-vs-killed documented).
18. **Roll schedule source via API; front-month volume-leader detection; atomic identity switch.**
19. **Sentinel drill:** kill Risk Engine with a paper position open ⇒ Sentinel flattens within bound.
20. **Crash-loop breaker drill** + **clock-skew injection drill** ⇒ HALT fires correctly.
21. **capture.py throughput under peak tick burst in Python** (Cython/native fallback decision).
22. **Soak test (multi-day paper):** memory/fd stability, WAL rotation, no aggregate drift, no
    permanent-lockout state reachable (§12.8).
23. **Reservation-leak hunt:** property test — every reservation reaches exactly one terminal
    release across all failure paths.
- V24. broker-order / broker-datafeed run in separate processes on separate cores; kill/reconnect
  the datafeed under load and prove the order path is undisturbed (latency + zero missed exits).
- V25. Vendor-neutral seam: same interface satisfied by IBKR scaffold and by Tradovate/DataBento;
  swap is config, not code.
- V26. Atomic financial-picture snapshot: Allocator mirror is self-consistent (balance ↔ positions
  ↔ reservations) under burst; no torn reads.
- V27. Balance monotonic-by-source guard: inject an out-of-order late poll and prove the older value
  is discarded.
- V28. Scoring process: EMA (per-day, span-configurable) computed off-hot-path; ranking-table lookup
  is O(1) on both Allocator and Limiter; kill Scoring and prove FCFS fallback keeps trading.
- V29. Strategy-death drill: kill a strategy holding an open position; prove flatten → deregister →
  relaunch ordering, no stale keyed state survives deregistration, restart boots to flat, and the
  EMA receives only the flatten fill (no phantom entry from the death itself).
- V30. Crash-loop → quarantine drill: force 3 restarts inside the window; prove quarantine (dead,
  flat, alerted), removal from the live ranking table, score archived and restorable, and the rest
  of the system trades on undisturbed.
- V31. Slow-joiner drill: restart the Allocator mid-session under active publishing; prove
  snapshot-on-subscribe yields a correct mirror within seconds and that a half-built mirror is
  treated as stale (fast-drop/deny) until the snapshot lands.
- V32. Margin coherence: prove Allocator and Limiter read the SAME versioned per-symbol margin from
  the unified snapshot (never two sources); inject a margin update mid-sizing and confirm the sizing
  pass and the gate evaluate against one internally coherent snapshot (no fresh-margin/stale-balance
  cross-table skew).
- V33. Stop semantics: prove fixed stops anchor once at fill; trailing stops hold at initial_distance
  until the trail would sit tighter, then ratchet behind the high-water mark and never regress;
  distance→price conversion uses the confirmed fill (never the pre-fill signal price).
- V34. Cold-start reconciliation: boot the system with an open broker position and prove (a) the
  mandatory broker query runs before any strategy registers, (b) an unexpected position is flattened
  to flat, and (c) if the market is closed the system holds in HALT with alert and flattens only once
  tradable — never firing into a shut market.
- V35. Correlation-bucket cap: prove within-bucket dollar risk is summed correctly (micros at 1/10),
  a proposal that would breach `bucket_cap_pct × balance` is sized down then denied, and positions in
  different buckets do NOT constrain each other through this rule (only via the portfolio layers).
- V36. Observability: prove every dashboard panel is fed only by read-only snapshot mirrors (no hot-
  path reads, no state writes), a freshly opened dashboard is correct via snapshot-on-subscribe, and
  the critical alert tier fires on survival-floor breach, Sentinel firing, and cold-start-in-HALT.
V37. **Two-plane logging drill (§12.10, §12.1):** (a) fire every inventory event in a harness and
assert each lands on its mapped plane(s); (b) kill the Risk Engine with positions open, let the
Sentinel flatten, reboot — assert the marker file replays into the event log as `source=sentinel`
rows and the marker archives; (c) drop Postgres mid-session — assert Plane-2 continuity.
V38. **Session-close flatten drill (§6.1b):** hold a position into the flatten window ⇒ flat by
close with `reason=session` Plane-1 rows; config validation rejects `SESSION_FLATTEN_LEAD_MIN ≥`
blackout lead; indeterminate-during-session-flatten resolves via §4 to confirmed flat.

---

## 14. Locked Invariants (do not violate)

- Nothing reaches broker-order without passing the Limiter.
- Every uncertainty resolves toward **flat**. Known state beats optimal state.
- The exit/protective path has **zero wire/delivery dependency**.
- "Open" = **confirmed fill** only. Never optimistic.
- One in-flight action per strategy — and it can never wedge (GO-timeout).
- Restart = flat, always.
- **Every reservation reaches exactly one terminal release.**
- **Survival is watched on net-liq; sizing is computed on cash.** Never conflate.
- Brick/candle formation is one shared library; live == historical by construction.
- Hot path = cache reads + arithmetic only.
- Detection may live anywhere; **execution of any flatten is Limiter-only** (Sentinel excepted, as
  last resort when the Limiter itself is dead).
- **No condition may block trading forever without an operator decision.**

---

## 15. Audit v1.1 Changelog

**Critical corrections:**
- C1 Margin **reservation lifecycle** added — committed = open + pending reservations; release on
  every terminal path (double-spend race closed). §3, §6.5, §11, invariant.
- C2 Survival floor corrected to **net-liq** (cash doesn't erode with price; broker liquidates on
  net-liq). Sizing stays on cash. §6.5, invariant.
- C3 Sizing guards: zero/invalid stop ⇒ deny; missing margin ⇒ not-tradable; clamp ≥ 0. §7.
- C4 **Blackout onset cancels pending entry orders.** §3, §6.1.
- C5 **Contract rolls** — front-month identity, roll-day blackout, atomic switch, Renko roll seam.
  §7.5, CC-18.
- C6 **GO-timeout** — lost-GO deadlock on the one-in-flight lock broken. §4, CC-10.
- C7 **Baseline re-acceptance** — permanent margin-regime shift cannot lock the system out. §6.3.

**Non-stop additions (§12):** Sentinel deadman (CC-19), supervision + crash-loop breaker (CC-20),
clock integrity/UTC discipline (CC-20), Postgres-down = degraded persistence not trading,
disk-critical ⇒ HALT, HALT set/clear semantics, exchange-halt awareness, anti-lockout review (CC-22).

**Accuracy/efficiency:** slippage pad in sizing; micro/full selection rule defined; explicit
threading model (single-threaded Limiter loop + low-priority sender; single-threaded Allocator =
lock-free contention); push-preferred websocket updates (CC-8); commission/fee accounting +
ledger reconcile; post-open warmup (configurable); idempotent exec-report dedup; reservation
property test (CC-23); capture throughput benchmark (CC-21); soak test (CC-22).

**Audited, unchanged:** two-phase gate; in-process broker + sender (GIL acceptable — I/O-bound);
O(1) hot-path claims (hold with running aggregates); stop-eval O(positions≤5)/tick; partial-fill
cancel race (self-healing under reservations).

---

## 16. ULTRAREVIEW v1.2 Changelog (Allocator optimality pass)

**Found & fixed:**
- U1 **Routing ping-pong eliminated.** v1.1's literal pathway implied Strategy→Limiter→Allocator→
  Limiter (two cross-core round-trips, 3–4 hops). v1.2 = **single-pass**: Strategy→Allocator→Risk
  Engine→broker (2 hops). Two-phase rule *logic* preserved inside the manifest (Phase A size-
  independent before Phase B size-dependent); "never size a dead signal" preserved by the
  fast-drop against the same cache. §3.
- U2 **Committed-margin visibility for the Allocator.** Headroom now = 0.70×balance − committed
  (open + reservations) read from a Limiter-published cache — kills systematic size-down churn at
  the gate. One source of truth. §3, §11.
- U3 **Cache transport defined** — PUB/SUB per-process mirrors, freshness stamps, snapshot-on-
  subscribe; restart rebuild bounded, half-built mirror = stale. §12.7.
- U4 **Single-instrument preference** replaces mixed full+micro legs — commission drag (10 micro
  RTs ≈ 2–4× one full RT) and dual order-lifecycle complexity beat the marginal granularity gain.
  §7.
- U5 **Sizing rationale rides the order message** (binding constraint + input snapshot) so the
  Limiter's event log audits sizing without breaking sole-writer. §3, §9.

**Attacked & upheld (no change):** separate-process Allocator (fault isolation > µs hop);
single-threaded Allocator (µs sizing, no saturation at N≤5); static correlation caps
(dynamic correlation = research project, violates determinism); reservation placement in Limiter
(authority stays prohibitive-side; U2 gives the Allocator visibility without authority);
per-GO-only Allocator work (zero per-tick load — optimal). (Contention arbitration was revisited in
v1.3 — see §6.6: performance-weighted scoring off the hot path, with FCFS retained as the fallback.)

---

## 17. v1.3 Session Changelog (broker split · full financial picture · performance contention)

**Naming / project.** Renamed **Io → NICS**. Development uses **IBKR** as a free scaffold behind
*both* library seams, then splits to prod vendors in two independent cutovers.

**Broker split (locked).** The former single `broker.py` is split into two vendor-neutral libraries
with separate processes, cores, and failure domains:
- **broker-order** — execution + account management (orders, fills, positions, margin, balance).
  Lives in the Risk Engine process, Core 2. IBKR (scaffold) → **Tradovate** (prod).
- **broker-datafeed** — streaming market data only. Lives **inside the capture.py process**, Core 1.
  IBKR (scaffold) → **DataBento** (prod).
- Rationale: **stability** is the primary prize — a datafeed reconnect storm / firehose backpressure
  / malformed tick cannot stall or crash the order path (process + core isolation). "Speed" is only
  the second-order benefit of the order path no longer *contending* with the firehose (no shared
  socket/lock, no GIL time lost decoding ticks while an exit fires) — splitting the libraries is not
  itself faster. Isolation is load-bearing, so the two must not share a thread or core.
- Only built bars cross Core 1 → Core 2 (shared memory); never a shared socket. Ticks never source
  from the order vendor.

**Full financial-picture publish (locked).** The Limiter (sole writer of canonical state) now
publishes ONE atomic snapshot the Allocator mirrors continuously: **live balance + per-position
table (trade_id → symbol, strategy, size, margin, state) + Σ margin + Σ reservations + committed +
uncommitted liquidity**. The Allocator must know the complete finances of the system at all times,
across the full lifecycle (reserved/pending/open/closing/closed) — not just an aggregate margin
scalar. Balance and table publish together (atomicity rule) so headroom is never computed off a
stale/fresh mismatch. Authority intact: Limiter writes truth, Allocator reads mirror. §3.

**Balance refresh = hybrid (locked).** Event-driven on every money-moving trade event **plus** a
slow periodic poll, reconciled by a **monotonic-by-source guard** (venue timestamp/sequence;
discard any reading older than the one held) so balance never regresses. §6.4b.

**Performance-weighted contention (locked).** Dedicated **Scoring process** is sole writer of a
continuously updated ranking table = **realized-P&L EMA per (strategy_id, symbol) pair** (keying
locked in ULTRAREVIEW-2 D2), advances **per day**, span =
variable defaulting to **10 trading days**. Allocator reads it to weight sizing; **Limiter reads it
to arbitrate** contention (both O(1) lookup, neither computes). **Fallback = first-come-first-served**
when the process/table is unavailable — order flow never halts. §6.6.

**Sizing pathway ordering (reaffirmed, not changed).** Cheap size-independent checks (fast-drop) →
size → authoritative size-dependent gate. A dead signal is never sized; size-dependent rules (margin
ceiling, survival floor, correlation) cannot be evaluated without a size, so they necessarily follow
sizing. Operator-confirmed after audit.

**Partial fill (locked).** Reported as fact, never negotiated: position = actual filled qty,
remainder cancelled, strategy informed and its **FSM owns the smaller-than-requested state** (no
Limiter auto-top-up). Real-time Allocator reflection — the unfilled reservation releases on fill
confirmation, over-reserved capital returns to deployable instantly. §4.

**Feedback-path audit (locked).** Indeterminate ⇒ flatten-on-uncertainty with **full broadcast**
(strategy hard-reset + slot freed; Allocator mirror updates; event log; Scoring books any real
fill) and **reconcile-then-publish-confirmed-truth** — the broadcast carries what the broker
confirms, never "we flattened." **Every reconciliation event pulls broker-authoritative balance AND
positions** (uniform, cheap, off-hot-path; broker truth beats local projection beyond tolerance).
**Orphan recovery** = one-cycle heartbeat grace → **flatten → force-deregister → kill → relaunch**
(money made safe first; no stale state survives; clean re-entry to flat). **Crash-loop cap**: 3
restarts in a tunable window ⇒ **quarantine** (dead & flat, alert, removed from the live ranking
table so it can't win capital it can't use; **score archived, not destroyed** — operator-driven
return only). Score **persists across death/restart** (it belongs to strategy-trading-a-symbol, not
a process instance; a crash is operational, not a trade verdict, and writes **nothing** to the EMA
— only real fills do). Every recovery step is visible in the Allocator mirror as it happens;
mid-recovery positions show as **in-flight-closing**, never "available." §4.

**Broker abstraction contract defined (locked).** Added §2A: the method-and-event signature both
libraries implement so vendor swap is config not code. **broker-order** commands (connect, place_order,
cancel_order, flatten, query_positions, query_balance, query_order_status, get_margin) + pushed events
(on_ack, on_fill idempotent by order_id/exec_id, on_cancel, on_balance w/ venue seq, on_position,
on_session). **broker-datafeed** commands (connect, subscribe/unsubscribe) + events (on_tick,
on_feed_status). Push/callback model, no vendor type crosses the line, order/datafeed contracts
disjoint, venue-sourced timestamps, non-blocking send. Locks the V25 vendor-neutral seam at method level.

**Build sequencing added (locked).** Added §12B: six mega-arcs for Claude Code — R1 seams & skeleton,
R2 Limiter safety spine, R3 Allocator/sizing/financial-picture, R4 blackouts/pollers/non-stop, R5
scoring/feedback-recovery/observability, R6 hardening & soak (gates the Tradovate/DataBento cutovers).
Scaffold-first, safety-spine-before-trading, optimisation-last; each arc Phase-0 baselined, sized by
file-set disjointness, sub-agents parallel, PROGRESS in the title block; each maps to §13 verifications.

**Configuration parameters centralised (locked).** Added §12A: a single source-of-truth list of
every tunable (risk/sizing, liquidity/survival, correlation, blackouts, feeds/staleness, timeouts/
liveness, scoring, cooldown) with stable names + defaults; CC-calibrate values are placeholders
until measured on node02. Inline mentions now point at named parameters rather than scattered magics.

**Observability — dashboards & alerting (locked).** Added §12.9: a strictly **read-only** monitoring
surface built on the published snapshots (snapshot-on-subscribe; never writes state or touches the
hot path). Four dashboard panels — **A** money & safety (balance, net-liq, survival-floor headroom,
deployable liquidity, per-bucket correlation load, day realized P&L), **B** positions & orders (live
per-position table incl. trailing-stop level, in-flight/partial-fill/reservations), **C** strategies
& scoring (strategy states, heartbeats, restart counts, ranking table + FCFS-fallback flag), **D**
system & data health (feed freshness, process/core liveness, HALT cause, open blackouts, broker
session). Three-tier **alerting** (critical page / warning / info) carrying cause + snapshot values.
**Invariant:** monitoring is never a control path — operator control is a separate authenticated path.

**Correlation-bucket cap (locked — formula).** Exposure measured in **dollar risk**
(`(stop_ticks+slippage_pad)×tick_value×contracts`, micros at 1/10). Cap is **same-bucket only** and
expressed as a **percent of balance**: `Σ dollar_risk(open+pending in bucket) + proposed ≤
bucket_cap_pct × balance`. Different buckets don't constrain each other here — cross-bucket total is
governed by the portfolio layers (70% deployable, aggregate margin cap, net-liq floor). Buckets:
equities {ES,NQ}, energy {CL}, metals {GC}, rates {ZN}. §7.

**Cold-start reconciliation (locked).** On boot the Limiter **actively queries the broker for the
true open-position set + balance** (local state is trustless at start, so the broker's answer *is*
the record) and this gates registration. Already flat ⇒ assert and proceed. Any unexpected open
position ⇒ **flatten to flat before any strategy registers** (never adopt an inherited position),
**guarded by market-tradability** — if the market is closed/halted the system **holds in HALT with a
loud alert** and flattens the instant it can trade, never firing orders into a shut market. §4.

**GO message contract (locked).** Defined the strategy→Allocator trust boundary: direction, symbol,
strategy_id, signal_ts, and **stop intent as a tick DISTANCE (never absolute price)** converted to a
price by the Limiter at fill. **`stop_mode` is strategy-chosen per signal:** *fixed* (anchored once
at fill) or *trailing* (separate `initial_distance` + `trail_distance`; holds at initial until the
trail would sit tighter, then ratchets behind the high-water mark, only ever moving in favour).
Limiter validates and owns conversion/placement/maintenance. §4.

**Live per-symbol margin transport (locked).** Live current margin per symbol rides **inside the
one unified financial-picture snapshot** (one writer = Limiter, one version stamp across balance +
positions + reservations + margin), NOT as a separate table or its own shared-memory block.
Allocator (sizing) and Limiter (gate) read the identical versioned row from their read-only mirrors
— no cross-table skew, no reader traffic on the hot gate's cache lines. Price firehose stays the
sole raw-shared-memory exception. §6.4, §3.

**State-table transport (locked).** **ZeroMQ plain PUB/SUB + snapshot-on-subscribe, mirror model**
is the standard for ALL state tables; **no raw shared memory for state tables** (would break
single-writer); **no heavier delivery-guarantee layer** (snapshot supplies the correctness). Sole
exception: the per-tick price firehose stays on the shared-memory single-writer ring buffer. §12.7.

**Two-plane logging (locked, post-ULTRAREVIEW audit).** An events-of-interest sweep found only
trade-lifecycle rows were durably recorded. Plane 1 = Postgres event log (Limiter sole writer,
financial truth — extended with cancel, GO-timeout, HALT, operator-action, strategy-lifecycle,
cold-start-outcome rows). Plane 2 = journald/syslog operational log (each process writes its own,
diagnostic only, never a reconciliation input, survives Postgres outage). **Sentinel sole-writer
gap fixed:** local append-only marker file, replayed into the event log by next cold-start
(`source=sentinel`). Rule: anything that changes or gates money ⇒ Plane-1 row. §12.10, §12.1, §9, V37.

**Session-close flatten (locked, ULTRAREVIEW-2 D1).** The intraday-only mandate gains its missing
enforcement: at `SESSION_FLATTEN_LEAD_MIN` (default 10, per-symbol, CC-calibrate) before each
symbol's close, the Limiter force-flattens that symbol, `reason=session`. Boot-validated ordering
`flatten lead < entry-blackout lead − pad`; failure ladder reuses §4 indeterminate machinery and
§12.6 halted-market honesty. A position lifecycle cannot cross a session boundary by construction.
§6.1b, §12A, V38, arc R4.

**Ranking-table keying (locked, ULTRAREVIEW-2 D2).** Canonical key = **(strategy_id, symbol)** —
one EMA row per pair. Resolves the per-symbol vs strategy×symbol contradiction: score persistence
across death and quarantine row-removal both hold verbatim; per-symbol figures are derived display
aggregates. Arbitration compares the competing pairs' rows; equal/absent ⇒ FCFS. §1, §6.6, §12.9.

**Operator control path & config lifecycle (locked, ULTRAREVIEW-2 D3).** Closed verb set: HALT
set/clear, flatten-all (via existing protective-exit, `reason=operator`), quarantine-restore
(restart-to-flat, score rows return, counter resets), config-reload (= supervised restart).
Authenticated messages to the owning process; Limiter books the Plane-1 rows; never via dashboard.
**Config is boot-loaded, restart-only** — no hot-reload; config version stamped into the boot
event. §12.11, §12A.

**HALT-while-Limiter-down (locked, ULTRAREVIEW-2 D4).** Fail-closed by construction (no Limiter ⇒
nothing reaches the broker); the Plane-1 `HALT set` row books retroactively at next boot via
cold-start reconciliation — Sentinel-marker pattern, sole-writer intact. §12.5, §12.10.
