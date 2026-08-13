# CLAUDE.md — Nix (Opus 5.0 optimized)

Root instruction set for Claude Code in the **Nix** project. Durable invariants only. Workflows, procedures, and subsystem detail belong in `.claude/rules/*.md` (currently empty — see below); design authority lives in `~/nix/docs/*.md`. Both are indexed below — nothing else is a source of truth.

Be extremely concise. Sacrifice grammar for the sake of concision.

## Mission

Nix is BlackBox Trading LLC's autonomous **futures** trading platform. Greenfield: may inherit lessons from prior systems, never code, resources, or unverified behavioral assumptions.

- Scope: 1–5 concurrent instruments, one strategy per instrument, no ownership ambiguity. (The risk spec's multi-strategy-per-symbol arbitration is dormant future-proofing, not operating scope.)
- Practice/sim first; live promotion is a separate explicit gate.
- Futures-native concerns in scope: contract specs, tick size, tick value, expiries, rollover, session calendars, margin regimes, exchange constraints.
- Non-goal: no spot FX, CFDs, or crypto unless added as new project scope.

## Rules — load always (`.claude/rules/`)

**Status: none exist (verified 2026-08-09).** `.claude/rules/` is not present on disk. All prior references removed — `elemets.md`, `packages.md`, `roles.md`, `directory-layout.md`, `debugging.md`, `elemet_structure.md` do not exist; do not hunt for them. Until rules are authored, the content they were meant to hold (pinned dependency manifest, script roles/ownership, canonical-paths derived from `docs/directory_structure.md`, Tier 1/2/3 gates derived from `docs/debug.md`) has no rule-layer home — read the `docs/*.md` specs directly per the table below.

**Derivation invariant (holds once rules exist):** when a source spec version-bumps, the derived rule is regenerated in the same arc. A derived rule may narrow or operationalize its spec; it may never contradict it.

Every arc, on completion, MUST: (1) append its summary to the end of `~/nix/sessions/SESSION.md`, (2) overwrite (not append) `~/nix/downloads/RESULTS.md` with that arc's full results, (3) **prove the arc is durable: `HEAD` advanced, `HEAD`'s tree contains the arc's paths (`git ls-tree -r HEAD --name-only`), and `git status --short` is empty for them.** Do not report "**** ARC completed ****" until all three are verified done — cat both files and paste the git evidence as the last action before reporting completion, and paste confirmation of their state into the chat response. **(1) and (2) are satisfiable by files that exist only in a working tree; an mtime proves a file was written, not that the work survives a `git checkout` — ARC 024 passed this gate with all 30 of its paths staged and never committed.** Mechanics, the exemption, and the ceiling: `docs/nix_check_contract.md` §16 (AMENDMENT 4).

## Specs — read on demand (`~/nix/docs/`)

Not auto-loaded. Read the ones an arc touches; they cost nothing until opened. Filenames exact.

| file | authority | read when |
|---|---|---|
| `nics_risk_subsystem_spec_v1.3.md` | **frozen — never edit; STILL THE CITED AUTHORITY** | any work on order flow, gating, sizing, stops, HALT, reconciliation, two-plane logging, §12A tunables, §13 objectives (38). Every `§x:line` citation in the tree resolves against THIS file's line numbers |
| `nics_risk_subsystem_spec_v1.4.md` | **the ARC 027 mechanical fold — NOT yet the authority** | reading the amendments in place. v1.3 + the seven `SPEC-AMENDMENTS.md` entries inserted at their named sections inside `<!-- BEGIN/END FOLDED -->` markers. Nothing reworded, nothing renumbered. `scripts/tests/test_spec_v14_fold.py` proves, on every run, that v1.4 minus the folded blocks is byte-identical to frozen v1.3 **as committed at `aaa6a28`**. **It is not cited by anything and must not be cited yet:** the fold inserts lines, so every `§x:line` coordinate below the first insertion moves, and re-pointing the tree is separate serial work (CHECK-DEBT D3.33). Two implied §2A list additions were REFUSED as editorial (D3.32) |
| `nix_strategy_contract_v1.1.md` | **binding interface** (`contract_rev 1.1.0`) | any work on the strategy seam or the bus. §3–4 schemas + §9A guarantees are the **acceptance criteria** for the Nix-side implementation; `contract_rev` mismatch = registration rejection |
| `debug.md` | **doctrine of record** (v1.2.0, three tiers) | changing gates or regenerating `debugging.md`. Supersedes any two-tier protocol found elsewhere. v1.2.0 adds **§7.12 the standing question** (required of every gate at the point it is built) and failure mode #14 — both load-bearing; this table said v1.1.0 until ARC 018, and v1.1.0 is the version that *lacked* §7.12 |
| `directory_structure.md` | canonical topology (v1.3.0) | adding artifacts or regenerating `directory-layout.md` |
| `elements_v2.md` | **non-authoritative ops input** (v2.1) | provisioning, `install.sh`, credential encryption, `verify.py`, versioning, backup/DR. Risk spec wins wherever they meet |
| `VERIFY-AND-CHECKS.md` | **doctrine — external, inherited; outranks `nix_check_contract.md`** | any work on a check or gate. Parts C and D are binding rules; Part A/B *inventory* describes the predecessor system's tree, not Nix's — inherit the lessons, never the inventory (see `nix_check_contract.md` §15.4) |
| `nix_check_contract.md` | **derived implementation spec** (v1.3.0) — subordinate to `VERIFY-AND-CHECKS.md` | any work on `install.sh`, `bootstrap.sh`, `scripts/verify.py`, or `checks/check_*.py`. §15 is the doctrine conformance map: read it first when the two appear to disagree. Was itself named `VERIFY-AND-CHECKS.md` until ARC 010 |
| `CHECK-CONTRACT-AMENDMENTS.md` | **amendment ledger for the check contract — a RECORD, not an authority** | any change to check status, actuation, or the coverage trigger. `VERIFY-AND-CHECKS.md` is unversioned, external, and has no amendment mechanism: amendments land in `nix_check_contract.md` and are recorded here. Numbered independently of `SPEC-AMENDMENTS.md`, which amends the frozen *risk* spec. **Cite as `CHECK-A<n>`; the risk ledger is `SPEC-A<n>`** (ARC 028 / 0.4) — both hold six and a bare "AMENDMENT 6" named two different rulings. `scripts/tests/test_amendment_ledgers.py` enforces the prefix and per-ledger number uniqueness |
| `CHECK-DEBT.md` | ledger of owed-but-unwritten checks (doctrine A.4) | every arc that changes the environment: record the debt rather than blocking on it |
| `dev_and_services_plan.md` | staging plan | vendor/account/stage questions: Stage 0–4 sequence, dev box, QuantVPS |
| `nix-strategy-evaluator-pipeline-6.docx` | **Crucible pipeline design** (planning-stage, no code yet; supersedes pipeline-5) | strategy candidate scoring: static/contract/structural checks, historical scoring, WFO, holdout, AI council review, paper trading, live-promotion gate, monitoring, retirement (pipeline Gates 0–9 / scorer gates G1–G7) |
| `nix_db_schema_spec.docx` | **source of truth** (v1.3.0, validated live against Postgres 16) | persistent storage: `trade_history` db, per-symbol `<symbol>_bar_history` dbs, FDW hub, symbol provisioning, `validate_schemas.sh` (40 checks) |

**Not yet authored** (do not hunt; they do not exist): capture & transform · Nix-side bus implementation · vendor integration (IBKR/DataBento/Tradovate) · session calendar · contract roll · sim/replay harness · dashboard & operator auth. (Live-promotion gate has a planning-stage design in `nix-strategy-evaluator-pipeline-6.docx` — no implementation yet.)

**Doc audit (2026-08-09):** confirmed every file above is present on disk with the exact filename listed, and spot-checked version numbers/section references against file contents — all accurate. `dev_and_services_paln.md` (misspelled duplicate) is gone; that cleanup is done.

**ARC 010 correction (2026-08-10):** the real `VERIFY-AND-CHECKS.md` was delivered and now holds that filename. What this table previously indexed under that name was a self-authored reconstruction, written in ARC 008 when the real document was not on the machine; it is now `nix_check_contract.md` and is derived, not authoritative. Section citations in `checks/*.py` and `scripts/nixverify/*` refer to `nix_check_contract.md`; doctrine citations use the real document's Part/section letters (A.2, B.4, C.3 …).

## Core directives

1. Prove real properties, not proxies.
2. Prefer direct measurement over inference.
3. Derive from a single source of truth; do not restate mutable facts.
4. Fail closed and loud.
5. Verified on-disk and running state outrank memory, briefs, and stale documentation.
6. Append history; never rewrite banked evidence.
7. Keep changes minimal, local, and reversible.
8. If a rule can be enforced mechanically, enforce it and keep prose brief.
9. `cc` is shorthand for the Claude Code CLI (launch using `cl.sh`).

## Working model

- Read this file and all load-always rules before acting.
- Root file holds durable invariants only; rule files hold workflows and detail.
- Do not duplicate the same rule in multiple places.
- Compress aggressively; extra prompt text is a liability unless it changes behavior.
- Finish the main task and test it before moving on.
- Be concise; prefer bullet TL;DR over long explanations.
- Plan before execution; insert the plan into the leaderboard. Plans need definable boundaries and measurable definitions of step success.

## Architecture invariants

- Ubuntu 26.04 LTS, headless.
- Self-contained home `~/nix`, except the system PostgreSQL cluster. Python based.
- Per-module JSON configs only; config-role and data-role JSON stay separate. Risk spec §12A is the **semantic** authority for tunables (names, defaults, cross-knob boot validation); per-module JSON is the **physical** layout; boot-loaded, restart-only lifecycle applies throughout.
- Daemons headless and self-healing; no runtime operator input. (Spec §12.11 authenticated operator verbs are exceptional control, not runtime input — build them.)

## Check contract (v2 — actuation)

Amendments recorded in `docs/CHECK-CONTRACT-AMENDMENTS.md`; mechanics in `docs/nix_check_contract.md` v1.4.0.

1. Every check verifies, corrects, installs, selected by flags — on the runner **and on the check's own CLI**. Default = measure-only; a flagless check never mutates.
2. Correct/install is followed by an **independent** re-measurement: fresh process, verify-only, real effective state. A return value from the correcting path is not a verification. The verdict after a mutation is the re-verify's.
3. Any module or setting written to disk, or changed, ships an associated check script in the same arc — or a `CHECK-DEBT.md` row. Broader than the prior environment-change trigger; supersedes it. Ledger obligation, never a build gate.
4. Status: green=Pass(0) · red=Fail(1) · light blue=Cannot-measure/skipped(2) · yellow=Guarded(3). Guarded = measured subject + known-red marker naming the discharging arc. Guarded withholds certification, never durability. Aggregate: Fail > Cannot-measure > Guarded > Pass.
5. `checks/registry.json` is the master execution plan. (The operator ruling calls it `manifest.json`; **the file on disk is `registry.json` and the NAME IS AN OPEN OPERATOR RULING — do not rename either way.**) Blocks ordered least- to most-dependent. Single-check blocks sequential; multi-check blocks parallel **only** where members' declared resources are proven disjoint.
6. Every check declares its dependency (`DEPENDS_ON`) and its resource claims (`RESOURCES`) to `verify.py`. Declarations are read **statically (AST), never by importing the check**.
7. `verify.py --optimize` derives the plan from the folder. Cycles, orphans (both directions), undeclared dependencies, and non-disjoint parallel blocks are loud errors and **no plan is written**. Proposes `<registry>.proposed`; `--commit` installs.
8. `verify.py` emits Plane-2 structured events to journald (risk spec §12.10) via stdlib `SysLogHandler`→`/dev/log`. Presentation output never enters the journal; Plane 2 never lands in `logs/`. `verify.py` never writes Plane 1.
9. A retrofitted check is a **new** check: its can-fail binding does not survive the retrofit and must be re-established, or it reverts to UNBOUND.
10. **A safety property proven while its subject is unavailable is not proven.** Where an observer cannot see a resource *because the resource is unreachable*, the verdict is Cannot-measure — **never Pass**. The attempt is the claim; a positively-observed undeclared claim outranks masking. (§17)
11. **Every can-fail control asserts the REASON** — message, site, or field — **never the exit code alone.** An exit code is a shared namespace: the detector firing, the instrument breaking, and the interpreter refusing to start all reach the same integer. Exempt only where the exit code *is* the subject (mapping-table tests). (§18)
12. Declared resource claims are checked against **observed** ones at runtime, not merely against each other. A check declaring `RESOURCES = ()` while dialling a port is measurable, not trusted. Failure policy is declared (`ON_FAIL`) and derived into the plan; a halting check is emitted as its own single-check block, because a block halts on *any* member's failure. (§4.4, §17)
13. **A rule that decides a check's verdict is written HERE and recorded in `CHECK-CONTRACT-AMENDMENTS.md`, or it does not bind.** An arc brief may propose one; a brief is not where one lives. Arc-brief section labels (`§0a`, `§0c`) are per-arc and **collide across arcs** — they are not ledger identifiers and must never be cited as ones. Measured: a declaration-only binding classifier governed three arcs' verdicts under the brief label `§0c` while `§0c` on disk meant rule 9 above, which is live; and its own output was a constant, so it decided nothing. Withdrawn — `CHECK-A7`, CHECK-DEBT D3.81. (`scripts/nixverify/measurement_path.py` is retained as a **structural instrument only**, with no authority over any verdict.)
14. **A declared EXCLUSION is a guard with its re-owning ceiling lifted, and nothing else lifted.** `check_artifact_gate_coverage` may move an artifact out of the ceiling-guarded `rows` into an `exclusions` bucket that the re-owning ceiling does not judge — but only under a recorded `CHECK-A<n>` amendment naming the architect ruling, because the gate cannot tell an authorized move from a laundering one. An exclusion stays inside the one-way ratchet (silent growth and acquired-coverage are still FAILs), stays owned by a LIVE arc (a completed owner is Cannot-measure, so it cannot outlive its owner), stays assigned under §0g, and must carry a written justification and declare itself temporary. Live under `CHECK-A8`; its current instance (thirteen artifacts, owner ARC 030, temporary) is CHECK-DEBT D3.104.

## Naming

**Nix** in prose, `nix` in identifiers. Historical spellings inside frozen artifacts: **NICS** (risk spec — read as Nix) and **node02** (means the Nix dev/execution node, currently the MS-01). New artifacts never use them.

## Change control

Append all instruction changes to `~/nix/CLAUDE-CHANGELOG.md`. Treat this file as a high-signal control surface: compact, stable, difficult to contradict.

## Design and Development Structures

- `claude.ai` is project manager and architect; never debugs. Produces arc `.md` files and prompts, each a task plus a definition of success.
- `cc` is the writer, debugger, and execution agent, with authority to do what it needs to accomplish the goal.
- `cc` writes logs exclusively by appending `~/nix/sessions/SESSION.md` (singular filename is canonical). `cc` creates or overwrites the arc's summary and comms back to claude.ai in `~/nix/downloads/RESULTS.md`.
- `cc` should use sub-agents when possible.
- End of each arc: `cc` cleans up temporary files created in the arc.
- End of each arc: `cc` states `**** ARC completed ****` and approximates what percent this arc moved development forward for this module and the whole project.
