# ARC 035 · Stage 1 · SUB-AGENT C — §0a self-audit

**Branch:** `arc-035-c` · **Worktree:** `/home/bbt/nix-wt-arc-035-c` · **Canonical tree:** `/home/bbt/nix`
**Mandate:** degraded persistence — risk spec §12.4 (with §12.5, §12.9, §12.10, §9).
**Written and committed BEFORE the code**, per the common brief §2 (D3.191: ARC 033 and ARC 034 both
lost their sub-agents' reasoning to a session cap while the code survived).

> *What would have to be true for my deliverable to complete successfully while measuring nothing?*

---

## 0. The one-line answer

**Postgres would never have to go down, the disk would never have to refuse, and every assertion could
still be green** — because both of §12.4's failures are reachable in this tree today by setting a
Python attribute (`RecordingSink.fail_with`) or by reading a method that returns a constant. Fourteen
conditions below. Each is closed, narrowed, or declared open with its reason.

---

## 1. C1 — "Postgres outage ⇒ WAL buffers, trading continues, operator alerted"

### C1.1 — Postgres never goes down. *(the brief's own §0a, and the easy one)*
`scripts/wal_kill_drill.py:sink_outage` produces §12.4's outage with
`sink.fail_with = RuntimeError("planted Postgres outage: connection refused")`. That is a **boolean,
not an outage**: no server exists, no socket is closed, no connection is refused by anything.
`check_plane1_wal` ARM 5's green is over that boolean.
**Closed:** my C1 arm runs against an **ephemeral PostgreSQL cluster I build and own** (`initdb`,
`pg_ctl` on a private unix socket, `synchronous_commit=on`), and the outage is
`pg_ctl stop -m immediate` — a real crash of a real server. Evidence banked with the arm: the
postmaster's PID, that PID's **absence from `/proc` after the stop**, the socket path's absence, and
the connect stderr psql actually returned. The system cluster is never touched (see §5).

### C1.2 — "Trading continues" is measured as `admits_new_entries() == True`.
That call is one `if` over an enum. Asserting it proves the enum, not that the Limiter trades.
**Closed:** the continuation is driven through the **real hot path** while the server is down —
`gate.GatePass.evaluate` (the §3 authoritative pass) returns APPROVE, `reservations.ReservationLedger`
takes a reservation, `stops.StopBook.arm`/`maintain` moves a stop. The claim is "the Limiter kept
gating, reserving and protecting", so those three verbs are the measurement.

### C1.3 — The gate would approve anyway, because nothing connects it to persistence at all.
Measured, and it is **true of the tree as it stands**: `GatePass` takes a `HaltFlagPort`, and no
implementation of that port has ever read the WAL's persistence state. So "the gate still approves
during a Postgres outage" would be green on a system where the gate *also* approves during
disk-critical — which is the §12.4 violation this arc exists to prevent.
**Closed by building the missing wiring** (`scripts/nixrisk/degraded.py:PersistenceHaltFlag`) and by
making C1 and C2 **the same instrument in opposite directions**: the identical gate, the identical
halt port, approving under SINK_DEGRADED and denying under DISK_CRITICAL. A green on one is only
evidence next to the red on the other.

### C1.4 — The alert is "fired" into a list nobody classifies.
`Plane1Wal`'s `AlertFn` is `(event, detail)`. §12.9 requires a **tier** and requires the alert to
carry *"the cause and the relevant snapshot values, not just a code"*. An assertion that
`("wal_sink_degraded", ...)` appears in a list measures neither.
**Closed:** `degraded.PersistenceAlerts` classifies into the **existing** `survival.AlertTier` /
`survival.Alert` (reused, not reinvented) and emits through the existing `survival.AlertSink`. The arm
asserts `tier is AlertTier.WARNING` **and** the snapshot's contents.
**Open, and named as a spec finding:** §12.9's Warning tier names *"Postgres down ⇒ degraded
persistence"* verbatim, so WARNING for the sink outage is **transcribed**. §12.9 names **no tier at all
for disk-critical**, and §12.5's HALT-setter list does not name it either. My CRITICAL classification
for disk-critical is therefore **derived, not transcribed** — chosen fail-closed because §12.4 makes it
the halting failure. It is labelled `derived=True` in the code and reported as a spec gap. Anything
unrecognised is also raised CRITICAL rather than dropped, for the same reason.

### C1.5 — Rows "buffer" but nothing was ever committed before the outage, so the backlog is the
whole population and no ordering claim has content.
**Closed:** a non-vacuity floor on both sides — rows committed *before* the crash ≥ 8 and rows
buffered *during* it ≥ 8, asserted separately, with the pre-crash rows counted **in Postgres by a
`SELECT`**, not from a Python counter.

---

## 2. C2 — "Disk-critical ⇒ HALT new entries, open stops still fire"

### C2.1 — The disk never actually refuses.
**Already closed in this tree and I am reusing it, not reinventing it:** `wal_kill_drill._critical`
sets `RLIMIT_FSIZE`, ignores `SIGXFSZ`, and appends until the **kernel** returns `EFBIG`. A mock that
raises `OSError` would prove only that the code has an `except`. My C2 child uses the same mechanism
and asserts the errno reached `PersistenceState.DISK_CRITICAL` through the real `_go_critical` latch.
*Considered and rejected:* a small `tmpfs` filled to `ENOSPC` — mounting one needs root, which this
agent does not have and must not take. `EFBIG` is a real refusal by a real filesystem layer and is what
the brief blesses.

### C2.2 — **"Open stops still fire" is decided by a constant.** *(the strongest finding here)*
`Plane1Wal.protective_exit_allowed()` is `return True, "..."` — unconditional, with no branch. It
cannot return False in any state. `check_plane1_wal` ARM 4's *"protective exit permitted"* green is
therefore an assertion **about a literal**, and it would stay green if every stop in the system were
deleted. This is the `CHECK-A7` shape — *"its own output was a constant, so it decided nothing"* —
recurring inside a live gate.
**Closed:** half two is measured as an **actual protective exit produced from an actual armed stop**:
`StopBook.arm` at a fill, a price tick that **breaches** it, `StopBook.breached()` returning that stop,
**while the same WAL is really disk-critical in the same process**. The control that makes it
attributable: the same breach in the same child with the rlimit **not** set, so "the stop fired" cannot
be satisfied by a stop that would have fired anyway for unrelated reasons — and, in the disk-critical
arm, an assertion that the exit path made **no WAL append at all** (the WAL refuses every append at
that point, so an exit that needed one could not have been produced).

### C2.3 — "New entries HALT" is measured on the WAL rather than on the entry path.
`admits_new_entries()` going False halts nothing by itself; the Limiter's gate is what refuses an
order. **Closed:** the C2 child evaluates a well-formed `ProposedOrder` through `GatePass` and requires
`Decision.DENY` **naming the disk-critical rule and carrying the errno**, not merely a deny.

### C2.4 — Everything is denied, so the deny proves nothing.
A gate that denies all orders passes C2's first half and is worthless.
**Closed:** the **unmutated control** in the same child — no rlimit, same order, same manifest —
must return APPROVE. Plant and control differ in one `setrlimit` call.

### C2.5 — The pair is split across two runs so the system is never in both states at once.
Half one alone is not merely *"a system that stops trading"* (as my mandate puts it): it is a system
with **unprotected open positions**, which is strictly the worse failure of the two. Understating it is
the direction that would let someone accept it. **Closed:** both halves are asserted **in the same
process, in the same disk-critical state, against the same WAL**, and the report states the hazard the
right way round.

---

## 3. C3 — "Reconnect heals: in order, exactly once"

### C3.1 — **The outage is a clean shutdown.** *(the vacuous durability claim in my mandate)*
This is the §3 trap of the common brief, one layer up from the SIGKILL/fsync version. `pg_ctl stop -m
fast` is a *graceful* shutdown: it checkpoints, flushes everything, and loses nothing **by
construction**. "No rows lost across the outage" would then be a claim about a program that was asked
politely to exit — measuring nothing about durability, exactly as a SIGKILL measures nothing about
fsync. A `SIGKILL` of a `psql` **client** is worse still: it does not touch the server at all.
**Closed:** every outage in C1/C3 is `pg_ctl stop -m immediate` (postmaster killed, recovery required
on next start) against a cluster started with `synchronous_commit = on` and `fsync = on`, and the arm
asserts the restarted server **actually ran recovery** (the "database system was not properly shut
down; automatic recovery in progress" line in the server log) — otherwise a `-m immediate` that
happened to be preceded by a checkpoint would be indistinguishable from a clean stop.

### C3.2 — The flush is never shown a duplicate, so dedup is untested.
A flush with no duplicate in it exercises no unique index. **Closed, in both directions:**
1. **the refusal is observed** — one already-committed row re-inserted with a *plain* INSERT must come
   back `SQLSTATE 23505`, and the assertion names the **index**
   (`plane1_event_log_natural_key_uq`), not just the code. Phase 0.4 of this arc found exactly this one
   level down: the right SQLSTATE for the **wrong object** would have reported "correctly refused" over
   a live second writer. `plane1_positions_pkey` is also a 23505.
2. **the heal absorbs it** — the sink's real flush is `ON CONFLICT (natural_key, occurred_at) DO
   NOTHING`, so a deliberately re-delivered buffered group inserts **0** rows and the log's total row
   count is **unchanged**. Both numbers are read back with `SELECT count(*)`.

### C3.3 — Ordering is asserted from the wrong authority.
`event_id` is assigned at INSERT and Postgres commit order under group-commit is *batch* order; both
would "prove" ordering while proving only that a sequence increments.
**Closed:** ordering is asserted from `wal_seq`, which is stamped **at enqueue** and carried through
the WAL record (schema spec §2.2), and the assertion is a **join back to the WAL file**: the sequence
of `(wal_seq, natural_key)` read out of Postgres `ORDER BY wal_seq` must equal the sequence
`wal.recover()` reads off the WAL's own bytes. A monotone-integer check alone would pass on rows that
had been shuffled.

### C3.4 — `wal_seq`/`natural_key` are invented at flush time.
Then a re-delivered row would get a *different* key and the unique index could never fire — dedup would
be structurally impossible while looking fine. **Closed by design:** both are stamped **once, at
enqueue**, by `degraded.Plane1Enqueuer`, and travel inside the WAL record. That is also what §2.2
requires (*"a re-delivered buffered record carries its own original `occurred_at` out of the WAL"*).

---

## 4. Cross-cutting

### 4.1 — The whole drill runs against a double and the report does not say so.
**Declared per claim, in the report:** C1 and C3 carry **only** the real-cluster arm. C2 is
process-local by nature (the subject is a filesystem refusal and an in-memory stop book) and uses **no
Postgres double at all** — it uses the kernel. `RecordingSink` is not used by any arm of mine.

### 4.2 — The gate passes because its subject could not be reached, and that reads as green.
`initdb`/`pg_ctl`/`psql`/`strace` absent, or the cluster failing to start, must be
**`CANNOT_MEASURE`, never `PASS`** (contract §17, doctrine A.4). Closed in `run()` and driven by a
can-fail control.

### 4.3 — The check exists but never sees a red.
Closed by a can-fail suite in the house shape: **one** real drill per module, plants are deep copies of
its observations with **one** field changed, every plant asserts its own anchor first (a `str.replace`
with no match plants nothing — this bit twice in Phase 0 of this arc), and an **unmutated control** run
that passes.

### 4.4 — Every control asserts the exit code alone.
Standing rule. Every refusal in my code asserts the **reason**: the SQLSTATE **and** the object, the
errno, the named rule, the site. Never `rc != 0`.

### 4.5 — I add a second Plane-1 writer to make the test convenient.
§12.10: *"no new writers, ever."* Closed: the only thing that inserts into `plane1_event_log` anywhere
in my work is the group-commit sink at the end of the Limiter's own
`enqueue → WAL → writer → group-commit` path, connecting as **`nix_limiter`** via `SET ROLE`. It is a
conduit, not an author. The duplicate-refusal probe (C3.2.1) is a **rejected** insert as the same role,
which adds no row by construction; it is issued inside a transaction that is rolled back.

### 4.6 — I take down the shared cluster and destroy three siblings' work.
Structural, not a promise: nothing I write ever calls `pg_ctl`/`systemctl` without an explicit
`-D <my tmpdir>/pg`, every scratch database carries the `p1c_` prefix, and my cluster listens on a
private unix socket with `listen_addresses=''` so it cannot even be reached by TCP. Teardown is
`pg_ctl stop -m immediate` + `rm -rf` of my own tmpdir, in a `finally`.

### 4.7 — I fill the shared 31 G `/tmp` tmpfs.
Phase 0 of this arc lost 234 tests across twenty subjects to this. Closed: my scratch tree is a single
`mkdtemp`, an `initdb` cluster is ~40 MB, `RLIMIT_FSIZE` caps the disk-critical WAL at 4 KB, nothing
copies `.venv` or `.venv-dev` (`shutil.ignore_patterns` matches **exactly**, so `".venv"` does not
match `.venv-dev`), and teardown is unconditional.

### 4.8 — The integrator merges four branches blind and my seam has moved.
ARC 034's integration found a changed method signature that every branch's own gates were green over.
**Closed as far as one branch can:** I add **no new module-level names to `wal.py` and change no
existing signature there**; `CommitSinkPort.commit(rows) -> int` is used exactly as it stands. Sub-agent
A's concrete sink can be substituted for mine wherever mine is constructed. The assumptions I am making
about A's work are stated explicitly in my report so the integrator can check them rather than discover
them.

---

## 5. What I looked for and did NOT find

- **A second hazard stated backwards.** The mandate's C1 gets the famous one *right* ("trading does NOT
  stop because the record degraded"). The one I found stated backwards is §2.5's understatement of
  half-one-alone. I did not find a third; I checked the alert tiering (WARNING for a Postgres outage is
  §12.9 verbatim, correct), the ordering authority (WAL, not Postgres — correct), and the exactly-once
  mechanism (the unique index, correct).
- **A conflict between my mandate and frozen §12.4.** None: the mandate quotes it accurately. The gap
  is §12.9's *silence* on disk-critical's tier (§1.4 above), which is a gap and not a contradiction.

## 5b. Found while measuring, not predicted — added after the code was written

The audit above is what I predicted. These four were **measured** during the work and are recorded
here because an integrator cannot reconstruct reasoning nobody wrote down.

### 5b.1 — `scripts/harness.py` CORRUPTS THE REAL GIT INDEX OF WHATEVER REPOSITORY RUNS IT
**Severity: it blocked every commit in this tree, and it is D3.22's exact class.** `harness.py`'s
`build()` makes five `git` subprocess calls (`init`, two `config`, `add -A`, `commit`) **without
`gitenv.scrubbed_env()`**. Under a git hook — which is how it is reached, since
`checks/check_monitor_tui.py` executes it and the pre-commit runtime gate runs that check — git
exports `GIT_DIR` and `GIT_INDEX_FILE`, and **`git -C <fixture>` does not override them**: `-C`
changes the working directory; repository discovery stops at the inherited `GIT_DIR`.

**Observed on this worktree, mid-commit:** the index was reduced to one entry, ~430 tracked paths
appeared as staged deletions, and `seed.txt` — a string that exists nowhere but `harness.py:55` — was
staged. **Reproduced outside the repo** against a throwaway victim: `D important.py` / `AD seed.txt`,
identical. **Consequence:** the seven `git ls-files`-based gates below it in the run
(`check_artifact_gate_coverage`, `check_name_coherence` ×2, `check_order_path_bans`,
`check_uncalled_entry_points` ×3) all failed their NON-VACUITY floors — because the tree they measure
had been emptied. Seven "regressions" with one cause, none of them in the code they named.

Almost certainly **activated by ARC 035 Phase 0.2**, which fixed `harness.py`'s hard-coded
`/home/claude/work/monitor.py`. With the wrong path the module `sys.exit`ed before `build()` ever ran.
The portability fix switched on a latent index-corrupting defect.

**Fixed here** (five `env=GIT_ENV` arguments + the rationale). Verified plant-and-control: with the
scrub, the victim index is byte-identical after the run; `check_monitor_tui` still PASSes with its
`KNOWN_RED` pin unchanged (130 ok / 10 fail, same ten arms).

### 5b.2 — `EventKind` and `plane1_event_enum` DO NOT AGREE, and a naive sink would crash in production
A sink that inserted `row.kind.value` would raise *invalid input value for enum* at group-commit time
for **six of the twenty kinds**: `cold_start` (the enum spells it `cold_start_outcome`),
`force_deregister` / `kill` / `relaunch` / `quarantine` (§12.10:757 makes those ONE inventory row,
`strategy_lifecycle`), and `boot`, which §12.10 routes to **no Plane-1 row at all**. The drill carries
`EVENT_TYPE_MAP` and refuses an unmapped kind loudly rather than dropping it (a lost Plane-1 row) or
coercing it (an event type §12.10 never authorised). **The map belongs with the shipped sink, not in a
drill** — flagged for the integrator.

### 5b.3 — `check_uncalled_entry_points` is RED ON TRUNK, and my drill is the first caller of three verbs
Measured in a detached worktree at `e6775b4`, with none of my files present: **17 rows**
(`fills.py`, `join.py`, `recovery.py`, `supervision.py`, `risk_config.py`). Not mine, not new here,
and sub-agent D owns the sweep. What IS mine: the drill is the **first shipped caller** of
`GatePass.evaluate`, `StopBook.breached` and `StopBook.maintain` — the §3 gate and the stop book had
no production caller at all — so those three rows are removed from
`checks/uncalled_entry_points_baseline.json`, which a ratchet may only shrink.

### 5b.4 — the `bandit` hook environment on this node scans ZERO files and exits 0
Every file, mine and pre-existing alike, comes back *"exception while scanning file"* —
`AttributeError: 'Constant' object has no attribute 's'`, the Python-3.14 failure the config's own
comment records as fixed in 1.9.4. Reproduce:
`~/.cache/pre-commit/repoz5a6uyku/py_env-python3/bin/bandit -c pyproject.toml checks/check_plane1_wal.py`.
**Reported, not fixed** — it is a hook-environment question, not a code one, and it is outside this
branch's mandate. It needs confirming against the real hook invocation before anyone acts on it.

## 6. Declared NOT closed

- **A power cut.** Nothing here drops the page cache. Postgres durability is proven at
  `-m immediate` + `synchronous_commit=on` + observed recovery; the local WAL's durability is proven by
  `check_plane1_wal`'s observed `fsync` syscall. Neither is a power-loss test and no green of mine may
  be read as one.
- **The live `nix_plane1` database's behaviour under outage.** Untestable by me by construction — I may
  not stop the system cluster. Every real-outage claim is about my ephemeral cluster running the same
  frozen `databases/schema/plane1.sql`.
- **Which sink production actually wires in.** Mine is a `psql`-subprocess instrument. Whether the
  shipped Limiter uses A's sink, and whether the alert sink is connected to a real transport, is a
  wiring property this arc's integration stage owns, not this branch.
