"""ARC 033 / 1C -- the can-fail suite for `checks/check_staleness.py`.

**THE REQUIREMENT THIS FILE EXISTS TO SATISFY:** prove the gate actually
reddens on a real defect in EACH declared arm, and that each red NAMES THE
REASON -- the site and the condition -- never the exit code or the status alone
(check contract v2 rule 11 / §18).

**No plant touches a production artifact** (doctrine C.8). Every control builds
a throwaway `nix_home` under `tmp_path` carrying a COPY of `scripts/nixrisk/`
and `risks/`, perturbs the COPY, and drives the SHIPPED gate's own bytes
against it. Each plant is followed IN THE SAME TEST by a restore-and-re-run
control, so an ambient cause could not have produced the red.

**THE TWO HEADLINE PLANTS ARE EACH OTHER'S CONTROL**, because that pairing is
the whole point of the gate:

* `test_a_detector_that_never_blocks_reddens` is ARC 022 F17 itself -- the
  detector agrees with a dead feed. A gate that only proved "staleness fires"
  would pass F17, because F17 fired on plenty of things.
* `test_a_detector_that_always_blocks_reddens` is the mirror image -- a slow
  feed halted as though it were dead. A gate that only proved "staleness does
  not over-fire" would pass a detector that never fires.

A suite with one of them measures half, and it is the half that lets a correct
feed flatten a healthy book.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
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
# APPENDED, never inserted at the front -- loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_staleness as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

FRESHNESS = "scripts/nixrisk/freshness.py"
CONFIG = "risks/staleness.config.json"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of `scripts/nixrisk/` and `risks/`."""
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _subject(home: Path) -> Path:
    return home / FRESHNESS


def _plant(home: Path, old: str, new: str) -> str:
    """Swap one exact fragment in the COPY, returning the pristine source.

    The replacement is asserted to have landed. A plant that silently matched
    nothing produces a green that looks like a control and proves nothing --
    the same vacuity this whole file is about, one level up.
    """
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    assert old in pristine, f"plant fragment not found in {FRESHNESS}: {old!r}"
    path.write_text(pristine.replace(old, new, 1), encoding="utf-8")
    return pristine


def _restore(home: Path, pristine: str) -> None:
    _subject(home).write_text(pristine, encoding="utf-8")


def _red(result, *tokens: str) -> None:
    """Assert FAIL and that the REASON names each token (rule 11)."""
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL, got {result.status}: {result.evidence or result.detail}"
    )
    blob = f"{result.site} {result.evidence} {result.detail}"
    for token in tokens:
        assert token in blob, f"the red does not name {token!r}: {blob}"


# ---------------------------------------------------------------------------
# NON-VACUITY FIRST (nix_check_contract.md §5.1)
# ---------------------------------------------------------------------------


def test_the_pristine_tree_PASSES(home: Path) -> None:
    """Without a plant the gate is green, or every red below proves nothing."""
    result = _run(home)
    assert result.status is Status.PASS, result.evidence or result.detail
    assert "TIME SINCE LAST ARRIVAL" in result.evidence


def test_an_absent_subject_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    _subject(home).unlink()
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert FRESHNESS in result.detail


