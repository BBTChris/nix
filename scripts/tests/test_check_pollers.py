"""ARC 033 / 1C -- the can-fail suite for `checks/check_pollers.py`.

**THE REQUIREMENT THIS FILE EXISTS TO SATISFY:** prove the gate reddens on a
real defect in each declared arm, and that each red NAMES THE REASON -- the
site and the condition -- never the exit code or the status alone (check
contract v2 rule 11 / §18).

**No plant touches a production artifact** (doctrine C.8). Every control builds
a throwaway `nix_home` under `tmp_path` carrying a COPY of `scripts/nixrisk/`
and `risks/`, perturbs the COPY, and drives the SHIPPED gate against it. Every
plant is followed IN THE SAME TEST by a restore-and-re-run control.

**THE HEADLINE PLANT is `test_a_SECOND_live_margin_surface_reddens`:** §6.4's
v1.3 lock is the one property in this module that a reading pass would call
plausible in either direction -- a "fast, seconds" margin poller is exactly
where a live per-symbol margin figure wants to live, and one that cached it
would look correct and pass every other arm here.

**WHAT IS DELIBERATELY NOT PLANTED, because a suite that pretended otherwise
would be the defect:** ARM POOL's CONTAINMENT half. A poller that blocked the
event loop makes the gate HANG rather than redden, so its negative outcome is a
timeout and not a verdict. What is planted instead is the SHAPE (`async def`
removed) and the YIELD half (the per-symbol yield removed), which are the two
mechanisms containment actually stands on.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front -- loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_pollers as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

POLLERS = "scripts/nixrisk/pollers.py"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of `scripts/nixrisk/` and `risks/`."""
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _subject(home: Path) -> Path:
    return home / POLLERS


def _plant(home: Path, old: str, new: str) -> str:
    """Swap one exact fragment in the COPY, returning the pristine source."""
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    assert old in pristine, f"plant fragment not found in {POLLERS}: {old!r}"
    path.write_text(pristine.replace(old, new, 1), encoding="utf-8")
    return pristine


def _append(home: Path, text: str) -> str:
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    path.write_text(pristine + text, encoding="utf-8")
    return pristine


def _restore(home: Path, pristine: str) -> None:
    _subject(home).write_text(pristine, encoding="utf-8")


def _red(result, *tokens: str) -> None:
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
    result = _run(home)
    assert result.status is Status.PASS, result.evidence or result.detail
    assert "second margin table" in result.evidence


def test_an_absent_subject_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    _subject(home).unlink()
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert POLLERS in result.detail


