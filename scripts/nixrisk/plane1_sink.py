"""§9's Postgres end of the Plane-1 write path: the group-commit sink.

ARC 035 / Stage 1 / sub-agent A. Authority:
`docs/nics_risk_subsystem_spec_v1.3.md` §9 (*Persistence Model, event-sourced*:
**Limiter = sole writer.** *Enqueue → durable local WAL → shared-pool writer →
group-commit to Postgres*), §11 item 6 (event-log writes off the hot path,
WAL-buffered, batched), §12.4 (*degraded persistence ≠ degraded trading*),
§12.10 (Plane 1, **no new writers, ever**). Substrate:
`databases/schema/plane1.sql`, frozen in Phase 0.4 of this arc.

`scripts/nixrisk/wal.py` built everything on the near side of the boundary —
`Plane1Wal`, `GroupCommitWriter`, `CommitSinkPort` — and said so in its own
docstring: *"the only implementations in this tree are the in-memory
`RecordingSink` and the test doubles."* This module is the real one.

---

## WHY `psql`, AND NOT A DRIVER

There is no Python PostgreSQL driver in the venv and `nix_check_contract.md`
§9.1 keeps checks stdlib-only; `.venv` mutation is behind
`scripts/nixverify/venv_lock.py`. So the transport is `psql` as a subprocess,
the same instrument `checks/check_plane1_schema.py` uses. That is a real cost
and it is stated rather than hidden: one process per group-commit, not one per
row, which is exactly the batching §11 item 6 asks for and is why the cost is
bearable. A driver, when one is admitted to the venv under the lock, replaces
`_run_psql` and nothing else — every mapping decision below is transport-blind.

## ONE TRANSACTION PER BATCH, AND IT IS ALL-OR-NOTHING

`commit()` emits ONE `psql -c` string: `BEGIN; SET LOCAL ROLE …; INSERT …
VALUES (…),(…),(…) …; COMMIT;`. A batch that violates any CHECK constraint
lands **zero** rows, which is the property `test_plane1_sink.py` drives with a
deliberately malformed row in the MIDDLE of a batch. A per-row INSERT loop
would leave a half-written group behind after a failure and make the crash gap
two-sided; §9's ordering only works because the group is atomic.

`SET LOCAL ROLE` rather than `SET ROLE`: the role reverts at `COMMIT`, so a
pooled connection cannot inherit the Limiter's identity from a previous batch.

## THE NATURAL KEY IS A CONTENT HASH, AND THAT IS THE WHOLE OF EXACTLY-ONCE

`plane1_event_log` carries `UNIQUE (natural_key, occurred_at)`. §12.4's
reconnect heal re-presents buffered WAL records after an outage, so the key has
to be identical for a re-delivery and different for a genuinely different
event. It is therefore derived from the record's own canonical bytes —
`encode_row`'s JSON body, SHA-256 — and NOT from `wal_seq`, which is the
tempting choice and the wrong one: after a restart the sequence is re-derived
from the database, so the same logical record can carry a different `wal_seq`
on replay and a seq-keyed dedup would let it in twice.

Two rows that hash the same are identical in kind, timestamp, strategy, trade,
reason AND fields. Nothing distinguishes them, so they are the same event; that
is a claim about the schema's own grain and it is stated here so the next
author can argue with it rather than discover it.

`ON CONFLICT (natural_key, occurred_at) DO NOTHING` makes the re-delivery a
no-op instead of an error, and `RETURNING event_id` makes the sink's return
value the number of rows that actually LANDED — so a caller can tell a
deduplicated flush from a fresh one.

## THE TWO VOCABULARIES ARE NOT THE SAME SET — A MEASURED FINDING

`EventKind` (`scripts/nixrisk/seam.py`, FROZEN) and `plane1_event_enum`
(`databases/schema/plane1.sql`, FROZEN) do not agree, in both directions:

* **Five §12.10 event types have no `EventKind` member at all** — `filled`,
  `go_timeout`, `drift_audit`, `sentinel_flatten`, `operator_action`. The
  Limiter cannot enqueue them, so nothing in this tree can record them. That is
  the seam's own stated rule (*"a member lands here ONLY when the machinery
  that emits it exists"*) meeting a schema transcribed from the spec's full
  inventory, and it is a real gap, not a defect in either file.
* **Several `EventKind` members share one §12.10 row.** `FORCE_DEREGISTER`,
  `KILL`, `RELAUNCH` and `QUARANTINE` are the four verbs of §12.10:757's single
  *strategy lifecycle* row. The mapping folds them onto `strategy_lifecycle`
  and the ORIGINAL kind is preserved in `payload->>'event_kind'`, so nothing is
  lost: a reader can recover the verb, and a reader filtering by event_type
  still sees every lifecycle transition.
* **`EventKind.BOOT` has no §12.10 home.** It is not in the inventory and it is
  emitted by nothing in `scripts/nixrisk/` (only named in a `risk_config.py`
  docstring and a test). It is therefore listed in `UNMAPPED_EVENT_KINDS` and
  the sink **RAISES** on it rather than laundering it into a neighbouring enum
  value. Fail closed and loud: a row filed under the wrong event type is worse
  than a row refused, because the refusal is visible and the misfile is not.

`EVENT_KIND_TO_PLANE1` is TOTAL over `EventKind` — every member is either
mapped or explicitly unmapped — and `test_plane1_sink.py` asserts that, so a
member added to the frozen seam by a later arc reddens here instead of being
silently dropped on the floor.

## WHAT THIS MODULE DOES NOT DO

It does not fold the projection (sub-agent B), it does not implement §12.4's
degradation policy (sub-agent C — it merely RAISES, which is what
`GroupCommitWriter` turns into `SINK_DEGRADED`), and it does not audit drift
(sub-agent D). It has **no production constructor yet**: no daemon in this tree
builds one, because there is no daemon. That is recorded rather than papered
over.

**It also proves nothing about the local WAL's durability.** A Postgres
`COMMIT` under `synchronous_commit = on` is a real durability boundary for
POSTGRES; `os.fsync` on the WAL's own descriptor is the boundary for the WAL,
and `checks/check_plane1_wal.py` owns that with a syscall observation and a
both-halves control. Two boundaries, two instruments; neither green covers the
other.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import hashlib
import json
import re
import shutil
import subprocess  # nosec B404 - psql IS the transport; §9.1 forbids new deps
from collections.abc import Sequence
from typing import Final

from nixrisk.seam import EventKind, EventRow
from nixrisk.wal import encode_row

#: The live Plane-1 database. The same literal `check_plane1_schema.PLANE1_DB`
#: carries; `test_plane1_sink.py` asserts the two agree, because a sink pointed
#: at a different database from the one the gate inspects would make both green
#: and neither true.
PLANE1_DB: Final[str] = "nix_plane1"

#: §12.10's sole writer. Not a default that can be quietly overridden in
#: production: it is overridable so the CAN-FAIL can drive the sink under a
#: non-Limiter identity and observe the refusal, which is the only way to prove
#: the privilege actually bites.
LIMITER_ROLE: Final[str] = "nix_limiter"

LOG_TABLE: Final[str] = "plane1_event_log"

#: The schema's documented "absent" sentinel. NOT NULL columns with a sentinel
#: rather than NULLs, so "absent" and "lost" cannot be confused.
ABSENT: Final[str] = "-"

#: `insufficient_privilege` — the only SQLSTATE that is evidence about grants.
SQLSTATE_INSUFFICIENT_PRIVILEGE: Final[str] = "42501"

#: An unquoted PostgreSQL identifier. `role` reaches SQL as a bare identifier in
#: `SET LOCAL ROLE …` — there is no parameter form for that statement — so it is
#: VALIDATED at construction rather than trusted. The parameter exists so the
#: sole-writer gate can drive this class as `nix_reader` and observe the
#: refusal; that is a fixed vocabulary of role names, and anything outside this
#: shape is refused before a statement is composed.
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

# EVERY `# nosec B608` IN THIS FILE, ARGUED ONCE HERE RATHER THAN THREE TIMES.
# Bandit flags f-string SQL as a possible injection vector, which is the right
# default. Two of the three interpolations are the MODULE-LEVEL CONSTANT
# `LOG_TABLE`; the third is `self.role`, checked against `_IDENTIFIER` in
# `__init__` and refused there if it is not a bare lower-case identifier. Every
# VALUE — timestamps, strategy ids, trade ids, reasons, symbols, payloads —
# goes through `_sql_str`, which doubles quotes under
# `standard_conforming_strings`; `test_plane1_sink.py` drives that with a reason
# containing `'; DROP TABLE plane1_event_log; --` and reads the row back
# byte-identical with the table still present.


class SinkError(RuntimeError):
    """A group-commit attempt failed. Always carries what psql said.

    Raised rather than swallowed: `GroupCommitWriter.drain_once` catches it and
    turns it into §12.4's `SINK_DEGRADED` — rows buffer in the WAL and trading
    continues. A sink that returned 0 on failure would be indistinguishable
    from an empty batch and the degradation would never be entered.
    """

    def __init__(self, message: str, *, sqlstate: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.stderr = stderr


class UnmappableEvent(SinkError):
    """An `EventKind` with no §12.10 Plane-1 home. Refused, never laundered."""


#: `EventKind` -> `plane1_event_enum`. TOTAL over `EventKind` when read together
#: with `UNMAPPED_EVENT_KINDS`; the pair is asserted exhaustive by the tests.
EVENT_KIND_TO_PLANE1: Final[dict[EventKind, str]] = {
    EventKind.SIGNAL: "signal",
    EventKind.ACCEPTED: "accepted",
    EventKind.DENIED: "denied",
    EventKind.RESERVATION_TAKEN: "reservation_taken",
    EventKind.RESERVATION_RELEASED: "reservation_released",
    EventKind.PROTECTIVE_EXIT: "protective_exit",
    EventKind.EXIT_INTENT: "exit_intent",
    EventKind.CLOSED: "closed",
    EventKind.CANCEL: "cancel",
    EventKind.COLD_START: "cold_start_outcome",
    EventKind.HALT_SET: "halt_set",
    EventKind.HALT_CLEARED: "halt_cleared",
    # §12.10:757's ONE strategy-lifecycle row, four verbs. The verb survives in
    # payload->>'event_kind'; folding them is the spec's own grouping, not a
    # convenience.
    EventKind.FORCE_DEREGISTER: "strategy_lifecycle",
    EventKind.KILL: "strategy_lifecycle",
    EventKind.RELAUNCH: "strategy_lifecycle",
    EventKind.QUARANTINE: "strategy_lifecycle",
    # ARC 035 STAGE 2 INTEGRATION — THE CROSS-BRANCH DEFECT, and it is the
    # cleanest example this arc produced of why an integration stage exists.
    #
    # Sub-agent D added `EventKind.DRIFT_AUDIT` to the FROZEN seam in a parallel
    # worktree, because §11.7's audit event is one of the six §12.10 rows ticked
    # in BOTH planes and the seam carried no member for it. Sub-agent A wrote
    # this map in a different worktree against a seam that did not have it yet.
    # Both branches were internally consistent and both were green; on the
    # merged tree `test_the_mapping_is_TOTAL_over_the_frozen_EventKind` went red
    # naming exactly one member.
    #
    # The totality test is the only reason this was visible. Without it the
    # sink would have raised `EventKind.DRIFT_AUDIT is in neither ...` at
    # group-commit time — in production, on the one event whose entire purpose
    # is to report that the books disagree.
    #
    # `plane1_event_enum` already carried `drift_audit` from the Phase-0.4
    # freeze, so the schema needed nothing; the gap was seam-side only, exactly
    # as sub-agent D recorded it.
    EventKind.DRIFT_AUDIT: "drift_audit",
}

#: Kinds the frozen seam can produce that §12.10 does not list, with the reason.
#: The sink REFUSES them. See the module docstring.
UNMAPPED_EVENT_KINDS: Final[dict[EventKind, str]] = {
    EventKind.BOOT: (
        "§12.10's Plane-1 inventory has no 'boot' row and plane1_event_enum has "
        "no member for it. Nothing in scripts/nixrisk/ emits it (it is named "
        "only in a scripts/risk_config.py docstring and a test). Filing it under "
        "cold_start_outcome would put a row §12.10 never authorised into the "
        "money record under a neighbouring type, which is worse than refusing "
        "it: the refusal is visible and the misfile is not"
    ),
}

#: §12.10 event types with NO `EventKind` member — the Limiter cannot enqueue
#: them, so nothing in this tree can record them. Derived from the two frozen
#: files and stated here once, with the reason each is still absent, so the
#: coverage gate can report it PER TYPE rather than generalising one drive.
#: ARC 035 STAGE 2: `drift_audit` LEFT this map, and its own entry said why it
#: would. Sub-agent A wrote *"the audit itself is ARC 035 sub-agent D's mandate;
#: no EventKind member exists for it yet"* — and sub-agent D, in a worktree A
#: could not see, built the audit AND the seam member in the same commit. The
#: census went 5 -> 4 because a declared gap was closed by a sibling branch,
#: which is the one direction this map is supposed to move.
UNROUTABLE_PLANE1_EVENTS: Final[dict[str, str]] = {
    "filled": (
        "entry-fill confirmation. seam.py's EventKind docstring names it as "
        "STILL OMITTED for want of emitting code; scripts/nixrisk/fills.py "
        "handles fills but routes no Plane-1 row"
    ),
    "go_timeout": (
        "the §12.10 order-path terminal. seam.py names it STILL OMITTED; "
        "TerminalPath carries the concept, EventKind does not"
    ),
    "sentinel_flatten": (
        "§12.1, booked via marker replay at cold start. nixrisk/flatten.py "
        "emits PROTECTIVE_EXIT with the trigger in FIELDS, so the transition IS "
        "recorded — under protective_exit, not under its own §12.10 type"
    ),
    "operator_action": (
        "§12.11's authenticated verbs. seam.py names operator-control actions as "
        "STILL OMITTED; the authenticated transport does not exist"
    ),
}


def resolve_event_type(kind: EventKind) -> str:
    """`EventKind` -> the `plane1_event_enum` label. Raises on an unmapped kind."""
    mapped = EVENT_KIND_TO_PLANE1.get(kind)
    if mapped is not None:
        return mapped
    reason = UNMAPPED_EVENT_KINDS.get(kind)
    if reason is not None:
        raise UnmappableEvent(
            f"EventKind.{kind.name} has no §12.10 Plane-1 row: {reason}"
        )
    raise UnmappableEvent(
        f"EventKind.{kind.name} is in neither EVENT_KIND_TO_PLANE1 nor "
        f"UNMAPPED_EVENT_KINDS. A member was added to the FROZEN seam without a "
        f"§12.10 routing decision; the sink refuses rather than guess which "
        f"money event this is"
    )


def natural_key_for(row: EventRow) -> str:
    """The event's identity for exactly-once replay. Content-derived, not seq.

    `encode_row` already produces the WAL's canonical, sorted-key JSON framing,
    so this hashes exactly the bytes that went to disk — a re-delivery of the
    same WAL record cannot produce a different key, and a different event cannot
    produce the same one without being identical in every field.
    """
    body = encode_row(row).split(b" ", 1)[1].rstrip(b"\n")
    digest = hashlib.sha256(body).hexdigest()
    return f"{row.kind.value}:{digest[:40]}"


def _sql_str(value: str) -> str:
    """One SQL string literal. Doubling is the whole escape under
    `standard_conforming_strings` (on by default since 9.1), which makes a
    backslash an ordinary character rather than an escape introducer."""
    return "'" + value.replace("'", "''") + "'"


def _run_psql(
    database: str, sql: str, *, timeout: float = 60.0
) -> subprocess.CompletedProcess[str]:
    """One psql invocation. VERBOSITY=verbose so the SQLSTATE reaches stderr.

    Without it psql prints the message only, and a message is prose while a
    SQLSTATE is a contract (check-contract rule 11).
    """
    binary = shutil.which("psql")
    if binary is None:
        raise SinkError("psql is not on PATH — the Plane-1 transport is absent")
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        [
            binary,
            "-d",
            database,
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=verbose",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _sqlstate(stderr: str) -> str:
    """psql's SQLSTATE under VERBOSITY=verbose: `ERROR:  42501: permission ...`."""
    for line in stderr.splitlines():
        head, _, rest = line.partition(":")
        if head.strip() in {"ERROR", "FATAL", "PANIC"}:
            code = rest.strip().split(":", 1)[0].strip()
            if len(code) == 5 and code[0].isdigit() and code.isalnum():
                return code.upper()
    return ""


