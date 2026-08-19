# ARC 038 sub-agent E — THE SOLE WRITER AND THE RECORD

Worktree: `/home/bbt/nix-wt-arc-038-e`   Branch: `arc-038-e`
Interpreter: `/home/bbt/nix-wt-arc-038-e/.venv/bin/python` (CPython 3.14.4)
Invariants assigned: **I8** (*the Limiter is the SOLE Plane-1 writer*, §9:549 / §12.10:729 / §14:965)
and **I12** (*the cap is fed by REAL values*, §6.5:408 / §7:470 / §15 C2–C3:983).

Every number below was produced by executing something in this worktree against the REAL system
PostgreSQL cluster, real subprocesses and real `SIGKILL`. Nothing here is a reading of the source
presented as a measurement; where I could only read, the row says CANNOT-MEASURE and why.

---

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I8 | write a Plane-1 row / rewrite one from a NON-Limiter identity, six ways, against the REAL `nix_plane1` | **VIOLATION (FE1)** — all six succeeded; nothing but convention stops them | `check_plane1_sole_writer`, `check_plane1_schema` | **yes** — proven by measurement: the scan reaches 367 files incl. `scripts/nixrisk/plane1_sink.py`; the schema gate's ARM 4/9 really do drive `nix_limiter`/`nix_reader` | **yes for what they scope** — a planted second author reddened `check_plane1_sole_writer` naming `scripts/nixrisk/_arc038e_plant.py`. **But neither gate's scope CONTAINS the effective connecting identity** — measured: zero `current_user`/`usesuper`/`rolsuper` probes of the session in either gate, so the gap in FE1 is invisible to both |
| I8 | a durable row that never went through the WAL: construct the shipped sink inside Scoring / Allocator / Sentinel / realized-P&L / a check and `.commit()` | **VIOLATION (FE2)** — five non-Limiter processes each landed a row, `Plane1Wal` never constructed | `check_plane1_sole_writer` ARM B2/B3 (static) | yes (same measurement) | **no plant needed — the gate's own docstring concedes it**: ARM B is blind to a *call* of an enumerated sink. Constructing `Plane1PostgresSink` is not an `EventRow(…)` node nor an `INSERT INTO` literal |
| I8 | attack the monotone `wal_seq`: two writers racing; a dedup replay; a real `SIGKILL` mid-drain | **VIOLATION (FE3)** — `wal_seq` is not unique (0,0,1,1,2,2), not faithful (WAL record 4 landed as `wal_seq` 8) and not gapless (4,5,6,7 missing with ZERO rows lost) | `check_plane1_crash_gap`, `check_plane1_wal` | **no, for this subject** — `check_plane1_crash_gap`'s `SUBJECTS` is `scripts/plane1_crash_drill.py` and it inspects the drill's JSON; it never reads `wal_seq` continuity in any record | n/a — **nothing in the tree detects a `wal_seq` duplicate or hole** |
| I8 | `natural_key_for`: two events colliding; one event with two keys | **VIOLATION (FE4), DISCHARGED** — one event produced two keys across the WAL round-trip; the same event landed TWICE in real Postgres. No collision found in an 816-event sweep | `test_plane1_sink.py` (`test_the_natural_key_is_CONTENT_derived_not_sequence_derived`) | yes (it really calls `natural_key_for`) | **no** — it asserts content-vs-sequence derivation and never the round-trip, so the defect was outside its scope |
| I8 | enumerate `EventKind`, prove each mappable AND emitted | **VIOLATION (FE5)** — mapping is TOTAL (18/18 resolve or raise `UnmappableEvent`), but `SIGNAL`, `ACCEPTED` and `DENIED` — §9's first three rows — are emitted by **no production path** | `check_plane1_event_coverage` | **yes, and it is honest** — it reports them `TRANSPORT-ONLY (NOT YET PRODUCED)` on every run | **n/a — it PASSES on them by design** (the ratchet is deliberately asymmetric). Green over a disclosed hole, not a hidden one |
| I8 | `SIGKILL` a real writer mid-drain and reconcile disk against Postgres | **RESISTED (RE1)** | `check_plane1_wal` | yes | not planted (its own both-halves control is already in place; C.9) |
| I12 | drive the cap end to end from a REAL fill's REAL stop distance | **CANNOT-MEASURE → and the reason is itself a VIOLATION (FE6)**: `scripts/nixrisk/gate.py` reads **no stop distance in any spelling**; swinging `stop_ticks` 1 → 1 000 000 leaves both cap rules' verdicts byte-identical | `check_allocator_caps`, `check_limiter_gate` | `check_allocator_caps` is non-vacuous **for the Allocator** (7 arms, 5 symbols, 4 bucket ceilings) | **its scope does not contain the Limiter's cap at all** — `SUBJECTS` is `nixalloc/caps.py`, `nixalloc/contention.py`, `risks/allocator_caps.config.json`; `gate.py` appears nowhere in it |
| I12 | poison the margin the cap IS fed by | **VIOLATION (FE7), DISCHARGED** — `margin_per_contract` of `0.0` or `-1000.0` made the WHOLE two-phase pass **APPROVE 100 contracts** against §15 C3 | `check_limiter_gate` | yes (drives the real `GatePass`) | **no** — it hardcodes `deployable_fraction=0.70` and a positive margin; the zero-margin branch was never driven |
| I12 | poison the net-liq mark and the survival pad | **VIOLATION (FE8, FE9), DISCHARGED** — a `(NaN, True)` mark APPROVES; `survival_safety_pad=NaN` is accepted at construction and disables the floor at every size | `check_limiter_gate`, `checks`/`risk_config` boot rules | yes | **no** — `_positive_scalars` accepts NaN (`NaN <= 0` is False) and `netliq_safety_pad` does not end in `_pct`, so no boot rule sees it |
| I12 | the `fresh` flag — is it discarded by any consumer? | **RESISTED (RE2)** — exactly one production call site (`gate.py:542`), and it short-circuits to DENY on `not fresh` | `check_limiter_gate` | yes | not planted (C.9 — its stale arm exists) |
| I12 | every poisoned stop distance and fill price into `StopBook.arm` | **RESISTED (RE3)** — twelve poisonings, twelve refusals | `check_synthetic_stop_only` | yes (AST-parses `stops.py` every run) | **no, and it cannot** — its three arms are broker imports / order verbs / native stop-order-type literals. A `stops.py` whose `_valid_distance` always returned `0` would still PASS |
| I12 | the per-tick hot path: a NaN / +inf tick price | **VIOLATION (FE10)** — `breached(NaN)` does **not** fire; `maintain(+inf)` ratchets `level` and `high_water` to `+inf` permanently | `check_synthetic_stop_only` | **yes** — 2 files AST-parsed every run, and it reddened on a plant in the REAL `stops.py` naming both sites, then green on a byte-identical restore (sha256 proven) | **yes for its own subject, no for this one** — the plant it catches is a broker delegation; a non-finite tick price is outside its three arms entirely |

---

## FINDINGS

### FE1 — Plane-1 sole-writership and append-only are enforced on a ROLE nothing runs as; the identity everything DOES run as can INSERT, UPDATE, DELETE and TRUNCATE the money record

