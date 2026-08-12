#!/usr/bin/env python3
"""§9's WAL durability and §12.4's two failures, measured on syscalls and corpses.

Subjects: `scripts/nixrisk/wal.py`, `scripts/wal_kill_drill.py`.

Authority — `docs/nics_risk_subsystem_spec_v1.3.md` §9, §11, §12.4, §12.10:
the event-sourced write path (*"Limiter = sole writer. Enqueue → durable local
WAL → shared-pool writer → group-commit to Postgres. Crash gap healed by startup
reconciliation vs broker truth."*), the hot-path discipline whose sixth item puts
group-commit off that path, *"Degraded persistence ≠ degraded trading"*, and
Plane 1's **no new writers, ever**.

Instrument doctrine — `docs/nix_check_contract.md` §4, §5, §17, §18.

ONE property (§5.5): *the Plane-1 WAL reaches stable storage by an observed
`fsync`, survives a real process death, and keeps §12.4's two failures apart —
a degraded sink buffers and trades on; a WAL that cannot append halts new
entries while protective exits stay unconditional.*

No other registered check owns any of this: `check_feed_kill_drill` owns the
DATAFEED's kill behaviour (`scripts/capture.py`, the price ring, the bus) and
`check_plane2_across_kill` owns journald's survival of a death. Neither touches
Plane 1, the WAL, or persistence state.

---

## debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
## MEASURING NOTHING

1. **NO FSYNC EVER HAPPENS.** *A WAL is durable only if it fsyncs*, and a
   durability gate passes trivially against a write that never left the page
   cache. Closed by ARM 1, which does not read `wal.py` and does not trust
   `Plane1Wal.fsyncs`: it reads `strace -y -e trace=fsync,fdatasync` output from
   a child process and requires an `fsync(fd</path/to/this/WAL>)` line. `-y`
   makes strace print the descriptor's target, so an fsync of the WAL is
   distinguishable from an fsync of anything else the interpreter touched.

2. **THE MATCHER MATCHES ANYTHING.** An arm that greps a busy trace for "fsync"
   is green forever. Closed by ARM 1's CONTROL: the identical child with
   `sync_to_disk` withheld must produce **zero** matching lines. Plant and
   control differ in one flag.

3. **NOTHING CRASHES.** A crash-gap test that never crashes measures the happy
   path. Closed by ARM 2: `os.kill(pid, SIGKILL)` against a PID the child
   announced, and the verdict reads the KERNEL's reaped wait status, which must
   be exactly `-9`. Its CONTROL is a second child allowed to finish, reaping `0`
   — so "it died" cannot be satisfied by a process that merely stopped.

4. **THE RECOVERY READER IS NEVER SHOWN DAMAGE.** Closed by ARM 3: a kill that
   lands with half a record on disk. `recover()` must not raise, must report the
   torn tail in bytes, and must still return every durable row.

5. **THE DISK NEVER REFUSES.** A mock raising `OSError` proves the code has an
   `except`. Closed by ARM 4: a child sets `RLIMIT_FSIZE`, ignores `SIGXFSZ`, and
   appends until the KERNEL returns `EFBIG`.

6. **THE TWO §12.4 FAILURES ARE NEVER TOLD APART.** The whole point of §12.4 is
   that they are different. Closed by ARM 5, which requires the disagreement
   directly: in `SINK_DEGRADED` the WAL must ADMIT new entries; in
   `DISK_CRITICAL` it must REFUSE them naming the errno; and in BOTH the
   protective exit must be permitted. An implementation that halted on either
   failure, or on neither, fails this arm.

---

## WHAT THIS GATE CANNOT PROVE, STATED RATHER THAN IMPLIED

**A SIGKILL IS NOT A POWER CUT, AND THIS GATE PUTS THE NUMBER ON IT.** A killed
process's dirty pages belong to the kernel, which is still running, so bytes that
never reached the platter are still readable. The evidence line reports both
`recovered_rows` (everything the page cache still holds) and
`durable_prefix_rows` (what the last `fsync` covered), and they differ by two
orders of magnitude. That gap is the honest statement of what ARM 2 measures and
what only ARM 1 can.

**NOT COVERED, AND NO GREEN HERE MAY BE READ AS COVERING IT:** full Postgres
schema integration (the sink is `RecordingSink`, in memory), §9's cold-start
reconciliation vs broker truth, the group-commit cursor's own durability across a
restart, stop conversion, protective-exit wiring to broker-order, session-close
flatten, full HALT semantics, the Sentinel, Scoring and the Allocator. A Limiter
that logs correctly but cannot exit is not a safety spine.
"""

