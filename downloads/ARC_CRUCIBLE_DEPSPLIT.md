# ARC · CRUCIBLE-DEPSPLIT

**NAME:** CRUCIBLE-DEPSPLIT
**PURPOSE:** Retire dependency debt D3.111 — introduce a dev/runtime venv split so build-only dependencies (e.g. `pandas_market_calendars`) never install into the runtime venv, AND teach `check_python_deps` to flag transitive-range violations so a future bump that escapes a declared pin's range fails loudly instead of silently.
**ESTIMATED RUNTIME:** ~42 min (4 serial instruments × ~7 min + a ~14 min check-integration constant, per the CALENDAR-INFRA cost lesson)
**RESUME:** `~/nix/sessions/crucible_depsplit_checkpoint.json`
**BUDGET GATE:** ~6% weekly quota estimate — LAUNCH ALLOWED iff remaining >= ~9%

<!-- ===== BEGIN ARC EXECUTION CONTRACT v1.1.0 — INLINE VERBATIM ===== -->

### ARC EXECUTION CONTRACT v1.1.0 (binding)

This arc is **atomic**: it runs to a banked verdict, or it halts with a structured question.
There is no third outcome. Echo `CONTRACT: 1.1.0` in `RESULTS.md`.

**A1 — Completion means banked.** The arc is COMPLETE only when the bank protocol has run end to
end: fresh `sessions/RESULTS.md` -> COPY to `downloads/RESULTS.md` -> append `SESSION.md` ->
commit -> push. A FAILED arc that banks its failure verdict is COMPLETE. Work that is not banked
does not count. Never end a turn with work done and nothing written.

**A2 — Two legal stops only.** `HALT:QUESTION` (blocking ambiguity unresolvable from repo, spec,
or grep) and `HALT:GATE` (hard gate failed, remediation out of scope). Hard gates: `/astral:uv`,
`/astral:ruff`, `/astral:ty`, the test harness, Playwright. NOT legal stops — auto-proceed
through: context pressure (compact and continue), partial confidence, wanting confirmation at a
phase boundary, running long, or any minor/mid-tier bug found in the adversarial debug loop (fix
it; it is in scope). Attempt grep/spec/repo resolution BEFORE declaring `HALT:QUESTION`.

**A3 — Questions are front-loaded.** PRE-FLIGHT before touching any file: read the arc in full;
grep-verify every CONFIDENT/INFERRED code location and report each VERIFIED or NOT FOUND; confirm
every named input file exists; then emit ALL clarification questions at once as one numbered
list. After pre-flight clears, no further questions except a true `HALT:QUESTION`. Every question
carries your own RECOMMENDED DEFAULT.

**A4 — Every phase ends resumable.** At each phase boundary: BACKUP taken before any edit, phase
state written to the checkpoint file, phase verdict appended to `sessions/RESULTS.md`. Checkpoint
state must let a session with NO memory of this run resume correctly — what changed, what passed,
what remains, next action. A restart from zero is a contract violation.

**A5 — Budget gate.** Verified operator-side before launch. Not your responsibility at runtime;
do not re-check it.

**A6 — No confirmation theater.** Never ask permission to advance past a PASS gate, run the
adversarial debug loop, take a backup, or bank. Auto-proceed on PASS is mandatory.

**A7 — Halt output.** On any halt emit exactly this and nothing else:

```
HALT: QUESTION | GATE
CONTRACT: 1.1.0
PHASE: <n of m>
CHECKPOINT: <path>
BANKED: yes/no
QUESTION: <single question>
RECOMMENDED DEFAULT: <your answer>
```

One question per halt, never batched. `BANKED: no` only before the first phase boundary; if any
file was modified, write partial state to the checkpoint first.

**A8 — Live progress.** If estimated runtime exceeds ~15 min, emit unbuffered
`[PHASE n/m] <name> | <pct>% | elapsed <mm:ss> | ETA <mm:ss>`, times read from `date -u`. Silence
beyond ~5 min is a violation.

**Final phase self-assert** — record in `RESULTS.md` as `CONTRACT: PASS` or
`CONTRACT: FAIL <clauses>`:

