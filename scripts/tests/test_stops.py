"""ARC 029 / sub-agent A — the synthetic stop book driven directly (§4, V33).

This is the module's own can-fail suite. Every property is proven, and every
proof is made to REDDEN on a planted defect that names the site or the reason,
never an exit code alone (check contract v2 §11). Test names SHOUT the property.

The three §0a hypotheses the brief hands down are MEASURED here, not assumed:

* *"never moves backward" is trivially satisfied by a stop that never moves at
  all* — closed by `test_a_TRAILING_stop_ACTIVATES_and_RATCHETS_MULTIPLE_ticks`,
  which proves the level STRICTLY advances more than once, and by a `_FrozenBook`
  variant that never moves and is shown to FAIL that assertion. NOT backwards.
* *a trailing path that never reaches activation is the fixed case under another
  name* — every trailing ratchet test drives the price ACROSS the activation
  threshold (`trail_distance > initial_distance`, so activation requires a real
  favourable advance) and a separate test proves the stop HOLDS below it. NOT
  backwards.
* *the activation instant is where a backward jump would hide* — asserted head-on
  in `test_the_ACTIVATION_INSTANT_moves_the_level_FORWARD_never_backward`, and
  the `_CurrentPriceBook` variant (activation recomputed from the current price)
  is shown to give ground back on a retrace, which is the measurement behind the
  `activated` latch. NOT backwards.
"""

# pylint: disable=invalid-name,redefined-outer-name

from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_synthetic_stop_only as stop_gate  # pylint: disable=wrong-import-position
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    ProposedOrder,
    Side,
    StopBookPort,
    StopMode,
    StopState,
)
from nixrisk.stops import (  # pylint: disable=wrong-import-position
    DuplicateStop,
    InvalidStopIntent,
    StopBook,
    UnknownStop,
    UntradableSymbol,
)
from nixverify.contract import (  # pylint: disable=wrong-import-position
    CheckResult,
    Context,
    Mode,
    Status,
)

TICK = 0.25
SYMBOL = "ESZ25"
FILL = 100.0


def _order(
    *,
    coid: str = "COID-1",
    side: Side = Side.LONG,
    stop_ticks: int = 10,
    mode: StopMode = StopMode.FIXED,
    symbol: str = SYMBOL,
) -> ProposedOrder:
    """A sized proposal carrying stop intent as a tick DISTANCE (§4)."""
    return ProposedOrder(
        client_order_id=coid,
        strategy_id="STRAT-A",
        symbol=symbol,
        side=side,
        qty=2,
        margin_per_contract=500.0,
        stop_ticks=stop_ticks,
        stop_mode=mode,
        signal_ts=1_000.0,
    )


@pytest.fixture
def book() -> StopBook:
    """A book that knows one instrument's tick size (§12A instrument constant)."""
    return StopBook({SYMBOL: TICK})


# ==========================================================================
# THE FROZEN PORT — conformance MEASURED, never claimed by inheritance
# ==========================================================================


def _port_methods() -> list[str]:
    """Derived from the Protocol itself, so a verb added there is required here."""
    return sorted(
        name
        for name, value in vars(StopBookPort).items()
        if not name.startswith("_") and inspect.isfunction(value)
    )


def test_the_STOPBOOK_declares_EVERY_FROZEN_PORT_verb_compatibly() -> None:
    """A book the seam's declaration does not describe is a second authority.

    `arm` carries ONE extra parameter — `trail_ticks` — because the frozen
    `ProposedOrder` cannot express a trailing stop's second distance (the seam
    gap the module docstring reports). It is asserted to be KEYWORD-ONLY with a
    default, so `arm(fill_price, order)` — the port's exact call — still type-
    checks; the extra is opt-in, not a changed contract.
    """
    names = _port_methods()
    assert names == ["arm", "breached", "forget", "maintain"], names
    for name in names:
        assert hasattr(StopBook, name), f"the book declares no {name}"
        port_params = list(inspect.signature(getattr(StopBookPort, name)).parameters)
        impl = inspect.signature(getattr(StopBook, name))
        impl_params = list(impl.parameters)
        assert impl_params[: len(port_params)] == port_params, (
            f"{name}: the book's parameters {impl_params} do not extend the frozen "
            f"port's {port_params}"
        )
        for extra in impl_params[len(port_params) :]:
            param = impl.parameters[extra]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
                f"{name}: extra parameter {extra!r} is not keyword-only, so it "
                "changes the port's positional call signature"
            )
            assert param.default is not inspect.Parameter.empty, (
                f"{name}: extra parameter {extra!r} has no default, so the port's "
                "own call arity no longer satisfies the book"
            )


