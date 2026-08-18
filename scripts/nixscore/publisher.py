"""The §6.6 ranking table's REAL publish path, over §12.7's transport.

`seam.py` is the frozen shape — rows, snapshot, the FCFS-or-ranked contract.
This module is the wiring: a Scoring-side writer that owns a real `ipc://`
ZeroMQ endpoint, and a consumer-side reader that owns a real subscriber, a
`RankingMirror`, and one additional thing the mirror does not provide — an
**atomically-captured multi-row view**.

Nothing here re-implements anything `nixbus.statebus` or `nixscore.seam`
already own (doctrine C.9). `RankingWriter` is `StatePublisher` +
`RankingPublisher`; `RankingReader` is `StateSubscriber` + `RankingMirror`.

## THE TRANSPORT, RE-READ RATHER THAN INHERITED

§6.6:457-458 makes the Scoring process *"the sole writer of a continuously
updated ranking table **in shared memory**"*. §12.7 (line 644, LOCKED v1.3) is
later, names *"ranking table §6.6"* in its own opening list of the tables it
governs, and says at line 650: *"**Mirror model, NOT raw shared memory.** …
Raw shared state tables would let multiple processes touch the same bytes —
reintroducing locks, races, and torn reads, and reducing the single-writer
principle to fiction."* Its sole exception is the per-tick price firehose,
*"prices only, never financial state"*. A ranking table is financial state.
**§12.7 governs**, and the two sections were read on disk rather than taken
from any summary of them.

## WHAT WAS MEASURED BUILDING THIS, BECAUSE IT CHANGES HOW THIS IS USED

Three facts about the real transport, each measured on this node (pyzmq 27.1.0
/ libzmq 4.3.5) and each with a consequence in the code below.

1. **`ipc://` bind is NOT exclusive.** A second `StatePublisher` binding the
   same endpoint while the first is still bound SUCCEEDS — libzmq unlinks the
   existing socket file and rebinds. There is no `EADDRINUSE`. So the transport
   contributes **nothing** to §6.6's sole-writer guarantee: the incumbent's
   already-connected subscribers keep their (now-unlinked) inode, but every
   subscriber that connects or **reconnects** after the hijack lands on the
   impostor. Measured cross-process: kill the real publisher with `SIGKILL`,
   bind an impostor on the same path, and the surviving subscriber's SUB socket
   auto-reconnects and delivers the impostor's snapshots — 16 messages, 5737
   bytes, all of them refused by `RankingMirror` on the identity stamp and
   counted in `foreign_rejected`. **The consumer-side identity check is the
   whole of the sole-writer enforcement.** `RankingReader` therefore exposes
   `foreign_rejected` as a first-class observable rather than hiding it.

2. **The publisher does not block on a slow subscriber, it DROPS.** Measured:
   4000 publishes into a connected, never-draining subscriber completed in
   0.038 s with a worst single `publish()` of 0.38 ms; the subscriber then
   drained exactly 2000 messages, sequences 1..2000, **zero interior gaps**.
   XPUB's mute action is drop, so the loss is a **tail truncation**, not a
   hole: the consumer's table looks perfectly well-formed and is 2000 updates
   behind. §6.6's *"Scoring never waits on a reader"* holds; the cost is paid
   in silence at the consumer. `RankingReader` counts sequence gaps
   (`gaps_detected`) for the interior case and — the part that actually
   defends against truncation — the **freshness stamp** is what makes a
   fallen-behind table go stale and fall back to FCFS.

3. **Two separate reads of a mirror ARE tearable under a concurrent writer.**
   Measured: a writer thread applying 130 424 snapshots while a reader thread
   did 2 364 031 back-to-back `lookup(first)` / `lookup(second)` pairs
   produced **71 observations in which the two rows came from different
   published tables**. That is the exact shape of `RankingMirror.arbitrate`,
   which reads `self._rows` twice. It is unreachable in the single-threaded
   consumer loop this module is built for (`pump()` and the reads happen on one
   thread) — but it is not unreachable by construction, and a consumer that
   pumps on a background thread would hit it. Recorded in `docs/CHECK-DEBT.md`;
   the frozen seam was NOT edited for it.

   `RankingView` is the answer on this side of the freeze: it is captured by a
   **single attribute read** and is immutable thereafter, so any number of
   rows read out of one view come from one published table. Measured **0
   tears** in the harness that drives BOTH shapes against ONE writer thread —
   136 884 applies, 1 480 504 read pairs, **45 tears on the two-lookup path
   and 0 on the view path in the same run**. The 71 above is a separate,
   earlier run against a bare `RankingMirror`; the two are different harnesses
   and are quoted as such rather than blurred into one figure.

## SINGLE-THREAD CONTRACT

`RankingReader` is **not thread-safe and does not pretend to be.** `pump()`
mutates; `view()`, `lookup()` and `arbitrate()` read. Call them from one
thread — the consumer's own loop — exactly as `StatePublisher.service()` is
documented to be called from the owner's loop and for the same reason: a
background pump thread reintroduces the shared-mutation surface §12.7's mirror
model exists to remove.

## NO MATH ON THE READ PATH

`view`, `lookup` and `arbitrate` here are single attribute reads, single dict
gets and one delegation. §6.6: *"Both hot paths do an O(1) table lookup, never
math."* §11:595 says it again for the Allocator and Limiter.
`checks/check_ranking_table.py` parses this file's read path and reddens on a
reader that computes — the defect no output assertion can see, because a
recomputed EMA is the *right number*.
"""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import Mapping
from typing import Any