- [ ] A1 bank protocol executed end to end
- [ ] A3 pre-flight ran; all CONFIDENT/INFERRED locations grep-verified
- [ ] A4 every phase boundary left a resumable checkpoint
- [ ] A6 no permission requests issued
- [ ] A8 live status emitted at required cadence

<!-- ===== END ARC EXECUTION CONTRACT v1.1.0 ===== -->

---

## OBJECTIVE

When this arc is done, build-only Python dependencies cannot install into the Nix runtime venv,
and any future transitive dependency bump that escapes a declared top-level pin's version range
fails a check loudly instead of passing silently. The `tzdata`-out-of-`ib_async`-range condition
recorded as D3.111 is either resolved (runtime venv no longer carries the out-of-range `tzdata`)
or explicitly and correctly reported by the new check as a known, tracked exception. The Crucible
calendar generator runs under the dev venv; the runtime calendar module and all of Titan/Nix
runtime continue to run under the runtime venv with no calendar library present.

---

## DEFINITION OF SUCCESS (measurable, falsifiable, method-agnostic)

The arc succeeds iff ALL of the following are provable:

1. **Venv split exists and is real.** There are two distinct dependency sets: a RUNTIME set and a
   DEV/BUILD set. The calendar generator's library (`pandas_market_calendars` and its transitive
   deps) is in DEV only. PROOF: create/refresh the runtime venv from the runtime requirement set
   alone, `pip list` shows NO `pandas_market_calendars` and NO `exchange_calendars`; the runtime
   test suite (`test_crucible_calendar.py`) still passes 33/33 against that clean runtime venv.

2. **Generator still runs under DEV.** `scripts/crucible/calendar_gen.py generate()` runs to a
   byte-identical artifact under the dev venv. PROOF: regenerate under dev venv → `diff -q` clean
   against the committed artifact, same `content_hash_sha256`.

3. **D3.111 resolved or correctly reported.** EITHER the runtime venv no longer carries the
   out-of-`ib_async`-range `tzdata` (resolved), OR the new transitive-range check reports it as a
   named, tracked exception with an explicit justification (not silently ignored). PROOF: show the
   runtime venv's `tzdata` version and the new check's verdict on it; if reported-not-resolved, show
   the exception is explicit in a tracked config, not a blanket skip.

4. **Transitive-range check exists and fires.** `check_python_deps` (or a new sibling check) now
   inspects the INSTALLED transitive dependency tree against every declared top-level pin's declared
   dependency ranges, not just the three top-level pins. PROOF: with the tree as-is it produces a
   correct verdict; then, in a disposable/simulated resolution, force a transitive dep out of a
   declared range and show the check goes RED (a real failing scenario, run in an interpreter, not a
   mental walkthrough). Restore.

5. **No runtime regression.** The full `scripts/tests` suite and `verify.py` show zero net-new
   failures attributable to this arc versus the CALENDAR-INFRA banked baseline (1,496 passed / 1
   skipped / 2 xfailed; verify.py 28 pass / 3 fail / 2 cannot-measure / 1 guarded, where the extra
   FAIL was the uncommitted-attribution artifact). PROOF: race-free full-suite run + verify.py run,
   diffed against that baseline, net-new failures = 0.

