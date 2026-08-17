#!/usr/bin/env python3
"""§4's orphan / strategy-death recovery — THE ORDER, OBSERVED, not asserted.

ONE gate over `scripts/nixrisk/recovery.py`. The property is a SEQUENCE:
§4:262-268 flattens FIRST and force-deregisters SECOND, because deregistering
first orphans the position — the sweep is *"swept by `strategy_id`"* and there
is nothing left to sweep by once the registration is gone.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.

WHY THIS GATE READS A JOURNAL AND NOT THE SOURCE. Source order proves nothing
about execution order: a swallowed exception, a guard, an early return or a
branch all leave three calls sitting in the file in the right order and run them
in the wrong one (`check_limiter_seam` ARM 3 records the same lesson). So the
sequencer records each step AS IT EXECUTES into an append-only
`RecoveryJournal`, and every arm here asserts over that journal. ARM 2 then
drives a FALSIFIER — a subclass that performs the same three calls in the
reverse order — and requires it to LOSE the property, so the assertion is proven
able to fail.

THE FIVE ARMS

  1. **THE HEARTBEAT** (§4:260-261). One miss is NOT death; a SECOND CONSECUTIVE
     miss is; a beat between two misses resets the run. The grace comes from
     `risks/limiter.config.json`, a different artifact from the subject.
  2. **THE ORDER, OBSERVED** — plus the falsifier that loses it, plus the proof
     the flatten was NOT vacuous: a real OPEN row, a real broker close, and the
     registration asserted PRESENT at the instant it fired.
  3. **FORCE-DEREGISTER TEARS DOWN ALL FOUR THINGS** §4:266-268 names, then the
     registry is RE-READ to prove nothing stale survived.
  4. **THE ALLOCATOR READS IN-FLIGHT-CLOSING THROUGH A REAL DEATH** (§4:281-286).
     The published snapshot is the one the recovery itself produced, and the
     SHIPPED `nixalloc.lifecycle` screen is what answers. The non-vacuity floor
     is not an arithmetic identity: the SAME snapshot must answer differently
     for the dying strategy and for a live one.
  5. **THE CAP QUARANTINES AND THE REST KEEPS TRADING** (§4:272-274), driven
     through the REAL §3 `GatePass` over the SHIPPED `default_manifest` with the
     real registry as the one-in-flight port — a live strategy's proposal must
     still be APPROVED with a quarantined strategy in the world.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. **The subject could fail to import.** CLOSED: CANNOT_MEASURE naming the
    exception (§17), never a PASS.
 2. **The order could be read off the source.** CLOSED: every ordering assertion
    reads `RecoveryJournal`, which is written by the code path that performs
    each step, and ARM 2's falsifier proves the assertion can fail.
 3. **The order could hold vacuously** over steps that closed nothing. CLOSED:
    ARM 2 requires a real broker close of a real owned row, and the falsifier is
    required to leave that same row unclosed.
 4. **The lifecycle screen could refuse everyone**, making ARM 4 an identity.
    CLOSED: the same published snapshot must return eligible=False for the dying
    strategy AND eligible=True for the live one.
 5. **The publish could sit in front of the flatten**, coupling §14's zero-wire
    exit to the state bus. CLOSED: ARM 2 drives one recovery with the picture
    sink RAISING and requires the broker close to have landed anyway and the
    recovery to have completed with the failed publish RECORDED.
 6. **A green could imply score handling across death works.** CLOSED: the
    evidence PRINTS `supervision.SCORE_BOUNDARY` — §4:275-280 is R5 and nothing
    here implements it.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=too-many-lines
# C0302: just over the 1000-line default, and the overflow is the §7.12 answers,
# the ordering argument and the per-finding REASON strings — the part a future
# arc cannot re-derive. `check_allocator_pathway` and `check_allocator_mirror`
# carry the same disable for the same reason.
# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-instance-attributes,protected-access
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS `nixrisk` and `nixalloc` out of `ctx.nix_home` (shared
#: interpreter import state) and WRITES a scratch restart ledger under `/tmp`.
#: It spawns no subprocess, opens no socket and touches no systemd.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/recovery.py sequences a "
    "protective flatten and a force-deregistration); a repair that edited it to "
    "satisfy its own gate is the class of action risk spec §4 forbids on the "
    "order path"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/recovery.py",)

NAME = "check_orphan_recovery"

RECOVERY_FILE = "scripts/nixrisk/recovery.py"
PACKAGES = ("nixrisk", "nixalloc")

#: WHICH steps a complete recovery must have RUN. Labels only — this tuple says
#: nothing about their order, deliberately. The ORDER is judged two ways, and
#: neither of them is this tuple: by comparing the observed positions of FLATTEN
#: and FORCE_DEREGISTER in the journal, and by requiring the observed sequence to
#: be non-decreasing in `RecoveryStep.order`, which is the subject's OWN declared
#: scale. Writing the expected order out here as a list would make the gate agree
#: with a rule this file had restated (directive 3).
REQUIRED_STEPS = ("detect_death", "flatten", "force_deregister", "kill")


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    recovery: ModuleType
    supervision: ModuleType
    flatten: ModuleType
    picture: ModuleType
    reservations: ModuleType
    gate: ModuleType
    halt: ModuleType
    seam: ModuleType
    lifecycle: ModuleType
    limiter_values: dict
    supervision_knobs: Any


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key
        for key in sys.modules
        if key in PACKAGES or key.startswith(tuple(f"{p}." for p in PACKAGES))
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key in PACKAGES or key.startswith(tuple(f"{p}." for p in PACKAGES))
    }
    saved_rc = sys.modules.pop("risk_config", None)
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        supervision = importlib.import_module("nixrisk.supervision")
        risk_config = importlib.import_module("risk_config")
        configs = risk_config.load_risk_configs(home)
        return Loaded(
            recovery=importlib.import_module("nixrisk.recovery"),
            supervision=supervision,
            flatten=importlib.import_module("nixrisk.flatten"),
            picture=importlib.import_module("nixrisk.picture"),
            reservations=importlib.import_module("nixrisk.reservations"),
            gate=importlib.import_module("nixrisk.gate"),
            halt=importlib.import_module("nixrisk.halt"),
            seam=importlib.import_module("nixrisk.seam"),
            lifecycle=importlib.import_module("nixalloc.lifecycle"),
            limiter_values=dict(configs.modules["limiter"].values),
            supervision_knobs=supervision.SupervisionKnobs.from_config(
                configs.modules["supervision"].values
            ),
        ), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"cannot load the §4 recovery subject out of {home}: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        _purge(saved_modules)
        if saved_rc is not None:
            sys.modules["risk_config"] = saved_rc
        else:
            sys.modules.pop("risk_config", None)
        sys.path[:] = saved_path


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------

DEAD = "strat-dead"
LIVE = "strat-live"


class _Broker:
    def __init__(self) -> None:
        self.flatten_calls: list[str | None] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)

    def cancel_order(self, client_order_id: str) -> None:
        del client_order_id


class _Sink:
    def __init__(self) -> None:
        self.emitted: list = []

    def emit(self, picture: Any) -> None:
        self.emitted.append(picture)


class _DeadSink:
    def emit(self, picture: Any) -> None:
        del picture
        raise ConnectionError("state bus down")


class _Plane1:
    def __init__(self) -> None:
        self.rows: list = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return len(self.rows)


class _Plane2:
    def __init__(self) -> None:
        self.lines: list = []

    def emit(self, event: str, **fields: Any) -> str:
        self.lines.append((event, dict(fields)))
        return event


class _Alerts:
    def __init__(self) -> None:
        self.raised: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        self.raised.append((code, message))


class _StrategySink:
    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        del trade_id, strategy_id, reason, hard_reset


class _Scoring:
    def book_realized(self, **kwargs: Any) -> None:
        del kwargs


class _Supervisor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def kill(self, strategy_id: str) -> str:
        self.calls.append(("kill", strategy_id))
        return f"killed {strategy_id}"

    def relaunch(self, strategy_id: str) -> str:
        self.calls.append(("relaunch", strategy_id))
        return f"relaunched {strategy_id}"


class _Clear:
    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        return False, ""


class _NetLiq:
    def mark(self) -> tuple[float, bool]:
        return 10_000_000.0, True


class _Ledger:
    def __init__(self, seam: ModuleType) -> None:
        self._seam = seam
        self.live: dict = {}

    def take(self, order: Any, now: float) -> Any:
        reservation = self._seam.Reservation(
            reservation_id=f"res-{len(self.live) + 1}",
            client_order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            margin=order.proposed_margin,
            state=self._seam.ReservationState.TAKEN,
            taken_ts=now,
        )
        self.live[reservation.reservation_id] = reservation
        return reservation

    def release(self, reservation_id: str, via: Any, now: float) -> Any:
        import dataclasses  # pylint: disable=import-outside-toplevel

        held = self.live.pop(reservation_id)
        return dataclasses.replace(
            held,
            state=self._seam.ReservationState.RELEASED,
            released_ts=now,
            released_via=via,
        )

    def outstanding(self) -> tuple:
        return tuple(self.live.values())

    def total_reserved(self) -> float:
        return sum(row.margin for row in self.live.values())


class World:
    """One wired Limiter built out of the SHIPPED modules. No local fakes of any
    subject — only of the ports the subject was designed to be handed."""

    def __init__(
        self, loaded: Loaded, tmp: Path, *, sink: Any = None, cls=None
    ) -> None:
        self.loaded = loaded
        self.sink = sink if sink is not None else _Sink()
        self.broker = _Broker()
        self.plane1 = _Plane1()
        self.plane2 = _Plane2()
        self.alerts = _Alerts()
        self.supervisor = _Supervisor()
        self.book = loaded.picture.FinancialPictureBook(
            balance=100_000.0, deployable_fraction=0.70, sink=self.sink
        )
        self.flatten = loaded.flatten.ProtectiveFlatten(
            broker=self.broker,
            ledger=loaded.reservations.ReservationLedger(self.plane1),
            picture=self.book,
            strategy=_StrategySink(),
            plane1=self.plane1,
            scoring=_Scoring(),
        )
        self.registry = loaded.recovery.StrategyRegistry()
        self.heartbeat = loaded.recovery.heartbeat_from_config(loaded.limiter_values)
        self.breaker = loaded.supervision.CrashLoopBreaker(
            knobs=loaded.supervision_knobs,
            scope=loaded.supervision.BreakerScope.STRATEGY,
            ledger=loaded.supervision.RestartLedger(tmp),
            alert=self.alerts,
            plane2=self.plane2,
        )
        builder = cls or loaded.recovery.RecoverySequencer
        self.sequencer = builder(
            registry=self.registry,
            heartbeat=self.heartbeat,
            flatten=self.flatten,
            picture=self.book,
            breaker=self.breaker,
            supervisor=self.supervisor,
            plane1=self.plane1,
            plane2=self.plane2,
            alert=self.alerts,
        )

    def admit(self, strategy_id: str, slot: int, now: float = 0.0) -> None:
        self.registry.register(strategy_id, slot=slot, now=now)
        self.heartbeat.arm(strategy_id, now=now)

    def open_position(self, strategy_id: str, trade_id: str, symbol: str) -> None:
        seam = self.loaded.seam
        rows = list(self.book.current().positions)
        rows.append(
            seam.PositionRow(
                trade_id=trade_id,
                symbol=symbol,
                strategy_id=strategy_id,
                size=1,
                margin=1000.0,
                state=seam.PositionState.OPEN,
                stop_distance=20,
            )
        )
        self.book.commit(positions=rows)


def _world(loaded: Loaded, tmp: Path, **kw: Any) -> World:
    built = World(loaded, tmp, **kw)
    built.admit(DEAD, slot=1)
    built.admit(LIVE, slot=2)
    built.open_position(DEAD, "T-dead", "MESU6")
    built.open_position(LIVE, "T-live", "MNQU6")
    return built


# --------------------------------------------------------------------------
# ARM 1 — the STRATEGY heartbeat (§4:260-261)
# --------------------------------------------------------------------------


def _arm_heartbeat(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:heartbeat"
    monitor = loaded.recovery.heartbeat_from_config(loaded.limiter_values)
    grace = loaded.limiter_values["heartbeat_miss_grace_cycles"]
    if monitor.grace_cycles != grace:
        findings.append(
            Finding(
                site,
                f"the monitor runs at grace={monitor.grace_cycles} but "
                f"risks/limiter.config.json says {grace}",
            )
        )

    monitor.arm("s", now=0.0)
    first = monitor.miss("s", now=1.0)
    if first.presumed_dead:
        findings.append(
            Finding(
                site,
                f"ONE miss presumed death: {first.reason} — §4:260 waits EXACTLY "
                "one cycle, and a death flattens positions",
            )
        )
    second = monitor.miss("s", now=2.0)
    if not second.presumed_dead:
        findings.append(
            Finding(
                site,
                f"a SECOND consecutive miss did not presume death: {second.reason}",
            )
        )
    if "PRESUMED DEAD" not in second.reason:
        findings.append(
            Finding(site, f"the death verdict carries no reason: {second.reason!r}")
        )

    # CONSECUTIVE is the load-bearing word: a beat resets the run.
    reset = loaded.recovery.heartbeat_from_config(loaded.limiter_values)
    reset.arm("s", now=0.0)
    reset.miss("s", now=1.0)
    reset.beat("s", now=1.5)
    third = reset.miss("s", now=2.5)
    if third.presumed_dead:
        findings.append(
            Finding(
                site,
                f"miss → BEAT → miss presumed death: {third.reason} — the two "
                "misses are not CONSECUTIVE, and a monitor written against an "
                "elapsed gap cannot tell the two histories apart",
            )
        )

    # An unarmed strategy is never reported dead (§7.12/3).
    if reset.presumed_dead(99.0) not in ((), ("s",)):
        findings.append(Finding(site, "poll reported an unarmed strategy"))
    try:
        loaded.recovery.HeartbeatMonitor(interval_s=1.0, grace_cycles=0)
        findings.append(
            Finding(
                site,
                "a grace of ZERO cycles was accepted — one dropped beat would be "
                "a strategy death, and a strategy death flattens positions",
            )
        )
    except loaded.recovery.RecoveryError:
        pass
    return findings


# --------------------------------------------------------------------------
# ARM 2 — THE ORDER, observed, with the falsifier and the dead-wire drive
# --------------------------------------------------------------------------


def _falsifier(loaded: Loaded) -> Any:
    recovery = loaded.recovery

    class _DeregisterFirst(recovery.RecoverySequencer):  # type: ignore[name-defined,misc]
        """THE FALSIFIER: the same three calls, in the WRONG execution order."""

        def recover(self, strategy_id: str, *, now: float | None = None):
            stamp = self._clock() if now is None else float(now)
            self._record(
                recovery.RecoveryStep.DETECT_DEATH,
                strategy_id,
                stamp,
                True,
                "falsifier",
            )
            self._step_deregister(strategy_id, stamp)
            flattened = self._step_flatten(strategy_id, stamp)
            self._step_publish(strategy_id, stamp)
            return flattened

    return _DeregisterFirst


def _arm_order(loaded: Loaded, root: Path) -> tuple[list[Finding], tuple[str, ...]]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:order"
    recovery = loaded.recovery
    world = _world(loaded, root / "order.jsonl")
    world.registry.take_in_flight(DEAD, "c-dead-1")

    outcome = world.sequencer.recover(DEAD, now=100.0)
    observed = tuple(step.value for step in outcome.sequence)

    missing = [label for label in REQUIRED_STEPS if label not in observed]
    if missing:
        findings.append(
            Finding(
                site, f"the recovery never ran {missing}; observed {list(observed)}"
            )
        )
    flatten_at = world.sequencer.journal.index_of(recovery.RecoveryStep.FLATTEN, DEAD)
    dereg_at = world.sequencer.journal.index_of(
        recovery.RecoveryStep.FORCE_DEREGISTER, DEAD
    )
    if not 0 <= flatten_at < dereg_at:
        findings.append(
            Finding(
                site,
                f"OBSERVED order {list(observed)} — §4:262-268 flattens FIRST and "
                "force-deregisters SECOND; deregistering first orphans the "
                "position because the sweep is by strategy_id",
            )
        )
    # The second, independent reading of the same property: the executed steps
    # must be non-decreasing on the subject's OWN declared scale. This catches an
    # inversion anywhere in the run, not only the one pair named above.
    ranks = [step.order for step in outcome.sequence]
    if ranks != sorted(ranks):
        findings.append(
            Finding(
                site,
                f"the executed steps {list(observed)} rank {ranks} on "
                "RecoveryStep.order, which is not non-decreasing — some step ran "
                "before one §4:262-274 places ahead of it",
            )
        )
    # NON-VACUITY: a real owned row, a real broker close, ownership at the time.
    if outcome.flattened_trades != ("T-dead",):
        findings.append(
            Finding(
                site,
                f"the flatten closed {outcome.flattened_trades!r}, not the dying "
                "strategy's real OPEN row — the order would hold vacuously over "
                "two steps that did nothing",
            )
        )
    if world.broker.flatten_calls != ["MESU6"]:
        findings.append(
            Finding(
                site,
                f"the broker saw {world.broker.flatten_calls!r} — the §14 "
                "Limiter-only executor was not reached",
            )
        )
    step = next(
        (s for s in outcome.steps if s.step is recovery.RecoveryStep.FLATTEN), None
    )
    if step is None or "is_registered=True" not in step.detail:
        findings.append(
            Finding(
                site,
                "the flatten step does not record that the registration was "
                "still PRESENT when it fired — §4:262-265's 'unambiguous known "
                "owner' is then unmeasured",
            )
        )

    findings += _arm_falsifier(loaded, root)
    findings += _arm_dead_wire(loaded, root)
    return findings, observed


def _arm_falsifier(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:order:falsifier"
    broken = World(loaded, root / "falsifier.jsonl", cls=_falsifier(loaded))
    broken.admit(DEAD, slot=1)
    broken.open_position(DEAD, "T-dead", "MESU6")

    flattened = broken.sequencer.recover(DEAD, now=100.0)

    if flattened:
        findings.append(
            Finding(
                site,
                f"the deregister-first falsifier still closed {flattened!r} — it "
                "no longer falsifies, so the order assertion above cannot fail "
                "and measures nothing",
            )
        )
    if broken.broker.flatten_calls:
        findings.append(
            Finding(
                site,
                f"the falsifier reached the broker anyway "
                f"({broken.broker.flatten_calls!r}); the ORPHANING did not happen",
            )
        )
    survivors = [
        row for row in broken.book.current().positions if row.trade_id == "T-dead"
    ]
    if len(survivors) != 1:
        findings.append(
            Finding(site, "the falsifier's orphaned position is not observable")
        )
    return findings


def _arm_dead_wire(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:zero-wire"
    recovery = loaded.recovery
    world = World(loaded, root / "deadwire.jsonl")
    world.admit(DEAD, slot=1)
    world.open_position(DEAD, "T-dead", "MESU6")
    # The wire goes down AFTER the setup publish, so the drive starts from a
    # real picture and only the recovery's own publish meets a dead bus.
    world.book._sink = _DeadSink()

    outcome = world.sequencer.recover(DEAD, now=100.0)

    if world.broker.flatten_calls != ["MESU6"]:
        findings.append(
            Finding(
                site,
                "the exit did not fire with the state bus DOWN — §14 gives the "
                "protective path ZERO wire dependency, and a publish placed in "
                "front of the flatten couples them",
            )
        )
    publish = next(
        (
            s
            for s in outcome.steps
            if s.step is recovery.RecoveryStep.PUBLISH_IN_FLIGHT_CLOSING
        ),
        None,
    )
    if publish is None or publish.ok:
        findings.append(
            Finding(
                site,
                "a publish against a DEAD sink was recorded as successful — the "
                "failure was swallowed rather than recorded",
            )
        )
    if not outcome.relaunched:
        findings.append(
            Finding(
                site,
                "the recovery stopped at the failed publish, leaving the dead "
                "strategy registered — §4:267's lingering registration",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — force-deregister tears down ALL FOUR things (§4:266-268)
# --------------------------------------------------------------------------


def _arm_teardown(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:force-deregister"
    world = _world(loaded, root / "teardown.jsonl")
    world.registry.take_in_flight(DEAD, "c-dead-1")
    if world.registry.in_flight(DEAD)[0] is not True:
        findings.append(Finding(site, "the one-in-flight lock was never taken"))
        return findings

    outcome = world.sequencer.recover(DEAD, now=100.0)
    dereg = outcome.deregistration

    if dereg is None or not dereg.had_registration:
        findings.append(Finding(site, "no registration was torn down"))
        return findings
    for label, seen, expected in (
        ("one-in-flight lock", dereg.released_in_flight, "c-dead-1"),
        ("pending state", dereg.dropped_pending, ("c-dead-1",)),
        ("slot", dereg.freed_slot, 1),
    ):
        if seen != expected:
            findings.append(
                Finding(
                    site,
                    f"§4:266-268's {label} was not torn down: saw {seen!r}, "
                    f"expected {expected!r} — 'nothing stale may survive'",
                )
            )
    # RE-READ: nothing survived.
    if world.registry.is_registered(DEAD) or world.registry.get(DEAD) is not None:
        findings.append(Finding(site, "the registration survived the teardown"))
    if world.registry.in_flight(DEAD)[0]:
        findings.append(Finding(site, "the one-in-flight lock survived the teardown"))
    if DEAD in world.heartbeat.armed():
        findings.append(
            Finding(
                site,
                "the heartbeat monitor still watches the dead strategy — §4:267: "
                "a lingering registration would leave the Limiter expecting "
                "heartbeats",
            )
        )
    if world.registry.registered() != (LIVE,):
        findings.append(
            Finding(
                site,
                f"the teardown disturbed other registrations: "
                f"{world.registry.registered()!r}",
            )
        )
    kinds = {row.kind for row in world.plane1.rows}
    for required in (
        loaded.seam.EventKind.FORCE_DEREGISTER,
        loaded.seam.EventKind.KILL,
        loaded.seam.EventKind.RELAUNCH,
    ):
        if required not in kinds:
            findings.append(
                Finding(
                    site,
                    f"§12.10:757 routes the strategy-lifecycle row "
                    f"{required.value!r} to Plane 1 and none was booked",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 4 — the Allocator reads IN-FLIGHT-CLOSING through a REAL death
# --------------------------------------------------------------------------


def _arm_allocator(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:allocator"
    lifecycle = loaded.lifecycle
    world = _world(loaded, root / "allocator.jsonl")

    before = lifecycle.eligibility(world.book.current(), DEAD)
    if not before.eligible:
        findings.append(
            Finding(
                site,
                f"the dying strategy was ALREADY ineligible before the death: "
                f"{before.reason} — the transition would be unobservable",
            )
        )

    outcome = world.sequencer.recover(DEAD, now=100.0)
    published = world.book.current()
    after = lifecycle.eligibility(published, DEAD)
    live = lifecycle.eligibility(published, LIVE)

    if after.eligible:
        findings.append(
            Finding(
                site,
                f"after a REAL death the dying strategy still reads eligible: "
                f"{after.reason} — §4:284-286 makes it in-flight-closing, NOT "
                "normal-and-available",
            )
        )
    if after.closing_trades != ("T-dead",):
        findings.append(
            Finding(
                site,
                f"the published closing rows are {after.closing_trades!r}; the "
                "recovery's own row is not the one being screened",
            )
        )
    # NON-VACUITY, and not an identity: the SAME snapshot must answer
    # differently for a strategy that did not die.
    if not live.eligible:
        findings.append(
            Finding(
                site,
                f"the live strategy was ALSO refused off the same snapshot: "
                f"{live.reason} — a screen that refuses everyone would pass the "
                "assertion above while measuring nothing",
            )
        )
    if outcome.published_version != published.version:
        findings.append(
            Finding(
                site,
                f"the recovery reported version {outcome.published_version} and "
                f"the book holds {published.version} — the snapshot screened is "
                "not the one the recovery published",
            )
        )
    if not world.sink.emitted:
        findings.append(
            Finding(site, "nothing reached the Allocator mirror's wire at all")
        )
    return findings


# --------------------------------------------------------------------------
# ARM 5 — the cap quarantines and the REST KEEPS TRADING
# --------------------------------------------------------------------------


def _arm_quarantine(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{RECOVERY_FILE}:quarantine"
    recovery = loaded.recovery
    cap = loaded.supervision_knobs.crash_loop_max
    world = _world(loaded, root / "quarantine.jsonl")

    outcomes = []
    for index in range(cap):
        if not world.registry.is_registered(DEAD):
            world.admit(DEAD, slot=1, now=200.0 + index)
        outcomes.append(world.sequencer.recover(DEAD, now=200.0 + index))

    if any(o.quarantined for o in outcomes[:-1]):
        findings.append(
            Finding(
                site,
                f"quarantined BEFORE {cap} restarts: {[o.reason for o in outcomes]}",
            )
        )
    final = outcomes[-1]
    if not final.quarantined or final.relaunched:
        findings.append(
            Finding(
                site,
                f"the {cap}th recovery relaunched instead of quarantining: "
                f"{final.reason} — §4:272 says stop relaunching",
            )
        )
    if recovery.RecoveryStep.RELAUNCH in final.sequence:
        findings.append(
            Finding(
                site,
                f"a RELAUNCH step ran on the quarantining recovery: {final.reason}",
            )
        )
    if world.supervisor.calls[-1] != ("kill", DEAD):
        findings.append(
            Finding(
                site,
                "the quarantining recovery did not KILL — §4:272 says stop "
                "relaunching, not stop killing; a half-dead process left alive "
                "is the orphan state the rule exists to end",
            )
        )
    if not any(code == "recovery.quarantine" for code, _ in world.alerts.raised):
        findings.append(
            Finding(site, f"no quarantine alert: {[c for c, _ in world.alerts.raised]}")
        )

    # THE REST OF THE SYSTEM KEEPS TRADING — driven through the REAL §3 pass.
    halt = loaded.halt.HaltFlag(
        plane1=_Plane1(),
        plane2=_Plane2(),
        floors=loaded.limiter_values["halt_cooldown_floor_s"],
    )
    if halt.is_set() != (False, ""):
        findings.append(
            Finding(site, "a fresh HALT flag is not clear — the drive is invalid")
        )
    clear = _Clear()
    gate = loaded.gate.GatePass(
        halt,
        list(
            loaded.gate.default_manifest(
                blackout=clear,
                tradability=clear,
                staleness=clear,
                clock_skew=clear,
                in_flight=world.registry,
                net_liq=_NetLiq(),
                deployable_fraction=0.70,
                survival_safety_pad=0.10,
                coherence_tolerance=1e-6,
            )
        ),
        _Ledger(loaded.seam),
    )
    proposal = loaded.seam.ProposedOrder(
        client_order_id="c-live-1",
        strategy_id=LIVE,
        symbol="MNQU6",
        side=loaded.seam.Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=loaded.seam.StopMode.FIXED,
        signal_ts=1.0,
    )
    verdict = gate.evaluate(proposal, world.book.current(), 300.0)
    if verdict.decision is not loaded.seam.Decision.APPROVE:
        findings.append(
            Finding(
                site,
                f"with one strategy QUARANTINED, a DIFFERENT strategy's proposal "
                f"was {verdict.decision.value} at rule {verdict.rule!r}: "
                f"{verdict.reason} — §4:273 says the rest of the system keeps "
                "trading",
            )
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------

ARMS = 5


def _remove_tree(root: Path) -> None:
    """Delete the scratch directory by ABSOLUTE path, never `shutil.rmtree`
    (ARC 026: rmtree unlinks with a bare relative name no RESOURCES claim can
    account for)."""
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


def _evidence(loaded: Loaded, observed: tuple[str, ...]) -> str:
    return (
        f"{ARMS} arms driving the SHIPPED {RECOVERY_FILE} together with the real "
        f"nixrisk.flatten executor, the real FinancialPictureBook, the real §3 "
        f"GatePass and the real nixalloc.lifecycle screen. THE OBSERVED STEP "
        f"SEQUENCE of one real death, read off the append-only RecoveryJournal "
        f"as each step executed: {list(observed)}. The §4:260-261 heartbeat "
        f"driven at one miss (alive), two consecutive (dead) and miss-beat-miss "
        f"(alive) at grace="
        f"{loaded.limiter_values['heartbeat_miss_grace_cycles']} from "
        f"risks/limiter.config.json; a deregister-first FALSIFIER proven to "
        f"close nothing; the exit proven to fire with the state bus REMOVED; "
        f"§4:266-268's four teardowns observed and the registry re-read; the "
        f"Allocator screen answering False for the dying strategy and True for a "
        f"live one off the SAME published snapshot; and the "
        f"{loaded.supervision_knobs.crash_loop_max}-restart cap quarantining "
        f"while a different strategy's proposal is still APPROVED by the real "
        f"pass with the HALT flag clear. "
        f"WHAT IS NOT HERE — {loaded.supervision.SCORE_BOUNDARY}"
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    root = Path("/tmp") / f"nix-{NAME}-{id(ctx):x}"
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        root.mkdir(parents=True, exist_ok=True)
        findings: list[Finding] = []
        findings += _arm_heartbeat(loaded)
        order_findings, observed = _arm_order(loaded, root)
        findings += order_findings
        findings += _arm_teardown(loaded, root)
        findings += _arm_allocator(loaded, root)
        findings += _arm_quarantine(loaded, root)
        evidence = _evidence(loaded, observed)
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
    finally:
        _remove_tree(root)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
