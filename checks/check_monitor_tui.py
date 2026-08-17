#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: the three MON-1 operator-TUI artifacts behave EXACTLY as recorded.

ARC 035 / Phase 0.2. `scripts/monitor.py`, `scripts/harness.py` and
`scripts/pty_test.py` sat in `checks/gate_coverage_baseline.json`'s `artifacts`
ratchet with their owner walked `ARC 031 -> 032 -> 033 -> 035` — four arcs, three
re-ownings, one over the operator ceiling (D2.31). D3.113 retired the previous
`check_monitor.py` and recorded the reason as *"the tooling is deprecated and not
being extended, so per C1 a plant here would measure nothing."*

**That sentence is the thing this gate contradicts, and it is worth being precise
about why.** `check_monitor` was retired because it FAILED — the harness reports
real disagreements with `monitor.py` on this node. Retiring an instrument because
its subject is red is the same move as re-running a check under a friendlier
interpreter until it goes green, which this tree refuses everywhere else. A plant
in `monitor.py` measures a great deal; what it does NOT do is turn a deprecated
TUI green, and those are different claims.

So the property this gate proves is not *"the TUI is correct"*. It is:

    **the three artifacts execute, and their measured behaviour is EXACTLY the
    behaviour recorded here — no better and no worse.**

That is a real, falsifiable property of a real execution, and it is the strongest
honest one available over tooling nobody is repairing.

## The three arms

* **ARM 1 — `monitor.py --selftest` exits 0.** The TUI's own internal
  consistency checks, run in a real child interpreter.
* **ARM 2 — `pty_test.py` exits 0 and reports zero failures.** This one forks a
  real pty, drives the real curses loop, sends real keys, storms the terminal
  size, and asserts the alternate screen is restored. It is the most
  load-bearing arm: it is the only place in this tree where curses runs.
  **One of its arms is a clock, and is treated as one** — see
  `_TIMING_SENSITIVE_PTY_ARMS` and CHECK-DEBT D3.204. Measured, not assumed:
  the flake was observed while writing this gate, on the same page as the
  §7.12 sentence predicting it.
* **ARM 3 — `harness.py`'s failing set is EXACTLY `KNOWN_RED`.** Two-way, and
  the second direction is what stops this becoming a suppression file:
  - a failure NOT in `KNOWN_RED` is a **regression** — new breakage;
  - a member of `KNOWN_RED` that no longer fails is a **stale pin** — the
    record is lying about the subject, and the fix is to shrink the pin in the
    same commit that fixed the behaviour.
  Identical in shape to `check_artifact_gate_coverage`'s ratchet, and for
  identical reasons: a one-directional accepted set rots.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **`harness.py` could die after three checks and its (empty) failing set
   could be compared against an (empty) pin.** *Closed:* `KNOWN_RED` is
   non-empty today, so an early death yields a set that is missing members and
   reddens as a stale pin — and independently, `MIN_CREDIBLE_CHECKS` requires
   the observed check population to be at least a floor, or the verdict is
   CANNOT_MEASURE naming the count. A harness that did not run is not a
   harness that passed.
2. **A subprocess could fail to start and be read as a clean exit.** *Closed:*
   every arm asserts on the child's own reported RESULT LINE as well as its
   return code — check-contract rule 11, the reason and not only the integer.
   `pty_test.py` printing `PTY RESULT: 0 failures` is a different fact from
   `pty_test.py` exiting 0, and both are required.
3. **`KNOWN_RED` could be regenerated from the run.** An instrument that
   rewrites its own baseline manufactures its own green — the exact sentence
   `gate_coverage_baseline.json` opens with. *Closed:* `KNOWN_RED` is a literal
   in this file, hand-entered from two independent runs that agreed, and
   nothing in this gate writes it.
4. **The pin could drift with load.** A flaky harness arm would make this gate
   flap and the flap would eventually be silenced by widening the pin.
   *Closed as far as it can be:* the recorded set was taken from two
   consecutive runs whose failing sets were byte-identical. **Not closed, and
   named:** two runs is not a proof of determinism. If this gate ever flaps,
   the honest repair is a CHECK-DEBT row naming the flaky arm, never a wider
   pin.
