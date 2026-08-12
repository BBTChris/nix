#!/usr/bin/env python3
# pylint: disable=too-many-lines
#   The file is ~1000 lines and roughly a third of them are the reasoning above
#   the code: WHY the kill is randomised, WHY the two channels carry different
#   thresholds, WHY the clean-exit control exists, and exactly WHAT the Plane-2
#   comparison can and cannot bound. That reasoning is the deliverable — a drill
#   whose evidence a reader cannot audit is the vacuity this item exists to
#   catch — and deleting it to satisfy a line count would remove the only thing
#   standing between a green drill and a green drill that measured nothing.
#   Splitting the producer from the observer would be worse: they must agree on
#   the wire shape, the topic and the per-channel thresholds, and two copies of
#   that agreement drift. Same pragma, same kind of reason, as
#   `scripts/broker/broker_seam.py` line 45.
"""`feed_kill_drill.py` — kill the datafeed under load and MEASURE what happens.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §13 objective **V24**
(*"broker-order / broker-datafeed run in separate processes on separate cores;
kill/reconnect the datafeed under load and prove the order path is undisturbed
(latency + zero missed exits)"*), §12.7 (state-table transport + the price-firehose
exception), §12.10 (two-plane logging), §10 (Process/Core Map, locked).
`docs/SPEC-AMENDMENTS.md` AMENDMENT 6 (freshness is per-channel).

------------------------------------------------------------------------------
WHAT THIS DRILL DOES **NOT** DISCHARGE, STATED FIRST
------------------------------------------------------------------------------

**V24's definition of success is a statement about the ORDER PATH**, and this
node has no order path: §10 gives the Risk Engine (Limiter + broker-order) Core 2
and `nixbus.core_map.Role.RISK_ENGINE` carries *"Not built yet."* There is no
process to be undisturbed, no exit to be missed, and no latency to measure. A
drill that reported V24 green would be reporting on the half of the objective it
can see.

So this file discharges the **datafeed half** of V24 — *kill/reconnect the
datafeed under load* — and nothing else. `docs/CHECK-DEBT.md` D1.47 carries the
order-path half. Read `check_feed_kill_drill.py`'s verdict the same way.

Two further bounds, both measured rather than assumed:

* **There is no venue.** IB Gateway is down on this node, so the `venue_ts` this
  drill carries is stamped by the producer's own `CLOCK_REALTIME`, not by a
  venue. That makes the freshness arithmetic exact (one clock, one machine) and
  makes it a SIMULATION of the venue-clock relationship, not a measurement of it.
  What is real: the process, the kill, the two transports, the per-channel
  transition machinery, and the journal.
* **Load is synthetic.** The rate is whatever this box sustains through
  `nixbus.price_ring`, and it is REPORTED AS MEASURED DOWNSTREAM — counted by the
  reader out of the ring, never read back from the producer's own claim.

------------------------------------------------------------------------------
THE THREE WAYS A KILL DRILL PASSES WHILE MEASURING NOTHING (debug.md §7.12)
------------------------------------------------------------------------------

1. **The feed was never under load.** *Closed:* every trial reports
   `observed_tick_rate_hz`, computed by `PriceRingReader` from ticks it actually
   drained out of shared memory over a measured interval. A trial below
   `MIN_CREDIBLE_RATE_HZ` is refused, not reported.
2. **The process was never actually killed.** *Closed:* the drill records the PID
   it spawned, the signal number it sent, and the **reaped wait status**. A
   `returncode` of `-9` is the kernel's account of the death; the drill's own
   intention is not evidence of it.
3. **Detection fires on a timer and merely FOLLOWS the kill in time.** This is
   the one a control arm alone does not close, and it is the reason this file is
   larger than a control arm would need.

   *Closed by RANDOMISING THE KILL and measuring which clock detection tracks.*
   Each trial kills at an offset drawn from its OWN STRATUM of
   `[KILL_MIN_S, KILL_MAX_S]` — the window is cut into `trials` equal bands and
   one offset is drawn uniformly inside each. **Stratified rather than i.i.d.,
   and the reason is measured:** three i.i.d. draws from a 0.9 s window produce a
   sample stdev below `MIN_JITTER_S` a few percent of the time, so the drill
   refused itself on a run of the real gate (`kill offsets varied by only
   0.0262s`). A refusal that arrives at random is a coin toss wearing an
   instrument's name. Stratification puts a floor under the spread while leaving
   every individual offset unpredictable, so the discriminator's POWER becomes a
   property of the design instead of a property of the draw.
   For a detector driven by the DEATH, `detect - kill` is tight and
   `detect - start` inherits the full jitter of the kill offset. For a detector
   driven by a TIMER, exactly the reverse. The two hypotheses therefore predict
   opposite orderings of two standard deviations, and the drill reports both.

   The discriminator has power only if the kill offsets actually varied, so
   `stdev(kill_offset) < MIN_JITTER_S` is a refusal rather than a pass — an
   instrument with no spread cannot tell the two hypotheses apart and must not
   be allowed to report that it did.

   *Also closed by a CONTROL arm* that runs at least as long as the longest
   trial, never kills, and must produce zero staleness transitions.

4. **All channels flip together, which one collapsed timer would also produce.**
   *Closed twice.* (a) Under the kill, the TICK and POLL channels carry DIFFERENT
   thresholds and are required to transition at measurably different times, each
   tracking its own. (b) The `starve` arm freezes ONE channel's venue clock with
   nothing killed at all: only that channel may transition, and a collapsed
   verdict cannot produce a one-channel move.

------------------------------------------------------------------------------
PLANE 2 ACROSS THE KILL — WHAT SURVIVES AND WHAT IS LOST (§12.10)
------------------------------------------------------------------------------

`nixverify.plane2` writes each event as one `sendto` on the `/dev/log` datagram
socket, with no userspace buffer between the call and the kernel. So a record
whose `emit()` returned has already left the process, and SIGKILL cannot recall
it. That is the survival claim and it is checkable: every heartbeat carries a
`seq`, the SAME `seq` goes out on the state bus, and the journal must hold every
seq the bus delivered.

**What is lost, stated because it is the deliverable and not a caveat:**

* `capture.py`'s `process_stop` event **never happens**. `CaptureProcess.close()`
  emits it, SIGKILL runs no code, and there is no handler that could — nor could
  there be one for SIGKILL. An operator reading Plane 2 alone therefore cannot
  distinguish *killed* from *hung but alive* from *idle*: the stream simply
  stops. (SIGTERM is equally silent TODAY for a different reason — `capture.py`
  installs no handler — and that one IS fixable. `docs/CHECK-DEBT.md` D1.48.)
* Anything the process would have emitted after its last successful `sendto` is
  lost with no record that it existed. The drill can bound this from below (the
  bus tells it what the producer definitely reached) and **cannot bound it from
  above**, and does not pretend to.
* The producer's own `Plane2.failed` counter dies with the producer. If `/dev/log`
  had rejected a datagram in the final instants, nothing outside the process
  knows. Also unbounded, also stated.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import secrets
import signal
import statistics
import subprocess  # nosec B404 - re-executes THIS file, argv built here, no shell
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
for _extra in (str(_HERE), str(_HERE / "broker")):
    if _extra not in sys.path:
        sys.path.append(_extra)

# pylint: disable=wrong-import-position
import capture
from broker_seam import (
    ChannelFreshness,
    ChannelState,
    FeedChannel,
    FeedLag,
    FreshnessReport,
    LagProvenance,
    MarketDataMode,
)
from nixbus import price_ring, statebus
from nixverify.plane2 import Plane2
from nixverify.plane2 import read_back as plane2_read_back

#: The heartbeat table. The producer OWNS it, publishes it every beat, and it is
#: what carries each channel's venue clock outward — a consumer computes
#: freshness from this and from nothing the producer asserts about itself.
TOPIC_HEARTBEAT = "tbl.drill_heartbeat"

#: Per-channel staleness budgets, DELIBERATELY UNEQUAL and deliberately far
#: apart. Equal thresholds would make simultaneous transitions the correct
#: behaviour, and the drill would lose its ability to tell a per-channel detector
#: from one collapsed timer — the very property AMENDMENT 6 is about.
THRESHOLD_S: dict[FeedChannel, float] = {
    FeedChannel.TICK: 0.20,
    FeedChannel.POLL: 0.90,
}

#: Ticks pushed into the ring per producer iteration. A burst rather than one per
#: loop so the rate is set by memory bandwidth and not by the loop's own
#: bookkeeping — the point is real load, not a paced metronome.
TICK_BURST = 256

#: Beats per second of the per-channel freshness observation. Not the tick rate:
#: §12.10 rejects per-tick chatter and `capture.py` publishes on TRANSITION only.
BEAT_HZ = 50.0

#: A trial below this observed rate was not "under load" and is refused.
MIN_CREDIBLE_RATE_HZ = 1000.0

#: Kill-offset window, seconds after the producer's first heartbeat.
KILL_MIN_S = 0.35
KILL_MAX_S = 1.25

#: Below this spread the randomised-kill discriminator has no power. Refusal,
#: never a pass. Set below the window's own stdev (uniform over 0.9 s is ~0.26)
#: with room for a short run, and above the scheduler noise a fixed schedule
#: would produce.
MIN_JITTER_S = 0.08

#: How much tighter `stdev(detect - kill)` must be than `stdev(detect - start)`
#: for detection to be attributed to the death. A ratio, not a latency budget:
#: the absolute latency is a property of the thresholds and is reported beside
#: it, but the ATTRIBUTION is about which clock the detector follows.
ATTRIBUTION_RATIO = 3.0

#: How long to wait for journald to catch up before declaring a record lost.
#: A readback that raced the journal would report a LOSS that was only a DELAY,
#: on the one property this drill exists to report honestly.
JOURNAL_TIMEOUT_S = 8.0

#: Observer loop budget per pass, milliseconds. Bounds detection resolution:
#: nothing here can attribute a death more finely than this, and the drill says
#: so in its own output rather than implying a precision it does not have.
OBSERVE_POLL_MS = 5

_SYMBOL = "DRILL"
_SYMBOL_ID = 1


# ---------------------------------------------------------------------------
# The per-channel report — built by BOTH sides from the seam's own types
# ---------------------------------------------------------------------------


def _lag() -> FeedLag:
    """A zero declared lag, provenance stated. There is no venue to observe.

    `VENDOR_DECLARED` with `0.0` is the honest label for a synthetic producer
    stamping its own clock: a real number with no venue measurement behind it.
    `UNOBSERVED` would force `declared_lag_s=None`, which makes every
    `excess_staleness_s` `None` and every channel CANNOT_MEASURE — a drill in
    which nothing can ever go stale.
    """
    return FeedLag(
        declared_lag_s=0.0,
        observed_lag_s=None,
        observed_n=0,
        provenance=LagProvenance.VENDOR_DECLARED,
        granted_mode=MarketDataMode.DELAYED,
    )


def _channel(
    channel: FeedChannel, venue_ts: float | None, now: float
) -> ChannelFreshness:
    """One channel's reading. `ChannelFreshness` refuses a contradicting verdict."""
    lag = _lag()
    excess = lag.excess_staleness_s(venue_ts, now)
    threshold = THRESHOLD_S[channel]
    if excess is None:
        state = ChannelState.CANNOT_MEASURE
    else:
        state = ChannelState.FRESH if excess <= threshold else ChannelState.STALE
    return ChannelFreshness(
        channel=channel,
        venue_ts=venue_ts,
        lag=lag,
        excess_staleness_s=excess,
        threshold_s=threshold,
        state=state,
        recv_ts=now,
    )