from nixbus.statebus import (
    StateMessage,
    StatePublisher,
    StateSubscriber,
    endpoint_for,
)

from nixscore.seam import (
    RANKING_TOPIC,
    SCORING_WRITER_IDENTITY,
    PairKey,
    RankingMirror,
    RankingPublisher,
    RankingSnapshot,
    RankRow,
    SeamError,
    Verdict,
)

#: The §12.7 endpoint name for this table. One name, derived by both sides, so
#: a writer and a reader cannot be pointed at different sockets by a typo.
RANKING_ENDPOINT_NAME = "ranking"


def ranking_endpoint(root: str | os.PathLike[str] | None = None) -> str:
    """The `ipc://` endpoint the ranking table is published on."""
    return endpoint_for(RANKING_ENDPOINT_NAME, root=root)


@dataclasses.dataclass(frozen=True, slots=True)
class RankingView:
    """One published table, captured whole. **The torn-free multi-row read.**

    A view is produced by `RankingReader.view()` in a single attribute read and
    is immutable afterwards, so every row taken out of one view came from one
    published snapshot. `RankingMirror.lookup` is atomic per row; a *pair* of
    lookups is not, and the difference was measured (see the module docstring).

    `captured_at` is when this table was ACCEPTED by the consumer, not when the
    publisher stamped it — the two differ by transport latency and only the
    first is a fact the consumer observed.
    """

    rows: Mapping[PairKey, RankRow]
    span_days: int
    seq: int
    stamp: float
    captured_at: float

    def lookup(self, strategy_id: str, symbol: str) -> RankRow | None:
        """O(1). One dict get on a table that can no longer change."""
        return self.rows.get((strategy_id, symbol))

    def age_s(self, now: float | None = None) -> float:
        """Seconds since this table was accepted."""
        return max(0.0, (time.time() if now is None else now) - self.captured_at)


@dataclasses.dataclass(frozen=True, slots=True)
class PumpResult:
    """What one `pump()` actually carried. Counters, never a boolean.

    `received` is messages taken off the socket; `accepted` is those that became
    the table. They differ by exactly the refusals, and a caller that can see
    only "no error" cannot tell a healthy quiet bus from a hijacked one.
    """

    received: int
    accepted: int
    foreign: int
    malformed: int
    off_topic: int
    bytes_received: int

    @property
    def carried_nothing(self) -> bool:
        """True when this pump observed no traffic at all (non-vacuity)."""
        return self.received == 0


