# ARC 043 — RESULTS

**ULTRAREVIEW · Limiter slice 5 · I8 sole-writer ENFORCEMENT · TIER INTERIOR**

**BADGE: Limiter STAYS RED.** Clean set `{I5, I6, I7, I8, I10} = 5/12`, open = 7.
First invariant flip since ARC 041.

**Predecessor DERIVED:** brief said `≈ 382cbd4`; `git rev-parse HEAD` said **`2417e2a`**.
Everything below is frozen and diffed against `2417e2a`.

**Commit escalation: NO.** `scripts/limiterd.py` is on the runtime gate's uncovered list and was
NOT touched — it owns §9's first arrow only (enqueue → WAL); the INSERT-capable connection lives in
`scripts/nixrisk/plane1_sink.Plane1PostgresSink`. Every changed `.py` is known to `.testmondata`,
so the commit takes the incremental path rather than the ~43-minute full pass.

---

## ARC 043 — ULTRAREVIEW, Limiter slice 5: I8 sole-writer ENFORCEMENT

**Tier INTERIOR. Predecessor DERIVED, not cited: the brief said `≈ 382cbd4`; `git rev-parse HEAD`
said `2417e2a`.** Same one-commit lag 042 recorded — the post-write-back re-measure commits after
the RESULTS HEAD — and every freeze and diff in this arc is against `2417e2a`.

**Badge: Limiter STAYS RED. Clean set `{I5, I6, I7, I8, I10} = 5/12`, open = 7.** First invariant
flip since ARC 041.

### The owed sequencing ruling, answered at kickoff from the 038 register itself

**NO invariant of I1–I12 requires full §9 event-booking coverage, so D3.434 is NOT
Limiter-greening-blocking — it is Plane-1-module debt and the Limiter can green on its twelve
invariants without it.** Read off all twelve rows and 038's sub-agent charters A–F: I1/I10/I11 are
gate-wall ordering and cancellation, I2 is the in-process reservation ledger, I3/I4 are exit-path
independence and fill-vs-ack, I6/I7 are the cash/net-liq split and snapshot atomicity, I5/I9 are
wedge-freedom and hot-path purity, I12 is input freshness. **I8's own text is *"a second writer, or
a write that skips the WAL"*** — an identity-and-route property. Sub-agent E's charter says the same
and counts no event types. **The consequence is stated so it cannot be misread later: a green
Limiter badge with D3.434 open means the invariants hold, NOT that the money record is complete.**

### S1 — the defect reproduced on the live cluster, before a line changed

A plain script importing nothing from `nixrisk` (pids 57646/57708), ordinary connection, against the
real `nix_plane1`:

| surface | result |
|---|---|
| ambient `INSERT`, no `-U`, no `SET ROLE` | **LANDED** — `event_id 1445`, `event_type 'filled'`, SELECTed back, shape-identical to a real row |
| ambient `UPDATE` of the append-only log | **SUCCEEDED** — `reason` read back as `'rewritten by a rogue'` |
| ambient `TRUNCATE` | **SUCCEEDED** (rolled back after proving) |
| the same write DECLARING `nix_reader` | **REFUSED, SQLSTATE 42501**, `permission denied for table plane1_event_log` |

**The grants were never wrong — the last row proves they bite. They bite only a writer polite enough
to DECLARE a non-writer identity.** `Plane1PostgresSink` connected as ambient superuser `bbt` and
then voluntarily `SET LOCAL ROLE nix_limiter`; a rogue omits that line and inherits superuser. That
is ARC 038's "convention, not enforcement" in one sentence. Forged rows deleted; record restored to
its single pre-existing row.

### S2 — the enforcement, in two layers, because one was not available

A **SUPERUSER bypasses every privilege check in the executor**, and the OS user this tree runs as is
one. No REVOKE, GRANT, ownership change or RLS policy binds a superuser. **`pg_hba.conf` is the one
mechanism that does** — the postmaster evaluates it before a role's privileges exist.

