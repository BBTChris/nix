"""ARC 029 / sub-agent B — the protective-flatten executor, driven directly.

This is the can-fail suite for `scripts/nixrisk/flatten.py` (B1–B5). Every control
follows plant → red (naming the SITE and the REASON) → restore → green, and every
assertion reads the REASON — a message, a field, a booked cause — never an exit
code alone (check contract v2 §11).

The four §0a hazards this brief states are treated as HYPOTHESES and MEASURED:

* **zero-wire is provable only by REMOVAL.** `test_zero_wire_*` runs with the
  picture wire DEAD; the falsifier `_WireCoupledFlatten` couples the exit to the
  wire and is shown to die with it. A healthy-transport test would measure
  nothing here.
* **precedence is proven only under CONTENTION.** `test_precedence_*` drives BOTH
  authorities at the SAME trade in BOTH orderings; `_LastWriteWinsFlatten` shows a
  no-precedence arbiter loses the property. A sequential protective-only path is
  refused as vacuous.
* **reconcile-then-publish must publish the CONFIRMED state, not the intent.**
  `test_reconcile_*` drives one fixture where the flatten hits nothing and one
  where it closes a real position, and proves the published balance is broker
  truth AFTER the flatten. `_PublishesIntentFlatten` publishes the pre-flatten
  projection and is shown to fail the same assertion.
* **a distinct HALT_ONSET cause is real, not collapsed** (SPEC-A7). The onset
  controls prove HALT releases under `HALT_ONSET` and blackout under
  `BLACKOUT_ONSET`, and that a non-onset cause is refused.

§7.12 (the standing question) is answered per control in its docstring.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods,too-many-arguments
# pylint: disable=too-many-positional-arguments,wrong-import-position
# duplicate-code: the ClosedRecord the test constructs as its EXPECTED value
# necessarily mirrors the one flatten.py builds — asserting equality against a
# hand-built record is the point, and R0801 cannot tell a test's expected-value
# mirror from copied production logic.
# pylint: disable=duplicate-code
# invalid-name: the test names are sentences. redefined-outer-name: pytest
# fixtures. protected-access: the plant subclasses reach the executor's injected
# collaborators to build a WRONG variant — that is how the falsifier is written.
# missing-function-docstring: the test doubles' verbs are named after the ports
# they stand in for; a docstring would restate the port. too-few-public-methods /
# too-many-arguments: DeadPictureSink is a one-verb stand-in and `_executor` takes
# the collaborators the executor takes — the counts are the seam's, not this file's.

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "broker"))

from broker_seam import Balance, Position  # pylint: disable=wrong-import-position
from nixrisk.flatten import (  # pylint: disable=wrong-import-position
    CloseAuthority,
    ClosedRecord,
    CloseOutcome,
    CloseTarget,
    ConfirmedFlat,
    ExitEventKind,
    FlattenAction,
    NotAnOnsetCause,
    PendingEntry,
    ProtectiveFlatten,
    TriggerNotFireable,
)
from nixrisk.picture import (  # pylint: disable=wrong-import-position
    FinancialPictureBook,
    PictureSink,
)
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionRow,
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)

SPEC = REPO / "docs" / "nics_risk_subsystem_spec_v1.3.md"


# ==========================================================================
# Test doubles — a broker whose truth CHANGES, and recording fan-out sinks
# ==========================================================================


class ReconcileBroker:
    """A `BrokerFlattenPort` whose flatten really moves money and position truth.

    Deliberately NOT `StubBrokerOrder`: this suite's whole subject is that broker
    truth AFTER a flatten differs from the pre-flatten projection, and a stub with
    a constant balance cannot express it. `realize_on_flatten` books a realized
    P&L into cash the instant a symbol is flattened, so `query_balance` returns a
    figure the projection never held.
    """

    def __init__(self, *, positions: list[Position] | None = None, cash: float) -> None:
        self._positions: dict[str, Position] = {p.symbol: p for p in (positions or [])}
        self._cash = cash
        self._net_liq = cash
        self.realize_on_flatten: dict[str, float] = {}
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)
        targets = [symbol] if symbol else list(self._positions)
        for sym in targets:
            if sym is not None and sym in self._positions:
                del self._positions[sym]
                self._cash += self.realize_on_flatten.get(sym, 0.0)
        self._net_liq = self._cash  # flat ⇒ net-liq collapses to cash

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.net_qty != 0]

    async def query_balance(self) -> Balance:
        return Balance(
            cash=self._cash,
            net_liquidation=self._net_liq,
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=0.0,
        )


@dataclass
class StrategySink:
    """§4 fan-out (a). Records every `closed, reason=X, hard_reset` notification."""

    closed: list[tuple[str, str, str, bool]] = field(default_factory=list)

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


@dataclass
class ExitLog:
    """The interim §12.10 exit surface. Records every row and its kind."""

    rows: list[tuple[ExitEventKind, str | None, str, str, str]] = field(
        default_factory=list
    )

    def record(
        self,
        *,
        kind: ExitEventKind,
        trade_id: str | None,
        strategy_id: str,
        symbol: str,
        reason: str,
        ts: float,
    ) -> None:
        del ts
        self.rows.append((kind, trade_id, strategy_id, symbol, reason))

    def of(
        self, kind: ExitEventKind
    ) -> list[tuple[ExitEventKind, str | None, str, str, str]]:
        return [row for row in self.rows if row[0] is kind]


@dataclass
class ScoringSink:
    """§4 fan-out (d). Records the realized-P&L hand-off (EMA math is R5)."""

    booked: list[tuple[tuple[str, ...], float, float]] = field(default_factory=list)

    def book_realized(
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        del ts
        self.booked.append((closed_trades, realized_delta, confirmed_balance))


@dataclass
class RecordingPictureSink:
    """§12.7 allocator-mirror wire. Records every published (emitted) picture."""

    emitted: list[object] = field(default_factory=list)

    def emit(self, picture: object) -> None:
        self.emitted.append(picture)


class DeadPictureSink:
    """The WIRE, REMOVED. Every publish attempt raises — state bus down / ZMQ gone.

    §14's zero-wire property is provable only against this: a healthy sink cannot
    show that the exit does not depend on the wire, because a dependency it does
    not exercise is invisible.
    """

    def emit(self, picture: object) -> None:
        raise ConnectionError(
            "state bus down / ZMQ unavailable — the picture is unpublishable"
        )


class Plane1Recorder:
    """§9 Plane-1 sink for the ledger. Keeps every row; no durability."""

    def __init__(self) -> None:
        self.rows: list[EventRow] = []

    def enqueue(self, row: EventRow) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)

    def of(self, kind: EventKind) -> list[EventRow]:
        return [row for row in self.rows if row.kind is kind]


# ==========================================================================
# Builders / fixtures
# ==========================================================================


def _order(
    coid: str, symbol: str = "MESU6", per_contract: float = 1000.0
) -> ProposedOrder:
    """One §3 proposal, already sized, so the ledger can take a reservation."""
    return ProposedOrder(
        client_order_id=coid,
        strategy_id="strat-1",
        symbol=symbol,
        side=Side.LONG,
        qty=1,
        margin_per_contract=per_contract,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


def _clock() -> float:
    """A deterministic monotone-enough clock for records."""
    _clock.t += 1.0  # type: ignore[attr-defined]
    return _clock.t  # type: ignore[attr-defined]


_clock.t = 1000.0  # type: ignore[attr-defined]


def _executor(
    broker: ReconcileBroker,
    *,
    picture: FinancialPictureBook,
    ledger: ReservationLedger | None = None,
    strategy: StrategySink | None = None,
    event_log: ExitLog | None = None,
    scoring: ScoringSink | None = None,
    cls: type[ProtectiveFlatten] = ProtectiveFlatten,
) -> ProtectiveFlatten:
    """One executor wired to the given collaborators, defaulting the rest."""
    return cls(
        broker=broker,
        ledger=ledger or ReservationLedger(Plane1Recorder()),
        picture=picture,
        strategy=strategy or StrategySink(),
        event_log=event_log or ExitLog(),
        scoring=scoring or ScoringSink(),
        clock=_clock,
    )


def _flat_book(
    sink: PictureSink | None, *, balance: float = 20344.34
) -> FinancialPictureBook:
    """A picture book seeded flat, publishing to `sink`."""
    return FinancialPictureBook(balance=balance, deployable_fraction=0.70, sink=sink)


# ==========================================================================
# B1 — the trigger set, TRANSCRIBED FROM §3 and CLOSED
# ==========================================================================


def _spec_triggers() -> set[str]:
    """§3:169's protective-exit set, parsed HERE so this set is not the enum's."""
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(r"Limiter \((?P<set>[^)]*synthetic stop[^)]*)\)", text)
    assert match is not None, "§3's protective-exit trigger sentence is not in the spec"
    return {
        re.sub(r"[\s\-]+", "_", part.strip()).upper()
        for part in match.group("set").split("/")
        if part.strip()
    }


def test_the_TRIGGER_SET_is_SS3_s_own_list_transcribed_and_CLOSED() -> None:
    """§7.12: this could pass while measuring nothing only if the trigger set were
    read from `FlattenTrigger` itself — then it would compare the enum with itself.
    It is parsed from §3's sentence in the frozen spec instead, so a member the
    spec does not name, or a spec trigger the enum drops, reddens it."""
    spec = _spec_triggers()
    enum_names = {t.name for t in FlattenTrigger}

    assert spec == enum_names, (
        f"the FROZEN FlattenTrigger is not §3's transcribed list: "
        f"only in spec={spec - enum_names}, only in enum={enum_names - spec}"
    )
    assert len(spec) == 7, spec


def test_fire_REFUSES_the_R4_triggers_LOUDLY_and_names_the_MECHANISM() -> None:
    """§7.12: a silent no-op would 'succeed' while flattening nothing, which reads
    exactly like a flatten. So the refusal must be loud AND name the unbuilt
    mechanism, not merely return. SESSION_CLOSE names the R4 calendar; SENTINEL
    names the R4 last-resort executor and that it is not the live Limiter's."""
    broker = ReconcileBroker(cash=20344.34)
    ex = _executor(broker, picture=_flat_book(RecordingPictureSink()))

    with pytest.raises(TriggerNotFireable) as session:
        ex.fire(FlattenTrigger.SESSION_CLOSE, symbol="MESU6")
    assert "session calendar" in str(session.value), str(session.value)
    assert "§6.1b" in str(session.value), str(session.value)

    with pytest.raises(TriggerNotFireable) as sentinel:
        ex.fire(FlattenTrigger.SENTINEL, symbol="MESU6")
    assert "last-resort" in str(sentinel.value), str(sentinel.value)
    assert "DEAD" in str(sentinel.value), str(sentinel.value)

    # The refusal really BLOCKED the exit — no broker call leaked through.
    assert not broker.flatten_calls, broker.flatten_calls


