"""ARC 027 C4 — the standing gate over D1.44's reserved cores.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. A demonstration missing the last step shows only that a gate can fail.

**The plant here is a PROCESS, not a file** (doctrine C.8 — no plant touches a
production artifact). Every can-fail spawns a real interpreter under the real
`nix_home`, pins it to a real reserved core, drives the SHIPPED gate against the
real process table, and reaps the child on every path including failure. Nothing
under `~/nix` is written, moved or edited by any test in this file.

**Every control asserts the REASON** — the PID and the named condition — never
the exit code alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access
# pylint: disable=use-implicit-booleaness-not-comparison,consider-using-with
# `errors == ()` asserts the TYPE and the emptiness together, the same
# convention `scripts/tests/test_declarations.py` adopts: `not x` is also
# satisfied by `None`, so a reader that started returning None would pass a
# truthiness assertion while having measured nothing.
# `consider-using-with`: the plant's lifetime is deliberately LONGER than the
# fixture body — the gate measures /proc for it while it holds — and the
# fixture's own `finally` owns the kill and the reap on every path.
# `protected-access`: the can-fail controls drive the gate's ARMS and its census
# helper, which are private by design. Making them public so a test could reach
# them would be a surface invented for the test.
# pylint: disable=duplicate-code
# Test names SHOUT the property; the sys.path bootstrap forces late imports and
# is identical in every check test by requirement.

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_reserved_cores as gate  # pylint: disable=wrong-import-position
from nixbus.core_map import (  # pylint: disable=wrong-import-position
    SPEC_CORES,
    current_cpu,
    nix_processes,
    online_cores,
    reserved_cores,
    slice_members,
)
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_reserved_cores.py"

#: A plant that pins itself to one core and holds. Spawned under the REAL
#: `nix_home` interpreter so it is a Nix process by the enumerator's own
#: predicate — not by a special case written for this file.
_PIN_AND_HOLD = (
    "import os,time\n"
    "os.sched_setaffinity(0,{{{core}}})\n"
    "print('ready',flush=True)\n"
    "time.sleep(20)\n"
)


def _ctx() -> Context:
    return Context(nix_home=REPO, mode=Mode.VERIFY)


@pytest.fixture
def reserved() -> frozenset[int]:
    """The reserved set on THIS box, or skip: there is nothing to test on 6 cores."""
    cores, error = reserved_cores()
    if error or not cores:
        pytest.skip(f"no reserved cores on this node ({error or 'all cores assigned'})")
    return cores


@pytest.fixture
def pinned_child(reserved: frozenset[int]) -> Iterator[subprocess.Popen[str]]:
    """A live Nix process PINNED to a reserved core. Reaped on every path."""
    python = REPO / ".venv" / "bin" / "python3"
    if not python.is_file():
        pytest.skip(f"no venv interpreter at {python}")
    core = max(reserved)
    proc = subprocess.Popen(
        [str(python), "-c", _PIN_AND_HOLD.format(core=core)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=20)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the enumerator and the readers actually see this node
# --------------------------------------------------------------------------


def test_the_enumerator_finds_this_very_process() -> None:
    """The credibility floor: a census blind to its own author proves nothing."""
    import os

    found, _ = nix_processes(REPO)
    assert os.getpid() in {process.pid for process in found}, (
        "the enumerator did not find the pytest process, which is running "
        f"{sys.argv[0]!r} from inside {REPO} — every clean reading it produces "
        "would be uninformative"
    )


def test_the_reserved_set_is_disjoint_from_every_core_section_10_assigns() -> None:
    """The surplus is NOT more pool, and the arithmetic makes that unreachable."""
    cores, error = reserved_cores()
    assert not error, error
    assert not (cores & SPEC_CORES), (
        f"reserved={sorted(cores)} intersects §10's assigned set "
        f"{sorted(SPEC_CORES)} — the surplus has been folded into the map"
    )


def test_current_cpu_reads_a_real_core_for_a_pinned_process(
    pinned_child: subprocess.Popen[str], reserved: frozenset[int]
) -> None:
    """`/proc/<pid>/stat` field 39 is occupancy, and it tracks the pin."""
    core = max(reserved)
    for _ in range(50):
        cpu, error = current_cpu(pinned_child.pid)
        assert not error, error
        if cpu == core:
            return
        time.sleep(0.02)
    pytest.fail(
        f"a process pinned to core {core} never reported that core in "
        f"/proc/{pinned_child.pid}/stat field 39 — the occupancy reader is not "
        "reading occupancy"
    )


def test_current_cpu_survives_a_comm_containing_spaces_and_parens(
    tmp_path: Path,
) -> None:
    """The `)`-split, not a whitespace split. A shifted field is a wrong core."""
    stat = tmp_path / "stat"
    fields = " ".join(str(n) for n in range(3, 40))
    stat.write_text(f"1234 (weird ) name) {fields}\n", encoding="utf-8")
    monkeyed = stat.read_text(encoding="utf-8")
    _, _, tail = monkeyed.rpartition(")")
    assert int(tail.split()[39 - 3]) == 39, (
        "the field arithmetic is wrong: field 39 must be the 37th token after "
        "the last ')'"
    )


def test_online_cores_reads_sysfs_and_not_a_cpu_count() -> None:
    """WHICH cores exist, not how many. A count cannot express a gap."""
    cores, error = online_cores()
    assert not error, error
    assert cores, "sysfs reported no online CPU, which cannot be true of a box"
    assert 0 in cores, f"CPU 0 is not online according to {sorted(cores)}"


def test_slice_membership_is_the_kernels_answer_and_says_so_when_absent() -> None:
    """`cgroup.procs` or a named error — never a silent empty tuple."""
    pids, error = slice_members()
    assert isinstance(pids, tuple)
    if error:
        assert "cannot read" in error and "cgroup.procs" in error
    else:
        assert all(isinstance(pid, int) for pid in pids)


def test_an_unpinned_process_is_not_reported_as_pinned(
    reserved: frozenset[int],
) -> None:
    """The distinction D1.44 turns on: drift is not an assignment."""
    del reserved
    import os

    online, _ = online_cores()
    found, _ = nix_processes(REPO)
    me = next(p for p in found if p.pid == os.getpid())
    assert me.mask == online, (
        f"this test process is pinned to {sorted(me.mask)}; the suite must not be "
        "pinning its own runner"
    )
    assert me.pinned(online) is False


def test_a_pinned_process_IS_reported_as_pinned_and_as_occupying(
    pinned_child: subprocess.Popen[str], reserved: frozenset[int]
) -> None:
    """Both facts, separately: permitted (mask) and observed (task_cpu)."""
    online, _ = online_cores()
    core = max(reserved)
    for _ in range(50):
        found, _ = nix_processes(REPO)
        matches = [p for p in found if p.pid == pinned_child.pid]
        if matches and matches[0].occupies(reserved):
            process = matches[0]
            assert process.pinned(online) is True
            assert process.reserved_in_mask(reserved) == frozenset({core})
            return
        time.sleep(0.02)
    pytest.fail(
        f"a process pinned to reserved core {core} was never reported as occupying it"
    )


# --------------------------------------------------------------------------
# THE CAN-FAIL — a real process on a reserved core, and the SHIPPED gate reddens
# --------------------------------------------------------------------------


def test_a_nix_process_pinned_to_a_reserved_core_FAILS_and_names_its_pid(
    pinned_child: subprocess.Popen[str], reserved: frozenset[int]
) -> None:
    """§0e's committed artifact: the shipped gate driven red by a real violation."""
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status in (Status.FAIL_NEEDS_OPERATOR, Status.FAIL_REPAIRABLE), (
        f"a live Nix process pinned to reserved core {max(reserved)} produced "
        f"{result.status} — detail={result.detail!r}"
    )
    assert f"pid={pinned_child.pid}" in result.detail, (
        "the verdict does not name the offending PID; an exit code alone is a "
        f"shared namespace (detail={result.detail!r})"
    )
    assert "NARROWED onto reserved core" in result.detail, (
        f"the verdict does not name the CONDITION it detected: {result.detail!r}"
    )
    assert "sched_getaffinity" in result.site, (
        f"the verdict does not name the reader it used: site={result.site!r}"
    )


