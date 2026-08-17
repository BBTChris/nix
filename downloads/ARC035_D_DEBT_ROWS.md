# ARC 035 · SUB-AGENT D — proposed CHECK-DEBT rows (NOT WRITTEN TO THE LEDGER)

**Branch:** `arc-035-d`. **Read this before writing any row.**

**No row here carries a number, and that is the deliverable.** ARC 030 had three sub-agents each
open their own `D3.117` blind, because none could see the others' branches. I cannot see A, B or C.
The integrator assigns numbers **after** all four branches are visible, appends the rows, and then
derives the series figure by the mechanism in §3 below. Nothing in this file is appended to
`docs/CHECK-DEBT.md` by me.

**Row format** (D3 series): `| # | instrument | status | owner | owning module |` — five columns, the
last from the controlled vocabulary at `CHECK-DEBT.md`'s "The controlled vocabulary" table. Owning
module for every row below is `limiter` unless stated.

**Next free numbers as measured on this branch** (`e6775b4` + my commits): **D1.56, D2.42, D3.204**.
D3 is not densely numbered — D3.158–176 are absent entirely — so "highest + 1" is the rule, not
"count + 1".

---

## §1 — ROWS THIS BRANCH OPENS

### R-D1 — the audit that reconciles everything has nothing calling it

> | *(assign)* | **The §11.7 full-scan drift audit is BUILT, DRIVEN and UNSCHEDULED — every public verb of `scripts/nixrisk/drift_audit.py` has zero production callers** | ARC 035 (Stage 1 / D), MEASURED: the only drivers of `DriftAudit.run`, `run_if_due`, `due`, `full_scan`, `classify` and `projection_from_rows` are `checks/check_drift_audit.py` and `scripts/tests/test_check_drift_audit.py`; `rg` over `scripts/` minus `scripts/tests/` finds no other construction of `DriftAudit` | ARC 036+. §11.7 says **periodic** and there is no Limiter run loop in this tree to schedule it from — the same gap `check_uncalled_entry_points`' own run already measures one layer up, where the ONLY non-test construction of `FillHandler`, `ProtectiveFlatten`, `GatePass`, `HaltFlag`, `ColdStart` or `ReservationLedger` anywhere in `scripts/` is a gate or `wal_kill_drill.py`. **The baseline was NOT widened to absorb this and that decision is the row**, exactly as D3.203 refused the same move for ARC 034's own growth. `check_drift_audit`'s evidence prints `UNBOUND (D3.51)` on every run, so a green cannot be read as more than it is. Discharge = the Limiter's event loop calling `run_if_due` on its off-hot-path timer, or an explicit named admission | *(assign)* | limiter |

### R-D2 — two of §11.3's six aggregates have no producer to reconcile

> | *(assign)* | **§11.7 says *every* running aggregate and only FOUR of §11.3's six are reachable from the frozen snapshot — bucket exposure and the net-liq mark are unreconcilable in production today** | ARC 035 (Stage 1 / D), MEASURED against `scripts/nixrisk/seam.py`: `FinancialPicture` carries `balance`, `sum_open_margin`, `sum_reservations` and `positions`, and carries **no** bucket-exposure map and **no** net-liq mark. §11.3:586-587 names all six | ARC 036+. Bucket exposure is priced by `nixalloc.caps`, which does **not** satisfy `drift_audit.BucketPricerPort` as it stands (`dollar_risk(exposure, config)` vs the port's `dollar_risk(symbol, contracts, stop_ticks)`); the net-liq mark is held by `nixrisk.survival`. The audit refuses to score either `drift=0.0`: it reports `measurable=False` with a named reason and `AuditOutcome.complete` False (§17 — *a safety property proven while its subject is unavailable is not proven*), and `check_drift_audit`'s ARM SEVENTEEN plants the withheld producer and requires exactly that. **So the gate drives all six and production can reconcile four.** Discharge = the ~10-line `caps` adapter plus a survival-watch read wired into the audit's caller, or a `SPEC-A<n>` widening of `FinancialPicture` to carry both | *(assign)* | limiter |

### R-D3 — the projection cannot price itself

