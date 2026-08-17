#!/usr/bin/env python3
"""A CONFIRMED FILL arms the stop, releases the remainder, and publishes §3's row.

ARC 034 / sub-agent A. ONE gate, ONE property (`nix_check_contract.md` §5.5):

    driving a real `ExecutionReport` through the shipped `FillHandler` ARMS a
    stop that was not armed before, releases the unfilled remainder's
    reservation, and publishes §3's position row carrying THAT stop's distance —
    in the order `nixrisk/fill_seam.py` fixes — after which §7's correlation
    bucket cap prices the held position from that real value and its answer
    MOVES when the distance moves.

Every `§` in this file cites `docs/nics_risk_subsystem_spec_v1.3.md` unless
another document is named on the line. `D3.<n>` cites `docs/CHECK-DEBT.md`.

------------------------------------------------------------------------------
WHY THIS IS ONE PROPERTY AND NOT EIGHT
------------------------------------------------------------------------------
Every arm below is a property OF ONE DRIVE of one event. The subject is not a
class, it is a MOTION: §3 and §4 require the arm, the release and the publish to
be one motion under one version stamp, so "the stop was armed" and "the row was
published" are not separable claims — a gate proving either alone proves the
thing D3.178 already found green and useless. Splitting them would give two gates
that must build the same rig and drive the same fill, which is the duplicate
instrument doctrine C.9 forbids.

The JOIN is a genuinely different property (a round trip over a registry, with no
fill in it) and it is a DIFFERENT gate: `checks/check_trade_join.py`.

------------------------------------------------------------------------------
THE TRAP THIS GATE EXISTS TO AVOID — named first, because it is the point
------------------------------------------------------------------------------
ARC 033's `check_origin_write` proves the writer publishes the stop book's own
figure. It calls `arm` itself and it calls `on_fill` itself. **A gate that calls
`arm` directly re-proves ARC 029's mechanism; the NEW thing is that a FILL calls
it.** So no arm here may reach for `StopBook.arm`, and the stop book handed to the
handler is asserted EMPTY for the order before the fill and populated after it.
The arming is required to be a CONSEQUENCE of the fill, observed on both sides.

The second half of the same trap is the cap. A cap driven once returns a number,
and a number proves nothing about pricing: `used_dollar_risk` could be a constant
and every assertion about one drive would still hold. ARM CAP therefore drives the
SAME symbol, the SAME filled size and a DIFFERENT stop distance through the whole
fill path a second time, and requires the admitted contract count to DIFFER. A cap
that answers the same for every distance is not pricing anything.

------------------------------------------------------------------------------
THE EIGHT ARMS
------------------------------------------------------------------------------
* **ARM SEQUENCE.** `FillOutcome.steps` on every first fill equals the seam's own
  `FillStep` order. The expected order is READ OFF THE IMPORTED ENUM (sorted by
  value), never typed here, so a reordering of the seam and a reordering of the
  handler cannot agree with each other through this file.
* **ARM ORDERING.** The recorded sequence is a claim the handler makes about
  itself. This arm observes the order from OUTSIDE, through a wrapper that
  DELEGATES to the shipped `IocRemainder` and samples the world at the instant
  step 2 runs: the stop must ALREADY be in the book (step 1 ran) and the picture
  book must NOT yet have committed this fill (step 3 has not). Those two facts
  bracket step 2 without asking the handler anything.
* **ARM CAUSATION.** `StopBook.get(coid)` is `None` before `on_fill` and a
  `StopState` after, per order; the armed distance is the APPROVED order's
  `stop_ticks` (§7:476, the sizer's own distance); the published
  `PositionRow.stop_distance` is that armed distance. All three, per trade.
* **ARM PARTIAL.** §4's partial-fill rule with filled DRIVEN APART from requested:
  the published size is the FILLED quantity, an IOC cancel is issued for the short
  orders and NOT for the fully-filled ones, and the reservation is released. A
  population where filled equals requested measures nothing about this.
* **ARM ONCE.** A successive partial fill of the same order does NOT re-convert
  the stop: no `ARM_STOP` step, the same `StopState` object, and — the fact that
  makes it a measurement rather than a restatement — the stop's `anchor` is still
  the FIRST fill's price, so a silent re-arm against the second price is visible.
* **ARM CAP.** §7:501's exposure unit computed HERE from the frozen sentence, over
  the PUBLISHED rows, against `nixalloc.caps.admit`'s own answer; two same-bucket
  rows summed with `contributors == 2`; and the answer required to MOVE when the
  distance moves.
* **ARM CONFORMANCE.** The shipped classes satisfy the frozen ports — `isinstance`
  against the `runtime_checkable` Protocols AND a parameter-name comparison,
  because a `runtime_checkable` isinstance compares METHOD NAMES ONLY and is blind
  to arity, parameter names and every annotation. `LimiterFillSink.on_fill` is
  compared against `broker_seam.OrderEventSink.on_fill` parsed by AST out of
  `scripts/broker/broker_seam.py` — a DIFFERENT file this module cannot edit in
  the same motion.
* **ARM REFUSAL.** A fill for an order this Limiter never approved is refused
  LOUDLY by both the handler and the sink, and the message NAMES the order — never
  a bare exception type, never a silently reconstructed distance.

------------------------------------------------------------------------------
WHAT THIS GATE CANNOT PROVE, stated rather than implied
------------------------------------------------------------------------------
**It does not prove a broker event reaches this handler in production.**
`LimiterFillSink` carries a MINORITY of `broker_seam.OrderEventSink`'s verbs, so
it cannot yet be handed to the IBKR adapter and no live fill flows. **The exact
fraction is not written here** — ARM CONFORMANCE derives both figures from
`scripts/broker/broker_seam.py` and puts them in the evidence on every run, so
the day the Limiter's event handler grows its second verb this paragraph does not
have to be found and edited (directive 3). ARM CONFORMANCE
proves the SHAPE matches the event the broker seam already emits; it says nothing
about anything calling it. That residual is the ARC 034 successor to D3.178 and it
is reported as CHECK-DEBT by the arc that built this, never implied by this green.

It also does not prove the IOC cancel does anything on the wire (the cancel port
is driven against a recorder here — the venue side is `broker_order_ibkr`'s and
has its own gates), and it proves nothing about §9's `filled` Plane-1 row, which
`seam.EventKind` has no member for.

------------------------------------------------------------------------------
`debug.md` §7.12 — THE STANDING QUESTION, asked where this gate was built
------------------------------------------------------------------------------
*What would have to be true for this gate to PASS while measuring NOTHING?*

1. **The subject is unimportable, or the import falls through to the LIVE
   repository** because `checks/_preamble.py` appends the real `scripts/` to
   `sys.path` and never removes it (D3.124). *Closed twice:* an import failure is
   CANNOT_MEASURE naming the exception (§17 — never a PASS), and every loaded
   module's `__file__` must resolve to the exact path under the tree under
   judgement, with the subject pinned hardest.
2. **The drive raises on every fill, so nothing is published and no arm has a row
   to disagree with.** *Closed:* `MIN_FULL_SEQUENCES`, `MIN_TRADES`,
   `MIN_PARTIAL_ORDERS` and `MIN_CANCELS` are floors read off what the drive
   ACTUALLY did, and every one sits strictly below today's figure.
3. **Every order shares one stop distance**, so a handler that published a
   constant would agree with the reference by luck. *Closed:* the distances must
   be pairwise DISTINCT, non-zero, and disjoint from the quantities before any
   comparison is trusted — otherwise a handler publishing `size` where the
   distance belongs agrees by coincidence.
4. **The expected step order is a constant in this file**, so a reordered seam and
   a reordered handler agree through the gate. *Closed:* the expectation is
   `sorted(FillStep, key=value)` off the IMPORTED enum.
5. **The cap returns a constant**, so ARM CAP's arithmetic holds for every input.
   *Closed twice, and neither closure is a PASS:* the three drives at three
   distances must not all admit the same count — that disagreement is a DEFECT
   naming both distances — and `MIN_DISTINCT_CAP_ANSWERS` additionally refuses a
   run that reached fewer than two answers, so a drive that collapsed to one
   question cannot certify either.
6. **`filled == requested` everywhere**, so ARM PARTIAL cannot tell the filled size
   from the requested one and a handler arming against the requested size passes.
   *Closed:* `_population_defect` requires at least `MIN_PARTIAL_ORDERS` orders
   whose filled quantity is strictly below their requested quantity, and the
   published size is compared against the FILLED figure specifically.
7. **`isinstance` against a `runtime_checkable` Protocol passes on method NAMES
   alone**, so a class whose parameters have drifted satisfies the port and fails
   at the call. *Closed:* `_signature_defect` compares parameter names in order,
   and the pairs are REQUIRED rather than floored — a missing class is a defect
   naming it, never a silently shorter loop.
8. **A subject that raises is reported as a broken instrument**, hiding a real
   defect behind CANNOT_MEASURE. *Closed for the DRIVES, and the limit is stated
   exactly rather than generously:* `_run_drive` and `_run_alts` are guarded, and
   an unexpected exception inside either is a FINDING naming the exception,
   because these are drives the module is required to absorb (§18's
   shared-namespace rule). **The individual arms are NOT separately guarded** — an
   exception raised inside an arm reaches `run`'s outer handler and becomes
   CANNOT_MEASURE, which is a statement about this instrument rather than about
   the subject. That is a real residual, not a closure, and it is written here
   rather than claimed away; `check_origin_write` carries a per-arm `_guarded`
   wrapper and this gate does not.

9. **A defect flattens a tallied figure and the floor answers first**, so a
   violation the gate measured is reported as one it could not measure. *Closed,
   and MEASURED rather than reasoned:* five controls in
   `scripts/tests/test_check_fill_handler.py` reached CANNOT_MEASURE this way
   before `run` was reordered to report defects BEFORE floors. A floor exists to
   stop a vacuous PASS, never to suppress an observed violation.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# C0302 (too-many-lines): over the default, and the excess is DOCSTRING — the
# eight arms' reasoning, the standing question with its eight named closures, and
# the per-constant notes saying why each expected value is derived rather than
# typed. `nix_check_contract.md` §4.2 requires the check be one runnable file and
# §5.5 makes one gate own one property, so splitting it would move the reasoning
# into a module the gate does not import.
# pylint: disable=too-many-lines,duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. Every subject is a module on disk that no check
#: produces, and the config the cap reads is a repository file.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS `nixrisk` and `nixalloc` out of `ctx.nix_home`, so it mutates
#: `sys.path` and `sys.modules` for the duration and restores both. Check contract
#: v2 rule 12 checks declared claims against OBSERVED ones; `()` here would be the
#: falsifiable-and-false declaration that rule exists to catch.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep. Arithmetic over dictionaries and two AST parses.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for a fill path that arms no stop, releases no reservation, or "
    "publishes a distance the arm did not produce is a change to the motion §3 "
    "and §4 require to be atomic, decided by a human against the frozen spec. An "
    "instrument empowered to edit the handler until its own drive came back "
    "clean would be manufacturing its own green over the exact hole D3.178 "
    "exists because nobody noticed: a mechanism that was landed and never called."
)
#: Genuinely MEASURED here: both modules are imported out of the tree under test
#: and DRIVEN — a real `ExecutionReport` through the real handler, over the
#: shipped stop book, execution ledger, reservation ledger and picture book. The
#: seam, the writer, the caps module and the broker seam are READ; each has its
#: own gate.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/fills.py",
    "scripts/nixrisk/join.py",
)

NAME = "check_fill_handler"

HANDLER = "scripts/nixrisk/fills.py"
JOIN = "scripts/nixrisk/join.py"
#: ARM CONFORMANCE's reference side for the sink, and a DIFFERENT file on purpose:
#: `broker_seam.py` is the §2A contract and this module cannot edit it in the same
#: motion, so an agreement between them is two hands rather than one.
BROKER_SEAM = "scripts/broker/broker_seam.py"
CAPS_CONFIG = "risks/allocator_caps.config.json"
ALLOC_CONFIG = "risks/allocator.config.json"

#: The dotted names imported out of the tree under test, each pinned to the path
#: it must resolve to. A name-based import against a `sys.path` the preamble has
#: already seeded with the REAL repository would measure the live tree whatever
#: `ctx.nix_home` said.
_MODULES: tuple[tuple[str, str], ...] = (
    ("nixrisk.fills", HANDLER),
    ("nixrisk.join", JOIN),
    ("nixrisk.fill_seam", "scripts/nixrisk/fill_seam.py"),
    ("nixrisk.seam", "scripts/nixrisk/seam.py"),
    ("nixrisk.stops", "scripts/nixrisk/stops.py"),
    ("nixrisk.positions", "scripts/nixrisk/positions.py"),
    ("nixrisk.picture", "scripts/nixrisk/picture.py"),
    ("nixrisk.execution", "scripts/nixrisk/execution.py"),
    ("nixrisk.reservations", "scripts/nixrisk/reservations.py"),
    ("nixalloc.caps", "scripts/nixalloc/caps.py"),
    ("nixalloc.seam", "scripts/nixalloc/seam.py"),
)

# --------------------------------------------------------------------------
# THE POPULATION. `(client_order_id, strategy_id, symbol, qty, stop_ticks,
# fill_price, filled_qty)`.
#
# * SYMBOLS ARE §7:498's BUCKET SYMBOLS. ES and NQ share the equities bucket on
#   purpose, so ARM CAP sums TWO same-bucket exposures and `sum([x]) == max([x])`
#   cannot hide a cap that compares against the largest member.
# * STOP DISTANCES ARE PAIRWISE DISTINCT, non-zero, and DISJOINT FROM THE
#   QUANTITIES — §7.12 note 3. A handler publishing `size` where the distance
#   belongs must not agree by coincidence.
# * TWO ORDERS ARE FILLED SHORT. §7.12 note 6: with `filled == requested`
#   everywhere, a handler that armed and sized against the REQUESTED quantity
#   would be indistinguishable from one that used the filled quantity.
# --------------------------------------------------------------------------
_ORDERS: tuple[tuple[str, str, str, int, int, float, int], ...] = (
    ("CO-1", "strat-es", "ES", 4, 13, 5000.00, 3),
    ("CO-2", "strat-nq", "NQ", 3, 41, 18000.00, 3),
    ("CO-3", "strat-cl", "CL", 2, 27, 70.00, 1),
    ("CO-4", "strat-gc", "GC", 5, 55, 2300.00, 5),
)

#: ARM ONCE's second execution: the order it re-fills, its exec id, this exec's
#: INCREMENT and the broker's new cumulative. `CO-1` filled 3 of 4; the cancel
#: lost the race and the last contract filled (§4 names this case outright).
#: Driven at a DIFFERENT price from the first fill so a silent re-arm moves the
#: stop's `anchor` and becomes visible.
_LATE_FILL = ("CO-1", "e2", 1, 4)
_LATE_PRICE = 5010.00

#: ARM CAP's further drives: the SAME symbol and the SAME requested and filled
#: sizes as `CO-1`, with only the stop distance moved. Each is driven through the
#: whole shipped fill path in its own rig, so the row the cap prices is a real
#: published row and not a hand-built one. TWO of them, not one: with a single
#: alternate the run observes exactly two cap answers and the floor below would
#: sit AT today's figure — the anchor doctrine C.4 rejects.
_ALT_ORDERS: tuple[tuple[str, str, str, int, int, float, int], ...] = (
    ("CO-9", "strat-es-a", "ES", 4, 89, 5000.00, 3),
    ("CO-8", "strat-es-b", "ES", 4, 31, 5000.00, 3),
)

#: Per-symbol tick SIZE (the price value of one tick — an instrument constant,
#: §12A boot-loaded) and margin per contract. Not the cap's `tick_value_usd`,
#: which is dollars per tick and is read from the repository's own config.
_TICKS = {"ES": 0.25, "NQ": 0.25, "CL": 0.01, "GC": 0.10}
_MARGIN = {"ES": 500.0, "NQ": 1000.0, "CL": 1700.0, "GC": 900.0}
_BALANCE = 250_000.0
_FRACTION = 0.70

#: ARM CAP's proposal: a fresh ES order measured against the bucket the drive
#: just filled. The distance is deliberately not one of `_ORDERS`'.
_PROPOSAL_SYMBOL = "ES"
_PROPOSAL_BUCKET = "equities"
_PROPOSAL_CONTRACTS = 5
_PROPOSAL_STOP_TICKS = 20

# --------------------------------------------------------------------------
# NON-VACUITY FLOORS (`debug.md` §7.12). Every one is STRICTLY BELOW today's
# figure and non-zero. Today the drive carries 4 trades, 4 full step sequences,
# 2 short-filled orders, 2 IOC cancels, 4 distinct distances, 4 conformance
# pairs and 2 distinct cap answers. Doctrine C.4: a threshold set to today's
# number is an anchor that moves and discriminates nothing before then.
# --------------------------------------------------------------------------

#: Trades published by the drive. One trade cannot expose a wrong join.
MIN_TRADES = 2
#: Fills whose FULL three-step sequence was observed. Two, because one sequence
#: cannot distinguish "the handler runs the steps in order" from "the handler ran
#: once and happened to".
MIN_FULL_SEQUENCES = 2
#: Orders whose filled quantity is strictly BELOW their requested quantity.
#: Without one, §4's partial-fill rule is never exercised at all.
MIN_PARTIAL_ORDERS = 1
#: IOC cancels observed at the recorder. Without one, the cancel half of §4's
#: one-fact remainder is an untested claim.
MIN_CANCELS = 1
#: Distinct stop distances in the population. Below this a wrong join publishes
#: the right number by luck.
MIN_DISTINCT_DISTANCES = 2
#: Class->port pairs held against the frozen Protocols with a signature compare.
#: Today 3 (the fourth pairing in `_CONFORMANCE` is one that must NOT hold, and
#: it is counted nowhere).
MIN_CONFORMANCE_PAIRS = 2
#: Distinct answers §7's cap gave across the three drives. Today 3. **ONE ANSWER
#: IS A NUMBER; SEVERAL ANSWERS AT SEVERAL DISTANCES IS PRICING** — a cap that
#: returns the same count whatever the stop distance is not consuming it.
MIN_DISTINCT_CAP_ANSWERS = 2


class Finding(NamedTuple):
    """One defect: WHERE it is and WHY it is wrong. Never a bare status (§18)."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The subjects and the collaborators, imported out of the tree under test."""

    fills: ModuleType
    join: ModuleType
    fill_seam: ModuleType
    seam: ModuleType
    stops: ModuleType
    positions: ModuleType
    picture: ModuleType
    execution: ModuleType
    reservations: ModuleType
    caps: ModuleType
    alloc_seam: ModuleType


