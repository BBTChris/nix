# ARC 035 · Stage 1 · SUB-AGENT A — §0a self-audit

**Branch:** `arc-035-a` · **Worktree:** `/home/bbt/nix-wt-arc-035-a` · **Canonical tree:** `/home/bbt/nix`

**Mandate:** the Plane-1 **writer** (A1 sink + migration), the **sole-writer proof by attempt**
(A2), **group-commit off the hot path** (A3), and **every §12.10 event actually writes a row** (A4).

Written and committed BEFORE the code, per the common brief §2 (ARC 033/034 lost their sub-agents'
reasoning to a session cap with the work staged and unbanked — D3.191). Updated as I learned; the
final state is what is banked.

---

## THE QUESTION: what would have to be true for my deliverable to complete successfully while
## measuring nothing?

Condition by condition. Each is either CLOSED (and by what), or NAMED as open.

### A1 — the Postgres commit sink

1. **The sink could never be called by anything real.** A `CommitSinkPort` implementation that
   compiles, has tests, and is wired to nothing is `RecordingSink` with a longer name. *Closed:*
   `Plane1PostgresSink` is driven **through `GroupCommitWriter`** in every test that claims a row
   landed — never by calling `.commit()` directly — so the path under measurement is §9's own
   `enqueue → durable local WAL → shared-pool writer → group-commit`. Where a test does call
   `.commit()` directly it is a unit test of the SQL and says so in its name.
2. **The sink could write to a database nobody else uses.** A scratch database built from the
   shipped DDL is the correct *test* substrate, but if the sink can only ever be pointed at a
   scratch database the production claim is vacuous. *Closed:* the sink takes a database name and
   the default is the module constant `nix_plane1`, the same literal `check_plane1_schema.PLANE1_DB`
   carries; a test asserts the two literals agree. *Open, and named:* nothing in this tree
   *constructs* a `Plane1PostgresSink` in a daemon yet — there is no daemon. The sink is reachable
   production code with no production caller, which is exactly the finding sub-agent D's D2 sweep
   is looking for. I record it rather than hide it, and I do NOT claim the production path is live.
3. **"One transaction per batch" could be a docstring.** *Closed:* the batch is a single `psql -c`
   string beginning `BEGIN;` and ending `COMMIT;`, and a can-fail test plants a row that violates
   the CHECK constraint in the MIDDLE of a batch and asserts **zero** rows from that batch landed.
   Atomicity proven by the all-or-nothing outcome, not by reading the SQL.
4. **The migration could be "idempotent" because it never does anything.** A provisioner that
   silently no-ops on a *partially* applied database is worse than one that fails. *Closed:*
   `provision_plane1.py` distinguishes ABSENT (create + apply), COMPLETE (verify + report), and
   INCOMPLETE (refuse, naming the missing objects) — three outcomes, and the third is a loud
   refusal, not a repair. A test drives all three.
5. **`wal_seq` could be a constant.** A column that is always 0 is not ordering. *Closed:* the sink
   carries a monotonic counter seeded from `max(wal_seq)` in the target database (`max_wal_seq`),
   and a test asserts strictly-increasing `wal_seq` across two writer sessions. *Named limitation:*
   between restarts the counter is re-derived from the DATABASE, so a WAL whose tail Postgres never
   saw re-numbers on replay. That is the same in-memory-cursor limitation `GroupCommitWriter`
   already declares; I did not invent a durable cursor whose own durability nothing here proves.

### A2 — sole writer

6. **The static scan could scan nothing.** `git ls-files` returning an empty list, a glob that
   matches no file, a regex that matches no construction — every one of them reports "no unauthorised
   writer found" over an empty population. *Closed:* the gate asserts non-vacuity floors before it
   reports anything — a minimum number of scanned files, a minimum number of *found* `EventRow(...)`
   constructions, and a minimum number of *found* `enqueue(` call sites. Below any floor the verdict
   is `CANNOT_MEASURE`, never PASS (§17). The floors are floors, not today's numbers.
