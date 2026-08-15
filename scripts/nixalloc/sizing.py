"""The Allocator's sizing pathway — §7's physics, §16 U1/U2/U4/U5's corrections.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless a document is
named on the same line.

THE AUTHORITY THIS MODULE HAS, AND THE AUTHORITY IT DOES NOT (§2, §3)
--------------------------------------------------------------------
The Allocator is **permissive**: it sizes and it PROPOSES. Nothing here gates,
reserves, places, or writes canonical state. The single output type is
`Proposal` (`nixalloc.seam`), whose `reaches_broker` is the constant `False`,
and every number this module consumes arrives on ONE `FinancialPicture` read
from the injected `MirrorPort`. There is no second source for balance, for
`committed`, or for per-symbol margin, and the absence is the design: §16 U2's
whole point is that the Allocator stops recomputing what the Limiter published,
because the recomputation is what produced v1.1's systematic size-down churn at
the gate.

ORDERING IS A PROPERTY OF WHAT RUNS, NOT OF WHAT IS WRITTEN (§16 U1)
--------------------------------------------------------------------
`propose` performs, in this order:

  1. **fast-drop against the tradability cache** — §16 U1's "never size a dead
     signal", delivered here rather than by a round trip through the Limiter;
  2. **fast-drop on a mirror that is not `sizeable`** — §12.7 / §0i, the mirror
     is stale-until-proven-fresh;
  3. the §15 C3 / §7 guards (invalid stop intent, symbol absent from the margin
     cache, instrument constants absent);
  4. the arithmetic;
  5. the `Proposal`, carrying its `SizingRationale` (§16 U5).

Steps 1 and 2 complete before step 4 **runs**, and that is observable rather
than asserted: every arithmetic step is a MODULE-LEVEL function
(`headroom_usd`, `dollar_risk_per_contract`, `risk_contracts`,
`margin_contracts`, `select_instrument`) called through the module globals, so
an observer may replace them with recorders and read the call order that
actually happened. `checks/check_allocator_sizing.py` does exactly that, and
proves its own discriminating power on a deliberate sizes-first falsifier.
A gate that read this docstring, or the source order below, would prove
nothing: source order and execution order are different facts, and the second
is the one §16 U1 is about.

A DEAD SIGNAL NEVER TOUCHES THE MIRROR, AND THE PROPOSAL SAYS SO
----------------------------------------------------------------
`SizingRationale.snapshot_version` is `NO_SNAPSHOT` (-1) on a tradability
fast-drop, because the mirror was never read. `nixalloc.seam.MirrorPort.version`
documents a negative value as "there is none"; a rationale claiming version 0
after a drop would be claiming a read that did not happen.

WHERE THE NUMBERS COME FROM, AND WHY NO NEW CONFIG FILE LANDED HERE
-------------------------------------------------------------------
* **§12A knobs** — `per_trade_risk_usd`, `symbol_cap`, `slippage_pad_ticks`,
  `micro_full_threshold`, `quant_tolerance` are ALREADY homed in
  `risks/allocator.config.json` (ARC 028), and `DEPLOYABLE_PCT` = 0.70 is homed
  in `risks/limiter.config.json` as `deployable_pct`. `SizingKnobs` READS those
  two files through `scripts/risk_config.py` and validates what it read.
  **0.70 is not carved anywhere in this file.** A second physical home for
  either knob would be red under `checks/check_risks_data_only.py` ARM 2 ("a
  knob cited by two files is red because two files that hold one value can
  disagree without either being wrong"), so no `risks/allocator_sizing.config`
  was created.
* **`tick_value` is NOT a knob and has no home in `risks/`, deliberately.** It
  is an instrument constant: `nix_strategy_contract_v1.1.md` §7.2 is explicit
  — *"No hardcoded tick_size / tick_value / symbol constants"* — and they
  arrive on the registration ACK at run time.

  §12A lists no `TICK_VALUE`, so putting one in `risks/` would invent a knob
  the tunables list does not carry. `InstrumentSpec` is therefore INJECTED,
  and a symbol with no spec is `NOT_TRADABLE` — the same posture §7 gives a
  symbol missing from the margin cache.
* **`margin_per_contract`, `balance`, `committed`** — the published mirror, and
  only the published mirror.

WHAT THIS MODULE DOES NOT DO — stated, so no green implies it
-------------------------------------------------------------
* **The §7 correlation-bucket cap is not implemented here.** `BucketCapPort` is
  the injection point and it is a REQUIRED constructor argument with no
  default: passing `None` is a decision a caller has to make in the open, and
  when it is `None` every `SizingRationale.note` says the cap was not applied.
  The implementation is `scripts/nixalloc/caps.py`, a different owner.
* **Contention is `FCFS`, always.** §6.6 makes the Scoring process the sole
  writer of the ranking table, and no writer exists — so `PERFORMANCE_WEIGHTED`
  is unreachable, and §6.6's own fallback is the state the system runs in.
  Arbitration is the LIMITER's (§6.6); this module only records the policy.
* **The mirror's transport and staleness machinery** (`scripts/nixalloc/mirror.py`),
  blackout/calendar windows (R4), the strategy FSM, and the Limiter's Phase B.

THE PHASE-B RE-CHECK IS THE GUARANTEE, NOT REDUNDANCY
-----------------------------------------------------
This module sizes WITHIN headroom, permissively, off a snapshot that may be
one version behind by the time the Limiter evaluates it. §3 names that race and
answers it: *"the rare race ... is caught authoritatively at the Limiter —
trivial wasted sizing, correct outcome."* `AggregateMarginCapRule` in
`scripts/nixrisk/gate.py` is where `committed + proposed < 0.70 × balance` is
ENFORCED. Sizing within headroom here is an optimisation that keeps the gate
from having to size down; it is not a second gate, and it must never be read as
one.

A FINDING ABOUT THE SPEC, REPORTED RATHER THAN ROUTED AROUND — CHECK-DEBT D3.126,
RULED AS SPEC-A8 (ARC 031, Phase 5): §7 GOVERNS, and this module already obeys it
--------------------------------------------------------------------------------
The architect adopted §7's ordering and amended §3:132 to POINT at §7's pipeline
(`docs/SPEC-AMENDMENTS.md`, SPEC-A8; the frozen document is not edited). The ruling
ratifies what shipped, so NOT ONE LINE BELOW CHANGED — which is the whole content of
"mechanical fold". The reasoning the ruling adopted is the reasoning this docstring
recorded at the moment of the choice, and it is left standing below unaltered.

§3:132 orders the pathway `size = min(risk, margin, symbol_cap) → instrument
selection → FCFS → correlation cap`, i.e. selection AFTER the `min`. §7:488-493
orders it the other way: *"compute ideal size in micro units ... if risk-ideal
quantizes acceptably to fulls ... fulls only; otherwise micros only"*, which
makes selection a function of the RISK term alone and prior to the rest.

**§7's order is implemented, and the reason is measurable rather than
aesthetic:** `margin_contracts` divides by `live_margin_per_contract` and
`symbol_cap` is a per-instrument ceiling, so neither term is even DEFINED until
the instrument is known — ES margin is not MES margin. Under §3's literal
order, a risk-ideal of 0.6 fulls yields `min(...) = 0` and denies before micros
are ever considered, which defeats the granularity micros exist for. The two
orders agree on every input where the full contract is selected. D3.126 recorded
the divergence for the architect; SPEC-A8 is the answer, and it is the order above.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from nixalloc.seam import (
    BUCKET_OF,
    AllocatorPort,
    BindingConstraint,
    ContentionPolicy,
    CorrelationBucket,
    FinancialPicture,
    MirrorPort,
    Proposal,
    ProposalOutcome,
    ProposedOrder,
    Side,
    SizingRationale,
    StopMode,
    TradabilityCachePort,
)

# pylint: disable=too-few-public-methods
# `BucketCapPort` and `InstrumentSpecPort`-shaped value types carry exactly the
# verbs and fields their subject has. Inventing a second method to clear a
# class-shape threshold would make each a worse stand-in for the thing it
# stands in for (§2: every verb invented is authority granted).

__all__ = [
    "NO_SNAPSHOT",
    "BucketCapPort",
    "BucketQuery",
    "BucketVerdict",
    "Instrument",
    "InstrumentSpec",
    "SizingAllocator",
    "SizingConfigError",
    "SizingKnobs",
    "dollar_risk_per_contract",
    "headroom_usd",
    "load_sizing_knobs",
    "margin_contracts",
    "risk_contracts",
    "select_instrument",
]

#: The `snapshot_version` a rationale carries when NO mirror read happened.
#: Negative because `MirrorPort.version` documents negative as "there is none",
#: and 0 is a plausible first version (`nixalloc/seam.py:277-283`).
NO_SNAPSHOT = -1

#: The module whose config holds §12A's `DEPLOYABLE_PCT`. Named, not guessed:
#: `risks/limiter.config.json` is its ONE physical home (ARM 2 of
#: `checks/check_risks_data_only.py`), and the Allocator reads it from there
#: rather than carrying a second copy.
DEPLOYABLE_PCT_MODULE = "limiter"
DEPLOYABLE_PCT_KEY = "deployable_pct"
ALLOCATOR_MODULE = "allocator"


class SizingConfigError(ValueError):
    """A knob set this module refuses to size on.

    Never degraded to a default (directive 4, doctrine C.7): every knob below
    bounds a quantity that reaches a broker, and a silently substituted default
    would size real money off a number nobody chose.
    """


# ---------------------------------------------------------------------------
# Instrument constants (§7) — injected, never config, never carved
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstrumentSpec:
    """One symbol's contract constants: the full leg, its micro, and the ratio.

    `nix_strategy_contract_v1.1.md` §7.2 forbids hardcoding these and delivers
    them on the registration ACK, so they are injected here rather than read
    from `risks/`.

    §7:489 fixes the ratio's meaning — *"micro units (MES etc. = 1/10)"* —
    and the field exists so the 10 is a per-symbol datum rather than a
    constant this module asserts about every product forever.
    """

    symbol: str
    micro_symbol: str
    tick_value: float
    micro_ratio: int = 10

    def defect(self) -> str:
        """Why this spec cannot be sized against, or `""`."""
        if not math.isfinite(self.tick_value) or self.tick_value <= 0.0:
            return f"tick_value {self.tick_value!r} is not a positive finite number"
        if self.micro_ratio < 1:
            return f"micro_ratio {self.micro_ratio!r} is below 1"
        if not self.symbol or not self.micro_symbol:
            return "symbol and micro_symbol must both be named"
        return ""


@dataclass(frozen=True)
class Instrument:
    """The instrument SELECTED for one proposal, in its own units.

    `units_per_full` is the §7:502 weight in reverse: a micro is 1/10 of a
    full, so ten micro units make one full's exposure. It is what converts a
    per-symbol ceiling expressed in fulls into the selected instrument's units.
    """

    symbol: str
    tick_value: float
    units_per_full: int
    is_micro: bool


# ---------------------------------------------------------------------------
# §12A knobs (read from `risks/`, validated here)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SizingKnobs:
    """The §12A tunables this pathway reads. Frozen; validated on construction.

    `deployable_pct` is §12A:811's `DEPLOYABLE_PCT` and it is READ, not carved:
    §16 U2's headroom is `DEPLOYABLE_PCT × balance − committed`, and a literal
    0.70 in this file would be a second authority for a number
    `risks/limiter.config.json` already owns.
    """

    per_trade_risk_usd: float
    deployable_pct: float
    symbol_cap: Mapping[str, int]
    slippage_pad_ticks: Mapping[str, int]
    micro_full_threshold: int
    quant_tolerance: float

    def __post_init__(self) -> None:
        """Refuse an invalid set at construction (§12A:801 boot validation)."""
        problems = _knob_defects(self)
        if problems:
            raise SizingConfigError("; ".join(problems))


def _positive(name: str, value: float) -> str:
    if not math.isfinite(value) or value <= 0.0:
        return f"{name}={value!r} must be a positive finite number"
    return ""


def _map_defects(name: str, table: Mapping[str, int], floor: int) -> list[str]:
    """Every entry is an int at or above `floor`. Bools are not ints here."""
    found: list[str] = []
    if not table:
        found.append(f"{name} is empty — a sizing pass has no symbol it may size")
    for symbol, value in table.items():
        if isinstance(value, bool) or not isinstance(value, int):
            found.append(f"{name}[{symbol}]={value!r} is not an int")
        elif value < floor:
            found.append(f"{name}[{symbol}]={value!r} is below {floor}")
    return found


def _knob_defects(knobs: SizingKnobs) -> list[str]:
    """Every reason this set must not size. Collected, never short-circuited."""
    found = [
        complaint
        for complaint in (
            _positive("per_trade_risk_usd", knobs.per_trade_risk_usd),
            _positive("deployable_pct", knobs.deployable_pct),
        )
        if complaint
    ]
    if math.isfinite(knobs.deployable_pct) and knobs.deployable_pct > 1.0:
        found.append(
            f"deployable_pct={knobs.deployable_pct!r} exceeds 1.0 — §6.5's "
            "'30% buffer / 70% deployable' is a fraction of balance"
        )
    found += _map_defects("symbol_cap", knobs.symbol_cap, 1)
    found += _map_defects("slippage_pad_ticks", knobs.slippage_pad_ticks, 0)
    if set(knobs.symbol_cap) != set(knobs.slippage_pad_ticks):
        found.append(
            "symbol_cap and slippage_pad_ticks cover different symbols — §7:483's "
            "posture is that a half-configured symbol is not sizeable, and a pad "
            "missing for a capped symbol would size against an unpadded stop"
        )
    if knobs.micro_full_threshold < 1:
        found.append(
            f"micro_full_threshold={knobs.micro_full_threshold!r} is below 1 — "
            "§7:492 counts WHOLE fulls, so a threshold under one selects fulls "
            "for a risk-ideal of zero contracts"
        )
    if not 0.0 <= knobs.quant_tolerance < 1.0:
        found.append(
            f"quant_tolerance={knobs.quant_tolerance!r} is outside [0, 1) — it is "
            "a fraction of ONE full contract (§7:492), and 1.0 admits every "
            "quantization error, which is the rule switched off"
        )
    return found


def _int_map(raw: object, name: str) -> dict[str, int]:
    """A `risks/` map read as ints. Raises rather than coercing a float silently."""
    if not isinstance(raw, Mapping):
        raise SizingConfigError(f"{name} is {type(raw).__name__}, expected an object")
    out: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise SizingConfigError(f"{name}[{key}]={value!r} is not an int")
        out[str(key)] = value
    return out


def _float(raw: object, name: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SizingConfigError(f"{name} is {type(raw).__name__}, expected a number")
    return float(raw)


def _int(raw: object, name: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SizingConfigError(f"{name} is {type(raw).__name__}, expected an int")
    return raw


def load_sizing_knobs(root: Path | None = None) -> SizingKnobs:
    """Read §12A's sizing knobs out of `risks/`. Raises `SizingConfigError`.

    Called ONCE, at boot (§12.11: boot-loaded, restart-only). There is no
    reload entry point, and the two source files are read through the loader
    that already owns them rather than parsed again here — a second parser is a
    second authority for the same bytes.
    """
    # Imported inside the function so `nixalloc.sizing` stays importable in a
    # tree that has no `risks/` — the check drives this module against copies.
    import risk_config  # pylint: disable=import-outside-toplevel

    try:
        configs = risk_config.load_risk_configs(root)
    except risk_config.RiskConfigError as exc:
        raise SizingConfigError(f"risks/ would not load: {exc}") from exc
    read = configs.value
    return SizingKnobs(
        per_trade_risk_usd=_float(
            read(ALLOCATOR_MODULE, "per_trade_risk_usd"), "per_trade_risk_usd"
        ),
        deployable_pct=_float(
            read(DEPLOYABLE_PCT_MODULE, DEPLOYABLE_PCT_KEY), DEPLOYABLE_PCT_KEY
        ),
        symbol_cap=_int_map(read(ALLOCATOR_MODULE, "symbol_cap"), "symbol_cap"),
        slippage_pad_ticks=_int_map(
            read(ALLOCATOR_MODULE, "slippage_pad_ticks"), "slippage_pad_ticks"
        ),
        micro_full_threshold=_int(
            read(ALLOCATOR_MODULE, "micro_full_threshold"), "micro_full_threshold"
        ),
        quant_tolerance=_float(
            read(ALLOCATOR_MODULE, "quant_tolerance"), "quant_tolerance"
        ),
    )


# ---------------------------------------------------------------------------
# The correlation-bucket cap's INJECTION POINT — not its implementation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BucketVerdict:
    """What a §7 bucket cap admitted, and the figures it admitted it against."""

    contracts: int
    used: float
    ceiling: float
    note: str = ""


@dataclass(frozen=True)
class BucketQuery:
    """Everything §7:501's exposure unit needs to price ONE proposal.

    ARC 031 / Stage 2 WIDENED this seam, and the reason is a measurement
    rather than a preference. The port originally passed
    `(bucket, contracts, risk_per_contract, picture)`, and Stage 2's
    integration found that insufficient the first time a real implementation
    was wired behind it: §7's cap prices exposure from
    `(stop_ticks + slippage_pad) × tick_value × contracts`, so an
    implementation needs the LOGICAL symbol (to resolve the bucket and the
    per-symbol pad and tick value), the STOP DISTANCE, and whether the
    selected instrument is a micro leg (§7:502 counts micros at 1/10). None of
    those three could be recovered from the old arguments: `equities` holds
    two symbols, so the bucket alone does not name the proposal's symbol, and
    the pass silently reported "cap NOT APPLIED" for every equities proposal
    on a snapshot that priced both ES and NQ — the normal case.

    Neither Stage-1 gate could see it. Sub-agent B drove the port with `None`
    and asserted the not-applied sentence; sub-agent C drove `caps.admit`
    directly with `Exposure` rows it constructed. The argument between them
    was never made until Stage 2 made it.
    """

    #: The LOGICAL symbol (ES, not MES) — §7:498's bucket map is keyed on it.
    symbol: str
    bucket: CorrelationBucket
    contracts: int
    stop_ticks: int
    #: True when instrument selection chose the micro leg (§16 U4, §7:502).
    micro: bool
    #: The pass's own per-contract dollar risk, carried so an implementation
    #: can cross-check its own pricing against the sizer's.
    risk_per_contract: float
    picture: FinancialPicture


@runtime_checkable
class BucketCapPort(Protocol):
    """§7:505-515's same-bucket dollar-risk ceiling. Implemented elsewhere.

    Declared here as the seam this pathway calls, and NOT implemented here:
    `scripts/nixalloc/caps.py` owns the formula and
    `scripts/nixalloc/wiring.py` owns the adapter. `SizingAllocator` takes it
    as a required argument so a caller with no cap wired has to say `None` out
    loud rather than acquire a permissive default by omission.
    """

    def admit(self, query: BucketQuery) -> BucketVerdict:
        """Clamp `query.contracts` toward B's ceiling. Never raises the size."""


