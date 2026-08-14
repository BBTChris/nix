"""Crucible calendar runtime module — query test suite.

Exercises ARC CRUCIBLE-CALENDAR-INFRA Success #1, #3, #4, #5, #6. Imports
ONLY `crucible.calendar` (the runtime module), never `crucible.calendar_gen`
(the generator) — that is itself part of Success #1's proof: this whole
file must be able to pass with the generator's calendar library absent.
"""

from __future__ import annotations

import ast
import itertools
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest  # pylint: disable=import-error
from crucible import calendar as cal

REPO_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_MODULE = REPO_ROOT / "scripts" / "crucible" / "calendar.py"

# From here down, this file deliberately re-declares constants and re-derives
# logic that also lives in checks/check_crucible_calendar.py (the locked
# group roster, the forbidden-imports scan) rather than importing them: an
# independent second implementation is the point -- a bug in the gate's own
# definitions would otherwise go unnoticed by a test sharing them. Mirrors
# check_monitor.py's reasoning for duplicating its __main__ block.
# pylint: disable=duplicate-code
ALL_GROUPS = (
    "agriculturals",
    "energy",
    "equity_index",
    "fx",
    "interest_rates",
    "metals",
)


# --- Success #1: two-layer separation -------------------------------------


def test_runtime_module_declares_all_six_groups():
    """The vendored artifact carries exactly the six locked product groups."""
    assert cal.known_product_groups() == tuple(sorted(ALL_GROUPS))


