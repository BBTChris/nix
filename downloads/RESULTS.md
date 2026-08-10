# ARC 015 — RESULTS

**Async contract applied; all four ARC 014 findings closed, each with a mutation-proved test** —
2026-08-10

---

## 0. Handoff note

`~/nix/downloads/arc_015_async_contract.md` arrived and was executed end to end. Everything it
references was on disk: `scripts/broker/{broker_seam,broker_order_ibkr,ibkr_mapping,seam_simulate}.py`
and `scripts/tests/test_broker_order.py`, all carrying ARC 014's `avg_price` unit fix and
`check_await_conformance()`. All edits were made **in place**; nothing was replaced from the
architect's copies.

ARC 014's own arc document still has not reached the machine (the second such loss after
`VERIFY-AND-CHECKS.md` in ARC 008). Nothing in ARC 015 depended on it.

One housekeeping note: `downloads/broker_seam.py`, `downloads/broker_order_ibkr.py`,
`downloads/ibkr_mapping.py`, `downloads/simulate.py`, `downloads/test_broker_order.py` are the
architect's original copies and are now **substantially behind** the landed code. They should not be
read as current. `scripts/broker/` and `scripts/tests/` are the source of truth.

---

## 1. Part 1 — the sync/async split, applied

The operator-ratified split is implemented exactly as specified, and the decision (with the rejected
alternative) is written into `BrokerOrderPort`'s docstring so it is not relitigated from the code.

| verb | contract | applied to |
|---|---|---|
| `place_order`, `cancel_order`, `flatten`, `disconnect`, `query_order_status` | **sync** | port, Stub, Hollow, IBKR adapter, mapping skeleton, every caller and test |
| `connect`, `query_positions`, `query_balance`, `get_margin` | **async** | same |

`check_await_conformance()` is clean on all four conformance subjects (Stub, Hollow, the IBKR
adapter, the mapping skeleton).

### It is demonstrably capable of failing

Planted **one plausible divergence** in the real adapter — `query_positions` served from the
in-memory mirror with `async` dropped, which compiles, imports, and passes structural conformance —
then removed it:

```
BEFORE PLANT — real adapter:
  structural : CLEAN (all verbs present)
  await      : CLEAN

WITH PLANT (query_positions served from the mirror, `async` dropped):
  structural : CLEAN (all verbs present)
  await      : ['query_positions: port declares async, adapter is sync']

AFTER REMOVING THE PLANT:
  structural : CLEAN (all verbs present)
  await      : CLEAN

plant removed; adapter byte-identical to its pre-plant state
```

Note the middle block's first line: **structural conformance stayed CLEAN through the divergence.**
That is the point of the second checker, measured rather than argued.

The plant is not only a one-off. It also lives permanently as `AwaitDivergentBrokerOrder` in
`broker_seam.py` — a Hollow subclass whose sole purpose is to be caught — and both suites assert the
checker returns exactly one entry naming `query_positions`. A demonstration that is deleted has to
be taken on trust by the next reader.

### The false docstring claim is gone

The `THREADING/ASYNC NOTE` asserting "the sync surface the Limiter sees is satisfied by scheduling
onto the loop" is deleted. Its replacement states what is actually true — the send path is
non-blocking because `ib.placeOrder`/`ib.cancelOrder` are themselves non-blocking, **not** because
anything schedules — and records the retraction, because a docstring describing a mechanism the code
does not have is this file's most dangerous failure mode.

### Hollow is still a failing control

Converted along with the real adapters, deliberately: a control that started failing the *await*
check for a shape reason would have stopped measuring behaviour. It still fails the behavioural
suite on **9 assertions**:

```
NON-VACUITY: Hollow FAILS behavioural assertions (control)
  -> 9 failures: ['connect emits on_session', 'place_order emits on_ack',
     'status is working after place', 'adapter can be driven to a fill (no opt-out)',
     'position exists after fill',
     'flatten assertion is non-vacuous (a position existed to clear)',
     'balance is non-trivial', 'balance carries venue_seq_ts',
     'get_margin returns a real figure']
```

---

## 2. Part 2 — the four findings, closed

Every fix below was **mutation-tested**: the fix was reverted, the suite re-run, and the failing
assertions recorded. A test that passes both with and without the fix proves nothing.

### 2a. Zero-qty rows filtered from `query_positions()`

Filtered at the single point both the returned list and the mirror are built from, so they cannot
diverge again. Mutation — filter removed:

```
M1 (2a) zero-qty filter removed          suite exit=1  (CAUGHT)
  XX §2a: zero-qty rows filtered from the RETURNED list
  XX §2a: the real position still comes back (filter is not a black hole)
  XX §2a: a caller's truthiness test sees FLAT when the account is flat
```