# ---------------------------------------------------------------------------
# THE ARITHMETIC — module-level so an observer can watch it run (§16 U1)
# ---------------------------------------------------------------------------


def headroom_usd(picture: FinancialPicture, deployable_pct: float) -> float:
    """§16 U2: `DEPLOYABLE_PCT × balance − committed`. TWO published reads.

    `committed` is READ. It is never re-derived from `picture.positions`, and
    the position table is not touched at all: §3 publishes `committed` as a
    running aggregate under one version stamp, §16 U2 makes reading it the
    thing that "kills systematic size-down churn at the gate", and a consumer
    that re-summed the rows would be a second authority for a number the
    Limiter owns — free to disagree with the gate that enforces it.

    May be negative. The clamp is `margin_contracts`' job, not this one's: a
    negative headroom is a real, reportable state and flattening it to zero
    here would hide it from `SizingRationale.headroom`.
    """
    return deployable_pct * picture.balance - picture.committed


def dollar_risk_per_contract(
    stop_ticks: int, slippage_pad_ticks: int, tick_value: float
) -> float:
    """§7:476's denominator: `(stop_ticks + slippage_pad) × tick_value`.

    The pad is INSIDE the dollar-risk figure, not applied afterwards — §7:481:
    *"stops gap through (news spikes); `risk_$` is honest only if sized against
    stop + expected slippage"*. It is the same figure §7:501 makes the
    correlation bucket's exposure unit, so both uses read one definition.
    """
    return max(0, stop_ticks + slippage_pad_ticks) * tick_value


