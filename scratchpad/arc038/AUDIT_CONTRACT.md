# ARC 038 — ULTRAREVIEW: Risk Engine / Limiter (pass 1) — SHARED AUDIT CONTRACT

You are ONE of seven parallel adversarial sub-agents (A–G) auditing a FROZEN module.
Read this whole file before acting. Your per-agent assignment is in your own prompt.

## THE CANONICAL PATH

`/home/bbt/nix` is the canonical primary tree. **You do not work there.** You work
ONLY inside your own worktree, whose absolute path is in your prompt. Never write to
`/home/bbt/nix` and never write into a sibling worktree. Your worktree already has
`state/` and `.venv/` symlinked in (`scripts/provision_worktree.sh` did it) and its
`check_node_identity` passes.

Interpreter: `<WORKTREE>/.venv/bin/python` (CPython 3.14.4). State it in your report.
For pytest: `<WORKTREE>/.venv/bin/python -m pytest`.

## WHAT THIS ARC IS — AND IS NOT

It BUILDS NOTHING. It attacks the built Limiter (`scripts/nixrisk/*.py`, 30 modules,
~20k LOC) and asks of every locked invariant in the frozen spec's §14:

> **what would have to be true for this to hold in the tests while being FALSE in
> reality?**

The Limiter already passed a DESIGN ultrareview (spec §16, "locked, ULTRAREVIEW-2").
This is the IMPLEMENTATION ultrareview.

### THE FREEZE (0.2) — BINDING

No production Limiter code change is permitted **except to discharge a finding YOUR
OWN AUDIT RAISED AND NAMED**. No features. No refactor for taste. No renames, no
type-annotation tidying, no docstring improvements, no "while I was here".
**A Stage-1 change to a frozen file that is not tied to a named finding is ITSELF a
finding, and the integrator will find it by diffing against the frozen SHAs**, which
are recorded at `/home/bbt/nix/scratchpad/arc038/frozen_limiter_shas.txt`.

If you fix something, the fix must be minimal, local, reversible, and the finding must
be written down FIRST (in your findings file) with the exact site.

## READ THE SPEC DIRECTLY — NEVER A PARAPHRASE

Authority is `docs/nics_risk_subsystem_spec_v1.3.md` (FROZEN — never edit it). Read the
sections your invariants live in, by line number, from that file:

- §3 Canonical Trade Pathway (single-pass routing, two-phase rule logic) — line 111
- §4 State Model — line 178
- §6.5 Liquidity governor (mixed) — line 408
- §9 Persistence Model (event-sourced) — line 549
- §11 Performance & Hot-Path Discipline — line 579
- §14 Locked Invariants — line 965
- §15 Audit v1.1 Changelog (C1 reservation lifecycle / double-spend race, C2 net-liq vs
  cash, C3 sizing guards, C4 blackout onset cancels pending entries, C6 GO-timeout) — 983

`docs/nics_risk_subsystem_spec_v1.4.md` is a mechanical fold and **is NOT the authority
and must not be cited.** Cite v1.3 as `§x:line`.

Also relevant, read on demand: `docs/VERIFY-AND-CHECKS.md` (doctrine, outranks the
derived contract), `docs/nix_check_contract.md` (derived, v1.5.0), `docs/CHECK-DEBT.md`
(the ledger — read it, but see the WRITE rules below), `CLAUDE.md`.

## METHOD — REAL INTERPRETER, REAL BOUNDARIES. NO MENTAL WALKTHROUGHS.

A claim you did not execute is not a measurement. Specifically:

- `asyncio.run` where the code is async; real threads where it is threaded.
- Real subprocesses for anything crossing a process boundary. `pgrep` / `/proc` for
  liveness. **Real `SIGKILL`** for death (`os.kill(pid, signal.SIGKILL)`, then reap and
  assert the `-9`).
- **Real Postgres** for the record (Plane 1). The cluster is the system PostgreSQL.
  Look at `scripts/nixrisk/plane1_sink.py` and `scripts/provision_plane1.py` for how
  the tree reaches it; look at `checks/check_plane1_*.py` for how the existing gates do.
  If you genuinely cannot reach the real boundary, that is a **Cannot-measure**, stated
  as such with the reason — never a Pass, and never a FakeIB-only proof standing in for
  an available real boundary (`nix_check_contract.md` §10, rule 10).
- Real sockets for the state bus (`ipc://`), real `/dev/shm` for the price ring.
- **Clean up what you create**: kill every child, close every socket, unlink every
  `/dev/shm` segment you open. D3.347 is a measured case where fourteen leaked
  `nix_drill_*` segments silently HUNG a later suite for a whole census run. Name your
  segments with your own pid and reap them in a `finally`.

## THE AUDIT CONTRACT, PER INVARIANT — three obligations, all three required

For EACH invariant assigned to you:

**(a) A RED-TEAM ATTEMPT.** A real adversarial scenario, executed, that tries to
violate the invariant. Corner it: concurrency, ordering, death mid-operation, a
dependency removed, a value poisoned, a duplicate, a late arrival, a race.

