# ARC 017 — RESULTS

**Session-state integrity · startup window closure · gate-coverage truth**
Mega arc, three parallel sub-agents on disjoint file sets. 2026-08-10.
Branch `arc-017-session-integrity` · **PR #11** · pushed at first commit, not at merge.

**STATUS: BANKED, NOT CERTIFIED — known-red `R1-A`.**

---

## 1. Verification — every number below is from a pasted command

```
$ .venv/bin/python scripts/verify.py
  [ok]   check_python_runtime
  [ok]   check_venv
  [ok]   check_node_identity
  [ok]   check_python_deps
  [ok]   check_ibgateway_config
  [ok]   check_ibgateway_service
  [ok]   check_order_path_bans
  [ok]   check_derived_claims

  8 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
verify exit=0
```

```
$ .venv/bin/python -m pytest scripts/tests -q
pytest exit=0
159 passed in 10.77s
```

```
$ .venv/bin/pre-commit run --all-files
pre-commit exit=0
ruff check...............................................................Passed
ruff format..............................................................Passed
pylint...................................................................Passed
mypy.....................................................................Passed
bandit (production)......................................................Passed
bandit (tests)...........................................................Passed
complexipy...............................................................Passed
Stage 3 — runtime pass...................................................Passed
```

### Check count — derived, against no stated expectation

The brief states no expected value (§0a). Three independent derivations, reported as found:

```
--- (a) the brief's prescribed command, against the corrected path ---
brief's expression over scripts/verify.py: 1
--- (b) two independent derivations that actually measure it ---
registry.json registered : 8
checks/check_*.py on disk: 8
agree                    : True
--- (c) what verify.py itself executed ---
  8 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
```

**The count is 8.** Derivation (a) is the brief's own §7 expression and it returns **1** — see §5.

### Test count delta

**159 → 159, flat, and the flatness is explained rather than waved past.** Sub-agent A's adapter
driver is a *single* pytest test, so new proofs raise assertions and not the collected count. Its
executed assertions grew **79 → 108** (baseline driver re-run at 92f9f17 in an isolated checkout:
`79 passed, 0 failed`; current: `108 passed, 0 failed`). AST-derived `record()` call sites: 78 → 107.

### Hooks now proven able to say no: 7 of 8 (was 5 of 8)

`ruff-check`, `pylint`, `mypy`, `complexipy`, `bandit (production)`, **`bandit (tests)`**,
**`pytest-affected`**. The eighth, `ruff-format`, is classified a **formatter, not a gate** — see §3.

---

## 2. Sub-agent A — broker-order

**Both hard prerequisites were checked before the work they gated, not alongside it.**

- **A2 prerequisite passed.** Nothing reads the order fetches. The only candidate hit,
  `ibkr_mapping.py:115` naming `IB.reqAllOpenOrdersAsync()`, is a string literal inside a
  `Finding(...)` documentation record; the implementation reads `self._trades[cid].orderStatus`.
- **A3 prerequisite passed.** `_rebuild_mirror()` does **not** depend on `_startup_complete`, so the
  reorder was correct and no separate internal flag was needed. `_connected` stayed at its old
  position because the rebuild needs it; only the gate moved.

**A1(a) — `UP_DATA_LOSS` as a third enum member, not a boolean beside `UP`.** Both options are
prose-free, so the tiebreaker was *what an un-updated consumer does*. A boolean defaults `False`: an
unaware consumer reads a lossy restore as clean `UP` and resumes against state it has no reason to
distrust — the fact is present but **silently ignorable**, which is the defect being removed. A
distinct member makes `state is SessionState.UP` simply `False`. IBKR precedes 1101 with 1100, so
that consumer is already in DOWN and stays there: **it fails toward halted.** Declared as a Nix
addition following the `feed_lag()` precedent; **frozen spec not edited**. Invariant 2 asserted
mechanically — `"1100"/"1101"/"1102"` absent from every session `reason`.

**A1(b) — the adapter re-reconciles before publishing.** Non-vacuity proven by populating the mirror
with a position the venue would *contradict* (`MESU6 +2` in mirror, venue returns `MNQU6 -1`), so the
re-read is observable in contents, not just call count. Ordering proven by an instrument recording
how many session events the sink had received at the instant the venue was queried — not inferred.
A clean restore still does **not** rebuild, so the two paths stay asymmetric.

**A3 — the window is closed, and the plant reproduces the probe's defect end to end:**