7. **The privilege half could duplicate `check_plane1_schema` ARM 9** and inherit its green for
   free. Doctrine C.9. *Closed by measuring a DIFFERENT thing:* ARM 9 proves *the database refuses
   an ad-hoc statement*. My arm proves *the shipped sink, run under a non-Limiter role, is refused* —
   i.e. the WIRING, which `check_plane1_schema`'s own §7.12 hazard 5 explicitly declares out of its
   scope and hands to "the sole-writer gate". The instrument is `Plane1PostgresSink` itself, not psql.
8. **The refusal could be for the wrong object.** Phase 0.4 already found this one level down: a
   sequence refuses with SQLSTATE 42501 exactly as loudly as a table. *Closed:* the arm asserts
   SQLSTATE `42501` **and** `permission denied for table plane1_event_log` in the same stderr —
   never the exit code alone, never the SQLSTATE alone (standing rule; check-contract rule 11).
9. **The refusal could be true of a role with no rights at all.** *Closed:* the control runs the
   identical sink against the identical database as `nix_limiter` and requires the INSERT to
   **succeed** and the row to be readable back. Refusal is evidence only beside a permission that works.
10. **The static scan is blind to dynamic dispatch** — `getattr(obj, "en" + "queue")`, an ORM, a
    `psql` invocation assembled at runtime, a subprocess reading SQL from a file. **NOT CLOSED, and
    it cannot be closed by a static scan.** It is stated in the gate's docstring, in its evidence
    line, and here. It is why the privilege half exists: the database refuses a second writer
    whether the scan can see it or not. Neither half alone is the proof.

### A3 — group-commit off the hot path

11. **An idle-system latency test.** The brief names this and it is the one I would otherwise have
    written: measure gate latency, see a small number, declare isolation. It measures a fast box.
    *Closed:* the measurement is a CONCURRENT drive — a writer thread committing through a
    **deliberately slow** sink (a real `time.sleep` inside `commit`, not a mock) while the gate
    evaluation loop runs — and it ships a **CONTROL** in which the identical gate loop is wired
    SYNCHRONOUSLY to the identical slow sink. The claim is the DIFFERENCE between the two, not the
    absolute figure. If the control's latency were not inflated, the instrument would be measuring
    nothing and the gate says so and returns `CANNOT_MEASURE`.
12. **A single timing.** *Closed:* n = 2,000 gate evaluations per arm, and the statistic reported is
    the **p99** (plus median and max), because a hot path that blocks does so on a minority of
    iterations — a mean would dilute exactly the signal being looked for.
13. **The "gate evaluation" could not be the real gate.** A synthetic `pass` loop proves nothing
    about `nixrisk.gate`. *Closed:* the loop calls the real `RuleChain`/gate evaluation from
    `scripts/nixrisk/gate.py` over a real `ProposedOrder` and `FinancialPicture`. *Named:* the
    picture and the ports are in-memory doubles — §11 makes the entry pathway *cache reads and
    arithmetic only*, so in-memory IS the specified substrate here, not a shortcut.
14. **The slow sink could be slow in a way the hot path could never see.** If the writer thread and
    the gate loop never overlap in time, "the gate did not block" is trivially true. *Closed:* the
    drill reports the number of commits that COMPLETED during the gate loop and requires it to be
    above a floor; zero overlap is `CANNOT_MEASURE`.
15. **The GIL could make this a Python-scheduling measurement rather than an architecture one.**
    **NOT CLOSED — named.** `time.sleep` releases the GIL, so the concurrency is real for the shape
    under test (a sink blocked on I/O), and blocking on `psql`/socket I/O releases it likewise. What
    this drill does NOT prove is isolation against a sink that burns CPU in Python. Stated in the
    gate's docstring and its evidence.

### A4 — every §12.10 event writes a row

16. **One event type driven and generalised.** The brief names this as manufactured coverage.
    *Closed:* the drive is a loop over the **18** members of `plane1_event_enum`, each with its own
    row in the reported table, each asserted individually for the four §9 fields.
