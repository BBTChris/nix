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
 6. Wire-freedom could pass over ONE trigger while another carries a wire —
    which is not hypothetical: answer 2's arm drives `SYNTHETIC_STOP` alone, and
    ARC 038 / sub-agent C filed that gap as FINDING FC5 / D3.373. ARC 048
    re-measured it, and a wire dependency reachable only from `STALE_PRICE` left
    a real position OPEN at the broker while this gate returned rc=0. CLOSED by
    ARM 6, three ways at once: the trigger set is DERIVED from the frozen enum
    minus the subject's own refusals (never a list here, which would go stale
    the moment a member is added); every fireable member is driven in BOTH
    target shapes with the state bus and the Plane-1 delivery wire dead; and the
    live call census of each drive is classified against an ALLOW-set, so a
    transport nobody thought to ban is CANNOT_MEASURE naming it rather than a
    silent pass. The protective-exit sites themselves are derived from the
    subject's AST and every one must have been ENTERED, so an exit added later
    that the drive does not reach reddens instead of hiding.

Each of the arms above additionally drives a FALSIFIER — a subclass of
`ProtectiveFlatten` deliberately wrong on the one property the arm names — and
requires the falsifier to LOSE the property this gate's own assertion checks.
An arm whose falsifier passes measures nothing; that is asserted, not assumed.
"""

# too-many-lines: over the 1000 default, and the overage is ARM 3b's and ARM 6's
# prose plus their staging. (The count itself is NOT restated here — directive 3;
# `wc -l` derives it, and the figure this comment used to carry went stale in the
# same arc that added an arm.) ARC 045 added the onset SELECTION arm and ARC 048
# the exhaustive wire-freedom arm, each with the measurement behind it in its own
# comment block — ARM 3's "exits untouched" clause was green over
# a sweep cancelling a protective order at the venue, because cancelling an order
# is not calling `flatten`. The alternative was to cut the reasoning to satisfy a
# line count, which inverts directive 8: enforce mechanically what can be, and
# the prose that cannot be is what makes the next reader's edit safe. Same call
# `scripts/nixrisk/flatten.py` itself already makes, one file over.
# pylint: disable=too-many-lines

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
                stop_distance=20,
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
# ARM 3b — onset SELECTION: complete (by derivation), selective, scoped
# --------------------------------------------------------------------------
#
# ARC 045 / I11 (§3:172-174, §6.1, §15:995 C4, §14). ARM 3 above owns the
# onset-cancel's CAUSE BOOKING; this arm owns WHICH ORDERS THE SWEEP PICKS, and
# the split is stated in both docstrings so doctrine C.9's boundary survives the
# next author. It is an ARM of this gate and not a new check for the same
# reason: `flatten.ProtectiveFlatten.cancel_entries_on_onset` is one property's
# one instrument, and `check_halt` ARM 4 measures the HALT TRANSITION's use of
# it (that the transition sweeps at all, and books `onset_sweep`), never the
# selection predicate.
#
# Measured before it was written (ARC 045 / S1, at e3bef1a): ARM 3's "exits
# untouched" clause asserted `broker.flatten_calls == []` and that an open
# POSITION survived — and both stay true while the sweep cancels every EXIT
# ORDER it is handed, because cancelling an order is not calling `flatten`. The
# arm was green over a sweep that cancelled a protective stop at the venue and
# reported it on `cancelled` as an entry. That is the §0a shape: a gate green
# over a real gap, in the half that unprotects a live position.


#: What the sweep is contracted to do with each order role. DERIVED against the
#: subject's own `OrderRole` on every run rather than transcribed: a role member
#: that appears in `flatten.py` and not here is an order kind this arm cannot
#: classify, and the arm answers CANNOT_MEASURE naming it (never PASS). That is
#: the D3.440 lesson — a fixed list that meets an unknown kind must say so.
_ROLE_DISPOSITION: dict[str, bool] = {
    "entry": True,  # cancelled by the onset
    "exit": False,  # never cancelled (§3:173)
    "protective": False,  # never cancelled (§3:173, §14)
}


class _AlienKind:
    """An order of a kind no `OrderRole` describes. The sweep must NOT cancel it.

    Not a role member and not a `PendingEntry`: this is the shape a future book
    hands over when a new order kind ships before this path learns about it. The
    only safe dispositions are "refuse and name it"; cancelling it might kill a
    stop, and skipping it quietly might leave an entry live inside the window.
    """

    def __init__(self, coid: str, symbol: str) -> None:
        self.client_order_id = coid
        self.strategy_id = "strat-alien"
        self.symbol = symbol
        self.role = "iceberg"


def _stage_onset_scope(loaded: Loaded) -> tuple[Any, Any, Any, list[str], list[str]]:
    """Real ledger + real executor + the orders the claim is about.

    Returns `(executor, ledger, broker, entry_coids, exit_coids)`. Two symbols
    and two strategies, so a per-symbol blackout has something to leave alone.

    **`c-stop` holds an OUTSTANDING reservation and declares itself PROTECTIVE**,
    and that is deliberate rather than convenient: it is ARC 038 / FA-6's shape
    (CHECK-DEBT D3.354) — an approved entry that has FILLED at the venue and now
    guards the position it opened, its reservation not yet converted to open
    margin. In that state the money record still says "outstanding" and the ROLE
    is the only thing between the sweep and cancelling a live stop, which is
    exactly what makes `_CANCELLABLE_ROLES` load-bearing and plantable.
    """
    flatten = loaded.flatten
    seam = loaded.seam
    plane1 = _Plane1()
    ledger = loaded.reservations.ReservationLedger(plane1)

    def _take(coid: str, symbol: str, strategy: str) -> None:
        ledger.take(
            seam.ProposedOrder(
                client_order_id=coid,
                strategy_id=strategy,
                symbol=symbol,
                side=seam.Side.LONG,
                qty=1,
                margin_per_contract=1000.0,
                stop_ticks=20,
                stop_mode=seam.StopMode.FIXED,
                signal_ts=1000.0,
            ),
            1.0,
        )

    _take("c-a1", "MESU6", "strat-1")
    _take("c-a2", "MESU6", "strat-2")
    _take("c-b1", "MNQU6", "strat-2")
    _take("c-stop", "MESU6", "strat-1")
    _take("c-exit", "MNQU6", "strat-2")

    broker = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 2, 5000.0)],
        cash=20344.34,
    )
    _bind_balance(broker, loaded)
    executor = flatten.ProtectiveFlatten(
        broker=broker,
        ledger=ledger,
        picture=_flat_book(loaded, _RecordingSink()),
        strategy=_StrategySink(),
        plane1=plane1,
        scoring=_ScoringSink(),
        clock=_clock_seq(),
    )
    return executor, ledger, broker, ["c-a1", "c-a2", "c-b1"], ["c-stop", "c-exit"]


def _onset_book(loaded: Loaded) -> list[Any]:
    """The book a §3 pending-entry port hands over: entries AND the exits it knows."""
    flatten = loaded.flatten
    return [
        flatten.PendingEntry("c-a1", "strat-1", "MESU6"),
        flatten.PendingEntry("c-a2", "strat-2", "MESU6"),
        flatten.PendingEntry("c-b1", "strat-2", "MNQU6"),
        flatten.PendingEntry(
            "c-stop", "strat-1", "MESU6", role=flatten.OrderRole.PROTECTIVE
        ),
        flatten.PendingEntry("c-exit", "strat-2", "MNQU6", role=flatten.OrderRole.EXIT),
    ]


def _arm_onset_selection(loaded: Loaded, home: Path) -> tuple[list[Finding], list[str]]:
    """§3:173's SELECTION: every in-scope entry, only entries, only in scope.

    Returns `(findings, unmeasurable)`. A non-empty `unmeasurable` takes the
    whole gate to CANNOT_MEASURE — check-contract rule 10: a safety property
    whose subject cannot be classified is not proven, and the verdict is never
    PASS.
    """
    del home  # kept for call-shape symmetry with the other arm functions
    findings: list[Finding] = []
    unmeasurable: list[str] = []
    flatten = loaded.flatten
    seam = loaded.seam
    site = f"{FLATTEN_FILE}:cancel_entries_on_onset[selection]"

    # -- COMPLETENESS BY DERIVATION, not by a transcribed list --------------
    roles = getattr(flatten, "OrderRole", None)
    if roles is None:
        unmeasurable.append(
            f"{site}: the subject declares no `OrderRole`, so entry-vs-exit is "
            "not expressible in order state and §3:173's partition cannot be "
            "measured at all"
        )
        return findings, unmeasurable
    unknown = [r.value for r in roles if r.value not in _ROLE_DISPOSITION]
    if unknown:
        unmeasurable.append(
            f"{site}: `OrderRole` carries {unknown!r}, which this arm has no "
            "disposition for — an order kind it cannot classify. §3:173 says "
            "the onset cancels ALL pending ENTRY orders, and an unclassified "
            "kind may be one; reporting PASS would certify a completeness this "
            "arm did not measure (D3.440)"
        )
        # DELIBERATELY NOT a return. Contract rule 4 aggregates Fail ABOVE
        # Cannot-measure, and an early return here inverted it: a tree carrying
        # BOTH a new role member and a real incompleteness reported
        # CANNOT_MEASURE and the violation went unnamed. Caught by this arm's
        # own binding control (`test_PLANT_C_and_a_REAL_FAIL_TOGETHER_report_
        # the_FAIL`) rather than reasoned about, which is why that control
        # exists. The roles this arm DOES know are still measurable, so it
        # keeps driving and reports both facts.

    executor, ledger, broker, entry_coids, exit_coids = _stage_onset_scope(loaded)

    # -- NON-VACUITY (rule 4): the scope really holds what the claim is about
    outstanding = {r.client_order_id for r in ledger.outstanding()}
    missing_entries = [c for c in entry_coids if c not in outstanding]
    missing_exits = [c for c in exit_coids if c not in outstanding]
    if missing_entries or missing_exits:
        unmeasurable.append(
            f"{site}: staging failed — entries not reserved {missing_entries!r}, "
            f"exits not reserved {missing_exits!r}; a sweep over an empty scope "
            "proves nothing"
        )
        return findings, unmeasurable
    if not broker._positions:  # pylint: disable=protected-access
        unmeasurable.append(
            f"{site}: staging failed — no OPEN position, so 'a cancelled "
            "protective order leaves a position unprotected' has no subject"
        )
        return findings, unmeasurable

    # -- the drive: a GLOBAL HALT onset over the whole book -----------------
    outcome = executor.cancel_entries_on_onset(
        seam.TerminalPath.HALT_ONSET, tuple(_onset_book(loaded))
    )
    reached_venue = list(broker.cancel_calls)

    # PLANT A — an in-scope entry SURVIVES the onset.
    survivors = [c for c in entry_coids if c not in reached_venue]
    if survivors:
        findings.append(
            Finding(
                site,
                f"INCOMPLETE: pending ENTRY {survivors!r} never reached the venue "
                f"as a cancel on a GLOBAL HALT onset (cancelled={reached_venue!r}) "
                "— each is still WORKING and can fill inside the HALT window it "
                "was not approved for (§3:174, §15:995 C4)",
            )
        )

    # PLANT B — the predicate cancels an EXIT / PROTECTIVE order.
    killed = [c for c in exit_coids if c in reached_venue]
    if killed:
        findings.append(
            Finding(
                site,
                f"OVER-BROAD: the onset cancelled {killed!r} at the venue. "
                f"'c-stop' guards the OPEN MESU6 position "
                f"{sorted(broker._positions)!r}, which the cancel leaves "  # pylint: disable=protected-access
                "UNPROTECTED inside the window — §3:173 is 'exits untouched' and "
                "§14 gives the protective path zero delivery dependency",
            )
        )
    excluded = {c for c, _ in getattr(outcome, "protected", ())}
    if not killed and set(exit_coids) - excluded:
        findings.append(
            Finding(
                site,
                f"the exits {sorted(set(exit_coids) - excluded)!r} were not "
                "cancelled but are not reported on `OnsetCancellation.protected` "
                "either — the exclusion must be ASSERTED, not incidental, or the "
                "next reader cannot tell a guard from an accident",
            )
        )

    # PLANT C — an order kind the sweep cannot classify: never cancelled, named.
    executor2, _l2, broker2, _e2, _x2 = _stage_onset_scope(loaded)
    alien = _AlienKind("c-alien", "MESU6")
    out2 = executor2.cancel_entries_on_onset(
        seam.TerminalPath.HALT_ONSET,
        (flatten.PendingEntry("c-a1", "strat-1", "MESU6"), alien),
    )
    if "c-alien" in broker2.cancel_calls:
        findings.append(
            Finding(
                site,
                "an order of a kind the sweep cannot classify (role='iceberg') "
                "was CANCELLED at the venue — it may be a protective order, and "
                "§3:173 leaves those untouched",
            )
        )
    elif "c-alien" not in {c for c, _ in getattr(out2, "unclassified", ())}:
        findings.append(
            Finding(
                site,
                "an unclassifiable order was silently skipped — not cancelled and "
                "not reported on `unclassified`, so nothing can tell it from an "
                "entry left live inside the window (§3:174)",
            )
        )
    elif getattr(out2, "complete", True) is not False:
        findings.append(
            Finding(
                site,
                "the sweep reported `complete` over an order it could not "
                "classify — §12.10:753's HALT row would claim a clean sweep it "
                "did not perform",
            )
        )

    # -- SCOPE: a per-symbol blackout leaves the other symbol alone ----------
    executor3, _l3, broker3, _e3, _x3 = _stage_onset_scope(loaded)
    executor3.cancel_entries_on_onset(
        seam.TerminalPath.BLACKOUT_ONSET, tuple(_onset_book(loaded)), scope="MESU6"
    )
    scoped = list(broker3.cancel_calls)
    if "c-b1" in scoped:
        findings.append(
            Finding(
                site,
                f"a MESU6 BLACKOUT onset cancelled MNQU6's entry 'c-b1' "
                f"(cancelled={scoped!r}) — §6.1/§6.2/§6.3 windows are PER-SYMBOL "
                "off the live calendar; a blackout on one symbol is not a HALT",
            )
        )
    if not {"c-a1", "c-a2"} <= set(scoped):
        findings.append(
            Finding(
                site,
                f"a MESU6 BLACKOUT onset left MESU6 entries "
                f"{sorted({'c-a1', 'c-a2'} - set(scoped))!r} working "
                "(§3:173 cancels ALL in-scope pending entries)",
            )
        )
    return findings, unmeasurable


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


# --------------------------------------------------------------------------
# ARM 6 — EXHAUSTIVE wire-freedom: EVERY derived trigger, everything DEAD
# --------------------------------------------------------------------------
#
# ARC 048 / I3. ARM 1 above drives ONE trigger (`SYNTHETIC_STOP`) against ONE
# dead surface (the picture sink), and that is the whole of what any standing
# instrument asserted about §14:969's *"the exit/protective path has ZERO
# wire/delivery dependency"*. ARC 038 / sub-agent C measured the gap and
# recorded it as FINDING FC5 / D3.373: a wire dependency reachable from any
# trigger ARM 1 does not drive is INVISIBLE here.
#
# Re-measured at ARC 048 / S1 before this arm was written, so the defect is a
# measurement and not an inference. The frozen `FlattenTrigger` declares SEVEN
# members and `flatten.py` refuses ONE (`SENTINEL`, R4) — so SIX are fireable
# and ARM 1 drives ONE of them. Planting a wire dependency reachable only from
# `STALE_PRICE` (`self._picture.publish(...)` guarded on the trigger) and
# driving it with the wire dead left the position OPEN at the broker:
#
#     synthetic_stop  flattened=True   calls=['MESU6']  still_open=[]
#     stale_price     RAISED ConnectionError  calls=[]  STILL OPEN=['MESU6']
#     === check_flatten rc=0   pass: ...
#
# A real unflattened position, and the gate certifying wire-freedom over it.
#
# THE PROOF IS AN ABSENCE, so it is taken TWO ways and neither alone is enough:
#
#  (a) DRIVEN — every fireable trigger, in BOTH target shapes (§4's untargeted
#      uncertainty flatten and the targeted per-trade close, which are the two
#      DERIVED `self._broker.flatten(...)` sites), with the state bus, the
#      Plane-1 delivery wire and the Allocator all DEAD. Each must still reach
#      the broker.
#
#  (b) DERIVED, BY SHAPE — the live call census of each drive is taken from the
#      running interpreter (`sys.setprofile`) and compared against an ALLOW-set,
#      not merely a ban-list. A ban-list only catches wires someone thought to
#      name; §7.12 asks what would make this pass while measuring nothing, and
#      "a transport nobody listed" is the answer. So a module on the exit path
#      that is neither allowed nor known-banned is UNCLASSIFIABLE and reports
#      CANNOT_MEASURE naming it, never PASS (the I2/I11 completeness lesson).
#      Measured: the shipped exit path enters FOUR module roots and 15 frames
#      total, which is what makes an allow-set honest here rather than noisy.
#
# COMPLETENESS IS THE OBLIGATION (contract rule 4). The set of protective-exit
# sites is DERIVED from the subject's own source by AST shape — an `ast.Call`
# whose func is `.flatten` on an attribute of `self` inside a `ProtectiveFlatten`
# method — never by matching an identifier's spelling (the D3.426 lesson). The
# union of the drives must have ENTERED every derived site; a site the drive
# never reached is a protective exit this arm did not prove anything about.

#: The disposition this arm has for each declared trigger. A member of the
#: frozen `FlattenTrigger` with NO entry here is one this arm cannot classify —
#: it cannot know whether a newly-declared trigger is meant to fire or to be
#: refused, and guessing either way would certify something unmeasured. It
#: reports CANNOT_MEASURE naming the member. Same idiom, same reason, as
#: `_ROLE_DISPOSITION` in ARM 3b.
_TRIGGER_DISPOSITION: dict[str, str] = {
    "synthetic_stop": "fireable",
    "stale_price": "fireable",
    "net_liq_floor": "fireable",
    "session_close": "fireable",
    "uncertainty": "fireable",
    "orphan": "fireable",
    # R4: the Sentinel is the last-resort executor that runs when the Limiter is
    # DEAD (§14), so the live Limiter never issues it. `fire()` raises.
    "sentinel": "refused",
}

#: Modules whose presence on the exit path IS a wire/delivery dependency. Named
#: so the FAIL can say WHICH wire (check contract rule 11 — assert the reason,
#: never the bare outcome). `nixrisk.wal` is deliberately ABSENT: the local WAL
#: append is ON this path by design and is FC1's subject, made non-fatal rather
#: than removed — a bounded in-process buffer append is not a wire.
_BANNED_ON_EXIT: tuple[str, ...] = (
    "asyncio",
    "queue",
    "concurrent",
    "socket",
    "select",
    "selectors",
    "ssl",
    "http",
    "urllib",
    "zmq",
    "subprocess",
    "multiprocessing",
    "nixbus",
    "nixalloc",
    "nixrisk.picture",
    "nixrisk.plane1_sink",
)

#: The ONLY modules the protective path may enter. Derived by measurement, not
#: by permission: the shipped path enters `nixrisk.flatten` (the subject),
#: `nixrisk.seam` (the frozen vocabulary and record types) and `enum` (member
#: value lookup). Anything else is unclassifiable — see the arm's comment.
_ALLOWED_ON_EXIT: tuple[str, ...] = ("enum", "nixrisk.flatten", "nixrisk.seam")


class _DeadPlane1:
    """The Plane-1 delivery wire, unreachable. FC1's subject, kept dead here."""

    def enqueue(self, row: Any) -> None:
        raise OSError(27, "EFBIG: the WAL cannot append (delivery wire dead)")

    def sync_to_disk(self) -> int:
        raise OSError(27, "EFBIG: the WAL cannot append (delivery wire dead)")

    def pending(self) -> int:
        return 0


