#!/usr/bin/env python3
"""§9's durability, measured on processes that really die and syscalls really made.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §9 (*durable local WAL …
crash gap healed by startup reconciliation*), §12.4 (*Degraded persistence ≠
degraded trading*; **disk-critical** ⇒ HALT new entries). Subject:
`scripts/nixrisk/wal.py`. Pattern: `scripts/feed_kill_drill.py` — self
re-execution under `sys.executable`, the child announces its own PID, the parent
kills BY PID and reports the KERNEL's reaped wait status.

---

## §0a — WHAT WOULD HAVE TO BE TRUE FOR THIS DRILL TO MEASURE NOTHING

1. **The fsync is never made and nobody looks.** `sync_to_disk`'s docstring says
   it fsyncs. A docstring is not a syscall. Closed by `observe_fsync`, which runs
   a child under `strace -y -e trace=fsync,fdatasync` and requires an `fsync`
   line **annotated with this WAL's own path** — `strace -y` prints the fd's
   target, so the arm can tell an fsync of the WAL from an fsync of anything else
   the interpreter touched. And it is paired with a CONTROL that runs the same
   child with the sync withheld and requires the line to be ABSENT: without that
   half, an arm that matched any line at all in a busy trace would pass forever.

2. **Nothing crashes.** A crash-gap test that never crashes measures the happy
   path with extra steps. Closed by `crash_gap`: `os.kill(pid, SIGKILL)` against
   a PID the child announced, and the verdict reads `Popen.wait`'s reaped status,
   which must be exactly `-SIGKILL`. A clean exit — reaped `0` — is a DIFFERENT
   arm (`clean_exit`) and the two are compared, so "the process died" cannot be
   satisfied by a process that finished.

3. **The disk never refuses.** §12.4's disk-critical branch is the one that HALTs
   a business, and a mock that raises `OSError` proves only that the code has an
   `except`. Closed by `disk_critical`: a child sets `RLIMIT_FSIZE`, ignores
   `SIGXFSZ`, and appends until the KERNEL returns `EFBIG`. That is a real
   refusal by a real filesystem layer.

4. **The recovery reader is never shown damage.** Closed by the `torn` variant of
   `crash_gap`: after its fsync the child writes the first half of a record's
   bytes and then blocks, so the kill lands with a partial record on disk. The
   half-write is staged rather than raced — a race for a mid-`write(2)` kill is
   unwinnable, because the kernel completes a small `write(2)` to a regular file
   whatever signal is pending — and it is the SHAPE a crash mid-flush leaves. The
   process death is real; the position of the cut is chosen.

---

## WHAT THIS DRILL CANNOT PROVE, STATED RATHER THAN IMPLIED

**SIGKILL DOES NOT TEST FSYNC.** A killed process's dirty pages belong to the
kernel, which is still running and still owns them, so every byte `enqueue`
returned from is readable afterwards whether or not `sync_to_disk` was ever
called. `crash_gap` therefore measures what a restarted Limiter can RECOVER and
how far behind the group-commit sink is; it says nothing about a power cut, and
the fsync arm exists precisely because it cannot. Anyone reading a green here as
"durable across power loss" is reading it wrong — that needs the machine to lose
power, and this drill does not.

**And nothing here is Postgres.** §9's group-commit sink is a `RecordingSink` in
memory. Full Postgres schema integration and §9's *"crash gap healed by startup
reconciliation vs broker truth"* are NOT in this arc.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess  # nosec B404 - re-executes THIS file; argv built here, no shell
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))

# pylint: disable=wrong-import-position
from nixrisk.seam import EventKind, EventRow
from nixrisk.wal import (
    DiskCritical,
    GroupCommitWriter,
    PersistenceState,
    Plane1Wal,
    RecordingSink,
    encode_row,
    recover,
)

#: Rows the child makes durable before anything else happens. The floor the
#: crash-gap arm asserts against: below this "nothing was lost" is a statement
#: about an empty set.
DURABLE_ROWS = 32
#: Rows the child enqueues WITHOUT syncing, in a loop, until it is killed. The
#: gap is measured, never assumed, so this is only an upper bound on the loop.
GAP_ROWS = 4096
#: Seconds the parent lets the child run before killing it. Long enough that the
#: child is inside its unsynced loop; short enough that a drill is a drill.
KILL_AFTER_S = 0.35
#: Ceiling on reaping a SIGKILLed child. A miss here is a broken machine.
REAP_TIMEOUT_S = 20.0
#: Ceiling on the strace-observed child, which does a fixed, tiny amount of work.
STRACE_TIMEOUT_S = 60.0
#: Bytes the disk-critical child is allowed to write before the kernel refuses.
FSIZE_LIMIT = 4096

#: `strace -y` annotates each fd with its target: `fsync(3</path/to/wal>) = 0`.
#: Anchored on the PATH, not merely on the verb, so an fsync of anything else the
#: interpreter touched cannot satisfy the arm.
_FSYNC_LINE = re.compile(r"\b(fsync|fdatasync)\((?P<fd>\d+)<(?P<path>[^>]+)>")


def _row(index: int) -> EventRow:
    """One §9 row. Every field the spec requires on every row."""
    return EventRow(
        kind=EventKind.ACCEPTED,
        ts=time.time(),
        strategy_id="drill",
        reason=f"wal drill row {index}",
        trade_id=f"T{index:06d}",
        fields={"index": str(index)},
    )


# ---------------------------------------------------------------------------
# The children
# ---------------------------------------------------------------------------


def _announce(**fields: Any) -> None:
    """One JSON line, flushed. The parent must learn the PID from the CHILD."""
    print(json.dumps({"pid": os.getpid(), **fields}), flush=True)


def _produce(path: Path, *, sync: bool, torn: bool, hold_s: float) -> int:
    """Child: fill a WAL, optionally sync it, then either block or exit cleanly.

    `hold_s < 0` means *block forever* — the parent will kill it. `hold_s >= 0`
    means run for that long and exit 0, which is the clean-exit CONTROL.
    """
    wal = Plane1Wal(path)
    for index in range(DURABLE_ROWS):
        wal.enqueue(_row(index))
    made = wal.sync_to_disk() if sync else 0
    if torn:
        # A HALF RECORD, written straight at the fd the WAL owns. Staged, not
        # raced: see the module docstring for why a mid-write(2) kill is
        # unwinnable and why the shape is what matters.
        record = encode_row(_row(9_999))
        os.write(wal.fileno(), record[: len(record) // 2])
    _announce(
        path=str(path),
        durable=made,
        pending=wal.pending(),
        bytes_written=wal.bytes_written,
        durable_bytes=wal.durable_bytes,
        fsyncs=wal.fsyncs,
        torn=torn,
    )
    deadline = time.monotonic() + hold_s
    index = DURABLE_ROWS
    while hold_s < 0 or time.monotonic() < deadline:
        if index < DURABLE_ROWS + GAP_ROWS and not torn:
            wal.enqueue(_row(index))
            index += 1
        else:
            time.sleep(0.005)
    wal.close()
    return 0


def _critical(path: Path) -> int:
    """Child: append under `RLIMIT_FSIZE` until the KERNEL refuses. §12.4."""
    import resource  # pylint: disable=import-outside-toplevel

    # SIGXFSZ's default action is to terminate. Ignored so the write returns
    # EFBIG to the caller instead, which is the condition §12.4 is about: the
    # WAL cannot append and the process is still alive to say so.
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_LIMIT, FSIZE_LIMIT))
    wal = Plane1Wal(path)
    sink = RecordingSink()
    writer = GroupCommitWriter(wal, sink)
    refusal = ""
    accepted = 0
    for index in range(GAP_ROWS):
        try:
            wal.enqueue(_row(index))
        except DiskCritical as exc:
            refusal = str(exc)
            break
        accepted += 1
    admits, admit_reason = wal.admits_new_entries()
    exits, exit_reason = wal.protective_exit_allowed()
    _announce(
        path=str(path),
        accepted=accepted,
        refusal=refusal,
        state=wal.state.value,
        admits_new_entries=admits,
        admit_reason=admit_reason,
        protective_exit_allowed=exits,
        exit_reason=exit_reason,
        backlog=writer.backlog(),
    )
    return 0


# ---------------------------------------------------------------------------
# The parent — the arms
# ---------------------------------------------------------------------------


def _child_argv(mode: str, path: Path, **flags: Any) -> list[str]:
    """argv for one child. Built here; never a shell string."""
    argv = [sys.executable, str(Path(__file__).resolve()), mode, "--path", str(path)]
    for name, value in flags.items():
        if value is True:
            argv.append(f"--{name.replace('_', '-')}")
        elif value is not False and value is not None:
            argv += [f"--{name.replace('_', '-')}", str(value)]
    return argv


def _spawn(argv: list[str]) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    """Start a child and read its self-announcement. Raises if it never spoke."""
    # pylint: disable=consider-using-with
    # The child outlives this call by design; every caller owns the kill and the
    # reap on every path, including the paths where the arm fails.
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=REAP_TIMEOUT_S)
        stderr = (proc.stderr.read() if proc.stderr else "")[:600]
        raise RuntimeError(f"child printed no announcement; stderr={stderr!r}")
    return proc, json.loads(line)


def crash_gap(root: Path, *, torn: bool = False) -> dict[str, Any]:
    """SIGKILL a child mid-WAL and report what a restarted Limiter can read back."""
    path = root / f"crash{'-torn' if torn else ''}.wal"
    proc, hello = _spawn(_child_argv("--produce", path, hold_s=-1.0, torn=torn))
    try:
        time.sleep(KILL_AFTER_S)
        kill_mono = time.monotonic()
        os.kill(proc.pid, signal.SIGKILL)
        status = proc.wait(timeout=REAP_TIMEOUT_S)
        reap_mono = time.monotonic()
    finally:
        if proc.poll() is None:  # pragma: no cover - only if the kill missed
            proc.kill()
            proc.wait(timeout=REAP_TIMEOUT_S)
    recovered = recover(path)
    durable_prefix = recover(path, int(hello["durable_bytes"]))
    return {
        "arm": "crash_gap_torn" if torn else "crash_gap",
        "path": str(path),
        "pid": proc.pid,
        "signal": "SIGKILL",
        "signal_number": int(signal.SIGKILL),
        "reap_status": status,
        "reap_latency_s": reap_mono - kill_mono,
        "announced": hello,
        "recovered_rows": len(recovered.rows),
        "durable_prefix_rows": len(durable_prefix.rows),
        "torn_tail_bytes": recovered.torn_tail_bytes,
        "corrupt_records": recovered.corrupt_records,
        "bytes_on_disk": recovered.bytes_read,
        "recovered_trade_ids": [row.trade_id for row in recovered.rows[:4]],
    }


def clean_exit(root: Path) -> dict[str, Any]:
    """The CONTROL for `crash_gap`: the same child, allowed to finish. Reaps 0."""
    path = root / "clean.wal"
    proc, hello = _spawn(_child_argv("--produce", path, hold_s=0.25, torn=False))
    status = proc.wait(timeout=REAP_TIMEOUT_S)
    recovered = recover(path)
    return {
        "arm": "clean_exit",
        "path": str(path),
        "pid": proc.pid,
        "reap_status": status,
        "announced": hello,
        "recovered_rows": len(recovered.rows),
        "torn_tail_bytes": recovered.torn_tail_bytes,
    }


def observe_fsync(root: Path, *, sync: bool) -> dict[str, Any]:
    """Run a child under `strace` and report every fsync it made, WITH the path.

    `sync=False` is the CONTROL: the identical child with `sync_to_disk`
    withheld, so the only difference between the two traces is whether the
    durability verb ran.
    """
    strace = shutil.which("strace")
    path = root / f"fsync{'' if sync else '-control'}.wal"
    trace = root / f"strace{'' if sync else '-control'}.out"
    if strace is None:
        return {
            "arm": "fsync" if sync else "fsync_control",
            "available": False,
            "reason": "strace is not on PATH — the syscall cannot be observed, "
            "and an unobserved syscall is CANNOT_MEASURE, never PASS",
            "path": str(path),
        }
    argv = [strace, "-f", "-y", "-e", "trace=fsync,fdatasync", "-o", str(trace)]
    argv += _child_argv("--produce", path, hold_s=0.0, torn=False, no_sync=not sync)
    proc = subprocess.run(  # nosec B603 - argv built here, no shell
        argv, capture_output=True, text=True, timeout=STRACE_TIMEOUT_S, check=False
    )
    text = trace.read_text(encoding="utf-8", errors="replace") if trace.exists() else ""
    matched = [
        line
        for line in text.splitlines()
        if (m := _FSYNC_LINE.search(line)) and Path(m.group("path")) == path
    ]
    return {
        "arm": "fsync" if sync else "fsync_control",
        "available": True,
        "path": str(path),
        "strace": strace,
        "returncode": proc.returncode,
        "trace_lines": len(text.splitlines()),
        "fsync_lines_for_wal": matched,
        "fsync_count_for_wal": len(matched),
        "stderr": proc.stderr[-400:],
    }


def disk_critical(root: Path) -> dict[str, Any]:
    """§12.4's disk-critical arm, produced by the KERNEL and not by a mock."""
    path = root / "critical.wal"
    proc, hello = _spawn(_child_argv("--critical", path))
    status = proc.wait(timeout=REAP_TIMEOUT_S)
    return {"arm": "disk_critical", "reap_status": status, **hello}