* `databases/schema/plane1_hba.conf` (new) — the source of truth for the connection layer.
  `local nix_plane1 all reject`, `host nix_plane1 all 0.0.0.0/0 reject`, with `nix_limiter` and
  `nix_reader` admitted by `peer` + ident map and `postgres` kept over its own socket so DDL and
  `pg_dump` remain possible as a deliberate `sudo -u postgres` operator action. Installed ABOVE the
  distribution's general rules, because pg_hba is first-match and a block appended below `local all
  all peer` is unreachable while looking installed.
* `databases/schema/plane1_enforcement.sql` (new) — the privilege layer. Both roles become LOGIN
  and NOSUPERUSER, cross-membership is REVOKEd so neither can `SET ROLE` into the other, and the log
  keeps INSERT exclusive to `nix_limiter` with UPDATE/DELETE/TRUNCATE held by nobody.
* `scripts/provision_plane1.py --enforce` installs both idempotently and then **re-measures in fresh
  processes** (rule 2): ambient refused, both roles connect, reader's INSERT refused. It refuses to
  report success on any of those.
* `scripts/nixrisk/plane1_sink.py` — one seam: `psql -U <role>`. **The role is now the connection
  identity, not an assumed one.** `SET LOCAL ROLE` is kept as a self-set for a future pooled driver.

**A password for the writer was CONSIDERED AND REFUSED, and the reason is in the DDL:** a secret
stored 0600 under the same OS user a rogue would run as is readable by the process it defends
against. It converts a one-flag bypass into a two-line one while costing a credential no fresh
checkout has, and calling that enforcement is precisely the "weaker mechanism looking like the
guarantee" `plane1.sql` already refuses for triggers. **No trigger was added either, for
`plane1.sql`'s own recorded reason**, although the brief permitted one.

### S3 — both directions, on the real cluster

**(a) every surface S1 opened is refused.** Ambient INSERT/UPDATE/DELETE/TRUNCATE all die at the
postmaster: `FATAL: pg_hba.conf rejects connection for host "[local]", user "bbt", database
"nix_plane1"`. TCP `127.0.0.1` refused both SSL and non-SSL. Declared `nix_reader` refused with
42501 at the table. `SELECT` confirms **0 forged rows**. *Non-vacuity:* the identical rogue script
and statement against a scratch database carrying the same DDL but no hba block **landed the row,
rc=0** — the instrument works; the enforcement is what refuses.

**(b) nothing sanctioned broke.** `nix_limiter` INSERTs the live record successfully (rolled back,
explicit `event_id` so the sequence is unconsumed). `check_go_timeout` **exit 0** — a real limiterd,
258 ticks, one firing, `plane1={"booked":1,"refused":0,"wal_durable":1}`. `check_sentinel_deadman`
**exit 0** — SIGKILL, marker `['before','after']`, **replay booked 2 rows**. `check_halt` **exit 0**
— retroactive booking across a genuine SIGKILL, 14 Plane-1 rows. `check_coldstart` **exit 0**. The
Sentinel is confirmed NOT a Postgres writer and was not touched.

### S4 — the gate: ARM D, and what the plants taught it

`check_plane1_sole_writer` was EXTENDED, never duplicated (rule 8 / C.9). **ARM A has always passed
and the invariant was still unenforced, because ARM A's probe is COOPERATIVE — it drives the sink as
a role that announces itself a non-writer. A rogue announces nothing.** ARM D measures the identity
ARM A assumes away, against the live record, with every attempt inside `BEGIN … ROLLBACK` and an
explicit `event_id` so nothing durable is written and no sequence moves: a gate that forges a money
row to prove money rows cannot be forged has already done the damage.

**PLANT A** — `GRANT INSERT ON plane1_event_log TO nix_reader` (038's exact state): **exit 1**,
*"nix_reader — a NON-WRITER — wrote nix_plane1.plane1_event_log, returning event_id -1."*
**PLANT A′** — the pg_hba block removed, which is I8's actual defect: **exit 1**, *"the AMBIENT
identity wrote nix_plane1.plane1_event_log with no role declared at all … a forged §9 row
indistinguishable from a real one."* **PLANT B** — the writer's grant dropped: **exit 1**, *"the
SANCTIONED WRITER 'nix_limiter' could not write … Enforcement that also refuses the sole writer is a
regression, not a fix."* Each restored by re-running the tracked migration, not by hand; gate exit 0
after each.

**PLANT A′ FOUND A REAL DEFECT IN THIS ARC'S OWN WIRING, and that is the most useful thing it did.**
With ARM A first, the gate returned **CANNOT_MEASURE (exit 2)** on a live ambient write: the same
hba block carries the scratch-database login line, so ARM A's control could not connect and raised
before ARM D looked at the record. A positively-observed second writer shipped as "nothing was
measured", which under rule 4's `Fail > Cannot-measure` is strictly weaker than the truth. **This is
D3.409 recurring one arm along, so it took D3.409's repair:** ARM D now runs first, its defects join
`observed`, and the shape control accepts whichever identity can read the catalog — if the ambient
one can, that belongs in the evidence, not in an exception. Re-measured under the same plant:
**exit 1**, naming the forged row.

Six new tests in `test_check_plane1_sole_writer.py`, all passing, including one that drives ARM D
against an unenforced scratch database (the pre-043 world in miniature, needing no privileged edit
to arm) and one that proves ARM D leaves the row count and the sequence unmoved **on a database
where the write genuinely succeeds** — a rollback nobody reached would prove nothing.

`RESOURCES` gains `postgres:nix_plane1`, and the addition **reverses an earlier refusal rather than
forgetting it**: the token was previously rejected as unfalsifiable (D3.152's class) because nothing
in the gate dialled the live record. ARM D does, three times, every run. The claim is falsifiable
now, so it is declared.

### D3.435(b) folded in — and the word "shape" is not claimed

The brief asked for the `*_drill.py` filename-SUFFIX match to become a SHAPE match. **Three
candidate shapes were measured on this tree and each misclassified:** constant-literal §9 fields
(the drills use f-strings over a loop index — separates nothing); creates-its-own-Postgres-substrate
(clean on three drills, but MISSES `wal_kill_drill.py`, re-creating exactly one free green); and
spawned-by-a-check (true of every drill AND of `scripts/limiterd.py`, the one module §9 authorises
to be a producer). **A drill and a daemon are syntactically alike, and that is the finding.**
`DRILL_SUFFIX` is replaced by `GATE_DRIVERS`, a path→reason enumeration in the form this tree
already uses for the same problem, plus `gate_driver_liveness`, which makes the census
CANNOT_MEASURE if any named path stops existing — closing both halves of the suffix defect (no
accidental capture, no silent loss on rename), driven non-vacuously in both directions.
`signal`/`accepted`/`denied` read TRANSPORT-ONLY, the honest state. The residual is D3.440.

### FREEZE, and the wider paths explained rather than waved through

Diff against `2417e2a`: 8 modified, 2 new, +849/-17. Allowed by the brief: the two new DDL/config
files, the writer-role connection (`plane1_sink.py`, plus `projection.py`'s one `Psql.user` field
and `provision_plane1.py`'s installer), the extended gate and its test, `CHECK-DEBT.md`. **Three
paths are wider and each is a direct consequence, not a widening:** `check_plane1_schema.py` and
`check_plane1_projection.py` read the live record and the ambient identity can no longer reach it,
so they connect as `nix_reader` (and ARM 9 connects AS each role rather than assuming it — strictly
stronger); `check_plane1_event_coverage.py` is the D3.435 fold-in the brief ordered. **Nothing** in
the risk-gate seams, `picture.py`/mirror, the 042 booking, or WAL internals. **`limiterd.py` was not
touched and did not need to be** — it owns §9's first arrow only, so the commit gate does not
escalate.

### Close-out

**(b)** DERIVED reverse-dependency closure by AST import-graph inversion over the eight changed
`.py` files, never a hand list: **28 files, 15 of them tests**. Non-vacuity asserted before it was
believed — it contains `check_plane1_sole_writer.py`, `plane1_sink.py`, their tests, and the
writer-process dependents `check_realized_pnl` and `check_plane1_hot_path`. **241 passed in 91 s**
(closure + the WAL suite, added by detection: `GATE_DRIVERS` names `wal_kill_drill.py` by filename
rather than by path, so no import edge exists and the closure could not see it — a stated blind
spot, paid for rather than argued about). No cost-aware exclusion was needed. RED-before /
GREEN-after on this arc's own defect is PLANT A′: exit 1 armed, exit 0 restored.
**(c)** The gate is BOUND from three real FAIL plants, each exit 1 naming its site.
**(d)** CHECK-DEBT reconciled. **I8's discharge is an invariant flip, not a debt row.** D3.435
half (b) discharged with its search recorded; **D3.438** (enforcement stops at the OS user —
impersonation needs a service account, provisioning scope), **D3.439** (the WAL is a second surface,
latent only because no daemon runs the group-commit writer) and **D3.440** (`GATE_DRIVERS` is an
enumeration) opened. The eight CHECK-A8/A9 exclusions re-owned **043 → 044 before the write-back**,
named at kickoff from the file's own `owner` field rather than discovered at the close.

### Ops

`/tmp` inodes 13% → **5%** (six stale basetemps, 1.5 GB). **This arc added ZERO orphan scratch
databases** — `nixp1t_*` still 60 and `p1a_sink_c760218413` predates the arc, both measured at
kickoff and at teardown, neither swept (D3.437 is an operator `dropdb`).

### The prediction, stated before the tree is measured

`verify.py` **`90 | 3 | 2 | 0 | 1`, exit 1 — unchanged from 042's final.** S4 extended the existing
owner rather than adding a gate, so rule 8 / Part C.9 says no count moves; the brief's conditional
`passed+1` does not apply because no new gate file was created. The three standing fails
(`check_ibgateway_service`, `check_uncalled_entry_points`, `check_monitor_tui`) unchanged, and
`guarded` holds at 1 because the exclusions were re-pointed before this arc named itself complete.
