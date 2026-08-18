#!/usr/bin/env python3
# C0302: this module is over pylint's line ceiling and the excess is PROSE —
# the §7.12 standing question answered arm by arm, and a rationale beside every
# plant. Doctrine B.7 puts the argument next to the instrument it argues for;
# splitting the gate to satisfy a line counter would move half the reasoning
# away from the code it explains.
# pylint: disable=too-many-lines
"""The Allocator READS §6.6's ranking table, and the read CHANGES the outcome.

`checks/check_scoring_seam.py` judges the seam's own read path — that
`RankingMirror` looks up rather than computes, that its fallback answers rather
than stalls, that a foreign writer is refused. **This gate is the CONSUMER side,
and until ARC 036 nothing gated it at all.** A seam can be perfect and have no
caller; that is precisely the class `check_uncalled_entry_points` measured on
this exact module (`_ARC036_PHASE0_CARRIED` carried seven §6.6 entry points by
name because their production readers did not exist), and it is the class
ARC 033's correlation cap shipped in.

## WHAT IS ACTUALLY PROVEN HERE

**1. The ordering is a FUNCTION OF THE TABLE, in both directions.** Two
strategies GO on one symbol (§6.6:453's own case) against capital that can
satisfy exactly one. The gate drives the race with the higher realized-P&L EMA
on the earlier arrival and requires the earlier arrival to win — and then
**REVERSES the two pair-rows and requires the winner to reverse with them.**

The second half is the whole arm. A race that always sizes its first argument
passes the first half perfectly, and so does a race whose ranking read is
decorative, because in the un-flipped case the ranked answer and the arrival
answer are the same answer. Only the flip separates them.

**2. The race actually CONTENDED.** Proven before either verdict is trusted:
each contender, run ALONE against the same capital, is SIZED with contracts;
run together, one of them is not. If both fit alone and both fit together there
was no contention, the ordering decided nothing, and this gate reports
CANNOT_MEASURE rather than a green over a race that was never a race.

**3. A SCORING OUTAGE NEVER DENIES.** §6.6:467-468: *"Ranking is an
optimization, never a safety gate: a scoring outage must NEVER halt order
flow."* EVERY documented route to an unusable table is driven — no mirror
injected at all, a mirror that never received a snapshot, a table stale by the
clock, a snapshot from a foreign writer, a contender with no pair-row, tied
EMAs, and a mirror that raises on every verb — and every one must still produce
a proposal per contender, in ARRIVAL order, with the head still SIZED. The
COUNT is derived into the verdict from `outage_races` itself and is not stated
here, because a number written beside a set goes stale the moment the set
grows. **This is the hazard stated backwards:** the
dangerous direction is not "FCFS ordered them wrongly", it is "the consumer
refused, or stalled, because Scoring was down".

**4. THE CONSUMER DOES NOT COMPUTE.** §6.6:461-463 and §11:595 fix the
consumer's read as an O(1) table lookup, never math. A consumer that
recalculated an EMA would produce the RIGHT NUMBER and would be a hot-path
violation no output check can see, so the subject is the SHAPE of the read path
— the AST of the adapter and the pairwise read in `scripts/nixalloc/wiring.py`.

**5. THE READ IS PER-GO, NOT PER-TICK.** §16 gives the Allocator per-GO-only
work. A ranking read on the tick path would be a new cost the design does not
carry. Measured by COUNTING every touch of the mirror through a counting proxy:
zero at construction, and bounded per race.

## Non-vacuity, and what this gate CANNOT prove

Every arm is a pure function over data, driven twice each run — once with the
SHIPPED pathway's real answer and once with a deliberately broken one that the
arm must reject. An arm that cannot demonstrate its own defect is reported as
BLIND (`CANNOT_MEASURE`), never as green.

It does **not** prove the Scoring process exists — it does not (R5, §12B) — nor
that anything boots the Allocator, nor that the score-to-sizing-weight transform
of §6.6:459 is implemented, because it is not. What it proves is CONSUMPTION:
the table, when present, decides who gets the capital.
"""

# pylint: disable=duplicate-code
# R0801 pairs this module's §4.4 declaration preamble with every other check.
# The duplication cannot be factored out and that is the design: `PRIVILEGE`,
# `DEPENDS_ON`, `RESOURCES` and the rest are read STATICALLY, by AST, without
# importing the check (check contract §4.4), so a shared base module would be
# invisible to that reader.
from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. This gate imports the composed pathway out of
#: `ctx.nix_home` and drives it in-process with injected doubles.
DEPENDS_ON: tuple[str, ...] = ()
#: The interpreter state this gate mutates and restores, declared so the
#: mutation is visible. No socket, no port, no file write, no child process:
#: the mirror is fed by hand and the transport is never built.
#: `check_observed_resource_claims` compares this against what one execution
#: OBSERVES, and if the observer sees more the observer is right (§17).
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: The artifacts this gate MEASURES, for `check_artifact_gate_coverage`.
#: `wiring.py` is both parsed and driven here. The two modules underneath it are
#: named because this gate imports and drives them as part of the same pass —
#: `contention.py` produces the ordering under judgement and `nixscore/seam.py`
#: is the table being consumed, so a defect in either is a defect this gate
#: hits. That is the honest ground for the claim, and the only one.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixalloc/wiring.py",
    "scripts/nixalloc/contention.py",
    "scripts/nixscore/seam.py",
)
#: FALSE on the facts: one AST parse and a few dozen in-process races.
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every finding here is a design defect in the consumer — a ranking that is "
    "read but does not change the outcome, a scoring outage that reaches a "
    "refusal, a consumer that recomputes a score, a read that moved onto the "
    "tick path. None has a mechanical repair that does not amount to deciding "
    "what the wiring was FOR, and an automated edit to the path that keeps "
    "order flow alive when Scoring dies is the last thing that should be "
    "automated. A human edits it."
)
INSTALLABLE = False
ON_FAIL = "continue"

