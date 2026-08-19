"""risk_config.py — the boot-time loader and cross-knob validator for `risks/`.

ARC 028 sub-agent D. `risks/` holds the §12A knobs as DATA; this module is the
only place those numbers become objects, and it is where the cross-knob boot
validation §12A:801-802 requires actually RUNS. The authority split, stated once
and not repeated per-file:

  * `docs/nics_risk_subsystem_spec_v1.3.md` §12A is the SEMANTIC authority —
    names, defaults, meanings, and the boot validation that must reject an
    invalid set "before any strategy registers".
  * `risks/<module>.config.json` is the PHYSICAL layout — per-module JSON,
    config-role, numbers only.
  * This module is the LOADER and the RULE HOST. **Every behavioural decision
    lives here and none of it lives in `risks/`** — that is the whole point, and
    `checks/check_risks_data_only.py` is the standing instrument over it.

WHY THE RULES ARE CODE AND THE JSON ONLY NAMES THEM. A `_boot_validation` block
that is a list of prose nothing executes is documentation wearing a rule's
clothes. A `_boot_validation` block that is a list of *expressions* is worse: it
is an eval'able rule language smuggled into a data file, which makes `risks/` a
second behavioural authority that can disagree with the spec silently — the
exact failure `docs/directory_structure.md` bans for this directory. So the
predicate is a Python callable here, the JSON carries only its ID and its
provenance, and the gate proves the two sets correspond in BOTH directions.

LIFECYCLE — §12.11, and it is enforced rather than asserted
-----------------------------------------------------------
*"Config lifecycle (locked): boot-loaded, restart-only. No hot-reload — a
mid-session change would let two decisions inside one open trade read different
tunables."* Three mechanisms, none of them prose:

 1. **There is no reload verb.** No function here re-reads a file it has already
    read, nothing watches a path, nothing imports `signal`, `threading`,
    `asyncio` or an inotify binding, and nothing reads an mtime. The gate reads
    this module's AST and fails on any of those.
 2. **The product is IMMUTABLE.** `RiskConfigSet` and `ModuleConfig` are frozen
    dataclasses over `MappingProxyType` views, so a booted process physically
    cannot have its tunables changed underneath it. Two decisions inside one open
    trade read the same numbers because there is no writer.
 3. **The set carries a VERSION.** `config_version` is a digest over the VALUE
    keys of every module — documentation keys excluded, because a reworded
    comment is not a different configuration. §12.11 requires that version be
    stamped into the Plane-1 boot event, and `scripts/nixrisk/seam.py`'s
    `EventKind.BOOT` row is where it goes.

`debug.md` §7.12 — THE STANDING QUESTION for `validate_all`: *what would have to
be true for this to pass while checking nothing?*
  1. **No config files found**, so the rule loop iterates an empty set. GUARDED:
     `load_risk_configs` raises when a declared module file is absent, and the
     shipped module list is derived from the directory rather than defaulted.
  2. **Every rule declares modules that are not present**, so no rule ever
     evaluates. GUARDED: `validate_all` counts the rule EVALUATIONS it performed
     and raises when that count is zero.
  3. **The rules are never invoked** because a caller builds the object
     directly. GUARDED: `RiskConfigSet.__post_init__` runs `validate_all`, so an
     invalid set cannot be constructed.
  4. **A knob is absent and the rule reads it with a default.** GUARDED: every
     read goes through `_require`, which raises on absence. There is no
     `.get(name, default)` in this module.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType

#: Derived from this module's own location, never typed as an absolute path
#: (`debug.md` §7.4: the tree moves — a worktree, another operator's home — and a
#: literal root rots silently). scripts/ -> ~/nix
_REPO_ROOT = Path(__file__).resolve().parents[1]
RISKS_DIR = "risks"

#: The suffix every per-module config carries. A file in `risks/` that is not one
#: of these is not a config, and the gate treats it as a defect rather than
#: skipping it quietly.
CONFIG_SUFFIX = ".config.json"

#: Keys the loader NEVER reads. They are the file's own account of where each
#: value came from, and a loader that consumed them would make the documentation
#: load-bearing — at which point rewording a comment could change behaviour.
DOC_KEY_PREFIX = "_"

#: Modules this loader owns. `broker_order` is deliberately NOT here: it has its
#: own loader (`scripts/broker/broker_order_config.py`, §2A vendor library) and
#: giving it two would be the second-authority shape one directory over.
OWNED_MODULES: tuple[str, ...] = (
    "allocator",
    "limiter",
    "scoring",
    "sentinel",
    "staleness",
    "supervision",
)


class RiskConfigError(Exception):
    """A config that cannot be loaded or cannot be validated.

    Never degraded to defaults (CLAUDE.md directive 4, doctrine C.7). A config
    this module cannot fully validate is a config it must not run on: every knob
    in `risks/` bounds either a gate, a blackout or a protective exit, and a
    silently-substituted default is worse than an unreadable file.
    """


# ---------------------------------------------------------------------------
# The loaded shape — immutable by construction (§12.11 mechanism 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleConfig:
    """One module's VALUE keys. Frozen, and its mapping is a read-only view.

    THE `_`-PREFIXED KEYS ARE NOT HERE AND THAT IS DELIBERATE. `_meta`,
    `_derivations` and `_boot_validation` are the file's own account of where its
    numbers came from. A loader that consumed any of them would make prose
    load-bearing — rewording a comment would become a behaviour change — so this
    loader reads NUMBERS and nothing else, and
    `checks/check_risks_data_only.py` fails if it ever starts reading more. The
    correspondence between a file's declared rule ids and the rules implemented
    below is therefore the GATE's property, not this module's.
    """

    module: str
    source: Path
    values: Mapping[str, object]


def _leaves(value: object, path: str) -> Iterable[tuple[str, object]]:
    """Every scalar in a value tree, with a dotted path naming where it sits."""
    if isinstance(value, Mapping):
        for key in sorted(value):
            yield from _leaves(value[key], f"{path}.{key}")
        return
    yield path, value


# ---------------------------------------------------------------------------
# The rules. CODE, with an ID the JSON names and this module implements.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootRule:
    """One cross-knob boot rule.

    `modules` is the set this rule applies to, and it is what makes the
    correspondence with each JSON's `_boot_validation` list checkable in BOTH
    directions: a rule that applies to a module the file does not declare is as
    much a defect as a declared id nothing implements.
    """

    id: str
    modules: tuple[str, ...]
    spec: str
    check: Callable[[Mapping[str, ModuleConfig]], list[str]]


def _require(cfg: ModuleConfig, key: str) -> object:
    """Read a key by NAME and raise if absent. No defaulted read exists here."""
    if key not in cfg.values:
        raise RiskConfigError(f"{cfg.source}: required key {key!r} is absent")
    return cfg.values[key]


def _number(cfg: ModuleConfig, key: str) -> float:
    """A knob that must be numeric, read by name."""
    value = _require(cfg, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RiskConfigError(
            f"{cfg.source}: {key}={value!r} is {type(value).__name__}, expected a number"
        )
    return float(value)


def knob(cfg: ModuleConfig, key: str) -> float:
    """`_number` under a PUBLIC name, for readers outside this module.

    ARC 034 / sub-agent B. `scripts/nixsentinel/config.py` is a legitimate second
    READER of `risks/` — never a second authority; it calls the rule callables
    below rather than restating them — and it needs the same by-name, no-default,
    type-checked read every rule here uses. Giving it a public name is better
    than either reaching into a `_`-private from another package or growing a
    parallel accessor that could accept a default and quietly diverge.
    """
    return _number(cfg, key)


def _mapping(cfg: ModuleConfig, key: str) -> Mapping[str, object]:
    """A knob that must be a map of numbers, read by name."""
    value = _require(cfg, key)
    if not isinstance(value, Mapping):
        raise RiskConfigError(
            f"{cfg.source}: {key} is {type(value).__name__}, expected an object"
        )
    return value


#: The cooldown ladder is the one place a ZERO is legal, because §4:301 says
#: "Discretionary exit -> none" and none is a value. Named here so the positivity
#: rule's carve-out is visible rather than buried in a condition.
_COOLDOWN_KEY = "cooldown_min_time_s"
_COOLDOWN_ORDER = ("discretionary", "stop", "uncertainty", "margin_session")


def _positive_scalars(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """Every scalar outside the cooldown ladder is > 0 (§12A:801-802)."""
    problems: list[str] = []
    for module, cfg in sorted(loaded.items()):
        for key, value in sorted(cfg.values.items()):
            if key == _COOLDOWN_KEY:
                continue
            for where, leaf in _leaves(value, key):
                if isinstance(leaf, bool) or not isinstance(leaf, (int, float)):
                    problems.append(
                        f"{module}.{where}={leaf!r} is {type(leaf).__name__}, "
                        "expected a number"
                    )
                elif not math.isfinite(leaf):
                    # ARC 038 / sub-agent E — FE9. `NaN` passes EVERY ordering
                    # comparison, so `leaf <= 0` admitted it and only the
                    # `_pct_range` rule — which inspects keys ending `_pct` alone
                    # — happened to catch the fraction knobs. Measured: with this
                    # branch absent, `limiter.netliq_safety_pad = nan`,
                    # `= inf` and `limiter.ledger_drift_tolerance_usd = nan` were
                    # all ACCEPTED AT BOOT, and a NaN survival pad turns §6.5's
                    # floor off at every size. A finiteness test cannot be
                    # written as an inequality; it has to be its own branch.
                    problems.append(
                        f"{module}.{where}={leaf!r} is not FINITE — a non-finite "
                        "knob passes every ordering comparison a validator can "
                        "make, so it reaches the rule that reads it and disables "
                        "whatever comparison that rule performs (§12A:801-802)"
                    )
                elif leaf <= 0:
                    problems.append(
                        f"{module}.{where}={leaf!r} — every scalar knob outside "
                        "the cooldown ladder must be > 0"
                    )
    return problems


def _pct_range(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """Every `_pct` knob is a fraction of balance, so it lies in (0, 1]."""
    problems: list[str] = []
    for module, cfg in sorted(loaded.items()):
        for key, value in sorted(cfg.values.items()):
            if not key.endswith("_pct"):
                continue
            for where, leaf in _leaves(value, key):
                if not isinstance(leaf, (int, float)) or isinstance(leaf, bool):
                    problems.append(f"{module}.{where}={leaf!r} is not a number")
                elif not 0 < float(leaf) <= 1:
                    problems.append(
                        f"{module}.{where}={leaf!r} — a fraction of balance must "
                        "lie in (0, 1]"
                    )
    return problems


def _margin_cap_within_deployable(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """The aggregate margin cap may not exceed the deployable envelope."""
    cfg = loaded["limiter"]
    cap = _number(cfg, "agg_margin_cap_pct")
    deployable = _number(cfg, "deployable_pct")
    if cap > deployable:
        return [
            (
                f"limiter.agg_margin_cap_pct={cap} exceeds "
                f"limiter.deployable_pct={deployable} — the hard margin cap "
                "would admit commitments the 30% buffer was reserved to "
                "protect, and the two are one coupled system"
            )
        ]
    return []


#: The label the ordering rule reports the GLOBAL default pair under. Not a
#: symbol, and shaped so it can never collide with one: §12A:819-820 give a
#: global default with a per-symbol override, so the pair that governs every
#: unlisted symbol has to be judged too, and it needs a name in the message.
_GLOBAL_SET = "<global default>"

#: The two per-symbol override maps §12A:819-820 authorise ("per-symbol
#: override", stated for BOTH knobs). Keys are symbols; values are that symbol's
#: effective minutes. A symbol absent from a map inherits the global default.
_LEAD_BY_SYMBOL = "session_flatten_lead_min_by_symbol"
_BLACKOUT_BY_SYMBOL = "eod_blackout_min_by_symbol"


def _override(cfg: ModuleConfig, key: str) -> Mapping[str, object]:
    """A per-symbol override map, or an empty one when the knob is absent.

    The ONLY defaulted read in this module, and the default is the EMPTY set
    rather than a value. That distinction is what keeps `_require`'s no-defaults
    rule intact: an absent override map means "no symbol overrides anything", so
    every symbol falls through to the global pair, which IS read by `_number`
    and does raise when absent. A defaulted NUMBER would let a missing knob
    validate; a defaulted empty MAP cannot hide one.
    """
    if key not in cfg.values:
        return {}
    return _mapping(cfg, key)


def _symbol_minutes(
    cfg: ModuleConfig, overrides: Mapping[str, object], symbol: str, default: float
) -> tuple[float | None, str | None]:
    """One symbol's effective minutes, or `(None, problem)` if unusable."""
    if symbol not in overrides:
        return default, None
    value = overrides[symbol]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, (
            f"{cfg.source.name}: per-symbol override for {symbol!r} is "
            f"{value!r} ({type(value).__name__}), expected a number"
        )
    return float(value), None