def report_for(clocks: dict[str, float | None], now: float) -> FreshnessReport:
    """Build the uncollapsed per-channel report from each channel's venue clock."""
    return FreshnessReport(
        symbol=_SYMBOL,
        now=now,
        channels=tuple(
            _channel(channel, clocks.get(channel.value), now) for channel in THRESHOLD_S
        ),
    )


# ---------------------------------------------------------------------------
# PRODUCER — the process that gets killed
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _ProducerArgs:
    """Everything the child needs. A dataclass so `main` stays flat."""

    endpoint: str
    ring: str
    nonce: str
    duration_s: float
    starve: str
    pin: bool


def _producer_clocks(args: _ProducerArgs, now: float, frozen: dict[str, float]) -> dict:
    """Each channel's venue clock this beat; a starved channel keeps its old one."""
    clocks: dict[str, float | None] = {}
    for channel in THRESHOLD_S:
        if channel.value == args.starve:
            clocks[channel.value] = frozen.setdefault(channel.value, now)
        else:
            clocks[channel.value] = now
    return clocks


def _produce(args: _ProducerArgs) -> int:  # pylint: disable=too-many-locals
    """Run a real `CaptureProcess` under real load until told otherwise.

    Prints ONE JSON line — pid, endpoint, ring, cores — and then holds. That line
    is the whole contract with the parent: the parent must know WHICH pid it is
    about to kill, and it must learn it from the child rather than from a scan.
    """
    plane2 = Plane2(identifier=capture.IDENTIFIER, process=capture.PROCESS)
    publisher = statebus.StatePublisher(args.endpoint)
    ring = price_ring.PriceRingWriter(args.ring, capacity=4096)
    process = capture.CaptureProcess(
        plane2=plane2, publisher=publisher, ring=ring, pin=args.pin
    )
    reading = process.start()
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "endpoint": args.endpoint,
                "ring": args.ring,
                "nonce": args.nonce,
                "cores": sorted(reading.mask),
                "plane2_available": plane2.available,
                "plane2_transport": plane2.transport,
            }
        ),
        flush=True,
    )
    deadline = time.monotonic() + args.duration_s
    interval = 1.0 / BEAT_HZ
    next_beat = time.monotonic()
    frozen: dict[str, float] = {}
    seq = 0
    while time.monotonic() < deadline:
        for _ in range(TICK_BURST):
            process.on_tick(_SYMBOL_ID, 1.0, 1.0, time.time_ns())
        publisher.service(0)
        if time.monotonic() < next_beat:
            continue
        next_beat += interval
        seq += 1
        now = time.time()
        clocks = _producer_clocks(args, now, frozen)
        process.observe_freshness(report_for(clocks, now))
        publisher.publish(
            TOPIC_HEARTBEAT,
            {"seq": seq, "ring_seq": ring.write_seq, "nonce": args.nonce, **clocks},
        )
        plane2.emit(
            "drill_heartbeat", nonce=args.nonce, seq=seq, ring_seq=ring.write_seq
        )
    process.close()
    return 0


