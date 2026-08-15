#!/usr/bin/env python3
"""A published `stop_distance` is the STOP BOOK's figure for that same trade.

ONE gate, ONE property (`nix_check_contract.md` §5.5). The property is not *the
field is populated* — that is the trap this gate exists to avoid — it is:

    for every trade in §3's published position table, the row's `stop_distance`
    EQUALS `StopState.initial_distance_ticks` for the order that opened that
    trade, and the gate REDDENS on a value that is present, positive, plausible
    and WRONG.

Discharges the gate half of CHECK-DEBT **D3.150**, whose whole finding is that
nothing in production ever CHOSE a value for this field: ARC 032 proved it
TRAVELS (codec, wire, mirror, process boundary) and proved nothing about it
being RIGHT. §7:501 prices correlation-bucket exposure from it, so a wrong
number is consumed by a safety cap that cannot question it.

## THE TRAP, NAMED FIRST BECAUSE IT IS THE POINT

**A gate that only checks the field is non-null PASSES ON A WRONG VALUE.** Every
comparison here is PER TRADE and against a figure this gate holds independently
of the object that produced the row:

* the reference is this gate's own `stop_ticks` LITERAL, written beside the
  order it belongs to;
* it is cross-checked against a SECOND, separately-constructed `StopBook` armed
  from the same orders and NEVER handed to the writer, so a literal that has
  gone stale against the shipped conversion is a refusal rather than a false
  red;
* and the two must agree with each other BEFORE either is compared to the
  subject.

`scripts/tests/test_check_origin_write.py` plants a writer that publishes a
present, positive, plausible and wrong distance — the FIRST stop in the book
rather than this trade's, which is a wrong JOIN and produces a real distance
belonging to another trade — and requires this gate to redden naming the trade
and both numbers.

## THE SIX ARMS, and why no one of them carries the property

* **ARM ORIGIN.** The published table against the independent reference, per
  trade, over a population whose distances are pairwise DISTINCT.
* **ARM JOIN.** The whole drive again under a NON-IDENTITY trade-id mint. Under
  the default binding a trade IS its entry order, so `trade_id ==
  client_order_id` and a writer that hard-coded the identity publishes
  byte-identical rows: no drive over the default can see it. This one can, and
  it also proves the join is the INJECTED surface rather than an equality.
* **ARM UNSTOPPED.** A confirmed fill whose trade has no armed stop must publish
  NO ROW and refuse loudly. A defaulted or zero distance here is D3.136's
  fail-open under a new spelling — §7:501 prices the position at zero risk, the
  bucket reads emptier, and an emptier bucket ADMITS MORE.
* **ARM LEDGER.** Two partial fills of one order publish ONE row carrying the
  CUMULATIVE size, and a re-delivered execution does not move the table. §4's
  ledger owns that arithmetic (doctrine C.9) and this arm is what shows the
  writer asks it rather than re-deriving position.
* **ARM SNAPSHOT.** The row rides `FinancialPictureBook.commit()` — §3's one
  snapshot, §9's sole writer — advancing the version exactly once per published
  fill, with balance travelling on the same object. A second table would satisfy
  ARM ORIGIN perfectly.
* **ARM STRUCTURE.** The two things no drive can see. (a) The distance must
  trace to `initial_distance_ticks`, and the module must never read
  `stop_ticks`: a writer that published the ORDER's distance instead of the STOP
  BOOK's produces identical output on every drive, because `arm` records one
  from the other — right up until a stop is amended. (b) `trade_id` must come
  from the origin record, not from the report's order id.

## DOCTRINE C.9 — why this is not a second instrument

`scripts/tests/test_positions.py` drives the same module. Three things separate
them, weakest first:

1. `check_artifact_gate_coverage` counts `SUBJECTS` and cannot see a test
   module. That is the weakest reason and it is listed first so it cannot be
   mistaken for the load-bearing one.
2. **Different tree.** The suite drives the module resolved out of THIS
   repository at development time; this gate imports it out of `ctx.nix_home`
   and ASSERTS the provenance (D3.124), which is a question `verify.py` can ask
   on a box whose runtime venv has no pytest.
3. **Different property.** ARM STRUCTURE is invisible to any drive, and the
   independence construction (a reference stop book the writer never touches) is
   this gate's, not the suite's.

## debug.md §7.12 — THE STANDING QUESTION, answered where the gate is built

*What would have to be true for this gate to PASS while measuring nothing?*

1. **The subject could be unimportable, or resolve to another tree.**
   `checks/_preamble.py` appends the REAL `scripts/` to `sys.path` and never
   removes it, so an empty `nix_home` falls through to the live repository and
   the gate reports on a tree it never read (D3.124). *Closed twice:* an import
   failure is CANNOT_MEASURE naming the exception (§17 — never a PASS), and
   every loaded module's `__file__` must lie under the tree under judgement,
   with the SUBJECT pinned to the exact file ARM STRUCTURE parses.
2. **The population could be empty or a single trade.** One trade cannot expose
   a wrong join at all, and an empty table would let a writer that publishes
   nothing pass. *Closed:* `MIN_TRADES`, `MIN_SYMBOLS`, `MIN_PARTIAL_ORDERS`,
   `MIN_UNSTOPPED_DRIVES`, `MIN_DUPLICATE_DELIVERIES` and
   `MIN_NON_IDENTITY_TRADES` are FLOORS, every one strictly below what today's
   population carries (doctrine C.4 — a threshold equal to today's count reddens
   on the next edit and discriminates nothing before then), and the verdict is
   CANNOT_MEASURE below any of them.
3. **Every trade could coincidentally share ONE stop distance**, and a wrong
   join would publish the right number. *Closed:* the distances must be pairwise
   DISTINCT and non-zero before any comparison is trusted, they are required to
   be disjoint from the quantities (so a writer publishing `size` where the
   distance belongs cannot agree by luck), and the guard itself is driven by
   `test_check_origin_write.py` with a degenerate population.
4. **The stop book could be consulted THROUGH THE OBJECT THAT PRODUCED THE
   ROW**, making the comparison a figure against itself. *Closed:* the reference
   is this gate's own literal, cross-checked against a SECOND stop book armed
   here and never handed to the writer; the writer's own book is never read by
   the comparison. A disagreement between the literal and the reference book is
   CANNOT_MEASURE — the instrument is broken, and that is not a statement about
   the subject.
5. **A refusal could be reported as agreement.** A writer that raised on every
   fill would publish an empty table, which trivially contains no wrong row.
   *Closed:* ARM ORIGIN requires exactly one published row PER TRADE and counts
   them, and the floors are read off what the drive ACTUALLY published.
6. **The gate could compute its expectation from the subject.** *Closed:* no
   expected figure is ever read from a `PositionRow`; every one is a literal in
   this file or is derived from the literals by arithmetic written here.
7. **A raising subject could be reported as a broken instrument.** *Closed:*
   every arm is run through `_guarded`, which turns an unexpected exception into
   a FINDING about the subject naming the exception, because this gate's drive is
   a legitimate one the module is required to absorb (§18's shared-namespace
   rule).

## WHAT THIS GATE CANNOT PROVE, stated rather than implied

It drives the WRITER. Nothing here proves the Limiter's broker-event handlers
call `on_fill` on every real execution report, or that anything ever calls
`StopBook.arm` in production — both are the same D3.51 residual
`check_reservation_lifecycle` carries, and the second is reported as CHECK-DEBT
by the arc that built this. A green means *the shipped origin writer publishes
the stop book's own figure, for the right trade, on the one snapshot, and
refuses when it has no figure*. It does NOT mean production fills reach it.
UNBOUND, and the evidence string says so on every run.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# C0302 (too-many-lines) disabled for the reason `check_execution_ledger`
# records: the §7.12 block, the C.9 argument and the per-finding reason strings
# ARE the deliverable, and §4.2 requires the check to be one runnable file.
# pylint: disable=too-many-lines,duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first: the writer is imported from the tree under test and
#: no check produces it.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS the `nixrisk` package out of `ctx.nix_home`, so it mutates
#: `sys.path` and `sys.modules` for the duration of the load and restores both —
#: the same declaration `check_execution_ledger` carries for the same reason.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep. The drive is arithmetic over dictionaries.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for a writer that publishes the wrong stop distance, keys a row "
    "to the wrong trade, or defaults a distance it does not have is a change to "
    "the figure §7:501 prices every correlation-bucket decision from, decided by "
    "a human against the frozen spec. An instrument empowered to edit the writer "
    "until its own drive came back clean would be manufacturing its own green "
    "over the one number D3.150 exists because nobody was choosing"
)
#: Genuinely MEASURED here: the writer is imported out of the tree under test,
#: driven against the shipped picture book, execution ledger and stop book, and
#: its source is parsed. The seam, the picture, the ledger and the stop book are
#: READ; each has its own gate.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/positions.py",)

NAME = "check_origin_write"

WRITER = "scripts/nixrisk/positions.py"
PACKAGE = "nixrisk"
MODULE = "nixrisk.positions"
_MODULES = (
    MODULE,
    "nixrisk.seam",
    "nixrisk.picture",
    "nixrisk.execution",
    "nixrisk.stops",
)

# --------------------------------------------------------------------------
# NON-VACUITY FLOORS. Every one is a FLOOR and every one is strictly below what
# the population below carries today (4 trades, 4 symbols, 2 partially-filled
# orders, 2 unstopped drives, 2 duplicate deliveries, 4 non-identity trades).
# Doctrine C.4: a threshold set to today's number is an anchor that moves.
# --------------------------------------------------------------------------

#: One trade cannot expose a wrong join at all — any join maps the only row to
#: the only stop. Two can, provided their distances differ.
MIN_TRADES = 2
#: One symbol cannot show the row is keyed by trade rather than by instrument.
MIN_SYMBOLS = 2
#: Below this the distances cannot be pairwise distinct in a useful way.
MIN_DISTINCT_DISTANCES = 2
#: Orders filled by MORE THAN ONE execution. Without one, §4's cumulative size
#: is indistinguishable from "the last fill's quantity".
MIN_PARTIAL_ORDERS = 1
#: Fills driven against a trade with NO armed stop. Without one, the fail-closed
#: half of the property is never exercised.
MIN_UNSTOPPED_DRIVES = 1
#: Re-delivered executions. Without one, idempotency at the published table is
#: an untested claim.
MIN_DUPLICATE_DELIVERIES = 1
#: Trades whose `trade_id` genuinely differs from their `client_order_id`.
#: Below this the join arm is running under the default binding, where a
#: hard-coded identity is invisible.
MIN_NON_IDENTITY_TRADES = 2

# --------------------------------------------------------------------------
# THE POPULATION. `(client_order_id, strategy_id, symbol, long?, qty,
# stop_ticks, fill_price)`.
#
# The stop distances are PAIRWISE DISTINCT, non-zero, and disjoint from the
# quantities — see §7.12 rule 3. Deliberately NOT a copy of
# `scripts/tests/test_positions.py`'s population.
# --------------------------------------------------------------------------
_ORDERS: tuple[tuple[str, str, str, bool, int, int, float], ...] = (
    ("CO-1", "strat-es", "ESZ6", True, 4, 13, 5000.00),
    ("CO-2", "strat-nq", "NQZ6", False, 3, 27, 18000.00),
    ("CO-3", "strat-cl", "CLZ6", True, 1, 41, 70.00),
    ("CO-4", "strat-rty", "RTYZ6", True, 2, 55, 2300.00),
)

#: Orders whose fill arrives as SUCCESSIVE partial executions, and how.
#: `client_order_id -> ((exec_id, increment, broker cumulative), ...)`.
_PARTIALS: dict[str, tuple[tuple[str, int, int], ...]] = {
    "CO-1": (("e1", 2, 2), ("e2", 2, 4)),
    "CO-4": (("e1", 1, 1), ("e2", 1, 2)),
}

#: Orders approved and FILLED with no stop ever armed. Two, so the floor of one
#: is a floor. `(client_order_id, strategy_id, symbol, long?, qty, price)`.
_UNSTOPPED: tuple[tuple[str, str, str, bool, int, float], ...] = (
    ("CO-9", "strat-es", "ESZ6", True, 2, 5001.00),
    ("CO-8", "strat-nq", "NQZ6", False, 1, 18010.00),
)

#: Per-symbol tick size (an instrument constant, §12A boot-loaded) and margin.
_TICKS = {"ESZ6": 0.25, "NQZ6": 0.25, "CLZ6": 0.01, "RTYZ6": 0.10}
_MARGIN = {"ESZ6": 500.0, "NQZ6": 1000.0, "CLZ6": 1700.0, "RTYZ6": 400.0}
_BALANCE = 250_000.0
_FRACTION = 0.70

#: The non-identity mint ARM JOIN drives under. A prefix AND the symbol, so the
#: minted id cannot coincide with any order id under any spelling.
_MINT_PREFIX = "TRD::"


class Finding(NamedTuple):
    """One defect: where it is, and what is wrong. Never a bare status."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The subject and the collaborators, imported out of the tree under test."""

    positions: ModuleType
    seam: ModuleType
    picture: ModuleType
    execution: ModuleType
    stops: ModuleType