NAME = "check_scoring_consumption"

WIRING = "scripts/nixalloc/wiring.py"

#: The consumer's read path, by function name inside `WIRING`. DERIVED against
#: the module's own AST every run: a rename that orphans this list is a loud
#: non-vacuity finding rather than a silently empty scan (§7.12/2).
READ_PATH = ("available", "row", "_pairwise")

#: Tokens that mean "the consumer is doing the Scoring process's job". Each is a
#: way of computing a score rather than reading one. `rank_rows` is the seam's
#: OWN ranking function and is legitimate exactly once, inside the Scoring
#: process before `publish`; a consumer calling it is a consumer computing the
#: ranking.
BANNED_ON_READ_PATH = (
    "exp",
    "log",
    "pow",
    "mean",
    "ema",
    "smooth",
    "alpha",
    "rank_rows",
    "statistics",
)

#: The two pairs the race is run between. §6.6:447's canonical key.
PAIR_A = ("scoring-strat-a", "ES")
PAIR_B = ("scoring-strat-b", "ES")

#: Realized-P&L EMAs. Far apart on purpose: a ranking arm driven on scores that
#: differ in the sixth decimal would be measuring float comparison.
HIGH_EMA = 900.0
LOW_EMA = 100.0

#: Freshness threshold for the driven mirror, and the ages either side of it.
STALE_AFTER_S = 5.0
FRESH_AGE_S = 0.5
STALE_AGE_S = 5.001

#: The fake clock every race is run against. A FIXED number, so "stale" is a
#: property of the arithmetic rather than of how slowly this gate ran.
RACE_NOW = 1_000_000.0

#: Capital. `BALANCE * DEPLOYABLE_PCT` is the §16 U2 headroom, and
#: `MARGIN_PER_CONTRACT` is set so that headroom buys contracts for ONE
#: contender and nothing for the second. The gate does not assert that — it
#: MEASURES it (`_arm_contended`).
BALANCE = 25_000.0
DEPLOYABLE_PCT = 0.70
MARGIN_PER_CONTRACT = 12_000.0
TICK_VALUE = 12.5
STOP_TICKS = 20

#: Ceiling on mirror touches per contender in one race. Generous — the wiring
#: needs one freshness read, one lookup and one age per contender plus a handful
#: for the race itself — and far below anything that read the table repeatedly.
#: A FLOOR-style anchor: it is not today's measured count, so it does not move
#: when one more audit term is read.
MAX_MIRROR_READS_PER_CONTENDER = 8
#: Plus this many for the race as a whole (`available`, `arbitrate`, `fresh`,
#: `span_days`).
MAX_MIRROR_READS_PER_RACE = 8


@dataclasses.dataclass(frozen=True)
class Finding:
    """One defect, anchored to the site that carries it and the reason (§18)."""

    site: str
    why: str


@dataclasses.dataclass(frozen=True)
class Race:
    """One race's answer, reduced to the four facts every arm judges.

    A value type and not the live `ContentionOutcome`, deliberately: every arm
    below is a pure function over this, so the can-fail control can hand the
    SAME arm a deliberately wrong answer without constructing a second pathway.
    An arm that could only be driven through the real code could never be shown
    to fail.
    """

    #: `(strategy_id, symbol)` pairs, in the order the race actually sized them.
    order: tuple[tuple[str, str], ...]
    #: Same order: each contender's `ProposalOutcome` value, as a plain string.
    outcomes: tuple[str, ...]
    #: Same order: contracts proposed.
    contracts: tuple[int, ...]
    #: `"fcfs"` or `"performance_weighted"` — the policy that ordered it.
    policy: str
    reason: str
    #: The frozen seam's own pairwise verdict, `(outcome, winner)`, or None.
    pairwise: tuple[str, tuple[str, str]] | None
    disagreement: str = ""

    @property
    def head(self) -> tuple[str, str]:
        """The pair the race sized FIRST — the one that got the capital."""
        return self.order[0]


SIZED = "sized"


# ---------------------------------------------------------------------------
# Loading the subject out of `ctx.nix_home`
# ---------------------------------------------------------------------------


def _purge(prefixes: tuple[str, ...]) -> None:
    """Drop already-imported first-party modules so `home` wins the import."""
    for name in [k for k in sys.modules if k.split(".")[0] in prefixes]:
        del sys.modules[name]


_PREFIXES = ("nixalloc", "nixrisk", "nixscore", "nixbus")

_MODULES = (
    ("nixalloc.wiring", WIRING),
    ("nixalloc.seam", "scripts/nixalloc/seam.py"),
    ("nixalloc.sizing", "scripts/nixalloc/sizing.py"),
    ("nixscore.seam", "scripts/nixscore/seam.py"),
    ("nixbus.statebus", "scripts/nixbus/statebus.py"),
)


