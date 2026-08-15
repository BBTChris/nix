"""The Allocator's PRIVATE read-only mirror of the Limiter's financial picture.

ARC 031 / Stage 1 (sub-agent A). Authority:
`docs/nics_risk_subsystem_spec_v1.3.md` §2 (component model / authority split —
the Allocator is **permissive**), §3 (*FULL FINANCIAL-PICTURE PUBLISH* and its
**ATOMICITY RULE**), §6.4 (live per-symbol margin folded into the one unified
snapshot, one writer, one version stamp), §6.4b (hybrid balance refresh and the
**MONOTONIC-BY-SOURCE guard**, *per key*), §12.7 (state-table transport, LOCKED
v1.3 — ZeroMQ PUB/SUB + snapshot-on-subscribe, mirror model), §16 U2/U3.

The types are the FROZEN `scripts/nixalloc/seam.py`; nothing here re-declares
one. The wire codec is `scripts/nixrisk/picture.py`'s, imported rather than
restated — one definition of one wire contract (§6.4: *"identical bytes by
construction"*).

---

## THE AUTHORITY LINE THIS MODULE IS NOT ALLOWED TO CROSS (§2)

The Allocator *reads and proposes*. It never gates, never reserves, never
places, and never writes canonical state. Two consequences are structural here
rather than remembered:

1. **This module never builds a `FinancialPicture`.** Every picture it holds
   arrived whole, from the Limiter, through `decode_picture`. There is no code
   path below that constructs one, merges two, or patches a field of one — and
   the merge is the tempting one: when a reading regresses on a single key
   (§6.4b), the obvious repair is "keep the good key from the held picture and
   take the rest from the new one". That repair makes the Allocator a **second
   maintainer of the financial picture**, holding a snapshot no version stamp
   ever covered and that the Limiter's event log has no record of. So a
   regression on ANY key discards the WHOLE reading and the held picture stands
   (`_regression`). It costs freshness on the other keys and it costs nothing
   that §6.4b protects: nothing regresses, and the age of what is held is
   already measured — that is what `STALE` is for.
2. **Nothing can push a picture INTO this object.** `AllocatorMirror` has no
   verb that accepts a picture; it PULLS from a `SnapshotFeedPort`. That is why
   `refresh()` takes a timeout and not a snapshot.

## §0i — STALE UNTIL PROVEN FRESH, in four states and not two

The default cell is EMPTY, and `MirrorState` separates EMPTY from PARTIAL for
the reason ARC 027 measured on the publisher's side (`XPUB_VERBOSE`): **a missed
snapshot looks exactly like a quiet, healthy feed.** From the consumer's seat
those are three distinguishable facts and this module keeps them distinguished:

* **EMPTY** — nothing has ever arrived from the publisher. `heard` is False.
* **PARTIAL** — traffic arrived and no complete, stamped, self-consistent
  snapshot has landed yet (a delta-only mirror, an unstamped picture, a picture
  that disagrees with itself, a picture whose containers are writable).
* **FRESH** — a complete snapshot is held and its `published_ts` is inside the
  ceiling. *This is also the state a QUIET publisher leaves behind*, which is
  the point: quiet-and-current is a legitimate state and is not the same fact
  as never-heard-from.
* **STALE** — held once, now past the ceiling. §6.4's rule for a stale cache is
  refuse, never "carry on with the last value".

Only FRESH is `sizeable` (the seam's single predicate), so all three refusals
fast-drop identically. Telling them apart is what makes the alert actionable.

---

## §6.4b's MONOTONIC-BY-SOURCE GUARD, AND WHAT THE PUBLISHED SNAPSHOT DOES NOT
## CARRY — MEASURED, NOT ASSUMED

§6.4b requires *every* venue-sourced reading to carry the venue's own
timestamp/sequence, and the guard to be **per key** so *"a late update on one
key can never regress another"*.

**The published financial picture in this tree carries no such stamps.**
`nixalloc.seam.MIRRORED_FIELDS` pins nine fields at `SEAM_REV 1.0.0` — `version,
published_ts, balance, positions, margin_per_contract, sum_open_margin,
sum_reservations, committed, deployable` — and `published_ts` is the *Limiter's*
clock (`nixrisk.picture.FinancialPictureBook._build` stamps it with its own
`clock()`), not a venue stamp. So §6.4b's per-key guard is **not expressible
over the published snapshot alone**, and that gap is CHECK-DEBT D3.121, owned by
ARC 032. It is a gap in the WIRE, not in the rule.

This module therefore takes the stamps as a field that rides BESIDE the picture
(`MirrorUpdate.source_stamps`, wire key `source_stamps`), keyed as `balance`,
`margin:<symbol>`, `position:<trade_id>` — §6.4b's own three key classes. And
when a reading arrives with **no** stamps at all, the fallback is neither
"trust it" nor "refuse everything":

    every key is stamped with the picture's own `published_ts`.

That degenerates the per-key guard to a whole-snapshot recency guard, which is
strictly stronger than nothing and exactly as strong as the information
available. It is COUNTED (`degraded_source_stamps`) rather than logged as prose,
because a guard that quietly weakens itself is the defect §6.4b exists to
prevent, one layer up.

## Boundary against the gates that already exist (§5.5, doctrine C.9)

* `checks/check_state_bus.py` owns `nixbus/statebus.py` — whether the transport
  delivers, answers a subscription with a snapshot, and stamps freshness.
* `checks/check_picture_atomicity.py` owns `nixrisk/picture.py` — whether the
  Limiter's snapshot is atomic under a real race at the PUBLISHER.
* `checks/check_allocator_mirror.py` owns THIS file — whether the CONSUMER's
  private mirror is atomic under a real race at the reader, refuses a half-built
  snapshot, discards an older reading per key, and cannot be written.

None re-measures another: this module would still fail on a torn consumer over a
perfect bus and a perfect publisher, and `nixrisk.picture.PictureMirror` (the
Limiter-package mirror, which has no `MirrorState`, no per-key guard and no
`MirrorPort`) is a different object with a different job and is not this.

## What this module is NOT

It does not size (§7 — sub-agent B), does not cap (§7 correlation buckets — sub-
agent C), does not arbitrate contention (§6.6 — the Scoring process is R5 and
does not exist), and does not read the tradability cache (§16 U1). A green here
covers none of them.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from nixrisk.picture import (
    SPEC_DEPLOYABLE_FRACTION,
    TOPIC,
    PictureError,
    decode_picture,
    picture_defects,
)

from nixalloc.seam import (
    FinancialPicture,
    MirrorSnapshot,
    MirrorState,
)

# pylint: disable=too-few-public-methods
# `SnapshotFeedPort` is a one-verb Protocol — a DECLARATION with exactly the
# surface §12.7's consumer side has. A second verb invented to satisfy a
# class-shape heuristic would be authority granted (§2), the same reasoning
# `nixalloc/seam.py` and `nixrisk/picture.py` both record for their own ports.

__all__ = [
    "BALANCE_KEY",
    "NO_VERSION",
    "SOURCE_STAMPS_FIELD",
    "AllocatorMirror",
    "MirrorUpdate",
    "MirrorUsageError",
    "SnapshotFeedPort",
    "StateBusFeed",
    "margin_key",
    "position_key",
]

#: `MirrorPort.version()` promises a NEGATIVE value when nothing is held —
#: zero is a plausible first version and a caller comparing `version() == 0`
#: would read "never received" as "received version 0" (seam, `MirrorPort`).
NO_VERSION: Final[int] = -1

#: §6.4b's three key classes, spelled once. `balance` is a scalar so its key is
#: a literal; margin is per SYMBOL and position is per INSTRUMENT (here the
#: `trade_id` §3 keys the position table by), exactly as §6.4b names them.
BALANCE_KEY: Final[str] = "balance"

#: The wire field carrying §6.4b's per-key venue stamps, if the publisher has
#: any. **No leading underscore, and that is not cosmetic:** `statebus._decode`
#: strips every `_`-prefixed key out of the payload before a mirror sees it, so
#: `_source_stamps` would arrive as silence. `nixrisk.picture.WIRE_SCHEMA`
#: records the same lesson, found the same way.
SOURCE_STAMPS_FIELD: Final[str] = "source_stamps"

_SITE: Final[str] = "scripts/nixalloc/mirror.py:AllocatorMirror"


def margin_key(symbol: str) -> str:
    """§6.4b's per-SYMBOL margin key."""
    return f"margin:{symbol}"