@dataclasses.dataclass
class Tally:  # pylint: disable=too-many-instance-attributes
    """What the drive actually did. Non-vacuity is read off this, not asserted."""

    trades_compared: int = 0
    symbols: int = 0
    distinct_distances: int = 0
    partial_orders: int = 0
    unstopped_drives: int = 0
    duplicate_deliveries: int = 0
    non_identity_trades: int = 0


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# --------------------------------------------------------------------------
# LOADING — the subject comes out of the tree under test, never out of this one
# --------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    """Drop every `nixrisk*` module, restoring whatever was there before."""
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def _provenance(loaded: Loaded, home: Path) -> str:
    """Did every loaded module really come OUT OF `home`? MEASURED, not assumed.

    D3.124: `_preamble` appends the REAL `scripts/` to `sys.path` and never
    removes it, so an import against a tree lacking the subject resolves against
    the live repository and the gate measures a tree other than the one it
    reports on. The SUBJECT is pinned harder than the collaborators, because
    ARM STRUCTURE parses `home/WRITER` from disk while every other arm drives
    the IMPORTED module: those two halves must be the same FILE, not merely two
    files under one root.
    """
    root = (home / "scripts").resolve()
    subject = (home / WRITER).resolve()
    for module in loaded:
        origin = getattr(module, "__file__", None)
        if origin is None:
            return f"{module.__name__} has no __file__, so its origin is unknowable"
        resolved = Path(origin).resolve()
        if root != resolved and root not in resolved.parents:
            return (
                f"{module.__name__} was imported from {resolved}, which is NOT "
                f"under {root} — the tree under judgement does not contain the "
                "subject and the import fell through to another tree, so this "
                "gate measured something other than what it is reporting on "
                "(§17: never a PASS)"
            )
        if module.__name__ == MODULE and resolved != subject:
            return (
                f"{MODULE} was imported from {resolved}, not from the {WRITER} "
                f"this gate parses statically ({subject}) — the driven half and "
                "the read half would be judging two different files, so nothing "
                "was measured about either (§17: never a PASS)"
            )
    return ""


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the subject from `home`, leaving the interpreter as it was found.

    A path-keyed import is what lets a plant live on a `tmp_path` COPY (doctrine
    C.8): the gate drives whichever tree it is pointed at, and the production
    writer is never written.
    """
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    # A tree created after interpreter start is invisible to FileFinder's
    # directory-mtime cache, and the resulting ModuleNotFoundError would report
    # "the subject is unavailable" over a subject that is right there.
    importlib.invalidate_caches()
    try:
        modules = [importlib.import_module(name) for name in _MODULES]
        loaded = Loaded(*modules)
        complaint = _provenance(loaded, home)
        return (None, complaint) if complaint else (loaded, "")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{WRITER}: cannot import {MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# THE RIG — the shipped collaborators, assembled as production would
# --------------------------------------------------------------------------


def _order(loaded: Loaded, row: tuple[Any, ...]) -> Any:
    """One `ProposedOrder` from a population row."""
    seam = loaded.seam
    coid, strategy, symbol, is_long, qty, stop_ticks, _price = row
    return seam.ProposedOrder(
        client_order_id=coid,
        strategy_id=strategy,
        symbol=symbol,
        side=seam.Side.LONG if is_long else seam.Side.SHORT,
        qty=qty,
        margin_per_contract=_MARGIN[symbol],
        stop_ticks=stop_ticks,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1000.0,
    )


def _report(
    loaded: Loaded,
    row: tuple[Any, ...],
    *,
    exec_id: str = "x1",
    qty: int | None = None,
    cumulative: int | None = None,
) -> Any:
    """One `ExecutionReport` for a population row."""
    execution = loaded.execution
    coid, _strategy, symbol, is_long, order_qty, _stop, price = row
    filled = order_qty if qty is None else qty
    return execution.ExecutionReport(
        order_id=coid,
        exec_id=exec_id,
        symbol=symbol,
        side=execution.FillSide.BUY if is_long else execution.FillSide.SELL,
        filled_qty=filled,
        price=price,
        cumulative_qty=filled if cumulative is None else cumulative,
        ts=1001.0 + len(exec_id),
    )


class Rig:
    """One writer plus the shipped collaborators it composes. Fresh per arm."""

    def __init__(self, loaded: Loaded, *, mint: Any = None) -> None:
        self.loaded = loaded
        self.book = loaded.picture.FinancialPictureBook(
            balance=_BALANCE,
            deployable_fraction=_FRACTION,
            margin_per_contract=_MARGIN,
        )
        self.ledger = loaded.execution.ExecutionLedger()
        self.stops = loaded.stops.StopBook(_TICKS)
        origins_kwargs = {} if mint is None else {"mint": mint}
        self.origins = loaded.positions.EntryOrderOrigins(**origins_kwargs)
        self.writer = loaded.positions.PositionOriginWriter(
            picture=self.book,
            ledger=self.ledger,
            stops=self.stops,
            origins=self.origins,
        )

    def open(self, row: tuple[Any, ...], *, arm: bool = True) -> Any:
        """Approval, then the confirmed-fill stop arming. Returns the origin."""
        order = _order(self.loaded, row)
        origin = self.origins.record(order)
        if arm:
            self.stops.arm(row[6], order)
        return origin

    def published(self) -> dict[str, Any]:
        """The published position table, keyed by `trade_id`."""
        return {row.trade_id: row for row in self.book.current().positions}


def _reference_book(loaded: Loaded) -> Any:
    """A SECOND stop book, armed here and never handed to any writer.

    §7.12 rule 4: if the reference were read through the object that produced
    the row, the comparison would be a figure against itself. This book exists
    only to cross-check this gate's own literals against the shipped conversion,
    so a stale literal is a REFUSAL rather than a false red.
    """
    book = loaded.stops.StopBook(_TICKS)
    for row in _ORDERS:
        book.arm(row[6], _order(loaded, row))
    return book


# --------------------------------------------------------------------------
# PRE-FLIGHT — the population's own credibility, before any verdict
# --------------------------------------------------------------------------


def _population_defect() -> str:
    """A degenerate population agrees with anything. Refuse before measuring.

    Written as an ordered table rather than a ladder of returns: every entry is
    a way this gate's OWN input could make a green meaningless, and a table can
    be read as the list §7.12 rule 3 asks for.
    """
    distances = [row[5] for row in _ORDERS]
    quantities = {row[4] for row in _ORDERS}
    symbols = {row[2] for row in _ORDERS}
    complaints = (
        (
            len(_ORDERS) < MIN_TRADES,
            (
                f"the drive population carries {len(_ORDERS)} trade(s), below "
                f"the floor of {MIN_TRADES} — a single trade cannot expose a "
                "wrong join, because any join maps the only row to the only "
                "stop (§5.3: an empty scope is never a PASS)"
            ),
        ),
        (
            any(distance <= 0 for distance in distances),
            (
                f"a reference stop distance of {min(distances, default=0)!r} "
                "would let a writer publishing zero — the D3.136 fail-open this "
                "gate exists to catch — agree with the reference"
            ),
        ),
        (
            len(set(distances)) != len(distances),
            (
                f"two trades share a stop distance {sorted(distances)} — a "
                "writer that read the WRONG trade's stop would publish the "
                "right number by luck and this gate would see agreement"
            ),
        ),
        (
            len(set(distances)) < MIN_DISTINCT_DISTANCES,
            (
                f"{len(set(distances))} distinct stop distance(s), below the "
                f"floor of {MIN_DISTINCT_DISTANCES}"
            ),
        ),
        (
            bool(set(distances) & quantities),
            (
                "a stop distance coincides with a position size "
                f"({sorted(set(distances) & quantities)}) — a writer publishing "
                "`size` where the distance belongs would agree by coincidence"
            ),
        ),
        (
            len(symbols) < MIN_SYMBOLS,
            (
                f"the population spans {len(symbols)} symbol(s), below the "
                f"floor of {MIN_SYMBOLS}"
            ),
        ),
    )
    for failed, why in complaints:
        if failed:
            return f"{WRITER}: {why}"
    return ""


def _reference_defect(loaded: Loaded) -> str:
    """This gate's literals against the SHIPPED conversion. Broken ⇒ refuse."""
    try:
        book = _reference_book(loaded)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            f"{WRITER}: this gate's own reference stop book could not be armed — "
            f"{type(exc).__name__}: {exc}. With no independent reference there is "
            "nothing to compare the published rows against, so a verdict here "
            "would be about this instrument and not about the writer (§17: never "
            "a PASS)"
        )
    for row in _ORDERS:
        state = book.get(row[0])
        if state is None or state.initial_distance_ticks != row[5]:
            return (
                f"{WRITER}: this gate's literal stop distance for {row[0]} is "
                f"{row[5]!r} and the SHIPPED stop book armed from the same order "
                f"holds {getattr(state, 'initial_distance_ticks', None)!r} — the "
                "reference disagrees with itself, so a red here would be about "
                "this instrument and not about the writer (§17: never a PASS)"
            )
    return ""