def _session_pairs(
    cfg: ModuleConfig,
) -> list[tuple[str, float | None, float | None, list[str]]]:
    """THE ONE RESOLUTION of §6.1b's per-symbol pairs. Validator AND consumer.

    Returns `(symbol, lead_min, eod_blackout_min, defects)` for the global
    default and for every symbol named in either override map.

    **It is one function because a second resolution is a second authority**
    (directive 3). The rule below judges these pairs; `session_flatten_lead_min`
    below hands the SAME pairs to `nixrisk.session.SessionFlattener`. If the
    scheduler re-derived the effective lead from the raw knobs, a divergence
    between the two would mean the deadline that fires is not the one the boot
    validation approved — and nothing would disagree out loud.
    """
    lead_default = _number(cfg, "session_flatten_lead_min")
    blackout_default = _number(cfg, "eod_blackout_min")
    lead_overrides = _override(cfg, _LEAD_BY_SYMBOL)
    blackout_overrides = _override(cfg, _BLACKOUT_BY_SYMBOL)
    rows: list[tuple[str, float | None, float | None, list[str]]] = []
    for symbol in [_GLOBAL_SET, *sorted(set(lead_overrides) | set(blackout_overrides))]:
        lead, lead_problem = _symbol_minutes(cfg, lead_overrides, symbol, lead_default)
        blackout, blackout_problem = _symbol_minutes(
            cfg, blackout_overrides, symbol, blackout_default
        )
        defects = [p for p in (lead_problem, blackout_problem) if p is not None]
        rows.append((symbol, lead, blackout, defects))
    return rows


