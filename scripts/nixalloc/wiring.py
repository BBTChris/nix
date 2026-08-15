"""Stage 2 — the three Stage-1 pieces composed into ONE pass, and the gap.

ARC 031 / Stage 2. Sub-agent A built the mirror, B the sizing pathway, C the
correlation cap and the FCFS fallback. Each was built against the frozen seam
with its own doubles, on purpose, so none of them measured the others. This
module is where they meet, and composing them is what found the thing none of
them could see alone.

---------------------------------------------------------------------------
THE FINDING THIS MODULE EXISTS TO STATE (CHECK-DEBT D3.136)
---------------------------------------------------------------------------
**§7's correlation-bucket cap cannot be computed from the published snapshot
alone, and nothing in Stage 1 could notice.**

§7:501 fixes the exposure unit as dollar risk:
`(stop_ticks + slippage_pad) × tick_value × contracts`. Applying it to the
positions already in a bucket therefore needs each open/pending position's
**stop distance**. The published `PositionRow` (`nixrisk.seam`, frozen) carries
`trade_id`, `symbol`, `strategy_id`, `size`, `margin`, `state` — and **no stop
distance at all**. The distance lives in the Limiter's stop book as
`StopState.initial_distance_ticks`, keyed by `client_order_id`, and the stop
book is not published.

So the cap has exactly two possible input paths and BOTH are currently closed:

1. **Read the stop book as a second table.** That is the cross-table skew §6.4
   refuses in the same breath as it fixes one snapshot — "independent tables
   tick on independent clocks, so a sizing pass could read fresh margin against
   slightly stale balance". It is also unavailable: nothing publishes it.
2. **Put the distance on the published row.** That is a change to the one
   snapshot §3 makes atomic, so it is a `SEAM_REV` bump and an architect
   ruling, not an implementation detail this arc may take.

**RULED — OPTION A, path 2 (ARC 031, Phase 5).** The architect adopted the
published-row fix: `PositionRow` gains `stop_distance`, riding the SAME
versioned snapshot as `balance` and `positions` — one more field under one
writer and one version stamp (§6.4b's principle) — and explicitly NOT path 1,
which *is* the cross-table skew §6.4 forbids. The deciding argument is that the
cap is a **safety input currently failing OPEN**: an unpriced position reads as
zero risk, the bucket looks emptier than it is, and an emptier bucket ADMITS
more. **This is R3-B's opening item and is NOT built here**: the Limiter (sole
writer) adds the field, every mirror consumer widens, `SEAM_REV` goes to
`1.1.0` (planned target recorded in `nixalloc/seam.py`), and R3-B re-proves the
one-versioned-row identity across the wider schema. Until that lands, every
sentence below still holds and this module still reports what it cannot price.

Sub-agent C's `admit()` is correct as a FORMULA and its can-fail proves the
summation. Sub-agent B's `BucketCapPort` is the right seam. Neither could see
that the argument between them has no production source, because C was handed
`Exposure` rows directly and B was handed `None`. **A green from either gate
does not mean the cap can run**, and this module refuses to hide that: the
exposure source is an INJECTED port with no default, `PublishedExposures`
(the only source derivable from the snapshot today) reports every row it could
not price, and `PathwayReport` carries that count out to the caller.

---------------------------------------------------------------------------
WHAT IS COMPOSED HERE, AND WHAT IS STILL ABSENT
---------------------------------------------------------------------------
Composed: the mirror consumer (A) → the tradability fast-drop and sizing
pathway (B) → the correlation-bucket cap (C), under one snapshot version.

Absent, and stated rather than implied: the Scoring process and
performance-weighted contention (R5 — `ContentionPolicy.FCFS` is the only
policy this system can take, and `contention.rank` is wired here only to prove
the fallback fires); blackout/calendar pollers (R4); the strategy FSM; the
Limiter's own Phase B (which re-checks everything this proposes — that
re-check is the guarantee, not redundancy); and the per-position stop distance
above.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nixalloc import caps
from nixalloc.seam import (
    BUCKET_OF,
    CorrelationBucket,
    FinancialPicture,
    MirrorPort,
    PositionRow,
    PositionState,
    Proposal,
    ProposalOutcome,
    Side,
    StopMode,
    TradabilityCachePort,
)
from nixalloc.sizing import (
    BucketCapPort,
    BucketQuery,
    BucketVerdict,
    InstrumentSpec,
    SizingAllocator,
    SizingKnobs,
)

# pylint: disable=too-few-public-methods
# `ExposureSourcePort` and `AllocatorPathway` carry exactly the verbs their
# subjects have. Inventing a second method to clear a class-shape threshold
# would be inventing surface — and on the pathway, surface IS authority (§2).
#
# pylint: disable=too-many-arguments,too-many-positional-arguments
# `AllocatorPathway.propose` mirrors `AllocatorPort.propose`, whose parameters
# are exactly the fields §2's component table says a GO carries. Collapsing
# them into a `Go` struct is a real decision deferred to R3-B with the strategy
# FSM, which OWNS that message shape; minting it here would put the strategy's
# wire type in the Allocator's composition layer.

#: §7:505-510's "open + pending in bucket B". `RESERVED` is deliberately
#: included: §3's reservation lifecycle makes a reservation capital already
#: committed, and a cap that ignored reservations would admit a proposal
#: against room another proposal has already taken.
COUNTED_STATES = (PositionState.RESERVED, PositionState.PENDING, PositionState.OPEN)


@runtime_checkable
class ExposureSourcePort(Protocol):
    """Where an already-held position's DOLLAR RISK comes from.

    A port and not a function, because the honest answer today is "nowhere"
    (D3.136) and the shape of the eventual answer is an architect ruling. An
    implementation must report what it could not price rather than pricing it
    at zero — a position silently valued at zero risk makes the bucket look
    emptier than it is, which is the direction that ADMITS trades.
    """

    def exposures(
        self, picture: FinancialPicture, bucket: CorrelationBucket
    ) -> tuple[Sequence[caps.Exposure], tuple[str, ...]]:
        """`(priced exposures, trade_ids that could NOT be priced)`."""


@dataclass(frozen=True)
class PublishedExposures:
    """The only exposure source derivable from the published snapshot today.

    It prices a row ONLY if the caller supplied that trade's stop distance out
    of band, and returns every other counted row as UNPRICED. That is not a
    workaround: it is the measurement. On a real snapshot with no side table,
    `unpriced` equals the number of counted rows in the bucket and `exposures`
    is empty — so a cap computed from it is a cap over nothing, and
    `PathwayReport.cap_blind` says so out loud.
    """

    #: `trade_id -> stop distance in ticks`, whatever the caller could learn.
    #: Empty is the honest production value today.
    stop_ticks_by_trade: Mapping[str, int] = dataclasses.field(default_factory=dict)
    #: `trade_id`s known to be micro legs (§7:502, counted at 1/10 weight).
    micro_trades: frozenset[str] = frozenset()

    def exposures(
        self, picture: FinancialPicture, bucket: CorrelationBucket
    ) -> tuple[Sequence[caps.Exposure], tuple[str, ...]]:
        """`(priced, unpriced)` — every counted row this source could not price."""
        priced: list[caps.Exposure] = []
        unpriced: list[str] = []
        for row in _counted_rows(picture, bucket):
            stop = self.stop_ticks_by_trade.get(row.trade_id)
            if stop is None or stop <= 0:
                unpriced.append(row.trade_id)
                continue
            priced.append(
                caps.Exposure(
                    symbol=row.symbol,
                    contracts=abs(row.size),
                    stop_ticks=stop,
                    micro=row.trade_id in self.micro_trades,
                )
            )
        return tuple(priced), tuple(unpriced)


def _counted_rows(
    picture: FinancialPicture, bucket: CorrelationBucket
) -> tuple[PositionRow, ...]:
    """§7's "open + pending in bucket B", from the published table only."""
    return tuple(
        row
        for row in picture.positions
        if row.state in COUNTED_STATES and BUCKET_OF.get(row.symbol) is bucket
    )