@pytest.mark.parametrize(
    "trigger",
    [
        FlattenTrigger.SYNTHETIC_STOP,
        FlattenTrigger.STALE_PRICE,
        FlattenTrigger.NET_LIQ_FLOOR,
        FlattenTrigger.UNCERTAINTY,
        FlattenTrigger.ORPHAN,
    ],
)
def test_fire_ACCEPTS_every_LIMITER_FIRED_trigger_and_issues_the_flatten(
    trigger: FlattenTrigger,
) -> None:
    """The five Limiter-fired triggers each reach the broker. The R4 partition is
    proven CLOSED against the whole enum by the union check below."""
    broker = ReconcileBroker(cash=20344.34)
    ex = _executor(broker, picture=_flat_book(RecordingPictureSink()))

    action = ex.fire(trigger, symbol="MESU6")

    assert isinstance(action, FlattenAction)
    assert broker.flatten_calls == ["MESU6"], broker.flatten_calls


def test_the_R4_partition_covers_the_WHOLE_enum_no_trigger_unhandled() -> None:
    """§7.12: a partition that silently dropped a trigger would leave it neither
    fired nor refused. Every FlattenTrigger must be exactly one of the two."""
    from nixrisk.flatten import _R4_TRIGGERS  # pylint: disable=import-outside-toplevel

    fired = 0
    refused = 0
    for trigger in FlattenTrigger:
        broker = ReconcileBroker(cash=1.0)
        ex = _executor(broker, picture=_flat_book(RecordingPictureSink()))
        if trigger in _R4_TRIGGERS:
            with pytest.raises(TriggerNotFireable):
                ex.fire(trigger, symbol="MESU6")
            refused += 1
        else:
            ex.fire(trigger, symbol="MESU6")
            fired += 1
    assert fired + refused == len(FlattenTrigger), (fired, refused)
    assert refused == 2 and fired == 5, (fired, refused)


