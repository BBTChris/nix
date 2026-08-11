# ARC 024 — The Check Contract: Plane 2, Actuation, Orchestration

**Module:** verify.py / checks subsystem
**Predecessor:** ARC 023 (must be merged before this arc starts)
**Origin:** operator design session, recovered and transcribed by the operator. Treated as
operator ruling, not architect proposal, except where marked **[ARCHITECT RULING]** below.

---

## §0a — Self-audit clause (standing)

Before acting on any instruction in this brief, `cc` asks: *what would have to be true for this
step to complete successfully while measuring nothing?* Any step whose success is compatible with
measuring nothing is a defect in this brief. Report it, do not silently satisfy it.

## §0b — Architect spellings are non-binding (standing, from ARC 023)

Every concrete spelling in this brief — file layouts, discovery mechanisms, flag names, schema
shapes — is a sketch, not a contract. The **invariants** are binding; the spellings are not. If
implementing a spelling as written would degrade an instrument, blind a gate, or make a check
report over a subject it never drove, **refuse it with a measurement** that shows the degradation,
then implement the invariant a different way and record the substitution.

Precedent: ARC 022's A1 roster-derivation sketch would have blinded two gates to CANNOT_MEASURE and
reddened four claims invisibly. `cc` refused it with measurement. That was correct and is now policy.

## §0c — Retrofit invalidates binding (new doctrine, this arc)

**A retrofitted check is a new check.** Any check modified to add actuation verbs, dependency
declarations, resource claims, or a new status loses its D3.10 binding at the moment of
modification. Its can-fail proof against a real subject must be re-established, or it reverts to
UNBOUND. ARC 023 spent an entire arc binding gates; this arc must not silently unbind them.

---

## PHASE 0 — Reconciliation (no build until all six report)

Nothing in Stage 1+ starts until these are answered from disk, not from this brief.

**0.1 — ARC 023 close-out.** Confirm 023 merged. Report HEAD, `verify.py` exit code, the pass /
fail / cannot-measure triple, pytest count, CHECK-DEBT level. Confirm `~/nix/downloads/RESULTS.md`
was actually rewritten by 023 and is not a stale carry-forward (`head -1`, plus
`grep -c "ARC 023" ~/nix/sessions/SESSION.md`).

**0.2 — `manifest.json` vs `registry.json` (NAME CONTRADICTION — do not resolve silently).**
The operator ruling names `~/nix/checks/manifest.json` as the master execution plan. The architect's
record of this repo names `~/nix/checks/registry.json`. Report the actual on-disk state: which
files exist, their schemas, what reads them, and whether they are the same artifact under two names,
two artifacts with different jobs, or one name that is simply wrong. **Do not rename, merge, or
create either file in Phase 0.** Report and stop; the operator rules on the name.

**0.3 — TUI census.** Does `verify.py` have a TUI today? Report its actual output surface: TTY
detection, colour usage, progress rendering, what it writes to stdout vs stderr, and whether any
of it is already structured. The colour/progress ruling in Stage 4 presumes a surface to render to;
if there is none, say so — building one is arc scope and must be sized.

**0.4 — Check census (this sizes every later arc).** Full inventory of `~/nix/checks/`: every
check file; which are referenced by the manifest/registry and which are orphaned; which are in
CHECK-DEBT; which carry known-red markers; which are BOUND / UNBOUND / RETIRED / DEFERRED after
023. Report the count. The operator's estimate is **hundreds when complete** — the current number
is the denominator for the retrofit plan.

**0.5 — Authority-document reconciliation.** `CLAUDE.md`'s spec table does not list
`VERIFY-AND-CHECKS.md`, `nix_check_contract.md`, or `CHECK-DEBT.md`, yet the check contract is
governed by them. Report what exists on disk, each file's version, and which is the actual
authority for the check contract. A governing document absent from the load table is the same
defect class as an unloaded load-always rule.

**0.6 — `debug.md` version drift.** `CLAUDE.md` cites `debug.md` **v1.1.0** in two places
(`Rules` table derivation column, `Specs` table). The architect's record says on-disk is **v1.2.0**.
Per `CLAUDE.md`'s own derivation invariant, a version bump regenerates the derived rule
(`debugging.md`) in the same arc. Report actual on-disk version of both, and whether the
regeneration ever happened. If drifted, that is a finding and is repaired in Stage 5.

