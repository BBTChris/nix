"""The freshness DETECTOR — §6.4's stale condition and §12.3's clock-integrity
condition, produced as the two flag ports `nixrisk/gate.py` already consumes.

ARC 033 / Stage 1 / C. `nixrisk/gate.py` has assembled
`SymbolFlagRule("data_staleness", ...)` and `GlobalFlagRule("clock_skew", ...)`
since ARC 028, and `risks/staleness.config.json` has held every §12A threshold
as data since then. **Neither port had an implementation anywhere in the tree.**
This module is that implementation, and it is the whole of it: the rules are
not touched, the manifest is not touched, and `gate.py` is not edited by this
arc at all. `StalenessFlagPort` structurally satisfies `gate.SymbolFlagPort`
and `ClockSkewFlagPort` structurally satisfies `gate.GlobalFlagPort` — both are
`runtime_checkable` Protocols, so the connection is measurable rather than
asserted, and `checks/check_staleness.py` measures it.

---

## WHY THIS IS A SEPARATE MODULE FROM `pollers.py`, AND NOT A SECTION OF IT

`calendar_seam.py` declares `WindowSetReadPort.freshness` synchronous with the
reason **SELF-REFERENCE**: *"the condition being detected is 'the thing that
refreshes this cache stopped making progress' ... an awaitable staleness read
cannot report the outage that prevents it from returning. Fail-closed detection
must not depend on the machinery it is watching."*

That argument does not stop at `async`. A detector that lives inside the poller
object is reachable only through the object whose stall it exists to detect: a
poller that has wedged, thrown, or never been constructed takes its own stale
alarm down with it. So the detector holds the stamps and the clock, the poller
hands it observations, and the detector answers with nothing of the poller's in
its call path. Everything in this module is pure: a clock, a mapping, and
arithmetic. There is no I/O, no `async`, no task, and no import of `pollers`.

The dependency runs one way — `pollers` imports `freshness`, never the reverse
— and `check_staleness` measures that direction on the shipped bytes, because
the argument above is worth exactly as much as its enforcement.

---

## THE MEASURE IS TIME SINCE THE **LAST ARRIVAL**. NOT A COUNT. NOT A MEAN.

This is the defect ARC 022 F17 shipped, and it is the reason this module exists
in the shape it does. F17 decided "stale" from a **session mean** — and the
mean agreed while the last packets were 900 seconds out. *The mean was fine and
the data was dead.* A mean over a session is dominated by the session; a feed
that delivered briskly for six hours and then stopped has a healthy mean for a
long time after it died.

Two counter-examples, and a detector has to get **both** right:

* **BRISK-THEN-DEAD.** Hundreds of arrivals at a tight cadence, then nothing
  for 900 s. Mean interval: small. Count in the session: large. **Truth:
  STALE.** A mean-based or count-based detector says FRESH. This is F17.
* **SPARSE-BUT-CURRENT.** A long historical gap, then an arrival 100 ms ago.
  Mean interval: enormous. Count in the session: tiny. **Truth: FRESH.** A
  mean-based detector says STALE, and a count-based one halts a healthy feed.

`FeedFreshness.age_ms` is `now - held.as_of` and nothing else. No window, no
sample, no aggregate — there is no code path in this module that can see a
second arrival, which is why neither counter-example can be got wrong here.
`check_staleness` drives both, and it drives a mean-based comparator alongside
to show it inverting on both, so the claim is a measurement rather than a
paragraph.

---

## `as_of` IS THE SOURCE'S INSTANT, NOT ARRIVAL TIME (§6.4b)

`FreshnessStamp.as_of` is the venue's own instant. §6.4b: *"Ordering is by
source-of-truth time, never by arrival time."* Two consequences that are easy
to get backwards:

1. **Age is measured against the source stamp.** A reading that took two
   seconds to arrive is two seconds old on arrival, and that is correct: the
   quantity §6.4 bounds is how old the DATA is, not how recently a socket was
   touched. A transport that buffers cannot launder age.
2. **A source stamp AHEAD of the local clock is a defect, not freshness.** A
   future-dated stamp yields a negative age and would read as eternally fresh
   — a feed that could never go stale, which is exactly the safety property
   inverted. Beyond `CLOCK_SKEW_MAX_MS` of lead (the one knob §12A already
   gives for local-vs-source disagreement — no new tunable is invented here) it
   is reported STALE with a reason that says *ahead*, so an operator is not
   sent looking for a dead feed when the real fault is a clock.

---

## §6.4's "AFTER RETRY/BACKOFF" — WHERE THE LADDER SITS

§6.4 declares a feed stale *"(freshness stamp past threshold, after
retry/backoff)"*. The spec does not say whether the ladder runs before or after
the threshold is crossed, and `risks/staleness.config.json` records that
ambiguity honestly rather than resolving it by preference. This module places
the ladder **after** the crossing and calls the sum the DEADLINE:

    deadline_ms(feed) = threshold_ms(feed) + retry.total_ms

* Past `threshold_ms` the feed is `CacheState.STALE` — the observation is true
  and is reported as such.
* It does not BLOCK until `deadline_ms`, because §6.4 puts halt-and-flatten
  behind the retries and a halt that fires before them would make the retry
  policy decorative.

The two are deliberately different questions on the same reading, and both are
on `FreshnessReading`: `state` is what the cache IS, `blocked` is what the gate
DOES. Collapsing them would mean either halting during the retries or never
being able to say a cache went stale and came back.

`risk_config._retry_ladder_fits_smallest_threshold` already boot-validates that
`retry.total_ms` is shorter than the tightest threshold, so the deadline can
never be more than double the threshold an operator configured.

---

## STALE-UNTIL-PROVEN-FRESH — `EMPTY` BLOCKS

`CacheState.EMPTY` — never heard from — blocks, with a reason that says never
rather than stale. `calendar_seam.py` puts `EMPTY` first in the enumeration for
this reason and records the consequence: *"here, the book gets flattened."* A
detector that treated silence-since-boot as health would be green on a poller
that never started, which is the failure `nix_check_contract.md` §17 names —
a safety property proven while its subject is unavailable is not proven.

An **unknown feed** is treated the same way: `StalenessFlagPort` reads every
feed the policy carries, and a feed with no stamp for the key being asked about
is EMPTY and blocks. There is no path through this module where an absent
subject produces a clear verdict.

---

## §6.4b MONOTONIC-BY-SOURCE — WHOSE PROPERTY THIS IS, AND WHOSE IT IS NOT

`SourceMonotonicGuard` implements §6.4b's rule: a reading older than the one
held for that key is **discarded, not applied**, ordering by source instant and
then by the venue's sequence number, **per key**.

`nixalloc/mirror.py` implements a guard of the same shape and counts its
degradations. **It is not this one, and the difference is the seam, not the
wording** (doctrine C.9 forbids a duplicate instrument over the same subject,
not the same rule applied at two different places):

* **SIDE.** There: CONSUMER — the Allocator's private mirror. Here: PRODUCER —
  the poller's own cache, before anything is published.
* **SUBJECT.** There: the published `FinancialPicture`. Here: the
  `FreshnessStamp`s arriving from the venue and from the push feed.
* **KEYS.** There: `balance`, `margin:<symbol>`, `position:<trade_id>`. Here:
  `<feed>` and `<feed>:<symbol>`.
* **ORDERING.** There: picture `version`, then per-key float stamps. Here:
  `as_of`, then `source_seq`.
* **DEGRADED MODE.** There: yes, and counted — D3.121, the wire carries no
  venue stamps. Here: none; the stamp is not optional on this side.

The consequence is that neither can stand in for the other: a regression the
mirror catches has already been published, and a reordering the transport
introduces downstream is invisible from here. §6.4b names *the Limiter* as the
acceptor, so applying the identical rule at the poller's own cache is this
arc's extension of it and is labelled as one rather than presented as the
spec's own words.

There is **no degraded mode here on purpose.** The mirror degrades because the
wire it reads genuinely carries no venue stamps; the poller CONSTRUCTS the
stamp from the reading it just fetched, so an unstamped reading at this seam is
a bug in the poller, not a gap in a schema. `admit` raises rather than guesses.

---

## §12.3 — CLOCK INTEGRITY, AND THE ONE THING IT DOES NOT DEFINE

§12.3: *"All blackouts are clock-driven ⇒ the clock is safety-critical. chrony
sync + continuous skew monitor against exchange/vendor timestamps; skew >
threshold ⇒ stale-class HALT. All internal time is UTC."*

`ClockSkewMonitor` is that monitor. Skew is `|local − reference|` against an
exchange/vendor instant; past `CLOCK_SKEW_MAX_MS` it blocks with a stale-class
reason. **Never observed blocks too**, for the `EMPTY` reason above: a skew
monitor that has taken no reading has not proven the clock, and §12.3 makes the
clock the thing every blackout stands on.

**The gap, stated rather than papered over:** a skew observation is itself
perishable — an observation from an hour ago proves nothing about now, and a
monitor that trusts one forever is the same F17 shape one layer over. §12A
gives `CLOCK_SKEW_MAX_MS` (how far off) and **no knob at all for how old a skew
observation may be**. Rather than invent a tunable §12A does not carry, or
silently reuse another feed's threshold as though the spec had said so,
`ClockSkewMonitor` takes `observation_max_age_ms` as a **required constructor
argument with no default** — the same refusal `nixalloc.mirror.AllocatorMirror`
records for `max_age_s`: *"a ceiling with a default is a ceiling nobody
chose."* The missing §12A knob is CHECK-DEBT, not a decision taken here.

**ALL INTERNAL TIME IS UTC** is enforced, not requested: every `datetime` that
enters this module is checked for `tzinfo` and for a zero UTC offset, and a
naive or offset instant raises `NaiveInstantError` at the boundary. §12.3's
sentence is one a comment cannot keep; `check_staleness` plants a naive instant
and requires the raise.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from nixrisk.calendar_seam import CacheState, FreshnessStamp

__all__ = [
    "GLOBAL_FEEDS",
    "THRESHOLD_SUFFIX",
    "ClockSkewFlagPort",
    "ClockSkewMonitor",
    "FreshnessReading",
    "FreshnessTracker",
    "NaiveInstantError",
    "RetryLadder",
    "SkewObservation",
    "SourceMonotonicGuard",
    "StalenessFlagPort",
    "StalenessPolicy",
    "StalenessUsageError",
    "feed_key",
]

#: The suffix `risks/staleness.config.json` spells its per-feed thresholds with.
#: Feed NAMES are derived by stripping it, never listed: a knob added to §12A
#: and to the config is in scope here the moment it lands, with no edit to this
#: module. `risk_config._retry_ladder_fits_smallest_threshold` reads the same
#: suffix off the same file, which is what makes the two agree by construction
#: rather than by both being maintained.
THRESHOLD_SUFFIX = "_stale_ms"

#: Feeds with NO symbol dimension. §6.4b keys the guard *"per symbol for margin,
#: per instrument for position"*; balance is an ACCOUNT-level quantity in the
#: same clause (*"balance originates at the venue"*, one figure, not one per
#: symbol), so keying it per symbol would make every symbol's balance stamp
#: permanently EMPTY.
#:
#: Anything NOT named here is per-symbol, and that default is the fail-closed
#: direction on purpose: a genuinely global feed mistakenly treated as
#: per-symbol has no stamp under any symbol key, reads EMPTY, and BLOCKS. The
#: opposite default would let a new feed answer for every symbol off one
#: observation.
GLOBAL_FEEDS: frozenset[str] = frozenset({"balance"})


class StalenessUsageError(Exception):
    """A caller used this module wrongly. Never degraded to a default.

    Same refusal `risk_config.RiskConfigError` records: every knob here bounds a
    halt-and-flatten, and a silently substituted default is worse than a loud
    stop.
    """


class NaiveInstantError(StalenessUsageError):
    """§12.3: all internal time is UTC. A naive or offset instant is refused."""


def _utc(value: object, site: str) -> datetime:
    """§12.3's UTC rule, enforced at the boundary of every public verb."""
    if not isinstance(value, datetime):
        raise NaiveInstantError(
            f"{site}: expected a datetime, got {type(value).__name__} — §12.3 "
            "makes every internal instant a timezone-aware UTC datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise NaiveInstantError(
            f"{site}: {value!r} is NAIVE. §12.3: 'All internal time is UTC'. A "
            "naive instant carries no offset, so an age computed from it is a "
            "number whose units depend on the host's local zone"
        )
    if value.utcoffset() != UTC.utcoffset(None):
        raise NaiveInstantError(
            f"{site}: {value!r} carries a non-zero UTC offset. §12.3 puts the "
            "exchange-local -> UTC conversion at window generation, exactly "
            "once; an offset instant reaching a decision path means it "
            "happened somewhere else as well"
        )
    return value


