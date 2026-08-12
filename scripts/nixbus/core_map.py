"""§10's locked Process/Core Map, expressed as something the kernel can be asked.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §10 (Process / Core Map,
**locked**) and §11 (hot-path discipline). The table is reproduced here as data
because §10 is the single source of truth for it (`CLAUDE.md` directive 3) — no
JSON config restates it, and there is deliberately nothing an operator can edit
that would move a role to a different core without editing the spec.

## THE POINT OF THIS MODULE, stated before the code

A core map is the easiest thing in this project to fake. `AllowedCPUs=0-5` in a
unit file, a `taskset` in a comment, a JSON key called `"core": 1` — every one of
those is a *statement of intent* that reads exactly like a measurement and costs
nothing to be wrong about. ARC 006 installed `nix-trading.slice` and
`docs/CHECK-DEBT.md` D1.2 has carried *"`nix-trading.slice` core pinning
(`AllowedCPUs=0-5`) — unassigned"* ever since, beside D1.3's note that
*"`scripts/tests/test_systemd_units.py` reads the unit **files**; nothing reads
the running system."*

So this module never reports a core assignment it has not read out of the kernel
for a **specific live PID**, and it offers two independent ways of reading it:

| reader | interface | what it is |
|---|---|---|
| `affinity_syscall` | `os.sched_getaffinity(pid)` | the `sched_getaffinity(2)` syscall |
| `affinity_procfs` | `/proc/<pid>/status` `Cpus_allowed_list` | procfs on the
  same task struct |

`effective_affinity` reads **both** and refuses to answer when they disagree.
They come from one kernel and so are not independent *sources* — that is stated
rather than implied, and the value of taking both is that a bug in either
reader's parsing, or a PID that exited between the two reads, becomes visible
instead of becoming the answer.

## What is measured here, and what is NOT — a bound, not a disclaimer

**MEASURED:** which CPUs a running process is *permitted* to run on.

**NOT MEASURED, and no function here should be read as covering it:**

1. **Isolation.** §10's Notes column says *"isolcpus/nohz_full/IRQ affinity for
   the rest"* and *"isolated, elevated"*. MEASURED on this node 2026-08-12:
   `/proc/cmdline` carries **neither `isolcpus` nor `nohz_full`**. Affinity is
   *inclusion* — it says a process may use core 1; it says nothing about who else
   may. `isolated_cores()` reports what the kernel says and reports nothing when
   the kernel says nothing.
2. **Scheduling priority.** §10 says Core 2 is *"highest priority"* and
   `docs/elements_v2.md`:82 names `chrt`/`SCHED_FIFO`. Not implemented, not
   measured here, and `docs/CHECK-DEBT.md` carries the row.
3. **Where a process actually ran.** An affinity mask is a permission. The
   `task_cpu` a thread last executed on is a different fact and is not read.

## Cores 6-19 — the spec's table is smaller than this box

§10 assigns cores 0-5 and stops. This node has **20**. `nix-trading.slice`'s own
`Description=` records the reasoning: *"QuantVPS is 6-core total, so 0-5 there is
the whole box; this dev box has 20, so 0-5 is a real restriction. Same
`AllowedCPUs` value either way — that's the point."*

`SPEC_ASSIGNED` therefore covers `0-5` **exactly**, and cores 6-19 are
`UNASSIGNED_BY_SPEC` — not silently folded into the shared pool. Folding them in
would be this module inventing a spec row, which is the substitution
`docs/SPEC-AMENDMENTS.md` AMENDMENT 3 names. A process pinned to core 7 is
**off-map**, and that is a finding for the architect, not a fact this file gets
to decide.
"""

from __future__ import annotations

import dataclasses
import enum
import os
import re
from collections.abc import Iterable
from pathlib import Path

#: The cgroup-v2 cpuset the trading slice actually enforces. This is the
#: KERNEL's copy, not `systemctl show`'s rendering of the unit file: systemd
#: reports `AllowedCPUs=` from its own parsed configuration whether or not it
#: ever reached a cgroup, and the whole subject of this module is the difference
#: between those two sentences. The `nix.slice` parent comes from systemd's
#: dash-hierarchy naming and is not a file anywhere.
TRADING_SLICE = "nix-trading.slice"
TRADING_SLICE_CPUSET = Path(
    "/sys/fs/cgroup/nix.slice/nix-trading.slice/cpuset.cpus.effective"
)

#: Kernel command line, read for `isolcpus=` / `nohz_full=`.
PROC_CMDLINE = Path("/proc/cmdline")


class Role(enum.Enum):
    """A row of §10's table. The value is the spec's own wording, trimmed.

    A `Role` is what a PROCESS declares itself to be; the core set it is entitled
    to is `SPEC_ASSIGNED[role]` and is not settable from outside this module.
    """

    OS = "os"
    """Core 0 — OS/kernel + interrupts. Nix never pins anything here."""

    CAPTURE = "capture"
    """Core 1 — `capture.py`, hosting the **broker-datafeed** library."""

    RISK_ENGINE = "risk_engine"
    """Core 2 — Risk Engine (Limiter + broker-order). Not built yet."""

    ALLOCATOR = "allocator"
    """Core 3 — Allocator + strategy processes. Not built yet."""

    SHARED_POOL = "shared_pool"
    """Cores 4-5 — Postgres, pollers, backfill, logging, ZMQ proxy, dashboards,
    health, Sentinel, Scoring process."""


