"""ARC 028 / D — the §12A boot validation FIRES, and the config cannot hot-reload.

Two properties, both driven rather than asserted:

  * **THE BOOT VALIDATION IS RUNNABLE AND CAN SAY NO.** §12A:801-802 requires
    boot validation to reject an invalid set "before any strategy registers". A
    `_boot_validation` block nothing executes is documentation, so every rule in
    `scripts/risk_config.py` is driven RED here, one at a time, over a throwaway
    copy of the real configs — and each control asserts the RULE ID in the
    message, never merely that something raised.

  * **BOOT-LOADED, RESTART-ONLY (§12.11).** *"No hot-reload — a mid-session
    change would let two decisions inside one open trade read different
    tunables."* Proved mechanically: the loaded object is frozen, its mappings
    are read-only views, an on-disk edit is invisible to an already-loaded set,
    and the config version that §12.11 stamps into the Plane-1 boot event moves
    on a VALUE change and not on a reworded comment.

**No plant touches a production artifact** (doctrine C.8). Every case copies
`risks/` into `tmp_path`, perturbs the copy, and loads from there. The real
configs are read and never written.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# test module by requirement.

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import risk_config as rc  # pylint: disable=wrong-import-position

sys.path.append(str(REPO / "scripts" / "nixrisk"))


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of the real risks/ directory."""
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    return tmp_path


