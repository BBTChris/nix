"""§6.5's net-liq survival watch — §15 C2 made a standing watch, and §4's
broker-authoritative reconcile.

Authority: ``docs/nics_risk_subsystem_spec_v1.3.md`` §6.5 (*survival watch,
continuous, corrected*), §12.9 (the **Critical** alert tier), §15 C2 (*survival
floor corrected to net-liq; sizing stays on cash*), §4 (*broker-authoritative
balance on EVERY reconciliation*, the monotonic-by-source guard), §14 (locked
invariants). The value types are the FROZEN ``scripts/nixrisk/seam.py`` —
``SurvivalReading``, ``SurvivalWatchPort``, ``FlattenTrigger.NET_LIQ_FLOOR``,
``PositionRow`` — and nothing here re-declares them. Σ open margin's membership
rule is ``picture.OPEN_MARGIN_STATES``, imported rather than restated so this
module is not a second authority for which position states carry margin.

ARC 029 / sub-agent C.

------------------------------------------------------------------------------
THE ONE DISTINCTION THIS MODULE EXISTS TO HOLD — §15 C2, §14 (invariant)
------------------------------------------------------------------------------
**Survival is watched on NET-LIQ; sizing is computed on CASH. Never conflate.**
The broker liquidates on *net-liq vs maintenance margin*, and net-liq erodes
with price while cash does not: an open position moving against the book drops
net-liq tick by tick with cash untouched (cash changes on fills and fees, not on
marks). So the force-flatten decision reads ``net_liq`` — through the seam's
``SurvivalReading.breached`` (``net_liq < floor``, which is the *only* definition
of the predicate, so a reader cannot accidentally spell it against cash) — and
the sizing denominator reads ``cash`` through ``sizing_liquidity``. A single
"equity" figure would let one be read where the other was meant and nothing
would disagree, which is precisely the defect §15 C2 corrects.

``SurvivalReading.unrealized`` is the field that lets a test drive the two apart.
A reading with ``net_liq == cash`` (``unrealized == 0``) proves NOTHING about the
distinction: swapping the two in the predicate returns the same verdict. Only an
open position with unrealized P&L (``net_liq != cash``), with the floor placed
BETWEEN them, discriminates a net-liq watch from a cash watch — which is why the
suite drives them apart both ways rather than testing the degenerate equal case.

------------------------------------------------------------------------------
THE STANDING WATCH IS NOT THE PRE-TRADE CHECK — §6.5, and C2
------------------------------------------------------------------------------
``gate.SurvivalHeadroomRule`` (ARC 028) is Phase B: the PROJECTED net-liq impact
of a *new* entry, taken against ``(Σ open margin + proposed) × (1 + pad)``. This
module is the OTHER half of §6.5 — the continuous watch on the OPEN book, taken
against the *current* Σ open margin, that force-flattens when net-liq has already
fallen through the floor. The two share the floor formula and nothing else: one
guards an entry, this one guards money already committed.

------------------------------------------------------------------------------
ZERO WIRE DEPENDENCY, and why this class is SYNCHRONOUS — §14, seam docstring
------------------------------------------------------------------------------
§14: *the exit/protective path has zero wire/delivery dependency*. The watch
fires the flatten by a DIRECT synchronous call into an injected
``FlattenExecutor`` (the Limiter's own flatten path — *execution of any flatten
is Limiter-only*), and raises the Critical alert by a direct call into an
injected ``AlertSink``. Neither touches the state bus, the picture publisher, or
any socket: a coroutine would need a running loop to make progress, and the whole
point of §14 is that the exit fires when the bus is down. ``read`` is a single
attribute load; the reading it returns is a frozen ``SurvivalReading`` rebound as
one store (the ``picture.FinancialPictureBook`` mechanism), so a consumer never
observes a half-updated reading and "publishes atomically" is a property of the
type rather than a discipline.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO — stated, so no green here implies it
------------------------------------------------------------------------------
It does not EXECUTE the flatten (that is the injected Limiter path, sub-agent B),
does not build the flatten fan-out (strategy / Allocator mirror / event log /
Scoring), does not own the §12.7 bus transport (``picture.py`` does), and does
not compute the per-tick net-liq mark off the price cache (its caller does and
hands it in via ``mark``). The synthetic-stop caveat of §12.1 stands: a killed
Risk Engine is an unprotected position until the Sentinel (R4) exists, and no
green here may be read as covering that gap.
"""

