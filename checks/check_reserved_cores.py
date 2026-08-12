#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4).
"""Gate: the cores §10 assigns to NOTHING stay unassigned. D1.44's instrument.

Subject: `scripts/nixbus/core_map.py`'s reservation readers, and the live process
table of this node.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §10 (Process/Core Map,
**locked** — the table assigns cores 0-5 and stops);
`docs/CHECK-DEBT.md` **D1.44**, on which the architect has now ruled: the surplus
cores are **reserved and unassigned**, to be kept empty of Nix processes, and are
explicitly **NOT more shared pool** — §10's pool is cores 4-5 and stays cores 4-5.

## §0b — WHAT WAS ASKED, WHAT IS ENFORCED, AND THE MEASUREMENT BEHIND THE GAP

The ruling's spelling is *"gate that they stay empty of Nix processes"*. Taken
literally — *no Nix process's task may last run on a reserved core* — this gate
would be red on this node right now, and would be red because of its own runner.

**MEASURED, 2026-08-12, on this node:** nothing on the box is pinned at all.
`nix-trading.slice`'s `cgroup.procs` is EMPTY (D1.42 — the slice exists and no
unit has ever joined it), so every Nix process runs at the box default mask
`0-19` and the scheduler places it wherever it likes, including cores 6-19. That
population includes `verify.py` itself, this gate, and every `pytest` worker. A
gate that failed on them would be reporting the presence of its own instrument,
would be red on every run regardless of the subject, and would become furniture
inside one arc.

So the enforced rule is the one the ruling is actually about — **no Nix process
may be ASSIGNED to a reserved core** — and it is enforced over the population an
assignment can exist in:

| rule | population | verdict |
|---|---|---|
| mask must not touch a reserved core | processes whose mask was NARROWED (pinned) | FAIL |
| mask must not touch a reserved core | `nix-trading.slice` members | FAIL |
| cpuset must not admit a reserved core | the slice itself, kernel-effective | FAIL |
| §10's shared pool is exactly `{4, 5}` | `core_map.SPEC_ASSIGNED` | FAIL |
| where unpinned Nix tasks LAST RAN | everything else | **REPORTED, counted** |

The last row is the substitution, and it is reported rather than dropped: the
verdict's evidence carries how many Nix processes are drift-capable and how many
of them were observed ON a reserved core at the sampling instant.
`docs/CHECK-DEBT.md` **D1.46** owns closing it, and it closes by PINNING things
(the slice acquiring members, D1.42), not by changing this gate.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **It enumerates zero Nix processes and concludes the cores are empty.** The
   failure the architect named. *Closed twice.* (a) **Credibility floor:** the
   enumerator must find THIS PROCESS's own PID, and a census that cannot see its
   own author is CANNOT_MEASURE. (b) **Non-vacuity plant:** a real Nix process is
   spawned pinned to a reserved core and the enumerator must find it AND classify
   it as a violation, naming its PID — then it is reaped and the same population
   must come back clean. A gate that only ever saw a clean tree would never have
   shown that it could see anything.
2. **There is nothing to reserve.** On the 6-core QuantVPS box §10's table is the
   whole machine and `reserved_cores()` is empty. *Closed:* an empty reserved set
   is CANNOT_MEASURE naming the box, never a PASS.
3. **It reads a config file that says `AllowedCPUs=0-5`.** *Closed:* no
   configuration is read. Masks come from `sched_getaffinity(2)` and
   `/proc/<pid>/status`, occupancy from `/proc/<pid>/stat` field 39, the cpuset
   from the cgroup's own `cpuset.cpus.effective`, and the online set from sysfs.
4. **The reserved set is derived from something that could quietly include the
   pool.** *Closed by arm 4:* `SPEC_ASSIGNED[SHARED_POOL]` must be exactly
   `{4, 5}`. Folding the surplus into the pool would empty the reserved set and
   turn this whole gate off silently; it reddens instead.
5. **The plant is never actually pinned** and arm 0 passes because nothing was
   found to violate anything. *Closed:* the plant's own mask is re-read from the
   kernel for its PID by the parent, and a plant whose mask is not the reserved
   core it asked for is CANNOT_MEASURE.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess  # nosec B404 - spawns the venv interpreter, argv here, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixbus.core_map import (
    SPEC_ASSIGNED,
    TRADING_SLICE,
    TRADING_SLICE_CPUSET,
    ProcessCore,
    Role,
    effective_affinity,
    format_cpu_list,
    nix_processes,
    online_cores,
    reserved_cores,
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
#: The plant runs under `.venv/bin/python3` so that its argv[0] is a path inside
#: `nix_home` — which is what makes it a Nix process by the enumerator's OWN
#: predicate rather than by a special case written for the test.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Two claims:
#: * `subprocess:python3` — the non-vacuity plant. OBSERVABLE by
#:   `check_observed_resource_claims` as `subprocess:.../python3`.
#: * `cpu-affinity` — the plant sets its own scheduler affinity. Outside the
#:   observer's vocabulary (it happens in the CHILD), declared so the plan keeps
#:   this gate away from `check_core_map` and the drill gates rather than racing
#:   them for cores.
RESOURCES: tuple[str, ...] = ("subprocess:python3", "cpu-affinity")
TIME_BOUND = True
#: Three enumerations of `/proc` plus one short-lived child. MEASURED ~1 s.
EXPECTED_S = 4.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a violation here is a process running with the wrong affinity; 'correcting' "
    "it would mean this gate reaching into another process's scheduler state, "
    "which mutates the subject and leaves no independent verifier"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixbus/core_map.py",)

NAME = "check_reserved_cores"

#: How long the planted process holds, so the parent can read `/proc` for it.
PLANT_HOLD_S = 1.0
PLANT_TIMEOUT_S = 20.0

#: The plant, as a `-c` program. It pins itself, prints its kernel-read mask, and
#: holds. The parent measures `/proc/<pid>` independently and never trusts this.
_PLANT = (
    "import os,sys,time\n"
    "core={core}\n"
    "os.sched_setaffinity(0,{{core}})\n"
    "print(sorted(os.sched_getaffinity(os.getpid())),flush=True)\n"
    "time.sleep({hold})\n"
)


@dataclasses.dataclass(frozen=True)
class _Census:
    """One enumeration of the Nix process population, already classified."""

    processes: tuple[ProcessCore, ...]
    slice_error: str
    assigned: tuple[ProcessCore, ...]
    drift_capable: tuple[ProcessCore, ...]
    occupying: tuple[ProcessCore, ...]

    @property
    def pids(self) -> frozenset[int]:
        """Every PID this census saw."""
        return frozenset(process.pid for process in self.processes)


def _census(home: Path, reserved: frozenset[int], online: frozenset[int]) -> _Census:
    """Enumerate and classify. The classification IS the rule — see the docstring."""
    processes, slice_error = nix_processes(home)
    assigned = tuple(
        process
        for process in processes
        if process.reserved_in_mask(reserved)
        and (process.pinned(online) or process.in_slice)
    )
    return _Census(
        processes=processes,
        slice_error=slice_error,
        assigned=assigned,
        drift_capable=tuple(
            process
            for process in processes
            if not process.pinned(online) and process.reserved_in_mask(reserved)
        ),
        occupying=tuple(process for process in processes if process.occupies(reserved)),
    )


def _describe(process: ProcessCore) -> str:
    """One process, both core facts, for a defect or a piece of evidence."""
    return (
        f"pid={process.pid} mask={format_cpu_list(process.mask) or '-'} "
        f"last_cpu={process.cpu} slice={process.in_slice} "
        f"cmd={process.cmdline[:70]!r}"
    )


def _plant(home: Path, core: int) -> tuple[subprocess.Popen[str] | None, str]:
    """Spawn a Nix process pinned to a RESERVED core. Non-vacuity, arm 0."""
    python = home / ".venv" / "bin" / "python3"
    if not python.is_file():
        return None, f"no venv interpreter at {python} — check_venv owns this"
    argv = [str(python), "-c", _PLANT.format(core=core, hold=PLANT_HOLD_S)]
    try:
        # pylint: disable=consider-using-with
        # The child must OUTLIVE this call: the whole measurement is the parent
        # reading `/proc/<pid>` while it holds. `run` owns the reap on every path.
        proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except (OSError, ValueError) as exc:
        return None, f"could not spawn the plant: {exc!r}"
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=PLANT_TIMEOUT_S)
        return None, "the plant printed no mask"
    return proc, ""


def _reap(proc: subprocess.Popen[str]) -> None:
    """Stop the plant. Never leaves a child behind, on any path."""
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=PLANT_TIMEOUT_S)


def _arm0_plant(
    home: Path, reserved: frozenset[int], online: frozenset[int]
) -> tuple[str, str]:
    """NON-VACUITY — plant, prove the enumerator sees it, reap. `(evidence, why)`."""
    core = max(reserved)
    proc, error = _plant(home, core)
    if proc is None:
        return "", f"the non-vacuity plant could not be created: {error}"
    try:
        reading = effective_affinity(proc.pid)
        if not reading.agree or reading.mask != frozenset({core}):
            return "", (
                f"the plant pid={proc.pid} was asked for core {core} and the kernel "
                f"reports {reading.describe()} — a plant that is not where it claims "
                "to be cannot demonstrate that the enumerator finds it"
            )
        census = _census(home, reserved, online)
        found = [process for process in census.assigned if process.pid == proc.pid]
        if not found:
            return "", (
                f"a live Nix process pid={proc.pid} pinned to reserved core {core} "
                f"was NOT reported by the enumerator (it saw {len(census.processes)} "
                "Nix process(es)) — this gate cannot see the violation it exists to "
                "find, so its clean readings carry no information"
            )
        planted = _describe(found[0])
    finally:
        _reap(proc)
    # INDEPENDENT RE-MEASUREMENT after the plant is gone (§4.3): a demonstration
    # that stops at "the gate can fail" has not shown that the same population
    # comes back clean, and a plant that leaked would leave every later run red
    # for a reason belonging to this gate.
    after = _census(home, reserved, online)
    if any(process.pid == proc.pid for process in after.assigned):
        return "", (
            f"the plant pid={proc.pid} was reaped and the enumerator still reports "
            "it as assigned to a reserved core — this gate cannot tell a live "
            "violation from a dead one"
        )
    return (
        f"NON-VACUITY: planted a Nix process on reserved core {core}, the enumerator "
        f"flagged it ({planted}), and after the reap the same population is clean"
    ), ""


def _why_assigned(process: ProcessCore, reserved: frozenset[int]) -> str:
    """Which of the two populations this process violates, and with which cores."""
    stray = format_cpu_list(process.reserved_in_mask(reserved))
    if process.in_slice:
        return (
            f"{_describe(process)} — a {TRADING_SLICE} member holds reserved core(s) "
            f"{stray} in its mask, and §10 assigns them to nothing"
        )
    return (
        f"{_describe(process)} — its mask was NARROWED onto reserved core(s) {stray}; "
        "an unpinned process at the box default is drift, but a narrowed one is an "
        "assignment somebody made"
    )


def _arm1_assigned(
    census: _Census, reserved: frozenset[int], defects: list, ev: list
) -> None:
    """No Nix process is ASSIGNED to a reserved core. THE RULE."""
    site = "sched_getaffinity(2) over the live Nix process population"
    for process in census.assigned:
        defects.append((site, _why_assigned(process, reserved)))
    if not census.assigned:
        ev.append(
            f"ASSIGNMENT: none of {len(census.processes)} Nix process(es) is pinned "
            "onto a reserved core, and no slice member holds one"
        )


def _arm2_slice(reserved: frozenset[int], defects: list, ev: list) -> str:
    """The slice's KERNEL-effective cpuset must admit no reserved core."""
    cores, error = slice_cpuset()
    if error:
        return error
    stray = cores & reserved
    if stray:
        defects.append(
            (
                str(TRADING_SLICE_CPUSET),
                (
                    f"{TRADING_SLICE} enforces {format_cpu_list(cores)}, which "
                    f"includes reserved core(s) {format_cpu_list(stray)} — the cgroup "
                    "would let a member run where §10 assigns nothing"
                ),
            )
        )
        return ""
    ev.append(
        f"{TRADING_SLICE} cpuset.cpus.effective={format_cpu_list(cores)}, disjoint "
        "from the reserved set"
    )
    return ""


