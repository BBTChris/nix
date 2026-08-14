# RESULTS — ARC CRUCIBLE-DEPSPLIT

CONTRACT: 1.1.0
DATE: 2026-08-14
BRANCH: arc-crucible-depsplit (off arc-crucible-calendar-infra @ 2b9b5a8, per the one-branch-per-arc
convention observed in SESSION.md/CALENDAR-INFRA — no ambiguity requiring a question)

## Bank protocol

This file is `sessions/RESULTS.md`, freshly written this arc. It is copied verbatim to
`downloads/RESULTS.md`, `sessions/SESSION.md` gets an appended summary, then commit -> push,
per A1 and the arc's BANK PROTOCOL section.

## PRE-FLIGHT (A3)

Arc read in full. Every CONFIDENT/INFERRED location grep-verified before any file was touched:
`checks/pinned_deps.json`, `scripts/crucible/generator-requirements.txt`, `scripts/crucible/
calendar_gen.py`, `scripts/tests/test_crucible_calendar.py`, `checks/check_python_deps.py`
(confirmed it compares only the 3 exact pins, no transitive-range logic), current `tzdata`=2026.3,
`ib_async`=2.1.0, `ib_async`'s declared range `>=2025.2,<2026.0` (exact match), the D3.111 row in
`docs/CHECK-DEBT.md`, and the CALENDAR-INFRA baseline (1,496p/1s/2x; verify.py 28/3/2/1) against
the banked `downloads/RESULTS.md` — all VERIFIED, zero NOT FOUND. Two additional pre-flight
findings, both resolved without a question (AUTHORITY delegates the mechanism choice to CC): the
repo has zero existing `uv` usage for dependency management (no lock file, no `[project]`/
`[tool.uv]`, `install.sh` uses raw `pip`); `numpy` in the shared venv is required by both
`exchange_calendars` (calendar-only) and `aeventkit` (`ib_async`'s own transitive dep) — it had to
stay in the runtime set. Zero clarification questions were needed; pre-flight cleared and A6
governed the rest (no confirmation theater, auto-proceed on PASS).

## What was built

**Split mechanism — `uv pip install` into two venvs, no `[project]`/dependency-groups added to
`pyproject.toml`** (repo has none today; this keeps `.venv`'s path and activation exactly as Chris
already uses it — the one AUTHORITY-gated question that would have needed to be asked, avoided by
design):

- **`.venv`** (runtime, `install.sh`-managed, untouched invocation) — `checks/pinned_deps.json`'s 3
  exact pins + new **`checks/requirements-runtime.txt`** (`coverage`, `pre-commit`,
  `pytest-testmon` — previously-installed, previously-UNTRACKED dev tooling `.pre-commit-config.
  yaml`'s local runtime-gate hook depends on; now tracked and `uv`-installed, not ad hoc). Rebuilt
  from scratch (backed up first) via `uv pip install`, never `pip` directly, for this arc's own
  dependency-set change (Success #7).
- **`.venv-dev`** (build-only, new) — `scripts/crucible/generator-requirements.txt`
  (`pandas_market_calendars==5.4.0`, header rewritten to install here, never `.venv`) plus new
  **`scripts/crucible/generator-test-requirements.txt`** (`pytest` — needed only to run
  `test_crucible_calendar_gen.py`, the one file that legitimately imports the generator).

**`scripts/crucible/calendar_gen.py`** — wrong-venv guard added, BEFORE the calendar-library
imports: resolves `sys.prefix` against `.venv-dev`'s absolute path (mirrors `check_venv.py`'s own
pattern) and raises `RuntimeError` naming the exact 3 fix commands on mismatch. A future accidental
`pip install` of the generator dep back into `.venv` (the literal D3.111 mechanism) can no longer
silently half-work.

**D3.111 — RESOLVED, not reported.** Real `.venv` rebuilt from the runtime requirement set alone:
`pip list` carries no `pandas_market_calendars`, no `exchange_calendars`; `tzdata` is now `2025.3`
— back inside `ib_async`'s declared `>=2025.2,<2026.0` (was `2026.3`, outside it). Removing the
calendar-exclusive transitives (`exchange_calendars`, `pandas`, `korean_lunar_calendar`, `pyluach`,
`toolz`) let `tzdata` naturally re-resolve in range; no explicit pin was needed. Proven twice: once
in a disposable venv (Hard Limit #8), then for real in the actual `.venv`.

**`checks/check_python_transitive_deps.py`** — new sibling check (Success #4), `CORRECTABLE =
False` (no single safe automatic repair — could mean pinning the drifted package, widening the
declaring package's requirement, or a human call; `ib_async` is live-broker-adjacent and this check
does not choose on Chris's behalf). Queries the venv's own `importlib.metadata` + `Requires-Dist`
in a subprocess (never imports what it inspects, mirrors `check_python_deps.py`'s §9.4 reasoning),
using `pip._vendor.packaging` for PEP 440/508 parsing (vendored into every venv `python -m venv`
creates — available wherever there's a venv, no new top-level dependency to itself be exempted
from checking). Violations may be reported as a tracked, justified exception
(`checks/transitive_deps_exceptions.json`, matched on the (consumer, dependency, declared_range)
TRIPLE so a stale exception can never silently cover a *different* future drift of the same edge —
hard limit, no blanket skip); the ledger ships empty since D3.111 was resolved, not reported.
Registered in `checks/registry.json` via the sanctioned bootstrap (new checks are orphans until
named once, then `verify.py --optimize --commit` derives placement — not hand-maintained
membership/ordering, just the one-time membership acknowledgment the tool's own orphan gate
requires). 11 tests, including the REAL can-fail Success #4 requires: a disposable venv,
`ib_async==2.1.0` installed normally, then `tzdata==2026.3` force-installed with `--no-deps` —
reproducing D3.111's exact shape — `query_violations()` against that real interpreter detects it,
`evaluate()` returns `FAIL_NEEDS_OPERATOR` naming both packages and both versions. Verified,
restored (disposable venv, nothing shared touched).

**`docs/directory_structure.md`** v1.5.0 -> v1.6.0 — documents the `.venv`/`.venv-dev` convention,
what each holds, and the wrong-venv guard `calendar_gen.py` demonstrates as the pattern for any
future generator (Success #6).

**Astral gates (Success #7).** `ruff check` + `ruff format --check`: clean on every new/changed
`.py` file. `pylint --fail-on=E,F`: 10.00/10. `bandit`: 0 issues. `ty`: `calendar_gen.py` checked
separately against `.venv-dev` (`ty check ... --python .venv-dev`, all clean — `[tool.ty.src]
exclude` added since one project can only resolve one Python environment per invocation); every
other new/changed file shows only the same pre-existing `_preamble`-sys.path-trick unresolved-
import class every sibling `checks/check_*.py`/`scripts/tests/test_check_*.py` already shows
(verified by diffing diagnostic counts against `check_python_deps.py` / `test_check_python_deps.py`
— not a regression this arc introduced).

## Adversarial debug pass (Success #8) — 3 real regressions found and fixed

Both found by the FULL suite run, not a mental walkthrough:

1. **`checks/check_price_ring.py`** — `_SKIP_DIRS` excluded `.venv` but not the new `.venv-dev`, so
   the filesystem sweep flagged `numpy`/`pandas`/`pip`'s own vendored `mmap` use inside
   `.venv-dev/lib/.../site-packages/...` as §12.7 violations. **Fix:** added `.venv-dev` to
   `_SKIP_DIRS`, same stated reason as `.venv`. Re-verified PASS against the real tree; the check's
   own 18/18 tests still pass.
2. **`checks/check_derived_claims.py`** — the `pytest_collected_tests` claim's `source_ast` probe
   (`_p_pytest_ast_count`) counts `test_*` functions purely textually and had no way to know that a
   module-level `pytest.importorskip(...)` collapses pytest's own `--collect-only` tally when it
   fires. Latent since CALENDAR-INFRA wrote `test_crucible_calendar_gen.py`'s `importorskip` guard
   — it never actually fired until this arc's split made `pandas_market_calendars` genuinely absent
   from `.venv`, at which point the two sources (`pytest_collector`=1501 real,
   `source_ast`=1510 stale-textual) genuinely disagreed for the first time, reddening the gate and
   7 of its own plant tests. **Fix:** added `_module_level_importorskip_target()` (top-level-only
   AST scan, never `ast.walk` — a nested guard doesn't run at import time) and
   `_importable_under()` (asks the real `venv_python` via subprocess, mirrors `check_python_deps.
   py`'s never-import-the-target design). Empirically verified, not assumed: a firing
   `importorskip` contributes **0**, not 1, to `--collect-only`'s "N tests collected" line (it
   surfaces as "1 skipped" only in a REAL run's terminal summary, a different count than the one
   `pytest_collector`'s regex reads) — first tried 1, measured 1502 vs the real 1501, corrected to
   0, re-measured exact match. Re-verified: `source_ast` now 1501, matches `pytest_collector`
   exactly; all 16 of the check's own tests pass.

3. **`scripts/tests/test_check_derived_claims.py`** — found while banking, not before: `docs/
   CHECK-DEBT.md` legitimately needed a new series-table row this arc (see below), and its stated
   open count (153) is the SAME as CALENDAR-INFRA's row directly above it (0 opened, 0 discharged).
   `test_the_shipped_gate_reddens_when_a_DOCUMENT_RESTATES_A_WRONG_NUMBER`'s plant located "the"
   row stating the derived count with `re.search` (first match) rather than mirroring the probe's
   own `rows[-1]` (true latest) selection — with two consecutive rows now stating the same number,
   it planted into the earlier, non-latest row, which the probe never reads, so the gate correctly
   saw no disagreement and the test's own `exit_code == 1` assertion failed. **Fix:** switched to
   `re.finditer(...)[-1]`, matching the probe's actual selection, plus an explicit assertion that
   the located row's stated count agrees with the derived value before the plant (so a future
   drift between fixture and probe fails loudly at that assertion, not as a confusing downstream
   mismatch). Re-verified: 16/16 pass.

No other adversarial findings. All three fixes are the A2-authorized in-scope repair for a
regression this arc's own change caused — not scope creep.

## CHECK-DEBT.md

D3.111 marked **RESOLVED IN MECHANISM** in its own row (both halves of its stated discharge path
done: the venv split, and the new transitive-range check), but left counted OPEN — this arc's own
brief is unnumbered like CALENDAR-INFRA's, so `_DISCHARGED`'s numeric-only `discharged ARC \d+`
pattern cannot bind here either, the exact blind spot D3.112 already names. New series-table row
appended: `2026-08-14 | ARC CRUCIBLE-DEPSPLIT | 153 | +0` (zero opened, zero discharged in ledger
bookkeeping terms — the two regressions above were fixed within this arc, not deferred, so neither
opened a new debt row). `check_debt_open_items` re-verified at 153 both sides after the edit.

## Definition of Success — verdicts

1. **Venv split exists and is real. PROVEN.** `.venv` rebuilt from the runtime requirement set
   alone: `pip list` shows no `pandas_market_calendars`, no `exchange_calendars`.
   `test_crucible_calendar.py`: 33/33 passing against that clean venv.
2. **Generator still runs under DEV. PROVEN.** Regenerated under `.venv-dev`:
   `content_hash_sha256=dbb01cc55e2d9f2d66502b769d0211611cbbcc4a4281c0342bfcc91fc53b4f67`, byte-
   identical to the committed artifact.
3. **D3.111 resolved or correctly reported. RESOLVED.** Real `.venv`'s `tzdata` is `2025.3`, inside
   `ib_async`'s declared range. `check_python_transitive_deps` PASSes against the real tree
   (evidence: "0 transitive-range violations ... 0 exceptions active").
4. **Transitive-range check exists and fires. PROVEN.** Correct verdict on the real tree (PASS);
   real disposable-venv can-fail forces `tzdata` out of `ib_async`'s range and the check goes RED,
   naming both packages and both versions — see `test_a_forced_out_of_range_transitive_dep_
   reddens_the_gate`. Restored (disposable venv discarded).
5. **No runtime regression. PROVEN, net-new failures = 0.** Full suite (race-free, sequential with
   verify.py): **1,498 passed, 2 skipped, 2 xfailed** vs baseline 1,496p/1s/2x — the +2 passed nets
   +11 new `check_python_transitive_deps` tests against -9 `test_crucible_calendar_gen.py` tests
   that now collapse into the +1 skip (by design — that file's own docstring anticipated exactly
   this: "needs pandas_market_calendars installed... exactly the two-layer split the arc requires";
   its 9 tests are proven to still pass, 9/9, run separately under `.venv-dev`, so no coverage was
   lost, only relocated). **verify.py: 29 pass | 3 fail | 2 cannot-measure | 0 skipped | 1 guarded**
   vs baseline 28/3/2/1 — the +1 pass is the new check; the same 3 FAIL categories as baseline
   (`check_ibgateway_service`/`check_ibgateway_config`'s downstream `check_observed_resource_
   claims` — Gateway not running, environmental, unrelated; `check_monitor` — harness display,
   unrelated; `check_untracked_attribution` — now also naming this arc's own not-yet-committed
   files, cleared by this arc's own commit below) and the same 1 GUARDED (`check_artifact_gate_
   coverage`, D3.104/CHECK-A8, unrelated, pre-existing). Zero net-new failure categories.
6. **Which-venv is discoverable. PROVEN.** `docs/directory_structure.md` v1.6.0. Wrong-venv
   invocation of the generator fails loudly, naming the fix, rather than half-working.
7. **Astral gates clean. PROVEN** — see above.
8. **Adversarial debug pass complete. PROVEN** — 3 findings, all fixed, symptom/root-cause/fix
   recorded above.

## Actual vs estimated cost

Estimated ~42 min (4 x ~7 min serial instruments + ~14 min check-integration constant). Actual: PRE-
FLIGHT + full build ~1h05m wall clock to this point, dominated by two full-suite runs (~10 min
each) plus the adversarial debug loop the second run's real regressions required — the ~14 min
check-integration constant held roughly for the FIRST check (`check_python_transitive_deps`,
registry bootstrap + full-suite proof), but this arc's dependency-set change ALSO touched two
*existing* checks (`check_price_ring`, `check_derived_claims`) as regression repairs, which the
estimate did not fold in. Correction for a future A5 coefficient: an arc whose dependency-set
change can shift filesystem-sweep or test-count-derivation checks' inputs should budget a second
full-suite-run cycle for the adversarial pass, not assume the first run is clean.

## Final phase self-assert

- [x] A1 bank protocol executed end to end (this file -> copy -> SESSION.md -> commit -> push)
- [x] A3 pre-flight ran; all CONFIDENT/INFERRED locations grep-verified before any file was touched
- [x] A4 every phase boundary left a resumable checkpoint (`sessions/crucible_depsplit_checkpoint.
      json`, 3 revisions across the arc)
- [x] A6 no permission requests issued (zero HALT:QUESTION; pre-flight cleared with 0 questions)
- [x] A8 live status emitted at required cadence (estimated runtime exceeded 15 min)

CONTRACT: PASS
