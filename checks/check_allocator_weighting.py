#!/usr/bin/env python3
"""§6.6:459's weight moves a SIZE, and §4's recovery states reach the screen.

ARC 037 / sub-agent E. ONE gate, ONE property (the one-gate-one-property rule
is `nix_check_contract.md` §5.5).

Authority is the frozen `docs/nics_risk_subsystem_spec_v1.3.md` throughout, and
every §-citation below resolves against it: *the Allocator's consumption of
§6.6's ranking table and §4's recovery states changes what it PROPOSES — the
size when a table is live, the refusal when a strategy is dying or quarantined —
and neither can refuse a proposal for a SCORING reason.*

Its sibling `check_scoring_consumption` owns the ORDER (ARC 036: reversing two
pair-rows' realized EMAs reverses which contender takes the capital). This gate
owns what the order does to the CONTRACT COUNT, and what the §4 lifecycle does
to eligibility. Two properties, two gates, no second instrument for either
(doctrine C.9).

  * **ARM 1 — the weight moves the SIZE.** Two GOs identical in side, symbol,
    stop, arrival spacing and published capital, differing only in RANK, driven
    through the SHIPPED `AllocatorPathway.propose_contended`. Requires TWO
    DISTINCT contract counts, best-ranked strictly larger. **It carries its own
    discriminator**, because two distinct counts are the DEFAULT here and not
    the finding: `_RaceMirror` already withholds the head contender's margin
    from the one behind it, so a race can produce two sizes with no weighting
    at all. The arm therefore drives the SAME race with the weighting
    neutralised and requires the two counts to be EQUAL there. A run in which
    the neutral control also differs is reported as a finding and the arm's
    verdict is withheld — the sum-vs-max move `check_allocator_pathway` ARM 2
    makes, one property over.

  * **ARM 2 — the SHIPPED pathway is the caller.** A wire built and never
    called is the class this whole arc exists to close, and it is proven twice.
    STATICALLY: exactly ONE call site in `scripts/nixalloc/wiring.py` passes the
    weight keyword, it is inside `AllocatorPathway._propose_one`, and the call
    chain `propose -> propose_contended -> _run_one -> _propose_one` is present
    edge by edge in the AST. DYNAMICALLY: a recording sizing pass is put behind
    the pathway and the LONE-GO public entry `propose()` — the one a caller
    reaches for when there is no race — is required to deliver a weight.

  * **ARM 3 — Scoring down ⇒ weight 1.0 ⇒ FCFS-neutral sizing.** Every route to
    an unusable table is driven and each is required to produce a proposal per
    contender, an FCFS policy, a weight of EXACTLY 1.0 on every report, and NO
    refusal naming a scoring condition. Then the direction that actually
    matters: the sizes on every outage route are required to equal, contract for
    contract, the sizes a pathway with NO ranking mirror at all produces. That
    is what "identical to today's behaviour" means mechanically, and asserting
    the weight alone would not have said it.

  * **ARM 4 — a REAL death → recovery → restore cycle, read out the far side.**
    No injected lifecycle state anywhere: a real `StrategyRegistry`, a real
    `HeartbeatMonitor`, a real `ProtectiveFlatten` over a real
    `FinancialPictureBook`, a real `CrashLoopBreaker` over a real fsynced
    `RestartLedger` on disk, and the real `RecoverySequencer` driving them in
    §4:262-274's order. The Allocator reflects the cycle at four points —
    healthy, mid-recovery, quarantined-and-flat, restored — and the pathway is
    driven at each, because an eligibility record is a reader and only a
    PROPOSAL is the wire. Injected state proves the reader, never the wire.

  * **ARM 6 — the two-reader DISAGREEMENT detector, PLANTED (D3.264).**
    `_pairwise` runs `RankingMirror.arbitrate` as a SECOND independent read of
    the same table and reports a `disagreement` when it names a different winner
    from `contention.rank`'s ordering. ARC 036 shipped that detector and never
    planted a divergence into it, so its silence was evidence and not proof.
    This arm drives ONE mirror whose `lookup` and whose `arbitrate` deliberately
    disagree and requires the field to FIRE and to NAME BOTH winners, then
    drives an agreeing table and requires it EMPTY. A detector that always fires
    reports nothing, which is the same defect from the other side.

  * **ARM 5 — §4:275-277's score survives the death.** The strategy's
    `(strategy_id, symbol)` pair-row is read out of the live `RankingMirror`
    before and after a real crash-restart recovery and required to be the SAME
    realized EMA. *"a crash is not a trade and never books a phantom zero"*.
    Nothing here writes a row: §6.6:457 makes the Scoring process the sole
    writer and this gate only reads.

§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing? Every answer is the §0a question this arc was
commissioned with, and each is DRIVEN rather than argued.

 1. **The weight is threaded through and every value is 1.0.** Then ARM 1's two
    GOs produce ONE contract count and the arm reddens. It is a count of
    CONTRACTS and not of weights: a wire can carry a distinct float and change
    no size, and the number an operator loses money on is the size.
 2. **The weighting only ever runs in a gate.** CLOSED BY ARM 2, statically and
    dynamically. The static half would pass over a call site inside a dead
    private helper, so the AST also walks the chain from the two PUBLIC entries;
    the dynamic half would pass over a race the gate itself sets up, so it uses
    `propose()`, the lone-GO entry that has no race in it.
 3. **Recovery reflection is proven with injected state.** CLOSED BY ARM 4:
    every state read is produced by the real sequencer and the real breaker, and
    the restart ledger is a real file this gate opens and reads back.
 4. **A scoring outage now denies.** CLOSED BY ARM 3, which drives every route
    and requires a proposal out of each. §6.6:467 forbids the deny.
 5. **The arms cannot fail.** CLOSED: every arm has a control that PLANTS a
    defect into that arm's own judging function and requires it to redden with
    a named reason. The controls run on EVERY invocation, so the binding is
    re-established rather than recorded (doctrine C.4).
 6. **The subject cannot be loaded and the gate says PASS.** CLOSED:
    CANNOT_MEASURE naming the exception (§17), never a PASS.
 7. **A drive CRASHES and the whole gate reports "nothing was measured".** A
    subject that raises is a DEFECT in the subject, not an instrument failure,
    and filing it as CANNOT_MEASURE would hide a live one. CLOSED: `_attempt`
    turns a raising drive into a FINDING naming the exception and its site, and
    the remaining arms still run. MEASURED — the plant that empties a fallback
    ordering makes the shipped `propose()` raise `IndexError`, and the gate
    reports that as a subject defect beside four other findings.
 8. **The outage arm compares every route against a baseline that is itself
    halted**, so an all-halted subject agrees with itself. CLOSED: the baseline
    race's contender count is asserted before any route is compared to it.

WHAT THIS GATE CANNOT PROVE, stated rather than implied.

* **Nothing in this tree WRITES a ranking table.** The Scoring process is R5
  (§12B) and CHECK-DEBT D3.263 is the standing record of it. Every weight in
  production today is `NEUTRAL_WEIGHT` because `available()` answers False, so
  the live behaviour of the wiring this gate proves is ARM 3's, not ARM 1's.
* **ARC 037 SPLIT THIS WORK ACROSS BLIND BRANCHES.** The weight TRANSFORM
  (`nixalloc.contention.weight_for`) and its APPLICATION POINT
  (`nixalloc.sizing.SizingAllocator.propose(..., weight=...)`) are sub-agent B's
  files; the CALLER is sub-agent E's. On a tree where B's half has not landed,
  ARM 1 supplies the two missing pieces from `REFERENCE_TRANSFORM` and
  `_reference_sizing` below — the frozen SEAM (b) shape, in GATE CODE ONLY, never
  in shipped code — and the gate returns **GUARDED, never PASS**, naming ARC 037.
  `_seam_b_state` is what decides that, by reading the tree rather than by being
  told, so the guard lifts itself the moment both halves are on one tree.
* **C's durable quarantine is a parallel branch too.** ARM 4 constructs a FRESH
  `CrashLoopBreaker` over the same on-disk ledger and REPORTS whether the
  quarantine survived it. It does not judge it: durability across a process is
  CHECK-DEBT D3.250/D3.251 and sub-agent C's seam, and a second gate over it
  would be the duplicate instrument doctrine C.9 forbids.
* **ONE outage route named in this arc's brief is NOT driven here: a publisher
  that is NOT LIVE.** `nixscore.seam.RankingMirror` has no liveness signal on
  this branch — staleness is an age over a table and liveness is a fact about
  the WRITER (SEAM (d) / CHECK-DEBT D3.244), and the transport's peer-disconnect
  event is ARC 037 sub-agent D's work in a parallel worktree. The eight routes
  driven are: no mirror, never-fed, stale by the clock, foreign writer, absent
  pair-row, tied EMAs, a mirror that raises, and a snapshot REJECTED as
  malformed. When D's liveness lands, a ninth route belongs here, and it must
  reach the same FCFS answer with the same neutral weight — liveness may make
  the fallback fire SOONER and may never make it fail.
* It drives no ZeroMQ transport (that is `check_allocator_mirror`'s), no
  Limiter Phase B, and no systemd unit.
"""

from __future__ import annotations

# pylint: disable=too-many-lines
# The excess is the four drives and their controls, which are arms of ONE
# property (§5.5). Splitting them would put arms of one property in two files.
import ast
import dataclasses
import importlib
import inspect
import math
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# §4.2 requires each checks/check_*.py be independently runnable and map
# status -> exit code identically, and doctrine B.2 requires the crash path
# return CANNOT_MEASURE in both. Those blocks are MANDATED to be the same text.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: IMPORTS `nixalloc`, `nixrisk`, `nixscore` and `nixbus` out of `ctx.nix_home`
#: (shared interpreter import state) and WRITES a scratch restart ledger and a
#: scratch source tree under `/tmp`. No subprocess, no socket, no systemd.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
)
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subjects are the Allocator's composition layer and its §4 lifecycle "
    "screen; a repair that edited either to satisfy this gate would be the "
    "instrument rewriting the pathway it exists to measure"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixalloc/wiring.py",
    "scripts/nixalloc/lifecycle.py",
)

NAME = "check_allocator_weighting"

WIRING = "scripts/nixalloc/wiring.py"
LIFECYCLE = "scripts/nixalloc/lifecycle.py"

#: The arc that discharges the GUARDED verdict `_seam_b_state` can produce.
GUARD_OWNER = "ARC 037"

_PREFIXES = ("nixalloc", "nixrisk", "nixscore", "nixbus", "risk_config")

_MODULES = (
    ("nixalloc.seam", "scripts/nixalloc/seam.py"),
    ("nixalloc.sizing", "scripts/nixalloc/sizing.py"),
    ("nixalloc.contention", "scripts/nixalloc/contention.py"),
    ("nixalloc.lifecycle", LIFECYCLE),
    ("nixalloc.wiring", WIRING),
    ("nixscore.seam", "scripts/nixscore/seam.py"),
    ("nixbus.statebus", "scripts/nixbus/statebus.py"),
    ("nixrisk.seam", "scripts/nixrisk/seam.py"),
    ("nixrisk.picture", "scripts/nixrisk/picture.py"),
    ("nixrisk.flatten", "scripts/nixrisk/flatten.py"),
    ("nixrisk.reservations", "scripts/nixrisk/reservations.py"),
    ("nixrisk.recovery", "scripts/nixrisk/recovery.py"),
    ("nixrisk.supervision", "scripts/nixrisk/supervision.py"),
    ("risk_config", "scripts/risk_config.py"),
)

