# RESULTS — ARC CRUCIBLE-CALENDAR-INFRA

CONTRACT: 1.1.0
DATE: 2026-08-14
BRANCH: arc-crucible-calendar-infra (off arc-029-integration, per operator answer at PRE-FLIGHT)

## Bank protocol

This file is `sessions/RESULTS.md`, freshly written this arc. It is copied verbatim to
`downloads/RESULTS.md`, `sessions/SESSION.md` gets an appended summary, then commit -> push,
per A1 and the arc's BANK PROTOCOL section.

## PRE-FLIGHT (A3)

- Arc read in full; inline contract (lines 9-73) verified byte-identical to the standing
  `downloads/ARC_EXECUTION_CONTRACT.md` §9.
- CONFIDENT/INFERRED grep-verification: "no prior Crucible calendar code exists" (INFERRED) —
  **VERIFIED**, no matches for `crucible` in any `.py` file pre-arc.
- Named inputs confirmed present: arc file, contract file, `sessions/SESSION.md`,
  `downloads/RESULTS.md`.
- One clarification question asked (branch strategy — not resolvable from repo/grep given the
  ARC 029/MON-1 branch-collision precedent logged in `sessions/SESSION.md`); operator chose
  "new branch off arc-029-integration." No `HALT:QUESTION` was raised at any point after
  pre-flight cleared.

## Scope note

Two files outside the arc's scope fence were touched: `checks/check_derived_claims.py` and
`scripts/tests/test_check_derived_claims.py`, one line of regex each. Both are the A2-authorized
in-scope fix for a real regression this arc's own commit caused (see Adversarial debug pass #5) —
not scope creep, a bug found in the adversarial debug loop and fixed per the contract.

## What was built

- **Library chosen: `pandas_market_calendars==5.4.0`** (dev/build-only). Evaluated against
  `exchange_calendars`; chosen because it ships CME calendars scoped exactly to the six locked
  product groups (`CME_Equity`, `CMEGlobex_Energy`, `CMEGlobex_Metals`, `CME_InterestRate`,
  `CME_Agriculture`, `CME_FX`), full 2007-2030 coverage confirmed before committing to it, and its
  `regular_market_times` encode real regime-change dates (e.g. the 2012-11-19 CME Globex hours
  extension) rather than a flat assumption.
- **`scripts/crucible/calendar_gen.py`** — build-time generator. Only module allowed to import the
  calendar library. Computes ETH bounds from the library's own UTC-native schedule; RTH bounds from
  a per-group static settlement-window table (WebSearch-corroborated this session — direct
  cmegroup.com fetch timed out twice, recorded rather than silently skipped), capped so an
  early-close day truncates RTH too (a real inverted-window bug found and fixed mid-arc — see
  Adversarial debug pass). Classifies every holiday/early-close row LIBRARY | CME-VERIFIED, with a
  small, explicit, citation-carrying override table (4 rows, from a real 2008 NYMEX press release)
  upgrading specific pre-2010 non-equity HIGH-RISK rows.
- **`scripts/crucible/calendar.py`** — runtime query module. Zero calendar-library import, zero
  network. Implements all five locked v1 functions: `session_bounds`, `is_session_open`,
  `next_close`, `is_early_close`, `trading_days`.
- **`scripts/crucible/calendar_data/`** — vendored artifact: `cme_calendar_sessions.csv` (35,484
  rows), `cme_calendar_reconciliation.csv` (1,433 rows), `cme_calendar_provenance.json`.
- **`checks/check_crucible_calendar.py`** — new verify.py gate (level-0, registered via
  `verify.py --optimize --commit`). Independently recomputes the artifact's sha256 against the
  provenance stamp, statically scans the runtime module for forbidden imports, and drives the
  runtime module's `known_product_groups()` for real.
- **`scripts/tests/test_crucible_calendar.py`** (33 tests) + **`test_crucible_calendar_gen.py`**
  (9 tests) — 42 tests total, all passing.
- **`docs/directory_structure.md`** v1.4.0 -> v1.5.0 (names `scripts/crucible/`); `CLAUDE.md`'s
  specs-table row corrected to match (was stale at v1.3.0, a pre-existing drift from before this
  arc, fixed in the same motion).

## Definition of Success — evidence

