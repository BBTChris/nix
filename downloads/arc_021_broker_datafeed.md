# ARC 021 — R1-B: broker-datafeed, the second §2A library
### 2 sub-agents · offline-first · disjoint from broker-order by invariant, not by convention

===RUN SUMMARY: ARC 021 — R1-B broker-datafeed; FeedLag as a first-class interface property; granted-mode and bar-immutability gates, Estimated run time: 4–5 h, completes ~15-18% of the current stage (lands the second of the two §2A libraries against the delayed-and-polled Stage 0 shape, makes the ~600 s feed lag a declared property of the interface rather than a fact people remember, and closes D1.13 and D1.14 — the two gates that have been waiting for a datafeed to exist since ARC 010)===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract
- `~/nix/docs/debug.md` v1.2.0 — **§5** tiers, **§7.4** stale anchors, **§7.12** the standing question
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A (the datafeed port and the invariants at
  §2A:103–107), §4, §13
- `~/nix/docs/SPEC-AMENDMENTS.md` — the pending rulings, including the third added below
- `~/nix/docs/CHECK-DEBT.md`

Authority order per `CLAUDE.md`. **Verified on-disk state outranks this document.**

`python` is not on PATH; use `.venv/bin/python`. `verify.py` is at `scripts/verify.py`.

### 0a. Citations

`check_spec_citations.py` will check this brief's `§`-references mechanically. Two things it
cannot catch, both mine, both standing:

- **`V9`/`V11`/`V24` is architect shorthand.** §13 numbers objectives 1–23 plainly and only adopts a
  `V` prefix at V24. This brief writes "§13 objective N" for 1–23.
- **Success criteria are cross-checked against rulings this time.** ARC 020 found two places where
  my brief contradicted itself — a criterion requiring a traversal to keep passing that the same
  document's ruling necessarily inverted, and C1 retiring a phrase §9.5 then demanded by name. If
  you find a third, say so; it is a class I am now watching for and have not yet eliminated.

### 0b. Baseline — confirm, do not assume

```bash
cd ~/nix
git rev-parse --short HEAD
git fetch origin && git merge-base --is-ancestor HEAD origin/main && echo "on origin/main" || echo "NOT on origin/main"
git status --porcelain
git config --get core.bare
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
.venv/bin/python checks/check_spec_citations.py; echo "spec_citations exit=$?"
ls -la ~/nix/downloads/TAP_SESSION.md 2>/dev/null && echo "TAP SESSION PRESENT" || echo "NO TAP SESSION"
```

ARC 020 reported: 242 passed / 0 xfailed, pre-commit 8/8, claims 10/10, debt 40 rows, merged at
`d377ed6`. **Reported values, not targets.**

**`verify.py` may legitimately be exit 1.** ARC 020 closed with `check_ibgateway_service` failing and
`check_ibgateway_config` cannot-measure, both from IBKR's daily session expiry — not code. If a tap
session has since run, expect exit 0. **If it has not, exit 1 with those two checks and that cause is
the accepted baseline for this arc**, and the success criteria below say so rather than demanding a
green nobody can produce.

`git fetch` before the ancestor check: ARC 020 found local `main` stale at the ARC 018 merge while
`origin/main` was correct.

**If `TAP_SESSION.md` exists, read it first.** It carries the granted-`marketDataType` observation
and a re-measured feed lag, and both are inputs below. If it does not exist, §4 and §5 proceed with
declared reds rather than waiting.

---

## 1. THE PROHIBITION THAT DEFINES THIS ARC

**Invariant 3 requires broker-order and broker-datafeed to be disjoint — no shared object.**
(§2A:103–107; verify the exact line before citing it.)

`broker_order_ibkr.py` already contains connection handling, session-state publishing, error-code
mapping and reconnect logic. Writing a datafeed adapter will surface an obvious opportunity to
factor that out into something both import.

**Do not.** That is the invariant violation, and it will look like good engineering at the moment it
happens — which is exactly why this is stated before you reach the decision rather than after.

The two libraries may duplicate code. **Duplication between them is the design, not debt.** They run
in different processes on different cores (Core 1 capture, Core 2 Risk Engine), they fail
independently by requirement, and §13 objective 24's whole subject is proving a datafeed fault does
not disturb the order path. A shared object makes that objective unprovable no matter how the drill
is run.

If you believe a specific extraction is safe, **stop and argue it**. Do not extract and explain.

---

## 2. Hard prohibitions

1. **Invariant 3 — no object shared between the two libraries.** §1.
2. **Do not edit the frozen specs.** New surface lands as declared Nix additions, following the
   `feed_lag()` / `UP_DATA_LOSS` precedent, plus a `docs/SPEC-AMENDMENTS.md` entry attributed as an
   operator ruling, never as spec text (D2.17).
