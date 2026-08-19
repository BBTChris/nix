"""§5's Limiter: the SINGLE-THREADED EVENT LOOP itself, as a running thing.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 039 / sub-agent A. This module exists because of ARC 038's deepest finding:
**every Limiter invariant proven in this tree so far is proven about a LIBRARY.**
`nixrisk/gate.py` decides, `nixrisk/reservations.py` accounts, `nixrisk/halt.py`
latches, `nixrisk/recovery.py` tears down — and not one of them has ever run
inside a process that was alive when nobody was calling it. §2:42 does not
describe a library. It describes a component whose Process/Placement column
reads *"in Risk Engine"* and whose threading model is spelled out at §5:322-324:

    - **Limiter = single-threaded event loop** (shared-mem price poll + ZMQ
      inbox + sender completions, processed serially) + **one low-priority
      sender thread** (blocking I/O, releases GIL; hung socket contained; hot
      loop never blocks). Serial processing eliminates fill-vs-tick races by
      construction.

That paragraph is a claim about a PROCESS. A library cannot satisfy it, cannot
falsify it, and cannot be measured against it from outside. This module is the
substrate that can be: `LimiterLoop.run()` blocks, ticks, and does not stop
because nothing is asking it to.

------------------------------------------------------------------------------
WHAT THIS MODULE DELIBERATELY DOES NOT DO
------------------------------------------------------------------------------
ARC 039 (slice 1) implemented NO invariant here, deliberately. ARC 040 (slice 2)
added EXACTLY ONE — §4:210-212's GO-TIMEOUT, `_break_go_deadlocks` below — and
nothing else moved: there is still no sole-writer enforcement (§9), no torn-state
detection, no sizing, no placement, no flatten and no cold start. Those live in
the modules named above and stay there.

The GO-timeout is here rather than in a library for the reason this whole module
exists. §4:212 says *"within T of emitting GO"*: T is a DURATION, a duration
needs a clock that is still running when nobody is calling anything, and slice 1
built the only such clock in this tree. ARC 038 (F) measured the consequence of
its absence directly — a real SIGKILL of the GO holder left the lock held past
the knob, because the knob had no reader anywhere in the shipped population.

Two things it DOES own, because both are properties of the *running* thing and
of nothing else:

  1. **THE HEARTBEAT CADENCE.** `nixsentinel/heartbeat.py`'s module docstring is
     explicit that it *"does not run the Limiter's publish loop — the Limiter
     owns its own cadence and calls `publish()` from it."* This is that cadence,
     and it is driven off the loop's OWN monotonic clock inside the loop's own
     tick. See the next block: that placement is the whole safety property.
  2. **THE ONE-IN-FLIGHT LOCK AS LIVE STATE.** `StrategyRegistry` has always
     been correct and has always been a per-call fixture built by a test.
     `self.registry` is an attribute of a process that outlives every command it
     serves, which is the only shape in which "one in flight per strategy"
     (§4:208-209, §3:140) is a statement about the system rather than about a
     function call.

------------------------------------------------------------------------------
WHY THE HEARTBEAT MUST BE PUBLISHED FROM THE TICK AND FROM NOWHERE ELSE
------------------------------------------------------------------------------
§12.1:603-604: the Sentinel *"Watches the Risk-Engine heartbeat. Heartbeat lost
**and** positions possibly open ⇒ emergency flatten-all"*. The heartbeat is the
only evidence the Sentinel has that the process holding every synthetic stop is
still able to act.

A heartbeat published by a `threading.Timer`, by a second thread, or by a signal
handler advances while the event loop is wedged. The Sentinel then reads a
climbing `seq`, concludes the Risk Engine is healthy, and never fires — with
open positions and nothing servicing them. That is the §12.1 catastrophe, and it
is produced by a design choice that looks like a tidy separation of concerns.
`nixsentinel/heartbeat.py` already names the sibling case: a hung process with a
thread updating `ts` reads healthy forever, which is why `seq` exists. This
module closes the other half — `seq` only advances if a TICK COMPLETED.

Three mechanisms, none of them a comment:

  * `_claim_loop_thread` records the ident of the first thread to enter `tick`
    and REFUSES any second one, naming both. §5:322's *single-threaded* is
    therefore enforced rather than asserted.
  * `_publish_heartbeat` refuses unless the caller is that thread AND the loop
    is currently inside `tick`. A timer, a helper thread, or a well-meaning
    `loop._publish_heartbeat()` from outside the tick raises `LoopError`.
  * the beat is published **LAST in the tick**, after ingress and drain. A beat
    published first would mean "the loop entered a tick"; published last it
    means "the loop COMPLETED a tick", which is the thing the Sentinel is being
    asked to believe.

`heartbeat_publisher_idents` is the observation the gate reads: the set of
thread idents that have ever published. A single-element set equal to the loop's
own ident is the property, measured rather than argued.

------------------------------------------------------------------------------
§11 HOT-PATH DISCIPLINE, AND WHERE THE INGRESS READ SITS INSIDE IT
------------------------------------------------------------------------------
§11:581-582: *"Entry pathway = **cache reads + arithmetic only**; everything
expensive lives on pollers / event-handlers updating caches and running
aggregates."* The tick body here does exactly three things: pull from an
in-memory queue, call a handler per item, and compare two floats. There is no
network call, no database, no `import`, no `fsync`, and no unbounded loop — the
drain is capped at `max_drain_per_tick` so one flooded inbox cannot starve the
beat.

The INGRESS callable is the one thing that touches the outside world, and it is
the loop's stand-in for §5:322's *"ZMQ inbox"* — the spec puts that read inside
the loop, so this is the specified placement and not an exception to §11. What
§11 bans is expensive work in the pathway that DECIDES; reading the arriving
message is what produces the thing to decide about. `scripts/limiterd.py` is the
one supplier today and its reader is bounded per tick for the same reason the
drain is.

------------------------------------------------------------------------------
THE SENDER THREAD IS A STUB AND IS STILL A REAL OS THREAD
------------------------------------------------------------------------------
§5:323 gives the Limiter *"one low-priority sender thread (blocking I/O,
releases GIL; hung socket contained; hot loop never blocks)"*. `SenderThread`
places no orders — §2A's `place_order` is not called anywhere in this arc and
must not be — but it is a genuine `threading.Thread` blocking on a
`queue.Queue`, so `/proc/<pid>/task` shows two tasks and the *shape* of the
threading model is measurable from outside the process before any order exists.

Its nice value is raised (priority lowered) from inside the thread via
`os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), ...)`. On Linux
`PRIO_PROCESS` with a TID applies to that thread alone; on a platform where it
applied process-wide it would silently nice the HOT LOOP, which is the opposite
of §5:323. So the loop reads its own nice before and after starting the sender
and records a fault if it moved — the hazard is measured, not assumed away.

------------------------------------------------------------------------------
KNOBS ARE DERIVED (CLAUDE.md directive 3)
------------------------------------------------------------------------------
`heartbeat_interval_s` is §12A:832's `HEARTBEAT_INTERVAL` and its single
physical home is `risks/limiter.config.json`. `heartbeat_interval_from_config`
reads it through `scripts/risk_config.py`'s own loader and validator; no number
is spelled here. Unlike `nixsentinel/config.py` — which reads two files
standalone because a deadman must not die of a sibling's typo — the Limiter uses
the full `load_risk_configs`: it IS the process for which a broken sibling config
means the boot is wrong.

`TICKS_PER_HEARTBEAT` is a **declared Nix addition**. §12A names no tick cadence
for the Limiter loop, so the tick interval is derived as
`heartbeat_interval_s / TICKS_PER_HEARTBEAT` rather than introduced as a
twentieth knob in `risks/limiter.config.json` — a knob nothing in the spec
authorises is a second authority, and the brief for this arc forbids one.

------------------------------------------------------------------------------
`debug.md` §7.12 — THE STANDING QUESTION for this module: what would have to be
true for `LimiterLoop.run()` to complete while proving nothing?
------------------------------------------------------------------------------
  1. **`max_ticks` is 1 and the loop returns having ticked once.** Not closed by
     construction and not closable here — it is the caller's choice, and a test
     harness legitimately wants it. CLOSED IN THE INSTRUMENT instead:
     `LoopStop.ticks` and `LoopStop.heartbeats` are both reported, so a run that
     ticked once and beat once is visible as such rather than as "it ran".
  2. **The heartbeat never fires because `heartbeat_interval_s` is enormous.**
     GUARDED: the FIRST tick always publishes (`_next_beat_at` starts unset), so
     `heartbeats >= 1` for any run that ticked at all, and a run that ticked zero
     times reports `ticks == 0`.
  3. **The sender thread was never started, so the two-task claim is false.**
     GUARDED: `run()` starts it before the first tick and `LoopStop.sender_alive`
     records whether it was alive at stop; `SenderThread.started` is an
     `Event` waited on, not a hope.
  4. **The registry is empty, so the one-in-flight lock is never exercised.**
     Not closable here — an idle Limiter is a legitimate state. Reported:
     `LoopStop.registrations` and `LoopStop.in_flight` are both in the final
     record, so an idle run says it was idle.
  5. **Nothing ever called `tick`, and `run` exited on the stop flag first.**
     GUARDED: `stop()` is read at the TOP of the tick, so a loop stopped before
     it ever ran reports `ticks == 0` and the reason that stopped it.
"""

