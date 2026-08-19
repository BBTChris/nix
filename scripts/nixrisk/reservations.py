"""§3's margin-reservation ledger — the exactly-once lifecycle, and Σ.

ARC 028 / B. Implements the FROZEN `ReservationLedgerPort` declared in
`scripts/nixrisk/seam.py`. Nothing here is a second authority: the seam fixes the
types and the terminal-path vocabulary, `nics_risk_subsystem_spec_v1.3.md` §3
fixes the state machine, and this module is the arithmetic that keeps them true.

---

## THE PROPERTY, and it is §14's, verbatim

> **Every reservation reaches exactly one terminal release.**

**Exactly one** is two failures, not one, and they are not the same defect:

* **ZERO releases — a LEAK.** Capital stays committed forever. Σ reservations
  only climbs, `deployable` only shrinks, and §3's Phase B (`committed + proposed
  < 70% × balance`) eventually denies everything. The system stops trading.
* **TWO OR MORE releases — a DOUBLE RELEASE.** Σ is decremented twice for one
  commitment, so `committed` under-counts and Phase B approves orders the account
  cannot carry. The system OVER-COMMITS.

**A leak is CONSERVATIVE and a double release is not**, which is why `release`
refuses the second call rather than absorbing it, and why `resolve` returns a
`Refusal` that NAMES the terminal path the reservation already took.

### Which of the two is louder — MEASURED, and the intuitive answer is backwards

The intuitive reading is that a leak is loud (trading stops, somebody notices)
and a double release is silent. Against the instrument the spec actually
mandates — §11.7's *"periodic full-scan audit reconciles every running aggregate
vs ground truth (drift ⇒ audit event; material drift ⇒ HALT)"* — the ordering
INVERTS, and `audit()` below is where you can see it:

* A **double release** breaks the arithmetic identity `Σ == fsum(TAKEN margins)`
  at the instant it happens. `audit()` reports non-zero drift on the very next
  cycle, with a magnitude equal to the double-released margin. It is the LOUD one
  and it is loud immediately.
* A **leak** breaks NO identity. A leaked reservation is a perfectly ordinary
  `TAKEN` row: it sums into the incremental aggregate and into the full scan
  identically, so drift stays 0.0 forever. §11.7's audit is structurally blind to
  it. It is the SILENT one, and it stays silent until capital starvation is
  mistaken for conservative sizing.

So the two defects need two different instruments, and this module ships both:
`audit()` catches the double release; only an EXTERNAL record of which orders
reached a terminal outcome catches the leak — which is why `resolve` is the
event-shaped surface and why `refusals()` and `released()` are readable.

---

## WHAT SITS WHERE, and why Σ is not a `sum()`

§11.3 keeps **Σ reservations** as an *incremental running aggregate*, so
`total_reserved()` is an O(1) read of a stored float and never a scan. That is
not a micro-optimisation and removing it would silently disarm §11.7: an
aggregate DERIVED from the store cannot disagree with a full scan OF that store,
so the reconcile would compare a value with itself and report drift 0.0 over any
defect whatsoever. **The two sides of `audit()` must come from two different
pieces of arithmetic or the audit is furniture.**

The price of a genuinely incremental float aggregate is float drift: `+=` and
`-=` over the same values in different orders do not land on the same bits as
`math.fsum`. That drift is real, it is bounded at ~1e-13 for account-scale
figures, and `AUDIT_TOLERANCE` is set orders of magnitude below `MIN_MARGIN` so
it can never swallow a real double release. §11.7's own language ("drift" vs
"material drift") is written for exactly this.

## §4's partial fill

> *"the reservation for the unfilled portion released ... the instant reality
> comes in under the reservation, not on a delay."*

The reservation is taken for the FULL proposed margin and released **whole** on
`FILL`, at fill confirmation — not proportionally, and not later at the IOC
remainder-cancel. The filled portion becomes open margin, which belongs to the
position table and not to this ledger; the unfilled portion simply stops being
reserved. One release, at the fill instant, covers both halves of §4's sentence.

**That makes the remainder-cancel the natural double-release site**, and §4 says
it happens: *"If the cancel loses the race and the remainder fills…"*. A `CANCEL`
event arriving after the `FILL` release is REFUSED here, and the refusal names
`FILL` as the path already taken. It is the realistic shape of the defect, not a
synthetic one.

## WHAT THIS MODULE DOES NOT DO — stated, not implied

Stop conversion and trailing maintenance, protective-exit wiring to broker-order,
session-close flatten, HALT semantics and auto-clear, cold-start reconciliation,
the Sentinel, Scoring and the Allocator are all out of scope for ARC 028 and none
of them is even referenced here. **A Limiter that gates but cannot exit is not a
safety spine yet.** Nor does this module DECIDE when a terminal event has
occurred: it is told. Proving that the Limiter's event handlers call `resolve` on
every real fill, cancel, reject, timeout and blackout is a property of code that
does not exist yet, and `checks/check_reservation_lifecycle.py` says so in its
own verdict rather than letting a green here be read as that guarantee.
"""

