"""The Sentinel's knobs — loaded standalone, validated by the one authority.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 034 / sub-agent B (B1). §12A is the SEMANTIC authority for every tunable in
this system and `risks/*.config.json` is the physical layout; this module is the
Sentinel's reader of that layout, and it is deliberately NOT
`scripts/risk_config.py`'s `load_risk_configs`.

------------------------------------------------------------------------------
WHY A SECOND READER AND NOT A SECOND AUTHORITY — the distinction is the point
------------------------------------------------------------------------------
`load_risk_configs` loads and validates EVERY module in `OWNED_MODULES` and
raises if any one of them is unreadable. For the Limiter, the Allocator and the
Scoring process that is exactly right: they are one system and a broken sibling
config means the boot is wrong.

For the Sentinel it is a **common-mode failure**. §12.1:603 requires it to be
*"Tiny, dependency-minimal"* on a *"separate code path (minimal common-mode
failure)"*, and it exists to act when the rest of the system is already sick. A
deadman that refuses to start because `risks/scoring.config.json` has a typo is
a deadman that is absent exactly when the box is in the state that produces
typos in configs — so this module reads the TWO files whose numbers govern it
and no others.

**It restates nothing and implements no rule of its own.** The two cross-knob
rules that constrain these knobs live in `scripts/risk_config.py`'s `BOOT_RULES`
alongside every other module's, and this module *calls those same callables*
rather than spelling them again (directive 3, doctrine C.9). If it held its own
copy the two could disagree, and the one that ran at boot would not be the one
that ran in the Sentinel.

------------------------------------------------------------------------------
WHY IT STILL DEPENDS ON `risks/limiter.config.json`
------------------------------------------------------------------------------
Because the number it needs lives there and nowhere else. §12A:832
HEARTBEAT_INTERVAL = 1s is the Limiter's knob, published by the Limiter, and
`risks/limiter.config.json` is its single physical home. The Sentinel's threshold
is a MULTIPLE of it, so restating the interval in `risks/sentinel.config.json`
would put one number in two files — the defect directive 3 names. A limiter
config that cannot be read is therefore a genuine refusal here, and it is loud.

------------------------------------------------------------------------------
§12A NAMES NO SENTINEL THRESHOLD, AND THAT IS STATED RATHER THAN PAPERED OVER
------------------------------------------------------------------------------
§12A:832 gives HEARTBEAT_INTERVAL and HEARTBEAT_MISS_GRACE, and §4:260-261 spends
both on the STRATEGY heartbeat's presumed-dead rule. It names no threshold at
which the RISK-ENGINE heartbeat is considered lost, so `heartbeat_loss_multiple`
is a declared Nix addition with a stated derivation, not a spec figure — the same
shape as `session_flatten_lead_pad_min` and `halt_cooldown_floor_s` before it.
`risks/sentinel.config.json`'s `_derivations` block says so in the file itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import risk_config

#: scripts/nixsentinel/config.py -> ~/nix. Derived from this module's own
#: location and never typed as an absolute path (`docs/debug.md` §7.4: the tree
#: moves — a worktree, another operator's home — and a literal root rots
#: silently).
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The two modules whose numbers govern the Sentinel. `limiter` is here for its
#: §12A:832 interval and for nothing else; see the module docstring.
SENTINEL_MODULE = "sentinel"
REFERENCE_MODULE = "limiter"


class SentinelConfigError(RuntimeError):
    """A knob set the Sentinel cannot load or cannot validate.

    Never degraded to a default. CLAUDE.md directive 4 (fail closed and loud) and
    doctrine C.7: a defaulted loss threshold is a deadman with a made-up idea of
    how long silence means death, which is either a nuisance flatten or no
    flatten at all, and neither failure announces itself.
    """


@dataclass(frozen=True)
class SentinelKnobs:
    """The four numbers the watchdog runs on. FROZEN — §12.11 boot-loaded only.

    Two of the four are read from `risks/limiter.config.json` rather than copied
    into `risks/sentinel.config.json`: `heartbeat_interval_s` and
    `heartbeat_miss_grace_cycles` are §12A:832's knobs with a single physical
    home, and a second copy would be a mutable fact restated (directive 3).
    """

    #: §12A:832 HEARTBEAT_INTERVAL, read from the limiter's config.
    heartbeat_interval_s: float
    #: §12A:832 HEARTBEAT_MISS_GRACE, read from the limiter's config. Present
    #: here ONLY as the floor the Sentinel's own threshold must clear.
    heartbeat_miss_grace_cycles: float
    #: The Nix addition. How many intervals of silence make the RISK ENGINE
    #: presumed dead. Not a §12A figure — see the module docstring.
    heartbeat_loss_multiple: float
    #: How often the watchdog wakes. Bounded above by the loss threshold, or the
    #: Sentinel could sleep through the whole window it exists to notice.
    poll_interval_s: float

    @property
    def loss_threshold_s(self) -> float:
        """Silence beyond this and the Risk Engine is presumed dead (§12.1:604)."""
        return self.heartbeat_interval_s * self.heartbeat_loss_multiple

    @property
    def limiter_grace_s(self) -> float:
        """§4:260-261's own presumed-dead window, as a comparable number.

        The Limiter tolerates one missed beat before presuming a STRATEGY dead.
        The Sentinel's threshold has to be strictly longer than the equivalent
        window on the Risk Engine's own beat, or the deadman would declare death
        on a blip the system it is watching has not even noticed yet.
        """
        return self.heartbeat_interval_s * (1.0 + self.heartbeat_miss_grace_cycles)


def _read_module(base: Path, module: str) -> risk_config.ModuleConfig:
    """One `risks/<module>.config.json`, VALUE keys only. Raises on anything.

    Builds `risk_config.ModuleConfig` rather than a local shape so the rule
    callables in `risk_config.BOOT_RULES` can be applied to it unchanged. The
    `_`-prefixed documentation keys are dropped here for the same reason
    `risk_config._read_one` drops them: a loader that read them would make prose
    load-bearing, at which point rewording a comment is a behaviour change.
    """
    path = base / f"{module}{risk_config.CONFIG_SUFFIX}"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SentinelConfigError(f"cannot read {path}: {exc!r}") from exc
    except ValueError as exc:
        raise SentinelConfigError(f"{path} is not valid JSON: {exc!r}") from exc
    if not isinstance(raw, dict):
        raise SentinelConfigError(
            f"{path}: top level is {type(raw).__name__}, expected an object"
        )
    values = {
        key: value
        for key, value in raw.items()
        if not key.startswith(risk_config.DOC_KEY_PREFIX)
    }
    if not values:
        raise SentinelConfigError(
            f"{path} carries no value key at all — a config of pure documentation "
            "is a set of knobs that does not exist"
        )
    return risk_config.ModuleConfig(
        module=module, source=path, values=MappingProxyType(values)
    )


def sentinel_rules() -> tuple[risk_config.BootRule, ...]:
    """Every `BOOT_RULES` entry that names the Sentinel. Derived, never listed.

    Listing the ids here would be a second roster that could fall out of step
    with the one it copies; asking `risk_config` which of its rules apply is the
    same question `rule_ids_for` answers for the gate, and it can only ever give
    one answer.
    """
    return tuple(
        rule for rule in risk_config.BOOT_RULES if SENTINEL_MODULE in rule.modules
    )


def load_sentinel_knobs(root: Path | None = None) -> SentinelKnobs:
    """Load and validate the Sentinel's knob set. Raises on anything.

    Called ONCE, at Sentinel boot. There is no reload verb: §12.11 makes
    `config-reload` a supervised restart, so the only way to observe a changed
    file is to be a new process — and the Sentinel above all others must not
    change its idea of "dead" while it is watching.

    Only the rules that NAME the Sentinel are run. A rule that governs the
    Allocator's sizing is a real rule and it is not this process's business; the
    boot-time `load_risk_configs` runs every one of them for the system as a
    whole, and this deliberately narrower pass is what keeps a sibling module's
    broken config from taking the deadman down with it.
    """
    base = (root or _REPO_ROOT) / risk_config.RISKS_DIR
    loaded = {
        module: _read_module(base, module)
        for module in (REFERENCE_MODULE, SENTINEL_MODULE)
    }
    rules = sentinel_rules()
    if not rules:
        raise SentinelConfigError(
            "no rule in risk_config.BOOT_RULES names the sentinel module — a "
            "knob set validated by nothing must never load as if it had been "
            "validated (docs/debug.md §7.12)"
        )
    problems: list[str] = []
    for rule in rules:
        try:
            found = rule.check(loaded)
        except risk_config.RiskConfigError as exc:
            problems.append(f"[{rule.id} {rule.spec}] {exc}")
            continue
        if found:
            problems.append(f"[{rule.id} {rule.spec}] " + "; ".join(found))
    if problems:
        raise SentinelConfigError("; ".join(problems))
    sentinel = loaded[SENTINEL_MODULE]
    limiter = loaded[REFERENCE_MODULE]
    return SentinelKnobs(
        heartbeat_interval_s=risk_config.knob(limiter, "heartbeat_interval_s"),
        heartbeat_miss_grace_cycles=risk_config.knob(
            limiter, "heartbeat_miss_grace_cycles"
        ),
        heartbeat_loss_multiple=risk_config.knob(sentinel, "heartbeat_loss_multiple"),
        poll_interval_s=risk_config.knob(sentinel, "poll_interval_s"),
    )
