"""§4's orphan / strategy-death recovery — the ORDER is the safety property.

ARC 034 / sub-agent C (C2, C3, C4). Authority is the frozen risk spec,
`docs/nics_risk_subsystem_spec_v1.3.md`. Every `§` on any line below cites that
document unless another one is named on the same line.

THE RULE, TRANSCRIBED WORD FOR WORD FROM §4:260-274 (v1.3, LOCKED)
-------------------------------------------------------------------
    **Orphan / strategy-death recovery (v1.3, locked):** heartbeat miss ⇒ wait
    **exactly one cycle (1s)**; a second consecutive miss ⇒ strategy presumed
    dead. Recovery runs **safety-before-restart, in strict order**:

    1. **Flatten first** — close any open positions owned by that strategy
       (swept by `strategy_id`) while its registration still exists, so each
       position has an unambiguous known owner. A dead strategy holding a live
       position is the dangerous state; money is made safe immediately, before
       any process-lifecycle work.
    2. **Force-deregister in the Risk Engine** — the Limiter tears down ALL
       state keyed to that strategy: one-in-flight lock, pending state, slot,
       registration. Nothing stale may survive the death (a lingering
       registration would leave the Limiter expecting heartbeats / holding a
       slot).
    3. **Kill + relaunch** — process is killed and relaunched; it re-registers
       and **boots to flat** like any cold start — a genuinely new registration,
       not a half-cleared old one.

WHY THE ORDER IS THE PROPERTY, AND WHY IT IS OBSERVED RATHER THAN ASSERTED
---------------------------------------------------------------------------
Deregistering first ORPHANS the position: the moment the registration is gone,
the open position has no owner, and the sweep in step 1 is *"swept by
`strategy_id`"* — it has nothing left to sweep by. So an implementation that
does the same three things in the wrong order is not slightly wrong, it loses
the money.

Source order proves nothing about execution order. A `try/except` that swallows
the flatten, a guard that skips it, an early return, a branch that reaches
deregistration first — every one of those leaves the three calls sitting in the
file in the right order and runs them in the wrong one. `check_limiter_seam`
ARM 3 already records that lesson. So this module RECORDS EACH STEP AS IT
EXECUTES, into an append-only `RecoveryJournal`, and both instruments assert over
the journal — the sequence that actually ran — never over the code.

THE TRANSITIONAL STATE IS PUBLISHED, AND IT IS PUBLISHED *AFTER* THE FLATTEN
-----------------------------------------------------------------------------
§4:281-286 (locked) requires every recovery action to reach the Allocator via the
mirrored snapshot, and requires the TRANSITIONAL state to be visible: *"a
strategy mid-recovery reads as **in-flight-closing**, NOT normal-and-available,
so it is never counted eligible for new capital while dying."*

That publish happens AFTER the broker flatten and not before, and the ordering is
deliberate. §14 gives the protective/exit path ZERO wire dependency; publishing
first would put the state bus in front of the flatten, so a dead bus would stop
the exit — the exact coupling `scripts/nixrisk/flatten.py` is built to avoid and
proves by removing the wire. Money is made safe first; the Allocator is told
immediately afterwards, and a publish that RAISES is caught, recorded in the
journal as a failed step, and does not unwind the flatten that already fired.

EXECUTION IS LIMITER-ONLY (§14) — THIS MODULE DETECTS AND SEQUENCES
--------------------------------------------------------------------
§14: *detection may live anywhere; EXECUTION of any flatten is Limiter-only.*
Nothing here calls a broker. `RecoverySequencer` hands a `FlattenTrigger.ORPHAN`
to `scripts/nixrisk/flatten.py`'s `ProtectiveFlatten`, which is the one place a
flatten is issued, and which already documented this exact hand-off as awaiting
the heartbeat machinery built here. There is no second flatten path.

**A dead strategy that owns NO published row does not get an untargeted
flatten.** `ProtectiveFlatten.fire(..., symbol=None, targets=())` reaches
`broker.flatten(None)`, which is a flatten of EVERYTHING — it would close other
strategies' positions to recover a strategy that held nothing, destroying exactly
the ownership §4:263 asks the sweep to preserve. The step is recorded as
`FLATTEN` with zero targets and a stated reason instead.

THE CRASH-LOOP CAP AND QUARANTINE (§4:272-274)
-----------------------------------------------
Step 3 asks supervision whether it MAY relaunch. `nixrisk.supervision`'s
`CrashLoopBreaker` at `BreakerScope.STRATEGY` counts the restarts; on the cap it
quarantines instead — *"left dead and flat, alert raised — while the rest of the
system keeps trading"*. That last clause is a property with teeth and is driven
in both instruments: a quarantined strategy must not stop a DIFFERENT strategy's
proposal from being approved by the real §3 gate pass.

**Score handling across death is R5 and is NOT in this arc.** §4:275-280 locks it
and this module implements none of it; `supervision.SCORE_BOUNDARY` is the one
place that sentence lives and both gates print it. Quarantining here removes a
strategy from no ranking table, because §6.6:457-461's table has exactly one
writer — the Scoring process — and Scoring does not exist in this tree.

`debug.md` §7.12 — THE STANDING QUESTION, per surface:

`HeartbeatMonitor.poll`: *what would make it answer while measuring nothing?*
  1. **No strategy ever misses**, so the presumed-dead branch is dead code.
     CLOSED IN BOTH INSTRUMENTS: each drives one miss (must NOT be dead — §4:260
     waits exactly one cycle) and then a SECOND CONSECUTIVE miss (must be dead),
     and each drives miss → beat → miss, which must NOT be dead because the
     misses are not consecutive.
  2. **The grace is read out of the monitor.** CLOSED: the expected cycle count
     comes from `risks/limiter.config.json`'s `heartbeat_miss_grace_cycles`, a
     different artifact from the code, and the gate computes the expected death
     tick from it.
  3. **A strategy that never registered reads as dead**, so the monitor
     "detects" strategies that do not exist. CLOSED: `poll` reports only
     strategies that were `arm`ed, and `presumed_dead` names the beat it last
     saw.

`RecoverySequencer.recover`: *what would make it answer while measuring nothing?*
  4. **The journal could be written from the source order** rather than as steps
     execute. CLOSED BY CONSTRUCTION: each step is appended by the code path that
     performs it, immediately after it performs it, and the falsifier
     `_DeregisterFirstSequencer` in `scripts/tests/test_recovery.py` reorders the
     EXECUTION and is shown to produce a journal in the wrong order — so the
     assertion is proven to be able to fail.
  5. **The flatten could be a no-op** — no owned rows, nothing to close — and
     the order assertion would hold vacuously over two steps that did nothing.
     CLOSED: the drives give the dying strategy a REAL open position, and assert
     the broker saw the close AND that the position was still owned (the
     registration still present) at the instant it fired.
  6. **Force-deregister could tear down some state and leave the rest.** CLOSED:
     `ForcedDeregistration` reports the four things §4:266-268 names — one-in-
     flight lock, pending state, slot, registration — as four separate observed
     facts, and both instruments assert all four went, then re-read the registry
     to prove nothing stale survived.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from nixrisk.seam import EventKind, EventRow, FlattenTrigger, PositionState

# pylint: disable=too-many-lines
# C0302: the module is ~1070 lines and about 55% of it is the §4:260-274
# transcription, the ordering argument and the §7.12 answers. `halt.py` and
# `check_allocator_pathway.py` carry the same disable for the same reason: on
# this tree the doctrine that a safety module states what it does NOT cover, in
# full, is what pushes a file over the line.
# pylint: disable=too-few-public-methods
# The Protocols below are one-verb ports (the process supervisor, the ops plane,
# the operator alert). A second verb invented to clear a class-shape heuristic
# would be surface this module does not own.

__all__ = [
    "ORPHAN_REASON",
    "ForcedDeregistration",
    "HeartbeatMonitor",
    "RecordedStep",
    "RecoveryError",
    "RecoveryJournal",
    "RecoveryOutcome",
    "RecoverySequencer",
    "RecoveryStep",
    "Registration",
    "StrategyRegistry",
    "SupervisorPort",
]

_SITE: Final[str] = "scripts/nixrisk/recovery.py"

#: The `reason` every row of this recovery carries. §4:263's own words, so the
#: strategy feedback, the Plane-1 rows and the operator alert all say the same
#: thing about why a position closed.
ORPHAN_REASON: Final[str] = (
    "orphan: strategy presumed dead on a second consecutive heartbeat miss "
    "(§4:260-261); positions flattened while the registration still existed "
    "(§4:262-265)"
)


class RecoveryError(RuntimeError):
    """A recovery that cannot proceed safely. Loud, never a silent skip."""


# ---------------------------------------------------------------------------
# The STRATEGY heartbeat (§4:260-261, §12A:832)
# ---------------------------------------------------------------------------
#
# This is the STRATEGY heartbeat and only that. The Risk-Engine heartbeat of
# §12.1 is a different beat with a different consumer (the Sentinel deadman) and
# is not built or touched here.


@dataclass(frozen=True)
class HeartbeatVerdict:
    """One strategy's liveness at one poll. Every field is a fact, not a code."""

    strategy_id: str
    consecutive_misses: int
    grace_cycles: int
    presumed_dead: bool
    last_beat_ts: float | None
    now: float
    reason: str


