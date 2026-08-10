# ARC 015 — Apply the async Contract Decision; Close the ARC 014 Findings

## Read first

**Do not expect new `.py` files with this arc.** The landed copies in `scripts/broker/` and
`scripts/tests/` are **ahead of the architect's** — they carry ARC 014's `avg_price` unit fix
and `check_await_conformance()`, which the architect's originals do not. Modify the landed
code in place. Sending fresh files would silently revert real fixes.

(Handoff note: ARC 014's own arc document never reached the machine, the second such failure
after `VERIFY-AND-CHECKS.md` in ARC 008. If this document is the only thing that arrived and
something it references is missing, say so before proceeding rather than substituting.)

ARC 014 found five defects in architect-written code and fixed one. This arc resolves the
architectural question and closes the other four.

---

## Part 1 — The sync/async decision (operator-ratified)

**Decision: the seam is split. Send-path verbs stay sync and fire-and-forget; query verbs are
declared `async` in the port.**

| verb | contract | why |
|---|---|---|
| `place_order` | **sync** | §2A already says it returns an ack via `on_ack`, never a value. Invariant 5 requires the send path be non-blocking. |
| `cancel_order` | **sync** | same path |
| `flatten` | **sync** | protective path, MUST NOT BLOCK (§2A). ARC 014 measured 0.6 ms with zero venue queries — keep it that way. |
| `disconnect` | **sync** | teardown, no result needed |
| `query_order_status` | **sync** | reads a cached `Trade.orderStatus`; no venue round trip |
| `connect` | **async** | off hot path |
| `query_positions` | **async** | cold-start reconciliation (§4), off hot path |
| `query_balance` | **async** | off hot path |
| `get_margin` | **async** | poll fallback, off hot path, already needs an explicit timeout |

**Rejected alternative, recorded so it isn't relitigated:** having the adapter schedule onto the
loop to preserve a fully-sync port — which is what the architect's docstring falsely claimed was
already happening. It resolves to either `run_until_complete` (blocks — violates invariant 5) or
returning futures (an async contract wearing a sync signature, which is worse than declaring it).

Apply this to `BrokerOrderPort`, `StubBrokerOrder`, `HollowBrokerOrder`, and every caller/test.
`check_await_conformance()` must come back clean — and it must still be capable of *failing*:
demonstrate it by planting one divergence, confirming it names the verb, and removing the plant.

**Delete the false docstring claim in `broker_order_ibkr.py`.** It asserted scheduling that does
not exist. Replace it with what is actually true after this change.

`HollowBrokerOrder` must remain a *failing* control after conversion. A control that is quietly
repaired into conformance stops being a control.

---

## Part 2 — Close the four open findings

### 2a. `query_positions()` leaks zero-quantity rows (ARC 014 §6)
IBKR returns a `position=0` row after a round trip. The mirror filters `net_qty != 0`; the
returned list does not. §4 makes this call **cold-start ground truth**, and a caller doing
`if broker.query_positions(): halt()` sees a phantom position.

Filter zero rows from the returned list so the mirror and the return value cannot disagree.
Add a test that fails without the filter.

### 2b. Startup executions reach the fill handler (ARC 014 §6)
`_wire_events()` runs before `connectAsync`, whose default `fetchFields` includes `EXECUTIONS`,
so historical executions are delivered to `_on_ib_exec_details` at connect. They are dropped
today **only** because `_from_ib` happens to be empty — accidental, not designed.

Make it deliberate. Either narrow `fetchFields`, or gate the fill handler on a connect-complete
flag, or wire events after connect — your call, but state which and why, and make the mechanism
survive a reconnect (Gateway auto-restarts daily at 03:00). Add a test that delivers a historical
execution at connect and proves it is ignored **by design**, not by luck.

### 2c. The missing-ack race (ARC 014 §7) — build the gate
`_on_ib_order_status` acks only on `PreSubmitted`/`Submitted`. A market order going
`PendingSubmit → Filled` produces **no ack at all**, and the Limiter waits forever on an order
that already filled. Live, the venue emitted `PreSubmitted` then `Filled` 44 ms apart — one
sample of a race, not proof it cannot happen.

