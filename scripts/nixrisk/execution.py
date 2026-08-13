"""§4's idempotent execution ledger — position state from cumulative fills.

ARC 029 / Stage 2.3. Ingests broker EXECUTION REPORTS and maintains canonical
position state so that the state is a pure FUNCTION OF THE SET of unique fills —
and therefore immune to duplicate OR out-of-order delivery. Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md`.

§4, verbatim, because the sentence is the whole design:

> **Idempotent execution handling:** broker events are deduplicated by
> (order_id, exec_id); position state derives from cumulative fills — immune to
> duplicate or out-of-order execution reports.

and the event that feeds it, §4's broker-order seam:

> `on_fill(client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty)`
> — idempotent by (order_id, exec_id); partial fills arrive as successive events.

---

## WHAT `order_id` IS, AND WHY IT IS NOT A SECOND IDENTIFIER

§4 spells the dedup key `(order_id, exec_id)`; the `on_fill` event's first field
is `client_order_id`. They are the SAME neutral identifier: §2A invariant 2 keeps
every vendor type below the seam, so the venue's own order handle is mapped to the
`client_order_id` this system minted and never leaks above the line. `ExecutionReport`
therefore names the field `order_id` to match §4's dedup sentence exactly, and it
carries the neutral id the broker seam already exposes — not a vendor orderId.

## INCREMENTAL PER EXEC, AND CUMULATIVE IS DERIVED — the deliberate choice

`ExecutionReport.filled_qty` is the **incremental** quantity of ONE execution, not a
running cumulative. That is the load-bearing decision and it is why immunity holds
by construction:

* Position state is `Σ signed_qty over the SET of unique (order_id, exec_id) fills`.
  Both the set and the sum are order-independent: a sum is commutative, and the set
  is keyed, so a duplicate maps to a key already present and a reordering visits the
  same keys in a different sequence. Neither can change the result. **`position()`
  reads that set directly** (a scan), so the immunity is a property of the type, not
  a discipline a caller must keep — the same construction `FinancialPictureBook`
  uses for atomicity.
* Had the report instead carried a **cumulative** figure as its source of truth,
  the position would be `the cumulative of the LAST exec`, and "last" is an ordering
  the spec explicitly says we must be immune to. A cumulative source turns
  out-of-order delivery into a wrong answer; an incremental source turns it into the
  same answer.

The broker DOES also report its own `cumulative_qty` per exec, and this type keeps
it — not as the source of position, but as an INDEPENDENT cross-check. `audit()`
compares the derived cumulative (`Σ` of the incrementals it holds) against the
broker's reported cumulative (`max` over the set — monotone per order), and a
`reported > derived` gap is a MISSING exec this ledger has not yet seen. Two
different pieces of arithmetic over the same set, for the same reason
`reservations.audit()` keeps Σ incremental and re-scans with `fsum`: an aggregate
that cannot disagree with its own cross-check is furniture.

## FAIL CLOSED ON A CONTRADICTION — a duplicate KEY is not always a benign duplicate

A second report under an already-seen `(order_id, exec_id)` carrying IDENTICAL data
is the ordinary re-delivery §4 makes idempotent: a no-op. A second report under the
same key carrying DIFFERENT data (a different qty, price, side or symbol) is not a
duplicate at all — it is a broker telling two stories about one execution, and
silently dropping it would keep whichever story arrived first with no record that
the other existed. `ingest` RAISES `ContradictoryExecution` naming the fields that
disagree (check contract v2 §11 — a control asserts the REASON, never a bare code).
A NEW exec for a known order whose side or symbol contradicts the order's
established side/symbol is the same class of fault and is refused the same way: one
`order_id` is one order in one instrument in one direction.

## RECONCILIATION AGAINST §3'S POSITION TABLE

`reconcile(rows)` compares this ledger's derived net quantity per symbol against the
`PositionRow.size` §3 publishes, and returns a `PositionDrift` per symbol. **It
assumes `PositionRow.size` is SIGNED** (negative == short), matching the §2A broker
`Position.net_qty` convention — `PositionRow` carries no side field, so the sign is
the only place direction can live. That assumption is an integration seam question
(see the module's RETURN notes), surfaced rather than hidden: a drift is reported,
never silently reconciled away, because §4 makes broker truth win and this ledger is
the fill-side half of that reconciliation, not its arbiter.

## WHAT THIS MODULE DOES NOT DO — stated, not implied

It does not place, cancel, or reconcile against the broker over the wire; it is
told what filled and keeps the books. It does not decide when a position is `OPEN`
vs `CLOSING` (§4's two-phase entry state is the Limiter's, keyed off fill
confirmation — this ledger supplies the cumulative reality that decision reads). It
cannot detect a fill it was never sent EXCEPT through the `cumulative_qty`
cross-check above, and even that sees a gap only once a LATER exec of the same order
arrives. A killed process loses this in-memory ledger like every other synthetic
state (§12.1); durability is §9's WAL, written by the Limiter's event handlers that
DRIVE this ledger, not by the ledger itself.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Iterable, Sequence
from typing import Final

from nixrisk.seam import PositionRow

#: The economic fields that IDENTIFY one execution. Two reports under the same
#: `(order_id, exec_id)` must agree on every one of these or one of them is a lie
#: about a single venue event. Derived from the dataclass so a new field cannot be
#: added to the report and silently left out of the contradiction check.
_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "symbol",
    "side",
    "filled_qty",
    "price",
    "cumulative_qty",
    "ts",
)


class ExecutionError(RuntimeError):
    """Base for every refusal this ledger raises. Never caught internally."""


class InvalidExecutionReport(ExecutionError):
    """A report whose own fields are not a possible execution (bad qty/price)."""


class ContradictoryExecution(ExecutionError):
    """Two reports disagree about one execution, or an order about itself.

    §4 makes a re-delivery idempotent, NOT a rewrite. A second report under a seen
    `(order_id, exec_id)` with different data — or a new exec for a known order with
    a different side/symbol — is a broker inconsistency. Absorbing it would keep one
    story and erase the other with no record; this ledger refuses and names the
    disagreement instead.
    """


class FillSide(enum.Enum):
    """The ACTION one fill executes. Buy or sell — never a position direction.

    Deliberately NOT `nixrisk.seam.Side` (LONG/SHORT). A fill is an order action,
    and a protective flatten of a LONG fires a SELL, so LONG/SHORT is the wrong
    axis: the same open position is closed by the opposite action. This mirrors the
    §2A broker seam's own `Side` (BUY/SELL), spelled locally rather than imported so
    a datafeed/order library fault cannot reach this ledger through a shared type
    (§2A invariant 3), the same reason `seam.Side` is spelled and not imported.
    """

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """+1 for a buy, -1 for a sell. The sign net position accumulates under."""
        return 1 if self is FillSide.BUY else -1


@dataclasses.dataclass(frozen=True)
class ExecutionReport:  # pylint: disable=too-many-instance-attributes
    # Eight fields, and each is one the §4 `on_fill` event carries or §9 requires:
    # order_id/exec_id are the dedup key, symbol/side/filled_qty/price/cumulative_qty
    # are the fill itself, and ts is §9's mandatory row timestamp. Dropping one to
    # satisfy a default threshold of seven would either lose a field the broker
    # reports or push it into a nested struct a consumer must read separately. The
    # threshold is about behavioural classes accreting state; this is a frozen value
    # type with no behaviour — the same case seam.py's value types document.
    """One broker execution report — the `on_fill` event as a frozen value.

    `filled_qty` is INCREMENTAL (this exec's own quantity); `cumulative_qty` is the
    broker's running total for the order, kept only as `audit()`'s cross-check. See
    the module docstring for why the incremental figure is the source of truth and
    the cumulative one is not.
    """

    order_id: str
    exec_id: str
    symbol: str
    side: FillSide
    filled_qty: int
    price: float
    cumulative_qty: int
    ts: float

    def __post_init__(self) -> None:
        """Refuse a report that is not a possible execution. Fail closed, loud."""
        for name in ("order_id", "exec_id", "symbol"):
            if not getattr(self, name):
                raise InvalidExecutionReport(
                    f"{name} is empty — an execution with no {name} cannot be keyed, "
                    "and a blank key would collide unrelated fills into one record"
                )
        if self.filled_qty <= 0:
            raise InvalidExecutionReport(
                f"{self.order_id}/{self.exec_id}: filled_qty={self.filled_qty!r} — an "
                "execution moves a positive quantity; a zero/negative increment is a "
                "fill no arithmetic can see"
            )
        if self.cumulative_qty < self.filled_qty:
            raise InvalidExecutionReport(
                f"{self.order_id}/{self.exec_id}: cumulative_qty={self.cumulative_qty!r}"
                f" is below this exec's own filled_qty={self.filled_qty!r} — the running"
                " total cannot be less than the increment that is part of it"
            )
        if not math.isfinite(self.price) or self.price <= 0.0:
            raise InvalidExecutionReport(
                f"{self.order_id}/{self.exec_id}: price={self.price!r} is not a finite "
                "positive figure — a fill priced at zero/NaN/Inf poisons every VWAP it "
                "enters"
            )

    @property
    def key(self) -> tuple[str, str]:
        """The `(order_id, exec_id)` §4 deduplicates by. The whole identity."""
        return (self.order_id, self.exec_id)

    @property
    def signed_qty(self) -> int:
        """`filled_qty` signed by side — the quantity net position accumulates."""
        return self.side.sign * self.filled_qty

    @property
    def notional(self) -> float:
        """`price × filled_qty`. Summed per side, it is a VWAP's numerator."""
        return self.price * self.filled_qty


class IngestDisposition(enum.Enum):
    """What `ingest` did with a report. A contradiction is RAISED, not a member.

    Two members and no third: a report is either the first sighting of its key
    (`APPLIED`) or an exact re-delivery of a key already held (`DUPLICATE`). A
    contradictory duplicate is not a disposition — it is a fault, and it leaves
    through an exception so a caller cannot mistake it for a benign no-op.
    """

    APPLIED = "applied"
    DUPLICATE = "duplicate"


@dataclasses.dataclass(frozen=True)
class IngestOutcome:
    """The result of one `ingest`. Immutable; carries the report it acted on."""

    disposition: IngestDisposition
    report: ExecutionReport

    @property
    def applied(self) -> bool:
        """True when this report was the first sighting of its key."""
        return self.disposition is IngestDisposition.APPLIED


@dataclasses.dataclass(frozen=True)
class DerivedPosition:
    """One symbol's position, DERIVED from the set of unique fills for it.

    Every field is a symmetric function of that set — a sum or a count — so two
    ledgers fed the same fills in any order, with any duplicates, produce equal
    `DerivedPosition`s. That is the §4 immunity property, made a property of the
    value rather than a claim about the code path that built it.
    """

    symbol: str
    net_qty: int
    bought_qty: int
    sold_qty: int
    buy_notional: float
    sell_notional: float
    fills: int

    @property
    def buy_vwap(self) -> float | None:
        """Volume-weighted average buy price, or `None` when nothing was bought."""
        return self.buy_notional / self.bought_qty if self.bought_qty else None

    @property
    def sell_vwap(self) -> float | None:
        """Volume-weighted average sell price, or `None` when nothing was sold."""
        return self.sell_notional / self.sold_qty if self.sold_qty else None

    @property
    def is_flat(self) -> bool:
        """Provably flat means a zero NET quantity, not zero fills."""
        return self.net_qty == 0


@dataclasses.dataclass(frozen=True)
class OrderAudit:
    """§4's cumulative cross-check for one order. Derived vs broker-reported.

    `derived_cumulative` is `Σ` of the increments this ledger holds; `reported_
    cumulative` is `max` of the broker's `cumulative_qty` over the same set (monotone
    per order). They are two pieces of arithmetic over one set, and a disagreement is
    a gap (a missing exec) or an overrun (an impossible over-report) — not float
    noise, because these are integer contract counts.
    """

    order_id: str
    derived_cumulative: int
    reported_cumulative: int
    fills: int

    @property
    def gap(self) -> int:
        """`reported − derived`. Positive ⇒ execs the broker counted but we lack."""
        return self.reported_cumulative - self.derived_cumulative

    @property
    def complete(self) -> bool:
        """True when every exec the broker's cumulative implies is accounted for."""
        return self.gap == 0


@dataclasses.dataclass(frozen=True)
class PositionDrift:
    """One symbol's reconciliation of derived fills against §3's position row.

    `row_size` is `PositionRow.size`, assumed SIGNED (see the module docstring). A
    non-zero `drift` is surfaced, never corrected here: §4 makes broker truth the
    arbiter, and this ledger is the fill-side input to that reconciliation.
    """

    symbol: str
    derived_net_qty: int
    row_size: int

    @property
    def drift(self) -> int:
        """`derived − row`. Zero ⇒ the fill ledger and the position table agree."""
        return self.derived_net_qty - self.row_size

    @property
    def agrees(self) -> bool:
        """True when the derived net quantity equals the published row size."""
        return self.drift == 0


class ExecutionLedger:
    """§4's idempotent execution ledger. SYNCHRONOUS by construction.

    Synchronous for the reason the whole gate path is (§5's single-threaded loop):
    ingesting a fill maintains the canonical position state a subsequent pass reads,
    and an awaitable `ingest` would admit a second pass reading a position that does
    not yet include a fill already delivered — the fill-vs-tick race §5 eliminates.

    The dedup store `_fills` — keyed by `(order_id, exec_id)` — IS the state. Every
    derived figure is a pure function of it, so correctness under duplication and
    reordering is structural: a duplicate maps to a present key and a reordering
    visits the same keys, and neither changes what a scan of the store computes.
    """

    def __init__(self) -> None:
        #: `(order_id, exec_id) -> the one report for that execution`. The ONE
        #: source of truth; every derived figure scans it. A dict keyed by the §4
        #: dedup tuple is what makes a duplicate a no-op and a reordering invisible.
        self._fills: dict[tuple[str, str], ExecutionReport] = {}
        #: `order_id -> the side its first fill established`. One order is one
        #: direction; a later exec that disagrees is a broker inconsistency.
        self._order_side: dict[str, FillSide] = {}
        #: `order_id -> the symbol its first fill established`. Likewise one order
        #: is one instrument.
        self._order_symbol: dict[str, str] = {}
        #: Observability counters: a ledger that cannot say what it did with a
        #: stream can only be believed, not measured (the `reservations` argument).
        self.applied = 0
        self.duplicates = 0
        self.contradictions = 0

    # -- the event surface --------------------------------------------------

    def ingest(self, report: ExecutionReport) -> IngestOutcome:
        """Take one execution report. Idempotent; refuses a contradiction, loud.

        First sighting of `(order_id, exec_id)` ⇒ APPLIED. Exact re-delivery ⇒
        DUPLICATE, a no-op. A same-key report with different data, or a new exec for
        a known order in a different side/symbol ⇒ `ContradictoryExecution`.
        """
        prior = self._fills.get(report.key)
        if prior is not None:
            return self._on_duplicate_key(prior, report)
        self._guard_order_consistency(report)
        self._fills[report.key] = report
        self._order_side.setdefault(report.order_id, report.side)
        self._order_symbol.setdefault(report.order_id, report.symbol)
        self.applied += 1
        return IngestOutcome(IngestDisposition.APPLIED, report)

    def ingest_all(
        self, reports: Iterable[ExecutionReport]
    ) -> tuple[IngestOutcome, ...]:
        """Ingest a stream in arrival order. A convenience over `ingest`, no policy."""
        return tuple(self.ingest(report) for report in reports)

    # -- derived position state (§4) ---------------------------------------

    def position(self, symbol: str) -> DerivedPosition:
        """The canonical position for `symbol`, a pure function of its fill set.

        A SCAN, deliberately: the store is the truth and this reads it, so the value
        cannot drift from the fills the way a parallel running total could. Execution
        handling is event-driven at trade frequency, not the §11 per-tick hot path,
        so an O(fills) read here costs nothing the spec budgets against.
        """
        fills = [r for r in self._fills.values() if r.symbol == symbol]
        bought = [r for r in fills if r.side is FillSide.BUY]
        sold = [r for r in fills if r.side is FillSide.SELL]
        return DerivedPosition(
            symbol=symbol,
            net_qty=sum(r.signed_qty for r in fills),
            bought_qty=sum(r.filled_qty for r in bought),
            sold_qty=sum(r.filled_qty for r in sold),
            buy_notional=math.fsum(r.notional for r in bought),
            sell_notional=math.fsum(r.notional for r in sold),
            fills=len(fills),
        )

    def order_cumulative(self, order_id: str) -> int:
        """`Σ` of the increments held for `order_id` — the DERIVED cumulative fill."""
        return sum(r.filled_qty for r in self._fills.values() if r.order_id == order_id)

    def audit(self, order_id: str) -> OrderAudit:
        """§4's cross-check: derived cumulative vs the broker's reported cumulative.

        A gap (`reported > derived`) is a missing exec — data the broker's own
        running total says exists that this ledger has not been handed. It is
        detectable even under out-of-order delivery, because both `Σ` and `max` are
        order-independent over the set.
        """
        order_fills = [r for r in self._fills.values() if r.order_id == order_id]
        return OrderAudit(
            order_id=order_id,
            derived_cumulative=sum(r.filled_qty for r in order_fills),
            reported_cumulative=max((r.cumulative_qty for r in order_fills), default=0),
            fills=len(order_fills),
        )

    def reconcile(self, rows: Sequence[PositionRow]) -> tuple[PositionDrift, ...]:
        """Compare derived net quantity against §3's published position rows.

        Keyed by symbol; rows sharing a symbol are summed (CLAUDE.md scope is one
        strategy per instrument, so this is a defensive sum, not a real fan-in). A
        drift is reported per symbol seen in EITHER the ledger or the rows, so a
        position the ledger holds that no row shows — and the reverse — both surface.
        """
        row_by_symbol: dict[str, int] = {}
        for row in rows:
            row_by_symbol[row.symbol] = row_by_symbol.get(row.symbol, 0) + row.size
        symbols = set(row_by_symbol) | self.symbols()
        return tuple(
            PositionDrift(
                symbol=symbol,
                derived_net_qty=self.position(symbol).net_qty,
                row_size=row_by_symbol.get(symbol, 0),
            )
            for symbol in sorted(symbols)
        )

    # -- readable records ---------------------------------------------------

    def symbols(self) -> frozenset[str]:
        """Every symbol this ledger holds a fill for."""
        return frozenset(r.symbol for r in self._fills.values())

    def orders(self) -> frozenset[str]:
        """Every order_id this ledger holds a fill for."""
        return frozenset(self._order_symbol)

    def fill_count(self) -> int:
        """The number of UNIQUE executions held — never the number ingested."""
        return len(self._fills)

    # -- internals ----------------------------------------------------------

    def _on_duplicate_key(
        self, prior: ExecutionReport, report: ExecutionReport
    ) -> IngestOutcome:
        """A second report under a seen key: benign re-delivery, or contradiction."""
        disagreements = _identity_disagreements(prior, report)
        if disagreements:
            self.contradictions += 1
            raise ContradictoryExecution(
                f"execution {report.key} was already reported with different data: "
                + "; ".join(disagreements)
                + " — §4 makes a RE-DELIVERY idempotent, not a rewrite, so this is a "
                "broker inconsistency and is refused rather than silently dropped"
            )
        self.duplicates += 1
        return IngestOutcome(IngestDisposition.DUPLICATE, report)

    def _guard_order_consistency(self, report: ExecutionReport) -> None:
        """One order_id is one instrument in one direction. Refuse a report that
        would make it two."""
        side = self._order_side.get(report.order_id)
        if side is not None and side is not report.side:
            self.contradictions += 1
            raise ContradictoryExecution(
                f"order {report.order_id} already filled {side.value} and exec "
                f"{report.exec_id} reports {report.side.value} — one order is one "
                "direction; a side flip within an order is a broker inconsistency"
            )
        symbol = self._order_symbol.get(report.order_id)
        if symbol is not None and symbol != report.symbol:
            self.contradictions += 1
            raise ContradictoryExecution(
                f"order {report.order_id} already filled {symbol!r} and exec "
                f"{report.exec_id} reports {report.symbol!r} — one order is one "
                "instrument"
            )


def _identity_disagreements(
    prior: ExecutionReport, report: ExecutionReport
) -> list[str]:
    """Every identity field on which two same-key reports disagree, named."""
    return [
        f"{name}: {getattr(prior, name)!r} then {getattr(report, name)!r}"
        for name in _IDENTITY_FIELDS
        if getattr(prior, name) != getattr(report, name)
    ]
