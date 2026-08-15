"""§6.1–§6.3 blackout windows — THE PRODUCER OF A PORT THAT ALREADY HAS A RULE.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 033 / Stage 1 / sub-agent A.

------------------------------------------------------------------------------
WHAT THIS MODULE IS, AND WHAT IT DELIBERATELY IS NOT
------------------------------------------------------------------------------
`nixrisk.gate` already assembles §6.5's unified pre-size denial by name:

    SymbolFlagRule("blackout_window", blackout, "§6.1-6.3 EOD/EOW/news-margin/roll-day")

The RULE exists, the port shape exists (`SymbolFlagPort.read(symbol) ->
(blocked, reason)`), the executor that dispatches it exists and is measured by
`checks/check_limiter_gate.py`. **Nothing produced the port.** This module is
that producer and nothing else: `BlackoutEvaluator` satisfies `SymbolFlagPort`
and is passed to `default_manifest(blackout=...)`. No rule class is added, the
manifest is not touched, and `nixrisk/gate.py` is not edited — a class per
window type is exactly the code §6.5 says not to write.

`SymbolFlagRule`'s own docstring states the reason that seam is parameterised:
*"new blackout types are data (a window), not code … the DATA is the cache and
the identity is the name."* This module produces the DATA.

------------------------------------------------------------------------------
THE TWO HALVES, AND WHY THEY ARE SEPARATE OBJECTS
------------------------------------------------------------------------------
* `SessionWindowSource` implements `calendar_seam.WindowSourcePort`. It is the
  §12.3 generation step: (symbol, UTC day) -> windows, every instant already
  UTC. It reads `crucible.calendar`, which does no timezone math at all — the
  exchange-local -> UTC conversion happened once, offline, in
  `crucible/calendar_gen.py`. **This module contains no timezone name, no
  `ZoneInfo` and no local-time arithmetic**, and that is §12.3's "converts
  exchange-local exactly once at window generation" honoured by not doing it a
  second time.
* `BlackoutEvaluator` implements `gate.SymbolFlagPort`. It is the DECISION
  step: it compares `now` against a published window set and against live
  margin. It generates nothing.

They are separate because §6.4 separates them: the poller generates and
publishes, the Limiter *reads caches only*. One class doing both would be a
Limiter that regenerates the calendar on the hot path.

------------------------------------------------------------------------------
§6.5's DISJUNCTION IS FLAT, AND `entry_only` IS NOT AN ENTRY FILTER
------------------------------------------------------------------------------
The unified model is `HALT ∨ now ∈ any window ∨ margin elevated ∨ data stale ∨
clock skewed`. For the ENTRY gate this evaluator therefore denies on **any**
active window — it does not filter by `Window.entry_only` and it does not
branch on `Window.kind`.

That is worth stating because the tempting reading is backwards.
`entry_only=True` does not mean *"this window blocks entries"* (they all do);
it means *"this window blocks entries AND NOTHING ELSE — exits still fire"*
(§6.1). The field is read by the EXIT path, which is not this module. An
evaluator that filtered entries to `entry_only` windows would admit entries
during exactly the windows that block more than entries: the strictest rows
would become the weakest. `checks/check_blackout_windows.py` additionally
proves, on this file's bytes, that no decision path here branches on
`WindowKind`, which `calendar_seam.py` bans in as many words: *"If a future
reader finds a rule switching on `WindowKind`, that rule is the defect."*

------------------------------------------------------------------------------
§6.2's UNION — "widest active leading edge wins"
------------------------------------------------------------------------------
`now ∈ any window` IS the union; a disjunction needs no union operator. What
§6.2 adds is an ATTRIBUTION rule: where several windows are active, the denial
names the one whose leading edge is widest (earliest `start`), tie-broken by
the later `end`. On a Friday the EOD window (`close − 20 min`) and the EOW
window (`close − 30 min`) overlap for the whole of the EOD window's life, and
the denial must name EOW — the narrower window is *contained*, and naming it
would tell an operator the block ends at the next daily open when it actually
runs to Sunday.

------------------------------------------------------------------------------
§6.3's ASYMMETRIC EDGES — the only rule here that carries STATE
------------------------------------------------------------------------------
* **Leading edge = clock.** A scheduled margin-affecting event at `E` produces
  a window `[E − NEWS_BLACKOUT_MIN, E)`. That is all the data can honestly say:
  `WindowKind.NEWS_MARGIN`'s own docstring records that a trailing instant
  would *"claim knowledge §6.3 explicitly does not have"*.
* **Trailing edge = live margin, and it is attached to the SPIKE rather than
  to the window.** Blocked while live margin exceeds the accepted baseline by
  more than `margin_elevated_pct`, and for `margin_min_hold_s` after the last
  elevated observation. **The floor is armed by elevation, never by the
  window's end** — an earlier draft of this module armed it from the window and
  it was wrong twice over: it would have needed a `kind == NEWS_MARGIN` branch
  (banned), and it would have re-introduced a clock-driven trailing edge, which
  is the exact symmetry §6.3 refuses. A scheduled event that moves no margin
  releases immediately, because there is nothing to wait for.
* **Unscheduled spikes come free.** The elevation test reads live margin and
  never asks whether a window explained it, so a spike with no calendar entry
  blocks on the same code path. That is not a bonus — it is *why* the trailing
  edge is reactive rather than a second clock.
* **Anti-lockout re-acceptance.** Margin held continuously elevated for
  `margin_reacceptance_s` is a regime shift, not a spike: the level is accepted
  as the new baseline, an operator alert is raised, and entries resume. §6.3:
  *"A permanent broker hike must never lock the system out forever."*

**Where the re-accepted baseline LIVES, and why it is not a second authority.**
`MarginBaselineReadPort` is read-only to the Limiter (§6.4) — this evaluator
physically cannot publish to it. `risks/limiter.config.json` already records
the resolution in its own `_meta`: *"§6.3's baseline re-acceptance is the sole
runtime-adaptive value and is explicitly STATE, not config."* So the
re-acceptance is held here as STATE and reconciled against the published cache
by §6.4b's ordering rule — **newer `accepted_at` wins, per symbol**. When the
margin poller publishes a baseline stamped later than the local re-acceptance,
the local record is retired and the published one governs. Two records, one
ordering rule, no arbitration invented here.

------------------------------------------------------------------------------
ONSET (§3) — WHAT IS EMITTED AND WHAT IS NOT
------------------------------------------------------------------------------
§6.1: *"Onset cancels pending entry orders (§3)."* §3's release-path list
already carries `TerminalPath.BLACKOUT_ONSET`, so no path is minted here. On
the transition from clear to inside-a-window this evaluator releases the
symbol's outstanding reservations through the injected `ReservationLedgerPort`
— the ledger's own verb, its own idempotency — and emits one `BlackoutOnset`
record naming the window and the released ids.

**It does not talk to the broker.** Cancelling a working order at the venue is
`nixrisk/execution.py`'s and broker-order's job and neither is edited here. The
reservation release is the half that is this module's to do; the record is what
the other half consumes.

**The edge is OBSERVED, not scheduled.** `read()` is called when a proposal
arrives, so an onset occurring while nothing proposes is seen at the next call.
The Limiter's own loop tick, where a scheduled observation belongs, is not
built (`gate.py`: *"a Limiter that gates but cannot exit is not a safety spine
yet"*). `tick()` is exposed for that loop and shares one code path with
`read()`, so wiring it later changes a caller and not a rule. Carried as
CHECK-DEBT rather than papered over.

------------------------------------------------------------------------------
SPEC-A10 — THE CALENDAR SOURCE ROSTER
------------------------------------------------------------------------------
`CALENDAR_SOURCES` is the declared roster of LIVE calendar sources this tree
reads, and today it has exactly one member. `docs/SPEC-AMENDMENTS.md`
`SPEC-A10` records why a conflict-resolution mechanism cannot be built against
it: *"A conflict-resolution rule over one source has nothing to resolve, and a
gate built over it would drive a disagreement it manufactured between two
halves of the same artifact."* What the amendment names as buildable is *"a
gate that reddens if a SECOND calendar source is ever introduced without a
flagging path"*. `record_source_conflict` is that flagging path, and the
invariant `check_blackout_windows` enforces is: **more than one source in the
roster ⇒ this module must statically call it.** No disagreement is simulated
anywhere.

------------------------------------------------------------------------------
`debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS MODULE TO RUN AND
DECIDE NOTHING?
------------------------------------------------------------------------------
1. **The window set is never published**, so `active` is always empty and every
   entry sails through. *Closed:* an absent set, or a cache in
   `CacheState.EMPTY`, is a DENIAL naming the absence — §6.4's fail-closed
   direction. `windows(symbol) -> None` and an empty `WindowSet` are different
   and both are handled, because `calendar_seam` makes them different on
   purpose.
2. **The clock is wrong or naive**, so `now` never lands inside anything.
   *Closed:* a naive `now` is a denial naming the offending value. §12.3 makes
   UTC the invariant, and comparing a naive instant to an aware one raises —
   which would otherwise reach the executor's rule-raised-⇒-deny path carrying
   a `TypeError` for a reason.
3. **The margin arm has no reference level**, so it never fires. *Stated, not
   closed:* with no published baseline the trailing edge has nothing to return
   *to* and the arm abstains — windows still decide. With a baseline held and
   the live figure missing it DENIES, because there the subject exists and the
   reading is what is unavailable (`nix_check_contract.md` §17). The two cases
   are not symmetric and are not collapsed.
4. **The knobs are zero**, so every window has zero width. *Closed:*
   `BlackoutKnobs` range-validates at construction and refuses to build — §12A
   boot validation, applied at the object that reads the numbers.
5. **The calendar's break-class vocabulary moves**, so no EOW window is ever
   emitted and every Friday looks like a Thursday. *Closed:*
   `SessionWindowSource` refuses on an unrecognised class rather than emitting
   fewer windows, because the failure is otherwise invisible — the EOD window
   is still there and every drive still finds a window.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from crucible import calendar as cme_calendar
from crucible.calendar import BreakWindow

from nixrisk.calendar_seam import (
    CacheState,
    MarginBaseline,
    MarginBaselineReadPort,
    Window,
    WindowKind,
    WindowSet,
    WindowSetReadPort,
)
from nixrisk.seam import FinancialPicturePort, ReservationLedgerPort, TerminalPath

__all__ = [
    "CALENDAR_SOURCES",
    "KNOB_KEYS",
    "WEEKEND_BREAK_CLASS",
    "AlertSink",
    "BlackoutEvaluator",
    "BlackoutKnobError",
    "BlackoutKnobs",
    "BlackoutOnset",
    "CalendarQueryPort",
    "OnsetSink",
    "ScheduledEvent",
    "ScheduledEventPort",
    "SessionWindowSource",
    "SourceConflict",
    "UnusableCalendarError",
    "record_source_conflict",
]

# pylint: disable=too-few-public-methods
# Every Protocol below carries exactly the verbs its spec clause gives it, for
# the reason `calendar_seam.py` records at the same disable: on a sink or a
# read port an invented second verb is authority the spec withheld.

#: SPEC-A10. The LIVE calendar sources this tree reads, as repository paths.
#: Exactly one today: the vendored, hash-stamped CME artifact. A ROSTER, not a
#: search path — `check_blackout_windows` reads it statically and requires a
#: flagging path the moment it grows a second member.
CALENDAR_SOURCES: tuple[str, ...] = ("scripts/crucible/calendar_data",)

#: The break-window classification marking a weekend gap in the vendored
#: artifact (`crucible/calendar_ext_gen._classify_break`). §6.2's window is
#: "Friday close -> Sunday open", which is precisely this class, so the EOW
#: window is derived from the artifact's own label rather than from weekday
#: arithmetic repeated here.
WEEKEND_BREAK_CLASS = "WEEKEND"

#: The break classes this module knows how to read. An artifact that returns
#: anything else is a refusal, not a shrug — see `_assert_vocabulary`.
KNOWN_BREAK_CLASSES: frozenset[str] = frozenset(
    {WEEKEND_BREAK_CLASS, "DAILY_BREAK", "HOLIDAY_BREAK"}
)

#: The §12A-derived knob names this module reads out of `risks/`, in one place.
#: Physical layout is `risks/limiter.config.json`; §12A is the semantic
#: authority. Nothing here carries a default — `gate.py`'s rule, for its reason:
#: a default written in code is a second authority that wins whenever a caller
#: forgets the config.
KNOB_KEYS: tuple[str, ...] = (
    "eod_blackout_min",
    "eow_blackout_min",
    "news_blackout_min",
    "margin_elevated_pct",
    "margin_min_hold_s",
    "margin_reacceptance_s",
)


class BlackoutKnobError(ValueError):
    """A §12A tunable outside its admissible range. Raised at construction."""


class UnusableCalendarError(RuntimeError):
    """The vendored calendar cannot answer the question asked of it.

    Raised at window-GENERATION time, never inside a gate pass: generation runs
    on the poller's cadence (§6.4, minutes) and a loud refusal there is a poller
    that stops publishing, which the evaluator turns into a denial. A silently
    empty window set would be an approval.
    """


# ---------------------------------------------------------------------------
# Knobs (§12A)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlackoutKnobs:
    """§12A's blackout tunables as one immutable value, range-validated.

    Three of the six are §12A knobs by name (`EOD_BLACKOUT_MIN`,
    `EOW_BLACKOUT_MIN`, `NEWS_BLACKOUT_MIN`). The other three are declared Nix
    additions, and their absence from §12A is a FINDING rather than an
    oversight — recorded in `risks/limiter.config.json`'s `_derivations` and in
    CHECK-DEBT. §6.3 states a "min-time floor" and a "defined period" for
    re-acceptance and gives neither a knob name, so the one anti-lockout rule
    the spec singles out is unexecutable as written. Landed as data with a
    stated direction of error rather than as a literal in this file.
    """

    eod_blackout_min: float
    eow_blackout_min: float
    news_blackout_min: float
    margin_elevated_pct: float
    margin_min_hold_s: float
    margin_reacceptance_s: float

    def __post_init__(self) -> None:
        """§12A cross-knob boot validation, at the object that reads them."""
        for name in ("eod_blackout_min", "eow_blackout_min", "news_blackout_min"):
            value = float(getattr(self, name))
            if value <= 0.0:
                raise BlackoutKnobError(
                    f"{name} must be > 0, got {value!r} — a blackout of zero "
                    "width is a gate that cannot deny, and it looks exactly "
                    "like a market that is always open (§12A boot validation)"
                )
        if not 0.0 < self.margin_elevated_pct <= 1.0:
            raise BlackoutKnobError(
                f"margin_elevated_pct must be in (0, 1], got "
                f"{self.margin_elevated_pct!r} — at 0 every rounding tick is a "
                "spike and the system never trades; above 1 the trailing edge "
                "ignores a doubling of margin (§6.3)"
            )
        if self.margin_min_hold_s <= 0.0:
            raise BlackoutKnobError(
                f"margin_min_hold_s must be > 0, got "
                f"{self.margin_min_hold_s!r} — §6.3's trailing edge is 'margin "
                "returns to baseline (+ min-time floor)'; a floor of zero "
                "removes the '+'"
            )
        if self.margin_reacceptance_s <= self.margin_min_hold_s:
            raise BlackoutKnobError(
                f"margin_reacceptance_s {self.margin_reacceptance_s!r} must "
                f"exceed margin_min_hold_s {self.margin_min_hold_s!r} — §6.3 "
                "separates a SPIKE (hold, then release) from a REGIME SHIFT "
                "(accept the new baseline). A re-acceptance period inside the "
                "min-time floor re-baselines every ordinary spike, which is "
                "the anti-lockout rule inverted into a rule that never blocks"
            )

    @classmethod
    def from_config(cls, values: Mapping[str, object]) -> BlackoutKnobs:
        """Build from a loaded `risks/` module config. No defaults, ever.

        A refusal rather than `.get(name, default)`, for `risk_config.py`'s own
        stated reason: there is no defaulted read anywhere on the boot path,
        because an absent knob must be a refusal to boot and not a number
        nobody chose.
        """
        missing = [key for key in KNOB_KEYS if key not in values]
        if missing:
            raise BlackoutKnobError(
                f"blackout knobs absent from the loaded config: {missing} — "
                "§12A owns these values and this module holds no default for "
                "any of them"
            )
        return cls(
            eod_blackout_min=float(values["eod_blackout_min"]),  # type: ignore[arg-type]
            eow_blackout_min=float(values["eow_blackout_min"]),  # type: ignore[arg-type]
            news_blackout_min=float(values["news_blackout_min"]),  # type: ignore[arg-type]
            margin_elevated_pct=float(values["margin_elevated_pct"]),  # type: ignore[arg-type]
            margin_min_hold_s=float(values["margin_min_hold_s"]),  # type: ignore[arg-type]
            margin_reacceptance_s=float(values["margin_reacceptance_s"]),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Sinks, ports and event data
# ---------------------------------------------------------------------------


@runtime_checkable
class AlertSink(Protocol):
    """§6.3's operator alert. One verb; the transport is not this module's."""

    def alert(self, code: str, message: str) -> None:
        """Raise one operator-visible alert."""


@runtime_checkable
class CalendarQueryPort(Protocol):
    """The two `crucible.calendar` verbs this module reads. Declared, not new.

    Declared as a Protocol so the calendar is an ARGUMENT: a gate driving a
    plant, or a poller reading a different generation of the artifact, hands in
    its own. `crucible.calendar` itself satisfies it as a module, which is why
    this is a Protocol rather than a wrapper class — a wrapper would be a second
    query surface over one artifact, the shape doctrine C.9 forbids.
    """

    def product_group_of(self, symbol: str) -> str:
        """The product group whose session calendar governs `symbol` (§6.1)."""

    def break_window(self, product_group: str, on_date: object) -> BreakWindow | None:
        """The closed window that FOLLOWS `on_date`'s session, or None."""


