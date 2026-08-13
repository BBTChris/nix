"""§4's synthetic stops — the distance→price conversion and the trailing ratchet.

ARC 029 / sub-agent A. Implements the FROZEN `StopBookPort` declared in
`scripts/nixrisk/seam.py` over the FROZEN `StopState` value type. Nothing here is
a second authority: the seam fixes the types and the sync/async posture,
`nics_risk_subsystem_spec_v1.3.md` §4 fixes the stop lifecycle, and this module
is the arithmetic that keeps them true. Every `§` cites that frozen spec.

------------------------------------------------------------------------------
THESE STOPS ARE SYNTHETIC, AND THAT IS BY DESIGN — NOT A GAP TO CLOSE HERE
------------------------------------------------------------------------------
§12.1: *"This is our software, not a broker-side stop — that prohibition
stands."* A synthetic stop lives in the Limiter's memory: `arm` returns a
`StopState`, `maintain` is cache-reads-and-arithmetic (§11's hot path), and
NOTHING in this module reaches a broker. It therefore dies with the process
holding it; the Sentinel (§12.1, R4) is what covers that gap and it does not
exist yet, so a killed Risk Engine is an unprotected position. No green in this
module's tests may be read as denying that. `checks/check_synthetic_stop_only.py`
proves the prohibition mechanically: no order-placement verb, no broker import,
no broker-native stop order-type token appears on this path.

------------------------------------------------------------------------------
A1 — CONVERSION HAPPENS ONCE, AT CONFIRMED FILL
------------------------------------------------------------------------------
The GO carries stop intent as a tick DISTANCE, never an absolute price (§4): the
strategy signals before it knows its fill, so distance survives slippage where a
price would land on the wrong side of entry. `arm(fill_price, order)` converts
distance→price ONCE, against the confirmed fill, and records that fill in
`StopState.anchor`. `maintain` never re-converts the anchor from a distance — the
initial `level` is stored, not recomputed — so the conversion cannot silently run
twice against two different prices. Missing/zero/invalid distance ⇒ DENY (§3
ingress guard, §15 C3); here a deny is a raise, because `arm` returns a
`StopState`, not a verdict, and directive 4 is fail-closed-and-loud.

------------------------------------------------------------------------------
A2 / A3 — FIXED IS STATIC; TRAILING RATCHETS BEHIND THE HIGH-WATER MARK
------------------------------------------------------------------------------
* **fixed** (§4:188): anchored once at `fill ± initial_distance`, static forever.
  `maintain` never moves it.
* **trailing** (§4:190-196): two distances. `initial_distance` is where the stop
  first sits; `trail_distance` is the gap kept behind the high-water mark. The
  stop HOLDS at the initial level until price advances far enough that the trail
  would sit TIGHTER than the initial stop, and only THEN begins trailing — so it
  only ever moves in the strategy's favour and never jumps backward at
  activation. Once trailing it ratchets behind the HWM every tick and never gives
  ground back.

WHY NON-REGRESSION HOLDS, AND WHAT THE `activated` LATCH IS ACTUALLY FOR. The
ratchet never gives ground back because `level` only ever moves to a value the
high-water mark implies, and the high-water mark is monotone in the strategy's
favour (`max` for a long, `min` for a short) — it never retreats, so the trail
level it implies never retreats. That is the primary guarantee. The seam
nevertheless MANDATES the `activated` field, and it forbids one specific wrong
implementation: deciding activation from the CURRENT price each tick ("is price
now far enough from the initial stop?"). That test answers *no* on a retrace and
would de-activate a stop that had already begun trailing, giving ground back at
the worst moment. This module never reads the current price to decide activation;
it latches `activated` the first tick the trail crosses tighter than the initial
level and never re-evaluates it. `test_stops.py` plants exactly that
current-price recompute and shows it regresses, which is the measurement behind
this paragraph.

------------------------------------------------------------------------------
A4 — PER-TICK MAINTENANCE IS NOT LOGGED (§12.10)
------------------------------------------------------------------------------
§12.10: per-tick trailing ratchets are chatty and derivable, so they are NOT
logged; the final trail level rides the `closed` row, which the protective-flatten
machinery emits — not this module. This class therefore holds NO Plane-1 sink at
all: it cannot log per tick because it has nothing to log with. That is a
structural guarantee, not a discipline, and `test_stops.py` asserts the
constructor takes no logging collaborator so the guarantee cannot rot into one.

------------------------------------------------------------------------------
A SEAM GAP, REPORTED RATHER THAN PAPERED OVER — the trailing second distance
------------------------------------------------------------------------------
`ProposedOrder` (frozen) carries a SINGLE `stop_ticks`, but §4 gives a trailing
stop TWO distances and `StopState` has fields for both. `stop_ticks` is the risk
distance the Allocator sized against (§4:129, `(stop_ticks + slippage_pad) ×
tick_value`), i.e. the INITIAL distance; the trailing `trail_distance` has no
field on the frozen `ProposedOrder` — the GO's second distance was dropped in the
projection. The seam is frozen and was not edited. `arm` therefore takes the
trail distance as an explicit `trail_ticks` argument, defaulted to `None`, and a
TRAILING order armed without it is DENIED (fail closed) rather than having a trail
distance invented from the initial one — inventing `trail = initial` would be a
policy choice the strategy is supposed to make per signal (§4:187), not this
module. A FIXED order ignores `trail_ticks` entirely. This gap is an integration
finding for the arc integrator to route (extend the contract / GO projection to
carry `trail_distance`); it is named here so it cannot become invisible.

Tick size is a different matter and is legitimately config: the price value of
one tick is an instrument constant (a contract spec, boot-loaded, restart-only),
not a per-signal choice, so `StopBook` is constructed with a per-symbol tick-size
map. A symbol absent from it is not-tradable and `arm` denies — the §4:198 rule
(*symbol absent from the margin field set ⇒ not-tradable*) one layer in.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from typing import Final

from nixrisk.seam import ProposedOrder, Side, StopMode, StopState


class StopError(RuntimeError):
    """Base for every refusal this book raises. Never caught internally."""


class InvalidStopIntent(StopError):
    """`arm` for an order whose stop distance is missing, zero, or not finite.

    §3's ingress guard and §15 C3: *invalid/zero stop intent ⇒ deny*. A stop
    distance of zero would anchor the stop ON the entry, so it fires on the first
    adverse tick; a negative distance would place it on the PROFIT side of entry,
    where it can never protect anything. Both are denied at conversion, loudly.
    """


class UntradableSymbol(StopError):
    """`arm` for a symbol with no tick size — its distance has no price scale.

    §4:198: a symbol absent from the instrument field set is not-tradable. A tick
    distance cannot be converted to a price without the price value of a tick, so
    a missing tick size is denied rather than defaulted — a guessed tick size is a
    stop at the wrong price.
    """


class DuplicateStop(StopError):
    """`arm` for a `client_order_id` this book already holds a stop for.

    A stop is armed ONCE, at the confirmed fill (§4). A second arm for the same
    order is either a duplicate fill event or a keying defect; either way it must
    not silently replace a live stop with a re-converted one.
    """


class UnknownStop(StopError):
    """`forget` for a `client_order_id` this book never armed or already dropped.

    Loud on purpose: a forget for a stop that does not exist is the signature of a
    close event keyed differently from the arm event, which would leave real
    positions holding stops nobody maintains — the same keying-disagreement class
    `reservations.py` refuses in its `_refuse_unknown` path.
    """


#: The smallest admissible stop distance, in ticks. §4 expresses stop intent in
#: whole ticks (`stop_ticks: int`), so the floor is one tick: a sub-tick stop is
#: not representable and a zero-tick stop is denied by `InvalidStopIntent`.
MIN_STOP_TICKS: Final[int] = 1


def _sign(side: Side) -> float:
    """+1 when the favourable direction is UP (long), -1 when it is DOWN (short).

    Every direction-dependent comparison in this module is expressed as
    `sign * x`, so a long and a short share one arithmetic and the two can never
    drift apart the way two mirror-image code paths would. For a long the stop
    sits BELOW entry and the high-water mark is the MAX price; for a short the
    stop sits ABOVE entry and the high-water mark is the MIN price. `sign` is the
    one place that distinction lives.
    """
    return 1.0 if side is Side.LONG else -1.0


def _tighter(sign: float, candidate: float, level: float) -> bool:
    """Is `candidate` a tighter (more protective) stop than `level`?

    Tighter means closer to locking in the favourable move: HIGHER for a long,
    LOWER for a short. `sign * candidate > sign * level` captures both. Strict:
    a candidate equal to the current level is not an advance and must not count as
    a ratchet, or a stall would read as motion.
    """
    return sign * candidate > sign * level


def _breached(sign: float, price: float, level: float) -> bool:
    """Has `price` reached or passed through the stop `level`?

    For a long, breach is `price <= level` (price fell to the stop); for a short,
    `price >= level`. `sign * price <= sign * level` is both. Inclusive of the
    level itself: a trade that prints exactly at the stop has hit it.
    """
    return sign * price <= sign * level


def _valid_distance(client_order_id: str, ticks: int, field: str) -> int:
    """A stop distance that is a whole positive number of ticks, or a raise.

    §3/§15 C3: zero or invalid stop intent ⇒ deny. Both sides of the guard live
    here so the initial and the trail distance are held to one rule. `bool` is
    rejected explicitly: `True` is an `int` of value 1 in Python, and a stop
    distance that is really a mis-passed flag is exactly the invalid intent §15 C3
    denies.
    """
    if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < MIN_STOP_TICKS:
        raise InvalidStopIntent(
            f"{client_order_id}: {field}={ticks!r} is not a whole number of ticks "
            f"at or above {MIN_STOP_TICKS} — a zero or negative stop distance "
            "anchors the stop on or past the entry, where it cannot protect (§15 C3)"
        )
    return ticks


class StopBook:
    """Where synthetic stops live (§4, V33). Satisfies the frozen `StopBookPort`.

    SYNCHRONOUS throughout, for the reason the seam gives: an `async def maintain`
    would put a suspension point between reading a price and ratcheting the stop
    that price implies, so a fill could be serviced in between and the stop would
    ratchet against a position that no longer exists — the fill-vs-tick race §5
    eliminates by construction.

    Deliberately NOT a subclass of `StopBookPort`: a `Protocol`'s method bodies
    are docstrings, so inheriting it means a verb this class forgot to override
    returns `None` silently. Conformance is proven by comparing signatures against
    the port instead (see `test_stops.py`), which is a measurement, not a claim.

    NO PLANE-1 SINK. Per-tick ratchets are not logged (§12.10, A4); this book has
    nothing to log with, which is what makes "not logged" a property of the type
    rather than a rule the caller is trusted to keep.
    """

    def __init__(self, tick_size: Mapping[str, float]) -> None:
        #: Per-symbol price value of one tick. An instrument constant, boot-loaded
        #: (§12A lifecycle: restart-only). Copied so a later mutation of the
        #: caller's mapping cannot silently re-scale a live stop.
        self._tick_size: dict[str, float] = dict(tick_size)
        #: client_order_id -> the live stop. The book's whole state.
        self._stops: dict[str, StopState] = {}
        #: symbol -> the client_order_ids holding a stop on it, so `maintain` and
        #: `breached` touch only the stops a tick can move — §11's hot path is
        #: cache reads and arithmetic, never a scan of the whole book.
        self._by_symbol: dict[str, set[str]] = {}

    # -- the port -----------------------------------------------------------

    def arm(
        self,
        fill_price: float,
        order: ProposedOrder,
        *,
        trail_ticks: int | None = None,
    ) -> StopState:
        """Convert distance → price ONCE, at the confirmed fill (§4, A1).

        `trail_ticks` carries the trailing stop's second distance, which the
        frozen `ProposedOrder` cannot express (see the module docstring). It is
        ignored for a FIXED order and REQUIRED for a TRAILING one; a trailing arm
        without it is denied rather than having a trail distance invented.
        """
        if not math.isfinite(fill_price) or fill_price <= 0.0:
            raise InvalidStopIntent(
                f"{order.client_order_id}: fill price {fill_price!r} is not a "
                "positive finite number — a stop cannot be anchored against it"
            )
        initial = _valid_distance(order.client_order_id, order.stop_ticks, "stop_ticks")
        tick = self._tick_size.get(order.symbol)
        if tick is None or not math.isfinite(tick) or tick <= 0.0:
            raise UntradableSymbol(
                f"{order.client_order_id}: symbol {order.symbol!r} has no positive "
                f"tick size (got {tick!r}) — its tick distance has no price scale, "
                "so it is not-tradable (§4:198)"
            )
        if order.client_order_id in self._stops:
            raise DuplicateStop(
                f"{order.client_order_id}: a stop is already armed for this order — "
                "a stop is converted ONCE at the confirmed fill (§4)"
            )
        trail = self._trail_distance(order, trail_ticks)
        sign = _sign(order.side)
        level = fill_price - sign * initial * tick
        state = StopState(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            mode=order.stop_mode,
            initial_distance_ticks=initial,
            trail_distance_ticks=trail,
            anchor=fill_price,
            level=level,
            high_water=fill_price,
            activated=False,
        )
        self._stops[state.client_order_id] = state
        self._by_symbol.setdefault(state.symbol, set()).add(state.client_order_id)
        return state

    def maintain(self, symbol: str, price: float) -> tuple[StopState, ...]:
        """Ratchet every trailing stop this price moves (§4, A3). Never logged.

        Reads the tick price and does arithmetic — §11's hot path. A FIXED stop is
        never moved. High-water advances are always persisted (a later tick's
        trail is measured from them); the returned tuple is only the stops whose
        `level` actually ratcheted, which is the precise meaning of "moved".
        """
        moved: list[StopState] = []
        for coid in tuple(self._by_symbol.get(symbol, ())):
            state = self._stops[coid]
            if state.mode is not StopMode.TRAILING:
                continue
            updated = self._ratchet(state, price, self._tick_size[state.symbol])
            if updated is None:
                continue
            self._stops[coid] = updated
            if updated.level != state.level:
                moved.append(updated)
        return tuple(moved)

    def breached(self, symbol: str, price: float) -> tuple[StopState, ...]:
        """Stops this price has taken out (§4). Reads, never fires.

        Returns the breached stops so the Limiter can fire the protective flatten;
        it does NOT drop them (that is `forget`, called after the flatten
        confirms). Reading and firing are separate so a read can never place an
        order — the §12.1 prohibition, kept structural.
        """
        out: list[StopState] = []
        for coid in tuple(self._by_symbol.get(symbol, ())):
            state = self._stops[coid]
            if _breached(_sign(state.side), price, state.level):
                out.append(state)
        return tuple(out)

    def forget(self, client_order_id: str) -> None:
        """Drop a stop whose position is closed (§4). Loud on an unknown id."""
        state = self._stops.pop(client_order_id, None)
        if state is None:
            raise UnknownStop(
                f"{client_order_id}: no stop is armed for this order — a forget for "
                "a stop that does not exist is a keying defect, not a no-op"
            )
        holders = self._by_symbol.get(state.symbol)
        if holders is not None:
            holders.discard(client_order_id)
            if not holders:
                del self._by_symbol[state.symbol]

    # -- readable state -----------------------------------------------------

    def get(self, client_order_id: str) -> StopState | None:
        """The live stop for one order, or None. For maintenance and evidence."""
        return self._stops.get(client_order_id)

    def stops(self) -> tuple[StopState, ...]:
        """Every live stop, ordered by client_order_id. Never the hot path."""
        return tuple(self._stops[coid] for coid in sorted(self._stops))

    # -- internals ----------------------------------------------------------

    def _trail_distance(self, order: ProposedOrder, trail_ticks: int | None) -> int:
        """The trailing second distance, or 0 for a fixed stop.

        FIXED ignores `trail_ticks` (a fixed stop has no trail). TRAILING requires
        it and validates it exactly like the initial distance — see the module
        docstring on why it cannot be defaulted from the initial distance.
        """
        if order.stop_mode is not StopMode.TRAILING:
            return 0
        if trail_ticks is None:
            raise InvalidStopIntent(
                f"{order.client_order_id}: a trailing stop needs a trail distance, "
                "which the frozen ProposedOrder does not carry; arm() was called "
                "without trail_ticks. Denying rather than inventing trail=initial — "
                "the strategy chooses the trail per signal (§4:187)"
            )
        return _valid_distance(order.client_order_id, trail_ticks, "trail_ticks")

    @staticmethod
    def _ratchet(state: StopState, price: float, tick: float) -> StopState | None:
        """One trailing tick. Returns a new `StopState`, or None if nothing changed.

        The `activated` field is a LATCH, respected exactly as the seam requires:
        activation is decided against the stored `level` (initially the initial
        stop), NEVER against the current price, so a retrace cannot de-activate a
        stop that has begun trailing. High-water is monotone in the favourable
        direction, so the trail level it implies — and therefore `level` — never
        gives ground back.
        """
        sign = _sign(state.side)
        high_water = (
            price if sign * price > sign * state.high_water else state.high_water
        )
        trail_level = high_water - sign * state.trail_distance_ticks * tick
        activated = state.activated
        level = state.level
        if _tighter(sign, trail_level, level):
            # Before activation this is the moment the trail first sits tighter
            # than the initial stop (§4 activation); after it, an ordinary ratchet.
            level = trail_level
            activated = True
        if high_water == state.high_water and level == state.level:
            return None
        return dataclasses.replace(
            state, high_water=high_water, level=level, activated=activated
        )
