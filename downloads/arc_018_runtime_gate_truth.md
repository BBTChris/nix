# ARC 018 — Runtime-Gate Truth · Neutral Rejection Taxonomy · Ban-Gate Hardening
### Mega arc · 3 parallel sub-agents · scoped from ARC 017's named gaps

===RUN SUMMARY: ARC 018 — Runtime-gate truth, neutral rejection taxonomy, ban-gate hardening (mega, 3 sub-agents), Estimated run time: 4-6 h, completes ~60% of R1-A readiness===

---

## 0. Authority and posture

Read directly, never from a paraphrase:
- `~/nix/docs/VERIFY-AND-CHECKS.md` — check/verify contract
- `~/nix/docs/debug.md` — three tiers; **§7.12 the standing question** applies to every gate here
- `~/nix/docs/nics_risk_subsystem_spec_v1.3.md` — §2A, §4, §14
- `~/nix/docs/CHECK-DEBT.md` — the ledger; D2.13, D2.14, D2.15, D3.5, D1.18 are this arc's subjects

Authority order per `CLAUDE.md`. **Verified on-disk state outranks this document.** ARC 017 found six
defects in its own brief by applying that rule; apply it here with the same aggression. If the disk
contradicts anything below, the disk wins and you report it.

### 0a. Baseline — confirm, do not assume

This brief deliberately states **no expected end-state values** for any count. Confirm the starting
point and report any deviation before touching anything:

```bash
cd ~/nix
git rev-parse --short HEAD          # ARC 017 landed on PR #11 — confirm it is on main
git status --porcelain
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
```

Expected from ARC 017's banked results: verify 8/exit 0, pytest 159, pre-commit 8/8, debt 30 rows,
7 of 8 hooks with a demonstrated can-fail. **These are ARC 017's reported values, not this arc's
targets.** If any differs, that is information — report it rather than reconciling toward it.

Note `python` is not on PATH. Every command in this brief uses `.venv/bin/python`, and `verify.py`
lives at `scripts/verify.py`, not repo root. ARC 017 found both the hard way.

---

## 1. Why this arc, and why in this order

ARC 017 closed both session-integrity defects and discharged D2.8. It also surfaced something worse
than either: **D2.13 — the runtime gate exits 0 having measured nothing, today, in the shipped
config.**

A warm `pytest --testmon` prints `collected 0 items`, `no tests ran`, and exits **0**. The hook's own
comment claims removing exit-5 tolerance closed this; it does not, because exit 5 belongs to the
deselect path and testmon's empty run never reaches it. Compounding it, `.testmondata` is gitignored,
per-machine, and reviewer-invisible — **an untracked file sets what the runtime gate measures.**
Failure mode #14, inside the gate that is supposed to catch runtime regressions.

This is bandit-scanning-nothing recurring in a different hook, and it is live right now. It goes
first. Everything else in this arc is worth less while the runtime gate can report green having run
nothing.

**Sub-agent A is primary.** If time forces a choice, A lands and B or C defers with a known-red
marker naming R1-A.

---

## 2. Hard prohibitions

1. **No retry/backoff on the order path.** No `tenacity`, `backoff`, `retrying`, or hand-rolled retry
   loop in `scripts/broker/`. §4: pending timeouts resolve via `query_order_status`; the system
   **never auto-resends**.
2. **No `asyncio.run`, `run_until_complete`, `run_forever`, or blocking wait on the sync send path.**
   Invariant 5.
3. **`clientId=0` permanently excluded.** Diagnostics use **905**; **1** reserved for the Risk Engine.
4. **Do not un-ignore `state/`.** D1.16 pairs with the deferred Fernet→TPM2 arc.
5. **Do not "fix" D1.17.** §4 wants an unrequested drop distinguishable from a requested one. It is a
   Limiter-side edge-versus-level decision.
6. **No hand-typed numbers in `RESULTS.md`.** Every count from a pasted command.
7. **Purge `__pycache__` between every plant/unplant step.** ARC 017's seventh finding: a
   sha256-identical restore is **not** evidence the restored code ran. CPython validates `.pyc` on
   `(mtime, size)`, so a pure line swap can leave planted bytecode resident behind byte-identical
   source. It produced a false red in ARC 017's own first pass.
8. **No plant survives the arc.** Phase 4 re-asserts a clean tree.

---

## 3. Sub-agent dispatch — disjoint file sets