from __future__ import annotations

import dataclasses
import enum
import itertools
import math
from typing import Final

from nixrisk.seam import (
    EventKind,
    EventRow,
    Plane1Port,
    ProposedOrder,
    Reservation,
    ReservationState,
    TerminalPath,
)

#: The smallest margin a reservation may carry. A zero-margin reservation is not
#: a cheap trade, it is a reservation that no arithmetic can see: every Σ
#: assertion over it is `0 == 0` and every double release of it is invisible.
#: §3's ingress guard already denies a symbol absent from the margin cache; this
#: is the same refusal one layer in.
#:
#: SET BY MEASUREMENT, not by taste. The first value written here was `1e-6`,
#: which is exactly `AUDIT_TOLERANCE × 1000` — and `checks/check_reservation_
#: lifecycle.py`'s separation floor REDDENED on it on its first run, because
#: `1e-9 * 1000.0` is `1.0000000000000002e-06` in binary floating point and the
#: two figures were not merely close, they were the wrong side of each other.
#: A defect sitting exactly on a discrimination boundary is not separated from
#: it. `1e-3` is six orders above the tolerance, and every real futures margin is
#: six or more orders above THAT.
MIN_MARGIN: Final[float] = 1e-3

#: §11.7's drift floor. Below this, a disagreement between the incremental
#: aggregate and the full scan is float representation, not a lost or duplicated
#: commitment. Chosen relative to `MIN_MARGIN` (three orders below the smallest
#: admissible reservation, and eleven or more below any real futures margin), NOT
#: tuned against an observed run — a tolerance fitted to today's drift is an
#: anchor that moves.
AUDIT_TOLERANCE: Final[float] = 1e-9


class LedgerError(RuntimeError):
    """Base for every refusal this ledger raises. Never caught internally."""


class DuplicateReservation(LedgerError):
    """`take` for a `client_order_id` this ledger has already seen."""


class UnknownReservation(LedgerError):
    """`release` for a `reservation_id` this ledger never minted."""


class DoubleRelease(LedgerError):
    """`release` for a reservation that already reached a terminal path.

    §14: every reservation reaches EXACTLY ONE terminal release. Absorbing the
    second call would under-count committed margin and let §3's Phase B approve
    orders against capital that is already spent.
    """


class InvalidReservation(LedgerError):
    """`take` for an order whose margin is not a positive, finite figure."""


class RefusalKind(enum.Enum):
    """Why a terminal event was NOT turned into a release.

    The two are deliberately distinguishable. `ALREADY_TERMINAL` is the ledger
    working: §14 enforced against a duplicate event. `NEVER_RESERVED` is the
    ledger being asked about an order it has no record of — normal for an order
    denied before Phase B ever took a reservation, and the exact signature of a
    ledger whose `take` and `resolve` disagree about their key, which would leak
    every reservation while reporting every event handled.
    """

    ALREADY_TERMINAL = "already_terminal"
    NEVER_RESERVED = "never_reserved"


@dataclasses.dataclass(frozen=True)
class Refusal:
    """A terminal event this ledger declined to act on, and why.

    Carries the path already taken so the caller can report *"the remainder
    cancel arrived after the fill release"* rather than *"something was wrong"*
    (check contract v2 §11 — a control asserts the REASON).
    """

    kind: RefusalKind
    client_order_id: str
    requested: TerminalPath
    reason: str
    reservation_id: str | None = None
    already_via: TerminalPath | None = None
    already_released_ts: float | None = None


@dataclasses.dataclass(frozen=True)
class Resolution:
    """The outcome of one terminal event. Exactly one member is set.

    Returned rather than raised because a duplicate terminal event is an ordinary
    fact of §4's fill-vs-cancel race and not an error in the caller — while a
    duplicate `release` on the frozen port IS an error, and still raises.
    """

    released: Reservation | None = None
    refusal: Refusal | None = None

    @property
    def accepted(self) -> bool:
        """True when this event produced a release."""
        return self.released is not None


