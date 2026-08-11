# ARC 023 — Binding · The Four · Amendment 5
### Product first, then bind — because ARC 022 proved a gate bound to a moving subject binds to nothing

===RUN SUMMARY: ARC 023 — Bind or Retire the Five UNBOUND Gates; Close F12/F13/F17/F21; Amendment 5 (Per-Channel Freshness), Estimated run time: 5.5–6 h, completes ~15% of the current stage (converts the UNBOUND census from a list of owed work into a settled BOUND/RETIRED disposition for every gate in the tree, repairs the freshness path that currently halts-and-flattens on the only healthy data channel Stage 0 has, and closes the three remaining Tier-3 defects that put phantom state on the wire or lose sealed bars silently)===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract, doctrine B.4
- `~/nix/docs/nix_check_contract.md` — §5.3 verdict semantics
- `~/nix/docs/debug.md` v1.2.0 — §2.1 overview · §3 Tier 1 · §4 Tier 2 · **§5 Tier 3** (verified first-hand in ARC 022)
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A, §4, §6.4, §7.6, §7.7, §13
- `~/nix/docs/SPEC-AMENDMENTS.md` — Amendments 1–4 and Amendment 3's refinement; this arc adds 5
- `~/nix/docs/CHECK-DEBT.md`

Authority order per `CLAUDE.md`. **Verified on-disk state outranks this document.**
`python` is not on PATH; use `.venv/bin/python`. `verify.py` is at `scripts/verify.py`.

### 0a. Self-audit clause

Report contradictions in this brief rather than reconciling them. ARC 020 found two; ARC 021 found a
citation that resolved cleanly and pointed at the section the arc's own prohibition banned; ARC 022
found a design sketch that would have blinded both gates it was meant to serve.

Every §-citation in this brief is second-hand from your own prior reports. **A citation that resolves
but whose content does not support the claim beside it is a finding.**

### 0b. NEW STANDING CLAUSE — the architect's spellings are non-binding

ARC 022's A refused a spelling I specified — deriving the roster by concatenating the partition
constants — and refused it *with measurement*: both datafeed gates AST-read the roster, accept only a
literal `Tuple`/`List`, and a `BinOp` yields nothing, so the change would have blinded both to
CANNOT_MEASURE and reddened four claims, invisibly, since one was already at exit 2.

**The refusal was correct and it is now policy.** Where this brief states an implementation spelling
rather than an invariant, the spelling is a suggestion. **If implementing it as written would degrade
an instrument, refuse it, say so, and show the measurement.** This is check-rule 5 — assert
invariants, not snapshotted values — turned on the briefs themselves.

### 0c. Baseline — confirm, do not assume

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

ARC 022 reported: pytest 338 passed + 2 xfailed (340 collected), registered checks 12, claims 13/13,
CHECK-DEBT 62 rows, pre-commit 8/8, `verify.py` exit 1 with **9 passed / 1 failed / 2 cannot-measure**.
**Reported values, not targets.**

**Standing rule, tightened.** The accepted `verify.py` baseline is: `check_ibgateway_service` FAIL and
`check_ibgateway_config` cannot-measure from the Gateway's daily session expiry, plus
`check_datafeed_granted_mode` cannot-measure until this arc binds it. **A further *failure* is a real
finding; so is any further *non-pass* whose cause is not named.** ARC 022 had to draw that distinction
mid-arc because the old rule said only "a third failure."

`git add -A` before `pre-commit` — it does not scan untracked files. **And see Phase 0 item 3 before
running `git add -A` in any worktree.**

---

## 1. PHASE 0 — three reconciliations, before any build

Cheap, and two of them bear on whether ARC 022's results are safe to bank.

### 0.1 A contradiction between two derived figures in ARC 022's own results

`broker_order_open_debt_rows` is reported at **level 13, Δ +2 this arc**, while the corrected series
reads `ARC 020: 11 → ARC 021: 13 → ARC 022: 13` — which makes this arc's delta **0**.

Re-derive both from the tree. State which figure was wrong and why, and whether "+2 real" was
annotating the ARC 021 transition in the ARC 022 column. **This is the derived-figure contradiction
class and `check_derived_claims` reports 13/13 over it** — that gap is item 3.4's subject.

### 0.2 Debt ledger — opened and closed, not net