| agent | owns (write) | may read | forbidden |
|---|---|---|---|
| **A** | `.pre-commit-config.yaml`, `pyproject.toml` (pytest/testmon config only), `scratch/runtime/**`, `docs/CHECK-DEBT.md` | all | `scripts/broker/**`, `checks/**`, `checks/registry.json` |
| **B** | `scripts/broker/**`, `scripts/tests/test_broker_order.py`, `scripts/tests/test_seam_simulate.py` | all | `checks/**`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |
| **C** | `checks/**`, `checks/derived_claims.json` | all | `scripts/broker/**`, `.pre-commit-config.yaml`, `docs/CHECK-DEBT.md` |

**Contention points, parent-owned, serialized in Phase 4:** `checks/registry.json` registration · the
final full-tree run · reconciling A's ledger edits against C's harness output.

A sub-agent needing a write outside its set **stops and reports** rather than reaching across. ARC 017
noted a concurrent write by one sub-agent caused pre-commit to attribute a modification to a hook
that never writes files — so cross-set writes corrupt evidence, not just state.

---

## 4. SUB-AGENT A (PRIMARY) — make the runtime gate incapable of silent green

### A1. D2.13 — zero collection must never report success

**The defect, restated so the fix is aimed correctly:** the failure is not that testmon selects
nothing. Selecting nothing is *correct* when nothing changed. The failure is that a run which
measured nothing is **indistinguishable from a run that measured everything and passed.**

Fix so that a zero-collection run reports **CANNOT-MEASURE or FAIL, never PASS.** Approach is yours;
state your choice and why. Constraints:

- The gate must report **its own scope** — how many tests it selected — on every run, visibly.
  A gate that cannot say what it measured cannot be trusted to have measured anything
- Do **not** simply force a full sweep on every commit. That trades a silent-green defect for a
  slow gate nobody runs, which is a worse outcome by §7.12's own logic
- A legitimate "nothing changed, nothing to run" outcome must be **expressible and distinguishable**
  from "the selector is broken" and from "the database is missing"

**Prove it, in this order:**
1. **Non-vacuity:** demonstrate the gate can select a non-zero set at all in the current tree
2. **The defect reproduced:** warm the database, run with no changes, show the pre-fix behaviour
   (`collected 0`, exit 0) captured verbatim
3. **The fix:** same conditions, show the new verdict is not a silent pass
4. **Can-fail preserved:** ARC 017 proved `pytest-affected` catches a planted failure with selection
   proven (collected 9, neither 0 nor 159). Re-run that proof after the fix — a change that fixes
   zero-collection while breaking real selection is a net loss
5. **Purge `__pycache__` between steps** (prohibition 7)

### A2. `.testmondata` — the untracked file that sets gate scope

`.testmondata` is gitignored, per-machine, and reviewer-invisible. Two people running the same commit
can get different gate scopes and neither can tell.

**Do not fix by tracking it** — it is a binary SQLite artifact with WAL sidecars, and committing it
plants a second source of truth that goes stale immediately. ARC 016 rejected the same shape for
`downloads/*.py`.

Required instead: make the *state* of the database an **explicit, visible input** to the gate's
verdict. A missing, stale, or foreign database must be detectable and must not silently narrow scope.
State how you achieved that and what remains undetectable.

**Answer §7.12 in writing beside the config:** what would have to be true for this hook to pass while
measuring nothing? ARC 017 answered it once for the tracking case; this is the second live answer.

### A3. D3.5 — `ruff format --check`, discharge or state why not

ARC 017 demonstrated `ruff format --check` works as a reporting configuration (exit 1, sha256
unchanged, names `<file>:1:1`), but adopting it was a behaviour change out of that arc's scope. It is
in scope here.

Adopt it, and prove the full FAIL-with-CONTROL cycle with the site named. If adopting it breaks
developer ergonomics in a way you judge unacceptable, **say so and leave D3.5 open** — an honest open
debt beats a gate nobody can work with. Do not adopt it and then quietly relax it elsewhere.

ARC 017's causality finding stands as context: pre-commit's `files were modified by this hook`
attribution is **not causal** — it fired against `bandit`, which never writes files. Any evidence
resting on that message is unreliable regardless of which hook it names.

### A4. Verify ARC 016's restore was not compromised

Prohibition 7's `.pyc` finding was discovered in ARC 017. ARC 016 §1.3 used the same sha256-identical
restore as evidence.

