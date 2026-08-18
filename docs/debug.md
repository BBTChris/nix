# DEBUG AND PROOF — OPERATING DOCTRINE

**Version 1.2.0.** Supersedes v1.1.0, which lacked §7.12 — the standing question now required of
every gate at the point it is built. Supersedes v1.0.0 (`71821507…`), which must not be used — it
described two tiers where this protocol has three, omitted PyLint, and graduated rigour only by
*when* you were working rather than by *what you were touching*.

**Audience:** an AI agent writing, reviewing, or verifying code in this codebase.
**Assumes:** nothing. Read it end to end before your first patch.
**Status:** training and reference material. It does **not** supersede any rules file already
installed in the repository; where the two disagree, the installed rule wins and you report the
divergence rather than resolving it yourself.

### What changed in v1.2.0

1. **§7.12 added — the standing question.** *"What would have to be true for this to pass while
   measuring nothing?"* Now required of every new gate, **answered in writing at the point the gate
   is built**. Promoted out of the Nix check-debt ledger (ARC 016) after the seventh recorded
   instance of one failure class. See §7.12 for the evidence base.
2. **Failure-mode #14 added** to the §8 catalogue: *scope set by an external mutable list*.
3. **§9 operating checklist** gains the standing question under the per-instrument block.

### What changed in v1.1.0

1. **Three tiers, not two.** End-of-Module certification (§5) was missing entirely.
2. **Escalation is by surface, not by diff size** (§2.2). A one-line change to an irreversible
   surface takes the heavy path; four hundred lines of dashboard does not.
3. **PyLint added** to the light check alongside Ruff (§3.2), with the reason both are run.
4. **Trigger table** at the front, so a change can be classified in ten seconds without reading
   the doctrine.

---

## TRIGGER TABLE — READ THIS FIRST

| you are… | run | §  |
|---|---|---|
| mid-iteration, recoverable surface | **Tier 1** — Ruff, PyLint, `pytest --testmon` | §3 |
| touching an **irreversible surface**, any size, even one line | **Tier 2** — all five stages, now, not at commit | §4 |
| about to `git commit` | **Tier 2** — all five stages | §4 |
| declaring a module done | **Tier 3** — exhaustive certification | §5 |
| writing or editing **any instrument** | §7 in full, regardless of tier | §7 |
| **building a new gate** | **§7.12 — answer the standing question in writing, beside the gate** | §7.12 |

**The ten-second classification test:**

> **If this change is wrong and reaches production, can a later commit fully undo the damage?**
> **No → IRREVERSIBLE.  Yes → RECOVERABLE.**

Append-only writes, migrations, live orders, payments, credential material, destructive operations,
restore paths, security boundaries, published API contracts → **irreversible**. Dashboards, reports,
internal tooling, docs, styling → **recoverable**.

---

## 0. THE PREMISE

**A passing test suite is not evidence. It is a claim that requires its own evidence.**

This is not a stylistic preference. In this codebase, measured across an extended build, **roughly one
defect in three was found inside the instrument doing the measuring, not inside the code under
measurement.** Concrete instances, all real:

- a can-fail check that had silently stopped perturbing anything three changes earlier — it reported
  the same verdict for the perturbed and unperturbed run, and both were green
- a kill-test that killed a child process which had already committed, so it proved nothing about
  crash-safety while appearing to
- a retention probe structurally incapable of measuring retention
- a boundary gate that returned GREEN when a forbidden host was planted **into its own allowlist**,
  because the allowlist lived in the file under judgement
- a test suite reading 120 passed / 0 failed on **both** a defect and its fix

Every one of those is a **false GREEN**. A false GREEN is worse than a RED, because a RED gets
investigated and a false GREEN gets trusted.

**The doctrine that follows exists to make false GREENs structurally difficult.** Everything else —
the tools, the tiers, the orchestration — is mechanism in service of that.

---

## 1. VOCABULARY

Use these terms precisely. They are load-bearing.

| term | definition |
|---|---|
| **Instrument** | Any code whose output is a verdict: a test, a gate, a check, a harness, a linter configuration. Instruments are code, therefore instruments have defects. |
| **Gate** | A registered instrument whose verdict blocks progress. Exit 0 = PASS, non-zero = FAIL. |
| **Can-fail** | A demonstration that an instrument *is able to return FAIL*. Performed by deliberately introducing the defect the instrument exists to catch, and observing it caught. |
| **Plant** | The deliberate defect introduced for a can-fail. |
| **CONTROL** | The same instrument run against the *unmodified* subject, which must PASS. A can-fail without a CONTROL proves only that the instrument can fail, not that it fails *for the right reason*. |
| **Vacuous pass** | An instrument that returns PASS because it examined nothing. The most common false GREEN. |
| **Non-vacuity check** | An assertion, made *before* any plant, that the instrument's scope actually contains its intended subject. |
| **Proof by absence** | Establishing that a capability does not exist anywhere in a module or import closure, rather than that it is not invoked at a particular call site. |
| **Anchor** | The thing an assertion is pinned to. A *derived* anchor is computed from the subject; a *literal* anchor is written down. Literal anchors go stale silently. |
| **Repair-then-attest** | The rule that the party who fixes a defect is not the party who certifies the fix. |
| **Surface** | What a change touches, classified IRREVERSIBLE or RECOVERABLE. Determines tier. See §2.2. |

