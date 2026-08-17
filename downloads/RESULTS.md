# ARC 035 — Plane-1: The Durable Record

**Canonical path: `/home/bbt/nix`** (absolute; never relocated).
**Module:** Postgres / Plane-1 (Core 4–5 shared pool) + the Limiter's persistence path (sole writer).

---

## THE HEADLINE: A CORRECTNESS FIX ARMED A LATENT DEFECT AND IT CORRUPTED THE REPOSITORY

`scripts/harness.py` made five `git` subprocess calls without the D3.22 scrubbed environment. Under a
git hook, git **exports** `GIT_DIR` and `GIT_INDEX_FILE`, and **`git -C <fixture>` does not override
them** — `-C` changes the working directory; repository discovery stops at the inherited `GIT_DIR`.

Measured consequences, not inferred: a live worktree's index reduced to one entry with ~430 tracked
paths staged as deletions; `seed.txt` — a string that exists nowhere but `harness.py` — staged into a
repository that has never contained it; and **`core.bare = true` written into the canonical tree's own
config**, which is why `git status` in `/home/bbt/nix` began answering *"this operation must be run in
a work tree."* Seven `git ls-files`-based gates below it then failed their non-vacuity floors, because
the tree they measure had been emptied. **Seven "regressions" with one cause, none of them in the code
they named.**

It had been dormant for four arcs behind a hard-coded `/home/claude/work/monitor.py` — an absolute
path from another machine — which made the module `sys.exit` before `build()` ever ran. **ARC 035
Phase 0.2 fixed that path, and in the same phase registered `check_monitor_tui`, which EXECUTES the
harness inside every commit.** A latent defect plus a correctness fix equals an outage, and nothing in
this tree gates for that pairing. Found by sub-agent C from a worktree, reproduced by the integrator
against a throwaway victim, repaired at all five call sites, and now held by
`scripts/tests/test_harness_git_isolation.py` — which carries a **both-halves control**: the
unscrubbed copy must corrupt a victim, the shipped one must leave its index byte-identical.

**Writing that test found a second §7.12 hazard in the instrument itself.** The first draft exported
`GIT_WORK_TREE` as well, and that **masks the defect completely** — with it set the fixture's
`git -C <fixture> add -A` resolves its worktree to the victim and re-adds the victim's own files, so
the index comes back byte-identical and the control goes silent: `30d7c773 -> c46768e2` without it,
`0df6ce02 -> 0df6ce02` with it, same code, same harness. The control passed vacuously and the only
reason anyone knows is that a control was written at all. **Then the commit gate caught the same class
a third time**, in this test's own reporting call: an unscrubbed `git status` inside a hook compares
the REAL repository's index against the victim's working tree and reports the entire Nix tree as
deleted. D3.22, three times in one arc, twice on the instrument built to police it. Recorded as
**D3.205**.

---

## PHASE 0 — CORRECTIONS, CARRIED RULINGS, AND THE SCHEMA FREEZE

### 0.1 — the re-measure, and a self-inflicted measurement error reported against myself

`verify.py` on trunk under **both documented interpreters** — `.venv/bin/python` (3.14.4) and
`/usr/bin/python3.14` — returned **64 passed | 3 failed | 2 cannot measure | 0 skipped, exit 1**:
byte-identical to ARC 034's banked close. Census 69 three ways. No delta. (`.venv-dev` returns
`57 | 3 | 9 | 0`; it is the *test* venv with no `zmq`, not a documented launch mode, and that
distinction is why the figures differ.)

**The pytest half of 0.1 is CONTAMINATED and is reported as such rather than quietly re-run.** A
24-minute full-suite run was started and then the tree was edited under it, so its `2 failed, 2645
passed` mixes two tree states. It is not a valid ARC 034 baseline. The honest figure is the quiescent
close-out run below.

### 0.2 — the four-artifact ceiling breach, DISCHARGED BY REAL COVERAGE