# ==========================================================================
# B2 — ZERO WIRE, provable only by REMOVING the wire
# ==========================================================================


class _WireCoupledFlatten(ProtectiveFlatten):
    """THE FALSIFIER for zero-wire: an exit that publishes BEFORE it flattens.

    Wrong on purpose — it couples the protective action to the wire, so with the
    wire removed the publish raises and the broker flatten never runs. It exists
    to prove the zero-wire test would CATCH a wire-coupled implementation; the
    real `fire` never touches the wire (§7.1: removing the plant removes the
    evidence, so the plant is a named class, not an edit)."""

    def fire(
        self,
        trigger: FlattenTrigger,
        *,
        symbol: str | None = None,
        targets: object = (),
    ) -> FlattenAction:
        # WRONG: the wire, on the protective path.
        self._picture.publish(self._picture.current())
        return super().fire(trigger, symbol=symbol, targets=targets)  # type: ignore[arg-type]


def test_zero_wire_the_EXIT_FIRES_with_the_WIRE_REMOVED() -> None:
    """§14: the protective path has ZERO wire/delivery dependency.

    §7.12: with a HEALTHY sink this test measures nothing — a dependency not
    exercised is invisible. So the sink is DEAD (state bus down / ZMQ gone) and
    the position is a real one at the broker. The exit must still close it."""
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    dead = DeadPictureSink()
    ex = _executor(broker, picture=_flat_book(dead))
    target = CloseTarget("T-1", "MESU6", "strat-1")

    # Non-vacuity: the wire really is dead.
    with pytest.raises(ConnectionError):
        dead.emit(object())

    ex.fire(FlattenTrigger.SYNTHETIC_STOP, symbol="MESU6", targets=[target])

    assert broker.flatten_calls == ["MESU6"], (
        "the exit did not fire with the wire down — it has a wire dependency"
    )
    assert "MESU6" not in broker._positions, broker._positions


