"""§5:322's THIRD loop input: sender completions, and their dispatch to §3.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 046 — the I1 SPIKE. §5:322-324 gives the Limiter three serial inputs:

    - **Limiter = single-threaded event loop** (shared-mem price poll + ZMQ
      inbox + sender completions, processed serially) + **one low-priority
      sender thread** (blocking I/O, releases GIL; hung socket contained; hot
      loop never blocks). Serial processing eliminates fill-vs-tick races by
      construction.

Two of those three existed before this module. `nixrisk/loop.py` ticks, and
`scripts/limiterd.py` reads the inbox inside the tick. **Sender completions did
not exist anywhere.** Measured at ARC 046 S1 against `dc78249`: the string
`completion` appeared exactly once in the whole Limiter surface, inside that
docstring quote, and the daemon's only inbound verb set was
`['register', 'go', 'status', 'resolve']`. §3's terminal handlers
(`nixrisk/outcomes.py`) were proven correct — ARC 044 discharged I2 over them —
and nothing in a running process had ever called one.

That is the gap this module closes for ONE path.

------------------------------------------------------------------------------
WHAT THIS MODULE IS, AND WHAT IT DELIBERATELY IS NOT
------------------------------------------------------------------------------
It is the parse, the §4:214 dedup, and the dispatch. It is NOT a handler: every
release is `nixrisk/outcomes.py`'s, called, never reimplemented. `outcomes.py`
and `reservations.py` are BYTE-IDENTICAL across this arc and that is asserted by
`git hash-object`, not by intent.

**ARC 047 wires the SECOND path: `on_fill`.** `on_reject`, `on_ack`,
`on_position`, `on_balance`, `on_margin` and `on_session` (§2A:74-84) all still
parse and all still reach `dispatch`, and every one of them returns `UNWIRED`
naming itself. That is the deliberate shape of a spike: an unwired event must be
READABLE as unwired rather than absorbed as handled, because "the daemon
processed it" and "the daemon dropped it" are the two readings ARC 046 exists to
keep apart. A silent drop here would let a future arc believe a path works.

------------------------------------------------------------------------------
ARC 047 — WHY FILL NEEDED A SECOND PORT, MEASURED RATHER THAN ASSUMED
------------------------------------------------------------------------------
ARC 046 wired cancel through `OutcomesPort` — structurally
`nixrisk.outcomes.OrderOutcomes` — and the wiring cost was a single call. Fill
could not reuse it, and the reason is a measurement, not a preference:
`OrderOutcomes` **has no `on_fill`**, and its own `HANDLES` map declares the
three §3 paths it books as `{CANCEL, REJECT, PENDING_TIMEOUT}`. `TerminalPath`
has a `FILL` member and `outcomes.py` deliberately does not serve it, because
**fill is not a release — §3 says the reservation *converts to open-margin***,
which is an arm, a cancel of the remainder, a release, a published position row
and a minted `trade_id`, in a fixed order. That cascade already exists whole in
`nixrisk/fills.py` (`FillHandler` / `LimiterFillSink`, ARC 034), and it satisfies
a different surface.

So this module gained a SECOND port (`FillSinkPort`) rather than a second verb
on the first. The two are not interchangeable and collapsing them would put a
release and a conversion behind one name.

**THE ORDER IS THE SAFETY PROPERTY AND IT IS NOT THIS MODULE'S.** `fills.py`
arms the stop FIRST (§4's distance->price conversion at the confirmed fill),
releases the remainder second, and publishes third — and it RAISES rather than
returning a partial outcome. This module therefore never sees a half-handled
fill: either the whole cascade ran or the handler raised and nothing was
published. `_dispatch_fill` nevertheless re-asserts, at the daemon boundary,
that the dispatched fill produced an ARMED STOP and an OPEN row, because a
conversion without a stop is an UNPROTECTED POSITION (§4, §12.1) and the
daemon must not be able to create one silently.

**NO order is placed and nothing is sent.** Nix stops are SYNTHETIC (§12.1:
*"This is our software, not a broker-side stop"*), so "the protective stop is
placed" means `nixrisk.stops.StopBook` holds a live `StopState` at
`fill -/+ distance x tick_size` for that order. There is no broker-side stop
order and there must not be one.

------------------------------------------------------------------------------
WHY THE DEDUP IS HERE AND NOT LEFT TO THE LEDGER
------------------------------------------------------------------------------
`ReservationLedger.resolve` already refuses a second terminal event for one
`client_order_id` — ARC 044 / I2, and that guard stands. It is NOT the same
property. §4:214 is explicit:

    **Idempotent execution handling:** broker events are deduplicated by
    (order_id, exec_id); position state derives from cumulative fills — immune
    to duplicate or out-of-order execution reports.

The key is the PAIR. Two distinct exec reports for one order are two events the
ledger must see (a fill then its remainder cancel, §4's own named race); ONE
exec report delivered twice is one event a venue re-sent, and it must never
reach a handler at all. Leaving that to the ledger's refusal would mean every
re-delivery booked a spurious `Refusal` — a record that reads, to anything
auditing §11.7's reconcile, exactly like a real venue anomaly. Deduping on the
pair keeps the ledger's refusal list meaning what it says.

Bounded, for §11:581. An unbounded set of every exec id a long-lived daemon ever
saw is a leak on the hot path; `DEDUP_MAX` is the ceiling and eviction is FIFO.
A key evicted under pressure is a key that can be re-dispatched, so the ceiling
is generous and `evicted` is COUNTED and reported — an operator reading a
non-zero `evicted` is reading the one condition under which this guard weakens,
rather than trusting a guarantee that quietly stopped holding.

------------------------------------------------------------------------------
`debug.md` §7.12 — THE STANDING QUESTION
------------------------------------------------------------------------------
What would have to be true for a run of this module to look healthy while
proving nothing?

 1. **Nothing was ever dispatched, and the absence read as "no completions
    arrived".** GUARDED: `DispatchLedger` counts `seen`, `dispatched`,
    `duplicates`, `unwired`, `refused` and `malformed` SEPARATELY, so *never
    arrived*, *arrived and dispatched*, *arrived and deduped* and *arrived and
    dropped* are five distinguishable readings rather than one silence.
 2. **The dispatch ran but the handler did nothing**, and a bare "dispatched"
    counter credited it. GUARDED: `DispatchResult.released_margin` is read off
    the `OutcomeRecord` the handler RETURNED, so a dispatch that released
    nothing reports zero rather than success.
 3. **The dedup deduped everything**, including first deliveries, and a
    permanently-quiet handler looked idempotent. GUARDED: a duplicate is
    counted as `duplicates` and never as `dispatched`, and the gate's DRIVEN arm
    asserts a FIRST delivery releases before it asserts a second does not.
 4. **The completion never crossed a thread boundary** — a test that called
    `dispatch` directly would prove the handler works and say nothing about the
    daemon, which is the exact failure ARC 038 found five times. GUARDED:
    `SenderCompletion.source` records where the completion was parsed from, and
    the gate asserts it arrived through the loop's own drain.
 5. **A malformed completion killed the tick.** GUARDED: `parse_completion`
    raises `MalformedCompletion` and nothing else; the caller in
    `scripts/limiterd.py` contains it into a counter, because a Limiter that
    died of one bad exec report would be a remote kill switch on the process
    holding every synthetic stop (§12.1:604).
 6. **ARC 047. A fill "dispatched" and the position opened with NO STOP** —
    the one reading that would be worse than not wiring fill at all, because an
    unprotected position is the hazard I11 exists to guard. GUARDED TWICE:
    `fills.py` arms BEFORE it releases and raises rather than returning a
    partial outcome, and `_dispatch_fill` then re-asserts at the daemon
    boundary that the outcome carries an armed `StopState` and an OPEN row —
    a fill that converted margin without a stop is `REFUSED`, never
    `DISPATCHED`, and the reason names the unprotected position.
 7. **ARC 047. A fill dispatch was credited without the reservation actually
    converting.** GUARDED: `DispatchResult.converted_margin` is read off the
    `FillOutcome` the handler RETURNED (its published picture's Σ open margin),
    not from a counter this module increments, so a cascade that armed and
    published nothing reports zero rather than success — guard 2 for fill.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

#: Named once so every refusal points at the same file (doctrine C.2).
SITE: Final[str] = "scripts/nixrisk/completions.py"

#: §2A:74-84's pushed broker events, TRANSCRIBED. The list is the spec's, not
#: this build's: an event named here and not wired is `UNWIRED` and says so; an
#: event NOT named here is `UNKNOWN` and is refused. Two different readings.
EVENT_ACK: Final[str] = "on_ack"
EVENT_FILL: Final[str] = "on_fill"
EVENT_CANCEL: Final[str] = "on_cancel"
EVENT_REJECT: Final[str] = "on_reject"
EVENT_BALANCE: Final[str] = "on_balance"
EVENT_MARGIN: Final[str] = "on_margin"
EVENT_POSITION: Final[str] = "on_position"
EVENT_SESSION: Final[str] = "on_session"
SPEC_EVENTS: Final[tuple[str, ...]] = (
    EVENT_ACK,
    EVENT_FILL,
    EVENT_CANCEL,
    EVENT_REJECT,
    EVENT_BALANCE,
    EVENT_MARGIN,
    EVENT_POSITION,
    EVENT_SESSION,
)

#: The §2A events this build DISPATCHES. Spelled as a tuple so an arc adds a
#: member rather than editing a condition, and so a census can read which paths
#: this build actually serves without executing it. ARC 046 put `on_cancel`
#: here; ARC 047 added `on_fill`; ARC 053 added `on_reject`.
#: `checks/check_limiter_daemon_dispatch.py` READS this tuple, so the gate's
#: UNWIRED arm narrows as the tuple grows instead of going quietly stale.
WIRED_EVENTS: Final[tuple[str, ...]] = (EVENT_CANCEL, EVENT_FILL, EVENT_REJECT)

#: §4:214's dedup ceiling. Bounded for §11:581; see the module docstring on why
#: eviction is counted rather than assumed away.
DEDUP_MAX: Final[int] = 65536

#: Wire version for a completion file. Its OWN namespace: a completion is
#: written by the broker seam, and the command schema is written by a client.
COMPLETION_SCHEMA: Final[int] = 1


class CompletionError(RuntimeError):
    """Base for everything this module refuses."""


class MalformedCompletion(CompletionError):
    """The bytes could not be read as a §2A exec report. Names why."""


class OutcomesPort(Protocol):  # pylint: disable=too-few-public-methods
    """The §3 terminal-handler surface this module CALLS and never reimplements.

    Structurally `nixrisk.outcomes.OrderOutcomes`. Declared as a Protocol so the
    dependency points one way — the dispatcher knows the handler's shape, the
    handler knows nothing about the daemon — and so the byte-identity of
    `outcomes.py` across this arc is a fact rather than a hope.
    """

    def on_cancel(self, client_order_id: str, *, reason: str = "") -> Any:
        """§3's cancel release. ARC 044 / I2 proved it; ARC 046 CALLS it."""

    def on_reject(self, client_order_id: str, *, reason: str = "") -> Any:
        """§3's reject release. ARC 044 / I2 proved it; ARC 053 CALLS it.

        A SECOND verb rather than one `resolve(via=...)`: `outcomes.py` spells
        its three `resolve(..., TerminalPath.X, ...)` calls literally so the AST
        census that measures which §3 release paths production books can read
        the `via` STATICALLY, and a port that collapsed the two verbs here would
        push the same unreadability up one layer. Two verbs are also two
        INDEPENDENTLY plantable dispatch sites, which is what makes PLANT A
        (reject dispatch removed) unable to hide behind the cancel arm.
        """


