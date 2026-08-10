# ARC 017 — Session-State Integrity · Startup Window Closure · Gate-Coverage Truth
### Mega arc · 3 parallel sub-agents · scoped from the ARC 017 read-only probe

===RUN SUMMARY: ARC 017 — Session-state integrity, startup window closure, gate-coverage truth (mega, 3 sub-agents), Estimated run time: 4-6 h, completes ~55% of R1-A readiness===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract
- `~/nix/docs/debug.md` v1.2.0 — three tiers; **§7.12 the standing question** applies to every gate written here
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A, §4, §14

Authority order per `CLAUDE.md`. Verified on-disk state outranks this document. If the disk
contradicts anything below, **the disk wins and you report it** rather than reconciling silently.
Baseline: `main @ 92f9f17`, clean tree, verify 6/exit 0, pytest 159, pre-commit 8/8.

**This arc reverses ARC 016's no-behaviour-change constraint.** ARC 016 correctly documented a live
window rather than closing it, because closure was out of its scope. Closure is the point of this
arc. Three items ARC 016 opened or surfaced are discharged here; two are explicitly not.

**Operator ratifications carried into this arc** (both are seam-visible, both decided):
1. Narrow `fetchFields` to positions + account only — drop `ORDERS_OPEN` and `ORDERS_COMPLETE`.
2. Extend the seam so a lossy session restore is expressible as **structured state**, not as a
   free-text reason string. **This is the primary work item, not a rider.**

### 0a. A correction to this brief, banked before the arc runs

An earlier draft of §7 read: *"Checks should be 8 (6 + order-path-bans + derived-claims) — derived,
not asserted."* That is doctrine B.7's failure mode appearing **inside the brief written to fix it**:
an executor holding the expected value does not derive freely, it derives toward the anchor. `cc`
caught it before execution and stated it would report the real number regardless.

Corrected below — §7 now names no expected count. **Record this as the ninth instance in the D2.8
evidence base, and the second found by applying §7.12 rather than by accident.**

Reasoning is given throughout so you can tell when it stops applying. If an instruction here is
wrong, say so and stop.

---

## 1. Priority note — read before scoping your effort

The probe found two defects. They are **not** equally probable, and the ordering is
counter-intuitive:

- **The startup window** needs an IBKR order-id collision **and** a concurrent `place_order` inside
  a single-digit-millisecond window, **and** a Limiter to receive the phantom fill. Real, narrow,
  currently unreachable end-to-end because no Limiter exists.
- **1101 mirror staleness needs no coincidence at all.** One reconnect with data loss and
  `_rebuild_mirror()` is never re-run — the adapter emits `UP` and returns. `flatten()` then reads
  that mirror as ground truth at 0.6 ms with zero venue queries. A stale mirror makes the
  **protective path confidently wrong**, which is the worst failure shape in this system:
  §14 says the exit path has zero wire dependency, and that guarantee is only as good as the mirror
  behind it.

**Sub-agent A treats 1101 as primary and the window as secondary.** If time pressure forces a
choice, 1101 lands and the window is deferred with a known-red marker naming R2 — not the reverse.

---

## 2. Hard prohibitions

1. **No retry/backoff on the order path.** No `tenacity`, `backoff`, `retrying`, or hand-rolled
   retry loop in `scripts/broker/`. §4: pending timeouts resolve via `query_order_status`; the
   system **never auto-resends**. A retry decorator on `place_order` turns one intended order into
   two.
2. **No `asyncio.run`, `run_until_complete`, `run_forever`, or blocking wait on the sync send path.**
   Invariant 5.
3. **`clientId=0` permanently excluded.** Diagnostics use **905**; **1** reserved for the Risk Engine.
4. **Do not un-ignore `state/`.** D1.16 is real but out of scope here — it holds the hardware UUID
   and credential JSON. It pairs with the deferred Fernet→TPM2 arc and gets its own review.
5. **Do not "fix" D1.17** (double DOWN on requested disconnect). §4 wants an unrequested drop
   distinguishable from a requested one; dropping one event destroys that. It is a Limiter-side
   edge-vs-level decision. Leave it, and confirm in `RESULTS.md` that it was left deliberately.