6. **Which-venv is discoverable.** Any future arc that runs a generator can determine which venv to
   use without guessing. PROOF: the convention is documented in `docs/directory_structure.md` (or
   the repo's canonical dep doc) and the generator refuses / warns clearly if run under the wrong
   venv (a runtime-venv invocation of the generator must not silently half-work).

7. **Astral gates clean.** `/astral:ruff` and `/astral:ty` clean on all new/changed code;
   `/astral:uv` used for any dependency-set change. The dev/runtime split is expressed through the
   uv/dependency tooling, not ad-hoc pip calls.

8. **Adversarial debug pass complete.** Post-write deep scan; all major and mid-tier findings fixed
   and documented (symptom → root cause → fix). Prefer real-interpreter adversarial scenarios
   (asyncio.run + pgrep where relevant; here, real venv creation + `pip install` into a disposable
   venv) over mental walkthroughs.

---

## AUTHORITY

**CC may, unasked:**

- Choose the mechanism for the split (uv dependency groups, separate requirement files, uv's
  dev-dependency support — CC picks the one that fits the repo's existing uv usage; justify it).
- Choose whether D3.111 is best RESOLVED (pin/repair the runtime tree so `tzdata` is back in range)
  or REPORTED (tracked exception) — but must state which and why, and prove it either way.
- Decide whether the transitive-range logic extends `check_python_deps` or lands as a new sibling
  check; either is fine if Success #4 is proven.
- Design the disposable-venv test scenario for Success #4.

**Needs confirmation (HALT:QUESTION):**

- Any change to the three existing top-level runtime pins themselves (versions Chris relies on for
  the live broker path — `ib_async` especially). Report/adjust ranges, do not silently re-pin a
  runtime dependency Chris's live trading depends on.
- Any split mechanism that would require Chris to change how he activates or invokes the runtime
  venv for normal Titan/Nix operation.

---

## HARD LIMITS / HALT CRITERIA

- Do NOT silence D3.111 with a blanket ignore/skip to make a check pass. Resolve it or report it as
  an explicit, justified, tracked exception (Success #3). A blanket skip is a FAIL.
- Do NOT re-pin or upgrade `ib_async` or the other live-runtime top-level pins to make ranges
  reconcile — that touches the live broker path. HALT:QUESTION if range reconciliation appears to
  require it.
- Do NOT break the CALENDAR-INFRA two-layer proof: the runtime calendar module must still pass with
  calendar libs absent (Success #1 re-proves this under the new split).

---

## FACTS CC CANNOT DERIVE

- **Platform:** Nix, node02 (Ubuntu 26.04). Repo root `~/nix`.
- **The debt (from CALENDAR-INFRA bank, D3.111):** the repo currently has a SINGLE shared `.venv`;
  installing the generator's dev-only dep transitively bumped `tzdata` to 2026.3, outside
  `ib_async`'s declared `<2026.0` range. `ib_async` still imports cleanly and `check_python_deps`
  still PASSes because it only compares its three declared top-level pins, never their dependents'
  transitive ranges. Nothing broken today; nothing would notice a future breaking bump. (INFERRED
  from the prior bank — grep/inspect the live tree in pre-flight to confirm current `tzdata` and
  `ib_async` versions and the exact declared range before acting.)
- **`checks/pinned_deps.json`** holds the runtime pins; the generator dep was deliberately kept OUT
  of it during CALENDAR-INFRA (INFERRED — verify path/name in pre-flight).
- **`scripts/crucible/generator-requirements.txt`** was introduced by CALENDAR-INFRA for the
  generator-only install (INFERRED — verify).
- **Live-runtime sensitivity:** `ib_async` is on the live broker path. Its pin is not to be moved by
  this arc without explicit confirmation.
- **Astral toolchain:** `/astral:uv`, `/astral:ruff`, `/astral:ty` are Claude Code skills, invoke by
  name.
- **Baseline to diff against:** CALENDAR-INFRA banked suite/verify.py numbers, above in Success #5.

---

## SCOPE FENCE

IN: dev/runtime dependency split mechanism, generator-under-dev-venv wiring, transitive-range check
(extend or new sibling), D3.111 resolution-or-tracked-exception, which-venv documentation +
wrong-venv guard on the generator, tests for all of the above, Astral gates, adversarial debug pass.

OUT: the corpus builder, the fill model (later arcs). Any change to the three live-runtime top-level
pins' versions. Any broker/live-path code. Bar aggregation.

---

## BANK PROTOCOL

fresh `sessions/RESULTS.md` -> COPY to `downloads/RESULTS.md` -> append `SESSION.md` -> commit ->
push. `RESULTS.md` records `CONTRACT: 1.1.0`, the final-phase self-assert, whether D3.111 was
RESOLVED or REPORTED (with the mechanism), the split mechanism chosen, the transitive-range check's
disposable-venv proof result, the suite/verify.py diff vs the CALENDAR-INFRA baseline, and
actual-vs-estimated arc cost for A5 coefficient tuning (this arc's estimate already folds in a
~14 min check-integration constant per that lesson — record whether that correction held).