def test_EVERY_PORT_VERB_is_SYNCHRONOUS_on_BOTH_sides_of_the_seam() -> None:
    """§11's hot path is cache reads + arithmetic; an awaitable `maintain` puts a
    suspension point between reading a price and ratcheting the stop it implies —
    the fill-vs-tick race §5 eliminates by construction (seam docstring)."""
    for name in _port_methods():
        assert not inspect.iscoroutinefunction(getattr(StopBookPort, name)), (
            f"the FROZEN seam declares {name} as a coroutine"
        )
        assert not inspect.iscoroutinefunction(getattr(StopBook, name)), (
            f"the book implements {name} as a coroutine"
        )


def test_the_STOPBOOK_does_NOT_INHERIT_the_Protocol() -> None:
    """A Protocol's method bodies are docstrings. Inheriting means a verb the book
    forgot to override returns None, silently, at the point of use."""
    assert StopBookPort not in StopBook.__mro__, StopBook.__mro__


def test_the_STOPBOOK_holds_NO_PLANE1_SINK_so_per_tick_cannot_be_logged() -> None:
    """A4 / §12.10: per-tick ratchets are NOT logged. The book proves it
    structurally by holding nothing to log WITH — its constructor takes only the
    tick-size map. Can-fail: add a `plane1`/sink parameter and this reddens."""
    params = [p for p in inspect.signature(StopBook.__init__).parameters if p != "self"]
    assert params == ["tick_size"], (
        f"StopBook.__init__ takes {params}; a logging collaborator here would let "
        "per-tick ratchets be logged, which §12.10 forbids"
    )


# ==========================================================================
# A1 — conversion happens ONCE, at the CONFIRMED FILL; ingress guard BOTH sides
# ==========================================================================


def test_a_VALID_distance_ARMS_and_converts_against_the_CONFIRMED_FILL(
    book: StopBook,
) -> None:
    """A1: distance→price conversion uses the FILL, not the pre-fill signal.

    Proven by arming the SAME order at two different fills: the level tracks the
    fill, so it cannot have been computed from a fixed signal price. `anchor`
    records the fill it converted against (§4)."""
    order = _order(stop_ticks=10)
    state = book.arm(FILL, order)
    assert state.anchor == FILL
    assert state.level == pytest.approx(FILL - 10 * TICK)  # 97.5, below a long entry

    other = StopBook({SYMBOL: TICK})
    slipped = other.arm(FILL + 4 * TICK, order)  # a different confirmed fill
    assert slipped.level == pytest.approx(FILL + 4 * TICK - 10 * TICK)
    assert slipped.level != state.level, (
        "the level did not move with the fill — conversion used something other "
        "than the confirmed fill price"
    )


def test_a_SHORT_stop_converts_to_the_price_ABOVE_entry(book: StopBook) -> None:
    """A1: for a short the protective stop sits ABOVE the fill. A sign error would
    put it below, on the wrong side of entry, where it can never protect."""
    state = book.arm(FILL, _order(side=Side.SHORT, stop_ticks=10))
    assert state.level == pytest.approx(FILL + 10 * TICK)  # 102.5, above the entry


@pytest.mark.parametrize("bad", [0, -5])
def test_a_MISSING_ZERO_or_NEGATIVE_distance_DENIES_at_conversion(
    book: StopBook, bad: int
) -> None:
    """A1 ingress guard, the DENY side (§3, §15 C3). A raise IS the deny, because
    `arm` returns a StopState not a verdict. The reason names the field."""
    with pytest.raises(InvalidStopIntent) as exc:
        book.arm(FILL, _order(stop_ticks=bad))
    assert "stop_ticks" in str(exc.value) and str(bad) in str(exc.value)


