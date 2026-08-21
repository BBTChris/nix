"""§5:322's per-tick price poll, §4's trail maintenance, and breach DETECTION.

ARC 055 / I1 ARC C1. ARC 047 ARMED synthetic stops at the confirmed fill and
CHECK-DEBT D3.451 recorded what was missing: nothing with a pid ever called
`StopBook.maintain` or `StopBook.breached`, so an armed stop never trailed and
never fired. MEASURED at `66f9f8b` (ARC 055 / S1) on a real `limiterd`: a stop
armed at `5000.0 - 8 x 0.25 = 4998.0`, `level` INVARIANT across 101 real ticks,
no price directory, no price verb, no price block in the status reply, and
`hasattr(broker, "flatten") is False`. The same numbers driven through the
LIBRARY trailed to `5002.0` and reported the breach. The mechanism worked; the
daemon drove none of it. **An armed stop that is never maintained and never
breached is not protection.**

This module is the missing driver, and it is deliberately the SMALLEST thing
that can be one: a price cache the tick READS, and a poll that maintains, tests
for breach, and ENQUEUES. It fires nothing and it sends nothing.

------------------------------------------------------------------------------
THE SPLIT — WHY DETECTION AND FIRING ARE DIFFERENT OBJECTS (§5, I9)
------------------------------------------------------------------------------
§5:322-324 is explicit: *"Limiter = single-threaded event loop (shared-mem price
poll + ZMQ inbox + sender completions, processed serially) + one low-priority
sender thread (blocking I/O, releases GIL; hung socket contained; hot loop never
blocks)"*. The price poll is ON the hot loop by the spec's own words. The
protective fire is NOT hot-path work: `flatten.ProtectiveFlatten.fire` takes an
arbitration LOCK (`request_close` -> `_arbiter`, ARC 038 FC2) and appends a
§12.10 row through the Plane-1 port, and a lock the hot loop can block on is the
one thing §5:323 exists to prevent.

So `poll()` DETECTS and ENQUEUES — cache reads, arithmetic, and §15's
`O(positions <= 5)/tick` stop evaluation, and nothing else — and `drain()` hands
the enqueued firings to §5:323's sender thread, which is where the fire happens.
I9 (hot-path purity, discharged ARC 050) is a DISCHARGED invariant that this
arc's new code could silently break, so `check_hot_path_purity` gains an arm
that traces `StopWatch.poll` under the same allow-set that judges the §3 gate
pass. Every module root this poll may enter is named there and measured, not
granted.

------------------------------------------------------------------------------
FIRE-ONCE IS A PROPERTY OF THIS OBJECT, NOT A DISCIPLINE OF ITS CALLER
------------------------------------------------------------------------------
`StopBook.breached` is a READ: it returns the breached stops on EVERY tick and
does not drop them ("*Reads, never fires*" — it is `forget` that drops, after the
flatten confirms, which is ARC D's work). Driven naively that means a breach at
tick N re-fires at N+1, N+2, ... for as long as price stays past the level — one
protective flatten per tick against one position. A double-flatten is a real
defect: §4's arbiter drops the redundant close, but the venue call in
`ProtectiveFlatten.fire` is issued BEFORE the arbiter sees the target for the
uncertainty path, and each extra firing is an extra `flatten` at the broker.

So this object holds `_in_flight`: the `client_order_id`s it has already
enqueued a protective flatten for. A stop in that set is SKIPPED by every later
poll. The mark is taken in the same pass that enqueues, on the single loop
thread, so there is no window between deciding to fire and recording that the
fire was decided. It is released by `forget` — the same verb that drops the stop
— and by nothing else, so a "released" state can never outlive the stop it
belonged to. C1 fires and sends; the closing fill coming back and the position
reconciling is ARC D, and until D lands a fired position stays marked, which is
the fail-CLOSED direction: at worst one protective flatten is not re-sent.

------------------------------------------------------------------------------
THE PRICE RING, AND WHAT IT IS HONESTLY NOT
------------------------------------------------------------------------------
§5:322 names a *shared-mem price poll*. There is NO capture feed, no shared
memory segment and no vendor integration in this tree — `PriceRing` is the
in-process ring the daemon holds, written by the serial ingress and READ by the
tick. That is the same relationship a shared-memory ring has with its consumer
(the tick reads the head slot; it never computes it), and it is what makes the
poll hot-path-pure: `head()` is one dict lookup.

What it is NOT is a market data feed. When capture exists, the writer changes
and this reader does not. **CHECK-DEBT D3.473** records that, so nothing here
can be read as a claim that the Limiter is receiving real prices.

`RING_SYMBOL_CAP` bounds the ring at §7's symbol scope (*"up to 5 top-liquid
(ES, NQ, CL, GC, ZN)"*) rather than being config: §15's `O(positions <= 5)/tick`
is the bound the hot path is judged against, and a per-tick loop whose length a
config file could raise is not bounded by anything a gate can read. It is a
`Final` constant for that reason and is NOT a §12A tunable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from nixrisk.seam import Side, StopBookPort

#: §7's symbol scope — *"up to 5 top-liquid (ES, NQ, CL, GC, ZN)"* — and §15's
#: `O(positions <= 5)/tick`. A hard ceiling, NOT a §12A tunable: see the module
#: docstring's last paragraph on why a config-raisable per-tick loop bound is not
#: a bound at all.
RING_SYMBOL_CAP: Final[int] = 5


class PriceRingFull(RuntimeError):
    """A price for a SIXTH symbol. §7's scope is five; refused, never evicted.

    Loud rather than silently evicting the oldest symbol, because eviction would
    silently stop maintaining the stops on the evicted symbol — the exact D3.451
    shape this module exists to close, reintroduced one layer down and invisible.
    """


@dataclass(frozen=True)
class PriceTick:
    """One price the ring holds for one symbol. The tick READS these."""

    symbol: str
    price: float
    seq: int


@dataclass(frozen=True)
class BreachFiring:
    """One detected breach, enqueued for §5:323's sender thread to FIRE.

    A DECLARATION OF DETECTION, never a claim that anything was sent — the same
    distinction `flatten.FlattenAction` draws between "we sent a flatten" and
    "the position is confirmed flat", one step earlier in the chain. Carries no
    timestamp deliberately: a clock read on the hot path would put `time` on a
    path whose whole claim is cache-reads-and-arithmetic, and the sender stamps
    the instant it actually fires, which is the instant that matters.
    """

    client_order_id: str
    symbol: str
    side: Side
    level: float
    price: float
    tick: int


class PriceRing:
    """§5:322's price ring, in-process. Written by ingress, READ by the tick.

    `head` is ONE dict lookup and is the only verb the hot path calls. `publish`
    is the writer's verb and runs on the serial ingress, never inside `poll`.
    """

    def __init__(self) -> None:
        #: symbol -> the newest tick for it. The whole state.
        self._head: dict[str, PriceTick] = {}
        #: Monotonic publication counter, so a consumer can tell a re-read of the
        #: same tick from a genuinely new one without comparing floats.
        self._seq = 0

    def publish(self, symbol: str, price: float) -> PriceTick:
        """Record the newest price for one symbol. NOT the hot path."""
        if symbol not in self._head and len(self._head) >= RING_SYMBOL_CAP:
            raise PriceRingFull(
                f"{symbol!r}: the price ring already holds {RING_SYMBOL_CAP} "
                f"symbols ({sorted(self._head)}) and §7 scopes this system to "
                f"{RING_SYMBOL_CAP} top-liquid instruments. Refusing rather than "
                "evicting one — an evicted symbol's stops stop being maintained, "
                "which is D3.451 reintroduced silently"
            )
        self._seq += 1
        tick = PriceTick(symbol=symbol, price=float(price), seq=self._seq)
        self._head[symbol] = tick
        return tick

    def head(self, symbol: str) -> PriceTick | None:
        """The newest price for one symbol, or None. ONE dict read — hot path."""
        return self._head.get(symbol)

    def symbols(self) -> tuple[str, ...]:
        """The symbols the ring holds, bounded by `RING_SYMBOL_CAP`. Hot path."""
        return tuple(self._head)

    def published(self) -> int:
        """How many prices have ever been published. Evidence, not the hot path."""
        return self._seq


class StopWatch:  # pylint: disable=too-many-instance-attributes
    # R0902: eight, and four of them are the COUNTERS an out-of-process reader
    # judges this object by — polls, maintained, breaches, suppressed. They are
    # the difference between *nothing breached* and *nothing could breach*, which
    # is D3.451 itself. Folding them behind a sub-object would put the measured
    # facts one indirection away from the poll that produced them.
    """§5:322's price poll driving §4's trail and breach. DETECTS; never fires.

    Holds no broker, no Plane-1 sink and no clock — structurally, so "this object
    cannot send" is a property of the type rather than a rule its caller is
    trusted to keep. That is `stops.StopBook`'s own argument for holding no
    logging collaborator (§12.10, A4), applied one layer out.
    """

    def __init__(self, ring: PriceRing, stops: StopBookPort) -> None:
        self._ring = ring
        #: The §4 book, typed by the FROZEN PORT and not by `StopBook` — the same
        #: choice `flatten.py` makes for its collaborators. This driver calls
        #: `maintain` and `breached` and nothing else, and declaring the port
        #: says so in a form a type checker enforces.
        self._stops = stops
        #: client_order_id -> the firing already enqueued for it. THE FIRE-ONCE
        #: MARK; see the module docstring.
        self._in_flight: dict[str, BreachFiring] = {}
        #: Firings detected and not yet drained to §5:323's sender thread.
        self._pending: list[BreachFiring] = []
        #: Evidence counters, read out of the process by the runtime record.
        self.polls = 0
        self.maintained = 0
        self.breaches = 0
        self.suppressed = 0

    # -- the hot path -------------------------------------------------------

    def poll(self, tick: int) -> int:
        """ONE tick: maintain every armed stop, detect breaches, enqueue. PURE.

        Returns the number of firings enqueued by THIS poll. Cache reads,
        arithmetic and §15's `O(positions <= 5)/tick` stop evaluation — no I/O,
        no lock, no clock, no allocation beyond the frozen records it produces.
        `check_hot_path_purity` traces this method under its allow-set and a
        module root outside it is CANNOT_MEASURE, never a PASS.
        """
        self.polls += 1
        fired = 0
        for symbol in self._ring.symbols():
            head = self._ring.head(symbol)
            if head is None:  # pragma: no cover - symbols() is head's own keys
                continue
            price = head.price
            # §4:190-196's ratchet. MONOTONIC by `StopBook`'s construction — the
            # high-water mark is monotone in the strategy's favour, so the trail
            # level it implies never gives ground back. This driver never
            # computes a level itself, deliberately: a second piece of trailing
            # arithmetic here could disagree with §4's and a stop would sit at
            # two prices at once.
            self.maintained += len(self._stops.maintain(symbol, price))
            for state in self._stops.breached(symbol, price):
                if state.client_order_id in self._in_flight:
                    self.suppressed += 1
                    continue
                firing = BreachFiring(
                    client_order_id=state.client_order_id,
                    symbol=state.symbol,
                    side=state.side,
                    level=state.level,
                    price=price,
                    tick=tick,
                )
                # MARKED IN THE SAME PASS THAT ENQUEUES. One loop thread, no
                # window: see the module docstring on fire-once.
                self._in_flight[state.client_order_id] = firing
                self._pending.append(firing)
                self.breaches += 1
                fired += 1
        return fired

    # -- the boundary -------------------------------------------------------

    def drain(self) -> tuple[BreachFiring, ...]:
        """Take the detected firings for the sender. A list swap; never blocks."""
        if not self._pending:
            return ()
        out = tuple(self._pending)
        self._pending = []
        return out

    def forget(self, client_order_id: str) -> BreachFiring | None:
        """Release the fire-once mark. Returns what was released, or None.

        The ONLY release. Called where `StopBook.forget` is called — when the
        position closes — so the mark can never outlive the stop it belongs to.
        Silent on an unknown id, unlike `StopBook.forget`, because this book is
        SPARSE by construction: it holds only the orders that actually breached,
        so a close for a never-breached order is the ordinary case and not a
        keying defect.
        """
        return self._in_flight.pop(client_order_id, None)

    # -- readable state -----------------------------------------------------

    def in_flight(self) -> tuple[str, ...]:
        """The orders a protective flatten has been enqueued for, sorted."""
        return tuple(sorted(self._in_flight))

    def pending(self) -> tuple[BreachFiring, ...]:
        """Firings detected and not yet drained. Evidence, never the hot path."""
        return tuple(self._pending)