@dataclass(frozen=True)
class Moment:
    """The world as it was at the instant step 2 ran, sampled from OUTSIDE.

    ARM ORDERING's whole evidence. `stop_armed` says step 1 had already happened;
    `commits` and `writes` say step 3 had not. Neither is a question put to the
    handler, which is what separates this from reading `FillOutcome.steps`.
    """

    client_order_id: str
    stop_armed: bool
    writes: int
    commits: int


@dataclass
class Tally:  # pylint: disable=too-many-instance-attributes
    """What the drive ACTUALLY did. Non-vacuity is read off this, never asserted."""

    trades: int = 0
    full_sequences: int = 0
    partial_orders: int = 0
    cancels: int = 0
    conformance_pairs: int = 0
    cap_answers: tuple[int, ...] = ()
    distinct_distances: int = 0
    cap_used: float = 0.0
    cap_contributors: int = 0
    steps_seen: tuple[str, ...] = ()
    disagreements: int = 0
    #: Verbs of `broker_seam.OrderEventSink` the shipped sink carries, and how
    #: many that Protocol declares. BOTH DERIVED — the wiring gap is the fact a
    #: reader of this green most needs, so it is measured, never typed.
    sink_verbs: int = 0
    seam_verbs: int = 0


# R0902 refused with a reason: fifteen attributes, and every one is a
# COLLABORATOR the shipped fill path was assembled from or an OBSERVATION the
# arms read. Dropping one to reach a threshold of seven would either remove a
# shipped component from the drive — making the drive less like production —
# or remove an observation from a verdict, and a gate that cannot say what it
# saw can only be believed. The threshold is about behavioural classes
# accreting state; this is a rig.
@dataclass
class Drive:  # pylint: disable=too-many-instance-attributes
    """One complete drive of the shipped fill path, plus everything it produced."""

    loaded: Loaded
    handler: Any = None
    sink: Any = None
    stops: Any = None
    book: Any = None
    writer: Any = None
    remainder: Any = None
    cancels: Any = None
    origins: Any = None
    approvals: Any = None
    reservations: Any = None
    #: `client_order_id -> FillOutcome` for the FIRST fill of each order.
    outcomes: dict[str, Any] = field(default_factory=dict)
    #: `client_order_id -> the stop book's answer BEFORE that order's first fill`.
    before: dict[str, Any] = field(default_factory=dict)
    moments: list[Moment] = field(default_factory=list)
    late: Any = None