- **Invariant:** I8. §9:549 — *"**Limiter = sole writer.** … Never overwrite."* §12.10:729 — *"Plane 1 — Financial event log … Postgres append-only, **Limiter sole writer** (§9). The auditable record of money truth. **No new writers, ever.**"*
- **Site:** `databases/schema/plane1.sql:33-43` — the argument *"APPEND-ONLY BY PRIVILEGE, NOT BY TRIGGER … the writer role is GRANTed SELECT and INSERT on the log and is granted nothing else, ever"* — and `databases/schema/plane1.sql:252-256`, the grants themselves; plus `scripts/nixrisk/plane1_sink.py:315-343` (`_run_psql`), which passes **no `-U`**, so the connection is whatever `pg_hba` resolves the OS user to.
- **Scenario (executed):** `bash /tmp/.../attack1_realdb.sh` against the **live `nix_plane1`**, as the ordinary runtime OS user, with no role assumed and no WAL. Every statement was wrapped `BEGIN … ROLLBACK` so the real record was not mutated; the executor checks a grant at statement time, so a `RETURNING` row is proof the privilege was granted.
- **Observed:**

  ```
  ### who am I to postgres
  bbt super=true

  ### A1: bare psql, NO SET ROLE, NO WAL -> INSERT into the REAL log (rolled back)
  967|filled|ARC038E-IMPOSTOR|ROW CREATED BY A NON-LIMITER
  ### A2: bare psql UPDATE an existing row (append-only claim) (rolled back)
  1|REWRITTEN BY ARC038E
  ### A3: bare psql DELETE (rolled back)
  1|DELETED FROM THE APPEND-ONLY LOG
  ### A4: bare psql TRUNCATE (rolled back)
  TRUNCATE ACCEPTED, rows now 0
  ### post-attack: the real log is untouched
  rows=1 max_wal_seq=1
  ```

  And the catalog says why:

  ```
  plane1_event_log|{bbt=arwdDxtm/bbt,nix_limiter=ar/bbt,nix_reader=r/bbt}
  bbt|t|t|{}        <- rolsuper=t, rolcanlogin=t
  ```

  `bbt` is the log's **owner AND a superuser**. `nix_limiter` holds `ar` (SELECT+INSERT) exactly as
  the DDL intends — and that constraint is simply not reachable from the identity every process in
  this tree connects as. **What stopped each attempt: NOTHING BUT CONVENTION.** Not a DB grant (the
  grant does not apply), not a schema constraint, not a single code path.
- **Why the tests did not catch it:** `check_plane1_schema` ARM 4 asks `has_table_privilege` for
  `WRITER_ROLE` and `READER_ROLE` only (`checks/check_plane1_schema.py:350-360`); ARM 9 attempts the
  mutations under `SET ROLE nix_limiter` / `nix_reader` only. Its docstring even records the premise
  — *"`SET ROLE` is a real privilege drop **even from a superuser session**"* (`:37-39`) — and then
  never asks what that superuser session can do without the `SET ROLE`. `check_plane1_sole_writer`
  drives the same two roles. Measured precisely: `current_user` appears in
  `check_plane1_schema.py` exactly ONCE, at line 37, **in prose inside the docstring**; no SQL in
  either gate SELECTs `current_user`, `session_user`, `usesuper` or `rolsuper`, so no arm of either
  gate ever asks what the SESSION can do. So the gate's own evidence sentence, *"append-only proven
  BY PRIVILEGE … and BY ATTEMPT"*, is true of `nix_limiter` and false of the runtime.
- **Status:** **BLOCKS.** Not dischargeable inside the freeze, and the reason is stated rather than
  hedged: no SQL fixes it. A superuser is exempt from every grant, and a table's owner holds
  UPDATE/DELETE/TRUNCATE by ownership. The only fix is a **non-superuser login identity for the
  runtime**, and `pg_hba.conf` on this node is `local all all peer`, so that needs either a
  `pg_ident` map or a TCP/scram credential — a system-configuration change outside this worktree and
  outside the Limiter. `ALTER ROLE bbt NOSUPERUSER` would break every other gate on the box and is
  not a candidate. **This defines ARC 039.** What I did land is the standing both-halves control
  (below) that pins the refusal to the ROLE, so the boundary's real location is on the record.
- **Debt row:** D3.388

### FE2 — the shipped Plane-1 sink is a public class any module can construct and `.commit()`, and the WAL is bypassed with nothing raised

- **Invariant:** I8. §9:549 — *"Enqueue → **durable local WAL** → shared-pool writer → **group-commit** to Postgres."* The ordering is the invariant, not a suggestion: `scripts/nixrisk/wal.py:485-501` says the one-sidedness of the crash gap depends on it.
- **Site:** `scripts/nixrisk/plane1_sink.py:457` — `def commit(self, rows: Sequence[EventRow]) -> int:` — reachable from any importer, with no evidence of WAL durability in the signature and none demanded.
- **Scenario (executed):** `attack2_impostors.py` — a scratch Plane-1 database built by the SHIPPED
  `scripts/provision_plane1.py` from the SHIPPED `databases/schema/plane1.sql`, then FIVE real
  subprocesses, each with an explicit `env=` whose `PYTHONPATH` has `/home/bbt/nix/scripts` filtered
  out and this worktree's `scripts/` prepended (D3.344), each printing the `__file__` it imported
  from so the staged-tree defeat cannot hide.
- **Observed:**

  ```
  --- IMPOSTOR scoring: rc=0
    imported nixscore.ema from /home/bbt/nix-wt-arc-038-e/scripts/nixscore/ema.py
    plane1_sink from /home/bbt/nix-wt-arc-038-e/scripts/nixrisk/plane1_sink.py
    sink.commit() landed 1 row(s) -- WAL BYPASSED ENTIRELY
    nixrisk.wal in sys.modules: True   Plane1Wal ever constructed: NO
  --- IMPOSTOR allocator: rc=0   ... landed 1 row(s)
  --- IMPOSTOR sentinel: rc=0    ... landed 1 row(s)
  --- IMPOSTOR realized: rc=0    ... landed 1 row(s)
  --- IMPOSTOR a-check: rc=0     ... landed 1 row(s)

  ### THE RECORD AFTER THE ATTACK — who authored it
  IMPOSTOR-scoring|signal|0|written by scoring, NO WAL, NO Limiter
  IMPOSTOR-allocator|signal|1|written by allocator, NO WAL, NO Limiter
  IMPOSTOR-sentinel|signal|2|written by sentinel, NO WAL, NO Limiter
  IMPOSTOR-realized|signal|3|written by realized, NO WAL, NO Limiter
  IMPOSTOR-check|halt_set|4|a check wrote the money record
  ```

  Note `wal_seq` 0–4: each impostor's sink read `max(wal_seq)+1` off the database and minted a
  plausible sequence number for a row that never touched a WAL. **`wal_seq` is therefore not
  evidence of WAL passage.** The ARC 037 realized-P&L path was attacked as its own identity and is
  the one honest case in the set: `scripts/nixrisk/realized.py` is pure and writes nothing — the
  import is all that was borrowed.
- **Why the tests did not catch it:** `check_plane1_sole_writer` ARM B1 detects *composing* an
  `INSERT INTO plane1_event_log` literal; ARM B2 detects *defining* a new `commit(self, rows, …)`;
  ARM B3 detects *constructing* an `EventRow` with no route to `.enqueue`. **Calling an enumerated
  sink is none of the three**, and the gate says so itself: *"Dynamic dispatch is invisible to it …
  That is not a hazard this gate closes; it is the reason ARM A exists. The database refuses a
  second writer whether the scan can see it or not."* ARM A is exactly the half FE1 shows to be
  hollow on this cluster. The two halves were designed to cover each other and both are open at
  once.
