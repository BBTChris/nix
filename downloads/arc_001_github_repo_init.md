# ARC 001 — GitHub Repo Init

**Task:** Create and wire up the private GitHub repo `nix` under the BBT account, mirroring the canonical `~/nix` topology, with the frozen docs under version control from commit one.

**Context (do not re-derive, just execute):**
- Repo name: `nix`
- Visibility: **private**
- Canonical topology: `~/nix/{scripts,docs,checks,risks,sessions,downloads,web,logs,databases}` (per `directory_structure.md` v1.1.0)
- Docs to seed into `docs/`: `nics_risk_subsystem_spec_v1.3.md`, `nix_strategy_contract_v1.1.md`, `elements_v2.md`, `directory_structure.md`, `debug.md`, `dev_and_services_plan.md`
- Version file: initialize `1.0.0` per `elements_v2.md` §1.1 (metadata only, no tunables)

## Steps
1. `gh repo create nix --private --description "BlackBox Trading LLC — Nix autonomous futures platform"` (confirm `gh auth status` is BBT account first; do not proceed if wrong account).
2. Initialize local `~/nix` as the repo root if not already a git repo (`git init`, set `origin` to the new remote).
3. Create the directory skeleton exactly per `directory_structure.md`; empty dirs get `.gitkeep`.
4. Copy the six docs listed above into `~/nix/docs/`. Verify filenames match `CLAUDE.md`'s table **exactly** (spellings are load-bearing, not typos to fix).
5. Add `.gitignore`:
   - encrypted credential JSON (Fernet-encrypted broker creds file)
   - `logs/*` (non-Plane artifacts only — never commit these anyway)
   - `databases/*` (pg_dump staging)
   - `*.env`, any master-password material
   - standard Python (`__pycache__/`, `*.pyc`, `.venv/`)
6. Write version file at the path `elements_v2.md` §1.1 specifies, content `1.0.0`.
7. Commit: `git add -A && git commit -m "Initial repo structure + frozen spec docs, v1.0.0"`.
8. Tag `v1.0.0`, push `main` + tag to origin.
9. Confirm branch protection on `main` is **not** set up yet (single-dev trunk-based per current stage) — explicitly note this as a future gate, not an oversight.

## Definition of success
- [ ] `gh repo view nix` shows private, correct owner
- [ ] `~/nix` is a git repo with `origin` = the new remote
- [ ] Full directory skeleton present, matches `directory_structure.md` verbatim
- [ ] All six docs present under `docs/` with exact filenames from `CLAUDE.md`
- [ ] `.gitignore` excludes credential/log/db paths
- [ ] Version file present, content `1.0.0`
- [ ] `v1.0.0` tag pushed, visible on GitHub
- [ ] `git status` clean; nothing untracked that should be tracked, nothing tracked that should be ignored

## Out of scope for this arc
- No code (`scripts/`) yet — R1 seams & skeleton is a separate arc
- No CI/CD, no branch protection, no GitHub Actions
- No secrets loaded into GitHub (Actions secrets, etc.) — not needed until CI exists

**End of arc:** `cc` appends to `~/nix/sessions/SESSION.md`, writes `~/nix/downloads/RESULTS.md`, states `**** ARC completed ****` with % progress estimate.