def _cannot_measure(detail: str) -> CheckResult:
    """Doctrine B.2: an unread subject is CANNOT_MEASURE, never PASS."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ==========================================================================
# LOADING — the subject comes out of the tree under test, never out of this one
# ==========================================================================


def _purge(prefixes: tuple[str, ...]) -> None:
    """Drop already-imported first-party modules so `home` wins the import."""
    for name in [key for key in sys.modules if key.split(".")[0] in prefixes]:
        del sys.modules[name]


_PACKAGES = ("nixrisk", "nixalloc", "risk_config")


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import every module out of `home`, or say precisely why not.

    A path-keyed import is what lets a plant live on a `tmp_path` COPY (doctrine
    C.8): the gate drives whichever tree it is pointed at, and the production
    modules are never written.
    """
    for rel in (HANDLER, JOIN, BROKER_SEAM, CAPS_CONFIG, ALLOC_CONFIG):
        if not (home / rel).is_file():
            return None, (
                f"{rel}: no such file under {home} — the subject is unavailable, "
                "so nothing was measured (§17: never a PASS)"
            )
    saved_path = list(sys.path)
    saved_modules = dict(sys.modules)
    try:
        sys.path.insert(0, str((home / "scripts").resolve()))
        _purge(_PACKAGES)
        # A tree created after interpreter start is invisible to FileFinder's
        # directory-mtime cache, and the resulting ModuleNotFoundError would
        # report "the subject is unavailable" over a subject that is right there.
        importlib.invalidate_caches()
        modules: list[ModuleType] = []
        for dotted, rel in _MODULES:
            module = importlib.import_module(dotted)
            got = Path(getattr(module, "__file__", "") or "").resolve()
            want = (home / rel).resolve()
            if got != want:
                return None, (
                    f"{dotted} was imported from {got}, not from the {rel} this "
                    f"gate reports on ({want}) — the import fell through to "
                    "another tree (D3.124), so this gate measured something "
                    "other than what it names (§17: never a PASS)"
                )
            modules.append(module)
        return Loaded(*modules), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{HANDLER}: cannot import the fill path from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so nothing "
            "was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(_PACKAGES)
        sys.modules.update(saved_modules)


# ==========================================================================
# THE RIG — the shipped collaborators, assembled as production would
# ==========================================================================


class _Plane1:
    """§9's sink, recording. The reservation ledger REQUIRES one and refuses None."""

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        """Append; §11.6 makes this hot-path-safe and not durable."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Nothing to fsync in a drive."""
        return 0

    def pending(self) -> int:
        """Rows buffered."""
        return len(self.rows)


class _CancelRecorder:  # pylint: disable=too-few-public-methods
    """`fills.CancelPort`. THE ONE THING HERE THAT IS NOT SHIPPED CODE.

    It provably cannot be: the venue side is `broker_order_ibkr`'s IBKR adapter,
    which needs a live gateway, and §2A's `cancel_order` returns nothing — the
    result arrives asynchronously as an event. What the cancel does on the wire is
    that adapter's property and has its own gates; what this gate owns is WHETHER
    a cancel was issued, for WHICH order, and only when a remainder existed.
    """

    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def cancel_order(self, client_order_id: str) -> None:
        """Record the IOC cancel §4 requires for the unfilled remainder."""
        self.cancelled.append(client_order_id)


