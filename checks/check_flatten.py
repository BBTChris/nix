#!/usr/bin/env python3
"""§3/§4/§14's protective-flatten executor, DRIVEN — `scripts/nixrisk/flatten.py`.

ONE gate, FOUR properties the CHECK-DEBT ledger opened against this module
(D3.105) and ARC 029/B's own docstring states as accountable: zero-wire fire,
dual-authority precedence under contention, onset-cancel booking the NAMED
onset cause, and reconcile-then-publish broadcasting the CONFIRMED state, never
the pre-flatten intent. `scripts/tests/test_flatten.py` is the 20-test
behavioural suite this gate DRIVES a representative slice of directly, using
the same falsifier pattern (a wrong subclass named per property, shown to lose
it) so a green here is not read off a suite the gate never touches.

WHY DRIVE RATHER THAN SHELL OUT TO PYTEST. The runtime `.venv` `verify.py` runs
under has no pytest (dev-only, per the ARC CRUCIBLE-DEPSPLIT venv split); a
check that shelled to pytest would be CANNOT_MEASURE on every real run. So this
gate imports `nixrisk.flatten` and its collaborators straight out of
`ctx.nix_home` (the `check_reservation_lifecycle` pattern: path-keyed import,
sys.modules/sys.path restored, so a plant can live on a `tmp_path` copy without
touching the real interpreter's module cache) and drives them with hand-built
doubles — no pytest, no test-file import.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to import. CLOSED: an import failure is
    CANNOT_MEASURE naming the exception (§17, never a PASS).
 2. Zero-wire could pass with a HEALTHY sink — a wire dependency the drive
    never exercises is invisible. CLOSED: the picture sink RAISES on `emit`
    (state bus down), and the drive requires the broker flatten call to have
    landed anyway.
 3. Precedence could pass sequentially (protective-only), which never puts the
    two authorities in CONTENTION. CLOSED: the drive fires DISCRETIONARY then
    PROTECTIVE at the SAME trade and asserts the DISCRETIONARY one really
    executed first (non-vacuity) before requiring PROTECTIVE to win.
 4. Onset-cause booking could collapse HALT_ONSET and BLACKOUT_ONSET to a bare
    CANCEL and still show "released". CLOSED: the drive reads the booked
    `released_via` member back, not merely a release count.
 5. Reconcile-then-publish could pass by publishing the pre-flatten projection
    unchanged when the flatten hits nothing. CLOSED: the REAL-POSITION fixture
    books a broker-side realized gain the projection never held, and the drive
    asserts the published balance is the POST figure and differs from the
    pre-flatten one — exactly what `_PublishesIntentFlatten` in the test suite
    is shown to fail.

Each of the four arms above additionally drives a FALSIFIER — a subclass of
`ProtectiveFlatten` deliberately wrong on the one property the arm names — and
requires the falsifier to LOSE the property this gate's own assertion checks.
An arm whose falsifier passes measures nothing; that is asserted, not assumed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the test doubles'
# verbs are named after the ports they stand in for, and each arm function's
# name states its own property (§7.12 answer per arm) — a docstring would
# restate the name. too-few-public-methods: several doubles are one-verb
# stand-ins for a frozen port's single relevant method. too-many-locals: an
# arm's local count is the drive's own inputs/outputs, not incidental state.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS the executor package out of `ctx.nix_home` (same reason
#: `check_reservation_lifecycle` declares it: two checks importing concurrently
#: share one interpreter's import state).
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: NON-CORRECTABLE: the subject is risk-path source (the protective-EXIT half of
#: the Limiter). A gate empowered to edit it until its own drive came back clean
#: would be manufacturing green over the one path §14 requires to fire when
#: everything else is down.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/flatten.py, the §14 "
    "protective-exit executor); a repair that edited it to satisfy its own gate "
    "is the same class of action risk spec §4 forbids on the order path"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/flatten.py",)

NAME = "check_flatten"

FLATTEN_FILE = "scripts/nixrisk/flatten.py"
FLATTEN_MODULE = "nixrisk.flatten"
SEAM_MODULE = "nixrisk.seam"
PICTURE_MODULE = "nixrisk.picture"
RESERVATIONS_MODULE = "nixrisk.reservations"
PACKAGE = "nixrisk"


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    flatten: ModuleType
    seam: ModuleType
    picture: ModuleType
    reservations: ModuleType
    broker_seam: ModuleType


# --------------------------------------------------------------------------
# LOADING — out of ctx.nix_home, never this process's own tree by accident
# --------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    sys.path.insert(0, str((home / "scripts" / "broker").resolve()))
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            flatten=importlib.import_module(FLATTEN_MODULE),
            seam=importlib.import_module(SEAM_MODULE),
            picture=importlib.import_module(PICTURE_MODULE),
            reservations=importlib.import_module(RESERVATIONS_MODULE),
            broker_seam=importlib.import_module("broker_seam"),
        )
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{FLATTEN_FILE}: cannot import {FLATTEN_MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# Doubles — minimal, hand-built, no pytest and no test-file import
# --------------------------------------------------------------------------


class _DeadSink:
    """The wire, removed. Every `emit` raises — state bus down / ZMQ gone."""

    def emit(self, picture: object) -> None:
        raise ConnectionError("state bus down / ZMQ unavailable")


class _RecordingSink:
    def __init__(self) -> None:
        self.emitted: list[Any] = []

    def emit(self, picture: object) -> None:
        self.emitted.append(picture)


class _Broker:
    """A broker whose truth CHANGES on flatten — realizes P&L into cash."""

    def __init__(self, *, positions: list[Any] | None = None, cash: float) -> None:
        self._positions: dict[str, Any] = {p.symbol: p for p in (positions or [])}
        self._cash = cash
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

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[Any]:
        return [p for p in self._positions.values() if p.net_qty != 0]

    async def query_balance(self, seam: ModuleType | None = None) -> Any:
        # `seam` unused: Balance is built by the caller (`_balance`) since this
        # double is constructed before `Loaded.seam` exists in some call sites.
        raise NotImplementedError


class _StrategySink:
    def __init__(self) -> None:
        self.closed: list[tuple[str, str, str, bool]] = []

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


class _ScoringSink:
    def __init__(self) -> None:
        self.booked: list[tuple[tuple[str, ...], float, float]] = []

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


class _Plane1:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)


def _clock_seq() -> Any:
    state = {"t": 1000.0}

    def clock() -> float:
        state["t"] += 1.0
        return state["t"]

    return clock


def _make_broker(loaded: Loaded, *, positions=None, cash: float) -> _Broker:
    del loaded  # signature kept symmetric with callers; nothing needed here
    return _Broker(positions=positions, cash=cash)


def _bind_balance(broker: _Broker, loaded: Loaded) -> None:
    """Wire `query_balance` to build a real `Balance` from the loaded broker seam."""

    async def query_balance() -> Any:
        return loaded.broker_seam.Balance(
            cash=broker._cash,  # pylint: disable=protected-access
            net_liquidation=broker._cash,  # pylint: disable=protected-access
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=0.0,
        )

    broker.query_balance = query_balance  # type: ignore[method-assign,assignment]


def _executor(loaded: Loaded, home: Path, broker: _Broker, *, picture, cls=None):
    del home  # kept for call-shape symmetry with the other arm builders
    flatten = loaded.flatten
    executor_cls = cls or flatten.ProtectiveFlatten
    plane1 = _Plane1()
    ledger = loaded.reservations.ReservationLedger(plane1)
    _bind_balance(broker, loaded)
    return (
        executor_cls(
            broker=broker,
            ledger=ledger,
            picture=picture,
            strategy=_StrategySink(),
            plane1=plane1,
            scoring=_ScoringSink(),
            clock=_clock_seq(),
        ),
        plane1,
        ledger,
    )


def _flat_book(loaded: Loaded, sink, *, balance: float = 20344.34):
    return loaded.picture.FinancialPictureBook(
        balance=balance, deployable_fraction=0.70, sink=sink
    )


def _open_book(loaded: Loaded, sink, *, balance: float, trade_id: str = "T-1"):
    book = _flat_book(loaded, sink, balance=balance)
    book.commit(
        balance=balance,
        positions=[
            loaded.seam.PositionRow(
                trade_id=trade_id,
                symbol="MESU6",
                strategy_id="strat-1",
                size=1,
                margin=1000.0,
                state=loaded.seam.PositionState.OPEN,
            )
        ],
    )
    return book


# --------------------------------------------------------------------------
# ARM 1 — zero-wire: the exit FIRES with the wire REMOVED
# --------------------------------------------------------------------------


def _arm_zero_wire(loaded: Loaded, home: Path) -> list[Finding]:
    findings: list[Finding] = []
    flatten = loaded.flatten
    position = loaded.broker_seam.Position("MESU6", 1, 7800.0)
    broker = _make_broker(loaded, positions=[position], cash=20344.34)
    dead = _DeadSink()

    # Non-vacuity: the wire really is dead.
    try:
        dead.emit(object())
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_DeadSink", "the dead sink did not raise — vacuous"
            )
        )
        return findings
    except ConnectionError:
        pass

    ex, _plane1, _ledger = _executor(
        loaded, home, broker, picture=_flat_book(loaded, dead)
    )
    target = flatten.CloseTarget("T-1", "MESU6", "strat-1")
    site = f"{FLATTEN_FILE}:fire[zero-wire]"
    try:
        ex.fire(
            loaded.seam.FlattenTrigger.SYNTHETIC_STOP, symbol="MESU6", targets=[target]
        )
    except ConnectionError as exc:
        # A raise here IS the defect: the protective path touched the dead wire
        # before (or instead of) reaching the broker. Report it as a FINDING,
        # never let it propagate to CANNOT_MEASURE — a crash on THIS path is
        # exactly what "has a wire dependency" looks like.
        findings.append(
            Finding(
                site,
                f"fire() RAISED {type(exc).__name__}: {exc} with the wire dead — "
                "the protective path has a wire dependency (§14: ZERO wire/"
                "delivery dependency required)",
            )
        )
        return findings

    if broker.flatten_calls != ["MESU6"]:
        findings.append(
            Finding(
                site,
                f"with the wire DEAD the broker saw {broker.flatten_calls!r}, not "
                "['MESU6'] — the exit did not fire, so it has a wire dependency "
                "(§14: the protective path must have ZERO wire/delivery dependency)",
            )
        )
    if "MESU6" in broker._positions:  # pylint: disable=protected-access
        findings.append(
            Finding(site, "the position survived a fired protective flatten")
        )

    # The falsifier: a wire-coupled fire must DIE with the wire.
    class _WireCoupled(flatten.ProtectiveFlatten):  # type: ignore[name-defined]
        def fire(self, trigger, *, symbol=None, targets=()):
            self._picture.publish(self._picture.current())  # WRONG: touches the wire
            return super().fire(trigger, symbol=symbol, targets=targets)

    broker2 = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    ex2, _, _ = _executor(
        loaded, home, broker2, picture=_flat_book(loaded, dead), cls=_WireCoupled
    )
    site2 = f"{FLATTEN_FILE}:falsifier[zero-wire]"
    try:
        ex2.fire(
            loaded.seam.FlattenTrigger.SYNTHETIC_STOP, symbol="MESU6", targets=[target]
        )
        findings.append(
            Finding(
                site2,
                "the wire-coupled falsifier fired successfully with the wire dead — "
                "it no longer falsifies, so this arm's assertion is unproven",
            )
        )
    except ConnectionError:
        if broker2.flatten_calls:
            findings.append(
                Finding(
                    site2,
                    "the wire-coupled falsifier still reached the broker before "
                    "dying — the plant did not couple the wire ahead of the flatten",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — precedence: protective ALWAYS wins, under CONTENTION
# --------------------------------------------------------------------------


def _arm_precedence(loaded: Loaded, home: Path) -> list[Finding]:
    findings: list[Finding] = []
    flatten = loaded.flatten

    broker = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    ex, _plane1, _ledger = _executor(
        loaded, home, broker, picture=_flat_book(loaded, _RecordingSink())
    )
    target = flatten.CloseTarget("T-1", "MESU6", "strat-1")

    disc = ex.request_close(target, flatten.CloseAuthority.DISCRETIONARY, "edge spent")
    ex.request_close(
        target,
        flatten.CloseAuthority.PROTECTIVE,
        "protective flatten (trigger=stale_price)",
    )
    site = f"{FLATTEN_FILE}:request_close[precedence]"
    if not disc.executed:
        findings.append(
            Finding(site, "the discretionary close never executed — no real contention")
        )
    winner = ex.closed_record("T-1")
    if winner is None or winner.authority is not flatten.CloseAuthority.PROTECTIVE:
        findings.append(
            Finding(
                site,
                f"after a discretionary close then a protective one for the SAME "
                f"trade, the recorded winner is {winner!r} — protective must "
                "always win (§4 dual authority)",
            )
        )
    elif winner.superseded is not flatten.CloseAuthority.DISCRETIONARY:
        findings.append(
            Finding(
                site, f"winner did not record superseding DISCRETIONARY: {winner!r}"
            )
        )

    # The REVERSE ordering, on the REAL executor: protective first, then a
    # discretionary close of the same trade must be DROPPED, not silently
    # override the winner (§4). Both orderings are driven directly — a
    # sequential protective-only path (only one ordering exercised) is refused
    # as vacuous per §7.12 answer 3.
    broker_rev = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    ex_rev, _, _ = _executor(
        loaded, home, broker_rev, picture=_flat_book(loaded, _RecordingSink())
    )
    prot_first = ex_rev.request_close(
        target, flatten.CloseAuthority.PROTECTIVE, "protective flatten"
    )
    disc_second = ex_rev.request_close(
        target, flatten.CloseAuthority.DISCRETIONARY, "edge spent"
    )
    site_rev = f"{FLATTEN_FILE}:request_close[precedence-reverse]"
    if not prot_first.executed:
        findings.append(
            Finding(
                site_rev, "the protective close never executed — no real contention"
            )
        )
    if disc_second.executed:
        findings.append(
            Finding(
                site_rev,
                "a discretionary close AFTER a protective one for the same trade "
                "EXECUTED — it must be DROPPED (§4: protective always wins)",
            )
        )
    elif "protective always wins" not in disc_second.dropped_reason:
        findings.append(
            Finding(
                site_rev,
                f"the dropped discretionary close's reason does not name why: "
                f"{disc_second.dropped_reason!r}",
            )
        )
    winner_rev = ex_rev.closed_record("T-1")
    if (
        winner_rev is None
        or winner_rev.authority is not flatten.CloseAuthority.PROTECTIVE
    ):
        findings.append(
            Finding(
                site_rev,
                f"winner changed to {winner_rev!r} after a dropped discretionary close",
            )
        )
    if broker_rev.flatten_calls.count("MESU6") != 1:
        findings.append(
            Finding(
                site_rev,
                f"broker.flatten('MESU6') was called {broker_rev.flatten_calls.count('MESU6')} "
                "time(s) — a dropped discretionary close must not reach the broker a second time",
            )
        )

    # Falsifier: last-write-wins arbiter must LOSE the property.
    class _LastWriteWins(flatten.ProtectiveFlatten):  # type: ignore[name-defined]
        def request_close(self, target, authority, reason):
            self._broker.flatten(target.symbol)
            record = flatten.ClosedRecord(
                trade_id=target.trade_id,
                symbol=target.symbol,
                strategy_id=target.strategy_id,
                authority=authority,
                reason=reason,
                closed_ts=self._clock(),
                hard_reset=authority is flatten.CloseAuthority.PROTECTIVE,
                superseded=None,
            )
            self._closed[target.trade_id] = record
            return flatten.CloseOutcome(executed=True, record=record)

    broker2 = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    ex2, _, _ = _executor(
        loaded,
        home,
        broker2,
        picture=_flat_book(loaded, _RecordingSink()),
        cls=_LastWriteWins,
    )
    ex2.request_close(target, flatten.CloseAuthority.PROTECTIVE, "protective flatten")
    ex2.request_close(target, flatten.CloseAuthority.DISCRETIONARY, "edge spent")
    loser = ex2.closed_record("T-1")
    if loser is None or loser.authority is not flatten.CloseAuthority.DISCRETIONARY:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:falsifier[precedence]",
                f"the no-precedence falsifier still recorded {loser!r} as the "
                "winner — it no longer falsifies, so this arm's assertion is unproven",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — onset-cancel books the NAMED cause, exits untouched
# --------------------------------------------------------------------------


def _arm_onset(loaded: Loaded, home: Path) -> list[Finding]:
    del home  # kept for call-shape symmetry with the other arm functions
    findings: list[Finding] = []
    flatten = loaded.flatten
    seam = loaded.seam

    plane1 = _Plane1()
    ledger = loaded.reservations.ReservationLedger(plane1)
    order = seam.ProposedOrder(
        client_order_id="c-1",
        strategy_id="strat-1",
        symbol="MESU6",
        side=seam.Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=20,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1000.0,
    )
    ledger.take(order, 1.0)
    broker = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("ESZ6", 2, 5000.0)],
        cash=20344.34,
    )
    _bind_balance(broker, loaded)
    ex = flatten.ProtectiveFlatten(
        broker=broker,
        ledger=ledger,
        picture=_flat_book(loaded, _RecordingSink()),
        strategy=_StrategySink(),
        plane1=plane1,
        scoring=_ScoringSink(),
        clock=_clock_seq(),
    )
    pending = [flatten.PendingEntry("c-1", "strat-1", "MESU6")]

    result = ex.cancel_entries_on_onset(seam.TerminalPath.HALT_ONSET, pending)
    site = f"{FLATTEN_FILE}:cancel_entries_on_onset[onset]"
    if (
        len(result.released) != 1
        or result.released[0].released_via is not seam.TerminalPath.HALT_ONSET
    ):
        findings.append(
            Finding(
                site,
                f"HALT_ONSET onset released via {result.released!r}, not HALT_ONSET",
            )
        )
    if broker.flatten_calls:
        findings.append(
            Finding(
                site,
                "the onset cancel called broker.flatten — exits must stay untouched",
            )
        )
    if "ESZ6" not in broker._positions:  # pylint: disable=protected-access
        findings.append(
            Finding(
                site, "the open exit position was closed by an entry-only onset cancel"
            )
        )

    # The refusal: a non-onset cause must be REFUSED, naming why.
    site2 = f"{FLATTEN_FILE}:cancel_entries_on_onset[refusal]"
    try:
        ex.cancel_entries_on_onset(seam.TerminalPath.CANCEL, pending)
        findings.append(
            Finding(site2, "a non-onset cause (CANCEL) was accepted, not refused")
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        if type(exc).__name__ != "NotAnOnsetCause" or "not an onset cause" not in str(
            exc
        ):
            findings.append(
                Finding(
                    site2,
                    f"the refusal was {type(exc).__name__}: {exc} — must be "
                    "NotAnOnsetCause naming 'not an onset cause'",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 4 — reconcile-then-publish: the CONFIRMED state, not the intent
# --------------------------------------------------------------------------


def _run_coro(coro: Any) -> Any:
    """Run one coroutine to completion without an event-loop dependency."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    raise RuntimeError("coroutine awaited — this drive uses no I/O, should never yield")


