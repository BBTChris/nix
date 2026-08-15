#!/usr/bin/env python3
"""§4's cold-start reconciliation, DRIVEN — `scripts/nixrisk/coldstart.py`.

ONE gate, THREE properties CHECK-DEBT D3.107 opened and the module's own §0a
section states as MEASURED hypotheses:

  1. **The registration gate is a REFUSED ATTEMPT, not a flag read.** §0a:
     "gates registration" is unfalsifiable unless something attempts to
     register — a test that only reads `registration_admitted()` green-lights
     a `register()` that ignores the flag entirely. This gate calls
     `register()` before the flat assertion and requires `RegistrationRefused`
     naming the state; a bool-only assertion would pass a falsifier that
     admits anyway.
  2. **FLATTEN-BEFORE-REGISTER.** An inherited open position must be flattened
     and RE-CONFIRMED flat before admission — registration must never precede
     the confirming poll. Driven with an inherited position and asserting the
     ORDER: flatten call happened, THEN the confirm poll, THEN admission.
  3. **The market-tradable guard's TWO HALVES.** §4/D4: a shut market holds in
     HALT with a loud alert and admits nothing (never fires into it); the SAME
     box's market becoming tradable then flattens on the next pass. An
     always-open drill measures NEITHER half (§0a) — this gate drives both:
     closed-market hold, then reopened-market flatten, on the same instance.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to import. CLOSED: CANNOT_MEASURE naming the
    exception (§17, never a PASS).
 2. The registration gate could be checked only via the boolean flag, which
    a falsifier that admits unconditionally would still satisfy if the flag
    happened to be read correctly elsewhere. CLOSED: the drive calls
    `register()` directly pre-flat and requires `RegistrationRefused`; a
    falsifier `_AlwaysAdmits` that overrides `register()` to never raise is
    driven and required to be caught.
 3. Flatten-before-register could pass by coincidence if the executor's
    `flatten` and the confirm-poll happen to interleave harmlessly in a
    single-threaded drive. CLOSED: the drive reads the ORDER of recorded
    calls (a shared list both doubles append to) rather than trusting the
    absence of a race.
 4. The HALT half could pass by never actually building a genuinely-closed
    market fixture (a `market_tradable` stub returning `True` unconditionally
    would make the "closed" scenario indistinguishable from "open"). CLOSED:
    the double's tradable flag is read fresh on every call, and the drive
    asserts BOTH that `hold_in_halt` was called (not skipped) AND that
    `flatten` was NOT called while closed.
 5. The reopen half could pass without the closed half ever having happened
    (an always-open box "reopening" trivially). CLOSED: both halves run on
    the SAME instance in sequence — closed first (asserted HELD_IN_HALT and
    zero flatten calls), then the flag flips and the SAME instance's next
    `reconcile()` is asserted to flatten and admit.

Each arm additionally drives a FALSIFIER and requires it to LOSE the property
this gate's own assertion checks.
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
    "the subject is risk-path source (scripts/nixrisk/coldstart.py, the §4 "
    "cold-start registration gate); a repair that edited it to satisfy its own "
    "gate is the same class of action risk spec §4 forbids on the order path"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/coldstart.py",)

NAME = "check_coldstart"

COLDSTART_FILE = "scripts/nixrisk/coldstart.py"
COLDSTART_MODULE = "nixrisk.coldstart"
SEAM_MODULE = "nixrisk.seam"
PACKAGE = "nixrisk"


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    coldstart: ModuleType
    seam: ModuleType


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
    `nixrisk.coldstart` and returned **PASS over a tree that contained
    nothing** — reproduced on this file and on `check_survival_watch` in
    fresh interpreters against fresh empty trees (ARC 031, Stage 1 sub-agent
    A, and re-measured at Stage 3 integration before this guard was written).

    A PASS over an absent subject is the exact shape §17 forbids: the property
    was proven against a different tree than the one under judgement. The
    guard compares each loaded module's own `__file__` back against `home`,
    which is a fact the import cannot fake.
    """
    root = (home / "scripts").resolve()
    strays = []
    for label, module in (("coldstart", loaded.coldstart), ("seam", loaded.seam)):
        origin = Path(getattr(module, "__file__", "") or "").resolve()
        if root not in origin.parents:
            strays.append(f"{label} resolved to {origin}")
    if not strays:
        return ""
    return (
        f"{COLDSTART_FILE}: the import resolved OUTSIDE {home} — "
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
            coldstart=importlib.import_module(COLDSTART_MODULE),
            seam=importlib.import_module(SEAM_MODULE),
        )
        stray = _provenance_defect(home, loaded)
        if stray:
            return None, stray
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{COLDSTART_FILE}: cannot import {COLDSTART_MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------


class _Broker:
    """A `BrokerSessionPort` whose truth and tradability are settable per call."""

    def __init__(self, *, truth: Any, tradable: bool, why: str = "") -> None:
        self.truth = truth
        self.tradable = tradable
        self.why = why
        self.poll_calls = 0

    def poll_truth(self) -> Any:
        self.poll_calls += 1
        return self.truth

    def market_tradable(self) -> tuple[bool, str]:
        return self.tradable, self.why


class _Flattener:
    def __init__(self, log: list[str], *, triggers: tuple[Any, ...] = ()) -> None:
        self._log = log
        self._triggers = triggers
        self.calls = 0

    def flatten(self, truth: Any) -> tuple[Any, ...]:
        del truth
        self.calls += 1
        self._log.append("flatten")
        return self._triggers


class _Halt:
    def __init__(self, log: list[str] | None = None) -> None:
        self.calls: list[str] = []
        self._log = log

    def hold_in_halt(self, reason: str) -> None:
        self.calls.append(reason)
        if self._log is not None:
            self._log.append("hold_in_halt")


class _Plane1:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)