# ---------------------------------------------------------------------------
# OBSERVER — a separate process's view, and the only source of every verdict
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Observation:  # pylint: disable=too-many-instance-attributes
    """What one trial's observer saw. Every field is measured, none configured.

    Eleven fields, and the count is the design rather than an oversight: the two
    rate properties are each computed from THREE independently recorded
    quantities (a sequence pair, a monotonic pair, and a drained count), and the
    per-channel detection and recovery instants are separate maps because a
    channel that went stale and a channel that came back are different events.
    Nesting them to satisfy a field counter would put the inputs of a reported
    figure one indirection away from it — the shape `ChannelFreshness` refuses
    inside the seam."""

    detected: dict[str, float] = dataclasses.field(default_factory=dict)
    transitions: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    ticks: int = 0
    dropped: int = 0
    first_tick_mono: float = 0.0
    last_tick_mono: float = 0.0
    first_seq: int = -1
    last_seq: int = -1
    bus_max_seq: int = 0
    ring_seq_at_last_beat: int = 0
    recovered: dict[str, float] = dataclasses.field(default_factory=dict)

    @property
    def observed_rate_hz(self) -> float:
        """THE LOAD FIGURE. Ticks per second the PRODUCER wrote, measured HERE.

        Derived from `PriceRingReader.read_seq` — the ring's own sequence numbers,
        read out of shared memory by a different process. It counts every tick the
        producer published, including the ones this reader was too slow to drain
        (the ring overwrites, and `poll()` hands back the gap rather than hiding
        it). No number the producer asserted about itself is an input.

        `drained_rate_hz` is the different and lesser fact — how fast this
        particular consumer kept up — and the two are reported separately because
        conflating them would let a slow reader understate the load it was proving.
        """
        span = self.last_tick_mono - self.first_tick_mono
        moved = self.last_seq - self.first_seq
        return moved / span if span > 0 and moved > 0 else 0.0

    @property
    def drained_rate_hz(self) -> float:
        """Ticks per second this consumer actually took delivery of."""
        span = self.last_tick_mono - self.first_tick_mono
        return self.ticks / span if span > 0 and self.ticks else 0.0


