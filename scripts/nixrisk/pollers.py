"""§6.4's two pollers — the PRODUCERS behind the freshness detector.

ARC 033 / Stage 1 / C. §6.4's first bullet, verbatim: *"**Margin poller** (fast,
seconds) -> margin cache. **Calendar poller** (slow, minutes) -> per-symbol
window set (sessions, econ events, **roll schedule**, holidays/half-days). Both
on shared pool."* Phase 0.4 declared `MarginPollerPort` and `CalendarPollerPort`
in `calendar_seam.py` and implemented neither. This module implements both, and
the caches they own, and nothing else.

`MarginPoller` satisfies `MarginPollerPort` **and** `MarginBaselineReadPort`;
`CalendarPoller` satisfies `CalendarPollerPort` **and** `WindowSetReadPort`. One
object per cache is the §12.7 mirror model applied literally: *"Each owning
process ... holds the real table in its own memory and publishes an atomic
snapshot outward."* The owner and the read port are the same object because
there is exactly one writer, and splitting them would create a second name that
could be handed a second writer.

---

## THE §6.4 v1.3 LOCK: THERE IS NO MARGIN TABLE HERE, AND THAT IS THE DESIGN

§6.4's locked v1.3 paragraph: *"live current margin per symbol is **NOT a
separate table or its own shared-memory block.** broker-order brings it in; the
Limiter folds it into the **one unified financial-picture snapshot** ... under
one writer and one version stamp"*, with the reason stated in the same
paragraph: *"independent tables tick on independent clocks, so a sizing pass
could read fresh margin against slightly stale balance — cross-table skew, the
same split-brain we removed for balance, reintroduced at a new seam."*

So `MarginPoller`'s cache holds **`MarginBaseline` rows and nothing else** —
§6.3's accepted baseline level, the figure a trailing edge waits to return to
and a stable-elevated regime shift re-accepts. `calendar_seam.py` already drew
that line and this module stays on its side of it. The LIVE per-symbol figure
is `FinancialPicture.margin_per_contract`, it arrives via broker-order, the
Limiter writes it, and **this module never reads it, never holds it, and never
publishes it.** `check_pollers` measures that as an AST property over these
bytes rather than trusting the paragraph: an attribute access naming the live
field anywhere in this file is a FAIL.

The temptation this closes is concrete. A "fast, seconds" margin poller is
exactly where a live per-symbol margin figure wants to live, and a poller that
cached one would look correct, pass its own tests, and reintroduce the
cross-table skew §6.4 spent a paragraph removing — at a seam nobody was
watching, because it would be inside the object the spec asked for.

---

## PUSH-PREFERRED (§6.4) — A DEMOTION IS A CHANGE IN BEHAVIOUR, NOT A LABEL

§6.4: *"if Tradovate's user-sync websocket delivers account/margin/position
events, event-driven updates are primary and polling demotes to fallback/audit
(CC-verify)."*

`PushDemotion` carries that as state with three constraints that make the
demotion real:

* `audit_interval_ms` **must be strictly greater than** `poll_interval_ms`, and
  the constructor refuses otherwise. A "demotion" that polls at the same
  cadence has demoted nothing; it has renamed something. That is the whole
  difference between implementing this clause and gesturing at it.
* the demotion is **time-bounded by the pushes themselves**: `mode()` reports
  `FALLBACK_AUDIT` only while a push has arrived within `push_idle_ms`. When
  the websocket dies, no explicit failover event is needed and none is waited
  for — the poller re-promotes to `PRIMARY` by the absence of pushes, which is
  the only signal a dead socket reliably sends. §6.4 calls polling the
  FALLBACK, and a fallback that needs to be told to take over is not one.
* polling **does not stop** when demoted. §6.4 says fallback/audit, and audit is
  the second word: the poll keeps running at the wider cadence, its readings go
  through the same §6.4b guard as the pushes, and a poll that lands behind a
  fresher push is DISCARDED rather than merged — §6.4b's own parenthetical,
  *"a slow poll landing after a fresher push is dropped, not applied."* The
  audit is therefore free: the guard's `discarded_older` counter is the audit
  agreeing, and an ADMITTED poll while pushes are live is the audit finding the
  push feed behind.

---

## SYNCHRONOUS OR ASYNCHRONOUS — `calendar_seam.py` DECLARED IT; THIS HONOURS IT

The seam gave each verb its own reason and this module implements them, rather
than choosing again:

* **`MarginPoller.poll_once` — async for CONTAINMENT.** *"A hung broker socket
  must cost one suspended coroutine and not one blocked pool worker."* The
  venue call is `await`ed and there is no blocking call anywhere on its path;
  `check_pollers` hangs a fetch forever and measures that the calendar refresh
  sharing the loop still completes.
* **`CalendarPoller.refresh` — async for DURATION, which is not the same
  argument.** *"Async here buys cooperative yielding during a long rebuild so a
  slow calendar refresh cannot starve the fast margin poll sharing the pool."*
  So `refresh` yields **once per symbol** — the yield is inside the rebuild
  loop, not around it, because a coroutine that awaits only at its start and
  its end is a blocking function with `async` written on it.
* **both `publish` verbs — synchronous, for §12.7.** *"The verb returns when
  the bytes are consistent, or it is not a publish."* Each publish is a single
  rebind of one attribute to an already-built immutable tuple, so a reader is
  holding either the whole old snapshot or the whole new one — the same
  single-cell argument `nixalloc/mirror.py` makes on the consumer side.

## §10 — BOTH ON THE SHARED POOL

§10 puts pollers on cores 4-5 with Postgres, backfill, logging, the ZMQ proxy,
dashboards, health, the Sentinel and Scoring. `run` on each poller is a
cooperative loop, so both live on one event loop on that pool rather than
taking a thread each. The cadence split §6.4 states — seconds against minutes —
is the reason they can share: the calendar's yield-per-symbol is what keeps the
margin poll's cadence a property of its own interval rather than of the
calendar's size.

## WHAT IS NOT HERE

* **The staleness RULE.** `freshness.py` owns it, and the dependency runs one
  way: this module imports it and it does not import this one. Its docstring
  gives the reason (fail-closed detection must not depend on the machinery it
  watches) and `check_staleness` measures the direction.
* **The HALT state machine.** §6.4 splits it: *"Detection = system; execution =
  Limiter."* These pollers and `freshness.py` produce the CONDITION;
  `nixrisk/flatten.py` owns the flatten and the HALT semantics of §12.5 are
  owned elsewhere. Nothing in this module fires an exit.
* **The window GENERATOR.** `CalendarPoller` takes a `WindowSourcePort` — the
  seam's single declared home for §12.3's exchange-local -> UTC conversion,
  *"exactly once at window generation"*. Building windows here would be that
  conversion in a second place.
* **Vendor transport.** `fetch` and the window source are injected callables.
  §2A's vendor library is not this module's, and a poller that dialled a broker
  directly would be untestable and would put vendor code on core 4-5's pool
  behind an interface nobody declared.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from nixrisk.calendar_seam import (
    CacheState,
    FreshnessStamp,
    MarginBaseline,
    Window,
    WindowSet,
)
from nixrisk.freshness import FreshnessTracker, StalenessUsageError

__all__ = [
    "CALENDAR_FEED",
    "MARGIN_FEED",
    "CalendarPoller",
    "MarginPoller",
    "PollerMode",
    "PollerUsageError",
    "PushDemotion",
    "StampedBaseline",
    "StampedWindowSet",
]

#: The §12A knob names these pollers answer to, with the `_stale_ms` suffix
#: stripped exactly as `freshness.StalenessPolicy` strips it. Written here as
#: the feed IDENTITY the stamps carry; the THRESHOLD is never written here.
MARGIN_FEED = "margin"
CALENDAR_FEED = "calendar"


class PollerUsageError(StalenessUsageError):
    """A poller was constructed or driven wrongly. Never degraded to a default."""


class PollerMode(enum.Enum):
    """§6.4's push-preferred clause as two states.

    `PRIMARY` — polling is the source of record.
    `FALLBACK_AUDIT` — the venue's push feed is delivering, so polling has
    demoted: wider cadence, same guard, and its readings audit the push feed
    rather than lead it.
    """

    PRIMARY = "primary"
    FALLBACK_AUDIT = "fallback_audit"


class PushDemotion:  # pylint: disable=too-many-instance-attributes
    # Over pylint's seven because of the COUNTERS, for the reason
    # `nixalloc.mirror.AllocatorMirror` records for its five: a producer
    # that cannot say what it polled, published, audited and discarded can
    # only be believed. Removing a counter to satisfy a shape heuristic
    # would remove the evidence this module is measured by.
    """§6.4's push-preferred state. Shared by both pollers, owned by neither.

    Composed rather than inherited: the two pollers have different cadences,
    different caches and different reasons for being async, and the ONE thing
    they share is this clause. A base class would have carried the rest along
    with it.
    """

    def __init__(
        self,
        *,
        poll_interval_ms: float,
        audit_interval_ms: float,
        push_idle_ms: float,
        clock: Callable[[], datetime],
    ) -> None:
        if poll_interval_ms <= 0:
            raise PollerUsageError(
                f"poll_interval_ms={poll_interval_ms!r} must be positive — a "
                "poller with no interval is a busy loop on the shared pool (§10)"
            )
        if audit_interval_ms <= poll_interval_ms:
            raise PollerUsageError(
                f"audit_interval_ms={audit_interval_ms!r} is not greater than "
                f"poll_interval_ms={poll_interval_ms!r}. §6.4 demotes polling to "
                "fallback/audit when pushes arrive; a demotion that polls at the "
                "same cadence has changed a NAME and not a behaviour"
            )
        if push_idle_ms <= 0:
            raise PollerUsageError(
                f"push_idle_ms={push_idle_ms!r} must be positive — with no idle "
                "window a single push would demote the poller forever, and a "
                "dead websocket sends no event to promote it back"
            )
        self._poll_interval_ms = float(poll_interval_ms)
        self._audit_interval_ms = float(audit_interval_ms)
        self._push_idle_ms = float(push_idle_ms)
        self._clock = clock
        self._last_push: datetime | None = None
        self.pushes = 0
        self.demotions = 0
        self.promotions = 0
        #: ARC 034 (D3.194). Pushes SEEN and REFUSED, kept apart from `pushes`
        #: so the demotion state can be read against what actually moved it.
        #: A refusal that only shrank a number would be indistinguishable from
        #: a push that never arrived.
        self.rejected_future = 0
        self.rejected_regressive = 0
        self._mode = PollerMode.PRIMARY

    @property
    def last_push(self) -> datetime | None:
        """When the most recent push was noted (UTC), or `None`."""
        return self._last_push

    def note_push(self, at: datetime) -> None:
        """Record that the venue's push feed delivered. May demote.

        **MONOTONIC AND CLOCK-BOUNDED. ARC 034 (D3.194), and this used to be a
        single unconditional assignment.**

        `_last_push` is the ONLY thing standing between a dead websocket and a
        poller that keeps auditing at the wide cadence, so a stamp this method
        accepts is a safety decision, not bookkeeping. Two ways a venue stamp
        breaks the clause, both measured against the shipped code:

        * **A FUTURE stamp pins the demotion.** `_settle` demotes while the
          push is younger than `push_idle_ms`; one push stamped a day ahead
          therefore holds `FALLBACK_AUDIT` through a day of total websocket
          silence. Measured on the shipped module: 0 h, 1 h, 6 h and 24 h of
          silence after a single `now + 240 h` push all still read
          `FALLBACK_AUDIT`. A stamp the local clock says has not happened yet
          is REFUSED — the poller stays `PRIMARY`, which is the direction §6.4
          fails in, because polling IS the fallback.
        * **A REGRESSIVE stamp re-promotes a live demotion.** Assigning
          unconditionally let a late-arriving push carrying an OLD instant move
          `_last_push` backwards, which widens `idle_ms` and promotes a poller
          whose push feed is in fact healthy. §6.4b already states the rule for
          venue-sourced values — *"the Limiter accepts a new value for a given
          key ONLY if it is newer than the one it holds"* — and this is that
          rule applied to the push CLOCK rather than to the push PAYLOAD. The
          reading itself is not dropped by this method; `on_push` still hands
          the rows to the §6.4b guard, which decides the payload's fate on its
          own terms.

        Both refusals are COUNTED rather than silent, and `pushes` still counts
        the arrival, because *"a push arrived and was refused"* and *"no push
        arrived"* are different states of the world and a poller that could not
        tell them apart could only be believed.

        A naive `at` is refused loudly rather than compared: the subtraction in
        `_settle` would raise `TypeError` several frames away from the caller
        that supplied it, and §12.3 makes UTC the invariant.
        """
        now = self._clock()
        if at.tzinfo is None or at.utcoffset() is None:
            raise PollerUsageError(
                f"push stamp {at!r} is naive — §12.3 puts every instant on the "
                "UTC timeline, and a naive stamp compared against an aware "
                "clock raises three frames from the venue that sent it"
            )
        self.pushes += 1
        if at > now:
            # Fail CLOSED: refusing to record leaves the poller PRIMARY, which
            # polls MORE often. Accepting would demote on the strength of an
            # instant the local clock says has not happened.
            self.rejected_future += 1
        elif self._last_push is not None and at < self._last_push:
            self.rejected_regressive += 1
        else:
            self._last_push = at
        self._settle()

    def mode(self) -> PollerMode:
        """The CURRENT mode, recomputed against the clock on every read.

        Recomputed rather than stored-and-trusted because the promotion back to
        `PRIMARY` is triggered by an ABSENCE — no event ever arrives to announce
        that the websocket died, so a mode that only changed on an event would
        stay demoted through the outage it exists to survive.
        """
        self._settle()
        return self._mode

    def interval_ms(self) -> float:
        """The cadence for the CURRENT mode — the demotion made physical."""
        if self.mode() is PollerMode.FALLBACK_AUDIT:
            return self._audit_interval_ms
        return self._poll_interval_ms

    def _settle(self) -> None:
        wanted = PollerMode.PRIMARY
        if self._last_push is not None:
            idle_ms = (self._clock() - self._last_push).total_seconds() * 1000.0
            # ARC 034 (D3.194): the LOWER bound is not decoration. `idle_ms` is
            # signed, and a negative value means the last push is in the FUTURE
            # of the clock reading it — which `note_push` now refuses at the
            # door, but which a backwards clock step can still produce after
            # the fact. A bare `idle_ms <= push_idle_ms` reads every negative
            # value as *"a push just arrived"* and demotes on a clock jump.
            if 0.0 <= idle_ms <= self._push_idle_ms:
                wanted = PollerMode.FALLBACK_AUDIT
        if wanted is self._mode:
            return
        if wanted is PollerMode.FALLBACK_AUDIT:
            self.demotions += 1
        else:
            self.promotions += 1
        self._mode = wanted


# ---------------------------------------------------------------------------
# What a venue round-trip returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StampedBaseline:
    """One §6.3 baseline row with the venue stamp §6.4b orders it by.

    The stamp is PER ROW, not per round-trip, because §6.4b's guard is *"per
    key (per symbol for margin ...) so a late update on one key can never
    regress another"*. One stamp for a whole reading would make a symbol the
    venue did not refresh look as fresh as one it did.
    """

    baseline: MarginBaseline
    stamp: FreshnessStamp


@dataclass(frozen=True)
class StampedWindowSet:
    """One symbol's window set with the stamp of the calendar data behind it."""

    window_set: WindowSet
    stamp: FreshnessStamp