5. **The artifacts could be run from somewhere other than `ctx.nix_home`.**
   *Closed:* all three paths are resolved under `ctx.nix_home` and the gate is
   CANNOT_MEASURE if any is absent.

## Why PASS and not GUARDED

Check-contract rule 4 makes GUARDED *"measured subject + known-red marker naming
the discharging arc"*. That fits a red whose REPAIR is deferred to a named arc.
Here no repair is owed by anyone: the operator's MON-1 ruling deprecated the TUI
and D3.113 recorded that it is not being extended. A GUARDED verdict would need
a live owner, that owner would be re-pointed every arc, and four arcs later it
would be back at the ceiling this gate was written to discharge. The known reds
are enumerated in the evidence, verbatim, on every run — visible without being a
walking deferral.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 - running the three artifacts IS the subject
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
#: Forks a pty and spawns children, all inside private temp dirs. Nothing on
#: this box outside /tmp is written, and no service is touched.
DISRUPTIVE = False
TIME_BOUND = False
EXPECTED_S = 75.0
DEPENDS_ON: tuple[str, ...] = ()
#: `harness.py` and `pty_test.py` each `mkdtemp` their own fixture root and set
#: HOME into it; all three are real child interpreters.
RESOURCES: tuple[str, ...] = ("file-write:/tmp", "subprocess:python")
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is deprecated operator tooling under the MON-1 ruling "
    "(CHECK-DEBT D3.113); a gate that repaired it would be extending tooling "
    "the operator retired, and a gate that rewrote its own KNOWN_RED pin would "
    "manufacture its own green"
)
ANCHOR = "scripts/monitor.py"
SUBJECTS: tuple[str, ...] = (
    "scripts/monitor.py",
    "scripts/harness.py",
    "scripts/pty_test.py",
)

NAME = "check_monitor_tui"

#: The harness arms that FAIL on this node, measured on two consecutive runs
#: whose failing sets were identical, at ARC 035 / Phase 0.2. Hand-entered.
#: Nothing in this file writes this tuple.
#:
#: `4K shows wtok used` appears TWICE because it is asserted at two distinct
#: call sites (harness.py lines 467 and 489) and both fail; a set would have
#: silently collapsed them and hidden the repair of exactly one.
KNOWN_RED: tuple[str, ...] = (
    "3a ETA is None",
    "3d dict-form todos read",
    "4I eta basis names obs",
    "4I whole-job ETA sane",
    "4K points to statusline",
    "4K shows wtok used",
    "4K shows wtok used",
    "4Q bars blank-track (no shade glyph)",
    "4c prior points to statusline",
    "todos 20/27",
)

#: A harness that reported fewer than this many arms did not run to completion,
#: whatever it exited with. Well under the ~138 observed, so ordinary growth in
#: the harness does not trip it; far above zero, so a crashed run cannot pass.
MIN_CREDIBLE_CHECKS = 100

#: ARC 035 / 0.2, MEASURED rather than assumed. `pty: survives resize storm`
#: fires a burst of `TIOCSWINSZ` ioctls and then asserts the child is still
#: painting within a deadline. On an idle box it passed 5/5 serially and 4/4
#: under four-way concurrency; it failed ONCE, inside a pytest run that was
#: itself under load. That arm therefore measures the SCHEDULER as much as the
#: subject, and a deadline missed because the CPU was busy is not evidence
#: about `monitor.py`.
#:
#: §17 governs: a property whose instrument's precondition was not met is
#: CANNOT_MEASURE, **never a PASS** — and here, never a FAIL either, because a
#: red attributed to the wrong subject is as dishonest as a green. Widening
#: ARM 2 to tolerate this arm was the available cheap fix and is refused: a
#: tolerated failure is invisible, a CANNOT_MEASURE is loud.
#:
#: ONE arm, because one is what was observed. `pty: still alive after force
#: probe` is arguably the same class and is deliberately NOT listed — adding an
#: arm on suspicion would convert a real future break into a shrug. CHECK-DEBT
#: D3.204.
_TIMING_SENSITIVE_PTY_ARMS: frozenset[str] = frozenset({"pty: survives resize storm"})