#: §10's table, verbatim in structure. `frozenset` because a core set has no
#: order and must not be mutated by a consumer holding a reference to it.
SPEC_ASSIGNED: dict[Role, frozenset[int]] = {
    Role.OS: frozenset({0}),
    Role.CAPTURE: frozenset({1}),
    Role.RISK_ENGINE: frozenset({2}),
    Role.ALLOCATOR: frozenset({3}),
    Role.SHARED_POOL: frozenset({4, 5}),
}

#: Every core §10 assigns to anything: 0-5. The slice's `AllowedCPUs=0-5` is the
#: same set, and that agreement is asserted by `checks/check_core_map.py` rather
#: than assumed here.
SPEC_CORES: frozenset[int] = frozenset().union(*SPEC_ASSIGNED.values())

#: Roles Nix may pin a process of its own to. `Role.OS` is excluded: core 0 is
#: the kernel's, and a Nix process asking to be pinned there is a bug, not a
#: configuration.
PINNABLE: frozenset[Role] = frozenset(SPEC_ASSIGNED) - {Role.OS}

_CPU_LIST = re.compile(r"^\s*\d+(-\d+)?(\s*,\s*\d+(-\d+)?)*\s*$")


class CoreMapError(RuntimeError):
    """A core-map operation failed. Always carries what could not be done."""


def parse_cpu_list(text: str) -> frozenset[int]:
    """Parse a Linux CPU list (`0-5`, `1,3,5`, `0-2,7`) into a set.

    Raises rather than returning an empty set on garbage: an empty affinity mask
    is not a thing the kernel produces, so `set()` as an error signal would be a
    value that means both "no CPUs" and "I could not read it".
    """
    stripped = text.strip()
    if not stripped:
        raise CoreMapError("empty CPU list")
    if not _CPU_LIST.match(stripped):
        raise CoreMapError(f"not a CPU list: {stripped!r}")
    cores: set[int] = set()
    for part in stripped.split(","):
        low, _, high = part.strip().partition("-")
        cores.update(range(int(low), int(high or low) + 1))
    return frozenset(cores)


def format_cpu_list(cores: Iterable[int]) -> str:
    """Render a core set the way the kernel does, so evidence strings compare."""
    ordered = sorted(set(cores))
    if not ordered:
        return "-"
    spans: list[str] = []
    start = previous = ordered[0]
    for core in ordered[1:]:
        if core == previous + 1:
            previous = core
            continue
        spans.append(f"{start}" if start == previous else f"{start}-{previous}")
        start = previous = core
    spans.append(f"{start}" if start == previous else f"{start}-{previous}")
    return ",".join(spans)


def affinity_syscall(pid: int) -> frozenset[int]:
    """`sched_getaffinity(2)` for `pid`. The kernel, asked directly."""
    try:
        return frozenset(os.sched_getaffinity(pid))
    except (OSError, ValueError) as exc:
        raise CoreMapError(f"sched_getaffinity({pid}) failed: {exc!r}") from exc


def affinity_procfs(pid: int) -> frozenset[int]:
    """`Cpus_allowed_list` from `/proc/<pid>/status`. The same truth, other door.

    ARC 006's SESSION.md entry records this exact field being read from a live
    process under the slice (*"read its actual kernel-enforced affinity from
    `/proc/<pid>/status` (`Cpus_allowed_list: 0-5`)"*). It is kept as a second
    reader so a parsing defect in either one cannot become the verdict.
    """
    status = Path(f"/proc/{pid}/status")
    try:
        text = status.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CoreMapError(f"cannot read {status}: {exc!r}") from exc
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return parse_cpu_list(line.split(":", 1)[1])
    raise CoreMapError(f"{status} carries no Cpus_allowed_list line")


@dataclasses.dataclass(frozen=True)
class AffinityReading:
    """Two kernel readings of one PID's permitted CPU set, plus their verdict."""

    pid: int
    syscall: frozenset[int] = frozenset()
    procfs: frozenset[int] = frozenset()
    error: str = ""

    @property
    def agree(self) -> bool:
        """True when both readers answered and answered the same."""
        return not self.error and self.syscall == self.procfs

    @property
    def mask(self) -> frozenset[int]:
        """The permitted CPU set. Only meaningful when `agree`."""
        return self.syscall

    def describe(self) -> str:
        """One line of evidence naming both readers, for a check's `evidence`."""
        if self.error:
            return f"pid={self.pid} UNREADABLE: {self.error}"
        return (
            f"pid={self.pid} sched_getaffinity={format_cpu_list(self.syscall)} "
            f"/proc/{self.pid}/status:Cpus_allowed_list="
            f"{format_cpu_list(self.procfs)}"
        )


