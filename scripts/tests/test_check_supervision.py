"""ARC 034 / sub-agent C — the can-fail suite for `checks/check_supervision.py`.

Structure follows the `check_flatten` precedent (`nix_check_contract.md` §5.1):
non-vacuity FIRST (the real tree passes and the evidence names what was driven),
then plants that must FAIL and NAME their site.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the subject and its
collaborators, perturbs the COPY, and drives the SHIPPED gate's own bytes
against it. `scripts/nixrisk/supervision.py` is read and never written here.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_supervision as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

COPIED = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/supervision.py",
    "scripts/nixrisk/halt.py",
    "scripts/nixrisk/seam.py",
    "scripts/risk_config.py",
    "scripts/nix_crash_loop_halt.py",
    "scripts/nix-supervision.conf",
    "scripts/nix-crash-loop-halt@.service",
    "scripts/nixsentinel/__init__.py",
    "scripts/nixsentinel/config.py",
)

#: The `risks/` half of the manifest, DERIVED rather than enumerated — and the
#: change is a measured one, not a tidy-up. This tuple used to name five configs
#: by hand and was correct for the tree it was written against; ARC 034's
#: sub-agent B then added `risks/sentinel.config.json` and widened
#: `risk_config.OWNED_MODULES` in a parallel worktree, so on the merged tree the
#: scratch home was missing a config the validator requires and the CONTROL went
#: CANNOT_MEASURE — before a single plant had been applied.
#:
#: The authority for which configs must exist is `risk_config.OWNED_MODULES`, not
#: a list in a test file, so this reads the directory. That is deliberately NOT
#: the same call as deriving an expected VALUE from the subject: nothing here is
#: asserted against, it is only what gets copied into the venue, so the gate's
#: own findings stay independent of it.
_RISK_CONFIGS = tuple(
    f"risks/{path.name}" for path in sorted((REPO / "risks").glob("*.json"))
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the breaker, its knobs and its units."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "risks").mkdir(parents=True)
    (tmp_path / "scripts" / "nixsentinel").mkdir(parents=True)
    for rel in (*COPIED, *_RISK_CONFIGS):
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> None:
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _red(result, *, site: str, phrase: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert site in (result.site or ""), result.site
    assert phrase in (result.detail or ""), result.detail


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_FOUR_arms() -> None:
    """Non-vacuity first: the shipped tree is green, and the evidence names what
    was actually driven — including the two things a green must NOT imply."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "DRIVEN TO A TRIP" in result.evidence, result.evidence
    assert "boundary instant driven from BOTH sides" in result.evidence
    assert "declare NO HALT" in result.evidence
    assert "REAL subprocesses" in result.evidence
    assert "installed, enabled, started and reloaded nothing" in result.evidence
    # RE-POINTED ARC 037 (D3.252): the boundary used to read "ARC R5 … Scoring
    # does not exist in this tree", which stopped being true when
    # scripts/nixscore/ exists. What is absent now is the JOIN, and that is the
    # phrase this assertion holds the evidence to.
    assert "NO JOIN" in result.evidence, "the scoring boundary is not printed"
    assert "ScoreStore.archive_strategy" in result.evidence, result.evidence


def test_the_COPIED_TREE_also_passes_so_every_plant_below_starts_GREEN(
    home: Path,
) -> None:
    """Non-vacuity for the fixture itself: a plant that reddens a tree that was
    already red measures the fixture, not the plant."""
    assert _run(home).status is Status.PASS, _run(home)


def test_the_GATE_DECLARES_EVERY_new_artifact_as_a_SUBJECT() -> None:
    """The artifact-coverage ratchet FAILs on an artifact no check declares."""
    for rel in (
        "scripts/nixrisk/supervision.py",
        "scripts/nix_crash_loop_halt.py",
        "risks/supervision.config.json",
    ):
        assert rel in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON


# --------------------------------------------------------------------------
# PLANT 1 — the cap never fires
# --------------------------------------------------------------------------


def test_a_BREAKER_THAT_NEVER_TRIPS_fails_and_NAMES_the_cap(home: Path) -> None:
    """§12.2:617's whole consequence removed. This is the plant a gate that only
    counted to two would miss entirely."""
    _plant(
        home,
        "scripts/nixrisk/supervision.py",
        "        tripped = len(counted) >= self._knobs.crash_loop_max",
        "        tripped = False  # PLANTED: the cap never fires",
    )

    result = _run(home)

    _red(result, site="cap", phrase="did NOT trip the breaker")


def test_a_BREAKER_THAT_COUNTS_BUT_NEVER_HALTS_fails(home: Path) -> None:
    """The cap fires and the money never stops — 'blind restart-into-trading with
    a log line'. The verdict still says tripped, so only reading the §12.5 CAUSE
    off the HALT sink catches it."""
    _plant(
        home,
        "scripts/nixrisk/supervision.py",
        "            self._halt.set(HaltCause.CRASH_LOOP, verdict.reason, now=stamp)",
        "            pass  # PLANTED: counted, never halted",
    )

    result = _run(home)

    _red(result, site="cap", phrase="no §12.5 HALT was declared")


# --------------------------------------------------------------------------
# PLANT 2 — the window is removed
# --------------------------------------------------------------------------