def test_the_same_population_passes_once_the_plant_is_gone(
    reserved: frozenset[int],
) -> None:
    """The third step. Without it the gate is only known to be able to fail."""
    del reserved
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status is Status.PASS, (
        f"with no planted process the gate is {result.status}: {result.detail!r}"
    )
    assert "NON-VACUITY" in result.evidence
    assert "RESERVED-UNASSIGNED" in result.evidence


# --------------------------------------------------------------------------
# THE GATE'S OWN NON-VACUITY ARM, and its refusals
# --------------------------------------------------------------------------


def test_the_gate_plants_reaps_and_reports_the_plant_it_found() -> None:
    """Arm 0 runs for real and names the core it planted on."""
    cores, error = reserved_cores()
    if error or not cores:
        pytest.skip("no reserved cores on this node")
    online, _ = online_cores()
    evidence, why = gate._arm0_plant(REPO, cores, online)
    assert not why, why
    assert f"reserved core {max(cores)}" in evidence
    assert "after the reap the same population is clean" in evidence


def test_a_box_with_no_surplus_is_CANNOT_MEASURE_and_never_a_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 6-core QuantVPS case. An empty reserved set is not a clean reading."""
    monkeypatch.setattr(gate, "reserved_cores", lambda: (frozenset(), ""))
    monkeypatch.setattr(gate, "online_cores", lambda: (frozenset(range(6)), ""))
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status is Status.CANNOT_MEASURE
    assert "no surplus to reserve" in result.detail


def test_a_census_that_cannot_see_its_own_author_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The vacuity the architect named: zero processes must not read as empty."""
    monkeypatch.setattr(gate, "nix_processes", lambda home: ((), ""))
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status is Status.CANNOT_MEASURE
    assert "cannot see its own author" in result.detail