# R0903: both this and `_CancelRecorder` are SINGLE-VERB ports, and the
# narrowness is the declared property — `fills.CancelPort` has `cancel_order`
# and nothing else so a reservation path structurally cannot place an order.
# A second verb added to satisfy a threshold of two would widen exactly the
# surface `scripts/nixrisk/fills.py` narrowed on purpose.
class _OrderingRemainder:  # pylint: disable=too-few-public-methods
    """`RemainderPort` that DELEGATES to the shipped `IocRemainder` and observes.

    NOT a fake and not a stand-in: every quantity, every cancel and every returned
    Σ comes from the real component. What this wrapper adds is a SAMPLE of the
    world taken at the instant step 2 is entered, which is the only place from
    which steps 1 and 3 can be bracketed without asking the handler what it did.
    """

    def __init__(self, inner: Any, drive: Drive) -> None:
        self._inner = inner
        self._drive = drive

    def release_remainder(
        self, client_order_id: str, *, filled_qty: int, requested_qty: int
    ) -> float:
        """Sample, then delegate. The delegation is the whole behaviour."""
        self._drive.moments.append(
            Moment(
                client_order_id=client_order_id,
                stop_armed=self._drive.stops.get(client_order_id) is not None,
                writes=int(self._drive.writer.writes),
                commits=int(self._drive.book.commits),
            )
        )
        return self._inner.release_remainder(
            client_order_id, filled_qty=filled_qty, requested_qty=requested_qty
        )


def _clock() -> Any:
    """A deterministic monotonic clock. §9 rows need a timestamp; drives need it fixed."""
    state = {"t": 1000.0}

    def now() -> float:
        state["t"] += 1.0
        return state["t"]

    return now


def _order(loaded: Loaded, row: tuple[Any, ...]) -> Any:
    """One `ProposedOrder` from a population row. LONG throughout — see §7.12/6.

    Direction is not this gate's subject (`check_execution_ledger` owns the sign
    convention and `check_origin_write` drives both), and holding it constant
    keeps the filled-vs-requested comparison the one thing moving.
    """
    seam = loaded.seam
    coid, strategy, symbol, qty, stop_ticks, _price, _filled = row
    return seam.ProposedOrder(
        client_order_id=coid,
        strategy_id=strategy,
        symbol=symbol,
        side=seam.Side.LONG,
        qty=qty,
        margin_per_contract=_MARGIN[symbol],
        stop_ticks=stop_ticks,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1000.0,
    )


def _build(loaded: Loaded) -> Drive:
    """Assemble the whole shipped fill path exactly as production wiring would."""
    drive = Drive(loaded=loaded)
    drive.book = loaded.picture.FinancialPictureBook(
        balance=_BALANCE,
        deployable_fraction=_FRACTION,
        margin_per_contract=_MARGIN,
    )
    ledger = loaded.execution.ExecutionLedger()
    drive.stops = loaded.stops.StopBook(_TICKS)
    # THE PRODUCTION JOIN, not the degenerate one: `production_origins` refuses an
    # identity mint, so every published `trade_id` here is genuinely distinct from
    # its `client_order_id` and ARM CAUSATION's key comparison is not vacuous.
    drive.origins = loaded.join.production_origins()
    drive.approvals = loaded.fills.ApprovedOrderBook()
    drive.writer = loaded.positions.PositionOriginWriter(
        picture=drive.book,
        ledger=ledger,
        stops=drive.stops,
        origins=drive.origins,
    )
    drive.cancels = _CancelRecorder()
    clock = _clock()
    drive.reservations = loaded.reservations.ReservationLedger(_Plane1())
    drive.remainder = loaded.fills.IocRemainder(
        reservations=drive.reservations,
        cancels=drive.cancels,
        clock=clock,
    )
    drive.handler = loaded.fills.FillHandler(
        orders=drive.approvals,
        stops=drive.stops,
        remainder=_OrderingRemainder(drive.remainder, drive),
        writer=drive.writer,
    )
    drive.sink = loaded.fills.LimiterFillSink(
        handler=drive.handler, orders=drive.approvals, clock=clock
    )
    return drive


def _approve(drive: Drive, row: tuple[Any, ...]) -> None:
    """Approval: hold the order, record the join, take the reservation.

    Everything the Limiter does BEFORE a fill, and nothing it does after. No stop
    is armed here — that is the whole subject, and a gate that armed it would be
    re-proving ARC 029's mechanism instead of proving a fill calls it.
    """
    order = _order(drive.loaded, row)
    drive.approvals.record(order)
    drive.origins.record(order)
    drive.reservations.take(order, 1000.0)


def _feed(drive: Drive, row: tuple[Any, ...], *, exec_id: str = "e1") -> None:
    """One §2A broker fill event, through the SINK — the production entry point.

    Driven through `LimiterFillSink` rather than `FillHandler.on_fill` directly,
    because the sink is the surface a broker adapter would call and the conversion
    it performs (§2A carries no SIDE) is part of the path under judgement.
    """
    coid, _strategy, symbol, _qty, _stop, price, filled = row
    drive.before[coid] = drive.stops.get(coid)
    drive.sink.on_fill(coid, exec_id, symbol, filled, price, filled)
    drive.outcomes[coid] = drive.sink.outcomes()[-1]


def _run_drive(loaded: Loaded) -> tuple[Drive | None, Finding | None]:
    """Approve, fill, and re-fill. An unexpected raise is a FINDING, not a crash.

    §7.12 note 8: these are drives the module is REQUIRED to absorb, so an
    exception here is a statement about the subject and it is reported as one —
    naming the exception, per check contract v2 §11 (assert the REASON).
    """
    drive = _build(loaded)
    try:
        for row in _ORDERS:
            _approve(drive, row)
            _feed(drive, row)
        coid, exec_id, increment, cumulative = _LATE_FILL
        drive.sink.on_fill(coid, exec_id, "ES", increment, _LATE_PRICE, cumulative)
        drive.late = drive.sink.outcomes()[-1]
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, Finding(
            f"{HANDLER}:FillHandler.on_fill",
            (
                f"driving the shipped fill path raised {type(exc).__name__}: {exc}. "
                "A confirmed fill over an approved order with a taken reservation "
                "is the ordinary case §4 describes, so refusing it is a defect in "
                "the subject and not a limit of this instrument"
            ),
        )
    return drive, None


# ==========================================================================
# PRE-FLIGHT — this instrument's OWN credibility, before any verdict
# ==========================================================================


def _alt_distances() -> set[int]:
    """The stop distances ARM CAP's alternate drives use. Derived, never typed."""
    return {row[4] for row in _ALT_ORDERS}


def _population_defect() -> str:
    """A degenerate population agrees with anything. Refuse before measuring."""
    distances = [row[4] for row in _ORDERS]
    quantities = {row[3] for row in _ORDERS}
    shorts = [row for row in _ORDERS if row[6] < row[3]]
    complaints = (
        (
            len(_ORDERS) < MIN_TRADES,
            (
                f"{len(_ORDERS)} order(s), below the floor of {MIN_TRADES} — one "
                "trade cannot expose a wrong join, because any join maps the "
                "only row to the only stop"
            ),
        ),
        (
            any(distance <= 0 for distance in distances),
            (
                f"a stop distance of {min(distances, default=0)!r} would let a "
                "handler publishing ZERO — D3.136's fail-open, which prices a "
                "real position at zero dollar risk and makes the bucket ADMIT "
                "MORE — agree with this gate's reference"
            ),
        ),
        (
            len(set(distances)) != len(distances),
            (
                f"two orders share a stop distance {sorted(distances)} — a "
                "handler that armed the WRONG order's stop would publish the "
                "right number by luck and this gate would see agreement"
            ),
        ),
        (
            len(set(distances)) < MIN_DISTINCT_DISTANCES,
            (
                f"{len(set(distances))} distinct distance(s), below the floor "
                f"of {MIN_DISTINCT_DISTANCES}"
            ),
        ),
        (
            bool(set(distances) & quantities),
            (
                "a stop distance coincides with a quantity "
                f"({sorted(set(distances) & quantities)}) — a handler "
                "publishing `size` where the distance belongs would agree by "
                "coincidence"
            ),
        ),
        (
            len(shorts) < MIN_PARTIAL_ORDERS,
            (
                f"{len(shorts)} order(s) filled SHORT, below the floor of "
                f"{MIN_PARTIAL_ORDERS} — with filled == requested everywhere, a "
                "handler that sized and armed against the REQUESTED quantity is "
                "indistinguishable from one that used the filled quantity (§4)"
            ),
        ),
        (
            bool(_alt_distances() & set(distances)),
            (
                "an alternate drive reuses a stop distance from the main "
                f"population ({sorted(_alt_distances() & set(distances))}) — the "
                "cap answers could then coincide legitimately and prove nothing "
                "about pricing"
            ),
        ),
        (
            len(_alt_distances()) < len(_ALT_ORDERS),
            (
                "two alternate drives share a stop distance "
                f"{sorted(row[4] for row in _ALT_ORDERS)}, so they can only ever "
                "produce one cap answer between them"
            ),
        ),
    )
    for failed, why in complaints:
        if failed:
            return f"{HANDLER}: {why}"
    return ""


