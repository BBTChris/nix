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

import os
import subprocess
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


# ===========================================================================
# ARC 052 — D3.464 (the marker never reached the log) and D3.465 (the log's
# teardown line was unreadable to the gate). Two defects on the same seam,
# both measured at `9a96eab`, and the pair is why they are tested together:
#
#   * `arc_050.log` carries NO marker. The run reached close-out and printed it
#     to the CHAT; this file's subject is a LOG, so the gate read
#     CANNOT-MEASURE — correctly, about evidence that was never written.
#   * `arc_051.log` carries the marker AND a teardown line, in the right order,
#     and the gate read FAIL with `teardowns=0`. `CLAUDE.md` instructs cc to
#     prove the teardown while disclaiming the root-owned `[watchdogd]`, cc
#     wrote both on ONE line, and the reader's kernel-thread veto was
#     line-scoped. The instrument was refusing the exact sentence the
#     instructions told the operator to produce.
#
# The repairs are on opposite sides and each stands alone: the READER now asks
# for a positive cc-watchdog signature instead of vetoing on a mention (strictly
# stronger — a teardown that identifies nothing used to pass and no longer
# does), and the EMITTER gained `teardown` and `marker` verbs, so the marker
# cannot be shown to the operator without landing in the log.
#
# §7.12, asked here: what would have to be true for these tests to pass while
# measuring nothing? The emitter tests could assert on strings this file also
# writes. They do not — every one of them runs `scripts/arc_heartbeat.sh` as a
# subprocess and then feeds the FILE IT PRODUCED to the gate. The two sides are
# only ever joined through the artifact.
# ===========================================================================

HEARTBEAT = REPO / "scripts" / "arc_heartbeat.sh"

#: `arc_051.log`'s teardown line, reduced to its shape: the claim about cc's own
#: watchdog and the disclaimer about the kernel thread, on ONE line. This is the
#: string that measured `teardowns=0` at `9a96eab`.
DISCLAIMING_TEARDOWN = (
    "WATCHDOG TEARDOWN: confirmed dead (no arc_heartbeat/arc_watchdog process "
    "owned by cc is alive; ps -eo pid,ppid,user,args matched cc's own signature "
    "and found none). The root-owned kernel thread [watchdogd] pid 165 is "
    "present, is NOT cc's, cannot be killed, and is NOT a leak."
)