class HeartbeatMonitor:
    """§4:260-261's strategy heartbeat: miss ⇒ one cycle ⇒ second miss ⇒ dead.

    *"heartbeat miss ⇒ wait exactly one cycle (1s); a second consecutive miss ⇒
    strategy presumed dead."*

    CONSECUTIVE is the load-bearing word and it is why this counts misses rather
    than measuring an elapsed gap: a strategy that misses, beats, and misses
    again has had two misses and is ALIVE, and a monitor written against "no beat
    for 2s" cannot tell those two histories apart. A beat RESETS the run.

    Both knobs come from `risks/limiter.config.json` (`heartbeat_interval_s` = 1,
    `heartbeat_miss_grace_cycles` = 1, both §12A:832 knobs stated outright).
    Nothing is defaulted: an absent knob is a refusal, because a grace of zero
    makes one dropped beat a strategy death and a strategy death flattens
    positions.
    """

    def __init__(
        self,
        *,
        interval_s: float,
        grace_cycles: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if interval_s <= 0:
            raise RecoveryError(
                f"{_SITE}: heartbeat_interval_s must be > 0, got {interval_s!r} "
                "— a cycle of zero length means every poll is a new cycle and "
                "the 'exactly one cycle' wait of §4:260 has no duration"
            )
        if isinstance(grace_cycles, bool) or not isinstance(grace_cycles, int):
            raise RecoveryError(
                f"{_SITE}: heartbeat_miss_grace_cycles must be a whole number "
                f"of cycles, got {grace_cycles!r}"
            )
        if grace_cycles < 1:
            raise RecoveryError(
                f"{_SITE}: heartbeat_miss_grace_cycles must be >= 1, got "
                f"{grace_cycles!r} — §4:260-261 pins the grace at exactly one "
                "cycle before a SECOND consecutive miss presumes death; a grace "
                "of zero makes one dropped beat a strategy death, and a "
                "strategy death flattens positions "
                "(risks/limiter.config.json, liveness.heartbeat_grace_at_least_one_cycle)"
            )
        self._interval_s = float(interval_s)
        self._grace = grace_cycles
        self._clock = clock
        self._last: dict[str, float | None] = {}
        self._misses: dict[str, int] = {}

    @property
    def interval_s(self) -> float:
        """§12A:832's `HEARTBEAT_INTERVAL`, in seconds."""
        return self._interval_s

    @property
    def grace_cycles(self) -> int:
        """§12A:832's `HEARTBEAT_MISS_GRACE`, in cycles."""
        return self._grace

    def arm(self, strategy_id: str, now: float | None = None) -> None:
        """Start watching a registered strategy. Only armed strategies are polled.

        A monitor that reported on strategies it was never told about would
        "detect the death" of every process that has never existed (§7.12/3).
        """
        self._last[strategy_id] = self._clock() if now is None else float(now)
        self._misses[strategy_id] = 0

    def disarm(self, strategy_id: str) -> None:
        """Stop watching. Called by force-deregistration — §4:267's *'a lingering
        registration would leave the Limiter expecting heartbeats'*."""
        self._last.pop(strategy_id, None)
        self._misses.pop(strategy_id, None)

    def armed(self) -> tuple[str, ...]:
        """Every strategy currently watched, sorted."""
        return tuple(sorted(self._last))

    def beat(self, strategy_id: str, now: float | None = None) -> None:
        """One heartbeat received. RESETS the consecutive-miss run."""
        if strategy_id not in self._last:
            raise RecoveryError(
                f"{_SITE}: heartbeat from {strategy_id!r}, which is not armed — "
                "a beat from an unregistered strategy is a §2 registration "
                "question, not a liveness one, and is refused rather than "
                "silently arming a strategy nobody admitted"
            )
        self._last[strategy_id] = self._clock() if now is None else float(now)
        self._misses[strategy_id] = 0

    def miss(self, strategy_id: str, now: float | None = None) -> HeartbeatVerdict:
        """One cycle elapsed with no beat. Returns the verdict for THIS cycle."""
        if strategy_id not in self._last:
            raise RecoveryError(
                f"{_SITE}: cannot record a miss for {strategy_id!r} — it is not "
                "armed, so there is no beat it could have missed"
            )
        stamp = self._clock() if now is None else float(now)
        self._misses[strategy_id] = self._misses.get(strategy_id, 0) + 1
        return self._verdict(strategy_id, stamp)

    def poll(self, now: float | None = None) -> tuple[HeartbeatVerdict, ...]:
        """Every armed strategy's verdict at this instant, sorted by id.

        Reads the recorded miss runs; it does not itself decide that a cycle
        elapsed, because whose clock defines a cycle is the caller's §5 event
        loop's business and not this object's.
        """
        stamp = self._clock() if now is None else float(now)
        return tuple(self._verdict(sid, stamp) for sid in sorted(self._last))

    def presumed_dead(self, now: float | None = None) -> tuple[str, ...]:
        """The strategies §4:261 presumes dead at this instant."""
        return tuple(v.strategy_id for v in self.poll(now) if v.presumed_dead)

    def _verdict(self, strategy_id: str, stamp: float) -> HeartbeatVerdict:
        misses = self._misses.get(strategy_id, 0)
        last = self._last.get(strategy_id)
        dead = misses > self._grace
        if dead:
            reason = (
                f"{_SITE}: {strategy_id!r} PRESUMED DEAD — {misses} consecutive "
                f"heartbeat miss(es) at a grace of {self._grace} cycle(s) of "
                f"{self._interval_s}s (§4:260-261: miss ⇒ wait exactly one "
                f"cycle; a SECOND consecutive miss ⇒ presumed dead). Last beat "
                f"seen at {last!r}, now {stamp!r}"
            )
        else:
            reason = (
                f"{_SITE}: {strategy_id!r} is alive — {misses} consecutive "
                f"miss(es), within the grace of {self._grace} cycle(s). §4:260 "
                f"waits exactly one cycle after the first miss. Last beat seen "
                f"at {last!r}, now {stamp!r}"
            )
        return HeartbeatVerdict(
            strategy_id=strategy_id,
            consecutive_misses=misses,
            grace_cycles=self._grace,
            presumed_dead=dead,
            last_beat_ts=last,
            now=stamp,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# The registry force-deregistration tears down (§4:266-268)
# ---------------------------------------------------------------------------


@dataclass
class Registration:
    """ALL Limiter state keyed to one strategy — §4:266-268's four things.

    *"the Limiter tears down ALL state keyed to that strategy: one-in-flight
    lock, pending state, slot, registration."* Four names, four fields, so
    "nothing stale may survive" is a statement with four checkable parts rather
    than one boolean.
    """

    strategy_id: str
    #: §4:210-212's one-in-flight lock: the client_order_id holding it, or None.
    in_flight: str | None = None
    #: §4's pending state: client_order_id -> whatever the Limiter holds for it.
    pending: dict[str, str] = field(default_factory=dict)
    #: §2's slot — the strategy occupies one of the platform's concurrency slots.
    slot: int | None = None
    registered_ts: float = 0.0


@dataclass(frozen=True)
class ForcedDeregistration:
    """What a force-deregister actually tore down. Four observed facts."""

    strategy_id: str
    had_registration: bool
    released_in_flight: str | None
    dropped_pending: tuple[str, ...]
    freed_slot: int | None
    reason: str

    @property
    def complete(self) -> bool:
        """Did every one of §4:266-268's four names come down?"""
        return self.had_registration


class StrategyRegistry:
    """The Limiter's registration table. In-memory; §5 single-threaded.

    Deliberately small and deliberately NOT a second admission gate:
    `nixrisk/coldstart.py` owns whether a registration may be ADMITTED (§4, V34 —
    no strategy registers until provably flat), and this owns what is HELD once
    one has been. Two objects, two properties, doctrine C.9.
    """

    def __init__(self) -> None:
        self._rows: dict[str, Registration] = {}

    def register(self, strategy_id: str, *, slot: int, now: float) -> Registration:
        """Admit one strategy into the table. Refuses a duplicate, loudly."""
        if strategy_id in self._rows:
            raise RecoveryError(
                f"{_SITE}: {strategy_id!r} is already registered — §4:269-271 "
                "makes a relaunch 'a genuinely new registration, not a "
                "half-cleared old one', so a second register over a live row "
                "would be the half-cleared state it forbids"
            )
        row = Registration(strategy_id=strategy_id, slot=slot, registered_ts=now)
        self._rows[strategy_id] = row
        return row

    def get(self, strategy_id: str) -> Registration | None:
        """The row, or None. `None` IS the post-deregistration answer."""
        return self._rows.get(strategy_id)

    def is_registered(self, strategy_id: str) -> bool:
        """Does the Limiter still expect heartbeats and hold a slot for this id?"""
        return strategy_id in self._rows

    def registered(self) -> tuple[str, ...]:
        """Every live registration, sorted."""
        return tuple(sorted(self._rows))

    def take_in_flight(self, strategy_id: str, client_order_id: str) -> None:
        """Occupy the one-in-flight lock (§4:210-212). Refuses a SECOND take.

        ARC 038 / sub-agent F (finding FF2). The guard is here and not only in
        `gate.InFlightLockRule` because the rule READS the lock and this method
        IS the lock: without it, eight `take_in_flight` calls for one strategy
        were all accepted, `row.in_flight` was silently re-pointed at the last
        `client_order_id`, the earlier ones stayed live in `pending` and
        unreachable through `in_flight()`, and `force_deregister` reported ONE
        `released_in_flight` for eight takes. §4:210 fixes *one* in-flight
        action per strategy; a mutator that cannot say no leaves that invariant
        resting entirely on every caller remembering to ask the gate first.
        """
        row = self._require(strategy_id)
        if row.in_flight is not None:
            raise RecoveryError(
                f"{_SITE}: {strategy_id!r} already holds the one-in-flight lock "
                f"with {row.in_flight!r}; refusing to take it for "
                f"{client_order_id!r}. §4:210 allows ONE in-flight action per "
                "strategy, and overwriting the lock would leave "
                f"{row.in_flight!r} pending with nothing naming it — the "
                "release path reports the lock it can see, not the one it "
                "replaced"
            )
        row.in_flight = client_order_id
        row.pending[client_order_id] = "pending"

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """Satisfies the frozen `gate.InFlightPort`. A DEREGISTERED strategy is
        not locked — it has no slot to be locked in, and the gate that consults
        this will refuse it at registration instead."""
        row = self._rows.get(strategy_id)
        if row is None or row.in_flight is None:
            return False, f"{strategy_id}: no order in flight"
        return True, (
            f"{strategy_id}: one-in-flight lock held by {row.in_flight} (§4:210)"
        )

    def force_deregister(self, strategy_id: str) -> ForcedDeregistration:
        """§4:266-268 — tear down ALL state keyed to this strategy. Idempotent.

        Returns WHAT came down, not whether something did: a teardown that
        reports a bare success cannot distinguish "released the lock, freed the
        slot and dropped two pending orders" from "found nothing and said yes".
        """
        row = self._rows.pop(strategy_id, None)
        if row is None:
            return ForcedDeregistration(
                strategy_id=strategy_id,
                had_registration=False,
                released_in_flight=None,
                dropped_pending=(),
                freed_slot=None,
                reason=(
                    f"{_SITE}: {strategy_id!r} held no registration — nothing to "
                    "tear down. This is NOT a successful teardown of a live "
                    "strategy and must not be read as one"
                ),
            )
        dropped = tuple(sorted(row.pending))
        released = row.in_flight
        freed = row.slot
        row.in_flight = None
        row.pending.clear()
        row.slot = None
        return ForcedDeregistration(
            strategy_id=strategy_id,
            had_registration=True,
            released_in_flight=released,
            dropped_pending=dropped,
            freed_slot=freed,
            reason=(
                f"{_SITE}: force-deregistered {strategy_id!r} (§4:266-268) — "
                f"one-in-flight lock {released!r} released, {len(dropped)} "
                f"pending order(s) {list(dropped)} dropped, slot {freed!r} "
                f"freed, registration removed. Nothing keyed to this strategy "
                f"survives; the Limiter no longer expects its heartbeats"
            ),
        )

    def _require(self, strategy_id: str) -> Registration:
        row = self._rows.get(strategy_id)
        if row is None:
            raise RecoveryError(
                f"{_SITE}: {strategy_id!r} is not registered in the Risk Engine"
            )
        return row


# ---------------------------------------------------------------------------
# The observed sequence — the deliverable of this module
# ---------------------------------------------------------------------------


class RecoveryStep(enum.Enum):
    """The steps a recovery may take, in §4:262-274's order. AN ORDERED SET.

    The `order` of a member is what the assertions read. It is declared here so
    that "flatten before deregister" is one comparison against a fixed scale
    rather than a rule re-derived at each assertion site.
    """

    DETECT_DEATH = ("detect_death", 0)
    FLATTEN = ("flatten", 1)
    PUBLISH_IN_FLIGHT_CLOSING = ("publish_in_flight_closing", 2)
    FORCE_DEREGISTER = ("force_deregister", 3)
    KILL = ("kill", 4)
    RELAUNCH = ("relaunch", 5)
    QUARANTINE = ("quarantine", 5)

    def __init__(self, label: str, order: int) -> None:
        # The ignore below: `_value_` is typed as the member's own tuple, and
        # re-binding it to the label is the documented custom-`Enum.__init__`
        # pattern (the tuple is the CONSTRUCTOR's argument list, not the value).
        # PRE-EXISTING; surfaced by ARC 037 only because mypy type-checks this
        # module when scripts/nixrisk/supervision.py is in the same run.
        self._value_ = label  # type: ignore[assignment]
        self.order = order


@dataclass(frozen=True)
class RecordedStep:
    """ONE step, recorded AT THE MOMENT IT RAN. `seq` is the execution ordinal."""

    seq: int
    step: RecoveryStep
    strategy_id: str
    ts: float
    ok: bool
    detail: str


class RecoveryJournal:
    """An append-only observation list. THE INSTRUMENT THE ORDER IS PROVEN ON.

    Nothing here is derived from the source: `RecoverySequencer` appends each
    step from inside the code path that performs it, immediately after it
    performs it. Two properties follow that no reading of the file could give:

    * a step that was SKIPPED does not appear, however prominently its call sits
      in the source;
    * a step that ran in the wrong ORDER appears in the wrong order.

    Append-only, never rewritten (directive 6). There is no verb that removes or
    reorders an entry, deliberately: a journal a sequencer could tidy up is a
    journal that proves what the sequencer wanted to have happened.
    """

    def __init__(self) -> None:
        self._entries: list[RecordedStep] = []

    def record(
        self, step: RecoveryStep, strategy_id: str, ts: float, *, ok: bool, detail: str
    ) -> RecordedStep:
        """Append one executed step. Returns it."""
        entry = RecordedStep(
            seq=len(self._entries) + 1,
            step=step,
            strategy_id=strategy_id,
            ts=ts,
            ok=ok,
            detail=detail,
        )
        self._entries.append(entry)
        return entry

    def entries(self, strategy_id: str | None = None) -> tuple[RecordedStep, ...]:
        """Every recorded step in EXECUTION order, optionally for one strategy."""
        if strategy_id is None:
            return tuple(self._entries)
        return tuple(e for e in self._entries if e.strategy_id == strategy_id)

    def sequence(self, strategy_id: str | None = None) -> tuple[RecoveryStep, ...]:
        """Just the steps, in execution order. What the order assertions read."""
        return tuple(e.step for e in self.entries(strategy_id))

    def index_of(self, step: RecoveryStep, strategy_id: str | None = None) -> int:
        """The execution position of a step, or -1 when it never ran."""
        seq = self.sequence(strategy_id)
        return seq.index(step) if step in seq else -1


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


@runtime_checkable
class SupervisorPort(Protocol):
    """§4:269-271's process lifecycle. Two verbs, and they are separate.

    Kill and relaunch are distinct because the cap sits BETWEEN them: §4:272 says
    *"stop relaunching"*, not "stop killing". A dead strategy is killed whether
    or not it will come back, because leaving a half-dead process alive is the
    orphan state the whole rule exists to end.
    """

    def kill(self, strategy_id: str) -> str:
        """Kill the strategy process. Returns an operator-readable detail."""

    def relaunch(self, strategy_id: str) -> str:
        """Relaunch it. §4:271 — it re-registers and boots to flat."""


@runtime_checkable
class BreakerPort(Protocol):
    """The §4:272 cap. Satisfied by `supervision.CrashLoopBreaker` at STRATEGY."""

    def record_restart(self, subject: str, *, now: float | None = None) -> Any:
        """Count one restart of this strategy and decide."""

    def may_relaunch(self, subject: str) -> tuple[bool, str]:
        """`(allowed, reason)` — is this strategy quarantined?"""


@runtime_checkable
class FlattenPort(Protocol):
    """The §14 execution half. Satisfied by `flatten.ProtectiveFlatten`."""

    def fire(
        self,
        trigger: Any,
        *,
        symbol: str | None = None,
        targets: Sequence[Any] = (),
        reason: str | None = None,
    ) -> Any:
        """Fire a protective flatten. Zero wire, in-process, Limiter-only."""


@runtime_checkable
class PicturePort(Protocol):
    """The published financial picture (§3:154-164). Read AND republish."""

    def current(self) -> Any:
        """The Limiter's own canonical snapshot."""

    def commit(self, **changes: Any) -> Any:
        """Publish one atomic snapshot. §3's atomicity rule."""


@runtime_checkable
class Plane1Port(Protocol):
    """§9's write path. The Limiter is the SOLE writer."""

    def enqueue(self, row: EventRow) -> None:
        """Append one row to the local WAL buffer."""


@runtime_checkable
class Plane2Port(Protocol):
    """§12.10:739's ops plane. Diagnostic only."""

    def emit(self, event: str, **fields: Any) -> str:
        """Write one structured operational line."""


@runtime_checkable
class AlertSink(Protocol):
    """The operator alert. One verb; the transport is not ours."""

    def alert(self, code: str, message: str) -> None:
        """Raise one operator-visible alert."""


# ---------------------------------------------------------------------------
# The sequencer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveryOutcome:  # pylint: disable=too-many-instance-attributes
    # Eight fields, one per §4:262-274 outcome a caller or a gate must be able to
    # read separately: who died, the executed step list, what was closed, what
    # was torn down, which of relaunch/quarantine happened, the published
    # version, and the reason. A frozen value with no behaviour.
    """One completed recovery. `steps` is what actually ran, in that order."""

    strategy_id: str
    steps: tuple[RecordedStep, ...]
    flattened_trades: tuple[str, ...]
    deregistration: ForcedDeregistration | None
    relaunched: bool
    quarantined: bool
    published_version: int | None
    reason: str

    @property
    def sequence(self) -> tuple[RecoveryStep, ...]:
        """The steps in EXECUTION order."""
        return tuple(step.step for step in self.steps)


class RecoverySequencer:  # pylint: disable=too-many-instance-attributes
    # Ten attributes: nine collaborators, each one surface §4:262-274 names: the registry, the
    # heartbeat, the §14 flatten executor, the picture book, the breaker, the
    # supervisor, both planes and the alert. None is incidental state.
    """§4:262-274's recovery, in strict order, recording each step as it runs.

    Single instance, owned by the Limiter's single-threaded §5 loop. Every verb
    is SYNCHRONOUS: the flatten it drives is §14's zero-wire in-process call, and
    a suspension point inside a recovery is a window in which the dying strategy
    could be deregistered by something else while its position is still open.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        registry: StrategyRegistry,
        heartbeat: HeartbeatMonitor,
        flatten: FlattenPort,
        picture: PicturePort,
        breaker: BreakerPort,
        supervisor: SupervisorPort,
        plane1: Plane1Port,
        plane2: Plane2Port,
        alert: AlertSink,
        journal: RecoveryJournal | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._registry = registry
        self._heartbeat = heartbeat
        self._flatten = flatten
        self._picture = picture
        self._breaker = breaker
        self._supervisor = supervisor
        self._plane1 = plane1
        self._plane2 = plane2
        self._alert = alert
        self.journal = journal if journal is not None else RecoveryJournal()
        self._clock = clock

    # -- the sweep -----------------------------------------------------------

    def owned_rows(self, strategy_id: str) -> tuple[Any, ...]:
        """§4:263's sweep BY `strategy_id`, over the Limiter's canonical table.

        **THE REGISTRATION IS A PRECONDITION OF THE SWEEP, NOT A COURTESY.**
        §4:262-265 requires the flatten to run *"while its registration still
        exists, so each position has an unambiguous known owner"*. A position row
        carries a `strategy_id` string; what makes that string an OWNER is the
        live registration behind it. Once the registration is gone the string
        names nobody the Limiter admits, and closing under it would be the
        Limiter acting on an attribution it can no longer stand behind — so this
        returns EMPTY and says why, which is exactly what being orphaned means.

        That precondition is what makes the §4 ORDER load-bearing in code rather
        than only in prose: `_DeregisterFirstSequencer` in
        `scripts/tests/test_recovery.py` performs the same three calls in the
        wrong order and closes nothing, because by the time it sweeps there is no
        owner left to sweep by.

        Read from the Limiter's own published picture and not from the broker:
        the broker's view is per-symbol and carries no owner at all.
        """
        if not self._registry.is_registered(strategy_id):
            return ()
        picture = self._picture.current()
        return tuple(
            row
            for row in picture.positions
            if row.strategy_id == strategy_id
            and row.state in (PositionState.OPEN, PositionState.PENDING)
        )

    # -- the recovery --------------------------------------------------------

    def recover(self, strategy_id: str, *, now: float | None = None) -> RecoveryOutcome:
        """§4:262-274, in strict order. Each step recorded AS IT EXECUTES.

        1 flatten → (publish the transitional state) → 2 force-deregister →
        3 kill + relaunch, or QUARANTINE where the §4:272 cap has been reached.

        The publish sits AFTER the flatten and not before, so §14's zero-wire
        exit keeps its property: a dead state bus must not be able to stop the
        close. A publish that raises is recorded as a failed step and does not
        unwind the flatten that already fired — money is already safe, and
        refusing to continue at that point would leave the strategy registered,
        which is §4:267's lingering registration.
        """
        stamp = self._clock() if now is None else float(now)
        mark = len(self.journal.entries())
        if not self._registry.is_registered(strategy_id):
            raise RecoveryError(
                f"{_SITE}: refusing to recover {strategy_id!r} — it holds no "
                "registration. §4:262-265 flattens 'while its registration still "
                "exists, so each position has an unambiguous known owner'; "
                "recovering an already-deregistered strategy is the orphaned "
                "state this order exists to prevent, not a recovery of it"
            )
        self._record(
            RecoveryStep.DETECT_DEATH,
            strategy_id,
            stamp,
            True,
            self._dead_detail(strategy_id, stamp),
        )

        flattened = self._step_flatten(strategy_id, stamp)
        version = self._step_publish(strategy_id, stamp)
        dereg = self._step_deregister(strategy_id, stamp)
        relaunched, quarantined = self._step_lifecycle(strategy_id, stamp)

        # THIS recovery's steps only. The journal is append-only and shared
        # across every recovery the Limiter runs, so a crash loop's third
        # recovery would otherwise report the first two's RELAUNCH steps as its
        # own — and the quarantine assertion "RELAUNCH did not run" would read
        # a step from a different death.
        steps = tuple(
            entry
            for entry in self.journal.entries()[mark:]
            if entry.strategy_id == strategy_id
        )
        return RecoveryOutcome(
            strategy_id=strategy_id,
            steps=steps,
            flattened_trades=flattened,
            deregistration=dereg,
            relaunched=relaunched,
            quarantined=quarantined,
            published_version=version,
            reason=(
                f"{_SITE}: recovered {strategy_id!r} in the §4:262-274 order — "
                f"{[entry.step.value for entry in steps]}. "
                f"{len(flattened)} trade(s) flattened while still owned; "
                f"relaunched={relaunched}, quarantined={quarantined}"
            ),
        )

    # -- the steps -----------------------------------------------------------

    def _step_flatten(self, strategy_id: str, stamp: float) -> tuple[str, ...]:
        """STEP 1 (§4:262-265). Flatten while the registration STILL EXISTS."""
        registered = self._registry.is_registered(strategy_id)
        rows = self.owned_rows(strategy_id)
        if not rows:
            orphaned = not registered
            self._record(
                RecoveryStep.FLATTEN,
                strategy_id,
                stamp,
                not orphaned,
                (
                    (
                        f"ORPHANED: {strategy_id!r} holds NO registration at the "
                        "moment of the sweep, so §4:263's sweep by strategy_id "
                        "has no owner to sweep by and nothing was closed. This "
                        "is what deregistering before flattening costs"
                    )
                    if orphaned
                    else (
                        f"{strategy_id!r} owned no open or pending position row "
                        "at death, so nothing was closed. NO untargeted flatten "
                        "was issued: an untargeted flatten reaches "
                        "broker.flatten(None), which closes EVERY symbol and "
                        "would destroy other strategies' positions to recover "
                        "one that held nothing"
                    )
                ),
            )
            return ()
        targets = tuple(
            _CloseTargetLike(row.trade_id, row.symbol, strategy_id) for row in rows
        )
        action = self._flatten.fire(
            FlattenTrigger.ORPHAN, targets=targets, reason=ORPHAN_REASON
        )
        closed = tuple(target.trade_id for target in targets)
        self._record(
            RecoveryStep.FLATTEN,
            strategy_id,
            stamp,
            True,
            (
                f"fired FlattenTrigger.{FlattenTrigger.ORPHAN.name} at "
                f"{len(targets)} owned target(s) {list(closed)} through the §14 "
                f"Limiter-only executor while the registration was STILL "
                f"PRESENT (registry.is_registered="
                f"{self._registry.is_registered(strategy_id)}); "
                f"reason={ORPHAN_REASON!r}; action={type(action).__name__}"
            ),
        )
        return closed

    def _step_publish(self, strategy_id: str, stamp: float) -> int | None:
        """§4:281-286. The transitional state reaches the Allocator mirror.

        Every row this strategy owned is republished as `CLOSING` —
        §4:284's *in-flight-closing* — so the Allocator's lifecycle screen refuses
        it new capital while it is dying. `nixalloc/lifecycle.py` is the reader;
        this is the heartbeat-originated PRODUCER it was built to reflect and had
        never had (CHECK-DEBT D3.155).
        """
        try:
            current = self._picture.current()
            rows = tuple(
                _closing(row) if row.strategy_id == strategy_id else row
                for row in current.positions
            )
            published = self._picture.commit(positions=rows)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self._record(
                RecoveryStep.PUBLISH_IN_FLIGHT_CLOSING,
                strategy_id,
                stamp,
                False,
                (
                    f"the mirrored-snapshot publish RAISED "
                    f"{type(exc).__name__}: {exc}. The flatten had already "
                    "fired (§14 zero-wire), so money is safe and the recovery "
                    "CONTINUES — stopping here would leave the dead strategy "
                    "registered, which is §4:267's lingering registration"
                ),
            )
            return None
        changed = sum(
            1
            for row in rows
            if row.strategy_id == strategy_id and row.state is PositionState.CLOSING
        )
        self._record(
            RecoveryStep.PUBLISH_IN_FLIGHT_CLOSING,
            strategy_id,
            stamp,
            True,
            (
                f"published snapshot version {published.version} with {changed} "
                f"row(s) of {strategy_id!r} in state "
                f"{PositionState.CLOSING.value!r} — §4:284's in-flight-closing, "
                "NOT normal-and-available, so the Allocator never counts a dying "
                "strategy eligible for new capital"
            ),
        )
        return int(published.version)

    def _step_deregister(self, strategy_id: str, stamp: float) -> ForcedDeregistration:
        """STEP 2 (§4:266-268). Tear down ALL state keyed to this strategy."""
        dereg = self._registry.force_deregister(strategy_id)
        self._heartbeat.disarm(strategy_id)
        self._book(EventKind.FORCE_DEREGISTER, strategy_id, dereg.reason, stamp)
        self._record(
            RecoveryStep.FORCE_DEREGISTER,
            strategy_id,
            stamp,
            dereg.complete,
            dereg.reason,
        )
        return dereg

    def _step_lifecycle(self, strategy_id: str, stamp: float) -> tuple[bool, bool]:
        """STEP 3 (§4:269-274). Kill, then relaunch — unless the cap says no."""
        killed = self._supervisor.kill(strategy_id)
        self._book(EventKind.KILL, strategy_id, killed, stamp)
        self._record(RecoveryStep.KILL, strategy_id, stamp, True, killed)

        verdict = self._breaker.record_restart(strategy_id, now=stamp)
        allowed, why = self._breaker.may_relaunch(strategy_id)
        self._plane2.emit(
            "orphan-recovery",
            strategy_id=strategy_id,
            steps=[s.value for s in self.journal.sequence(strategy_id)],
            relaunch_allowed=allowed,
            cap_hit=bool(getattr(verdict, "tripped", False)),
        )
        if not allowed:
            self._book(EventKind.QUARANTINE, strategy_id, why, stamp)
            self._record(RecoveryStep.QUARANTINE, strategy_id, stamp, True, why)
            self._alert.alert(
                "recovery.quarantine",
                f"§4:273 — {strategy_id!r} left DEAD AND FLAT; the rest of the "
                f"system keeps trading. {why}",
            )
            return False, True
        detail = self._supervisor.relaunch(strategy_id)
        self._book(EventKind.RELAUNCH, strategy_id, detail, stamp)
        self._record(RecoveryStep.RELAUNCH, strategy_id, stamp, True, detail)
        return True, False

    # -- plumbing ------------------------------------------------------------

    def _dead_detail(self, strategy_id: str, stamp: float) -> str:
        for verdict in self._heartbeat.poll(stamp):
            if verdict.strategy_id == strategy_id:
                return verdict.reason
        return (
            f"{_SITE}: {strategy_id!r} is not armed on the strategy heartbeat, "
            "so this recovery was driven by a caller and not by §4:260-261's "
            "second consecutive miss"
        )

    def _record(
        self,
        step: RecoveryStep,
        strategy_id: str,
        stamp: float,
        ok: bool,
        detail: str,
    ) -> None:
        self.journal.record(step, strategy_id, stamp, ok=ok, detail=detail)

    def _book(
        self, kind: EventKind, strategy_id: str, reason: str, stamp: float
    ) -> None:
        """One §12.10:757 strategy-lifecycle row onto Plane 1 (§9 sole writer)."""
        self._plane1.enqueue(
            EventRow(
                kind=kind,
                ts=stamp,
                strategy_id=strategy_id,
                reason=reason,
                fields={"trigger": FlattenTrigger.ORPHAN.value},
            )
        )


@dataclass(frozen=True)
class _CloseTargetLike:
    """The three identity fields `flatten.CloseTarget` carries (§4 feedback).

    Structural rather than an import of `flatten.CloseTarget`, deliberately: this
    module must not acquire an import edge to the executor it hands work to, or
    the detection/execution split §14 draws would be one module deep on one side
    and two on the other. `ProtectiveFlatten.request_close` reads exactly these
    three attributes.
    """

    trade_id: str
    symbol: str
    strategy_id: str


def _closing(row: Any) -> Any:
    """One published row, moved to `CLOSING` and otherwise UNCHANGED.

    Every other field is CARRIED, never re-derived: `flatten.py:_confirmed_rows`
    records the same rule and the same reason — inventing a stop distance here
    would make the Limiter publish a §7:501 exposure figure no sizing pass
    computed.
    """
    if row.state is PositionState.CLOSING:
        return row
    return type(row)(
        trade_id=row.trade_id,
        symbol=row.symbol,
        strategy_id=row.strategy_id,
        size=row.size,
        margin=row.margin,
        state=PositionState.CLOSING,
        stop_distance=row.stop_distance,
    )


def heartbeat_from_config(
    values: Mapping[str, object], clock: Callable[[], float] = time.time
) -> HeartbeatMonitor:
    """Build the strategy heartbeat from `risks/limiter.config.json` VALUE keys.

    No defaults (directive 4): both knobs are §12A:832 knobs stated outright, and
    an absent one is a refusal rather than a number nobody chose.
    """
    missing = [
        key
        for key in ("heartbeat_interval_s", "heartbeat_miss_grace_cycles")
        if key not in values
    ]
    if missing:
        raise RecoveryError(
            f"{_SITE}: heartbeat knobs absent from the loaded config: {missing} "
            "— §12A:832 owns these values and this module holds no default"
        )
    interval = values["heartbeat_interval_s"]
    grace = values["heartbeat_miss_grace_cycles"]
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        raise RecoveryError(
            f"{_SITE}: heartbeat_interval_s={interval!r} is not a number"
        )
    if isinstance(grace, bool) or not isinstance(grace, int):
        raise RecoveryError(
            f"{_SITE}: heartbeat_miss_grace_cycles={grace!r} is not a whole "
            "number of cycles"
        )
    return HeartbeatMonitor(interval_s=float(interval), grace_cycles=grace, clock=clock)