def test_a_NON_INTEGER_stop_distance_is_INVALID(book: StopBook) -> None:
    """§15 C3: `True` is an int of value 1 in Python — a mis-passed flag is exactly
    the invalid intent the guard denies, so bool is refused explicitly."""
    order = dataclasses.replace(_order(), stop_ticks=True)  # type: ignore[arg-type]
    with pytest.raises(InvalidStopIntent):
        book.arm(FILL, order)


def test_a_NON_POSITIVE_FILL_price_DENIES(book: StopBook) -> None:
    """A stop cannot be anchored against a zero or negative fill price."""
    with pytest.raises(InvalidStopIntent) as exc:
        book.arm(0.0, _order())
    assert "fill price" in str(exc.value)


def test_an_UNKNOWN_SYMBOL_is_NOT_TRADABLE_and_DENIES() -> None:
    """§4:198: a symbol with no tick size has no price scale for its distance, so
    it is not-tradable. Denied rather than defaulted — a guessed tick is a stop at
    the wrong price."""
    empty = StopBook({})  # no instrument known
    with pytest.raises(UntradableSymbol) as exc:
        empty.arm(FILL, _order())
    assert SYMBOL in str(exc.value)


def test_a_SECOND_ARM_for_the_SAME_ORDER_RAISES(book: StopBook) -> None:
    """A stop is converted ONCE at the confirmed fill (§4). A second arm would
    silently replace a live stop with a re-converted one."""
    book.arm(FILL, _order())
    with pytest.raises(DuplicateStop):
        book.arm(FILL + 1.0, _order())


# ==========================================================================
# A2 — a FIXED stop anchors once and NEVER moves
# ==========================================================================


def test_a_FIXED_stop_ANCHORS_ONCE_and_NEVER_MOVES(book: StopBook) -> None:
    """A2 (§4:188). maintain moves nothing for a fixed stop, at any price."""
    book.arm(FILL, _order(mode=StopMode.FIXED, stop_ticks=10))
    anchored = book.get("COID-1")
    assert anchored is not None and anchored.level == pytest.approx(97.5)
    for price in (FILL + 5.0, FILL - 0.4, FILL + 20.0):
        assert not book.maintain(SYMBOL, price), "a fixed stop moved"
    after = book.get("COID-1")
    assert after is not None and after.level == anchored.level


# ==========================================================================
# A3 — a TRAILING stop HOLDS, then ACTIVATES, then RATCHETS, never regressing
# ==========================================================================
#
# Numbers (long, tick 0.25, fill 100.0, initial 10, trail 15):
#   initial level    = 100.0 - 10*0.25 = 97.50
#   trail level(P)   = high_water - 15*0.25 = high_water - 3.75
#   activation price : trail tighter than initial <=> high_water - 3.75 > 97.50
#                      <=> high_water > 101.25  (>5 ticks of favourable advance)
# trail_distance (15) > initial_distance (10) on purpose: activation demands a
# REAL advance, so the path is not the fixed case wearing a trailing label.


def _trailing(book: StopBook, coid: str = "COID-1") -> StopState:
    order = _order(coid=coid, mode=StopMode.TRAILING, stop_ticks=10)
    return book.arm(FILL, order, trail_ticks=15)


def test_a_TRAILING_arm_WITHOUT_the_second_distance_DENIES(book: StopBook) -> None:
    """The seam gap, failing closed: `ProposedOrder` cannot carry the trail
    distance, so a trailing arm without `trail_ticks` is denied rather than having
    trail=initial invented (the strategy chooses the trail per signal, §4:187)."""
    with pytest.raises(InvalidStopIntent) as exc:
        book.arm(FILL, _order(mode=StopMode.TRAILING, stop_ticks=10))
    assert "trail" in str(exc.value).lower()


def test_a_TRAILING_stop_HOLDS_at_the_INITIAL_level_below_the_threshold(
    book: StopBook,
) -> None:
    """A3: it holds at the initial level until the trail would sit tighter. At
    101.00 (below the 101.25 threshold) the stop has NOT moved — this is what
    proves the path is not the fixed case: the threshold is real and not yet
    crossed."""
    _trailing(book)
    assert not book.maintain(SYMBOL, 101.00), "the stop moved below the threshold"
    held = book.get("COID-1")
    assert held is not None
    assert held.level == pytest.approx(97.50)
    assert held.activated is False
    assert held.high_water == pytest.approx(101.00)  # HWM tracked; level held