---

## 2. THE THREE-TIER MODEL

### 2.1 The tiers

```
  edit ─► TIER 1 ─► edit ─► TIER 1 ─► … ─► git commit ─► TIER 2 ─► … ─► module done ─► TIER 3
          (seconds)                                      (minutes, blocking)            (hours)
                        ▲
                        └── touching an irreversible surface? escalate to TIER 2 immediately
```

- **Tier 1 — light check.** Constant, during iteration. Cheap. Catches obvious breakage without
  slowing the loop. **Recoverable surfaces only.**
- **Tier 2 — commit gate.** At the commit boundary, **and** on any touch to an irreversible surface
  regardless of when. Five stages, all must PASS. Any FAIL **blocks the commit**.
- **Tier 3 — End-of-Module certification.** Once, when a module is declared done. Exhaustive. Asks a
  question neither other tier asks: *is this module actually fit for purpose?*

**Tier 2 does not run on every build.** Running it constantly destroys the iteration loop and trains
you to bypass it, which is worse than not having it. **Tier 3 does not run at commits.** It is a
milestone activity, not a per-change one.

### 2.2 The escalation rule — SURFACE, NOT SIZE

**Diff size is a poor proxy for risk and it fails in the direction that hurts.** *"It's only a small
change"* is one of the most reliable precursors to a production incident. This codebase has the
receipts: **one character** in a grid constraint was wrong for months and silently accepted 20% of the
data it judged; **one config key** held a connection to a production host nobody had ever named; **one
line** in an append-only write path is not a small change. Meanwhile a four-hundred-line dashboard
rewrite is genuinely low-stakes.

**So the rule is:**

> **ANY change touching an IRREVERSIBLE surface takes Tier 2 — regardless of size, and immediately,
> not deferred to the commit boundary.**
> **Changes confined to RECOVERABLE surfaces take Tier 1 during iteration and Tier 2 at commit.**

**Classify in writing before you start**, using the ten-second test in the trigger table. The
classification is challengeable by a reviewer and changed only by an explicit, recorded decision — not
silently, and never after the fact to justify a lighter path already taken.

**When genuinely uncertain, classify IRREVERSIBLE.** The cost of over-classifying is minutes. The cost
of under-classifying is the incident.

---

## 3. TIER 1 — THE LIGHT CHECK

**When:** after every meaningful edit, on recoverable surfaces, during ordinary development.
**Budget:** seconds. If it takes longer than the edit did, it is misconfigured.

### 3.1 Lint and format — Ruff

```bash
ruff check .          # lint
ruff check . --fix    # lint and autofix what is safely fixable
ruff format .         # format
ruff format --check . # verify formatting without writing
```

Ruff is a Rust-implemented linter and formatter that subsumes Flake8, isort, pyupgrade, pydocstyle,
eradicate and most of Black. It is explicitly designed to be used alongside a type checker rather than
instead of one — fast feedback on lint violations, while the type checker gives detailed feedback on
type errors. Configuration lives in `pyproject.toml` under `[tool.ruff]`.

Docs: https://docs.astral.sh/ruff/

### 3.2 Design smells — PyLint

```bash
pylint src/                       # analyse a package
pylint --fail-under=9.0 src/      # gate on the score
pylint --fail-on=E,F src/         # gate on categories regardless of score
pylint --disable=C0114 src/       # disable a specific message
```

**Why both Ruff and PyLint, when Ruff already replaces most linters.** They answer different
questions, and PyLint's own documentation lists Ruff as a tool to run *alongside* it rather than
instead of it.

- **Ruff** is syntactic and rule-based, and extremely fast. It asks: *does this violate a known rule?*
- **PyLint** builds an inference model of the code via `astroid` and reasons about actual values
  rather than trusting annotations — so it catches design-level smells Ruff does not attempt:
  too-many-branches with context, inconsistent return statements, dead code paths, attribute errors on
  inferred types, and cross-module inconsistencies. It is slower for exactly that reason.

In short: **Ruff catches rule violations, PyLint catches bad design.** The second class is what
survives a green Ruff run and shows up later as a defect.

Two mechanics worth knowing: `--fail-under` gates on the aggregate score, `--fail-on` returns non-zero
for specific messages or categories **even when the score is above the threshold** — use `--fail-on=E,F`
so that errors and fatals can never be averaged away by a good score elsewhere.

**⚠ Link warning.** The PyLint project no longer controls the `pylint.org` domain; per their own FAQ,
its current owners serve outdated documentation alongside advertisements. **Use only:**
https://pylint.readthedocs.io/ · https://pylint.pycqa.org/en/latest/ · https://github.com/pylint-dev/pylint

### 3.3 Affected tests only — pytest with testmon

