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

## ARC 027 — the architect decided it, and the decision is RESERVED-EMPTY

`docs/CHECK-DEBT.md` **D1.44** carried that finding as an explicit architect
question. The ruling this arc implements: cores above §10's table are **reserved
and unassigned**, and are to be kept **empty of Nix processes**. Explicitly NOT
more shared pool — §10's pool is cores 4-5 and stays cores 4-5, which
`reserved_cores()` asserts by construction rather than by comment (it subtracts
`SPEC_CORES`, of which 4 and 5 are members, so a reserved set that contained
either would be arithmetically impossible).

Reservation needs three readers §10's affinity story did not, and each is a
DIFFERENT fact:

| reader | interface | the fact |
|---|---|---|
| `online_cores` | `/sys/devices/system/cpu/online` | which cores EXIST to reserve |
| `current_cpu` | `/proc/<pid>/stat` field 39 | where a task LAST RAN — occupancy |
| `slice_members` | `nix-trading.slice`'s `cgroup.procs` | who the kernel counts as Nix |

`current_cpu` is the one this module's own header called *"NOT MEASURED ... a
different fact and is not read"*. It is read now, because *empty* is a statement
about where tasks ran and an affinity mask cannot make it: a process permitted
`0-19` is permitted core 7 and may never once have been scheduled there. Both
facts are reported separately and neither is allowed to stand in for the other.
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

#: Cores the kernel has ONLINE. `os.cpu_count()` is deliberately not used: it
#: answers "how many", and a reservation is about WHICH — a box with cores 0-3
#: and 8-11 online has count 8 and no core 4, and a set built from `range(count)`
#: would reserve four cores that do not exist while missing four that do.
CPU_ONLINE = Path("/sys/devices/system/cpu/online")

#: The trading slice's process list, as the KERNEL maintains it. Membership here
#: is not a claim anyone can write in a file: systemd puts a process in the
#: cgroup, and this is the cgroup's own answer.
TRADING_SLICE_PROCS = Path("/sys/fs/cgroup/nix.slice/nix-trading.slice/cgroup.procs")

#: `/proc/<pid>/stat` field 39 (`processor`), 1-based per `proc(5)`. Fields 1 and
#: 2 (`pid`, `comm`) are consumed by the `)`-split below, so field 3 is index 0
#: of the remainder and the offset is `39 - 3`.
_STAT_PROCESSOR_INDEX = 39 - 3


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


def online_cores() -> tuple[frozenset[int], str]:
    """Cores the kernel reports ONLINE, from sysfs. Returns `(cores, error)`.

    Never raises, and never falls back to `os.cpu_count()`. A fallback would let
    the reserved set be derived from a *count* when the *identity* of the cores is
    the whole question, and it would do so silently — the caller would receive a
    plausible set and no way to know which reader produced it.
    """
    try:
        text = CPU_ONLINE.read_text(encoding="utf-8")
    except OSError as exc:
        return frozenset(), f"cannot read {CPU_ONLINE}: {exc!r}"
    try:
        return parse_cpu_list(text), ""
    except CoreMapError as exc:
        return frozenset(), f"{CPU_ONLINE}: {exc}"


def reserved_cores() -> tuple[frozenset[int], str]:
    """Cores that EXIST and that §10 assigns to nothing. D1.44's subject.

    `online - SPEC_CORES`. Cores 4-5 are members of `SPEC_CORES` (§10's shared
    pool), so a reserved set containing either is not merely wrong, it is
    unreachable by this arithmetic — which is how *"the surplus is not more
    pool"* is enforced rather than asserted.

    An EMPTY reserved set is a real and reportable state, not a defect: on the
    6-core QuantVPS box §10's table is the whole machine and there is nothing to
    reserve. The `error` string is empty in that case, and a caller must treat an
    empty set as "nothing to measure here", never as "everything is clear".
    """
    online, error = online_cores()
    if error:
        return frozenset(), error
    return online - SPEC_CORES, ""