- **Status:** **BLOCKS.** A single Python process cannot enforce sole-writership on itself; the
  boundary §2:35 draws is a PROCESS and CORE boundary and §12.10's is a DATABASE-IDENTITY boundary.
  Both are provisioning. A caller-frame assertion inside `commit()` would be fragile theatre and I
  am not adding it under a freeze. **ARC 039.**
- **Debt row:** D3.389

### FE3 — `wal_seq` is neither unique, faithful, nor gapless, and NOTHING in the tree detects any of the three

- **Invariant:** I8 / §9:549. `databases/schema/plane1.sql:151-160` states the contract this column
  is supposed to satisfy: *"`wal_seq` — **the local WAL record number this row came from**. The WAL
  is the only place ordering is authoritative."*
- **Site:** `scripts/nixrisk/plane1_sink.py:423-427` (`next_wal_seq`, an unsynchronised
  read-modify-write over `max(wal_seq)`), `:498` (`self._next_seq = first_seq + len(rows)`, which
  advances over rows `ON CONFLICT` discarded), and `databases/schema/plane1.sql:160`/`:168`, where
  the only constraint on the column is `CHECK (wal_seq >= 0)` — no UNIQUE, anywhere.
- **Scenario (executed):** `attack3_seqrace.py` — two real subprocesses, each its own
  `Plane1PostgresSink` on the same scratch database, both resolving `next_wal_seq()` before a shared
  wall-clock barrier; then a §12.4-shaped reconnect replay of the same rows through a fresh sink.
- **Observed:**

  ```
  RACER-A: next_wal_seq() -> 0        RACER-B: next_wal_seq() -> 0
  RACER-A: landed 3 at first_seq=0    RACER-B: landed 3 at first_seq=0
  ### rows / distinct wal_seq: 6 rows, 3 distinct wal_seq
  wal_seq=0 used by RACER-A/RACER-A-0, RACER-B/RACER-B-0
  wal_seq=1 used by RACER-A/RACER-A-1, RACER-B/RACER-B-1
  wal_seq=2 used by RACER-A/RACER-A-2, RACER-B/RACER-B-2

  ### B: replay the SAME rows through a FRESH sink (the §12.4 reconnect heal)
    replay first_seq=3 landed=0 deduplicated=3
    next genuine row first_seq=6 landed=1
  ### the wal_seq sequence now: 0,0,1,1,2,2,6
  ### MISSING wal_seq: 3,4,5
  ```

  And from the `SIGKILL` drill (`attack4_kill.py`), the faithfulness half, on a database where
  **nothing was lost**:

  ```
  ### WAL on disk: 12 rows, intact=True   ### Postgres holds: 4 rows, wal_seq=[0,1,2,3]
  ### RESTART: drain: committed 8 of 12  deduplicated 4
  ### after restart: 12 rows; wal_seq=[0,1,2,3,8,9,10,11,12,13,14,15]
  ```

  WAL record #4 landed carrying `wal_seq` **8**, and `wal_seq` 4–7 do not exist. Twelve WAL records,
  twelve rows, zero loss — and a four-wide hole in the column whose documented meaning is *"the
  local WAL record number this row came from"*. So a hole is not evidence of loss, and a genuine
  loss produces the same signature: the one column §9's *"crash gap healed by startup
  reconciliation"* would have to read cannot distinguish them.
- **Why the tests did not catch it:** `test_plane1_sink.py::test_wal_seq_RESUMES_from_the_log_not_from_zero`
  asserts the resume, which is the behaviour that CAUSES this. `check_plane1_crash_gap`'s
  `SUBJECTS` is `("scripts/plane1_crash_drill.py",)` and its four arms inspect the drill's JSON
  (fsync observed, crash real, uncommitted tail discarded, the instrument still discriminates) — it
  never reads `wal_seq` continuity in any record. No other check mentions `wal_seq` continuity at
  all. There is no detector to be vacuous: **there is no detector.**
- **Status:** **BLOCKS.** A faithful `wal_seq` means the sink being TOLD the row's WAL index, which
  `GroupCommitWriter` knows (`self._cursor`) and `CommitSinkPort.commit(rows)` cannot carry. Widening
  that Protocol breaks `RecordingSink` and every double in the tree — not minimal, not local, and not
  a change to make under a freeze. Uniqueness wants a UNIQUE index on a partitioned table, which
  must include the partition key, so `(wal_seq, occurred_at)` would still admit the duplicate at a
  different instant. **ARC 039**, and it is a design question, not a patch.
- **Debt row:** D3.390

### FE4 — `natural_key_for` was not canonical: one event had two identities depending on which side of the disk it was read from

- **Invariant:** I8 / §9:549's exactly-once record. `scripts/nixrisk/plane1_sink.py:41-60` claims
  *"a re-delivery of the same WAL record cannot produce a different key"*.
- **Site:** `scripts/nixrisk/plane1_sink.py:303` (pre-fix) — `body = encode_row(row).split(b" ", 1)[1].rstrip(b"\n")`.
  `encode_row` hashes the row it is HANDED; `scripts/nixrisk/wal.py:172-180` (`decode_record`), which
  is what `GroupCommitWriter.drain_once` actually feeds the sink, COERCES on the way back off disk —
  `float(raw["ts"])`, `str(raw["strategy_id"])`, `str(raw["trade_id"])`, `{str(k): str(v) …}`.
- **Scenario (executed):** a real interpreter over every coercion `decode_record` applies, then the
  harm driven end to end against real Postgres through the shipped sink.
- **Observed:**

  ```
  int ts (annotation says float)   mem=7f462a93c5e7 disk=e00e58979319 stable=False
  int trade_id                     mem=89263044e916 disk=14ba8c18b13a stable=False
  int strategy_id                  mem=5c7d4004ed72 disk=b15dfd7805d2 stable=False
  int field value                  mem=f9c676ee...   disk=e87a0f5a...   stable=False
  float / bool / None field value  ... all stable=False
  ```

  and in the database: with the pre-fix key the SAME event landed **twice** (`count(*) = 2` for one
  `occurred_at`); with the fix it lands once and the replay reports `rows_deduplicated == 1`. An
  816-event sweep over every §9 field found **no collision** in the other direction, so the
  content-hash's distinctness claim held.
- **Why the tests did not catch it:** `test_the_natural_key_is_CONTENT_derived_not_sequence_derived`
  asserts content-vs-sequence derivation and index-sensitivity; nothing asserted stability across the
  round-trip, and every existing driver happens to build all-`str`, float-`ts` rows, so the defect
  was latent behind conforming callers. `EventRow.fields` is annotated `Mapping[str, str]` and
  **nothing enforces it** — the sink is reachable directly (FE2), so a non-conforming row is not
  hypothetical.
- **Status:** **DISCHARGED IN THIS ARC.** `natural_key_for` now PERFORMS the WAL round trip before
  hashing — `encode_row(decode_record(encode_row(row)))` (`scripts/nixrisk/plane1_sink.py:295-340`).
  It is the IDENTITY on every value the annotations allow — asserted, so no banked key moves. **The
  first version of this repair hand-copied `decode_record`'s coercions into a fresh `EventRow(…)`
  here and `check_plane1_sole_writer` ARM B3 reddened on it** (see the gate audit); calling the codec
  cannot drift from the codec, and it adds no `EventRow` construction to the sole writer. The control
  is
  `scripts/tests/test_arc038_e_plane1_record.py`, and its can-fail is `_pre_fix_natural_key`: the
  pre-fix expression byte for byte, run FIRST, and REQUIRED to split one event into two identities
  and to duplicate the row in real Postgres before the protected half is allowed to assert anything.