# --------------------------------------------------------------------------
# ARM ORIGIN — the published figure against the independent reference
# --------------------------------------------------------------------------


def _one_origin(
    row: tuple[Any, ...], origin: Any, published: dict[str, Any], reference: Any
) -> Finding | None:
    """One trade's published row against the independent reference, or `None`."""
    site = f"{WRITER}:PositionRow.stop_distance"
    coid, _strategy, symbol, _long, _qty, expected, _price = row
    got = published.get(origin.trade_id)
    if got is None:
        return Finding(
            site,
            f"trade {origin.trade_id!r} (order {coid}, {symbol}) has NO published "
            f"row after a confirmed fill; the table holds {sorted(published)} — a "
            "position that never reaches §3's table is priced at zero by "
            "OMISSION, which is the same admitting direction as a zero distance "
            "(D3.136's second door)",
        )
    independent = reference.get(coid).initial_distance_ticks
    if got.stop_distance != expected or independent != expected:
        return Finding(
            site,
            f"trade {origin.trade_id!r} (order {coid}, {symbol}) publishes "
            f"stop_distance={got.stop_distance!r}; the stop book armed from that "
            f"order's own stop_ticks holds {independent!r} and this gate's "
            f"independent reference says {expected!r}. §7:501 prices bucket "
            "exposure as (stop_ticks + pad) × tick_value × contracts, so the "
            "published number is the one §7's correlation cap will spend, and it "
            "is not the one the sizer sized against. Note the population's "
            "distances are pairwise distinct: a value that is present, positive "
            "and plausible is still WRONG if it belongs to another trade",
        )
    return None