def _reference_terms(loaded: Loaded, home: Path) -> tuple[Any, str]:
    """§7's cap config, loaded from the repository's own files. Broken ⇒ refuse.

    Read through `caps.load_cap_config` rather than re-parsed here, because the
    §12A knob's ONE physical home is `risks/allocator.config.json` and a second
    reader in this gate would be a second home for the ceiling percentage. The
    ARITHMETIC is still this gate's — see `_expected_dollar_risk`.
    """
    try:
        return loaded.caps.load_cap_config(home), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{CAPS_CONFIG}: this gate's reference cap terms could not be "
            f"loaded — {type(exc).__name__}: {exc}. With no independent ceiling "
            "and no tick values, ARM CAP would be a verdict about this "
            "instrument and not about the fill path (§17: never a PASS)"
        )


def _expected_dollar_risk(
    config: Any, symbol: str, stop_ticks: int, size: int
) -> float:
    """§7:501, TRANSCRIBED HERE: `(stop_ticks + slippage_pad) × tick_value × contracts`.

    Written out in this file rather than obtained from `nixalloc.caps`, so ARM
    CAP's expected side and its subject side are two pieces of arithmetic. The
    numbers come from the repository's config because §12A gives them exactly one
    home; the FORMULA is the frozen sentence, typed here.
    """
    pad = float(config.slippage_pad_ticks[symbol])
    tick_value = float(config.tick_value_usd[symbol])
    return (float(stop_ticks) + pad) * tick_value * float(size)


# ==========================================================================
# ARM SEQUENCE — the steps the handler REALLY ran, in the seam's own order
# ==========================================================================


def _expected_order(loaded: Loaded) -> tuple[str, ...]:
    """The seam's `FillStep` order, READ OFF THE IMPORTED ENUM. Never typed here."""
    step = loaded.fill_seam.FillStep
    return tuple(member.name for member in sorted(step, key=lambda m: m.value))


def sequence_defects(drive: Drive, expected: tuple[str, ...]) -> list[Finding]:
    """Every first fill ran ALL of the seam's steps, in the seam's own order."""
    defects: list[Finding] = []
    for coid, outcome in sorted(drive.outcomes.items()):
        observed = tuple(step.name for step in outcome.steps)
        values = [int(step.value) for step in outcome.steps]
        if observed != expected:
            defects.append(
                Finding(
                    f"{HANDLER}:FillHandler.on_fill[{coid}]",
                    f"recorded steps {list(observed)}, but the seam's FillStep "
                    f"order is {list(expected)}. The order is the safety "
                    "property: the arm must precede the write because the origin "
                    "writer REFUSES a fill with no armed stop, and the release "
                    "must precede the write because §4 requires the published "
                    "snapshot to carry the unfilled portion ALREADY released, "
                    "'not on a delay'",
                )
            )
        if values != sorted(values):
            defects.append(
                Finding(
                    f"{HANDLER}:FillHandler.on_fill[{coid}]",
                    f"recorded step values {values} are not increasing — "
                    "FillStep is an IntEnum precisely so the sequence can be "
                    "asserted over what RAN rather than over source order",
                )
            )
    return defects


# ==========================================================================
# ARM ORDERING — the same order, observed from OUTSIDE the handler
# ==========================================================================


def ordering_defects(drive: Drive) -> list[Finding]:
    """At the instant step 2 ran: step 1 HAD happened and step 3 had NOT."""
    defects: list[Finding] = []
    for published, moment in enumerate(drive.moments):
        if not moment.stop_armed:
            defects.append(
                Finding(
                    f"{HANDLER}:FillHandler.on_fill[{moment.client_order_id}]",
                    "the remainder was released while the stop book still held "
                    "NO stop for this order, so step 1 had not run when step 2 "
                    "did. Stated in the right direction: the origin write's OWN "
                    "refusal is what prevents a defaulted distance; this ORDER "
                    "is what prevents the refusal. Without the arm first the "
                    "fill is booked in §4's ledger and ABSENT from §3's "
                    "published table, which is the `unbucketed` door D3.136 "
                    "found while closing the fail-open — a position nothing "
                    "prices admits more just as surely as one priced at zero",
                )
            )
        if moment.writes != published or moment.commits != published:
            defects.append(
                Finding(
                    f"{HANDLER}:FillHandler.on_fill[{moment.client_order_id}]",
                    f"at the instant the remainder was released the writer had "
                    f"published {moment.writes} row(s) and the picture book had "
                    f"committed {moment.commits} time(s), against "
                    f"{published} expected — step 3 ran before step 2, so the "
                    "published snapshot carried a reservation §4 requires to "
                    "have been released already",
                )
            )
    return defects


# ==========================================================================
# ARM CAUSATION — the fill ARMED the stop, and the row carries THAT distance
# ==========================================================================


def causation_defects(drive: Drive) -> list[Finding]:
    """Not armed before, armed after, and the published distance is the armed one."""
    defects: list[Finding] = []
    for row in _ORDERS:
        coid, _strategy, _symbol, _qty, stop_ticks, _price, _filled = row
        site = f"{HANDLER}:FillHandler.on_fill[{coid}]"
        if drive.before.get(coid) is not None:
            defects.append(
                Finding(
                    site,
                    "the stop book already held a stop for this order BEFORE the "
                    "fill was delivered, so nothing here shows the fill armed "
                    "anything — this gate would be re-proving ARC 029's "
                    "mechanism instead of proving a fill CALLS it",
                )
            )
            continue
        defects += _armed_defects(drive, coid, stop_ticks, site)
    return defects


def _armed_defects(
    drive: Drive, coid: str, stop_ticks: int, site: str
) -> list[Finding]:
    """The three post-fill facts, per trade. Split out to keep the arm linear."""
    defects: list[Finding] = []
    live = drive.stops.get(coid)
    if live is None:
        return [
            Finding(
                site,
                "the fill was handled and the stop book STILL holds no stop for "
                "this order — §4 converts the GO's tick distance to an absolute "
                "price at the confirmed fill, and nothing did",
            )
        ]
    outcome = drive.outcomes[coid]
    if int(live.initial_distance_ticks) != stop_ticks:
        defects.append(
            Finding(
                site,
                f"the armed stop records {live.initial_distance_ticks} tick(s) "
                f"against the approved order's stop_ticks={stop_ticks} — §7:476 "
                "sizes the position against that distance, so an arm against any "
                "other number protects a position sized for a different one",
            )
        )
    published = int(outcome.write.row.stop_distance)
    if published != int(live.initial_distance_ticks):
        defects.append(
            Finding(
                site,
                f"the published row carries stop_distance={published} while the "
                f"stop this fill armed records "
                f"{live.initial_distance_ticks} — §7:501 prices correlation "
                "bucket exposure from the published figure, and a figure the "
                "arm did not produce is a number the cap cannot question",
            )
        )
    if outcome.write.row.trade_id == coid:
        defects.append(
            Finding(
                site,
                f"the published row is keyed by {outcome.write.row.trade_id!r}, "
                "which IS the client_order_id — D3.177's architect ruling keeps "
                "the two DISTINCT, and the production join was supposed to have "
                "made an identity mint unreachable",
            )
        )
    return defects


# ==========================================================================
# ARM PARTIAL — §4's partial-fill rule, with filled DRIVEN APART from requested
# ==========================================================================