@dataclass(frozen=True)
class ScheduledEvent:
    """§6.3's *scheduled margin-affecting event*. `at` is UTC.

    Supplied by the calendar poller (§6.4's "econ events"). **There is no econ
    event artifact in this tree** — `calendar_data/` carries sessions, breaks, a
    symbol map and a roll schedule and nothing else — so this is an INPUT type,
    not a table this module reads. Inventing a placeholder event file would put
    a fabricated calendar on a denial path.
    """

    symbol: str
    at: datetime
    source: str
    label: str = ""


@runtime_checkable
class ScheduledEventPort(Protocol):
    """The poller's econ-event surface, read-only (§6.4)."""

    def events(self, symbol: str) -> tuple[ScheduledEvent, ...]:
        """Scheduled margin-affecting events for one symbol."""


@dataclass(frozen=True)
class BlackoutOnset:
    """§3's blackout-onset cancellation, as a record.

    `via` is `TerminalPath.BLACKOUT_ONSET`, read off the FROZEN seam's own
    enumeration — that member is the spec's list and not the implementation's,
    and minting a parallel string here would put a second spelling of one
    release path into §9's record of money truth.
    """

    symbol: str
    window: Window
    at: datetime
    released: tuple[str, ...]
    via: TerminalPath = TerminalPath.BLACKOUT_ONSET