---

## STAGE 1 — Plane 2 logging foundation (SERIAL, first)

Operator ruling: logging is built **first**, because `verify.py` must log events to the system log.

Spec authority: `nics_risk_subsystem_spec_v1.3.md` §12.10, two-plane model, locked.
- Plane 1 = Postgres, **Limiter sole writer**, financial truth. **Not this arc. No new Plane-1
  writers, ever.** `verify.py` never writes Plane 1.
- Plane 2 = journald/syslog, each process writes its own structured one-line events
  (UTC timestamp, process, event, key=value), **diagnostic only, never a reconciliation input**.
- `directory_structure.md` pins `logs/` to non-Plane artifacts only (Sentinel marker, backup
  staging, web logs). **Plane 2 never lands in `logs/`.**

**1.1 — Emission.** `verify.py` emits Plane-2 structured events to the journal. Note the wrinkle
and solve it explicitly: §12.10 gets stdout→journald free *because every process is
systemd-managed*. `verify.py` is run interactively from a shell and is not. Free routing does not
apply — an explicit journal path is required. Measure what is actually available on node02 before
choosing (`python-systemd` / `JournalHandler` / `SysLogHandler` to `/dev/log` / `systemd-cat`);
do not assume a package is present.

Minimum event inventory for this run: run start (with args), per-check start, per-check verdict
(check name, status, exit code, duration), actuation attempted (verb, target), actuation
re-verify outcome, run end (aggregate triple). Field format per §12.10.

**1.2 — Gate: `checks/check_verify_logging.py`.** Per the standing check-script rule. Non-vacuity
is the whole point here: **a handler attached to a logger that never emits, or that emits into a
dead socket, must FAIL, not PASS.** The gate reads the journal back (`journalctl`) and proves a
known emitted event landed with the expected fields. Ships with a demonstrated FAIL path
(control: emission disabled ⇒ exit 1). Standing question applies: what would have to be true for
this gate to pass while measuring nothing?

**1.3 — Presentation is not the event stream.** The TUI surface (colour, spinners, progress bars,
count-up timers) goes to the terminal only and **must never enter the journal**. Prove it: a
non-TTY run (piped, redirected, `script`-less) emits zero ANSI escapes and zero spinner frames
into Plane 2, and degrades to plain sequential output on stdout. A journal full of spinner frames
is a corrupted diagnostic plane.

---

## STAGE 2 — The check contract amendment (SERIAL, must land before any retrofit)

The operator ruling changes what a check *is*. That is a contract change, not an implementation
detail, and it is written down before code moves.

**2.1 — Actuation verbs (operator ruling 1).** Every check must be able to **verify**, **correct**,
and **install**, selected by passed-in flags.

**[ARCHITECT RULING — revocable]** Default is measure-only. A check invoked with no flags **never
mutates anything**. `--correct` and `--install` are explicit opt-in, per-invocation. Reason: this
arc converts every instrument in the system into an actuator. On a trading platform, a default that
can mutate turns a diagnostic run into an unreviewed change to a live system. If the operator wants
correction on by default, say so and I will reverse it — but it should be a decision, not an
inherited default.

**2.2 — Post-actuation re-verify (operator ruling 3).** When a check corrects or installs, it runs
a verify afterwards to confirm the change actually happened.

**[ARCHITECT RULING — revocable]** The re-verify must be an **independent re-measurement**, not a
return value from the correcting code path. Concretely: re-exec the check in verify-only mode as a
fresh subprocess and read real effective state. Reason: a correct-then-confirm loop that shares
process state with the thing that did the writing is the project's signature defect — an instrument
reporting on a state it just wrote. `correct()` returning `True` and the check reporting PASS on
that basis is a vacuous pass by construction. **The re-verify must be able to fail after a
successful-looking correction, and that must be demonstrated with a control.**

