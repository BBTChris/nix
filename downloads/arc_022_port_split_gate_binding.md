# ARC 022 — Port Split · Gate Binding · Tier-3 on broker-datafeed
### Staged: one serial stage, then two parallel agents — because the parallelism is only real after the port settles

===RUN SUMMARY: ARC 022 — Datafeed Port Sync/Async Split; D3.10 Gate Binding and the UNBOUND Audit; Tier-3 on broker-datafeed, Estimated run time: 4.5–5 h, completes ~12-15% of the current stage (settles the datafeed port's async contract so a sync signature can no longer conceal a wire round-trip, converts "can-fail proven" from a claim about fakes into a claim about real subjects across every gate in the tree, and runs the module's first end-of-module traversal — plus two amendments the architect owes and one ledger scoping defect that inflated a coverage figure by five)===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract, doctrine B.4
- `~/nix/docs/debug.md` v1.2.0 — **tier map corrected below**
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A, §4, §13
- `~/nix/docs/SPEC-AMENDMENTS.md` — Amendments 1–3; this arc adds 4 and refines 3
- `~/nix/docs/CHECK-DEBT.md`

Authority order per `CLAUDE.md`. **Verified on-disk state outranks this document.**

`python` is not on PATH; use `.venv/bin/python`. `verify.py` is at `scripts/verify.py`.

### 0a. The tier map, corrected — and a new defect class

**ARC 021 found that the previous brief cited `debug.md §5` for "Tier 1 and Tier 2" while its own
prohibition 6 forbade Tier 3 — and §5 *is* "TIER 3 — END-OF-MODULE CERTIFICATION."** A literal reader
would have built exactly what the arc banned, on the architect's authority.

Per ARC 021's derivation: **Tier 1 = §3 · Tier 2 = §4 · Tier 3 = §5 · tier overview = §2.1.**
Verify this yourself before relying on it; it is second-hand here.

**This is a new class and it is worse than a phantom citation.** A phantom fails loudly and
`check_spec_citations` catches it. A *valid* citation pointing at the wrong content passes every gate
in the tree. If a citation in this brief resolves but its content does not support the claim beside
it, that is a finding — say so.

Standing notation, restated and this time obeyed: §13 numbers objectives 1–23 plainly and adopts the
`V` prefix at **V24** (spec line 919). The previous brief stated this and then violated it fourteen
lines later, twice.

### 0b. Baseline — confirm, do not assume

```bash
cd ~/nix
git fetch origin
git rev-parse --short HEAD
git merge-base --is-ancestor HEAD origin/main && echo "on origin/main" || echo "NOT on origin/main"
git status --porcelain
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
git add -A && .venv/bin/pre-commit run --all-files 2>&1 | tail -14
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
.venv/bin/python checks/check_spec_citations.py; echo "spec_citations exit=$?"
ls -la ~/nix/downloads/TAP_SESSION.md 2>/dev/null && echo "TAP PRESENT" || echo "NO TAP"
```

ARC 021 reported: pytest 293, registered checks 12, claims 13/13, CHECK-DEBT 53 rows, pre-commit 8/8,
`verify.py` exit 1. **Reported values, not targets.**

**`verify.py` exit 1 is the accepted baseline** — `check_ibgateway_service` failing and
`check_ibgateway_config` cannot-measure, both from the Gateway's daily session expiry, not code. **A
third failure is a real finding.** If a tap session has since run, expect exit 0.

**Note the `git add -A` before `pre-commit`.** ARC 021 measured this live: `pre-commit run
--all-files` **does not scan untracked files**, and all 8 hooks reported green over a sub-agent's new
gates for an entire build while ~30 findings waited for `git add`. Every prior brief's Phase 4 was
invalid over new work. This is the third time git's tracking state has silently set gate scope —
ARC 016's untracked broker package, ARC 020's stale local `main`, now this.

---

## 1. Why this arc is staged rather than three-way parallel

Stage 1's port change alters the surface Stage 2's traversal drives and the shape Stage 2's gates
read. Running all three in parallel would have B writing a traversal against a port mid-change and C
binding gates to a shape that is still moving — which is the D3.10 defect being manufactured
deliberately rather than avoided.

**Stage 1: sub-agent A alone, serial.** Port split, Amendment 4, Amendment 3's refinement.
**Stage 2: sub-agents B and C in parallel**, once the port has settled.

Do not compress this. The parallelism in Stage 2 is real; parallelism across the boundary is not.

---

## 2. Hard prohibitions

1. **Invariant 3 — no object shared between broker-order and broker-datafeed** (§2A:103–107;
   verify). ARC 021 refused three extractions and argued each; the same answers hold. The error
   tables in particular stay separate: 1101 means *the position mirror may have missed events* to one
   library and *subscriptions may have been dropped and the grant re-negotiated* to the other. One
   table forces one meaning on both.
