"""The §6.6 EMA gate must REDDEN on every way the score could be wrong.

The mandate that commissioned this engine asked for two proofs: *"prove by
measurement that changing the config changes the smoothing, and that a
hard-coded span would be caught"*, and *"prove the RANKING reflects realized
productivity per day, not trade count"*. Both are here, and both are driven by
BREAKING A REAL COPY of the shipped engine and running the SHIPPED gate against
the broken tree — never by asserting that a detector function returns True.

Doctrine C.8: no plant touches a production artefact. Every broken engine is
written under `tmp_path`, and the gate is pointed at that home.

## §0a on this file: what would make it pass while measuring nothing?

Five answers, and every one of them is an arm here rather than a note.

  * **The gate could pass the honest engine and also pass every broken one.**
    So every plant arm is a PAIR — the same tree, the same gate, one edit
    apart — and the unbroken half is asserted green in its own test first.

  * **A plant could fail to apply.** `_break` asserts its anchor is present AND
    that the text changed, so a refactor that moves an anchor turns these tests
    red rather than quietly turning them into duplicates of the clean case.

  * **A red could be the WRONG red.** Every plant arm asserts a substring of the
    gate's `detail` — the site or the reason — and never merely
    `status is FAIL`. An exit code is a shared namespace (check contract §18)
    and so is a failing verdict: an import error, a syntax error in the plant
    and the defect all reach `FAIL`.

  * **The span could be proven "config-driven" by a test that never changes the
    config.** So the config is written twice, at two spans, and the SMOOTHING is
    required to differ — not just the stored attribute.

  * **The ranking could be proven by ONE pair.** A rank is a comparison; one
    contender proves the arithmetic and nothing about the ordering. Every
    ranking test drives at least two pairs whose realized-per-day and whose
    trade COUNT point in OPPOSITE directions, and asserts that disagreement
    exists before asserting which way the ranking went.

## The one property whose only real test is killing a process

§12.11 is *boot-loaded, restart-only*. "There is no hot reload" cannot be proven
by calling a function: the claim is about what a LIVE process does when the file
under it changes. `test_the_span_is_boot_loaded_and_only_a_RESTART_moves_it`
starts a real interpreter holding a real engine, rewrites
`risks/scoring.config.json` underneath it, asks the live process for its span
and requires the OLD value, then KILLS it and requires the successor to report
the new one. Both halves matter: without the kill, an engine that simply never
reads the config would pass the first half.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# W0212 (protected-access): this suite measures the GATE, and two of the gate's
# own controls are private by design — `_static_findings` (the non-vacuity
# floor) and `_LEAK_PLANTS` (the anchors every plant arm depends on). A test
# that could only reach the public surface could not assert that the anchors are
# still live, which is the one failure that turns the whole gate into a shrug.
# pylint: disable=protected-access
# Test names spell the OUTCOME. The sys.path bootstrap is repeated per module
# deliberately; one shared helper would let a single edit un-bind several.
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess  # nosec B404 - a REAL second process is the subject (§12.11)
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _extra in (str(REPO / "checks"), str(REPO / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_scoring_ema as gate  # pylint: disable=import-error
from nixscore import ema  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

MON = dt.date(2026, 8, 3)


# ---------------------------------------------------------------------------
# A throwaway home holding a REAL copy of everything the gate reads
# ---------------------------------------------------------------------------


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    """A tree the gate can be pointed at, with a real copy of the engine.

    The gate imports the engine from the home it is given, so a broken copy here
    is genuinely the subject under test — not a monkeypatched attribute on the
    shipped module, which would prove the gate reads a name rather than a tree.
    """
    dst = tmp_path / "nix"
    (dst / "scripts").mkdir(parents=True)
    (dst / "databases" / "schema").mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__")
    for package in ("nixscore", "nixbus"):
        shutil.copytree(
            REPO / "scripts" / package, dst / "scripts" / package, ignore=ignore
        )
    shutil.copy2(REPO / "scripts" / "risk_config.py", dst / "scripts")
    shutil.copytree(REPO / "risks", dst / "risks", ignore=ignore)
    shutil.copy2(REPO / gate.SCHEMA_FILE, dst / gate.SCHEMA_FILE)
    return dst


def _run(nix_home: Path):
    """Run the SHIPPED gate against `nix_home`, with a clean engine import."""
    _purge()
    scripts = str(nix_home / "scripts")
    sys.path.insert(0, scripts)
    try:
        return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))
    finally:
        while scripts in sys.path:
            sys.path.remove(scripts)
        _purge()


def _purge() -> None:
    for name in [m for m in sys.modules if m.startswith(("nixscore", "risk_config"))]:
        del sys.modules[name]


def _break(nix_home: Path, edits: Sequence[tuple[str, str]]) -> None:
    """Textual edits to the COPIED engine, each asserted to have landed."""
    target = nix_home / gate.EMA_MODULE
    text = target.read_text(encoding="utf-8")
    for old, new in edits:
        assert old in text, f"plant anchor {old!r} is not in the copied engine"
        changed = text.replace(old, new, 1)
        assert changed != text, "the plant changed nothing"
        text = changed
    target.write_text(text, encoding="utf-8")


def _red(result, *needles: str) -> None:
    """A FAIL whose detail NAMES the reason — never the status alone (§18)."""
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL, got {result.status}: {result.detail}"
    )
    for needle in needles:
        assert needle in result.detail, (
            f"the gate reddened without naming {needle!r}: {result.detail[:600]}"
        )


# ---------------------------------------------------------------------------
# The unbroken half — asserted first, so every plant below is a PAIR
# ---------------------------------------------------------------------------


def test_the_gate_PASSES_the_engine_as_shipped(home: Path) -> None:
    result = _run(home)
    assert result.status is Status.PASS, result.detail
    assert "all five plant-driven arms proved they can fail" in result.evidence


def test_the_gate_PASSES_the_engine_in_the_REAL_tree() -> None:
    """The shipped tree, not a copy. A green on a fixture is not a green here."""
    _purge()
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail


# ---------------------------------------------------------------------------
# THE SPAN — derived, and actually reaching the arithmetic
# ---------------------------------------------------------------------------


def test_a_span_CARVED_as_a_parameter_default_reddens_the_gate(home: Path) -> None:
    _break(
        home,
        [
            (
                "def alpha_for(span: int) -> float:",
                "def alpha_for(span: int = 10) -> float:",
            )
        ],
    )
    _red(_run(home), "alpha_for(span=)", "carved constant")


def test_an_engine_that_IGNORES_its_config_reddens_the_gate(home: Path) -> None:
    """The plant the AST arm cannot see, which is why both halves exist.

    `cls(span=10)` is a keyword argument, not a binding — no name is bound to a
    literal anywhere, so a purely static scan reports the module clean. Only
    driving the engine from a written config catches it.
    """
    _break(
        home, [("return cls(span=span_days_from_config(root))", "return cls(span=10)")]
    )
    result = _run(home)
    _red(result, "from_config", "The knob is not the span")
    assert "score_ema_span_days=3" in result.detail


def test_the_two_spans_must_actually_SMOOTH_differently(home: Path) -> None:
    """An engine that loads the span honestly and then never uses it."""
    _break(home, [("weight = alpha_for(span)", "weight = alpha_for(10)")])
    _red(_run(home), "ema_over_days", "read and then ignored")


def test_an_INVERTED_span_to_alpha_relation_reddens_the_gate(home: Path) -> None:
    _break(home, [("return 2.0 / (span + 1.0)", "return 1.0 - 2.0 / (span + 1.0)")])
    _red(_run(home), "alpha_for", "must fade faster")


# ---------------------------------------------------------------------------
# UNREALIZED — both doors
# ---------------------------------------------------------------------------


def test_an_engine_that_books_a_FILL_as_realized_reddens_the_gate(home: Path) -> None:
    _break(
        home,
        [
            (
                '{"closed", "protective_exit", "sentinel_flatten"}',
                '{"closed", "protective_exit", "sentinel_flatten", "filled"}',
            ),
            ('        "filled",\n        "signal",', '        "signal",'),
        ],
    )
    _red(_run(home), "never steer capital")


def test_an_engine_that_tolerates_a_MARK_in_the_payload_reddens_the_gate(
    home: Path,
) -> None:
    _break(home, [('"unrealized_pnl",', '"__never_a_real_key__",')])
    _red(_run(home), "_realized_amount", "unrealized_pnl")


def test_an_engine_that_DEFAULTS_an_absent_realized_figure_to_zero_reddens(
    home: Path,
) -> None:
    """The quietest failure in the file, and the reason the refusal exists.

    Nothing in this tree writes `realized_pnl`. An engine that read an absent
    figure as a zero advance would score every pair 0.0, tie every comparison,
    and send every arbitration to FCFS — which is EXACTLY what a healthy cold
    start looks like. Totally blind, and green everywhere.
    """
    _break(
        home,
        [
            ("    if REALIZED_FIELD not in payload:", "    if False:"),
            (
                "    raw = payload[REALIZED_FIELD]",
                "    raw = payload.get(REALIZED_FIELD, 0.0)",
            ),
        ],
    )
    _red(
        _run(home),
        "_realized_amount",
        "blind engine look exactly like a healthy cold start",
    )


def test_the_gate_reddens_when_the_refusal_stops_NAMING_the_reason(home: Path) -> None:
    """§18: a control asserts the reason, so the gate asserts the engine does."""
    _break(
        home,
        [
            (
                "f\"{where}: payload carries {', '.join(leaked)} — an OPEN mark on a \"",
                'f"{where}: refused — an OPEN mark on a "',
            )
        ],
    )
    _red(_run(home), "without naming the offending field")


# ---------------------------------------------------------------------------
# ACTIVITY vs COMPLETED DECISIONS — §6.6:438
# ---------------------------------------------------------------------------


def test_an_engine_that_ranks_TRADE_COUNT_reddens_the_gate(home: Path) -> None:
    _break(
        home,
        [
            (
                "day_map[close.day] = day_map.get(close.day, 0.0) + close.realized",
                "day_map[close.day] = day_map.get(close.day, 0.0) + 1.0",
            )
        ],
    )
    _red(_run(home), "daily_advances", "can't dominate purely by trading more often")


def test_an_engine_that_reduces_to_a_SUM_over_the_window_reddens_the_gate(
    home: Path,
) -> None:
    """Same total, same trade count, different spread — only an EMA separates them."""
    _break(
        home,
        [
            (
                (
                    "    value = advances[first]\n"
                    "    for day in _grid_days(first, through, grid):\n"
                    "        value += weight * (advances.get(day, 0.0) - value)"
                ),
                (
                    "    value = sum(advances.values())\n"
                    "    for day in _grid_days(first, through, grid):\n        pass"
                ),
            )
        ],
    )
    _red(_run(home), "older days fade continuously")


# ---------------------------------------------------------------------------
# THE ABSENT DAY, AND THE DAY GRID
# ---------------------------------------------------------------------------


def test_an_engine_whose_score_never_FADES_reddens_the_gate(home: Path) -> None:
    _break(
        home,
        [
            (
                "value += weight * (advances.get(day, 0.0) - value)",
                "value += weight * (advances.get(day, value) - value)",
            )
        ],
    )
    result = _run(home)
    _red(result, "ema_over_days", "recency is measured in TRADES")
    # THE ORDERING PROPERTY, PINNED. This plant is the SAME edit the gate's own
    # decay control makes, so the control has no anchor left and reports itself
    # blind. A positively-observed defect must still be a FAIL — masking it
    # behind "my instrument cannot self-test" is the reading that loses it.
    assert "control is BLIND" in result.evidence, result.evidence


def test_a_CALENDAR_day_grid_reddens_the_gate(home: Path) -> None:
    """§6.6:442 says TRADING days; a calendar walk folds two extra zeros a week."""
    _break(home, [("    return day.weekday() < 5", "    return True")])
    result = _run(home)
    _red(result, "the grid is inert")
    assert "is_trading_day" in result.detail


# ---------------------------------------------------------------------------
# THE CLASSIFICATION, AND THIN DATA
# ---------------------------------------------------------------------------


def test_an_event_type_the_engine_cannot_CLASSIFY_reddens_the_gate(
    home: Path,
) -> None:
    _break(home, [('        "drift_audit",\n', "")])
    _red(_run(home), "CLASSIFIED_EVENT_TYPES", "drift_audit")


def test_a_score_that_CLAIMS_history_it_does_not_have_reddens_the_gate(
    home: Path,
) -> None:
    _break(
        home,
        [
            (
                "days_observed=len(observed),",
                "days_observed=len(_grid_days(first, through, grid)) + 1,",
            )
        ],
    )
    _red(_run(home), "days_observed", "counts SILENCE as history")


def test_a_ZERO_SEEDED_ema_reddens_the_gate(home: Path) -> None:
    """A zero seed halves a genuine first-day result. §6.6's thin-data caution."""
    _break(
        home, [("    value = advances[first]", "    value = weight * advances[first]")]
    )
    _red(_run(home), "did not exist into its history")