def _arm3_pool(reserved: frozenset[int], defects: list, ev: list) -> None:
    """§10's shared pool is cores 4-5. The surplus is NOT more pool."""
    site = "scripts/nixbus/core_map.py:SPEC_ASSIGNED[Role.SHARED_POOL]"
    pool = SPEC_ASSIGNED[Role.SHARED_POOL]
    if pool != frozenset({4, 5}):
        defects.append(
            (
                site,
                (
                    f"§10's shared pool reads {format_cpu_list(pool)}; the locked "
                    "table says cores 4-5. Widening the pool over the surplus would "
                    "empty the reserved set and turn this gate off in silence"
                ),
            )
        )
        return
    ev.append(
        f"POOL: §10's shared pool is {format_cpu_list(pool)} and the reserved set "
        f"{format_cpu_list(reserved)} is disjoint from every assigned core"
    )


def _arm4_report_drift(census: _Census, reserved: frozenset[int], ev: list) -> None:
    """The SUBSTITUTION, reported: who could drift, and who was on a reserved core."""
    ev.append(
        f"DRIFT (reported, not gated — D1.46): {len(census.drift_capable)} of "
        f"{len(census.processes)} Nix process(es) run unpinned at the box default "
        f"and are permitted reserved cores {format_cpu_list(reserved)}; "
        f"{len(census.occupying)} of them were LAST SCHEDULED on a reserved core at "
        "the sampling instant"
        + (
            " (" + "; ".join(_describe(p) for p in census.occupying[:3]) + ")"
            if census.occupying
            else ""
        )
    )


