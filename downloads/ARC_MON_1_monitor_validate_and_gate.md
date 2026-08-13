# ARC MON-1 — Monitor validation on node02 + verify.py gate

===RUN SUMMARY: ARC MON-1 monitor validate + gate, Estimated run time: 15m, completes ~1% of total project (0% of the ARC 017 broker stage — orthogonal observability tooling)===

**Model:** Claude Sonnet 5 (default). No Opus/Fable escalation required.

**Files this arc touches**
- `~/nix/scripts/monitor.py` — READ/validate only (already md5 `50cf4183ea053b132cd05cc3eb4fde5a`); patch ONLY if a real node02 defect surfaces in SC-2/SC-3
- `~/nix/scripts/harness.py` — READ/validate (md5 `857b4654fc55c80bf56a265a182ffa4b`)
- `~/nix/scripts/pty_test.py` — READ/validate (md5 `54fb8594cab328f2e8eff97710bdff32`)
- `~/nix/checks/check_monitor.py` — **NEW** verify.py gate
- `~/nix/sessions/SESSION.md` — append summary (standing req)
- `~/nix/downloads/RESULTS.md` — overwrite (standing req)

**Context.** The three script files are already present on node02 and md5-matched to the architect's copies. This arc does NOT re-place them. It (a) proves the suites pass on node02, (b) proves the monitor reads the REAL `~/.claude` telemetry — the one thing still unproven — (c) fixes anything node02-specific that surfaces, and (d) builds `check_monitor.py` so the tooling becomes a first-class, non-vacuous verify.py gate rather than a loose script.

**Paramount order:** correctness → reliability → optimization. This arc is entirely in the correctness band.

---

## Preconditions (fail loud, do not proceed if unmet)

```bash
cd ~/nix/scripts
md5sum monitor.py harness.py pty_test.py
```
Expect exactly:
```
50cf4183ea053b132cd05cc3eb4fde5a  monitor.py
857b4654fc55c80bf56a265a182ffa4b  harness.py
54fb8594cab328f2e8eff97710bdff32  pty_test.py
```
If any md5 differs, STOP and report — the wrong file is on the box and every downstream result would be vacuous.

---

## SC-1 — Suites pass on node02

Run all three; capture raw output verbatim (do not summarize) into RESULTS.md.
```bash
cd ~/nix/scripts
python3 monitor.py --selftest
python3 harness.py 2>&1 | tail -5
python3 pty_test.py 2>&1 | tail -5
```
PASS = `SELFTEST PASS`, harness `RESULT: 0 failures`, pty `PTY RESULT: 0 failures`.

Vacuity guard: paste the actual final lines, not a claim of success. A green claim with no pasted evidence does not satisfy this criterion.

## SC-2 — Prove the monitor reads the REAL ~/.claude (non-vacuous)

Independently count, THEN compare to what the monitor reports.
```bash
find ~/.claude/projects -name '*.jsonl' 2>/dev/null | wc -l
find ~/.claude/todos -name '*.json' 2>/dev/null | wc -l
python3 ~/nix/scripts/monitor.py --once --width 110
```
Capture the full `--once` frame into RESULTS.md. Then assert:
- The footer `jsonl N files` N EQUALS the `find … *.jsonl | wc -l` count. If they disagree, that is the "instrument measuring nothing while reporting green" defect — record it as a defect and proceed to SC-3.
- The DISCOVERY panel is absent. If present, transcribe every line it names.

If `~/.claude/projects` does not exist or holds 0 jsonl (no Claude Code history on node02): record this explicitly. The gate (SC-4) will correctly return CANNOT-MEASURE (exit 2) in that state; note it as a known-red condition to discharge once real sessions exist, naming this arc.

## SC-3 — Fix only real defects (no phantom fixes)

If SC-2 surfaced a footer/find mismatch, a DISCOVERY path miss against a real path, or a `--once` crash:
- Diagnose root cause against the actual node02 `~/.claude` layout (path shape, permissions, jsonl schema).
- Apply the minimal fix to `monitor.py`.
- Re-run SC-1 and SC-2; both must pass post-fix.
- Document the defect: what was observed, the root cause, the fix.

If SC-2 was clean, state explicitly "no node02 defect found — no monitor.py change." Do NOT invent a change to look productive.