```
E  A3: an execDetails injected DURING the mirror rebuild produces NO on_fill
     -> fills 0 -> 1: [('c-window','e-window-1','MESU6',1,7785.0,1)]
E  A3: it produces NO on_ack either — _ensure_acked is not reached
     -> acks 0 -> 1: [('c-window',<AckStatus.ACCEPTED>,'synthesised: fill arrived with no prior ack')]
```

**A2 — resolved `fetchFields`, enum evaluated at run time:**

```
StartupFetchALL     = <POSITIONS|ORDERS_OPEN|ORDERS_COMPLETE|ACCOUNT_UPDATES|SUB_ACCOUNT_UPDATES|EXECUTIONS: 63>
passed after change = <POSITIONS|ACCOUNT_UPDATES|SUB_ACCOUNT_UPDATES: 25>
  EXECUTIONS False · ORDERS_OPEN False · ORDERS_COMPLETE False
  POSITIONS True · ACCOUNT_UPDATES True · SUB_ACCOUNT_UPDATES True
```

Built **up** from the three wanted members, not subtracted from `ALL` — subtraction anchors to a
value that moves, so anything a future `ib_async` adds to `ALL` would arrive switched on.

**An ARC 016 claim is overturned.** "Jointly sufficient, individually insufficient" was wrong twice:
its stated reason no longer exists after A3, **and its symmetry claim was never true even in ARC
016** — it was argued for EXECUTIONS only, while `ORDERS_COMPLETE` replays onto `orderStatusEvent`,
reaching `_ensure_acked`/`on_cancel`. Corrected at all three sites.

**A4 — the asymmetry is deliberate; no new debt.** Six of seven §2A events emit; exactly three are
deduped, and the split is precisely edge-versus-level. `on_cancel` is **not** in the suspected gap and
`on_position` does not need to be. D1.17 left deliberately per §2.5.

**Controls still fail as controls** — driven verdict-by-verdict, not inferred from a green aggregate:
Hollow 9 behavioural failures, working Stub 0, `AwaitDivergent` still names `query_positions`.
`test_seam_simulate.py` byte-identical to baseline (empty diff vs `92f9f17`).

---

## 3. Sub-agent B — gate coverage

**Non-vacuity first.** Scope derived using pre-commit's own `Classifier.filenames_for_hook`, not a
reimplementation: `37/37/37/37/18/19/37/87`, **none zero**. The two bandit hooks partition the
37-file set exactly (18+19) — that cross-check is what makes the claim measured rather than asserted.

| hook | verdict |
|---|---|
| `bandit (tests)` | **CAUGHT** — B602 High/High, `./scripts/tests/test_systemd_units.py:77:4` |
| `pytest-affected` | **CAUGHT**, selection proven — collected **9**, neither 0 (skipped) nor 159 (swept) |
| `ruff-format` | **CAUGHT BUT DID NOT NAME THE SITE** — partial, **not rounded up** |

**`ruff-format` is a formatter, not a gate — and no pass was manufactured.** `ruff format` itself
exits 0 having rewritten the file; the exit 1 comes from pre-commit's before/after tree hash. That
attribution was proven **not causal**: during a concurrent write by another sub-agent, pre-commit
reported `bandit … Failed — files were modified by this hook` though bandit never writes a file. It
names no site, and a second run over the same defect passes because the gate consumed its own
subject. `ruff format --check` was demonstrated as a working reporting configuration (exit 1, sha256
unchanged, names `<file>:1:1`) but adopting it is a behaviour change this arc was not scoped to make.
**D3.5 opened and left OPEN.**

**Three findings beyond scope:**

1. **D2.13 — D2.12 standing in the config today.** A warm `pytest --testmon` prints `collected 0
   items`, `no tests ran`, and **exits 0**. The hook's own comment claimed removing exit-5 tolerance
   closed this; it does not — exit 5 belongs to the deselect path, which testmon's empty run never
   reaches. Compounding it, `.testmondata` is gitignored: an untracked, per-machine,
   reviewer-invisible file sets what the runtime gate measures.
2. **The pre-ARC-010 bandit env is still on disk** in `~/.cache/pre-commit` and still reproduces the
   original defect verbatim (`exception while scanning file` ×18/19, **rc=0**). Only the `rev: 1.9.4`
   pin routes around it.
3. **The `~100 B101 sites` restatement was also wrong** — derived count **318**.

**D3.1 corrected** to name `bandit (production)` as the only hook its ARC 010 plant could have
covered; the second entry became **D3.6**, opened and discharged with its plant inside
`^scripts/tests/`.

---

## 4. Sub-agent C — checks

