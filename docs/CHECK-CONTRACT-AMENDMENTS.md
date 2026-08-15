# CHECK-CONTRACT-AMENDMENTS — amendments to the check/verify contract

**Status: a RECORD, not an authority.** Nothing here is doctrine text. Each entry describes
behaviour Nix implements that `VERIFY-AND-CHECKS.md` does not describe, or describes differently.

**`VERIFY-AND-CHECKS.md` is never edited in place.** It is external, inherited doctrine — its
audience line names *Luna*, not Nix — it carries **no version number** and **no amendment
mechanism**. There is nowhere inside it to put a Nix amendment, and editing another system's
doctrine to make Nix's implementation look conformant is the inverse of measuring. Amendments are
therefore **implemented in the derived spec `nix_check_contract.md`** (v1.3.0) and **recorded
here**. The doctrine keeps its authority over everything it does say.

**CITATION FORM: `CHECK-A<n>` (ARC 028 / 0.4, architect ruling).** `CHECK-A3` *is* amendment 3 of
this ledger; the number is unchanged and nothing was renumbered. The prefix exists because a bare
**"AMENDMENT 6" named two different rulings** — one here, one in `SPEC-AMENDMENTS.md`, which
numbers from 1 independently and also holds six. `scripts/tests/test_amendment_ledgers.py`
enforces the prefix and the uniqueness of the number **within** each ledger, mechanically, because
the defect that produced this ruling (two entries issued as `AMENDMENT 5` inside one file) was
caught by a human reading both and by nothing else.

## Why this file exists rather than `SPEC-AMENDMENTS.md`

ARC 024's brief (§2.6) said to record the amendment "in the project's amendment ledger alongside
Amendments 1–5." Measured against the file, that instruction is wrong on two counts:

1. **Wrong ledger.** `SPEC-AMENDMENTS.md`'s first line is *"pending amendments to the frozen risk
   spec"*; every entry there names a section of `nics_risk_subsystem_spec_v1.3.md` that would have
   to say it, and every entry is `PENDING` a v1.4 the architect owns. A check-contract amendment
   has no risk-spec section to name and no v1.4 to be pending on. Filing it there would put two
   different source documents' pending changes in one ledger, and the first reader to act on it
   would carry a check-contract ruling into the order path with frozen-spec weight — the exact
   attribution failure `SPEC-AMENDMENTS.md`'s own D2.17 paragraph exists to prevent.
2. **Wrong count.** `SPEC-AMENDMENTS.md` holds **six** amendments (1–6, plus a refinement to 3),
   not five. "Alongside Amendments 1–5" was already stale when the brief was written.

**This ledger numbers from 1 independently.** AMENDMENT 1 here is not AMENDMENT 1 there.

## Attribution rule (inherited from `SPEC-AMENDMENTS.md`, CHECK-DEBT D2.17)

Every entry names its origin — the ruling and the arc that issued it — and every section reference
names the document it belongs to. Doctrine citations use `VERIFY-AND-CHECKS.md`'s Part/section
letters (A.2, B.2, D.2 …). Numeric section references (§4.1, §4.2) are `nix_check_contract.md`'s
own. An operator ruling has the authority of an operator decision, which is real, and does not have
the authority of the doctrine.

---

## CHECK-A1 — `GUARDED`, a fourth exit code

| field | value |
|---|---|
| origin | **Operator ruling on TUI colours, issued in ARC 024** (red = Failed · yellow = Guarded · green = Passed · light blue = Cannot run or check). The colour was ruled; the *meaning* was not, and the semantics below are **[ARCHITECT RULING — revocable]** |
| implemented by | ARC 024, `scripts/nixverify/contract.py`, `engine.py`, `render.py` |
| doctrine it extends | `VERIFY-AND-CHECKS.md` §B.2 (three exit codes) and Part D item 2 |
| status | implemented as written; operator to confirm Guarded's meaning |

### What changed

`Status.GUARDED` → exit **3**. The full mapping:

| colour | status | exit |
|---|---|---|
| green | `PASS` | `0` |
| red | `FAIL_REPAIRABLE`, `FAIL_NEEDS_OPERATOR` | `1` |
| light blue | `CANNOT_MEASURE`, `SKIPPED` | `2` |
| yellow | `GUARDED` | `3` |

### Semantics [ARCHITECT RULING — revocable]

**The check's subject is real and WAS measured, and the check carries a known-red marker naming the
specific future arc that discharges it.** Neither a pass (nothing was proven) nor a failure (nothing
is broken) — **a deferral with an owner.**

**Guarded withholds certification but never durability.** The arc still banks; it is recorded NOT
CERTIFIED. This is doctrine §B.1's rule for RED applied unchanged to the new state: evidence is
never lost to make a verdict look better.

### Why it is additive rather than a revision of exit 2

`0`/`1`/`2` keep exactly the meanings §B.2 gives them. Exit 2 in particular is untouched, which
preserves Part D item 2 — *"keep the exit-code contract, including exit 2; it exists because of a
measured incident."*

The reason it can be preserved rather than amended is in the incident itself. §B.2's exit 2 exists
because a gate shelled out, the subprocess timed out, the interpreter exited `1`, and **the gate was
recorded as reporting a violation while having measured nothing.** GUARDED cannot recreate that
class: it is a status available **only to a gate that DID measure**, and the engine enforces that
rather than asking for it. The two states are not competing for the same code because they are not
describing the same thing — exit 2 is *"I could not look"*, exit 3 is *"I looked, and this is
known-red with a named owner."*

### Mechanically enforced, not asked for in prose

`contract.validate_result` downgrades a `GUARDED` result to `CANNOT_MEASURE` when:

- `evidence` is empty — a deferral that measured nothing is an unmeasured claim with a colour; or
- `guard_owner` is empty — **`CHECK-DEBT.md` doctrine B.3: *an owner that cannot pay is no owner
  wearing a name.*** A marker pointed at nobody becomes furniture, and GUARDED is the one status
  that would rot into a drawer for anything inconvenient because, unlike FAIL, it costs nothing to
  claim.