class _Observer:
    """Subscriber + ring reader + the per-channel monitor, in the parent.

    Deliberately in the PARENT's process and the PARENT's clock: the kill time
    and the detection time are compared to a resolution of milliseconds, and two
    processes' `time.monotonic()` are two different epochs. Everything the
    observer measures is still measured across a process boundary — the subject
    is the producer, which is a different process by construction.
    """

    def __init__(self, endpoint: str, ring: str) -> None:
        self.subscriber = statebus.StateSubscriber(
            endpoint, topics=("tbl.",), required=(TOPIC_HEARTBEAT,)
        )
        self.reader = price_ring.PriceRingReader(ring)
        self.monitor = capture.FeedStalenessMonitor()
        self.clocks: dict[str, float | None] = {}
        self.out = _Observation()

    def _absorb_bus(self) -> None:
        for message in self.subscriber.drain(OBSERVE_POLL_MS):
            if message.topic != TOPIC_HEARTBEAT:
                continue
            payload = message.payload
            self.out.bus_max_seq = max(self.out.bus_max_seq, int(payload.get("seq", 0)))
            self.out.ring_seq_at_last_beat = int(payload.get("ring_seq", 0))
            for channel in THRESHOLD_S:
                value = payload.get(channel.value)
                if value is not None:
                    self.clocks[channel.value] = float(value)

    def _absorb_ring(self, mono: float) -> None:
        ticks, dropped = self.reader.poll()
        self.out.dropped += dropped
        if not ticks and not dropped:
            return
        if self.out.first_seq < 0:
            self.out.first_seq = self.reader.read_seq - len(ticks) - dropped
            self.out.first_tick_mono = mono
        self.out.ticks += len(ticks)
        self.out.last_seq = self.reader.read_seq
        self.out.last_tick_mono = mono

    def _fold(self, mono: float) -> None:
        """Compute freshness HERE, from the clocks the producer last published."""
        for moved in self.monitor.observe(report_for(self.clocks, time.time())):
            record = {
                "channel": moved.channel.value,
                "from": moved.previous,
                "to": moved.current.value,
                "at_mono": mono,
                "excess_staleness_s": moved.excess_staleness_s,
                "threshold_s": moved.threshold_s,
            }
            self.out.transitions.append(record)
            if moved.current is ChannelState.STALE:
                self.out.detected.setdefault(moved.channel.value, mono)
            elif moved.previous == ChannelState.STALE.value:
                self.out.recovered.setdefault(moved.channel.value, mono)

    def step(self) -> None:
        """One observation pass. Bus, then ring, then the per-channel verdict."""
        mono = time.monotonic()
        self._absorb_bus()
        self._absorb_ring(mono)
        self._fold(mono)

    def close(self) -> None:
        """Release both transports. The reader never unlinks; it does not own it."""
        self.subscriber.close()
        self.reader.close()


