# THE VERIFY FAMILY AND THE CHECK SYSTEM — CONTRACT AND ORIENTATION

**Audience:** an AI agent that will build, extend, or reason about Luna's verification machinery.
**Status of this document:** it describes **two different things** and keeps them separate on purpose.

> ## ⚠ READ THIS FIRST — `verify.py` DOES NOT EXIST
>
> Measured on the real tree, whole-tree `find`, not merely absent from its stated path:
> **`verify.py` · `bump_version.py` · `registry.json` · `strategy.py` · `risk_engine` are all absent.**
> `~/luna/checks/` contains only `.gitkeep`.
>
> The bible once named `verify.py` in the present tense in its directory table. **That was a defect**, it
> was measured as one, and the reference was removed by amendment. The rule that replaced the old build-
> status line is the governing one here:
>
> **"This file names desired state, never inventory. Every artifact named here is unproven until seen on
> disk. The tree is the authority on what exists."**
>
> **§A below is DESIGN — a contract for something not yet built. §B is what actually runs today.**
> If you write code, docstrings, or documentation that describe §A in the present tense, you will
> reproduce the exact defect this project has already paid to remove. Use the future or the conditional.

---

# PART A — THE VERIFY FAMILY (DESIGNED, NOT BUILT)

## A.1 The core abstraction

**A check is an idempotent unit that declares a desired state, assesses reality against it, and can
converge reality to match.**

Three properties follow, and each is load-bearing:

1. **Declarative.** A check states what *should* be true, not what steps to run. The steps are the
   library's business.
2. **Idempotent.** Running it twice is running it once. Convergence, not mutation.
3. **Assess-and-converge are the same unit.** The thing that knows how to detect drift is the thing
   that knows how to fix it — because separating them guarantees they eventually disagree.

## A.2 One library, three drivers

**There is exactly one check library. Drivers are postures over it, never separate implementations.**

| driver | posture |
|---|---|
| `install` | first-time convergence against a bare machine — assumes nothing exists |
| `verify` | **read-only by default.** Assess and report drift, touch nothing |
| `maintain` | continuous convergence on a running system — assumes everything exists |

**`verify --correct` is a flag on `verify`, not a fourth driver.** The reason is precise:

> **You cannot correct without assessing.** Making correction a separate verb would permit a repair
> path that never measured what it was repairing.

**And the default matters more than the flag.** `verify` must be read-only by default so that a bare
`verify` — invoked from cron, or by a human in a panic at 3 a.m. — **cannot mutate the system.** A
verification tool that repairs by accident is a tool that destroys evidence at exactly the moment the
evidence matters.

## A.3 `status` is a view, not a script

**`status` is not a separate program.** It is a fast, human-facing, filtered read-only view *over*
`verify` — same checks, same assessment.

**The property this buys: `status` physically cannot disagree with `verify`.** Two programs answering
"is the system healthy?" will diverge; the only question is when. One program with two presentations
cannot.

This is the project's `derive, never restate` principle applied to a user interface.

## A.4 Where checks live

| path | contents |
|---|---|
| `~/luna/checks/` | per-component checks, their manifests, and `registry.json` |
| `~/luna/docs/CHECK-DEBT.md` | the ledger of owed-but-unwritten checks |

## A.5 The layout is itself a checkable desired state

The directory tree is not convention — it is declared state. **A check declares the tree shape,
`verify` flags a stray file, and `verify --correct` moves it home.**

This is the pattern to internalise: **if a rule can be stated as a desired state, it should be a check
rather than a paragraph.** A rule in prose is enforced by whoever remembers it. A rule as a check is
enforced by the machine, every run, forever.

## A.6 Where `verify` is load-bearing outside the check phase

Two places, both irreversible-class:

- **Release.** A commit is not a release. The release driver is the only legal path:
  `clean tree → verify PASS → flag-driven X.Y.Z bump → annotated tag → generated notes → push`.
  **Any gate failure aborts.**
- **Update.** Saturday only, tagged releases only, never a branch tip. Verifies **flat-and-idle** as a
  precondition — failing closed rather than trusting the calendar — then is **atomic and reversible**:
  `snapshot → swap → verify → auto-rollback on failure`.

**Note the shape in both: `verify` is the predicate that authorises an irreversible act, and its
failure is what makes the act reversible.**

## A.7 Why the check system is built LATE — and what that changes

**Deliberate sequencing decision, not neglect.** The check system is built after the trading core
exists, because a check declares a desired state and most of the desired states do not exist yet.