# ---------------------------------------------------------------------------
# The margin poller (§6.4 fast; §6.3 BASELINE cache — see the docstring's lock)
# ---------------------------------------------------------------------------


class MarginPoller:  # pylint: disable=too-many-instance-attributes
    # Over pylint's seven because of the COUNTERS, for the reason
    # `nixalloc.mirror.AllocatorMirror` records for its five: a producer
    # that cannot say what it polled, published, audited and discarded can
    # only be believed. Removing a counter to satisfy a shape heuristic
    # would remove the evidence this module is measured by.
    """§6.4's fast margin poller. Owns the §6.3 baseline cache; publishes it.

    Satisfies `calendar_seam.MarginPollerPort` and
    `calendar_seam.MarginBaselineReadPort`.
    """

    def __init__(
        self,
        *,
        fetch: Callable[[], Awaitable[Sequence[StampedBaseline]]],
        tracker: FreshnessTracker,
        demotion: PushDemotion,
        sink: Callable[[tuple[MarginBaseline, ...]], None] | None = None,
    ) -> None:
        self._fetch = fetch
        self._tracker = tracker
        self._demotion = demotion
        self._sink = sink
        #: THE single mutable cell a reader loads (§12.7, and the same argument
        #: `nixalloc.mirror.AllocatorMirror` makes for `_cell`). Rebound whole
        #: by `publish`; never mutated in place.
        self._published: tuple[MarginBaseline, ...] = ()
        self._index: dict[str, MarginBaseline] = {}
        self.polls = 0
        self.audit_polls = 0
        self.pushes_applied = 0
        self.publishes = 0

    # -- MarginPollerPort ---------------------------------------------------

    async def poll_once(self) -> FreshnessStamp:
        """One venue round-trip. ASYNCHRONOUS — containment (see the docstring).

        Everything on this path either awaits or is arithmetic. There is no
        blocking call, no `time.sleep`, and no synchronous socket: a venue that
        never answers suspends this coroutine and costs the shared pool
        nothing else.
        """
        self.polls += 1
        if self._demotion.mode() is PollerMode.FALLBACK_AUDIT:
            self.audit_polls += 1
        rows = await self._fetch()
        return self._apply(rows)

    def publish(self, baselines: tuple[MarginBaseline, ...]) -> None:
        """Publish an ATOMIC snapshot (§12.7). SYNCHRONOUS.

        The tuple is built by the caller and installed by ONE rebind, so a
        concurrent reader holds either the whole previous snapshot or the whole
        new one. There is no window in which the index and the published tuple
        disagree, because the index is rebuilt into a fresh dict first and
        swapped in the same way.
        """
        snapshot = tuple(baselines)
        index = {row.symbol: row for row in snapshot}
        self._index = index
        self._published = snapshot
        self.publishes += 1
        if self._sink is not None:
            self._sink(snapshot)

    # -- push-preferred -----------------------------------------------------

    def on_push(self, rows: Sequence[StampedBaseline], at: datetime) -> int:
        """Apply a venue push and DEMOTE polling to fallback/audit (§6.4).

        Returns the number of rows admitted. Rows go through the SAME §6.4b
        guard as polled ones, so a push carrying an older instant than the cache
        holds is discarded exactly as a late poll would be — the guard is about
        source time, not about which door the reading came through.
        """
        self._demotion.note_push(at)
        before = self._tracker.guard.admitted
        self._apply(rows)
        applied = self._tracker.guard.admitted - before
        self.pushes_applied += applied
        return applied

    @property
    def mode(self) -> PollerMode:
        """§6.4's push-preferred mode, recomputed against the clock."""
        return self._demotion.mode()

    # -- MarginBaselineReadPort --------------------------------------------

    def baseline(self, symbol: str) -> MarginBaseline | None:
        """The accepted §6.3 baseline for `symbol`, or `None`. O(1)."""
        return self._index.get(symbol)

    def published(self) -> tuple[MarginBaseline, ...]:
        """The whole published snapshot — one attribute load."""
        return self._published

    def state(self) -> CacheState:
        """EMPTY / FRESH / STALE for the cache AS A WHOLE.

        The whole is as stale as its STALEST key, not as fresh as its freshest:
        §6.4b's guard is per key precisely because one live symbol says nothing
        about four dead ones, and a cache-level verdict taken from the best key
        would let one lively feed mask the rest.
        """
        if not self._published:
            return CacheState.EMPTY
        states = {
            self._tracker.reading(MARGIN_FEED, row.symbol).state
            for row in self._published
        }
        if CacheState.EMPTY in states:
            return CacheState.EMPTY
        if CacheState.STALE in states:
            return CacheState.STALE
        return CacheState.FRESH

    def freshness(self) -> FreshnessStamp | None:
        """The OLDEST stamp held across symbols. `None` before first publish.

        Oldest, for `state`'s reason: a cache-level freshness taken from the
        newest key is a number that cannot go stale while any one symbol is
        being updated.
        """
        return _oldest_stamp(
            self._tracker, MARGIN_FEED, [r.symbol for r in self._published]
        )

    # -- the shared-pool loop (§10) ----------------------------------------

    async def run(self, *, stop: asyncio.Event, max_cycles: int | None = None) -> int:
        """Poll at the CURRENT mode's cadence until `stop`. Returns cycles run.

        `max_cycles` exists so a measurement can bound the loop without racing
        a timer; there is no other caller and no default that runs forever
        silently.
        """
        return await _run_loop(
            body=self.poll_once,
            interval_ms=self._demotion.interval_ms,
            stop=stop,
            max_cycles=max_cycles,
        )

    # -- internals ----------------------------------------------------------

    def _apply(self, rows: Sequence[StampedBaseline]) -> FreshnessStamp:
        """Guard every row, fold the admitted ones in, publish once."""
        if not rows:
            raise PollerUsageError(
                "a margin reading carried NO rows. An empty reading is "
                "indistinguishable from a healthy quiet one once it is folded "
                "in, and §6.4 makes silence a halt condition — the producer "
                "must say so loudly rather than publish nothing"
            )
        merged = dict(self._index)
        newest: FreshnessStamp | None = None
        for row in rows:
            if row.stamp.feed != MARGIN_FEED:
                raise PollerUsageError(
                    f"margin row for {row.baseline.symbol!r} carries feed "
                    f"{row.stamp.feed!r}; the §12A knob this poller is judged "
                    f"against is {MARGIN_FEED!r}"
                )
            if self._tracker.observe(row.stamp, row.baseline.symbol):
                merged[row.baseline.symbol] = row.baseline
            if newest is None or row.stamp.as_of > newest.as_of:
                newest = row.stamp
        self.publish(tuple(merged[key] for key in sorted(merged)))
        assert newest is not None  # nosec B101 - `rows` is non-empty above
        return newest


