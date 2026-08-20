"""§3's NON-FILL terminal outcomes — the CANCEL, REJECT and PENDING_TIMEOUT releases.

ARC 044 / I2. Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`.

§14:972 locks the invariant: *"Every reservation reaches exactly one terminal
release."* §3:151 names the whole release set:

> taken at approval → released on: fill (converts to open-margin), cancel,
> reject, pending-timeout resolution, blackout-onset cancellation. **No leak
> paths.**

Before this module three of those six paths had **no production release site at
all** — measured by AST census over `scripts/nixrisk/*.py` in ARC 038 (F-B3) and
carried as CHECK-DEBT **D3.358**:

    FILL            fills.py      (IocRemainder.release_remainder)
    BLACKOUT_ONSET  blackout.py, flatten.py
    HALT_ONSET      flatten.py
    CANCEL          NONE
    REJECT          NONE
    PENDING_TIMEOUT NONE

An entry that was rejected by the venue, or cancelled outside a blackout/HALT
onset, or that never resolved, therefore held its whole reservation for the life
of the process. That is the AT-LEAST-ONE half of §14 failing, and it is invisible
to §11.7: a leaked reservation sums into the incremental aggregate and into the
full scan **identically**, so `ReservationLedger.audit()` reports `drift=0.0` and
`material=False` over it forever (driven, ARC 044 S1b). The consequence is a slow
strangle — Σ reservations climbs monotonically, `committed` never falls, and §3
Phase B (`committed + proposed < 70% × balance`) eventually denies everything
while looking exactly like a market that stopped giving signals.

## WHY THESE THREE LIVE HERE AND NOT IN `reservations.py`

The census that measures the wiring gap scans every production module for a
`resolve`/`release` call. Had the ledger booked its own paths, the ledger could
satisfy that census with six one-line methods and the measurement would become
self-satisfying — the exact circularity `seam.TerminalPath`'s docstring forbids
("deriving the path set from the code and then proving the code covers it is
circular and passes while measuring nothing"). A release site has to be an EVENT
SURFACE that something outside the ledger drives, which is what `fills.py`,
`blackout.py` and `flatten.py` already are. This module is the fourth.

They are also not `fills.py`'s. `fills.py` owns §4's *fill* arithmetic — the
partial-fill remainder, the IOC cancel, the conversion of reservation to open
margin. A cancel that filled NOTHING, a reject, and a timeout carry no quantity
and no price: nothing converts, and `IocRemainder._guard` refuses `filled_qty <=
0` precisely because a remainder computed over a zero fill is a statement about
nothing. Routing a zero-fill cancel through the fill path would make the count of
partial fills stop being the count of partial fills.

## PENDING TIMEOUT IS RESOLVED BY A QUERY, AND THE TIMER IS NOT THE EVENT

§2A:71 / §4:241 / §12A:830 are unanimous: a pending-order timeout is resolved by
`query_order_status` and **NEVER by a resend**. §4 "Failure resolution" gives the
query three outcomes — *confirmed / cancelled / indeterminate*.

The release therefore hangs off the RESOLUTION, never off the timer firing. That
distinction is the whole safety argument: releasing at `PENDING_ACK_TIMEOUT_MS`
would free margin for an order that is still working at the venue, which is an
under-count of `committed` and the cap breach §15 C1 closed. `flatten.py` already
took the same decision in the other direction and says so at its own refusal site
— an entry the broker would not cancel is "STILL WORKING at the venue … Its
reservation is NOT released, so it is still counted in committed margin, which is
the safe direction".

So, per venue state (`broker_seam.OrderStatus.state`, consumed structurally
through `StatusQueryPort` rather than imported — §2A invariant 2, and the same
narrowing `fills.py::CancelPort` applies):

    cancelled | rejected  -> RELEASE under PENDING_TIMEOUT (dead, nothing working)
    filled               -> NOT released here. The fill path owns FILL (§3: it
                            converts to open-margin, and only `fills.py` has the
                            quantities that conversion needs).
    working              -> NOT released. The commitment is real and live.
    indeterminate        -> NOT released. §4's answer to an unresolvable order is
                            flatten-on-uncertainty, which releases under its own
                            cause in `flatten.py`.
    unknown              -> NOT released, and this is the one deliberately
                            conservative choice. `unknown` means THIS ADAPTER has
                            no record of the id — it is not a statement about the
                            venue (`broker_seam.OrderStatus`'s own docstring), so
                            treating it as death would release margin for an
                            order that may be live under another adapter session.
                            Held, counted, and named in `history()`. CHECK-DEBT
                            D3.441.

A held outcome is not a leak: nothing terminal has happened to that reservation
yet, and whichever real terminal event eventually arrives releases it exactly
once. §14 is about reservations that reach a terminal event, and a working order
has not.

## EXACTLY ONE, NOT ONE MORE — where the AT-MOST-ONE half is enforced

Nothing here counts, subtracts, or remembers "already released". Every path goes
through `ReservationLedger.resolve`, which is keyed by `client_order_id` and
already refuses a second terminal event with a `Refusal` naming the path already
taken (`RefusalKind.ALREADY_TERMINAL`) while leaving Σ bit-identical. This module
therefore cannot double-count even in principle: a duplicate cancel, a reject
racing a timeout resolution, or a timeout resolution racing the fill path all
land on the same guard and are RECORDED as refusals — released-exactly-once, not
released-again. `refused` and `history()` make that observable rather than
believed, which is the argument `ReservationLedger` makes for its own counters.

**NO retry and NO auto-resend anywhere in this module** (§4, §2A:71). The only
outbound verb it holds is a status QUERY.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, runtime_checkable

from .seam import TerminalPath

#: Cited by every refusal and every guard so a reader lands on the file.
SITE = "scripts/nixrisk/outcomes.py"


#: Which PUBLIC verb of `OrderOutcomes` books which §3 release path.
#:
#: Declared so an instrument can drive this module WITHOUT spelling a release
#: path as a literal of its own. `check_reservation_lifecycle`'s ARM WIRING is
#: forbidden by its own test (`test_the_PATH_SET_is_PARSED_FROM_THE_SPEC_and_
#: appears_NOWHERE_in_the_gate`) from naming any `TerminalPath` member in its
#: source, because an expected set the gate chose proves nothing. It therefore
#: reads this map — and CROSS-CHECKS it against its own AST census of this file,
#: so a declaration that under-states what this module actually books is
#: CANNOT_MEASURE, never a quietly smaller drive. Read-only for the same reason:
#: a subject that could rewrite the instrument's plan at run time is not a
#: subject.
HANDLES: Mapping[TerminalPath, str] = MappingProxyType(
    {
        TerminalPath.CANCEL: "on_cancel",
        TerminalPath.REJECT: "on_reject",
        TerminalPath.PENDING_TIMEOUT: "resolve_pending_timeouts",
    }
)


class OutcomeError(RuntimeError):
    """Base for this module's refusals. Never raised for ordinary duplicates."""