**(b) EITHER a reproduced violation OR a proof of resistance.**
- A reproduced violation is a FINDING: exact file:line site, the scenario, the observed
  wrong state, and the invariant it breaks.
- A proof of resistance is **the attack FAILING to break it**, shown by output. It is
  NOT "I looked and there is no such path", and it is NOT the attack being absent.
  If the attack could not be mounted, say Cannot-measure and why.

**(c) AN AUDIT OF THE EXISTING GATE that claims to cover the invariant.**
Find the `checks/check_*.py` (and/or `scripts/tests/test_*.py`) that claims this
invariant. Then:
1. **NON-VACUITY FIRST**: prove the gate's SCOPE actually CONTAINS its subject. A gate
   that never opens the file, never imports the module, or never reaches the branch is
   green over nothing. Show the scope containment by measurement.
2. **PLANT THE VIOLATION** in the real subject, run the gate, and require it to (i) go
   RED and (ii) NAME THE SITE. Then remove the plant and require it to go green.
3. If it stays GREEN under the plant, that gate **measured nothing** — a finding of the
   ARC 037 / ARC 035 class. **Assume at least one existing Limiter gate is green over a
   real gap; the project has found one nearly every arc.**

## §0a — THE AUDIT INSTRUMENT IS ITSELF UNDER AUDIT

Every audit control YOU write must prove it CAN fail: plant the exact violation,
confirm your control reddens AND names the site, remove the plant, confirm it passes.
An audit that never sees the invariant broken has measured nothing — the cardinal sin
in an ULTRAREVIEW.

Two specific self-deceptions this project has MEASURED, and you must rule out in your
own instruments:

1. **The inherited-`PYTHONPATH` staged-tree defeat (D3.344, ARC 037).** Two suites
   called `subprocess.run` with **no `env=`**, so a gate launched against a STAGED,
   PLANTED copy of the tree inherited `PYTHONPATH` pointing at the REAL
   `/home/bbt/nix/scripts` and imported the PRODUCTION module. Every plant was
   defeated and the gate PASSED while reporting on the staged tree. **If you stage a
   tree and plant in it, you MUST pass an explicit `env=` to the child and you MUST
   prove the child imported from the staged path** (e.g. assert the module's
   `__file__` in the child, printed from the child). The safe-direction repair that
   is ALSO wrong: replacing `PYTHONPATH` wholesale drops the binding census's
   `sitecustomize` directory and makes your run invisible to the census — filter the
   real-tree entries and keep the rest.
2. **Controls masking themselves (ARC 035, three times).** A both-halves control must
   run the UNPROTECTED half first and require the bad outcome to appear, then the
   protected half and require it gone. A control that only ever runs the protected
   half proves nothing.

**Every control asserts the REASON — a message, a site, or a field — NEVER the exit
code alone** (check contract rule 11, `nix_check_contract.md` §18). An exit code is a
shared namespace: the detector firing, the instrument breaking and the interpreter
refusing to start all reach the same integer.

## WHAT YOU MAY WRITE, AND WHERE

1. **Your findings file — REQUIRED.** `downloads/arc038_findings_<LETTER>.md` in your
   worktree, in the format below. This is your deliverable of record.
2. **Audit instruments — REQUIRED where you claim a control.** New pytest suites at
   `scripts/tests/test_arc038_<letter>_<subject>.py`. These must pass under
   `<WORKTREE>/.venv/bin/python -m pytest <file>` and must contain the plant/restore
   can-fail proof of themselves. Match the surrounding suites' idiom (read two or three
   neighbours in `scripts/tests/` first — module docstring stating what would have to
   be true for this to measure nothing, `§7.12`-style, is the house style).
3. **A `checks/check_*.py` ONLY if a finding genuinely needs a STANDING gate** and no
   existing gate can be pointed at it. If you add one you MUST also add `DEPENDS_ON`,
   `RESOURCES`, `ON_FAIL`, `SUBJECTS` declarations and register it in
   `checks/registry.json`. Prefer pointing an EXISTING gate at the gap, or a pytest
   suite. Say in your report which you chose and why. **Doctrine C.9 forbids a second
   instrument re-asserting what an existing suite already asserts.**
4. **Debt rows.** Do NOT edit `docs/CHECK-DEBT.md` — five branches editing one table
   is how ARC 037 got cross-branch defects. Instead write your rows to
   `downloads/arc038_debt_<LETTER>.md` as ready-to-paste table rows in the ledger's
   exact 6-column format:
   `| D3.NNN | **<headline>** | ARC 038 (<your stage>), MEASURED | <body: mechanism, the drive, the numbers, what discharge would be> | <owner arc> | <owning module token> |`
   Use ONLY ids from **your reserved block** (in your prompt). The `owning module`
   column is an AUTHORED controlled vocabulary — read the vocabulary section of
   `docs/CHECK-DEBT.md` (heading "The controlled vocabulary") and use one existing
   token. **For `scripts/nixrisk/` the token is `limiter`** (`docs/CHECK-DEBT.md:349-364`);
   for a check/gate/`scripts/nixverify/` subject it is `verify`; for `scripts/nixbus/`
   or the price ring it is `capture`. **There is NO `risk` token — an unknown token is a
   loud `ProbeError`, not a silent exclusion.** (Corrected mid-arc: this file said `risk`,
   which does not exist. Sub-agent D measured it against the vocabulary table.)

