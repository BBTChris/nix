#!/usr/bin/env python3
"""Position is a function of the SET of unique `(order_id, exec_id)` fills.

ONE gate, ONE property (`nix_check_contract.md` §5.5): §4's idempotency sentence
in `nics_risk_subsystem_spec_v1.3.md` — *"broker events are deduplicated by
(order_id, exec_id); position state derives from cumulative fills — immune to
duplicate or out-of-order execution reports"* — holds over the SHIPPED
`scripts/nixrisk/execution.py`, DRIVEN, out of the tree under judgement.

Discharges CHECK-DEBT **D3.144** by real per-artifact coverage, which is the
shape D3.120's discharge already modelled: the artifact leaves the
`gate_coverage_baseline.json` ratchet because a check NAMES it in `SUBJECTS` and
genuinely drives it, not because a new `CHECK-A<n>` exclusion was minted.

## THE FIVE ARMS, and why one arm cannot carry this property

* **ARM REFERENCE.** The in-order stream, against BOTH a hand-computed literal
  and this gate's own independent Σ over the unique-key set. A permutation arm
  that only proves "every arrival order agrees with every other" is vacuous if
  the agreed figure is wrong.
* **ARM IDEMPOTENCE.** Every report delivered TWICE. The derived position must
  be byte-identical to the reference and the unique-fill count unchanged. A
  ledger that forgot to deduplicate double-counts here and nowhere else.
* **ARM PERMUTATION.** Four deterministic reorderings, each PROVEN reordered
  before its result is trusted (index order differs from identity, inversion
  count above a floor, and a counted number of arrivals whose broker cumulative
  moves BACKWARDS inside one order — the literal out-of-order signature).
* **ARM CROSS-CHECK.** §4's independent audit: `Σ` of the increments this ledger
  holds against `max` of the broker's own `cumulative_qty`. Driven in BOTH
  directions — a complete order closes the gap, an order with one exec withheld
  reports the gap as exactly the missing quantity — and the position is checked
  to still reflect only what was SEEN, so the disagreement is surfaced rather
  than silently reconciled. `reconcile()` against §3's published rows is driven
  the same way, both halves.
* **ARM STRUCTURE.** The one thing the behavioural arms provably cannot see: a
  correctly-maintained running total is ALSO permutation-invariant and ALSO
  duplicate-immune, so no drive can separate it from the scan the module's own
  docstring calls load-bearing (*"`position()` reads that set directly (a scan),
  so the immunity is a property of the type, not a discipline a caller must
  keep"*). Read statically instead: `position` may read the keyed dedup store
  and nothing else, and the store is DERIVED from `ingest` rather than typed
  here.

## DOCTRINE C.9 — why this is not a second instrument, weakest reason first

`scripts/tests/test_execution.py` drives the same module hard, including
permutation-invariance under duplication. Three things separate the two, and the
honest ordering puts the thin one first:

1. `check_artifact_gate_coverage` counts `SUBJECTS` declarations and cannot see
   a test module. That is D3.138's argument in reverse and it is the WEAKEST of
   the three — coverage arithmetic is a reason to want a check, never a reason
   for one to exist.
2. **Different tree.** The suite drives the module resolved out of THIS
   repository at development time. This gate imports it out of `ctx.nix_home`
   and ASSERTS the provenance (D3.124), so it answers *is the tree this node is
   running correct* — a question `verify.py` can ask on a box whose runtime venv
   has no pytest at all, and which the suite therefore cannot ask there.
3. **Different properties.** ARM STRUCTURE and the static half of ARM
   CROSS-CHECK are not in the suite and cannot be: the first is invisible to any
   drive (see above) and the second is a statement about which FIELDS the two
   sides of the cross-check read. The reused `exec_id` inside the stream (`A-1`
   and `A-4` both carry `a1`) likewise proves the key is the PAIR, which a suite
   built on distinct exec ids never asks.

## debug.md §7.12 — THE STANDING QUESTION, answered where the gate is built

*What would have to be true for this gate to PASS while measuring nothing?*

1. **The ledger could be unimportable, or could resolve to another tree.**
   `checks/_preamble.py` appends the REAL `scripts/` to `sys.path` and never
   removes it, so an empty `nix_home` does not fail the import — it falls
   through to the live repository and the gate reports on a tree it never read
   (D3.124). *Closed twice:* an import failure is CANNOT_MEASURE naming the
   exception (§17 — never a PASS), and every loaded module's `__file__` must lie
   under the tree under judgement or the verdict is CANNOT_MEASURE naming the
   foreign path.
2. **The stream could be too short for duplicate-vs-unique to differ.** A
   one-fill stream cannot separate a correct ledger from one with no dedup at
   all. *Closed:* `MIN_UNIQUE_FILLS`, `MIN_ORDERS`, `MIN_SYMBOLS`,
   `MIN_SELL_FILLS` and `MIN_DUPLICATE_DELIVERIES` are FLOORS, every one of them
   strictly below what today's stream carries (doctrine C.4 — a threshold equal
   to today's count reddens on the next edit and proves nothing before then).
3. **A "permutation" could equal the in-order stream.** *Closed:* each
   reordering is required to differ from the identity order, to carry at least
   `MIN_INVERSIONS` inversions against it, and the run as a whole to deliver at
   least `MIN_CUMULATIVE_INVERSIONS` arrivals whose broker cumulative goes
   BACKWARDS within one order. Below those floors the verdict is
   CANNOT_MEASURE, not PASS.
4. **The cross-check could compare a figure against itself.** If `audit()`
   derived the "reported" cumulative from the same `filled_qty` increments as
   the derived one, the gap would be identically zero over every defect.
   *Closed twice:* statically — `audit`'s body must read BOTH `filled_qty` and
   `cumulative_qty` — and behaviourally, by driving a stream whose two figures
   genuinely disagree and requiring the exact gap.
5. **The expected figures could be degenerate.** Zero nets, or two symbols
   sharing one net, would let a ledger that returns a constant or reads the
   wrong symbol pass. *Closed:* every expected net is required non-zero and
   pairwise distinct before any comparison is made.
6. **The gate could compute its expectation FROM the ledger.** *Closed:* the
   reference is a hand-computed literal AND an independent re-derivation written
   here (a plain sum over a dict keyed by the §4 pair), and the two must agree
   with each other before either is compared to the subject.

## WHAT THIS GATE CANNOT PROVE, stated rather than implied

It drives the LEDGER. Nothing here proves the Limiter's broker-event handlers
CALL `ingest` on every real execution report, because those handlers do not
exist — the same residual `check_reservation_lifecycle` carries as D3.51, one
module over. A green means *the shipped ledger derives position from the unique
fill set and keeps an audit cross-check that discriminates*. It does NOT mean
production fills reach it. UNBOUND, and the evidence string says so on every
run.
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

# C0302 (too-many-lines) disabled, matching check_artifact_gate_coverage and
# check_datafeed_granted_mode: the §7.12 block, the C.9 argument and the
# per-finding reason strings ARE the deliverable here — every one of them is a
# sentence an operator reads out of a red verdict — and splitting the gate
# across modules to satisfy a line count would break §4.2's requirement that a
# check be independently runnable as one file.
# pylint: disable=too-many-lines,duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The ledger is imported from the tree under test and
#: no check produces it.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS the ledger package out of `ctx.nix_home`, so it mutates
#: `sys.path` and `sys.modules` for the duration of the load and restores both.
#: Declared for the same reason `check_reservation_lifecycle` declares them.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep. The drive is arithmetic over dictionaries.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for a ledger that double-counts a duplicate fill, loses an "
    "out-of-order one, or runs a cross-check against itself is a change to the "
    "position arithmetic §4 makes canonical, decided by a human against the "
    "frozen spec. An instrument empowered to edit the ledger until its own "
    "drive came back clean would be manufacturing its own green over the "
    "figure every downstream sizing and flatten decision reads"
)
#: Genuinely MEASURED here: the ledger is imported out of the tree under test,
#: driven with five streams, and its source is parsed. The seam is READ (its
#: PositionRow is constructed to drive `reconcile`) and is declared by
#: check_limiter_seam, which is where its own gate lives.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/execution.py",)

NAME = "check_execution_ledger"

LEDGER = "scripts/nixrisk/execution.py"
PACKAGE = "nixrisk"
MODULE = "nixrisk.execution"
SEAM_MODULE = "nixrisk.seam"

# --------------------------------------------------------------------------
# NON-VACUITY FLOORS. Every one is a FLOOR and every one is strictly below what
# the stream below carries today (9 unique fills, 5 orders, 3 symbols, 3 sell
# fills, 9 duplicate deliveries, 4 reorderings). Doctrine C.4: a threshold set
# to today's number is an anchor that moves — it reddens on the next edit to
# the stream and discriminates nothing in the meantime.
# --------------------------------------------------------------------------

#: Below this the dedup path is not exercised on enough distinct keys for a
#: duplicate to be distinguishable from a unique arrival.
MIN_UNIQUE_FILLS = 6
#: One order cannot show that the dedup key is a PAIR rather than an exec id.
MIN_ORDERS = 3
#: One symbol cannot show that `position` partitions by symbol at all.
MIN_SYMBOLS = 2
#: With no SELL the signed sum degenerates to a plain count of quantity.
MIN_SELL_FILLS = 1
#: The duplicated stream must be materially longer than the unique set.
MIN_DUPLICATE_DELIVERIES = 4
#: How many streams must be PROVEN reordered before the permutation verdict
#: means anything.
MIN_REORDERED_STREAMS = 3
#: Per reordering, against the identity order.
MIN_INVERSIONS = 4
#: Arrivals, across the whole run, whose broker cumulative moves BACKWARDS
#: inside one order — the literal out-of-order signature, as distinct from a
#: reshuffle that happens to keep every order internally in sequence.
MIN_CUMULATIVE_INVERSIONS = 2

#: The stream. `(order_id, exec_id, symbol, side, filled_qty, cumulative_qty)`.
#: `A-1` and `A-4` deliberately SHARE the exec id `a1` under different orders:
#: a ledger keyed on `exec_id` alone collides them and the reference arm sees
#: it. Deliberately NOT a copy of `scripts/tests/test_execution.py`'s stream.
_STREAM: tuple[tuple[str, str, str, str, int, int], ...] = (
    ("A-1", "a1", "ESZ6", "buy", 3, 3),
    ("A-1", "a2", "ESZ6", "buy", 2, 5),
    ("A-1", "a3", "ESZ6", "buy", 4, 9),
    ("A-2", "b1", "NQZ6", "buy", 2, 2),
    ("A-2", "b2", "NQZ6", "buy", 5, 7),
    ("A-3", "c1", "ESZ6", "sell", 4, 4),
    ("A-3", "c2", "ESZ6", "sell", 1, 5),
    ("A-4", "a1", "NQZ6", "sell", 4, 4),
    ("A-5", "e1", "RTYZ6", "buy", 6, 6),
)

#: HAND-COMPUTED from `_STREAM` above, and cross-checked at run time against
#: this gate's own independent re-derivation before either is compared to the
#: ledger. ESZ6 = (3+2+4) − (4+1) = 4 ; NQZ6 = (2+5) − 4 = 3 ; RTYZ6 = 6.
_EXPECTED_NET: dict[str, int] = {"ESZ6": 4, "NQZ6": 3, "RTYZ6": 6}

#: The exec withheld to open a cross-check gap: `A-1`'s middle increment. The
#: two surviving execs of that order still carry the broker's cumulative 9, so
#: the gap is exactly this report's own `filled_qty`.
_WITHHELD = ("A-1", "a2")

#: How far one §3 position row is put wrong in the reconcile arm.
_ROW_DELTA = 3


class Finding(NamedTuple):
    """One defect: where it is, and what is wrong. Never a bare status."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The ledger and the seam, imported out of the tree under test."""

    execution: ModuleType
    seam: ModuleType