from __future__ import annotations

import enum
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from nixrisk.picture import OPEN_MARGIN_STATES
from nixrisk.seam import FlattenTrigger, PositionRow, SurvivalReading

# R0903 (too-few-public-methods): every Protocol below is a single-verb
# DECLARATION with exactly the surface the spec gives it — a second method would
# be a port doing two jobs. Disabled at module scope as in `picture.py`/`gate.py`.
# pylint: disable=too-few-public-methods

#: The §12A tunable that names this watch's one number. §6.5's floor is
#: ``net_liq < Σ open margin × (1 + NETLIQ_SAFETY_PAD)`` and §12A owns the value;
#: this constant is the KEY, never a default — `SurvivalWatch` takes the pad
#: explicitly, for the reason `AggregateMarginCapRule` takes the fraction
#: explicitly: a safety pad with a silent default is a floor nobody chose.
NETLIQ_SAFETY_PAD_KNOB: Final[str] = "NETLIQ_SAFETY_PAD"

#: The event name the protective flatten and its Critical alert are booked under.
#: §12.9 pages on "survival-floor breach / protective flatten fired"; this is the
#: cause string that rides both so an operator triages without logging into the
#: box.
BREACH_EVENT: Final[str] = "netliq_survival_floor_breach"

#: The event name a broker-vs-projection correction is booked under. §6.5's
#: "ledger reconcile ... drift beyond tolerance ⇒ audit event" is §12.9's Warning
#: tier ("aggregate-drift audit event"), NOT Critical — the Critical tier is
#: reserved for the breach, and the suite asserts the two do not collapse.
DRIFT_EVENT: Final[str] = "netliq_projection_drift"


class AlertTier(enum.Enum):
    """§12.9's push tiers. Only the three the spec names; no fourth.

    ``CRITICAL`` pages immediately (survival-floor breach / protective flatten).
    ``WARNING`` is the aggregate-drift audit event. ``INFO`` is not raised by this
    module and is present only so the enum matches §12.9's stated set rather than
    this module's subset — a reader cannot mistake "the tiers this file uses" for
    "the tiers that exist".
    """

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Alert:
    """One §12.9 alert. Carries the CAUSE and the snapshot values, not just a code.

    §12.9: *"Alerts carry the cause and the relevant snapshot values, not just a
    code, so the operator can triage without logging into the box."* ``snapshot``
    is that requirement made structural — a mapping of the figures behind the
    alert (net-liq, cash, floor, unrealized), so a Critical page is actionable on
    its face.
    """

    tier: AlertTier
    event: str
    detail: str
    snapshot: Mapping[str, str]


@runtime_checkable
class AlertSink(Protocol):
    """Where an alert goes. §12.9's push transport is CC-defined; this is its seam."""

    def emit(self, alert: Alert) -> None:
        """Push one alert. Never dropped silently by this module."""


@runtime_checkable
class FlattenExecutor(Protocol):
    """The Limiter's protective-flatten path, called DIRECTLY and synchronously.

    §14: execution of any flatten is Limiter-only, and the protective path has
    zero wire dependency. The watch is DETECTION; it hands the trigger to this
    executor by an in-process call. The concrete executor (order build, fan-out,
    reconcile-then-publish) is sub-agent B's; this port is the boundary between
    detecting a breach and firing the exit.
    """

    def flatten(self, trigger: FlattenTrigger, reason: str) -> None:
        """Flatten the open book for ``trigger``. Reason names the cause (§3)."""


@dataclass(frozen=True)
class BrokerReading:
    """One broker reconciliation poll: balance AND positions in ONE motion (§4).

    §4: *every reconciliation event pulls a direct broker balance + position poll
    in the same motion*. Both halves ride one object because a balance read at one
    instant against positions read at another is exactly the stale-balance tear §3's
    atomicity rule forbids. ``net_liq`` and ``cash`` are both broker-authoritative
    (the broker liquidates on net-liq and holds the cash balance); ``unrealized``
    is their residual and Σ open margin is derived from ``positions`` with the
    shared ``OPEN_MARGIN_STATES`` rule. ``venue_ts`` is the venue's own
    timestamp/sequence — the key the monotonic-by-source guard orders by, never
    arrival time.
    """

    cash: float
    net_liq: float
    positions: tuple[PositionRow, ...]
    venue_ts: float