The third assertion is the caller idiom §4 actually invites: `if await broker.query_positions():
halt()`.

### 2b. Startup executions — mechanism stated

**Mechanism of record: a connect-scoped gate.** `self._startup_complete` is set False at the top of
`connect()` and True the instant `connectAsync` returns; `_on_ib_order_status` and
`_on_ib_exec_details` refuse while it is closed.

Why this one over the alternatives:
- **Venue-agnostic** — it catches any startup replay whatever ib_async decides to fetch, including
  anything a future version adds. Narrowing `fetchFields` alone only covers what is known today.
- **Reconnect-safe for free** — the gate is scoped to the CALL, so it re-arms on every `connect()`.
  There is no separate reconnect path to remember, which matters because the Gateway restarts daily
  at 03:00.
- **The window is provably empty** — there is no `await` between `connectAsync` returning and the
  gate opening, so the loop cannot dispatch anything into it. It opens **before** `_rebuild_mirror()`
  deliberately: that method awaits `reqPositionsAsync`, and a genuine fill can land during the await
  (the existing D3 race). Holding the gate shut across it would drop a real fill to catch a
  historical one.

Belt and braces at the source: `fetchFields` now drops `EXECUTIONS`, so the replay is not requested
either. The gate is the guarantee; this only reduces what has to be caught. Nothing reads
`ib.fills()`/`ib.executions()` — the adapter keeps its own `(order_id, exec_id)` ledger.

Two further corrections found while building it:
- **The id maps are now cleared BEFORE `connectAsync`, not after.** The replay arrives *during*
  `connectAsync`; clearing afterwards meant a reconnect still held the previous session's map while
  the venue was replaying it. That is the exact mechanism by which the old "dropped because
  `_from_ib` happened to be empty" accident would have failed on a reconnect.
- **`_wire_events()` is now idempotent per IB instance.** ib_async's `Event` uses `+=`, so wiring
  once per `connect()` registered a second copy of every handler after the 03:00 restart and a third
  after the next. The dedupe sets hid the duplicate ack and duplicate fill, so the only honest
  observable is the handler count — which the suite now asserts.

The test drives it as a **reconnect**, so the historical execution carries the same `orderId` the
sequence reissues. Mutation — gate removed AND the clear moved back after `connectAsync` (i.e. the
pre-ARC-015 code):

```
M2 (2b) startup gate removed AND id-map clear moved back   suite exit=1  (CAUGHT)
  XX §2b: historical execution replayed at connect produces NO fill
  XX §2b: historical orderStatus replayed at connect produces NO ack
  XX §2b: connectAsync asked for StartupFetch WITHOUT EXECUTIONS
  XX §2b: still ignored on the SECOND reconnect (survives the 03:00 restart, twice)
```

There is also an assertion that the gate **opens** — a gate that never opens drops every real fill,
which would be a worse defect than the one being fixed.

### 2c. The missing-ack race — closed

Any event that proves the venue accepted an order — a fill, or a terminal transition implying it was
live — synthesises the ack **first**, so the Limiter can never observe a fill or a cancel for an
order it never saw accepted. Ordering, not merely presence, is the guarantee.

Three things worth flagging in the implementation:

1. **`Inactive`/`ValidationError` deliberately do NOT synthesise.** They are terminal *without*
   acceptance; IBKR delivers the reason on `errorEvent`, which raises a REJECTED ack. Synthesising
   ACCEPTED there would invent an acceptance that never happened — the opposite defect, and worse.
   Two assertions guard this direction.
2. **All ack paths share one gate** (`_ack_once`) and one dedupe set, so venue-ack, error-rejection
   and synthesis cannot both fire for the same order.
3. **A real venue ack is not labelled "synthesised".** The first cut routed the normal
   PreSubmitted path through the synthesis helper; the suite caught it immediately. `reason` is the
   provenance channel, and destroying that distinction would make the synthesis unauditable.

Proof of ordering needed a cross-stream observable, so `RecordingSink` gained a `sequence` list
recording every event in arrival order — the per-stream lists cannot express "the ack preceded the
fill", and an adapter emitting the fill first would satisfy every per-stream assertion. Both event
orderings are driven, because IBKR does not guarantee which lands first. Mutation — synthesis
removed:

```
M3 (2c) ack synthesis removed             suite exit=1  (CAUGHT)
  XX §2c (exec before status): an ack IS raised for a PendingSubmit -> Filled order
  XX §2c (exec before status): the ack PRECEDES the fill in arrival order
  XX §2c (exec before status): the synthesised ack says so, so provenance is not lost
  XX §2c (exec before status): exactly ONE ack — synthesis does not double up
  XX §2c (status before exec): an ack IS raised for a PendingSubmit -> Filled order
  XX §2c (status before exec): the ack PRECEDES the fill in arrival order
  XX §2c (status before exec): the synthesised ack says so, so provenance is not lost
  XX §2c (status before exec): exactly ONE ack — synthesis does not double up
  XX §2c: a cancel with no prior ack synthesises the ack FIRST
```