**2.3 — The non-correctable class.**
**[ARCHITECT RULING — revocable]** Some checks declare themselves permanently non-correctable and
refuse `--correct`/`--install` loudly. Proposed members: anything on the order path; anything
touching credentials or `state/` (0600); anything that would mutate broker session state, clientId
assignments, or open positions. Reason: §4 prohibits auto-resend on the order path for exactly this
reason — automatic remediation there converts one intended action into two. Operator to ratify or
narrow the list.

**2.4 — Safety interlock.**
**[ARCHITECT RULING — revocable]** `--correct` and `--install` refuse to run when a trading session
is active or positions may be open, and say why. Reason: fail-closed doctrine. Nix's whole risk
posture is that uncertainty resolves toward flat; a remediation pass that mutates the box mid-session
resolves uncertainty toward change.

**2.5 — Status contract (operator ruling on TUI colours).**
Operator ruling: red = Failed · yellow = **Guarded** · green = Passed · light blue = Cannot run or
check.

This is a **fourth state**. The existing contract in `VERIFY-AND-CHECKS.md` is
`0=PASS / 1=FAIL / 2=CANNOT-MEASURE` — three states. Adding Guarded amends a frozen authority
document and must be recorded as an amendment, not an edit-in-place.

**[ARCHITECT RULING — revocable]** Proposed semantics, because the ruling gave the colour but not
the meaning: **Guarded = the check's subject is real and measured, but the check carries a known-red
marker naming the specific future arc that discharges it.** It is neither a pass (nothing was
proven) nor a failure (nothing is broken) — it is a deferral with an owner. Mapping:
`green→0` · `red→1` · `light blue→2 (CANNOT-MEASURE)` · `yellow→3 (GUARDED, new)`.
Consequence to state plainly: **Guarded withholds certification but never durability** — the arc
still banks, recorded NOT CERTIFIED. If the operator meant something else by Guarded, this is the
place to correct it.

**2.6 — Amendment artifact.** Write the amendment; do not edit the frozen document in place. Record
in the project's amendment ledger alongside Amendments 1–5. Read `VERIFY-AND-CHECKS.md` **directly**
when writing this — never work from this brief's paraphrase of it.

**2.7 — Coverage rule broadened (operator ruling 4).** The standing rule today is: any arc that adds
a package, sets an OS-level variable, or makes an environment change builds a
`checks/check_<property>.py` gate. The operator ruling **broadens the trigger**: *any time any module
or setting is written to disk or changes*, an associated check script must be added. Record the
broadened trigger in the contract document, not only in this brief.

**Gate obligation.** A doctrine this broad is unenforceable as prose and will rot into a slogan.
Build `checks/check_artifact_gate_coverage.py`: enumerate the tracked module and config artifacts,
and enumerate the subjects declared by the check population (the declaration mechanism from 3.3
supplies this); any artifact with **zero** declaring check is a FAIL naming the artifact.

**[ARCHITECT RULING — revocable]** This gate ships **UNBOUND** per D3.10 and must say so. It proves
that *some check names the artifact*, which is a weaker property than *some check measures the
artifact*. A check naming a subject it never drives is D3.16 exactly, and this gate cannot see that
class. Do not let its green be read as coverage. Binding it is a named future arc.

---

## STAGE 3 — Orchestration: `manifest.json`, blocks, `--optimize`

Subject to the Phase 0.2 name ruling. Written here as `manifest.json` per the operator.

**3.1 — Block model (operator ruling 7).**
- The manifest is the **master plan for order of execution**, expressed as blocks.
- A block containing **one** check, connected to another block, runs **sequentially**.
- A block containing **multiple** checks runs those checks **in parallel, each in its own process**,
  and **by definition they have no dependency on one another**.
- The manifest is ordered **least-dependent to most-dependent**.
- **Every check declares its dependency to `verify.py`.**

**3.2 — Disjointness is proven, not asserted.**
**[ARCHITECT RULING — revocable]** "By definition no dependency" is a claim, and an unproven claim
about parallel safety produces flaky greens that look like flaky infrastructure. Each check
therefore declares the **resources it claims** (ports, clientIds, files it writes, services it
restarts, the journal, `state/`), and a block is only valid as parallel if its members' claimed
resource sets are **disjoint**. Validation is mechanical and fails loud.