@runtime_checkable
class OnsetSink(Protocol):
    """Where a blackout onset is reported. One verb."""

    def on_blackout_onset(self, onset: BlackoutOnset) -> None:
        """Record one onset. Called once per clear -> in-window transition."""


@dataclass(frozen=True)
class SourceConflict:
    """SPEC-A10: one disagreement between calendar sources, as a RECORD.

    A value type and not a resolution: SPEC-A10's rule is *"live source wins on
    disagreement; disagreements are logged as flagged events, never silently
    resolved"*, and the second half is what needs somewhere to live.
    """

    field_name: str
    live_value: object
    live_source: str
    other_value: object
    other_source: str
    at: datetime


def record_source_conflict(  # pylint: disable=too-many-arguments
    *,
    field_name: str,
    live_value: object,
    live_source: str,
    other_value: object,
    other_source: str,
    at: datetime,
    alert: AlertSink | None = None,
) -> tuple[object, SourceConflict | None]:
    """SPEC-A10's FLAGGING PATH. Returns `(live_value, conflict_or_None)`.

    Live wins — §6.1/§6.1b/§6.2 windows are evaluated against `now`, and a
    historical source is by construction a record of what was believed earlier.
    That is the uninteresting half. The interesting half is that a disagreement
    is RETURNED and ALERTED so it cannot be resolved silently: a disagreement
    means one source is wrong about when a market is open, and a system that
    discards it has thrown away the only signal anyone would ever have had.

    **Unreachable today, and that is the honest state.** `CALENDAR_SOURCES` has
    one member, so nothing in this tree can call this with two values. The gate
    is what keeps it that way: the moment a second source is declared, this call
    must appear on the window path or `check_blackout_windows` reddens. The
    function exists first so the gate has something to require.
    """
    if live_value == other_value:
        return live_value, None
    conflict = SourceConflict(
        field_name=field_name,
        live_value=live_value,
        live_source=live_source,
        other_value=other_value,
        other_source=other_source,
        at=at,
    )
    if alert is not None:
        alert.alert(
            "calendar_source_conflict",
            (
                f"SPEC-A10: calendar sources disagree on {field_name!r} — live "
                f"{live_source} says {live_value!r}, {other_source} says "
                f"{other_value!r}. The LIVE value governs this live decision "
                "and the disagreement is recorded; it is never silently "
                "resolved"
            ),
        )
    return live_value, conflict


