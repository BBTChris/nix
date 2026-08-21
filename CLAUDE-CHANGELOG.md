# CLAUDE.md Change Log

Append-only. One entry per instruction change to `~/nix/CLAUDE.md`.

---

## 2026-08-09 — docs table audit

Scanned `~/nix/docs/` against CLAUDE.md's "Specs — read on demand" table.

- Verified all 6 previously-listed docs exist on disk under the exact listed
  filenames; spot-checked version numbers and section refs (§13/38 objectives,
  §12A, §12.10 two-plane logging, contract §3/§4/§9A, debug.md three-tier
  structure) — all accurate, no drift.
- Added 2 rows to the Specs table for docs on disk but previously unindexed:
  `nix-strategy-evaluator-pipeline-6.docx` (Crucible strategy evaluator
  pipeline design, planning-stage) and `nix_db_schema_spec.docx` (DB schema
  spec v1.3.0, validated live against Postgres 16).
- Removed "live-promotion gate" from the "Not yet authored" list — a
  planning-stage design now exists in `nix-strategy-evaluator-pipeline-6.docx`
  (still unimplemented). Added a parenthetical pointer.
- Replaced the completed "Stale artifact" line (`dev_and_services_paln.md`
  removal) with a dated confirmation that the cleanup is done and the doc
  table was audited.

**Not addressed, flagged for follow-up:** `~/nix/.claude/rules/` does not
exist on disk — none of `elemets.md`, `packages.md`, `roles.md`,
`directory-layout.md`, `debugging.md` are present. CLAUDE.md's own rule says
this should halt work until reconciled. Out of scope for this docs-only pass;
needs an explicit decision on what those rules should contain.

## 2026-08-09 — rules table stripped (files absent on disk)

Re-confirmed `~/nix/.claude/rules/` and every file it was meant to hold
(`elemets.md`, `packages.md`, `roles.md`, `directory-layout.md`,
`debugging.md`, `elemet_structure.md`) do not exist anywhere under `~/nix`.
Per instruction, removed all references to absent files:

- Replaced the "Rules — load always" table (5 rows, all dangling) with a
  status note: no rule files exist; nothing to auto-load; read `docs/*.md`
  directly until rules are authored.
- Dropped the `elemets.md`/`elemet_structure.md` "open objective" paragraph
  — moot once the reference itself is removed.
- Updated the root mission paragraph's `.claude/rules/*.md` mention to note
  it's currently empty, so it no longer implies rules are indexed there.

**Net effect:** no load-always rule files govern this project right now.
Everything previously delegated to rules (dependency manifest, script
roles/ownership, directory-layout enforcement, debug-tier gates) has no
rule-layer document — only the `docs/*.md` specs they'd have derived from.
This is a real capability gap, not just a stale reference; someone should
decide whether/when to author these rule files.

## 2026-08-09 — SESSION.md/RESULTS.md write-back made a hard gate

Added to the "Rules — load always" section: every arc, on completion, MUST
append its summary to `~/nix/sessions/SESSION.md` and overwrite (not append)
`~/nix/downloads/RESULTS.md` with that arc's full results, and must `cat`
both files and paste their confirmed state into the chat response before
reporting `**** ARC completed ****`. Prompted by the prior arc (public
visibility + branch protection) where RESULTS.md was skipped on first pass
and only caught retroactively — this closes that gap mechanically rather
than relying on memory.

## 2026-08-09 — ARC 008 — verify.py v2 doc reconciliation

- Added `VERIFY-AND-CHECKS.md` to CLAUDE.md's spec table; it is the authority for
  the provisioning/verification layer.
- `elements_v2.md` §1.2/§1.3 reconciled: three semantic modes, `scripts/` location,
  systemd-creds supersedes Fernet (decision recorded; migration itself not yet
  landed — `install.sh` still contains the Fernet block).
- `directory_structure.md` v1.3.0: `scripts/` names the engine package
  (`nixverify/`) and its test suite (`scripts/tests/`).