**Consequence, and it is the important part:** the check-coverage rule shifts from a **build gate** to
a **ledger obligation**. Every arc that touches a component with declarable state **owes** a check, and
that obligation is recorded in `CHECK-DEBT.md` rather than blocking the arc.

**The check phase's PASS gate is the drain of that ledger.** Measured warning for whoever builds this:
**CHECK-DEBT has risen monotonically — 95 → ~190 across seventeen arcs — and has never once fallen.**
A gate of *"fully drained"* against that series is unreachable as written; it has since been restated
to something achievable. **Do not build a gate whose criterion the trend line says can never be met.**

---

# PART B — WHAT ACTUALLY RUNS TODAY: THE STANDING-GATE REGISTRY

**This is real, on disk, and has caught defects.** It is not `verify.py`. It is the mechanism that
exists in the meantime, and any future `verify` must subsume it rather than replace it.

## B.1 Shape

- **Individual gates** are standalone scripts, conventionally `checks/check_<property>.py` or
  `scripts/check_<property>.py`, each owning exactly one property.
- **`bank.sh` runs the registered gates at STEP 2 of every arc bank.** That is the enforcement point:
  the gate suite runs unconditionally at the arc boundary, and its verdict is banked.
- **A RED withholds *certification*, never *durability*.** The arc still banks; it is recorded as NOT
  CERTIFIED. **Evidence is never lost to make a verdict look better.**

## B.2 Exit-code contract

| exit | meaning |
|---|---|
| `0` | **PASS** — measured, and satisfied |
| `1` | **FAIL** — measured, and violated |
| `2` | **CANNOT MEASURE** — the gate did not run correctly |

**Exit 2 exists because of a real defect and you must preserve it.** A gate shelled out to a
subprocess; the subprocess timed out; the exception type was not caught by the handler; the interpreter
exited **1** — *the same code the gate used for "violation detected"* — and the gate was recorded as
reporting a violation **while having measured nothing.** It sat under a `known-red` marker for arcs.

**A marker on a broken instrument is indistinguishable from a marker on a working one.** That is a
false GREEN wearing a RED coat, and a distinct exit code is what separates them.

## B.3 The `known-red` marker

A gate may be RED for a known, owned reason — a property that is genuinely not yet satisfied. The
marker records that, and **`bank.sh` discriminates expected REDs from new ones**, so an unexpected RED
is never lost in the noise of an expected one.

**Two rules govern markers, both learned expensively:**

1. **A marker must name the arc that can actually discharge it.** *An owner that cannot pay is no owner
   wearing a name* — a marker pointed at an arc whose own scope forbids the fix becomes furniture.
2. **A marker's membership must never change silently.** If the set of things a gate covers shifts, say
   so; a known-red whose meaning drifted is a marker nobody is reading.

## B.4 The rule that keeps gates honest

**A standing RED is closed by making the gate STRICTER, or by fixing the code — never by weakening,
unregistering, exempting, or re-scoping the gate.**

Worked instance: a gate stood RED for arcs. It closed by **wiring a real production caller** and by
demanding strictly *more* than it did while it was RED.

Counter-instance from the same project, and the tempting one: a gate went RED on a *correct*
implementation inside the very module it guards. **The tempting fix was to exempt that file — and it
would have blinded the gate to the one module that can actually reach the field it protects.** A gate
that fails on the correct implementation of its own subject is not strict; it is **broken**, and the
repair is to the gate's logic, not to its scope.

## B.5 Representative gates, and what each teaches

| gate | property | the lesson it carries |
|---|---|---|
| `anchor-derivation` | no assertion is pinned to a coordinate that moves | **Built by an agent with no knowledge of a parallel fix, it autonomously found the exact defect that fix existed to remove — the first machine catch of that failure class in the project's history.** |
| `check_readonly_boundary` | market-data paths cannot reach a mutating endpoint | proof **by absence over the import closure**, not by call-site guard |
| `binding-single-home` | one symbol map, one home | went RED on real work one arc after registration — *predicted in writing when it was registered* |
| `production-caller-required` | a declared capability has a real `ExecStart=` caller | **a tripwire with no caller is not a tripwire** |
| `check_mid_overlap` | two series agree within served precision | closes **by convergence, never by widening tolerance** |
| `check_complexity.py` | cognitive-complexity ceiling | **wraps `complexipy` because the tool exits 0 on zero files** — a misconfigured glob would otherwise produce a clean PASS that measured nothing |
| `stream-no-compression` | the stream path never requests a compressing encoding | scoped to the stream **only** — the REST path keeps compression, where it is a large win. **A blanket ban would redden correct code** |
| `forex-week-single-impl` | one implementation of the week boundary | duplicate implementations of a boundary rule diverge silently |
| `size-authority` | nothing but the allocator can produce a size | **it correctly refused its own author's first draft** |

