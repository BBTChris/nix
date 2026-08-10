# ARC 016 — Commit the broker Package; Prove Gate Coverage; Re-validate Live

## Why this arc exists

Two arcs of real code exist **only on node02's filesystem**. ARC 014 landed
`scripts/broker/` and `scripts/tests/test_broker_order.py`; ARC 015 substantially rewrote
them. Nothing has been committed. A stray `git clean -fdx` erases both arcs, and there is no
review trail for the first application code in the project.

ARC 015 §4 also established that the commit gate was green on those files while measuring
nothing, because `pre-commit run --all-files` means all *git-tracked* files. That was fixed by
naming the directory explicitly. **Naming is not the fix — tracking is.** A gate whose scope
depends on someone remembering to name a path will eventually be run by someone who doesn't.

Third: ARC 014's 31 live assertions validated code that has since changed on the very paths it
exercised. The current adapter has never connected to a Gateway.

No new features in this arc. Consolidation only.

---

## Part 1 — Track the code, then prove the gate follows

1. `git add` `scripts/broker/` and `scripts/tests/test_broker_order.py`. Check for anything
   that should **not** be tracked (caches, `__pycache__`, editor droppings) and gitignore it
   rather than committing it.
2. Confirm nothing else in the tree is silently untracked and therefore silently ungated.
   `git status --porcelain --untracked-files=all` across `scripts/`, `checks/`, and any other
   directory the gate is supposed to cover. **Report the full list**, even if empty — an empty
   result stated is worth more than an absence assumed.
3. **Prove the gate now covers these files by virtue of tracking, not naming.** Plant one
   defect in a tracked broker file that the hooks should catch — pick something unambiguous
   (an unused import for ruff, or a type error for mypy). Then:
   - run `pre-commit run --all-files` **without naming any path**
   - confirm it fails and names the planted site
   - remove the plant, confirm clean, confirm the file is byte-identical to its pre-plant state

   This is the same control shape ARC 015 used for `check_await_conformance`, applied to the
   gate's *scope* rather than its logic. Record the before/with-plant/after output.

4. Branch, commit, PR, merge to main. Follow the ARC 007/009 pattern
   (`gh pr merge <n> --merge --admin`). Suggested branch: `arc-016-broker-consolidate`.
   The commit message should say what landed across ARC 014 and 015, because this single commit
   is carrying two arcs of work into history.

---

## Part 2 — Close the cheap debts

### 2a. `seam_simulate.py` into pytest (D1.15)
It holds **both seam non-vacuity controls** — `HollowBrokerOrder` and
`AwaitDivergentBrokerOrder` — and is currently only ever run by hand. A control that only runs
when someone remembers to run it is not a control. Give it a pytest entry point the way
`test_broker_order.py` got one, so the project suite carries it. Confirm the controls still
*fail* their behavioural assertions after the conversion.

### 2b. Record the joint dependency in the startup-execution fix
ARC 015 §2b describes dropping `EXECUTIONS` from `fetchFields` as belt-and-braces over the
connect-scoped gate. It is more load-bearing than that framing suggests: the gate deliberately
opens **before** `_rebuild_mirror()` awaits `reqPositionsAsync`, so if `EXECUTIONS` were ever
restored, replayed executions could land inside that await window and pass an already-open gate.

The two mechanisms are **jointly** sufficient and individually are not. Write that into the code
where both are set, so a future author does not remove one believing the other covers it.

### 2c. Promote the recurring failure class to doctrine
ARC 015 §4 is the **seventh** instance of one pattern in this project:

- bandit scanning nothing since ARC 006
- CHECK-DEBT hand-miscounted, twice
- the unread 10-minute delay in ARC 010's own output
- `check_structural_conformance` passing `async` against a sync-declared port
- `avg_price` invisible to a polite `FakeIB`
- `--all-files` not covering untracked files
- an **order** sink passed into the **datafeed** port, surviving only because no feed event was
  ever driven through it

Every one is a green light that measured nothing. Seven is not a run of bad luck; it is this
project's characteristic failure mode.

Promote it from debt item **D2.8** to a stated principle in the debug/verification doctrine,
with a standing question attached to every new gate: **"what would have to be true for this to
pass while measuring nothing?"** — and require that the answer be written down at the point the
gate is built, not discovered two arcs later. The seven instances above are the evidence base;
cite them so the principle arrives with proof rather than as an assertion.

---

## Part 3 — Re-validate the changed paths against the live Gateway

ARC 015 closed every finding offline, which was correct and is what its Part 2d existed to make
possible. But these paths changed after ARC 014's live run and have never met a venue:

