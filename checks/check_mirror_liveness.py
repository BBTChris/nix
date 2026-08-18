#!/usr/bin/env python3
# pylint: disable=duplicate-code,too-many-lines
# C0302 (too-many-lines): one arm per declared property, each carrying its own
# reason string — an operator reads those instead of the code, and
# `docs/nix_check_contract.md` §5.5 keeps ONE gate to ONE property, so splitting
# the arms across two modules would create a second gate over half a property.
# §4.2 forbids the shared helper module that is the only other way to shorten it.
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`docs/nix_check_contract.md` §4.2, §4.4): the
# symbols are read STATICALLY, by AST, without importing the check, so a shared
# base module would be invisible to that reader and would break the contract to
# satisfy a similarity counter.
"""Gate: a DEAD publisher's ranking mirror goes UNRANKED, and order flow survives it.

Every bare `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen risk
spec. Where another document is meant it is named on the line.

ARC 037 / sub-agent D. The property is **§6.6:465's first condition — *"if the
Scoring process is DOWN"* — implemented as an OBSERVATION OF THE WRITER rather
than inferred from the age of what it wrote.**

Subject: `scripts/nixscore/liveness.py`, driven against REAL
`scripts/nixscore/process.py` children in REAL processes, killed with a REAL
`SIGKILL` whose reaped status this gate reads from the kernel.

------------------------------------------------------------------------------
THE DEFECT THIS GATE EXISTS OVER — `docs/CHECK-DEBT.md` D3.244
------------------------------------------------------------------------------

ARC 036 measured, on this node: **144,699 arbitrations decided RANKED from a
dead process's frozen table over a 0.483 s window**, at `stale_after_s = 0.5`.
The subscriber socket outlives the publisher, so the consumer's mirror stays
complete, populated and confident, and only the CLOCK ever ends it. Staleness is
an age over a table; liveness is a fact about the writer. §12.7's freshness
stamp measures the first and was never asked to measure the second.

`check_scoring_fallback` owns the SURVIVAL property — order flow keeps deciding
across a death — and gates the window in both directions. It does not own, and
must not be made to own, the question of what ENDS that window. This gate owns
that one, and the division is exact (doctrine C.9).

------------------------------------------------------------------------------
THE ARMS
------------------------------------------------------------------------------

* **ARM KILL — the same death, watched two ways.** One Scoring child, ONE
  `SIGKILL`, and TWO readers subscribed to the same endpoint: one with the
  liveness observer and one with `observe_liveness=False`. Both keep arbitrating
  across the death. The side-by-side is therefore the *same death at the same
  instant on the same box*, not this run against a figure quoted from a previous
  arc. The observing reader's RANKED-after-kill count must be at or below
  `MAX_RANKED_FROM_CORPSE` and its window at or below
  `MAX_LIVENESS_WINDOW_S`; the blind reader's must be ORDERS OF MAGNITUDE
  larger, or there was no defect here to repair and this gate is measuring a box
  too slow to produce one.

* **ARM FLOW — §6.6:467 outranks everything this gate is for.** *"Ranking is an
  optimization, never a safety gate: a scoring outage must NEVER halt order
  flow."* Every arbitration across the death must ANSWER. Zero exceptions out of
  the order path, a floor on the count of decisions taken after the kill, and a
  ceiling on the worst gap between two consecutive ones — including the gap that
  straddles the kill instant. A mean would hide the one event that matters.

* **ARM VACUITY — a healthy publisher is LIVE and its table is RANKED.** The
  arm that stops this whole mechanism from being a way to turn §6.6's degraded
  mode into the only mode. Zero FCFS across a live publisher, a live verdict,
  and `RankingMirror.fresh()` true at the end.

* **ARM WEDGE — the publisher that is ALIVE and has STOPPED.** It never
  disconnects, so the peer signal is blind to it by construction: the child is
  spawned with a publish interval far longer than the drive, stays alive for the
  whole arm, and is reaped cleanly afterwards. The heartbeat/sequence deadline
  must fire, the verdict must name `heartbeat` and NOT `peer`, and the
  discriminator is a THIRD reader on the same wedged publisher with the deadline
  disabled, which must still be RANKING. Without that control the wedge arm
  would be satisfied by any reader that fell back for any reason.

* **ARM RAISE — the observer itself is the new failure mode.** A liveness
  observer that raises must not take order flow with it. The arm plants an
  observer whose `observe()` raises on every call, drives real arbitrations
  through the shipped `RankingReader.pump`, and requires: no exception out of
  the order path, every decision answered, the verdict `not live` with signal
  `observer`, and the exception's type NAMED in the reason. Fail closed to
  FCFS, which is a decision and never a refusal.

* **ARM SHAPE — the hazard stated backwards.** Liveness makes the fallback fire
  SOONER; it may never make it fail, raise, block or deny. So: `liveness.py`'s
  read verbs contain no `raise`, no loop, no `try` and no socket call; and
  `seam.py`'s `arbitrate` calls NOTHING on the observer — it reads a boolean the
  pump loop fed it. A hot path that called out to an observer would be one more
  thing that can be slow at exactly the moment a process died (§11:595).

------------------------------------------------------------------------------
THE STANDING QUESTION (`docs/debug.md` §7.12) — WHAT WOULD HAVE TO BE TRUE FOR
THIS GATE TO PASS WHILE MEASURING NOTHING
------------------------------------------------------------------------------

1. *The liveness bound never observes a dead publisher* — it could be reading a
   flag, a timeout, or nothing. **Closed by ARM KILL:** the pid is announced by
   the CHILD, the signal is `os.kill(pid, SIGKILL)`, the reaped wait status must
   be exactly `-SIGKILL`, `/proc/<pid>` must be gone after the reap, and the
   RANKED decisions counted are the ones taken AFTER that reap point. The blind
   reader on the same socket is what proves the window was ended by the
   observation rather than by the arm being too short to contain one.
2. *The fallback now halts instead of falling back.* **Closed by ARM FLOW:**
   §6.6:467 outranks this gate's own subject, so a liveness observer that made
   order flow stop would be a worse outcome than D3.244. Every decision is
   counted and every exception out of the order path is a finding.
3. *The bound fires always, so there is no live path at all.* **Closed by ARM
   VACUITY:** a healthy publisher must produce a live verdict and zero FCFS. A
   liveness bound that never lets anything be ranked has turned degraded mode
   into the only mode, which is the failure this gate could most easily hide.
4. *The wedged-but-alive publisher is invisible.* **Closed by ARM WEDGE**, whose
   subject stays alive throughout (proved by a clean `SIGNALLED_EXIT` reap after
   the arm, not by an assertion) and whose control reader — same publisher,
   deadline disabled — must still be RANKING.
5. *The gate's defect functions cannot fire.* **Closed by `_arms_can_fail`**,
   which feeds every defect function a DOCTORED outcome and refuses to certify
   unless each produces a finding, and then feeds each a HEALTHY outcome and
   refuses if any produces one. A control that cannot demonstrate the defect is
   BLIND, not passing.
6. *The plants ran against the shipped files.* They do not: every AST plant is a
   source STRING authored in this file (doctrine C.8), and no arm writes to a
   production artifact.
7. *`pyzmq` is missing so the gate skipped and the runner read the skip as
   fine.* Closed by `docs/nix_check_contract.md` §17: an unimportable subject is
   `CANNOT_MEASURE`, never PASS, and the reason names the interpreter.
8. *Everything was inspected and nothing was counted.* Closed by the floors,
   every one of which is orders of magnitude below what this node measures
   (`docs/debug.md` §7.4) and none of which is zero.
"""

from __future__ import annotations

