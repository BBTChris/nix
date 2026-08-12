"""§9's Plane-1 write path: enqueue → durable local WAL → writer → group-commit.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §9 (*Persistence Model,
event-sourced*), §11.6 (*group-commit event-log writes off hot path,
WAL-buffered*), §12.4 (*Degraded persistence ≠ degraded trading*), §12.10
(Plane 1, **Limiter sole writer, no new writers, ever**). The types are the
FROZEN `scripts/nixrisk/seam.py`.

§9, verbatim: *"**Limiter = sole writer.** Enqueue → **durable local WAL** →
shared-pool writer → **group-commit** to Postgres. Crash gap healed by startup
reconciliation vs broker truth."*

---

## THE SPLIT IS THE POINT, NOT AN IMPLEMENTATION DETAIL

`Plane1Wal.enqueue` is synchronous, bounded, and **returns without durability**
— a `write()` into the kernel's page cache and nothing more. `sync_to_disk` is
the durability verb and it is the one that costs: `flush()` then
**`os.fsync()`**, the syscall, on the WAL's own file descriptor.

**A WAL IS DURABLE ONLY IF IT FSYNCS.** A write that returned successfully is a
write the page cache accepted; a power cut discards it and the process that made
it never learns. So `sync_to_disk` is not a formality around `flush()`, and the
gate over this module does not take the docstring's word for it — it runs a
child under `strace -y -e trace=fsync,fdatasync` and requires the syscall to
appear **against this WAL's path**. See `checks/check_plane1_wal.py`.

**And SIGKILL does not prove it.** A killed process's dirty page-cache pages
survive: the kernel is still up and still owns them. So a kill drill measures
the CRASH GAP — what a restarted Limiter can recover, and how much Postgres has
not yet been told — and measures nothing at all about fsync. The two properties
need two instruments and this module says so rather than letting one green cover
both.

---

## §12.4 — TWO FAILURES THAT LOOK ALIKE AND ARE NOT

> Postgres outage: WAL buffers, trading continues, operator alerted.
> **Disk-critical** (WAL cannot append) ⇒ HALT new entries — no audit trail, no
> new risk. Open positions remain protected (stops read memory, not disk).

`PersistenceState` is those two failures kept apart:

* `SINK_DEGRADED` — the group-commit sink refused. Rows accumulate in the WAL,
  `admits_new_entries()` stays **True**, an operator alert fires. Trading
  continues, because the record of it is intact and merely behind.
* `DISK_CRITICAL` — the append itself failed. `admits_new_entries()` goes
  **False** and names the errno. There is no audit trail, so there is no new
  risk.

`protective_exit_allowed()` is **True in every state including
`DISK_CRITICAL`**, and it is a separate verb rather than an argument to the
first one, because the difference between the two answers is the difference
between a bad afternoon and a stopped business. An exit blocked by a full disk
would leave open positions unprotected precisely when the system is least able
to report it.

---

## WHAT IS NOT IN THIS ARC

**Full Postgres schema integration and cold-start reconciliation are NOT built
here.** `CommitSinkPort` is the seam a Postgres writer will implement; the only
implementations in this tree are the in-memory `RecordingSink` and the test
doubles. §9's *"crash gap healed by startup reconciliation vs broker truth"* is
named by `Recovery` and healed by nobody yet: this module can tell a restarted
Limiter exactly which rows are on disk and which the sink has not seen, and
turning that into a reconciliation against broker truth is a separate arc. No
verdict from this module's gate may be read as covering either.
"""

from __future__ import annotations

import enum
import json
import os
import time
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from nixrisk.seam import EventKind, EventRow

# R0903 (too-few-public-methods): `CommitSinkPort` is a single-verb Protocol —
# the DECLARATION of §9's shared-pool boundary and nothing else.
# pylint: disable=too-few-public-methods

#: Record framing: `<crc32 hex> <json>\n`. The checksum is not decoration — it is
#: what lets `recover()` tell a TORN TAIL (a record the crash cut in half) from a
#: complete record, without which a restarted Limiter would parse a fragment as
#: truth or refuse to start. A length prefix would do the same job for truncation
#: and nothing for corruption; a bare newline frame does neither.
_FRAME: Final[str] = "{crc:08x} {body}\n"
_RECORD_SEP: Final[bytes] = b"\n"