6. **No hand-typed numbers in `RESULTS.md`.** Every count from a pasted command.
7. **No plant survives the arc.** Every FAIL-with-CONTROL ends unplanted, byte-identical by sha256,
   and Phase 4 re-asserts a clean tree.

---

## 3. Sub-agent dispatch — disjoint file sets

| agent | owns (write) | may read | forbidden |
|---|---|---|---|
| **A** | `scripts/broker/**`, `scripts/tests/test_broker_order.py`, `scripts/tests/test_seam_simulate.py` | all | `checks/**`, `verify.py`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |
| **B** | `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md`, `scratch/instrument/**` | all | `scripts/broker/**`, `checks/**`, `verify.py` |
| **C** | `checks/**` (new files), `checks/derived_claims.json` | all | `scripts/broker/**`, `verify.py`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |

**Contention points, parent-owned, serialized in Phase 4:** `verify.py` registration · the final
full-tree run · the `CHECK-DEBT.md` count reconciliation against C's harness output.

If a sub-agent needs a write outside its set, it stops and reports rather than reaching across.

---

## 4. SUB-AGENT A — broker-order: session-state integrity and window closure

### A1 (PRIMARY). 1101 vs 1102 — structured state, and self-reconciliation

**Current state, from the probe:** `_on_ib_error` lines 726–735 carry distinct branches with
distinct reason strings, but **both emit `SessionState.UP`**, and `SessionState` has only UP/DOWN.
A consumer cannot distinguish them without string-matching `reason` — which is §7.4's stale literal
anchor, in the worst possible place. And the adapter **does not re-run `_rebuild_mirror()` on 1101**;
it emits and returns. The comment says "so the Limiter re-reconciles" — a requirement on a component
that does not exist, recorded nowhere a gate can read.

**Two changes:**

**(a) Make data-loss structured.** Extend the session event so the distinction is a field, not a
string. Shape is yours — a third enum member (`UP_DATA_LOSS`), or a boolean/flag alongside `UP`.
State your choice and why. Constraints:
- It must be **readable without parsing prose**
- It must be **vendor-neutral** — no IBKR error code crosses the seam (invariant 2). 1101/1102 are
  IBKR spellings; the seam carries the *meaning*
- `reason` may keep the human-readable text; it must stop being the only carrier of the fact

**(b) The adapter re-reconciles its own mirror on data-loss restore.** The mirror is the adapter's
own state and `flatten()` reads it as ground truth. On 1101, `_rebuild_mirror()` runs before the
session event is emitted, so no consumer ever sees UP over a stale mirror. This is **not** the
adapter making a trading decision — that stays the Limiter's. It is the adapter refusing to publish
a state it knows may be wrong.

**Precedent for extending §2A:** `feed_lag()` is already a declared Nix addition flagged as such in
`broker_seam.py`. Follow that pattern exactly — declare it, flag it, document why §2A as frozen
could not express it. Do **not** edit the frozen spec.

**Proof required:**
- Offline: drive 1101 and 1102 through the error handler. Assert the emitted states are
  **distinguishable without reading `reason`**, and that 1101 triggers a mirror rebuild while 1102
  does not.
- **Non-vacuity first:** populate the mirror before injecting 1101, so "rebuild happened" is not
  empty→empty. Assert the mirror was actually re-read.
- **Can-fail:** revert the branch so both emit plain UP → the test must FAIL and name the site →
  restore → pass. Paste all four.
- Update `test_seam_simulate.py` controls if the port surface changed. `AwaitDivergentBrokerOrder`
  and `HollowBrokerOrder` must still fail as controls afterwards — a port change that quietly makes
  a control pass is the ARC 016 §2a defect recurring.

### A2. `fetchFields` — narrow to positions + account

Ratified: drop `ORDERS_OPEN` and `ORDERS_COMPLETE`. Probe evidence: `ORDERS_COMPLETE` replays
completed orders onto `orderStatusEvent → _on_ib_order_status`, whose Filled/Cancelled branches
reach `_ensure_acked` and `on_cancel`. Gate-covered, `fetchFields`-uncovered — so §2b's "joint
sufficiency" framing holds for executions and **not** for orders.