def _require_utc(value: datetime, what: str) -> None:
    """§12.3: all internal time is UTC. A naive instant is a refusal."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{what} {value!r} is naive; §12.3 makes all internal time UTC, and "
            "a naive instant compared against an aware one raises rather than "
            "answering wrongly"
        )


# ---------------------------------------------------------------------------
# Generation (§6.1, §6.2, §6.3's leading edge, §12.3)
# ---------------------------------------------------------------------------


class SessionWindowSource:
    """`WindowSourcePort`: (symbol, UTC day) -> that day's windows, all UTC.

    Reads `crucible.calendar`, whose every returned instant is already a
    resolved UTC instant. **No timezone name appears in this module** and none
    may: §12.3 puts the exchange-local conversion at window generation, and the
    vendored artifact IS that generation, performed once, offline.

    THE ±1 DAY SWEEP. A break window is keyed by the date of the session whose
    close opens it (`crucible.calendar.break_window`), and a UTC day is not a CT
    trade date. A window keyed to the previous trade date can still be live
    inside this UTC day and one keyed to the next can already have started, so
    three trade dates are swept and the caller is handed the union. Sweeping
    only the requested day would drop the EOD window across the UTC midnight
    boundary — a hole in the middle of the blackout it is supposed to be.
    """

    def __init__(
        self,
        knobs: BlackoutKnobs,
        calendar: CalendarQueryPort | None = None,
    ) -> None:
        self._knobs = knobs
        self._calendar: CalendarQueryPort = calendar or cme_calendar  # type: ignore[assignment]

    def windows_for(self, symbol: str, day: datetime) -> tuple[Window, ...]:
        """§6.1's EOD and §6.2's EOW windows covering the UTC day of `day`."""
        _require_utc(day, "day")
        group = self._calendar.product_group_of(symbol)
        target = day.astimezone(UTC).date()
        seen: set[tuple[str, datetime, datetime]] = set()
        out: list[Window] = []
        classes: set[str] = set()
        for offset in (-1, 0, 1):
            brk = self._calendar.break_window(group, target + timedelta(days=offset))
            if brk is None:
                continue
            classes.add(brk.klass)
            for window in self._windows_of_break(symbol, group, brk):
                key = (window.kind.value, window.start, window.end)
                if key not in seen:
                    seen.add(key)
                    out.append(window)
        self._assert_vocabulary(symbol, group, target, classes)
        return tuple(sorted(out, key=lambda w: (w.start, w.end)))

    def _windows_of_break(
        self, symbol: str, group: str, brk: BreakWindow
    ) -> list[Window]:
        """§6.1 always; §6.2 additionally where the gap IS the weekend."""
        stamp = f"crucible.calendar:{group}:{brk.date}:{brk.klass}"
        windows = [
            Window(
                kind=WindowKind.EOD,
                symbol=symbol,
                start=brk.start - timedelta(minutes=self._knobs.eod_blackout_min),
                end=brk.end,
                entry_only=True,
                source=stamp,
            )
        ]
        if brk.klass == WEEKEND_BREAK_CLASS:
            windows.append(
                Window(
                    kind=WindowKind.EOW,
                    symbol=symbol,
                    start=brk.start - timedelta(minutes=self._knobs.eow_blackout_min),
                    end=brk.end,
                    entry_only=True,
                    source=stamp,
                )
            )
        return windows

    def _assert_vocabulary(
        self, symbol: str, group: str, target: object, classes: set[str]
    ) -> None:
        """Fail closed if the artifact's break-class vocabulary moved.

        Without this, renaming `WEEKEND` in the generator would stop every EOW
        window being emitted and NOTHING would say so — the EOD window is still
        there, so every drive still finds a window and every test still passes
        while §6.2 has quietly ceased to exist.
        """
        if not classes:
            raise UnusableCalendarError(
                f"no break window at all for {symbol!r} ({group}) on any of the "
                f"three trade dates around {target} — the vendored calendar "
                "cannot say when this symbol's session ends, so §6.1's window "
                "cannot be built, and an empty window set reads as 'clear'"
            )
        unknown = classes - KNOWN_BREAK_CLASSES
        if unknown:
            raise UnusableCalendarError(
                f"vendored calendar returned break class(es) {sorted(unknown)} "
                f"for {symbol!r} ({group}) around {target}; this module knows "
                f"{sorted(KNOWN_BREAK_CLASSES)}. §6.2's window is keyed off "
                f"{WEEKEND_BREAK_CLASS!r}, so an unrecognised vocabulary means "
                "the weekend blackout may be silently absent"
            )

    def news_windows(
        self, symbol: str, events: Sequence[ScheduledEvent]
    ) -> tuple[Window, ...]:
        """§6.3's LEADING edge only: `[event − NEWS_BLACKOUT_MIN, event)`.

        The trailing edge is deliberately not here. `WindowKind.NEWS_MARGIN`:
        the reactive edge *"is therefore NOT expressible as a pre-computed
        instant; a window carrying a fabricated end instant would claim
        knowledge §6.3 explicitly does not have."* `BlackoutEvaluator` holds it
        open against live margin.
        """
        lead = timedelta(minutes=self._knobs.news_blackout_min)
        out: list[Window] = []
        for event in events:
            if event.symbol != symbol:
                continue
            _require_utc(event.at, f"event {event.label or event.source}")
            source = f"{event.source}:{event.label}" if event.label else event.source
            out.append(
                Window(
                    kind=WindowKind.NEWS_MARGIN,
                    symbol=symbol,
                    start=event.at - lead,
                    end=event.at,
                    entry_only=True,
                    source=source,
                )
            )
        return tuple(sorted(out, key=lambda w: (w.start, w.end)))

    def window_set(
        self,
        symbol: str,
        day: datetime,
        events: Sequence[ScheduledEvent] = (),
    ) -> WindowSet:
        """One publishable `WindowSet` for `symbol` over the UTC day of `day`."""
        windows = self.windows_for(symbol, day) + self.news_windows(symbol, events)
        return WindowSet(
            symbol=symbol,
            windows=tuple(sorted(windows, key=lambda w: (w.start, w.end))),
            generated_at=day.astimezone(UTC),
        )


# ---------------------------------------------------------------------------
# The evaluator (§6.5's pre-size disjunction, the per-symbol half)
# ---------------------------------------------------------------------------


@dataclass
class _MarginState:
    """§6.3's per-symbol trailing-edge state. The only mutable thing here."""

    elevated_since: datetime | None = None
    hold_until: datetime | None = None
    re_accepted: MarginBaseline | None = None
    window_key: tuple[str, datetime, datetime] | None = None