ARC 016's plant *added* a line, so file size changed and the `.pyc` should have invalidated — but
"should have" is the phrasing this project keeps disproving. Spend five minutes confirming it, and
report the answer either way. If ARC 016's evidence is sound, say so and the matter is closed. If it
is not, that is a finding about a banked arc and it goes in the ledger.

### A5. Ledger

- Discharge what A proves; leave open what comes back partial
- The pre-ARC-010 bandit environment is still on disk in `~/.cache/pre-commit` and still reproduces
  the original defect verbatim (`exception while scanning file`, rc=0). Only the `rev: 1.9.4` pin
  routes around it. Record whether that is acceptable standing risk or owed as debt — a pin is a
  declaration, and this project's rule is that declarations are not evidence
- Recount mechanically. C's harness now owns the count; if A and the harness disagree in Phase 4,
  the harness wins

---

## 5. SUB-AGENT B — D1.18: no vendor spelling above the seam

### B1. The tension, stated fairly

ARC 017 reported rather than silently decided: an IBKR error integer still crosses the seam inside
`on_ack(reason)`. Invariant 2 forbids vendor types above the seam. An integer inside a free-text
field is not a vendor *type* in the type-system sense — so a narrow reading says invariant 2 holds.

**The operator ruling is that the narrow reading is insufficient, for one reason:** it is the same
defect ARC 017 just fixed at A1(a). A consumer that needs the distinction has no structured way to
get it, so it will string-match — and §7.4 names that a stale literal anchor. `1101` in a session
`reason` and an IBKR error integer in an ack `reason` are the same shape.

**This ruling is provisional and ratifiable on your findings.** If the code shows the reason field is
genuinely never consumed programmatically and there is a structural guarantee it cannot be, say so —
that is an argument the operator has not heard and it may change the decision.

### B2. The neutral rejection taxonomy

Introduce a vendor-neutral rejection reason as **structured state**, following A1(a)'s pattern
exactly:

- The *fact* — why the venue refused — becomes a structured, enumerated value
- `reason` keeps the human-readable text, **including** the IBKR code, for debugging. It stops being
  the only carrier
- No IBKR integer, code, or spelling is required to interpret the structured value
- Declared as a Nix addition following the `feed_lag()` and `UP_DATA_LOSS` precedent. **Frozen spec
  not edited**

**Taxonomy design — the hard part, and where judgment is wanted:** the categories must be ones a
*Limiter* can act on differently, not a re-spelling of IBKR's error list. If two IBKR codes lead to
the same Limiter behaviour they belong in the same category. If you cannot distinguish a category by
what a consumer would do differently, it should not exist. State your categories and the behavioural
distinction each earns.

Map the IBKR codes you can evidence. **Anything unmapped falls to an explicit unknown category** —
never to the nearest plausible match, and never silently. An unknown that reads as a known is worse
than an unknown that reads as unknown.

### B3. Proof

- **Invariant 2 asserted mechanically**, as A1(a) did: no IBKR code appears in any structured field,
  across every rejection path
- **Non-vacuity:** prove the rejection path is reachable and actually exercised — a taxonomy tested
  only on paths that never fire is the vacuous-control class
- **Can-fail:** collapse the taxonomy so every rejection maps to one category → the test must FAIL
  and name the site → restore → pass. Paste all four, with `__pycache__` purged between
- **Controls:** `HollowBrokerOrder`, working `StubBrokerOrder`, `AwaitDivergentBrokerOrder` must all
  still behave as controls after the port change. ARC 016 §2a is the precedent — a port change that
  quietly makes a control pass is the defect

### B4. `_mirror_stale` — named gap 7, one paragraph

ARC 017 left `_mirror_stale` as observable adapter state with no consumer, because the Limiter does
not exist. Confirm it is still observable, still correct, and record what a consumer will be required
to do with it. Do not build a consumer. This is a note for R2, written now while the reasoning is
fresh rather than reconstructed later.

---

## 6. SUB-AGENT C — close the ban gate's known evasions

ARC 017 shipped `check_order_path_bans.py` and named its own gaps honestly. Close the two that are
closeable; state clearly why the third is not.

### C1. D2.14 — hand-rolled retry loops

A PASS today means "no retry *library* and no loop-blocking *call*". It has never meant "nothing
retries". §2.1 bans hand-rolled retry loops and the gate cannot see them.