- **Debt row:** none needed.

### FE5 — §9's first three event types — `signal`, `accepted`, `denied` — are emitted by no production path, so the money record contains no record of any gate decision

- **Invariant:** I8 / §9:549 (*"one row per transition (signal, accepted, filled, … denied …)"*) and
  §3:111's *"deny (rule named, fail-fast)"*, whose whole point is that the deciding rule is on the
  record.
- **Site:** `scripts/nixrisk/gate.py` — the two-phase gate — contains **no** reference to
  `Plane1Port`, `EventRow` or `enqueue`. Measured: `grep -n "Plane1Port\|plane1\|EventRow\|enqueue" scripts/nixrisk/gate.py`
  returns nothing.
- **Scenario (executed):** enumerate `EventKind` in a real interpreter, resolve every member through
  `resolve_event_type`, then grep the whole tree for each member's emission.
- **Observed:** the mapping is TOTAL — all 18 members resolve, and `EventKind.BOOT` raises
  `UnmappableEvent` rather than being laundered. But:

  ```
  EventKind.SIGNAL / ACCEPTED / DENIED — every occurrence outside seam.py/plane1_sink.py:
    scripts/tests/*  (7 sites)   scripts/wal_kill_drill.py
    scripts/plane1_degraded_drill.py  scripts/plane1_hotpath_drill.py
    checks/check_plane1_sole_writer.py  (this gate's own probe rows)
  ```

  No production emitter. The gate itself agrees, on every run:

  ```
  pass: 18 §12.10 event type(s) … 11 DRIVEN, 3 TRANSPORT-ONLY (the path works; NOT YET
  PRODUCED by any module), 4 UNROUTABLE … accepted=TRANSPORT-ONLY; denied=TRANSPORT-ONLY;
  signal=TRANSPORT-ONLY
  ```
- **Why the tests did not catch it:** they DID, and then passed. `check_plane1_event_coverage`'s
  ratchet is deliberately asymmetric — *"a type gaining a producer is reported and does NOT fail"* —
  and a type that never had one has nothing to lose. The `UNROUTABLE_PLANE1_EVENTS` census in
  `plane1_sink.py:255-274` enumerates the **schema-side** gap (four types with no `EventKind`) with a
  written reason each; the mirror-image gap — a member with a mapping, a schema enum value and no
  emitter — is counted nowhere and carries no `CHECK-DEBT` row. This is green over a *disclosed*
  hole, which is a different and lesser sin than green over a hidden one, but the hole is the core of
  §9's trade lifecycle.
- **Status:** **BLOCKS.** The emitter belongs in the gate's settle path and is a build task, not an
  audit patch. **ARC 039.**
- **Debt row:** D3.391

### FE6 — the Limiter's margin cap is fed by NO stop distance at all; the wire I12 asserts does not exist in `gate.py`

- **Invariant:** I12. §7:470 Sizing Physics; §7:481 *"`risk_$` is honest only if sized against stop +
  expected slippage"*; §7:501/§7:511's bucket exposure priced from the distance.
- **Site:** `scripts/nixrisk/gate.py:436-487` (`AggregateMarginCapRule`) and `:571-629`
  (`DeployableCeilingRule`). Their entire input set is `order.margin_per_contract`,
  `order.proposed_margin`, `picture.balance`, `picture.committed`, `picture.deployable`.
- **Scenario (executed):** hold the proposal constant and swing only `stop_ticks`.
- **Observed:**

  ```
  qty=100 mpc=1000 balance=100000 cap=0.70 -> SIZE_DOWN sized=69
    stop_ticks=1         -> SIZE_DOWN sized=69
    stop_ticks=20        -> SIZE_DOWN sized=69
    stop_ticks=1000000   -> SIZE_DOWN sized=69
  ```

  A stop fifty thousand times wider changes nothing. Independently confirmed by grep:
  `stop_distance|stop_ticks|initial_distance_ticks|StopState|StopBook` has **zero** hits in
  `gate.py`. And the cap FRACTION is not fed from config either: `agg_margin_cap_pct` in
  `risks/limiter.config.json` is read by exactly one place in the tree —
  `scripts/risk_config.py:254`, its own boot validator — while every value reaching
  `AggregateMarginCapRule` comes from a drill, check or test literal (`plane1_hotpath_drill.py:231`,
  `plane1_degraded_drill.py:827`, `check_limiter_gate.py:813`, …). So
  `interlock.margin_cap_within_deployable` validates a relationship between two numbers that no
  shipped rule instance ever reads.
- **Why the tests did not catch it:** `check_allocator_caps` — seven arms, genuinely non-vacuous —
  has `SUBJECTS = ("scripts/nixalloc/caps.py", "scripts/nixalloc/contention.py", "risks/allocator_caps.config.json")`.
  It measures the **Allocator's** per-bucket correlation cap, priced from `tick_value_usd`. The
  Limiter's two margin-cap rules are not in its scope, and `check_limiter_gate` supplies the fraction
  as a literal. Nothing compares the two sides.
- **Status:** **BLOCKS.** This is D3.150/D3.178's residual restated at the cap: the stop distance
  reaches `PositionRow.stop_distance` (`positions.py:565`) and §7:501's bucket exposure, and the
  Limiter's own cap never asks for it. Whether it SHOULD is a spec-reading the architect owns.
  **ARC 039.**
- **Debt row:** D3.392, D3.393

### FE7 — a `margin_per_contract` of `0.0` or negative makes the WHOLE two-phase gate APPROVE, against §15 C3's *"missing margin ⇒ not-tradable"*

- **Invariant:** I12. §15 C3:983 — *"C3 Sizing guards: zero/invalid stop ⇒ deny; **missing margin ⇒
  not-tradable**; clamp ≥ 0."*
- **Site:** `scripts/nixrisk/gate.py:475` — `if picture.committed + proposed < cap: return _clear(self._name)`
  — and `:611` — `if proposed <= picture.deployable: return _clear(self._name)`. With
  `margin_per_contract <= 0` the `proposed_margin` is `<= 0`, so both comparisons clear on the
  CHEAPEST branch. The `<= 0.0` guard that exists (`gate.py:360-361`, in `_largest_fit`) is reached
  only on the size-down branch, i.e. only when the cap has already bitten.
- **Scenario (executed):** `attack_i12b.py` / `attack_i12c.py` — the real `GatePass` with the real
  `default_manifest`, on a COHERENT financial picture (so `PictureCoherenceRule` cannot mask the
  result), control first.
- **Observed:**

  ```
  CONTROL mpc=1000, qty=100 (cap must bite)    -> SIZE_DOWN   rule='aggregate_margin_cap'
  mpc=0.0, qty=100                             -> APPROVE     rule='manifest_exhausted'
  mpc=-1000.0, qty=100                         -> APPROVE     rule='manifest_exhausted'
  ```

  A hundred contracts admitted through §6.5's hard cap because their margin was declared as nothing.
  `ProposedOrder` performs no validation of the field, so the poisoned order is constructable —
  and §2:35 makes the Limiter **prohibitive**, so trusting the permissive Allocator to have produced
  a positive number is exactly the trust the authority split forbids.
