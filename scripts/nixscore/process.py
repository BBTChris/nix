#!/usr/bin/env python3
"""The §6.6 Scoring process: a REAL process that can be REALLY killed.

ARC 036 / sub-agent C. Authority: `docs/nics_risk_subsystem_spec_v1.3.md`
§6.6:457 (*a dedicated Scoring process … is the sole writer of a continuously
updated ranking table*), §6.6:465 (**FALLBACK, locked**), §12.7:650 (mirror
model, ZeroMQ PUB/SUB, snapshot-on-subscribe), §12.7:662 (*mirror incomplete ⇒
treated as stale*), §12.9 (the **Warning** tier: *Scoring down ⇒ FCFS
fallback*), §11:595 (*Ranking-table lookup only … stale/absent table ⇒ FCFS
fallback, never a stall*), §12.2:617 (supervision / crash-loop breaker).

The row shape, the arbitration contract and the five FCFS triggers are
`scripts/nixscore/seam.py`, FROZEN at `seam_rev 1.0.0`. **Nothing here
re-declares one of them.** This module is the two things the seam deliberately
is not: a process that owns the table and publishes it, and the consumer-side
plumbing that connects the wire to the frozen mirror.

------------------------------------------------------------------------------
WHY THIS MODULE EXISTS AT ALL — the trap it was built to defeat
------------------------------------------------------------------------------

§6.6:465, locked: *"if the Scoring process is down or its table is stale, both
Allocator and Limiter fall back to first-come-first-served … Ranking is an
optimization, never a safety gate: a scoring outage must NEVER halt order
flow."*

**A Scoring process that is never taken down never exercises that fallback.**
`checks/check_scoring_seam.py` drives all five triggers in-process and is
correct as far as it reaches — but every one of its "outages" is a Python object
that was never fed. Under that suite the SURVIVAL property (order flow keeps
deciding while the writer is a corpse) is 100 % unmeasured and every gate is
green. So the subject here is a process with a pid, and the instrument that
consumes it (`scripts/scoring_kill_drill.py`) kills it with `SIGKILL` and reads
the KERNEL's reaped wait status.

------------------------------------------------------------------------------
THE PERSISTENCE SEAM IS DECLARED HERE AND IMPLEMENTED ELSEWHERE
------------------------------------------------------------------------------

§6.6 requires the score to **persist across process death** (*"keyed to the
pair, not the process"*). That store is sub-agent D's, and building a second one
here would be the duplicate instrument doctrine C.9 forbids. So `ScoreStore` is
a `Protocol` — a declaration — and the only implementation shipped in this file
is `EphemeralScoreStore`, which **says of itself that it is not durable**
(`durable = False`). A stub that claimed durability would be the worst artifact
in this arc: every gate green, and the scores gone the moment the thing this
module exists to survive actually happens.

------------------------------------------------------------------------------
WHAT A READER GETS, AND THE WINDOW IT IS WRONG IN
------------------------------------------------------------------------------

`RankingReader` holds a `StateSubscriber` and the frozen `RankingMirror`. When
the publisher dies, **the subscriber socket does not**: libzmq keeps the SUB
endpoint open and simply stops receiving. The mirror therefore holds a complete,
well-formed, confidently-answered table that stopped being true at the instant
of death, and it keeps RANKING on it until `stale_after_s` elapses. That window
is a design consequence of §12.7's freshness model, not a defect — but it is
real, it is `stale_after_s` long, and it is measured and reported by name
(`frozen_table_window_s`) rather than left for someone to discover. Shrinking it
is a tunable decision; pretending it is zero is a lie a green gate would tell.

`FallbackAlarm` is §12.9's Warning tier on that transition, EDGE-triggered so an
operator gets one alert and not a stream. **There is no alert TRANSPORT in this
tree** — every `AlertSink` in `scripts/` is a Protocol whose only implementations
are test doubles, and §12.9 leaves the transport CC-defined (§13). That is
recorded as a debt row, not invented here.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from types import FrameType
from typing import Protocol, runtime_checkable

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_SCRIPTS))

# pylint: disable=wrong-import-position
from nixbus.statebus import StatePublisher, StateSubscriber

from nixscore.seam import (
    RANKING_TOPIC,
    SCORING_WRITER_IDENTITY,
    PairKey,
    RankingMirror,
    RankingPublisher,
    RankingSnapshot,
    RankRow,
    Verdict,
    rank_rows,
)

#: §6.6's `SCORE_EMA_SPAN_DAYS` default, carried as DATA on every snapshot so a
#: consumer can read the span the table was computed under. It is a §12A tunable
#: and not a carved constant; this is the boot default, overridable on the CLI.
DEFAULT_SPAN_DAYS = 10

#: How often the process re-publishes the whole table. §12.7 asks for a
#: *periodic full-state refresh* on top of snapshot-on-subscribe; this is that
#: period. Short, because the reader's freshness threshold is what it feeds.
DEFAULT_PUBLISH_INTERVAL_S = 0.05

#: The §12.9 Warning-tier codes. Named constants because an operator's runbook
#: keys on the CODE and a typo'd string is an alert nobody has a rule for.
SCORING_DOWN_CODE = "scoring-down-fcfs"
SCORING_RESTORED_CODE = "scoring-restored-ranked"

#: Exit code `main` returns when it was asked to stop by a signal it handles.
#: DISTINCT from 0 so a clean shutdown is distinguishable from a run that simply
#: finished, and distinct from 1 so it is not read as a failure (check contract
#: §18: an exit code is a shared namespace).
SIGNALLED_EXIT = 7


class ScoringProcessError(RuntimeError):
    """A Scoring process could not do what it was asked. Always says what."""


@dataclasses.dataclass(frozen=True, slots=True)
class StoredScore:
    """One pair's persisted standing: the EMA and how much history stands behind it.

    The unit of persistence is deliberately the SAME unit §6.6 locks as the unit
    of storage — one row per `(strategy_id, symbol)` pair — so a store can be
    swapped in without the process re-shaping anything.
    """

    realized_ema: float
    days_observed: int


@runtime_checkable
class ScoreStore(Protocol):
    """The persistence seam. **Declared here, implemented by sub-agent D.**

    §6.6: the score *"persists across process death (keyed to the pair, not the
    process)"*. `durable` is an attribute rather than a docstring claim so a
    caller can BRANCH on it — a process that knows its store forgets can say so
    in its startup announcement instead of implying otherwise by silence.
    """

    #: Whether scores written here survive this process being killed.
    durable: bool

    def load(self) -> Mapping[PairKey, StoredScore]:
        """Every persisted pair-row. Empty on a genuinely cold start."""

    def save(self, scores: Mapping[PairKey, StoredScore]) -> int:
        """Persist the whole table atomically. Returns rows written."""


class EphemeralScoreStore:
    """The STUB. Holds scores in memory and **loses them when the process dies**.

    `durable = False` is the whole point of this class: it is the honest stand-in
    for the store sub-agent D builds, and it advertises the exact property it
    does not have. Wiring the real store is the integrator's job at Stage 2 —
    this object is what keeps `ScoringProcess` runnable until then.
    """

    #: Read by callers, printed in the startup announcement. Never True here.
    durable = False

    def __init__(self, seed: Mapping[PairKey, StoredScore] | None = None) -> None:
        self._scores: dict[PairKey, StoredScore] = dict(seed or {})
        self.loads = 0
        self.saves = 0

    def load(self) -> Mapping[PairKey, StoredScore]:
        """Whatever this process put here. Counted, so a caller can prove it ran."""
        self.loads += 1
        return dict(self._scores)

    def save(self, scores: Mapping[PairKey, StoredScore]) -> int:
        """Replace the held table. Counted. Durable to exactly nothing."""
        self._scores = dict(scores)
        self.saves += 1
        return len(self._scores)


class AlertSink(Protocol):  # pylint: disable=too-few-public-methods
    """§12.9's push tier. One verb, declared; the transport is CC-defined (§13).

    R0903 is refused rather than satisfied: a Protocol is a DECLARATION, and
    inventing a second verb to reach a method count would put a surface in the
    seam that no caller asked for.
    """

    def alert(self, code: str, message: str) -> None:
        """Deliver one alert. Carries the CAUSE, never only a code (§12.9)."""


class RecordingAlertSink:
    """An `AlertSink` that keeps what it was told. The only one this tree has.

    Not a convenience: `scripts/` contains four `AlertSink` Protocols and **zero
    concrete transports**, so an alert raised by production code today reaches
    nobody unless a caller supplies a sink. Shipping a recording one makes that
    fact measurable — a drill can prove the alert FIRED and with what — instead
    of leaving the alert path untested because there is nothing to attach to it.
    """

    def __init__(self) -> None:
        self.alerts: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        """Record one alert."""
        self.alerts.append((code, message))

    def codes(self) -> tuple[str, ...]:
        """Just the codes, in order. What an assertion usually wants."""
        return tuple(code for code, _ in self.alerts)


class ScoringProcess:  # pylint: disable=too-many-instance-attributes
    """The §6.6 Scoring process. Sole writer of the ranking table.

    Three of its attributes are COUNTERS — `published`, `snapshots_served`,
    `saves` — and they exist for the reason `StatePublisher`'s four do: a writer
    that cannot say what it wrote can only be believed.

    The table lives in THIS object's memory (§12.7's mirror model) and leaves
    only as an atomic snapshot through `RankingPublisher`. There is no verb by
    which anything outside can write a row: `set_score` is the single mutator and
    it takes scalars, never a table.
    """

    def __init__(
        self,
        publisher: RankingPublisher,
        *,
        store: ScoreStore,
        span_days: int = DEFAULT_SPAN_DAYS,
        publish_interval_s: float = DEFAULT_PUBLISH_INTERVAL_S,
    ) -> None:
        if span_days <= 0:
            raise ScoringProcessError(
                f"span_days={span_days!r}: §6.6's EMA span is a count of trading "
                "days and a non-positive span defines no smoothing at all"
            )
        if publish_interval_s <= 0:
            raise ScoringProcessError(
                f"publish_interval_s={publish_interval_s!r}: a non-positive "
                "period would republish in a spin loop and starve `service`"
            )
        self._publisher = publisher
        self._store = store
        self.span_days = int(span_days)
        self.publish_interval_s = float(publish_interval_s)
        self._scores: dict[PairKey, StoredScore] = dict(store.load())
        self._last_publish: float | None = None
        self._stopped = False
        #: COUNTERS, not flags — the same reasoning as `StatePublisher`'s four.
        self.published = 0
        self.snapshots_served = 0
        self.saves = 0

    @property
    def store_is_durable(self) -> bool:
        """Whether this process's scores survive its own death. §6.6."""
        return bool(getattr(self._store, "durable", False))

    @property
    def scores(self) -> Mapping[PairKey, StoredScore]:
        """A COPY of the owned table. The owner never hands out its own dict."""
        return dict(self._scores)

    def set_score(self, key: PairKey, realized_ema: float, days_observed: int) -> None:
        """The ONE mutator. Scoring-side: this is where the EMA lands.

        The EMA arithmetic itself is sub-agent A's engine; what is locked here is
        that the value arrives through a single writer and per `(strategy_id,
        symbol)` pair, which is §6.6's canonical key.
        """
        strategy_id, symbol = key
        if not strategy_id or not symbol:
            raise ScoringProcessError(
                f"pair key {key!r} has an empty component — §6.6 keys one row per "
                "(strategy_id, symbol) and a half-key names no pair"
            )
        self._scores[key] = StoredScore(float(realized_ema), int(days_observed))

    def snapshot(self) -> RankingSnapshot:
        """The whole table as one atomic value. Ranking happens HERE, off any hot path."""
        emas = {key: score.realized_ema for key, score in self._scores.items()}
        observed = {key: score.days_observed for key, score in self._scores.items()}
        rows: dict[PairKey, RankRow] = rank_rows(emas, observed)
        return RankingSnapshot(
            rows=rows,
            span_days=self.span_days,
            writer_identity=SCORING_WRITER_IDENTITY,
        )

    def publish_table(self, now: float | None = None) -> int:
        """Publish the table and persist it. Returns rows published."""
        snapshot = self.snapshot()
        self._publisher.publish(snapshot)
        self.published += 1
        self._last_publish = time.monotonic() if now is None else now
        self.saves += 1
        self._store.save(self.scores)
        return len(snapshot.rows)

    def _due(self, now: float) -> bool:
        """Whether the periodic full-state refresh (§12.7) is owed."""
        if self._last_publish is None:
            return True
        return (now - self._last_publish) >= self.publish_interval_s

    def tick(self, timeout_ms: int = 0) -> dict[str, int]:
        """One pass of the process loop: serve subscriptions, republish if due.

        Split out from `run` so a test or a drill can step the process without a
        thread, and so the two things §12.7 requires — snapshot-on-subscribe and
        the periodic refresh — are visibly two things.
        """
        served = self._publisher.service(timeout_ms)
        self.snapshots_served += served
        rows = 0
        if self._due(time.monotonic()):
            rows = self.publish_table()
        return {"served": served, "published_rows": rows}

    def run(self, *, deadline_s: float | None = None, tick_ms: int = 5) -> int:
        """Loop until `deadline_s` elapses or `stop()` is called. Returns ticks.

        `deadline_s is None` means *until stopped or killed*, which is the mode
        the kill drill uses: the process must be alive and working at the instant
        the signal lands, or the drill measured a shutdown rather than a death.
        """
        self._stopped = False
        started = time.monotonic()
        ticks = 0
        while not self._stopped:
            if deadline_s is not None and (time.monotonic() - started) >= deadline_s:
                break
            self.tick(tick_ms)
            ticks += 1
        return ticks

    def stop(self) -> None:
        """Ask `run` to return at the top of the next pass. Idempotent."""
        self._stopped = True


