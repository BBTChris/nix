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