Both downgrades append their reason to `detail` rather than replacing it: the downgrade path is
where an operator most needs the check's own account of why it is uncertain.

### Aggregate dominance: FAIL > CANNOT-MEASURE > GUARDED > PASS

`engine.aggregate_exit` ranks GUARDED **below** cannot-measure. The order is the ruling, and the
justification is informational content: a cannot-measure carries **no information about its
subject**; a GUARDED verdict carries a measurement *and* the name of the arc that discharges it.
Ranking the informative state above the uninformative one would let a run of known-red deferrals
out-shout a gate that went blind — the direction §B.2's exit 2 exists to prevent.

### Non-regression — measured, not assumed, and measured twice

**At the point the amendment landed (ARC 024 Stage 2): no check emitted `GUARDED`.** The
`Status.GUARDED` branch in `aggregate_exit` and `exit_code_for` was unreachable, the aggregate was
**bit-identical** to the pre-amendment function, and `verify.py` still returned exit `1` with the
same pass/fail/cannot-measure triple across the change.

**Re-measured after Stage 2.7 (2026-08-11), because that is no longer true.**
`checks/check_artifact_gate_coverage.py` is the first and only emitter:

```
11 passed | 1 failed | 1 cannot measure | 0 skipped | 1 guarded          exit 1
[GRD]  check_artifact_gate_coverage  24 artifact(s) accepted as uncovered by
       checks/gate_coverage_baseline.json, discharged by the bulk check retrofit
       arc (ARC 025+), sized in ARC 024 Stage 6.4
```

**The aggregate is unchanged at exit `1` — and that is the dominance rule doing its job, not a
coincidence.** A live GUARDED did not displace a live FAIL. Exit `3` is reachable only on a run with
no failure and no cannot-measure, which this tree does not currently produce.

### Colour reassignment — recorded, because a silent one is the defect

`CANNOT_MEASURE` was **yellow** up to ARC 023. The ruling gives yellow to `GUARDED` and moves
cannot-measure and skipped to **light blue**, which now covers both.

**No information is lost.** `SKIPPED` and `CANNOT_MEASURE` keep **distinct glyphs in both glyph
sets** (`·`/`⚠` unicode, `[--]`/`[??]` ASCII), and they already shared exit code `2` before this
amendment. Colour is redundant with the glyph here, and the glyph — unlike the colour — survives a
pipe.

---

## CHECK-A2 — actuation: verify / correct / install, and the independent re-verify

| field | value |
|---|---|
| origin | **Operator rulings 1 and 3, issued in ARC 024.** Ruling 1: every check must be able to verify, correct and install, selected by passed-in flags. Ruling 3: a correction is followed by a verify that confirms the change happened |
| implemented by | ARC 024, `scripts/nixverify/actuation.py` (`standalone_main`, `reverify`, `guard_mutation`, `session_state`) |
| doctrine it operationalises | `VERIFY-AND-CHECKS.md` §A.1 (assess-and-converge are the same unit), §A.2 (`verify --correct` is a flag, not a fourth driver; read-only by default) |
| status | all four sub-rulings **[ARCHITECT RULING — revocable]**, implemented as written, awaiting ratification |

### §2.1 — the flag surface, and what was already true

Every check exposes verify/correct/install on **its own CLI** via
`nixverify.actuation.standalone_main`. **Default is measure-only; a flagless check never mutates.**
`--correct` and `--install` are mutually exclusive, explicit, per invocation; no environment
variable and no config key turns them on.

**This was already the runner's policy and is recorded, not introduced.** `scripts/verify.py` has
carried `--mode verify|correct|install` since ARC 009, defaulting to `verify`, and hands the mode to
every check as `run(mode, ctx)`. What was missing was the *check's own* CLI: **all 13 registered
checks hardcoded `Mode.VERIFY` in `__main__`.** A check was an actuator the runner could drive and
an operator could not. `parse_actuation` closes that gap.

### §2.2 — the re-verify is an INDEPENDENT re-measurement [ARCHITECT RULING — revocable]

After a correction or install, `actuation.reverify()` **re-executes the check as a fresh subprocess
in verify-only mode** and reads its exit code. It does not call `run()` again in-process and it does
not accept any value from the correcting path.

**A return value from the correcting path is not a verification.** `correct()` returning `True` and
the check reporting PASS on that basis is a vacuous pass *by construction*: the correcting code and
the confirming code share every assumption, every cached value, and every module-level import. A
fresh process shares none of them — it re-reads the file, re-opens the socket, re-asks systemd.

**The verdict after a mutation is the re-verify's, not the correction's.** `standalone_main` returns
`reverify()`'s exit code, not the correcting run's, and prints a loud disagreement notice when the
correction reported success and the independent re-measurement did not.

### §2.3 — the non-correctable class [ARCHITECT RULING — revocable; OPERATOR TO RATIFY OR NARROW]

A check may declare `CORRECTABLE = False` with a mandatory `NON_CORRECTABLE_REASON`, and then
refuses `--correct`/`--install` **loudly**, naming its reason, rather than silently ignoring the
flag. **A refusal with no reason is a declaration error** — `declarations.read_declaration` records
it as such, and `optimize.py` treats it as fatal for that check.

Proposed members, for the operator to ratify or narrow:

- anything on the **order path**;
- anything touching **credentials** or `state/` (mode 0600);
- anything that would mutate **broker session state, clientId assignments, or open positions**.

The reasoning is the risk spec's own: auto-resend on the order path is prohibited because automatic
remediation there converts one intended action into two.

**Charter member implemented: `checks/check_order_path_bans.py`** (`CORRECTABLE = False`).
`checks/check_verify_logging.py` is the second, on a different reason — its subject is the journal
transport, and "correcting" it would mean writing to the thing under measurement.

### §2.4 — the session safety interlock [ARCHITECT RULING — revocable]

`--correct` and `--install` refuse unless a trading session is **positively measured INACTIVE**.

**Three states, not two, and the third is the honest one:**

| verdict | outcome |
|---|---|
| `active` | **refuse** — units active inside `nix-trading.slice`, named |
| `inactive` | permit — measured, not inferred from absence of evidence |
| `unknown` | **refuse, and name what could not be determined** (systemctl absent, non-zero exit, subprocess error) |