class RankingReader:
    """The consumer side: wire -> frozen `RankingMirror`. Allocator and Limiter each hold one.

    Two verbs and they are deliberately on opposite sides of a line:

    * `pump` touches the SOCKET. It loops, it does I/O, and it is called from the
      consumer's own loop — **never from the order path**.
    * `arbitrate` touches NOTHING but the mirror. It is a straight delegation to
      the frozen seam, so the order path's latency is the seam's O(1) lookup and
      nothing this module added.

    Keeping them apart is the §11:595 discipline made structural: if `arbitrate`
    pumped, an order decision would sit behind a socket at exactly the moment the
    publisher stopped answering.
    """

    def __init__(
        self,
        subscriber: StateSubscriber,
        *,
        stale_after_s: float,
        identity: str = SCORING_WRITER_IDENTITY,
    ) -> None:
        self._subscriber = subscriber
        self.mirror = RankingMirror(stale_after_s=stale_after_s, identity=identity)
        #: Ranking messages that reached the mirror. Zero is a finding, exactly
        #: as `StateSubscriber.bytes_received == 0` is.
        self.pumped = 0

    def pump(self, timeout_ms: int = 0) -> int:
        """Drain the socket into the mirror. Returns snapshots APPLIED.

        Off the order path by contract — see the class docstring.

        **It does not call `StateSubscriber.drain`, and that is deliberate.**
        MEASURED, ARC 036 sub-agent C: `drain` computes its remaining budget as
        `int((deadline - now) * 1000)`, so a budget of 1 ms truncates to `0`
        before the first poll and the method returns having **never looked at
        the socket**. A caller asking for one millisecond silently gets "never".
        The first observed symptom was a reader that received nothing across a
        whole drill while every socket was healthy — a mirror reporting the
        never-fed FCFS trigger for a reason that had nothing to do with the
        publisher. Recorded as CHECK-DEBT; not repaired here, because `drain` is
        shared transport and this arc does not own it.

        `timeout_ms=0` here is therefore a genuinely non-blocking sweep: take
        everything the socket already holds and return.
        """
        applied = 0
        budget = timeout_ms
        while True:
            message = self._subscriber.poll(budget)
            budget = 0
            if message is None:
                self.pumped += applied
                return applied
            if self.mirror.apply(message):
                applied += 1

    def arbitrate(self, first: PairKey, second: PairKey) -> Verdict:
        """THE ORDER PATH. One delegation to the frozen seam; no I/O, no math."""
        return self.mirror.arbitrate(first, second)

    def close(self) -> None:
        """Release the subscriber's socket."""
        self._subscriber.close()


