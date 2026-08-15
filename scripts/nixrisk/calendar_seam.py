"""The calendar / blackout / poller seam — types and ports, no behaviour.

ARC 033 / Phase 0.4. Third in the line that starts at `nixrisk/seam.py` (ARC
028 / 0.6, the Limiter's own boundary) and continues at `nixalloc/seam.py`
(ARC 031 / 0.6, the Allocator's consumer side): landed BEFORE any blackout
rule, poller, or session-close flatten exists, so those are built against a
settled boundary instead of against each other.

WHAT IS IN HERE. Value types, enumerations, and `Protocol` declarations. No
rule, no arithmetic, no I/O, no policy. `check_calendar_schema` proves the
no-behaviour claim structurally rather than asking a reader to take it.

---

## §12.3 — THE ONE INVARIANT THIS WHOLE MODULE EXISTS TO CARRY

§12.3, verbatim: *"**All internal time is UTC**; the calendar poller converts
exchange-local (incl. DST) exactly once at window generation."*

Two halves, and the second is the one that gets lost:

1. Every instant in every type below is a timezone-aware UTC `datetime`. There
   is no `America/Chicago` anywhere in this module, and none may appear.
2. **Exchange-local time is a GENERATION-TIME input, never a decision-time
   one.** `WindowSourcePort.windows_for` is the single declared home for the
   conversion. Everything downstream of it — every gate, every flatten
   deadline, every roll instant — compares UTC instants to UTC instants.

The vendored artifact under `scripts/crucible/calendar_data/` stores two
Central-time columns (`eth_open_ct`, `eth_close_ct`) alongside its UTC ones.
They are DST-correct and **nothing reads them**: they are audit/eyeball
columns, written by `calendar_gen.py` and consumed by no runtime code. That is
precisely why `check_calendar_schema` enforces *no decision path READS a
stored local-time field* rather than *no stored local-time field exists*: the
weaker-sounding rule is the one that is true of the shipped tree, is
mechanically checkable on it, and still closes the hazard — the next arc that
needs "exchange local" will find `eth_open_ct` sitting there and read it. A
rule phrased as "no such column exists" would have reddened a green tree on
day one and been suppressed by day two, which buys nothing. See that gate's
docstring for the same argument from the instrument's side.

---

## WHAT IS DELIBERATELY *NOT* IN HERE, because saying so is the point

* **A margin TABLE.** §6.4's v1.3 lock: *"live current margin per symbol is
  **NOT** a separate table or its own shared-memory block"* — the Limiter
  folds it into the one unified financial-picture snapshot under one writer
  and one version stamp. `FinancialPicture.margin_per_contract` (imported and
  re-exported below, never restated) already IS that field set. What §6.4's
  first bullet calls the poller's "margin cache" is therefore, after the v1.3
  lock, the **scheduled/baseline** regime data §6.3 needs — the level a
  trailing edge waits to return to, and the level a stable-elevated regime
  shift re-accepts. That, and only that, is `MarginBaselineReadPort`.
  Declaring a second live-margin surface here would reintroduce the
  cross-table skew §6.4 spent a paragraph removing, at a new seam.
* **Every blackout RULE.** §6.1 (EOD), §6.1b (session-close flatten), §6.2
  (EOW union), §6.3 (news/margin asymmetric edges), §6.4's stale⇒halt+flatten
  and §6.5's unified model are all rules, and none of them is here. This
  module freezes the SHAPE of what those rules read.
* **The staleness THRESHOLDS.** `MARGIN_STALE_MS` / `CALENDAR_STALE_MS` /
  `CLOCK_SKEW_MAX_MS` are §12A tunables, boot-loaded from per-module JSON.
  `FreshnessStamp` carries the observation; the comparison is a rule's, and a
  default written here would become the value nobody re-tuned.
* **The window GENERATOR.** `WindowSourcePort` is declared, not implemented.
  The generation of live per-symbol windows is the calendar poller's job
  (§6.4); the vendored build-time artifact under `scripts/crucible/` is its
  offline counterpart, not its replacement.

---

## §6.5 — "NEW BLACKOUT TYPES ARE DATA (A WINDOW), NOT CODE"

`WindowKind` is an enumeration, which is code, and that looks like a
contradiction. It is not, and the distinction is worth writing down because
getting it backwards is how the rule dies:

`WindowKind` records **which spec clause emitted a window** — it is a
provenance label carried for the audit trail and for §6.1's entry-only
asymmetry. **No gating rule may branch on it.** §6.5's unified model is
`now ∈ any window`, kind-agnostic; §6.1's *"Entry-only; exits still fire"* is
carried by `Window.entry_only`, a per-ROW boolean, not by a `kind == EOD`
test. So a new blackout type adds ROWS to a window set and, at most, one
enumeration member for the log — never a branch, never a rule. If a future
reader finds a rule switching on `WindowKind`, that rule is the defect.

`Window.entry_only` is the field that makes §6.1's asymmetry data rather than
convention: an EOD window is entry-only, a §6.3 open-position breach is not,
and both are the same type with different bytes.

---

## SYNCHRONOUS OR ASYNCHRONOUS — declared per verb, with the reasoning

`nixrisk/seam.py` declared every verb synchronous; `nixalloc/seam.py` did too
and said explicitly that *"a blanket 'same as the Limiter' would be a style
rule wearing an argument's clothes"*. **This module is the first to declare
BOTH, so the split has to earn itself verb by verb.** Every reason below is
its own; none of them is "consistent with the Limiter".

**SYNCHRONOUS — the read side (§6.4: "Allocator/Limiter read caches only"):**

* **`WindowSetReadPort.windows` — SYNCHRONOUS, and it is a TOTALITY
  property.** §6.5's unified model puts `now ∈ any window` in the *pre-size*
  gate, on the Limiter's single-threaded loop (§5). The verb must be total:
  there is no "window set not ready yet" answer a gate can act on, so an
  absent set returns `CacheState.EMPTY` immediately and the rule fails closed.
  An awaitable lookup has a third outcome — *pending* — and a pre-size gate
  with a pending branch is a gate that can neither admit nor deny.
* **`WindowSetReadPort.freshness` — SYNCHRONOUS, and here the reason is
  SELF-REFERENCE, which is why it cannot inherit the verb above's.** §6.4:
  stale ⇒ halt new entries AND flatten open. The condition being detected is
  "the thing that refreshes this cache stopped making progress" — and on a
  single-threaded loop that is frequently the same stall that would service an
  `await`. An awaitable staleness read cannot report the outage that prevents
  it from returning. Fail-closed detection must not depend on the machinery it
  is watching.
* **`MarginBaselineReadPort.baseline` — SYNCHRONOUS, and the reason is
  §6.3's trailing EDGE.** The reactive edge holds until live margin returns to
  baseline; that comparison reads a *live* figure off the picture and a
  *baseline* figure off this cache, and it must read both against one instant.
  An awaitable baseline read puts a suspension point between the two terms of
  a single comparison — the operand skew §6.4 rejects independent tables for,
  reproduced inside one rule.
* **`MarginBaselineReadPort.freshness` — SYNCHRONOUS, distinct again:**
  `MARGIN_STALE_MS` and `CALENDAR_STALE_MS` are *different* §12A knobs on
  *different* cadences (§6.4: seconds vs minutes). The two stamps must be
  readable in one breath, or their relative age becomes a function of
  scheduling order rather than of the data, and the halt decision starts
  depending on which coroutine woke first.
* **`RollScheduleReadPort.front_contract` — SYNCHRONOUS, and it is an
  IDENTITY property.** §7.5: all symbol-keyed subsystems (capture, backfill,
  margin cache, calendar, Renko state, positions) switch identity
  **atomically at a defined roll instant**. An awaitable identity lookup
  admits two subsystems resolving the same instant on opposite sides of the
  roll across a suspension — which is exactly the stitched-across-contracts
  seam §7.5 forbids, arriving through the clock instead of through the data.
* **`RollScheduleReadPort.next_roll` — SYNCHRONOUS**, and its reason is not
  the atomicity above: it feeds §7.5's *roll-day entry blackout*, which is a
  window, and windows are generated ahead of time by a batch that has no loop
  to yield to.
* **`WindowSourcePort.windows_for` — SYNCHRONOUS, and this one is the §12.3
  invariant itself.** It is the single place exchange-local becomes UTC,
  "exactly once at window generation". A pure function of (symbol, day,
  calendar rows) has nothing to await; making it awaitable would invite an
  implementation that fetches, and a conversion that can fetch is a
  conversion that can happen twice, against two different tzdb states.
* **`MarginPollerPort.publish` / `CalendarPollerPort.publish` —
  SYNCHRONOUS, both, and for §12.7's reason rather than any of the above.**
  Snapshot-on-subscribe publishes an ATOMIC snapshot outward; an awaitable
  publish opens the window in which a subscriber's mirror can observe a
  half-built table, which is the state §12.7 calls "incomplete ⇒ treated as
  stale". The verb returns when the bytes are consistent, or it is not a
  publish.

**ASYNCHRONOUS — the poll side, and the two are async for DIFFERENT reasons:**

* **`MarginPollerPort.poll_once` — ASYNCHRONOUS because of CONTAINMENT.**
  It is real venue I/O on the shared pool (§6.4: fast, seconds), behind
  `RETRY_BACKOFF`. A hung broker socket must cost one suspended coroutine and
  not one blocked pool worker — the same containment argument §5 gives for
  putting the Limiter's sender on its own low-priority thread, reached here
  through the pool rather than through the loop. Latency is the concern.
* **`CalendarPollerPort.refresh` — ASYNCHRONOUS because of DURATION, which is
  not the same argument.** Its cadence is minutes and its unit of work is
  bulk: sessions, econ events, roll schedule, holidays and half-days, for
  every symbol (§6.4). It is not latency-sensitive at all. Async here buys
  cooperative yielding *during a long rebuild* so a slow calendar refresh
  cannot starve the fast margin poll sharing the pool; it buys no I/O overlap
  worth naming, and saying so keeps a later reader from "optimising" the
  margin poller's reason onto it.

---

## THE READ PORTS DECLARE NO MUTATING VERB, AND THAT IS STRUCTURAL

§6.4: *"Allocator/Limiter **read caches only**."* `nixalloc/seam.py` makes the
same authority split structural by giving `MirrorPort` no `publish`, `set`,
`update` or `apply`. Same here: every Protocol named in `READ_ONLY_PORTS`
below carries only verbs that return. `check_calendar_schema` walks that tuple
and reddens on any mutating verb declared on any of them, so the property is
measured on the shipped bytes rather than asserted in this paragraph.

The poller ports are where mutation lives, and they are deliberately NOT in
`READ_ONLY_PORTS` — the split is the point, not an oversight.

---

## STALE-UNTIL-PROVEN-FRESH — the default value is EMPTY, not FRESH

`CacheState`'s first member is `EMPTY` and `FreshnessStamp` has no default
`as_of`. §6.4 makes stale a HALT-and-flatten condition, so a cache that has
never heard from its poller must not be indistinguishable from a quiet,
healthy one. This is the same hazard `nixalloc/seam.py` records for the
mirror; it is repeated here because the consequence is different — there, a
sizing pass fast-drops; here, the book gets flattened.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from nixrisk.seam import FinancialPicture

__all__ = [
    "READ_ONLY_PORTS",
    "CacheState",
    "CalendarPollerPort",
    "ContractIdentity",
    "FinancialPicture",
    "FreshnessStamp",
    "MarginBaseline",
    "MarginBaselineReadPort",
    "MarginPollerPort",
    "RollScheduleReadPort",
    "Window",
    "WindowKind",
    "WindowSet",
    "WindowSetReadPort",
    "WindowSourcePort",
]

# pylint: disable=too-few-public-methods
# Every Protocol below carries exactly the verbs its spec clause gives it. A
# boundary is not improved by inventing a second method so a class-shape
# heuristic is satisfied; on a READ port an invented verb is authority granted
# that §6.4 withheld. Same reasoning `nixalloc/seam.py` records for its four.


# ---------------------------------------------------------------------------
# Window vocabulary (§6.1, §6.1b, §6.2, §6.3, §6.5, §7.5)
# ---------------------------------------------------------------------------


class WindowKind(enum.Enum):
    """WHICH SPEC CLAUSE EMITTED A WINDOW. A provenance label, never a branch.

    See the module docstring's §6.5 section: the gating rule is
    `now ∈ any window`, kind-agnostic. This enumeration exists so the Plane-1
    event log can say *why* an entry was denied, and so a window set can be
    audited clause by clause. A rule that switches on it is the defect.
    """

    #: §6.1 — 15–20 min before session close through the next session open.
    EOD = "eod"
    #: §6.1b — the force-flatten deadline. Emitted as a window so the flatten
    #: trigger and the entry blackout it must lead are the same kind of object
    #: and the boot-validated ordering invariant compares like with like.
    SESSION_FLATTEN = "session_flatten"
    #: §6.2 — 30 min before Friday close through Sunday session open.
    EOW = "eow"
    #: §6.3 — leading edge only. The trailing edge is live-margin-reactive and
    #: therefore NOT expressible as a pre-computed instant; a window carrying a
    #: fabricated end instant would claim knowledge §6.3 explicitly does not
    #: have. The rule holds the trailing edge open; the data states the lead.
    NEWS_MARGIN = "news_margin"
    #: §7.5 — roll-day entry blackout for the affected symbol.
    ROLL = "roll"
    #: The exchange is not open. Derived from the vendored session artifact as
    #: the gap between one session's close and the next session's open, and
    #: sub-classified there (daily break, weekend, holiday) rather than here.
    CLOSED = "closed"


@dataclass(frozen=True)
class Window:
    """One blackout window. Both instants UTC, half-open `[start, end)`.

    Half-open by declaration: an instant equal to `end` is OUTSIDE. Closed
    intervals make two adjacent windows overlap at a shared instant, and §6.2's
    union ("widest active leading edge wins") would then have to disambiguate a
    boundary that carries no information.

    `entry_only` carries §6.1's *"Entry-only; exits still fire"* as DATA. It is
    per-row, not per-kind, because §6.3 emits both flavours: a scheduled
    margin-event lead is entry-only, while a real margin breach on an open
    position is not.
    """

    kind: WindowKind
    symbol: str
    start: datetime
    end: datetime
    entry_only: bool
    #: Where this row came from — a vendored artifact stamp, a vendor feed id,
    #: or a rule name. A window that cannot say what emitted it cannot be
    #: reconciled against the calendar it claims to come from.
    source: str


@dataclass(frozen=True)
class WindowSet:
    """§6.4's *per-symbol window set*, as one immutable value.

    Frozen, and `windows` is a tuple rather than a list, for the reason
    `nixalloc/seam.py` gives its value types: a consumer holding a mutable
    window set could edit a published blackout in place, and every later reader
    in that process would gate on the edit — a change to canonical safety state
    that never left the process and appears in no event log.
    """

    symbol: str
    windows: tuple[Window, ...]
    #: The instant the SET was generated (UTC) — §12.3's "exactly once at
    #: window generation" is stamped here, so a consumer can prove which tzdb
    #: state a set was resolved under without re-deriving anything.
    generated_at: datetime


# ---------------------------------------------------------------------------
# Freshness (§6.4, §6.4b, §12.3)
# ---------------------------------------------------------------------------


class CacheState(enum.Enum):
    """EMPTY first, by declaration — see the module docstring's last section."""

    EMPTY = "empty"
    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True)