- **Why the tests did not catch it:** `check_limiter_gate` drives the real `GatePass` but always with
  a positive margin and `deployable_fraction=0.70` hardcoded (`checks/check_limiter_gate.py:813`); no
  arm drives a zero or negative margin. The guard's existence inside `_largest_fit` reads, on
  inspection, as though the case were covered.
- **Status:** **DISCHARGED IN THIS ARC.** One shared guard, `_unpriceable_margin`, at the top of both
  cap rules' `evaluate`: a `margin_per_contract` that is not a positive finite number is a DENY
  naming §15 C3. Control: `scripts/tests/test_arc038_e_limiter_cap.py`, whose can-fail runs the
  UNPROTECTED half (the guard removed by monkeypatching it to return `None`) and REQUIRES the
  APPROVE to reappear.
- **Debt row:** none needed.

### FE8 — a net-liq mark of `NaN` with `fresh=True` clears §6.5's survival floor

- **Invariant:** I12. §15 C2:983 — *"C2 Survival floor corrected to **net-liq** … broker liquidates
  on net-liq"*; `nics_risk_subsystem_spec_v1.3.md` §14:965 — *"**Survival is watched on net-liq**"*; and separately `nix_check_contract.md` §17 — a
  safety property proven while its subject is unavailable is not proven.
- **Site:** `scripts/nixrisk/gate.py:557` — `if net_liq < floor:`. `NaN < anything` is `False`, so
  control falls through to `_clear`.
- **Scenario (executed):** the real `GatePass`, coherent picture, arithmetic stated so the control is
  not a coincidence: `projected = 50 000 + 1 000 = 51 000`, pad `0.25` ⇒ `floor = 63 750`.
- **Observed:**

  ```
  CONTROL net_liq=1_000_000 (well above the floor)      -> APPROVE
  net_liq=60_000 (BELOW the 63_750 floor) -> must DENY  -> DENY  rule='survival_headroom'
       §6.5 survival floor: net_liq 60000.0 < projected Σ open margin 51000.0 x (1 + 0.25) = 63750.0
  net_liq=NaN, fresh=True                               -> APPROVE   <-- FAIL-OPEN
  ```

  The rule's own docstring calls the mark *"the only reading that stands between this account and a
  broker liquidation"*.
- **Why the tests did not catch it:** the freshness arm exists and works (RE2), and a NaN mark is not
  a stale mark — it is a fresh nonsense one, and no arm drives it. `NetLiqMarkPort` has **no
  production implementation at all** (FE6/D3.393), so every mark in the tree is a hardcoded
  `10_000_000.0, True`, which is comfortably above every floor any test builds.
- **Status:** **DISCHARGED IN THIS ARC** — `evaluate` denies a non-finite mark, with the same §17
  reasoning the stale arm already uses. Control + can-fail in `test_arc038_e_limiter_cap.py`.
- **Debt row:** none needed.

### FE9 — `survival_safety_pad = NaN` is accepted at construction and silently disables the survival floor at every size, and no boot rule rejects it

- **Invariant:** I12 / §12A:797 cross-knob boot validation; §15 C2.
- **Site:** `scripts/nixrisk/gate.py:520` — `if safety_pad < 0.0: raise KnobError(...)`. `NaN < 0.0`
  is `False`, so NaN is admitted; then `floor = projected * (1.0 + NaN)` is `NaN` and `net_liq < NaN`
  is `False` for every mark. Boot side: `scripts/risk_config.py:212-230` (`_positive_scalars`) uses
  `leaf <= 0`, which `NaN` also passes, and `_pct_range` (`:233-248`) only inspects keys ending
  `_pct` — `netliq_safety_pad` does not.
- **Scenario (executed):** the real `GatePass`, the SAME case that must deny, with only the pad
  changed; then the real boot rules over a real `ModuleConfig`.
- **Observed:**

  ```
  net_liq=60_000 but pad=NaN                         -> APPROVE   <-- FAIL-OPEN
  net_liq=60_000, pad=0.25 (the same case, sane pad) -> DENY  rule='survival_headroom'

  netliq_safety_pad=nan          -> ACCEPTED AT BOOT  <-- no rule sees it
  netliq_safety_pad=inf          -> ACCEPTED AT BOOT  <-- no rule sees it
  netliq_safety_pad=-1.0         -> REJECTED
  ledger_drift_tolerance_usd=nan -> ACCEPTED AT BOOT  <-- no rule sees it

  and does json.loads even accept a bare NaN token in a config file?
      {'netliq_safety_pad': nan}
  ```

  So a NaN can physically reach the config file, survive boot validation, be accepted by the rule's
  constructor, and turn off §6.5's survival floor with nothing raised anywhere.
- **Why the tests did not catch it:** `test_risk_config.py` drives negative and out-of-range values;
  NaN passes every `<`/`<=` comparison an ordering-based validator can make, which is precisely why
  a finiteness test has to be explicit.
- **Status:** **DISCHARGED IN THIS ARC**, on both sides: `SurvivalHeadroomRule.__init__` refuses a
  non-finite pad, and `risk_config._positive_scalars` refuses a non-finite scalar (which also closes
  `ledger_drift_tolerance_usd` and every future non-`_pct` knob). Controls + can-fails in
  `test_arc038_e_limiter_cap.py`.
- **Debt row:** D3.395 — the residual: `json.loads` in `risk_config._read_one` has no
  `parse_constant` guard, so `NaN`/`Infinity` tokens still PARSE; they are now caught one layer
  later, by value, rather than refused at the file boundary.

### FE10 — the per-tick stop path has no finiteness guard: a `NaN` tick makes a breached stop report NOT breached, and one `+inf` tick destroys the level permanently

- **Invariant:** I12-adjacent, and §14:965 — *"Every uncertainty resolves toward **flat**"*; §11:579
  hot path.
- **Site:** `scripts/nixrisk/stops.py:292` (`maintain`), `:313` (`breached`), `:187` (`_breached`),
  `:373` (`_ratchet`). `arm` is guarded at `:255`; `maintain`/`breached` are not.
- **Scenario (executed):** a real `StopBook`, a LONG armed at 4500.00 with 20 ticks at 0.25 ⇒ level
  4495.0, then poisoned tick prices.
- **Observed:**

  ```
  breached(4494.00)  (below the level, must fire) -> ['cX']
  breached(4510.00)  (above, must not fire)       -> []
  breached(price=NaN  ) -> DOES NOT FIRE
  breached(price=+inf ) -> DOES NOT FIRE
  breached(price=-inf ) -> FIRES
  breached(price=0.0  ) -> FIRES

   armed TRAILING level=4495.0 high_water=4500.0 activated=False
   after maintain(4520.0): level=4517.5 high_water=4520.0 activated=True
   after maintain(NaN):    level=4517.5 high_water=4520.0 activated=True  (silent no-op)
   after maintain(+inf):   level=inf    high_water=inf    activated=True
  ```

  After one `+inf` tick the trailing stop's level and high-water mark are `inf`, which is permanent
  state corruption: every subsequent price satisfies `price <= inf`, so the stop reports breached
  forever. `NaN` is the more dangerous direction — a stop that cannot answer reports "not breached",
  which is an uncertainty resolving away from flat.
