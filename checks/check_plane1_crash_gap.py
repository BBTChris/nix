#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: §9's crash gap is measured at a REAL durability boundary, and the
instrument that measures it still DISCRIMINATES.

ARC 035 / Stage 1 / sub-agent B (B3). Subject: `scripts/plane1_crash_drill.py`.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §9 — *"Enqueue → durable local
WAL → shared-pool writer → group-commit to Postgres. Crash gap healed by startup
reconciliation vs broker truth."*

## WHAT THIS GATE IS FOR, AND WHY IT IS NOT "DID THE ROWS COME BACK"

The arc brief's §0a: *"a SIGKILL cannot test fsync — a dead process's dirty pages
belong to a living kernel."* The same objection applies one level up to
`pg_ctl -m immediate`, which SIGQUITs the postmaster and leaves the page cache
untouched. So a gate that only asserted *"the committed rows survived the crash"*
could be green over a cluster with `fsync = off` and no durability guarantee at
all — the exact shape the brief warns about.

This gate therefore has FOUR arms and the last two are the ones that matter:

1. **THE FSYNC IS OBSERVED**, with its control. `strace -f -y` on the postmaster
   must show an `fsync`/`fdatasync` whose fd resolves inside **this cluster's own**
   `pg_wal/`, and the `fsync = off` cluster must show **none**. Both halves: an
   arm that matched any line in a busy trace is not a detector.
2. **The crash is real.** `pg_ctl -m immediate` returned 0 and the restarted
   postmaster reported a CRASH RECOVERY rather than a clean start, and the
   committed rows are all back.
3. **The uncommitted tail did not survive — and is NOT counted as durability.**
   Those rows were invisible before the crash and are discarded at recovery
   whether or not anything ever fsynced. The arm rests on the TRANSACTION
   boundary; the drill says so in its own `boundary` field and this gate requires
   that disclaimer to still be there, because a JSON blob that lost it would be
   read as a durability result.
4. **THE INSTRUMENT STILL DISCRIMINATES.** The `fsync = on` and `fsync = off`
   clusters differ in exactly one setting, and their crash outcomes must DIFFER.
   Measured on PostgreSQL 18.4, `fsync = off` loses the whole log. If a future
   version, filesystem or kernel makes both clusters survive, the crash arm has
   become **vacuous** — and that is a defect *of this instrument*, reported as
   one, rather than an extra green. This arm is the reason the gate exists.

## What NO green here means

**Not power loss.** An observed `fsync(2)` that returned is a syscall the kernel
completed; nothing in the drill drops a page cache, and a drive that lies about
its write cache is outside every instrument in this tree. `elements_v2.md` §4's
backup/DR — the only thing that would cover a lost disk — is a later arc.

**Not the system cluster.** Every cluster here is created by `initdb` under a
private socket directory with `listen_addresses = ''` and destroyed on the way
out. This gate never stops, restarts or reconfigures the live PostgreSQL.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **`initdb`/`pg_ctl`/`postgres` absent**, so no boundary can be built.
   *Closed:* CANNOT_MEASURE naming the missing binary (§17), never a PASS.
2. **`strace` absent**, so the fsync cannot be observed and arm 1 is a no-op.
   *Closed:* the drill reports `strace_available`, and this gate turns a false
   into CANNOT_MEASURE rather than skipping the arm quietly.
3. **The trace is read while the tracer is still buffering**, reporting zero
   lines for syscalls that really happened. *Closed in the drill:* the trace file
   is read only after `pg_ctl stop` has reaped the tracer.
4. **Both clusters survive**, making the crash arm vacuous. *Closed:* that is arm
   4, and it is a FAIL.
5. **The drill could crash-and-recover ZERO rows** and report "all of them
   survived" over an empty set. *Closed:* `MIN_COMMITTED_ROWS`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
