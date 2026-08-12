#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check
# must declare the same symbols and must be independently runnable, so the
# blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter. Same pragma, same
# reason, as `scripts/nixverify/actuation.py` line 1.
"""Gate: §10's core map holds as RUNNING STATE for a real `capture.py` process.

Subject: `scripts/nixbus/core_map.py`, `scripts/capture.py`'s pin, and the
kernel's own answer for a live PID.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §10 (Process/Core Map,
locked); `docs/nix_check_contract.md` §4-§5; `docs/VERIFY-AND-CHECKS.md` Part C.
Discharges `docs/CHECK-DEBT.md` **D1.2** (*`nix-trading.slice` core pinning,
ARC 006, unassigned*) and the affinity half of **D1.3** (*"nothing reads the
running system"*).

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

The arc brief names this gate's failure mode by name: *"a core-affinity gate that
reads configuration rather than the running process's actual affinity mask"*.
Six answers, each an arm rather than a paragraph:

1. **It reads the unit file, or a JSON config, and calls that "affinity".**
   `AllowedCPUs=0-5` in `/etc/systemd/system/nix-trading.slice` is a *statement of
   intent* that costs nothing to be wrong about; `systemctl show` reports
   systemd's parse of that same statement, not the kernel's enforcement of it.
   *Closed by arm 1:* this gate reads `sched_getaffinity(pid)` and
   `/proc/<pid>/status:Cpus_allowed_list` **for a PID it spawned and can name**.
   No configuration file is read anywhere in this module — there is not one to
   read, because §10 is the map's only source and it is a spec, not a setting.
2. **It measures ITSELF.** A gate that pins its own process and then reads its
   own mask is an instrument reporting on a state it just wrote
   (`nix_check_contract.md` §4.3). *Closed:* the subject is a **separate
   process**, spawned from `scripts/capture.py`, and the measurement is taken by
   the parent through `/proc` while the child holds.
3. **The mask it reads happens to be the answer for every process on the box.**
   If this node were a one-CPU machine, or if some global policy already confined
   everything to core 1, arm 1 would pass without `capture.py` having done
   anything. *Closed by arm 2, the CONTROL:* the same program is spawned a second
   time with `--no-pin`, and its mask MUST differ. If the control's mask also
   reads `1`, the reading carries no information and this gate returns
   CANNOT_MEASURE rather than a PASS it did not earn.
4. **It proves affinity and quietly implies ISOLATION.** §10's Notes column says
   *"isolcpus/nohz_full/IRQ affinity for the rest"* and *"isolated, elevated"*.
   Affinity is inclusion: it says `capture.py` MAY use core 1, never that nothing
   else may. *Closed by arm 4*, which reads `/proc/cmdline` and states in the
   verdict's own evidence that isolation is NOT in effect on this node. The gate
   is not permitted to be silent about the half of §10 it cannot prove.
5. **It never looks at the slice at all.** *Closed by arm 3*, which reads the
   cgroup-v2 `cpuset.cpus.effective` the kernel enforces — not `systemctl show`.
6. **The child fails to start and "nothing was wrong".** A spawn that raised, or
   a child that printed nothing, would leave the arms with no defect to report.
   *Closed:* every failure to obtain a live PID is CANNOT_MEASURE naming the
   cause, and a PASS is impossible without a parsed PID that `/proc` answered for.

## Why the subject is `capture.py` and not a helper

`capture.py --self-report` runs `nixbus.core_map.pin_self(Role.CAPTURE)` — the
same call the real process makes on the same line of the same file. A purpose-
built helper that pinned itself would prove a helper can be pinned.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess  # nosec B404 - re-executes capture.py, argv built here, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixbus.core_map import (
    SPEC_ASSIGNED,
    SPEC_CORES,
    TRADING_SLICE,
    TRADING_SLICE_CPUSET,
    AffinityReading,
    Role,
    effective_affinity,
    format_cpu_list,
    isolated_cores,
    off_map_cores,
    slice_cpuset,
)
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `capture.py` imports `nixbus.statebus`, which imports `pyzmq` — a pin in
#: `checks/pinned_deps.json`, so the child needs the venv to start at all. The
#: edge is declared rather than left to luck: `verify.py` itself runs under
#: `/usr/bin/python3` (see `nix-verify.service`), so "the interpreter running me
#: has zmq" is not something this gate may assume about the interpreter it
#: SPAWNS.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Two claims, both real:
#: * `subprocess:python3` — this gate spawns the venv interpreter twice
#:   (measured arm and control arm). OBSERVABLE by
#:   `check_observed_resource_claims` as `subprocess:.../python3`.
#: * `cpu-affinity` — the child mutates its own scheduler affinity. NOT in the
#:   observer's vocabulary (audit hooks do not cover `sched_setaffinity`, and it
#:   happens in the CHILD, which the observer does not follow either), so it is
#:   declared for the PLAN's benefit: any future check that pins a process must
#:   collide with this one rather than race it. Over-declaring costs parallelism;
#:   under-declaring costs correctness (ARC 025's headline finding).
RESOURCES: tuple[str, ...] = ("subprocess:python3", "cpu-affinity")
TIME_BOUND = True
#: Two child spawns, each holding for HOLD_S, plus interpreter startup.
EXPECTED_S = 4.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the map is §10, which is frozen spec, and the pin is applied by the process "
    "at its own start — 'correcting' affinity from here would mean this gate "
    "reaching into another process's scheduler state, which is a mutation of the "
    "thing under measurement and would leave no independent verifier"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixbus/core_map.py",
    "scripts/capture.py",
)

NAME = "check_core_map"

#: How long the spawned child holds after reporting, so `/proc/<pid>` exists to
#: be read. Bounded: a child that outlived this would make the gate's runtime a
#: function of the child's patience.
HOLD_S = 0.5
SPAWN_TIMEOUT_S = 20.0


@dataclasses.dataclass
class _Child:
    """A spawned `capture.py --self-report`, its PID, and the parent's reading."""

    pid: int = 0
    self_report: dict[str, object] = dataclasses.field(default_factory=dict)
    reading: AffinityReading | None = None
    proc: subprocess.Popen[str] | None = None
    error: str = ""


