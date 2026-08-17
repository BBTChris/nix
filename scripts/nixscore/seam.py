"""The §6.6 Scoring seam, frozen ARC 036 Phase 0.4.

## What is on each side

**Scoring (this side of the seam, shared pool, Core 4–5)** is the **sole
writer** of a ranking table: one row per `(strategy_id, symbol)` pair carrying
that pair's **realized-P&L EMA** and its rank. It is the only thing in the
system that computes a score.

**The Allocator and the Limiter (the other side)** hold a **private read-only
mirror** and do an **O(1) lookup** on it. §6.6: *"Nobody but the Scoring process
COMPUTES the score. Reading a precomputed rank to break a tie is enforcement
and is legitimate for the Limiter; computing the EMA / defining 'productive' is
the allocation judgment that stays out of the gate."*

## THE TRANSPORT IS §12.7's MIRROR MODEL, NOT SHARED MEMORY — and §6.6 reads
## the other way, so this is stated rather than assumed

§6.6:459 says the Scoring process is sole writer of a ranking table *"in shared
memory"*. §12.7 is LOCKED, is later, and **names this exact table**:

> **Standard mechanism for ALL state tables** (financial picture §3, **ranking
> table §6.6**, tradability, margin/calendar caches): **ZeroMQ plain PUB/SUB +
> snapshot-on-subscribe, mirror model.**
> **Mirror model, NOT raw shared memory.** … Raw shared state tables would let
> multiple processes touch the same bytes — reintroducing locks, races, and
> torn reads, and reducing the single-writer principle to fiction.

and enumerates its **sole exception** as the per-tick price firehose (§10),
*"prices only, never financial state"*. A ranking table is financial state, so
it is not the exception. §12.7 governs; §6.6's phrase is the earlier spelling.

This matters practically and not only textually: the arc brief that
commissioned this module asked for a *"shared-memory sole-writer publish"*, and
building that would have re-introduced the multi-writer surface §12.7 refuses —
while still passing a sole-writer test, because a single writer is exactly what
the shared-memory design also claims. The hazard was stated backwards; the
mechanism below is the one the frozen spec locks.

Concretely: this seam carries **no bytes of its own**. It rides
`nixbus.statebus`, which already implements §12.7's publisher/subscriber/mirror
with snapshot-on-subscribe and per-topic sequencing (doctrine C.9 — extend the
instrument that owns the property, never build a second).

## THE FALLBACK IS THE SAFETY-RELEVANT HALF

§6.6, locked: *"if the Scoring process is down or its table is stale, both
Allocator and Limiter fall back to first-come-first-served … Ranking is an
optimization, never a safety gate: a scoring outage must NEVER halt order
flow."*

So `RankingMirror.arbitrate` has exactly two outcomes and **neither of them is
"wait"**. It cannot raise, cannot block, and cannot return "unknown": every
path that is not a ranked comparison returns `FCFS` with the reason named. The
FCFS winner is the **earlier arrival**, which is first-come-first-served spelled
out — deterministic, structurally neutral (it favours no symbol), and needing
no computation at the instant a process just died.

The five FCFS triggers, each with its own reason string so a caller can say
WHICH one fired rather than only that the fallback ran (check contract §18):

  1. no snapshot has arrived (mirror incomplete — §12.7's fast-drop condition)
  2. the table is stale past `stale_after_s`
  3. either contender's pair-row is absent (cold start, no history — §6.6)
  4. the two rows carry equal EMAs (§6.6: *"Equal or absent scores ⇒ FCFS"*)
  5. the snapshot was published by an identity that is not the Scoring process

## Sync/async per verb

* `RankingPublisher.publish` — **async** (fire-and-forget PUB). The writer never
  waits on a consumer; a blocked dashboard cannot stall Scoring.
* `RankingPublisher.service` — **sync**, and is what serves snapshot-on-subscribe.
* `RankingMirror.apply` — **sync**, local, fed only from the subscriber socket.
* `RankingMirror.lookup` / `arbitrate` — **sync, O(1), hot path**, no I/O, no
  arithmetic beyond one comparison of two precomputed floats.

## What this module deliberately does NOT contain

Any EMA arithmetic. The span, the daily-advance reduction and the smoothing all
live on the Scoring side behind `publish`. A reader that computes is the §11
hot-path violation, and `checks/check_scoring_seam.py` is what reddens on it.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from nixbus.statebus import StateMessage

#: Bumped whenever the ROW SHAPE or the arbitration contract changes, so a
#: consumer built against an older seam is a version mismatch rather than a
#: silent misread. Frozen at 1.0.0 by ARC 036 Phase 0.4.
SEAM_REV = "1.0.0"

#: The §12.7 topic this table publishes under.
RANKING_TOPIC = "ranking"

#: The one identity permitted to have written a snapshot of this table. §6.6:
#: *"A dedicated Scoring process … is the sole writer."* Carried IN the payload
#: so the sole-writer property is checked at the consumer, where a foreign
#: publisher would actually land, rather than asserted at the publisher, where
#: the impostor would never look.
SCORING_WRITER_IDENTITY = "scoring"

#: Wire keys. Named once; the encoders and decoders below both read these.
_ROWS_KEY = "rows"
_WRITER_KEY = "writer_identity"
_SPAN_KEY = "span_days"
_SEAM_REV_KEY = "seam_rev"

PairKey = tuple[str, str]


class SeamError(RuntimeError):
    """A malformed ranking payload. Never raised on the arbitration path."""


@dataclasses.dataclass(frozen=True, slots=True)
class RankRow:
    """One `(strategy_id, symbol)` pair's standing. §6.6's locked keying.

    `realized_ema` is **realized P&L per day, EMA-smoothed** — closed trades
    only. §6.6: *"Unrealized/paper gains never steer capital (a green open
    position can reverse before it closes)."*

    `days_observed` is carried because §6.6's own caution is that early realized
    samples are thin; a consumer that wants to know how much history stands
    behind a rank can read it instead of guessing. Nothing on the hot path
    branches on it — that would be policy, and policy here is the Allocator's.
    """

    strategy_id: str
    symbol: str
    realized_ema: float
    rank: int
    days_observed: int

    @property
    def key(self) -> PairKey:
        """The `(strategy_id, symbol)` pair this row is keyed on (§6.6)."""
        return (self.strategy_id, self.symbol)

    def as_wire(self) -> dict[str, Any]:
        """This row as JSON-safe scalars."""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "realized_ema": float(self.realized_ema),
            "rank": int(self.rank),
            "days_observed": int(self.days_observed),
        }

    @classmethod
    def from_wire(cls, raw: Mapping[str, Any]) -> RankRow:
        """One row off the wire, or `SeamError` naming the malformed field."""
        try:
            return cls(
                strategy_id=str(raw["strategy_id"]),
                symbol=str(raw["symbol"]),
                realized_ema=float(raw["realized_ema"]),
                rank=int(raw["rank"]),
                days_observed=int(raw["days_observed"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SeamError(f"malformed rank row {raw!r}: {exc!r}") from exc


def wire_key(key: PairKey) -> str:
    """`(strategy, symbol)` as one JSON object key.

    The separator is a NUL, which cannot occur in either component and so
    cannot be produced by a strategy id or a symbol that happens to contain the
    delimiter — the failure mode a `:` or a `/` would have.
    """
    strategy_id, symbol = key
    if "\0" in strategy_id or "\0" in symbol:
        raise SeamError(f"NUL in pair key {key!r}")
    return f"{strategy_id}\0{symbol}"


def parse_key(raw: str) -> PairKey:
    """The inverse of `wire_key`. Raises `SeamError` on an unsplittable key."""
    strategy_id, sep, symbol = raw.partition("\0")
    if not sep:
        raise SeamError(f"un-splittable pair key {raw!r}")
    return (strategy_id, symbol)


class Arbitration(StrEnum):
    """The two outcomes. There is deliberately no third."""

    RANKED = "ranked"
    FCFS = "fcfs"


@dataclasses.dataclass(frozen=True, slots=True)
class Verdict:
    """Who wins, by which route, and WHY — never an outcome without a reason.

    `winner` is always populated. FCFS is a real answer (the earlier arrival),
    not an absence of one: §6.6 requires the fallback to decide, because the
    thing it must never do is stall.
    """

    outcome: Arbitration
    winner: PairKey
    reason: str

    @property
    def fell_back(self) -> bool:
        """Whether the ranking was unavailable and FCFS decided instead."""
        return self.outcome is Arbitration.FCFS


@dataclasses.dataclass(frozen=True, slots=True)
class RankingSnapshot:
    """The whole table as one atomic value. Published; never mutated in place."""

    rows: Mapping[PairKey, RankRow]
    span_days: int
    writer_identity: str = SCORING_WRITER_IDENTITY
    seam_rev: str = SEAM_REV

    def lookup(self, key: PairKey) -> RankRow | None:
        """O(1). One dict get, no scan, no arithmetic."""
        return self.rows.get(key)

    def as_wire(self) -> dict[str, Any]:
        """The whole table as one JSON object, ready for §12.7's transport."""
        return {
            _ROWS_KEY: {wire_key(k): row.as_wire() for k, row in self.rows.items()},
            _SPAN_KEY: int(self.span_days),
            _WRITER_KEY: self.writer_identity,
            _SEAM_REV_KEY: self.seam_rev,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> RankingSnapshot:
        """One snapshot off the wire, or `SeamError` naming what was wrong."""
        raw_rows = payload.get(_ROWS_KEY)
        if not isinstance(raw_rows, Mapping):
            raise SeamError(f"ranking payload has no {_ROWS_KEY!r} object")
        rows = {
            parse_key(k): RankRow.from_wire(v)
            for k, v in raw_rows.items()
            if isinstance(v, Mapping)
        }
        if len(rows) != len(raw_rows):
            raise SeamError("ranking payload carries a non-object row")
        try:
            span = int(payload[_SPAN_KEY])
        except (KeyError, TypeError, ValueError) as exc:
            raise SeamError(f"ranking payload has no usable {_SPAN_KEY}") from exc
        return cls(
            rows=rows,
            span_days=span,
            writer_identity=str(payload.get(_WRITER_KEY, "")),
            seam_rev=str(payload.get(_SEAM_REV_KEY, "")),
        )


def rank_rows(
    realized_ema: Mapping[PairKey, float],
    days_observed: Mapping[PairKey, int] | None = None,
) -> dict[PairKey, RankRow]:
    """Attach a dense rank to each pair. **Scoring-side only.**

    Rank 1 is the highest realized EMA. Ties share a rank, which is what makes
    `arbitrate` fall back to FCFS on them rather than inventing an order out of
    dict iteration — §6.6: *"Equal or absent scores ⇒ FCFS."*

    This is the one place ordering is computed, and it is off the hot path by
    construction: it runs in the Scoring process, before `publish`.
    """
    observed = days_observed or {}
    ordered = sorted(realized_ema.items(), key=lambda item: (-item[1], item[0]))
    out: dict[PairKey, RankRow] = {}
    rank = 0
    previous: float | None = None
    for index, (key, ema) in enumerate(ordered, start=1):
        if previous is None or ema != previous:
            rank = index
            previous = ema
        out[key] = RankRow(
            strategy_id=key[0],
            symbol=key[1],
            realized_ema=ema,
            rank=rank,
            days_observed=int(observed.get(key, 0)),
        )
    return out


class RankingPublisher:
    """The Scoring process's outward face. **Sole writer, by construction.**

    There is no method here by which a consumer can write, and the underlying
    `StatePublisher` holds the table in this process's own memory and hands out
    copies — §12.7's *"raw shared state tables would … reduce the single-writer
    principle to fiction."*

    The publisher is passed IN rather than built here so the Scoring process
    owns its socket lifetime, and so a test can drive the seam without a
    transport at all.
    """

    def __init__(self, publisher: Any, *, identity: str = SCORING_WRITER_IDENTITY):
        self._publisher = publisher
        self.identity = identity
        self.published = 0

    def publish(self, snapshot: RankingSnapshot) -> None:
        """ASYNC, fire-and-forget. Scoring never waits on a reader."""
        if snapshot.writer_identity != self.identity:
            raise SeamError(
                f"refusing to publish a snapshot stamped {snapshot.writer_identity!r} "
                f"from the publisher identified as {self.identity!r} — the "
                "sole-writer stamp is not a field a caller may choose"
            )
        self._publisher.publish(RANKING_TOPIC, snapshot.as_wire())
        self.published += 1

    def service(self, timeout_ms: int = 0) -> int:
        """SYNC. Serves §12.7's mandatory snapshot-on-subscribe."""
        return self._publisher.service(timeout_ms)


class RankingMirror:  # pylint: disable=too-many-instance-attributes
    """A consumer's PRIVATE, READ-ONLY copy. O(1) reads, no math.

    The Allocator and the Limiter each hold one. It exposes `lookup` and
    `arbitrate` and **no setter**: the only way state enters is `apply`, fed
    from the subscriber socket.

    ## Stale-until-proven-fresh (§0i)

    A mirror that has received nothing is STALE, not empty-and-fine. §12.7:
    *"mirror incomplete ⇒ treated as stale ⇒ fast-drop/deny until snapshot
    lands"* — and here "fast-drop" means FCFS, because §6.6 forbids the deny.
    `_applied_at` starts at `None` and every freshness question against `None`
    answers stale.
    """

    def __init__(
        self,
        *,
        stale_after_s: float,
        identity: str = SCORING_WRITER_IDENTITY,
    ) -> None:
        if stale_after_s <= 0:
            raise SeamError(
                f"stale_after_s={stale_after_s!r}: a non-positive freshness "
                "threshold makes every table stale forever, which turns the "
                "FCFS fallback from a degraded mode into the only mode"
            )
        self.stale_after_s = float(stale_after_s)
        self.identity = identity
        self._rows: dict[PairKey, RankRow] = {}
        self._applied_at: float | None = None
        self._span_days: int | None = None
        #: COUNTERS, not flags. A transport that cannot say what it carried can
        #: only be believed; the same reasoning as `StatePublisher`'s four.
        self.applied = 0
        self.foreign_rejected = 0
        self.malformed_rejected = 0

    # -- ingress ---------------------------------------------------------

    def apply(self, message: StateMessage, now: float | None = None) -> bool:
        """Fold one update in. Returns whether it was accepted.

        A snapshot stamped by anything other than the Scoring identity is
        REJECTED and counted. That is the sole-writer property enforced where a
        foreign writer would actually arrive — a second publisher binding the
        same endpoint reaches the consumer, and only the consumer can refuse it.
        """
        if message.topic != RANKING_TOPIC:
            return False
        try:
            snapshot = RankingSnapshot.from_wire(message.payload)
        except SeamError:
            self.malformed_rejected += 1
            return False
        if snapshot.writer_identity != self.identity:
            self.foreign_rejected += 1
            return False
        self._rows = dict(snapshot.rows)
        self._span_days = snapshot.span_days
        self._applied_at = time.time() if now is None else now
        self.applied += 1
        return True

    # -- read contract ---------------------------------------------------

    @property
    def span_days(self) -> int | None:
        """The span the live table was computed under, or None if never fed."""
        return self._span_days

    def age_s(self, now: float | None = None) -> float | None:
        """Seconds since the last accepted snapshot, or None if never fed."""
        if self._applied_at is None:
            return None
        return max(0.0, (time.time() if now is None else now) - self._applied_at)

    def fresh(self, now: float | None = None) -> bool:
        """§0i: stale until proven fresh. Never fed ⇒ False."""
        age = self.age_s(now)
        return age is not None and age <= self.stale_after_s

    def lookup(self, strategy_id: str, symbol: str) -> RankRow | None:
        """THE HOT-PATH READ. One dict get. No arithmetic, no I/O, no scan."""
        return self._rows.get((strategy_id, symbol))

    def arbitrate(
        self,
        first: PairKey,
        second: PairKey,
        now: float | None = None,
    ) -> Verdict:
        """Decide between two contenders, in ARRIVAL ORDER. Never blocks.

        `first` arrived first; that is what makes the fallback
        first-come-first-served rather than an arbitrary pick. Every non-ranked
        path returns FCFS with `first` as the winner and the trigger named.

        This function has no `raise`, no loop over the table, no I/O, and its
        only arithmetic is one subtraction for the age and one float comparison
        — which is what "O(1) lookup, never math" means in §6.6 and §11:595.
        """
        if self._applied_at is None:
            return Verdict(
                Arbitration.FCFS,
                first,
                "no ranking snapshot has arrived; §12.7 treats an incomplete "
                "mirror as stale and §6.6 makes the degraded answer FCFS",
            )
        age = self.age_s(now)
        if age is None or age > self.stale_after_s:
            return Verdict(
                Arbitration.FCFS,
                first,
                f"ranking table stale: age {age:.3f}s exceeds the "
                f"{self.stale_after_s:.3f}s freshness threshold (§12.7)",
            )
        left = self._rows.get(first)
        right = self._rows.get(second)
        if left is None or right is None:
            absent = first if left is None else second
            return Verdict(
                Arbitration.FCFS,
                first,
                f"no ranking row for {absent!r} — cold start or no realized "
                "history; §6.6 makes an absent score FCFS",
            )
        if left.realized_ema == right.realized_ema:
            return Verdict(
                Arbitration.FCFS,
                first,
                f"equal realized EMA ({left.realized_ema!r}) for {first!r} and "
                f"{second!r}; §6.6 makes an equal score FCFS",
            )
        winner = first if left.realized_ema > right.realized_ema else second
        return Verdict(
            Arbitration.RANKED,
            winner,
            f"higher realized-P&L EMA: {first!r}={left.realized_ema!r} vs "
            f"{second!r}={right.realized_ema!r}",
        )
