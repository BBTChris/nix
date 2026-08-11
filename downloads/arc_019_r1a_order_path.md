# ARC 019 — R1-A: Send-Path Behaviour Under Stress · Partial Fills · Reconnect · Tier-3
### Mega arc · 3 parallel sub-agents · the first predominantly-product arc since ARC 015

===RUN SUMMARY: ARC 019 — Send-Path Behaviour Under Stress; Partial Fills; Reconnect; Tier-3 Traversal, Estimated run time: 4–5 h, completes ~10-12% of the current stage (measures whether the sync send path actually blocks under a stalled socket rather than assuming it does not, closes the partial-fill and remainder-cancel path, stops _mirror_stale latching across a good reconnect, and runs the first Tier-3 traversal against broker-order — plus two apparatus riders earned by ARC 018: a citation-integrity claim and proof the hook suite is installed and intact)===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract
- `~/nix/docs/debug.md` **v1.2.0** — three tiers; **§5 Tier-3** is sub-agent B's spine; **§7.12** applies to every gate
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A, §4, §13
- `~/nix/docs/CHECK-DEBT.md` — D1.10, D1.12, D1.19, D1.20 are this arc's subjects

Authority order per `CLAUDE.md`. **Verified on-disk state outranks this document.**

### 0a. Every §-citation in this brief is suspect. Verify before relying on any of them.

ARC 018 established that **§2.1 does not exist** — it originated in the ARC 017 *brief*, then
propagated into the CHECK-DEBT D2.14 row and into a gate's own docstring. Architect prose acquired
spec authority by repetition. ARC 018 also established that **the numbered invariants 1–5 are at
§2A:103–108, not §14** — §14 exists, is unnumbered, and holds different content, so every prior
brief's "invariant N per §14" pointed at the wrong section.

The citations below have been corrected against ARC 018's verified anchors, but they are still
architect-authored and still unverified by you:

- never auto-resend — **§2A:71**, **§4:241**, **§12A:830**
- retry/backoff **mandated outside** the order path (pollers) — **§12A:827**, **§6.4:374**, **§13:900**
- numbered invariants — **§2A:103–108**
- V9, V11, V24 — **§13**

**Check each one before you rely on it. If a citation does not resolve, say so and name where it
came from.** Sub-agent C is building the gate that makes this check permanent; until it exists,
do it by hand.

### 0b. Baseline — confirm, do not assume

This brief states **no expected end-state values**. Confirm the start and report deviations:

```bash
cd ~/nix
git rev-parse --short HEAD
git status --porcelain
gh pr list --state open
git merge-base --is-ancestor HEAD main && echo "HEAD is on main" || echo "HEAD NOT on main"
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
```

ARC 018 reported: verify 8/exit 0, pytest 180, pre-commit 8/8, claims 9/9, debt 29, per-hook
can-fail 8/8. **Those are its reported values, not this arc's targets.**

**Check the merge state explicitly.** ARC 017's PR #11 was open, not merged, when ARC 018's brief
asserted it had landed — the ARC 013 stranding shape recurring. ARC 018 was based on ARC 017's tip,
so landing it should have resolved both. Confirm that it did.

`python` is not on PATH; `verify.py` is at `scripts/verify.py`.

---

## 1. Why this arc, and what changes about it

ARCs 016, 017 and 018 were predominantly apparatus. Each was the right call — bandit scanning
nothing, a live phantom-fill window, a runtime gate green over zero tests. The apparatus is now
genuinely good: 8 of 8 hooks demonstrated able to fail, 9 registered claims, a runtime gate that
reports its own scope.

**Broker-order is at 56% of one module of six, and the last arc moved the project ~3 points.** The
streak stops here. This arc is product work with two small apparatus riders, both earned by
findings ARC 018 made rather than invented for their own sake.

**The riders do not grow.** If sub-agent C finishes early, it stops. Apparatus expansion beyond
C1 and C2 is out of scope, and a good idea for a ninth gate is a debt row, not a task.

---

## 2. Hard prohibitions

1. **No retry/backoff on the order path.** No `tenacity`, `backoff`, `retrying`, or hand-rolled
   retry loop in the order-path scope. Pending timeouts resolve via `query_order_status`; the
   system **never auto-resends**. Note the boundary is one directory wide — retry is *mandated*
   for pollers outside the order path, so if a gate reddens spec-mandated behaviour the repair is
   to the scope boundary, never to the ban.