1. **Two-layer separation.** PROVEN twice: (a) literal — `pip uninstall`'d
   `pandas_market_calendars`/`pandas`/`exchange_calendars`/their transitive deps from the shared
   `.venv`, ran `pytest scripts/tests/test_crucible_calendar.py` — **33/33 passed** with the
   libraries physically absent, then reinstalled generator-only via
   `scripts/crucible/generator-requirements.txt`. (b) standing/automated —
   `test_runtime_module_works_with_calendar_libs_absent` blocks the libraries via a `sys.meta_path`
   finder in a subprocess on every future run, and `test_static_grep_no_calendar_lib_or_network_import`
   AST-parses `calendar.py` for any import of the library or `socket`/`http`/`urllib`. Both pass.
2. **Determinism.** `calendar_gen.py generate()` run twice, `cme_calendar_sessions.csv` and
   `cme_calendar_reconciliation.csv` byte-identical both times (`diff -q` clean), same
   `content_hash_sha256`. `test_generate_is_deterministic_across_two_calls` holds this standing.
3. **Full-complex, product-group-scoped coverage.** Thanksgiving 2024 (2024-11-28): energy closes
   13:30 CT, equity index 12:00 CT, FX does NOT early-close (16:00 CT normal), agriculturals is a
   full holiday (no session) — four different outcomes, one date, proving distinct per-group rules.
   `test_group_scoped_session_bounds_diverge_on_known_early_close_day` holds this.
4. **Span.** `trading_days()` for all six groups, 2008-01-01..2030-12-31: monotonic, no duplicates,
   first session <= 2008-01-03, last >= 2030-12-30, 240-262 sessions/year average (tolerance band
   around the ~252/year US-futures baseline). Session counts range 5,786 (agriculturals) to 5,945
   (equity_index) across the 23-year span — reconciles to the group's own holiday load.
5. **UTC-primary, DST-correct.** Every artifact row is UTC; the artifact carries a CT reference
   column for audit only. `session_bounds` on the 2024 spring-forward and fall-back weeks shows
   the correct -06:00 -> -05:00 -> -06:00 offset walk with no duplicated or skipped session, and
   the daily maintenance break (16:00-17:00 CT) reads `is_session_open() == False`.
6. **API surface.** All five v1 functions implemented and tested across normal sessions,
   early-close (`is_early_close` returns the actual UTC override close, not a bare `True`),
   holidays (`session_bounds` -> `None`), the Sunday evening session open, the daily maintenance
   break, and both DST transitions.
7. **Reconciliation gate.** Every row in `cme_calendar_reconciliation.csv` carries
   `source in {LIBRARY, CME-VERIFIED}` — never unclassified, enforced by an `assert` in the
   generator itself that would refuse to emit rather than silently pass an unclassified row through.
   102 rows are flagged `high_risk=1` (non-equity, pre-2010). 4 rows (2 dates x 2 groups) are
   upgraded to `CME-VERIFIED` against a real, cited 2008 NYMEX press release
   (cmegroup.com/media-room, fetched via WebSearch this session) — the rest of the HIGH-RISK
   population is left honestly `LIBRARY`-sourced rather than fabricated as verified.
8. **Provenance stamp.** `content_hash_sha256`, generator library + exact version, generation UTC
   timestamp (excluded from the hash), and the CME source reference are all in
   `cme_calendar_provenance.json`. `test_committed_artifact_hash_matches_provenance_stamp` and
   `checks/check_crucible_calendar.py` both independently recompute the hash from the committed
   bytes and compare against the stamp — a hand-edit of either without regenerating both together
   fails loudly.
9. **Astral gates.** `ruff check` / `ruff format --check` clean on all new files. `ty check`
   (run with `PYTHONPATH=scripts:checks`, the same convention the pre-existing `checks/*.py` need
   for `nixverify` resolution) clean on all new files — two real third-party stub gaps
   (`pandas.DataFrame.iterrows()` typed `Hashable` not `Timestamp`; `CustomBusinessDay.holidays`
   absent from stubs) fixed with narrow `typing.cast`, not blanket ignores. The generator dependency
   is deliberately NOT in `checks/pinned_deps.json` (would force it to live in the runtime venv
   forever); see D3.111 below for the one real side effect this caused.
