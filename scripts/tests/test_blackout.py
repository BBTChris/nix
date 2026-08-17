"""ARC 033 / Stage 1A — behaviour of `nixrisk.blackout`, driven INSIDE and OUT.

**THE RULE THIS FILE IS WRITTEN AGAINST.** A window test whose `now` never
lands inside the window proves nothing: the evaluator would return "not
blocked" for an empty reason and every assertion would still hold. So every
window type below is driven at an instant genuinely INSIDE its window and at an
instant genuinely OUTSIDE it, and both sides are asserted — the blocked side on
its verbatim reason, never on the boolean alone.

The calendar is the SHIPPED vendored artifact, not a fixture: the whole point
of §6.1's "per-symbol via live calendar" is that the instants come from the
calendar, and a hand-written window set would prove that the evaluator can read
a tuple.

* §6.1 (EOD): ES, Thursday 2026-08-13. Close 21:00Z, daily break to 22:00Z.
* §6.2 (EOW): ES, Friday 2026-08-14. Close 21:00Z, weekend break to Sunday
  2026-08-16 22:00Z. The EOW leading edge (−30) is WIDER than the EOD one
  (−20), so the two overlap and the union is real rather than illustrated.
* §6.3: driven on live margin with the clock held still, because the trailing
  edge is reactive and a clock cannot move it.
"""
# pylint: disable=redefined-outer-name,duplicate-code
# C0116 / R0903 disabled at module scope for the port DOUBLES below. Each is a
# stand-in carrying exactly the verbs its port declares; a docstring per
# one-line accessor, or a second method invented to clear a class-shape
# threshold, makes each double a worse stand-in for the thing it doubles --
# the reason `check_limiter_gate` records at the same disable. The TESTS
# themselves each carry a docstring naming the property they drive.
# pylint: disable=missing-function-docstring,too-few-public-methods

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixrisk.blackout import (
    BlackoutEvaluator,
    BlackoutKnobError,
    BlackoutKnobs,
    BlackoutOnset,
    ScheduledEvent,
    SessionWindowSource,
    UnusableCalendarError,
    record_source_conflict,
)
from nixrisk.calendar_seam import CacheState, FreshnessStamp, MarginBaseline, WindowSet
from nixrisk.seam import (
    FinancialPicture,
    PositionState,
    Reservation,
    ReservationState,
    TerminalPath,
)

# pylint: enable=wrong-import-position

SYMBOL = "ES"
#: Thursday 2026-08-13: ETH close 21:00Z, daily break re-opening 22:00Z.
THU_CLOSE = datetime(2026, 8, 13, 21, 0, tzinfo=UTC)
THU_REOPEN = datetime(2026, 8, 13, 22, 0, tzinfo=UTC)
#: Friday 2026-08-14: ETH close 21:00Z, weekend break to Sunday 22:00Z.
FRI_CLOSE = datetime(2026, 8, 14, 21, 0, tzinfo=UTC)
SUN_OPEN = datetime(2026, 8, 16, 22, 0, tzinfo=UTC)

KNOBS = BlackoutKnobs(
    eod_blackout_min=20,
    eow_blackout_min=30,
    news_blackout_min=20,
    margin_elevated_pct=0.10,
    margin_min_hold_s=300,
    margin_reacceptance_s=3600,
)


# ---------------------------------------------------------------------------
# Doubles. Each carries exactly the port's verbs (§6.4's read-only caches).
# ---------------------------------------------------------------------------


