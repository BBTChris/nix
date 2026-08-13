#!/usr/bin/env python3
"""check_monitor -- verify.py gate: the arc monitor reads REAL ~/.claude telemetry.

PROPERTY PROVEN (real, effective, on THIS host):
  `scripts/monitor.py` is present, internally self-consistent (its own
  `--selftest` and BOTH test harnesses -- `harness.py` and `pty_test.py` -- exit
  clean), AND actually observes the live Claude Code telemetry surface: the count
  of session transcripts the monitor REPORTS in its rendered footer equals the
  count that independently exists on disk under the same telemetry root. An
  instrument that paints a frame while reading zero files, when files exist, is
  the "measuring nothing while reporting green" failure this gate exists to catch
  (VERIFY-AND-CHECKS.md §B.5 `check_complexity` -- the tool that exits 0 on zero
  files -- is the same shape one level up).

EXIT / STATUS CONTRACT (nix_check_contract.md §4.2, VERIFY-AND-CHECKS.md §B.2):
  PASS (0)            monitor present, suites green, reported == independent count
  FAIL (1)            a suite RAN and exited non-zero, the footer went missing,
                      the frame crashed, or the reported count disagrees with
                      disk (a blind instrument) -- a measured violation, sited
  CANNOT_MEASURE (2)  no telemetry to read (`~/.claude/projects` absent or holds
                      0 transcripts), the monitor tooling itself is absent, or a
                      suite could not be RUN at all (timeout / OSError). The read
                      cannot be proven either way; §17 and doctrine C.1/B.2 forbid
                      a PASS here, and §B.2's exit-2 is why "could not run" is held
                      distinct from "ran and failed"

NON-VACUITY:
  The core assertion compares two numbers that MOVE TOGETHER -- the monitor's own
  reported jsonl count and an INDEPENDENT rglob of the SAME tree, never a fixed
  literal (no `== 5`) -- so it can neither pass by coincidence nor rot as usage
  grows. If the monitor silently stopped reading, its reported count would drop to
  0 while the independent count stayed > 0, and this gate would FAIL (doctrine C.4:
  never anchor to something that moves; assert the invariant, not the value).

DEMONSTRATED FAIL PATH (doctrine C.2 -- prove the gate CAN fail, with a control):
  CHECK_MONITOR_FORCE_FAIL=1 forces the FAIL branch, proving it is reachable and
  emits a loud, SITED message (§18: assert the reason, never the exit code alone).
  Driven on the box in this arc's RESULTS.

debug.md §7.12 -- WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The monitor reports a count matching disk while actually reading nothing.
    CLOSED: reported and independent are two INDEPENDENT rglobs of the same root;
    a blind reader drops to 0 while disk stays > 0, which is a FAIL, not a match.
 2. There is no telemetry, so "0 == 0" reads as a vacuous PASS. CLOSED: an absent
    `projects/` or a zero-transcript tree is CANNOT_MEASURE, never PASS (§5.3), and
    CANNOT_MEASURE dominates PASS in the aggregate.
 3. The suites pass while the monitor is broken. GUARDED by the FORCE_FAIL control
    (the FAIL branch is proven reachable) and by running the suites as real
    subprocesses whose non-zero exit is a FAIL that names the suite and its tail.
 4. The suites are never actually RUN (interpreter missing, timeout) and silence
    reads as success. CLOSED: a suite that could not be run is CANNOT_MEASURE
    naming the reason, never a pass -- the §B.2 incident (a timed-out subprocess
    exiting 1 recorded as a violation) inverted.
 5. The footer format drifts and the count is parsed from nothing. CLOSED: a
    missing `jsonl N files` footer is a FAIL, not an absent number read as 0.

RECONCILIATION NOTE. The architect's reference implementation is a standalone
exit-code script. Its LOGIC is preserved verbatim; its PACKAGING is rebuilt to
this box's house style -- the `nixverify.contract` `run(mode, ctx) -> CheckResult`
seam, static orchestration declarations read by `--optimize`, `standalone_main`
for the CLI, and CANNOT_MEASURE (not a bare exit 1) for every could-not-measure
branch per doctrine B.2. This is an EXTENSION of no existing gate: no check owns
the monitor tooling's property (doctrine C.9 -- one instrument per property), so a
new one is correct rather than a second owner of someone else's subject.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404 - fixed argv (sys.executable + repo paths), no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported; §4.4) ---
#: Nothing must run first: this gate reads the monitor tooling and the live
#: `~/.claude` telemetry surface, neither of which any other check produces.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate SPAWNS the interpreter four times -- `monitor.py --selftest`,
#: `harness.py`, `pty_test.py`, and `monitor.py --once`. BOTH basename spellings
#: are declared because `check_observed_resource_claims` matches a subprocess
#: claim by BASENAME and `sys.executable` is `.venv/bin/python` under pytest and
#: `/usr/bin/python3` under `nix-verify.service` (the same reasoning
#: `check_plane1_wal` / `check_feed_kill_drill` record). Nothing else is claimed:
#: the rglob and the `stat`/`exists` reads are read-only filesystem reads holding
#: nothing another check contends for, and the monitor child's own writes
#: (`~/.config/nixmon`) happen inside a SPAWNED process, which the observer does
#: not attribute to this check.
RESOURCES: tuple[str, ...] = ("subprocess:python3", "subprocess:python")
#: TRUE: `pty_test.py` alone runs ~18s of pseudo-terminal trials on this box.
TIME_BOUND = True
#: This gate's own ceiling, never an observed duration (§4.4). Four subprocesses,
#: dominated by the PTY suite; comfortably inside `observe_check`'s 60s per-check
#: budget so the observation gate can re-execute this one without timing out.
EXPECTED_S = 60.0
#: NON-CORRECTABLE. The subject is the monitor tooling itself; a gate that
#: "corrected" it would edit the very artifact under measurement, making its own
#: verdict true by construction -- the `check_observed_resource_claims` reasoning
#: (an instrument that rewrote its subject to satisfy itself measures nothing).
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the arc-monitor tooling (scripts/monitor.py and its two test "
    "harnesses); a repair that edited them to satisfy this gate would make the "
    "verdict true by construction and measure nothing"
)
#: The artifacts this gate NAMES and DRIVES. Declared so
#: `check_artifact_gate_coverage` records the three monitor scripts as covered --
#: they are tracked `scripts/*.py` outside `scripts/tests/`, so without a naming
#: check they would be uncovered artifacts (a coverage regression). This gate does
#: not merely name them: it opens and executes all three on every run.
SUBJECTS: tuple[str, ...] = (
    "scripts/monitor.py",
    "scripts/harness.py",
    "scripts/pty_test.py",
)

NAME = "check_monitor"

#: The monitor's footer prints `jsonl N files, M parse err`. N is the count the
#: instrument REPORTS reading; the whole non-vacuity argument turns on it.
FOOTER_RE = re.compile(r"jsonl\s+(\d+)\s+files")

#: Per-subprocess wall-clock ceiling. Well above the ~18s PTY suite; a run that
#: exceeds it is CANNOT_MEASURE (could not be measured), never a silent pass.
CMD_TIMEOUT_S = 90.0


def _claude_home() -> Path:
    """The live Claude Code telemetry root. `CLAUDE_HOME` overrides for tests."""
    return Path(os.environ.get("CLAUDE_HOME", os.path.expanduser("~/.claude")))


def _run(argv: list[str], cwd: Path) -> tuple[int, str, str, str]:
    """Run one subprocess. Returns `(rc, stdout, stderr, could_not_run)`.

    A non-empty final field means the subprocess could not be RUN to a verdict
    (timeout or OSError) -- distinct from a run that finished with a non-zero
    exit. The distinction is the §B.2 incident: a subprocess that timed out, whose
    exception went uncaught, exited the same `1` a real violation uses and was
    recorded as a violation while having measured nothing.
    """
    try:
        proc = subprocess.run(  # nosec B603 - argv built here from fixed paths
            argv,
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT_S,
            cwd=str(cwd),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "", f"timed out after {CMD_TIMEOUT_S}s"
    except OSError as exc:
        return 125, "", "", f"could not spawn: {exc!r}"
    return proc.returncode, proc.stdout, proc.stderr, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the monitor is self-consistent AND reads the real telemetry surface."""
    try:
        # Demonstrated, reachable FAIL path (doctrine C.2). Sited (§18).
        if os.environ.get("CHECK_MONITOR_FORCE_FAIL") == "1":
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=f"{NAME}:CHECK_MONITOR_FORCE_FAIL",
                evidence=(
                    "forced-failure control (doctrine C.2): the FAIL branch is "
                    "reachable and names its site, not a bare exit code"
                ),
                detail=(
                    "CHECK_MONITOR_FORCE_FAIL=1 -- the demonstrated can-fail path, "
                    "proving this gate is not a constant PASS"
                ),
            )

        scripts = Path(ctx.nix_home) / "scripts"
        monitor = scripts / "monitor.py"
        harness = scripts / "harness.py"
        pty = scripts / "pty_test.py"

        # Subject availability (§17, §5.3): a property proven while its subject is
        # unavailable is not proven -- an absent tool is CANNOT_MEASURE, not FAIL.
        missing = [p.name for p in (monitor, harness, pty) if not p.is_file()]
        if missing:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=(
                    f"monitor tooling absent under {scripts}: "
                    f"{', '.join(missing)} -- the subject cannot be observed, so "
                    "its behaviour cannot be measured (§17)"
                ),
            )

        # 1. Self-consistency: the tool's own three suites must exit clean.
        for label, argv in (
            ("selftest", [sys.executable, str(monitor), "--selftest"]),
            ("harness", [sys.executable, str(harness)]),
            ("pty_test", [sys.executable, str(pty)]),
        ):
            rc, out, err, could_not_run = _run(argv, scripts)
            if could_not_run:
                return CheckResult(
                    name=NAME,
                    status=Status.CANNOT_MEASURE,
                    detail=(
                        f"{label} could not be run ({could_not_run}); the suite "
                        "did not reach a verdict, so its outcome is UNMEASURED, "
                        "never a pass (doctrine B.2)"
                    ),
                )
            if rc != 0:
                tail = " | ".join((err or out).strip().splitlines()[-3:]) or "-"
                return CheckResult(
                    name=NAME,
                    status=Status.FAIL_NEEDS_OPERATOR,
                    site=f"{NAME}:{label}",
                    evidence=(
                        f"monitor suite {label!r} FAILED on this host -- the tool "
                        "is not internally self-consistent"
                    ),
                    detail=f"{label} exited {rc}: {tail}",
                )

        # 2. NON-VACUOUS read proof: what the monitor REPORTS must equal what
        #    independently exists under the SAME telemetry root.
        claude_home = _claude_home()
        projects = claude_home / "projects"
        if not projects.is_dir():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=(
                    f"no telemetry root at {projects}; there are no sessions to "
                    "read, so the monitor's read cannot be proven either way "
                    "(§5.3) -- discharge once real Claude Code history exists"
                ),
            )
        independent = len(list(projects.rglob("*.jsonl")))
        if independent == 0:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=(
                    f"{projects} exists but holds 0 *.jsonl transcripts; nothing "
                    "to read, so the read cannot be proven (§5.3)"
                ),
            )

        rc, out, err, could_not_run = _run(
            [
                sys.executable,
                str(monitor),
                "--once",
                "--width",
                "110",
                "--claude-home",
                str(claude_home),
            ],
            scripts,
        )
        if could_not_run:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=(
                    f"monitor --once could not be run ({could_not_run}); the read "
                    "was not measured, never a pass (doctrine B.2)"
                ),
            )
        if rc != 0:
            crash = (err or out).strip().splitlines()[-3:]
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=f"{NAME}:monitor --once",
                evidence="monitor --once did not render a frame on this host",
                detail=f"monitor --once exited {rc}: {' | '.join(crash) or '-'}",
            )
        match = FOOTER_RE.search(out)
        if not match:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=f"{NAME}:footer",
                evidence="monitor --once rendered without a 'jsonl N files' footer",
                detail=(
                    "no 'jsonl N files' footer in the frame -- the frame did not "
                    "render or the footer format changed; the reported count "
                    "cannot be read, so it must not be inferred as 0"
                ),
            )
        reported = int(match.group(1))
        if reported != independent:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=f"{NAME}:{projects}",
                evidence=(
                    f"BLIND INSTRUMENT: monitor reports {reported} jsonl files, "
                    f"{independent} exist on disk"
                ),
                detail=(
                    f"monitor's rendered footer reports {reported} jsonl "
                    f"transcript(s) but an independent rglob of {projects} finds "
                    f"{independent}. The instrument is measuring something other "
                    "than the live telemetry surface it claims to observe"
                ),
            )

        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"monitor tooling self-consistent (selftest + harness + pty_test "
                f"green) and NON-VACUOUS: its rendered footer reports {reported} "
                f"jsonl transcript(s), independently {independent} exist under "
                f"{projects} (two rglobs of the same root, matched -- not a fixed "
                "literal)"
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