@pytest.mark.asyncio
async def test_zero_wire_is_FALSIFIABLE_a_coupled_exit_DIES_with_the_wire() -> None:
    """The can-fail twin: `_WireCoupledFlatten` publishes on the protective path,
    so with the wire removed the publish raises at the coupling SITE and the
    broker flatten never runs. This is what the property's ABSENCE looks like, and
    it proves the test above is not vacuous."""
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    ex = _executor(
        broker, picture=_flat_book(DeadPictureSink()), cls=_WireCoupledFlatten
    )
    target = CloseTarget("T-1", "MESU6", "strat-1")

    with pytest.raises(ConnectionError) as caught:
        ex.fire(FlattenTrigger.SYNTHETIC_STOP, symbol="MESU6", targets=[target])

    assert "state bus down" in str(caught.value), str(caught.value)
    assert not broker.flatten_calls, (
        "the coupled exit reached the broker anyway — the plant did not couple"
    )
    assert "MESU6" in broker._positions, (
        "the coupled exit closed the position despite the dead wire"
    )


# ==========================================================================
# B3 — PROTECTIVE ALWAYS WINS, proven only under CONTENTION
# ==========================================================================


class _LastWriteWinsFlatten(ProtectiveFlatten):
    """THE FALSIFIER for precedence: an arbiter with no precedence — last write
    wins. A discretionary close arriving after a protective one would overwrite
    the winner. It proves the precedence test catches a broken arbiter."""

    def request_close(
        self, target: CloseTarget, authority: CloseAuthority, reason: str
    ) -> CloseOutcome:
        self._broker.flatten(target.symbol)
        record = ClosedRecord(
            trade_id=target.trade_id,
            symbol=target.symbol,
            strategy_id=target.strategy_id,
            authority=authority,
            reason=reason,
            closed_ts=self._clock(),
            hard_reset=authority is CloseAuthority.PROTECTIVE,
            superseded=None,
        )
        self._closed[target.trade_id] = record
        return CloseOutcome(executed=True, record=record)