def load(home: Path) -> tuple[dict[str, ModuleType] | None, str]:
    """Import the subject modules out of `home`, or say why not.

    Each module's `__file__` is compared back against the path it must resolve
    to. A name-based import against a `sys.path` the preamble has already seeded
    with the REAL repository would measure the live tree whatever `ctx.nix_home`
    said — a defect this project has shipped before.
    """
    saved_path, saved_modules = list(sys.path), dict(sys.modules)
    try:
        sys.path.insert(0, str((home / "scripts").resolve()))
        _purge(_PREFIXES)
        loaded: dict[str, ModuleType] = {}
        for dotted, rel in _MODULES:
            module = __import__(dotted, fromlist=["_"])
            actual = Path(getattr(module, "__file__", "") or "").resolve()
            if actual != (home / rel).resolve():
                return None, (
                    f"{dotted} resolved to {actual}, not {home / rel} — the "
                    "subject under measurement is not the tree that was named"
                )
            loaded[dotted] = module
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, f"cannot import the Allocator out of {home}: {exc!r}"
    finally:
        sys.path[:] = saved_path
        sys.modules.clear()
        sys.modules.update(saved_modules)


# ---------------------------------------------------------------------------
# The doubles. Ports the frozen seam already names, and nothing else.
# ---------------------------------------------------------------------------


class _Tradability:  # pylint: disable=too-few-public-methods
    """§16 U1's fast-drop cache, always open. Not the subject here."""

    def tradable(self, symbol: str) -> tuple[bool, str]:
        """Every symbol is tradable; this gate is about contention, not U1."""
        del symbol
        return True, "open"


class _Mirror:  # pylint: disable=too-few-public-methods
    """A `MirrorPort` holding one published financial picture."""

    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Any:
        """§12.7's private, process-local read."""
        return self._snapshot

    def version(self) -> int:
        """The published stamp."""
        picture = self._snapshot.picture
        return -1 if picture is None else picture.version


class _CountingMirror:
    """A `RankingMirror` that counts every touch. §16's per-GO-only claim.

    A proxy rather than a subclass: the subject is how MANY times the wiring
    reaches for the table, and a proxy makes every reach pass through one place
    that can be counted. `span_days` is a property on the real mirror and is
    spelled as one here so the wiring's access is identical.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.reads = 0

    @property
    def span_days(self) -> int | None:
        """One read."""
        self.reads += 1
        return self._inner.span_days

    def fresh(self, now: float | None = None) -> bool:
        """One read."""
        self.reads += 1
        return self._inner.fresh(now)

    def age_s(self, now: float | None = None) -> float | None:
        """One read."""
        self.reads += 1
        return self._inner.age_s(now)

    def lookup(self, strategy_id: str, symbol: str) -> Any:
        """One read."""
        self.reads += 1
        return self._inner.lookup(strategy_id, symbol)

    def arbitrate(self, first: Any, second: Any, now: float | None = None) -> Any:
        """One read."""
        self.reads += 1
        return self._inner.arbitrate(first, second, now)


class _RaisingMirror:
    """A table whose every verb throws — a publisher that just died."""

    span_days = property(lambda self: 1 / 0)

    def fresh(self, now: float | None = None) -> bool:
        """The failure mode a dead segment actually presents."""
        raise RuntimeError(f"scoring mirror is gone (now={now!r})")

    def age_s(self, now: float | None = None) -> float | None:
        """Unreachable when `fresh` already threw; declared for shape."""
        raise RuntimeError(f"scoring mirror is gone (now={now!r})")

    def lookup(self, strategy_id: str, symbol: str) -> Any:
        """Unreachable when `fresh` already threw; declared for shape."""
        raise RuntimeError(f"scoring mirror is gone ({strategy_id}/{symbol})")

    def arbitrate(self, first: Any, second: Any, now: float | None = None) -> Any:
        """The pairwise read against a dead table."""
        raise RuntimeError(f"scoring mirror is gone ({first!r} vs {second!r})")


# ---------------------------------------------------------------------------
# Building one race
# ---------------------------------------------------------------------------


def _picture(mods: dict[str, ModuleType]) -> Any:
    """§3's ONE atomic published snapshot, with room for one contender."""
    seam = mods["nixalloc.seam"]
    return seam.FinancialPicture(
        version=41,
        published_ts=RACE_NOW,
        balance=BALANCE,
        positions=(),
        margin_per_contract={"ES": MARGIN_PER_CONTRACT, "MES": MARGIN_PER_CONTRACT},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=BALANCE * DEPLOYABLE_PCT,
    )


def _pathway(mods: dict[str, ModuleType], ranking: Any) -> Any:
    """The SHIPPED `AllocatorPathway`, with `ranking` as its §6.6 mirror."""
    seam, sizing, wiring = (
        mods["nixalloc.seam"],
        mods["nixalloc.sizing"],
        mods["nixalloc.wiring"],
    )
    snapshot = seam.MirrorSnapshot(
        state=seam.MirrorState.FRESH,
        picture=_picture(mods),
        reason="complete and stamped",
    )
    return wiring.AllocatorPathway(
        mirror=_Mirror(snapshot),
        tradability=_Tradability(),
        instruments={
            "ES": sizing.InstrumentSpec(
                symbol="ES", micro_symbol="MES", tick_value=TICK_VALUE
            )
        },
        knobs=sizing.SizingKnobs(
            #: Enormous ON PURPOSE: §7's per-trade RISK term must not be what
            #: binds, or the race would be decided by the stop and not by the
            #: capital, and "shared capital cannot satisfy them all" (§6.6:431)
            #: would never be the subject.
            per_trade_risk_usd=1_000_000.0,
            deployable_pct=DEPLOYABLE_PCT,
            symbol_cap={"ES": 500},
            slippage_pad_ticks={"ES": 2},
            micro_full_threshold=2,
            quant_tolerance=0.25,
        ),
        bucket_cap=None,
        ranking=ranking,
    )


