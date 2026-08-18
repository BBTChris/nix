"""Is the ranking table's WRITER alive? — the observation §12.7's clock cannot make.

ARC 037 / sub-agent D. Authority: `docs/nics_risk_subsystem_spec_v1.3.md`
§6.6:465-468 (**FALLBACK, locked** — *"if the Scoring process is down or its
table is stale, both Allocator and Limiter fall back to first-come-first-served
… Ranking is an optimization, never a safety gate: a scoring outage must NEVER
halt order flow"*), §12.7:644-662 (mirror model, freshness stamps, *mirror
incomplete ⇒ treated as stale*), §12.9 (Warning: *Scoring down ⇒ FCFS*).

Repairs `docs/CHECK-DEBT.md` D3.244.

------------------------------------------------------------------------------
THE DEFECT, AS MEASURED — "RANKED FROM A CORPSE"
------------------------------------------------------------------------------

ARC 036 measured, on this node: **144,699 arbitrations decided RANKED from a
dead process's frozen table over a 0.483 s window**, at `stale_after_s = 0.5`.
(D3.244's own row carries the first run's figures, 140,830 over 0.476 s; the
integrated tree re-measured 144,699 / 0.483 s. Both are the same fact.)

The mechanism is not subtle and it is not a bug in anything: **the subscriber
socket outlives the publisher.** libzmq keeps the SUB endpoint open and simply
stops receiving, so the consumer's mirror stays *complete, populated and
confident* — every row present, every field well-formed — and it answers RANKED
from it until the table's AGE crosses `stale_after_s`. §6.6's locked fallback
fires eventually and order flow never stops; what is wrong is only that the
window is a **function of a tunable** rather than of the death.

**Staleness is an age over a TABLE. Liveness is a fact about the WRITER.**
§12.7's freshness stamp measures the first and was never asked to measure the
second. Using the age as a stand-in for "the writer is alive" is a proxy, which
is exactly what directive 1 forbids — and it is the direction of proxy that
costs the most, because the confident answer is the wrong one.

------------------------------------------------------------------------------
THE TWO SIGNALS, AND WHY THERE MUST BE TWO
------------------------------------------------------------------------------

**SIGNAL 1 — the peer disconnect (`peer`).** A `zmq.SUB` socket's *monitor*
socket (`Socket.get_monitor_socket()` +
`zmq.utils.monitor.recv_monitor_message`) delivers libzmq's own connection
events up to the application. When an `ipc://` publisher's process dies, the
kernel closes its end and libzmq raises `EVENT_DISCONNECTED`.

MEASURED on this node, pyzmq 27.1.0 / libzmq 4.3.5, against real
`scripts/nixscore/process.py` children killed with `SIGKILL`, seven runs:
`EVENT_DISCONNECTED` arrived **1.417 / 1.543 / 2.136 ms** (min / median / max)
after the signal. The figure is quoted with what is IN the path, because the
first spelling of this measurement read 3.27 ms and the difference was
`Popen.wait()` reaping the child before the poll loop started — a number that
described the harness, not the transport. End to end, from `SIGKILL` to the
first FCFS verdict a consumer actually takes, `check_mirror_liveness` measures
**3.44 ms**, and that one legitimately includes the reap and the arbitration
loop's own cadence.

That is an *observation of the writer*, not a timeout, so the
RANKED-from-a-corpse window collapses to disconnect-detection latency instead of
scaling linearly with `stale_after_s`.

**SIGNAL 2 — the sequence/heartbeat deadline (`heartbeat`).** A publisher that
is ALIVE but WEDGED — blocked, spinning, stopped publishing — never disconnects,
so signal 1 is blind to it by construction. §12.7 already puts a monotonically
increasing `_seq` on every update, so the second signal needs no new wire field:
the deadline is on the **advance of the sequence**, not on the arrival of bytes,
because a publisher re-sending an identical table is still publishing and a
publisher whose `_seq` has stopped moving is not.

Two signals, two failure modes, and the verdict SAYS WHICH ONE FIRED — check
contract §18: *every can-fail control asserts the REASON*, and an operator who
is told only "not live" cannot tell a dead process from a wedged one, which are
different incidents with different runbooks.

The heartbeat deadline defaults to `None` (disabled) and that is a decision, not
an oversight: it must be set from the publisher's KNOWN publish cadence, and a
consumer cannot know that cadence. A guessed default would either be too tight
(FCFS on a loaded box, with no outage at all) or too loose to mean anything.
`docs/CHECK-DEBT.md` D3.313 carries the missing physical config home, which is
the same home D3.244 asks for `stale_after_s`.

------------------------------------------------------------------------------
§0a — WHAT WOULD HAVE TO BE TRUE FOR THIS MODULE TO BE PRESENT AND USELESS
------------------------------------------------------------------------------

1. **It never observes a real death.** The instrument is
   `checks/check_mirror_liveness.py`, which SIGKILLs a real
   `scripts/nixscore/process.py` child and counts RANKED verdicts taken AFTER
   the reaped `-SIGKILL`.
2. **It answers "not live" always**, which turns §6.6's degraded mode into the
   only mode and is a worse outcome than the defect it repairs. Closed by the
   NON-VACUITY arm: a healthy publisher must produce RANKED verdicts and a live
   verdict, or the gate reddens.
3. **It halts order flow.** It structurally cannot: nothing here is called from
   an arbitration path. `RankingMirror.arbitrate` reads a **plain boolean
   attribute** that this module FED it from the consumer's pump loop; there is
   no call, no socket and no `try` on the order path, which is also what keeps
   `checks/check_scoring_seam.py`'s stalling-node scan satisfied.
4. **An observer that raises takes order flow with it.** Closed at the feeder:
   `nixscore.process.RankingReader.pump` catches anything out of `observe()`
   and feeds the mirror `live=False` with the exception named. FAIL CLOSED to
   **FCFS**, which is a decision, never a refusal — §6.6:467.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO
------------------------------------------------------------------------------

It does not decide anything. It reports two facts about a socket and lets the
seam turn them into an FCFS reason. It holds no table, no score, no policy and
no threshold beyond the one deadline it is handed.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Protocol

# pylint: disable=import-error
# `pyzmq` is a `checks/pinned_deps.json` pin installed in `.venv`; pylint runs
# from its own isolated pre-commit environment, which has no venv packages and
# so cannot resolve it statically. Same per-line disable `nixbus.statebus` uses.
import zmq
from zmq.utils.monitor import recv_monitor_message

#: The two signals, named. An operator's runbook keys on WHICH one fired: a
#: `peer` verdict is a process that is gone and a `heartbeat` verdict is a
#: process that is present and not working. Different incidents.
SIGNAL_PEER = "peer"
SIGNAL_HEARTBEAT = "heartbeat"
SIGNAL_OBSERVER = "observer"

#: libzmq events that PROVE a peer is attached. `HANDSHAKE_SUCCEEDED` is
#: included because it is the last event of a successful attach and a monitor
#: registered mid-connect can see it without having seen `CONNECTED`.
_ALIVE_EVENTS = frozenset(
    {
        int(zmq.EVENT_CONNECTED),
        int(zmq.EVENT_HANDSHAKE_SUCCEEDED),
    }
)

#: libzmq events that prove there is NO peer attached right now. MEASURED on
#: this node across a SIGKILL and a relaunch, in delivery order:
#: `DISCONNECTED, CONNECT_RETRIED, CLOSED, CONNECT_RETRIED, …` then on the
#: relaunch `CLOSED, CONNECT_RETRIED, CONNECTED, HANDSHAKE_SUCCEEDED`. The
#: retry/closed pair is the SUB socket cycling its own connect attempt, which is
#: only ever true while nothing is attached — so it corroborates the latch and
#: never contradicts it, and the last event in a drain wins.
_DEAD_EVENTS = frozenset(
    {
        int(zmq.EVENT_DISCONNECTED),
        int(zmq.EVENT_CONNECT_RETRIED),
        int(zmq.EVENT_CONNECT_DELAYED),
        int(zmq.EVENT_CLOSED),
        int(zmq.EVENT_MONITOR_STOPPED),
    }
)


class LivenessObserver(Protocol):
    """What `nixscore.process.RankingReader` requires of a liveness observer.

    Declared so the reader's seam is a CONTRACT rather than a concrete class: a
    gate that needs an observer which raises on every call — and
    `checks/check_mirror_liveness.py`'s ARM RAISE needs exactly that — must be
    able to supply one without subclassing the thing under measurement.

    Five verbs and no more. `verdict` is the only one a consumer reads, and it
    is the only one that must never raise.
    """

    def note_message(self, seq: int = -1) -> None:
        """Record one received update, with its §12.7 sequence."""

    def observe(self) -> int:
        """Drain the transport's own connection events. May raise; the reader catches."""

    def note_observe_error(self, exc: BaseException) -> None:
        """Record that `observe` raised. Latches NOT LIVE."""

    def verdict(self, now: float | None = None) -> LivenessVerdict:
        """The two signals, resolved. Never raises, never blocks, never denies."""

    def close(self) -> None:
        """Release the monitor. Must run BEFORE the subscriber closes."""


