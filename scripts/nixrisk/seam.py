"""The Limiter's frozen internal seam — types and ports, no behaviour.

ARC 028 / Phase 0.6. Landed BEFORE any implementation so the gate pass, the
reservation ledger and the financial picture can be built against a settled
boundary instead of against each other.

WHAT IS IN HERE. Value types, enumerations, and `Protocol` declarations. There
is no rule, no arithmetic, no I/O and no policy. `risks/` holds the §12A knobs
as DATA and this module holds the SHAPE; the behaviour lives in the Limiter's
own code, which is what keeps `risks/` from becoming a second behavioural
authority (`directory_structure.md`).

---

## SYNCHRONOUS OR ASYNCHRONOUS — declared, per the §2A precedent

§2A's ports were declared async by default (SPEC-AMENDMENTS AMENDMENT 5) because
they are I/O against a venue. **Every verb declared in this module is the
opposite, and it is not a style choice.**

* **`RulePort.evaluate` — SYNCHRONOUS.** §5 fixes the Limiter as a
  *single-threaded event loop* and says serial processing "eliminates
  fill-vs-tick races by construction". §3 gives the pass ONE authoritative
  traversal. An `async def evaluate` is a declared suspension point: the loop
  may service a fill between two rules of the same pass, so the pass would judge
  a proposal against a financial picture that changed underneath it — which is
  the exact race §5 claims to have eliminated. §11 also makes the entry pathway
  "cache reads + arithmetic only"; a coroutine that may suspend has no bounded
  cost, so an O(1) claim over it is unfalsifiable.
* **`ReservationLedgerPort` — SYNCHRONOUS.** §11.3 keeps Σ reservations as a
  running incremental aggregate. Taking a reservation is the arithmetic that
  maintains it, and it must be indivisible with respect to the decision that
  caused it: an awaitable `take` admits a second pass reading a committed figure
  that does not yet include the first pass's approval, which is the
  over-commitment §3's Phase B exists to prevent.
* **`FinancialPicturePort.publish` — SYNCHRONOUS.** §3's ATOMICITY RULE:
  balance and the position table publish "as one snapshot — never two separate
  reads". An awaitable publish reintroduces exactly the window the rule forbids,
  between building the snapshot and putting it on the wire.
* **`Plane1Port.enqueue` — SYNCHRONOUS; the DRAIN is not.** §9 is
  `enqueue → durable local WAL → shared-pool writer → group-commit`, and §11.6
  puts group-commit off the hot path. So the hot half is a bounded synchronous
  append and the slow half — fsync, Postgres, group-commit — belongs to the
  shared-pool writer. That split is the seam, not an implementation detail:
  `enqueue` returning without durability is what §12.4 needs in order to keep
  trading through a Postgres outage.

The one asynchronous surface the Limiter owns is **outbound send**, and it is
already declared elsewhere: §10's "outbound exit connectivity cannot [be a
separate process] ⇒ broker-order in-process, async sender", satisfied by
`scripts/broker/broker_seam.py`. This module does not restate it.

---

## WHAT THIS SEAM DELIBERATELY DOES NOT DECIDE

Stop conversion and trailing maintenance (§4), the protective-exit wiring to
broker-order, session-close flatten (§6.1b), full HALT semantics and auto-clear
(§12.5), cold-start reconciliation (§4), the Sentinel (§12.1), Scoring (§6.6)
and the Allocator. **A Limiter that gates but cannot exit is not a safety spine
yet**, and no type in here should be read as implying otherwise.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# pylint: disable=too-many-instance-attributes
# ProposedOrder, Reservation and FinancialPicture each carry exactly the fields
# the frozen spec enumerates -- §3's financial-picture publish lists nine, and
# dropping one to satisfy a default threshold of seven would either lose a
# published field or push it into a nested struct that consumers must read
# SEPARATELY, which is precisely what §3's atomicity rule forbids. The threshold
# is about behavioural classes accreting state; these are frozen value types with
# no behaviour at all.

# ---------------------------------------------------------------------------
# The two-phase pass (§3)
# ---------------------------------------------------------------------------


class Phase(enum.Enum):
    """§3's two phases. The ORDER is the invariant, not the labels.

    `SIZE_INDEPENDENT` rules run first and `SIZE_DEPENDENT` rules run after, in
    one authoritative pass. Declaring the phase on the rule rather than encoding
    it in a list's source order is what makes the ordering checkable at runtime:
    source order proves nothing about execution order.
    """

    SIZE_INDEPENDENT = "A"
    SIZE_DEPENDENT = "B"


class Decision(enum.Enum):
    """§3's three outcomes. `SIZE_DOWN` is distinct from `DENY` (§5)."""

    APPROVE = "approve"
    SIZE_DOWN = "size_down"
    DENY = "deny"