import ast
import itertools
import json
import os
import signal
import subprocess  # nosec B404 - launches sys.executable with an argv built here
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status, result_from_defects

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: The arms spawn `.venv/bin/python` children that import `pyzmq`.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Declared against what this gate OBSERVABLY does, not against what it intends
#: (check contract rule 12 / §17: the observer outranks the declaration).
#: * `subprocess:python` / `subprocess:python3` — three arms spawn
#:   `scripts/nixscore/process.py` under `sys.executable`. BOTH spellings,
#:   because the observer matches a subprocess claim by BASENAME and
#:   `sys.executable` is `.venv/bin/python` under pytest and `/usr/bin/python3`
#:   under `nix-verify.service`.
#: * `file-write:/tmp` — the bus root is a `tempfile.TemporaryDirectory`.
#: * `zmq-ipc` — real `ipc://` endpoints are bound and connected. NOT observable
#:   by `check_observed_resource_claims` (libzmq calls `bind(2)` from C, so no
#:   Python-level syscall is seen), so it is declared for the PLAN's benefit:
#:   shared with `check_state_bus`, `check_scoring_fallback`, `check_ranking_table`
#:   and the allocator mirror gates, which must not run parallel with this one.
RESOURCES: tuple[str, ...] = (
    "subprocess:python",
    "subprocess:python3",
    "file-write:/tmp",
    "zmq-ipc",
)
TIME_BOUND = True
#: Four driving arms, each spawning at least one real interpreter, plus a ~1.0 s
#: kill window and a ~0.6 s wedge sweep. MEASURED on this node at ~6 s; the
#: declaration carries headroom for a loaded box.
EXPECTED_S = 20.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what a CONSUMER concludes when the Scoring process stops "
    "existing. There is no state on disk to repair, and a 'correction' would "
    "mean editing the fallback while the fallback is the thing under "
    "measurement — the one path in §6.6 that keeps order flow alive when a "
    "process just died."
)
INSTALLABLE = False
#: The artifact this gate MEASURES, for `check_artifact_gate_coverage`.
#: `scripts/nixscore/seam.py` is deliberately NOT claimed: it is owned by
#: `check_scoring_seam`, and `scripts/nixscore/process.py` by
#: `check_scoring_fallback`. A second declarer would be the duplicate instrument
#: doctrine C.9 forbids. The ARM SHAPE reads from both of those files, which is
#: an inspection and not a claim of ownership.
SUBJECTS: tuple[str, ...] = ("scripts/nixscore/liveness.py",)

NAME = "check_mirror_liveness"

LIVENESS_MODULE = "scripts/nixscore/liveness.py"
SEAM_MODULE = "scripts/nixscore/seam.py"

#: The two contenders. §6.6's arbitration compares the competing PAIR-rows, so
#: both live on one symbol: two strategies GO on ES and only one can be fed.
FIRST = ("alpha", "ES")
SECOND = ("bravo", "ES")

#: The readers' freshness threshold, matched to `scoring_kill_drill.STALE_AFTER_S`
#: so this gate's window is directly comparable with D3.244's own figure.
STALE_AFTER_S = 0.5

#: The heartbeat/sequence deadline for ARM WEDGE. Far tighter than
#: `STALE_AFTER_S` — that is the whole point of a second signal — and far above
#: the 50 ms publish cadence the child is normally driven at.
HEARTBEAT_DEADLINE_S = 0.15

#: Drive windows.
PRE_KILL_S = 0.40
POST_KILL_S = STALE_AFTER_S + 0.55
VACUITY_S = 0.40
WEDGE_S = 0.45
RAISE_S = 0.25

#: Ceiling on reaping a signalled child. A miss here is a broken machine.
REAP_TIMEOUT_S = 20.0

#: Poll budget on the DECISION loop: zero, a non-blocking sweep. A blocking poll
#: would put the socket's latency into the number this gate exists to report.
PUMP_MS = 0
STARTUP_PUMP_MS = 50

#: FLOORS, all orders of magnitude below what this node measures (78k pre-kill
#: and 213k post-kill decisions), so they are floors and not a restatement of
#: today's throughput — a figure anchored to the current rate would redden the
#: day the box got slower for an unrelated reason (`docs/debug.md` §7.4).
MIN_PRE_DECISIONS = 200
MIN_POST_DECISIONS = 200
MIN_VACUITY_DECISIONS = 200
MIN_WEDGE_DECISIONS = 100
MIN_RAISE_DECISIONS = 50

#: THE BOUND D3.244 IS ABOUT. Zero is what this node measures; the ceiling is
#: not zero because one arbitration can be in flight in the microseconds before
#: the monitor is drained, and a gate that reddens on a scheduling accident is a
#: gate that gets widened. ARC 036's figure on the age route was **144,699**.
MAX_RANKED_FROM_CORPSE = 25

#: Ceiling on the liveness route's window. MEASURED end-to-end (SIGKILL to first
#: FCFS verdict, including the reap and this loop's own cadence) at ~3.45 ms on
#: this node; libzmq's `EVENT_DISCONNECTED` alone lands at 1.417/1.543/2.136 ms
#: (min/median/max over seven kills). Roughly 30x of headroom, and still two
#: orders of magnitude below `STALE_AFTER_S` — which is the property, because a
#: liveness window that drifts toward the threshold has become the age route.
MAX_LIVENESS_WINDOW_S = 0.100

#: How much worse the BLIND reader must be for this run to have contained a real
#: defect to repair. Not a restatement of 144,699: it is a RATIO, so it survives
#: a slower box. On this node the observed ratio is unbounded (the observing
#: reader ranks ZERO), so this is the weakest honest floor.
MIN_BLIND_RANKED = 1000

#: Ceiling on the gap between two consecutive order decisions. Observed on this
#: node: ~3.5 ms, including the gap that straddles the kill. Two orders of
#: magnitude above that, and infinitely below "halted", which is the only
#: alternative §6.6:467 cares about.
MAX_DECISION_GAP_S = 0.5

#: Read verbs of the observer that must be total: no raise, no loop, no try, no
#: socket. They are what a consumer's verdict is derived from, and the consumer
#: is an order path that has to keep going.
LIVENESS_READ_PATH = ("verdict", "seq_age_s", "peer_observed", "last_event")

#: The CONCRETE observer. The read-path scan is confined to this class, never to
#: the module: `liveness.py` also declares a `LivenessObserver` Protocol whose
#: five verbs have empty bodies, and a module-wide walk would count those stubs
#: toward the non-vacuity floor.
OBSERVER_CLASS = "PublisherLiveness"

#: Socket verbs. A call to one of these from a read verb is I/O on a path that
#: must answer at the instant a process died.
BANNED_IO_CALLS = (
    "poll",
    "recv",
    "send",
    "recv_multipart",
    "send_multipart",
    "recv_monitor_message",
    "get_monitor_socket",
    "connect",
    "bind",
)

#: Verbs the ORDER PATH must not call on an observer. `seam.py`'s `arbitrate`
#: reads a boolean the pump loop fed it; calling out to the observer would put
#: the observer's latency, and its exceptions, on the order path.
BANNED_OBSERVER_CALLS = ("observe", "verdict", "note_observe_error")

#: Constructs that make a read path stop being total.
STALLING_NODES = (ast.While, ast.For, ast.AsyncFor, ast.Await, ast.Try)


def _load(name: str) -> tuple[Any, str]:
    """Import a subject module lazily. CANNOT_MEASURE when pyzmq is absent (§17)."""
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    try:
        module = __import__(name, fromlist=["*"])
    except ImportError as exc:
        return None, (
            f"cannot import {name} under {sys.executable}: {exc!r} — the subject "
            "is unreachable, and §17 makes an unobservable subject "
            "CANNOT_MEASURE, never PASS"
        )
    return module, ""


# ---------------------------------------------------------------------------
# THE DRIVE — real children, real sockets, real signals
#
# The four `drive_*` functions carry `# pylint: disable=too-many-locals`.
# R0914 is refused rather than satisfied: every local in them is one
# MEASURED figure the arm reports by name, and the usual remedy — folding
# them into a dict as they are produced — would move the field names out of
# the reader's sight at exactly the place a reader has to check that the arm
# reports what it measured.
# ---------------------------------------------------------------------------


def _child_argv(endpoint: str, interval_s: float) -> list[str]:
    """argv for one Scoring child. Built here; never a shell string."""
    module = (
        Path(__file__).resolve().parent.parent / "scripts" / "nixscore" / "process.py"
    )
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


def spawn_scoring(endpoint: str, interval_s: float = 0.05) -> tuple[Any, dict]:
    """Start a real Scoring child and read its self-announcement.

    Raises if the child never spoke — a child that failed to start must not be
    reported as a child that died (check contract §18).
    """
    # pylint: disable=consider-using-with
    # The child outlives this call by design; every caller owns the kill and the
    # reap on every path, including the paths where the arm fails.
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        _child_argv(endpoint, interval_s),
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


class Decisions:
    """Every arbitration with the monotonic instant it was decided.

    A list and not a counter: *"order flow did not halt"* is a statement about
    the largest GAP between consecutive decisions, and a counter cannot answer
    it. Only derived figures are reported — thousands of rows would bury the
    numbers that matter.
    """

    def __init__(self) -> None:
        self.rows: list[tuple[float, str, str]] = []
        self.errors: list[str] = []

    def record(self, reader: Any) -> None:
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

    def first_fcfs(self, mark: float) -> tuple[float, str, str] | None:
        """The first FCFS decision at or after `mark`."""
        for row in self.since(mark):
            if row[1] == "fcfs":
                return row
        return None

    def max_gap_s(self) -> float:
        """The WORST interval between consecutive decisions. Never the mean."""
        stamps = [row[0] for row in self.rows]
        return max(
            (later - earlier for earlier, later in itertools.pairwise(stamps)),
            default=0.0,
        )