#: §12.4's alert. A `Callable[[str, str], None]` — `(event, detail)` — rather
#: than a logger, because §12.10 keeps Plane 2 diagnostic and this module must
#: not become a second Plane-1 writer by accident. The default DROPS, which is
#: honest: a WAL with no alert sink configured is not alerting, and pretending
#: otherwise by printing would put an unstructured line where §12.10 requires a
#: structured one.
AlertFn = Callable[[str, str], None]


class WalError(RuntimeError):
    """A Plane-1 WAL operation was refused. Always carries what could not be done."""


class DiskCritical(WalError):
    """§12.4's disk-critical condition: the WAL could not append.

    Raised by `enqueue` at the moment the append fails AND on every subsequent
    `enqueue`, because the condition does not clear by itself. §12.4: HALT new
    entries — no audit trail, no new risk.
    """


class PersistenceState(enum.Enum):
    """§12.4's three states. The two failures are DIFFERENT and stay different."""

    HEALTHY = "healthy"
    #: Postgres (the group-commit sink) refused. WAL buffers; trading CONTINUES.
    SINK_DEGRADED = "sink_degraded"
    #: The WAL cannot append. HALT new entries; open positions stay protected.
    DISK_CRITICAL = "disk_critical"


# ---------------------------------------------------------------------------
# The record codec (§9: timestamp + strategy_id + trade_id + reason on every row)
# ---------------------------------------------------------------------------