```bash
pytest --testmon           # run only tests affected by the current change
pytest --testmon-noselect  # run all, but update the dependency database
```

`pytest-testmon` maintains a database mapping tests to the source lines they execute, and on each run
selects only the tests whose dependencies changed. This is what makes Tier 1 fast enough to run
constantly.

**Two failure modes you must know:**
1. **A stale or deleted `.testmondata` silently degrades selection.** If test selection behaves
   surprisingly, verify the database exists and is current before trusting a green run.
2. **testmon selects on *executed* lines.** A test that should cover new code but does not execute it
   will not be selected — and its absence looks identical to its passing. Never infer coverage from
   testmon selection.

Docs: https://testmon.org/ · Source: https://github.com/tarpas/pytest-testmon
pytest docs: https://docs.pytest.org/

### 3.4 Tier 1 PASS criterion

**PASS = clean Ruff lint AND clean Ruff format AND PyLint above threshold with no E/F AND all affected
tests green.**

Nothing heavier runs here. No type checking, no security scan, no complexity ceiling, no adversarial
review. Those are Tier 2, and running them here is a configuration error.

---

## 4. TIER 2 — THE COMMIT GATE

**When:** immediately before `git commit` — **or** the moment you touch an irreversible surface, per
§2.2.
**All five stages must return PASS.** Any FAIL blocks the commit until resolved.
**Order matters:** stages 1–2 are analytical and cheap to act on; 3–4 are executional; 5 is the final
sweep. Running 5 first wastes time fixing style in code that stage 2 will tell you to delete.

### STAGE 1 — UltraCode Deep Pass

**What:** deep logic and edge-case analysis over **all changed files**.

**Focus, in this order:**
1. **Boundary conditions.** Every comparison operator is a decision: is it `<` or `<=`? For each,
   state what happens at exactly the boundary value.
2. **Off-by-one.** Any index arithmetic, any range, any window, any count — especially where a count
   and an index are used together.
3. **Unhandled states.** Enumerate the states the code can be in. For each, is there a branch? An
   `else` that "cannot happen" is a state you have not enumerated.
4. **Race conditions.** Any shared mutable state, concurrent access, check-then-act sequence, or
   assumption that two operations are atomic because they are adjacent.
5. **Empty, single, and maximum.** Zero elements, one element, and the largest input this will ever
   legitimately see. Most collection bugs live at zero and one.

**Worked instance from this codebase:** a check-then-act on a resource budget — the check passed, then
a second code path opened the resource without re-checking. Caught by asking *"what happens between
the check and the act."*

**PASS = no unresolved logic defects identified.** *Identified and consciously accepted with a written
reason* counts as resolved. *Not looked for* does not.

### STAGE 2 — UltraReview (Adversarial)

**What:** you argue **against your own code**. Not review it — attack it.

This is a different cognitive posture from Stage 1 and must be performed as one. In Stage 1 you check
whether the code does what it says. In Stage 2 you try to construct an input, a sequence, or an
environment that makes it do something else.

**Attack surface checklist:**
- **Hidden assumptions.** List every assumption not asserted. For each: what happens when it is false?
  Who guarantees it? Is that guarantee enforced, or conventional?
- **Failure modes.** For every external call: what if it is slow? Times out? Returns a partial result?
  Returns success with an empty body? Fails *after* a side effect?
- **Security-relevant logic.** Any value crossing a trust boundary: input parsing, path construction,
  deserialisation, credential handling, subprocess arguments, SQL construction.
- **The gate's own escape.** If what you wrote is an instrument: **can it be made to pass by editing
  something it also reads?** (Real defect here — a boundary gate whose allowlist lived inside the file
  being judged. Widening the boundary took one edit.)
- **What would make this pass without doing anything?** If you can name a way, the instrument is
  vacuous and Stage 2 has failed until it is fixed.

**PASS = no unresolved objections remain.** An objection is resolved by a fix, or by a written
rebuttal that survives re-reading.

### STAGE 3 — Runtime Pass (pytest + pdb)

```bash
pytest --testmon              # affected tests
pytest --testmon --pdb        # drop into pdb at the point of failure
pytest --testmon -x           # stop at first failure
pytest --testmon -x --pdb -l  # first failure, debugger, show locals
```

**`--pdb` is not optional decoration.** A failing assertion tells you the value was wrong. The
debugger at that frame tells you *why* — and that difference is usually the difference between fixing
a symptom and fixing a cause. In `pdb`: `p <expr>` print, `pp <expr>` pretty-print, `l` list source,
`u`/`d` up/down the stack, `w` where, `c` continue.

pdb reference: https://docs.python.org/3/library/pdb.html

**PASS = all affected tests green, with any failure understood at the frame level rather than patched
at the assertion level.**

### STAGE 4 — Workflow Simulation

**What:** trace each pathway end to end, as a real user or upstream system would exercise it. Not unit
behaviour — **whole journeys**.

**Non-visual modules:** simulate at the code level. Drive the real entry point with real inputs
through the real dependencies, substituting only what is genuinely external.