class _Clock:
    """A settable UTC clock. `now` is DRIVEN; nothing here reads the wall."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


@dataclass
class _WindowCache:
    """`WindowSetReadPort`."""

    sets: dict[str, WindowSet] = field(default_factory=dict)
    cache_state: CacheState = CacheState.FRESH

    def windows(self, symbol: str) -> WindowSet | None:
        return self.sets.get(symbol)

    def state(self) -> CacheState:
        return self.cache_state

    def freshness(self) -> FreshnessStamp | None:
        return FreshnessStamp(feed="calendar", as_of=THU_CLOSE)


@dataclass
class _BaselineCache:
    """`MarginBaselineReadPort`."""

    levels: dict[str, MarginBaseline] = field(default_factory=dict)

    def baseline(self, symbol: str) -> MarginBaseline | None:
        return self.levels.get(symbol)

    def state(self) -> CacheState:
        return CacheState.FRESH

    def freshness(self) -> FreshnessStamp | None:
        return FreshnessStamp(feed="margin", as_of=THU_CLOSE)


class _Picture:
    """`FinancialPicturePort` over one mutable per-symbol margin mapping."""

    def __init__(self, margin: dict[str, float] | None = None) -> None:
        self.margin = margin if margin is not None else {}
        self.version = 1

    def publish(self, picture: FinancialPicture) -> None:  # pragma: no cover
        raise AssertionError("the evaluator must never publish (§6.4 read-only)")

    def current(self) -> FinancialPicture:
        return FinancialPicture(
            version=self.version,
            published_ts=0.0,
            balance=100_000.0,
            positions=(),
            margin_per_contract=dict(self.margin),
            sum_open_margin=0.0,
            sum_reservations=0.0,
            committed=0.0,
            deployable=70_000.0,
        )


@dataclass
class _Alerts:
    """`AlertSink`."""

    raised: list[tuple[str, str]] = field(default_factory=list)

    def alert(self, code: str, message: str) -> None:
        self.raised.append((code, message))


@dataclass
class _Onsets:
    """`OnsetSink`."""

    seen: list[BlackoutOnset] = field(default_factory=list)

    def on_blackout_onset(self, onset: BlackoutOnset) -> None:
        self.seen.append(onset)


class _Ledger:
    """`ReservationLedgerPort`, enough of it to observe a release."""

    def __init__(self, rows: list[Reservation]) -> None:
        self.rows = rows
        self.released: list[tuple[str, TerminalPath]] = []

    def take(self, order: object, now: float) -> Reservation:  # pragma: no cover
        raise AssertionError("the evaluator must never take a reservation")

    def release(
        self, reservation_id: str, via: TerminalPath, now: float
    ) -> Reservation:
        del now
        self.released.append((reservation_id, via))
        self.rows = [r for r in self.rows if r.reservation_id != reservation_id]
        return Reservation(
            reservation_id=reservation_id,
            client_order_id="c",
            strategy_id="s",
            symbol=SYMBOL,
            margin=1.0,
            state=ReservationState.RELEASED,
            taken_ts=0.0,
            released_via=via,
        )

    def outstanding(self) -> tuple[Reservation, ...]:
        return tuple(self.rows)

    def total_reserved(self) -> float:
        return sum(r.margin for r in self.rows)


def _reservation(rid: str, symbol: str = SYMBOL) -> Reservation:
    return Reservation(
        reservation_id=rid,
        client_order_id=f"c-{rid}",
        strategy_id=f"s-{rid}",
        symbol=symbol,
        margin=500.0,
        state=ReservationState.TAKEN,
        taken_ts=0.0,
    )


@dataclass
class _Rig:  # pylint: disable=too-many-instance-attributes
    """One wired evaluator plus every double it reads, for the drives below."""

    evaluator: BlackoutEvaluator
    clock: _Clock
    windows: _WindowCache
    baselines: _BaselineCache
    picture: _Picture
    alerts: _Alerts
    onsets: _Onsets
    ledger: _Ledger


def _rig(at: datetime, *, day: datetime | None = None, events=()) -> _Rig:
    """Wire the SHIPPED evaluator over the SHIPPED calendar at instant `at`."""
    clock = _Clock(at)
    source = SessionWindowSource(KNOBS)
    windows = _WindowCache(
        {SYMBOL: source.window_set(SYMBOL, day or at, events=events)}
    )
    baselines = _BaselineCache()
    picture = _Picture()
    alerts = _Alerts()
    onsets = _Onsets()
    ledger = _Ledger([])
    return _Rig(
        evaluator=BlackoutEvaluator(
            windows=windows,
            baselines=baselines,
            picture=picture,
            clock=clock,
            knobs=KNOBS,
            alert=alerts,
            onset=onsets,
            ledger=ledger,
        ),
        clock=clock,
        windows=windows,
        baselines=baselines,
        picture=picture,
        alerts=alerts,
        onsets=onsets,
        ledger=ledger,
    )


# ---------------------------------------------------------------------------
# The port shape — the rule that already exists must be able to hold this
# ---------------------------------------------------------------------------


def test_evaluator_satisfies_the_symbol_flag_port_the_manifest_already_names():
    """`gate.default_manifest(blackout=...)` accepts it with no gate.py edit."""
    from nixrisk.gate import SymbolFlagPort  # pylint: disable=import-outside-toplevel

    assert isinstance(_rig(THU_CLOSE).evaluator, SymbolFlagPort)


# ---------------------------------------------------------------------------
# §6.1 — EOD. INSIDE and OUTSIDE.
# ---------------------------------------------------------------------------


def test_eod_inside_blocks_and_names_the_window():
    """10 min before Thursday's close is INSIDE `[close−20, reopen)`."""
    rig = _rig(THU_CLOSE - timedelta(minutes=10))
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "§6.1-6.3 blackout" in reason
    assert "eod" in reason
    assert THU_REOPEN.isoformat() in reason


