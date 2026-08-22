"""ARC 058 — `nixrisk/closing.py`: the CLOSING fill, reconciled. The library half.

`checks/check_i1_convergence.py` proves this module is DAEMON-INVOKED and DRIVEN,
end to end, through a real `limiterd`'s own ingress. It cannot cheaply reach the
REFUSAL branches — a §3 commit that declines, a WAL that cannot append, a
strategy channel that raises, an ambiguous attribution — because each needs a
collaborator made to fail, and making one fail inside a spawned process is a
source plant rather than a test. Those branches are this module's, and the two
halves are deliberately different questions: *does the running daemon do this*
and *does this decide correctly when a collaborator refuses*.

**Nothing here is a second opinion on the daemon.** No test below spawns a
process, and the gate spawns six; where they touch the same verb they ask
different things of it.
"""
# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=too-few-public-methods,duplicate-code

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.closing import (  # pylint: disable=wrong-import-position
    ClosingFillHandler,
    FlattenInFlightBook,
    Refused,
)
from nixrisk.completions import (  # pylint: disable=wrong-import-position
    ExecReportDedup,
    SenderCompletion,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    EventKind,
    PositionRow,
    PositionState,
    TradeOrigin,
)

SYMBOL = "ES"
TRADE = "TRD-1"
STRATEGY = "s1"
ENTRY = "entry-1"
CLOSING = "flat-1"


# --------------------------------------------------------------------------
# The doubles. Each is the NARROWEST thing that satisfies one collaborator.
# --------------------------------------------------------------------------


@dataclass
class _Picture:
    """§3's table. `commit` REPLACES the rows, exactly as the real book does."""

    positions: tuple[PositionRow, ...]
    sum_open_margin: float = 1000.0
    commits: int = 0
    refuse: Exception | None = None

    def current(self) -> _Picture:
        return self

    def commit(self, **changes: Any) -> _Picture:
        if self.refuse is not None:
            raise self.refuse
        self.positions = tuple(changes.get("positions", self.positions))
        self.commits += 1
        self.sum_open_margin = sum(
            row.margin
            for row in self.positions
            if row.state in {PositionState.OPEN, PositionState.CLOSING}
        )
        return self


class _Stops:
    """§4's synthetic-stop book. LOUD on an unknown id, as `StopBook` is."""

    def __init__(self, armed: set[str] | None = None) -> None:
        self.armed = set() if armed is None else armed
        self.forgotten: list[str] = []
        self.raise_on_forget = False

    def get(self, client_order_id: str) -> object | None:
        return object() if client_order_id in self.armed else None

    def forget(self, client_order_id: str) -> None:
        if self.raise_on_forget:
            raise RuntimeError("stop book refused")
        self.armed.discard(client_order_id)
        self.forgotten.append(client_order_id)


class _Watch:
    """C1's fire-once book. SILENT on an unknown id, as `StopWatch` is."""

    def __init__(self) -> None:
        self.forgotten: list[str] = []

    def forget(self, client_order_id: str) -> str:
        self.forgotten.append(client_order_id)
        return client_order_id


class _Origins:
    """§3/§4's trade<->order join."""

    def __init__(self, by_order: dict[str, TradeOrigin]) -> None:
        self._by_order = by_order

    def origin_for_order(self, client_order_id: str) -> TradeOrigin | None:
        return self._by_order.get(client_order_id)

    def origin_for_trade(self, trade_id: str) -> TradeOrigin | None:
        return next(
            (o for o in self._by_order.values() if o.trade_id == trade_id), None
        )


class _Strategy:
    """§4 fan-out (a)."""

    def __init__(self) -> None:
        self.closed: list[tuple[str, str, str, bool]] = []
        self.raise_on_close = False

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        if self.raise_on_close:
            raise RuntimeError("no channel")
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