def sink_outage(root: Path) -> dict[str, Any]:
    """§12.4's OTHER half, in-process: Postgres down, WAL buffers, trading on.

    In-process rather than in a child on purpose: the property is about what the
    Limiter's own objects report, and a subprocess boundary would put a JSON
    round-trip between the assertion and the state it is about.
    """
    path = root / "outage.wal"
    alerts: list[tuple[str, str]] = []
    wal = Plane1Wal(path, alert=lambda event, detail: alerts.append((event, detail)))
    sink = RecordingSink()
    writer = GroupCommitWriter(wal, sink)
    for index in range(8):
        wal.enqueue(_row(index))
    wal.sync_to_disk()
    healthy = writer.drain_once()

    sink.fail_with = RuntimeError("planted Postgres outage: connection refused")
    for index in range(8, 24):
        wal.enqueue(_row(index))
    wal.sync_to_disk()
    degraded = writer.drain_once()
    admits, admit_reason = wal.admits_new_entries()
    # Trading CONTINUES: the WAL still takes entries while the sink is down.
    wal.enqueue(_row(24))
    accepted_during_outage = wal.pending()

    sink.fail_with = None
    restored = writer.drain_once()
    wal.close()
    return {
        "arm": "sink_outage",
        "path": str(path),
        "healthy": {"committed": healthy.committed, "state": healthy.state.value},
        "degraded": {
            "committed": degraded.committed,
            "backlog": degraded.backlog,
            "state": degraded.state.value,
            "error": degraded.error,
        },
        "restored": {
            "committed": restored.committed,
            "backlog": restored.backlog,
            "state": restored.state.value,
        },
        "admits_new_entries": admits,
        "admit_reason": admit_reason,
        "accepted_during_outage": accepted_during_outage,
        "alerts": alerts,
        "rows_in_sink": len(sink.rows),
        "expected_state": PersistenceState.SINK_DEGRADED.value,
    }


