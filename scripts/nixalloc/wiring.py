"""Stage 2 — the three Stage-1 pieces composed into ONE pass, and the gap.

ARC 031 / Stage 2. Sub-agent A built the mirror, B the sizing pathway, C the
correlation cap and the FCFS fallback. Each was built against the frozen seam
with its own doubles, on purpose, so none of them measured the others. This
module is where they meet, and composing them is what found the thing none of
them could see alone.

---------------------------------------------------------------------------
D3.136 IS CLOSED (ARC 032, Stage 2), AND THE FINDING IS KEPT
---------------------------------------------------------------------------
**§7's cap now runs on the COMPLETE bucket.** `PositionRow.stop_distance` rides
the published snapshot (`SEAM_REV 1.1.0`, `WIRE_SCHEMA 2`, `SPEC-A9`), so
`PublishedExposures` prices a held position from the same versioned row that
carries `balance`, and `Σ dollar_risk(open + pending in B) + proposed ≤
bucket_cap_pct(B) × balance` has every term real. The out-of-band stop table
this module carried as a measurement of the gap is DELETED, not defaulted.

**Measured before and after on ONE scenario, because the after alone proves
nothing:** two held same-bucket positions carrying real stop distances, and a
third proposal against them. Under the pre-widening bytes the two held rows
priced at ZERO, the bucket read empty and the third proposal was ADMITTED
WHOLE; under the widened row the same scenario prices the bucket at its true
summed dollar risk and the third proposal is CAPPED. The figures are in
`scripts/tests/test_allocator_pathway.py` and the pre-widening half is driven
from git rather than simulated.

The original finding is kept below verbatim in substance, because the reason a
gap existed outlives the gap and the NEXT one will have this shape.

**§7's correlation-bucket cap could not be computed from the published snapshot
alone, and nothing in Stage 1 could notice.**

§7:501 fixes the exposure unit as dollar risk:
`(stop_ticks + slippage_pad) × tick_value × contracts`. Applying it to the
positions already in a bucket therefore needs each open/pending position's
**stop distance**. The published `PositionRow` (`nixrisk.seam`, frozen) carries
`trade_id`, `symbol`, `strategy_id`, `size`, `margin`, `state` — and **no stop
distance at all**. The distance lives in the Limiter's stop book as
`StopState.initial_distance_ticks`, keyed by `client_order_id`, and the stop
book is not published.

So the cap had exactly two possible input paths and BOTH were closed:

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
more. **BUILT IN ARC 032**: the Limiter (sole writer) added the field, every
mirror consumer widened, `SEAM_REV` went to `1.1.0`, and the one-versioned-row
identity was RE-PROVEN on the wider row by the same race harness — including a
third plant that IS path 1, the stop-book join, so the refusal of Option B is a
measurement in this tree and not only an argument in a ledger.

**AND A SECOND DOOR WAS FOUND WHILE CLOSING THE FIRST**, which is the part
worth carrying forward: reading the stop distance off the row does nothing for
a row that never reaches the bucket at all. §7:498's map is keyed on LOGICAL
symbols and nothing pins what vocabulary the published `symbol` field speaks,
so a row spelled `ESZ6` was dropped by the bucket filter with no counter and no
note — valued at zero by OMISSION rather than by valuation, in the same
admitting direction. `PublishedExposures.classify` reports that class
separately (`unbucketed`), because the two faults need different repairs.

Sub-agent C's `admit()` is correct as a FORMULA and its can-fail proves the
summation. Sub-agent B's `BucketCapPort` is the right seam. Neither could see
that the argument between them has no production source, because C was handed
`Exposure` rows directly and B was handed `None`. **A green from either gate
does not mean the cap can run**, and this module refuses to hide that: the
exposure source is an INJECTED port with no default, `PublishedExposures`
reports every counted row it could not price AND every one it could not
bucket, and `PathwayReport` carries both counts out to the caller.

Absent, and stated rather than implied: the published row does not say whether
a position is a §7:502 MICRO leg. `PublishedExposures.micro_symbols` is
injected from the registration ACK's static instrument data. Empty errs
CONSERVATIVELY — a micro priced as a full is priced at ten times its weight, so
the bucket reads FULLER and the cap admits LESS — but it is still wrong, and it
is owned in `CHECK-DEBT` rather than left to be rediscovered.

---------------------------------------------------------------------------
WHAT IS COMPOSED HERE, AND WHAT IS STILL ABSENT
---------------------------------------------------------------------------
Composed: the mirror consumer (A) → the tradability fast-drop and sizing
pathway (B) → the correlation-bucket cap (C), under one snapshot version.

Absent, and stated rather than implied: the Scoring process and
performance-weighted contention (R5 — `ContentionPolicy.FCFS` is the only
policy this system can take); blackout/calendar pollers (R4); the strategy FSM;
and the Limiter's own Phase B (which re-checks everything this proposes — that
re-check is the guarantee, not redundancy).

**A SENTENCE THAT WAS HERE AND WAS FALSE, corrected rather than deleted.** This
paragraph used to read *"`contention.rank` is wired here only to prove the
fallback fires"*. It was not wired here at all: this module never imported
`nixalloc.contention`, and nothing on a production path called `rank`. Sub-agent
C measured it in ARC 032 by grep, from a worktree with no visibility into this
file, and reported it rather than editing a file it was not given (CHECK-DEBT
D3.147). It is the same shape as D3.136 one layer up — a docstring asserting a
composition that does not exist, in the module whose whole job is to state what
the composition cannot do.

**ARC 032 wired the §4 capital screen, which is the half that was load-bearing**
(see `_screen_capital` below). Performance-weighted contention still is not
wired and still cannot be: §6.6's ranking table has no writer, `rank` degrades
to FCFS by construction, and a §16 U1 single-pass proposal has no race to
arbitrate — arbitration is the Limiter's, across concurrent proposals. That
paragraph now says what is true.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nixalloc import caps
from nixalloc import lifecycle as lifecycle_mod
from nixalloc.seam import (
    BUCKET_OF,
    BindingConstraint,
    ContentionPolicy,
    CorrelationBucket,
    FinancialPicture,
    MirrorPort,
    PositionRow,
    PositionState,
    Proposal,
    ProposalOutcome,
    Side,
    SizingRationale,
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
    """The exposure source, derived from the PUBLISHED SNAPSHOT and nothing else.

    **ARC 032 closed D3.136 here.** Until this arc the published `PositionRow`
    carried no stop distance, so this class priced a row only if the caller
    handed it one **out of band** (`stop_ticks_by_trade`), and on a real
    snapshot that map was empty: every counted row came back UNPRICED, the
    bucket summed to zero, and the cap admitted against a bucket it could not
    see. The row now carries `stop_distance` on the same versioned snapshot as
    `balance` (`SEAM_REV 1.1.0`, `SPEC-A9`), so the distance is read from the
    row and the out-of-band map is GONE.

    **The map was deleted rather than kept as a fallback, and that is the §0a
    decision in this class.** A retained side table is a second, unversioned
    input a gate can manufacture — exactly the shape that let ARC 031 ship
    three green gates over a cap that could not run. With it gone, the only
    way to drive this class is to publish a row, which is the thing under
    measurement.

    THREE OUTCOMES PER COUNTED ROW, and all three are REPORTED:

    * **priced** — the row is in bucket B and carries a positive stop distance.
    * **unpriced** — the row is in bucket B and its `stop_distance` is absent or
      non-positive. Reported, never valued at zero: a row silently worth zero
      makes the bucket look emptier than it is, which is the direction that
      ADMITS.
    * **unbucketed** — §7:498's map gives the row's symbol NO bucket at all.

    That third class is new in ARC 032 and it is a **second fail-open door the
    widening exposed**. `BUCKET_OF` is keyed on §7:498's LOGICAL symbols
    (`ES`, `NQ`, `CL`, `GC`, `ZN`). Nothing pins the vocabulary of the
    published row's `symbol` field, and this tree already publishes all three
    spellings in its own fixtures — `ES` (logical), `MES` (micro logical) and
    `ESZ6` / `MESU6` (contract). The pre-ARC-032 filter was a single
    comprehension, `BUCKET_OF.get(row.symbol) is bucket`, so a real row
    carrying a contract symbol matched NOTHING and vanished from the bucket
    silently — priced at zero by omission rather than by valuation, with no
    counter and no note. Closing D3.136 by reading the stop distance would not
    have closed that; the row would still never have reached the sum.
    """

    #: §7:502's micro legs. The published row does NOT say whether a position
    #: is a micro, so this is injected — but it is a STATIC INSTRUMENT PROPERTY
    #: (the micro leg's symbol, delivered on the registration ACK per
    #: `nix_strategy_contract_v1.1.md` §7.2), never per-trade state. That is the
    #: distinction that makes it config rather than a manufactured measurement.
    #: EMPTY is safe in the conservative direction and is not silent: a micro
    #: priced as a full is priced at TEN TIMES its §7:502 weight, so the bucket
    #: reads FULLER than it is and the cap admits LESS. Over-counting is the
    #: direction that denies; it is still wrong and it is owned in CHECK-DEBT.
    micro_symbols: frozenset[str] = frozenset()

    def exposures(
        self, picture: FinancialPicture, bucket: CorrelationBucket
    ) -> tuple[Sequence[caps.Exposure], tuple[str, ...]]:
        """`(priced, unpriced)`. See `classify` for the third class."""
        priced, unpriced, _ = self.classify(picture, bucket)
        return priced, unpriced

    def classify(
        self, picture: FinancialPicture, bucket: CorrelationBucket
    ) -> tuple[tuple[caps.Exposure, ...], tuple[str, ...], tuple[str, ...]]:
        """`(priced, unpriced, unbucketed)` over the WHOLE counted table.

        Iterates every counted-state row rather than a pre-filtered bucket
        slice, because "this row belongs to another bucket" and "this row
        belongs to no bucket §7 knows" are different facts and only the first
        is a legitimate reason to drop it.
        """
        priced: list[caps.Exposure] = []
        unpriced: list[str] = []
        unbucketed: list[str] = []
        for row in picture.positions:
            if row.state not in COUNTED_STATES:
                continue
            row_bucket = BUCKET_OF.get(row.symbol)
            if row_bucket is None:
                unbucketed.append(f"{row.trade_id}:{row.symbol}")
                continue
            if row_bucket is not bucket:
                continue
            stop = int(row.stop_distance)
            if stop <= 0:
                unpriced.append(row.trade_id)
                continue
            priced.append(
                caps.Exposure(
                    symbol=row.symbol,
                    contracts=abs(row.size),
                    stop_ticks=stop,
                    micro=row.symbol in self.micro_symbols,
                )
            )
        return tuple(priced), tuple(unpriced), tuple(unbucketed)


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
    #: ARC 032. Counted rows §7:498 places in NO bucket — see
    #: `PublishedExposures.classify`. Kept separate from `unpriced` because the
    #: two need different repairs: an unpriced row needs a publisher that fills
    #: `stop_distance`, an unbucketed one needs a decision about what vocabulary
    #: the published `symbol` field speaks. Collapsing them would report one
    #: number for two faults, which is the ambiguity §7.12/1 refuses.
    unbucketed: list[str] = dataclasses.field(default_factory=list)

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
        self.unbucketed.clear()
        try:
            classify = getattr(self.source, "classify", None)
            if classify is None:
                held, unpriced = self.source.exposures(  # pylint: disable=assignment-from-no-return
                    query.picture, query.bucket
                )
                unbucketed: tuple[str, ...] = ()
            else:
                held, unpriced, unbucketed = classify(query.picture, query.bucket)
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
        self.unbucketed.extend(unbucketed)
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
            "NOT be priced (published stop_distance absent or non-positive), "
            "so this ceiling is measured over an INCOMPLETE bucket"
            if unpriced
            else ""
        )
        stray = (
            f"; {len(unbucketed)} counted row(s) carry a symbol §7:498 places "
            f"in NO bucket and were therefore counted in NONE: "
            f"{list(unbucketed)} — the published row's symbol vocabulary is "
            "unpinned, so a row spelled as a contract month never reaches its "
            "bucket's SUM. That is a fail-open in the same direction D3.136 "
            "was, reached by a different door"
            if unbucketed
            else ""
        )
        return BucketVerdict(
            contracts=decision.admitted_contracts,
            used=decision.used_dollar_risk,
            ceiling=decision.ceiling_dollar_risk,
            note=f"§7 cap applied over {len(held)} priced exposure(s){blind}{stray}",
        )


@dataclass(frozen=True)
class PathwayReport:
    """One GO's outcome, plus what the pass could NOT see while producing it."""

    proposal: Proposal
    #: Held positions in the proposal's bucket that had no priceable stop.
    cap_blind: tuple[str, ...] = ()
    #: True when the cap ran over an incomplete bucket.
    cap_incomplete: bool = False
    #: ARC 032: counted rows §7:498 places in no bucket at all. A row here was
    #: counted in NO bucket's sum, so the cap ran over less than the table.
    cap_unbucketed: tuple[str, ...] = ()

    @property
    def reaches_broker(self) -> bool:
        """Always False — §2. The pathway emits proposals, never orders."""
        return self.proposal.reaches_broker

    @property
    def cap_complete(self) -> bool:
        """True only when EVERY counted row was classified and priced.

        One predicate over both classes, deliberately: a caller asking "did the
        cap see the whole bucket?" must not have to know there are two ways for
        the answer to be no, and a caller that checked only `cap_incomplete`
        would read an unbucketed table as a complete one.
        """
        return not self.cap_incomplete and not self.cap_unbucketed


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
        lifecycle: lifecycle_mod.LifecycleViewPort | None = None,
    ) -> None:
        self._cap = bucket_cap
        #: ARC 032. §4:284-286's capital screen. Defaulted to a view over THIS
        #: pathway's own mirror rather than to `None`, and the default is the
        #: decision: an opt-in safety screen is off in every caller that
        #: forgets it, and D3.136 is this arc's evidence that a defaulted-off
        #: safety input is not a smaller version of a safety input.
        self._lifecycle = (
            lifecycle_mod.MirrorLifecycle(mirror) if lifecycle is None else lifecycle
        )
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
        refusal = self._screen_capital(strategy_id, symbol)
        if refusal is not None:
            return refusal
        proposal = self._allocator.propose(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            stop_ticks=stop_ticks,
            stop_mode=stop_mode,
            signal_ts=signal_ts,
        )
        blind = tuple(self._cap.unpriced) if self._cap is not None else ()
        stray = tuple(self._cap.unbucketed) if self._cap is not None else ()
        return PathwayReport(
            proposal=proposal,
            cap_blind=blind,
            cap_incomplete=bool(blind),
            cap_unbucketed=stray,
        )

    def _screen_capital(self, strategy_id: str, symbol: str) -> PathwayReport | None:
        """§4:284-286, BEFORE sizing. `None` when the strategy may be sized.

        **ORDER, and it is the rule rather than a preference.** §4:284-285 says a
        strategy mid-recovery *"is never counted eligible for new capital while
        dying"*. NEVER COUNTED — so the refusal is prior to §7's arithmetic, not
        a term inside it. Sizing a dying strategy and then discarding the number
        would compute a per-trade risk figure, a margin figure and a bucket
        contribution for capital that was never available, and §16 U5's
        rationale would carry all three as if they had meant something.

        **IT ABSTAINS ON A NON-FRESH MIRROR, and that boundary was MEASURED, not
        designed.** The first draft screened unconditionally.
        `lifecycle.eligibility_from_mirror` folds §12.7's freshness refusal into
        its own answer — correct for a contention pass, where a stale mirror
        must refuse and there is nobody else to say so — so an EMPTY, PARTIAL or
        STALE mirror came back INELIGIBLE and this method returned
        `NO_SIZE_DENY`. `check_allocator_pathway` reddened immediately: *"the
        three non-sizing outcomes collapsed into 2 — a pathway that cannot tell
        a dead signal from a stale mirror hides the §0i class entirely"*.

        §0i is the SIZING pass's to report and it already reports it. So the
        screen abstains when there is no FRESH picture to screen against
        (`MirrorLifecycle.pin()` returns `None`) and lets `STALE_MIRROR` reach
        the caller intact. Two rules, two owners; folding them would have cost
        the operator the distinction between a dying strategy and a dead feed.

        **It never raises into the pass**, for the reason `BucketCapAdapter`
        does not: §6.6 says a scoring outage must never halt order flow, and the
        same holds for a screen. A view that raises becomes a REFUSAL naming the
        exception — fail-CLOSED, which is the direction §4 wants, and the
        opposite of the cap's `unpriced` case where silence admitted. Note that
        abstention and refusal are different answers to different questions: the
        first says *another rule owns this*, the second says *this rule could
        not run*.

        **The screen and the sizing pass take TWO reads of the mirror**, and
        that is stated rather than hidden. §3's atomicity rule is about a
        consumer observing fields from two DIFFERENT versions inside one answer,
        and this is not that — the screen's answer is a boolean over one pinned
        picture and is discarded before sizing begins, so no figure below is
        computed from the screen's version. What a moving mirror CAN do here is
        admit a strategy that turned dying one version later, and the Limiter's
        Phase B re-check is the backstop §3 puts there for exactly that.
        Recorded in CHECK-DEBT rather than papered over.
        """
        try:
            verdict, abstain = _screen_verdict(self._lifecycle, strategy_id)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            verdict, abstain = (
                lifecycle_mod.CapitalEligibility(
                    strategy_id=strategy_id,
                    eligible=False,
                    reason=(
                        "§4:284-286 capital screen REFUSED and the pass denies "
                        f"rather than dies: {type(exc).__name__}: {exc}"
                    ),
                    snapshot_version=None,
                    closing_trades=(),
                    observed_states=(),
                    rows=0,
                ),
                False,
            )
        if abstain or verdict is None or verdict.eligible:
            return None
        return PathwayReport(proposal=_capital_refusal(verdict, symbol))