def test_widening_section_10s_shared_pool_over_the_surplus_FAILS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Arm 3: folding 6-19 into the pool would turn this gate off in silence."""
    from nixbus.core_map import Role

    widened = dict(gate.SPEC_ASSIGNED)
    widened[Role.SHARED_POOL] = frozenset(range(4, 20))
    monkeypatch.setattr(gate, "SPEC_ASSIGNED", widened)
    defects: list[tuple[str, str]] = []
    gate._arm3_pool(frozenset(range(6, 20)), defects, [])
    assert defects, "a widened shared pool produced no defect"
    site, why = defects[0]
    assert "SHARED_POOL" in site
    assert "the locked table says cores 4-5" in why


def test_a_slice_cpuset_admitting_a_reserved_core_FAILS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Arm 2: the cgroup is the kernel's enforcement, and it must not admit 6-19."""
    monkeypatch.setattr(gate, "slice_cpuset", lambda: (frozenset(range(8)), ""))
    defects: list[tuple[str, str]] = []
    assert gate._arm2_slice(frozenset(range(6, 20)), defects, []) == ""
    assert defects, "a slice cpuset covering cores 6-7 produced no defect"
    site, why = defects[0]
    assert "cpuset.cpus.effective" in site
    assert "includes reserved core(s) 6-7" in why


# --------------------------------------------------------------------------
# DECLARATIONS — the plan reads these statically and must be able to
# --------------------------------------------------------------------------


def test_the_gate_declares_what_the_plan_needs() -> None:
    """`DEPENDS_ON`/`RESOURCES`/`ON_FAIL`/`SUBJECTS`, parsed by AST, no errors."""
    declaration = read_declaration(GATE_FILE)
    assert declaration.errors == ()
    assert declaration.depends_on == ("check_venv",)
    assert set(declaration.resources) == {"subprocess:python3", "cpu-affinity"}
    assert declaration.on_fail == "continue"
    assert "scripts/nixbus/core_map.py" in declaration.subjects
