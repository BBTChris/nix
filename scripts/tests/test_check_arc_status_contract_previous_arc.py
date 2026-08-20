"""D3.455 — `check_arc_status_contract` NAMES the arc it audited, and audits
the PREVIOUS arc specifically rather than whatever log is newest.

ARC 049. The defect this pins is measured, not hypothetical: ARC 048's sweep
reported `[ok]` against `/home/bbt/nix/scratchpad/arc_logs/arc_047.log` — a
COMPLETED arc's evidence — because `arc_048.log` did not exist when the check
ran. The verdict named no arc, so a green read as a statement about ARC 048
when it was a statement about ARC 047. That is check-contract rule 10's shape
(a property certified while its subject is unavailable) reached by mislabelling
rather than by absence.

The cadence itself is CORRECT and is not what changed (D3.433): the completion
marker is by construction the last token an arc prints, so the arc under audit
is always the previous one. What changed is that the running arc's own log is
now excluded BY NAME, the audited arc travels back into the verdict line, and a
run with nothing older inside the freshness window is CANNOT_MEASURE naming
what is missing instead of a quiet fall-back onto a log old enough that a PASS
off it is an assurance about a different week.

Rule 11 throughout: every assertion reads the REASON, never the status alone.
"""
# Test names SHOUT the property under test on purpose — a red verdict should
# read as a sentence about the defect. Same convention, same reason, as
# test_status_contract.py; late imports are this file's sys.path bootstrap,
# and `_running_arc` is read directly because the arc id it derives is the
# whole subject of one test.
# pylint: disable=invalid-name,import-outside-toplevel,protected-access

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "checks"))
sys.path.insert(0, str(REPO / "scripts"))

import check_arc_status_contract as gate  # pylint: disable=wrong-import-position
from nixverify.contract import Mode, Status  # pylint: disable=wrong-import-position

#: A COMPLETE arc log: pulses, a self-verify, a teardown matched by pid, and the
#: marker last. Shaped from the real `arc_048.log`, not invented.
COMPLETE = """[ARC {arc} #######- 90% stage 14/15 - re-measure - 32m - ~3m - HEAD abc1234 ADVANCED]
HEARTBEAT SELF-VERIFY: ok (emitter produced a pulse)
[ARC {arc} ######## 96% stage 15/15 - close-out - 35m - ~1m - HEAD abc1234 ADVANCED]
WATCHDOG TEARDOWN: confirmed dead (pid 434005 / arc_heartbeat)
**** ARC completed ****
"""

#: The same run with the teardown line removed: the arc finished and left cc's
#: own watchdog breathing. The audit must still BITE on the previous arc.
LEAKED = COMPLETE.replace(
    "WATCHDOG TEARDOWN: confirmed dead (pid 434005 / arc_heartbeat)\n", ""
)

#: A run in flight: beats, no marker. Not judgeable, by design.
IN_FLIGHT = """[ARC {arc} ##------ 20% stage 2/8 - S1 - 6m - ~24m - HEAD abc1234 ADVANCED]
"""


class _Ctx:  # pylint: disable=too-few-public-methods
    def __init__(self, home: Path) -> None:
        self.nix_home = home


def _home(tmp_path: Path, running: str, logs: dict[str, tuple[str, float]]) -> Path:
    """A tree with a progress file naming `running` and the logs given.

    `logs` maps arc id -> (body, age_seconds), so a stale log is stale because
    of its mtime rather than because a constant here says so.
    """
    home = tmp_path / "home"
    directory = home / gate.ARC_LOG_DIR
    directory.mkdir(parents=True)
    (home / "scratchpad" / "arc_progress.txt").write_text(
        f"arc={running}\nstart=1\nts=2\nstage=1\ntotal=8\nop=x\npct=1\n",
        encoding="utf-8",
    )
    now = time.time()
    for arc, (body, age) in logs.items():
        path = directory / f"arc_{arc}.log"
        path.write_text(body.format(arc=arc), encoding="utf-8")
        import os  # pylint: disable=import-outside-toplevel

        os.utime(path, (now - age, now - age))
    return home


def _run(home: Path):
    """The ENGINE arm. `check_arc_status_contract` defines `run` twice by design.

    The module is a verbatim CLI drop-in with the ARC 041-T engine adapter
    appended below it, so the name `run` is bound first to the CLI signature
    `(log_path, live, min_pulses)` and then re-bound to the dispatcher that
    routes `(Mode, Context)` to `_engine_run`. mypy reads the first binding;
    the dispatcher is what actually answers. The ignore names both codes rather
    than blanket-silencing the call.
    """
    return gate.run(Mode.VERIFY, _Ctx(home))  # type: ignore[call-arg,arg-type]


