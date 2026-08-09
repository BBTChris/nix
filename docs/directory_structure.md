# directory_structure — `~/nix` directory topology — v1.2.0

Application root: `~/nix`. Everything for Nix is self-contained here, **except the system PostgreSQL
cluster** (lives at the OS default per CLAUDE.md).

```
~/nix
  |-- scripts      All Python and shell scripts
  |-- docs         Reference documentation and markdown files (incl. the frozen risk spec)
  |-- checks       Check modules for verify.py and JSON execution map
  |-- risks        Library of risk rules and JSON execution map — data-role expression of the
  |                risk spec + §12A knobs; never a second behavioral authority
  |-- sessions     Development session log: SESSION.md (append-only, canonical singular name)
  |-- downloads    Transfer location claude.ai <-> Claude Code. Arc .md files land here;
  |                RESULTS.md (overwritten per arc) lives here
  |-- web          Dashboard and web root (read-only observability surface per spec §12.9)
  |-- logs         Non-Plane artifacts ONLY: Sentinel marker file, backup staging exports,
  |                web-server logs. Operational logging (Plane 2) is journald/syslog per spec
  |                §12.10 — never files here. Financial truth (Plane 1) is Postgres.
  |-- databases    pg_dump landing/staging for the Backblaze pipeline + auxiliary DB files.
  |                NEVER the PostgreSQL cluster itself.
  |-- state        Hardware identity + encrypted credential storage. `chmod 600` throughout;
                   gitignored wholesale (defense in depth beyond the `*credentials*.json` rule).
```

**v1.2.0 changes:** Added `state/` — created by Arc 006's `install.sh` (hardware-UUID capture +
credential-encryption mechanism) but never added to this list at the time, same category of gap
as ARC 001's `VERSION`-file assumption. Confirmed via `ls ~/nix` diffed against the full
documented list that `state/` was the only undocumented *canonical* top-level directory;
`graphify-out/` also exists on disk but is gitignored, disclaimed tool working-output (per
`sessions/SESSION.md`'s Arc-002 entry: "not part of this arc's scope") — not a content directory
of this project, deliberately left off this list.

**v1.1.0 changes:** Nix naming; typo fixes; `logs/` and `databases/` purposes pinned so the spec's
two-plane logging model and the external PG cluster cannot be forked by ambiguity; SESSION.md
declared canonical.
