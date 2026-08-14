# directory_structure — `~/nix` directory topology — v1.6.0

Application root: `~/nix`. Everything for Nix is self-contained here, **except the system PostgreSQL
cluster** (lives at the OS default per CLAUDE.md).

```
~/nix
  |-- scripts      All Python and shell scripts; verify.py engine (nixverify/),
  |                the vendor-neutral broker seam + vendor adapters (broker/),
  |                the Crucible strategy-evaluation pipeline (crucible/, calendar
  |                infra so far), and the test suite (scripts/tests/)
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

**v1.6.0 changes — which venv, canonically:** ARC CRUCIBLE-DEPSPLIT split the single
shared venv into two, gitignored the same way (`.venv-dev` / `.venv-dev/`, mirroring
`.venv` / `.venv/`):

- **`.venv`** — the runtime venv. `install.sh`-managed: `checks/pinned_deps.json`'s
  three exact, drift-repaired pins (`ib_async`, `pytest-asyncio`, `pyzmq`) plus
  `checks/requirements-runtime.txt`'s unpinned general dev-tooling (`coverage`,
  `pre-commit`, `pytest-testmon`) plus `cryptography`. ALL of Titan/Nix runtime, the
  full test suite, and `verify.py` run under this venv. It carries no calendar
  library — never has, by convention now enforced structurally (below).
- **`.venv-dev`** — build-only. Holds `scripts/crucible/generator-requirements.txt`
  (`pandas_market_calendars` and its own transitive tree) plus, layered on top,
  `scripts/crucible/generator-test-requirements.txt` (`pytest` — needed only to run
  `scripts/tests/test_crucible_calendar_gen.py`, the one test file that legitimately
  imports the generator; under the default full-suite run via `.venv`, that file's
  `pytest.importorskip` makes it skip cleanly rather than fail, by design). The ONLY
  thing that runs here is `scripts/crucible/calendar_gen.py` (directly or via that
  test file), which refuses to import under any other interpreter (its own
  venv-identity guard, resolved `sys.prefix` against this path) — a wrong-venv
  invocation fails loudly with the exact three commands to fix it, rather than
  silently half-working. Build: `uv venv .venv-dev && uv pip install --python
  .venv-dev/bin/python -r scripts/crucible/generator-requirements.txt -r
  scripts/crucible/generator-test-requirements.txt`.

**Discovering which venv a future generator should use:** by convention, a build-time
generator that needs a library the runtime venv must never carry gets its own
`.venv-<name>`, documented here, with the same refuse-if-wrong-interpreter guard
`calendar_gen.py` demonstrates — not installed ad hoc into `.venv` (docs/CHECK-DEBT.md
D3.111 is the incident this replaces). `checks/check_python_transitive_deps.py`
inspects `.venv`'s installed tree against every already-pinned package's own declared
transitive ranges, so a future generator dependency that leaks into the wrong venv (or
a routine bump that drifts an already-installed transitive out of range) fails that
check loudly instead of silently, the way `tzdata` did before this split existed.

**v1.5.0 changes:** `scripts/` line expanded to name `crucible/` -- the Crucible
strategy-evaluation pipeline (`~/nix/docs/nix-strategy-evaluator-pipeline-6.docx`).
ARC CRUCIBLE-CALENDAR-INFRA landed its first slice: `calendar_gen.py` (build-time
generator, the only module allowed to import a calendar library),
`calendar.py` (zero-dependency runtime query module), and `calendar_data/`
(the vendored, hash-stamped CME session-calendar artifact, 2008-2030, six
product groups). Same reasoning as `broker/` and `nixverify/`: a subpackage
under an already-documented top-level directory is named here rather than
left implicit. Future arcs add the corpus builder, fill model, and bar
aggregation under this same directory -- not built here (scope fence).

**v1.4.0 changes:** `scripts/` line expanded again to name `broker/` — the §2A vendor-neutral
seam (`broker_seam.py`), the IBKR order adapter (`broker_order_ibkr.py`), the mapping findings
record (`ibkr_mapping.py`), and the vendorless seam simulator (`seam_simulate.py`), landed by
ARC 014. Same reasoning as v1.3.0's `nixverify/`: a subpackage under an already-documented
top-level directory is named here rather than left implicit, because "All Python and shell
scripts" covers it but does not make it findable. The adapter's own test lives in
`scripts/tests/test_broker_order.py` per v1.3.0's rule that tests stay under `scripts/`.
`pyproject.toml`'s `pythonpath` gained `scripts/broker` so the flat intra-package imports
resolve under pytest without a sys.path insert that would trip conftest's session guard.

**v1.3.0 changes:** `scripts/` line expanded to name the `nixverify/` engine package
and `scripts/tests/`. Tests deliberately live under `scripts/` rather than a new
top-level `tests/` — "All Python and shell scripts" already covers them, and adding
an undocumented top-level directory is the exact gap v1.2.0 closed for `state/`.

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