**GUI modules:** drive with Playwright, emulating a real user walking the interface, performing
typical actions, measuring whether the UI is bug-free and fit for purpose.

```bash
pip install pytest-playwright
playwright install     # download browser binaries — required, and easy to forget
pytest --headed        # watch it run
pytest --tracing=on    # produce a trace for failure forensics
```

Playwright Python docs: https://playwright.dev/python/

**Every simulated pathway MUST declare, explicitly, three things:**

1. **Input / preconditions** — the exact starting state
2. **Expected end state** — what should be true when the pathway completes
3. **The observable that proves the end state** — the specific thing you will look at

**If the observable does not match, that pathway FAILS and the gate BLOCKS the commit.**

**The third item is where this stage earns its cost, and where it is most often faked.** *"The function
returned without raising"* is not an observable of an end state — it is an observable of the absence of
one particular failure. Ask: *if the end state silently did not occur, would this observable change?*
If no, you have not declared an observable.

**PASS = every declared pathway's observable matched its expected end state.**

### STAGE 5 — Static Sweep (final gate)

```bash
ruff check .                                   # lint
ruff format --check .                          # format
mypy .                                         # types
bandit -r . -c pyproject.toml                  # security
complexipy . --max-complexity-allowed <N>      # cognitive complexity ceiling
```

**mypy** — static type checking. Strictness is configured, not default; a permissive mypy that passes
everything is a vacuous gate. Configure under `[tool.mypy]`, and treat `# type: ignore` without a
specific error code as a defect. Docs: https://mypy.readthedocs.io/

**Bandit** — security scanner for common Python issues: `subprocess` with `shell=True`, `assert` used
for enforcement (it vanishes under `-O`), insecure temp files, weak hashing, unsafe deserialisation,
hardcoded credentials. Suppressions use `# nosec` and **every suppression must carry a written
reason** — an unexplained `# nosec` is an unreviewed security decision.
Docs: https://bandit.readthedocs.io/

**complexipy** — cognitive complexity, which measures how hard code is for a *human* to follow. Unlike
cyclomatic complexity it accounts for nesting depth and control-flow patterns that affect
comprehension, implementing the Campbell/SonarSource metric in Rust.

```bash
complexipy .                                  # analyse a directory tree
complexipy . --max-complexity-allowed 15      # enforce a ceiling
complexipy . --top 5                          # the five worst functions
complexipy . --failed --suggest-refactors     # deterministic refactor suggestions
complexipy . --diff main                      # fail only on regressions vs a git ref
complexipy . --plain                          # plain text, intended for scripting and agents
```

`--diff` is the correct mode for adopting a ceiling on an existing codebase without a stop-the-world
refactor: it fails only on threshold-breaking regressions relative to a reference. Inline suppression
is `# complexipy: ignore` — **not** `# noqa: complexipy`, because tools like `yesqa` strip unrecognised
`noqa` comments and would silently delete your suppressions.
Docs: https://rohaquinlop.github.io/complexipy/ · Source: https://github.com/rohaquinlop/complexipy

**Two warnings, learned here the hard way:**
1. **Some tools exit 0 when given zero files.** A misconfigured path glob therefore produces a clean
   PASS that measured nothing. Wrap such tools in a script that asserts the file count is non-zero
   before trusting the verdict.
2. **A complexity ceiling written as a literal in a document goes stale.** Reference the measured
   baseline, not a number written down last month. See §7.4.

**PASS = clean across all four.**

---

## 5. TIER 3 — END-OF-MODULE CERTIFICATION

**When:** once, when a module is declared done. Not at commits.
**Budget:** hours. This is a milestone, and it is the only tier that asks whether the module is
actually *good*, as opposed to merely *not visibly broken*.

**Nothing in Tiers 1 and 2 asks that question.** They ask whether this change broke something. A module
can pass every commit gate it ever faced and still be unfit: correct on the inputs anyone thought to
try, wrong at the scale it will actually meet, and undefined at its own boundaries.

### 5.1 Real-world workflow traversal

**Drive the module the way the real world will**, end to end, through its real entry points, with
realistic data volumes and realistic sequencing — not fixtures chosen to be convenient.

Every traversal declares the same three things Stage 4 requires: **input/preconditions · expected end
state · the observable that proves it.** The difference is scope: Stage 4 proves a pathway works;
Tier 3 proves the *module* works, across its pathways, in combination, in the order a real caller
would use them.

**Include the sequences nobody designs for:** the same operation twice, operations interleaved, an
operation retried after a partial failure, a caller that abandons midway.

### 5.2 Fit for purpose

State what the module is **for**, in one sentence, then demonstrate it does that — not that its
functions return correct values.

Ask explicitly: **is there a real workflow this module makes harder than it should be?** A module can
be entirely correct and still be wrong for its job. This is the only tier where that finding is in
scope, and it is a legitimate certification failure.

### 5.3 Bounds checks

For every input, parameter and buffer, establish and test the actual limits:

- **minimum** — zero, empty, null, the smallest legal value
- **maximum** — the largest legal value, and the first illegal one
- **just inside and just outside** each boundary, both sides
- **what happens beyond** — clean rejection, or undefined behaviour? *Undefined is a certification
  failure, not a finding to note.*