17. **A synthesized row could be presented as a production drive.** Constructing an `EventRow` in a
    test and pushing it through the WAL proves the *transport*; it does not prove that any
    production code path ever emits that kind. Conflating the two is the manufactured coverage the
    brief forbids. *Closed by SPLITTING the claim into two measured columns:* `TRANSPORT` (the kind
    was driven through the real enqueue → WAL → group-commit → Postgres path and its row landed with
    all four §9 fields) and `PRODUCER` (a production module in `scripts/nixrisk/` constructs an
    `EventRow` of that kind — derived by static scan of the tree, not asserted by hand). An event
    type with TRANSPORT and no PRODUCER is reported as **NOT YET PRODUCED**, per type, in the gate's
    own verdict — not only in my report.
18. **The producer census could be a hand-maintained list** that goes stale the moment another
    sub-agent adds an emitter. *Closed:* it is derived by AST scan of `scripts/nixrisk/*.py` for
    `EventKind.<MEMBER>` references, so B, C and D adding emitters moves the census without anyone
    editing a literal.
19. **The vocabularies could silently disagree.** `EventKind` (frozen, in `seam.py`) and
    `plane1_event_enum` (frozen, in `plane1.sql`) are NOT the same set. This is a real, measured
    finding of this sub-agent, not a hazard I closed — see the report. The mapping is explicit and
    TOTAL over `EventKind`, and a kind with no §12.10 home makes the sink **raise** rather than
    launder the row into a neighbouring enum value (fail closed and loud, directive 4). A test
    asserts the mapping covers every `EventKind` member, so a future member added to the frozen seam
    reddens here instead of being silently dropped.

### Cross-cutting

20. **`git add -A` before every gate measurement**, per the common brief. A gate that reads
    `git ls-files` measures the INDEX, and an unstaged new file is invisible to it — the failure
    mode #14 shape.
21. **A can-fail whose plant does not apply.** `str.replace` with no match is a silent no-op and the
    resulting red reads as a gate that failed to detect. *Closed:* every plant asserts its anchor
    exists (count == 1) before mutating, and every can-fail suite carries an UNMUTATED CONTROL that
    passes.
22. **Postgres could be down**, and every arm above would report "no defects" over nothing.
    *Closed:* unreachable server or absent database is `CANNOT_MEASURE` naming the psql stderr
    (§17), in all three gates.
23. **A scratch database or scratch directory could leak** onto a shared 31 G tmpfs and a shared
    cluster. *Closed:* every scratch database is named `p1a_…` and dropped in a fixture teardown;
    no fixture copies `.venv` or `.venv-dev` anywhere.

---

## THE DURABILITY TRAP, AS IT APPLIES TO ME

The common brief says to assume this brief contains at least one durability claim a process-kill
would pass vacuously, and at least one hazard stated backwards.

**My mandate contains no fsync claim** — A1–A4 are about the Postgres end of the path, and
`check_plane1_wal` already owns the fsync syscall observation with its both-halves control. I do not
re-drive it (doctrine C.9). What I must not do is let a Postgres `COMMIT` be *read* as covering the
local WAL's durability: they are two boundaries and `synchronous_commit` governs only the second.
Every scratch cluster I build sets `synchronous_commit = on` so the Postgres half is a real
durability boundary, and I say plainly that a psql-client kill proves nothing.

Candidates found, recorded in the report with what I ruled out.

---

## WHAT I AM NOT DOING (declared up front, so it is a deferral and not a gap)

- I do not build the positions projection or its rebuild (sub-agent B).
- I do not build degraded-persistence behaviour around the sink (sub-agent C) — but the sink raises
  on failure so `GroupCommitWriter` can produce §12.4's `SINK_DEGRADED`, which is C's substrate.
- I do not build the drift audit (sub-agent D).
- I do not edit `scripts/nixrisk/seam.py` (frozen), `checks/check_plane1_schema.py`,
  `databases/schema/plane1.sql`, `checks/check_monitor_tui.py` or `checks/check_venv_lock.py`.
- I do not stop, restart or reconfigure the system PostgreSQL cluster; I do not touch systemd.

---

# UPDATE — what the measurements actually said (written after the code, appended not rewritten)

The list above is the audit as reasoned BEFORE the code. This section records where the reasoning
was right, where it was wrong, and what the instruments found that no amount of reasoning would have.

## Hazards that fired for real — the audit's own can-fail