def position_key(trade_id: str) -> str:
    """§6.4b's per-INSTRUMENT position key, on §3's `trade_id`."""
    return f"position:{trade_id}"


class MirrorUsageError(RuntimeError):
    """The mirror was constructed or driven wrongly. Always says what and why."""


# ---------------------------------------------------------------------------
# What a feed OFFERS the mirror
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MirrorUpdate:
    """One reading OFFERED to the mirror. The mirror decides whether to hold it.

    `heard` is separate from `complete` because §12.7's hazard is that the two
    look the same from outside: a subscriber that missed its snapshot and a
    subscriber whose publisher is quiet both have `complete=False` and no
    picture, and only `heard` distinguishes "nothing has EVER arrived" from
    "something arrived and it was not enough".
    """

    picture: FinancialPicture | None = None
    heard: bool = False
    complete: bool = False
    source_stamps: Mapping[str, float] = MappingProxyType({})
    note: str = ""


@runtime_checkable
class SnapshotFeedPort(Protocol):
    """Where readings come FROM. The mirror pulls; nothing pushes (§2).

    Injectable so the mirror's rules can be driven deterministically without a
    live broker — and `StateBusFeed` below is the §12.7 implementation, so the
    same rules are exercised over a real `ipc://` socket too. A rule proven only
    against a fake transport has not been proven.
    """

    def read(self, timeout_ms: int) -> MirrorUpdate:
        """The best reading available within the budget. SYNCHRONOUS (seam)."""