def partial_defects(drive: Drive) -> list[Finding]:
    """Position = ACTUAL filled qty; the remainder cancelled; nothing else."""
    defects: list[Finding] = []
    for row in _ORDERS:
        coid, _strategy, _symbol, qty, _stop, _price, filled = row
        site = f"{HANDLER}:IocRemainder.release_remainder[{coid}]"
        outcome = drive.outcomes[coid]
        if int(outcome.filled_qty) != filled or int(outcome.requested_qty) != qty:
            defects.append(
                Finding(
                    site,
                    f"the outcome reports filled={outcome.filled_qty} of "
                    f"requested={outcome.requested_qty}, against {filled} of "
                    f"{qty} actually driven — §4 sets the position to the ACTUAL "
                    "filled quantity, and a handler measuring the requested one "
                    "silently over-states every partially-filled position",
                )
            )
        if abs(int(outcome.write.row.size)) != filled:
            defects.append(
                Finding(
                    site,
                    f"the published row carries size={outcome.write.row.size} "
                    f"for a fill of {filled} — §4: 'Limiter sets position = "
                    "actual filled qty'. §7:501 multiplies the contract count by "
                    "the dollar risk per contract, so an over-stated size "
                    "over-prices the bucket and an under-stated one ADMITS MORE",
                )
            )
        defects += _cancel_defects(drive, coid, qty, filled, site)
    return defects


def _cancel_defects(
    drive: Drive, coid: str, qty: int, filled: int, site: str
) -> list[Finding]:
    """A cancel exactly when a remainder existed, and never otherwise."""
    issued = drive.cancels.cancelled.count(coid)
    if filled < qty and issued == 0:
        return [
            Finding(
                site,
                f"{filled} of {qty} filled and NO IOC cancel was issued — §4 "
                "cancels the unfilled remainder, and a remainder left working at "
                "the venue can still fill against capital the Allocator has "
                "already been told is free",
            )
        ]
    if filled >= qty and issued:
        return [
            Finding(
                site,
                f"the order filled in full ({filled} of {qty}) and {issued} IOC "
                "cancel(s) were issued anyway — the count of cancels then stops "
                "being the count of partial fills, which is the figure an "
                "operator reads to see how often the system is filled short",
            )
        ]
    return []


# ==========================================================================
# ARM ONCE — a successive partial fill does NOT re-convert the stop (§4)
# ==========================================================================


def once_defects(drive: Drive) -> list[Finding]:
    """The stop is converted ONCE, at the FIRST confirmed fill, and stays anchored."""
    coid, _exec_id, _increment, cumulative = _LATE_FILL
    site = f"{HANDLER}:FillHandler.on_fill[{coid}/late]"
    first = drive.outcomes[coid]
    late = drive.late
    defects: list[Finding] = []
    if any(step.name == "ARM_STOP" for step in late.steps):
        defects.append(
            Finding(
                site,
                "a successive partial fill recorded ARM_STOP — §4 converts the "
                "distance to a price ONCE at the confirmed fill, and a second "
                "conversion would re-anchor a live stop against a later price. "
                "Recording a step that did not run also makes FillOutcome.steps "
                "a description of the source rather than of what ran",
            )
        )
    if late.armed is not first.armed:
        defects.append(
            Finding(
                site,
                "the late fill reports a DIFFERENT StopState object from the one "
                "the first fill armed, so the trade's protection is no longer "
                "the stop that was converted at its confirmed fill",
            )
        )
    live = drive.stops.get(coid)
    if live is not None and float(live.anchor) != float(_ORDERS[0][5]):
        defects.append(
            Finding(
                site,
                f"the stop's anchor is now {live.anchor} against the FIRST "
                f"fill's price {_ORDERS[0][5]} — the stop was silently "
                "re-converted against the later fill, which is exactly the "
                "double conversion `StopState.anchor` exists to make visible",
            )
        )
    if int(late.filled_qty) != cumulative:
        defects.append(
            Finding(
                site,
                f"after the late fill the position reads {late.filled_qty} "
                f"against a cumulative {cumulative} — §4's ledger derives "
                "position from the SET of unique fills, so a successive partial "
                "must update the row it already wrote, never replace its size "
                "with the last increment",
            )
        )
    return defects


# ==========================================================================
# ARM CAP — §7:501 prices the PUBLISHED row, and the answer MOVES with distance
# ==========================================================================


def _exposure(loaded: Loaded, row: Any) -> Any:
    """§7:511's contribution, built from a PUBLISHED row and nothing else."""
    return loaded.caps.Exposure(
        symbol=row.symbol,
        contracts=abs(int(row.size)),
        stop_ticks=int(row.stop_distance),
    )


def _admit(loaded: Loaded, config: Any, rows: list[Any]) -> Any:
    """§7's cap over a book of published rows. The REAL entry point, unwrapped."""
    return loaded.caps.admit(
        _PROPOSAL_SYMBOL,
        _PROPOSAL_CONTRACTS,
        _PROPOSAL_STOP_TICKS,
        [_exposure(loaded, row) for row in rows],
        _BALANCE,
        config,
    )


def cap_defects(
    drive: Drive, alts: list[Drive], config: Any, tally: Tally
) -> list[Finding]:
    """The cap prices the held book off the fill's own distance, and it MOVES."""
    loaded = drive.loaded
    equities = [drive.outcomes[coid].write.row for coid in ("CO-1", "CO-2")]
    decision = _admit(loaded, config, equities)
    tally.cap_used = float(decision.used_dollar_risk)
    tally.cap_contributors = int(decision.contributors)
    expected = sum(
        _expected_dollar_risk(
            config, row.symbol, int(row.stop_distance), abs(int(row.size))
        )
        for row in equities
    )
    defects = _cap_sum_defects(decision, expected, equities)
    # ONE symbol, ONE filled size, ONLY the stop distance moving — each row from
    # its own complete drive of the shipped fill path.
    priced = [(int(equities[0].stop_distance), _admit(loaded, config, [equities[0]]))]
    for alt, row in zip(alts, _ALT_ORDERS, strict=True):
        published = alt.outcomes[row[0]].write.row
        priced.append(
            (int(published.stop_distance), _admit(loaded, config, [published]))
        )
    tally.cap_answers = tuple(int(d.admitted_contracts) for _, d in priced)
    if len({answer for _, d in priced for answer in (int(d.admitted_contracts),)}) < 2:
        defects.append(
            Finding(
                f"{HANDLER}:nixalloc.caps.admit[{_PROPOSAL_SYMBOL}]",
                f"the cap admitted {tally.cap_answers} contract(s) for one held "
                f"{_PROPOSAL_SYMBOL} position of the same size at stop distances "
                f"{[ticks for ticks, _ in priced]} — an answer that does not move "
                "when the distance moves is not pricing the position at all, and "
                "D3.150's whole finding is that this field had no production "
                "source to move it",
            )
        )
    return defects


def _cap_sum_defects(decision: Any, expected: float, rows: list[Any]) -> list[Finding]:
    """§7:511 is a SUM over the bucket. Two contributors, or it proves nothing."""
    site = f"{HANDLER}:nixalloc.caps.admit[{_PROPOSAL_BUCKET}]"
    defects: list[Finding] = []
    if int(decision.contributors) != len(rows):
        defects.append(
            Finding(
                site,
                f"the cap summed {decision.contributors} exposure(s) over "
                f"{len(rows)} published same-bucket rows — with one contributor "
                "a SUM and a MAX are the same number, so a cap comparing against "
                "the largest member would be invisible (§13 V35:949)",
            )
        )
    if abs(float(decision.used_dollar_risk) - expected) > 1e-9:
        defects.append(
            Finding(
                site,
                f"the cap priced the held book at {decision.used_dollar_risk}, "
                f"against {expected} from §7:501's formula applied to the "
                "PUBLISHED rows — the distance the fill armed is not the "
                "distance the cap is consuming",
            )
        )
    if float(decision.used_dollar_risk) <= 0.0:
        defects.append(
            Finding(
                site,
                "the cap priced the held book at zero dollar risk — a bucket "
                "that reads empty ADMITS MORE, which is D3.136's fail-open under "
                "a new spelling and the exact consequence of an unpopulated "
                "stop_distance",
            )
        )
    return defects


# ==========================================================================
# ARM CONFORMANCE — the shipped classes satisfy the FROZEN ports, signatures too
# ==========================================================================

