"""§12.1's last-resort deadman — the watchdog itself.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 034 / sub-agent B (B1, B3, B4). Built against the FROZEN
`scripts/nixsentinel/seam.py`; it changes no declared type and adds no verb to
any port.

------------------------------------------------------------------------------
THE ONE SENTENCE THIS MODULE IMPLEMENTS (§12.1:603-606)
------------------------------------------------------------------------------
*"Tiny, dependency-minimal independent process (shared pool). Watches the
Risk-Engine heartbeat. Heartbeat lost and positions possibly open ⇒ emergency
flatten-all via its own broker session + operator alert. Deliberately dumb,
separate code path (minimal common-mode failure)."*

**BOTH halves of the condition, and they are measured separately.** Heartbeat
loss alone does not authorise anything: a flatten against an already-flat account
is a nuisance action with its own hazard, and §12.1:605 conditions the act on
positions possibly being open. Exposure alone authorises nothing either — while
the Limiter lives, §14:977-978 makes execution of any flatten Limiter-only.

------------------------------------------------------------------------------
THE AUTHORITATIVE ANSWER TO "ARE POSITIONS OPEN" IS THE BROKER'S, NOT THE HINT'S
------------------------------------------------------------------------------
`Heartbeat.positions_open` rides on the heartbeat and is the Limiter's last known
count. By the time this module reads it, the Limiter has been silent for at least
the loss threshold, so the figure is stale BY CONSTRUCTION — it is a hint that
says "there was exposure when I last spoke".

**Nothing in this module branches on it.** The second half of the condition is
answered by `SentinelBrokerPort.open_positions()` on the Sentinel's OWN session,
which is §4's rule applied where it matters most: the broker wins and we correct.
The hint is carried into `WakeOutcome` so an operator can see what the dead
process believed, and that is the whole of its use.

------------------------------------------------------------------------------
RESTART IS NOT HANG, AND `ts` ALONE CANNOT TELL THEM APART
------------------------------------------------------------------------------
The seam's `Heartbeat` fixes this and this module is where it becomes behaviour.
Two independent detectors run and their results are OR'd:

* **STALENESS** — `now - beat.ts` past the threshold. Catches the ordinary death:
  the process is gone and the file stops moving.
* **NO PROGRESS** — no change in `(pid, seq)` for the threshold. Catches the HANG
  that staleness cannot: a wedged process can still have a thread stamping a
  fresh `ts` while the counter that proves work is frozen, and a watcher reading
  `ts` alone would call that healthy forever.

A NEW `pid` with `seq` restarted is progress and is classified `RESTARTED`; the
SAME `pid` with a frozen `seq` is classified `FROZEN`. Both are reported, because
§12.2's supervisor and an operator need different narratives for them even though
the deadman's own response is the same.

------------------------------------------------------------------------------
THE ORDER IS THE SAFETY PROPERTY (§12.1:608-614, §14:975)
------------------------------------------------------------------------------
1. `MarkerPhase.BEFORE`, DURABLE, before one instruction reaches the broker.
2. the flatten, on the Sentinel's own session.
3. `MarkerPhase.AFTER`, with the acks.
4. the operator alert, LAST and guarded.

Step 4 is last on purpose. §14:975 gives the exit/protective path *"zero
wire/delivery dependency"*, and an alert channel that is down must not be able to
abort a flatten. Ordering is the primary mechanism — by the time the alert is
attempted the act is finished and recorded — and the `try/except` around it is
the belt: the seam declares `raise_alert` never raises, and an implementation
that broke that promise must still not cost an exit.

A Sentinel killed between 1 and 3 leaves a `BEFORE` with no `AFTER`. That is not
corruption; it is the record §12.1:608's fix exists to preserve, and
`nixrisk/coldstart.py` books it flagged `interrupted`.

------------------------------------------------------------------------------
WHAT THIS MODULE DELIBERATELY CANNOT DO — §14's boundary, kept narrow
------------------------------------------------------------------------------
It flattens and it alerts. It does not arbitrate authority, size a position,
gate an entry, take or release a reservation, publish a financial picture, write
Plane 1, or set HALT. §14:977-978 permits ONE exception to Limiter-only
execution — an emergency flatten when the Limiter is dead — not a second Limiter,
and the narrowness is what earns the exception.

It imports NOTHING from `nixrisk`. §12.1:603's *separate code path* is the
property this package exists to hold: an import edge into the Limiter's package
would mean the defect that killed the Risk Engine also killed its watcher, which
is the definition of the common-mode failure named as the reason for the
separation.
"""