def session_flatten_lead_min(config: RiskConfigSet) -> Mapping[str, float]:
    """§6.1b:340's per-symbol lead, for every symbol the config names.

    The map `nixrisk.session.SessionFlattener` takes as `lead_min`. Read off the
    SAME `_session_pairs` the boot rule judged, so the deadline that fires is
    the one boot validation approved (see that helper's docstring).

    The global-default row is deliberately NOT in the result: it is not a symbol,
    and a scheduler handed `{"<global default>": 10}` would happily manage an
    instrument by that name. A symbol with no override has no row here, and
    `SessionFlattener` refuses at construction rather than defaulting — which is
    the loud direction (directive 4).
    """
    pairs = _session_pairs(config.modules["limiter"])
    return MappingProxyType(
        {
            symbol: lead
            for symbol, lead, _blackout, defects in pairs
            if symbol != _GLOBAL_SET and lead is not None and not defects
        }
    )


def _session_flatten_before_eod_blackout(
    loaded: Mapping[str, ModuleConfig],
) -> list[str]:
    """The §6.1b ordering invariant — the one §12A:802 names as boot-validated.

    §6.1b:346-348, verbatim: *"`SESSION_FLATTEN_LEAD_MIN < EOD_BLACKOUT_MIN −
    pad` **per symbol** — the entry blackout must lead the flatten deadline ...
    Config validation **rejects** any per-symbol set violating it."*

    **PER SYMBOL is the load-bearing phrase and it is why this rule iterates.**
    Through ARC 032 this predicate compared exactly one pair — the global
    default — which is the vacuous case the moment a per-symbol override exists:
    §12A:819-820 authorise an override on BOTH knobs, so an operator could set
    `ES` to a lead of 25 against a global blackout of 20 and the rule would have
    passed on the untouched global pair while `ES` was inverted. The set judged
    here is therefore the global default PLUS every symbol named in either
    override map, and every message NAMES the symbol, because "the config is
    invalid" is not an operator instruction.

    Extended, not duplicated (doctrine C.9): same `BootRule`, same id, same
    `_boot_validation` entry. A second rule id would have made the global pair
    and the per-symbol pairs two authorities over one invariant.
    """
    cfg = loaded["limiter"]
    pad = _number(cfg, "session_flatten_lead_pad_min")
    problems: list[str] = []
    for symbol, lead, blackout, defects in _session_pairs(cfg):
        problems.extend(defects)
        if lead is None or blackout is None:
            continue
        if lead >= blackout - pad:
            problems.append(
                f"symbol {symbol}: session_flatten_lead_min={lead} is not < "
                f"eod_blackout_min={blackout} - pad={pad} — the entry blackout "
                "must LEAD the session-close flatten deadline for THIS symbol, "
                "or the system can open a position in it after the deadline "
                "that force-flattens it (§6.1b:346-348, per symbol)"
            )
    return problems


