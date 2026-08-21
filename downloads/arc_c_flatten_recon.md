# ARC C — flatten-producer reconnaissance (produced by ARC 052, Task 4)

READ-ONLY survey. Every claim below cites a file:line that was opened and read in
this pass. Interpreter `/home/bbt/nix/.venv/bin/python` was not needed — nothing
here was executed; the survey is static.

The single structural fact that governs all four questions:

> **`scripts/limiterd.py` imports no gate, no flatten, and no freshness.**
> Its import block (`scripts/limiterd.py:126-172`) is `completions`, `execution`,
> `fills`, `join`, `loop`, `outcomes`, `picture`, `positions`, `recovery`
> (`RecoveryError` only), `reservations`, `seam`, `stops`, `wal`,
> `nixsentinel.heartbeat`. There is no `nixrisk.gate`, no `nixrisk.flatten`, no
> `nixrisk.freshness`, no `nixrisk.session`.

So the running daemon has **no protective-exit path at all**, and the whole of
`flatten.py` is reachable in this tree only from tests and gates.

---

## 1. D3.453 — the `STALE_PRICE` producer

### 1.1 Where "stale" is decided

`scripts/nixrisk/freshness.py:528` `class FreshnessTracker` — the detector.
The verdict is produced by one method:

- `scripts/nixrisk/freshness.py:573` `FreshnessTracker.reading(feed, symbol="") -> FreshnessReading`
  — *"This feed's freshness at `clock()`. ONE subtraction, no aggregate."*

The returned value type is `scripts/nixrisk/freshness.py:503`
`@dataclass(frozen=True) class FreshnessReading` with fields
`feed, key, state, blocked, reason, age_ms, threshold_ms, deadline_ms`
(`freshness.py:517-524`). Its docstring draws the vocabulary distinction ARC C
must respect (`freshness.py:509-512`):