# ---------------------------------------------------------------------------
# The calendar poller (§6.4 slow) — per-symbol window sets
# ---------------------------------------------------------------------------


class CalendarPoller:  # pylint: disable=too-many-instance-attributes
    # Over pylint's seven because of the COUNTERS, for the reason
    # `nixalloc.mirror.AllocatorMirror` records for its five: a producer
    # that cannot say what it polled, published, audited and discarded can
    # only be believed. Removing a counter to satisfy a shape heuristic
    # would remove the evidence this module is measured by.
    """§6.4's slow calendar poller. Owns the per-symbol window set; publishes it.

    Satisfies `calendar_seam.CalendarPollerPort` and
    `calendar_seam.WindowSetReadPort`.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        symbols: Sequence[str],
        build: Callable[[str], tuple[Window, ...]],
        stamp_for: Callable[[str], FreshnessStamp],
        tracker: FreshnessTracker,
        clock: Callable[[], datetime],
        demotion: PushDemotion,
        sink: Callable[[tuple[WindowSet, ...]], None] | None = None,
    ) -> None:
        if not symbols:
            raise PollerUsageError(
                "a calendar poller over NO symbols publishes an empty window "
                "set, and an empty window set reads exactly like a clear one to "
                "§6.5's `now in any window` rule"
            )
        self._symbols = tuple(symbols)
        self._build = build
        self._stamp_for = stamp_for
        self._tracker = tracker
        self._clock = clock
        self._demotion = demotion
        self._sink = sink
        self._published: tuple[WindowSet, ...] = ()
        self._index: dict[str, WindowSet] = {}
        self.refreshes = 0
        self.publishes = 0
        self.yields = 0

    # -- CalendarPollerPort -------------------------------------------------

    async def refresh(self) -> FreshnessStamp:
        """Rebuild every symbol's window set. ASYNCHRONOUS — DURATION.

        The `await` is INSIDE the per-symbol loop, not around it. That is the
        whole of `calendar_seam.py`'s duration argument made physical: a bulk
        rebuild that suspends only at its edges cannot let the fast margin poll
        in, however long it takes, and `check_pollers` measures the interleaving
        rather than reading this sentence.
        """
        self.refreshes += 1
        stamped: list[StampedWindowSet] = []
        for symbol in self._symbols:
            await asyncio.sleep(0)
            self.yields += 1
            stamp = self._stamp_for(symbol)
            if stamp.feed != CALENDAR_FEED:
                raise PollerUsageError(
                    f"calendar stamp for {symbol!r} carries feed "
                    f"{stamp.feed!r}; the §12A knob this poller is judged "
                    f"against is {CALENDAR_FEED!r}"
                )
            stamped.append(
                StampedWindowSet(
                    window_set=WindowSet(
                        symbol=symbol,
                        windows=tuple(self._build(symbol)),
                        generated_at=self._clock(),
                    ),
                    stamp=stamp,
                )
            )
        return self._apply(stamped)

    def publish(self, sets: tuple[WindowSet, ...]) -> None:
        """Publish an ATOMIC snapshot (§12.7). SYNCHRONOUS. One rebind."""
        snapshot = tuple(sets)
        self._index = {row.symbol: row for row in snapshot}
        self._published = snapshot
        self.publishes += 1
        if self._sink is not None:
            self._sink(snapshot)

    def on_push(self, rows: Sequence[StampedWindowSet], at: datetime) -> int:
        """Apply a venue/vendor push and demote polling to fallback/audit."""
        self._demotion.note_push(at)
        before = self._tracker.guard.admitted
        self._apply(rows)
        return self._tracker.guard.admitted - before

    @property
    def mode(self) -> PollerMode:
        """§6.4's push-preferred mode, recomputed against the clock."""
        return self._demotion.mode()

    # -- WindowSetReadPort --------------------------------------------------

    def windows(self, symbol: str) -> WindowSet | None:
        """The symbol's current window set, or `None` if none is held. O(1)."""
        return self._index.get(symbol)

    def published(self) -> tuple[WindowSet, ...]:
        """The whole published snapshot — one attribute load."""
        return self._published

    def state(self) -> CacheState:
        """EMPTY / FRESH / STALE for the cache as a whole. Stalest key wins."""
        if not self._published:
            return CacheState.EMPTY
        states = {
            self._tracker.reading(CALENDAR_FEED, row.symbol).state
            for row in self._published
        }
        if CacheState.EMPTY in states:
            return CacheState.EMPTY
        if CacheState.STALE in states:
            return CacheState.STALE
        return CacheState.FRESH

    def freshness(self) -> FreshnessStamp | None:
        """The OLDEST stamp held across symbols. `None` before first publish."""
        return _oldest_stamp(
            self._tracker, CALENDAR_FEED, [r.symbol for r in self._published]
        )

    # -- the shared-pool loop (§10) ----------------------------------------

    async def run(self, *, stop: asyncio.Event, max_cycles: int | None = None) -> int:
        """Refresh at the CURRENT mode's cadence until `stop`. Returns cycles."""
        return await _run_loop(
            body=self.refresh,
            interval_ms=self._demotion.interval_ms,
            stop=stop,
            max_cycles=max_cycles,
        )

    # -- internals ----------------------------------------------------------

    def _apply(self, rows: Sequence[StampedWindowSet]) -> FreshnessStamp:
        merged = dict(self._index)
        newest: FreshnessStamp | None = None
        for row in rows:
            if self._tracker.observe(row.stamp, row.window_set.symbol):
                merged[row.window_set.symbol] = row.window_set
            if newest is None or row.stamp.as_of > newest.as_of:
                newest = row.stamp
        if newest is None:
            raise PollerUsageError(
                "a calendar reading carried NO symbols — see MarginPoller._apply"
            )
        self.publish(tuple(merged[key] for key in sorted(merged)))
        return newest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _oldest_stamp(
    tracker: FreshnessTracker, feed: str, symbols: Sequence[str]
) -> FreshnessStamp | None:
    """The oldest stamp held for `feed` across `symbols`, or `None`."""
    stamps = [
        stamp
        for stamp in (tracker.held(feed, symbol) for symbol in symbols)
        if stamp is not None
    ]
    if not stamps:
        return None
    return min(stamps, key=lambda stamp: stamp.as_of)


