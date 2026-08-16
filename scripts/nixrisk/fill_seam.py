"""The Limiter's fill-handler seam — types and ports, no behaviour (§4, D3.178).

ARC 034 / Phase 0.6(b). Landed BEFORE the handler so the handler, its gate and
the integration drill can be built against a settled boundary.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the line. `D3.<n>` cites `docs/CHECK-DEBT.md`.

------------------------------------------------------------------------------
WHY THIS SEAM EXISTS — the mechanism that was landed and never CALLED
------------------------------------------------------------------------------
ARC 029 built `nixrisk.stops.StopBook.arm` — §4's distance→price conversion at
confirmed fill. ARC 033 built `nixrisk.positions.PositionOriginWriter.on_fill` —
§3's origin write, which publishes `PositionRow.stop_distance` from the armed
stop, and gated it with `checks/check_origin_write.py`.

**Both had ZERO production callers** (D3.178). So the bucket cap that §7:501
prices exposure from was pricing a field that nothing in production ever
populated: a gate green over a mechanism nothing invokes. *A decision recorded is
not a mechanism landed, and a mechanism landed is not a mechanism CALLED.*

This seam declares the missing caller's surface. It is a SEAM and not the caller:
the behaviour is `nixrisk/fills.py`.

------------------------------------------------------------------------------
WHY THESE PORTS ARE DECLARED HERE AND NOT ADDED TO `nixrisk/seam.py`
------------------------------------------------------------------------------
`nixrisk/seam.py` is at `SEAM_REV 1.1.0` and widening a frozen port is an
architect ruling. `positions.py` set the precedent for the alternative and stated
it: *"a consumer declaring the surface it actually consumes is ordinary"*
(`StopLookupPort`). Every port below is that — the narrow surface the fill
handler consumes, satisfied by classes that already exist and were written
without knowledge of this file.

**Each port is NARROWER than the class that satisfies it, deliberately.**
`StopArmPort` has `arm` and nothing else, so the handler structurally cannot
`forget` a stop, `maintain` one, or read the book. Narrowing is how the authority
boundary stops being a convention.

------------------------------------------------------------------------------
SYNCHRONOUS, every verb — §5, §3
------------------------------------------------------------------------------
§5 fixes the Limiter as a single-threaded event loop and says serial processing
*"eliminates fill-vs-tick races by construction"*. §3's ATOMICITY RULE publishes
balance and the position table *"as one snapshot — never two separate reads"*.

`on_fill` performs FOUR state changes that §3 and §4 require to be one motion:
the stop is armed, the remainder is cancelled, the reservation is released, and
the row is published. An `async def` anywhere in that sequence is a declared
suspension point, and the loop servicing a second fill inside it would publish a
snapshot from between two halves of one fill — the exact tear §3 forbids and the
exact race §5 claims to have eliminated.

The one async surface in the neighbourhood is §10's outbound sender, already
declared in `scripts/broker/broker_seam.py`. This module does not restate it.

------------------------------------------------------------------------------
THE ORDER IS THE SAFETY PROPERTY, so it is a declared VALUE (`FillStep`)
------------------------------------------------------------------------------
`PositionOriginWriter.on_fill` REFUSES a fill with no armed stop, loudly, and
records it in `unstopped()` — because §7:501 prices bucket exposure from
`stop_distance` and a defaulted zero *"would price a real position at zero dollar
risk, make the correlation bucket read emptier than it is and ADMIT MORE"*
(D3.136's fail-open under a new spelling).

So the arm MUST precede the write, and the ordering is not a convention an
implementation may reorder for tidiness:

  1. `FillStep.ARM_STOP`        — `StopArmPort.arm(fill_price, order)`, §4.
  2. `FillStep.RELEASE_REMAINDER` — IOC-cancel the unfilled remainder and release
     its reservation, §4's partial-fill rule.
  3. `FillStep.ORIGIN_WRITE`    — `OriginWritePort.on_fill(...)`, §3's row, with
     the post-release reservation total so both land under ONE version stamp.

Step 2 sits BETWEEN them for a stated reason: §4 requires the published snapshot
to carry *"the true filled size, the real committed margin, and the reservation
for the unfilled portion released"* — all in the write of step 3. Releasing after
the write would publish a snapshot in which the over-reserved capital is still
taken, which is §4's *"not on a delay"* violated by one step.

**`FillStep` is an `enum.IntEnum` and its values ARE the order.** A gate can
therefore assert the sequence by comparing observed step values, rather than by
reading the handler's source and believing it.

------------------------------------------------------------------------------
THE JOIN IS NOT COLLAPSED — D3.177, the architect ruling
------------------------------------------------------------------------------
`trade_id` and `client_order_id` stay DISTINCT with an explicit, gated,
Limiter-owned join (`seam.TradeOrigin` / `seam.TradeOriginPort`, ARC 033).
`positions.identity_trade_id` — which returns `order.client_order_id` unchanged —
is the DEGENERATE mint, and it is exactly the hard-coded equality the ruling
forbids in production: an equality that holds by construction hides every skew,
because there is no observation that could contradict it.

`TradeIdMintPort` below is declared so the production mint is an INJECTED,
NAMEABLE policy rather than a default nobody chose. `NON_IDENTITY_MINT_REQUIRED`
states the rule the gate enforces.

------------------------------------------------------------------------------
WHAT THIS SEAM DELIBERATELY DOES NOT DECIDE
------------------------------------------------------------------------------
How a `trade_id` is spelled, what the IOC cancel does on the wire, the Plane-1
`filled` event kind (`seam.EventKind` has no member for it and adding one is a
frozen-seam edit), trailing-stop maintenance, and what a supervising loop does
with an `unstopped()` record. Those are behaviour or frozen-seam authority.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nixrisk.execution import ExecutionReport
from nixrisk.positions import OriginWrite
from nixrisk.seam import ProposedOrder, StopState

# R0903 (too-few-public-methods): every `Protocol` below is a SINGLE-VERB port
# and the narrowness IS the declared property — see "WHY THESE PORTS ARE DECLARED
# HERE" above. `StopArmPort` has `arm` and nothing else precisely so the fill
# handler structurally cannot `forget` a stop, `maintain` one, or fire an exit
# from inside a fill; `check_fill_seam` ARM 4 reddens if it ever stops being a
# proper subset of `seam.StopBookPort`. Adding a second verb to satisfy a default
# threshold of two would widen the surface this file exists to narrow. The
# threshold is about behavioural classes accreting state; these carry no
# behaviour at all. `positions.StopLookupPort` documents the same case.
# pylint: disable=too-few-public-methods

#: This seam's revision. Read by `checks/check_fill_seam.py`, which refuses a
#: shape change that did not move it.
FILL_SEAM_REV = "1.0.0"

#: D3.177's rule, stated where the gate can read it. The production mint may not
#: be `positions.identity_trade_id`: an equality that holds by construction is
#: unfalsifiable, so no observation can ever report skew between the two keys.
NON_IDENTITY_MINT_REQUIRED = True


class FillStep(enum.IntEnum):
    """The handler's three steps. **The VALUES are the order** (see the header).

    `IntEnum`, not `Enum`, so a gate can assert `observed == sorted(observed)`
    over real recorded steps. Ordering asserted from source order proves nothing
    about execution order — `check_limiter_seam` ARM 3 already records that
    lesson one module over.
    """

    ARM_STOP = 1
    RELEASE_REMAINDER = 2
    ORIGIN_WRITE = 3


@runtime_checkable
class StopArmPort(Protocol):
    """§4's distance→price conversion at confirmed fill. SYNCHRONOUS.

    ONE verb. Satisfied by `nixrisk.stops.StopBook.arm` structurally, without
    that class knowing this port exists.

    **Narrower than `seam.StopBookPort` on purpose**: no `forget`, no `maintain`,
    no `breached`. The fill handler arms; per-tick maintenance and stop-out
    detection belong to the tick path, and a handler holding those verbs could
    fire an exit from inside a fill — §14 makes execution of any flatten
    Limiter-only and `nixrisk.flatten` owns it, not this.
    """

    def arm(self, fill_price: float, order: ProposedOrder) -> StopState:
        """Convert the order's tick distance to an absolute price, ONCE (§4)."""