def risk_contracts(per_trade_risk_usd: float, per_contract_risk: float) -> int:
    """§7:476's risk term, floored and clamped ≥ 0 (§15 C3)."""
    if per_contract_risk <= 0.0 or not math.isfinite(per_contract_risk):
        return 0
    return max(0, math.floor(per_trade_risk_usd / per_contract_risk))


def margin_contracts(headroom: float, margin_per_contract: float) -> int:
    """§7:477's margin term: `floor(max(0, headroom) / live_margin)`.

    `max(0, headroom)` is §7:483's *"every term clamps ≥ 0 (no negative-floor
    artifacts)"* at the one place a negative can arise — a `committed` above
    `DEPLOYABLE_PCT × balance`, which is an ordinary state after a fill.
    """
    if margin_per_contract <= 0.0 or not math.isfinite(margin_per_contract):
        return 0
    return max(0, math.floor(max(0.0, headroom) / margin_per_contract))


def select_instrument(
    ideal_micro_units: float, spec: InstrumentSpec, knobs: SizingKnobs
) -> Instrument:
    """§7:488-493 / §16 U4: fulls only, or micros only. Never both.

    *"compute ideal size in micro units (MES etc. = 1/10). One instrument per
    trade — no mixed full+micro legs in v1 ... if risk-ideal quantizes
    acceptably to fulls (≥ threshold fulls, quantization error ≤ tolerance) ⇒
    fulls only; otherwise micros only."*

    Both halves of the condition are load-bearing and both are measured:
    `whole_fulls` is the "≥ threshold fulls" half and `quant_error` — the
    fraction of a full contract that fulls-only would throw away — is the
    "quantization error ≤ tolerance" half.
    """
    ideal_fulls = ideal_micro_units / spec.micro_ratio
    whole_fulls = math.floor(ideal_fulls)
    quant_error = ideal_fulls - whole_fulls
    if (
        whole_fulls >= knobs.micro_full_threshold
        and quant_error <= knobs.quant_tolerance
    ):
        return Instrument(
            symbol=spec.symbol,
            tick_value=spec.tick_value,
            units_per_full=1,
            is_micro=False,
        )
    return Instrument(
        symbol=spec.micro_symbol,
        tick_value=spec.tick_value / spec.micro_ratio,
        units_per_full=spec.micro_ratio,
        is_micro=True,
    )


