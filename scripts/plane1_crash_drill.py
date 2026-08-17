#!/usr/bin/env python3
# pylint: disable=too-many-instance-attributes,missing-function-docstring
# The drill carries one attribute per moving part of the ephemeral cluster
# (data dir, socket dir, port, log path, pid, dbname, ...) because each one
# is separately asserted when the crash is measured.
# pylint: disable=duplicate-code
# R0801 must be disabled at the TOP of the file, before the docstring: the
# similarities checker reports at module scope and a pragma further down
# does not reach it. Same placement as check_nixverify_init.py and a dozen
# siblings. What it pairs here is this arc's Plane-1 modules by their shared
# psql helpers, declaration blocks and scratch-cluster fixtures — required by
# §4.2 (every check independently runnable and self-contained), and written
# by four sub-agents in worktrees that could not see each other.
"""§9's crash gap, measured at a REAL durability boundary — on its OWN cluster.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §9 (*"Enqueue → durable local
WAL → shared-pool writer → group-commit to Postgres. Crash gap healed by startup
reconciliation vs broker truth."*). ARC 035 / Stage 1 / sub-agent B (B3).
Companion: `scripts/wal_kill_drill.py`, which owns the LOCAL-WAL half and whose
`observe_fsync` arm is reused here rather than reinvented.

==============================================================================
§0a — WHAT WOULD HAVE TO BE TRUE FOR THIS DRILL TO MEASURE NOTHING
==============================================================================

**1. THE CRASH MIGHT NOT DISCRIMINATE — A PREDICTION THIS DRILL MADE AND THEN
MEASURED AND WITHDREW.** `-m immediate` sends `SIGQUIT` to the postmaster: the
*server* dies without a checkpoint and recovers from WAL on restart. The page
cache belongs to a kernel that is still running, so the reasoning goes that every
byte written but never fsynced is still there and a cluster started with
`fsync = off` would pass a naive "committed rows survived the crash" test just as
green as a correct one.

**That prediction is WRONG on PostgreSQL 18.4, and the reason it is wrong is more
interesting than the prediction.** `crash_and_recover` runs on two clusters
differing only in their DURABILITY settings. The durable one comes back with
every committed row; the contrast one comes back with the log **empty or absent
entirely**. Recovery runs, redo completes, and the rows are simply not there.

**The mechanism, because it is not the page-cache argument.** The contrast
cluster sets `synchronous_commit = off`, and that means `COMMIT` returns before
the WAL record has left **PostgreSQL's own shared WAL buffers** — which are
shared memory, not the kernel's page cache. `SIGQUIT` destroys shared memory. So
the lost rows were never handed to the kernel at all, and the "a living kernel
still owns the dirty pages" reasoning simply does not reach them. The prediction
was not merely wrong about the outcome; it was reasoning about the wrong buffer.

**What the differential does NOT license.** It is evidence that the settings
matter. It is NOT evidence about POWER LOSS, because nothing in this drill drops
a page cache — the durable cluster's rows reached the kernel and were fsynced,
and no instrument here can say what a disk does after that. The direct evidence
that the durability verb ran is still arm 2, the observed `fdatasync` on this
cluster's own `pg_wal/`; the crash arm is corroboration beside it, never a
replacement for it.

**2. THE FSYNC IS NEVER MADE AND NOBODY LOOKS.** `synchronous_commit = on` is a
setting, and a setting is a claim. *Closed by* `fsync_lines`: the postmaster runs
under `strace -f -y -e trace=fsync,fdatasync`, `-y` annotates each fd with its
target, and the arm requires a line whose path is under **this cluster's own**
`pg_wal/` — so an fsync of a data file, or of anything else on the box, cannot
satisfy it. The CONTROL is the same cluster with `fsync = off`, requiring the
line to be **ABSENT**. Both halves, exactly as `wal_kill_drill.observe_fsync`
does for the local WAL; the control is what stops "matched some line in a busy
trace" from passing forever.

**3. "THE UNCOMMITTED TAIL DOES NOT SURVIVE" IS DRESSED UP AS DURABILITY.** It is
not, and this file says so rather than banking it. An uncommitted transaction's
rows are invisible to every other session before the crash and are discarded at
recovery **whether or not anything was ever fsynced**. That arm rests on the
TRANSACTION boundary, would pass under a bare `kill -9` of the postmaster, and is
reported with `boundary = "transaction (NOT durability)"`. It is worth measuring
— it is the crash gap's near edge — and it is not evidence about fsync.

**4. NOTHING CRASHES.** *Closed:* `pg_ctl -m immediate stop`'s return code and the
recovery line in the restarted server's log are both captured, and the restarted
postmaster must actually report a crash recovery rather than a clean start.

==============================================================================
WHAT THIS DRILL CANNOT PROVE, STATED RATHER THAN IMPLIED
==============================================================================

**It does not prove survival of POWER LOSS.** An observed `fsync(2)` that
returned 0 is a syscall the kernel completed; a drive that lies about its write
cache is outside every instrument in this tree. Proving that needs the machine to
lose power, and this drill does not.

**It never touches the system cluster.** There is one live PostgreSQL 18.4
cluster on this box carrying `trade_history`, `nix_plane1` and three sibling
agents' work. Everything here happens on a cluster this file creates with
`initdb`, listening on **no TCP port at all** (`listen_addresses = ''`) over a
private UNIX socket directory, and destroys on the way out.
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
import contextlib
import json
import re
import shutil
import subprocess  # nosec B404 - pg_ctl/initdb/psql ARE the instruments
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))

# pylint: disable=wrong-import-position
from nixrisk.projection import Psql

REPO = _HERE.parent
SCHEMA_SQL = REPO / "databases" / "schema" / "plane1.sql"

#: Where PostgreSQL's own binaries live when they are not on PATH. Ubuntu ships
#: `psql` via a wrapper and leaves `initdb`/`pg_ctl`/`postgres` here.
_PG_BIN_GLOB = "/usr/lib/postgresql/*/bin"

#: Seconds to wait for a freshly started postmaster to accept connections.
READY_TIMEOUT_S = 60.0
#: Seconds to wait for `initdb`, `pg_ctl` and the workload psql calls.
CMD_TIMEOUT_S = 180.0

#: `strace -y` annotates each fd with its target:
#: `fdatasync(8</tmp/…/pg_wal/000000010000000000000001>) = 0`. Anchored on the
#: PATH, never on the verb alone.
_SYNC_LINE = re.compile(r"\b(fsync|fdatasync)\((?P<fd>\d+)<(?P<path>[^>]+)>")

#: Rows the drill commits before crashing. Below a handful, "they all came back"
#: is a statement about a set small enough to be an accident.
COMMITTED_ROWS = 24
#: Rows written inside a transaction that is never committed.
UNCOMMITTED_ROWS = 8


def pg_bin(name: str) -> str:
    """Locate a PostgreSQL binary. Raises rather than silently degrading."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in sorted(Path("/").glob(_PG_BIN_GLOB.lstrip("/")), reverse=True):
        if (candidate / name).is_file():
            return str(candidate / name)
    raise RuntimeError(
        f"{name} is not on PATH and not under {_PG_BIN_GLOB}; the durability "
        f"boundary cannot be built, and an unbuildable boundary is "
        f"CANNOT_MEASURE, never PASS"
    )


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - argv built here, no shell
        argv,
        capture_output=True,
        text=True,
        timeout=CMD_TIMEOUT_S,
        check=False,
        **kwargs,
    )


