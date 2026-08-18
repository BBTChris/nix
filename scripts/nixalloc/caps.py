"""§7's correlation-bucket cap, BY FORMULA — the SUM inside one bucket, and nothing else.

ARC 031 Stage 1 / sub-agent C. The frozen risk spec states the rule at
`nics_risk_subsystem_spec_v1.3.md` §7:497-515 and states the objective it has to
satisfy at §13 V35:949 — *"prove within-bucket dollar risk is SUMMED correctly
(micros at 1/10), a proposal that would breach `bucket_cap_pct × balance` is
sized down then denied, and positions in different buckets do NOT constrain each
other through this rule"*. Three clauses, and this module implements exactly
those three.

THE FORMULA, transcribed from §7:511-515 and not paraphrased::

    Σ dollar_risk(open + pending in bucket B) + proposed_dollar_risk
        ≤ bucket_cap_pct(B) × balance

with the exposure unit fixed at §7:500-504::

    dollar_risk = (stop_ticks + slippage_pad) × tick_value × contracts

and micros carrying 1/10 weight.

FOUR THINGS THIS MODULE IS DELIBERATELY CAREFUL ABOUT
-----------------------------------------------------

1. **It is a SUM over the bucket, never a comparison against the largest
   member.** A cap driven with ONE position per bucket cannot tell the two
   apart — `sum([x]) == max([x])` — so the difference only becomes observable
   at two same-bucket positions. `bucket_dollar_risk` therefore reports how
   many exposures it summed (`contributors`), and `checks/check_allocator_caps.py`
   drives TWO same-bucket positions and asserts against the SUM while asserting
   the `max()`-shaped answer would have differed. The falsifier is in the gate,
   not only in the prose.

2. **SAME-BUCKET ONLY (§7:505-510).** Everything outside bucket B is filtered
   out before the sum, so a large energy position cannot shrink an equities
   proposal through this rule. §7:508-510 is explicit that cross-bucket total
   exposure is bounded by the portfolio-wide layers instead (70% deployable,
   aggregate margin cap, net-liq survival floor, §6.5) — those are the
   Limiter's and are NOT here.

3. **Size-down TOWARD the ceiling, then deny at zero (§7:514).** The admitted
   size is `floor((ceiling − used) / per_contract_risk)` clamped into
   `[0, proposed]`. It is not "deny on breach": a proposal for 5 that only fits
   2 is admitted at 2, and only a headroom that will not carry a single
   contract denies. The two are different behaviours and both are driven.

4. **`bucket_cap_pct` IS NOT DECLARED HERE, AND NOT IN THIS MODULE'S OWN CONFIG
   FILE EITHER.** It is a §12A knob (§12A:816 `BUCKET_CAP_PCT`) and it already
   has its ONE physical home in `risks/allocator.config.json`. MEASURED, not
   reasoned: a second copy under `risks/allocator_caps.config.json` makes
   `checks/check_risks_data_only.py` ARM 2 red with *"is a SECOND physical home
   for §12A knob `BUCKET_CAP_PCT`"*. So this loader reads the ceiling percentage
   from the module config the validated loader already owns, and
   `risks/allocator_caps.config.json` holds only what has no home at all — the
   per-symbol tick values and the micro weight, both of which say outright that
   they are not §12A knobs.

WHAT IS NOT HERE, stated rather than implied
--------------------------------------------
* The risk and margin terms of §7:476-478's `min(...)` — sub-agent B owns those
  (`scripts/nixalloc/sizing.py`). This module owns ONE term of that min, the
  bucket cap, and it is deliberately callable on its own.
* The mirror's transport and staleness machinery (§12.7) — sub-agent A.
* Contention (§6.6) — `scripts/nixalloc/contention.py`, next door.
* Any decision about WHO wins a contention race. §2:40 makes the Allocator
  permissive; §6.6:459-460 gives arbitration to the Limiter.

`debug.md` §7.12 — THE STANDING QUESTION for `admit`: *what would have to be
true for this to return an answer while measuring nothing?*
  1. **The exposure list is empty**, so the sum is 0 and the cap never binds.
     GUARDED: `CapDecision.contributors` reports the count that was actually
     summed, so a caller — and the gate — can tell "nothing in the bucket" from
     "the filter dropped everything".
  2. **The symbol has no bucket**, so the filter matches nothing and the
     proposal sails through. CLOSED: `BucketCapError`, never a silent admit.
     §7:483 makes an unresolvable symbol *not-tradable*, and the Allocator maps
     this exception onto `ProposalOutcome.NOT_TRADABLE`.
  3. **`per_contract_dollar_risk` is zero**, so `headroom / per` is a division
     by zero or an unbounded admit. CLOSED: `BucketCapError` — §7:483 makes an
     invalid/zero stop intent a DENY, and the Allocator never invents a size.
  4. **The ceiling is unbounded** because a cap percentage is missing. CLOSED:
     `_require` raises on absence; there is no defaulted read in this module.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from nixalloc.seam import BUCKET_OF, BindingConstraint, CorrelationBucket

__all__ = [
    "BOOT_RULE_IDS",
    "CAPS_CONFIG",
    "BucketCapError",
    "CapConfig",
    "CapDecision",
    "Exposure",
    "admit",
    "bucket_dollar_risk",
    "bucket_for",
    "dollar_risk",
    "load_cap_config",
    "per_contract_dollar_risk",
]

#: This module's own data-role file. Holds ONLY knobs with no other home; see
#: point 4 of the module docstring for why `bucket_cap_pct` is not among them.
CAPS_CONFIG = "risks/allocator_caps.config.json"

#: The module whose §12A knobs this one reads rather than restates. Named as a
#: string so the pointer is visible to a reader and to a gate.
ALLOCATOR_MODULE = "allocator"

#: The boot rules `risks/allocator_caps.config.json` declares and this module
#: implements. `checks/check_risks_data_only.py` ARM 4 reads this tuple out of
#: this file's AST and requires the correspondence — a declared rule nothing
#: runs is documentation wearing a rule's clothes.
BOOT_RULE_IDS: tuple[str, ...] = (
    "caps.tick_values_are_positive",
    "caps.micro_weight_is_a_fraction",
    "caps.tick_values_cover_every_bucketed_symbol",
)

#: Keys that document rather than configure. Filtered by prefix test, never read
#: by subscript: a loader that consumed one would make rewording a comment a
#: behaviour change.
_DOC_PREFIX = "_"


class BucketCapError(Exception):
    """A cap that cannot be computed. NEVER degraded into an admit.

    CLAUDE.md directive 4 (fail closed and loud) and §7:483's guard posture: an
    unresolvable symbol is *not-tradable* and an invalid/zero stop intent is a
    DENY. Both are conditions under which a number produced anyway would be an
    invented size, so this module produces an exception instead and the
    Allocator maps it onto the matching `ProposalOutcome`.
    """


@dataclass(frozen=True)
class CapConfig:
    """Every number §7's cap formula needs, and where each one comes from.

    Frozen, because a sizing pass that could edit its own ceiling mid-pass is
    the §12.11 hazard ("two decisions inside one open trade read different
    tunables") reproduced inside a single decision.
    """

    #: §12A:816 `BUCKET_CAP_PCT[bucket]`, read from `risks/allocator.config.json`
    #: — its ONE physical home. Keyed by `CorrelationBucket.value`.
    bucket_cap_pct: Mapping[str, float]
    #: §12A:806 `SLIPPAGE_PAD_TICKS`, same single home. Per symbol.
    slippage_pad_ticks: Mapping[str, float]
    #: Dollars per tick per FULL contract. Not a §12A knob — see the config file.
    tick_value_usd: Mapping[str, float]
    #: §7:502 — micros count at 1/10 weight.
    micro_weight: float


@dataclass(frozen=True)
class Exposure:
    """One open-or-pending position's contribution to a bucket (§7:511).

    `stop_ticks` is the tick DISTANCE the position was sized against (§2:38's
    GO shape), not a price. `micro` selects §7:502's 1/10 weight.
    """

    symbol: str
    contracts: int
    stop_ticks: int
    micro: bool = False


# R0902 refused with a reason: these nine fields are exactly the terms §16 U5
# requires to ride the order message ("binding constraint + input snapshot") for
# THIS constraint — the bucket, the proposed and admitted sizes, the summed
# used/ceiling pair, the per-contract unit that converts between them, the
# contributor count that makes the SUM falsifiable, the binding constraint and
# the reason. Dropping one to reach a threshold of seven would either lose an
# audit term or nest it, and a nested term is one the Limiter's event log has to
# read SEPARATELY — the cross-read §3's atomicity rule exists to forbid,
# reproduced in the audit trail. Same reasoning `nixalloc/seam.py` records for
# `SizingRationale`'s own field count.
# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class CapDecision:
    """What the cap did, and every term it did it with (§16 U5).

    §16 U5 requires the sizing rationale to ride the order message so the
    Limiter's event log can audit sizing without breaking sole-writer. "Two
    contracts" is not auditable; "two contracts, because the equities bucket
    held $850 of $1000 and one contract costs $75" is.
    """

    bucket: CorrelationBucket
    proposed_contracts: int
    admitted_contracts: int
    #: Σ dollar_risk over the SAME bucket only. The summation §13 V35:949 names.
    used_dollar_risk: float
    #: `bucket_cap_pct(B) × balance` (§7:512).
    ceiling_dollar_risk: float
    per_contract_dollar_risk: float
    #: How many exposures were actually summed. A ZERO here distinguishes "the
    #: bucket is empty" from "the filter dropped everything", which is §7.12/1.
    contributors: int
    binding: BindingConstraint
    reason: str

    @property
    def denied(self) -> bool:
        """True when not one contract fits under the ceiling (§7:514)."""
        return self.admitted_contracts == 0

    @property
    def sized_down(self) -> bool:
        """True when the cap shrank the proposal without denying it (§7:514)."""
        return 0 < self.admitted_contracts < self.proposed_contracts


def bucket_for(symbol: str) -> CorrelationBucket | None:
    """§7:498's static membership, read from the seam. Never re-spelled here.

    `None` is a real answer and the caller must handle it: a symbol §7 does not
    place in a bucket has no within-bucket concentration to measure, and
    guessing one would put a symbol scope decision in a cap.
    """
    return BUCKET_OF.get(symbol)


def per_contract_dollar_risk(
    symbol: str, stop_ticks: int, config: CapConfig, *, micro: bool = False
) -> float:
    """§7:500-504's exposure unit, for ONE contract.

    `(stop_ticks + slippage_pad) × tick_value`, times §7:502's 1/10 for a
    micro. Applying the weight to the full contract's tick value is the same
    arithmetic as using the micro instrument's own tick value — §7:503 says the
    micro's dollar risk "falls out naturally" — and
    `scripts/tests/test_allocator_caps.py` asserts the two spellings agree
    rather than leaving the equivalence to the reader.
    """
    pad = _require(config.slippage_pad_ticks, symbol, "slippage_pad_ticks")
    tick_value = _require(config.tick_value_usd, symbol, "tick_value_usd")
    weight = config.micro_weight if micro else 1.0
    return (float(stop_ticks) + pad) * tick_value * weight


def dollar_risk(exposure: Exposure, config: CapConfig) -> float:
    """§7:501's `(stop_ticks + slippage_pad) × tick_value × contracts`."""
    per = per_contract_dollar_risk(
        exposure.symbol, exposure.stop_ticks, config, micro=exposure.micro
    )
    return per * float(exposure.contracts)


def bucket_dollar_risk(
    exposures: Iterable[Exposure], bucket: CorrelationBucket, config: CapConfig
) -> tuple[float, int]:
    """`(Σ dollar_risk, contributors)` over bucket B ONLY (§7:505-510, §13 V35).

    The SUM is the whole point and the count is what makes it checkable: a
    caller holding only the total cannot tell a sum of three from the largest
    of three, and with one position per bucket the two are equal. Returning the
    contributor count lets an instrument assert it summed more than one.
    """
    total = 0.0
    contributors = 0
    for exposure in exposures:
        if bucket_for(exposure.symbol) is not bucket:
            continue
        total += dollar_risk(exposure, config)
        contributors += 1
    return total, contributors


# R0913/R0917 refused with a reason: these seven are the §7:511 inequality's own
# terms — the proposal (symbol, contracts, stop distance, micro), the book it is
# measured against, the balance the ceiling is a percentage OF, and the config
# that carries the percentage. Collapsing them into a `Proposal` struct is a real
# option and a real decision; it belongs with the module that OWNS the proposal
# shape (`nixalloc/seam.py`'s `Proposal`, built by the sizing pathway), and
# minting a second one here would put a wire type in a rule.
# pylint: disable=too-many-arguments,too-many-positional-arguments
def admit(
    symbol: str,
    contracts: int,
    stop_ticks: int,
    exposures: Sequence[Exposure],
    balance: float,
    config: CapConfig,
    *,
    micro: bool = False,
) -> CapDecision:
    """Apply §7:511-515's cap to one proposal. Size down, then deny at zero.

    Raises `BucketCapError` for a symbol §7 gives no bucket, for a non-positive
    stop distance, and for a non-positive proposed size — all three are §7:483
    guards under which producing a number would be inventing a size.
    """
    bucket = bucket_for(symbol)
    if bucket is None:
        raise BucketCapError(
            f"{symbol}: §7:498 places it in no correlation bucket, so its "
            "within-bucket concentration cannot be measured — §7:483 makes an "
            "unresolvable symbol not-tradable, never silently admitted"
        )
    if contracts <= 0:
        raise BucketCapError(
            f"{symbol}: proposed {contracts} contract(s) — a cap on a "
            "non-positive proposal would report a ceiling nobody asked about"
        )
    if stop_ticks <= 0:
        raise BucketCapError(
            f"{symbol}: stop distance {stop_ticks} ticks — §7:483 makes an "
            "invalid/zero stop intent a DENY, and the Allocator never invents "
            "a size to make one deniable"
        )
    per = per_contract_dollar_risk(symbol, stop_ticks, config, micro=micro)
    if per <= 0:
        raise BucketCapError(
            f"{symbol}: per-contract dollar risk computed to {per}, so every "
            "size would fit under every ceiling — a cap that cannot bind is "
            "not a cap"
        )
    ceiling = _require(config.bucket_cap_pct, bucket.value, "bucket_cap_pct") * float(
        balance
    )
    used, contributors = bucket_dollar_risk(exposures, bucket, config)
    return _decide(
        bucket=bucket,
        symbol=symbol,
        contracts=contracts,
        per=per,
        used=used,
        ceiling=ceiling,
        contributors=contributors,
    )


# R0913/R0917 refused with a reason: these seven are exactly the terms
# `CapDecision` has to carry for §16 U5's audit trail, and collapsing them into
# a struct here would mint a second value type that exists only to satisfy an
# argument-count heuristic.
def _decide(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    bucket: CorrelationBucket,
    symbol: str,
    contracts: int,
    per: float,
    used: float,
    ceiling: float,
    contributors: int,
) -> CapDecision:
    """The arithmetic half of `admit`, separated from its guards.

    Split out so the guards read as guards and this reads as §7:511-515's one
    inequality, rearranged for the unknown::

        used + admitted × per ≤ ceiling   ⟺   admitted ≤ (ceiling − used) / per
    """
    headroom = ceiling - used
    fits = math.floor(headroom / per) if headroom > 0 else 0
    admitted = max(0, min(contracts, fits))
    binding = (
        BindingConstraint.BUCKET_CAP if admitted < contracts else BindingConstraint.NONE
    )
    return CapDecision(
        bucket=bucket,
        proposed_contracts=contracts,
        admitted_contracts=admitted,
        used_dollar_risk=used,
        ceiling_dollar_risk=ceiling,
        per_contract_dollar_risk=per,
        contributors=contributors,
        binding=binding,
        reason=_reason(
            symbol, bucket, contracts, admitted, used, ceiling, per, contributors
        ),
    )


# R0913/R0917 refused for the same reason as `_decide`: the message must NAME
# every term, because §18 requires the reason and not the number.
def _reason(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    symbol: str,
    bucket: CorrelationBucket,
    contracts: int,
    admitted: int,
    used: float,
    ceiling: float,
    per: float,
    contributors: int,
) -> str:
    """Say WHY, with every term named (§18). Never just the number."""
    shape = (
        "admitted whole"
        if admitted == contracts
        else ("DENIED at zero" if admitted == 0 else "sized down toward the ceiling")
    )
    return (
        f"{symbol} in bucket {bucket.value}: {shape} — proposed {contracts}, "
        f"admitted {admitted}. §7:511 sum over {contributors} same-bucket "
        f"exposure(s) = {used:.4f}, ceiling = {ceiling:.4f}, per-contract "
        f"dollar risk = {per:.4f}, headroom = {ceiling - used:.4f}"
    )


def _require(table: Mapping[str, float], key: str, what: str) -> float:
    """Read a configured number by NAME and raise on absence. No defaults.

    There is deliberately no `.get(key, default)` anywhere in this module: a
    silently-substituted ceiling is a cap that does not bind, which is worse
    than an unreadable config (doctrine C.7).
    """
    if key not in table:
        raise BucketCapError(
            f"{what}: no entry for {key!r} — a missing cap term is never "
            "defaulted, because a defaulted ceiling is a ceiling nobody set"
        )
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BucketCapError(f"{what}[{key}] is {value!r}, expected a number")
    return float(value)


# ---------------------------------------------------------------------------
# The loader. §12.11 — boot-loaded, restart-only. There is no second entry
# point that re-reads a file it has already read.
# ---------------------------------------------------------------------------


def _values(path: Path) -> dict[str, object]:
    """A config file's VALUE keys. Documentation keys are filtered by prefix."""
    if not path.is_file():
        raise BucketCapError(f"{path} is absent — never a set of defaults")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BucketCapError(f"{path}: unreadable JSON — {exc}") from exc
    if not isinstance(raw, dict):
        raise BucketCapError(
            f"{path}: top level is {type(raw).__name__}, expected an object"
        )
    return {k: v for k, v in raw.items() if not k.startswith(_DOC_PREFIX)}


def _numeric_map(
    values: Mapping[str, object], key: str, where: str
) -> dict[str, float]:
    """One knob that must be a flat map of numbers, read by name."""
    if key not in values:
        raise BucketCapError(f"{where}: required key {key!r} is absent")
    table = values[key]
    if not isinstance(table, dict):
        raise BucketCapError(
            f"{where}:{key} is {type(table).__name__}, expected an object"
        )
    typed: Mapping[str, float] = table
    return {name: _require(typed, name, f"{where}:{key}") for name in table}


def _scalar(values: Mapping[str, object], key: str, where: str) -> float:
    """One knob that must be a bare number, read by name. No defaulted read."""
    if key not in values:
        raise BucketCapError(f"{where}: required key {key!r} is absent")
    typed: Mapping[str, float] = values  # type: ignore[assignment]
    return _require(typed, key, where)


def _validate(config: CapConfig, where: str) -> None:
    """Run every rule `BOOT_RULE_IDS` names. Raises on the first violation.

    §7.12 for this function: a validator that evaluated zero rules must never
    return as if it had, so the rule count is asserted against `BOOT_RULE_IDS`
    before any verdict is reached.
    """
    problems: list[str] = []
    evaluated = 0
    for name, value in sorted(
        config.tick_value_usd.items()
    ):  # tick_values_are_positive
        if value <= 0:
            problems.append(f"{where}:tick_value_usd[{name}]={value} is not > 0")
    evaluated += 1
    if not 0 < config.micro_weight <= 1:  # micro_weight_is_a_fraction
        problems.append(
            f"{where}:micro_weight={config.micro_weight} is outside (0, 1] — "
            "§7:502 makes a micro a FRACTION of a full contract's dollar risk"
        )
    evaluated += 1
    missing = sorted(set(BUCKET_OF) - set(config.tick_value_usd))
    if missing:  # tick_values_cover_every_bucketed_symbol
        problems.append(
            f"{where}:tick_value_usd has no entry for {missing} — §7:498 places "
            "those symbols in a bucket, so a cap over them would be computed "
            "against a tick value that does not exist"
        )
    evaluated += 1
    if evaluated != len(BOOT_RULE_IDS):
        raise BucketCapError(
            f"{where}: evaluated {evaluated} rule(s) against "
            f"{len(BOOT_RULE_IDS)} declared id(s) — a validator that checked "
            "fewer rules than it declares must never return as if it had"
        )
    if problems:
        raise BucketCapError(f"{where}: " + "; ".join(problems))


def load_cap_config(root: Path) -> CapConfig:
    """Build the cap's config from the ONE home each knob already has.

    `bucket_cap_pct` and `slippage_pad_ticks` come from
    `risks/allocator.config.json` through `risk_config`, which is the loader
    that VALIDATES them; only the two knobs with no home anywhere come from
    `risks/allocator_caps.config.json`. Called once, at boot — there is no
    reload verb here, and §12.11 makes a config change a supervised restart.
    """
    import risk_config  # pylint: disable=import-outside-toplevel

    try:
        allocator = risk_config.load_risk_configs(root).modules[ALLOCATOR_MODULE]
    except risk_config.RiskConfigError as exc:
        raise BucketCapError(f"{ALLOCATOR_MODULE} config: {exc}") from exc
    except KeyError as exc:
        raise BucketCapError(
            f"risk_config does not own module {ALLOCATOR_MODULE!r}, so the "
            "§12A cap knobs have no validated source"
        ) from exc
    shared = dict(allocator.values)
    own = _values(root / CAPS_CONFIG)
    config = CapConfig(
        bucket_cap_pct=_numeric_map(shared, "bucket_cap_pct", str(allocator.source)),
        slippage_pad_ticks=_numeric_map(
            shared, "slippage_pad_ticks", str(allocator.source)
        ),
        tick_value_usd=_numeric_map(own, "tick_value_usd", CAPS_CONFIG),
        micro_weight=_scalar(own, "micro_weight", CAPS_CONFIG),
    )
    _validate(config, CAPS_CONFIG)
    return config