A two-state interlock would have to guess, and a guess in this position is either a refusal that
never lifts or a permission that was never earned.

**`--force` does NOT override the interlock.** It raises its own refusal saying so. The flag is
reserved and deliberately inert here.

Order of checks inside `guard_mutation` is load-bearing: the per-check `CORRECTABLE = False` refusal
fires **before** the session interlock, so a non-correctable check refuses for its own reason even
on a quiet box — otherwise the operator learns "no session is running" and infers, wrongly, that
correction would have been available.

The observable is a unit **active inside `nix-trading.slice`**, not the slice's own `ActiveState`:
a slice is a cgroup, always `active`, and reading it would produce a permanent meaningless refusal.

---

## CHECK-A3 — the coverage trigger broadened

| field | value |
|---|---|
| origin | **Operator ruling 4, issued in ARC 024** |
| implemented by | ARC 024, recorded in `nix_check_contract.md` §1 |
| supersedes | `nix_check_contract.md` §1's environment-change wording |
| status | trigger recorded; the enforcing gate is **owed** (see below) |

### What changed

| | trigger |
|---|---|
| old (`nix_check_contract.md` §1) | every **environment** change owes a check — a package installed, a setting written, a unit wired, a file created |
| new | **any time any module or setting is written to disk or changes**, an associated check script is owed |

Strictly broader: a module written into `scripts/` changes no environment and owed nothing under the
old trigger. It owes now.

### What did NOT change — the ledger character

**The obligation is a LEDGER obligation, not a build gate** (doctrine A.7). An arc that owes a check
and does not write it records the debt in `docs/CHECK-DEBT.md` and proceeds.

**Do not build a gate on "CHECK-DEBT drained."** Doctrine A.7 records the measured counter-example:
on the predecessor system that ledger rose monotonically across seventeen arcs and never once fell.
The target is **per-arc movement**, not zero. Broadening the trigger raises the accrual rate, which
makes this warning more binding, not less.

### The enforcing gate, and the ceiling on what it can prove

`checks/check_artifact_gate_coverage.py` enumerates the tracked module and config artifacts,
enumerates the subjects declared by the check population (AMENDMENT 2's declaration mechanism
supplies this), and reports any artifact with **zero** declaring check. Measured on disk 2026-08-11
and registered; it is a **ratchet** — the 24 artifacts in `checks/gate_coverage_baseline.json` are
existing debt and report `GUARDED` (AMENDMENT 1) owned by the bulk retrofit arc; a *new* uncovered
artifact is a regression and is a FAIL; a baseline entry that has since become covered is also a
FAIL, so the baseline can only tighten and can never become a suppression list.

**[ARCHITECT RULING — revocable]** It ships **UNBOUND per `CHECK-DEBT.md`'s D3.10 rule of record,
and says so in its own docstring and in its verdict.** It proves that **SOME CHECK NAMES the
artifact**,
which is strictly weaker than **SOME CHECK MEASURES it**. A check naming a subject it never drives
is **D3.16 exactly**, and this gate is structurally unable to see that class — the declaration it
reads is a string, and a string cannot be interrogated about whether the code beneath it runs.

**Its green must not be read as coverage.** D3.10's ratified rule is why: a can-fail against a
purpose-built fake proves a gate *can* discriminate, not that it discriminates against its real
subject, and a gate binds **per subject, not once**. Binding this one is a named future arc.

---

## CHECK-A4 — the close-out gate proves durability, not authorship

| field | value |
|---|---|
| origin | **Operator finding, issued in ARC 025 close-out of ARC 024** |
| implemented by | ARC 025, recorded in `nix_check_contract.md` §16 |
| supersedes | nothing. `CLAUDE.md`'s write-back rule stands; this adds a third obligation to it |
| status | rule recorded; the enforcing check is **owed** (see below) |

### The counter-example is measured, and it is this project's own

`CLAUDE.md` requires every arc to append `sessions/SESSION.md`, overwrite `downloads/RESULTS.md`,
and `cat` both before reporting completion. **ARC 024 satisfied that gate completely and its entire
output was outside history.**

| | ARC 024 at self-reported completion |
|---|---|
| `SESSION.md` written, `RESULTS.md` written, both `cat`-ed | **yes — gate passed** |
| `HEAD` | `2871bc6`, the **ARC 023** merge |
| the arc's work | 30 paths, 5,019 insertions, **staged in the index, never committed** |
| gate figures reported (`verify.py`, pytest, pre-commit, claims harness) | all taken against a tree that was **not history** |

A `git reset` would have destroyed the arc and every measurement in its report would still have read
as green. **The gate could not see this because nothing it checks is a property of the repository.**
An mtime proves a file was written; it does not prove the work is durable.

### What changed

| | close-out obligation |
|---|---|
| old (`CLAUDE.md`) | append `SESSION.md`; overwrite `RESULTS.md`; `cat` both as the last action |
| new (**+** `nix_check_contract.md` §16) | **and** show that `HEAD` advanced, that `HEAD`'s tree contains the arc's paths, and that `git status --short` is empty for them |

**Shown, not asserted** — `git rev-parse HEAD` either side, `git ls-tree -r HEAD --name-only`, and
`git status --short`. `ls` is not evidence: the index is not history and the working tree is not
history. An arc that legitimately wrote nothing to the repository is exempt and **says so out loud**;
a silent exemption is the defect wearing the exemption's name.

### §16.2 — the figures are re-taken against the merged tree

An arc's gate figures are evidence about a tree. If that tree never became history the figures
describe nothing durable. After the merge the four harnesses re-run and the results are compared
against what the arc reported. **A delta is a finding even when its cause is environmental** — *"the
number moved and here is why"* is a result; *"the number did not move"* was the claim under test.