- **Why the tests did not catch it:** `check_synthetic_stop_only`'s three arms are broker imports,
  order verbs and native stop order-type literals — a `stops.py` whose `_valid_distance` always
  returned `0` would still PASS it. `test_stops.py` drives the arm guards thoroughly and does not
  drive a non-finite tick.
- **Status:** **BLOCKS — deliberately not fixed here.** A per-tick `math.isfinite` is a §11:579
  hot-path cost, and §11 says *"Hot path = cache reads + arithmetic only"*. Whether the guard belongs
  on the tick or at the price ring's producer is an architect's call, not a freeze patch, and
  `stops.py` may be another sub-agent's subject this arc. **ARC 039.**
- **Debt row:** D3.394

---

## PROOFS OF RESISTANCE

### RE1 — I8 held: §9's crash gap is ONE-SIDED across a real `SIGKILL`, and exactly-once survives the heal

- **Attack:** a real writer subprocess enqueued 12 rows, fsynced them, committed one group of 4,
  announced, and was `SIGKILL`ed mid-drain; then the WAL on disk was reconciled against Postgres by
  natural key, and a restarted writer with a zero cursor re-presented everything.
- **Command + output:** `attack4_kill.py`

  ```
  ### SIGKILL: waitpid status=9 signalled=True signal=9 (expect 9)
  ### WAL on disk: 12 rows, intact=True, torn=0B, corrupt=0
  ### Postgres holds: 4 rows, wal_seq=[0,1,2,3]
  ### CRASH GAP = 8 row(s) on disk that Postgres never saw
     PG keys not in the WAL: NONE (gap is one-sided, as §9 requires)
  ### RESTART: cursor 0, durable_rows 12 -> committed 8, deduplicated 4, err none
  ### rows duplicated by natural_key: NONE — exactly-once held
  ```
- **What this does and does NOT prove:** it proves the FORBIDDEN direction (Postgres holding a row
  the durable WAL lost) did not occur on this run, and that the content-derived key made the replay
  idempotent. It proves **nothing about fsync** — a `SIGKILL` leaves dirty pages with a living
  kernel; `check_plane1_wal`'s `strace` arm owns that boundary and I did not re-drive it (C.9). It
  also proves nothing about §9's *"reconciliation vs broker truth"*, which does not exist.

### RE2 — I12 held: the `NetLiqMarkPort` freshness flag is not discarded by any consumer

- **Attack:** enumerate every `.mark(` call site under `scripts/` excluding `scripts/tests/`, then
  drive the one that exists with `fresh=False`.
- **Command + output:** exactly one production call site — `scripts/nixrisk/gate.py:542`,
  `net_liq, fresh = self._port.mark()`, inspected on the very next line. Driven:

  ```
  mark says NOT fresh   -> DENY  rule='survival_headroom'
       §6.5 net-liq mark is STALE or absent, so the survival floor cannot be evaluated. Denying:
       a safety property proven while its subject is unavailable is not proven
  ```
- **What this does and does NOT prove:** the flag is honoured by the only consumer that exists. It
  does NOT prove the flag is ever `False` in reality — there is no production `NetLiqMarkPort`
  implementation anywhere (D3.393), so nothing produces the flag at all.

### RE3 — I12 held: `StopBook.arm` refuses every poisoned distance and every poisoned fill price

- **Attack:** twelve poisonings of the one place a stop distance becomes a price.
- **Command + output:** `attack_i12d.py`

  ```
  stop_ticks = 0 / -5 / True / 2.5 / NaN            -> InvalidStopIntent (refused)
  fill_price = 0.0 / NaN / inf                      -> InvalidStopIntent (refused)
  symbol unknown / tick_size = 0.0 / tick_size = NaN-> UntradableSymbol   (refused)
  TRAILING with no trail_ticks                      -> InvalidStopIntent (refused)
  re-arm of the SAME client_order_id at a NEW fill  -> DuplicateStop     (refused)
  ```

  And the honest happy path, traced: fill 4500.00, `stop_ticks` 20, tick 0.25 ⇒
  `initial_distance_ticks=20`, `anchor=4500.0`, `level=4495.0`, and `4500.00 - 20×0.25 = 4495.0`
  matches.
- **What this does and does NOT prove:** the conversion is guarded, exactly once, and refuses rather
  than clamping — §15 C3's *"zero/invalid stop ⇒ deny"* is genuinely implemented at the arm. It
  proves nothing about the distance being RIGHT, nothing about the cap seeing it (FE6), and nothing
  about the path being reached: no production code constructs a `StopBook`.

### RE4 — I12 held: a rule that raises is a DENY, not an approve

- **Attack:** poison the cap's inputs with `NaN` so `int(NaN)` raises inside `_largest_fit`.
- **Command + output — measured BEFORE this arc's FE7 fix**, which is the state the invariant had to
  be tested in:

  ```
  margin_per_contract = NaN  -> DENY  rule='aggregate_margin_cap'
       rule raised ValueError: cannot convert float NaN to integer — a rule that cannot answer
       has not approved (§5: side-effect-free, non-blocking; directive 4: fail closed)
  picture.balance = NaN      -> DENY  rule='aggregate_margin_cap'
  picture.deployable = NaN   -> DENY  rule='deployable_ceiling'
  ```

  **After the fix the first line moves and the other two do not**, which is worth stating because a
  reader re-running this will see a different reason: a NaN `margin_per_contract` is now caught by
  `_unpriceable_margin` and denies naming §15 C3, while a NaN `picture.balance` or
  `picture.deployable` still reaches `int(NaN)` and denies via the executor's catch. Re-measured
  after the fix:

  ```
  mpc=NaN, qty=100  -> DENY  rule='aggregate_margin_cap'
       §15 C3 missing margin ⇒ NOT-TRADABLE: margin_per_contract=nan for 'ES' is not a positive
       finite number …
  ```
- **What this does and does NOT prove:** `GatePass._dispatch` (`gate.py:770-780`) catches any rule
  exception and denies, naming the rule — genuinely fail-closed, and that is why the poisoned-picture
  cases were left alone rather than guarded (minimality: they already deny). It does NOT make them
  *good*: the deny arrives as a stack-trace string rather than a §6.5 reason, and the guard is the
  executor's, not the rule's. FE7–FE9 are the cases that do NOT raise, which is why they were the
  dangerous ones.

---

## GATE AUDIT

### check_plane1_sole_writer
- **Claims:** I8 — *"the CODE has exactly one Plane-1 author, and a second one is REFUSED."*
- **Scope containment proven by:** calling the gate's own `_python_files(home)` and asserting
  membership: **367 files scanned**, `scripts/nixrisk/plane1_sink.py` and `scripts/nixrisk/wal.py`
  both present; the walk is `rglob` over the FILESYSTEM, so an untracked new writer is in scope.
- **Plant:** a new `scripts/nixrisk/_arc038e_plant.py` composing
  `INSERT INTO plane1_event_log … VALUES …` via `subprocess` against `nix_plane1`.
  → **verdict: RED**, `fail_needs_operator`, naming the site:
  `ARM B1: scripts/nixrisk/_arc038e_plant.py composes SQL against the Plane-1 log: 'INSERT INTO plane1_event_log (occurred_at, event_type, strategy_id, tr'`
- **Restore:** file unlinked; `git status --short` empty for it → **green again**, with the same
  evidence sentence and the same 367/15/43/5 counts.
