"""ARC 029 / sub-agent C — the net-liq survival watch driven directly.

Owns §6.5's standing watch, §15 C2's net-liq/cash non-conflation, §12.9's
Critical alert, and §4's broker-authoritative reconcile with the
monotonic-by-source guard. Conformance to the FROZEN ``SurvivalWatchPort`` is
MEASURED here, never claimed by inheritance.

**Every control asserts the REASON** — the message, the tier, the field, or the
arithmetic — never a bare boolean or an exception type alone (check contract v2
§11). Each property is made CAN-FAIL: the fault is planted, the named site
reddens, the fault is restored, and the property goes green — and where the
module has no external gate to redden, the discriminating fault is one the test
would catch (a cash-based watch, a stale-poll-applied guard), shown by a paired
assertion that the wrong implementation gives the OPPOSITE verdict.

§7.12, the standing question — *what would have to be true for a control here to
pass while measuring nothing?* Answered per-test. The one this whole file exists
to close: a reading where ``net_liq == cash`` makes the watch's verdict identical
whether it reads net-liq or cash, so a suite built only on equal readings proves
nothing about §15 C2. Every distinction test below drives the two APART.
"""
# pylint: disable=invalid-name,redefined-outer-name,too-few-public-methods

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.seam import (  # pylint: disable=wrong-import-position
    FlattenTrigger,
    PositionRow,
    PositionState,
    SurvivalReading,
    SurvivalWatchPort,
)
from nixrisk.survival import (  # pylint: disable=wrong-import-position
    BREACH_EVENT,
    DRIFT_EVENT,
    Alert,
    AlertTier,
    BrokerReading,
    KnobError,
    SurvivalNotReady,
    SurvivalWatch,
    SurvivalWatchError,
)

# --------------------------------------------------------------------------
# Test doubles — a flatten executor and an alert sink that record, not act
# --------------------------------------------------------------------------


class RecordingFlatten:
    """A ``FlattenExecutor`` that records every fire. Zero wire, by construction."""

    def __init__(self) -> None:
        self.fires: list[tuple[FlattenTrigger, str]] = []

    def flatten(self, trigger: FlattenTrigger, reason: str) -> None:
        """Record the trigger and reason. No I/O, no bus, no socket."""
        self.fires.append((trigger, reason))