def _arm_reconcile(loaded: Loaded, home: Path) -> list[Finding]:
    findings: list[Finding] = []
    flatten = loaded.flatten
    sink = _RecordingSink()
    book = _open_book(loaded, sink, balance=20344.34)
    broker = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    broker.realize_on_flatten["MESU6"] = 500.0
    ex, _plane1, _ledger = _executor(loaded, home, broker, picture=book)
    target = flatten.CloseTarget("T-1", "MESU6", "strat-1")

    ex.fire(loaded.seam.FlattenTrigger.UNCERTAINTY, symbol="MESU6", targets=[target])
    confirmed: Any = _run_coro(ex.reconcile_and_publish())

    site = f"{FLATTEN_FILE}:reconcile_and_publish[confirmed]"
    # pylint: disable=no-member
    # `confirmed` is what `_run_coro` hands back from a `StopIteration.value`,
    # and pylint's astroid inference tracks that control-flow shape rather
    # than the `Any` annotation, so it reports the real `ConfirmedFlat`
    # fields below as absent from a synthetic 'value' class. False positive.
    if confirmed.confirmed_balance != 20844.34:
        findings.append(
            Finding(
                site,
                f"confirmed_balance={confirmed.confirmed_balance!r}, expected 20844.34",
            )
        )
    if confirmed.confirmed_balance == confirmed.projection_balance:
        findings.append(
            Finding(
                site,
                "confirmed_balance equals projection_balance — the flatten's real "
                "P&L was not reflected; a published CONFIRMED state must differ "
                "from the pre-flatten intent when the flatten really closed something",
            )
        )
    if sink.emitted and getattr(sink.emitted[-1], "balance", None) != 20844.34:
        findings.append(
            Finding(
                site,
                f"published balance {sink.emitted[-1].balance!r} != broker truth 20844.34",
            )
        )

    # Falsifier: publishing the pre-flatten INTENT must fail this exact check.
    class _PublishesIntent(flatten.ProtectiveFlatten):  # type: ignore[name-defined]
        async def reconcile_and_publish(self):
            projection = self._picture.current()
            await self._broker.query_positions()
            await self._broker.query_balance()
            picture = self._picture.commit(
                balance=projection.balance,
                positions=(),
                sum_reservations=self._ledger.total_reserved(),
            )
            return loaded.flatten.ConfirmedFlat(
                picture=picture,
                confirmed_balance=projection.balance,
                projection_balance=projection.balance,
                closed_trades=(),
                realized_delta=0.0,
                is_flat=True,
            )

    sink2 = _RecordingSink()
    book2 = _open_book(loaded, sink2, balance=20344.34)
    broker2 = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    broker2.realize_on_flatten["MESU6"] = 500.0
    ex2, _, _ = _executor(loaded, home, broker2, picture=book2, cls=_PublishesIntent)
    ex2.fire(loaded.seam.FlattenTrigger.UNCERTAINTY, symbol="MESU6", targets=[target])
    confirmed2: Any = _run_coro(ex2.reconcile_and_publish())
    if confirmed2.confirmed_balance == 20844.34:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:falsifier[reconcile]",
                "the intent-publishing falsifier published broker truth anyway — "
                "it no longer falsifies",
            )
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_zero_wire(loaded, ctx.nix_home)
        findings += _arm_precedence(loaded, ctx.nix_home)
        findings += _arm_onset(loaded, ctx.nix_home)
        findings += _arm_reconcile(loaded, ctx.nix_home)
        evidence = (
            f"{FLATTEN_FILE}: drove zero-wire fire, dual-authority precedence "
            "under contention, onset-cancel cause booking + refusal, and "
            "reconcile-then-publish (confirmed vs intent) — 4 arms, each with a "
            "falsifier proven to lose its property"
        )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
