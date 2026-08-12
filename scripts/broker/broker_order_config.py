"""broker_order_config.py — boot-loaded §12A tunables for the broker-order module.

WHY THIS FILE EXISTS (ARC 020 A6). The protective path grew two quantities that are
genuinely tunable — how long a repeat `flatten` is suppressed, and how long a terminal
order stays queryable through `query_order_status`. Both were about to become bare
literals inside `broker_order_ibkr.py`, which is `debug.md` §7.4's anchor problem sitting
on the exit path: a number that describes the current state of the world, with nothing
tying it to the thing it was derived from.

THE THREE-LAYER RULE, as CLAUDE.md states it and as this file implements it:
  - `nics_risk_subsystem_spec_v1.3.md` §12A is the SEMANTIC authority — names, defaults,
    meanings, and the cross-knob boot validation that must reject an invalid set "before
    any strategy registers".
  - `risks/broker_order.config.json` is the PHYSICAL layout — per-module JSON, config-role,
    kept separate from any data-role JSON per CLAUDE.md.
  - This module is the LOADER, and it is the only place either of those is read.

ARC 028 (D1) — TWO FILES, AND EACH §12A KNOB HAS EXACTLY ONE HOME. Two of the five
values below are §12A knobs the LIMITER owns, and until ARC 028 they were MIRRORED into
this module's config because the Limiter had no config of its own. That mirror was a
second authority for a value §12A already owns, recorded as CHECK-DEBT D1.31 and as an
obligation in the config's own `_meta`. `risks/limiter.config.json` now exists, so
`load_broker_order_config` READS those two from it. Nothing is restated, so nothing can
drift; `checks/check_risks_data_only.py` fails if any §12A knob acquires a second home.

LIFECYCLE (§12A / §12.11): values load at BOOT and change only through a restart. There is
deliberately no reload verb here. A hot-editable protective-path constant is a way to
change what `flatten` does while it is running, and §12.11 already settled that question.

FAIL CLOSED AND LOUD (CLAUDE.md directive 4, doctrine C.7). Every failure path raises.
There is no default-on-missing-file, no default-on-bad-value and no partial load: a config
this module cannot fully validate is a config it must not run on, because the two knobs it
carries both bound behaviour on the exit path. The one thing worse than an unreadable
config is a silently-substituted one.

§7.12 — THE STANDING QUESTION, for the validation below: *what would have to be true for
`validate()` to pass while checking nothing?*
  1. The file loads a dict with none of the expected keys and validation only iterates
     what is present. GUARDED: every field is read by NAME through `_require()`, which
     raises on absence — there is no `.get(name, default)` anywhere in this file.
  2. The cross-knob rules are written over values that are all zero/None, so every
     comparison is trivially satisfiable. GUARDED: the positivity rule runs FIRST and
     rejects zero, so no cross-knob comparison is ever evaluated on a degenerate set.
  3. The rules are asserted but never invoked, because `load_broker_order_config` builds
     the dataclass directly. GUARDED: `__post_init__` runs `validate()`, so the object
     cannot exist unvalidated — construction and validation are one motion.
  4. A test constructs the dataclass with keyword defaults and so never reads the JSON at
     all, leaving the file itself unvalidated. GUARDED: the dataclass has NO defaults;
     every field must be supplied, and `test_broker_order.py` loads the real file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

from broker_seam import BrokerSeamError

# Derived from this module's own location, never typed as an absolute path (§7.4: the tree
# moves — a worktree, a different operator's home — and a literal root would rot silently).
# scripts/broker/ -> scripts/ -> ~/nix
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "risks" / "broker_order.config.json"

#: ARC 028 (D1) — THE OBLIGATION IN THIS FILE'S OWN `_meta` COMING DUE.
#: `pending_ack_timeout_ms` and `fill_timeout_ms` are §12A knobs the LIMITER owns
#: (§12A:830). ARC 020 mirrored them into `risks/broker_order.config.json`
#: because there was nowhere else to put them and boot validation had to see them
#: — and wrote down, in the config's own `_meta`, that the mirror was a second
#: authority on a fuse. `risks/limiter.config.json` now exists, so this module
#: READS them instead of restating them. Two files can no longer disagree about
#: one §12A knob, because only one file holds it.
LIMITER_CONFIG_PATH = _REPO_ROOT / "risks" / "limiter.config.json"

#: Knobs read from the LIMITER's config rather than from this module's own.
#: Named here, once, so the split is visible at the top of the file rather than
#: inferred from two `_require` call sites.
LIMITER_OWNED_KEYS: tuple[str, ...] = ("pending_ack_timeout_ms", "fill_timeout_ms")

#: The ids of the cross-knob boot rules `validate()` below implements. The
#: config's `_boot_validation` block names exactly these, and
#: `checks/check_risks_data_only.py` proves the correspondence in both
#: directions — a declared id nothing implements is documentation, and an
#: implemented rule the config does not declare is a rule nobody can find.
BOOT_RULE_IDS: tuple[str, ...] = (
    "positive.scalars",
    "ordering.flatten_window_within_pending_ack",
    "ordering.retention_outlasts_pending_ack",
    "ordering.retention_outlasts_fill_timeout",
)


class BrokerConfigError(BrokerSeamError):
    """A config that cannot be loaded or cannot be validated. Never degraded to defaults."""


@dataclass(frozen=True)
class BrokerOrderConfig:
    """The §12A knobs this module reads. NO DEFAULTS — see §7.12 answer 4 above."""

    pending_ack_timeout_ms: int
    """§12A:830 `PENDING_ACK_TIMEOUT_MS`. The Limiter's, and READ from
    `risks/limiter.config.json` — never restated here. The two knobs below are
    DERIVED from it and boot validation has to see both."""

    fill_timeout_ms: int
    """§12A:830 `FILL_TIMEOUT`, order-type-dependent, CC-calibrate. Also the
    Limiter's and also read from its config; present only so
    `terminal_order_retention_ms` is validated against something rather than nothing."""

    flatten_idempotency_window_ms: int
    """ARC 020 A6, operator-ratified. How long a protective `flatten`'s declared intent
    for a symbol suppresses a second `flatten` for that symbol. On expiry the intent is
    DISCARDED; the adapter never auto-refires (re-invocation is the Limiter's)."""

    terminal_order_retention_ms: int
    """ARC 020 A1, D1.24's retention policy. How long an order that reached a terminal
    state stays queryable through `query_order_status` before its per-order state is
    released."""

    flatten_attempt_log_depth: int
    """ARC 020 A6, D1.28. Ring depth of the flatten attempt record. Not a §12A knob; an
    observability bound that keeps the record from becoming the leak D1.24 was opened for."""

    def __post_init__(self) -> None:
        self.validate()

    # ---- the cross-knob boot validation §12A requires -----------------------------
    def validate(self) -> None:
        """Reject an invalid set LOUDLY. §12A: "Boot validation ... rejects an invalid set
        before any strategy registers."

        Each rule names the section it comes from, because a rule whose provenance is not
        written down is one refactor away from being 'simplified' as arbitrary.
        """
        problems: list[str] = []

        # Rule 1 — positivity. Runs first, so no cross-knob comparison below is ever
        # evaluated over a degenerate all-zero set (§7.12 answer 2).
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                problems.append(
                    f"[positive.scalars] {f.name}={value!r} — must be a positive int"
                )
        if problems:
            raise BrokerConfigError("; ".join(problems))

        # Rule 2 — §4 "Failure resolution" + §12A:830. The adapter must stop suppressing a
        # repeat protective flatten at the instant the Limiter's pending-timeout machinery
        # takes the question over. Suppressing past that point means nothing is protecting.
        if self.flatten_idempotency_window_ms > self.pending_ack_timeout_ms:
            problems.append(
                f"[ordering.flatten_window_within_pending_ack] "
                f"flatten_idempotency_window_ms={self.flatten_idempotency_window_ms} "
                f"exceeds pending_ack_timeout_ms={self.pending_ack_timeout_ms} — the "
                "adapter would still be suppressing a protective flatten after the "
                "Limiter's §4 pending-timeout resolution had already begun"
            )

        # Rule 3/4 — §4 "Failure resolution" and §4 "Partial fill". A terminal order must
        # outlive both the interval after which the Limiter asks about it and a late
        # execution racing the terminal transition.
        if self.terminal_order_retention_ms <= self.pending_ack_timeout_ms:
            problems.append(
                f"[ordering.retention_outlasts_pending_ack] "
                f"terminal_order_retention_ms={self.terminal_order_retention_ms} does not "
                f"exceed pending_ack_timeout_ms={self.pending_ack_timeout_ms} — a terminal "
                "order could be released before the Limiter queries it (§4 resolves a "
                "pending timeout by QUERYING, never by resending)"
            )
        if self.terminal_order_retention_ms <= self.fill_timeout_ms:
            problems.append(
                f"[ordering.retention_outlasts_fill_timeout] "
                f"terminal_order_retention_ms={self.terminal_order_retention_ms} does not "
                f"exceed fill_timeout_ms={self.fill_timeout_ms} — same reason, on the fill "
                "half of §4's pending-timeout pair"
            )

        if problems:
            raise BrokerConfigError("; ".join(problems))


def _require(raw: dict, key: str, source: str) -> int:
    """Read a key by NAME and raise if it is absent. There is no defaulted read in this
    module — a missing knob is a config that was not written, not a knob that is zero."""
    if key not in raw:
        raise BrokerConfigError(f"{source}: required key {key!r} is absent")
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise BrokerConfigError(
            f"{source}: {key}={value!r} is {type(value).__name__}, expected int"
        )
    return value


def _load_object(src: Path, what: str) -> dict:
    """Read one per-module JSON config into a dict. Raises on anything.

    One reader, two files (this module's own and the Limiter's), so the two can
    never disagree about what "unreadable" or "not an object" means.
    """
    try:
        text = src.read_text(encoding="utf-8")
    except OSError as exc:
        raise BrokerConfigError(f"cannot read {what} config at {src}: {exc}") from exc
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise BrokerConfigError(f"{src} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BrokerConfigError(
            f"{src}: top level is {type(raw).__name__}, expected object"
        )
    return raw


def load_broker_order_config(
    path: Path | None = None, limiter_path: Path | None = None
) -> BrokerOrderConfig:
    """Load and validate the per-module config. Raises `BrokerConfigError` on anything.

    TWO files, and the split is the point (ARC 028 D1). This module's own knobs come
    from `risks/broker_order.config.json`; the two §12A knobs the LIMITER owns come
    from `risks/limiter.config.json`. Neither file restates the other's values, so a
    §12A knob has exactly one physical home and no pair of files can drift apart.

    Keys prefixed `_` in the JSON are documentation (`_meta`, `_derivations`,
    `_boot_validation`) and are deliberately NOT loaded: they exist so a reader can check
    the derivation of every value against the spec without leaving the file, which is the
    whole defence against a knob quietly becoming a magic number again.
    """
    src = path or DEFAULT_CONFIG_PATH
    limiter_src = limiter_path or LIMITER_CONFIG_PATH
    raw = _load_object(src, "broker-order")
    limiter_raw = _load_object(limiter_src, "limiter")

    source = str(src)
    limiter_source = str(limiter_src)
    return BrokerOrderConfig(
        pending_ack_timeout_ms=_require(
            limiter_raw, "pending_ack_timeout_ms", limiter_source
        ),
        fill_timeout_ms=_require(limiter_raw, "fill_timeout_ms", limiter_source),
        flatten_idempotency_window_ms=_require(
            raw, "flatten_idempotency_window_ms", source
        ),
        terminal_order_retention_ms=_require(
            raw, "terminal_order_retention_ms", source
        ),
        flatten_attempt_log_depth=_require(raw, "flatten_attempt_log_depth", source),
    )