2. **Do not edit the frozen specs.** New surface lands as declared Nix additions plus a
   `SPEC-AMENDMENTS.md` entry attributed as an operator ruling, never as spec text (D2.17).
3. **No retry/backoff on the order path.** Retry is *mandated* for pollers outside it.
4. **`clientId=0` permanently excluded.** Datafeed is **2** (ARC 021's argued decision); **1**
   reserved for the Risk Engine; **905** diagnostics.
5. **Do not build the Limiter, the Allocator, `capture.py` wiring, or any consumer.**
6. **No hand-typed numbers in `RESULTS.md`.**
7. **`git add` before every gate measurement.** §0b.
8. **Purge `__pycache__` between every plant/unplant step.**
9. **No plant survives the arc.**

---

## 3. STAGE 1 — SUB-AGENT A (serial): the port, and two amendments

Owns: `scripts/broker/**`, `scripts/tests/test_broker_datafeed.py`.

### A1. D1.38 — the datafeed port's sync/async split

**Operator ruling, ratified. Record verbatim in `SPEC-AMENDMENTS.md`:**

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

**Extend `check_await_conformance()` — do not build a second checker** (check-rule 8). It already
owns "seam signature conforms" for the order port. It must now assert **both directions** for the
datafeed port too, via `inspect.iscoroutinefunction`:
- every async-set verb **is** a coroutine function on every datafeed adapter, **and**
- every sync-set verb **is not**.

**Derive both sets from one declared constant per port.** Duplicating the verb lists between the
checker and the seam is how they drift. The asymmetric form — asserting only the async side —
reproduces ARC 015's hole in mirror image, and that hole has now been closed once already.

**Can-fail both directions:** make a sync verb async → FAIL naming the site → restore → pass; make an
async verb sync → same cycle. Four outputs per direction, `__pycache__` purged.

### A2. Amendment 4 — `on_bar` / `on_bar_revision`, ratified and scoped

**Operator ruling. Record verbatim:**

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

**Make the boundary enforceable, not merely documented.** A bar must carry its provenance, and a
tick-derived bar must be unconstructible by this adapter. `BarRevision.__post_init__` already refuses
to exist hollow — apply the same technique here rather than a comment.

### A3. Amendment 3 — the refinement, and paying down its over-application

**Operator ruling. Record as a refinement to Amendment 3, not a fourth amendment:**

> **AMENDMENT 3, REFINEMENT (ARC 022).** The absence principle applies to facts the venue *can fail
> to report*, not to every field as a matter of course. Where a field's presence is structurally
> guaranteed by the existence of its container — a bar that exists has an open — an optional type is
> noise, and its predictable consequence is consumers writing `or 0.0`, which reintroduces the
> substitution the amendment forbids while wearing a null check.
>
> **Each optional field must be justified by an observable absence**: a case where the venue returns
> the container and omits the field. Fields that cannot be absent are not optional.

ARC 021 reported the cost lands entirely on consumers that do not exist yet and that the bill is real
and unmeasured. **Apply the refinement to what ARC 021 built**: for every `| None` currently on a
tick or bar field, state the observable absence that justifies it, or remove the optionality.

Where absence *is* observable, keep it and say what the venue does. Where it is not, removing the
`| None` is not a weakening of the amendment — it is the amendment applied correctly.

### A4. Report the port change's blast radius

State plainly what Stage 2 will be working against: which signatures changed, which fields lost or
kept optionality, and which of ARC 021's tests needed rewriting. B and C both read this.

---

## 4. STAGE 2 — SUB-AGENT B: Tier 3 on broker-datafeed

Owns: `scripts/tests/test_datafeed_tier3.py` (new).

**Read `debug.md` §5 directly** — end-of-module certification. §0a's tier map is second-hand; confirm
it. Tier 3 asks whether the module is *good*, not whether it is *not visibly broken*, and its subject
is the sequences nobody designs for: the same operation twice, interleaved operations, a retry after
partial failure, a caller that abandons midway.

**You write no production code.** Output is the traversal suite plus a findings list. **A finding you
cannot fix is a successful outcome**; a finding you fix by reaching into `scripts/broker/` is a scope
violation. ARC 019's B ran this way and it worked.

### B1. The traversal set

At minimum:

| sequence | what it probes |
|---|---|
| `subscribe` twice for one symbol | idempotency of the subscription path |
| `subscribe` / `unsubscribe` interleaved for one symbol | ordering under overlap |
| `unsubscribe` for a symbol never subscribed | the silent-no-op class |
| a `poll_history` await cancelled mid-flight | caller abandons midway |
| two overlapping `poll_history` calls for one symbol | ARC 020's D1.26 shape, in the other library |
| a re-poll returning a *revised* bar while a subscription is live | seal versus stream, both writing |
| session drop and reconnect with subscriptions outstanding | are they re-established, or silently lost |
| a grant that changes on re-subscribe | D1.13's live shape — the sentinel's whole reason |
| `disconnect` with a poll in flight | teardown with work outstanding |
| `feed_lag()` read during a reconnect | a retained observable over a session that moved |

Add sequences your reading suggests are sharper. **Say which you added and why** — the judgment about
what to probe is the valuable part, not the count.

### B2. Rules

- **Non-vacuity is mandatory per sequence.** A traversal that passes because the sequence never
  actually interleaved has demonstrated nothing. Assert on observed ordering, not just end state.
  ARC 019's traversal caught two of its own that never interleaved
- **Assert the invariant, not a snapshot.** Do not encode an event sequence a legitimate refactor
  would break
- **Distinguish "wrong" from "undefined."** A sequence whose correct outcome the spec does not
  determine is a **spec finding** — report it and name the section that would need to say. Do not
  invent the answer
- **Three-encoding convention** as established in `test_broker_tier3.py`: a defect the spec determines
  gets a `strict=True` xfail; a spec gap gets a different encoding. Follow the module's own docstring
- Any control you add must fail for the reason you intend, asserted structurally **and**
  behaviourally

### B3. Findings report

Per finding: the sequence, observed behaviour, classification (**code defect / spec gap /
working-as-intended-but-surprising**), and recommended disposition. Triage is Phase 4's.

---

## 5. STAGE 2 — SUB-AGENT C: make "can-fail proven" mean something

Owns: `checks/**`, `checks/derived_claims.json`, `docs/CHECK-DEBT.md`.

### C1. D3.10 — the standing rule, ratified and strengthened

**Operator ruling. Record in `CHECK-DEBT.md` as a rule of record:**

> A gate's can-fail against a **purpose-built fake** proves the gate *can* discriminate, not that it
> discriminates **against its real subject**. Until a can-fail is demonstrated against the real
> subject the gate governs, the gate is recorded **UNBOUND**, and the debt it covers is **not
> narrowed**.
>
> A gate binds **per subject, not once.** A gate bound against one adapter is unbound against the
> next, because the next presents a third shape.

This is ratified because ARC 021 measured it: both new gates passed **two real planted defects**, and
so did all 49 of the adapter's own tests, after six fake-based plants had all failed correctly.

### C2. The UNBOUND audit — a census, not an estimate

For **every** registered gate, determine: was its can-fail ever demonstrated against the **real
subject it governs**, or only against a fake or a scratch fixture?

- Derive the gate list from the tree, never a hand list
- For each, cite the arc and the evidence. **"I believe so" is not an answer** — this rule exists to
  eliminate exactly that
- Record **BOUND** or **UNBOUND** per gate, and open a debt row for each UNBOUND one
- ARC 020's `check_order_path_bans` planted `import tenacity` into real files; `check_derived_claims`
  edited a real banked number. Those look bound. **Confirm rather than assume** — the two datafeed
  gates also looked proven

**Do not re-bind the two datafeed gates in this stage.** Their subject is changing under A. Binding a
gate to a shape mid-change is the D3.10 defect manufactured on purpose. That work is Phase 4's,
after A has landed.

### C3. D2.19 — the contamination that inflated a coverage figure by five

`broker_order_open_debt_rows` moved 11 → 16 in an arc that **did not touch broker-order**. Rows naming
`ibkr_mapping.py` — a file hosting both §2A adapters' mapping — are claimed by the order-side rule's
module-basename half.

Fix the scoping rule so a shared-host file does not attribute to one module by basename alone. State
what remains ambiguous; ARC 021 named this ambiguity before it bit, and it bit anyway.

**Re-derive both depth figures after the fix and report the corrected series**, saying plainly that
the prior 16 was contamination and not work.

### C4. D2.20 and D2.21 — assess, close or refuse with reasons

- **D2.20**: `check_datafeed_granted_mode` arm B3 approximates dataflow by intersecting sets of
  *names*, so every method call contributes its receiver to both sets. It is name-identity, not
  dataflow
- **D2.21**: the seal gate's guard-polarity remains unchecked

Both were named honestly by ARC 021 rather than hidden. Assess whether either is closeable at
acceptable cost. **"Not closeable at acceptable cost, here is why" is a complete answer** — ARC 020's
D3.7 refusal is the standard, and it was worth more than a weak closure.

**Do not weaken either gate to make a residual disappear.** Doctrine B.4 cuts both ways: a gate that
reddens correct code is broken, and a gate loosened until nothing reddens is worse.

### C5. Then stop.

No new gate beyond what C1–C4 require. A good idea is a debt row.

---

## 6. PHASE 4 — integration, binding, triage

Parent-owned.

1. Merge worktrees; **verify each worktree's base explicitly** (ARC 019: all three were provisioned
   from `main` rather than session HEAD). Confirm the `state/`-symlink provisioning fix is in place
   so agents stop rediscovering it (ARC 020 finding 9)