def encode_row(row: EventRow) -> bytes:
    """One §9 row -> one framed, checksummed record."""
    body = json.dumps(
        {
            "kind": row.kind.value,
            "ts": row.ts,
            "strategy_id": row.strategy_id,
            "reason": row.reason,
            "trade_id": row.trade_id,
            "fields": dict(row.fields),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return _FRAME.format(crc=zlib.crc32(body.encode("utf-8")), body=body).encode(
        "utf-8"
    )


def decode_record(record: bytes) -> EventRow:
    """One framed record -> one `EventRow`. Raises `WalError` on any damage."""
    try:
        checksum, _, body = record.decode("utf-8").partition(" ")
        expected = int(checksum, 16)
    except (UnicodeDecodeError, ValueError) as exc:
        raise WalError(f"unframed WAL record {record[:80]!r}: {exc!r}") from exc
    if not body:
        raise WalError(f"WAL record carries no body: {record[:80]!r}")
    actual = zlib.crc32(body.encode("utf-8"))
    if actual != expected:
        raise WalError(
            f"WAL record checksum {actual:08x} != framed {expected:08x} — the "
            "record on disk is not the record that was written"
        )
    try:
        raw = json.loads(body)
        return EventRow(
            kind=EventKind(raw["kind"]),
            ts=float(raw["ts"]),
            strategy_id=str(raw["strategy_id"]),
            reason=str(raw["reason"]),
            trade_id=None if raw["trade_id"] is None else str(raw["trade_id"]),
            fields={str(k): str(v) for k, v in raw["fields"].items()},
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise WalError(f"undecodable WAL row: {exc!r}") from exc


@dataclass(frozen=True)
class Recovery:
    """What a restarted Limiter can read back, and what the crash cost.

    `torn_tail_bytes` and `corrupt_records` are REPORTED, never repaired here.
    §9 heals the crash gap by *"startup reconciliation vs broker truth"*, which
    this arc does not build; silently discarding a damaged tail would destroy the
    only evidence that reconciliation will have.
    """

    path: str
    rows: tuple[EventRow, ...]
    torn_tail_bytes: int
    corrupt_records: int
    bytes_read: int

    @property
    def intact(self) -> bool:
        """True when every byte on disk parsed as a complete, checksummed row."""
        return self.torn_tail_bytes == 0 and self.corrupt_records == 0


def recover(path: str | os.PathLike[str], limit_bytes: int | None = None) -> Recovery:
    """Read a WAL back after a crash. NEVER raises on damage — it reports it.

    `limit_bytes` reads only the first N bytes, which is how `GroupCommitWriter`
    reads the DURABLE PREFIX and nothing beyond it. A plain read cannot make that
    distinction: bytes that reached the page cache are visible to every reader on
    this machine whether or not they ever reached the platter, so "what is on
    disk" and "what a `read()` returns" are different questions and only the
    WAL's own `durable_bytes` answers the first.
    """
    target = Path(path)
    try:
        blob = target.read_bytes()
    except OSError as exc:
        raise WalError(f"cannot read WAL {target}: {exc!r}") from exc
    if limit_bytes is not None:
        blob = blob[: max(0, limit_bytes)]
    complete, torn = blob.rsplit(_RECORD_SEP, 1) if _RECORD_SEP in blob else (b"", blob)
    rows: list[EventRow] = []
    corrupt = 0
    for record in complete.split(_RECORD_SEP) if complete else ():
        if not record:
            continue
        try:
            rows.append(decode_record(record))
        except WalError:
            corrupt += 1
    return Recovery(
        path=str(target),
        rows=tuple(rows),
        torn_tail_bytes=len(torn),
        corrupt_records=corrupt,
        bytes_read=len(blob),
    )


# ---------------------------------------------------------------------------
# The WAL (§9's hot half, §12.4's disk-critical arm)
# ---------------------------------------------------------------------------


def _drop_alert(event: str, detail: str) -> None:
    """The default alert sink: drops. See `AlertFn` for why it is not a print."""
    del event, detail


class Plane1Wal:  # pylint: disable=too-many-instance-attributes
    # Twelve attributes, of which SIX are counters (`enqueued`,
    # `bytes_written`, `fsyncs`, `durable`, `durable_bytes`, `_pending`). A WAL
    # that cannot say how many times it reached stable storage can only be
    # believed, and `durable_bytes` in particular is what lets
    # `GroupCommitWriter` read the durable PREFIX rather than the whole file.
    """§9's durable local WAL. Satisfies `Plane1Port`. The Limiter is SOLE writer.

    Opened `O_APPEND` so every write lands at the end whatever else holds the
    file, and `buffering=0` so `enqueue` issues the `write(2)` itself rather than
    handing bytes to a userspace buffer that a SIGKILL would take with it. That
    choice is deliberate and it is the one that makes the crash gap MEASURABLE:
    with Python-level buffering, a killed process loses whatever had not been
    flushed and the loss is invisible from outside. Unbuffered, everything
    `enqueue` returned from is in the kernel, and what is lost to a crash is
    exactly nothing — while what is lost to a POWER CUT is everything since the
    last `sync_to_disk`, which is the distinction `fsyncs` exists to expose.

    Counters, for the same reason every other transport in this tree has them:
    `enqueued`, `bytes_written`, `fsyncs`, `durable`. A WAL that cannot say how
    many times it reached stable storage can only be believed.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        alert: AlertFn = _drop_alert,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self._alert = alert
        self._clock = clock
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # pylint: disable=consider-using-with
            # The handle's lifetime is the WAL's, not this call's.
            self._fh = open(self.path, "ab", buffering=0)  # noqa: SIM115
        except OSError as exc:
            raise WalError(f"cannot open WAL {self.path}: {exc!r}") from exc
        self._state = PersistenceState.HEALTHY
        self._critical_reason = ""
        self._pending = 0
        self.enqueued = 0
        self.bytes_written = 0
        self.fsyncs = 0
        self.durable = 0
        self.durable_bytes = 0

    # -- the port ---------------------------------------------------------

    def enqueue(self, row: EventRow) -> None:
        """Append one row. Bounded, hot-path-safe, and NOT durable (§9, §11.6)."""
        if self._state is PersistenceState.DISK_CRITICAL:
            raise DiskCritical(
                f"WAL {self.path} is DISK-CRITICAL ({self._critical_reason}) — "
                "§12.4 HALTs new entries when the WAL cannot append: no audit "
                "trail, no new risk"
            )
        record = encode_row(row)
        try:
            written = self._fh.write(record)
        except OSError as exc:
            self._go_critical(exc)
            raise DiskCritical(
                f"WAL {self.path} could not append {len(record)} bytes: "
                f"{self._critical_reason}"
            ) from exc
        self._pending += 1
        self.enqueued += 1
        self.bytes_written += int(written or 0)

    def sync_to_disk(self) -> int:
        """Force the buffered rows to STABLE storage. Returns rows made durable.

        `os.fsync` is the whole verb. There is no code path in this class that
        makes a row durable without it, which is what the gate's strace arm is
        able to assert against this file's own path.
        """
        if not self._pending:
            return 0
        try:
            os.fsync(self._fh.fileno())
        except OSError as exc:
            self._go_critical(exc)
            raise DiskCritical(
                f"WAL {self.path} could not fsync: {self._critical_reason}"
            ) from exc
        made = self._pending
        self._pending = 0
        self.fsyncs += 1
        self.durable += made
        self.durable_bytes = self.bytes_written
        return made

    def pending(self) -> int:
        """Rows enqueued but not yet durable. A §12.4 disk-critical input."""
        return self._pending

    def fileno(self) -> int:
        """The WAL's own descriptor.

        Public so an INSTRUMENT can write a deliberately damaged tail to the real
        file the real WAL owns (`scripts/wal_kill_drill.py`'s torn arm) instead
        of reaching through `_fh`. The alternative was a drill that fabricated a
        second file and called it a crash, which measures the fabricator.
        """
        return self._fh.fileno()

    # -- §12.4 ------------------------------------------------------------

    @property
    def state(self) -> PersistenceState:
        """§12.4's current persistence state. Never inferred from a counter."""
        return self._state

    def admits_new_entries(self) -> tuple[bool, str]:
        """§12.4: may the Limiter accept a NEW ENTRY right now? `(ok, reason)`.

        False in `DISK_CRITICAL` only. A degraded sink is explicitly NOT a reason
        to stop trading — that is the whole sentence *"degraded persistence ≠
        degraded trading"*, and conflating the two turns a Postgres restart into
        a halted business.
        """
        if self._state is PersistenceState.DISK_CRITICAL:
            return False, (
                f"§12.4 disk-critical: {self._critical_reason} — HALT new entries, "
                "no audit trail, no new risk"
            )
        if self._state is PersistenceState.SINK_DEGRADED:
            return True, (
                f"§12.4 degraded persistence is NOT degraded trading: the "
                f"group-commit sink is down and {self._pending + self.durable} "
                "row(s) are buffering in the WAL; the operator is alerted and "
                "entries continue"
            )
        return True, f"WAL healthy at {self.path}"

    def protective_exit_allowed(self) -> tuple[bool, str]:
        """§12.4: may a protective exit fire? ALWAYS true, in every state.

        *"Open positions remain protected (stops read memory, not disk)."* The
        exit path has no persistence dependency by design (§3's exit path is
        "zero wire dependency"), so a full disk must never reach it.
        """
        return True, (
            f"protective exit is unconditional in state {self._state.value}: §12.4 "
            "keeps open positions protected because stops read MEMORY, not disk"
        )

    def _go_critical(self, exc: OSError) -> None:
        """Latch DISK_CRITICAL and alert. The condition does not clear itself."""
        self._critical_reason = f"{type(exc).__name__} errno={exc.errno} {exc.strerror}"
        self._state = PersistenceState.DISK_CRITICAL
        self._alert("wal_disk_critical", f"{self.path}: {self._critical_reason}")

    def note_sink(self, degraded: bool, detail: str) -> None:
        """Move between HEALTHY and SINK_DEGRADED. Never out of DISK_CRITICAL.

        Public because `GroupCommitWriter` — the §9 shared-pool half, a separate
        object by design — is the only thing that learns the sink's condition. A
        private spelling reached through would make the reader believe the two
        halves are one object, which is exactly the coupling §11.6 removes.
        """
        if self._state is PersistenceState.DISK_CRITICAL:
            return
        target = (
            PersistenceState.SINK_DEGRADED if degraded else PersistenceState.HEALTHY
        )
        if target is self._state:
            return
        self._state = target
        self._alert(
            "wal_sink_degraded" if degraded else "wal_sink_restored",
            f"{self.path}: {detail}",
        )

    def close(self) -> None:
        """Release the handle. Does NOT fsync — durability is an explicit verb."""
        self._fh.close()


# ---------------------------------------------------------------------------
# Group commit (§9's shared-pool half, §11.6 off the hot path)
# ---------------------------------------------------------------------------


class CommitSinkPort(Protocol):
    """§9's Postgres boundary. NOT implemented against Postgres in this arc."""

    def commit(self, rows: Sequence[EventRow]) -> int:
        """Persist a GROUP of rows in one transaction. Returns rows persisted."""


@dataclass
class RecordingSink:
    """An in-memory `CommitSinkPort`, and an outage switch. Not Postgres.

    `fail_with` is how §12.4's Postgres outage is produced without a Postgres:
    set it and every `commit` raises. It is production code rather than a test
    double because the drill process needs it too, and a drill importing a test
    module is a drill measuring the test suite.
    """

    rows: list[EventRow] = field(default_factory=list)
    commits: int = 0
    fail_with: Exception | None = None

    def commit(self, rows: Sequence[EventRow]) -> int:
        """Persist a group, or raise `fail_with` — §12.4's outage, on demand."""
        if self.fail_with is not None:
            raise self.fail_with
        self.rows.extend(rows)
        self.commits += 1
        return len(rows)


@dataclass(frozen=True)
class CommitResult:
    """One group-commit attempt. Both outcomes carry the backlog they left."""

    committed: int
    backlog: int
    state: PersistenceState
    error: str = ""

    @property
    def ok(self) -> bool:
        """True when the sink took the group."""
        return not self.error


class GroupCommitWriter:
    """§9's shared-pool writer. Off the hot path (§11.6), and only ever behind it.

    It commits **from the WAL's DURABLE PREFIX only**. That ordering is §9's own
    — *"enqueue → durable local WAL → shared-pool writer → group-commit"* — and
    it is what makes the crash gap one-sided: after a crash, everything Postgres
    holds is on disk, and the gap is rows on disk that Postgres has not seen. The
    reverse gap (Postgres holding a row the WAL lost) cannot arise, and a writer
    that committed un-fsynced rows would create it.

    The cursor is a byte offset into the WAL, held **in memory**. That is a
    deliberate, stated limitation of this arc: after a restart the cursor is zero
    and every recovered row looks uncommitted. §9's answer is startup
    reconciliation vs broker truth, which is NOT in this arc, so the honest
    behaviour is to re-present rather than to invent a persisted cursor whose
    own durability nothing here proves.
    """

    def __init__(
        self,
        wal: Plane1Wal,
        sink: CommitSinkPort,
        *,
        batch_max: int = 256,
    ) -> None:
        if batch_max < 1:
            raise WalError(f"batch_max must be >= 1, got {batch_max!r}")
        self._wal = wal
        self._sink = sink
        self._batch_max = batch_max
        self._cursor = 0
        self.groups = 0
        self.rows_committed = 0
        self.failures = 0

    @property
    def cursor(self) -> int:
        """Rows this writer has seen the sink accept. Never persisted (see above)."""
        return self._cursor

    def durable_rows(self) -> int:
        """Rows in the WAL's DURABLE PREFIX — bounded by the last fsync, not the
        last write. Read from the file, never from an in-memory counter."""
        return len(recover(self._wal.path, self._wal.durable_bytes).rows)

    def backlog(self) -> int:
        """Durable rows the sink has not taken. §12.4's buffering, as a number."""
        return max(0, self.durable_rows() - self._cursor)

    def drain_once(self) -> CommitResult:
        """One group-commit attempt. Never raises: a sink outage is a RESULT."""
        available = recover(self._wal.path, self._wal.durable_bytes).rows
        rows = available[self._cursor :][: self._batch_max]
        if not rows:
            self._wal.note_sink(False, "nothing to commit")
            return CommitResult(
                0, max(0, len(available) - self._cursor), self._wal.state
            )
        try:
            taken = self._sink.commit(rows)
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
            self.failures += 1
            detail = f"{type(exc).__name__}: {exc}"
            # §12.4: a sink outage buffers and ALERTS. It does not halt.
            self._wal.note_sink(True, detail)
            return CommitResult(
                0, max(0, len(available) - self._cursor), self._wal.state, error=detail
            )
        self._cursor += len(rows)
        self.groups += 1
        self.rows_committed += taken
        self._wal.note_sink(False, f"group of {len(rows)} committed")
        return CommitResult(
            taken, max(0, len(available) - self._cursor), self._wal.state
        )