def _module_of(entry: str) -> str:
    """`nixrisk.flatten.ProtectiveFlatten.fire` -> `nixrisk.flatten`.

    Two segments for a package'd module, one otherwise — the same shape the
    census entries are built in, so classification never needs the qualname.
    """
    parts = entry.split(".")
    if parts[0] in ("nixrisk", "nixbus", "nixalloc", "nixscore", "nixsentinel"):
        return ".".join(parts[:2])
    return parts[0]


def _census(drive: Any) -> tuple[set[str], BaseException | None]:
    """Every `module.qualname` ENTERED during `drive()`, plus what it raised.

    §7.12: reading the source and concluding "there is no such path" is not a
    measurement — a healthy transport hides a dependency it does not exercise,
    and a dead one hides behind the exception. So the census comes from the
    running interpreter and the exception is RETURNED rather than propagated,
    because on this path a raise IS the finding.
    """
    seen: set[str] = set()

    def profile(frame: Any, event: str, arg: Any) -> None:
        del arg
        if event == "call":
            seen.add(
                f"{frame.f_globals.get('__name__', '?')}.{frame.f_code.co_qualname}"
            )

    previous = sys.getprofile()
    raised: BaseException | None = None
    sys.setprofile(profile)
    try:
        drive()
    except BaseException as exc:  # noqa: BLE001  pylint: disable=broad-except
        raised = exc
    finally:
        sys.setprofile(previous)
    return seen, raised