class FillSinkPort(Protocol):  # pylint: disable=too-few-public-methods
    """ARC 047. §2A:75's `on_fill` broker event surface, as this module CALLS it.

    Structurally `nixrisk.fills.LimiterFillSink`. Declared as a Protocol for the
    reason `OutcomesPort` is: the dependency points one way, and `fills.py` is
    byte-identical across this arc because nothing here reached into it.

    **TWO verbs, and the second is not decoration.** `on_fill` returns `None` —
    that shape is `broker_seam.OrderEventSink`'s and this module may not widen
    it — so a dispatcher holding only `on_fill` could count a dispatch and know
    nothing about what the cascade did. `outcomes()` is how the handler's OWN
    answer is read back, which is §7.12 guard 2 (*the dispatch ran but the
    handler did nothing*) applied to a verb that cannot return one.

    NARROWER than `LimiterFillSink` deliberately: no reader for the approval
    book, no stop book, no picture. A dispatcher that could arm a stop would be a
    second conversion site and §4 converts ONCE, at the confirmed fill.
    """

    # The six positional fields are §2A's own `on_fill` signature, transcribed.
    def on_fill(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        client_order_id: str,
        exec_id: str,
        symbol: str,
        filled_qty: int,
        price: float,
        cumulative_qty: int,
    ) -> None:
        """One §2A confirmed fill. Arms the stop, releases, publishes (§4, §3)."""

    def outcomes(self) -> tuple[Any, ...]:
        """Every `FillOutcome` this sink produced, in arrival order."""