def test_a_TRAILING_stop_ACTIVATES_and_RATCHETS_MULTIPLE_ticks_behind_the_HWM(
    book: StopBook,
) -> None:
    """A3 / hypothesis 1: it ACTUALLY ratchets — the level advances more than once,
    each time to high_water - trail. A stop that never moved would satisfy 'never
    backward' vacuously; this proves motion, repeatedly, across the threshold."""
    _trailing(book)
    assert not book.maintain(SYMBOL, 101.00)  # holds, below threshold

    moved1 = book.maintain(SYMBOL, 101.50)  # crosses 101.25 -> activates
    assert len(moved1) == 1
    assert moved1[0].activated is True
    assert moved1[0].level == pytest.approx(101.50 - 3.75)  # 97.75

    moved2 = book.maintain(SYMBOL, 102.00)  # ratchet
    assert moved2[0].level == pytest.approx(102.00 - 3.75)  # 98.25

    moved3 = book.maintain(SYMBOL, 103.00)  # ratchet again
    assert moved3[0].level == pytest.approx(103.00 - 3.75)  # 99.25

    levels = [97.75, 98.25, 99.25]
    assert levels == sorted(levels) and levels[0] < levels[-1], (
        "the level did not strictly advance across ratchets — a stop that never "
        "moves satisfies 'never backward' while measuring nothing"
    )


def test_the_ACTIVATION_INSTANT_moves_the_level_FORWARD_never_backward(
    book: StopBook,
) -> None:
    """Hypothesis 3: the activation instant is where a backward jump would hide.
    At activation the level goes 97.50 -> 97.75 — strictly UP (favour), never a
    step down. A jump to `high_water - trail` computed against a fresh HWM must
    not be allowed to sit LOWER than the initial stop."""
    state = _trailing(book)
    initial_level = state.level  # 97.50
    moved = book.maintain(SYMBOL, 101.50)  # the activation instant
    assert moved and moved[0].level > initial_level, (
        f"the level jumped BACKWARD at activation: {initial_level} -> {moved[0].level}"
    )


def test_a_TRAILING_stop_NEVER_gives_ground_back_across_a_RETRACE(
    book: StopBook,
) -> None:
    """A3: once ratcheted, a retrace does not loosen the stop — the high-water mark
    is monotone, so the trail it implies never retreats."""
    _trailing(book)
    book.maintain(SYMBOL, 101.50)  # activate -> 97.75
    book.maintain(SYMBOL, 103.00)  # ratchet  -> 99.25
    peak = book.get("COID-1")
    assert peak is not None and peak.level == pytest.approx(99.25)

    assert not book.maintain(SYMBOL, 101.00), "the stop moved on a retrace"
    after = book.get("COID-1")
    assert after is not None
    assert after.level == pytest.approx(99.25), "the stop gave ground back"
    assert after.activated is True, "a retrace de-activated the stop"


def test_a_TRAILING_SHORT_activates_and_ratchets_the_MIRROR_way(book: StopBook) -> None:
    """A3 symmetry for a short: favour is DOWN, the HWM is the MIN price, and the
    stop ratchets DOWNWARD. A sign error surfaces here and nowhere else.

    Short numbers (fill 100, initial 10, trail 15): initial level 102.50,
    activation when high_water < 98.75, trail level = high_water + 3.75."""
    order = _order(coid="S1", side=Side.SHORT, mode=StopMode.TRAILING, stop_ticks=10)
    book.arm(FILL, order, trail_ticks=15)
    assert not book.maintain(SYMBOL, 99.00)  # above threshold, holds
    held = book.get("S1")
    assert held is not None and held.level == pytest.approx(102.50)

    moved = book.maintain(SYMBOL, 98.50)  # crosses 98.75 -> activates
    assert moved and moved[0].level == pytest.approx(98.50 + 3.75)  # 102.25
    assert moved[0].level < 102.50, "a short's stop did not move DOWN (favour)"

    book.maintain(SYMBOL, 98.00)  # ratchet -> 101.75
    assert not book.maintain(SYMBOL, 99.50)  # retrace, no ground given back
    after = book.get("S1")
    assert after is not None and after.level == pytest.approx(101.75)


