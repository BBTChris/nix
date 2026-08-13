"""ARC 026 — the properties `scripts/nixbus/core_map.py` claims, made falsifiable.

What each test proves, stated before the code:

* **Round-trip.** `parse_cpu_list`/`format_cpu_list` survive every shape the
  kernel renders (`0-5`, `1,3,5`, `0-2,7`, `1`), so an evidence string built from
  a parsed mask compares byte-for-byte with the one `/proc` produced.
* **Garbage is named, never absorbed.** An empty or malformed list raises
  `CoreMapError` carrying the offending text — an empty set as an error signal
  would mean both "no CPUs" and "I could not read it".
* **`SPEC_ASSIGNED` is §10's table, exactly.** 0->OS, 1->CAPTURE, 2->RISK_ENGINE,
  3->ALLOCATOR, {4,5}->SHARED_POOL, and `SPEC_CORES == {0..5}` — cores 6+ are
  assigned to nothing and are not folded into the shared pool.
* **`role_for_cores` is EXACT equality.** `{1, 2}` is not "capture, loosely"; it
  is a process that may preempt the Risk Engine, and it maps to no row.
* **`pin_self` refuses core 0 and says whose it is.**
* **`effective_affinity` measures a real PID.** Both readers agree on this live
  process; a PINNED CHILD reads back a DIFFERENT mask than its parent, which is
  what makes the reader a measurement rather than an echo; and an absent PID
  yields a reading whose `.error` names the failed syscall and whose `.agree` is
  False, never an exception a gate would read as a verdict about its subject.
* **`isolated_cores` never reports isolation it did not read.** A non-empty note
  and a non-empty core set are mutually exclusive.

**No test pins the pytest process.** The single pinned subject is a short-lived
child spawned with `sys.executable`, writing its report into `tmp_path`, measured
from the parent and killed in a `finally`. Nothing here touches a production
artifact: the only writes are under `tmp_path`, and every reader is read-only.
"""
# pylint: disable=invalid-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is shared with the other
# suites by design. Each deliberate, so the pragma is named.

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixbus import core_map  # pylint: disable=wrong-import-position
from nixbus.core_map import (  # pylint: disable=wrong-import-position
    CoreMapError,
    Role,
)

#: Longest the parent waits for the spawned child to report its pin.
CHILD_TIMEOUT_S = 10.0
CHILD_POLL_S = 0.05

#: The child pins itself to §10's CAPTURE core and holds, so the parent has a
#: live `/proc/<pid>` to read. It reports through a file rather than a pipe: a
#: blocking `readline()` on a child that failed to start is a hung test suite.
_CHILD = """
import json, os, sys, time
from nixbus.core_map import Role, pin_self
reading = pin_self(Role.CAPTURE)
open(sys.argv[1], "w", encoding="utf-8").write(
    json.dumps({"pid": reading.pid, "syscall": sorted(reading.syscall)})
)
time.sleep(float(sys.argv[2]))
"""


# --- CPU lists: round-trip, and refusal that names the text ---------------


@pytest.mark.parametrize(
    ("text", "cores"),
    [
        ("0-5", {0, 1, 2, 3, 4, 5}),
        ("1,3,5", {1, 3, 5}),
        ("0-2,7", {0, 1, 2, 7}),
        ("1", {1}),
    ],
)
def test_a_KERNEL_CPU_LIST_round_trips_through_parse_and_format(
    text: str, cores: set[int]
) -> None:
    """Parsed to the right set, and rendered back to the identical string."""
    parsed = core_map.parse_cpu_list(text)
    assert parsed == frozenset(cores), f"{text!r} parsed to {sorted(parsed)}"
    assert core_map.format_cpu_list(parsed) == text, core_map.format_cpu_list(parsed)


def test_an_EMPTY_cpu_list_raises_and_says_it_was_EMPTY() -> None:
    """The reason, not the type: `set()` must never be an error signal."""
    with pytest.raises(CoreMapError, match="empty CPU list"):
        core_map.parse_cpu_list("   ")


@pytest.mark.parametrize("garbage", ["0-5;7", "cpus=0-5", "0--5", "-1"])
def test_GARBAGE_raises_and_NAMES_the_offending_text(garbage: str) -> None:
    """The message must carry the text that was rejected, verbatim."""
    with pytest.raises(CoreMapError, match="not a CPU list") as refusal:
        core_map.parse_cpu_list(garbage)

    assert repr(garbage) in str(refusal.value), str(refusal.value)