| changed | needs live proof because |
|---|---|
| `connect()` now async, with a startup gate and `fetchFields` minus `EXECUTIONS` | if `fetchFields` was over-narrowed, connect may not populate what later calls assume |
| id maps cleared **before** `connectAsync` | reordering around the live connect sequence |
| `_wire_events()` idempotent per IB instance | the duplicate-handler bug only manifests on a real second connect |
| `query_positions()` async + zero-qty filter | the zero-qty row is a *venue* behaviour, only reproducible there |
| ack synthesis on terminal-without-ack | changes what the Limiter observes on a real fill |
| `avg_price` normalisation | fixed in ARC 014 and live-proved then, but the code has moved |

Connect on **clientId=905**. Never 1 (reserved for the Risk Engine), never 0 (permanently
excluded — implicitly adopts manual TWS orders).

### 3a. Read-only first
- `connect()` succeeds; `on_session(UP)`; mirror rebuild does not raise
- `query_positions()` — account flat; **zero-qty rows genuinely filtered against real venue
  output**. If IBKR doesn't emit a zero-qty row on a flat account, say so — the filter is then
  proved only offline and that should be stated, not implied.
- `query_balance()` — real figures; `ts_is_venue_sourced=False` still set (GAP-2)
- `get_margin("MESU6")` — a real figure via `whatIfOrderAsync` under timeout (the ARC 012 trap)

### 3b. The reconnect, which offline could not fully prove
`connect()` → `disconnect()` → `connect()` against the real Gateway. Assert:
- handler count per event is unchanged after the second connect (`_wire_events` idempotency —
  this is the one that offline could only simulate)
- no ack or fill is produced from any startup replay on either connect
- the id map does not carry across

### 3c. Order lifecycle — paper DUR250018, MES only, qty 1, flat between every test
- one BUY 1 MESU6 MKT: ack arrives via the event stream exactly once; `on_fill` carries
  `cumQty`; **`avg_price` is per-unit, not notional** (the ARC 014 defect, re-proved live)
- **`flatten()` against the real open position** — still the centrepiece. Re-prove: returns
  without blocking, **zero `reqPositionsAsync` calls during the call** (wrap and count as ARC 014
  did), venue confirms flat afterwards.
- one far-off LMT, then `cancel_order`; `query_order_status` resolves correctly
- **Observe, do not force:** whether the venue ever produces `PendingSubmit → Filled` with no
  intermediate state. ARC 014 measured `PreSubmitted → Filled` 44 ms apart. If it doesn't occur,
  record that the synthesis path remains offline-proved only. Do not manufacture it live.

State the market state. A closed market makes lifecycle results CANNOT-MEASURE, not failures.

A `finally` cleanup that cancels strays and closes any residual position must run, as in ARC 014.

---

## Definition of success

- [ ] `scripts/broker/` and the adapter test tracked in git; full untracked-file audit reported
- [ ] **Gate coverage proved by tracking, not naming**: defect planted, caught by an unqualified
      `pre-commit run --all-files`, removed, file byte-identical
- [ ] Committed, PR'd, merged to main; commit message covers both ARC 014 and 015
- [ ] `seam_simulate.py` in the pytest suite; both non-vacuity controls still *fail* as controls
- [ ] The joint gate/`fetchFields` dependency written into the code
- [ ] D2.8 promoted to doctrine with the standing question and the seven-instance evidence base
- [ ] Live: connect, positions, balance, margin verified on clientId=905 with real figures
- [ ] Live: reconnect proves `_wire_events` idempotency by handler count
- [ ] Live: order lifecycle on MES — ack-once, per-unit `avg_price`, cancel, status
- [ ] Live: **`flatten()` closes a real position with zero venue queries**; venue confirms flat
- [ ] Ack-synthesis path either observed live or explicitly recorded as offline-proved only
- [ ] Account confirmed flat at close via fresh venue query
- [ ] `verify.py` exit 0; Tier-2 gates pass on the now-tracked tree

## Out of scope

- **broker-datafeed** — separate library, separate process, separate arc (§2A invariant 3)
- No Limiter, Allocator, Risk Engine, or strategy code
- No new adapter features; no behaviour changes beyond 2b's comment and 2a's entry point
- No Gateway settings changes; no reboot (D1.12 stays open)
- No ES orders

## Standing note

If a git action is refused by the permission classifier, report it and move on — but note that
Part 1 is the point of this arc, so a refusal there is a blocking finding, not a footnote.

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
