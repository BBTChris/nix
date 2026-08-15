"""§6.6 contention, consumer side — the READ seam, and the FCFS fallback that is the live state.

ARC 031 Stage 1 / sub-agent C. §6.6:429-468 of the frozen risk spec says that
when proposals compete for capital that cannot satisfy them all, the winner is
chosen by recent realized productivity — a realized-P&L EMA per
`(strategy_id, symbol)` pair, published by a dedicated **Scoring process** that
is the sole writer of a ranking table.

**THAT PROCESS DOES NOT EXIST.** Scoring is R5 (§12B), no writer for the ranking
table has been built, and therefore the table is permanently absent. So the
honest description of this module is: *it wires the READ seam and it implements
the FALLBACK, and the fallback is the state the whole system runs in today.*
That is not a limitation discovered late; §6.6:465-468 locks it —

    "if the Scoring process is down or its table is stale, both Allocator and
    Limiter fall back to first-come-first-served — deterministic, structurally
    neutral (favors no symbol), needs no computation at the moment a process
    just died. Ranking is an optimization, never a safety gate: a scoring
    outage must NEVER halt order flow."

THE AUTHORITY BOUNDARY, AND WHY THERE IS NO `award()` IN THIS FILE
------------------------------------------------------------------
§6.6:459-460 splits the two readers by verb: *"The **Allocator reads** it to
weight sizing. The **Limiter reads** it to arbitrate contention when a shared
resource can't satisfy every proposal at once."* §2:40 makes the Allocator
**permissive** and §2:42 makes the Limiter **prohibitive**.

This module is on the Allocator's side of that line, so it produces an
**ORDERING** and it never awards anything. There is no `award`, no `winner`, no
`grant`, no `allocate`, no `assign` and no `arbitrate` verb here, and their
absence is the declaration — the same move `scripts/nixalloc/seam.py` makes by
giving `RankingTablePort` no writer verb. `checks/check_allocator_caps.py`
proves it BY ATTEMPT: it reaches for each forbidden verb on the imported module
and requires every reach to come back empty.

WHAT IS DEFERRED TO R5, SO NO GATE HERE IMPLIES COVERAGE IT DOES NOT HAVE
-------------------------------------------------------------------------
1. **The Scoring process itself and every line of EMA math.** §6.6:461 —
   "Nobody but the Scoring process COMPUTES the score." Nothing here computes
   one; the only arithmetic over a score in this file is a COMPARISON, which
   §6.6:453 names as the arbitration primitive and §6.6:463 explicitly permits
   on the hot path ("an O(1) table lookup, never math").
2. **The score → sizing-weight transform.** §6.6:459 says the Allocator reads
   the table "to weight sizing" and the spec fixes no transform. Inventing one
   would be exactly the "defining productive" allocation judgment §6.6:461-463
   keeps out of the consumer. `ContentionRanking.weights` is therefore 1.0 for
   every contender under BOTH policies, and `reason` says so out loud, so a
   caller cannot mistake a live ordering for live weighting.
3. **The ranking table's staleness THRESHOLD.** §12A names
   `MARGIN_STALE_MS`, `CALENDAR_STALE_MS`, `PRICE_STALE_MS` and
   `BALANCE_STALE_MS` and names no threshold for the ranking table, so this
   module does not invent one: `RankingTablePort.available()` is the authority
   on absent-or-stale, and the optional `max_age_s` argument is applied only
   when a caller supplies one. (CHECK-DEBT D3.133.)

`debug.md` §7.12 — THE STANDING QUESTION for `rank`: *what would have to be true
for this to return an answer while measuring nothing?*
  1. **The contender list is empty**, so any ordering is correct. GUARDED:
     `ContentionRanking.contenders` reports the count, and the gate asserts a
     floor above one before reading an ordering.
  2. **The FCFS answer coincides with the input order, the alphabetical order
     and the score order all at once**, so agreeing with it proves nothing.
     CLOSED IN THE INSTRUMENTS, which is where it can be closed: every FCFS
     control is driven on contenders whose arrival order disagrees with both
     their alphabetical order and their scores.
  3. **The read seam is decorative** — `rank` never calls the port and always
     returns FCFS, which would look identical in the only state the system is
     ever in. CLOSED: the gate drives a port with DIFFERENT live scores and
     requires the ordering to move off arrival order.
  4. **The fallback is reached by an exception escaping**, so "never halts" is
     true only because the caller crashed. CLOSED: a port that RAISES is driven
     and must still produce a deterministic FCFS answer naming the exception.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nixalloc.seam import ContentionPolicy, RankingRow, RankingTablePort

__all__ = [
    "NEUTRAL_WEIGHT",
    "Contender",
    "ContentionRanking",
    "fcfs_order",
    "rank",
]

#: The weight every contender carries under BOTH policies today. Named rather
#: than written as a bare 1.0 at three call sites, because the number is a
#: DECLARATION: sizing is not weighted by score in this arc, and §6.6:459's
#: "weight sizing" is deferred to R5 with the process that publishes the score.
NEUTRAL_WEIGHT = 1.0


@dataclass(frozen=True)
class Contender:
    """One proposal competing for a shared resource (§6.6:431-432).

    `arrival_seq` is a monotonic ARRIVAL counter stamped by whoever received
    the GO — lower is earlier. It is deliberately not a timestamp: FCFS has to
    be *deterministic* (§6.6:466) and two GOs inside one clock tick would tie
    on a float and be ordered by whatever the sort did next.
    """

    strategy_id: str
    symbol: str
    arrival_seq: int

    @property
    def pair(self) -> tuple[str, str]:
        """§6.6:447's canonical key: ONE row per `(strategy_id, symbol)`."""
        return (self.strategy_id, self.symbol)


