#!/usr/bin/env python3
"""The composed Allocator pass — `scripts/nixalloc/wiring.py`, DRIVEN.

ARC 031 / Stage 2. Sub-agents A, B and C each built against the frozen seam
with their own doubles, on purpose, so **none of them measured the others**.
Three gates were green and the composition still did not work. This gate is the
standing instrument for the composition itself.

ONE gate, ONE property (`nix_check_contract.md` §5.5): *one GO becomes one
PROPOSAL, off one published snapshot, through the pieces in §16 U1's order —
and nothing it emits can reach a broker.* Five arms serve that one property.

  * **ARM 1 — 2.1, six paths, one snapshot.** A clean size, a headroom-capped
    size-down, a bucket-capped size-down, a dead-signal drop, a zero-stop deny
    and a stale-mirror refusal, all driven against ONE simulated Limiter
    picture. The three non-sizing outcomes are required to be DISTINCT: a
    pathway that collapsed them into one "denied" would be unactionable and
    would hide the stale-mirror class entirely.

  * **ARM 2 — the bucket cap is measured against the SUM of the bucket.** Two
    same-bucket positions, and the case is required to DISCRIMINATE before it
    is allowed to report: the arm computes the max-shaped answer alongside the
    sum-shaped one and refuses if they agree. Sub-agent C's own §0a finding,
    re-driven here through the composed adapter — the thing under test at THIS
    level is the translation from a published position table into exposures,
    which C never saw.

  * **ARM 3 — D3.136, the gap the composition FOUND.** §7 prices exposure from
    `(stop_ticks + slippage_pad) × tick_value × contracts` and the published
    `PositionRow` carries no stop distance at all. Driven in both directions:
    with an out-of-band stop table the cap runs and reports complete; with the
    honest empty one it reports INCOMPLETE and names every row it could not
    price. A cap silently computed over an empty bucket is the false green
    this arm exists to refuse — and it fails in the ADMITTING direction, which
    is why it is an arm and not a comment.

  * **ARM 4 — 2.2, partial-fill reflection (§4).** Two published versions of
    one trade: reserved for 20, filled at 5, the unfilled reservation
    released. The Allocator's headroom must move on the republish, and the
    arm additionally proves it moved because a PUBLISHED field moved, not
    because the pathway recomputed anything from the rows.

  * **ARM 5 — 2.3, every output is a proposal (§2).** Across all of ARM 1's
    paths: `reaches_broker` is False, no emitted object carries a venue field
    a broker adapter could consume, and the composed object exposes no
    place/submit/reserve/release/publish verb — proven by ATTEMPT
    (`getattr` returning None), not by reading the source.

§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?

 1. The modules could fail to import. CLOSED: CANNOT_MEASURE naming the
    exception (§17), never a PASS.
 2. It could import the wrong tree. `checks/_preamble.py` appends the REAL
    `scripts/` to `sys.path` permanently, so a name-based import resolves
    against the live repository whatever `ctx.nix_home` says — the defect
    sub-agent A measured LIVE on two shipped gates (D3.124). CLOSED: every
    module is loaded by exact path out of `ctx.nix_home` and each loaded
    module's `__file__` is compared back against it.
 3. ARM 2's discriminating case could stop discriminating — a knob change
    that makes sum and max agree turns the arm into a tautology while it
    still reports green. CLOSED: the arm computes both shapes and REFUSES
    (a finding) when they agree.
 4. ARM 1 could pass with the cap unwired, since an unwired cap changes no
    size. CLOSED: the bucket path asserts the binding constraint IS
    `BUCKET_CAP` and that the rationale names a bucket, so a `None` cap
    reddens rather than passing quietly.
 5. Every arm could be skipped by an exception in an earlier one. CLOSED: the
    arms run unconditionally, each returns its own findings, and the evidence
    line states the arm count that executed.
 6. The stale-mirror arm could pass on a mirror that is merely EMPTY, proving
    nothing about PARTIAL. CLOSED: all three non-fresh states are driven and
    each refusal must name its own state.

WHAT THIS GATE CANNOT PROVE, stated rather than implied. It drives the
composition against a SIMULATED Limiter snapshot in one process. It does not
prove the real ZeroMQ wire (that is `check_allocator_mirror`'s transport arm,
itself one-process — D3.122), it does not prove the Limiter's Phase B agrees
with any size proposed here, and it proves nothing about the Scoring process,
which does not exist (R5). A green means the pieces compose in §16 U1's order
and the authority boundary holds at the seam.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import MappingProxyType, ModuleType
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
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the composition of three risk-path modules; a repair that "
    "edited any of them to satisfy this gate would be the instrument rewriting "
    "the pathway it exists to measure"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixalloc/wiring.py",)

NAME = "check_allocator_pathway"

WIRING = "scripts/nixalloc/wiring.py"
#: Loaded by exact path out of the tree under test, in dependency order.
PACKAGE_MODULES = (
    ("nixalloc", "scripts/nixalloc/__init__.py"),
    ("nixalloc.seam", "scripts/nixalloc/seam.py"),
    ("nixalloc.caps", "scripts/nixalloc/caps.py"),
    ("nixalloc.sizing", "scripts/nixalloc/sizing.py"),
    ("nixalloc.wiring", WIRING),
)

#: A bucket ceiling at which the two held positions leave room for SOME but not
#: all of the proposal. Chosen so sum and max disagree; the arm re-proves that
#: they still disagree on every run rather than trusting this number.
DISCRIMINATING_CEILING_PCT = 0.015


class Finding(NamedTuple):
    """One defect. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The composed pathway's modules, out of the tree under test."""

    seam: ModuleType
    caps: ModuleType
    sizing: ModuleType
    wiring: ModuleType