# R0902 refused with a reason: NINE fields, and SIX of them are §2A:74-84's own
# `on_fill` signature transcribed (`client_order_id`, `exec_id`, `symbol`,
# `done_qty`, `price`, `cumulative_qty`). Collapsing any of them into `raw`
# would move a field the dispatch passes into a FROZEN six-argument seam back
# into an untyped dict, and reading it out at call time is a second parse —
# outside the tick's one parse, and unguarded. `event`, `source` and `raw` are
# the observation's own identity. The threshold is about behavioural classes
# accreting state; this carries no behaviour at all.
@dataclass(frozen=True)
class SenderCompletion:  # pylint: disable=too-many-instance-attributes
    """ONE §5:322 sender completion, parsed. AN OBSERVATION, not a decision.

    `source` is not decoration. ARC 038's deepest finding was that every Limiter
    invariant in this tree was proven about a library a test constructed; a
    completion that cannot say where it entered the process cannot distinguish
    "the daemon dispatched it" from "the test called the handler".
    """

    event: str
    client_order_id: str
    exec_id: str
    done_qty: int
    source: str
    #: ARC 047. §2A:75's `on_fill` carries three fields no other §2A event does:
    #: the instrument, the execution price and the venue's running total. They
    #: are members here rather than left in `raw` because `_dispatch_fill` passes
    #: them into a FROZEN six-argument seam (`OrderEventSink.on_fill`), and a
    #: dispatch reading them back out of an untyped dict at call time would be a
    #: second parse — outside the tick's one parse, and unguarded.
    #:
    #: Zero/empty on every NON-fill event and that is not a default standing in
    #: for a missing value: §2A's `on_cancel` genuinely carries no price. The
    #: parse below REFUSES a fill that omits any of them, so an empty symbol on a
    #: fill is impossible by construction rather than by convention.
    symbol: str = ""
    price: float = 0.0
    cumulative_qty: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def dedup_key(self) -> tuple[str, str]:
        """§4:214's key: the PAIR. See the module docstring on why not the order."""
        return (self.client_order_id, self.exec_id)


class Disposition:  # pylint: disable=too-few-public-methods
    """What `dispatch` did. Five outcomes, none of them a bare boolean."""

    DISPATCHED: Final[str] = "dispatched"
    DUPLICATE: Final[str] = "duplicate"
    UNWIRED: Final[str] = "unwired"
    UNKNOWN: Final[str] = "unknown"
    REFUSED: Final[str] = "refused"