@runtime_checkable
class OriginWritePort(Protocol):
    """§3's origin write. SYNCHRONOUS. Satisfied by `PositionOriginWriter`.

    `sum_reservations` is keyword-only and is the post-release total, so §3's
    atomicity rule holds across the whole fill: the released remainder and the
    published position land under ONE version stamp. Passing `None` carries the
    previous figure forward and DOUBLE-COUNTS the filled portion — conservative,
    still wrong, and `positions.py` says so in its own docstring.
    """

    def on_fill(
        self, report: ExecutionReport, *, sum_reservations: float | None = ...
    ) -> OriginWrite:
        """Publish §3's row for this fill, `stop_distance` from the armed stop."""


@runtime_checkable
class ApprovedOrderPort(Protocol):
    """The `ProposedOrder` the Limiter approved for this order id. A LOOKUP.

    Needed because `arm` converts from `ProposedOrder.stop_ticks` — *the sizer's
    own distance* (§7:476) — and an execution report does not carry it. The
    handler must NOT reconstruct the order from the fill: a distance re-derived
    at fill time is a value the system chose twice, and `check_origin_write`
    exists precisely to keep the published distance traceable to the approval.

    Returns `None` for an unknown order rather than raising, matching
    `TradeOriginPort`'s reasoning: an unknown order is a question with an answer,
    and the caller holds the context to decide whether it is fatal.
    """

    def order_for(self, client_order_id: str) -> ProposedOrder | None:
        """The approved order, or `None` if this Limiter never approved it."""