_OK = re.compile(r"^  ok   (.+?)(?:  ::.*)?$")
_FAIL = re.compile(r"^  FAIL (.+?)(?: ::.*)?$")
_SELFTEST_OK = "SELFTEST PASS"
_PTY_CLEAN = "PTY RESULT: 0 failures"

#: Nothing here should ever approach these; they exist so a wedged child
#: reports a bounded CANNOT_MEASURE instead of hanging the whole runner.
_TIMEOUT_S = 240


def _run(python: str, script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        [python, str(script), *args],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )


def _loadavg() -> str:
    """1/5/15-minute load, for the CANNOT_MEASURE detail. Never load-bearing."""
    try:
        one, five, fifteen = __import__("os").getloadavg()
    except OSError:
        return "unavailable"
    return f"{one:.2f}/{five:.2f}/{fifteen:.2f}"


def parse_pty(stdout: str) -> tuple[list[str], list[str]]:
    """`(ok_names, fail_names)` from a `pty_test.py` run.

    `pty_test.py` prints the same `  ok   ` / `  FAIL ` shape as `harness.py`
    but with a different detail separator, so it gets its own parser rather
    than a regex widened until it swallows both.
    """
    oks: list[str] = []
    fails: list[str] = []
    for line in stdout.splitlines():
        if line.startswith("  FAIL "):
            fails.append(line[len("  FAIL ") :].split(" :: ")[0].strip())
        elif line.startswith("  ok   "):
            oks.append(line[len("  ok   ") :].split(" :: ")[0].strip())
    return oks, fails


def parse_harness(stdout: str) -> tuple[list[str], list[str]]:
    """`(ok_names, fail_names)` from a harness run. Named so it can be planted.

    Both lists preserve duplicates: the harness asserts some names at more than
    one call site, and collapsing them would let one of the two be repaired
    (or broken) invisibly.
    """
    oks: list[str] = []
    fails: list[str] = []
    for line in stdout.splitlines():
        match = _FAIL.match(line)
        if match:
            fails.append(match.group(1).strip())
            continue
        match = _OK.match(line)
        if match:
            oks.append(match.group(1).strip())
    return oks, fails


def compare_to_pin(fails: list[str], pin: tuple[str, ...]) -> list[str]:
    """Two-way diff of the observed failing set against the recorded pin."""
    observed = sorted(fails)
    expected = sorted(pin)
    if observed == expected:
        return []
    remaining = list(expected)
    regressions: list[str] = []
    for name in observed:
        if name in remaining:
            remaining.remove(name)
        else:
            regressions.append(name)
    defects: list[str] = []
    if regressions:
        defects.append(
            "ARM3 REGRESSION: harness arm(s) failing that are NOT in the "
            "recorded pin: " + "; ".join(regressions)
        )
    if remaining:
        defects.append(
            "ARM3 STALE PIN: recorded known-red arm(s) that no longer fail: "
            + "; ".join(remaining)
            + " — the record is now lying about the subject. Shrink KNOWN_RED "
            "in the same commit as the behaviour change; a pin that only ever "
            "grows is a suppression file"
        )
    return defects