def _edit(home: Path, module: str, mutate) -> None:
    """Apply `mutate` to one copied config's parsed JSON and write it back."""
    path = home / "risks" / f"{module}{rc.CONFIG_SUFFIX}"
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def _rejection(home: Path) -> str:
    """Load the copied tree and return the rejection message. Fails if it loads."""
    try:
        rc.load_risk_configs(home)
    except rc.RiskConfigError as exc:
        return str(exc)
    raise AssertionError(
        "the invalid set LOADED — boot validation did not fire, which is the "
        "decoration §12A:801-802 exists to prevent"
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the real set loads, and the rule population is real
# --------------------------------------------------------------------------


def test_the_REAL_CONFIGS_load_and_the_RULE_SET_is_not_empty() -> None:
    """The credibility floor. A can-fail over a set that never loads proves nothing."""
    loaded = rc.load_risk_configs(REPO)

    assert set(loaded.modules) == set(rc.OWNED_MODULES), sorted(loaded.modules)
    assert len(rc.BOOT_RULES) >= 5, [rule.id for rule in rc.BOOT_RULES]
    assert len(loaded.config_version) == 64, loaded.config_version


def test_EVERY_DECLARED_RULE_APPLIES_TO_AT_LEAST_ONE_LOADED_MODULE() -> None:
    """A rule whose modules do not exist never runs and is furniture (§7.12 #2)."""
    for rule in rc.BOOT_RULES:
        assert set(rule.modules) & set(rc.OWNED_MODULES), (
            f"{rule.id} names modules {rule.modules}, none of which is loaded — "
            "it could never evaluate"
        )


def test_a_VALIDATOR_THAT_EVALUATED_NOTHING_RAISES_rather_than_returning() -> None:
    """§7.12 answer 2, mechanised: zero evaluations is never a pass."""
    with pytest.raises(rc.RiskConfigError) as caught:
        rc.validate_all({})

    assert "evaluated nothing" in str(caught.value), caught.value


# --------------------------------------------------------------------------
# EVERY RULE DRIVEN RED — each control asserts the RULE ID, not an exception type
# --------------------------------------------------------------------------


def test_positive_scalars_REJECTS_a_zero_knob(home: Path) -> None:
    """A zero risk numerator sizes every proposal to nothing — silently."""
    _edit(home, "allocator", lambda raw: raw.__setitem__("per_trade_risk_usd", 0))

    message = _rejection(home)

    assert "[positive.scalars" in message, message
    assert "per_trade_risk_usd" in message, message


def test_positive_scalars_REJECTS_a_NESTED_zero_inside_a_map(home: Path) -> None:
    """The rule reaches leaves, not just top-level keys."""
    _edit(home, "allocator", lambda raw: raw["symbol_cap"].__setitem__("ES", 0))

    message = _rejection(home)

    assert "[positive.scalars" in message, message
    assert "symbol_cap.ES" in message, message


def test_pct_range_REJECTS_a_fraction_above_one(home: Path) -> None:
    """A cap above 1 would deploy more than the account holds."""
    _edit(home, "limiter", lambda raw: raw.__setitem__("deployable_pct", 1.5))

    message = _rejection(home)

    assert "[fraction.pct_range" in message, message
    assert "deployable_pct" in message, message


def test_interlock_REJECTS_a_margin_cap_wider_than_the_deployable_envelope(
    home: Path,
) -> None:
    """§6.5 calls the cap and the buffer one coupled system."""
    _edit(home, "limiter", lambda raw: raw.__setitem__("agg_margin_cap_pct", 0.9))

    message = _rejection(home)

    assert "[interlock.margin_cap_within_deployable" in message, message
    assert "0.9" in message and "0.7" in message, message


def test_the_SECTION_6_1b_ORDERING_INVARIANT_REJECTS_an_inverted_set(
    home: Path,
) -> None:
    """The one invariant §12A:802 names as boot-validated, actually rejecting."""
    _edit(home, "limiter", lambda raw: raw.__setitem__("session_flatten_lead_min", 16))

    message = _rejection(home)

    assert "[ordering.session_flatten_before_eod_blackout" in message, message
    assert "must LEAD" in message, message


def test_go_timeout_REJECTS_a_breaker_that_outruns_the_resolution(home: Path) -> None:
    """§4:210's deadlock breaker must not fire on the healthy path."""
    _edit(home, "limiter", lambda raw: raw.__setitem__("go_timeout_s", 1))

    message = _rejection(home)

    assert "[liveness.go_timeout_outlasts_pending_ack" in message, message
    assert "flat-and-free" in message, message


def test_heartbeat_grace_REJECTS_a_sub_cycle_grace(home: Path) -> None:
    """One dropped beat must not be a death — death recovery flattens (§4:260)."""
    _edit(
        home, "limiter", lambda raw: raw.__setitem__("heartbeat_miss_grace_cycles", 0.5)
    )

    message = _rejection(home)

    assert "[liveness.heartbeat_grace_at_least_one_cycle" in message, message
    assert "flattens" in message, message


def test_the_COOLDOWN_LADDER_REJECTS_an_inverted_pair(home: Path) -> None:
    """§4:301 fixes the order none <= short <= longer <= longest."""
    _edit(
        home, "limiter", lambda raw: raw["cooldown_min_time_s"].__setitem__("stop", 400)
    )

    message = _rejection(home)

    assert "[cooldown.ladder_is_ordered" in message, message
    assert "inverts it" in message, message


def test_the_COOLDOWN_LADDER_REJECTS_an_EXIT_CLASS_SECTION_4_DOES_NOT_NAME(
    home: Path,
) -> None:
    """A class invented in risks/ would be a rule with no authority behind it."""
    _edit(
        home,
        "limiter",
        lambda raw: raw["cooldown_min_time_s"].__setitem__("weekend_vibes", 60),
    )

    message = _rejection(home)

    assert "[cooldown.ladder_is_ordered" in message, message
    assert "weekend_vibes" in message, message


def test_symbol_maps_REJECT_a_half_configured_symbol(home: Path) -> None:
    """A capped symbol with no pad sizes against an unpadded stop (§7:481-483)."""
    _edit(home, "allocator", lambda raw: raw["slippage_pad_ticks"].pop("ZN"))

    message = _rejection(home)

    assert "[sizing.symbol_maps_agree" in message, message
    assert "'ZN'" in message, message


def test_the_RETRY_LADDER_REJECTS_a_backoff_longer_than_the_tightest_threshold(
    home: Path,
) -> None:
    """§6.4:373 declares stale only after retry/backoff; the ladder must fit."""
    _edit(
        home,
        "staleness",
        lambda raw: raw["retry_backoff"].__setitem__("initial_ms", 5000),
    )

    message = _rejection(home)

    assert "[staleness.retry_ladder_fits_smallest_threshold" in message, message
    assert "price_stale_ms" in message, message


def test_the_EMA_SPAN_REJECTS_a_fractional_day(home: Path) -> None:
    """§6.6:438's input is one realized number per DAY."""
    _edit(home, "scoring", lambda raw: raw.__setitem__("score_ema_span_days", 10.5))

    message = _rejection(home)

    assert "[scoring.span_is_whole_days" in message, message


def test_EVERY_RULE_IN_THE_SET_HAS_BEEN_DRIVEN_RED_BY_THIS_MODULE() -> None:
    """The census that keeps the can-fail suite honest as rules are added.

    Without this, adding an eleventh rule and no eleventh control would leave a
    rule that has never been seen to say no — which is precisely the D3 class
    this ledger keeps ('a gate is guilty until shown able to say no').
    """
    source = Path(__file__).read_text(encoding="utf-8")
    undriven = [rule.id for rule in rc.BOOT_RULES if f"[{rule.id}" not in source]

    assert not undriven, (
        f"boot rule(s) {undriven} are implemented and no control in this module "
        "has ever observed them rejecting a set"
    )


# --------------------------------------------------------------------------
# LOUD, NEVER DEFAULTED
# --------------------------------------------------------------------------


def test_an_ABSENT_MODULE_CONFIG_is_LOUD_and_never_a_set_of_defaults(
    home: Path,
) -> None:
    """CLAUDE.md directive 4. The one thing worse than an unreadable config is a
    silently-substituted one."""
    (home / "risks" / f"scoring{rc.CONFIG_SUFFIX}").unlink()

    with pytest.raises(rc.RiskConfigError) as caught:
        rc.load_risk_configs(home)

    assert "is absent" in str(caught.value), caught.value
    assert "never a set of defaults" in str(caught.value), caught.value


def test_a_CONFIG_OF_PURE_DOCUMENTATION_is_LOUD(home: Path) -> None:
    """A file with only `_`-keys is a set of knobs that does not exist."""
    path = home / "risks" / f"supervision{rc.CONFIG_SUFFIX}"
    raw = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps({k: v for k, v in raw.items() if k.startswith("_")}, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(rc.RiskConfigError) as caught:
        rc.load_risk_configs(home)

    assert "carries no value key" in str(caught.value), caught.value


# --------------------------------------------------------------------------
# §12.11 — BOOT-LOADED, RESTART-ONLY. Measured, not asserted in prose.
# --------------------------------------------------------------------------


def test_the_LOADED_SET_IS_FROZEN_so_no_writer_can_change_it_mid_session(
    home: Path,
) -> None:
    """§12.11's reason, made physical: two decisions inside one open trade cannot
    read different tunables because there is no writer at all."""
    loaded = rc.load_risk_configs(home)

    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.modules = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        loaded.modules["limiter"].values["deployable_pct"] = 0.9  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.modules["limiter"].module = "other"  # type: ignore[misc]


def test_an_ON_DISK_EDIT_IS_INVISIBLE_to_an_ALREADY_LOADED_SET(home: Path) -> None:
    """The no-hot-reload property itself: a mid-session file change reaches
    nothing, and the only way to observe it is to load again — a restart."""
    booted = rc.load_risk_configs(home)
    before = booted.config_version

    _edit(home, "limiter", lambda raw: raw.__setitem__("eod_blackout_min", 25))

    assert booted.value("limiter", "eod_blackout_min") == 20, (
        "the booted set observed a mid-session edit — §12.11 forbids exactly this"
    )
    assert booted.config_version == before, booted.config_version

    rebooted = rc.load_risk_configs(home)
    assert rebooted.value("limiter", "eod_blackout_min") == 25
    assert rebooted.config_version != before, (
        "a restart read the changed file and the version did NOT move — the "
        "Plane-1 boot stamp would then be unable to tell two tunable sets apart"
    )


def test_the_CONFIG_VERSION_MOVES_ON_A_VALUE_and_NOT_ON_A_REWORDED_COMMENT(
    home: Path,
) -> None:
    """§12.11 stamps the version into the boot event so every later row is
    traceable to the tunable set it ran under. A version that moved on prose
    would tell the operator only that the file changed — which they knew."""
    baseline = rc.load_risk_configs(home).config_version

    _edit(
        home, "limiter", lambda raw: raw["_meta"].__setitem__("landed_by", "reworded")
    )
    assert rc.load_risk_configs(home).config_version == baseline, (
        "a documentation edit moved the config version"
    )

    _edit(home, "limiter", lambda raw: raw.__setitem__("news_blackout_min", 21))
    assert rc.load_risk_configs(home).config_version != baseline, (
        "a VALUE edit did not move the config version"
    )


def test_the_LOADER_EXPOSES_NO_RELOAD_VERB_at_all() -> None:
    """§12.11 makes `config-reload` a supervised restart and nothing else. The
    check gate reads this property by AST; this control reads the live module,
    so the two cannot both be fooled by the same trick."""
    reload_verb = re.compile(r"(?i)(reload|refresh|reread|rewatch|watch)")
    offenders = [
        name
        for name in dir(rc)
        if callable(getattr(rc, name)) and reload_verb.search(name)
    ]

    assert not offenders, (
        f"{rc.__name__} exposes reload-shaped callable(s): {offenders}"
    )


def test_the_CONFIG_VERSION_FITS_THE_FROZEN_SEAMS_BOOT_EVENT(home: Path) -> None:
    """§12.11: "the config version is stamped into the boot event (Plane-1)".

    The stamp needs a home in the frozen seam or the requirement has nowhere to
    land. `scripts/nixrisk/seam.py` is READ here and never edited — the row is
    constructed, which is what proves `EventKind.BOOT` and `EventRow.fields` can
    actually carry it.
    """
    # `scripts/nixrisk` is appended to sys.path at module scope, which pylint's
    # static resolution cannot see (the same reason `checks/` carries the
    # disable in every other check test).
    from seam import (  # pylint: disable=import-outside-toplevel,import-error
        EventKind,
        EventRow,
    )

    loaded = rc.load_risk_configs(home)
    row = EventRow(
        kind=EventKind.BOOT,
        ts=0.0,
        strategy_id="",
        reason="boot",
        fields={"config_version": loaded.config_version},
    )

    assert row.kind is EventKind.BOOT
    assert row.fields["config_version"] == loaded.config_version