**Gate this on a prerequisite:** first confirm **nothing reads the order fetches** —
`ib.orders()`, `ib.trades()`, `openOrders`, `reqAllOpenOrders`, or any startup reconciliation that
depends on them. If something does, **stop and report**; do not narrow and then discover a
dependency. If nothing does, narrow to `POSITIONS|ACCOUNT_UPDATES|SUB_ACCOUNT_UPDATES`.

Prove the resolved value the way the probe did — evaluate the enum, do not read the source line:

```
StartupFetchALL     = ...
passed after change = ...
```

Assert `EXECUTIONS`, `ORDERS_OPEN`, `ORDERS_COMPLETE` all absent.

Correct the §2b comment at all three sites. The current text asserts a symmetry the probe disproved;
leaving it invites a future author to trust a coverage claim that was never true.

### A3 (SECONDARY). Close the startup window

Probe trace, from `main @ 92f9f17`:

```
311  self._connected = True
316  self._startup_complete = True      <- gate opens
318  await self._rebuild_mirror()       <- 465: reqPositionsAsync, a real loop yield
319  self._sink.on_session(UP)
```

All three conditions hold simultaneously between 318 and its completion, and there is **no mutual
exclusion of any kind in the adapter** — no `Lock`, no `Semaphore`, no re-entrancy guard.
`_require_session` gates only on `_connected`, already `True` at 311. Nothing downstream of the
line-663 check re-tests startup state, so a matching `execDetails` reaches `_ensure_acked` and
`on_fill`.

**Fix: move the gate open to after the rebuild completes.** The gate must be closed for the entire
interval in which `_connected` is `True` and the mirror is not yet trustworthy.

Watch for the obvious trap: if `_rebuild_mirror()` itself relies on `_startup_complete` being `True`
to function, moving the line breaks it. Check before moving. If it does, the fix is a separate
internal flag, not reordering.

**Proof required:**
- **Non-vacuity:** demonstrate the handler is reachable at all in the test harness — a test that
  passes because nothing ever dispatched is the exact class §7.12 asks about
- Inject a matching `execDetails` **during** the rebuild await, offline via `FakeIB`. Assert **no**
  `on_fill` and **no** `on_ack` escape
- **Can-fail:** restore the old ordering → the injection must produce a phantom fill → the test must
  FAIL and name it → restore the fix → pass. Paste all four
- Assert the gate re-arms on reconnect (ARC 016 proved handler idempotency; prove the gate follows)

### A4. `_ack_once` scope check — five minutes, do it

ARC 016 noted acks are deduped through `_ack_once` while **session events are not deduped at all**.
D1.17 is deferred, but confirm the asymmetry is *deliberate* and not an oversight that also affects
`on_cancel` or `on_position`. One-paragraph answer. If other events share the gap, open it as a debt
item; do not fix it here.

---

## 5. SUB-AGENT B — gate coverage: three undemonstrated hooks, and a ledger that overstates itself

**Premise.** The probe found three of eight hooks have never been shown able to say no — and **two
of those three are not recorded as owed anywhere**. D3.1 reads as though one discharge covered
"bandit", but the entry was split into two scoped hooks in that same arc (ARC 010), and the plant
landed in `checks/check_venv.py` — disjoint from `bandit (tests)`' `^scripts/tests/` scope. D3.4
covers only `pytest --testmon`.

**A ledger that overstates its own coverage is the CHECK-DEBT defect class recurring for the third
time.** Fixing the ledger matters as much as demonstrating the hooks. Both are in scope.

### B1. Non-vacuity first, per hook