def drive_artifacts(nix_home: Path, python: str) -> tuple[list[str], dict[str, int]]:
    """Execute all three artifacts. Returns `(defects, counts)`.

    Named and split out so the can-fail suite can drive the SHIPPED arms
    against a scratch tree holding a PLANTED `monitor.py`.
    """
    defects: list[str] = []
    counts: dict[str, int] = {}

    selftest = _run(python, nix_home / "scripts" / "monitor.py", "--selftest")
    if selftest.returncode != 0 or _SELFTEST_OK not in selftest.stdout:
        defects.append(
            f"ARM1: monitor.py --selftest rc={selftest.returncode}, "
            f"{_SELFTEST_OK!r} "
            f"{'present' if _SELFTEST_OK in selftest.stdout else 'ABSENT'} "
            f"in stdout — tail: {selftest.stdout.strip()[-300:]!r} "
            f"stderr: {selftest.stderr.strip()[-300:]!r}"
        )

    pty = _run(python, nix_home / "scripts" / "pty_test.py")
    _, pty_fails = parse_pty(pty.stdout)
    if pty.returncode != 0 or _PTY_CLEAN not in pty.stdout:
        hard = [name for name in pty_fails if name not in _TIMING_SENSITIVE_PTY_ARMS]
        soft = [name for name in pty_fails if name in _TIMING_SENSITIVE_PTY_ARMS]
        if not pty_fails:
            defects.append(
                f"ARM2: pty_test.py rc={pty.returncode} and {_PTY_CLEAN!r} is "
                f"ABSENT, yet no failing arm was reported — the driver did not "
                f"run to completion. stdout tail: "
                f"{pty.stdout.strip()[-300:]!r} stderr: "
                f"{pty.stderr.strip()[-300:]!r}"
            )
        elif hard:
            defects.append(
                f"ARM2: pty_test.py rc={pty.returncode}; failing arms: "
                f"{'; '.join(hard)}"
                + (f" (plus timing-sensitive: {'; '.join(soft)})" if soft else "")
                + f" stderr: {pty.stderr.strip()[-300:]!r}"
            )
        else:
            defects.append(
                f"ARM2 CANNOT_MEASURE: the ONLY failing pty arm(s) are "
                f"timing-sensitive — {'; '.join(soft)} — measured at load "
                f"average {_loadavg()}. That arm asserts liveness within a "
                f"deadline, so a busy scheduler and a broken subject are "
                f"indistinguishable here (§17). Withheld rather than tolerated: "
                f"CHECK-DEBT D3.204"
            )

    harness = _run(python, nix_home / "scripts" / "harness.py")
    oks, fails = parse_harness(harness.stdout)
    counts = {"ok": len(oks), "fail": len(fails), "total": len(oks) + len(fails)}
    if counts["total"] < MIN_CREDIBLE_CHECKS:
        defects.append(
            f"ARM3 CANNOT_MEASURE: harness.py reported only {counts['total']} "
            f"arm(s) (floor {MIN_CREDIBLE_CHECKS}), rc={harness.returncode} — "
            f"it did not run to completion, so its failing set is not a "
            f"measurement of anything. stderr: {harness.stderr.strip()[-300:]!r}"
        )
    else:
        defects += compare_to_pin(fails, KNOWN_RED)
    return defects, counts


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Execute all three MON-1 artifacts and pin their behaviour exactly."""
    try:
        missing = [rel for rel in SUBJECTS if not (ctx.nix_home / rel).is_file()]
        if missing:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=ANCHOR,
                detail=(
                    f"absent under {ctx.nix_home}: {', '.join(missing)} — "
                    f"nothing to execute, so nothing was measured (§17)"
                ),
            )
        python = sys.executable or shutil.which("python3") or "python3"
        defects, counts = drive_artifacts(ctx.nix_home, python)
        unmeasurable = [d for d in defects if "CANNOT_MEASURE" in d]
        if unmeasurable:
            # §17: an unmeasurable arm withholds the whole verdict. It does NOT
            # get to hide a FAIL from a sibling arm, so those are reported in
            # the same detail rather than dropped.
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site="scripts/harness.py"
                if any(d.startswith("ARM3") for d in unmeasurable)
                else "scripts/pty_test.py",
                detail="; ".join(defects),
            )
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=(
                    f"MON-1 artifacts: {len(defects)} defect(s) over 3 arms "
                    f"(harness {counts.get('ok')} ok / {counts.get('fail')} fail)"
                ),
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"3/3 arms: monitor.py --selftest PASS; pty_test.py 0 failures "
                f"(real pty, real curses loop); harness.py "
                f"{counts['ok']} ok / {counts['fail']} fail and the failing set "
                f"is EXACTLY the recorded pin. This is a behaviour PIN over "
                f"deprecated MON-1 tooling (D3.113), not a certification that "
                f"the TUI is correct. Known red, enumerated verbatim: "
                f"{'; '.join(KNOWN_RED)}. Interpreter: {python}"
            ),
        )
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail=(
                f"a MON-1 artifact did not finish within {_TIMEOUT_S}s "
                f"({exc.cmd}); it was killed, so nothing was measured"
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py (§4.2).
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
