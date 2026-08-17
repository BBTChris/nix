"""ARC 034 / sub-agent A — the fail-closed branches of the fill path itself.

`checks/check_fill_handler.py` and `checks/check_trade_join.py` drive the fill
path end to end and own the ORDERING, CAUSATION, PARTIAL-FILL and JOIN
properties. This suite exists for a different and narrower reason, stated so it
is not mistaken for a second instrument over the same property (doctrine C.9):

    **the refusals in `scripts/nixrisk/fills.py` and `scripts/nixrisk/join.py`
    that no gate drive can reach.**

The ARC 034 / 0.5 audit measured exactly this shape one arc earlier —
*fail-closed branches undriven because the gate's own doubles cannot produce the
input*. A gate assembles a WORKING fill path out of shipped components, so it
cannot hand `IocRemainder` a negative quantity, cannot re-approve a live order,
and cannot pass a non-callable as a minting policy: those inputs are unreachable
from a correct rig. They are reachable from here, and each one is a guard that
fails closed on money.

Every control asserts the REASON — a substring of the refusal naming WHAT was
wrong — never the exception type alone (check contract v2 §11 / §18). Every `§`
cites `docs/nics_risk_subsystem_spec_v1.3.md`.
"""
# pylint: disable=invalid-name,duplicate-code
# too-few-public-methods: the doubles below are SINGLE-VERB ports, and the
# narrowness is the point — `fills.CancelPort` declares `cancel_order` and
# nothing else so a reservation path structurally cannot place an order. A
# second verb added to satisfy a threshold of two would widen exactly the
# surface the module narrowed on purpose.
# pylint: disable=too-few-public-methods

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk import fills, join  # pylint: disable=wrong-import-position
from nixrisk.positions import (  # pylint: disable=wrong-import-position
    identity_trade_id,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)