def _self_broker_flatten_line(node: Any) -> int | None:
    """The line of a `self.<anything>.flatten(...)` call, else `None`.

    BY SHAPE, never by spelling (D3.426): the collaborator's ATTRIBUTE NAME is
    not matched, only that the call is `.flatten(...)` on an attribute of
    `self`. Renaming `_broker` does not hide a protective exit from this.

    Returns the LINE rather than a bool so the caller keeps the coordinate
    without re-narrowing the node — the shape test and the site's identity are
    one answer, not two.
    """
    import ast  # pylint: disable=import-outside-toplevel

    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "flatten":
        return None
    owner = func.value
    if not isinstance(owner, ast.Attribute):
        return None
    if not isinstance(owner.value, ast.Name) or owner.value.id != "self":
        return None
    return node.lineno


def _exit_line_in_method(fn: Any) -> int | None:
    """The `self.*.flatten(...)` line inside ONE method body, if any."""
    import ast  # pylint: disable=import-outside-toplevel

    for node in ast.walk(fn):
        line = _self_broker_flatten_line(node)
        if line is not None:
            return line
    return None


def _methods_of_executor(tree: Any) -> list[Any]:
    """Every `def` directly in the `ProtectiveFlatten` class body."""
    import ast  # pylint: disable=import-outside-toplevel

    return [
        fn
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef) and cls.name == "ProtectiveFlatten"
        for fn in cls.body
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _exit_sites_in(tree: Any) -> dict[str, int]:
    """`ProtectiveFlatten` methods holding a `self.*.flatten(...)` call."""
    sites: dict[str, int] = {}
    for fn in _methods_of_executor(tree):
        line = _exit_line_in_method(fn)
        if line is not None:
            sites[fn.name] = line
    return sites


