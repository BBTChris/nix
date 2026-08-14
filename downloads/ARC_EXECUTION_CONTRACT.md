# ARC EXECUTION CONTRACT

**Version:** 1.1.0
**Status:** STANDING — INLINED VERBATIM into every CC arc
**Applies to:** all Claude Code (CC) arcs on Node01 and node02, all platforms (Nix, Titan, successors)
**Owner:** Chris Chapman / BlackBox Trading LLC

---

## 0. PURPOSE

An arc is **atomic**. It runs to a banked verdict, or it halts at a defined checkpoint with a
structured question. There is no third outcome.

This contract exists to eliminate three observed failure modes:

1. Work performed but never banked (verdict lost, history broken).
2. Mid-phase confirmation prompts that stall an unattended run.
3. Hard stops mid-arc with no resumable checkpoint, forcing a restart from zero.

## 0.1 DISTRIBUTION MODEL

Section 9 (INLINE PREAMBLE BLOCK) is copied **verbatim** into every arc .md, immediately after
the arc header and before the Objective. This document is the master; Section 9 is what ships.

- Arcs are self-contained. CC never resolves an external path to learn the contract.
- The preamble carries a version stamp. CC echoes it in `RESULTS.md`.
- On a contract version bump, in-flight arcs keep the version they were drafted with. Do NOT
  edit a live arc (FREEZE WHILE AN ARC IS LIVE).

---

## A1 — COMPLETION IS DEFINED BY THE BANK, NOT BY THE WORK

An arc is **COMPLETE** only when the full bank protocol has executed:

```
append-if-unbanked -> erase -> fresh sessions/RESULTS.md
-> COPY to downloads/RESULTS.md
-> append SESSION.md
-> commit
-> push
```

- A **FAILED** arc that banks its failure verdict is COMPLETE. Failure is a legitimate result.
- An arc that produces working, verified code but never banks is **INCOMPLETE**. The work does
  not count.
- CC MUST NOT end a turn with work performed and nothing written to `RESULTS.md`.
- The bank is the last action of the arc. Nothing follows it.

---

## A2 — ONLY TWO LEGAL STOP REASONS

| Code | Meaning |
|---|---|
| `HALT:QUESTION` | A genuinely blocking ambiguity CC cannot resolve from the repo, the spec, or `grep`. |
| `HALT:GATE` | A hard gate failed and remediation is outside the arc's authorized scope. |

**Hard gates:** `/astral:uv`, `/astral:ruff`, `/astral:ty`, the test harness, Playwright UI
validation.

**Not legal stop reasons.** CC auto-proceeds through all of:

- Token or context pressure (compact and continue).
- Partial confidence in an approach.
- Wanting operator confirmation at a phase boundary.
- "This is taking longer than estimated."
- A minor or mid-tier bug found in the post-write adversarial debug loop (fix it; in scope by
  default).
- Ambiguity that `grep`, the spec, or the repo can resolve. CC MUST attempt resolution before
  declaring `HALT:QUESTION`.

---

## A3 — QUESTIONS ARE FRONT-LOADED

Every arc opens with a **PRE-FLIGHT** pass before any file is touched:

1. Read the arc in full.
2. `grep`-verify every code location marked CONFIDENT or INFERRED. Report each VERIFIED or
   NOT FOUND.
3. Confirm every named input file exists (FILE-DROP VERIFY).
4. Emit **all** clarification questions at once, as a single numbered list.

After pre-flight clears, the arc is **question-free** until completion, except for a true
`HALT:QUESTION`. Every question carries CC's own recommended default so the operator can answer
in one word.

---

## A4 — EVERY PHASE ENDS RESUMABLE

At each phase boundary CC MUST have:

- Taken a BACKUP before any edit in that phase.
- Written phase state to the checkpoint file.
- Appended the phase verdict to `sessions/RESULTS.md`.

An unplanned hard stop — quota exhaustion, crash, network loss, operator interrupt — MUST be
resumable from the last checkpoint. A restart from zero is a contract violation.

Checkpoint state MUST be sufficient to resume WITHOUT the original context: what changed, what
passed, what remains, and the next action. Assume the resuming session has no memory of the run.

The arc header carries a `RESUME:` line naming the checkpoint file path.

---

## A5 — PRE-FLIGHT BUDGET GATE (HARD)

**Operator-side and blocking.** CC cannot query subscription quota; the operator performs this
check before pasting the kickoff.

```
LAUNCH ALLOWED  iff  remaining_weekly_quota_pct >= 1.5 x estimated_arc_cost_pct
```

- ESTIMATED RUNTIME is in the arc header (longest serial chain x ~7 min).
- On gate failure the arc **does not launch**. No partial run, no "start it and see."
- Permitted responses, in order of preference:
  1. Defer until after the weekly reset.
  2. Re-scope to a smaller serial chain that passes the gate.
  3. Enable usage credits so the run cannot hard-stop mid-phase.
  4. Downgrade the execution model, reserving the stronger model for the bank verdict turn.
- The arc header carries a `BUDGET GATE:` line stating the estimate checked against.
- The 1.5x coefficient is provisional. Log actual-vs-estimated cost in `RESULTS.md` per arc and
  tune off real data.

---

## A6 — NO CONFIRMATION THEATER

CC never asks permission to advance past a PASS gate, run the adversarial debug loop, take a
backup, or bank the session. Auto-proceed on PASS is mandatory. The only interactive moments in
an arc are pre-flight questions and a legal `HALT`.

---

## A7 — STRUCTURED HALT OUTPUT

On any halt CC emits exactly this block and nothing else before stopping:

```
HALT: QUESTION | GATE
CONTRACT: <version>
PHASE: <n of m>
CHECKPOINT: <path>
BANKED: yes/no
QUESTION: <single question>
RECOMMENDED DEFAULT: <CC's answer>
```

- One question per halt. Never batch.
- `BANKED: no` is permitted only when the halt occurs before the first phase boundary.
- If `BANKED: no` and any file was modified, CC MUST write partial state to the checkpoint file
  before emitting the halt block.

---

## A8 — LIVE PROGRESS DISCIPLINE

For any arc whose estimated runtime exceeds ~15 minutes, CC MUST emit periodic unbuffered status:

```
[PHASE n/m] <name> | <pct>% | elapsed <mm:ss> | ETA <mm:ss>
```

Elapsed and ETA are read from `date -u`, never estimated from work volume. Silence beyond ~5
minutes during an unattended run is a contract violation.

---

## 9. INLINE PREAMBLE BLOCK

Copy everything between the markers verbatim into every arc .md, immediately after the arc header
and before the Objective.

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

## CHANGE LOG

| Version | Change |
|---|---|
| 1.1.0 | Distribution model set to INLINE-VERBATIM (S0.1 + S9 preamble block added). A4 gains context-free resumability requirement. A5 gains provisional-coefficient note and is marked operator-side-only in the inline block. A7 halt block gains `CONTRACT:` version line. A8 gains `date -u` sourcing. Compliance self-assert folded into the inline block. |
| 1.0.0 | Initial contract. A1-A8 established. A5 budget gate set to HARD, operator-side. |