def _order(coid: str = "CO-1", *, qty: int = 4, strategy: str = "strat-es"):
    return ProposedOrder(
        client_order_id=coid,
        strategy_id=strategy,
        symbol="ES",
        side=Side.LONG,
        qty=qty,
        margin_per_contract=500.0,
        stop_ticks=13,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


class _Reservations:
    """The two verbs `fills.ReservationBookPort` declares, and nothing else."""

    def __init__(self, *, sigma: float = 0.0, accept: bool = True) -> None:
        self._sigma = sigma
        self._accept = accept
        self.calls: list[tuple[str, TerminalPath]] = []

    def resolve(self, client_order_id, via, now, reason=""):
        """Record and answer. `Resolution` is the shipped value type."""
        del now, reason
        self.calls.append((client_order_id, via))
        from nixrisk.reservations import (  # pylint: disable=import-outside-toplevel
            Refusal,
            RefusalKind,
            Resolution,
        )

        if self._accept:
            # `Resolution.accepted` is `released is not None`; the RECORD's shape
            # is `reservations`' own property and has its own gate, so a sentinel
            # is enough here and a fabricated `Reservation` would be a second
            # source of truth for a value type this suite does not judge.
            return Resolution(released=object())
        return Resolution(
            refusal=Refusal(
                kind=RefusalKind.ALREADY_TERMINAL,
                client_order_id=client_order_id,
                requested=via,
                reason="planted: this order already reached a terminal path",
            )
        )

    def total_reserved(self) -> float:
        """§11.3's running aggregate."""
        return self._sigma


class _Cancels:
    """`fills.CancelPort`, recording."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def cancel_order(self, client_order_id: str) -> None:
        """Record the §4 IOC cancel."""
        self.cancelled.append(client_order_id)


def _clock() -> float:
    return 1000.0


# ==========================================================================
# `ApprovedOrderBook` — §4 allows ONE in-flight action per strategy
# ==========================================================================


def test_RE_APPROVING_A_LIVE_ORDER_is_REFUSED_and_NAMES_BOTH_DISTANCES() -> None:
    """A silent replacement re-points the distance §7:501 prices the bucket from."""
    book = fills.ApprovedOrderBook()
    book.record(_order())

    with pytest.raises(fills.DuplicateApproval) as caught:
        book.record(_order(qty=9))

    assert "already approved" in str(caught.value), caught.value
    # §18: the TYPE must not contradict the condition. A duplicate approval is
    # the opposite of an unapproved fill, so it may not share that name.
    assert not isinstance(caught.value, fills.UnapprovedFill), caught.value
    assert "stop_ticks=13" in str(caught.value), caught.value
    assert book.recorded == 1, book.recorded


def test_an_UNKNOWN_ORDER_is_a_QUESTION_WITH_AN_ANSWER_never_a_raise() -> None:
    """`ApprovedOrderPort` returns `None`; the CALLER holds the fatality context."""
    assert fills.ApprovedOrderBook().order_for("CO-NOPE") is None


# ==========================================================================
# `IocRemainder` — §4's remainder is `requested − filled`
# ==========================================================================


@pytest.mark.parametrize(
    ("filled", "requested"),
    [(0, 4), (-1, 4), (3, 0), (3, -2)],
)
def test_a_NON_POSITIVE_QUANTITY_is_REFUSED_and_NAMES_BOTH_SIDES(
    filled: int, requested: int
) -> None:
    """A cap on nothing is a statement about nothing. Deny at the boundary."""
    remainder = fills.IocRemainder(
        reservations=_Reservations(), cancels=_Cancels(), clock=_clock
    )

    with pytest.raises(fills.InvalidRemainder) as caught:
        remainder.release_remainder("CO-1", filled_qty=filled, requested_qty=requested)

    assert f"filled_qty={filled!r}" in str(caught.value), caught.value
    assert f"requested_qty={requested!r}" in str(caught.value), caught.value


def test_an_OVER_FILL_is_COUNTED_and_NOT_CANCELLED_because_NOTHING_IS_WORKING() -> None:
    """§4: 'if the cancel loses the race and the remainder fills'. Counted, not raised.

    The count matters on its own: an over-fill against a reservation taken for the
    REQUESTED size is the one shape that can breach a cap, so it must be visible
    even though §4 makes cumulative reality win.
    """
    cancels = _Cancels()
    remainder = fills.IocRemainder(
        reservations=_Reservations(sigma=7.5), cancels=cancels, clock=_clock
    )

    sigma = remainder.release_remainder("CO-1", filled_qty=5, requested_qty=4)

    assert sigma == 7.5
    assert remainder.over_fills == 1, remainder.over_fills
    assert not cancels.cancelled, cancels.cancelled
    assert remainder.history()[0].cancelled is False


def test_a_DUPLICATE_TERMINAL_EVENT_RECORDS_THE_REASON_never_a_bare_boolean() -> None:
    """§4's fill-vs-cancel race is ordinary data, and the reason IS the fact (§18)."""
    remainder = fills.IocRemainder(
        reservations=_Reservations(accept=False), cancels=_Cancels(), clock=_clock
    )

    remainder.release_remainder("CO-1", filled_qty=4, requested_qty=4)

    record = remainder.history()[0]
    assert record.released is False
    assert "already reached a terminal path" in record.refusal_reason
    assert remainder.refused_releases == 1


def test_the_CANCEL_PRECEDES_THE_RELEASE_because_the_OTHER_ORDER_OVER_COMMITS() -> None:
    """Releasing first frees capital while the venue is still working the remainder."""
    order: list[str] = []

    class _Watching(_Cancels):
        def cancel_order(self, client_order_id: str) -> None:
            order.append("cancel")
            super().cancel_order(client_order_id)

    class _WatchingReservations(_Reservations):
        def resolve(self, client_order_id, via, now, reason=""):
            order.append("release")
            return super().resolve(client_order_id, via, now, reason)

    remainder = fills.IocRemainder(
        reservations=_WatchingReservations(), cancels=_Watching(), clock=_clock
    )
    remainder.release_remainder("CO-1", filled_qty=3, requested_qty=4)

    assert order == ["cancel", "release"], order


def test_the_RELEASE_IS_BOOKED_AS_A_FILL_because_3_CONVERTS_IT_TO_OPEN_MARGIN() -> None:
    """§3's lifecycle: the reservation is released ON FILL and becomes open margin."""
    reservations = _Reservations()
    remainder = fills.IocRemainder(
        reservations=reservations, cancels=_Cancels(), clock=_clock
    )

    remainder.release_remainder("CO-1", filled_qty=3, requested_qty=4)

    assert reservations.calls == [("CO-1", TerminalPath.FILL)], reservations.calls


# ==========================================================================
# `join` — the production mint and the factory that guards it
# ==========================================================================


def test_the_MINT_REFUSES_TO_RETURN_ITS_INPUT_whatever_the_SPELLING() -> None:
    """The guard is INSIDE the mint, so a contrived `client_order_id` cannot pass."""
    mint = join.SequencedTradeIdMint(prefix="")
    collision = f"-00000001-{'strat-es'}"

    with pytest.raises(join.CollapsedJoin) as caught:
        mint.mint(_order(coid=collision))

    assert "IS that order's client_order_id" in str(caught.value), caught.value
    assert "D3.177" in str(caught.value), caught.value


def test_the_MINT_IS_INJECTIVE_and_SAYS_HOW_MANY_IT_HAS_ISSUED() -> None:
    """A minting policy that cannot say what it issued can only be believed."""
    mint = join.SequencedTradeIdMint()
    minted = {mint.mint(_order(coid=f"CO-{n}", strategy="s")) for n in range(50)}

    assert len(minted) == 50, sorted(minted)[:5]
    assert mint.issued == 50, mint.issued


def test_a_NON_CALLABLE_POLICY_is_REFUSED_and_NAMES_WHAT_WAS_PASSED() -> None:
    """A registry with no minting policy has no key to publish §3's table under."""
    with pytest.raises(join.CollapsedJoin) as caught:
        join.production_origins(mint=42)  # type: ignore[arg-type]

    assert "neither a TradeIdMintPort nor a callable" in str(caught.value), caught.value
    assert "42" in str(caught.value), caught.value


def test_a_MINT_RETURNING_A_BLANK_KEY_is_REFUSED_by_the_PROBE() -> None:
    """§3:159 keys the table by trade_id; a blank key collides every row."""
    with pytest.raises(join.CollapsedJoin) as caught:
        join.production_origins(mint=lambda order: "")

    assert "collides every row" in str(caught.value), caught.value


def test_the_PROBE_BEATS_A_NAME_COMPARISON_on_the_ANONYMOUS_IDENTITY() -> None:
    """`policy is identity_trade_id` is defeated by the same behaviour renamed."""
    with pytest.raises(join.CollapsedJoin) as caught:
        join.production_origins(mint=lambda order: order.client_order_id)

    assert "is the client_order_id it was given" in str(caught.value), caught.value


def test_the_NAMED_DEGENERATE_MINT_is_REFUSED_and_NAMED(monkeypatch) -> None:
    """The fast path exists so the message can say WHICH function was passed."""
    with pytest.raises(join.CollapsedJoin) as caught:
        join.production_origins(mint=identity_trade_id)

    assert "positions.identity_trade_id was passed" in str(caught.value), caught.value
    assert "documented degenerate case" in str(caught.value), caught.value
    del monkeypatch


def test_a_PORT_OBJECT_and_a_BARE_CALLABLE_are_BOTH_ACCEPTED() -> None:
    """Refusing the bare callable would leave the degenerate policy reachable."""
    port = join.SequencedTradeIdMint()
    assert isinstance(port, join.TradeIdMintPort)

    from_port = join.production_origins(mint=port)
    from_callable = join.production_origins(mint=join.SequencedTradeIdMint().mint)

    for origins in (from_port, from_callable):
        origin = origins.record(_order())
        assert origin.trade_id != "CO-1", origin
        assert origins.origin_for_trade(origin.trade_id).client_order_id == "CO-1"