def current_cpu(pid: int) -> tuple[int | None, str]:
    """The CPU `pid`'s task LAST RAN ON (`/proc/<pid>/stat` field 39).

    Returns `(cpu, error)`. This is OCCUPANCY, not permission, and it is the only
    one of the two that can answer "is this core empty" — see the module header.

    The `comm` field can contain spaces AND parentheses (`(sh -c foo)bar`), so the
    parse splits at the LAST `)`. Splitting on whitespace, or on the first `)`,
    silently shifts every subsequent field and yields a confident wrong core
    number, which is worse than an error.
    """
    stat = Path(f"/proc/{pid}/stat")
    try:
        text = stat.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"cannot read {stat}: {exc!r}"
    _, _, tail = text.rpartition(")")
    fields = tail.split()
    if len(fields) <= _STAT_PROCESSOR_INDEX:
        return None, f"{stat} carries {len(fields)} field(s) after comm; need 37"
    try:
        return int(fields[_STAT_PROCESSOR_INDEX]), ""
    except ValueError as exc:
        return None, f"{stat} field 39 is not an integer: {exc!r}"


def slice_members() -> tuple[tuple[int, ...], str]:
    """PIDs the kernel counts as members of `nix-trading.slice`.

    Returns `(pids, error)`. As with `slice_cpuset`, an absent file means the
    slice has never had a member — systemd creates the cgroup lazily — and that
    is reported as an error string rather than as an empty tuple, because "no
    members" and "no cgroup to ask" are the two facts a reservation gate must not
    confuse.
    """
    try:
        text = TRADING_SLICE_PROCS.read_text(encoding="utf-8")
    except OSError as exc:
        return (), f"cannot read {TRADING_SLICE_PROCS}: {exc!r}"
    pids: list[int] = []
    for line in text.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return tuple(pids), ""


@dataclasses.dataclass(frozen=True)
class ProcessCore:
    """One process, its permitted mask, and where it last ran. Both facts, apart."""

    pid: int
    cmdline: str
    mask: frozenset[int]
    cpu: int | None
    in_slice: bool
    error: str = ""

    def pinned(self, online: frozenset[int]) -> bool:
        """True when something narrowed this process's mask below the whole box.

        A process at the box default is NOT pinned, and the distinction is the
        one D1.44 turns on: an unpinned process is *permitted* every reserved
        core by nobody's decision, whereas a process whose mask was narrowed ONTO
        a reserved core was put there deliberately.
        """
        return bool(self.mask) and self.mask != online

    def reserved_in_mask(self, reserved: frozenset[int]) -> frozenset[int]:
        """Reserved cores this process is PERMITTED to run on."""
        return self.mask & reserved

    def occupies(self, reserved: frozenset[int]) -> bool:
        """True when this process's task was last scheduled ON a reserved core."""
        return self.cpu is not None and self.cpu in reserved