Demonstrated on this very close-out: re-running `verify.py` against merged ARC 024 gave
`10 passed | 1 failed | 2 cannot measure | 0 skipped | 1 guarded` against the arc's reported
`11 passed | 1 failed | 1 cannot measure`. The extra cannot-measure was `check_derived_claims`
dropping to 12/13 claims because its `pytest_collector` source extracts `(?m)^(\d+) tests? collected`
and the harness shell exports `FORCE_COLOR=3`, so pytest prefixed the summary line with ANSI and the
anchored `^` stopped matching. With `FORCE_COLOR` unset the merged tree reproduces the arc's figures
exactly. **Environmental, not a merge regression — and worth having: the claim silently stops being
compared in any colourised environment, and no arc would have learned that without §16.2.**

### The ceiling on what this gate can prove — stated, not implied

It proves the arc's paths are **in** history. It does not prove their **content** is what was
measured: a path committed after a post-measurement edit satisfies all three obligations and carries
different bytes. §16.2 is the compensating control and is weaker than it looks — it re-derives the
figures, it does not prove byte identity with the measured tree. Nor does the gate prove the history
is reachable by anyone else; a local commit satisfies §16.1 and dies with the disk, so where the
target is a shared branch, durability means pushed and merged and the merge commit is the evidence.

### The enforcing check is owed

Every clause of §16.1 is mechanically checkable from `git` alone, which makes this rule owed a check
under §1 as broadened by AMENDMENT 3. **None was written in this close-out** — the close-out's write
scope was ARC 024's history and this amendment, and a gate on arc completion is arc-boundary
machinery Nix does not have (§15.4 records that Nix has no `bank.sh`). Recorded rather than blocking,
per §1.

---

## Standing note for the architect

Open items this ledger records and does not resolve (ARC 024 returned them to the operator):

1. **`manifest.json` vs `registry.json`** — the operator ruling names `checks/manifest.json`; the
   file on disk is `checks/registry.json`, named per doctrine A.4/D.5 and renamed from
   `verify_manifest.json` in ARC 010. **Not resolved silently in either direction.**
2. **Guarded's meaning** — the colour was ruled, the semantics above are the architect's proposal.
3. **The non-correctable class** — ratify or narrow the three proposed members.
4. **The safety interlock** — ratify.
5. **`--optimize`** — propose-then-commit is implemented; overwrite-in-place was the alternative.

Added by the ARC 025 close-out:

6. **§16.1's three obligations** — ratify. The exemption clause in particular: an arc that wrote
   nothing to the repository declares that and passes, and an exemption granted on an arc's own
   say-so is a hole an arc can walk through by claiming it wrote nothing.
7. **The §16 enforcing check is owed and unwritten**, and it is arc-boundary machinery Nix does not
   have (§15.4: no `bank.sh`). Where should it live — a `checks/check_*.py` that reads `git`, a
   pre-commit hook, or the runner?
8. **`check_derived_claims`'s `pytest_collector` source is environment-fragile** — found by §16.2's
   re-measurement, not by an arc. Its extract is anchored `(?m)^(\d+) tests? collected` and pytest
   emits ANSI before the digits whenever `FORCE_COLOR` is set, so the claim degrades to
   `NOT MEASURED` in any colourised shell. It fails in the safe direction — CANNOT_MEASURE naming
   itself, never a wrong number — so this is a **coverage** defect, not a correctness one. Not
   repaired in this close-out: the fix is a one-line source change, but a `CHECK-DEBT.md` row for it
   moves `check_debt_open_items` 66 → 67 and that number is compared by the very gate in question.
   Owed to ARC 025 proper as a paired change.

---

## CHECK-A5 — the masked hazard, the reason-asserting control, and declared failure policy

| field | value |
|---|---|
| origin | **ARC 025.** Parts 1 and 2 are architect rulings carried in the ARC 025 brief; part 3 is a defect ARC 025 measured in ARC 024's own `--optimize` |
| implemented by | ARC 025, recorded in `nix_check_contract.md` §17, §18 and §4.4 |
| supersedes | nothing. All three are additive |
| status | §17 shipped with a live emitter and a demonstrated FAIL path · §18 shipped and the existing population audited to zero · §4.4's `ON_FAIL` shipped and derived into the installed plan |

### Part 1 — §17, a property proven while its subject is unavailable is not proven

D2.27 read: *disjointness is proven over declarations, never over actual resource use, and no static
mechanism can close that gap.* True of static mechanisms — and ARC 024 had already built the dynamic
one as a one-off. ARC 025 promoted it to a standing gate,
`checks/check_observed_resource_claims.py`, over `scripts/nixverify/observe.py`.

**The instrument is a CPython audit hook (PEP 578), not a monkeypatch, and the substitution was made
with a measurement.** A monkeypatch is defeated by re-import, by a reference captured before the
patch, and by reaching through to `_socket` — and **a defeated spy reports no claims**, which is
exactly the false green the gate exists to prevent. An audit hook cannot be removed or bypassed and
fires *inside* CPython at the call, which is what makes a refused connection still an observed claim.

**What it caught on the real tree, in its first two runs — seven false declarations:**

| check | observed | had declared |
|---|---|---|
| `check_order_path_bans` | `subprocess:.venv/bin/python3` | `()` — *"reads source files only … writes nothing"* |
| `check_verify_logging` | `file-write:checks/.plane2_control_<nonce>` | `journal` only |
| `check_artifact_gate_coverage` | `subprocess:git` | `()` |
| `check_derived_claims` | `subprocess:/usr/bin/python3` | `venv` only |
| `check_hook_suite` | `subprocess:git` | `git-hooks, pre-commit-store, venv` |
| `check_node_identity` | `subprocess:blkid`, `subprocess:findmnt` | `state/node_identity.json` only |

The first is the one that matters most: `check_venv` claims `venv` and **rebuilds it under
`--correct`**, so a plan that believed `()` could have co-scheduled `check_order_path_bans` with the
check deleting its interpreter.

The `check_node_identity` pair is the one that shows the mechanism earning its place. It was **not an
oversight** — Wave A reasoned in writing that `findmnt` and `blkid` are read-only kernel/device
queries contending with nothing, and deliberately left them undeclared. The argument is about
*contention*; a declaration states what the check *touches*, and this project fails closed. **A
human's plausible reasoning about resource use was checked against what the process actually did,
and reality won.** That is the whole content of closing D2.27.

