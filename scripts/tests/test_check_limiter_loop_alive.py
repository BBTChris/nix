"""ARC 039 / B — the can-fail suite for the Limiter-loop liveness gate.

Structure follows `docs/nix_check_contract.md` §5.1: non-vacuity FIRST, then one
PLANT per declared arm that must FAIL and NAME its site, then the same real
population passing unperturbed. A demonstration missing the last step shows only
that a gate can fail.

**EVERY CONTROL ASSERTS THE REASON** — a substring of `site` or `detail` naming
WHAT was wrong — never a status and never an exit code (check contract v2 §11 /
`docs/nix_check_contract.md` §18). `FAIL_NEEDS_OPERATOR` is one integer shared by
every arm of the gate, so a control keyed on it alone would pass whenever the
gate failed for any reason at all, including a reason the control did not plant.

**No control touches a production artifact** (doctrine C.8). Every plant builds a
throwaway `nix_home` under `tmp_path` holding a STUB `scripts/limiterd.py` and
drives the SHIPPED gate — imported by its real path, never copied — against it.
The real `scripts/limiterd.py` and `scripts/nixrisk/loop.py` are executed by the
one control that runs against `REPO` and are never written.

**Why a stub entrypoint rather than a perturbed copy of the real one.** The
property under test is a relationship between a PROCESS and a FILE — the
heartbeat advances if and only if the loop ticks. Every plant here breaks that
relationship in a way that is one line of stub and would be a large, unrealistic
edit to a working daemon; and a plant built by deleting code from the real loop
would prove only that the gate notices deleted code. The plants are therefore
minimal programs that are honest about being programs: each publishes a REAL
heartbeat through the REAL `nixsentinel.heartbeat.HeartbeatPublisher`, so the
record the gate reads is the shipped record and only the LIFETIME relationship is
false.

**Why the ghost writer self-terminates.** `test_a_HEARTBEAT_THAT_OUTLIVES...`
forks a writer that survives the gate's `SIGKILL` — that is the whole plant. A
writer with no bound would keep creating files inside the gate's
`TemporaryDirectory` while Python was removing it, and the resulting teardown
`OSError` would reach the gate's own broad `except` and turn a planted FAIL into
CANNOT_MEASURE. It therefore stops 1.5s after its parent dies (long past the
gate's post-mortem window) and again the moment its directory disappears.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import os
import subprocess  # nosec B404 - one pgrep with a literal argv, no shell
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_limiter_loop_alive as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: Every stub begins here: the real publisher, the real record name, the real
#: argument surface the gate calls with. Only the LIFETIME relationship differs.
_PREAMBLE = '''\
"""PLANT (ARC 039 / B). Not a Limiter. See test_check_limiter_loop_alive.py."""

import argparse
import os
import sys
import time

sys.path.insert(0, {scripts!r})

from nixsentinel.heartbeat import DEFAULT_HEARTBEAT_NAME, HeartbeatPublisher

parser = argparse.ArgumentParser()
parser.add_argument("--runtime-dir", required=True)
parser.add_argument("--heartbeat-interval", type=float, default=0.05)
parser.add_argument("--tick-interval", type=float, default=0.05)
parser.add_argument("--max-ticks", type=int, default=600)
args = parser.parse_args()

RUNTIME = os.path.abspath(args.runtime_dir)
os.makedirs(RUNTIME, exist_ok=True)
BEAT = os.path.join(RUNTIME, DEFAULT_HEARTBEAT_NAME)
'''

#: PLANT 1 — the heartbeat OUTLIVES the loop. A forked writer publishes under the
#: parent's pid and keeps publishing after the gate SIGKILLs the parent. This is
#: the §12.1:604-605 catastrophe: the Sentinel reads a healthy Limiter that is
#: not there.
_GHOST = (
    _PREAMBLE
    + """
OWNER = os.getpid()
if os.fork() == 0:
    # THE GHOST. Orphaned by the gate's SIGKILL and still publishing under the
    # DEAD parent's pid. Bounded twice so it cannot outlive the measurement:
    # 1.5s past its parent's death, and gone the moment its directory is.
    publisher = HeartbeatPublisher(BEAT, pid=OWNER)
    orphaned_at = None
    hard_stop = time.time() + 25.0
    while time.time() < hard_stop:
        if not os.path.isdir(RUNTIME):
            os._exit(0)
        if os.getppid() != OWNER:
            if orphaned_at is None:
                orphaned_at = time.time()
            elif time.time() - orphaned_at > 1.5:
                os._exit(0)
        try:
            publisher.publish(0)
        except Exception:
            os._exit(0)
        time.sleep(args.heartbeat_interval)
    os._exit(0)

time.sleep(30.0)
"""
)

#: PLANT 2 — a "loop" that is not a resident process. It exits at once, so
#: /proc never shows a live pid for the observation window.
_EXITS_AT_ONCE = (
    _PREAMBLE
    + """
print("started and returned; this is not a loop")
raise SystemExit(0)
"""
)

#: PLANT 3 — a real resident process publishing a real record that names SOMEONE
#: ELSE. `os.getppid()` here is the gate's own interpreter: alive, real, and not
#: the pid the gate launched.
_FOREIGN_PID = (
    _PREAMBLE
    + """