async def _run_loop(
    *,
    body: Callable[[], Awaitable[FreshnessStamp]],
    interval_ms: Callable[[], float],
    stop: asyncio.Event,
    max_cycles: int | None,
) -> int:
    """One cooperative poller loop on the §10 shared pool. Returns cycles run.

    `interval_ms` is a CALLABLE, read once per cycle, so a push-preferred
    demotion takes effect on the next sleep rather than at the next restart —
    a cadence captured at construction would make §6.4's demotion a boot-time
    decision.
    """
    cycles = 0
    while not stop.is_set():
        if max_cycles is not None and cycles >= max_cycles:
            return cycles
        await body()
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return cycles
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_ms() / 1000.0)
        except TimeoutError:
            continue
    return cycles


#: Read by `check_pollers` off these bytes: the live per-symbol margin field is
#: the LIMITER's, folded into the one financial-picture snapshot (§6.4 v1.3
#: lock). No expression in this module may name it. Declared as data so the gate
#: does not carry a literal the module could drift away from.
LIVE_MARGIN_FIELD = "margin_per_contract"

#: The (class, port) pairs this module claims to satisfy. `check_pollers`
#: resolves both sides and runs `isinstance` against the seam's
#: `runtime_checkable` Protocols, so the claim is measured, not declared.
PORT_IMPLEMENTATIONS: tuple[tuple[str, str], ...] = (
    ("MarginPoller", "MarginPollerPort"),
    ("MarginPoller", "MarginBaselineReadPort"),
    ("CalendarPoller", "CalendarPollerPort"),
    ("CalendarPoller", "WindowSetReadPort"),
)