from __future__ import annotations

import enum
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from nixsentinel.config import SentinelKnobs
from nixsentinel.heartbeat import HeartbeatError
from nixsentinel.seam import (
    MARKER_SCHEMA,
    AlertPort,
    BrokerAck,
    Heartbeat,
    HeartbeatPort,
    MarkerPhase,
    MarkerRecord,
    MarkerWriterPort,
    SentinelBrokerPort,
    TriggerCause,
)

# R0902 (too-many-instance-attributes) on `WakeOutcome` and on `Sentinel`:
# the outcome record carries every figure a verdict was reached on, because a
# watchdog that cannot say what it saw can only be believed, and the class holds
# four injected ports plus the small amount of history that distinguishes a
# restart from a hang. Dropping a field to reach a threshold would drop an
# observation from the evidence.
# pylint: disable=too-many-instance-attributes


class LivenessClass(enum.Enum):
    """What the last read said about the Risk Engine, as a NAMED observation.

    Reported on every wake so that "the Sentinel did not act" is a fact with a
    reason attached rather than an absence of output. `RESTARTED` and `FROZEN`
    exist because §12.2's supervisor and an operator need different narratives
    for a process that came back and one that is wedged, even though the deadman
    responds to the second the same way it responds to a death.
    """

    #: No heartbeat has EVER been published. Not a loss — see `Sentinel.poll`.
    NEVER_SEEN = "never_seen"
    #: The first beat this watcher has read. Progress by definition.
    FIRST_SEEN = "first_seen"
    #: `seq` advanced under the same pid. The Risk Engine is doing work.
    PROGRESSING = "progressing"
    #: A NEW pid. §12.2 restarted the process; `seq` restarting from zero is the
    #: corroboration, and the pid change is the evidence.
    RESTARTED = "restarted"
    #: Same pid, `seq` unchanged. A HANG. `ts` may still be advancing.
    FROZEN = "frozen"
    #: The heartbeat existed and was seen before, and has now gone.
    VANISHED = "vanished"
    #: Present and unparsable. Counted as NO PROGRESS — fail closed.
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class WakeOutcome:
    """One wake-up of the watchdog, fully accounted for.

    Every wake returns one of these, including the overwhelming majority that do
    nothing. That is deliberate: §12.1:605's nuisance-flatten hazard can only be
    shown not to have fired if a wake that did not fire is OBSERVABLE, and a
    component that proved its restraint by producing no output would be
    indistinguishable from one that never ran.
    """

    #: `None` when the wake reached no §12.1 condition at all.
    cause: TriggerCause | None
    #: Did a flatten instruction reach the broker on this wake?
    acted: bool
    liveness: LivenessClass
    #: Seconds since the last beat this watcher could read. `inf` when none.
    heartbeat_age_s: float
    #: Seconds since `(pid, seq)` last CHANGED. The hang detector's figure.
    silence_s: float
    symbols: tuple[str, ...] = ()
    acks: tuple[BrokerAck, ...] = ()
    observed_pid: int | None = None
    observed_seq: int | None = None
    #: What the DEAD process believed it was holding. A hint, never an input to
    #: any decision here — see the module docstring.
    hinted_positions_open: int | None = None
    #: What the Sentinel's OWN broker session said. The authoritative figure, and
    #: `None` when the broker was never asked because the condition never fired.
    broker_positions_open: int | None = None
    #: True when this wake found the condition still true after already acting.
    latched: bool = False
    #: Set when the alert channel refused. NEVER a reason to withhold the act.
    alert_failed: str = ""
    #: WHICH loss detector reached the threshold on this wake. Two independent
    #: tests run (staleness and no-progress) and reporting one figure for both is
    #: how a message comes to assert the opposite of what happened.
    stale: bool = False
    no_progress: bool = False
    detail: str = ""


