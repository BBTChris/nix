# ARC 007 — Merge PR #8; Doc-Conversion Corruption Audit; directory_structure.md patch

## Part 1 — Merge PR #8

Merge `arc-006-provisioning-v2` (PR #8) into `main` via admin override. If conflicts arise
against anything merged since Arc 006 was scoped, resolve `SESSION.md`/`RESULTS.md` conflicts by
chronological concatenation (never silently drop an entry), same as every prior arc. Verify
post-merge: `git log --oneline -5 origin/main` shows the merge commit, and every file Arc 006's
RESULTS.md claims to have created/modified is actually present on `origin/main` — spot-check at
least: `nix-trading.slice`, `nix-verify.service`, `nix-verify.timer`, `state/node_identity.json`,
`state/encrypt_credentials.py`, the applied schema SQL, `.pre-commit-config.yaml`.

Also: delete the stray branch flagged last arc as blocked by the permission classifier
(`arc-006-dev-box-provisioning`, the pre-`-v2` superseded one) now that a human is authorizing it.
Confirm it's genuinely superseded (nothing on it absent from `main` post-merge) before deleting —
same check discipline as the PR #3 branch-deletion decision.

## Part 2 — Doc-conversion corruption audit

**Context:** Arc 006 discovered that `docs/nix_db_schema_spec.docx`'s markdown conversion had
silently stripped extraction markup the schema's own self-extracting harness needed. This was
only caught because that particular doc has a 40-check harness built in — most docs don't have
that safety net. Audit every doc in `~/nix/docs/` for the same failure mode.

**Method:**
1. Identify every `.md` file in `docs/` that has (or plausibly had) a `.docx` source — check
   `CLAUDE-CHANGELOG.md`, `SESSION.md`, and any conversion tooling references (e.g. `graphify`)
   for provenance. For files where provenance is unclear, say so rather than guessing.
2. For any `.md` file with a live `.docx` counterpart still in the repo (`nix-strategy-evaluator-pipeline-6.docx`
   is one candidate — check if a `.md` counterpart exists or was ever generated from it), re-extract
   the `.docx` content via `python-docx` directly (same method that fixed the schema spec) and
   diff structurally against the current `.md`: missing sections, stripped code fences, stripped
   tables, collapsed whitespace that changes meaning, smart-quote corruption in anything
   code-like (paths, function names, config keys).
3. For `.md` files with **no** surviving `.docx` source (already-converted-and-source-deleted
   case) — check internally for conversion artifacts: orphaned fence markers, tables that don't
   render, any section that looks truncated mid-sentence, any reference to structure
   (numbered lists, nested headers) that doesn't match its own table of contents if one exists.
4. Explicitly check `nics_risk_subsystem_spec_v1_3.md` and `nix_strategy_contract_v1_1.md` with
   extra care — these are the two frozen, authority-order-1-and-2 docs. Corruption here is highest
   consequence since they win all conflicts on order flow/gating/sizing/stops.

**Report, per doc checked:** clean / corrupted-and-fixed / corrupted-and-flagged-for-human-review
(use this last category if a fix would require judgment calls about original intent, rather than
silently guessing at what the source meant). Do not silently "fix" the two frozen docs even if
corruption is found — flag for explicit human sign-off before touching anything in that
authority tier, since they're supposed to never be edited.

## Part 3 — directory_structure.md patch

Add `state/` to the canonical top-level directory list (alongside `scripts/`, `docs/`, `checks/`,
`risks/`, `sessions/`, `downloads/`, `web/`, `logs/`, `databases/`), with a one-line description:
hardware identity + encrypted credential storage, `chmod 600` throughout. Confirm this is the only
undocumented top-level directory currently on disk — `ls ~/nix` and diff against the full
documented list, don't assume `state/` is the only gap.

## Definition of success

- [ ] PR #8 merged, verified present on `origin/main`, spot-checked files confirmed
- [ ] Stray branch deleted after confirming it's genuinely superseded
- [ ] Every doc in `docs/` checked for conversion corruption, each with an explicit clean/fixed/
      flagged verdict — no doc silently skipped
- [ ] Both frozen docs (risk spec, strategy contract) explicitly checked with extra scrutiny;
      any corruption found there is flagged for human sign-off, not auto-fixed
- [ ] `directory_structure.md` updated with `state/`; confirmed no other undocumented top-level
      dirs exist

## Out of scope

- No `scripts/` application code
- No editing of frozen docs' *content* even if corruption is found — flag only
- No new infra beyond what Arc 006 already stood up

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's full results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
