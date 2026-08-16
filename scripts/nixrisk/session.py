"""§6.1b's session-close flatten — the intraday-only mandate, BY CONSTRUCTION.

ARC 033 / Stage 1 / sub-agent B. Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md` unless another document is named on the
line.

§6.1b:339, verbatim: *"The never-hold-overnight mandate is enforced **by
construction**, not by convention"*. §6.1b:340-342 gives the mechanism: at
`SESSION_FLATTEN_LEAD_MIN` before each symbol's session close — same live
calendar as §6.1, clock-driven UTC per §12.3 — the Limiter force-flattens all
open positions in that symbol with `reason=session`.

WHY A NEW MODULE AND NOT A BRANCH INSIDE `flatten.py` (doctrine C.9). This is a
SCHEDULER, not a second executor. `nixrisk.flatten.ProtectiveFlatten` remains the
one place a flatten is issued (§14: *execution of any flatten is Limiter-only*),
and nothing here calls the broker. What this module owns is the half §6.1b adds
and `flatten.py` deliberately withheld: the DEADLINE, the once-per-session latch,
the §12.6 honesty clause at that deadline, and the §12.9 alert tier. Sub-agent
C's net-liq watch (`nixrisk.survival`) has exactly this shape already — detection
here, execution there — and that split is the reason this file exists rather than
a `if trigger is SESSION_CLOSE` inside the executor.

===========================================================================
THE TWO ADDITIVE EDITS THIS MODULE FORCED ON `flatten.py`, AND WHY
===========================================================================
1. **`FlattenTrigger.SESSION_CLOSE` left `_R4_TRIGGERS`.** ARC 029 refused it
   with the reason *"needs the R4 session calendar (§6.1b)"*. ARC 033 / Phase 0.4
   landed that calendar (`scripts/crucible/calendar.py`'s per-symbol extensions
   and `nixrisk/calendar_seam.py`'s read ports). The refusal was a statement
   about an unbuilt mechanism, and the mechanism is built; leaving it in place
   would make the executor refuse the one trigger this module exists to fire.
   `SENTINEL` stays refused — it is the executor that runs when the Limiter is
   DEAD, which no live Limiter issues, and that reason has not changed.
2. **`fire(..., reason=...)`**, optional and defaulted to the pre-existing
   derived string. §6.1b:352 fixes the wire word: *"strategy receives `closed,
   reason=session`"*. The executor derived its reason from the trigger NAME
   (`session_close`), which is a different string, and §6.1b names this one. A
   scheduler that passed the trigger and hoped the derived string was close
   enough would be publishing a reason no clause authorises.

===========================================================================
§12.6 — THE HONESTY CLAUSE. THIS IS THE DEFECT CLASS THE MODULE IS SHAPED BY
===========================================================================
§12.6:641-642, verbatim: *"a halted market cannot be flattened by any design;
exposure rides until reopen, then protective rules act."* §6.1b:349-351 routes
the deadline's failure ladder straight into it and adds the tier: **Critical
alert**.

The failure to make impossible is ARC 022's F13 — `ok=True` reported over a lost
bar. Its shape is a success flag computed from *"we performed the action"*
rather than from *"the world changed"*. Three mechanisms, none of them prose:

* **THERE IS NO BOOLEAN.** `SessionFlattenOutcome` carries a
  `SessionFlattenVerdict`, a five-member enumeration, and no `ok`, `success` or
  `flattened` field exists anywhere in this module. A caller cannot read a
  truthy value off a ridden exposure because there is no truthy value to read.
* **THE VERDICT IS DERIVED FROM BROKER TRUTH, NOT FROM THE CALL.**
  `_verdict_after_fire` takes a `ConfirmedFlat` — the §4
  reconcile-then-publish product, built from `query_positions`/`query_balance`
  AFTER the flatten — and the symbol. It is never handed a "did we call fire"
  flag, so no code path can construct `FLAT_CONFIRMED` out of having tried.
* **THE RESIDUAL RISK IS ON THE OUTCOME, WHERE THE READER MEETS IT.**
  `SessionFlattenOutcome.residual_risk` is a non-empty sentence on exactly the
  verdicts where exposure rides, and empty on the others. §12.6 requires the
  residual risk be *documented honestly*; a document nobody opens at 15:50 UTC
  is not where that belongs, so it rides the value the operator's alert quotes.

The two exposure-rides verdicts are DISTINCT and both distinct from a clean
flatten:

* `EXPOSURE_RIDES_MARKET_HALTED` — the venue was halted/limit-locked/closed (or
  its state could not be determined) AT the deadline, so **no order was sent at
  all**. §4:231-235's market-tradable guard: the system does not fire orders
  into a shut market; *"Flatten-to-flat stays the rule; it is guarded, never
  blind."*
* `EXPOSURE_RIDES_UNCONFIRMED` — the venue looked tradable, the flatten WAS
  sent, and broker truth afterwards still shows the symbol. That is the §4
  indeterminate path resolving to *not flat*, and it is a different operator
  action from the first, so it is a different member.

===========================================================================
`debug.md` §7.12 — THE STANDING QUESTION FOR THIS MODULE
===========================================================================
*What would have to be true for this scheduler to run and enforce nothing?*

1. **The deadline never arrives**, because `now` is fed from a clock that never
   crosses it. GUARDED IN THE GATE, not here: a module cannot make its caller
   advance time. `checks/check_session_flatten.py` and
   `scripts/tests/test_session_flatten.py` both DRIVE `now` from before the
   deadline to after it and assert the before-tick fired nothing and the
   after-tick fired — a suite that only ever samples one instant is the vacuous
   case and is asserted against.
2. **No symbol is ever due**, because the calendar returns `None` for every
   close. GUARDED: `tick` counts the symbols it EVALUATED, and
   `SessionFlattenSweep.evaluated` carries it; a sweep that evaluated zero
   symbols is visible in the value rather than reported as a quiet all-clear.
   `UnknownSessionClose` is raised where a symbol under management has no close
   at all, because a managed symbol with no deadline is a symbol with no
   backstop (directive 4).
3. **The book is always empty**, so the flatten always has nothing to close and
   `FLAT_CONFIRMED` is free. GUARDED: `NOTHING_OPEN` is its own verdict and is
   NOT `FLAT_CONFIRMED`. The two are told apart by the pre-fire book, so a
   drive that never opens a position cannot produce the confirmed-flat verdict
   at all.
4. **The latch suppresses every fire**, so the deadline passes silently on the
   second and every subsequent tick. GUARDED: the latch is keyed by
   `(symbol, session_close)`, so a NEW session close re-arms it; and
   `already_fired` is a distinct verdict-free path reported as
   `SessionFlattenSweep.suppressed`, not folded into the fired count.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from nixrisk.flatten import CloseTarget, ConfirmedFlat, ProtectiveFlatten
from nixrisk.seam import FinancialPicture, FlattenTrigger, PositionState
from nixrisk.survival import Alert, AlertSink, AlertTier

__all__ = [
    "OPEN_STATES",
    "SESSION_FLATTEN_EVENT",
    "SESSION_REASON",
    "OpenBookReadPort",
    "SessionCloseReadPort",
    "SessionFlattenOutcome",
    "SessionFlattenSweep",
    "SessionFlattenVerdict",
    "SessionFlattener",
    "SessionScheduleError",
    "UnknownSessionClose",
    "VenueState",
    "VenueStateReadPort",
]

# pylint: disable=too-few-public-methods
# Every Protocol below carries exactly the verbs its clause names. On a READ
# port an invented second verb is authority the spec withheld — the reasoning
# `nixrisk/calendar_seam.py` records for its own four.

#: §6.1b:342's wire word, verbatim and in ONE place. The strategy receives
#: `closed, reason=session`; the trigger is named `session_close` and the two
#: are NOT the same string, which is why this constant exists rather than a
#: `trigger.value` read at the call site.
SESSION_REASON = "session"

#: The §12.9 alert `event` field for every alert this module raises. One name,
#: three tiers — the tier carries the severity, the event carries the subject,
#: which is the split `nixrisk/survival.py` already uses for its breach/drift
#: pair and is why this module does not invent a second vocabulary.
SESSION_FLATTEN_EVENT = "session_close_flatten"

#: Position states that are live exposure at the deadline. Identical in content
#: to `flatten._LIVE_STATES` and deliberately NOT imported from it: that name is
#: private to the executor and describes what a RECONCILE treats as live, while
#: this describes what a DEADLINE treats as open. They agree today; binding them
#: together would make a later divergence in one silently change the other.
OPEN_STATES: frozenset[PositionState] = frozenset(
    {PositionState.OPEN, PositionState.CLOSING}
)


class SessionScheduleError(RuntimeError):
    """Base for every refusal this scheduler raises. Never caught internally."""


class UnknownSessionClose(SessionScheduleError):
    """A managed symbol whose session close the calendar cannot supply.

    LOUD rather than skipped (directive 4). §6.1b's guarantee is that a position
    lifecycle *cannot cross a session boundary*; a symbol with no known close has
    no deadline, therefore no backstop, and a scheduler that quietly skipped it
    would report an all-clear sweep over an unprotected book.
    """


# ---------------------------------------------------------------------------
# The read ports — narrow, and each one names the clause that shapes it
# ---------------------------------------------------------------------------


@runtime_checkable
class SessionCloseReadPort(Protocol):
    """§6.1b:340's *"same live calendar as §6.1"*, narrowed to the one question.

    SYNCHRONOUS, and the reason is §6.1b's own: the deadline is compared on the
    Limiter's single-threaded loop (§5) against a clock, and an awaitable close
    lookup admits a suspension between reading the close and reading `now` — at
    which point the deadline is a function of scheduling order. The same
    argument `nixrisk/calendar_seam.py` gives `RollScheduleReadPort`.

    Returns a timezone-aware UTC instant or `None`. `None` means *the calendar
    does not cover this instant for this symbol* and is never a guess: §12.3
    puts every internal instant in UTC and the conversion happens exactly once
    at window generation, so a scheduler inventing a close would be a second
    conversion against a different tzdb state.
    """

    def next_close(self, symbol: str, at: datetime) -> datetime | None:
        """The next session close at or after `at` (UTC), or `None`."""


class VenueState(enum.Enum):
    """Whether the venue can accept the flatten AT the deadline (§12.6, §4).

    FOUR members and not a boolean, because the three non-tradable cases reach
    the operator differently and a boolean would collapse them into one page.
    `UNKNOWN` is a member rather than an exception for the same reason §6.4's
    cache is EMPTY before FRESH: *cannot determine* must not be silently
    indistinguishable from *fine*, and it must fail closed (§4:231-235 — the
    system does not fire orders into a market it cannot see).
    """

    TRADABLE = "tradable"
    #: §12.6 — exchange halt or limit-lock. The clause this module is shaped by.
    HALTED = "halted"
    #: The session is not open at all (weekend, holiday, maintenance break).
    CLOSED = "closed"
    #: The venue state could not be determined. Treated exactly as untradable.
    UNKNOWN = "unknown"


@runtime_checkable
class VenueStateReadPort(Protocol):
    """Is the venue tradable for `symbol` at `at`? (§12.6, §4's guard.)

    **THIS IS NOT §12.5's HALT** and must never be confused with it. §12.5's HALT
    is a state NIX sets on ITSELF (stale data, clock skew, crash loop, operator);
    this is the EXCHANGE's state, which Nix observes and cannot set. Nothing here
    implements, sets or clears the §12.5 flag — that is a separate subsystem —
    and this port exists only so the deadline can tell §12.6's honesty case apart
    from a clean fire.
    """

    def venue_state(self, symbol: str, at: datetime) -> VenueState:
        """The venue's tradability for `symbol` at UTC instant `at`."""


@runtime_checkable
class OpenBookReadPort(Protocol):
    """The Limiter's own position table (§3's one atomic snapshot).

    `nixrisk.picture.FinancialPictureBook` satisfies this structurally. Declared
    narrow, and READ-ONLY, because §6.1b makes this module a DETECTOR: it reads
    the book to find what is open and hands targets to the executor. A `commit`
    or `publish` verb here would put a second writer on §9's sole-writer path.
    """

    def current(self) -> FinancialPicture:
        """The Limiter's own copy of the position table (§12.7's mirror model)."""


# ---------------------------------------------------------------------------
# The verdict — five members, no boolean, and the honesty case is TWO of them
# ---------------------------------------------------------------------------


class SessionFlattenVerdict(enum.Enum):
    """What one symbol's deadline evaluation actually established.

    There is no `ok`. Read the module docstring's §12.6 section for why: a
    success flag computed from *we performed the action* is ARC 022's F13, and
    the deadline is precisely where that defect would be most expensive.
    """

    #: `now` has not reached this symbol's deadline. Nothing was attempted.
    NOT_DUE = "not_due"
    #: The deadline arrived and the book held no live exposure in this symbol.
    #: DISTINCT from `FLAT_CONFIRMED`: nothing was closed because nothing was
    #: open, which is not the same fact as a flatten confirming flat.
    NOTHING_OPEN = "nothing_open"
    #: The flatten fired and broker truth afterwards no longer shows the symbol.
    #: The ONLY verdict that may be read as "the mandate held".
    FLAT_CONFIRMED = "flat_confirmed"
    #: §12.6 — the venue was halted / limit-locked / closed / unreadable AT the
    #: deadline. NO ORDER WAS SENT. Exposure rides until reopen (§12.6:642).
    EXPOSURE_RIDES_MARKET_HALTED = "exposure_rides_market_halted"
    #: The flatten WAS sent and broker truth afterwards STILL shows the symbol.
    #: §4's indeterminate path resolving to not-flat. Exposure rides.
    EXPOSURE_RIDES_UNCONFIRMED = "exposure_rides_unconfirmed"

    @property
    def exposure_rides(self) -> bool:
        """True where a position survived its own session-close deadline.

        The one predicate a caller may branch on, and it is derived from the
        member rather than stored, so a new member cannot be added without
        landing on one side of it.
        """
        return self in _RIDING_VERDICTS

    @property
    def alert_tier(self) -> AlertTier:
        """§6.1b:353 — *Info-tier on clean fire; failure paths land in the
        existing Critical machinery.* The mapping is HERE, on the verdict, so an
        exposure-rides verdict cannot be raised at Info by a caller that forgot.
        """
        return AlertTier.CRITICAL if self.exposure_rides else AlertTier.INFO


#: The verdicts on which a position outlived its deadline. Named as a set so
#: `exposure_rides` is a membership test over a written-down list rather than an
#: `in (a, b)` inline that a sixth member could be added beside unnoticed.
_RIDING_VERDICTS: frozenset[SessionFlattenVerdict] = frozenset(
    {
        SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED,
        SessionFlattenVerdict.EXPOSURE_RIDES_UNCONFIRMED,
    }
)

#: §12.6:641-642's residual risk, per riding verdict, in the words the operator
#: reads. Empty for every non-riding verdict — an outcome that states a residual
#: risk it does not have is as misleading as one that hides the risk it does.
_RESIDUAL_RISK: Mapping[SessionFlattenVerdict, str] = {
    SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED: (
        "§12.6: a halted market cannot be flattened by any design. No order was "
        "sent — firing into a shut venue is refused by §4's market-tradable "
        "guard. The position REMAINS OPEN across the session boundary and the "
        "§6.1b intraday-only guarantee DOES NOT HOLD for it. Exposure rides "
        "until reopen, when protective rules act."
    ),
    SessionFlattenVerdict.EXPOSURE_RIDES_UNCONFIRMED: (
        "§4 + §12.6: the flatten WAS sent and broker truth afterwards STILL "
        "shows this symbol. The position is NOT confirmed flat, so the §6.1b "
        "intraday-only guarantee DOES NOT HOLD for it. Exposure rides; the "
        "Limiter keeps the row CLOSING and re-reconciles."
    ),
}


# ---------------------------------------------------------------------------
# Value records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionFlattenOutcome:  # pylint: disable=too-many-instance-attributes
    # Nine fields, each a distinct fact the §6.1b deadline produces: which
    # symbol, the two instants that define the deadline, the verdict, what was
    # targeted, what broker truth said, the venue's state, the residual-risk
    # sentence, and the alert raised. A frozen record with no behaviour; the
    # class-shape threshold is about behavioural classes accreting state.
    """One symbol's deadline evaluation. The unit a caller branches on.

    `confirmed` is the §4 reconcile product and is `None` on the two paths that
    never reached a reconcile (`NOT_DUE`, `NOTHING_OPEN`) and on
    `EXPOSURE_RIDES_MARKET_HALTED`, where no order was sent. That `None` is
    itself informative and is why the field is not defaulted to an empty
    `ConfirmedFlat`: a synthesised confirmation would claim a broker poll that
    never happened.
    """

    symbol: str
    session_close: datetime
    deadline: datetime
    verdict: SessionFlattenVerdict
    targets: tuple[CloseTarget, ...]
    venue: VenueState
    confirmed: ConfirmedFlat | None
    residual_risk: str
    alert: Alert | None

    @property
    def exposure_rides(self) -> bool:
        """Delegates to the verdict. Never stored — one authority, one answer."""
        return self.verdict.exposure_rides


@dataclass(frozen=True)
class SessionFlattenSweep:
    """One `tick`: every managed symbol evaluated at ONE instant.

    `evaluated` is `debug.md` §7.12 answer 2 made structural — a sweep that
    looked at nothing says so in the value, instead of returning an empty
    outcome list a caller reads as "all clear". `suppressed` is answer 4: a
    symbol whose deadline already fired this session is counted separately from
    one that was not due, because the two are different facts about the book.
    """

    at: datetime
    evaluated: int
    suppressed: tuple[str, ...]
    outcomes: tuple[SessionFlattenOutcome, ...]

    @property
    def riding(self) -> tuple[SessionFlattenOutcome, ...]:
        """Every outcome on which exposure survived its deadline (§12.6)."""
        return tuple(outcome for outcome in self.outcomes if outcome.exposure_rides)

    @property
    def fired(self) -> tuple[SessionFlattenOutcome, ...]:
        """Every outcome where a deadline was reached with live exposure."""
        return tuple(
            outcome
            for outcome in self.outcomes
            if outcome.verdict is not SessionFlattenVerdict.NOT_DUE
            and outcome.verdict is not SessionFlattenVerdict.NOTHING_OPEN
        )


# ---------------------------------------------------------------------------
# The scheduler
# ---------------------------------------------------------------------------


class SessionFlattener:  # pylint: disable=too-many-instance-attributes
    # Six injected collaborators (calendar, venue, book, executor, alert sink,
    # clock) plus the per-symbol lead map and the latch. Each is one port §6.1b
    # names or one piece of the deadline's own memory.
    """§6.1b's deadline. DETECTION here; EXECUTION stays in `flatten.py` (§14).

    Owned by the Limiter's single-threaded loop (§5) and driven by `tick(now)`,
    where `now` is a timezone-aware UTC instant (§12.3). Nothing in this class
    reads a wall clock of its own by default — the clock is injected — because a
    deadline that samples `datetime.now()` internally cannot be driven across
    itself by any test, which is exactly `debug.md` §7.12 answer 1.

    `reconcile` is the caller's: `tick` is synchronous because it runs on the
    §5 loop and the protective fire is zero-wire (§14), while §4's reconcile is
    the one async, off-hot-path verb. `tick_async` is the awaitable wrapper that
    performs the fire AND the reconcile in one motion, and it is the entry point
    the honesty clause needs, because the honest verdict is only knowable after
    broker truth is read back.
    """

    # too-many-arguments: six keyword-only collaborators, each a port §6.1b or
    # §12.6 names. None is defaulted except the clock, and a defaulted alert
    # sink would let a Critical page fan out into a black hole.
    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        calendar: SessionCloseReadPort,
        venue: VenueStateReadPort,
        book: OpenBookReadPort,
        executor: ProtectiveFlatten,
        alert: AlertSink,
        lead_min: Mapping[str, float],
        symbols: Sequence[str],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._calendar = calendar
        self._venue = venue
        self._book = book
        self._executor = executor
        self._alert = alert
        #: symbol -> SESSION_FLATTEN_LEAD_MIN, the per-symbol effective value
        #: §12A:820 declares ("per-symbol override"). Built by
        #: `risk_config.session_flatten_lead_min`, off the SAME `_session_pairs`
        #: resolution the boot rule judged, and never re-derived here: a second
        #: resolution is a second authority that can disagree with the one the
        #: ordering invariant was validated against, and the deadline that fires
        #: would then not be the deadline boot validation approved.
        self._lead_min = dict(lead_min)
        self._symbols = tuple(symbols)
        self._clock = clock
        #: (symbol, session_close) -> the outcome already produced. Keyed by the
        #: CLOSE, so the next session re-arms the deadline automatically and a
        #: latch cannot outlive the session it belongs to.
        self._fired: dict[tuple[str, datetime], SessionFlattenOutcome] = {}
        missing = [symbol for symbol in self._symbols if symbol not in self._lead_min]
        if missing:
            raise SessionScheduleError(
                f"no session_flatten_lead_min for managed symbol(s) "
                f"{', '.join(sorted(missing))} — a managed symbol with no lead has "
                "no deadline and therefore no §6.1b backstop; never defaulted "
                "(directive 4)"
            )

    # -- the deadline ---------------------------------------------------------

    def deadline(self, symbol: str, at: datetime) -> tuple[datetime, datetime]:
        """`(session_close, deadline)` for `symbol` at UTC instant `at`.

        §6.1b:340: the deadline is `SESSION_FLATTEN_LEAD_MIN` BEFORE the close.
        Raises `UnknownSessionClose` where the calendar cannot supply one — see
        that exception's docstring for why this is loud rather than skipped.
        """
        _require_utc(at, "at")
        close = self._calendar.next_close(symbol, at)
        if close is None:
            raise UnknownSessionClose(
                f"{symbol}: the session calendar supplies no close at or after "
                f"{at.isoformat()} — a managed symbol with no close has no §6.1b "
                "deadline and therefore no backstop against holding overnight"
            )
        _require_utc(close, f"{symbol} session close")
        return close, close - timedelta(minutes=self._lead_min[symbol])

    def is_due(self, symbol: str, at: datetime) -> bool:
        """Has `symbol`'s §6.1b deadline been reached at `at`? Half-open `>=`."""
        _, deadline = self.deadline(symbol, at)
        return at >= deadline

    # -- the sweep ------------------------------------------------------------

    async def tick_async(self, now: datetime | None = None) -> SessionFlattenSweep:
        """Evaluate every managed symbol at ONE instant. The real entry point.

        ASYNC because the honest verdict is not knowable until §4's reconcile has
        read broker truth back, and `ProtectiveFlatten.reconcile_and_publish` is
        the §2A async verb that does it. The protective FIRE inside is still the
        synchronous zero-wire call (§14) — the await is the *after*, exactly as
        `flatten.py` documents for its own split.
        """
        at = self._now(now)
        outcomes: list[SessionFlattenOutcome] = []
        suppressed: list[str] = []
        for symbol in self._symbols:
            close, deadline = self.deadline(symbol, at)
            if (symbol, close) in self._fired:
                suppressed.append(symbol)
                continue
            outcome = await self._evaluate(symbol, at, close, deadline)
            if outcome.verdict is not SessionFlattenVerdict.NOT_DUE:
                self._fired[(symbol, close)] = outcome
            outcomes.append(outcome)
        return SessionFlattenSweep(
            at=at,
            evaluated=len(self._symbols),
            suppressed=tuple(suppressed),
            outcomes=tuple(outcomes),
        )

    async def _evaluate(
        self, symbol: str, at: datetime, close: datetime, deadline: datetime
    ) -> SessionFlattenOutcome:
        """One symbol at one instant. The whole §6.1b failure ladder lives here."""
        if at < deadline:
            # NOT_DUE reads NO port at all — not the venue, not the book. The
            # deadline is the only thing that has happened, and a pre-deadline
            # tick that polled the venue would make the honesty clause's input
            # a function of tick cadence.
            return self._outcome(
                symbol,
                close,
                deadline,
                SessionFlattenVerdict.NOT_DUE,
            )
        targets = self._open_targets(symbol)
        venue = self._venue.venue_state(symbol, at)
        if not targets:
            return self._outcome(
                symbol,
                close,
                deadline,
                SessionFlattenVerdict.NOTHING_OPEN,
                venue=venue,
            )
        if venue is not VenueState.TRADABLE:
            # §4:231-235 — the guard. We do NOT fire orders into a shut market;
            # §12.6 — and we do not pretend the position closed.
            return self._outcome(
                symbol,
                close,
                deadline,
                SessionFlattenVerdict.EXPOSURE_RIDES_MARKET_HALTED,
                targets,
                venue=venue,
            )
        # The fire is SYNCHRONOUS and zero-wire (§14). `reason=session` is
        # §6.1b:342's own word and reaches the strategy through the executor's
        # §4 fan-out.
        self._executor.fire(
            FlattenTrigger.SESSION_CLOSE,
            symbol=symbol,
            targets=targets,
            reason=SESSION_REASON,
        )
        confirmed = await self._executor.reconcile_and_publish()
        verdict = _verdict_after_fire(confirmed, symbol)
        return self._outcome(
            symbol, close, deadline, verdict, targets, venue=venue, confirmed=confirmed
        )

    # -- construction of the one honest record --------------------------------

    # too-many-arguments: the outcome's own fields. This is the SINGLE
    # constructor of `SessionFlattenOutcome` in this module, deliberately, so
    # the residual-risk sentence and the alert cannot be attached by one call
    # site and forgotten by another.
    def _outcome(  # pylint: disable=too-many-arguments
        self,
        symbol: str,
        close: datetime,
        deadline: datetime,
        verdict: SessionFlattenVerdict,
        targets: tuple[CloseTarget, ...] = (),
        *,
        venue: VenueState = VenueState.UNKNOWN,
        confirmed: ConfirmedFlat | None = None,
    ) -> SessionFlattenOutcome:
        """Build the outcome AND raise its §12.9 alert. One place, one motion."""
        alert = None
        if verdict is not SessionFlattenVerdict.NOT_DUE:
            alert = _alert_for(
                verdict, symbol, close, deadline, targets=targets, venue=venue
            )
            self._alert.emit(alert)
        return SessionFlattenOutcome(
            symbol=symbol,
            session_close=close,
            deadline=deadline,
            verdict=verdict,
            targets=targets,
            venue=venue,
            confirmed=confirmed,
            residual_risk=_RESIDUAL_RISK.get(verdict, ""),
            alert=alert,
        )

    # -- helpers ---------------------------------------------------------------

    def _open_targets(self, symbol: str) -> tuple[CloseTarget, ...]:
        """§6.1b:341 — *all open positions in that symbol*, off the ONE snapshot."""
        picture = self._book.current()
        return tuple(
            CloseTarget(
                trade_id=row.trade_id, symbol=row.symbol, strategy_id=row.strategy_id
            )
            for row in picture.positions
            if row.symbol == symbol and row.state in OPEN_STATES
        )

    def _now(self, now: datetime | None) -> datetime:
        if now is not None:
            _require_utc(now, "now")
            return now
        if self._clock is None:
            raise SessionScheduleError(
                "tick_async called with no instant and no injected clock — a "
                "deadline that reads a wall clock it was not given cannot be "
                "driven across itself, and an undriven deadline measures nothing"
            )
        at = self._clock()
        _require_utc(at, "clock()")
        return at

    def fired_outcome(
        self, symbol: str, session_close: datetime
    ) -> SessionFlattenOutcome | None:
        """The latched outcome for one symbol-session, or `None`. Readable state."""
        return self._fired.get((symbol, session_close))


# ---------------------------------------------------------------------------
# The verdict derivation — the ONE place FLAT_CONFIRMED can be produced
# ---------------------------------------------------------------------------


def _verdict_after_fire(confirmed: ConfirmedFlat, symbol: str) -> SessionFlattenVerdict:
    """Broker truth AFTER the flatten decides the verdict. Nothing else does.

    Deliberately takes NO "did the fire happen" argument. §4's
    reconcile-then-publish already carries the only fact that settles it — the
    published position table, built from `query_positions` — and this function
    reads the symbol out of that table. So `FLAT_CONFIRMED` is unreachable from
    a code path that merely called `fire`, which is the ARC 022 F13 defect made
    structurally impossible rather than tested for.

    Reads the SYMBOL out of the confirmed rows rather than `confirmed.is_flat`.
    `is_flat` is a book-wide fact; a second symbol still riding would drag this
    one's verdict down with it, and a per-symbol deadline must answer per symbol.
    """
    still_held = any(row.symbol == symbol for row in confirmed.picture.positions)
    if still_held:
        return SessionFlattenVerdict.EXPOSURE_RIDES_UNCONFIRMED
    return SessionFlattenVerdict.FLAT_CONFIRMED


# too-many-arguments: the alert's snapshot fields. §12.9 requires an alert carry
# "the cause and the relevant snapshot values, not just a code", and each
# argument here is one of those values.
def _alert_for(  # pylint: disable=too-many-arguments
    verdict: SessionFlattenVerdict,
    symbol: str,
    close: datetime,
    deadline: datetime,
    *,
    targets: tuple[CloseTarget, ...],
    venue: VenueState,
) -> Alert:
    """§12.9's alert for one verdict. Tier comes from the VERDICT, not a caller.

    §6.1b:353: Info on clean fire, Critical on the failure paths. The mapping is
    `SessionFlattenVerdict.alert_tier`, so an exposure-rides outcome physically
    cannot be paged at Info.
    """
    residual = _RESIDUAL_RISK.get(verdict, "")
    detail = (
        f"§6.1b session-close flatten, {symbol}: {verdict.value} at deadline "
        f"{deadline.isoformat()} (session close {close.isoformat()}, venue "
        f"{venue.value}, {len(targets)} open position(s))"
    )
    if residual:
        detail = f"{detail}. RESIDUAL RISK — {residual}"
    return Alert(
        tier=verdict.alert_tier,
        event=SESSION_FLATTEN_EVENT,
        detail=detail,
        snapshot={
            "symbol": symbol,
            "verdict": verdict.value,
            "session_close": close.isoformat(),
            "deadline": deadline.isoformat(),
            "venue": venue.value,
            "open_positions": str(len(targets)),
            "exposure_rides": str(verdict.exposure_rides).lower(),
            "residual_risk": residual,
        },
    )


def _require_utc(value: datetime, what: str) -> None:
    """§12.3: all internal time is UTC. A naive instant is refused, never assumed.

    Refusing a naive datetime rather than localising it is the point: localising
    would be a SECOND exchange-local conversion, and §12.3 puts the conversion
    exactly once at window generation.
    """
    if value.tzinfo is None:
        raise SessionScheduleError(
            f"{what}={value!r} is naive — §12.3 makes all internal time UTC and "
            "this module never assumes a zone for a caller"
        )
    if value.utcoffset() != UTC.utcoffset(None):
        raise SessionScheduleError(
            f"{what}={value!r} is not UTC (offset {value.utcoffset()}) — §12.3 "
            "converts exchange-local exactly once, at window generation"
        )