def test_format_cpu_list_renders_an_EMPTY_set_as_a_DASH_not_as_nothing() -> None:
    """An empty rendering must still be visible in an evidence string."""
    assert core_map.format_cpu_list([]) == "-"


# --- §10's table, reproduced exactly ---------------------------------------


def test_SPEC_ASSIGNED_is_SECTION_10s_table_row_for_row() -> None:
    """The locked map: 0/1/2/3 single-core, {4,5} shared, nothing else."""
    assert core_map.SPEC_ASSIGNED == {
        Role.OS: frozenset({0}),
        Role.CAPTURE: frozenset({1}),
        Role.RISK_ENGINE: frozenset({2}),
        Role.ALLOCATOR: frozenset({3}),
        Role.SHARED_POOL: frozenset({4, 5}),
    }
    assert core_map.SPEC_CORES == frozenset({0, 1, 2, 3, 4, 5})


def test_CORE_ZERO_is_the_OSs_and_is_NOT_PINNABLE_by_declaration() -> None:
    """`PINNABLE` is every §10 role except the OS's."""
    assert Role.OS not in core_map.PINNABLE
    assert core_map.PINNABLE == frozenset(
        {Role.CAPTURE, Role.RISK_ENGINE, Role.ALLOCATOR, Role.SHARED_POOL}
    )


def test_role_for_cores_is_EXACT_equality_so_ONE_AND_TWO_is_NO_ROLE() -> None:
    """`{1, 2}` is not 'capture, loosely' — it may preempt the Risk Engine."""
    assert core_map.role_for_cores({1}) is Role.CAPTURE
    assert core_map.role_for_cores({4, 5}) is Role.SHARED_POOL
    assert core_map.role_for_cores({1, 2}) is None, "subset matching would be a lie"
    assert core_map.role_for_cores({4}) is None, "half the shared pool is not the pool"


def test_a_CORE_ABOVE_FIVE_is_OFF_MAP_and_is_not_folded_into_the_pool() -> None:
    """§10 assigns 0-5 and stops; this box has 20 and the rest are unassigned."""
    assert core_map.off_map_cores({1, 7}) == frozenset({7})
    assert core_map.off_map_cores({0, 1, 2, 3, 4, 5}) == frozenset()


def test_pin_self_REFUSES_role_OS_and_names_CORE_ZERO_as_the_OSs() -> None:
    """The refusal carries the reason; nothing is pinned by this call."""
    before = os.sched_getaffinity(0)
    with pytest.raises(CoreMapError, match="§10 gives core 0 to the OS"):
        core_map.pin_self(Role.OS)
    assert os.sched_getaffinity(0) == before, "a refused pin must change nothing"


# --- the live kernel, read two ways ----------------------------------------


def test_the_LIVE_process_is_read_by_BOTH_interfaces_and_they_AGREE() -> None:
    """Non-vacuity: a real PID, a non-empty mask, two readers in agreement."""
    reading = core_map.effective_affinity(os.getpid())

    assert reading.error == "", reading.error
    assert reading.agree is True, reading.describe()
    assert reading.mask, "an empty affinity mask is not a thing the kernel produces"
    assert reading.syscall == reading.procfs, reading.describe()
    assert "sched_getaffinity=" in reading.describe(), reading.describe()
    assert "Cpus_allowed_list=" in reading.describe(), reading.describe()


def _absent_pid() -> int:
    """A PID number that names no process right now, verified both ways."""
    for candidate in range(2**22 - 1, 2**22 - 4096, -1):
        if Path(f"/proc/{candidate}").exists():
            continue
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except PermissionError:
            continue
    raise AssertionError("no absent PID found below pid_max — cannot plant")


def test_an_ABSENT_PID_yields_a_reading_whose_ERROR_names_the_failed_syscall() -> None:
    """A gate's correct response to 'I could not look' is never an exception."""
    pid = _absent_pid()

    reading = core_map.effective_affinity(pid)

    assert reading.agree is False, reading.describe()
    # THE REASON: the named syscall and the PID, not merely 'something failed'.
    assert f"sched_getaffinity({pid})" in reading.error, reading.error
    assert "ProcessLookupError" in reading.error, reading.error
    assert f"pid={pid} UNREADABLE" in reading.describe(), reading.describe()