#: `(frozen port, the DRIVE attribute holding the constructed object, the class's
#: own name, why this pair)`. A CONSTANT here, unlike the step order: the seam
#: names its satisfying classes only in prose, and deriving the pairing from prose
#: would let a docstring edit retarget the gate at whatever class happens to fit.
#: The pairing is the ARCHITECTURAL claim, so changing it is a diff on the
#: instrument. **The objects held against the ports are the ones the drive
#: actually used**, not classes constructed for the comparison.
_CONFORMANCE: tuple[tuple[str, str, str, str], ...] = (
    (
        "FillHandlerPort",
        "handler",
        "FillHandler",
        "the caller D3.178 said was missing",
    ),
    (
        "RemainderPort",
        "remainder",
        "IocRemainder",
        "§4's partial-fill remainder, cancel and release as ONE fact",
    ),
    (
        "ApprovedOrderPort",
        "approvals",
        "ApprovedOrderBook",
        "§7:476's sizer distance, which an execution report does not carry",
    ),
)

#: `(port, drive attribute)` pairings that must NOT hold. `StopArmPort` is the
#: handler's INPUT: a handler that also satisfied it could arm itself, and the
#: narrowing that keeps §4's single conversion inside the stop book would be a
#: convention again. Asserted from the other side, because a narrowing nothing
#: tests for absence is a narrowing nobody would notice widening.
_MUST_NOT_SATISFY: tuple[tuple[str, str, str], ...] = (
    ("StopArmPort", "handler", "FillHandler"),
)


def _signature_defect(port_method: Any, real_method: Any) -> str:
    """Compare PARAMETER NAMES in order. The half `isinstance` cannot see.

    A `runtime_checkable` Protocol's `isinstance` compares METHOD NAMES ONLY —
    blind to arity, to parameter names and to every annotation — so a class whose
    parameters have drifted satisfies the Protocol and fails at the call. Extra
    parameters on the real method are allowed only when they are OPTIONAL,
    because an extra REQUIRED parameter is a call the port's caller cannot make.
    """
    want = list(inspect.signature(port_method).parameters.values())
    got = list(inspect.signature(real_method).parameters.values())
    want_names = [p.name for p in want]
    got_names = [p.name for p in got]
    if got_names[: len(want_names)] != want_names:
        return f"parameters {got_names} do not open with the port's {want_names}"
    extra = [p for p in got[len(want) :] if p.default is inspect.Parameter.empty]
    if extra:
        return (
            f"declares extra REQUIRED parameter(s) {[p.name for p in extra]} — "
            "a caller holding only the port cannot supply them"
        )
    return ""


def conformance_defects(drive: Drive, tally: Tally) -> list[Finding]:
    """Every shipped OBJECT held against its frozen port: isinstance AND signature."""
    defects: list[Finding] = []
    for port_name, attr, class_name, why in _CONFORMANCE:
        port = getattr(drive.loaded.fill_seam, port_name, None)
        obj = getattr(drive, attr, None)
        site = f"{HANDLER}:{class_name}->{port_name}"
        if port is None or obj is None:
            defects.append(
                Finding(site, f"{port_name} or {class_name} is absent — {why}")
            )
            continue
        tally.conformance_pairs += 1
        if not isinstance(obj, port):
            defects.append(
                Finding(
                    site,
                    f"the constructed {class_name} does not satisfy {port_name} "
                    f"— {why}, and a caller holding only the port cannot call it",
                )
            )
            continue
        # `__protocol_attrs__` is the verb roster CPython derives for a Protocol,
        # so the roster is the PORT's and never a list typed in this file.
        for verb in sorted(port.__protocol_attrs__):
            complaint = _signature_defect(getattr(port, verb), getattr(type(obj), verb))
            if complaint:
                defects.append(Finding(f"{site}.{verb}", complaint))
    defects += _forbidden_defects(drive)
    return defects


def _forbidden_defects(drive: Drive) -> list[Finding]:
    """Pairings that must NOT hold. The narrowing, asserted from the other side."""
    defects: list[Finding] = []
    for port_name, attr, class_name in _MUST_NOT_SATISFY:
        port = getattr(drive.loaded.fill_seam, port_name, None)
        obj = getattr(drive, attr, None)
        if port is None or obj is None or not isinstance(obj, port):
            continue
        defects.append(
            Finding(
                f"{HANDLER}:{class_name}->{port_name}",
                f"the constructed {class_name} SATISFIES {port_name}, which it "
                "consumes — a handler that also satisfies the arming port can "
                "arm itself, and §4's single conversion at the confirmed fill "
                "stops being enforced by the one component that owns the stop "
                "book",
            )
        )
    return defects