2. **Re-bind the two datafeed gates to the settled adapter**, and re-run ARC 021's two real plants:
   deleting the sentinel write in `subscribe()`, and substituting requested for granted in the
   adapter-wide accessor. **Both must now fail and name the site.** If either still passes, that is
   the arc's headline and it is reported as such
3. Register new gates and claims in `checks/registry.json`
4. **Triage B's findings.** Trivial fixes here; non-trivial ones become debt rows naming ARC 023.
   Do not batch-fix a concurrency defect under time pressure — that destroys the traversal's value
5. Reconcile C's ledger edits against `check_derived_claims`; the harness owns the count
6. Confirm no plants; `__pycache__` purged; `core.bare != true`; `git fsck` clean
7. **`git add -A` first**, then run:

```bash
cd ~/nix
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
git add -A && .venv/bin/pre-commit run --all-files 2>&1 | tail -14
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
.venv/bin/python checks/check_spec_citations.py; echo "spec_citations exit=$?"
```

All five raw. **Derive every count against no stated expectation.**

8. Clean temp files per `CLAUDE.md`
9. Commit, PR, **merge, confirm on `origin/main`**

---

## 7. PHASE 5 — live (OPTIONAL, do not request a tap)

If `TAP_SESSION.md` exists, cite what it banked for D1.33 and the lag re-measurement. If a live
session happens to exist, the grant-change-on-re-subscribe sequence (B1) is the one worth confirming
live, since it is D1.13's actual shape.

