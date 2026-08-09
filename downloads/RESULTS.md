# RESULTS.md — Nix arc results

Overwritten per arc (per `docs/directory_structure.md` v1.1.0) — holds the current arc's summary
and comms back to claude.ai.

## ARC 004 — Close stale PR #3

**Status: complete.**

### What happened

- **PR #3** (`docs: ARC 002 RESULTS.md`, branch `docs/arc002-results`) closed without merging:
  `gh pr close 3 --comment "Superseded by later arcs — RESULTS.md content from Arc 002 is stale
  relative to Arc 003's final state on main."`
- **Branch deletion check (required before deciding):** `git log origin/docs/arc002-results
  ^origin/main --oneline` — returned commit `82efd05` ("docs: RESULTS.md for ARC 002…"), which is
  **not** on `main`. Per instruction, the branch was **not** deleted — it's the only place that
  commit currently exists.
- **Confirmed via `gh pr view 3`:** `state: CLOSED`.

### Context worth surfacing (discovered during this arc, not something this arc's instructions asked me to fix)

`origin/main`'s `SESSION.md` and `RESULTS.md` are **currently behind** the work already done:
- `SESSION.md` on `main` ends at the §1.1a entry — it does not yet contain the ARC 003 entry
  (CLAUDE.md write-back gate, `enforce_admins` fix, PR #1+#2 merge), because that content only
  ever landed in **PR #5** (`docs/arc003-writeback`), which is still open.
- `RESULTS.md` on `main` is still the **ARC 001** version — neither ARC 002's nor ARC 003's
  overwrite ever merged (PR #3 carried ARC 002's, now closed unmerged by this arc's own
  instruction; PR #5 carries ARC 003's, still open).

This arc's own write-back (this file, and the one-line `SESSION.md` entry) is being committed
directly on top of that same un-merged-forward `main`, per this arc's explicit instructions —
not held back pending PR #5.

## Out of scope (confirmed unchanged)

- No code (`scripts/`) — R1 seams & skeleton is a separate arc.
- No CI/CD.
- No secrets loaded into GitHub.
- PR #5 merge — not requested this arc, left open.

**** ARC completed **** — housekeeping arc, no code; <1% of whole-project progress.