@dataclasses.dataclass
class Tally:  # pylint: disable=too-many-instance-attributes
    """What the drive actually did. Non-vacuity is read off this, not asserted."""

    unique_fills: int = 0
    orders: int = 0
    symbols: int = 0
    sell_fills: int = 0
    duplicate_deliveries: int = 0
    reordered_streams: int = 0
    inversions: int = 0
    cumulative_inversions: int = 0


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# --------------------------------------------------------------------------
# LOADING — the ledger comes out of the tree under test, never out of this one
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

    D3.124: `checks/_preamble.py` appends the REAL `scripts/` to `sys.path` and
    never removes it, so an import against a tree that lacks the subject does
    not fail — it resolves against the live repository and the gate measures a
    tree other than the one it reports on. `__file__` is the interpreter's own
    record of where the bytes came from, which is why it is the answer.

    The SUBJECT is pinned harder than the seam: `arm_structure` parses
    `home/LEDGER` from disk while every other arm drives the IMPORTED module, so
    those two halves must be the same file and not merely two files under the
    same root. The seam is only read, and is checked against the root.
    """
    root = (home / "scripts").resolve()
    subject = (home / LEDGER).resolve()
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
                f"{MODULE} was imported from {resolved}, not from the {LEDGER} "
                f"this gate parses statically ({subject}) — the driven half and "
                "the read half would be judging two different files, so nothing "
                "was measured about either (§17: never a PASS)"
            )
    return ""


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the ledger from `home`, leaving the interpreter as it was found.

    A path-keyed import is what lets a plant live on a `tmp_path` COPY (doctrine
    C.8): the gate drives whichever tree it is pointed at, and the production
    ledger is never written.
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
    # directory-mtime cache, and the resulting ModuleNotFoundError would be
    # reported as "the subject is unavailable" over a subject that is right
    # there. Required, not defensive: every plant lives in a fresh tmp_path.
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            execution=importlib.import_module(MODULE),
            seam=importlib.import_module(SEAM_MODULE),
        )
        complaint = _provenance(loaded, home)
        return (None, complaint) if complaint else (loaded, "")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{LEDGER}: cannot import {MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# THE STREAM, and this gate's OWN arithmetic over it
# --------------------------------------------------------------------------


#: `(order_id, exec_id) -> its position in `_STREAM``. Price and timestamp are
#: derived from THIS rather than from a report's position in the delivered
#: stream, because they are identity fields: deriving them from arrival order
#: would make a re-delivery of a key carry a different price and a permutation
#: carry a different timestamp, so the ledger would correctly refuse the
#: duplicated and reordered streams as CONTRADICTIONS and the immunity arms
#: would never run. Measured, not reasoned about: the first draft did exactly
#: that and this gate returned CANNOT_MEASURE naming `price: 5000.25 then
#: 5000.5`.
_KEY_INDEX: dict[tuple[str, str], int] = {
    (row[0], row[1]): index for index, row in enumerate(_STREAM)
}


def _reports(loaded: Loaded, rows: tuple[tuple[Any, ...], ...]) -> tuple[Any, ...]:
    """Build `ExecutionReport`s. Prices are distinct and non-round on purpose."""
    execution = loaded.execution
    return tuple(
        execution.ExecutionReport(
            order_id=order_id,
            exec_id=exec_id,
            symbol=symbol,
            side=execution.FillSide(side),
            filled_qty=qty,
            price=5000.25 + 0.25 * _KEY_INDEX[(order_id, exec_id)],
            cumulative_qty=cumulative,
            ts=1000.0 + _KEY_INDEX[(order_id, exec_id)],
        )
        for order_id, exec_id, symbol, side, qty, cumulative in rows
    )


def _independent(rows: tuple[tuple[Any, ...], ...], symbol: str) -> int:
    """Σ signed quantity over the UNIQUE `(order_id, exec_id)` set — this gate's
    own arithmetic, written here so the expectation is never the subject's."""
    unique: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in rows:
        unique[(row[0], row[1])] = row
    return sum(
        (row[4] if row[3] == "buy" else -row[4])
        for row in unique.values()
        if row[2] == symbol
    )


