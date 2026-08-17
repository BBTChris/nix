"""THE CALLER — one confirmed fill becomes an armed stop, a release, a §3 row.

ARC 034 / sub-agent A. Discharges the caller half of CHECK-DEBT **D3.178** and
the consumption half of **D3.150**. Every `§` in this file cites
`docs/nics_risk_subsystem_spec_v1.3.md`; `D3.<n>` cites `docs/CHECK-DEBT.md`.

==============================================================================
WHY THIS MODULE EXISTS — a mechanism landed is not a mechanism CALLED
==============================================================================
ARC 029 built `nixrisk.stops.StopBook.arm`: §4's distance→price conversion at the
confirmed fill. ARC 033 built `nixrisk.positions.PositionOriginWriter.on_fill`:
§3's origin write, which publishes `PositionRow.stop_distance` from the armed
stop, and gated it with `checks/check_origin_write.py`.

**Both had ZERO production callers.** §7:501 prices correlation-bucket exposure
from `stop_distance`, so the safety cap that decides how much correlated risk the
system may hold was pricing a field that nothing in production ever populated.
Two green gates over two mechanisms nothing invoked.

`scripts/nixrisk/fill_seam.py` (FROZEN, `FILL_SEAM_REV 1.0.0`, gated by
`checks/check_fill_seam.py`) declares the missing caller's surface. This module is
the behaviour behind it. Nothing here re-decides anything the seam settled: the
step ORDER, the synchrony, and the narrowness of every port are the seam's, and
where this module needs a surface the seam did not declare it declares its own
narrow one rather than widening a frozen port.

==============================================================================
THE ORDER IS THE SAFETY PROPERTY, AND IT IS RECORDED AS IT HAPPENS
==============================================================================
1. `FillStep.ARM_STOP` — `StopArmPort.arm(fill_price, order)` (§4). The GO's tick
   DISTANCE becomes an absolute price against the CONFIRMED fill.
2. `FillStep.RELEASE_REMAINDER` — IOC-cancel the unfilled remainder and release
   its reservation (§4's partial-fill rule), returning the post-release Σ.
3. `FillStep.ORIGIN_WRITE` — `OriginWritePort.on_fill(report, sum_reservations=Σ)`
   (§3), so the released capital and the published position land under ONE
   version stamp.

The arm MUST precede the write because `PositionOriginWriter` REFUSES a fill with
no armed stop — a defaulted distance would price a real position at zero dollar
risk, make the correlation bucket read emptier than it is, and ADMIT MORE. The
release MUST sit between them because §4 requires the published snapshot to carry
the reservation for the unfilled portion ALREADY released, *"not on a delay"*.

**`FillOutcome.steps` is appended to as each step COMPLETES, never assembled at
the end.** A tuple built after the fact is a re-statement of source order, and
source order is what a reader believes rather than what an interpreter ran. A
step that did not run is not recorded — see the re-arm rule below.

==============================================================================
THE STOP IS CONVERTED ONCE, SO THE HANDLER REMEMBERS WHAT IT ARMED
==============================================================================
§4 converts distance→price ONCE at the confirmed fill, and `StopBook.arm` refuses
a second arm for one order (`DuplicateStop`) precisely so a re-delivered or
successive partial fill cannot silently replace a live stop with a re-converted
one anchored at a different price.

A partial fill arrives as SUCCESSIVE events (§4), so `on_fill` is called again for
the same order. `StopArmPort` is deliberately narrowed to the single verb `arm` —
it has no reader — so this handler cannot ask the book whether a stop exists. It
therefore keeps its own record of the orders it has armed, and on a later fill of
the same order it does NOT call `arm` again and does NOT record `ARM_STOP`.
`FillOutcome.armed` still carries that trade's `StopState`, because the question
*"which stop protects this fill"* has the same answer either way.

**The residual, named rather than implied:** the handler's record and the stop
book are two stores of one fact. If anything else armed or forgot a stop for an
order this handler has seen, they disagree, and this handler would decline to
re-arm a stop that is no longer in the book. Nothing else arms today (this module
is the only caller of `arm` in the tree) and `forget` is the protective-flatten
path's, which runs after the position is closed. It is written down because the
day a second arming site exists, this is where it breaks.

==============================================================================
TWO CUMULATIVE FIGURES, AND WHICH ONE ANSWERS WHICH QUESTION
==============================================================================
This is the one place the module holds two numbers for one thing, so it is stated
rather than left to be found:

* **The IOC cancel uses the BROKER's `report.cumulative_qty`.** The cancel is a
  message to the VENUE about the order the VENUE is working, and the venue's own
  running total is the figure that says how much of it is still outstanding. §4
  makes the fill *"a fact the system reports, never a negotiation"*.
* **The published POSITION uses the LEDGER's derived cumulative.** That figure is
  `ExecutionLedger.order_cumulative`, read inside `PositionOriginWriter`, and it
  is a sum over the SET of unique `(order_id, exec_id)` fills — immune to
  duplicate and out-of-order delivery in a way the broker's last-reported
  cumulative is not. `FillOutcome.filled_qty` is that ledger figure, taken from
  the published row, never re-derived here (doctrine C.9).

When the two disagree, the ledger has not seen an execution the venue has already
counted. This handler does not raise — §4 makes broker truth win for the venue
action, and `ExecutionLedger.audit()` owns the reconciliation — but it RECORDS the
disagreement in `disagreements()` where a supervising loop can read it. A number
nobody can question is worse than a gap that shouts.

==============================================================================
WHAT THIS MODULE DOES NOT DO — stated, not implied
==============================================================================
* **It writes no Plane-1 row.** §9's inventory has a `filled` transition and
  `seam.EventKind` deliberately has no member for it (*"a member lands here ONLY
  when the machinery that emits it exists"*). Adding one is a frozen-seam edit
  outside this arc's authority, so the §9 `filled` row is OWED, not skipped.
* **It does not inform the strategy.** §4's partial-fill rule requires the
  Limiter to inform the strategy that it is smaller than it asked for; the
  strategy feedback surface is `nixrisk.seam.StrategyFeedbackPort`, driven by the
  flatten path today. Wiring it from here is a separate decision about what the
  §4 feedback event for a partial entry is called, and it is owed.
* **It does not fire a flatten.** `PositionOriginWriter` refuses an unstopped fill
  and records it; §14 resolves that toward FLAT and §14 makes flatten execution
  Limiter-only, owned by `nixrisk.flatten`. This handler lets the refusal out.
* **It does not decide `OPEN` vs `CLOSING`.** This is the ENTRY path: the origin
  write publishes the row that first represents an open position.

==============================================================================
THE WIRING GAP — REPORTED, BECAUSE THIS IS THE DEFECT ONE LAYER OUT
==============================================================================
`LimiterFillSink` below converts §2A's `on_fill(client_order_id, exec_id, symbol,
filled_qty, price, cumulative_qty)` event into an `ExecutionReport` and drives the
handler. That is the shape `scripts/broker/broker_seam.py`'s `OrderEventSink`
declares and `scripts/broker/broker_order_ibkr.py` pushes to.

**`LimiterFillSink` is NOT a complete `OrderEventSink`, and it must not be
presented as one.** That Protocol also declares `on_ack`, `on_cancel`,
`on_balance`, `on_margin`, `on_position` and `on_session`, and every one of them
belongs to Limiter machinery that does not exist yet. A partial sink handed to the
IBKR adapter would crash on the first ack, so this class cannot yet be given to
it, and **there is therefore still no live broker event reaching this handler**.
The live count — how many of that Protocol's verbs this class carries — is not
restated here: `checks/check_fill_handler.py` derives both figures from
`scripts/broker/broker_seam.py` and puts them in its evidence on every run.
What has changed is that the fill path now exists, is driven end to end by
`checks/check_fill_handler.py`, and consumes exactly the event the broker seam
already emits — so the remaining work is the other six verbs, not this one. Any
green in this arc that is read as "production fills reach the correlation cap"
would be reading it wrong.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol, runtime_checkable

from nixrisk.execution import ExecutionReport, FillSide
from nixrisk.fill_seam import (
    ApprovedOrderPort,
    FillOutcome,
    FillStep,
    OriginWritePort,
    RemainderPort,
    StopArmPort,
)
from nixrisk.reservations import Resolution
from nixrisk.seam import ProposedOrder, Side, StopState, TerminalPath

# R0903 (too-few-public-methods): `CancelPort` is a single-verb Protocol — the
# whole surface `IocRemainder` consumes from the broker, and a second verb would
# let the reservation path place or flatten. §12.1's prohibition and §14's
# Limiter-only flatten are both kept structural by that narrowness, the same
# construction `fill_seam.StopArmPort` documents.
# pylint: disable=too-few-public-methods


class Clock(Protocol):
    """A monotonic-enough source of §9's row timestamps. Injected, never `time`.

    Declared rather than importing `time.time` so a drive can be deterministic
    and so this module imports nothing side-effecting — the same reason
    `nixrisk.flatten` takes its clock.
    """

    def __call__(self) -> float:
        """Now, in seconds."""


class FillError(RuntimeError):
    """Base for every refusal on this path. Always names what and why (§18)."""


class UnapprovedFill(FillError):
    """A fill arrived for an order this Limiter never approved.

    Refused rather than absorbed. `arm` converts from `ProposedOrder.stop_ticks`
    — the sizer's own distance (§7:476) — and an execution report does not carry
    it, so without the approval there is no distance to convert and no `qty` to
    measure a remainder against. Reconstructing either from the fill would be the
    system choosing the same number twice, which is exactly the independence
    `check_origin_write` exists to preserve.
    """


class DuplicateApproval(FillError):
    """An order was recorded as approved twice.

    A DISTINCT type from `UnapprovedFill` deliberately, and the distinction is
    §18's: the two conditions are opposites — this Limiter holds no record of the
    order, versus it already holds one — and an exception whose NAME contradicts
    the condition it reports is the shared-namespace defect §18 exists to close,
    one layer up from an exit code.
    """


class InvalidRemainder(FillError):
    """A remainder release whose quantities are not a possible fill.

    A non-positive filled or requested quantity would make the cancel decision
    meaningless — §4's remainder is `requested − filled`, and a zero requested
    size makes every fill an over-fill. Denied at the boundary, loudly, rather
    than producing a cancel for a quantity nobody ordered.
    """


# ---------------------------------------------------------------------------
# The approvals this Limiter is holding — `ApprovedOrderPort`, the LOOKUP
# ---------------------------------------------------------------------------


class ApprovedOrderBook:
    """Every `ProposedOrder` this Limiter approved, keyed by `client_order_id`.

    Recorded at APPROVAL, beside `EntryOrderOrigins` and for the same reason: the
    association exists at that moment and at no other. Kept SEPARATE from the
    origin registry deliberately — that one holds the trade↔order join and this
    one holds the ORDER, and a single object holding both would be a second place
    the join could be established (`positions.py` makes the join an injected
    policy precisely so it has exactly one home).

    In-memory, §12.7: it dies with the process like every other synthetic state
    (§12.1), and §4's cold start refuses to adopt inherited positions.
    """

    def __init__(self) -> None:
        self._orders: dict[str, ProposedOrder] = {}
        #: How many approvals this book holds. An observable, for the reason
        #: `EntryOrderOrigins.recorded` is one: a registry that cannot say what
        #: it holds can only be believed, not measured.
        self.recorded = 0

    def record(self, order: ProposedOrder) -> ProposedOrder:
        """Hold one approved order. Refuses a re-record, loudly.

        §4 allows one in-flight action per strategy, so a second approval under a
        live `client_order_id` is either a duplicate event or a keying defect.
        Silently replacing the held order would re-point the stop distance and
        the requested size of an order that may already have filled.
        """
        prior = self._orders.get(order.client_order_id)
        if prior is not None:
            raise DuplicateApproval(
                f"order {order.client_order_id!r} is already approved with "
                f"qty={prior.qty} stop_ticks={prior.stop_ticks}; refusing to "
                f"replace it with qty={order.qty} stop_ticks={order.stop_ticks} "
                "— §4 allows one in-flight action per strategy, and a silent "
                "replacement would re-point the distance §7:501 prices this "
                "position's bucket exposure from"
            )
        self._orders[order.client_order_id] = order
        self.recorded += 1
        return order

    def order_for(self, client_order_id: str) -> ProposedOrder | None:
        """The approved order, or `None`. Never raises — see `ApprovedOrderPort`."""
        return self._orders.get(client_order_id)

    def approved(self) -> tuple[str, ...]:
        """Every held `client_order_id`, sorted. Evidence, never the hot path."""
        return tuple(sorted(self._orders))


# ---------------------------------------------------------------------------
# §4's partial-fill remainder — `RemainderPort`, cancel THEN release
# ---------------------------------------------------------------------------


@runtime_checkable
class CancelPort(Protocol):
    """The IOC cancel, as this module consumes it. ONE verb, SYNCHRONOUS.

    Narrower than `broker_seam.BrokerOrderPort` on purpose: no `place_order`, no
    `flatten`, no `connect`. A reservation-release path that could place an order
    would be a second order-placement site (§12.1 keeps stops synthetic; §14 makes
    flatten execution Limiter-only and `nixrisk.flatten` owns it). `cancel_order`
    is declared SYNC on that port — §2A invariant 5 makes the send path
    non-blocking — so consuming it synchronously reverses nothing.
    """

    def cancel_order(self, client_order_id: str) -> None:
        """Cancel whatever of this order the venue is still working (§4, IOC)."""


@runtime_checkable
class ReservationBookPort(Protocol):
    """§3's reservation lifecycle, as this module consumes it. TWO verbs.

    Both are needed and neither is decoration: `resolve` performs the release
    keyed by the identifier a broker event actually carries, and `total_reserved`
    is the post-release Σ that must ride the SAME version stamp as the published
    row (§3's atomicity rule). Reading Σ from anywhere other than the book that
    just released would be the cross-table read §6.4 warns about, one layer in.

    `take`, `release`, `audit` and the rest of `ReservationLedgerPort` are
    deliberately absent: a fill path that could TAKE a reservation could commit
    capital, and this path only ever gives capital back.
    """

    def resolve(
        self, client_order_id: str, via: TerminalPath, now: float, reason: str = ""
    ) -> Resolution:
        """One terminal event for one order. Releases, or refuses and says why."""

    def total_reserved(self) -> float:
        """§11.3's running aggregate: Σ margin over the TAKEN set."""


@dataclasses.dataclass(frozen=True)
class RemainderRelease:
    """What one remainder release actually did. Kept so it is not merely lost."""

    client_order_id: str
    filled_qty: int
    requested_qty: int
    cancelled: bool
    released: bool
    #: Why the reservation was NOT released, when it was not. §4's fill-vs-cancel
    #: race makes a duplicate terminal event ordinary data rather than an error,
    #: and the reason is the fact — never the bare boolean above (§18).
    refusal_reason: str
    sum_reservations: float


# R0902 refused with a reason: EIGHT attributes, and FIVE of them are
# observables — four counters plus the release history. They exist for the
# reason `ReservationLedger`'s counters do: a component that cannot say what it
# did can only be believed, not measured, and `checks/check_fill_handler.py`
# reads them out of a real drive. The other three are the injected
# collaborators this class composes and owns none of.
class IocRemainder:  # pylint: disable=too-many-instance-attributes
    """§4's remainder: IOC-cancel what did not fill, release its reservation.

    SYNCHRONOUS, and the two halves are ONE verb because §4 makes them one fact.
    Splitting them would admit a state in which the order is cancelled while its
    capital is still reserved — invisible to every consumer, and erring toward
    LESS deployable capital, which `positions.py` already documents as
    conservative-and-still-wrong.

    **CANCEL FIRST, THEN RELEASE**, and the order is not arbitrary. Releasing
    first would return the capital to deployable while the venue is still working
    the remainder, so a fill that wins the race against the cancel would commit
    margin the Allocator has already been told is free — a real over-commitment,
    which is the condition §3's Phase B exists to prevent. Cancelling first can
    only ever err the other way, and §4 says so outright: *"the reservation
    covered full size, so no cap breach either way."*

    **The WHOLE reservation is released, not a fraction of it.** §3's lifecycle
    releases a reservation ON FILL — it *"converts to open-margin"* — and the
    filled portion's margin re-appears as `PositionRow.margin` on the very
    snapshot this release rides. Releasing only the unfilled fraction would
    double-count the filled portion, holding both a reservation and open margin
    for one commitment.
    """

    def __init__(
        self,
        *,
        reservations: ReservationBookPort,
        cancels: CancelPort,
        clock: Clock,
    ) -> None:
        self._reservations = reservations
        self._cancels = cancels
        self._clock = clock
        #: Observables. A component that cannot say what it did can only be
        #: believed, not measured (`ReservationLedger`'s own argument).
        self.cancels_issued = 0
        self.releases = 0
        self.refused_releases = 0
        self.over_fills = 0
        self._history: list[RemainderRelease] = []

    def release_remainder(
        self, client_order_id: str, *, filled_qty: int, requested_qty: int
    ) -> float:
        """Cancel the unfilled remainder, release the reservation, return Σ (§4).

        The subtraction lives HERE and not in the caller, exactly as the seam
        requires: a caller computing the remainder would be a second place §4's
        partial-fill arithmetic lives, and two places is how the two answers start
        to differ.
        """
        self._guard(client_order_id, filled_qty, requested_qty)
        cancelled = self._cancel_if_short(client_order_id, filled_qty, requested_qty)
        resolution = self._reservations.resolve(
            client_order_id,
            TerminalPath.FILL,
            self._clock(),
            reason=(
                f"fill confirmed {filled_qty} of {requested_qty} — §3 releases the "
                "reservation ON FILL (it converts to open-margin) and §4 releases "
                "the unfilled portion the instant reality comes in under it"
            ),
        )
        sigma = self._reservations.total_reserved()
        self._record(
            client_order_id, filled_qty, requested_qty, cancelled, resolution, sigma
        )
        return sigma

    def history(self) -> tuple[RemainderRelease, ...]:
        """Every release this component performed, in arrival order."""
        return tuple(self._history)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _guard(client_order_id: str, filled_qty: int, requested_qty: int) -> None:
        """Refuse quantities that make §4's remainder meaningless."""
        if filled_qty <= 0 or requested_qty <= 0:
            raise InvalidRemainder(
                f"{client_order_id}: filled_qty={filled_qty!r} of "
                f"requested_qty={requested_qty!r} — §4's remainder is "
                "requested minus filled, and a non-positive quantity on either "
                "side makes the cancel decision a statement about nothing"
            )

    def _cancel_if_short(
        self, client_order_id: str, filled_qty: int, requested_qty: int
    ) -> bool:
        """IOC-cancel the remainder, but only when there IS one.

        An unconditional cancel would send a cancel for a fully-filled order on
        every fill — harmless at the venue, and a lie in the record: the count of
        cancels would stop being the count of partial fills, which is the figure
        an operator reads to see how often the system is being filled short.
        """
        if filled_qty > requested_qty:
            # §4: "If the cancel loses the race and the remainder fills, position
            # state reflects cumulative reality." Counted rather than raised, for
            # that reason — but counted, because an over-fill against a reservation
            # taken for the requested size is the one shape that CAN breach a cap.
            self.over_fills += 1
            return False
        if filled_qty == requested_qty:
            return False
        self._cancels.cancel_order(client_order_id)
        self.cancels_issued += 1
        return True

    def _record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        client_order_id: str,
        filled_qty: int,
        requested_qty: int,
        cancelled: bool,
        resolution: Resolution,
        sigma: float,
    ) -> None:
        """Book what happened, counters and history together. Never a bare bool."""
        if resolution.accepted:
            self.releases += 1
            reason = ""
        else:
            self.refused_releases += 1
            refusal = resolution.refusal
            reason = (
                refusal.reason
                if refusal is not None
                else (
                    "the reservation book returned neither a release nor a "
                    "refusal, so the terminal event's disposition is unknown"
                )
            )
        self._history.append(
            RemainderRelease(
                client_order_id=client_order_id,
                filled_qty=filled_qty,
                requested_qty=requested_qty,
                cancelled=cancelled,
                released=resolution.accepted,
                refusal_reason=reason,
                sum_reservations=sigma,
            )
        )