The concrete hazard is not hypothetical: clientId **1** (Risk Engine), **2** (datafeed), **905**
(diagnostics) are distinct precisely because IBKR sessions collide. Two checks in the same parallel
block both opening a diagnostic session will produce an intermittent failure that reads as a network
problem. Prove disjointness or run them sequentially.

**3.3 — Dependency declaration mechanism.**
Invariant: `--optimize` must be able to read every check's declared dependencies and resource claims
**without executing the check's measurement logic**.

**Spelling deliberately not specified** — §0b applies, and this is exactly where ARC 022's A1 trap
lived. Import-to-read executes module-level code; AST-parse is brittle to expression form. Measure
both against the real check population from Phase 0.4, pick one, and **demonstrate the failure mode
of the one not chosen**. If a check's declaration is unreadable by the chosen mechanism, that is a
loud error, never a silent default of "no dependencies" — a check that silently declares nothing
lands in a parallel block it does not belong in.

**3.4 — `--optimize` (operator ruling 7).** `verify.py --optimize` reads `~/nix/checks/` for check
scripts and builds an optimized `manifest.json`.

**[ARCHITECT RULING — revocable, and I recommend this deviation explicitly]** The ruling says
`--optimize` **overwrites the existing** manifest. I recommend it does **not** overwrite by default.
Instead: write `manifest.json.proposed`, print a diff against the current manifest, and require an
explicit second flag (`--commit`) to install it. Reason: the manifest is the master execution plan
for eventually hundreds of checks. A single bad derivation that silently overwrites it destroys the
ordering with no recovery point and no diff to review — and the failure surfaces later as checks
running in the wrong order, which reads as a product bug, not a tooling bug. One keystroke of
friction, full auditability. **Operator's call — say the word and it overwrites.**

**3.5 — `--optimize` must fail loud on:**
- **Cycles.** Topological sort with cycle detection. A cycle is an error naming the participating
  checks; never a silently chosen order.
- **Orphans.** A check file present in `checks/` but absent from the manifest. This is the
  **fifth instance** of the project's tracking-state-sets-gate-scope defect class (bandit scanning
  nothing · pre-commit skipping untracked · `--all-files` missing untracked · D2.24's ignore
  spellings). Deriving the manifest from the folder is the structural fix — prove it works.
- **Undeclared dependency.** A check that declares nothing when the mechanism expects a declaration.
- **Non-disjoint parallel block.** Per 3.2.

---

## STAGE 4 — TUI surface

**4.1 — Status colours (operator ruling).** red = Failed · yellow = Guarded · green = Passed ·
light blue = Cannot run or check. Semantics per 2.5.

**4.2 — Progress rendering (operator ruling).**
- **Time-bound event** (duration knowable in advance) ⇒ **text progress indicator**.
- **Non-deterministic duration** ⇒ **spinner with a count-up clock**.

**4.3 — Which is which is declared, not guessed.** A check declares whether its runtime is
time-bound and, if so, its expected duration. **Do not anchor an expected duration to a moving
value** (standing check-script rule) — a progress bar calibrated against last run's timing silently
becomes wrong.

**4.4 — Degradation.** Non-TTY ⇒ no ANSI, no spinner frames, plain sequential output. Per 1.3, none
of this reaches Plane 2. Prove with a piped run.

---

## STAGE 5 — Doctrine to disk

**5.1 — Write the recovered doctrine into `~/nix/CLAUDE.md`.** Operator instruction. Keep
`CLAUDE.md`'s existing character: durable invariants only, extremely concise, no workflow detail.
Detail belongs in the check contract document and `.claude/rules/`, not the root file.

New section, roughly:

> ## Check contract (v2 — actuation)
>
> 1. Every check verifies, corrects, and installs, selected by flags. Default = measure-only;
>    a flagless check never mutates.
> 2. Correct/install is followed by an **independent** re-measurement (fresh process, real
>    effective state). A return value from the correcting path is not a verification.
> 3. Any module or setting written to disk, or changed, ships an associated check script in the
>    same arc. Broader than the prior environment-change trigger; supersedes it.
> 4. Status: green=Pass(0) · red=Fail(1) · light blue=Cannot-measure(2) · yellow=Guarded(3).
>    Guarded = measured subject, known-red marker naming the discharging arc.
> 5. `checks/manifest.json` is the master execution plan. Blocks ordered least- to most-dependent.
>    Single-check blocks run sequentially; multi-check blocks run in parallel, one process each,
>    and their members must claim disjoint resources — proven, not asserted.
> 6. Every check declares its dependency to `verify.py`.
> 7. `verify.py --optimize` derives the manifest from the folder. Cycles, orphans, undeclared
>    dependencies, and non-disjoint parallel blocks are loud errors.
> 8. `verify.py` emits Plane-2 structured events to journald (§12.10). Presentation output never
>    enters the journal; Plane 2 never lands in `logs/`.
> 9. A retrofitted check is a new check: its can-fail binding does not survive the retrofit.

**5.2 — Changelog.** Append to `~/nix/CLAUDE-CHANGELOG.md` per `CLAUDE.md`'s change-control rule.

**5.3 — Repair Phase 0.6 drift** if found: `debug.md` version references in `CLAUDE.md`, and
regenerate `debugging.md` if the derivation invariant was missed.

---

## STAGE 6 — Pilot retrofit ONLY (operator ruling 2, deliberately scoped down)

Operator ruling 2 is to go back and retrofit **all** existing checks. **This arc retrofits two or
three, as reference implementations, and stops.** Rationale is stated plainly rather than assumed:

- The contract in Stage 2 is unproven until something real is built against it. Retrofitting the
  whole population against an unproven contract means re-doing the whole population.
- §0c: every retrofit unbinds a gate. ARC 023 just spent an arc binding them. Unbinding the entire
  population in one arc destroys that work with no staged recovery.
- Phase 0.4 supplies the count. Sizing the bulk retrofit is an output of this arc, not an input.

**6.1** — Select pilots spanning the shape space: one trivially correctable (a config/setting), one
installable (a package/unit), one **non-correctable** (order-path or credential-adjacent, to prove
the refusal path fires).

**6.2** — Each pilot: full flag surface, independent post-actuation re-verify with a demonstrated
control, dependency declaration, resource claims, time-bound declaration, Plane-2 emission.

**6.3** — Re-establish can-fail per §0c for each pilot against its **real** subject. D3.10's lesson
holds: can-fail proven only against a fake does not transfer.

**6.4** — Output a sized plan for the bulk retrofit: count, grouping, arc-by-arc split, and which
checks are non-correctable.

---

## PHASE 7 — Close-out

1. `verify.py` full run. Baseline is `check_ibgateway_service` FAIL + `check_ibgateway_config`
   cannot-measure (Gateway daily 03:00 expiry), plus whatever 023 settled. **A further FAILURE is a
   finding, and so is any further NON-PASS whose cause is not named.**
2. Full pytest, pre-commit all hooks, derived-claims harness, CHECK-DEBT level.
3. `git add -A` before every gate measurement — but per D2.24, prove the ignore rules resolve per
   target first; do not stage a `state/` symlink into a 0600 credential directory.
4. Standing write-back gate:
   - Append arc summary to end of `~/nix/sessions/SESSION.md`
   - **Overwrite** `~/nix/downloads/RESULTS.md` with this arc's results
   - `cat` both files as the final action, paste resulting state into the response
   - **Additionally, confirm `RESULTS.md` was actually rewritten this run** — not merely that the
     write-back gate reported success. A stale file is indistinguishable from a gate reporting green
     over a file it never wrote. This bit us in the 022→023 handoff.
5. Only then: `**** ARC completed ****`

**Run summary line, required:**

`===RUN SUMMARY: Check Contract — Plane 2, Actuation, Orchestration, Estimated run time: <time>, completes <%> (<what this moves forward>)===`

---

## Open items returned to the operator (do not guess — report and ask)

1. `manifest.json` vs `registry.json` — the name (Phase 0.2).
2. Does `--correct` default on or off? (2.1 — architect says off.)
3. Ratify or narrow the non-correctable class. (2.3)
4. Ratify the safety interlock. (2.4)
5. Confirm Guarded's meaning. (2.5 — architect proposed known-red-with-owner.)
6. Does `--optimize` overwrite, or propose-then-commit? (3.4 — architect recommends propose.)