**Otherwise: known-red markers naming the next tap.** Do not request one — the runbook exists and the
operator schedules it.

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.**

---

## 8. Write-back gate

1. Append this arc's summary to `~/nix/sessions/SESSION.md`
2. Series row in **`docs/CHECK-DEBT.md`**
3. **Overwrite** `~/nix/downloads/RESULTS.md`
4. `cat` both, paste their state
5. Coverage for broker-order and broker-datafeed, **level and delta distinguishable**, naming what
   each derives from — and **the corrected broker-order depth series after D2.19**, with the prior
   value named as contamination
6. Only then `**** ARC completed ****`

---

## 9. Success criteria

**Stage 1 — A**
- [ ] Port split implemented per the ruling; ruling recorded verbatim and attributed
- [ ] `check_await_conformance()` **extended**, both directions, both ports, sets from one constant per port
- [ ] Can-fail both directions, four outputs each, `__pycache__` purged
- [ ] Amendment 4 recorded verbatim; bar provenance enforceable in code, not documented only
- [ ] Amendment 3 refinement recorded; every surviving `| None` justified by a stated observable absence, others removed
- [ ] Blast radius reported for B and C

**Stage 2 — B**
- [ ] Traversal covering at least the ten tabled sequences plus any added with reasoning
- [ ] Non-vacuity per sequence — observed ordering asserted
- [ ] Findings classified with recommended dispositions
- [ ] No writes into `scripts/broker/`

**Stage 2 — C**
- [ ] D3.10 rule recorded as a rule of record
- [ ] UNBOUND audit complete: every gate BOUND or UNBOUND with cited evidence; debt rows opened for UNBOUND
- [ ] Datafeed gates **not** re-bound in this stage
- [ ] D2.19 scoping fixed; both depth figures re-derived; prior 16 named as contamination
- [ ] D2.20 and D2.21 each closed or refused with reasons; neither gate weakened
- [ ] Nothing built beyond C1–C4

**Integration**
- [ ] Both ARC 021 real plants re-run against the settled adapter; **both fail and name the site**, or the failure to do so is the reported headline
- [ ] B's findings triaged, not batch-fixed
- [ ] `git add` performed before every gate measurement
- [ ] `verify.py` exit 0 if a tap ran; otherwise exit 1 with **only** the two Gateway checks and that cause named — a third failure is a real finding
- [ ] pytest delta explained; harness/ledger reconciled with the harness winning
- [ ] No plants; merged and confirmed on `origin/main`
- [ ] Write-back gate satisfied

**Explicitly NOT in this arc:** V24's kill-under-load drill (**R1-D**) · `capture.py` wiring, ZMQ,
the shared-memory ring (**R1-C**) · the Limiter and every consumer · D1.22's bounding policy · D1.19 ·
D1.20's consumer half · D1.35 config JSON · a v1.4 of the frozen spec · the tap itself.

**Apply §0a to this brief.** ARC 020 found two self-contradictions in mine; ARC 021 found a citation
that resolved correctly and pointed at the section the arc's own prohibition banned. Report what you
find rather than reconciling it.

Report deviations rather than substituting. A named gap is worth more than a green claim.