def feed_key(feed: str, symbol: str = "") -> str:
    """§6.4b's per-key identity for a feed observation.

    Global feeds key on the feed alone; everything else keys on
    `<feed>:<symbol>`, so *"a late update on one key can never regress
    another"* holds across symbols as well as across feeds.
    """
    if feed in GLOBAL_FEEDS:
        return feed
    return f"{feed}:{symbol}"


# ---------------------------------------------------------------------------
# §12A knobs, loaded — never defaulted
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryLadder:
    """§12A's `RETRY_BACKOFF`, as the three fields the config declares.

    `total_ms` is the geometric sum `risk_config` boot-validates against the
    tightest threshold. It is computed the same way there and here from the same
    three numbers; it is not stored, so there is no second copy to drift.
    """

    attempts: int
    initial_ms: float
    multiplier: float

    @property
    def total_ms(self) -> float:
        """The whole ladder's duration in ms."""
        return sum(
            self.initial_ms * self.multiplier**step for step in range(self.attempts)
        )

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> RetryLadder:
        """Build from the config's `retry_backoff` object. Raises on anything."""
        fields = ("attempts", "initial_ms", "multiplier")
        numbers: dict[str, float] = {}
        for field in fields:
            if field not in values:
                raise StalenessUsageError(
                    f"retry_backoff is missing {field!r} — §12A's RETRY_BACKOFF "
                    "is a policy, and a policy missing a field is not a shorter "
                    "policy, it is an unloadable one"
                )
            value = values[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StalenessUsageError(
                    f"retry_backoff.{field}={value!r} is "
                    f"{type(value).__name__}, expected a number"
                )
            numbers[field] = float(value)
        if numbers["attempts"] < 1:
            raise StalenessUsageError(
                f"retry_backoff.attempts={numbers['attempts']!r} — §6.4 declares "
                "a feed stale 'after retry/backoff', so a ladder with no rung "
                "is a stale declaration with no retry in front of it"
            )
        return cls(
            attempts=int(numbers["attempts"]),
            initial_ms=numbers["initial_ms"],
            multiplier=numbers["multiplier"],
        )


@dataclass(frozen=True)
class StalenessPolicy:
    """Every §12A knob this module reads, loaded from `risks/staleness.*`.

    FROZEN, and its mapping is a plain read-only dict built at construction:
    §12.11 makes these boot-loaded and restart-only, so there is deliberately no
    setter a mid-session edit could reach.
    """

    thresholds_ms: Mapping[str, float]
    clock_skew_max_ms: float
    retry: RetryLadder

    @property
    def feeds(self) -> tuple[str, ...]:
        """Every feed the config declares a threshold for, sorted."""
        return tuple(sorted(self.thresholds_ms))

    def threshold_ms(self, feed: str) -> float:
        """§6.4's per-feed stale threshold. Raises on a feed with no knob."""
        if feed not in self.thresholds_ms:
            raise StalenessUsageError(
                f"no §12A threshold is configured for feed {feed!r} "
                f"(configured: {', '.join(self.feeds) or 'none'}) — a feed "
                "gated against a threshold nobody set is ungated"
            )
        return self.thresholds_ms[feed]

    def deadline_ms(self, feed: str) -> float:
        """Threshold PLUS the retry ladder — see the module docstring."""
        return self.threshold_ms(feed) + self.retry.total_ms

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> StalenessPolicy:
        """Build from `risks/staleness.config.json`'s VALUE keys.

        Takes the plain mapping rather than a `RiskConfigSet` so this module has
        no import edge to the loader: the detector must be constructible in a
        test, in a check, and at boot, and only one of those three has a
        validated config set in hand.
        """
        thresholds: dict[str, float] = {}
        for key, value in values.items():
            if not key.endswith(THRESHOLD_SUFFIX):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StalenessUsageError(
                    f"{key}={value!r} is {type(value).__name__}, expected a number"
                )
            if value <= 0:
                raise StalenessUsageError(
                    f"{key}={value!r} — a non-positive stale threshold declares "
                    "the feed stale on the first reading and halts trading "
                    "immediately (risks/staleness.config.json, positive.scalars)"
                )
            thresholds[key[: -len(THRESHOLD_SUFFIX)]] = float(value)
        if not thresholds:
            raise StalenessUsageError(
                f"no `{THRESHOLD_SUFFIX}` key is present — a staleness policy "
                "with no threshold declares nothing stale, ever, which is the "
                "gate passing while measuring nothing"
            )
        skew = values.get("clock_skew_max_ms")
        if isinstance(skew, bool) or not isinstance(skew, (int, float)):
            raise StalenessUsageError(
                f"clock_skew_max_ms={skew!r} is absent or not a number — §12.3 "
                "makes the clock safety-critical and every blackout stands on it"
            )
        if skew <= 0:
            raise StalenessUsageError(
                f"clock_skew_max_ms={skew!r} — a non-positive skew ceiling "
                "HALTs on the first observation, however good the clock is"
            )
        backoff = values.get("retry_backoff")
        if not isinstance(backoff, Mapping):
            raise StalenessUsageError(
                "retry_backoff is absent or is not an object — §6.4 puts the "
                "halt behind the ladder, so a missing ladder is a missing bound "
                "on detection latency"
            )
        return cls(
            thresholds_ms=dict(thresholds),
            clock_skew_max_ms=float(skew),
            retry=RetryLadder.from_values(backoff),
        )


# ---------------------------------------------------------------------------
# §6.4b — MONOTONIC BY SOURCE, per key
# ---------------------------------------------------------------------------


class SourceMonotonicGuard:
    """§6.4b: a reading older than the one held for that key is DISCARDED.

    Two counters, for the reason `nixalloc.mirror.AllocatorMirror` gives its
    five: *"a mirror that cannot say what it accepted and what it threw away
    cannot be measured, only believed."* `discarded_older` is the only
    externally visible evidence the guard ever fired.
    """

    def __init__(self) -> None:
        self._held: dict[str, FreshnessStamp] = {}
        self.admitted = 0
        self.discarded_older = 0

    def held(self, key: str) -> FreshnessStamp | None:
        """The newest stamp accepted for `key`, or `None`."""
        return self._held.get(key)

    def keys(self) -> tuple[str, ...]:
        """Every key that has ever been admitted, sorted."""
        return tuple(sorted(self._held))

    def admit(self, key: str, stamp: FreshnessStamp) -> bool:
        """`True` if `stamp` was accepted for `key`; `False` if discarded.

        STRICTLY newer wins. §6.4b accepts *"ONLY if it is newer than the one it
        holds"*, so an equal instant is not newer and is discarded — a venue
        that re-sends the same reading must not be able to refresh its own age.
        Where the venue supplies `source_seq`, equal instants are broken by it,
        because *"a venue that stamps two readings in the same second still
        orders them"* (`calendar_seam.FreshnessStamp`).
        """
        if not isinstance(stamp, FreshnessStamp):
            raise StalenessUsageError(
                f"admit({key!r}) was handed {type(stamp).__name__}, not a "
                "FreshnessStamp — the poller constructs the stamp from the "
                "reading it fetched, so an unstamped reading at this seam is a "
                "defect in the producer, never a schema gap to degrade around"
            )
        _utc(stamp.as_of, f"SourceMonotonicGuard.admit({key!r})")
        current = self._held.get(key)
        if current is not None and not self._is_newer(stamp, current):
            self.discarded_older += 1
            return False
        self._held[key] = stamp
        self.admitted += 1
        return True

    @staticmethod
    def _is_newer(candidate: FreshnessStamp, held: FreshnessStamp) -> bool:
        """Order by source instant, then by the venue's sequence number."""
        if candidate.as_of != held.as_of:
            return candidate.as_of > held.as_of
        if candidate.source_seq is None or held.source_seq is None:
            return False
        return candidate.source_seq > held.source_seq


# ---------------------------------------------------------------------------
# The reading a rule acts on
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessReading:  # pylint: disable=too-many-instance-attributes
    """One feed's age against its §12A threshold, at one instant.

    `state` is what the cache IS (§6.4's freshness stamp past threshold);
    `blocked` is what the gate DOES (§6.4's halt, which sits behind the retry
    ladder). See the module docstring — they are different questions and both
    are needed.
    """

    feed: str
    key: str
    state: CacheState
    blocked: bool
    reason: str
    #: `None` only where nothing has ever been observed for this key.
    age_ms: float | None
    threshold_ms: float
    deadline_ms: float


# ---------------------------------------------------------------------------
# The detector
# ---------------------------------------------------------------------------


class FreshnessTracker:
    """Holds the newest stamp per key and answers with its AGE. Pure.

    The clock is injected because the subject under test is a relationship
    between two instants, and a detector that reads the wall clock internally
    can only be tested by waiting. `check_staleness` drives 900-second staleness
    without a 900-second run precisely because of this argument.
    """

    def __init__(
        self,
        policy: StalenessPolicy,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._policy = policy
        self._clock = clock
        self._guard = SourceMonotonicGuard()
        self.observations = 0

    @property
    def policy(self) -> StalenessPolicy:
        """The loaded §12A knobs this tracker judges against."""
        return self._policy

    @property
    def guard(self) -> SourceMonotonicGuard:
        """§6.4b's per-key guard, exposed for its counters."""
        return self._guard

    def observe(self, stamp: FreshnessStamp, symbol: str = "") -> bool:
        """Record one arrival. `False` where §6.4b's guard discarded it.

        The stamp's `feed` names the §12A knob (`calendar_seam.FreshnessStamp`),
        so an observation for a feed no threshold covers is refused HERE rather
        than being held and silently never judged.
        """
        self._policy.threshold_ms(stamp.feed)
        self.observations += 1
        return self._guard.admit(feed_key(stamp.feed, symbol), stamp)

    def held(self, feed: str, symbol: str = "") -> FreshnessStamp | None:
        """The newest admitted stamp for this feed/symbol, or `None`."""
        return self._guard.held(feed_key(feed, symbol))

    def reading(self, feed: str, symbol: str = "") -> FreshnessReading:
        """This feed's freshness at `clock()`. ONE subtraction, no aggregate."""
        threshold = self._policy.threshold_ms(feed)
        deadline = self._policy.deadline_ms(feed)
        key = feed_key(feed, symbol)
        now = _utc(self._clock(), f"FreshnessTracker.reading({feed!r})")
        stamp = self._guard.held(key)
        if stamp is None:
            return FreshnessReading(
                feed=feed,
                key=key,
                state=CacheState.EMPTY,
                blocked=True,
                reason=(
                    f"feed {feed!r} has NEVER been observed for key {key!r} — "
                    "an unstarted or wedged poller is not a quiet healthy one "
                    "(§6.4, stale-until-proven-fresh); §17: a property proven "
                    "while its subject is unavailable is not proven"
                ),
                age_ms=None,
                threshold_ms=threshold,
                deadline_ms=deadline,
            )
        # THE measurement. `now - as_of` against the LAST arrival's own source
        # instant. There is no second sample in scope, by construction.
        age_ms = (now - stamp.as_of).total_seconds() * 1000.0
        if age_ms < -self._policy.clock_skew_max_ms:
            return FreshnessReading(
                feed=feed,
                key=key,
                state=CacheState.STALE,
                blocked=True,
                reason=(
                    f"feed {feed!r} key {key!r}: source stamp {stamp.as_of.isoformat()} "
                    f"is AHEAD of the local clock by {-age_ms:.0f} ms, beyond "
                    f"CLOCK_SKEW_MAX_MS={self._policy.clock_skew_max_ms:.0f} ms. A "
                    "future-dated stamp never ages, so the feed would read fresh "
                    "forever — this is a clock or venue fault (§12.3), not freshness"
                ),
                age_ms=age_ms,
                threshold_ms=threshold,
                deadline_ms=deadline,
            )
        if age_ms <= threshold:
            return FreshnessReading(
                feed=feed,
                key=key,
                state=CacheState.FRESH,
                blocked=False,
                reason="",
                age_ms=age_ms,
                threshold_ms=threshold,
                deadline_ms=deadline,
            )
        blocked = age_ms > deadline
        if blocked:
            reason = (
                f"feed {feed!r} key {key!r} is STALE: {age_ms:.0f} ms since the "
                f"LAST ARRIVAL (source instant {stamp.as_of.isoformat()}), past "
                f"the §12A threshold of {threshold:.0f} ms and past the "
                f"{deadline:.0f} ms retry/backoff deadline. §6.4: stale => halt "
                "new entries AND flatten open"
            )
        else:
            reason = (
                f"feed {feed!r} key {key!r} is past its {threshold:.0f} ms "
                f"threshold at {age_ms:.0f} ms, inside the retry/backoff window "
                f"that ends at {deadline:.0f} ms — §6.4 declares stale only "
                "AFTER retry/backoff, so this is not yet a halt"
            )
        return FreshnessReading(
            feed=feed,
            key=key,
            state=CacheState.STALE,
            blocked=blocked,
            reason=reason,
            age_ms=age_ms,
            threshold_ms=threshold,
            deadline_ms=deadline,
        )


# ---------------------------------------------------------------------------
# The two ports `gate.py` already consumes (§3 phase A)
# ---------------------------------------------------------------------------


class StalenessFlagPort:
    """§6.4's stale condition as `gate.SymbolFlagPort`. `read(symbol)`.

    Satisfies the Protocol structurally; nothing in `gate.py` is edited, and
    `check_staleness` asserts `isinstance(port, gate.SymbolFlagPort)` against
    the shipped `runtime_checkable` declaration rather than against a comment.

    O(1) per feed (§11.1: *"a dict lookup, never a scan"*) — the loop is over
    the configured FEEDS, a fixed handful fixed at boot, not over any
    population that grows with the book.
    """

    def __init__(self, tracker: FreshnessTracker) -> None:
        self._tracker = tracker

    @property
    def tracker(self) -> FreshnessTracker:
        """The detector behind this port."""
        return self._tracker

    def readings(self, symbol: str) -> tuple[FreshnessReading, ...]:
        """Every configured feed's reading for this symbol, in feed order."""
        return tuple(
            self._tracker.reading(feed, symbol) for feed in self._tracker.policy.feeds
        )

    def read(self, symbol: str) -> tuple[bool, str]:
        """`(blocked, reason)` — the shape `gate.SymbolFlagRule` dispatches.

        EVERY blocking feed is named, not just the first. §3 requires a denial
        to be actionable, and *"margin is stale"* sends an operator to one feed
        when three have stopped; the reason a rule reports is the only account
        anyone downstream gets.
        """
        blocking = [r for r in self.readings(symbol) if r.blocked]
        if not blocking:
            return False, ""
        return True, "; ".join(r.reason for r in blocking)


@dataclass(frozen=True)
class SkewObservation:
    """One comparison of the local UTC clock against an exchange/vendor instant.

    `source` names WHICH reference — §12.3 says *"against exchange/vendor
    timestamps"*, plural, and a skew figure whose reference is unknown cannot be
    acted on: correcting against a broken vendor clock is how a good host clock
    gets dragged off.
    """

    local: datetime
    reference: datetime
    source: str
    #: When this comparison was TAKEN (UTC). Distinct from `local`, which is the
    #: value being compared: a monitor may hold an observation longer than it
    #: took to make one, and the age that matters is the holding time.
    observed_at: datetime

    @property
    def skew_ms(self) -> float:
        """Signed: positive where the LOCAL clock is ahead of the reference."""
        return (self.local - self.reference).total_seconds() * 1000.0


class ClockSkewMonitor:  # pylint: disable=too-many-instance-attributes
    """§12.3's continuous skew monitor as `gate.GlobalFlagPort`. `read()`.

    `observation_max_age_ms` is REQUIRED and has no default — see the module
    docstring's §12.3 section. §12A carries no knob for it and one is not
    invented here.
    """

    def __init__(
        self,
        policy: StalenessPolicy,
        *,
        clock: Callable[[], datetime],
        observation_max_age_ms: float,
    ) -> None:
        if observation_max_age_ms <= 0:
            raise StalenessUsageError(
                f"observation_max_age_ms={observation_max_age_ms!r} must be "
                "positive — a non-positive ceiling makes every observation "
                "stale on arrival and HALTs on a correct clock"
            )
        self._policy = policy
        self._clock = clock
        self._max_age_ms = float(observation_max_age_ms)
        self._latest: SkewObservation | None = None
        self.observations = 0

    @property
    def latest(self) -> SkewObservation | None:
        """The most recent skew observation, or `None`."""
        return self._latest

    def observe(self, observation: SkewObservation) -> None:
        """Record one comparison. Every instant is UTC-checked at this boundary."""
        for field in ("local", "reference", "observed_at"):
            _utc(getattr(observation, field), f"SkewObservation.{field}")
        self._latest = observation
        self.observations += 1

    def read(self) -> tuple[bool, str]:
        """`(blocked, reason)` — the shape `gate.GlobalFlagRule` dispatches."""
        now = _utc(self._clock(), "ClockSkewMonitor.read")
        observation = self._latest
        if observation is None:
            return True, (
                "§12.3 clock integrity: NO skew observation has ever been "
                "taken. All blackouts are clock-driven, so an unverified clock "
                "is a stale-class HALT, not a clear one (§17: a property proven "
                "while its subject is unavailable is not proven)"
            )
        age_ms = (now - observation.observed_at).total_seconds() * 1000.0
        if age_ms > self._max_age_ms:
            return True, (
                f"§12.3 clock integrity: the newest skew observation (source "
                f"{observation.source!r}) was taken {age_ms:.0f} ms ago, past "
                f"the {self._max_age_ms:.0f} ms holding ceiling. A skew reading "
                "that is not refreshed proves the clock was good once, which is "
                "the stale-measure defect one layer up — stale-class HALT"
            )
        skew = observation.skew_ms
        if abs(skew) > self._policy.clock_skew_max_ms:
            direction = "AHEAD of" if skew > 0 else "BEHIND"
            return True, (
                f"§12.3 clock integrity: local clock is {abs(skew):.0f} ms "
                f"{direction} reference {observation.source!r}, past "
                f"CLOCK_SKEW_MAX_MS={self._policy.clock_skew_max_ms:.0f} ms — "
                "stale-class HALT. Every blackout in §6 is clock-driven, so a "
                "skewed clock moves every window without moving any config"
            )
        return False, ""


#: Declared here so `check_staleness` can assert the structural connection to
#: `gate.py`'s Protocols by reading THIS tuple rather than by a name typed into
#: the gate. A class listed here and not satisfying its port is the defect.
PORT_IMPLEMENTATIONS: tuple[tuple[str, str], ...] = (
    ("StalenessFlagPort", "SymbolFlagPort"),
    ("ClockSkewFlagPort", "GlobalFlagPort"),
)

#: §12.3's clock-integrity port, under the name §12A and `gate.py` use for the
#: rule (`clock_skew`). An alias rather than a second class: two classes would
#: be two things to keep in step, and `check_staleness` proves the alias is the
#: same object.
ClockSkewFlagPort = ClockSkewMonitor