def test_a_subject_that_will_not_import_is_CANNOT_MEASURE(home: Path) -> None:
    _subject(home).write_text("class (\n", encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "would not import" in result.detail


# ---------------------------------------------------------------------------
# THE HEADLINE PLANT -- §6.4's v1.3 lock
# ---------------------------------------------------------------------------


def test_a_SECOND_live_margin_surface_reddens(home: Path) -> None:
    """A helper reaching the LIVE per-symbol margin field is the locked defect.

    Planted as a module-level helper nothing calls, which is the realistic
    shape: the first version of this defect is always a convenience accessor,
    and it is a cross-table skew the moment anything calls it.
    """
    pristine = _append(
        home,
        "\n\ndef _live_margin_of(picture):\n"
        '    """PLANTED: reaches the Limiter\'s live per-symbol figure."""\n'
        "    return picture.margin_per_contract\n",
    )
    _red(
        _run(home),
        "LIVE per-symbol margin field",
        "one unified financial-picture snapshot",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_importing_the_FinancialPicture_into_the_poller_reddens(home: Path) -> None:
    """The unified snapshot is the LIMITER's, under one writer and one stamp."""
    pristine = _plant(
        home,
        "from nixrisk.freshness import FreshnessTracker, StalenessUsageError",
        "from nixrisk.freshness import FreshnessTracker, StalenessUsageError\n"
        "from nixrisk.seam import FinancialPicture  # noqa: F401  PLANTED",
    )
    _red(_run(home), "imports FinancialPicture", "second surface for the same state")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


# ---------------------------------------------------------------------------
# §6.4's push-preferred clause
# ---------------------------------------------------------------------------


def test_a_demotion_that_does_NOT_widen_the_cadence_reddens(home: Path) -> None:
    """A demotion that keeps its interval has changed a NAME, not a behaviour."""
    pristine = _plant(
        home,
        "        if self.mode() is PollerMode.FALLBACK_AUDIT:\n"
        "            return self._audit_interval_ms",
        "        if self.mode() is PollerMode.FALLBACK_AUDIT:\n"
        "            return self._poll_interval_ms",
    )
    _red(
        _run(home),
        "changed a NAME and not a behaviour",
        "PushDemotion.interval_ms",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_poller_that_never_RE_PROMOTES_reddens(home: Path) -> None:
    """A dead websocket sends no failover event; the fallback must not wait."""
    pristine = _plant(
        home,
        "            if idle_ms <= self._push_idle_ms:\n"
        "                wanted = PollerMode.FALLBACK_AUDIT",
        "            if True:\n                wanted = PollerMode.FALLBACK_AUDIT",
    )
    _red(
        _run(home),
        "push silence",
        "stays demoted through the outage",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_constructor_that_accepts_an_EQUAL_audit_interval_reddens(home: Path) -> None:
    """A configuration that cannot demote would pass every other arm here."""
    pristine = _plant(
        home,
        "        if audit_interval_ms <= poll_interval_ms:",
        "        if False:",
    )
    _red(
        _run(home),
        "PushDemotion.__init__",
        "gesturing at it",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


# ---------------------------------------------------------------------------
# §6.4b at the producer
# ---------------------------------------------------------------------------


def test_a_poller_that_BYPASSES_the_monotonic_guard_reddens(home: Path) -> None:
    """§6.4b: a slow poll landing after a fresher push is dropped, not applied."""
    pristine = _plant(
        home,
        "            if self._tracker.observe(row.stamp, row.baseline.symbol):\n"
        "                merged[row.baseline.symbol] = row.baseline",
        "            if True:\n                merged[row.baseline.symbol] = row.baseline",
    )
    _red(_run(home), "through the guard", "dropped, not applied")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


# ---------------------------------------------------------------------------
# §10 shared pool / §12.7 transport shape
# ---------------------------------------------------------------------------


def test_a_rebuild_that_yields_only_at_its_EDGES_reddens(home: Path) -> None:
    """A coroutine that awaits only at its edges is a blocking function."""
    pristine = _plant(
        home,
        "        for symbol in self._symbols:\n"
        "            await asyncio.sleep(0)\n"
        "            self.yields += 1",
        "        await asyncio.sleep(0)\n"
        "        for symbol in self._symbols:\n"
        "            self.yields += 1",
    )
    _red(
        _run(home),
        "CalendarPoller.refresh",
        "cannot starve the fast margin poll",
    )
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_SYNCHRONOUS_poll_verb_reddens(home: Path) -> None:
    """`calendar_seam.py` declared poll_once async for CONTAINMENT."""
    path = _subject(home)
    pristine = path.read_text(encoding="utf-8")
    # TWO fragments, because dropping `async` alone is a SyntaxError and a
    # SyntaxError is CANNOT_MEASURE -- which would demonstrate the loader, not
    # the arm. The realistic defect converts the whole verb.
    planted = pristine.replace(
        "    async def poll_once(self) -> FreshnessStamp:",
        "    def poll_once(self) -> FreshnessStamp:",
        1,
    ).replace("        rows = await self._fetch()", "        rows = self._fetch()", 1)
    assert planted != pristine
    path.write_text(planted, encoding="utf-8")
    _red(_run(home), "poll_once", "CONTAINMENT")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_an_AWAITABLE_publish_reddens(home: Path) -> None:
    """§12.7: the verb returns when the bytes are consistent, or it is not a publish."""
    pristine = _plant(
        home,
        "    def publish(self, baselines: tuple[MarginBaseline, ...]) -> None:",
        "    async def publish(self, baselines: tuple[MarginBaseline, ...]) -> None:",
    )
    _red(_run(home), "MarginPoller.publish", "half-built table")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


# ---------------------------------------------------------------------------
# Cache-level verdicts
# ---------------------------------------------------------------------------


def test_an_unpublished_cache_reported_FRESH_reddens(home: Path) -> None:
    """`calendar_seam.py` puts EMPTY first: here the book gets flattened."""
    pristine = _plant(
        home,
        '        """EMPTY / FRESH / STALE for the cache AS A WHOLE.',
        '        """EMPTY / FRESH / STALE for the cache AS A WHOLE.\n\n'
        "        PLANTED.\n"
        '        """\n'
        "        if not self._published:\n"
        "            return CacheState.FRESH\n"
        '        _ = """',
    )
    _red(_run(home), "MarginPoller.state", "rather than EMPTY")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_cache_freshness_taken_from_the_NEWEST_key_reddens(home: Path) -> None:
    """One live symbol must not mask four dead ones."""
    pristine = _plant(
        home,
        "    return min(stamps, key=lambda stamp: stamp.as_of)",
        "    return max(stamps, key=lambda stamp: stamp.as_of)",
    )
    _red(_run(home), "the NEWEST key rather than the oldest", "can never go stale")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_FALSE_port_claim_reddens(home: Path) -> None:
    """A declaration over a Protocol the class does not satisfy."""
    pristine = _plant(
        home,
        '    ("CalendarPoller", "WindowSetReadPort"),',
        '    ("CalendarPoller", "MarginBaselineReadPort"),',
    )
    _red(_run(home), "CalendarPoller", "does not satisfy")
    _restore(home, pristine)
    assert _run(home).status is Status.PASS


def test_a_gate_that_CRASHES_is_CANNOT_MEASURE_not_FAIL(home: Path) -> None:
    """Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1."""
    pristine = _plant(
        home,
        "class MarginPoller:",
        "class MarginPoller:\n    _boom = 1 / 0",
    )
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "would not import" in result.detail or "gate raised" in result.detail
    _restore(home, pristine)
    assert _run(home).status is Status.PASS