@dataclass
class _Reading:
    """One heartbeat observation, before any decision is taken on it."""

    beat: Heartbeat | None
    liveness: LivenessClass
    age_s: float
    silence_s: float
    #: `now - beat.ts` reached the threshold. The ordinary-death detector.
    stale: bool = False
    #: `(pid, seq)` has not changed for the threshold. The HANG detector, and the
    #: one staleness cannot substitute for: a wedged process can keep stamping a
    #: fresh `ts` while the counter that proves work is frozen.
    no_progress: bool = False
    detail: str = ""

    @property
    def lost(self) -> bool:
        """Either detector is enough. §12.1:604 asks only whether it was lost."""
        return self.stale or self.no_progress

    @property
    def fired(self) -> str:
        """WHICH detector(s) reached the threshold, named for the record.

        The first version of this module reported the silence figure in every
        loss message regardless of which test had actually tripped, which
        produced the sentence *"silence 0.164s >= 0.200s"* in a real drill — a
        false statement asserting the opposite of what happened. A message that
        names a detector must be derived from the detector.
        """
        names = []
        if self.stale:
            names.append(f"stale (age {self.age_s:.3f}s)")
        if self.no_progress:
            names.append(f"no progress (silence {self.silence_s:.3f}s)")
        return " and ".join(names) if names else "no detector"