Extend the **existing** gate (check-rule 8 — do not build a second that could disagree). Detect the
shape structurally via AST: a loop construct whose body contains a send-path call, a bounded retry
counter around an order verb, an `except` that re-invokes the call it just caught.

**This will produce false positives, and that is the point of stating it now.** A gate that flags a
legitimate loop is recoverable; a gate that misses a real retry sends two orders. Bias toward
flagging, and provide an explicit, *narrow*, documented suppression for reviewed cases — never a
blanket exclusion, and never file-level.

**Non-vacuity, can-fail per detected shape, `__pycache__` purged, §7.12 answered beside the gate.**

### C2. D2.15 — a second home for the order path

`ORDER_PATH_DIRS` is the single fix point. A new *file* under `scripts/broker/` is covered
automatically; a new *directory* is not.

Make the discovery derive from something that moves with the tree rather than a hand-maintained list.
Options include deriving from what imports the seam, or from a declared marker the seam itself owns.
State your approach and what remains uncovered.

**Register the resulting scope as a claim in `derived_claims.json`** — the file set the gate believes
it covers is exactly the kind of number that goes stale silently.

### C3. Named gap 4 — dynamic evasion inside a function body

Report on it; do not necessarily fix it. A dynamic import inside a function that never runs at import
time is invisible to both arms. Assess honestly whether it is closeable without unacceptable false
positives. **"Not closeable at acceptable cost, here is why" is a complete and acceptable answer** —
ARC 017's named-gap discipline is the standard.

### C4. The percentage scheme — register one, retire the other

ARC 017 reported broker-order progress as ~13%, derived from the §2A 16-element roster. A prior
architect estimate used a readiness-weighted decomposition and produced ~42%. **Both call themselves
"broker-order percent" and are not comparable.** That is the 19-vs-16 shape recurring, in the progress
number itself.

Resolve it:
- The **module percent is the machine-derivable one** — the §2A element scheme. Register its
  derivation in `derived_claims.json` so the series is reproducible
- Readiness commentary may continue as prose but **must not be expressed as a percent**, so two
  incomparable numbers cannot both claim the name again
- Register the *scheme identifier* alongside the value, so a future change of scheme is visible
  rather than a silent discontinuity in the series

### C5. Named gap 5 — registry coverage, one paragraph

`check_derived_claims` proves every *registered* number is right; it cannot prove the registry covers
the numbers that matter. That is failure mode #14, inherent to a registry-driven instrument, and ARC
017 stated it beside the gate rather than papering over it. Confirm that statement is still accurate
and still visible. Do not attempt to fix it — an instrument that could prove its own completeness
would be a different and much larger thing.

---

## 7. PHASE 4 — serialization, integration, verification

Parent-owned. Sub-agents complete first.

1. Merge branches/worktrees; resolve collisions explicitly
2. Register any new or extended gates in `checks/registry.json` — note ARC 017 placed code-invariant
   gates in a `code-invariants` block, deliberately last and deliberately **not** `on_fail: halt`.
   Follow that placement unless you can argue otherwise
3. **Reconcile A's ledger edits against C's harness.** The harness owns the count; if they disagree,
   the harness is right and the ledger is corrected. ARC 017 proved this loop works — including
   catching its own discharge going stale
4. Confirm no plants remain: `git status --porcelain`, `scratch/` absent, sha256 spot-checks, **and
   `__pycache__` purged** so no stale bytecode masks a restore
5. Run:

```bash
cd ~/nix
.venv/bin/python scripts/verify.py; echo "verify exit=$?"
.venv/bin/python -m pytest scripts/tests -q 2>&1 | tail -3
.venv/bin/pre-commit run --all-files 2>&1 | tail -12
.venv/bin/python checks/check_derived_claims.py; echo "derived_claims exit=$?"
```

All four raw. **Derive every count; this brief states no expected values.** If a derived number
surprises you, that is information, not an error to reconcile away.

6. Clean up temp files per `CLAUDE.md`
7. Commit, PR, merge. **Push the moment commits exist** — durability does not wait for a merge

---

## 8. PHASE 5 — live confirmation (OPTIONAL — do not request a 2FA tap)

Only B has live-observable behaviour, and only on the rejection path.

- **If a session is live and the market is open, and well clear of the 16:00 CT close:** place an
  order the venue will refuse (an unaffordable size is the cleanest, and ARC 012 established that a
  rejection carries `err 201`). Confirm the structured category is populated and no IBKR integer is
  required to read it
