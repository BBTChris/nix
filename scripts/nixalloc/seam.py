"""The Allocator's frozen consumer-side seam — types and ports, no behaviour.

ARC 031 / Phase 0.6, and it is the mirror image of `nixrisk/seam.py` (ARC 028 /
0.6): landed BEFORE any implementation so the mirror consumer, the sizing
pathway and the correlation caps are built against a settled boundary instead
of against each other.

WHAT IS IN HERE. Value types, enumerations, and `Protocol` declarations. No
rule, no arithmetic, no I/O, no policy.

WHAT IS DELIBERATELY *NOT* IN HERE, because saying so is the point:

* **The financial-picture schema.** `FinancialPicture`, `PositionRow` and
  `PositionState` are IMPORTED from `nixrisk.seam` and re-exported, never
  restated. §6.4 fixes one snapshot under "one writer and one version stamp",
  and §3 says both the Allocator (margin-contracts sizing) and the Limiter
  (size-dependent gate) read **the same versioned row** — *identical bytes by
  construction*. Two declarations of one wire contract cannot be identical by
  construction; they can only be identical by inspection, which is the thing
  that stops happening. `check_allocator_seam` asserts the IDENTITY of those
  objects, not their shape.
* **The Scoring process and any EMA math** (§6.6). This seam declares the
  ranking-table READ port and nothing that writes it: Scoring is R5 and does
  not exist. "Nobody but the Scoring process COMPUTES the score" is a §6.6
  lock, so a `compute`/`publish` verb here would be the authority violation
  written into the boundary.
* **Blackout/calendar windows** (R4) and **the strategy FSM** (a separate
  module, §2).

---

## THE AUTHORITY SPLIT, WRITTEN INTO THE TYPES (§2, §3)

The Allocator is **permissive**. The seam enforces that structurally rather
than by asking implementers to remember it:

1. **`MirrorPort` declares no mutating verb.** There is no `publish`, no
   `set`, no `update`, no `apply`. Its only verbs return.
2. **Every value type is a frozen dataclass.** A consumer holding a mutable
   `FinancialPicture` could edit a published field in place and every later
   reader in that process would see the edit — a write to canonical state
   that never left the process and would appear nowhere in the Limiter's event
   log. Frozen is what makes A4's "read-only proven by ATTEMPT" a
   `FrozenInstanceError` rather than a code review.
3. **The Allocator's output type is `Proposal`, and it is not an order.**
   `ProposedOrder` (the Limiter's own type) rides inside it as a field that is
   `None` on every non-sizing outcome. Nothing here reaches a broker; §3's
   single pass sends the proposal to the Risk Engine, which decides.

---

## SYNCHRONOUS OR ASYNCHRONOUS — declared per verb, with the reasoning

`nixrisk/seam.py` declared every verb synchronous and gave a per-verb reason.
**Every verb in THIS module is synchronous too, and the reasons are different
ones** — a blanket "same as the Limiter" would be a style rule wearing an
argument's clothes.

* **`MirrorPort.snapshot` — SYNCHRONOUS.** §12.7 makes the mirror a private,
  process-local, read-only copy and the read "O(1) local, no cross-core
  contention". There is no I/O to await: the bytes are already in this
  process's memory, put there by the subscriber loop. An `async def snapshot`
  would declare a suspension point in the middle of a sizing pass, and §3's
  guarantee is that the Allocator sizes on ONE version — a pass that could
  suspend between reading balance and reading the position table is exactly
  the cross-field skew §6.4 refuses ("independent tables tick on independent
  clocks"), reintroduced inside a single table.
* **`MirrorPort.version` — SYNCHRONOUS**, and it exists so a caller can prove
  two reads came from one snapshot without trusting that they did.
* **`RankingTablePort.row` / `.available` — SYNCHRONOUS.** §6.6 fixes the read
  as an **O(1) table lookup, never math**, on a hot path, and the fallback is
  the whole point: "a scoring outage must NEVER halt order flow". An awaitable
  lookup against a dead publisher is a place order flow can stall; a
  synchronous read of an absent table returns `None` immediately and FCFS
  proceeds.
* **`TradabilityCachePort.tradable` — SYNCHRONOUS.** §16 U1 keeps "never size
  a dead signal" as a fast-drop **against the same cache**, before sizing. A
  suspension point there is a window in which the pass has neither dropped nor
  sized, which is the state §5's single-threaded loop exists to make
  impossible.
* **`AllocatorPort.propose` — SYNCHRONOUS.** §2 makes the Allocator
  single-threaded and §16 upholds it ("µs sizing, no saturation at N≤5"), and
  §16 U1 makes the pathway single-pass Strategy → Allocator → Risk Engine. A
  coroutine has no bounded cost, so the per-GO-only claim over it would be
  unfalsifiable — the same objection `nixrisk/seam.py` raises against an
  `async def evaluate`, reached from the other side of the hop.

---

## §0i — THE MIRROR IS STALE-UNTIL-PROVEN-FRESH, and the type says so

§12.7: snapshot-on-subscribe is "mandatory, not polish", and a consumer whose
mirror is incomplete is "treated as stale ⇒ fast-drop/deny until snapshot
lands". `MirrorSnapshot` is therefore never a bare `FinancialPicture`: it is a
state plus an optional picture plus the reason, and `sizeable` is the single
predicate a sizing pass may consult. The default-constructed value is
`EMPTY`, not `FRESH` — a mirror that has never heard from the Limiter must
not be indistinguishable from a quiet, healthy one (ARC 027's `XPUB_VERBOSE`
finding, which is the same hazard on the publisher's side).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nixrisk.seam import (
    FinancialPicture,
    PositionRow,
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
)

# pylint: disable=too-many-instance-attributes
# `SizingRationale` carries exactly the terms §16 U5 requires to ride the order
# message ("binding constraint + input snapshot"), which is twelve: the binding
# constraint, the snapshot version every term was computed against, the three
# candidate sizes §7's `min(...)` compares, the headroom §16 U2 defines, the
# bucket and its used/ceiling pair, the contention policy, the §6.6:459 score
# weight that multiplied the risk budget (ARC 037), and a free note.
# Dropping one to satisfy a threshold of seven would either lose an audit term
# or nest it, and a nested term is one the Limiter's event log has to read
# SEPARATELY — the cross-read §3's atomicity rule exists to forbid, reproduced
# in the audit trail. Same reasoning `nixrisk/seam.py` records for its own three.
#
# pylint: disable=too-few-public-methods
# `MirrorPort`, `RankingTablePort`, `TradabilityCachePort` and `AllocatorPort`
# are Protocols with exactly the verbs the spec gives them. A boundary is not
# improved by inventing a second method so a class-shape heuristic is satisfied;
# every verb invented here is authority granted (§2).
#
# pylint: disable=too-many-arguments,too-many-positional-arguments
# `AllocatorPort.propose` takes exactly the fields §2's component table says a
# GO carries (direction, symbol, strategy_id, signal_ts, stop as tick distance +
# stop_mode). Collapsing them into a `Go` struct is a real option and a real
# decision -- it is deferred to R3-B with the strategy FSM, which is the module
# that OWNS that message shape (§2); minting the struct here would put the
# strategy's wire type in the Allocator's seam.

#: Re-exported so a consumer imports the ONE definition from either package and
#: gets the same object. Listed explicitly rather than left to `import *`,
#: because `check_allocator_seam` asserts object IDENTITY against
#: `nixrisk.seam` and a wildcard would hide which names are load-bearing.
__all__ = [
    "BUCKET_OF",
    "MIRRORED_FIELDS",
    "POSITION_ROW_FIELDS",
    "SEAM_REV",
    "STOP_DISTANCE_FIELD",
    "AllocatorPort",
    "BindingConstraint",
    "ContentionPolicy",
    "CorrelationBucket",
    "FinancialPicture",
    "MirrorPort",
    "MirrorSnapshot",
    "MirrorState",
    "PositionRow",
    "PositionState",
    "Proposal",
    "ProposalOutcome",
    "ProposedOrder",
    "RankingRow",
    "RankingTablePort",
    "Side",
    "SizingRationale",
    "StopMode",
    "TradabilityCachePort",
]

#: This seam's own revision. Bumped when a declared property changes, so a
#: consumer built against an older shape can refuse rather than mis-read —
#: the same role `contract_rev` plays in `nix_strategy_contract_v1.1.md` §3.
SEAM_REV = "1.1.0"

#: **ARC 032 BUMPED THIS 1.0.0 -> 1.1.0, AND ONLY BECAUSE THE WIRE ACTUALLY
#: CHANGED.** ARC 031 recorded `1.1.0` as a PLANNED target and deliberately
#: left the literal at `1.0.0`, on the stated rule that the literal moves when
#: the bytes move and not when a decision is taken. The bytes have now moved:
#: `nixrisk.seam.PositionRow` carries `stop_distance`, `nixrisk.picture`
#: encodes and decodes it, and `WIRE_SCHEMA` went `1 -> 2` in the same edit.
#: A consumer built against `1.0.0` must refuse this snapshot rather than
#: mis-read it, which is the whole job of the number.
#:
#: The ruling this discharges, kept because the argument is the durable part:
#:
#: ARCHITECT RULING on CHECK-DEBT **D3.136**, OPTION A (ARC 031, Phase 5):
#: `PositionRow` gains **`stop_distance`**. §7:501 prices bucket exposure as
#: `(stop_ticks + slippage_pad) × tick_value × contracts`, so applying the
#: correlation cap to positions ALREADY held needs each one's stop distance —
#: and the published row carries none, so today an unpriced position values at
#: ZERO, the bucket reads EMPTIER than it is, and the cap FAILS OPEN by
#: admitting more. A safety input that fails open is the direction that matters,
#: and `check_allocator_pathway` ARM 3 already drives both directions.
#:
#: The ruling picked the SKEW-FREE fix. `stop_distance` rides the SAME versioned
#: snapshot as `balance` and `positions` — one more field under ONE writer and
#: ONE version stamp (§6.4b's principle). It is explicitly NOT the stop-book
#: read: the stop book is a SECOND table, and joining it to this one is the
#: cross-table skew §6.4 forbids in the same breath as it fixes one snapshot.
#:
#: **BUILT IN ARC 032 (R3-B).** The Limiter (sole writer) added the field, the
#: codec carries it both directions, and the one-versioned-row identity was
#: RE-PROVEN on the WIDER row by `check_picture_atomicity` rather than assumed
#: to survive the widening.
#:
#: **ONE SENTENCE OF ARC 031's RULING WAS WRONG ON THE FACTS, and correcting it
#: is worth more than repeating it.** It said *"`MIRRORED_FIELDS` above gains
#: it"*. `MIRRORED_FIELDS` pins the fields of **`FinancialPicture`**, and
#: `stop_distance` is a field of **`PositionRow`** — a member of the
#: `positions` tuple, one level down. Adding the name to `MIRRORED_FIELDS`
#: would have made the tuple disagree with `dataclasses.fields(FinancialPicture)`
#: and reddened `check_allocator_seam` on the spot. The invariant the sentence
#: was reaching for is real and is honoured by `POSITION_ROW_FIELDS` below: the
#: published row's schema is PINNED TO A LITERAL at `SEAM_REV`, so widening it
#: costs a deliberate edit here. The spelling was a sketch; the invariant binds
#: (§0b).
#:
#: The row's own field list is an extension of a frozen enumeration (§3:159
#: names `symbol, strategy_id, size, margin, state`), recorded as **`SPEC-A9`**.

#: THE PINNED SCHEMA at `SEAM_REV`. Spelled out, and the spelling is the point.
#:
#: MEASURED, not reasoned: the first draft of this tuple was DERIVED —
#: `tuple(f.name for f in dataclasses.fields(FinancialPicture))` — on the
#: argument that a derivation can never go stale. It cannot go stale and it
#: also cannot NOTICE: `check_allocator_seam`'s can-fail suite renamed each
#: published field in turn and the gate stayed GREEN on eight of nine, because
#: the derivation moved with the rename. Only `version` reddened, and only
#: because `VERSION_FIELD` below was a literal. That is precisely the
#: ARC 028/029 seam-gate defect — a gate that passes on a renamed field —
#: rebuilt one arc later by an argument that sounded like doctrine C.4.
#:
#: So the pin is a literal, checked against `dataclasses.fields()` by the gate.
#: C.4 forbids a GATE anchoring to something that moves; a versioned CONTRACT
#: pinning the schema it was built against is the opposite move, and it is the
#: same one `nix_strategy_contract_v1.1.md` §3 makes with `contract_rev`.
#: Changing the published snapshot therefore costs an edit here and a
#: `SEAM_REV` bump — which is the deliberate, reviewable act a wire-contract
#: change should be.
MIRRORED_FIELDS: tuple[str, ...] = (
    "version",
    "published_ts",
    "balance",
    "positions",
    "margin_per_contract",
    "sum_open_margin",
    "sum_reservations",
    "committed",
    "deployable",
)

#: The version stamp's field name. §3's atomicity rule is checkable from
#: outside ONLY through this field: a consumer that observes a balance and a
#: position table bearing different versions has observed a torn read.
VERSION_FIELD = "version"

#: THE PINNED SCHEMA OF ONE PUBLISHED **ROW** at `SEAM_REV`. A literal, for the
#: identical reason `MIRRORED_FIELDS` is one, and it is new in ARC 032 because
#: until ARC 032 **nothing in this tree pinned it at all**.
#:
#: MEASURED, and this is the gap the widening exposed rather than created:
#: `check_limiter_seam` pins the field names of `FinancialPicture` (nine
#: entries, each with its §3 reason) and `check_allocator_seam` ARM 2 compares
#: `MIRRORED_FIELDS` against `dataclasses.fields(FinancialPicture)`. **Neither
#: names a single field of `PositionRow`.** So on the tree as it stood, renaming
#: `PositionRow.margin` to `PositionRow.margn`, or DELETING `state`, changed the
#: published wire and left every seam gate green. The nine-field pin was doing
#: its job one level too high, and a widening was the thing that made anyone
#: look.
#:
#: Pinned as a literal and checked against `dataclasses.fields(PositionRow)` by
#: `check_allocator_seam`, never DERIVED from it. ARC 031 measured why: its
#: first `MIRRORED_FIELDS` was derived, its can-fail renamed each published
#: field in turn, and the gate stayed GREEN on eight of nine because the
#: derivation moved with the rename. A derivation cannot go stale and it also
#: cannot NOTICE.
POSITION_ROW_FIELDS: tuple[str, ...] = (
    "trade_id",
    "symbol",
    "strategy_id",
    "size",
    "margin",
    "state",
    #: ARC 032, `SEAM_REV 1.1.0`, `SPEC-A9`. §7:501's exposure unit, for the
    #: positions already held.
    "stop_distance",
)

#: The published row's stop-distance field name, pinned separately for the same
#: reason `VERSION_FIELD` is pinned separately: §7's correlation cap is
#: computable from the published snapshot ONLY through this field, so dropping
#: or renaming it does not make the cap wrong — it makes the cap FAIL OPEN
#: again, silently, which is strictly worse than making it fail. A rename
#: caught by `POSITION_ROW_FIELDS` alone would be reported as "the schema
#: moved"; this one is reported as "the thing that closed D3.136 is gone".
STOP_DISTANCE_FIELD = "stop_distance"


# ---------------------------------------------------------------------------
# The mirror (§3, §12.7, §0i)
# ---------------------------------------------------------------------------


class MirrorState(enum.Enum):
    """What this process's private copy of the financial picture actually is.

    Four values and not two, because "not fresh" hides the distinction that
    matters operationally: a mirror that never subscribed, a mirror whose
    snapshot is still arriving, and a mirror whose snapshot arrived and then
    aged out are three different faults with three different repairs. All
    three refuse sizing identically, which is the safety property; telling
    them apart is what makes the alert actionable.
    """

    #: No snapshot has ever been received. The default, deliberately.
    EMPTY = "empty"
    #: A snapshot is arriving and is not yet complete or not yet stamped.
    #: §12.7: "never sizes on a half-built mirror".
    PARTIAL = "partial"
    #: Complete, stamped, and inside the freshness threshold.
    FRESH = "fresh"
    #: Complete once, but the freshness stamp is past threshold (§6.4).
    STALE = "stale"


@dataclass(frozen=True)
class MirrorSnapshot:
    """One read of the mirror: a state, the picture if there is one, and why.

    `reason` is not decoration. §12.7's hazard is that an absent snapshot
    looks exactly like a quiet feed, so a refusal that cannot say WHICH of the
    three non-sizing states it is in reproduces that ambiguity one layer up.
    """

    state: MirrorState = MirrorState.EMPTY
    picture: FinancialPicture | None = None
    reason: str = "no snapshot has been received"

    @property
    def sizeable(self) -> bool:
        """The ONE predicate a sizing pass may consult (§0i).

        A single expression over this object's own fields, deliberately: an
        implementation is free to decide freshness, and is not free to decide
        that a `PARTIAL` mirror is sizeable after all.
        """
        return self.state is MirrorState.FRESH and self.picture is not None


@runtime_checkable
class MirrorPort(Protocol):
    """The Allocator's private read-only mirror of the financial picture.

    §12.7's mirror model, consumer side. **There is no mutating verb here and
    that absence is the declaration** — the Limiter's `FinancialPicturePort`
    has `publish`, this has nothing that takes a picture as an argument.
    """

    def snapshot(self) -> MirrorSnapshot:
        """The current mirror state. SYNCHRONOUS — a local, O(1) read."""

    def version(self) -> int:
        """The stamp on the held snapshot, or a negative value when there is none.

        Negative rather than zero: zero is a plausible first version and a
        caller comparing `version() == 0` against an unsubscribed mirror would
        read "never received" as "received version 0".
        """


# ---------------------------------------------------------------------------
# Tradability (§16 U1 — never size a dead signal)
# ---------------------------------------------------------------------------


@runtime_checkable
class TradabilityCachePort(Protocol):
    """The same cache the Limiter's Phase A fast-drop reads (§16 U1, §6.4).

    Read-only, and the reason it lives on the Allocator side at all is U1: the
    single-pass routing means the drop happens HERE, before any sizing
    arithmetic, rather than by a round trip through the Limiter.
    """

    def tradable(self, symbol: str) -> tuple[bool, str]:
        """`(tradable, reason)`. SYNCHRONOUS. The reason is required when False."""


# ---------------------------------------------------------------------------
# Correlation buckets (§7, locked)
# ---------------------------------------------------------------------------


class CorrelationBucket(enum.Enum):
    """§7's static buckets. Static is a §16 decision, not an omission —
    dynamic correlation is a research project and violates determinism."""

    EQUITIES = "equities"
    ENERGY = "energy"
    METALS = "metals"
    RATES = "rates"


#: §7's symbol → bucket map. The cap is SAME-BUCKET ONLY: positions in
#: different buckets do not constrain each other through this rule.
#: `check_allocator_seam` derives the expected mapping from the frozen spec's
#: own sentence, so this table is checkable rather than asserted.
BUCKET_OF: Mapping[str, CorrelationBucket] = {
    "ES": CorrelationBucket.EQUITIES,
    "NQ": CorrelationBucket.EQUITIES,
    "CL": CorrelationBucket.ENERGY,
    "GC": CorrelationBucket.METALS,
    "ZN": CorrelationBucket.RATES,
}


# ---------------------------------------------------------------------------
# Contention (§6.6) — the READ seam, with the writer absent
# ---------------------------------------------------------------------------


class ContentionPolicy(enum.Enum):
    """How a contention race is settled. §6.6 locks both values.

    `PERFORMANCE_WEIGHTED` is declared and NOT reachable in this arc: the
    Scoring process is R5 and no writer for the ranking table exists, so the
    table is permanently absent and `FCFS` is the state the whole system runs
    in. Declaring the value the design specifies, while the code can only
    reach the fallback, is honest; omitting it would make a later addition
    look like a design change rather than an implementation landing.
    """

    PERFORMANCE_WEIGHTED = "performance_weighted"
    FCFS = "fcfs"


@dataclass(frozen=True)
class RankingRow:
    """§6.6's stored unit: ONE row per `(strategy_id, symbol)` pair.

    Keyed on the pair and not the symbol, because that is the only keying
    under which score survives process death (§4) and quarantine removes
    exactly one strategy's rows. Any per-symbol figure is a derived display
    aggregate and is never this.
    """

    strategy_id: str
    symbol: str
    #: Realized-P&L EMA. Realized only — unrealized never steers capital.
    score: float
    #: The publisher's freshness stamp. A row past threshold is treated as
    #: absent, which is a fallback to FCFS and never a halt.
    as_of: float


@runtime_checkable
class RankingTablePort(Protocol):
    """READ-ONLY view of the Scoring process's ranking table (§6.6).

    **No writer verb, by design and not by omission.** §6.6: "Nobody but the
    Scoring process COMPUTES the score... computing the EMA / defining
    'productive' is the allocation judgment that stays out of the gate." A
    `publish` here would put that judgment inside the consumer.
    """

    def available(self) -> bool:
        """False when the table is absent or stale — the R3-A steady state."""

    def row(self, strategy_id: str, symbol: str) -> RankingRow | None:
        """The pair's row, or None. SYNCHRONOUS, O(1), never math."""


