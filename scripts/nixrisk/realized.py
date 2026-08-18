"""§6.6's realized P&L for ONE closed trade — the figure §9's record did not carry.

ARC 037 / sub-agent A (D3.220, the keystone). Built against SEAM (a) as frozen in
`downloads/ARC037-SEAM-FREEZE.md`. Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md` unless another document is named.

------------------------------------------------------------------------------
THE WIRE THAT WAS NOT THERE
------------------------------------------------------------------------------
`scripts/nixscore/ema.py` (ARC 036) computes §6.6's realized-P&L EMA and reads
its input from `plane1_event_log.payload` under the key `realized_pnl`. Its own
docstring records, measured, that **nothing in this tree wrote that key**: the
one realized-P&L hand-off that existed was `flatten.ScoringSink.book_realized`,
an ACCOUNT-LEVEL balance delta over a set of closed trades. §6.6:448 locks the
canonical key as `(strategy_id, symbol)`, and an account delta cannot be
attributed to a pair — two trades closing in the same reconcile produce one
number, and no arithmetic recovers which pair earned which part of it. So the
Scoring engine read a figure the durable record did not carry, and every gate
over it was green because a scorer with no input and a scorer with a cold start
look identical.

This module is the arithmetic half of closing that wire. `nixrisk.flatten` is
the writing half (the Limiter, §9's SOLE writer — no new writer, no new port,
no new daemon), and the figure rides the `closed` / `protective_exit` rows the
Limiter already books, which is §12.10:768's own pattern: *"the final trail
level rides the `closed` row."*

------------------------------------------------------------------------------
THE FORMULA, AND WHY EVERY COST TERM IS IN IT
------------------------------------------------------------------------------
    realized = direction × (exit_price − entry_price) × qty × point_value
             − commission_in − commission_out − fees − slippage_cost

* **§6.5:409-410** makes the modelled costs part of the realized figure by name:
  the sizing denominator *"changes on fills **and commissions/fees**, which debit
  on close."* A gross figure would rank a strategy on money it never kept.
* **§7:481's slippage pad** is the same argument on the other side: *"`risk_$`
  is honest only if sized against stop + expected slippage."* A realized figure
  that ignores the slippage the sizer already priced would rank strategies on a
  fill nobody got.
* `point_value` is the contract's $/point (§7: *"fixed $/point per symbol"*).
  It is a FACT ABOUT THE INSTRUMENT supplied by the caller, never a literal
  here — `sizing.py` states the same rule for `tick_value` and this module has
  no more right to carve a symbol constant than it does.

**One `qty`, and it is the entry's.** This module prices a FULL round trip: the
quantity that went on is the quantity that came off. A partial scale-out would
need the entry commission attributed across legs, and that attribution is a
decision about the trade's book rather than arithmetic over one close — it is
recorded as CHECK-DEBT rather than guessed at here. `nixrisk.flatten` closes
whole trades (`CloseTarget` is one `trade_id`), so nothing in this tree needs
the split today.

------------------------------------------------------------------------------
FAIL CLOSED AND LOUD — THERE IS NO SILENT ZERO ANYWHERE ON THIS PATH
------------------------------------------------------------------------------
Every refusal here exists because of one paragraph in `nixscore/ema.py`: an
absent realized figure treated as a zero advance *"would score every pair 0.0,
tie every comparison, and make a totally blind engine indistinguishable from a
healthy cold start."* The same trap has a writer-side spelling — a writer that
emits `0.0` when it cannot compute a figure is worse than one that emits
nothing, because the reader's own refusal (`MissingRealized`) can no longer
fire. So:

* a missing, non-numeric, NaN or infinite input RAISES, naming the field;
* a qty or a point value that is not positive RAISES — those are not a small
  trade, they are a trade the record cannot describe;
* `realized_fields` emits the key or it does not emit it. It never emits a
  placeholder value. The writer's non-emission is visible in the record (see
  `flatten._realizing_fields`, which books a `realized_status` naming WHY) and
  is refused by name at the reader.

------------------------------------------------------------------------------
THE OPEN MARK CANNOT REACH THE ARITHMETIC, AND `peak_price` IS THE PROOF
------------------------------------------------------------------------------
§6.6:435: *"Realized P&L only — closed trades. Unrealized/paper gains never
steer capital (a green open position can reverse before it closes)."*

`TradeFacts` deliberately CARRIES `peak_price` — the best mark seen while the
position was open — and `realized_pnl` deliberately does not take a `TradeFacts`
at all: it takes the entry and the exit, and there is no parameter through which
a mark could arrive. Carrying the peak is what makes the ban MEASURABLE: a
`check_realized_pnl` arm drives a trade that goes green while open and closes
red, and requires the written figure to be the NEGATIVE close and never the
positive peak. A module that simply never mentioned a peak could not be shown to
be ignoring one.

`BANNED_UNREALIZED_FIELDS` is the field-name half of the same ban, and this
module states it so a WRITER can be checked against it without the Limiter
importing the scorer. That is a deliberate restatement of a constant that also
lives in `nixscore.ema`, and it is directive 3's one honest exception: the
alternative is `nixrisk` (the safety spine, the exit path) importing `nixscore`
(the ranking optimisation), so a scorer that failed to import would stop a
protective flatten from booking its row. The restatement is not left to
convention — `check_realized_pnl` and `scripts/tests/test_realized_pnl.py` both
assert BYTE EQUALITY with `nixscore.ema`'s constants in both directions, so a
rename on either side is a loud red rather than a wire that silently parts.

------------------------------------------------------------------------------
WHY THE PAYLOAD VALUE IS TEXT
------------------------------------------------------------------------------
`nixrisk.seam.EventRow.fields` is `Mapping[str, str]` and the seam is FROZEN.
Widening it to carry a float is a wire-schema change (`SEAM_REV` / `WIRE_SCHEMA`)
for one field, and this module refuses to make one. `repr(float)` is Python's
shortest round-tripping representation, so `float(repr(x)) == x` exactly — the
value survives the JSONB payload without loss, and `ema._realized_amount`
already accepts `str` and floats it. `test_realized_pnl.py` drives the
round-trip on the worst representable cases rather than asserting it.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO
------------------------------------------------------------------------------
* It does not know when a trade closed, what filled, or at what price. It is
  pure over facts a caller supplies — the same separation `nixscore.ema` makes,
  for the same reason: the arithmetic is drivable without a broker and without
  Postgres.
* It does not write. `nixrisk.flatten` writes, through the one `Plane1Port`.
* It does not SOURCE the facts. `RecordedTradeFacts` is a book a caller fills;
  **no production code path fills one**, because this tree has no fill feed —
  `EventKind` still has no `filled` member and `nixrisk.execution`'s ledger is
  not wired to a broker. That gap is recorded (CHECK-DEBT) and is why a
  realizing row whose facts are absent books a `realized_status` instead of a
  number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from nixrisk.seam import Side

#: The `plane1_event_log.payload` key the figure lands under. Byte-identical to
#: `nixscore.ema.REALIZED_FIELD`, asserted equal by gate and suite (above).
REALIZED_FIELD: Final[str] = "realized_pnl"

#: The payload key §6.6's pair-half rides under. `plane1_sink._values_clause`
#: also lifts it into the row's own `symbol` COLUMN, so the pair is readable
#: from the row without opening the JSONB.
SYMBOL_FIELD: Final[str] = "symbol"

#: The key a realizing row carries INSTEAD of a figure when no figure could be
#: computed. It names WHY in the durable record; it is never a number and never
#: a zero, so a reader cannot mistake it for a realization.
STATUS_FIELD: Final[str] = "realized_status"

#: Payload keys that name an OPEN mark. Byte-identical to
#: `nixscore.ema.BANNED_UNREALIZED_FIELDS`; see the module docstring for why the
#: constant is restated here rather than imported across the package boundary.
BANNED_UNREALIZED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "unrealized_pnl",
        "unrealized",
        "open_pnl",
        "mark_to_market",
        "mtm",
        "paper_pnl",
        "floating_pnl",
    }
)

#: §6.6:435's sign convention, as data. `+1` for a long (price up is profit),
#: `-1` for a short. Spelled as a mapping over the frozen `Side` so a member
#: added to the seam is a `KeyError` at the one site that reads it, rather than
#: an `if/else` that silently treats every non-LONG as a short.
_DIRECTION: Final[dict[Side, float]] = {Side.LONG: 1.0, Side.SHORT: -1.0}


class RealizedError(RuntimeError):
    """A realized figure that cannot be computed. NEVER degraded to a zero."""


class MissingTradeFact(RealizedError):
    """An input the formula needs is absent or unreadable. Named, not defaulted."""


class ImpossibleTradeFact(RealizedError):
    """An input that is present but cannot describe a real trade (qty <= 0)."""


def _finite(value: object, field_name: str, where: str) -> float:
    """One numeric fact, or a refusal naming the field and the trade.

    `bool` is rejected explicitly: `True` is an `int` in Python and `1.0` is a
    plausible-looking price, so a flag that reached a money field would compute
    a wrong number quietly rather than raise.
    """
    if value is None:
        raise MissingTradeFact(
            f"{where}: {field_name} is absent. §6.5:409-410 makes the realized "
            "figure net of commissions and fees, so an absent cost term is not a "
            "zero cost — it is an unknown one, and a scorer cannot tell the "
            "difference once it is written down"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissingTradeFact(
            f"{where}: {field_name}={value!r} is not a number ({type(value).__name__})"
        )
    number = float(value)
    if not math.isfinite(number):
        raise MissingTradeFact(
            f"{where}: {field_name}={value!r} is not finite. A NaN would "
            "propagate through the EMA and make every later score NaN, and a "
            "NaN ranking compares False against everything"
        )
    return number


@dataclass(frozen=True)
class TradeEntry:  # pylint: disable=too-many-instance-attributes
    # Eight fields, and each is one term of the frozen SEAM (a) formula or one
    # half of §6.6:448's key. Trimming one would move a term of a money figure
    # into a nested struct the caller must assemble separately — which is where
    # a missing cost hides. The threshold is about behavioural classes
    # accreting state; this is a frozen record with no behaviour.
    """What the trade cost to put on. One instrument, one direction (§2A/§4)."""

    trade_id: str
    strategy_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    #: The contract's $/point (§7). A FACT ABOUT THE INSTRUMENT, supplied by the
    #: caller — never a literal in this module (`sizing.py`'s rule for
    #: `tick_value`, and the same reason: a carved symbol constant is wrong for
    #: every symbol it was not carved for).
    point_value: float
    #: Entry commission, in dollars, for the whole `qty`.
    commission: float


@dataclass(frozen=True)
class TradeExit:
    """What came off, and what the exit itself cost. The EXIT FILL, not a mark."""

    trade_id: str
    price: float
    commission: float
    fees: float
    #: §7:481's slippage, priced in DOLLARS for this fill. The sizer already
    #: charges the pad against the risk budget; a realized figure that ignored
    #: it would rank strategies on a fill nobody got.
    slippage_cost: float


@dataclass(frozen=True)
class TradeFacts:
    """One closed round trip: the entry, the exit, and the mark that is IGNORED.

    `peak_price` is the best mark seen while the position was open. It is
    carried and RECORDED and it never reaches `realized_pnl`, which takes the
    entry and the exit and has no parameter a mark could arrive through. See
    the module docstring: carrying it is what makes the §6.6:435 ban
    measurable rather than merely absent.
    """

    entry: TradeEntry
    exit: TradeExit
    peak_price: float | None = None

    @property
    def trade_id(self) -> str:
        """The trade both halves must agree about."""
        return self.entry.trade_id


@dataclass(frozen=True)
class RealizedPnl:  # pylint: disable=too-many-instance-attributes
    # Ten fields BY DESIGN: the pair, the trade, the quantity, and every term
    # of the arithmetic. A result that carried only `net` would make a wrong
    # figure unattributable to the term that produced it, which is the whole
    # value of `key_facts` in a gate's evidence.
    """The figure and every term that produced it. `net` is what §6.6 ranks."""

    trade_id: str
    strategy_id: str
    symbol: str
    qty: int
    gross: float
    commission_in: float
    commission_out: float
    fees: float
    slippage_cost: float
    net: float

    @property
    def key(self) -> tuple[str, str]:
        """§6.6:448's locked canonical key: `(strategy_id, symbol)`."""
        return (self.strategy_id, self.symbol)

    @property
    def costs(self) -> float:
        """Everything §6.5:409-410 debits on close. `gross - costs == net`."""
        return self.commission_in + self.commission_out + self.fees + self.slippage_cost

    @property
    def payload_value(self) -> str:
        """`net` as the payload text. `repr` round-trips a float exactly."""
        return repr(self.net)

    @property
    def key_facts(self) -> str:
        """A one-line account of the figure, for a check's `evidence` field."""
        return (
            f"{self.strategy_id}/{self.symbol} trade {self.trade_id}: gross "
            f"{self.gross:.6f} - costs {self.costs:.6f} (commission "
            f"{self.commission_in:.4f}+{self.commission_out:.4f}, fees "
            f"{self.fees:.4f}, slippage {self.slippage_cost:.4f}) = net "
            f"{self.net:.6f} on {self.qty} contract(s)"
        )