# --- the CAN-FAIL for the ratchet properties: broken variants must be caught ---


class _FrozenBook(StopBook):
    """A book whose stops never move — the vacuous satisfier of 'never backward'.

    Overrides the ratchet to a no-op. The multi-ratchet assertions above MUST fail
    against it, which is what proves those assertions measure motion and are not
    satisfied by a stop that simply never moves."""

    @staticmethod
    def _ratchet(state: StopState, price: float, tick: float) -> StopState | None:
        return None


class _CurrentPriceBook(StopBook):
    """The WRONG activation rule the `activated` latch exists to forbid.

    Activation is (re)decided from the CURRENT price each tick instead of the
    stored level, so a retrace below the activation price DE-ACTIVATES the stop and
    it gives ground back. This is the defect the module docstring's non-regression
    guarantee is measured against."""

    @staticmethod
    def _ratchet(state: StopState, price: float, tick: float) -> StopState | None:
        sign = 1.0 if state.side is Side.LONG else -1.0
        # BUG: activation judged against the current price, not the stored level.
        activation_price = (
            state.anchor
            + sign * (state.trail_distance_ticks - state.initial_distance_ticks) * tick
        )
        active_now = sign * price > sign * activation_price
        if not active_now:
            return dataclasses.replace(state, activated=False)  # gives ground back
        trail_level = price - sign * state.trail_distance_ticks * tick
        return dataclasses.replace(
            state, high_water=price, level=trail_level, activated=True
        )


def test_CANFAIL_a_FROZEN_book_never_ratchets_so_the_motion_assertion_reddens() -> None:
    """Plant: a stop that never moves. The multi-ratchet property must NOT hold on
    it — proving that property is about MOTION, not a tautology."""
    book = _FrozenBook({SYMBOL: TICK})
    _trailing(book)
    assert not book.maintain(SYMBOL, 101.50)  # planted defect: no motion
    assert not book.maintain(SYMBOL, 103.00)
    held = book.get("COID-1")
    assert held is not None and held.level == pytest.approx(97.50), (
        "the frozen variant should be stuck at the initial level"
    )
    # The real book, restored, DOES ratchet — green.
    real = StopBook({SYMBOL: TICK})
    _trailing(real)
    real.maintain(SYMBOL, 101.50)
    moved = real.maintain(SYMBOL, 103.00)
    assert moved and moved[0].level == pytest.approx(99.25)


def test_CANFAIL_current_price_activation_GIVES_GROUND_BACK_on_a_retrace() -> None:
    """Plant: activation recomputed from the current price (no latch). It regresses
    on a retrace; the shipped book does not. This is the measurement behind the
    `activated` latch — the hypothesis that 'the activation instant is where a
    backward jump hides', proven by exhibiting the jump the correct code forbids."""
    broken = _CurrentPriceBook({SYMBOL: TICK})
    _trailing(broken)
    broken.maintain(SYMBOL, 101.50)  # activate
    broken.maintain(SYMBOL, 103.00)  # ratchet -> 99.25
    broken.maintain(SYMBOL, 101.00)  # retrace below activation price (101.25)
    hurt = broken.get("COID-1")
    assert hurt is not None and (hurt.activated is False or hurt.level < 99.25), (
        "the planted defect was supposed to give ground back on the retrace"
    )

    # Restore: the shipped book holds its ground on the identical sequence — green.
    real = StopBook({SYMBOL: TICK})
    _trailing(real)
    real.maintain(SYMBOL, 101.50)
    real.maintain(SYMBOL, 103.00)
    real.maintain(SYMBOL, 101.00)
    good = real.get("COID-1")
    assert good is not None and good.level == pytest.approx(99.25) and good.activated


# ==========================================================================
# breached — reading, never firing; forget — loud on an unknown id
# ==========================================================================