class FreshnessStamp:
    """The observation a staleness rule reads. It carries NO threshold.

    `as_of` is the SOURCE's own instant, not arrival time: §6.4b's
    MONOTONIC-BY-SOURCE guard orders every venue-sourced reading "by
    source-of-truth time, never by arrival time". `source_seq` carries the
    venue's sequence number where one exists, because a venue that stamps two
    readings in the same second still orders them.

    `feed` names which §12A knob applies (`margin`, `calendar`, ...). The knob's
    VALUE is not here: a default written into the seam becomes the value nobody
    re-tunes, and §12A is the single source of truth for tunables.
    """

    feed: str
    as_of: datetime
    source_seq: int | None = None


# ---------------------------------------------------------------------------
# Margin baseline (§6.3) — NOT the live per-symbol figure. See the docstring.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarginBaseline:
    """§6.3's baseline level and the instant it was accepted, per symbol.

    The *live* figure this is compared against is
    `FinancialPicture.margin_per_contract`, re-exported above and never
    restated here (§6.4's one-snapshot lock). `accepted_at` exists because
    §6.3's anti-lockout re-acceptance is an EVENT — "if margin holds
    stable-elevated beyond a defined period ... accept the new level as
    baseline — alert operator" — and an event with no timestamp cannot be
    audited, alerted on, or distinguished from the original level.
    """

    symbol: str
    level: float
    accepted_at: datetime
    #: True where `level` is a §6.3 re-acceptance rather than the original
    #: observed baseline. The operator alert §6.3 requires is a rule's to
    #: raise; this field is what tells it there is something to raise.
    re_accepted: bool = False