def _snapshot(ledger: Any) -> dict[str, Any]:
    """The full derived position state — the value that must be invariant."""
    return {symbol: ledger.position(symbol) for symbol in sorted(_EXPECTED_NET)}


def _fed(loaded: Loaded, reports: tuple[Any, ...]) -> Any:
    """A fresh ledger fed the stream in the given arrival order."""
    ledger = loaded.execution.ExecutionLedger()
    ledger.ingest_all(reports)
    return ledger


# --------------------------------------------------------------------------
# PRE-FLIGHT — the floors, before any verdict is possible
# --------------------------------------------------------------------------


def _index_orders(size: int) -> tuple[tuple[int, ...], ...]:
    """Four deterministic reorderings. No randomness: a flaky gate is not one."""
    half = size // 2
    return (
        tuple(range(size - 1, -1, -1)),
        tuple((index + 4) % size for index in range(size)),
        tuple(range(0, size, 2)) + tuple(range(1, size, 2)),
        tuple(reversed(range(half))) + tuple(reversed(range(half, size))),
    )


def _inversions(order: tuple[int, ...]) -> int:
    """Pairs delivered out of their natural relative order. The reorder metric."""
    return sum(
        1
        for i in range(len(order))
        for j in range(i + 1, len(order))
        if order[i] > order[j]
    )


