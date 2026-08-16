"""§12.1's durable record — the local append-only marker file, and its replay side.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 034 / sub-agent B (B2). Implements the FROZEN `MarkerWriterPort` and
`MarkerReplayPort` declared in `scripts/nixsentinel/seam.py`. It changes neither
port and adds no verb to either.

------------------------------------------------------------------------------
THE GAP THIS CLOSES, IN THE SPEC'S OWN WORDS (§12.1:608-614)
------------------------------------------------------------------------------
*"the Sentinel fires precisely when the sole event-log writer (Limiter) is dead,
so its flatten would otherwise be the least-recorded action in the system. Fix:
the Sentinel writes a local append-only marker file (timestamp, trigger cause,
symbols, broker acks) before and after acting — no Postgres, no shared writer,
nothing to fail. On next boot, cold-start reconciliation reads the marker and
books the flatten into the real event log retroactively (rows tagged
`source=sentinel`), then archives the marker."*

Three properties follow, and each is mechanical here rather than promised:

1. **DURABLE ON RETURN.** Every `append` is one `write(2)` then one `fsync(2)`
   before the call returns, and the first append also fsyncs the containing
   DIRECTORY so the file's own directory entry survives. A marker still in the
   page cache when the machine goes down records nothing, and this file exists
   only for the case where the process that wrote it does not survive.
2. **APPEND-ONLY.** `MarkerWriter` has one verb. There is no truncate, no seek,
   no clear — the seam's ARM 6 polices the declaration and this module holds the
   implementation to it by simply not having anywhere to put such a call.
   Directive 6 one layer up: append history, never rewrite banked evidence.
3. **A `BEFORE` WITH NO `AFTER` IS THE POINT, NOT A DEFECT.** It is the record of
   a Sentinel that died mid-flatten, and it is the single most valuable line the
   file can hold: without it, a mid-flatten death is indistinguishable from a
   Sentinel that never woke, and cold start would reconcile a partially flattened
   account against a log that never heard of the attempt. `read_pending` returns
   it; `nixrisk/coldstart.py` books it flagged `interrupted`.

------------------------------------------------------------------------------
WHY THIS IS NOT `nixrisk.halt.HaltMarker`, WHICH LOOKS ALMOST IDENTICAL
------------------------------------------------------------------------------
Doctrine C.9 says extend the instrument that owns a property, never build a
second — so the near-duplicate needs its reason stated rather than left to be
noticed. `nixrisk/halt.py` carries a marker built to *"§12.1's construction"* for
a DIFFERENT subject: §12.5:634-638's Limiter-down HALT row. It lives inside
`nixrisk`, imports `nixrisk.seam`, and its records are HALT causes.

This one cannot import it, and the prohibition is the safety property rather
than taste: §12.1:603 requires the Sentinel to run on a *"separate code path
(minimal common-mode failure)"*, and it runs precisely when the Limiter is dead.
An import edge from here into `nixrisk` would mean the defect that killed the
Risk Engine — a bad import, a config parse, a shared invariant — also stops the
record of the emergency being written. The duplication is therefore FORCED by
the spec, and it is the smaller cost: two ~80-line writers versus a common-mode
failure on the one path that has no fallback.

------------------------------------------------------------------------------
WHERE THE FILE LIVES — decided BEFORE this package existed
------------------------------------------------------------------------------
`docs/directory_structure.md`'s `logs` line names *"Sentinel marker file"* as a
Non-Plane artifact. That is honoured here, not re-decided. §12.1's marker is
deliberately not Plane 1 (it is written when the sole Plane-1 writer is dead) and
deliberately not Plane 2 (§12.10 keeps Plane 2 in journald, and journald is not
guaranteed available on the path this record exists to survive).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from nixsentinel.seam import (
    MARKER_SCHEMA,
    BrokerAck,
    MarkerPhase,
    MarkerRecord,
    TriggerCause,
)

#: The file's name under `logs/`. One file, not one per event: §12.1:610 says
#: *"a local append-only marker file"*, singular, and a per-event file would make
#: "every record awaiting replay, in write order" a directory listing whose order
#: depends on the filesystem.
DEFAULT_MARKER_NAME = "sentinel_marker.jsonl"

#: The suffix an archived marker takes. A RENAME, never a delete (§12.1:613 says
#: *"archives the marker"*, and directive 6 says never rewrite banked evidence):
#: the marker is the only account of what the dying process saw, and the replay
#: that consumed it is not a reason to destroy it.
ARCHIVE_SUFFIX = "replayed"

#: `0600`. The marker names symbols and position counts; nothing outside
#: `state/` needs to be world readable and the ambient umask is not a guarantee.
_MODE = 0o600


class MarkerError(RuntimeError):
    """The marker could not be written, read, or archived.

    RAISED, never swallowed — and that is the opposite of the rule `AlertPort`
    carries. An alert that cannot be delivered must not abort the flatten (§14's
    zero delivery dependency); a MARKER that cannot be written is the failure of
    the one mechanism §12.1:608 exists to provide, so it is loud. The watchdog
    treats a failed `BEFORE` append as a refusal to act blind: acting with no
    record is the state the fix was written to eliminate.
    """


def as_dict(record: MarkerRecord) -> dict[str, object]:
    """One record as a plain JSON-compatible mapping. PUBLIC, and single-homed.

    Public because the writer is not the only thing that needs the wire shape:
    `scripts/sentinel_kill_drill.py` reports what the marker held, and a second
    spelling of this mapping there would be two descriptions of one format that
    could disagree about a field name (doctrine C.9, directive 3). Pylint's
    duplicate-code checker caught exactly that pair before this function existed.
    """
    return {
        "schema": record.schema,
        "phase": record.phase.value,
        "ts": record.ts,
        "cause": record.cause.value,
        "symbols": list(record.symbols),
        "acks": [
            {"symbol": ack.symbol, "ok": ack.ok, "detail": ack.detail}
            for ack in record.acks
        ],
        "sentinel_pid": record.sentinel_pid,
        "heartbeat_age_s": record.heartbeat_age_s,
    }


def _encode(record: MarkerRecord) -> str:
    """One record as one JSON line. Sorted keys, no spaces — stable bytes."""
    return json.dumps(as_dict(record), sort_keys=True, separators=(",", ":")) + "\n"


def _refusal(where: str, exc: Exception) -> MarkerError:
    """The one refusal every malformed-record path raises.

    One sentence in one place, so the three callers below cannot drift apart in
    what they say. SKIPPING is the single thing this reader must never do: the
    unparsable line may be the only evidence that an emergency flatten was
    attempted, and discarding it is the failure §12.1:608's fix exists to prevent.
    """
    return MarkerError(
        f"{where}: not a marker record ({exc!r}) — refusing to SKIP it. A "
        "line this reader cannot parse may be the only evidence that an "
        "emergency flatten was attempted, and discarding it is the failure "
        "§12.1:608's fix exists to prevent"
    )


def _decode(raw: object, where: str) -> MarkerRecord:
    """One JSON object back into a `MarkerRecord`. Raises on anything else.

    The SCHEMA is settled before any field is given a meaning: a record from an
    older build may parse perfectly and mean something else, and this file is
    written on one boot and read on a later one.
    """
    if not isinstance(raw, dict):
        raise MarkerError(
            f"{where}: record is {type(raw).__name__}, expected an object"
        )
    try:
        schema = int(raw["schema"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _refusal(where, exc) from exc
    if schema != MARKER_SCHEMA:
        raise MarkerError(
            f"{where}: marker schema {schema} != this build's {MARKER_SCHEMA}. "
            "The writer and the replayer are different processes on different "
            "BOOTS and may be different builds, so the fields are refused "
            "rather than read positionally into a meaning they may not have"
        )
    try:
        return MarkerRecord(
            schema=schema,
            phase=MarkerPhase(raw["phase"]),
            ts=float(raw["ts"]),
            cause=TriggerCause(raw["cause"]),
            symbols=tuple(str(symbol) for symbol in raw["symbols"]),
            acks=tuple(
                BrokerAck(
                    symbol=str(ack["symbol"]),
                    ok=bool(ack["ok"]),
                    detail=str(ack.get("detail", "")),
                )
                for ack in raw["acks"]
            ),
            sentinel_pid=int(raw["sentinel_pid"]),
            heartbeat_age_s=float(raw["heartbeat_age_s"]),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise _refusal(where, exc) from exc


# R0903 (too-few-public-methods): ONE verb IS the append-only property. The
# frozen `MarkerWriterPort` declares `append` and nothing else precisely so a
# writer cannot rewind, and adding a second verb to reach a threshold is the
# widening `check_sentinel_seam` ARM 6 exists to refuse.
# pylint: disable=too-few-public-methods
class MarkerWriter:
    """§12.1:610's writer. Satisfies the frozen `MarkerWriterPort`. ONE verb.

    Deliberately NOT a subclass of `MarkerWriterPort`: a `Protocol`'s method
    bodies are docstrings, so a verb this class forgot to override would silently
    return `None` and a caller would believe a record was durable when nothing
    was written — which is precisely the failure this file exists to make
    impossible. Conformance is proven by comparing signatures against the port,
    which is a measurement rather than a nominal claim. `nixrisk/coldstart.py`
    records the same argument for the same reason.

    Deliberately SEPARATE from `MarkerReplay` even though both hold one path.
    A single object carrying `append` and `archive` would be a writer that can
    retire the file it is appending to; the seam splits the ports precisely so
    that the act of retiring evidence lives with the boot-time reader that has
    already booked it, never with the dying process.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MarkerError(
                f"cannot create the marker directory for {self.path}: {exc!r}"
            ) from exc

    def append(self, record: MarkerRecord) -> None:
        """Append one record. Returns only once the bytes are DURABLE on disk.

        Durable means write + fsync, and on the record that CREATES the file it
        also means an fsync of the parent directory: without that, the file's
        directory entry can be lost even though its contents were synced, and a
        marker that cannot be found is a marker that was not written.

        `O_APPEND` is what makes concurrent appends safe without a lock — the
        kernel places every write at the current end of file — and it is also
        what makes this writer structurally unable to overwrite an earlier
        record. Append-only is a property of the open flags here, not a promise.
        """
        first = not self.path.exists()
        line = _encode(record).encode("utf-8")
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _MODE)
        except OSError as exc:
            raise MarkerError(f"cannot open the marker {self.path}: {exc!r}") from exc
        try:
            os.write(fd, line)
            os.fsync(fd)
        except OSError as exc:
            raise MarkerError(
                f"cannot append to the marker {self.path}: {exc!r} — refusing to "
                "return as if the record were durable"
            ) from exc
        finally:
            os.close(fd)
        if first:
            self._fsync_parent()

    def _fsync_parent(self) -> None:
        """Sync the directory entry of a marker that has just been created."""
        try:
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError as exc:
            raise MarkerError(
                f"cannot open {self.path.parent} to sync the marker's directory "
                f"entry: {exc!r}"
            ) from exc
        try:
            os.fsync(dir_fd)
        except OSError as exc:
            raise MarkerError(
                f"cannot sync the directory entry for {self.path}: {exc!r} — the "
                "record is on the device but the name that finds it may not be"
            ) from exc
        finally:
            os.close(dir_fd)