def _contended_executor(broker: ReconcileBroker) -> ProtectiveFlatten:
    return _executor(broker, picture=_flat_book(RecordingPictureSink()))


def test_precedence_PROTECTIVE_OVERRIDES_a_prior_DISCRETIONARY_close() -> None:
    """§4: protective always wins. §7.12: a protective-only sequential path would
    pass a weaker claim while never putting the two in CONTENTION, so this drives
    a discretionary close FIRST (it really executes — non-vacuity), then the
    protective one, and requires the protective to win with a hard reset."""
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    ex = _contended_executor(broker)
    target = CloseTarget("T-1", "MESU6", "strat-1")

    disc = ex.request_close(target, CloseAuthority.DISCRETIONARY, "edge spent")
    prot = ex.request_close(
        target, CloseAuthority.PROTECTIVE, "protective flatten (trigger=stale_price)"
    )

    # Non-vacuity: they WERE in contention — the discretionary really acted first.
    assert disc.executed is True, "the discretionary close never acted — no contention"
    assert prot.executed is True, prot

    winner = ex.closed_record("T-1")
    assert winner is not None
    assert winner.authority is CloseAuthority.PROTECTIVE, winner
    assert winner.superseded is CloseAuthority.DISCRETIONARY, winner
    assert winner.hard_reset is True, winner
    assert "stale_price" in winner.reason, winner.reason


def test_precedence_DISCRETIONARY_cannot_OVERRIDE_a_prior_PROTECTIVE_close() -> None:
    """The reverse ordering: protective first, then a discretionary exit for the
    same trade. The discretionary is DROPPED and says why; the winner is
    unchanged; the broker is not flattened a second time."""
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    ex = _contended_executor(broker)
    target = CloseTarget("T-1", "MESU6", "strat-1")

    prot = ex.request_close(target, CloseAuthority.PROTECTIVE, "protective flatten")
    disc = ex.request_close(target, CloseAuthority.DISCRETIONARY, "edge spent")

    assert prot.executed is True
    assert disc.executed is False, "a discretionary exit overrode a protective one"
    assert "protective always wins" in disc.dropped_reason, disc.dropped_reason
    won = ex.closed_record("T-1")
    assert won is not None and won.authority is CloseAuthority.PROTECTIVE, won
    assert broker.flatten_calls == ["MESU6"], (
        "the dropped discretionary close still reached the broker"
    )


