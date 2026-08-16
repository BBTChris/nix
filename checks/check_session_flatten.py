#!/usr/bin/env python3
"""The session-close flatten, DRIVEN across its own deadline.

ONE gate, ONE property in three parts (`nix_check_contract.md` §5.5).

Every `§` below cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another
document is named on the line. In that document:

    part 1  at `SESSION_FLATTEN_LEAD_MIN` before a symbol's session close, the
        Limiter force-flattens that symbol with `reason=session` — and a tick
        BEFORE the deadline does nothing at all (§6.1b:340-342);
    part 2  a market halted at the deadline is NOT reported as a flatten. The
        verdict is distinguishable from a clean one by a caller, and the
        residual risk is stated where a reader meets it (§12.6:641-642);
    part 3  the ordering invariant `SESSION_FLATTEN_LEAD_MIN < EOD_BLACKOUT_MIN
        − pad` is boot-validated PER SYMBOL, and an inverted per-symbol pair is
        REJECTED naming the symbol (§6.1b:346-348).

------------------------------------------------------------------------------
THE TRAP, NAMED FIRST, BECAUSE IT IS WHAT THIS GATE IS FOR
------------------------------------------------------------------------------
**A flatten gate whose deadline never arrives is green over an idle scheduler.**
Every tick returns `NOT_DUE`, no broker call is ever made, and every assertion
about firing is vacuously skipped. So the drive here CROSSES the deadline: it
ticks at `deadline − 1 min`, asserts the broker call list is EMPTY, then ticks at
`deadline + 1 s` and requires the flatten to have landed. The before-tick
assertion is not decoration — it is what makes the after-tick informative.

The same discipline on the other two: the halted arm HALTS the venue (having
first run the identical rig TRADABLE), and the config arm FEEDS AN INVALID SET
rather than only a valid one.

------------------------------------------------------------------------------
WHY DRIVE RATHER THAN SHELL OUT TO PYTEST
------------------------------------------------------------------------------
The runtime `.venv` `verify.py` runs under has no pytest (dev-only, per the ARC
CRUCIBLE-DEPSPLIT venv split); a check that shelled to pytest would be
CANNOT_MEASURE on every real run. So this gate imports `nixrisk.session` and its
collaborators straight out of `ctx.nix_home` — the `check_flatten` pattern:
path-keyed import with `sys.modules`/`sys.path` restored — and drives them with
hand-built doubles. No pytest, no test-file import.

------------------------------------------------------------------------------
`debug.md` §7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?
------------------------------------------------------------------------------
 1. The subject could fail to import. CLOSED: an import failure is
    CANNOT_MEASURE naming the exception (§17, never a PASS).
 2. **The deadline could never arrive.** CLOSED: `_arm_deadline` asserts the
    pre-deadline tick produced `NOT_DUE` AND that the broker saw nothing, then
    asserts the post-deadline tick fired. A rig that could not fire would redden
    on the second half; a rig that fired always would redden on the first.
 3. **The market could never halt.** CLOSED: `_arm_halted` drives ONE rig
    through `TRADABLE` (pre-deadline) and then `HALTED` (at the deadline), so
    the riding verdict is shown to be a function of the venue state rather than
    a constant. It additionally requires the broker call list to be EMPTY —
    §4's guard refuses to fire into a shut venue — which a constant-verdict
    implementation cannot produce.
 4. **The honesty could be untestable** because a caller cannot tell the cases
    apart. CLOSED: `_arm_distinguishable` compares a clean outcome and a riding
    one on FOUR independent channels (the verdict member, the `exposure_rides`
    predicate, the residual-risk sentence, the §12.9 alert tier) and requires
    all four to differ — and refuses to compare at all unless the clean
    reference really did reach FLAT_CONFIRMED.
 5. **The config validator could accept everything.** CLOSED: `_arm_config`
    feeds an INVERTED per-symbol pair over a throwaway copy of `risks/` and
    requires the rejection message to name the SYMBOL; it then re-runs the
    unmodified copy and requires it to LOAD, so a validator that rejected
    everything is caught too.
 6. **A falsifier could stop falsifying**, leaving "the real one passed"
    uninformative. CLOSED: `_arm_deadline` and `_arm_distinguishable` each drive
    a subclass of `SessionFlattener` deliberately wrong on the one property they
    name, and the gate FAILS if the falsifier passes.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the doubles' verbs are
# named after the ports they stand in for, and each arm function's name states
# its own property — a docstring would restate the name.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS the scheduler package out of `ctx.nix_home` and writes a
#: throwaway copy of `risks/` under the system temp dir for the config arm.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
)
#: NON-CORRECTABLE: the subject is risk-path source — the §6.1b deadline that
#: enforces the never-hold-overnight mandate. A gate empowered to edit it until
#: its own drive came back clean would be manufacturing green over the one
#: backstop that keeps a position from crossing a session boundary.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/session.py, the §6.1b "
    "session-close flatten deadline, and scripts/risk_config.py's boot "
    "validator); a repair that edited either to satisfy its own gate is the "
    "same class of action risk spec §4 forbids on the order path"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/session.py",
    "risks/limiter.config.json",
)

NAME = "check_session_flatten"

SESSION_FILE = "scripts/nixrisk/session.py"
CONFIG_FILE = "risks/limiter.config.json"
PACKAGE = "nixrisk"

#: The symbol the config arm ADDS an inverted per-symbol override for. In the
#: §7:495 scope and deliberately not a symbol the shipped map already names — the
#: map holds deviations only and ships empty, so the drive has to introduce one.
VICTIM_SYMBOL = "ES"

#: The one crossing every arm drives. A close, its §6.1b deadline at a 10-minute
#: lead, and an instant strictly either side of that deadline.
CLOSE = datetime(2026, 8, 20, 21, 0, tzinfo=UTC)
DEADLINE = CLOSE - timedelta(minutes=10)
BEFORE = DEADLINE - timedelta(minutes=1)
AFTER = DEADLINE + timedelta(seconds=1)


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    session: ModuleType
    flatten: ModuleType
    picture: ModuleType
    reservations: ModuleType
    seam: ModuleType
    survival: ModuleType
    broker_seam: ModuleType
    risk_config: ModuleType


# --------------------------------------------------------------------------
# LOADING — out of ctx.nix_home, never this process's own tree by accident
# --------------------------------------------------------------------------


#: Every top-level module name this gate resolves out of `ctx.nix_home`. ALL of
#: them are purged and restored, not just the package: a module left cached from
#: a previous `home` would be measured while a different tree was named, which
#: the origin check below turns from a silent wrong measurement into a loud
#: CANNOT_MEASURE — but purging is the fix, and the origin check is the guard.
_OWNED_ROOTS: tuple[str, ...] = (PACKAGE, "risk_config", "broker_seam")


def _owned(name: str) -> bool:
    return name in _OWNED_ROOTS or name.startswith(f"{PACKAGE}.")


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [key for key in sys.modules if _owned(key)]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {key: value for key, value in sys.modules.items() if _owned(key)}
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    sys.path.insert(0, str((home / "scripts" / "broker").resolve()))
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            session=importlib.import_module("nixrisk.session"),
            flatten=importlib.import_module("nixrisk.flatten"),
            picture=importlib.import_module("nixrisk.picture"),
            reservations=importlib.import_module("nixrisk.reservations"),
            seam=importlib.import_module("nixrisk.seam"),
            survival=importlib.import_module("nixrisk.survival"),
            broker_seam=importlib.import_module("broker_seam"),
            risk_config=importlib.import_module("risk_config"),
        )
        # THE SUBJECT MUST BE THE ONE UNDER `home`. `sys.path` may already carry
        # the canonical tree (a test process, another check), and an import that
        # silently resolved there would drive the SHIPPED module while claiming
        # to drive the copy — a gate measuring a different file than it names.
        root = str(home.resolve())
        for name, module in loaded._asdict().items():
            origin = getattr(module, "__file__", "") or ""
            if not origin.startswith(root):
                return None, (
                    f"{SESSION_FILE}: {name} resolved to {origin!r}, which is "
                    f"OUTSIDE {root} — the subject under measurement is not the "
                    "one named (§17: never a PASS)"
                )
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{SESSION_FILE}: cannot import nixrisk.session from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# Doubles — minimal, hand-built, no pytest and no test-file import
# --------------------------------------------------------------------------


class _Calendar:
    def __init__(self) -> None:
        self.closes = [CLOSE, CLOSE + timedelta(days=1)]

    def next_close(self, symbol: str, at: datetime) -> datetime | None:
        del symbol
        for close in self.closes:
            if close >= at:
                return close
        return None


class _Venue:
    def __init__(self, state: Any) -> None:
        self.state = state
        self.calls: list[tuple[str, datetime]] = []

    def venue_state(self, symbol: str, at: datetime) -> Any:
        self.calls.append((symbol, at))
        return self.state


class _Broker:
    """A broker whose flatten really moves truth — or REFUSES to, on demand."""

    def __init__(self, loaded: Loaded, *, hold: bool) -> None:
        self._loaded = loaded
        self._positions = (
            {"MES": loaded.broker_seam.Position("MES", 1, 7800.0)} if hold else {}
        )
        self.deaf = False
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)
        if self.deaf:
            return
        for sym in [symbol] if symbol else list(self._positions):
            self._positions.pop(sym, None)

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[Any]:
        return [p for p in self._positions.values() if p.net_qty != 0]

    async def query_balance(self) -> Any:
        return self._loaded.broker_seam.Balance(
            cash=20344.34,
            net_liquidation=20344.34,
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=0.0,
        )


class _Strategy:
    def __init__(self) -> None:
        self.closed: list[tuple[str, str, str, bool]] = []

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


class _Scoring:
    def book_realized(self, **kwargs: Any) -> None:
        del kwargs


class _Plane1:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)


class _Alerts:
    def __init__(self) -> None:
        self.emitted: list[Any] = []

    def emit(self, alert: Any) -> None:
        self.emitted.append(alert)


class _Sink:
    def emit(self, picture: Any) -> None:
        del picture


class _Rig(NamedTuple):
    flattener: Any
    broker: _Broker
    venue: _Venue
    alerts: _Alerts
    strategy: _Strategy


def _rig(
    loaded: Loaded, *, open_position: bool = True, venue: Any = None, cls: Any = None
) -> _Rig:
    session = loaded.session
    venue_state = venue if venue is not None else session.VenueState.TRADABLE
    broker = _Broker(loaded, hold=open_position)
    book = loaded.picture.FinancialPictureBook(
        balance=20344.34, deployable_fraction=0.70, sink=_Sink()
    )
    if open_position:
        book.commit(
            positions=[
                loaded.seam.PositionRow(
                    trade_id="T-1",
                    symbol="MES",
                    strategy_id="S-1",
                    size=1,
                    margin=1200.0,
                    state=loaded.seam.PositionState.OPEN,
                    stop_distance=8,
                )
            ]
        )
    plane1 = _Plane1()
    strategy = _Strategy()
    executor = loaded.flatten.ProtectiveFlatten(
        broker=broker,
        ledger=loaded.reservations.ReservationLedger(plane1),
        picture=book,
        strategy=strategy,
        plane1=plane1,
        scoring=_Scoring(),
        clock=lambda: 1000.0,
    )
    venue_double = _Venue(venue_state)
    alerts = _Alerts()
    flattener = (cls or session.SessionFlattener)(
        calendar=_Calendar(),
        venue=venue_double,
        book=book,
        executor=executor,
        alert=alerts,
        lead_min={"MES": 10},
        symbols=("MES",),
    )
    return _Rig(flattener, broker, venue_double, alerts, strategy)


def _tick(rig: _Rig, at: datetime) -> Any:
    return asyncio.run(rig.flattener.tick_async(at))


# --------------------------------------------------------------------------
# ARM 1 (B1) — the drive ACROSS the deadline, and reason=session
# --------------------------------------------------------------------------


def _arm_deadline(loaded: Loaded) -> list[Finding]:
    session = loaded.session
    site = f"{SESSION_FILE}:deadline"
    findings: list[Finding] = []
    rig = _rig(loaded)

    before = _tick(rig, BEFORE)
    before_verdicts = [outcome.verdict for outcome in before.outcomes]
    if before_verdicts != [session.SessionFlattenVerdict.NOT_DUE]:
        findings.append(
            Finding(
                site, f"pre-deadline tick produced {before_verdicts}, expected NOT_DUE"
            )
        )
    if rig.broker.flatten_calls:
        findings.append(
            Finding(
                site,
                f"a flatten fired BEFORE the deadline: {rig.broker.flatten_calls} — "
                "the deadline is not what decided it",
            )
        )
    if rig.venue.calls:
        findings.append(
            Finding(site, "a pre-deadline tick polled the venue; NOT_DUE is clock-only")
        )

    after = _tick(rig, AFTER)
    after_verdicts = [outcome.verdict for outcome in after.outcomes]
    if after_verdicts != [session.SessionFlattenVerdict.FLAT_CONFIRMED]:
        findings.append(
            Finding(
                site,
                f"post-deadline tick produced {after_verdicts}, expected "
                "FLAT_CONFIRMED — the deadline did not fire (§6.1b:340)",
            )
        )
    if rig.broker.flatten_calls != ["MES"]:
        findings.append(
            Finding(
                site,
                f"broker flatten calls {rig.broker.flatten_calls!r}, expected "
                "['MES'] — the force-flatten never reached the venue",
            )
        )
    if not after.outcomes:
        findings.append(
            Finding(site, "the post-deadline tick produced NO outcome at all")
        )
    if not rig.strategy.closed:
        findings.append(Finding(site, "§4's fan-out told the strategy nothing"))
    else:
        reason = rig.strategy.closed[-1][2]
        # Compared against the LITERAL from §6.1b:352, never against the
        # subject's own `SESSION_REASON` — that would be the module compared
        # with itself, and a renamed constant would pass on both sides.
        if reason != "session":
            findings.append(
                Finding(
                    site,
                    f"strategy received reason={reason!r}, expected 'session' — "
                    "§6.1b:352 fixes the word",
                )
            )

    # Falsifier: a deadline that never arrives must fail this exact arm.
    # `session` is imported at RUNTIME out of ctx.nix_home, so mypy cannot see
    # the base class at all — the ignore covers the dynamic base, not a
    # typing shortcut in the plant itself.
    class _NeverDue(session.SessionFlattener):  # type: ignore[misc,name-defined]
        def is_due(self, symbol: str, at: datetime) -> bool:
            del symbol, at  # the DEFECT: the deadline is never reached
            return False

        async def _evaluate(self, symbol, at, close, deadline):
            del at  # THE DEFECT: the instant is never compared to the deadline
            return self._outcome(
                symbol,
                close,
                deadline,
                session.SessionFlattenVerdict.NOT_DUE,
            )

    plant = _rig(loaded, cls=_NeverDue)
    _tick(plant, BEFORE)
    plant_after = _tick(plant, AFTER)
    if [o.verdict for o in plant_after.outcomes] != [
        session.SessionFlattenVerdict.NOT_DUE
    ] or plant.broker.flatten_calls:
        findings.append(
            Finding(
                f"{SESSION_FILE}:falsifier[deadline]",
                "the never-due falsifier fired anyway — it no longer falsifies, "
                "so the arm above is not a discriminator",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 (B2) — the §12.6 honesty clause, with the market ACTUALLY HALTED
# --------------------------------------------------------------------------


def _arm_halted(loaded: Loaded) -> list[Finding]:
    session = loaded.session
    site = f"{SESSION_FILE}:halted"
    findings: list[Finding] = []

    rig = _rig(loaded)
    if rig.venue.state is not session.VenueState.TRADABLE:
        findings.append(Finding(site, "the rig did not start TRADABLE; nothing halted"))
    _tick(rig, BEFORE)

    rig.venue.state = session.VenueState.HALTED  # THE MARKET HALTS.
    sweep = _tick(rig, AFTER)
    if not sweep.outcomes:
        return [
            *findings,
            Finding(
                site,
                "the post-deadline tick produced NO outcome at all for the "
                "halted symbol — §12.6's case cannot be reported by a sweep "
                "that reports nothing",
            ),
        ]
    outcome = sweep.outcomes[0]

    if (
        outcome.verdict
        is not session.SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED
    ):
        findings.append(
            Finding(
                site,
                f"a HALTED market at the deadline produced {outcome.verdict} — "
                "§12.6 says a halted market cannot be flattened by any design",
            )
        )
    if rig.broker.flatten_calls:
        findings.append(
            Finding(
                site,
                f"an order was fired into a HALTED venue ({rig.broker.flatten_calls!r}) "
                "— §4's market-tradable guard: flatten is guarded, never blind",
            )
        )
    if not outcome.exposure_rides:
        findings.append(
            Finding(site, "the halted outcome does not report exposure_rides")
        )
    if not outcome.residual_risk:
        findings.append(
            Finding(
                site, "the halted outcome states NO residual risk (§12.6 requires it)"
            )
        )
    if (
        outcome.alert is None
        or outcome.alert.tier is not loaded.survival.AlertTier.CRITICAL
    ):
        findings.append(
            Finding(
                site,
                f"the halted outcome alerted at {getattr(outcome.alert, 'tier', None)}, "
                "expected CRITICAL (§6.1b:349-351, §6.1b:353)",
            )
        )

    return findings


def _arm_distinguishable(loaded: Loaded) -> list[Finding]:
    """A ridden exposure is tellable from a clean flatten, on four channels.

    Split out of `_arm_halted` so each function measures ONE thing: that arm
    establishes that a halted market rides, this one establishes that a caller
    can SEE that it rode. The two were one function and it carried both the
    §12.6 drive and the F13 falsifier, which is two subjects in one place.
    """
    session = loaded.session
    site = f"{SESSION_FILE}:halted"
    findings: list[Finding] = []

    rig = _rig(loaded)
    _tick(rig, BEFORE)
    rig.venue.state = session.VenueState.HALTED
    riding = _tick(rig, AFTER)
    if not riding.outcomes:
        return [Finding(site, "the halted rig produced NO outcome to compare")]
    outcome = riding.outcomes[0]

    # The caller-distinguishability property, on FOUR independent channels.
    clean = _rig(loaded)
    _tick(clean, BEFORE)
    clean_outcome = _tick(clean, AFTER).outcomes[0]
    if clean_outcome.verdict is not session.SessionFlattenVerdict.FLAT_CONFIRMED:
        findings.append(
            Finding(
                site,
                f"the CLEAN reference produced {clean_outcome.verdict}, not "
                "FLAT_CONFIRMED — there is no clean flatten to distinguish a "
                "ridden one FROM, so the four channels below measure nothing",
            )
        )
    else:
        channels = {
            "verdict member": clean_outcome.verdict is not outcome.verdict,
            "exposure_rides predicate": clean_outcome.exposure_rides
            != outcome.exposure_rides,
            "residual-risk sentence": bool(clean_outcome.residual_risk)
            != bool(outcome.residual_risk),
            "§12.9 alert tier": getattr(clean_outcome.alert, "tier", None)
            is not getattr(outcome.alert, "tier", None),
        }
        for channel, distinct in sorted(channels.items()):
            if not distinct:
                findings.append(
                    Finding(
                        site,
                        f"a caller CANNOT tell a ridden exposure from a clean "
                        f"flatten by the {channel}",
                    )
                )

    # The second riding verdict: the order WAS sent and broker truth still holds.
    deaf = _rig(loaded)
    deaf.broker.deaf = True
    _tick(deaf, BEFORE)
    deaf_sweep = _tick(deaf, AFTER)
    if not deaf_sweep.outcomes:
        return [*findings, Finding(site, "the deaf-broker tick produced NO outcome")]
    deaf_outcome = deaf_sweep.outcomes[0]
    if (
        deaf_outcome.verdict
        is not session.SessionFlattenVerdict.EXPOSURE_RIDES_UNCONFIRMED
    ):
        findings.append(
            Finding(
                site,
                f"a flatten the broker ignored produced {deaf_outcome.verdict} — "
                "§4's indeterminate path resolving to NOT flat",
            )
        )
    if deaf_outcome.verdict is outcome.verdict:
        findings.append(
            Finding(
                site,
                "'never sent' and 'sent and ignored' collapse to one verdict — "
                "they are different operator actions",
            )
        )

    # Falsifier: a scheduler that reports success from having FIRED (ARC 022 F13).
    # Dynamic base, same reason as `_NeverDue` above.
    class _SuccessFromHavingFired(session.SessionFlattener):  # type: ignore[misc,name-defined]
        async def _evaluate(self, symbol, at, close, deadline):
            if at < deadline:
                return self._outcome(
                    symbol,
                    close,
                    deadline,
                    session.SessionFlattenVerdict.NOT_DUE,
                )
            targets = self._open_targets(symbol)
            venue = self._venue.venue_state(symbol, at)
            if not targets:
                return self._outcome(
                    symbol,
                    close,
                    deadline,
                    session.SessionFlattenVerdict.NOTHING_OPEN,
                    venue=venue,
                )
            self._executor.fire(
                loaded.seam.FlattenTrigger.SESSION_CLOSE,
                symbol=symbol,
                targets=targets,
                reason="session",
            )
            confirmed = await self._executor.reconcile_and_publish()
            return self._outcome(
                symbol,
                close,
                deadline,
                session.SessionFlattenVerdict.FLAT_CONFIRMED,
                targets,
                venue=venue,
                confirmed=confirmed,
            )

    plant = _rig(loaded, cls=_SuccessFromHavingFired)
    plant.broker.deaf = True
    _tick(plant, BEFORE)
    plant_sweep = _tick(plant, AFTER)
    plant_outcome = plant_sweep.outcomes[0] if plant_sweep.outcomes else None
    if getattr(plant_outcome, "verdict", None) is not (
        session.SessionFlattenVerdict.FLAT_CONFIRMED
    ):
        findings.append(
            Finding(
                f"{SESSION_FILE}:falsifier[halted]",
                "the success-from-having-fired falsifier stopped reporting a "
                "phantom success — it no longer falsifies, so the arm above is "
                "not a discriminator",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 (B1c) — the boot validator REJECTS an inverted PER-SYMBOL pair
# --------------------------------------------------------------------------


def _arm_config(loaded: Loaded, home: Path) -> list[Finding]:
    site = f"{CONFIG_FILE}:ordering.session_flatten_before_eod_blackout"
    findings: list[Finding] = []
    risk_config = loaded.risk_config
    scratch = Path(tempfile.mkdtemp(prefix="check_session_flatten_"))
    try:
        shutil.copytree(home / "risks", scratch / "risks")
        path = scratch / "risks" / "limiter.config.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        # (a) the UNMODIFIED copy must LOAD — a validator that rejects
        #     everything is as useless as one that accepts everything.
        try:
            risk_config.load_risk_configs(scratch)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            findings.append(
                Finding(
                    site,
                    f"the SHIPPED config does not load: {type(exc).__name__}: {exc}",
                )
            )
            return findings

        # (b) the per-symbol override MAP must exist, or the per-symbol half of
        #     §6.1b:346-348 has no physical home to be validated over. It is
        #     legitimately EMPTY on the shipped tree — it holds DEVIATIONS only,
        #     and nothing is CC-calibrated yet — so the test is that the key is
        #     there and is a map, never that it has rows.
        overrides = raw.get("session_flatten_lead_min_by_symbol")
        blackouts = raw.get("eod_blackout_min_by_symbol")
        if not isinstance(overrides, dict):
            findings.append(
                Finding(
                    site,
                    "risks/limiter.config.json carries no "
                    "session_flatten_lead_min_by_symbol map — §6.1b:346-348 holds "
                    "PER SYMBOL and there is no per-symbol set to judge",
                )
            )
            return findings
        if not isinstance(blackouts, dict):
            findings.append(
                Finding(site, "no eod_blackout_min_by_symbol map to judge against")
            )
            return findings

        # (c) THE INVERTED PAIR. One symbol, one knob, everything else legal.
        #     The symbol is ADDED rather than picked out of the map, because the
        #     shipped map is empty by design — and adding one is the stronger
        #     drive anyway: the rule must notice a symbol that was not in the
        #     file at all a moment ago.
        victim = VICTIM_SYMBOL
        blackout = float(blackouts.get(victim, raw["eod_blackout_min"]))
        raw["session_flatten_lead_min_by_symbol"][victim] = blackout + 5
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        try:
            risk_config.load_risk_configs(scratch)
            findings.append(
                Finding(
                    site,
                    f"an INVERTED per-symbol pair for {victim} LOADED — "
                    "§6.1b:348 says config validation rejects any per-symbol set "
                    "violating the ordering invariant, and this validator does not",
                )
            )
        except risk_config.RiskConfigError as exc:
            message = str(exc)
            if "ordering.session_flatten_before_eod_blackout" not in message:
                findings.append(
                    Finding(site, f"rejected under the wrong rule id: {message}")
                )
            if victim not in message:
                findings.append(
                    Finding(
                        site,
                        f"the rejection does not NAME the symbol {victim!r}: "
                        f"{message} — 'the config is invalid' is not an operator "
                        "instruction",
                    )
                )
        return findings
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_deadline(loaded)
        findings += _arm_halted(loaded)
        findings += _arm_distinguishable(loaded)
        findings += _arm_config(loaded, ctx.nix_home)
        evidence = (
            f"{SESSION_FILE}: drove the §6.1b deadline ACROSS itself "
            f"({BEFORE.isoformat()} -> {AFTER.isoformat()}, close "
            f"{CLOSE.isoformat()}, lead 10 min) — pre-deadline tick fired "
            "nothing, post-deadline tick force-flattened with reason=session; "
            "drove the §12.6 honesty clause with the venue ACTUALLY HALTED (no "
            "order sent, Critical alert, residual risk stated) and with a "
            "broker that ignored the flatten (EXPOSURE_RIDES_UNCONFIRMED); and "
            "fed the boot validator an INVERTED per-symbol pair, requiring the "
            "rejection to name the symbol — 4 arms, 2 with falsifiers proven to "
            "lose their property"
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
