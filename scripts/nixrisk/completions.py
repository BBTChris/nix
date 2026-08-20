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

**ONLY THE CANCEL PATH IS WIRED.** `on_fill`, `on_reject`, `on_ack`,
`on_position`, `on_balance`, `on_margin` and `on_session` (§2A:74-84) all parse
and all reach `dispatch`, and every one of them returns `UNWIRED` naming itself.
That is the deliberate shape of a spike: an unwired event must be READABLE as
unwired rather than absorbed as handled, because "the daemon processed it" and
"the daemon dropped it" are the two readings ARC 046 exists to keep apart. A
silent drop here would let a future arc believe the fill path works.

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
"""

from __future__ import annotations

import json
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

#: The ONE event ARC 046 wired. Spelled as a tuple so the next arc adds a
#: member rather than editing a condition, and so a census can read which
#: paths this build actually serves without executing it.
WIRED_EVENTS: Final[tuple[str, ...]] = (EVENT_CANCEL,)

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


@dataclass(frozen=True)
class SenderCompletion:
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


@dataclass(frozen=True)
class DispatchResult:
    """One dispatch decision, with the handler's own answer folded in."""

    disposition: str
    completion: SenderCompletion
    reason: str
    released_margin: float = 0.0
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
    return SenderCompletion(
        event=event,
        client_order_id=client_order_id,
        exec_id=exec_id,
        done_qty=done_qty,
        source=source,
        raw=raw,
    )


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

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block, for `limiter.runtime.json`."""
        return {
            "consumed": self.consumed,
            "seen": self.seen,
            "dispatched": self.dispatched,
            "duplicates": self.duplicates,
            "unwired": self.unwired,
            "unknown": self.unknown,
            "refused": self.refused,
            "malformed": self.malformed,
            "released_margin": self.released_margin,
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
        dedup: ExecReportDedup | None = None,
    ) -> None:
        self._outcomes = outcomes
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

    def _finish(self, result: DispatchResult) -> DispatchResult:
        """Count it, remember it, return it. The ONE place the ledger moves."""
        if result.disposition == Disposition.DISPATCHED:
            self.ledger.dispatched += 1
            self.ledger.released_margin += result.released_margin
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