def counts(rows: list[tuple[float, str, str]]) -> dict[str, int]:
    """How many of each outcome, plus the total."""
    return {
        "decisions": len(rows),
        "ranked": sum(1 for row in rows if row[1] == "ranked"),
        "fcfs": sum(1 for row in rows if row[1] == "fcfs"),
    }


def _proc_gone(pid: int) -> bool:
    """Whether `/proc/<pid>` is absent. Read AFTER the reap, so it must be."""
    return not Path(f"/proc/{pid}").exists()


def _open_reader(process_mod: Any, statebus: Any, endpoint: str, **kwargs: Any) -> Any:
    """A real subscriber on a real socket, wrapped in the SHIPPED reader."""
    subscriber = statebus.StateSubscriber(endpoint, [process_mod.RANKING_TOPIC])
    return process_mod.RankingReader(subscriber, stale_after_s=STALE_AFTER_S, **kwargs)


def _warm(readers: list[Any], budget_s: float = 5.0) -> bool:
    """Pump until every reader's mirror is fresh. Returns whether all landed."""
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        for reader in readers:
            reader.pump(STARTUP_PUMP_MS)
        if all(reader.mirror.fresh() for reader in readers):
            return True
    return False


def _rows_held(reader: Any) -> int:
    """How many of the two contenders' rows the mirror still holds.

    Read through the seam's own `lookup`, never a private dict: the number that
    matters is whether the table being fallen back FROM is populated, and
    `lookup` is the verb an Allocator would use.
    """
    return sum(
        1 for key in (FIRST, SECOND) if reader.mirror.lookup(key[0], key[1]) is not None
    )


# ---------------------------------------------------------------------------
# ARM KILL + ARM FLOW — the same death, watched two ways
# ---------------------------------------------------------------------------


def drive_kill(process_mod: Any, statebus: Any, root: Path) -> dict[str, Any]:  # pylint: disable=too-many-locals
    """SIGKILL one Scoring child under TWO readers: one observing, one blind."""
    endpoint = statebus.endpoint_for("live-kill", root)
    proc, hello = spawn_scoring(endpoint)
    seeing = _open_reader(process_mod, statebus, endpoint)
    blind = _open_reader(process_mod, statebus, endpoint, observe_liveness=False)
    seeing_log = Decisions()
    blind_log = Decisions()
    kill_mono = 0.0
    status: int | None = None
    alive_before = False
    try:
        warmed = _warm([seeing, blind])
        until = time.monotonic() + PRE_KILL_S
        while time.monotonic() < until:
            seeing.pump(PUMP_MS)
            blind.pump(PUMP_MS)
            seeing_log.record(seeing)
            blind_log.record(blind)
        age_at_kill = seeing.mirror.age_s()
        alive_before = not _proc_gone(int(hello["pid"]))
        os.kill(int(hello["pid"]), signal.SIGKILL)
        kill_mono = time.monotonic()
        status = proc.wait(timeout=REAP_TIMEOUT_S)
        until = kill_mono + POST_KILL_S
        while time.monotonic() < until:
            seeing.pump(PUMP_MS)
            blind.pump(PUMP_MS)
            seeing_log.record(seeing)
            blind_log.record(blind)
    finally:
        if proc.poll() is None:  # pragma: no cover - only if the kill missed
            proc.kill()
            proc.wait(timeout=REAP_TIMEOUT_S)
        rows_at_end = _rows_held(seeing)
        observer = seeing.liveness
        signals = {
            "disconnects": getattr(observer, "disconnects", -1),
            "events_seen": getattr(observer, "events_seen", -1),
            "peer_observed": getattr(observer, "peer_observed", None),
            "last_event": getattr(observer, "last_event", ""),
        }
        liveness_lost = seeing.mirror.liveness_lost
        liveness_fed = seeing.mirror.liveness_fed
        seeing.close()
        blind.close()
    seeing_first = seeing_log.first_fcfs(kill_mono)
    blind_first = blind_log.first_fcfs(kill_mono)
    return {
        "arm": "kill",
        "pid": int(hello["pid"]),
        "warmed": warmed,
        "reap_status": status,
        "expected_reap_status": -int(signal.SIGKILL),
        "pid_alive_before_kill": alive_before,
        "pid_gone_after_reap": _proc_gone(int(hello["pid"])),
        "stale_after_s": STALE_AFTER_S,
        "table_age_at_kill_s": age_at_kill,
        "pre": counts(seeing_log.before(kill_mono)),
        "post": counts(seeing_log.since(kill_mono)),
        "blind_post": counts(blind_log.since(kill_mono)),
        "window_s": None if seeing_first is None else seeing_first[0] - kill_mono,
        "blind_window_s": None if blind_first is None else blind_first[0] - kill_mono,
        "first_fcfs_reason": "" if seeing_first is None else seeing_first[2],
        "blind_first_fcfs_reason": "" if blind_first is None else blind_first[2],
        "rows_held_at_first_fcfs": rows_at_end,
        "max_decision_gap_s": seeing_log.max_gap_s(),
        "gap_across_kill_s": (
            (seeing_log.since(kill_mono)[0][0] - seeing_log.before(kill_mono)[-1][0])
            if seeing_log.since(kill_mono) and seeing_log.before(kill_mono)
            else None
        ),
        "order_path_exceptions": seeing_log.errors,
        "liveness_lost": liveness_lost,
        "liveness_fed": liveness_fed,
        "signals": signals,
    }


def kill_defects(kill: dict) -> list[tuple[str, str]]:
    """The death was real, and the liveness bound saw it."""
    site = f"{LIVENESS_MODULE}:PublisherLiveness[peer]"
    out: list[tuple[str, str]] = []
    expected = kill.get("expected_reap_status")
    if kill.get("reap_status") != expected:
        out.append(
            (
                site,
                (
                    f"pid {kill.get('pid')} reaped {kill.get('reap_status')!r}, not "
                    f"{expected!r}. Only the kernel's reaped wait status distinguishes "
                    "a process that was KILLED from one that exited, one that failed "
                    "to start, and a flag that said 'down' (check contract §18)"
                ),
            )
        )
    if not kill.get("pid_alive_before_kill"):
        out.append(
            (site, "the pid was already gone before the signal — nothing was killed")
        )
    if not kill.get("pid_gone_after_reap"):
        out.append((site, f"/proc/{kill.get('pid')} still exists after the reap"))
    if not kill.get("warmed"):
        out.append(
            (
                site,
                (
                    "a reader's mirror never went fresh before the kill — the fallback "
                    "cannot be attributed to a death that a cold reader would have "
                    "produced anyway"
                ),
            )
        )
    if int(kill.get("pre", {}).get("fcfs", 0)) != 0:
        out.append(
            (
                site,
                (
                    f"{kill['pre']['fcfs']} FCFS verdict(s) BEFORE the kill. The "
                    "fallback was already firing, so the kill changed nothing"
                ),
            )
        )
    if int(kill.get("pre", {}).get("ranked", 0)) < MIN_PRE_DECISIONS:
        out.append(
            (
                site,
                (
                    f"only {kill['pre']['ranked']} RANKED verdict(s) before the kill, "
                    f"below the {MIN_PRE_DECISIONS} floor. A reader that was never "
                    "ranking cannot be shown to have stopped"
                ),
            )
        )
    return out


def corpse_defects(kill: dict) -> list[tuple[str, str]]:
    """D3.244 itself: RANKED-from-a-corpse, bounded, against a blind control."""
    site = f"{LIVENESS_MODULE}:PublisherLiveness[window]"
    out: list[tuple[str, str]] = []
    ranked = int(kill.get("post", {}).get("ranked", 0))
    if ranked > MAX_RANKED_FROM_CORPSE:
        out.append(
            (
                site,
                (
                    f"{ranked} arbitration(s) decided RANKED from the dead process's "
                    f"frozen table, over the {MAX_RANKED_FROM_CORPSE} ceiling. That "
                    "is CHECK-DEBT D3.244 exactly: a complete, populated, confident "
                    "mirror answering from a corpse"
                ),
            )
        )
    window = kill.get("window_s")
    if window is None:
        out.append(
            (
                site,
                (
                    "the observing reader NEVER fell back to FCFS after the publisher "
                    "died — the liveness bound did not fire at all"
                ),
            )
        )
    elif float(window) > MAX_LIVENESS_WINDOW_S:
        out.append(
            (
                site,
                (
                    f"the observing reader kept RANKING for {float(window):.3f}s after "
                    f"the death, over the {MAX_LIVENESS_WINDOW_S}s ceiling. A "
                    "peer-disconnect observation costs milliseconds on this node; a "
                    "window that has drifted toward the "
                    f"{kill.get('stale_after_s')}s freshness threshold is the AGE "
                    "route wearing the liveness route's name"
                ),
            )
        )
    reason = str(kill.get("first_fcfs_reason") or "")
    if "writer not live" not in reason.lower():
        out.append(
            (
                site,
                (
                    f"the first post-kill FCFS named {reason!r}, which is not the "
                    "liveness trigger. The window may have been ended by the clock, "
                    "in which case nothing here measured the writer (check contract "
                    "§18)"
                ),
            )
        )
    elif "peer" not in reason.lower():
        out.append(
            (
                site,
                (
                    f"the liveness reason {reason!r} does not name the PEER signal. A "
                    "dead process and a wedged one are different incidents with "
                    "different runbooks"
                ),
            )
        )
    if int(kill.get("rows_held_at_first_fcfs", 0)) < 2:
        out.append(
            (
                site,
                (
                    "the mirror held fewer than both contenders' rows when it fell "
                    "back, so this measured the ABSENT-table trigger, not the "
                    "populated-but-dead one D3.244 is about"
                ),
            )
        )
    if int(kill.get("signals", {}).get("disconnects", 0)) < 1:
        out.append(
            (
                site,
                (
                    "the observer counted zero libzmq DISCONNECT events across a real "
                    "SIGKILL, so whatever ended the window, it was not an observation "
                    "of the writer"
                ),
            )
        )
    return out


