"""ARC 026 C5/C4 — the standing gate over `capture.py`'s Plane-2 obligation.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing.

**No plant touches a production artifact** (doctrine C.8). The behavioural plants
are shim namespaces handed to the gate through its own `_load` seam; the
filesystem plants build a miniature `nix_home` under `tmp_path`. The real
`scripts/capture.py` is never edited.

**Every control asserts the REASON** — the site, the named condition, or the
field — never the exit code alone (check contract v2 §11).

Every test here emits into the REAL journal under the real `nix-capture`
identifier, carrying a per-test nonce. That is deliberate: a Plane-2 gate tested
against a fake journal would prove that a fake journal works.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access
# `protected-access`: a can-fail control drives the gate's ARMS, which are
# private by design — an arm made public so a test could reach it would be a
# surface the gate did not need, invented for the test. Doctrine C.8 says the
# plant must not touch the production artifact; it does not say the test may
# only use the public API.
# pylint: disable=duplicate-code,too-few-public-methods
# Test names SHOUT the property; shim classes are deliberately tiny; the
# sys.path bootstrap forces late imports. Each deliberate, so the pragma is named.

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "scripts" / "broker"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import capture  # pylint: disable=wrong-import-position
import check_capture_plane2 as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_capture_plane2.py"

pytestmark = pytest.mark.skipif(
    not Path(gate.JOURNAL_SOCKET).exists() or not Path(gate.JOURNALCTL).exists(),
    reason="no journal ingress on this node — the gate's own subject is absent",
)


def _run(home: Path = REPO):
    """Drive the gate."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _shim(**overrides: object) -> tuple[object, object]:
    """The real `capture` with named parts swapped, plus the real seam.

    `broker_seam` is imported here rather than obtained from `gate._load()`:
    every caller of this helper is about to monkeypatch `_load`, and a helper
    that called it would recurse into its own replacement.
    """
    import broker_seam as seam

    parts: dict[str, object] = {
        "IDENTIFIER": capture.IDENTIFIER,
        "PROCESS": capture.PROCESS,
        "CaptureProcess": capture.CaptureProcess,
    }
    parts.update(overrides)
    return types.SimpleNamespace(**parts), seam


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — real events reached the real journal.
# --------------------------------------------------------------------------


def test_the_REAL_capture_py_PASSES_and_the_events_ROUND_TRIP() -> None:
    """A green means three per-channel events were read back out of journald."""
    result = _run()
    assert result.status is Status.PASS, result.detail
    assert "3 per-channel transition events recovered" in result.evidence
    assert "emitter delivered=" in result.evidence, result.evidence


def test_the_transitions_are_PER_CHANNEL_and_the_control_emitted_nothing() -> None:
    """AMENDMENT 6's shape and §12.10's transition rule, in one evidence line."""
    result = _run()
    assert "('unobserved', 'fresh')" in result.evidence, result.evidence
    assert "CONTROL: unchanged re-observation emitted 0" in result.evidence


def test_capture_py_writes_NO_PLANE_1_and_NOTHING_under_logs() -> None:
    """§12.10: Plane 1 has one writer forever, and it is not this process."""
    result = _run()
    assert "capture.py imports no database driver" in result.evidence
    assert "logs/ holds no capture.py Plane-2 artifact" in result.evidence


# --------------------------------------------------------------------------
# PLANT 1 — a LEVEL logger wearing a transition logger's name.
# --------------------------------------------------------------------------


class _LevelLogger(capture.CaptureProcess):
    """Emits on every observation, changed or not. §12.10's chatty-logging shape."""

    def observe_freshness(self, report):  # type: ignore[no-untyped-def]
        """Real transitions, plus one event for an unchanged channel."""
        changed = super().observe_freshness(report)
        if changed:
            return changed
        entry = report.channels[0]
        transition = capture.StalenessTransition(
            symbol=str(report.symbol),
            channel=entry.channel,
            previous=entry.state.value,
            current=entry.state,
            excess_staleness_s=entry.excess_staleness_s,
            threshold_s=entry.threshold_s,
            effective_lag_s=entry.lag.effective_lag_s,
            venue_ts=entry.venue_ts,
            lag_provenance=entry.lag.provenance.value,
        )
        self.plane2.emit("feed_staleness_transition", **transition.fields())
        return [transition]


def test_a_LEVEL_LOGGER_fails_and_NAMES_the_monitor_and_the_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headline can-fail: §12.10's row is *staleness TRANSITIONS*, not levels."""
    monkeypatch.setattr(gate, "_load", lambda: (_shim(CaptureProcess=_LevelLogger), ""))
    result = _run()
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "capture.py:FeedStalenessMonitor.observe" in result.site, result.site
    assert "re-observing an UNCHANGED channel" in result.detail, result.detail
    assert "chatty logging" in result.detail, result.detail


def test_UNPLANTING_the_level_logger_restores_PASS() -> None:
    """The plant removed, the same gate passes. Step three of §5.1."""
    assert _run().status is Status.PASS


# --------------------------------------------------------------------------
# PLANT 2 — the process lies about which process it is.
# --------------------------------------------------------------------------