def _origin_findings(
    rig: Rig, reference: Any, origins: dict[str, Any], tally: Tally
) -> list[Finding]:
    """Per trade: the row exists, and its distance is the stop book's."""
    published = rig.published()
    findings: list[Finding] = []
    for row in _ORDERS:
        finding = _one_origin(row, origins[row[0]], published, reference)
        if finding is None:
            tally.trades_compared += 1
        else:
            findings.append(finding)
    tally.symbols = len({row.symbol for row in published.values()})
    tally.distinct_distances = len({row.stop_distance for row in published.values()})
    return findings


def arm_origin(loaded: Loaded, tally: Tally) -> list[Finding]:
    """The whole population, filled, compared per trade against the reference."""
    rig = Rig(loaded)
    reference = _reference_book(loaded)
    origins = {row[0]: rig.open(row) for row in _ORDERS}
    _fill_population(rig, loaded)
    return _origin_findings(rig, reference, origins, tally)


# --------------------------------------------------------------------------
# ARM JOIN — the same drive under a NON-IDENTITY mint
# --------------------------------------------------------------------------


def arm_join(loaded: Loaded, tally: Tally) -> list[Finding]:
    """The published key follows the INJECTED policy, not the order id.

    Under the default binding a trade IS its entry order, so `trade_id ==
    client_order_id` and a writer that hard-coded the identity is invisible to
    every drive over the default. This arm is the drive that can see it, and it
    re-checks the distance THROUGH the changed join so a writer that kept a
    private order-keyed table is caught as well.
    """
    rig = Rig(loaded, mint=lambda order: f"{_MINT_PREFIX}{order.client_order_id}")
    origins = {row[0]: rig.open(row) for row in _ORDERS}
    for row in _ORDERS:
        rig.writer.on_fill(_report(loaded, row))
    published = rig.published()
    findings: list[Finding] = []
    for row in _ORDERS:
        findings += _one_join(row, origins[row[0]], published, tally)
    return findings + _identity_leak(published, f"{WRITER}:PositionRow.trade_id")