ARC 034 carried `check_artifact_gate_coverage` as a FAIL: four `artifacts` rows re-owned
`ARC 031 -> 032 -> 033 -> 035`, three re-ownings against an operator ceiling of two (D2.31). The brief
forbade both cheap discharges — another walk, and an exclusion. Neither was taken.

* **`checks/check_venv_lock.py`** — six arms of REAL two-process `flock` contention. A child
  interpreter takes the lock; the parent's `probe_lock` must report HELD **and name the child's pid**
  (a probe seeing its own hold is otherwise indistinguishable from a correct one); a non-blocking
  acquire must raise `VenvLockHeld` **naming the lock path**; `blocking=True, timeout=T` must **wait at
  least T** and then raise; and `SIGKILL` of the holder must free it — the arm that separates a real
  `flock` from a hand-rolled lockfile that wedges the box forever when its owner dies. Ten plants, one
  unmutated CONTROL.
* **`checks/check_monitor_tui.py`** — executes all three MON-1 artifacts for real. D3.113 recorded the
  disposition as *"a plant here would measure nothing"*; **the plants redden, so that sentence is
  refuted by measurement rather than argued with.** `harness.py`'s failing set is pinned **two-way**: a
  failure not in the pin is a regression, a pinned failure that stops failing is a stale pin. A
  one-directional accepted set rots.

`artifacts` is now empty — a SHRINK, which needs no admitting arc — and the gate is **GUARDED**, not
FAIL.

**A real flake was measured, on the same page as the §7.12 sentence predicting it.**
`pty: survives resize storm` passed 5/5 serially and 4/4 under four-way concurrency, and failed once
inside a loaded pytest run. It is a deadline assertion, so a busy scheduler and a broken subject are
indistinguishable there. **Widening ARM 2 to tolerate it was the cheap fix and is refused** — a
tolerated failure is invisible, a CANNOT_MEASURE is loud. One arm is listed because one was observed;
`pty: still alive after force probe` is arguably the same class and is deliberately NOT listed, because
adding an arm on suspicion converts a real future break into a shrug. **D3.204** — which sub-agent D
then measured was cited by *seven* places in shipped code and *zero* in the ledger, one of them printed
into an operator-facing verdict. The number was free; the row is now written.

### 0.3 — carried operator rulings: reported, not acted on

* **PUSH.** `main` is **22 ahead / 0 behind** `origin/main` — a clean fast-forward, re-confirmed after
  `git fetch --prune`. **NOT PUSHED.** Operator's call.
* **SPEC-A10 vendor.** Still **UNRATIFIED**, and all three preconditions re-measured as unmet:
  `blackout.CALENDAR_SOURCES` is `("scripts/crucible/calendar_data",)` — exactly one source;
  `dev_and_services_plan.md` names no calendar vendor; there is no live calendar poller. The
  conflict gate therefore stays **unbuilt with its reason recorded**, and no second source is
  manufactured. The buildable half — the ratchet that reddens if a second source ever appears without
  a flagging path — is built and live.
* **Branch protection.** ARC 032's ruleset is drafted and **NOT APPLIED**. Outward-facing GitHub
  state, operator's alone. D3.141 still stands: there is no CI, so applying it today would block every
  PR rather than protect anything.

### 0.4 — the Plane-1 schema, FROZEN

`databases/schema/plane1.sql` (v1.0.0), `docs/nix_plane1_schema_spec.md`,
`checks/check_plane1_schema.py`, live database `nix_plane1` on PostgreSQL **18.4**.

**Append-only is enforced by PRIVILEGE, not by trigger,** and the argument is in the file: a
`BEFORE UPDATE ... RAISE` trigger is dropped by the owner, disabled by one `ALTER TABLE`, skipped
wholesale by `session_replication_role = replica`, and **never fires on `TRUNCATE` at all**. A missing
GRANT has none of those bypasses. The gate treats the *presence* of a trigger on the log as a defect,
even though a trigger only adds a restriction — because it would make the weak mechanism look like the
strong one to whoever reads the DDL next.