# ==========================================================================
# The duty cycle, preserved and now legible.
# ==========================================================================


def test_it_audits_the_PREVIOUS_arc_and_NAMES_it(tmp_path) -> None:
    """ARC 049 running, ARC 048 complete: PASS, and the verdict says 048."""
    home = _home(
        tmp_path,
        running="049",
        logs={"048": (COMPLETE, 3600.0), "049": (IN_FLIGHT, 0.0)},
    )
    result = _run(home)
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "AUDITED ARC 048" in result.evidence, result.evidence
    assert "arc_048.log" in result.evidence, result.evidence
    # And NOT about the arc that is running — the ARC 048 defect exactly.
    assert "arc_049.log" not in result.evidence, result.evidence


def test_the_audit_still_BITES_on_the_previous_arc(tmp_path) -> None:
    """A leaked watchdog one arc back is a FAIL, named. The cadence still works."""
    home = _home(
        tmp_path,
        running="049",
        logs={"048": (LEAKED, 3600.0), "049": (IN_FLIGHT, 0.0)},
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"{result.status}: {result.detail}"
    )
    assert "AUDITED ARC 048" in result.evidence, result.evidence
    assert "teardown" in result.detail.lower(), result.detail


# ==========================================================================
# THE DEMONSTRATED FAIL — the pre-patch behaviour, refused.
# ==========================================================================


def test_a_STALE_previous_log_is_CANNOT_MEASURE_not_a_PASS_off_it(tmp_path) -> None:
    """The plant: the expected previous-arc log is outside the window.

    Before this patch the picker took the newest log unconditionally and, with
    the running arc's log absent, would have passed off whatever it found. Here
    the only non-running log is two days old: the honest answer is
    CANNOT_MEASURE naming the window, and it must name it rather than reporting
    a green about a different week.
    """
    home = _home(
        tmp_path,
        running="049",
        logs={
            "047": (COMPLETE, gate.ARC_LOG_MAX_AGE_S * 2),
            "049": (IN_FLIGHT, 0.0),
        },
    )
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, (
        f"{result.status}: {result.detail} / {result.evidence}"
    )
    assert "arc_047.log" in result.detail, result.detail
    assert "freshness window" in result.detail, result.detail
    assert "049 is running" in result.detail, result.detail


def test_the_RUNNING_arcs_own_log_is_never_the_subject(tmp_path) -> None:
    """Only the running arc's log exists: CANNOT_MEASURE naming it. Never PASS.

    This is the ARC 048 situation with the tee applied — the running arc's log
    is the NEWEST file in the directory, which is precisely what the old picker
    chose.
    """
    home = _home(tmp_path, running="049", logs={"049": (IN_FLIGHT, 0.0)})
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, f"{result.status}: {result.detail}"
    assert "arc_049.log" in result.detail, result.detail
    assert "RUNNING RIGHT NOW" in result.detail, result.detail


def test_a_COMPLETE_running_log_is_STILL_not_the_subject(tmp_path) -> None:
    """Even if the running arc's log already carries a marker, it is excluded.

    Rule 10 with the sharpest edge: an arc cannot certify its own conduct in the
    same sweep it is conducting. The marker is the last token it prints, so a
    marker present mid-run means the log is being written past its own close-out
    — and a gate that graded it would be grading a run that has not ended.
    """
    home = _home(tmp_path, running="049", logs={"049": (COMPLETE, 0.0)})
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, (
        f"{result.status}: {result.detail} / {result.evidence}"
    )
    assert "RUNNING RIGHT NOW" in result.detail, result.detail


# ==========================================================================
# Absence of a progress file: no arc is running, so the newest log IS previous.
# ==========================================================================


def test_with_NO_running_arc_the_newest_completed_log_is_audited(tmp_path) -> None:
    """A bare periodic sweep still audits the last arc, and still names it."""
    home = tmp_path / "home"
    directory = home / gate.ARC_LOG_DIR
    directory.mkdir(parents=True)
    path = directory / "arc_048.log"
    path.write_text(COMPLETE.format(arc="048"), encoding="utf-8")
    result = _run(home)
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "AUDITED ARC 048" in result.evidence, result.evidence


@pytest.mark.parametrize("arc", ["049", "041T"])
def test_the_running_arc_id_is_READ_not_assumed(tmp_path, arc) -> None:
    """`041T` is a real arc id in this tree; a numeric decrement would miss it."""
    home = _home(
        tmp_path,
        running=arc,
        logs={"040": (COMPLETE, 3600.0), arc: (IN_FLIGHT, 0.0)},
    )
    assert gate._running_arc(home) == arc  # pylint: disable=protected-access
    result = _run(home)
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "AUDITED ARC 040" in result.evidence, result.evidence