def _binding_of(risk: int, margin: int, cap: int, headroom: float) -> BindingConstraint:
    """Which term of §7:478's `min(...)` decided the size (§16 U5).

    `HEADROOM` and `MARGIN` are separated on the fact that distinguishes them:
    when headroom itself is at or below zero the account has no deployable
    room at all, and reporting `MARGIN` there would send an operator to look at
    a per-contract margin figure that is not what bound the trade.
    """
    smallest = min(risk, margin, cap)
    if margin == smallest and headroom <= 0.0:
        return BindingConstraint.HEADROOM
    if risk == smallest:
        return BindingConstraint.RISK
    if margin == smallest:
        return BindingConstraint.MARGIN
    return BindingConstraint.SYMBOL_CAP


def _empty_rationale(note: str, version: int = NO_SNAPSHOT) -> SizingRationale:
    """The rationale a NON-sizing outcome carries. Zeros, and a reason.

    Zeros rather than plausible-looking figures: §16 U5 makes this object the
    Limiter's audit record, and a `risk_contracts` of 3 on a proposal that
    never sized would put a number nobody computed into the event log.
    """
    return SizingRationale(
        binding=BindingConstraint.NONE,
        snapshot_version=version,
        risk_contracts=0,
        margin_contracts=0,
        symbol_cap=0,
        headroom=0.0,
        bucket=None,
        bucket_used=0.0,
        bucket_ceiling=0.0,
        contention=ContentionPolicy.FCFS,
        note=note,
    )