def _one_join(
    row: tuple[Any, ...], origin: Any, published: dict[str, Any], tally: Tally
) -> list[Finding]:
    """One trade under the non-identity mint: the key, then the distance."""
    site = f"{WRITER}:PositionRow.trade_id"
    coid, expected = row[0], row[5]
    minted = f"{_MINT_PREFIX}{coid}"
    if origin.trade_id != minted:
        return [
            Finding(
                site,
                f"the injected mint returned {minted!r} for order {coid} and the "
                f"recorded origin holds {origin.trade_id!r} — the join is not the "
                "injected surface it declares",
            )
        ]
    got = published.get(minted)
    if got is None:
        return [
            Finding(
                site,
                f"under a NON-IDENTITY mint the published table is keyed "
                f"{sorted(published)} and carries no row for {minted!r}. The "
                "writer is keying §3's table by something other than the "
                "TradeOrigin it was handed — most likely the client_order_id, "
                "which is INDISTINGUISHABLE from correct under the default "
                "binding and wrong the moment a trade is not its entry order",
            )
        ]
    tally.non_identity_trades += 1
    if got.stop_distance != expected:
        return [
            Finding(
                site,
                f"trade {minted!r} publishes stop_distance="
                f"{got.stop_distance!r} against the reference {expected!r} — the "
                "distance did not survive a change of join, so the two are "
                "related by an assumption rather than by the recorded origin",
            )
        ]
    return []


def _identity_leak(published: dict[str, Any], site: str) -> list[Finding]:
    """No published key may still be a bare order id under a changed mint."""
    leaked = sorted(set(published) & {row[0] for row in _ORDERS})
    if not leaked:
        return []
    return [
        Finding(
            site,
            f"under a NON-IDENTITY mint the published table still carries "
            f"{leaked} — those are client_order_ids, so the writer wrote an "
            "equality where the injected join belongs",
        )
    ]


# --------------------------------------------------------------------------
# ARM UNSTOPPED — a fill with no armed stop publishes NOTHING, loudly
# --------------------------------------------------------------------------


def arm_unstopped(loaded: Loaded, tally: Tally) -> list[Finding]:
    """The fail-closed half. A defaulted distance here is D3.136 all over again."""
    site = f"{WRITER}:on_fill[no armed stop]"
    findings: list[Finding] = []
    for coid, strategy, symbol, is_long, qty, price in _UNSTOPPED:
        row = (coid, strategy, symbol, is_long, qty, 0, price)
        rig = Rig(loaded)
        rig.open(row, arm=False)
        before = rig.book.current()
        try:
            rig.writer.on_fill(_report(loaded, row))
        except loaded.positions.UnstoppedFill as exc:
            tally.unstopped_drives += 1
            findings += _refusal_findings(rig, before, str(exc), coid, site)
            continue
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            findings.append(
                Finding(
                    site,
                    f"{coid}: the writer refused an unstopped fill with "
                    f"{type(exc).__name__}: {exc} — the refusal must be the "
                    "module's own UnstoppedFill, because a caller cannot tell an "
                    "unprotected position from an unrelated fault by exception "
                    "type alone (§18)",
                )
            )
            continue
        findings.append(
            Finding(
                site,
                f"{coid} ({symbol}, {qty} filled) has NO armed stop and the "
                f"writer PUBLISHED anyway: {_render_rows(rig)}. §7:501 prices "
                "bucket exposure from stop_distance, so a defaulted or zero "
                "value prices a real position at zero dollar risk, the bucket "
                "reads emptier than it is and the correlation cap ADMITS MORE — "
                "D3.136's fail-open under a new spelling, on a field that now "
                "looks populated",
            )
        )
    return findings