# ---------------------------------------------------------------------------
# The proposal (§3, §7, §16 U5)
# ---------------------------------------------------------------------------


class BindingConstraint(enum.Enum):
    """Which term of §7's `min(...)` actually decided the size.

    §16 U5 requires the sizing rationale to ride the order message so the
    Limiter's event log can audit sizing without breaking sole-writer. "The
    size was 3" is not auditable; "the size was 3 and the bucket cap bound it"
    is.
    """

    #: `floor(per_trade_risk_$ / ((stop_ticks + slippage_pad) × tick_value))`
    RISK = "risk"
    #: `floor(max(0, headroom_$) / live_margin_per_contract)`
    MARGIN = "margin"
    SYMBOL_CAP = "symbol_cap"
    #: 0.70 × balance − committed (§16 U2)
    HEADROOM = "headroom"
    #: §7's same-bucket dollar-risk ceiling
    BUCKET_CAP = "bucket_cap"
    #: §6.6 arbitration — reserved; the Limiter arbitrates, not the Allocator
    CONTENTION = "contention"
    #: Nothing bound: the risk-ideal size was admitted whole
    NONE = "none"


@dataclass(frozen=True)
class SizingRationale:
    """§16 U5's "binding constraint + input snapshot", as a value.

    `snapshot_version` is the audit anchor: it names the exact published
    version every term below was computed against, so the Limiter's Phase B
    re-check can say whether it re-checked the same picture or a later one.
    """

    binding: BindingConstraint
    snapshot_version: int
    risk_contracts: int
    margin_contracts: int
    symbol_cap: int
    headroom: float
    bucket: CorrelationBucket | None
    bucket_used: float
    bucket_ceiling: float
    contention: ContentionPolicy
    note: str = ""
    #: ARC 037 / SEAM (b), discharging CHECK-DEBT **D3.260**. The §6.6:459
    #: score -> sizing weight that was MULTIPLIED INTO §7:478's
    #: `per_trade_risk_$` **before** `risk_contracts = floor(...)`, recorded so
    #: the Limiter's audit record can tell a size that was weighted from one
    #: that was not. `1.0` is NEUTRAL and is the default, so every proposal
    #: built before this field existed reads as exactly what it was.
    #:
    #: **`SEAM_REV` IS DELIBERATELY NOT BUMPED.** `SizingRationale` is an
    #: in-process value on the Allocator's own `Proposal`; it is not on the
    #: §12.7 wire, `MIRRORED_FIELDS` and `POSITION_ROW_FIELDS` do not name it,
    #: and no consumer decodes it off a socket. This project's rule is that the
    #: literal moves when the BYTES move (see `SEAM_REV`'s own note above,
    #: where ARC 031 declined to bump on a DECISION and ARC 032 bumped on the
    #: encoded field). Bumping here would make a wire-contract change out of an
    #: added audit term and teach the next reader that the number is decorative.
    score_weight: float = 1.0