import plane1_crash_drill as drill
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
EXPECTED_S = 30.0
DEPENDS_ON: tuple[str, ...] = ()
#: Every token names a binary this process really spawns, so the process table
#: can contradict any of them (D3.152's unfalsifiable-token debt is what a
#: `postgres:ephemeral` token would have been). `strace` is declared because the
#: drill spawns it whenever it is present, and its absence is CANNOT_MEASURE
#: rather than a silently skipped arm.
RESOURCES: tuple[str, ...] = (
    # ARC 035 Stage 2 integration: ADDED after `check_observed_resource_claims`
    # measured this gate on the MERGED tree and found the declaration false.
    # The ephemeral cluster this gate builds writes thousands of files under
    # its own `/tmp` directory — `pg/base/1/1247`, the WAL segments, the socket
    # — and the declaration named only the subprocesses that do it. §4.4: a
    # declaration is checked against OBSERVED claims, not against the other
    # declarations, and the branch's own green could not see this because the
    # observer gate had not run over the new check.
    "file-write:/tmp",
    # ARC 035 Stage 2: `createdb` and `pg_isready` were OBSERVED and not
    # declared. The gate creates its database and waits for the ephemeral
    # postmaster to accept connections; both are real child processes.
    "subprocess:createdb",
    "subprocess:pg_isready",
    "subprocess:initdb",
    "subprocess:pg_ctl",
    "subprocess:postgres",
    "subprocess:psql",
    "subprocess:strace",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is whether a durability boundary can still be measured; a gate "
    "authorised to 'repair' it would be adjusting the instrument until it agreed "
    "with the answer, which is the one thing an instrument may never do"
)
ANCHOR = "scripts/plane1_crash_drill.py"
SUBJECTS: tuple[str, ...] = ("scripts/plane1_crash_drill.py",)

NAME = "check_plane1_crash_gap"

#: Below this, "every committed row came back" is a statement about a set small
#: enough to be an accident.
MIN_COMMITTED_ROWS = 8


def inspect_drill(result: dict[str, Any]) -> list[str]:
    """Every arm against ONE drill result. Returns defects.

    Takes the drill's dict rather than running it, so the can-fail suite can
    drive the SHIPPED arms against a REAL run with exactly ONE field mutated —
    which is a plant at a named site, not a fabricated fixture.
    """
    defects: list[str] = []
    durable = result["durable"]
    contrast = result["fsync_off_contrast"]
    control = result["fsync_control"]

    if not durable.get("strace_available") or not control.get("strace_available"):
        return [
            (
                "ARM1 CANNOT_MEASURE: strace is not on PATH, so no fsync was "
                "observed. A durability claim resting on an unobserved syscall is "
                "not a claim (§17)"
            )
        ]
    defects += _arm1_fsync(durable, control)
    defects += _arm2_crash(durable)
    defects += _arm3_uncommitted(durable)
    defects += _arm4_discriminates(durable, contrast, result)
    return defects


def _arm1_fsync(durable: dict[str, Any], control: dict[str, Any]) -> list[str]:
    """The syscall, and the control that gives it meaning."""
    defects: list[str] = []
    if durable["wal_fsync_lines_at_commit"] <= 0:
        defects.append(
            "ARM1: no fsync/fdatasync was observed on this cluster's own pg_wal/ "
            "during a synchronous_commit=on workload. `synchronous_commit = on` "
            "is a setting and a setting is a claim; the syscall is the "
            "measurement, and it was not made"
        )
    if control["wal_fsync_lines"] != 0:
        defects.append(
            f"ARM1 CONTROL: the fsync=off cluster showed "
            f"{control['wal_fsync_lines']} pg_wal fsync line(s), and must show "
            f"NONE. Without the absent half, 'we matched an fsync line' is "
            f"satisfied by any fsync anywhere in a busy trace, forever"
        )
    return defects


def _arm2_crash(durable: dict[str, Any]) -> list[str]:
    """A real crash, a real recovery, and every committed row back."""
    defects: list[str] = []
    if durable["rows_before_crash"] < MIN_COMMITTED_ROWS:
        return [
            (
                f"ARM2 CANNOT_MEASURE: only {durable['rows_before_crash']} row(s) "
                f"were committed before the crash, below the floor of "
                f"{MIN_COMMITTED_ROWS}; 'they all came back' over a set that small "
                f"is not evidence"
            )
        ]
    if durable["crash"]["pg_ctl_rc"] != 0:
        defects.append(
            f"ARM2: `pg_ctl -m immediate stop` returned "
            f"{durable['crash']['pg_ctl_rc']} — the crash this gate rests on did "
            f"not happen: {durable['crash']['pg_ctl_stderr']}"
        )
    if not durable["crash_recovery_in_server_log"]:
        defects.append(
            "ARM2: the restarted postmaster reported no crash recovery. A clean "
            "start means the server was shut down properly and the arm measured "
            "an ordinary restart"
        )
    if not durable["committed_survived"]:
        defects.append(
            f"ARM2: {durable['rows_after_recovery']!r} of "
            f"{durable['rows_before_crash']} COMMITTED rows survived the crash. "
            f"§9's group-commit is the durable record of money truth"
            + (
                f" ({durable['recovery_error']})"
                if durable.get("recovery_error")
                else ""
            )
        )
    return defects