## 2026-08-10 — ARC 018 — debug.md version corrected in the spec table

- Spec table indexed `debug.md` as **v1.1.0**; the file on disk reads
  **"Version 1.2.0. Supersedes v1.1.0, which lacked §7.12"**. Corrected to v1.2.0.
- This mattered rather than being cosmetic: §7.12 (the standing question, required of
  every gate at the point it is built) and failure mode #14 are exactly what v1.1.0
  lacked, and both are load-bearing for ARC 017 and ARC 018. An agent reading the index
  and trusting the stated version would have been reading for a doctrine that did not
  contain the section the arc turns on.
- Found by sub-agent A while applying §0a's "verified on-disk state outranks this
  document" to the brief. Reported rather than worked around; `CLAUDE.md` was outside
  that sub-agent's write scope, so the parent applied it in Phase 4.

## 2026-08-11 — ARC 024 — check contract v2 (actuation) written into CLAUDE.md

- Added a new section **`## Check contract (v2 — actuation)`** after "Architecture
  invariants": nine numbered durable invariants covering the actuation verbs and
  measure-only default, the independent post-mutation re-verify, the broadened
  coverage trigger, the four-state status/exit mapping with Guarded, the block
  execution plan and proven-disjoint parallelism, static (AST) declaration reading,
  `--optimize`'s propose-then-commit and its loud-error set, Plane-2 emission to
  journald, and §0c's "a retrofitted check is a new check".
- The section is the brief's Stage 5.1 list **corrected to what shipped**, not
  transcribed: the check's own CLI is named (the runner already had `--mode`, default
  `verify`, since ARC 009 — the 13 checks hardcoded `Mode.VERIFY` in `__main__`);
  light blue is recorded as covering cannot-measure **and skipped**; the aggregate
  dominance order (Fail > Cannot-measure > Guarded > Pass) is stated; declarations are
  named (`DEPENDS_ON`, `RESOURCES`) and pinned to AST reading; `--optimize` writes no
  plan at all on error and proposes rather than overwrites; the retrofit rule states
  the consequence (reverts to UNBOUND).
- Invariant 5 records `checks/registry.json` as the on-disk name **and flags the name
  as an open operator ruling** — the ruling says `manifest.json`, the file says
  `registry.json`. Recorded rather than resolved, per Phase 0.2's "do not rename,
  merge, or create either file."
- Added 1 row to the "Specs — read on demand" table for
  `docs/CHECK-CONTRACT-AMENDMENTS.md` (a RECORD, not an authority; read on any change
  to check status, actuation, or the coverage trigger). New file this arc:
  `VERIFY-AND-CHECKS.md` is external, inherited, **unversioned, and carries no
  amendment mechanism**, so it is never edited in place; and `SPEC-AMENDMENTS.md` is
  the wrong home because it amends the frozen **risk** spec and holds six amendments,
  not five as the brief stated.
- Corrected the `nix_check_contract.md` row's version citation **v1.1.0 → v1.2.0**,
  matching the bump made to that file in the same arc. Not a discretionary edit: an
  index that names a version the file does not carry is the exact ARC 018 defect
  recorded two entries above.
- **No other CLAUDE.md content changed.** In particular the `debug.md` row was NOT
  touched — it already reads v1.2.0 on disk, which is correct; the ARC 024 brief's
  Phase 0.6 claim that CLAUDE.md cites `debug.md` v1.1.0 in two places is **false
  against the file**. The only occurrences of "v1.1.0" in that row are the historical
  note ARC 018 added recording that it *used* to say v1.1.0.

## 2026-08-12 — ARC 024 close-out — the write-back gate must prove durability

- **The finding this entry exists for:** ARC 024 reported every gate green — `verify.py`, the
  pytest suite, the pre-commit suite, the claims harness — wrote `SESSION.md` and `RESULTS.md`,
  cat-ed both, and passed the write-back gate **with `HEAD` still on the ARC 023 merge**. All 30
  paths, 5,019 insertions, were staged in the index and never committed. Every measurement in that
  report was taken against a tree that was not history and would not have survived a `git reset`.