**Proven BY ATTEMPT, which is what the brief demanded:** `UPDATE`, `DELETE` and `TRUNCATE` as
`nix_limiter`, and `INSERT` as `nix_reader`, are each refused with **SQLSTATE 42501** — against a
CONTROL `INSERT` as `nix_limiter` that SUCCEEDS, because a refusal is only evidence beside a permission
that works.

**The gate's own can-fail suite found a hole in the gate.** The reader-INSERT probe was refused with
the right SQLSTATE over a database where the reader really DID hold INSERT — because the reader lacks
`USAGE` on the sequence the `event_id` DEFAULT calls, and **a sequence refusal carries the same
42501**. Check-contract rule 11 recurring one level down: the code was right and the OBJECT was wrong.
The arm now asserts `permission denied for table plane1_event_log` as well.

**Sixteen plants.** The brief's named one — `GRANT UPDATE ON plane1_event_log TO nix_limiter` — reddens
both the catalog arm and the attempt arm. The sibling that matters almost as much is a grant on **one
partition**: PostgreSQL checks the table a statement *names*, so `UPDATE plane1_event_log` stays refused
while `UPDATE plane1_event_log_2026_08` succeeds, and a parent-only audit would call that database
append-only. Also planted: DELETE, TRUNCATE, a second writer, an enum member missing, an enum member
§12.10 never authorised, a nullable `reason`, a trigger, the exactly-once index dropped, an
*over*-restricted projection (a schema that is beautifully append-only and impossible to reconcile),
and a writer with no rights at all — which is CANNOT_MEASURE, not four free greens.

### And the disk, which reported as 234 test failures

The first attempt to bank Phase 0 returned `45 failed, 189 errors`. Every one resolved to
**`[Errno 28] No space left on device`**. `/tmp` is a 31 G tmpfs; `/tmp/pytest-of-bbt` held 15 G across
27 retained sessions. Cause: `shutil.ignore_patterns` matches **exactly**, so `".venv"` does not match
`.venv-dev`, and **zero of the seven tree-copying fixtures named it** — `test_check_halt.py` ignored
only `__pycache__` and copied both venvs and `.git` besides. Fixed at all seven and **measured**: the
same suites now run 83 passed and grow `/tmp` by 0.4 G where they previously grew it by gigabytes.

**The failure mode is the part worth keeping: a full disk does not report itself as a full disk.** It
reports as 234 failing tests across twenty unrelated subjects, every one of which looks like a
regression in whatever arc is running. **D3.206.**

---

## STAGE 1 — FOUR PARALLEL SUB-AGENTS, ALL KILLED, ALL FOUR SELF-AUDITS SURVIVED

A session cap terminated all four mid-flight — the **third arc running** (D3.191). What is different
is a measurement, not a hope: **the dispatch brief required the §0a self-audit written and committed
BEFORE the code**, and all four survived. ARC 033 and ARC 034 lost exactly this, and an integrator
cannot reconstruct reasoning nobody wrote down.

Sub-agent B's worktree index showed 412 phantom staged deletions — the harness defect above, caught in
the act. Rebuilt from HEAD without touching its working tree; every file was intact.

Each branch's own suite was measured **before** being banked, never after: **A 121 passed · B 88 ·
C 77 · D committed with its gate PASS**.

**What the four built.** A: the Postgres commit sink (`plane1_sink.py`), the provisioner, the
sole-writer gate proven by attempt, the §11-item-6 hot-path drill with a slow-sink control, and the
per-event-type coverage gate. B: the positions fold (`projection.py`), the fixture conduit
(`plane1_seed.py`), cold-start reconciliation against broker truth, and the crash-gap drill on its own
ephemeral cluster crashed with `pg_ctl -m immediate`. C: `degraded.py` — §12.4's ladder, including the
`PersistenceHaltFlag` wiring that did not exist, so that "the gate still approves during a Postgres
outage" is only evidence next to "the gate denies under disk-critical". D: the §11-item-7 full-scan
drift audit over all six of §11 item 3's aggregates, with materiality **derived** from
`reservations.AUDIT_TOLERANCE` and `reservations.MIN_MARGIN` rather than typed.