def _venv_python(nix_home: Path) -> Path:
    """The interpreter `capture.py` must run under. Never `sys.executable`."""
    return nix_home / ".venv" / "bin" / "python3"


def _spawn(nix_home: Path, *, pin: bool) -> _Child:
    """Start `capture.py --self-report`, read its PID line, leave it holding."""
    argv = [
        str(_venv_python(nix_home)),
        str(nix_home / "scripts" / "capture.py"),
        "--self-report",
        "--hold-s",
        str(HOLD_S),
    ]
    if not pin:
        argv.append("--no-pin")
    try:
        # pylint: disable=consider-using-with
        # A `with` block would reap the child at the end of THIS function, and
        # the whole measurement happens afterwards: the parent reads
        # `/proc/<pid>/status` for a process that must still be alive. The
        # lifetime is deliberately longer than the call, and `_measure` owns the
        # wait/kill in every path.
        proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except (OSError, ValueError) as exc:
        return _Child(error=f"could not spawn {argv[1]}: {exc!r}")
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=SPAWN_TIMEOUT_S)
        return _Child(error=f"{argv[1]} --self-report printed nothing")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        proc.kill()
        proc.wait(timeout=SPAWN_TIMEOUT_S)
        return _Child(error=f"self-report is not JSON: {exc!r} ({line[:120]!r})")
    return _Child(pid=int(payload.get("pid", 0)), self_report=payload, proc=proc)


def _measure(child: _Child) -> _Child:
    """Read the child's mask from the PARENT while it holds, then reap it."""
    if child.error or not child.pid:
        return child
    child.reading = effective_affinity(child.pid)
    proc = child.proc
    if proc is not None:
        try:
            proc.wait(timeout=SPAWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=SPAWN_TIMEOUT_S)
    return child


def _run_child(nix_home: Path, *, pin: bool) -> _Child:
    """Spawn, measure from `/proc`, reap. The whole measurement, in order."""
    return _measure(_spawn(nix_home, pin=pin))