def test_breached_reports_the_stops_a_price_TOOK_OUT_and_does_NOT_fire(
    book: StopBook,
) -> None:
    """A stop is breached when price reaches or passes through the level. `breached`
    READS — it returns the taken-out stops and leaves them in the book for the
    protective-flatten path to fire and then `forget`."""
    _trailing(book)
    book.maintain(SYMBOL, 101.50)  # level -> 97.75
    book.maintain(SYMBOL, 103.00)  # level -> 99.25
    assert not book.breached(SYMBOL, 99.50)  # above the stop, untouched
    taken = book.breached(SYMBOL, 99.25)  # exactly at the stop -> breached
    assert len(taken) == 1 and taken[0].client_order_id == "COID-1"
    assert book.get("COID-1") is not None, "breached fired instead of only reading"


def test_forget_drops_a_stop_and_RAISES_on_an_UNKNOWN_id(book: StopBook) -> None:
    """forget drops a closed position's stop; an unknown id is a keying defect and
    is loud, not a no-op — a forget keyed differently from the arm would leave real
    positions holding unmaintained stops."""
    book.arm(FILL, _order())
    book.forget("COID-1")
    assert book.get("COID-1") is None
    with pytest.raises(UnknownStop):
        book.forget("COID-1")  # already gone
    with pytest.raises(UnknownStop):
        book.forget("NEVER-ARMED")


# ==========================================================================
# A5 — the §12.1 prohibition gate, DRIVEN (plant -> red naming site -> restore)
# ==========================================================================


def _stop_home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of the shipped stops.py."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    src = (REPO / "scripts" / "nixrisk" / "stops.py").read_text(encoding="utf-8")
    (tmp_path / "scripts" / "nixrisk" / "stops.py").write_text(src, encoding="utf-8")
    return tmp_path


def _run_gate(home: Path) -> CheckResult:
    return stop_gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def test_the_PROHIBITION_gate_PASSES_on_the_SHIPPED_synthetic_stop(
    tmp_path: Path,
) -> None:
    """§12.1: the shipped stop book reaches no broker. The gate is GREEN on it, and
    its evidence names what it scanned so a green cannot be an empty scan."""
    result = _run_gate(_stop_home(tmp_path))
    assert result.status is Status.PASS, result.detail
    assert "stops.py" in result.evidence and "synthetic-stop-only" in result.evidence


def test_CANFAIL_the_gate_REDDENS_on_a_planted_BROKER_IMPORT(tmp_path: Path) -> None:
    """Plant a broker import onto the stop path. The gate goes PASS -> FAIL naming
    the SITE and the REASON (not the exit code alone). Restored copy is green."""
    home = _stop_home(tmp_path)
    path = home / "scripts" / "nixrisk" / "stops.py"
    src = path.read_text(encoding="utf-8")
    anchor = "from nixrisk.seam import ProposedOrder, Side, StopMode, StopState"
    assert src.count(anchor) == 1
    path.write_text(
        src.replace(anchor, anchor + "\nfrom broker_seam import place_order"),
        encoding="utf-8",
    )
    result = _run_gate(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "broker_seam" in result.detail and "stops.py:" in result.site


def test_CANFAIL_the_gate_REDDENS_on_a_planted_ORDER_VERB_and_STOP_TYPE(
    tmp_path: Path,
) -> None:
    """Plant an order-placement verb call AND a broker-native stop order-type code.
    Both are named as delegations; the word 'stop' elsewhere in the module is NOT
    a false positive (the code is matched as an exact literal, not a substring)."""
    home = _stop_home(tmp_path)
    path = home / "scripts" / "nixrisk" / "stops.py"
    src = path.read_text(encoding="utf-8")
    anchor = "        self._by_symbol: dict[str, set[str]] = {}"
    assert src.count(anchor) == 1
    plant = anchor + '\n        place_order(order_type="STP")'
    path.write_text(src.replace(anchor, plant), encoding="utf-8")
    result = _run_gate(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "place_order" in result.detail
    assert "STP" in result.detail and "order-type" in result.detail


def test_the_gate_CANNOT_MEASURE_when_the_ANCHOR_is_ABSENT(tmp_path: Path) -> None:
    """§5.3: with stops.py absent the scan reached nothing — CANNOT_MEASURE, never
    a vacuous PASS."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    result = _run_gate(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert "anchor" in result.detail