def _refusal_findings(
    rig: Rig, before: Any, message: str, coid: str, site: str
) -> list[Finding]:
    """A refusal must name its reason AND leave the published table untouched."""
    findings: list[Finding] = []
    if coid not in message or "stop" not in message.lower():
        findings.append(
            Finding(
                site,
                f"{coid}: the refusal does not name the order and the missing "
                f"stop; it says {message!r}. An exception TYPE is a shared "
                "namespace — the reason is the evidence (check contract v2 §11)",
            )
        )
    after = rig.book.current()
    if after.positions or after.version != before.version:
        findings.append(
            Finding(
                site,
                f"{coid}: the writer raised AND moved the published table "
                f"(version {before.version!r} -> {after.version!r}, rows "
                f"{_render_rows(rig)}) — a refusal that still publishes leaves a "
                "row nobody chose the distance for",
            )
        )
    recorded = rig.writer.unstopped()
    if not any(record.client_order_id == coid for record in recorded):
        findings.append(
            Finding(
                site,
                f"{coid}: the refusal is not recorded in unstopped() "
                f"({[record.client_order_id for record in recorded]}) — a "
                "confirmed fill with no stop is an UNPROTECTED position (§4, "
                "§12.1) and §14 resolves it toward FLAT, so a refusal that "
                "vanishes leaves nothing for a supervising loop to act on",
            )
        )
    if rig.ledger.position(_symbol_of(coid)).net_qty == 0:
        findings.append(
            Finding(
                site,
                f"{coid}: the refused fill is not in the execution ledger — §4 "
                "makes the fill a FACT the system reports, never a negotiation, "
                "so discarding it makes the ledger's derived position disagree "
                "with the account",
            )
        )
    return findings


def _symbol_of(coid: str) -> str:
    """The symbol an unstopped population row trades."""
    return next(row[2] for row in _UNSTOPPED if row[0] == coid)


def _render_rows(rig: Rig) -> str:
    """The published table as `trade=distance`, for a reason-bearing message."""
    return (
        ", ".join(
            f"{row.trade_id}={row.stop_distance!r}"
            for row in rig.book.current().positions
        )
        or "<empty>"
    )


# --------------------------------------------------------------------------
# ARM LEDGER — §4's cumulative size, and idempotency at the published table
# --------------------------------------------------------------------------


def _fill_population(rig: Rig, loaded: Loaded) -> None:
    """Deliver every execution the population implies, partials included."""
    for row in _ORDERS:
        for exec_id, increment, cumulative in _PARTIALS.get(
            row[0], (("x1", row[4], row[4]),)
        ):
            rig.writer.on_fill(
                _report(
                    loaded, row, exec_id=exec_id, qty=increment, cumulative=cumulative
                )
            )


def _partial_findings(rig: Rig, origins: dict[str, Any], tally: Tally) -> list[Finding]:
    """A partially-filled order publishes ONE row at the §4 cumulative size."""
    site = f"{WRITER}:on_fill[cumulative]"
    findings: list[Finding] = []
    published = rig.published()
    for coid, execs in _PARTIALS.items():
        tally.partial_orders += 1
        row = next(item for item in _ORDERS if item[0] == coid)
        filled = sum(increment for _exec_id, increment, _cum in execs)
        signed = filled if row[3] else -filled
        got = published.get(origins[coid].trade_id)
        if got is None or got.size != signed:
            findings.append(
                Finding(
                    site,
                    f"{coid} filled in {len(execs)} executions totalling "
                    f"{filled!r} contracts and the published row carries size "
                    f"{getattr(got, 'size', None)!r} (expected {signed!r}) — §4 "
                    "sets position to the ACTUAL filled quantity and derives it "
                    "from the cumulative fill set, so a row that shows the last "
                    "increment is a position the account does not hold",
                )
            )
    return findings


def _duplicate_findings(rig: Rig, loaded: Loaded, tally: Tally) -> list[Finding]:
    """A re-delivered execution must not move the published table at all."""
    rows_before = rig.published()
    version_before = rig.book.current().version
    for row in _ORDERS[1:3]:
        tally.duplicate_deliveries += 1
        rig.writer.on_fill(_report(loaded, row))
    if rig.published() == rows_before and rig.book.current().version == version_before:
        return []
    return [
        Finding(
            f"{WRITER}:on_fill[duplicate]",
            f"re-delivering {tally.duplicate_deliveries} already-seen "
            f"execution(s) moved the published table from version "
            f"{version_before!r} to {rig.book.current().version!r} — §4 makes a "
            "re-delivery idempotent, and a table that advances on one reports a "
            "change the broker never made",
        )
    ]


def arm_ledger(loaded: Loaded, tally: Tally) -> list[Finding]:
    """Partial fills sum; a re-delivery does not move the table (doctrine C.9)."""
    site = f"{WRITER}:on_fill[cumulative]"
    rig = Rig(loaded)
    origins = {row[0]: rig.open(row) for row in _ORDERS}
    _fill_population(rig, loaded)
    findings = _partial_findings(rig, origins, tally)
    findings += _duplicate_findings(rig, loaded, tally)
    return findings + _row_count_findings(rig, len(_ORDERS), site)


def _row_count_findings(rig: Rig, expected: int, site: str) -> list[Finding]:
    """One row per trade. §3's table is KEYED by trade_id."""
    rows = rig.book.current().positions
    if len(rows) == expected and len({row.trade_id for row in rows}) == expected:
        return []
    return [
        Finding(
            site,
            f"the published table holds {len(rows)} row(s) under "
            f"{len({row.trade_id for row in rows})} distinct trade_id(s) for "
            f"{expected} trade(s) — §3 keys the position table BY trade_id, and a "
            "second row for one key double-counts the position in every aggregate "
            "computed over the table",
        )
    ]


# --------------------------------------------------------------------------
# ARM SNAPSHOT — the row rides §3's ONE versioned snapshot
# --------------------------------------------------------------------------