## WHAT YOU MUST NOT TOUCH

- `/home/bbt/nix` (the primary tree) or any sibling worktree.
- `docs/nics_risk_subsystem_spec_v1.3.md` (frozen), `docs/nics_risk_subsystem_spec_v1.4.md`.
- `docs/CHECK-DEBT.md`, `sessions/SESSION.md`, `downloads/RESULTS.md`,
  `checks/gate_coverage_baseline.json`, `CLAUDE.md`, `CLAUDE-CHANGELOG.md`.
  (The integrator owns all of these.)
- Any `scripts/nixrisk/*.py` file, unless discharging a finding you named. See FREEZE.
- Any module outside the Limiter's own neighbourhood. Scope creep ends the audit.

## GIT DISCIPLINE — MEASURED RULES, NOT STYLE

- `git add -A` **before every gate measurement**. Generated files that must not reach
  the index are covered by `.gitignore` (D2.24: ignore-rules-per-target).
- **D3.205 / D3.22: scrub the git environment on EVERY subprocess git call.** Use
  `scripts/nixverify/gitenv.py` (read it) rather than inventing a scrub. An inherited
  `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` has, measured, re-pointed a subprocess
  git call at the wrong repository.
- Commit to YOUR branch only, in small commits with real messages that say what was
  measured. Leave your branch committed and clean (`git status --short` empty) when you
  finish — the integrator merges from your branch. **Uncommitted work is lost work.**
- Never `git rebase`, never `git push`, never `git checkout main`, never
  `git worktree remove`.

## YOUR FINDINGS FILE FORMAT — follow it exactly

```markdown
# ARC 038 sub-agent <LETTER> — <title>

Worktree: <abs path>   Branch: arc-038-<letter>   Interpreter: <path> (CPython x.y.z)
Invariants assigned: <I..>

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I<n> | <one line> | VIOLATION / RESISTED / CANNOT-MEASURE | check_x | yes/no + how proven | yes/no + the site it named |

## FINDINGS  (one block each; if none, say "NO FINDINGS" and show why that is a
##            measurement and not an absence)

### F<LETTER><k> — <headline>
- **Invariant:** I<n>  (spec §x:line, quoted)
- **Site:** `path/to/file.py:LINE` — `<the exact expression or call>`
- **Scenario (executed):** <what was driven, in a real interpreter, with the command>
- **Observed:** <the wrong state, with the actual numbers/messages printed>
- **Why the tests did not catch it:** <the specific reason>
- **Status:** DISCHARGED IN THIS ARC (with the control that proves it and the proof
  that the control can fail) | BLOCKS (nothing fixed) | DISCHARGED-BY-GATE
- **Debt row:** D3.NNN

## PROOFS OF RESISTANCE  (the attacks that FAILED to break the invariant)

### R<LETTER><k> — I<n> held
- **Attack:** <what was driven>
- **Command + output:** <paste the real output that shows the attack failing>
- **What this does and does NOT prove:** <be precise about the residual>

## GATE AUDIT  (per gate, the non-vacuity + plant/restore evidence)

### check_<name>
- **Claims:** <invariant>
- **Scope containment proven by:** <measurement>
- **Plant:** <the exact edit>  → **verdict:** RED naming `<site>` / **GREEN (FINDING)**
- **Restore:** byte-identical? <how proven> → verdict green again?

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL
| suite/control | plant used | reddened? | site named | restored green? |

## WHAT I COULD NOT MEASURE, AND WHY
## FILES I CHANGED (path — why — tied to which finding)
## COMMITS (sha — subject)
```

## HOW TO FINISH

1. Everything committed on your branch; `git status --short` empty.
2. Your findings file and debt file present and committed.
3. Run the Limiter-relevant part of the suite in your worktree and report the numbers:
   `<WORKTREE>/.venv/bin/python -m pytest scripts/tests -q -k "risk or limiter or gate or reservation or flatten or picture or plane1 or halt or blackout or survival or fill or execution"`
   plus your own new suites. If you changed a frozen file, run the FULL suite.
4. Your final message back to the integrator is a COMPACT summary: the verdict table,
   the finding headlines with sites and status, what you could not measure, your
   commits, and your suite numbers. Do not paste your whole findings file.

## THE BADGE RULE — why "understood but not fixed" is not good enough

The Limiter's status-board badge flips red ✗ → green ✓ **only when EVERY finding this
audit surfaces is DISCHARGED, not deferred.** ULTRAREVIEW findings may NOT be banked
forward — that is the whole difference from a build arc. So: if you CAN discharge a
finding inside the freeze (a minimal, local, reversible fix tied to the named finding,
with a control that proves the fix AND is proven able to fail), **do it**. If you
cannot, say so plainly and it defines ARC 039. Do not soften a finding into an
observation to keep the badge, and do not inflate a style preference into a finding.