def _cumulative_inversions(rows: tuple[tuple[Any, ...], ...]) -> int:
    """Arrivals whose broker cumulative goes BACKWARDS inside one order."""
    seen: dict[str, int] = {}
    backwards = 0
    for row in rows:
        order_id, cumulative = row[0], row[5]
        if cumulative < seen.get(order_id, 0):
            backwards += 1
        seen[order_id] = max(seen.get(order_id, 0), cumulative)
    return backwards


def _stream_floors(tally: Tally) -> str:
    """The stream's own credibility, before the ledger is asked anything."""
    checks = (
        (tally.unique_fills, MIN_UNIQUE_FILLS, "unique fill(s)"),
        (tally.orders, MIN_ORDERS, "order(s)"),
        (tally.symbols, MIN_SYMBOLS, "symbol(s)"),
        (tally.sell_fills, MIN_SELL_FILLS, "SELL fill(s)"),
    )
    for actual, floor, label in checks:
        if actual < floor:
            return (
                f"{LEDGER}: the drive stream carries {actual} {label}, below the "
                f"floor of {floor} — a stream that small cannot tell a correct "
                "ledger from one that never deduplicated, so a clean sheet here "
                "would be about an empty run (§5.3: an empty scope is never a "
                "PASS)"
            )
    return ""


def _expectation_defect() -> str:
    """Degenerate expectations agree with anything. Refuse before measuring."""
    nets = list(_EXPECTED_NET.values())
    if any(net == 0 for net in nets):
        return (
            f"{LEDGER}: an expected net of 0 would let a ledger that returns a "
            "constant zero pass this gate"
        )
    if len(set(nets)) != len(nets):
        return (
            f"{LEDGER}: two symbols share an expected net {sorted(nets)} — a "
            "ledger reading the wrong symbol's fills would be invisible"
        )
    mismatched = [
        f"{symbol}: literal {net} vs independently derived "
        f"{_independent(_STREAM, symbol)}"
        for symbol, net in _EXPECTED_NET.items()
        if _independent(_STREAM, symbol) != net
    ]
    if mismatched:
        return (
            f"{LEDGER}: this gate's hand-computed reference disagrees with its "
            f"own independent re-derivation ({'; '.join(mismatched)}) — the "
            "expectation is broken before the subject is consulted"
        )
    return ""


def _tally_stream(tally: Tally) -> None:
    """Fill the stream-shape half of the tally from `_STREAM` itself."""
    unique = {(row[0], row[1]): row for row in _STREAM}
    tally.unique_fills = len(unique)
    tally.orders = len({row[0] for row in unique.values()})
    tally.symbols = len({row[2] for row in unique.values()})
    tally.sell_fills = len([row for row in unique.values() if row[3] == "sell"])


# --------------------------------------------------------------------------
# ARM REFERENCE — the in-order stream against a literal and an independent Σ
# --------------------------------------------------------------------------


def _reference_findings(ledger: Any, symbol: str) -> list[Finding]:
    """One symbol's derived position against both references."""
    site = f"{LEDGER}:position[{symbol}]"
    derived = ledger.position(symbol)
    expected = _EXPECTED_NET[symbol]
    if derived.net_qty != expected:
        return [
            Finding(
                site,
                f"net_qty is {derived.net_qty!r} on the in-order stream and both "
                f"this gate's hand-computed figure and its independent Σ over the "
                f"unique (order_id, exec_id) set say {expected!r} — §4 makes "
                "position a function of that set and the ledger is not computing "
                "it. Note the stream reuses one exec_id across two orders, so a "
                "ledger keyed on exec_id alone lands here",
            )
        ]
    bought = sum(row[4] for row in _STREAM if row[2] == symbol and row[3] == "buy")
    sold = sum(row[4] for row in _STREAM if row[2] == symbol and row[3] == "sell")
    if (derived.bought_qty, derived.sold_qty) != (bought, sold):
        return [
            Finding(
                site,
                f"bought/sold read {derived.bought_qty!r}/{derived.sold_qty!r} "
                f"against {bought!r}/{sold!r} — the net is right while the two "
                "sides that make it up are not, which a net-only comparison "
                "cannot see",
            )
        ]
    return []


def arm_reference(loaded: Loaded) -> tuple[list[Finding], Any]:
    """The reference snapshot, pinned to arithmetic rather than self-consistency."""
    ledger = _fed(loaded, _reports(loaded, _STREAM))
    findings: list[Finding] = []
    for symbol in sorted(_EXPECTED_NET):
        findings += _reference_findings(ledger, symbol)
    if ledger.fill_count() != len({(row[0], row[1]) for row in _STREAM}):
        findings.append(
            Finding(
                f"{LEDGER}:fill_count",
                f"the ledger holds {ledger.fill_count()} unique execution(s) for "
                f"a stream of {len({(row[0], row[1]) for row in _STREAM})} "
                "distinct (order_id, exec_id) pairs — the dedup key is not the §4 "
                "pair",
            )
        )
    return findings, ledger


