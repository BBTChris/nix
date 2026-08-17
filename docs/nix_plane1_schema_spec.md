# Nix — Plane-1 schema specification (v1.0.0, FROZEN ARC 035 / Phase 0.4)

**Derived spec.** Subordinate to `nics_risk_subsystem_spec_v1.3.md` §9 and §12.10, which are frozen and
are the authority. This file may narrow or operationalize them; it may never contradict them. Where
this file and the risk spec appear to disagree, the risk spec wins and this file is the defect.

**Implementation:** `databases/schema/plane1.sql`. **Gate:** `checks/check_plane1_schema.py`
(can-fail suite `scripts/tests/test_check_plane1_schema.py`).
**Canonical path:** `/home/bbt/nix` (absolute).

---

## 0. The two boundaries, stated first because they are the ones that get blurred

### 0.1 Plane 1 is NOT the analytics database

`nix_db_schema_spec.docx` / `databases/schema/trade_history.sql` define the **backtest / paper / live
trade-history store**: one row per *round trip*, rows that **mutate** as exits land (`updated_at`
maintained by trigger), backtest leaves deliberately `UNLOGGED` because they are regenerable by
design. That store exists to be *queried for evaluation*.

Plane 1 is the opposite object on every one of those axes:

| | analytics (`trade_history`) | Plane 1 (`nix_plane1`) |
|---|---|---|
| grain | one row per round trip | one row per **transition** |
| mutability | rows update as exits land | **never** — no writer holds UPDATE |
| regenerable | backtest leaves, by design | **no** — it *is* the record |
| written by | three engine roles, per branch | **the Limiter, alone** |
| read by | evaluation, Crucible, dashboards | reconciliation, projection rebuild, dashboards |

They are **separate databases on the same cluster**, and that separation is load-bearing rather than
tidy: a privilege model is only as strong as the smallest grant in the database it lives in, and the
analytics store's writer roles legitimately hold `UPDATE`. Putting both in one database would put a
role that can update rows in the same catalog as a table whose entire safety property is that no role
can.

### 0.2 The migration seam — DECLARED, not assumed

A **closed live trade** eventually appears in `trade_history.trades_live_<symbol>`. That is a **READ**
of Plane 1 and a **WRITE** to the analytics store, performed by an analytics-side job.

- It is **not a Plane-1 writer.** It never inserts into `plane1_event_log`.
- It **does not exist yet.** No arc has built it and this arc does not.
- What this schema guarantees is only that the read side is *possible*: a closed trade's full
  transition history is recoverable by `trade_id` from `plane1_event_log`, indexed for it.

Anything more than that is future work and is not claimed here.

### 0.3 Sole writer — §12.10, verbatim: *"Limiter sole writer. No new writers, ever."*