* **6 (the scan could scan nothing) fired in the useful direction.** The first run of the authorship
  scan flagged **this gate's own docstring** and **its own defect message**, because both name
  `INSERT INTO plane1_event_log` in prose and the scan read raw file text. Repaired at the cause:
  the scan now reads string LITERALS by AST, skips docstrings, and requires `VALUES`/`SELECT` so a
  MENTION is not a STATEMENT. The can-fail suite's own plant had to be assembled from two halves for
  the same reason, or the suite would have been a hit on itself and the plant would have been
  indistinguishable from the harness.
* **18 (the producer census could be stale) fired in a way I had not predicted, and it is D3.200's
  exact shape.** The first census reported ALL EIGHTEEN types DRIVEN. `scripts/nixrisk/plane1_sink.py`
  — my own mapping table — NAMES every `EventKind` member, so the AST scan counted the SINK as a
  producer of everything. The census was reading its expected value out of the artefact it polices.
  Repaired by `NOT_PRODUCERS = {seam.py, plane1_sink.py}`: one DEFINES the enum, the other MAPS it,
  and neither emits. With it, `signal`/`accepted`/`denied` come back correctly as NOT YET PRODUCED.
* **11/14 (the concurrency could be a fiction) fired twice.** The first real drill run reported
  **zero** commits overlapping the hot loop — 600 gate evaluations finish in ~9 ms and one 5 ms
  commit had not completed. That is precisely the §0a the brief names, and the floor caught it
  instead of a green being printed. Repaired by making the loop run until BOTH a sample floor and an
  OVERLAP floor are met, and by seeding the WAL before the persistence thread starts.

## A DEFECT IN EXISTING CODE, found by the A3 drill and NOT repaired here

`GroupCommitWriter.drain_once` (`scripts/nixrisk/wal.py`, shipped in ARC 028) calls
`recover(path, durable_bytes)` on EVERY drain, which re-reads and re-PARSES the entire WAL. Drain
cost is therefore O(rows) and a run is O(rows²). Measured: at ~24,000 rows a single drain spends
>100 ms decoding JSON, the persistence thread starves against the GIL, and **two** commits completed
in a loop that should have seen dozens. It is invisible in `test_wal.py` because those WALs hold
tens of rows.

Not repaired by me, and the reason is stated rather than assumed: `wal.py` is the shared substrate
of all four Stage-1 sub-agents in this arc, and a cursor rework landing on branch A would collide
with B's projection and C's degraded-persistence work. It is reported to the integrator. The drill
works around it with a declared `MAX_WAL_ROWS` cap and says so at the constant.

## A SECOND ARTEFACT, measured and reported rather than smoothed

The concurrent arm's **max** is ~one full commit while its p99 is ~16 us. That is CPython's 5 ms
switch interval meeting the drill's WAL mutex: the persistence thread holds the lock, releases the
GIL inside `fsync`, and needs the GIL back to release the lock while the hot thread holds it. It is
a real hazard of putting a mutex on the hot path — not of §11.6's architecture — and it is why the
statistic is the p99 and the max is printed anyway.

## The vacuous durability claim and the backwards hazard — what I looked for and what I found

The common brief says to assume at least one of each. What I looked at and what I concluded:

* **Vacuous durability claim, FOUND, in my own mandate rather than in the brief's prose.** A1 says
  "writing WAL records into `plane1_event_log` … in ONE transaction per group-commit batch". A test
  that drove a batch, saw `count(*) = 5`, and called the write durable would pass a SIGKILL of the
  psql client trivially — the rows are in Postgres's own WAL and the client's death is irrelevant.
  Closed by not making the claim: this sub-agent asserts ATOMICITY (a bad row in the middle lands
  ZERO rows) and EXACTLY-ONCE (a re-delivered group deduplicates), both of which are properties of
  the transaction rather than of the storage boundary, and by stating in the sink's own docstring
  that a Postgres COMMIT is a durability boundary for POSTGRES and says nothing about the local WAL,
  whose boundary `check_plane1_wal` owns on syscalls. **Sub-agent B's B3 is where a real Postgres
  crash boundary is owed**, and it needs `pg_ctl -m immediate` on its OWN ephemeral cluster.
