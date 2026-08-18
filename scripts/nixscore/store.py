"""The §6.6 durable score store: the pair-row survives the process, and
quarantine ARCHIVES exactly one strategy's rows rather than destroying them.

## The two properties, and why they are ONE module

§6.6:429-433, *Ownership & authority (locked)*:

> **Canonical key = `(strategy_id, symbol)` (v1.3, locked):** one row per pair,
> realized-P&L EMA per pair. This is the only keying under which the rest of the
> design is simultaneously true: score **persists across process death** (keyed
> to the pair, not the process — §4) and **quarantine removes exactly that
> strategy's rows** (archived, not destroyed).

The spec says *simultaneously*, and it is right to: the two properties are the
same fact read twice. A store keyed to the process cannot survive one, and a
store keyed to the SYMBOL cannot remove *exactly that strategy's* rows — it
would take the neighbours sharing the symbol with it. Both failures are invisible
to a single-strategy test, which is why the gate that owns this file
(`checks/check_scoring_lifecycle.py`) drives two strategies over one symbol and
one strategy over two symbols before it believes any "removed exactly".

§4:275-280 is the same rule from the recovery side:

> a normal crash-restart **persists** the strategy's realized-P&L history (score
> keyed by strategy×symbol, not by process instance; a crash is not a trade and
> never books a phantom zero/loss …). On **quarantine**, the strategy is
> **removed from the live ranking table** … its realized history is **archived,
> not destroyed** (recoverable if the operator deliberately brings it back).

## WHY A FILE, AND WHY `os.replace`

The subject is a process that DIES. A score held only in the Scoring process's
memory is reset by the very event it must survive, exactly as
`nixrisk/supervision.py`'s `RestartLedger` argues about the crash counter. So the
rows go to disk, and every mutation is durable before the call returns: write a
sibling temp file, `fsync` it, `os.replace` it over the target, `fsync` the
directory. `os.replace` is atomic within a filesystem — POSIX guarantees a
concurrent reader sees either the whole old file or the whole new one, never a
blend — and that atomicity is what makes ARCHIVE atomic without a second
mechanism.

**That is the point of writing the whole document rather than a delta.** The
archive is not "remove from live, then add to archived", which is two writes with
a lethal instant between them where the rows are in NEITHER place. It is one
`os.replace` of a document in which the move has already happened. A kill at any
instant leaves the previous whole document or the next whole document.

In-memory state is swapped in **after** the durable write returns, never before,
so a raise mid-write leaves this object agreeing with the disk rather than with
an intention.

## ARCHIVED IS NOT ABSENT, and the API refuses to blur them

§6.6 says *archived, not destroyed*. If a consumer cannot tell the two apart, the
distinction is prose. `presence()` therefore returns a three-valued `Presence`
(`LIVE` / `ARCHIVED` / `ABSENT`) rather than a bool, and it is the only read that
crosses the archive boundary — `get()` and `snapshot()` see the LIVE table only,
because §4:279 removes a quarantined strategy from the live ranking table so it
*"can no longer win a contention tiebreak for capital it can't use"*.

## WHAT THIS MODULE IS NOT

No EMA arithmetic (that is the Scoring engine's, behind the §11 hot-path rule),
no ranking (`nixscore.seam.rank_rows`), no transport (`nixscore.seam`'s §12.7
publisher), no quarantine POLICY (`nixrisk.supervision.CrashLoopBreaker` decides
*who*; this decides *what happens to their rows*). It holds state and makes it
durable, and it is deliberately the only thing in `nixscore` that touches a disk.

## The §12.11 verb set is CLOSED — and nothing here asks to widen it

Four verbs, and verb 3 is *"`quarantine-restore` — … archived score rows return
to the live ranking table (§6.6); crash-loop counter resets."* `restore_strategy`
is the score half of that one verb. `archive_strategy` is NOT a fifth verb: it is
the automatic consequence of §4:273's quarantine, taken by supervision without an
operator, in the same way the flatten in §4's step 1 is not an operator verb.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import time
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from nixscore.seam import PairKey, RankingSnapshot, rank_rows, wire_key

#: Bumped whenever the ON-DISK DOCUMENT shape changes. A store written by a newer
#: revision is refused rather than half-read: §6.6's rows are the input to
#: capital allocation, so a field this code does not understand is a reason to
#: stop, not to guess.
STORE_REV = "1.0.0"

_REV_KEY = "store_rev"
_REVISION_KEY = "revision"
_LIVE_KEY = "live"
_ARCHIVED_KEY = "archived"
_ROWS_KEY = "rows"
_AT_KEY = "archived_at"
_REASON_KEY = "reason"

_SITE = "scripts/nixscore/store.py"

__all__ = [
    "STORE_REV",
    "ArchiveOutcome",
    "Presence",
    "RestoreOutcome",
    "ScoreRecord",
    "ScoreStore",
    "ScoreStoreError",
    "ScoreStorePort",
]


class ScoreStoreError(RuntimeError):
    """A store that cannot be trusted. Raised LOUD, never degraded to empty.

    The distinction this class exists to protect: **an empty store and an
    unreadable store are different facts.** An empty store means no strategy has
    ever scored; an unreadable one means the history may exist and cannot be
    seen. Returning `{}` for the second would silently book every strategy back
    to cold start — the phantom zero §4:276 forbids — and would make the
    atomicity measurement in `checks/check_scoring_lifecycle.py` unfalsifiable,
    because a torn file would read as a legitimately empty one.
    """


class Presence(StrEnum):
    """Where a pair stands. THREE values, because §6.6 has three states.

    `ARCHIVED` is not a shade of `ABSENT`: §6.6 says *archived, not destroyed*,
    and a consumer that cannot distinguish them cannot tell a quarantined
    strategy from one that never traded.
    """

    LIVE = "live"
    ARCHIVED = "archived"
    ABSENT = "absent"


@dataclasses.dataclass(frozen=True, slots=True)
class ScoreRecord:
    """One `(strategy_id, symbol)` pair's persisted realized-P&L history.

    Deliberately NOT `nixscore.seam.RankRow`: a rank is a property of the whole
    table at one instant and is recomputed on every publish, so persisting one
    would bank a derived figure that goes stale the moment a neighbour moves
    (directive 3). What is durable is the pair's own EMA and how much history
    stands behind it; `snapshot()` re-derives the ranks.
    """

    strategy_id: str
    symbol: str
    realized_ema: float
    days_observed: int
    updated_at: float

    @property
    def key(self) -> PairKey:
        """The `(strategy_id, symbol)` pair this record is keyed on (§6.6)."""
        return (self.strategy_id, self.symbol)

    def as_wire(self) -> dict[str, Any]:
        """This record as JSON-safe scalars."""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "realized_ema": float(self.realized_ema),
            "days_observed": int(self.days_observed),
            "updated_at": float(self.updated_at),
        }

    @classmethod
    def from_wire(cls, raw: Mapping[str, Any]) -> ScoreRecord:
        """One record off disk, or `ScoreStoreError` naming the bad field."""
        try:
            return cls(
                strategy_id=str(raw["strategy_id"]),
                symbol=str(raw["symbol"]),
                realized_ema=float(raw["realized_ema"]),
                days_observed=int(raw["days_observed"]),
                updated_at=float(raw["updated_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ScoreStoreError(
                f"{_SITE}: malformed score record {raw!r}: {exc!r}"
            ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class ArchiveOutcome:
    """What one archive did. `reason` is present on BOTH answers (§18).

    A no-op archive (nothing to move) is a real answer and says so; it is not an
    error, because §4:273 quarantines a strategy whether or not it has ever
    closed a trade, and a cold-start strategy legitimately owns no rows.
    """

    strategy_id: str
    archived: tuple[PairKey, ...]
    untouched: tuple[PairKey, ...]
    reason: str

    @property
    def moved(self) -> bool:
        """Whether any row actually changed side."""
        return bool(self.archived)


@dataclasses.dataclass(frozen=True, slots=True)
class RestoreOutcome:
    """§12.11 verb 3's score half. Says whether anything came back, and why.

    A restore of a strategy that was never archived is the case that would
    otherwise be SILENT: nothing to move, no error, no output. It returns
    `restored=False` with a reason naming the strategy and the fact that no
    archive existed, so an operator who typed the wrong id learns it.
    """

    strategy_id: str
    restored: tuple[PairKey, ...]
    reason: str

    @property
    def rehydrated(self) -> bool:
        """Whether any archived row returned to the live table."""
        return bool(self.restored)


@runtime_checkable
class ScoreStorePort(Protocol):
    """The seam the Scoring process holds the store behind.

    Stated here, next to the only implementation, so a consumer (the Scoring
    process in `nixscore/process.py`) can be built and tested against a fake
    without importing a disk. Every verb the process needs is on this Protocol
    and nothing else is: the process never sees the document, the path, or the
    temp file.
    """

    def get(self, strategy_id: str, symbol: str) -> ScoreRecord | None:
        """The LIVE record for one pair, or None."""

    def record(
        self,
        strategy_id: str,
        symbol: str,
        realized_ema: float,
        days_observed: int,
        *,
        now: float | None = None,
    ) -> ScoreRecord:
        """Upsert one pair's EMA. Durable before this returns."""

    def presence(self, strategy_id: str, symbol: str) -> Presence:
        """LIVE / ARCHIVED / ABSENT for one pair."""

    def live_pairs(self) -> tuple[PairKey, ...]:
        """Every pair in the live table, sorted."""

    def archived_pairs(self, strategy_id: str | None = None) -> tuple[PairKey, ...]:
        """Every archived pair, optionally for one strategy, sorted."""

    def archive_strategy(
        self, strategy_id: str, reason: str, *, now: float | None = None
    ) -> ArchiveOutcome:
        """§4:279 — move exactly this strategy's rows out of the live table."""

    def restore_strategy(
        self, strategy_id: str, operator: str, *, now: float | None = None
    ) -> RestoreOutcome:
        """§12.11 verb 3 — return this strategy's archived rows to the live table."""

    def snapshot(self, span_days: int) -> RankingSnapshot:
        """The LIVE table as a publishable §6.6 snapshot, ranks re-derived."""