class _Plane1:
    """§9's write path."""

    def __init__(self) -> None:
        self.rows: list[Any] = []
        self.raise_on_enqueue = False

    def enqueue(self, row: Any) -> None:
        if self.raise_on_enqueue:
            raise RuntimeError("DiskCritical: WAL cannot append")
        self.rows.append(row)


@dataclass(frozen=True)
class _Record:
    """§4's arbiter's `ClosedRecord`, read through `closed_record`."""

    reason: str
    hard_reset: bool


class _Arbiter:
    def __init__(self, records: dict[str, _Record]) -> None:
        self._records = records

    def closed_record(self, trade_id: str) -> _Record | None:
        return self._records.get(trade_id)


# --------------------------------------------------------------------------
# The rig
# --------------------------------------------------------------------------


def _row(
    trade_id: str = TRADE, state: PositionState = PositionState.OPEN
) -> PositionRow:
    return PositionRow(
        trade_id=trade_id,
        symbol=SYMBOL,
        strategy_id=STRATEGY,
        size=2,
        margin=1000.0,
        state=state,
        stop_distance=8,
    )


def _fill(
    client_order_id: str = CLOSING, exec_id: str = "x-1", symbol: str = SYMBOL
) -> SenderCompletion:
    return SenderCompletion(
        event="on_fill",
        client_order_id=client_order_id,
        exec_id=exec_id,
        done_qty=2,
        # B108 is about a hardcoded temp PATH being written to; this string
        # is never opened. `source` is an OBSERVATION — the ingress file the
        # completion entered through — and it is exactly what lets a reader
        # tell "the daemon dispatched it" from "the test called the handler".
        source="/tmp/completions/close.json",  # nosec B108
        symbol=symbol,
        price=4997.0,
        cumulative_qty=2,
    )


def _rig(  # pylint: disable=too-many-arguments
    *,
    rows: tuple[PositionRow, ...] = (),
    armed: set[str] | None = None,
    origins: dict[str, TradeOrigin] | None = None,
    arbiter: _Arbiter | None = None,
    in_flight: FlattenInFlightBook | None = None,
) -> dict[str, Any]:
    picture = _Picture(positions=rows)
    stops = _Stops({ENTRY} if armed is None else armed)
    watch = _Watch()
    book = FlattenInFlightBook() if in_flight is None else in_flight
    strategy = _Strategy()
    plane1 = _Plane1()
    join = _Origins(
        {
            ENTRY: TradeOrigin(
                trade_id=TRADE, client_order_id=ENTRY, strategy_id=STRATEGY
            )
        }
        if origins is None
        else origins
    )
    dedup = ExecReportDedup()
    # Built with EXPLICIT keywords rather than a `**dict` splat. The splat was
    # written first and mypy refused it BY NAME at the commit gate: a
    # `dict[str, object]` erases every collaborator's type at exactly the seam
    # this module exists to type correctly. `closing.py` names the Limiter's own
    # books CONCRETELY so `check_uncalled_entry_points` can resolve their
    # callers (that is what discharges D3.481), and a rig that erased them would
    # be asserting against a shape nothing checks. The per-argument ignores are
    # the honest cost of substituting doubles for concrete types, and each is
    # narrow enough to name the argument it covers.
    handler = ClosingFillHandler(
        picture=picture,  # type: ignore[arg-type]
        stops=stops,  # type: ignore[arg-type]
        stop_watch=watch,  # type: ignore[arg-type]
        origins=join,  # type: ignore[arg-type]
        dedup=dedup,
        strategy=strategy,
        plane1=plane1,
        in_flight=book,
        arbiter=arbiter,
        clock=lambda: 1000.0,
    )
    return {
        "picture": picture,
        "stops": stops,
        "stop_watch": watch,
        "origins": join,
        "dedup": dedup,
        "strategy": strategy,
        "plane1": plane1,
        "handler": handler,
        "book": book,
    }