# --------------------------------------------------------------------------
# ARM IDEMPOTENCE — every report delivered twice
# --------------------------------------------------------------------------


def arm_idempotence(
    loaded: Loaded, reference: dict[str, Any], tally: Tally
) -> list[Finding]:
    """A duplicate `(order_id, exec_id)` must not move the position at all."""
    site = f"{LEDGER}:ingest[duplicate]"
    doubled: list[tuple[Any, ...]] = []
    for row in _STREAM:
        doubled += [row, row]
    tally.duplicate_deliveries = len(doubled) - len({(r[0], r[1]) for r in _STREAM})
    ledger = _fed(loaded, _reports(loaded, tuple(doubled)))
    findings: list[Finding] = []
    observed = _snapshot(ledger)
    if observed != reference:
        findings.append(
            Finding(
                site,
                f"delivering every report TWICE changed the derived position "
                f"from {_nets(reference)} to {_nets(observed)} — §4 makes a "
                "re-delivery idempotent, and a ledger that double-counts one "
                "reports a position the account does not hold",
            )
        )
    unique = len({(row[0], row[1]) for row in _STREAM})
    if ledger.fill_count() != unique:
        findings.append(
            Finding(
                site,
                f"the ledger holds {ledger.fill_count()} unique execution(s) "
                f"after a stream of {len(doubled)} deliveries carrying {unique} "
                "distinct keys — the duplicates entered the SET",
            )
        )
    return findings + _duplicate_counters(ledger, unique, site)


def _duplicate_counters(ledger: Any, unique: int, site: str) -> list[Finding]:
    """The ledger must be able to SAY the idempotency fired, not merely be quiet."""
    if (ledger.applied, ledger.duplicates) == (unique, unique):
        return []
    return [
        Finding(
            site,
            f"the ledger booked applied={ledger.applied!r} duplicates="
            f"{ledger.duplicates!r} over {unique} distinct keys each delivered "
            "twice — a ledger that cannot report what it did with a stream can "
            "only be believed, not measured",
        )
    ]


def _nets(snapshot: dict[str, Any]) -> str:
    """Positions rendered as `symbol=net`, for a reason-bearing message."""
    return ", ".join(f"{symbol}={pos.net_qty!r}" for symbol, pos in snapshot.items())


# --------------------------------------------------------------------------
# ARM PERMUTATION — four reorderings, each PROVEN reordered first
# --------------------------------------------------------------------------


def _one_permutation(
    loaded: Loaded, order: tuple[int, ...], reference: dict[str, Any], tally: Tally
) -> list[Finding]:
    """One reordering: prove it is genuinely reordered, then trust its result."""
    site = f"{LEDGER}:ingest[permutation]"
    rows = tuple(_STREAM[index] for index in order)
    inversions = _inversions(order)
    if order == tuple(range(len(_STREAM))) or inversions < MIN_INVERSIONS:
        return [
            Finding(
                f"{site}:{order}",
                f"this gate's own 'permutation' carries {inversions} inversion(s) "
                f"against the floor of {MIN_INVERSIONS} — an arrival order that "
                "is not actually out of order proves nothing about immunity to "
                "out-of-order delivery",
            )
        ]
    tally.reordered_streams += 1
    tally.inversions += inversions
    tally.cumulative_inversions += _cumulative_inversions(rows)
    observed = _snapshot(_fed(loaded, _reports(loaded, rows)))
    if observed != reference:
        return [
            Finding(
                f"{site}:{order}",
                f"arrival order {order} ({inversions} inversion(s)) produced "
                f"{_nets(observed)} where the in-order stream produces "
                f"{_nets(reference)} — §4 requires immunity to out-of-order "
                "execution reports, and this ledger's answer depends on when the "
                "broker happened to deliver",
            )
        ]
    return []


def arm_permutation(
    loaded: Loaded, reference: dict[str, Any], tally: Tally
) -> list[Finding]:
    """Every reordering must reproduce the reference snapshot exactly."""
    findings: list[Finding] = []
    for order in _index_orders(len(_STREAM)):
        findings += _one_permutation(loaded, order, reference, tally)
    return findings


# --------------------------------------------------------------------------
# ARM CROSS-CHECK — Σ increments vs the broker's own cumulative, BOTH halves
# --------------------------------------------------------------------------


def _audit_complete(ledger: Any) -> list[Finding]:
    """The complete stream closes every order's gap. The half that must be 0."""
    site = f"{LEDGER}:audit[complete]"
    findings: list[Finding] = []
    for order_id in sorted({row[0] for row in _STREAM}):
        audit = ledger.audit(order_id)
        if audit.reported_cumulative <= 0 or audit.derived_cumulative <= 0:
            findings.append(
                Finding(
                    site,
                    f"{order_id} audits derived={audit.derived_cumulative!r} "
                    f"reported={audit.reported_cumulative!r} — a cross-check "
                    "between two zeroes agrees with everything",
                )
            )
        elif not audit.complete:
            findings.append(
                Finding(
                    site,
                    f"{order_id} reports gap {audit.gap!r} on the COMPLETE "
                    f"stream (derived {audit.derived_cumulative!r} vs reported "
                    f"{audit.reported_cumulative!r}) — the cross-check fires on "
                    "data that is not missing anything",
                )
            )
    return findings