def blind_control_defects(kill: dict) -> list[tuple[str, str]]:
    """The un-repaired half: a reader on the SAME socket, watching the SAME death.

    Without it the corpse bound is unfalsifiable — a box too slow to rank
    anything in half a second would satisfy `MAX_RANKED_FROM_CORPSE` with no
    liveness bound present at all.
    """
    site = f"{LIVENESS_MODULE}:blind-control"
    out: list[tuple[str, str]] = []
    blind = int(kill.get("blind_post", {}).get("ranked", 0))
    if blind < MIN_BLIND_RANKED:
        out.append(
            (
                site,
                (
                    f"the blind reader (observe_liveness=False) on the same socket "
                    f"ranked only {blind} time(s) from the same corpse, below the "
                    f"{MIN_BLIND_RANKED} floor. This run did not contain the defect "
                    "the liveness bound exists to repair, so the bound was not shown "
                    "to have repaired anything"
                ),
            )
        )
    reason = str(kill.get("blind_first_fcfs_reason") or "")
    if "stale" not in reason.lower():
        out.append(
            (
                site,
                (
                    f"the blind reader's first post-kill FCFS named {reason!r}, not "
                    "the table's age. The control is supposed to be the AGE route; if "
                    "it is not, the two readers are not being compared on the thing "
                    "that differs between them"
                ),
            )
        )
    return out