3. **No retry/backoff on the order path.** Note the asymmetry: retry is **mandated** for pollers
   outside it (§12A:827, §6.4:374, §13:900), and the datafeed's poll fallback is squarely outside.
   `check_order_path_bans` derives its scope from `scripts/broker/` — **if adding a datafeed file
   reddens it for spec-mandated polling behaviour, the repair is to the scope boundary, never to the
   ban.** Report it rather than working around it.
4. **`clientId=0` permanently excluded.** Diagnostics **905**; **1** reserved for the Risk Engine.
   Decide and state which clientId the datafeed will use in production — it must not be 1, and
   sharing 905 with diagnostics is a decision, not a default.
5. **Do not build the Limiter, the Allocator, `capture.py`'s process wiring, or any consumer.**
   Record obligations; build state.
6. **No Tier-3 traversal this arc.** `debug.md`'s tiers are sequential, and a module that did not
   exist this morning cannot have a Tier-3. Tier 1 and Tier 2 land here; **Tier-3 is named for ARC
   022** and that is the honest sequencing, not a deferral to save time.
7. **No hand-typed numbers in `RESULTS.md`.**
8. **Purge `__pycache__` between every plant/unplant step.**
9. **No plant survives the arc.**

---

## 3. Sub-agent dispatch

| agent | owns (write) | may read | forbidden |
|---|---|---|---|
| **A** | `scripts/broker/**`, `scripts/tests/test_broker_datafeed.py` | all | `checks/**`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |
| **B** | `checks/**`, `checks/derived_claims.json`, `docs/CHECK-DEBT.md` | all | `scripts/broker/**`, `scripts/tests/**`, `.pre-commit-config.yaml` |

**Two agents, not three.** A Tier-3 agent has nothing to traverse until A lands, and ARC 020
established that parallel agents over one file trade a real merge hazard for no throughput.

**Before dispatch:** confirm the worktree provisioning fix landed. ARC 020 finding 9 — `state/` is
gitignored so a fresh linked worktree has no `state/node_identity.json` and no `.venv`, failing
`check_node_identity` and blocking the Stage 3 gate at commit time. Both ARC 020 sub-agents hit it
independently and solved it separately. If it has not been fixed, fix it once at dispatch rather than
letting each agent rediscover it.

**Verify each worktree's base explicitly** — in ARC 019 all three were provisioned from `main`
rather than session HEAD.

**Contention, parent-owned, serialized in Phase 4:** `checks/registry.json` · `broker_seam.py` if B
needs to read a moving roster · the final full-tree run.

---

## 4. SUB-AGENT A — the datafeed adapter

### A1. The port, derived from the spec — not from memory

Derive the `BrokerDatafeedPort` surface from §2A directly. ARC 019 established the counting is
subtle: §2A's bullets and its identifiers disagree, broker-order is 16 by identifier, and the code
declares one flagged Nix addition (`feed_lag()`) beyond the spec roster.

**Derive the datafeed roster the same way and state both counts.** Register the result as a claim if
B agrees it belongs in the registry. Do not carry any number forward from a brief, including this one.

`broker_seam.py` already declares `BrokerDatafeedPort` and `DATAFEED_PORT_VERBS`. **Read what is
there before writing** — the seam is ahead of every architect copy.

### A2. `FeedLag` — a first-class property, not a comment

**This is the design decision the whole arc turns on.**

At Stage 0, wall-clock and data-clock are approximately **600 seconds apart** (ARC 010 measured
600.3 s, spread 1.9 s, n=8 — not the documented 15–20 minutes). Tradovate and DataBento set it to 0.

Any session-gating, staleness, or bar-boundary logic written against wall-clock **will misbehave in
ways that look like bugs** unless the interface carries the lag explicitly. A consumer asking "is
this tick fresh?" gets a different and correct answer once the lag is declared.

`feed_lag()` already exists on the seam as a flagged addition. **Make it load-bearing:**
- Every emitted tick or bar carries enough for a consumer to compute both wall-age and data-age
  without knowing the vendor
- The declared lag is **observed, not configured** where it can be observed, and where it is
  configured, the configured value is validated against observation and a divergence is a finding
- A consumer must not be able to compute freshness *correctly by accident* — if the lag is zero on
  Tradovate and 600 s here, the same consumer code must give the right answer on both

**If `TAP_SESSION.md` carries a re-measured lag, use it and say so.** If it does not, use ARC 010's
figure, mark it as a value from a prior arc, and register the re-measurement as owed.

