#!/usr/bin/env python3
"""§6.6's FCFS fallback, measured on a Scoring process that REALLY dies.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §6.6:465 (**FALLBACK,
locked** — *"if the Scoring process is down or its table is stale, both
Allocator and Limiter fall back to first-come-first-served … a scoring outage
must NEVER halt order flow"*), §12.7:650/:662 (mirror model, freshness stamps,
*mirror incomplete ⇒ treated as stale*), §12.9 (Warning: *Scoring down ⇒ FCFS
fallback*), §11:595 (*stale/absent table ⇒ FCFS fallback, never a stall*).

Subjects: `scripts/nixscore/process.py` and the FROZEN `scripts/nixscore/seam.py`,
driven as REAL objects in REAL processes. Pattern: `scripts/wal_kill_drill.py`
and `scripts/sentinel_kill_drill.py` — a child announces its own PID on stdout,
the parent kills BY PID, and the verdict reads the KERNEL's reaped wait status
(doctrine C.9: extend the pattern, do not invent a sixth spelling).

------------------------------------------------------------------------------
§0a — WHAT WOULD HAVE TO BE TRUE FOR THIS DRILL TO MEASURE NOTHING
------------------------------------------------------------------------------

1. **Nothing was ever killed — a flag said "down".** This is the whole trap.
   Closed by `kill_mid_contention`: `os.kill(pid, SIGKILL)` against a PID the
   CHILD announced, and the verdict requires `Popen.wait`'s reaped status to be
   exactly `-SIGKILL`, plus `/proc/<pid>` absent after the reap. `control_clean`
   is the discriminator §18 demands: the identical child stopped with `SIGTERM`
   reaps `SIGNALLED_EXIT`, so "died" cannot be satisfied by "exited", and
   neither can be satisfied by "never started" (a child that never announces
   raises before any arm runs).

2. **Order flow was never flowing, so it cannot be shown not to have stopped.**
   A fallback measured on a reader that made three decisions has measured
   nothing. Closed by `MIN_DECISIONS_PRE`/`MIN_DECISIONS_POST` floors and by
   `MIN_RANKED_PRE`: the arbitration loop must have been RANKING — i.e. the
   ranking table was live and deciding — before the kill, or the "fallback" is
   just a cold mirror that was never anything else.

3. **The FCFS was already there.** If the reader had been falling back from the
   start, the kill changed nothing. Closed by requiring `ranked_pre` above its
   floor and `fcfs_pre == 0`, and by `control_no_kill`, which runs the same loop
   for the same wall-clock with the publisher ALIVE and requires **zero** FCFS
   verdicts. That control is the un-break half: it is what makes the FCFS in the
   kill arm attributable to the kill.

4. **Staleness is a proxy for "the process died".** Then a stale-but-present
   table from a LIVE process would be read as fresh, which is the silent failure
   this whole mandate is aimed at. Closed by `staleness_boundary`, where the
   Scoring process stays ALIVE and simply stops publishing: the table is real,
   present, well-formed and old, and the fallback must fire on the CLOCK alone.
   Driven from both sides of the threshold plus never-fed, because the middle of
   the range is the one place a broken predicate and a correct one agree.

5. **"Order flow did not halt" is asserted, not measured.** Closed by recording
   a monotonic timestamp for every single decision and reporting the WORST gap
   between consecutive ones — including the gap that straddles the kill instant.
   A mean would hide the one event that matters.

6. **The reader survived because it never saw the death.** Closed by holding the
   subscriber socket OPEN across the kill and reporting `rows_held_at_first_fcfs`:
   the mirror is complete, populated and confident at the moment it falls back.
   That is C2's stale-but-present case arriving by C1's route, and it is the
   configuration in which a naive freshness check is silently wrong.

------------------------------------------------------------------------------
WHAT THIS DRILL DOES NOT PROVE, STATED RATHER THAN IMPLIED
------------------------------------------------------------------------------

**There is no Allocator or Limiter here.** §6.6 names them as the two readers;
neither has a run loop in this tree yet (sub-agent E owns the Allocator's
consumption). The reader driven here is `nixscore.publisher.RankingReader` — the
shipped consumer-side plumbing both of them will hold — so what is proven is
that the READ PATH survives and keeps deciding. That an Allocator wired to it
also keeps proposing is a separate claim and is not made.

**And no score survives anything.** `EphemeralScoreStore` is a stub with
`durable = False`. §6.6's *"persists across process death"* is sub-agent D's
store and is deliberately NOT implemented here; the restart arm therefore
measures that the READER re-acquires, not that the SCORES did.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import secrets
import signal
import subprocess  # nosec B404 - launches sys.executable with an argv built here
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.append(str(_HERE))

# pylint: disable=wrong-import-position
from nixbus.statebus import StateSubscriber, endpoint_for
from nixscore.process import (
    SCORING_DOWN_CODE,
    SIGNALLED_EXIT,
    FallbackAlarm,
    RecordingAlertSink,
)

# ARC 037 (CHECK-DEBT D3.271): `RankingReader` moved here from
# `nixscore.process` when the two same-named classes ARC 036's parallel
# sub-agents invented were COLLAPSED into one. The surviving class kept the
# direct-poll `pump` this drill depends on (D3.240) — see its docstring.
from nixscore.publisher import RankingReader
from nixscore.seam import RANKING_TOPIC

#: The two contenders. §6.6's arbitration compares the competing PAIR-rows, so
#: both live on one symbol: two strategies GO on ES and only one can be fed.
FIRST = ("alpha", "ES")
SECOND = ("bravo", "ES")

#: The reader's freshness threshold. Short so the drill is a drill; the property
#: is that the transition happens at THIS number of real seconds after the last
#: update, whatever the number is.
STALE_AFTER_S = 0.5

#: How long the Scoring process runs before the kill, and how long the
#: arbitration loop keeps deciding afterwards. The post window is comfortably
#: past the freshness threshold so the transition is inside the measurement.
PRE_KILL_S = 0.45
POST_KILL_S = STALE_AFTER_S + 0.55

#: Ceiling on reaping a signalled child. A miss here is a broken machine.
REAP_TIMEOUT_S = 20.0

#: Poll budget for the pump on the DECISION loop: zero, a non-blocking sweep.
#: The order-flow measurement is a statement about how often a decision can be
#: taken, and a blocking poll on that loop would put the socket's latency into
#: the number this drill exists to report.
PUMP_MS = 0

#: Poll budget for the STARTUP wait, where blocking is correct: nothing is being
#: measured yet and the arm cannot begin until a real snapshot has arrived.
STARTUP_PUMP_MS = 50


def _child_argv(endpoint: str, *, interval_s: float) -> list[str]:
    """argv for one Scoring process. Built here; never a shell string."""
    module = _HERE / "nixscore" / "process.py"
    return [
        sys.executable,
        str(module),
        "--endpoint",
        endpoint,
        "--interval-s",
        str(interval_s),
        "--score",
        f"{FIRST[0]},{FIRST[1]},900.0,14",
        "--score",
        f"{SECOND[0]},{SECOND[1]},100.0,11",
    ]


def spawn_scoring(
    endpoint: str, *, interval_s: float = 0.05
) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    """Start a real Scoring process and read its self-announcement.

    Raises if the child never spoke — a child that failed to start must not be
    reported as a child that died (check contract §18).
    """
    # pylint: disable=consider-using-with
    # The child outlives this call by design; every caller owns the kill and the
    # reap on every path, including the paths where the arm fails.
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        _child_argv(endpoint, interval_s=interval_s),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=REAP_TIMEOUT_S)
        stderr = (proc.stderr.read() if proc.stderr else "")[:800]
        raise RuntimeError(f"Scoring child printed no announcement; stderr={stderr!r}")
    return proc, json.loads(line)


def open_reader(endpoint: str) -> RankingReader:
    """A real subscriber on a real socket, wrapped in the shipped reader.

    The subscriber is built HERE and handed in, rather than letting the reader
    build its own, because this drill is the case the reader's second
    construction shape exists for: a consumer that owns its socket. The reader
    takes over its lifetime — `reader.close()` releases it.
    """
    return RankingReader(
        StateSubscriber(endpoint, [RANKING_TOPIC]), stale_after_s=STALE_AFTER_S
    )


def pump_until_fresh(reader: RankingReader, budget_s: float = 5.0) -> float | None:
    """Pump until the mirror holds a snapshot. Returns the monotonic time it landed."""
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        # `.accepted` and not the PumpResult itself: a `PumpResult` is a
        # populated tuple and is therefore ALWAYS truthy, so testing the object
        # would silently drop the "a snapshot actually landed" half of this
        # condition. ARC 037, at the collapse (D3.271).
        if reader.pump(STARTUP_PUMP_MS).accepted and reader.mirror.fresh():
            return time.monotonic()
    return None


class DecisionLog:
    """Every arbitration, with the monotonic instant it was decided.

    A list and not a counter: *"order flow did not halt"* is a statement about
    the largest GAP between consecutive decisions, and a counter cannot answer
    it. The raw list stays in memory and only the derived figures are reported —
    thousands of rows of JSON would bury the four numbers that matter.
    """

    def __init__(self) -> None:
        self.rows: list[tuple[float, str, str]] = []
        self.errors: list[str] = []

    def record(self, reader: RankingReader) -> None:
        """One decision. An exception out of the order path is a RECORDED defect."""
        try:
            verdict = reader.arbitrate(FIRST, SECOND)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            self.errors.append(f"{type(exc).__name__}: {exc}")
            return
        self.rows.append((time.monotonic(), str(verdict.outcome), verdict.reason))

    def since(self, mark: float) -> list[tuple[float, str, str]]:
        """Decisions taken at or after `mark`."""
        return [row for row in self.rows if row[0] >= mark]

    def before(self, mark: float) -> list[tuple[float, str, str]]:
        """Decisions taken strictly before `mark`."""
        return [row for row in self.rows if row[0] < mark]

    def max_gap_s(self) -> float:
        """The WORST interval between consecutive decisions. Never the mean."""
        stamps = [row[0] for row in self.rows]
        return max(
            (later - earlier for earlier, later in itertools.pairwise(stamps)),
            default=0.0,
        )

    def first_of(self, outcome: str, mark: float) -> tuple[float, str, str] | None:
        """The first decision with `outcome` at or after `mark`."""
        for row in self.since(mark):
            if row[1] == outcome:
                return row
        return None


def _drive_until(
    reader: RankingReader, log: DecisionLog, alarm: FallbackAlarm, until: float
) -> None:
    """Pump and decide, flat out, until the monotonic deadline."""
    while time.monotonic() < until:
        reader.pump(PUMP_MS)
        alarm.poll()
        log.record(reader)


def _counts(rows: list[tuple[float, str, str]]) -> dict[str, int]:
    """How many of each outcome, plus the total."""
    return {
        "decisions": len(rows),
        "ranked": sum(1 for row in rows if row[1] == "ranked"),
        "fcfs": sum(1 for row in rows if row[1] == "fcfs"),
    }


def contender_rows(reader: RankingReader) -> int:
    """How many of the two contenders' pair-rows the mirror still holds.

    Read through the seam's own `lookup`, never through its private dict: the
    number that matters is whether the table the reader is about to fall back
    FROM is populated, and `lookup` is the verb an Allocator would use.
    """
    return sum(
        1 for key in (FIRST, SECOND) if reader.mirror.lookup(key[0], key[1]) is not None
    )


def _proc_gone(pid: int) -> bool:
    """Whether `/proc/<pid>` is absent. Read AFTER the reap, so it must be."""
    return not Path(f"/proc/{pid}").exists()


# ---------------------------------------------------------------------------
# ARM 1 — the kill, mid-contention
# ---------------------------------------------------------------------------


def kill_mid_contention(root: Path) -> dict[str, Any]:
    """SIGKILL a live Scoring process mid-arbitration and report what the reader did."""
    endpoint = endpoint_for("rank-kill", root)
    proc, hello = spawn_scoring(endpoint)
    reader = open_reader(endpoint)
    sink = RecordingAlertSink()
    alarm = FallbackAlarm(reader.mirror, alert=sink)
    log = DecisionLog()
    try:
        first_apply = pump_until_fresh(reader)
        alarm.poll()
        _drive_until(reader, log, alarm, time.monotonic() + PRE_KILL_S)
        last_apply_age = reader.mirror.age_s()
        alive_before = _proc_gone(int(hello["pid"])) is False
        os.kill(int(hello["pid"]), signal.SIGKILL)
        kill_mono = time.monotonic()
        status = proc.wait(timeout=REAP_TIMEOUT_S)
        _drive_until(reader, log, alarm, kill_mono + POST_KILL_S)
    finally:
        if proc.poll() is None:  # pragma: no cover - only if the kill missed
            proc.kill()
            proc.wait(timeout=REAP_TIMEOUT_S)
        rows_at_end = contender_rows(reader)
        reader.close()
    first_fcfs = log.first_of("fcfs", kill_mono)
    return {
        "arm": "kill_mid_contention",
        "endpoint": endpoint,
        "pid": int(hello["pid"]),
        "announced": hello,
        "signal": "SIGKILL",
        "signal_number": int(signal.SIGKILL),
        "reap_status": status,
        "expected_reap_status": -int(signal.SIGKILL),
        "pid_alive_before_kill": alive_before,
        "pid_gone_after_reap": _proc_gone(int(hello["pid"])),
        "snapshot_landed": first_apply is not None,
        "snapshots_applied": reader.applied,
        "stale_after_s": STALE_AFTER_S,
        "table_age_at_kill_s": last_apply_age,
        "pre": _counts(log.before(kill_mono)),
        "post": _counts(log.since(kill_mono)),
        "max_decision_gap_s": log.max_gap_s(),
        "gap_across_kill_s": (
            (log.since(kill_mono)[0][0] - log.before(kill_mono)[-1][0])
            if log.since(kill_mono) and log.before(kill_mono)
            else None
        ),
        "frozen_table_window_s": (
            None if first_fcfs is None else first_fcfs[0] - kill_mono
        ),
        "first_fcfs_reason": None if first_fcfs is None else first_fcfs[2],
        "rows_held_at_first_fcfs": rows_at_end,
        "order_path_exceptions": log.errors,
        "alerts": sink.alerts,
        "alert_codes": list(sink.codes()),
    }


# ---------------------------------------------------------------------------
# ARM 2 — the controls
# ---------------------------------------------------------------------------


def control_no_kill(root: Path) -> dict[str, Any]:
    """The UN-BREAK half: the identical loop with the publisher left ALIVE."""
    endpoint = endpoint_for("rank-live", root)
    proc, hello = spawn_scoring(endpoint)
    reader = open_reader(endpoint)
    sink = RecordingAlertSink()
    alarm = FallbackAlarm(reader.mirror, alert=sink)
    log = DecisionLog()
    try:
        landed = pump_until_fresh(reader)
        alarm.poll()
        _drive_until(reader, log, alarm, time.monotonic() + PRE_KILL_S + POST_KILL_S)
        still_fresh = reader.mirror.fresh()
    finally:
        proc.terminate()
        status = proc.wait(timeout=REAP_TIMEOUT_S)
        reader.close()
    return {
        "arm": "control_no_kill",
        "endpoint": endpoint,
        "pid": int(hello["pid"]),
        "reap_status": status,
        "snapshot_landed": landed is not None,
        "snapshots_applied": reader.applied,
        "still_fresh_at_end": still_fresh,
        "counts": _counts(log.rows),
        "max_decision_gap_s": log.max_gap_s(),
        "order_path_exceptions": log.errors,
        "alert_codes": list(sink.codes()),
    }


def control_clean_exit(root: Path) -> dict[str, Any]:
    """The DISCRIMINATOR (§18): the same child stopped, not killed. Reaps 7, not -9."""
    endpoint = endpoint_for("rank-clean", root)
    proc, hello = spawn_scoring(endpoint)
    time.sleep(0.1)
    proc.send_signal(signal.SIGTERM)
    status = proc.wait(timeout=REAP_TIMEOUT_S)
    return {
        "arm": "control_clean_exit",
        "pid": int(hello["pid"]),
        "signal": "SIGTERM",
        "reap_status": status,
        "expected_reap_status": SIGNALLED_EXIT,
        "kill_reap_status_would_be": -int(signal.SIGKILL),
        "stderr": (proc.stderr.read() if proc.stderr else "")[-400:],
    }


# ---------------------------------------------------------------------------
# ARM 3 — real staleness, against a process that is STILL ALIVE
# ---------------------------------------------------------------------------


def staleness_boundary(root: Path) -> dict[str, Any]:
    """A LIVE process that stopped publishing. The clock alone must trigger FCFS.

    This is the stale-but-present case and it is the dangerous one: the table is
    real, complete and confidently answerable, and it stopped being true. Nothing
    died, so any implementation that keys freshness on process liveness rather
    than on elapsed time passes every other arm and fails here.

    Three points, because two of them are an arithmetic identity: just inside the
    threshold, just outside it, and never-fed.
    """
    endpoint = endpoint_for("rank-stale", root)
    # An interval far longer than the arm: the child publishes once at startup,
    # then only services subscriptions. It is ALIVE the whole time.
    proc, hello = spawn_scoring(endpoint, interval_s=3600.0)
    reader = open_reader(endpoint)
    cold = open_reader(endpoint_for("rank-cold", root))
    try:
        landed = pump_until_fresh(reader)
        inside = _sample_at(reader, landed, STALE_AFTER_S * 0.8)
        outside = _sample_at(reader, landed, STALE_AFTER_S * 1.2)
        cold_verdict = cold.arbitrate(FIRST, SECOND)
        never = {
            "fresh": cold.mirror.fresh(),
            "age_s": cold.mirror.age_s(),
            "outcome": str(cold_verdict.outcome),
            "reason": cold_verdict.reason,
        }
        alive = proc.poll() is None
    finally:
        proc.terminate()
        status = proc.wait(timeout=REAP_TIMEOUT_S)
        reader.close()
        cold.close()
    return {
        "arm": "staleness_boundary",
        "pid": int(hello["pid"]),
        "publisher_alive_throughout": alive,
        "reap_status": status,
        "stale_after_s": STALE_AFTER_S,
        "snapshot_landed": landed is not None,
        "inside": inside,
        "outside": outside,
        "never_fed": never,
    }


def _sample_at(reader: RankingReader, landed: float | None, offset_s: float) -> dict:
    """Sleep until `offset_s` past the snapshot and report the mirror's answer.

    No pumping, and no injected clock: the age this reads is real wall-clock
    elapsed time since a real message really arrived.
    """
    if landed is None:
        return {"measured": False, "why": "no snapshot ever landed"}
    remaining = (landed + offset_s) - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)
    verdict = reader.arbitrate(FIRST, SECOND)
    return {
        "measured": True,
        "target_offset_s": offset_s,
        "observed_age_s": reader.mirror.age_s(),
        "fresh": reader.mirror.fresh(),
        "rows_held": contender_rows(reader),
        "outcome": str(verdict.outcome),
        "winner": list(verdict.winner),
        "reason": verdict.reason,
    }


# ---------------------------------------------------------------------------
# ARM 4 — restart: does anything wedge?
# ---------------------------------------------------------------------------


def restart_after_kill(root: Path) -> dict[str, Any]:
    """Kill, relaunch on the same endpoint, and see whether the READER wedges.

    The reader is NOT restarted and NOT resubscribed. §12.7's snapshot-on-subscribe
    plus libzmq's own reconnect are what must carry it, and if they do not, an
    operator restarting Scoring would silently leave every consumer on FCFS
    forever — a degraded mode that never ends and never alerts again, because the
    alarm is edge-triggered.
    """
    endpoint = endpoint_for("rank-restart", root)
    socket_path = Path(endpoint.removeprefix("ipc://"))
    proc, hello = spawn_scoring(endpoint)
    reader = open_reader(endpoint)
    sink = RecordingAlertSink()
    alarm = FallbackAlarm(reader.mirror, alert=sink)
    log = DecisionLog()
    outcome: dict[str, Any] = {
        "arm": "restart_after_kill",
        "first_pid": int(hello["pid"]),
    }
    try:
        pump_until_fresh(reader)
        alarm.poll()
        os.kill(int(hello["pid"]), signal.SIGKILL)
        outcome["first_reap_status"] = proc.wait(timeout=REAP_TIMEOUT_S)
        outcome["stale_socket_file_survived_sigkill"] = socket_path.exists()
        _drive_until(reader, log, alarm, time.monotonic() + POST_KILL_S)
        outcome["fcfs_while_down"] = _counts(log.rows)["fcfs"]
        outcome.update(_relaunch(endpoint, reader, alarm))
    except RuntimeError as exc:
        outcome["rebound"] = False
        outcome["why"] = f"the relaunched Scoring process could not start: {exc}"
    finally:
        reader.close()
    outcome["reader_was_restarted"] = False
    outcome["reader_resubscribed"] = False
    outcome["alert_codes"] = list(sink.codes())
    return outcome


def _relaunch(
    endpoint: str, reader: RankingReader, alarm: FallbackAlarm
) -> dict[str, Any]:
    """Start a SECOND Scoring process on the same endpoint and time the re-acquire."""
    second, hello = spawn_scoring(endpoint)
    try:
        regained = _regain(reader, alarm)
    finally:
        second.terminate()
        status = second.wait(timeout=REAP_TIMEOUT_S)
    return {
        "rebound": True,
        "second_pid": int(hello["pid"]),
        "second_reap_status": status,
        "regained_s": regained,
    }


def _regain(
    reader: RankingReader, alarm: FallbackAlarm, budget_s: float = 5.0
) -> float | None:
    """Seconds until the un-restarted reader RANKS again, or None if it wedged."""
    started = time.monotonic()
    while time.monotonic() - started < budget_s:
        reader.pump(STARTUP_PUMP_MS)
        alarm.poll()
        if str(reader.arbitrate(FIRST, SECOND).outcome) == "ranked":
            return time.monotonic() - started
    return None


# ---------------------------------------------------------------------------


def run_drill(root: Path) -> dict[str, Any]:
    """Every arm, once. The check reads this dict and never re-derives it."""
    root.mkdir(parents=True, exist_ok=True)
    return {
        "nonce": f"ARC036C-{secrets.token_hex(6)}",
        "root": str(root),
        "constants": {
            "stale_after_s": STALE_AFTER_S,
            "pre_kill_s": PRE_KILL_S,
            "post_kill_s": POST_KILL_S,
            "scoring_down_code": SCORING_DOWN_CODE,
            "first": list(FIRST),
            "second": list(SECOND),
        },
        "kill": kill_mid_contention(root),
        "no_kill": control_no_kill(root),
        "clean": control_clean_exit(root),
        "stale": staleness_boundary(root),
        "restart": restart_after_kill(root),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the drill and print it as JSON."""
    parser = argparse.ArgumentParser(description="§6.6 Scoring kill drill")
    parser.add_argument("--root", type=Path, help="scratch root for bus sockets")
    args = parser.parse_args(argv)
    if args.root is not None:
        print(json.dumps(run_drill(args.root), indent=2, default=str))
        return 0
    with tempfile.TemporaryDirectory(prefix="nixscoredrill") as tmp:
        print(json.dumps(run_drill(Path(tmp)), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