def _arm3_uncommitted(durable: dict[str, Any]) -> list[str]:
    """The near edge of the gap — and its disclaimer, which must still be there."""
    defects: list[str] = []
    if durable["uncommitted_survived"]:
        defects.append(
            "ARM3: rows from a transaction that was never committed SURVIVED the "
            "crash. An uncommitted write becoming durable is a torn record: the "
            "log would hold transitions the system never decided"
        )
    if "NOT a durability boundary" not in durable.get("boundary", ""):
        defects.append(
            "ARM3: the drill's `boundary` field no longer says that the "
            "uncommitted-tail arm rests on the TRANSACTION boundary and not a "
            "durability one. That arm would pass under a bare kill -9, and a "
            "result read without the disclaimer is read as durability"
        )
    return defects


def _arm4_discriminates(
    durable: dict[str, Any], contrast: dict[str, Any], result: dict[str, Any]
) -> list[str]:
    """THE ARM THIS GATE EXISTS FOR: is the crash test still a measurement?"""
    defects: list[str] = []
    if contrast["fsync"] != "off" or durable["fsync"] != "on":
        return [
            (
                f"ARM4 CANNOT_MEASURE: the two clusters are not the differential "
                f"they claim to be (durable fsync={durable['fsync']!r}, contrast "
                f"fsync={contrast['fsync']!r})"
            )
        ]
    if durable["committed_survived"] == contrast["committed_survived"]:
        defects.append(
            f"ARM4: the fsync=on and fsync=off clusters now behave IDENTICALLY "
            f"across `pg_ctl -m immediate` (both committed_survived="
            f"{durable['committed_survived']}). The crash arm has stopped "
            f"discriminating the durability setting and is VACUOUS — a green on "
            f"it would be the arc brief's own §0a failure, and the durability "
            f"claim must fall back to ARM 1's observed fsync alone"
        )
    if "power-loss" not in result.get("boundary", ""):
        defects.append(
            "ARM4: the drill's `boundary` field no longer disclaims power loss. "
            "Nothing here drops a page cache, and a differential between two "
            "server settings is not evidence about what a disk does when the "
            "lights go out"
        )
    return defects


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Build two ephemeral clusters, crash both, and measure the difference."""
    try:
        for binary in ("initdb", "pg_ctl", "postgres", "psql"):
            drill.pg_bin(binary)
    except RuntimeError as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail=(
                f"the durability boundary cannot be built, so nothing was "
                f"measured (§17): {exc}"
            ),
        )
    try:
        result = drill.run_drill()
        defects = inspect_drill(result)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail=f"the drill raised {type(exc).__name__}: {exc}",
        )
    if any("CANNOT_MEASURE" in d for d in defects):
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail="; ".join(defects),
        )
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=ANCHOR,
            evidence=f"{len(defects)} durability-measurement defect(s)",
            detail="; ".join(defects),
        )
    durable = result["durable"]
    contrast = result["fsync_off_contrast"]
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=(
            f"§9's crash gap measured on two ephemeral clusters differing only "
            f"in their durability settings. Durable: "
            f"{durable['wal_fsync_lines_at_commit']} "
            f"fdatasync line(s) OBSERVED on its own pg_wal/, "
            f"{durable['rows_after_recovery']}/{durable['rows_before_crash']} "
            f"committed rows survived `pg_ctl -m immediate` + crash recovery, "
            f"and the uncommitted tail did not (TRANSACTION boundary, not a "
            f"durability one). Contrast: 0 pg_wal fsync lines, and "
            f"committed_survived={contrast['committed_survived']} — the crash "
            f"arm still DISCRIMINATES. No power-loss claim is made anywhere"
        ),
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