**The masked-hazard clause is what makes the result trustworthy on THIS box.** The Gateway is down,
so both Gateway gates get `ECONNREFUSED` and everything downstream of the handshake never executes.
An observer recording only *successful* use would have seen two checks touching nothing and
certified their collision as safe. The hazard is invisible exactly when the observation is cheapest.
Live verdict: `CANNOT_MEASURE`, naming both gates, `ECONNREFUSED`, and `UNOBSERVED`.

### Part 2 — §18, every can-fail control asserts the REASON

ARC 024's §2.2 re-verify control **passed because the subprocess crashed and also returned 1**. ARC
025 audited the whole population by AST and repaired it to zero.

| population | ARC 025 start | close |
|---|---|---|
| controls over a driven subject | 47 | **68** |
| assert a REASON | 42 | **68** |
| **assert EXIT CODE ONLY** | **5** | **0** |
| contract-table tests (exempt) | 3 | 4 |

The last delinquent was `test_reverify_of_a_missing_check_is_cannot_measure` — **ARC 024's own
incident, still unrepaired eighteen months of arcs later**, asserting `exit_code == 2` where exit 2
is what the *interpreter* returns when it cannot open the file and also what a check that ran
correctly and honestly reported CANNOT_MEASURE returns.

### Part 3 — §4.4's `ON_FAIL`, because `--optimize` was silently dropping failure policy

`derive_plan` never emitted `on_fail`, and `Block.on_fail` defaults to `"continue"`. **A
`--optimize --commit` would have installed a plan in which a failed Python runtime no longer halts
the run** — and every success criterion stated for the derivation (plan derived, zero cycles, zero
orphans, `.proposed` written, `--commit` required) would still have been met. A planning tool that
passes all its own tests while discarding a safety policy is this project's vacuity class wearing a
new coat.

**The obvious repair is worse than the defect and was refused with a measurement.** Marking the
level `halt` fails because `engine.run_blocks` halts when **any** member of a halting block fails —
and on this tree `check_ibgateway_service` FAILs by design, so it would have taken every downstream
check with it. Halting checks are therefore emitted as their **own single-check blocks**, which
reproduces the hand-maintained semantics exactly: the floor halts on its own failure and nothing
else.

### Open item 8 of AMENDMENT 4 is DISCHARGED

`check_derived_claims`'s `pytest_collector` was environment-fragile: `FORCE_COLOR` in the ambient
shell made pytest emit ANSI before the digits, the `(?m)^(\d+) tests? collected` anchor missed, and
the claim degraded to `NOT MEASURED` — `verify.py` reporting `10 passed | 1 failed | 2 cannot
measure` instead of `11 | 1 | 1`. ARC 024 recorded it and deferred it, correctly noting the
circularity: the `CHECK-DEBT.md` row would move `check_debt_open_items` 66 → 67, and that number is
compared by the very gate in question.

**Repaired at the source runner, not by widening the regex.** A new `_child_env()` strips
`FORCE_COLOR`/`CLICOLOR_FORCE` and sets `NO_COLOR=1`/`TERM=dumb` for **every** subprocess site, so
it protects sources nobody has written yet rather than the one that broke; ANSI stripping in
`_extract` is a second, independent layer for a tool that colours for its own reasons. Control:
`verify.py` run twice, identical in every other respect, reports the same figures with
`FORCE_COLOR` set and unset.

**It was independently re-measured before it was fixed**, which is §16.2 working as designed — ARC
025's Phase 0 re-run against the merged tree reproduced the exact degradation from the ledger entry.

### Open items returned to the operator

1. **The §17 observer's residual is DYNAMIC**, and narrower than D2.27's but real: it observes the
   code paths a run actually took. A branch not taken is not observed. There is no proposal to close
   this and it should not be read as closed.
2. **§18's rule is mechanically checkable and the auditor ran as a one-off.** Promoting it to a
   standing `checks/check_*.py` is owed; recorded as debt rather than blocking.
3. **`registry.json` vs `manifest.json` remains UNRULED.** ARC 025 renamed nothing in either
   direction, per instruction. The vocabulary (`manifest_version`, `nixverify/manifest.py`,
   `ManifestError`, `load_manifest()`, `--manifest`) is untouched and still disagrees with the
   filename.
4. **Wave C's can-fail binding is still owed to the tap session** — see `CHECK-DEBT.md`. ARC 025
   declared both Gateway gates and gave them the actuation surface; it did **not** re-bind them,
   because that needs a live authenticated Gateway.

---

## CHECK-A6 — the execution plan gets ONE name (ARC 026, B1)

**Amends `nix_check_contract.md` §6. Does not amend `VERIFY-AND-CHECKS.md`**, which names
`registry.json` at A.4 and D.5 and says nothing about the identifiers — the doctrine was never the
source of the disagreement.

### What was wrong

ARC 010 renamed the FILE (`verify_manifest.json` → `checks/registry.json`, per doctrine A.4/D.5) and
stopped. Every identifier one layer down kept the old word, so a single artifact had two live names:

| layer | name before this amendment | name now |
|---|---|---|
| the file | `checks/registry.json` | `checks/registry.json` (**unchanged — the filename ruling is still open**) |
| the module | `scripts/nixverify/manifest.py` | `scripts/nixverify/registry.py` |
| the exception | `ManifestError` | `RegistryError` |
| the loader | `load_manifest()` | `load_registry()` |
| the CLI flag | `--manifest` | `--registry` |
| the JSON key | `manifest_version` | `registry_version` |
| the Plane-2 `run_start` field | `manifest=` | `registry=` |

**This is not cosmetic and it is not a filename ruling.** Two live spellings of one thing, edited by
different hands at different times, is the failure class this project has already paid for twice
under the names `ORDERS_OPEN` and `avg_price`: nothing keeps them in step, and the last writer wins
silently. It is a defect **whichever way the operator eventually rules on the filename**, because
under either ruling one of the two spellings has to go. Purging it now means a future ruling is one
mechanical pass instead of a rename plus an archaeology exercise.

### What is deliberately NOT changed