def _armed(book: FlattenInFlightBook, *, trade_id: str = TRADE) -> None:
    book.arm(
        key=ENTRY,
        symbol=SYMBOL,
        trade_id=trade_id,
        strategy_id=STRATEGY,
        reason="protective flatten (trigger=synthetic_stop)",
        trigger="synthetic_stop",
        at=999.0,
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the happy path really closes, so every refusal below is
# a refusal of something that otherwise works.
# --------------------------------------------------------------------------


def test_the_HAPPY_PATH_closes_the_row_releases_the_margin_and_tells_the_strategy():
    rig = _rig(rows=(_row(),))
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert rig["picture"].positions[0].state is PositionState.CLOSED
    assert rig["picture"].sum_open_margin == 0.0
    assert outcome.open_margin_after == 0.0
    assert rig["stops"].forgotten == [ENTRY]
    assert rig["stop_watch"].forgotten == [ENTRY]
    assert rig["strategy"].closed == [
        (TRADE, STRATEGY, "protective flatten (trigger=synthetic_stop)", True)
    ]
    assert [r.kind for r in rig["plane1"].rows] == [EventKind.CLOSED]
    assert not outcome.failures
    assert not rig["book"].in_flight()


def test_the_CLOSED_row_carries_the_close_PRICE_and_books_NO_realized_figure():
    """The two facts a fill-driven close has that a reconcile poll does not —
    and the one it must NOT carry, because `request_close` already booked it."""
    rig = _rig(rows=(_row(),))
    _armed(rig["book"])
    rig["handler"].close(_fill())
    fields = dict(rig["plane1"].rows[0].fields)
    assert fields["close_price"] == "4997.0"
    assert fields["exec_id"] == "x-1"
    assert fields["closing_order_id"] == CLOSING
    assert "realized_pnl" not in fields
    assert "double" in fields["realized_status"]


# --------------------------------------------------------------------------
# RECOGNITION — three facts, and a fill failing any one is NOT adopted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("event", ["on_cancel", "on_reject", "on_ack"])
def test_a_NON_FILL_is_not_a_close(event: str):
    rig = _rig(rows=(_row(),))
    _armed(rig["book"])
    assert rig["handler"].close(replace(_fill(), event=event)) is None
    assert rig["picture"].commits == 0


def test_an_APPROVED_ENTRY_belongs_to_the_fill_cascade_and_is_never_adopted():
    rig = _rig(rows=(_row(),))
    _armed(rig["book"])
    assert rig["handler"].close(_fill(client_order_id=ENTRY)) is None
    assert rig["picture"].commits == 0


def test_a_fill_with_NO_FLATTEN_IN_FLIGHT_is_left_to_the_ordinary_dispatch():
    """The load-bearing fact. Adopting this would close a position off a venue
    message nothing in this process asked for."""
    rig = _rig(rows=(_row(),))
    assert rig["handler"].close(_fill()) is None
    assert rig["picture"].commits == 0
    assert not rig["handler"].refusals


def test_a_flatten_in_flight_for_ANOTHER_SYMBOL_does_not_adopt_this_fill():
    rig = _rig(rows=(_row(),))
    rig["book"].arm(
        key="other",
        symbol="NQ",
        trade_id="TRD-9",
        strategy_id=STRATEGY,
        reason="r",
        trigger="uncertainty",
        at=999.0,
    )
    assert rig["handler"].close(_fill()) is None
    assert rig["picture"].commits == 0


def test_a_symbol_with_NO_LIVE_ROW_closes_nothing_which_is_the_idempotent_case():
    rig = _rig(rows=(_row(state=PositionState.CLOSED),))
    _armed(rig["book"])
    assert rig["handler"].close(_fill()) is None
    assert rig["picture"].commits == 0


# --------------------------------------------------------------------------
# §4's UNTARGETED uncertainty flatten — attribution by SYMBOL, refused when
# ambiguous. The branch a daemon drive reaches only with two live trades.
# --------------------------------------------------------------------------


def test_an_UNTARGETED_flatten_attributes_to_the_symbol_s_SOLE_live_row():
    rig = _rig(rows=(_row(),))
    _armed(rig["book"], trade_id="")
    outcome = rig["handler"].close(_fill())
    assert outcome is not None and outcome.trade_id == TRADE
    assert rig["picture"].positions[0].state is PositionState.CLOSED


def test_an_UNTARGETED_flatten_over_TWO_live_rows_REFUSES_and_NAMES_both():
    """§4 tags feedback BY trade id so it cannot be applied to the wrong
    position. Guessing here would release the wrong capital and retire the
    wrong stop, so it fails closed and says which two it could not choose."""
    rig = _rig(rows=(_row(), _row(trade_id="TRD-2")))
    _armed(rig["book"], trade_id="")
    assert rig["handler"].close(_fill()) is None
    assert rig["picture"].commits == 0
    assert rig["handler"].refusals, "an ambiguous attribution must be NAMED"
    why = rig["handler"].refusals[0]
    assert "TRD-1" in why and "TRD-2" in why
    assert "NOT closed, NOT discharged" in why
    assert rig["book"].in_flight(), "the flatten must stay armed for a retry"


# --------------------------------------------------------------------------
# IDEMPOTENCY — two keys, because there are two ways to double-close
# --------------------------------------------------------------------------


def test_a_RE_DELIVERED_exec_report_closes_nothing_twice_and_says_why():
    rig = _rig(rows=(_row(),))
    _armed(rig["book"])
    assert rig["handler"].close(_fill()) is not None
    _armed(rig["book"])  # the venue could re-deliver while another is in flight
    rig["picture"].positions = (_row(),)  # and §3 could still show it live
    assert rig["handler"].close(_fill()) is None
    assert rig["handler"].duplicates == 1
    assert "§4:214" in rig["handler"].refusals[-1]
    assert rig["picture"].commits == 1


def test_the_dedup_book_is_SHARED_with_the_entry_dispatcher_never_a_second_one():
    """A private book would make a re-delivery a duplicate to one and news to
    the other. The key is claimed in the SAME book the entry path claims in."""
    rig = _rig(rows=(_row(),))
    _armed(rig["book"])
    rig["dedup"].claim((CLOSING, "x-1"))  # the entry dispatcher got there first
    assert rig["handler"].close(_fill()) is None
    assert rig["handler"].duplicates == 1
    assert rig["picture"].commits == 0


# --------------------------------------------------------------------------
# THE ORDER IS THE SAFETY PROPERTY — §3 first, and its refusal aborts the whole
# --------------------------------------------------------------------------


def test_a_REFUSED_S3_COMMIT_aborts_the_WHOLE_close_and_leaves_the_flatten_ARMED():
    """Fail-closed: the capital stays committed and the stop stays armed, which
    is the conservative error. Telling a strategy it is flat while §3 still
    carries the position is not."""
    rig = _rig(rows=(_row(),))
    rig["picture"].refuse = RuntimeError("TornPicture: refusing to commit")
    _armed(rig["book"])
    with pytest.raises(Refused):
        rig["handler"].close(_fill())
    assert not rig["stops"].forgotten, "nothing downstream of §3 may have run"
    assert not rig["stop_watch"].forgotten
    assert not rig["plane1"].rows
    assert not rig["strategy"].closed
    assert rig["book"].in_flight(), "the flatten stays IN FLIGHT for a retry"
    assert "NOTHING downstream ran" in rig["handler"].refusals[-1]


# --------------------------------------------------------------------------
# EVERYTHING AFTER THE COMMIT IS RECORDED, NEVER RAISED (FC1, one module over)
# --------------------------------------------------------------------------


def test_a_WAL_that_cannot_append_does_NOT_abort_a_close_the_venue_already_made():
    rig = _rig(rows=(_row(),))
    rig["plane1"].raise_on_enqueue = True
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert rig["picture"].positions[0].state is PositionState.CLOSED
    assert rig["strategy"].closed, "the strategy is still told"
    assert any("§12.10" in f and "NOT appended" in f for f in outcome.failures)
    assert rig["handler"].unbooked


def test_a_STRATEGY_CHANNEL_that_raises_is_RECORDED_and_the_close_still_stands():
    rig = _rig(rows=(_row(),))
    rig["strategy"].raise_on_close = True
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert rig["picture"].sum_open_margin == 0.0
    assert any("was NOT delivered" in f for f in outcome.failures)


def test_a_CLOSE_WITH_NO_ARMED_STOP_is_NAMED_rather_than_silently_fine():
    """§12.1 makes the stop Limiter-held, so a position that closed with nothing
    protecting it is the unprotected-position condition arriving late."""
    rig = _rig(rows=(_row(),), armed=set())
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert any("no synthetic stop was armed" in f for f in outcome.failures)


def test_a_STOP_BOOK_that_refuses_the_forget_is_RECORDED_with_its_own_reason():
    rig = _rig(rows=(_row(),))
    rig["stops"].raise_on_forget = True
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert any(
        "was NOT retired" in f and "stop book refused" in f for f in outcome.failures
    )


def test_a_TRADE_WITH_NO_JOIN_retires_no_stop_and_says_so():
    rig = _rig(rows=(_row(),), origins={})
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert outcome.entry_order_id == ""
    assert any("retired NO synthetic stop" in f for f in outcome.failures)
    assert not rig["stop_watch"].forgotten


# --------------------------------------------------------------------------
# ATTRIBUTION — §4's arbiter is the authority where one exists
# --------------------------------------------------------------------------


def test_the_ARBITER_S_reason_and_FSM_verdict_WIN_over_the_daemon_s_send_record():
    """`request_close` is the one place a close is DECIDED; re-deriving either
    fact here would be the system choosing one thing twice."""
    rig = _rig(
        rows=(_row(),),
        arbiter=_Arbiter(
            {TRADE: _Record(reason="closed, reason=session", hard_reset=True)}
        ),
    )
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert outcome.reason == "closed, reason=session"
    assert rig["plane1"].rows[0].reason == "closed, reason=session"
    assert rig["strategy"].closed[0][2] == "closed, reason=session"


def test_with_NO_arbiter_record_the_DAEMON_S_OWN_send_reason_is_used():
    """§4's untargeted uncertainty flatten never reaches the arbiter at all, so
    the fallback is a real answer rather than a default."""
    rig = _rig(rows=(_row(),), arbiter=_Arbiter({}))
    _armed(rig["book"])
    outcome = rig["handler"].close(_fill())
    assert outcome is not None
    assert outcome.reason == "protective flatten (trigger=synthetic_stop)"
    assert outcome.hard_reset is True


# --------------------------------------------------------------------------
# THE IN-FLIGHT BOOK is BOUNDED, and the eviction is COUNTED
# --------------------------------------------------------------------------


def test_the_in_flight_book_is_BOUNDED_and_an_evicted_flatten_is_COUNTED():
    """An unbounded book on a daemon that runs for weeks is a leak with a §12
    name, and an eviction nobody counted is a confirmation nobody can attribute."""
    book = FlattenInFlightBook(max_entries=2)
    for n in range(4):
        book.arm(
            key=f"k{n}",
            symbol=SYMBOL,
            trade_id=f"T{n}",
            strategy_id=STRATEGY,
            reason="r",
            trigger="uncertainty",
            at=float(n),
        )
    assert len(book.in_flight()) == 2
    assert book.armed == 4
    assert book.dropped == 2
    assert book.record()["dropped"] == 2


def test_discharging_a_flatten_TWICE_is_False_the_second_time():
    book = FlattenInFlightBook()
    entry = book.arm(
        key="k",
        symbol=SYMBOL,
        trade_id=TRADE,
        strategy_id=STRATEGY,
        reason="r",
        trigger="synthetic_stop",
        at=1.0,
    )
    assert book.discharge(entry) is True
    assert book.discharge(entry) is False
    assert book.discharged == 1