from __future__ import annotations

# C0302 (too-many-lines): this module is one §5:322 event loop plus the ONE
# invariant ARC 040 put inside it, and the length is documentation rather than
# code — the prose blocks above and the §-citing reason strings below outweigh
# the executable lines. Splitting the breaker out of the loop to clear a line
# count would put §4:212's duration measurement in a module with no clock.
# pylint: disable=too-many-lines
import os
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import risk_config
from nixsentinel.heartbeat import HeartbeatPublisher
from nixsentinel.seam import Heartbeat

from nixrisk.gate import InFlightPort
from nixrisk.recovery import (
    RecoveryError,
    Registration,
    ReleasedInFlight,
    StrategyRegistry,
)

#: Named once so every refusal below points at the same file. Doctrine C.2: the
#: instrument names the site, and a reason that names no site sends the reader
#: hunting through a package for the sentence that produced it.
SITE: Final[str] = "scripts/nixrisk/loop.py"

#: The module whose `risks/*.config.json` carries §12A:832's interval. Its single
#: physical home; `nixsentinel/config.py` reads the same key from the same file
#: for the same reason (directive 3 — one number, one home).
CONFIG_MODULE: Final[str] = "limiter"
HEARTBEAT_INTERVAL_KEY: Final[str] = "heartbeat_interval_s"

#: §12A:831's `GO_TIMEOUT_T`. Its one physical home is the SAME
#: `risks/limiter.config.json` the interval above comes from, and this is the
#: name under which that file spells it. ARC 038 (F) measured that no shipped
#: module outside `scripts/risk_config.py`'s cross-knob validator read this
#: key: the deadlock breaker was a knob nobody read, which is why §14:971's
#: *"it can never wedge (GO-timeout)"* had no implementation. This module is
#: the first reader (CHECK-DEBT D3.398).
GO_TIMEOUT_KEY: Final[str] = "go_timeout_s"

#: DECLARED NIX ADDITION — see the module docstring. §12A names no tick cadence,
#: so the loop's is DERIVED from the one interval the spec does give rather than
#: landed as a new knob. Twenty ticks per beat means the beat is never later than
#: 5% of its own interval, which is the resolution the §12.1 watcher needs, and
#: it keeps `stop()` latency (one tick) at 50 ms on the shipped 1 s interval.
TICKS_PER_HEARTBEAT: Final[int] = 20

#: How many queued items one tick may handle. §11:581's discipline made physical:
#: an unbounded drain lets one flooded inbox hold the tick open past the beat's
#: deadline, and a late beat is indistinguishable to the Sentinel from a dead
#: Limiter. Work that does not fit stays queued for the next tick.
DEFAULT_DRAIN_PER_TICK: Final[int] = 64

#: The nice increment applied to §5:323's sender thread. POSITIVE = lower
#: priority, and a positive increment is the one direction an unprivileged
#: process may always take, so the sender can never fail to yield to the loop
#: for want of a capability.
DEFAULT_SENDER_NICE: Final[int] = 5

#: How long a clean stop waits for the sender to drain. Bounded deliberately:
#: §5:323 puts the sender there precisely so a *hung socket is contained*, and a
#: shutdown that joined it forever would let the contained fault take the process
#: down after all.
SENDER_JOIN_TIMEOUT_S: Final[float] = 2.0

#: The sender's record of what it was handed, bounded. A daemon that appended
#: forever would leak; the ledger is an observation for the gate and the tests,
#: not evidence (§9's Plane-1 log is evidence and this is not it).
SENDER_LEDGER_MAX: Final[int] = 256

#: Fault strings kept for the final record, bounded for the same reason.
FAULT_LEDGER_MAX: Final[int] = 64

#: The OS thread name, so `/proc/<pid>/task/<tid>/comm` names the §5:323 thread
#: rather than showing an anonymous `python3`. Truncated by the kernel to 15
#: bytes, so it is chosen short enough to survive that.
SENDER_THREAD_NAME: Final[str] = "nix-sender"

#: §4:203-205's outcome vocabulary, transcribed rather than invented: *"every
#: outcome (sized / denied / pending / open / closed / rejected /
#: protective-flatten) is pushed to the originating strategy FSM"*. Split in two
#: because ONE of the seven is not terminal — §4:201-202 makes `pending` the
#: state the one-in-flight lock is held THROUGH, so a release on it would free
#: the lock on a live order, which is the §4:243 indeterminate case arriving by
#: the front door.
TERMINAL_OUTCOMES: Final[frozenset[str]] = frozenset(
    {"sized", "denied", "open", "closed", "rejected", "protective-flatten"}
)
NON_TERMINAL_OUTCOMES: Final[frozenset[str]] = frozenset({"pending"})