# ---------------------------------------------------------------------------
# TRIALS
# ---------------------------------------------------------------------------


def _drop_endpoint(endpoint: str) -> None:
    """Unlink an `ipc://` socket file by ABSOLUTE path, before the tmpdir goes.

    MEASURED, and this is the reason it exists rather than leaving it to the
    temporary directory: `TemporaryDirectory`'s cleanup walks with a directory
    file descriptor and so raises the `os.remove` audit event with a RELATIVE
    name (`d0.ipc`). `check_observed_resource_claims` resolves a relative claim
    against the observer's own cwd, so the claim lands under the repository and
    no `file-write:/tmp` declaration can honestly cover it. Removing the socket
    here means the claim carries the absolute path it actually refers to — a
    declaration should be true, not merely accepted.
    """
    if not endpoint.startswith("ipc://"):
        return
    try:
        Path(endpoint[len("ipc://") :]).unlink(missing_ok=True)
    except OSError:
        pass


def _spawn(args: _ProducerArgs) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    """Start the producer and read its self-announcement. Raises on either half."""
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--produce",
        "--endpoint",
        args.endpoint,
        "--ring",
        args.ring,
        "--nonce",
        args.nonce,
        "--duration-s",
        str(args.duration_s),
        "--starve",
        args.starve,
    ]
    if not args.pin:
        argv.append("--no-pin")
    # pylint: disable=consider-using-with
    # The child's lifetime is longer than this call by design: the whole drill
    # happens while it runs, and `_trial` owns the kill and the reap on every
    # path, including the paths where the drill fails.
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=20)
        stderr = (proc.stderr.read() if proc.stderr else "")[:400]
        raise RuntimeError(f"producer printed no announcement; stderr={stderr!r}")
    return proc, json.loads(line)


def _reap(proc: subprocess.Popen[str]) -> int:
    """Wait for the child and return the KERNEL's wait status. Never the drill's."""
    try:
        return proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait(timeout=20)


def _observe_until(observer: _Observer, until_mono: float) -> None:
    """Pump the observer until `until_mono`. The only way time passes here."""
    while time.monotonic() < until_mono:
        observer.step()


def _trial(  # pylint: disable=too-many-locals
    root: Path, nonce: str, index: int, *, kill_offset: float, pin: bool
) -> dict[str, Any]:
    """One randomised kill. Returns the trial's whole evidence record."""
    arm_nonce = f"{nonce}t{index}"
    args = _ProducerArgs(
        endpoint=statebus.endpoint_for(f"d{index}", root),
        ring=f"nix_drill_{nonce}_{index}",
        nonce=arm_nonce,
        duration_s=kill_offset + 6.0,
        starve="",
        pin=pin,
    )
    proc, hello = _spawn(args)
    observer = _Observer(args.endpoint, args.ring)
    record: dict[str, Any] = {
        "trial": index,
        "hello": hello,
        "arm_nonce": arm_nonce,
        "kill_offset_s": kill_offset,
    }
    try:
        start_mono = time.monotonic()
        _observe_until(observer, start_mono + kill_offset)
        kill_mono = time.monotonic()
        os.kill(proc.pid, signal.SIGKILL)
        status = _reap(proc)
        reap_mono = time.monotonic()
        _observe_until(observer, kill_mono + max(THRESHOLD_S.values()) + 1.0)
    finally:
        observer.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=20)
        price_ring.unlink_segment(args.ring)
        _drop_endpoint(args.endpoint)
    record.update(
        pid=proc.pid,
        signal="SIGKILL",
        signal_number=int(signal.SIGKILL),
        reap_status=status,
        start_mono=start_mono,
        kill_mono=kill_mono,
        reap_mono=reap_mono,
        reap_latency_s=reap_mono - kill_mono,
        **_evidence(observer.out, start_mono, kill_mono),
    )
    return record