* **Hazard stated backwards — one CANDIDATE, and I do not claim it as a confirmed instance.** A2's
  brief sentence says *"a non-Limiter INSERT is REFUSED by privilege, not merely absent from the
  code"*, and then asks for a static scan as the code half. Read literally, the static scan is the
  thing the sentence calls vacuous; the arm that carries the weight is the ATTEMPT. I built both and
  ordered them so the attempt is the load-bearing one and the scan is explicitly described as unable
  to see dynamic dispatch. That is a reading, not a defect in the brief, and I say so.
* **What I ruled OUT:** A3's "prove the gate never blocks" is not backwards — the brief supplies its
  own control and the control is the right one. A4's "each event type is its own drive" is not
  backwards either. The schema's append-only-by-privilege reasoning is right way round and
  `check_plane1_schema` already drives it both directions.

## Conditions I closed differently from how I planned

* **2 (the sink could write a database nobody uses)** — I planned to assert the two literals agree
  by importing the sibling check. A check must not import another check (§4.2, and `checks/` is not
  reliably on `sys.path` under every runner), so ARM C reads the sibling's `PLANE1_DB` **by AST from
  its source** instead. That is also the stronger form: it reads what the file DECLARES.
* **17 (transport vs production)** — I planned a two-column table in my report. The brief demanded it
  in the GATE'S OWN VERDICT, so the three states are printed per type in `evidence`, and the report
  merely repeats what the gate says.

## Still open, and named

* The sink has **no production constructor**. Nothing in this tree builds a `Plane1PostgresSink` in
  a daemon, because there is no daemon. Sub-agent D's D2 sweep should see it and should report it.
* **Five of eighteen §12.10 event types cannot be recorded at all** — the frozen `EventKind` has no
  member for `filled`, `go_timeout`, `drift_audit`, `sentinel_flatten` or `operator_action`. Three
  more are routable with no producer. That is 8 of 18 §12.10 transitions the money record cannot
  carry today, and it is a finding for the arc, not a defect of this sub-agent.
* **`EventKind.BOOT` has no §12.10 home at all** — the reverse-direction disagreement. The sink
  refuses it rather than filing it under a neighbouring type.

---

# UPDATE 2 — the defect that emptied this repository's index, twice

Two commit attempts failed on this branch. Neither was a code regression, and the second one is
worth recording because the failure mode was invisible from the failure list.

`scripts/harness.py` — the MON-1 TUI's adversarial harness, executed by `check_monitor_tui`, which
the full suite runs — made five `git` subprocess calls with **no `gitenv.scrubbed_env()`** (D3.22).
`git commit` exports `GIT_DIR` and `GIT_INDEX_FILE` to every hook and to everything a hook runs, and
`git -C <fixture>` does **not** override `GIT_DIR`: `-C` changes the working directory while the
environment still names the INVOKING repository. So `git add -A` inside the fixture staged
`seed.txt` **into this worktree's real index and dropped all 412 other entries**. `git ls-files`
then returned ONE path, and every gate whose scope is the tracked file set failed its non-vacuity
floor at once — 59 reds across `test_check_calendar_schema`, `test_check_blackout_windows` and
others, every one of which passes in isolation.

**Proven with a both-halves control**, because a repair with no demonstrated failure is a guess:

* a throwaway victim repository with 5 tracked files;
* `GIT_DIR`/`GIT_INDEX_FILE` pointed at it, `scripts/harness.py` run;
* **with the scrub: 5 files before, 5 after.**
* **control — the same harness with `env=env` removed: 5 files before, 1 after.**

FOUND INDEPENDENTLY BY SUB-AGENT C, who diagnosed it first and reproduced it against a throwaway
victim as well. This branch hit the same wall and applies the same repair; the integrator should
expect a conflict in `scripts/harness.py` and can take either side. `check_monitor_tui` still passes
with its recorded pin byte-for-byte unchanged (130 ok / 10 fail, the same enumerated failing set),
so the repair changed the environment and not the behaviour.

The lesson for the audit: **my §0a asked what would let my DELIVERABLE pass while measuring nothing.
It did not ask what would let the GATE AROUND it fail while nothing was wrong.** The second question
cost two full 26-minute suite runs and produced 59 reds that named twenty innocent subjects. Both
questions are worth asking.