def arm_snapshot(loaded: Loaded) -> list[Finding]:
    """One commit per published fill, balance travelling on the same object."""
    site = f"{WRITER}:FinancialPictureBook.commit"
    rig = Rig(loaded)
    findings: list[Finding] = []
    for row in _ORDERS:
        rig.open(row)
        before = rig.book.current().version
        write = rig.writer.on_fill(_report(loaded, row))
        picture = write.picture
        if picture.version != before + 1:
            findings.append(
                Finding(
                    site,
                    f"{row[0]}: the picture version went {before!r} -> "
                    f"{picture.version!r} for ONE published fill — §3 publishes "
                    "one atomic snapshot per change, and a row that lands outside "
                    "a single commit is a second write a consumer can observe "
                    "between",
                )
            )
        if picture is not rig.book.current():
            findings.append(
                Finding(
                    site,
                    f"{row[0]}: the returned snapshot is not the book's current "
                    "one — the row was published somewhere other than §3's table, "
                    "and §9 makes the Limiter the SOLE writer of one table",
                )
            )
        if write.row not in picture.positions or picture.balance != _BALANCE:
            findings.append(
                Finding(
                    site,
                    f"{row[0]}: the row is not on the snapshot carrying balance "
                    f"{picture.balance!r} (expected {_BALANCE!r}) — §3's ATOMICITY "
                    "RULE publishes balance and the position table together or "
                    "not at all",
                )
            )
    return findings + _coherence_findings(loaded, rig, site)


def _coherence_findings(loaded: Loaded, rig: Rig, site: str) -> list[Finding]:
    """The final snapshot must satisfy the shipped torn-read predicate."""
    defects = loaded.picture.picture_defects(rig.book.current(), _FRACTION)
    if not defects:
        return []
    return [
        Finding(
            site,
            f"the snapshot the origin write produced disagrees with itself: "
            f"{'; '.join(defects)} — a picture whose own aggregates do not follow "
            "from its rows is refused at publish time, so a writer that builds "
            "one has broken §3's coherence and not merely mispriced a row",
        )
    ]


# --------------------------------------------------------------------------
# ARM STRUCTURE — the two properties no drive can see
# --------------------------------------------------------------------------


