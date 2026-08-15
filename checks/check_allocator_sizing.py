#!/usr/bin/env python3
"""Gate: the Allocator's sizing pass DROPS BEFORE IT SIZES, and sizes off the
published picture — measured by driving it, never by reading it.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *a GO
becomes a proposal through §16 U1's single pass, with every figure taken from
the ONE published snapshot.* Six arms serve that single property. Each closes a
different route by which the pass can look correct and be wrong.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless a document is
named on the same line.

------------------------------------------------------------------------------
WHY THIS GATE HAS TO DRIVE REAL OBJECTS
------------------------------------------------------------------------------
An allocator that sizes a dead signal and then discards the result produces a
**byte-identical proposal** to one that dropped first: same outcome, same
reason, same zero contracts. Nothing about the output distinguishes them. So
the measurement cannot be over outputs, and it cannot be over source order —
reading the order somebody WROTE proves nothing about the order something RAN,
and §16 U1 is a statement about the second.

This gate therefore replaces every arithmetic function in the subject with a
recorder writing to one shared call log, hands the subject recording mirror and
tradability ports writing to the SAME log, drives it, and reads the log. ARM 2
then drives a deliberately WRONG allocator — one that sizes before it asks
whether the symbol is tradable — through the same instrument and FAILS if the
instrument does not catch it. An instrument that cannot fail on the defect is
not evidence about the subject.

------------------------------------------------------------------------------
THE ARMS
------------------------------------------------------------------------------
  * **ARM 1 — execution order.** A dead signal's call log holds the tradability
    query and NOTHING else: no mirror read, no arithmetic. A live signal's log
    holds the tradability query, then the snapshot, then the arithmetic, and
    exactly ONE snapshot read (§3's atomicity: one pass, one version). A mirror
    that is not `sizeable` sizes nothing at all.

  * **ARM 2 — the instrument's discriminating power.** The falsifier, run every
    time this gate runs rather than once at authoring time.

  * **ARM 3 — the published `committed` is the one used (§16 U2).** The picture
    handed in has a `committed` that disagrees with the sum of its own position
    rows by a floor-checked margin, and its position table counts its own
    traversals. Headroom must equal `DEPLOYABLE_PCT × balance − PUBLISHED
    committed`, and the traversal count must be zero: a sizer that re-derived
    the aggregate would satisfy every other arm here and fail this one twice.

  * **ARM 4 — the §15 C3 / §7 guards.** Zero and negative stop distances are
    deny-shaped NO-SIZE proposals carrying no size; a symbol absent from the
    published margin cache is not-tradable; a negative headroom clamps to zero
    contracts with no negative term anywhere; and the slippage pad is INSIDE
    the dollar-risk denominator, shown by two pads producing two answers.

  * **ARM 5 — §16 U4's single-instrument preference, BOTH branches.** A case
    that quantizes acceptably to fulls and a case that does not are both
    driven, both reached, and every sized proposal names exactly one
    instrument. A rule exercised on one branch has not been exercised.

  * **ARM 6 — one versioned row, two readers (§6.4).** The Allocator and the
    REAL `nixrisk.gate.GatePass` over the REAL `default_manifest` are handed
    the same picture through a proxy that records who read what. Every field
    both read must carry identical values, and the version stamp must be among
    them. The falsifier hands them two different rows and requires the same
    comparison to notice.

  * **ARM 7 — 0.70 is READ, not carved.** `DEPLOYABLE_PCT` has exactly one
    physical home (`risks/limiter.config.json`); the loader must return that
    file's value, and the subject's source must contain no arithmetic on a
    carved 0.70.

------------------------------------------------------------------------------
`debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
MEASURING NOTHING. Six routes, each closed by a mechanism, not by a promise:
------------------------------------------------------------------------------
 1. **The subject never loads**, and every arm skips. Closed: `load_subject`
    returns a complaint and the verdict is CANNOT_MEASURE, never PASS.
 2. **The recorders are never installed**, so "no arithmetic ran" is trivially
    true for every input. Closed: ARM 1 requires a KNOWN-SIZING pass to record
    at least `MIN_ARITHMETIC_CALLS` distinct arithmetic names before it judges
    the dead-signal log.
 3. **The instrument cannot see a violation at all.** Closed by ARM 2, which
    fails unless the sizes-first falsifier is caught.
 4. **The identity arm compares fields neither reader touched.** Closed:
    `MIN_SHARED_FIELDS`, and the version stamp is required to be one of them,
    and the two-row falsifier must be flagged.
 5. **The committed plant is not actually a disagreement**, so "published wins"
    and "re-derived wins" give the same number. Closed: the gap is asserted at
    or above `MIN_PLANT_GAP` before any comparison is made.
 6. **The fulls/micros arm lands on one branch every time.** Closed: both
    branch labels must appear in the observed outcomes, counted.

------------------------------------------------------------------------------
WHAT THIS GATE CANNOT PROVE — stated, so no green implies it
------------------------------------------------------------------------------
1. **Anything about the correlation-bucket cap.** `BucketCapPort` is an
   injection point in the subject and this gate drives it as `None`; the cap
   lives in `scripts/nixalloc/caps.py`, a different owner. Every rationale in
   this gate's evidence therefore says the cap was NOT applied.
2. **Anything about the mirror's transport or staleness machinery.** The mirror
   here is a double. What the real subscriber does with freshness stamps is
   `scripts/nixalloc/mirror.py`'s property.
3. **Anything about contention.** §6.6's ranking table has no writer, so FCFS
   is the only reachable policy and this gate can only observe that it is the
   one recorded.
4. **That the numbers are the RIGHT numbers.** Every §12A value in `risks/` is
   a CC-calibrate placeholder. This gate proves the arithmetic consumes what is
   configured, never that the configuration is calibrated.
5. **That the Limiter and the Allocator read the same row ACROSS A PROCESS
   BOUNDARY.** ARM 6 drives both readers in one process against one object. The
   wire between them is `scripts/nixrisk/picture.py`'s codec and
   `check_picture_atomicity`'s subject; the gap is named again at ARM 6's
   `margin_per_contract` sub-arm, where the gate reads the Allocator's COPY of
   the figure off the order rather than the picture's own row.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status, result_from_defects

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text; the only way to
# deduplicate them is a shared helper, which §4.2 forbids.
# R0903 (too-few-public-methods) disabled at module scope. Every class here is a
# PORT DOUBLE carrying exactly the port's own verb, or the counting tuple, or
# the recording proxy. A second method added to clear a class-shape threshold
# would make each a worse stand-in for the thing it doubles.
# pylint: disable=too-few-public-methods
# R0913 (too-many-arguments) disabled at module scope. `_picture` and
# `_allocator` take one keyword per DIMENSION an arm varies -- balance,
# committed, the position table, the margin map, the version stamp, the
# mirror state, the knob set. Folding them into a struct would hide which
# dimension a given arm is moving, and the arms' readability IS the
# argument that they measure different things.
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=duplicate-code
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The subject is a stdlib-only package in this tree and
#: is imported by path, not through the venv.
DEPENDS_ON: tuple[str, ...] = ()
#: The subject is loaded by prefixing `<nix_home>/scripts` onto `sys.path` and
#: purging any already-imported `nixalloc*`, `nixrisk*` and `risk_config` so the
#: modules come from the tree under measurement. Both mutations are restored and
#: both are declared: check contract v2 §12 checks declared claims against
#: OBSERVED ones, so an undeclared interpreter mutation would be a finding
#: against this gate. `risks/*.json` is READ and never written; a read is not an
#: observable claim under `scripts/nixverify/observe.py`, and no path here is
#: opened for writing.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No socket, no subprocess, no sleep, no poll. Every arm is arithmetic over
#: objects this process constructed.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is §7 and §16 of the FROZEN risk spec, which is never "
    "edited, and the measured side is the order in which the subject's own "
    "pass runs. An instrument empowered to rewrite the sizing pathway into "
    "agreement with the spec would be authoring the subject it certifies -- "
    "the same objection that makes check_limiter_gate non-correctable."
)
#: Genuinely DRIVEN here: every arm constructs objects from this module and
#: executes its `SizingAllocator.propose`.
SUBJECTS: tuple[str, ...] = ("scripts/nixalloc/sizing.py",)

NAME = "check_allocator_sizing"

SIZING = "scripts/nixalloc/sizing.py"
SITE = f"{SIZING}:SizingAllocator.propose"
ARITH_SITE = f"{SIZING}:module-level arithmetic"
CONFIG_SITE = f"{SIZING}:load_sizing_knobs"
GATE_SITE = "scripts/nixrisk/gate.py:GatePass.evaluate"

#: Non-vacuity floors. Each is a count this gate MUST reach or it has measured
#: nothing and says so rather than passing.
MIN_ARITHMETIC_CALLS = 3
MIN_SHARED_FIELDS = 3
MIN_PLANT_GAP = 50_000.0
MIN_BRANCHES = 2
MIN_GUARD_CASES = 4

#: The recorder tokens. `TRADABLE` and `SNAPSHOT` are written by the port
#: doubles; the rest are the subject's own module-level function names.
TRADABLE = "tradability.tradable"
SNAPSHOT = "mirror.snapshot"
ARITHMETIC: tuple[str, ...] = (
    "headroom_usd",
    "dollar_risk_per_contract",
    "risk_contracts",
    "margin_contracts",
    "select_instrument",
)

#: The instrument constants the doubles size against. Injected rather than
#: configured: the strategy contract (`nix_strategy_contract_v1.1.md` §7.2)
#: forbids hardcoding them and delivers them on the registration ACK.
#:
#: The risk spec's own tunables list carries no TICK_VALUE knob, so there is
#: no home in `risks/` for these and no second authority to drift from.
TICK_VALUE = 12.5
MICRO_RATIO = 10
BALANCE = 250_000.0
COMMITTED = 20_000.0
VERSION_STAMP = 903


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ---------------------------------------------------------------------------
# Loading the subject FROM THE TREE UNDER MEASUREMENT
# ---------------------------------------------------------------------------

_PURGE_PREFIXES = ("nixalloc", "nixrisk")
_PURGE_EXACT = ("risk_config",)


class _Subject:
    """The subject's modules, plus the Limiter's gate, from ONE tree.

    All from the same tree so the types the sizer imported and the types the
    gate imported are the SAME classes. Loading `sizing` from a `tmp_path` copy
    while building a picture from the repo would compare a plant against
    objects it never saw.

    Typed `Any` deliberately: which tree these came from is chosen at run time,
    and a static type here would be a claim about that choice.
    """

    def __init__(self, home: Path, sizing: Any, seam: Any, gate: Any) -> None:
        self.home = home
        self.sizing = sizing
        self.seam = seam
        self.gate = gate


def _purge() -> dict[str, Any]:
    saved = {
        key: value
        for key, value in sys.modules.items()
        if key in _PURGE_EXACT
        or any(key == p or key.startswith(f"{p}.") for p in _PURGE_PREFIXES)
    }
    for key in saved:
        del sys.modules[key]
    return saved


def load_subject(home: Path) -> tuple[_Subject | None, str]:
    """Import the subject from `home`. Returns `(subject, complaint)`.

    `sys.modules` is purged of the subject's packages before and after, because
    a gate that ran once against the repo would otherwise hand back the repo's
    module for every subsequent tree — and a plant that is never loaded is a
    plant that cannot fail.
    """
    scripts = home / "scripts"
    if not (scripts / "nixalloc" / "sizing.py").is_file():
        return None, f"{SIZING} is not on disk under {home} — nothing to drive"
    saved_path = list(sys.path)
    saved_mods = _purge()
    sys.path.insert(0, str(scripts.resolve()))
    try:
        seam = importlib.import_module("nixalloc.seam")
        sizing = importlib.import_module("nixalloc.sizing")
        gate = importlib.import_module("nixrisk.gate")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            None,
            f"{SIZING} would not import from {home}: {type(exc).__name__}: {exc}",
        )
    finally:
        _purge()
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path
    return _Subject(home, sizing, seam, gate), ""


# ---------------------------------------------------------------------------
# The instrumented population — objects that record their OWN invocation
# ---------------------------------------------------------------------------


class _RecordingTradability:
    """The §16 U1 fast-drop cache, marking the log where it was consulted."""

    def __init__(self, log: list[str], tradable: bool) -> None:
        self._log = log
        self._tradable = tradable

    def tradable(self, symbol: str) -> tuple[bool, str]:
        """`(tradable, reason)`, recorded at the position it was read."""
        del symbol
        self._log.append(TRADABLE)
        return self._tradable, "planted: not tradable"


class _RecordingMirror:
    """A read-only `MirrorPort` double. No publish verb exists on it."""

    def __init__(self, log: list[str], seam: Any, picture: Any, state: Any) -> None:
        self._log = log
        self._seam = seam
        self._picture = picture
        self._state = state

    def snapshot(self) -> Any:
        """One local read, recorded."""
        self._log.append(SNAPSHOT)
        fresh = self._state is self._seam.MirrorState.FRESH
        return self._seam.MirrorSnapshot(
            state=self._state,
            picture=self._picture if fresh else None,
            reason="planted mirror state",
        )

    def version(self) -> int:
        """The stamp on the held snapshot, or a negative value when there is none."""
        return -1 if self._picture is None else int(self._picture.version)


class _CountingPositions(tuple):  # type: ignore[type-arg]
    """A position table that counts every row anything pulls out of it.

    §11 keeps the aggregates as precomputed running figures on the snapshot.
    A sizer that re-summed the rows would satisfy every arithmetic assertion in
    this file and produce a non-zero count here.
    """

    traversals = 0

    def __iter__(self) -> Any:
        for row in tuple.__iter__(self):
            type(self).traversals += 1
            yield row

    def __getitem__(self, index: Any) -> Any:
        type(self).traversals += 1
        return tuple.__getitem__(self, index)


class _RecordingPicture:
    """Pass-through over one picture, logging `(reader, field, value)` per read."""

    def __init__(self, picture: Any, sink: list[Any], reader: str) -> None:
        self._picture = picture
        self._sink = sink
        self._reader = reader

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._picture, name)
        self._sink.append((self._reader, name, value))
        return value


class _Open:
    """A Phase-A flag port that blocks nothing, in symbol and global shapes."""

    def read(self, *args: Any) -> tuple[bool, str]:
        """`(blocked, reason)`."""
        del args
        return False, ""


class _Free:
    """The one-in-flight lock, held by nobody."""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)`."""
        del strategy_id
        return False, ""


