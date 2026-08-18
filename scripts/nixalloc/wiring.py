# C0302: this module is over pylint's line ceiling and the excess is PROSE —
# three arcs of measured findings kept next to the composition they were found
# in (D3.136's fail-open cap, D3.147's false docstring, and ARC 036's ranking
# consumption with what it deliberately did NOT land). Doctrine B.7 puts the
# argument beside the instrument it argues for; splitting this module to satisfy
# a line counter would move half the reasoning away from the code it explains.
# pylint: disable=too-many-lines
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

---------------------------------------------------------------------------
ARC 036 (sub-agent E) — THE RANKING TABLE IS NOW **READ**, AND WHAT THAT IS NOT
---------------------------------------------------------------------------
The paragraph immediately above was true when it was written and is now half
false, so it is corrected here rather than deleted. ARC 036 Phase 0 froze
`scripts/nixscore/seam.py` (`seam_rev 1.0.0`): a `RankingMirror` that a
consumer feeds from §12.7's state bus and reads with `lookup`, `fresh`,
`span_days` and `arbitrate`. **Until this edit nothing in shipped code called
any of them** — `check_uncalled_entry_points` said so by name, and
`scripts/tests/test_check_uncalled_entry_points.py::_ARC036_PHASE0_CARRIED`
carried the names as an obligation rather than as a note.

This module is the consumer. `_MirrorRankingTable` presents the frozen mirror
as the `RankingTablePort` `nixalloc/contention.py` already reads, and
`AllocatorPathway.propose_contended` runs a race: `contention.rank` ORDERS the
contenders from the live table, `propose` is then called once per contender in
that order, and the capital each sized proposal takes is withheld from the ones
behind it (`_RaceMirror`). **The ordering therefore changes the OUTCOME**, which
is the property that separates a ranking that is read from a ranking that is
merely present: `checks/check_scoring_consumption.py` drives two contenders
against capital for one, then REVERSES the two realized-P&L EMAs and requires
the winner to reverse with them.

**WHAT DID NOT LAND, said plainly so a green here is not read as more.**

1. **The Scoring PROCESS.** Still R5. Nothing in this tree writes a ranking
   table; the mirror is fed by whoever holds the subscriber socket, and in
   production today that is nobody. So the LIVE state of this wiring is still
   §6.6:465's FCFS fallback, and that is exactly what it must be.
2. **The score -> sizing-weight transform.** §6.6:459 gives the Allocator the
   read "to weight sizing" and the spec fixes no transform.
   `contention.NEUTRAL_WEIGHT` is still 1.0 for every contender. What is wired
   is the ORDER, not a weight. **SUPERSEDED BY ARC 037 — see below.**
3. **Recovery reflection** and the rest of the Allocator's Scoring-dependent
   finish. A later arc. **PARTLY SUPERSEDED BY ARC 037 — see below.**
4. **An AWARD.** §6.6:459-460 gives the Allocator the read and the LIMITER the
   arbitration. `propose_contended` emits N `PathwayReport`s and reaches no
   broker; the Limiter's Phase B re-checks every one of them.

**THE IN-RACE CAPITAL ADJUSTMENT IS NOT A PUBLISHED FIGURE, and the honest
statement of that is `_RaceMirror`'s whole docstring.** §3 publishes ONE
versioned picture and this module does not get to invent a second one. What
`_RaceMirror` does is subtract, from the picture handed to contender *k*, the
margin contenders *1..k-1* have already been proposed for in THIS race — a
reservation §3 has not been asked to make yet. Without it a race is not a race:
two contenders read the same untouched `committed`, both size in full, and
"shared capital cannot satisfy them all" (§6.6:431) has no mechanism at all.
The published `version` is untouched, `PathwayReport.race_committed` reports the
adjustment for every contender that received one, and the Limiter's Phase B is
the authority that actually reserves.

---------------------------------------------------------------------------
ARC 037 (sub-agent E) — THE ORDER NOW MOVES THE **SIZE**, AND WHAT IT IS NOT
---------------------------------------------------------------------------
Item 2 above is discharged and item 3 is half discharged, so both are marked in
place rather than deleted — the paragraph that was true when written stays
legible beside the one that supersedes it (directive 6).

**E1 — the weight is THREADED, and this module is only the thread.** The
transform itself is `nixalloc/contention.py`'s (`weight_for`, ordinal in the
RANK and never in the score) and its APPLICATION POINT is `nixalloc/sizing.py`'s
§7:478 risk budget. What lives here is one lookup and one keyword:
`propose_contended` reads each contender's weight out of
`ContentionRanking.weights` and `_propose_one` hands it to
`SizingAllocator.propose`. **No arithmetic over a weight or a score happens in
this file**, which is the same boundary `_MirrorRankingTable` records for the
read: §6.6:461-463 keeps computation out of the consumer, and multiplying a risk
budget here would be §7 arithmetic in a composition layer besides.