@runtime_checkable
class BrokerReconcilePort(Protocol):
    """§4's broker-authoritative source. ONE call yields balance AND positions."""

    def poll(self) -> BrokerReading:
        """Pull cash, net-liq and the position set together, with a venue stamp."""


@dataclass(frozen=True)
class WatchOutcome:
    """The standing watch's answer for one reading. Evidence, never a side effect.

    ``fired`` is True only on the call that actually fired the flatten — the latch
    (see ``SurvivalWatch``) suppresses re-fires while a breach persists, so a
    caller can tell "breached and I fired" from "breached and already firing".
    """

    reading: SurvivalReading
    breached: bool
    fired: bool
    source: str


@dataclass(frozen=True)
class ReconcileOutcome:  # pylint: disable=too-many-instance-attributes
    # Eight fields, and every one is an OBSERVABLE the reconcile produced: the
    # reading, the event that drove it, whether it applied (monotonic guard),
    # whether it corrected the projection, the signed drift, the drop note, and
    # the breach/fire the standing watch reported on the fresh reading. A frozen
    # value type with no behaviour; the threshold is about behavioural classes.
    """One §4 reconciliation event's result, and what it did to the held reading.

    ``applied`` is False when the monotonic-by-source guard discarded a stale poll
    (older ``venue_ts`` than the one held): §4 discards, never applies. ``corrected``
    is True when the local projection disagreed with broker truth beyond tolerance
    and broker truth won — the §12.9 Warning audit event. ``drift`` is
    projection − broker net-liq, signed.
    """

    reading: SurvivalReading
    event: str
    applied: bool
    corrected: bool
    drift: float
    note: str
    breached: bool
    fired: bool


class SurvivalWatchError(RuntimeError):
    """A survival-watch operation was refused. Always says what and why."""


class SurvivalNotReady(SurvivalWatchError):
    """A reading was asked for before any mark or reconcile established one.

    Fail closed: a survival watch with no reading has not proven the account
    safe, so it refuses to answer rather than inventing a comfortable figure.
    """


class KnobError(ValueError):
    """A §12A tunable outside its admissible range. Raised at construction."""


def _finite(name: str, value: float) -> str:
    """``""`` when ``value`` is a real number; else why it is not usable."""
    if math.isnan(value) or math.isinf(value):
        return (
            f"{name} is {value!r} — a survival reading carrying NaN/Inf cannot be "
            "compared against the floor, and a safety property that cannot be "
            "evaluated is not proven (nix_check_contract.md §17)"
        )
    return ""


def _sum_open_margin(positions: tuple[PositionRow, ...]) -> float:
    """Σ open margin over the broker's position set, by the shared membership rule."""
    return math.fsum(row.margin for row in positions if row.state in OPEN_MARGIN_STATES)