class InvalidOutcomeConfig(OutcomeError):
    """A tunable that makes the timeout arm a statement about nothing."""


@runtime_checkable
class ReservationBookPort(Protocol):
    """§3's reservation lifecycle, as this module consumes it. THREE verbs.

    Narrower than `seam.ReservationLedgerPort` on purpose: no `take` and no
    `release`. This module ENDS reservations and never starts one, and `release`
    is the id-keyed primitive that RAISES on a double release — a broker event
    arriving twice is data, not an exception (§4's fill-vs-cancel race is
    expected), so `resolve` is the only release verb reachable from here.
    """

    def resolve(
        self, client_order_id: str, via: TerminalPath, now: float, reason: str = ""
    ) -> Any:
        """One terminal event for one order. Releases, or REFUSES and says why."""

    def outstanding(self) -> Sequence[Any]:
        """Every reservation currently TAKEN — what the timeout arm sweeps."""

    def total_reserved(self) -> float:
        """§11.3's running aggregate, read back so a release is measured."""


@runtime_checkable
class StatusQueryPort(Protocol):  # pylint: disable=too-few-public-methods
    """§4's pending-timeout resolution verb. ONE verb, and it is a READ.

    Deliberately not `broker_seam.BrokerOrderPort`: that port can place and
    flatten, and a reservation-release path that could place an order would be a
    second order-placement site. It is also not IMPORTED from `scripts/broker`
    — §2A invariant 2 keeps vendor structure below the seam and this module
    consumes the answer structurally (`.state`), exactly as `fills.py::CancelPort`
    narrows the same adapter.
    """

    def query_order_status(self, client_order_id: str) -> Any:
        """§2A:71 — the status query. NEVER an auto-resend."""


