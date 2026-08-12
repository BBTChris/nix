"""ARC 028 / D — the standing gate over `risks/`, driven.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then plants
that must FAIL and NAME their site, then the plants removed and the same
population passing. A demonstration missing the last step shows only that a gate
can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the real `risks/` tree,
the real frozen spec and the real validators, perturbs the copy, and drives the
SHIPPED gate against it. The real files are read and never written.

**Every control asserts the REASON** — the site and the named condition — never
the exit code alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_risks_data_only as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: Everything the gate reads outside `risks/` itself.
_COPIED = (
    "docs/nics_risk_subsystem_spec_v1.3.md",
    "scripts/risk_config.py",
    "scripts/broker/broker_order_config.py",
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of risks/, the spec and the validators."""
    shutil.copytree(REPO / gate.RISKS, tmp_path / gate.RISKS)
    for rel in _COPIED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _config(home: Path, module: str) -> Path:
    return home / gate.RISKS / f"{module}{gate.CONFIG_SUFFIX}"


def _edit(home: Path, module: str, mutate) -> None:
    """Apply `mutate` to one copied config's parsed JSON and write it back."""
    path = _config(home, module)
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real reference side and a real subject
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_compared() -> None:
    """The credibility floor: both sides non-empty, and the counts are evidence."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "§12A knobs 29 == homes 29" in result.evidence, result.evidence
    assert "config file(s)" in result.evidence, result.evidence
    assert "stated default(s) compared" in result.evidence, result.evidence


def test_the_KNOB_SET_is_PARSED_FROM_THE_SPEC_and_is_not_a_constant_here() -> None:
    """If the expected set were hardcoded, editing §12A could not move it."""
    parsed, complaint = gate.spec_knobs(REPO)

    assert complaint == "", complaint
    assert len(parsed) == 29, sorted(parsed)
    assert "PENDING_ACK_TIMEOUT_MS" in parsed, sorted(parsed)
    assert "PER_TRADE_RISK_$" in parsed, sorted(parsed)
    source = Path(gate.__file__).read_text(encoding="utf-8")
    for knob in sorted(parsed):
        assert knob not in source, (
            f"{knob} appears as a literal in the gate's own source — the "
            "expected side would then be a constant, and the comparison would "
            "be the gate agreeing with itself"
        )
    assert "29" not in source, (
        "the derived knob count appears as a literal in the gate's own source"
    )


def test_ADDING_A_KNOB_TO_THE_SPEC_MOVES_THE_DERIVED_SET(home: Path) -> None:
    """The derivation proven by MOVING the source, not by reading the code."""
    spec = home / gate.SPEC
    before, _ = gate.spec_knobs(home)
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "- `SCORE_EMA_SPAN_DAYS` = 10",
            "- `TOTALLY_NEW_KNOB` — invented by this control.\n"
            "- `SCORE_EMA_SPAN_DAYS` = 10",
        ),
        encoding="utf-8",
    )

    after, complaint = gate.spec_knobs(home)

    assert complaint == "", complaint
    assert after - before == {"TOTALLY_NEW_KNOB"}, sorted(after - before)


def test_the_STATED_DEFAULTS_are_PARSED_FROM_THE_SPEC_too() -> None:
    """The drift arm's reference side is the frozen file, not a table here."""
    defaults = gate.spec_defaults(REPO)

    assert len(defaults) >= gate.MIN_SPEC_DEFAULTS, sorted(defaults)
    assert defaults["EOD_BLACKOUT_MIN"] == 20, defaults
    assert defaults["DEPLOYABLE_PCT"] == 0.70, defaults


# --------------------------------------------------------------------------
# THE PLANTS — each must FAIL, and NAME the site and the condition
# --------------------------------------------------------------------------


