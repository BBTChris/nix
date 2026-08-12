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