def test_precedence_is_FALSIFIABLE_a_last_write_wins_arbiter_LOSES_it() -> None:
    """The can-fail: under `_LastWriteWinsFlatten` the discretionary close arriving
    after the protective one overwrites the winner, so the recorded authority is
    DISCRETIONARY. That is exactly the assertion the real arbiter passes and this
    one fails — the property is measured, not assumed."""
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    ex = _executor(
        broker, picture=_flat_book(RecordingPictureSink()), cls=_LastWriteWinsFlatten
    )
    target = CloseTarget("T-1", "MESU6", "strat-1")

    ex.request_close(target, CloseAuthority.PROTECTIVE, "protective flatten")
    ex.request_close(target, CloseAuthority.DISCRETIONARY, "edge spent")

    winner = ex.closed_record("T-1")
    assert winner is not None
    # The broken arbiter lost the property; the real one holds it.
    assert winner.authority is CloseAuthority.DISCRETIONARY, (
        "the falsifier did not lose precedence — it no longer falsifies"
    )


# ==========================================================================
# B4 — ONSET cancels pending ENTRY orders, exits untouched, DISTINCT causes
# ==========================================================================


def _ledger_with_entries(*coids: str) -> tuple[ReservationLedger, Plane1Recorder]:
    """A ledger holding a live reservation for each pending entry."""
    rec = Plane1Recorder()
    ledger = ReservationLedger(rec)
    for coid in coids:
        ledger.take(_order(coid), 1.0)
    return ledger, rec


@pytest.mark.parametrize(
    ("cause", "via_value"),
    [
        (TerminalPath.HALT_ONSET, "halt_onset"),
        (TerminalPath.BLACKOUT_ONSET, "blackout_onset"),
    ],
)
def test_onset_CANCELS_pending_entries_and_RELEASES_under_the_NAMED_cause(
    cause: TerminalPath, via_value: str
) -> None:
    """§3 + SPEC-A7: HALT onset and blackout onset each cancel pending entries and
    release the reservation under their OWN cause. §7.12: an onset that released
    under a shared `CANCEL` would pass a bare release count while erasing which
    onset freed the capital, so the assertion reads the BOOKED `via`, not a count."""
    ledger, rec = _ledger_with_entries("c-1")
    assert ledger.total_reserved() > 0.0
    broker = ReconcileBroker(cash=20344.34)
    ex = _executor(broker, picture=_flat_book(RecordingPictureSink()), ledger=ledger)
    pending = [PendingEntry("c-1", "strat-1", "MESU6")]

    result = ex.cancel_entries_on_onset(cause, pending)

    assert broker.cancel_calls == ["c-1"], broker.cancel_calls
    assert ledger.total_reserved() == 0.0, ledger.audit()
    assert len(result.released) == 1 and result.released[0].released_via is cause
    row = rec.of(EventKind.RESERVATION_RELEASED)[0]
    assert row.fields["via"] == via_value, row
    # SPEC-A7: the cause is DISTINCT — a HALT release is not a blackout release.
    other = (
        TerminalPath.BLACKOUT_ONSET
        if cause is TerminalPath.HALT_ONSET
        else TerminalPath.HALT_ONSET
    )
    assert result.released[0].released_via is not other, result.released[0]


def test_onset_leaves_OPEN_POSITIONS_UNTOUCHED_it_only_CANCELS_entries() -> None:
    """§3: 'exits untouched'. §7.12: a method that flattened everything would also
    empty the pending set and pass a naive 'entries gone' check, so the control
    holds an OPEN position across the onset and requires it to SURVIVE — the
    broker's flatten must never be called."""
    ledger, _ = _ledger_with_entries("c-1")
    broker = ReconcileBroker(positions=[Position("ESZ6", 2, 5000.0)], cash=20344.34)
    ex = _executor(broker, picture=_flat_book(RecordingPictureSink()), ledger=ledger)

    ex.cancel_entries_on_onset(
        TerminalPath.HALT_ONSET, [PendingEntry("c-1", "strat-1", "MESU6")]
    )

    assert not broker.flatten_calls, "onset flattened an open position — exits touched"
    assert "ESZ6" in broker._positions, "the open exit position was closed by the onset"