@dataclass(frozen=True)
class ContentionRanking:
    """An ORDERING and a weighting. Never an award — see the module docstring.

    `policy` says which of §6.6's two rules produced it, and `reason` says WHY
    that one and not the other (§18: assert the reason, never the code).
    """

    policy: ContentionPolicy
    #: Best-first. Advisory input to sizing; the Limiter arbitrates (§6.6:459).
    ordering: tuple[Contender, ...]
    #: `(strategy_id, symbol)` -> sizing weight. Every value is `NEUTRAL_WEIGHT`
    #: in this arc, under both policies. See deferral 2 above.
    weights: Mapping[tuple[str, str], float]
    #: How many contenders had a live row. Zero under every fallback path.
    scored: int
    #: How many contenders were ranked at all (§7.12/1 — an empty race is not
    #: a correct answer, it is no measurement).
    contenders: int
    reason: str

    @property
    def is_fallback(self) -> bool:
        """True when §6.6:465-468's FCFS fallback produced this ordering."""
        return self.policy is ContentionPolicy.FCFS


def fcfs_order(contenders: Sequence[Contender]) -> tuple[Contender, ...]:
    """§6.6:466's fallback ordering: by ARRIVAL, and by nothing else.

    Sorted on `arrival_seq` alone. `sorted` is stable, so contenders sharing a
    sequence number keep the order they were handed in — deterministic, and
    still a function of arrival rather than of the symbol. Nothing about the
    symbol, the strategy id or any score enters this function, which is what
    §6.6:466's "structurally neutral (favors no symbol)" means mechanically.
    """
    return tuple(sorted(contenders, key=lambda contender: contender.arrival_seq))


def _fallback(
    contenders: Sequence[Contender], reason: str, scored: int = 0
) -> ContentionRanking:
    """Build the FCFS answer. The ONE constructor for every fallback path.

    One constructor and not four, so no route into the fallback can quietly
    differ from another — a fallback reached because the table was absent and a
    fallback reached because the port raised must produce the same ORDER, and
    differ only in the reason they name.
    """
    ordered = fcfs_order(contenders)
    return ContentionRanking(
        policy=ContentionPolicy.FCFS,
        ordering=ordered,
        weights={contender.pair: NEUTRAL_WEIGHT for contender in ordered},
        scored=scored,
        contenders=len(contenders),
        reason=reason,
    )