@dataclass(frozen=True)
class _Sized:
    """One sizing pass's intermediate terms, before the bucket cap."""

    instrument: Instrument
    per_contract_risk: float
    risk: int
    margin: int
    cap: int
    headroom: float
    margin_per_contract: float


@dataclass(frozen=True)
class _Settled:
    """The size that survived `min(...)` and the bucket cap, plus its rationale."""

    contracts: int
    rationale: SizingRationale


# ---------------------------------------------------------------------------
# The Allocator
# ---------------------------------------------------------------------------


class SizingAllocator:
    """`AllocatorPort`: one GO in, one `Proposal` out. Synchronous, single-pass.

    Construct once at boot. Every dependency is injected — the mirror, the
    tradability cache, the instrument specs, the knobs, and the bucket cap —
    because every one of them is owned by a different module and this class
    must not be able to acquire a second source for any of them.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        mirror: MirrorPort,
        tradability: TradabilityCachePort,
        instruments: Mapping[str, InstrumentSpec],
        knobs: SizingKnobs,
        bucket_cap: BucketCapPort | None,
    ) -> None:
        """`bucket_cap` has NO default: `None` is a decision, not an omission."""
        self._mirror = mirror
        self._tradability = tradability
        self._instruments = dict(instruments)
        self._knobs = knobs
        self._bucket_cap = bucket_cap

    # -- the pass -----------------------------------------------------------

    def propose(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        strategy_id: str,
        symbol: str,
        side: Side,
        stop_ticks: int,
        stop_mode: StopMode,
        signal_ts: float,
    ) -> Proposal:
        """§16 U1's single pass, in §16 U1's order. See the module docstring.

        The three early returns below happen BEFORE any call into this module's
        arithmetic functions, and the first of them happens before the mirror
        is read at all.
        """
        drop = self._fast_drop(strategy_id, symbol)
        if drop is not None:
            return drop
        snapshot = self._mirror.snapshot()
        if not snapshot.sizeable or snapshot.picture is None:
            return self._refuse(
                ProposalOutcome.STALE_MIRROR,
                strategy_id,
                symbol,
                f"§0i/§12.7: mirror is {snapshot.state.value} — {snapshot.reason}",
                version=self._mirror.version(),
            )
        picture = snapshot.picture
        guard = self._guard(strategy_id, symbol, stop_ticks, picture)
        if guard is not None:
            return guard
        return self._size(
            strategy_id, symbol, side, stop_ticks, stop_mode, signal_ts, picture
        )

    # -- step 1: never size a dead signal (§16 U1) --------------------------

    def _fast_drop(self, strategy_id: str, symbol: str) -> Proposal | None:
        """The tradability cache, and NOTHING else. No mirror read lives here.

        §3:118 puts this drop on the Allocator "permissively at ingress", and
        §3:120 accepts the rare race in which the flag flips afterwards: the
        Limiter's Phase A catches it authoritatively. This is an optimisation
        with a permissive posture, never a gate.
        """
        tradable, why = self._tradability.tradable(symbol)
        if tradable:
            return None
        return self._refuse(
            ProposalOutcome.NOT_TRADABLE,
            strategy_id,
            symbol,
            f"§16 U1 fast-drop: {symbol} is not tradable — "
            f"{why or 'the cache gave no reason, which is itself a defect'}",
        )

    # -- step 3: §15 C3 / §7 guards -----------------------------------------

    def _guard(
        self, strategy_id: str, symbol: str, stop_ticks: int, picture: FinancialPicture
    ) -> Proposal | None:
        """§15 C3: zero/invalid stop ⇒ DENY; missing margin ⇒ NOT-TRADABLE.

        The two outcomes are different on purpose (`nixalloc/seam.py:441-457`):
        an invalid stop is a proposal the LIMITER denies and this module does
        not manufacture a size for, while an absent margin figure means the
        symbol cannot be sized at all.
        """
        if not isinstance(stop_ticks, int) or isinstance(stop_ticks, bool):
            return self._deny_no_size(
                strategy_id, symbol, picture, f"stop_ticks {stop_ticks!r} is not an int"
            )
        if stop_ticks <= 0:
            return self._deny_no_size(
                strategy_id,
                symbol,
                picture,
                f"stop_ticks {stop_ticks!r} is not a positive tick DISTANCE (§4)",
            )
        return self._not_tradable_defect(strategy_id, symbol, picture)

    def _not_tradable_defect(
        self, strategy_id: str, symbol: str, picture: FinancialPicture
    ) -> Proposal | None:
        """§7:483's not-tradable guards: no margin, no spec, no cap, no pad."""
        reason = ""
        if symbol not in picture.margin_per_contract:
            reason = (
                f"§7:483: {symbol} is absent from the published margin cache "
                f"(picture version {picture.version})"
            )
        elif symbol not in self._instruments:
            reason = (
                f"§7:483 (same posture): no InstrumentSpec for {symbol}, so "
                "tick_value is unknown and the risk term is undefined"
            )
        elif symbol not in self._knobs.symbol_cap:
            reason = f"§12A:807: no SYMBOL_CAP configured for {symbol}"
        else:
            defect = self._instruments[symbol].defect()
            if defect:
                reason = (
                    f"§7:483 (same posture): InstrumentSpec for {symbol} — {defect}"
                )
        if not reason:
            return None
        return self._refuse(
            ProposalOutcome.NOT_TRADABLE,
            strategy_id,
            symbol,
            reason,
            version=picture.version,
        )

    # -- step 4: the arithmetic ---------------------------------------------

    def _terms(
        self, symbol: str, stop_ticks: int, picture: FinancialPicture
    ) -> _Sized | str:
        """§7:476-478's three terms, in the SELECTED instrument's units.

        Returns the terms, or a reason string when the selected instrument has
        no published margin — a micro leg whose key is missing from the margin
        cache is the same §7:483 not-tradable state as its full.
        """
        knobs = self._knobs
        spec = self._instruments[symbol]
        pad = knobs.slippage_pad_ticks[symbol]
        micro_risk = dollar_risk_per_contract(
            stop_ticks, pad, spec.tick_value / spec.micro_ratio
        )
        ideal_micro_units = (
            0.0 if micro_risk <= 0.0 else knobs.per_trade_risk_usd / micro_risk
        )
        instrument = select_instrument(ideal_micro_units, spec, knobs)
        if instrument.symbol not in picture.margin_per_contract:
            return (
                f"§7:483: selected instrument {instrument.symbol} is absent from "
                f"the published margin cache (picture version {picture.version})"
            )
        per_contract_risk = dollar_risk_per_contract(
            stop_ticks, pad, instrument.tick_value
        )
        headroom = headroom_usd(picture, knobs.deployable_pct)
        live_margin = picture.margin_per_contract[instrument.symbol]
        return _Sized(
            instrument=instrument,
            per_contract_risk=per_contract_risk,
            risk=risk_contracts(knobs.per_trade_risk_usd, per_contract_risk),
            margin=margin_contracts(headroom, live_margin),
            cap=max(0, knobs.symbol_cap[symbol] * instrument.units_per_full),
            headroom=headroom,
            margin_per_contract=live_margin,
        )

    def _size(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        strategy_id: str,
        symbol: str,
        side: Side,
        stop_ticks: int,
        stop_mode: StopMode,
        signal_ts: float,
        picture: FinancialPicture,
    ) -> Proposal:
        """`min(risk, margin, symbol_cap)` → bucket cap → proposal (§7:478)."""
        terms = self._terms(symbol, stop_ticks, picture)
        if isinstance(terms, str):
            return self._refuse(
                ProposalOutcome.NOT_TRADABLE,
                strategy_id,
                symbol,
                terms,
                version=picture.version,
            )
        settled = self._settle(symbol, stop_ticks, picture, terms)
        if settled.contracts <= 0:
            return Proposal(
                outcome=ProposalOutcome.ZERO_AFTER_CLAMP,
                symbol=symbol,
                strategy_id=strategy_id,
                contracts=0,
                rationale=settled.rationale,
                reason=(
                    f"§7:478 min(risk={terms.risk}, margin={terms.margin}, "
                    f"cap={terms.cap}) floored to {settled.contracts} — "
                    f"{settled.rationale.binding.value} bound it"
                ),
            )
        return Proposal(
            outcome=ProposalOutcome.SIZED,
            symbol=symbol,
            strategy_id=strategy_id,
            contracts=settled.contracts,
            rationale=settled.rationale,
            order=ProposedOrder(
                client_order_id=_order_id(strategy_id, symbol, signal_ts, picture),
                strategy_id=strategy_id,
                symbol=terms.instrument.symbol,
                side=side,
                qty=settled.contracts,
                margin_per_contract=terms.margin_per_contract,
                stop_ticks=stop_ticks,
                stop_mode=stop_mode,
                signal_ts=signal_ts,
            ),
            reason=(
                f"§7:478 sized {settled.contracts} {terms.instrument.symbol} against "
                f"picture version {picture.version}; "
                f"{settled.rationale.binding.value} bound it"
            ),
        )

    def _settle(
        self,
        symbol: str,
        stop_ticks: int,
        picture: FinancialPicture,
        terms: _Sized,
    ) -> _Settled:
        """`min(...)`, then the bucket cap, then §16 U5's rationale for both."""
        contracts = max(0, min(terms.risk, terms.margin, terms.cap))
        bucket = BUCKET_OF.get(symbol)
        capped, used, ceiling, note = self._apply_bucket_cap(
            bucket, symbol, stop_ticks, contracts, terms, picture
        )
        binding = (
            BindingConstraint.BUCKET_CAP
            if capped < contracts
            else _binding_of(terms.risk, terms.margin, terms.cap, terms.headroom)
        )
        return _Settled(
            contracts=capped,
            rationale=SizingRationale(
                binding=binding,
                snapshot_version=picture.version,
                risk_contracts=terms.risk,
                margin_contracts=terms.margin,
                symbol_cap=terms.cap,
                headroom=terms.headroom,
                bucket=bucket,
                bucket_used=used,
                bucket_ceiling=ceiling,
                contention=ContentionPolicy.FCFS,
                note=(
                    f"{'micros' if terms.instrument.is_micro else 'fulls'}-only "
                    f"{terms.instrument.symbol}; dollar risk per contract "
                    f"{terms.per_contract_risk:.6g} (stop {stop_ticks} + pad "
                    f"{self._knobs.slippage_pad_ticks[symbol]} ticks); {note}"
                ),
            ),
        )

    def _apply_bucket_cap(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        bucket: CorrelationBucket | None,
        symbol: str,
        stop_ticks: int,
        contracts: int,
        terms: _Sized,
        picture: FinancialPicture,
    ) -> tuple[int, float, float, str]:
        """Delegate to the injected cap, or say loudly that none was applied."""
        if self._bucket_cap is None or bucket is None:
            return (
                contracts,
                0.0,
                0.0,
                "§7 correlation-bucket cap NOT APPLIED: "
                + (
                    "no BucketCapPort is wired (scripts/nixalloc/caps.py)"
                    if self._bucket_cap is None
                    else f"{terms.instrument.symbol} is in no §7 bucket"
                ),
            )
        verdict = self._bucket_cap.admit(
            BucketQuery(
                symbol=symbol,
                bucket=bucket,
                contracts=contracts,
                stop_ticks=stop_ticks,
                micro=terms.instrument.is_micro,
                risk_per_contract=terms.per_contract_risk,
                picture=picture,
            )
        )
        admitted = max(0, min(contracts, verdict.contracts))
        return admitted, verdict.used, verdict.ceiling, verdict.note

    # -- proposal shapes ----------------------------------------------------

    def _refuse(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        outcome: ProposalOutcome,
        strategy_id: str,
        symbol: str,
        reason: str,
        version: int = NO_SNAPSHOT,
    ) -> Proposal:
        """A non-sizing proposal. `contracts` is 0 and `order` is None."""
        return Proposal(
            outcome=outcome,
            symbol=symbol,
            strategy_id=strategy_id,
            contracts=0,
            rationale=_empty_rationale(reason, version),
            reason=reason,
        )

    def _deny_no_size(
        self, strategy_id: str, symbol: str, picture: FinancialPicture, why: str
    ) -> Proposal:
        """§15 C3's deny. The LIMITER denies; this module manufactures no size."""
        return self._refuse(
            ProposalOutcome.NO_SIZE_DENY,
            strategy_id,
            symbol,
            f"§15 C3 / §7:483 invalid stop intent: {why} — the Limiter denies; "
            "the Allocator does not manufacture a size to make it deniable",
            version=picture.version,
        )


def _order_id(
    strategy_id: str, symbol: str, signal_ts: float, picture: FinancialPicture
) -> str:
    """A deterministic client order id, derived from the GO and the snapshot.

    Deterministic rather than random: §9's log is event-sourced and a replay
    that produced different ids would not reconcile. Uniqueness holds because
    §3's one-in-flight-per-strategy lock makes two GOs from one strategy for
    one symbol at one `signal_ts` against one picture version impossible.
    """
    return f"{strategy_id}:{symbol}:{signal_ts!r}:v{picture.version}"


def _port_check(allocator: SizingAllocator) -> AllocatorPort:
    """Structural assertion, checked by mypy and by nothing else.

    If `SizingAllocator.propose` ever drifts from the frozen `AllocatorPort`
    signature, this function stops type-checking. `AllocatorPort` is not
    `runtime_checkable` (`nixalloc/seam.py:489`), so there is no isinstance
    test to write and pretending otherwise would be a claim with no mechanism
    behind it — `scripts/tests/test_allocator_sizing.py` asserts the verb set
    at run time instead.
    """
    return allocator