def test_onset_REFUSES_a_non_onset_cause_and_NAMES_the_hazard() -> None:
    """The can-fail: releasing an entry-cancel under a non-onset cause is refused.
    Plant TerminalPath.CANCEL (a real member, the tempting collapse SPEC-A7
    forbids) → red naming the wrong-cause hazard; restore HALT_ONSET → green."""
    ledger, _ = _ledger_with_entries("c-1")
    broker = ReconcileBroker(cash=20344.34)
    ex = _executor(broker, picture=_flat_book(RecordingPictureSink()), ledger=ledger)
    pending = [PendingEntry("c-1", "strat-1", "MESU6")]

    with pytest.raises(NotAnOnsetCause) as caught:
        ex.cancel_entries_on_onset(TerminalPath.CANCEL, pending)
    assert "not an onset cause" in str(caught.value), str(caught.value)
    assert "BLACKOUT_ONSET or HALT_ONSET" in str(caught.value), str(caught.value)

    # RESTORE: an onset cause is accepted.
    ok = ex.cancel_entries_on_onset(TerminalPath.HALT_ONSET, pending)
    assert ok.cause is TerminalPath.HALT_ONSET


# ==========================================================================
# B5 — RECONCILE-THEN-PUBLISH the CONFIRMED state, two fixtures
# ==========================================================================


class _PublishesIntentFlatten(ProtectiveFlatten):
    """THE FALSIFIER for reconcile-then-publish: it publishes the pre-flatten
    projection balance (the INTENT) instead of the broker-confirmed one. It proves
    the confirmed-state assertion catches an implementation that broadcasts 'we
    sent a flatten' rather than 'here is the CONFIRMED flat state'."""

    async def reconcile_and_publish(self) -> ConfirmedFlat:
        projection = self._picture.current()
        await self._broker.query_positions()
        await self._broker.query_balance()
        # WRONG: the intent, not broker truth.
        picture = self._picture.commit(
            balance=projection.balance,
            positions=(),
            sum_reservations=self._ledger.total_reserved(),
        )
        return ConfirmedFlat(
            picture=picture,
            confirmed_balance=projection.balance,
            projection_balance=projection.balance,
            closed_trades=(),
            realized_delta=0.0,
            is_flat=True,
        )


def _open_book(
    sink: PictureSink | None, *, balance: float
) -> tuple[FinancialPictureBook, str]:
    """A picture book whose mirror holds one OPEN MESU6 position (trade T-1)."""
    book = _flat_book(sink, balance=balance)
    book.commit(
        balance=balance,
        positions=[
            PositionRow(
                trade_id="T-1",
                symbol="MESU6",
                strategy_id="strat-1",
                size=1,
                margin=1000.0,
                state=PositionState.OPEN,
            )
        ],
    )
    return book, "T-1"


@pytest.mark.asyncio
async def test_reconcile_when_the_flatten_HITS_NOTHING_confirms_FLAT() -> None:
    """§4: the flatten may hit nothing. The Limiter's mirror is flat, the broker is
    flat, and reconcile confirms flat — no closed trades, nothing booked to
    Scoring, and the published balance is broker truth."""
    sink = RecordingPictureSink()
    broker = ReconcileBroker(cash=20344.34)
    scoring = ScoringSink()
    ex = _executor(broker, picture=_flat_book(sink, balance=20344.34), scoring=scoring)

    ex.fire(FlattenTrigger.UNCERTAINTY, symbol="MESU6")
    confirmed = await ex.reconcile_and_publish()

    assert confirmed.is_flat is True
    assert confirmed.closed_trades == (), confirmed
    assert scoring.booked == [((), 0.0, 20344.34)], scoring.booked
    assert confirmed.picture.balance == 20344.34
    assert broker.flatten_calls == ["MESU6"], "the safety flatten was not sent"