def test_a_subject_that_will_not_import_is_CANNOT_MEASURE(home: Path) -> None:
    _subject(home).write_text("def (\n", encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "would not import" in result.detail


def test_a_config_with_too_few_feeds_is_CANNOT_MEASURE(home: Path) -> None:
    """§12A enumerates four `_STALE_MS` knobs; three is a feed left ungated."""
    path = home / CONFIG
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["price_stale_ms"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "below the non-vacuity floor" in result.detail
    assert "ungated" in result.detail


# ---------------------------------------------------------------------------
# THE TWO HEADLINE PLANTS -- each other's control
# ---------------------------------------------------------------------------


def test_a_detector_that_never_blocks_reddens(home: Path) -> None:
    """ARC 022 F17 ITSELF: the detector agrees with a dead feed.

    The plant leaves the STATE reporting correctly and only removes the halt,
    which is what makes it the realistic version of the defect: everything an
    operator would read still says STALE.
    """
    pristine = _plant(home, "blocked = age_ms > deadline", "blocked = False")
    _red(
        _run(home),
        "FreshnessTracker.reading",
        "900000 ms",
        "F17",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_detector_that_always_blocks_reddens(home: Path) -> None:
    """The mirror image: a slow-but-fresh feed halted as though it were dead."""
    pristine = _plant(
        home,
        "                state=CacheState.FRESH,\n                blocked=False,",
        "                state=CacheState.FRESH,\n                blocked=True,",
    )
    _red(
        _run(home),
        "A slow feed is not a stale one",
        "flattens a healthy book",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


# ---------------------------------------------------------------------------
# One plant per remaining arm
# ---------------------------------------------------------------------------


def test_a_halt_that_fires_INSIDE_the_retry_window_reddens(home: Path) -> None:
    """§6.4 declares a feed stale only AFTER retry/backoff."""
    pristine = _plant(
        home, "blocked = age_ms > deadline", "blocked = age_ms > threshold"
    )
    _red(
        _run(home),
        "retry/backoff window",
        "makes the configured RETRY_BACKOFF decorative",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_an_EMPTY_cache_reported_as_healthy_reddens(home: Path) -> None:
    """Stale-until-proven-fresh: a poller that never started is not a quiet one."""
    pristine = _plant(
        home,
        "                state=CacheState.EMPTY,\n                blocked=True,",
        "                state=CacheState.EMPTY,\n                blocked=False,",
    )
    _red(
        _run(home),
        "NEVER observed anything reported clear",
        "unstarted or wedged poller",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_FUTURE_dated_source_stamp_accepted_as_fresh_reddens(home: Path) -> None:
    """A stamp ahead of the clock never ages -- the property INVERTED."""
    pristine = _plant(
        home,
        "if age_ms < -self._policy.clock_skew_max_ms:",
        "if False:",
    )
    _red(
        _run(home),
        "AHEAD of the local clock",
        "reads fresh forever",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_clock_skew_ceiling_that_never_trips_reddens(home: Path) -> None:
    """§12.3: skew > threshold => stale-class HALT."""
    pristine = _plant(
        home,
        "if abs(skew) > self._policy.clock_skew_max_ms:",
        "if abs(skew) > self._policy.clock_skew_max_ms * 1000.0:",
    )
    _red(_run(home), "ClockSkewMonitor.read", "did not HALT", "stale-class HALT")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_clock_monitor_that_halts_a_GOOD_clock_reddens(home: Path) -> None:
    """The other half: chrony's ordinary jitter must not flatten the book."""
    pristine = _plant(
        home,
        "if abs(skew) > self._policy.clock_skew_max_ms:",
        "if abs(skew) >= 0.0:",
    )
    _red(_run(home), "was HALTed", "halts the book on chrony's ordinary jitter")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_skew_observation_trusted_FOREVER_reddens(home: Path) -> None:
    """A clock proven once is not a clock proven now."""
    pristine = _plant(home, "if age_ms > self._max_age_ms:", "if False:")
    _red(_run(home), "holding ceiling", "was good once")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_NAIVE_instant_accepted_reddens(home: Path) -> None:
    """§12.3: all internal time is UTC, enforced rather than requested."""
    pristine = _plant(
        home,
        '    """§12.3\'s UTC rule, enforced at the boundary of every public verb."""',
        '    """§12.3\'s UTC rule, enforced at the boundary of every public verb."""'
        "\n    return value  # type: ignore[return-value]  # PLANTED",
    )
    _red(
        _run(home),
        "NAIVE datetime was ACCEPTED",
        "units that depend on the host's local zone",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_MONOTONIC_guard_that_admits_older_readings_reddens(home: Path) -> None:
    """§6.4b: anything older is discarded, not applied."""
    pristine = _plant(
        home,
        "        if candidate.as_of != held.as_of:\n"
        "            return candidate.as_of > held.as_of",
        "        if candidate.as_of != held.as_of:\n            return True",
    )
    _red(
        _run(home),
        "SourceMonotonicGuard",
        "discarded, not applied",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_guard_that_admits_an_IDENTICAL_reading_reddens(home: Path) -> None:
    """A venue re-sending one reading must not refresh its own age."""
    pristine = _plant(
        home,
        "        if candidate.source_seq is None or held.source_seq is None:\n"
        "            return False",
        "        if candidate.source_seq is None or held.source_seq is None:\n"
        "            return True\n        return True",
    )
    _red(_run(home), "_is_newer", "would make a dead feed immortal")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_port_that_does_not_satisfy_the_gate_Protocol_reddens(home: Path) -> None:
    """A perfectly correct detector no rule can dispatch produces no halt."""
    pristine = _plant(
        home,
        "    def read(self, symbol: str) -> tuple[bool, str]:",
        "    def read_flag(self, symbol: str) -> tuple[bool, str]:",
    )
    result = _run(home)
    assert result.status in (Status.FAIL_NEEDS_OPERATOR, Status.CANNOT_MEASURE)
    blob = f"{result.site} {result.evidence} {result.detail}"
    assert "SymbolFlagPort" in blob or "read_flag" in blob or "read" in blob
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_detector_that_reads_the_WALL_CLOCK_reddens(home: Path) -> None:
    """The clock is injected; a detector that imports `time` cannot be driven."""
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    path.write_text(
        pristine.replace(
            "from datetime import UTC, datetime",
            "import time\nfrom datetime import UTC, datetime",
            1,
        ),
        encoding="utf-8",
    )
    _red(_run(home), "imports 'time'", "clock is INJECTED")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_detector_that_imports_the_POLLER_reddens(home: Path) -> None:
    """Fail-closed detection must not depend on the machinery it is watching."""
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    path.write_text(
        pristine.replace(
            "from nixrisk.calendar_seam import CacheState, FreshnessStamp",
            "from nixrisk.calendar_seam import CacheState, FreshnessStamp\n"
            "import nixrisk.pollers  # noqa",
            1,
        ),
        encoding="utf-8",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "the dependency runs one way" in result.detail
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_gate_that_CRASHES_is_CANNOT_MEASURE_not_FAIL(home: Path) -> None:
    """Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1."""
    pristine = _plant(
        home,
        "class StalenessPolicy:",
        "class StalenessPolicy:\n    _boom = 1 / 0",
    )
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "would not import" in result.detail or "gate raised" in result.detail
    _restore(home, pristine)
    assert _run(home).status is Status.PASS