class SurvivalWatch:  # pylint: disable=too-many-instance-attributes
    # SIX of the attributes are COUNTERS (`polls`, `applied`, `dropped`,
    # `corrections`, `flattens`, `criticals`). They exist for the reason
    # `ReservationLedger`'s and `FinancialPictureBook`'s counters do: a watch that
    # cannot say how many times it polled, corrected, or fired can only be
    # believed, not measured. The threshold is about behavioural classes accreting
    # state; these are the observables a gate reads. The rest are the pad, the
    # tolerance, three injected collaborators, the held reading, the guard's
    # last-applied venue stamp, and the fired latch.
    """§6.5's standing net-liq watch. Satisfies the FROZEN ``SurvivalWatchPort``.

    SYNCHRONOUS throughout (seam docstring): the exit fires by a direct call and
    the protective path has zero wire dependency, so there is no awaitable here.

    Deliberately NOT a subclass of ``SurvivalWatchPort``. A Protocol's method
    bodies are docstrings, so inheriting it would let a verb this class forgot to
    override return ``None`` silently; conformance is proven by comparing
    signatures against the port (the suite does), which is a measurement rather
    than a nominal claim — the same choice ``ReservationLedger`` makes.

    ------------------------------------------------------------------------
    THE FLOOR IS DYNAMIC, and the seam's ``floor()`` phrasing is resolved here
    ------------------------------------------------------------------------
    §6.5's floor is ``Σ open margin × (1 + safety_pad)`` — it moves as the open
    book grows and shrinks. The §12A tunable is the ``safety_pad``; the effective
    floor is derived per reading from the broker's Σ open margin. So ``floor()``
    returns the CURRENT effective floor (against the last reading's Σ open
    margin), and ``SurvivalReading.floor`` carries that same value at read time.
    The seam calls ``floor()`` "the configured survival floor (§12A tunable,
    boot-loaded)"; the tunable is the pad, and this is the reported seam ambiguity
    (a static ``floor()`` cannot express §6.5's ``× Σ open margin`` term).
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        safety_pad: float,
        broker: BrokerReconcilePort,
        flatten: FlattenExecutor,
        alert: AlertSink,
        tolerance: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not math.isfinite(safety_pad) or safety_pad < 0.0:
            raise KnobError(
                f"{NETLIQ_SAFETY_PAD_KNOB} must be a finite pad >= 0, got "
                f"{safety_pad!r} — a negative pad places the floor BELOW Σ open "
                "margin, which is the broker's own liquidation trigger and the "
                "thing §6.5 exists to stay above"
            )
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise KnobError(
                f"reconcile tolerance must be finite and >= 0, got {tolerance!r} "
                "— a negative tolerance would correct on every poll, and an "
                "infinite one would never let broker truth win (§4)"
            )
        self._safety_pad = float(safety_pad)
        self._tolerance = float(tolerance)
        self._broker = broker
        self._flatten = flatten
        self._alert = alert
        self._clock = clock
        self._current: SurvivalReading | None = None
        self._last_venue_ts: float | None = None
        self._fired = False
        self.polls = 0
        self.applied = 0
        self.dropped = 0
        self.corrections = 0
        self.flattens = 0
        self.criticals = 0

    # -- the frozen port ----------------------------------------------------

    def read(self) -> SurvivalReading:
        """The current reading — ONE attribute load, whole or nothing (§3, §12.7).

        Broker-authoritative after a reconcile, the per-tick mark otherwise. A
        reader never sees a half-built reading because a half-built reading is
        never bound to this name.
        """
        if self._current is None:
            raise SurvivalNotReady(
                "no survival reading yet — mark the net-liq or reconcile against "
                "broker truth before reading; a watch with no reading has not "
                "proven the account safe and will not pretend it has"
            )
        return self._current

    def floor(self) -> float:
        """§6.5's current effective floor: Σ open margin × (1 + safety_pad).

        Dynamic, not a boot constant — see the class docstring on the seam
        ambiguity. Raises until a reading exists, for the reason ``read`` does.
        """
        return self.read().floor

    # -- the net-liq/cash distinction made a verb (§15 C2) ------------------

    def sizing_liquidity(self) -> float:
        """§6.5's sizing denominator: CASH, never net-liq. The other half of C2.

        Sizing changes on fills and fees and EXCLUDES unrealized value, always.
        Returning ``cash`` here — while ``breached`` reads ``net_liq`` — is the
        structural non-conflation: the two figures are read through two different
        verbs, so a caller cannot size on the number the watch flattens on.
        """
        return self.read().cash

    # -- the per-tick mark (§6.5: net-liq marked incrementally per tick) ----

    def mark(
        self, *, cash: float, net_liq: float, sum_open_margin: float
    ) -> WatchOutcome:
        """Take a fresh per-tick net-liq mark and run the standing watch on it.

        §6.5 marks net-liq incrementally per tick off the price cache; this is the
        fast LOCAL view (the projection §4's reconcile later corrects). It stores
        the reading atomically and then evaluates the breach, so a mark that falls
        through the floor fires the flatten on the same tick it was observed —
        which is what "*before* Tradovate's trigger" requires.
        """
        self._require_finite(cash, net_liq, "mark", sum_open_margin)
        self._store(net_liq=net_liq, cash=cash, sum_open_margin=sum_open_margin)
        return self._check_current("mark")

    # -- the standing watch (§6.5 force-flatten, §12.9 Critical) ------------

    def check(self) -> WatchOutcome:
        """Evaluate the current reading WITHOUT changing it. Fires on a breach.

        Idempotent against re-fire: while a breach persists the latch suppresses a
        second flatten, so calling ``check`` repeatedly does not spray the exit
        path with duplicate orders. The latch re-arms once net-liq recovers above
        the floor, so a later breach fires again.
        """
        return self._check_current("check")

    # -- §4 broker-authoritative reconcile, uniform on EVERY event ----------

    def reconcile(self, event: str) -> ReconcileOutcome:
        """Pull broker truth and adopt it. UNIFORM on every event (§4, v1.3 locked).

        There is no "is this ambiguous enough?" branch: every reconciliation
        event — indeterminate, orphan, protective flatten, partial-fill
        resolution, any fill/close — pulls exactly ONE broker poll (balance AND
        positions, one motion) and, unless the monotonic-by-source guard discards
        it as stale, publishes the fresh authoritative reading atomically and runs
        the standing watch on it. If the local projection disagreed with broker
        truth beyond tolerance, BROKER WINS and the disagreement is booked as a
        §12.9 Warning audit event.
        """
        poll = self._broker.poll()
        self.polls += 1
        stale = self._stale_reason(poll.venue_ts)
        if stale:
            self.dropped += 1
            return ReconcileOutcome(
                reading=self.read(),
                event=event,
                applied=False,
                corrected=False,
                drift=0.0,
                note=stale,
                breached=self._current is not None and self._current.breached,
                fired=False,
            )
        # Σ open margin is derived FIRST so the finite guard can see it: it is an
        # input to the floor, and the floor is the predicate (finding FD2).
        sum_open_margin = _sum_open_margin(poll.positions)
        self._require_finite(
            poll.cash, poll.net_liq, f"reconcile:{event}", sum_open_margin
        )
        corrected, drift = self._note_drift(poll)
        self._store(
            net_liq=poll.net_liq,
            cash=poll.cash,
            sum_open_margin=sum_open_margin,
        )
        self._last_venue_ts = poll.venue_ts
        self.applied += 1
        watch = self._check_current(f"reconcile:{event}")
        return ReconcileOutcome(
            reading=watch.reading,
            event=event,
            applied=True,
            corrected=corrected,
            drift=drift,
            note="",
            breached=watch.breached,
            fired=watch.fired,
        )

    # -- internals ----------------------------------------------------------

    def _require_finite(
        self, cash: float, net_liq: float, where: str, sum_open_margin: float
    ) -> None:
        """Refuse a non-finite figure LOUDLY. A NaN net-liq is not a safe one.

        ``sum_open_margin`` is checked HERE and was ADDED BY MEASUREMENT (ARC 038
        / sub-agent D, finding FD2). It was the one input this guard omitted, and
        it is the one the FLOOR is built from: with ``sum_open_margin = nan`` the
        floor is ``nan``, ``SurvivalReading.breached`` is ``net_liq < nan`` which
        is **False**, and the standing watch reported the account SAFE and NEVER
        FIRED. MEASURED both ways in: a ``mark`` with cash 50,000 / net-liq 9,000
        against a NaN Σ open margin gave ``flattens=0 criticals=0``, and ONE
        broker position row carrying ``margin=nan`` did the same through
        ``reconcile`` — ``applied=True, floor=nan, breached=False``. §17 is
        explicit that a safety property which cannot be EVALUATED is not proven,
        and this module's own ``_finite`` docstring says exactly that; the guard
        now covers every term the predicate reads rather than two of the three.
        """
        for note in (
            _finite("cash", cash),
            _finite("net_liq", net_liq),
            _finite("sum_open_margin", sum_open_margin),
        ):
            if note:
                raise SurvivalWatchError(f"{where}: {note}")

    def _floor_for(self, sum_open_margin: float) -> float:
        """§6.5's floor formula, in ONE place: Σ open margin × (1 + safety_pad).

        The ``max(0.0, …)`` is §7:483's *"every term clamps ≥ 0 (no negative-floor
        artifacts)"* applied to the one term that can go negative here, and it was
        ADDED BY MEASUREMENT (ARC 038 / sub-agent D, finding FD2): a Σ open margin
        of −10,000 produced a floor of −11,000, against which a net-liq of −5,000
        — an account the broker has already liquidated — read ``breached=False``.
        A floor below zero is not a floor. On every legitimate input (margins are
        non-negative) the clamp is the identity, so it can only ever move a
        verdict toward flat. It does NOT stand in for the finite guard above and
        the pair is coupled: with the clamp alone, ``max(0.0, nan)`` is ``0.0``
        and the watch still never fires — measured, and pinned by
        ``test_arc038_d_money_truth.py``.
        """
        return max(0.0, sum_open_margin) * (1.0 + self._safety_pad)

    def _store(self, *, net_liq: float, cash: float, sum_open_margin: float) -> None:
        """THE single store. Atomicity of the published reading lives here."""
        self._current = SurvivalReading(
            net_liq=net_liq,
            cash=cash,
            unrealized=net_liq - cash,
            floor=self._floor_for(sum_open_margin),
            taken_at=self._clock(),
        )

    def _stale_reason(self, venue_ts: float) -> str:
        """Monotonic-by-source guard: ``""`` to apply, else why it is discarded.

        §4: a value is accepted only if newer than the one held; anything older is
        discarded, not applied, ordered by the venue's own time and never by
        arrival. A poll whose ``venue_ts`` is not strictly greater than the last
        applied one is a stale poll that landed after a fresher reading.
        """
        if self._last_venue_ts is not None and venue_ts <= self._last_venue_ts:
            return (
                f"monotonic-by-source guard: poll venue_ts {venue_ts!r} is not "
                f"newer than the last applied {self._last_venue_ts!r} — §4 discards "
                "a stale venue reading rather than letting balance go backwards"
            )
        return ""

    def _note_drift(self, poll: BrokerReading) -> tuple[bool, float]:
        """Compare the local projection to broker truth. Beyond tolerance ⇒ Warning.

        Returns ``(corrected, drift)``. Broker truth is adopted either way (it is
        the source of truth); ``corrected`` records whether the projection had
        drifted materially, which is the §12.9 aggregate-drift audit event.
        """
        if self._current is None:
            return (False, 0.0)
        drift = self._current.net_liq - poll.net_liq
        if abs(drift) <= self._tolerance:
            return (False, drift)
        self.corrections += 1
        self._alert.emit(
            Alert(
                tier=AlertTier.WARNING,
                event=DRIFT_EVENT,
                detail=(
                    f"§4 broker-authoritative reconcile: local net-liq projection "
                    f"{self._current.net_liq!r} disagrees with broker truth "
                    f"{poll.net_liq!r} by {drift:+.6f} (> tolerance "
                    f"{self._tolerance!r}); broker wins and we correct"
                ),
                snapshot={
                    "projected_net_liq": repr(self._current.net_liq),
                    "broker_net_liq": repr(poll.net_liq),
                    "drift": repr(drift),
                    "tolerance": repr(self._tolerance),
                },
            )
        )
        return (True, drift)

    def _check_current(self, source: str) -> WatchOutcome:
        """The standing watch's core: fire the flatten + Critical alert on a breach.

        The breach predicate is ``SurvivalReading.breached`` — ``net_liq < floor``
        — and NOTHING here reads cash for the decision: that is the §15 C2
        non-conflation, held by delegating to the seam's own property. The latch
        (``_fired``) suppresses re-fires while breached and re-arms on recovery, so
        a persistent breach fires exactly one flatten.
        """
        reading = self.read()
        breached = reading.breached
        if not breached:
            self._fired = False
            return WatchOutcome(reading, breached=False, fired=False, source=source)
        if self._fired:
            return WatchOutcome(reading, breached=True, fired=False, source=source)
        reason = (
            f"§6.5 survival floor breached: net_liq {reading.net_liq!r} < floor "
            f"{reading.floor!r} (Σ open margin × (1 + {self._safety_pad!r})); "
            f"shortfall {reading.floor - reading.net_liq!r}. cash {reading.cash!r} "
            f"is NOT the trigger — the broker liquidates on net-liq (§15 C2)"
        )
        self._flatten.flatten(FlattenTrigger.NET_LIQ_FLOOR, reason)
        self.flattens += 1
        self._alert.emit(
            Alert(
                tier=AlertTier.CRITICAL,
                event=BREACH_EVENT,
                detail=reason,
                snapshot={
                    "net_liq": repr(reading.net_liq),
                    "cash": repr(reading.cash),
                    "unrealized": repr(reading.unrealized),
                    "floor": repr(reading.floor),
                    "source": source,
                },
            )
        )
        self.criticals += 1
        self._fired = True
        return WatchOutcome(reading, breached=True, fired=True, source=source)