def _evidence(out: _Observation, start_mono: float, kill_mono: float) -> dict[str, Any]:
    """Fold one observation into the flat, quotable evidence shape."""
    return {
        "observed_tick_rate_hz": out.observed_rate_hz,
        "drained_tick_rate_hz": out.drained_rate_hz,
        "ticks_observed": out.ticks,
        "ticks_dropped": out.dropped,
        "ring_seq_span": max(0, out.last_seq - out.first_seq),
        "ring_seq_at_last_beat": out.ring_seq_at_last_beat,
        "bus_max_seq": out.bus_max_seq,
        "transitions": out.transitions,
        "detect_latency_s": {
            channel: at - kill_mono for channel, at in out.detected.items()
        },
        "detect_since_start_s": {
            channel: at - start_mono for channel, at in out.detected.items()
        },
    }


def _hold(  # pylint: disable=too-many-arguments
    root: Path,
    nonce: str,
    *,
    tag: str,
    arm: str,
    starve: str,
    hold_s: float,
    pin: bool,
) -> dict[str, Any]:
    """Run a producer for `hold_s` WITHOUT killing it, and report what was seen.

    Both no-kill arms are this function, and merging them is not tidying: they
    must be identical in every respect except the one variable each isolates, or
    a difference in the harness could masquerade as the effect being measured.

    * `starve=""` is the **CONTROL** — same producer, same load, no kill, run at
      least as long as the longest trial. Any `fresh -> stale` here means the
      detector fires without a death and every trial's red is uninformative.
    * `starve="poll"` is the **INDEPENDENCE** arm — one channel's venue clock
      frozen with the process ALIVE. Exactly that channel may move, which no
      single collapsed timer can produce.
    """
    args = _ProducerArgs(
        endpoint=statebus.endpoint_for(tag, root),
        ring=f"nix_drill_{nonce}_{tag}",
        nonce=f"{nonce}{tag}",
        duration_s=hold_s + 4.0,
        starve=starve,
        pin=pin,
    )
    proc, hello = _spawn(args)
    observer = _Observer(args.endpoint, args.ring)
    try:
        start_mono = time.monotonic()
        _observe_until(observer, start_mono + hold_s)
    finally:
        observer.close()
        proc.kill()
        status = _reap(proc)
        price_ring.unlink_segment(args.ring)
        _drop_endpoint(args.endpoint)
    return {
        "arm": arm,
        "hello": hello,
        "arm_nonce": f"{nonce}{tag}",
        "pid": proc.pid,
        "starved_channel": starve,
        "held_s": hold_s,
        "reap_status": status,
        **_evidence(observer.out, start_mono, start_mono),
    }