def _audit_gap(loaded: Loaded) -> list[Finding]:
    """One exec withheld: the gap must be exactly its quantity, and SURFACED."""
    site = f"{LEDGER}:audit[withheld]"
    withheld = next(
        row for row in _STREAM if (row[0], row[1]) == _WITHHELD
    )  # the middle increment of A-1
    rows = tuple(row for row in _STREAM if (row[0], row[1]) != _WITHHELD)
    ledger = _fed(loaded, _reports(loaded, rows))
    audit = ledger.audit(_WITHHELD[0])
    findings: list[Finding] = []
    if audit.gap != withheld[4] or audit.complete:
        findings.append(
            Finding(
                site,
                f"{_WITHHELD[0]} is missing exec {_WITHHELD[1]} (filled_qty "
                f"{withheld[4]!r}) and audit() reports gap {audit.gap!r} / "
                f"complete={audit.complete!r} — the broker's own cumulative "
                "records a fill this ledger never received and the cross-check "
                "did not see it. A cross-check whose two sides read the same "
                "field reports 0 over every defect",
            )
        )
    return findings + _audit_not_reconciled(ledger, withheld, site)


def _audit_not_reconciled(
    ledger: Any, withheld: tuple[Any, ...], site: str
) -> list[Finding]:
    """The gap is REPORTED, never absorbed: position reflects only what was seen."""
    symbol = withheld[2]
    seen_net = _EXPECTED_NET[symbol] - withheld[4]
    actual = ledger.position(symbol).net_qty
    if actual == seen_net:
        return []
    return [
        Finding(
            site,
            f"{symbol} position reads {actual!r} with exec {_WITHHELD[1]} never "
            f"delivered; the fills actually seen sum to {seen_net!r}. The ledger "
            "moved its own position toward the broker's cumulative instead of "
            "reporting the disagreement — §4 makes broker truth the arbiter of "
            "the RECONCILIATION, not a figure this ledger may silently adopt",
        )
    ]