def _emit(scratch: Path, verb: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the REAL emitter against a throwaway scratch dir."""
    return subprocess.run(
        # Invoked by the script's OWN absolute path, not `bash <path>`: a bare
        # interpreter name is a PATH lookup (bandit B607), and the shebang
        # already names the interpreter the shipped emitter runs under.
        [str(HEARTBEAT), verb, *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=str(REPO),
        env={
            **os.environ,
            "NIX_SCRATCH": str(scratch),
            "ARC_PROGRESS": str(scratch / "arc_progress.txt"),
            "ARC_HB_STATE": str(scratch / ".hb"),
            "ARC_LOG_DIR": str(scratch / "arc_logs"),
        },
    )


def _emitter_scratch(tmp_path: Path, arc: str = "999") -> Path:
    scratch = tmp_path / "scratch"
    (scratch / "arc_logs").mkdir(parents=True)
    now = int(time.time())
    (scratch / "arc_progress.txt").write_text(
        f"arc={arc}\nstart={now}\nts={now}\nstage=1\ntotal=2\nop=t\npct=50\n",
        encoding="utf-8",
    )
    return scratch


# --- D3.465: the READER ------------------------------------------------------


def test_D3465_a_teardown_that_DISCLAIMS_watchdogd_ON_THE_SAME_LINE_is_COUNTED() -> (
    None
):
    """The regression that was LIVE at 9a96eab, pinned by its real shape."""
    log = COMPLETE.format(arc="051").replace(
        "WATCHDOG TEARDOWN: confirmed dead (pid 434005 / arc_heartbeat)",
        DISCLAIMING_TEARDOWN,
    )
    verdict, reasons, facts = gate.audit_log(log)
    assert verdict == gate.PASS, (reasons, facts)
    assert facts["teardown_confirmations"] == 1, facts


def test_D3465_a_teardown_that_NAMES_NO_PROCESS_now_FAILS_and_says_why() -> None:
    """The STRENGTHENING, not a softening: the pre-D3.465 rule accepted this.

    `not KERNEL_WD.search(line)` was a proxy for "this is about cc's watchdog",
    and a bare confirmation satisfies the proxy while identifying nothing. The
    reason string must name the diagnosis, not merely the absence — rule 11.
    """
    log = COMPLETE.format(arc="051").replace(
        "WATCHDOG TEARDOWN: confirmed dead (pid 434005 / arc_heartbeat)",
        "WATCHDOG TEARDOWN: confirmed dead",
    )
    verdict, reasons, facts = gate.audit_log(log)
    assert verdict == gate.FAIL, (reasons, facts)
    assert any("none NAMES cc's own watchdog" in r for r in reasons), reasons


def test_D3465_a_teardown_written_ONLY_about_the_kernel_thread_still_FAILS() -> None:
    """The property the old veto existed for survives the repair."""
    log = COMPLETE.format(arc="051").replace(
        "WATCHDOG TEARDOWN: confirmed dead (pid 434005 / arc_heartbeat)",
        "WATCHDOG TEARDOWN: confirmed dead [watchdogd] kernel thread",
    )
    verdict, reasons, _ = gate.audit_log(log)
    assert verdict == gate.FAIL, reasons
    assert any("cc's own watchdog" in r for r in reasons), reasons


def test_D3465_the_reported_watchdog_pid_is_CCS_never_the_kernel_threads() -> None:
    """`wd_pid=165` was the kernel thread's, read out of a disclaimer clause and
    reported as cc's — confidently wrong about the one number a reader acts on."""
    _v, _r, clean = gate.audit_log(COMPLETE.format(arc="051"))
    assert clean["watchdog_pid"] == 434005, clean

    log = COMPLETE.format(arc="051").replace(
        "WATCHDOG TEARDOWN: confirmed dead (pid 434005 / arc_heartbeat)",
        DISCLAIMING_TEARDOWN,
    )
    _v2, _r2, disclaimed = gate.audit_log(log)
    assert disclaimed["watchdog_pid"] != 165, disclaimed


def test_the_drop_ins_OWN_SELFTEST_is_green() -> None:
    """The CLI's `--selftest` carries every planted arm; a red one here means a
    repair above broke a property an earlier arc banked."""
    done = subprocess.run(
        [
            sys.executable,
            str(REPO / "checks" / "check_arc_status_contract.py"),
            "--selftest",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "=== SELF-TEST PASS ===" in done.stdout, done.stdout


# --- D3.464: the EMITTER -----------------------------------------------------


def test_D3464_the_marker_verb_PRINTS_AND_RECORDS_in_one_call(tmp_path) -> None:
    """THE ROW'S NAMED DISCHARGE. `arc_050.log` lost its marker because printing
    it and logging it were two acts and only one happened. Here there is one
    act: the operator's line and the log entry come out of the same call."""
    scratch = _emitter_scratch(tmp_path)
    _emit(scratch, "selfcheck")
    _emit(scratch, "teardown")

    done = _emit(scratch, "marker")
    assert done.returncode == 0, done.stderr
    assert "**** ARC completed ****" in done.stdout, done.stdout
    log = (scratch / "arc_logs" / "arc_999.log").read_text(encoding="utf-8")
    assert log.count("**** ARC completed ****") == 1, log


def test_D3464_the_marker_REFUSES_when_no_teardown_names_ccs_watchdog(
    tmp_path,
) -> None:
    """Fail closed. The marker certifies a torn-down state (CHECK-A10 / §16.4);
    issuing it before the instrument is proven dead is the defect the gate would
    otherwise have to catch one arc later."""
    scratch = _emitter_scratch(tmp_path)
    _emit(scratch, "selfcheck")

    done = _emit(scratch, "marker")
    assert done.returncode == 2, done
    assert "**** ARC completed ****" not in done.stdout, done.stdout
    log = (scratch / "arc_logs" / "arc_999.log").read_text(encoding="utf-8")
    assert "ARC completed" not in log, log
    assert "MARKER REFUSED" in done.stderr, done.stderr


def test_D3464_the_teardown_verb_puts_the_watchdogd_DISCLAIMER_ON_ITS_OWN_LINE(
    tmp_path,
) -> None:
    """The emitter-side half of D3.465. Both repairs are independent, and this
    one keeps the two facts — *cc's watchdog is dead* and *the kernel thread is
    not cc's* — from ever sharing a line again."""
    scratch = _emitter_scratch(tmp_path)
    _emit(scratch, "teardown")
    lines = (
        (scratch / "arc_logs" / "arc_999.log").read_text(encoding="utf-8").splitlines()
    )
    claim = [ln for ln in lines if "WATCHDOG TEARDOWN" in ln]
    assert len(claim) == 1, lines
    assert "[watchdogd]" not in claim[0], claim[0]
    assert any("[watchdogd]" in ln and "WATCHDOG TEARDOWN" not in ln for ln in lines)


def test_D3464_END_TO_END_a_log_written_ONLY_by_the_emitter_is_a_PASS(
    tmp_path,
) -> None:
    """The two sides joined through the artifact and nothing else: the emitter
    writes the file, the gate reads the file, and no string is shared by this
    test with either of them except the verdict."""
    scratch = _emitter_scratch(tmp_path, arc="777")
    _emit(scratch, "selfcheck")
    _emit(scratch, "pulse")
    _emit(scratch, "teardown", "--pid", "424242")
    _emit(scratch, "marker")

    text = (scratch / "arc_logs" / "arc_777.log").read_text(encoding="utf-8")
    verdict, reasons, facts = gate.audit_log(text)
    assert verdict == gate.PASS, (reasons, text)
    assert facts["teardown_confirmations"] == 1, facts
    assert facts["watchdog_pid"] == 424242, facts