# ---------------------------------------------------------------------------
# THE GATE'S OWN CONTROLS
# ---------------------------------------------------------------------------


def test_a_plant_whose_ANCHOR_is_absent_is_a_loud_failure_not_a_clean_module() -> None:
    """A plant that matched nothing yields a pristine module and a blind arm."""
    source = (REPO / gate.EMA_MODULE).read_text(encoding="utf-8")
    with pytest.raises(gate.PlantFailed) as caught:
        gate.plant(source, [("this_text_is_not_in_the_engine", "x")], "bogus")
    assert "did not apply" in str(caught.value)


def test_the_carved_span_scan_reports_a_scan_over_NOTHING_as_vacuous() -> None:
    findings, seen = gate.carved_span_defects("x = 1\n")
    assert not findings and seen == 0
    assert any(
        "cannot report a carved constant" in f.why for f in gate._static_findings("")
    )


def test_every_plant_the_gate_relies_on_still_has_a_live_anchor() -> None:
    """The gate's five can-fail controls, checked against the shipped source.

    If a refactor moves an anchor the gate degrades to CANNOT_MEASURE rather
    than lying — but it degrades silently across a whole run, so the anchors are
    asserted here where the failure has a name.
    """
    source = (REPO / gate.EMA_MODULE).read_text(encoding="utf-8")
    anchors = [old for _label, edits in gate._LEAK_PLANTS for old, _new in edits]
    anchors += [
        "value += weight * (advances.get(day, 0.0) - value)",
        "days_observed=len(observed),",
        "day_map[close.day] = day_map.get(close.day, 0.0) + close.realized",
    ]
    missing = [a for a in anchors if a not in source]
    assert not missing, f"plant anchors no longer in {gate.EMA_MODULE}: {missing}"


