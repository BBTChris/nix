#!/usr/bin/env python3
"""
check_arc_status_contract.py — verify.py gate for the Status Contract.

Makes "the operator was kept informed AND the instrument was torn down" a MEASURED
property of an arc run, not a remembered instruction. It audits an arc's own log and
FAILS if a run reached close-out with:
  (a) no heartbeat / watchdog-self-verify evidence, or
  (b) cc's OWN heartbeat watchdog left alive after the completion marker.

Critical false-positive guard (039R): the kernel thread [watchdogd] is root-owned,
always present, and is NOT cc's watchdog. This gate matches cc's watchdog by its own
signature and EXPLICITLY excludes [watchdogd]; it never treats the kernel thread as a leak.

Exit-code contract (VERIFY-AND-CHECKS rule 1):
    0 = PASS         1 = FAIL         2 = CANNOT-MEASURE
No uncaught exception may collapse to exit 1. Fail closed and loud.

Anchors are DERIVED, not literal (rule 5): the arc id and the watchdog pid come from the
log itself, not from a snapshotted constant.

Usage:
    check_arc_status_contract.py --log <arc.log> [--live] [--min-pulses N]
    check_arc_status_contract.py --selftest        # demonstrated FAIL + non-vacuity
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404 - one `pgrep -af` call, fixed argv, no shell
import sys

PASS, FAIL, CANNOT = 0, 1, 2

# ---- signatures (regex; the format lives in arc_heartbeat.sh, mirrored here as a reader) ----
RE_PULSE = re.compile(
    r"\[ARC\s+(?P<arc>\S+)\s+[#\-]{2,}\s+.*?stage\s+\d+/\d+", re.IGNORECASE
)
RE_SELFVER = re.compile(r"HEARTBEAT SELF-VERIFY:\s*ok", re.IGNORECASE)
RE_MARKER = re.compile(r"\*{2,}\s*ARC\s+completed\s*\*{2,}", re.IGNORECASE)
RE_TEARDN = re.compile(r"WATCHDOG TEARDOWN:\s*(confirmed|dead|gone)", re.IGNORECASE)
RE_LEAK = re.compile(r"WATCHDOG.*(still\s+alive|ALIVE|not\s+dead)", re.IGNORECASE)
RE_WD_PID = re.compile(r"watchdog.*?pid[=\s:]+(?P<pid>\d+)", re.IGNORECASE)
# cc's own watchdog signature for the live scan; kernel thread is excluded separately.
WD_SIG = os.environ.get("ARC_WD_SIG", r"arc_heartbeat|NIX_ARC_WATCHDOG")
KERNEL_WD = re.compile(r"\[watchdogd\]|(?:^|\s)watchdogd(?:\s|$)")


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _split_at_marker(text: str):
    """Return (before, after, matched) around the FIRST completion marker."""
    m = RE_MARKER.search(text)
    if not m:
        return text, "", None
    return text[: m.start()], text[m.end() :], m


def audit_log(text: str, min_pulses: int = 1):
    """Return (verdict, reasons:list[str], facts:dict)."""
    reasons: list[str] = []
    facts: dict = {}

    before, after, marker = _split_at_marker(text)

    # (0) NON-VACUITY: a run that never reached close-out cannot be judged for
    #     "reached close-out without heartbeats". CANNOT-MEASURE, never PASS/FAIL.
    if marker is None:
        return (
            CANNOT,
            ["no ARC-completed marker in log: run did not reach close-out"],
            facts,
        )

    # (0b) NON-VACUITY of the detector itself (rule 4): prove the pulse detector's
    #      scope is real by recording what it can see, before trusting an absence.
    pulses = RE_PULSE.findall(before)
    facts["pulses_before_marker"] = len(pulses)
    facts["arc"] = pulses[0] if pulses else None

    # (1) HEARTBEAT EVIDENCE
    if len(pulses) < min_pulses:
        reasons.append(
            f"heartbeat evidence missing: {len(pulses)} pulse line(s) before marker, "
            f"need >= {min_pulses}"
        )
    if not RE_SELFVER.search(before):
        reasons.append(
            "no watchdog self-verify line (HEARTBEAT SELF-VERIFY: ok) before marker"
        )

    # (2) TEARDOWN PROOF — cc's own watchdog, before the marker, and NOT [watchdogd].
    teardown_lines = [
        ln
        for ln in before.splitlines()
        if RE_TEARDN.search(ln) and not KERNEL_WD.search(ln)
    ]
    facts["teardown_confirmations"] = len(teardown_lines)
    if not teardown_lines:
        reasons.append(
            "no watchdog-teardown confirmation for cc's own watchdog before marker"
        )

    # (3) LEAK IN LOG — a 'still alive' line AFTER the marker for cc's own watchdog.
    leak_lines = [
        ln
        for ln in after.splitlines()
        if RE_LEAK.search(ln) and not KERNEL_WD.search(ln)
    ]
    if leak_lines:
        reasons.append(
            f"cc watchdog reported alive after marker: {leak_lines[0].strip()!r}"
        )

    # derive self-reported watchdog pid (for the optional --live arm)
    mpid = RE_WD_PID.search(text)
    facts["watchdog_pid"] = int(mpid.group("pid")) if mpid else None

    return (FAIL if reasons else PASS), reasons, facts


def live_watchdog_leak(sig: str = WD_SIG):
    """Best-effort: is a process matching cc's watchdog signature alive, excluding
    the kernel [watchdogd]? Returns (found:bool|None, detail). None = cannot scan."""
    if not shutil.which("pgrep"):
        return None, "pgrep unavailable"
    try:
        # -a prints cmdline so we can filter the kernel thread out ourselves.
        out = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, PATH lookup of a
            # coreutils-class binary; the pattern is a regex passed as an argument, never
            # interpolated into a command line.
            ["pgrep", "-af", sig],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # DELIBERATELY BLIND (check contract rule 1): every failure of the
        # instrument must reach CANNOT-MEASURE. A narrower clause would let one
        # unanticipated exception type escape and be reported by the interpreter
        # as exit 1 — the exact code this gate uses for "violation detected", and
        # the measured incident VERIFY-AND-CHECKS.md B.2 exists to record.
        return None, f"pgrep error: {exc}"
    hits = [ln for ln in out.splitlines() if ln.strip() and not KERNEL_WD.search(ln)]
    return (len(hits) > 0), (hits[0] if hits else "no live cc watchdog")


def run(log_path: str, live: bool, min_pulses: int) -> int:
    """Audit one arc log and print the verdict. Returns the exit code."""
    if not log_path or not os.path.isfile(log_path):
        print(f"[CANNOT] arc log not found: {log_path}")
        return CANNOT
    verdict, reasons, facts = audit_log(_read(log_path), min_pulses=min_pulses)

    if live and verdict != CANNOT:
        found, detail = live_watchdog_leak()
        if found is True:
            verdict = FAIL
            reasons.append(
                f"LIVE: cc watchdog still running (not [watchdogd]): {detail}"
            )
        elif found is None:
            print(f"[note] live scan skipped: {detail}")

    tag = {PASS: "PASS", FAIL: "FAIL", CANNOT: "CANNOT-MEASURE"}[verdict]
    print(
        f"[{tag}] arc_status_contract  arc={facts.get('arc')}  "
        f"pulses={facts.get('pulses_before_marker')}  "
        f"teardowns={facts.get('teardown_confirmations')}  "
        f"wd_pid={facts.get('watchdog_pid')}"
    )
    for r in reasons:
        print(f"    - {r}")
    return verdict


# --------------------------------------------------------------------------- #
#  SELF-TEST: demonstrated FAIL in every arm + non-vacuity, per the check contract
# --------------------------------------------------------------------------- #
_CLEAN = """\
kickoff: ARC 041 INTERIOR, 15 stages
watchdog started pid=3941502
[ARC 041 ###----- 20% stage 3/15 - ops preflight - 6m - ~24m - HEAD a70a2c4 ADVANCED]
HEARTBEAT SELF-VERIFY: ok (emitter produced a pulse)
[ARC 041 #####--- 60% stage 9/15 - implement - 25m - ~16m - HEAD a70a2c4 ADVANCED]
[watchdogd] kernel thread present pid=165   (must be ignored)
WATCHDOG TEARDOWN: confirmed dead (pid 3941502 / arc_heartbeat)
verify.py 90 | 2 | 2 | 0 | 1
**** ARC completed ****
"""


def _selftest() -> int:  # pylint: disable=too-many-locals
    cases = []

    def check(name, text, want, min_pulses=1):
        v, reasons, facts = audit_log(text, min_pulses=min_pulses)
        ok = v == want
        cases.append((name, ok, v, want, reasons))
        return ok, facts

    # NON-VACUITY FIRST: the detector must actually SEE pulses in the clean log,
    # else a later "missing pulses" FAIL would be vacuous.
    _ok0, facts0 = check("clean -> PASS", _CLEAN, PASS)
    nv = facts0.get("pulses_before_marker", 0) >= 1 and not KERNEL_WD.search("x")
    cases.append(
        (
            "non-vacuity: detector sees >=1 pulse in clean log",
            nv,
            facts0.get("pulses_before_marker"),
            ">=1",
            [],
        )
    )

    # PLANT A: strip the heartbeat pulses + self-verify -> FAIL
    plant_a = (
        "\n".join(
            ln
            for ln in _CLEAN.splitlines()
            if not RE_PULSE.search(ln) and not RE_SELFVER.search(ln)
        )
        + "\n"
    )
    check("PLANT no-heartbeat -> FAIL", plant_a, FAIL)

    # PLANT B: leave cc's watchdog alive after the marker -> FAIL
    plant_b = _CLEAN.replace(
        "**** ARC completed ****",
        "**** ARC completed ****\nWARN: WATCHDOG arc_heartbeat still alive pid=3941502",
    )
    check("PLANT leaked-watchdog -> FAIL", plant_b, FAIL)

    # PLANT C: the kernel [watchdogd] after the marker must NOT count as a leak -> PASS
    plant_c = _CLEAN.replace(
        "**** ARC completed ****",
        "**** ARC completed ****\n[watchdogd] still alive pid=165",
    )
    check("kernel [watchdogd] after marker -> still PASS", plant_c, PASS)

    # PLANT D: no marker -> CANNOT-MEASURE (non-vacuity of the whole gate)
    plant_d = _CLEAN.replace("**** ARC completed ****", "(run killed mid-flight)")
    check("no-marker -> CANNOT-MEASURE", plant_d, CANNOT)

    # PLANT E: teardown line is only for [watchdogd] -> must still FAIL (real wd not torn down)
    plant_e = _CLEAN.replace(
        "WATCHDOG TEARDOWN: confirmed dead (pid 3941502 / arc_heartbeat)",
        "WATCHDOG TEARDOWN: confirmed dead [watchdogd] kernel thread",
    )
    check("teardown only for kernel thread -> FAIL", plant_e, FAIL)

    print("=== SELF-TEST ===")
    allok = True
    for name, ok, got, want, reasons in cases:
        allok &= ok
        print(f"  [{'ok' if ok else 'XX'}] {name}  (got={got}, want={want})")
        if not ok:
            for r in reasons:
                print(f"          {r}")
    print("=== SELF-TEST", "PASS ===" if allok else "FAIL ===")
    return PASS if allok else FAIL


def main() -> int:
    """The drop-in's own CLI: --selftest, or --log <arc.log>."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--log")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--min-pulses", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.log:
        print("[CANNOT] no --log given")
        return CANNOT
    return run(args.log, args.live, args.min_pulses)


# ============================================================================
#  verify.py CONTRACT ADAPTER — APPENDED by ARC 041-T. Nothing above this line
#  was altered: the drop-in was installed byte-verbatim and this block is
#  additive.
#
#  WHY IT IS NEEDED, and it is the same reason as the sibling gate's: the
#  engine calls `run(mode, ctx) -> CheckResult` and the verbatim body defines a
#  `run(log_path, live, min_pulses) -> int`. Registering the file as shipped
#  would load cleanly and blow up on invocation. The adapter DISPATCHES on the
#  first argument's type so the CLI and the engine share ONE measurement
#  implementation (`audit_log`) rather than acquiring a second (doctrine C.9).
#
#  WHAT `--log` DEFAULTS TO UNDER THE ENGINE, and why it is CANNOT-MEASURE and
#  not PASS when there is nothing to read. `audit_log` judges the proposition
#  *this arc reached close-out while keeping the operator informed and tearing
#  its watchdog down*. With no fresh arc log the proposition has no subject, and
#  check-contract rule 10 is explicit: a safety property proven while its
#  subject is unavailable is not proven. So the bare periodic sweep — no arc
#  running, no log written in the freshness window — reports CANNOT-MEASURE and
#  costs the run one light-blue, which is the honest price. It PASSES at an
#  arc's close-out, against that arc's own log.
# ============================================================================
# pylint: disable=wrong-import-position  # the adapter is appended BELOW the
# verbatim drop-in on purpose; see the block comment above.
import time
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-position
from nixverify.contract import CheckResult, Mode, Status

# pylint: disable=duplicate-code  # the two ARC 041-T adapters are two
# instances of ONE shape (declare, dispatch, map to CheckResult). Factoring
# them into a shared helper would put a third module between every gate and
# its own verdict; the house answer to this message is the same disable.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
EXPECTED_S = 2.0
DEPENDS_ON: tuple[str, ...] = ()
#: The engine arm reads files and spawns nothing: `--live` (the only `pgrep`
#: path in this module) is NOT reachable from `_engine_run`, deliberately. A
#: process scan from inside the sweep would be measuring whatever else happens
#: to be running on the box at sweep time, not the arc the log describes.
RESOURCES: tuple[str, ...] = ()
ON_FAIL = "continue"
#: NON-CORRECTABLE. The subject is an arc's own conduct — beats emitted,
#: watchdog torn down. There is nothing on disk to repair; a gate that could
#: "fix" it would be editing the log it is reading.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is a completed run's conduct recorded in its own log; the "
    "only thing a repair could touch is the evidence"
)
#: `scripts/arc_heartbeat.sh` is the EMITTER this reader is paired with. It is
#: not a `.py`/`.json` artifact so `check_artifact_gate_coverage` does not track
#: it, but naming it here records the pairing that the ARC 041-T parity proof
#: measured.
SUBJECTS: tuple[str, ...] = ("scripts/arc_heartbeat.sh",)

NAME = "check_arc_status_contract"

#: Where an arc's own run log is written. Under `scratchpad/`, which is
#: gitignored: a run log is evidence about a run, not a tracked artifact.
ARC_LOG_DIR = "scratchpad/arc_logs"
ARC_LOG_GLOB = "*.log"
#: Beyond this the newest log is not describing anything current, and a PASS
#: read off it would be an assurance about a different week. 24 h.
ARC_LOG_MAX_AGE_S = 86400

_cli_run = run


#: The progress file the emitter reads. Its `arc=` line is the ONLY statement in
#: the tree of which arc is running RIGHT NOW.
ARC_PROGRESS = "scratchpad/arc_progress.txt"


def _running_arc(home: Path) -> str:
    """The arc id the progress file says is RUNNING, or `""` if it says none."""
    try:
        text = (home / ARC_PROGRESS).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "arc":
            return value.strip()
    return ""


def _previous_arc_log(home: Path):
    """The PREVIOUS arc's log, the arc it belongs to, and why it is unusable.

    D3.455, ARC 049. This used to take the NEWEST log unconditionally, which is
    how ARC 048 reported `[ok]` against `arc_047.log` — a COMPLETED arc's
    evidence — while ARC 048 was the arc running. The check's duty cycle is one
    arc behind (D3.433), and that is deliberate: an arc that has not finished
    has not yet done the thing being judged, and the completion marker is by
    construction the LAST token it prints. What was wrong was not the cadence
    but the SILENCE — the verdict never said which arc it concerned, so an
    `[ok]` read as a statement about the arc in progress.

    So: the running arc's own log is EXCLUDED by name, the newest of what
    remains is the previous arc's, and the arc id travels back with it. With a
    run in flight and no earlier log inside the window the answer is
    CANNOT_MEASURE naming what is missing — never a quiet fall-back onto a log
    old enough that a PASS off it is an assurance about a different week.

    Returns (path|None, arc_id, reason).
    """
    directory = home / ARC_LOG_DIR
    if not directory.is_dir():
        return None, "", f"no arc-log directory at {ARC_LOG_DIR}"
    logs = [p for p in directory.glob(ARC_LOG_GLOB) if p.is_file()]
    if not logs:
        return None, "", f"{ARC_LOG_DIR} holds no {ARC_LOG_GLOB}"
    running = _running_arc(home)
    own = f"arc_{running}.log" if running else ""
    candidates = [p for p in logs if p.name != own]
    if not candidates:
        return (
            None,
            running,
            (
                f"the only arc log in {ARC_LOG_DIR} is {own}, which belongs to the "
                f"arc RUNNING RIGHT NOW (ARC {running}). Its conduct is not "
                f"judgeable until it reaches close-out, and there is no previous "
                f"arc's log to audit instead"
            ),
        )
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    age = time.time() - newest.stat().st_mtime
    if age > ARC_LOG_MAX_AGE_S:
        return (
            None,
            running,
            (
                f"the newest log that is not the running arc's ({newest.name}) is "
                f"{int(age)}s old, past the {ARC_LOG_MAX_AGE_S}s freshness window"
                + (f"; ARC {running} is running" if running else "")
            ),
        )
    audited = newest.stem.removeprefix("arc_")
    return newest, audited, ""


def _engine_run(mode, ctx) -> CheckResult:  # pylint: disable=unused-argument
    home = Path(
        getattr(ctx, "nix_home", None) or os.environ.get("NIX_HOME", "/home/bbt/nix")
    )
    log, audited, why = _previous_arc_log(home)
    if log is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(home / ARC_LOG_DIR),
            detail=f"{why} — no arc conduct to audit in this sweep",
        )
    try:
        text = _read(str(log))
    except OSError as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(log),
            detail=f"cannot read arc log: {exc!r}",
        )

    verdict, reasons, facts = audit_log(text, min_pulses=1)
    # D3.455: the arc is NAMED in the verdict line, so an `[ok]` cannot be read
    # as a statement about whichever arc happened to be running.
    measured = (
        f"AUDITED ARC {audited or '?'} ({log.name}): arc={facts.get('arc')} "
        f"pulses={facts.get('pulses_before_marker')} "
        f"teardowns={facts.get('teardown_confirmations')} "
        f"wd_pid={facts.get('watchdog_pid')}"
    )
    if verdict == CANNOT:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(log),
            detail=(
                f"ARC {audited or '?'}: "
                + ("; ".join(reasons) or "arc log is not judgeable")
            ),
        )
    if verdict == PASS:
        return CheckResult(
            name=NAME, status=Status.PASS, site=str(log), evidence=measured
        )
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site=str(log),
        evidence=measured,
        detail="; ".join(reasons),
        action=(
            "emit beats with scripts/arc_heartbeat.sh and print "
            "'WATCHDOG TEARDOWN: confirmed dead (pid <N> / arc_heartbeat)' "
            "before the completion marker"
        ),
    )