- Amended the arc-completion rule above with a **third obligation**: `HEAD` advanced, `HEAD`'s tree
  contains the arc's paths, and `git status --short` empty for them — shown with
  `git rev-parse` / `git ls-tree` / `git status`, not with `ls`. The index is not history and the
  working tree is not history.
- Substance lives in `docs/nix_check_contract.md` **§16 (new), AMENDMENT 4**, recorded in
  `docs/CHECK-CONTRACT-AMENDMENTS.md`; contract bumped **v1.2.0 → v1.3.0**. §16.2 requires the
  arc's figures to be **re-taken against the merged tree** and any delta reported as a finding.
  §16.3 states the ceiling out loud: it proves the paths are *in* history, never that their bytes
  are the bytes that were measured, and a local commit satisfies it and dies with the disk.
- **Why the rule went into CLAUDE.md and not only into the spec:** the write-back gate lives here.
  Adding the durability clause to the derived spec while this file still said *"cat both files"*
  would have left the weaker rule standing in the higher-authority document — the derivation
  invariant two lines above, inverted.
- The §16 gate is mechanically checkable and is therefore **owed a check** under §1 as broadened by
  AMENDMENT 3. None written; recorded rather than blocking, and returned to the architect as open
  items 6 and 7 in the amendment ledger's standing note.

## ARC 025 — check contract v1.4.0: the masked hazard, the reason-asserting control, declared failure policy

- **Check contract gains items 10, 11 and 12.** Substance in `docs/nix_check_contract.md`
  **§17 and §18 (new)** plus `ON_FAIL` in **§4.4**, all AMENDMENT 5, recorded in
  `docs/CHECK-CONTRACT-AMENDMENTS.md`; contract bumped **v1.3.0 → v1.4.0**.
- **Item 10 — a safety property proven while its subject is unavailable is not proven.** Where an
  observer cannot see a resource *because the resource is unreachable*, the verdict is
  Cannot-measure, **never Pass**. The attempt is the claim; a positively-observed undeclared claim
  outranks masking. This closes CHECK-DEBT **D2.27** with a *runtime* instrument — the row's claim
  that no STATIC mechanism could close it was correct, which is why the closure is dynamic.
- **Item 11 — every can-fail control asserts the REASON**, never the exit code alone. An exit code
  is a shared namespace: the detector firing, the instrument breaking, and the interpreter refusing
  to start all reach the same integer. Audited across 512 test functions; exit-code-only controls
  **5 → 0** of 68. Exempt only where the exit code *is* the subject.
- **Item 12 — declared resource claims are checked against OBSERVED ones**, and failure policy is
  declared rather than assumed. `--optimize` was measured **silently dropping** `on_fail: halt`
  while satisfying every stated success criterion for the derivation.
- **Why these went into CLAUDE.md and not only into the spec:** items 5–9 already state what a check
  must declare and how the plan is derived. Leaving the observed-vs-declared rule only in the
  derived spec would have left this file asserting that declared disjointness is what the plan
  rests on — which stopped being true this arc.
- **The §18 rule is mechanically checkable and its auditor ran as a one-off**; promoting it to a
  standing check is recorded as **D2.29** rather than blocking, per §1 as broadened by AMENDMENT 3.
- `checks/registry.json` is now **DERIVED** by `verify.py --optimize --commit` rather than
  hand-maintained. Its accumulated rationale comments are superseded: the ordering they justified is
  now *declared* in each check's `DEPENDS_ON`/`RESOURCES`/`ON_FAIL`, which is one source of truth
  instead of two, and the prose survives in git history (directive 6 — history is appended, and a
  file replaced in a commit is not history erased).

## ARC 027 (B) — 2026-08-12