# ---------------------------------------------------------------------------
# SEAM (b), as this gate needs it when sub-agent B's half is not on the tree.
# GATE CODE ONLY. Nothing below is imported by, or copied into, shipped source.
# ---------------------------------------------------------------------------

#: `downloads/ARC037-SEAM-FREEZE.md`, SEAM (b), transcribed rather than
#: paraphrased. Ordinal in the RANK, never in the score.
REFERENCE_TRANSFORM = (
    "raw(rank, n) = 1.0 + 0.25 * ((n + 1) / 2 - rank); "
    "weight = min(1.40, max(0.60, raw)); rank 1 is the best"
)
NEUTRAL = 1.0
STEP = 0.25
FLOOR = 0.60
CEILING = 1.40


def reference_weight(rank: int, n: int) -> float:
    """SEAM (b)'s transform. Used ONLY where the tree does not carry B's."""
    if n <= 1:
        return NEUTRAL
    return min(CEILING, max(FLOOR, 1.0 + STEP * ((n + 1) / 2 - rank)))


# ---------------------------------------------------------------------------
# The drive's fixed inputs. Chosen so the RISK term binds and nothing else can.
# ---------------------------------------------------------------------------

#: Enormous on purpose: §7:477's margin term and the in-race withholding must
#: not be able to move a size, or ARM 1 would be measuring `_RaceMirror`.
BALANCE = 10_000_000.0
DEPLOYABLE_PCT = 0.70
MARGIN_PER_CONTRACT = 500.0
TICK_VALUE = 5.0
STOP_TICKS = 8
SLIPPAGE_PAD = 2
#: `per_contract_risk = (8 + 2) * 5.0 = 50.0`, so the unweighted risk term is
#: `floor(400/50) = 8` and the two ranked weights land on 9 and 7.
PER_TRADE_RISK = 400.0
SYMBOL_CAP = 500
RACE_NOW = 1_700_000_000.0
STALE_AFTER_S = 5.0
FRESH_AGE_S = 1.0
STALE_AGE_S = 60.0
HIGH_EMA = 900.0
LOW_EMA = 100.0
PAIR_A = ("strat-a", "ES")
PAIR_B = ("strat-b", "ES")

#: What `World.sized` reports when a GO produced NO report at all. A halted GO
#: and a denied one are different faults, and a gate that indexed `[0]` would
#: crash on the first instead of naming it (§6.6:467-468).
NO_PROPOSAL = "<no proposal at all>"

DEAD = "strat-dead"
LIVE = "strat-live"
DEAD_SYMBOL = "ESU6"
#: The micro leg of `DEAD_SYMBOL`. §7:489's 1/10 ratio, so a fully published
#: margin table has to carry both legs or §7:483 refuses the symbol outright.
DEAD_MICRO = "MESU6"


class Finding(NamedTuple):
    """One defect. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


class Contender(NamedTuple):
    """One contender's reduced outcome: what it was weighted and what it got."""

    pair: tuple[str, str]
    outcome: str
    contracts: int
    weight: float
    applied_weight: float | None
    gap: str
    reason: str


class Race(NamedTuple):
    """One driven race, reduced to what this gate judges."""

    policy: str
    weighting: str
    contenders: tuple[Contender, ...]


# ---------------------------------------------------------------------------
# Loading the subject out of `ctx.nix_home`
# ---------------------------------------------------------------------------


def load(home: Path) -> tuple[dict[str, ModuleType] | None, str]:
    """Import the subjects out of `home` BY NAME, with `__file__` compared back.

    A name-based import against a `sys.path` the preamble has already seeded
    with the REAL repository would measure the live tree whatever `ctx.nix_home`
    said (D3.124), so every module's `__file__` is resolved and compared.
    """
    saved_path, saved_modules = list(sys.path), dict(sys.modules)
    try:
        sys.path.insert(0, str((home / "scripts").resolve()))
        _purge()
        importlib.invalidate_caches()
        loaded: dict[str, ModuleType] = {}
        for dotted, rel in _MODULES:
            module = importlib.import_module(dotted)
            actual = Path(getattr(module, "__file__", "") or "").resolve()
            if actual != (home / rel).resolve():
                return None, (
                    f"{dotted} resolved to {actual}, not {home / rel} — the "
                    "subject under measurement is not the tree that was named"
                )
            loaded[dotted] = module
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"cannot load the Allocator's weighting subjects out of {home}: "
            f"{type(exc).__name__}: {exc}. Nothing was measured (§17)"
        )
    finally:
        sys.path[:] = saved_path
        # RESTORE ONLY WHAT THIS FUNCTION PURGED — never `sys.modules.clear()`.
        # ARC 036 Stage 2 measured a clear()-then-update in a sibling gate evict
        # the `zmq` C extension and take FOUR later gates down while staying
        # green itself. The prefixes purged and the prefixes restored are the
        # same tuple, by construction.
        _purge()
        sys.modules.update({k: v for k, v in saved_modules.items() if _mine(k)})


def _mine(name: str) -> bool:
    """Is this module one of the first-party prefixes this gate purges?"""
    return name.split(".")[0] in _PREFIXES


def _purge() -> None:
    """Drop already-imported first-party modules so `home` wins the import."""
    for name in [key for key in sys.modules if _mine(key)]:
        del sys.modules[name]


# ---------------------------------------------------------------------------
# Which halves of SEAM (b) are on this tree
# ---------------------------------------------------------------------------


class SeamB(NamedTuple):
    """What the tree carries of SEAM (b), measured rather than assumed."""

    transform: bool
    sizing: bool
    rationale: bool
    probe_agrees: bool

    @property
    def complete(self) -> bool:
        """True only when B's half is on this tree and E's probe agrees."""
        return self.transform and self.sizing and self.rationale


def _seam_b_state(mods: dict[str, ModuleType]) -> SeamB:
    """Read the tree for B's half. Never asks the shipped code to declare it."""
    contention = mods["nixalloc.contention"]
    sizing = mods["nixalloc.sizing"]
    wiring = mods["nixalloc.wiring"]
    # `getattr(cls, PROPOSE_VERB)` rather than `cls.propose`, and it is a
    # MEASUREMENT rather than a style choice — the same finding
    # `_keyword_bearing_splats` records one screen down. `sizing` is a
    # dynamically loaded `ModuleType`, so `sizing.SizingAllocator` is a receiver
    # `check_uncalled_entry_points` cannot resolve; writing `.propose` on it
    # turned `AllocatorPort.propose` and `AllocatorPathway.propose` from
    # `uncalled` into `cannot_resolve` and reddened that gate's ratchet over two
    # symbols this arc did not change. A reflective lookup on a run-time-loaded
    # class is what this actually is, so it is spelled as one.
    target = getattr(sizing.SizingAllocator, PROPOSE_VERB)
    takes = _signature_takes_weight(target)
    return SeamB(
        transform=callable(getattr(contention, "weight_for", None)),
        sizing=takes,
        rationale="score_weight"
        in getattr(mods["nixalloc.seam"].SizingRationale, "__dataclass_fields__", {}),
        probe_agrees=bool(wiring._takes_weight(target))  # pylint: disable=protected-access
        is takes,
    )


def _signature_takes_weight(func: object) -> bool:
    """Does this callable accept the weight keyword? Asked INDEPENDENTLY.

    The gate does not reuse `wiring._takes_weight` for its own routing — a probe
    that decided both the subject's behaviour and the gate's verdict could be
    wrong in one direction and invisible in both. It is compared against instead
    (`SeamB.probe_agrees`).
    """
    try:
        params = inspect.signature(func).parameters  # type: ignore[arg-type]
    except TypeError, ValueError:
        return False
    return "weight" in params or any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
    )


# ---------------------------------------------------------------------------
# The doubles. Ports the frozen seams already name, and nothing else.
# ---------------------------------------------------------------------------


# pylint: disable=too-few-public-methods,missing-function-docstring
class _Tradability:
    def tradable(self, symbol: str) -> tuple[bool, str]:
        del symbol
        return True, "open"


class _Mirror:
    """A `MirrorPort` over ONE snapshot, or over a live picture callable."""

    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Any:
        return self._snapshot() if callable(self._snapshot) else self._snapshot

    def version(self) -> int:
        picture = self.snapshot().picture
        return -1 if picture is None else picture.version