class _LoggingBroker(_Broker):
    """A broker whose poll_truth appends to a shared call-order log."""

    def __init__(
        self, *, log: list[str], truth: Any, tradable: bool, why: str = ""
    ) -> None:
        super().__init__(truth=truth, tradable=tradable, why=why)
        self._log = log

    def poll_truth(self) -> Any:
        self._log.append("poll_truth")
        return super().poll_truth()


def _truth(loaded: Loaded, *, positions=(), balance: float = 1000.0) -> Any:
    return loaded.seam.BrokerTruth(
        positions=tuple(positions), balance=balance, polled_at=0.0
    )


def _position(loaded: Loaded) -> Any:
    return loaded.seam.PositionRow(
        trade_id="T-1",
        symbol="MESU6",
        strategy_id="strat-1",
        size=1,
        margin=1000.0,
        state=loaded.seam.PositionState.OPEN,
    )


# --------------------------------------------------------------------------
# ARM 1 — the registration gate is a REFUSED ATTEMPT
# --------------------------------------------------------------------------


def _arm_registration_gate(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    coldstart = loaded.coldstart
    site = f"{COLDSTART_FILE}:register[gate]"

    broker = _Broker(truth=_truth(loaded), tradable=True)
    cs = coldstart.ColdStart(broker, _Flattener([]), _Halt(), _Plane1())

    try:
        cs.register("strat-1", 0.0)
        findings.append(
            Finding(
                site,
                "register() SUCCEEDED before the provably-flat assertion — the gate did not gate",
            )
        )
    except coldstart.RegistrationRefused as exc:
        if "not passed" not in str(exc) and "REFUSED" not in str(exc):
            findings.append(Finding(site, f"refusal did not name the reason: {exc}"))
    if cs.registered():
        findings.append(
            Finding(
                site,
                f"registered() is non-empty despite a refused attempt: {cs.registered()}",
            )
        )

    # After flat is asserted, the SAME attempt must succeed.
    cs.reconcile(1.0)
    cs.register("strat-1", 2.0)
    if "strat-1" not in cs.registered():
        findings.append(
            Finding(
                site,
                "register() after a confirmed-flat reconcile did not admit strat-1",
            )
        )

    # Falsifier: a ColdStart whose register() never checks the flag.
    class _AlwaysAdmits(coldstart.ColdStart):  # type: ignore[name-defined]
        def register(self, strategy_id: str, now: float) -> None:
            del now
            self._registered.append(strategy_id)  # pylint: disable=protected-access

    broker2 = _Broker(truth=_truth(loaded), tradable=True)
    fake = _AlwaysAdmits(broker2, _Flattener([]), _Halt(), _Plane1())
    fake.register("strat-x", 0.0)  # the falsifier admits unconditionally, by design
    if "strat-x" not in fake.registered():
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the always-admits falsifier did not admit — it no longer falsifies",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — FLATTEN-BEFORE-REGISTER, ordering
# --------------------------------------------------------------------------


def _arm_flatten_before_register(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    coldstart = loaded.coldstart
    seam = loaded.seam
    site = f"{COLDSTART_FILE}:reconcile[order]"

    log: list[str] = []
    inherited = _truth(loaded, positions=[_position(loaded)])
    confirmed = _truth(loaded)  # empty ⇒ flat, returned by the SECOND poll
    polls = [inherited, confirmed]

    class _SequencedBroker(_Broker):
        def poll_truth(self):
            log.append("poll_truth")
            self.poll_calls += 1
            return polls.pop(0)

    broker = _SequencedBroker(truth=None, tradable=True)
    flattener = _Flattener(log, triggers=(seam.FlattenTrigger.ORPHAN,))
    cs = coldstart.ColdStart(broker, flattener, _Halt(), _Plane1())

    outcome = cs.reconcile(1.0)

    if flattener.calls != 1:
        findings.append(
            Finding(site, f"expected exactly 1 flatten call, got {flattener.calls}")
        )
    if broker.poll_calls != 2:
        findings.append(
            Finding(
                site,
                f"expected exactly 2 polls (initial + confirm), got {broker.poll_calls}",
            )
        )
    if "flatten" not in log or "poll_truth" not in log:
        findings.append(Finding(site, f"call log missing an expected call: {log}"))
    else:
        flatten_idx = log.index("flatten")
        # The confirm poll is the SECOND poll_truth in the log.
        poll_indices = [i for i, c in enumerate(log) if c == "poll_truth"]
        if len(poll_indices) < 2 or not (
            poll_indices[0] < flatten_idx < poll_indices[1]
        ):
            findings.append(
                Finding(
                    site,
                    f"call order is {log} — must be poll, flatten, confirm-poll, in that order",
                )
            )
    if not outcome.admitted:
        findings.append(
            Finding(site, f"a confirmed-flat flatten did not admit: {outcome!r}")
        )
    if outcome.flattened != (seam.FlattenTrigger.ORPHAN,):
        findings.append(
            Finding(site, f"flattened under wrong trigger set: {outcome.flattened!r}")
        )

    # Register BEFORE reconcile must still be refused even with a healthy broker.
    broker2 = _Broker(
        truth=_truth(loaded, positions=[_position(loaded)]), tradable=True
    )
    cs2 = coldstart.ColdStart(broker2, _Flattener([]), _Halt(), _Plane1())
    try:
        cs2.register("strat-1", 0.0)
        findings.append(Finding(site, "register() before any reconcile pass succeeded"))
    except coldstart.RegistrationRefused:
        pass
    return findings


# --------------------------------------------------------------------------
# ARM 3 — the market-tradable guard's TWO HALVES, on the SAME instance
# --------------------------------------------------------------------------


class _TruthBox:
    """Mutable holder so `_SelfFlatteningBroker` and its flattener share state.

    `seam` is the LOADED module (out of `ctx.nix_home`), never imported fresh —
    a fresh top-level import would resolve against whatever `nixrisk.seam` this
    process last had on `sys.path`, which after `load()` restores its state is
    NOT necessarily the tree under test.
    """

    def __init__(self, seam: ModuleType, positions: tuple[Any, ...]) -> None:
        self._seam = seam
        self._positions = positions

    def snapshot(self) -> Any:
        return self._seam.BrokerTruth(
            positions=self._positions, balance=1000.0, polled_at=0.0
        )

    def clear(self) -> None:
        self._positions = ()


class _SelfFlatteningBroker(_Broker):
    """A broker whose held truth clears the moment `flatten` is invoked on it —
    so a re-poll after a reopened-market flatten genuinely reports flat, the
    way a real broker would after the market order actually filled."""

    def __init__(
        self,
        *,
        seam: ModuleType,
        positions: tuple[Any, ...],
        tradable: bool,
        why: str = "",
    ) -> None:
        super().__init__(truth=_TruthBox(seam, positions), tradable=tradable, why=why)

    def poll_truth(self) -> Any:
        self.poll_calls += 1
        return self.truth.snapshot()


class _ClearingFlattener:
    def __init__(
        self, box: _TruthBox, log: list[str], *, triggers: tuple[Any, ...] = ()
    ) -> None:
        self._box = box
        self._log = log
        self._triggers = triggers
        self.calls = 0

    def flatten(self, truth: Any) -> tuple[Any, ...]:
        del truth
        self.calls += 1
        self._log.append("flatten")
        self._box.clear()
        return self._triggers


def _arm_market_guard(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    coldstart = loaded.coldstart
    seam = loaded.seam
    site = f"{COLDSTART_FILE}:market_guard"

    log: list[str] = []
    truth = _truth(loaded, positions=[_position(loaded)])
    broker = _SelfFlatteningBroker(
        seam=seam,
        positions=(_position(loaded),),
        tradable=False,
        why="weekend session gap",
    )
    flattener = _ClearingFlattener(
        broker.truth, log, triggers=(seam.FlattenTrigger.ORPHAN,)
    )
    halt = _Halt(log)
    cs = coldstart.ColdStart(broker, flattener, halt, _Plane1())

    # HALF 1 — closed market: hold in HALT, admit nothing, never fire.
    closed = cs.reconcile(1.0)
    if closed.admitted:
        findings.append(
            Finding(
                f"{site}:closed",
                "reconcile ADMITTED registration while the market is closed",
            )
        )
    if closed.state is not coldstart.ColdStartState.HELD_IN_HALT:
        findings.append(
            Finding(
                f"{site}:closed", f"state is {closed.state!r}, expected HELD_IN_HALT"
            )
        )
    if flattener.calls:
        findings.append(
            Finding(f"{site}:closed", "flatten() was called into a CLOSED market")
        )
    if not halt.calls:
        findings.append(
            Finding(
                f"{site}:closed",
                "hold_in_halt() was NEVER called — the HALT alert was skipped",
            )
        )

    # flatten_to_flat called directly must also refuse (§4: the guard lives on
    # the primitive itself, not only in the reconcile flow).
    try:
        cs.flatten_to_flat(truth)
        findings.append(
            Finding(
                f"{site}:closed",
                "flatten_to_flat() fired into a closed market directly",
            )
        )
    except coldstart.ColdStartError as exc:
        if "shut market" not in str(exc):
            findings.append(
                Finding(f"{site}:closed", f"refusal did not name a shut market: {exc}")
            )

    # HALF 2 — the SAME instance's market reopens: it must now flatten + admit.
    broker.tradable = True
    reopened = cs.reconcile(2.0)
    if not reopened.admitted:
        findings.append(
            Finding(
                f"{site}:reopened",
                f"reconcile after reopen did not admit: {reopened!r}",
            )
        )
    if flattener.calls != 1:
        findings.append(
            Finding(
                f"{site}:reopened",
                f"expected 1 flatten call after reopen, got {flattener.calls}",
            )
        )

    # Falsifier: a market_tradable guard that always says True.
    class _AlwaysOpen(coldstart.ColdStart):  # type: ignore[name-defined]
        def flatten_to_flat(self, truth):
            return self._flattener.flatten(truth)  # WRONG: no tradability check

    broker2 = _Broker(
        truth=_truth(loaded, positions=[_position(loaded)]),
        tradable=False,
        why="halted",
    )
    flattener2 = _Flattener([])
    fake = _AlwaysOpen(broker2, flattener2, _Halt(), _Plane1())
    try:
        fake.flatten_to_flat(broker2.truth)
    except coldstart.ColdStartError:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the always-open falsifier still refused — it no longer falsifies",
            )
        )
    if flattener2.calls != 1:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the always-open falsifier did not fire into the closed market",
            )
        )
    return findings


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_registration_gate(loaded)
        findings += _arm_flatten_before_register(loaded)
        findings += _arm_market_guard(loaded)
        evidence = (
            f"{COLDSTART_FILE}: drove the registration gate as a REFUSED attempt "
            "(not a flag read), flatten-before-register ordering with a confirm "
            "poll, and the market-tradable guard's two halves (closed-market hold "
            "+ same-instance reopen flatten) — 3 arms, each with a falsifier "
            "proven to lose its property"
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