class FallbackAlarm:  # pylint: disable=too-few-public-methods
    """§12.9's Warning: *Scoring down ⇒ FCFS fallback*. EDGE-triggered, both ways.

    Edge and not level, because §12.9's alerting tier is *push, not glance*: a
    level-triggered alarm on a dead Scoring process pages the operator once per
    poll forever, which is how a real alert gets muted and then missed. The
    recovery edge is alerted too — an operator told the system degraded and never
    told it recovered has to go and look, which is the thing the tier exists to
    avoid.

    The message carries the AGE, the THRESHOLD and the ROW COUNT, because §12.9
    requires alerts to carry *"the cause and the relevant snapshot values, not
    just a code"*.
    """

    def __init__(
        self, mirror: RankingMirror, *, alert: AlertSink | None = None
    ) -> None:
        self._mirror = mirror
        self._alert = alert
        #: `None` until the first poll: the FIRST observation is not an edge, it
        #: is the baseline. Alerting on it would page on every reader start.
        self._was_fresh: bool | None = None
        self.fired: list[tuple[str, str]] = []

    def poll(self, now: float | None = None) -> str:
        """Observe the mirror once. Returns the code fired, or `""`."""
        fresh = self._mirror.fresh(now)
        previous = self._was_fresh
        self._was_fresh = fresh
        if previous is None or previous == fresh:
            return ""
        code = SCORING_RESTORED_CODE if fresh else SCORING_DOWN_CODE
        self._emit(code, now)
        return code

    def _emit(self, code: str, now: float | None) -> None:
        """Raise one alert with the cause and the snapshot values (§12.9)."""
        age = self._mirror.age_s(now)
        age_text = "never fed" if age is None else f"{age:.3f}s"
        message = (
            f"§6.6 contention arbitration is now "
            f"{'RANKED again' if code == SCORING_RESTORED_CODE else 'FCFS'}: "
            f"ranking table age {age_text} against a "
            f"{self._mirror.stale_after_s:.3f}s freshness threshold, "
            f"{self._mirror.applied} snapshot(s) applied. Order flow is "
            f"UNAFFECTED — §6.6:465 makes ranking an optimization, never a "
            f"safety gate"
        )
        self.fired.append((code, message))
        if self._alert is not None:
            self._alert.alert(code, message)