class RankingWriter:
    """The Scoring process's side: binds the endpoint, owns the table.

    Sole writer **by construction on this side** — the table lives in this
    process's memory and consumers receive copies — and, as measured, sole
    writer **only** because consumers check the identity stamp. `ipc://` bind
    is not exclusive; see the module docstring, fact 1.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        identity: str = SCORING_WRITER_IDENTITY,
        context: Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.identity = identity
        self._state = StatePublisher(endpoint, context=context)
        self._ranking = RankingPublisher(self._state, identity=identity)

    @property
    def published(self) -> int:
        """Tables published so far. The writer's non-vacuity observable."""
        return self._ranking.published

    @property
    def snapshots_served(self) -> int:
        """Snapshot-on-subscribe answers sent (§12.7's mandatory mechanism)."""
        return self._state.snapshots_served

    @property
    def subscribes_seen(self) -> int:
        """Subscriptions this publisher was told about."""
        return self._state.subscribes_seen

    def publish_rows(
        self,
        rows: Mapping[PairKey, RankRow],
        span_days: int,
    ) -> RankingSnapshot:
        """Publish a ranking table. ASYNC — Scoring never waits on a reader.

        Returns the snapshot that went out so the caller can record what it
        published rather than re-deriving it.
        """
        snapshot = RankingSnapshot(
            rows=dict(rows),
            span_days=int(span_days),
            writer_identity=self.identity,
        )
        self._ranking.publish(snapshot)
        return snapshot

    def publish(self, snapshot: RankingSnapshot) -> None:
        """Publish an already-built snapshot. ASYNC, fire-and-forget."""
        self._ranking.publish(snapshot)

    def service(self, timeout_ms: int = 0) -> int:
        """SYNC. Answer pending subscriptions with a full snapshot (§12.7).

        Must be called from the Scoring loop — `StatePublisher.service` is
        documented as loop-called precisely so the owned table is never
        reachable from two threads.
        """
        return self._ranking.service(timeout_ms)

    def close(self) -> None:
        """Release the socket and its private context."""
        self._state.close()