**Specs table: `nics_risk_subsystem_spec_v1.4.md` added as a SECOND row, and v1.3's row
now says it is STILL THE CITED AUTHORITY.** v1.4 is the ARC 027 mechanical fold of
`docs/SPEC-AMENDMENTS.md`'s seven entries into frozen v1.3, each inside
`<!-- BEGIN/END FOLDED -->` markers. `scripts/tests/test_spec_v14_fold.py` proves on
every run that v1.4 minus those blocks is byte-identical to v1.3 **as committed at
`aaa6a28`** — the only commit that has ever touched the risk spec — rather than to the
working copy, which would compare the file to itself.

**v1.4 is deliberately NOT the authority and the table says so.** The fold inserts
lines, so every `§x:line` coordinate the governed roots cite moves; re-pointing the tree
is separate serial work (CHECK-DEBT D3.33). Two implied §2A list additions were refused
as editorial (D3.32). `checks/check_spec_citations.py`'s `REQUIRED_DOCS` is deliberately
UNCHANGED: that gate's own docstring says a v1.4 landing without the constant moving must
make it CANNOT_MEASURE loudly, and that is only the correct direction once v1.4 is meant
to be the subject.

**Nothing was renumbered.** Two rulings were both issued titled "AMENDMENT 5"; the ledger
records the ARC 023 one as AMENDMENT 6 while keeping its self-reference verbatim, and the
fold reproduces that exactly. The collision is the architect's to rule on.

## ARC 028 (2026-08-12) — Phase 0

- **Check contract gains rule 13:** *a rule that decides a check's verdict is written into `CLAUDE.md`
  and recorded in `CHECK-CONTRACT-AMENDMENTS.md`, or it does not bind.* Arc-brief section labels are
  per-arc and collide across arcs; they are not ledger identifiers. Added because a declaration-only
  binding classifier governed three arcs' binding verdicts under the brief label `§0c` **while `§0c`
  on disk meant rule 9** (a retrofitted check is a new check), which is live and load-bearing. The
  withdrawn rule had no on-disk name at all, so nothing could be edited to withdraw it and nothing
  could have contradicted it. Recorded as `CHECK-A7`; CHECK-DEBT D3.81.
- **Both amendment ledgers gain a citation prefix** — `SPEC-A<n>` and `CHECK-A<n>`. Numbers are
  unchanged and nothing was renumbered. The specs table row for `CHECK-CONTRACT-AMENDMENTS.md` now
  carries the citation form. Enforced mechanically by `scripts/tests/test_amendment_ledgers.py`
  (prefix present, number unique **within** its ledger, prefixes disjoint, refinements excluded from
  the number space), driven red both ways against the real ledger and restored byte-identically.

## ARC 029 — check-contract rule 14: the declared exclusion (D3.104 / CHECK-A8)

- **Added check-contract rule 14** to `CLAUDE.md`: a declared EXCLUSION is a guard with its
  re-owning ceiling lifted and nothing else lifted. `check_artifact_gate_coverage` may move an
  artifact out of the ceiling-guarded `rows` into an `exclusions` bucket only under a recorded
  `CHECK-A<n>` amendment, because the gate cannot tell an authorized move from a laundering one. An
  exclusion stays inside the one-way ratchet, stays owned by a live arc (a completed owner is
  Cannot-measure), stays assigned under §0g, and must justify itself and declare itself temporary.
- **Origin:** architect ruling on CHECK-DEBT D3.104 — the re-owning ceiling (D2.31, ceiling of two)
  fired when ARC 029 / 0.5 re-pointed thirteen already-at-ceiling artifacts to a fourth owner. The
  ruling chose OPTION 3 as a HOLDING state for ARC 029 only; ARC 030 empties the exclusion with real
  per-artifact coverage. Recorded as `CHECK-A8` in `docs/CHECK-CONTRACT-AMENDMENTS.md` and §19 of
  `docs/nix_check_contract.md`; the current instance (thirteen artifacts, owner ARC 030, temporary)
  is CHECK-DEBT D3.104. Enforced by `check_artifact_gate_coverage`'s exclusion arms, each planted and
  driven red in `scripts/tests/test_check_artifact_gate_coverage.py`.