## SC-4 — Build the verify.py gate `~/nix/checks/check_monitor.py`

FIRST: read `~/nix/VERIFY-AND-CHECKS.md` directly (do not work from memory or paraphrase). Then check whether an existing gate already covers scripts/tooling; if so, EXTEND it rather than duplicating. Otherwise create `check_monitor.py` satisfying the full contract:

- Exit codes: `0` PASS / `1` FAIL / `2` CANNOT-MEASURE.
- Proves REAL effective state, not a moving value: it must assert the monitor's REPORTED jsonl count equals an INDEPENDENT `rglob` of the same telemetry root. Never anchor to a fixed number (no `== 5`); the two counts move together, so the assertion cannot pass vacuously and cannot rot as usage grows.
- CANNOT-MEASURE when `~/.claude/projects` is absent or holds 0 transcripts (the read cannot be proven either way).
- Ships a DEMONSTRATED, reachable FAIL path (`CHECK_MONITOR_FORCE_FAIL=1`).
- Fails closed and loud: any unhandled exception exits 1 with a specific message, never a silent pass.
- Vacuity question, answered in a comment: "What would have to be true for this gate to pass while measuring nothing?" — Answer: the monitor would have to report a jsonl count matching disk while actually reading nothing, which the independent-rglob cross-check makes impossible; and the suites would have to pass while broken, which the FORCE_FAIL demonstration and the blind-instrument branch guard against.

A validated reference implementation is provided below. Reconcile it against the ACTUAL VERIFY-AND-CHECKS.md contract on node02 (helper names, registration convention, output format) and adjust to match house style — the logic is proven, the packaging must conform.

Then prove the gate on the box across every branch:
```bash
cd ~/nix
python3 checks/check_monitor.py ; echo "PASS-path exit: $?"          # expect 0 (or 2 if no telemetry)
CHECK_MONITOR_FORCE_FAIL=1 python3 checks/check_monitor.py ; echo "FAIL-path exit: $?"   # expect 1
python3 verify.py 2>&1 | grep -i monitor   # gate is picked up by the runner
```
Paste all three results.

## SC-5 — Track in git (prove coverage by TRACKING, not naming)

This is the ARC 014–016 lesson applied: untracked files make gate evidence vacuous.
```bash
cd ~/nix
git add -f scripts/monitor.py scripts/harness.py scripts/pty_test.py checks/check_monitor.py
git ls-files scripts/monitor.py scripts/harness.py scripts/pty_test.py checks/check_monitor.py
git status --porcelain scripts/ checks/check_monitor.py
git commit -m "ARC MON-1: track monitor tooling + verify.py gate"
```
`git ls-files` MUST list all four (proof they are tracked, not merely present). `git status --porcelain` for those paths MUST be empty after commit. If `.gitignore` swallows any, use `-f` and note it — that silent-ignore is exactly the broker-package failure mode.

---

## Standing arc requirements (no exceptions)

1. Append this arc's summary to the END of `~/nix/sessions/SESSION.md`.
2. OVERWRITE `~/nix/downloads/RESULTS.md` with this arc's results (raw SC-1/SC-2 output pasted, not summarized — derive-never-restate).
3. As the FINAL action, `cat ~/nix/sessions/SESSION.md` and `cat ~/nix/downloads/RESULTS.md`, and paste both resulting states into the chat response BEFORE declaring completion.
4. Do not declare `**** ARC completed ****` without step 3's paste.

---

## Reference implementation — `~/nix/checks/check_monitor.py`

Validated by the architect across PASS / CANNOT-MEASURE(×2) / forced-FAIL / blind-instrument-FAIL / regressed-suite-FAIL. md5 `a9f2c28bc9b03c63ded531fd0e5c3d43`. Reconcile packaging with VERIFY-AND-CHECKS.md before finalizing.