class LoopError(RuntimeError):
    """A violation of the loop's own threading contract, or a boot refusal.

    Never caught and downgraded inside this module. Every condition that raises
    it is one under which §5:322's *single-threaded event loop* has already
    stopped being true, and continuing would produce a process that looks like a
    Limiter and is not one (directive 4: fail closed and loud).

    Deliberately DISTINCT from a handler fault. A command that cannot be parsed
    is contained and counted — see `LimiterLoop.tick` — because a strategy that
    could kill the Risk Engine by writing a bad file would be a remote kill
    switch on the process holding every synthetic stop.
    """


@dataclass(frozen=True)
class SenderHandoff:
    """One item the loop handed to §5:323's sender thread. AN OBSERVATION.

    Recorded by the sender AT THE MOMENT IT DEQUEUED it, so the ledger shows what
    actually crossed the thread boundary rather than what the loop intended to
    send. `tick` is the loop tick that handed it over, which is what makes the
    handoff traceable back to the serial pass that produced it (§5:324).
    """

    seq: int
    tick: int
    payload: object


# R0902 (too-many-instance-attributes): six of the ten are the thread's own
# OBSERVATIONS — native id, effective nice, the priority refusal, the handoff
# count, the started Event and the ledger — and each exists because a gate
# reads it from outside. Folding them into a sub-object to satisfy a counter
# would put the measured facts one indirection away from the thread that
# produced them.
# pylint: disable=too-many-instance-attributes
class SenderThread:
    """§5:323's ONE low-priority sender thread. A STUB: it records, never sends.

    A stub that is a real OS thread, deliberately. The property this arc can
    prove from outside the process is the SHAPE of §5's threading model — two
    tasks under `/proc/<pid>/task`, one of them blocked on a queue at a lower
    priority — and that property is falsified by a design that "will add the
    thread when there is something to send". §2A's `place_order` is not called
    here and must not be until the broker seam is wired into a running Limiter.

    Blocking `queue.Queue.get()` is the point, not an implementation detail:
    §5:323 puts blocking I/O on this thread so the *hot loop never blocks*, and
    `hand_off` uses an unbounded `put`, which never blocks the caller.
    """

    def __init__(
        self,
        *,
        nice: int = DEFAULT_SENDER_NICE,
        ledger_max: int = SENDER_LEDGER_MAX,
    ) -> None:
        self._queue: queue.Queue[object] = queue.Queue()
        self._ledger: deque[SenderHandoff] = deque(maxlen=ledger_max)
        self._nice = int(nice)
        self._handoffs = 0
        self._stop = object()
        self._started = threading.Event()
        self._thread = threading.Thread(
            target=self._serve, name=SENDER_THREAD_NAME, daemon=True
        )
        #: Set by the thread itself, from inside itself. A native id read by the
        #: parent would be the parent's.
        self.native_id: int | None = None
        #: The nice value read BACK after setting it. Reading back rather than
        #: trusting the setter is check contract v2 rule 2 applied one layer
        #: down: the return value of a mutating call is not a verification.
        self.nice_effective: int | None = None
        #: Empty when the priority was lowered. A REASON when it was not — never
        #: a bare False, because "could not lower the sender's priority" and
        #: "this kernel does not do per-thread nice" are different findings.
        self.priority_error: str = ""

    @property
    def alive(self) -> bool:
        """Is the OS thread running right now? Read from `threading`, not cached."""
        return self._thread.is_alive()

    @property
    def handoffs(self) -> int:
        """How many items the thread has actually dequeued. Not how many were put."""
        return self._handoffs

    def ledger(self) -> tuple[SenderHandoff, ...]:
        """The bounded record of what crossed the thread boundary, oldest first."""
        return tuple(self._ledger)

    def start(self, timeout: float = 1.0) -> None:
        """Start the thread and WAIT until it has announced its own native id.

        The wait is not politeness. Without it `native_id` is `None` for an
        unbounded window after `start()` returns, and a gate reading it would
        record "no sender thread" for a thread that was starting — a
        cannot-measure reported as a fail (check contract v2 rule 10, inverted).
        """
        self._thread.start()
        if not self._started.wait(timeout=timeout):
            raise LoopError(
                f"{SITE}: the §5:323 sender thread did not reach its serve loop "
                f"within {timeout}s — refusing to run a Limiter whose sender "
                "thread cannot be shown to exist, because the two-task shape is "
                "the only part of §5's threading model this arc can prove"
            )

    def hand_off(self, payload: object, *, tick: int) -> SenderHandoff:
        """Queue one item from the loop thread. NEVER BLOCKS (§5:323-324).

        Returns the handoff record the loop can keep; the sender appends its own
        copy when it dequeues, so the two together show anything stuck in the
        queue.
        """
        record = SenderHandoff(seq=self._handoffs + 1, tick=tick, payload=payload)
        self._queue.put(record)
        return record

    def stop(self, timeout: float = SENDER_JOIN_TIMEOUT_S) -> bool:
        """Ask the thread to finish and join it. `True` if it actually exited.

        The return value is READ by `LimiterLoop.run` and lands in `LoopStop`,
        because a sender that did not exit is exactly the *hung socket* §5:323
        expects to contain, and a shutdown that reported success anyway would
        hide the one fault the design anticipates.
        """
        if not self._thread.is_alive():
            return True
        self._queue.put(self._stop)
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def _serve(self) -> None:
        """The thread body: lower own priority, then block on the queue forever."""
        self.native_id = threading.get_native_id()
        self._lower_priority()
        self._started.set()
        while True:
            item = self._queue.get()
            try:
                if item is self._stop:
                    return
                if isinstance(item, SenderHandoff):
                    self._ledger.append(item)
                    self._handoffs += 1
            finally:
                self._queue.task_done()

    def _lower_priority(self) -> None:
        """§5:323's *low-priority*, applied to THIS thread and then read back."""
        tid = self.native_id
        if tid is None:  # pragma: no cover - set two lines before every call
            return
        try:
            os.setpriority(os.PRIO_PROCESS, tid, self._nice)
            self.nice_effective = os.getpriority(os.PRIO_PROCESS, tid)
        except OSError as exc:
            self.priority_error = (
                f"{SITE}: cannot lower the §5:323 sender thread's priority to "
                f"nice {self._nice} on tid {tid}: {exc!r}. The thread still runs "
                "and the loop is still single-threaded; what is lost is the "
                "guarantee that a busy sender yields to the hot loop"
            )
            return
        if self.nice_effective != self._nice:
            self.priority_error = (
                f"{SITE}: asked for nice {self._nice} on the §5:323 sender "
                f"thread and read back {self.nice_effective} — the kernel did "
                "not apply what was requested, so the priority separation §5:323 "
                "relies on is not in effect"
            )