### 5.4 Scale concerns

**Measure, do not extrapolate.** Run the module at the volume it will actually see, and at an order of
magnitude beyond it.

- **Throughput** — measured, with the number recorded
- **Degradation shape** — does cost grow linearly, or quadratically? Find out where the curve bends
- **Resource growth** — memory, file handles, connections, locks. Anything per-item that is not
  released is a leak that only appears at scale
- **Concurrency** — behaviour with N callers, not one

**Real incident from this codebase:** a write path measured 47 rows/second and was assumed adequate.
Measured properly against real volume, it implied ~98 days for the full workload. Rebuilt, it reached
~11,900 rows/second. **Nobody knew until someone measured at scale** — and the redesign then
invalidated a crash-safety test whose timing window no longer bit, which is failure mode #6 in §8.

### 5.5 Corner cases

Enumerate deliberately; do not wait to encounter them:

- empty input, single-element input, all-identical input, already-sorted input
- duplicate keys, unicode, embedded nulls, very long strings
- boundary timestamps: epoch, DST transitions, leap seconds, year boundaries, week boundaries
- concurrent identical requests
- the operation performed twice — **idempotence is a property, and it must be proven, not hoped for**
- failure injected at each external call, including failure *after* a side effect

### 5.6 Full static sweep

The complete Stage 5 sweep over the **whole module**, not just changed files — plus the full test
suite, not the affected subset:

```bash
pytest                                 # everything, not --testmon
ruff check . && ruff format --check .
pylint --fail-on=E,F <module>
mypy <module>
bandit -r <module>
complexipy <module> --max-complexity-allowed <N>
```

### 5.7 Instrument audit

**Every instrument covering this module is re-verified against §7 before certification.**

This is the step most likely to be skipped and the one most likely to pay. Instruments written many
changes ago have had many opportunities to go stale, and a module certified on stale instruments is
certified on nothing.

For each: non-vacuity asserted, can-fail re-demonstrated, CONTROL clean, no literal anchors.

### 5.8 Tier 3 PASS criterion

**PASS = every workflow traversal's observable matched · bounds defined and enforced at every edge ·
scale measured with numbers recorded · corner cases enumerated and handled · full static sweep clean ·
full suite green · every covering instrument re-verified.**

**A module is not certified because nothing failed. It is certified because the things that would have
failed were tried.**

---

## 6. ORCHESTRATION

Wire Tier 2 into the `pre-commit` framework so it fires automatically on `git commit` and blocks on
any failure. Tier 1 you run during iteration. Tier 3 is invoked deliberately at a milestone.

```bash
pip install pre-commit
pre-commit install            # install the git hook — REQUIRED, this is the step people skip
pre-commit run --all-files    # run every hook over the whole tree
pre-commit autoupdate         # bump pinned hook revisions
```

Framework docs: https://pre-commit.com/

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.0
    hooks:
      - id: ruff-check
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pylint-dev/pylint
    rev: v4.0.6
    hooks:
      - id: pylint
        args: ["--fail-on=E,F"]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.18.2
    hooks:
      - id: mypy

  - repo: https://github.com/PyCQA/bandit
    rev: 1.8.6
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]

  - repo: https://github.com/rohaquinlop/complexipy-pre-commit
    rev: v3.0.0
    hooks:
      - id: complexipy

  - repo: local
    hooks:
      - id: pytest-affected
        name: Stage 3 — runtime pass
        entry: pytest --testmon
        language: system
        pass_filenames: false
        always_run: true