**THE NEUTRAL DIRECTION IS THE HALF THAT PROTECTS ORDER FLOW**, and it is
structural rather than tested-into-existence: every FCFS route reaches
`contention._fallback`, which is the ONE constructor for all of them and which
stamps `NEUTRAL_WEIGHT` on every contender. So *Scoring down ⇒ weight 1.0 ⇒
FCFS-neutral sizing* is a property of the fallback's shape, not of a branch here
that could be forgotten — there is no route through `propose_contended` that
reads a weight from anywhere but `ranking.weights`, and `_weight_of` defaults a
missing pair to the same constant.

**E2 — the §4 screen now reflects QUARANTINE as well as in-flight-closing.**
`AllocatorPathway` takes a `quarantine` view and folds it into the default
`MirrorLifecycle` (see `nixalloc/lifecycle.py`, which owns the rule). The gap it
closes is a REAL one and it is stated as a defect rather than as a feature: a
quarantined strategy's rows go CLOSED once the recovery flatten completes, and
until this arc the screen — which reads position rows and nothing else — then
answered ELIGIBLE for a strategy §4:274 says is *"NOT auto-resurrected"*.

**WHAT STILL DID NOT LAND.**

* **The Scoring PROCESS is still R5.** Nothing in this tree writes a ranking
  table, so `available()` answers False, every weight is `NEUTRAL_WEIGHT`, and
  the weighting this module now threads is DORMANT in production exactly as the
  ordering is (CHECK-DEBT D3.263).
* **`SizingRationale.score_weight` is `nixalloc/sizing.py`'s field**, not this
  module's. `PathwayReport.score_weight` is what was REQUESTED; the rationale
  records what was APPLIED. See `WEIGHT_UNSUPPORTED` for the one state in which
  they can differ, and why it is reported rather than denied.