- **AND IT CAUGHT MY OWN FIX — the strongest non-vacuity evidence in this report.** FE4's first
  repair hand-copied `decode_record`'s coercions into a fresh `EventRow(…)` inside
  `plane1_sink.py`. The full suite went RED on two of this gate's own can-fail tests:

  ```
  FAILED scripts/tests/test_check_plane1_sole_writer.py::test_control_the_UNMUTATED_tree_scans_clean
  FAILED scripts/tests/test_check_plane1_sole_writer.py::test_control_the_shipped_gate_PASSES_against_this_tree
  E  AssertionError: ARM B3: scripts/nixrisk/plane1_sink.py:319 constructs a Plane-1 EventRow with
     no syntactic route to .enqueue(…). Every row must originate from the Limiter's enqueue path (§9)
  = 2 failed, 3274 passed, 3 skipped, 2 xfailed in 2208.41s (0:36:48) =
  ```

  I did **not** add an exemption. The gate was right twice over: a second `EventRow` construction
  inside the sole writer's own module is the shape §12.10 forbids, and a hand-copied coercion is a
  SECOND source of truth for the canonical form that drifts the moment `decode_record` changes. The
  repair now PERFORMS the round trip — `encode_row(decode_record(encode_row(row)))` — so the key is
  the canonical form by construction rather than by agreement, and there is no new `EventRow(` node
  in the sink. Re-run: 53 passed, including both of the gate's controls.
- **The gap this audit found:** ARM A's privilege probe is `nix_limiter` (control) vs `nix_reader`
  (probe). Neither is the identity the tree runs as, and the gate contains no `current_user` /
  `session_user` / `usesuper` / `rolsuper` probe. FE1 and FE2 are both outside its scope while its
  evidence sentence reads as a sole-writership proof.

### check_plane1_schema
- **Claims:** append-only *"BY PRIVILEGE on the log parent and every partition, and BY ATTEMPT"*.
- **Scope containment proven by:** it really queries `has_table_privilege` per partition
  (`:350-360`) and really attempts `SET ROLE …; UPDATE/DELETE/TRUNCATE` — I confirmed the roles it
  names are `WRITER_ROLE`/`READER_ROLE` only.
- **Plant:** **not planted.** Its only reachable subject is the LIVE `nix_plane1`, and the plant
  required (`GRANT UPDATE ON plane1_event_log TO nix_limiter`) is a catalog change to the production
  money record. I declined; that is a CANNOT-MEASURE for the plant obligation, recorded rather than
  papered over. Its can-fail suite `test_check_plane1_schema.py` does drive planted scratch
  databases.
- **The gap this audit found:** the same as FE1 — the evidence sentence *"append-only proven"* is
  scoped to a role nothing runs as.

### check_plane1_event_coverage
- **Claims:** every §12.10 Plane-1 event type classified BY DRIVE, one at a time, with a PRODUCER
  column.