def _cmdline_of(pid: int) -> str:
    """`/proc/<pid>/cmdline`, NUL-separated, rendered with spaces. `''` if gone."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return " ".join(part for part in raw.decode("utf-8", "replace").split("\0") if part)


def _cwd_of(pid: int) -> Path | None:
    """`/proc/<pid>/cwd`, or `None` when it cannot be followed.

    Needed because argv is routinely RELATIVE: `./.venv/bin/python
    checks/check_x.py` is how every check is run by hand, and neither token is an
    absolute path. Resolving them the way the kernel did — against the process's
    own working directory — is the difference between finding those processes and
    reporting an empty census. MEASURED: the first spelling of `_mentions_home`
    considered absolute tokens only, and `check_reserved_cores` could not find
    ITSELF.
    """
    try:
        return Path(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return None


def _image_of(pid: int) -> Path | None:
    """`/proc/<pid>/exe` — the binary the KERNEL resolved — or `None`.

    Not a guess about a token: the image the kernel already resolved through
    `PATH`. `None` when the link cannot be followed (the process exited
    mid-scan, or it belongs to another user).
    """
    try:
        return Path(os.readlink(f"/proc/{pid}/exe"))
    except OSError:
        return None


def _image_under(pid: int, nix_home: Path) -> bool:
    """Is this process's executable image inside `nix_home`?

    `is_relative_to`, never `startswith`, for the same reason `_mentions_home`
    says: `/home/bbt/nix` is a string prefix of `/home/bbt/nix-wt-arc-027-c`.

    **What this does NOT cover, MEASURED rather than assumed.** It was written
    for a venv interpreter and does not catch one: `~/nix/.venv/bin/python` is a
    SYMLINK, so the kernel records `/usr/bin/python3.14` and this predicate is
    False for every Python process in the tree. It is kept because it covers a
    different, real population — anything whose binary genuinely lives under
    `nix_home` — and because the disproof is worth more on the page than the
    predicate is. `_runs_tree_venv` is what closes the venv case.
    """
    image = _image_of(pid)
    if image is None:
        return False
    try:
        return image.is_relative_to(nix_home)
    except OSError, ValueError:
        return False


def _environ_of(pid: int) -> dict[str, str]:
    """`/proc/<pid>/environ` as a mapping. Empty when it cannot be read.

    The INITIAL environment, which is the right one: the question is how the
    process was STARTED, not what it has re-exported since. Unreadable for
    another user's processes, which degrades to "not attributed by this
    predicate" — never to an exception a caller would read as a verdict.
    """
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for part in raw.decode("utf-8", "replace").split("\0"):
        name, sep, value = part.partition("=")
        if sep:
            out.setdefault(name, value)
    return out


def _venv_interpreter(nix_home: Path) -> Path | None:
    """The real binary `nix_home/.venv/bin/python` resolves to, or `None`.

    Resolved from the TREE, so the comparison in `_runs_tree_venv` is against a
    fact about this repository rather than a hardcoded system path.
    """
    link = nix_home / ".venv" / "bin" / "python"
    try:
        return link.resolve(strict=True)
    except OSError:
        return None


def _runs_tree_venv(pid: int, nix_home: Path) -> bool:
    """Is this process the tree's venv interpreter, started from that venv?

    MEASURED, ARC 028 / 0.1, and this is the predicate the defect actually
    needed. `_mentions_home` deliberately refuses to resolve BARE WORDS against
    the cwd — correctly, since that rule is what keeps an operator's shell out of
    a core census. But an activated venv spells the interpreter `python`, so
    under `python -m pytest` NO argv token names a path, the census could not see
    its own author, and `check_reserved_cores` returned CANNOT_MEASURE naming its
    own pid. The byte-identical run under `./.venv/bin/python -m pytest` passed:
    **the verdict was a function of the invocation spelling, not of the
    property.** `nix_processes` had already conceded this miss in prose ("a Nix
    process re-exec'd with a bare interpreter and no path argument"); a conceded
    blindness in a §10 safety census is still a blindness.

    TWO kernel facts, both required, because either alone over-attributes:

    * `VIRTUAL_ENV` names a venv inside `nix_home` — but an operator's `bash`
      inherits that variable the moment they `activate`, and a shell is not a
      Nix process.
    * `/proc/<pid>/exe` is the binary that venv's `python` resolves to — which
      excludes the shell, since `/bin/bash` is not the interpreter.

    The residual over-attribution is a SYSTEM interpreter invoked by hand from an
    activated shell. That process is running inside this tree's environment, so
    counting it is the conservative direction for a census whose failure mode is
    missing a process that occupies a reserved core.
    """
    venv = _venv_interpreter(nix_home)
    if venv is None:
        return False
    declared = _environ_of(pid).get("VIRTUAL_ENV")
    if not declared:
        return False
    try:
        if not Path(declared).is_relative_to(nix_home):
            return False
    except OSError, ValueError:
        return False
    return _image_of(pid) == venv


def _mentions_home(pid: int, cmdline: str, nix_home: Path) -> bool:
    """Does any argv token name a path inside `nix_home`?

    `Path.is_relative_to`, never a string `startswith`: `/home/bbt/nix` is a
    string prefix of `/home/bbt/nix-wt-arc-027-c`, so a prefix test would count a
    different tree's processes as this tree's. MEASURED — three worktrees of this
    repository were live on this node while this function was written.

    A token counts as a path candidate only if it contains a `/` or ends in a
    source-file suffix. Bare words (`git`, `-q`, `--json`) are not resolved
    against the cwd: doing so would make every process whose working directory
    happens to be inside the tree a Nix process, which would sweep an operator's
    shell into a core-map census.
    """
    cwd: Path | None = None
    for token in cmdline.split():
        if token.startswith("/"):
            candidate = Path(token)
        elif "/" in token or token.endswith((".py", ".sh")):
            if cwd is None:
                cwd = _cwd_of(pid)
            if cwd is None:
                continue
            candidate = cwd / token
        else:
            continue
        try:
            if candidate.is_relative_to(nix_home):
                return True
        except OSError, ValueError:
            continue
    return False


def nix_processes(nix_home: Path) -> tuple[tuple[ProcessCore, ...], str]:
    """Every live process this node can attribute to Nix, with both core facts.

    Returns `(processes, error)`. FOUR independent predicates, unioned, because
    they cover different populations and each misses what the others catch:

    * **`nix-trading.slice` membership** — the kernel's own answer, and the
      population §10's map is actually about. Misses anything Nix runs outside
      the slice, which today is everything: no unit has ever joined it (D1.42).
    * **an argv token under `nix_home`** — catches an interactively-run
      `verify.py`, a `pytest scripts/tests/...`, a spawned `capture.py`. Misses a
      process whose every argv token is a bare word.
    * **an executable image under `nix_home`** (`/proc/exe`) — catches a binary
      that genuinely lives in the tree. MEASURED not to catch the venv
      interpreter, which is a symlink out to `/usr/bin`; see `_image_under`.
    * **the tree's venv interpreter, started from that venv** (ARC 028 / 0.1) —
      catches `python -m pytest` under an activated venv, which is how this
      suite is routinely run and which every predicate above loses. See
      `_runs_tree_venv` for why it takes two kernel facts and not one.

    Together they are still not "every Nix process" — a Nix process running a
    system interpreter, outside the slice, with no path argument and no
    `VIRTUAL_ENV` is invisible to all four — and this docstring says so rather
    than a gate implying otherwise. A process is reported with `error` set when it
    was attributed but could not be read — it exited mid-scan, or it belongs to
    another user — and a caller must not read that as a clean core.
    """
    members, member_error = slice_members()
    in_slice = set(members)
    try:
        candidates = {
            int(entry.name) for entry in Path("/proc").iterdir() if entry.name.isdigit()
        }
    except OSError as exc:
        return (), f"cannot enumerate /proc: {exc!r}"
    found: list[ProcessCore] = []
    for pid in sorted(candidates | in_slice):
        cmdline = _cmdline_of(pid)
        member = pid in in_slice
        # Ordered cheapest-first: the argv scan is string work over a string
        # already read, and only falls through to a second readlink when it
        # finds nothing. Both are unioned, so the order costs nothing but time.
        if (
            not member
            and not _mentions_home(pid, cmdline, nix_home)
            and not _image_under(pid, nix_home)
            and not _runs_tree_venv(pid, nix_home)
        ):
            continue
        reading = effective_affinity(pid)
        cpu, cpu_error = current_cpu(pid)
        found.append(
            ProcessCore(
                pid=pid,
                cmdline=cmdline,
                mask=reading.mask if reading.agree else frozenset(),
                cpu=cpu,
                in_slice=member,
                error="; ".join(part for part in (reading.error, cpu_error) if part),
            )
        )
    return tuple(found), member_error


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