def _rows(loaded: Loaded, sizes: dict[str, int]) -> tuple[tuple[Any, ...], str]:
    """§3 position rows for `reconcile`, or the reason none could be built."""
    seam = loaded.seam
    try:
        built = tuple(
            seam.PositionRow(
                trade_id=f"T-{symbol}",
                symbol=symbol,
                strategy_id="strat-1",
                size=size,
                margin=1234.5,
                state=seam.PositionState.OPEN,
                stop_distance=20,
            )
            for symbol, size in sorted(sizes.items())
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (), (
            f"{LEDGER}: cannot construct a §3 PositionRow from the seam in the "
            f"tree under test — {type(exc).__name__}: {exc}. The reconcile arm "
            "has no input, so nothing was measured (§17: never a PASS)"
        )
    return built, ""


def _reconcile_arm(loaded: Loaded, ledger: Any) -> tuple[list[Finding], str]:
    """§3's published rows, both halves: agreement, then a row put wrong."""
    site = f"{LEDGER}:reconcile"
    agreeing, complaint = _rows(loaded, dict(_EXPECTED_NET))
    if complaint:
        return [], complaint
    findings = [
        Finding(
            site,
            f"{drift.symbol} reports drift {drift.drift!r} against a row that "
            f"matches the derived net {drift.derived_net_qty!r} — a reconcile "
            "that disagrees with agreement discriminates nothing",
        )
        for drift in ledger.reconcile(agreeing)
        if not drift.agrees
    ]
    wrong = dict(_EXPECTED_NET)
    target = min(wrong)
    wrong[target] -= _ROW_DELTA
    rows, complaint = _rows(loaded, wrong)
    if complaint:
        return findings, complaint
    return findings + _drift_findings(ledger, rows, target, site), ""


def _drift_findings(
    ledger: Any, rows: tuple[Any, ...], target: str, site: str
) -> list[Finding]:
    """The wrong row must be flagged, with the exact derived-vs-row numbers."""
    drifts = {drift.symbol: drift for drift in ledger.reconcile(rows)}
    drift = drifts.get(target)
    if drift is None:
        return [
            Finding(
                site,
                f"reconcile returned no row for {target} at all, so a position "
                "the ledger holds could vanish from the reconciliation entirely",
            )
        ]
    if drift.agrees or drift.drift != _ROW_DELTA:
        return [
            Finding(
                site,
                f"{target}'s §3 row was put {_ROW_DELTA!r} below the derived net "
                f"{_EXPECTED_NET[target]!r} and reconcile reports drift "
                f"{drift.drift!r} / agrees={drift.agrees!r} — a drift the ledger "
                "cannot see is a drift it silently reconciled away",
            )
        ]
    return []


# --------------------------------------------------------------------------
# ARM CONTRADICTION — a duplicate KEY carrying different data is not benign
# --------------------------------------------------------------------------


def arm_contradiction(loaded: Loaded) -> list[Finding]:
    """A same-key rewrite must RAISE naming the field. The idempotence arm is
    blind to it by construction: an exact re-delivery cannot move the position
    even in a ledger that blindly overwrites its store."""
    site = f"{LEDGER}:ingest[contradiction]"
    first, second = _STREAM[0], (*_STREAM[0][:4], _STREAM[0][4] + 5, _STREAM[0][5] + 5)
    ledger = _fed(loaded, _reports(loaded, (first,)))
    before = ledger.position(first[2]).net_qty
    reports = _reports(loaded, (first, second))
    try:
        ledger.ingest(reports[1])
    except loaded.execution.ContradictoryExecution as exc:
        return _contradiction_reason(str(exc), first, ledger, site)
    return [
        Finding(
            site,
            f"a second report under the seen key {first[0]}/{first[1]} carrying "
            f"filled_qty {second[4]!r} instead of {first[4]!r} was ABSORBED "
            f"(position {before!r} -> {ledger.position(first[2]).net_qty!r}). §4 "
            "makes a RE-DELIVERY idempotent, not a rewrite: one of the two "
            "stories about that execution is now gone with no record it existed",
        )
    ]


def _contradiction_reason(
    message: str, first: tuple[Any, ...], ledger: Any, site: str
) -> list[Finding]:
    """The refusal must NAME the disagreement (check contract v2 §11 / §18)."""
    findings: list[Finding] = []
    if "filled_qty" not in message:
        findings.append(
            Finding(
                site,
                f"the refusal does not name the field that disagreed; it says "
                f"{message!r}. An exception TYPE is a shared namespace — the "
                "reason is the evidence",
            )
        )
    if ledger.position(first[2]).net_qty != _independent((first,), first[2]):
        findings.append(
            Finding(
                site,
                f"the refused rewrite still moved {first[2]} to "
                f"{ledger.position(first[2]).net_qty!r} — the ledger raised and "
                "mutated, which keeps neither story intact",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM STRUCTURE — the property no drive can see
# --------------------------------------------------------------------------


def _ledger_class(tree: ast.Module) -> ast.ClassDef | None:
    """The class declaring both `ingest` and `position`. Found, never named."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {
            child.name for child in node.body if isinstance(child, ast.FunctionDef)
        }
        if {"ingest", "position"} <= methods:
            return node
    return None


def _method(node: ast.ClassDef, name: str) -> ast.FunctionDef | None:
    for child in node.body:
        if isinstance(child, ast.FunctionDef) and child.name == name:
            return child
    return None


def _store_attribute(ingest: ast.FunctionDef) -> str:
    """The attribute `ingest` stores the report itself into, under a key.

    DERIVED, not typed: the store is whichever `self.<attr>[...]` is assigned
    the `ingest` parameter. That is what makes `position` a function of a SET —
    and it means this gate does not carry the store's name as a literal that
    would rot the moment the ledger renamed it.
    """
    parameter = ingest.args.args[1].arg if len(ingest.args.args) > 1 else ""
    for node in ast.walk(ingest):
        store = _keyed_store(node, parameter)
        if store:
            return store
    return ""


def _keyed_store(node: ast.AST, parameter: str) -> str:
    """`self.<attr>[...] = <parameter>` -> `<attr>`; anything else -> `""`."""
    if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
        return ""
    if node.value.id != parameter:
        return ""
    for target in node.targets:
        if isinstance(target, ast.Subscript):
            return _self_attr(target.value)
    return ""


def _self_attr(node: ast.AST) -> str:
    """`self.<attr>` -> `<attr>`; anything else -> `""`."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return ""


def _self_reads(node: ast.AST) -> set[str]:
    """Every `self.<attr>` read inside `node`."""
    return {attr for child in ast.walk(node) if (attr := _self_attr(child))}


def arm_structure(home: Path) -> list[Finding]:
    """`position` derives from the keyed store and from nothing else.

    A correctly-maintained running total is permutation-invariant AND
    duplicate-immune, so no drive can separate it from the scan the module's own
    docstring calls the reason the immunity is structural. This is the arm that
    can, and it is why this gate is not `test_execution.py` with a different
    entry point.
    """
    site = f"{LEDGER}:position"
    tree = ast.parse((home / LEDGER).read_text(encoding="utf-8"), filename=LEDGER)
    node = _ledger_class(tree)
    if node is None:
        return [Finding(LEDGER, "no class declares both ingest and position")]
    ingest, position = _method(node, "ingest"), _method(node, "position")
    if ingest is None or position is None:
        return [Finding(LEDGER, "ingest or position is not a plain function")]
    store = _store_attribute(ingest)
    if not store:
        return [
            Finding(
                f"{LEDGER}:ingest",
                "ingest never stores the report itself under a key — the keyed "
                "store IS the state §4 makes position a function of, and without "
                "one a duplicate has nothing to map onto",
            )
        ]
    return _position_reads(position, store, site) + _audit_fields(node, site)


def _position_reads(position: ast.FunctionDef, store: str, site: str) -> list[Finding]:
    """`position` may read the store, and nothing else that anyone maintains."""
    extra = sorted(_self_reads(position) - {store})
    if not extra:
        return []
    return [
        Finding(
            site,
            f"position reads self.{', self.'.join(extra)} as well as the keyed "
            f"store self.{store} — §4's immunity is a property of a SCAN over "
            "the unique-fill SET, and a maintained running total re-introduces "
            "exactly the ordering discipline the set construction exists to "
            "make unnecessary. No drive can see this: a correctly-maintained "
            "total is permutation-invariant and duplicate-immune too, right up "
            "until it drifts",
        )
    ]


def _audit_fields(node: ast.ClassDef, site: str) -> list[Finding]:
    """`audit`'s two sides must read DIFFERENT fields, or the gap is always 0."""
    audit = _method(node, "audit")
    if audit is None:
        return [Finding(f"{site}:audit", "the ledger declares no audit()")]
    fields = {
        child.attr for child in ast.walk(audit) if isinstance(child, ast.Attribute)
    }
    missing = sorted({"filled_qty", "cumulative_qty"} - fields)
    if not missing:
        return []
    return [
        Finding(
            f"{LEDGER}:audit",
            f"audit() never reads {', '.join(missing)} — §4's cross-check is two "
            "pieces of arithmetic over two DIFFERENT records (this ledger's Σ of "
            "increments against the broker's own running total), and one that "
            "reads a single field compares a figure with itself and reports gap "
            "0 over every missing execution",
        )
    ]


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def _drive_floors(tally: Tally) -> str:
    """What the drive ACTUALLY delivered, read off the tally rather than hoped."""
    checks = (
        (
            tally.duplicate_deliveries,
            MIN_DUPLICATE_DELIVERIES,
            "duplicate delivery/deliveries",
        ),
        (tally.reordered_streams, MIN_REORDERED_STREAMS, "proven-reordered stream(s)"),
        (
            tally.cumulative_inversions,
            MIN_CUMULATIVE_INVERSIONS,
            "backwards-cumulative arrival(s)",
        ),
    )
    for actual, floor, label in checks:
        if actual < floor:
            return (
                f"{LEDGER}: the drive delivered {actual} {label}, below the floor "
                f"of {floor} — the immunity verdict would be about a stream that "
                "never exercised the condition it claims immunity from"
            )
    return ""


def _evidence(tally: Tally) -> str:
    return (
        f"{tally.unique_fills} unique (order_id, exec_id) fill(s) across "
        f"{tally.orders} order(s) and {tally.symbols} symbol(s) "
        f"({tally.sell_fills} SELL), driven against the SHIPPED ledger imported "
        f"out of the tree under judgement with its __file__ provenance asserted; "
        f"{tally.duplicate_deliveries} duplicate delivery/deliveries and "
        f"{tally.reordered_streams} proven-reordered stream(s) carrying "
        f"{tally.inversions} inversion(s) and {tally.cumulative_inversions} "
        f"backwards-cumulative arrival(s), every one reproducing the reference "
        f"position exactly; the §4 cross-check driven in BOTH directions "
        f"(complete order gap 0, withheld exec gap equal to its own filled_qty) "
        f"and §3's reconcile in both; position proven to read the keyed store "
        f"and nothing else. Reference figures are hand-computed AND "
        f"independently re-derived here, never read from the subject. UNBOUND: "
        f"drives the LEDGER, never the Limiter's broker-event handlers, which do "
        f"not exist yet (the D3.51 residual, one module over)"
    )


def _guarded(label: str, arm: Any) -> list[Finding]:
    """Run one arm. A RAISING ledger is a finding about the ledger, not a crash.

    §4 requires the ledger to ABSORB duplicate and out-of-order delivery; a
    stream this gate builds from legitimate execution reports is one it must not
    refuse. Letting the exception reach `run` would report CANNOT_MEASURE — "the
    instrument broke" — over a subject that broke instead, which is exactly the
    shared-namespace confusion §18 exists to stop.
    """
    try:
        return list(arm())
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{LEDGER}:{label}",
                f"the drive raised {type(exc).__name__}: {exc} — this gate's "
                "stream is a legitimate one and §4 requires the ledger to "
                "absorb it, so a refusal here is the ledger's defect and not "
                "this gate's inability to measure",
            )
        ]


def _drive(loaded: Loaded, tally: Tally) -> tuple[list[Finding], str]:
    """Every arm, in order. Returns (findings, refusal)."""
    reference: dict[str, Any] = {}
    try:
        findings, ledger = arm_reference(loaded)
        reference = _snapshot(ledger)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return _guarded("ingest[reference]", _raiser(exc)), ""
    arms: tuple[tuple[str, Any], ...] = (
        ("ingest[duplicate]", lambda: arm_idempotence(loaded, reference, tally)),
        ("ingest[permutation]", lambda: arm_permutation(loaded, reference, tally)),
        ("audit[complete]", lambda: _audit_complete(ledger)),
        ("audit[withheld]", lambda: _audit_gap(loaded)),
        ("ingest[contradiction]", lambda: arm_contradiction(loaded)),
    )
    for label, arm in arms:
        findings += _guarded(label, arm)
    reconciled, complaint = _reconcile_arm(loaded, ledger)
    findings += reconciled
    if complaint:
        return findings, complaint
    return findings, ""


def _raiser(exc: BaseException) -> Any:
    """A zero-argument callable that re-raises `exc`, so the reference arm's own
    failure is reported through the same reason-bearing path as every other."""

    def _again() -> list[Finding]:
        raise exc

    return _again


def _preflight(home: Path, tally: Tally) -> tuple[Loaded | None, str]:
    """Both sides, or the ONE reason the comparison cannot be made.

    The floors and the expectation are checked BEFORE the subject is imported,
    deliberately: a gate whose own reference is degenerate has nothing to say
    about any ledger, and saying it after a successful import would read as a
    statement about the subject.
    """
    for complaint in (_stream_floors(tally), _expectation_defect()):
        if complaint:
            return None, complaint
    return load(home)


def _verdict(findings: list[Finding], refusal: str, tally: Tally) -> CheckResult:
    """One reading or one refusal, never both and never neither."""
    if refusal:
        return _cannot_measure(refusal)
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
    """Drive §4's idempotency property through the ledger. Never repairs."""
    try:
        tally = Tally()
        _tally_stream(tally)
        loaded, complaint = _preflight(ctx.nix_home, tally)
        if loaded is None:
            return _cannot_measure(complaint)
        findings, refusal = _drive(loaded, tally)
        findings += arm_structure(ctx.nix_home)
        return _verdict(findings, refusal, tally)
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