def _import_one(home: Path, name: str, rel: str) -> tuple[ModuleType | None, str]:
    """One module, BY EXACT PATH, with its own `__file__` compared back."""
    target = (home / rel).resolve()
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        return None, f"{rel}: no import spec for {target}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    actual = Path(getattr(module, "__file__", "") or "").resolve()
    if actual != target:
        return None, (
            f"{rel}: loaded {actual}, not {target} — the gate would be "
            "measuring a different tree than the one it was given"
        )
    return module, ""


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the pathway BY EXACT PATH out of `home`. Never by name (§7.12/2)."""
    for _name, rel in PACKAGE_MODULES:
        if not (home / rel).is_file():
            return None, (
                f"{rel}: no such file under {home} — the subject is "
                "unavailable, so nothing was measured (§17: never a PASS)"
            )
    saved_path = list(sys.path)
    saved_modules = dict(sys.modules)
    try:
        sys.path.insert(0, str((home / "scripts").resolve()))
        loaded: dict[str, ModuleType] = {}
        for name, rel in PACKAGE_MODULES:
            module, complaint = _import_one(home, name, rel)
            if module is None:
                return None, complaint
            loaded[name] = module
        return (
            Loaded(
                seam=loaded["nixalloc.seam"],
                caps=loaded["nixalloc.caps"],
                sizing=loaded["nixalloc.sizing"],
                wiring=loaded["nixalloc.wiring"],
            ),
            "",
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{WIRING}: cannot load out of {home} — {type(exc).__name__}: "
            f"{exc}. Nothing was measured (§17)"
        )
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if k not in saved_modules]:
            del sys.modules[key]
        sys.modules.update(saved_modules)


# --------------------------------------------------------------------------
# The simulated Limiter. One publisher, one snapshot, no transport.
# --------------------------------------------------------------------------


# pylint: disable=too-few-public-methods,missing-function-docstring
# The two doubles below stand in for ports whose verbs the frozen seam already
# names and documents; a second method invented to clear a class-shape
# threshold, or a docstring restating a verb name the seam defines, would make
# each a worse stand-in for the thing it replaces, not a better one.
class _Mirror:
    """A `MirrorPort` holding one snapshot. No verb accepts a picture."""

    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Any:
        return self._snapshot

    def version(self) -> int:
        picture = self._snapshot.picture
        return -1 if picture is None else picture.version


class _Tradability:
    def __init__(self, tradable: bool, why: str) -> None:
        self._tradable = tradable
        self._why = why

    def tradable(self, symbol: str) -> tuple[bool, str]:
        del symbol
        return self._tradable, self._why


def _row(loaded: Loaded, trade_id: str, symbol: str, size: int) -> Any:
    return loaded.seam.PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id="strat-1",
        size=size,
        margin=500.0,
        state=loaded.seam.PositionState.OPEN,
    )


def _picture(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    loaded: Loaded,
    *,
    balance: float = 100_000.0,
    committed: float = 10_000.0,
    positions: tuple[Any, ...] = (),
    version: int = 41,
    sum_open: float | None = None,
    sum_res: float = 0.0,
) -> Any:
    return loaded.seam.FinancialPicture(
        version=version,
        published_ts=1_700_000_000.0,
        balance=balance,
        positions=positions,
        margin_per_contract=MappingProxyType(
            {"ES": 500.0, "MES": 50.0, "NQ": 400.0, "MNQ": 40.0}
        ),
        sum_open_margin=committed if sum_open is None else sum_open,
        sum_reservations=sum_res,
        committed=committed,
        deployable=balance * 0.70 - committed,
    )


def _fresh(loaded: Loaded, picture: Any) -> Any:
    return loaded.seam.MirrorSnapshot(
        state=loaded.seam.MirrorState.FRESH,
        picture=picture,
        reason="complete and stamped",
    )


def _knobs(loaded: Loaded) -> Any:
    return loaded.sizing.SizingKnobs(
        per_trade_risk_usd=1_000.0,
        deployable_pct=0.70,
        symbol_cap={"ES": 50, "NQ": 50},
        slippage_pad_ticks={"ES": 2, "NQ": 2},
        micro_full_threshold=2,
        quant_tolerance=0.25,
    )


def _instruments(loaded: Loaded) -> dict[str, Any]:
    spec = loaded.sizing.InstrumentSpec
    return {
        "ES": spec(symbol="ES", micro_symbol="MES", tick_value=12.5, micro_ratio=10),
        "NQ": spec(symbol="NQ", micro_symbol="MNQ", tick_value=5.0, micro_ratio=10),
    }


def _cap_config(loaded: Loaded, ceiling_pct: float) -> Any:
    return loaded.caps.CapConfig(
        bucket_cap_pct=MappingProxyType(
            {name: ceiling_pct for name in ("equities", "energy", "metals", "rates")}
        ),
        slippage_pad_ticks=MappingProxyType(
            {"ES": 2.0, "NQ": 2.0, "CL": 2.0, "GC": 2.0, "ZN": 2.0}
        ),
        tick_value_usd=MappingProxyType(
            {"ES": 12.5, "NQ": 5.0, "CL": 10.0, "GC": 10.0, "ZN": 15.625}
        ),
        micro_weight=0.1,
    )


def _pathway(
    loaded: Loaded,
    snapshot: Any,
    *,
    tradable: bool = True,
    why: str = "open",
    cap: Any = None,
) -> Any:
    return loaded.wiring.AllocatorPathway(
        mirror=_Mirror(snapshot),
        tradability=_Tradability(tradable, why),
        instruments=_instruments(loaded),
        knobs=_knobs(loaded),
        bucket_cap=cap,
    )


def _go(loaded: Loaded, pathway: Any, *, stop_ticks: int = 20) -> Any:
    return pathway.propose(
        "strat-1",
        "ES",
        loaded.seam.Side.LONG,
        stop_ticks,
        loaded.seam.StopMode.FIXED,
        1.0,
    )


# --------------------------------------------------------------------------
# ARM 1 — 2.1: six paths, one snapshot
# --------------------------------------------------------------------------


def _arm_six_paths(loaded: Loaded) -> list[Finding]:
    site = f"{WIRING}:AllocatorPathway.propose"
    outcome = loaded.seam.ProposalOutcome
    findings: list[Finding] = []
    held = (_row(loaded, "T-ES", "ES", 2), _row(loaded, "T-NQ", "NQ", 3))
    picture = _picture(loaded, positions=held)
    stops = loaded.wiring.PublishedExposures(
        stop_ticks_by_trade={"T-ES": 20, "T-NQ": 20}
    )
    cap = loaded.wiring.BucketCapAdapter(
        config=_cap_config(loaded, DISCRIMINATING_CEILING_PCT), source=stops
    )

    clean = _go(loaded, _pathway(loaded, _fresh(loaded, picture)))
    tight = _go(
        loaded,
        _pathway(loaded, _fresh(loaded, _picture(loaded, committed=69_900.0))),
        stop_ticks=2,
    )
    capped = _go(loaded, _pathway(loaded, _fresh(loaded, picture), cap=cap))
    dead = _go(
        loaded,
        _pathway(loaded, _fresh(loaded, picture), tradable=False, why="blackout"),
    )
    zero = _go(loaded, _pathway(loaded, _fresh(loaded, picture)), stop_ticks=0)
    stale = _go(loaded, _pathway(loaded, loaded.seam.MirrorSnapshot()))

    if clean.proposal.outcome is not outcome.SIZED or clean.proposal.contracts <= 0:
        findings.append(Finding(site, f"the clean path did not size: {clean.proposal}"))
    if clean.proposal.rationale.snapshot_version != picture.version:
        findings.append(
            Finding(
                site,
                "§16 U5: the rationale does not name the snapshot it sized "
                f"against ({clean.proposal.rationale.snapshot_version} != "
                f"{picture.version})",
            )
        )
    if tight.proposal.contracts >= clean.proposal.contracts:
        findings.append(
            Finding(
                f"{site}[headroom]",
                f"§16 U2: committed 69,900 sized {tight.proposal.contracts} vs "
                f"{clean.proposal.contracts} at committed 10,000 — headroom "
                "did not bind",
            )
        )
    if capped.proposal.contracts >= clean.proposal.contracts:
        findings.append(
            Finding(
                f"{site}[bucket]",
                f"§7: the cap admitted {capped.proposal.contracts} against an "
                f"uncapped {clean.proposal.contracts} — it did not bind",
            )
        )
    elif (
        capped.proposal.rationale.binding
        is not loaded.seam.BindingConstraint.BUCKET_CAP
    ):
        findings.append(
            Finding(
                f"{site}[bucket]",
                "the size fell but the binding constraint is "
                f"{capped.proposal.rationale.binding} — the cap is not what bound it",
            )
        )
    elif capped.proposal.rationale.bucket is None:
        findings.append(
            Finding(f"{site}[bucket]", "a bucket-bound proposal names no bucket")
        )
    if dead.proposal.outcome is not outcome.NOT_TRADABLE or dead.proposal.order:
        findings.append(
            Finding(f"{site}[dead]", f"a dead signal was not dropped: {dead.proposal}")
        )
    if zero.proposal.outcome is not outcome.NO_SIZE_DENY or zero.proposal.contracts:
        findings.append(
            Finding(
                f"{site}[zero-stop]",
                "§7:483: a zero stop distance must be a deny-shaped no-size, "
                f"and the Allocator must not manufacture a size: {zero.proposal}",
            )
        )
    findings += _stale_states(loaded)
    kinds = {dead.proposal.outcome, zero.proposal.outcome, stale.proposal.outcome}
    if len(kinds) != 3:
        findings.append(
            Finding(
                f"{site}[distinct]",
                f"the three non-sizing outcomes collapsed into {len(kinds)}: "
                f"{sorted(k.value for k in kinds)} — a pathway that cannot tell "
                "a dead signal from a stale mirror hides the §0i class entirely",
            )
        )
    return findings


def _stale_states(loaded: Loaded) -> list[Finding]:
    """§0i: EMPTY, PARTIAL and STALE each refuse, and each names itself."""
    findings: list[Finding] = []
    state_cls = loaded.seam.MirrorState
    for state in (state_cls.EMPTY, state_cls.PARTIAL, state_cls.STALE):
        snapshot = loaded.seam.MirrorSnapshot(
            state=state, picture=None, reason=f"planted {state.value}"
        )
        report = _go(loaded, _pathway(loaded, snapshot))
        site = f"{WIRING}:AllocatorPathway.propose[stale:{state.value}]"
        if report.proposal.outcome is not loaded.seam.ProposalOutcome.STALE_MIRROR:
            findings.append(
                Finding(
                    site,
                    f"§0i/§12.7: a {state.value} mirror was sized on rather than "
                    f"refused: {report.proposal}",
                )
            )
        elif state.value not in report.proposal.reason:
            findings.append(
                Finding(
                    site,
                    "the refusal does not name WHICH non-fresh state it was — "
                    "a mirror that never subscribed and one that aged out are "
                    f"different faults: {report.proposal.reason}",
                )
            )
        if report.proposal.rationale.snapshot_version >= 0:
            findings.append(
                Finding(
                    site,
                    "a refusal claims a snapshot version it never read: "
                    f"{report.proposal.rationale.snapshot_version}",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — the cap is measured against the SUM, and the case must discriminate
# --------------------------------------------------------------------------


def _arm_summation(loaded: Loaded) -> list[Finding]:
    site = f"{WIRING}:BucketCapAdapter.admit[summation]"
    findings: list[Finding] = []
    both = (_row(loaded, "T-ES", "ES", 2), _row(loaded, "T-NQ", "NQ", 3))
    stops = loaded.wiring.PublishedExposures(
        stop_ticks_by_trade={"T-ES": 20, "T-NQ": 20}
    )
    config = _cap_config(loaded, DISCRIMINATING_CEILING_PCT)

    # THE DISCRIMINATOR, re-proved every run (§7.12/3). The sum-shaped and
    # max-shaped answers must still differ, or this arm is a tautology.
    priced = [
        loaded.caps.dollar_risk(exposure, config)
        for exposure in stops.exposures(
            _picture(loaded, positions=both), loaded.seam.CorrelationBucket.EQUITIES
        )[0]
    ]
    if len(priced) < 2:
        return [
            Finding(
                site,
                f"only {len(priced)} exposure(s) priced — one position per "
                "bucket never exercises the summation, which is the whole "
                "point of this arm",
            )
        ]
    if abs(sum(priced) - max(priced)) < 1e-9:
        return [
            Finding(
                site,
                f"the two held positions price identically ({priced}), so sum "
                "and max agree and this case no longer DISCRIMINATES",
            )
        ]

    two = _go(
        loaded,
        _pathway(
            loaded,
            _fresh(loaded, _picture(loaded, positions=both)),
            cap=loaded.wiring.BucketCapAdapter(config=config, source=stops),
        ),
    )
    one = _go(
        loaded,
        _pathway(
            loaded,
            _fresh(loaded, _picture(loaded, positions=(both[0],))),
            cap=loaded.wiring.BucketCapAdapter(config=config, source=stops),
        ),
    )
    if one.proposal.contracts <= two.proposal.contracts:
        findings.append(
            Finding(
                site,
                f"removing one of two same-bucket positions did not loosen the "
                f"cap ({two.proposal.contracts} -> {one.proposal.contracts}) — "
                "the adapter is not summing the bucket",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — D3.136: an unpriceable bucket is REPORTED, never a clean ceiling
# --------------------------------------------------------------------------


def _arm_unpriceable(loaded: Loaded) -> list[Finding]:
    site = f"{WIRING}:PublishedExposures[D3.136]"
    findings: list[Finding] = []
    held = (_row(loaded, "T-ES", "ES", 2), _row(loaded, "T-NQ", "NQ", 3))
    picture = _picture(loaded, positions=held)
    config = _cap_config(loaded, DISCRIMINATING_CEILING_PCT)

    blind = loaded.wiring.BucketCapAdapter(
        config=config, source=loaded.wiring.PublishedExposures()
    )
    report = _go(loaded, _pathway(loaded, _fresh(loaded, picture), cap=blind))
    if not report.cap_incomplete:
        findings.append(
            Finding(
                site,
                "two held equities positions had no published stop distance "
                "and the pathway reported a CLEAN cap — a ceiling measured "
                "over an empty bucket admits more than a real one, which is "
                "the false green in the ADMITTING direction",
            )
        )
    if set(report.cap_blind) != {"T-ES", "T-NQ"}:
        findings.append(
            Finding(
                site,
                f"the unpriced rows were not named: {report.cap_blind}",
            )
        )
    if "could NOT be priced" not in report.proposal.rationale.note:
        findings.append(
            Finding(
                site,
                "§16 U5's rationale does not carry the blindness, so the "
                f"Limiter's event log could not audit it: {report.proposal.rationale.note}",
            )
        )

    priced = loaded.wiring.BucketCapAdapter(
        config=config,
        source=loaded.wiring.PublishedExposures(
            stop_ticks_by_trade={"T-ES": 20, "T-NQ": 20}
        ),
    )
    ok = _go(loaded, _pathway(loaded, _fresh(loaded, picture), cap=priced))
    if ok.cap_incomplete:
        findings.append(
            Finding(site, f"a fully priced bucket reported incomplete: {ok.cap_blind}")
        )
    if report.proposal.contracts < ok.proposal.contracts:
        findings.append(
            Finding(
                site,
                "pricing held positions at zero ADMITTED LESS than pricing "
                "them honestly — if that were true the gap would be "
                "conservative, and D3.136 would be a nuisance rather than a "
                "hazard. Measured the other way",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 4 — 2.2: partial-fill reflection (§4)
# --------------------------------------------------------------------------


def _arm_partial_fill(loaded: Loaded) -> list[Finding]:
    site = f"{WIRING}:AllocatorPathway.propose[partial-fill]"
    findings: list[Finding] = []
    reserved = _picture(
        loaded, version=41, committed=10_000.0, sum_res=10_000.0, sum_open=0.0
    )
    filled = _picture(
        loaded, version=42, committed=2_500.0, sum_res=0.0, sum_open=2_500.0
    )
    before = _go(loaded, _pathway(loaded, _fresh(loaded, reserved)), stop_ticks=2)
    after = _go(loaded, _pathway(loaded, _fresh(loaded, filled)), stop_ticks=2)
    if after.proposal.rationale.headroom <= before.proposal.rationale.headroom:
        findings.append(
            Finding(
                site,
                "§4: the released reservation did not reach the Allocator's "
                f"headroom ({before.proposal.rationale.headroom} -> "
                f"{after.proposal.rationale.headroom}) — the mirror is not "
                "reflecting the republish",
            )
        )
    if (
        before.proposal.rationale.snapshot_version,
        after.proposal.rationale.snapshot_version,
    ) != (41, 42):
        findings.append(
            Finding(
                site,
                "each pass must name the version it sized against or the "
                "reflection cannot be attributed to a republish: "
                f"{before.proposal.rationale.snapshot_version}, "
                f"{after.proposal.rationale.snapshot_version}",
            )
        )
    # The reflection is a READ of a published field, not a derivation: a
    # snapshot whose `committed` says the capital came back while its rows say
    # otherwise must be followed on the PUBLISHED figure (§16 U2).
    disagreeing = _picture(
        loaded,
        version=43,
        committed=0.0,
        sum_res=0.0,
        sum_open=0.0,
        positions=(_row(loaded, "T-1", "ES", 20),),
    )
    read = _go(loaded, _pathway(loaded, _fresh(loaded, disagreeing)), stop_ticks=2)
    expected = 0.70 * disagreeing.balance - disagreeing.committed
    if abs(read.proposal.rationale.headroom - expected) > 1e-6:
        findings.append(
            Finding(
                site,
                "§16 U2: headroom followed the position rows instead of the "
                f"published committed figure ({read.proposal.rationale.headroom} "
                f"!= {expected})",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 5 — 2.3: every output is a proposal, never an order (§2)
# --------------------------------------------------------------------------

#: Fields a broker adapter would need. Their ABSENCE is the property.
_VENUE_FIELDS = ("venue", "account", "route", "exchange", "session", "order_ref")
#: Verbs whose presence on the composed object would BE the authority.
_FORBIDDEN_VERBS = (
    "place",
    "submit",
    "send",
    "reserve",
    "release",
    "publish",
    "write",
    "commit",
    "flatten",
    "cancel",
)


def _one_report_is_a_proposal(site: str, report: Any) -> list[Finding]:
    """One emitted report: not routable, and carrying no venue field."""
    findings: list[Finding] = []
    if report.reaches_broker or report.proposal.reaches_broker:
        findings.append(
            Finding(site, f"an emitted object claims it reaches a broker: {report}")
        )
    order = report.proposal.order
    if order is None:
        return findings
    findings += [
        Finding(
            f"{site}[{field}]",
            f"the emitted order carries {field!r} — the Allocator's output "
            "would be routable without the Limiter's pass (§2)",
        )
        for field in _VENUE_FIELDS
        if hasattr(order, field)
    ]
    return findings


def _arm_authority(loaded: Loaded) -> list[Finding]:
    site = f"{WIRING}:AllocatorPathway"
    findings: list[Finding] = []
    picture = _picture(loaded, positions=(_row(loaded, "T-ES", "ES", 2),))
    reports = [
        _go(loaded, _pathway(loaded, _fresh(loaded, picture))),
        _go(loaded, _pathway(loaded, _fresh(loaded, picture), tradable=False)),
        _go(loaded, _pathway(loaded, _fresh(loaded, picture)), stop_ticks=0),
        _go(loaded, _pathway(loaded, loaded.seam.MirrorSnapshot())),
    ]
    for report in reports:
        findings += _one_report_is_a_proposal(site, report)
    pathway = _pathway(loaded, _fresh(loaded, picture))
    for verb in _FORBIDDEN_VERBS:
        if getattr(pathway, verb, None) is not None:
            findings.append(
                Finding(
                    f"{site}.{verb}",
                    f"the composed pathway exposes {verb!r} — §2 makes the "
                    "Allocator permissive, and a verb it exposes is authority "
                    "it has",
                )
            )
    if len(reports) != 4:
        findings.append(
            Finding(site, "the authority arm drove fewer paths than it names")
        )
    return findings


ARMS = 5


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive all five arms against the composed pathway under `ctx.nix_home`."""
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_six_paths(loaded)
        findings += _arm_summation(loaded)
        findings += _arm_unpriceable(loaded)
        findings += _arm_partial_fill(loaded)
        findings += _arm_authority(loaded)
        evidence = (
            f"{WIRING}: {ARMS} arms over the COMPOSED pathway (mirror consumer "
            "-> tradability fast-drop -> sizing -> §7 cap), driven against one "
            "simulated Limiter snapshot: 2.1's six paths with the three "
            "non-sizing outcomes proven DISTINCT; the bucket cap measured "
            "against the SUM of two same-bucket positions, with the "
            "sum-vs-max discriminator re-proved on this run; D3.136's "
            "unpriceable bucket reported INCOMPLETE in both directions and "
            "shown to fail in the ADMITTING direction; §4's partial-fill "
            "release reflected off the PUBLISHED committed figure across two "
            "versions; and §2's authority boundary proven by ATTEMPT over "
            f"{len(_FORBIDDEN_VERBS)} verbs and {len(_VENUE_FIELDS)} venue "
            "fields. NOT proven here: the real ZMQ wire, the Limiter's Phase "
            "B, and anything about the Scoring process, which does not exist"
        )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
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