# R0902 refused with a reason: NINE fields, and FIVE of them are the FILL
# observables — every one read off the `FillOutcome` the handler RETURNED, never
# counted here. Dropping one to satisfy the counter would remove a measurement
# from a gate's verdict: `stop_level` is what makes an unprotected position
# detectable at this boundary, and `converted_margin` is §7.12 guard 7 applied
# to a sink verb that returns `None`.
@dataclass(frozen=True)
class DispatchResult:  # pylint: disable=too-many-instance-attributes
    """One dispatch decision, with the handler's own answer folded in."""

    disposition: str
    completion: SenderCompletion
    reason: str
    released_margin: float = 0.0
    #: ARC 047, the FILL observables. Every one is read off the `FillOutcome` the
    #: handler RETURNED — never counted here — for the reason `released_margin`
    #: is (§7.12 guard 2): a cascade that armed nothing and published nothing
    #: must report zeros, not a dispatch.
    trade_id: str = ""
    #: The absolute price §4's distance->price conversion produced at the
    #: confirmed fill. 0.0 means NO STOP, which is never a `DISPATCHED` fill.
    stop_level: float = 0.0
    stop_distance_ticks: int = 0
    #: Signed §3 position size on the published row. §14: *"Open" = confirmed
    #: fill only.*
    opened_size: int = 0
    #: Σ open margin on the picture this fill published — the *converts to
    #: open-margin* half of §3's lifecycle, as the writer itself reported it.
    converted_margin: float = 0.0
    # NO `dispatched` convenience property. `disposition` is the answer and it
    # has five values; a boolean beside it would be a second, lossier spelling
    # of the same fact that a reader could take for the whole one — and
    # `check_uncalled_entry_points` measured it as public surface nothing calls.


def parse_completion(blob: bytes | str, *, source: str) -> SenderCompletion:
    """Read one §2A exec report. Raises `MalformedCompletion`, never anything else.

    The parse is a DECISION and decisions belong in the tick (§5:322's serial
    processing) — the same argument `scripts/limiterd.py`'s `RawCommand` makes
    for carrying bytes rather than a parsed object across the ingress.
    """
    text = blob.decode("utf-8", "replace") if isinstance(blob, bytes) else blob
    try:
        raw = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise MalformedCompletion(
            f"{SITE}: completion from {source!r} is not JSON: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise MalformedCompletion(
            f"{SITE}: completion from {source!r} is a "
            f"{type(raw).__name__}, not an object"
        )
    schema = raw.get("schema")
    if schema != COMPLETION_SCHEMA:
        raise MalformedCompletion(
            f"{SITE}: completion schema {schema!r} != this build's "
            f"{COMPLETION_SCHEMA} — refusing to read fields into a meaning they "
            "may not have"
        )
    event = str(raw.get("event") or "")
    if not event:
        raise MalformedCompletion(
            f"{SITE}: completion from {source!r} names no event; §2A:74-84's "
            f"pushed events are {list(SPEC_EVENTS)}"
        )
    client_order_id = str(raw.get("client_order_id") or "")
    if not client_order_id:
        raise MalformedCompletion(
            f"{SITE}: {event} from {source!r} carries no client_order_id — §3's "
            "release is keyed by the identifier the broker event actually carries"
        )
    exec_id = str(raw.get("exec_id") or "")
    if not exec_id:
        # FAIL CLOSED. §4:214 dedups by (order_id, exec_id); an event with no
        # exec_id cannot be deduplicated, so absorbing it would mean the one
        # guarantee §15:1004 names is silently off for that event. Refusing is
        # the lesser fault: a refused completion is a counted, named refusal.
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} from {source!r} carries no "
            "exec_id. §4:214 deduplicates broker events by (order_id, exec_id) — "
            "an event that cannot be keyed cannot be made idempotent, and a "
            "re-delivery would release twice"
        )
    try:
        done_qty = int(raw.get("done_qty") or 0)
    except (TypeError, ValueError) as exc:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} has non-integer "
            f"done_qty={raw.get('done_qty')!r}"
        ) from exc
    symbol, price, cumulative = _fill_fields(raw, event, client_order_id, done_qty)
    return SenderCompletion(
        event=event,
        client_order_id=client_order_id,
        exec_id=exec_id,
        done_qty=done_qty,
        source=source,
        symbol=symbol,
        price=price,
        cumulative_qty=cumulative,
        raw=raw,
    )