# ---------------------------------------------------------------------------
# Roll identity (§7.5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractIdentity:
    """The front-month identity every symbol-keyed subsystem switches on.

    `symbol` is the LOGICAL symbol (`ES`) — the key §7:498's buckets and
    `nixalloc.seam.BUCKET_OF` are written against. `contract` is the dated
    instrument (`ESZ26`). Keeping both in one value is what lets §7.5's
    "switch identity atomically" be a single assignment rather than a pair of
    them that can be observed half-applied.

    `roll_at` is the DEFINED ROLL INSTANT (UTC) at which this identity ceases
    to be front. §7.5 makes that instant the seam for Renko/backfill
    continuity, so it belongs to the identity, not to a schedule a caller has
    to look up separately.
    """

    symbol: str
    contract: str
    front_from: datetime
    roll_at: datetime


# ---------------------------------------------------------------------------
# READ ports (§6.4: "Allocator/Limiter read caches only")
# ---------------------------------------------------------------------------


@runtime_checkable
class WindowSetReadPort(Protocol):
    """§6.4's per-symbol window set, read-only. Total by declaration."""

    def windows(self, symbol: str) -> WindowSet | None:
        """The symbol's current window set, or `None` if none is held.

        `None` and an empty `WindowSet` are DIFFERENT and both are legal: the
        first means "nothing published for this symbol", the second means
        "published, and this symbol has no active windows". Collapsing them
        would make an unpublished symbol indistinguishable from a clear one,
        and §6.4's fail-closed direction depends on telling them apart.
        """

    def state(self) -> CacheState:
        """EMPTY / FRESH / STALE for the cache as a whole."""

    def freshness(self) -> FreshnessStamp | None:
        """The stamp a §6.4 staleness rule reads. `None` before first publish."""


