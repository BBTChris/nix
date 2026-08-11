# CHECK-CONTRACT-AMENDMENTS — amendments to the check/verify contract

**Status: a RECORD, not an authority.** Nothing here is doctrine text. Each entry describes
behaviour Nix implements that `VERIFY-AND-CHECKS.md` does not describe, or describes differently.

**`VERIFY-AND-CHECKS.md` is never edited in place.** It is external, inherited doctrine — its
audience line names *Luna*, not Nix — it carries **no version number** and **no amendment
mechanism**. There is nowhere inside it to put a Nix amendment, and editing another system's
doctrine to make Nix's implementation look conformant is the inverse of measuring. Amendments are
therefore **implemented in the derived spec `nix_check_contract.md`** (v1.2.0) and **recorded
here**. The doctrine keeps its authority over everything it does say.

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

## AMENDMENT 1 — `GUARDED`, a fourth exit code

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

## AMENDMENT 2 — actuation: verify / correct / install, and the independent re-verify

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

## AMENDMENT 3 — the coverage trigger broadened

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

## Standing note for the architect

Open items this ledger records and does not resolve (ARC 024 returned them to the operator):

1. **`manifest.json` vs `registry.json`** — the operator ruling names `checks/manifest.json`; the
   file on disk is `checks/registry.json`, named per doctrine A.4/D.5 and renamed from
   `verify_manifest.json` in ARC 010. **Not resolved silently in either direction.**
2. **Guarded's meaning** — the colour was ruled, the semantics above are the architect's proposal.
3. **The non-correctable class** — ratify or narrow the three proposed members.
4. **The safety interlock** — ratify.
5. **`--optimize`** — propose-then-commit is implemented; overwrite-in-place was the alternative.