class RecordingAlerts:
    """An ``AlertSink`` that keeps every alert so the TIER can be asserted."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def emit(self, alert: Alert) -> None:
        """Keep the alert; the tests read ``alerts`` directly."""
        self.alerts.append(alert)

    def of(self, tier: AlertTier) -> list[Alert]:
        """Every alert of one §12.9 tier, in arrival order."""
        return [a for a in self.alerts if a.tier is tier]


class ScriptedBroker:
    """A ``BrokerReconcilePort`` that returns queued readings and COUNTS polls.

    The poll count is the instrument for "uniform on every reconciliation event":
    a reconcile that skipped the broker on some events would leave the count below
    the number of reconcile calls.
    """

    def __init__(self, readings: list[BrokerReading]) -> None:
        self._readings = list(readings)
        self.polls = 0

    def poll(self) -> BrokerReading:
        """Hand back the next scripted reading and count the call."""
        self.polls += 1
        if not self._readings:
            raise AssertionError("broker polled more times than scripted")
        return self._readings.pop(0)


def pos(margin: float, state: PositionState = PositionState.OPEN) -> PositionRow:
    """One position row carrying ``margin`` in ``state``."""
    return PositionRow(
        trade_id="T-1",
        symbol="ESZ6",
        strategy_id="strat-1",
        size=1,
        margin=margin,
        state=state,
    )


def watch(
    *,
    safety_pad: float = 0.10,
    broker: ScriptedBroker | None = None,
    tolerance: float = 1.0,
) -> tuple[SurvivalWatch, RecordingFlatten, RecordingAlerts, ScriptedBroker]:
    """A watch with recording collaborators and a fixed clock."""
    flat = RecordingFlatten()
    alerts = RecordingAlerts()
    brk = broker if broker is not None else ScriptedBroker([])
    sw = SurvivalWatch(
        safety_pad=safety_pad,
        broker=brk,
        flatten=flat,
        alert=alerts,
        tolerance=tolerance,
        clock=lambda: 1000.0,
    )
    return sw, flat, alerts, brk


# --------------------------------------------------------------------------
# THE FROZEN PORT — conformance MEASURED, never claimed by inheritance
# --------------------------------------------------------------------------


def _port_methods() -> list[str]:
    """Derived from the Protocol itself, so a method added there becomes required."""
    return sorted(
        name
        for name, value in vars(SurvivalWatchPort).items()
        if not name.startswith("_") and inspect.isfunction(value)
    )


def test_the_WATCH_matches_the_FROZEN_PORT_signature_for_signature() -> None:
    """A watch the seam's declaration does not describe is a second authority.

    §7.12: this passes while measuring nothing only if the port declared no
    verbs — asserted against.
    """
    names = _port_methods()
    assert names == ["floor", "read"], f"the port's verbs changed: {names}"
    for name in names:
        port = inspect.signature(getattr(SurvivalWatchPort, name))
        assert hasattr(SurvivalWatch, name), f"the watch declares no {name}"
        impl = inspect.signature(getattr(SurvivalWatch, name))
        assert impl == port, (
            f"{name}: the watch declares {impl} and the frozen port declares {port}"
        )


def test_EVERY_PORT_VERB_is_SYNCHRONOUS_on_BOTH_SIDES_of_the_seam() -> None:
    """§14: the protective path fires by a direct call and needs no running loop.

    A coroutine ``read`` would need a loop to make progress, which is the wire
    dependency §14 forbids the exit from having.
    """
    for name in _port_methods():
        assert not inspect.iscoroutinefunction(getattr(SurvivalWatchPort, name)), name
        assert not inspect.iscoroutinefunction(getattr(SurvivalWatch, name)), (
            f"the watch implements {name} as a coroutine — the exit path may not "
            "depend on a running event loop (§14)"
        )


def test_the_WATCH_does_NOT_INHERIT_the_Protocol() -> None:
    """Inheriting the Protocol would let a forgotten verb return None silently."""
    assert SurvivalWatchPort not in SurvivalWatch.__mro__, SurvivalWatch.__mro__


# --------------------------------------------------------------------------
# C1 / §15 C2 — SURVIVAL ON NET-LIQ, SIZING ON CASH. Drive them APART.
# --------------------------------------------------------------------------


def test_the_EQUAL_reading_proves_NOTHING_and_this_test_says_so() -> None:
    """§0a hypothesis, MEASURED: with net_liq == cash the two watches agree.

    This is the vacuity the rest of C1 exists to escape, made explicit. A reading
    where ``net_liq == cash`` yields the SAME breach verdict whether the predicate
    reads net-liq or cash — so any test built on it measures nothing about the
    distinction. Demonstrated, not assumed: below, the net-liq predicate and the
    cash predicate return the identical bool on an equal reading, for BOTH a
    breaching and a non-breaching floor.
    """
    for net_eq_cash, floor in ((100.0, 120.0), (100.0, 80.0)):
        reading = SurvivalReading(
            net_liq=net_eq_cash,
            cash=net_eq_cash,
            unrealized=0.0,
            floor=floor,
            taken_at=0.0,
        )
        net_liq_verdict = reading.net_liq < reading.floor
        cash_verdict = reading.cash < reading.floor
        assert net_liq_verdict == cash_verdict, (
            "an equal reading cannot distinguish a net-liq watch from a cash one"
        )


def test_UNREALIZED_LOSS_fires_on_NET_LIQ_while_CASH_stays_comfortable() -> None:
    """§15 C2: net-liq erodes with price, cash does not. Floor placed BETWEEN them.

    An open position at an unrealized LOSS drops net-liq below cash. With the floor
    set so ``net_liq < floor <= cash``, the watch MUST fire (it tracks net-liq) and
    ``sizing_liquidity`` MUST still read the comfortable cash. **Can-fail:** the
    paired assertion shows a cash-based watch (``cash < floor``) would NOT fire on
    this same reading — so a watch that conflated the two would be caught here.
    """
    sw, flat, alerts, _ = watch(safety_pad=0.0)
    # Σ open margin 90 → floor 90. cash 100 (comfortable), unrealized −20 → net_liq 80.
    out = sw.mark(cash=100.0, net_liq=80.0, sum_open_margin=90.0)

    assert out.reading.floor == 90.0, out.reading
    assert out.reading.unrealized == -20.0, "the two must actually be driven apart"
    assert out.breached and out.fired, "net_liq 80 < floor 90 must fire the watch"
    assert flat.fires == [(FlattenTrigger.NET_LIQ_FLOOR, flat.fires[0][1])], flat.fires
    assert sw.sizing_liquidity() == 100.0, "sizing tracks CASH, which is comfortable"

    # Can-fail: a cash-based watch would read the SAME reading as safe.
    assert out.reading.cash >= out.reading.floor, (
        "cash 100 >= floor 90, so a watch that read cash would NOT have fired — "
        "this reading is what discriminates the two, and the watch fired anyway"
    )
    assert len(alerts.of(AlertTier.CRITICAL)) == 1, alerts.alerts


def test_UNREALIZED_GAIN_does_NOT_fire_even_though_CASH_is_below_floor() -> None:
    """The reverse drive: net-liq ABOVE cash. A cash watch would false-alarm.

    An unrealized GAIN lifts net-liq above cash. With ``cash < floor < net_liq``
    the watch must NOT fire (net-liq is safe). **Can-fail:** a cash-based watch
    (``cash < floor``) WOULD fire here — a spurious flatten of a healthy account —
    so the paired assertion catches the conflation in the opposite direction.
    """
    sw, flat, alerts, _ = watch(safety_pad=0.0)
    # Σ open margin 100 → floor 100. cash 90 (below floor), unrealized +30 → net_liq 120.
    out = sw.mark(cash=90.0, net_liq=120.0, sum_open_margin=100.0)

    assert out.reading.floor == 100.0
    assert out.reading.unrealized == 30.0, "the two must actually be driven apart"
    assert not out.breached and not out.fired, "net_liq 120 >= floor 100: no fire"
    assert not flat.fires, "a healthy account must not be flattened"
    assert not alerts.alerts, "no alert on a safe reading"

    # Can-fail: a cash-based watch would have force-flattened a healthy account.
    assert out.reading.cash < out.reading.floor, (
        "cash 90 < floor 100, so a watch that read cash WOULD have fired — the "
        "watch read net-liq and correctly held"
    )


def test_the_BREACH_PREDICATE_is_the_SEAM_PROPERTY_over_NET_LIQ() -> None:
    """The watch's verdict is exactly ``SurvivalReading.breached`` (net_liq<floor).

    Delegating to the seam's property is what keeps the predicate spelled against
    net-liq in ONE place. Asserted by agreement across a driven-apart reading.
    """
    sw, _flat, _alerts, _ = watch(safety_pad=0.0)
    out = sw.mark(cash=100.0, net_liq=80.0, sum_open_margin=90.0)
    assert out.breached is out.reading.breached is True
    assert out.reading.breached == (out.reading.net_liq < out.reading.floor)


# --------------------------------------------------------------------------
# C2 — BOTH sides of the floor, and the CRITICAL alert (assert the TIER)
# --------------------------------------------------------------------------


def test_ABOVE_the_floor_does_NOT_fire() -> None:
    """§6.5: a reading above the floor is safe. No flatten, no alert."""
    sw, flat, alerts, _ = watch(safety_pad=0.5)
    # Σ open margin 100 → floor 150. net_liq 200 is well above.
    out = sw.mark(cash=200.0, net_liq=200.0, sum_open_margin=100.0)
    assert out.reading.floor == 150.0
    assert not out.breached and not out.fired
    assert not flat.fires
    assert not alerts.alerts


def test_BELOW_the_floor_fires_the_FLATTEN_and_a_CRITICAL_alert() -> None:
    """§6.5 + §12.9: a breach fires ``NET_LIQ_FLOOR`` AND pages Critical.

    Asserts the TRIGGER member, the reason naming net-liq and the floor, the alert
    TIER (Critical, not merely "an alert"), and the snapshot carrying the figures
    §12.9 requires. §7.12: this could pass on a constant "always fire" only if a
    non-breach also fired — ``test_ABOVE_the_floor_does_NOT_fire`` refutes that.
    """
    sw, flat, alerts, _ = watch(safety_pad=0.5)
    # Σ open margin 100 → floor 150. net_liq 130 < 150.
    out = sw.mark(cash=130.0, net_liq=130.0, sum_open_margin=100.0)

    assert out.breached and out.fired
    assert len(flat.fires) == 1, flat.fires
    trigger, reason = flat.fires[0]
    assert trigger is FlattenTrigger.NET_LIQ_FLOOR, trigger
    assert "net_liq" in reason and "130" in reason and "150" in reason, reason
    assert "§15 C2" in reason and "net-liq" in reason, reason

    crit = alerts.of(AlertTier.CRITICAL)
    assert len(crit) == 1, alerts.alerts
    assert crit[0].event == BREACH_EVENT, crit[0]
    assert crit[0].tier is AlertTier.CRITICAL, "§12.9 pages Critical on breach"
    assert crit[0].snapshot["net_liq"] == repr(130.0), crit[0].snapshot
    assert crit[0].snapshot["floor"] == repr(150.0), crit[0].snapshot
    assert set(crit[0].snapshot) >= {"net_liq", "cash", "unrealized", "floor"}, (
        "§12.9: an alert carries the snapshot values, not just a code"
    )


def test_the_ALERT_and_FLATTEN_fire_TOGETHER_not_one_without_the_other() -> None:
    """C2 requires BOTH. Can-fail: a watch that fired only the flatten (or only the
    alert) would break one of these two counts, so both are asserted on one breach.
    """
    sw, flat, alerts, _ = watch(safety_pad=0.0)
    sw.mark(cash=50.0, net_liq=50.0, sum_open_margin=100.0)
    assert sw.flattens == 1 and sw.criticals == 1, (sw.flattens, sw.criticals)
    assert len(flat.fires) == len(alerts.of(AlertTier.CRITICAL)) == 1


def test_a_PERSISTENT_breach_fires_ONCE_and_RE_ARMS_on_recovery() -> None:
    """The latch: a standing watch must not spray duplicate flattens every tick.

    Fires once on breach; a second breaching mark does NOT re-fire; a mark back
    above the floor re-arms; the next breach fires again. Can-fail: without the
    latch the second breaching mark would push ``flattens`` to 2.
    """
    sw, flat, _alerts, _ = watch(safety_pad=0.0)
    sw.mark(cash=50.0, net_liq=50.0, sum_open_margin=100.0)  # breach → fire
    sw.mark(cash=40.0, net_liq=40.0, sum_open_margin=100.0)  # still breached → no fire
    assert sw.flattens == 1, "a persistent breach must fire exactly once"
    sw.mark(cash=200.0, net_liq=200.0, sum_open_margin=100.0)  # recover → re-arm
    sw.mark(cash=50.0, net_liq=50.0, sum_open_margin=100.0)  # breach again → fire
    assert sw.flattens == 2, "a fresh breach after recovery must fire again"
    assert len(flat.fires) == 2


def test_ZERO_WIRE_the_flatten_fires_with_a_broker_that_cannot_be_reached() -> None:
    """§14: the protective path fires even with the reconcile/broker wire down.

    The per-tick ``mark`` path takes no broker poll at all, so a breach flattens
    with the broker unreachable — the exit has zero wire dependency. Modelled by a
    broker whose ``poll`` raises; ``mark`` never calls it, and the flatten fires.
    """

    class DeadBroker:
        """A broker whose wire is down. ``poll`` must never be reached by ``mark``."""

        def poll(self) -> BrokerReading:  # pragma: no cover - must never be called
            """Raise: the per-tick mark path must not touch the broker at all."""
            raise ConnectionError("the wire is down")

    sw = SurvivalWatch(
        safety_pad=0.0,
        broker=DeadBroker(),
        flatten=(flat := RecordingFlatten()),
        alert=RecordingAlerts(),
        tolerance=1.0,
        clock=lambda: 0.0,
    )
    out = sw.mark(cash=50.0, net_liq=50.0, sum_open_margin=100.0)
    assert out.fired and flat.fires[0][0] is FlattenTrigger.NET_LIQ_FLOOR


# --------------------------------------------------------------------------
# C3 — BROKER-AUTHORITATIVE reconcile, UNIFORM, broker-wins, monotonic guard
# --------------------------------------------------------------------------


def test_RECONCILE_pulls_BALANCE_and_POSITIONS_in_ONE_motion() -> None:
    """§4: one poll yields both halves; the floor derives from THOSE positions.

    Both the balance (net_liq/cash) and Σ open margin used by the resulting reading
    come from the single ``poll`` object — asserted by one poll producing a reading
    whose floor matches the polled positions.
    """
    brk = ScriptedBroker(
        [
            BrokerReading(
                cash=1000.0, net_liq=1000.0, positions=(pos(200.0),), venue_ts=1.0
            )
        ]
    )
    sw, _flat, _alerts, _ = watch(safety_pad=0.5, broker=brk)
    out = sw.reconcile("cold_start")
    assert brk.polls == 1, "exactly one poll per reconcile"
    assert out.applied
    assert out.reading.net_liq == 1000.0 and out.reading.cash == 1000.0
    assert out.reading.floor == 300.0, "floor = Σ open margin 200 × (1 + 0.5)"


def test_RECONCILE_is_UNIFORM_every_event_polls_the_broker() -> None:
    """§4: no "is this ambiguous enough?" branch — every event pulls a poll.

    Drives the full spec-named event set and asserts the poll count equals the
    number of reconcile calls. **Can-fail:** a reconcile that skipped the poll on
    the "unambiguous" events (e.g. a plain fill) would leave ``polls`` short of the
    event count, and this assertion reddens naming the deficit.
    """
    events = [
        "indeterminate",
        "orphan",
        "protective_flatten",
        "partial_fill_resolution",
        "fill",
        "close",
    ]
    readings = [
        BrokerReading(
            cash=1000.0,
            net_liq=1000.0,
            positions=(pos(100.0),),
            venue_ts=float(i + 1),
        )
        for i in range(len(events))
    ]
    brk = ScriptedBroker(readings)
    sw, _flat, _alerts, _ = watch(safety_pad=0.0, broker=brk, tolerance=1000.0)
    for event in events:
        out = sw.reconcile(event)
        assert out.applied, event
    assert brk.polls == len(events), (
        f"uniform reconcile must poll once per event: {brk.polls} polls for "
        f"{len(events)} events"
    )
    assert sw.polls == len(events)


def test_BROKER_WINS_when_projection_disagrees_beyond_tolerance() -> None:
    """§4: projection is a fast local guess; beyond tolerance BROKER WINS.

    A local ``mark`` sets a rosy projection; a reconcile whose broker truth differs
    beyond tolerance overwrites it with broker truth AND books a §12.9 WARNING
    audit event. Asserts the adopted value is the BROKER's, the correction flag,
    the signed drift, and that the audit alert is Warning — **not** Critical.
    """
    brk = ScriptedBroker(
        [
            BrokerReading(
                cash=800.0, net_liq=800.0, positions=(pos(100.0),), venue_ts=5.0
            )
        ]
    )
    sw, _flat, alerts, _ = watch(safety_pad=0.0, broker=brk, tolerance=1.0)
    # Rosy local projection: net_liq 1000, far above the eventual broker 800.
    sw.mark(cash=1000.0, net_liq=1000.0, sum_open_margin=100.0)

    out = sw.reconcile("periodic")
    assert out.applied and out.corrected, out
    assert out.drift == pytest.approx(200.0), "projection 1000 − broker 800"
    assert sw.read().net_liq == 800.0, "broker truth wins and we correct"

    warn = alerts.of(AlertTier.WARNING)
    assert len(warn) == 1 and warn[0].event == DRIFT_EVENT, alerts.alerts
    assert alerts.of(AlertTier.CRITICAL) == [], "a drift correction is not a breach"


def test_WITHIN_tolerance_the_projection_is_NOT_flagged_as_a_correction() -> None:
    """The other side of tolerance: a small disagreement is float noise, not a drift.

    Can-fail: a watch that flagged every disagreement would raise a spurious audit
    event here, so ``corrected`` False and zero Warning alerts is the discriminator.
    """
    brk = ScriptedBroker(
        [
            BrokerReading(
                cash=1000.5, net_liq=1000.5, positions=(pos(100.0),), venue_ts=5.0
            )
        ]
    )
    sw, _flat, alerts, _ = watch(safety_pad=0.0, broker=brk, tolerance=1.0)
    sw.mark(cash=1000.0, net_liq=1000.0, sum_open_margin=100.0)
    out = sw.reconcile("periodic")
    assert not out.corrected, "0.5 <= tolerance 1.0 is not a material drift"
    assert alerts.of(AlertTier.WARNING) == []


def test_MONOTONIC_guard_DISCARDS_a_stale_poll_and_does_NOT_apply_it() -> None:
    """§4 (V27): a poll older than the last applied venue_ts is discarded, not applied.

    Applies a fresh reading (venue_ts 10), then a stale one (venue_ts 4). The stale
    poll must be dropped: the held reading stays the fresh one, ``applied`` is
    False, and the drop names the guard. **Can-fail:** a watch that ordered by
    ARRIVAL rather than venue time would apply the stale reading, regressing
    net-liq — asserted against by the held value being unchanged.
    """
    fresh = BrokerReading(
        cash=900.0, net_liq=900.0, positions=(pos(100.0),), venue_ts=10.0
    )
    stale = BrokerReading(
        cash=500.0, net_liq=500.0, positions=(pos(100.0),), venue_ts=4.0
    )
    brk = ScriptedBroker([fresh, stale])
    sw, _flat, _alerts, _ = watch(safety_pad=0.0, broker=brk, tolerance=1000.0)

    sw.reconcile("push")  # applies venue_ts 10 → net_liq 900
    out = sw.reconcile("late_poll")  # venue_ts 4, stale

    assert not out.applied, "a stale venue reading must be discarded"
    assert "monotonic-by-source guard" in out.note, out.note
    assert sw.read().net_liq == 900.0, (
        "the stale poll must NOT regress the held net-liq — ordering is by venue "
        "time, never arrival"
    )
    assert sw.dropped == 1 and sw.applied == 1


def test_an_EQUAL_venue_ts_is_also_discarded_not_reapplied() -> None:
    """The boundary: accept only if STRICTLY newer. Equal timestamp ⇒ discard."""
    first = BrokerReading(
        cash=900.0, net_liq=900.0, positions=(pos(100.0),), venue_ts=7.0
    )
    same = BrokerReading(cash=1.0, net_liq=1.0, positions=(pos(100.0),), venue_ts=7.0)
    brk = ScriptedBroker([first, same])
    sw, _flat, _alerts, _ = watch(safety_pad=0.0, broker=brk, tolerance=1e9)
    sw.reconcile("a")
    out = sw.reconcile("b")
    assert not out.applied and sw.read().net_liq == 900.0


def test_RECONCILE_runs_the_STANDING_WATCH_on_the_fresh_reading() -> None:
    """A reconcile that reveals a breach fires the flatten on the fresh truth (§4→§6.5).

    Broker truth comes back inside the floor; the reconcile must fire, proving the
    watch runs on the authoritative reading and not only on local marks.
    """
    brk = ScriptedBroker(
        [BrokerReading(cash=50.0, net_liq=50.0, positions=(pos(100.0),), venue_ts=1.0)]
    )
    sw, flat, alerts, _ = watch(safety_pad=0.0, broker=brk)
    out = sw.reconcile("indeterminate")
    assert out.breached and out.fired
    assert flat.fires[0][0] is FlattenTrigger.NET_LIQ_FLOOR
    assert len(alerts.of(AlertTier.CRITICAL)) == 1


# --------------------------------------------------------------------------
# Fail-closed construction and reads
# --------------------------------------------------------------------------


def test_READ_before_any_reading_FAILS_CLOSED_and_LOUD() -> None:
    """A watch with no reading has not proven the account safe (directive 4)."""
    sw, _flat, _alerts, _ = watch()
    with pytest.raises(SurvivalNotReady, match="no survival reading yet"):
        sw.read()
    with pytest.raises(SurvivalNotReady):
        sw.floor()
    with pytest.raises(SurvivalNotReady):
        sw.sizing_liquidity()


def test_a_NEGATIVE_safety_pad_is_REFUSED_at_construction() -> None:
    """§6.5: a negative pad puts the floor below Σ open margin — refused, named."""
    with pytest.raises(KnobError, match="NETLIQ_SAFETY_PAD"):
        watch(safety_pad=-0.01)


def test_a_NEGATIVE_or_INFINITE_tolerance_is_REFUSED() -> None:
    """A negative tolerance corrects on every poll; an infinite one never corrects."""
    with pytest.raises(KnobError, match="tolerance"):
        watch(tolerance=-1.0)
    with pytest.raises(KnobError, match="tolerance"):
        watch(tolerance=float("inf"))


def test_a_NON_FINITE_net_liq_is_REFUSED_LOUDLY_not_treated_as_safe() -> None:
    """nix_check_contract.md §17: a property that cannot be evaluated is not proven.

    A NaN net-liq cannot be compared to the floor, so it must raise rather than
    slip through as a comfortable figure. Asserts the reason names the field.
    """
    sw, _flat, _alerts, _ = watch()
    with pytest.raises(SurvivalWatchError, match="net_liq is nan"):
        sw.mark(cash=100.0, net_liq=float("nan"), sum_open_margin=10.0)


def test_the_FLOOR_uses_the_SHARED_open_margin_states_not_a_private_rule() -> None:
    """Σ open margin membership is ``picture.OPEN_MARGIN_STATES`` — one authority.

    A RESERVED/PENDING/CLOSED row contributes nothing to the floor; only OPEN and
    CLOSING do. Can-fail: a private membership rule that counted a PENDING row
    would inflate the floor here.
    """
    positions = (
        pos(100.0, PositionState.OPEN),
        pos(100.0, PositionState.CLOSING),
        pos(999.0, PositionState.PENDING),  # excluded
        pos(999.0, PositionState.RESERVED),  # excluded
        pos(999.0, PositionState.CLOSED),  # excluded
    )
    brk = ScriptedBroker(
        [BrokerReading(cash=1.0, net_liq=1.0, positions=positions, venue_ts=1.0)]
    )
    sw, _flat, _alerts, _ = watch(safety_pad=0.0, broker=brk)
    out = sw.reconcile("cold_start")
    assert out.reading.floor == 200.0, "only OPEN+CLOSING (100+100) enter Σ open margin"


def test_READ_is_ATOMIC_the_reading_is_replaced_whole_never_mutated() -> None:
    """§3/§12.7: a consumer holding a prior reading is unaffected by a later store.

    ``SurvivalReading`` is frozen and ``read`` returns the one bound object, so a
    reference taken before a new mark keeps its old values — there is no window in
    which some fields are new and others old.
    """
    sw, _flat, _alerts, _ = watch(safety_pad=0.0)
    sw.mark(cash=100.0, net_liq=100.0, sum_open_margin=10.0)
    held = sw.read()
    sw.mark(cash=1.0, net_liq=1.0, sum_open_margin=10.0)
    assert held.net_liq == 100.0, "the earlier reading is immutable and unchanged"
    assert sw.read().net_liq == 1.0, "the new store is visible via a fresh read"