- **Scope containment proven by:** running it — 18 types, each driven through
  enqueue → WAL → group-commit → read-back. I checked the §7.12 hazard it claims to close (*"the
  producer census could be read out of the subject it polices"*) and it IS closed:
  `NOT_PRODUCERS = frozenset({"seam.py", "plane1_sink.py"})` excludes the mapping table, so the
  census is genuinely independent.
- **Plant:** `EventKind.HALT_CLEARED: "halt_cleared"` DELETED from `EVENT_KIND_TO_PLANE1`
  (sha256 `660281e6…` → `54e53256…`), `__pycache__` purged between plant and restore (ARC 017's
  seventh finding).
  → **verdict: RED**, `fail_needs_operator`, naming the site:
  `halt_cleared: the schema can record it, nixrisk.plane1_sink maps no EventKind to it, and it is not
  enumerated in UNROUTABLE_PLANE1_EVENTS. An event type in neither the mapping nor the declared gap
  is an unaudited hole in the money record` — and the per-type census printed
  `halt_cleared=UNCLASSIFIED` beside the seventeen unchanged verdicts.
- **Restore:** byte-identical, proven by sha256 back to `660281e6…` → **green again**, 18 types,
  `halt_cleared=DRIVEN`.
- **Verdict:** honest, NON-VACUOUS instrument that PASSES over a real hole by design. FE5 / D3.391.

### check_plane1_crash_gap
- **Claims:** §9's crash gap measured at a real durability boundary, and the instrument still
  discriminates.
- **Scope containment proven by:** reading its declarations — `SUBJECTS = ("scripts/plane1_crash_drill.py",)`,
  and all four arms consume the drill's result dict.
- **Plant:** not planted. **Non-vacuity FAILS for the subject I was sent to attack:** the gate never
  reads `wal_seq` continuity in any record, so it cannot see FE3's duplicates or holes. It is
  non-vacuous for its own declared subject and silent on mine.

### check_plane1_wal
- **Claims:** the fsync syscall, the torn tail, disk-critical, and §12.4's two failures.
- **Scope containment proven by:** running it — real `strace` observation
  (`fsync(3</tmp/nixwal-…/fsync.wal>) = 0`, control 0 lines), real SIGKILL reaped `-9`, real `EFBIG`.
- **Plant:** not planted; its own both-halves controls are in place and re-driving them is the
  duplicate instrument C.9 forbids.

### check_ledger_row_preservation
- **Claims:** no `CHECK-DEBT.md` row id ever disappears.
- **Scope containment proven by:** running it — 369 ids in the working file against a union of 369
  taken from 115 committed revisions across 354 commits reachable from HEAD, git env scrubbed
  (D3.205), with a planted deletion and a no-defect control driven in the same run.
- **Plant:** not planted separately — the gate plants its own, in the run, and prints both halves.
  **This is the model the other gates should follow**, and it is why I did not add a second one.

### check_realized_pnl
- **Claims:** the ARC 037 realized-P&L figure, written by the Limiter, read by the scorer.
- **Scope containment proven by:** running it — 4 realizing rows into a scratch Plane-1 database
  through `Plane1Wal → GroupCommitWriter → Plane1PostgresSink`, read back by SELECT, EMA advanced
  and compared against the closed form, green-while-open → closes-red driven, and 4 plants each
  required to trip the arm it guards.
- **Plant:** not planted. D3.345 is unchanged by this arc: its can-fails call arm functions directly
  and never produce a `CheckResult`, so it reads EXERCISED-NEVER-RED in the binding census while
  reddening on demand. I did not touch it — a can-fail that drives `run()` end to end is a real
  repair and it belongs to whoever owns D3.345, not to a Plane-1 audit passing through.

### check_allocator_caps
- **Claims:** §7:511's per-bucket correlation cap and §6.6:465's FCFS fallback.
- **Scope containment proven by:** running it — 7 arms, 5 symbols, 4 bucket ceilings, buckets parsed
  from the spec at run time with none spelled in the gate, and a `max()`-shaped falsifier required to
  DISAGREE. Genuinely strong.
- **Plant:** not planted. **Non-vacuity FAILS for my invariant:** `SUBJECTS` is
  `nixalloc/caps.py`, `nixalloc/contention.py`, `risks/allocator_caps.config.json`. `gate.py` is not
  in scope and neither cap rule is driven. FE6/FE7 were invisible to it by construction, not by
  defect.

### check_synthetic_stop_only
- **Claims:** §12.1 — no delegation to a broker-side stop.
- **Scope containment proven by:** running it — *"AST-scanned 2 file(s) [seam.py, stops.py] for 6
  broker import root(s), 3 order verb(s), 4 native stop order-type code(s); 0 delegations"*.
- **Plant:** driven here, in the REAL subject, not in a copy: `from broker import broker_seam` added
  to `scripts/nixrisk/stops.py` AND `_ARC038E_PLANT_ORDER_TYPE = "STP LMT"` (sha256 `936d0562…` →
  `896483ab…`), `__pycache__` purged between plant and restore.
  → **verdict: RED**, `fail_needs_operator`, `2 delegation(s)`, naming BOTH sites:
  `scripts/nixrisk/stops.py:101: imports broker module 'broker' onto the stop path;
  scripts/nixrisk/stops.py:155: string literal 'STP LMT' is a broker-native stop order-type code —
  the fingerprint of a broker-side stop`
- **Restore:** byte-identical, proven by sha256 back to `936d0562…` → **green again**, `0
  delegations`.
- **Verdict:** genuinely non-vacuous FOR ITS OWN SUBJECT, and that non-vacuity **does not extend to
  distance validity**: it is a delegation ban, not a correctness gate, so FE10 is outside it.

---

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL

| suite/control | plant used | reddened? | site named | restored green? |
|---|---|---|---|---|
| `test_arc038_e_plane1_record.py::test_the_UNPROTECTED_half_really_produces_TWO_KEYS_for_ONE_EVENT` | `_pre_fix_natural_key` — the pre-fix expression byte for byte — required to split ONE event into TWO identities for every coercion `decode_record` applies | n/a (this IS the unprotected half; it FAILS if the defect is absent) | each coercion labelled | yes |
| `…::test_the_natural_key_is_CANONICAL_across_the_WAL_ROUND_TRIP` | same, as the negative control | yes — asserted to differ before the fix | the coercion label | yes |
| `…::test_a_REPLAY_of_an_UNCOERCED_row_is_DEDUPLICATED_by_the_REAL_sink` | `monkeypatch` the sink's `natural_key_for` to the pre-fix expression; require `count(*) = 2` for one `occurred_at` in real Postgres | yes — the duplicate row is REQUIRED to appear | `plane1_event_log`, by `occurred_at` | yes — `monkeypatch.undo()`, then `rows_deduplicated == 1` and `count(*) = 1` |
| `…::test_the_canonicalisation_moves_NO_key_the_annotations_ALLOW` | asserts byte equality with the pre-fix key on conforming rows | would redden on any key movement | the kind and `trade_id` | yes |
| `…::test_the_APPEND_ONLY_refusal_is_caused_by_the_ROLE_and_by_NOTHING_ELSE` | both halves: the mutations WITHOUT a role must be ACCEPTED (the control), then under `SET LOCAL ROLE nix_limiter` must be refused with 42501 AND `permission denied for table plane1_event_log` | yes — drop the `SET LOCAL ROLE` and the protected half fails | the verb and the table | yes |
| `…::test_the_sink_NEVER_composes_a_write_without_assuming_the_ROLE` | intercepts the composed statement; asserts `SET LOCAL ROLE` precedes the INSERT and that no bare `SET ROLE` survives COMMIT | yes | the statement prefix | yes |
| `…::test_the_CRASH_GAP_is_ONE_SIDED_and_EXACTLY_ONCE_survives_a_REAL_SIGKILL` | asserts `WIFSIGNALED`/9 (never a return code), a strictly POSITIVE gap before judging one-sidedness, and zero duplicated natural keys after the heal | yes — an empty gap or a surviving forbidden-direction key fails it | the offending natural keys | yes |
| `test_arc038_e_limiter_cap.py` — all arms | see that file's table; every arm runs the UNPROTECTED half (the guard neutralised) and REQUIRES the fail-open outcome to reappear before requiring it gone | yes | the rule name and the §15 clause | yes |

Two self-deceptions ruled out by construction, as the contract requires:
1. **D3.344, the inherited-`PYTHONPATH` staged-tree defeat.** Every subprocess in this audit was
   launched with an explicit `env=` built by FILTERING `/home/bbt/nix/scripts` out of `PYTHONPATH`
   and prepending this worktree's `scripts/` — never by replacing `PYTHONPATH` wholesale, so the
   binding census's `sitecustomize` entry survives. Every impostor child PRINTED the `__file__` it
   imported from, and all of them are under `/home/bbt/nix-wt-arc-038-e/`.
2. **ARC 035's self-masking controls.** Every control above runs the unprotected half FIRST and
   requires the bad outcome to APPEAR.

---

## WHAT I COULD NOT MEASURE, AND WHY

1. **Whether `check_plane1_schema` reddens under a planted grant.** Its only reachable subject is the
   live `nix_plane1`, and the plant is `GRANT UPDATE ON plane1_event_log TO nix_limiter` — a catalog
   change to the production money record. Declined. CANNOT-MEASURE, stated, not a pass.
2. **The `wal_seq` race under a real multi-process Limiter.** I proved two `Plane1PostgresSink`
   instances collide; whether production would ever run two is unknowable because **no daemon
   constructs one** (`plane1_sink.py:96-98` says so itself). The collision is a property of the
   numbering, not a prediction about deployment.
3. **fsync / power loss.** Out of scope by design; `check_plane1_wal` owns it and I did not re-drive
   it (C.9). A `SIGKILL` measures the crash gap and nothing about the platter.
4. **Whether §9's *"crash gap healed by startup reconciliation vs broker truth"* works.** It does not
   exist — `wal.py:62-71` records that. I measured what a restart RE-PRESENTS, not what a
   reconciliation would resolve.
5. **The cap fed by a real fill, end to end.** Not measurable: `gate.py` reads no distance (FE6) and
   nothing in production constructs `StopBook`, `FillHandler`, `PositionOriginWriter` or any
   `NetLiqMarkPort` implementation (D3.393). I drove every link that exists, separately, and said so.
6. **`EventKind.BOOT`'s absence from the schema.** Confirmed it RAISES `UnmappableEvent` rather than
   being laundered, which is the designed behaviour; I did not attempt to argue the routing decision.

---

## FILES I CHANGED

| path | why | finding |
|---|---|---|
| `scripts/nixrisk/plane1_sink.py` | `natural_key_for` now PERFORMS the WAL round trip (`encode_row(decode_record(encode_row(row)))`) before hashing, so one event has one identity on both sides of the disk. Identity on every conforming value — asserted. Second iteration: the first hand-copied the coercions and `check_plane1_sole_writer` ARM B3 caught it | FE4 |
| `scripts/nixrisk/gate.py` | `_unpriceable_margin` guard on both cap rules (§15 C3); `SurvivalHeadroomRule` denies a non-finite mark (§15 C2 / §17) and refuses a non-finite pad at construction | FE7, FE8, FE9 |
| `scripts/risk_config.py` | `_positive_scalars` refuses a non-finite scalar — `NaN` passes every ordering comparison, which is why finiteness has to be explicit | FE9 |
| `scripts/tests/test_arc038_e_plane1_record.py` | new — the I8 controls and their can-fail proofs | FE4, FE1 |
| `scripts/tests/test_arc038_e_limiter_cap.py` | new — the I12 controls and their can-fail proofs | FE7, FE8, FE9 |
| `downloads/arc038_findings_E.md`, `downloads/arc038_debt_E.md` | the deliverables | — |

## COMMITS

See `git log --oneline arc-038-e` — listed in the final summary.