@pytest.mark.asyncio
async def test_reconcile_when_the_flatten_CLOSES_A_REAL_POSITION_publishes_CONFIRMED() -> (
    None
):
    """§4: the flatten may close a real position, and the broadcast is 'here is the
    CONFIRMED flat state', not 'we sent a flatten'.

    §7.12 / the measured hypothesis: this passes while measuring nothing unless the
    published balance is broker truth AFTER the flatten and DIFFERS from the
    pre-flatten projection. So the broker realizes +500 on the flatten, and the
    control requires the confirmed balance to be the post figure and NOT the
    projection — the falsifier `_PublishesIntentFlatten` fails this exact line."""
    sink = RecordingPictureSink()
    book, trade_id = _open_book(sink, balance=20344.34)
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    broker.realize_on_flatten["MESU6"] = 500.0
    strategy = StrategySink()
    event_log = ExitLog()
    scoring = ScoringSink()
    ex = _executor(
        broker,
        picture=book,
        strategy=strategy,
        event_log=event_log,
        scoring=scoring,
    )

    ex.fire(
        FlattenTrigger.UNCERTAINTY,
        symbol="MESU6",
        targets=[CloseTarget(trade_id, "MESU6", "strat-1")],
    )
    confirmed = await ex.reconcile_and_publish()

    # The CONFIRMED (post-reconcile) state — broker truth, not the intent.
    assert confirmed.confirmed_balance == 20844.34, confirmed
    assert confirmed.projection_balance == 20344.34, confirmed
    assert confirmed.confirmed_balance != confirmed.projection_balance
    assert confirmed.realized_delta == 500.0, confirmed
    assert confirmed.is_flat is True
    assert confirmed.closed_trades == (trade_id,), confirmed

    # Published to the Allocator mirror = the CONFIRMED balance.
    assert sink.emitted[-1].balance == 20844.34, sink.emitted[-1]  # type: ignore[attr-defined]
    # Fan-out (a) strategy, (c) event log, (d) Scoring all saw the confirmed close.
    assert strategy.closed and strategy.closed[-1][0] == trade_id
    assert strategy.closed[-1][3] is True, "protective close did not hard-reset the FSM"
    assert "uncertainty" in strategy.closed[-1][2], strategy.closed[-1]
    assert event_log.of(ExitEventKind.CLOSED), event_log.rows
    assert scoring.booked[-1][0] == (trade_id,), scoring.booked
    assert scoring.booked[-1][1] == 500.0, scoring.booked


@pytest.mark.asyncio
async def test_reconcile_is_FALSIFIABLE_publishing_the_INTENT_shows_the_wrong_balance() -> (
    None
):
    """The can-fail: `_PublishesIntentFlatten` commits the pre-flatten projection
    balance, so the published figure is the intent (20344.34) and NOT broker truth
    (20844.34). The assertion that the confirmed balance is the post figure — the
    one the real reconcile passes — fails here, at the published field."""
    sink = RecordingPictureSink()
    book, trade_id = _open_book(sink, balance=20344.34)
    broker = ReconcileBroker(positions=[Position("MESU6", 1, 7800.0)], cash=20344.34)
    broker.realize_on_flatten["MESU6"] = 500.0
    ex = _executor(broker, picture=book, cls=_PublishesIntentFlatten)

    ex.fire(
        FlattenTrigger.UNCERTAINTY,
        symbol="MESU6",
        targets=[CloseTarget(trade_id, "MESU6", "strat-1")],
    )
    confirmed = await ex.reconcile_and_publish()

    # The falsifier published the INTENT — the published balance is the stale
    # projection, which is exactly what the confirmed-state control forbids.
    assert sink.emitted[-1].balance == 20344.34, sink.emitted[-1]  # type: ignore[attr-defined]
    assert confirmed.confirmed_balance != 20844.34, (
        "the falsifier published broker truth — it no longer falsifies"
    )
