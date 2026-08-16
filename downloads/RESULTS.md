# ARC 033 — R4-A: Blackouts, Pollers, and the Origin Write

**Canonical path:** `/home/bbt/nix` (absolute, unmoved). Nothing was relocated.
**Not pushed.** `origin/main` is where ARC 031 left it; the push is the operator's.

---

## THE HEADLINE: THE RULES EXISTED, THE PRODUCERS DID NOT

§6.5's unified pre-size denial — `HALT ∨ now ∈ any window ∨ margin elevated ∨ data stale ∨ clock
skewed` — has been **assembled by name** in `scripts/nixrisk/gate.py` since ARC 028, and
`check_limiter_gate` has gated the executor with 8 arms. **Nothing implemented any of the four
ports.** The rules were wired to inputs that did not exist.

That is ARC 031's failure inverted: there, three green gates sat over a cap that could not run; here,
a proven executor sat over ports nobody had built. So Stage 1 built **producers**, and the
distinction is the spec's own — §6.5 says new blackout types are **data (a window), not code**, and
`SymbolFlagRule`'s docstring says a class per window type *"would be the code the spec says not to
write."* A brief followed literally would have minted four such classes.

| port | consumer (since ARC 028) | producer (ARC 033) |
|---|---|---|
| `blackout_window` | `SymbolFlagRule(…, "§6.1-6.3")` | `nixrisk/blackout.py` |
| `data_staleness` | `SymbolFlagRule(…, "§6.4")` | `nixrisk/freshness.py` |
| `clock_skew` | `GlobalFlagRule(…, "§12.3")` | `nixrisk/freshness.py` |
| `HaltFlagPort` | branch 0, before the manifest | `nixrisk/halt.py` |

Plus `nixrisk/session.py` (§6.1b deadline), `nixrisk/roll.py` (§7.5 roll instant),
`nixrisk/positions.py` (the origin write) and the extended calendar.

---

## THE §6.5 INTERLOCK, AS A FIGURE RATHER THAN A CLAIM

§6.5 asserts the 70% cap is only safe because the blackouts keep the book out of the close-snap —
*"cap + blackout calendar are one coupled system."* Driven with ONE cap-breaching proposal, run twice
through the real `GatePass`:

```
window CLEAR : size_down by aggregate_margin_cap, 10 rules evaluated
window OPEN  : deny      by blackout_window,       2 rules evaluated
               and aggregate_margin_cap NEVER RAN