def test_a_WINDOWLESS_BREAKER_fails_and_NAMES_the_missing_window(home: Path) -> None:
    """A breaker that counts every restart EVER would quarantine a strategy that
    crashed once a month for three months. The window is the whole tunable."""
    _plant(
        home,
        "scripts/nixrisk/supervision.py",
        "        floor = max(\n"
        "            now - self._knobs.window_s, "
        'self._floors.get(subject, float("-inf"))\n'
        "        )",
        '        floor = self._floors.get(subject, float("-inf"))  # PLANTED',
    )

    result = _run(home)

    _red(result, site="window", phrase="that is a breaker with no window")


def test_an_INCLUSIVE_BOUNDARY_fails_because_the_window_is_HALF_OPEN(
    home: Path,
) -> None:
    """The boundary instant, planted. `since` is changed from `>` to `>=`, so a
    restart EXACTLY `window_s` old still counts — a crash loop could then walk
    out of its own window one second at a time and never leave it."""
    _plant(
        home,
        "scripts/nixrisk/supervision.py",
        "            if rec.subject == subject and rec.ts > floor_ts",
        "            if rec.subject == subject and rec.ts >= floor_ts",
    )

    result = _run(home)

    _red(result, site="boundary", phrase="the window is HALF-OPEN")


# --------------------------------------------------------------------------
# PLANT 3 — the quarantine
# --------------------------------------------------------------------------


def test_a_QUARANTINE_WITH_NO_ALERT_fails(home: Path) -> None:
    """§4:273 — 'quarantined ... alert raised'. The strategy is left dead and the
    operator is never told."""
    _plant(
        home,
        "scripts/nixrisk/supervision.py",
        '                "supervision.quarantine",',
        '                "supervision.silent",  # PLANTED',
    )

    result = _run(home)

    _red(result, site="quarantine", phrase="no quarantine alert")


def test_a_STRATEGY_BREAKER_THAT_ACCEPTS_A_HALT_FLAG_fails(home: Path) -> None:
    """§4:273 inverted: one strategy's crash loop would stop the whole platform.
    The refusal is at CONSTRUCTION, so removing it is removing the rule."""
    _plant(
        home,
        "scripts/nixrisk/supervision.py",
        "        if scope is BreakerScope.STRATEGY and halt is not None:",
        "        if False:  # PLANTED: the mis-wiring is accepted",
    )

    result = _run(home)

    _red(result, site="wiring", phrase="was ACCEPTED")


# --------------------------------------------------------------------------
# PLANT 4 — the systemd policy and the actuator
# --------------------------------------------------------------------------


def test_a_DROP_IN_THAT_DISAGREES_WITH_THE_KNOBS_fails(home: Path) -> None:
    """Both sides derived: systemd's own limiter and the §12.2 breaker must count
    to the SAME numbers, or whichever fires first decides."""
    _plant(
        home,
        "scripts/nix-supervision.conf",
        "StartLimitBurst=3",
        "StartLimitBurst=7",
    )

    result = _run(home)

    _red(
        result,
        site="nix-supervision.conf",
        phrase="count to different numbers",
    )


def test_a_DROP_IN_THAT_LETS_SYSTEMD_TAKE_THE_CONSEQUENCE_fails(home: Path) -> None:
    """§12.2:617's consequence is HALT + operator alert, and systemd can declare
    neither. `StartLimitAction=reboot` is a supervisor choosing the outcome."""
    _plant(
        home,
        "scripts/nix-supervision.conf",
        "StartLimitAction=none",
        "StartLimitAction=reboot",
    )

    result = _run(home)

    _red(result, site="nix-supervision.conf", phrase="expected 'none'")


def test_an_ACTUATOR_WITH_AN_IN_MEMORY_COUNTER_fails_ACROSS_PROCESSES(
    home: Path,
) -> None:
    """The counter must survive the crash it counts. Planting a fresh ledger path
    per invocation is exactly what an in-process counter looks like from the
    outside: every run reports one restart, forever."""
    _plant(
        home,
        "scripts/nix_crash_loop_halt.py",
        "    ledger = RestartLedger(args.ledger or (home / DEFAULT_LEDGER))",
        "    import uuid  # PLANTED: a fresh ledger per process\n"
        "    ledger = RestartLedger(\n"
        "        f'{args.ledger or (home / DEFAULT_LEDGER)}.{uuid.uuid4().hex}'\n"
        "    )",
    )

    result = _run(home)

    _red(result, site=gate.ACTUATOR_FILE, phrase="SEPARATE processes")


def test_an_ACTUATOR_THAT_WRITES_NO_HALT_MARKER_fails(home: Path) -> None:
    """§12.5:634-638: the Limiter may BE the crash-looping process, so the marker
    is the only record cold-start reconciliation can replay."""
    _plant(
        home,
        "scripts/nix_crash_loop_halt.py",
        "        marker.record_set("
        "HaltCause.CRASH_LOOP, reason, now, seq, current_boot_id())",
        "        pass  # PLANTED: no marker",
    )

    result = _run(home)

    _red(result, site=gate.ACTUATOR_FILE, phrase="NO §12.5:634-638 HALT marker")


# --------------------------------------------------------------------------
# The gate's own failure modes
# --------------------------------------------------------------------------


def test_a_MISSING_SUBJECT_is_CANNOT_MEASURE_and_never_a_PASS(tmp_path: Path) -> None:
    """§17: a safety property proven while its subject is unavailable is not
    proven. The absence must NEVER read as green."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot load the §12.2 supervision subject" in (result.detail or "")


def test_no_plant_touched_the_repository() -> None:
    """Doctrine C.8, asserted rather than promised: the live tree is still green."""
    assert _run(REPO).status is Status.PASS