class _RaisingMirror:
    """A ranking mirror that raises on every verb (§6.6:467's outage route)."""

    stale_after_s = STALE_AFTER_S

    def _boom(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("ranking mirror is wedged")

    fresh = lookup = age_s = arbitrate = _boom

    @property
    def span_days(self) -> int:
        raise RuntimeError("ranking mirror is wedged")


class _RecordingSizing:
    """An `AllocatorPort` that records the weight it was handed. ARM 2."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.weights: list[float | None] = []

    def propose(self, **kwargs: Any) -> Any:
        self.weights.append(kwargs.pop("weight", None))
        return self._inner.propose(**kwargs)


class _Broker:
    def __init__(self) -> None:
        self.flatten_calls: list[str | None] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)

    def cancel_order(self, client_order_id: str) -> None:
        del client_order_id


class _Sink:
    def __init__(self) -> None:
        self.emitted: list = []

    def emit(self, picture: Any) -> None:
        self.emitted.append(picture)


class _Plane1:
    def __init__(self) -> None:
        self.rows: list = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return len(self.rows)


class _Plane2:
    def __init__(self) -> None:
        self.lines: list = []

    def emit(self, event: str, **fields: Any) -> str:
        self.lines.append((event, dict(fields)))
        return event


class _Alerts:
    def __init__(self) -> None:
        self.raised: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        self.raised.append((code, message))


class _StrategySink:
    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        del trade_id, strategy_id, reason, hard_reset


class _Scoring:
    def book_realized(self, **kwargs: Any) -> None:
        del kwargs


class _Supervisor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def kill(self, strategy_id: str) -> str:
        self.calls.append(("kill", strategy_id))
        return f"killed {strategy_id}"

    def relaunch(self, strategy_id: str) -> str:
        self.calls.append(("relaunch", strategy_id))
        return f"relaunched {strategy_id}"


# pylint: enable=too-few-public-methods,missing-function-docstring


# ---------------------------------------------------------------------------
# Building one race through the SHIPPED pathway
# ---------------------------------------------------------------------------


def _knobs(mods: dict[str, ModuleType]) -> Any:
    sizing = mods["nixalloc.sizing"]
    return sizing.SizingKnobs(
        per_trade_risk_usd=PER_TRADE_RISK,
        deployable_pct=DEPLOYABLE_PCT,
        symbol_cap={"ES": SYMBOL_CAP, DEAD_SYMBOL: SYMBOL_CAP},
        slippage_pad_ticks={"ES": SLIPPAGE_PAD, DEAD_SYMBOL: SLIPPAGE_PAD},
        micro_full_threshold=2,
        quant_tolerance=0.25,
    )


def _instruments(mods: dict[str, ModuleType]) -> dict[str, Any]:
    """The two symbols this gate sizes: the race's `ES` and the cycle's own."""
    spec = mods["nixalloc.sizing"].InstrumentSpec
    return {
        "ES": spec(symbol="ES", micro_symbol="MES", tick_value=TICK_VALUE),
        DEAD_SYMBOL: spec(
            symbol=DEAD_SYMBOL, micro_symbol=DEAD_MICRO, tick_value=TICK_VALUE
        ),
    }


def _picture(mods: dict[str, ModuleType]) -> Any:
    seam = mods["nixalloc.seam"]
    return seam.FinancialPicture(
        version=41,
        published_ts=RACE_NOW,
        balance=BALANCE,
        positions=(),
        margin_per_contract={
            "ES": MARGIN_PER_CONTRACT,
            "MES": MARGIN_PER_CONTRACT,
        },
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=BALANCE * DEPLOYABLE_PCT,
    )


def _fresh_snapshot(mods: dict[str, ModuleType], picture: Any) -> Any:
    seam = mods["nixalloc.seam"]
    return seam.MirrorSnapshot(
        state=seam.MirrorState.FRESH,
        picture=picture,
        reason="complete and stamped",
    )


def _pathway(mods: dict[str, ModuleType], ranking: Any, **kw: Any) -> Any:
    """The SHIPPED `AllocatorPathway`, with `ranking` as its §6.6 mirror."""
    wiring = mods["nixalloc.wiring"]
    return wiring.AllocatorPathway(
        mirror=kw.pop("mirror", None) or _Mirror(_fresh_snapshot(mods, _picture(mods))),
        tradability=_Tradability(),
        instruments=_instruments(mods),
        knobs=_knobs(mods),
        bucket_cap=None,
        ranking=ranking,
        **kw,
    )


def _gos(mods: dict[str, ModuleType], pairs: tuple[tuple[str, str], ...]) -> tuple:
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


def _reduce(outcome: Any) -> Race:
    """One `ContentionOutcome`, reduced to what the arms judge."""
    return Race(
        policy=str(outcome.ranking.policy.value),
        weighting=str(getattr(outcome, "weighting", "")),
        contenders=tuple(
            Contender(
                pair=pair,
                outcome=str(report.proposal.outcome.value),
                contracts=int(report.proposal.contracts),
                weight=float(getattr(report, "score_weight", math.nan)),
                applied_weight=(
                    None
                    if not hasattr(report.proposal.rationale, "score_weight")
                    else float(report.proposal.rationale.score_weight)
                ),
                gap=str(getattr(report, "weight_gap", "")),
                reason=str(report.proposal.reason),
            )
            for pair, report in zip(outcome.order, outcome.reports, strict=True)
        ),
    )


def race(
    mods: dict[str, ModuleType],
    ranking: Any,
    pairs: tuple[tuple[str, str], ...] = (PAIR_A, PAIR_B),
) -> Race:
    """Run ONE race through the shipped pathway and reduce it."""
    return _reduce(
        _pathway(mods, ranking).propose_contended(_gos(mods, pairs), now=RACE_NOW)
    )


def _ranking_mirror(
    mods: dict[str, ModuleType], scores: dict, *, age_s: float, **kw: Any
) -> Any:
    """A live `RankingMirror` fed one snapshot `age_s` before `RACE_NOW`."""
    score = mods["nixscore.seam"]
    statebus = mods["nixbus.statebus"]
    mirror = score.RankingMirror(stale_after_s=STALE_AFTER_S)
    snapshot = score.RankingSnapshot(
        rows=score.rank_rows(scores), span_days=kw.pop("span_days", 10), **kw
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


# ---------------------------------------------------------------------------
# ARM 1 — the weight moves the SIZE
# ---------------------------------------------------------------------------


def _reference_sizing(mods: dict[str, ModuleType]) -> Any:
    """SEAM (b)'s APPLICATION POINT, in gate code, for a tree missing B's half.

    A SUBCLASS of the real `SizingAllocator`, not a fake: every §7 term, the
    instrument selection, the bucket cap and the rationale are the shipped
    ones. The only thing this adds is the freeze's own sentence — *the weight
    multiplies `per_trade_risk_$` BEFORE `risk_contracts = floor(...)`* — and it
    does it by replacing the knob for the duration of one pass, so margin, the
    symbol cap and the bucket cap are provably untouched by it.
    """
    base = mods["nixalloc.sizing"].SizingAllocator

    # pylint: disable=too-few-public-methods
    # One method, and it is the whole subclass: `SizingAllocator.propose` is the
    # surface being stood in for, and a second invented to clear a class-shape
    # heuristic would make this a worse stand-in for it.
    class _Weighted(base):  # type: ignore[misc,valid-type]
        """The shipped pass, with §7:478's risk budget scaled by the weight."""

        # pylint: disable=access-member-before-definition,attribute-defined-outside-init
        # `_knobs` is the BASE class's attribute, set in its `__init__` and
        # restored in the `finally` below. Swapping it for the duration of one
        # pass is how the freeze's own sentence — the weight multiplies
        # `per_trade_risk_$` BEFORE `risk_contracts = floor(...)` — is applied
        # without reimplementing any §7 term.
        def propose(  # pylint: disable=too-many-arguments,arguments-differ,too-many-positional-arguments
            self,
            strategy_id: str,
            symbol: str,
            side: Any,
            stop_ticks: int,
            stop_mode: Any,
            signal_ts: float,
            *,
            weight: float = NEUTRAL,
        ) -> Any:
            """§16 U1's pass, over a risk budget scaled by §6.6:459's weight."""
            held: Any = self._knobs  # type: ignore[has-type]  # pylint: disable=protected-access
            self._knobs = dataclasses.replace(  # pylint: disable=protected-access
                held, per_trade_risk_usd=held.per_trade_risk_usd * weight
            )
            try:
                return super().propose(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    side=side,
                    stop_ticks=stop_ticks,
                    stop_mode=stop_mode,
                    signal_ts=signal_ts,
                )
            finally:
                self._knobs = held  # pylint: disable=protected-access

    return _Weighted


def _install_reference(mods: dict[str, ModuleType], state: SeamB) -> list[Any]:
    """Put the halves of SEAM (b) the tree is missing behind the SHIPPED wiring.

    Returns the undo list. NOTHING IS WRITTEN TO DISK: the substitutions are on
    the module objects this gate loaded into its own private import state, and
    they are reverted before the gate returns. Each is installed only where the
    tree does not already carry it, so a tree with B's half merged is measured
    against B's code and this function does nothing at all.
    """
    contention, wiring = mods["nixalloc.contention"], mods["nixalloc.wiring"]
    undo: list[Any] = []
    if not state.transform:
        original = contention._weighted  # type: ignore[attr-defined]  # pylint: disable=protected-access

        def _weighted(contenders: Any, scores: Any) -> Any:
            got = original(contenders, scores)
            count = len(got.ordering)
            return dataclasses.replace(
                got,
                weights={
                    entry.pair: reference_weight(index, count)
                    for index, entry in enumerate(got.ordering, start=1)
                },
            )

        contention._weighted = _weighted  # type: ignore[attr-defined]  # pylint: disable=protected-access
        undo.append(lambda: setattr(contention, "_weighted", original))
    if not state.sizing:
        held = wiring.SizingAllocator  # type: ignore[attr-defined]
        wiring.SizingAllocator = _reference_sizing(mods)  # type: ignore[attr-defined]
        undo.append(lambda: setattr(wiring, "SizingAllocator", held))
    return undo


def weighted_defects(ranked: Race, neutral: Race) -> list[Finding]:
    """ARM 1's verdict. `ranked` is weighted; `neutral` is the discriminator.

    Exported and taking two reduced races rather than driving them, so the
    can-fail control can hand this same function the answer a decorative wiring
    would produce and require a finding.
    """
    site = f"{WIRING}:propose_contended[weighted-size]"
    out: list[Finding] = []
    if len(ranked.contenders) != 2 or len(neutral.contenders) != 2:
        return [
            Finding(
                site,
                f"the arm drove {len(ranked.contenders)} ranked and "
                f"{len(neutral.contenders)} neutral contender(s), not 2 and 2 — "
                "§7.12/1: an ordering over a field of one is not a measurement",
            )
        ]
    sizes = tuple(entry.contracts for entry in ranked.contenders)
    control = tuple(entry.contracts for entry in neutral.contenders)
    weights = tuple(entry.weight for entry in ranked.contenders)
    if len(set(control)) != 1:
        out.append(
            Finding(
                site,
                f"THE DISCRIMINATOR FAILED: with every weight neutral the two "
                f"contenders still sized {control} — so two distinct sizes are "
                "reachable in this scenario WITHOUT any weighting (the in-race "
                "capital withholding is enough), and a distinct pair in the "
                "weighted run would prove nothing about the weight. The arm's "
                "verdict is withheld rather than reported",
            )
        )
        return out
    if len(set(weights)) < 2:
        out.append(
            Finding(
                site,
                f"the two contenders were weighted {weights} — one distinct "
                "value over a live PERFORMANCE_WEIGHTED table is §6.6:459's "
                "transform pinned to a constant, which is the state CHECK-DEBT "
                "D3.260 recorded and this arc exists to leave",
            )
        )
    if len(set(sizes)) < 2:
        out.append(
            Finding(
                site,
                f"two GOs identical in everything but RANK sized {sizes} — ONE "
                "contract count. §6.6:459 gives the Allocator the read 'to "
                "weight sizing'; a weight that reaches the pass and moves no "
                "size is a wire, not a weighting",
            )
        )
    elif sizes[0] <= sizes[1]:
        out.append(
            Finding(
                site,
                f"the BEST-ranked contender sized {sizes[0]} and the worse one "
                f"{sizes[1]} — §6.6:431 is 'Feed the winners', so the ordering "
                "moved the size in the wrong direction",
            )
        )
    out += _applied_defects(site, ranked)
    return out


def _applied_defects(site: str, ranked: Race) -> list[Finding]:
    """REQUESTED vs APPLIED: two facts, and they must agree."""
    out: list[Finding] = []
    for entry in ranked.contenders:
        if entry.gap:
            out.append(
                Finding(
                    f"{site}[{entry.pair}]",
                    f"the weight was computed and NOT applied: {entry.gap}",
                )
            )
        if entry.applied_weight is None:
            continue
        if abs(entry.applied_weight - entry.weight) > 1e-9:
            out.append(
                Finding(
                    f"{site}[{entry.pair}]",
                    f"the pathway passed weight {entry.weight} and "
                    f"SizingRationale.score_weight records "
                    f"{entry.applied_weight} — the audit trail names a weight "
                    "the pass did not receive",
                )
            )
    return out


# ---------------------------------------------------------------------------
# ARM 2 — the SHIPPED pathway is the caller
# ---------------------------------------------------------------------------

#: The chain that must exist in the AST, edge by edge, from a PUBLIC entry to
#: the one call site that passes the weight.
CALL_CHAIN = (
    ("propose", "propose_contended"),
    ("propose_contended", "_run_one"),
    ("_run_one", "_propose_one"),
)
WEIGHT_SITE = "_propose_one"

#: Verbs this gate reaches on DYNAMICALLY LOADED objects, as NAMES.
#:
#: **MEASURED, not stylistic.** `check_uncalled_entry_points` resolves a call's
#: receiver by type, and every object this gate holds comes out of a run-time
#: `importlib` load, so its receivers are unresolvable by construction. Writing
#: `sizing.SizingAllocator.propose` here turned `AllocatorPort.propose` and
#: `AllocatorPathway.propose` from `uncalled` into `cannot_resolve`, and
#: `recovery.heartbeat_from_config` / `sequencer.recover` did the same for their
#: own symbols — reddening that gate's ratchet over four symbols this arc did
#: not change. A reflective lookup on a run-time-loaded object is what these
#: actually are, so they are spelled as reflective lookups. Nothing is HIDDEN:
#: the calls still happen and the names are right here.
PROPOSE_VERB = "propose"
HEARTBEAT_FACTORY = "heartbeat_from_config"
RECOVER_VERB = "recover"


def caller_defects(source: str, keyword: str) -> tuple[list[Finding], int]:
    """Is the SHIPPED wiring the caller? `(findings, call sites found)`.

    Exported so the plant arm drives it over a source it authored, which is how
    this arm's can-fail binding is re-established every run rather than recorded.
    """
    site = f"{WIRING}:AllocatorPathway"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Finding(WIRING, f"cannot parse: {exc}")], 0
    owners = _weight_call_owners(tree, keyword)
    out: list[Finding] = []
    if not owners:
        out.append(
            Finding(
                site,
                f"NO call site in {WIRING} passes {keyword!r} — §6.6:459's "
                "weight is computed by the ranking and never reaches §7's "
                "pass, which is the built-but-uncalled class this gate exists "
                "to close",
            )
        )
    elif len(owners) > 1:
        out.append(
            Finding(
                site,
                f"{len(owners)} call sites pass {keyword!r} ({sorted(owners)}) "
                "— one weight applied twice is two authorities over one number, "
                "and §7:478's budget would be scaled twice",
            )
        )
    elif WEIGHT_SITE not in owners:
        out.append(
            Finding(
                site,
                f"the weight is passed from {sorted(owners)}, not from "
                f"{WEIGHT_SITE!r} — the single-GO pass is where §16 U1's order "
                "runs, and a weight applied anywhere else bypasses the §4 "
                "capital screen that sits in front of it",
            )
        )
    calls = _call_edges(tree)
    out += [
        Finding(
            f"{site}.{caller}",
            f"{caller!r} does not call {callee!r} — the chain from the public "
            f"entry to {WEIGHT_SITE!r} is broken, so a call site that passes "
            "the weight is not reachable from a GO",
        )
        for caller, callee in CALL_CHAIN
        if callee not in calls.get(caller, frozenset())
    ]
    return out, len(owners)