Before any plant, capture **how many files each hook actually examined** and assert non-zero.
`debug.md` warns some tools exit 0 on zero files; ARC 016 proved the scope list itself is mutable
(failure mode #14). Paste the counts. A hook that cannot report its own scope is itself a finding.

**Scope discipline:** each plant must land **inside that hook's own file set**. `bandit (tests)`
scopes to `^scripts/tests/`, so its plant goes there — planting in `checks/` is precisely the error
that made D3.1 read as discharged when it wasn't.

### B2. FAIL-with-CONTROL — the three undemonstrated hooks

| hook | plant | must be caught as | plant location |
|---|---|---|---|
| `ruff-format` | mis-formatted file (odd indentation, line length) | formatting diff / hook failure | inside its own scope |
| `bandit (tests)` | `subprocess.run(cmd, shell=True)` or equivalent | B602 or equivalent, HIGH | **`scripts/tests/`** — its scope |
| `pytest-affected` | assertion that must fail, in an affected test | test failure via the hook, not bare pytest | affected path |

For each: **CONTROL → PLANT → CAN-FAIL → RESTORE (sha256 byte-identical) → CONTROL**, exactly the
ARC 016 §1.3 shape.

Record each as **caught / caught but did not name the site / not caught**. The middle outcome is a
partial pass and must be reported as such, never rounded up.

**`ruff-format` caveat:** it *repairs* rather than reports. Its failure mode is legitimately "files
were modified by this hook". State plainly whether that is acceptable evidence for this hook, or
whether it needs `--check`-style configuration to report instead of repair. ARC 016 chose an
unfixable defect for `ruff-check` for exactly this reason — same problem, different hook. **If it
turns out to be unprovable as a reporting gate, the honest outcome is to record it as a formatter
rather than a gate — do not manufacture a pass.**

**`pytest-affected` caveat:** `--testmon` selects by dependency graph. Prove the planted failure is
actually *selected*, not merely present. A plant the selector skips demonstrates nothing, and
"a suite that silently skips a gate reports GREEN" is D2.12 verbatim.

### B3. Repair the ledger

- Correct D3.1 so it names **which** bandit hook was discharged and which was not
- Open ledger entries for `ruff-format` and `bandit (tests)` — they were owed and unrecorded
- Discharge what B2 proves; leave undischarged anything that comes back partial
- Recount mechanically. The series table silently skipped ARC 014 and 015 (ARC 016 finding #4) — a
  ledger that stops being written is indistinguishable from one with nothing to report

### B4. §7.12 applied to the config itself

Answer in writing, beside the config: **what would have to be true for `pre-commit run --all-files`
to pass while measuring nothing?** ARC 016 answered it once for the tracking case. `state/` proves
there is at least one live remaining answer. Write it down.

### B5. Cleanup

`scratch/instrument/` removed entirely. `git status --porcelain` clean of it.

---

## 6. SUB-AGENT C — checks: order-path bans, and the D2.8 harness

### C1. `checks/check_order_path_bans.py`

One gate, one property: **no banned construct on the order path.** Both ban classes in a single gate
so they cannot disagree about what "the order path" means (check-rule 8).

Bans, as **data** not hardcoded logic:
- retry libraries: `tenacity`, `backoff`, `retrying`
- loop-blocking calls: `asyncio.run`, `run_until_complete`, `run_forever`

Requirements:
- **Exit contract** 0=PASS / 1=FAIL / 2=CANNOT-MEASURE. A crashed gate is CANNOT-MEASURE, never 1
- **Two arms.** (i) AST-parse every `.py` under `scripts/broker/`, walking `Import`, `ImportFrom`,
  `Attribute`, decorator nodes. (ii) Import the seam in a subprocess; assert no banned module in
  that process's `sys.modules`. Arm (i) catches dormant code; arm (ii) catches a transitive pull-in
  arm (i) cannot see
- **Never anchor to a moving value.** Derive the file set from `Path("scripts/broker").rglob("*.py")`
  at run time — a new adapter file must be covered automatically
- **Non-vacuity before planting:** assert the set is non-empty and contains at least
  `broker_seam.py` and `broker_order_ibkr.py`
- **FAIL-with-CONTROL once per ban class** — plant `import tenacity` → FAIL naming file and line →
  unplant → PASS; then plant `run_until_complete` → same cycle. Testing one class and assuming the
  other is how the bandit hole survived four arcs
- **§7.12 answered in writing beside the gate**
- Fail closed and loud

### C2. D2.8 — the derive-never-restate harness

**D2.8 is doctrine B.7: no harness parses a constant out of a document and asserts the code equals
it.** It is the *derive-never-restate* class, **not** the vacuous-pass class — the ARC 016 brief
mis-cited it, `cc` caught the error, and the correction stands. D2.8 remains **open and unassigned**
and is discharged here for the first time.

Build `checks/check_derived_claims.py` + `checks/derived_claims.json`.

The JSON is a registry: each entry names **where a claim appears** (file + locating pattern) and
**the command that derives the true value**. The gate re-derives and asserts the document matches.

**Seed with six entries** — five general, one that closes a specific live wound:

1. `verify.py` check count
2. pytest collected-test count
3. `pinned_deps.json` entry count
4. CHECK-DEBT open-item count
5. **§2A broker-order element count** — derived from the frozen spec by identifier, not by bullet.
   The probe settled this: broker-order is **16** (9 verbs + 7 events); 19 was the markdown-bullet
   count across *both* libraries; both libraries by identifier is **22**; code declares 23 with
   `feed_lag()` as a flagged Nix addition
6. **The ARC 014 mapping classification.** This is the wound. The banked mapping reads
   "19 verbs/events — 8 CLEAN, 7 FRICTION, 4 GAP", and 8+7+4 = 19. **Two unrelated derivations both
   land on 19** — the bullet count and the classification total. That coincidence is what let a
   wrong number look right across three arcs. If broker-order is 16, the classification is over by
   3 and must be re-derived against the correct roster. Register the re-derived total; if it cannot
   be re-derived without judgment calls, say so and register what can be

Requirements:
- Exit contract as above
- **Non-vacuity:** registry non-empty, every referenced file exists, every derivation command
  produces a parseable number. An entry pointing at a missing file is **FAIL**, not skip
- **FAIL-with-CONTROL:** edit one banked number to a wrong value → gate FAILs and **names the claim,
  the stated value, and the derived value** → restore → PASS
- **§7.12 answered in writing beside the gate**
- **Scope discipline:** v1 covers numeric claims only. Do not attempt prose-fact verification

**Evidence base, for the record beside the gate — nine instances:** CHECK-DEBT hand-maintained and
wrong twice; the 10-minute feed delay sitting uncomputed in ARC 010's own banked output; the
`avg_price` unit mismatch; the D2.8 citation naming the wrong target; the series table silently
skipping two arcs; the 19/16 count that survived three arcs on a coincidence; and this brief's own
§7 anchoring the expected check count while asking for it to be derived (§0a).

---

## 7. PHASE 4 — serialization, integration, verification

Parent-owned. Sub-agents complete first.

1. Merge branches/worktrees; resolve collisions explicitly
2. Register new gates in `verify.py`
3. **Reconcile C's harness against B's ledger edits** — the CHECK-DEBT count is now machine-derived;
   if the harness and the ledger disagree, the harness is right and the ledger is corrected. This is
   the first live test of D2.8 doing its job
4. Confirm no plants remain: `git status --porcelain`, `scratch/` gone, sha256 spot-check
5. Run:

```bash
cd ~/nix
python verify.py; echo "verify exit=$?"
python -m pytest scripts/tests -q 2>&1 | tail -5
pre-commit run --all-files 2>&1 | tail -25
python - <<'PY'
import pathlib, re
print("checks in verify.py:", len(set(re.findall(r"check_[a-z0-9_]+", pathlib.Path("verify.py").read_text()))))
PY
```

All four outputs raw.

- **Test count:** must be ≥ the 159 baseline; explain the delta.
- **Check count:** derive it and report what it is. **This brief states no expected value** — see
  §0a. If the derived number surprises you, that is information, not an error to reconcile away.

6. Clean up temp files per `CLAUDE.md`
7. Commit, PR, merge. **Push the moment commits exist** — ARC 016 established that durability does
   not wait for a merge, and ARC 013's stranded branch is why

---

## 8. PHASE 5 — live confirmation (OPTIONAL — do not request a 2FA tap)

Only A1(b) and A3 have live-observable behaviour, and both need induced conditions.

- **If a session is live and the market is open:** reconnect on clientId 905 and confirm the gate
  re-arms and no startup replay escapes. That is the honest limit — 1101 cannot be induced on demand
- **1101 specifically:** do **not** manufacture. If it occurs naturally, capture it. Otherwise record
  the offline proof as the proof, and say so
- **If no session:** known-red marker naming **R1-A**. RED withholds certification, not durability —
  the arc banks, recorded NOT CERTIFIED

Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s. Say so in `RESULTS.md` in those words.

---

## 9. Write-back gate — completion is never claimed without this

1. Append this arc's summary to the end of `~/nix/sessions/SESSION.md` — **and add the series-table
   rows**, since ARC 014 and 015 are the precedent for that being silently skipped
2. **Overwrite** (not append) `~/nix/downloads/RESULTS.md`
3. `cat` both and paste their resulting state into the response
4. State percent moved for **broker-order**, **apparatus**, and **whole project** — each derived
   from something, naming what
5. Only then print `**** ARC completed ****`

---

## 10. Success criteria — all, or no completion claim

**Sub-agent A**
- [ ] Data-loss restore is **structured state**, distinguishable without reading `reason`; no IBKR code crosses the seam
- [ ] Adapter re-runs `_rebuild_mirror()` on data-loss restore, **before** emitting the session event
- [ ] Non-vacuity proven (mirror populated first); can-fail demonstrated, all four outputs pasted
- [ ] `test_seam_simulate.py` controls still fail as controls after the port change
- [ ] Order-fetch dependency check run **before** narrowing; `fetchFields` resolved value pasted showing EXECUTIONS + both ORDERS flags absent — or a stop-and-report if a dependency exists
- [ ] §2b comments corrected at all three sites
- [ ] Startup gate closed for the whole rebuild interval; injected `execDetails` produces no `on_fill` and no `on_ack`; non-vacuity + can-fail both proven
- [ ] Gate re-arms on reconnect
- [ ] `_ack_once` asymmetry answered; new debt opened if it extends beyond session events

**Sub-agent B**
- [ ] Non-vacuity file counts captured per hook, all non-zero
- [ ] FAIL-with-CONTROL on `ruff-format`, `bandit (tests)`, `pytest-affected`, each planted **inside its own scope**
- [ ] `pytest-affected` plant proven **selected**, not merely present
- [ ] `ruff-format` repair-vs-report question answered explicitly
- [ ] Each recorded caught / caught-without-naming / not caught
- [ ] D3.1 corrected; ledger entries opened for the two unrecorded hooks; count recounted mechanically
- [ ] §7.12 answered in writing for the pre-commit config
- [ ] `scratch/instrument/` gone

**Sub-agent C**
- [ ] `check_order_path_bans.py` built; non-vacuity proven; FAIL-with-CONTROL for **both** ban classes; §7.12 answered beside the gate
- [ ] `check_derived_claims.py` + registry built, six entries seeded, non-vacuity proven, can-fail naming claim/stated/derived; §7.12 answered beside the gate
- [ ] ARC 014 classification re-derived against the 16-element roster, or the obstacle stated

**Integration**
- [ ] Gates registered; `verify.py` exit 0; check count **derived and reported**, against no stated expectation
- [ ] pytest ≥ 159, delta explained
- [ ] `pre-commit run --all-files` clean, with an explicit statement of which hooks are now *proven*
- [ ] Harness/ledger reconciliation performed; harness wins any disagreement
- [ ] No plants remain; temp files cleaned; pushed
- [ ] Every number in `RESULTS.md` traceable to a pasted command
- [ ] Write-back gate satisfied, including series-table rows

**Explicitly NOT in this arc, and why:** D1.16 (`state/encrypt_credentials.py` — pairs with the
Fernet→TPM2 review), D1.17 (double DOWN — Limiter-side edge-vs-level decision), V11 (needs a real
stop loop → R2), V24 (needs broker-datafeed → R1-D).

Report deviations rather than substituting. A named gap is worth more than a green claim.