def flow_defects(kill: dict) -> list[tuple[str, str]]:
    """§6.6:467 — *a scoring outage must NEVER halt order flow.* Measured.

    This outranks everything else in this gate. Liveness makes the fallback fire
    SOONER; a liveness bound that made it fail, raise, block or deny would be a
    worse artifact than the defect it repairs.
    """
    site = f"{LIVENESS_MODULE}:order-flow"
    out: list[tuple[str, str]] = []
    post = kill.get("post", {})
    if int(post.get("decisions", 0)) < MIN_POST_DECISIONS:
        out.append(
            (
                site,
                (
                    f"only {post.get('decisions')} arbitration(s) after the kill, "
                    f"below the {MIN_POST_DECISIONS} floor — 'order flow continued' "
                    "is a statement about a loop that never ran"
                ),
            )
        )
    if int(post.get("decisions", 0)) != int(post.get("ranked", 0)) + int(
        post.get("fcfs", 0)
    ):
        out.append(
            (
                site,
                (
                    f"{post.get('decisions')} decisions do not decompose into "
                    f"{post.get('ranked')} ranked + {post.get('fcfs')} fcfs — a "
                    "third outcome exists, and §6.6 allows exactly two"
                ),
            )
        )
    for field in ("max_decision_gap_s", "gap_across_kill_s"):
        gap = kill.get(field)
        if gap is None or float(gap) > MAX_DECISION_GAP_S:
            out.append(
                (
                    site,
                    (
                        f"{field}={gap!r} against a {MAX_DECISION_GAP_S}s ceiling. "
                        "§6.6:467 makes ranking an optimization, never a safety gate: "
                        "the reader must keep deciding at the instant the writer dies"
                    ),
                )
            )
    errors = kill.get("order_path_exceptions") or []
    if errors:
        out.append(
            (
                site,
                (
                    f"the order path raised {errors!r}. An exception out of the "
                    "fallback is a stall wearing a traceback: the caller is an order "
                    "path that has to keep going"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM VACUITY — a healthy publisher is LIVE, and the table is RANKED
# ---------------------------------------------------------------------------


def drive_vacuity(process_mod: Any, statebus: Any, root: Path) -> dict[str, Any]:  # pylint: disable=too-many-locals
    """The un-break half: a HEALTHY publisher must be live and RANKED."""
    endpoint = statebus.endpoint_for("live-ok", root)
    proc, hello = spawn_scoring(endpoint)
    reader = _open_reader(process_mod, statebus, endpoint)
    log = Decisions()
    try:
        warmed = _warm([reader])
        until = time.monotonic() + VACUITY_S
        while time.monotonic() < until:
            reader.pump(PUMP_MS)
            log.record(reader)
        verdict = reader.liveness.verdict()
        fresh_at_end = reader.mirror.fresh()
        writer_live = reader.mirror.writer_live
        fed = reader.mirror.liveness_fed
        lost = reader.mirror.liveness_lost
        alive = proc.poll() is None
    finally:
        reader.close()
        proc.send_signal(signal.SIGTERM)
        status = proc.wait(timeout=REAP_TIMEOUT_S)
    return {
        "arm": "vacuity",
        "pid": int(hello["pid"]),
        "warmed": warmed,
        "publisher_alive_throughout": alive,
        "reap_status": status,
        "expected_reap_status": process_mod.SIGNALLED_EXIT,
        "counts": counts(log.rows),
        "verdict_live": verdict.live,
        "verdict_signal": verdict.signal,
        "verdict_reason": verdict.reason,
        "mirror_writer_live": writer_live,
        "fresh_at_end": fresh_at_end,
        "liveness_fed": fed,
        "liveness_lost": lost,
        "order_path_exceptions": log.errors,
    }


def vacuity_defects(ok: dict) -> list[tuple[str, str]]:
    """A liveness bound that never lets anything be RANKED is the worse defect."""
    site = f"{LIVENESS_MODULE}:non-vacuity"
    out: list[tuple[str, str]] = []
    if not ok.get("publisher_alive_throughout"):
        out.append(
            (
                site,
                (
                    "the healthy publisher did not survive the arm, so this measured a "
                    "death and not a live path"
                ),
            )
        )
    if ok.get("reap_status") != ok.get("expected_reap_status"):
        out.append(
            (
                site,
                (
                    f"the healthy child reaped {ok.get('reap_status')!r}, not "
                    f"{ok.get('expected_reap_status')!r} — it did not exit through "
                    "the clean SIGTERM path, so 'it was alive throughout' is not "
                    "established by the kernel"
                ),
            )
        )
    counts_ = ok.get("counts", {})
    if int(counts_.get("decisions", 0)) < MIN_VACUITY_DECISIONS:
        out.append(
            (
                site,
                (
                    f"the healthy arm took {counts_.get('decisions')} decision(s), "
                    f"below the {MIN_VACUITY_DECISIONS} floor — a non-vacuity control "
                    "proves the live path by running, not by being silent"
                ),
            )
        )
    if int(counts_.get("fcfs", 0)) != 0:
        out.append(
            (
                site,
                (
                    f"{counts_.get('fcfs')} FCFS verdict(s) against a HEALTHY, LIVE "
                    "publisher. The liveness bound fires without an outage, which "
                    "turns §6.6:465's degraded mode into the only mode — a worse "
                    "outcome than the RANKED-from-a-corpse window it replaces"
                ),
            )
        )
    if int(counts_.get("ranked", 0)) < MIN_VACUITY_DECISIONS:
        out.append(
            (
                site,
                (
                    f"only {counts_.get('ranked')} RANKED verdict(s) against a healthy "
                    f"publisher, below the {MIN_VACUITY_DECISIONS} floor"
                ),
            )
        )
    if not ok.get("verdict_live") or not ok.get("mirror_writer_live"):
        out.append(
            (
                site,
                (
                    f"the observer reported live={ok.get('verdict_live')!r} and the "
                    f"mirror writer_live={ok.get('mirror_writer_live')!r} against a "
                    "publisher that was alive for the whole arm"
                ),
            )
        )
    if not ok.get("fresh_at_end"):
        out.append((site, "the mirror was not fresh at the end of the healthy arm"))
    if int(ok.get("liveness_fed", 0)) < 1:
        out.append(
            (
                site,
                (
                    "the mirror was fed ZERO liveness observations, so `writer_live` "
                    "is its constructor's default and nothing was measured. Zero here "
                    "is a finding exactly as `bytes_received == 0` is"
                ),
            )
        )
    if int(ok.get("liveness_lost", 0)) != 0:
        out.append(
            (
                site,
                (
                    f"the mirror recorded {ok.get('liveness_lost')} liveness LOSS "
                    "edge(s) against a publisher that never died"
                ),
            )
        )
    if ok.get("order_path_exceptions"):
        out.append((site, f"the order path raised {ok.get('order_path_exceptions')!r}"))
    return out


# ---------------------------------------------------------------------------
# ARM WEDGE — alive, connected, and not publishing
# ---------------------------------------------------------------------------


def drive_wedge(process_mod: Any, statebus: Any, root: Path) -> dict[str, Any]:  # pylint: disable=too-many-locals
    """A publisher that stays ALIVE and stops publishing. No disconnect, ever.

    The child is spawned with a publish interval far longer than the arm, so it
    binds, publishes its table once, announces, and then sits in its loop
    serving subscriptions without ever advancing `_seq`. That is the wedge: a
    process the peer signal cannot see, because there is nothing wrong with its
    socket.
    """
    endpoint = statebus.endpoint_for("live-wedge", root)
    proc, hello = spawn_scoring(endpoint, interval_s=60.0)
    watched = _open_reader(
        process_mod,
        statebus,
        endpoint,
        heartbeat_deadline_s=HEARTBEAT_DEADLINE_S,
    )
    control = _open_reader(process_mod, statebus, endpoint)
    log = Decisions()
    control_log = Decisions()
    try:
        warmed = _warm([watched, control])
        until = time.monotonic() + WEDGE_S
        while time.monotonic() < until:
            watched.pump(PUMP_MS)
            control.pump(PUMP_MS)
            log.record(watched)
            control_log.record(control)
        verdict = watched.liveness.verdict()
        control_verdict = control.liveness.verdict()
        seq_age = watched.liveness.seq_age_s()
        peer = watched.liveness.peer_observed
        table_age = watched.mirror.age_s()
        rows = _rows_held(watched)
        alive = proc.poll() is None
    finally:
        watched.close()
        control.close()
        proc.send_signal(signal.SIGTERM)
        status = proc.wait(timeout=REAP_TIMEOUT_S)
    first = log.first_fcfs(0.0)
    return {
        "arm": "wedge",
        "pid": int(hello["pid"]),
        "warmed": warmed,
        "publisher_alive_throughout": alive,
        "reap_status": status,
        "expected_reap_status": process_mod.SIGNALLED_EXIT,
        "heartbeat_deadline_s": HEARTBEAT_DEADLINE_S,
        "stale_after_s": STALE_AFTER_S,
        "table_age_at_end_s": table_age,
        "seq_age_s": seq_age,
        "peer_observed": peer,
        "rows_held": rows,
        "counts": counts(log.rows),
        "control_counts": counts(control_log.rows),
        "verdict_live": verdict.live,
        "verdict_signal": verdict.signal,
        "verdict_reason": verdict.reason,
        "control_verdict_live": control_verdict.live,
        "control_verdict_signal": control_verdict.signal,
        "first_fcfs_reason": "" if first is None else first[2],
        "order_path_exceptions": log.errors,
    }


def wedge_defects(wedge: dict) -> list[tuple[str, str]]:
    """The SECOND signal, on the failure mode the FIRST one is blind to."""
    site = f"{LIVENESS_MODULE}:PublisherLiveness[heartbeat]"
    out: list[tuple[str, str]] = []
    if not wedge.get("publisher_alive_throughout"):
        out.append(
            (
                site,
                (
                    "the wedged publisher DIED during the arm, so the peer signal could "
                    "have produced this verdict and the heartbeat proved nothing"
                ),
            )
        )
    if wedge.get("reap_status") != wedge.get("expected_reap_status"):
        out.append(
            (
                site,
                (
                    f"the wedged child reaped {wedge.get('reap_status')!r}, not "
                    f"{wedge.get('expected_reap_status')!r}: the kernel does not "
                    "confirm it was alive and stoppable at the end of the arm"
                ),
            )
        )
    if wedge.get("peer_observed") is not True:
        out.append(
            (
                site,
                (
                    f"the PEER signal reported {wedge.get('peer_observed')!r} on a "
                    "publisher that never disconnected. If the peer signal fired, "
                    "this arm measured signal 1 again and not signal 2"
                ),
            )
        )
    if wedge.get("verdict_live") is not False:
        out.append(
            (
                site,
                (
                    f"the observer reported live={wedge.get('verdict_live')!r} on a "
                    f"publisher whose §12.7 sequence had not advanced for "
                    f"{wedge.get('seq_age_s')!r}s against a "
                    f"{wedge.get('heartbeat_deadline_s')}s deadline. A publisher that "
                    "is alive but WEDGED never disconnects, which is exactly why a "
                    "second signal exists"
                ),
            )
        )
    if wedge.get("verdict_signal") != "heartbeat":
        out.append(
            (
                site,
                (
                    f"the verdict named the {wedge.get('verdict_signal')!r} signal, "
                    "not 'heartbeat'. Check contract §18: the reason must say WHICH "
                    "control fired, and a dead process is a different incident from "
                    "a wedged one"
                ),
            )
        )
    counts_ = wedge.get("counts", {})
    if int(counts_.get("decisions", 0)) < MIN_WEDGE_DECISIONS:
        out.append(
            (
                site,
                (
                    f"the wedge arm took {counts_.get('decisions')} decision(s), below "
                    f"the {MIN_WEDGE_DECISIONS} floor"
                ),
            )
        )
    if int(counts_.get("fcfs", 0)) < 1:
        out.append((site, "the watched reader never fell back on a wedged publisher"))
    if "wedged" not in str(wedge.get("first_fcfs_reason") or "").lower():
        out.append(
            (
                site,
                (
                    f"the first FCFS named {wedge.get('first_fcfs_reason')!r}, which "
                    "does not identify the wedge. An operator reading it cannot tell "
                    "a stopped writer from a dead one"
                ),
            )
        )
    if int(wedge.get("rows_held", 0)) < 2:
        out.append(
            (
                site,
                (
                    "the wedged reader's mirror held fewer than both contenders' rows, so "
                    "this measured the absent-table trigger"
                ),
            )
        )
    out += _wedge_control_defects(site, wedge)
    if wedge.get("order_path_exceptions"):
        out.append(
            (site, f"the order path raised {wedge.get('order_path_exceptions')!r}")
        )
    return out


def _wedge_control_defects(site: str, wedge: dict) -> list[tuple[str, str]]:
    """The discriminator: same wedged publisher, heartbeat DISABLED, still RANKING.

    Without it, any reader that fell back for any reason would satisfy the arm —
    including one whose table simply aged past `stale_after_s` while the arm ran.
    """
    out: list[tuple[str, str]] = []
    control = wedge.get("control_counts", {})
    if int(control.get("ranked", 0)) < MIN_WEDGE_DECISIONS:
        out.append(
            (
                site,
                (
                    f"the control reader (heartbeat disabled) on the SAME wedged "
                    f"publisher ranked only {control.get('ranked')} time(s), below "
                    f"the {MIN_WEDGE_DECISIONS} floor. The two readers differ only in "
                    "the deadline, so if the control also fell back then something "
                    "other than the heartbeat ended the watched reader's ranking"
                ),
            )
        )
    if int(control.get("fcfs", 0)) != 0:
        out.append(
            (
                site,
                (
                    f"the control reader took {control.get('fcfs')} FCFS verdict(s) on "
                    "the same wedged publisher, so the watched reader's fallback is "
                    "not attributable to the heartbeat deadline"
                ),
            )
        )
    if wedge.get("control_verdict_live") is not True:
        out.append(
            (
                site,
                (
                    f"the control observer reported live="
                    f"{wedge.get('control_verdict_live')!r} with its deadline "
                    "disabled, which means the peer signal fired and this arm is not "
                    "about the heartbeat at all"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM RAISE — the observer is the new failure mode
# ---------------------------------------------------------------------------


class ExplodingObserver:
    """An observer whose `observe()` always raises. §6.6:467's worst case.

    Not a mock of the subject: it is a DEFECT PLANTED IN THE SEAM the shipped
    `RankingReader.pump` reaches through, so what is measured is the shipped
    reader's handling and not a re-implementation of it.
    """

    def __init__(self, real: Any) -> None:
        self._real = real
        self.calls = 0

    def note_message(self, seq: int = -1) -> None:
        """Delegate: the message path must stay intact so the mirror still fills."""
        self._real.note_message(seq)

    def observe(self) -> int:
        """Always raises. The whole point."""
        self.calls += 1
        raise RuntimeError("planted liveness observer failure")

    def note_observe_error(self, exc: BaseException) -> None:
        """Delegate, so the SHIPPED latch is what produces the verdict."""
        self._real.note_observe_error(exc)

    def verdict(self, now: float | None = None) -> Any:
        """Delegate to the shipped verdict logic."""
        return self._real.verdict(now)

    def close(self) -> None:
        """Delegate teardown, so the monitor socket is still released."""
        self._real.close()


def drive_raise(process_mod: Any, statebus: Any, root: Path) -> dict[str, Any]:  # pylint: disable=too-many-locals
    """A raising observer must NOT halt order flow. §6.6:467 outranks this gate."""
    liveness_mod, error = _load("nixscore.liveness")
    if liveness_mod is None:  # pragma: no cover - §17 path, handled by the caller
        raise RuntimeError(error)
    endpoint = statebus.endpoint_for("live-raise", root)
    proc, hello = spawn_scoring(endpoint)
    subscriber = statebus.StateSubscriber(endpoint, [process_mod.RANKING_TOPIC])
    observer = ExplodingObserver(liveness_mod.PublisherLiveness(subscriber))
    reader = process_mod.RankingReader(
        subscriber, stale_after_s=STALE_AFTER_S, liveness=observer
    )
    log = Decisions()
    try:
        until = time.monotonic() + RAISE_S
        while time.monotonic() < until:
            reader.pump(PUMP_MS)
            log.record(reader)
        errors = list(reader.liveness_errors)
        verdict = observer.verdict()
        writer_live = reader.mirror.writer_live
        calls = observer.calls
        alive = proc.poll() is None
    finally:
        reader.close()
        proc.send_signal(signal.SIGTERM)
        status = proc.wait(timeout=REAP_TIMEOUT_S)
    first = log.first_fcfs(0.0)
    return {
        "arm": "raise",
        "pid": int(hello["pid"]),
        "publisher_alive_throughout": alive,
        "reap_status": status,
        "expected_reap_status": process_mod.SIGNALLED_EXIT,
        "observe_calls": calls,
        "counts": counts(log.rows),
        "order_path_exceptions": log.errors,
        "pump_caught": errors[:3],
        "pump_caught_n": len(errors),
        "verdict_live": verdict.live,
        "verdict_signal": verdict.signal,
        "verdict_reason": verdict.reason,
        "mirror_writer_live": writer_live,
        "first_fcfs_reason": "" if first is None else first[2],
    }


def raise_defects(arm: dict) -> list[tuple[str, str]]:
    """A liveness observer that raises must still leave order flow running."""
    site = f"{LIVENESS_MODULE}:observer-raised"
    out: list[tuple[str, str]] = []
    if int(arm.get("observe_calls", 0)) < 1:
        out.append(
            (
                site,
                (
                    "the planted observer was never called, so nothing raised and this "
                    "arm measured the healthy path under a different name"
                ),
            )
        )
    if arm.get("order_path_exceptions"):
        out.append(
            (
                site,
                (
                    f"the ORDER PATH raised {arm.get('order_path_exceptions')!r} "
                    "because the liveness observer did. §6.6:467: a scoring outage "
                    "must NEVER halt order flow, and an observer built to make the "
                    "outage visible sooner must not become a new way for it to halt"
                ),
            )
        )
    counts_ = arm.get("counts", {})
    if int(counts_.get("decisions", 0)) < MIN_RAISE_DECISIONS:
        out.append(
            (
                site,
                (
                    f"only {counts_.get('decisions')} decision(s) taken while the "
                    f"observer was raising, below the {MIN_RAISE_DECISIONS} floor"
                ),
            )
        )
    if int(counts_.get("fcfs", 0)) != int(counts_.get("decisions", 0)):
        out.append(
            (
                site,
                (
                    f"{counts_.get('ranked')} of {counts_.get('decisions')} decisions "
                    "were RANKED while the liveness observer was blind. Directive 4 "
                    "is fail CLOSED: an observer that cannot see the writer has not "
                    "seen a live writer"
                ),
            )
        )
    if int(arm.get("pump_caught_n", 0)) < 1:
        out.append(
            (
                site,
                (
                    "the shipped reader caught ZERO observer exceptions, so nothing "
                    "proves the catch is where the survival came from"
                ),
            )
        )
    if (
        arm.get("verdict_live") is not False
        or arm.get("mirror_writer_live") is not False
    ):
        out.append(
            (
                site,
                (
                    f"verdict live={arm.get('verdict_live')!r} / mirror writer_live="
                    f"{arm.get('mirror_writer_live')!r} while the observer was "
                    "raising on every call"
                ),
            )
        )
    if arm.get("verdict_signal") != "observer":
        out.append(
            (
                site,
                (
                    f"the verdict named the {arm.get('verdict_signal')!r} signal, not "
                    "'observer'. §18: an operator must be able to tell a broken "
                    "instrument from a dead publisher"
                ),
            )
        )
    if "RuntimeError" not in str(arm.get("verdict_reason") or ""):
        out.append(
            (
                site,
                (
                    f"the reason {arm.get('verdict_reason')!r} does not name the "
                    "exception that caused it — §18 requires the REASON, and 'not "
                    "live' with no cause is not one"
                ),
            )
        )
    if not arm.get("publisher_alive_throughout"):
        out.append(
            (
                site,
                (
                    "the publisher died during the raise arm, so the FCFS could have come "
                    "from the death rather than from the broken observer"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM SHAPE — the hazard stated backwards, read out of the source
# ---------------------------------------------------------------------------


def read_path_defects(source: str) -> tuple[list[tuple[str, str]], int]:
    """The observer's read verbs are TOTAL: no raise, no loop, no try, no I/O.

    Scanned INSIDE `class PublisherLiveness` and nowhere else. `liveness.py`
    also declares a `LivenessObserver` Protocol carrying the same five verb
    names with empty bodies, and a walk over the whole module would count those
    stubs as scanned read paths — four expected verbs would become eight, and
    half the scan would be over declarations that execute nothing. A
    non-vacuity floor satisfied by stubs is the shape this arm exists to refuse.
    """
    findings: list[tuple[str, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(LIVENESS_MODULE, f"cannot parse: {exc}")], 0
    body: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == OBSERVER_CLASS:
            body = node.body
    scanned = 0
    for node in body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in LIVENESS_READ_PATH:
            continue
        scanned += 1
        site = f"{LIVENESS_MODULE}:{OBSERVER_CLASS}.{node.name}"
        findings += _read_verb_defects(site, node)
    return findings, scanned


def _read_verb_defects(site: str, node: ast.AST) -> list[tuple[str, str]]:
    """Anything in one read verb that makes it able to raise, block or do I/O."""
    out: list[tuple[str, str]] = []
    for inner in ast.walk(node):
        if isinstance(inner, STALLING_NODES):
            out.append(
                (
                    site,
                    (
                        f"contains {type(inner).__name__} — a liveness read is taken "
                        "on the way to an order decision that must answer at the "
                        "instant a process died (§6.6:467, §11:595)"
                    ),
                )
            )
        if isinstance(inner, ast.Raise):
            out.append(
                (
                    site,
                    (
                        "can raise. §6.6:467 forbids a scoring outage halting order "
                        "flow, and an exception out of the liveness read is a stall "
                        "wearing a traceback"
                    ),
                )
            )
        if isinstance(inner, ast.Call):
            name = _called_name(inner)
            if name in BANNED_IO_CALLS:
                out.append(
                    (
                        site,
                        (
                            f"calls {name}() — that is I/O on a read that feeds an "
                            "order decision. The socket is touched in `observe`, from "
                            "the consumer's pump loop, and nowhere else"
                        ),
                    )
                )
    return out


def order_path_defects(source: str) -> tuple[list[tuple[str, str]], int]:
    """`seam.py`'s `arbitrate` reads a BOOLEAN; it never calls the observer."""
    findings: list[tuple[str, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(SEAM_MODULE, f"cannot parse: {exc}")], 0
    scanned = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in ("arbitrate", "fresh"):
            continue
        scanned += 1
        site = f"{SEAM_MODULE}:{node.name}"
        for inner in ast.walk(node):
            findings += _order_node_defects(site, inner)
    return findings, scanned


def _order_node_defects(site: str, inner: ast.AST) -> list[tuple[str, str]]:
    """One node's verdict on the seam's order path, or nothing."""
    if isinstance(inner, (ast.Try, ast.While, ast.For)):
        return [
            (
                site,
                (
                    f"contains {type(inner).__name__}: the order path must "
                    "stay a straight read. The liveness `try` belongs in "
                    "`RankingReader.pump`, off this path"
                ),
            )
        ]
    if isinstance(inner, ast.Call) and _called_name(inner) in (
        BANNED_OBSERVER_CALLS + BANNED_IO_CALLS
    ):
        return [
            (
                site,
                (
                    f"calls {_called_name(inner)}() on the order path. The "
                    "mirror is FED liveness from the pump loop and reads a "
                    "plain attribute; calling out to an observer here would "
                    "put its latency, and its exceptions, on an order "
                    "decision (§11:595)"
                ),
            )
        ]
    return []


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


# ---------------------------------------------------------------------------
# CAN-FAIL: every defect function driven over a DOCTORED subject
# ---------------------------------------------------------------------------

_GOOD_KILL = {
    "pid": 1,
    "warmed": True,
    "reap_status": -9,
    "expected_reap_status": -9,
    "pid_alive_before_kill": True,
    "pid_gone_after_reap": True,
    "stale_after_s": 0.5,
    "table_age_at_kill_s": 0.01,
    "pre": {"decisions": 9999, "ranked": 9999, "fcfs": 0},
    "post": {"decisions": 9999, "ranked": 0, "fcfs": 9999},
    "blind_post": {"decisions": 9999, "ranked": 144699, "fcfs": 5000},
    "window_s": 0.0035,
    "blind_window_s": 0.483,
    "first_fcfs_reason": (
        "ranking WRITER not live [peer]: the Scoring publisher's peer is GONE — "
        "libzmq DISCONNECTED on the subscriber socket after 1 disconnect(s)"
    ),
    "blind_first_fcfs_reason": "ranking table stale: age 0.500s exceeds the ...",
    "rows_held_at_first_fcfs": 2,
    "max_decision_gap_s": 0.0035,
    "gap_across_kill_s": 0.0035,
    "order_path_exceptions": [],
    "liveness_lost": 1,
    "liveness_fed": 9999,
    "signals": {
        "disconnects": 1,
        "events_seen": 6,
        "peer_observed": False,
        "last_event": "DISCONNECTED",
    },
}
_GOOD_VACUITY = {
    "publisher_alive_throughout": True,
    "reap_status": 7,
    "expected_reap_status": 7,
    "counts": {"decisions": 9999, "ranked": 9999, "fcfs": 0},
    "verdict_live": True,
    "verdict_signal": "peer",
    "verdict_reason": "peer attached",
    "mirror_writer_live": True,
    "fresh_at_end": True,
    "liveness_fed": 9999,
    "liveness_lost": 0,
    "order_path_exceptions": [],
}
_GOOD_WEDGE = {
    "publisher_alive_throughout": True,
    "reap_status": 7,
    "expected_reap_status": 7,
    "heartbeat_deadline_s": 0.15,
    "stale_after_s": 0.5,
    "seq_age_s": 0.31,
    "peer_observed": True,
    "rows_held": 2,
    "counts": {"decisions": 5000, "ranked": 1000, "fcfs": 4000},
    "control_counts": {"decisions": 5000, "ranked": 5000, "fcfs": 0},
    "verdict_live": False,
    "verdict_signal": "heartbeat",
    "control_verdict_live": True,
    "control_verdict_signal": "peer",
    "first_fcfs_reason": (
        "ranking WRITER not live [heartbeat]: the Scoring publisher is CONNECTED "
        "but WEDGED: §12.7 sequence 4 has not advanced for 0.310s"
    ),
    "order_path_exceptions": [],
}
_GOOD_RAISE = {
    "publisher_alive_throughout": True,
    "observe_calls": 5000,
    "counts": {"decisions": 5000, "ranked": 0, "fcfs": 5000},
    "order_path_exceptions": [],
    "pump_caught_n": 5000,
    "verdict_live": False,
    "verdict_signal": "observer",
    "verdict_reason": (
        "the liveness observer raised RuntimeError: planted liveness observer "
        "failure and can no longer see the writer"
    ),
    "mirror_writer_live": False,
    "first_fcfs_reason": "ranking WRITER not live [observer]: ...",
}

_CLEAN_READ = (
    "class PublisherLiveness:\n"
    "    def verdict(self, now=None):\n"
    "        return LivenessVerdict(self._peer is not False, 'peer', self._reason)\n"
)
_RAISING_READ = (
    "class PublisherLiveness:\n"
    "    def verdict(self, now=None):\n"
    "        raise LivenessError('no observation')\n"
)
_IO_READ = (
    "class PublisherLiveness:\n"
    "    def verdict(self, now=None):\n"
    "        self._monitor.poll(0)\n"
    "        return LivenessVerdict(True, 'peer', '')\n"
)
_CLEAN_ORDER = (
    "class RankingMirror:\n"
    "    def arbitrate(self, first, second, now=None):\n"
    "        if not self._writer_live:\n"
    "            return Verdict(Arbitration.FCFS, first, self._writer_live_reason)\n"
    "        return Verdict(Arbitration.RANKED, first, 'higher EMA')\n"
    "    def fresh(self, now=None):\n"
    "        return self._writer_live and self.age_s(now) is not None\n"
)
_ASKING_ORDER = (
    "class RankingMirror:\n"
    "    def arbitrate(self, first, second, now=None):\n"
    "        if not self._liveness.verdict(now).live:\n"
    "            return Verdict(Arbitration.FCFS, first, 'dead')\n"
    "        return Verdict(Arbitration.RANKED, first, 'higher EMA')\n"
    "    def fresh(self, now=None):\n"
    "        return True\n"
)


def _with(base: dict, **overrides: Any) -> dict:
    """A copy of `base` with fields replaced. The plant, never the shipped dict."""
    return {**base, **overrides}


def _plants() -> tuple[tuple[str, list[tuple[str, str]]], ...]:
    """Every defect function, fed a doctored subject that MUST produce a finding."""
    return (
        ("kill/exited-not-killed", kill_defects(_with(_GOOD_KILL, reap_status=0))),
        (
            "kill/already-falling-back",
            kill_defects(
                _with(_GOOD_KILL, pre={"decisions": 9999, "ranked": 0, "fcfs": 9999})
            ),
        ),
        ("kill/never-warmed", kill_defects(_with(_GOOD_KILL, warmed=False))),
        (
            "corpse/ranked-from-a-corpse",
            corpse_defects(
                _with(
                    _GOOD_KILL,
                    post={"decisions": 9999, "ranked": 144699, "fcfs": 9999},
                )
            ),
        ),
        (
            "corpse/window-drifted-to-the-clock",
            corpse_defects(_with(_GOOD_KILL, window_s=0.483)),
        ),
        ("corpse/never-fell-back", corpse_defects(_with(_GOOD_KILL, window_s=None))),
        (
            "corpse/ended-by-the-clock",
            corpse_defects(
                _with(_GOOD_KILL, first_fcfs_reason="ranking table stale: age 0.5s")
            ),
        ),
        (
            "corpse/reason-names-no-signal",
            corpse_defects(
                _with(_GOOD_KILL, first_fcfs_reason="ranking WRITER not live: gone")
            ),
        ),
        (
            "corpse/absent-not-populated",
            corpse_defects(_with(_GOOD_KILL, rows_held_at_first_fcfs=0)),
        ),
        (
            "corpse/no-disconnect-observed",
            corpse_defects(
                _with(_GOOD_KILL, signals={"disconnects": 0, "peer_observed": False})
            ),
        ),
        (
            "blind/no-defect-to-repair",
            blind_control_defects(
                _with(
                    _GOOD_KILL,
                    blind_post={"decisions": 10, "ranked": 3, "fcfs": 7},
                )
            ),
        ),
        (
            "blind/control-not-the-age-route",
            blind_control_defects(
                _with(_GOOD_KILL, blind_first_fcfs_reason="WRITER not live [peer]")
            ),
        ),
        ("flow/halted", flow_defects(_with(_GOOD_KILL, gap_across_kill_s=10.0))),
        (
            "flow/raised",
            flow_defects(_with(_GOOD_KILL, order_path_exceptions=["boom"])),
        ),
        (
            "flow/third-outcome",
            flow_defects(
                _with(
                    _GOOD_KILL,
                    post={"decisions": 9999, "ranked": 0, "fcfs": 8000},
                )
            ),
        ),
        (
            "vacuity/fcfs-while-healthy",
            vacuity_defects(
                _with(
                    _GOOD_VACUITY,
                    counts={"decisions": 9999, "ranked": 0, "fcfs": 9999},
                )
            ),
        ),
        (
            "vacuity/never-fed",
            vacuity_defects(_with(_GOOD_VACUITY, liveness_fed=0)),
        ),
        (
            "vacuity/dead-while-healthy",
            vacuity_defects(_with(_GOOD_VACUITY, verdict_live=False)),
        ),
        (
            "wedge/second-signal-silent",
            wedge_defects(_with(_GOOD_WEDGE, verdict_live=True)),
        ),
        (
            "wedge/wrong-signal-fired",
            wedge_defects(_with(_GOOD_WEDGE, verdict_signal="peer")),
        ),
        (
            "wedge/publisher-actually-died",
            wedge_defects(_with(_GOOD_WEDGE, peer_observed=False)),
        ),
        (
            "wedge/control-also-fell-back",
            wedge_defects(
                _with(
                    _GOOD_WEDGE,
                    control_counts={"decisions": 5000, "ranked": 0, "fcfs": 5000},
                )
            ),
        ),
        (
            "raise/order-path-took-it",
            raise_defects(_with(_GOOD_RAISE, order_path_exceptions=["RuntimeError"])),
        ),
        (
            "raise/ranked-while-blind",
            raise_defects(
                _with(
                    _GOOD_RAISE, counts={"decisions": 5000, "ranked": 5000, "fcfs": 0}
                )
            ),
        ),
        (
            "raise/reason-omits-the-cause",
            raise_defects(_with(_GOOD_RAISE, verdict_reason="not live")),
        ),
        ("raise/never-raised", raise_defects(_with(_GOOD_RAISE, observe_calls=0))),
        ("shape/read-can-raise", read_path_defects(_RAISING_READ)[0]),
        ("shape/read-does-io", read_path_defects(_IO_READ)[0]),
        ("shape/order-path-asks-the-observer", order_path_defects(_ASKING_ORDER)[0]),
    )


def _arms_can_fail() -> tuple[str, str]:
    """The first arm that cannot demonstrate its defect, or ("", "")."""
    for label, findings in _plants():
        if not findings:
            return label, (
                f"the {label} plant produced NO finding — that arm cannot see the "
                "defect it exists to see, so its silence is blind, not green"
            )
    clean_read, read_scanned = read_path_defects(_CLEAN_READ)
    if read_scanned != 1 or clean_read:
        return "shape/read-false-positive", (
            f"a total read verb was reported as a defect ({clean_read!r}) over "
            f"{read_scanned} scanned verb(s) — the arm flags everything, which is "
            "the same blindness pointed the other way"
        )
    clean_order, order_scanned = order_path_defects(_CLEAN_ORDER)
    if order_scanned != 2 or clean_order:
        return "shape/order-false-positive", (
            f"a clean order path was reported as a defect ({clean_order!r}) over "
            f"{order_scanned} scanned function(s), expected 2"
        )
    for label, findings in (
        ("kill", kill_defects(_GOOD_KILL)),
        ("corpse", corpse_defects(_GOOD_KILL)),
        ("blind", blind_control_defects(_GOOD_KILL)),
        ("flow", flow_defects(_GOOD_KILL)),
        ("vacuity", vacuity_defects(_GOOD_VACUITY)),
        ("wedge", wedge_defects(_GOOD_WEDGE)),
        ("raise", raise_defects(_GOOD_RAISE)),
    ):
        if findings:
            return f"{label}/false-positive", (
                f"a healthy {label} outcome produced {findings!r} — the arm cannot "
                "return clean, so its findings carry no information"
            )
    return "", ""


# ---------------------------------------------------------------------------


def _num(value: Any, scale: float = 1.0, unit: str = "s") -> str:
    """A measured number, or `n/a` — **never a crash**.

    Every optional field here is `None` in exactly the case the gate exists to
    report, so a renderer that cannot print `None` is a renderer that masks the
    defect (§17: masking is the failure, and the verdict after it is not the one
    that was measured).
    """
    if value is None:
        return "n/a"
    return f"{float(value) * scale:.3f}{unit}"


def _evidence(outcome: dict, read_scanned: int, order_scanned: int) -> str:
    """What WAS measured, attached to the PASS and to the FAIL alike."""
    kill = outcome["kill"]
    wedge = outcome["wedge"]
    ok = outcome["vacuity"]
    raised = outcome["raise"]
    return (
        f"pid {kill['pid']} SIGKILLed mid-contention and reaped "
        f"{kill['reap_status']} (/proc gone={kill['pid_gone_after_reap']}); TWO "
        f"readers on the SAME socket watched the SAME death: the OBSERVING reader "
        f"took {kill['post']['ranked']} RANKED decision(s) from the corpse over a "
        f"{_num(kill['window_s'], 1000, 'ms')} window, the BLIND reader "
        f"(observe_liveness=False) took {kill['blind_post']['ranked']} over "
        f"{_num(kill['blind_window_s'])} on the same box and the same instant "
        f"(ARC 036 / CHECK-DEBT D3.244 measured 144,699 over 0.483s at the same "
        f"{kill['stale_after_s']}s threshold); {kill['signals']['disconnects']} "
        f"libzmq DISCONNECT event(s) observed, last event "
        f"{kill['signals']['last_event']!r}, mirror fed "
        f"{kill['liveness_fed']} liveness observation(s) with "
        f"{kill['liveness_lost']} loss edge(s); order flow answered "
        f"{kill['post']['decisions']} time(s) after the kill with "
        f"{len(kill['order_path_exceptions'])} order-path exception(s), worst "
        f"inter-decision gap {_num(kill['max_decision_gap_s'], 1000, 'ms')} "
        f"(across-kill {_num(kill['gap_across_kill_s'], 1000, 'ms')}); NON-VACUITY: "
        f"a healthy publisher (reaped {ok['reap_status']}) gave "
        f"{ok['counts']['ranked']} RANKED and {ok['counts']['fcfs']} FCFS with "
        f"live={ok['verdict_live']}; WEDGE: a publisher alive throughout (reaped "
        f"{wedge['reap_status']}, peer_observed={wedge['peer_observed']}) with its "
        f"§12.7 sequence frozen {_num(wedge['seq_age_s'])} against a "
        f"{wedge['heartbeat_deadline_s']}s deadline gave "
        f"{wedge['counts']['fcfs']} FCFS on the {wedge['verdict_signal']!r} signal "
        f"while its control reader (deadline disabled, same publisher) stayed "
        f"RANKED {wedge['control_counts']['ranked']} time(s); RAISE: an observer "
        f"raising on all {raised['observe_calls']} call(s) left "
        f"{raised['counts']['decisions']} decision(s) answered, "
        f"{raised['counts']['fcfs']} of them FCFS, "
        f"{len(raised['order_path_exceptions'])} order-path exception(s), "
        f"{raised['pump_caught_n']} caught in the shipped pump; {read_scanned} "
        f"liveness read verb(s) and {order_scanned} seam order-path function(s) "
        f"scanned; all {len(_plants())} defect arms proved they can fail on "
        f"planted subjects this run"
    )


def _measure(root: Path) -> tuple[list[tuple[str, str]], dict, int, int]:
    """Run every arm once and judge it. Returns (defects, outcome, scans)."""
    process_mod, error = _load("nixscore.process")
    if process_mod is None:
        raise RuntimeError(error)
    statebus, error = _load("nixbus.statebus")
    if statebus is None:
        raise RuntimeError(error)
    outcome = {
        "kill": drive_kill(process_mod, statebus, root),
        "vacuity": drive_vacuity(process_mod, statebus, root),
        "wedge": drive_wedge(process_mod, statebus, root),
        "raise": drive_raise(process_mod, statebus, root),
    }
    home = Path(__file__).resolve().parent.parent
    read_findings, read_scanned = read_path_defects(
        (home / LIVENESS_MODULE).read_text(encoding="utf-8")
    )
    order_findings, order_scanned = order_path_defects(
        (home / SEAM_MODULE).read_text(encoding="utf-8")
    )
    defects = (
        kill_defects(outcome["kill"])
        + corpse_defects(outcome["kill"])
        + blind_control_defects(outcome["kill"])
        + flow_defects(outcome["kill"])
        + vacuity_defects(outcome["vacuity"])
        + wedge_defects(outcome["wedge"])
        + raise_defects(outcome["raise"])
        + read_findings
        + order_findings
    )
    if read_scanned != len(LIVENESS_READ_PATH):
        defects.append(
            (
                f"{NAME}:non-vacuity",
                (
                    f"the liveness read-path scan found {read_scanned} of "
                    f"{len(LIVENESS_READ_PATH)} expected verb(s) in "
                    f"{LIVENESS_MODULE} — a scan over nothing cannot report a read "
                    "that raises"
                ),
            )
        )
    if order_scanned < 2:
        defects.append(
            (
                f"{NAME}:non-vacuity",
                (
                    f"the seam order-path scan found {order_scanned} function(s) in "
                    f"{SEAM_MODULE}, expected `arbitrate` and `fresh`"
                ),
            )
        )
    return defects, outcome, read_scanned, order_scanned


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure it. See the module docstring for what, and for §7.12."""
    try:
        blind, why = _arms_can_fail()
        if blind:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{blind}",
                detail=f"the {blind} arm cannot fail: {why}",
            )
        module, error = _load("nixscore.liveness")
        if module is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        with tempfile.TemporaryDirectory(prefix="nixliveness") as tmp:
            defects, outcome, read_scanned, order_scanned = _measure(Path(tmp))
        return result_from_defects(
            NAME, defects, _evidence(outcome, read_scanned, order_scanned)
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
