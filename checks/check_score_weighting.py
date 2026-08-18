#!/usr/bin/env python3
"""Gate: §6.6:459's score → sizing weight is REAL — it differs, it moves a SIZE,
and its bounds bind — measured by driving the shipped pathway, never by reading it.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless a document is
named on the same line.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9). The
property, stated against the frozen risk spec: *the weight the Allocator
derives from the ranking table changes how many contracts a GO is sized for, in
the direction `docs/nics_risk_subsystem_spec_v1.3.md` §6.6:431 names, and only
where a weight is allowed to reach.* Seven arms serve that single property.

------------------------------------------------------------------------------
WHY THIS GATE EXISTS AT ALL, AND WHAT IT IS AGAINST
------------------------------------------------------------------------------
`nixalloc.contention.NEUTRAL_WEIGHT` was `1.0` for every contender under BOTH
policies from ARC 031 to ARC 036, and `ContentionRanking.weights` existed the
whole time (CHECK-DEBT **D3.260**). A test over that object passed on every
race, every policy and every score — while proving nothing, because every value
it compared was the same constant. **A weighting gate in which every weight is
1.0 is green over nothing**, and that shape is what this file is built against
rather than something it merely avoids.

So no arm here asserts that a weight EXISTS or that it has a plausible value.
Each requires a DIFFERENCE that a constant cannot produce:

  * **ARM 0 — the literals are the ARCHITECT'S, not this tree's.** §6.6:459
    gives the Allocator the read "to weight sizing" and the FROZEN SPEC FIXES
    NO TRANSFORM, so the four constants are an architect ruling recorded in
    `downloads/ARC037-SEAM-FREEZE.md` SEAM (b). This arm parses them out of
    that document and compares them to the module's own. A tree that invented
    its own transform, or a document that moved, is a defect and not a green.
    The reference side is a file this gate does not write.

  * **ARM 1 — the weights DIFFER.** A race of three contenders with three
    distinct realized-P&L EMAs, driven through the real `contention.rank`
    against a live table port, must come back `PERFORMANCE_WEIGHTED` with at
    least `MIN_DISTINCT_WEIGHTS` DISTINCT values in `weights`, ordered so the
    best rank carries the largest (§6.6:431 "feed the winners"). The falsifier
    is driven in the same arm: a ranking whose weights are pinned to
    `NEUTRAL_WEIGHT` must be CAUGHT, naming the constant.

  * **ARM 2 — the weight moves a SIZE, not a number.** Two GOs identical in
    every input — same symbol, same side, same stop, same picture, same knobs,
    same instrument — differing ONLY in their rank, must produce
    `MIN_DISTINCT_SIZES` DISTINCT contract counts out of the real
    `SizingAllocator.propose`. Two distinct weights would not be evidence: a
    computed weight that is never applied produces exactly that. The falsifier
    — an allocator that accepts the weight and drops it — is driven and must
    be caught.

  * **ARM 3 — the clamp BINDS, at a rank anybody can drive.** At `n = 8` the
    raw transform gives `1.875` at rank 1 and `0.125` at rank 8, both outside
    the bounds. The arm recomputes both raws from the SUBJECT's own constants,
    requires each to be genuinely outside its bound (or the clamp is
    decoration and the arm refuses), requires the returned weight to BE the
    bound, and requires the ranking's reason to NAME which bound bound it
    (§18: the reason, never the value alone).

  * **ARM 4 — every declared NEUTRAL case, each driven separately.** No port;
    a port reporting itself unavailable; a port that RAISES; an absent
    pair-row; tied EMAs; cold start with no rows at all; and a field of ONE.
    Each must be exactly `NEUTRAL_WEIGHT` — §6.6:455 makes all of them FCFS
    cases and §6.6:466 makes FCFS structurally neutral, which is a statement
    about the SIZE as well as the order. They are driven one at a time because
    a single "all fallbacks are neutral" assertion passes when five of the six
    routes are unreachable.

  * **ARM 5 — the direction that must not exist.** Margin, the symbol cap and
    the correlation-bucket cap are capital-safety ceilings. This arm drives a
    margin-bound case and a cap-bound case at the CEILING weight and at the
    FLOOR weight and requires the size to be IDENTICAL — a safety ceiling that
    moved with a performance score is the defect this arm is for, and it is
    the one defect here that costs money rather than accuracy.

  * **ARM 6 — an illegal weight is REFUSED, loudly.** NaN, zero, negative, and
    both sides of the frozen band must raise out of `propose`, and the message
    must name the CONDITION (§18). A clamp would satisfy every other arm in
    this file: the sizes would still differ, the bounds would still hold, and a
    caller wiring a broken weight would never learn.

------------------------------------------------------------------------------
`debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
MEASURING NOTHING. Six routes, each closed by a mechanism:
------------------------------------------------------------------------------
 1. **Every weight is `NEUTRAL_WEIGHT`** — the D3.260 shape exactly. Closed by
    ARM 1's `MIN_DISTINCT_WEIGHTS` floor, and by its falsifier, which pins the
    transform back to the constant and must be caught naming it.
 2. **The weight is computed and never applied.** Closed by ARM 2, which
    compares SIZES out of the real sizing path and drops the weight in its own
    falsifier to prove the comparison can notice.
 3. **The clamp is unreachable decoration.** Closed by ARM 3, which refuses
    (CANNOT_MEASURE, never PASS) unless both raws are genuinely outside their
    bounds before it judges anything.
 4. **The subject never loads**, so every arm skips. Closed: `load_subject`
    returns a complaint and the verdict is CANNOT_MEASURE.
 5. **The neutral cases are one case counted six times.** Closed: ARM 4 drives
    six distinct ROUTES into the fallback and names each in its evidence, and
    requires the routes to report six distinct REASONS — one constructor is
    used for all of them by design (`_fallback`), so identical reasons would
    mean the routes collapsed.
 6. **The reference side is this tree's own opinion.** Closed by ARM 0: the
    four literals are read out of the architect's freeze document, which no
    part of this gate writes, and a missing document is a refusal.

------------------------------------------------------------------------------
WHAT THIS GATE CANNOT PROVE — stated, so no green implies it
------------------------------------------------------------------------------
1. **That any weight is ever applied IN PRODUCTION.** Nothing in this tree
   publishes a ranking table (CHECK-DEBT D3.263), so `available()` answers
   False, `rank` takes §6.6:465's fallback, and every live weight is
   `NEUTRAL_WEIGHT`. This gate proves the pathway weights WHEN A TABLE IS
   PRESENT; it constructs that table itself.
2. **That the four literals are the RIGHT ones.** They are an architect ruling
   over a transform the frozen spec does not fix. This gate proves the tree
   implements the ruling, never that the ruling is calibrated.
3. **That `weight` is passed by any caller.** `propose`'s parameter is
   keyword-only and defaults to neutral; who supplies it is
   `scripts/nixalloc/wiring.py`'s property and CHECK-DEBT D3.290's subject.
4. **Anything about the correlation-bucket cap's own arithmetic.** ARM 5 drives
   it as `None` and proves only that the two weighted drives agree; the cap is
   `scripts/nixalloc/caps.py`'s subject and `check_allocator_caps`' gate.
"""

