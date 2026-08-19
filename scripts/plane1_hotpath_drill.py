#!/usr/bin/env python3
"""§11 item 6 measured under LOAD: the gate never blocks on a group-commit.

ARC 035 / Stage 1 / sub-agent A (A3). Authority:
`docs/nics_risk_subsystem_spec_v1.3.md` §11 (the entry pathway is *cache reads
and arithmetic only*) and §11 item 6 (*group-commit event-log writes off the hot
path, WAL-buffered*).

## THE BRIEF'S §0a, WHICH THIS DRILL EXISTS TO OBEY

> *an idle-system latency test proves NOTHING about hot-path isolation.*

That is the measurement anyone writes first: time the gate, see a small number,
declare victory. It measures a fast box. A gate that DID block on Postgres
would still look fast on an idle system because there was nothing to block ON.

So the drill runs **three arms over the same gate, the same order, the same
picture, and the same rule manifest**, and the claim is the RELATION between
them, never any one figure:

* **BASELINE** — the gate loop alone. No WAL writer, no sink, nothing
  concurrent. This is the number an idle-system test would report, and it is
  here as the thing the other two are compared against.
* **CONCURRENT** — the same loop while a persistence thread is *actually
  committing*, through a sink with a REAL delay in `commit()`. If §11 item 6 holds,
  this is indistinguishable from BASELINE.
* **SYNCHRONOUS CONTROL** — the same loop with the identical sink wired
  **inline**: `evaluate → enqueue → sync_to_disk → drain_once`, all inside the
  timed region. This is what a Limiter that wrote Plane 1 on the hot path would
  do, and its latency MUST be inflated by roughly the sink's delay.

**Without the control the concurrent figure proves nothing.** It is the control
that demonstrates the instrument can see blocking at all: if a deliberately slow
sink placed directly on the hot path did NOT move the number, then the number is
not measuring the hot path and no conclusion about isolation may be drawn from
it. The drill reports that as an explicit `discriminates` flag rather than
leaving the reader to infer it.

A fourth arm, **POSTGRES**, repeats CONCURRENT against the real
`Plane1PostgresSink` and a scratch database, so the claim is about the shipped
sink and not only about a `time.sleep`. It is skipped, named, when psql or the
cluster is unavailable — §17: a property proven while its subject is
unreachable is not proven.

## THE STATISTIC, AND WHY IT IS p99

n = 2,000 timed gate evaluations per fast arm (300 for the synchronous control,
because every one of its iterations pays a real commit and 2,000 would take
minutes). The reported statistic is the **p99**, with the median and the max
beside it. A mean is the wrong instrument here: a hot path that blocks does so
on the MINORITY of iterations that coincide with a flush, and averaging is
precisely the operation that hides a minority. A single timing is not a
measurement and is not reported.

## THE LOCK, AND WHY IT IS WHERE IT IS

`Plane1Wal` is not thread-safe: `enqueue` and `sync_to_disk` both touch
`_pending`. The persistence thread therefore takes a mutex around
`sync_to_disk` ONLY — and holds nothing at all while `commit()` runs. That
placement IS the architecture under test: the hot path can contend for a
microsecond-scale fsync, and can never contend for the sink. A drill that put
the slow call inside the lock would be measuring a different design, and one
that used no lock at all would be racing on a counter and calling it a result.

## A MEASURED ARTEFACT THAT IS NOT SMOOTHED AWAY: THE MUTEX CONVOY

The concurrent arm's **max** is routinely ~one full `delay_s` while its p99 is
tens of microseconds — one sample in a few thousand, at 5 ms, against a p99 of
~40 us. That is not noise and it is reported rather than trimmed. It is CPython's
switch interval (`sys.getswitchinterval()`, 5 ms by default) meeting the WAL
mutex: the persistence thread takes the lock, releases the GIL inside `fsync`,
and then needs the GIL back in order to RELEASE the lock — while the hot thread,
holding the GIL and running pure Python, may not yield for a full switch
interval. The hot path then waits on `lock.acquire()`.

**This is a property of putting a mutex on the hot path at all, not of §11 item 6's
architecture**, and the honest reading is that it is a real production hazard
worth a later arc: a per-thread WAL handle, or a lock-free hand-off, removes it,
and a lower `switchinterval` only shrinks it. It is also exactly why the
statistic is the p99 and not the max — a single scheduler artefact must not be
able to decide a verdict — and why the max is printed anyway, so nobody has to
discover it later.

## WHAT THIS DRILL CANNOT PROVE, STATED RATHER THAN IMPLIED

`time.sleep` and socket/subprocess I/O both RELEASE the GIL, so the concurrency
is real for the shape under test — a sink blocked on I/O, which is what a
Postgres commit is. This drill does **not** prove isolation against a sink that
burns CPU in Python: the GIL would serialise that, and the honest answer is that
the architecture's isolation is against I/O, which is the failure §11 item 6 names.
It also proves nothing about fsync durability (`checks/check_plane1_wal.py`
owns that, on syscalls) and nothing about the schema (`check_plane1_schema`).
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# pylint: disable=wrong-import-position
from nixrisk.gate import GatePass, default_manifest
from nixrisk.plane1_sink import Plane1PostgresSink, SinkError
from nixrisk.seam import (
    EventKind,
    EventRow,
    FinancialPicture,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.wal import GroupCommitWriter, Plane1Wal

#: §12A knobs, at their spec defaults. Not under test here — the gate's
#: ARITHMETIC belongs to `test_limiter_gate.py`; this drill only needs the real
#: rule chain to run, so it runs the shipped one.
FRACTION: Final[float] = 0.70
SAFETY_PAD: Final[float] = 0.10
TOLERANCE: Final[float] = 1e-6

#: The deliberate delay inside `commit()`. Two milliseconds is ~200x a gate
#: evaluation on this class of box, which is the point: it is impossible to
#: confuse with noise, and the synchronous control is expected to show it almost
#: exactly. It was 5 ms and came DOWN, for a measured reason — see MAX_WAL_ROWS:
#: a longer commit means fewer commits complete inside the hot loop, and the
#: overlap floor is what stops this drill measuring an idle system.
DEFAULT_DELAY_S: Final[float] = 0.002
DEFAULT_ITERATIONS: Final[int] = 2000
#: The control pays a real commit per iteration; 2,000 would take minutes.
DEFAULT_CONTROL_ITERATIONS: Final[int] = 300
#: The concurrent arms keep sampling until this many group-commits have actually
#: COMPLETED alongside the hot loop. Sizing the loop by iterations alone produced
#: a zero-overlap run the first time this was measured — see `concurrent`.
MIN_OVERLAP_COMMITS: Final[int] = 5
#: The hard cap on that stretch, as a multiple of `iterations`. Hitting it leaves
#: the overlap below the floor, which the gate reports as CANNOT_MEASURE.
MAX_OVERLAP_STRETCH: Final[int] = 40
#: The hot loop STOPS ENQUEUEING past this many rows, while continuing to
#: evaluate and time the gate.
#:
#: MEASURED FINDING, ARC 035 / A, and the reason this constant exists:
#: `GroupCommitWriter.drain_once` re-reads and re-PARSES the ENTIRE WAL on every
#: drain (`recover(path, durable_bytes)`), so a drain costs O(rows) and a run
#: costs O(rows**2). At ~24,000 rows a single drain spends >100 ms of pure Python
#: decoding JSON, the persistence thread starves against the GIL, and only two
#: commits complete in a loop that should have seen dozens. Capping the WAL keeps
#: the DRILL measuring §11 item 6 instead of measuring that quadratic. The quadratic
#: itself is a real property of the shipped writer and is REPORTED rather than
#: repaired here — `wal.py` is shared with three sibling sub-agents in this
#: stage, and a cursor rework belongs to whoever owns that seam next.
MAX_WAL_ROWS: Final[int] = 2000
#: The GIL handoff cadence the concurrent arm runs under. CHECK-DEBT D3.346,
#: discharged ARC 038 / sub-agent F.
#:
#: CHOSEN BY MEASUREMENT, and the losing candidates are recorded because the
#: obvious move — "as small as possible" — is the wrong one. Eight runs each on
#: this box, against the gate's TWO ceilings (p99 < 200us, and p99 < 10x the
#: BASELINE arm's ~10us, i.e. ~100us):
#:
#:   * default 0.005 : overlap 6/6 today, but overlap 1-2 on three of six runs
#:                     once the interval is raised — that IS D3.346's mechanism.
#:   * 0.0005        : overlap 6/6, max down to 640-1,660us, but p99 reached
#:                     102.2us — INSIDE the 10x-baseline bound by 3us. Trading
#:                     a CANNOT_MEASURE flake for a FAIL flake is worse.
#:   * 0.002         : overlap 8/8, p99 <= 39.4us, but one max at 11,092us.
#:   * 0.001         : overlap 8/8, p99 16.3-20.4us (the UNMODIFIED arm reads
#:                     15.3-17.5us, so the cost is ~3us), max 1,161-1,421us
#:                     against ~5,200us unpinned. Chosen.
OVERLAP_SWITCH_INTERVAL_S: Final[float] = 0.001


class SlowSink:  # pylint: disable=too-few-public-methods
    """A `CommitSinkPort` with a REAL delay. Not a mock and not a patch.

    The delay is `time.sleep`, which releases the GIL exactly as a socket read
    does, so the concurrency the CONCURRENT arm relies on is the same
    concurrency a Postgres commit gets.
    """

    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.rows: list[EventRow] = []
        self.commits = 0

    def commit(self, rows: Sequence[EventRow]) -> int:
        """Persist a group, slowly."""
        time.sleep(self.delay_s)
        self.rows.extend(rows)
        self.commits += 1
        return len(rows)


class _Clear:
    """Every §11.1-shaped port in one object, all clear. In-memory BY SPEC.

    §11 makes the entry pathway *cache reads and arithmetic only*, so an
    in-memory port is the specified substrate here, not a shortcut for one.
    """

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        """`(blocked, reason)`."""
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`."""
        return False, ""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)`."""
        del strategy_id
        return False, ""

    def mark(self) -> tuple[float, bool]:
        """§6.5's net-liq mark."""
        return 10_000_000.0, True


def _gate() -> GatePass:
    clear = _Clear()
    rules = default_manifest(
        blackout=clear,
        tradability=clear,
        staleness=clear,
        clock_skew=clear,
        in_flight=clear,
        net_liq=clear,
        deployable_fraction=FRACTION,
        survival_safety_pad=SAFETY_PAD,
        coherence_tolerance=TOLERANCE,
    )
    return GatePass(clear, list(rules))


def _order() -> ProposedOrder:
    return ProposedOrder(
        client_order_id="hotpath-1",
        strategy_id="s1",
        symbol="ES",
        side=Side.LONG,
        qty=4,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture() -> FinancialPicture:
    return FinancialPicture(
        version=1,
        published_ts=1.0,
        balance=1_000_000.0,
        positions=(),
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=500_000.0,
    )


def _row(index: int) -> EventRow:
    return EventRow(
        kind=EventKind.SIGNAL,
        ts=1_755_000_000.0 + index * 1e-3,
        strategy_id="s1",
        reason=f"hot-path drill row {index}",
        trade_id=f"t-{index}",
        fields={"symbol": "ES", "seq": str(index)},
    )


def _stats(samples_ns: list[int]) -> dict[str, float]:
    """p50 / p99 / max in MICROSECONDS, plus n. Never a single timing."""
    ordered = sorted(samples_ns)
    index99 = min(len(ordered) - 1, round(0.99 * (len(ordered) - 1)))
    return {
        "n": len(ordered),
        "p50_us": statistics.median(ordered) / 1000.0,
        "p99_us": ordered[index99] / 1000.0,
        "max_us": ordered[-1] / 1000.0,
    }


def baseline(iterations: int) -> dict[str, Any]:
    """ARM 1: the gate loop alone. The figure an idle-system test would report."""
    gate, order, picture = _gate(), _order(), _picture()
    samples: list[int] = []
    for index in range(iterations):
        start = time.perf_counter_ns()
        gate.evaluate(order, picture, 1.0 + index)
        samples.append(time.perf_counter_ns() - start)
    return {"arm": "baseline", **_stats(samples)}


def concurrent(  # pylint: disable=too-many-locals
    root: Path,
    iterations: int,
    delay_s: float,
    min_overlap_commits: int = MIN_OVERLAP_COMMITS,
) -> dict[str, Any]:
    """ARM 2: the gate loop WHILE a persistence thread commits through a slow sink."""
    path = root / f"hotpath-{uuid.uuid4().hex[:8]}.wal"
    wal = Plane1Wal(path)
    sink = SlowSink(delay_s)
    writer = GroupCommitWriter(wal, sink, batch_max=8)
    lock = threading.Lock()
    stop = threading.Event()

    def persist() -> None:
        while not stop.is_set():
            with lock:
                try:
                    wal.sync_to_disk()
                except OSError:  # pragma: no cover - the WAL is on a real fs
                    return
            # The SLOW call is deliberately OUTSIDE the lock. That placement is
            # the architecture under test.
            writer.drain_once()

    # A SEED, synced before the thread starts, so the writer has work from its
    # first tick. Without it the first commit cannot begin until the hot loop has
    # already produced and fsynced rows, which on a busy box is most of the loop.
    for index in range(64):
        wal.enqueue(_row(index))
    wal.sync_to_disk()

    thread = threading.Thread(target=persist, name="plane1-persist", daemon=True)
    gate, order, picture = _gate(), _order(), _picture()
    # CHECK-DEBT D3.346, DISCHARGED ARC 038 / sub-agent F. The overlap floor is
    # not load-sensitive in general — it is sensitive to the GIL HANDOFF CADENCE,
    # which is what this module's own docstring already names as the convoy's
    # cause. MEASURED: at `setswitchinterval(0.05)` three of six runs fell to an
    # overlap of 1-2, below the gate's floor of 3, and were reported
    # CANNOT_MEASURE. Pinning it here removes the box's cadence from the
    # measurement: at `OVERLAP_SWITCH_INTERVAL_S` the overlap reached 6 on 8 of
    # 8 runs and this arm's MAX fell from ~5,200us to 1,161-1,421us. The
    # direction is the honest one — the hot loop yields MORE often, so its p99
    # rises by ~3us — the bias is AGAINST a pass, never toward one. See the
    # constant for the candidates that were measured and rejected. Restored in
    # the `finally`, and REPORTED in the result so no reader has to discover
    # that the arm changed a process-global.
    previous_switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(OVERLAP_SWITCH_INTERVAL_S)
    samples: list[int] = []
    thread.start()
    try:
        # The loop runs until BOTH the sample floor and the OVERLAP floor are
        # met. Sizing it by iterations alone is what produced a zero-overlap run
        # the first time this was measured: 600 gate evaluations finish in ~9 ms
        # and one commit costs 5 ms, so the hot loop can end before a single
        # commit completes — and "the gate did not block" is then trivially true.
        # A hard cap keeps a stalled sink from spinning forever; hitting it
        # leaves the overlap low, which the gate reports as CANNOT_MEASURE rather
        # than as a pass.
        index = 0
        cap = iterations * MAX_OVERLAP_STRETCH
        while index < cap and (
            len(samples) < iterations or sink.commits < min_overlap_commits
        ):
            start = time.perf_counter_ns()
            gate.evaluate(order, picture, 1.0 + index)
            if wal.enqueued < MAX_WAL_ROWS:
                with lock:
                    wal.enqueue(_row(index))
            samples.append(time.perf_counter_ns() - start)
            index += 1
    finally:
        stop.set()
        thread.join(timeout=5.0)
        sys.setswitchinterval(previous_switch_interval)
    commits_during = sink.commits
    rows_enqueued = wal.enqueued
    wal.close()
    path.unlink(missing_ok=True)
    return {
        "arm": "concurrent",
        "delay_s": delay_s,
        "commits_during_hot_loop": commits_during,
        "rows_committed": len(sink.rows),
        "rows_enqueued": rows_enqueued,
        "iterations_driven": index,
        "overlap_stretch_cap_hit": index >= cap,
        "switch_interval_s": OVERLAP_SWITCH_INTERVAL_S,
        **_stats(samples),
    }


def synchronous_control(root: Path, iterations: int, delay_s: float) -> dict[str, Any]:
    """ARM 3: THE CONTROL. The identical slow sink, wired INLINE on the hot path.

    If this arm's p99 is not inflated by roughly `delay_s`, the instrument
    cannot see blocking and ARM 2's green says nothing.
    """
    path = root / f"hotpath-ctl-{uuid.uuid4().hex[:8]}.wal"
    wal = Plane1Wal(path)
    sink = SlowSink(delay_s)
    writer = GroupCommitWriter(wal, sink, batch_max=8)
    gate, order, picture = _gate(), _order(), _picture()
    samples: list[int] = []
    for index in range(iterations):
        start = time.perf_counter_ns()
        gate.evaluate(order, picture, 1.0 + index)
        wal.enqueue(_row(index))
        wal.sync_to_disk()
        writer.drain_once()
        samples.append(time.perf_counter_ns() - start)
    commits = sink.commits
    wal.close()
    path.unlink(missing_ok=True)
    return {
        "arm": "synchronous_control",
        "delay_s": delay_s,
        "commits_during_hot_loop": commits,
        "rows_committed": len(sink.rows),
        **_stats(samples),
    }


def _scratch_database() -> tuple[str, str]:
    """Build a scratch Plane-1 database. Returns `(name, error)`."""
    if shutil.which("psql") is None or shutil.which("createdb") is None:
        return "", "psql/createdb are not on PATH"
    # Imported here so the drill's fast arms do not depend on the provisioner.
    import provision_plane1  # pylint: disable=import-outside-toplevel

    name = "p1a_hotpath_" + uuid.uuid4().hex[:10]
    try:
        outcome, detail = provision_plane1.provision(name, provision_plane1.SCHEMA_SQL)
    except provision_plane1.ProvisionError as exc:
        return "", f"cannot provision {name}: {exc}"
    if outcome != "created":
        return "", f"provisioning {name} returned {outcome}: {detail}"
    return name, ""


def _drop_database(name: str) -> None:
    binary = shutil.which("dropdb")
    if binary is None or not name:
        return
    import subprocess  # nosec B404  pylint: disable=import-outside-toplevel

    subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "--if-exists", "--force", name],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def postgres_concurrent(  # pylint: disable=too-many-locals
    root: Path, iterations: int
) -> dict[str, Any]:
    """ARM 4: ARM 2 again, against the REAL sink and a real database.

    Skipped-and-named when the cluster is unreachable (§17), never silently
    dropped: an arm that vanishes on a box without Postgres would let the whole
    drill report isolation while never touching the shipped sink.
    """
    database, error = _scratch_database()
    if error:
        return {"arm": "postgres", "available": False, "error": error}
    path = root / f"hotpath-pg-{uuid.uuid4().hex[:8]}.wal"
    wal = Plane1Wal(path)
    sink = Plane1PostgresSink(database)
    writer = GroupCommitWriter(wal, sink, batch_max=64)
    lock = threading.Lock()
    stop = threading.Event()
    failures: list[str] = []

    def persist() -> None:
        while not stop.is_set():
            with lock:
                try:
                    wal.sync_to_disk()
                except OSError:  # pragma: no cover
                    return
            try:
                writer.drain_once()
            except SinkError as exc:  # pragma: no cover - drain_once catches
                failures.append(str(exc))
                return

    for index in range(64):
        wal.enqueue(_row(index))
    wal.sync_to_disk()

    thread = threading.Thread(target=persist, name="plane1-pg-persist", daemon=True)
    gate, order, picture = _gate(), _order(), _picture()
    thread.start()
    samples: list[int] = []
    try:
        index = 0
        cap = iterations * MAX_OVERLAP_STRETCH
        while index < cap and (len(samples) < iterations or sink.groups < 1):
            start = time.perf_counter_ns()
            gate.evaluate(order, picture, 1.0 + index)
            if wal.enqueued < MAX_WAL_ROWS:
                with lock:
                    wal.enqueue(_row(index))
            samples.append(time.perf_counter_ns() - start)
            index += 1
    finally:
        stop.set()
        thread.join(timeout=30.0)
    landed = sink.rows_landed
    groups = sink.groups
    wal.close()
    path.unlink(missing_ok=True)
    _drop_database(database)
    return {
        "arm": "postgres",
        "available": True,
        "database": database,
        "groups_during_hot_loop": groups,
        "rows_landed": landed,
        "sink_failures": failures,
        **_stats(samples),
    }


def run_drill(
    root: Path,
    *,
    iterations: int = DEFAULT_ITERATIONS,
    control_iterations: int = DEFAULT_CONTROL_ITERATIONS,
    delay_s: float = DEFAULT_DELAY_S,
) -> dict[str, Any]:
    """Every arm, once. The check reads this dict and never re-derives it."""
    root.mkdir(parents=True, exist_ok=True)
    return {
        "root": str(root),
        "delay_s": delay_s,
        "baseline": baseline(iterations),
        "concurrent": concurrent(root, iterations, delay_s),
        "synchronous_control": synchronous_control(root, control_iterations, delay_s),
        "postgres": postgres_concurrent(root, iterations),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the drill and print it as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument(
        "--control-iterations", type=int, default=DEFAULT_CONTROL_ITERATIONS
    )
    parser.add_argument("--delay-s", type=float, default=DEFAULT_DELAY_S)
    args = parser.parse_args(argv)
    root = args.root or Path(
        tempfile.mkdtemp(prefix="nixp1hot-", dir=os.environ.get("TMPDIR", "/tmp"))  # nosec B108
    )
    print(
        json.dumps(
            run_drill(
                root,
                iterations=args.iterations,
                control_iterations=args.control_iterations,
                delay_s=args.delay_s,
            ),
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