`check_debt_open_items` moved 53 → 62. The rows named in the results (D3.11–D3.16, D2.23, D2.24,
D1.39, D1.40) already exceed +9 before B's Tier-3 findings are counted, which implies closures
(D2.19, D2.21) are netting against them. **Report opened and closed separately with row IDs**, and
reconcile: "5 UNBOUND gates" against "D3.11–D3.14" is five subjects and four rows.

### 0.3 Security — positive confirmation, not reasoning

D2.24 staged a symlink pointing at `~/nix/state` (0600; hardware UUID and credential JSON), and
`git fsck` reported two dangling blobs. **The repo is public.**

Git stores a symlink as a blob containing its *target path*, not the target's contents, so exposure
should be bounded to a path string. **Confirm that; do not reason it.** Required:

- Identify both dangling blobs — `git cat-file -p` each, report type and size
- Search **all** reachable history on **all** refs, local and remote, for any blob whose path is under
  `state/` or `.venv/`, and for any symlink entry (mode `120000`) naming either
- Report whether any such object ever reached a commit, and whether any such commit was pushed

If anything reached pushed history, **stop and report before proceeding** — remediation on a public
repo is an operator decision, not a sub-agent's.

---

## 2. Hard prohibitions

1. **Invariant 3 — no object shared between broker-order and broker-datafeed** (§2A:103–107).
2. **Do not edit the frozen specs.** New surface lands as declared Nix additions plus a
   `SPEC-AMENDMENTS.md` entry attributed as an operator ruling (D2.17).
3. **No retry/backoff on the order path.** Mandatory for pollers outside it.
4. **`clientId=0` permanently excluded.** Datafeed **2** · Risk Engine **1** · diagnostics **905**.
5. **Do not build the Limiter, the Allocator, `capture.py` wiring, or any consumer.**
6. **No new Tier 3, and no Tier-3 findings beyond F12/F13/F17/F21.** Others stay debt rows.
7. **No hand-typed numbers in `RESULTS.md`.**
8. **`git add` before every gate measurement** — after Phase 0.3 clears the worktree ignore proof.
9. **Purge `__pycache__` between every plant/unplant step. No plant survives the arc.**
10. **Do not weaken a gate to make a residual disappear.** Doctrine B.4 cuts both ways.

---

## 3. STAGE 1 — two agents in parallel

The split is real because A's subjects are `scripts/broker/**` and B's are `checks/**` and `docs/**`,
**with one exclusion stated in B4 to keep it that way.**

### SUB-AGENT A — the four product defects and Amendment 5

Owns: `scripts/broker/**`, `scripts/tests/test_broker_datafeed.py`.

#### A1. F21 — Amendment 5, per-channel freshness

**Operator ruling. Record verbatim in `SPEC-AMENDMENTS.md`:**

> **AMENDMENT 5 — freshness is per-channel.** Each channel by which the seam observes a symbol carries
> its own venue timestamp and its own `effective_lag_s`. The seam declares **which channels are fresh
> and which are stale**, and does not collapse them into a single boolean. Excess staleness is computed
> per channel by the existing formula, `excess_staleness_s = (now − venue_ts) − effective_lag_s`, with
> the channel's own lag.
>
> The consumer decides which channels it requires. A consumer that requires ticks is entitled to halt
> when the tick channel is stale; the **seam** is not entitled to decide that on its behalf.
>
> Rationale: `evaluate_freshness` reads `last_tick_venue_ts` alone. At Stage 0 no tick stream exists —
> `reqTickByTickData` returns 10189 naming the product class — so a symbol fed entirely by successful,
> current polls is permanently STALE and drives §6.4's halt-and-flatten. **The module fail-closes on
> the only margin-class path it has.** A bar's venue timestamp is a venue observation exactly as a
> tick's is; the defect is that only one channel updates the stamp.
>
> This is Amendment 3's absence principle applied to freshness: the seam reports what it observed per
> channel and substitutes nothing — including not substituting a collapsed verdict for the
> observations that produced it.
>
> Sections that would have to say it: §2A's absent freshness-stamp declaration, and §6.4:371-374.
> Origin: operator ruling issued in ARC 023. Not spec text. Pending a v1.4 the architect owns.

