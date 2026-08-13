"""§4's cold-start reconciliation — the registration gate and its market guard.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 029 / sub-agent D. Implements the FROZEN `ColdStartPort` declared in
`scripts/nixrisk/seam.py`; it changes neither that port nor any other seam type.
Nothing here is a second authority — the seam fixes the vocabulary
(`BrokerTruth`, `FlattenTrigger`), §4 fixes the reconciliation discipline, and
this module is the ordering logic that keeps them true.

------------------------------------------------------------------------------
THE PROPERTY THIS MODULE EXISTS TO HOLD — and why it is SYNCHRONOUS (§4, V34)
------------------------------------------------------------------------------
§4, locked: on start the local state is empty and TRUSTLESS. The Limiter
**actively queries the broker** the moment broker-order has a session — the true
open-position set AND balance in one poll — and *"at cold start the broker's
answer is the record, not a reconciliation against one"*. That query **gates
registration**: no strategy registers until a provably-flat assertion has passed.

The gate is an ORDERING property, which is why the seam declares `ColdStartPort`
synchronous and why this class is too. An awaitable admission gate is a
suspension point during which a registration could interleave, admitting a
strategy against unproven state — and `restart = flat, always` (§14) is not a
preference that tolerates a race. So `reconcile` and `register` are plain calls:
between the flat assertion and the first admission there is no `await` a
registration can slip through.

------------------------------------------------------------------------------
"GATES REGISTRATION" IS ONLY FALSIFIABLE AGAINST AN ATTEMPT (§0a, MEASURED)
------------------------------------------------------------------------------
The brief states, as a hypothesis to measure: *"gates registration" is
unfalsifiable unless something attempts to register.* It is CORRECT, and the
measurement is in `test_coldstart.py`: `registration_admitted()` is a bool, and a
test that only reads it green-lights a `register()` that ignores the flag
entirely — a bool-only assertion passes against a gate that does not gate. So
this module exposes `register()` as the surface a strategy actually drives, and
it RAISES `RegistrationRefused` naming the reason while not-yet-flat. The refusal
is the property; reading the flag is a proxy for it.

------------------------------------------------------------------------------
THE MARKET-TRADABLE GUARD HAS TWO HALVES (§4, D4, MEASURED)
------------------------------------------------------------------------------
Flatten fires MARKET orders, so it needs an open, tradable market. If the box
comes up to an open position while the market is closed or halted, the system
does **NOT** fire into a shut market — it **holds in HALT with a loud alert** and
flattens the instant the market is tradable. The brief's hypothesis — *a drill
with the market always open measures NEITHER half* — is CORRECT: an always-open
run never reaches `hold_in_halt` (the HALT half) and never re-flattens on reopen
(the flatten half). `test_coldstart.py` drives both: held-in-HALT while closed,
and flattened once the same box's market reopens.

The guard lives on `flatten_to_flat` itself, not only in the reconcile flow: the
verb REFUSES to fire into a shut market and says so, so the guard is a property of
the flatten primitive and cannot be bypassed by a caller that reaches it directly.

------------------------------------------------------------------------------
WHICH TRIGGER AN INHERITED POSITION FLATTENS UNDER — ORPHAN, not UNCERTAINTY
------------------------------------------------------------------------------
§3:169's trigger set names both `orphan` and `uncertainty`. A cold-start
inherited position is not UNCERTAINTY — broker truth is definite, the position
provably exists — it is ORPHAN: a live position that no registered strategy owns,
which is exactly what cold start finds before any registration exists. The
executor chooses the trigger; `flatten_to_flat` returns what it fired. This module
records the reasoning so a future reader does not mistake a definite ownerless
position for an indeterminate one.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO — stated, so no green here implies it
------------------------------------------------------------------------------
It does not OPEN the broker session (§2A's port owns that) — it is handed a
`BrokerSessionPort` already able to poll. It does not fire the market orders
itself: execution of any flatten is Limiter-only, and the injected
`FlattenExecutorPort` is where that execution lives. It does not decide the global
HALT flag's full §12.5 semantics or auto-clear (R4) — it is handed a
`HaltAlertPort` and raises HALT through it. It does not build the session calendar
that answers `market_tradable` (R4); it reads a port. And the frozen seam's
`EventKind` has no `COLD_START` member on purpose (see its docstring), so the
cold-start outcome is booked under the existing `BOOT` kind and the dedicated kind
is an integration debt, not a member quietly invented here.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Protocol, runtime_checkable

from nixrisk.seam import (
    BrokerTruth,
    EventKind,
    EventRow,
    FlattenTrigger,
    Plane1Port,
)

#: The `strategy_id` a system-level Plane-1 row carries. Cold-start reconciliation
#: is not owned by any strategy — it runs before any strategy registers — so its
#: §9 row cannot name one. A sentinel actor is honest where borrowing a real
#: strategy_id would attribute a system boot to a strategy that has not registered.
SYSTEM_ACTOR = "__system__"


class ColdStartError(RuntimeError):
    """Base for every refusal this reconciler raises. Never caught internally."""


class RegistrationRefused(ColdStartError):
    """A `register` attempt before the provably-flat assertion has passed.

    §4: no strategy registers until cold start asserts flat. This is raised — not
    returned — because a strategy that ignored the refusal and proceeded would be
    trading against unproven state, which is the exact hazard the gate exists to
    prevent. It NAMES the state so the caller learns WHY, not merely that it was
    refused (check contract v2 §11: assert the reason, never the code alone).
    """


# ---------------------------------------------------------------------------
# The collaborators this reconciler stands on (injected, never constructed here)
# ---------------------------------------------------------------------------
#
# R0903 (too-few-public-methods) disabled: each is a Protocol declaring exactly
# the surface §4 gives it. A second method would be a port doing two jobs.
# pylint: disable=too-few-public-methods


@runtime_checkable
class BrokerSessionPort(Protocol):
    """§4's broker truth source. ONE poll returns positions AND balance together.

    `poll_truth` pulls both halves in the same motion because §4 requires it: a
    balance read at one instant against positions read at another is exactly the
    stale-balance tear §3's atomicity rule exists to prevent. `market_tradable`
    carries a REASON alongside the flag so the held-in-HALT alert can name why the
    market is shut (weekend, session gap, exchange halt).
    """

    def poll_truth(self) -> BrokerTruth:
        """Positions + balance + one stamp, in a single broker round-trip."""

    def market_tradable(self) -> tuple[bool, str]:
        """`(tradable, why)`. Closed/halted ⇒ `(False, reason)`."""


@runtime_checkable
class FlattenExecutorPort(Protocol):
    """Where the Limiter-only flatten EXECUTION lives (§14: execution is Limiter).

    Handed the broker truth, it fires a market order to close every inherited
    position and returns the `FlattenTrigger`s it fired under. Injected rather than
    inlined so the actual market-order path — the wire — is a collaborator this
    ordering logic does not itself own.
    """

    def flatten(self, truth: BrokerTruth) -> tuple[FlattenTrigger, ...]:
        """Close every inherited position. Returns the triggers fired."""


@runtime_checkable
class HaltAlertPort(Protocol):
    """Holds the system in HALT with a loud (§12.9 Critical) alert.

    One verb, because the two are inseparable at cold start: §4 says the
    held-in-HALT state is announced with a LOUD alert, and §12.5 lists cold-start
    -in-HALT among the conditions that page immediately. A hold that set the flag
    without alerting would be a silent HALT, which is the failure mode §12.9's
    critical tier exists to prevent.
    """

    def hold_in_halt(self, reason: str) -> None:
        """Set the global HALT and raise the Critical alert, with the reason."""


# ---------------------------------------------------------------------------
# The outcome of one reconcile pass
# ---------------------------------------------------------------------------


class ColdStartState(enum.Enum):
    """Where cold-start reconciliation stands. Three states, and no fourth.

    `PENDING` is the trustless start: nothing polled, nothing admitted.
    `HELD_IN_HALT` is an inherited position the guard would not fire on (market
    shut) or a flatten that did not reach flat — either way registration stays
    refused. `FLAT_ASSERTED` is the ONLY state that admits registration, and it is
    reached only through a broker-confirmed flat. There is deliberately no
    "adopted" state: an inherited position is never adopted (§4).
    """

    PENDING = "pending"
    HELD_IN_HALT = "held_in_halt"
    FLAT_ASSERTED = "flat_asserted"


@dataclasses.dataclass(frozen=True)
class ReconcileOutcome:
    """One reconcile pass, recorded. Immutable — a later pass produces a new one.

    `admitted` is redundant with `state is FLAT_ASSERTED` by construction, and
    that is the point: a consumer can read the boolean the gate turns on without
    knowing the state machine, and the two can be asserted equal so a state that
    forgot to flip the flag is caught.
    """

    state: ColdStartState
    truth: BrokerTruth
    flattened: tuple[FlattenTrigger, ...]
    admitted: bool
    reason: str


# pylint: disable=too-many-instance-attributes
# NINE attributes: three injected collaborators (broker, flattener, halt), the
# required Plane-1 sink, and five pieces of the ordering state this class exists
# to hold — the state enum, the admission latch, the last broker truth, the poll
# counter that proves the one-motion query, and the admitted-registration list.
# None is behavioural accretion; each is one field the §4 gate needs to decide.
class ColdStart:
    """§4's cold-start reconciliation. Satisfies the frozen `ColdStartPort`.

    SYNCHRONOUS throughout, for the reason the seam gives: the gate is an ordering
    property and an awaitable admission gate is a window a registration can
    interleave through.

    Deliberately NOT a subclass of `ColdStartPort`. A `Protocol`'s method bodies
    are docstrings, so inheriting it means a verb this class forgot to override
    returns `None` silently — a gate whose `registration_admitted()` answered
    `None` reads as falsey and would look like a working refusal while measuring
    nothing. Conformance is proven by comparing signatures against the port
    instead, which is a measurement rather than a nominal claim.
    """

    def __init__(
        self,
        broker: BrokerSessionPort,
        flattener: FlattenExecutorPort,
        halt: HaltAlertPort,
        plane1: Plane1Port,
    ) -> None:
        self._broker = broker
        self._flattener = flattener
        self._halt = halt
        #: §9: the Limiter is the SOLE writer of Plane 1, and §12.10 books the
        #: cold-start outcome there. Required, never defaulted to a sink — a
        #: reconciler that quietly discarded its own held-in-HALT row would leave
        #: the one paging event with no durable record.
        self._plane1 = plane1
        self._state = ColdStartState.PENDING
        self._admitted = False
        self._last_truth: BrokerTruth | None = None
        #: Counts broker round-trips, so a test can prove `query_truth` pulls both
        #: halves in ONE motion rather than two reads that could tear (§4).
        self._polls = 0
        self._registered: list[str] = []

    # -- the frozen port ----------------------------------------------------

    def query_truth(self) -> BrokerTruth:
        """Poll the broker for the true position set and balance, together.

        One round-trip, counted. At cold start the answer IS the record — there is
        no local state to reconcile it against — so the returned `BrokerTruth` is
        stored as the ground truth every later decision reads.
        """
        self._polls += 1
        truth = self._broker.poll_truth()
        self._last_truth = truth
        return truth

    def market_tradable(self) -> bool:
        """May a market order be fired right now? Closed/halted ⇒ False."""
        tradable, _why = self._broker.market_tradable()
        return tradable

    def flatten_to_flat(self, truth: BrokerTruth) -> tuple[FlattenTrigger, ...]:
        """Flatten every inherited position. Never adopt, never reason about.

        The MARKET-TRADABLE guard lives here, at the point of firing: flatten
        fires market orders, so a shut market makes this a REFUSAL, not a blind
        send (§4, D4). An already-flat truth flattens nothing and returns empty —
        never an adoption. Every inherited position closes under `ORPHAN`: it is a
        live position no registered strategy owns, which is definite, not
        uncertain.
        """
        if truth.is_flat:
            return ()
        tradable, why = self._broker.market_tradable()
        if not tradable:
            raise ColdStartError(
                f"refusing to flatten {len(truth.positions)} inherited "
                f"position(s) into a shut market ({why}) — §4's market-tradable "
                "guard: the system does NOT fire market orders into a "
                "closed/halted market; it holds in HALT until tradable"
            )
        return self._flattener.flatten(truth)

    def registration_admitted(self) -> bool:
        """Has the provably-flat assertion passed? Gates every registration."""
        return self._admitted

    # -- the driver and the registration surface ----------------------------

    def reconcile(self, now: float) -> ReconcileOutcome:
        """Run one cold-start pass and return where it landed.

        Already flat ⇒ assert flat and admit. An unexpected open position on a
        TRADABLE market ⇒ flatten, RE-QUERY broker truth to confirm, admit only on
        a confirmed flat. An open position on a SHUT market ⇒ hold in HALT with the
        loud alert and admit nothing — the flatten waits for the market. Callable
        again from `HELD_IN_HALT`: that re-run is how the held position flattens
        the instant the market becomes tradable (§4, D4).
        """
        truth = self.query_truth()
        if truth.is_flat:
            return self._admit(truth, (), now, "already flat")
        tradable, why = self._broker.market_tradable()
        if not tradable:
            return self._hold(
                truth,
                now,
                f"cold-start found {len(truth.positions)} inherited position(s) "
                f"while the market is NOT tradable ({why}) — holding in HALT and "
                "flattening the instant the market is tradable; NOT firing market "
                "orders into a shut market (§4 market-tradable guard)",
            )
        triggers = self.flatten_to_flat(truth)
        confirmed = self.query_truth()
        if confirmed.is_flat:
            return self._admit(confirmed, triggers, now, "flattened to flat")
        return self._hold(
            confirmed,
            now,
            f"cold-start flatten fired {tuple(t.value for t in triggers)} but the "
            f"broker still reports {len(confirmed.positions)} open position(s) — "
            "refusing to admit registration and holding in HALT (fail closed, "
            "§4 / directive 4: known state beats optimal state)",
        )

    def register(self, strategy_id: str, now: float) -> None:
        """A strategy's registration ATTEMPT. Refused until provably flat.

        This is the surface that makes the gate falsifiable: it is what a strategy
        drives, and it RAISES while not-yet-flat rather than reading a flag and
        hoping the caller checked it. The attempt is the claim — a drill where
        nothing registers proves nothing about a gate (§0a).
        """
        del now  # accepted for call-shape symmetry with the rest of the seam
        if not self._admitted:
            raise RegistrationRefused(
                f"{strategy_id}: registration REFUSED — the cold-start "
                f"provably-flat assertion has not passed (state="
                f"{self._state.value}). §4: no strategy registers until a "
                "provably-flat assertion has passed, and an inherited position is "
                "never adopted, however profitable"
            )
        self._registered.append(strategy_id)

    def registered(self) -> tuple[str, ...]:
        """Every strategy admitted so far. Empty until the gate opens."""
        return tuple(self._registered)

    @property
    def state(self) -> ColdStartState:
        """Where reconciliation stands. For evidence and the outcome record."""
        return self._state

    # -- internals ----------------------------------------------------------

    def _admit(
        self,
        truth: BrokerTruth,
        triggers: tuple[FlattenTrigger, ...],
        now: float,
        phrase: str,
    ) -> ReconcileOutcome:
        """The ONE place registration becomes admissible. Provably flat only."""
        self._state = ColdStartState.FLAT_ASSERTED
        self._admitted = True
        reason = (
            f"cold-start: provably flat ({phrase}); registration admitted "
            f"(§4 V34), broker balance {truth.balance!r}"
        )
        self._book(now, reason)
        return ReconcileOutcome(
            state=self._state,
            truth=truth,
            flattened=triggers,
            admitted=True,
            reason=reason,
        )

    def _hold(self, truth: BrokerTruth, now: float, reason: str) -> ReconcileOutcome:
        """Hold in HALT with the loud alert. Admits NOTHING (§4, directive 4)."""
        self._state = ColdStartState.HELD_IN_HALT
        self._admitted = False
        self._halt.hold_in_halt(reason)
        self._book(now, reason)
        return ReconcileOutcome(
            state=self._state,
            truth=truth,
            flattened=(),
            admitted=False,
            reason=reason,
        )

    def _book(self, now: float, reason: str) -> None:
        """§12.10's cold-start outcome row, on the sole Plane-1 writer (§9).

        Booked under `EventKind.BOOT`: the frozen seam's `EventKind` has no
        `COLD_START` member (its docstring refuses to invent inventory rows for
        machinery that does not exist), and cold-start reconciliation IS the boot
        event. The dedicated kind is an integration debt, not a member added here.
        """
        self._plane1.enqueue(
            EventRow(
                kind=EventKind.BOOT,
                ts=now,
                strategy_id=SYSTEM_ACTOR,
                reason=reason,
                fields={
                    "state": self._state.value,
                    "admitted": repr(self._admitted),
                },
            )
        )