def _screen_verdict(
    view: lifecycle_mod.LifecycleViewPort, strategy_id: str
) -> tuple[lifecycle_mod.CapitalEligibility | None, bool]:
    """`(verdict, abstain)`. Abstain means: no FRESH picture, §0i owns this GO.

    `pin()` is preferred where the view has it, because it is the ONE surface
    that distinguishes "the mirror has nothing to screen against" from "the
    strategy is dying" — `LifecycleViewPort.eligibility` deliberately folds them
    together, which is right for a contention race and wrong here. A view
    without `pin` cannot make the distinction, so it never abstains and a stale
    mirror reaches the caller as a capital refusal; that is a property of the
    injected double, and it is why the production default is `MirrorLifecycle`.
    """
    pin = getattr(view, "pin", None)
    if pin is None:
        return view.eligibility(strategy_id), False
    pinned = pin()
    if pinned is None:
        return None, True
    return pinned.eligibility(strategy_id), False


def _capital_refusal(
    verdict: lifecycle_mod.CapitalEligibility, symbol: str
) -> Proposal:
    """§4:284-286's refusal, shaped as a `Proposal` so the Limiter still logs it.

    `NO_SIZE_DENY` and not a new outcome, and not `STALE_MIRROR`: §7 already
    fixes DENY as the shape for "this GO does not become a size", the Allocator
    never invents a size to make a refusal expressible, and minting a sixth
    `ProposalOutcome` member would put a lifecycle decision in the seam's own
    vocabulary. The REASON carries §4's citation, so the Limiter's event log can
    tell a dying strategy from an invalid stop without reading the enum.

    The rationale reports ZERO for every §7 term and `snapshot_version` from the
    screen's own verdict. Zeroes, because nothing was sized — a rationale that
    carried plausible-looking terms for a pass that never ran §7 would be the
    audit trail asserting arithmetic that did not happen.
    """
    return Proposal(
        outcome=ProposalOutcome.NO_SIZE_DENY,
        symbol=symbol,
        strategy_id=verdict.strategy_id,
        contracts=0,
        rationale=SizingRationale(
            binding=BindingConstraint.NONE,
            snapshot_version=(
                -1 if verdict.snapshot_version is None else verdict.snapshot_version
            ),
            risk_contracts=0,
            margin_contracts=0,
            symbol_cap=0,
            headroom=0.0,
            bucket=BUCKET_OF.get(symbol),
            bucket_used=0.0,
            bucket_ceiling=0.0,
            contention=ContentionPolicy.FCFS,
            note=(
                "§4:284-286 capital screen REFUSED before sizing; no §7 term was "
                "computed, so every figure here is zero rather than plausible"
            ),
        ),
        reason=verdict.reason,
    )


def lifecycle_check(pathway: AllocatorPathway) -> lifecycle_mod.LifecycleViewPort:
    """Structural assertion that the screen is still ON the pathway (D3.147).

    `LifecycleViewPort` is `runtime_checkable`, so this is an `isinstance` the
    interpreter performs — the same move `port_check` makes for the cap, and it
    exists for the same reason: D3.147 was a docstring claiming a wiring that
    was not there, and the repair for that class is an assertion, not a sentence.
    Raises rather than returning `None` on absence: a pathway with no screen is
    not a pathway with an optional feature off, it is §4:284-286 unenforced.
    """
    view = pathway._lifecycle  # pylint: disable=protected-access
    if not isinstance(view, lifecycle_mod.LifecycleViewPort):
        raise TypeError(
            "AllocatorPathway holds no LifecycleViewPort — §4:284-286's capital "
            "screen is not on the pass, so a strategy mid-recovery would be "
            "counted normal-and-available while dying"
        )
    return view


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
    "lifecycle_check",
    "port_check",
]