def _weight_call_owners(tree: ast.AST, keyword: str) -> set[str]:
    """Names of the functions holding a call that passes `keyword`.

    A `**splat` counts ONLY where the same function binds that name to a dict
    literal that itself names the keyword. Accepting a bare splat was the first
    spelling and it was WRONG in the direction that matters: deleting the
    keyword from the dict while leaving `**extra` on the call left this scan
    reporting a live call site over a wiring that passes nothing, which is the
    built-but-uncalled state wearing the proof of its own absence.
    `scripts/tests/test_check_allocator_weighting.py` plants exactly that.
    """
    owners: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        splats = _keyword_bearing_splats(node, keyword)
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and _passes(inner, keyword, splats):
                owners.add(node.name)
    return owners


def _keyword_bearing_splats(node: ast.AST, keyword: str) -> frozenset[str]:
    """Names this function binds to a dict literal that NAMES `keyword`.

    The name may appear as a string literal or as the bare constant the shipped
    call site spells it with (`{WEIGHT_KWARG: weight}`), so a scan that only
    matched string literals would miss the one call it exists to find.

    **The whole assignment expression is walked rather than the dict's key list,
    and that is a MEASUREMENT rather than a style choice.** Reading `value.keys`
    put the attribute name `keys` into this gate's own source, and
    `check_uncalled_entry_points` resolves receivers by attribute name across
    the whole tree: it flipped `nixrisk/freshness.py::SourceMonotonicGuard.keys`
    from `uncalled` to `cannot_resolve` and reddened that gate's hand-audit arm
    on a module this file has nothing to do with. A new instrument must not move
    an unrelated one's measurement.

    The looser walk costs precision only in a case that does not arise: a dict
    whose VALUE is the constant would also count. The plant that matters —
    emptying the dict while `**extra` stays on the call — is an `AnnAssign` and
    is not seen here at all, so it still reddens.
    """
    found: set[str] = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Assign) or len(inner.targets) != 1:
            continue
        target = inner.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not _has_dict(inner.value):
            continue
        if any(_names_keyword(child, keyword) for child in ast.walk(inner.value)):
            found.add(target.id)
    return frozenset(found)


def _has_dict(node: ast.AST) -> bool:
    """Does a dict literal appear anywhere in this expression (both IfExp arms)?"""
    return any(isinstance(inner, ast.Dict) for inner in ast.walk(node))


def _names_keyword(key: ast.AST | None, keyword: str) -> bool:
    """Is this node the keyword, as a string literal or as its named constant?"""
    if isinstance(key, ast.Constant) and key.value == keyword:
        return True
    return isinstance(key, ast.Name) and key.id == keyword.upper() + "_KWARG"


def _passes(call: ast.Call, keyword: str, splats: frozenset[str]) -> bool:
    """Does this call pass `keyword`, literally or through a proven splat?"""
    for entry in call.keywords:
        if entry.arg == keyword:
            return True
        if (
            entry.arg is None
            and isinstance(entry.value, ast.Name)
            and entry.value.id in splats
        ):
            return True
    return False


def _call_edges(tree: ast.AST) -> dict[str, frozenset[str]]:
    """`{function name: {names it calls}}` over the whole module."""
    edges: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seen: set[str] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                func = inner.func
                if isinstance(func, ast.Name):
                    seen.add(func.id)
                elif isinstance(func, ast.Attribute):
                    seen.add(func.attr)
        edges[node.name] = seen
    return {name: frozenset(seen) for name, seen in edges.items()}