from __future__ import annotations

import shutil
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

# Deliberately duplicated across every checks/check_*.py: `nix_check_contract.md`
# §4.2 requires each check be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: The drill re-executes itself under the venv interpreter.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Five claims, declared honestly (D1.54: under-declaring costs correctness,
#: over-declaring costs only parallelism).
#: * `subprocess:python3` / `subprocess:python` — the drill spawns six children
#:   through `sys.executable`. BOTH spellings, because the observer matches a
#:   subprocess claim by BASENAME and `sys.executable` is `.venv/bin/python`
#:   under pytest and `/usr/bin/python3` under `nix-verify.service`.
#: * `subprocess:strace` — ARM 1's tracer, spawned twice. Observable, and this
#:   claim is what makes it declared rather than discovered.
#: * `file-write:/tmp` — the scratch root (`tempfile.mkdtemp`), the WAL files
#:   inside it, and the strace output. Cleaned by absolute-path unlinks, NEVER by
#:   `shutil.rmtree`: on POSIX that unlinks through a directory fd with a bare
#:   relative name, which the observer records as an unattributable
#:   `file-write:crash.wal` that no rooted declaration can cover.
#: * `ptrace` — strace attaches to its own child. NOT in the observer's
#:   vocabulary (it is a syscall made by a subprocess, not by this process), so
#:   it is declared for the PLAN's benefit; two checks tracing at once is not a
#:   conflict today but the claim is real and belongs in the plan.
RESOURCES: tuple[str, ...] = (
    "subprocess:python3",
    "subprocess:python",
    "subprocess:strace",
    "file-write:/tmp",
    "ptrace",
)
TIME_BOUND = True
#: MEASURED on this node, not budgeted: two traced children, two killed children,
#: one clean child, one rlimit child, plus the in-process outage arm.
EXPECTED_S = 10.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what a WAL DOES when a process dies and when a filesystem "
    "refuses. There is no state on disk to repair, and a 'correction' would mean "
    "editing the durability path while it is the thing under measurement"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/wal.py",
    "scripts/wal_kill_drill.py",
)

NAME = "check_plane1_wal"

#: Non-vacuity floors (`debug.md` §7.12). Floors, not today's numbers.
MIN_DURABLE_ROWS = 8
MIN_TORN_TAIL_BYTES = 1
MIN_BACKLOG = 1

_SITE_FSYNC = "scripts/nixrisk/wal.py:Plane1Wal.sync_to_disk"
_SITE_RECOVER = "scripts/nixrisk/wal.py:recover"
_SITE_ADMIT = "scripts/nixrisk/wal.py:Plane1Wal.admits_new_entries"
_SITE_EXIT = "scripts/nixrisk/wal.py:Plane1Wal.protective_exit_allowed"
_SITE_COMMIT = "scripts/nixrisk/wal.py:GroupCommitWriter.drain_once"
_SITE_KILL = "scripts/wal_kill_drill.py:crash_gap os.kill(pid, SIGKILL)"


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def _import_drill() -> tuple[Any, str]:
    """Lazy import so an unimportable subject is CANNOT_MEASURE, not a load error."""
    try:
        import wal_kill_drill  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, f"cannot import wal_kill_drill under {sys.executable}: {exc!r}"
    return wal_kill_drill, ""