class Sentinel:
    """The §12.1 deadman. Watches, and in one narrow case acts.

    Deliberately NOT a subclass of any seam `Protocol`: a `Protocol`'s method
    bodies are docstrings, so an inherited verb this class forgot to override
    would return `None` silently, and `None` is a meaningful value on more than
    one of these ports. Conformance is proven by comparing signatures, which is a
    measurement rather than a nominal claim — the argument `nixrisk/coldstart.py`
    records for the same choice.

    SYNCHRONOUS throughout, for the reason the seam gives: this process must make
    progress with no event loop, in the scenario that already killed the Risk
    Engine.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        heartbeat: HeartbeatPort,
        broker: SentinelBrokerPort,
        marker: MarkerWriterPort,
        alert: AlertPort,
        knobs: SentinelKnobs,
        *,
        pid: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._heartbeat = heartbeat
        self._broker = broker
        self._marker = marker
        self._alert = alert
        self._knobs = knobs
        #: This watcher's own pid, stamped into every marker record so a replay
        #: can say WHICH watcher acted (§12.10's attribution).
        self.pid = os.getpid() if pid is None else pid
        self._clock = clock
        self._connected = False
        self._ever_seen = False
        self._last_pid: int | None = None
        self._last_seq: int | None = None
        self._last_progress_ts: float | None = None
        self._lost = False
        #: Set once a flatten has really been fired this episode. The ONLY latch
        #: that suppresses acting — see `_no_positions` for why a flat answer
        #: must never set it.
        self._fired = False
        #: Set once the "lost but flat" restraint has been RECORDED this episode.
        #: A record latch, not an action latch: it keeps the marker to one line
        #: per episode while leaving the broker question open on every wake.
        self._recorded_flat = False

    # -- observation ---------------------------------------------------------

    def _read(self) -> tuple[Heartbeat | None, bool]:
        """`(beat, unreadable)`. Absence is `(None, False)`; a fault is `(None, True)`.

        `HeartbeatError` and `OSError` are caught and counted as NO PROGRESS —
        fail closed, because a heartbeat this process cannot read has not proven
        the Risk Engine alive. Anything else PROPAGATES: a deadman that flattened
        an account because of a programming error inside its own reader would be
        a worse failure than one that crashes loudly and is restarted by §12.2's
        supervisor.
        """
        try:
            return self._heartbeat.read(), False
        except HeartbeatError, OSError:
            return None, True

    def _classify(self, beat: Heartbeat, now: float) -> LivenessClass:
        """Which of the four live classes this beat represents. Updates history."""
        if self._last_pid is None:
            liveness = LivenessClass.FIRST_SEEN
        elif beat.pid != self._last_pid:
            liveness = LivenessClass.RESTARTED
        elif beat.seq != self._last_seq:
            liveness = LivenessClass.PROGRESSING
        else:
            liveness = LivenessClass.FROZEN
        if liveness is not LivenessClass.FROZEN:
            self._last_progress_ts = now
        self._last_pid, self._last_seq = beat.pid, beat.seq
        self._ever_seen = True
        return liveness

    def _observe(self, now: float) -> _Reading:
        """One read, classified, with both loss detectors evaluated."""
        beat, unreadable = self._read()
        if beat is not None:
            liveness = self._classify(beat, now)
            age = now - beat.ts
        elif not self._ever_seen:
            return _Reading(
                beat=None,
                liveness=LivenessClass.NEVER_SEEN,
                age_s=float("inf"),
                silence_s=float("inf"),
                detail=(
                    "no Risk-Engine heartbeat has ever been published, so there "
                    "is no evidence of a Limiter to have lost. §12.1:604 watches "
                    "for a heartbeat that was LOST; treating never-seen as lost "
                    "would fire an emergency flatten on every cold boot"
                ),
            )
        else:
            liveness = (
                LivenessClass.UNREADABLE if unreadable else LivenessClass.VANISHED
            )
            age = float("inf")
        silence = self._silence(now)
        threshold = self._knobs.loss_threshold_s
        return _Reading(
            beat=beat,
            liveness=liveness,
            age_s=age,
            silence_s=silence,
            stale=age >= threshold,
            no_progress=silence >= threshold,
        )

    def _silence(self, now: float) -> float:
        """Seconds since `(pid, seq)` last changed. `inf` before the first beat."""
        if self._last_progress_ts is None:
            return float("inf")
        return now - self._last_progress_ts

    # -- the wake ------------------------------------------------------------

    def poll(self, now: float | None = None) -> WakeOutcome:
        """One wake-up. Returns what was observed and what, if anything, was done.

        The `NEVER_SEEN` early return is load-bearing and is the seam's own
        instruction: absence is not loss. A Sentinel that started before the
        Limiter has seen nothing and has no evidence of exposure; collapsing that
        into "lost" would flatten every cold boot, which is §12.1:605's nuisance
        hazard fired on the most routine event there is. The inherited-position
        case at cold boot is §4's, and `nixrisk/coldstart.py` owns it.
        """
        stamp = float(self._clock() if now is None else now)
        reading = self._observe(stamp)
        if reading.liveness is LivenessClass.NEVER_SEEN:
            return self._quiet(reading, reading.detail)
        if not reading.lost:
            return self._on_alive(reading, stamp)
        return self._on_lost(reading, stamp)

    def _outcome(
        self,
        reading: _Reading,
        *,
        cause: TriggerCause | None = None,
        acted: bool = False,
        detail: str = "",
        **extra: object,
    ) -> WakeOutcome:
        """Every wake's record, built from ONE reading in ONE place.

        Factored deliberately, and not for brevity: the observed pid, the observed
        seq, the stale hint and the two detector flags belong on EVERY outcome,
        and a second spelling of this constructor is exactly where one of them
        goes missing on the one path an operator later needs it. `self` is unused
        by design — the method is here so no caller can build an outcome any
        other way.
        """
        del self  # the constraint is the single construction site, not state
        beat = reading.beat
        return WakeOutcome(
            cause=cause,
            acted=acted,
            liveness=reading.liveness,
            heartbeat_age_s=reading.age_s,
            silence_s=reading.silence_s,
            observed_pid=beat.pid if beat else None,
            observed_seq=beat.seq if beat else None,
            hinted_positions_open=beat.positions_open if beat else None,
            stale=reading.stale,
            no_progress=reading.no_progress,
            detail=detail,
            **extra,  # type: ignore[arg-type]
        )

    def _quiet(self, reading: _Reading, detail: str) -> WakeOutcome:
        """A wake that reached no condition. Still an observation, still reported."""
        return self._outcome(reading, detail=detail)

    def _on_alive(self, reading: _Reading, now: float) -> WakeOutcome:
        """The heartbeat is live. The only interesting case is a RECOVERY.

        A recovery clears the latch, so a Limiter that dies twice is acted on
        twice. It is also RECORDED: §12.1's marker is the Sentinel's only durable
        voice, and a watcher that declared death and then quietly changed its mind
        would leave an operator with a `HEARTBEAT_LOST_NO_POSITIONS` record and no
        account of how the episode ended.
        """
        if not self._lost:
            return self._quiet(
                reading,
                f"heartbeat live ({reading.liveness.value}); silence "
                f"{reading.silence_s:.3f}s is under the "
                f"{self._knobs.loss_threshold_s:.3f}s loss threshold",
            )
        self._lost = False
        self._fired = False
        self._recorded_flat = False
        detail = (
            f"heartbeat RECOVERED ({reading.liveness.value}) after being declared "
            f"lost; no flatten. §12.1:604's condition is no longer true"
        )
        self._write(
            TriggerCause.HEARTBEAT_RECOVERED,
            MarkerPhase.AFTER,
            symbols=(),
            acks=(),
            ts=now,
            silence=0.0,
        )
        failure = self._notify(TriggerCause.HEARTBEAT_RECOVERED, detail)
        return self._outcome(
            reading,
            cause=TriggerCause.HEARTBEAT_RECOVERED,
            detail=detail,
            alert_failed=failure,
        )

    def _on_lost(self, reading: _Reading, now: float) -> WakeOutcome:
        """The heartbeat is lost. Ask the BROKER whether there is anything to do."""
        self._lost = True
        if self._fired:
            return self._outcome(
                reading,
                latched=True,
                detail=(
                    "heartbeat still lost and this Sentinel has already acted on "
                    "this episode. Not acting again: the Limiter is dead, so "
                    "nothing can have opened a new position, and a re-flatten "
                    "every poll would be a stream of nuisance orders against a "
                    "flat account"
                ),
            )
        self._ensure_session()
        positions = self._broker.open_positions()
        if not positions:
            return self._no_positions(reading, now)
        return self._flatten(reading, now, tuple(p.symbol for p in positions))

    def _no_positions(self, reading: _Reading, now: float) -> WakeOutcome:
        """Heartbeat lost, broker says flat. RECORD the restraint, do not act.

        One `AFTER` record and no `BEFORE`, deliberately: the pairing invariant is
        *a `BEFORE` with no `AFTER` means the act was interrupted*, and bracketing
        a non-act would make that invariant need a qualifier. There was no act to
        bracket, so there is one record saying what was decided and why.

        **THIS PATH DOES NOT SET THE ACTED LATCH, AND THE FIRST VERSION OF THIS
        MODULE DID — the hazard was stated backwards.** The latch's justification
        is *"the Limiter is dead, so nothing can have opened a new position"*, and
        that is true only AFTER a flatten has closed what was there. It is exactly
        false here: an order that was in flight at the instant the Risk Engine
        died fills afterwards, and a Sentinel that had already looked once, seen a
        flat account, and latched would ignore the resulting position for the rest
        of the episode. The one case where re-asking the broker matters most is
        the one where the first answer was "nothing".

        What IS latched is the RECORD, so the marker gains one line per episode
        rather than one per poll. Restraint stays observable; the watch stays open.
        """
        detail = (
            f"heartbeat LOST ({reading.liveness.value}; {reading.fired} against a "
            f"{self._knobs.loss_threshold_s:.3f}s threshold) but "
            "this Sentinel's OWN broker session reports NO open position. §12.1:605 "
            "conditions the flatten on positions possibly being open; a flatten "
            "against a flat account is a nuisance action with its own hazard. NOT "
            "flattening, and NOT latching — an order in flight when the Limiter "
            "died can still fill, so the broker is asked again on every wake"
        )
        if self._recorded_flat:
            return self._outcome(
                reading,
                cause=TriggerCause.HEARTBEAT_LOST_NO_POSITIONS,
                detail=detail,
                broker_positions_open=0,
            )
        self._recorded_flat = True
        self._write(
            TriggerCause.HEARTBEAT_LOST_NO_POSITIONS,
            MarkerPhase.AFTER,
            symbols=(),
            acks=(),
            ts=now,
            silence=reading.silence_s,
        )
        failure = self._notify(TriggerCause.HEARTBEAT_LOST_NO_POSITIONS, detail)
        return self._outcome(
            reading,
            cause=TriggerCause.HEARTBEAT_LOST_NO_POSITIONS,
            detail=detail,
            broker_positions_open=0,
            alert_failed=failure,
        )

    def _flatten(
        self, reading: _Reading, now: float, symbols: tuple[str, ...]
    ) -> WakeOutcome:
        """§12.1:605's emergency flatten-all. The marker goes FIRST and is durable.

        If this process dies between the `BEFORE` append and the `AFTER` one — a
        `SIGKILL`, a venue call that never returns, an `os._exit` deep in a broker
        library — the file on disk holds a `BEFORE` and no `AFTER`. That is the
        evidence §12.1:608's fix exists to preserve, and it is why the append
        above the flatten is fsynced rather than buffered.
        """
        self._write(
            TriggerCause.HEARTBEAT_LOST,
            MarkerPhase.BEFORE,
            symbols=symbols,
            acks=(),
            ts=now,
            silence=reading.silence_s,
        )
        acks = tuple(self._broker.flatten_all())
        self._write(
            TriggerCause.HEARTBEAT_LOST,
            MarkerPhase.AFTER,
            symbols=symbols,
            acks=acks,
            ts=float(self._clock()),
            silence=reading.silence_s,
        )
        self._fired = True
        detail = (
            f"heartbeat LOST ({reading.liveness.value}; {reading.fired} against a "
            f"{self._knobs.loss_threshold_s:.3f}s threshold) and "
            f"this Sentinel's OWN broker session reports {len(symbols)} open "
            f"position(s) {symbols}. EMERGENCY FLATTEN-ALL fired (§12.1:604-606); "
            f"{sum(1 for ack in acks if ack.ok)}/{len(acks)} close(s) acknowledged"
        )
        failure = self._notify(TriggerCause.HEARTBEAT_LOST, detail)
        return self._outcome(
            reading,
            cause=TriggerCause.HEARTBEAT_LOST,
            acted=True,
            detail=detail,
            symbols=symbols,
            acks=acks,
            broker_positions_open=len(symbols),
            alert_failed=failure,
        )

    # -- collaborators -------------------------------------------------------

    def _ensure_session(self) -> None:
        """Open the Sentinel's OWN session, once, before it is first needed.

        §12.1:605: *"via its own broker session"*. Not the Limiter's — sharing
        that handle would mean the deadman's only means of acting dies with the
        process it is watching, which is the common-mode failure this component
        exists to avoid.
        """
        if not self._connected:
            self._broker.connect()
            self._connected = True

    def _write(  # pylint: disable=too-many-arguments
        self,
        cause: TriggerCause,
        phase: MarkerPhase,
        *,
        symbols: tuple[str, ...],
        acks: tuple[BrokerAck, ...],
        ts: float,
        silence: float,
    ) -> None:
        """Append one marker record. Durable on return, or it raises."""
        self._marker.append(
            MarkerRecord(
                schema=MARKER_SCHEMA,
                phase=phase,
                ts=ts,
                cause=cause,
                symbols=symbols,
                acks=acks,
                sentinel_pid=self.pid,
                heartbeat_age_s=silence,
            )
        )

    def _notify(self, cause: TriggerCause, detail: str) -> str:
        """Tell the operator. Returns the failure text, or `''`. NEVER raises.

        §14:975 gives the protective path zero delivery dependency. The seam
        declares `raise_alert` never raises; this guard is what makes that a
        property of the SYSTEM rather than of every future implementation, and it
        runs after the act is already finished and recorded so a slow or broken
        channel cannot even delay the flatten.
        """
        try:
            self._alert.raise_alert(cause, detail)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return (
                f"alert channel refused ({type(exc).__name__}: {exc}) — the "
                "flatten is unaffected (§14:975, zero delivery dependency) and the "
                "marker file is the durable record, not this"
            )
        return ""

    # -- the process loop ----------------------------------------------------

    def close(self) -> None:
        """Release this process's own broker session, if one was ever opened.

        Calls `disconnect` only when `connect` succeeded: the seam declares
        `disconnect` never raises so a failed teardown cannot mask a completed
        flatten, and calling it on a session that was never opened would ask a
        vendor library to tear down state it does not have.

        The real process reaches this through `run_until`'s `finally`. It exists
        as a separate verb because a drill child that ends without ever running
        the loop still has to give the session back.
        """
        if self._connected:
            self._connected = False
            self._broker.disconnect()

    def run_until(
        self,
        stop: Callable[[tuple[WakeOutcome, ...]], bool],
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_wakes: int = 0,
    ) -> tuple[WakeOutcome, ...]:
        """Poll at the configured interval until `stop(wakes)` is true.

        `stop` is a predicate over **the wakes so far**, not a bare flag, and that
        is what makes one loop serve both callers: the real process stops on an
        external signal and ignores the argument, while a drill stops the moment
        a §12.1 condition has actually been reached. A `Callable[[], bool]` would
        have forced the drill to write its own loop, and a loop nothing runs is a
        loop nothing has ever measured.

        `stop` is injected rather than read from a signal handler because a signal
        handler is a dependency, and §12.1:603 says dependency-minimal — the
        systemd unit that supervises this process kills it, and a killed deadman
        is exactly as correct as a stopped one.

        `max_wakes` is a hard ceiling; zero means unbounded, which is what the
        real process uses.

        Exceptions from a wake PROPAGATE. A broker that raises mid-flatten leaves
        a `BEFORE` with no `AFTER` on disk and takes this process down; §12.2's
        crash-loop breaker is the mechanism that then decides what happens, and
        swallowing the fault here would put a second supervision policy in a
        module whose whole value is that it has none. The session is still handed
        back on the way out, because `close` never raises by the seam's own
        declaration and cannot therefore replace the fault being reported.
        """
        wakes: list[WakeOutcome] = []
        try:
            while not stop(tuple(wakes)):
                wakes.append(self.poll())
                if max_wakes and len(wakes) >= max_wakes:
                    break
                sleep(self._knobs.poll_interval_s)
        finally:
            self.close()
        return tuple(wakes)