def test_an_event_stamped_with_the_WRONG_PROC_fails_and_NAMES_the_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§12.10: each PROCESS writes its own events, so `proc=` is load-bearing."""
    monkeypatch.setattr(gate, "_load", lambda: (_shim(PROCESS="verify.py"), ""))
    result = _run()
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "proc='verify.py', expected capture.py" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — a Plane-1 writer appears inside capture.py.
# --------------------------------------------------------------------------


def test_a_capture_py_that_IMPORTS_A_DB_DRIVER_fails_and_quotes_the_rule(
    tmp_path: Path,
) -> None:
    """§12.10: *'Limiter sole writer ... No new writers, ever.'*"""
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    (home / "scripts" / "capture.py").write_text(
        "import psycopg2\n\n\ndef go():\n    return psycopg2\n", encoding="utf-8"
    )
    defects: list[tuple[str, str]] = []
    evidence: list[str] = []
    gate._arm_no_plane1(home, defects, evidence)
    assert defects, "a DB import inside capture.py was not a finding"
    site, why = defects[0]
    assert site == "scripts/capture.py", site
    assert "No new writers, ever" in why, why
    assert "psycopg2" in why, why


def test_UNPLANTING_the_db_import_clears_the_finding(tmp_path: Path) -> None:
    """Step three of §5.1 for plant 3."""
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    source = home / "scripts" / "capture.py"
    source.write_text("import psycopg2\n", encoding="utf-8")
    defects: list[tuple[str, str]] = []
    gate._arm_no_plane1(home, defects, [])
    assert defects
    source.write_text("import json\n", encoding="utf-8")
    cleared: list[tuple[str, str]] = []
    evidence: list[str] = []
    gate._arm_no_plane1(home, cleared, evidence)
    assert not cleared, cleared
    assert "imports no database driver" in evidence[0], evidence


# --------------------------------------------------------------------------
# PLANT 4 — Plane 2 lands in `logs/`, which is pinned to non-Plane artifacts.
# --------------------------------------------------------------------------


def test_a_PLANE_2_ARTIFACT_under_logs_fails_and_NAMES_the_stray_file(
    tmp_path: Path,
) -> None:
    """`directory_structure.md` pins `logs/` to non-Plane artifacts."""
    home = tmp_path / "home"
    (home / "logs").mkdir(parents=True)
    stray = home / "logs" / "capture.log"
    stray.write_text(
        "ts=2026-08-12T00:00:00.000000Z proc=capture.py event=x\n", encoding="utf-8"
    )
    defects: list[tuple[str, str]] = []
    gate._arm_logs_dir(home, defects, [])
    assert defects, "a Plane-2 artifact under logs/ was not a finding"
    assert defects[0][0] == "logs/capture.log", defects
    assert "under logs/" in defects[0][1], defects

    stray.unlink()
    cleared: list[tuple[str, str]] = []
    evidence: list[str] = []
    gate._arm_logs_dir(home, cleared, evidence)
    assert not cleared, cleared
    assert "no capture.py Plane-2 artifact" in evidence[0], evidence


# --------------------------------------------------------------------------
# The gate refuses to look, loudly, rather than passing.
# --------------------------------------------------------------------------


def test_NOTHING_reaching_the_journal_is_CANNOT_MEASURE_not_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The transport-vacuity rule, applied to Plane 2."""
    monkeypatch.setattr(gate, "_await_readback", lambda _ident, _nonce: ([], ""))
    result = _run()
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "never PASS" in result.detail, result.detail
    assert "reached the journal within" in result.detail, result.detail


def test_an_UNREADABLE_journal_is_CANNOT_MEASURE_and_carries_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'I could not look' is never 'the log is fine'."""
    monkeypatch.setattr(
        gate, "_await_readback", lambda _ident, _nonce: ([], "journalctl exit 1: nope")
    )
    result = _run()
    assert result.status is Status.CANNOT_MEASURE
    assert "journalctl exit 1: nope" in result.detail, result.detail


def test_a_MISSING_journalctl_is_CANNOT_MEASURE_and_NAMES_the_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No reader means no round-trip, which is not a clean Plane 2."""
    monkeypatch.setattr(gate, "JOURNALCTL", "/nonexistent/journalctl")
    result = _run()
    assert result.status is Status.CANNOT_MEASURE
    assert "/nonexistent/journalctl" in result.detail, result.detail


def test_an_UNIMPORTABLE_capture_is_CANNOT_MEASURE_and_NAMES_the_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`verify.py` may run under an interpreter with no pyzmq. Not a PASS."""
    monkeypatch.setattr(gate, "_load", lambda: (None, "cannot import capture.py: boom"))
    result = _run()
    assert result.status is Status.CANNOT_MEASURE
    assert "cannot import capture.py" in result.detail, result.detail


# --------------------------------------------------------------------------
# The gate never pins its own runner, and its declarations are readable.
# --------------------------------------------------------------------------


def test_the_gate_DOES_NOT_PIN_the_process_it_runs_in() -> None:
    """An instrument that pinned its runner would change the machine it measures."""
    import os

    before = os.sched_getaffinity(0)
    _run()
    assert os.sched_getaffinity(0) == before, "the gate repinned its own runner"


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_venv",)
    assert declaration.resources == ("journal",)
    assert declaration.subjects == ("scripts/capture.py",)


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "writing the events under measurement" in combined, combined