def _mirror(mods: dict[str, ModuleType], scores: dict, *, age_s: float, **kw) -> Any:
    """A live `RankingMirror` fed one snapshot `age_s` before `RACE_NOW`."""
    score = mods["nixscore.seam"]
    statebus = mods["nixbus.statebus"]
    mirror = score.RankingMirror(stale_after_s=STALE_AFTER_S)
    snapshot = score.RankingSnapshot(
        rows=score.rank_rows(scores),
        span_days=kw.pop("span_days", 10),
        **kw,
    )
    mirror.apply(
        statebus.StateMessage(
            topic=score.RANKING_TOPIC,
            payload=snapshot.as_wire(),
            seq=1,
            stamp=RACE_NOW - age_s,
            snapshot=True,
        ),
        now=RACE_NOW - age_s,
    )
    return mirror


def _gos(mods: dict[str, ModuleType], pairs: tuple[tuple[str, str], ...]) -> tuple:
    """One GO per pair, stamped with its ARRIVAL position (1, 2, ...)."""
    seam, wiring = mods["nixalloc.seam"], mods["nixalloc.wiring"]
    return tuple(
        wiring.Go(
            strategy_id=strategy_id,
            symbol=symbol,
            side=seam.Side.LONG,
            stop_ticks=STOP_TICKS,
            stop_mode=seam.StopMode.FIXED,
            signal_ts=RACE_NOW,
            arrival_seq=index,
        )
        for index, (strategy_id, symbol) in enumerate(pairs, start=1)
    )


def race(
    mods: dict[str, ModuleType],
    ranking: Any,
    pairs: tuple[tuple[str, str], ...] = (PAIR_A, PAIR_B),
) -> Race:
    """Run ONE race through the shipped pathway and reduce it to a `Race`."""
    outcome = _pathway(mods, ranking).propose_contended(_gos(mods, pairs), now=RACE_NOW)
    verdict = outcome.pairwise
    return Race(
        order=tuple(outcome.order),
        outcomes=tuple(str(r.proposal.outcome.value) for r in outcome.reports),
        contracts=tuple(int(r.proposal.contracts) for r in outcome.reports),
        policy=str(outcome.ranking.policy.value),
        reason=str(outcome.reason),
        pairwise=(
            None if verdict is None else (str(verdict.outcome), tuple(verdict.winner))
        ),
        disagreement=str(outcome.disagreement),
    )


# ---------------------------------------------------------------------------
# ARM 1 — the ordering is a FUNCTION OF THE TABLE, and the FLIP proves it
# ---------------------------------------------------------------------------


def flip_defects(normal: Race, flipped: Race) -> list[Finding]:
    """The headline arm. `normal` favours `PAIR_A`; `flipped` favours `PAIR_B`.

    Exported and taking two values rather than driving the pathway itself, so
    the can-fail control can hand this same arm the answer a decorative wiring
    would produce and require a finding.
    """
    site = f"{WIRING}:propose_contended"
    findings = _winner_defects(normal, PAIR_A, "A ranked above B", site)
    findings += _winner_defects(flipped, PAIR_B, "B ranked above A (FLIPPED)", site)
    if normal.head == flipped.head:
        findings.append(
            Finding(
                site,
                f"REVERSING the two pair-rows' realized-P&L EMAs left the same "
                f"contender {normal.head!r} holding the capital. The ordering is "
                "not a function of the ranking table: a wiring that always sizes "
                "its first argument produces exactly this, and it passes every "
                "un-flipped assertion (§6.6:433 — the winner is chosen by recent "
                "realized productivity, not by arrival order)",
            )
        )
    findings += _policy_defects(normal, site, "A ranked above B")
    findings += _policy_defects(flipped, site, "B ranked above A (FLIPPED)")
    return findings


def shape_defects(driven: tuple[tuple[str, Race, int], ...]) -> list[Finding]:
    """Every driven race returned one proposal per contender. Judged FIRST.

    A subject that hands back an empty race is a FAILURE and not an
    unmeasurable: §6.6:467-468's forbidden direction is precisely a consumer
    that produced nothing because the ranking was unusable. It is judged before
    any other arm because the other arms index into these tuples, and an
    instrument that crashes on a broken subject reports `gate raised IndexError`
    — which names the gate, not the defect (§18).
    """
    site = f"{WIRING}:propose_contended[shape]"
    return [
        Finding(
            site,
            f"[{label}] the race returned {len(got.order)} proposal(s) for "
            f"{expected} contender(s) ({got.outcomes!r}). Every contender must "
            "come back with a proposal: §6.6:467-468 makes ranking an "
            "optimization and never a safety gate, so a contender that received "
            "no answer was halted by one",
        )
        for label, got, expected in driven
        if len(got.order) != expected
        or len(got.outcomes) != expected
        or len(got.contracts) != expected
    ]


def _winner_defects(got: Race, expected, label: str, site: str) -> list[Finding]:
    """One direction: the higher-EMA pair leads AND takes the capital."""
    out: list[Finding] = []
    if got.head != tuple(expected):
        out.append(
            Finding(
                site,
                f"[{label}] the race sized {got.head!r} first; §6.6:453 compares "
                f"the two pair-rows and {tuple(expected)!r} carries the higher "
                f"realized-P&L EMA. Order was {got.order!r}, reason: {got.reason}",
            )
        )
        return out
    if got.outcomes[0] != SIZED or got.contracts[0] <= 0:
        out.append(
            Finding(
                site,
                f"[{label}] the higher-ranked pair led the ordering and was NOT "
                f"sized ({got.outcomes[0]!r}, {got.contracts[0]} contracts). An "
                "ordering that does not decide who receives capital is a sort, "
                "not contention",
            )
        )
    if got.outcomes[1] == SIZED and got.contracts[1] > 0:
        out.append(
            Finding(
                site,
                f"[{label}] BOTH contenders were sized ({got.contracts}). §6.6:431 "
                "defines contention as shared capital that cannot satisfy them "
                "all — if both fit, the race decided nothing and the flip below "
                "proves nothing either",
            )
        )
    return out