"""

from __future__ import annotations

import dataclasses
import inspect
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from nixalloc import caps, contention
from nixalloc import lifecycle as lifecycle_mod
from nixalloc.seam import (
    BUCKET_OF,
    BindingConstraint,
    ContentionPolicy,
    CorrelationBucket,
    FinancialPicture,
    MirrorPort,
    MirrorSnapshot,
    PositionRow,
    PositionState,
    Proposal,
    ProposalOutcome,
    RankingRow,
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

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at run time
    # TYPING-ONLY, AND IT IS A MEASUREMENT RATHER THAN A STYLE CHOICE — the same
    # one `nixalloc/contention.py` records for `LifecycleViewPort`.
    # `checks/check_allocator_pathway.py`'s can-fail suite copies this module
    # into a throwaway tree from a HAND-MAINTAINED file list that does not carry
    # `scripts/nixscore/` or the `scripts/nixbus/` transport underneath it, so a
    # RUN-TIME first-party import of the seam here would turn most of that suite
    # into "cannot load out of /tmp/...: ModuleNotFoundError" while the gate
    # stayed green on the real tree.
    #
    # The mirror is consumed STRUCTURALLY — this module never constructs a
    # `RankingMirror`, never decodes a snapshot and never touches the transport;
    # it reads four verbs off an object the caller owns. So a typing-only import
    # is the honest shape as well as the cheap one, and the ANNOTATIONS still
    # carry the type: `check_uncalled_entry_points` resolves a receiver by its
    # annotation's bare name, which is how `RankingMirror.lookup` and its three
    # siblings become CALLED-in-shipped-code rather than uncalled surface.
    from nixscore.seam import RankingMirror, Verdict

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
    #: ARC 036. Dollars of margin EARLIER contenders in the same §6.6 race were
    #: already proposed for, and which were therefore withheld from this one.
    #: Zero for a lone GO and for the head of every race. It is reported rather
    #: than folded silently into `headroom` because it is the ONE term in this
    #: report that did not come off the published snapshot (§3) — an auditor
    #: reading `SizingRationale.headroom` against the published `committed` at
    #: `snapshot_version` has to be able to see why the two disagree.
    race_committed: float = 0.0
    #: ARC 037 (E1). §6.6:459's SIZING WEIGHT, as the pathway PASSED it into
    #: §7's pass for this contender — `ContentionRanking.weights[pair]`, which
    #: is `NEUTRAL_WEIGHT` on every FCFS route by construction.
    #:
    #: This is the REQUESTED figure and `SizingRationale.score_weight` is the
    #: APPLIED one; they are two facts, not one restated (directive 3). They
    #: agree whenever the sizing seam accepts a weight, and the gate asserts
    #: that they do. They can only disagree while `weight_gap` is non-empty,
    #: which is the one state in which a weight was computed and dropped.
    score_weight: float = contention.NEUTRAL_WEIGHT
    #: EMPTY when the weight above actually reached §7's risk budget. Non-empty
    #: names WHY it did not — see `AllocatorPathway._weight_kwarg`. It is a
    #: reported string and never a refusal: §6.6:467-468 forbids a scoring
    #: condition halting order flow, and a weight that could not be applied is
    #: a scoring condition.
    weight_gap: str = ""

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


# ---------------------------------------------------------------------------
# ARC 036 — §6.6's ranking table, CONSUMED
# ---------------------------------------------------------------------------

#: §6.6:453 defines the pairwise comparison for exactly TWO contenders: *"two
#: strategies GO on one symbol ⇒ compare the two pair-rows"*. Named rather than
#: written as a bare `2`, because the number is the SPEC'S and not a tuning
#: choice — `RankingMirror.arbitrate` takes two pairs and no more.
PAIRWISE_CONTENDERS = 2

#: The keyword `SizingAllocator.propose` takes §6.6:459's sizing weight on.
#: Named once, because it is read by `inspect` below and written at the one call
#: site, and two spellings of one keyword is a defect that only shows at run time.
WEIGHT_KWARG = "weight"

#: What a `weight_gap` says when the injected sizing pass cannot take a weight.
#: ARC 037 SPLIT THIS WORK ACROSS TWO BLIND BRANCHES: sub-agent B owns
#: `nixalloc/sizing.py` and adds `propose(..., *, weight=NEUTRAL_WEIGHT)` there;
#: this module owns the CALLER. On a tree where only one half has landed the
#: caller must neither crash nor silently drop the figure, so the pathway probes
#: the injected allocator ONCE at construction and REPORTS the shortfall on
#: every report and every outcome. **This is a transition state and it is
#: measurable, not assumed**: `checks/check_allocator_weighting.py` reads the
#: probe and returns GUARDED — never PASS — while it is False, naming the arc
#: that discharges it. When both halves are on one tree the probe answers True
#: and the guard lifts itself with no edit here (CHECK-DEBT D3.320).
WEIGHT_UNSUPPORTED = (
    "scripts/nixalloc/wiring.py:AllocatorPathway: the injected sizing pass takes "
    "no {kwarg!r} keyword, so §6.6:459's weight was COMPUTED and NOT APPLIED — "
    "§7:478's risk budget was sized unweighted. Reported and never denied: "
    "§6.6:467-468 forbids a scoring condition halting order flow"
)


def _takes_weight(propose: object) -> bool:
    """Does this sizing pass accept §6.6:459's weight? Asked ONCE, of the object.

    `inspect.signature` over the bound method, not `hasattr` over the class and
    not a `try/except TypeError` around a live proposal: a `TypeError` raised
    from INSIDE a sizing pass that does take the keyword would be swallowed as
    "unsupported" and the pathway would silently downgrade to unweighted sizing
    on a tree where weighting exists. The question asked here is about the
    SIGNATURE, so it is asked of the signature.

    A `**kwargs` sink counts as accepting it — that is what a decorator or a
    test double wrapping the real pass looks like, and refusing those would make
    the probe report a shortfall that is not there.
    """
    try:
        params = inspect.signature(propose).parameters  # type: ignore[arg-type]
    except TypeError, ValueError:
        return False
    if WEIGHT_KWARG in params:
        return True
    return any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values())


class _MirrorRankingTable:
    """§6.6's ranking table, presented as the port the Allocator already reads.

    **This class is the consumption wiring and it is deliberately the whole of
    it.** `nixalloc/seam.py` declares `RankingTablePort` (`available` + `row`,
    no writer verb) and `nixalloc/contention.py` has read that port since
    ARC 031 — against nothing, because §6.6's writer did not exist. ARC 036
    Phase 0 froze the mirror; this adapter is the join, and it is an ADAPTER
    rather than a reimplementation for doctrine C.9's reason: the mirror owns
    freshness and the O(1) lookup, and a second module deciding either of those
    would be a second authority over one property.

    **NO ARITHMETIC OVER A SCORE HAPPENS HERE.** §6.6:461-463 and §11:595 fix
    the consumer's read as an O(1) table lookup, never math: `available()` asks
    the mirror whether it is fresh and `row()` hands back the pair-row's
    precomputed `realized_ema` unchanged. The one subtraction below is a
    TIMESTAMP, not a score — see `row`.

    Private on purpose. A caller hands `AllocatorPathway` a `RankingMirror` and
    gets the wiring; exposing a second constructible port would be one more way
    to build a pathway whose ranking read is silently absent.
    """

    def __init__(self, mirror: RankingMirror) -> None:
        self._mirror = mirror
        #: THE RACE'S CLOCK, or `None` for wall clock. `RankingTablePort` takes
        #: no `now` — it was declared for a hot path that reads the wall clock —
        #: so a caller with its own clock has nowhere to put it, and the two
        #: reads of the table (`contention.rank` through this port, and
        #: `RankingMirror.arbitrate` directly) would answer against two
        #: different clocks. **MEASURED, not anticipated:** the first drive of
        #: this wiring fed the mirror at t=100.0 and read it at wall clock, so
        #: the port reported the table STALE while the seam ranked it fine, and
        #: `ContentionOutcome.disagreement` is what said so. Set once per race
        #: by `propose_contended`; single-threaded by §2/§5's own loop.
        self.now: float | None = None

    def available(self) -> bool:
        """False when the table is absent or stale — §6.6:465's fallback trigger.

        Delegated to `RankingMirror.fresh`, which is §0i's stale-until-proven-
        fresh predicate: a mirror that has never received a snapshot answers
        False, so an unfed reader falls back rather than reading an empty table
        as an agreeing one.
        """
        return bool(self._mirror.fresh(self.now))

    def row(self, strategy_id: str, symbol: str) -> RankingRow | None:
        """The pair's row, or None. SYNCHRONOUS, O(1), never score math.

        `as_of` is the WHOLE TABLE's freshness stamp, and that is not a
        shortcut: §12.7's mirror model publishes the ranking table as one atomic
        snapshot, so there is no such thing as a per-row age — every row in the
        mirror arrived in the same message. Deriving it as `stamp - age` costs
        one subtraction over a clock and touches no score, which is what
        §6.6:463's *"O(1) table lookup, never math"* forbids.
        """
        hit = self._mirror.lookup(strategy_id, symbol)
        if hit is None:
            return None
        stamp = time.time() if self.now is None else self.now
        age = self._mirror.age_s(stamp)
        return RankingRow(
            strategy_id=hit.strategy_id,
            symbol=hit.symbol,
            score=hit.realized_ema,
            as_of=0.0 if age is None else stamp - age,
        )


class _RaceMirror:
    """The published picture, MINUS what this race has already proposed for.

    `MirrorPort`, wrapping the real one. `spent` is zero for a lone GO and for
    the head of every race, so a pathway that never runs a contended race is
    byte-for-byte the pathway ARC 032 shipped.

    **WHY THIS EXISTS.** §6.6:431 defines contention as *"shared capital
    (liquidity/margin) cannot satisfy them all"*. Two contenders reading one
    untouched `committed` both size in full and nothing is ever contended — the
    race would be a sort with no consequence, and a gate over it would prove
    that a list can be reordered. §3's reservation lifecycle is what makes the
    second contender see the first one's capital as gone; inside ONE race no
    reservation has been made yet, so the pathway carries the figure itself.

    **WHAT IT IS NOT.** It is not a second published snapshot. `version` is the
    real one, `balance` and `positions` are untouched, and the adjustment is
    reported out on `PathwayReport.race_committed` rather than folded silently
    into `headroom`. The Allocator is permissive (§2:40) and the Limiter's
    Phase B re-check is what actually reserves; this only stops the Allocator
    proposing twice against room it has already offered once.

    Mutable, and single-threaded by §2/§5's own loop. A frozen value would mean
    rebuilding `SizingAllocator` per contender, which would put the composition
    root on the per-GO path.
    """

    def __init__(self, inner: MirrorPort) -> None:
        self._inner = inner
        self.spent = 0.0

    def snapshot(self) -> MirrorSnapshot:
        """The published mirror read, with this race's commitment withheld."""
        got = self._inner.snapshot()
        if not self.spent or got.picture is None:
            return got
        return dataclasses.replace(
            got,
            picture=dataclasses.replace(
                got.picture, committed=got.picture.committed + self.spent
            ),
            reason=(
                f"{got.reason}; §6.6 race: {self.spent:.2f} of margin is already "
                "proposed for by an earlier contender in this race and is "
                "withheld from this one (NOT a published figure — §3's version "
                "stamp is unchanged and the Limiter's Phase B is what reserves)"
            ),
        )

    def version(self) -> int:
        """The published stamp, untouched. The adjustment mints no version."""
        return self._inner.version()