def _live_rows(
    contenders: Sequence[Contender],
    table: RankingTablePort,
    max_age_s: float | None,
    now: float | None,
) -> tuple[dict[tuple[str, str], float], str]:
    """`({pair: score}, complaint)` for every contender with a usable row.

    A row is unusable when it is absent, or when the caller supplied both a
    `now` and a `max_age_s` and the row is older than that. Aging is applied
    only on request: §12A defines no staleness threshold for the ranking table
    and this module will not invent one (deferral 3).
    """
    scores: dict[tuple[str, str], float] = {}
    for contender in contenders:
        row = table.row(contender.strategy_id, contender.symbol)
        if not isinstance(row, RankingRow):
            continue
        if max_age_s is not None and now is not None and now - row.as_of > max_age_s:
            continue
        scores[contender.pair] = float(row.score)
    if len(scores) < len(contenders):
        return {}, (
            f"{len(scores)} of {len(contenders)} contender(s) have a live "
            "ranking row — §6.6:455 makes an ABSENT score an FCFS case, and a "
            "partial table would rank a scored pair above an unscored one for "
            "no reason a realized P&L supports"
        )
    if len(set(scores.values())) <= 1:
        return {}, (
            "every contender's realized-P&L EMA is equal "
            f"({sorted(set(scores.values()))}) — §6.6:455 makes EQUAL scores an "
            "FCFS case, which is the cold-start state by construction"
        )
    return scores, ""


def rank(
    contenders: Sequence[Contender],
    table: RankingTablePort | None,
    *,
    max_age_s: float | None = None,
    now: float | None = None,
) -> ContentionRanking:
    """Order competing proposals. SYNCHRONOUS, total, and it never raises.

    Never raising is not defensive habit, it is §6.6:467-468: *"Ranking is an
    optimization, never a safety gate: a scoring outage must NEVER halt order
    flow."* A port that is absent, that reports itself unavailable, or that
    throws, all reach the same deterministic FCFS ordering; they differ only in
    the reason the ranking carries. There is no await, no retry, no sleep and
    no loop over a clock in this function, so "immediately" is a property of
    its shape rather than of its timing on a good day.
    """
    if table is None:
        return _fallback(
            contenders,
            "no ranking-table port was supplied — the Scoring process is R5 "
            "(§12B) and does not exist, so §6.6:465's fallback is not an error "
            "path here, it is the live configuration",
        )
    try:
        available = bool(table.available())
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return _fallback(
            contenders,
            f"the ranking table's availability probe raised "
            f"{type(exc).__name__}: {exc} — §6.6:467 forbids a scoring outage "
            "halting order flow, so the exception becomes a fallback and a "
            "reason, never a propagated failure",
        )
    if not available:
        return _fallback(
            contenders,
            "the ranking table reports itself unavailable (absent or stale) — "
            "§6.6:465's locked fallback",
        )
    try:
        scores, complaint = _live_rows(contenders, table, max_age_s, now)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return _fallback(
            contenders,
            f"the ranking-table lookup raised {type(exc).__name__}: {exc} — "
            "§6.6:463 makes the read an O(1) lookup, and a lookup that fails "
            "is an absent score (§6.6:455), never a halt",
        )
    if complaint:
        return _fallback(contenders, complaint)
    return _weighted(contenders, scores)


def _weighted(
    contenders: Sequence[Contender], scores: Mapping[tuple[str, str], float]
) -> ContentionRanking:
    """§6.6:433's performance-weighted ordering: highest realized-P&L EMA first.

    Ties break on arrival, so the FCFS rule is the tiebreaker inside the
    performance rule rather than a separate branch — §6.6:455 makes equal
    scores an FCFS case, and a pair of equal scores inside a larger field is
    the same case in miniature.

    The COMPARISON is all that happens here. No EMA is computed, no score is
    combined, and no weight is derived from one — see deferrals 1 and 2.
    """
    ordered = tuple(sorted(contenders, key=lambda c: (-scores[c.pair], c.arrival_seq)))
    return ContentionRanking(
        policy=ContentionPolicy.PERFORMANCE_WEIGHTED,
        ordering=ordered,
        weights={contender.pair: NEUTRAL_WEIGHT for contender in ordered},
        scored=len(scores),
        contenders=len(contenders),
        reason=(
            f"{len(scores)} live ranking row(s) with distinct realized-P&L EMAs "
            "— ordered by comparison (§6.6:453), arrival breaking ties. The "
            "score -> SIZING WEIGHT transform is NOT implemented: §6.6:459 "
            "gives it to the Allocator and the spec fixes no transform, so "
            f"every weight is {NEUTRAL_WEIGHT} and the weighting is deferred to "
            "R5 with the Scoring process. This ordering is ADVISORY: §6.6:459 "
            "gives arbitration to the Limiter, not to this module"
        ),
    )