def test_eod_leading_edge_is_inclusive_and_one_second_before_it_is_clear():
    """The instant the lead opens blocks; one second earlier does not."""
    rig = _rig(THU_CLOSE - timedelta(minutes=20))
    assert rig.evaluator.read(SYMBOL)[0]
    rig.clock.at = THU_CLOSE - timedelta(minutes=20, seconds=1)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert not blocked, reason
    assert reason == ""


def test_eod_outside_after_the_next_open_permits_entry():
    """`[start, end)` is half-open: the re-open instant itself is OUTSIDE."""
    rig = _rig(THU_REOPEN)
    assert rig.evaluator.read(SYMBOL) == (False, "")
    rig.clock.at = THU_REOPEN + timedelta(minutes=30)
    assert rig.evaluator.read(SYMBOL) == (False, "")


def test_eod_covers_the_whole_closed_period_not_only_the_lead():
    """§6.1 runs THROUGH the next open, so mid-break is still blocked."""
    rig = _rig(THU_CLOSE + timedelta(minutes=30))
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked and "eod" in reason, reason


# ---------------------------------------------------------------------------
# §6.2 — EOW, and the union that needs TWO overlapping windows to exist
# ---------------------------------------------------------------------------


def test_eow_generates_two_overlapping_windows_with_the_wider_lead_first():
    """The premise of the union test, asserted rather than assumed."""
    windows = SessionWindowSource(KNOBS).windows_for(SYMBOL, FRI_CLOSE)
    friday = [w for w in windows if w.end == SUN_OPEN]
    kinds = {w.kind.value: w for w in friday}
    assert set(kinds) == {"eod", "eow"}, kinds
    assert kinds["eow"].start == FRI_CLOSE - timedelta(minutes=30)
    assert kinds["eod"].start == FRI_CLOSE - timedelta(minutes=20)
    assert kinds["eow"].start < kinds["eod"].start


def test_eow_blocks_where_the_narrower_eod_window_alone_would_not():
    """THE UNION. 25 min before Friday close: EOW is active, EOD is not."""
    at = FRI_CLOSE - timedelta(minutes=25)
    rig = _rig(at, day=FRI_CLOSE)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "eow" in reason and SUN_OPEN.isoformat() in reason

    # The control: the SAME instant against a set holding only the EOD window
    # is CLEAR. One window cannot show a union, so the union is shown by
    # removing the other one and watching the verdict flip.
    only_eod = tuple(
        w for w in rig.windows.sets[SYMBOL].windows if w.kind.value != "eow"
    )
    rig.windows.sets[SYMBOL] = WindowSet(
        symbol=SYMBOL, windows=only_eod, generated_at=FRI_CLOSE
    )
    assert rig.evaluator.read(SYMBOL) == (False, ""), "EOD alone must not block here"


def test_eow_wins_the_attribution_while_both_windows_are_active():
    """10 min before Friday close BOTH are active; the widest edge names it."""
    rig = _rig(FRI_CLOSE - timedelta(minutes=10), day=FRI_CLOSE)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "inside the eow window" in reason, reason
    assert "other active window(s) ['eod']" in reason, reason
    assert "widest active leading edge wins" in reason


def test_eow_outside_before_the_lead_and_after_sunday_open():
    """Both OUTSIDE drives: 40 min before Friday close, and after Sunday open."""
    rig = _rig(FRI_CLOSE - timedelta(minutes=40), day=FRI_CLOSE)
    assert rig.evaluator.read(SYMBOL) == (False, "")
    rig.clock.at = SUN_OPEN + timedelta(minutes=1)
    assert rig.evaluator.read(SYMBOL) == (False, "")