def realized_pnl(entry: TradeEntry, exit_fill: TradeExit) -> RealizedPnl:
    """§6.6's realized figure for ONE closed trade. Pure, total, fails loud.

    Takes the EXIT FILL and the ENTRY FILL and nothing else — there is no
    parameter here through which an open mark, a peak or a high-water value
    could arrive (§6.6:435). Every input is checked before it is multiplied,
    because a wrong money figure that was computed is indistinguishable from a
    right one once it is written into §9's record.
    """
    where = f"trade {entry.trade_id!r}"
    if exit_fill.trade_id != entry.trade_id:
        raise MissingTradeFact(
            f"{where}: the exit names trade {exit_fill.trade_id!r}. A realized "
            "figure computed across two trades is attributed to whichever one "
            "the caller happened to pass first, and §6.6:448 keys the row on the "
            "pair that actually earned it"
        )
    if not entry.strategy_id or not entry.symbol:
        raise MissingTradeFact(
            f"{where}: strategy_id={entry.strategy_id!r} symbol={entry.symbol!r} "
            "— §6.6:448 locks the canonical key as (strategy_id, symbol), and a "
            "figure that cannot be attributed to one cannot be scored"
        )
    if entry.side not in _DIRECTION:
        raise MissingTradeFact(f"{where}: side={entry.side!r} has no direction")
    if not isinstance(entry.qty, int) or isinstance(entry.qty, bool) or entry.qty <= 0:
        raise ImpossibleTradeFact(
            f"{where}: qty={entry.qty!r} is not a positive whole number of "
            "contracts. §7 sizes in DISCRETE whole contracts, and a zero-qty "
            "'trade' realizes exactly the negative of its costs — a number that "
            "looks like a small loss and is really a missing position"
        )
    point_value = _finite(entry.point_value, "entry.point_value", where)
    if point_value <= 0.0:
        raise ImpossibleTradeFact(
            f"{where}: point_value={point_value!r} is not positive. §7 fixes a "
            "$/point per symbol; a non-positive one prices every move at zero or "
            "backwards, and the whole ranking inverts"
        )
    entry_price = _finite(entry.price, "entry.price", where)
    exit_price = _finite(exit_fill.price, "exit.price", where)
    commission_in = _finite(entry.commission, "entry.commission", where)
    commission_out = _finite(exit_fill.commission, "exit.commission", where)
    fees = _finite(exit_fill.fees, "exit.fees", where)
    slippage_cost = _finite(exit_fill.slippage_cost, "exit.slippage_cost", where)
    gross = (
        _DIRECTION[entry.side] * (exit_price - entry_price) * entry.qty * point_value
    )
    return RealizedPnl(
        trade_id=entry.trade_id,
        strategy_id=entry.strategy_id,
        symbol=entry.symbol,
        qty=entry.qty,
        gross=gross,
        commission_in=commission_in,
        commission_out=commission_out,
        fees=fees,
        slippage_cost=slippage_cost,
        net=gross - commission_in - commission_out - fees - slippage_cost,
    )