def _decode_rows(raw: Any, where: str) -> dict[PairKey, ScoreRecord]:
    """One `{wire_key: record}` object off disk, keyed back to pairs."""
    if not isinstance(raw, Mapping):
        raise ScoreStoreError(f"{_SITE}: {where} is not an object: {raw!r}")
    out: dict[PairKey, ScoreRecord] = {}
    for value in raw.values():
        record = ScoreRecord.from_wire(value if isinstance(value, Mapping) else {})
        out[record.key] = record
    return out


def _encode_rows(rows: Mapping[PairKey, ScoreRecord]) -> dict[str, Any]:
    """`{pair: record}` as the on-disk `{wire_key: record}` object."""
    return {wire_key(key): row.as_wire() for key, row in sorted(rows.items())}


@dataclasses.dataclass(frozen=True, slots=True)
class _Archive:
    """One strategy's archived rows, plus when and why they were archived."""

    rows: dict[PairKey, ScoreRecord]
    archived_at: float
    reason: str


class ScoreStore:
    """The durable §6.6 table. One file, whole-document atomic writes.

    Not thread-safe and deliberately not lock-protected: §6.6:459 makes the
    Scoring process the SOLE WRITER, and a lock here would be the beginning of
    the multi-writer surface §12.7 refuses. Concurrent READERS are safe by
    construction — `os.replace` never exposes a partial document.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        """Open (or adopt) the store at `path`. Reads; never writes.

        An open that wrote would destroy the evidence the survival gate needs:
        the question *"did the row outlive the process?"* cannot be asked of a
        store that resets itself the moment the next process looks at it.
        """
        self.path = Path(path)
        self._live: dict[PairKey, ScoreRecord] = {}
        self._archived: dict[str, _Archive] = {}
        self._revision = 0
        self._load()

    # -- reads ---------------------------------------------------------------

    @property
    def revision(self) -> int:
        """Durable-write counter. Monotonic, persisted, never reset by a reopen.

        A store that cannot say how many times it has been written cannot
        distinguish "the writer died before doing anything" from "the writer did
        the work and it vanished" — which is precisely the difference the
        atomicity arm of `check_scoring_lifecycle` measures.
        """
        return self._revision

    def get(self, strategy_id: str, symbol: str) -> ScoreRecord | None:
        """The LIVE record for one pair, or None. Archived rows are NOT live."""
        return self._live.get((strategy_id, symbol))

    def presence(self, strategy_id: str, symbol: str) -> Presence:
        """LIVE / ARCHIVED / ABSENT. The only read that crosses the boundary."""
        key = (strategy_id, symbol)
        if key in self._live:
            return Presence.LIVE
        archive = self._archived.get(strategy_id)
        if archive is not None and key in archive.rows:
            return Presence.ARCHIVED
        return Presence.ABSENT

    def live_pairs(self) -> tuple[PairKey, ...]:
        """Every pair in the live table, sorted for a stable set comparison."""
        return tuple(sorted(self._live))

    def archived_pairs(self, strategy_id: str | None = None) -> tuple[PairKey, ...]:
        """Every archived pair, optionally narrowed to one strategy. Sorted."""
        if strategy_id is not None:
            archive = self._archived.get(strategy_id)
            return tuple(sorted(archive.rows)) if archive is not None else ()
        found: list[PairKey] = []
        for archive in self._archived.values():
            found.extend(archive.rows)
        return tuple(sorted(found))

    def archived_record(self, strategy_id: str, symbol: str) -> ScoreRecord | None:
        """The ARCHIVED record for one pair, or None. §6.6's *not destroyed*."""
        archive = self._archived.get(strategy_id)
        if archive is None:
            return None
        return archive.rows.get((strategy_id, symbol))

    def archive_reason(self, strategy_id: str) -> str:
        """Why this strategy's rows were archived, or `''` if they were not."""
        archive = self._archived.get(strategy_id)
        return archive.reason if archive is not None else ""

    def snapshot(self, span_days: int) -> RankingSnapshot:
        """The LIVE table as a publishable §6.6 snapshot. Ranks re-derived here.

        Archived rows are excluded by construction — §4:279 removes a
        quarantined strategy from the live ranking table *"so it can no longer
        win a contention tiebreak for capital it can't use"*, and a snapshot
        that carried them would hand the Limiter exactly that.
        """
        ema = {key: row.realized_ema for key, row in self._live.items()}
        observed = {key: row.days_observed for key, row in self._live.items()}
        return RankingSnapshot(rows=rank_rows(ema, observed), span_days=int(span_days))

    # -- the write path ------------------------------------------------------

    def record(
        self,
        strategy_id: str,
        symbol: str,
        realized_ema: float,
        days_observed: int,
        *,
        now: float | None = None,
    ) -> ScoreRecord:
        """Upsert one pair's realized-P&L EMA. Durable before this returns.

        Writing a pair whose strategy is currently ARCHIVED is a refusal, not an
        overwrite: §4:279 has removed that strategy from the live table, so a
        write that quietly re-created a live row would resurrect a quarantined
        strategy without the §12.11 verb that is the only way back.
        """
        if strategy_id in self._archived:
            raise ScoreStoreError(
                f"{_SITE}: refusing to write a live row for {strategy_id!r} — its "
                f"rows are ARCHIVED (§4:279). The only way back to the live table "
                f"is the §12.11 'quarantine-restore' verb, and a silent upsert "
                f"here would be an un-audited resurrection"
            )
        stamp = time.time() if now is None else float(now)
        row = ScoreRecord(
            strategy_id=strategy_id,
            symbol=symbol,
            realized_ema=float(realized_ema),
            days_observed=int(days_observed),
            updated_at=stamp,
        )
        live = dict(self._live)
        live[row.key] = row
        self._commit(live, self._archived)
        return row

    def archive_strategy(
        self, strategy_id: str, reason: str, *, now: float | None = None
    ) -> ArchiveOutcome:
        """§4:279 — move EXACTLY this strategy's rows out of the live table.

        "Exactly" is the whole property, and it is one line: the rows selected
        are those whose OWN `strategy_id` matches. Every other pair — including
        one keyed to a different strategy on the SAME symbol — is untouched, and
        the outcome names both sets so a caller can assert on the untouched half
        rather than only on the moved one.

        ATOMIC: the move is committed as one whole-document `os.replace`, so a
        kill at any instant leaves every row on exactly one side. There is no
        window in which a row is in neither place.
        """
        stamp = time.time() if now is None else float(now)
        moving = {k: v for k, v in self._live.items() if k[0] == strategy_id}
        staying = {k: v for k, v in self._live.items() if k[0] != strategy_id}
        existing = self._archived.get(strategy_id)
        merged = dict(existing.rows) if existing is not None else {}
        merged.update(moving)
        archived = dict(self._archived)
        if merged:
            archived[strategy_id] = _Archive(
                rows=merged, archived_at=stamp, reason=reason
            )
        self._commit(staying, archived)
        return ArchiveOutcome(
            strategy_id=strategy_id,
            archived=tuple(sorted(moving)),
            untouched=tuple(sorted(staying)),
            reason=(
                f"{_SITE}: archived {len(moving)} row(s) for {strategy_id!r} "
                f"({sorted(moving)}); {len(staying)} row(s) belonging to other "
                f"strategies were untouched ({sorted(staying)}). §4:279 — removed "
                f"from the LIVE ranking table, archived not destroyed. Cause: "
                f"{reason}"
            ),
        )

    def restore_strategy(
        self, strategy_id: str, operator: str, *, now: float | None = None
    ) -> RestoreOutcome:
        """§12.11 verb 3's score half — archived rows return to the live table.

        The values returned are the values archived, byte for byte: the archive
        holds the records themselves, so a restore is a move and not a
        recomputation. §4:280 — *recoverable if the operator deliberately brings
        it back.*

        A strategy that was never archived is NOT an error and NOT silent: the
        outcome says `restored=False` and names the strategy, so a mistyped id is
        visible to the operator who typed it.
        """
        archive = self._archived.get(strategy_id)
        if archive is None:
            return RestoreOutcome(
                strategy_id=strategy_id,
                restored=(),
                reason=(
                    f"{_SITE}: '{operator}' asked to restore {strategy_id!r}, which "
                    f"has NO archived rows — nothing returned to the live table. "
                    f"Known archives: {sorted(self._archived)}"
                ),
            )
        archived = {k: v for k, v in self._archived.items() if k != strategy_id}
        live = dict(self._live)
        collisions = sorted(set(live) & set(archive.rows))
        if collisions:
            raise ScoreStoreError(
                f"{_SITE}: cannot restore {strategy_id!r} — {collisions} already "
                f"exist in the LIVE table. An archived pair and a live pair of the "
                f"same key means the archive boundary was crossed by something "
                f"other than these two verbs"
            )
        live.update(archive.rows)
        self._commit(live, archived)
        return RestoreOutcome(
            strategy_id=strategy_id,
            restored=tuple(sorted(archive.rows)),
            reason=(
                f"{_SITE}: '{operator}' restored {len(archive.rows)} archived row(s) "
                f"for {strategy_id!r} ({sorted(archive.rows)}) to the live table at "
                f"{time.time() if now is None else float(now)!r}; they were archived "
                f"at {archive.archived_at!r} because: {archive.reason}"
            ),
        )

    # -- durability ----------------------------------------------------------

    def _document(
        self,
        live: Mapping[PairKey, ScoreRecord],
        archived: Mapping[str, _Archive],
        revision: int,
    ) -> dict[str, Any]:
        """The whole store as one JSON-safe document."""
        return {
            _REV_KEY: STORE_REV,
            _REVISION_KEY: int(revision),
            _LIVE_KEY: _encode_rows(live),
            _ARCHIVED_KEY: {
                name: {
                    _AT_KEY: float(arc.archived_at),
                    _REASON_KEY: arc.reason,
                    _ROWS_KEY: _encode_rows(arc.rows),
                }
                for name, arc in sorted(archived.items())
            },
        }

    def _commit(
        self,
        live: Mapping[PairKey, ScoreRecord],
        archived: Mapping[str, _Archive],
    ) -> None:
        """Make the candidate state DURABLE, then adopt it. Never the reverse.

        Order of operations, each chosen for the failure it survives:

        1. serialise the candidate document (a raise here has changed nothing);
        2. write it to a sibling temp file, `fsync` the FILE — durable bytes, but
           under a name nobody reads;
        3. `os.replace` it over the target — atomic; readers see old or new;
        4. `fsync` the DIRECTORY, so the rename itself survives power loss (the
           reason `nixsentinel/marker.py` fsyncs the parent on file creation);
        5. only now adopt the candidate in memory.

        The temp file is a SIBLING, not `/tmp`: `os.replace` is atomic only
        within one filesystem, and a cross-device rename would degrade to a
        copy — reintroducing the torn window this whole design exists to close.
        """
        revision = self._revision + 1
        payload = json.dumps(
            self._document(live, archived, revision), sort_keys=True
        ).encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        except OSError:
            self._unlink_quietly(temp_name)
            raise
        self._fsync_parent()
        self._live = dict(live)
        self._archived = dict(archived)
        self._revision = revision

    @staticmethod
    def _unlink_quietly(name: str) -> None:
        """Drop a temp file whose write failed. Never masks the original error."""
        try:
            os.unlink(name)
        except OSError:
            pass

    def _fsync_parent(self) -> None:
        """`fsync` the containing directory so the rename itself is durable."""
        dir_fd = os.open(str(self.path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    # -- loading -------------------------------------------------------------

    def _load(self) -> None:
        """Read the document, or leave the store empty if there is no file yet.

        Every other failure is LOUD. A truncated, unparseable or
        newer-revision document raises `ScoreStoreError`: reading it as empty
        would book every strategy back to cold start, which is §4:276's phantom
        zero arriving through the back door.
        """
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ScoreStoreError(f"{_SITE}: cannot read {self.path}: {exc!r}") from exc
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScoreStoreError(
                f"{_SITE}: {self.path} is not readable JSON ({len(raw)} byte(s)): "
                f"{exc!r} — a store that cannot be read is NOT an empty store"
            ) from exc
        if not isinstance(doc, Mapping):
            raise ScoreStoreError(f"{_SITE}: {self.path} is not a JSON object")
        found = str(doc.get(_REV_KEY, ""))
        if found != STORE_REV:
            raise ScoreStoreError(
                f"{_SITE}: {self.path} carries {_REV_KEY}={found!r}, this code "
                f"speaks {STORE_REV!r} — refusing to half-read a document shape it "
                f"does not know"
            )
        self._live = _decode_rows(doc.get(_LIVE_KEY, {}), f"{self.path}:{_LIVE_KEY}")
        self._archived = _load_archives(doc.get(_ARCHIVED_KEY, {}), str(self.path))
        self._revision = int(doc.get(_REVISION_KEY, 0))
        self._assert_disjoint()

    def _assert_disjoint(self) -> None:
        """No pair may be LIVE and ARCHIVED at once. The torn-state invariant.

        §6.6's archive is a MOVE. A pair on both sides means something wrote a
        delta instead of a whole document, and the store would answer `LIVE` for
        a row a quarantined strategy still owns.
        """
        for name, archive in self._archived.items():
            both = sorted(set(self._live) & set(archive.rows))
            if both:
                raise ScoreStoreError(
                    f"{_SITE}: {self.path} has {both} in BOTH the live table and "
                    f"{name!r}'s archive — the archive is a move, not a copy"
                )


def _load_archives(raw: Any, where: str) -> dict[str, _Archive]:
    """The `archived` object off disk, or `ScoreStoreError` naming the fault."""
    if not isinstance(raw, Mapping):
        raise ScoreStoreError(f"{_SITE}: {where}:{_ARCHIVED_KEY} is not an object")
    out: dict[str, _Archive] = {}
    for name, body in raw.items():
        if not isinstance(body, Mapping):
            raise ScoreStoreError(
                f"{_SITE}: {where}: archive {name!r} is not an object"
            )
        rows = _decode_rows(body.get(_ROWS_KEY, {}), f"{where}: archive {name!r}")
        foreign = sorted(key for key in rows if key[0] != str(name))
        if foreign:
            raise ScoreStoreError(
                f"{_SITE}: {where}: archive {name!r} holds {foreign}, which belong "
                f"to other strategies — an archive must hold EXACTLY its own "
                f"strategy's rows (§6.6)"
            )
        out[str(name)] = _Archive(
            rows=rows,
            archived_at=float(body.get(_AT_KEY, 0.0)),
            reason=str(body.get(_REASON_KEY, "")),
        )
    return out