The poll channel's `effective_lag_s` is **not measured on this system**. Grade it **VENDOR_DECLARED**
with a known-red marker naming the tap, exactly as `Bar.volume` was graded in ARC 022. Do not
substitute the tick channel's 600.0–601.9 s figure for it — that is the substitution the amendment
forbids, wearing a plausible number.

#### A2. F17 — the lag window

`lag_samples` is unbounded; the session mean read AGREES at 602.97 s while the last 100 packets sat at
900 s, 60 tolerances out, measured at 10,100 ticks. The load-bearing observable is wrong in the
direction that matters — it says the feed agrees while the feed has degraded by 300 s.

**Invariants, which bind. The numbers are mine; the spelling is not (§0b):**

- The window is bounded **by time, not by count.** A count window is meaningless across this system's
  tick-rate range — ARC 013 measured 18 delayed ticks in 40 s on MESU6, and F17 measured 10,100. A
  100-sample window spans 220 s at one rate and under a second at the other
- **Window = 60 s.** Derived from the halt decision's own timescale against the ~5 s tolerance implied
  by F17's own arithmetic, and it yields ~27 samples at ARC 013's measured rate
- **Sample floor = 5.** Below the floor, `FeedLag` declares **absence** — it does not report a mean
  over too few samples, and it does not fall back to the session-wide figure. Amendment 3
- Memory is bounded regardless of rate, and **which bound applied is observable**
- If a session-wide figure is retained at all it is **informational and separately named**, and
  nothing decides on it

If measurement shows 60 s or 5 is wrong, **report the measurement and the number you would choose.**
I own the numbers; I do not own them against evidence.

#### A3. F13 — the sealed-but-unpublished bar

A sink that raises leaves a bar sealed but unpublished; every later poll drops it as an identical
re-poll. Permanently lost, no revision, no error — while the attempt record says `ok=True, rows=4`.

Two defects, and both need closing: the loss, **and the attempt record asserting success over it.**
`ok=True` while a bar was lost is the "green while measuring nothing" class inside the product rather
than inside an instrument.

Seal and publish must not be separable in a way that admits a bar in neither state. **Do not solve
this by re-deriving the bar** — D1.14's seal-and-never-rewrite holds.

#### A4. F12 — phantom subscriptions on the wire

`poll_history` calls `setdefault`, manufacturing a subscription record, so a later `unsubscribe` puts
a real `cancelMktData` on the wire for a symbol never subscribed. Polling must not create
subscription state. Whatever `poll_history` legitimately needs to record is **not** a subscription and
must not be named or typed as one.

#### A5. D1.39/D1.40 — the vendor boundary

`Bar.volume`'s `-1` sentinel is IBKR's documented sentinel, **VENDOR_DECLARED**, never measured here,
and **not translated at the vendor boundary** — so a raw `-1` can reach a consumer as a volume. Translate
it at the boundary into the absence the amendment requires. The grade stays VENDOR_DECLARED with the
known-red marker naming the tap; translating it is not measuring it.

#### A6. Report the blast radius

Every signature, type, and return shape that moved. Stage 2 binds gates against these subjects and
cannot bind against a shape it has to guess.

---

### SUB-AGENT B — bind what A is not moving, and repair the ledger's reasoning

Owns: `checks/**` **except** `check_datafeed_granted_mode.py`, `check_datafeed_bar_seal.py`, and
`check_await_conformance`'s datafeed arms; `docs/CHECK-DEBT.md`.

#### B1. Bind or retire the UNBOUND gates whose subjects A is not touching

For each, a **four-output plant against the real subject**: control → plant → verdict names the site →
unplant → byte-identical restore by sha256, `__pycache__` purged between every step, verdicts recorded
**individually, never in aggregate** (§7.7).

Three dispositions, all acceptable:
- **BOUND** — can-fail demonstrated against the real subject
- **RETIRED** — the gate cannot be bound at acceptable cost, with reasons. ARC 020's D3.7 refusal is
  the standard, and a clean refusal is worth more than a weak binding
- **UNBOUND, deferred** — with the specific arc that can discharge it named

**A gate that cannot be planted against its real subject is telling you something about the gate.**
D3.16's gate reported PASS across two arcs over a method it never executed.

#### B2. The compensating-control audit — D3.15 generalised

`check_datafeed_bar_seal` arm 4 measures nothing, and **D2.20 and D2.21 both cited that arm as their
compensating control.** A residual was accepted on the strength of a control that measures nothing.

