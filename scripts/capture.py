#!/usr/bin/env python3
"""`capture.py` — the Core 1 process that hosts the broker-datafeed library.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §10 (Process/Core Map,
locked — *"Core 1 | capture.py (hosts **broker-datafeed** library) | isolated,
elevated — tick firehose"*), §2A (the datafeed seam), §12.7 (state-table
transport + the price-firehose exception), §12.10 (two-plane logging).
`docs/SPEC-AMENDMENTS.md` AMENDMENT 6 (freshness is per-channel; the ruling text
calls itself AMENDMENT 5 and the file records why the number moved).

## WHAT THIS FILE IS

The **process**. It owns three things and nothing else:

1. **Its core.** `start()` pins to §10's Core 1 through `nixbus.core_map` and
   reports the mask the kernel actually gave it back.
2. **Its Plane-2 stream.** §12.10: *"Each process writes its **own** structured
   one-line events."* The broker libraries are in-process libraries and have no
   stream of their own; `capture.py` is a process and therefore owes emission
   directly. It emits feed-staleness transitions **per channel**, which is what
   AMENDMENT 6 turned from one event into several.
3. **Its two transports.** State tables go out over `nixbus.statebus` (ZMQ,
   §12.7); per-tick prices go into `nixbus.price_ring` (shared memory, §12.7's
   sole exception).

## WHAT THIS FILE IS NOT — stated, because each absence is load-bearing

* **It is not a Plane-1 writer, and cannot become one by accident.** §12.10:
  *"Plane 1 — Postgres, **Limiter sole writer**. No new writers, ever."* There is
  no database import in this module, no connection string, and no file handle
  under `logs/`. The Limiter does not exist yet; when it does, it writes Plane 1
  and this file still does not.
* **It does not connect to a venue.** `scripts/broker/broker_datafeed_ibkr.py`
  is the adapter and it needs a live IB Gateway, which is down on this node. A
  connect path written against a session that has never been observed would be
  an unmeasured claim; the seam is injected (`attach_datafeed`) so the wiring is
  a constructor argument rather than a rewrite when a session exists.
* **It does not decide what staleness MEANS.** AMENDMENT 6: *"The consumer
  decides which channels it requires ... the **seam** is not entitled to decide
  that on its behalf."* `capture.py` is not that consumer either — it OBSERVES
  the per-channel report, records transitions, and publishes them. The
  halt-and-flatten decision is §6.4's and belongs to the Limiter.

## The transition rule, and why it is transitions rather than levels

§12.10's inventory row is *"feed staleness **transitions**; broker session
lost/restored"* — Plane 2, no Plane 1. A level would be one event per poll per
channel per symbol, which is the chatty logging §12.10 explicitly rejects for
trailing-stop ratchets. So `FeedStalenessMonitor` holds the last state it saw for
each `(symbol, channel)` and emits **only on change**, including the first
observation (`from=unobserved`), because a channel's first reading is the
transition out of "we had no relationship with this symbol".
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
for _extra in (str(_HERE), str(_HERE / "broker")):
    if _extra not in sys.path:
        sys.path.append(_extra)

# pylint: disable=wrong-import-position
from broker_seam import (
    ChannelState,
    FeedChannel,
    FreshnessReport,
)
from nixbus import price_ring, statebus
from nixbus.core_map import (
    AffinityReading,
    Role,
    format_cpu_list,
    pin_self,
)
from nixverify.plane2 import Plane2

#: §12.10's `proc=` field for every event this process emits.
PROCESS = "capture.py"

#: `journalctl -t nix-capture` selects this process's Plane-2 stream and nothing
#: else. Distinct from `verify.py`'s `nix-verify` so the two planes-2 streams of
#: two processes never have to be told apart by content.
IDENTIFIER = "nix-capture"

#: The state table this process OWNS and publishes (§12.7 mirror model). Feed
#: status is capture.py's to publish because capture.py is where the datafeed
#: library lives; nothing else may publish it.
TOPIC_FEED_STATUS = "tbl.feed_status"

#: Endpoint name under the bus root. One socket, one owner.
BUS_NAME = "capture"

#: `unobserved` is not a `ChannelState`. It is the absence of one, and it is
#: spelled here rather than added to that enum: `ChannelState` is a verdict about
#: a channel, and "we have never looked" is not a verdict.
UNOBSERVED = "unobserved"


@dataclasses.dataclass(frozen=True)
class StalenessTransition:  # pylint: disable=too-many-instance-attributes
    """One channel's state changing. The unit of §12.10's inventory row.

    Nine fields, and the count is the design: AMENDMENT 6 requires a per-channel
    verdict to carry the inputs that produced it, so `excess_staleness_s`,
    `threshold_s`, `effective_lag_s`, `venue_ts` and `lag_provenance` ride beside
    `from`/`to`. Splitting them into a nested object to satisfy a field counter
    would put the reasoning one indirection away from the verdict, which is the
    shape `ChannelFreshness.__post_init__` refuses inside the seam."""

    symbol: str
    channel: FeedChannel
    previous: str
    current: ChannelState
    excess_staleness_s: float | None
    threshold_s: float
    effective_lag_s: float | None
    venue_ts: float | None
    lag_provenance: str

    def fields(self) -> dict[str, Any]:
        """The §12.10 `key=value` payload. Every input to the verdict rides along.

        A transition event carrying only `from`/`to` would be a verdict with its
        reasoning stripped — the same shape `ChannelFreshness.__post_init__`
        refuses inside the seam. An operator reading the journal must be able to
        recompute the verdict from the line.
        """
        return {
            "symbol": self.symbol,
            "channel": self.channel.value,
            "from": self.previous,
            "to": self.current.value,
            "excess_staleness_s": (
                "-"
                if self.excess_staleness_s is None
                else f"{self.excess_staleness_s:.3f}"
            ),
            "threshold_s": f"{self.threshold_s:.3f}",
            "effective_lag_s": (
                "-" if self.effective_lag_s is None else f"{self.effective_lag_s:.3f}"
            ),
            "venue_ts": "-" if self.venue_ts is None else f"{self.venue_ts:.6f}",
            "lag_provenance": self.lag_provenance,
        }


class FeedStalenessMonitor:
    """Per-`(symbol, channel)` state, and the transitions between states.

    Deliberately holds no `Plane2`: this class decides WHAT changed and the
    caller decides where that goes. Keeping the two apart is what lets the
    transition rule be tested without a journal, and what stops a future consumer
    of the transitions from having to acquire a syslog socket to get them.
    """

    def __init__(self) -> None:
        self._last: dict[tuple[str, FeedChannel], str] = {}
        self.observations = 0
        self.transitions = 0

    def observe(self, report: FreshnessReport) -> list[StalenessTransition]:
        """Fold one per-channel report in; return only the channels that MOVED."""
        changed: list[StalenessTransition] = []
        for entry in report.channels:
            self.observations += 1
            key = (str(report.symbol), entry.channel)
            previous = self._last.get(key, UNOBSERVED)
            if previous == entry.state.value:
                continue
            self._last[key] = entry.state.value
            self.transitions += 1
            changed.append(
                StalenessTransition(
                    symbol=str(report.symbol),
                    channel=entry.channel,
                    previous=previous,
                    current=entry.state,
                    excess_staleness_s=entry.excess_staleness_s,
                    threshold_s=entry.threshold_s,
                    effective_lag_s=entry.lag.effective_lag_s,
                    venue_ts=entry.venue_ts,
                    lag_provenance=entry.lag.provenance.value,
                )
            )
        return changed

    def state_of(self, symbol: str, channel: FeedChannel) -> str:
        """This monitor's last reading for one channel, or `unobserved`."""
        return self._last.get((symbol, channel), UNOBSERVED)

    def table(self) -> dict[str, dict[str, str]]:
        """The published state table: `{symbol: {channel: state}}`.

        Uncollapsed, exactly as `FreshnessReport` is. There is no `is_stale` key
        here for the same reason AMENDMENT 6 forbids one on the report — a
        consumer must name the channel it requires to get an answer.
        """
        table: dict[str, dict[str, str]] = {}
        for (symbol, channel), state in sorted(
            self._last.items(), key=lambda item: (item[0][0], item[0][1].value)
        ):
            table.setdefault(symbol, {})[channel.value] = state
        return table