@dataclass(frozen=True)
class Go:
    """One strategy GO entering a race, carrying its ARRIVAL position.

    `arrival_seq` is `contention.Contender`'s monotonic counter and it is what
    makes §6.6:465's fallback first-come-FIRST-SERVED rather than an arbitrary
    pick: when the table is absent, stale or tied, the race is ordered by this
    and by nothing else. It is not a timestamp, for the reason `Contender`
    records — two GOs inside one clock tick would tie on a float.
    """

    strategy_id: str
    symbol: str
    side: Side
    stop_ticks: int
    stop_mode: StopMode
    signal_ts: float
    arrival_seq: int = 0


@dataclass(frozen=True)
class ContentionOutcome:  # pylint: disable=too-many-instance-attributes
    """One §6.6 race: how it was ordered, what was read, and every report.

    `reports` is in the ORDER THE RACE WAS RUN, best-first, which is the order
    that decided who got the capital — not the arrival order and not the order
    the caller passed. `order` names the same sequence as `(strategy_id,
    symbol)` pairs so a caller can read the decision without walking reports.

    R0902: nine fields, and every one is a separate FACT about the race — the
    ordering and its reason, the reports, the pairs, the frozen seam's own
    verdict, the two audit terms §16 U5 wants riding the decision, and the two
    ways the read can have gone wrong. Collapsing `pairwise_error` into
    `disagreement`, or the span into the reason string, would report one number
    for two faults and cost the operator the distinction that names the repair
    — the same argument `SizingRationale` records for its own field count.
    """

    #: The ordering `contention.rank` produced, with its own reason and policy.
    ranking: contention.ContentionRanking
    reports: tuple[PathwayReport, ...]
    order: tuple[tuple[str, str], ...]
    #: §6.6:453's two-pair comparison, taken from the FROZEN seam, for a race of
    #: exactly two. `None` for any other size and whenever no mirror was
    #: injected — never a fabricated verdict.
    pairwise: Verdict | None
    #: The EMA span the live table was computed under (§6.6:442). An audit term:
    #: a ranking read without the span it was smoothed over cannot be reproduced.
    span_days: int | None
    table_fresh: bool
    reason: str
    #: Non-empty when a read of the mirror RAISED. §6.6:467-468 forbids a
    #: scoring outage halting order flow, so a mirror that throws becomes a
    #: reported string and an FCFS race — never a propagated exception. Kept
    #: separate from `disagreement` because "the two readers disagreed" and
    #: "one reader could not answer" are different faults with different
    #: repairs, and one number for two faults is the ambiguity §7.12/1 refuses.
    pairwise_error: str = ""
    #: Non-empty when `contention.rank`'s ordering and the frozen seam's own
    #: `arbitrate` disagreed about a two-contender race. Two independent reads
    #: of one table reaching different winners is a DEFECT, not a preference,
    #: and it is reported rather than silently resolved in favour of either.
    disagreement: str = ""
    #: ARC 037 (E1). What the §6.6:459 SIZE weighting did on this race, in one
    #: sentence: the policy, how many DISTINCT weights the ranking produced, and
    #: whether the sizing seam accepted them. The weights themselves are not
    #: restated — they are `ranking.weights`, and each contender's is on its own
    #: `PathwayReport.score_weight` (directive 3).
    weighting: str = ""