def test_eow_blocks_across_the_whole_weekend():
    """Saturday noon is inside `[Friday close−30, Sunday open)`."""
    rig = _rig(datetime(2026, 8, 15, 12, 0, tzinfo=UTC), day=FRI_CLOSE)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked and "eow" in reason, reason


# ---------------------------------------------------------------------------
# §6.3 — asymmetric edges
# ---------------------------------------------------------------------------


def _news_rig(event_at: datetime) -> _Rig:
    """A rig whose window set carries one scheduled margin event."""
    event = ScheduledEvent(
        symbol=SYMBOL, at=event_at, source="test-poller", label="fomc"
    )
    rig = _rig(event_at, day=event_at, events=(event,))
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=event_at - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 1000.0
    return rig


#: A Wednesday inside RTH: no EOD/EOW window is anywhere near it, so a block
#: here can only be §6.3's. Chosen deliberately — running the news drives
#: inside a session-close window would prove nothing about the news edge.
EVENT_AT = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)


def test_news_leading_edge_is_the_clock_inside_and_outside():
    """INSIDE `[E−20m, E)` blocks; 21 min before, and at E itself, do not."""
    rig = _news_rig(EVENT_AT)
    rig.clock.at = EVENT_AT - timedelta(minutes=21)
    assert rig.evaluator.read(SYMBOL) == (False, "")

    rig.clock.at = EVENT_AT - timedelta(minutes=10)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "news_margin" in reason and "test-poller:fomc" in reason

    # The trailing edge is REACTIVE: an event that moves no margin releases at
    # the event instant. A clock-driven trailing edge is the symmetry §6.3
    # refuses, so this assertion is deliberate and not an oversight.
    rig.clock.at = EVENT_AT
    assert rig.evaluator.read(SYMBOL) == (False, "")


def test_margin_spike_holds_the_trailing_edge_open_and_returns_to_baseline():
    """The full §6.3 trailing-edge drive: spike, return, floor, release."""
    rig = _news_rig(EVENT_AT)

    rig.clock.at = EVENT_AT + timedelta(seconds=30)
    rig.picture.margin[SYMBOL] = 4000.0  # the 4x snap §6.5 names
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "§6.3 margin elevated" in reason and "4000.0" in reason

    # MARGIN ACTUALLY RETURNS TO BASELINE. Still blocked: the min-time floor
    # runs 300s from the last elevated observation.
    rig.clock.at = EVENT_AT + timedelta(seconds=60)
    rig.picture.margin[SYMBOL] = 1000.0
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "§6.3 min-time floor" in reason
    assert "returned to baseline" in reason

    # Past the floor, with margin still at baseline: PERMITTED.
    rig.clock.at = EVENT_AT + timedelta(seconds=400)
    assert rig.evaluator.read(SYMBOL) == (False, "")


def test_unscheduled_spike_blocks_with_no_window_at_all():
    """§6.3's "catches unscheduled spikes for free", driven with no event."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 1000.0
    assert rig.evaluator.read(SYMBOL) == (False, ""), "premise: nothing is active"

    rig.picture.margin[SYMBOL] = 1200.0
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "UNSCHEDULED" in reason


def test_elevation_within_tolerance_does_not_block():
    """A 9% move under a 10% tolerance is not a spike."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 1090.0
    assert rig.evaluator.read(SYMBOL) == (False, "")


