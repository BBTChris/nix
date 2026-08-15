"""The ORIGIN WRITE — the §3 row a CONFIRMED FILL first publishes for a trade.

ARC 033 / Phase 0.2. Discharges the mechanism half of CHECK-DEBT **D3.150**:
before this module, exactly TWO production constructions of `PositionRow`
existed — `picture._decode_row`, which READS `stop_distance` off the wire, and
`flatten._confirmed_rows`, which CARRIES it from the mirror's row onto a CLOSING
row. **Neither ever CHOSE one.** There was no fill path at all, so no code ever
created the row that first represents an open position, and every
`stop_distance` in the tree was a test or gate literal. §7:501 prices bucket
exposure from that field, so the number §7's correlation cap consumes had no
production source. This module is that source.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`.

===========================================================================
WHERE THE NUMBER COMES FROM, AND WHY IT IS NOT A SECOND TABLE JOIN
===========================================================================
`stop_distance` is read from the **authoritative stop book** —
`StopState.initial_distance_ticks`, which `StopBook.arm` records from
`ProposedOrder.stop_ticks`, which is the very distance the sizer sized against
(§7:476: `risk_contracts = floor(per_trade_risk_$ / ((stop_ticks + slippage_pad)
× tick_value))`). So the published figure IS the sizer's own input, travelling
to the consumer that re-prices the same exposure.

`seam.PositionRow`'s own docstring says the field is *"explicitly NOT a read of
the Limiter's stop book"*, and that sentence is TRUE OF THE READER AND FALSE OF
THE WRITER — the distinction is who reads it and when, and it is worth spelling
out because read as an absolute it forbids the only mechanism that can ever
populate the field:

* **Refused (D3.136 Option B).** A CONSUMER — the Allocator's correlation cap —
  joining the published picture to the stop book at sizing time. Two tables on
  two clocks, and §6.4's cross-table skew in the same breath as it fixes one
  snapshot. Nothing publishes the stop book, so it is also unavailable.
* **Ruled (D3.136 Option A, `SPEC-A9`, built in ARC 032).** The distance rides
  the ONE versioned snapshot. Which requires that someone STAMP it there, once,
  and the only authority holding it is the stop book.

This module is that stamp, and it is the one place the two tables may meet:
the Limiter is §9's sole writer and §5's single-threaded loop, it reads its own
book and commits the row in ONE motion, and after the commit no consumer needs
the second table at all. A writer reading its own state to build a snapshot is
not a cross-table join; it is what building a snapshot IS.

===========================================================================
THE JOIN THE SPEC DOES NOT DEFINE — DECLARED, INJECTED, AND OVERRIDABLE
===========================================================================
§3:159 keys the position table by `trade_id`; the stop book, `ProposedOrder`,
`Reservation` and §4's `(order_id, exec_id)` dedup tuple are keyed by
`client_order_id`; **and no sentence in the frozen spec, and no code in this
tree, relates them.** *"The published stop_distance for the same trade"* was
therefore not expressible — the D3.137 shape (a seam that cannot express its own
inputs) one module over.

Writing `trade_id == client_order_id` inside the row construction would have
BURIED an architectural decision in an equality, where no reader sees it and no
gate can redden on it. Instead:

* `seam.TradeOrigin` / `seam.TradeOriginPort` (ARC 033 / 0.2, additive) declare
  the relationship as a value and a lookup;
* `EntryOrderOrigins` implements the port and takes the minting policy as an
  INJECTED callable;
* `identity_trade_id` is the DEFAULT binding — *a trade IS the entry order that
  opened it* — which is sound in this system's declared scope (intraday-only,
  one strategy per instrument, one in-flight action per strategy, §4) and is
  **a named default, not an identity**: `EntryOrderOrigins(mint=...)` changes it
  without touching a single construction site, and `test_positions.py` drives a
  non-identity mint end to end so the seam is proven not to assume it.

The relationship itself remains an ARCHITECT RULING that is owed. This module
takes a default so the mechanism can exist; it does not take the decision.

===========================================================================
FAIL CLOSED AND LOUD — A FILL WITH NO ARMED STOP PUBLISHES NO ROW
===========================================================================
`on_fill` REFUSES, with `UnstoppedFill`, when the trade has no armed stop. It
does not default, does not zero, and does not guess. The reasoning is written
out because both available dispositions are imperfect and the choice must be
visible:

* **A defaulted/zero distance is a LIE THE CAP CANNOT DETECT.** §7:501 prices the
  position at zero dollar risk, the bucket reads emptier than it is, and an
  emptier bucket **ADMITS MORE** — D3.136's fail-open under a new spelling, on a
  field that now looks populated.
* **An absent row is an ABSENCE THIS MODULE NAMES AND COUNTS.** It admits more
  too — that is the `unbucketed` door D3.136 found while closing the first — but
  it raises, it increments `refusals`, and it records the fill in `unstopped()`
  where a supervising loop can see it. A number nobody can question is worse
  than a gap that shouts.
* **"Publish and mark" is not available to this arc.** `PositionRow`'s field
  list is frozen at `SEAM_REV 1.1.0`; adding an `unpriced` flag is a seam
  widening and an architect ruling. Refusal is the only fail-closed disposition
  inside this arc's authority, and that is a reason for the choice, not a
  rationalisation of it.

**And the condition is not merely a bookkeeping gap.** A confirmed fill with no
armed stop is an UNPROTECTED POSITION (§4, §12.1): §14 resolves every
uncertainty toward flat, so the correct response is a protective flatten on the
UNCERTAINTY trigger, not a row. This module cannot fire one — §14 makes flatten
execution Limiter-only and `nixrisk.flatten` owns it — so it refuses loudly and
leaves the escalation to the caller. **Nothing yet consumes `unstopped()` to
fire that flatten**, and that residual is reported as CHECK-DEBT rather than
implied by a green here.

**The fill is booked BEFORE the refusal, deliberately.** §4: *"the fill is a
fact the system reports, never a negotiation."* The execution ledger records
what the broker did whatever this module then decides about publishing; a
refusal that also discarded the fill would make the ledger's derived position
disagree with the account.

===========================================================================
DOCTRINE C.9 — POSITION IS NOT RE-DERIVED HERE
===========================================================================
`size` comes from `ExecutionLedger.order_cumulative()` — §4's idempotent ledger,
which already owns *"position state derives from cumulative fills — immune to
duplicate or out-of-order execution reports"* and is gated by
`checks/check_execution_ledger.py`. This module ingests the report into that
ledger and then ASKS it. There is no second position arithmetic here, so a
partial fill publishes the true cumulative size (§4's partial-fill rule: position
= actual filled qty) and a re-delivered report cannot move the published table.

The SIGN is `report.side.sign`, and it is safe to take from the report because
the ledger refuses a side flip within one order (`_guard_order_consistency`):
one `order_id` is one instrument in one direction, checked by the instrument
that owns it rather than assumed here.

`margin` is `|size| × margin_per_contract[symbol]`, read from the CURRENT
picture's own margin field set (§6.4's live per-symbol margin, published under
the same writer and version stamp) — not from a fourth source. A symbol absent
from it is **not-tradable** (§4:198) and is refused, never defaulted.

===========================================================================
WHAT THIS MODULE DOES NOT DO — stated, not implied
===========================================================================
* **It does not ARM the stop.** `StopBook.arm` is the distance→price conversion
  at confirmed fill (§4) and it belongs to the same moment, but arming here
  would mean this module read back a figure it had just produced — a comparison
  of a value against itself, and the exact independence `check_origin_write`
  requires between the two sides. The stop must already be armed; if it is not,
  see the refusal above. **Nothing in production calls `arm` either** — that is
  the other half of the same hole and is reported as CHECK-DEBT.
* **It writes no Plane-1 row.** §9's inventory has a `filled` transition and
  `seam.EventKind` deliberately has no member for it (*"a member lands here ONLY
  when the machinery that emits it exists"*). Adding one is a seam edit outside
  this phase's authority, so the §9 `filled` row is owed, not silently skipped.
* **It does not convert the reservation.** §3's lifecycle releases a reservation
  ON FILL (it *"converts to open-margin"*) and releases the unfilled remainder
  (§4's partial-fill rule). `sum_reservations` is a PASS-THROUGH: a caller that
  owns `ReservationLedger` hands in the post-release figure so the whole change
  lands under ONE version stamp; a caller that passes nothing carries the
  previous figure forward, which DOUBLE-COUNTS the filled portion (open margin
  plus a still-taken reservation) and therefore errs toward LESS deployable
  capital. Conservative, still wrong, and owed as CHECK-DEBT rather than wired
  half-way here.
* **It does not close, flatten, or reconcile**, and it is not a second position
  table: every row it produces goes onto `FinancialPictureBook.commit()`, the
  one snapshot with one writer and one version stamp (§3, §9).
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable
from typing import NoReturn, Protocol, runtime_checkable

from nixrisk.execution import ExecutionLedger, ExecutionReport
from nixrisk.picture import FinancialPictureBook
from nixrisk.seam import (
    FinancialPicture,
    PositionRow,
    PositionState,
    ProposedOrder,
    StopState,
    TradeOrigin,
    TradeOriginPort,
)

# R0903 (too-few-public-methods): `StopLookupPort` is a single-verb Protocol —
# the whole surface this module needs from the stop book, and a second method
# would be a reader that also does something else.
# pylint: disable=too-few-public-methods


class OriginError(RuntimeError):
    """An origin write was refused. Always names what and why (§18)."""


class UnknownTrade(OriginError):
    """A fill arrived for an order this system never recorded opening a trade.

    §3 keys the position table by `trade_id`; without an origin record there is
    no key to publish the row under. Refused rather than invented: a synthesised
    trade id would put a position into the published table that no approval, no
    reservation and no strategy feedback path knows about (§4's feedback is
    tagged BY trade_id precisely to prevent cross-position mis-application).
    """


class UnstoppedFill(OriginError):
    """A confirmed fill whose trade has no armed stop. See the module docstring.

    Not a defaulted row and not a zero: §7:501 prices bucket exposure from the
    distance, so a zero prices a real position at zero risk and ADMITS MORE. It
    is also an unprotected position (§4, §12.1) and §14 resolves toward flat.
    """


class UntradableSymbol(OriginError):
    """A fill in a symbol absent from the published margin field set (§4:198).

    The row's `margin` has no scale without it, and a guessed margin figure
    enters `committed` — the number every Phase-B capital rule is evaluated
    against (§3).
    """


class DuplicateOrigin(OriginError):
    """An order or a minted `trade_id` was recorded twice.

    Both directions are refused. A re-recorded order would let a second approval
    silently re-key a live trade; a COLLIDING `trade_id` would put two positions
    under one key in a table §3 says is keyed by it — the defect
    `picture.picture_defects` refuses a whole snapshot for, caught here at the
    moment it is created instead of at publish time.
    """


# ---------------------------------------------------------------------------
# The join — the DEFAULT BINDING, named and overridable
# ---------------------------------------------------------------------------

#: The minting policy's type: one accepted order in, its trade's id out.
TradeIdMint = Callable[[ProposedOrder], str]


def identity_trade_id(order: ProposedOrder) -> str:
    """**THE DEFAULT BINDING: a trade IS the entry order that opened it.**

    Sound in this system's DECLARED scope and nowhere claimed beyond it:
    CLAUDE.md fixes one strategy per instrument with no ownership ambiguity,
    §4 allows one in-flight action per strategy, §6.1b makes the system
    intraday-only so no position spans a session, and §4's cold start refuses to
    adopt any inherited position. Under those four together, an entry order and
    the trade it opens are in bijection.

    **It is a named default and NOT an identity assumption**, and the difference
    is the whole point of `EntryOrderOrigins` taking it as an argument: the
    architect ruling on how `trade_id` relates to `client_order_id` is owed
    (CHECK-DEBT), and when it lands, a ruling that trades carry their own minted
    identity is a one-line injection here — not an audit of every site that
    happened to write one id where the other was meant.

    Where it would BREAK, stated rather than left to be discovered: a scaling
    order (several entry orders building one position), a position that survives
    a session, or a venue-side amendment that re-issues the order id. Each makes
    the bijection false, and each is out of the declared scope above.
    """
    return order.client_order_id


class EntryOrderOrigins:
    """`TradeOriginPort` over the orders this Limiter approved. In-memory, §12.7.

    Recorded at APPROVAL, which is the moment the association exists and the
    only moment at which all three of `trade_id`, `client_order_id` and
    `strategy_id` are known together — the reason `TradeOrigin` carries the
    strategy rather than leaving a writer to look it up in a table that may have
    moved (§6.4's second-table argument, one layer in).

    Both directions are stored, and the reverse map is not redundant: it is what
    makes a colliding mint detectable AT RECORD TIME rather than as a torn
    position table at publish time.
    """

    def __init__(self, *, mint: TradeIdMint = identity_trade_id) -> None:
        #: The minting policy. INJECTED — see `identity_trade_id`.
        self._mint = mint
        self._by_order: dict[str, TradeOrigin] = {}
        self._by_trade: dict[str, TradeOrigin] = {}
        #: How many origins were recorded. A registry that cannot say what it
        #: holds can only be believed, not measured (`reservations`' argument).
        self.recorded = 0

    def record(self, order: ProposedOrder) -> TradeOrigin:
        """Mint this order's trade id and record the join. Refuses a duplicate."""
        if order.client_order_id in self._by_order:
            raise DuplicateOrigin(
                f"order {order.client_order_id!r} already opened trade "
                f"{self._by_order[order.client_order_id].trade_id!r} — recording "
                "it again would silently re-key a live trade, and §4 mints a "
                "trade_id ONCE at open"
            )
        trade_id = self._mint(order)
        if not isinstance(trade_id, str) or not trade_id:
            raise DuplicateOrigin(
                f"order {order.client_order_id!r}: the injected mint returned "
                f"{trade_id!r}, which is not a usable trade_id — §3 keys the "
                "position table by it and a blank key collides every row"
            )
        clash = self._by_trade.get(trade_id)
        if clash is not None:
            raise DuplicateOrigin(
                f"minting a trade_id for order {order.client_order_id!r} produced "
                f"{trade_id!r}, which order {clash.client_order_id!r} already "
                "holds — §3 keys the position table BY trade_id, and a table with "
                "two rows for one key is not keyed by it"
            )
        origin = TradeOrigin(
            trade_id=trade_id,
            client_order_id=order.client_order_id,
            strategy_id=order.strategy_id,
        )
        self._by_order[origin.client_order_id] = origin
        self._by_trade[origin.trade_id] = origin
        self.recorded += 1
        return origin

    def origin_for_order(self, client_order_id: str) -> TradeOrigin | None:
        """The trade this order opened, or `None`. Never raises (see the port)."""
        return self._by_order.get(client_order_id)

    def origin_for_trade(self, trade_id: str) -> TradeOrigin | None:
        """The order that opened this trade, or `None`. The reverse direction."""
        return self._by_trade.get(trade_id)


# ---------------------------------------------------------------------------
# The stop book, as this module needs to READ it
# ---------------------------------------------------------------------------


@runtime_checkable
class StopLookupPort(Protocol):
    """One verb: the armed stop for an order, or `None`. Reading, never arming.

    Narrower than `seam.StopBookPort` on purpose, and declared HERE rather than
    added to the seam: the seam is at `SEAM_REV 1.1.0` and widening a frozen
    port is an architect ruling, while a consumer declaring the surface it
    actually consumes is ordinary. `nixrisk.stops.StopBook.get` satisfies it as
    shipped, unchanged.

    A read-only surface is also what keeps the two sides of
    `check_origin_write`'s comparison independent: a writer that could arm would
    be comparing a figure against one it produced itself.
    """

    def get(self, client_order_id: str) -> StopState | None:
        """The live stop for one order, or `None` when none is armed."""


# ---------------------------------------------------------------------------
# The origin write
# ---------------------------------------------------------------------------


class WriteDisposition(enum.Enum):
    """What `on_fill` did. A refusal is RAISED, never a member.

    Two members and no third: the fill either moved the published table
    (`PUBLISHED`) or was an exact re-delivery of an execution already held
    (`DUPLICATE`), which §4 makes a no-op. Anything this module refuses leaves
    through an exception, so a caller cannot mistake a refusal for a quiet
    success — the `IngestDisposition` rule, one module over.
    """

    PUBLISHED = "published"
    DUPLICATE = "duplicate"


@dataclasses.dataclass(frozen=True)
class OriginWrite:
    """The result of one `on_fill`: the row, the snapshot it rode, and which."""

    disposition: WriteDisposition
    row: PositionRow
    picture: FinancialPicture
    origin: TradeOrigin

    @property
    def published(self) -> bool:
        """True when this fill moved the published table."""
        return self.disposition is WriteDisposition.PUBLISHED


@dataclasses.dataclass(frozen=True)
class UnstoppedRecord:
    """A fill refused for want of an armed stop — kept so it is not merely lost.

    §14 resolves every uncertainty toward FLAT, and a filled position with no
    stop is one (§12.1: the stop is synthetic and lives in the Limiter). This is
    the record a supervising loop reads to fire the UNCERTAINTY flatten. Nothing
    consumes it yet, and that residual is CHECK-DEBT, not a green.
    """

    client_order_id: str
    trade_id: str
    symbol: str
    filled_qty: int
    ts: float


class PositionOriginWriter:  # pylint: disable=too-many-instance-attributes
    # Eight attributes, and FOUR of them are observables: three counters plus
    # the unstopped record. They exist for the reason `FinancialPictureBook`'s
    # counters do — a writer that cannot say what it published can only be
    # believed, not measured — and `check_origin_write` reads every one of them
    # out of a real drive. The other four are the injected collaborators this
    # class composes and owns none of. The threshold is about behavioural
    # classes accreting STATE; dropping a counter to satisfy it would remove a
    # measurement from the gate's verdict.
    """The Limiter-side component that turns a CONFIRMED FILL into §3's row.

    One job: publish the row that first represents an open position, with
    `stop_distance` taken from the authoritative stop book for that trade, onto
    the SAME versioned snapshot as everything else (§3's atomicity rule, §9's
    sole writer). It owns no table of its own — `FinancialPictureBook` holds the
    position table, `ExecutionLedger` holds the fills, `StopBook` holds the
    stops, and the origin registry holds the join.

    SYNCHRONOUS, for the reason the whole Limiter path is (§5's single-threaded
    loop): an awaitable write would let a second fill be serviced between
    reading the stop book and committing the row it implies.
    """

    def __init__(
        self,
        *,
        picture: FinancialPictureBook,
        ledger: ExecutionLedger,
        stops: StopLookupPort,
        origins: TradeOriginPort,
    ) -> None:
        self._picture = picture
        self._ledger = ledger
        self._stops = stops
        self._origins = origins
        #: Observables. A writer that cannot say what it published can only be
        #: believed, not measured (`FinancialPictureBook`'s own argument).
        self.writes = 0
        self.duplicates = 0
        self.refusals = 0
        self._unstopped: list[UnstoppedRecord] = []

    # -- the event surface --------------------------------------------------

    def on_fill(
        self, report: ExecutionReport, *, sum_reservations: float | None = None
    ) -> OriginWrite:
        """One confirmed fill -> one published §3 row. Refuses, loudly, or writes.

        `sum_reservations` is a PASS-THROUGH to `commit()` so a caller that has
        just released this order's reservation (§3's lifecycle: released ON FILL,
        converting to open margin) lands both changes under ONE version stamp.
        Left `None` the previous figure carries forward — see the module
        docstring for why that is conservative and still owed.
        """
        origin = self._origins.origin_for_order(report.order_id)
        if origin is None:
            self.refusals += 1
            raise UnknownTrade(
                f"fill {report.order_id}/{report.exec_id} in {report.symbol!r}: no "
                "TradeOrigin is recorded for this order, so there is no trade_id "
                "to key §3's position row by. The trade<->order join is an "
                "INJECTED surface (seam.TradeOriginPort) and it has no record of "
                "this order opening a trade — refusing rather than minting one "
                "here, which would publish a position no approval and no strategy "
                "feedback path knows about (§4)"
            )
        outcome = self._ledger.ingest(report)
        stop = self._stops.get(origin.client_order_id)
        if stop is None:
            self._refuse_unstopped(report, origin)
        distance = stop.initial_distance_ticks
        row = self._row(report, origin, distance)
        if not outcome.applied:
            self.duplicates += 1
            return OriginWrite(
                disposition=WriteDisposition.DUPLICATE,
                row=row,
                picture=self._picture.current(),
                origin=origin,
            )
        picture = self._picture.commit(
            positions=self._merged(row), sum_reservations=sum_reservations
        )
        self.writes += 1
        return OriginWrite(
            disposition=WriteDisposition.PUBLISHED,
            row=row,
            picture=picture,
            origin=origin,
        )

    def unstopped(self) -> tuple[UnstoppedRecord, ...]:
        """Fills refused for want of an armed stop, in arrival order.

        The escalation surface: §14 says an unprotected position resolves toward
        FLAT, this module may not fire a flatten (§14 makes execution
        Limiter-only and `nixrisk.flatten` owns it), so the condition is recorded
        where a supervising loop can act on it instead of vanishing into a log.
        """
        return tuple(self._unstopped)

    # -- internals ----------------------------------------------------------

    def _refuse_unstopped(
        self, report: ExecutionReport, origin: TradeOrigin
    ) -> NoReturn:
        """Record and RAISE. Never returns — the caller has no fallback path."""
        self.refusals += 1
        self._unstopped.append(
            UnstoppedRecord(
                client_order_id=origin.client_order_id,
                trade_id=origin.trade_id,
                symbol=report.symbol,
                filled_qty=report.filled_qty,
                ts=report.ts,
            )
        )
        raise UnstoppedFill(
            f"fill {report.order_id}/{report.exec_id} confirmed {report.filled_qty} "
            f"{report.symbol} for trade {origin.trade_id!r} (order "
            f"{origin.client_order_id!r}) but the stop book has NO ARMED STOP for "
            "it, so this writer has no stop distance to publish. Refusing to "
            "publish the row: §7:501 prices bucket exposure from that distance, "
            "so a defaulted or zero value would price a real position at zero "
            "dollar risk, make the correlation bucket read emptier than it is and "
            "ADMIT MORE (D3.136's fail-open under a new spelling). The fill is "
            "already booked in the execution ledger — §4 makes it a fact, not a "
            "negotiation — and this position is UNPROTECTED (§4, §12.1), so §14 "
            "resolves it toward FLAT: see unstopped() and fire the UNCERTAINTY "
            "flatten"
        )

    def _row(
        self, report: ExecutionReport, origin: TradeOrigin, distance: int
    ) -> PositionRow:
        """§3's row for this trade, every field from the authority that owns it."""
        filled = self._ledger.order_cumulative(report.order_id)
        size = report.side.sign * filled
        margin_per_contract = self._picture.current().margin_per_contract.get(
            report.symbol
        )
        if margin_per_contract is None:
            self.refusals += 1
            raise UntradableSymbol(
                f"fill {report.order_id}/{report.exec_id}: symbol "
                f"{report.symbol!r} is absent from the published margin field set, "
                "so this row's margin has no scale — §4:198 makes such a symbol "
                "NOT-TRADABLE and a guessed figure would enter `committed`, which "
                "every §3 Phase-B capital rule is evaluated against"
            )
        return PositionRow(
            trade_id=origin.trade_id,
            symbol=report.symbol,
            strategy_id=origin.strategy_id,
            size=size,
            margin=abs(size) * margin_per_contract,
            state=PositionState.OPEN,
            # THE ORIGIN WRITE. `StopState.initial_distance_ticks`, which
            # `StopBook.arm` recorded from `ProposedOrder.stop_ticks` — the
            # sizer's own distance (§7:476). Never a literal, never a default,
            # never re-derived from the fill.
            stop_distance=distance,
        )

    def _merged(self, row: PositionRow) -> tuple[PositionRow, ...]:
        """The position table with `row` in it: replaced in place, or appended.

        Replaced RATHER THAN appended when the trade is already published, and
        in its existing slot: §3's table is keyed by `trade_id`, so a second row
        for one key is the duplicate `picture_defects` refuses a whole snapshot
        for. A later partial fill of the same order therefore UPDATES the row it
        already wrote (§4's partial-fill rule: position = actual filled qty).
        """
        current = self._picture.current().positions
        if any(existing.trade_id == row.trade_id for existing in current):
            return tuple(
                row if existing.trade_id == row.trade_id else existing
                for existing in current
            )
        return (*current, row)