class LivenessError(RuntimeError):
    """The observer could not be built or torn down. **Never raised on a read.**"""


@dataclasses.dataclass(frozen=True, slots=True)
class LivenessVerdict:
    """Whether the WRITER is alive, by which signal, and why (§18).

    `live` is the only field a hot path would ever branch on, and no hot path
    reads this object at all — the seam is fed a boolean. The other two fields
    exist so the FCFS reason can name the failure mode instead of asserting the
    outcome.
    """

    live: bool
    signal: str
    reason: str


def _event_name(code: int) -> str:
    """libzmq's own name for an event code, or the number. Never raises."""
    try:
        return zmq.Event(code).name
    except ValueError:  # pragma: no cover - unknown event codes are diagnostics
        return f"event {code}"


class PublisherLiveness:  # pylint: disable=too-many-instance-attributes
    """Observes a `StateSubscriber`'s socket and answers: is the WRITER alive?

    Constructed with the subscriber, drained from the consumer's pump loop,
    never touched from an order path.

    ## Stale-until-proven-live, with one deliberate exception

    `_peer` starts `None` — *never observed* — and a never-observed peer is
    **not** reported dead, because the observer has made no observation and
    §17's rule is that an unmeasured subject is not a measured failure. The
    exception is the first RECEIVED MESSAGE: a message off the socket is direct
    evidence that a peer was attached, so `note_message` promotes `None` to
    live. It **cannot** clear a latched `False`, which is the whole point —
    messages already buffered when the publisher died must not resurrect it.

    Counters, not flags (the reasoning `StatePublisher`'s four are built on): an
    observer that cannot say how many events it saw can only be believed.
    """

    def __init__(
        self,
        subscriber: Any,
        *,
        heartbeat_deadline_s: float | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        if heartbeat_deadline_s is not None and heartbeat_deadline_s <= 0:
            raise LivenessError(
                f"heartbeat_deadline_s={heartbeat_deadline_s!r}: a non-positive "
                "deadline reports every publisher wedged the instant it is "
                "observed, which turns §6.6's degraded mode into the only mode"
            )
        self._clock = clock
        self.heartbeat_deadline_s = heartbeat_deadline_s
        try:
            socket = subscriber.socket
        except AttributeError as exc:
            raise LivenessError(
                f"{type(subscriber).__name__} exposes no `socket`: the peer-disconnect "
                "signal can only be asked of the zmq socket itself, and an observer "
                "that cannot reach one would report liveness it never measured"
            ) from exc
        self._socket = socket
        try:
            self._monitor = socket.get_monitor_socket()
        except (zmq.ZMQError, AttributeError) as exc:
            raise LivenessError(
                f"cannot attach a monitor socket to {socket!r}: {exc!r}"
            ) from exc
        #: `None` = never observed; `True`/`False` = latched by an event.
        self._peer: bool | None = None
        self._last_event: str = ""
        self._last_event_at: float | None = None
        self._last_seq: int = -1
        self._last_seq_advance_at: float | None = None
        self._error: str = ""
        #: COUNTERS.
        self.events_seen = 0
        self.disconnects = 0
        self.connects = 0
        self.messages_noted = 0
        self.observe_errors = 0

    # -- ingress: called from the consumer's pump loop, never an order path --

    def note_message(self, seq: int = -1) -> None:
        """Record one received update. Direct evidence a peer WAS attached.

        Feed this BEFORE draining the monitor in the same pass: the monitor's
        latch is authoritative and must have the last word, so a disconnect
        event cannot be undone by bytes that were buffered before the death.
        """
        self.messages_noted += 1
        if self._peer is None:
            self._peer = True
            self._last_event = "message-received"
            self._last_event_at = self._clock()
        if int(seq) > self._last_seq:
            self._last_seq = int(seq)
            self._last_seq_advance_at = self._clock()

    def observe(self) -> int:
        """Drain every pending monitor event. Returns how many were read.

        The LAST event in the drain wins, which is what makes a kill-then-
        relaunch cycle (`DISCONNECTED … CONNECTED, HANDSHAKE_SUCCEEDED`) end
        live without special-casing the sequence.

        Raises only what libzmq raises. The caller — `RankingReader.pump` — is
        what turns that into a `live=False` verdict rather than an exception on
        the consumer's loop; see §0a case 4 in the module docstring.
        """
        read = 0
        while self._monitor.poll(0, zmq.POLLIN):
            message = recv_monitor_message(self._monitor)
            code = int(message["event"])
            read += 1
            self.events_seen += 1
            if code in _ALIVE_EVENTS:
                self._peer = True
                self.connects += 1
            elif code in _DEAD_EVENTS:
                if code == int(zmq.EVENT_DISCONNECTED):
                    self.disconnects += 1
                self._peer = False
            else:
                continue
            self._last_event = _event_name(code)
            self._last_event_at = self._clock()
        return read

    def note_observe_error(self, exc: BaseException) -> None:
        """Record that `observe` raised. **Latches NOT LIVE, loudly.**

        Directive 4, fail closed: an observer that cannot see the writer has not
        seen a live writer. Closing to FCFS is a decision and never a refusal,
        so §6.6:467 is intact — the order path keeps answering, it just stops
        believing a table nothing is watching.
        """
        self.observe_errors += 1
        self._error = f"{type(exc).__name__}: {exc}"

    # -- read contract: pure, O(1), no I/O, and it never raises -------------

    @property
    def peer_observed(self) -> bool | None:
        """`True`/`False` once latched by an event, `None` if never observed."""
        return self._peer

    @property
    def last_event(self) -> str:
        """libzmq's name for the last event that moved the latch."""
        return self._last_event

    def seq_age_s(self, now: float | None = None) -> float | None:
        """Seconds since `_seq` last ADVANCED, or `None` if it never has."""
        if self._last_seq_advance_at is None:
            return None
        return max(
            0.0, (self._clock() if now is None else now) - self._last_seq_advance_at
        )

    def verdict(self, now: float | None = None) -> LivenessVerdict:
        """The two signals, resolved. **Never raises, never blocks, never denies.**

        Order is deliberate: the observer's own failure first (it invalidates
        both signals), then the peer (a dead process is not also wedged), then
        the heartbeat.
        """
        if self._error:
            return LivenessVerdict(
                False,
                SIGNAL_OBSERVER,
                (
                    f"the liveness observer raised {self._error} and can no longer "
                    "see the writer; §6.6:467 makes the degraded answer FCFS, never "
                    "a refusal"
                ),
            )
        if self._peer is False:
            # NEVER-ATTACHED IS NOT GONE. MEASURED, ARC 037: a subscriber
            # connected before any publisher binds latches `_peer = False` off
            # `CONNECT_DELAYED`/`CONNECT_RETRIED`, and the first spelling of
            # this reason said the peer was "GONE … after 0 disconnect(s)" — a
            # reason that contradicts its own count in its own sentence, which
            # is `docs/CHECK-DEBT.md` D3.250's shape exactly. The VERDICT is
            # identical either way (FCFS, and correctly so on a cold start);
            # what differs is what an operator is told, and §18 makes the reason
            # the assertable artifact.
            never = self.connects == 0 and self.disconnects == 0
            return LivenessVerdict(
                False,
                SIGNAL_PEER,
                (
                    (
                        "the Scoring publisher has NEVER been attached — libzmq "
                        f"{self.last_event or 'CONNECT_DELAYED'} on the subscriber "
                        "socket, 0 connect(s) and 0 disconnect(s). Cold start: "
                        "there is no writer to be down, and §6.6 makes an absent "
                        "table FCFS"
                    )
                    if never
                    else (
                        f"the Scoring publisher's peer is GONE — libzmq "
                        f"{self.last_event or 'DISCONNECTED'} on the subscriber "
                        f"socket after {self.disconnects} disconnect(s). This is an "
                        "observation of the WRITER, not the table's age: §6.6:465 "
                        "makes a down Scoring process FCFS immediately"
                    )
                ),
            )
        age = self.seq_age_s(now)
        deadline = self.heartbeat_deadline_s
        if deadline is not None and age is not None and age > deadline:
            return LivenessVerdict(
                False,
                SIGNAL_HEARTBEAT,
                (
                    f"the Scoring publisher is CONNECTED but WEDGED: §12.7 sequence "
                    f"{self._last_seq} has not advanced for {age:.3f}s against a "
                    f"{deadline:.3f}s deadline. A live-but-stopped writer never "
                    "disconnects, so the peer signal cannot see this one"
                ),
            )
        if self._peer is None:
            return LivenessVerdict(
                True,
                SIGNAL_PEER,
                "no liveness observation has been made yet; §17 makes an unmeasured "
                "subject unmeasured, never a measured failure",
            )
        return LivenessVerdict(
            True,
            SIGNAL_PEER,
            (
                f"the Scoring publisher's peer is attached (libzmq "
                f"{self.last_event or 'CONNECTED'}), {self.messages_noted} update(s) "
                f"seen, §12.7 sequence at {self._last_seq}"
            ),
        )

    # -- lifetime ----------------------------------------------------------

    def close(self) -> None:
        """Detach the monitor. **Must run BEFORE the subscriber closes.**

        MEASURED on this node (pyzmq 27.1.0 / libzmq 4.3.5): a monitor socket
        left open makes the subscriber's `Context.term()` block **forever**, and
        `Socket.disable_monitor()` alone does not prevent it — it sets pyzmq's
        reference to `None` and calls `monitor(None, 0)` without ever closing
        the PAIR socket, so the socket leaks and the hang is identical. Closing
        with `linger=0` first and disabling second is the order that was
        measured to terminate. Idempotent.
        """
        monitor = self._monitor
        if monitor is None:
            return
        self._monitor = None
        try:
            monitor.close(linger=0)
            self._socket.disable_monitor()
        except (zmq.ZMQError, AttributeError, RuntimeError) as exc:
            raise LivenessError(f"cannot detach the monitor socket: {exc!r}") from exc