@dataclasses.dataclass(frozen=True)
class LedgerAudit:
    """§11.7's full-scan reconcile of Σ against ground truth.

    `aggregate` is the incremental running value §11.3 mandates; `scanned` is
    recomputed from the TAKEN rows with `math.fsum`. They are produced by two
    different pieces of arithmetic on purpose — see the module docstring.
    """

    aggregate: float
    scanned: float
    outstanding: int
    taken: int
    released: int
    refused: int
    tolerance: float = AUDIT_TOLERANCE

    @property
    def drift(self) -> float:
        """Incremental minus ground truth. Negative ⇒ Σ under-counts."""
        return self.aggregate - self.scanned

    @property
    def material(self) -> bool:
        """§11.7: material drift ⇒ HALT. Below tolerance it is float noise."""
        return abs(self.drift) > self.tolerance


# pylint: disable=too-many-instance-attributes
# NINE attributes, and each is one O(1) INDEX. §11 makes the entry pathway
# "cache reads + arithmetic only", so every lookup this class performs on the hot
# path has to be a dict hit: reservation_id -> live, client_order_id -> live id,
# reservation_id -> terminal, client_order_id -> terminal. Collapsing any pair
# into one store turns one of those into a scan, which is the discipline §11
# exists to enforce; and dropping Σ into a computed property would make §11.7's
# reconcile compare a value with itself (see the module docstring). The remaining
# three are the injected Plane-1 sink (§9), the audit tolerance and the id
# counter. The threshold is about behavioural classes accreting state; these are
# four indices, one aggregate, and three collaborators.
class ReservationLedger:
    """§3's reservation lifecycle. Satisfies the frozen `ReservationLedgerPort`.

    SYNCHRONOUS throughout, for the reason the seam gives: an awaitable `take`
    admits a second pass reading a Σ that does not yet include the first pass's
    approval, which is the over-commitment §3's Phase B exists to prevent.

    Deliberately NOT a subclass of `ReservationLedgerPort`. A `Protocol`'s method
    bodies are docstrings, so inheriting it means a method this class forgot to
    override returns `None` silently — a ledger whose `total_reserved()` answers
    `None` would be caught by nothing at the point of the mistake. Conformance is
    proven by comparing signatures against the port instead, which is a
    measurement rather than a nominal claim.
    """

    def __init__(self, plane1: Plane1Port, tolerance: float = AUDIT_TOLERANCE):
        #: §9: the Limiter is the SOLE writer of Plane 1, and §12.10 books
        #: `reservation taken / released` there. Required, never defaulted to a
        #: sink — a ledger that quietly discards its own audit rows would keep
        #: perfect internal books and leave no record anyone else can read.
        self._plane1 = plane1
        self._tolerance = tolerance
        #: reservation_id -> the TAKEN record. The ground truth Σ is derived from.
        self._live: dict[str, Reservation] = {}
        #: client_order_id -> reservation_id, for the live set only.
        self._by_order: dict[str, str] = {}
        #: reservation_id -> the RELEASED record. Append-only; never popped.
        self._terminal: dict[str, Reservation] = {}
        #: client_order_id -> the RELEASED record, so a late duplicate event can
        #: be refused with the path already taken NAMED.
        self._order_terminal: dict[str, Reservation] = {}
        self._refusals: list[Refusal] = []
        #: §11.3's incremental running aggregate. Maintained by `take`/`release`
        #: and NEVER recomputed from `_live` — see the module docstring on why a
        #: derived Σ makes §11.7's reconcile vacuous.
        self._sigma: float = 0.0
        self._seq = itertools.count(1)

    # -- the port -----------------------------------------------------------

    def take(self, order: ProposedOrder, now: float) -> Reservation:
        """Take a reservation for `order.proposed_margin`. Raises on duplicate."""
        margin = order.proposed_margin
        if not math.isfinite(margin) or margin < MIN_MARGIN:
            raise InvalidReservation(
                f"{order.client_order_id}: proposed margin {margin!r} is not a "
                f"finite figure at or above MIN_MARGIN {MIN_MARGIN!r} — a "
                "reservation no arithmetic can see is not a reservation"
            )
        if order.client_order_id in self._by_order:
            raise DuplicateReservation(
                f"{order.client_order_id}: already holds live reservation "
                f"{self._by_order[order.client_order_id]} — §4 allows one "
                "in-flight action per strategy, so a second take is a defect"
            )
        if order.client_order_id in self._order_terminal:
            raise DuplicateReservation(
                f"{order.client_order_id}: already reached terminal path "
                f"{self._order_terminal[order.client_order_id].released_via} — "
                "a client_order_id is minted once and never reused"
            )
        return self._book(order, margin, now)

    def release(
        self, reservation_id: str, via: TerminalPath, now: float
    ) -> Reservation:
        """Release exactly once. Raises on unknown id and on double release."""
        prior = self._terminal.get(reservation_id)
        if prior is not None:
            raise DoubleRelease(
                f"{reservation_id}: already released via "
                f"{prior.released_via.value if prior.released_via else '?'} at "
                f"{prior.released_ts!r}; refusing a second release via "
                f"{via.value}. §14: every reservation reaches EXACTLY ONE "
                "terminal release, and absorbing this call would decrement Σ "
                "twice for one commitment"
            )
        live = self._live.get(reservation_id)
        if live is None:
            raise UnknownReservation(
                f"{reservation_id}: this ledger never minted that reservation_id"
            )
        return self._settle(live, via, now)

    def outstanding(self) -> tuple[Reservation, ...]:
        """Every reservation currently TAKEN. The ground truth Σ is derived from."""
        return tuple(sorted(self._live.values(), key=lambda res: res.reservation_id))

    def total_reserved(self) -> float:
        """§11.3's running aggregate: Σ margin over the TAKEN set."""
        return self._sigma

    # -- the event surface --------------------------------------------------

    def resolve(
        self,
        client_order_id: str,
        via: TerminalPath,
        now: float,
        reason: str = "",
    ) -> Resolution:
        """One terminal event for one order. Releases, or REFUSES and says why.

        This is the surface the Limiter's event handlers drive. `release` is the
        port's id-keyed primitive and raises; this is keyed by the identifier a
        broker event actually carries, and a duplicate is data rather than a
        crash (§4's fill-vs-remainder-cancel race is expected, not exceptional).
        """
        reservation_id = self._by_order.get(client_order_id)
        if reservation_id is not None:
            return Resolution(
                released=self._settle(self._live[reservation_id], via, now, reason)
            )
        prior = self._order_terminal.get(client_order_id)
        if prior is not None:
            return Resolution(
                refusal=self._refuse_duplicate(client_order_id, via, prior)
            )
        return Resolution(refusal=self._refuse_unknown(client_order_id, via))

    # -- readable records ---------------------------------------------------

    def released(self) -> tuple[Reservation, ...]:
        """Every RELEASED record, oldest first. Append-only; never rewritten."""
        return tuple(
            sorted(self._terminal.values(), key=lambda res: res.reservation_id)
        )

    def refusals(self) -> tuple[Refusal, ...]:
        """Every terminal event this ledger declined, in arrival order."""
        return tuple(self._refusals)

    def audit(self) -> LedgerAudit:
        """§11.7's full-scan reconcile. Off the hot path; drift ⇒ audit event."""
        return LedgerAudit(
            aggregate=self._sigma,
            scanned=math.fsum(res.margin for res in self._live.values()),
            outstanding=len(self._live),
            taken=len(self._live) + len(self._terminal),
            released=len(self._terminal),
            refused=len(self._refusals),
            tolerance=self._tolerance,
        )

    # -- internals ----------------------------------------------------------

    def _book(self, order: ProposedOrder, margin: float, now: float) -> Reservation:
        """Mint, store, increment Σ, and write the §12.10 Plane-1 row.

        **ALL-OR-NOTHING, and that is a MEASURED repair (ARC 038 / B, F-B1).**
        `_emit` can raise: the shipped Plane-1 sink is `nixrisk.wal.Plane1Wal`,
        whose `enqueue` raises `DiskCritical` when the WAL is disk-critical or the
        append itself fails, and §12.4 makes that a real condition rather than a
        hypothetical one. `gate.py::GatePass._settle` wraps this call in a blanket
        `except Exception` and turns any failure into a DENY — so a `take` that
        mutated the stores and THEN raised left a reservation held for an order
        that is never sent, and no terminal event can ever release it. Driven
        against a real `Plane1Wal` under a real `RLIMIT_FSIZE` refusal (EFBIG,
        errno 27): three DENIED orders holding 12000.0 of margin permanently,
        with `audit()` reporting drift 0.0 the whole time, because a LEAK breaks
        no arithmetic identity and §11.7's reconcile is structurally blind to one.

        The undo restores Σ by ASSIGNMENT rather than by `-= margin`: `+=` then
        `-=` over binary floats does not return to the same bits, and the repair
        for a leak must not introduce the drift §11.7 exists to watch.

        The reservation_id counter is NOT rewound. Ids are identities, not a dense
        sequence, and re-minting a withdrawn id would make two different refusals
        indistinguishable in §9's record.

        This is the TAKE direction ONLY. `_settle`'s deliberate
        mutate-then-record order — releasing capital even when the record fails —
        is CHECK-DEBT D3.53's ruling and is untouched here.
        """
        reservation = Reservation(
            reservation_id=f"RSV-{next(self._seq):08d}",
            client_order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            margin=margin,
            state=ReservationState.TAKEN,
            taken_ts=now,
        )
        self._live[reservation.reservation_id] = reservation
        self._by_order[order.client_order_id] = reservation.reservation_id
        sigma_before = self._sigma
        self._sigma += margin
        try:
            self._emit(EventKind.RESERVATION_TAKEN, reservation, "approved", now)
        except BaseException:
            del self._live[reservation.reservation_id]
            del self._by_order[order.client_order_id]
            self._sigma = sigma_before
            raise
        return reservation

    def _settle(
        self, live: Reservation, via: TerminalPath, now: float, reason: str = ""
    ) -> Reservation:
        """The ONE place a reservation leaves the TAKEN set. Σ decrements here.

        Every terminal path funnels through this method rather than each handler
        doing its own bookkeeping: a per-path release is a per-path opportunity
        to forget one of the four stores, and §3's *"No leak paths"* is a
        statement about the whole path set at once.
        """
        released = dataclasses.replace(
            live,
            state=ReservationState.RELEASED,
            released_ts=now,
            released_via=via,
        )
        del self._live[live.reservation_id]
        del self._by_order[live.client_order_id]
        self._terminal[live.reservation_id] = released
        self._order_terminal[live.client_order_id] = released
        self._sigma -= live.margin
        self._emit(EventKind.RESERVATION_RELEASED, released, reason or via.value, now)
        return released

    def _refuse_duplicate(
        self, client_order_id: str, via: TerminalPath, prior: Reservation
    ) -> Refusal:
        """§14 enforced: a second terminal event for an already-terminal order."""
        already = prior.released_via
        refusal = Refusal(
            kind=RefusalKind.ALREADY_TERMINAL,
            client_order_id=client_order_id,
            requested=via,
            reservation_id=prior.reservation_id,
            already_via=already,
            already_released_ts=prior.released_ts,
            reason=(
                f"{client_order_id}: reservation {prior.reservation_id} already "
                f"released via {already.value if already else '?'}; refusing "
                f"a second release via {via.value} (§14: exactly one terminal "
                "release). Σ is unchanged"
            ),
        )
        self._refusals.append(refusal)
        return refusal

    def _refuse_unknown(self, client_order_id: str, via: TerminalPath) -> Refusal:
        """No reservation was ever taken for this order.

        Legitimate for an order denied before Phase B, and it is ALSO the exact
        signature of a ledger whose `take` and `resolve` key on different things
        — which would leak every reservation while reporting every event
        handled. Recorded with its own kind so the two can be told apart.
        """
        refusal = Refusal(
            kind=RefusalKind.NEVER_RESERVED,
            client_order_id=client_order_id,
            requested=via,
            reason=(
                f"{client_order_id}: no reservation was ever taken for this "
                f"client_order_id, so there is nothing to release via "
                f"{via.value}. Σ is unchanged"
            ),
        )
        self._refusals.append(refusal)
        return refusal

    def _emit(
        self, kind: EventKind, reservation: Reservation, reason: str, now: float
    ) -> None:
        """§12.10's Plane-1 row. Enqueue only — durability is §9's WAL, not ours.

        Written AFTER the store mutation, deliberately. The ledger's own state is
        the money truth §11.3 publishes; a WAL that cannot append is §12.4's
        disk-critical HALT input and is not a decision this module gets to make.
        The residual — an enqueue that raises leaves a settled reservation with
        no Plane-1 row — is CHECK-DEBT D3.53 rather than silently swallowed here.
        """
        self._plane1.enqueue(
            EventRow(
                kind=kind,
                ts=now,
                strategy_id=reservation.strategy_id,
                reason=reason,
                fields={
                    "reservation_id": reservation.reservation_id,
                    "client_order_id": reservation.client_order_id,
                    "symbol": reservation.symbol,
                    "margin": repr(reservation.margin),
                    "via": (
                        reservation.released_via.value
                        if reservation.released_via
                        else ""
                    ),
                    "sum_reservations": repr(self._sigma),
                },
            )
        )