10. **Adversarial debug pass.** See below — four real bugs found and fixed (two in the calendar
    module itself, one a regression in a pre-existing check-contract gate this arc's own commit
    caused, one a coverage gap the pre-commit hook's own full-suite run caught), one real
    environmental side effect recorded as debt, one investigated finding confirmed unrelated to
    this arc.

## Adversarial debug pass

1. **FIXED — inverted RTH/ETH window on early-close days.** The static per-group RTH close
   time-of-day could exceed the session's actual (early) close, producing `rth_close > eth_close`
   — an impossible window. Found on the very first generated row for Thanksgiving 2024 by manual
   inspection, not a mental walkthrough. Fixed: `_rth_bounds` now caps `rth_close = min(rth_close,
   eth_close)` and `rth_open = min(rth_open, rth_close)`. Regression-guarded by
   `test_no_early_close_row_has_close_after_static_rth_and_before_eth_close`, which checks
   `rth_open <= rth_close <= eth_close` over all 35,484 rows.
2. **FIXED — `next_close` could `IndexError` at an exact-close boundary and used the wrong bisect
   side.** Original implementation used `bisect_right` plus a broken fallback branch that indexed
   out of range when `utc_instant` equalled the artifact's last close. Rewritten with
   `bisect_left`, which is both correct and simpler. Regression-guarded by
   `test_next_close_exactly_at_a_close_returns_that_close` and
   `test_next_close_out_of_span_raises`.
3. **FIXED — test-authoring bug, not the module.** An early hand test asserted
   `is_session_open() is False` at 22:30 UTC on 2024-06-03, reasoning from a CST (-6) offset when
   the actual date is CDT (-5) — the module was correct, the test's own arithmetic was off by an
   hour. Fixed to 21:30 UTC.
4. **RECORDED — CHECK-DEBT D3.111.** Installing the generator's dev-only dependency into the
   shared `.venv` (this repo has no dev/runtime venv split) transitively bumped `tzdata` to
   2026.3, printing a real pip resolver warning that it falls outside `ib_async`'s declared
   `<2026.0` range. Measured, not just a warning: `ib_async` still imports cleanly and
   `check_python_deps` still PASSes on this node — nothing is broken today, but nothing in this
   tree would notice if a future transitive bump did break something, since `check_python_deps`
   only compares its three declared top-level pins, never their dependents' transitive ranges.
5. **FOUND, then FIXED — CHECK-DEBT D3.112.** `check_derived_claims`'s `check_debt_open_items`
   probe (`_p_check_debt_series_latest`) required the CHECK-DEBT series table's latest row to
   match `ARC \d+` — every prior arc was numbered, this one deliberately was not (its brief
   withheld a number; the next sequential number, ARC 030, is already D3.104's named owner for
   unrelated work, and reusing it here would misattribute that debt). This arc's own summary row
   couldn't satisfy the probe, producing a real `DISAGREEMENT`. First left RED on the principle
   of not gaming the regex — reversed once the real cost became concrete: `pytest` surfaced
   **seven pre-existing tests failing against the live, unplanted tree**
   (`test_check_derived_claims.py`'s tree-cleanliness suite), which is a genuine regression, not a
   cosmetic mismatch. A2 makes a mid-tier bug found in the adversarial debug loop in-scope to fix
   regardless of whose file it lands in. Fixed: the probe's pattern widened to `(ARC [\w-]+)`.
   Re-verified: `check_debt_open_items=153` both sides, 0 restatements, all seven tests pass.
   CHECK-DEBT D3.112 records the bug (fixed) and is deliberately left counted OPEN: the SEPARATE
   `_DISCHARGED` pattern that would exclude a row from the open count is *also* numeric-only and
   carries its own exact-anchor plant test plus an independently-maintained twin in
   `independent_claims.py` — widening that too was refused as scope beyond what the regression
   required.
6. **FIXED — three new tracked files uncovered by any check's SUBJECTS.**
   The pre-commit runtime-pass hook (a full testmon-escalated suite run,
   triggered because the new files had no fingerprint) failed two
   `test_check_artifact_gate_coverage.py` tests: the real gate returned
   `FAIL_NEEDS_OPERATOR` on `scripts/crucible/__init__.py`,
   `scripts/crucible/calendar_gen.py`, and
   `sessions/crucible_calendar_checkpoint.json` -- three tracked, non-test
   artifacts this arc added that `check_crucible_calendar.py`'s `SUBJECTS`
   tuple hadn't named. Fixed by adding all three; the gate returned to its
   standing GUARDED (D3.104/CHECK-A8) shape and both tests pass. `SUBJECTS`
   proves NAMED, never MEASURED -- `calendar_gen.py` is exercised by
   `test_crucible_calendar_gen.py`, not by this check, exactly as the check's
   own docstring already says of itself.
7. **Investigated, not a regression.** A `verify.py` run mid-arc showed `check_feed_kill_drill`
   CANNOT_MEASURE on `ModuleNotFoundError: No module named 'tenacity'` inside `scripts/capture.py`
   at a line number the file doesn't currently have. Root-caused to a race against this session's
   own concurrently-running full-suite `pytest` process: `test_check_order_path_bans*.py` plants
   `import tenacity` into `capture.py` temporarily to exercise a different gate, and the manual
   `verify.py` invocation caught the tree mid-plant. Confirmed unrelated to this arc's dependency
   changes (`import capture` succeeds cleanly standalone; neither `pandas_market_calendars` nor
   `exchange_calendars` depend on `tenacity`) and confirmed gone on a race-free re-run.

## Repo-wide regression check

Full suite (`scripts/tests`, 1,499 tests after this arc, up from 1,454 in the ARC 029 baseline),
race-free (no concurrent verify.py/plant-test collision): **1,496 passed, 1 skipped, 2 xfailed, 0
failed.**

`verify.py` (default mode, user privilege), race-free run: **28 passed | 3 failed | 2 cannot
measure | 0 skipped | 1 guarded**. This is IDENTICAL in shape to ARC 029's own banked baseline (28
pass / 2 fail / 2 cannot-measure / 1 guarded) plus exactly one additional expected FAIL —
`check_untracked_attribution`, because this arc's files are not yet committed at measurement time;
it lists this arc's own 12 new/changed paths (all headed for this commit) alongside pre-existing,
NOT-this-arc's-doing debris (`.ua/` graphify cache, `scripts/m.sh`) already untracked before this
arc started, both left untouched as out of scope. The two pre-existing FAILs
(`check_ibgateway_service`, `check_monitor`) and two CANNOT_MEASUREs
(`check_ibgateway_config`/`check_observed_resource_claims`, both downstream of the same
unreachable Gateway) are the standing tap-session and concurrent-MON-1-arc debt named in
`sessions/SESSION.md`'s ARC 029 entry, not introduced here. `check_artifact_gate_coverage` is
GUARDED per the standing D3.104/CHECK-A8 exclusion, also pre-existing. `check_crucible_calendar`,
`check_derived_claims`, and `check_feed_kill_drill` (which showed a transient race-condition
CANNOT_MEASURE mid-arc, root-caused and confirmed unrelated — see Adversarial debug pass #6) all
read `[ok]`. **Net new failures this arc introduces once committed: zero.**

## Cost

Estimated ~35 min (5 x ~7 min serial instruments). Actual: **~64 min** (10:11-11:15 UTC), roughly
1.8x the estimate. Not evenly distributed: library evaluation + source-verification (WebSearch
corroboration for RTH conventions and the 2008 NYMEX holiday citation) and the check-contract
registration chain (`verify.py --optimize --commit`, discovering and fixing the D3.112
`check_derived_claims` regression, the CHECK-DEBT ledger consistency work) together cost more than
the core generator+runtime+test build. Two ~10-minute full-suite `pytest` runs (repo-wide
regression proof) also ran serially rather than overlapping with other work in places. None of this
was itemized in the 5x~7min estimate, which priced the calendar-specific build but not the
check-contract integration tax every new module now carries. Logged per A5's request to tune the
coefficient off real data.

## Contract self-assert

- [x] A1 bank protocol executed end to end (this file -> copy to downloads/ -> SESSION.md append ->
      commit -> push, next actions)
- [x] A3 pre-flight ran; the one CONFIDENT/INFERRED location was grep-verified
- [x] A4 — see checkpoint note below (single-phase-boundary arc; no unplanned hard stop occurred,
      so no mid-arc resume was ever exercised)
- [x] A6 no permission requests issued (one PRE-FLIGHT clarification question, which A3 explicitly
      carves out as distinct from a mid-arc permission request)
- [x] A8 live status emitted (`[PHASE n/5]` lines through execution)

**CONTRACT: PASS**

## Checkpoint note (A4)

`sessions/crucible_calendar_checkpoint.json` was written at Phase 1 and never needed a second
write: no unplanned hard stop occurred, so no resume was ever exercised. The arc ran to a single
banked verdict in one continuous session, which is a legal, contract-satisfying shape — A4's
requirement is that a hard stop *would* land on a resumable state, not that one must occur.
