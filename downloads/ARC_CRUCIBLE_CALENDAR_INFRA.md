# ARC · CRUCIBLE-CALENDAR-INFRA

**NAME:** CRUCIBLE-CALENDAR-INFRA
**PURPOSE:** Build the calendar infrastructure layer for the Crucible futures strategy evaluation pipeline — a deterministic, network-free, product-group-scoped CME session calendar for 2008–2030, consumed by the corpus builder, fill model, and bar aggregation.
**ESTIMATED RUNTIME:** ~35 min (5 serial measuring instruments × ~7 min)
**RESUME:** `~/nix/sessions/crucible_calendar_checkpoint.json`
**BUDGET GATE:** ~5% weekly quota estimate — LAUNCH ALLOWED iff remaining >= ~7.5%

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

When this arc is done, the Nix repo contains a calendar infrastructure module that answers CME
session questions for the full CME product complex, 2008–2030, with ZERO network dependency and
ZERO nondeterminism at query time. The vendored calendar artifact is the single runtime source of
truth, is content-hashed, and carries generator provenance sufficient to reproduce it exactly.
The corpus builder and fill model (later arcs) can import this module and query it without any
calendar library present in the runtime venv.

---

## DEFINITION OF SUCCESS (measurable, falsifiable, method-agnostic)

The arc succeeds iff ALL of the following are provable:

1. **Two-layer separation proven.** A generator produces the artifact at build time using a
   pinned calendar library; the runtime query module imports NO calendar library and makes NO
   network call. PROOF: uninstall the calendar library from the runtime venv, run the full query
   test suite, all pass. PROOF: static grep of the runtime module shows no import of the
   generator's library and no socket/http/urllib usage.

2. **Determinism.** Generating the artifact twice from the same pinned inputs yields
   byte-identical output (stable sort, no wall-clock in payload beyond the recorded gen-timestamp
   field, which is excluded from the content hash). PROOF: generate → hash → regenerate → hash →
   compare.

3. **Full-complex coverage, product-group-scoped.** The artifact carries distinct session rules
   for at least: equity index, energy, metals, interest rates, agriculturals, FX. A single global
   calendar is a FAIL. PROOF: query `session_bounds` for one representative product per group on a
   date with a known group-specific early close (e.g. a day energy closes early but equity index
   does not) and show they differ.

4. **Span.** Coverage is continuous 2008-01-01 through 2030-12-31 for every product group, with
   no gap days inside declared trading ranges. PROOF: `trading_days` over the full span returns a
   monotonic gap-free sequence per group; count reconciles to expected session count within the
   reconciliation tolerance.

5. **UTC-primary storage.** Every session boundary is stored as a UTC instant, resolved from
   `America/Chicago` wall-clock at generation time with DST resolved. A CT reference column exists
   for audit. Runtime does NO timezone math. PROOF: a DST-transition week (spring-forward and
   fall-back) shows correct UTC offsets (CDT −5, CST −6) with no duplicated or skipped session
   instants; grep runtime module for tz-conversion calls returns none in the query path.

6. **API surface present and behaviorally correct.** All five v1 functions exist and pass tests:
   `is_session_open(product_group, utc_instant) -> bool`,
   `session_bounds(product_group, date) -> (rth_open, rth_close, eth_open, eth_close)` UTC,
   `next_close(product_group, utc_instant) -> utc_instant`,
   `is_early_close(product_group, date) -> bool | override_close`,
   `trading_days(product_group, start, end) -> [dates]`.
   PROOF: test suite exercises each across normal sessions, early-close days, holidays, the Sunday
   open, the daily maintenance break, and both DST transitions.

7. **Reconciliation gate.** Generator output is diffed against CME's published holiday /
   early-close schedule; any row not reconciled fails the build. Pre-2010 non-equity rows are
   flagged HIGH-RISK and source-verified, NOT trusted from library output alone. PROOF: a
   reconciliation report artifact lists every early-close/holiday row with source = LIBRARY |
   CME-VERIFIED | MANUAL, and the build refuses to emit if any row is UNRECONCILED.