@runtime_checkable
class MarginBaselineReadPort(Protocol):
    """§6.3's baseline cache, read-only. Not the live per-symbol figure."""

    def baseline(self, symbol: str) -> MarginBaseline | None:
        """The accepted baseline for `symbol`, or `None` if none is held."""

    def state(self) -> CacheState:
        """EMPTY / FRESH / STALE for the cache as a whole."""

    def freshness(self) -> FreshnessStamp | None:
        """The stamp a §6.4 staleness rule reads. `None` before first publish."""


@runtime_checkable
class RollScheduleReadPort(Protocol):
    """§7.5's roll schedule, read-only."""

    def front_contract(self, symbol: str, at: datetime) -> ContractIdentity | None:
        """Front-month identity for `symbol` at UTC instant `at`.

        `None` where the schedule does not cover `at` — never a guess. §7.5
        makes the roll instant the boundary for Renko/backfill continuity, and
        a guessed identity is precisely the phantom stitch it forbids.
        """

    def next_roll(self, symbol: str, at: datetime) -> datetime | None:
        """The next roll instant at or after `at` (UTC), feeding §7.5's window."""

    def state(self) -> CacheState:
        """EMPTY / FRESH / STALE for the schedule as a whole."""


# ---------------------------------------------------------------------------
# Generation and poller ports (§6.4, §12.3)
# ---------------------------------------------------------------------------