def _seam_sink_params(home: Path) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """`OrderEventSink.on_fill`'s parameter names, parsed out of the broker seam.

    A DIFFERENT FILE, and that is the point: `scripts/broker/broker_seam.py` is
    §2A's locked contract, this gate's subject cannot edit it in the same motion,
    so an agreement between the sink and the event shape is two hands rather than
    one. Parsed by AST rather than imported because importing the broker seam
    pulls a vendor-adjacent module into a risk-path gate for no gain.
    """
    try:
        tree = ast.parse((home / BROKER_SEAM).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return (), (), f"{BROKER_SEAM}: does not parse ({type(exc).__name__}: {exc})"
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "OrderEventSink":
            continue
        roster = tuple(
            verb.name for verb in node.body if isinstance(verb, ast.FunctionDef)
        )
        for verb in node.body:
            if isinstance(verb, ast.FunctionDef) and verb.name == "on_fill":
                return tuple(arg.arg for arg in verb.args.args), roster, ""
    return (
        (),
        (),
        (
            f"{BROKER_SEAM}: OrderEventSink.on_fill was not found — §2A's fill "
            "event is the shape the sink exists to consume, and without it this "
            "gate has no reference side for the production entry point"
        ),
    )


def sink_defects(loaded: Loaded, home: Path, tally: Tally) -> tuple[list[Finding], str]:
    """`LimiterFillSink.on_fill` carries §2A's own event shape, name for name.

    Also COUNTS how many of `OrderEventSink`'s verbs the sink carries, and that
    count is DERIVED from the broker seam rather than written down. The wiring gap
    — a minority of the declared verbs — is the single most important thing a
    reader of this gate's green must not misread, and a hand-typed fraction
    would be a restatement of a mutable fact that goes stale the day the Limiter's
    event handler grows its second verb (directive 3).
    """
    want, roster, refusal = _seam_sink_params(home)
    if refusal:
        return [], refusal
    sink = getattr(loaded.fills, "LimiterFillSink", None)
    if sink is None:
        return [
            Finding(
                f"{HANDLER}:LimiterFillSink",
                "absent — nothing converts §2A's on_fill event into an "
                "ExecutionReport, so the handler has no surface a broker adapter "
                "could ever reach",
            )
        ], ""
    tally.sink_verbs = sum(1 for verb in roster if hasattr(sink, verb))
    tally.seam_verbs = len(roster)
    got = tuple(inspect.signature(sink.on_fill).parameters)
    if got != want:
        return [
            Finding(
                f"{HANDLER}:LimiterFillSink.on_fill",
                f"takes {list(got)} against §2A's declared {list(want)} in "
                f"{BROKER_SEAM} — a sink whose shape differs from the event the "
                "broker adapter pushes cannot be wired to it at all, which is "
                "D3.178's defect one layer out",
            )
        ], ""
    return [], ""


# ==========================================================================
# ARM REFUSAL — an unapproved fill is refused LOUDLY, by both surfaces
# ==========================================================================


def refusal_defects(drive: Drive) -> list[Finding]:
    """A fill with no approval has no distance to convert. Refuse, and say so."""
    loaded = drive.loaded
    report = loaded.execution.ExecutionReport(
        order_id="CO-NEVER-APPROVED",
        exec_id="e1",
        symbol="ES",
        side=loaded.execution.FillSide.BUY,
        filled_qty=1,
        price=5000.0,
        cumulative_qty=1,
        ts=2000.0,
    )
    defects = _refuses(
        lambda: drive.handler.on_fill(report),
        f"{HANDLER}:FillHandler.on_fill[unapproved]",
        "CO-NEVER-APPROVED",
    )
    defects += _refuses(
        lambda: drive.sink.on_fill("CO-NEVER-APPROVED", "e2", "ES", 1, 5000.0, 1),
        f"{HANDLER}:LimiterFillSink.on_fill[unapproved]",
        "CO-NEVER-APPROVED",
    )
    return defects


def _refuses(drive_it: Any, site: str, must_name: str) -> list[Finding]:
    """Run a call that MUST raise, and require the message to NAME the subject.

    Check contract v2 §11: every can-fail control asserts the REASON, never the
    exception type alone. An `UnapprovedFill` that named nothing would be
    indistinguishable from one raised for a different order.
    """
    try:
        drive_it()
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        if must_name in str(exc):
            return []
        return [
            Finding(
                site,
                f"refused with {type(exc).__name__}: {exc} — the refusal does "
                f"not name {must_name!r}, so an operator cannot tell WHICH fill "
                "was refused from the message alone",
            )
        ]
    return [
        Finding(
            site,
            "a fill for an order this Limiter never approved was ACCEPTED — "
            "there is no stop_ticks to convert (§7:476 sizes against the "
            "approved distance) and no requested size to measure §4's remainder "
            "against, so whatever it published was reconstructed from the fill",
        )
    ]


# ==========================================================================
# THE VERDICT
# ==========================================================================


def _floor_refusal(tally: Tally) -> CheckResult | None:
    """`debug.md` §7.12: a run that reached nothing reports so, never PASS."""
    floors = (
        (tally.trades, MIN_TRADES, "trade(s) published by the drive"),
        (tally.full_sequences, MIN_FULL_SEQUENCES, "full three-step sequence(s)"),
        (tally.partial_orders, MIN_PARTIAL_ORDERS, "order(s) filled SHORT"),
        (tally.cancels, MIN_CANCELS, "IOC cancel(s) observed"),
        (tally.conformance_pairs, MIN_CONFORMANCE_PAIRS, "class->port pair(s) driven"),
        (
            len(set(tally.cap_answers)),
            MIN_DISTINCT_CAP_ANSWERS,
            "distinct cap answer(s) across two stop distances",
        ),
    )
    for observed, floor, what in floors:
        if observed < floor:
            return _cannot_measure(
                f"{HANDLER}: the drive produced {observed} {what}, below the "
                f"floor of {floor}. A drive that reached this little cannot "
                "discriminate a working fill path from a handler that raised on "
                "everything (§5.3: an empty scope is never a PASS)"
            )
    return None


def _evidence(tally: Tally) -> str:
    """Every figure this run actually observed. Never a restatement."""
    return (
        f"drove {tally.trades} confirmed fill(s) through the SHIPPED "
        f"LimiterFillSink -> FillHandler; steps observed per first fill "
        f"[{', '.join(tally.steps_seen) or 'none'}]; "
        f"{tally.full_sequences} full three-step sequence(s); "
        f"{tally.partial_orders} order(s) filled SHORT with {tally.cancels} IOC "
        f"cancel(s); {tally.distinct_distances} distinct stop distance(s), each "
        f"armed BY the fill and republished on §3's row; §7:501 priced "
        f"{tally.cap_contributors} same-bucket published row(s) at "
        f"{tally.cap_used:.4f} dollar risk and admitted "
        f"{list(tally.cap_answers)} contract(s) across {len(tally.cap_answers)} "
        f"stop distance(s) each driven through the whole fill path; "
        f"{tally.conformance_pairs} class->port pair(s) held against the frozen "
        f"Protocols with a parameter-name comparison; "
        f"{tally.disagreements} venue-vs-ledger cumulative disagreement(s). "
        "UNBOUND: nothing here proves a live broker event reaches this handler — "
        f"LimiterFillSink carries {tally.sink_verbs} of "
        f"{BROKER_SEAM}'s OrderEventSink's {tally.seam_verbs} verb(s), so it "
        "cannot yet be handed to the IBKR adapter and NO live fill flows"
    )


def _fill_tally(drive: Drive, expected: tuple[str, ...], tally: Tally) -> None:
    """Read the drive's own figures off the drive. Never off this file's tables."""
    tally.trades = len(drive.book.current().positions)
    tally.full_sequences = sum(
        1
        for outcome in drive.outcomes.values()
        if tuple(step.name for step in outcome.steps) == expected
    )
    tally.partial_orders = sum(
        1 for row in _ORDERS if int(drive.outcomes[row[0]].filled_qty) < row[3]
    )
    tally.cancels = len(drive.cancels.cancelled)
    tally.distinct_distances = len(
        {int(outcome.write.row.stop_distance) for outcome in drive.outcomes.values()}
    )
    tally.steps_seen = tuple(
        sorted(
            {
                "+".join(step.name for step in outcome.steps)
                for outcome in drive.outcomes.values()
            }
        )
    )
    tally.disagreements = len(drive.handler.disagreements())


# R0911 refused with a reason: SEVEN returns, and six of them are the distinct
# ways this gate can fail to reach a measurement — a degenerate population, an
# unimportable subject, unloadable reference terms, a raising main drive, a
# raising alternate drive and an unreadable broker seam. Each carries its own
# reason string, which check contract v2 §11 requires; collapsing them behind
# one exit would either lose the reason or hide it in a flag a caller has to
# decode. `debug.md` §7.12 asks what would make this gate pass while measuring
# nothing, and every one of these returns is an answer to it.
def _measure(  # pylint: disable=too-many-return-statements
    home: Path,
) -> tuple[list[Finding], Tally | None, str]:
    """Run every arm. Returns `(defects, tally, refusal_detail)`."""
    population = _population_defect()
    if population:
        return [], None, population
    loaded, complaint = load(home)
    if loaded is None:
        return [], None, complaint
    config, refusal = _reference_terms(loaded, home)
    if config is None:
        return [], None, refusal
    drive, finding = _run_drive(loaded)
    if drive is None:
        return [finding] if finding else [], None, ""
    alts, alt_finding = _run_alts(loaded)
    if alts is None:
        return [alt_finding] if alt_finding else [], None, ""
    expected = _expected_order(loaded)
    tally = Tally()
    _fill_tally(drive, expected, tally)
    defects = sequence_defects(drive, expected)
    defects += ordering_defects(drive)
    defects += causation_defects(drive)
    defects += partial_defects(drive)
    defects += once_defects(drive)
    defects += cap_defects(drive, alts, config, tally)
    defects += conformance_defects(drive, tally)
    sink_errs, sink_refusal = sink_defects(loaded, home, tally)
    if sink_refusal:
        return [], None, sink_refusal
    defects += sink_errs
    defects += refusal_defects(drive)
    return defects, tally, ""


def _run_alts(loaded: Loaded) -> tuple[list[Drive] | None, Finding | None]:
    """ARM CAP's further drives: same symbol, same sizes, DIFFERENT distances.

    A fresh rig per alternate, because a stop is armed once per order and a
    picture book already holding the first drive's rows would make the cap's
    input a mixture rather than one row at one distance.
    """
    alts: list[Drive] = []
    for row in _ALT_ORDERS:
        alt = _build(loaded)
        try:
            _approve(alt, row)
            _feed(alt, row)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return None, Finding(
                f"{HANDLER}:FillHandler.on_fill[{row[0]}]",
                f"the alternate drive at stop distance {row[4]} raised "
                f"{type(exc).__name__}: {exc}, so the cap could only be asked "
                "about the distances that did drive — and an answer that never "
                "moves is indistinguishable from pricing",
            )
        alts.append(alt)
    return alts, None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive a real fill and hold the whole motion against §3, §4 and §7."""
    try:
        defects, tally, refusal = _measure(ctx.nix_home)
        if tally is None and not defects:
            return _cannot_measure(
                refusal
                or f"{HANDLER}: neither a reading nor a refusal — a gate's own "
                "pre-flight returning nothing is never a verdict"
            )
        evidence = _evidence(tally) if tally is not None else ""
        # DEFECTS BEFORE THE FLOOR, and the order is load-bearing. A floor exists
        # to stop a VACUOUS PASS, never to suppress a violation the run actually
        # observed: a defect that also drove a tallied figure to zero — a handler
        # that issues no IOC cancel drives `cancels` to zero, which is exactly the
        # §4 breach the arm caught — would otherwise be reported as "this gate
        # could not measure" when the gate measured it precisely. MEASURED: five
        # controls in this file's own suite reached CANNOT_MEASURE that way before
        # this order was fixed. Fail > Cannot-measure in the aggregate for the
        # same reason.
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        if tally is not None:
            floor = _floor_refusal(tally)
            if floor is not None:
                return floor
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
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