* **`checks/registry.json` is not renamed, in either direction.** The ARC 024 operator ruling calls
  the artifact `manifest.json`; the file on disk is `registry.json`. **Still unruled, still not
  resolved silently.** ARC 026 took no position: this amendment would have been written the same way
  with the names swapped.
* **`nics_risk_subsystem_spec_v1.3.md` §5 "Rule Manifest"** is untouched and out of scope. It names
  a *different* concept — the Limiter's two-phase rule set — and `risks/broker_order.config.json`
  refers to it correctly. A purge that reddened the frozen spec's own vocabulary would be doctrine
  B.4's forbidden direction dressed as tidiness.

### The gate

`checks/check_name_coherence.py`, with `scripts/tests/test_check_name_coherence.py`. It scans the
git-tracked tree for a declared list of identifier spellings — never the English word, for the reason
above — and FAILS naming `path:line` and the token. Can-fail is parametrised over the gate's own
`BANNED` tuple, so a spelling added to the rule cannot ship without a demonstration.

**Exempt, and the exemption is the gate's own soft spot:** `CHECK-CONTRACT-AMENDMENTS.md` (this
file — the table above is the record), `CHECK-DEBT.md`, `sessions/SESSION.md`, `CLAUDE-CHANGELOG.md`,
`downloads/` (the architect's briefs, not ours to edit), `docs/superpowers/plans/` (dated plan
records from ARC 008–009), and the gate and its test, which must name what they ban. Every one of
those is a record whose function is to say what the vocabulary USED to be, and `CLAUDE.md`
directive 6 forbids rewriting banked evidence. **A future arc that widens that tuple to turn a red
green is doing the thing the doctrine names at B.4.**

### Residual, recorded rather than argued away

The gate cannot see an occurrence hidden inside its own source or its own test, because both are
exempt by name. `CHECK-DEBT.md` D3.23.

---

## CHECK-A7 — the declaration-only binding classifier is WITHDRAWN (ARC 027 ratified, recorded ARC 028 / 0.3)

| field | value |
|---|---|
| origin | Architect ruling, issued ARC 027 finding 0.3, ratified. Recorded to disk in ARC 028 / 0.3 |
| status | **WITHDRAWN, not narrowed.** The rule is gone; nothing replaces it |
| closes | nothing. It REMOVES a rule that governed binding verdicts across three arcs |

### The rule that is withdrawn

For three arcs, a check's binding verdict turned in part on a **declaration-only classification**:
whether a control reached the gate's *measurement path* or only its *declarations*, computed by
`scripts/nixverify/measurement_path.py`. A control that touched only declarations was not to count
as binding.

### The measured grounds, which are the point

`scripts/nixverify/contract.py` sits on **every check's verdict path** and changed in three
consecutive arcs. The classifier therefore answered "yes, the measurement path was reached" for
every check, in every arc, without exception. **A rule whose output is a constant decides nothing.**
It was not wrong; it was inert, while reading as though it were doing work — which is worse than
absent, because a binding table carrying its verdicts implied a discrimination that was never made.

`measurement_path.py` is **RETAINED as a STRUCTURAL instrument only.** It is what proved the
finding, and deleting the instrument that disproved a rule is how the disproof gets re-litigated.
It has no authority over any binding verdict.

### THE LABEL COLLISION — and why nothing in the check contract was edited to record this

The withdrawal was issued in the briefs as **"`0c`"**. It was NOT applied to
`nix_check_contract.md` or to `CLAUDE.md`, and that refusal is deliberate and measured:

> **``0c`` on disk is a DIFFERENT RULE, and it is live.** `CHECK-DEBT.md` D2.30 and D3.20 and
> `CLAUDE-CHANGELOG.md` all cite ``0c`` as *"a retrofitted check is a NEW check: its can-fail
> binding does not survive the retrofit and must be re-established, or it reverts to UNBOUND"* —
> ARC 025's `0c`, which ships today as **check-contract rule 9 in `CLAUDE.md`** and is load-bearing.

Withdrawing "`0c`" from the check contract by its label would have deleted the retrofit rule.
``0c`` is an **arc-brief section label**, and arc-brief labels are per-arc and collide across arcs;
they were never ledger identifiers and must not be treated as ones. The withdrawn rule had **no
on-disk name at all** — which is itself the finding: a rule governed three arcs' binding verdicts
without ever being written into the contract it governed, so nothing on disk could be edited to
withdraw it and nothing on disk could have contradicted it either.

**Standing consequence:** a rule that decides a check's verdict is written into
`nix_check_contract.md` and recorded here, or it does not bind. A brief may propose one; a brief is
not where one lives. See `SPEC-A6`'s header note and `CHECK-A6` for the same collision class one
level up, and `CHECK-DEBT.md` D3.81.

---

## CHECK-A8 — the declared exclusion: a guard with its re-owning ceiling lifted, and nothing else (ARC 029 / D3.104)

| field | value |
|---|---|
| origin | Architect ruling on **CHECK-DEBT D3.104**, issued to ARC 029, recorded here in the same arc |
| status | **LIVE, and explicitly a HOLDING mechanism.** The rule binds; this instance of it (thirteen artifacts) is temporary and owned by ARC 030 |
| governs | `check_artifact_gate_coverage` — adds a verdict-deciding classification, so it is written into the check contract (`CLAUDE.md` rule 14) and recorded here, per **check-contract rule 13** |

### What fired, and why the ceiling could not simply be obeyed

`check_artifact_gate_coverage` carries an operator-ruled **re-owning ceiling of two** (`CHECK-A`-era
D2.31, ARC 027): a guard's owner may be walked forward at most twice; the third re-owning escalates
GUARDED to FAIL. ARC 029 / 0.5 re-pointed all sixteen `gate_coverage_baseline.json` owners off the
**completed** `ARC 027` to `ARC 030` — the repair the gate's own CANNOT_MEASURE verdict had demanded
(*"re-point the marker at a live arc or take the red"*). Thirteen of the sixteen were **already at the
ceiling** (`the bulk check retrofit arc (ARC 025+)… -> ARC 025 -> ARC 027`), so the fourth owner was
one re-owning too many and the gate went FAIL. The lineage is derived from committed blobs, so the
red could not be edited away; reverting the owner to `ARC 027` restores a **completed arc as owner**,
which is the masking doctrine B.3 exists to refuse. The ceiling was working; there was no compliant
green available from inside the guard.