# R0911 (too-many-return-statements) is not reached, but the ladder below is the
# same fail-closed shape `limiterd.CommandHandler._reply_for` records: five
# distinguishable refusals, each naming which field of §2A:75 was unusable and
# what it would have decided. One reason string over all five would make the
# gate's REASON assertion (check contract v2 rule 11) unable to tell them apart.
def _fill_fields(
    raw: dict[str, Any], event: str, client_order_id: str, done_qty: int
) -> tuple[str, float, int]:
    """ARC 047. §2A:75's three fill-only fields, or a named refusal.

    Returns `("", 0.0, 0)` for every NON-fill event: §2A's other pushed events
    genuinely do not carry an instrument, a price or a running total, so reading
    them there would invent values rather than parse them.

    For a fill, every one of the three is REQUIRED and the refusals are separate.
    Fail closed, and the reason is the whole point of doing it here rather than
    letting the cascade discover it: `StopBook.arm` needs a positive finite price
    to anchor against and a symbol to scale by (§4, §4:198), `ExecutionReport`
    needs a signed cumulative to derive position state from (§4), and a fill that
    reached the handler missing any of them would fail DEEP — after the §4:214
    dedup key was already claimed, which is the one place a refusal cannot be
    retried.
    """
    if event != EVENT_FILL:
        return "", 0.0, 0
    symbol = str(raw.get("symbol") or "")
    if not symbol:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} names no symbol. §4:198 "
            "makes a symbol with no instrument scale NOT-TRADABLE, and the "
            "distance->price stop conversion has no tick size to multiply by — "
            "refusing rather than opening a position this Limiter cannot protect"
        )
    try:
        price = float(raw.get("price"))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} in {symbol!r} has "
            f"non-numeric price={raw.get('price')!r} — §4 anchors the synthetic "
            "stop against the CONFIRMED fill price and there is nothing to anchor"
        ) from exc
    if not math.isfinite(price) or price <= 0.0:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} in {symbol!r} has "
            f"price={price!r}, which is not a positive finite number. §4's stop "
            "is anchored at fill -/+ distance x tick_size; a non-finite anchor "
            "produces a stop level nothing can compare a price against"
        )
    if done_qty <= 0:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} in {symbol!r} has "
            f"done_qty={done_qty!r}. §14 makes OPEN a CONFIRMED FILL and nothing "
            "else; a fill of zero contracts is not a confirmation, and §4's "
            "remainder arithmetic (requested minus filled) is a statement about "
            "nothing when filled is non-positive"
        )
    try:
        cumulative = int(raw.get("cumulative_qty") or 0)
    except (TypeError, ValueError) as exc:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} has non-integer "
            f"cumulative_qty={raw.get('cumulative_qty')!r} — §4 derives position "
            "state from CUMULATIVE fills, so an unreadable running total makes "
            "every partial fill's published size a guess"
        ) from exc
    if cumulative < done_qty:
        raise MalformedCompletion(
            f"{SITE}: {event} for {client_order_id!r} reports cumulative_qty="
            f"{cumulative} BELOW this execution's done_qty={done_qty}. The "
            "venue's running total cannot be smaller than the execution it "
            "includes; §4 makes the fill a fact the system reports, and a total "
            "that contradicts its own part is not one"
        )
    return symbol, price, cumulative


class ExecReportDedup:
    """§4:214 / §15:1004's exec-report dedup, keyed by (order_id, exec_id).

    Bounded and FIFO. `evicted` is counted because an evicted key is a key that
    can be re-dispatched: the guarantee weakens under pressure and an operator
    must be able to read that it did, rather than be told it never does.
    """

    def __init__(self, max_keys: int = DEDUP_MAX) -> None:
        if int(max_keys) < 1:
            raise CompletionError(
                f"{SITE}: max_keys={max_keys!r} — a dedup with no capacity "
                "deduplicates nothing and would report perfect idempotency"
            )
        self.max_keys = int(max_keys)
        self._keys: set[tuple[str, str]] = set()
        self._order: deque[tuple[str, str]] = deque()
        self.evicted = 0

    def __len__(self) -> int:
        return len(self._keys)

    def seen(self, key: tuple[str, str]) -> bool:
        """Has this exact (order_id, exec_id) been claimed? Does not claim it."""
        return key in self._keys

    def claim(self, key: tuple[str, str]) -> bool:
        """Claim the key. True = FIRST delivery; False = a re-delivery.

        The claim happens BEFORE the handler runs, not after. A handler that
        raised after a post-hoc claim would leave the key unclaimed and the next
        re-delivery would run it again — which is the double release §14 forbids,
        reached through the error path instead of the happy one.
        """
        if key in self._keys:
            return False
        self._keys.add(key)
        self._order.append(key)
        while len(self._order) > self.max_keys:
            self.evicted += 1
            self._keys.discard(self._order.popleft())
        return True