# ---------------------------------------------------------------------------
# The runnable process
# ---------------------------------------------------------------------------


def parse_score(raw: str) -> tuple[PairKey, StoredScore]:
    """`strategy,symbol,ema,days` -> one seeded pair-row. Raises on anything else."""
    parts = raw.split(",")
    if len(parts) != 4:
        raise ScoringProcessError(
            f"--score {raw!r}: expected strategy,symbol,ema,days (four fields)"
        )
    strategy, symbol, ema, days = parts
    try:
        return (strategy, symbol), StoredScore(float(ema), int(days))
    except ValueError as exc:
        raise ScoringProcessError(f"--score {raw!r}: {exc}") from exc


def build_process(
    endpoint: str,
    seeds: Mapping[PairKey, StoredScore],
    span_days: int,
    interval_s: float,
) -> tuple[ScoringProcess, StatePublisher]:
    """Bind the endpoint and construct the process around it.

    Returns the raw `StatePublisher` too, so a caller that must close the socket
    on an error path can, without reaching through the process object.
    The seeds go in through `set_score`, **not** through the store's constructor.
    That is deliberate: `set_score` is the verb sub-agent A's EMA engine will
    call, so the CLI drives the process along the same path production will, and
    a store handed a pre-filled dict would leave the one mutator unexercised by
    everything except a test.
    """
    state = StatePublisher(endpoint)
    process = ScoringProcess(
        RankingPublisher(state),
        store=EphemeralScoreStore(),
        span_days=span_days,
        publish_interval_s=interval_s,
    )
    for key, score in seeds.items():
        process.set_score(key, score.realized_ema, score.days_observed)
    return process, state