def _arm1_pinned(child: _Child, defects: list[tuple[str, str]], ev: list[str]) -> None:
    """The real process's real mask is exactly §10's Core 1 set."""
    site = "scripts/capture.py:pin_self(Role.CAPTURE)"
    reading = child.reading
    if reading is None or reading.error:
        return
    ev.append(f"MEASURED {reading.describe()}")
    wanted = SPEC_ASSIGNED[Role.CAPTURE]
    if not reading.agree:
        defects.append(
            (
                f"/proc/{reading.pid}/status",
                (
                    f"the two kernel readers disagree — sched_getaffinity="
                    f"{format_cpu_list(reading.syscall)} but Cpus_allowed_list="
                    f"{format_cpu_list(reading.procfs)}"
                ),
            )
        )
        return
    if reading.mask != wanted:
        defects.append(
            (
                site,
                (
                    f"pid {reading.pid} runs with Cpus_allowed_list="
                    f"{format_cpu_list(reading.mask)}, but §10 assigns capture.py "
                    f"core {format_cpu_list(wanted)} — this is the kernel's mask "
                    "for the live process, not a config reading"
                ),
            )
        )
        return
    stray = off_map_cores(reading.mask)
    if stray:
        defects.append(
            (site, f"pid {reading.pid} may use {format_cpu_list(stray)}, off §10's map")
        )


def _arm2_control(
    pinned: _Child, control: _Child, defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """CONTROL — an unpinned run of the SAME program must read differently.

    This is what makes arm 1 falsifiable. If the box confined every process to
    core 1 by some policy this gate cannot see, arm 1 would pass having measured
    the box rather than `capture.py`.
    """
    site = "scripts/capture.py --no-pin CONTROL"
    if control.error or control.reading is None or control.reading.error:
        return
    ev.append(f"CONTROL {control.reading.describe()}")
    if pinned.reading is None or pinned.reading.error:
        return
    if control.reading.mask == pinned.reading.mask:
        defects.append(
            (
                site,
                (
                    f"an UNPINNED capture.py reads the same mask "
                    f"{format_cpu_list(control.reading.mask)} as the pinned one — "
                    "the reading cannot distinguish a pinned process from an "
                    "unpinned one, so arm 1's PASS would carry no information"
                ),
            )
        )


def _arm3_slice(defects: list[tuple[str, str]], ev: list[str]) -> str:
    """The slice's KERNEL-effective cpuset must admit every §10 core."""
    cores, error = slice_cpuset()
    if error:
        return error
    ev.append(f"{TRADING_SLICE} cpuset.cpus.effective={format_cpu_list(cores)}")
    missing = SPEC_CORES - cores
    if missing:
        defects.append(
            (
                str(TRADING_SLICE_CPUSET),
                (
                    f"the slice enforces {format_cpu_list(cores)} but §10 assigns "
                    f"{format_cpu_list(SPEC_CORES)} — cores "
                    f"{format_cpu_list(missing)} are named by the map and denied "
                    "by the cgroup"
                ),
            )
        )
    return ""


def _arm4_isolation(ev: list[str]) -> None:
    """Report §10's isolation column HONESTLY. Never claim it, never omit it."""
    isolated, note = isolated_cores()
    ev.append(
        f"ISOLATION NOT CLAIMED: {note}"
        if note
        else f"kernel isolates {format_cpu_list(isolated)} (isolcpus/nohz_full)"
    )


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure a live `capture.py`'s kernel affinity against §10's locked map."""
    nix_home = Path(ctx.nix_home)
    python = _venv_python(nix_home)
    if not python.is_file():
        return _cannot(f"no venv interpreter at {python} — check_venv owns this", [])

    evidence: list[str] = []
    defects: list[tuple[str, str]] = []
    pinned = _run_child(nix_home, pin=True)
    if pinned.error or pinned.reading is None or pinned.reading.error:
        why = pinned.error or (pinned.reading.error if pinned.reading else "no reading")
        return _cannot(f"could not measure a live capture.py: {why}", evidence)

    control = _run_child(nix_home, pin=False)
    if control.error or control.reading is None or control.reading.error:
        why = control.error or (
            control.reading.error if control.reading else "no reading"
        )
        return _cannot(
            f"the CONTROL arm could not run ({why}) — without it a PASS cannot be "
            "distinguished from a box that confines everything to core 1",
            evidence,
        )

    _arm1_pinned(pinned, defects, evidence)
    _arm2_control(pinned, control, defects, evidence)
    slice_error = _arm3_slice(defects, evidence)
    _arm4_isolation(evidence)
    if slice_error and not defects:
        return _cannot(
            f"process affinity measured and correct, but {slice_error}", evidence
        )
    if slice_error:
        evidence.append(f"slice UNMEASURED: {slice_error}")
    return result_from_defects(NAME, defects, "; ".join(evidence))


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