def _clean(root: Path, nonce: str, hold_s: float, *, pin: bool) -> dict[str, Any]:
    """CONTROL for the Plane-2 loss claim — a producer that exits NORMALLY.

    Without this arm, *"no `process_stop` reached the journal after the kill"* is
    unfalsifiable: an emitter that never emits `process_stop` at all produces the
    identical evidence, and the drill would be reporting a feature of the code as
    a consequence of the kill. Here the same program, same path, runs to its own
    deadline and calls `CaptureProcess.close()` — so `process_stop` MUST appear,
    and its absence in the killed arms becomes attributable to the killing.
    """
    args = _ProducerArgs(
        endpoint=statebus.endpoint_for("dk", root),
        ring=f"nix_drill_{nonce}_k",
        nonce=f"{nonce}k",
        duration_s=hold_s,
        starve="",
        pin=pin,
    )
    proc, hello = _spawn(args)
    try:
        status = proc.wait(timeout=hold_s + 20.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        status = proc.wait(timeout=20)
    price_ring.unlink_segment(args.ring)
    _drop_endpoint(args.endpoint)
    return {
        "arm": "control-clean-exit",
        "hello": hello,
        "arm_nonce": f"{nonce}k",
        "pid": proc.pid,
        "reap_status": status,
        "bus_max_seq": 0,
        "held_s": hold_s,
    }


# ---------------------------------------------------------------------------
# PLANE 2 ACROSS THE KILL
# ---------------------------------------------------------------------------


def _fields(line: str) -> dict[str, str]:
    """Split a §12.10 one-line event into its `key=value` fields."""
    found: dict[str, str] = {}
    for token in line.split(" "):
        key, sep, value = token.partition("=")
        if sep:
            found.setdefault(key, value)
    return found


def _await_journal(base_nonce: str, want: int) -> tuple[list[str], str]:
    """Poll the journal until this drill's events land, or the budget is spent.

    `want` is the number of heartbeat lines the BUS proved were emitted. Waiting
    for that count rather than for "any line" is what stops the readback from
    racing the journal and reporting a loss that was only a delay — a false
    positive on the one property this function exists to measure honestly.
    """
    deadline = time.monotonic() + JOURNAL_TIMEOUT_S
    lines: list[str] = []
    while True:
        lines, error = plane2_read_back(
            identifier=capture.IDENTIFIER, since="-5 min", grep=base_nonce
        )
        if error:
            return [], error
        beats = sum(1 for line in lines if "event=drill_heartbeat" in line)
        if beats >= want or time.monotonic() >= deadline:
            return lines, ""
        time.sleep(0.2)


def plane2_evidence(base_nonce: str, arms: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """What reached the journal across each arm's life, and what did not.

    `arms` maps an arm's per-producer nonce to `{"pid": int, "bus_max_seq": int}`.
    Every verdict here is a comparison of two INDEPENDENT records of the same
    events — the state bus (ZeroMQ, a socket the producer wrote) and journald
    (`/dev/log`, a different socket the producer wrote) — so a claim of survival
    rests on two transports agreeing, not on one transport being asked about
    itself.
    """
    want = sum(int(arm.get("bus_max_seq", 0)) for arm in arms.values())
    lines, error = _await_journal(base_nonce, want)
    if error:
        return {"error": error, "arms": {}}
    pids = {str(arm["pid"]): nonce for nonce, arm in arms.items()}
    seqs: dict[str, set[int]] = {nonce: set() for nonce in arms}
    lifecycle: dict[str, set[str]] = {nonce: set() for nonce in arms}
    all_lines, all_error = plane2_read_back(
        identifier=capture.IDENTIFIER, since="-5 min"
    )
    for line in lines:
        fields = _fields(line)
        nonce = fields.get("nonce", "")
        if fields.get("event") == "drill_heartbeat" and nonce in seqs:
            seqs[nonce].add(int(fields.get("seq", "0")))
    for line in [] if all_error else all_lines:
        fields = _fields(line)
        nonce = pids.get(fields.get("pid", ""), "")
        if nonce and fields.get("event") in ("process_start", "process_stop"):
            lifecycle[nonce].add(str(fields["event"]))
    return {
        "error": "",
        "lifecycle_readback_error": all_error,
        "arms": {
            nonce: _plane2_arm(arm, seqs[nonce], lifecycle[nonce])
            for nonce, arm in arms.items()
        },
    }


def _plane2_arm(arm: dict[str, Any], seen: set[int], lifecycle: set[str]) -> dict:
    """One producer's Plane-2 record, compared against what the bus proved."""
    bus_max = int(arm.get("bus_max_seq", 0))
    expected = set(range(1, bus_max + 1))
    return {
        "pid": arm["pid"],
        "killed": bool(arm.get("killed")),
        #: False on the clean-exit arm, which runs with no observer attached. The
        #: seq comparison is then not merely empty, it is UNAVAILABLE, and the
        #: flag says so — an arm with nothing to compare must not read as an arm
        #: that compared and found nothing wrong.
        "bus_compared": bus_max > 0,
        "bus_max_seq": bus_max,
        "journal_max_seq": max(seen) if seen else 0,
        "journal_seq_count": len(seen),
        "lost_below_bus_max": sorted(expected - seen),
        "beyond_bus_max": sorted(seen - expected) if bus_max else [],
        "process_start_in_journal": "process_start" in lifecycle,
        "process_stop_in_journal": "process_stop" in lifecycle,
    }


# ---------------------------------------------------------------------------
# ATTRIBUTION
# ---------------------------------------------------------------------------


def attribution(trials: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    """Which clock does detection follow — the kill's, or the wall's?

    Returns the two standard deviations and a verdict. `refusal` is non-empty
    whenever the statistic could not have discriminated: too few trials, or kill
    offsets that did not actually vary. A refusal is never a pass, and it is
    never quietly folded into `attributed`.
    """
    latencies = [
        t["detect_latency_s"][channel]
        for t in trials
        if channel in t["detect_latency_s"]
    ]
    since = [
        t["detect_since_start_s"][channel]
        for t in trials
        if channel in t["detect_since_start_s"]
    ]
    offsets = [t["kill_offset_s"] for t in trials]
    if len(latencies) < 3 or len(latencies) != len(trials):
        return {
            "channel": channel,
            "refusal": (
                f"{len(latencies)} of {len(trials)} trial(s) detected on channel "
                f"{channel}; the discriminator needs a detection in every trial and "
                "at least 3"
            ),
        }
    jitter = statistics.stdev(offsets)
    if jitter < MIN_JITTER_S:
        return {
            "channel": channel,
            "refusal": (
                f"kill offsets varied by only {jitter:.4f}s (floor {MIN_JITTER_S}s) — "
                "with no spread a kill-driven detector and a timer-driven one predict "
                "the SAME numbers, so this run could not have told them apart"
            ),
        }
    lat_sd = statistics.stdev(latencies)
    since_sd = statistics.stdev(since)
    return {
        "channel": channel,
        "refusal": "",
        "n": len(latencies),
        "kill_offset_stdev_s": jitter,
        "detect_latency_mean_s": statistics.fmean(latencies),
        "detect_latency_stdev_s": lat_sd,
        "detect_since_start_stdev_s": since_sd,
        "ratio": (since_sd / lat_sd) if lat_sd > 0 else float("inf"),
        "attributed": since_sd > lat_sd * ATTRIBUTION_RATIO,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def stratified_offsets(trials: int) -> list[float]:
    """One kill offset per trial, each drawn uniformly inside its OWN band.

    The window `[KILL_MIN_S, KILL_MAX_S]` is cut into `trials` equal strata and
    one offset is drawn in each. Every offset is still unpredictable — nothing in
    the producer can anticipate its own death — but the SPREAD is bounded below
    by the stratum width, which is what the attribution statistic needs to have
    any power at all. See the module docstring for the run that forced this.
    """
    rng = secrets.SystemRandom()
    width = (KILL_MAX_S - KILL_MIN_S) / max(1, trials)
    return [
        rng.uniform(KILL_MIN_S + index * width, KILL_MIN_S + (index + 1) * width)
        for index in range(trials)
    ]


def run_drill(  # pylint: disable=too-many-arguments
    root: Path,
    *,
    trials: int,
    pin: bool,
    starve: bool = True,
    plane2: bool = True,
) -> dict:
    """The whole drill: N randomised kills, a control, and a starve arm.

    `starve` and `plane2` are switchable so the two gates that drive this can each
    pay only for the arms their own property needs. Neither switch can turn off an
    arm that another arm's verdict depends on: the attribution statistic reads
    only `trials`, and the Plane-2 comparison reads only what the arms recorded.
    """
    nonce = secrets.token_hex(6)
    records = [
        _trial(root, nonce, index, kill_offset=offset, pin=pin)
        for index, offset in enumerate(stratified_offsets(trials))
    ]
    longest = (
        max([t["kill_offset_s"] for t in records] + [KILL_MAX_S])
        + max(THRESHOLD_S.values())
        + 1.0
    )
    out: dict[str, Any] = {
        "nonce": nonce,
        "observer_resolution_ms": OBSERVE_POLL_MS,
        "thresholds_s": {c.value: v for c, v in THRESHOLD_S.items()},
        "trials": records,
        "control": _hold(
            root,
            nonce,
            tag="c",
            arm="control-no-kill",
            starve="",
            hold_s=longest,
            pin=pin,
        ),
        "attribution": {
            channel.value: attribution(records, channel.value)
            for channel in THRESHOLD_S
        },
    }
    if starve:
        out["starve"] = _hold(
            root,
            nonce,
            tag="s",
            arm=f"starve-{FeedChannel.POLL.value}",
            starve=FeedChannel.POLL.value,
            hold_s=THRESHOLD_S[FeedChannel.POLL] + 0.6,
            pin=pin,
        )
    if not plane2:
        return out
    out["clean_exit"] = _clean(root, nonce, 0.8, pin=pin)
    arms = {
        record["arm_nonce"]: {
            "pid": record["pid"],
            "bus_max_seq": record.get("bus_max_seq", 0),
            "killed": bool(record.get("signal")),
        }
        for record in [
            *records,
            out["control"],
            out["clean_exit"],
            *([out["starve"]] if starve else []),
        ]
    }
    out["plane2"] = plane2_evidence(nonce, arms)
    return out


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--produce", action="store_true", help="be the datafeed (child)"
    )
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--ring", default="")
    parser.add_argument("--nonce", default="")
    parser.add_argument("--duration-s", type=float, default=5.0)
    parser.add_argument(
        "--starve", default="", help="freeze this channel's venue clock"
    )
    parser.add_argument(
        "--no-pin", action="store_true", help="do not pin to §10 Core 1"
    )
    parser.add_argument("--root", default="", help="bus root (parent mode)")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--json", dest="json_out", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    """`--produce` is the child; otherwise run the drill and print its evidence."""
    args = _parser().parse_args(argv)
    if args.produce:
        return _produce(
            _ProducerArgs(
                endpoint=args.endpoint,
                ring=args.ring,
                nonce=args.nonce,
                duration_s=args.duration_s,
                starve=args.starve,
                pin=not args.no_pin,
            )
        )
    if not args.root:
        print("--root is required in drill mode (a bus root you own)", file=sys.stderr)
        return 2
    result = run_drill(Path(args.root), trials=args.trials, pin=not args.no_pin)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