def test_affinity_syscall_RAISES_for_an_absent_pid_and_NAMES_it() -> None:
    """The raising layer under `effective_affinity` carries the same reason."""
    pid = _absent_pid()
    with pytest.raises(CoreMapError, match=f"sched_getaffinity\\({pid}\\) failed"):
        core_map.affinity_syscall(pid)


def test_affinity_procfs_RAISES_for_an_absent_pid_and_NAMES_the_PATH() -> None:
    """The procfs reader names the file it could not read."""
    pid = _absent_pid()
    with pytest.raises(CoreMapError, match=f"cannot read /proc/{pid}/status"):
        core_map.affinity_procfs(pid)


def test_a_PINNED_CHILD_reads_a_DIFFERENT_MASK_than_this_unpinned_process(
    tmp_path: Path,
) -> None:
    """The measurement, end to end, WITHOUT confining the pytest process.

    A child pins itself to §10's Core 1 and holds. The parent reads that child's
    mask out of the kernel and it must be `{1}` — different from the parent's
    own. A reader that echoed its caller's mask would pass every other test here
    and fail this one.
    """
    parent = core_map.effective_affinity(os.getpid()).mask
    if 1 not in parent:
        pytest.skip(f"this runner may not use core 1 (mask {sorted(parent)})")
    report = tmp_path / "child.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "scripts")
    with subprocess.Popen(  # nosec - sys.executable, literal argv, no shell
        [sys.executable, "-c", _CHILD, str(report), "30"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    ) as child:
        try:
            deadline = time.monotonic() + CHILD_TIMEOUT_S
            while not report.is_file() and time.monotonic() < deadline:
                assert child.poll() is None, f"child died: {child.communicate()[1]}"
                time.sleep(CHILD_POLL_S)
            assert report.is_file(), f"child never reported in {CHILD_TIMEOUT_S}s"
            claimed = json.loads(report.read_text(encoding="utf-8"))

            measured = core_map.effective_affinity(child.pid)

            assert measured.error == "", measured.error
            assert measured.agree is True, measured.describe()
            assert measured.mask == frozenset({1}), measured.describe()
            assert measured.mask != parent, "the child's mask must differ from ours"
            assert core_map.role_for_cores(measured.mask) is Role.CAPTURE
            # The child's own view and the parent's measurement of it must agree,
            # or one of the two readings is about a different process than it
            # believes.
            assert sorted(measured.mask) == claimed["syscall"], claimed
            assert claimed["pid"] == child.pid, claimed
        finally:
            # Unplant: the pinned subject is killed here, never left holding a
            # core. `Popen.__exit__` reaps it.
            child.kill()
    # Unplant: the pin died with the child, and this process was never touched.
    assert os.sched_getaffinity(0) == set(parent), "the runner was repinned"


# --- what is NOT measured, stated as a property ----------------------------


def test_isolated_cores_NEVER_reports_isolation_it_did_not_read() -> None:
    """A note and a core set are mutually exclusive — no silent empty answer.

    On this node `/proc/cmdline` carries neither `isolcpus=` nor `nohz_full=`, so
    the note is non-empty and the set MUST be empty. Reporting `frozenset()` with
    no note would let a caller read 'nothing is isolated' as 'isolation was
    checked and is fine'.
    """
    cores, note = core_map.isolated_cores()

    if note:
        assert cores == frozenset(), f"a note plus cores {sorted(cores)} is incoherent"
        assert str(core_map.PROC_CMDLINE) in note, note
    else:
        assert cores, "an empty set with no note is the unreadable answer"


def test_slice_cpuset_returns_EITHER_cores_OR_a_reason_never_a_silent_empty() -> None:
    """`(frozenset(), "")` is the one return this function must never make."""
    cores, error = core_map.slice_cpuset()

    if error:
        assert cores == frozenset(), f"cores {sorted(cores)} beside an error"
        assert str(core_map.TRADING_SLICE_CPUSET) in error, error
    else:
        assert cores, "an empty cpuset with no error is unreadable"


# --- ARC 028 / 0.1: the census must not depend on how it was INVOKED -------
#
# The defect these three controls exist for was measured, not reasoned about:
# `python -m pytest -q -k reserved_cores` gave `4 failed, 12 passed` while
# `./.venv/bin/python -m pytest -q -k reserved_cores` gave `16 passed` against
# byte-identical bytes on the same box in the same minute. Every argv token of
# the first spelling is a bare word, `_mentions_home` refuses to resolve bare
# words against the cwd, and so the census could not see its own author.
#
# NOTHING under `~/nix` is written by any of these. The subject is a short-lived
# child, killed in a `finally`, and the readers are read-only.

#: Sleeps and holds so the parent has a live `/proc/<pid>` to attribute. Takes
#: no path argument, deliberately: a path argument is the very thing whose
#: absence is under test.
_BARE_CHILD = "import time; time.sleep(float(__import__('sys').argv[1]))"

#: A child that ANNOUNCES itself before sleeping. The announcement is the
#: synchronisation: a byte on stdout can only be written by a process that has
#: already exec'd and started running, so a reader that has it holds proof of
#: both — no polling, no deadline, nothing to flip under scheduler noise.
_READY_CHILD = (
    "import sys, time; sys.stdout.write('R'); sys.stdout.flush(); "
    "time.sleep(float(sys.argv[1]))"
)


def _await_ready(child: subprocess.Popen[bytes]) -> None:
    """Block until the child has exec'd AND started running, on its own word.

    **`_await_exec` cannot answer this question when the child's image equals the
    parent's, and that is ARC 029 / 0.1's second finding.** Its docstring already
    names the window — `Popen` returns between the fork and the exec, and in that
    window `/proc/<pid>/exe` is still the PARENT's image — but it treats the image
    as a discriminator. For a venv-interpreter child spawned by a venv-interpreter
    test runner the two images are THE SAME FILE, so the wait is satisfied before
    the fork has finished and every `/proc` read that follows may land in the
    pre-exec window.

    MEASURED, and it is not theoretical: the new complementary control read
    `/proc/<pid>/cmdline` as `''` in 4 of 5 full-file runs while passing in
    isolation. The same window makes the neighbouring venv control pass for the
    WRONG REASON — its premise is `_mentions_home(...) is False`, and an empty
    cmdline satisfies that vacuously, which is a premise that cannot fail.

    A byte on stdout removes the race rather than widening a timeout: only a
    process that has replaced its image and begun executing can write it.
    """
    assert child.stdout is not None, "the child was not given a stdout pipe"
    readable, _, _ = select.select([child.stdout], [], [], CHILD_TIMEOUT_S)
    if not readable:
        raise AssertionError(
            f"child {child.pid} never announced itself within {CHILD_TIMEOUT_S}s "
            f"(rc={child.poll()})"
        )
    token = child.stdout.read(1)
    if token != b"R":
        raise AssertionError(
            f"child {child.pid} announced {token!r}, not b'R' — it did not reach "
            "the program it was given"
        )


def _venv_python() -> Path:
    python = REPO / ".venv" / "bin" / "python"
    if not python.is_file():
        pytest.skip(f"no venv interpreter at {python}")
    return python


def _await_exec(child: subprocess.Popen[bytes], expected_image: Path) -> None:
    """Block until the child has actually EXEC'd, or fail naming what it is.

    `Popen` returns between the fork and the exec, and in that window the
    child's `/proc/<pid>/exe` is still the PARENT's image. A control that read
    `/proc` in that window would be measuring this test runner and would flip
    with scheduler noise — the `/bin/bash` control below would intermittently
    see a Python image and pass for the wrong reason. Waiting on the image
    itself is the direct measurement; a `sleep` would be the proxy.
    """
    deadline = time.monotonic() + CHILD_TIMEOUT_S
    while time.monotonic() < deadline:
        # pylint: disable-next=protected-access
        if core_map._image_of(child.pid) == expected_image:
            return
        assert child.poll() is None, f"child exited before exec: rc={child.poll()}"
        time.sleep(CHILD_POLL_S)
    # pylint: disable-next=protected-access
    seen = core_map._image_of(child.pid)
    raise AssertionError(
        f"child {child.pid} never exec'd {expected_image} within "
        f"{CHILD_TIMEOUT_S}s — /proc/<pid>/exe reads {seen}"
    )


def test_a_VENV_CHILD_with_NO_PATH_TOKEN_in_argv_is_STILL_attributed_to_nix() -> None:
    """The regression control for the invocation-spelling dependence.

    `argv[0]` is the bare word `python` — exactly what an activated venv puts in
    `/proc/<pid>/cmdline` — so the argv predicate MUST miss it. If the census
    finds it anyway, it found it on a property of the process rather than on a
    property of how somebody typed it.
    """
    python = _venv_python()
    expected_image = python.resolve(strict=True)
    env = dict(os.environ)
    env["VIRTUAL_ENV"] = str(REPO / ".venv")
    with subprocess.Popen(  # nosec - literal argv, explicit executable, no shell
        ["python", "-c", _READY_CHILD, "30"],
        executable=str(python),
        env=env,
        cwd="/",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as child:
        try:
            # `_await_ready`, not `_await_exec`: this child's image is the SAME
            # FILE as the test runner's, so the image wait is satisfied in the
            # pre-exec window and the premise below could read an empty cmdline
            # and pass vacuously (ARC 029 / 0.1, measured).
            _await_ready(child)
            assert core_map._image_of(child.pid) == expected_image, (  # pylint: disable=protected-access
                "the child is not running the venv interpreter"
            )
            cmdline = core_map._cmdline_of(child.pid)  # pylint: disable=protected-access

            # The premise of the test, asserted rather than assumed: this child
            # really is invisible to the argv predicate — and it is a REAL argv,
            # not an unreadable one.
            assert cmdline, "cmdline read back empty — the premise below is vacuous"
            assert (
                core_map._mentions_home(  # pylint: disable=protected-access
                    child.pid, cmdline, REPO
                )
                is False
            ), (
                f"the argv predicate matched {cmdline!r} — this child was "
                "supposed to carry no path token, so the control below would "
                "have passed without the venv predicate existing"
            )

            found, _ = core_map.nix_processes(REPO)
            assert child.pid in {process.pid for process in found}, (
                f"pid {child.pid} runs {python} with cmdline {cmdline!r} and the "
                "census did not attribute it to Nix — the verdict is a function "
                "of the invocation spelling, not of the process"
            )
        finally:
            child.kill()


def test_the_PROC_EXE_predicate_does_NOT_cover_the_venv_and_that_is_MEASURED() -> None:
    """Banked disproof: `/proc/exe` was written for this case and misses it.

    `~/nix/.venv/bin/python` is a SYMLINK, so the kernel records the system
    interpreter and `_image_under` is False for every Python process in the
    tree. Without this control, a later reader would delete `_runs_tree_venv` as
    redundant with `_image_under` and re-open the defect silently.

    **DRIVEN AGAINST A CONSTRUCTED CHILD, and the previous spelling is ARC 029 /
    0.1's opening finding.** It read the AMBIENT process — `os.getpid()` — and so
    asked its question of whatever interpreter happened to be running the suite.
    `_runs_tree_venv` is defined on `VIRTUAL_ENV`, which the ambient process
    carries only when the venv was ACTIVATED, while the test's own precondition
    was `sys.executable.startswith(REPO)`, which does not imply it. MEASURED,
    byte-identical tree, same commit:

        source .venv/bin/activate && python -m pytest   ->  PASSES
        ./.venv/bin/python -m pytest                    ->  FAILS

    **That is the ARC 028 defect this very predicate was written to remove — a
    verdict that is a function of the invocation spelling — reintroduced in the
    control rather than in the code.** And it failed on the spelling where the
    census is perfectly healthy: with an absolute-path argv, `_mentions_home`
    attributes the process and `nix_processes` sees itself. Measured, all three
    spellings, against the union:

        absolute path, unactivated   mentions_home=True   venv=False   SEEN
        activated, bare `python`     mentions_home=False  venv=True    SEEN
        venv on PATH, unactivated    mentions_home=False  venv=False   BLIND

    The third row is a real residual blindness and is recorded as CHECK-DEBT
    D3.101 rather than repaired here — no `/proc` fact distinguishes it, which is
    why D1.42 (join the units to `nix-trading.slice`) is its honest closure.

    Every other control in this file already drives a constructed child with an
    explicit environment; this one was the exception. D3.100's general rule, one
    layer along: an instrument whose input is the ambient state measures the
    ambient state, not the property.
    """
    python = _venv_python()
    expected_image = python.resolve(strict=True)
    env = dict(os.environ)
    # The activated spelling, CONSTRUCTED rather than inherited — this is the
    # whole repair. The predicate's precondition is now stated by the test that
    # depends on it, instead of being borrowed from how pytest was launched.
    env["VIRTUAL_ENV"] = str(REPO / ".venv")
    with subprocess.Popen(  # nosec - literal argv, explicit executable, no shell
        ["python", "-c", _READY_CHILD, "30"],
        executable=str(python),
        env=env,
        cwd="/",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as child:
        try:
            _await_ready(child)

            # The disproof itself: the kernel's image for a venv interpreter is
            # the SYSTEM binary, outside the tree, so `_image_under` cannot see
            # this process and `_runs_tree_venv` is not redundant with it.
            image = core_map._image_of(child.pid)  # pylint: disable=protected-access
            assert image is not None, "/proc/<pid>/exe could not be read"
            assert image == expected_image, (
                f"the child's image is {image}, not the {expected_image} the venv "
                "interpreter resolves to — this control is measuring something else"
            )
            assert image.is_relative_to(REPO) is False, (
                f"/proc/<pid>/exe is {image}, INSIDE {REPO} — the venv "
                "interpreter has stopped being a symlink out of the tree, so "
                "this disproof no longer holds and _runs_tree_venv should be "
                "re-examined"
            )
            assert (
                core_map._image_under(child.pid, REPO)  # pylint: disable=protected-access
                is False
            ), "the image predicate claimed a process it is documented to miss"

            assert core_map._runs_tree_venv(  # pylint: disable=protected-access
                child.pid, REPO
            ), "the predicate that is supposed to cover this case does not"
        finally:
            child.kill()


def test_the_VENV_PREDICATE_needs_VIRTUAL_ENV_and_the_ARGV_ONE_COVERS_ITS_GAP() -> None:
    """The two predicates are COMPLEMENTARY, and that is asserted, not assumed.

    ARC 029 / 0.1. `_runs_tree_venv` returns False for the tree's own interpreter
    invoked by absolute path without activation — correctly, since `VIRTUAL_ENV`
    is how it distinguishes the tree's venv from any other process sharing the
    system image. What makes that safe is `_mentions_home` catching the same
    process by its argv, and the census unioning the two.

    Pinned because the repair above could otherwise be read as "the venv
    predicate is unreliable" and reverted toward something that attributes on the
    shared system image alone — which would sweep every unrelated `python3.14` on
    the node into a core census.
    """
    python = _venv_python()
    expected_image = python.resolve(strict=True)
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    with subprocess.Popen(  # nosec - literal argv, absolute path, no shell
        [str(python), "-c", _READY_CHILD, "30"],
        env=env,
        cwd="/",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as child:
        try:
            _await_ready(child)
            assert core_map._image_of(child.pid) == expected_image, (  # pylint: disable=protected-access
                "the child is not running the venv interpreter"
            )
            cmdline = core_map._cmdline_of(child.pid)  # pylint: disable=protected-access
            assert cmdline, "cmdline read back empty — the assertions below are vacuous"

            assert (
                core_map._runs_tree_venv(  # pylint: disable=protected-access
                    child.pid, REPO
                )
                is False
            ), (
                "the venv predicate claimed a process with no VIRTUAL_ENV — it "
                "has degraded to attributing on the shared system image"
            )
            assert core_map._mentions_home(  # pylint: disable=protected-access
                child.pid, cmdline, REPO
            ), f"the argv predicate lost {cmdline!r}, which names a path in the tree"

            found, _ = core_map.nix_processes(REPO)
            assert child.pid in {process.pid for process in found}, (
                f"pid {child.pid} is the tree's own interpreter and the census "
                "did not attribute it — the union has lost a member"
            )
        finally:
            child.kill()


def test_VIRTUAL_ENV_ALONE_does_NOT_make_a_SHELL_a_nix_process() -> None:
    """The over-attribution control: both kernel facts are required.

    An operator who runs `activate` exports `VIRTUAL_ENV` into every child,
    including their shell. A predicate resting on that variable alone would
    sweep the operator's `bash` into a core census, which is precisely the
    hazard `_mentions_home`'s bare-word rule exists to prevent.
    """
    shell = Path("/bin/bash")
    if not shell.exists():
        pytest.skip("no /bin/bash on this node")
    expected_image = shell.resolve(strict=True)
    env = dict(os.environ)
    env["VIRTUAL_ENV"] = str(REPO / ".venv")
    with subprocess.Popen(  # nosec - literal argv, no shell interpolation
        [str(shell), "-c", "sleep 30"],
        env=env,
        cwd="/",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as child:
        try:
            _await_exec(child, expected_image)
            assert (
                core_map._runs_tree_venv(  # pylint: disable=protected-access
                    child.pid, REPO
                )
                is False
            ), (
                f"pid {child.pid} is {shell} with VIRTUAL_ENV set and the venv "
                "predicate claimed it — the predicate has degraded to 'anything "
                "started from an activated shell'"
            )
        finally:
            child.kill()