### The rule

A **declared exclusion** is an artifact moved out of the ratchet's `rows` (the ceiling-guarded set)
into a top-level `exclusions` object in `gate_coverage_baseline.json`. An exclusion **escapes the
re-owning ceiling and nothing else**:

* it is still inside the **one-way ratchet** — `exclusions` is folded into the accepted set the
  high-water mark judges, so a silent addition is an unadmitted-growth FAIL and an artifact that
  acquires real coverage is a stale-baseline FAIL, wherever it sits;
* it is still owned by a **live arc** — a completed owner is CANNOT_MEASURE (the honest "the holding
  state expired" verdict), which is what stops the bucket outliving ARC 030;
* it is still assigned under **§0g** — an owner naming the arc in flight is refused at write time;
* and it **must carry a written `justification` and `temporary: true`** per entry.

The one rule lifted is the ceiling, and it is lifted **only under this recorded amendment**. The gate
cannot tell an authorized move from a laundering one — that is exactly why the authorization lives in
this ledger and in the contract, not in the instrument (rule 13).

### This instance, and its exit

Thirteen ceiling-tripped artifacts are moved into `exclusions`, each justified, all owned by
`ARC 030`. **ARC 030 is the committed bulk-retrofit arc:** it builds real per-artifact can-fail
coverage for all thirteen, empties the exclusion, and drives `check_artifact_gate_coverage` green **by
measurement**. The exclusion is temporary and `CHECK-DEBT.md` D3.104 says so. The three below-ceiling
artifacts (`gitenv.py`, `measurement_path.py`, `registry.py`) are untouched and remain guarded rows.
Verdict under this amendment: **GUARDED**, owner `ARC 030` — a withheld certification, never a pass.

---

## CHECK-A9 — the declared exclusion extends to two more artifacts, on doctrine-C.9 grounds (ARC 031 / D3.138)

| field | value |
|---|---|
| origin | Architect ruling on **CHECK-DEBT D3.138**, issued to ARC 031, recorded here in the same arc |
| status | **LIVE, and explicitly a HOLDING mechanism**, exactly as `CHECK-A8` is. The rule binds; this instance (two artifacts, owner `ARC 032`, temporary) is CHECK-DEBT D3.138 |
| governs | `check_artifact_gate_coverage` — the same verdict-deciding classification `CHECK-A8` created, applied to two named paths. Written into the check contract (`nix_check_contract.md` §19) and recorded here, per **check-contract rule 13** |
| scope | `scripts/nixverify/gitenv.py` and `scripts/nixverify/registry.py`. **Two paths, named. Nothing else.** `CHECK-A8` was scoped to its thirteen and this is scoped to its two, for the same reason: the gate cannot tell an authorized move from a laundering one, so the authorization enumerates its subjects |

### What fired, and why every move was closed

ARC 031's Stage-3 integration had to re-point every row owned by `ARC 031` before the arc appended
its own `sessions/SESSION.md` summary — `guard_owner_defect` and `_exclusion_deferrals` are READ
rules that run on every read, so the moment `completed_arcs()` includes `ARC 031` those rows read as
owned by an arc that cannot pay (doctrine B.3; D3.40's mechanism). Eleven rows had headroom and were
moved to `ARC 032`. **These two did not: both were AT the operator's re-owning ceiling, 2 of 2.**

That left three moves and all three were defects:

  * **walk the marker forward** — the third re-owning, which is *precisely* the move that produced
    D3.120 one arc earlier, repeated in the same arc that discharged D3.120 by measurement;
  * **revert to a previous owner** — a COMPLETED arc as owner, the masking doctrine B.3 exists to
    refuse;
  * **manufacture a `checks/check_*.py`** — see below, and this is the one that decides the ruling.

ARC 031 took none of them, recorded D3.138 with both available architect moves named, and let the
gate go **CANNOT_MEASURE** — the honest "a real debt has an owner who cannot pay" verdict, kept
rather than edited away. **The gate predicted it, the write-back caused it, and the re-measure
observed it**; that sequence is the evidence this amendment rests on.

### The grounds: doctrine C.9, and why a check here would REDUCE the tree's honesty

Both artifacts already carry real can-fail coverage — **by tests, which is the honest kind**:

  * `scripts/tests/test_gitenv_hostile.py` drives `scrubbed_env` with the **both-halves control**:
    every invocation is run UNSCRUBBED first and required to report the DECOY repository, so the
    suite can distinguish *the scrub worked* from *`GIT_DIR` never mattered here*. That control is
    stronger than what a fresh check would be written with.
  * `scripts/tests/test_registry.py` (and three more modules, and every `verify.py` run) exercise
    plan loading directly.

A `checks/check_*.py` re-driving either would be the **second instrument for a property the suite
already owns** — doctrine C.9's forbidden duplicate. It would lower this ratchet's count while
covering nothing new, which is D3.19's defect exactly: *naming is not measuring*. The ruling
therefore grants the exclusion rather than demanding a check, because **the honest reading is that
these two are covered and this gate cannot see it** — `check_artifact_gate_coverage` counts
`SUBJECTS` declarations, and a test module cannot make one.

That asymmetry is the whole content of this amendment and it is worth stating plainly: **CHECK-A8's
thirteen were an OVERDUE-WORK holding state; CHECK-A9's two are an INSTRUMENT-BLIND-SPOT holding
state.** Same bucket, same constraints, different reason — and the difference is why D3.138 stays
open as a debt against the *instrument*, not against the artifacts.

### What is lifted, and what is not

Nothing new. `CHECK-A9` grants these two paths exactly what `CHECK-A8` grants its thirteen and
**not one rule more**:

  * still inside the **one-way ratchet** — `Baseline.uncovered` folds `exclusions` into the single
    accepted set, so a silent addition to either bucket is an unadmitted-growth FAIL and an artifact
    that acquires real coverage is a stale-baseline FAIL. **MEASURED: the accepted set is 13 before
    and 13 after** (7 rows + 6 exclusions → 5 rows + 8 exclusions), so the high-water mark cannot
    see this move at all — which is the property that makes it a re-classification and not a growth;
  * still owned by a **LIVE arc** (`ARC 032`) — a completed owner degrades the gate to
    CANNOT_MEASURE, so the bucket cannot outlive its owner;
  * still assigned under **§0g** (`_exclusion_assignment_defects`);
  * still carrying a written `justification` and `temporary: true` per entry
    (`_exclusion_shape_defects`).

The **one** rule lifted is the re-owning ceiling.

### The measured verdict

`check_artifact_gate_coverage`: **CANNOT_MEASURE (exit 2) → GUARDED (exit 3)**, owner `ARC 032`,
13 accepted in 5 per-artifact rows + 8 declared exclusions. A withheld certification with a live
owner — never a pass, and the `UNBOUND` (D3.10) caveat on the verdict line is unchanged: this gate
proves an artifact is NAMED by a check, never that it is MEASURED by one.

### Exit

D3.138 is **discharged as a ruling** and the exclusion is temporary by declaration. Discharge of the
*instance* is either real per-artifact coverage that this gate can see, or an architect retiring the
rows — the bucket is a holding state, not a resting place. See `CHECK-A8` for the mechanism, D3.104
for its instance, and D3.120 for the measured cost of the move this ruling exists to avoid.

---

## CHECK-A10 — `**** ARC completed ****` is the LAST token, or the arc reports IN FLIGHT (ARC 033)

| field | value |
|---|---|
| origin | Architect ruling, issued to ARC 033. Not doctrine text — `VERIFY-AND-CHECKS.md` is external, unversioned and has no amendment mechanism, so the change is implemented in `nix_check_contract.md` §16.4 and recorded here |
| status | **LIVE.** A reporting-protocol rule, binding on every arc close-out from ARC 033 forward |
| governs | `cc`'s close-out REPORT — the order of tokens in the final chat response. It governs no check's verdict and mutates no artifact |
| scope | The completion marker and everything that may precede or follow it. It does not touch §16.1's three obligations, does not waive §16.2's re-measurement, and does not change what an arc must bank |

### The rule

**`**** ARC completed ****` is the last token printed. Nothing follows it** — no re-measure, no
`cat`, no summary, no percentage, no commentary.

If a post-write-back re-measure is required, it runs and is reported **before** the marker, and the
marker is printed only once that final measurement is **itself banked**. If the arc cannot reach a
stable state where the marker is last, it prints **no marker** and reports `STATUS: IN FLIGHT`,
naming what is still moving.

### Why this is a ruling and not a style preference

The marker is a **certificate over a state**, and its entire content is *the banked state is final
and nothing followed it*. That makes trailing output not untidy but self-contradicting:

  * a trailing **measurement** either agrees with the certificate (making the marker redundant) or
    disagrees with it (making the marker false at the moment it was printed) — and §16.2 exists
    precisely because figures move, so disagreement is the expected case, not the unlucky one;
  * a trailing **remark** is indistinguishable, to a reader, from a trailing measurement. The reader
    cannot classify what they are looking at, because classifying it is what the marker was for.

**The asymmetry that decides it:** an arc loses nothing by printing its percentage and its run summary
first, and loses the certificate entirely by printing anything after the marker. One ordering has no
cost and the other has no recovery.

### What it does NOT do — the misreading this section exists to prevent

**It does not waive the post-write-back re-measure, and reading it that way inverts it.** Some
transitions can only be observed after the write-back: `contract.completed_arcs()` reads
`sessions/SESSION.md`'s `##` headings, so an owner naming the arc in flight becomes an owner naming a
COMPLETED arc the instant that arc appends its own summary, and `check_artifact_gate_coverage` moves
GUARDED → CANNOT_MEASURE. That is D3.40's mechanism; ARC 031 met it on D3.138 and ARC 032 met it again
on D3.144, both predicted in writing before the commit that caused them.

This amendment **orders** that work rather than removing it: write back and commit → re-measure the
merged tree → record the re-measurement forward-only (§0h) into both files **and commit it** → show
§16.1's three obligations against that commit → print the marker. An arc that reports a figure it has
not banked has not finished; it has narrated.

### The measured counter-example is ARC 032's own close-out

ARC 032 did the hard half right and the easy half wrong, which is why it is the example rather than a
hypothetical. It ran the re-measure, observed the predicted GUARDED → CANNOT_MEASURE, appended the
observation forward-only to both files and **committed it** (`125e8d5`) before reporting — and then
printed the marker, followed by a forward-movement percentage and a `===RUN SUMMARY: …===` line.

**Nothing false was said and no figure moved.** The defect is structural: the arc's last banked act
was a commit and its last printed act was a summary, and nothing in the transcript tells a reader that
the two tokens after the marker were commentary rather than a late measurement.

### The collision with the brief format, resolved

`CLAUDE.md`'s arc-end rule asks for the marker **and** an approximate percentage, and arc briefs
routinely require a `===RUN SUMMARY: …===` line "alongside the arc". Both are commentary about a
finished arc and both precede the marker. Where a brief's wording places the marker first, §16.4
governs — **§0b: the spelling was a sketch, the invariant binds.**

### NO CHECK IS OWED, and that is a real difference from every other §16 obligation

§16.1–§16.3 are properties of the repository and are owed checks under §1 as broadened by
`CHECK-A3`. **§16.4 is not.** Its subject is the order of tokens in a chat response — output that
reaches the operator's terminal and is written to no file in this tree — so no `checks/check_*.py`
can observe it, and recording a phantom debt for a check nobody could write would put a permanent
unpayable row on the §1 list. An unowed check is not an owed check nobody wrote.

The residual is stated rather than implied: this rule is enforced by reading, which is the weakest
enforcement this project has. It is accepted because the alternative — writing the marker into a file
so a gate could see it — would make the marker a property of a FILE, and the thing being certified is
the REPORT.

### Exit

None. This amendment has no holding state and no instance to discharge: it is a standing rule, not a
temporary authorisation. It is revocable by the architect like every ruling in this ledger.