def test_the_gate_DECLARES_the_engine_as_a_subject() -> None:
    assert gate.SUBJECTS == ("scripts/nixscore/ema.py",)
    assert "scripts/nixscore/__init__.py" not in gate.SUBJECTS


def test_the_gate_is_CANNOT_MEASURE_when_the_engine_is_absent(tmp_path: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    empty = tmp_path / "empty"
    (empty / "scripts").mkdir(parents=True)
    result = _run(empty)
    assert result.status is Status.CANNOT_MEASURE, result.detail


# ---------------------------------------------------------------------------
# THE ENGINE ITSELF — arithmetic, refusals, and the ranking
# ---------------------------------------------------------------------------


def _grid(count: int) -> list[dt.date]:
    return gate.grid_days(MON, count)


def _close(pair: tuple[str, str], day: dt.date, amount: float, tag: str = "t"):
    return ema.RealizedClose(
        strategy_id=pair[0],
        symbol=pair[1],
        day=day,
        realized=amount,
        event_type="closed",
        trade_id=tag,
    )


def test_a_silent_day_decays_the_score_by_EXACTLY_one_minus_alpha() -> None:
    days = _grid(6)
    weight = ema.alpha_for(10)
    got = ema.ema_over_days({days[0]: 1000.0}, 10, days[5]).realized_ema
    assert got == pytest.approx(1000.0 * (1.0 - weight) ** 5, abs=1e-9)


def test_a_WEEKEND_costs_ONE_decay_step_and_not_three() -> None:
    friday, monday = dt.date(2026, 8, 7), dt.date(2026, 8, 10)
    assert friday.weekday() == 4 and monday.weekday() == 0
    weight = ema.alpha_for(10)
    trading = ema.ema_over_days({friday: 1000.0}, 10, monday).realized_ema
    calendar = ema.ema_over_days(
        {friday: 1000.0}, 10, monday, grid=lambda _day: True
    ).realized_ema
    assert trading == pytest.approx(1000.0 * (1.0 - weight), abs=1e-9)
    assert calendar == pytest.approx(1000.0 * (1.0 - weight) ** 3, abs=1e-9)
    assert trading != calendar


def test_a_hyperactive_pair_does_NOT_outrank_a_more_productive_one() -> None:
    """§6.6:438, and the two axes are asserted to DISAGREE before it is read."""
    days = _grid(10)
    few = [_close(("s_few", "ES"), d, 500.0, f"f{d}{i}") for d in days for i in (0, 1)]
    many = [
        _close(("s_many", "NQ"), d, 10.0, f"m{d}{i}") for d in days for i in range(40)
    ]
    closes = few + many
    counts = ema.close_counts(closes)
    assert counts[("s_many", "NQ")] == 20 * counts[("s_few", "ES")]
    snapshot = ema.RealizedEmaEngine(span=10).snapshot(closes, days[-1])
    assert snapshot.rows[("s_few", "ES")].rank == 1
    assert snapshot.rows[("s_many", "NQ")].rank == 2
    assert snapshot.rows[("s_few", "ES")].realized_ema == pytest.approx(1000.0)
    assert snapshot.rows[("s_many", "NQ")].realized_ema == pytest.approx(400.0)


def test_identical_TOTALS_and_identical_COUNTS_still_rank_apart() -> None:
    """Only a per-day EMA can separate these; a sum and a count cannot."""
    days = _grid(20)
    spike = [_close(("s_spike", "CL"), days[0], 250.0, f"s{i}") for i in range(20)]
    steady = [_close(("s_steady", "GC"), d, 250.0, f"g{d}") for d in days]
    assert sum(c.realized for c in spike) == sum(c.realized for c in steady)
    assert len(spike) == len(steady)
    scored = ema.score_pairs(spike + steady, 10, days[-1])
    assert (
        scored[("s_steady", "GC")].realized_ema > scored[("s_spike", "CL")].realized_ema
    )


def test_days_observed_counts_REAL_realized_days_and_not_the_calendar() -> None:
    days = _grid(11)
    scored = ema.score_pairs([_close(("s", "ES"), days[0], 1000.0)], 10, days[10])
    assert scored[("s", "ES")].days_observed == 1
    assert scored[("s", "ES")].closes_observed == 1


def test_a_one_day_EMA_IS_that_days_advance_with_no_bias_correction() -> None:
    day = _grid(1)[0]
    assert ema.ema_over_days({day: 777.0}, 10, day).realized_ema == pytest.approx(777.0)


def test_a_FILL_can_never_book_a_realization() -> None:
    day = _grid(1)[0]
    row = {
        "event_id": 1,
        "event_type": "filled",
        "strategy_id": "s",
        "symbol": "ES",
        "trade_id": "t",
        "occurred_at": day,
        "payload": {"realized_pnl": 9999.0},
    }
    assert not ema.realized_closes([row])
    with pytest.raises(ema.UnrealizedLeak, match="filled"):
        ema._one_close(row, ema.is_trading_day)  # pylint: disable=protected-access


def test_a_MARK_alongside_a_realization_refuses_the_row_WHOLE() -> None:
    day = _grid(1)[0]
    row = {
        "event_id": 2,
        "event_type": "closed",
        "strategy_id": "s",
        "symbol": "ES",
        "trade_id": "t",
        "occurred_at": day,
        "payload": {"realized_pnl": 10.0, "mark_to_market": 900.0},
    }
    with pytest.raises(ema.UnrealizedLeak, match="mark_to_market"):
        ema.realized_closes([row])


def test_an_ABSENT_realized_figure_is_refused_and_never_read_as_zero() -> None:
    day = _grid(1)[0]
    row = {
        "event_id": 3,
        "event_type": "closed",
        "strategy_id": "s",
        "symbol": "ES",
        "trade_id": "t",
        "occurred_at": day,
        "payload": {"qty": 1},
    }
    with pytest.raises(ema.MissingRealized, match="realized_pnl"):
        ema.realized_closes([row])


def test_a_realization_that_cannot_be_ATTRIBUTED_to_a_pair_is_refused() -> None:
    day = _grid(1)[0]
    row = {
        "event_id": 4,
        "event_type": "closed",
        "strategy_id": "s",
        "symbol": None,
        "trade_id": "t",
        "occurred_at": day,
        "payload": {"realized_pnl": 10.0},
    }
    with pytest.raises(ema.EmaError, match="keyed on the PAIR"):
        ema.realized_closes([row])


def test_a_realization_stamped_OFF_the_day_grid_is_refused_by_name() -> None:
    saturday = dt.date(2026, 8, 8)
    assert saturday.weekday() == 5
    row = {
        "event_id": 5,
        "event_type": "closed",
        "strategy_id": "s",
        "symbol": "ES",
        "trade_id": "t",
        "occurred_at": saturday,
        "payload": {"realized_pnl": 10.0},
    }
    with pytest.raises(ema.EmaError, match="Saturday"):
        ema.realized_closes([row])


def test_an_event_type_the_engine_has_no_rule_for_is_refused_not_ignored() -> None:
    day = _grid(1)[0]
    row = {
        "event_id": 6,
        "event_type": "invented_by_a_later_arc",
        "strategy_id": "s",
        "symbol": "ES",
        "trade_id": "t",
        "occurred_at": day,
        "payload": {"realized_pnl": 10.0},
    }
    assert not ema.realized_closes([row])
    with pytest.raises(ema.EmaError, match="no realization rule"):
        ema._one_close(row, ema.is_trading_day)  # pylint: disable=protected-access


def test_the_classification_PARTITIONS_the_frozen_schema_enum() -> None:
    members = gate.schema_enum_members(
        (REPO / gate.SCHEMA_FILE).read_text(encoding="utf-8")
    )
    assert len(members) >= gate.MIN_ENUM_MEMBERS
    assert members == ema.CLASSIFIED_EVENT_TYPES
    assert not ema.REALIZING_EVENT_TYPES & ema.NON_REALIZING_EVENT_TYPES


def test_an_EMPTY_history_is_an_ABSENT_score_and_never_a_low_one() -> None:
    with pytest.raises(ema.EmaError, match="ABSENT"):
        ema.ema_over_days({}, 10, MON)


def test_an_as_of_day_BEFORE_the_last_close_is_refused() -> None:
    days = _grid(3)
    with pytest.raises(ema.EmaError, match="has not happened yet"):
        ema.ema_over_days({days[2]: 1.0}, 10, days[0])


def test_a_NON_POSITIVE_span_is_refused_rather_than_inverting_the_ranking() -> None:
    with pytest.raises(ema.EmaError, match="not a smoothing window"):
        ema.alpha_for(0)


def test_a_MIS_STAMPED_occurred_at_is_refused_rather_than_walked() -> None:
    with pytest.raises(ema.EmaError, match="mis-stamped"):
        ema.ema_over_days({dt.date(1970, 1, 1): 1.0}, 10, dt.date(2026, 8, 3))


def test_a_timestamp_is_read_as_UTC_whatever_shape_it_arrives_in() -> None:
    want = dt.date(2026, 8, 3)
    assert ema.trading_day("2026-08-03 15:00:00+00") == want
    assert ema.trading_day("2026-08-03T15:00:00+00:00") == want
    assert ema.trading_day("2026-08-03") == want
    assert ema.trading_day(dt.datetime(2026, 8, 3, 15, 0, tzinfo=dt.UTC)) == want
    assert ema.trading_day(want) == want
    # A late-session close in a +14 zone is still ITS OWN utc day, not the local one.
    tz = dt.timezone(dt.timedelta(hours=14))
    assert ema.trading_day(dt.datetime(2026, 8, 4, 10, 0, tzinfo=tz)) == want


def test_the_top_verb_folds_LOG_ROWS_straight_to_a_publishable_snapshot() -> None:
    """`snapshot_from_log` is the whole path, and the fills in it are DROPPED."""
    days = _grid(2)
    rows = [
        {
            "event_id": i,
            "event_type": kind,
            "strategy_id": "s",
            "symbol": "ES",
            "trade_id": f"t{i}",
            "occurred_at": days[0],
            "payload": payload,
        }
        for i, (kind, payload) in enumerate(
            (
                ("filled", {"qty": 1, "price": 5000.0}),
                ("closed", {"realized_pnl": 400.0}),
                ("signal", {}),
                ("closed", {"realized_pnl": 100.0}),
            )
        )
    ]
    snapshot = ema.RealizedEmaEngine(span=10).snapshot_from_log(rows, days[0])
    row = snapshot.rows[("s", "ES")]
    # 400 + 100, ONE advance for the day — and the fill contributed nothing.
    assert row.realized_ema == pytest.approx(500.0)
    assert row.days_observed == 1
    assert row.rank == 1


def test_the_snapshot_carries_the_ENGINES_span_onto_the_wire() -> None:
    day = _grid(1)[0]
    snapshot = ema.RealizedEmaEngine(span=7).snapshot(
        [_close(("s", "ES"), day, 1.0)], day
    )
    assert snapshot.span_days == 7
    assert snapshot.writer_identity == "scoring"


# ---------------------------------------------------------------------------
# §12.11 — BOOT-LOADED, RESTART-ONLY. The arm that needs a real process.
# ---------------------------------------------------------------------------

_DRIVER = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from nixscore.ema import RealizedEmaEngine
engine = RealizedEmaEngine.from_config(Path(sys.argv[1]))
print("SPAN", engine.span, flush=True)
for line in sys.stdin:
    if line.strip() == "span":
        print("SPAN", engine.span, flush=True)
    elif line.strip() == "quit":
        break
"""


def _set_span(nix_home: Path, span: int) -> None:
    path = nix_home / gate.SCORING_CONFIG
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["score_ema_span_days"] = span
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _start(driver: Path, nix_home: Path) -> subprocess.Popen:
    return subprocess.Popen(  # nosec B603 - fixed argv, no shell
        [sys.executable, str(driver), str(nix_home), str(nix_home / "scripts")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _ask(proc: subprocess.Popen) -> int:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write("span\n")
    proc.stdin.flush()
    return int(proc.stdout.readline().split()[1])


def test_the_span_is_boot_loaded_and_only_a_RESTART_moves_it(
    home: Path, tmp_path: Path
) -> None:
    """§12.11: no hot reload. Proven against a LIVE process, then a kill.

    The first half alone is passable by an engine that never reads the config at
    all — so the kill is not decoration, it is the half that makes the first
    half mean something.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    _set_span(home, 11)

    proc = _start(driver, home)
    try:
        assert proc.stdout is not None
        assert int(proc.stdout.readline().split()[1]) == 11
        _set_span(home, 4)
        # The file on disk has genuinely changed under the running process.
        assert (
            json.loads((home / gate.SCORING_CONFIG).read_text())["score_ema_span_days"]
            == 4
        )
        time.sleep(0.2)
        assert _ask(proc) == 11, (
            "a LIVE process saw its span change when the file changed — §12.11 "
            "is boot-loaded, restart-only, because a mid-session change would "
            "let two decisions inside one open trade read different tunables"
        )
    finally:
        proc.kill()
        proc.wait(timeout=10)

    assert proc.returncode is not None, "the process did not actually die"
    successor = _start(driver, home)
    try:
        assert successor.stdout is not None
        assert int(successor.stdout.readline().split()[1]) == 4, (
            "a RESTARTED process still reported the old span — the config is "
            "not being read at boot either, so the first half proved nothing"
        )
    finally:
        successor.kill()
        successor.wait(timeout=10)


#: The same driver with a HOT-RELOAD engine — it rebuilds from config on every
#: ask. It exists to prove the arm above can SEE a hot reload; without it, a
#: driver that had silently stopped answering would produce the same green.
_HOT_DRIVER = _DRIVER.replace(
    'print("SPAN", engine.span, flush=True)\n    elif',
    'print("SPAN", RealizedEmaEngine.from_config(Path(sys.argv[1])).span, flush=True)\n    elif',
)


def test_the_restart_arm_can_SEE_a_hot_reload(home: Path, tmp_path: Path) -> None:
    """Both halves for the process arm: drive an engine that DOES hot-reload."""
    assert _HOT_DRIVER != _DRIVER, "the hot-reload plant changed nothing"
    driver = tmp_path / "hot.py"
    driver.write_text(_HOT_DRIVER, encoding="utf-8")
    _set_span(home, 11)
    proc = _start(driver, home)
    try:
        assert proc.stdout is not None
        assert int(proc.stdout.readline().split()[1]) == 11
        _set_span(home, 4)
        assert _ask(proc) == 4, (
            "a deliberately hot-reloading process reported the OLD span — the "
            "arm above cannot see a hot reload, so its green is blind"
        )
    finally:
        proc.kill()
        proc.wait(timeout=10)