```

The calendar keeps the book from ever reaching the state the cap exists to refuse. The first half
exists so the second half means something: a test that never builds a breaching proposal proves
nothing about a coupling.

---

## §12.10's TABLE CONTRADICTS THE BRIEF, AND THE SPEC WON

Stage 2.3 asked for **Plane-1** rows for *blackout opened/closed* and *roll seam*. §12.10's own event
inventory routes both to **Plane 2 ONLY** — the Plane-1 cell is an em dash. Writing them to Plane 1
would add diagnostic events to §9's append-only record of money truth, against §12.10's *"Plane 1 …
No new writers, ever"* and its statement that Plane 2 is *"diagnostic only — never a reconciliation
input, never read by the trading path."* HALT set/cleared **is** both, and the spec gives the reason:
*"it gates money."*

The correction is **pinned by reading the frozen spec at run time**, not by restating it — so if a
later arc amends §12.10, the test fails and the correction is revisited deliberately instead of
surviving as a stale opinion.

---

## THE TWO CARRIED CORRECTIONS

**D3.144 — DISCHARGED BY REAL COVERAGE**, which is what the architect ruled instead of an exclusion.
`check_execution_ledger`: five arms, nine plants, every plant a defect in the **subject** driven with
a stream §4 requires the ledger to absorb. **Doctrine C.9 answered by measurement, not argument:** a
running-total plant is permutation-invariant *and* duplicate-immune, so every behavioural arm and
every property `test_execution.py` already owns stays green over it — only the structural arm
reddens. `check_artifact_gate_coverage` CANNOT_MEASURE → **GUARDED**; uncovered 13 → 12; ratchet
tightened. The baseline removal was proven **required**, not tidy: with the entry restored, the
stale-baseline arm FAILs naming that row exactly.

**D3.150 — NARROWED, DELIBERATELY LEFT OPEN.** The origin write is built and gated: it takes
`stop_distance` from the stop book's own `initial_distance_ticks` onto the same versioned snapshot,
and the gate reddens on a value that is present, positive, plausible **and wrong** — which a
null-check would pass. **But `StopBook.arm` and `on_fill` both have zero production callers**
(D3.178), so production still never *chooses* a distance. Closing the row on a built mechanism would
be the move D3.136 was closed against: **a decision recorded is not a mechanism landed, and a
mechanism landed is not a mechanism CALLED.**

---

## THREE THINGS THE BRIEF GOT WRONG, MEASURED BEFORE BUILDING

1. **The trade↔order join did not exist.** §3:159 keys the position table by `trade_id`; `StopState`,
   `ProposedOrder`, `Reservation` and §4's dedup tuple all key by `client_order_id`; nothing joins
   them. The brief's own success criterion — *"the published stop_distance for the same trade"* — was
   **not expressible**. Made a SURFACE, not an equality: under the plausible default the two ids are
   equal, so a hard-coded equality emits byte-identical rows and no drive over the default can see
   it. The gate re-drives the population under a **non-identity mint**, the only way that defect is
   visible. D3.177 returns the ruling.
2. **The calendar already existed.** Extended, not rebuilt (C.9). And *"never stored Central"*, taken
   literally, would have reddened the shipped tree: `eth_open_ct`/`eth_close_ct` exist, are generated
   via tzdb, are DST-correct, and are **read by nothing**. The enforced invariant is **no decision
   path may READ a stored local-time field** — true, mechanically checkable, and it keeps a
   stored-but-unread column from becoming the next arc's shortcut.
3. **A4's rule had no authority.** *"Econoday"* and the *"calendar-source-conflict addendum"* appear
   **nowhere in this tree except the brief**; the frozen spec names no calendar vendor and neither
   does the staging plan. §0b/D3.81 forbids acting on a labelled rule with no ledger id, so it was
   given one — **`SPEC-A10`** — which also records why it cannot be BUILT: there is exactly ONE
   calendar source, so a conflict cannot occur, and a gate over it would drive a disagreement it
   manufactured between two halves of one artifact. The vendor is recorded **UNRATIFIED**.

---

## WHAT A SESSION CAP COST, STATED PLAINLY

Four Stage-1 sub-agents were killed mid-flight. 1C and 1D died **inside the commit gate** with their
work complete on disk and never committed — and §0d is explicit that an mtime is not history.

The integrator measured the delivered code before banking it — `check_pollers` (8 arms),
`check_staleness` (10 arms), `check_halt`, all PASS, with 99 + 51 tests green — and banked it rather
than discarding ~150 passing tests to re-run work that was finished. **What could not be rescued is
each author's own §0a self-audit**, the audit that caught a scope error in *every* sub-agent that
reported across two arcs. **D3.191** records that those four modules' gates are UNAUDITED until a
review pass asks §0a directly. Inventing an audit the integrator cannot perform would be the
restatement this ledger exists to refuse.

**The order-path literal was bumped five times from five blind worktrees** — 1A 18→19, 1B 18→20,
1C 18→20, 1D 18→19 — each locally right, all globally wrong, surfacing as three separate merge
conflicts on one line and resolved every time at the figure `check_order_path_bans` itself reports on
the merged tree: **24**. Two bumps had to be made by the integrator because the authors were gone.
The literal stays a **literal**: deriving it from the gate would make the test agree with its subject
by construction. D3.192 records that N parallel worktrees adding modules to one package home produce
N−1 guaranteed conflicts on it.

**The subjects corrected me twice.** `halt.HaltFlag` refused to construct against my integration
fixture — *"halt cooldown floors name ['operator'], which is not an auto-clearing §12.5:631 cause …
'operator' in particular clears ONLY by operator (§12.5:633), so a floor for it would imply an
auto-clear that does not exist"* — the fixture was wrong and the module was right. And my first draft
assumed `GateOutcome` carried a verdict list; it carries the binding rule and reason directly.

---

## CLOSE-OUT GATES

| gate | result |
|---|---|
| `verify.py` **venv** `/home/bbt/nix/.venv/bin/python` | `57 passed \| 1 failed \| 2 cannot measure \| 0 skipped \| 1 guarded` · exit 1 |
| `verify.py` **system** `/usr/bin/python3` | `57 passed \| 1 failed \| 2 cannot measure \| 0 skipped \| 1 guarded` · exit 1 |
| pytest | **2343 passed, 2 skipped, 2 xfailed** (from 1982 at arc start) |
| claims harness | green |
| CHECK-DEBT | **201**, derived twice, never typed |
| plan (`--optimize --commit`) | *"derived plan is identical to the live registry"* |
| census three ways | **61 == 61 == 61** |
| binding | **BOUND=59 · ENR=2 · UNBOUND=0** over 1,913 observations — all nine new gates BOUND, floor 48 |

**Identical under both documented interpreters.** Every non-PASS named:

* **FAIL — `check_ibgateway_service`**: `127.0.0.1:4002` ECONNREFUSED. The standing tap-session FAIL,
  by design, and the only code-independent one.
* **CANNOT_MEASURE — `check_ibgateway_config`**: same dead port, §4.1.
* **CANNOT_MEASURE — `check_observed_resource_claims`**: §17 masking by the same dead port.
* **GUARDED — `check_artifact_gate_coverage`**, owner **ARC 033** on all twelve remaining rows.

---

## WHAT IS STILL YOURS

1. **The push.** Not pushed.
2. **D3.177** — the `trade_id` ↔ `client_order_id` ruling. A default binding shipped in its absence,
   injected and overridable, so your ruling costs one argument rather than an audit.
3. **D3.150 / D3.178** — the fill handler that ARMS the stop and CALLS the origin write. Until it
   exists, §7's cap is fed by a mechanism nothing invokes.
4. **SPEC-A10's vendor** — `Econoday` is UNRATIFIED and an arc may not mint a vendor.
5. **D3.191** — the §0a review pass over the four rescued modules.
6. **The tap session** — still the only code-independent FAIL.

---

## POST-WRITE-BACK RE-MEASURE — banked BEFORE the marker (§16.4 / `CHECK-A10`)

The write-back appended ARC 033's summary to `sessions/SESSION.md`, which makes ARC 033 a COMPLETED
arc to `contract.completed_arcs`. All twelve remaining coverage rows are owned by ARC 033, so:

```
check_artifact_gate_coverage:  GUARDED (exit 3)  ->  CANNOT_MEASURE (exit 2)
  12 rows [gate_coverage_baseline.json:artifacts:scripts/harness.py:owner, …:monitor.py:owner,
           …:nixverify/venv_lock.py:owner, …] — owner 'ARC 033' has ALREADY COMPLETED

verify.py  →  57 passed | 1 failed | 3 cannot measure | 0 skipped   exit 1
```

**Predicted in writing before the commit that caused it.** This is D3.40's mechanism met for the
third arc running — ARC 031 on D3.138, ARC 032 on D3.144, ARC 033 on all twelve — and it is exactly
why §16.4 orders the re-measure BEFORE the marker rather than waiving it. Nothing else moved.

**Both figures are true of different moments**, and quoting only one would hide something:
`57 | 1 | 2 | 0 | 1` immediately before the write-back, identical under both interpreters, and
`57 | 1 | 3 | 0 | 0` immediately after.