def effective_affinity(pid: int) -> AffinityReading:
    """Read `pid`'s permitted CPU set through both interfaces. Never raises.

    Returns a reading carrying `error` rather than raising, because every caller
    is a gate whose correct response to "I could not look" is CANNOT_MEASURE and
    never an exception that reads as a failure of the subject.
    """
    try:
        syscall = affinity_syscall(pid)
        procfs = affinity_procfs(pid)
    except CoreMapError as exc:
        return AffinityReading(pid=pid, error=str(exc))
    return AffinityReading(pid=pid, syscall=syscall, procfs=procfs)


def pin_self(role: Role) -> AffinityReading:
    """Pin THIS process to `role`'s §10 cores and re-read the result.

    The return value is a fresh read through both interfaces **after** the
    `sched_setaffinity` call, never the argument that was passed in — a function
    that reported the mask it asked for would be `nix_check_contract.md` §4.3's
    "a return value from the correcting path is not a verification" in miniature.

    `Role.OS` is refused: core 0 is the kernel's.
    """
    if role not in PINNABLE:
        raise CoreMapError(
            f"role {role.value} is not pinnable — §10 gives core 0 to the OS and "
            "Nix pins nothing there"
        )
    cores = SPEC_ASSIGNED[role]
    try:
        os.sched_setaffinity(0, cores)
    except OSError as exc:
        raise CoreMapError(
            f"sched_setaffinity(self, {format_cpu_list(cores)}) failed for role "
            f"{role.value}: {exc!r}"
        ) from exc
    return effective_affinity(os.getpid())


def slice_cpuset() -> tuple[frozenset[int], str]:
    """The trading slice's KERNEL-effective cpuset, or why it could not be read.

    Returns `(cores, error)`. An empty `cores` with an empty `error` cannot
    happen: `parse_cpu_list` refuses an empty list.

    The cgroup directory exists only while the slice has had a member — systemd
    creates it lazily — so "not present" means *nothing has ever run in the
    slice*, which is a real and reportable state and is **not** the same as
    "the slice is misconfigured".
    """
    if not TRADING_SLICE_CPUSET.is_file():
        return frozenset(), (
            f"{TRADING_SLICE_CPUSET} absent — systemd creates a slice's cgroup "
            f"lazily, so {TRADING_SLICE} has no live cpuset to read; its "
            "enforcement is unobservable until a unit joins it"
        )
    try:
        return parse_cpu_list(TRADING_SLICE_CPUSET.read_text(encoding="utf-8")), ""
    except (OSError, CoreMapError) as exc:
        return frozenset(), f"{TRADING_SLICE_CPUSET}: {exc!r}"


def isolated_cores() -> tuple[frozenset[int], str]:
    """Cores the KERNEL was told to isolate, from `/proc/cmdline`.

    Returns `(cores, note)`. `note` is non-empty whenever the answer is "the
    kernel was told nothing" — which is this node's measured state and is the
    honest form of §10's *"isolcpus/nohz_full/IRQ affinity for the rest"* being
    unimplemented. Reporting `frozenset()` alone would let a caller read "no
    cores are isolated" as "isolation was checked and is fine".
    """
    try:
        cmdline = PROC_CMDLINE.read_text(encoding="utf-8")
    except OSError as exc:
        return frozenset(), f"cannot read {PROC_CMDLINE}: {exc!r}"
    isolated: set[int] = set()
    seen: list[str] = []
    for token in cmdline.split():
        key, _, value = token.partition("=")
        if key not in ("isolcpus", "nohz_full") or not value:
            continue
        seen.append(token)
        # isolcpus accepts flag prefixes (`isolcpus=domain,managed_irq,2-5`);
        # anything that is not a CPU list is a flag and is skipped rather than
        # guessed at.
        for part in value.split(","):
            try:
                isolated.update(parse_cpu_list(part))
            except CoreMapError:
                continue
    if not seen:
        return frozenset(), (
            f"{PROC_CMDLINE} carries neither isolcpus= nor nohz_full= — §10's "
            "isolation column is NOT in effect on this node; affinity is "
            "inclusion only and says nothing about who else may use these cores"
        )
    return frozenset(isolated), ""


def off_map_cores(mask: Iterable[int]) -> frozenset[int]:
    """Cores in `mask` that §10 assigns to nothing (i.e. 6 and above here)."""
    return frozenset(mask) - SPEC_CORES


def role_for_cores(mask: Iterable[int]) -> Role | None:
    """The §10 role whose core set is exactly `mask`, or `None` for no row.

    Exact equality, not subset: a process permitted cores `{1, 2}` is not "the
    capture role, loosely" — it is a process that may preempt the Risk Engine,
    which is the specific thing §10's split exists to prevent.
    """
    wanted = frozenset(mask)
    for role, cores in SPEC_ASSIGNED.items():
        if cores == wanted:
            return role
    return None