> | *(assign)* | **`plane1_positions` carries NO margin column, so Σ open margin's ground truth is reconstructed from the RUNNING side's margin cache** | ARC 035 (Stage 1 / D), MEASURED against `databases/schema/plane1.sql` frozen in Phase 0.4: the projection's columns are `trade_id, strategy_id, symbol, side, state, qty_open, qty_filled, avg_entry_price, stop_distance, opened_at, closed_at, last_event_id` — no margin, and `avg_entry_price` is a price, not a requirement | ARC 036+. `drift_audit._scan_open_margin` therefore prices the projection's contract counts with `picture.margin_per_contract`. The QUANTITIES are ground truth and a defect in the running Σ is still visible; a defect **in the margin cache itself** is invisible to this reconcile, because both sides then move together. Declared in the module docstring as the one deliberate exception to its own separation rule rather than hidden. Discharge = either a margin column on the projection (a Phase-0.4 schema decision to re-open, with §9's *"never overwrite"* to respect — the projection is derived, so this is admissible) or a second independent margin source for the scan | *(assign)* | limiter |

### R-D4 — a clean audit and a dead audit look identical

> | *(assign)* | **A drift audit that finds nothing writes to NEITHER plane, so an audit that stopped running is indistinguishable from a healthy book** | ARC 035 (Stage 1 / D), by construction and stated rather than discovered: §11.7 makes the audit event conditional on drift (*"drift ⇒ audit event"*), and `check_drift_audit`'s ARM CONTROL **requires** the silence — a detector that emitted on an agreeing book would fire on everything and would pass every plant arm while discriminating nothing | ARC 036+. The alternative was rejected with a reason: a Plane-1 "audit ran, clean" row is a non-transition in an append-only record of money transitions (§9), and §12.10's inventory has no such event. The honest closure is a **§12.9 liveness alert** on the audit's own cadence — Plane 2, diagnostic, where a missing heartbeat belongs — which this arc does not build. Until then, `DriftAudit.last_run` is the only observable and nothing reads it. Discharge = the §12.9 alert, or an operator-visible staleness surface over `last_run` | *(assign)* | limiter |

### R-D5 — the audit period is not a §12A tunable

> | *(assign)* | **`drift_audit.DriftAudit(interval_s=…)` is a constructor argument with no §12A entry, so §11.7's *periodic* has no single source of truth** | ARC 035 (Stage 1 / D), MEASURED: §12A is the semantic authority for tunables (names, defaults, cross-knob boot validation) and carries no drift-audit interval; `risks/*.json` carries no key for it | ARC 036+. The knob **is** validated at construction against `MIN_INTERVAL_S` and rejects zero, negative and hot-path-frequency values with a `KnobError` (`check_drift_audit` ARM WIRING drives all three), so the boot-validation half of §12A's discipline is met; what is missing is the declared name, the default and the config file it is read from. Deliberately not invented here — a tunable added to a per-module JSON without a §12A entry is a second authority. Discharge = a §12A entry (architect) and the `risks/` key derived from it | *(assign)* | limiter |

---

## §2 — THE FOUR CARRIED CANDIDATES, VERIFIED RATHER THAN ASSUMED

My mandate offered four "if you agree they are real". Each was checked against the tree. **All four are
real and none is covered by an existing row.**

### R-D6 — D3.204 is cited by shipped code and does not exist

**VERIFIED, and it is worse than the mandate stated.** `D3.204` is referenced in **seven** places —
`checks/check_monitor_tui.py:40,174,319` (line 319 emits the id into the check's own CANNOT_MEASURE
defect text, so it reaches an operator's terminal) and `scripts/tests/test_check_monitor_tui.py:60,69,143,154`
— and **zero** places in `docs/CHECK-DEBT.md`. Ledger greps: `\bpty\b` → 0 real hits (32 substring
hits are all "em**pty**"); `TIMING_SENSITIVE` → 0; `monitor_tui` → 0; `resize` → 1 hit, D3.190, an
unrelated §6.5 subject. **The number D3.204 is free** (highest D3 is 203), so the forward reference is
satisfiable exactly as written.

> | D3.204 | **One arm of `check_monitor_tui` is a CLOCK, and the row its own code already cites by number was never written** | ARC 035 (Phase 0.2), MEASURED not assumed: `pty: survives resize storm` fires a burst of `TIOCSWINSZ` ioctls and asserts the child is still painting within a deadline. It passed 5/5 serially and 4/4 under four-way concurrency, and failed ONCE inside a pytest run that was itself under load. `_TIMING_SENSITIVE_PTY_ARMS` names that one arm | ARC 036+. §17 governs and the treatment is already in the shipped gate: the arm is CANNOT_MEASURE under load, **never a PASS and never a FAIL** — a red attributed to the scheduler is as dishonest as a green. Widening ARM 2 to tolerate it was the cheap fix and was refused, because a tolerated failure is invisible and a CANNOT_MEASURE is loud. **What is owed is this row itself:** `checks/check_monitor_tui.py:319` prints `CHECK-DEBT D3.204` into an operator-facing verdict for a row the ledger does not contain, so the citation resolves to nothing. ONE arm is listed because one was observed; `pty: still alive after force probe` is arguably the same class and is deliberately NOT listed — adding an arm on suspicion converts a real future break into a shrug. Discharge = a deadline derived from a measured load envelope rather than a wall clock, or the arm re-expressed as a property that does not race | *(assign)* | verify |

**Note for the integrator:** this row's number is not free to move. Shipped code cites `D3.204` by
name. If another branch has already taken 204, the citation in `check_monitor_tui.py` and its four
test references must be updated in the same commit — the row and the citation are one change.

### R-D7 — the `.venv-dev` copytree class, fixed with no debt recorded

**VERIFIED.** All seven fixtures now carry `.venv-dev` in `shutil.ignore_patterns`
(`test_check_order_path_bans.py:176`, `test_check_python_deps.py:305`, `test_check_verify_logging.py:174`,
`test_check_datafeed_granted_mode.py:83`, `test_check_datafeed_bar_seal.py:76`,
`test_check_derived_claims.py:282`, `test_check_halt.py:48`). `git log -S'.venv-dev' -- scripts/tests/`
returns exactly `e6775b4` (ARC 035 Phase 0) and `a1f75ab` (ARC 030 Stage 2 A). Ledger greps: `tmpfs`
→ 0, `copytree` → 0, `31 G` → 0, `234` → 0; the five `venv-dev` hits are all a different subject
(D3.188 is a *provisioning* gap, the opposite direction). **Check-contract rule 3 is unsatisfied for
`e6775b4`'s seven-file edit: a change written to disk with neither a check nor a row.**

> | *(assign)* | **A full `/tmp` reports as N unrelated test regressions, and nothing gates the scratch-home ignore lists that fill it** | ARC 035 (Phase 0), MEASURED: the first attempt to bank Phase 0 came back `45 failed, 189 errors`, every one resolving to `[Errno 28] No space left on device` on a 31 G shared tmpfs holding 15 G across 27 retained pytest sessions. SEVEN fixtures copied 58 MB of `.venv-dev` each, because `shutil.ignore_patterns` matches EXACTLY and `".venv"` does not match `.venv-dev`; `test_check_halt.py`'s list was `("__pycache__",)` alone and copied both venvs and `.git` besides. Fixed at all seven and re-measured: the same suites now run 83 passed and grow `/tmp` by 0.4 G where they previously grew it by gigabytes | ARC 036+. **The fix is banked; the CLASS is not gated.** Two distinct owed instruments: (1) nothing checks that a scratch-home fixture's ignore list stays complete, and glob exactness means the next `.venv-something` — or a new large gitignored directory — recurs silently; (2) nothing detects a disk-full run, so it presents as **234 failing tests across twenty unrelated subjects, every one of which looks like a regression in whatever arc is running**. `venv_lock.py`'s own docstring already records this blind spot from ARC 030, recurring at a different site. Discharge = a fixture-level ignore-list gate (derived from the tree's large gitignored directories, never a typed roster) plus a pre-flight free-space assertion whose failure names the disk | *(assign)* | verify |

### R-D8 — the exclusions bucket, walked to a fifth arc

**VERIFIED.** `checks/gate_coverage_baseline.json`: `artifacts` is `{}` (Phase 0.2 discharged the four
by real coverage — good), and `exclusions` holds **eight** paths, **every one `owner: "ARC 035"`,
every one `temporary: true`**: `scripts/nixverify/{actuation,contract,engine,loader,optimize,render}.py`
under D3.104/CHECK-A8 and `scripts/nixverify/{gitenv,registry}.py` under D3.138/CHECK-A9. Owner
lineage: ARC 031 → 032 → 033 → 034 → 035.

**D3.104 is OPEN and its own text is stale in three ways** that no instrument can see: it says
*thirteen* artifacts (now eight), names *ARC 030* as owner (now ARC 035), and states *"ARC 030 is
committed as the bulk-retrofit arc: it builds real per-artifact coverage for all thirteen, empties
the exclusion"* — which did not happen. **D3.138 reads DISCHARGED by the bold-span rule while its own
text says the underlying instrument blind-spot is unpaid** and the two exclusions it created are
still live and still being re-owned every arc.

> | *(assign)* | **The `exclusions` bucket has been RE-OWNED FIVE TIMES and the two rows that authorise it have both gone stale in place — one counts thirteen artifacts that are now eight, the other reads DISCHARGED while its own subject is still open** | ARC 035 (Stage 1 / D), MEASURED against `checks/gate_coverage_baseline.json` and `git log` on it: eight paths, all `owner: ARC 035`, all `temporary: true`; owner lineage `ARC 031 → 032 → 033 → 034 → 035` | ARC 036+. **This is not a request to re-open D3.104 or D3.138 — it is the observation that neither can any longer describe its own subject.** D3.104's body says *thirteen* and *"ARC 030 … empties the exclusion"*; the bucket instead walked five arcs and holds eight. D3.138's body carries `**DISCHARGED ARC 031**`, so the derived open-row scan counts it closed, while the same body says *"the row stays open as a debt against the INSTRUMENT, not against the artifacts"* — a sentence the bold-span rule cannot act on. `CLAUDE.md` rule 14's decision to state the mechanism and NOT the count is the right shape and is currently accurate; the ledger rows are the copies that rotted. **`guard_owner_defect` reads the JSON and never these rows**, so nothing reddens on either drift. Discharge = real per-artifact can-fail coverage for the six CHECK-A8 paths (which empties the bucket and closes D3.104 by measurement), plus an architect ruling on whether D3.138's instrument blind-spot is a live row or a closed one — it cannot be both | *(assign)* | verify |

### R-D9 — the cluster is 18.4 and a live control surface says 16

**VERIFIED on the running server**, not from a document: `psql --version` → `psql (PostgreSQL) 18.4
(Ubuntu 18.4-0ubuntu0.26.04.1)`; `select version()` → `PostgreSQL 18.4 … on x86_64-pc-linux-gnu`;
`show server_version` → `18.4`; `pg_lsclusters` → one cluster, `18/main`, online, port 5432. The docx
really does say 16 (*"Validated end-to-end against a live PostgreSQL 16 instance"*, and inside its
embedded SQL, *"-- Validated against PostgreSQL 16."*). Ledger greps: `18\.4` → 0, `Postgres 16` → 0,
`PostgreSQL 16` → 0. `D1.5` is about cluster presence and role separation, not version.

**Partly recorded already, and correctly:** `docs/nix_plane1_schema_spec.md` §4 (added this arc,
Phase 0.4) records the measurement and explicitly refuses to correct the frozen external docx, on
directive-3 grounds. **What is NOT recorded is the live restatement:** `CLAUDE.md:44` carries
`| nix_db_schema_spec.docx | **source of truth** (v1.3.0, validated live against Postgres 16) |` — a
stale figure in the highest-signal control surface in the tree.

> | *(assign)* | **The cluster is PostgreSQL 18.4; `CLAUDE.md` restates "validated live against Postgres 16" and no instrument derives the running version from the running server** | ARC 035 (Stage 1 / D), MEASURED on the live cluster: `psql --version` and `select version()` both report **18.4** (`Ubuntu 18.4-0ubuntu0.26.04.1`); `pg_lsclusters` shows a single online cluster `18/main` on 5432. `nix_db_schema_spec.docx` v1.3.0 says 16 twice, and `CLAUDE.md:44` restates it | ARC 036+. Three separate facts and only the first is closed: (1) the measurement **is** recorded — `docs/nix_plane1_schema_spec.md` §4, this arc — and it correctly refuses to edit the frozen external docx, because restating a frozen document's version in a third file is the drift directive 3 forbids; (2) `CLAUDE.md`'s index line is a **restatement of that stale figure in a live control surface**, which is the D2.41 derive-never-restate class at the highest-signal site in the tree; (3) `validate_schemas.sh`'s 40 checks were validated on 16 and **have not been re-run on 18.4**, so the analytics store's own conformance to the installed server is unmeasured. Discharge = re-run `validate_schemas.sh` against 18.4 and record the result, plus either deriving the version claim in `CLAUDE.md` from the server or removing the parenthetical | *(assign)* | database |

---

## §2B — THREE MORE, MEASURED WHILE BUILDING RATHER THAN LOOKED FOR

### R-D10 — concurrent `pre-commit` across worktrees corrupts the index and fabricates reds

**MEASURED, not inferred.** Three of this arc's four sub-agent worktrees ran `pre-commit` against the
same shared `/home/bbt/nix/.git` at the same time. The run came back `7 failed, 2682 passed` in
25 minutes; **two of the seven were real and five were the concurrency**, and afterwards this
worktree's index showed all 429 tracked files as staged deletions while every file sat untouched on
disk (`git reset` repaired it). All five re-ran clean standalone.

> | *(assign)* | **Concurrent `pre-commit` runs in sibling worktrees of one shared `.git` fabricate test failures and can leave a worktree's INDEX showing every tracked file as deleted** | ARC 035 (Stage 1 / D), MEASURED: with three sub-agent worktrees gating simultaneously, one 25-minute run returned 7 failures of which 5 did not reproduce standalone, and `git status --short` afterwards reported `D` for all 429 tracked paths against an intact working tree | ARC 036+. The affected tests are the ones that read GIT rather than the filesystem — `check_uncalled_entry_points`' ratchet walk, `check_artifact_gate_coverage`'s committed-blob lineage, `check_name_coherence`'s tracked-file scope — because `pre-commit` stashes, and a stash in a linked worktree writes refs into the COMMON directory that another worktree's `git log` can see. **The cost is not the lost run; it is that a red produced by a neighbour is indistinguishable in the log from a red produced by the code**, which is the misattribution class `debug.md` §8 exists for, arriving through the build system instead of through a gate. Discharge = either a lock so one gate runs at a time across worktrees, or an environment stamp in the runtime-gate verdict line naming the other live runs so the reader can see the confound | *(assign)* | verify |

### R-D11 — a non-vacuity floor that the repair it certifies can switch off

> | *(assign)* | **`test_check_artifact_gate_coverage`'s owner-lineage non-vacuity floor was taken over `HEAD`'s `artifacts` bucket, so DISCHARGING the last row turned the arm off** | ARC 035 (Stage 1 / D), MEASURED at pure `HEAD` with all branch files removed: Phase 0.2 discharged the last four `artifacts` rows by real coverage — the correct outcome — leaving `committed["artifacts"] == {}` and `max([])` raising `ValueError` | **REPAIRED on branch `arc-035-d`**, and the row records the class rather than the incident. It was loud (a raise, not a skip) purely because the author wrote `max()` instead of an `if lengths:` guard; the same arm written defensively would have gone GREEN over an empty floor. The repair takes the floor over the COMMITTED HISTORY's row set, which no edit to `HEAD` can empty — the same reasoning that makes `_high_water_mark` a git walk instead of a `previous_count` field. **Left open as a SWEEP:** nothing has looked for the other instances of *"a non-vacuity floor whose population the success case empties"*, and this tree has many floors of exactly that shape. Discharge = the sweep | *(assign)* | verify |

### R-D12 — the uncalled detector attributes a call by receiver type, and an unresolvable receiver moves another module's baseline

**MEASURED and FIXED AT THE CAUSE on this branch, recorded because the mechanism will recur.**
Adding `drift_audit.py` made `check_uncalled_entry_points` report that `reservations.py::LedgerAudit.material`
had ACQUIRED coverage; adding `check_drift_audit.py` did the same to `halt.py::HaltFlag.active`.
Neither was true — `.active` appears **nowhere** in shipped code (`rg '\.active\b' scripts/ --glob
'!scripts/tests/**'` returns nothing). Both came from receivers the gate could not resolve: a
comprehension variable (`r.material`) and a gate-local call. The gate's instruction in that case is
*"tighten the baseline (a ratchet may only shrink)"* — which here would have recorded false coverage
of two genuinely uncalled verbs, in two modules this branch does not touch.

> | *(assign)* | **A new module can move an UNRELATED module's row out of `uncalled_entry_points_baseline.json` by naming an attribute, and the gate's own remedy for that is to delete the row** | ARC 035 (Stage 1 / D), MEASURED by bisection: `scripts/nixrisk/drift_audit.py` alone produced an acquired-coverage FAIL on `reservations.py::LedgerAudit.material`, and `checks/check_drift_audit.py` alone produced one on `halt.py::HaltFlag.active`, while `.active` occurs in no shipped file at all | ARC 036+. `check_uncalled_entry_points` resolves a call site by the RECEIVER'S TYPE and credits an unresolvable receiver to every class carrying that attribute name — deliberately, *"the conservative direction"*, and correct for finding calls. The unintended consequence runs the other way: an unresolvable receiver also removes a row from the baseline, and the verdict text then instructs the author to delete it. **Fixed at the cause here rather than by editing the baseline** — the gate now reads the HALT cause off the audited Plane-1 row (stronger: §12.5:633 is about the audited event) and the module filters through an annotated predicate — but nothing prevents the next module from doing it accidentally. Discharge = an acquired-coverage verdict that names the NEW call site it attributes the coverage to, so a false attribution is visible instead of being actioned | *(assign)* | verify |

### R-D13 — `mypy` and `pylint` had never read `checks/check_uncalled_entry_points.py` at all

**MEASURED and FIXED on this branch, and the mechanism is the interesting part.** The hooks pass
`pre-commit`'s changed-file list to `mypy`. With only `scripts/tests/test_check_uncalled_entry_points.py`
in that list, `import check_uncalled_entry_points` does not resolve — `checks/` is not on the search
path — so the module is silently skipped. Add ANY `checks/*.py` file to the same invocation and it
resolves, and **four type errors and one over-long line appeared in a 1,463-line gate that has been
committed, amended and relied on since ARC 034.** Proven by bisection: `mypy` on the test alone
passes; the same test plus `checks/check_drift_audit.py` fails with four errors, all in
`check_uncalled_entry_points.py` and none in either file that was passed.

All five are repaired here (a container-literal annotation that described one pair instead of a tuple
of pairs, and a loop variable reused across two different AST types).

> | *(assign)* | **A `checks/*.py` module is type-checked only when another `checks/*.py` file happens to be in the same `pre-commit` invocation, so `check_uncalled_entry_points.py` had FOUR unseen `mypy` errors and one unseen `pylint` violation** | ARC 035 (Stage 1 / D), MEASURED by bisection: `mypy --files scripts/tests/test_check_uncalled_entry_points.py` PASSES; adding `checks/check_drift_audit.py` to the same invocation FAILS with four errors, every one of them inside `checks/check_uncalled_entry_points.py`, a file neither invocation was asked to check | ARC 036+. The five defects are repaired on this branch; **the row is about the SCOPE HOLE, not the defects**, and the hole is `debug.md` §8 failure mode #14 arriving through the hook's file list instead of through `.gitignore`: the population a gate reads is a function of what else changed in the same commit. Every `checks/*.py` module that has never shared a commit with another `checks/*.py` module has the same unmeasured status, and nothing reports which those are. Discharge = either `mypy_path`/`files:` configuration that puts `checks/` on the search path unconditionally, or a periodic `--all-files` run whose result is banked; a per-commit file list is not a scope | *(assign)* | verify |

---

## §3 — THE DERIVATION MECHANISM THE INTEGRATOR MUST USE (D3.82)

**Do not type the series figure.** `checks/check_derived_claims.py`'s claim `check_debt_open_items`
runs two probes as separate subprocesses and reddens the gate if they disagree:

- **derived** — `_p_check_debt_open_count`: every line matching `^\|\s*D[123]\.\d+\s*\|`, minus every
  row a **bold span** declares discharged (`\*\*[^*]*\bdischarged ARC \d+`, case-insensitive). The
  bold-span restriction is deliberate: a bare substring scan mis-counted three rows in ARC 018,
  because D2.14/D2.15 read `**NARROWED ARC 018, NOT DISCHARGED.**`.
- **stated** — `_p_check_debt_series_latest`: the LAST `| yyyy-mm-dd | ARC … | <int> |` row **by
  position**, never by arc name (anchoring to a name is the stale-anchor defect the gate exists to
  remove).

**Procedure:**

1. Append every branch's rows to `docs/CHECK-DEBT.md` FIRST — all of A, B, C and D — and only then
   touch the `## Series` table.
2. Derive the figure:
   ```
   python3 /home/bbt/nix/checks/check_derived_claims.py --probe check_debt_open_count --nix-home /home/bbt/nix
   ```
   (integer on stdout; the full open-row id list on stderr, which is the audit trail.)
3. Write **that** integer into the new series row's `open debts` cell. Write the delta prose from the
   same scan, not from memory.
4. Verify:
   ```
   python3 /home/bbt/nix/checks/check_derived_claims.py /home/bbt/nix
   ```
   All 13 claims + 2 demonstrations must be measured; `sources disagree` is the red.

**Measured on this branch before my rows:** `check_debt_open_count` = **211**,
`check_debt_series_latest` = **211**. They agree, so any post-merge disagreement is the merge's.

**Two traps in the same file, flagged not fixed:**

- ARC 034's own series row states `211` in its count column while its prose says *"210 is
  `independent_claims.py`'s own row scan"* — a live instance of the D2.8/D3.82 restated-figure class
  **inside the row that claims derivation**. Do not copy that row's prose shape.
- `scripts/tests/test_check_derived_claims.py:526-527` hard-codes `("broker_order_open_debt_rows", 9)`
  and `("broker_datafeed_open_debt_rows", 7)` — literal restatements of two ledger tally figures,
  inside the suite for the derive-never-restate gate. If any row below is attributed to
  `broker-order` or `broker-datafeed`, the **stated per-module tally** must move too and those two
  literals will go red and read as a regression. None of my rows uses either token
  (mine are `limiter`, `verify`, `verify`, `database`), so my rows do not trip it — but A, B or C's
  might.

---

## §4 — WHAT THIS BRANCH DISCHARGES

**Nothing, and I am not going to manufacture one.** I looked at the plausible candidates:

- **D3.203** (17 uncalled rows in ARC 034's modules) — NOT discharged. It is still red on this branch
  and my own work *adds* to that surface (row R-D1). Its enumeration is also already stale: the armed
  run on this branch reports 19 regression rows, not 17, and includes four `supervision.py` rows and
  `scripts/nixsentinel/config.py::SentinelKnobs.limiter_grace_s` that D3.203 does not list. The
  ratchet high-water is now **177** (baseline tightened 193 → 177 between `87e05a0` and `eae28f8`),
  not the 193 the row records. Worth a one-line correction to D3.203 when the integrator touches it;
  I did not edit an existing row from a branch that cannot see the merged tree.
- **D3.178** (`StopBook.arm` / `PositionOriginWriter.on_fill` uncalled) — measured as **now wired**:
  `fills.py:626` calls `StopBook.arm` and `fills.py:573` calls `PositionOriginWriter.on_fill`, and
  `LimiterFillSink.on_fill` is reached from `scripts/broker/broker_seam.py:1994` and
  `broker_order_ibkr.py:1966,1979`. **That is evidence, not a discharge, and it is not mine to
  claim** — it is not this branch's work, the row is owned elsewhere, and the caveat below bounds it.
- **`halt.PRODUCERS[AGGREGATE_DRIFT]`** — the map's docstring says *"None of them calls this machine
  yet."* `drift_audit.py` calls `HaltFlag.set(AGGREGATE_DRIFT, …)` directly, so that sentence is now
  false for this cause. Handled in code on this branch (see the report), not as a debt row.

**The bound on every "production-called" claim in this arc, stated once:** every production call site
in `nixrisk` is one `nixrisk` module calling another. Nothing **roots** the chain — `rg` for
constructions of `FillHandler`, `LimiterFillSink`, `ProtectiveFlatten`, `SessionFlattener`,
`CrashLoopBreaker`, `GatePass`, `StopBook`, `PositionOriginWriter`, `ReservationLedger`, `ColdStart`
or `HaltFlag` outside `scripts/tests/` returns only `checks/*.py`, and the only non-gate construction
of `Plane1Wal`/`GroupCommitWriter` is `scripts/wal_kill_drill.py`. There is no daemon or `main` in
`scripts/` that assembles the Limiter. `check_uncalled_entry_points` cannot see this, because its
unit of judgement is the SYMBOL and not the object graph. **That is the single largest thing this arc
does not measure, and it is one layer above every row in this file.**