publisher = HeartbeatPublisher(BEAT, pid=os.getppid())
for _ in range(args.max_ticks):
    publisher.publish(0)
    time.sleep(args.heartbeat_interval)
"""
)


@pytest.fixture
def plant(tmp_path: Path):
    """Build a throwaway nix_home holding one stub `scripts/limiterd.py`."""

    def _build(source: str) -> Path:
        (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
        entry = tmp_path / gate.ENTRYPOINT
        entry.write_text(source.format(scripts=str(REPO / "scripts")), encoding="utf-8")
        return tmp_path

    return _build


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _survivors(token: Path) -> str:
    """Processes whose argv still mentions `token`. Empty string means none."""
    try:
        # nosec B603 B607 - literal argv, shell=False, output is read not run.
        found = subprocess.run(  # nosec B603 B607
            ["/usr/bin/pgrep", "-af", str(token)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return f"pgrep unavailable: {exc!r}"
    return found.stdout.strip()


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real subject, or refuses out loud
# --------------------------------------------------------------------------


def test_an_ABSENT_ENTRYPOINT_is_CANNOT_MEASURE_and_NAMES_THE_PATH(
    tmp_path: Path,
) -> None:
    """§5.3 / doctrine B.2: an empty scope is never a PASS."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.ENTRYPOINT in result.detail, result.detail
    assert "there is no daemon to judge" in result.detail, result.detail


def test_THE_FLOORS_ARE_FLOORS_and_none_of_them_is_zero() -> None:
    """A floor of zero is a floor that cannot refuse anything (doctrine C.4)."""
    floors = {
        "MIN_ALIVE_SAMPLES": gate.MIN_ALIVE_SAMPLES,
        "MIN_SEQ_ADVANCE": gate.MIN_SEQ_ADVANCE,
        "MIN_FROZEN_SAMPLES": gate.MIN_FROZEN_SAMPLES,
        "MIN_REPLIES": gate.MIN_REPLIES,
        "MIN_THREADS": gate.MIN_THREADS,
    }
    for name, value in floors.items():
        assert value > 0, f"{name} is {value}, which refuses nothing"


# --------------------------------------------------------------------------
# THE PLANTS — each must FAIL, and NAME the site and the condition
# --------------------------------------------------------------------------


def test_a_HEARTBEAT_THAT_OUTLIVES_THE_KILLED_LOOP_fails_and_NAMES_the_advance(
    plant,
) -> None:
    """ARM 3, the headline. The Sentinel's entire authority rests on this.

    A writer that survives the loop makes §12.1:604-605's inference false:
    heartbeat present would no longer mean Limiter alive, and a dead Limiter's
    open positions would keep their synthetic stops on paper only.
    """
    result = _run(plant(_GHOST))

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "seq advanced after death" in result.site, result.site
    assert "THE HEARTBEAT ADVANCED WITHOUT THE LOOP" in result.detail, result.detail
    assert "blind to a dead Limiter" in result.detail, result.detail


def test_an_ENTRYPOINT_THAT_RETURNS_is_not_a_LOOP_and_the_gate_SAYS_SO(
    plant,
) -> None:
    """ARM 1. A program that runs once is not a daemon, however green it exits."""
    result = _run(plant(_EXITS_AT_ONCE))

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.ENTRYPOINT in result.site, result.site
    assert "EXITED with rc 0" in result.detail, result.detail
    assert "A Limiter is a resident loop" in result.detail, result.detail
    # The §7.12 answer this control exists to prove: a subject that silences the
    # instrument by dying must not buy the milder verdict. Zero heartbeat
    # samples were taken here, and the sample-count floor did NOT convert the
    # finding into CANNOT_MEASURE.
    assert "below the floor" not in result.detail, result.detail


def test_a_HEARTBEAT_NAMING_ANOTHER_PID_fails_and_NAMES_BOTH_PIDS(plant) -> None:
    """ARM 2. A beat naming another process is not this process's beat.

    Also the LEAK control. A gate that forks a daemon and returns without
    reaping it is a defect in the instrument, not a finding about the subject —
    so after `run()` has returned, nothing launched from the plant tree may still
    be running.
    """
    home = plant(_FOREIGN_PID)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "risk_engine.heartbeat.json:pid" in result.site, result.site
    assert "is another process's beat" in result.detail, result.detail
    assert str(os.getpid()) in result.detail, result.detail
    assert _survivors(home) == "", (
        "the gate returned while a daemon it launched was still running — a gate "
        f"that leaks a process is a defect: {_survivors(home)}"
    )


# --------------------------------------------------------------------------
# THE PLANTS REMOVED — the real daemon, unperturbed, passing
# --------------------------------------------------------------------------


def test_the_REAL_LIMITER_DAEMON_passes_and_the_EVIDENCE_names_the_SIGKILL() -> None:
    """The last step §5.1 requires: the same instrument, green on real code.

    This is also the control that proves the plants above were driving anything:
    an arm that could never pass would make every plant vacuous.
    """
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert f"reaped -{9}" in result.evidence, result.evidence
    assert "present-while-alive True" in result.evidence, result.evidence
    assert "/proc present after reap False" in result.evidence, result.evidence
    assert "inbox replies accepted=[True, True, False]" in result.evidence, (
        result.evidence
    )