class ProposalOutcome(enum.Enum):
    """What the Allocator decided to hand the Risk Engine. Five values.

    `NO_SIZE_DENY` and `NOT_TRADABLE` are separate because §7 separates them:
    an invalid/zero stop intent is a DENY the Limiter issues (the Allocator
    does not manufacture a size to make it deniable), while a symbol missing
    from the margin cache is *not-tradable* and never reaches sizing at all.
    """

    SIZED = "sized"
    #: §7: invalid/zero stop intent ⇒ deny. Shaped as a proposal so the
    #: Limiter still logs it; the Allocator never invents a size.
    NO_SIZE_DENY = "no_size_deny"
    #: §7/§16 U1: dead signal, or symbol missing from the margin cache.
    NOT_TRADABLE = "not_tradable"
    #: §0i / §12.7: the mirror is EMPTY, PARTIAL or STALE — fast-drop.
    STALE_MIRROR = "stale_mirror"
    #: Sizing ran and every term floored to zero contracts.
    ZERO_AFTER_CLAMP = "zero_after_clamp"


@dataclass(frozen=True)
class Proposal:
    """The Allocator's ONLY output. A proposal, never an order (§2).

    `order` is `None` on every outcome but `SIZED`, and even when present it
    is a `ProposedOrder` — the Limiter's own type, which the Limiter must pass
    before anything reaches a broker. There is no field on this object a
    broker adapter could consume directly, and that is deliberate.
    """

    outcome: ProposalOutcome
    symbol: str
    strategy_id: str
    contracts: int
    rationale: SizingRationale
    order: ProposedOrder | None = None
    reason: str = ""

    @property
    def reaches_broker(self) -> bool:
        """Always False. The Allocator's authority, stated as a value.

        A single literal and not a computation: there is no state of this
        object under which the answer differs, and writing it as a predicate
        over fields would imply there is.
        """
        return False


@runtime_checkable
class AllocatorPort(Protocol):
    """Strategy GO in, `Proposal` out. SYNCHRONOUS, single-pass (§16 U1).

    The verb is `propose` and not `size`, `allocate` or `submit`: the name is
    the authority. Ordering INSIDE the implementation is fixed by §16 U1 —
    fast-drop against the tradability cache FIRST (never size a dead signal),
    then size, then emit the proposal carrying its rationale.
    """

    def propose(
        self,
        strategy_id: str,
        symbol: str,
        side: Side,
        stop_ticks: int,
        stop_mode: StopMode,
        signal_ts: float,
    ) -> Proposal:
        """One GO becomes one proposal. Per-GO work only — zero per-tick load."""