2. **No `asyncio.run`, `run_until_complete`, `run_forever`, or blocking wait on the sync send path.**
3. **`clientId=0` permanently excluded.** Diagnostics use **905**; **1** reserved for the Risk Engine.
4. **Do not un-ignore `state/`** (D1.16 — pairs with the deferred Fernet→TPM2 arc).
5. **Do not "fix" D1.17.** Limiter-side edge-versus-level decision.
6. **No hand-typed numbers in `RESULTS.md`.**
7. **Purge `__pycache__` between every plant/unplant step.** ARC 018 reproduced the hazard
   empirically and bounded it: stale bytecode survives when a plant preserves **both** byte size
   **and** integer-second mtime. A pure line swap does exactly that.
8. **No plant survives the arc.**
9. **Do not build a mechanism this arc does not prove is needed.** See §4.1 — measure first.

---

## 3. Sub-agent dispatch — disjoint file sets

| agent | owns (write) | may read | forbidden |
|---|---|---|---|
| **A** | `scripts/broker/**`, `scripts/tests/test_broker_order.py` | all | `checks/**`, `scripts/tests/test_broker_tier3.py`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |
| **B** | `scripts/tests/test_broker_tier3.py` (new) | all | `scripts/broker/**`, `checks/**`, `test_broker_order.py` |
| **C** | `checks/**`, `checks/derived_claims.json`, `docs/CHECK-DEBT.md` | all | `scripts/broker/**`, `scripts/tests/**`, `.pre-commit-config.yaml` |

**Sub-agent B writes no production code.** Tier-3 is a *discovery* activity: its output is a durable
traversal suite plus a findings list. Fixes are triaged in Phase 4 — trivial ones applied by the
parent, non-trivial ones opened as debt rows naming ARC 020. **B does not reach into
`scripts/broker/` to fix what it finds**, and a finding B cannot fix is still a successful outcome.

ARC 018 established that a concurrent cross-set write made pre-commit attribute a modification to a
hook that never writes files. Cross-set writes corrupt evidence, not just state.

**Contention, parent-owned, serialized in Phase 4:** `checks/registry.json` · the final full-tree
run · triage of B's findings.

---

## 4. SUB-AGENT A — send-path behaviour, partial fills, reconnect

### A1 (PRIMARY). Does the send path actually block? Measure before building anything.

**Read this before scoping.** Prior briefs have assumed a sender thread is needed. That assumption
has never been measured, and prohibition 9 forbids building a mechanism this arc does not prove is
needed. `ib.placeOrder()` returns a `Trade` immediately in the happy path — the open question is
what it does when the socket is stalled, slow, or the peer has gone away without a FIN.

**Measure first, on all four sync send verbs** — `place_order`, `cancel_order`, `flatten`,
`disconnect`:

- Wall-clock time to return, under (i) a healthy fake socket, (ii) a socket that accepts but never
  responds, (iii) a socket whose writes block on a full send buffer, (iv) a peer that vanished
- Report the measured numbers. Do not round, and do not describe them as "fast" — paste them

**Then decide, and justify the decision from the measurements:**
- If the verbs return promptly under all four conditions, **build nothing.** Record the measurement
  as the evidence and say so plainly
- If any verb blocks, the fix is a queue or a sender thread — build the minimum that resolves the
  measured block, not the general mechanism