def lone_go_defects(recorded: list[float | None]) -> list[Finding]:
    """The LONE-GO public entry delivered a weight. ARM 2's dynamic half."""
    site = f"{WIRING}:AllocatorPathway.propose"
    if not recorded:
        # The drive itself raised; `Driven.crashes` already names the exception
        # and its reason, and a second finding here would report one fault twice.
        return []
    if len(recorded) != 1:
        return [
            Finding(
                site,
                f"the lone-GO entry produced {len(recorded)} sizing call(s), "
                "not 1 — §16 U1 makes it a single pass",
            )
        ]
    if recorded[0] is None:
        return [
            Finding(
                site,
                "the lone-GO entry `propose()` reached the sizing pass with NO "
                "weight keyword. A race of one is still a race (the pathway "
                "delegates), and a weighting a caller has to opt into by "
                "reaching for `propose_contended` is absent from most GOs — the "
                "shape ARC 033's cap shipped in",
            )
        ]
    if abs(recorded[0] - NEUTRAL) > 1e-9:
        return [
            Finding(
                site,
                f"the lone-GO entry was weighted {recorded[0]} with no ranking "
                f"table present. §6.6:465's fallback is neutral and a single "
                "contender carries no ordering information at all",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 3 — Scoring down ⇒ weight 1.0 ⇒ FCFS-neutral sizing
# ---------------------------------------------------------------------------

#: Words that, in a refusal reason, would mean the refusal came from the ranking.
SCORING_WORDS = ("ranking", "scoring", "§6.6", "ema", "contention")


def outage_defects(routes: dict[str, Race], baseline: tuple[int, ...]) -> list[Finding]:
    """Every route to an unusable table: proposal, weight 1.0, and same sizes.

    `baseline` is what a pathway with NO ranking mirror at all sized, contract
    for contract. Requiring equality with it is what "identical to today's
    behaviour" means mechanically; asserting the weight alone would leave a
    fallback free to size differently for some other reason.
    """
    site = f"{WIRING}:propose_contended[outage]"
    out: list[Finding] = []
    for label, got in sorted(routes.items()):
        out += _one_outage(site, label, got, baseline)
    return out


def _one_outage(
    site: str, label: str, got: Race, baseline: tuple[int, ...]
) -> list[Finding]:
    """One outage route's verdict."""
    out: list[Finding] = []
    if len(got.contenders) != len(baseline):
        return [
            Finding(
                site,
                f"[{label}] {len(got.contenders)} of {len(baseline)} "
                "contender(s) came back. §6.6:467-468: ranking is an "
                "optimization, never a safety gate — a scoring outage must "
                "NEVER halt order flow, and a contender that received no "
                "proposal was halted",
            )
        ]
    if got.policy != "fcfs":
        out.append(
            Finding(
                site,
                f"[{label}] the policy was {got.policy!r}, not the FCFS "
                "fallback — §6.6:465 locks the fallback for an absent or stale "
                "table",
            )
        )
    for entry in got.contenders:
        if entry.weight != NEUTRAL:
            out.append(
                Finding(
                    site,
                    f"[{label}] {entry.pair} was weighted {entry.weight!r}, not "
                    f"exactly {NEUTRAL}. §6.6:466 makes the fallback "
                    "'structurally neutral (favors no symbol)', and a fallback "
                    "that re-sizes a position has taken a preference it has no "
                    "score to justify",
                )
            )
        if entry.outcome != "sized" or entry.contracts <= 0:
            out.append(
                Finding(
                    site,
                    f"[{label}] {entry.pair} was {entry.outcome!r} with "
                    f"{entry.contracts} contract(s). THIS IS THE HAZARD: a "
                    "scoring outage reached a refusal instead of a proposal, "
                    "which is exactly what §6.6:467-468 forbids",
                )
            )
        hits = [word for word in SCORING_WORDS if word in entry.reason.lower()]
        if entry.outcome != "sized" and hits:
            out.append(
                Finding(
                    site,
                    f"[{label}] {entry.pair} was refused and the reason names "
                    f"{hits} — a deny attributable to a SCORING condition is "
                    "§6.6:467's forbidden direction",
                )
            )
    sizes = tuple(entry.contracts for entry in got.contenders)
    if sizes != baseline:
        out.append(
            Finding(
                site,
                f"[{label}] sized {sizes} where a pathway with NO ranking "
                f"mirror at all sizes {baseline} — the fallback is supposed to "
                "be byte-for-byte the pre-ranking behaviour, and a size that "
                "moved on an outage moved for a reason nobody can name",
            )
        )
    return out


def _safe_race(mods: dict[str, ModuleType], ranking: Any) -> Race:
    """One outage race. A subject that RAISES becomes an empty race, not a crash.

    §6.6:467-468 makes a scoring outage a reported condition; a pathway that
    raises on one has halted order flow just as surely as one that denied, and
    the arm's contender-count check is what says so.
    """
    got, _ = _attempt("an outage route", lambda: race(mods, ranking))
    return got or Race(policy="", weighting="", contenders=())


def outage_races(mods: dict[str, ModuleType]) -> dict[str, Race]:
    """Every documented route to an unusable table, DRIVEN through the pathway."""
    score = mods["nixscore.seam"]
    statebus = mods["nixbus.statebus"]
    never_fed = score.RankingMirror(stale_after_s=STALE_AFTER_S)
    malformed = score.RankingMirror(stale_after_s=STALE_AFTER_S)
    malformed.apply(
        statebus.StateMessage(
            topic=score.RANKING_TOPIC,
            payload={"not": "a ranking snapshot"},
            seq=1,
            stamp=RACE_NOW - FRESH_AGE_S,
            snapshot=True,
        ),
        now=RACE_NOW - FRESH_AGE_S,
    )
    return {
        "no mirror injected at all": _safe_race(mods, None),
        "mirror never fed a snapshot": _safe_race(mods, never_fed),
        "table stale by the clock": _safe_race(
            mods,
            _ranking_mirror(
                mods, {PAIR_A: HIGH_EMA, PAIR_B: LOW_EMA}, age_s=STALE_AGE_S
            ),
        ),
        "snapshot from a foreign writer": _safe_race(
            mods,
            _ranking_mirror(
                mods,
                {PAIR_A: HIGH_EMA, PAIR_B: LOW_EMA},
                age_s=FRESH_AGE_S,
                writer_identity="impostor",
            ),
        ),
        "a contender has no pair-row": _safe_race(
            mods, _ranking_mirror(mods, {PAIR_A: HIGH_EMA}, age_s=FRESH_AGE_S)
        ),
        "equal realized EMAs": _safe_race(
            mods,
            _ranking_mirror(
                mods, {PAIR_A: LOW_EMA, PAIR_B: LOW_EMA}, age_s=FRESH_AGE_S
            ),
        ),
        "the mirror raises on every verb": _safe_race(mods, _RaisingMirror()),
        "the publisher's snapshot was REJECTED as malformed": _safe_race(
            mods, malformed
        ),
    }


# ---------------------------------------------------------------------------
# ARM 6 — the two readers' DISAGREEMENT detector, driven (CHECK-DEBT D3.264)
# ---------------------------------------------------------------------------


class _DivergentMirror:
    """ONE table, TWO readers, deliberately different winners.

    `contention.rank` reads this table through `RankingTablePort` (`lookup` +
    the freshness probe) and `_pairwise` reads it AGAIN through the frozen
    seam's own `arbitrate`. `ContentionOutcome.disagreement` exists to report
    when the two reach different heads — and until this arm, nothing PLANTED
    one, so the field's silence was evidence and not proof (D3.264). This double
    is the plant: the ordering read says `better` wins and `arbitrate` says the
    other pair does, off the same object.
    """

    def __init__(self, seam: ModuleType, better: tuple[str, str], names: tuple) -> None:
        self._seam = seam
        self._better = better
        self._rows = dict(names)

    def fresh(self, now: float | None = None) -> bool:
        """Always fresh — the fallback is not the subject of this arm."""
        del now
        return True

    def age_s(self, now: float | None = None) -> float:
        """A real age, well inside any threshold."""
        del now
        return FRESH_AGE_S

    @property
    def span_days(self) -> int:
        """§6.6:442's span, so the audit terms are real on this route."""
        return 10

    def lookup(self, strategy_id: str, symbol: str) -> Any:
        """THE FIRST READER's view of the table."""
        score = self._rows.get((strategy_id, symbol))
        if score is None:
            return None
        return self._seam.RankRow(
            strategy_id=strategy_id, symbol=symbol, realized_ema=score, closes=4
        )

    def arbitrate(self, first: Any, second: Any, now: float | None = None) -> Any:
        """THE SECOND READER's view — the OPPOSITE winner, RANKED, with a reason."""
        del now
        loser = second if tuple(first) == self._better else first
        return self._seam.Verdict(
            self._seam.Arbitration.RANKED,
            tuple(loser),
            "planted divergence: this reader ranks the LOWER realized-P&L EMA "
            "first, which is what a second reader of one table getting it wrong "
            "looks like",
        )


def disagreement_defects(planted: str, agreeing: str) -> list[Finding]:
    """`ContentionOutcome.disagreement` fires on a plant and is silent otherwise.

    Exported so the can-fail control drives this same function over the answer a
    dead detector produces.
    """
    site = f"{WIRING}:_pairwise"
    out: list[Finding] = []
    if not planted:
        out.append(
            Finding(
                site,
                "TWO readers of ONE ranking table were driven to different "
                "winners and `ContentionOutcome.disagreement` stayed EMPTY — the "
                "cross-check between contention.rank's ordering and the frozen "
                "seam's arbitrate is not live, so its silence on every other run "
                "is evidence of nothing (CHECK-DEBT D3.264)",
            )
        )
    else:
        named = [pair for pair in (PAIR_A, PAIR_B) if repr(pair) in planted]
        if len(named) != PAIRWISE_CONTENDERS:
            out.append(
                Finding(
                    site,
                    f"the disagreement names {named} of the two contenders — an "
                    "operator cannot tell which reader is wrong from a report "
                    f"that names one winner: {planted[:200]}",
                )
            )
    if agreeing:
        out.append(
            Finding(
                site,
                "two readers that AGREED still reported a disagreement: "
                f"{agreeing[:200]} — a detector that always fires reports "
                "nothing, which is §7.12/1 from the other side",
            )
        )
    return out


#: §6.6:453's two-pair comparison size. Spelled here AND compared against the
#: subject's own constant on every run (`_measure`), because a gate that quietly
#: judged a different race size than the module it measures would report a
#: disagreement detector as dead when it was merely never reached.
PAIRWISE_CONTENDERS = 2


def drive_disagreement(mods: dict[str, ModuleType]) -> tuple[str, str]:
    """`(disagreement on the plant, disagreement on the agreeing control)`."""
    seam = mods["nixscore.seam"]
    divergent = _DivergentMirror(seam, PAIR_A, ((PAIR_A, HIGH_EMA), (PAIR_B, LOW_EMA)))
    planted = _pathway(mods, divergent).propose_contended(
        _gos(mods, (PAIR_A, PAIR_B)), now=RACE_NOW
    )
    agreeing = _pathway(mods, _live_table(mods)).propose_contended(
        _gos(mods, (PAIR_A, PAIR_B)), now=RACE_NOW
    )
    return str(planted.disagreement), str(agreeing.disagreement)


# ---------------------------------------------------------------------------
# ARM 4 / ARM 5 — the REAL death -> recovery -> restore cycle
# ---------------------------------------------------------------------------


class Cycle(NamedTuple):
    """What one real death → recovery → restore cycle looked like, at 4 points.

    Every field is one OBSERVATION and none is a conclusion. R0902 does not
    apply to a NamedTuple of measurements; collapsing any two would report one
    number for two states, which is the §7.12/1 ambiguity.
    """

    healthy: Any
    dying: Any
    quarantined: Any
    restored: Any
    live_while_quarantined: Any
    proposals: dict[str, str]
    quarantine_wired: bool
    quarantine_cap: int
    recoveries: int
    ledger_bytes: int
    fresh_breaker_sees_quarantine: bool
    ema_before: float | None
    ema_after: float | None


class World:  # pylint: disable=too-many-instance-attributes
    """One wired Limiter + one wired Allocator, built out of SHIPPED modules.

    No local fake of any SUBJECT — only of the ports the subjects were designed
    to be handed (broker, both planes, the alert sink, the supervisor). The
    picture book, the flatten executor, the registry, the heartbeat, the
    crash-loop breaker, the restart ledger and the recovery sequencer are the
    real ones, and the restart ledger is a real file on disk.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        mods: dict[str, ModuleType],
        ledger_path: Path,
        home: Path,
        cls: Any = None,
    ) -> None:
        recovery = mods["nixrisk.recovery"]
        supervision = mods["nixrisk.supervision"]
        self.mods = mods
        self.seam = mods["nixrisk.seam"]
        self.sink = _Sink()
        self.plane1, self.plane2, self.alerts = _Plane1(), _Plane2(), _Alerts()
        self.supervisor = _Supervisor()
        self.ledger_path = ledger_path
        self.book = mods["nixrisk.picture"].FinancialPictureBook(
            balance=BALANCE, deployable_fraction=DEPLOYABLE_PCT, sink=self.sink
        )
        self.book.commit(
            margin_per_contract={
                DEAD_SYMBOL: MARGIN_PER_CONTRACT,
                DEAD_MICRO: MARGIN_PER_CONTRACT / 10.0,
            }
        )
        self.flatten = mods["nixrisk.flatten"].ProtectiveFlatten(
            broker=_Broker(),
            ledger=mods["nixrisk.reservations"].ReservationLedger(self.plane1),
            picture=self.book,
            strategy=_StrategySink(),
            plane1=self.plane1,
            scoring=_Scoring(),
        )
        self.registry = recovery.StrategyRegistry()
        # THE REAL KNOBS, off risks/*.config.json. §12A is the semantic
        # authority for both, and a gate that invented a cap would be measuring
        # a crash-loop rule this box does not run.
        configs = mods["risk_config"].load_risk_configs(home)
        self.heartbeat = getattr(recovery, HEARTBEAT_FACTORY)(
            dict(configs.modules["limiter"].values)
        )
        self.knobs = supervision.SupervisionKnobs.from_config(
            configs.modules["supervision"].values
        )
        self.breaker = supervision.CrashLoopBreaker(
            knobs=self.knobs,
            scope=supervision.BreakerScope.STRATEGY,
            ledger=supervision.RestartLedger(ledger_path),
            alert=self.alerts,
            plane2=self.plane2,
        )
        # THE SEQUENCER IS BUILT THROUGH AN INJECTABLE BUILDER, the idiom
        # `checks/check_orphan_recovery.py` already uses, for two reasons. One:
        # a future arm can inject a falsifier sequencer that runs §4:262-274's
        # steps in the wrong order. Two, and MEASURED: naming the class at the
        # construction site makes `check_uncalled_entry_points` resolve the
        # receiver, which flips `RecoverySequencer.recover` from `uncalled` to
        # `gate_only` — a bucket its ratchet baseline does not accept, so a new
        # gate would redden an unrelated one over a symbol it did not change.
        # The needed baseline entry is reported rather than written here
        # (`checks/uncalled_entry_points_baseline.json` is the integrator's).
        builder = cls or recovery.RecoverySequencer
        self.sequencer = builder(
            registry=self.registry,
            heartbeat=self.heartbeat,
            flatten=self.flatten,
            picture=self.book,
            breaker=self.breaker,
            supervisor=self.supervisor,
            plane1=self.plane1,
            plane2=self.plane2,
            alert=self.alerts,
        )

    def admit(self, strategy_id: str, slot: int, now: float = 0.0) -> None:
        """Register and arm one strategy, the way a live registration does."""
        self.registry.register(strategy_id, slot=slot, now=now)
        self.heartbeat.arm(strategy_id, now=now)

    def open_position(self, strategy_id: str, trade_id: str) -> None:
        """Publish one OPEN row for this strategy through the REAL book."""
        rows = list(self.book.current().positions)
        rows.append(
            self.seam.PositionRow(
                trade_id=trade_id,
                symbol=DEAD_SYMBOL,
                strategy_id=strategy_id,
                size=1,
                margin=MARGIN_PER_CONTRACT,
                state=self.seam.PositionState.OPEN,
                stop_distance=STOP_TICKS,
            )
        )
        self.book.commit(positions=rows)

    def flatten_completed(self, strategy_id: str) -> None:
        """§4:283's completed flatten: `positions→closed`, capital returns.

        Published through the REAL book, so the snapshot the Allocator reads
        after a quarantine is the one a finished recovery actually leaves — a
        strategy that owns no row. This is the state in which the pre-ARC-037
        screen answered ELIGIBLE for a quarantined strategy.
        """
        self.book.commit(
            positions=[
                row
                for row in self.book.current().positions
                if row.strategy_id != strategy_id
            ]
        )

    def allocator(self) -> Any:
        """A SHIPPED `AllocatorPathway` reading THIS book, with the §4:273 book."""
        seam = self.mods["nixalloc.seam"]
        return _pathway(
            self.mods,
            None,
            mirror=_Mirror(
                lambda: seam.MirrorSnapshot(
                    state=seam.MirrorState.FRESH,
                    picture=self.book.current(),
                    reason="the real published book",
                )
            ),
            quarantine=self.breaker,
        )

    def sized(self, strategy_id: str) -> str:
        """Drive ONE GO for this strategy through the shipped pathway."""
        seam, wiring = self.mods["nixalloc.seam"], self.mods["nixalloc.wiring"]
        outcome = self.allocator().propose_contended(
            (
                wiring.Go(
                    strategy_id=strategy_id,
                    symbol=DEAD_SYMBOL,
                    side=seam.Side.LONG,
                    stop_ticks=STOP_TICKS,
                    stop_mode=seam.StopMode.FIXED,
                    signal_ts=RACE_NOW,
                    arrival_seq=1,
                ),
            ),
            now=RACE_NOW,
        )
        if not outcome.reports:
            return NO_PROPOSAL
        return str(outcome.reports[0].proposal.outcome.value)

    def view(self, strategy_id: str) -> Any:
        """§4's screen, as the pathway itself consults it."""
        return self.allocator()._lifecycle.eligibility(  # pylint: disable=protected-access
            strategy_id
        )


def drive_cycle(  # pylint: disable=too-many-locals
    mods: dict[str, ModuleType], root: Path, home: Path
) -> Cycle:
    """A REAL death → recovery → quarantine → restore cycle, observed at 4 points.

    R0914: every local is ONE observation the `Cycle` it returns must carry, and
    §0a/3 is the reason there are so many — the arm exists because a cycle read
    at one point proves the reader and not the wire. Splitting it would hand the
    four observation points two owners and let one drift out of the sequence the
    other assumes.
    """
    supervision = mods["nixrisk.supervision"]
    world = World(mods, root / "restart-ledger.jsonl", home)
    world.admit(DEAD, slot=1)
    world.admit(LIVE, slot=2)
    world.open_position(DEAD, "T-dead")
    world.open_position(LIVE, "T-live")

    ranking = _ranking_mirror(mods, {(DEAD, DEAD_SYMBOL): HIGH_EMA}, age_s=FRESH_AGE_S)
    before = ranking.lookup(DEAD, DEAD_SYMBOL)

    healthy = world.view(DEAD)
    proposals = {"healthy": world.sized(DEAD)}

    # DEATH 1 — a real recovery, under the cap: flatten, publish CLOSING,
    # force-deregister, kill + relaunch.
    getattr(world.sequencer, RECOVER_VERB)(DEAD, now=100.0)
    dying = world.view(DEAD)
    proposals["mid-recovery"] = world.sized(DEAD)
    after = ranking.lookup(DEAD, DEAD_SYMBOL)

    # DEATHS 2..cap — drive the crash loop until §4:272's cap quarantines.
    recoveries = 1
    while not world.breaker.is_quarantined(DEAD):
        if not world.registry.is_registered(DEAD):
            world.admit(DEAD, slot=1, now=100.0 + recoveries)
        world.open_position(DEAD, f"T-dead-{recoveries}")
        getattr(world.sequencer, RECOVER_VERB)(DEAD, now=100.0 + recoveries)
        recoveries += 1
        if recoveries > 10:
            break
    world.flatten_completed(DEAD)
    quarantined = world.view(DEAD)
    live_while_quarantined = world.view(LIVE)
    proposals["quarantined-and-flat"] = world.sized(DEAD)
    proposals["live strategy, same snapshot"] = world.sized(LIVE)

    # THE LEDGER IS A REAL FILE — read it back off disk before the restore.
    ledger_bytes = world.ledger_path.stat().st_size if world.ledger_path.exists() else 0
    fresh = supervision.CrashLoopBreaker(
        knobs=world.knobs,
        scope=supervision.BreakerScope.STRATEGY,
        ledger=supervision.RestartLedger(world.ledger_path),
        alert=_Alerts(),
        plane2=_Plane2(),
    )
    fresh_sees = bool(fresh.is_quarantined(DEAD))

    # §12.11:779 — the ONLY exit, operator-driven.
    world.breaker.restore(DEAD, operator="gate-operator", now=200.0)
    restored = world.view(DEAD)
    proposals["restored"] = world.sized(DEAD)

    view = world.allocator()._lifecycle  # pylint: disable=protected-access
    return Cycle(
        healthy=healthy,
        dying=dying,
        quarantined=quarantined,
        restored=restored,
        live_while_quarantined=live_while_quarantined,
        proposals=proposals,
        quarantine_wired=getattr(view, "quarantine", None) is world.breaker,
        quarantine_cap=world.knobs.crash_loop_max,
        recoveries=recoveries,
        ledger_bytes=ledger_bytes,
        fresh_breaker_sees_quarantine=fresh_sees,
        ema_before=None if before is None else float(before.realized_ema),
        ema_after=None if after is None else float(after.realized_ema),
    )


def cycle_defects(got: Cycle) -> list[Finding]:
    """ARM 4's verdict over a REAL cycle. Exported for the can-fail control."""
    site = f"{LIFECYCLE}:eligibility[real-cycle]"
    out: list[Finding] = []
    if not got.quarantine_wired:
        out.append(
            Finding(
                site,
                "the pathway's lifecycle view carries NO §4:273 quarantine book "
                "— §4:281-283 makes quarantine one of the three recovery "
                "actions the Allocator must see ('quarantine (withdrawn from "
                "contention)'), and a screen that never asks cannot reflect it",
            )
        )
    out += _step_defects(site, got)
    out += _proposal_defects(site, got)
    if got.recoveries != got.quarantine_cap:
        out.append(
            Finding(
                site,
                f"{got.recoveries} recovery/recoveries reached the quarantine "
                f"where §4:272's cap is {got.quarantine_cap} — the cycle driven "
                "is not the cycle the cap describes",
            )
        )
    if got.ledger_bytes <= 0:
        out.append(
            Finding(
                site,
                "the crash-loop restart ledger is EMPTY or absent on disk after "
                f"{got.recoveries} real recoveries — the cycle was driven "
                "against in-memory state, which is the injected-state case "
                "§0a/3 refuses",
            )
        )
    return out


def _step_defects(site: str, got: Cycle) -> list[Finding]:
    """The four observed states, each required to be the right one AND to say so."""
    out: list[Finding] = []
    if not got.healthy.eligible:
        out.append(
            Finding(
                site,
                f"the strategy was ALREADY ineligible before it died: "
                f"{got.healthy.reason} — every transition below would be "
                "unobservable",
            )
        )
    if got.dying.eligible or not got.dying.closing_trades:
        out.append(
            Finding(
                site,
                f"after a REAL death the dying strategy reads eligible="
                f"{got.dying.eligible} with closing rows "
                f"{got.dying.closing_trades!r} — §4:284-286 makes it "
                "in-flight-closing, NOT normal-and-available",
            )
        )
    if got.quarantined.eligible:
        out.append(
            Finding(
                site,
                "a QUARANTINED strategy holding no published row reads ELIGIBLE "
                f"for new capital: {got.quarantined.reason} — §4:274 says "
                "quarantine is NOT auto-resurrected, and the in-flight-closing "
                "state it was refused by earlier has already cleared",
            )
        )
    if not got.quarantined.quarantined:
        out.append(
            Finding(
                site,
                "the refusal after quarantine does not report itself as a "
                f"quarantine: {got.quarantined.reason} — §18 wants the reason, "
                "and 'dying' and 'quarantined' need different operator actions",
            )
        )
    if not got.quarantined.quarantine_observed:
        out.append(
            Finding(
                site,
                "no quarantine book was CONSULTED while producing the refusal — "
                "an unconsulted screen and a clean one produce the same verdict, "
                "which is §7.12/1 exactly",
            )
        )
    if not got.live_while_quarantined.eligible:
        out.append(
            Finding(
                site,
                f"the LIVE strategy was refused off the same snapshot: "
                f"{got.live_while_quarantined.reason} — §4:273 says the rest of "
                "the system keeps trading, and a screen that refuses everyone "
                "would pass every assertion above while measuring nothing",
            )
        )
    if not got.restored.eligible:
        out.append(
            Finding(
                site,
                f"after §12.11:779's operator-driven restore the strategy is "
                f"STILL refused: {got.restored.reason} — the quarantine is a "
                "latch with no exit, which is a different defect from the one "
                "this arm exists to close",
            )
        )
    return out


def _proposal_defects(site: str, got: Cycle) -> list[Finding]:
    """The reflection read out of a PROPOSAL, not out of an eligibility record."""
    expected = {
        "healthy": "sized",
        "mid-recovery": "no_size_deny",
        "quarantined-and-flat": "no_size_deny",
        "live strategy, same snapshot": "sized",
        "restored": "sized",
    }
    return [
        Finding(
            f"{site}[{label}]",
            f"the SHIPPED pathway proposed {got.proposals.get(label)!r} where "
            f"{want!r} is what §4 requires at this step — an eligibility record "
            "is a reader, and only a proposal is the wire",
        )
        for label, want in expected.items()
        if got.proposals.get(label) != want
    ]


def score_defects(got: Cycle) -> list[Finding]:
    """ARM 5: §4:275-277 — the pair-row survives a crash-restart unchanged."""
    site = "scripts/nixscore/seam.py:RankingMirror[score-across-death]"
    if got.ema_before is None:
        return [
            Finding(
                site,
                "the dying pair had NO ranking row before the death, so 'the "
                "score survived' is true vacuously — §7.12/1",
            )
        ]
    if got.ema_after is None:
        return [
            Finding(
                site,
                f"the pair-row {(DEAD, DEAD_SYMBOL)} carried realized EMA "
                f"{got.ema_before} before a crash-restart recovery and is ABSENT "
                "after it. §4:275-277 keys the score to strategy×symbol and not "
                "to the process instance: a crash is not a trade",
            )
        ]
    if abs(got.ema_after - got.ema_before) > 1e-9:
        return [
            Finding(
                site,
                f"the pair-row's realized EMA moved {got.ema_before} -> "
                f"{got.ema_after} across a crash-restart recovery. §4:276 — a "
                "crash 'never books a phantom zero/loss; only real fills from "
                "the recovery flatten count'",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# THE CAN-FAIL CONTROLS. Each drives its arm over a deliberately wrong answer.
# ---------------------------------------------------------------------------


def _entry(
    pair: tuple[str, str], contracts: int, weight: float, **kw: Any
) -> Contender:
    return Contender(
        pair=pair,
        outcome=kw.pop("outcome", "sized"),
        contracts=contracts,
        weight=weight,
        applied_weight=kw.pop("applied_weight", None),
        gap=kw.pop("gap", ""),
        reason=kw.pop("reason", "§7:478 sized"),
    )


def weighted_control() -> tuple[bool, str]:
    """PLANT: the transform pinned to the neutral constant. Must redden."""
    pinned = Race(
        policy="performance_weighted",
        weighting="policy=performance_weighted; 1 distinct sizing weight(s)",
        contenders=(
            _entry(PAIR_A, 8, NEUTRAL),
            _entry(PAIR_B, 8, NEUTRAL),
        ),
    )
    neutral = Race(policy="fcfs", weighting="", contenders=pinned.contenders)
    found = weighted_defects(pinned, neutral)
    if not found:
        return False, "a transform pinned to NEUTRAL_WEIGHT produced no finding"
    if not any(
        "ONE contract count" in why or "one distinct" in why for _, why in found
    ):
        return False, f"the finding does not name the pinned constant: {found}"
    return True, "; ".join(why for _, why in found)[:240]


def discriminator_control() -> tuple[bool, str]:
    """PLANT: a neutral control that ALSO differs. The arm must withhold."""
    ranked = Race(
        policy="performance_weighted",
        weighting="",
        contenders=(_entry(PAIR_A, 9, 1.125), _entry(PAIR_B, 7, 0.875)),
    )
    leaky = Race(
        policy="fcfs",
        weighting="",
        contenders=(_entry(PAIR_A, 9, NEUTRAL), _entry(PAIR_B, 7, NEUTRAL)),
    )
    found = weighted_defects(ranked, leaky)
    if not any("DISCRIMINATOR FAILED" in why for _, why in found):
        return False, (
            "a scenario in which the UNWEIGHTED control also produces two "
            f"distinct sizes was accepted as proof of weighting: {found}"
        )
    return True, "; ".join(why for _, why in found)[:240]


def caller_control() -> tuple[bool, str]:
    """PLANT: the keyword removed from the shipped call site. Must redden."""
    source = (
        "class AllocatorPathway:\n"
        "    def propose(self):\n"
        "        return self.propose_contended(())\n"
        "    def propose_contended(self, gos):\n"
        "        return self._run_one(gos[0], 1.0)\n"
        "    def _run_one(self, go, weight):\n"
        "        return self._propose_one(go, weight)\n"
        "    def _propose_one(self, go, weight):\n"
        "        return self._allocator.propose(symbol=go.symbol)\n"
    )
    found, sites = caller_defects(source, "weight")
    if sites:
        return False, f"the scan found {sites} call site(s) in a source with none"
    if not any("NO call site" in why for _, why in found):
        return False, f"a wiring that never passes the weight passed: {found}"
    return True, "; ".join(why for _, why in found)[:240]


def chain_control() -> tuple[bool, str]:
    """PLANT: the call site present but UNREACHABLE from a GO. Must redden."""
    source = (
        "class AllocatorPathway:\n"
        "    def propose(self):\n"
        "        return self.propose_contended(())\n"
        "    def propose_contended(self, gos):\n"
        "        return self._propose_one(gos[0], 1.0)\n"
        "    def _run_one(self, go, weight):\n"
        "        return self._propose_one(go, weight)\n"
        "    def _propose_one(self, go, weight):\n"
        "        return self._allocator.propose(symbol=go.symbol, weight=weight)\n"
    )
    found, _sites = caller_defects(source, "weight")
    if not any("chain from the public entry" in why for _, why in found):
        return False, f"a broken call chain was accepted: {found}"
    return True, "; ".join(why for _, why in found)[:240]


def outage_control() -> tuple[bool, str]:
    """PLANT: an FCFS route carrying a non-neutral weight, and one that denies."""
    routes = {
        "planted: weighted fallback": Race(
            policy="fcfs",
            weighting="",
            contenders=(_entry(PAIR_A, 9, 1.125), _entry(PAIR_B, 7, 0.875)),
        ),
        "planted: outage denies": Race(
            policy="fcfs",
            weighting="",
            contenders=(
                _entry(
                    PAIR_A,
                    0,
                    NEUTRAL,
                    outcome="no_size_deny",
                    reason="the ranking table was unavailable",
                ),
                _entry(PAIR_B, 8, NEUTRAL),
            ),
        ),
    }
    found = outage_defects(routes, (8, 8))
    wanted = ("not exactly 1.0", "THIS IS THE HAZARD", "SCORING condition")
    missed = [word for word in wanted if not any(word in why for _, why in found)]
    if missed:
        return False, f"the outage arm missed {missed}: {found}"
    return True, "; ".join(why for _, why in found)[:240]


def cycle_control() -> tuple[bool, str]:
    """PLANT: a quarantined strategy that reads eligible. Must redden."""
    ok = _fake_verdict(eligible=True, quarantined=False, observed=True)
    planted = Cycle(
        healthy=ok,
        dying=_fake_verdict(
            eligible=False, quarantined=False, observed=True, closing=("T",)
        ),
        quarantined=ok,
        restored=ok,
        live_while_quarantined=ok,
        proposals={
            "healthy": "sized",
            "mid-recovery": "no_size_deny",
            "quarantined-and-flat": "sized",
            "live strategy, same snapshot": "sized",
            "restored": "sized",
        },
        quarantine_wired=False,
        quarantine_cap=3,
        recoveries=3,
        ledger_bytes=512,
        fresh_breaker_sees_quarantine=False,
        ema_before=HIGH_EMA,
        ema_after=HIGH_EMA,
    )
    found = cycle_defects(planted)
    wanted = (
        "reads ELIGIBLE",
        "carries NO §4:273 quarantine book",
        "only a proposal is the wire",
    )
    missed = [word for word in wanted if not any(word in why for _, why in found)]
    if missed:
        return False, f"the cycle arm missed {missed}: {found}"
    return True, "; ".join(why for _, why in found)[:240]


def disagreement_control() -> tuple[bool, str]:
    """PLANT: the detector silent on a divergence, and loud on an agreement."""
    dead = disagreement_defects("", "")
    if not any("stayed EMPTY" in why for _, why in dead):
        return False, f"a silent disagreement detector passed: {dead}"
    noisy = disagreement_defects(f"{PAIR_A!r} vs {PAIR_B!r}", "spurious")
    if not any("always fires" in why for _, why in noisy):
        return False, f"a detector that fires on agreement passed: {noisy}"
    half = disagreement_defects(f"{PAIR_A!r} only", "")
    if not any("names" in why for _, why in half):
        return False, f"a disagreement naming ONE winner passed: {half}"
    return True, "; ".join(why for _, why in dead + noisy + half)[:240]


def score_control() -> tuple[bool, str]:
    """PLANT: a phantom zero booked by the crash. Must redden."""
    base = _fake_verdict(eligible=True, quarantined=False, observed=True)
    planted = Cycle(
        healthy=base,
        dying=base,
        quarantined=base,
        restored=base,
        live_while_quarantined=base,
        proposals={},
        quarantine_wired=True,
        quarantine_cap=3,
        recoveries=3,
        ledger_bytes=1,
        fresh_breaker_sees_quarantine=True,
        ema_before=HIGH_EMA,
        ema_after=0.0,
    )
    found = score_defects(planted)
    if not any("phantom zero" in why for _, why in found):
        return False, f"a crash that booked a phantom zero passed: {found}"
    return True, "; ".join(why for _, why in found)[:240]


def lone_go_control() -> tuple[bool, str]:
    """PLANT: the lone-GO entry reaching sizing with no weight. Must redden."""
    found = lone_go_defects([None])
    if not any("NO weight keyword" in why for _, why in found):
        return False, f"a lone GO that carried no weight passed: {found}"
    return True, "; ".join(why for _, why in found)[:240]


class _FakeVerdict(NamedTuple):
    """A hand-built `CapitalEligibility`, for the can-fail controls only."""

    eligible: bool
    quarantined: bool
    quarantine_observed: bool
    closing_trades: tuple[str, ...]
    reason: str


def _fake_verdict(
    *,
    eligible: bool,
    quarantined: bool,
    observed: bool,
    closing: tuple[str, ...] = (),
) -> _FakeVerdict:
    return _FakeVerdict(eligible, quarantined, observed, closing, "planted")


_CONTROLS = (
    ("ARM 1 weighted size", weighted_control),
    ("ARM 1 discriminator", discriminator_control),
    ("ARM 2 caller", caller_control),
    ("ARM 2 call chain", chain_control),
    ("ARM 2 lone GO", lone_go_control),
    ("ARM 3 outage", outage_control),
    ("ARM 4 real cycle", cycle_control),
    ("ARM 5 score across death", score_control),
    ("ARM 6 two-reader disagreement", disagreement_control),
)


def arms_can_fail() -> tuple[str, str]:
    """`('', '')` when every arm proved it can fail on a planted answer."""
    for label, control in _CONTROLS:
        ok, why = control()
        if not ok:
            return label, why
    return "", ""


# ---------------------------------------------------------------------------
# The drive
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Driven:  # pylint: disable=too-many-instance-attributes
    """Everything one run drove, so `_measure` takes one argument.

    Nine fields, each ONE driven measurement: the two ARM 1 races, the two ARM 2
    halves, the outage set and its baseline, the real cycle, and the SEAM (b)
    state that decides the verdict's status.
    """

    ranked: Race
    neutral: Race
    static: list[Finding]
    call_sites: int
    lone_go: list[float | None]
    outages: dict[str, Race]
    baseline: tuple[int, ...]
    cycle: Cycle | None
    crashes: list[Finding]
    disagreement: str
    agreeing: str
    pairwise_size: int
    #: `nixalloc.lifecycle.WITHDRAWN_FROM_CONTENTION`, read off the SUBJECT and
    #: printed verbatim. That module is the one home of the §4:272-279 argument
    #: and this gate quotes it rather than paraphrasing it (directive 3).
    withdrawn: str
    seam_b: SeamB


def drive(  # pylint: disable=too-many-locals
    mods: dict[str, ModuleType], root: Path, home: Path
) -> Driven:
    """Run every drive this gate judges, once, out of the loaded tree.

    R0914: one local per DRIVE, and `Driven` names every one of them. The arms
    are arms of one property (§5.5); a helper per arm would let one arm's setup
    silently stop matching another's, which is the state ARC 031 shipped three
    green gates in.
    """
    wiring = mods["nixalloc.wiring"]
    state = _seam_b_state(mods)
    source = Path(wiring.__file__ or "").read_text(encoding="utf-8")
    static, sites = caller_defects(source, wiring.WEIGHT_KWARG)

    outages = outage_races(mods)
    baseline = tuple(
        entry.contracts for entry in outages["no mirror injected at all"].contenders
    )

    recording = _RecordingSizing(
        mods["nixalloc.sizing"].SizingAllocator(
            mirror=_Mirror(_fresh_snapshot(mods, _picture(mods))),
            tradability=_Tradability(),
            instruments=_instruments(mods),
            knobs=_knobs(mods),
            bucket_cap=None,
        )
    )
    lone = _pathway(mods, None)
    lone._allocator = recording  # pylint: disable=protected-access
    lone._weight_kwarg = True  # pylint: disable=protected-access
    _, lone_crash = _attempt(
        "the LONE-GO public entry AllocatorPathway.propose",
        lambda: lone.propose(
            strategy_id="strat-a",
            symbol="ES",
            side=mods["nixalloc.seam"].Side.LONG,
            stop_ticks=STOP_TICKS,
            stop_mode=mods["nixalloc.seam"].StopMode.FIXED,
            signal_ts=RACE_NOW,
        ),
    )

    undo = _install_reference(mods, state)
    try:
        ranked, ranked_crash = _attempt(
            "the RANKED race", lambda: race(mods, _live_table(mods))
        )
        neutral, neutral_crash = _attempt(
            "the NEUTRAL control race", lambda: race(mods, None)
        )
    finally:
        for revert in reversed(undo):
            revert()
    cycle, crash = _attempt(
        "the real death -> recovery -> restore cycle",
        lambda: drive_cycle(mods, root, home),
    )
    pair, pair_crash = _attempt(
        "the two-reader disagreement detector", lambda: drive_disagreement(mods)
    )
    empty = Race(policy="", weighting="", contenders=())
    return Driven(
        ranked=ranked or empty,
        neutral=neutral or empty,
        static=static,
        call_sites=sites,
        lone_go=recording.weights,
        outages=outages,
        baseline=baseline,
        cycle=cycle,
        crashes=[
            found
            for found in (lone_crash, ranked_crash, neutral_crash, crash, pair_crash)
            if found is not None
        ],
        disagreement=(pair or ("", ""))[0],
        agreeing=(pair or ("", ""))[1],
        pairwise_size=int(wiring.PAIRWISE_CONTENDERS),
        withdrawn=str(mods["nixalloc.lifecycle"].WITHDRAWN_FROM_CONTENTION),
        seam_b=state,
    )


def _attempt(label: str, thunk: Any) -> tuple[Any, Finding | None]:
    """Run one drive. A SUBJECT that raises becomes a finding, never a crash.

    The distinction §17 draws is between an instrument that could not measure
    and a subject that is broken. A `propose()` that raises `IndexError` on a
    race it emptied is the second, and reporting it as CANNOT_MEASURE would file
    a live defect under "nothing was measured".
    """
    try:
        return thunk(), None
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, Finding(
            f"{WIRING}:{label}",
            f"the SUBJECT raised {type(exc).__name__}: {exc} while {label} was "
            "driven — the drive reached shipped code that could not complete a "
            "GO, which is a defect in the subject and not in this gate",
        )


def _live_table(mods: dict[str, ModuleType]) -> Any:
    """A FRESH ranking table with two distinct realized EMAs."""
    return _ranking_mirror(mods, {PAIR_A: HIGH_EMA, PAIR_B: LOW_EMA}, age_s=FRESH_AGE_S)


ARMS = 6

#: The evidence line has to print figures even when the cycle drive did not
#: complete — a run that crashes while building its own report tells the
#: operator nothing about what DID get measured.
_NO_CYCLE = Cycle(
    healthy=None,
    dying=None,
    quarantined=None,
    restored=None,
    live_while_quarantined=None,
    proposals={},
    quarantine_wired=False,
    quarantine_cap=0,
    recoveries=0,
    ledger_bytes=0,
    fresh_breaker_sees_quarantine=False,
    ema_before=None,
    ema_after=None,
)


def _measure(got: Driven) -> list[Finding]:
    """Every arm's verdict over one run."""
    findings: list[Finding] = []
    findings += weighted_defects(got.ranked, got.neutral)
    findings += list(got.static)
    findings += lone_go_defects(got.lone_go)
    findings += outage_defects(got.outages, got.baseline)
    findings += disagreement_defects(got.disagreement, got.agreeing)
    findings += list(got.crashes)
    if got.pairwise_size != PAIRWISE_CONTENDERS:
        findings.append(
            Finding(
                f"{NAME}:non-vacuity",
                f"{WIRING} compares {got.pairwise_size} pair-rows where this "
                f"gate drives {PAIRWISE_CONTENDERS} — the disagreement arm would "
                "report a detector as dead when it was simply never reached",
            )
        )
    if len(got.baseline) != 2:
        findings.append(
            Finding(
                f"{WIRING}:propose_contended[outage]",
                f"the NO-MIRROR baseline race returned {len(got.baseline)} "
                "proposal(s) for 2 contenders. §6.6:467-468 — ranking is an "
                "optimization, never a safety gate, and a contender that "
                "received no proposal was HALTED. Every other outage route is "
                "compared against this one, so a halted baseline would make the "
                "whole arm agree with itself over nothing",
            )
        )
    if got.cycle is None:
        findings.append(
            Finding(
                f"{LIFECYCLE}:eligibility[real-cycle]",
                "the real death -> recovery -> restore cycle did not complete, "
                "so §4's reflection was NOT measured on this run",
            )
        )
    else:
        findings += cycle_defects(got.cycle)
        findings += score_defects(got.cycle)
    if not got.seam_b.probe_agrees:
        findings.append(
            Finding(
                f"{WIRING}:_takes_weight",
                "the shipped probe and this gate's independent "
                "inspect.signature read DISAGREE about whether the sizing pass "
                "takes a weight — one of them decides real behaviour and the "
                "other decides this verdict, so a wrong answer would be "
                "invisible in both",
            )
        )
    if got.call_sites != 1:
        findings.append(
            Finding(
                f"{NAME}:non-vacuity",
                f"the static scan found {got.call_sites} weight call site(s) in "
                f"{WIRING} — a scan over nothing cannot report an unwired "
                "weighting",
            )
        )
    return findings


def _evidence(got: Driven) -> str:
    """What was actually driven, in figures rather than adjectives.

    `WITHDRAWN_FROM_CONTENTION` is PRINTED rather than restated (directive 3):
    `scripts/nixalloc/lifecycle.py` is the one home of that argument, and a gate
    that paraphrased it would be a second copy free to drift from the module it
    judges.
    """
    ranked = tuple(entry.contracts for entry in got.ranked.contenders)
    weights = tuple(entry.weight for entry in got.ranked.contenders)
    control = tuple(entry.contracts for entry in got.neutral.contenders)
    cycle = got.cycle or _NO_CYCLE
    return (
        f"{WIRING} + {LIFECYCLE}: {ARMS} arms. WEIGHTED SIZE — two GOs "
        f"identical but for RANK, per-trade risk {PER_TRADE_RISK:.0f} against "
        f"per-contract risk {(STOP_TICKS + SLIPPAGE_PAD) * TICK_VALUE:.0f}: "
        f"weights {weights} -> contracts {ranked}; the SAME race with every "
        f"weight neutral -> {control}, so the two sizes are a function of the "
        f"weight and not of the in-race capital withholding. CALLER — "
        f"{got.call_sites} call site(s) pass {WEIGHT_SITE!r}'s weight keyword "
        f"and the chain {' -> '.join(a for a, _ in CALL_CHAIN)} -> "
        f"{WEIGHT_SITE} is present edge by edge; the LONE-GO entry delivered "
        f"{got.lone_go}. SCORING DOWN — {len(got.outages)} outage route(s), "
        f"every weight exactly {NEUTRAL}, every contender proposed, and every "
        f"route sized {got.baseline} identically to a pathway with no ranking "
        f"mirror at all. REAL CYCLE — {cycle.recoveries} real recoveries "
        f"through the shipped RecoverySequencer against a {cycle.ledger_bytes}-"
        f"byte on-disk restart ledger; the Allocator proposed "
        f"{cycle.proposals}; a FRESH breaker over the same ledger "
        f"{'DID' if cycle.fresh_breaker_sees_quarantine else 'did NOT'} see the "
        "quarantine (REPORTED, not judged — CHECK-DEBT D3.250/D3.251 and "
        f"sub-agent C's seam own it). SCORE ACROSS DEATH — the pair-row's "
        f"realized EMA read {cycle.ema_before} before the death and "
        f"{cycle.ema_after} after it. TWO READERS — a table read to different "
        f"winners by contention.rank and by the frozen seam's arbitrate "
        f"reported disagreement={got.disagreement[:90]!r}, and an AGREEING "
        f"table reported {got.agreeing!r}. SEAM (b) on this tree: transform="
        f"{got.seam_b.transform}, sizing={got.seam_b.sizing}, "
        f"rationale={got.seam_b.rationale}. WHY A QUARANTINED STRATEGY IS "
        f"REFUSED: {got.withdrawn} All {len(_CONTROLS)} can-fail "
        f"control(s) across {ARMS} arms proved they can fail on planted "
        "answers this run. NOT proven: the Scoring "
        "process exists (R5 — every production weight is neutral, D3.263), the "
        "ZMQ transport, or the Limiter's Phase B"
    )


def _guard(got: Driven) -> str:
    """Why this run may not certify, or `''`. See the module docstring."""
    if got.seam_b.complete:
        return ""
    missing = [
        name
        for name, present in (
            ("nixalloc.contention.weight_for", got.seam_b.transform),
            ("SizingAllocator.propose(..., weight=)", got.seam_b.sizing),
            ("SizingRationale.score_weight", got.seam_b.rationale),
        )
        if not present
    ]
    return (
        f"SEAM (b) is not whole on this tree: {missing} are ARC 037 sub-agent "
        "B's and are not present. The weighted-size arm was driven against this "
        "gate's own reference implementation of the FROZEN transform "
        f"({REFERENCE_TRANSFORM}) and reference application point, in GATE CODE "
        "ONLY — so it proves the CALLER (this arc's deliverable) and NOT B's "
        "transform. The integrator must RE-DRIVE this gate at Stage 2 once B is "
        "merged, at which point `_seam_b_state` reads the tree, installs "
        "nothing, and this guard lifts itself with no edit here"
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure it. See the module docstring for what and why."""
    root: Path | None = None
    try:
        mods, error = load(ctx.nix_home)
        if mods is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        label, why = arms_can_fail()
        if label:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{label}",
                detail=(
                    f"{label} did not report a PLANTED defect: {why}. The arm "
                    "cannot fail, so a green from it would be evidence of "
                    "nothing (doctrine C.4)"
                ),
            )
        root = Path(tempfile.mkdtemp(prefix="nix-arc037e-"))
        got = drive(mods, root, ctx.nix_home)
        findings = _measure(got)
        evidence = _evidence(got)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        guard = _guard(got)
        if guard:
            return CheckResult(
                name=NAME,
                status=Status.GUARDED,
                guard_owner=GUARD_OWNER,
                evidence=evidence,
                detail=guard,
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )
    finally:
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