@dataclass
class DispatchLedger:  # pylint: disable=too-many-instance-attributes
    """What the dispatcher has done. Counters, never a boolean (§7.12 guard 1).

    `consumed` is NOT `seen`, and collapsing the two would break guard 1 in the
    one place it matters most. MEASURED, ARC 046 S5 PLANT A: with the dispatch
    call removed, a ledger that only counted inside `dispatch` reported zero —
    and *the loop never received a completion* and *the loop received one and
    told nobody* became one reading. The first is the gate's instrument being
    broken; the second is the defect the gate exists to catch. `consumed` is
    incremented by the caller the moment the LOOP HANDS IT A COMPLETION, before
    anything decides what to do with it, so the two stay apart.
    """

    consumed: int = 0
    seen: int = 0
    dispatched: int = 0
    duplicates: int = 0
    unwired: int = 0
    unknown: int = 0
    refused: int = 0
    malformed: int = 0
    released_margin: float = 0.0
    #: ARC 047. PER-PATH dispatch counts. `dispatched` alone cannot answer *which
    #: path ran*, and with two wired events that question is the whole subject:
    #: a gate asserting `dispatched == 1` after pushing a fill would be equally
    #: satisfied by a cancel. Two counters, two readings.
    #:
    #: ARC 053 adds the THIRD, and adding it was not optional. `_finish` counted
    #: every non-fill dispatch as a cancel, so the moment `on_reject` became a
    #: wired event a reject would have incremented `cancels_dispatched` — the
    #: precise defect the paragraph above says these counters exist to prevent,
    #: reached by a new event arriving rather than by anyone editing the counter.
    #: A per-path counter set that is not extended when a path is added is a
    #: counter set that silently stops discriminating.
    cancels_dispatched: int = 0
    fills_dispatched: int = 0
    rejects_dispatched: int = 0
    #: Σ open margin the last dispatched fill's published picture reported, and
    #: how many §3 rows this daemon has opened. Both come off the handler's own
    #: `FillOutcome` (§7.12 guard 7).
    converted_margin: float = 0.0
    opened: int = 0

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block, for `limiter.runtime.json`."""
        return {
            "consumed": self.consumed,
            "seen": self.seen,
            "dispatched": self.dispatched,
            "cancels_dispatched": self.cancels_dispatched,
            "fills_dispatched": self.fills_dispatched,
            "rejects_dispatched": self.rejects_dispatched,
            "duplicates": self.duplicates,
            "unwired": self.unwired,
            "unknown": self.unknown,
            "refused": self.refused,
            "malformed": self.malformed,
            "released_margin": self.released_margin,
            "converted_margin": self.converted_margin,
            "opened": self.opened,
            "wired_events": list(WIRED_EVENTS),
        }


class CompletionDispatcher:
    """§5:322's serial dispatch of ONE sender completion to §3's handler.

    Runs INSIDE the loop's tick and on the loop's thread. No thread of its own,
    no queue of its own: §5:323 puts the blocking I/O on the sender and §5:322
    puts the processing here, and *serial processing eliminates fill-vs-tick
    races by construction*. A dispatcher with its own worker would put the race
    back.
    """

    def __init__(
        self,
        outcomes: OutcomesPort,
        *,
        fills: FillSinkPort | None = None,
        dedup: ExecReportDedup | None = None,
    ) -> None:
        self._outcomes = outcomes
        #: ARC 047. OPTIONAL for the reason `limiterd.CommandHandler`'s ledger
        #: is: a build constructed without a fill path must serve `on_fill` as a
        #: NAMED REFUSAL rather than as an unwired event, because *this build has
        #: no fill sink* and *this build does not wire fill* are two readings and
        #: `WIRED_EVENTS` above already claims the second is false.
        self._fills = fills
        self.dedup = ExecReportDedup() if dedup is None else dedup
        self.ledger = DispatchLedger()
        #: Every result, oldest first, bounded. The gate reads it to prove a
        #: completion was PROCESSED before it reads any verdict about release.
        self.history: deque[DispatchResult] = deque(maxlen=256)

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. Counters PLUS the last decision.

        The last decision's `source` is what lets a reader outside this process
        tell "the daemon's loop dispatched a completion that entered from the
        completions directory" from "something in here called a handler" —
        §7.12 guard 4, and the whole reason ARC 038's five library proofs did
        not settle I1.
        """
        block = self.ledger.record()
        last = self.history[-1] if self.history else None
        block.update(
            {
                "last_disposition": None if last is None else last.disposition,
                "last_source": None if last is None else last.completion.source,
                "last_event": None if last is None else last.completion.event,
                "last_exec_id": None if last is None else last.completion.exec_id,
                "last_reason": None if last is None else last.reason,
                "dedup_keys": len(self.dedup),
                "dedup_evicted": self.dedup.evicted,
                #: ARC 047. What this DISPATCHER was actually constructed with,
                #: beside what the MODULE declares in `wired_events`. The two can
                #: disagree — a build that wires fill in the tuple and hands in
                #: no sink serves a named refusal — and check contract rule 10
                #: makes that difference the difference between *cannot measure*
                #: and *fail*.
                "fill_sink": self._fills is not None,
            }
        )
        return block

    def dispatch(self, completion: SenderCompletion) -> DispatchResult:
        """Dispatch one completion. NEVER RAISES on a handler's refusal."""
        self.ledger.seen += 1
        if completion.event not in SPEC_EVENTS:
            return self._finish(
                DispatchResult(
                    Disposition.UNKNOWN,
                    completion,
                    f"{SITE}: {completion.event!r} is not one of §2A:74-84's "
                    f"pushed events {list(SPEC_EVENTS)}",
                )
            )
        if completion.event not in WIRED_EVENTS:
            return self._finish(
                DispatchResult(
                    Disposition.UNWIRED,
                    completion,
                    f"{SITE}: {completion.event} is a §2A event this build does "
                    f"NOT dispatch. ARC 046 wired {list(WIRED_EVENTS)} and no "
                    "other path; the reservation for "
                    f"{completion.client_order_id!r} is UNCHANGED and this is "
                    "recorded, not absorbed",
                )
            )
        # §4:214. Claimed BEFORE the handler runs — see `ExecReportDedup.claim`.
        if not self.dedup.claim(completion.dedup_key):
            return self._finish(
                DispatchResult(
                    Disposition.DUPLICATE,
                    completion,
                    f"{SITE}: exec report {completion.dedup_key} already "
                    "dispatched. §4:214 deduplicates broker events by "
                    "(order_id, exec_id); a second dispatch would be the double "
                    "release §14 forbids, reached at the daemon boundary",
                )
            )
        if completion.event == EVENT_FILL:
            return self._finish(self._dispatch_fill(completion))
        if completion.event == EVENT_REJECT:
            return self._finish(self._dispatch_reject(completion))
        return self._finish(self._dispatch_cancel(completion))

    def _dispatch_cancel(self, completion: SenderCompletion) -> DispatchResult:
        """§3's cancel release. CALLS `outcomes.on_cancel`; never reimplements it."""
        record = self._outcomes.on_cancel(
            completion.client_order_id,
            reason=(
                f"{SITE}: the §5:323 sender surfaced a §2A on_cancel "
                f"(exec_id {completion.exec_id!r}, done_qty "
                f"{completion.done_qty}) and §5:322's loop dispatched it "
                f"serially from {completion.source!r}"
            ),
        )
        released = float(getattr(record, "released_margin", 0.0) or 0.0)
        if released <= 0.0:
            # The handler ran and released nothing — a duplicate or unknown order
            # the LEDGER refused (`nixrisk/reservations.py`'s own refusal path).
            # Reported as REFUSED rather than dispatched: a bare "dispatched"
            # counter over a handler that did nothing is §7.12 guard 2.
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: §3's on_cancel ran for "
                f"{completion.client_order_id!r} and released no margin — the "
                "reservation ledger refused the terminal event; see its own "
                "refusals for which of unknown/duplicate it was",
                released_margin=0.0,
            )
        return DispatchResult(
            Disposition.DISPATCHED,
            completion,
            f"{SITE}: §5:322's loop dispatched a §2A on_cancel to §3's handler "
            f"and {released} of committed margin was released for "
            f"{completion.client_order_id!r}",
            released_margin=released,
        )

    def _dispatch_reject(self, completion: SenderCompletion) -> DispatchResult:
        """ARC 053. §3's reject release. CALLS `outcomes.on_reject`; never reimplements.

        A LITERAL MIRROR of `_dispatch_cancel`, and the duplication is the
        mechanism rather than an oversight — the same argument `outcomes.py`
        makes above its own three `resolve` sites, one layer up. Folding the two
        into `getattr(self._outcomes, EVENT_TO_VERB[event])` would make the
        handler this dispatcher calls `<unresolved>` to any AST census of the
        daemon's dispatch surface, so a gate could no longer read WHICH §3 path
        the daemon books from the source. It would also collapse two
        independently plantable sites into one: PLANT A removes the reject
        dispatch and must not be able to hide behind a working cancel arm.

        The §4 difference from cancel is in the SENTENCE, not the mechanism: a
        cancel means the order was working and stopped; a reject means it never
        worked at all, so nothing was ever at risk against the reservation it
        held. Both release, and §3 is indifferent between them for Σ — which is
        exactly why the reason string has to say which one happened.
        """
        record = self._outcomes.on_reject(
            completion.client_order_id,
            reason=(
                f"{SITE}: the §5:323 sender surfaced a §2A on_reject "
                f"(exec_id {completion.exec_id!r}, done_qty "
                f"{completion.done_qty}) and §5:322's loop dispatched it "
                f"serially from {completion.source!r}"
            ),
        )
        released = float(getattr(record, "released_margin", 0.0) or 0.0)
        if released <= 0.0:
            # The handler ran and released nothing — see `_dispatch_cancel`.
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: §3's on_reject ran for "
                f"{completion.client_order_id!r} and released no margin — the "
                "reservation ledger refused the terminal event; see its own "
                "refusals for which of unknown/duplicate it was",
                released_margin=0.0,
            )
        return DispatchResult(
            Disposition.DISPATCHED,
            completion,
            f"{SITE}: §5:322's loop dispatched a §2A on_reject to §3's handler "
            f"and {released} of committed margin was released for "
            f"{completion.client_order_id!r} — the venue refused the order "
            "outright, so nothing was ever working against that reservation",
            released_margin=released,
        )

    def _dispatch_fill(self, completion: SenderCompletion) -> DispatchResult:
        """ARC 047. §2A:75's fill -> `fills.py`'s cascade. CALLS, never reimplements.

        The whole §4/§3 order — arm the stop, IOC-cancel and release the
        remainder, publish §3's OPEN row under one version stamp — is
        `nixrisk.fills.FillHandler`'s and is not restated here. This method does
        three things and no fourth: it calls the sink, it CONTAINS the cascade's
        refusals, and it re-asserts the safety property at the daemon boundary.

        **CONTAINMENT IS NOT ABSORPTION.** `FillHandler.on_fill` raises rather
        than returning a partial outcome, and every one of its refusals
        (`UnapprovedFill`, `UnstoppedFill`, `UntradableSymbol`, `DuplicateStop`,
        `InvalidRemainder`, the ledger's own) is a real condition an operator
        must see. They are turned into a `REFUSED` result carrying the
        exception's own sentence, never swallowed — a Limiter that died of one
        bad exec report would be a remote kill switch on the process holding
        every synthetic stop (§12.1:604), and one that silently absorbed the
        refusal would be worse.

        **THE §4:214 KEY IS ALREADY CLAIMED WHEN THIS RUNS**, deliberately, and
        the consequence is stated rather than discovered: a fill whose cascade
        raised is NOT retried on a re-delivery. §4:240-241 forbids the resend and
        the alternative — releasing the key on failure — is how one intended
        conversion becomes two on the next duplicate.
        """
        if self._fills is None:
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: {completion.event} is declared wired "
                f"({list(WIRED_EVENTS)}) but this dispatcher was constructed "
                "with no fill sink, so §4's arm/release/publish cascade has "
                f"nothing to run. The reservation for "
                f"{completion.client_order_id!r} is UNCHANGED and no position "
                "was opened",
            )
        before = len(self._fills.outcomes())
        try:
            self._fills.on_fill(
                completion.client_order_id,
                completion.exec_id,
                completion.symbol,
                completion.done_qty,
                completion.price,
                completion.cumulative_qty,
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: §4's fill cascade REFUSED "
                f"{completion.client_order_id}/{completion.exec_id} in "
                f"{completion.symbol!r}: {type(exc).__name__}: {exc}",
            )
        outcomes = self._fills.outcomes()
        if len(outcomes) <= before:
            # §7.12 guard 7. The sink returned normally and produced no outcome:
            # the cascade did nothing and a bare "dispatched" would credit it.
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: the fill sink accepted "
                f"{completion.client_order_id}/{completion.exec_id} and recorded "
                f"NO outcome (outcomes {before} -> {len(outcomes)}) — §4's "
                "cascade did not run, so nothing was armed, released or published",
            )
        return self._read_fill_outcome(completion, outcomes[-1])

    def _read_fill_outcome(
        self, completion: SenderCompletion, outcome: Any
    ) -> DispatchResult:
        """The handler's OWN answer, read back — and the safety re-assertion.

        Every figure below comes off the `FillOutcome` the cascade returned. None
        is recomputed here: §4 converts the stop distance ONCE and §3 publishes
        the row once, and a dispatcher deriving either a second time would be the
        system choosing the same number twice (`positions.py`'s own argument).

        **THE SAFETY RE-ASSERTION.** A fill that converted a reservation to open
        margin without an armed stop is an UNPROTECTED POSITION (§4, §12.1) —
        the hazard §14 resolves toward FLAT and the one I11 guards. `fills.py`
        already makes it unreachable by arming first and raising on refusal; this
        states it a SECOND time, at the boundary the daemon owns, because the
        cost of the redundancy is one comparison and the cost of being wrong is
        a live position nothing protects. A fill reaching here with no stop is
        `REFUSED` and the reason names the unprotected position.
        """
        armed = getattr(outcome, "armed", None)
        write = getattr(outcome, "write", None)
        row = getattr(write, "row", None)
        origin = getattr(write, "origin", None)
        picture = getattr(write, "picture", None)
        level = float(getattr(armed, "level", 0.0) or 0.0)
        trade_id = str(getattr(origin, "trade_id", "") or "")
        if armed is None or not math.isfinite(level) or level <= 0.0:
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: UNPROTECTED POSITION. §4's cascade returned an outcome "
                f"for {completion.client_order_id!r} (trade {trade_id!r}) with NO "
                f"ARMED STOP (armed={armed!r}, level={level!r}). §12.1 makes the "
                "stop synthetic and Limiter-held, so a converted reservation with "
                "no StopState is a live position nothing protects; §14 resolves "
                "that toward FLAT. Refusing to record this as a dispatch",
            )
        if row is None or origin is None or picture is None:
            return DispatchResult(
                Disposition.REFUSED,
                completion,
                f"{SITE}: §4's cascade returned an outcome for "
                f"{completion.client_order_id!r} carrying no published §3 row "
                f"(row={row!r} origin={origin!r} picture={picture!r}) — the stop "
                "was armed and the position was never published, so §7:501's "
                "correlation bucket cannot see the exposure it must price",
            )
        converted = float(getattr(picture, "sum_open_margin", 0.0) or 0.0)
        size = int(getattr(row, "size", 0) or 0)
        return DispatchResult(
            Disposition.DISPATCHED,
            completion,
            f"{SITE}: §5:322's loop dispatched a §2A on_fill to §4's cascade — "
            f"trade {trade_id!r} OPEN at {completion.price} for {size} "
            f"{completion.symbol}, protective stop ARMED at {level} "
            f"({getattr(armed, 'initial_distance_ticks', 0)} ticks, "
            f"{getattr(getattr(armed, 'mode', None), 'value', '?')}), the §3 "
            f"reservation CONVERTED to open margin (Σ open margin {converted}, "
            f"Σ reservations {getattr(outcome, 'sum_reservations', None)}) from "
            f"{completion.source!r}",
            trade_id=trade_id,
            stop_level=level,
            stop_distance_ticks=int(getattr(armed, "initial_distance_ticks", 0) or 0),
            opened_size=size,
            converted_margin=converted,
        )

    def _finish(self, result: DispatchResult) -> DispatchResult:
        """Count it, remember it, return it. The ONE place the ledger moves."""
        if result.disposition == Disposition.DISPATCHED:
            self.ledger.dispatched += 1
            self.ledger.released_margin += result.released_margin
            if result.completion.event == EVENT_FILL:
                self.ledger.fills_dispatched += 1
                self.ledger.opened += 1
                # ASSIGNED, not accumulated: it is the Σ open margin of the ONE
                # picture the last fill published, and a running sum over
                # successive partial fills of one order would double-count the
                # same position's margin on every event.
                self.ledger.converted_margin = result.converted_margin
            elif result.completion.event == EVENT_REJECT:
                # ARC 053. NAMED, not folded into the cancel arm: *the venue
                # stopped a working order* and *the venue never accepted it* are
                # two §4 facts, and a single counter over both would make the
                # reject arm's own driven proof unfalsifiable.
                self.ledger.rejects_dispatched += 1
            else:
                self.ledger.cancels_dispatched += 1
        elif result.disposition == Disposition.DUPLICATE:
            self.ledger.duplicates += 1
        elif result.disposition == Disposition.UNWIRED:
            self.ledger.unwired += 1
        elif result.disposition == Disposition.UNKNOWN:
            self.ledger.unknown += 1
        else:
            self.ledger.refused += 1
        self.history.append(result)
        return result