Close it in the adapter: any transition into a terminal state without a prior ack must synthesise
the ack before the fill/cancel event, so the Limiter never observes a fill for an order it never
saw accepted. Then prove it — drive `PendingSubmit → Filled` with no intermediate state and
assert the ack precedes the fill.

### 2d. `FakeIB` fidelity (the debt behind ARC 014's real defect)
The `avg_price` unit bug was invisible offline because `fut()` has no `multiplier` and every
mirror assertion checks only `net_qty`. **The fake being unable to represent a defect is its own
debt.** Fix it:
- `fut()` carries a real `multiplier` (MES 5, ES 50)
- `positionEvent` reports `avgCost` as **notional** (price × multiplier), as IBKR does
- Mirror assertions check `avg_price`, not just `net_qty`
- Add the commission-inclusive `avgCost` wrinkle ARC 014 measured (7773.500 raw vs 7773.622
  from `avgCost`, the 0.122 being commission ÷ multiplier) so provenance differences are
  representable

Then confirm the fake earns its keep: **re-plant the original unit bug and verify the improved
suite now catches it.** A fake that could not catch the defect it was blind to is not yet fixed.

---

## Part 3 — Libraries

The operator's standing preference is industry-standard tooling. Two notes rather than a free hand:

**Adopt:**
- `pytest-asyncio` (or `anyio`'s pytest plugin) — required once the query verbs are `async`.
  Pin it, and add its pin to `checks/pinned_deps.json` so `check_python_deps` covers it.
- `asyncio.TaskGroup` over bare `create_task` for any supervised concurrency. Python 3.14.4 is
  installed, so structured concurrency is available and is the current best practice; a task
  that dies silently in the background is the failure mode it prevents.

**Do NOT adopt, and record why:**
- **No retry/backoff library (`tenacity`, `backoff`, or hand-rolled) anywhere on the order path.**
  This is where a best-practices instinct actively causes harm: §4 states that a pending timeout
  resolves via an order-status query and the system **never auto-resends**. A retry decorator on
  `place_order` silently converts one intended order into two. Retry is acceptable only on
  genuinely idempotent reads (`query_balance`, `get_margin`), and even there it must not mask a
  CANNOT-MEASURE into a stale value.

Anything else you propose to add, justify against what it replaces.

---

## Definition of success

- [ ] Port split applied per Part 1; `check_await_conformance()` clean **and** demonstrated
      capable of failing via a planted divergence that it names
- [ ] The false scheduling claim removed from `broker_order_ibkr.py`
- [ ] `HollowBrokerOrder` still fails the behavioural suite after conversion (control intact)
- [ ] Zero-qty rows filtered from `query_positions()`; test fails without the fix
- [ ] Startup-execution handling made deliberate with the mechanism stated; test proves it is
      ignored by design and survives a reconnect
- [ ] Missing-ack race closed in the adapter; ack proven to precede the fill on a
      `PendingSubmit → Filled` transition
- [ ] `FakeIB` carries multiplier/notional/commission fidelity; **the original `avg_price` unit
      bug re-planted and now caught**
- [ ] `pytest-asyncio` pinned in `checks/pinned_deps.json`
- [ ] No retry/backoff on the order path; the reasoning recorded where a future author will read it
- [ ] All suites green; Tier-2 gates pass; `verify.py` exit 0
- [ ] Account confirmed flat at close with a fresh venue query, if any order was placed

## Out of scope

- broker-datafeed — separate library, separate process, separate arc (§2A invariant 3)
- No Limiter, Allocator, Risk Engine, or strategy code
- No Gateway settings changes; no reboot (D1.12 stays open)
- Live order placement is **not required** by this arc. If a finding genuinely cannot be closed
  without one, paper DUR250018 / MES / qty 1 / flat between tests still applies — but prefer
  offline proof where the offline suite can now carry it, since Part 2d exists precisely to make
  that possible.

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