class CaptureProcess:  # pylint: disable=too-many-instance-attributes
    """The process object. Construct, `start()`, feed it, `close()`.

    Eight attributes because it owns four collaborators (`plane2`, `publisher`,
    `ring`, `monitor`) and reports three observables (`affinity`,
    `ticks_written`, `transitions_emitted`). The observables are what a gate
    reads instead of asking the process whether it worked.

    Every collaborator is optional and injected. A `CaptureProcess` with no bus
    and no ring is still a real process with a real core pin and a real Plane-2
    stream, which is what makes the pieces testable one at a time instead of only
    as a daemon nobody can run without a venue.
    """

    def __init__(
        self,
        *,
        plane2: Plane2 | None = None,
        publisher: statebus.StatePublisher | None = None,
        ring: price_ring.PriceRingWriter | None = None,
        pin: bool = True,
    ) -> None:
        self.plane2 = (
            plane2
            if plane2 is not None
            else Plane2(identifier=IDENTIFIER, process=PROCESS)
        )
        self.publisher = publisher
        self.ring = ring
        self._pin = pin
        self.monitor = FeedStalenessMonitor()
        self.affinity: AffinityReading | None = None
        self.ticks_written = 0
        self.transitions_emitted = 0

    def start(self) -> AffinityReading:
        """Pin to §10's Core 1 and announce the process on Plane 2.

        The returned reading is the kernel's, taken after the pin — `pin_self`
        re-reads through both interfaces rather than echoing back the set it was
        asked for.
        """
        reading = pin_self(Role.CAPTURE) if self._pin else _self_reading()
        self.affinity = reading
        self.plane2.emit(
            "process_start",
            pid=reading.pid,
            role=Role.CAPTURE.value,
            cores=format_cpu_list(reading.mask),
            affinity_readers_agree=reading.agree,
            pinned=self._pin,
        )
        return reading

    def observe_freshness(self, report: FreshnessReport) -> list[StalenessTransition]:
        """AMENDMENT 6's obligation: one Plane-2 event per channel that MOVED.

        Also republishes the feed-status table, but ONLY when something changed —
        §12.7's periodic full-state refresh is a separate, timed concern
        (`refresh()`), and republishing on every observation would put the tick
        rate onto the state bus.
        """
        changed = self.monitor.observe(report)
        for transition in changed:
            self.plane2.emit("feed_staleness_transition", **transition.fields())
            self.transitions_emitted += 1
        if changed and self.publisher is not None:
            self.publisher.publish(TOPIC_FEED_STATUS, self.monitor.table())
        return changed

    def on_tick(
        self, symbol_id: int, price: float, size: float, venue_ts_ns: int
    ) -> None:
        """§2A:91's `on_tick` landing in §12.7's sole shared-memory exception.

        No Plane-2 event per tick, deliberately: §12.10 keeps per-tick chatter out
        of the operational log for the same reason it keeps trailing-stop ratchets
        out of it.
        """
        if self.ring is None:
            return
        self.ring.publish(symbol_id, price, size, venue_ts_ns)
        self.ticks_written += 1

    def service(self, timeout_ms: int = 0) -> int:
        """Answer pending subscriptions with snapshots (§12.7). Call from the loop."""
        return 0 if self.publisher is None else self.publisher.service(timeout_ms)

    def refresh(self) -> int:
        """§12.7's periodic full-state refresh."""
        return 0 if self.publisher is None else self.publisher.refresh_all()

    def close(self) -> None:
        """Announce the stop on Plane 2 and release both transports."""
        self.plane2.emit(
            "process_stop",
            pid=os.getpid(),
            ticks_written=self.ticks_written,
            transitions=self.transitions_emitted,
        )
        if self.publisher is not None:
            self.publisher.close()
        if self.ring is not None:
            self.ring.close()
        self.plane2.close()