@dataclass(frozen=True)
class GoTimeout:
    """ONE firing of §4:210-212's deadlock breaker. AN OBSERVATION.

    `elapsed_s` is the loop's OWN monotonic clock measured between the tick that
    admitted the GO and the tick that broke it — not a `time.time()` read taken
    at whichever call site happened to notice. Two reasons, both of them the
    property this record exists to make checkable: a wall-clock read is not
    monotonic, so an NTP step could make a breaker fire early or never on a
    process whose whole job is holding money-bearing state; and a reading taken
    off the clock the beat is published from is the ONLY reading whose lateness
    is bounded by the same tick cadence §12.1:604's Sentinel is watching.

    `resent` is `False` and is a field rather than a comment because §4:240-241
    forbids the auto-resend outright — *"issue order-status query, never auto-
    resend"* — and a breaker that re-placed would turn one intended order into
    two. A record that could only say *what it released* could not say that it
    released and did nothing else.
    """

    strategy_id: str
    client_order_id: str
    admitted_tick: int
    fired_tick: int
    elapsed_s: float
    timeout_s: float
    released: bool
    resent: bool = False

    @property
    def reason(self) -> str:
        """The §4-citing sentence an operator reads. Check contract v2 rule 11."""
        return (
            f"{SITE}: §4:210-212 GO-timeout FIRED for {self.strategy_id!r} — "
            f"{self.client_order_id!r} was admitted on tick {self.admitted_tick} "
            f"and had no terminal feedback {self.elapsed_s:.3f}s later on tick "
            f"{self.fired_tick}, past the {self.timeout_s}s "
            f"limiter.{GO_TIMEOUT_KEY}. The GO is treated as DENIED and the "
            f"strategy is reset to flat-and-free; released={self.released}, "
            f"resent={self.resent} (§4:240-241 forbids the resend)"
        )


# R0902 (too-many-instance-attributes): a RECORD, not an object with
# behaviour. Every field is one observation the arc-end evidence needs, and
# a record that reported fewer facts to clear a threshold would be a
# smaller record, not a simpler design.
# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class LoopStop:
    """THE DOCUMENTED FINAL STATE of one `LimiterLoop.run()`. Returned, not printed.

    Every field is an OBSERVATION taken after the loop exited and after the
    sender was joined, so the record describes the state the process is actually
    leaving behind rather than the state it intended to leave. `scripts/limiterd.py`
    is what persists it; this module writes no file, which is what keeps the tick
    body free of the `fsync` §11:581 excludes.
    """

    reason: str
    ticks: int
    heartbeats: int
    last_seq: int
    last_beat_ts: float | None
    registrations: tuple[str, ...]
    in_flight: tuple[tuple[str, str], ...]
    sender_alive: bool
    sender_joined: bool
    sender_handoffs: int
    overruns: int
    #: Every §4:210-212 breaker firing this run, oldest first. An EMPTY tuple on
    #: a run that held no lock is the honest reading and is why the count is
    #: reported beside `in_flight` rather than instead of it: a timeout that
    #: never fired because nothing was ever in flight has measured nothing, and
    #: the pair says so.
    go_timeouts: tuple[GoTimeout, ...] = field(default_factory=tuple)
    faults: tuple[str, ...] = field(default_factory=tuple)

    @property
    def flat(self) -> bool:
        """Does this process hold no in-flight lock at all?

        The IN-PROCESS half of §12.2:618's *"Boot-flatten makes any single
        restart safe by design"*. It says nothing about the BROKER — that is
        `nixrisk/coldstart.py`'s ground-truth query and it is not wired into a
        running Limiter in this arc. A reader that took this for the broker's
        answer would be taking the one claim §4's cold-start section calls
        trustless.
        """
        return not self.in_flight


def heartbeat_interval_from_config(root: Path | None = None) -> float:
    """§12A:832's `HEARTBEAT_INTERVAL`, read from its one physical home.

    Goes through `risk_config.load_risk_configs`, which loads AND cross-knob
    validates every module the Limiter's boot depends on (§12A:801-802 requires
    that validation to happen *"before any strategy registers"*, and this is
    called before the loop is constructed). It is deliberately the whole-set
    loader and not `nixsentinel/config.py`'s narrow two-file read: the Sentinel
    reads narrowly so a sibling's typo cannot take the deadman down with it,
    while for the Limiter a sibling's typo IS a wrong boot.

    No default. `risk_config.RiskConfigError` propagates (directive 4): a Limiter
    that invented an interval would publish a beat on a cadence the Sentinel's
    threshold was not derived from, and the two would disagree about how long
    silence means death.
    """
    configs = risk_config.load_risk_configs(root)
    return risk_config.knob(configs.modules[CONFIG_MODULE], HEARTBEAT_INTERVAL_KEY)


def go_timeout_from_config(root: Path | None = None) -> float:
    """§12A:831's `GO_TIMEOUT_T`, read from its one physical home.

    THE READ ARC 038 (F) MEASURED AS MISSING. Deliberately the same
    `load_risk_configs` path as `heartbeat_interval_from_config` above and for
    the same reason: `risks/limiter.config.json` carries a cross-knob boot rule
    `liveness.go_timeout_outlasts_pending_ack` whose whole purpose is to reject
    a timeout that would fire while the Limiter's own pending-ack machinery is
    still resolving the same GO — *"the breaker fires on the healthy path"*, in
    that file's own words. Reading the number through the validator is what
    makes that rule govern the reader; reading the raw JSON here would leave the
    rule validating a value this module then ignored.

    No default (directive 4). A breaker that invented its own T would deny GOs
    the strategy still believes are live, and §4:211-212 has the strategy reset
    to flat-and-free on that signal — a wrong T is a wrong flat.
    """
    configs = risk_config.load_risk_configs(root)
    return risk_config.knob(configs.modules[CONFIG_MODULE], GO_TIMEOUT_KEY)


def tick_interval_for(heartbeat_interval_s: float) -> float:
    """The DERIVED tick cadence — `heartbeat_interval_s / TICKS_PER_HEARTBEAT`.

    One function so the derivation has one home. `scripts/limiterd.py` calls it
    for its `--tick-interval` default and this module calls it for the
    constructor's, which is what stops the entrypoint's default and the loop's
    from drifting into two different numbers (directive 3).
    """
    if heartbeat_interval_s <= 0.0:
        raise LoopError(
            f"{SITE}: heartbeat interval {heartbeat_interval_s!r} is not "
            "positive — §12A:832 gives HEARTBEAT_INTERVAL as 1s and a "
            "non-positive interval is a beat that is always due, which is a "
            "busy loop rather than a cadence"
        )
    return heartbeat_interval_s / TICKS_PER_HEARTBEAT