@runtime_checkable
class RemainderPort(Protocol):
    """§4's partial-fill remainder: IOC-cancel it, release its reservation.

    SYNCHRONOUS, and the two halves are ONE verb on purpose. §4 makes them one
    fact — *"cancels the unfilled remainder (IOC-style)"* and *"the reservation
    for the unfilled portion released"* — and splitting them into two ports would
    admit a state in which the order is cancelled while its capital is still
    reserved. That state is invisible to every consumer and errs toward LESS
    deployable capital, which is the failure `positions.py` already documents as
    conservative-and-still-wrong.

    Returns the post-release Σ reservations, which is exactly what step 3 hands
    to `OriginWritePort.on_fill`.
    """

    def release_remainder(
        self, client_order_id: str, *, filled_qty: int, requested_qty: int
    ) -> float:
        """Cancel the unfilled remainder, release its reservation, return Σ.

        `filled_qty` is the CUMULATIVE filled quantity and `requested_qty` the
        approved size. Both are passed rather than a single "remainder" figure so
        the implementation, not the caller, owns the subtraction — a caller that
        computed the remainder would be a second place the partial-fill
        arithmetic lives.
        """


@runtime_checkable
class TradeIdMintPort(Protocol):
    """How a `trade_id` is minted from the order that opened it (D3.177).

    A PORT rather than a bare callable so the production policy has a name, an
    identity and a place a gate can find it. `NON_IDENTITY_MINT_REQUIRED` above
    states the rule: whatever this returns, it may not be `client_order_id`
    unchanged, because an identity mapping makes the round-trip gate pass on
    every possible input and therefore measures nothing.
    """

    def mint(self, order: ProposedOrder) -> str:
        """This order's `trade_id`. Distinct from `order.client_order_id`."""


@dataclass(frozen=True)
class FillOutcome:
    """What one confirmed fill actually did. The handler's OBSERVABLE result.

    **`steps` is the sequence the handler REALLY executed**, appended as each
    step completes, and it is the reason this type exists rather than the handler
    returning `OriginWrite` alone. §4's recovery ordering taught the same lesson
    one module over: *the order is the safety property — prove it by observing
    the sequence, not by asserting it*. A gate reading `steps` observes what ran;
    a gate reading the handler's source observes what was written.

    `armed` is the `StopState` step 1 produced. Carrying it lets a gate prove the
    published `stop_distance` came from THIS arm rather than from a second stop
    book constructed elsewhere — the independence `check_origin_write` requires
    between the two sides.
    """

    steps: tuple[FillStep, ...]
    armed: StopState
    write: OriginWrite
    #: Σ reservations after the remainder release — the figure step 3 published.
    sum_reservations: float
    #: Cumulative filled quantity, from the execution ledger. §4: the position is
    #: the ACTUAL filled qty. Carried so a gate can prove the stop was armed
    #: against the filled size and not the requested one (a silent over-stop).
    filled_qty: int
    #: The approved size. Present so the pair above is comparable in one place.
    requested_qty: int


@runtime_checkable
class FillHandlerPort(Protocol):
    """THE CALLER D3.178 SAID WAS MISSING. SYNCHRONOUS (see the header).

    One verb, one event: a confirmed fill (§14: *"Open" = confirmed fill only.
    Never optimistic*) becomes an armed stop, a released remainder, and a
    published §3 row — in that order, under one version stamp.

    Raises rather than returning a partial outcome. There is no half-handled
    fill: `PositionOriginWriter` already refuses an unstopped fill loudly, and a
    handler that swallowed that refusal to return a "mostly fine" outcome would
    reintroduce the fail-open the refusal exists to prevent.
    """

    def on_fill(self, report: ExecutionReport) -> FillOutcome:
        """Handle one confirmed fill. Arms, releases, publishes — in that order."""