class AllocatorPathway:  # pylint: disable=too-many-instance-attributes
    """Mirror → fast-drop → size → cap, one GO, one `PathwayReport`.

    R0902: it holds one field per INJECTED PORT plus the two race-scoped
    wrappers, and every one of them is a seam some other module owns — the cap
    adapter, the §4 lifecycle view, the published mirror, the race mirror, the
    §6.6 ranking mirror, its port adapter, and the sizing allocator. Folding two
    together to clear a count would hide which port a defect moved, which is the
    diagnosis this composition layer exists to make possible.

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
        ranking: RankingMirror | None = None,
        quarantine: lifecycle_mod.QuarantineViewPort | None = None,
    ) -> None:
        self._cap = bucket_cap
        #: ARC 032. §4:284-286's capital screen. Defaulted to a view over THIS
        #: pathway's own mirror rather than to `None`, and the default is the
        #: decision: an opt-in safety screen is off in every caller that
        #: forgets it, and D3.136 is this arc's evidence that a defaulted-off
        #: safety input is not a smaller version of a safety input.
        self._lifecycle = (
            lifecycle_mod.MirrorLifecycle(mirror, quarantine)
            if lifecycle is None
            else lifecycle
        )
        #: ARC 037 (E2). §4:273's book, folded into the DEFAULT view above. It
        #: is deliberately NOT applied on top of an INJECTED `lifecycle`: a
        #: caller that supplies its own view owns what that view screens on, and
        #: a pathway that silently re-wrapped it would give one property two
        #: authorities. Kept as a field so the state is READABLE — a caller that
        #: passed both a book and its own view has had the book accepted and
        #: ignored, and `check_allocator_weighting` asserts against these two
        #: attributes rather than against a sentence (D3.147's repair shape).
        self._quarantine = quarantine
        #: ARC 036. The PUBLISHED mirror, kept because `_race` deliberately
        #: hands out an adjusted picture and the unadjusted one is still needed
        #: to price a contender's commitment.
        self._published = mirror
        self._race = _RaceMirror(mirror)
        #: ARC 036. §6.6's mirror, or `None`. `None` is not a degraded mode that
        #: needs special handling — `contention.rank(…, None)` is §6.6:465's
        #: locked FCFS fallback, which is the live configuration until the
        #: Scoring process exists.
        self._ranking_mirror = ranking
        self._ranking = None if ranking is None else _MirrorRankingTable(ranking)
        self._allocator = SizingAllocator(
            mirror=self._race,
            tradability=tradability,
            instruments=instruments,
            knobs=knobs,
            bucket_cap=bucket_cap,
        )
        #: ARC 037 (E1). Whether §6.6:459's weight can reach §7's risk budget on
        #: THIS tree. Probed ONCE, at construction, off the object that will be
        #: called — never per GO, because §16 gives the Allocator per-GO-only
        #: work and an `inspect.signature` on the hot path is exactly the cost
        #: `check_scoring_consumption`'s ARM 5 budget exists to refuse.
        self._weight_kwarg = _takes_weight(self._allocator.propose)

    def propose(
        self,
        strategy_id: str,
        symbol: str,
        side: Side,
        stop_ticks: int,
        stop_mode: StopMode,
        signal_ts: float,
    ) -> PathwayReport:
        """One GO in, one report out. Synchronous, single-pass (§16 U1).

        **A LONE GO IS A RACE OF ONE (ARC 036), and the delegation is the
        point.** Routing every GO through `propose_contended` is what makes the
        §6.6 read unconditional: a ranking consulted only by the method a caller
        remembers to reach for is a ranking that is absent from most GOs, and
        that is the shape ARC 033's cap shipped in. A race of one carries no
        in-race commitment (`_RaceMirror.spent` is reset to zero on entry) and
        no pairwise verdict (§6.6:453 compares TWO pair-rows), so the report is
        byte-for-byte the one this method returned before the wiring landed.
        """
        return self.propose_contended(
            (
                Go(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    side=side,
                    stop_ticks=stop_ticks,
                    stop_mode=stop_mode,
                    signal_ts=signal_ts,
                ),
            )
        ).reports[0]

    def propose_contended(
        self, gos: Sequence[Go], *, now: float | None = None
    ) -> ContentionOutcome:
        """§6.6's race: ORDER by the ranking table, then size in that order.

        Synchronous, total, and it **never denies for a scoring reason**. Every
        route by which the ranking can be unavailable — no mirror injected, a
        mirror that never received a snapshot, a stale table, a foreign writer,
        an absent pair-row, tied EMAs, a port that raises — reaches
        `contention.rank`'s FCFS fallback, which returns the ARRIVAL order and a
        reason. §6.6:467: *"Ranking is an optimization, never a safety gate: a
        scoring outage must NEVER halt order flow."* There is no branch below
        that can turn a ranking fault into a refusal, and
        `check_scoring_consumption` drives every one of those routes and
        requires a proposal out of each.

        The §4:284-286 capital screen and §0i's stale-mirror fast-drop are NOT
        re-implemented here: each contender goes through `propose`, which owns
        both, so a dying strategy or a half-built mirror is refused by exactly
        the rule that already refuses it (doctrine C.9).
        """
        contenders = tuple(
            contention.Contender(
                strategy_id=go.strategy_id,
                symbol=go.symbol,
                arrival_seq=go.arrival_seq,
            )
            for go in gos
        )
        if self._ranking is not None:
            self._ranking.now = now
        ranking = contention.rank(contenders, self._ranking)
        pairwise, disagreement, failed = self._pairwise(contenders, ranking, now)
        span, fresh, audit_failed = self._audit_terms(now)
        by_pair = {(go.strategy_id, go.symbol): go for go in gos}
        self._race.spent = 0.0
        reports: list[PathwayReport] = []
        for contender in ranking.ordering:
            reports.append(
                self._run_one(
                    by_pair[contender.pair],
                    _weight_of(ranking, contender.pair),
                )
            )
        return ContentionOutcome(
            ranking=ranking,
            reports=tuple(reports),
            order=tuple(contender.pair for contender in ranking.ordering),
            pairwise=pairwise,
            span_days=span,
            table_fresh=fresh,
            reason=(
                f"{len(reports)} contender(s) sized in "
                f"{'ARRIVAL (FCFS)' if ranking.is_fallback else 'RANKED'} order: "
                f"{ranking.reason}"
            ),
            pairwise_error="; ".join(part for part in (failed, audit_failed) if part),
            disagreement=disagreement,
            weighting=_weighting_note(ranking, self._weight_kwarg),
        )

    def _audit_terms(self, now: float | None) -> tuple[int | None, bool, str]:
        """`(span_days, table_fresh, error)`. §16 U5's audit reads, made TOTAL.

        These two are REPORTING terms — the EMA span the table was smoothed over
        and whether it was fresh — and neither steers a proposal. A mirror that
        raises while being asked for them would nonetheless kill the race, which
        is §6.6:467-468's forbidden direction reached through an audit field
        rather than through a decision. So the failure becomes a string.
        """
        mirror: RankingMirror | None = self._ranking_mirror
        if mirror is None:
            return None, False, ""
        try:
            return mirror.span_days, bool(mirror.fresh(now)), ""
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return (
                None,
                False,
                (
                    f"the ranking mirror raised {type(exc).__name__}: {exc} while "
                    "being read for its span and freshness — reported, because "
                    "§6.6:467 forbids a scoring outage halting order flow"
                ),
            )

    def _pairwise(
        self,
        contenders: Sequence[contention.Contender],
        ranking: contention.ContentionRanking,
        now: float | None,
    ) -> tuple[Verdict | None, str, str]:
        """§6.6:453's two-pair comparison, taken from the FROZEN seam.

        `(verdict, disagreement, error)`. It never raises: a mirror that throws
        becomes the third element and an FCFS race, because §6.6:467-468 makes a
        scoring outage a reported condition and never a halt.

        Run as a SECOND, independent read of the same table, and compared with
        the ordering `contention.rank` produced. That is not redundancy: `rank`
        reads the table through `RankingTablePort` and sorts N contenders, while
        `RankingMirror.arbitrate` is the seam's own verb for the exactly-two
        case and carries §18's reason for whichever of the five FCFS triggers
        fired. Two readers of one table reaching different winners is a defect
        in one of them, and the only way to see it is to run both.

        `first` is the EARLIER ARRIVAL, never the higher-ranked contender —
        that is what makes the seam's fallback first-come-first-served, and
        handing it the ranked order instead would make FCFS agree with the
        ranking by construction.
        """
        mirror: RankingMirror | None = self._ranking_mirror
        if mirror is None or len(contenders) != PAIRWISE_CONTENDERS:
            return None, "", ""
        arrival = contention.fcfs_order(contenders)
        first, second = arrival[0].pair, arrival[1].pair
        try:
            verdict: Verdict = mirror.arbitrate(first, second, now)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return (
                None,
                "",
                (
                    f"the frozen §6.6 seam's arbitrate raised {type(exc).__name__}: "
                    f"{exc} — §6.6:467-468 makes a scoring outage a REPORTED "
                    "condition and never a halt, so the race ran on contention.rank's "
                    "fallback alone"
                ),
            )
        if verdict.fell_back or not ranking.ordering:
            return verdict, "", ""
        head = ranking.ordering[0].pair
        if verdict.winner == head:
            return verdict, "", ""
        return (
            verdict,
            (
                f"scripts/nixalloc/wiring.py:_pairwise: the frozen §6.6 seam ranked "
                f"{verdict.winner!r} first ({verdict.reason}) while contention.rank "
                f"ordered {head!r} first ({ranking.reason}) — two reads of ONE "
                "ranking table disagreed, so at least one of them is wrong about "
                "the table and the race was run on the second"
            ),
            "",
        )

    def _run_one(self, go: Go, weight: float) -> PathwayReport:
        """One contender, sized against what the race has already committed."""
        withheld = self._race.spent
        report = dataclasses.replace(
            self._propose_one(go, weight), race_committed=withheld
        )
        self._race.spent = withheld + self._committed_by(report, go.symbol)
        return report

    def _committed_by(self, report: PathwayReport, symbol: str) -> float:
        """Margin dollars a sized proposal takes off the table for its rivals.

        Priced from the PUBLISHED `margin_per_contract` (§3), never from a
        second source: §6.4 refuses a sizing pass that reads one field fresh and
        another stale, and a per-symbol margin recovered from anywhere but the
        snapshot the proposal was sized against would be exactly that.

        A symbol absent from the published margin table prices at zero and the
        race becomes a plain ordering for it. That direction is deliberate: it
        can only ADMIT the next contender, which is the permissive Allocator's
        direction (§2:40) and the one the Limiter's Phase B re-checks. The
        symbol cannot in fact be absent here — `SizingAllocator` returns
        `NOT_TRADABLE` for a symbol missing from the margin cache and never
        reaches `SIZED` — so this is a floor, not a live path.
        """
        if report.proposal.outcome is not ProposalOutcome.SIZED:
            return 0.0
        picture = self._published.snapshot().picture
        if picture is None:
            return 0.0
        return report.proposal.contracts * float(
            picture.margin_per_contract.get(symbol, 0.0)
        )

    def _propose_one(self, go: Go, weight: float) -> PathwayReport:
        """The single-GO pass, plus §6.6:459's weight. §16 U1's single pass.

        **THE WEIGHT IS PASSED HERE AND NOWHERE ELSE.** §6.6:459 gives the
        Allocator the read *"to weight sizing"*, and the transform's APPLICATION
        POINT is §7:478's per-trade risk budget, inside `nixalloc/sizing.py`.
        This method hands the figure over; it does not multiply anything, and it
        must not — a weight applied here and again inside the sizing pass would
        be two authorities over one number, and a weight applied ONLY here would
        put §7 arithmetic in the composition layer that doctrine C.9 keeps it
        out of. `check_allocator_weighting` proves the shipped call site by
        AST — the keyword appears at exactly one call in this file.
        """
        refusal = self._screen_capital(go.strategy_id, go.symbol)
        if refusal is not None:
            # The §4 screen refused BEFORE §7 ran, so no weight was applied —
            # but the figure the pathway WOULD have passed still rides the
            # report. A refusal reporting a neutral weight it never computed
            # would tell an auditor the race was unweighted when it was not.
            return dataclasses.replace(refusal, score_weight=weight)
        extra = {WEIGHT_KWARG: weight} if self._weight_kwarg else {}
        proposal = self._allocator.propose(
            strategy_id=go.strategy_id,
            symbol=go.symbol,
            side=go.side,
            stop_ticks=go.stop_ticks,
            stop_mode=go.stop_mode,
            signal_ts=go.signal_ts,
            **extra,
        )
        blind = tuple(self._cap.unpriced) if self._cap is not None else ()
        stray = tuple(self._cap.unbucketed) if self._cap is not None else ()
        return PathwayReport(
            proposal=proposal,
            cap_blind=blind,
            cap_incomplete=bool(blind),
            cap_unbucketed=stray,
            score_weight=weight,
            weight_gap=(
                ""
                if self._weight_kwarg
                else WEIGHT_UNSUPPORTED.format(kwarg=WEIGHT_KWARG)
            ),
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


def _weight_of(ranking: contention.ContentionRanking, pair: tuple[str, str]) -> float:
    """This contender's §6.6:459 sizing weight. ONE dict lookup, no arithmetic.

    `NEUTRAL_WEIGHT` for a pair the ranking did not weight, which is the same
    number every FCFS route already carries — §6.6:465-466's fallback is
    *"structurally neutral (favors no symbol)"*, and a missing weight defaulting
    to anything else would make an absent score re-size a position.
    """
    return float(ranking.weights.get(pair, contention.NEUTRAL_WEIGHT))


def _weighting_note(ranking: contention.ContentionRanking, applied: bool) -> str:
    """One sentence about what the SIZE weighting did on this race.

    Reports the number of DISTINCT weights rather than the weights themselves:
    the values are `ranking.weights` and each contender's is on its own report,
    and the fact an operator cannot read off either of those is whether the race
    was weighted UNIFORMLY — which is the state a decorative transform produces
    and the state §6.6:465's fallback is REQUIRED to produce.
    """
    distinct = len(set(ranking.weights.values()))
    return (
        f"policy={ranking.policy.value}; {distinct} distinct sizing weight(s) "
        f"over {len(ranking.weights)} contender(s); "
        + (
            "applied to §7:478's risk budget"
            if applied
            else WEIGHT_UNSUPPORTED.format(kwarg=WEIGHT_KWARG)
        )
    )


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
    "PAIRWISE_CONTENDERS",
    "WEIGHT_KWARG",
    "WEIGHT_UNSUPPORTED",
    "AllocatorPathway",
    "BucketCapAdapter",
    "ContentionOutcome",
    "ExposureSourcePort",
    "Go",
    "PathwayReport",
    "ProposalOutcome",
    "PublishedExposures",
    "lifecycle_check",
    "port_check",
]