from __future__ import annotations

import dataclasses
import importlib
import math
import re
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
# pylint: disable=duplicate-code
# R0903 (too-few-public-methods) disabled at module scope. Every class here is a
# PORT DOUBLE carrying exactly the port's own verb. A second method added to
# clear a class-shape threshold would make each a worse stand-in.
# pylint: disable=too-few-public-methods
# R0913 (too-many-arguments) disabled at module scope: `_picture` and `_knobs`
# take one keyword per DIMENSION an arm varies, and the arms' readability IS the
# argument that they measure different things.
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The subject is a stdlib-only package in this tree and
#: is imported by path, not through the venv.
DEPENDS_ON: tuple[str, ...] = ()
#: The subject is loaded by prefixing `<nix_home>/scripts` onto `sys.path` and
#: purging any already-imported `nixalloc*`, `nixrisk*` and `risk_config`, so the
#: modules come from the tree under measurement. Both mutations are restored and
#: both are declared: check contract v2 §12 checks declared claims against
#: OBSERVED ones, so an undeclared interpreter mutation would be a finding
#: against this gate. `downloads/ARC037-SEAM-FREEZE.md` is READ and never
#: written, and a read is not an observable claim under
#: `scripts/nixverify/observe.py`.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: A block halts on any member's failure; this gate's failure is a finding about
#: two modules, never a reason to stop measuring the rest of the tree.
ON_FAIL = "continue"
#: No socket, no subprocess, no sleep, no poll. Every arm is arithmetic over
#: objects this process constructed.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is an ARCHITECT RULING recorded in "
    "downloads/ARC037-SEAM-FREEZE.md over a transform the frozen risk spec "
    "deliberately does not fix, and the measured side is a size driven out of "
    "the shipped sizing pathway. An instrument empowered to edit either would "
    "be authoring the ruling it certifies or writing the implementation it "
    "judges -- the same objection that makes check_allocator_sizing "
    "non-correctable"
)
#: Genuinely DRIVEN here: every arm constructs objects from these modules and
#: executes `contention.rank` and `SizingAllocator.propose`.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixalloc/contention.py",
    "scripts/nixalloc/sizing.py",
)

NAME = "check_score_weighting"

CONTENTION = "scripts/nixalloc/contention.py"
SIZING = "scripts/nixalloc/sizing.py"
FREEZE = "downloads/ARC037-SEAM-FREEZE.md"

TRANSFORM_SITE = f"{CONTENTION}:weight_for"
RANK_SITE = f"{CONTENTION}:rank"
SIZE_SITE = f"{SIZING}:SizingAllocator.propose"
GUARD_SITE = f"{SIZING}:_validated_weight"

#: Non-vacuity floors. Each is a count this gate MUST reach or it has measured
#: nothing and says so rather than passing.
MIN_DISTINCT_WEIGHTS = 2
MIN_DISTINCT_SIZES = 2
MIN_NEUTRAL_ROUTES = 6
MIN_REFUSALS = 5