# ---------------------------------------------------------------------------
# Arms — each appends `(site, why)` or a narration line, and returns None
# ---------------------------------------------------------------------------


def _arm_fsync(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 1: the SYSCALL, observed, against THIS WAL's path — plus its control."""
    traced = result["fsync"]
    control = result["fsync_control"]
    if not traced["available"]:
        # §17: a property proven while its instrument is unavailable is not
        # proven. Handled as a defect-free refusal by `_nonvacuity`, not here.
        return
    if traced["fsync_count_for_wal"] < 1:
        defects.append(
            (
                _SITE_FSYNC,
                (
                    f"strace saw {traced['trace_lines']} traced line(s) and NOT ONE "
                    f"fsync/fdatasync against {traced['path']}. A WAL is durable only "
                    "if it fsyncs; a write that returned is a write the page cache "
                    f"accepted (strace rc={traced['returncode']}, "
                    f"stderr={traced['stderr'][:120]!r})"
                ),
            )
        )
        return
    if control["fsync_count_for_wal"] != 0:
        defects.append(
            (
                _SITE_FSYNC,
                (
                    f"THE CONTROL FAILED: with sync_to_disk withheld, strace still "
                    f"reported {control['fsync_count_for_wal']} fsync line(s) for "
                    f"{control['path']} — this arm cannot discriminate, so its green "
                    "would be about a matcher that matches anything"
                ),
            )
        )
        return
    ev.append(
        f"FSYNC OBSERVED: {traced['fsync_lines_for_wal'][0].strip()} "
        f"(control with sync withheld: {control['fsync_count_for_wal']} line(s) "
        f"in {control['trace_lines']} traced)"
    )


def _arm_crash(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 2: a process that REALLY died, and what a restart can read back."""
    crash = result["crash"]
    clean = result["clean"]
    expected = -int(crash["signal_number"])
    if crash["reap_status"] != expected:
        defects.append(
            (
                _SITE_KILL,
                (
                    f"pid {crash['pid']} was sent {crash['signal']} "
                    f"({crash['signal_number']}) and reaped with status "
                    f"{crash['reap_status']}, not {expected} — the process did not die "
                    "of the signal this drill sent it, so nothing here is a crash test"
                ),
            )
        )
        return
    if clean["reap_status"] != 0:
        defects.append(
            (
                _SITE_KILL,
                (
                    f"THE CONTROL FAILED: the clean-exit child reaped "
                    f"{clean['reap_status']}, not 0 — if the control also dies, "
                    "'it died' discriminates nothing"
                ),
            )
        )
        return
    if crash["durable_prefix_rows"] < MIN_DURABLE_ROWS:
        defects.append(
            (
                _SITE_RECOVER,
                (
                    f"after the kill, only {crash['durable_prefix_rows']} row(s) were "
                    f"in the WAL's durable prefix, below the floor of "
                    f"{MIN_DURABLE_ROWS} — 'nothing was lost' would be a statement "
                    "about an empty set"
                ),
            )
        )
        return
    ev.append(
        f"CRASH: pid {crash['pid']} SIGKILL reaped {crash['reap_status']} in "
        f"{crash['reap_latency_s'] * 1000:.1f} ms; control reaped "
        f"{clean['reap_status']}; durable prefix {crash['durable_prefix_rows']} "
        f"row(s) vs {crash['recovered_rows']} readable — THE GAP IS THE POINT: "
        "the page cache survives a SIGKILL, so this arm measures the crash gap "
        "and says nothing about a power cut (ARM 1 does)"
    )


def _arm_torn(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 3: the recovery reader shown real damage from a real death."""
    torn = result["crash_torn"]
    if torn["torn_tail_bytes"] < MIN_TORN_TAIL_BYTES:
        defects.append(
            (
                _SITE_RECOVER,
                (
                    f"the torn-tail arm left {torn['torn_tail_bytes']} torn byte(s) on "
                    "disk — the recovery reader was never shown damage, so its "
                    "tolerance of damage is untested"
                ),
            )
        )
        return
    if torn["durable_prefix_rows"] < MIN_DURABLE_ROWS or torn["corrupt_records"]:
        defects.append(
            (
                _SITE_RECOVER,
                (
                    f"a {torn['torn_tail_bytes']}-byte torn tail cost the reader "
                    f"{torn['durable_prefix_rows']} durable row(s) and "
                    f"{torn['corrupt_records']} corrupt record(s) — §9 heals the crash "
                    "gap by reconciliation, which needs the intact rows to survive the "
                    "damaged one"
                ),
            )
        )
        return
    ev.append(
        f"TORN TAIL: {torn['torn_tail_bytes']} byte(s) of a half-written record "
        f"survived pid {torn['pid']}'s SIGKILL; recover() returned "
        f"{torn['durable_prefix_rows']} durable row(s), 0 corrupt, and did not raise"
    )


def _arm_disk_critical(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 4: the KERNEL refuses the append. §12.4's halting branch."""
    critical = result["critical"]
    if critical["state"] != "disk_critical" or not critical["refusal"]:
        defects.append(
            (
                _SITE_ADMIT,
                (
                    f"the WAL accepted {critical['accepted']} row(s) under RLIMIT_FSIZE "
                    f"and reported state {critical['state']!r} with refusal "
                    f"{critical['refusal']!r} — a filesystem that said EFBIG did not "
                    "reach §12.4's disk-critical branch"
                ),
            )
        )
        return
    if (
        critical["admits_new_entries"]
        or "disk-critical" not in critical["admit_reason"]
    ):
        defects.append(
            (
                _SITE_ADMIT,
                (
                    f"DISK-CRITICAL still admits new entries: "
                    f"{(critical['admits_new_entries'], critical['admit_reason'])!r} — "
                    "§12.4 HALTs new entries when the WAL cannot append: no audit "
                    "trail, no new risk"
                ),
            )
        )
        return
    if not critical["protective_exit_allowed"]:
        defects.append(
            (
                _SITE_EXIT,
                (
                    f"DISK-CRITICAL also blocked the PROTECTIVE EXIT: "
                    f"{critical['exit_reason']!r} — §12.4 keeps open positions "
                    "protected because stops read memory, not disk. An exit blocked by "
                    "a full disk is the difference between a bad afternoon and an "
                    "unhedged book"
                ),
            )
        )
        return
    ev.append(
        f"DISK-CRITICAL: the kernel refused after {critical['accepted']} row(s) "
        f"({critical['refusal'][-60:]}); entries denied, protective exit permitted"
    )


def _arm_degraded(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 5: §12.4's DISTINCTION. Sink down ⇒ buffer and trade on. Not a halt."""
    outage = result["outage"]
    degraded = outage["degraded"]
    if degraded["state"] != outage["expected_state"] or not degraded["error"]:
        defects.append(
            (
                _SITE_COMMIT,
                (
                    f"a refusing sink left the WAL in state {degraded['state']!r} with "
                    f"error {degraded['error']!r}, not {outage['expected_state']!r}"
                ),
            )
        )
        return
    if degraded["backlog"] < MIN_BACKLOG:
        defects.append(
            (
                _SITE_COMMIT,
                (
                    f"the sink outage produced a backlog of {degraded['backlog']} — "
                    "§12.4 says the WAL BUFFERS through a Postgres outage, and an "
                    "empty backlog means nothing was buffered"
                ),
            )
        )
        return
    if not outage["admits_new_entries"] or not outage["accepted_during_outage"]:
        defects.append(
            (
                _SITE_ADMIT,
                (
                    f"the WAL refused new entries during a SINK outage: "
                    f"{(outage['admits_new_entries'], outage['admit_reason'])!r}, "
                    f"{outage['accepted_during_outage']} accepted — §12.4's whole "
                    "sentence is 'degraded persistence ≠ degraded trading', and "
                    "halting here turns a Postgres restart into a stopped business"
                ),
            )
        )
        return
    if not any(event == "wal_sink_degraded" for event, _ in outage["alerts"]):
        defects.append(
            (
                _SITE_COMMIT,
                (
                    f"no operator alert fired for the sink outage; alerts were "
                    f"{[e for e, _ in outage['alerts']]!r} — §12.4 requires the "
                    "operator be alerted, and silent buffering is how a backlog "
                    "becomes a surprise"
                ),
            )
        )
        return
    if outage["restored"]["backlog"] or outage["restored"]["state"] != "healthy":
        defects.append(
            (
                _SITE_COMMIT,
                (
                    f"after the sink returned, backlog {outage['restored']['backlog']} "
                    f"remained in state {outage['restored']['state']!r} — the buffered "
                    "rows must reach the sink, or the WAL is a shredder with a delay"
                ),
            )
        )
        return
    ev.append(
        f"§12.4 DISTINCTION HELD: sink down ⇒ state {degraded['state']}, backlog "
        f"{degraded['backlog']}, entries ADMITTED, alert "
        f"{[e for e, _ in outage['alerts']]}; sink back ⇒ "
        f"{outage['restored']['committed']} row(s) committed, backlog 0. Disk "
        "critical ⇒ entries DENIED. Two failures, two answers"
    )


# ---------------------------------------------------------------------------


def _remove_tree(root: Path) -> None:
    """Absolute-path unlinks, never `shutil.rmtree` — see the RESOURCES note."""
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


def _nonvacuity(result: dict[str, Any], evidence: list[str]) -> CheckResult | None:
    """Every floor, checked BEFORE any arm contributes a verdict."""
    if shutil.which("strace") is None or not result["fsync"]["available"]:
        return _cannot(
            "strace is not available, so the fsync SYSCALL cannot be observed. "
            f"{result['fsync'].get('reason', '')} §17: a safety property proven "
            "while its subject is unobservable is not proven — CANNOT_MEASURE, "
            "deliberately never PASS",
            evidence,
        )
    if result["crash"]["signal_number"] != int(signal.SIGKILL):
        return _cannot(
            f"the drill reported signal {result['crash']['signal_number']}, not "
            f"SIGKILL ({int(signal.SIGKILL)}) — the kill this gate is about was "
            "not the kill that was sent",
            evidence,
        )
    rows = result["crash"]["recovered_rows"]
    if rows < MIN_DURABLE_ROWS:
        return _cannot(
            f"only {rows} row(s) were readable from the crashed WAL, below the "
            f"floor of {MIN_DURABLE_ROWS} — the child barely ran, and a durability "
            "verdict over an empty file is deliberately never PASS",
            evidence,
        )
    evidence.append(
        f"nonce {result['nonce']}; strace at {result['fsync']['strace']}; the drill "
        f"spawned {len([k for k in result if isinstance(result[k], dict)])} arms and "
        f"wrote {result['crash']['bytes_on_disk']} byte(s) of real WAL"
    )
    return None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Trace the fsync, kill the child, starve the disk. Never repairs."""
    evidence: list[str] = []
    drill, complaint = _import_drill()
    if complaint:
        return _cannot(complaint, evidence)
    root = Path(tempfile.mkdtemp(prefix="nixwal-"))
    try:
        result = drill.run_drill(root)
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-except
        return _cannot(f"the WAL drill could not be run: {exc!r}", evidence)
    finally:
        _remove_tree(root)

    refusal = _nonvacuity(result, evidence)
    if refusal is not None:
        return refusal

    defects: list[tuple[str, str]] = []
    _arm_fsync(result, defects, evidence)
    _arm_crash(result, defects, evidence)
    _arm_torn(result, defects, evidence)
    _arm_disk_critical(result, defects, evidence)
    _arm_degraded(result, defects, evidence)
    return result_from_defects(NAME, defects, "; ".join(evidence))


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
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