@dataclass(frozen=True)
class RuleVerdict:
    """One rule's answer. A DENY that does not name its rule is not a verdict.

    §3: "deny (rule named, fail-fast)". §5: "blocking rule named". The `rule`
    field is mandatory on every verdict and not only on denials, because the
    pass records what it EVALUATED, and a verdict that cannot say which rule
    produced it cannot be placed in that record.
    """

    rule: str
    decision: Decision
    reason: str
    sized_qty: int | None = None


@runtime_checkable
class RulePort(Protocol):
    """A §5 rule plugin: in-process, non-blocking, side-effect-free.

    SYNCHRONOUS by declaration — see the module docstring. `evaluate` receives
    the proposal and ONE financial picture; it may not fetch, await, or read a
    second snapshot, because a rule that reads twice can straddle a version
    boundary and §3's atomicity rule exists to make that impossible.
    """

    @property
    def name(self) -> str:
        """The identifier a denial is reported under. Stable across restarts."""

    @property
    def phase(self) -> Phase:
        """Which §3 phase this rule belongs to. Declared, never inferred."""

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        """Judge the proposal. Pure: no I/O, no mutation, no clock beyond `now`."""


@dataclass(frozen=True)
class GateOutcome:
    """The pass's authoritative result, and the record of HOW it got there.

    `evaluated` is the rule names **in the order they actually ran**, appended by
    the executor as each rule returns. It exists so the §3 ordering invariant is
    provable by OBSERVATION rather than by reading the manifest: a Phase-B rule
    appearing in this tuple after a Phase-A denial is a correctness defect that
    produces byte-identical output to a correct pass, and this field is the only
    thing that can tell them apart.
    """

    decision: Decision
    rule: str
    reason: str
    phase: Phase
    evaluated: tuple[str, ...]
    sized_qty: int | None = None
    reservation_id: str | None = None


# ---------------------------------------------------------------------------
# The proposal (§3, §4)
# ---------------------------------------------------------------------------


class StopMode(enum.Enum):
    """§4: the STRATEGY chooses per signal; not a system-wide policy."""

    FIXED = "fixed"
    TRAILING = "trailing"


class Side(enum.Enum):
    """Direction. Spelled here rather than imported from the broker seam: §2A
    invariant 3 keeps the order and datafeed contracts disjoint, and the
    Limiter's internal seam is not the vendor boundary either."""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class ProposedOrder:
    """What the Allocator hands the Limiter (§3), already sized.

    `stop_ticks` is a DISTANCE, never a price (§4): the strategy signals before
    it knows the fill, so a distance survives slippage and an absolute price does
    not. Conversion to a price happens once the fill is confirmed — and that
    conversion is explicitly NOT in this arc.
    """

    client_order_id: str
    strategy_id: str
    symbol: str
    side: Side
    qty: int
    margin_per_contract: float
    stop_ticks: int
    stop_mode: StopMode
    signal_ts: float

    @property
    def proposed_margin(self) -> float:
        """The margin this order would commit if it filled in full."""
        return self.qty * self.margin_per_contract


# ---------------------------------------------------------------------------
# The reservation lifecycle (§3)
# ---------------------------------------------------------------------------


class TerminalPath(enum.Enum):
    """§3's release paths, TRANSCRIBED FROM THE SPEC and closed.

    Verbatim: "taken at approval → released on: fill (converts to open-margin),
    cancel, reject, pending-timeout resolution, blackout-onset cancellation. No
    leak paths."

    This enumeration is the SPEC's list, not the implementation's. If an
    implementation reaches a terminal state not named here, that is a finding
    about the spec to be reported — never a member quietly added to this enum,
    because deriving the path set from the code and then proving the code covers
    it is circular and passes while measuring nothing.
    """

    FILL = "fill"
    CANCEL = "cancel"
    REJECT = "reject"
    PENDING_TIMEOUT = "pending_timeout"
    BLACKOUT_ONSET = "blackout_onset"


class ReservationState(enum.Enum):
    """A reservation is TAKEN or RELEASED. There is no third state.

    Deliberately two-valued: a `PARTIAL` or `SETTLING` state would be a place for
    margin to sit while counted by nobody, and Σ reservations is a §11.3 running
    aggregate that must equal the sum of the TAKEN rows at every instant.
    """

    TAKEN = "taken"
    RELEASED = "released"


@dataclass(frozen=True)
class Reservation:
    """One taken reservation. Immutable; release produces a new record."""

    reservation_id: str
    client_order_id: str
    strategy_id: str
    symbol: str
    margin: float
    state: ReservationState
    taken_ts: float
    released_ts: float | None = None
    released_via: TerminalPath | None = None


class ReservationLedgerPort(Protocol):
    """§3's reservation lifecycle. SYNCHRONOUS — see the module docstring.

    `release` is declared to return the released `Reservation` and to REFUSE a
    second release of the same id rather than absorbing it. Both directions are
    defects and they are not symmetric: a leak permanently reduces deployable
    capital and eventually blocks all trading, which is loud; a DOUBLE RELEASE
    under-counts committed margin and lets the system over-commit, which is
    silent, more dangerous, and invisible to a leak test that only checks that
    the ledger drains.
    """

    def take(self, order: ProposedOrder, now: float) -> Reservation:
        """Take a reservation for `order.proposed_margin`. Raises on duplicate."""

    def release(
        self, reservation_id: str, via: TerminalPath, now: float
    ) -> Reservation:
        """Release exactly once. Raises on unknown id and on double release."""

    def outstanding(self) -> tuple[Reservation, ...]:
        """Every reservation currently TAKEN. The ground truth Σ is derived from."""

    def total_reserved(self) -> float:
        """§11.3's running aggregate: Σ margin over the TAKEN set."""