@dataclasses.dataclass(frozen=True)
class _Cell:
    """The mirror's ENTIRE mutable state, as ONE immutable object.

    This is the atomicity mechanism and it is the same one
    `nixrisk.picture.FinancialPictureBook` uses on the writer's side: there is
    no `self._picture` beside a `self._stamps`, there is `self._cell`, and an
    update REBINDS that one name to a wholly-built replacement. A reader does
    one attribute load and walks away holding a self-consistent set. There is no
    instant at which the picture and the stamps that admitted it live in two
    places a reader could visit separately.
    """

    picture: FinancialPicture | None
    stamps: Mapping[str, float]
    heard: bool
    reason: str


_EMPTY_CELL: Final[_Cell] = _Cell(
    picture=None,
    stamps=MappingProxyType({}),
    heard=False,
    reason="no snapshot has been received",
)


def _writable(container: Any) -> bool:
    """Does this container's TYPE admit item assignment?

    A structural test and never a probe write: the only way to *attempt* a write
    on the publisher's own mapping is to perform one, and a mirror that mutates
    the object it is judging has committed the §2 violation it was checking for.

    The residual, stated: a mapping that defines `__setitem__` and raises would
    be refused here as writable when it is not. That is the fail-closed
    direction — a refusal costs one sizing pass, and holding a mirror the
    Allocator could write is a canonical-state write that appears in no event
    log (§9).
    """
    return hasattr(type(container), "__setitem__")


def _keys_of(picture: FinancialPicture) -> tuple[str, ...]:
    """§6.4b's key set for one picture: balance, per symbol, per instrument."""
    keys = [BALANCE_KEY]
    keys.extend(margin_key(symbol) for symbol in picture.margin_per_contract)
    keys.extend(position_key(row.trade_id) for row in picture.positions)
    return tuple(keys)


# ---------------------------------------------------------------------------
# The mirror (§3, §12.7, §0i) — satisfies `nixalloc.seam.MirrorPort`
# ---------------------------------------------------------------------------