Every Plane-1 row originates from the Limiter's `enqueue → durable local WAL → shared-pool writer →
group-commit` path (`scripts/nixrisk/wal.py`). **The shared-pool writer is a conduit, not a second
author** — it holds no independent authority to originate a row, and its identity to Postgres is the
Limiter's role.

The enforcement is a **grant**, not a convention: `nix_limiter` holds `SELECT, INSERT` on the log;
`nix_reader` holds `SELECT`. Nothing else holds anything. A test, tool, dashboard or migration that
inserts a Plane-1 row from any other identity is refused by the database, which is the point.

---

## 1. Append-only enforced by PRIVILEGE, not by trigger

This is the single most important decision in the file, and it is a deliberate departure from the
analytics store's use of triggers.

A `BEFORE UPDATE ... RAISE EXCEPTION` trigger is:

- **dropped** by the table's owner in one statement;
- **disabled** by `ALTER TABLE ... DISABLE TRIGGER`;
- **skipped wholesale** when `session_replication_role = 'replica'`;
- **never fired at all** by `TRUNCATE`.

A missing `GRANT` has none of those bypasses. The executor checks it on every statement, and the only
way past it is to re-issue the grant — which is a catalog change a gate can see and name.

So the rule is: **the writer role is granted `SELECT` and `INSERT` on the log and nothing else, ever,
and there is no trigger on the log.** `check_plane1_schema` ARM 5 treats the *presence* of a trigger
on the log as a defect, even though a trigger only ever adds a restriction — because a trigger there
would make the weaker mechanism look like the guarantee to whoever reads the DDL next.

**Grants are per relation, not per hierarchy.** PostgreSQL checks privileges against the table a
statement *names*. `UPDATE plane1_event_log SET ...` is checked against the parent;
`UPDATE plane1_event_log_2026_08 SET ...` is checked against the **child**. A grant audit that
inspected only the partitioned parent would call a database append-only while one partition was wide
open. Every partition is therefore granted explicitly and checked explicitly.

**The asymmetry is the design.** The Limiter holds `UPDATE`/`DELETE`/`TRUNCATE` on the *projection*,
because §9 calls the positions table rebuildable and a rebuild is a delete and a re-fold. A schema
that withheld those would be beautifully append-only and impossible to reconcile.

---

## 2. Objects

### 2.1 `plane1_event_enum` — the §12.10 inventory as a type

Exactly the rows of §12.10's table carrying a Plane-1 tick, and nothing else. **18 members:**

`signal` · `accepted` · `denied` · `filled` · `exit_intent` · `closed` · `protective_exit` ·
`reservation_taken` · `reservation_released` · `cancel` · `go_timeout` · `drift_audit` ·
`sentinel_flatten` · `halt_set` · `halt_cleared` · `operator_action` · `strategy_lifecycle` ·
`cold_start_outcome`

Plane-2-only events — crash-loop counts, heartbeat loss/orphan detect, blackout open/close,
contract-roll seam, feed-staleness transitions, broker session lost/restored, monotonic-guard
discards, alerts, systemd process start/stop — are **deliberately absent**. §12.10 makes Plane 2
diagnostic-only and explicitly *never a reconciliation input*.

The gate compares type against inventory in **both directions**. A member missing from the type is an
event that *cannot be recorded*. A member present in the type and absent from §12.10 is an *unaudited
money event someone can write*. A one-directional comparison would accept the second forever, and the
second is the likelier drift — adding an enum member is a one-line convenience.

### 2.2 `plane1_event_log` — the record

Partitioned `BY RANGE (occurred_at)`, monthly, **plus a `DEFAULT` catch-all**. The catch-all is not
tidiness: a row whose `occurred_at` falls outside every declared range would otherwise be *rejected*,
and losing a Plane-1 row to a missing partition is the worst failure this schema can have. A row that
lands in `DEFAULT` is not lost — it is *evidence that partition onboarding was skipped*.

`event_id` comes from an **explicit `SEQUENCE`**, not `GENERATED ... AS IDENTITY`. The analytics store
learned this: an identity column on a partitioned table is a property of the parent that partitions do
not inherit usefully, and the grant that lets a non-owner writer call `nextval()` has to name the
sequence. Naming the sequence is what makes the grant nameable.

**Two timestamps, because they answer different questions:**

- `occurred_at` — when the transition happened. Stamped by the Limiter at *enqueue*, carried through
  the WAL. This is trade time and it is the partition key.
- `recorded_at` — when the row landed in Postgres at group-commit.

`recorded_at - occurred_at` **is** the commit lag. After a crash, the widest gap in `occurred_at` with
no rows either side is **the crash gap** that cold-start reconciliation must heal against broker
truth. Conflating the two into one column is how a crash gap becomes invisible.

**§9's per-row requirement is structural.** *"Timestamp + strategy_id + trade_id + reason on every
row"* — all four are `NOT NULL`, with `CHECK`s forbidding the empty string. Events with genuinely no
trade (an operator HALT, a strategy registration) carry the documented sentinel `'-'` rather than
`NULL`: *"this event has no trade"* and *"this row's trade was lost"* are different facts and a `NULL`
would spell them the same way.

**Ordering and idempotency:**

- `wal_seq` — the local WAL record number. **The WAL is the only place ordering is authoritative.**
  Postgres commit order under group-commit is *batch* order, and `event_id` is assigned at INSERT and
  not at enqueue, so neither is a safe ordering key.
- `natural_key` — the event's identity for exactly-once replay, with
  `UNIQUE (natural_key, occurred_at)`. A unique index on a partitioned table must contain the
  partition key, and that is the right grain anyway: a re-delivered buffered record carries its own
  original `occurred_at` out of the WAL, so a duplicate collides; two genuinely different events
  sharing a natural key at different instants are, by construction, not the same event.

### 2.3 `plane1_positions` — the PROJECTION

§9: *"Positions table = projection (rebuildable; dashboard + reconciliation read it)."* Derived state,
a fold over the log. `last_event_id` is the fold's watermark — a projection that cannot say where it
is in the log is a projection nobody can reconcile against.

### 2.4 `plane1_projection_meta` — the watermark, singleton by constraint

One row, enforced by `PRIMARY KEY (id) CHECK (id = 1)`. "There is one row" written in a comment is a
claim; written as a constraint it is a fact.

---

## 3. What this file does NOT decide

- **The wiring.** That the Limiter *actually writes* through this schema, and that no other production
  path does, is a property of code, not of a catalog. It belongs to the sole-writer gate and to
  §12.10's own inventory drive, not here.
- **Retention.** Nothing in §9 or §12.10 authorises deleting a Plane-1 row, and no retention or
  archival policy is defined. Detaching an old partition would require `TRUNCATE`/`DROP` rights nobody
  currently holds, which is the correct default: a retention policy should be an explicit ruling, not
  a side effect of a grant.
- **Backup/DR.** `elements_v2.md` §4 (pg_dump rotation, Backblaze B2, monthly restore dry-run) is a
  later peripherals arc. A Plane-1 database with no proven-restorable backup is a durable record that
  survives a process crash and not a disk. **Stated, not solved.**
- **The analytics migration job** (§0.2).

## 4. Version note — the cluster is PostgreSQL 18.4, not 16

`nix_db_schema_spec.docx` v1.3.0 records itself as *validated live against Postgres 16*. The cluster on
this node is **PostgreSQL 18.4** (`psql (PostgreSQL) 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1)`), measured
ARC 035 / Phase 0.4. This file and `plane1.sql` are validated against **18.4**, which is what is
actually installed.

The analytics spec's own "16" is **not** corrected here — it is a frozen external document describing a
different store, and restating its version in a third file is the drift directive 3 forbids. What is
recorded is the measurement: the running cluster is 18.4, and any claim in any document that Nix runs
on 16 is stale as of this date.