> `state` is what the cache IS (§6.4's freshness stamp past threshold);
> `blocked` is what the gate DOES (§6.4's halt, which sits behind the retry ladder).

Four verdict branches in `reading`, in order:

| branch | file:line | `state` | `blocked` |
|---|---|---|---|
| never observed | `freshness.py:578-591` | `CacheState.EMPTY` | `True` |
| stamp ahead of local clock past `CLOCK_SKEW_MAX_MS` | `freshness.py:598-613` | `CacheState.STALE` | `True` |
| `age_ms <= threshold` | `freshness.py:615-625` | `CacheState.FRESH` | `False` |
| past threshold | `freshness.py:627-652` | `CacheState.STALE` | `blocked = age_ms > deadline` |

The **flatten-open sentence lives in the reason string and nowhere else** —
`scripts/nixrisk/freshness.py:633-634`:

```
"{deadline:.0f} ms retry/backoff deadline. §6.4: stale => halt "
"new entries AND flatten open"
```

That is the whole of "flatten open" in this module: a substring.

### 1.2 The spec half ARC C must implement

Frozen spec, `docs/nics_risk_subsystem_spec_v1.3.md`:

- `:298` — `- **Stale price / stale margin ⇒ halt new entries + flatten open** (§6.4).`
- `:368` — `### 6.4 Live-margin & calendar pollers + stale ⇒ halt+flatten`
- `:373-374` — `- Allocator/Limiter **read caches only**. **Stale (freshness stamp past threshold, after retry/backoff) ⇒ halt new entries AND flatten open.** Detection = system; execution = Limiter.`

### 1.3 What exists today

**Consumer that acts on the stale verdict — ONE, and it is the entries half only.**

- `scripts/nixrisk/freshness.py:660` `class StalenessFlagPort` — *"§6.4's stale condition as `gate.SymbolFlagPort`. `read(symbol)`."*
  - `freshness.py:672` `def __init__(self, tracker: FreshnessTracker) -> None` — **one collaborator, the tracker. No picture, no position book, no executor.**
  - `freshness.py:686` `read(symbol) -> tuple[bool, str]` returns `(blocked, joined reasons)`.
- `scripts/nixrisk/gate.py:1156` is the only consumer shape:
  `SymbolFlagRule("data_staleness", staleness, "§6.4 stale-data halt")`,
  inside `gate.py:1121 default_manifest(...)`.
- `SymbolFlagRule` (`gate.py:305`) is a **pre-size deny rule**. It blocks a
  `ProposedOrder`. It cannot close anything.

**Is an open position visible at that point? NO.** `StalenessFlagPort.read`
sees `FreshnessTracker` → `SourceMonotonicGuard` → stamps. The §3 position table
lives on `FinancialPictureBook` / `FinancialPicture.positions`, which this port
never touches. `freshness.py` does not import `picture`, `flatten`, or `seam`'s
`PositionState`.

**Is `default_manifest`/`GatePass` even running in production? NO.** Only
`scripts/plane1_degraded_drill.py:820,862`, `scripts/plane1_hotpath_drill.py:242,253`
and `checks/check_allocator_sizing.py:944,955` construct them.

**Is the tracker running in production? NO.** The only non-test importer of
`nixrisk.freshness` is `scripts/nixrisk/pollers.py:145`
(`from nixrisk.freshness import FreshnessTracker, StalenessUsageError`), and
`nixrisk.pollers` has **zero** non-test importers. `checks/uncalled_entry_points_baseline.json:591-593`
says so in its own reason field:

> "The module has exactly one importer in the tree (pollers.py), which itself has no production importer."

**Nothing fires `STALE_PRICE`.** `FlattenTrigger.STALE_PRICE` is declared at
`scripts/nixrisk/seam.py:627` (member of the seven-member enum at `seam.py:608`).
A tree-wide grep for `STALE_PRICE` hits exactly two lines: that declaration and
a parametrize entry at `scripts/tests/test_flatten.py:374`. It is **not** in
`flatten.py:143 _R4_TRIGGERS` (which holds only `SENTINEL`, `flatten.py:143`), so
the executor accepts it — `checks/check_flatten.py:1148` classifies it
`"stale_price": "fireable"` — and no line joins detector to executor.

Two more places in the tree state the gap in prose:

- `scripts/nixrisk/calendar_seam.py:112` — `§6.4: stale ⇒ halt new entries AND flatten open.`
- `scripts/nixrisk/calendar_seam.py:192-196` — *"§6.4 makes stale a HALT-and-flatten condition … here, the book gets flattened."*
- `risks/staleness.config.json` `_meta.still_not_implemented_here` — *"Detection is not execution. §6.4:374 assigns execution to the Limiter, so nothing in this subsystem halts or flattens: it produces the CONDITION and scripts/nixrisk/flatten.py plus the HALT state machine consume it."*

### 1.4 D3.453's residual, quoted

From `docs/CHECK-DEBT.md:945` (row `D3.453`, owner ARC 049, area `limiter`):

> **`FlattenTrigger.STALE_PRICE` is a §3 protective trigger that NOTHING in this tree ever fires — not shipped code, not a check, not a test drive: the detector exists, the executor accepts it, and no line joins them**

> "What has no route is the CALLER: `grep -rn STALE_PRICE` over the tree hits exactly TWO lines — the enum member at `seam.py:627` and a parametrize list at `scripts/tests/test_flatten.py:374`. `scripts/nixrisk/freshness.py:573` `FreshnessTracker.reading` computes staleness and `freshness.py:661`'s `StalenessFlagPort` feeds `gate.py` as a `SymbolFlagPort`, which BLOCKS NEW ENTRIES; §6.4's other half — flatten what is already open — has no implementation and `freshness.py:633` and `calendar_seam.py:112,196` both say so. This is NOT the same shape as D3.179 (`unstopped()` has a record and no consumer) or D3.451 (`StopBook.breached` has a consumer nowhere near a price poll): here the trigger has no producer at all, so the gap is invisible to `check_uncalled_entry_points`, which looks for uncalled ENTRY POINTS and not for unreachable ENUM MEMBERS. Recorded rather than fixed: wiring it needs the §6.4 staleness-to-flatten policy (which reading, which grace, whose deadline) and that is an architect ruling, not a local edit."

> "**I3 is unaffected** — I3 is about whether the exit path carries a wire, and ARM 6 proves `STALE_PRICE` flattens wire-dead the moment anything fires it."

### 1.5 The exact seam ARC C must build

There is **no seam today**. The seam has to be a new object holding three things
`StalenessFlagPort` deliberately does not hold: the reading, the open book, and
the executor. **`scripts/nixrisk/session.py` is the exact working template** and
should be copied in shape, not invented:

- `scripts/nixrisk/session.py:410` `class SessionFlattener` — *"§6.1b's deadline. DETECTION here; EXECUTION stays in `flatten.py` (§14)."*
- constructor `session.py:433-444`: `calendar`, `venue`, `book: OpenBookReadPort`, `executor: ProtectiveFlatten`, `alert: AlertSink`, `lead_min`, `symbols`, `clock`
- `session.py:617` `_open_targets(symbol)` — *"§6.1b:341 — all open positions in that symbol, off the ONE snapshot"* — reads `self._book.current().positions` and filters `row.state in OPEN_STATES` (`session.py:619-626`)
- `session.py:567-573` — the fire itself, then the async reconcile:
  ```
  self._executor.fire(
      FlattenTrigger.SESSION_CLOSE,
      symbol=symbol,
      targets=targets,
      reason=SESSION_REASON,
  )
  confirmed = await self._executor.reconcile_and_publish()
  ```
- `session.py:553-563` — the venue guard: *"§4:231-235 — the guard. We do NOT fire orders into a shut market"* → `EXPOSURE_RIDES_MARKET_HALTED`. **A stale-price flattener needs the same guard and hits it harder**: the reason the flatten is firing is that price data stopped, which is itself evidence the venue may be unreachable.

ARC C's `STALE_PRICE` flattener is `SessionFlattener` with `next_close`/`lead_min`
replaced by `FreshnessTracker.reading(feed, symbol)` and `deadline_ms`, and
`FlattenTrigger.SESSION_CLOSE` replaced by `FlattenTrigger.STALE_PRICE`.

**The open architect ruling D3.453 names** ("which reading, which grace, whose
deadline") maps onto concrete unresolved choices:

- WHICH READING — `price_stale_ms: 2000` only, or any of the four feeds?
  `risks/staleness.config.json` carries `margin_stale_ms 5000`,
  `calendar_stale_ms 900000`, `price_stale_ms 2000`, `balance_stale_ms 30000`.
  `StalenessFlagPort.read` currently ORs **all configured feeds**
  (`freshness.py:695-700`), which for a flatten would mean a 15-minute calendar
  gap flattens the book.
- WHICH GRACE — `blocked` (past `deadline_ms`, i.e. after the retry ladder) is
  the obvious predicate, but §6.4 gives no *second* grace for flatten-vs-halt,
  and flattening on the same instant that blocks entries is a policy choice, not
  a spec reading.
- WHOSE DEADLINE — no `STALE_FLATTEN_LEAD` knob exists in §12A;
  `risks/staleness.config.json` `_meta.no_knob_for_skew_observation_age` records
  the precedent for refusing to invent one.

---

## 2. D3.372 — not-tradable confirmed fill

### 2.1 The `UntradableSymbol` sites

Two distinct classes with the same name:

- `scripts/nixrisk/positions.py:209` `class UntradableSymbol(OriginError)` — **the D3.372 subject**
- `scripts/nixrisk/stops.py:121` `class UntradableSymbol(StopError)` — a different class, raised at `stops.py:263`

The D3.372 raise, `scripts/nixrisk/positions.py:545-553`, inside
`PositionOriginWriter._row` (`positions.py:536`):

```
545:        if margin_per_contract is None:
546:            self.refusals += 1
547:            raise UntradableSymbol(
548:                f"fill {report.order_id}/{report.exec_id}: symbol "
549:                f"{report.symbol!r} is absent from the published margin field set, "
550:                "so this row's margin has no scale — §4:198 makes such a symbol "
551:                "NOT-TRADABLE and a guessed figure would enter `committed`, which "
552:                "every §3 Phase-B capital rule is evaluated against"
553:            )
```

### 2.2 §4:198, verbatim from the frozen spec

`docs/nics_risk_subsystem_spec_v1.3.md:197-199`:

```
197: - **Validation / authority:** the **Limiter** validates the stop intent (missing/zero/invalid
198:   distance ⇒ deny; §3 ingress guard); symbol absent from the margin field set ⇒ not-tradable. The
199:   strategy proposes; the Limiter is the sole authority that converts, places, and maintains the stop.
```

Note the shape: §4:198 is a **DENY-AT-INGRESS rule** (*"§3 ingress guard"*), not
a post-fill rule. That is exactly why the architect's root fix is
deny-at-approval — the spec already puts the condition upstream, and
`positions.py:547` is where it is being discovered too late.

### 2.3 The ordering that makes it a defect

`scripts/nixrisk/positions.py:458-486`, `PositionOriginWriter.open`:

- `:470` `outcome = self._ledger.ingest(report)` — the execution ledger has already taken the fill
- `:471-473` stop lookup; `_refuse_unstopped` on miss
- `:475` `row = self._row(report, origin, distance)` ← **raises `UntradableSymbol` HERE**
- `:484` `picture = self._picture.commit(...)` — never reached

So `exec_ledger_net_qty=2` while `picture.positions == []`. The debt row's
measurement.

**The asymmetry, on disk.** The sibling refusal *does* leave a consumable
surface:

- `positions.py:495` `def unstopped(self) -> tuple[UnstoppedRecord, ...]` —
  *"The escalation surface: §14 says an unprotected position resolves toward FLAT, this module may not fire a flatten (§14 makes execution Limiter-only and `nixrisk.flatten` owns it), so the condition is recorded where a supervising loop can act on it instead of vanishing into a log."* (`positions.py:498-501`)
- `positions.py:507` `_refuse_unstopped` appends an `UnstoppedRecord` (`positions.py:512-519`) and then raises.
- `UntradableSymbol` at `:547` increments `self.refusals` and raises. **No record. No surface.**

`positions.py:521-533` (`UnstoppedFill`) even names the trigger by hand:
*"this position is UNPROTECTED (§4, §12.1), so §14 resolves it toward FLAT: see unstopped() and fire the UNCERTAINTY flatten"*. The not-tradable path has no such sentence and no such surface.

### 2.4 Where the TRIGGER would be raised, and where the CONSUMER hooks

**Trigger site (produce the condition):** `scripts/nixrisk/positions.py:545-553`.
The minimal shape mirrors `_refuse_unstopped`: a new frozen record type beside
`positions.py:387 class UnstoppedRecord`, a new list beside
`positions.py:443 self._unstopped: list[UnstoppedRecord] = []`, and a new public
reader beside `positions.py:495 unstopped()`.

**Consumer hook (act on it) — the daemon boundary that already CONTAINS this exception:**
`scripts/nixrisk/completions.py:724` `FillDispatcher._dispatch_fill`. Its docstring
names `UntradableSymbol` explicitly (`completions.py:735`):

> "**CONTAINMENT IS NOT ABSORPTION.** `FillHandler.on_fill` raises rather than returning a partial outcome, and every one of its refusals (`UnapprovedFill`, `UnstoppedFill`, `UntradableSymbol`, `DuplicateStop`, `InvalidRemainder`, the ledger's own) is a real condition an operator must see."

and the catch is `completions.py:770-777`:

```
770:        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
771:            return DispatchResult(
772:                Disposition.REFUSED,
...
776:                f"{completion.symbol!r}: {type(exc).__name__}: {exc}",
777:            )
```

`completions.py:743-747` records the consequence that makes a flatten mandatory
rather than optional:

> "**THE §4:214 KEY IS ALREADY CLAIMED WHEN THIS RUNS** … a fill whose cascade raised is NOT retried on a re-delivery."

The refusal is terminal. Nothing will ever come back for that position.

**Where the operator can see it today, and what is missing:**
`scripts/limiterd.py:684-692` publishes `"unstopped"` from `self.writer.unstopped()`,
with `limiterd.py:679-683` stating the residual:

> "Fills refused for want of an armed stop. §14 resolves an unprotected position toward FLAT and nothing in this process fires that flatten yet — the residual `positions.py` names and this daemon inherits."

The not-tradable refusal reaches only the bare counter
`"write_refusals": self.writer.refusals` (`limiterd.py:648`).

**Root fix — deny-at-approval — where it goes:**
`scripts/limiterd.py:1136` `CommandHandler._reserve` and
`scripts/limiterd.py:582` `FillPath.approve`. Note `limiterd.py:605-612`:

```
605:        # §4:198's instrument field set, seeded from the approval that named it.
...
611:        current = dict(self.picture.current().margin_per_contract)
612:        current[order.symbol] = order.margin_per_contract
```

In *this* build the approval seeds the field set, so the symbol is present at
approval by construction. The debt row's reachability claim is about the live
system — *"reachable mid-session from a margin poll that drops a symbol"* — i.e.
a margin feed that later removes the key. A deny-at-approval gate therefore has
to be a **§3 Phase-A rule reading the live margin field set**, and that is the
`tradability` port slot at `scripts/nixrisk/gate.py:1151-1155`:

```
1151:        SymbolFlagRule(
1152:            "tradability",
1153:            tradability,
1154:            "§11.1 tradable[symbol], §3 session boundary + post-open warmup",
1155:        ),
```

**That port has NO production implementation.** `blackout.py` supplies the
`blackout` port (`blackout.py:13`), `freshness.py:660` supplies `staleness` and
`freshness.py:808 ClockSkewFlagPort` supplies `clock_skew`. Nothing in
`scripts/nixrisk/` implements `tradability`; the only suppliers are stubs in
`scripts/plane1_degraded_drill.py:822` and `scripts/plane1_hotpath_drill.py:244`
(both `tradability=clear`). And `default_manifest` is not called from `limiterd.py`
at all. **The deny-at-approval fix therefore requires building the tradability
port AND wiring `GatePass` into the daemon — neither exists.**

### 2.5 D3.372's residual, quoted

From `docs/CHECK-DEBT.md:867` (owner ARC 050+, area `limiter`):

> **A fill the execution ledger INGESTED but the origin write REFUSED leaves §3's table and §12.7's mirror reading FLAT over a real position — and records nothing**

> "…a real 2-lot fill produced `position_table_states=[]`, `mirror_open_trades=[]`, `sum_open_margin=0`, `wal_kinds=["reservation_taken","reservation_released"]` (no fill trace), `writer_unstopped_records=0`, while `exec_ledger_net_qty=2` and `reconcile` reported `drift=2, agrees=false`. §7:501 prices bucket exposure from the published table, so the held position is priced at ZERO and §7's correlation cap ADMITS MORE — D3.136's fail-open under a new spelling. The asymmetry is the defect: the SIBLING refusal (`positions.py:507 _refuse_unstopped`) deliberately records an `UnstoppedRecord` *"where a supervising loop can act on it instead of vanishing into a log"*; this path records only a counter. Also observed: `sum_reservations` stayed 2000.0 while `reservations_outstanding` was empty, so `committed` carries a phantom. NOT discharged, and deliberately not softened: the repair needs an architect ruling on WHICH surface carries the condition (publish the row anyway — with what margin figure? — or hand `nixrisk.flatten` an `UNCERTAINTY` trigger from this site) plus a consumer, and neither is a minimal local change to a frozen file. The state is PINNED by `test_arc038_c_open_is_confirmed_fill.py::test_a_REFUSED_ORIGIN_WRITE_leaves_the_PICTURE_and_the_MIRROR_reading_FLAT`, whose assertions name themselves as the ones to rewrite when it is fixed. **OWNER RE-POINTED ARC 049 (was ARC 039, ten arcs stale).**"

The architect's ruling as given to ARC 052 — **FLATTEN, do not publish; the root
fix is deny-at-approval** — picks the second of the two branches the residual
offered ("hand `nixrisk.flatten` an `UNCERTAINTY` trigger from this site") and
adds the upstream half.

`checks/check_two_phase_entry.py:139-147` restates the scope boundary and must be
updated when ARC C lands:

> "* **D3.372 is NOT discharged by a green here.** … This gate drives the ACCEPTING path and says so on every run in its evidence string, so a green cannot be read as covering the refusal."

---

## 3. What is already present and reusable

### 3.1 (a) The protective-flatten machinery — `scripts/nixrisk/flatten.py`

**Value types / vocabulary**

| name | file:line | note |
|---|---|---|
| `FlattenError` | `flatten.py:161` | base |
| `TriggerNotFireable` | `flatten.py:165` | raised for `_R4_TRIGGERS` |
| `NotAnOnsetCause` | `flatten.py:169` | |
| `BrokerFlattenPort` (Protocol) | `flatten.py:210` | `flatten(symbol=None)` `:223`, `cancel_order(coid)` `:226` |
| `StrategyExitSink` (Protocol) | `flatten.py:242` | `on_closed(...)` `:245` |
| `ScoringSink` (Protocol) | `flatten.py:252` | `book_realized(...)` `:264` |
| `CloseAuthority` | `flatten.py:280` | `DISCRETIONARY`, `PROTECTIVE` |
| `CloseTarget` | `flatten.py:288` | `trade_id`, `symbol`, `strategy_id` |
| `OrderRole` | `flatten.py:296` | see 3.2 |
| `PendingEntry` | `flatten.py:334` | `client_order_id`, `strategy_id`, `symbol`, `role=OrderRole.ENTRY` |
| `ClosedRecord` | `flatten.py:353` | 8 fields |
| `CloseOutcome` | `flatten.py:371` | `executed`, `record`, `dropped_reason` |
| `FlattenAction` | `flatten.py:380` | `trigger`, `symbol`, `targets`, `outcomes`, `fired_ts` |
| `OnsetCancellation` | `flatten.py:397` | 8 dispositions; `complete` `:442` |
| `ConfirmedFlat` | `flatten.py:454` | the CONFIRMED fact, reconcile-only |
| `UnbookedRow` | `flatten.py:474` | Plane-1 refusal record |
| `_Intent` | `flatten.py:496` | private |
| `_R4_TRIGGERS` | `flatten.py:143` | `frozenset({FlattenTrigger.SENTINEL})` |
| `_ONSET_CAUSES` | `flatten.py:149` | `{BLACKOUT_ONSET, HALT_ONSET}` |
| `_LIVE_STATES` | `flatten.py:157` | `{PositionState.OPEN, PositionState.CLOSING}` |

**The executor** — `scripts/nixrisk/flatten.py:510` `class ProtectiveFlatten`:

```
528:    def __init__(  # pylint: disable=too-many-arguments
529:        self,
530:        *,
531:        broker: BrokerFlattenPort,
532:        ledger: ReservationLedger,
533:        picture: FinancialPictureBook,
534:        strategy: StrategyExitSink,
535:        plane1: Plane1Port,
536:        scoring: ScoringSink,
537:        trade_facts: TradeFactsBook | None = None,
538:        clock: Callable[[], float] = time.time,
539:    ) -> None:
```

Public verbs:

- `flatten.py:618` `fire(trigger, *, symbol=None, targets=(), reason=None) -> FlattenAction`
  — *"Fire a protective flatten. ZERO wire: a direct in-process broker call."* Refuses `_R4_TRIGGERS` loudly (`:632-639`). `reason` is optional and rides through to the §4 fan-out and Plane-1 row (`:653-668`).
- `flatten.py:677` `request_close(target, authority, reason) -> CloseOutcome` — §4's dual-authority arbiter, `threading.Lock` guarded (`self._arbiter`, `flatten.py:~615`).
- `flatten.py:887` `cancel_entries_on_onset(cause: TerminalPath, pending: Sequence[PendingEntry], *, scope: str | None = None) -> OnsetCancellation` — *"This method calls `cancel_order` ONLY. It never calls `flatten`"* (`:913-915`).
- `flatten.py:1085` `async reconcile_and_publish() -> ConfirmedFlat` — the one async verb.
- `flatten.py:1394` `closed_record(trade_id) -> ClosedRecord | None`.
- public attribute `self.unbooked: list[UnbookedRow]` (see `flatten.py:~596-608` for why it is an attribute, not an accessor — `check_uncalled_entry_points` refused the accessor by name).

**Who calls it today — the "wire-free" measurement.** `nixrisk.flatten` has
exactly **one** non-test importer in the whole tree:

```
scripts/nixrisk/session.py:120:from nixrisk.flatten import CloseTarget, ConfirmedFlat, ProtectiveFlatten
```

and `nixrisk.session` has **zero** importers (grep for `from nixrisk.session` /
`import nixrisk.session` outside tests returns nothing; `SessionFlattener(` is
constructed only at `scripts/tests/test_session_flatten.py:736`).

Production `fire()` call sites — three, all inside unreachable modules:

| site | trigger |
|---|---|
| `scripts/nixrisk/session.py:567` | `SESSION_CLOSE` |
| `scripts/nixrisk/recovery.py:986` | `ORPHAN` (`RecoverySequencer._step_flatten`, `recovery.py:953`) |
| `scripts/nixrisk/halt.py:1067` / `scripts/nixrisk/blackout.py:1067` | `cancel_entries_on_onset` only — no flatten |

`nixrisk.recovery` IS imported by `scripts/nixrisk/loop.py:192-197`, but only for
`RecoveryError, Registration, ReleasedInFlight, StrategyRegistry` — **not**
`RecoverySequencer`. And `scripts/limiterd.py:167` takes `RecoveryError` alone.

`ProtectiveFlatten(` is constructed at 15 sites, **every one a test or a check**:
`scripts/tests/test_exit_integration.py:280`, `test_arc044_exactly_one_terminal_release.py:261,507`,
`test_recovery.py:284`, `test_arc038_c_exit_brake.py:935`, `test_session_flatten.py:260`;
`checks/check_allocator_weighting.py:1451`, `check_allocator_lifecycle.py:710`,
`check_sentinel_deadman.py:493`, `check_realized_pnl.py:495,1051`,
`check_session_flatten.py:378`, `check_orphan_recovery.py:348`,
`check_flatten.py:634,789`.

**Verdict: `flatten.py` "exists and nothing in a running process calls it".**
The executor is complete and gated; every producer that would call it sits in a
module the daemon never imports.

### 3.2 (b) `OrderRole` and the trigger vocabulary

`scripts/nixrisk/flatten.py:296` `class OrderRole(enum.Enum)` — ARC 045 / I11:

```
ENTRY = "entry"          # flatten.py:317
EXIT = "exit"            # flatten.py:318
PROTECTIVE = "protective"  # flatten.py:319
```

Docstring (`flatten.py:297-315`): *"§3:173's partition of a working order: what an onset sweep may cancel … until this enum existed the tree had **no way to say which of the two an order was** … A predicate the type system cannot express is a predicate the next author silently breaks."*

Companion constant `scripts/nixrisk/flatten.py:330`:

```
_CANCELLABLE_ROLES: frozenset[OrderRole] = frozenset({OrderRole.ENTRY})
```

Enforcement sites: `flatten.py:832-840` (a non-`OrderRole` `role` is refused) and
`flatten.py:841` (`role not in _CANCELLABLE_ROLES` → excluded from the sweep).
`PendingEntry.role` defaults to `ENTRY` (`flatten.py:349`); the docstring
(`flatten.py:337-347`) is explicit that *"A declared role can only ever EXCLUDE an
order from the sweep, never admit one"* — admission is derived from the
reservation ledger in `_classify_for_onset` (`flatten.py:776`).

**Trigger enums in scope**

| enum | file:line | members |
|---|---|---|
| `FlattenTrigger` | `scripts/nixrisk/seam.py:608` | `SYNTHETIC_STOP`, `STALE_PRICE`, `NET_LIQ_FLOOR`, `SESSION_CLOSE`, `UNCERTAINTY`, `ORPHAN`, `SENTINEL` (`seam.py:626-632`) |
| `TerminalPath` | `scripts/nixrisk/seam.py:~260` | `FILL`, `CANCEL`, `REJECT`, `PENDING_TIMEOUT`, `BLACKOUT_ONSET`, `HALT_ONSET` (`seam.py:268-273`) |
| `CloseAuthority` | `flatten.py:280` | `DISCRETIONARY`, `PROTECTIVE` |
| `OrderRole` | `flatten.py:296` | `ENTRY`, `EXIT`, `PROTECTIVE` |

`FlattenTrigger`'s docstring is the spec transcription (`seam.py:610-612`):
*"Verbatim, §3:169: 'Limiter (synthetic stop / stale price / net-liq floor / session close / uncertainty / orphan / sentinel)'"* — matching `docs/nics_risk_subsystem_spec_v1.3.md:168`.

The gate's disposition table — `checks/check_flatten.py:1147-1152` — currently
classifies `stale_price` and `uncertainty` as `"fireable"`, and the fireable set
is DERIVED at `check_flatten.py:1358 _derive_fireable` against the subject's own
`_R4_TRIGGERS` (`check_flatten.py:1369`). **ARC C adds no enum member**, so this
derivation needs no change — which is the good news, and also why
`check_uncalled_entry_points` cannot see the gap (D3.453's own point).

### 3.3 Estimated ARC C build scope

**Files touched**

| file | change | new units |
|---|---|---|
| `scripts/nixrisk/stale_flatten.py` (NEW) | the §6.4 flatten-open producer, modelled on `session.py::SessionFlattener` | 1 class + ~6 methods; 1 verdict enum; 2 frozen dataclasses (`Outcome`, `Sweep`); 1 `OpenBookReadPort`-shaped Protocol (or import `session.OpenBookReadPort`, `session.py:244`) |
| `scripts/nixrisk/positions.py` | D3.372 trigger surface: record beside `UnstoppedRecord` (`:387`), list beside `:443`, reader beside `unstopped()` (`:495`), populate at `:546` before the raise | 1 dataclass + 1 method + 1 list |
| `scripts/nixrisk/completions.py` | D3.372 consumer: in `_dispatch_fill`'s `except` (`:770-777`), classify `UntradableSymbol` and fire `FlattenTrigger.UNCERTAINTY` before returning `REFUSED` | 1 injected port + ~1 helper method |
| `scripts/nixrisk/gate.py` | none expected — the `tradability` slot (`:1151-1155`) already exists | 0 |
| `scripts/nixrisk/<new>` tradability port | the deny-at-approval root fix: a `SymbolFlagPort` over `FinancialPicture.margin_per_contract` | 1 class + 2 methods |
| `scripts/limiterd.py` | wire it: construct the producer(s) in `FillPath.__init__` (`:535`) / the daemon build; hand `_dispatch_fill` its flatten port; add the new records to `FillPath.record()` (`:624`, beside `"unstopped"` at `:684`) | ~3 edits, 0 new classes |
| `risks/staleness.config.json` | possibly a §12A knob for the flatten grace — **blocked on the architect ruling**, see 1.5 | 0 or 1 key + `_derivations` + `_boot_validation` |
| `scripts/risk_config.py` | loader for that knob if it lands | 1 function |

Rough total: **~4 new classes, ~15 new functions/methods, 3 new frozen dataclasses, 1 new enum**, plus wiring edits.

**Gates / tests to extend**

| artifact | why |
|---|---|
| `checks/check_flatten.py` | ARM 6 already derives the fireable set (`:1358`) and drives all six; ARC C makes `stale_price` and `uncertainty` have real PRODUCERS, so the gate should gain a producer arm (today it only proves the executor accepts them) |
| `checks/check_staleness.py` | subject is `freshness.py` + the ports (`:450`, `:560`, `:609`); extend to the flatten-open half |
| `checks/check_session_flatten.py` | the closest existing template (`:378` builds a real `ProtectiveFlatten`, `:684-690` fires + reconciles). A `check_stale_flatten.py` is the honest new artifact rather than an extension — doctrine C.9 forbids a duplicate instrument, but the subject is different |
| `checks/check_two_phase_entry.py` | `:139-147` explicitly disclaims D3.372; that disclaimer must be rewritten when the refusal path gains a consumer |
| `checks/check_limiter_daemon_dispatch.py` | reads `FillPath.record()` (`limiterd.py:624-694`); the new records land there |
| `checks/check_uncalled_entry_points.py` + `checks/uncalled_entry_points_baseline.json` | `scripts/nixrisk/session.py` entries (`:807-831`: `is_due`, `tick_async`, `fired_outcome`, `SessionFlattenSweep.fired/riding`) and `scripts/nixrisk/freshness.py` entries (`:591-608`: `StalenessFlagPort.tracker`, `SourceMonotonicGuard.keys`, `ClockSkewMonitor.latest`) should SHRINK — the baseline is a one-way ratchet |
| `checks/check_artifact_gate_coverage.py` + `checks/gate_coverage_baseline.json` | a NEW production file needs a gate row in the same arc (check contract rule 3) |
| `checks/check_input_freshness.py` | only if ARC A's `signal_ts` work lands in the same arc; otherwise untouched |
| `scripts/tests/test_flatten.py` | `:370-379` parametrize already covers `STALE_PRICE` at the executor; a producer test is new |
| `scripts/tests/test_arc038_c_open_is_confirmed_fill.py` | `::test_a_REFUSED_ORIGIN_WRITE_leaves_the_PICTURE_and_the_MIRROR_reading_FLAT` (`:581`, `:612`) is the PIN — D3.372's row says its *"assertions name themselves as the ones to rewrite when it is fixed"* |
| `scripts/tests/test_session_flatten.py` | the copy source for a new `test_stale_flatten.py` |
| `docs/CHECK-DEBT.md` | discharge rows D3.453 and D3.372; expect new rows for whatever ARC C scopes out |

**Named blockers ARC C cannot resolve by itself**

1. D3.453's *"which reading, which grace, whose deadline"* — architect ruling; §12A has no `STALE_FLATTEN_*` knob and `risks/staleness.config.json` `_meta.no_knob_for_skew_observation_age` is the precedent for refusing to invent one.
2. D3.372's deny-at-approval half requires a `tradability` `SymbolFlagPort` implementation **and** `GatePass` wired into `limiterd.py` — neither exists today. If ARC C ships only the FLATTEN half, the debt row is partially discharged and must say so.

---

## 4. D3.463 — `signal_ts`

### 4.1 The `or time.time()` fallback — CONFIRMED

`scripts/limiterd.py:1155-1175`, verbatim with line numbers:

```
1155:                f"{VERB_RESERVE!r} needs §11.3's reservation ledger and this "
1156:                "build was constructed without one",
1157:            )
1158:        try:
1159:            order = ProposedOrder(
1160:                client_order_id=client_order_id,
1161:                strategy_id=strategy_id,
1162:                symbol=str(raw.get("symbol") or ""),
1163:                side=Side(str(raw.get("side") or Side.LONG.value)),
1164:                qty=int(raw.get("qty") or 0),
1165:                margin_per_contract=float(raw.get("margin_per_contract") or 0.0),
1166:                stop_ticks=int(raw.get("stop_ticks") or 0),
1167:                stop_mode=StopMode(str(raw.get("stop_mode") or StopMode.FIXED.value)),
1168:                signal_ts=float(raw.get("signal_ts") or time.time()),
1169:            )
1170:        except (TypeError, ValueError) as exc:
1171:            return self._refuse(
1172:                command_id,
1173:                VERB_RESERVE,
1174:                f"{client_order_id!r} is not a readable §3 order: "
1175:                f"{type(exc).__name__}: {exc}",
1176:            )
```

Line 1168 is exactly as D3.463 records it. It is the **only** `signal_ts`
assignment in shipped daemon code (the other non-test hits are
`scripts/plane1_degraded_drill.py:798`, `scripts/plane1_hotpath_drill.py:266`,
`scripts/nixalloc/*`, `scripts/nixrisk/join.py:222`).

The field itself: `scripts/nixrisk/seam.py:226` `signal_ts: float` on `ProposedOrder`.

### 4.2 The ingress path, traced

`limiterd.py` serves five verbs (`limiterd.py:270-290`):
`register`, `go`, `status`, `resolve`, `reserve`.

```
Inbox.drain (limiterd.py:328)
  -> CommandHandler.handle (limiterd.py:995)
    -> CommandHandler._reply_for (limiterd.py:1020)   # JSON, schema, verb validation
      -> CommandHandler._dispatch (limiterd.py:1063)
         :1067  verb == "status"   -> status reply
         :1098  verb == "register" -> LimiterLoop.admit
         :1115  verb == "resolve"  -> LimiterLoop.resolve_in_flight
         :1129  verb == "reserve"  -> CommandHandler._reserve (limiterd.py:1136)
                                        -> ProposedOrder(...)   <-- signal_ts, :1168
                                        -> ReservationLedger.take
                                        -> FillPath.approve (limiterd.py:582)
         :1131  verb == "go"       -> LimiterLoop.take_in_flight (loop.py:833)
                                        + LimiterLoop.hand_to_sender
```

**A measured surprise worth flagging to the architect: the `go` verb does NOT
construct a `ProposedOrder` and never touches `signal_ts`.**
`limiterd.py:1131-1134`:

```
1131:        accepted, reason = self._loop.take_in_flight(strategy_id, client_order_id)
1132:        if accepted:
1133:            self._loop.hand_to_sender((strategy_id, client_order_id))
1134:        return self._reply(command_id, verb, accepted=accepted, reason=reason)
```

`nixrisk/loop.py:833 take_in_flight(strategy_id, client_order_id)` takes two
strings and no timestamp. Its docstring (`loop.py:836-846`) is entirely about
§4:208-209's one-in-flight lock. The GO clock that DOES start is the loop's own
monotonic (`loop.py:862-863`: *"THE CLOCK STARTS HERE, on the loop's own monotonic, inside the tick that admitted the GO. §4:212 measures T from the emission of the GO"*) — which is precisely the `GoTimeout` quantity D3.463 says is a different quantity from signal age.

So in *this* build the signal instant enters the daemon **only through the
`reserve` verb**, i.e. at the approval moment, not at GO. The upstream producer
that stamps it is the Allocator: `scripts/nixalloc/sizing.py:976 signal_ts=signal_ts`
inside `propose`, fed from `scripts/nixalloc/wiring.py:1164 signal_ts=go.signal_ts`,
where `wiring.py:796 signal_ts: float` is the GO record's own field.

### 4.3 The one-way ratchet that admits it

`checks/check_input_freshness.py:248-262`:

```
248: #: THE ONE-WAY RATCHET. A dataclass field on a gate input that is CLOCK-SOURCED
249: #: somewhere in shipped code but that NO freshness-refusal site reads. Admitted
250: #: BY NAME, with the debt row that owns it. A field NOT here is a FAIL — silent
251: #: growth is the defect. See the module docstring's `signal_ts` section.
252: _ACCEPTED_UNGATED: dict[str, str] = {
253:     "ProposedOrder.signal_ts": (
254:         "STRATEGY-sourced, not venue-sourced: §6.4b scopes the monotonic guard "
...
259:         "signal's OWN age should bound entry is unanswered by the frozen spec "
260:         "— CHECK-DEBT D3.463, architect ruling"
261:     ),
262: }
```

`check_input_freshness.py:162-167` also declares `CORRECTABLE = False` —
*"An instrument empowered to edit `freshness.py`, `gate.py` or `picture.py` into agreement would be authoring the code it certifies."*

### 4.4 D3.463's residual, quoted

`docs/CHECK-DEBT.md:955`, owner **unassigned**, area `limiter`:

> **`ProposedOrder.signal_ts` is the ONE time quantity on a Limiter-gate input that no freshness-refusal site in the tree reads — the gate sizes and sends without ever asking how old the signal is**

> "Discharge = an architect ruling (a `SIGNAL_STALE_MS` in §12A and a rule, or a recorded decision that the GO-timeout is the whole bound), plus removing the `or time.time()` fallback so an unstamped GO is refused rather than dated now"

### 4.5 Is the fix correctly scoped to a separate ARC A?

**Yes — and the scoping is cleaner than the brief assumes, for two reasons.**

1. **No overlap with ARC C's files.** ARC A touches `scripts/limiterd.py::CommandHandler._reserve` and `checks/check_input_freshness.py`. ARC C touches `flatten.py`'s callers, `positions.py`, `completions.py`, and a new producer module. The one shared file is `limiterd.py`, and the two edits are in different classes (`CommandHandler` vs `FillPath`) and different methods.
2. **ARC A is blocked on the same class of ruling as ARC C but a different ruling.** D3.463 needs `SIGNAL_STALE_MS` in §12A or a recorded "GO-timeout is the whole bound". D3.453 needs the staleness-to-flatten policy. Neither unblocks the other.

**Exact functions ARC A would edit:**

| file:line | unit | edit |
|---|---|---|
| `scripts/limiterd.py:1136` | `CommandHandler._reserve` | delete the `or time.time()` at `:1168`; make an absent/unparseable `signal_ts` a `self._refuse(...)` (the refusal ladder at `:1170-1176` is the existing home) |
| `scripts/limiterd.py:1063` | `CommandHandler._dispatch` | only if the ruling puts the age check ahead of the reserve branch at `:1129` |
| `checks/check_input_freshness.py:252` | `_ACCEPTED_UNGATED` | remove the `ProposedOrder.signal_ts` entry — the ratchet may only shrink |
| `checks/check_input_freshness.py` (new arm) | — | a deny/act pair on signal age, matching ARMs 2-5 (`:107-120`) |
| `risks/limiter.config.json` + `scripts/risk_config.py` | — | `SIGNAL_STALE_MS` if the ruling creates one |
| `scripts/nixrisk/gate.py:1121` `default_manifest` | — | only if the ruling makes signal age a §3 Phase-A RULE rather than an ingress refusal. **Note this would be inert today** — `default_manifest` has no production caller (§1.3). |

One caveat ARC A must record: because the `go` verb never carries `signal_ts`
(§4.2), *"reject a stale GO"* in this build means *"reject a stale RESERVE"*.
Either the ruling names `reserve` as the approval moment where the age is
checked, or the `go` command schema (`COMMAND_SCHEMA = 1`, `limiterd.py:199`)
has to start carrying the stamp — which is a schema bump, not a local edit.

---

## What ARC C must build — summary table

| # | Item | Exists today | ARC C builds | Blocked on |
|---|---|---|---|---|
| 1 | Stale detector | `freshness.py:528 FreshnessTracker` / `:573 reading()` — complete, pure, testable | nothing | — |
| 2 | Stale → deny-new-entries | `freshness.py:660 StalenessFlagPort` → `gate.py:1156 SymbolFlagRule("data_staleness", …)` — **built, but `default_manifest` has no production caller** | nothing (but note the wire gap) | — |
| 3 | Stale → **flatten-open** (§6.4:374) | **NOTHING.** `STALE_PRICE` (`seam.py:627`) has zero producers | NEW module (`stale_flatten.py`): 1 class + ~6 methods, modelled line-for-line on `session.py:410 SessionFlattener` | architect ruling: which feed, which grace, whose deadline (D3.453) |
| 4 | Open-position visibility at the stale seam | **NO** — `StalenessFlagPort.__init__` (`freshness.py:672`) takes only the tracker | inject an `OpenBookReadPort` (`session.py:244`) reading `FinancialPicture.positions`, filter `_LIVE_STATES` (`flatten.py:157`) — copy `session.py:617 _open_targets` | — |
| 5 | Venue guard for a flatten fired *because data stopped* | pattern exists: `session.py:553-563 EXPOSURE_RIDES_MARKET_HALTED` | reuse the pattern; it matters more here | — |
| 6 | Not-tradable **trigger record** | **NOTHING** — `positions.py:546` bumps `self.refusals` and raises | 1 frozen dataclass + 1 list + 1 reader, beside `UnstoppedRecord` (`positions.py:387`) / `unstopped()` (`positions.py:495`) | — |
| 7 | Not-tradable → `UNCERTAINTY` flatten | **NOTHING** | hook in `completions.py:724 FillDispatcher._dispatch_fill`, inside the `except` at `:770`; fire `FlattenTrigger.UNCERTAINTY` before returning `REFUSED` | architect ruling already given (FLATTEN, do not publish) |
| 8 | Deny-at-approval root fix | **NOTHING** — the `tradability` port slot exists (`gate.py:1151-1155`) with no implementation; `GatePass` is not in `limiterd.py` | a `SymbolFlagPort` over `picture.margin_per_contract` (1 class, 2 methods) **plus** wiring `GatePass` into the daemon | large — may need its own arc |
| 9 | Protective executor | `flatten.py:510 ProtectiveFlatten`, 8-collaborator ctor at `:528`, verbs `fire`/`request_close`/`cancel_entries_on_onset`/`reconcile_and_publish` — **complete and gated, called by no running process** | **nothing** — construct it, do not modify it | — |
| 10 | `OrderRole` / trigger vocabulary | `flatten.py:296` (`ENTRY`/`EXIT`/`PROTECTIVE`), `_CANCELLABLE_ROLES` `:330`, `seam.py:608 FlattenTrigger` (7), `TerminalPath` (6), `CloseAuthority` (2) | **nothing** — no enum member is added, which is why `check_uncalled_entry_points` is blind to both gaps | — |
| 11 | Daemon wiring | `limiterd.py:126-172` imports no flatten/gate/freshness | construct the producers in the daemon; publish the new records in `FillPath.record()` (`limiterd.py:624`) | — |
| 12 | Gates | `check_flatten`, `check_staleness`, `check_session_flatten`, `check_two_phase_entry`, `check_limiter_daemon_dispatch`, `check_uncalled_entry_points`, `check_artifact_gate_coverage` | extend all seven; NEW `check_stale_flatten.py`; shrink the uncalled baseline (`:591`, `:807`) | check contract rule 3 |
| 13 | D3.463 `signal_ts` | `limiterd.py:1168 signal_ts=float(raw.get("signal_ts") or time.time())` | **NOT ARC C.** ARC A: `CommandHandler._reserve` (`limiterd.py:1136`) + `check_input_freshness._ACCEPTED_UNGATED` (`:252`) | architect ruling: `SIGNAL_STALE_MS` or "GO-timeout is the whole bound" |