@dataclass(frozen=True)
class _Verdict:
    """One arm's answer. `window` is set only where a window decided."""

    blocked: bool
    reason: str
    window: Window | None = None


class BlackoutEvaluator:  # pylint: disable=too-many-instance-attributes
    """`gate.SymbolFlagPort`: §6.1–§6.3 as `(blocked, reason)`, per symbol.

    Constructed once at boot and handed to `gate.default_manifest` as its
    `blackout` port. Every port argument is required and keyword-only: this
    object decides whether an entry is legal, and a defaulted port here would be
    a permissive stand-in that silently survives a wiring mistake.

    The instance-attribute count is above pylint's default and the disable is
    deliberate: the ports are §6.4's separate caches — windows, baselines, and
    the one unified picture — which the spec keeps separate on purpose, plus the
    knobs and the sinks. Bundling them into a context object to satisfy a
    counter would hide which cache a denial came from.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        windows: WindowSetReadPort,
        baselines: MarginBaselineReadPort,
        picture: FinancialPicturePort,
        clock: Callable[[], datetime],
        knobs: BlackoutKnobs,
        alert: AlertSink | None = None,
        onset: OnsetSink | None = None,
        ledger: ReservationLedgerPort | None = None,
    ) -> None:
        self._windows = windows
        self._baselines = baselines
        self._picture = picture
        self._clock = clock
        self._knobs = knobs
        self._alert = alert
        self._onset = onset
        self._ledger = ledger
        self._state: dict[str, _MarginState] = {}

    # -- the port -----------------------------------------------------------

    def read(self, symbol: str) -> tuple[bool, str]:
        """`(blocked, reason)` for one symbol — the §11.1 shape the rule reads."""
        return self.tick(symbol)

    def tick(self, symbol: str) -> tuple[bool, str]:
        """The same decision, named for the Limiter loop rather than the gate.

        One code path, two callers. The loop tick is what would make §6.1's
        onset cancellation punctual rather than proposal-driven; that loop is
        not built, so nothing calls this today and CHECK-DEBT carries the row.
        """
        try:
            now = self._clock()
            _require_utc(now, "now")
        except ValueError as exc:
            return True, (
                "§12.3 clock integrity: the blackout evaluator cannot place "
                f"'now' on the UTC timeline ({exc}). A window rule that cannot "
                "read the clock has not cleared anything"
            )
        verdict = self._decide(symbol, now)
        self._observe_edge(symbol, verdict, now)
        return verdict.blocked, verdict.reason

    # -- the decision -------------------------------------------------------

    def _decide(self, symbol: str, now: datetime) -> _Verdict:
        """§6.5's disjunction over the two arms this port owns."""
        window_verdict = self._window_arm(symbol, now)
        margin_verdict = self._margin_arm(symbol, now)
        if window_verdict.blocked and margin_verdict.blocked:
            return _Verdict(
                True,
                f"{window_verdict.reason} | ALSO: {margin_verdict.reason}",
                window_verdict.window,
            )
        if window_verdict.blocked:
            return window_verdict
        if margin_verdict.blocked:
            return margin_verdict
        return _Verdict(False, "")

    def _window_arm(self, symbol: str, now: datetime) -> _Verdict:
        """`now ∈ any window`, kind-agnostic and `entry_only`-agnostic (§6.5)."""
        state = self._windows.state()
        published = self._windows.windows(symbol)
        if published is None or state is CacheState.EMPTY:
            return _Verdict(
                True,
                (
                    "§6.4 fail-closed: no window set is published for "
                    f"{symbol!r} (cache state {state.value!r}). §6.1-6.3 cannot "
                    "be evaluated against a set that does not exist, and an "
                    "unpublished symbol must not be indistinguishable from a "
                    "clear one (nix_check_contract.md §17)"
                ),
            )
        active = [w for w in published.windows if w.start <= now < w.end]
        if not active:
            return _Verdict(False, "")
        # §6.2: the widest active leading edge wins. Earliest start, then the
        # later end, so a contained window never speaks for the one that
        # contains it.
        binding = min(active, key=lambda w: (w.start, -w.end.timestamp()))
        others = sorted(w.kind.value for w in active if w is not binding)
        also = f"; {len(others)} other active window(s) {others}" if others else ""
        return _Verdict(
            True,
            (
                f"§6.1-6.3 blackout: {symbol} is inside the "
                f"{binding.kind.value} window [{binding.start.isoformat()}, "
                f"{binding.end.isoformat()}) at {now.isoformat()} (source "
                f"{binding.source}){also}. §6.2: the widest active leading edge "
                "wins, so the denial names the window that opened earliest"
            ),
            binding,
        )

    def _margin_arm(self, symbol: str, now: datetime) -> _Verdict:
        """§6.3's trailing edge, unscheduled spikes, and the anti-lockout path."""
        state = self._state.setdefault(symbol, _MarginState())
        baseline = self._effective_baseline(symbol, state)
        if baseline is None:
            return _Verdict(False, "")
        live = self._picture.current().margin_per_contract.get(symbol)
        if live is None:
            return _Verdict(
                True,
                (
                    "§6.3 trailing edge: a margin baseline is held for "
                    f"{symbol!r} ({baseline.level!r}, accepted "
                    f"{baseline.accepted_at.isoformat()}) but the published "
                    "financial picture carries no live margin for it. The "
                    "reactive edge cannot be evaluated, and a safety property "
                    "proven while its subject is unavailable is not proven "
                    "(nix_check_contract.md §17)"
                ),
            )
        ceiling = baseline.level * (1.0 + self._knobs.margin_elevated_pct)
        if live > ceiling:
            return self._elevated(symbol, state, now, baseline, live, ceiling)
        state.elevated_since = None
        if state.hold_until is not None and now < state.hold_until:
            return _Verdict(
                True,
                (
                    f"§6.3 min-time floor: {symbol} margin has returned to "
                    f"baseline ({live!r} <= {ceiling!r}) but the floor runs to "
                    f"{state.hold_until.isoformat()} and now is "
                    f"{now.isoformat()}. The trailing edge is 'margin returns "
                    "to baseline (+ min-time floor)', and the floor is the part "
                    "that stops a one-tick dip reopening entries mid-event"
                ),
            )
        state.hold_until = None
        return _Verdict(False, "")

    def _elevated(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        symbol: str,
        state: _MarginState,
        now: datetime,
        baseline: MarginBaseline,
        live: float,
        ceiling: float,
    ) -> _Verdict:
        """Margin is above the accepted level: hold, or re-accept (§6.3)."""
        if state.elevated_since is None:
            state.elevated_since = now
        held = (now - state.elevated_since).total_seconds()
        if held >= self._knobs.margin_reacceptance_s:
            state.re_accepted = MarginBaseline(
                symbol=symbol, level=live, accepted_at=now, re_accepted=True
            )
            state.elevated_since = None
            state.hold_until = None
            if self._alert is not None:
                self._alert.alert(
                    "margin_baseline_re_accepted",
                    (
                        f"§6.3 anti-lockout: {symbol} margin held at {live!r} "
                        f"(above {ceiling!r}) for {held:.0f}s, beyond the "
                        f"{self._knobs.margin_reacceptance_s:.0f}s "
                        f"re-acceptance period. Accepting {live!r} as the new "
                        "baseline — this is a regime shift and not a spike, and "
                        "a permanent broker hike must never lock the system out "
                        "forever. Sizing shrinks naturally via margin_contracts"
                    ),
                )
            return _Verdict(False, "")
        state.hold_until = now + timedelta(seconds=self._knobs.margin_min_hold_s)
        return _Verdict(
            True,
            (
                f"§6.3 margin elevated: {symbol} live margin {live!r} exceeds "
                f"the accepted baseline {baseline.level!r} x (1 + "
                f"{self._knobs.margin_elevated_pct:.4g}) = {ceiling!r}, held "
                f"for {held:.0f}s of the "
                f"{self._knobs.margin_reacceptance_s:.0f}s re-acceptance "
                "period. The trailing edge is live margin, so an UNSCHEDULED "
                "spike blocks on this same path with no calendar entry at all"
            ),
        )

    def _effective_baseline(
        self, symbol: str, state: _MarginState
    ) -> MarginBaseline | None:
        """Published vs locally re-accepted, ordered by `accepted_at` (§6.4b).

        §6.4b orders every venue-sourced reading "by source-of-truth time, never
        by arrival time", per key. The same rule settles the one place this
        module holds state the poller also owns: whichever record was accepted
        LATER governs, and a published baseline newer than the local
        re-acceptance retires it. No arbitration is invented here.
        """
        published = self._baselines.baseline(symbol)
        local = state.re_accepted
        if local is None:
            return published
        if published is not None and published.accepted_at >= local.accepted_at:
            state.re_accepted = None
            return published
        return local

    # -- §3 onset -----------------------------------------------------------

    def _observe_edge(self, symbol: str, verdict: _Verdict, now: datetime) -> None:
        """Emit §3's blackout onset exactly once per clear -> in-window edge."""
        state = self._state.setdefault(symbol, _MarginState())
        window = verdict.window
        key = None if window is None else (window.kind.value, window.start, window.end)
        entered = key is not None and state.window_key is None
        state.window_key = key
        if entered and window is not None:
            self._fire_onset(symbol, window, now)

    def _fire_onset(self, symbol: str, window: Window, now: datetime) -> None:
        """Release the symbol's reservations and record the onset."""
        released: list[str] = []
        if self._ledger is not None:
            for reservation in self._ledger.outstanding():
                if reservation.symbol != symbol:
                    continue
                self._ledger.release(
                    reservation.reservation_id,
                    TerminalPath.BLACKOUT_ONSET,
                    now.timestamp(),
                )
                released.append(reservation.reservation_id)
        if self._onset is not None:
            self._onset.on_blackout_onset(
                BlackoutOnset(
                    symbol=symbol,
                    window=window,
                    at=now,
                    released=tuple(released),
                )
            )