def realized_fields(facts: TradeFacts) -> dict[str, str]:
    """The `EventRow.fields` a realizing row carries. Exactly two keys, or raise.

    `symbol` rides beside the figure because `plane1_sink._values_clause` lifts
    `fields['symbol']` into the row's own column AND leaves it in the payload,
    and `nixscore.ema` reads the pair from `(strategy_id, symbol)`. The
    strategy_id is not returned: it is already an `EventRow` field of its own,
    and writing it twice would let a row disagree with itself.

    **No banned key can be produced by this function** — the returned mapping is
    built from two module constants — and the assertion below makes that a
    checked property rather than a reading of the source: a later edit that
    renamed `REALIZED_FIELD` onto a mark's spelling would raise here, on the
    write path, instead of quietly steering capital on an open mark.
    """
    figure: RealizedPnl = realized_pnl(facts.entry, facts.exit)
    fields = {SYMBOL_FIELD: figure.symbol, REALIZED_FIELD: figure.payload_value}
    leaked = sorted(BANNED_UNREALIZED_FIELDS & set(fields))
    if leaked:
        raise RealizedError(
            f"the writer would emit {', '.join(leaked)} on a realizing row — "
            "§6.6:435: 'Unrealized/paper gains never steer capital'"
        )
    return fields


@runtime_checkable
class TradeFactsBook(Protocol):  # pylint: disable=too-few-public-methods
    """Where the Limiter asks what a closing trade actually cost and returned.

    A PORT, deliberately narrow: one question, answered or not answered. `None`
    is a real answer here and means *no confirmed exit fill for this trade*,
    which is the ordinary state at protective-exit time (§4: *"we sent a
    flatten"* and *"the position is confirmed flat"* are different facts). The
    writer books a `realized_status` naming that, never a zero.
    """

    def facts_for(self, trade_id: str) -> TradeFacts | None:
        """This trade's confirmed entry and exit facts, or `None`."""


class RecordedTradeFacts:
    """An in-memory `TradeFactsBook`. Synthetic state, dies with the process.

    Deliberately not durable and it says so: §12.1 makes synthetic state the
    kind that is rebuilt from markers and broker truth after a kill, and a book
    of fills that claimed durability without a WAL behind it would be the worse
    lie. The durable record is §9's Plane-1 log, which is what this book's
    output is written INTO.
    """

    def __init__(self) -> None:
        self._facts: dict[str, TradeFacts] = {}

    def record(self, facts: TradeFacts) -> None:
        """Record one trade's confirmed round trip. Last write wins per trade."""
        self._facts[facts.trade_id] = facts

    def facts_for(self, trade_id: str) -> TradeFacts | None:
        """This trade's facts, or `None` when no exit fill is confirmed."""
        return self._facts.get(trade_id)

    def __len__(self) -> int:
        """How many trades the book can price. A non-vacuity floor for a gate."""
        return len(self._facts)