## ARC CRUCIBLE-CALENDAR-INFRA (2026-08-14)

- **`directory_structure.md` bumped v1.4.0 -> v1.5.0**: names `scripts/crucible/`, the Crucible
  strategy-evaluation pipeline's first landed slice (calendar infra). Specs table row corrected to
  match (was stale at v1.3.0, itself a pre-existing drift from before this arc).
- **New check `check_crucible_calendar`** (level-0, `DEPENDS_ON=()`, `RESOURCES=()`, non-correctable):
  proves the vendored CME calendar artifact's sha256 independently matches its provenance stamp, and
  that the runtime query module (`scripts/crucible/calendar.py`) imports clean of any calendar
  library/network dependency and answers for all six locked product groups. Registered via
  `verify.py --optimize --commit`.
- No risk-spec or check-contract rule changes this arc -- new subsystem, existing contract applies.

## ARC 031 / Phase 0.6 (2026-08-15)

- `docs/directory_structure.md` v1.6.0 -> **v1.7.0**: the `scripts/` line now names
  `nixrisk/`, `nixalloc/` and `nixbus/`. `nixalloc/` is this arc's (the Allocator's
  frozen consumer-side seam). `nixrisk/` (ARC 028) and `nixbus/` (ARC 021) were
  already on disk and had never been named there — measured while adding the third,
  and fixed in the same motion rather than left to be rediscovered.