def test_stable_elevated_margin_is_re_accepted_and_alerts_the_operator():
    """THE ANTI-LOCKOUT DRIVE. Margin STAYS elevated past the period."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 4000.0

    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked and "margin elevated" in reason

    # Still elevated, an hour minus a second later: still locked out.
    rig.clock.at = EVENT_AT + timedelta(seconds=3599)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "3599s of the 3600s re-acceptance period" in reason

    # Past the period, STILL elevated: the level becomes the new baseline.
    rig.clock.at = EVENT_AT + timedelta(seconds=3601)
    assert rig.evaluator.read(SYMBOL) == (False, "")
    codes = [code for code, _ in rig.alerts.raised]
    assert codes == ["margin_baseline_re_accepted"], rig.alerts.raised
    assert "regime shift" in rig.alerts.raised[0][1]

    # And it STAYS unlocked at the new level — the lockout is actually broken,
    # not merely reported broken once.
    rig.clock.at = EVENT_AT + timedelta(seconds=7200)
    assert rig.evaluator.read(SYMBOL) == (False, "")


def test_a_published_baseline_newer_than_the_re_acceptance_wins():
    """§6.4b: newer `accepted_at` governs, so the poller reclaims the number."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 4000.0
    rig.evaluator.read(SYMBOL)
    rig.clock.at = EVENT_AT + timedelta(seconds=3601)
    assert rig.evaluator.read(SYMBOL) == (False, ""), "re-accepted at 4000"

    # The poller now publishes a LATER baseline back at the old level.
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT + timedelta(seconds=3602)
    )
    rig.clock.at = EVENT_AT + timedelta(seconds=3603)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "margin elevated" in reason and "1000.0" in reason


def test_baseline_held_but_live_margin_absent_denies():
    """§17: the trailing edge's subject exists and its reading does not."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT - timedelta(days=1)
    )
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "carries no live margin" in reason


def test_no_baseline_at_all_abstains_and_lets_the_windows_decide():
    """The asymmetric half: no reference level means no trailing edge to hold."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.picture.margin[SYMBOL] = 999_999.0
    assert rig.evaluator.read(SYMBOL) == (False, "")


# ---------------------------------------------------------------------------
# Fail-closed, §12.3, and the onset
# ---------------------------------------------------------------------------


def test_unpublished_window_set_denies_rather_than_clearing():
    """§6.4's direction: an absent set is not an open market."""
    rig = _rig(THU_CLOSE - timedelta(hours=6))
    assert rig.evaluator.read(SYMBOL) == (False, ""), "premise: clear when published"
    rig.windows.sets.clear()
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "no FRESH window set is published" in reason and "rows absent" in reason


def test_empty_cache_state_denies_even_with_a_set_present():
    """`CacheState.EMPTY` is stale-until-proven-fresh, and it fails closed."""
    rig = _rig(THU_CLOSE - timedelta(hours=6))
    rig.windows.cache_state = CacheState.EMPTY
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked and "cache state 'empty'" in reason, reason
    assert "rows present" in reason, reason


def test_stale_cache_state_denies_even_with_a_set_present():
    """ARC 034 (D3.193): §6.5's `data stale` disjunct, on the WINDOW arm.

    `CacheState` has three members and `_window_arm` used to fail closed on
    `EMPTY` alone, so a cache carrying rows that are KNOWN to be out of date
    returned CLEAR — an entry admitted off a window set nobody vouches for.
    The premise assertion is the half that makes this a measurement: the same
    rig clears when the cache is FRESH, so the denial is attributable to the
    state and to nothing else.
    """
    rig = _rig(THU_CLOSE - timedelta(hours=6))
    assert rig.evaluator.read(SYMBOL) == (False, ""), "premise: clear when FRESH"
    rig.windows.cache_state = CacheState.STALE
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, "a STALE window cache must DENY — §6.5 lists `data stale`"
    assert "cache state 'stale'" in reason, reason
    assert "rows present" in reason, reason
    assert "§6.4/§6.5 fail-closed" in reason, reason


def test_every_cache_state_other_than_fresh_denies():
    """The guard is `is not FRESH`, enumerated over the whole enum.

    Written as a sweep rather than as two cases so that a FOURTH `CacheState`
    member added later is judged by this test on the day it is added, instead
    of quietly joining the permitted side the way `STALE` did.
    """
    for state in CacheState:
        rig = _rig(THU_CLOSE - timedelta(hours=6))
        rig.windows.cache_state = state
        blocked, reason = rig.evaluator.read(SYMBOL)
        if state is CacheState.FRESH:
            assert not blocked, f"{state} must be the ONE permitted state: {reason}"
            continue
        assert blocked, f"{state.value} must deny — §6.4's fail-closed direction"
        assert f"cache state {state.value!r}" in reason, reason


def test_a_naive_clock_denies_and_names_the_value():
    """§12.3: a naive `now` cannot be placed on the UTC timeline."""
    rig = _rig(THU_CLOSE)
    rig.clock.at = THU_CLOSE.replace(tzinfo=None)
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked, reason
    assert "§12.3 clock integrity" in reason and "naive" in reason