### A3. What Stage 0 forbids — encode it, do not just document it

- **No real-time stream exists.** `reqTickByTickData` returns `Err 10189`, "No market data
  permissions for **CME FUT**" — it names the *product class*, so no instrument choice reaches it
- **`reqHistoricalTicks` is delayed by the same ~10 minutes.** It is not a real-time back door, and
  it will look like one
- **Delayed streaming works** via `reqMarketDataType(3)` + `reqMktData`
- **The poll fallback is the only margin path** — §2A's push path does not exist on IBKR
  (`capabilities.pushes_margin=False`) and stays untested until Tradovate

Declare these through `BrokerCapabilities` the way broker-order declares its four GAPs: **coverage
differences are declared above the seam, never silently degraded.** A capability that is absent must
be *stated as absent*, and a consumer must not be able to call a path that does not exist and get
silence.

### A4. The absence principle — the third pending amendment

**Operator ruling, ratified. Record verbatim in `docs/SPEC-AMENDMENTS.md`:**

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

**Apply it in this adapter throughout.** A missing tick field, an unreported bar, an absent
timestamp: each is declared, never defaulted. Where you find a place the principle is expensive to
honour, say so — the ruling is ratified but its cost has not been measured.

### A5. D1.14 — bar immutability on a re-requestable feed

Polled history **can return revised values**. A bar builder that rewrites a bar it already published
makes every downstream consumer's history unreproducible, and the revision arrives looking exactly
like new data.

Implement seal-and-never-rewrite: once a bar is published it is immutable. A later poll returning a
different value for a sealed bar is a **declared event**, not a silent overwrite — the consumer must
be able to learn that the venue's story changed.

**Prove it:** publish a bar, poll again with a revised value, assert the published bar is unchanged
and that the revision is observable. **Non-vacuity:** assert the revision genuinely differed —
a test where the second poll returns identical data proves nothing.

### A6. Tier 1 and Tier 2

Per `debug.md` §5. Tier 1: does it work on the paths it was designed for. Tier 2: the static gates.
**Tier 3 is ARC 022** (prohibition 6).

Include the multi-writer field rule from ARC 020 A8: **any field written by more than one event
handler has its meaning asserted per writer.** `avg_price` carried two meanings twice in
broker-order; a fresh module is the cheap moment to prevent the third.

---

## 5. SUB-AGENT B — the two gates that have waited for a datafeed to exist

### B1. D1.13 — granted `marketDataType`, not requested

**The defect this closes, stated precisely:** IBKR **silently downgrades** — mode 4 requested, mode 3
granted, no error. And `ib_async`'s `Ticker.marketDataType` **defaults to 1**, so an unset field is
indistinguishable from a genuine real-time grant. Sentinel it to 0 after subscribing. **Never infer
the mode from the request.**

Build a gate asserting the **granted** mode matches the **declared** one, failing on a silent
downgrade.

- **Prove real effective state**, never a proxy. That the request was made is not evidence of what
  was granted — that is the entire defect
- **Non-vacuity:** assert the subscription genuinely reported a mode, and that the sentinel
  distinguishes "unset" from "granted 1". A gate that cannot tell those apart reproduces the defect
  it exists to catch
- **Can-fail:** plant a declared mode that does not match the grant → FAIL naming the site → unplant
  → pass. Four outputs, `__pycache__` purged
- **§7.12 answered in writing beside the gate**
- **If no live session:** the gate is built and its can-fail proven against a fake; the *live*
  confirmation is a known-red naming the next tap. If `TAP_SESSION.md` carries the observation, use
  it and say so

### B2. D1.14 — the bar-immutability gate

A2 and A5 build the behaviour; this gate proves it holds and keeps holding.

Same requirements: exit contract 0/1/2, effective state, scope derived from the tree rather than a
snapshotted list, non-vacuity before the plant, can-fail naming the site, fails closed, §7.12
answered.

**Extend an existing gate if one already owns an adjacent property** (check-rule 8). Check before
building.

### B3. Claims

Register what this arc makes derivable. Candidates: the datafeed element roster, the declared feed
lag versus its observed value, the datafeed's open-debt-row count as a depth figure paralleling
broker-order's.

**The depth figure is a floor, never a fraction** — ARC 020's framing, and the reason is unchanged:
its denominator would be "how much do we trust this module", which is unknowable.

### B4. Then stop.

No eleventh, twelfth or thirteenth gate. A good idea is a debt row.

---

## 6. PHASE 4 — integration and verification

1. Merge worktrees; verify bases
2. Register gates and claims
3. **Check whether adding a datafeed file reddened `check_order_path_bans`.** If it did, that is
   prohibition 3's case: repair the scope boundary, never the ban, and report it