def test_a_PYTHON_FILE_IN_RISKS_fails_and_NAMES_IT(home: Path) -> None:
    """The bluntest route to behaviour in a data directory."""
    (home / gate.RISKS / "sizing_rule.py").write_text(
        "def deny(order):\n    return order.qty > 5\n", encoding="utf-8"
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risks/sizing_rule.py" in result.site, result.site
    assert "risks/ holds data" in result.detail, result.detail


def test_a_SUBDIRECTORY_IN_RISKS_fails_and_NAMES_IT(home: Path) -> None:
    """A tree is where a package hides."""
    (home / gate.RISKS / "rules").mkdir()

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risks/rules" in result.site, result.site
    assert "a subdirectory in risks/" in result.detail, result.detail


def test_a_RULE_EXPRESSION_SMUGGLED_INTO_A_VALUE_fails_and_NAMES_THE_KEY(
    home: Path,
) -> None:
    """THE headline hazard: an eval'able rule expression wearing a knob's name."""
    _edit(
        home,
        "limiter",
        lambda raw: raw.__setitem__(
            "netliq_safety_pad", "lambda pic: pic.balance * 0.25"
        ),
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risks/limiter.config.json:netliq_safety_pad" in result.site, result.site
    assert "may only be a number" in result.detail, result.detail
    assert "eval'able rule" in result.detail, result.detail


def test_a_CODE_PATH_KEY_HIDDEN_INSIDE_A_MAP_fails_and_NAMES_THE_LEAF(
    home: Path,
) -> None:
    """A string one level down is still a string in value position."""
    _edit(
        home,
        "allocator",
        lambda raw: raw["bucket_cap_pct"].__setitem__("equities", "use_legacy_cap"),
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "bucket_cap_pct.equities" in result.site, result.site
    assert "may only be a number" in result.detail, result.detail


def test_a_KNOB_WITH_NO_DERIVATION_fails_and_says_its_SEMANTICS_ARE_SETTLED_HERE(
    home: Path,
) -> None:
    """A knob with no stated origin has its meaning decided in risks/."""
    _edit(home, "scoring", lambda raw: raw["_derivations"].pop("score_ema_span_days"))

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risks/scoring.config.json:score_ema_span_days" in result.site, result.site
    assert "second authority risks/ may not become" in result.detail, result.detail


def test_a_FABRICATED_CITATION_fails_because_THE_CITED_LINE_IS_READ(
    home: Path,
) -> None:
    """A `§12A:<line>` that the frozen document does not carry is prose."""
    _edit(
        home,
        "supervision",
        lambda raw: raw["_derivations"].__setitem__(
            "crash_loop_max", "§12A:805 `CRASH_LOOP_MAX` = 3 restarts, stated outright."
        ),
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risks/supervision.config.json:crash_loop_max" in result.site, result.site
    assert "does not carry that name" in result.detail, result.detail


def test_a_CITATION_POINTING_OUTSIDE_THE_SECTION_fails_and_NAMES_THE_SPAN(
    home: Path,
) -> None:
    """§12A:<line> must land inside §12A, or the coordinate names another section."""
    _edit(
        home,
        "supervision",
        lambda raw: raw["_derivations"].__setitem__(
            "crash_loop_window_min", "§12A:272 `CRASH_LOOP_WINDOW` — window."
        ),
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "outside §12A's own span" in result.detail, result.detail


def test_a_SECOND_PHYSICAL_HOME_FOR_ONE_KNOB_fails_and_NAMES_BOTH(
    home: Path,
) -> None:
    """The exact regression the ARC 020 obligation was about: two files, one knob,
    and a disagreement neither of them can see."""

    def mirror(raw: dict) -> None:
        raw["pending_ack_timeout_ms"] = 2000
        raw["_derivations"]["pending_ack_timeout_ms"] = (
            "§12A:830 `PENDING_ACK_TIMEOUT_MS` — mirrored here for convenience."
        )

    _edit(home, "broker_order", mirror)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "pending_ack_timeout_ms" in result.site, result.site
    assert "SECOND physical home" in result.detail, result.detail
    # BOTH files are named, and which one the gate calls "second" is alphabetical
    # rather than meaningful — the finding is that two exist, not that one of
    # them is the intruder, and the message has to leave that judgment open.
    assert "risks/limiter.config.json" in result.detail, result.detail
    assert "risks/broker_order.config.json" in result.detail, result.detail
    assert "`PENDING_ACK_TIMEOUT_MS`" in result.detail, result.detail


def test_a_SPEC_KNOB_WITH_NO_HOME_fails_and_NAMES_THE_KNOB(home: Path) -> None:
    """A tunable the spec owns with nowhere to live is a literal waiting to be
    typed into code."""
    _edit(home, "scoring", lambda raw: raw.pop("score_ema_span_days"))
    _edit(home, "scoring", lambda raw: raw["_derivations"].pop("score_ema_span_days"))

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SCORE_EMA_SPAN_DAYS" in result.detail, result.detail
    assert "no file in risks/ lands it" in result.detail, result.detail


def test_a_DRIFTED_DEFAULT_fails_and_QUOTES_BOTH_NUMBERS(home: Path) -> None:
    """§12A states some values outright; the physical layout may not change them."""
    _edit(home, "limiter", lambda raw: raw.__setitem__("eow_blackout_min", 45))

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risks/limiter.config.json:eow_blackout_min" in result.site, result.site
    assert (
        "is 45, but §12A states `EOW_BLACKOUT_MIN` = 30.0 outright" in result.detail
    ), result.detail


def test_a_DECLARED_RULE_NOTHING_IMPLEMENTS_fails_and_NAMES_THE_ID(
    home: Path,
) -> None:
    """A `_boot_validation` list nothing executes is documentation."""
    _edit(
        home,
        "supervision",
        lambda raw: raw["_boot_validation"].append(
            {"id": "ordering.invented", "why": "looks rigorous", "spec": "§12A:801"}
        ),
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "_boot_validation.ordering.invented" in result.site, result.site
    assert "documentation wearing a rule's clothes" in result.detail, result.detail


def test_a_RULE_THAT_RUNS_AND_IS_DECLARED_NOWHERE_fails(home: Path) -> None:
    """The other direction: a rule nobody reading the config could find."""
    _edit(
        home,
        "scoring",
        lambda raw: raw.__setitem__(
            "_boot_validation",
            [
                entry
                for entry in raw["_boot_validation"]
                if entry["id"] != "positive.scalars"
            ],
        ),
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "does not declare `positive.scalars`" in result.detail, result.detail


def test_a_SHIPPED_SET_THAT_VIOLATES_ITS_OWN_RULES_fails_and_NAMES_THE_RULE(
    home: Path,
) -> None:
    """ARM 4's other half: the validator is RUN, not merely cross-referenced."""
    _edit(home, "limiter", lambda raw: raw.__setitem__("go_timeout_s", 1))

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "do not satisfy their own declared boot validation" in result.detail, (
        result.detail
    )
    assert "liveness.go_timeout_outlasts_pending_ack" in result.detail, result.detail


def test_a_RELOAD_VERB_IN_A_VALIDATOR_fails_and_CITES_THE_LIFECYCLE_LOCK(
    home: Path,
) -> None:
    """§12.11: boot-loaded, restart-only. A reload verb is how that stops holding."""
    loader = home / "scripts" / "risk_config.py"
    loader.write_text(
        loader.read_text(encoding="utf-8") + "\n\ndef reload_risk_configs(root=None):\n"
        '    """Re-read the configs mid-session."""\n'
        "    return load_risk_configs(root)\n",
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "reload_risk_configs" in result.site, result.site
    assert "boot-loaded, restart-only" in result.detail, result.detail


def test_a_VALIDATOR_THAT_WATCHES_ITS_FILE_fails_on_the_IMPORT(home: Path) -> None:
    """An import is enough: a loader that can be signalled can hot-reload."""
    loader = home / "scripts" / "risk_config.py"
    loader.write_text(
        "import signal\n" + loader.read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "imports signal" in result.detail, result.detail


def test_an_MTIME_LITERAL_IN_A_VALIDATOR_fails_and_NAMES_THE_LITERAL(
    home: Path,
) -> None:
    """The third §12.11 route, and it is the quiet one: a loader that grows a
    `st_mtime` comparison is watching its own file without importing anything."""
    loader = home / "scripts" / "risk_config.py"
    loader.write_text(
        loader.read_text(encoding="utf-8") + '\n\n_FRESHNESS_FIELD = "st_mtime"\n',
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "carries the literal 'st_mtime'" in result.detail, result.detail
    assert "starts watching itself" in result.detail, result.detail


def test_a_VALIDATOR_NAMED_BY_A_CONFIG_AND_NOT_ON_DISK_fails(home: Path) -> None:
    """ARM 4's other absent side: a `validated_by` pointing at nothing means the
    declared rule ids correspond to nothing that could run."""
    (home / "scripts" / "risk_config.py").unlink()

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "is named as a validator and is not on disk" in result.detail, result.detail


def test_a_VALIDATOR_READING_A_DOCUMENTATION_KEY_fails_and_NAMES_IT(
    home: Path,
) -> None:
    """Prose must never become load-bearing: rewording a comment may not change
    behaviour."""
    loader = home / "scripts" / "risk_config.py"
    loader.write_text(
        loader.read_text(encoding="utf-8") + "\n\ndef _origin(raw):\n"
        '    """Read the file\'s own documentation as if it were config."""\n'
        '    return raw["_derivations"]\n',
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "reads documentation key '_derivations'" in result.detail, result.detail


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent or tiny scope is not agreement
# --------------------------------------------------------------------------


def test_a_RENAMED_SECTION_12A_is_CANNOT_MEASURE_and_NEVER_a_PASS(
    home: Path,
) -> None:
    """§5.3: an empty scope is never a PASS. The gate must say it lost its side."""
    spec = home / gate.SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "## 12A. Configuration Parameters", "## 12Z. Configuration Parameters"
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "no '## 12A.' heading" in result.detail, result.detail
    assert "compare green against anything" in result.detail, result.detail


def test_an_ABSENT_RISKS_DIRECTORY_is_CANNOT_MEASURE(home: Path) -> None:
    """A gate whose subject is gone measured nothing (§17)."""
    shutil.rmtree(home / gate.RISKS)

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "is not a directory" in result.detail, result.detail


def test_a_NEARLY_EMPTY_RISKS_DIRECTORY_is_CANNOT_MEASURE_not_a_TRIVIAL_PASS(
    home: Path,
) -> None:
    """The §0a hazard named in this arc's brief: a no-behaviour gate over an
    empty directory passes while measuring nothing."""
    for path in sorted((home / gate.RISKS).glob("*.config.json"))[1:]:
        path.unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert f"below the floor of {gate.MIN_CONFIG_FILES}" in result.detail, result.detail
    assert "passes trivially" in result.detail, result.detail


def test_a_TRUNCATED_SECTION_12A_is_CANNOT_MEASURE_naming_the_KNOB_FLOOR(
    home: Path,
) -> None:
    """A parse that stopped matching must say so rather than report agreement."""
    spec = home / gate.SPEC
    text = spec.read_text(encoding="utf-8")
    start = text.index("## 12A. Configuration Parameters")
    end = text.index("## 12B.")
    spec.write_text(
        text[:start]
        + "## 12A. Configuration Parameters\n\n- `LONELY_KNOB` — the only one left.\n\n"
        + text[end:],
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert f"below the floor of {gate.MIN_SPEC_KNOBS}" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_SAME_COPIED_TREE_passes_once_every_plant_is_gone(home: Path) -> None:
    """Without this the gate is only known to be able to fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "§12A knobs 29 == homes 29" in result.evidence, result.evidence


def test_the_GATE_DECLARES_its_new_artifacts_as_SUBJECTS_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent."""
    for rel in (
        "risks/allocator.config.json",
        "risks/limiter.config.json",
        "risks/scoring.config.json",
        "risks/staleness.config.json",
        "risks/supervision.config.json",
        "scripts/risk_config.py",
    ):
        assert rel in gate.SUBJECTS, gate.SUBJECTS
    assert "risks/broker_order.config.json" not in gate.SUBJECTS, (
        "declaring the ARC 020 config here would redden the coverage ratchet's "
        "stale-baseline arm, whose repair is a shrink of a file this arc does "
        "not own — the situation is a CHECK-DEBT row, not a silent declaration"
    )
    assert gate.CORRECTABLE is False, "the frozen spec is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"