def _install_stop(process: ScoringProcess) -> None:
    """SIGTERM/SIGINT stop the loop cleanly. **SIGKILL is not catchable** — and
    that asymmetry is the point: the drill's control arm exits through here, and
    its kill arm cannot, so a reaped `0` and a reaped `-SIGKILL` are two facts."""

    def _handler(_signum: int, _frame: FrameType | None) -> None:
        process.stop()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def _announce(process: ScoringProcess, endpoint: str, rows: int) -> None:
    """One JSON line on stdout, flushed. The parent learns the PID from the CHILD.

    `store_durable` is in the line deliberately: a process whose scores die with
    it must SAY so where the operator and the drill both read it.
    """
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "endpoint": endpoint,
                "topic": RANKING_TOPIC,
                "rows": rows,
                "span_days": process.span_days,
                "identity": SCORING_WRITER_IDENTITY,
                "store_durable": process.store_is_durable,
                "started_at": time.time(),
            }
        ),
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="§6.6 Scoring process")
    parser.add_argument("--endpoint", required=True, help="ipc:// endpoint to bind")
    parser.add_argument("--span-days", type=int, default=DEFAULT_SPAN_DAYS)
    parser.add_argument("--interval-s", type=float, default=DEFAULT_PUBLISH_INTERVAL_S)
    parser.add_argument(
        "--score", action="append", default=[], help="strategy,symbol,ema,days"
    )
    parser.add_argument(
        "--run-s",
        type=float,
        default=-1.0,
        help="seconds to run; negative means until stopped or killed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Bind, seed, publish, announce, and run until stopped or killed."""
    args = _parser().parse_args(argv)
    seeds = dict(parse_score(raw) for raw in args.score)
    process, state = build_process(
        args.endpoint, seeds, args.span_days, args.interval_s
    )
    try:
        _install_stop(process)
        rows = process.publish_table()
        _announce(process, args.endpoint, rows)
        process.run(deadline_s=None if args.run_s < 0 else args.run_s)
    finally:
        state.close()
    return SIGNALLED_EXIT if args.run_s < 0 else 0


if __name__ == "__main__":
    sys.exit(main())