## B.6 `prove_*` harnesses — the other half

Distinct from gates, and the distinction matters:

- **`check_*` gates** are registered, run by `bank.sh`, and block certification.
- **`prove_*` harnesses** are per-module proofs of a specific property — determinism, byte-identical
  live/replay output, clock purity, crash-safety. They are **not** in the registry.

**⚠ Both must be baselined before any work begins.** Real incident: a `prove_*` harness and the lint
gate were **already failing before an arc started**, and only the registered gates had been baselined —
so those failures would have been attributed to the arc's own changes.

**Baseline everything that can be RED, on a pristine tree.** And a baseline taken while the tree is
moving is not a baseline.

## B.7 The self-enforcing pattern — the best thing in this system

One harness **parses a constant out of the bible** and asserts the running module's constants equal
what the specification says.

**Consequence: changing the specification without changing the code is RED, and changing the code
without changing the specification is also RED.** The document and the implementation cannot drift,
because a machine reads both and compares them.

**This is the pattern to reach for whenever a document states a number the code also states.** It turns
`derive, never restate` from a discipline into a mechanism. When you find a constant written in two
places, your first question should be whether one can read the other.

---

# PART C — RULES BINDING ON ANY GATE YOU WRITE

Every one of these was paid for. **Roughly one defect in three in this project was found inside the
instrument doing the measuring, not the code under measurement.**

1. **Prove the property, not a proxy.** A check reads **effective, running state** — a real verdict, a
   real restore, a real round trip. **Never** file presence, import success, or process-alive.
2. **Demonstrate the gate can FAIL, with a CONTROL.** Plant the exact defect; the gate must fail **and
   name the site**. Remove the plant; it must pass. Both halves, or you cannot distinguish *detects the
   defect* from *always fails*.
3. **Prove non-vacuity BEFORE any plant.** Assert the gate's scope contains its subject. Real incident:
   a rule added to a scanner inherited a scope that made it **structurally unable to see the file it
   was written about**. It would have passed forever.
4. **Never anchor to something that moves.** Derive the file list from the tree; assert the invariant,
   not the current value. **Five independent instances of this class, no two caught the same way.**
5. **Prove by absence, not by call-site guard.** Scan the module or import closure for the capability
   itself. Real incident: a fix was applied to the one file everyone knew about; proof by absence found
   **a second file nobody had ever named**.
6. **Compare verdict-by-verdict, never in aggregate.** A refactor once preserved the output *set* and
   changed its *order*; the aggregate comparison passed it.
7. **Fail closed and loud.** A correct-but-silent deny is a defect.
8. **A plant never touches a production artifact.** Real incident: a synthetic row was planted into an
   **append-only** datastore to prove a detector could fire. The detector worked. **The row is
   permanent, unsupersedable, and still in the canonical series.** The instrument was right; the method
   was wrong.
9. **Extend an instrument that already owns a property; never build a second.** Two instruments
   measuring one property will disagree, and you will not know which is right.
10. **One owner per shared global measurement.** If parallel work-streams each measure tree-wide
    complexity or lint state, the results are unattributable.

---

# PART D — IF YOU ARE ASKED TO BUILD `verify`

**A design brief, not permission. Building it is an operator decision that has not been made.**

1. **Subsume the existing gates; do not replace them.** They have caught real defects and carry their
   can-fail evidence. A rewrite discards that evidence and starts the trust clock at zero.
2. **Keep the exit-code contract**, including exit 2. It exists because of a measured incident.
3. **Read-only by default is non-negotiable**, and prove it — a `verify` demonstrated unable to mutate,
   not merely observed not mutating.
4. **`status` derives from `verify`.** Two programs is a defect in the design, not a shortcut.
5. **`registry.json` is the single source of what is registered** — and every consumer derives from it
   rather than restating its contents.
6. **The gate suite is itself an instrument, so it needs its own can-fail:** demonstrate that a
   registered gate which *should* fail is actually run and actually reported, end to end. **A suite
   that silently skips a gate reports GREEN.**
7. **Anything you write about it lives in the future tense until it is on disk.** See the warning at
   the top of this document.

---

## THE ONE-LINE VERSION

**`verify` asks whether reality matches declared state; `verify --correct` converges it; `status` is the
same answer with a friendlier face. None of it exists yet. What exists is a registry of standing gates
run at every arc bank — and the discipline that a gate is guilty until it has been shown able to say
no.**