4. Reconcile B's ledger edits against `check_derived_claims`; the harness owns the count. Watch for
   ARC 020's D1.30/D1.31 shape — new rows invisible to the depth claim because the scoping rule reads
   prose and the row named no module basename on a word boundary
5. Confirm no plants; `__pycache__` purged; `core.bare != true`; `git fsck` clean
6. Run:

```bash
cd ~/nix
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
.venv/bin/python checks/check_spec_citations.py; echo "spec_citations exit=$?"
```

All five raw. **Derive every count against no stated expectation.**

7. Clean temp files per `CLAUDE.md`
8. Commit, PR, **merge, confirm on `origin/main`**

---

## 7. PHASE 5 — live measurement (OPTIONAL)

**If `TAP_SESSION.md` already carries the granted-mode observation and a re-measured lag, this phase
is largely discharged** — cite it rather than re-running it, and say which figures came from there.

If a live session exists and none of it was captured:
- `reqMarketDataType(3)` + `reqMktData` on MESU6 (conId 793356217), clientId 905 — report requested
  versus granted, with the sentinel applied
- Also request mode 1 so the downgrade is **observed** rather than assumed
- A handful of lag samples against wall clock

**Decline near the 16:00 CT close** — ARC 017's precedent stands.

**If no session:** known-red markers naming the next tap. RED withholds certification, not durability.

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.** Say so in `RESULTS.md` in those words.

---

## 8. Write-back gate

1. Append this arc's summary to `~/nix/sessions/SESSION.md`
2. Series row in **`docs/CHECK-DEBT.md`**
3. **Overwrite** `~/nix/downloads/RESULTS.md`
4. `cat` both, paste their state
5. Coverage figures for broker-order and broker-datafeed, **level and delta distinguishable**, naming
   what each derives from. Broker-order's element coverage is expected not to move — this arc does
   not touch it
6. Only then `**** ARC completed ****`

---

## 9. Success criteria

**Sub-agent A**
- [ ] Datafeed roster derived from §2A directly; both bullet and identifier counts stated
- [ ] **No object shared with broker-order**; any proposed extraction argued and refused, or stopped and escalated
- [ ] `FeedLag` load-bearing: wall-age and data-age both computable by a vendor-blind consumer
- [ ] Configured lag validated against observation where observable; divergence is a finding
- [ ] Stage 0's three absences encoded through `BrokerCapabilities`, not documented only
- [ ] Absence principle applied throughout; places where it is expensive reported
- [ ] Bar seal-and-never-rewrite implemented; revision observable; non-vacuity proven
- [ ] Multi-writer fields asserted per writer
- [ ] Tier 1 and Tier 2 complete; **no Tier-3 attempted**
- [ ] Datafeed clientId decided and stated, not defaulted

**Sub-agent B**
- [ ] D1.13 gate proves **granted** mode, sentinel distinguishing unset from granted-1
- [ ] D1.14 gate built or an existing gate extended, with the check-rule-8 decision stated
- [ ] Both: non-vacuity, can-fail with four outputs, §7.12 answered, `__pycache__` purged
- [ ] Claims registered; depth figure framed as a floor, not a fraction
- [ ] Nothing built beyond B1–B3

**Integration**
- [ ] Third amendment recorded verbatim, attributed as an ARC 021 operator ruling
- [ ] `check_order_path_bans` scope question resolved at the boundary if it reddened
- [ ] pytest count derived, delta explained; pre-commit clean
- [ ] `verify.py`: **exit 0 if a tap session restored the Gateway; otherwise exit 1 with
      `check_ibgateway_service` / `check_ibgateway_config` as the only failures and that cause named.**
      Any third failure is a real finding
- [ ] Harness/ledger reconciled, harness winning
- [ ] No plants; merged and confirmed on `origin/main`
- [ ] Write-back gate satisfied

**Explicitly NOT in this arc:** Tier-3 on broker-datafeed (**ARC 022**) · §13 objective 24, the
kill-the-datafeed-under-load drill (**R1-D**, needs both libraries stable first) · the Limiter and
every consumer · `capture.py` process wiring, ZMQ, the shared-memory ring (**R1-C**) · D1.22's
bounding policy · D1.19 · D1.20's consumer half · a v1.4 of the frozen spec.

**Apply §0a to this brief.** ARC 019 found a direct contradiction with the frozen spec in mine; ARC
020 found two places where my brief contradicted itself. Report what you find rather than reconciling
it.

Report deviations rather than substituting. A named gap is worth more than a green claim.