#: Venue states that mean the order is DEAD with nothing working: the reservation
#: it holds can never convert and must be returned. Spelled as the strings
#: `broker_seam.OrderStatus.state` documents, because that field is the seam's
#: neutral vocabulary and this module must not invent a second one.
DEAD_STATES: frozenset[str] = frozenset({"cancelled", "rejected"})

#: Every state the seam declares. A state outside this set is a seam change this
#: module has not been taught, and it is REFUSED rather than guessed at.
KNOWN_STATES: frozenset[str] = DEAD_STATES | frozenset(
    {"working", "filled", "unknown", "indeterminate"}
)


class Disposition(enum.Enum):
    """What one outcome event did. Three-valued, and the third is not an error."""

    RELEASED = "released"
    """The reservation reached its terminal release, exactly once."""

    REFUSED = "refused"
    """The ledger declined: this order already reached a terminal path."""

    HELD = "held"
    """No terminal event yet — the commitment is still real (see the module doc)."""


@dataclass(frozen=True)
class OutcomeRecord:  # pylint: disable=too-few-public-methods
    """One event this module handled. Append-only evidence, never the hot path."""

    client_order_id: str
    via: TerminalPath
    disposition: Disposition
    sigma_before: float
    sigma_after: float
    detail: str

    @property
    def released_margin(self) -> float:
        """How much Σ actually fell. A RELEASED record with 0.0 here is a leak."""
        return self.sigma_before - self.sigma_after