# ---------------------------------------------------------------------------
# The financial picture (§3 "FULL FINANCIAL-PICTURE PUBLISH", §12.7)
# ---------------------------------------------------------------------------


class PositionState(enum.Enum):
    """§3: "every position in whatever state it is in"."""

    RESERVED = "reserved"
    PENDING = "pending"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(frozen=True)
class PositionRow:
    """§3's per-position row, keyed by `trade_id`."""

    trade_id: str
    symbol: str
    strategy_id: str
    size: int
    margin: float
    state: PositionState


@dataclass(frozen=True)
class FinancialPicture:
    """§3's ONE atomic snapshot, carrying ONE version stamp.

    Every field below is published together or not at all. The `version` is what
    makes that checkable from outside: a consumer that ever observes a balance
    and a position table bearing different versions has observed a torn read, and
    §3 says the Allocator "can never compute headroom off a stale balance and a
    fresh commitment, or the reverse".

    A frozen dataclass holding immutable members is the mechanism: there is no
    setter a publisher could call between two consumers' reads, so atomicity is a
    property of the type rather than a discipline the writer is asked to keep.
    """

    version: int
    published_ts: float
    balance: float
    positions: tuple[PositionRow, ...]
    margin_per_contract: Mapping[str, float]
    sum_open_margin: float
    sum_reservations: float
    committed: float
    deployable: float


class FinancialPicturePort(Protocol):
    """§12.7's mirror model: the Limiter owns the table, publishes snapshots.

    SYNCHRONOUS `publish` — see the module docstring. Snapshot-on-subscribe is
    mandatory rather than polish (§12.7): a consumer whose mirror is incomplete
    is treated as STALE and fast-drops or denies until the snapshot lands, and it
    is never sized on. A mirror that silently misses its snapshot looks exactly
    like a quiet feed.
    """

    def publish(self, picture: FinancialPicture) -> None:
        """Put one self-consistent snapshot on the wire. One version, one write."""

    def current(self) -> FinancialPicture:
        """The Limiter's own copy — the real table §12.7 keeps in its memory."""


# ---------------------------------------------------------------------------
# Plane 1 (§9, §12.4, §12.10)
# ---------------------------------------------------------------------------


class EventKind(enum.Enum):
    """The §12.10 inventory rows this arc's seam can produce.

    NOT the whole inventory. §12.10 also books protective-exit, exit-intent,
    closed, GO-timeout, HALT set/clear, operator action, strategy lifecycle and
    cold-start outcome; every one of those belongs to machinery this arc
    explicitly does not build, and inventing their members here would let a gate
    report coverage of paths that have no code.
    """

    SIGNAL = "signal"
    ACCEPTED = "accepted"
    DENIED = "denied"
    RESERVATION_TAKEN = "reservation_taken"
    RESERVATION_RELEASED = "reservation_released"
    BOOT = "boot"


@dataclass(frozen=True)
class EventRow:
    """One append-only Plane-1 row (§9). Never overwritten.

    §9 requires timestamp + strategy_id + trade_id + reason on every row. `trade_id`
    is optional in the TYPE and not in the spec: it is minted by the Limiter at
    open (§4), so a `denied` row that never reached an open has none, and a type
    that forced a value there would force the writer to invent one.
    """

    kind: EventKind
    ts: float
    strategy_id: str
    reason: str
    trade_id: str | None = None
    fields: Mapping[str, str] = field(default_factory=dict)


class Plane1Port(Protocol):
    """§9's write path. The Limiter is the SOLE writer; no new writers, ever.

    `enqueue` is SYNCHRONOUS and returns WITHOUT durability — that is the whole
    point of the split (§11.6, and see the module docstring). Durability is
    `sync_to_disk`'s job, and a WAL that has not fsynced is not durable however
    successfully the write returned: the page cache will happily accept bytes
    that a power cut then loses.

    §12.4 is the reason the two are separable at all: a Postgres outage buffers
    in the WAL and trading CONTINUES, while a disk-critical WAL that cannot
    append HALTs new entries. Degraded persistence is not degraded trading, and
    conflating `enqueue` with `commit` would make it so.
    """

    def enqueue(self, row: EventRow) -> None:
        """Append to the local WAL buffer. Bounded, hot-path-safe, not durable."""

    def sync_to_disk(self) -> int:
        """Force the buffered rows to STABLE storage. Returns rows made durable."""

    def pending(self) -> int:
        """Rows enqueued but not yet durable. A §12.4 disk-critical input."""