- ARC 017 declined to connect at 15:59 CDT because evidence taken at a session boundary is ambiguous.
  **That judgment was correct and stands as precedent** — decline again under the same conditions
- **If no session, or the wrong time of day:** known-red marker naming **R1-A**. RED withholds
  certification, not durability

Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or strategy
performance — the feed is delayed ~600 s. Say so in `RESULTS.md` in those words.

---

## 9. Write-back gate — completion is never claimed without this

1. Append this arc's summary to the end of `~/nix/sessions/SESSION.md`
2. Add the series row to **`docs/CHECK-DEBT.md`**, where the series table actually lives — ARC 017
   found the previous brief misattributed it to `SESSION.md`
3. **Overwrite** (not append) `~/nix/downloads/RESULTS.md`
4. `cat` both and paste their resulting state into the response
5. State percent moved for **broker-order**, **apparatus**, and **whole project** — using the scheme
   C4 registers, naming the scheme and what each figure derives from
6. Only then print `**** ARC completed ****`

---

## 10. Success criteria — all, or no completion claim

**Sub-agent A (primary)**
- [ ] Zero-collection reports CANNOT-MEASURE or FAIL, never PASS; approach stated with reasoning
- [ ] Gate reports its own selected-test count visibly on every run
- [ ] Legitimate "nothing changed" is distinguishable from "selector broken" and "database missing"
- [ ] Defect reproduced pre-fix verbatim; fix demonstrated under identical conditions
- [ ] ARC 017's selection proof re-run and still passing after the fix
- [ ] `.testmondata` state is an explicit visible input; not fixed by tracking it; residual gap stated
- [ ] §7.12 answered in writing beside the config
- [ ] D3.5 discharged with the site named, or left open with an explicit ergonomic reason
- [ ] ARC 016's restore evidence verified against the `.pyc` finding, answered either way
- [ ] Cached pre-ARC-010 bandit environment assessed as standing risk or recorded as debt

**Sub-agent B**
- [ ] Structured neutral rejection category; `reason` retains human text including the IBKR code
- [ ] No IBKR integer or spelling required to interpret any structured field; asserted mechanically
- [ ] Categories justified by *distinct consumer behaviour*, each stated
- [ ] Unmapped codes fall to an explicit unknown, never a nearest match
- [ ] Non-vacuity proven; can-fail demonstrated with all four outputs, `__pycache__` purged between
- [ ] All three seam-simulate controls still behave as controls
- [ ] `_mirror_stale` note recorded for R2
- [ ] If the evidence argues against the provisional ruling, that argument is made rather than executed around

**Sub-agent C**
- [ ] D2.14 detects hand-rolled retry shapes structurally; existing gate extended, not duplicated
- [ ] Suppression mechanism is narrow, documented, never file-level or blanket
- [ ] D2.15 scope derives from the tree; resulting file set registered as a claim
- [ ] Named gap 4 assessed honestly; "not closeable at acceptable cost" accepted if argued
- [ ] One percentage scheme registered with its derivation and a scheme identifier; the other retired from percent form
- [ ] Named gap 5 statement confirmed still accurate and visible
- [ ] Non-vacuity + can-fail per new detection shape; §7.12 answered beside every gate touched

**Integration**
- [ ] Gates registered; verify exit 0; every count derived against no stated expectation
- [ ] pytest count reported with any delta explained
- [ ] pre-commit clean, with an explicit statement of which hooks are now proven and which are not
- [ ] Harness/ledger reconciliation performed; harness wins any disagreement
- [ ] No plants remain; `__pycache__` purged; temp files cleaned; pushed
- [ ] Every number in `RESULTS.md` traceable to a pasted command
- [ ] Write-back gate satisfied, series row in `CHECK-DEBT.md`

**Explicitly NOT in this arc:** D1.16 (`state/` — pairs with Fernet→TPM2), D1.17 (Limiter-side
edge-vs-level), V11 (needs a stop loop → R2), V24 (needs broker-datafeed → R1-D), ARC 014 grade
*values* (named gap 6 — a flip keeps the sum at 16 and inventing a second source would be the anchor
the gate exists to remove).

**Apply §0a's reading to this brief.** ARC 017 found six defects in its predecessor by doing so,
including a derivation pointed at the wrong file that would have reported a catastrophic false
regression. Report what you find rather than reconciling it.

Report deviations rather than substituting. A named gap is worth more than a green claim.