**`flatten` deserves specific attention** regardless of outcome. Its per-symbol fan-out is a loop
(the single reviewed hit in ARC 018's D2.14 scan), so a per-call block multiplies by symbol count on
the **protective path** — the one that is supposed to have zero wire dependency and was validated at
0.6 ms against the mirror. A 0.6 ms mirror read in front of an N-times-blocking send is not a
protective path.

**This does not discharge V11.** V11 asks whether the stop loop keeps protecting while the send path
is stalled, and there is no stop loop until R2. State the known-red marker naming R2 explicitly, and
describe what you measured as what it is: send-verb behaviour under socket stress, against a declared
stand-in, not V11.

### A2. V9 — partial fill and remainder cancel

Currently untested. Drive through `FakeIB`:

- An order that fills partially, then fills again, then completes — assert fills accumulate without
  double-counting and the mirror lands on the correct net position and average price
- A partial fill followed by `cancel_order` on the remainder — assert `on_cancel` carries the
  **unfilled** quantity, that the filled portion stays in the mirror, and that the cancel does not
  reverse or discard it
- A partial fill followed by the venue cancelling the remainder itself
- **The ack-ordering invariant holds throughout**: exactly one `on_ack` per `client_order_id`,
  always preceding the first `on_fill`, no matter how the fills arrive

**Non-vacuity before any can-fail:** prove the partial-fill path is actually driven — a suite that
only ever sees complete fills demonstrates nothing about partials. Assert on the observed fill
sequence, not just the end state.

**Can-fail:** plant a defect that double-counts a partial (or discards the filled portion on cancel)
→ the suite must FAIL and name the site → unplant → pass. All four outputs, `__pycache__` purged
between.

**`FakeIB` fidelity:** ARC 015 established that a fake which cannot represent a defect class is debt,
not coverage. Before writing assertions, confirm `FakeIB` can represent a partial fill at all —
cumulative quantity, remaining quantity, and per-execution price. If it cannot, extending it is part
of this task.

### A3. D1.20 — `_mirror_stale` latches across a good reconnect

`connect()` discards `_rebuild_mirror()`'s verdict, so a mirror read that failed once stays `True`
even after a reconnect that rebuilt successfully. It fails toward "suspect", which is the safe
direction — but it is a one-way door: a consumer gating entries on it would never resume trading.

**Fix the adapter half now**, because it is adapter-internal correctness and does not require the
consumer to exist: `connect()` honours the rebuild verdict, so a successful rebuild clears the flag
and a failed one does not.

**Do not build the consumer.** D1.20's consumer-side obligation stays open and stays named. Record
what a consumer will be required to do, written now while the reasoning is fresh.

**Prove it:** populate the mirror, force a rebuild failure, assert `_mirror_stale` is `True`;
reconnect with a rebuild that succeeds, assert it clears. **Non-vacuity:** assert the flag was
genuinely `True` before the clearing reconnect, so "cleared" is not `False`→`False`.

### A4. Reconnect and re-subscribe

The probe in ARC 017 asked what happens on session drop and reconnect and the answer was partial.
Close it:

- Are subscriptions re-established, or silently lost?
- Does the position mirror re-reconcile on a plain reconnect (not just the 1101 data-loss path ARC
  017 built)?
- ARC 017 proved the startup gate re-arms on reconnect. Confirm that still holds after A1 and A3
- Is there any path where the adapter reports `UP` over a mirror it did not rebuild?

Fix what is adapter-internal. Anything requiring a consumer becomes a debt row naming R2.

---

## 5. SUB-AGENT B — Tier-3 traversal against broker-order

**This is the first Tier-3 run on real Nix application code.** `debug.md` §5 is the authority — read
it directly. Tier-3 asks whether the module is *good*, not whether it is *not visibly broken*, and
its subject is the sequences nobody designs for: the same operation twice, interleaved operations,
a retry after partial failure, a caller that abandons midway.

**You write no production code.** Output is `scripts/tests/test_broker_tier3.py` plus a findings
list. A finding you cannot fix is a successful outcome; a finding you fix by reaching into
`scripts/broker/` is a scope violation.

### B1. The traversal set

At minimum, drive each of these through the public seam against `FakeIB`:

| sequence | what it probes |
|---|---|
| `flatten()` called twice concurrently | the protective path against itself |
| `flatten()` while a fill for the same symbol is arriving | mirror mutation racing the read |
| `cancel_order()` on an order that filled microseconds earlier | ARC 015's collapsed-transition race, from the cancel side |
| `place_order()` immediately followed by `disconnect()` | teardown with work in flight |
| `disconnect()` during an in-flight `place_order()` | the same, inverted |
| a `query_positions()` await that is cancelled mid-flight | caller abandons midway — asyncio task cancellation |
| `flatten()` during a reconnect | protective path over an unrebuilt mirror |
| the same `client_order_id` reused after a completed order | identity reuse |
| two `place_order()` calls interleaved with a fill for the first | ack/fill ordering under interleaving |

Extend the set where your reading of the code suggests a sharper sequence. **Say which sequences you
added and why** — the judgment about what to probe is the valuable part, not the count.

### B2. Rules for the suite

- **Non-vacuity is mandatory per sequence.** A traversal test that passes because the sequence never
  actually interleaved has demonstrated nothing. Assert on observed ordering, not just end state.
  This is the exact class §7.12 asks about
- **Assert the invariant, not a snapshot.** Every sequence resolves toward a state that is *known*,
  and uncertainty resolves toward flat. Do not encode a specific expected sequence of events that a
  legitimate refactor would break
- **Distinguish "wrong" from "undefined".** Some of these have no specified correct behaviour yet.
  A sequence whose correct outcome the spec does not determine is a **spec finding**, not a code
  defect — report it that way and name the section that would need to say
- Controls: if you add a control (a deliberately broken driver), it must fail for the reason you
  intend and not for a shape reason. ARC 018's Hollow control was asserted structurally *and*
  behaviourally for exactly this reason

### B3. Findings report

For each finding: the sequence, the observed behaviour, whether it is a **code defect**, a **spec
gap**, or **working as intended but surprising**, and your recommended disposition. Triage happens
in Phase 4; your job is to find and characterise, not to decide what ships.

---

## 6. SUB-AGENT C — two riders, and then stop

### C1. Citation integrity — the class ARC 018 found

**The failure:** `§2.1` was authored in a task brief, cited as though it were the frozen spec,
and propagated into the CHECK-DEBT ledger and a gate's docstring. Architect prose acquired spec
authority through repetition. Separately, "invariant N per §14" pointed at the wrong section across
at least three briefs. Both are mechanically checkable and neither was caught by any gate.

Add a claim (or a gate — your call, argued) that **every `§`-citation of the frozen specs resolves
to a real heading in the cited document.**

- **Scope:** at minimum `docs/CHECK-DEBT.md`, `checks/**` docstrings, and `scripts/broker/**`
  comments. State what you covered and what you did not
- **Derive both sides.** The set of real headings comes from parsing the spec; the set of citations
  comes from scanning the tree. Neither is a hand-maintained list
- **Line-number citations** (`§2A:71`) are a distinct problem — a line number is failure mode #4 and
  will drift. Decide whether to verify the section only, or the section plus a content anchor, and
  argue the choice
- **Non-vacuity:** assert the citation set found is non-empty and contains at least one known-good
  citation. A scanner finding zero citations passes beautifully
- **Can-fail:** plant `§99.9` → FAIL naming file, line, and the unresolvable citation → unplant →
  pass
- **§7.12 answered in writing beside it**

### C2. D1.10 — is the hook suite installed, and is its hook set intact?

All 8 hooks are now demonstrated able to fail. **Nothing asserts they are wired in.** An uninstalled
`pre-commit`, a hook silently dropped from the config, or a `.git/hooks/pre-commit` that was
overwritten all produce a clean commit history with no gate having run — the last standing shape of
"green while measuring nothing."

The gate must prove **effective** state, not declared: the hook is installed at the git level, the
configured hook set matches what actually runs, and no hook has been silently dropped.

- **Derive the expected hook set from the config**, never a snapshot list — a hook added later must
  be covered automatically
- **Non-vacuity** before any plant
- **Can-fail:** remove a hook from the config, or uninstall the git hook → FAIL naming what is
  missing → restore → pass
- **Fold in the cached bandit finding.** ARC 018 classified the pre-ARC-010 bandit environment as
  *owed, not acceptable standing risk*, recorded under D1.10 — rev `2d0b675` still reports
  `Files skipped (20)` / exit 0 while 1.9.4 catches the same plant. Decide whether this gate can
  detect a routed-around environment, or whether that needs its own row. Either answer is fine;
  silence is not

### C3. Then stop.

Apparatus expansion beyond C1 and C2 is out of scope (§1). A good idea for a ninth gate is a debt
row, not a task.

---

## 7. PHASE 4 — serialization, triage, verification

Parent-owned.

1. Merge worktrees; resolve collisions explicitly
2. Register new gates in `checks/registry.json`
3. **Triage sub-agent B's findings.** Trivial fixes applied here; non-trivial ones become debt rows
   naming ARC 020. **Do not batch-fix under time pressure** — a rushed fix to a concurrency defect
   found by traversal is how the traversal's value is destroyed
4. **Reconcile C's ledger edits against `check_derived_claims`.** The harness owns the count. ARC 018
   found the harness was not implementing its own documented rule — naive `"discharged" in line`
   against a documented bold-span regex — so verify the harness is still reading rows the way
   `CHECK-DEBT`'s own note says it must
5. Confirm no plants remain: `git status --porcelain`, `scratch/` absent, sha256 spot-checks,
   `__pycache__` purged
6. Run:

```bash
cd ~/nix
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
```

All four raw. **Derive every count against no stated expectation.**

7. Clean up temp files per `CLAUDE.md`
8. Commit, PR, **merge — and confirm the merge landed on `main`.** Two arcs in a row have had a
   predecessor stranded on a branch. Push the moment commits exist

---

## 8. PHASE 5 — the tap bundle (OPTIONAL, and worth asking for)

Three things are blocked on the same IB Key tap. **This is the one place in this arc where asking
for a tap is justified**, because the marginal cost of the second and third discharge is zero.

**If the operator grants a session, run in this order:**

1. **D1.12 — the reboot test, first.** Reboot, then run `check_ibgateway_service` **before anyone
   touches the console.** `systemctl is-enabled` is a declaration, not evidence. If the console is
   touched first, the test proves nothing and the tap is wasted on it
2. **The rejection-taxonomy confirmation** owed from ARC 018: on `clientId=905`, an unaffordable-size
   order returning `reject_category=INSUFFICIENT_MARGIN` with `reason` still carrying `201: …MARGIN
   REQ […]`. Both halves in one observation — structured fact populated, human channel intact — and
   it re-validates the text anchor against IBKR's current wording, which offline tests cannot do
3. **Anything A1 measured offline** that a real socket can corroborate

**Decline near the 16:00 CT close.** ARC 017 declined at 15:59 CDT because evidence taken at a
session boundary is ambiguous; that precedent stands.

**If no session is granted:** known-red markers naming R1-A for the taxonomy and D1.12 for the
reboot. RED withholds certification, not durability.

Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or strategy
performance — the feed is delayed ~600 s. Say so in `RESULTS.md` in those words.

---

## 9. Write-back gate — completion is never claimed without this

1. Append this arc's summary to the end of `~/nix/sessions/SESSION.md`
2. Add the series row to **`docs/CHECK-DEBT.md`**, where the series table lives
3. **Overwrite** (not append) `~/nix/downloads/RESULTS.md`
4. `cat` both and paste their resulting state into the response
5. State percent moved for **broker-order**, **apparatus**, and **whole project**, using the
   registered `sec2a-element-v1` scheme where it applies and naming what each figure derives from.
   Note that ARC 018 established `~13%` and `56%` are a **delta and a level**, not two versions of
   one number — keep them distinguishable
6. Only then print `**** ARC completed ****`

---

## 10. Success criteria — all, or no completion claim

**Sub-agent A (primary)**
- [ ] All four sync send verbs measured under four socket conditions; numbers pasted, not characterised
- [ ] Build-or-don't-build decision made **from the measurements** and justified; nothing built that the measurements did not require
- [ ] `flatten`'s fan-out specifically assessed against the protective-path guarantee
- [ ] V11 known-red marker naming R2, with what was measured described as what it is
- [ ] V9: accumulating partials, remainder cancel carrying unfilled quantity, venue-side remainder cancel
- [ ] Ack-ordering invariant holds across every partial-fill sequence
- [ ] `FakeIB` confirmed able to represent partial fills; extended if not
- [ ] Non-vacuity proven; can-fail demonstrated, four outputs, `__pycache__` purged
- [ ] `connect()` honours the rebuild verdict; `_mirror_stale` clears on a good reconnect; non-vacuity proven
- [ ] Consumer-side D1.20 obligation recorded, not built
- [ ] Reconnect/re-subscribe answered on all four questions; adapter-internal fixes applied, consumer-dependent ones opened as debt

**Sub-agent B**
- [ ] `test_broker_tier3.py` covering at least the nine tabled sequences, plus any added with reasoning stated
- [ ] Non-vacuity per sequence — observed ordering asserted, not just end state
- [ ] Findings classified code defect / spec gap / working-as-intended-but-surprising, with recommended disposition
- [ ] No writes into `scripts/broker/`

**Sub-agent C**
- [ ] Citation-integrity claim or gate built; both sides derived; line-number question argued
- [ ] Non-vacuity proven; can-fail on a planted `§99.9`; §7.12 answered beside it
- [ ] D1.10: installed-and-intact proven from effective state; hook set derived from config
- [ ] Non-vacuity + can-fail; cached-bandit-environment question answered either way
- [ ] Nothing built beyond C1 and C2

**Integration**
- [ ] Gates registered; verify exit 0; every count derived against no stated expectation
- [ ] pytest delta explained
- [ ] pre-commit clean, with a statement of which hooks self-report scope and which still cannot
- [ ] B's findings triaged, not batch-fixed
- [ ] Harness still reading `CHECK-DEBT` rows the way its own note says it must
- [ ] No plants; `__pycache__` purged; temp files cleaned; pushed **and confirmed on `main`**
- [ ] Every number in `RESULTS.md` traceable to a pasted command
- [ ] Write-back gate satisfied, series row in `CHECK-DEBT.md`

**Explicitly NOT in this arc:** D1.16 (`state/` — Fernet→TPM2 arc), D1.17 (Limiter-side),
D1.19 (`AckProvenance` — discharges with the Limiter), D2.14 residuals (recursion, indirection past
one hop, cross-thread), D2.15 call-site derivation (needs the Limiter, and multiplies the
false-positive surface by its size), V11 (needs a stop loop → R2), V24 (needs broker-datafeed → R1-D).

**Apply §0a to this brief.** ARC 017 found six defects in its predecessor; ARC 018 found ten,
including a spec citation that never existed and a percentage that existed nowhere on disk. Report
what you find rather than reconciling it.

Report deviations rather than substituting. A named gap is worth more than a green claim.