The first run of that mutation aborted on an `IndexError` instead of reporting nine named failures.
The indexing is now guarded — a test that aborts is a worse instrument than one that fails.

### 2d. `FakeIB` fidelity — and the re-planted bug is caught

The fake now carries what it needs to *represent* the defect:

- `fut()` emits a real `multiplier`, as a string, as IBKR sends it — MES 5, ES 50, MNQ 2, NQ 20, by
  longest-prefix match so `MESU6` resolves to MES and not ES.
- `positionEvent` and `reqPositionsAsync` report `avgCost` as **notional** — `price × multiplier`.
- The **commission wrinkle** ARC 014 measured is encoded:
  `avgCost = price × multiplier + commission`. For the measured fill, `7773.50 × 5 + 0.61 =
  38868.11`, and `38868.11 / 5 = 7773.622` — reproducing the 0.122 provenance gap exactly.
- Mirror assertions read `avg_price`, on every path: `positionEvent`, `on_position`,
  `query_positions`, and the fill path (which is already per-unit and must NOT be divided).
- A second instrument uses a **different multiplier** (ES 50), so a hardcoded 5 cannot pass.

**The original unit bug re-planted, and caught.** `replanted_unit_bug_is_caught()` replaces
`_avg_price_from_cost` with the verbatim pre-fix behaviour and asserts the assertions now fail:

```
NON-VACUITY §2d: the RE-PLANTED ARC 014 unit bug is CAUGHT by this suite
  -> caught 6: ['mirror avg_price is per-unit (38868.11 != 7773.622)',
                'mirror avg_price is NOTIONAL — the ARC 014 unit defect',
                'avg_price within one tick of the raw execution price (gap 31094.61)',
                'on_position avg_price is per-unit (38868.11)',
                'ES avg_price normalised by ITS OWN multiplier (250002.2)',
                'query_positions avg_price is per-unit (38868.11)']
```

Six independent assertions catch it, including one that names the defect's *signature* rather than
just an inequality. A following assertion confirms the plant was removed and everything passes
again. This is permanent, not a one-off — the same pattern as the Hollow control, applied to a
defect instead of an adapter.

---

## 3. Part 3 — libraries

**Adopted:**
- **`pytest-asyncio 1.4.0`**, pinned in `checks/pinned_deps.json` (so `check_python_deps` covers its
  drift) and installed. Configured `asyncio_mode = "strict"`, **not** `auto`: auto silently coerces
  every `async def test_*` onto a loop, so a missing marker is invisible; strict makes "this test
  runs on the loop" a written decision and fails loudly otherwise — the same class of defect
  `check_await_conformance()` exists to catch one layer down.
- **`asyncio.TaskGroup` over bare `create_task`** — recorded as policy in the adapter's module
  docstring. There is currently **no supervised concurrency anywhere in this code** (`grep` for
  `create_task`/`ensure_future` across `scripts/` and `checks/` returns nothing), so the policy is
  written *before* the first task rather than after.

**NOT adopted, and why — recorded where a future author will read it:** a `RETRY POLICY` block in
`broker_order_ibkr.py`'s module docstring, immediately above the code, stating that no retry or
backoff may be added to `place_order`, `cancel_order` or `flatten`. §4 resolves a pending timeout by
querying order status and **never auto-resends**; a retry wrapper turns one intended order into two
live ones the venue accepted and cannot tell apart. The sharpest part is written down explicitly: a
socket write that raises *after* the request reached the venue is indistinguishable, from inside
this process, from one that never left — which is exactly why `place_order` rolls back and re-raises
rather than retrying. Retry is admissible only on genuinely idempotent reads, and even there must
not mask a CANNOT-MEASURE as a stale value.

Two assertions enforce it rather than trusting the prose:
- `NO-RETRY: a failed placement leaves ZERO orders at the venue (no auto-resend)`
- `margin: a prior success is NOT served as a fallback on a later failure`

Nothing else was added.

---

## 4. What the gate itself measured

Bringing `scripts/broker/` into the static sweep's **file list** surfaced something worth your
attention, unrelated to this arc's findings.

Those files have been in the tree since ARC 014 and were passing `pre-commit run --all-files`. They
were passing because they are **untracked**, and `--all-files` means all *git-tracked* files. Run
explicitly against them, the same hooks produced: ruff 11 findings, pylint 229 findings across 20
codes, mypy 7 type errors in 3 files, complexipy 2 drivers over the 15 ceiling (37 and 25).