class AllocatorMirror:  # pylint: disable=too-many-instance-attributes
    """The Allocator's private read-only copy. Satisfies `MirrorPort`.

    Five of its nine attributes are COUNTERS — `polls`, `applied`,
    `discarded_older`, `refused_incoherent`, `degraded_source_stamps` — and they
    exist for the reason `StatePublisher`'s four and `FinancialPictureBook`'s
    three do: a mirror that cannot say what it accepted and what it threw away
    cannot be measured, only believed. `discarded_older` in particular is the
    only externally visible evidence that §6.4b's guard ever fired.
    """

    def __init__(
        self,
        feed: SnapshotFeedPort,
        *,
        max_age_s: float,
        fraction: float = SPEC_DEPLOYABLE_FRACTION,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_age_s <= 0.0:
            raise MirrorUsageError(
                f"max_age_s must be positive, got {max_age_s!r} — §12.7's "
                "freshness ceiling is a §12A tunable and this class takes no "
                "default, for the same reason FinancialPictureBook takes no "
                "default deployable fraction: a ceiling with a default is a "
                "ceiling nobody chose"
            )
        self._feed = feed
        self._max_age_s = float(max_age_s)
        self._fraction = float(fraction)
        self._clock = clock
        #: THE single mutable name. Nothing else in this object is rebound by
        #: an update, and that is what makes a torn read impossible.
        self._cell: _Cell = _EMPTY_CELL
        self.polls = 0
        self.applied = 0
        self.discarded_older = 0
        self.refused_incoherent = 0
        self.degraded_source_stamps = 0
        #: The most recent refusal that did NOT change the held picture. A
        #: diagnostic, deliberately outside `_cell`: a bad new reading must not
        #: be able to disturb a good held one, not even its reason string.
        self.last_refusal = ""

    # -- MirrorPort -------------------------------------------------------

    def snapshot(self) -> MirrorSnapshot:
        """The current mirror state. SYNCHRONOUS, O(1), ONE attribute load.

        The single `self._cell` load below is the whole atomicity story on the
        consumer side. Everything after it is a pure function of the object that
        load returned, so a publish landing mid-read cannot be observed as a
        half-applied snapshot: the reader is already holding the old cell whole.
        """
        cell = self._cell  # <- THE single load. Atomicity lives here.
        if cell.picture is None:
            state = MirrorState.PARTIAL if cell.heard else MirrorState.EMPTY
            return MirrorSnapshot(state=state, picture=None, reason=cell.reason)
        age = self._clock() - cell.picture.published_ts
        if age > self._max_age_s:
            return MirrorSnapshot(
                state=MirrorState.STALE,
                picture=cell.picture,
                reason=(
                    f"{_SITE}: held picture version {cell.picture.version} is "
                    f"{age:.6f}s old, past the {self._max_age_s:.6f}s ceiling — "
                    "§6.4's rule for a stale cache is refuse, never carry on "
                    "with the last value"
                ),
            )
        return MirrorSnapshot(
            state=MirrorState.FRESH,
            picture=cell.picture,
            reason=(
                f"{_SITE}: picture version {cell.picture.version}, age "
                f"{age:.6f}s, inside the {self._max_age_s:.6f}s ceiling"
            ),
        )

    def version(self) -> int:
        """The stamp on the held snapshot, or `NO_VERSION` when there is none."""
        cell = self._cell  # <- the same single load, same reason
        return NO_VERSION if cell.picture is None else cell.picture.version

    # -- the ingest side. NOTE: it takes no picture (§2) -------------------

    def refresh(self, timeout_ms: int = 0) -> MirrorSnapshot:
        """PULL one reading from the feed, judge it, return the resulting state.

        Takes a timeout and NOT a picture. There is deliberately no verb on this
        object through which a caller can hand it a financial picture: §2's
        authority split is that the Limiter publishes and the Allocator reads,
        and a `set_picture()` here would let any code in the Allocator process
        install a picture the Limiter never sent and no version stamp covers.
        """
        self.polls += 1
        self._offer(self._feed.read(timeout_ms))
        return self.snapshot()

    def _offer(self, update: MirrorUpdate) -> None:
        """Judge ONE reading. The only method that ever rebinds `_cell`."""
        if update.picture is None:
            self._absent(update)
            return
        refusal = self._incoherent(update.picture)
        if refusal:
            self.refused_incoherent += 1
            self._refuse(refusal, heard=True)
            return
        stamps = self._stamps_for(update.picture, update.source_stamps)
        regression = self._regression(update.picture, stamps)
        if regression:
            self.discarded_older += 1
            self._refuse(regression, heard=True)
            return
        self._accept(update.picture, stamps)

    def _absent(self, update: MirrorUpdate) -> None:
        """No picture in this reading. Quiet-and-current is NOT never-heard."""
        note = update.note or "the feed offered no picture and gave no reason"
        self._refuse(f"{_SITE}: {note}", heard=update.heard)

    def _refuse(self, why: str, *, heard: bool) -> None:
        """Record a refusal WITHOUT disturbing a held picture.

        When nothing is held the refusal IS the state (EMPTY vs PARTIAL, decided
        by `heard`). When something is held it must survive: a reading the mirror
        declined to apply says nothing about the reading it already accepted, and
        dropping the good one would turn every malformed message into an outage.
        """
        self.last_refusal = why
        if self._cell.picture is not None:
            return
        self._cell = _Cell(
            picture=None,
            stamps=self._cell.stamps,
            heard=heard or self._cell.heard,
            reason=why,
        )

    def _incoherent(self, picture: FinancialPicture) -> str:
        """Why this picture is not holdable, or `""`. §12.7's half-built rule.

        Four independent conditions, each naming its own site. The first two are
        A4's structural half — a mirror the Allocator could WRITE is not a
        read-only mirror, whatever the port declares — and the last two are
        §12.7's *"never sizes on a half-built mirror"*.
        """
        if _writable(picture.positions):
            return (
                f"{_SITE}: the position table is a {type(picture.positions).__name__}, "
                "which admits item assignment — a mirror the Allocator can write "
                "is a write to canonical state that appears in no event log (§2, §9)"
            )
        if _writable(picture.margin_per_contract):
            return (
                f"{_SITE}: margin_per_contract is a "
                f"{type(picture.margin_per_contract).__name__}, which admits item "
                "assignment — see above; §6.4 publishes it under the Limiter's own "
                "writer and version stamp, so a writable copy here is a second writer"
            )
        if picture.version <= 0:
            return (
                f"{_SITE}: picture carries version {picture.version!r} — an UNSTAMPED "
                "snapshot is half-built by §12.7's own rule, and the stamp is the only "
                "thing that makes a torn read observable from outside (§3)"
            )
        defects = picture_defects(picture, self._fraction)
        if defects:
            return (
                f"{_SITE}: mirrored picture version {picture.version} disagrees with "
                "itself, so it was never simultaneously true: " + "; ".join(defects)
            )
        return ""

    def _stamps_for(
        self, picture: FinancialPicture, offered: Mapping[str, float]
    ) -> Mapping[str, float]:
        """§6.4b's per-key venue stamps for this reading, or the degraded form.

        See the module docstring: the published snapshot carries no venue stamps
        today (D3.121), so an unstamped reading is stamped with its own
        `published_ts` for every key. That is a whole-snapshot recency guard
        rather than a per-key one — strictly stronger than nothing, strictly
        weaker than §6.4b — and it is COUNTED so the weakening is never silent.
        """
        if offered:
            return dict(offered)
        self.degraded_source_stamps += 1
        return {key: picture.published_ts for key in _keys_of(picture)}

    def _regression(
        self, picture: FinancialPicture, stamps: Mapping[str, float]
    ) -> str:
        """§6.4b: which key this reading would move BACKWARDS, or `""`.

        Two tiers, and both discard rather than merge (see the module docstring's
        authority note). The version tier catches a reading the TRANSPORT
        delivered out of order; the per-key tier catches a reading the VENUE
        sourced out of order, which is the one §6.4b names — *"ordering is by
        source-of-truth time, never by arrival time"*.
        """
        held = self._cell.picture
        if held is None:
            return ""
        if picture.version <= held.version:
            return (
                f"{_SITE}: reading carries picture version {picture.version}, not newer "
                f"than the held {held.version} — DISCARDED, not applied (§6.4b: "
                "anything older is discarded, not applied)"
            )
        for key, held_stamp in sorted(self._cell.stamps.items()):
            incoming = stamps.get(key)
            if incoming is not None and incoming < held_stamp:
                return (
                    f"{_SITE}: key {key!r} carries venue stamp {incoming!r}, OLDER than "
                    f"the held {held_stamp!r} — §6.4b discards it rather than applying "
                    "it, and the whole reading is discarded rather than merged, because "
                    "a merged picture is one the Limiter never published and no version "
                    "stamp covers (§2, §3)"
                )
        return ""

    def _accept(self, picture: FinancialPicture, stamps: Mapping[str, float]) -> None:
        """Hold this reading. ONE store, and the stamps only ever advance."""
        merged = dict(self._cell.stamps)
        for key, value in stamps.items():
            merged[key] = max(value, merged[key]) if key in merged else value
        self._cell = _Cell(
            picture=picture,
            stamps=MappingProxyType(merged),
            heard=True,
            reason="",
        )
        self.applied += 1


# ---------------------------------------------------------------------------
# §12.7's REAL transport, adapted to the feed port
# ---------------------------------------------------------------------------


class StateBusFeed:
    """`nixbus.statebus.StateSubscriber` -> `MirrorUpdate`. A thin adapter.

    Deliberately thin: every RULE lives in `AllocatorMirror`, so the rules the
    unit drives deterministically are the same objects the socket path drives.
    An adapter that decided anything would be a second place the staleness rule
    lives, and the two would drift.

    It takes the subscriber rather than an endpoint so this module never opens a
    socket of its own and never imports `zmq` — which is what lets the mirror be
    driven with no ZeroMQ present at all, while the transport arm of
    `check_allocator_mirror` still drives it over a real `ipc://` endpoint.
    """

    def __init__(self, subscriber: Any, *, topic: str = TOPIC) -> None:
        self._subscriber = subscriber
        self.topic = topic

    def read(self, timeout_ms: int) -> MirrorUpdate:
        """Drain the socket and report what the private mirror now holds."""
        self._subscriber.drain(timeout_ms)
        mirror = self._subscriber.mirror
        heard = bool(getattr(self._subscriber, "bytes_received", 0))
        if not mirror.complete:
            return MirrorUpdate(
                heard=heard,
                complete=False,
                note=(
                    f"no snapshot yet for {mirror.missing} — §12.7 treats an "
                    "incomplete mirror as stale until the snapshot lands, and a "
                    "delta alone never completes it"
                ),
            )
        table = mirror.table(self.topic)
        try:
            picture = decode_picture(table)
        except PictureError as exc:
            return MirrorUpdate(
                heard=True,
                complete=True,
                note=f"undecodable financial picture on {self.topic!r}: {exc}",
            )
        stamps, bad = _read_stamps(table)
        if bad:
            return MirrorUpdate(
                heard=True,
                complete=True,
                note=(
                    f"{SOURCE_STAMPS_FIELD} carried an unreadable entry ({bad}) — "
                    "§6.4b orders by source-of-truth time, so a stamp that cannot be "
                    "read is refused rather than treated as absent"
                ),
            )
        return MirrorUpdate(
            picture=picture, heard=True, complete=True, source_stamps=stamps
        )


def _read_stamps(table: Mapping[str, Any]) -> tuple[Mapping[str, float], str]:
    """`(stamps, first unreadable entry)`. An empty mapping means "none sent"."""
    raw = table.get(SOURCE_STAMPS_FIELD)
    if raw is None:
        return MappingProxyType({}), ""
    if not isinstance(raw, Mapping):
        return MappingProxyType({}), f"{SOURCE_STAMPS_FIELD} is {type(raw).__name__}"
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except TypeError, ValueError:
            return MappingProxyType({}), f"{key!r} -> {value!r}"
    return MappingProxyType(out), ""