def _derive_exit_sites(home: Path) -> tuple[dict[str, int], str | None]:
    """The protective-exit sites the drive must reach for the proof to be complete."""
    import ast  # pylint: disable=import-outside-toplevel

    try:
        tree = ast.parse((home / FLATTEN_FILE).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return {}, f"cannot parse {FLATTEN_FILE}: {type(exc).__name__}: {exc}"
    sites = _exit_sites_in(tree)
    if not sites:
        return {}, (
            f"{FLATTEN_FILE}: the AST derivation found NO `self._broker.flatten("
            ")` site inside `ProtectiveFlatten` — the protective-exit set cannot "
            "be derived, so completeness is unmeasured (§17: never a PASS)"
        )
    return sites, None


def _drive_one(loaded: Loaded, trigger: Any, *, targeted: bool, cls: Any = None):
    """One trigger, one target shape, EVERYTHING dead. Returns the observation."""
    broker = _make_broker(
        loaded,
        positions=[loaded.broker_seam.Position("MESU6", 1, 7800.0)],
        cash=20344.34,
    )
    plane1 = _DeadPlane1()
    flatten = loaded.flatten
    executor_cls = cls or flatten.ProtectiveFlatten
    _bind_balance(broker, loaded)
    ledger = loaded.reservations.ReservationLedger(_Plane1())
    executor = executor_cls(
        broker=broker,
        ledger=ledger,
        picture=_flat_book(loaded, _DeadSink()),
        strategy=_StrategySink(),
        plane1=plane1,
        scoring=_ScoringSink(),
        clock=_clock_seq(),
    )
    # THE ALLOCATOR. §3:172 — *"Exit never routes through Allocator."* There is
    # no dead Allocator double here and that is deliberate: `ProtectiveFlatten`
    # takes no allocator collaborator at all, so injecting one to watch it go
    # unused would be a prop, not a measurement (directive 1 — prove the
    # property, not a proxy for it). The real assertion is the census below,
    # where `nixalloc` and `nixbus` are BANNED and any module outside the
    # allow-set is unclassifiable: an exit that reached the Allocator by ANY
    # route — import, mirror read, bus round-trip — puts a frame on this path.
    targets = [flatten.CloseTarget("T-1", "MESU6", "strat-1")] if targeted else []
    seen, raised = _census(
        lambda: executor.fire(trigger, symbol="MESU6", targets=targets)
    )
    return broker, seen, raised


def _derive_fireable(loaded: Loaded, site: str) -> tuple[list[Any], list[str]]:
    """DERIVATION 1 — the trigger vocabulary, off the frozen enum.

    The set is the enum MINUS the subject's own refusals, and both halves have
    to agree with this arm's disposition table or nothing is driven: a member
    with no disposition, or one the subject and the table classify differently,
    is a trigger whose REQUIRED BEHAVIOUR is undefined here. §17 answers that
    with CANNOT_MEASURE, never a guess.
    """
    unmeasurable: list[str] = []
    fireable: list[Any] = []
    refused_by_subject = set(loaded.flatten._R4_TRIGGERS)  # pylint: disable=protected-access
    for trigger in loaded.seam.FlattenTrigger:
        disposition = _TRIGGER_DISPOSITION.get(trigger.value)
        if disposition is None:
            unmeasurable.append(
                f"{site}: `FlattenTrigger` declares {trigger.value!r}, which this "
                "arm has NO disposition for — it cannot know whether a newly "
                "declared protective trigger is meant to fire or to be refused, "
                "and either guess would certify a path it never drove. §3:169's "
                "trigger set is the spec's, so a member appearing here is a "
                "question for the architect, not for this gate (§17: never a PASS)"
            )
            continue
        subject_refuses = trigger in refused_by_subject
        if subject_refuses != (disposition == "refused"):
            unmeasurable.append(
                f"{site}: {trigger.value!r} is dispositioned {disposition!r} here "
                f"but the subject's own `_R4_TRIGGERS` "
                f"{'refuses' if subject_refuses else 'does not refuse'} it — the "
                "arm and the subject disagree about what this trigger DOES, so "
                "what it must prove is undefined (§17: never a PASS)"
            )
            continue
        if disposition == "fireable":
            fireable.append(trigger)
    if not unmeasurable and not fireable:
        unmeasurable.append(
            f"{site}: the derivation produced NO fireable trigger — there is "
            "nothing to drive, so wire-freedom is unmeasured (§17)"
        )
    return fireable, unmeasurable


def _wire_is_really_dead(site: str) -> list[Finding]:
    """NON-VACUITY: each double REJECTS, so "survived" is not "never touched"."""
    findings: list[Finding] = []
    for name, probe in (
        ("the state bus", lambda: _DeadSink().emit(object())),
        ("the Plane-1 delivery wire", lambda: _DeadPlane1().enqueue(object())),
    ):
        rejected: BaseException | None = None
        try:
            probe()
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
            # ANY raise is the proof: the double is unreachable, not merely
            # idle. The exception TYPE is not asserted because the double's job
            # is to be dead, and pinning the type here would make this control
            # fail for a change in how deadness is spelled.
            rejected = exc
        if rejected is None:
            findings.append(
                Finding(site, f"{name} double did not reject — the drive is VACUOUS")
            )
    return findings


def _classify_census(
    seen: set[str], label: str, site: str
) -> tuple[list[Finding], list[str]]:
    """Each entered module: allowed, a NAMED wire, or UNCLASSIFIED.

    The third bucket is the point. A ban-list only catches transports someone
    thought to name, so an unknown module on the exit path is CANNOT_MEASURE
    naming it — never quietly clean (§17, and the I2/I11 completeness lesson).
    """
    findings: list[Finding] = []
    unmeasurable: list[str] = []
    for entry in sorted(seen):
        module = _module_of(entry)
        if module in _ALLOWED_ON_EXIT or module == __name__:
            continue
        banned = next(
            (b for b in _BANNED_ON_EXIT if module == b or module.startswith(b + ".")),
            None,
        )
        if banned is not None:
            findings.append(
                Finding(
                    site,
                    f"{label} ENTERED {entry} — {banned} on the protective path "
                    "IS a wire/delivery dependency (§14:969 gives the exit path "
                    "ZERO)",
                )
            )
        else:
            unmeasurable.append(
                f"{site}: {label} entered {entry}, a module this arm can neither "
                "allow nor name as a wire. An allow-set is used precisely because "
                "a ban-list only catches transports someone thought to list, so an "
                "unknown module on the exit path is UNCLASSIFIED, never clean "
                "(§17: never a PASS)"
            )
    return findings, unmeasurable


def _judge_drive(broker: Any, raised: BaseException | None, label: str, site: str):
    """One drive's verdict: did it flatten, with the wire dead?"""
    findings: list[Finding] = []
    still_open = sorted(broker._positions)  # pylint: disable=protected-access
    if raised is not None:
        findings.append(
            Finding(
                site,
                f"{label} RAISED {type(raised).__name__}: {raised} with the wire "
                f"DEAD, leaving {still_open!r} OPEN at the broker — the protective "
                "path has a wire/delivery dependency (§14:969: ZERO wire "
                "dependency; §3:172: exit never routes through the Allocator)",
            )
        )
        return findings
    if broker.flatten_calls != ["MESU6"]:
        findings.append(
            Finding(
                site,
                f"{label}: with the wire DEAD the broker saw "
                f"{broker.flatten_calls!r}, not ['MESU6'] — the exit did not fire "
                f"and {still_open!r} is still OPEN (§14:969)",
            )
        )
    if still_open:
        findings.append(
            Finding(
                site,
                f"{label}: {still_open!r} survived a fired protective flatten "
                "(§14:968 — every uncertainty resolves toward FLAT)",
            )
        )
    return findings


def _drive_every(
    loaded: Loaded, fireable: list[Any], site: str
) -> tuple[list[Finding], list[str], set[str]]:
    """EVERY fireable trigger, BOTH target shapes, everything dead."""
    findings: list[Finding] = []
    unmeasurable: list[str] = []
    entered: set[str] = set()
    for trigger in fireable:
        for targeted in (True, False):
            shape = "targeted" if targeted else "untargeted"
            label = f"trigger={trigger.value} ({shape})"
            broker, seen, raised = _drive_one(loaded, trigger, targeted=targeted)
            entered |= seen
            findings += _judge_drive(broker, raised, label, site)
            if raised is not None:
                continue
            census_findings, census_unmeasurable = _classify_census(seen, label, site)
            findings += census_findings
            unmeasurable += census_unmeasurable
    return findings, unmeasurable, entered


def _completeness(sites: dict[str, int], entered: set[str], site: str) -> list[Finding]:
    """Every DERIVED protective-exit site must have been ENTERED (rule 4)."""
    reached = {entry.split(".")[-1] for entry in entered}
    missed = {name: line for name, line in sites.items() if name not in reached}
    if not missed:
        return []
    return [
        Finding(
            site,
            "the drive never entered "
            + ", ".join(
                f"ProtectiveFlatten.{n} ({FLATTEN_FILE}:{ln})"
                for n, ln in sorted(missed.items(), key=lambda kv: kv[1])
            )
            + " — a DERIVED protective-exit site this arm proved nothing about, so "
            "wire-freedom is not complete over the subject (contract rule 4: "
            "completeness is the obligation)",
        )
    ]


def _census_is_not_blind(loaded: Loaded, trigger: Any) -> list[Finding]:
    """NON-VACUITY: a wire touch that EXISTS must appear in the census.

    §7.12 — an instrument that cannot see the thing it is looking for reports
    its absence just as confidently as a clean path does.
    """
    flatten = loaded.flatten

    class _WireCoupledEvery(flatten.ProtectiveFlatten):  # type: ignore[name-defined]
        def fire(self, trigger, *, symbol=None, targets=(), reason=None):
            self._picture.publish(self._picture.current())  # WRONG: touches the wire
            return super().fire(trigger, symbol=symbol, targets=targets, reason=reason)

    findings: list[Finding] = []
    site = f"{FLATTEN_FILE}:falsifier[wire-freedom]"
    _broker, seen, raised = _drive_one(
        loaded, trigger, targeted=True, cls=_WireCoupledEvery
    )
    if not any(_module_of(entry) == "nixrisk.picture" for entry in seen):
        findings.append(
            Finding(
                site,
                "the census did NOT see the wire-coupled falsifier's publish — it "
                "is blind, so this arm's absence proof is unproven. Census held "
                f"{sorted(e for e in seen if 'picture' in e)!r}",
            )
        )
    if raised is None:
        findings.append(
            Finding(
                site,
                "the wire-coupled falsifier fired successfully with the wire dead "
                "— it no longer falsifies",
            )
        )
    return findings


def _arm_wire_freedom(loaded: Loaded, home: Path) -> tuple[list[Finding], list[str]]:
    site = f"{FLATTEN_FILE}:fire[wire-freedom]"

    fireable, unmeasurable = _derive_fireable(loaded, site)
    if unmeasurable:
        return [], unmeasurable

    sites, site_error = _derive_exit_sites(home)
    if site_error is not None:
        return [], [site_error]

    vacuous = _wire_is_really_dead(site)
    if vacuous:
        return vacuous, []

    findings, unmeasurable, entered = _drive_every(loaded, fireable, site)
    findings += _completeness(sites, entered, site)
    findings += _census_is_not_blind(loaded, fireable[0])
    return findings, unmeasurable


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_zero_wire(loaded, ctx.nix_home)
        findings += _arm_precedence(loaded, ctx.nix_home)
        findings += _arm_onset(loaded, ctx.nix_home)
        selection, unmeasurable = _arm_onset_selection(loaded, ctx.nix_home)
        findings += selection
        findings += _arm_reconcile(loaded, ctx.nix_home)
        wire_free, wire_unmeasurable = _arm_wire_freedom(loaded, ctx.nix_home)
        findings += wire_free
        unmeasurable += wire_unmeasurable
        evidence = (
            f"{FLATTEN_FILE}: drove zero-wire fire, dual-authority precedence "
            "under contention, onset-cancel cause booking + refusal, onset "
            "SELECTION (complete by derivation over the subject's own OrderRole "
            "/ selective / per-symbol scope, 3 entries + 2 exits + 1 open "
            "position staged), reconcile-then-publish (confirmed vs intent), and "
            "EXHAUSTIVE wire-freedom (every fireable FlattenTrigger the frozen "
            "enum declares, in BOTH target shapes, with the state bus and the "
            "Plane-1 delivery wire DEAD; each drive's live call census "
            "classified against an allow-set, and every AST-derived "
            "self._broker.flatten() site required to have been entered) "
            "— 6 arms, each with a falsifier proven to lose its property"
        )
        if unmeasurable and not findings:
            # Rule 10 / §17: the selection arm could not classify its subject,
            # so completeness is UNMEASURED. Never PASS. A real FAIL still
            # outranks it (contract rule 4: Fail > Cannot-measure).
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                evidence=evidence,
                detail="; ".join(unmeasurable),
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