def _self_reading() -> AffinityReading:
    """This process's affinity, read but not set. Used when `pin=False`."""
    from nixbus.core_map import effective_affinity  # pylint: disable=C0415

    return effective_affinity(os.getpid())


def _self_report(hold_s: float, pin: bool) -> int:
    """Print this process's own kernel-read affinity, then hold. Exit code 0/1.

    THIS EXISTS FOR `checks/check_core_map.py` AND ITS SHAPE IS THE POINT. The
    gate does not read this JSON to decide anything — it reads `/proc/<pid>` and
    `sched_getaffinity(pid)` for the PID it spawned, from the parent, while this
    process is holding. The JSON carries the PID so the parent knows WHO to
    measure, and the child's own view of its mask so a disagreement between the
    child's reading and the parent's is visible rather than assumed away.

    `--hold-s` is what makes the measurement possible at all: a process that has
    exited has no `/proc/<pid>/status` and no affinity to read.
    """
    reading = pin_self(Role.CAPTURE) if pin else _self_reading()
    print(
        json.dumps(
            {
                "pid": reading.pid,
                "role": Role.CAPTURE.value,
                "pinned": pin,
                "syscall": sorted(reading.syscall),
                "procfs": sorted(reading.procfs),
                "agree": reading.agree,
                "error": reading.error,
            }
        ),
        flush=True,
    )
    if hold_s > 0:
        time.sleep(hold_s)
    return 0 if reading.agree else 1


def main(argv: list[str] | None = None) -> int:
    """CLI. `--self-report` is the affinity gate's subject; the loop needs a venue."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--self-report",
        action="store_true",
        help="pin to the §10 core, print this process's kernel-read affinity, hold",
    )
    parser.add_argument(
        "--hold-s",
        type=float,
        default=0.0,
        help="seconds to stay alive after reporting, so a parent can measure /proc",
    )
    parser.add_argument(
        "--no-pin",
        action="store_true",
        help="report affinity without setting it (the CONTROL arm's invocation)",
    )
    args = parser.parse_args(argv)
    if args.self_report:
        return _self_report(args.hold_s, pin=not args.no_pin)
    print(
        "capture.py: no venue session exists on this node (IB Gateway down) and a "
        "connect path written against a session never observed would be an "
        "unmeasured claim. Run with --self-report, or construct CaptureProcess "
        "with an injected datafeed adapter.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