**Sub-agent D corrected this arc's own dispatch brief.** I wrote that §12.10's table *"marks
drift-audit as the one event ✅ in both planes"*. Read against the frozen document that is false in the
direction that matters — **six** rows are dual-plane. A gate anchored to that misreading would be green
today and red the moment anything else was wired. D asserted the both-planes requirement and asserted
nothing about uniqueness.

---

## STAGE 2 — INTEGRATION: FOUR DEFECTS EVERY BRANCH WAS GREEN OVER

1. **The sole-writer collision.** A built the §12.10 detector; B built a module that composes INSERTs
   against the log. Neither could see the other; A's ARM B1 fired on B's file the first time both were
   in one tree. **RULED, and the exemption is MEASURED rather than argued:** a new ARM B1b drives the
   two properties it rests on — writes only under `SET ROLE nix_limiter`, and `seed()` **REFUSES the
   production database, proven by calling it** and requiring a raise that names the database. Strike
   either and the gate reddens. That is the difference between an exemption and a hole.
2. **The `EventKind` gap.** D added `EventKind.DRIFT_AUDIT` to the frozen seam; A wrote the sink's
   event-type map against a seam that did not have it.
   `test_the_mapping_is_TOTAL_over_the_frozen_EventKind` named exactly one member. **Without that
   totality test the sink would have raised at group-commit time in production, on the one event whose
   entire purpose is to report that the books disagree.** The schema needed nothing —
   `plane1_event_enum` already carried `drift_audit` from the Phase-0.4 freeze. A's
   `UNROUTABLE_PLANE1_EVENTS` census then went 5 → 4, and its own entry had predicted it: *"the audit
   itself is sub-agent D's mandate; no `EventKind` member exists for it yet."*
3. **Four false resource declarations**, all caught by `check_observed_resource_claims` on the merged
   tree. Two were the new gates' ephemeral clusters writing thousands of files under `/tmp` while
   declaring only subprocesses. **Two were this arc's own Phase-0.2 gates**: `check_monitor_tui` and
   `check_venv_lock` declared `subprocess:python`, `covers()` matches by BASENAME, and under the system
   interpreter they spawn `/usr/bin/python3` — a declaration TRUE under one documented launch mode and
   FALSE under the other. D3.140 exactly, landing on my own work.
4. **D3.192's shape, for the fourth arc running.** Three sub-agents each bumped
   `check_order_path_bans`' module-count literal from a blind worktree: A said 30, B said 31, C said
   30. **The merged gate's own figure is 34** — larger than all three. The literal is the only reason
   the disagreement was ever visible, and it is re-banked at the gate's printed evidence, never at
   anybody's arithmetic.

**The two-way pin caught its own arc.** `check_monitor_tui`'s KNOWN_RED moved by exactly two arms —
`3a ETA is None` FAILING → PASSING and `4I whole-job ETA present` PASSING → FAILING — and both moves
have one cause: before the git-scrub repair the fixture repository was never actually created, so
`monitor.py` computed its ETAs against a repository with no history. A one-directional accepted set
would have swallowed the regression and never noticed the repair.

---

## CLOSE-OUT — MEASURED

`verify.py` on trunk: **73 passed | 3 failed | 2 cannot measure | 0 skipped | 1 guarded, exit 1** —
**identical under BOTH documented interpreters** (`.venv/bin/python` and `/usr/bin/python3.14`).

pytest: **2885 passed, 0 failed, 2 skipped, 2 xfailed** (ARC 034 closed at 2646 — **+239 tests**),
taken on a quiescent tree.

Census **79 three ways**: 79 `checks/check_*.py` on disk, 79 in `registry.json`, and
`73+3+2+0+1 = 79` in the run. `--optimize` reports the derived plan identical to the live registry.

CHECK-DEBT **211 → 220**, and nothing in that figure was typed: 220 is `check_derived_claims`' own
`derived:ledger_rows`, which FAILED against the stale 211 inside the same edit that staled it.

