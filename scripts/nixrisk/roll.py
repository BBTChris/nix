"""§7.5's contract roll — the ATOMIC front-month identity switch.

ARC 033 / Stage 1 / sub-agent B. Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md` unless another document is named on the
line.

§7.5:520-522, verbatim: *"**Front-month = volume leader** per the liquidity
principle; roll schedule sourced by the calendar poller; all symbol-keyed
subsystems (capture, backfill, margin cache, calendar, Renko state, positions)
switch identity **atomically at a defined roll instant**."*

===========================================================================
WHAT "ATOMICALLY" HAS TO MEAN HERE, AND WHY IT IS THE §12.7 TEAR ONE LEVEL UP
===========================================================================
§12.7 forbids a consumer observing a balance and a position table bearing
different version stamps — a torn READ of one snapshot. §7.5 forbids the same
defect over a different subject: two symbol-keyed subsystems answering the same
instant with DIFFERENT contracts. Capture writing `ESZ26` bricks while the
position table is still keyed `ESU26` is a **torn identity**, and §7.5:525-526
names its consequence outright — phantom bricks stitched across contracts.

The mechanism is `nixrisk/picture.py`'s, transposed: **one immutable value,
replaced by ONE store, read by ONE load.** `IdentityEpoch` is frozen and holds
every subsystem's answer for every symbol; `RollIdentityBook.advance` builds a
whole new epoch and rebinds a single attribute; every reader begins by taking
ONE reference to it and answers every subsequent question off that reference.
There is no interleaving that can produce a mixed answer, because between the
reader's single load and its last question nothing it reads can change.

**A per-subsystem map updated in a loop is the defect**, and it is the shape a
reasonable implementation reaches for. `check_contract_roll` plants exactly that
— `_TornBook` — and requires it to TEAR under the same race harness this design
survives. An atomicity claim with no torn counterpart is guaranteed by
construction rather than measured (ARC 032's ruling on the published row).

===========================================================================
THE SCHEDULE IS **PROVISIONAL**. CHECK-DEBT D3.170, AND IT IS NOT DECORATION
===========================================================================
§7.5:520 sources the live schedule from the calendar poller and defines front
month as the **volume leader** — an OBSERVATION of the market. The vendored
artifact this module reads (`scripts/crucible/calendar_data/nix_roll_schedule.
csv`) is **rule-derived**: every row is stamped `high_risk=1` and
`crucible.calendar.Roll`'s own docstring says so. No offline artifact can
observe volume migration.

So the provenance is CARRIED, not dropped: `IdentityEpoch.provisional` names
every symbol whose identity came from a `high_risk` row, and
`RollIdentityBook.provisional_symbols()` is how a consumer asks. A consumer that
wants an exchange-observed roll can see that it does not have one. The gate's
own can-fail control is a plant that DROPS the flag — provenance laundering —
and it must redden.

Nothing here promotes a provisional row to observed, and nothing here treats
`high_risk` as a reason to refuse the identity: refusing would leave every
symbol-keyed subsystem with NO front month, which is worse than a flagged one.
The honest position is *this is the best available identity and here is its
provenance*, and the flag is where that sentence lives.

===========================================================================
THE ROLL-DAY BLACKOUT IS **DATA**, AND THIS MODULE DOES NOT MINT IT
===========================================================================
§7.5:523: *"**Roll-day entry blackout** for the affected symbol (a window —
data, not code)."* §6.5 makes the same rule general. This module therefore
produces the **INSTANT** (`RollIdentityBook.next_roll_instant`) and constructs
no `Window`, emits no blackout, and evaluates no gate. The window evaluator is
a separate owner in this stage; giving it an instant is data, and giving it a
rule would be the branch §6.5 forbids, arriving from a second author.

===========================================================================
`debug.md` §7.12 — THE STANDING QUESTION FOR THIS MODULE
===========================================================================
*What would have to be true for a roll gate to pass while measuring nothing?*

1. **Identity never actually shifts** — the drive samples one side of the roll,
   so `snapshot()` is trivially self-consistent. GUARDED IN THE GATE and the
   suite: both resolve an epoch strictly BEFORE the roll instant and strictly
   AFTER it and assert the two contracts DIFFER before any atomicity assertion
   runs. An arm that cannot show the identity moved measures nothing.
2. **The race never races** — one thread, so no interleaving is possible.
   GUARDED: the harness runs a writer thread flipping the epoch across the roll
   instant against N reader threads, and asserts the readers observed BOTH
   contracts (so the window really was crossed under contention) before
   asserting no reader observed a MIXED snapshot.
3. **The plant does not tear**, so "no tear observed" is uninformative. GUARDED:
   `_TornBook` is driven through the same harness and the gate FAILS if it does
   NOT tear — a falsifier that stopped falsifying is reported as a broken
   instrument, never as a pass.
4. **The subsystem set is empty**, so a snapshot over zero subsystems is
   self-consistent for free. GUARDED: `SYMBOL_KEYED_SUBSYSTEMS` is §7.5:521's
   own list, the book refuses an empty set at construction, and the gate asserts
   the count it measured.
5. **Provisional is always false**, so the flag looks clean because nothing sets
   it. GUARDED: the gate asserts the vendored schedule really does carry
   `high_risk=1` rows and that the epoch NAMES the symbol as provisional — the
   positive observation, not the absence of a complaint.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from nixrisk.calendar_seam import CacheState, ContractIdentity, RollScheduleReadPort

__all__ = [
    "SYMBOL_KEYED_SUBSYSTEMS",
    "IdentityEpoch",
    "NoFrontContract",
    "RollError",
    "RollIdentityBook",
    "TornIdentity",
    "VendoredRollSchedule",
]

#: §7.5:521's own list, transcribed and closed. These are the subsystems that
#: key on a symbol and therefore have to move together; a seventh is a finding
#: about the spec to report, not a member added here (the rule ARC 028 obeyed
#: for `TerminalPath` and the architect then ratified as `SPEC-A7`).
SYMBOL_KEYED_SUBSYSTEMS: tuple[str, ...] = (
    "capture",
    "backfill",
    "margin_cache",
    "calendar",
    "renko_state",
    "positions",
)


class RollError(RuntimeError):
    """Base for every refusal this module raises. Never caught internally."""


class NoFrontContract(RollError):
    """No front-month identity for a managed symbol at the resolved instant.

    LOUD rather than a nearest-neighbour guess (§7.5:525-526): the roll instant
    is the defined boundary for Renko/backfill continuity, and a guessed identity
    is exactly the phantom stitch across contracts §7.5 forbids. The identical
    reasoning `crucible.calendar.front_contract` records for returning `None`.
    """


class TornIdentity(RollError):
    """A snapshot in which two symbol-keyed subsystems disagree on one contract.

    Raised by `IdentityEpoch.__post_init__` — so an epoch that could be observed
    torn cannot be constructed. This is the assertion that makes the atomicity
    claim structural: a book that builds identities per subsystem rather than
    once per symbol fails HERE, at construction, rather than being caught later
    by a reader that happened to look.
    """


# ---------------------------------------------------------------------------
# The epoch — ONE immutable value, and the unit of atomicity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityEpoch:
    """Every symbol-keyed subsystem's front-month identity, as ONE value.

    Frozen, and `identities` is a read-only mapping view, for the reason
    `nixalloc/seam.py` gives its value types and `nixrisk/seam.py` gives the
    financial picture: a consumer holding a mutable identity map could edit a
    live front month in place, and every later reader in that process would key
    on the edit — a change to canonical routing state that never left the
    process and appears in no event log.

    **THE ATOMICITY IS THE SHAPE, NOT A DISCIPLINE.** There is exactly ONE
    identity per SYMBOL, and every subsystem answers off it. A per-subsystem
    identity map cannot be represented by this type at all, which is why the
    torn case is a construction-time refusal (`TornIdentity`) rather than a
    runtime check somebody has to remember to call.

    `version` is monotonic per book and is the §12.7 stamp transposed: two
    answers bearing different versions came from different epochs, and a reader
    that took one reference cannot have straddled them.
    """

    #: The UTC instant this epoch was RESOLVED for — not the instant it was
    #: built. The roll boundary is a property of the schedule, not of when a
    #: process happened to advance.
    resolved_for: datetime
    version: int
    #: symbol -> the ONE front-month identity every subsystem uses.
    identities: Mapping[str, ContractIdentity]
    #: The symbols whose identity came from a rule-derived (`high_risk`) row.
    #: CHECK-DEBT D3.170 — see the module docstring.
    provisional: frozenset[str]
    #: The subsystems this epoch answers for. §7.5:521's list by default; carried
    #: on the value so a snapshot states its own breadth rather than a reader
    #: assuming it.
    subsystems: tuple[str, ...] = SYMBOL_KEYED_SUBSYSTEMS

    def __post_init__(self) -> None:
        if not self.subsystems:
            raise TornIdentity(
                "an epoch over ZERO symbol-keyed subsystems is self-consistent "
                "for free and proves nothing — §7.5:521 names six"
            )
        for symbol, identity in self.identities.items():
            if identity.symbol != symbol:
                raise TornIdentity(
                    f"epoch key {symbol!r} holds an identity for "
                    f"{identity.symbol!r} — the map and the value disagree about "
                    "which symbol this is, which is a torn identity before any "
                    "reader has looked"
                )

    def contract_for(self, subsystem: str, symbol: str) -> str:
        """The dated contract `subsystem` must key `symbol` on, in this epoch.

        Every subsystem gets the SAME answer by construction — there is one
        identity per symbol. The `subsystem` argument exists so a caller's site
        names which subsystem is asking (the audit trail §7.5's seam needs), and
        so a subsystem outside §7.5:521's list is REFUSED rather than silently
        answered: an unlisted subsystem keying on a contract is one nobody
        arranged to switch.
        """
        if subsystem not in self.subsystems:
            raise NoFrontContract(
                f"{subsystem!r} is not one of §7.5:521's symbol-keyed subsystems "
                f"{self.subsystems} — answering it would hand a front month to a "
                "subsystem no roll was arranged for"
            )
        identity = self.identities.get(symbol)
        if identity is None:
            raise NoFrontContract(
                f"no front-month identity for {symbol!r} in epoch v{self.version} "
                f"(resolved for {self.resolved_for.isoformat()}) — §7.5 makes the "
                "roll instant a defined boundary and a guessed identity is the "
                "phantom stitch it forbids"
            )
        return identity.contract

    def snapshot(self) -> Mapping[tuple[str, str], str]:
        """Every `(subsystem, symbol) -> contract` pair, off THIS one value.

        The race harness's read verb. It performs no attribute load on any book:
        by the time a caller holds an `IdentityEpoch` the atomic read already
        happened, which is the whole design. A `snapshot` that reached back into
        a book would reintroduce the interleaving the epoch exists to remove.
        """
        return MappingProxyType(
            {
                (subsystem, symbol): identity.contract
                for subsystem in self.subsystems
                for symbol, identity in self.identities.items()
            }
        )


# ---------------------------------------------------------------------------
# The book — the ONE store / ONE load
# ---------------------------------------------------------------------------


class RollIdentityBook:
    """§7.5's front-month identity, switched atomically at the roll instant.

    Owned by whatever process keys on a symbol; the switch is `advance(at)` and
    the read is `epoch()`. Both are SYNCHRONOUS, and the reason is
    `nixrisk/calendar_seam.py`'s for `RollScheduleReadPort.front_contract`: an
    awaitable identity lookup admits two subsystems resolving the same instant
    on opposite sides of the roll across a suspension, which is the stitched
    seam §7.5:525-526 forbids arriving through the clock instead of the data.
    """

    def __init__(
        self,
        *,
        schedule: RollScheduleReadPort,
        symbols: Sequence[str],
        subsystems: Sequence[str] = SYMBOL_KEYED_SUBSYSTEMS,
        provisional_symbols: Iterable[str] = (),
    ) -> None:
        if not symbols:
            raise RollError(
                "a roll book over ZERO symbols answers every atomicity question "
                "vacuously; §7.5 is about the symbols under management"
            )
        if not subsystems:
            raise RollError(
                "a roll book over ZERO subsystems cannot tear and therefore "
                "cannot demonstrate that it does not — §7.5:521 names six"
            )
        self._schedule = schedule
        self._symbols = tuple(symbols)
        self._subsystems = tuple(subsystems)
        #: Symbols the SOURCE declared rule-derived. Injected rather than sniffed
        #: off the artifact here: `RollScheduleReadPort` is the frozen read
        #: boundary and carries no provenance field, so the adapter that reads
        #: the artifact is the one place that knows, and it tells the book.
        #: CHECK-DEBT D3.170.
        self._provisional_source = frozenset(provisional_symbols)
        self._version = 0
        #: THE SINGLE MUTABLE ATTRIBUTE IN THIS CLASS. One store in `advance`,
        #: one load in `epoch`. Everything else is derived from the value it
        #: holds, which is what makes the switch atomic.
        self._epoch: IdentityEpoch | None = None

    def advance(self, at: datetime) -> IdentityEpoch:
        """Resolve every symbol at `at` and install the result in ONE store.

        The whole epoch is BUILT first and only then bound. A partially-built
        epoch is never reachable by a reader, because the attribute still points
        at the previous complete one until the last statement. That ordering is
        the atomic switch; reversing it — bind, then fill — is `_TornBook`.
        """
        identities: dict[str, ContractIdentity] = {}
        provisional: set[str] = set()
        for symbol in self._symbols:
            identity = self._schedule.front_contract(symbol, at)
            if identity is None:
                raise NoFrontContract(
                    f"{symbol}: the roll schedule covers no front month at "
                    f"{at.isoformat()} — §7.5 makes the roll instant a defined "
                    "boundary, so an uncovered instant is refused, never guessed"
                )
            identities[symbol] = identity
            if symbol in self._provisional_source:
                provisional.add(symbol)
        epoch = IdentityEpoch(
            resolved_for=at,
            version=self._version + 1,
            identities=MappingProxyType(identities),
            provisional=frozenset(provisional),
            subsystems=self._subsystems,
        )
        self._version += 1
        self._epoch = epoch  # THE ONE STORE.
        return epoch

    def epoch(self) -> IdentityEpoch:
        """The current epoch, by ONE load. Raises before the first `advance`.

        Raising rather than resolving lazily is deliberate: a lazy read would
        make the FIRST reader's instant the epoch's instant, so which subsystem
        happened to ask first would decide which side of the roll everyone
        else lands on.
        """
        epoch = self._epoch  # THE ONE LOAD.
        if epoch is None:
            raise NoFrontContract(
                "the roll book has no epoch — `advance(at)` has not run. A lazy "
                "first read would let the first caller's instant decide the "
                "front month for every other subsystem"
            )
        return epoch

    def contract_for(self, subsystem: str, symbol: str) -> str:
        """One subsystem's contract for one symbol, off ONE epoch load."""
        return self.epoch().contract_for(subsystem, symbol)

    def snapshot(self) -> Mapping[tuple[str, str], str]:
        """Every subsystem's contract for every symbol, off ONE epoch load.

        The verb the race harness hammers. One load, then pure derivation — so a
        writer flipping the epoch mid-snapshot cannot be observed half-applied.
        """
        return self.epoch().snapshot()

    def provisional_symbols(self) -> frozenset[str]:
        """Symbols whose identity is rule-derived, not exchange-observed (D3.170).

        Read off the CURRENT epoch, not off the constructor argument, so a
        consumer is told about the provenance of the identity it actually holds.
        """
        return self.epoch().provisional

    def next_roll_instant(self, symbol: str, at: datetime) -> datetime | None:
        """§7.5:523's window input, as an INSTANT. This module mints no window.

        Pass-through to the schedule, and deliberately nothing more: the roll-day
        entry blackout is DATA (§7.5:523, §6.5), so the instant is what this
        module owes a window generator. Constructing a `Window` here would put a
        blackout rule in a second place.
        """
        return self._schedule.next_roll(symbol, at)


# ---------------------------------------------------------------------------
# The adapter — the ONE place the artifact's provenance is read (D3.170)
# ---------------------------------------------------------------------------


class VendoredRollSchedule:
    """`RollScheduleReadPort` over the vendored artifact, CARRYING provenance.

    `nixrisk/calendar_seam.py`'s `RollScheduleReadPort` returns a
    `ContractIdentity`, which has four fields and none of them is provenance —
    the seam is frozen and this module does not widen it. So the provenance is
    carried ALONGSIDE, by this adapter, which is the only object in the tree
    that sees both `crucible.calendar.Roll.high_risk` and the identity built
    from it.

    **`provisional` IS THE POINT, not a nicety.** §7.5:520 defines front month
    as the volume leader — an observation of the market — and every row in
    `nix_roll_schedule.csv` is rule-derived and stamped `high_risk=1`
    (CHECK-DEBT D3.170). A consumer keying capture, backfill and the position
    table on a rule-derived roll date must be able to learn that it is doing so.
    `check_contract_roll` plants an adapter that DROPS the flag and requires the
    gate to redden, because a silently-laundered provenance is indistinguishable
    from an observed one.

    Reads `crucible.calendar` lazily, inside `__init__`, so importing
    `nixrisk.roll` does not pull the vendored CSV loader into every process that
    only needs the epoch types.
    """

    def __init__(self) -> None:
        # pylint: disable=import-outside-toplevel
        from crucible import calendar as _calendar

        self._calendar = _calendar

    def front_contract(self, symbol: str, at: datetime) -> ContractIdentity | None:
        """§7.5's identity at `at`, or `None` off-span. Never a guess."""
        roll = self._calendar.front_contract(symbol, at)
        if roll is None:
            return None
        return ContractIdentity(
            symbol=roll.symbol,
            contract=roll.contract,
            front_from=roll.front_from,
            roll_at=roll.roll_at,
        )

    def next_roll(self, symbol: str, at: datetime) -> datetime | None:
        """The next roll instant at or after `at` (UTC), feeding §7.5's window."""
        return self._calendar.next_roll(symbol, at)

    def state(self) -> CacheState:
        """The vendored artifact is a build-time file, not a polled cache.

        `FRESH` once it loads: §6.4's staleness is about a POLLER falling behind,
        and this source has no poller. Saying `STALE` would make a §6.4 halt rule
        fire forever; saying `EMPTY` would be false the moment a row is readable.
        The honest weakness of this source is its PROVENANCE, and that is carried
        by `provisional_symbols`, not smuggled into a freshness verdict.
        """
        return CacheState.FRESH

    def provisional_symbols(self, at: datetime) -> frozenset[str]:
        """Symbols whose identity at `at` came from a `high_risk` row (D3.170).

        A POSITIVE observation: it reads `Roll.high_risk` off the artifact for
        the identity actually in force, rather than assuming the whole file is
        provisional. If a future regeneration corroborates a symbol's roll dates
        against the exchange, that symbol drops out of this set on its own.
        """
        provisional: set[str] = set()
        for symbol in self._calendar.known_symbols():
            roll = self._calendar.front_contract(symbol, at)
            if roll is not None and roll.high_risk:
                provisional.add(symbol)
        return frozenset(provisional)