```

**Pin every `rev`.** An unpinned hook means your gate changes without a commit, which makes a green
run unattributable. Bump deliberately, and treat the bump as a change that itself goes through Tier 2.

**On `--exit-non-zero-on-fix`:** without it, a hook that autofixes returns success and the commit
proceeds with files modified after staging — a silent divergence between what you reviewed and what
you committed.

**On PyLint in pre-commit:** it needs your project's imports resolvable, so it usually belongs as a
`local` hook running in the project environment rather than pre-commit's isolated one. If PyLint
cannot import your dependencies it degrades to near-silence, which is a vacuous pass.

**Bypassing.** `git commit --no-verify` exists. Using it converts an enforced gate into an honour
system. If you use it, say so in the commit message and open a follow-up — an undisclosed bypass is
indistinguishable from a gate that never ran.

**Stages 1, 2 and 4, and all of Tier 3, are analytical and cannot be fully automated.** You perform
them, and you write down their conclusions. **A stage whose only output is a feeling did not run.**

---

## 7. THE PROOF DISCIPLINE

The tiers are mechanism. This is the doctrine, and it is what actually prevents false GREENs. **These
rules apply at every tier, above and beyond it.**

### 7.1 Every instrument must be demonstrated able to FAIL, with a CONTROL

1. Plant the exact defect the instrument exists to catch.
2. Run it. **It must FAIL, and the failure must name the planted site.** A generic failure is weak
   evidence — it may be failing for an unrelated reason.
3. Remove the plant. Run against the unmodified subject — the **CONTROL**. It must PASS.
4. Record both results.

**Both halves are required.** A can-fail without a CONTROL cannot distinguish *detects the defect* from
*always fails*. A CONTROL without a can-fail cannot distinguish *correct* from *blind*.

### 7.2 A plant never touches a production artifact

Plants go in scratch copies, scratch trees, throwaway branches, temporary tables.

**Real incident:** an append-only datastore had a synthetic row planted into it to prove a detector
could fire. The detector worked. **The row was permanent, could not be superseded, and remains in the
production dataset.** The instrument was right; the method was wrong.

### 7.3 Prove non-vacuity before you prove anything else

**Before any plant, assert that the instrument's scope contains its intended subject.**

**Real incident:** a rule was added to a scanner whose existing rules were all scoped to one subsystem.
The new rule inherited that scope and was structurally incapable of seeing the file it was written
about. It would have passed forever.

```python
assert TARGET in instrument.scope(), (
    "instrument cannot see its subject — verdict is vacuous"
)
```

### 7.4 Never anchor an assertion to something that moves

**The most persistent defect class in this codebase — five independent instances, no two caught the
same way.**

| bad anchor | why it rots | good anchor |
|---|---|---|
| a hardcoded list of files | a later change adds a file; the check silently stops covering it | derive the list from the tree, or from one declared source |
| `assert count(*) == 0` | true only while the store is empty; passes forever afterward for the wrong reason | assert the invariant, not the current value |
| a literal ceiling copied into a doc | the real value drifts | reference the measured baseline |
| a specific spelling in an error message | refactor changes the wording | assert on the error type or code |
| a fixture pinned to a stale inventory | the inventory grew | regenerate the fixture from the subject |

**Rule: if an assertion contains a literal describing the current state of the world rather than the
invariant, it will go stale, and it will go stale silently.**

### 7.5 Repair and attestation are performed by different parties

The party that fixes a defect does not certify the fix. In an agent context: a separate context, a
separate pass, or a separate agent — one that has not seen the reasoning that produced the patch and
therefore cannot inherit its blind spot. Applied consistently here, **this found a further defect
nearly every time it was used.**

### 7.6 Prove by absence, not by call-site guard

Scan the **module or import closure** for the capability itself, not the places it might be invoked.

- **Weak:** "no call site passes a live host."
- **Strong:** "the live host is not reachable from the runtime import closure at all."

**Real incident:** a fix was applied to the one file everyone knew about. Proof by absence found **a
second file holding a live host nobody had ever named.** A call-site guard would have produced a clean,
wrong PASS. Absence is visible; discipline is not.

### 7.7 Compare verdict-by-verdict, never in aggregate

**Real incident:** a refactor preserved the *set* of outputs but changed their *order*. An aggregate
comparison — same count, same membership, still green overall — passed it. Verdict-by-verdict caught
it immediately. *"Still green overall"* is the aggregate that hides the swap.

### 7.8 Baseline everything that can be RED, on a pristine tree

Before changing anything, record the state of **every** instrument that could report a failure — not
just registered gates: ad-hoc harnesses, the lint gate, everything.

**Two real incidents:** two instruments were already failing before work started, and without a
baseline those failures would have been attributed to the change; and a baseline taken *while an edit
was in flight* nearly recorded a self-inflicted failure as pre-existing. **A baseline taken while the
tree is moving is not a baseline.**

### 7.9 Fail closed, and fail loud

Distinguish, in the output: **PASS** (measured, satisfied) · **FAIL** (measured, violated) · **CANNOT
MEASURE** (the instrument did not run correctly).

**Real incident:** a gate shelled out to a subprocess. The subprocess timed out. The exception type was
not caught, the interpreter exited 1 — **the same exit code the gate uses for "violation detected"** —
and the gate was recorded as reporting a violation while having measured nothing. Use a distinct exit
code for CANNOT MEASURE.

### 7.10 One owner per shared global measurement

If several parallel work-streams each measure the same tree-wide property — total lint state, total
complexity, total gate status — the results are unattributable. **Exactly one owner per shared global
measurement per unit of work.** Parallelism is licensed by disjoint file sets, not by independent
objectives.

### 7.11 Grade proof intensity by irreversibility

Uniform maximum rigour everywhere is itself a defect: it spends the proof budget where being wrong is
cheap, and it trains people to treat the ceremony as noise. This is the same axis §2.2 uses to select
a tier — **IRREVERSIBLE gets the full treatment; RECOVERABLE gets Tier 1 plus targeted proofs where it
touches an irreversible seam.** Classify in writing, before starting.

---

### 7.12 THE STANDING QUESTION — answer it in writing, at the point the gate is built

**Of every gate, before it is trusted, ask:**

> ### *What would have to be true for this to pass while measuring nothing?*

**Write the answer down where the gate is defined.** Not in an arc report, not in a commit message,
not in the reviewer's head — beside the gate, where the next person to edit it will read it. A gate
whose vacuity conditions are undocumented is one refactor away from meeting them silently.

This is the inverse of §11's question and the two are complementary. §11 asks *what would have made
this fail* — it interrogates a **result**. §7.12 asks what would let the gate pass **having examined
nothing** — it interrogates the **instrument's scope**. A gate can answer §11 convincingly and still
be reading zero files.

#### Why this is a principle and not a caution

**It is this project's characteristic failure mode.** Seven independent instances are on record, no
two found the same way, and every one was a green light that measured nothing:

| # | instance | what it measured | how it stayed green |
|---|---|---|---|
| 1 | `bandit` scanning nothing since ARC 006 | 0 of 27 files | 1.8.6 died per-file on Python 3.14, recorded "exception while scanning file", and **exited 0** |
| 2 | `CHECK-DEBT` series hand-miscounted, **twice** | a number the table already determines | prose restating a derived fact; nothing compared the two |
| 3 | the 10-minute feed delay sitting unread in ARC 010's **own output** | it was measured and printed | nobody asserted on it, so the value was produced and discarded |
| 4 | `check_structural_conformance` passing `async` against a **sync**-declared port | method presence only | `callable()` is true for `async def` too — right shape, un-awaited coroutine returned |
| 5 | `avg_price` invisible to a polite `FakeIB` | per-unit vs notional | the fake had no `multiplier`, so both units were **numerically identical** |
| 6 | `pre-commit run --all-files` over `scripts/broker/` | all *git-tracked* files | the files were **untracked**, so the gate's scope silently excluded them |
| 7 | an **order** sink passed into the **datafeed** port | nothing | invariant 3 says the contracts are disjoint; no feed event was ever driven through it |

Read the right-hand column as a set. These are not seven unrelated mistakes — they are seven ways of
arriving at the same place: **the instrument ran, the instrument was green, and the subject was never
in scope.** Instances 1 and 6 are scope defects, 4 and 5 are representational defects (the instrument
could not *express* the difference it was asked to detect), 2 and 3 are measurement-without-assertion,
and 7 is a type error that only a behavioural drive would surface.

**A run of one is luck. A run of seven is a mechanism.** Treat any new gate as belonging to this
family until its answer to the standing question is written down.

#### The eighth, found by applying it

ARC 016 added a pytest control asserting `HollowBrokerOrder` still fails behaviourally. It passed.
Driven against a *working* adapter it **also** passed — because the adapter emitted into one
`RecordingSink` while the assertions read a different one, so the suite was observing a sink nothing
had ever written to. It would have stayed green through the exact regression it existed to catch.
Caught within minutes by a can-fail run, i.e. by asking the standing question of a brand-new gate
rather than of an old one. **The discipline pays on first use, not eventually.**

#### What a written answer looks like

Name the specific conditions, in a form you could plant:

- ✅ *"Passes vacuously if `git ls-files` stops returning `scripts/broker/` — i.e. if the files are
  untracked. Non-vacuity is asserted by listing the scope before the plant."*
- ✅ *"Passes vacuously if the fake's `multiplier` is absent or 1, because notional and per-unit
  coincide. The fake therefore carries a real multiplier."*
- ❌ *"Thoroughly tested."* — names no condition, so it cannot be planted, so it was not answered.

**If you cannot name a condition, you have not examined the gate — you have admired it.**

## 8. FAILURE-MODE CATALOGUE

Every entry is a real defect found in this codebase, and each initially looked like a defect in
something else.

| # | failure mode | tell |
|---|---|---|
| 1 | Instrument stopped perturbing | Same verdict for plant and control |
| 2 | Vacuous scope | Instrument passes having examined zero files |
| 3 | Self-approving gate | The allowlist lives inside the file under judgement |
| 4 | Stale literal anchor | Assertion references a coordinate that has since moved |
| 5 | Aggregate comparison | Order, sequence, or attribution changes pass unnoticed |
| 6 | Timing-invalidated test | The subject got faster; the test's timing window no longer bites |
| 7 | Non-repeatable harness | Passes on first run, no-ops on second, still reports PASS |
| 8 | Import-shadowing plant | Two `sys.path` insertions; the plant sits behind the real module |
| 9 | Unreached branch | The "impossible" `else` was the actual path |
| 10 | Exit-code collision | CANNOT MEASURE indistinguishable from FAIL |
| 11 | Silent refusal | Correct rejection with no observable |
| 12 | Environment-shaped result | A proof taken in one environment presented as a claim about another |
| 13 | Under-classified surface | An irreversible change took the light path because the diff was small |
| 14 | Scope set by an external mutable list | The gate reads its file list from something a person edits — a tracked-file set, an allowlist, a registry — so *omitting* the subject silences it without touching the gate |

**On #12:** record the environment that produced every result *in the evidence itself*. A proof taken
against a simulator is not a proof about production, and by the time that matters the narrative will
not be nearby.

**On #13 — new in v1.1.0.** This is the failure mode §2.2 exists to prevent, and the one most likely to
be committed deliberately, under time pressure, with a good reason.

**On #14 — new in v1.2.0.** Distinct from #2 (vacuous scope) in *where the defect lives*: in #2 the
gate is misconfigured, in #14 the gate is configured exactly as intended and the **list it consults**
is what moved. Nothing about the gate looks wrong, and no diff to the gate ever appears. The measured
instance is §7.12's #6 — `pre-commit run --all-files` means all *git-tracked* files, so two arcs of
code sat inside the repository, outside the gate, under a permanent green. **Naming the path in the
invocation is not the repair; putting the subject in the list the gate derives its scope from is.**

---

## 9. OPERATING CHECKLIST

**Before your first change:**
- [ ] Classify the surface: IRREVERSIBLE or RECOVERABLE. **Write it down.**
- [ ] Baseline every instrument that can report a failure, on a pristine tree
- [ ] Record the baseline; your results will be read against it

**During iteration — Tier 1, recoverable surfaces:**
- [ ] `ruff check . --fix && ruff format .`
- [ ] `pylint --fail-on=E,F <module>`
- [ ] `pytest --testmon`

**Touching an irreversible surface — Tier 2 now, regardless of size:**
- [ ] All five stages below, before continuing — not deferred to commit

**Before `git commit` — Tier 2, all five in order:**
- [ ] **Stage 1** — boundaries, off-by-one, unhandled states, races, empty/single/max
- [ ] **Stage 2** — argue against your own code; name hidden assumptions; try to make it pass vacuously
- [ ] **Stage 3** — `pytest --testmon --pdb`; understand failures at the frame, not the assertion
- [ ] **Stage 4** — every pathway declares input, expected end state, and the observable that proves it
- [ ] **Stage 5** — `ruff` + `mypy` + `bandit` + `complexipy`, all clean

**Declaring a module done — Tier 3:**
- [ ] Real-world workflow traversals, including the sequences nobody designs for
- [ ] Fit for purpose — stated in one sentence, and demonstrated
- [ ] Bounds defined and enforced at every edge; nothing undefined beyond them
- [ ] Scale **measured** at real volume and 10×, with numbers recorded
- [ ] Corner cases enumerated deliberately; idempotence proven, not hoped for
- [ ] Full static sweep and **full** suite over the whole module
- [ ] **Every covering instrument re-verified against §7**

**For every instrument you wrote or touched, at any tier:**
- [ ] **§7.12 — the standing question answered IN WRITING, beside the gate:** *what would have to be
      true for this to pass while measuring nothing?* Name conditions you could plant, or it is not
      an answer
- [ ] Non-vacuity asserted before any plant
- [ ] Can-fail demonstrated; the failure names the site
- [ ] CONTROL run, passes clean
- [ ] Plant performed in scratch, never in a production artifact
- [ ] No literal anchor describing the current state of the world
- [ ] Distinct exit code for CANNOT MEASURE

**When reporting:**
- [ ] Per item: PASS / FAIL against the criterion **as written**, not as remembered
- [ ] Every defect as **symptom · root cause · fix** — including defects in the instruments
- [ ] **Every claim that measurement contradicted**, stated plainly
- [ ] The surface classification, and the environment that produced each result

---

## 10. TOOL REFERENCE

| tool | role | tier | docs |
|---|---|---|---|
| **pytest** | test runner | 1, 2, 3 | https://docs.pytest.org/ |
| **pytest-testmon** | selects only tests affected by the change | 1, 2 | https://testmon.org/ · https://github.com/tarpas/pytest-testmon |
| **Ruff** | lint + format — rule violations, fast | 1, 2, 3 | https://docs.astral.sh/ruff/ · hooks: https://github.com/astral-sh/ruff-pre-commit |
| **PyLint** | design smells via inference — slower, deeper | 1, 3 | https://pylint.readthedocs.io/ · https://github.com/pylint-dev/pylint · **not** `pylint.org` |
| **pdb** | interactive debugger, entered on failure | 2 (Stage 3) | https://docs.python.org/3/library/pdb.html |
| **Playwright** | GUI workflow simulation | 2 (Stage 4), 3 | https://playwright.dev/python/ |
| **mypy** | static type checking | 2 (Stage 5), 3 | https://mypy.readthedocs.io/ |
| **Bandit** | security scanning | 2 (Stage 5), 3 | https://bandit.readthedocs.io/ |
| **complexipy** | cognitive-complexity ceiling | 2 (Stage 5), 3 | https://rohaquinlop.github.io/complexipy/ · https://github.com/rohaquinlop/complexipy |
| **pre-commit** | orchestration and enforcement | 2 | https://pre-commit.com/ |

---

## 11. IF YOU REMEMBER ONE THING

**Ask, of every green result you produce: *what would have made this fail?***

If you cannot name the thing — specifically, concretely, and in a form you could plant — **you have not
verified anything. You have observed an absence of complaint.**

That question is the whole doctrine. The tiers and tools exist to make answering it routine.

**And its twin, §7.12, asked of the gate rather than the result:** *what would have to be true for
this to pass while measuring nothing?* Seven recorded instances say that is where this codebase
actually loses. Answer it in writing, beside the gate, on the day you build it.