#: The field size at which BOTH bounds are reachable by a real rank. Chosen by
#: the architect ruling, not by this gate: SEAM (b) states `raw(1, 8) = 1.875`
#: and `raw(8, 8) = 0.125`, and ARM 3 recomputes both from the subject's own
#: constants rather than trusting either figure.
CLAMP_FIELD = 8

#: The four literals the freeze fixes, by name. The VALUES are read out of the
#: document; only the names are spelled here, because a name is what a parser
#: needs and a value is what it must not assume.
FROZEN_NAMES = ("NEUTRAL_WEIGHT", "WEIGHT_STEP", "WEIGHT_FLOOR", "WEIGHT_CEILING")

#: One `NAME = value` line inside the freeze's SEAM (b) block.
_FROZEN_LINE = re.compile(
    r"^\s*(NEUTRAL_WEIGHT|WEIGHT_STEP|WEIGHT_FLOOR|WEIGHT_CEILING)\s*=\s*"
    r"([0-9]+\.[0-9]+)\s*$",
    re.MULTILINE,
)
#: SEAM (b)'s own section, anchored on its heading so a document that was
#: reorganised is a loud refusal rather than an empty expected set silently
#: agreeing with an empty measured one (§7.12/2).
_SEAM_B = re.compile(
    r"^## SEAM \(b\).*?(?=^## SEAM \(c\)|\Z)", re.MULTILINE | re.DOTALL
)

#: Instrument constants the doubles size against, injected rather than
#: configured: the strategy contract (`nix_strategy_contract_v1.1.md` §7.2)
#: forbids hardcoding them and delivers them on the registration ACK.
TICK_VALUE = 12.5
MICRO_RATIO = 10
BALANCE = 250_000.0
COMMITTED = 20_000.0
VERSION_STAMP = 937
PER_TRADE_RISK = 100.0
STOP_TICKS = 4


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ---------------------------------------------------------------------------
# Loading the subject FROM THE TREE UNDER MEASUREMENT
# ---------------------------------------------------------------------------

_PURGE_PREFIXES = ("nixalloc", "nixrisk")
_PURGE_EXACT = ("risk_config",)


class _Subject:
    """The subject's modules, plus the architect's frozen literals, from ONE tree.

    Typed `Any` deliberately: which tree these came from is chosen at run time,
    and a static type here would be a claim about that choice.
    """

    def __init__(self, home: Path, contention: Any, sizing: Any, seam: Any) -> None:
        self.home = home
        self.contention = contention
        self.sizing = sizing
        self.seam = seam