def _position_row_call(tree: ast.Module) -> ast.Call | None:
    """The module's construction of a §3 `PositionRow`. Found, never named."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PositionRow"
        ):
            return node
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _attributes(tree: ast.AST) -> set[str]:
    """Every attribute NAME read anywhere under `tree`."""
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def arm_structure(home: Path) -> list[Finding]:
    """The distance traces to the STOP BOOK, and the key to the ORIGIN.

    Neither is visible to a drive. (a) `StopBook.arm` records
    `initial_distance_ticks` FROM `ProposedOrder.stop_ticks`, so a writer that
    published the order's own figure produces identical output on every drive
    this gate can build — and diverges the moment a stop is amended or re-armed,
    which is precisely when the published number would stop being the one the
    stop that is actually protecting the position holds. (b) A `trade_id` taken
    from the report is byte-identical to the recorded origin's under the default
    binding; ARM JOIN catches it behaviourally and this catches the shape.
    """
    site = f"{WRITER}:PositionRow(...)"
    tree = ast.parse((home / WRITER).read_text(encoding="utf-8"), filename=WRITER)
    call = _position_row_call(tree)
    if call is None:
        return [
            Finding(
                site,
                "the module constructs no PositionRow at all — the origin write "
                "is the ONE production site that creates the row representing an "
                "open position (D3.150), and a module that builds none is not it",
            )
        ]
    findings = _distance_shape(call, site) + _trade_id_shape(call, site)
    return findings + _stop_ticks_read(tree, site)


def _distance_shape(call: ast.Call, site: str) -> list[Finding]:
    """`stop_distance=` may not be a literal, and must trace to a NAME."""
    value = _keyword(call, "stop_distance")
    if value is None:
        return [
            Finding(
                site,
                "the PositionRow construction passes no stop_distance keyword — "
                "a positional row construction cannot be read for where the "
                "figure came from, and §3's row is the one place the number is "
                "chosen",
            )
        ]
    if isinstance(value, ast.Constant):
        return [
            Finding(
                site,
                f"stop_distance is the LITERAL {value.value!r} — that is D3.150's "
                "finding restated as code: a placeholder is indistinguishable "
                "from a considered figure, and §7's correlation cap spends it "
                "either way",
            )
        ]
    return []


def _trade_id_shape(call: ast.Call, site: str) -> list[Finding]:
    """`trade_id=` must read a `trade_id`, not an order id."""
    value = _keyword(call, "trade_id")
    if value is None:
        return [
            Finding(
                site,
                "the PositionRow construction passes no trade_id keyword — §3 "
                "keys the table by it and the key cannot be read positionally",
            )
        ]
    names = _attributes(value)
    if (
        isinstance(value, ast.Constant)
        or "client_order_id" in names
        or "order_id" in names
    ):
        return [
            Finding(
                site,
                f"trade_id is fed from {sorted(names) or value!r} — the trade "
                "<-> order relationship is UNDEFINED in the frozen spec (no "
                "sentence relates trade_id to client_order_id), so writing the "
                "equality here buries an architectural decision where no reader "
                "sees it. It must come from the injected TradeOrigin, whose "
                "minting policy is where that decision belongs",
            )
        ]
    if "trade_id" not in names:
        return [
            Finding(
                site,
                f"trade_id is fed from {sorted(names) or value!r}, which never "
                "reads a trade_id — §3's key must come from the recorded origin",
            )
        ]
    return []


def _stop_ticks_read(tree: ast.Module, site: str) -> list[Finding]:
    """The module must read `initial_distance_ticks`, and never `stop_ticks`."""
    names = _attributes(tree)
    findings: list[Finding] = []
    if "initial_distance_ticks" not in names:
        findings.append(
            Finding(
                site,
                "the module never reads StopState.initial_distance_ticks — the "
                "AUTHORITATIVE stop book is the only holder of the distance the "
                "stop actually protecting this position was armed at, and a "
                "figure obtained anywhere else agrees with it only until a stop "
                "is amended",
            )
        )
    if "stop_ticks" in names:
        findings.append(
            Finding(
                site,
                "the module reads ProposedOrder.stop_ticks. `StopBook.arm` "
                "records initial_distance_ticks FROM stop_ticks, so the two agree "
                "on every drive this gate can build and NO behavioural arm can "
                "separate them — which is exactly why reading the order's copy "
                "instead of the stop book's is a defect that would ship green",
            )
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def _drive_floors(tally: Tally) -> str:
    """What the drive ACTUALLY delivered, read off the tally rather than hoped."""
    checks = (
        (tally.trades_compared, MIN_TRADES, "trade(s) compared"),
        (tally.symbols, MIN_SYMBOLS, "published symbol(s)"),
        (tally.distinct_distances, MIN_DISTINCT_DISTANCES, "distinct distance(s)"),
        (tally.partial_orders, MIN_PARTIAL_ORDERS, "partially-filled order(s)"),
        (tally.unstopped_drives, MIN_UNSTOPPED_DRIVES, "unstopped fill drive(s)"),
        (
            tally.duplicate_deliveries,
            MIN_DUPLICATE_DELIVERIES,
            "re-delivered execution(s)",
        ),
        (
            tally.non_identity_trades,
            MIN_NON_IDENTITY_TRADES,
            "non-identity trade id(s)",
        ),
    )
    for actual, floor, label in checks:
        if actual < floor:
            return (
                f"{WRITER}: the drive reached {actual} {label}, below the floor of "
                f"{floor} — the verdict would be about a population that never "
                "exercised the condition it claims to prove"
            )
    return ""


def _evidence(tally: Tally) -> str:
    return (
        f"{tally.trades_compared} trade(s) compared PER TRADE against an "
        f"INDEPENDENT reference (this gate's own literals, cross-checked against "
        f"a second StopBook armed here and never handed to the writer), across "
        f"{tally.symbols} symbol(s) carrying {tally.distinct_distances} DISTINCT "
        f"stop distance(s) — so a value that is present, positive and plausible "
        f"but belongs to another trade is still a red; the whole drive repeated "
        f"under a NON-IDENTITY trade-id mint ({tally.non_identity_trades} trade "
        f"id(s) differing from their client_order_id), which is the only way a "
        f"hard-coded identity is visible; {tally.unstopped_drives} confirmed "
        f"fill(s) with no armed stop refused with a reason and publishing NO row; "
        f"{tally.partial_orders} partially-filled order(s) publishing ONE row at "
        f"the §4 cumulative size and {tally.duplicate_deliveries} re-delivered "
        f"execution(s) not moving the table; every row proven to ride a single "
        f"FinancialPictureBook.commit() carrying balance under one version stamp; "
        f"and read statically for the two properties no drive can see (the "
        f"distance traces to initial_distance_ticks and never to stop_ticks, the "
        f"key to the recorded TradeOrigin). Driven against the SHIPPED writer "
        f"imported out of the tree under judgement with its __file__ provenance "
        f"asserted. UNBOUND: drives the WRITER, never the Limiter's broker-event "
        f"handlers or anything that calls StopBook.arm in production — neither "
        f"exists (the D3.51 residual, one module over)"
    )


def _guarded(label: str, arm: Any) -> list[Finding]:
    """Run one arm. A RAISING subject is a finding about the subject, not a crash.

    This gate's drive is a legitimate one: approved orders, armed stops, valid
    execution reports. A refusal is therefore the writer's defect, and letting
    the exception reach `run` would report CANNOT_MEASURE — "the instrument
    broke" — over a subject that broke instead (§18's shared namespace).
    """
    try:
        return list(arm())
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{WRITER}:{label}",
                f"the drive raised {type(exc).__name__}: {exc} — this gate's "
                "population is a legitimate one (recorded origins, armed stops, "
                "valid execution reports), so a refusal here is the writer's "
                "defect and not this gate's inability to measure",
            )
        ]


def _drive(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    """Every arm, in order."""
    arms: tuple[tuple[str, Any], ...] = (
        ("on_fill[origin]", lambda: arm_origin(loaded, tally)),
        ("on_fill[join]", lambda: arm_join(loaded, tally)),
        ("on_fill[no armed stop]", lambda: arm_unstopped(loaded, tally)),
        ("on_fill[cumulative]", lambda: arm_ledger(loaded, tally)),
        ("commit", lambda: arm_snapshot(loaded)),
        ("PositionRow(...)", lambda: arm_structure(home)),
    )
    findings: list[Finding] = []
    for label, arm in arms:
        findings += _guarded(label, arm)
    return findings


def _preflight(home: Path) -> tuple[Loaded | None, str]:
    """Both sides, or the ONE reason the comparison cannot be made.

    The population is judged BEFORE the subject is imported, deliberately: a
    gate whose own reference is degenerate has nothing to say about any writer,
    and saying it after a successful import would read as a statement about the
    subject.
    """
    complaint = _population_defect()
    if complaint:
        return None, complaint
    loaded, complaint = load(home)
    if loaded is None:
        return None, complaint
    complaint = _reference_defect(loaded)
    return (None, complaint) if complaint else (loaded, "")


def _verdict(findings: list[Finding], tally: Tally) -> CheckResult:
    """One reading or one refusal, never both and never neither."""
    floor = _drive_floors(tally)
    if floor and not findings:
        return _cannot_measure(floor)
    if findings:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in findings),
            evidence=_evidence(tally),
            detail="; ".join(f"{site}: {why}" for site, why in findings),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=_evidence(tally))


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the origin write. Never repairs (see NON_CORRECTABLE_REASON)."""
    try:
        tally = Tally()
        loaded, complaint = _preflight(ctx.nix_home)
        if loaded is None:
            return _cannot_measure(complaint)
        findings = _drive(loaded, ctx.nix_home, tally)
        return _verdict(findings, tally)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