class RankingReader:  # pylint: disable=too-many-instance-attributes
    """A consumer's side: subscriber + private mirror + atomic view.

    The Allocator and the Limiter each hold one. **Single-threaded**: see the
    module docstring. Every read verb below is O(1) and does no arithmetic
    beyond one age subtraction and one float comparison, both inside the frozen
    seam.

    ------------------------------------------------------------------------
    THIS IS THE COLLAPSE OF TWO CLASSES, ARC 037 (CHECK-DEBT D3.271)
    ------------------------------------------------------------------------

    ARC 036 ran five sub-agents in parallel worktrees that could not see each
    other, and two of them invented this class: `nixscore.publisher.RankingReader`
    (sub-agent B, this one) and `nixscore.process.RankingReader` (sub-agent C).
    Two independent classes doing one job — wrap a `StateSubscriber` and the
    frozen `RankingMirror` — which is the duplicate instrument doctrine C.9
    forbids on its own.

    **The measured consequence was worse than the duplication.**
    `check_uncalled_entry_points` resolves a call site by ATTRIBUTE NAME
    (D3.234), and the two classes shared the verbs `arbitrate`, `close` and
    `pump`. `scripts/scoring_kill_drill.py`'s entirely legitimate call to
    `process.RankingReader.pump` was credited to **this** class's `pump`, whose
    only callers were a gate and a test — so a real finding silently stopped
    being one. Renaming either class would have repaired the MEASUREMENT and
    left the duplication, which is why they were collapsed instead.

    **What was kept from the other one, and it is the important half:** `pump`
    polls the socket DIRECTLY rather than calling `StateSubscriber.drain`. See
    `pump`'s own docstring for the measurement (D3.240) — `drain` never polls at
    all for a sub-2 ms budget, and this class used to call it.

    ------------------------------------------------------------------------
    TWO WAYS IN, ONE CLASS
    ------------------------------------------------------------------------

    `source` is either the endpoint string — in which case this reader BUILDS
    and owns its subscriber, which is what a consumer that only wants a ranking
    table needs — or an already-constructed `StateSubscriber`, which is what a
    consumer that owns its own socket (the kill drill, and any consumer holding
    a `zmq.Poller` across several sockets) hands in. `close()` releases the
    socket in both cases: whoever handed it in is handing over its lifetime,
    and a reader that half-owned its transport would be a leak wearing a
    contract.
    """

    def __init__(
        self,
        source: str | StateSubscriber,
        *,
        stale_after_s: float,
        identity: str = SCORING_WRITER_IDENTITY,
        context: Any | None = None,
    ) -> None:
        if isinstance(source, StateSubscriber):
            self._subscriber = source
            self.endpoint = source.endpoint
        else:
            self.endpoint = source
            self._subscriber = StateSubscriber(
                source,
                [RANKING_TOPIC],
                required=[RANKING_TOPIC],
                context=context,
            )
        self._mirror = RankingMirror(stale_after_s=stale_after_s, identity=identity)
        #: The atomically-swapped view. `None` until a snapshot is accepted —
        #: §12.7's *"mirror incomplete => treated as stale"*, spelled as an
        #: absence a caller cannot misread as an empty table.
        self._view: RankingView | None = None
        self._last_seq = -1
        #: Interior sequence holes. NOT the same as the tail truncation a
        #: dropping publisher produces (module docstring, fact 2) — that one is
        #: invisible here by construction and is caught by staleness instead.
        self.gaps_detected = 0
        self.messages_lost = 0
        #: A publisher restart resets its sequence to zero, which arrives as a
        #: regression. Counted, and deliberately NOT a reason to refuse: §12.7's
        #: restart rebuild requires a restarted publisher's snapshot to land.
        self.sequence_regressions = 0
        self.off_topic = 0

    # -- ingress (MUTATES — owner thread only) ---------------------------

    def pump(self, timeout_ms: int = 0) -> PumpResult:
        """Drain the socket into the mirror. Returns what was carried.

        Never blocks past `timeout_ms`. This is the only method that mutates.

        **IT POLLS THE SOCKET DIRECTLY AND DOES NOT CALL `StateSubscriber.drain`,
        AND THAT IS DELIBERATE.** MEASURED, ARC 036 sub-agent C, and carried
        into this class by ARC 037's collapse (CHECK-DEBT D3.240, D3.271):
        `drain` computes its remaining budget as
        `int((deadline - time.monotonic()) * 1000)`, so **any budget under 2 ms
        truncates to `0` on the first pass and the method returns having never
        called `poll`.** A caller asking for one millisecond silently gets
        "never". The first observed symptom was `snapshots_applied = 0` across
        every arm of `scripts/scoring_kill_drill.py` with every socket healthy
        and a real publisher publishing every 50 ms — the mirror reported
        §12.7's never-fed FCFS trigger for a reason that had nothing to do with
        the publisher, which is a transport failure disguised as the safety
        property working.

        `drain` is `scripts/nixbus/statebus.py`, shared transport this module
        does not own, and D3.240 is open against it. Until it is repaired, the
        direct poll below is the behaviour that makes a tight consumer loop —
        the Allocator's and the Limiter's — able to ask for a millisecond and
        get one. `timeout_ms=0` is therefore a genuinely non-blocking sweep:
        take everything the socket already holds and return.

        THE SHAPE THAT MUST NOT COME BACK: replacing this loop with
        `self._subscriber.drain(timeout_ms)` restores the truncation for every
        consumer at once and the symptom is a stale mirror, not an error.
        `scripts/tests/test_ranking_reader_collapse.py` plants exactly that and
        requires it to be caught.
        """
        before = self._counters()
        received = 0
        budget = timeout_ms
        while True:
            message = self._subscriber.poll(budget)
            budget = 0
            if message is None:
                break
            received += 1
            self.ingest(message)
        after = self._counters()
        return PumpResult(
            received=received,
            accepted=after[0] - before[0],
            foreign=after[1] - before[1],
            malformed=after[2] - before[2],
            off_topic=after[3] - before[3],
            bytes_received=self._subscriber.bytes_received,
        )

    def _counters(self) -> tuple[int, int, int, int]:
        return (
            self._mirror.applied,
            self._mirror.foreign_rejected,
            self._mirror.malformed_rejected,
            self.off_topic,
        )

    def ingest(self, message: StateMessage) -> bool:
        """Fold ONE already-received message in. Returns whether it was accepted.

        Public because `pump()` is a convenience, not the only legitimate way
        in: a consumer that owns its own `zmq.Poller` across several sockets
        receives the message itself and hands it here. It is also the seam at
        which this reader can be driven at memory speed, which is what makes
        the concurrency measurement in `checks/check_ranking_table.py` able to
        produce a real read/write overlap rather than a serialised one.

        MUTATES. Owner thread only, like `pump`.
        """
        if message.topic != RANKING_TOPIC:
            self.off_topic += 1
            return False
        self._account_sequence(message.seq)
        if not self._mirror.apply(message):
            return False
        # ONE assignment, and it is the last thing that happens: a reader on
        # another thread that catches this attribute mid-update gets either the
        # whole previous view or the whole new one, never a half-built table.
        self._view = self._build_view(message)
        return True

    def _account_sequence(self, seq: int) -> None:
        """Count holes and restarts. Never decides whether to accept."""
        if self._last_seq >= 0:
            if seq <= self._last_seq:
                self.sequence_regressions += 1
            elif seq > self._last_seq + 1:
                self.gaps_detected += 1
                self.messages_lost += seq - self._last_seq - 1
        self._last_seq = max(self._last_seq, seq)

    def _build_view(self, message: StateMessage) -> RankingView | None:
        """Decode the accepted message into an immutable view, or keep the old.

        The mirror already accepted this payload, so `from_wire` cannot fail
        here — but it is guarded anyway, because "cannot fail" is the sentence
        that precedes an un-handled exception on a consumer's ingest path.
        """
        try:
            snapshot = RankingSnapshot.from_wire(message.payload)
        except SeamError:
            return self._view
        return RankingView(
            rows=dict(snapshot.rows),
            span_days=snapshot.span_days,
            seq=message.seq,
            stamp=message.stamp,
            captured_at=time.time(),
        )

    # -- read contract (O(1), NO MATH) -----------------------------------

    def view(self) -> RankingView | None:
        """THE COHERENT READ. One attribute read; `None` until a snapshot lands."""
        return self._view

    def lookup(self, strategy_id: str, symbol: str) -> RankRow | None:
        """THE HOT-PATH READ. One dict get inside the frozen mirror."""
        return self._mirror.lookup(strategy_id, symbol)

    def arbitrate(
        self,
        first: PairKey,
        second: PairKey,
        now: float | None = None,
    ) -> Verdict:
        """Delegate to the frozen seam. Never blocks, never raises, never math."""
        return self._mirror.arbitrate(first, second, now)

    # -- observables ------------------------------------------------------

    @property
    def mirror(self) -> RankingMirror:
        """The frozen mirror itself, for callers that need its own counters."""
        return self._mirror

    @property
    def applied(self) -> int:
        """Snapshots accepted into the table. The reader's non-vacuity observable."""
        return self._mirror.applied

    @property
    def foreign_rejected(self) -> int:
        """Snapshots refused on the identity stamp. **Sole-writer enforcement.**"""
        return self._mirror.foreign_rejected

    @property
    def malformed_rejected(self) -> int:
        """Payloads that were not a ranking table."""
        return self._mirror.malformed_rejected

    @property
    def bytes_received(self) -> int:
        """Wire bytes taken off the socket. The non-vacuity observable."""
        return self._subscriber.bytes_received

    @property
    def stale(self) -> bool:
        """§12.7's fast-drop condition. Never fed ⇒ stale."""
        return not self._mirror.fresh()

    def fresh(self, now: float | None = None) -> bool:
        """Whether the table is inside its freshness threshold."""
        return self._mirror.fresh(now)

    def age_s(self, now: float | None = None) -> float | None:
        """Seconds since the last accepted snapshot, or `None` if never fed."""
        return self._mirror.age_s(now)

    def close(self) -> None:
        """Release the socket and its private context."""
        self._subscriber.close()