def run(  # type: ignore[no-redef]  # pylint: disable=function-redefined
    *argv, **kwargs
):
    """Dispatch: `run(Mode, Context)` is the engine; anything else is the CLI.

    DELIBERATELY the same name as the CLI entry point above, and the shadowing
    is the mechanism rather than an accident: `nixverify.loader` binds whatever
    module-level `run` it finds, so the engine gets this one while `main()` —
    which resolved its `run` before this line executed — keeps the other. One
    measurement implementation, two callers (doctrine C.9).
    """
    if argv and isinstance(argv[0], Mode):
        return _engine_run(argv[0], argv[1] if len(argv) > 1 else None)
    return _cli_run(*argv, **kwargs)


# ---------------------------------------------------------------------------
#  __main__ — MOVED HERE by ARC 041-T, and the move is the point.
#
#  It used to sit above the adapter, which meant the CLI exited before the
#  engine entry point existed. That worked, and it worked by statement order —
#  the sort of correctness an editor breaks without a diff saying so. It also
#  left this block unable to reach `validate_result`, and
#  `scripts/tests/test_check_standalone_nonvacuity.py` requires every
#  `checks/check_*.py` to route its `__main__` through the §5 validation (or
#  through `standalone_main`, which applies it on the check's behalf). The test
#  caught exactly that and named both files.
#
#  TWO SURFACES, ONE MEASUREMENT. The drop-in's own flags keep the drop-in's own
#  CLI, because the arc brief's binding steps are spelled in them and because a
#  `--selftest` has no `CheckResult` to validate. Everything else — the flagless
#  measure-only default and the shared actuation flags — goes through
#  `standalone_main`, which reads CORRECTABLE from this module's declarations,
#  applies `validate_result`, and maps the status to the exit code. Neither
#  surface re-implements the measurement: both end at `run`.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    _OWN_FLAGS = ("--selftest", "--log", "--live", "--min-pulses")
    try:
        if any(a.split("=", 1)[0] in _OWN_FLAGS for a in sys.argv[1:]):
            sys.exit(main())
        sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
    except SystemExit:
        raise
    except BaseException as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # rule 1: never collapse an uncaught error to FAIL.
        print(f"[CANNOT] uncaught in check_arc_status_contract: {exc!r}")
        sys.exit(CANNOT)