def _purge() -> dict[str, Any]:
    """Remove ONLY the subject's own modules, and hand back what was removed.

    Removing only the declared prefixes rather than clearing `sys.modules` is
    CHECK-DEBT D3.270's repair, inherited deliberately: a gate that cleared the
    table evicted C extension modules and handed four unrelated gates a
    `zmq.Again` their own correct handler could not catch.
    """
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
    if not (scripts / "nixalloc" / "contention.py").is_file():
        return None, f"{CONTENTION} is not on disk under {home} — nothing to drive"
    if not (scripts / "nixalloc" / "sizing.py").is_file():
        return None, f"{SIZING} is not on disk under {home} — nothing to drive"
    saved_path = list(sys.path)
    saved_mods = _purge()
    sys.path.insert(0, str(scripts.resolve()))
    try:
        seam = importlib.import_module("nixalloc.seam")
        contention = importlib.import_module("nixalloc.contention")
        sizing = importlib.import_module("nixalloc.sizing")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            None,
            (
                f"{CONTENTION}/{SIZING} would not import from {home}: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    finally:
        _purge()
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path
    return _Subject(home, contention, sizing, seam), ""


# ---------------------------------------------------------------------------
# The population the arms drive
# ---------------------------------------------------------------------------


class _Table:
    """A live `RankingTablePort` over a fixed row set. READ verbs only."""

    def __init__(
        self, rows: dict[tuple[str, str], Any], available: bool = True
    ) -> None:
        self._rows = rows
        self._available = available

    def available(self) -> bool:
        """§6.6:465's absent-or-stale predicate."""
        return self._available

    def row(self, strategy_id: str, symbol: str) -> Any:
        """The pair's row, or None. O(1), never math."""
        return self._rows.get((strategy_id, symbol))


class _Raising:
    """A port that THROWS. §6.6:467 forbids a scoring outage halting order flow."""

    def available(self) -> bool:
        """Raises, deliberately."""
        raise RuntimeError("planted: the availability probe is down")

    def row(self, strategy_id: str, symbol: str) -> Any:
        """Never reached."""
        del strategy_id, symbol
        raise RuntimeError("planted: the row lookup is down")


class _Mirror:
    """A read-only `MirrorPort` double. No publish verb exists on it."""

    def __init__(self, seam: Any, picture: Any) -> None:
        self._seam = seam
        self._picture = picture

    def snapshot(self) -> Any:
        """One local read of one published picture."""
        return self._seam.MirrorSnapshot(
            state=self._seam.MirrorState.FRESH,
            picture=self._picture,
            reason="constructed by check_score_weighting",
        )

    def version(self) -> int:
        """The stamp on the held snapshot."""
        return int(self._picture.version)


class _Tradable:
    """The §16 U1 fast-drop cache, permitting everything."""

    def tradable(self, symbol: str) -> tuple[bool, str]:
        """`(tradable, reason)`."""
        del symbol
        return True, ""


def _contenders(subject: _Subject, count: int) -> list[Any]:
    """A field of `count`, whose ARRIVAL order disagrees with their scores.

    Arrival descends while the scores below ascend, so an ordering that merely
    echoed arrival — or the alphabet — would disagree with the one this gate
    requires. §7.12/2 of `contention.py`'s own standing question, honoured at
    the fixture rather than asserted in prose.
    """
    return [
        subject.contention.Contender(
            strategy_id=f"s{i}", symbol=f"X{i}", arrival_seq=count - i
        )
        for i in range(1, count + 1)
    ]


def _rows(
    subject: _Subject, contenders: list[Any], scores: list[float]
) -> dict[Any, Any]:
    return {
        contender.pair: subject.seam.RankingRow(
            strategy_id=contender.strategy_id,
            symbol=contender.symbol,
            score=score,
            as_of=0.0,
        )
        for contender, score in zip(contenders, scores, strict=True)
    }


def _picture(subject: _Subject, *, margins: dict[str, float] | None = None) -> Any:
    """One published snapshot. `committed` is a FIELD, never a derivation."""
    table = {"ES": 500.0, "MES": 50.0} if margins is None else margins
    return subject.seam.FinancialPicture(
        version=VERSION_STAMP,
        published_ts=1_700_000_000.0,
        balance=BALANCE,
        positions=(),
        margin_per_contract=MappingProxyType(dict(table)),
        sum_open_margin=COMMITTED,
        sum_reservations=0.0,
        committed=COMMITTED,
        deployable=BALANCE * 0.70 - COMMITTED,
    )


def _knobs(subject: _Subject, **overrides: Any) -> Any:
    base: dict[str, Any] = {
        "per_trade_risk_usd": PER_TRADE_RISK,
        "deployable_pct": 0.70,
        "symbol_cap": {"ES": 50},
        "slippage_pad_ticks": {"ES": 2},
        "micro_full_threshold": 2,
        "quant_tolerance": 0.25,
    }
    base.update(overrides)
    return subject.sizing.SizingKnobs(**base)


def _allocator(subject: _Subject, picture: Any, knobs: Any = None) -> Any:
    spec = subject.sizing.InstrumentSpec(
        symbol="ES", micro_symbol="MES", tick_value=TICK_VALUE, micro_ratio=MICRO_RATIO
    )
    return subject.sizing.SizingAllocator(
        mirror=_Mirror(subject.seam, picture),
        tradability=_Tradable(),
        instruments={"ES": spec},
        knobs=knobs if knobs is not None else _knobs(subject),
        bucket_cap=None,
    )


def _propose(subject: _Subject, allocator: Any, **kwargs: Any) -> Any:
    seam = subject.seam
    return allocator.propose(
        "s1", "ES", seam.Side.LONG, STOP_TICKS, seam.StopMode.FIXED, 1.5, **kwargs
    )


# ---------------------------------------------------------------------------
# ARM 0 — the literals are the ARCHITECT'S
# ---------------------------------------------------------------------------


def arm_frozen_literals(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """The four constants equal the architect ruling, read from its own file."""
    doc = subject.home / FREEZE
    if not doc.is_file():
        return [], (
            f"{FREEZE} is absent under {subject.home} — the reference side of "
            "this arm is an architect ruling, and a gate that cannot read its "
            "reference certifies nothing (§5.3)"
        )
    section = _SEAM_B.search(doc.read_text("utf-8"))
    if section is None:
        return [], (
            f"{FREEZE} holds no '## SEAM (b)' section — the anchor moved, so "
            "the expected set would be empty and an empty expected set agrees "
            "with anything"
        )
    ruled = {
        name: float(value) for name, value in _FROZEN_LINE.findall(section.group(0))
    }
    missing = [name for name in FROZEN_NAMES if name not in ruled]
    if missing:
        return [], (
            f"{FREEZE} SEAM (b) does not fix {missing} — this arm compares four "
            "literals and cannot compare the ones it could not read"
        )
    defects: list[tuple[str, str]] = []
    for name in FROZEN_NAMES:
        got = getattr(subject.contention, name, None)
        if not isinstance(got, float) or got != ruled[name]:
            defects.append(
                (
                    f"{CONTENTION}:{name}",
                    (
                        f"the module holds {got!r} while the architect ruling in "
                        f"{FREEZE} SEAM (b) fixes {ruled[name]!r} — §6.6:459 gives "
                        "the Allocator the read and the FROZEN SPEC FIXES NO "
                        "TRANSFORM, so a literal this tree chose for itself is "
                        "the allocation judgment §6.6:461-463 keeps out of the "
                        "consumer"
                    ),
                )
            )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 1 — the weights DIFFER, and the falsifier proves the arm can see it
# ---------------------------------------------------------------------------


def _distinct_defect(weights: dict[Any, float], neutral: float, label: str) -> str:
    """The finding a pinned weighting produces. "" when the weights are real."""
    values = set(weights.values())
    if len(values) >= MIN_DISTINCT_WEIGHTS:
        return ""
    if values == {neutral}:
        return (
            f"{label}: every weight is NEUTRAL_WEIGHT {neutral!r} under "
            "PERFORMANCE_WEIGHTED with distinct realized-P&L EMAs — that is "
            "CHECK-DEBT D3.260's exact shape, a weighting that changes nothing "
            "while an ordering changes"
        )
    return (
        f"{label}: {len(values)} distinct weight(s) {sorted(values)} for "
        f"{len(weights)} ranked contender(s); §6.6:431 'feed the winners' needs "
        f"at least {MIN_DISTINCT_WEIGHTS}"
    )


def arm_weights_differ(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """A three-way race with three distinct EMAs weights three ways."""
    contention = subject.contention
    field = _contenders(subject, 3)
    scores = [9.0, 3.0, 6.0]
    ranking = contention.rank(field, _Table(_rows(subject, field, scores)))
    if ranking.policy is not subject.seam.ContentionPolicy.PERFORMANCE_WEIGHTED:
        return [], (
            f"the race fell back to {ranking.policy.value} — {ranking.reason}. "
            "This arm judges the WEIGHTED policy and cannot judge it on a race "
            "that never reached it"
        )
    if ranking.contenders < MIN_DISTINCT_WEIGHTS:
        return [], (
            f"{ranking.contenders} contender(s) ranked — an ordering over fewer "
            "than two carries no weight information at all (§7.12/1)"
        )
    defects: list[tuple[str, str]] = []
    complaint = _distinct_defect(
        dict(ranking.weights), contention.NEUTRAL_WEIGHT, "live"
    )
    if complaint:
        defects.append((RANK_SITE, complaint))
    best, worst = ranking.ordering[0], ranking.ordering[-1]
    if ranking.weights[best.pair] <= ranking.weights[worst.pair]:
        defects.append(
            (
                RANK_SITE,
                (
                    f"the best-ranked pair {best.pair} carries weight "
                    f"{ranking.weights[best.pair]!r} and the worst {worst.pair} "
                    f"carries {ranking.weights[worst.pair]!r} — §6.6:431 is "
                    "'feed the winners', and a weighting that does not is "
                    "pointed the wrong way"
                ),
            )
        )
    # The falsifier, run EVERY time this gate runs rather than once at authoring
    # time: an instrument that cannot fail on the defect is not evidence.
    pinned = {pair: contention.NEUTRAL_WEIGHT for pair in ranking.weights}
    if not _distinct_defect(pinned, contention.NEUTRAL_WEIGHT, "falsifier"):
        defects.append(
            (
                f"{NAME}:_distinct_defect",
                (
                    "the pinned-to-NEUTRAL_WEIGHT falsifier was NOT caught — "
                    "this arm's comparison cannot see the one defect it exists "
                    "for, so its green over the live weights means nothing"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 2 — the weight moves a SIZE
# ---------------------------------------------------------------------------


def _sizes_defect(sizes: dict[float, int], label: str) -> str:
    """The finding a computed-but-unapplied weight produces."""
    counts = set(sizes.values())
    if len(counts) >= MIN_DISTINCT_SIZES:
        return ""
    return (
        f"{label}: weights {sorted(sizes)} produced contract count(s) "
        f"{sorted(counts)} out of §7:478's min(...) — two GOs identical in every "
        "input but their RANK sized the same, so the weight was computed and "
        "never applied to per_trade_risk_$"
    )


class _DroppingAllocator:
    """The falsifier: accepts the weight, sizes without it.

    Byte-identical output to a correct allocator on the neutral weight, which
    is exactly why it has to be driven rather than reasoned about.
    """

    def __init__(self, real: Any) -> None:
        self._real = real

    def propose(self, *args: Any, **kwargs: Any) -> Any:
        """Drop `weight` on the floor and size as if it were never passed."""
        kwargs.pop("weight", None)
        return self._real.propose(*args, **kwargs)


def _drive_sizes(
    subject: _Subject, allocator: Any, weights: list[float]
) -> dict[float, int]:
    return {
        weight: _propose(subject, allocator, weight=weight).contracts
        for weight in weights
    }


def arm_weight_moves_a_size(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Two GOs, one difference — the rank — and two DISTINCT contract counts."""
    contention = subject.contention
    field_size = 3
    best = contention.weight_for(1, field_size)
    worst = contention.weight_for(field_size, field_size)
    if best == worst:
        return [], (
            f"weight_for(1, {field_size}) == weight_for({field_size}, "
            f"{field_size}) == {best!r} — the two drives would differ in nothing, "
            "so a size difference could not be attributed to the rank"
        )
    allocator = _allocator(subject, _picture(subject))
    sizes = _drive_sizes(subject, allocator, [best, worst])
    defects: list[tuple[str, str]] = []
    complaint = _sizes_defect(sizes, "live")
    if complaint:
        defects.append((SIZE_SITE, complaint))
    if sizes[best] < sizes[worst]:
        defects.append(
            (
                SIZE_SITE,
                (
                    f"weight {best!r} sized {sizes[best]} contract(s) and weight "
                    f"{worst!r} sized {sizes[worst]} — the better rank was sized "
                    "SMALLER, which inverts §6.6:431"
                ),
            )
        )
    proposal = _propose(subject, allocator, weight=best)
    if proposal.rationale.score_weight != best:
        defects.append(
            (
                "scripts/nixalloc/seam.py:SizingRationale.score_weight",
                (
                    f"the rationale records {proposal.rationale.score_weight!r} "
                    f"for a pass driven at {best!r} — §16 U5 makes this object "
                    "the Limiter's audit record, and an audit record that names "
                    "a weight the arithmetic did not use is worse than none"
                ),
            )
        )
    dropped = _drive_sizes(subject, _DroppingAllocator(allocator), [best, worst])
    if not _sizes_defect(dropped, "falsifier"):
        defects.append(
            (
                f"{NAME}:_sizes_defect",
                (
                    "the weight-dropping falsifier was NOT caught — this arm's "
                    "comparison cannot distinguish an applied weight from an "
                    "ignored one, which is the whole property"
                ),
            )
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 3 — the clamp BINDS at a drivable rank
# ---------------------------------------------------------------------------


def _bound_defects(
    subject: _Subject, position: int, bound: float, label: str
) -> tuple[list[tuple[str, str]], str]:
    """One end of the clamp: raw outside the bound, weight AT the bound."""
    contention = subject.contention
    step = contention.WEIGHT_STEP
    raw = 1.0 + step * ((CLAMP_FIELD + 1) / 2 - position)
    outside = raw > bound if label == "ceiling" else raw < bound
    if not outside:
        return [], (
            f"raw({position}, {CLAMP_FIELD}) == {raw!r} is INSIDE the {label} "
            f"{bound!r} — the bound is not reachable by a driven rank here, so "
            "this arm would be certifying decoration (§7.12/3)"
        )
    got = contention.weight_for(position, CLAMP_FIELD)
    if got != bound:
        return [
            (
                TRANSFORM_SITE,
                (
                    f"raw({position}, {CLAMP_FIELD}) == {raw!r} is outside the "
                    f"{label} {bound!r} and weight_for returned {got!r} — the "
                    "clamp did not bind where the arithmetic says it must"
                ),
            )
        ], ""
    return [], ""


def arm_clamp_binds(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """At n = 8 both bounds bind, by value, and the reason NAMES them (§18)."""
    contention = subject.contention
    defects: list[tuple[str, str]] = []
    refusals: list[str] = []
    for position, bound, label in (
        (1, contention.WEIGHT_CEILING, "ceiling"),
        (CLAMP_FIELD, contention.WEIGHT_FLOOR, "floor"),
    ):
        found, refusal = _bound_defects(subject, position, bound, label)
        defects.extend(found)
        if refusal:
            refusals.append(refusal)
    if refusals:
        return defects, "; ".join(refusals)

    field = _contenders(subject, CLAMP_FIELD)
    scores = [float(CLAMP_FIELD - i) * 10.0 for i in range(CLAMP_FIELD)]
    ranking = contention.rank(field, _Table(_rows(subject, field, scores)))
    if ranking.policy is not subject.seam.ContentionPolicy.PERFORMANCE_WEIGHTED:
        return defects, (
            f"the n={CLAMP_FIELD} race fell back to {ranking.policy.value} — "
            f"{ranking.reason}"
        )
    values = set(ranking.weights.values())
    for bound, label in (
        (contention.WEIGHT_CEILING, "WEIGHT_CEILING"),
        (contention.WEIGHT_FLOOR, "WEIGHT_FLOOR"),
    ):
        if bound not in values:
            defects.append(
                (
                    RANK_SITE,
                    (
                        f"a field of {CLAMP_FIELD} produced weights "
                        f"{sorted(values)}, none of them the {label} {bound!r} — "
                        "the bound is unreachable through the live pathway even "
                        "though the transform clamps"
                    ),
                )
            )
        if label not in ranking.reason:
            defects.append(
                (
                    RANK_SITE,
                    (
                        f"the ranking's reason does not name {label} on a race "
                        f"where it BOUND a weight — §18 requires the REASON, and "
                        f"a clamp nobody can read is a clamp nobody can audit: "
                        f"{ranking.reason}"
                    ),
                )
            )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 4 — every declared NEUTRAL case, driven one at a time
# ---------------------------------------------------------------------------


def _neutral_routes(subject: _Subject) -> list[tuple[str, Any]]:
    """§6.6:455's cases, as SIX separate drives into the fallback.

    Separate rather than folded, because a single "the fallback is neutral"
    assertion passes when five of the six routes are unreachable — and the six
    reach one constructor (`contention._fallback`) by design, so the thing that
    has to be shown is that all six ARRIVE.
    """
    trio = _contenders(subject, 3)
    solo = _contenders(subject, 1)
    live = _rows(subject, trio, [9.0, 3.0, 6.0])
    absent = dict(live)
    absent.pop(trio[1].pair)
    return [
        ("no port at all", (trio, None)),
        ("port reports itself unavailable", (trio, _Table(live, available=False))),
        ("port RAISES", (trio, _Raising())),
        ("an absent pair-row", (trio, _Table(absent))),
        ("tied EMAs", (trio, _Table(_rows(subject, trio, [4.0, 4.0, 4.0])))),
        ("cold start, no rows at all", (trio, _Table({}))),
        ("a field of ONE", (solo, _Table(_rows(subject, solo, [7.0])))),
    ]


def arm_neutral_cases(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Every declared neutral case is EXACTLY `NEUTRAL_WEIGHT`, and says why."""
    contention = subject.contention
    neutral = contention.NEUTRAL_WEIGHT
    defects: list[tuple[str, str]] = []
    reasons: set[str] = set()
    for label, (field, table) in _neutral_routes(subject):
        ranking = contention.rank(field, table)
        reasons.add(ranking.reason)
        values = set(ranking.weights.values())
        if values != {neutral}:
            defects.append(
                (
                    RANK_SITE,
                    (
                        f"the neutral route '{label}' produced weights "
                        f"{sorted(values)} rather than exactly "
                        f"{{{neutral!r}}} — §6.6:455 makes it an FCFS case and "
                        "§6.6:466 makes FCFS structurally neutral, which is a "
                        "statement about the SIZE as well as the order"
                    ),
                )
            )
    if contention.weight_for(1, 1) != neutral:
        defects.append(
            (
                TRANSFORM_SITE,
                (
                    f"weight_for(1, 1) == {contention.weight_for(1, 1)!r} — a "
                    "single contender carries no ordering information and must "
                    "not be re-sized by a race it did not have"
                ),
            )
        )
    if len(reasons) < MIN_NEUTRAL_ROUTES:
        return defects, (
            f"{len(reasons)} distinct fallback reason(s) across "
            f"{len(_neutral_routes(subject))} driven route(s) — fewer than "
            f"{MIN_NEUTRAL_ROUTES} means the routes collapsed into one another "
            "and this arm counted one case several times (§7.12/5)"
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 5 — the direction that must not exist
# ---------------------------------------------------------------------------


def _ceiling_cases(subject: _Subject) -> list[tuple[str, Any, Any]]:
    """Two fixtures in which a CAPITAL-SAFETY ceiling binds at BOTH weights.

    Both cases are tuned so the ceiling is the smallest term at the FLOOR
    weight as well as at the CEILING weight. A fixture in which the risk term
    binds at one end and the ceiling at the other would show the two sizes
    differing and prove nothing about whether the ceiling moved — the arm would
    be measuring the risk term it already measured in ARM 2.
    """
    starved = subject.seam.FinancialPicture(
        version=VERSION_STAMP,
        published_ts=1_700_000_000.0,
        balance=400.0,
        positions=(),
        margin_per_contract=MappingProxyType({"ES": 500.0, "MES": 50.0}),
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=280.0,
    )
    return [
        ("margin", starved, _knobs(subject)),
        (
            "symbol cap",
            _picture(subject),
            _knobs(subject, per_trade_risk_usd=1_000.0, symbol_cap={"ES": 1}),
        ),
    ]


def arm_ceilings_are_not_weighted(
    subject: _Subject,
) -> tuple[list[tuple[str, str]], str]:
    """A capital-safety ceiling sizes the SAME at the floor and at the ceiling."""
    contention = subject.contention
    low, high = contention.WEIGHT_FLOOR, contention.WEIGHT_CEILING
    defects: list[tuple[str, str]] = []
    observed: list[str] = []
    for label, picture, knobs in _ceiling_cases(subject):
        allocator = _allocator(subject, picture, knobs)
        at_low = _propose(subject, allocator, weight=low)
        at_high = _propose(subject, allocator, weight=high)
        binding = at_high.rationale.binding.value
        observed.append(f"{label}->{binding}")
        if at_low.contracts != at_high.contracts:
            defects.append(
                (
                    SIZE_SITE,
                    (
                        f"the {label} ceiling sized {at_low.contracts} at weight "
                        f"{low!r} and {at_high.contracts} at weight {high!r} "
                        f"(binding {binding}) — margin, the symbol cap and the "
                        "correlation-bucket cap are CAPITAL-SAFETY ceilings, and "
                        "scaling a safety ceiling by a performance score is the "
                        "direction that must not exist"
                    ),
                )
            )
    if not any(
        label.split("->")[1] in {"margin", "symbol_cap", "headroom"}
        for label in observed
    ):
        return defects, (
            f"no drive reached a capital-safety ceiling (observed {observed}) — "
            "an arm that never made a ceiling bind has not shown the ceiling is "
            "unweighted, it has shown nothing"
        )
    return defects, ""


# ---------------------------------------------------------------------------
# ARM 6 — an illegal weight is REFUSED, loudly
# ---------------------------------------------------------------------------


def _illegal(subject: _Subject) -> list[tuple[str, Any, str]]:
    """Each illegal weight, with the CONDITION its refusal must name (§18)."""
    contention = subject.contention
    return [
        ("NaN", math.nan, "not finite"),
        ("zero", 0.0, "not positive"),
        ("negative", -contention.WEIGHT_CEILING, "not positive"),
        ("above the ceiling", contention.WEIGHT_CEILING + 0.1, "outside the frozen"),
        ("below the floor", contention.WEIGHT_FLOOR - 0.1, "outside the frozen"),
    ]


def arm_illegal_weight_refused(subject: _Subject) -> tuple[list[tuple[str, str]], str]:
    """Refused at the boundary, never clamped — and the message names WHY."""
    allocator = _allocator(subject, _picture(subject))
    defects: list[tuple[str, str]] = []
    refused = 0
    for label, value, condition in _illegal(subject):
        try:
            proposal = _propose(subject, allocator, weight=value)
        except subject.sizing.SizingConfigError as exc:
            refused += 1
            if condition not in str(exc):
                defects.append(
                    (
                        GUARD_SITE,
                        (
                            f"the refusal of {label} ({value!r}) does not name "
                            f"the condition {condition!r} — §18: an exception "
                            f"type is a shared namespace, and the reason is the "
                            f"actionable half. Got: {exc}"
                        ),
                    )
                )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            defects.append(
                (
                    GUARD_SITE,
                    (
                        f"{label} ({value!r}) raised {type(exc).__name__}: {exc} "
                        "— the sizer refuses a knob it will not size on with "
                        "SizingConfigError, and a different type is a refusal a "
                        "caller cannot catch alongside the others"
                    ),
                )
            )
        else:
            defects.append(
                (
                    GUARD_SITE,
                    (
                        f"{label} ({value!r}) was ACCEPTED and sized "
                        f"{proposal.contracts} contract(s) at recorded weight "
                        f"{proposal.rationale.score_weight!r} — an out-of-bounds "
                        "weight silently clamped makes a broken caller look "
                        "correct while sizing real money off a number nobody "
                        "chose (directive 4)"
                    ),
                )
            )
    if refused < MIN_REFUSALS and not defects:
        return defects, (
            f"{refused} of {MIN_REFUSALS} illegal weights refused, and no defect "
            "recorded — this arm cannot have measured what it claims"
        )
    control = _propose(subject, allocator, weight=subject.contention.NEUTRAL_WEIGHT)
    if control.outcome is not subject.seam.ProposalOutcome.SIZED:
        return defects, (
            f"the LEGAL control at NEUTRAL_WEIGHT came back "
            f"{control.outcome.value} — every refusal above is then explained by "
            "the fixture rather than by the weight (§5.1 step 6)"
        )
    return defects, ""


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

#: What a PASS here does and does NOT stand for. Attached to the FAIL as well:
#: an operator reading a failure needs to know what was successfully measured.
_EVIDENCE = (
    "the four transform literals were read out of the ARCHITECT RULING in "
    f"{FREEZE} SEAM (b) and compared to the module's own; a three-way race "
    f"produced >= {MIN_DISTINCT_WEIGHTS} distinct weights best-first, and the "
    "pinned-to-NEUTRAL_WEIGHT falsifier was driven and caught; two GOs "
    "differing ONLY in rank produced "
    f">= {MIN_DISTINCT_SIZES} distinct contract counts out of the real "
    "§7:478 min(...), and the weight-dropping falsifier was driven and caught; "
    f"both bounds were driven at n={CLAMP_FIELD} with the raw values recomputed "
    "from the subject's own constants and each shown OUTSIDE its bound before "
    f"the clamp was judged; {MIN_NEUTRAL_ROUTES}+ distinct neutral routes were "
    "each driven separately and each was exactly NEUTRAL_WEIGHT; a "
    "capital-safety ceiling sized IDENTICALLY at the floor and at the ceiling "
    f"weight; {MIN_REFUSALS} illegal weights were refused naming their "
    "condition. NOT proven: that any production caller passes a weight (the "
    "parameter defaults to neutral and nothing in this tree publishes a "
    "ranking table -- CHECK-DEBT D3.263, D3.290), and NOT proven: that the "
    "ruling's four literals are calibrated"
)


def _measure(subject: _Subject) -> CheckResult:
    """EVERY arm runs; the aggregate follows check contract v2 rule 4.

    Rule 4 orders the aggregate `Fail > Cannot-measure > Guarded > Pass`, so an
    arm that refused does NOT suppress a violation another arm positively
    OBSERVED. Returning on the first refusal would do exactly that, and it is a
    live hazard here: a transform pinned back to the constant makes ARM 1's
    finding true and simultaneously drives ARM 3's clamp out of reach, so the
    first arm measures a defect and the second measures nothing.
    """
    defects: list[tuple[str, str]] = []
    refusals: list[str] = []
    for arm in (
        arm_frozen_literals,
        arm_weights_differ,
        arm_weight_moves_a_size,
        arm_clamp_binds,
        arm_neutral_cases,
        arm_ceilings_are_not_weighted,
        arm_illegal_weight_refused,
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
    """Drive the shipped weighting pathway and read what actually ran. Never repairs."""
    try:
        subject, complaint = load_subject(ctx.nix_home)
        if complaint or subject is None:
            return _cannot_measure(
                complaint
                or f"{CONTENTION}: neither a subject nor a complaint — the gate's "
                "own pre-flight returned nothing, which is never a verdict"
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