**A gate whose scope is set by what has been `git add`ed can be silenced by not adding.** That is
the "can it be made to pass by editing something it also reads?" question from the debug doctrine's
Stage 2, in a form nobody edited anything to create.

All of it is now clean, both ways:
- Real fixes where the finding was real: two lifted helper functions, three over-long lines, a
  needless lambda, an un-narrowed `float()`, `_symbol_for` returning a non-`str`, a `RecordingFeedSink`
  (the seam suite had been passing an **order** sink into the **datafeed** port — invariant 3 says
  they are disjoint, and it only survived because no feed event was ever driven through it), and the
  two long drivers split into named sections.
- Named, reasoned suppressions where the finding was not: e.g. `FakeIB` **must** use camelCase to
  mirror ib_async's real surface, and the tests **must** read `_mirror`/`_from_ib` because that
  internal state is the thing under test. Every suppression names its codes and states why — never a
  blanket disable.

Side effect: this discharges **D3.2** (ruff/pylint/mypy/complexipy never demonstrated capable of
failing on this repo) with evidence from real code rather than a contrived plant.

---

## 5. Definition of success

- [x] **Port split applied per Part 1; `check_await_conformance()` clean AND demonstrated capable of
      failing via a planted divergence that it names** — §1. Clean on all four subjects; plant named
      `query_positions` and reported both sides of the disagreement; plant removed, file
      byte-identical; kept permanently as `AwaitDivergentBrokerOrder`.
- [x] **The false scheduling claim removed from `broker_order_ibkr.py`** — §1, replaced with what is
      true and with the retraction recorded.
- [x] **`HollowBrokerOrder` still fails the behavioural suite after conversion** — §1, 9 failures.
- [x] **Zero-qty rows filtered from `query_positions()`; test fails without the fix** — §2a,
      mutation M1, 3 assertions.
- [x] **Startup-execution handling made deliberate with the mechanism stated; test proves it is
      ignored by design and survives a reconnect** — §2b, connect-scoped gate (stated, with the
      reasoning for choosing it), plus two related corrections; mutation M2, 4 assertions; asserted
      across two reconnects.
- [x] **Missing-ack race closed; ack proven to precede the fill on `PendingSubmit → Filled`** — §2c,
      both event orderings, cross-stream ordering observable; mutation M3, 9 assertions.
- [x] **`FakeIB` carries multiplier/notional/commission fidelity; the original `avg_price` unit bug
      re-planted and now caught** — §2d, caught by 6 assertions.
- [x] **`pytest-asyncio` pinned in `checks/pinned_deps.json`** — 1.4.0, installed,
      `check_python_deps` green against it.
- [x] **No retry/backoff on the order path; the reasoning recorded where a future author will read
      it** — §3, module docstring plus two enforcing assertions.
- [x] **All suites green; Tier-2 gates pass; `verify.py` exit 0** — §6.
- [x] **Account confirmed flat at close with a fresh venue query, if any order was placed** — **no
      order was placed.** Every finding was closed offline, which is what Part 2d existed to make
      possible. The Gateway was never connected and no live session was opened during this arc.

---

## 6. Numbers

| measure | before | after |
|---|---|---|
| project pytest suite | 154 passed | **155 passed** |
| adapter driver assertions (`test_broker_order.py`) | 42 | **79** |
| seam simulator assertions (`seam_simulate.py`) | 26 | **33** |
| `verify.py` | 6 passed, exit 0 | **6 passed, exit 0** |
| Tier-2 pre-commit, tracked tree | 8/8 pass | **8/8 pass** |
| Tier-2 pre-commit, `scripts/broker/` explicitly | never run | **8/8 pass** |
| pinned packages | 1 | **2** |
| mutation tests proving non-vacuity | 1 (Hollow) | **6** (Hollow, await plant, M1, M2, M3, re-planted unit bug) |

---

## 7. Open for the architect

1. **`scripts/broker/` is untracked.** Nothing in it is committed, so the commit gate covers it only
   when it is named explicitly. Recorded as **D1.15**/**D3.2** in `CHECK-DEBT.md`. It should be
   `git add`ed at the next commit boundary.
2. **`seam_simulate.py` is not in the pytest suite.** It holds both seam non-vacuity controls and is
   only ever run by hand. Recorded as **D1.15**. Out of ARC 015's scope; cheap to close.
3. **`query_order_status` stays sync by contract.** If a vendor ever forces a venue round trip
   there, that is a contract change to be argued, not a signature to flip — the §4 pending-timeout
   path calls it.
4. **D1.12 (reboot persistence) remains open**, untouched as the arc directed.
