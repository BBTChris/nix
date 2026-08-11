# ARC 020 — Closing the Five: Session Lifecycle, Mirror Ordering, Protective-Path Observability
### 2 sub-agents (deliberately not 3) · the arc that clears R2's landmines

===RUN SUMMARY: ARC 020 — Closing the Five; Session Lifecycle; Mirror Ordering; Protective-Path Observability, Estimated run time: 5–6 h, completes ~12-14% of the current stage (closes the five live adapter defects ARC 019's traversal held open as strict xfails, lands two operator-ratified behavioural rulings as declared additions, makes the protective path able to report that it failed, and renames the coverage scheme so breadth stops reading as completeness — note element coverage will not move: this arc adds no §2A elements, it repairs existing ones, which is exactly the scheme limitation §10 of ARC 019 raised)===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract
- `~/nix/docs/debug.md` v1.2.0 — **§5 Tier-3**, **§7.12**, **§7.4** (stale anchors)
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A, §4, §5, §13
- `~/nix/docs/CHECK-DEBT.md` — D1.22 through D1.28, D2.17, D3.7, D3.8

Authority order per `CLAUDE.md`. **Verified on-disk state outranks this document.**

### 0a. Citations, and a notation correction

`check_spec_citations.py` now exists, so this brief's `§`-references will be checked
mechanically. Two things it cannot catch, both mine:

1. **`V9` / `V11` / `V27` are architect shorthand, not spec spelling.** §13 numbers objectives
   1–23 plainly and only adopts a `V` prefix at V24. All three ARC 019 sub-agents found this
   independently. This brief writes **"§13 objective N"** for 1–23. Existing ledger rows keep
   their spelling; do not mass-rewrite them in this arc.
2. **ARC 018's §2.1 correction was itself slightly wrong**, per ARC 019: the gate text said
   *"banned by ARC 017 §2.1"* and named the brief honestly. The unattributed citation was in the
   CHECK-DEBT row. **The defect was missing attribution, not a wrong document** — which is why
   D2.17 (unattributed citations remaining advisory) is the residual that matters.

### 0b. Baseline — confirm, do not assume

This brief states **no expected end-state values**.

```bash
cd ~/nix
git rev-parse --short HEAD
git status --porcelain
git merge-base --is-ancestor HEAD main && echo "HEAD on main" || echo "HEAD NOT on main"
gh pr list --state open
git config --get core.bare
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
.venv/bin/python checks/check_spec_citations.py; echo "spec_citations exit=$?"
```

ARC 019 reported: verify 10/exit 0, 233 passed + 5 xfailed, pre-commit 8/8, claims 9/9, debt 41
rows, ARCs 017/018/019 all ancestors of `main`. **Reported values, not targets.**

Three environment checks are deliberate. `core.bare` was set to `true` mid-ARC-019 by a test
fixture running `git init` inside a hook environment, because **git exports `GIT_DIR` and
`GIT_INDEX_FILE` into hooks where they outrank `cwd`**. Confirm it is unset. The merge check is
because `main` required an approving review no sole maintainer could give — every arc PR was
structurally unmergeable and three stranded before ARC 019 diagnosed it. Confirm the setting held.

**If you dispatch sub-agents into worktrees, verify each worktree's base explicitly.** In ARC 019
all three were provisioned from `main` rather than session HEAD; all three caught it independently,
but none was told to look.

---

## 1. Why two sub-agents and not three

Every one of the five defects lives in `scripts/broker/broker_order_ibkr.py`. Splitting them across
parallel agents means two branches editing one ~1,200-line file and merging the result — and a
botched merge in the order path is precisely the wrong place to save an hour.

**Sub-agent A works serially through the adapter. Sub-agent C runs in parallel on `checks/`, which
is genuinely disjoint.** If you judge a further split is safe, argue it; do not assume it.

The dependency order inside A is load-bearing and stated in §4. **D1.24 must land before the gate
ownership change**, because ownership is only a sound discriminator once per-order state is cleared
at the session boundary.

---

## 2. Hard prohibitions

1. **Do not edit the frozen specs.** §2A and §4 stay untouched. The two rulings in §5 are landed as
   **declared Nix additions** following the `feed_lag()` / `UP_DATA_LOSS` precedent, plus a recorded
   pending-amendment entry. A v1.4 of the frozen spec is an architect action, not this arc's.
2. **No retry/backoff on the order path.** Pending timeouts resolve via `query_order_status`; the
   system **never auto-resends** (§2A:71, §4:241, §12A:830 — all verified on disk in ARC 019). The
   boundary is one directory wide; retry is *mandated* for pollers outside it (§12A:827, §6.4:374,
   §13:900), so a gate reddening spec-mandated behaviour is repaired at the scope boundary, never at
   the ban.
3. **No `asyncio.run`, `run_until_complete`, `run_forever`, or blocking wait on the sync send path.**
4. **`clientId=0` permanently excluded.** Diagnostics **905**; **1** reserved for the Risk Engine.
5. **Do not build the Limiter, or any consumer.** Several fixes here create observable state whose
   consumer is R2's. Build the state, record the obligation, stop.
6. **Do not un-ignore `state/`** (D1.16). **Do not "fix" D1.17.**
7. **No hand-typed numbers in `RESULTS.md`.**
8. **Purge `__pycache__` between every plant/unplant step.** ARC 018 bounded the hazard: stale
   bytecode survives when a plant preserves both byte size and integer-second mtime. ARC 019's V9
   plant hit exactly that shape — 71450 bytes both times.
9. **Removing a `strict=True` xfail happens in the same motion as the fix it marks.** A repair that
   leaves the marker reddens the suite; that is the design.
10. **No plant survives the arc.**

---

## 3. Sub-agent dispatch

| agent | owns (write) | may read | forbidden |
|---|---|---|---|
| **A** | `scripts/broker/**`, `scripts/tests/test_broker_order.py`, `scripts/tests/test_broker_tier3.py` | all | `checks/**`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |
| **C** | `checks/**`, `checks/derived_claims.json`, `docs/CHECK-DEBT.md` | all | `scripts/broker/**`, `scripts/tests/**`, `.pre-commit-config.yaml` |

**Contention, parent-owned, serialized in Phase 4:** `checks/registry.json` · the final full-tree
run · reconciling A's ledger implications against C's harness output.

A cross-set write corrupts evidence, not just state — ARC 018 saw pre-commit attribute a
modification to a hook that never writes files.

---

## 4. SUB-AGENT A — the five, in dependency order

Work them in this sequence. It is not arbitrary.

### A1. D1.24 — per-order state at the session boundary (FIRST — unblocks A4)

**Observed:** after 200 fully-closed lifecycles with the mirror flat, every per-order map still held
200 entries — `_neutral`, `_orders`, `_trades`, `_to_ib`, `_from_ib`, `_acked`, `_seen_execs`.
`connect()` clears the vendor id maps and **not** `_orders`. Because IBKR order ids reset per
session, **`cancel_order` on a pre-restart id puts a live foreign order's `orderId` on the wire**.
No race required. `query_order_status` returns the dead session's cached `working` indefinitely, and
§4:241 names three outcomes of which this adapter can currently reach two.

**Two separate problems; fix both and keep them distinct:**
- **Session-boundary clearing.** All per-order state is scoped to a session and cleared when one
  ends. Decide and state whether clearing happens on `disconnect()`, on `connect()`, or both, and
  what happens to state for orders that were genuinely in flight when the session dropped — that
  last case is the one with a real answer owed
- **Unbounded growth within a session.** Even correctly scoped, 200 closed lifecycles should not
  retain 200 entries. State your retention rule and why it cannot discard something still needed

**Prove:** non-vacuity — assert the maps were genuinely populated before the boundary, so "cleared"
is not empty→empty. Assert a pre-restart id is rejected rather than transmitted, and name what the
rejection looks like to the caller. Can-fail with all four outputs, `__pycache__` purged.

### A2. D1.23 — a cancelled `connect()` leaves the order path live and mute

**Observed:** `_connected = True` is set before the rebuild is awaited; `CancelledError` is a
`BaseException` so `except Exception` misses it; nothing unwinds. Measured: `place_order`
**succeeds and reaches the venue** while acks, fills and mirror are all empty and no `on_session`
was ever published.

**Any caller using `asyncio.wait_for` lands in that window** — and bounding a venue call with
`wait_for` is the ordinary thing to do, not an exotic one. R2 will do it.

Fix so a cancelled or failed `connect()` leaves the adapter in a state that **refuses orders**, and
so cancellation unwinds rather than being skipped. Handle `BaseException` deliberately where
cancellation must be caught, and **re-raise** — swallowing `CancelledError` breaks task cancellation
semantics and creates a different defect.

**Prove:** drive a `connect()` cancelled at the rebuild await. Assert `place_order` is refused, and
that the refusal is observable to the caller rather than silent. Non-vacuity: assert the cancellation
genuinely landed inside the intended window, not before `connectAsync` or after publish.

### A3. D1.25 — session state published from a deferred task that never re-checks

**Observed:** `_on_data_loss_restore` schedules and returns; a `disconnect()` in the gap publishes
`UP_DATA_LOSS` (`is_up=True`) over a torn-down session. The rebuild verdict selects only the
`reason` **string** and never gates the publish. **Fails toward resuming.**

Fix so any deferred publish re-checks session validity at publish time, not at schedule time, and so
the rebuild verdict gates **whether** to publish, not merely what it says.

This is the same defect shape ARC 019 closed in §3 — plain `UP` published over an unrebuilt mirror —
arriving by a different route. **Assert the invariant once, across all emission sites**, rather than
patching this path; ARC 019 already established the mechanically-asserted form.

### A4. D1.27(b) — the startup gate discriminates by ownership, not elapsed time

**Operator ruling, ratified. Record this text verbatim in the decision record:**

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

ARC 017 already built the mechanism as guard 2 (the ownership filter). This makes it the primary
discriminator rather than a second line.

**The A1 dependency is not optional.** If A1's clearing is incomplete, this change converts a
conservative time gate into an ownership gate that can be fooled. Assert the dependency in the test:
a pre-session-boundary id must not be admitted.

**Prove:** an owned order's ack and fill are admitted during the window; a replayed foreign execution
is refused; ARC 017's phantom-fill traversal still passes. Non-vacuity: assert both an admission and
a refusal actually occurred — a gate that admits everything and a gate that refuses everything both
pass a one-sided test.

### A5. D1.26 — overlapping `query_positions()` lose the newer snapshot

**Observed:** `_mirror` assigned wholesale with no ordering guard; `mirror={}` after the venue had
confirmed `+3`. The module produces the concurrent second read itself. The adjacent fill-vs-read race
**is** already guarded — read-vs-read is not. **This is the protective path's only input.**

Fix with an ordering guard. Options include a monotonic sequence on each read with stale results
discarded, or serialising reads. State your choice and why, and specifically why it does not
introduce an await on the protective path.

**Prove:** two overlapping reads where the older completes last; assert the newer survives.
Non-vacuity: assert the overlap genuinely occurred — ARC 019's traversal caught two non-vacuity
failures where a sequence never actually interleaved, and this is the same trap.

### A6. D1.27(a) + D1.28 — flatten: idempotency window and an observable attempt record

These are one unit: both concern the protective path's ability to do the right thing and to say what
it did.

**Operator ruling, ratified. Record verbatim:**

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

**Window duration is yours to choose and to justify.** State the value, what it is derived from, and
why. Do not hardcode a bare literal — §12A is the home for tunables, and a magic number in the
protective path is §7.4's anchor problem.

**D1.28 — the protective path must be able to report that it failed.** Today `flatten` cannot
signal an under-sized close after a racing fill, a silent no-op on an unheld symbol, or a
non-idempotent `disconnect`. Produce an **observable attempt record**: what symbols, what
quantities, what order ids, and what was suppressed by the idempotency window. Follow the local
receipt pattern `place_order` already uses — the record is the adapter's declaration of intent, not
a claim about the venue.

**Do not build the reconciler.** Intent-versus-outcome is R2's; record the obligation.

**Prove:** two flattens inside the window emit one set of orders and record one suppression; two
outside the window emit twice; an unheld symbol produces an observable no-op rather than silence; the
attempt record survives the racing-fill case that ARC 019 measured. Can-fail on the suppression
logic, four outputs, `__pycache__` purged.

### A7. D1.22 — make absorption observable, decide nothing else

ARC 019's finding: 200 `place_order` calls into a verified-full pipe all returned normally, 155 in
`ib_async`'s `_msgQ`, asyncio buffering 10,204 B, **zero bytes drained**, and no send verb can tell
the caller which orders reached the venue.

Resolution is §4's — pending-timeout state machine plus `query_order_status`, both the Limiter's, and
**the repair is never a resend.** Not this arc's.

**What is this arc's:** the adapter currently gives a consumer no way to know it is absorbing. Expose
queue depth and write-buffer state as **observable adapter state**. That is cheap, it is honest, and
without it R2 has to infer absorption from silence.

**Do not implement a bounded-queue policy.** Where the bound sits and what happens at it is a Limiter
decision recorded in D1.22.

### A8. The per-writer field-meaning rule

`avg_price` has now carried two meanings twice — ARC 014's unit mismatch, and ARC 019's
last-fill-price versus weighted-average depending on which handler wrote last. Both times only a new
*class* of test could expose it, because both writers were individually plausible.

**Standing rule, applied here:** any field written by more than one event handler has its meaning
asserted **per writer**. Enumerate the multi-writer fields in the adapter, and for each, assert what
every writer means by it. Where two writers disagree, that is a finding — report it; do not pick one
silently.

This is bounded work: enumerate, assert, report. It is not a refactor.

---

## 5. SUB-AGENT C — the coverage scheme, and one gate

### C1. Rename the scheme so breadth stops reading as completeness

**Operator ruling:** `sec2a-element-v1` measures §2A **element coverage** — breadth. It is blind to
depth, and ARC 019 proved it: an arc that closed four defects, discovered five more, corrected a
banked performance figure fivefold and produced the module's first Tier-3 traversal registered as
**zero movement**.

- Rename the claim to **`broker_order_element_coverage_v1`** and drop "percent moved" framing
  wherever it appears in the ledger and the harness. The name must carry the limitation
- Keep the scheme identifier and the cross-derivation; this is a rename plus a framing correction,
  not a new measurement
- **Do not invent a confidence dimension.** A per-element confidence score is a hand-maintained
  rubric, which is the anchor the harness exists to remove

### C2. Add a depth figure — derived, and deliberately not a percent

Register **open CHECK-DEBT rows scoped to broker-order** as a claim. It rises when defects are found
and falls when they are fixed, it is fully derivable from the ledger, and it needs no rubric.

- **It must never be expressed as a percent.** Its denominator would be "how much do we trust this
  module," which is unknowable — that is named gap 5 exactly. State this beside the claim
- Scoping rows to a module needs a rule. State it, derive it, and say what is ambiguous. If rows
  cannot be attributed to a module without judgment, say so and register what can be

### C3. D3.7 — the per-hook canary, if it is closeable

ARC 019 established that `check_hook_suite` cannot prove the *pinned* environment's own
non-vacuity: nothing structural separates a bandit that scans 21 files from one that raises on all
21 and exits 0. That is the ARC 006–010 defect exactly, and it is currently undetectable.

Assess whether a per-hook canary — a known-bad fixture each hook must catch on every run — is
workable, or whether the cost (a permanent deliberate defect in the tree, or a fixture directory each
hook must be scoped to see) makes it worse than the debt.

**"Not closeable at acceptable cost, here is why" is a complete answer.** ARC 019's C3 rejected four
closures in writing and that was the right outcome.

### C4. Then stop.

Apparatus expansion beyond C1–C3 is out of scope. A good idea for an eleventh gate is a debt row.

---

## 6. Pending spec amendments — recorded, not applied

The two rulings in A4 and A6 change behaviour the frozen spec does not describe. **The frozen spec is
not edited** (prohibition 1).

Create or extend a single record — `docs/SPEC-AMENDMENTS.md` is the natural home if none exists —
carrying, for each ruling: the verbatim ruling text as given above, the section that would have to
say it, the arc that implemented it, and the fact that it is **pending** a v1.4 the architect owns.

**Attribute it properly.** D2.17 exists because an unattributed citation reads as spec. Each entry
names its origin as an operator ruling in ARC 020, not as spec text.

---

## 7. PHASE 4 — integration and verification

Parent-owned.

1. Merge worktrees; verify each was based on the right commit
2. Register any new claim in `checks/registry.json` and `derived_claims.json`
3. **Confirm every removed `strict=True` xfail corresponds to a landed fix**, and that no marker was
   removed without one. Derive the count of remaining xfails; do not assert it
4. **Reconcile C's ledger edits against `check_derived_claims`.** The harness owns the count. ARC 019
   caught a D1.20 row first written `**ADAPTER HALF DISCHARGED ARC 019**` — matching the bold-span
   rule and silently removing a row whose own text says the consumer half stays open. The
   `NARROWED, NOT DISCHARGED` convention exists for this
5. Confirm no plants remain: `git status --porcelain`, `__pycache__` purged, sha256 spot-checks,
   `git config --get core.bare` unset, `git fsck` clean
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

7. Clean up temp files per `CLAUDE.md`
8. Commit, PR, **merge, and confirm the merge landed on `main`**

---

## 8. PHASE 5 — the tap bundle, still owed

Two discharges have been waiting on one IB Key tap since ARC 018. **This is the justified ask.**

**If the operator grants a session, in this order:**

1. **D1.12 first.** Arm `nix-reboot-capture.service`, reboot, and let the capture run **before anyone
   touches the console**. The mechanism ARC 019 built is trustworthy precisely because it records
   evidence that nobody was there — `who`, `loginctl`, uptime against a 300 s ceiling. Touch the
   console first and the tap is wasted
2. **The rejection-taxonomy confirmation** owed from ARC 018: `clientId=905`, unaffordable size,
   `reject_category=INSUFFICIENT_MARGIN` with `reason` still carrying the `201` text. Both halves in
   one observation, and it re-validates the text anchor against IBKR's current wording — offline
   tests cannot
3. **Anything A2, A4 or A6 can corroborate live** without placing orders beyond the flatten cycle
   already proven in ARC 014

**Decline near the 16:00 CT close** — ARC 017's precedent, and it stands.

**If no session:** known-red markers naming R1-A and D1.12.

Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or strategy
performance — the feed is delayed ~600 s. Say so in `RESULTS.md` in those words.

---

## 9. Write-back gate

1. Append this arc's summary to `~/nix/sessions/SESSION.md`
2. Series row in **`docs/CHECK-DEBT.md`**
3. **Overwrite** `~/nix/downloads/RESULTS.md`
4. `cat` both, paste their state into the response
5. Percent moved for broker-order, apparatus, whole project — using the renamed scheme, keeping
   **level and delta distinguishable**, and naming what each derives from. **Element coverage is
   expected not to move; say so rather than reaching for a number that does**
6. Only then `**** ARC completed ****`

---

## 10. Success criteria

**Sub-agent A**
- [ ] D1.24: session-boundary clearing and in-session retention both addressed and kept distinct; in-flight-at-drop case answered; pre-restart id provably not transmitted
- [ ] D1.23: cancelled/failed `connect()` refuses orders; cancellation unwinds and re-raises; window entry asserted
- [ ] D1.25: deferred publishes re-check at publish time; verdict gates whether, not just what; invariant asserted across all emission sites
- [ ] D1.27(b): ownership discrimination landed, ruling recorded verbatim, A1 dependency asserted in test; ARC 017's phantom-fill traversal still passes
- [ ] D1.26: ordering guard with choice justified and no await added to the protective path; overlap proven genuine
- [ ] D1.27(a): idempotency window with duration justified and not a bare literal; ruling recorded verbatim
- [ ] D1.28: observable attempt record covering suppressions, unheld symbols, and the racing-fill case
- [ ] D1.22: queue depth and write-buffer state observable; no bounding policy implemented
- [ ] A8: multi-writer fields enumerated and asserted per writer; disagreements reported, not resolved silently
- [ ] Every fix: non-vacuity before can-fail, four outputs, `__pycache__` purged, xfail removed in the same motion

**Sub-agent C**
- [ ] Scheme renamed; "percent moved" framing corrected in ledger and harness; no confidence dimension invented
- [ ] Depth claim registered, derived, explicitly not a percent, with the not-a-percent reason stated beside it
- [ ] Module-scoping rule stated and derived, with ambiguity named
- [ ] D3.7 assessed; a reasoned refusal accepted
- [ ] Nothing built beyond C1–C3

**Integration**
- [ ] Pending-amendment record created with both rulings verbatim and properly attributed
- [ ] Every removed xfail corresponds to a landed fix; remaining count derived
- [ ] verify exit 0; both new gates pass; every count derived against no stated expectation
- [ ] pre-commit clean; harness/ledger reconciled with the harness winning
- [ ] `core.bare` unset, `git fsck` clean, no plants, `__pycache__` purged
- [ ] Merged and confirmed on `main`
- [ ] Write-back gate satisfied

**Explicitly NOT in this arc:** the Limiter or any consumer · D1.22's bounding policy · D1.19
(`AckProvenance`) · D1.20's consumer half · D2.14 residuals · D2.15 call-site derivation · D3.8 ·
§13 objective 11 (needs the stop loop → R2) · objective 24 (needs broker-datafeed → R1-D) · a v1.4
of the frozen spec.

**Apply §0a to this brief.** ARC 018 found ten defects in its predecessor, ARC 019 found a direct
contradiction with the frozen spec in mine. Report what you find rather than reconciling it.

Report deviations rather than substituting. A named gap is worth more than a green claim.