**Every non-PASS, named.**
* `check_ibgateway_service` **FAIL** — the tap session, by design, owed by twenty-two arcs.
* `check_uncalled_entry_points` **FAIL** — carried. D3.203's seventeen rows plus this arc's own new
  uncalled surface (`drift_audit`'s verbs). **The baseline was NOT widened to absorb any of it**,
  exactly as ARC 034 refused for its own growth. D3.209, D3.213.
* `check_untracked_attribution` **FAIL** — five artifacts sit in the canonical tree that no commit
  accounts for: three status-board files carried from ARC 034, plus
  `DASHBOARD_PY_TECHNICAL_REFERENCE.md` and `Nix_Logo_Package.zip`, which appeared at 17:44 and 18:30
  today and were not created by this arc. **Not committed, not moved, not deleted** — provenance is
  the operator's.
* `check_ibgateway_config` and `check_observed_resource_claims` **CANNOT_MEASURE** — both §17 masking
  by the same dead port.
* `check_artifact_gate_coverage` **GUARDED** — eight verify-machinery exclusions, owner **ARC 036**.

---

## WHAT WAS NOT DONE, STATED RATHER THAN IMPLIED BY GREEN

**PLANE 1 IS BUILT AND NOT WIRED, and no green here may be read as "Plane 1 is recording."** The sink,
the projection, the reconciler, the degraded-persistence flag and the §11-item-7 audit are reachable
production code whose only callers are gates, tests and drills — because there is no Limiter run loop
in this tree to call them from. `seam.EventKind` still cannot emit `filled` at all, and `filled` is the
event the positions projection is mostly a fold *of*. **D3.213.**

* **Stage 2's drills were not run as separate composed end-to-end runs.** Their substance is carried by
  gates that drive the real thing — a real `pg_ctl -m immediate` crash of a real ephemeral cluster, a
  real `EFBIG` from the kernel, a real two-process `flock` — but a single composed drill across all
  three was not executed. Owed.
* **Stage 3.2's observer sweep was not run** (three orders × two sweeps × two interpreters). The
  merged tree was measured under both interpreters and they agree, but the order-dependence sweep is
  not that measurement. Owed.
* **Stage 3.4's binding table was not rebuilt.** The last binding census is ARC 033's
  (BOUND=60, ENR=1, UNBOUND=0) and it now predates sixteen gates. Owed, and it was owed before this
  arc too.
* **A power cut is not tested.** Nothing here drops the page cache. Postgres durability rests on
  `pg_ctl -m immediate` + `synchronous_commit=on` + observed recovery; the local WAL's rests on an
  observed `fsync` syscall with a both-halves control. Neither is a power-loss test.
* **The live `nix_plane1` database was never taken down.** Every real-outage claim is about an
  ephemeral cluster running the same frozen DDL.
* R5 Scoring reads Plane 1 and is not built. Backup/DR (`elements_v2.md` §4) is a later arc — and a
  durable record with no proven-restorable backup survives a process crash, not a disk. The analytics
  trade-history store is a separate database and the migration seam is **declared, not built**. No
  systemd unit was enabled, started, installed or reloaded. A non-stop guarantee proven in sim is not
  proven live; there is no venue on this node and every broker in every arm is a double.

---

## OPERATOR / ARCHITECT ITEMS STILL OPEN

1. **The tap session** — console task, ~40 min, owed by twenty-two arcs. The only code-independent FAIL.
2. **The push** (22 ahead, clean fast-forward), **the SPEC-A10 calendar vendor**, and **branch
   protection** — all outward-facing, all still open.
3. **Provenance on five untracked artifacts** in the canonical tree.
4. **Backup/DR** as a gated safety property — a backup that silently stops is the "green while
   measuring nothing" class.
5. **v1.4 fold + D3.33** — amendments run to SPEC-A10 and the v1.4 file lags.

**Canonical path: `/home/bbt/nix`.**