# ---------------------------------------------------------------------------
# The handler — `FillHandlerPort`, the caller D3.178 said was missing
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CumulativeDisagreement:
    """The venue's running total and the ledger's, for one fill, disagreeing.

    Recorded rather than raised: §4 makes broker truth win for the venue action
    and `ExecutionLedger.audit()` owns the reconciliation. It is kept because a
    ledger that has not seen an execution the venue has counted means the
    published position is SMALLER than reality — and a position that reads
    smaller than it is makes §7:501's bucket read emptier and ADMIT MORE.
    """

    order_id: str
    exec_id: str
    broker_cumulative: int
    ledger_cumulative: int


# R0902 refused with a reason: NINE attributes — four injected ports, the
# record of what this handler armed (§4 converts ONCE and `StopArmPort` has no
# reader, so the handler must remember), three counters and the disagreement
# log. Dropping a counter would remove a measurement from a gate's verdict.
class FillHandler:  # pylint: disable=too-many-instance-attributes
    """One confirmed fill → armed stop, released remainder, published §3 row.

    Satisfies the frozen `fill_seam.FillHandlerPort`. Deliberately NOT a subclass
    of it: a `Protocol`'s method bodies are docstrings, so inheriting means a verb
    this class forgot to override returns `None` silently. Conformance is proven
    by holding the constructed object against the `runtime_checkable` Protocol AND
    comparing signatures — a measurement, not a nominal claim.

    SYNCHRONOUS throughout (§5's single-threaded loop, §3's atomicity rule). Every
    collaborator is INJECTED as a narrow port; this class constructs nothing and
    owns no table but its own record of what it has armed.

    §14: *"Open" = confirmed fill only. Never optimistic.* There is no verb here
    for an ack, a pending order or an optimistic position.
    """

    def __init__(
        self,
        *,
        orders: ApprovedOrderPort,
        stops: StopArmPort,
        remainder: RemainderPort,
        writer: OriginWritePort,
    ) -> None:
        self._orders = orders
        self._stops = stops
        self._remainder = remainder
        self._writer = writer
        #: `client_order_id` -> the `StopState` THIS handler armed. See the module
        #: docstring: §4 converts once, `StopArmPort` has no reader, so the
        #: handler remembers what it converted.
        self._armed: dict[str, StopState] = {}
        #: Observables, read by `checks/check_fill_handler.py` out of a real drive.
        self.handled = 0
        self.conversions = 0
        self.re_arms_declined = 0
        self._disagreements: list[CumulativeDisagreement] = []

    # -- the event surface --------------------------------------------------

    def on_fill(self, report: ExecutionReport) -> FillOutcome:
        """Handle one confirmed fill. Arms, releases, publishes — in that order.

        Raises rather than returning a partial outcome. There is no half-handled
        fill: `PositionOriginWriter` refuses an unstopped fill loudly, and a
        handler that swallowed that refusal to return a "mostly fine" outcome
        would reintroduce the fail-open the refusal exists to prevent.
        """
        order = self._approved(report)
        steps: list[FillStep] = []

        armed, converted = self._arm(order, report)
        if converted:
            steps.append(FillStep.ARM_STOP)

        sigma = self._remainder.release_remainder(
            order.client_order_id,
            filled_qty=report.cumulative_qty,
            requested_qty=order.qty,
        )
        steps.append(FillStep.RELEASE_REMAINDER)

        write = self._writer.on_fill(report, sum_reservations=sigma)
        steps.append(FillStep.ORIGIN_WRITE)

        filled = abs(write.row.size)
        self._note_disagreement(report, filled)
        self.handled += 1
        return FillOutcome(
            steps=tuple(steps),
            armed=armed,
            write=write,
            sum_reservations=sigma,
            filled_qty=filled,
            requested_qty=order.qty,
        )

    def armed_orders(self) -> tuple[str, ...]:
        """Every `client_order_id` this handler has converted a stop for, sorted."""
        return tuple(sorted(self._armed))

    def disagreements(self) -> tuple[CumulativeDisagreement, ...]:
        """Fills where the venue's cumulative and the ledger's did not agree."""
        return tuple(self._disagreements)

    # -- internals ----------------------------------------------------------

    def _approved(self, report: ExecutionReport) -> ProposedOrder:
        """The approval this fill belongs to, or a loud refusal."""
        order = self._orders.order_for(report.order_id)
        if order is None:
            raise UnapprovedFill(
                f"fill {report.order_id}/{report.exec_id} in {report.symbol!r}: "
                "this Limiter holds no approved order under that id, so there is "
                "no stop_ticks to convert (§4 converts the SIZER's distance, "
                "§7:476) and no requested size to measure §4's remainder against. "
                "Refusing rather than reconstructing either from the fill, which "
                "would be the system choosing the same number twice"
            )
        return order

    def _arm(
        self, order: ProposedOrder, report: ExecutionReport
    ) -> tuple[StopState, bool]:
        """Convert distance→price ONCE (§4). Returns `(state, did_convert)`.

        `did_convert` is what decides whether `FillStep.ARM_STOP` is recorded, so
        a successive partial fill reports the steps it REALLY ran. Recording a
        step that did not execute would make `FillOutcome.steps` a description of
        this function's source rather than of its behaviour.
        """
        prior = self._armed.get(order.client_order_id)
        if prior is not None:
            self.re_arms_declined += 1
            return prior, False
        state = self._stops.arm(report.price, order)
        self._armed[order.client_order_id] = state
        self.conversions += 1
        return state, True

    def _note_disagreement(self, report: ExecutionReport, ledger_filled: int) -> None:
        """Book a venue-vs-ledger cumulative disagreement. See the module docstring."""
        if report.cumulative_qty == ledger_filled:
            return
        self._disagreements.append(
            CumulativeDisagreement(
                order_id=report.order_id,
                exec_id=report.exec_id,
                broker_cumulative=report.cumulative_qty,
                ledger_cumulative=ledger_filled,
            )
        )