@runtime_checkable
class WindowSourcePort(Protocol):
    """THE single home of the exchange-local → UTC conversion (§12.3).

    Pure. Given a symbol and a UTC day, it returns that day's windows with
    every instant already resolved to UTC. Every consumer downstream compares
    UTC to UTC; nothing downstream may re-derive an exchange-local time, and
    `check_calendar_schema` measures that on the shipped tree.
    """

    def windows_for(self, symbol: str, day: datetime) -> tuple[Window, ...]:
        """The symbol's windows covering the UTC day containing `day`."""


@runtime_checkable
class MarginPollerPort(Protocol):
    """§6.4's fast (seconds) margin poller. Owns its cache; publishes outward."""

    async def poll_once(self) -> FreshnessStamp:
        """One venue round-trip. ASYNCHRONOUS — containment; see the docstring.

        Returns the stamp of what it fetched. §6.4's push-preferred clause
        means this may demote to fallback/audit when the user-sync websocket is
        delivering; the port is unchanged either way, which is the point of
        declaring the stamp rather than the transport.
        """

    def publish(self, baselines: tuple[MarginBaseline, ...]) -> None:
        """Publish an ATOMIC snapshot (§12.7). SYNCHRONOUS; see the docstring."""


@runtime_checkable
class CalendarPollerPort(Protocol):
    """§6.4's slow (minutes) calendar poller. Owns its cache; publishes outward."""

    async def refresh(self) -> FreshnessStamp:
        """Rebuild sessions, econ events, roll schedule, holidays and half-days.

        ASYNCHRONOUS — duration, not latency; see the docstring. One verb, not
        four, because §6.4 names them as one cache with one freshness stamp: a
        per-category refresh would give the halt rule four ages to reconcile
        where the spec gives it one.
        """

    def publish(self, sets: tuple[WindowSet, ...]) -> None:
        """Publish an ATOMIC snapshot (§12.7). SYNCHRONOUS; see the docstring."""


#: The Protocols on which NO mutating verb may be declared (§6.4's "read caches
#: only"). Read by `check_calendar_schema` off these bytes; the gate supplies
#: its own vocabulary of what counts as mutating, so a bug in one is not
#: automatically a bug in the other.
READ_ONLY_PORTS: tuple[str, ...] = (
    "WindowSetReadPort",
    "MarginBaselineReadPort",
    "RollScheduleReadPort",
)
