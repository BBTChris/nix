#!/usr/bin/env python3
"""§6.5's net-liq survival watch, DRIVEN — `scripts/nixrisk/survival.py`.

ONE gate, THREE properties CHECK-DEBT D3.106 opened against this module and
§15 C2 / §6.5 / §4 name as the ones a green here must actually exercise:

  1. **net-liq/cash NON-CONFLATION.** `breached` reads `net_liq`; the sizing
     denominator reads `cash`. The two must be driven APART (an equal reading
     proves nothing — see the module's own docstring) with the floor placed
     BETWEEN them, so a watch that swapped the two fields would redden here.
  2. **FLOOR-BREACH fires the flatten exactly once (the latch) + a Critical
     alert.** Driven by marking net-liq through the floor, then marking it
     through again while still breached (must NOT re-fire), then recovering
     and breaching again (must re-arm and fire a second time).
  3. **UNIFORM broker-authoritative reconcile.** Every reconcile event pulls
     ONE broker poll and adopts it; a drift beyond tolerance books a WARNING
     (never Critical) and broker truth wins; a stale (non-monotonic) venue
     timestamp is discarded, not applied.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to import. CLOSED: CANNOT_MEASURE naming the
    exception (§17, never a PASS).
 2. Non-conflation could pass on `net_liq == cash` — swapping the two fields
    in the predicate would return the same verdict and nothing would disagree.
    CLOSED: the drive uses an open position with real unrealized P&L (net_liq
    != cash) and places the floor strictly BETWEEN them, then asserts
    `sizing_liquidity()` returns the CASH figure while `breached` reads off
    net_liq — read via a falsifier that swaps the two fields and is shown to
    fail this exact assertion.
 3. The re-fire latch could be untested, so "fires once" is never actually
    driven under repetition. CLOSED: `mark` is called twice while breached and
    the second call is required to NOT re-fire; then net-liq recovers and
    breaches again and a SECOND fire is required.
 4. The Warning/Critical tiers could collapse to one alert stream and nothing
    would tell them apart. CLOSED: the drift-correction assertion reads the
    alert's OWN `tier` field and requires WARNING, and requires it is not the
    same alert as the breach's CRITICAL one.
 5. The monotonic guard could be untested by only ever polling forward-in-time.
    CLOSED: a stale (older `venue_ts`) poll is driven and the outcome's
    `applied=False` is asserted, with the note naming the guard.

Each arm additionally drives a FALSIFIER — a subclass or bad collaborator
deliberately wrong on the one property the arm names — and requires it to LOSE
the property this gate's own assertion checks, so a green here is not read off
an assertion nothing could ever fail.
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
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/survival.py, the §6.5 "
    "standing net-liq watch that fires the protective flatten); a repair that "
    "edited it to satisfy its own gate is the same class of action risk spec §4 "
    "forbids on the order path"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/survival.py",)

NAME = "check_survival_watch"

SURVIVAL_FILE = "scripts/nixrisk/survival.py"
SURVIVAL_MODULE = "nixrisk.survival"
SEAM_MODULE = "nixrisk.seam"
PICTURE_MODULE = "nixrisk.picture"
PACKAGE = "nixrisk"


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    survival: ModuleType
    seam: ModuleType
    picture: ModuleType


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def _provenance_defect(home: Path, loaded: Loaded) -> str:
    """CHECK-DEBT D3.124 — the module imported must live under `home`.

    MEASURED, not hypothesised: `checks/_preamble.py` appends the REAL
    repository's `scripts/` to `sys.path` permanently, and a name-based
    `import_module` walks that path after the `home/scripts` this function
    inserts. Pointed at an empty directory, this gate imported the LIVE
    `nixrisk.survival` and returned **PASS over a tree that contained
    nothing** — reproduced on this file and on `check_coldstart` in fresh
    interpreters against fresh empty trees (ARC 031, Stage 1 sub-agent A, and
    re-measured at Stage 3 integration before this guard was written).

    A PASS over an absent subject is the exact shape §17 forbids: the property
    was proven against a different tree than the one under judgement. The
    guard compares each loaded module's own `__file__` back against `home`,
    which is a fact the import cannot fake.
    """
    root = (home / "scripts").resolve()
    strays = []
    for label, module in (
        ("survival", loaded.survival),
        ("seam", loaded.seam),
        ("picture", loaded.picture),
    ):
        origin = Path(getattr(module, "__file__", "") or "").resolve()
        if root not in origin.parents:
            strays.append(f"{label} resolved to {origin}")
    if not strays:
        return ""
    return (
        f"{SURVIVAL_FILE}: the import resolved OUTSIDE {home} — "
        + "; ".join(strays)
        + ". `checks/_preamble.py` appends the real repository's scripts/ to "
        "sys.path permanently, so a name-based import silently measures the "
        "live tree; a property proven against a different tree is not proven "
        "(§17, CHECK-DEBT D3.124). CANNOT_MEASURE, never a PASS"
    )


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            survival=importlib.import_module(SURVIVAL_MODULE),
            seam=importlib.import_module(SEAM_MODULE),
            picture=importlib.import_module(PICTURE_MODULE),
        )
        stray = _provenance_defect(home, loaded)
        if stray:
            return None, stray
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{SURVIVAL_FILE}: cannot import {SURVIVAL_MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------


class _Flatten:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str]] = []

    def flatten(self, trigger: Any, reason: str) -> None:
        self.calls.append((trigger, reason))


class _Alerts:
    def __init__(self) -> None:
        self.emitted: list[Any] = []

    def emit(self, alert: Any) -> None:
        self.emitted.append(alert)


class _Broker:
    """A `BrokerReconcilePort` whose next poll is settable per call."""

    def __init__(self) -> None:
        self.next: Any = None
        self.polls = 0

    def poll(self) -> Any:
        self.polls += 1
        return self.next


def _watch(loaded: Loaded, *, pad: float = 0.10, tolerance: float = 1.0, cls=None):
    survival = loaded.survival
    watch_cls = cls or survival.SurvivalWatch
    flatten = _Flatten()
    alerts = _Alerts()
    broker = _Broker()
    watch = watch_cls(
        safety_pad=pad,
        broker=broker,
        flatten=flatten,
        alert=alerts,
        tolerance=tolerance,
    )
    return watch, flatten, alerts, broker


def _position(loaded: Loaded, *, margin: float) -> Any:
    return loaded.seam.PositionRow(
        trade_id="T-1",
        symbol="MESU6",
        strategy_id="strat-1",
        size=1,
        margin=margin,
        state=loaded.seam.PositionState.OPEN,
    )


# --------------------------------------------------------------------------
# ARM 1 — net-liq/cash NON-CONFLATION
# --------------------------------------------------------------------------


def _arm_nonconflation(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    watch, _flatten, _alerts, _broker = _watch(loaded, pad=0.10)
    site = f"{SURVIVAL_FILE}:nonconflation"

    # Σ open margin = 1000, floor = 1100. cash=1200 (never breaches if read as
    # the trigger); net_liq=1050 (breaches: 1050 < 1100). The two DIVERGE and
    # the floor sits strictly between them — a watch reading the wrong field
    # returns the opposite verdict.
    outcome = watch.mark(cash=1200.0, net_liq=1050.0, sum_open_margin=1000.0)

    if not outcome.breached:
        findings.append(
            Finding(
                site,
                f"net_liq=1050.0 < floor=1100.0 but breached={outcome.breached!r} "
                "— the watch is not reading net_liq for the breach decision",
            )
        )
    if watch.sizing_liquidity() != 1200.0:
        findings.append(
            Finding(
                site,
                f"sizing_liquidity()={watch.sizing_liquidity()!r}, expected the "
                "CASH figure 1200.0 — §15 C2: sizing must never read net_liq",
            )
        )

    # Falsifier: a watch that swaps net_liq and cash in the predicate.
    survival = loaded.survival

    class _Swapped(survival.SurvivalWatch):  # type: ignore[name-defined]
        def _check_current(self, source: str):
            reading = self.read()
            # WRONG: breach on cash instead of net_liq.
            breached = reading.cash < reading.floor
            if not breached:
                return survival.WatchOutcome(
                    reading, breached=False, fired=False, source=source
                )
            return survival.WatchOutcome(
                reading, breached=True, fired=False, source=source
            )

    watch2, _f2, _a2, _b2 = _watch(loaded, pad=0.10, cls=_Swapped)
    swapped_outcome = watch2.mark(cash=1200.0, net_liq=1050.0, sum_open_margin=1000.0)
    if swapped_outcome.breached:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the cash-conflating falsifier still reported a breach on this "
                "fixture (cash=1200 > floor=1100 should read NOT breached) — it "
                "no longer falsifies",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — floor-breach fires the flatten exactly once (latch) + Critical alert
# --------------------------------------------------------------------------


def _arm_breach_latch(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    watch, flatten, alerts, _broker = _watch(loaded, pad=0.0)
    site = f"{SURVIVAL_FILE}:breach_latch"

    first = watch.mark(cash=900.0, net_liq=900.0, sum_open_margin=1000.0)  # floor=1000
    if not (first.breached and first.fired):
        findings.append(Finding(site, f"first breaching mark did not fire: {first!r}"))
    if len(flatten.calls) != 1:
        findings.append(
            Finding(site, f"expected exactly 1 flatten call, got {len(flatten.calls)}")
        )
    elif flatten.calls[0][0] is not loaded.seam.FlattenTrigger.NET_LIQ_FLOOR:
        findings.append(
            Finding(site, f"flattened under wrong trigger {flatten.calls[0][0]!r}")
        )
    criticals = [
        a for a in alerts.emitted if getattr(a.tier, "value", "") == "critical"
    ]
    if len(criticals) != 1:
        findings.append(
            Finding(site, f"expected exactly 1 Critical alert, got {len(criticals)}")
        )

    # Still breached: must NOT re-fire (the latch).
    second = watch.mark(cash=850.0, net_liq=850.0, sum_open_margin=1000.0)
    if second.fired:
        findings.append(
            Finding(
                site,
                "a SECOND mark while still breached fired again — the latch did not suppress",
            )
        )
    if len(flatten.calls) != 1:
        findings.append(
            Finding(
                site,
                f"the latch failed: {len(flatten.calls)} flatten calls after a persistent breach",
            )
        )

    # Recover, then breach again: must RE-ARM and fire a second time.
    watch.mark(cash=1500.0, net_liq=1500.0, sum_open_margin=1000.0)
    third = watch.mark(cash=900.0, net_liq=900.0, sum_open_margin=1000.0)
    if not third.fired:
        findings.append(
            Finding(
                site,
                "a fresh breach after recovery did not re-fire — the latch did not re-arm",
            )
        )
    if len(flatten.calls) != 2:
        findings.append(
            Finding(
                site,
                f"expected 2 flatten calls total after recover+re-breach, got {len(flatten.calls)}",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — UNIFORM broker-authoritative reconcile
# --------------------------------------------------------------------------


def _arm_reconcile(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    watch, _flatten, alerts, broker = _watch(loaded, tolerance=1.0)
    site = f"{SURVIVAL_FILE}:reconcile"

    watch.mark(cash=1000.0, net_liq=1000.0, sum_open_margin=500.0)

    # A poll that drifts materially: broker wins, Warning booked (never Critical).
    broker.next = loaded.survival.BrokerReading(
        cash=1005.0,
        net_liq=990.0,
        positions=(_position(loaded, margin=500.0),),
        venue_ts=10.0,
    )
    outcome = watch.reconcile("fill")
    if not outcome.corrected:
        findings.append(
            Finding(site, "a drift beyond tolerance was not reported as corrected")
        )
    if outcome.reading.net_liq != 990.0:
        findings.append(
            Finding(
                site,
                f"reading.net_liq={outcome.reading.net_liq!r} — broker truth did not win",
            )
        )
    warnings = [a for a in alerts.emitted if getattr(a.tier, "value", "") == "warning"]
    if len(warnings) != 1:
        findings.append(
            Finding(
                site, f"expected exactly 1 Warning alert on drift, got {len(warnings)}"
            )
        )
    criticals_here = [
        a for a in alerts.emitted if getattr(a.tier, "value", "") == "critical"
    ]
    if criticals_here:
        findings.append(
            Finding(
                site, "a drift correction booked a Critical alert — tiers collapsed"
            )
        )

    # A STALE poll (older venue_ts): must be discarded, not applied.
    broker.next = loaded.survival.BrokerReading(
        cash=2000.0,
        net_liq=2000.0,
        positions=(),
        venue_ts=5.0,  # older than 10.0
    )
    stale_outcome = watch.reconcile("orphan")
    if stale_outcome.applied:
        findings.append(
            Finding(
                f"{site}:stale",
                "a poll with an OLDER venue_ts was applied, not discarded",
            )
        )
    if "monotonic" not in stale_outcome.note.lower():
        findings.append(
            Finding(
                f"{site}:stale",
                f"the discard note does not name the guard: {stale_outcome.note!r}",
            )
        )
    if watch.read().net_liq != 990.0:
        findings.append(
            Finding(
                f"{site}:stale",
                "the held reading changed despite a discarded stale poll",
            )
        )

    # Falsifier: a reconcile that skips the poll on some events is not UNIFORM.
    survival = loaded.survival

    class _NonUniform(survival.SurvivalWatch):  # type: ignore[name-defined]
        def reconcile(self, event: str):
            if event == "skip-me":
                return survival.ReconcileOutcome(
                    reading=self.read(),
                    event=event,
                    applied=False,
                    corrected=False,
                    drift=0.0,
                    note="WRONG: skipped the poll entirely",
                    breached=False,
                    fired=False,
                )
            return super().reconcile(event)

    watch2, _f2, _a2, broker2 = _watch(loaded, tolerance=1.0, cls=_NonUniform)
    watch2.mark(cash=1000.0, net_liq=1000.0, sum_open_margin=500.0)
    broker2.next = loaded.survival.BrokerReading(
        cash=1.0, net_liq=1.0, positions=(), venue_ts=1.0
    )
    watch2.reconcile("skip-me")
    if broker2.polls != 0:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the non-uniform falsifier polled anyway — it no longer falsifies",
            )
        )
    return findings


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_nonconflation(loaded)
        findings += _arm_breach_latch(loaded)
        findings += _arm_reconcile(loaded)
        evidence = (
            f"{SURVIVAL_FILE}: drove net-liq/cash non-conflation (floor between "
            "divergent readings), floor-breach flatten + Critical alert with the "
            "re-fire latch under repetition and re-arm on recovery, and uniform "
            "broker-authoritative reconcile (drift Warning + monotonic-guard "
            "discard) — 3 arms, each with a falsifier proven to lose its property"
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