class _Solvent:
    """A fresh net-liq mark far above the §6.5 floor.

    Deliberately enormous: §5's fail-fast stops dispatch at the first deny, and
    a survival floor that bit on ARM 6's inflated probe would prevent the one
    Phase-B rule that reads the picture's VERSION STAMP from ever running.
    """

    def mark(self) -> tuple[float, bool]:
        """`(net_liq, fresh)`."""
        return 1e18, True


class _Clear:
    """§11.5's HALT flag, clear — branch 0 must not short-circuit the pass."""

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`."""
        return False, ""


# ---------------------------------------------------------------------------
# The fixtures the arms drive
# ---------------------------------------------------------------------------


def _rows(subject: _Subject, *margins: float) -> tuple[Any, ...]:
    seam = subject.seam
    return tuple(
        seam.PositionRow(
            trade_id=f"t{i}",
            symbol="ES",
            strategy_id="s1",
            size=1,
            margin=margin,
            state=seam.PositionState.OPEN,
            stop_distance=20,
        )
        for i, margin in enumerate(margins)
    )


def _picture(
    subject: _Subject,
    *,
    balance: float = BALANCE,
    committed: float = COMMITTED,
    positions: Any = (),
    margins: dict[str, float] | None = None,
    version: int = VERSION_STAMP,
) -> Any:
    """One published snapshot. `committed` is a FIELD, never a derivation."""
    table = {"ES": 500.0, "MES": 50.0} if margins is None else margins
    return subject.seam.FinancialPicture(
        version=version,
        published_ts=1_700_000_000.0,
        balance=balance,
        positions=positions,
        margin_per_contract=MappingProxyType(dict(table)),
        sum_open_margin=committed,
        sum_reservations=0.0,
        committed=committed,
        deployable=balance * 0.70 - committed,
    )


def _knobs(subject: _Subject, **overrides: Any) -> Any:
    base: dict[str, Any] = {
        "per_trade_risk_usd": 100.0,
        "deployable_pct": 0.70,
        "symbol_cap": {"ES": 50},
        "slippage_pad_ticks": {"ES": 2},
        "micro_full_threshold": 2,
        "quant_tolerance": 0.25,
    }
    base.update(overrides)
    return subject.sizing.SizingKnobs(**base)


def _spec(subject: _Subject) -> Any:
    return subject.sizing.InstrumentSpec(
        symbol="ES", micro_symbol="MES", tick_value=TICK_VALUE, micro_ratio=MICRO_RATIO
    )


def _allocator(
    subject: _Subject,
    log: list[str],
    picture: Any,
    *,
    tradable: bool = True,
    state: Any = None,
    knobs: Any = None,
    instruments: Any = None,
) -> Any:
    seam = subject.seam
    return subject.sizing.SizingAllocator(
        mirror=_RecordingMirror(
            log, seam, picture, state if state is not None else seam.MirrorState.FRESH
        ),
        tradability=_RecordingTradability(log, tradable),
        instruments={"ES": _spec(subject)} if instruments is None else instruments,
        knobs=knobs if knobs is not None else _knobs(subject),
        bucket_cap=None,
    )


def _propose(subject: _Subject, allocator: Any, stop_ticks: int = 4) -> Any:
    seam = subject.seam
    return allocator.propose(
        "s1", "ES", seam.Side.LONG, stop_ticks, seam.StopMode.FIXED, 1.5
    )


class _Recorded:
    """Arithmetic recorders installed on the subject module, restored on exit."""

    def __init__(self, subject: _Subject, log: list[str]) -> None:
        self._module = subject.sizing
        self._log = log
        self._saved: dict[str, Any] = {}

    def __enter__(self) -> list[str]:
        for name in ARITHMETIC:
            real = getattr(self._module, name)
            self._saved[name] = real

            def recorder(*args: Any, _r: Any = real, _n: str = name, **kw: Any) -> Any:
                self._log.append(_n)
                return _r(*args, **kw)

            setattr(self._module, name, recorder)
        return self._log

    def __exit__(self, *exc: object) -> None:
        for name, real in self._saved.items():
            setattr(self._module, name, real)


# ---------------------------------------------------------------------------
# ARM 1 — EXECUTION ORDER (§16 U1)
# ---------------------------------------------------------------------------


def arm_execution_order(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """A dead signal drops before the mirror is read or any arithmetic runs."""
    defects: list[tuple[str, str]] = []
    live: list[str] = []
    with _Recorded(subject, live):
        sized = _propose(subject, _allocator(subject, live, _picture(subject)))
    arithmetic_seen = {name for name in live if name in ARITHMETIC}
    if len(arithmetic_seen) < MIN_ARITHMETIC_CALLS:
        return defects, (
            f"a KNOWN-SIZING pass recorded only {sorted(arithmetic_seen)} — fewer "
            f"than the {MIN_ARITHMETIC_CALLS} distinct arithmetic calls this "
            "instrument must see, so the recorders were not installed and the "
            "dead-signal log below would be empty for the wrong reason"
        )
    if sized.outcome is not subject.seam.ProposalOutcome.SIZED:
        return defects, f"the control pass did not size: {sized.outcome} {sized.reason}"

    defects += _order_defects(subject, live)
    dead: list[str] = []
    with _Recorded(subject, dead):
        dropped = _propose(
            subject, _allocator(subject, dead, _picture(subject), tradable=False)
        )
    if dead != [TRADABLE]:
        defects.append(
            (
                SITE,
                (
                    f"a dead signal ran {dead} — §16 U1 requires the tradability "
                    "fast-drop to be the FIRST and, on a drop, the ONLY thing "
                    "consulted; anything after it is a signal that was sized before "
                    "it was known to be dead"
                ),
            )
        )
    if dropped.outcome is not subject.seam.ProposalOutcome.NOT_TRADABLE:
        defects.append(
            (SITE, f"a dead signal produced {dropped.outcome}, not NOT_TRADABLE")
        )
    if dropped.rationale.snapshot_version >= 0:
        defects.append(
            (
                SITE,
                (
                    f"a dead signal's rationale claims snapshot version "
                    f"{dropped.rationale.snapshot_version} — a drop that never read "
                    "the mirror must not name a version it did not observe"
                ),
            )
        )
    return defects + _stale_defects(subject), ""


def _order_defects(subject: _Subject, live: list[str]) -> list[tuple[str, str]]:
    """The live pass's log is fast-drop, then ONE snapshot, then arithmetic."""
    del subject
    defects: list[tuple[str, str]] = []
    if not live or live[0] != TRADABLE:
        defects.append(
            (SITE, f"the pass began with {live[:1]}, not the §16 U1 fast-drop")
        )
    if len(live) < 2 or live[1] != SNAPSHOT:
        defects.append((SITE, f"the mirror was not the second thing read: {live[:3]}"))
    if live.count(SNAPSHOT) != 1:
        defects.append(
            (
                SITE,
                (
                    f"the pass read the mirror {live.count(SNAPSHOT)} times — §3's "
                    "atomicity rule gives one pass ONE version, and a second read "
                    "is the torn picture §16 U2 exists to prevent"
                ),
            )
        )
    stray = [name for name in live[2:] if name not in ARITHMETIC]
    if stray:
        defects.append((SITE, f"unexpected reads after the mirror: {stray}"))
    return defects


def _stale_defects(subject: _Subject) -> list[tuple[str, str]]:
    """§12.7: a mirror that is not `sizeable` never reaches the arithmetic."""
    seam = subject.seam
    defects: list[tuple[str, str]] = []
    for state in (
        seam.MirrorState.EMPTY,
        seam.MirrorState.PARTIAL,
        seam.MirrorState.STALE,
    ):
        log: list[str] = []
        with _Recorded(subject, log):
            proposal = _propose(
                subject, _allocator(subject, log, _picture(subject), state=state)
            )
        if set(log) & set(ARITHMETIC):
            defects.append(
                (
                    SITE,
                    (
                        f"mirror state {state.value} still reached the arithmetic "
                        f"({sorted(set(log) & set(ARITHMETIC))}) — §12.7 forbids "
                        "sizing on a half-built mirror"
                    ),
                )
            )
        if proposal.outcome is not seam.ProposalOutcome.STALE_MIRROR:
            defects.append(
                (SITE, f"mirror state {state.value} produced {proposal.outcome}")
            )
    return defects


# ---------------------------------------------------------------------------
# ARM 2 — THE INSTRUMENT'S DISCRIMINATING POWER (the falsifier)
# ---------------------------------------------------------------------------


def arm_falsifier(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Drive a sizes-first allocator and FAIL unless the instrument catches it.

    Not a test of the subject. A test of this gate: ARM 1's verdict is only
    evidence if the log it reads could have come out wrong.
    """
    log: list[str] = []
    picture = _picture(subject)
    mirror = _RecordingMirror(
        log, subject.seam, picture, subject.seam.MirrorState.FRESH
    )
    tradability = _RecordingTradability(log, False)

    with _Recorded(subject, log):
        snapshot = mirror.snapshot()
        subject.sizing.headroom_usd(snapshot.picture, 0.70)
        tradability.tradable("ES")

    if log[:1] == [TRADABLE]:
        return [
            (
                f"{__file__}:arm_falsifier",
                (
                    "the instrument reported the §16 U1 order for an allocator that "
                    "demonstrably sized BEFORE it asked whether the symbol was "
                    f"tradable (log {log}) — every other arm's log is unfalsifiable"
                ),
            )
        ], ""
    if "headroom_usd" not in log or TRADABLE not in log:
        return [], (
            f"the falsifier's own log is {log}: the recorders did not capture "
            "both the arithmetic and the port read, so this arm proved nothing"
        )
    return [], ""


# ---------------------------------------------------------------------------
# ARM 3 — THE PUBLISHED `committed` (§16 U2)
# ---------------------------------------------------------------------------


def arm_published_committed(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """The plant: `committed` disagrees with the rows, by a floor-checked gap."""
    rows = _rows(subject, *([10_000.0] * 9))
    derived = sum(row.margin for row in rows)
    gap = abs(derived - COMMITTED)
    if gap < MIN_PLANT_GAP:
        return [], (
            f"the planted disagreement is only {gap} — under {MIN_PLANT_GAP} the "
            "published and re-derived answers are too close for the comparison "
            "below to distinguish them"
        )

    _CountingPositions.traversals = 0
    picture = _picture(subject, positions=_CountingPositions(rows))
    proposal = _propose(subject, _allocator(subject, [], picture))

    defects: list[tuple[str, str]] = []
    expected = 0.70 * BALANCE - COMMITTED
    if abs(proposal.rationale.headroom - expected) > 1e-6:
        defects.append(
            (
                ARITH_SITE,
                (
                    f"headroom is {proposal.rationale.headroom!r}; §16 U2 gives "
                    f"0.70 x {BALANCE} - PUBLISHED committed {COMMITTED} = {expected!r}. "
                    f"Re-deriving committed from the {len(rows)} position rows would "
                    f"give {0.70 * BALANCE - derived!r} — one source of truth, lost"
                ),
            )
        )
    if _CountingPositions.traversals:
        defects.append(
            (
                ARITH_SITE,
                (
                    f"the pass pulled {_CountingPositions.traversals} row(s) out of "
                    "the position table — every figure it needs is published as a "
                    "running aggregate under one version stamp (§3, §11)"
                ),
            )
        )
    if proposal.rationale.contention is not subject.seam.ContentionPolicy.FCFS:
        defects.append(
            (
                SITE,
                (
                    f"contention recorded as {proposal.rationale.contention} — §6.6's "
                    "ranking table has no writer, so FCFS is the only reachable policy"
                ),
            )
        )
    if "NOT APPLIED" not in proposal.rationale.note:
        defects.append(
            (
                SITE,
                (
                    "the rationale does not say the §7 correlation-bucket cap was "
                    "skipped, so a green here would imply coverage this gate lacks"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 4 — THE GUARDS (§15 C3, §7)
# ---------------------------------------------------------------------------


def arm_guards(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Zero stop, missing margin, negative headroom, and the slippage pad."""
    seam = subject.seam
    defects: list[tuple[str, str]] = []
    cases = 0

    for stop in (0, -1):
        cases += 1
        proposal = _propose(subject, _allocator(subject, [], _picture(subject)), stop)
        if proposal.outcome is not seam.ProposalOutcome.NO_SIZE_DENY:
            defects.append(
                (
                    SITE,
                    (
                        f"stop_ticks={stop} produced {proposal.outcome} with "
                        f"{proposal.contracts} contract(s) — §15 C3 makes an invalid "
                        "stop a DENY the Limiter issues, and the Allocator must not "
                        "manufacture a size to make it deniable"
                    ),
                )
            )
        if proposal.contracts or proposal.order is not None:
            defects.append(
                (SITE, f"stop_ticks={stop} carried a size: {proposal.contracts}")
            )

    cases += 1
    missing = _propose(
        subject, _allocator(subject, [], _picture(subject, margins={"NQ": 100.0}))
    )
    if missing.outcome is not seam.ProposalOutcome.NOT_TRADABLE:
        defects.append(
            (
                SITE,
                (
                    f"a symbol absent from the published margin cache produced "
                    f"{missing.outcome} — §7's guard is not-tradable"
                ),
            )
        )

    cases += 1
    defects += _clamp_defects(subject)
    defects += _pad_defects(subject)
    if cases < MIN_GUARD_CASES:
        return defects, f"only {cases} guard cases were driven"
    return defects, ""


def _clamp_defects(subject: _Subject) -> list[tuple[str, str]]:
    """§7: every term clamps ≥ 0, on a picture whose headroom is negative."""
    proposal = _propose(
        subject, _allocator(subject, [], _picture(subject, committed=BALANCE))
    )
    rationale = proposal.rationale
    negatives = {
        field: value
        for field, value in (
            ("contracts", proposal.contracts),
            ("risk_contracts", rationale.risk_contracts),
            ("margin_contracts", rationale.margin_contracts),
            ("symbol_cap", rationale.symbol_cap),
        )
        if value < 0
    }
    if negatives:
        return [
            (ARITH_SITE, f"negative-floor artifacts survived the clamp: {negatives}")
        ]
    if rationale.headroom >= 0.0:
        return [
            (
                ARITH_SITE,
                (
                    f"headroom {rationale.headroom!r} is not negative on a picture "
                    f"whose committed ({BALANCE}) exceeds 0.70 x balance — the clamp "
                    "arm never reached the state it exists to measure"
                ),
            )
        ]
    if proposal.contracts:
        return [
            (
                SITE,
                f"a negative headroom still sized {proposal.contracts} contract(s)",
            )
        ]
    return []


def _pad_defects(subject: _Subject) -> list[tuple[str, str]]:
    """§7: the slippage pad is INSIDE the dollar-risk denominator, or it is not."""
    answers = {}
    for pad in (2, 4):
        proposal = _propose(
            subject,
            _allocator(
                subject,
                [],
                _picture(subject),
                knobs=_knobs(subject, slippage_pad_ticks={"ES": pad}),
            ),
        )
        answers[pad] = (
            proposal.contracts,
            None if proposal.order is None else proposal.order.symbol,
        )
    if answers[2] == answers[4]:
        return [
            (
                ARITH_SITE,
                (
                    f"pads of 2 and 4 ticks both produced {answers[2]} — the pad is "
                    "not inside `(stop_ticks + slippage_pad) x tick_value`, so "
                    "`risk_$` is dishonest through exactly the spikes §7 added it for"
                ),
            )
        ]
    if answers[2][1] != answers[4][1]:
        return [
            (
                ARITH_SITE,
                (
                    f"the two pad cases landed on different instruments {answers} — "
                    "instrument selection, not the pad, could be what moved the "
                    "number, so this sub-arm would not be measuring the pad"
                ),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 5 — §16 U4, BOTH BRANCHES
# ---------------------------------------------------------------------------


def arm_single_instrument(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Fulls and micros are both REACHED, and no proposal mixes them."""
    seam = subject.seam
    defects: list[tuple[str, str]] = []
    branches: dict[str, int] = {"ES": 0, "MES": 0}
    for stop in range(1, 40):
        proposal = _propose(subject, _allocator(subject, [], _picture(subject)), stop)
        if proposal.outcome is not seam.ProposalOutcome.SIZED:
            continue
        symbol = proposal.order.symbol
        if symbol not in branches:
            defects.append(
                (SITE, f"stop {stop} selected {symbol!r}, which is neither leg")
            )
            continue
        branches[symbol] += 1
        if proposal.order.qty != proposal.contracts:
            defects.append(
                (
                    SITE,
                    (
                        f"stop {stop}: order qty {proposal.order.qty} disagrees with "
                        f"proposal contracts {proposal.contracts}"
                    ),
                )
            )
    reached = [leg for leg, count in branches.items() if count]
    if len(reached) < MIN_BRANCHES:
        return defects, (
            f"only {reached} was ever selected across 39 stop distances — §16 U4's "
            "rule has two branches and a rule exercised on one has not been "
            "exercised"
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 6 — ONE VERSIONED ROW, TWO READERS (§6.4)
# ---------------------------------------------------------------------------


def _gate_pass(subject: _Subject) -> Any:
    gate = subject.gate
    manifest = gate.default_manifest(
        blackout=_Open(),
        tradability=_Open(),
        staleness=_Open(),
        clock_skew=_Open(),
        in_flight=_Free(),
        net_liq=_Solvent(),
        deployable_fraction=0.70,
        survival_safety_pad=0.10,
        coherence_tolerance=0.01,
    )
    return gate.GatePass(_Clear(), manifest, None)


def _both_readers(subject: _Subject, alloc_row: Any, gate_row: Any) -> dict[str, Any]:
    """Drive the Allocator and the REAL gate, recording every field each reads.

    The gate is driven twice: once as sized, once with an inflated quantity.
    §3's Phase-B rules build their reason strings before branching, so the
    second pass is what makes the gate read the picture's VERSION STAMP — the
    field §6.4's identity claim is actually about.
    """
    sink: list[Any] = []
    proposal = _propose(
        subject,
        _allocator(subject, [], _RecordingPicture(alloc_row, sink, "allocator")),
    )
    if proposal.order is None:
        return {"proposal": proposal, "seen": None}
    gate_pass = _gate_pass(subject)
    outcome = gate_pass.evaluate(
        proposal.order, _RecordingPicture(gate_row, sink, "gate"), 1.5
    )
    gate_pass.evaluate(
        dataclasses.replace(proposal.order, qty=1_000_000),
        _RecordingPicture(gate_row, sink, "gate"),
        1.5,
    )
    seen: dict[str, dict[str, Any]] = {"allocator": {}, "gate": {}}
    for reader, field, value in sink:
        seen[reader].setdefault(field, value)
    return {"proposal": proposal, "seen": seen, "outcome": outcome}


def arm_one_versioned_row(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Both readers observe identical values for every field both touched."""
    row = _picture(subject)
    result = _both_readers(subject, row, row)
    if result["seen"] is None:
        return [], f"the control pass produced no order: {result['proposal'].reason}"
    seen = result["seen"]
    shared = set(seen["allocator"]) & set(seen["gate"])
    if len(shared) < MIN_SHARED_FIELDS or "version" not in shared:
        return [], (
            f"only {sorted(shared)} was read by BOTH the Allocator and the gate — "
            f"under {MIN_SHARED_FIELDS} shared fields, or without the version "
            "stamp among them, the identity claim is about the empty set"
        )

    defects = [
        (
            GATE_SITE,
            (
                f"{field}: the Allocator observed {seen['allocator'][field]!r} and the "
                f"gate observed {seen['gate'][field]!r} on ONE picture — §6.4's "
                "'same versioned row, identical bytes by construction', refuted"
            ),
        )
        for field in sorted(shared)
        if seen["allocator"][field] != seen["gate"][field]
    ]
    defects += _identity_falsifier(subject)
    defects += _margin_copy_defects(subject, result["proposal"], row)
    return defects, ""


def _identity_falsifier(subject: _Subject) -> list[tuple[str, str]]:
    """Two different rows must make the same comparison disagree."""
    alloc_row = _picture(subject)
    gate_row = _picture(subject, balance=BALANCE / 2, version=VERSION_STAMP + 1)
    result = _both_readers(subject, alloc_row, gate_row)
    if result["seen"] is None:
        return [
            (
                f"{__file__}:_identity_falsifier",
                (
                    "the falsifier produced no order, so the identity arm above is "
                    "unfalsifiable"
                ),
            )
        ]
    seen = result["seen"]
    shared = set(seen["allocator"]) & set(seen["gate"])
    disagreed = {f for f in shared if seen["allocator"][f] != seen["gate"][f]}
    if not {"balance", "version"} <= disagreed:
        return [
            (
                f"{__file__}:_identity_falsifier",
                (
                    f"two readers were handed two DIFFERENT rows and the comparison "
                    f"flagged only {sorted(disagreed)} — it cannot refute §6.4's "
                    "claim, so its agreement verdict is not evidence"
                ),
            )
        ]
    return []


def _margin_copy_defects(
    subject: _Subject, proposal: Any, row: Any
) -> list[tuple[str, str]]:
    """THE NAMED GAP: the gate reads margin off the ORDER, not off the picture.

    `AggregateMarginCapRule` and `DeployableCeilingRule` divide by
    `order.margin_per_contract`. For that one figure the identity is carried by
    the Allocator's copy, so the strongest provable statement is that the copy
    equals the published row at the version the Allocator sized against.
    """
    source = (subject.home / "scripts" / "nixrisk" / "gate.py").read_text("utf-8")
    if "picture.margin_per_contract" in source:
        return [
            (
                GATE_SITE,
                (
                    "the gate now reads margin from the PICTURE; this gate's weaker "
                    "copy-equality claim is no longer the strongest one available "
                    "and must be re-derived"
                ),
            )
        ]
    published = row.margin_per_contract.get(proposal.order.symbol)
    if proposal.order.margin_per_contract != published:
        return [
            (
                SITE,
                (
                    f"the order carries margin {proposal.order.margin_per_contract!r} "
                    f"for {proposal.order.symbol} while the published row at version "
                    f"{row.version} says {published!r} — the gate divides by the "
                    "order's copy, so the two readers are on different numbers"
                ),
            )
        ]
    if proposal.rationale.snapshot_version != row.version:
        return [
            (
                SITE,
                (
                    f"the rationale names version {proposal.rationale.snapshot_version} "
                    f"but sized against {row.version}"
                ),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 7 — 0.70 IS READ, NOT CARVED (§12A)
# ---------------------------------------------------------------------------


def arm_knob_is_read(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """`DEPLOYABLE_PCT` comes out of its ONE physical home, not out of this code."""
    config = subject.home / "risks" / "limiter.config.json"
    if not config.is_file():
        return [], f"{config} is absent — the knob's home cannot be read"
    landed = json.loads(config.read_text("utf-8")).get("deployable_pct")
    saved_path = list(sys.path)
    saved_mods = _purge()
    sys.path.insert(0, str((subject.home / "scripts").resolve()))
    try:
        knobs = subject.sizing.load_sizing_knobs(subject.home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [], f"the loader raised {type(exc).__name__}: {exc}"
    finally:
        _purge()
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path

    defects: list[tuple[str, str]] = []
    if knobs.deployable_pct != landed:
        defects.append(
            (
                CONFIG_SITE,
                (
                    f"the loader returned {knobs.deployable_pct!r} while "
                    f"{config} holds {landed!r} — §12A owns the value and the "
                    "loader must not transform it"
                ),
            )
        )
    source = (subject.home / SIZING).read_text("utf-8")
    carved = [
        token for token in ("0.70 *", "0.7 *", "* 0.70", "* 0.7") if token in source
    ]
    if carved:
        defects.append(
            (
                CONFIG_SITE,
                (
                    f"{SIZING} carries arithmetic on a carved deployable fraction "
                    f"{carved} — a second physical home for a number "
                    "risks/limiter.config.json already owns, free to disagree with "
                    "the gate that enforces it"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

#: What a PASS here does and does NOT stand for. Attached to the FAIL as well:
#: an operator reading a failure needs to know what was successfully measured.
_EVIDENCE = (
    "execution order read from the subject's OWN arithmetic recorders, not "
    "from source order; the sizes-first falsifier was driven and caught; "
    f"committed planted {MIN_PLANT_GAP:.0f}+ away from the row sum with a "
    "traversal-counting position table; both fulls and micros branches "
    f"reached; >= {MIN_SHARED_FIELDS} picture fields read by BOTH the "
    "Allocator and the real GatePass, version stamp among them; the §7 "
    "correlation-bucket cap was NOT exercised (bucket_cap=None)"
)


def _measure(subject: _Subject) -> CheckResult:
    """EVERY arm runs; the aggregate follows check contract v2 rule 4.

    Rule 4 orders the aggregate `Fail > Cannot-measure > Guarded > Pass`, so an
    arm that refused does NOT suppress a violation another arm positively
    OBSERVED. Returning on the first refusal would do exactly that, and it is a
    live hazard here rather than a theoretical one: a subject that re-derives
    `committed` stops reading the published field, which both makes ARM 3's
    finding true and shrinks ARM 6's shared-field set below its floor. The first
    arm measured a defect; the second measured nothing. Reporting the second
    would hide the first.
    """
    defects: list[tuple[str, str]] = []
    refusals: list[str] = []
    for arm in (
        arm_execution_order,
        arm_falsifier,
        arm_published_committed,
        arm_guards,
        arm_single_instrument,
        arm_one_versioned_row,
        arm_knob_is_read,
    ):
        found, refusal = arm(subject)
        defects.extend(found)
        if refusal:
            refusals.append(f"{arm.__name__}: {refusal}")
    if defects:
        result = result_from_defects(NAME, defects, _EVIDENCE)
        if not refusals:
            return result
        return dataclasses.replace(
            result,
            evidence=f"{_EVIDENCE}; arms that also REFUSED: {'; '.join(refusals)}",
        )
    if refusals:
        return _cannot_measure(
            "; ".join(refusals) + " (§5.3: an empty scope is never a PASS)"
        )
    return result_from_defects(NAME, defects, _EVIDENCE)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the shipped sizing pathway and read what actually ran. Never repairs."""
    try:
        subject, complaint = load_subject(ctx.nix_home)
        if complaint or subject is None:
            return _cannot_measure(
                complaint
                or f"{SIZING}: neither a subject nor a complaint — the gate's own "
                "pre-flight returned nothing, which is never a verdict"
            )
        return _measure(subject)
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
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
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