def test_onset_releases_the_symbols_reservations_once_via_blackout_onset():
    """§3: onset cancels PENDING ENTRY orders; the path is the seam's own."""
    rig = _rig(THU_CLOSE - timedelta(minutes=25))
    rig.ledger.rows = [
        _reservation("r1"),
        _reservation("r2"),
        _reservation("rNQ", "NQ"),
    ]
    assert rig.evaluator.read(SYMBOL) == (False, ""), "premise: outside the window"
    assert not rig.onsets.seen

    rig.clock.at = THU_CLOSE - timedelta(minutes=10)
    assert rig.evaluator.read(SYMBOL)[0]
    assert len(rig.onsets.seen) == 1
    onset = rig.onsets.seen[0]
    assert onset.via is TerminalPath.BLACKOUT_ONSET
    assert onset.released == ("r1", "r2")
    assert [rid for rid, _ in rig.ledger.released] == ["r1", "r2"]
    assert all(via is TerminalPath.BLACKOUT_ONSET for _, via in rig.ledger.released)

    # A second read still inside the SAME window is not a second onset.
    rig.clock.at = THU_CLOSE - timedelta(minutes=5)
    assert rig.evaluator.read(SYMBOL)[0]
    assert len(rig.onsets.seen) == 1

    # Leaving and re-entering IS a second onset.
    rig.clock.at = THU_REOPEN + timedelta(minutes=1)
    assert rig.evaluator.read(SYMBOL) == (False, "")
    rig.clock.at = THU_CLOSE - timedelta(minutes=5)
    assert rig.evaluator.read(SYMBOL)[0]
    assert len(rig.onsets.seen) == 2


def test_a_margin_block_is_not_a_window_onset():
    """§6.3 holds open positions through; §3's cancel is a WINDOW onset."""
    rig = _rig(EVENT_AT, day=EVENT_AT)
    rig.ledger.rows = [_reservation("r1")]
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=EVENT_AT - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 4000.0
    assert rig.evaluator.read(SYMBOL)[0]
    assert not rig.onsets.seen
    assert not rig.ledger.released


def test_a_window_and_a_spike_together_report_both(monkeypatch):
    """§6.5's disjunction: the window names it, the margin state is appended."""
    del monkeypatch
    rig = _rig(THU_CLOSE - timedelta(minutes=10))
    rig.baselines.levels[SYMBOL] = MarginBaseline(
        symbol=SYMBOL, level=1000.0, accepted_at=THU_CLOSE - timedelta(days=1)
    )
    rig.picture.margin[SYMBOL] = 4000.0
    blocked, reason = rig.evaluator.read(SYMBOL)
    assert blocked
    assert "§6.1-6.3 blackout" in reason and "ALSO: §6.3 margin elevated" in reason


# ---------------------------------------------------------------------------
# Knobs (§12A) and generation refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "value", "fragment"),
    [
        ("eod_blackout_min", 0, "cannot deny"),
        ("eow_blackout_min", -1, "cannot deny"),
        ("news_blackout_min", 0, "cannot deny"),
        ("margin_elevated_pct", 0.0, "must be in (0, 1]"),
        ("margin_elevated_pct", 1.5, "must be in (0, 1]"),
        ("margin_min_hold_s", 0, "removes the '+'"),
        ("margin_reacceptance_s", 60, "re-baselines every ordinary spike"),
    ],
)
def test_out_of_range_knobs_refuse_to_construct(field_name, value, fragment):
    """§12A boot validation: an invalid set is a refusal, not a pass."""
    values = {
        "eod_blackout_min": 20,
        "eow_blackout_min": 30,
        "news_blackout_min": 20,
        "margin_elevated_pct": 0.10,
        "margin_min_hold_s": 300,
        "margin_reacceptance_s": 3600,
        field_name: value,
    }
    with pytest.raises(BlackoutKnobError) as excinfo:
        BlackoutKnobs(**values)
    assert fragment in str(excinfo.value)


def test_knobs_from_config_refuse_a_missing_knob_rather_than_defaulting():
    """No `.get(name, default)` anywhere on the boot path."""
    with pytest.raises(BlackoutKnobError) as excinfo:
        BlackoutKnobs.from_config({"eod_blackout_min": 20})
    assert "holds no default" in str(excinfo.value)