# ---------------------------------------------------------------------------
# The broker-event adapter — §2A's `on_fill` event, converted and driven
# ---------------------------------------------------------------------------


class LimiterFillSink:
    """§2A's `on_fill` event → an `ExecutionReport` → `FillHandler.on_fill`.

    **Read the module docstring's wiring-gap section before citing this class.**
    It carries the `on_fill` verb of `broker_seam.OrderEventSink` and none of the
    other six, so it cannot yet be handed to the IBKR adapter and no live broker
    event reaches the handler through it today.

    WHY A CONVERSION IS NEEDED AT ALL, rather than the handler taking the event
    directly: §2A's `on_fill` carries no SIDE. `ExecutionReport` requires one —
    position state is `Σ signed_qty`, and an unsigned fill has no sign to
    accumulate under. The side is taken from the APPROVED ORDER, which is the only
    authority that holds it, and mapped LONG→BUY / SHORT→SELL because this is the
    ENTRY path: the origin write publishes the row that first represents an open
    position. A closing fill inverts that mapping and belongs to the flatten path,
    which is `nixrisk.flatten`'s and not this class's.

    The venue's `symbol` is passed through UNTOUCHED rather than replaced by the
    order's. If they disagree, `ExecutionLedger._guard_order_consistency` refuses
    the report and names the disagreement — one `order_id` is one instrument —
    and silently substituting the order's symbol here would erase exactly that.
    """

    def __init__(
        self,
        *,
        handler: FillHandler,
        orders: ApprovedOrderPort,
        clock: Clock,
    ) -> None:
        self._handler = handler
        self._orders = orders
        self._clock = clock
        #: Observables: how many venue events arrived and what they produced.
        self.delivered = 0
        self._outcomes: list[FillOutcome] = []

    # The six positional fields are §2A's own `on_fill` signature, transcribed.
    # Collapsing them into a struct would redefine a locked seam shape.
    def on_fill(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        client_order_id: str,
        exec_id: str,
        symbol: str,
        filled_qty: int,
        price: float,
        cumulative_qty: int,
    ) -> None:
        """One §2A broker fill event. Returns nothing — the sink's shape is fixed."""
        order = self._orders.order_for(client_order_id)
        if order is None:
            raise UnapprovedFill(
                f"broker fill {client_order_id}/{exec_id} in {symbol!r}: this "
                "Limiter holds no approved order under that id, so the fill's "
                "SIDE cannot be resolved — §2A's on_fill event carries no side, "
                "and position state is a sum of SIGNED quantities. Refusing "
                "rather than guessing a direction"
            )
        self.delivered += 1
        outcome = self._handler.on_fill(
            ExecutionReport(
                order_id=client_order_id,
                exec_id=exec_id,
                symbol=symbol,
                side=FillSide.BUY if order.side is Side.LONG else FillSide.SELL,
                filled_qty=filled_qty,
                price=price,
                cumulative_qty=cumulative_qty,
                ts=self._clock(),
            )
        )
        self._outcomes.append(outcome)

    def outcomes(self) -> tuple[FillOutcome, ...]:
        """What every delivered event produced, in arrival order."""
        return tuple(self._outcomes)