```python
#!/usr/bin/env python3
"""check_monitor.py -- verify.py gate for the arc-monitor tooling.

PROPERTY PROVEN (real, effective, on THIS host):
  monitor.py is present, internally self-consistent (its own selftest + both
  test harnesses pass), AND can actually observe the live Claude Code telemetry
  surface -- i.e. the count of session transcripts it REPORTS equals the count
  that independently exists on disk. An instrument that prints a frame but reads
  zero files while files exist is the "measuring nothing while reporting green"
  failure this gate is built to catch.

EXIT CONTRACT (per VERIFY-AND-CHECKS.md):
  0 = PASS            all checks proved
  1 = FAIL            a check failed (fails closed and loud)
  2 = CANNOT-MEASURE  no telemetry exists to read (no ~/.claude/projects
                      transcripts), so the read cannot be proven either way

NON-VACUITY:
  The core assertion compares two numbers that move TOGETHER -- the monitor's
  reported jsonl count and an independent rglob of the same tree. It never
  anchors to a fixed number (e.g. "== 5"), so it cannot pass by coincidence and
  cannot rot as usage grows. If the monitor silently stopped reading, reported
  count would drop to 0 while the independent count stayed >0, and this gate
  would FAIL.

DEMONSTRATED FAIL PATH:
  CHECK_MONITOR_FORCE_FAIL=1 forces the failure branch, proving the FAIL path is
  reachable and emits a loud, specific message (contract requirement).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
MONITOR = SCRIPTS / "monitor.py"
HARNESS = SCRIPTS / "harness.py"
PTY = SCRIPTS / "pty_test.py"
CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", os.path.expanduser("~/.claude")))

FOOTER_RE = re.compile(r"jsonl\s+(\d+)\s+files")


def fail(msg: str) -> int:
    print(f"FAIL check_monitor: {msg}", file=sys.stderr)
    return 1


def cannot(msg: str) -> int:
    print(f"CANNOT-MEASURE check_monitor: {msg}", file=sys.stderr)
    return 2


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except OSError as exc:
        return 125, "", str(exc)


def main() -> int:
    # Demonstrated, reachable FAIL path (contract requirement).
    if os.environ.get("CHECK_MONITOR_FORCE_FAIL") == "1":
        return fail("forced failure path (CHECK_MONITOR_FORCE_FAIL=1) -- "
                    "proves the FAIL branch is reachable and loud")

    # 0. artifacts present
    for f in (MONITOR, HARNESS, PTY):
        if not f.exists():
            return fail(f"missing artifact: {f}")

    # 1. self-consistency: the tool's own three suites must pass
    for label, cmd in (
        ("selftest", [sys.executable, str(MONITOR), "--selftest"]),
        ("harness", [sys.executable, str(HARNESS)]),
        ("pty_test", [sys.executable, str(PTY)]),
    ):
        rc, out, err = run(cmd, timeout=180)
        if rc != 0:
            tail = (err or out).strip().splitlines()[-3:]
            return fail(f"{label} exited {rc}: {' | '.join(tail)}")

    # 2. NON-VACUOUS read proof: what the monitor reports must equal what
    #    independently exists under the SAME telemetry root.
    projects = CLAUDE_HOME / "projects"
    if not projects.exists():
        return cannot(f"no telemetry root at {projects}; cannot prove the "
                      f"monitor reads real sessions on this host")
    independent = len(list(projects.rglob("*.jsonl")))
    if independent == 0:
        return cannot(f"{projects} exists but holds 0 *.jsonl transcripts; "
                      f"nothing to read, so the read cannot be proven")

    rc, out, err = run([sys.executable, str(MONITOR), "--once", "--width", "110",
                        "--claude-home", str(CLAUDE_HOME)], timeout=60)
    if rc != 0:
        return fail(f"monitor --once exited {rc}: {(err or '').strip()[:200]}")
    m = FOOTER_RE.search(out)
    if not m:
        return fail("monitor --once produced no 'jsonl N files' footer; "
                    "frame did not render or format changed")
    reported = int(m.group(1))
    if reported != independent:
        return fail(f"BLIND INSTRUMENT: monitor reports {reported} jsonl files "
                    f"but {independent} exist under {projects}. The monitor is "
                    f"measuring nothing while reporting a frame.")

    print(f"PASS check_monitor: suites green; monitor reads {reported}/"
          f"{independent} transcripts under {projects} (non-vacuous).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail closed and loud, never silent-pass
        print(f"FAIL check_monitor: unhandled {type(exc).__name__}: {exc}",
              file=sys.stderr)
        sys.exit(1)
```