def max_wal_seq(database: str) -> int:
    """The highest `wal_seq` already banked, or -1 for an empty log.

    This is how a restarted writer resumes numbering without a persisted
    cursor. It is a READ of the record rather than a second source of truth,
    which is the only version of "resume" that cannot disagree with the log.
    """
    proc = _run_psql(
        database,
        f"SELECT coalesce(max(wal_seq), -1) FROM {LOG_TABLE}",  # nosec B608
    )
    if proc.returncode != 0:
        raise SinkError(
            f"cannot read max(wal_seq) from {database}.{LOG_TABLE}: "
            f"{proc.stderr.strip()[-300:]}",
            sqlstate=_sqlstate(proc.stderr),
            stderr=proc.stderr,
        )
    return int(proc.stdout.strip() or "-1")


class Plane1PostgresSink:  # pylint: disable=too-many-instance-attributes
    # Eight attributes, of which FOUR are counters (`groups`, `rows_seen`,
    # `rows_landed`, `rows_deduplicated`). A sink that cannot say how many
    # rows it deduplicated cannot tell a reconnect flush from a fresh one,
    # which is the §12.4 property C is built on.
    """§9's shared-pool half against real Postgres. A `CommitSinkPort`.

    Constructed with a database and a ROLE. The role is `nix_limiter` by
    default and is a parameter for exactly one reason: the sole-writer gate
    drives this same class under a non-Limiter identity and requires the INSERT
    to be refused with SQLSTATE 42501 naming the TABLE. A refusal that cannot be
    produced cannot be measured, and "the code only ever passes nix_limiter" is
    the vacuous version of the sole-writer claim — the version §12.10 does not
    accept.

    `wal_seq` numbering resumes from `max(wal_seq)` in the target database on
    first use. Stated limitation, inherited from `GroupCommitWriter`'s in-memory
    cursor: a WAL tail Postgres never saw is re-numbered on replay. The natural
    key is content-derived precisely so that re-numbering cannot duplicate a row.
    """

    def __init__(
        self,
        database: str = PLANE1_DB,
        *,
        role: str = LIMITER_ROLE,
        timeout_s: float = 60.0,
    ) -> None:
        if not _IDENTIFIER.match(role):
            raise SinkError(
                f"role {role!r} is not a bare PostgreSQL identifier. `SET LOCAL "
                f"ROLE` takes no parameter, so the role reaches SQL as text and "
                f"is refused here rather than composed"
            )
        if not _IDENTIFIER.match(database):
            raise SinkError(f"database {database!r} is not a bare identifier")
        self.database = database
        self.role = role
        self.timeout_s = timeout_s
        self._next_seq: int | None = None
        self.groups = 0
        self.rows_seen = 0
        self.rows_landed = 0
        self.rows_deduplicated = 0

    def next_wal_seq(self) -> int:
        """The seq the next row will carry. Resolved from the log on first ask."""
        if self._next_seq is None:
            self._next_seq = max_wal_seq(self.database) + 1
        return self._next_seq

    def _values_clause(self, rows: Sequence[EventRow], first_seq: int) -> str:
        tuples: list[str] = []
        for offset, row in enumerate(rows):
            event_type = resolve_event_type(row.kind)
            fields = dict(row.fields)
            payload = json.dumps(
                {**fields, "event_kind": row.kind.value}, sort_keys=True
            )
            symbol = fields.get("symbol")
            tuples.append(
                "("
                + ", ".join(
                    (
                        f"to_timestamp({float(row.ts)!r})",
                        f"{_sql_str(event_type)}::plane1_event_enum",
                        _sql_str(row.strategy_id or ABSENT),
                        _sql_str(row.trade_id or ABSENT),
                        _sql_str(row.reason),
                        "NULL" if symbol is None else _sql_str(symbol),
                        str(first_seq + offset),
                        _sql_str(natural_key_for(row)),
                        f"{_sql_str(payload)}::jsonb",
                    )
                )
                + ")"
            )
        return ", ".join(tuples)

    def commit(self, rows: Sequence[EventRow]) -> int:
        """Persist a GROUP in ONE transaction. Returns rows that LANDED.

        A re-delivered row is refused by the unique index and silently skipped
        (`ON CONFLICT DO NOTHING`), so the return value is below `len(rows)` on
        a duplicate flush and `rows_deduplicated` names how many. Raises
        `SinkError` on any failure — §12.4's degradation is the CALLER's policy,
        not this object's.
        """
        if not rows:
            return 0
        first_seq = self.next_wal_seq()
        statement = (
            "BEGIN; "
            f"SET LOCAL ROLE {self.role}; "  # nosec B608
            f"INSERT INTO {LOG_TABLE} "  # nosec B608
            "(occurred_at, event_type, strategy_id, trade_id, reason, symbol, "
            " wal_seq, natural_key, payload) VALUES "
            f"{self._values_clause(rows, first_seq)} "  # nosec B608
            "ON CONFLICT (natural_key, occurred_at) DO NOTHING "
            "RETURNING event_id; "
            "COMMIT;"
        )
        proc = _run_psql(self.database, statement, timeout=self.timeout_s)
        if proc.returncode != 0:
            state = _sqlstate(proc.stderr)
            # The SQLSTATE is put in the MESSAGE, not only on the exception
            # object, because `GroupCommitWriter.drain_once` catches this by
            # design (§12.4 turns an outage into SINK_DEGRADED rather than a
            # crash) and stringifies it into `CommitResult.error`. A caller
            # reading the seam's own result must still be able to assert the
            # REASON — check-contract rule 11 — and not merely that something
            # went wrong.
            raise SinkError(
                f"group-commit of {len(rows)} row(s) into {self.database}."
                f"{LOG_TABLE} as role {self.role!r} FAILED with SQLSTATE "
                f"{state or 'NONE REPORTED'}: {proc.stderr.strip()[-400:]}",
                sqlstate=state,
                stderr=proc.stderr,
            )
        landed = len([line for line in proc.stdout.splitlines() if line.strip()])
        self._next_seq = first_seq + len(rows)
        self.groups += 1
        self.rows_seen += len(rows)
        self.rows_landed += landed
        self.rows_deduplicated += len(rows) - landed
        return landed