**`check_order_path_bans.py`.** Both ban classes in one gate, bans as data, scope derived by `rglob`
at run time. FAIL-with-CONTROL run **separately per ban class**, plus a decorator form. It
discriminates code from prose — a docstring containing the literal `run_until_complete` is not
flagged. **Arm (ii) proven not redundant:** a planted `importlib.import_module("backoff")` is
invisible to the AST arm (no `Import` node — the name is a string) and was caught by the subprocess
`sys.modules` arm.

A `__main__`-guarded `asyncio.run` at `seam_simulate.py:525`, **pre-existing at baseline** (verified
against `git show 92f9f17:`), is ADVISORY and printed on every run so it cannot go invisible. That
was a repair to the gate's **logic**, never its scope — the file is not excluded and never will be.
Prohibition 2 scopes the ban to the sync send path; a driver entry point is not on it.

**`check_derived_claims.py` + `derived_claims.json` — D2.8 discharged, open since ARC 010.** Seven
claims, each a set of *commands that compute a number at run time*. **The registry stores no integer
anywhere** — banking "16" beside the claim that §2A has 16 elements would rebuild the exact defect
the instrument exists to catch. Every claim needs ≥2 sources; one source, or two sources that are the
same computation, is CANNOT-MEASURE.

**§2A broker-order = 16**, derived by identifier, with the wrong number's origin reproduced
mechanically: broker-order 15 bullets / **16 identifiers**; **19 bullets across both libraries** — the
19 that survived three arcs; 22 identifiers across both; 23 declared in code (22 + the flagged
`feed_lag` Nix addition).

**The ARC 014 classification re-derived: CLEAN 9, FRICTION 4, GAP 3 = 16.** The banked "19 — 8/7/4"
is wrong in a way worse than the count. Ground truth is `ibkr_mapping.FINDINGS`, which genuinely
holds 19 Findings graded 8/7/4 — but **a Finding is not a verb/event**. `summarise()` prints them
under a column header reading `VERB / EVENT`, and that mislabel is the wound: `"connect / disconnect"`
is one Finding grading two §2A verbs, `"subscribe / on_tick"` grades two *datafeed* elements, and
`"client_order_id mapping"`, `"symbol resolution"`, `"feed_lag"` are not §2A elements at all. **One
judgment call, stated rather than hidden:** `"connect / disconnect"` carries a single CLEAN grade,
propagated to both verbs. All 16 elements graded; zero ungraded.

---

## 5. Defects in the arc brief itself — found by applying §0a, reported not reconciled

§0a banked one instance and asked that the same reading be applied to the rest of the file. It found
five more.

| # | defect | disposition |
|---|---|---|
| 1 | `python` is not on PATH — **every** §7 command fails as written | used `.venv/bin/python` |
| 2 | `verify.py` is at `scripts/verify.py`, not repo root | corrected |
| 3 | **§7's prescribed check-count derivation returns 1, not 6** | replaced with two agreeing derivations |
| 4 | `scratch/instrument/` was already absent | confirmed; **not** created-then-deleted to manufacture a discharge |
| 5 | §9 attributes the series table to `SESSION.md`; it lives in `CHECK-DEBT.md` | routed correctly |
| 6 | §5's premise that ARC 014/015 series rows are missing is stale | ARC 016 reconstructed them; verified no gaps 010–017 — **disk wins** |

**Defect 3 is the significant one.** `scripts/verify.py` contains no check names at all — it loads a
manifest, and registration lives entirely in `checks/registry.json`. The brief's remedy for the
derive-never-restate class was itself an instrument that silently measured the wrong thing, and would
have reported a catastrophic-looking 6 → 1 regression. It is banked as an evidence instance and the
registry carries a verbatim note forbidding its reintroduction.

**A seventh, from A, affecting all future FAIL-with-CONTROL work:** a sha256-identical restore is
**not** by itself evidence that the restored code is what ran. A3's plant is a pure line swap, so
file size is unchanged, and CPython validates `.pyc` on `(mtime, size)` — a rapid plant/unplant
within one shell tick can leave planted bytecode resident behind byte-identical source. It produced a
false red in A's own first pass. Purge `__pycache__` between every step.

---

## 6. Phase 4 — the harness corrected the ledger, twice

Both gates registered in `checks/registry.json` in a new `code-invariants` block, deliberately last
and deliberately **not** `on_fail: halt` — neither is a bootstrap floor component, and a
code-invariant breach must not stop the environment checks that follow from being measured.