class OrderOutcomes:  # pylint: disable=too-many-instance-attributes
    """The Limiter's terminal-event handlers for §3's three non-fill paths.

    Construction validates the one tunable it holds, loudly (§12A:801-802: an
    invalid set is rejected at boot, not absorbed at run time).
    """

    def __init__(
        self,
        reservations: ReservationBookPort,
        *,
        clock: Callable[[], float],
        pending_ack_timeout_s: float,
    ) -> None:
        if not callable(clock):
            raise InvalidOutcomeConfig(
                f"{SITE}: clock={clock!r} is not callable — the timeout arm reads "
                "its deadline from the clock and a fixed instant would make every "
                "order permanently un-due or permanently due"
            )
        timeout = float(pending_ack_timeout_s)
        if not math.isfinite(timeout) or timeout <= 0.0:
            raise InvalidOutcomeConfig(
                f"{SITE}: pending_ack_timeout_s={pending_ack_timeout_s!r} is not a "
                "finite positive interval. §12A:830 PENDING_ACK_TIMEOUT_MS is the "
                "deadline after which §4 QUERIES; a non-positive one makes every "
                "reservation due the instant it is taken, and the query becomes a "
                "statement about nothing"
            )
        self._reservations = reservations
        self._clock = clock
        self.pending_ack_timeout_s = timeout

        #: Observables. A component that cannot say what it did can only be
        #: believed, not measured (`ReservationLedger`'s own argument).
        self.cancels_released = 0
        self.rejects_released = 0
        self.timeouts_released = 0
        self.refused = 0
        self.held = 0
        self.queries = 0
        self._history: list[OutcomeRecord] = []

    # -- the PUSH events: the venue told us the order is over ---------------
    #
    # Each of the three paths spells its own `resolve(…, TerminalPath.X, …)`
    # call, LITERALLY, and that is not repetition to be factored out. The AST
    # census that measures which of §3's release paths production actually books
    # reads the `via` argument STATICALLY (`check_reservation_lifecycle` ARM
    # WIRING; `test_arc038_b_reservation_terminality::_release_sites`). A single
    # shared helper taking `via` as a parameter makes every one of these paths
    # `<unresolved>` to that census — unreadable, therefore uncountable, and the
    # gate is required to answer CANNOT_MEASURE over it rather than credit it.
    # Three literal sites are also three INDEPENDENTLY plantable ones: a leak
    # planted on the cancel path must not be able to hide behind the reject.

    def on_cancel(self, client_order_id: str, *, reason: str = "") -> OutcomeRecord:
        """A cancel confirmation arrived: nothing filled, the order is over (§3).

        This is the IOC-full-cancel and the plain venue cancel. It is NOT the
        partial-fill remainder cancel — that one accompanies a real fill and is
        `fills.py::IocRemainder`'s, released under `FILL` because the filled part
        converts to open margin.
        """
        why = reason or (
            "the venue confirmed the order cancelled with nothing filled — §3 "
            "releases the reservation on cancel, and no margin converts"
        )
        at = self._clock()
        before = float(self._reservations.total_reserved())
        resolution = self._reservations.resolve(
            client_order_id, TerminalPath.CANCEL, at, why
        )
        return self._book(client_order_id, TerminalPath.CANCEL, before, resolution, why)

    def on_reject(self, client_order_id: str, *, reason: str = "") -> OutcomeRecord:
        """The venue refused the order outright: it will never work (§3)."""
        why = reason or (
            "the venue rejected the order — §3 releases the reservation on "
            "reject, and nothing was ever working against it"
        )
        at = self._clock()
        before = float(self._reservations.total_reserved())
        resolution = self._reservations.resolve(
            client_order_id, TerminalPath.REJECT, at, why
        )
        return self._book(client_order_id, TerminalPath.REJECT, before, resolution, why)

    # -- the PULL event: §4's pending-timeout resolution --------------------

    def due_for_status_query(self, now: float | None = None) -> tuple[str, ...]:
        """Every outstanding order past §12A:830's ack deadline, oldest first.

        Reads `taken_ts` off the ledger's own TAKEN set rather than keeping a
        second clock of its own: a private copy of when each order was taken is a
        second source of truth that can disagree with the one Σ is derived from.
        """
        at = self._clock() if now is None else float(now)
        deadline = at - self.pending_ack_timeout_s
        due = [
            reservation
            for reservation in self._reservations.outstanding()
            if float(reservation.taken_ts) <= deadline
        ]
        due.sort(
            key=lambda reservation: (
                float(reservation.taken_ts),
                str(reservation.client_order_id),
            )
        )
        return tuple(str(reservation.client_order_id) for reservation in due)

    def resolve_pending_timeouts(
        self, query: StatusQueryPort, now: float | None = None
    ) -> tuple[OutcomeRecord, ...]:
        """§4's failure resolution: QUERY every overdue order, never resend.

        One record per overdue order — RELEASED when the venue says the order is
        dead, HELD when it is still working or unresolvable, REFUSED when some
        other terminal event got there first. The sweep runs over a SNAPSHOT of
        the due set, so a release performed inside the loop cannot re-enter it.
        """
        at = self._clock() if now is None else float(now)
        records: list[OutcomeRecord] = []
        for client_order_id in self.due_for_status_query(at):
            self.queries += 1
            status = query.query_order_status(client_order_id)
            state = str(getattr(status, "state", ""))
            if state not in KNOWN_STATES:
                records.append(
                    self._hold(
                        client_order_id,
                        TerminalPath.PENDING_TIMEOUT,
                        f"{SITE}: query_order_status returned state={state!r}, "
                        f"which is outside the seam's declared set "
                        f"{sorted(KNOWN_STATES)}. An unrecognised state is not "
                        "evidence of death, so the reservation is HELD — the "
                        "direction that over-counts committed margin and can "
                        "never breach a cap",
                    )
                )
                continue
            if state not in DEAD_STATES:
                records.append(
                    self._hold(
                        client_order_id,
                        TerminalPath.PENDING_TIMEOUT,
                        f"{SITE}: the §4 status query answered {state!r} at "
                        f"{at!r}; nothing terminal has happened to this order, so "
                        "its reservation stays committed (§4 resolves a timeout "
                        "by querying and NEVER by resending)",
                    )
                )
                continue
            why = (
                f"§4 pending-timeout resolution: the status query answered "
                f"{state!r} after {self.pending_ack_timeout_s}s "
                f"(§12A:830 PENDING_ACK_TIMEOUT_MS), so the order is dead with "
                "nothing working and §3 releases its reservation"
            )
            before = float(self._reservations.total_reserved())
            resolution = self._reservations.resolve(
                client_order_id, TerminalPath.PENDING_TIMEOUT, at, why
            )
            records.append(
                self._book(
                    client_order_id,
                    TerminalPath.PENDING_TIMEOUT,
                    before,
                    resolution,
                    why,
                )
            )
        return tuple(records)

    # -- evidence -----------------------------------------------------------

    def history(self) -> tuple[OutcomeRecord, ...]:
        """Every event this module handled, in arrival order. Append-only."""
        return tuple(self._history)

    def released(self) -> tuple[OutcomeRecord, ...]:
        """Only the records that actually returned margin."""
        return tuple(
            record
            for record in self._history
            if record.disposition is Disposition.RELEASED
        )

    # -- internals ----------------------------------------------------------

    #: Which observable each path increments once the ledger has RELEASED. The
    #: `via` never travels through this map on its way to `resolve` — see the
    #: comment above `on_cancel`.
    _COUNTER: ClassVar[Mapping[TerminalPath, str]] = {
        TerminalPath.CANCEL: "cancels_released",
        TerminalPath.REJECT: "rejects_released",
        TerminalPath.PENDING_TIMEOUT: "timeouts_released",
    }

    def _book(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        client_order_id: str,
        via: TerminalPath,
        before: float,
        resolution: Any,
        reason: str,
    ) -> OutcomeRecord:
        """Classify ONE already-driven terminal event and record what happened.

        Σ is read back HERE, after the ledger has acted, so the record carries
        what the ledger did rather than what this module asked for — a component
        that reports its own intent is furniture.
        """
        after = float(self._reservations.total_reserved())
        if getattr(resolution, "released", None) is not None:
            counter = self._COUNTER[via]
            setattr(self, counter, getattr(self, counter) + 1)
            return self._record(
                client_order_id, via, Disposition.RELEASED, before, after, reason
            )
        self.refused += 1
        refusal = getattr(resolution, "refusal", None)
        return self._record(
            client_order_id,
            via,
            Disposition.REFUSED,
            before,
            after,
            f"{SITE}: the ledger REFUSED this {via.value} — "
            f"{getattr(refusal, 'reason', refusal)!r}. §14 gives every "
            "reservation exactly ONE terminal release, so a second event is "
            "recorded and Σ is left where it was",
        )

    def _hold(
        self, client_order_id: str, via: TerminalPath, detail: str
    ) -> OutcomeRecord:
        """No terminal event. Σ is read twice anyway, so the record can prove it."""
        self.held += 1
        sigma = float(self._reservations.total_reserved())
        return self._record(
            client_order_id, via, Disposition.HELD, sigma, sigma, detail
        )

    def _record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        client_order_id: str,
        via: TerminalPath,
        disposition: Disposition,
        before: float,
        after: float,
        detail: str,
    ) -> OutcomeRecord:
        record = OutcomeRecord(
            client_order_id=str(client_order_id),
            via=via,
            disposition=disposition,
            sigma_before=before,
            sigma_after=after,
            detail=detail,
        )
        self._history.append(record)
        return record