Sweep every debt row whose acceptance rests on a compensating control. For each: **does the named
control actually measure the thing?** Derive the row set from the ledger, not a hand list. Any row
whose control is vacuous returns to open with its original severity restored.

Do not repair arm 4 — that is Stage 2's, since its subject moves under A.

#### B3. The claims harness cannot see a claim going untrue

D1.14's banked claim that `FeedLag` "is constructed twice … and is proven to refuse a field write"
**became untrue at merge**, and `check_derived_claims` reported 13/13 across it.

The harness verifies that numbers derive. It does not verify that a claim about a *demonstrated
property* still holds. Add an arm that covers claims of that shape — a claim asserting a
demonstration must re-execute the demonstration, or be demoted out of the claims set into prose.

**Either outcome is acceptable. A claim that cannot be re-executed is not a claim.**

#### B4. The exclusion, stated so it stays real

Do not touch `check_datafeed_granted_mode`, `check_datafeed_bar_seal`, or `check_await_conformance`'s
datafeed arms. Their subjects move under A, and binding a gate to a shape mid-change is ARC 022's
central finding manufactured deliberately. Stage 2 owns them.

#### B5. Then stop. A good idea is a debt row.

---

## 4. STAGE 2 — serial, after A lands: the datafeed gates

### S2.1 `check_datafeed_granted_mode` — REBUILD, not repair

**Operator ruling.** The gate never once drove `IBKRBrokerDatafeed.granted_mode` since the adapter
landed, reported PASS across two arcs over a subject it never executed, is CANNOT_MEASURE on control,
and arm B3's granted-side name set is **empty** on its real subject — vacuous, not approximate. Three
independent defects in one instrument is a rebuild, not a repair.

**Invariants (§0b — the spelling is yours):**
- Subject discovery is driven from the **settled roster**, not from return annotations. Discovery by
  annotation is what let the real adapter go undiscovered
- **A subject that cannot be executed is CANNOT_MEASURE and loud**, never PASS. ARC 022's half-repair
  established this against `nix_check_contract.md` §5.3 — keep it
- `NotImplementedError` from `ibkr_mapping.IBKRDatafeedAdapter` stays a note, not a failure. It is a
  refusing skeleton and reddening it for honouring its own contract is B.4's forbidden direction
- **Non-vacuity is asserted before any plant**: prove the gate's subject set actually contains
  `IBKRBrokerDatafeed.granted_mode`. That assertion is the whole of D3.16

### S2.2 `check_datafeed_bar_seal` arm 4 — D3.15

`_synth_value` cannot resolve a union, so all five published types report unsynthesisable and the arm
measures nothing. Repair it, then **re-verify the rows B2 returned to open** — some may close again
honestly once the control measures.

### S2.3 `check_await_conformance` — re-bind to A's settled port

A's changes move signatures. Re-run the both-directional can-fail against the settled surface. The
third comparison (roster ⊆ Protocol) closed a hole open since ARC 014 — confirm it still holds after
Amendment 5's shape change.

---

## 5. PHASE 4 — integration, and the arc's real test

Parent-owned.

1. Merge worktrees; verify each worktree's base explicitly. Confirm `provision_worktree.sh` now
   **proves** the `state/` and `.venv/` ignores per target (D2.24) before any `git add -A`
2. **Re-run ARC 021's two real plants against the settled adapter**: the deleted sentinel write in
   `subscribe()`, and requested-substituted-for-granted in the adapter-wide accessor.
   **Both gates must now FAIL and name the site.** ARC 022 reported exit 2 / exit 2 and exit 0 / exit 0.
   **If either still fails to discriminate, that is the headline and it is reported as such** — and
   D3.10 stands unnarrowed for a third arc
3. **A four-output plant for each product fix**: a plant that reinstates F12, F13, F17 and F21
   respectively must be caught by something, and **you must say by what** — gate or pytest, reported
   as separate channels. Reading a pytest catch as a gate catch is the conflation D3.10 exists to
   prevent
4. Register new gates and claims in `checks/registry.json`
5. Reconcile B3's harness change against the claims set; the harness owns the count
6. Confirm no plants; `__pycache__` purged; `core.bare != true`; `git fsck` reported
7. **`git add -A` first**, then all five raw:

```bash
cd ~/nix
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
git add -A && .venv/bin/pre-commit run --all-files 2>&1 | tail -14
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
.venv/bin/python checks/check_spec_citations.py; echo "spec_citations exit=$?"
```

**Derive every count against no stated expectation.** Decompose `verify.py` — if
`check_datafeed_granted_mode` now passes, the cannot-measure count should fall to 1, and if it does
not, name why.

8. Clean temp files per `CLAUDE.md`
9. Commit, PR, **merge, confirm on `origin/main`**

---

## 6. PHASE 5 — live (OPTIONAL, do not request a tap)

If `TAP_SESSION.md` exists, cite what it banked for the poll-channel lag (A1), `Bar.volume`'s sentinel
(A5), and D1.33. Otherwise **known-red markers naming the next tap** — the runbook exists and the
operator schedules it.

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.**

---

## 7. Write-back gate

1. Append this arc's summary to `~/nix/sessions/SESSION.md`
2. Series row in `docs/CHECK-DEBT.md`
3. **Overwrite** `~/nix/downloads/RESULTS.md`
4. `cat` both, paste their state
5. Coverage with **level and delta distinguishable** and each naming its derivation — and given Phase
   0.1, state explicitly which column each figure sits in
6. **A BOUND/RETIRED/DEFERRED disposition table for all 12 gates**, one row each
7. Only then `**** ARC completed ****`

---

## 8. Success criteria

**Phase 0**
- [ ] The `broker_order_open_debt_rows` contradiction re-derived and resolved, with the wrong figure named
- [ ] Debt reported opened and closed with row IDs; the 5-UNBOUND / 4-row discrepancy reconciled
- [ ] Dangling blobs identified by content; all refs searched for `state/`, `.venv/`, mode `120000`;
      **positive confirmation** that nothing reached pushed history, or a stop-and-report

**Stage 1 — A**
- [ ] Amendment 5 recorded verbatim; freshness per-channel; no collapsed verdict; poll-channel lag
      VENDOR_DECLARED with a known-red marker, **not** substituted from the tick channel
- [ ] F17: time-bounded window with a sample floor and declared absence below it; memory bounded;
      no decision rests on a session-wide figure
- [ ] F13: the sealed-but-unpublished state is unreachable, **and** `ok=True` can no longer be
      asserted over a lost bar; seal-and-never-rewrite intact
- [ ] F12: polling creates no subscription state; no wire message for a symbol never subscribed
- [ ] D1.39/D1.40: `-1` translated at the vendor boundary; grade unchanged
- [ ] Blast radius reported

**Stage 1 — B**
- [ ] Every non-excluded UNBOUND gate disposed BOUND / RETIRED / DEFERRED-with-arc-named, each with a
      four-output plant or a stated refusal
- [ ] Compensating-control audit complete; vacuous-control rows reopened at original severity
- [ ] Claims harness gains an arm for demonstration-claims, **or** such claims are demoted to prose
- [ ] The B4 exclusion honoured

**Stage 2**
- [ ] `check_datafeed_granted_mode` rebuilt; non-vacuity asserted before any plant; unexecutable
      subject is CANNOT_MEASURE and loud; `NotImplementedError` still a note
- [ ] Arm 4 repaired; B2's reopened rows re-verified against a control that now measures
- [ ] `check_await_conformance` re-bound both directions; roster ⊆ Protocol still holds

**Integration**
- [ ] **Both ARC 021 plants now FAIL both gates and name the site** — or the failure to discriminate
      is the reported headline
- [ ] Each of F12/F13/F17/F21 has a reinstatement plant, caught, with the catching channel named
- [ ] All 12 gates carry a disposition
- [ ] `verify.py` decomposed; any non-pass named with cause
- [ ] pytest delta explained; no plants; merged and confirmed on `origin/main`
- [ ] Write-back gate satisfied

**Explicitly NOT in this arc:** V24's kill-under-load drill (**R1-D**) · `capture.py` wiring, ZMQ, the
shared-memory ring (**R1-C**) · the Limiter and every consumer · a new Tier 3 · Tier-3 findings beyond
the four named · D1.22 · D1.19 · D1.20's consumer half · D1.35 config JSON · a v1.4 of the frozen
spec · the tap itself.

Report deviations rather than substituting. A named gap is worth more than a green claim.