8. **Provenance stamp.** The artifact embeds: content hash (of payload excluding the gen-timestamp
   field), generator library name + pinned version, generation UTC timestamp, and the CME source
   document revision/date the reconciliation was performed against. PROOF: a downstream stamp can
   resolve to exact calendar bytes.

9. **Astral gates clean.** `/astral:ruff` and `/astral:ty` clean on all new code; `/astral:uv`
   used for any dependency change (the generator's calendar library is a BUILD/dev dependency, not
   a runtime dependency — prove this separation in the dependency declaration).

10. **Adversarial debug pass complete.** Post-write deep scan run; all major and mid-tier findings
    fixed and documented (symptom → root cause → fix) in the session log. Prefer real-interpreter
    adversarial scenarios over mental walkthroughs.

---

## AUTHORITY

**CC may, unasked:**

- Choose the artifact serialization format (recommend a plain-text, diff-friendly, deterministic
  format — parquet's internal nondeterminism makes it a poor fit for a hash-stable committed
  artifact; justify whatever is chosen).
- Choose the pinned calendar library and version. `exchange_calendars` and
  `pandas_market_calendars` are the obvious candidates; CC evaluates CME product-group coverage
  and picks. Treat any library's pre-2010 non-equity coverage as INFERRED until source-verified.
- Design the module layout, the generator/runtime split, the checkpoint schema, and the test
  harness structure.
- Define the product-group taxonomy and the representative product per group used for testing.

**Needs confirmation (HALT:QUESTION):**

- Any decision that would make the runtime depend on a calendar library or a network call.
- Any decision to reduce group scope below the six named groups or the 2008–2030 span.
- Any settlement-time or maintenance-break convention CC cannot source-verify and would otherwise
  guess.

---

## HARD LIMITS / HALT CRITERIA

- Runtime query path MUST NOT import a calendar library or open a socket. If the only way to pass
  a test is to violate this, HALT:QUESTION.
- Do not fabricate early-close or holiday rows to fill a coverage gap. An unreconciled row fails
  the build (Success #7); it is never silently filled. If reconciliation cannot be completed for a
  span, HALT:GATE with the unreconciled range named.
- Do not guess the CME maintenance break window or settlement times per group — source-verify or
  HALT:QUESTION.

---

## FACTS CC CANNOT DERIVE

- **Platform:** Nix, node02 (Ubuntu 26.04). Repo root `~/nix`. This is a NEW module — no prior
  Crucible calendar code exists (INFERRED — grep-verify in pre-flight; if a partial exists, treat
  it as prior state, do not overwrite blindly).
- **Consumers (future arcs):** corpus builder, fill model, bar aggregation. Design the API for
  them; do not build them here.
- **Determinism mandate:** Crucible carries determinism/provenance stamps (spec F-series). The
  calendar artifact must be a stampable, hash-stable input. This is WHY the two-layer split exists.
- **Product groups (locked this session):** equity index, energy, metals, interest rates,
  agriculturals, FX.
- **Span (locked):** 2008-01-01 → 2030-12-31.
- **TZ (locked):** UTC-primary, DST resolved at generation from America/Chicago, CT reference
  column for audit, no runtime tz math.
- **API v1 (locked):** the five functions in Success #6, signatures as written.
- **Known risk (locked):** library historical coverage thins pre-2010 for non-equity groups —
  those rows are HIGH-RISK, source-verify.
- **Astral toolchain:** `/astral:uv`, `/astral:ruff`, `/astral:ty` are Claude Code skills, invoke
  by name. Not venv packages.

---

## SCOPE FENCE

IN: calendar generator, vendored artifact, runtime query module + its five-function API,
reconciliation gate + report, provenance stamp, test harness, Astral gates, adversarial debug
pass.

OUT: corpus builder, fill model, bar aggregation (future arcs — this arc only makes the calendar
they will consume). Any product-level contract/roll logic. Any live-data wiring.

---

## BANK PROTOCOL

fresh `sessions/RESULTS.md` -> COPY to `downloads/RESULTS.md` -> append `SESSION.md` -> commit ->
push. `RESULTS.md` records `CONTRACT: 1.1.0`, the final-phase self-assert result, the artifact
content hash, the chosen library + version, the reconciliation report summary (rows by source),
and actual-vs-estimated arc cost for A5 coefficient tuning.