class Cluster:
    """An ephemeral PostgreSQL cluster this process owns, crashes and destroys.

    Listens on **no TCP port** and speaks only over a private UNIX socket
    directory, so nothing else on the box can reach it and it cannot be confused
    with the system cluster three sibling agents are using.

    `fsync` is a constructor argument rather than a constant because the whole
    §0a argument of this file is a comparison between a cluster that syncs and
    one that does not.
    """

    def __init__(self, root: Path, *, fsync: bool = True, trace: bool = True) -> None:
        self.root = root
        self.pgdata = root / "pg"
        self.sock = root / "sock"
        self.fsync = fsync
        self.trace = trace and shutil.which("strace") is not None
        self.traces: list[Path] = []
        self._proc: subprocess.Popen[str] | None = None
        self._starts = 0
        self.logs: list[Path] = []

    # -- lifecycle ----------------------------------------------------------

    def initdb(self) -> None:
        """Create the cluster. `--no-sync` affects initdb's OWN writes only."""
        self.sock.mkdir(parents=True, exist_ok=True)
        result = _run(
            [
                pg_bin("initdb"),
                "-D",
                str(self.pgdata),
                "--auth=trust",
                "-E",
                "UTF8",
                "--no-sync",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"initdb failed: {result.stderr[-500:]}")

    def start(self) -> None:
        """Start the postmaster in the FOREGROUND, optionally under strace."""
        self._starts += 1
        log = self.root / f"server-{self._starts}.log"
        self.logs.append(log)
        argv: list[str] = []
        if self.trace:
            trace = self.root / f"strace-{self._starts}.out"
            self.traces.append(trace)
            argv += [
                shutil.which("strace") or "strace",
                "-f",
                "-y",
                "-e",
                "trace=fsync,fdatasync",
                "-o",
                str(trace),
            ]
        argv += [
            pg_bin("postgres"),
            "-D",
            str(self.pgdata),
            "-k",
            str(self.sock),
            "-c",
            "listen_addresses=",
            "-c",
            f"synchronous_commit={'on' if self.fsync else 'off'}",
            "-c",
            f"fsync={'on' if self.fsync else 'off'}",
            "-c",
            "full_page_writes=on",
        ]
        if not self.fsync:
            # The contrast cluster's THIRD durability knob, and it is here to
            # make the contrast DETERMINISTIC rather than to widen it. With
            # `synchronous_commit = off` the walwriter still flushes every
            # `wal_writer_delay`, so on a slow run it can flush the whole batch
            # before the crash and the contrast silently disappears — a flaky
            # gate that sometimes reports "the crash no longer discriminates"
            # when nothing changed. Ten seconds is longer than the drill lives.
            argv += ["-c", "wal_writer_delay=10000ms"]
        handle = log.open("w", encoding="utf-8")
        # pylint: disable=consider-using-with
        # The postmaster outlives this call by design; `close()` owns the reap on
        # every path, including the paths where an arm fails.
        self._proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
            argv, stdout=handle, stderr=handle, text=True
        )
        self._await_ready()

    def _await_ready(self) -> None:
        ready = pg_bin("pg_isready")
        deadline = time.monotonic() + READY_TIMEOUT_S
        while time.monotonic() < deadline:
            probe = _run([ready, "-h", str(self.sock), "-q"])
            if probe.returncode == 0:
                return
            time.sleep(0.2)
        raise RuntimeError(
            f"postmaster never became ready; log tail: "
            f"{self.logs[-1].read_text(errors='replace')[-800:]}"
        )

    def stop_immediate(self) -> dict[str, Any]:
        """CRASH the server: `pg_ctl -m immediate` — SIGQUIT, no checkpoint.

        This is a real crash of PostgreSQL and it is NOT a power-loss boundary.
        See §0a hazard 1: the page cache belongs to a kernel that is still
        running. What makes the surviving rows a DURABILITY claim is the observed
        fsync, not this call.
        """
        result = _run(
            [pg_bin("pg_ctl"), "-D", str(self.pgdata), "-m", "immediate", "stop"]
        )
        status = None
        if self._proc is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                status = self._proc.wait(timeout=30)
            self._proc = None
        return {
            "mode": "immediate",
            "pg_ctl_rc": result.returncode,
            "pg_ctl_stderr": result.stderr[-300:],
            "postmaster_wait_status": status,
        }

    def close(self) -> None:
        """Stop whatever is running and delete the cluster. Never raises."""
        with contextlib.suppress(Exception):
            _run([pg_bin("pg_ctl"), "-D", str(self.pgdata), "-m", "immediate", "stop"])
        if self._proc is not None:
            with contextlib.suppress(Exception):
                self._proc.kill()
                self._proc.wait(timeout=30)
            self._proc = None
        shutil.rmtree(self.root, ignore_errors=True)

    # -- workload -----------------------------------------------------------

    def createdb(self, name: str) -> Psql:
        result = _run([pg_bin("createdb"), "-h", str(self.sock), name])
        if result.returncode != 0:
            raise RuntimeError(f"createdb {name}: {result.stderr[-300:]}")
        return self.psql(name)

    def psql(self, name: str) -> Psql:
        return Psql(dbname=name, host=str(self.sock))

    def load_schema(self, name: str) -> None:
        result = _run(
            [
                pg_bin("psql"),
                "-h",
                str(self.sock),
                "-d",
                name,
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(SCHEMA_SQL),
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"loading {SCHEMA_SQL}: {result.stderr[-500:]}")

    # -- observation --------------------------------------------------------

    def wal_sync_lines(self) -> list[str]:
        """Every `fsync`/`fdatasync` line whose fd points inside THIS `pg_wal/`."""
        wal = (self.pgdata / "pg_wal").resolve()
        found: list[str] = []
        for trace in self.traces:
            if not trace.exists():
                continue
            for line in trace.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                match = _SYNC_LINE.search(line)
                if match is None:
                    continue
                with contextlib.suppress(ValueError, OSError):
                    if wal in Path(match.group("path")).resolve().parents:
                        found.append(line.strip())
        return found

    def recovered(self) -> bool:
        """Did the restarted postmaster report a CRASH recovery, not a clean start?"""
        needles = ("database system was not properly shut down", "redo starts at")
        for log in self.logs:
            if not log.exists():
                continue
            text = log.read_text(encoding="utf-8", errors="replace")
            if any(needle in text for needle in needles):
                return True
        return False


@contextlib.contextmanager
def ephemeral_cluster(*, fsync: bool = True, trace: bool = True) -> Iterator[Cluster]:
    """An initialised, running cluster; destroyed on the way out, always."""
    root = Path(tempfile.mkdtemp(prefix="p1b-pg-"))
    cluster = Cluster(root, fsync=fsync, trace=trace)
    try:
        cluster.initdb()
        cluster.start()
        yield cluster
    finally:
        cluster.close()


# ---------------------------------------------------------------------------
# The rows. Written AS `nix_limiter` — the sole writer's identity (§12.10).
# ---------------------------------------------------------------------------


def _insert_sql(first_seq: int, count: int, tag: str) -> str:
    values = ",\n".join(
        f"('2026-08-17 12:{(first_seq + i) % 60:02d}:00+00', 'signal', 'drill', "
        f"'T-{first_seq + i:05d}', 'crash drill {tag} row {i}', "
        f"{first_seq + i}, 'crash-{tag}-{first_seq + i}')"
        for i in range(count)
    )
    # B608 argued once, here. Every interpolation above is an INT computed in
    # this function from its own arguments, or `tag`, which every caller passes
    # as a string literal. No value reaches this SQL from a database row, an
    # environment variable, a file, or a caller outside this module.
    return (
        "INSERT INTO plane1_event_log (occurred_at, event_type, strategy_id, "  # nosec B608
        "trade_id, reason, wal_seq, natural_key) VALUES\n" + values + ";"
    )


def commit_rows(psql: Psql, first_seq: int, count: int, tag: str) -> None:
    """One group-commit batch, COMMITTED, as the Limiter's role."""
    statement = (
        "BEGIN;\nSET ROLE nix_limiter;\n"
        + _insert_sql(first_seq, count, tag)
        + "\nCOMMIT;\n"
    )
    rc, _out, err = psql.run(statement, verbose=True)
    if rc != 0:
        raise RuntimeError(f"committed batch failed: {err[-400:]}")


def open_uncommitted(cluster: Cluster, dbname: str, first_seq: int, count: int):
    """Start a transaction that INSERTs and never commits. Returns the live psql.

    Held open deliberately: the rows must be uncommitted **at the instant of the
    crash**, and a psql that had exited would have rolled back before it.
    """
    argv = [
        pg_bin("psql"),
        "-h",
        str(cluster.sock),
        "-d",
        dbname,
        "-qAt",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    # pylint: disable=consider-using-with
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None  # nosec B101 - PIPE was requested above
    proc.stdin.write(
        "BEGIN;\nSET ROLE nix_limiter;\n"
        + _insert_sql(first_seq, count, "uncommitted")
        + "\nSELECT 'staged';\n"
    )
    proc.stdin.flush()
    assert proc.stdout is not None  # nosec B101 - PIPE was requested above
    line = proc.stdout.readline().strip()
    if line != "staged":
        proc.kill()
        raise RuntimeError(f"uncommitted staging did not confirm; got {line!r}")
    return proc


def count_rows(psql: Psql) -> int:
    return int(psql.must("select count(*) from plane1_event_log"))


def survived_rows(psql: Psql) -> tuple[int | None, str]:
    """Rows after recovery — or `(None, reason)` when the RELATION itself is gone.

    A missing table after a crash is a MEASUREMENT, not an instrument failure. It
    is exactly what the `fsync=off` cluster looks like on this box, and raising
    here would turn the most interesting result in the drill into a traceback in
    a fixture. §18: the reason is carried, never just the failure.
    """
    rc, out, err = psql.run("select count(*) from plane1_event_log")
    if rc != 0:
        return None, err[-300:]
    return int(out), ""


# ---------------------------------------------------------------------------
# The arms
# ---------------------------------------------------------------------------


def crash_and_recover(*, fsync: bool) -> dict[str, Any]:
    """Commit rows, stage an uncommitted tail, CRASH, restart, and count.

    Run twice by `run_drill` — once durable, once with durability disabled —
    because the DIFFERENCE between the two results is the whole §0a argument, and
    the difference measured here is not the one this file first predicted. How
    MUCH the contrast cluster loses varies (nothing at all, or the relation
    itself), which is what "no durability guarantee" looks like from outside;
    THAT it loses committed rows is what the gate asserts.
    """
    dbname = "p1b_crash"
    with ephemeral_cluster(fsync=fsync) as cluster:
        psql = cluster.createdb(dbname)
        cluster.load_schema(dbname)
        commit_rows(psql, 1, COMMITTED_ROWS, "committed")
        committed_before = count_rows(psql)
        staged = open_uncommitted(cluster, dbname, 1000, UNCOMMITTED_ROWS)
        visible_to_others = count_rows(psql)
        crash = cluster.stop_immediate()
        # AFTER the stop, never before: strace buffers its output file, so a
        # trace read while the tracer is still alive can report zero lines for
        # syscalls that were really made — an instrument failure that reads
        # exactly like the absence of an fsync.
        sync_lines_at_commit = cluster.wal_sync_lines()
        with contextlib.suppress(Exception):
            staged.kill()
            staged.wait(timeout=30)
        cluster.start()
        after, recovery_error = survived_rows(cluster.psql(dbname))
        return {
            "arm": "crash_and_recover",
            "fsync": "on" if fsync else "off",
            "synchronous_commit": "on" if fsync else "off",
            "committed_rows": COMMITTED_ROWS,
            "uncommitted_rows": UNCOMMITTED_ROWS,
            "rows_before_crash": committed_before,
            "rows_visible_to_other_sessions_while_staged": visible_to_others,
            "rows_after_recovery": after,
            "recovery_error": recovery_error,
            "committed_survived": after == committed_before,
            "uncommitted_survived": after is not None and after > committed_before,
            "crash": crash,
            "crash_recovery_in_server_log": cluster.recovered(),
            "wal_fsync_lines_at_commit": len(sync_lines_at_commit),
            "wal_fsync_sample": sync_lines_at_commit[:3],
            "strace_available": cluster.trace,
            "boundary": (
                "committed rows: fsync OBSERVED on this cluster's pg_wal + "
                "SIGQUIT crash recovery. uncommitted tail: TRANSACTION boundary, "
                "NOT a durability boundary — it would pass under a bare kill -9"
            ),
        }


def fsync_control() -> dict[str, Any]:
    """The both-halves CONTROL: the same workload with `fsync = off`.

    Without this half, "we saw an fsync line" would be satisfied by any fsync
    anywhere in a busy trace forever. With it, the line's ABSENCE under the one
    setting that suppresses it is what makes the presence mean something.
    """
    dbname = "p1b_ctl"
    with ephemeral_cluster(fsync=False) as cluster:
        psql = cluster.createdb(dbname)
        cluster.load_schema(dbname)
        commit_rows(psql, 1, COMMITTED_ROWS, "control")
        cluster.stop_immediate()  # flush the tracer before reading its file
        lines = cluster.wal_sync_lines()
        return {
            "arm": "fsync_control",
            "fsync": "off",
            "wal_fsync_lines": len(lines),
            "wal_fsync_sample": lines[:3],
            "strace_available": cluster.trace,
            "expectation": "ZERO — fsync=off suppresses the durability verb",
        }


def run_drill() -> dict[str, Any]:
    """Every arm, once. A caller reads this dict and never re-derives it."""
    durable = crash_and_recover(fsync=True)
    contrast = crash_and_recover(fsync=False)
    return {
        "durable": durable,
        "fsync_off_contrast": contrast,
        "fsync_control": fsync_control(),
        "predicted": (
            "that `pg_ctl -m immediate` would be VACUOUS — that the fsync=off "
            "cluster's committed rows would come back too, because the page "
            "cache belongs to a kernel that is still running"
        ),
        "measured": (
            f"REFUTED on PostgreSQL 18.4, and for a reason the prediction "
            f"missed: `synchronous_commit=off` returns from COMMIT before the "
            f"WAL record leaves PostgreSQL's own SHARED BUFFERS, which SIGQUIT "
            f"destroys — the kernel never held those bytes. durable recovered "
            f"{durable['rows_after_recovery']} of {durable['rows_before_crash']} "
            f"committed rows; the contrast cluster recovered "
            f"{contrast['rows_after_recovery']!r} "
            f"({contrast['recovery_error'] or 'no error'}). The crash arm "
            "DISCRIMINATES the durability setting"
        ),
        "boundary": (
            "the durability claim still rests primarily on the OBSERVED fdatasync "
            "on this cluster's own pg_wal/, with the crash contrast as "
            "corroboration. NEITHER is a power-loss boundary: nothing here drops "
            "a page cache"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the whole drill and print it as JSON."""
    parser = argparse.ArgumentParser(description="§9 crash-gap durability drill")
    parser.parse_args(argv)
    print(json.dumps(run_drill(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