class MarkerReplay:
    """Cold start's side. Satisfies the frozen `MarkerReplayPort`.

    `read_pending` and `archive` are separate verbs because §12.1:612-613 puts
    the booking BETWEEN them: archiving inside the read would lose the marker if
    the booking then failed, turning a recoverable replay into a silent gap in
    Plane 1. The seam says so; this class is what makes it true.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        #: Injected so the archive name is deterministic under test. `archive()`
        #: takes no argument because the FROZEN port declares none, and a port
        #: this module may not change is not a reason to leave the stamp to
        #: whatever `time.time` happens to be at import.
        self._clock = clock

    def read_pending(self) -> tuple[MarkerRecord, ...]:
        """Every record awaiting replay, in WRITE ORDER. Empty when there is none.

        An absent file is the ORDINARY case — the Sentinel never fired — and is
        an empty tuple, never an error. A file that exists and holds a line this
        reader cannot parse is a `MarkerError`: see `_decode` for why skipping is
        the one thing it must not do.

        An unmatched `BEFORE` is returned like any other record. The pairing is
        the CALLER's to interpret (`nixrisk/coldstart.py` does it), because "what
        an interrupted act means" is a reconciliation question and this class is
        a reader.
        """
        try:
            blob = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise MarkerError(f"cannot read the marker {self.path}: {exc!r}") from exc
        records: list[MarkerRecord] = []
        for index, line in enumerate(blob.splitlines()):
            if not line.strip():
                continue
            where = f"{self.path}:{index + 1}"
            try:
                raw = json.loads(line)
            except ValueError as exc:
                raise MarkerError(f"{where}: not JSON ({exc!r})") from exc
            records.append(_decode(raw, where))
        return tuple(records)

    def archive(self) -> None:
        """Retire the replayed marker. Called ONLY after the rows are booked.

        A rename, never a delete. The archived name carries the stamp so two
        replays on the same boot cannot collide, and so an operator reading
        `logs/` can see when each was retired.
        """
        if not self.path.exists():
            return
        target = self.path.with_name(
            f"{self.path.name}.{self._clock():.6f}.{ARCHIVE_SUFFIX}"
        )
        try:
            self.path.rename(target)
        except OSError as exc:
            raise MarkerError(
                f"cannot archive the marker {self.path} to {target}: {exc!r}"
            ) from exc


def pending_acts(
    records: tuple[MarkerRecord, ...],
) -> tuple[tuple[MarkerRecord, MarkerRecord | None], ...]:
    """Pair each `BEFORE` with its `AFTER`, in write order. `None` = INTERRUPTED.

    The one piece of interpretation this module owns, because it is a property of
    the FILE FORMAT rather than of reconciliation: §12.1:610's *"before and
    after acting"* makes the pair the unit, and a `BEFORE` whose `AFTER` never
    arrived is the interrupted act the whole fix exists to preserve.

    A lone `AFTER` — a record written with no preceding `BEFORE` — is a
    NON-FLATTEN wake (`HEARTBEAT_LOST_NO_POSITIONS`, `HEARTBEAT_RECOVERED`), for
    which there was no act to bracket. `nixsentinel/watchdog.py` writes exactly
    one `AFTER` for those, precisely so that the invariant *a `BEFORE` with no
    `AFTER` means interrupted* stays exact and never has to be qualified.
    Returned with a `None` first element is impossible here; those records come
    back through `unbracketed`.
    """
    pairs: list[tuple[MarkerRecord, MarkerRecord | None]] = []
    open_before: MarkerRecord | None = None
    for record in records:
        if record.phase is MarkerPhase.BEFORE:
            if open_before is not None:
                pairs.append((open_before, None))
            open_before = record
            continue
        if open_before is not None:
            pairs.append((open_before, record))
            open_before = None
    if open_before is not None:
        pairs.append((open_before, None))
    return tuple(pairs)


def unbracketed(records: tuple[MarkerRecord, ...]) -> tuple[MarkerRecord, ...]:
    """Every `AFTER` that brackets nothing — the wake-ups that did NOT flatten.

    These exist so that "the Sentinel woke and decided not to act" is an
    OBSERVABLE FACT rather than an absence of evidence. A nuisance flatten is its
    own hazard (§12.1:605 conditions the act on positions possibly being open),
    and a deadman that proved it did nothing by producing no output would be
    indistinguishable from a deadman that never ran.
    """
    bracketed = {id(after) for _before, after in pending_acts(records) if after}
    return tuple(
        record
        for record in records
        if record.phase is MarkerPhase.AFTER and id(record) not in bracketed
    )