@dataclass(frozen=True)
class BucketCapAdapter:
    """`BucketCapPort` over `caps.admit`. The join sub-agent B left open.

    **AND THE JOIN DID NOT FIT — CHECK-DEBT D3.137.** B's port originally
    passed `(bucket, contracts, risk_per_contract, picture)`; C's function
    needs `(symbol, contracts, stop_ticks, exposures, balance, config,
    micro)`. Neither was wrong on its own, and both gates were green: B drove
    the port with `None` and asserted the not-applied sentence, C drove
    `caps.admit` directly with exposures it constructed. The argument between
    them was never made until this module made it, and then it did not
    typecheck against §7 — `equities` holds two symbols, so `bucket` alone
    cannot name the proposal's symbol.

    The first draft here tried to recover the symbol from the bucket plus the
    margin table, and the integration test caught it in the direction that
    matters: on a snapshot pricing both ES and NQ (the normal case) the
    recovery was ambiguous, the adapter reported "cap NOT APPLIED", and the
    proposal went through UNCAPPED while every gate stayed green. `BucketQuery`
    is the repair — the seam now carries what §7:501 needs to price a
    proposal, and the widening is recorded rather than slipped in.

    **It never raises into the sizing pass.** `caps.admit` fails closed and
    loud on an unbucketed symbol, a non-positive stop and a non-positive size —
    correct for a formula, wrong for a hot path §6.6 says must never stall.
    Each becomes an admitted-zero verdict naming the refusal, so the pass
    denies rather than dying, and the reason still reaches §16 U5's rationale.
    """

    config: caps.CapConfig
    source: ExposureSourcePort
    #: Set by the pass, read by the report. A list because the adapter is
    #: frozen and this is measurement output, not configuration.
    unpriced: list[str] = dataclasses.field(default_factory=list)

    def admit(self, query: BucketQuery) -> BucketVerdict:
        """Clamp toward B's ceiling. Never raises the size, never raises at all.

        **Every refusal becomes an admitted-zero verdict rather than an
        exception**, and that too is a Stage-2 measurement rather than a
        design preference: `caps.admit` fails closed and loud on an unbucketed
        symbol, a non-positive stop and a non-positive size, which is right for
        a formula and fatal for a hot path §6.6 says must never stall. The
        exposure SOURCE is wrapped for the same reason and the wrapping was
        forced — this module's own integration test drove a raising source and
        the first draft let it kill the sizing pass.
        """
        self.unpriced.clear()
        try:
            held, unpriced = self.source.exposures(  # pylint: disable=assignment-from-no-return
                query.picture, query.bucket
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return BucketVerdict(
                contracts=0,
                used=0.0,
                ceiling=0.0,
                note=(
                    "§7 exposure source REFUSED and the pass denies rather "
                    f"than dies: {type(exc).__name__}: {exc}"
                ),
            )
        self.unpriced.extend(unpriced)
        try:
            decision = caps.admit(
                symbol=query.symbol,
                contracts=query.contracts,
                stop_ticks=query.stop_ticks,
                exposures=held,
                balance=query.picture.balance,
                config=self.config,
                micro=query.micro,
            )
        except caps.BucketCapError as exc:
            return BucketVerdict(
                contracts=0,
                used=0.0,
                ceiling=0.0,
                note=f"§7 cap REFUSED and the pass denies rather than dies: {exc}",
            )
        blind = (
            f"; {len(unpriced)} held position(s) in {query.bucket.value} could "
            "NOT be priced (no published stop distance — D3.136), so this "
            "ceiling is measured over an INCOMPLETE bucket"
            if unpriced
            else ""
        )
        return BucketVerdict(
            contracts=decision.admitted_contracts,
            used=decision.used_dollar_risk,
            ceiling=decision.ceiling_dollar_risk,
            note=f"§7 cap applied over {len(held)} priced exposure(s){blind}",
        )


@dataclass(frozen=True)
class PathwayReport:
    """One GO's outcome, plus what the pass could NOT see while producing it."""

    proposal: Proposal
    #: Held positions in the proposal's bucket that had no priceable stop.
    cap_blind: tuple[str, ...] = ()
    #: True when the cap ran over an incomplete bucket (D3.136).
    cap_incomplete: bool = False

    @property
    def reaches_broker(self) -> bool:
        """Always False — §2. The pathway emits proposals, never orders."""
        return self.proposal.reaches_broker


class AllocatorPathway:
    """Mirror → fast-drop → size → cap, one GO, one `PathwayReport`.

    Thin ON PURPOSE. Every rule lives in a Stage-1 module with its own gate;
    if a rule appeared here it would be a fourth authority none of those gates
    judges. What lives here is the COMPOSITION and the honest reporting of
    what the composition could not do.
    """

    def __init__(
        self,
        *,
        mirror: MirrorPort,
        tradability: TradabilityCachePort,
        instruments: Mapping[str, InstrumentSpec],
        knobs: SizingKnobs,
        bucket_cap: BucketCapAdapter | None,
    ) -> None:
        self._cap = bucket_cap
        self._allocator = SizingAllocator(
            mirror=mirror,
            tradability=tradability,
            instruments=instruments,
            knobs=knobs,
            bucket_cap=bucket_cap,
        )

    def propose(
        self,
        strategy_id: str,
        symbol: str,
        side: Side,
        stop_ticks: int,
        stop_mode: StopMode,
        signal_ts: float,
    ) -> PathwayReport:
        """One GO in, one report out. Synchronous, single-pass (§16 U1)."""
        proposal = self._allocator.propose(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            stop_ticks=stop_ticks,
            stop_mode=stop_mode,
            signal_ts=signal_ts,
        )
        blind = tuple(self._cap.unpriced) if self._cap is not None else ()
        return PathwayReport(
            proposal=proposal,
            cap_blind=blind,
            cap_incomplete=bool(blind),
        )


def port_check(pathway: AllocatorPathway) -> BucketCapPort | None:
    """Structural assertion that the adapter still satisfies B's port.

    Called by the gate rather than asserted in prose: `BucketCapPort` is a
    `runtime_checkable` Protocol, so this is an `isinstance` the interpreter
    performs, not a claim the author makes.
    """
    cap = pathway._cap  # pylint: disable=protected-access
    if cap is None:
        return None
    if not isinstance(cap, BucketCapPort):
        raise TypeError("BucketCapAdapter no longer satisfies BucketCapPort")
    return cap


__all__ = [
    "COUNTED_STATES",
    "AllocatorPathway",
    "BucketCapAdapter",
    "ExposureSourcePort",
    "PathwayReport",
    "ProposalOutcome",
    "PublishedExposures",
    "port_check",
]