def _go_timeout_outlasts_pending_ack(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """The deadlock breaker must not outrun the resolution it breaks out of."""
    cfg = loaded["limiter"]
    go_ms = _number(cfg, "go_timeout_s") * 1000
    ack_ms = _number(cfg, "pending_ack_timeout_ms")
    if go_ms <= ack_ms:
        return [
            (
                f"limiter.go_timeout_s={go_ms / 1000} ({go_ms} ms) does not "
                f"outlast pending_ack_timeout_ms={ack_ms} — the strategy would "
                "reset to flat-and-free while the Limiter is still resolving "
                "the same GO, so the breaker fires on the healthy path"
            )
        ]
    return []


def _heartbeat_grace_at_least_one_cycle(
    loaded: Mapping[str, ModuleConfig],
) -> list[str]:
    """One dropped beat must not be a strategy death — death recovery flattens."""
    grace = _number(loaded["limiter"], "heartbeat_miss_grace_cycles")
    if grace < 1:
        return [
            (
                f"limiter.heartbeat_miss_grace_cycles={grace} is below one "
                "cycle — a single dropped heartbeat would presume the strategy "
                "dead, and death recovery flattens its open positions"
            )
        ]
    return []


def _cooldown_ladder_is_ordered(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """§4:301 fixes the ORDER of the ladder; the seconds are CC-calibrate."""
    cfg = loaded["limiter"]
    ladder = _mapping(cfg, _COOLDOWN_KEY)
    missing = [name for name in _COOLDOWN_ORDER if name not in ladder]
    if missing:
        return [
            (
                f"limiter.{_COOLDOWN_KEY} is missing exit class(es) "
                f"{', '.join(missing)} — the ladder must carry every class §4 "
                "names"
            )
        ]
    extra = sorted(set(ladder) - set(_COOLDOWN_ORDER))
    problems = [
        f"limiter.{_COOLDOWN_KEY} carries exit class {name!r}, which §4 does not "
        "name — a class invented here would be a rule with no authority behind it"
        for name in extra
    ]
    rungs: list[tuple[str, float]] = []
    for name in _COOLDOWN_ORDER:
        value = ladder[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"limiter.{_COOLDOWN_KEY}.{name}={value!r} is not a number")
            return problems
        rungs.append((name, float(value)))
    problems.extend(_ladder_floor_defects(rungs))
    problems.extend(_ladder_order_defects(rungs))
    return problems


def _ladder_floor_defects(rungs: list[tuple[str, float]]) -> list[str]:
    """§4:301: only the discretionary class is 'none'; the rest have real floors."""
    problems: list[str] = []
    for index, (name, value) in enumerate(rungs):
        if value < 0:
            problems.append(
                f"limiter.{_COOLDOWN_KEY}.{name}={value} is negative — 'none' is "
                "zero, never less"
            )
        elif index and value <= 0:
            problems.append(
                f"limiter.{_COOLDOWN_KEY}.{name}={value} — only the "
                "discretionary class may be zero ('none'); every other class has "
                "a real floor"
            )
    return problems


def _ladder_order_defects(rungs: list[tuple[str, float]]) -> list[str]:
    """The ladder runs none <= short <= longer <= longest (§4:301)."""
    return [
        f"limiter.{_COOLDOWN_KEY}: {lower}={low} exceeds {upper}={high} — the "
        "ladder runs none <= short <= longer <= longest and this pair inverts it"
        for (lower, low), (upper, high) in pairwise(rungs)
        if low > high
    ]


def _symbol_maps_agree(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """A capped symbol with no slippage pad would size against an honest-looking
    but unpadded stop distance."""
    cfg = loaded["allocator"]
    caps = set(_mapping(cfg, "symbol_cap"))
    pads = set(_mapping(cfg, "slippage_pad_ticks"))
    problems: list[str] = []
    for symbol in sorted(caps - pads):
        problems.append(
            f"allocator: symbol {symbol!r} has a cap but no slippage pad — it "
            "would size against an unpadded stop distance"
        )
    for symbol in sorted(pads - caps):
        problems.append(
            f"allocator: symbol {symbol!r} has a slippage pad but no cap — it is "
            "half-configured, and a half-configured symbol must not be sizeable"
        )
    return problems


def _retry_ladder_fits_smallest_threshold(
    loaded: Mapping[str, ModuleConfig],
) -> list[str]:
    """The retry ladder must not dominate the freshness bound it sits inside."""
    cfg = loaded["staleness"]
    backoff = _mapping(cfg, "retry_backoff")
    for field in ("attempts", "initial_ms", "multiplier"):
        if field not in backoff:
            return [f"staleness.retry_backoff is missing {field!r}"]
    numbers: dict[str, float] = {}
    for field in ("attempts", "initial_ms", "multiplier"):
        value = backoff[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"staleness.retry_backoff.{field}={value!r} is not a number"]
        numbers[field] = float(value)
    attempts = int(numbers["attempts"])
    initial = numbers["initial_ms"]
    multiplier = numbers["multiplier"]
    total = sum(initial * multiplier**step for step in range(attempts))
    thresholds = {
        key: _number(cfg, key) for key in cfg.values if key.endswith("_stale_ms")
    }
    if not thresholds:
        return [
            (
                "staleness: no `_stale_ms` threshold to compare the retry "
                "ladder against — the rule would pass over an empty comparison"
            )
        ]
    tightest = min(thresholds, key=lambda key: thresholds[key])
    if total >= thresholds[tightest]:
        return [
            (
                f"staleness.retry_backoff totals {total:.0f} ms over "
                f"{attempts} attempt(s), which is not shorter than the "
                f"tightest threshold {tightest}="
                f"{thresholds[tightest]:.0f} ms — the declared threshold would "
                "stop being the quantity that bounds stale detection"
            )
        ]
    return []


def _span_is_whole_days(loaded: Mapping[str, ModuleConfig]) -> list[str]:
    """§6.6 produces one realized number per day; a fractional span counts what
    is never produced."""
    span = _number(loaded["scoring"], "score_ema_span_days")
    if span != int(span):
        return [
            (
                f"scoring.score_ema_span_days={span} is not a whole number of "
                "days, and the EMA's input is one realized figure per symbol "
                "per DAY"
            )
        ]
    return []


#: The Sentinel's threshold is a MULTIPLE of the Limiter's §12A:832 interval,
#: which has one physical home in `risks/limiter.config.json`. Both rules below
#: therefore read TWO modules while being FILED under `sentinel` alone: the
#: limiter's numbers are §12A figures stated outright and are the fixed reference
#: side, and the sentinel's are the Nix additions that must fit around them. A
#: rule filed under both would oblige `risks/limiter.config.json` to declare an id
#: about a module it knows nothing about.
_SENTINEL_REFERENCE = "limiter"


def _sentinel_pair(
    loaded: Mapping[str, ModuleConfig],
) -> tuple[ModuleConfig, ModuleConfig]:
    """`(sentinel, limiter)`, or a loud refusal. Never a defaulted reference.

    A rule that silently skipped itself because its reference module was not in
    the loaded set would be a rule that is off exactly when a partial load is
    what produced the mistake — the shape `docs/debug.md` §7.12 exists to catch.
    """
    if _SENTINEL_REFERENCE not in loaded:
        raise RiskConfigError(
            f"the sentinel rules read {_SENTINEL_REFERENCE!r} for §12A:832's "
            "heartbeat interval and it is not in the loaded set — refusing to "
            "validate the Sentinel's threshold against a reference that is absent"
        )
    return loaded["sentinel"], loaded[_SENTINEL_REFERENCE]


def _sentinel_loss_outlasts_limiter_grace(
    loaded: Mapping[str, ModuleConfig],
) -> list[str]:
    """The deadman must not declare death before the system it watches would.

    `docs/nics_risk_subsystem_spec_v1.3.md` §4:260-261 fixes the grace on a
    heartbeat at exactly one cycle before a second consecutive miss presumes
    death. The Sentinel's response to presumed death is an EMERGENCY FLATTEN of
    the whole account (§12.1:604-606), which is the most expensive action in the
    system, so its own threshold must be strictly longer than that grace. Equal is
    not enough: at equality a single scheduling jitter puts the deadman ahead of
    the supervisor, and §12.1:605's nuisance-flatten hazard fires on a blip.
    """
    sentinel, limiter = _sentinel_pair(loaded)
    multiple = _number(sentinel, "heartbeat_loss_multiple")
    grace = _number(limiter, "heartbeat_miss_grace_cycles")
    floor = 1.0 + grace
    if multiple <= floor:
        return [
            (
                f"sentinel.heartbeat_loss_multiple={multiple} does not exceed "
                f"1 + limiter.heartbeat_miss_grace_cycles={grace} (={floor}) — the "
                "Sentinel would presume the Risk Engine dead and flatten the whole "
                "account no later than the system's own one-cycle grace, so a "
                "single missed beat becomes an emergency flatten"
            )
        ]
    return []


def _sentinel_poll_fits_loss_threshold(
    loaded: Mapping[str, ModuleConfig],
) -> list[str]:
    """A watcher that sleeps longer than the window cannot see the window.

    The threshold is `heartbeat_interval_s x heartbeat_loss_multiple`. If the
    poll interval reaches it, detection latency is bounded below by the very
    quantity that defines the condition, and the deadman's response time becomes
    a property of its sleep rather than of the loss. `docs/nics_risk_subsystem
    _spec_v1.3.md` §12.1:603-606 gives the Sentinel no other timing discipline,
    so this is the one that has to hold.
    """
    sentinel, limiter = _sentinel_pair(loaded)
    poll = _number(sentinel, "poll_interval_s")
    threshold = _number(limiter, "heartbeat_interval_s") * _number(
        sentinel, "heartbeat_loss_multiple"
    )
    if poll >= threshold:
        return [
            (
                f"sentinel.poll_interval_s={poll} is not below the loss threshold "
                f"{threshold} (limiter.heartbeat_interval_s x "
                "sentinel.heartbeat_loss_multiple) — a watchdog whose sleep is as "
                "long as the window it watches can miss the whole window, and its "
                "detection time stops being a property of the loss"
            )
        ]
    return []


#: THE RULE SET. Every id here appears in the `_boot_validation` block of every
#: module it names, and the gate proves the correspondence in both directions.
BOOT_RULES: tuple[BootRule, ...] = (
    BootRule(
        id="positive.scalars",
        modules=OWNED_MODULES,
        spec="§12A:801",
        check=_positive_scalars,
    ),
    BootRule(
        id="fraction.pct_range",
        modules=("allocator", "limiter"),
        spec="§6.5:411",
        check=_pct_range,
    ),
    BootRule(
        id="interlock.margin_cap_within_deployable",
        modules=("limiter",),
        spec="§6.5:411",
        check=_margin_cap_within_deployable,
    ),
    BootRule(
        id="ordering.session_flatten_before_eod_blackout",
        modules=("limiter",),
        spec="§6.1b:346",
        check=_session_flatten_before_eod_blackout,
    ),
    BootRule(
        id="liveness.go_timeout_outlasts_pending_ack",
        modules=("limiter",),
        spec="§4:210",
        check=_go_timeout_outlasts_pending_ack,
    ),
    BootRule(
        id="liveness.heartbeat_grace_at_least_one_cycle",
        modules=("limiter",),
        spec="§4:260",
        check=_heartbeat_grace_at_least_one_cycle,
    ),
    BootRule(
        id="cooldown.ladder_is_ordered",
        modules=("limiter",),
        spec="§4:300",
        check=_cooldown_ladder_is_ordered,
    ),
    BootRule(
        id="sizing.symbol_maps_agree",
        modules=("allocator",),
        spec="§7:483",
        check=_symbol_maps_agree,
    ),
    BootRule(
        id="staleness.retry_ladder_fits_smallest_threshold",
        modules=("staleness",),
        spec="§6.4:373",
        check=_retry_ladder_fits_smallest_threshold,
    ),
    BootRule(
        id="scoring.span_is_whole_days",
        modules=("scoring",),
        spec="§6.6:438",
        check=_span_is_whole_days,
    ),
    BootRule(
        id="sentinel.loss_outlasts_limiter_grace",
        modules=("sentinel",),
        spec="§4:260",
        check=_sentinel_loss_outlasts_limiter_grace,
    ),
    BootRule(
        id="sentinel.poll_fits_loss_threshold",
        modules=("sentinel",),
        spec="§12.1:603",
        check=_sentinel_poll_fits_loss_threshold,
    ),
)


def rule_ids_for(module: str) -> tuple[str, ...]:
    """Every rule id that applies to `module`. The correspondence's code side."""
    return tuple(rule.id for rule in BOOT_RULES if module in rule.modules)


def validate_all(loaded: Mapping[str, ModuleConfig]) -> None:
    """Run every applicable rule. Raise on the FIRST non-empty problem list.

    Positivity runs first (it is the first member of `BOOT_RULES`) so no
    comparison below is ever evaluated over a degenerate all-zero set — the same
    ordering `broker_order_config.validate` uses, for the same reason.

    §7.12 answer 2 is enforced here: a run that evaluated ZERO rules raises,
    because a validator that checked nothing must never return as if it had.
    """
    evaluated = 0
    problems: list[str] = []
    for rule in BOOT_RULES:
        if not set(rule.modules) & set(loaded):
            continue
        evaluated += 1
        found = rule.check(loaded)
        if found:
            problems.append(f"[{rule.id} {rule.spec}] " + "; ".join(found))
            # Positivity is the gate for every later comparison: once a knob is
            # zero or the wrong type, the rules below are arithmetic over
            # nonsense and their messages would mislead.
            if rule.id == "positive.scalars":
                break
    if evaluated == 0:
        raise RiskConfigError(
            "no boot rule applied to the loaded set — a validator that evaluated "
            "nothing must never return as if it had validated"
        )
    if problems:
        raise RiskConfigError("; ".join(problems))


@dataclass(frozen=True)
class RiskConfigSet:
    """Every module's config, loaded once, validated on construction.

    FROZEN, and its `modules` mapping is a read-only view over frozen members.
    That is §12.11's no-hot-reload rule made physical rather than promised: there
    is no writer a mid-session edit could reach, so two decisions inside one open
    trade read the same numbers by construction.
    """

    modules: Mapping[str, ModuleConfig]

    def __post_init__(self) -> None:
        validate_all(self.modules)

    @property
    def config_version(self) -> str:
        """§12.11's boot stamp: a digest over VALUE keys only.

        Documentation keys are excluded deliberately. A reworded `_derivations`
        entry is not a different configuration, and a version that moved on prose
        would make every Plane-1 row's traceability claim weaker, not stronger:
        the operator would learn that *something in the file* changed, which is
        the thing they already knew.
        """
        payload = json.dumps(
            {name: dict(cfg.values) for name, cfg in sorted(self.modules.items())},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def value(self, module: str, key: str) -> object:
        """One knob, read by name. Raises when either the module or key is absent."""
        if module not in self.modules:
            raise RiskConfigError(f"no config loaded for module {module!r}")
        return _require(self.modules[module], key)


def _read_one(path: Path, module: str) -> ModuleConfig:
    """Parse one per-module config into its VALUE keys. Raises on anything."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RiskConfigError(f"cannot read risk config at {path}: {exc}") from exc
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise RiskConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise RiskConfigError(
            f"{path}: top level is {type(raw).__name__}, expected object"
        )
    values = {
        key: value for key, value in raw.items() if not key.startswith(DOC_KEY_PREFIX)
    }
    if not values:
        raise RiskConfigError(
            f"{path}: carries no value key at all — a config of pure "
            "documentation is a set of knobs that does not exist"
        )
    return ModuleConfig(module=module, source=path, values=MappingProxyType(values))


def load_risk_configs(root: Path | None = None) -> RiskConfigSet:
    """Load and validate every module this loader owns. Raises on anything.

    Called ONCE, at boot. There is deliberately no second entry point that
    refreshes an already-loaded set: §12.11 makes `config-reload` a supervised
    restart, so the only way to observe a changed file is to be a new process.
    """
    base = (root or _REPO_ROOT) / RISKS_DIR
    loaded: dict[str, ModuleConfig] = {}
    for module in OWNED_MODULES:
        path = base / f"{module}{CONFIG_SUFFIX}"
        if not path.is_file():
            raise RiskConfigError(
                f"{path} is absent — a declared module with no config is a set "
                "of knobs nothing can validate, never a set of defaults"
            )
        loaded[module] = _read_one(path, module)
    return RiskConfigSet(modules=MappingProxyType(loaded))