Three rows added that A and C owed but were forbidden to write: **D1.18** (an IBKR error integer
still crosses the seam inside `on_ack(reason)` — a genuine tension between invariant 2 and the
declared provenance channel, reported rather than silently decided), **D2.14** (a hand-rolled retry
loop is banned by §2.1 and undetected — a PASS means "no retry *library* and no loop-blocking
*call*", never "nothing retries"), **D2.15** (a new *file* under `scripts/broker/` is covered
automatically; a new *home* is not).

The series row was then **left deliberately stale** to test the new harness. It caught it, unprompted:

```
detail: derived_claims.json:check_debt_open_items: sources disagree
        — derived:ledger_rows=31, stated:series_table_latest_row=28
GATE_EXIT=1
```

Discharging D2.8 itself then removed a row, making the freshly-written 31 stale in turn — **and it
caught that too** (`derived:ledger_rows=30, stated:series_table_latest_row=31`). The row reads **30**
because a machine derived 30. This is the first time in the series that the number was produced by an
instrument rather than asserted by a person, and it closes the loop the ARC 012 note opened.

**Debt 27 → 30** (six opened, three discharged: D2.8, D3.4, D3.6).

**No plants remain.** `git status --porcelain` clean of them, `scratch/` absent, no stray worktrees,
sha256 spot-checks match the sub-agents' reported finals.

---

## 7. D1.17 — left deliberately

Confirmed per §2.5: the double `DOWN` on a requested disconnect was **not** touched. §4 wants an
unrequested drop distinguishable from a requested one, and dropping one event destroys that. A4
independently concluded it is the one genuine residual and that the fix is a Limiter-side
edge-versus-level decision.

---

## 8. Phase 5 — NOT CERTIFIED, known-red `R1-A`

No live confirmation was run and **no 2FA tap was requested**. IB Gateway was up and listening on
4002, but the clock decided it: **15:59 CDT**, one minute from the MES 16:00 CT close and the
maintenance break. Connecting at the session boundary would have produced ambiguous evidence about a
gate re-arm, which is worse than no evidence. **1101 cannot be induced on demand in any case** — the
offline proof is the proof, and is recorded as such rather than implied to be more.

RED withholds certification, not durability. The arc is banked, committed, and pushed.

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.**

---

## 9. Percent moved — each derived, naming what from

- **broker-order: ~13%.** Derived from the §2A roster of **16** elements (machine-derived by
  `check_derived_claims --probe spec_order_identifier_count`): both session-integrity defects the
  ARC 017 probe identified are closed (2/2), and 2/16 = 12.5%. The roster gained no elements and lost
  none; what changed is that the protective path can no longer be confidently wrong. Grade profile is
  now **CLEAN 9 / FRICTION 4 / GAP 3**, re-derived. The 3 GAPs need components that do not exist
  (Limiter, broker-datafeed), so they are not this module's to close.
- **apparatus: ~30%.** Derived from two counts, both pasted: registered gates **6 → 8** (+33%), and
  hooks with a demonstrated can-fail **5/8 → 7/8** (+25 points). D2.8 — the instrument that makes
  every future banked number self-checking — was open across seven arcs and is now discharged.
- **whole project: ~2%.** Derived from the ledger: **3 rows discharged of 37 total** (8% of the
  ledger), scaled down because the ledger covers the *apparatus* only. The trading core — Limiter,
  strategy runtime, broker-datafeed, Crucible — has no rows and no code, so apparatus progress is a
  small fraction of the whole. **This is the honest denominator, not a flattering one.**

---

## 10. Named gaps — what was not proven

1. **No live confirmation.** Offline proof only for A1(b) and A3. 1101 cannot be induced on demand.
2. **Hand-rolled retry loops on the order path are undetected** (D2.14). Banned by §2.1, invisible to
   both arms of the new gate.
3. **A second home for the order path** (D2.15). `ORDER_PATH_DIRS` is the single fix point; no
   mechanical guard.
4. **Dynamic/indirect evasion** inside a function body that never runs at import time is invisible to
   both arms.
5. **Registry coverage** — `check_derived_claims` proves every *registered* number is right; it cannot
   prove the registry covers the numbers that matter. Failure mode #14, inherent to a registry-driven
   instrument, stated beside the gate rather than papered over.
6. **The ARC 014 grade *values*.** The re-derivation pins the roster and the total three ways, but a
   grade *flip* would keep the sum at 16 and pass. Inventing a second source by banking today's
   tallies would be the anchor the gate exists to remove.
7. **`_mirror_stale` has no consumer** — it is observable adapter state, but the Limiter that would
   read it does not exist.
8. **A plant that testmon *skips*** was not constructed. Selection was proven positively; the
   zero-selection green is D2.13 and remains open.