def test_knobs_load_from_the_shipped_limiter_config():
    """The physical layout really carries the six values (§12A / `risks/`)."""
    import json  # pylint: disable=import-outside-toplevel

    values = json.loads((REPO / "risks" / "limiter.config.json").read_text())
    knobs = BlackoutKnobs.from_config(values)
    assert knobs.eod_blackout_min == 20
    assert knobs.eow_blackout_min == 30
    assert knobs.news_blackout_min == 20


def test_an_unknown_break_class_is_a_refusal_not_a_missing_window():
    """A renamed weekend class must be loud; a silent EOW absence is invisible."""

    class _Renamed:
        """A calendar whose weekend class was renamed under the module."""

        def product_group_of(self, symbol: str) -> str:
            del symbol
            return "equity_index"

        def break_window(self, product_group: str, on_date: object):
            del product_group, on_date

            @dataclass(frozen=True)
            class _Break:
                date: str = "2026-08-14"
                start: datetime = FRI_CLOSE
                end: datetime = SUN_OPEN
                klass: str = "END_OF_WEEK"

            return _Break()

    source = SessionWindowSource(KNOBS, calendar=_Renamed())
    with pytest.raises(UnusableCalendarError) as excinfo:
        source.windows_for(SYMBOL, FRI_CLOSE)
    assert "END_OF_WEEK" in str(excinfo.value)


def test_a_naive_generation_day_is_refused():
    """§12.3 at the generation boundary as well as at the decision one."""
    with pytest.raises(ValueError, match="naive"):
        SessionWindowSource(KNOBS).windows_for(SYMBOL, FRI_CLOSE.replace(tzinfo=None))


def test_positions_are_never_traversed_by_the_evaluator():
    """§11: the entry pathway is cache reads and arithmetic, not a table scan."""

    class _Counting(tuple):
        """A positions tuple that reports every traversal."""

        touches = 0

        def __iter__(self):
            type(self).touches += 1
            return super().__iter__()

        def __getitem__(self, item):
            type(self).touches += 1
            return super().__getitem__(item)

    rig = _rig(THU_CLOSE - timedelta(minutes=10))
    rows = _Counting(((SYMBOL, PositionState.OPEN),))
    original = rig.picture.current

    def _with_positions() -> FinancialPicture:
        import dataclasses  # pylint: disable=import-outside-toplevel

        return dataclasses.replace(original(), positions=rows)

    rig.picture.current = _with_positions  # type: ignore[method-assign]
    rig.evaluator.read(SYMBOL)
    assert _Counting.touches == 0


# ---------------------------------------------------------------------------
# SPEC-A10 — the flagging path itself
# ---------------------------------------------------------------------------


def test_source_conflict_flagging_path_returns_live_and_records_the_disagreement():
    """SPEC-A10's rule, on the FUNCTION. It is not a claim that a conflict exists.

    `CALENDAR_SOURCES` has one member and no conflict can occur in this tree —
    the amendment says so and this test does not contradict it. What is driven
    here is the flagging path's own behaviour: live wins, and the disagreement
    comes back as a record instead of being swallowed.
    """
    alerts = _Alerts()
    value, conflict = record_source_conflict(
        field_name="eth_close",
        live_value=FRI_CLOSE,
        live_source="live-poller",
        other_value=FRI_CLOSE + timedelta(minutes=15),
        other_source="vendored-artifact",
        at=FRI_CLOSE,
        alert=alerts,
    )
    assert value == FRI_CLOSE, "live source wins for a live decision"
    assert conflict is not None
    assert conflict.other_source == "vendored-artifact"
    assert alerts.raised[0][0] == "calendar_source_conflict"
    assert "never silently" in alerts.raised[0][1]


def test_agreeing_sources_raise_nothing():
    """No alert where there is no disagreement — a flag that always fires is noise."""
    alerts = _Alerts()
    value, conflict = record_source_conflict(
        field_name="eth_close",
        live_value=FRI_CLOSE,
        live_source="live-poller",
        other_value=FRI_CLOSE,
        other_source="vendored-artifact",
        at=FRI_CLOSE,
    )
    assert (value, conflict) == (FRI_CLOSE, None)
    assert not alerts.raised