def run_drill(root: Path) -> dict[str, Any]:
    """Every arm, once. The check reads this dict and never re-derives it."""
    root.mkdir(parents=True, exist_ok=True)
    return {
        "nonce": f"ARC028S2-{secrets.token_hex(6)}",
        "root": str(root),
        "fsync": observe_fsync(root, sync=True),
        "fsync_control": observe_fsync(root, sync=False),
        "crash": crash_gap(root),
        "crash_torn": crash_gap(root, torn=True),
        "clean": clean_exit(root),
        "critical": disk_critical(root),
        "outage": sink_outage(root),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--produce", action="store_true", help="child: fill a WAL")
    parser.add_argument("--critical", action="store_true", help="child: RLIMIT_FSIZE")
    parser.add_argument("--path", type=Path, help="WAL path (children)")
    parser.add_argument("--hold-s", type=float, default=-1.0)
    parser.add_argument("--torn", action="store_true")
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--root", type=Path, help="scratch root (parent)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one child mode, or the whole drill and print it as JSON."""
    args = _parser().parse_args(argv)
    if args.critical or args.produce:
        if args.path is None:
            raise SystemExit("--path is required for a child mode")
        if args.critical:
            return _critical(args.path)
        return _produce(
            args.path, sync=not args.no_sync, torn=args.torn, hold_s=args.hold_s
        )
    root = args.root or Path(os.environ.get("TMPDIR", "/tmp")) / "nixwal"  # nosec B108
    print(json.dumps(run_drill(root), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