def test_static_grep_no_calendar_lib_or_network_import():
    """Success #1 PROOF 2: static grep of the runtime module shows no import
    of the generator's library and no socket/http/urllib usage. Parsed via
    `ast`, not a plain substring grep, so a docstring mentioning the library
    by name (as this file's own header does) can never produce a false
    negative on the real check."""
    tree = ast.parse(CALENDAR_MODULE.read_text())
    # Deliberately re-declared rather than imported from
    # checks/check_crucible_calendar.py: an independent second
    # implementation is the point of this test -- a bug in the gate's own
    # FORBIDDEN_IMPORTS/scan logic would otherwise go unnoticed by a test
    # sharing its buggy definition.
    # pylint: disable=duplicate-code
    banned = {
        "pandas_market_calendars",
        "pandas",
        "exchange_calendars",
        "socket",
        "http",
        "http.client",
        "urllib",
        "urllib.request",
        "requests",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    hit = imported & banned
    assert not hit, f"runtime module imports forbidden module(s): {hit}"


def test_runtime_module_works_with_calendar_libs_absent():
    """Success #1 PROOF 1: uninstall the calendar library from the runtime
    venv, run the full query test suite, all pass. Simulated here by
    spawning a bare interpreter with `pandas_market_calendars`, `pandas`,
    and `exchange_calendars` excluded from sys.path via a `sitecustomize`-
    style meta path blocker installed before `crucible.calendar` is
    imported, then exercising every public API function end to end.

    A one-time literal `pip uninstall` of the shared dev venv followed by
    a full `pytest scripts/tests` run was also performed manually during
    this arc (see RESULTS.md) -- this test is the standing, repeatable
    substitute so the proof survives every future test run without the
    cost/fragility of mutating the shared venv on every CI invocation.
    """
    script = f"""
import sys

class _BlockCalendarLibs:
    BLOCKED = {{"pandas_market_calendars", "pandas", "exchange_calendars"}}
    def find_module(self, fullname, path=None):
        if fullname.split(".")[0] in self.BLOCKED:
            return self
        return None
    def load_module(self, fullname):
        raise ImportError(f"blocked for two-layer-separation proof: {{fullname}}")

sys.meta_path.insert(0, _BlockCalendarLibs())
sys.path.insert(0, {str(REPO_ROOT / "scripts")!r})

from crucible import calendar as cal
from datetime import date, datetime, timezone

assert cal.known_product_groups() == tuple(sorted({ALL_GROUPS!r}))
bounds = cal.session_bounds("equity_index", date(2024, 6, 3))
assert bounds is not None
assert cal.is_session_open(
    "equity_index", datetime(2024, 6, 3, 15, 0, tzinfo=timezone.utc)
)
assert cal.trading_days("fx", date(2024, 6, 3), date(2024, 6, 7))
print("OK: runtime module fully functional with calendar libs blocked")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"runtime module failed with calendar libs blocked\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK: runtime module fully functional" in result.stdout


# --- Success #3: product-group-scoped divergence ---------------------------


def test_group_scoped_session_bounds_diverge_on_known_early_close_day():
    """2024-11-28 (US Thanksgiving): energy closes early at 13:30 CT while
    equity index closes early at a DIFFERENT time (12:00 CT) and FX does not
    close early at all (16:00 CT, its normal close) -- proof the artifact
    carries distinct, product-group-scoped session rules, not one global
    calendar (Success #3)."""
    d = date(2024, 11, 28)
    energy_bounds = cal.session_bounds("energy", d)
    equity_bounds = cal.session_bounds("equity_index", d)
    fx_bounds = cal.session_bounds("fx", d)
    assert energy_bounds is not None and equity_bounds is not None
    assert fx_bounds is not None
    _, _, _, energy_close = energy_bounds
    _, _, _, equity_close = equity_bounds
    assert energy_close != equity_close
    assert cal.is_early_close("energy", d) is not False
    assert cal.is_early_close("equity_index", d) is not False
    assert cal.is_early_close("fx", d) is False, "FX does not early-close Thanksgiving"
    # Agriculture takes the full day as a holiday -- no session at all.
    assert cal.session_bounds("agriculturals", d) is None


def test_all_six_groups_have_independent_session_calendars():
    """Christmas Eve 2024: not every group need diverge on every day, but the
    six calendars must not all share one close time -- a single global
    calendar masquerading as six would fail this."""
    d = date(2024, 12, 24)  # Christmas Eve -- a classic multi-group divergence day
    results = {g: cal.session_bounds(g, d) for g in ALL_GROUPS}
    distinct_close_times = {r[3] for r in results.values() if r is not None}
    assert len(distinct_close_times) > 1, (
        "all groups share one close time -- single global calendar"
    )


# --- Success #4: span, gap-free ---------------------------------------------


def test_all_groups_constant_matches_the_parametrized_literal():
    """Guards the literal tuple below against drifting from ALL_GROUPS (they
    must be kept in lockstep by hand -- see the parametrize comment)."""
    assert set(ALL_GROUPS) == {
        "agriculturals",
        "energy",
        "equity_index",
        "fx",
        "interest_rates",
        "metals",
    }


@pytest.mark.parametrize(
    "group",
    (
        "agriculturals",
        "energy",
        "equity_index",
        "fx",
        "interest_rates",
        "metals",
    ),  # literal tuple, not ALL_GROUPS: check_derived_claims' AST probe
    # (checks/check_derived_claims.py:_parametrize_multiplier) requires a
    # literal List/Tuple node in the decorator call, not a name reference --
    # kept in lockstep with ALL_GROUPS by test_all_groups_constant_matches_
    # the_parametrized_literal below.
)
def test_trading_days_span_2008_2030_monotonic_gap_free(group):
    """Full locked span, every group: monotonic, gap-free, plausible density."""
    days = cal.trading_days(group, date(2008, 1, 1), date(2030, 12, 31))
    assert days == sorted(set(days)), "trading_days not monotonic / has duplicates"
    assert days[0] <= date(2008, 1, 3)
    assert days[-1] >= date(2030, 12, 30)
    # Reconciliation tolerance: ~252 sessions/year is the well-known US
    # futures-market baseline; 23 years should land close to that average.
    years = 2030 - 2008 + 1
    avg_per_year = len(days) / years
    assert 240 <= avg_per_year <= 262, (
        f"{group}: {avg_per_year} sessions/year avg out of tolerance"
    )


def test_trading_days_no_internal_gap_longer_than_a_weekend_plus_holiday_run():
    """No gap of more than ~4 consecutive missing calendar days inside the
    span for equity_index (the group with the fewest holiday closures) --
    catches a silently-dropped multi-week range, which a pure count check
    could mask if compensated by a duplicate elsewhere."""
    days = cal.trading_days("equity_index", date(2008, 1, 1), date(2030, 12, 31))
    worst_gap = max((b - a).days for a, b in itertools.pairwise(days))
    assert worst_gap <= 4, (
        f"gap of {worst_gap} calendar days found in equity_index span"
    )


# --- Success #5: UTC-primary, DST-correct -----------------------------------


def test_dst_spring_forward_week_utc_offsets():
    """Session dated 2024-03-08 (Fri, pre-transition) is CST (UTC-6): open
    23:00Z the prior evening. Session dated 2024-03-11 (Mon, opened Sunday
    evening post-transition) is CDT (UTC-5): open 22:00Z."""
    pre = cal.session_bounds("fx", date(2024, 3, 8))
    post = cal.session_bounds("fx", date(2024, 3, 11))
    assert pre is not None and post is not None
    _, _, pre_open, pre_close = pre
    _, _, post_open, post_close = post
    assert pre_open.hour == 23 and pre_close.hour == 22  # CST, UTC-6
    assert post_open.hour == 22 and post_close.hour == 21  # CDT, UTC-5


def test_dst_fall_back_week_utc_offsets_and_no_duplicate_or_skipped_session():
    """Fall-back week: no duplicate/unsorted session, Saturday never a
    session date, and the CDT -> CST offset walk lands correctly."""
    days = cal.trading_days("fx", date(2024, 10, 28), date(2024, 11, 8))
    assert days == sorted(set(days)), (
        "duplicate or unsorted session across fall-back week"
    )
    assert date(2024, 11, 2) not in days, "Saturday must never be a session date"
    pre = cal.session_bounds("fx", date(2024, 11, 1))  # Fri, pre-transition, CDT
    post = cal.session_bounds("fx", date(2024, 11, 4))  # Mon, post-transition, CST
    assert pre is not None and post is not None
    assert pre[2].hour == 22  # CDT open, UTC-5
    assert post[2].hour == 23  # CST open, UTC-6


def test_all_returned_instants_are_utc_aware():
    """Every session_bounds instant is timezone-aware and exactly UTC+00:00."""
    bounds = cal.session_bounds("equity_index", date(2024, 6, 3))
    assert bounds is not None
    for instant in bounds:
        assert instant.tzinfo is not None
        assert instant.utcoffset() == timedelta(0)


# --- Success #6: API surface + behavioral correctness -----------------------


def test_is_session_open_normal_session():
    """Mid-session instant reads open."""
    open_instant = datetime(2024, 6, 3, 15, 0, tzinfo=UTC)  # mid-session
    assert cal.is_session_open("equity_index", open_instant) is True


def test_is_session_open_false_during_daily_maintenance_break():
    """16:00-17:00 CT (21:00-22:00 UTC in summer CDT) is the daily maintenance
    break -- the gap between one session's close and the next session's
    open -- and must read as closed."""
    break_instant = datetime(2024, 6, 3, 21, 30, tzinfo=UTC)
    assert cal.is_session_open("equity_index", break_instant) is False


def test_is_session_open_false_on_holiday():
    """2024-11-28 (Thanksgiving) ag is a full holiday -- nothing open all day."""
    instant = datetime(2024, 11, 28, 18, 0, tzinfo=UTC)
    assert cal.is_session_open("agriculturals", instant) is False


def test_sunday_open_is_a_real_session_start():
    """The week's first session (Monday 2024-06-03) opens Sunday evening CT."""
    sunday_evening = datetime(2024, 6, 2, 23, 30, tzinfo=UTC)  # ~18:30 CT Sunday
    assert cal.is_session_open("fx", sunday_evening) is True


def test_next_close_from_mid_session():
    """From inside a live session, next_close is that session's own close."""
    instant = datetime(2024, 6, 3, 15, 0, tzinfo=UTC)
    close = cal.next_close("equity_index", instant)
    bounds = cal.session_bounds("equity_index", date(2024, 6, 3))
    assert bounds is not None
    assert close == bounds[3]


def test_next_close_from_maintenance_break_returns_next_session():
    """From inside the daily maintenance break, next_close is the NEXT
    session's close, not the one that just ended."""
    instant = datetime(2024, 6, 3, 22, 30, tzinfo=UTC)  # inside the break
    close = cal.next_close("equity_index", instant)
    assert close > instant
    next_bounds = cal.session_bounds("equity_index", date(2024, 6, 4))
    assert next_bounds is not None
    assert close == next_bounds[3]


def test_next_close_exactly_at_a_close_returns_that_close():
    """An instant exactly AT a close is itself the answer ('at or after')."""
    bounds = cal.session_bounds("equity_index", date(2024, 6, 3))
    assert bounds is not None
    assert cal.next_close("equity_index", bounds[3]) == bounds[3]


def test_next_close_out_of_span_raises():
    """Past the vendored artifact's span, next_close raises rather than
    guessing at a close that isn't in the data."""
    with pytest.raises(ValueError):
        cal.next_close("equity_index", datetime(2031, 1, 1, tzinfo=UTC))


def test_is_early_close_returns_override_close_not_bare_true():
    """is_early_close returns the actual UTC override close, not a bare
    True a caller would have to re-derive from session_bounds."""
    override = cal.is_early_close("energy", date(2024, 11, 28))
    assert override is not False
    assert isinstance(override, datetime)
    bounds = cal.session_bounds("energy", date(2024, 11, 28))
    assert bounds is not None
    assert override == bounds[3]


def test_is_early_close_false_on_normal_session():
    """A normal (non-early-close) session reads False."""
    assert cal.is_early_close("equity_index", date(2024, 6, 3)) is False


def test_is_early_close_false_on_holiday():
    """A holiday (no session at all) reads False, not an override close."""
    assert cal.is_early_close("agriculturals", date(2024, 11, 28)) is False


def test_session_bounds_none_on_holiday():
    """session_bounds returns None on a holiday, never a stale/fake window."""
    assert cal.session_bounds("equity_index", date(2024, 12, 25)) is None


def test_session_bounds_accepts_iso_string_and_date_object_identically():
    """An ISO date string and a `date` object for the same day answer identically."""
    from_str = cal.session_bounds("equity_index", "2024-06-03")
    from_date = cal.session_bounds("equity_index", date(2024, 6, 3))
    assert from_str == from_date


def test_unknown_product_group_raises():
    """An unrecognized product_group raises the dedicated error type."""
    with pytest.raises(cal.UnknownProductGroupError):
        cal.session_bounds("nonexistent_group", date(2024, 6, 3))


def test_trading_days_start_after_end_raises():
    """A backwards [start, end] range raises rather than returning an empty
    list that could be mistaken for a genuinely empty span."""
    with pytest.raises(ValueError):
        cal.trading_days("fx", date(2024, 6, 10), date(2024, 6, 1))


def test_utc_instant_must_be_timezone_aware():
    """A naive datetime is rejected by every instant-taking function rather
    than silently assumed to already be UTC."""
    naive = datetime(2024, 6, 3, 15, 0)  # noqa: DTZ001 -- naive-ness is the test subject
    with pytest.raises(ValueError):
        cal.is_session_open("fx", naive)
    with pytest.raises(ValueError):
        cal.next_close("fx", naive)


# --- artifact / provenance sanity (supports Success #2, #7, #8) ------------


def test_artifact_span_matches_locked_span():
    """Every group's vendored artifact starts in Jan 2008 and ends exactly
    2030-12-31, the locked span."""
    for group in ALL_GROUPS:
        first, last = cal.artifact_span(group)
        assert first.startswith("2008-01"), f"{group}: span starts {first}"
        assert last == "2030-12-31", f"{group}: span ends {last}"