def _cannot(detail: str) -> CheckResult:
    """CANNOT_MEASURE naming the wall. Never a PASS earned by failing to look."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def _population(
    home: Path,
) -> tuple[frozenset[int], frozenset[int], _Census | None, CheckResult | None]:
    """The reserved set and a credible census, or the refusal that stops the gate.

    Split out of `run` so the four ways this gate can decline to answer read as
    one idea rather than as four returns scattered through the verdict path. Each
    is CANNOT_MEASURE naming the wall: an unreadable CPU set, an underivable
    reserved set, a box with no surplus, and a census that cannot see its own
    author.
    """
    online, online_error = online_cores()
    if online_error:
        return (
            frozenset(),
            frozenset(),
            None,
            _cannot(f"cannot read the online CPU set: {online_error}"),
        )
    reserved, reserved_error = reserved_cores()
    if reserved_error:
        return (
            online,
            frozenset(),
            None,
            _cannot(f"cannot derive the reserved set: {reserved_error}"),
        )
    if not reserved:
        return (
            online,
            reserved,
            None,
            _cannot(
                f"this node has {format_cpu_list(online)} online and §10 assigns every "
                "one of them — there is no surplus to reserve here, which is the "
                "6-core QuantVPS case and is not a pass"
            ),
        )
    census = _census(home, reserved, online)
    if os.getpid() not in census.pids:
        return (
            online,
            reserved,
            None,
            _cannot(
                f"the enumerator saw {len(census.processes)} Nix process(es) and this "
                f"process (pid={os.getpid()}) was not among them — a census that cannot "
                "see its own author cannot be believed about anything it did not see"
            ),
        )
    return online, reserved, census, None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the cores §10 assigns to nothing are assigned to nothing."""
    home = Path(ctx.nix_home)
    online, reserved, census, refusal = _population(home)
    if refusal is not None or census is None:
        return refusal if refusal is not None else _cannot("no census was taken")
    plant_evidence, plant_error = _arm0_plant(home, reserved, online)
    if plant_error:
        return _cannot(plant_error)

    header = (
        f"online={format_cpu_list(online)} §10-assigned="
        f"{format_cpu_list(frozenset().union(*SPEC_ASSIGNED.values()))} "
        f"RESERVED-UNASSIGNED={format_cpu_list(reserved)}"
    )
    evidence: list[str] = [header, plant_evidence]
    defects: list[tuple[str, str]] = []
    _arm1_assigned(census, reserved, defects, evidence)
    slice_error = _arm2_slice(reserved, defects, evidence)
    _arm3_pool(reserved, defects, evidence)
    _arm4_report_drift(census, reserved, evidence)
    if census.slice_error:
        evidence.append(f"slice membership UNREADABLE: {census.slice_error}")
    if slice_error and not defects:
        return _cannot(
            f"the process population is clean, but the slice cpuset is unreadable: "
            f"{slice_error}"
        )
    if slice_error:
        evidence.append(f"slice cpuset UNMEASURED: {slice_error}")
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
