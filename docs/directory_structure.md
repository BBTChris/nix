# directory_structure — `~/nix` directory topology — v1.1.0

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
                   NEVER the PostgreSQL cluster itself.
```

**v1.1.0 changes:** Nix naming; typo fixes; `logs/` and `databases/` purposes pinned so the spec's
two-plane logging model and the external PG cluster cannot be forked by ambiguity; SESSION.md
declared canonical.