# R0902 (too-many-instance-attributes): the loop IS the process's state. Every
# attribute below is either a §5 collaborator (registry, sender, heartbeat), a
# cadence value derived from §12A:832, or an observation a gate reads from
# outside. Bundling them into sub-objects to satisfy a counter would put the
# thing being measured one indirection away from the measurement.
# pylint: disable=too-many-instance-attributes
class LimiterLoop:
    """§5:322's single-threaded event loop, as a thing that runs.

    ONE thread ticks. The tick drains, handles, and beats — in that order, with
    the beat last so `seq` means *a tick completed*. A second thread exists and
    does nothing but block on a queue at a lower nice value, because §5:323 says
    there is exactly one and it is low priority.

    THE REGISTRY IS AN ATTRIBUTE, NOT A FIXTURE. `self.registry` is created once
    per process and mutated in place. Every prior proof of the one-in-flight lock
    in this tree built a fresh `StrategyRegistry` inside the assertion that read
    it, which proves the class and proves nothing about the Limiter; a lock that
    lives as long as the process is the only version of §4:208-209 that a second
    process can observe being held.

    HOW THE LOCK IS EVALUATED, AND WHY NOT THROUGH `gate.InFlightLockRule`.
    `InFlightLockRule` is the production rule and it reads exactly the port this
    loop holds — but its `evaluate` signature takes a sized `ProposedOrder` and a
    `FinancialPicture`, and this arc has neither: the Allocator is a separate
    process (§2:38) that is not wired to a running Limiter yet. Fabricating an
    order to satisfy a rule that reads one field of it would put an invented
    `qty` and `margin_per_contract` into the very object the Phase-B rules read,
    and the next author who adds a rule at that call site would inherit a
    fabricated size for free. So `take_in_flight` below consults the SAME frozen
    `gate.InFlightPort` verb the rule consults — `StrategyRegistry.in_flight` —
    and the refusal names §3:140 and §4:208-210 explicitly. When a real
    `ProposedOrder` exists, this call site becomes a `GatePass` and the rule runs
    for real.
    """

    # R0913 (too-many-arguments): every one is KEYWORD-ONLY and every one is
    # either a §5 collaborator or a cadence the caller must be able to state.
    # The two clock seams (`monotonic`, `sleeper`) exist so a control can drive
    # the cadence deterministically rather than measuring `time.sleep`; removing
    # them would make the beat's placement untestable, which is the property this
    # module exists to hold.
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        *,
        heartbeat: HeartbeatPublisher,
        heartbeat_interval_s: float,
        tick_interval_s: float | None = None,
        registry: StrategyRegistry | None = None,
        ingress: Callable[[int], object] | None = None,
        handler: Callable[[object], None] | None = None,
        go_timeout_s: float,
        max_ticks: int = 0,
        max_drain_per_tick: int = DEFAULT_DRAIN_PER_TICK,
        sender_nice: int = DEFAULT_SENDER_NICE,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if heartbeat_interval_s <= 0.0:
            raise LoopError(
                f"{SITE}: heartbeat_interval_s={heartbeat_interval_s!r} is not "
                "positive. §12A:832 gives HEARTBEAT_INTERVAL as 1s"
            )
        tick_s = (
            tick_interval_for(heartbeat_interval_s)
            if tick_interval_s is None
            else float(tick_interval_s)
        )
        if tick_s <= 0.0:
            raise LoopError(
                f"{SITE}: tick_interval_s={tick_s!r} is not positive — a tick "
                "with no interval is a busy loop, and §5:324's *hot loop never "
                "blocks* is not an instruction to spin"
            )
        if tick_s > heartbeat_interval_s:
            raise LoopError(
                f"{SITE}: tick_interval_s={tick_s!r} exceeds "
                f"heartbeat_interval_s={heartbeat_interval_s!r}. The beat is "
                "published from the tick, so a tick slower than the beat cannot "
                "keep §12A:832's cadence and the Sentinel would read a "
                "systematically late heartbeat as a sick Limiter"
            )
        if float(go_timeout_s) <= 0.0:
            raise LoopError(
                f"{SITE}: go_timeout_s={go_timeout_s!r} is not positive. "
                "§12A:831 gives GO_TIMEOUT_T as the deadlock breaker's T and a "
                "non-positive T fires on the tick that admitted the GO — every "
                "GO denied, order flow shredded, and the gate beside it still "
                "green because 'the timeout works'"
            )
        if float(go_timeout_s) <= tick_s:
            raise LoopError(
                f"{SITE}: go_timeout_s={go_timeout_s!r} does not outlast one "
                f"tick ({tick_s!r}s). §4:210-212's breaker measures elapsed time "
                "ACROSS ticks; a T inside one tick cannot distinguish a lost GO "
                "from a GO the loop has not yet had a chance to serve"
            )
        if int(max_drain_per_tick) < 1:
            raise LoopError(
                f"{SITE}: max_drain_per_tick={max_drain_per_tick!r} — a tick "
                "that may handle no work is a loop that beats and never serves"
            )
        registry = StrategyRegistry() if registry is None else registry
        if not isinstance(registry, InFlightPort):
            raise LoopError(
                f"{SITE}: the live registry {type(registry).__name__!r} does not "
                "satisfy the frozen gate.InFlightPort — the loop's own state must "
                "be readable by §3:140's rule or the rule reads something else"
            )

        self.heartbeat_interval_s = float(heartbeat_interval_s)
        #: §12A:831's T. LIVE — read once at boot per §12.11's restart-only
        #: config lifecycle, never re-read inside the tick.
        self.go_timeout_s = float(go_timeout_s)
        self.tick_interval_s = tick_s
        self.max_ticks = int(max_ticks)
        self.max_drain_per_tick = int(max_drain_per_tick)
        #: LIVE STATE. Mutated in place for the life of the process (§4:208-209).
        self.registry: StrategyRegistry = registry
        self.sender = SenderThread(nice=sender_nice)
        self.tick_count = 0
        self.heartbeats_published = 0
        self.overruns = 0
        #: Every thread ident that has EVER published a beat. The observation the
        #: gate reads: one element, equal to the loop's own ident, is the §12.1
        #: property. Two elements is the catastrophe named in the module docstring.
        self.heartbeat_publisher_idents: set[int] = set()
        #: strategy_id -> (client_order_id, admitted_at_monotonic, admitted_tick).
        #: THE CLOCK §4:212's *"within T"* is measured on. Stamped by
        #: `take_in_flight` at the moment the lock was taken and cleared by every
        #: path that releases it, so the map and `registry.in_flight` cannot
        #: disagree about whether something is in flight — a second copy of that
        #: fact is exactly what `in_flight_holders` refuses to keep.
        self._go_admitted: dict[str, tuple[str, float, int]] = {}
        #: Every breaker firing this process has seen, bounded like the others.
        self._go_timeouts: deque[GoTimeout] = deque(maxlen=FAULT_LEDGER_MAX)

        self._heartbeat = heartbeat
        self._ingress = ingress
        self._handler = handler
        self._monotonic = monotonic
        self._sleep = sleeper
        self._inbox: queue.Queue[object] = queue.Queue()
        self._faults: deque[str] = deque(maxlen=FAULT_LEDGER_MAX)
        self._loop_ident: int | None = None
        self._loop_native_id: int | None = None
        self._in_tick = False
        self._next_beat_at: float | None = None
        self._last_beat: Heartbeat | None = None
        self._stopping = False
        self._stop_reason = ""

    # -- observations -------------------------------------------------------

    @property
    def heartbeat_seq(self) -> int:
        """The publisher's own `seq` — beats published by THIS process.

        Read off `HeartbeatPublisher`, never counted here in parallel: a second
        counter could disagree with the number in the file the Sentinel reads,
        and the file is the one that matters (directive 3).
        """
        return self._heartbeat.seq

    @property
    def last_beat(self) -> Heartbeat | None:
        """The last record published, or `None` before the first tick."""
        return self._last_beat

    def faults(self) -> tuple[str, ...]:
        """Contained failures, oldest first. Each one names its site and cause."""
        return tuple(self._faults)

    def in_flight_holders(self) -> tuple[tuple[str, str], ...]:
        """Every `(strategy_id, client_order_id)` holding the §4:208 lock.

        DERIVED from the registry on every call. A cached copy would be a second
        home for the one fact the lock is, and the two could disagree at exactly
        the moment the disagreement costs money.
        """
        held: list[tuple[str, str]] = []
        for strategy_id in self.registry.registered():
            row = self.registry.get(strategy_id)
            if row is not None and row.in_flight is not None:
                held.append((strategy_id, row.in_flight))
        return tuple(held)

    def positions_open_hint(self) -> int:
        """What the beat carries as §12.1's *positions possibly open* hint.

        This arc has no position table — nothing here fills, so nothing here can
        open. An IN-FLIGHT order is the only thing this process holds that could
        BECOME a position, so the count of held locks is the honest upper bound
        available, and it errs in the direction §12.1:604 wants: *positions
        possibly open*. The seam's `Heartbeat` docstring already fixes this field
        as a non-authoritative hint the Sentinel must not act on — it asks its own
        broker session — so an upper bound here misleads nobody and tells an
        operator reading the file afterwards what the dead process believed.
        """
        return len(self.in_flight_holders())

    # -- live state, owned by the loop --------------------------------------

    def allocate_slot(self) -> int:
        """The lowest slot integer no live registration holds. §4:266-268's *slot*.

        DERIVED from the registry rather than kept as a counter, so a slot freed
        by `force_deregister` is genuinely reusable and there is no second copy of
        the occupancy set to fall out of step with the rows. O(n) over at most the
        1-5 concurrent instruments `CLAUDE.md` fixes as the operating scope.
        """
        taken = {
            row.slot
            for row in (
                self.registry.get(strategy_id)
                for strategy_id in self.registry.registered()
            )
            if row is not None and row.slot is not None
        }
        slot = 0
        while slot in taken:
            slot += 1
        return slot

    def admit(self, strategy_id: str, *, now: float) -> Registration:
        """Register one strategy into the LIVE table, allocating its slot.

        NOT an admission gate. §4/V34's *no strategy registers until provably
        flat* is `nixrisk/coldstart.py`'s property and is not wired into a running
        Limiter in this arc; this is the table-keeping half, and a duplicate is
        refused by `StrategyRegistry.register` itself naming §4:269-271.
        """
        self._require_loop_thread("admit")
        return self.registry.register(strategy_id, slot=self.allocate_slot(), now=now)

    def take_in_flight(
        self, strategy_id: str, client_order_id: str
    ) -> tuple[bool, str]:
        """§4:208-209's one-in-flight lock, taken against the loop's LIVE registry.

        Returns `(accepted, reason)` and NEVER a bare boolean: check contract v2
        rule 11 — the reason is the assertion, and a refusal that did not name the
        `client_order_id` already holding the lock would tell an operator that
        something is in flight without telling them what.

        The read goes through `StrategyRegistry.in_flight`, which is the frozen
        `gate.InFlightPort` verb `gate.InFlightLockRule` itself calls; see the
        class docstring for why the rule object is not driven directly this arc.
        """
        self._require_loop_thread("take_in_flight")
        locked, why = self.registry.in_flight(strategy_id)
        if locked:
            return False, (
                f"{SITE}: {why} — §3:140 puts the one-in-flight-per-strategy "
                f"lock in PHASE A and §4:208-209 rejects the next signal "
                f"with-reason until resolution, so {client_order_id!r} is "
                f"refused. §4:210-212's GO-timeout is the deadlock breaker for "
                f"this state and fires at {self.go_timeout_s}s "
                f"(limiter.{GO_TIMEOUT_KEY}), so this lock cannot wedge"
            )
        try:
            self.registry.take_in_flight(strategy_id, client_order_id)
        except RecoveryError as exc:
            return False, f"{SITE}: {exc}"
        # THE CLOCK STARTS HERE, on the loop's own monotonic, inside the tick
        # that admitted the GO. §4:212 measures T from the emission of the GO;
        # the admission is the first instant this process can observe, and it is
        # the LATER of the two, so the breaker is never early on account of it.
        self._go_admitted[strategy_id] = (
            client_order_id,
            self._monotonic(),
            self.tick_count,
        )
        return True, (
            f"{SITE}: {strategy_id!r} took the §4:208 one-in-flight lock with "
            f"{client_order_id!r}; §4:210-212's GO-timeout is armed at "
            f"{self.go_timeout_s}s (limiter.{GO_TIMEOUT_KEY})"
        )

    def resolve_in_flight(
        self, strategy_id: str, client_order_id: str, outcome: str
    ) -> tuple[bool, str]:
        """§4:203-206's TERMINAL FEEDBACK — the healthy release of the lock.

        *"every outcome (sized / denied / pending / open / closed / rejected /
        protective-flatten) is pushed to the originating strategy FSM"*. This is
        the Limiter side of that: the outcome arrived, the in-flight action is
        RESOLVED, the lock comes off and the strategy is free for its next
        signal — with no breaker involved.

        This verb is what makes the breaker falsifiable in the OTHER direction.
        A timeout with no normal release beside it cannot be shown not to fire
        early: every GO would end at the breaker, and a gate would read that as
        the invariant working. `pending` is refused for the reason
        `NON_TERMINAL_OUTCOMES` gives.
        """
        self._require_loop_thread("resolve_in_flight")
        if outcome in NON_TERMINAL_OUTCOMES:
            return False, (
                f"{SITE}: {outcome!r} is not a TERMINAL outcome — §4:201-202 "
                f"makes PENDING the state the §4:208 lock is held THROUGH, so "
                f"resolving on it would release the lock on a live order. "
                f"Terminal outcomes: {sorted(TERMINAL_OUTCOMES)}"
            )
        if outcome not in TERMINAL_OUTCOMES:
            return False, (
                f"{SITE}: unknown outcome {outcome!r}; §4:203-205 enumerates "
                f"{sorted(TERMINAL_OUTCOMES | NON_TERMINAL_OUTCOMES)}"
            )
        try:
            released = self.registry.release_in_flight(
                strategy_id,
                client_order_id=client_order_id,
                reason=f"§4:203-206 terminal feedback outcome={outcome!r}",
            )
        except RecoveryError as exc:
            return False, f"{SITE}: {exc}"
        if not released.held:
            return False, f"{SITE}: {released.reason}"
        self._go_admitted.pop(strategy_id, None)
        return True, f"{SITE}: {released.reason}"

    def go_timeouts(self) -> tuple[GoTimeout, ...]:
        """Every §4:210-212 breaker firing, oldest first. THE OBSERVATION.

        Read by `checks/check_go_timeout.py` from outside the process, through
        the stop record `scripts/limiterd.py` writes. A count alone would not
        distinguish *the breaker fired on a lost GO* from *the breaker fired on
        every GO including the healthy ones*, so each firing carries its own
        elapsed time against its own T.
        """
        return tuple(self._go_timeouts)

    def go_armed(self) -> tuple[tuple[str, str, float], ...]:
        """`(strategy_id, client_order_id, elapsed_s)` for every armed GO. LIVE.

        Elapsed is computed at READ time off the loop's clock, so an operator
        asking the running process how long a lock has been held gets the answer
        as of the question rather than as of the last tick that happened to look.
        """
        now = self._monotonic()
        return tuple(
            (strategy_id, cid, now - at)
            for strategy_id, (cid, at, _tick) in sorted(self._go_admitted.items())
        )

    def hand_to_sender(self, payload: object) -> SenderHandoff:
        """Hand one item across §5:323's thread boundary. NEVER BLOCKS.

        The stub's whole job. In a wired Limiter this is where a §2A
        `place_order` would be dispatched onto the low-priority thread so a hung
        socket is contained and *the hot loop never blocks* (§5:323-324); in this
        arc the thread records the item and sends nothing, which is what makes
        the THREADING SHAPE measurable from outside the process before any order
        exists to be got wrong.
        """
        self._require_loop_thread("hand_to_sender")
        return self.sender.hand_off(payload, tick=self.tick_count)

    # -- the loop -----------------------------------------------------------

    def attach(
        self,
        *,
        ingress: Callable[[int], object] | None = None,
        handler: Callable[[object], None] | None = None,
    ) -> None:
        """Wire the inbox reader and the per-item handler AFTER construction.

        Both collaborators in `scripts/limiterd.py` need the loop — the reader
        calls `submit`, the handler reads `tick_count` and mutates the live
        registry — so neither can be built before it. That is a construction
        order, not a lifecycle: `attach` refuses once the loop has started,
        because a handler swapped mid-run would mean two ticks of one process
        served commands under different rules, which is the same shape §12.11
        forbids for config.
        """
        if self._loop_ident is not None:
            raise LoopError(
                f"{SITE}: attach() called on a loop that has already ticked. "
                "Swapping the ingress or the handler mid-run would let two ticks "
                "of one process serve commands under different rules"
            )
        if ingress is not None:
            self._ingress = ingress
        if handler is not None:
            self._handler = handler

    def submit(self, item: object) -> None:
        """Queue one item for the next tick's drain. Callable from any thread.

        The ONE verb on this object that is deliberately not loop-thread-only: a
        `queue.Queue` put is the handoff, and §5:322's serial processing is about
        where work is HANDLED, not about where it is enqueued.
        """
        self._inbox.put(item)

    def stop(self, reason: str = "stop() called") -> None:
        """Ask the loop to exit at the top of its next tick. Signal-handler safe.

        A flag and a string, nothing else — no lock, no queue, no I/O. §12.2:617
        has systemd send `SIGTERM`, whose handler runs between bytecodes in the
        main thread, and anything that could block there would turn a clean stop
        into the supervisor's `SIGKILL`.
        """
        self._stopping = True
        if not self._stop_reason:
            self._stop_reason = reason

    def tick(self) -> int:
        """ONE pass: ingress, bounded drain, then the beat. Returns the tick number.

        The ORDER is the property, not a convenience (see the module docstring):
        the beat goes out last so a published `seq` means the whole tick
        completed. §11:581 — cache reads and arithmetic only; the only outside
        contact is the ingress callable, which is §5:322's ZMQ-inbox read.

        THE BREAKER RUNS AFTER THE DRAIN AND BEFORE THE BEAT, and both halves of
        that placement are the invariant rather than a preference:

        * AFTER the drain, because terminal feedback that arrived in this very
          tick has already been handled by the time the breaker looks. A breaker
          that ran first would fire on a GO whose `resolved` reply was sitting
          two lines below it in the same inbox — a FALSE RELEASE on the healthy
          path, which is the failure mode §0a of this arc's brief names and the
          one `risks/limiter.config.json`'s own
          `liveness.go_timeout_outlasts_pending_ack` rule exists to prevent one
          layer down.
        * BEFORE the beat, because §12.1:604's beat carries
          `positions_open_hint`, which is DERIVED from the held locks. A beat
          published before the breaker would tell the Sentinel a lock is held
          that this same tick already broke.
        """
        self._claim_loop_thread()
        self._in_tick = True
        try:
            self.tick_count += 1
            self._run_ingress()
            self._drain()
            self._break_go_deadlocks()
            self._beat_if_due()
        finally:
            self._in_tick = False
        return self.tick_count

    def run(self) -> LoopStop:
        """Block, ticking on the derived cadence, until stopped. Returns the state.

        Runs in the CALLING thread and adopts it as the loop thread — the caller
        is `scripts/limiterd.py`'s `main`, which must be the main thread so
        §12.2's `SIGTERM` lands where `stop()` can be reached.
        """
        self._claim_loop_thread()
        self._start_sender()
        next_tick_at = self._monotonic()
        while not self._stopping:
            if self.max_ticks and self.tick_count >= self.max_ticks:
                self._stop_reason = (
                    f"--max-ticks={self.max_ticks} reached; the safety stop fired, "
                    "not a fault"
                )
                break
            self.tick()
            next_tick_at += self.tick_interval_s
            now = self._monotonic()
            if now < next_tick_at:
                self._sleep(next_tick_at - now)
            else:
                # The tick took longer than its own interval. Counted rather than
                # slept away: an overrun is the first symptom of §11:581 being
                # violated, and resetting the schedule hides it.
                self.overruns += 1
                next_tick_at = now
        return self._final_state()

    # -- internals ----------------------------------------------------------

    def _claim_loop_thread(self) -> None:
        """Adopt the calling thread as THE loop thread, or refuse a second one.

        §5:322's *single-threaded* enforced rather than asserted. The refusal
        names BOTH idents because "some other thread ticked" is not actionable and
        "thread 140234 ticked a loop owned by 139871" is.
        """
        ident = threading.get_ident()
        if self._loop_ident is None:
            self._loop_ident = ident
            self._loop_native_id = threading.get_native_id()
            return
        if ident != self._loop_ident:
            raise LoopError(
                f"{SITE}: thread {ident} entered a loop owned by thread "
                f"{self._loop_ident}. §5:322 makes the Limiter a SINGLE-THREADED "
                "event loop and §5:324 says serial processing eliminates "
                "fill-vs-tick races BY CONSTRUCTION — a second ticking thread "
                "removes the construction and leaves the claim"
            )

    def _require_loop_thread(self, verb: str) -> None:
        """Refuse a mutation of live state from anywhere but the loop thread."""
        ident = threading.get_ident()
        if self._loop_ident is not None and ident != self._loop_ident:
            raise LoopError(
                f"{SITE}: {verb!r} called from thread {ident}, but the loop is "
                f"owned by thread {self._loop_ident}. §5:322's serial processing "
                "is what makes the one-in-flight lock race-free; a second thread "
                "mutating the registry restores the race the design removed"
            )

    def _start_sender(self) -> None:
        """Start §5:323's sender and PROVE it did not nice the hot loop with it."""
        before = self._own_nice()
        self.sender.start()
        after = self._own_nice()
        if self.sender.priority_error:
            self._faults.append(self.sender.priority_error)
        if before is not None and after is not None and before != after:
            self._faults.append(
                f"{SITE}: lowering the §5:323 sender thread's priority moved the "
                f"LOOP thread's nice from {before} to {after} — on this kernel "
                "os.setpriority(PRIO_PROCESS, tid) is process-wide, so the hot "
                "loop was niced along with the sender, which is the opposite of "
                "§5:323"
            )

    def _own_nice(self) -> int | None:
        """This thread's nice value, or `None` if the platform will not say."""
        tid = self._loop_native_id
        if tid is None:  # pragma: no cover - set by _claim_loop_thread first
            return None
        try:
            return os.getpriority(os.PRIO_PROCESS, tid)
        except OSError:
            return None

    def _run_ingress(self) -> None:
        """§5:322's inbox read. Contained: a bad message must not kill the loop."""
        if self._ingress is None:
            return
        try:
            self._ingress(self.tick_count)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self._faults.append(
                f"{SITE}: ingress raised on tick {self.tick_count}: "
                f"{type(exc).__name__}: {exc}. Contained — a Limiter that died "
                "of a malformed inbound message would be a remote kill switch on "
                "the process holding every synthetic stop (§12.1:604)"
            )

    def _drain(self) -> int:
        """Handle at most `max_drain_per_tick` queued items. Returns how many."""
        handled = 0
        while handled < self.max_drain_per_tick:
            try:
                item = self._inbox.get_nowait()
            except queue.Empty:
                break
            handled += 1
            if self._handler is None:
                continue
            try:
                self._handler(item)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                self._faults.append(
                    f"{SITE}: handler raised on tick {self.tick_count} for "
                    f"{item!r}: {type(exc).__name__}: {exc}. Contained — a "
                    "Limiter that died of one bad command would be a remote "
                    "kill switch on the process holding every synthetic stop "
                    "(§12.1:604)"
                )
        return handled

    def _break_go_deadlocks(self) -> tuple[GoTimeout, ...]:
        """§4:210-212's DEADLOCK BREAKER, run once per tick on the LOOP'S CLOCK.

        *"if a strategy receives no sized/denied feedback within T of emitting
        GO (e.g. Allocator died holding it), it treats the GO as denied and
        resets to flat-and-free. The in-flight lock can never wedge on a lost
        message."* (§4:210-212, and §14:971 restates it as a locked invariant.)

        THE WHOLE MECHANISM IS THE COMPARISON ON THE NEXT LINE — `elapsed >=
        self.go_timeout_s` — and ARC 038 (F) measured that this tree contained
        no such comparison anywhere: a real SIGKILL of the GO holder left the
        lock held past the knob, on a loop that was alive, ticking and beating
        the whole time. The knob existed and nothing read it.

        THREE THINGS IT DOES NOT DO, each one a way this could pass while
        measuring nothing:
          * it does NOT resend, re-place, or retry (§4:240-241 — *"never auto-
            resend"*). `GoTimeout.resent` is a recorded `False`, not a comment;
          * it does NOT deregister. `release_in_flight` keeps the registration
            and the slot, because §4:211-212 resets the strategy to
            *flat-and-free* and a deregistration would be flat-and-GONE;
          * it does NOT fire on a strategy whose GO resolved normally — the
            stamp is popped by `resolve_in_flight` in the same tick's drain,
            which is why this runs after it.

        Reads the loop's own monotonic, never `time.time()`: T is a DURATION,
        and a wall clock that steps under an NTP correction would make the
        breaker fire early or never on the process holding every synthetic stop.
        """
        if not self._go_admitted:
            return ()
        now = self._monotonic()
        fired: list[GoTimeout] = []
        for strategy_id, (cid, admitted_at, admitted_tick) in sorted(
            self._go_admitted.items()
        ):
            elapsed = now - admitted_at
            if elapsed < self.go_timeout_s:
                continue
            released: ReleasedInFlight = self.registry.release_in_flight(
                strategy_id,
                client_order_id=cid,
                reason=(
                    f"§4:210-212 GO-timeout: no terminal feedback in "
                    f"{elapsed:.3f}s against T={self.go_timeout_s}s"
                ),
            )
            record = GoTimeout(
                strategy_id=strategy_id,
                client_order_id=cid,
                admitted_tick=admitted_tick,
                fired_tick=self.tick_count,
                elapsed_s=elapsed,
                timeout_s=self.go_timeout_s,
                released=released.held,
            )
            fired.append(record)
            self._go_timeouts.append(record)
        for record in fired:
            # Popped only AFTER the release succeeded. A stamp dropped first
            # would leave a lock held by a strategy the breaker no longer
            # watches — the wedge, rebuilt by the code that breaks it.
            self._go_admitted.pop(record.strategy_id, None)
        return tuple(fired)

    def _beat_if_due(self) -> Heartbeat | None:
        """Publish §12.1's beat if `heartbeat_interval_s` has elapsed. LOOP CLOCK."""
        now = self._monotonic()
        if self._next_beat_at is not None and now < self._next_beat_at:
            return None
        beat = self._publish_heartbeat()
        self._next_beat_at = now + self.heartbeat_interval_s
        return beat

    def _publish_heartbeat(self) -> Heartbeat:
        """The ONLY call to `HeartbeatPublisher.publish` in this process.

        Two refusals, both of them the §12.1 catastrophe named in the module
        docstring: a beat from another thread, and a beat from this thread but
        outside a tick. Either one produces a `seq` that climbs while the event
        loop is wedged, which is the reading the Sentinel must never be given.
        """
        ident = threading.get_ident()
        if self._loop_ident is None:
            raise LoopError(
                f"{SITE}: refusing to publish a §12.1:604 heartbeat before the "
                "loop has started. A beat that precedes the loop tells the "
                "Sentinel a Limiter is alive that has not yet ticked once"
            )
        if ident != self._loop_ident:
            raise LoopError(
                f"{SITE}: thread {ident} tried to publish the §12.1:604 "
                f"heartbeat; only the loop thread {self._loop_ident} may. A beat "
                "published off the loop advances while the loop is wedged, and "
                "the Sentinel then reads a climbing seq and never fires its "
                "emergency flatten — with positions open"
            )
        if not self._in_tick:
            raise LoopError(
                f"{SITE}: refusing to publish the §12.1:604 heartbeat from "
                "outside a tick. seq must mean *a tick completed*; a beat "
                "published beside the tick means only that something in this "
                "process is still able to write a file"
            )
        beat = self._heartbeat.publish(self.positions_open_hint())
        self.heartbeat_publisher_idents.add(ident)
        self.heartbeats_published += 1
        self._last_beat = beat
        return beat

    def _final_state(self) -> LoopStop:
        """Join the sender, then take one reading of everything. Never partial."""
        joined = self.sender.stop()
        return LoopStop(
            reason=self._stop_reason or "run() returned with no reason recorded",
            ticks=self.tick_count,
            heartbeats=self.heartbeats_published,
            last_seq=self._heartbeat.seq,
            last_beat_ts=None if self._last_beat is None else self._last_beat.ts,
            registrations=self.registry.registered(),
            in_flight=self.in_flight_holders(),
            sender_alive=self.sender.alive,
            sender_joined=joined,
            sender_handoffs=self.sender.handoffs,
            overruns=self.overruns,
            go_timeouts=self.go_timeouts(),
            faults=self.faults(),
        )