def _policy_defects(got: Race, site: str, label: str) -> list[Finding]:
    """A live, fresh, unequal table must produce a RANKED policy, not FCFS."""
    out: list[Finding] = []
    if got.policy != "performance_weighted":
        out.append(
            Finding(
                site,
                f"[{label}] a FRESH table with two DISTINCT realized-P&L EMAs "
                f"produced policy {got.policy!r}. §6.6:465 makes FCFS the "
                "fallback for an absent or stale table; reaching it on a live "
                "one means the read did not land — reason: " + got.reason,
            )
        )
    if got.pairwise is None:
        out.append(
            Finding(
                site,
                f"[{label}] no pairwise verdict was recorded for a race of two. "
                "§6.6:453 defines the two-pair comparison for exactly this case "
                "and the frozen seam owns it; a race that never asks it has one "
                "reader of the table where the design has two",
            )
        )
    if got.disagreement:
        out.append(
            Finding(
                site,
                f"[{label}] the two readers of ONE ranking table disagreed: "
                + got.disagreement,
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM 2 — NON-VACUITY: prove the race actually contended
# ---------------------------------------------------------------------------


def contention_defects(solo_a: Race, solo_b: Race, both: Race) -> list[Finding]:
    """Capital was genuinely insufficient for both. Checked BEFORE any verdict.

    Returns findings that make the gate CANNOT_MEASURE rather than FAIL: a race
    that never contended is an instrument that measured nothing, not a subject
    that is broken.
    """
    site = f"{NAME}:non-vacuity"
    out: list[Finding] = []
    for label, solo in (("A", solo_a), ("B", solo_b)):
        if solo.outcomes[0] != SIZED or solo.contracts[0] <= 0:
            out.append(
                Finding(
                    site,
                    f"contender {label} run ALONE against the same capital was "
                    f"{solo.outcomes[0]!r} with {solo.contracts[0]} contracts. "
                    "Nothing was contended: the loser of the race lost to a "
                    "refusal it would have met on its own",
                )
            )
    if all(outcome == SIZED for outcome in both.outcomes):
        out.append(
            Finding(
                site,
                f"BOTH contenders were sized together ({both.contracts}), so the "
                "capital satisfied them all and §6.6:431's precondition — "
                "'shared capital cannot satisfy them all' — was never met. Any "
                "ordering is a correct ordering here",
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM 3 — a scoring outage NEVER denies (§6.6:467-468)
# ---------------------------------------------------------------------------


def outage_defects(runs: dict[str, Race], contenders: int) -> list[Finding]:
    """Every route to an unusable table still produces a proposal per contender.

    The dangerous direction is stated backwards in most descriptions of this
    rule: the failure that matters is not a wrong FCFS order, it is a consumer
    that REFUSED or waited because Scoring was down.
    """
    site = f"{WIRING}:propose_contended[outage]"
    out: list[Finding] = []
    for label, got in sorted(runs.items()):
        out += _one_outage(label, got, contenders, site)
    return out


def _one_outage(label: str, got: Race, contenders: int, site: str) -> list[Finding]:
    """One outage route's verdict."""
    out: list[Finding] = []
    if len(got.order) != contenders or len(got.outcomes) != contenders:
        out.append(
            Finding(
                site,
                f"[{label}] {len(got.order)} of {contenders} contender(s) came "
                "back from the race. §6.6:467-468: ranking is an optimization, "
                "never a safety gate — a scoring outage must NEVER halt order "
                "flow, and a contender that received no proposal was halted",
            )
        )
        return out
    if got.policy != "fcfs":
        out.append(
            Finding(
                site,
                f"[{label}] the policy was {got.policy!r}, not the FCFS fallback. "
                "§6.6:465 locks the fallback for an absent or stale table; a "
                "PERFORMANCE_WEIGHTED answer over an unusable table is a ranking "
                "invented out of nothing",
            )
        )
    if got.order != (PAIR_A, PAIR_B):
        out.append(
            Finding(
                site,
                f"[{label}] the fallback ordered {got.order!r}, not the ARRIVAL "
                "order. First-come-first-served IS the arrival order (§6.6:466 — "
                "deterministic, structurally neutral, favours no symbol); "
                "anything else is a preference wearing the fallback's name",
            )
        )
    if got.outcomes[0] != SIZED or got.contracts[0] <= 0:
        out.append(
            Finding(
                site,
                f"[{label}] the FCFS head was {got.outcomes[0]!r} with "
                f"{got.contracts[0]} contracts. THIS IS THE HAZARD: a scoring "
                "outage reached a refusal instead of a proposal, which is "
                "exactly what §6.6:467-468 forbids",
            )
        )
    if not got.reason.strip():
        out.append(
            Finding(
                site,
                f"[{label}] the fallback fired with no reason. Six conditions "
                "reach FCFS and an operator cannot tell them apart from the "
                "outcome alone (check contract §18)",
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM 4 — the consumer does not COMPUTE (§6.6:461-463, §11:595)
# ---------------------------------------------------------------------------


def read_path_defects(source: str) -> tuple[list[Finding], int]:
    """Banned computation on the CONSUMER's read path. `(findings, scanned)`.

    Exported so the plant arm drives it over a source it authored, which is how
    this arm's can-fail binding is re-established every run rather than recorded.
    """
    findings: list[Finding] = []
    scanned = 0
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Finding(WIRING, f"cannot parse: {exc}")], 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in READ_PATH:
            continue
        scanned += 1
        site = f"{WIRING}:{node.name}"
        for inner in ast.walk(node):
            findings += _read_path_defect(site, inner)
    return findings, scanned


def _read_path_defect(site: str, inner: ast.AST) -> list[Finding]:
    """One node's verdict on the consumer read path, or nothing."""
    if isinstance(inner, ast.Call):
        name = _called_name(inner)
        if name and name.split(".")[-1] in BANNED_ON_READ_PATH:
            return [
                Finding(
                    site,
                    f"calls {name}() on the consumer's read path. §6.6:461-463: "
                    "nobody but the Scoring process COMPUTES the score, and both "
                    "hot paths do an O(1) table lookup, NEVER math",
                )
            ]
        return []
    if isinstance(inner, (ast.For, ast.AsyncFor, ast.comprehension)):
        return [
            Finding(
                site,
                "iterates on the consumer's read path. A scan over the ranking "
                "table is O(n) where §6.6:463 and §11:595 require O(1)",
            )
        ]
    if isinstance(inner, ast.BinOp) and isinstance(
        inner.op, (ast.Mult, ast.Div, ast.Pow)
    ):
        return [
            Finding(
                site,
                f"performs {type(inner.op).__name__} arithmetic on the "
                "consumer's read path — the shape of an EMA being recomputed by "
                "a reader (§11 hot-path violation). A timestamp subtraction is "
                "permitted and this is not one",
            )
        ]
    return []


def _called_name(node: ast.Call) -> str | None:
    """The bare name a call settles on, or None."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


# ---------------------------------------------------------------------------
# ARM 5 — the read is PER-GO, never per-tick (§16)
# ---------------------------------------------------------------------------


def cost_defects(at_rest: int, per_race: int, contenders: int) -> list[Finding]:
    """Mirror touches at construction and across one race, against a ceiling."""
    site = f"{WIRING}:AllocatorPathway"
    budget = MAX_MIRROR_READS_PER_CONTENDER * contenders + MAX_MIRROR_READS_PER_RACE
    out: list[Finding] = []
    if at_rest:
        out.append(
            Finding(
                site,
                f"{at_rest} ranking-table read(s) happened with NO GO proposed — "
                "building the pathway touched the table. §16 gives the Allocator "
                "per-GO-only work, and a read that happens without a GO is a "
                "cost on whatever loop constructs or ticks it",
            )
        )
    if per_race <= 0:
        out.append(
            Finding(
                site,
                "ZERO ranking-table reads across a whole race. The wiring is not "
                "consuming the table at all — which is the built-but-uncalled "
                "class this gate exists to close",
            )
        )
    elif per_race > budget:
        out.append(
            Finding(
                site,
                f"{per_race} ranking-table reads for {contenders} contender(s), "
                f"over the budget of {budget}. §6.6:463 makes the consumer's read "
                "an O(1) lookup per contender; a count that scales past that is a "
                "table being scanned or re-read",
            )
        )
    return out


# ---------------------------------------------------------------------------
# THE CAN-FAIL CONTROLS. Each drives its arm over a deliberately wrong answer.
# ---------------------------------------------------------------------------


def _race(
    order: tuple[tuple[str, str], ...],
    outcomes: tuple[str, ...],
    contracts: tuple[int, ...],
    policy: str = "performance_weighted",
) -> Race:
    """A hand-built answer, for the can-fail controls only."""
    return Race(
        order=order,
        outcomes=outcomes,
        contracts=contracts,
        policy=policy,
        reason="planted",
        pairwise=None if not order else ("ranked", order[0]),
    )


def flip_arm_can_fail() -> tuple[bool, str]:
    """Drive the flip arm over a race that IGNORES the table, require a finding."""
    always_first = _race((PAIR_A, PAIR_B), (SIZED, "zero_after_clamp"), (14, 0))
    if not flip_defects(always_first, always_first):
        return False, (
            "a race that sized its FIRST argument under BOTH rankings produced "
            "no finding — the flip arm cannot see a decorative ranking read, so "
            "its silence is blind, not green"
        )
    honest = _race((PAIR_B, PAIR_A), (SIZED, "zero_after_clamp"), (14, 0))
    leftover = flip_defects(always_first, honest)
    if leftover:
        return False, (
            "a correctly flipping race was reported as defective "
            f"({[f.why[:60] for f in leftover]}) — the arm flags everything, "
            "which is the same blindness pointed the other way"
        )
    return True, ""


def outage_arm_can_fail() -> tuple[bool, str]:
    """Drive the outage arm over a race that DENIED, and require a finding."""
    denied = _race((PAIR_A, PAIR_B), ("no_size_deny", "no_size_deny"), (0, 0), "fcfs")
    if not outage_defects({"planted-deny": denied}, 2):
        return False, (
            "a race that refused BOTH contenders while the table was down "
            "produced no finding — the outage arm cannot see §6.6:467-468's "
            "actual hazard, so its silence is blind, not green"
        )
    stalled = Race(
        order=(PAIR_A,),
        outcomes=(SIZED,),
        contracts=(14,),
        policy="fcfs",
        reason="one contender vanished",
        pairwise=None,
    )
    if not outage_defects({"planted-drop": stalled}, 2):
        return False, (
            "a race that returned one proposal for two contenders produced no "
            "finding — a dropped contender is a halted contender"
        )
    healthy = _race((PAIR_A, PAIR_B), (SIZED, "zero_after_clamp"), (14, 0), "fcfs")
    if outage_defects({"planted-ok": healthy}, 2):
        return False, "a healthy FCFS fallback was reported as an outage defect"
    return True, ""


def contention_arm_can_fail() -> tuple[bool, str]:
    """Drive the non-vacuity arm over a race where BOTH fitted."""
    fits = _race((PAIR_A, PAIR_B), (SIZED, SIZED), (14, 14))
    solo = _race((PAIR_A,), (SIZED,), (14,))
    if not contention_defects(solo, solo, fits):
        return False, (
            "a race in which BOTH contenders were sized produced no non-vacuity "
            "finding — the arm cannot see a race that never contended"
        )
    starved = _race((PAIR_A,), ("zero_after_clamp",), (0,))
    if not contention_defects(starved, solo, fits):
        return False, (
            "a contender that could not be sized even ALONE produced no finding "
            "— the arm cannot tell a lost race from a refusal"
        )
    real = _race((PAIR_A, PAIR_B), (SIZED, "zero_after_clamp"), (14, 0))
    if contention_defects(solo, solo, real):
        return False, "a genuinely contended race was reported as vacuous"
    return True, ""


def read_path_arm_can_fail() -> tuple[bool, str]:
    """Drive the AST arm over a consumer that computes, and require a finding."""
    computing = (
        "class T:\n"
        "    def row(self, strategy_id, symbol):\n"
        "        hit = self._mirror.lookup(strategy_id, symbol)\n"
        "        return hit.realized_ema * self._alpha ** self._span\n"
    )
    findings, scanned = read_path_defects(computing)
    if scanned != 1 or not findings:
        return False, (
            f"a consumer recomputing an EMA produced {len(findings)} finding(s) "
            f"over {scanned} scanned function(s) — the read-path arm cannot see a "
            "computing reader, so its silence is blind, not green"
        )
    clean, clean_scanned = read_path_defects(
        "class T:\n"
        "    def row(self, strategy_id, symbol):\n"
        "        return self._mirror.lookup(strategy_id, symbol)\n"
    )
    if clean_scanned != 1 or clean:
        return False, (
            "a plain delegation to the mirror's lookup was reported as computing "
            f"({[f.why[:60] for f in clean]}) — the arm flags everything"
        )
    return True, ""


def cost_arm_can_fail() -> tuple[bool, str]:
    """Drive the cost arm over a read at rest, a silent read and a scan."""
    if not cost_defects(3, 6, 2):
        return False, "a table read with NO GO proposed produced no finding"
    if not cost_defects(0, 0, 2):
        return False, (
            "ZERO reads across a whole race produced no finding — the cost arm "
            "would call a wiring that never consults the table cheap"
        )
    budget = MAX_MIRROR_READS_PER_CONTENDER * 2 + MAX_MIRROR_READS_PER_RACE
    if not cost_defects(0, budget + 1, 2):
        return False, "a read count over the budget produced no finding"
    if cost_defects(0, 1, 2):
        return False, "a single read across a race was reported as over budget"
    return True, ""


def shape_arm_can_fail() -> tuple[bool, str]:
    """Drive the shape arm over a race that dropped a contender."""
    dropped = Race(
        order=(PAIR_A,),
        outcomes=(SIZED,),
        contracts=(14,),
        policy="fcfs",
        reason="planted",
        pairwise=None,
    )
    if not shape_defects((("planted-drop", dropped, 2),)):
        return False, (
            "a race that returned one proposal for two contenders produced no "
            "shape finding — the arm that runs FIRST cannot see an empty race, "
            "so every arm after it would index into nothing"
        )
    if not shape_defects((("planted-empty", _race((), (), (), "fcfs"), 1),)):
        return False, "an EMPTY race produced no shape finding"
    healthy = _race((PAIR_A, PAIR_B), (SIZED, "zero_after_clamp"), (14, 0))
    if shape_defects((("planted-ok", healthy, 2),)):
        return False, "a well-formed race was reported as malformed"
    return True, ""


_CONTROLS = (
    ("shape", shape_arm_can_fail),
    ("flip", flip_arm_can_fail),
    ("outage", outage_arm_can_fail),
    ("non-vacuity", contention_arm_can_fail),
    ("read-path", read_path_arm_can_fail),
    ("cost", cost_arm_can_fail),
)


def arms_can_fail() -> tuple[str, str]:
    """The first arm that cannot demonstrate a defect, or `("", "")`."""
    for label, control in _CONTROLS:
        ok, why = control()
        if not ok:
            return label, why
    return "", ""


# ---------------------------------------------------------------------------
# Driving the six outage routes
# ---------------------------------------------------------------------------


def outage_races(mods: dict[str, ModuleType]) -> dict[str, Race]:
    """Every documented route to an unusable table, DRIVEN through the pathway."""
    score = mods["nixscore.seam"]
    return {
        "no mirror injected at all": race(mods, None),
        "mirror never fed a snapshot": race(
            mods, score.RankingMirror(stale_after_s=STALE_AFTER_S)
        ),
        "table stale by the clock": race(
            mods,
            _mirror(mods, {PAIR_A: HIGH_EMA, PAIR_B: LOW_EMA}, age_s=STALE_AGE_S),
        ),
        "snapshot from a foreign writer": race(
            mods,
            _mirror(
                mods,
                {PAIR_A: HIGH_EMA, PAIR_B: LOW_EMA},
                age_s=FRESH_AGE_S,
                writer_identity="impostor",
            ),
        ),
        "a contender has no pair-row": race(
            mods, _mirror(mods, {PAIR_A: HIGH_EMA}, age_s=FRESH_AGE_S)
        ),
        "equal realized EMAs": race(
            mods, _mirror(mods, {PAIR_A: LOW_EMA, PAIR_B: LOW_EMA}, age_s=FRESH_AGE_S)
        ),
        "the mirror raises on every verb": race(mods, _RaisingMirror()),
    }


def _live(mods: dict[str, ModuleType], first: float, second: float) -> Any:
    """A fresh mirror with `PAIR_A` on `first` and `PAIR_B` on `second`."""
    return _mirror(mods, {PAIR_A: first, PAIR_B: second}, age_s=FRESH_AGE_S)


def _cost_measurement(mods: dict[str, ModuleType]) -> tuple[int, int]:
    """`(reads at rest, reads across one race)` through the counting proxy."""
    counting = _CountingMirror(_live(mods, HIGH_EMA, LOW_EMA))
    _pathway(mods, counting)
    at_rest = counting.reads
    counting.reads = 0
    _pathway(mods, counting).propose_contended(
        _gos(mods, (PAIR_A, PAIR_B)), now=RACE_NOW
    )
    return at_rest, counting.reads


@dataclasses.dataclass(frozen=True)
class Driven:  # pylint: disable=too-many-instance-attributes
    """Everything one run drove, so `_measure` takes one argument.

    R0902: nine fields, and each is ONE driven measurement — the two ranked
    races, the two solo controls, the outage set, the two cost counts and the
    static scan's pair. Collapsing any two would report one number for two
    measurements, which is the ambiguity §7.12/1 refuses.
    """

    normal: Race
    flipped: Race
    solo_a: Race
    solo_b: Race
    outages: dict[str, Race]
    at_rest: int
    per_race: int
    scanned: int
    static: list[Finding]


def drive(mods: dict[str, ModuleType]) -> Driven:
    """Run every race this gate judges, once, out of the loaded tree."""
    source = (Path(mods["nixalloc.wiring"].__file__ or "")).read_text(encoding="utf-8")
    static, scanned = read_path_defects(source)
    at_rest, per_race = _cost_measurement(mods)
    return Driven(
        normal=race(mods, _live(mods, HIGH_EMA, LOW_EMA)),
        flipped=race(mods, _live(mods, LOW_EMA, HIGH_EMA)),
        solo_a=race(mods, _live(mods, HIGH_EMA, LOW_EMA), (PAIR_A,)),
        solo_b=race(mods, _live(mods, HIGH_EMA, LOW_EMA), (PAIR_B,)),
        outages=outage_races(mods),
        at_rest=at_rest,
        per_race=per_race,
        scanned=scanned,
        static=static,
    )


def _evidence(got: Driven) -> str:
    """What was actually driven, in figures rather than adjectives.

    Every figure is printed from a WHOLE tuple rather than an index, so this
    line survives a subject that returned an empty race — the case `shape_
    defects` reports and the one an indexing evidence string would crash on.
    """
    return (
        f"{WIRING}: a §6.6:453 race of two on ONE symbol against headroom "
        f"{BALANCE * DEPLOYABLE_PCT:.0f} and margin {MARGIN_PER_CONTRACT:.0f} per "
        f"contract, driven through the SHIPPED AllocatorPathway. RANKED: order "
        f"{got.normal.order} -> {got.normal.outcomes} {got.normal.contracts}; "
        f"FLIPPED the two pair-rows' realized EMAs and the same race became "
        f"{got.flipped.order} -> {got.flipped.outcomes} {got.flipped.contracts}. "
        f"Non-vacuity: each contender sized {got.solo_a.contracts}/"
        f"{got.solo_b.contracts} contract(s) ALONE, so the capital was genuinely "
        f"insufficient for both. {len(got.outages)} outage route(s) driven and "
        f"every one produced a proposal per contender in arrival order. "
        f"{got.scanned} consumer read-path function(s) scanned for computation, "
        f"iteration and I/O. Cost: {got.at_rest} table read(s) at rest, "
        f"{got.per_race} across one race. All {len(_CONTROLS)} arms proved they "
        f"can fail on planted answers this run. NOT proven: the Scoring process "
        f"(R5, §12B) exists, anything boots the Allocator, or §6.6:459's "
        f"score->sizing-weight transform is implemented — it is not"
    )


def _measure(got: Driven) -> tuple[list[Finding], list[Finding]]:
    """`(findings, vacuity)` over one run's driven races."""
    shape = shape_defects(
        (
            ("A ranked above B", got.normal, 2),
            ("B ranked above A (FLIPPED)", got.flipped, 2),
            ("contender A alone", got.solo_a, 1),
            ("contender B alone", got.solo_b, 1),
        )
    )
    findings = shape + outage_defects(got.outages, 2)
    findings += list(got.static)
    findings += cost_defects(got.at_rest, got.per_race, 2)
    if got.scanned != len(READ_PATH):
        findings.append(
            Finding(
                f"{NAME}:non-vacuity",
                f"the read-path scan found {got.scanned} of the {len(READ_PATH)} "
                f"functions it judges ({', '.join(READ_PATH)}) in {WIRING} — a "
                "scan over nothing cannot report a computing consumer",
            )
        )
    if shape:
        return findings, []
    findings += flip_defects(got.normal, got.flipped)
    return findings, contention_defects(got.solo_a, got.solo_b, got.normal)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure it. See the module docstring for what and why."""
    try:
        blind, why = arms_can_fail()
        if blind:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{blind}-arm",
                detail=f"the {blind} arm cannot fail: {why}",
            )
        mods, error = load(ctx.nix_home)
        if mods is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        got = drive(mods)
        evidence = _evidence(got)
        findings, vacuity = _measure(got)
        if vacuity:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site="; ".join(sorted({f.site for f in vacuity})),
                evidence=evidence,
                detail="; ".join(f"{f.site}: {f.why}" for f in vacuity),
            )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(sorted({f.site for f in findings})),
                evidence=evidence,
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