- The spec table above said `directory_structure.md` was **v1.5.0**; the file on
  disk was already **v1.6.0** (ARC CRUCIBLE-DEPSPLIT's venv split). Corrected to
  v1.7.0. Recorded rather than quietly overwritten: a version number in this table
  that trails the file it indexes is the "restate a mutable fact" failure core
  directive 3 forbids, and it went one whole arc unnoticed.

## ARC 031 / Phase 5 — architect rulings (2026-08-15)

- **Check contract rule 14 (`CLAUDE.md`) — `CHECK-A9` added beside `CHECK-A8`.** The
  declared-exclusion mechanism now names TWO amendments, each enumerating its own
  paths. `CHECK-A8` (D3.104) is the **overdue-work** case; `CHECK-A9` (D3.138) is the
  **instrument-blind-spot** case — `scripts/nixverify/gitenv.py` and
  `scripts/nixverify/registry.py` already carry real can-fail coverage BY TESTS, so a
  second `checks/check_*.py` is the duplicate instrument doctrine C.9 forbids, not new
  coverage. The stale instance figure (thirteen artifacts, owner ARC 030) is corrected
  to the measured one: eight, owner ARC 032, temporary.
- Recorded in `docs/CHECK-CONTRACT-AMENDMENTS.md` (`CHECK-A9`) and
  `docs/nix_check_contract.md` §19.1, per rule 13. Measured consequence:
  `check_artifact_gate_coverage` CANNOT_MEASURE (exit 2) -> **GUARDED (exit 3)**.
- **No `CLAUDE.md` change for `SPEC-A8` or the D3.136 ruling.** SPEC-A8 amends the
  frozen risk spec (`docs/SPEC-AMENDMENTS.md`); D3.136's OPTION A is a recorded
  decision R3-B executes. Neither is a durable invariant of this file.
- **Spec table version corrected, measured in passing.** The table indexed
  `nix_check_contract.md` at **v1.3.0**; the file's own header line has read
  **v1.4.0** since ARC 025 (AMENDMENT 5, §17/§18/`ON_FAIL`). Corrected in the
  table rather than left — the same "restate a mutable fact" failure (core
  directive 3) that ARC 031 / Phase 0.6 recorded one arc earlier for
  `directory_structure.md`, in the same table, found the same way: by opening the
  file the row indexes. The check contract itself is NOT bumped by `CHECK-A9`;
  §19.1 is an amendment recorded in place, exactly as `CHECK-A8`'s §19 was.

## ARC 033 / close-out contract — the completion marker is the LAST token (2026-08-15)

- **`CLAUDE.md` close-out contract (§Rules block) — new paragraph, and it ORDERS work rather
  than removing any.** `**** ARC completed ****` is the **last token printed, with nothing
  after it** — no re-measure, no `cat`, no summary, no percentage, no commentary. The marker
  is a **certificate over a state** (*the banked state is final and nothing followed it*), so a
  measurement printed after it **retroactively falsifies it**: the marker certified a state
  that then changed, and a reader cannot tell trailing commentary from a late measurement,
  which is the one distinction the marker exists to make unnecessary.
- **The post-write-back re-measure is NOT waived — it is ordered.** Where one is required (the
  D3.40 / D3.144 guard-owner transition, which fires the instant `sessions/SESSION.md` names
  the arc complete and `contract.completed_arcs()` sees it), the sequence is fixed: write back
  and commit → re-measure the merged tree → record that re-measurement **forward-only** (§0h)
  into `SESSION.md` and `RESULTS.md` **and commit it** → show §16.1's three obligations against
  that commit → print the marker. **The marker is printed only once the final measurement is
  itself banked.** An arc that reports a figure it has not banked has not finished; it has
  narrated.
- **`CLAUDE.md` arc-end rule (§Design and Development Structures) reordered to match.** The
  forward-movement percentage now explicitly PRECEDES the marker, as does any
  `===RUN SUMMARY: …===` an arc brief requires "alongside the arc". Where a brief's wording
  places the marker first, the contract governs — **§0b: the spelling was a sketch, the
  invariant binds.** This collision is real and recurring, not hypothetical: it is how ARC 032
  ended.
- **No marker at all where the state will not settle.** An arc whose tree is still moving prints
  **no marker and no weakened version of one** — it reports `STATUS: IN FLIGHT` and names what
  is still moving, in what direction, and what would settle it. A marker qualified into
  truthfulness (*"completed, pending X"*) is the same defect wearing an apology: still a
  certificate, still over a moving state.
- **Recorded per rule 13** in `docs/nix_check_contract.md` **§16.4** and
  `docs/CHECK-CONTRACT-AMENDMENTS.md` **`CHECK-A10`**. The check contract bumps
  **v1.4.0 → v1.5.0** (§16.4 is a new section, not an in-place clarification like `CHECK-A9`'s
  §19.1), and **both** of `CLAUDE.md`'s version references were moved with it — the spec table
  row and the check-contract header line — because ARC 031 recorded exactly that drift in this
  same table one arc earlier.
- **The measured counter-example is ARC 032's own close-out, and it is why this is a ruling.**
  ARC 032 did the hard half right: it ran the post-write-back re-measure, observed the predicted
  GUARDED → CANNOT_MEASURE on `check_artifact_gate_coverage`, appended it forward-only to both
  files and **committed it** (`125e8d5`) before reporting. Then it printed the marker and
  followed it with a forward-movement percentage and a run-summary line. **Nothing false was
  said and no figure moved — the defect is structural**, and that is precisely why a rule was
  needed rather than more care.
- **NO CHECK IS OWED, stated so it does not become a phantom debt row.** Every other §16
  obligation is a property of the repository and is owed a check under §1 as broadened by
  `CHECK-A3`. §16.4's subject is the **order of tokens in a chat response**, written to no file
  in this tree, so no `checks/check_*.py` can observe it. Enforcement is by reading — the
  weakest this project has — and it is accepted because writing the marker into a file so a gate
  could see it would make the marker a property of a FILE when the thing certified is the REPORT.
- **One stale restatement corrected in passing** (core directive 3). The spec table's
  `CHECK-CONTRACT-AMENDMENTS.md` row read *"both hold six"* — a count of two independently
  growing ledgers, restated in a third file, which this very edit would have made staler. The
  row now states the **mechanism** (the two ledgers are numbered independently and their ranges
  OVERLAP, which is why a bare "AMENDMENT 6" named two different rulings) and no number.

## ARC 033 — WAYPOINTS: a progress banner at the start of every stage (2026-08-15)

- **`CLAUDE.md` §Design and Development Structures — new standing rule, every arc.** At kickoff
  `cc` echoes the TOTAL stage count ONCE, **enumerated**, so the denominator cannot move
  mid-run; then prints a ruled banner at the START of each stage, before that stage's work
  begins.
- **Form:** `ARC <n> · <Module>/<Stage> — STAGE <k>/<total>: <short name>`, followed by an
  **elapsed / rough-ETA line** (`~<elapsed> in · ~<rough eta> left`), in a ruled box (or `===`
  lines) on its own lines. **Never a bare sentence buried in output** — the whole point is that
  an operator can read position from a glance at the terminal without reading the run.
- **The ETA is derived from the arc's TIME BUDGET and is labelled rough. It is not a live
  measurement, and it RESETS when a stage overruns.** The label is the load-bearing part: a
  figure derived from a budget is a plan, and presenting a plan as a measurement is exactly the
  restatement core directive 3 forbids — the same failure class as a series-table cell that
  stops matching the rows it summarises.
- **Granularity is fixed so the denominator is honest:** EVERY phase, stage, sub-agent and
  convergence step counts. Four parallel sub-agents are four stages; `3.1`–`3.4` are four, not
  one. Stating the enumeration at kickoff is what stops the denominator drifting as the arc
  discovers work — and this arc has already discovered three scope changes in Phase 0, so the
  risk is real rather than theoretical.
- **Pauses are visible:** on a pause or a stop-for-ruling the banner is reprinted with
  `— PAUSED, awaiting operator`, so a stopped run is distinguishable from a slow one at a
  glance. That is the same reasoning as §16.4/`CHECK-A10`'s `STATUS: IN FLIGHT`, one layer up:
  a run that has stopped must say so where the operator is already looking.
- **Not recorded in `nix_check_contract.md`, deliberately, and the distinction is the same one
  `CHECK-A10` had to make.** §16.4 governs the CLOSE-OUT certificate, which is a claim about a
  banked state; this rule governs MID-RUN progress reporting, which certifies nothing and gates
  nothing. Putting it in the check contract would imply a check could observe it — and like
  §16.4's marker ordering, its subject is terminal output written to no file in this tree, so
  no `checks/check_*.py` can see it and none is owed.

---

## ARC 034 / Phase 0 — check-contract rule 14's "current instance" stops being a restated number

**Changed:** rule 14's closing sentence no longer names a count or an owner arc. It points at
`checks/gate_coverage_baseline.json`'s own `exclusions` map, which is what `guard_owner_defect`
actually reads.

**Why, and it is measured rather than argued.** The sentence read *"eight artifacts, owner ARC 032,
temporary"* from ARC 031 until ARC 034. Over that span the owner walked **ARC 032 → ARC 033 →
ARC 035** while the text stood still, so it was wrong for three of the four arcs that carried it —
and nothing noticed, because no instrument reads this file for that figure. That is core directive 3
(*derive from a single source of truth; do not restate mutable facts*) failing on the very rule that
governs the ratchet, in exactly the shape ARC 033 repaired one row above it when the amendment-ledger
counts went stale.

The same repair was applied to `docs/CHECK-CONTRACT-AMENDMENTS.md`'s `CHECK-A8` and `CHECK-A9`
`status` rows, which named `ARC 030` and `ARC 032` respectively and were stale for the same reason.
The rule, the scope and the enumeration of paths stay in those amendments — those are not mutable.
Only the live owner moved out, to the file that holds it.

**Discovered by:** the D3.40/D3.144 guard-owner transition firing one layer below where ARC 033
predicted it. ARC 033 banked the `verify.py` effect (`check_artifact_gate_coverage` GUARDED →
CANNOT_MEASURE) and not the pytest one, so ARC 034's 0.1 re-measure opened on
`test_the_REAL_TREES_THIRTEEN_ceiling_tripped_artifacts_are_the_D3104_EXCLUSION` FAILING with
*"'ARC 033' has ALREADY COMPLETED"*. Re-owning to `ARC 035` discharged it. **A re-own is not a
discharge** and the amendments say so; it is the fourth consecutive one.

## ARC 041-T (2026-08-19) — STATUS EMIT

Added `## STATUS EMIT — call the script, never re-invent the format` and its `### The standing arc
prompt, rewired (ARC 041-T)` subsection to `CLAUDE.md`. The heartbeat/banner format moves OUT of
cc's memory and INTO `scripts/arc_heartbeat.sh`; cc calls it. Rationale: a format cc reconstructs
from priors degrades under context compaction — the observed failure was a 65-line banner emitted
per beat, burying the compact ticker the rule exists to produce. The WAYPOINT BANNERS rule is not
rewritten or contradicted; the new section says who FORMATS the beat, and names the script as the
tie-breaker against its own prose, on directive 8 (enforce mechanically, keep prose brief).

Paired instruments registered in the same arc: `checks/check_arc_status_contract.py` (audits an
arc's own log for heartbeat evidence + `[watchdogd]`-safe teardown proof) and
`checks/check_tmpfs_inode_headroom.py` (the axis that stopped ARC 039R — CHECK-DEBT D3.423).

## ARC 046 (2026-08-20) — STATUS EMIT block: D3.445 corrected
`arc_progress.txt` is **one `key=value` per line**, not one space-joined line. The block documented
the joined form while `scripts/arc_heartbeat.sh` has always parsed line-by-line
(`while IFS='=' read -r k v`), so the joined form parsed `arc` only, left `stage`/`ts` empty, and
ARC 045 emitted a false `STALL WARNING` against a run that was moving. Documentation now matches the
parser, which is the authority (directive 3: the format lives in the code, not in prose).
Not fixed here, recorded instead: `arc_heartbeat.sh`'s OWN header comment (line 16) still shows the
joined form — same defect, but the file is outside ARC 046's declared freeze. CHECK-DEBT row filed.

## ARC 052 (2026-08-21) — check contract rule 14: the PERMANENT disposition (`CHECK-A11`)

Rule 14 previously required every declared exclusion to be **owned by a LIVE arc** and to **declare
itself temporary**. Both clauses are kept for the temporary class and are now one half of a
two-valued disposition; the other half is `CHECK-A11`'s **permanent** class, which names no owner.

**Why the edit, measured rather than argued:** `gate_coverage_baseline.json`'s eight exclusion owners
were walked `ARC 030 → 032 → 033 → 035 → 036 → 037 → 039 → 040 → 043 → 046 → 049 → 052`, the last six
of them consecutive close-outs, each one recording in the JSON's own justification that the bump was
*"arc-boundary maintenance, not progress"*. The owner-liveness rule was demanding a name for work
that does not exist: all eight are `scripts/nixverify/*` driven by pytest, and doctrine C.9 forbids
the second instrument a `checks/check_*.py` over them would be. D3.104 was not an unpaid debt; it was
a debt with no payer, recorded once per arc as if it had one.

**What was added, not removed:** the permanent class must name `covered_by` witnesses that the gate
RESOLVES on every run — existence and aim, in both directions, with this gate's own test module
refused by name. Until this arc the claim "pytest measures it" lived only in a prose justification and
nothing read it. The one-way ratchet is untouched: a silent permanent addition is still an unadmitted
growth, and an artifact that acquires a real gate is still a stale-baseline FAIL.

Ruling recorded in full at `docs/CHECK-CONTRACT-AMENDMENTS.md` § `CHECK-A11`, per check-contract
rule 13. Measured effect on the tree: `check_artifact_gate_coverage` GUARDED → PASS, with all eight
permanent exclusions enumerated in `evidence` on every run.
