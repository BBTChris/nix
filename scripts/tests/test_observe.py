"""ARC 025 C1 — the runtime resource observer, and the vocabulary it compares with.

Every test here drives the REAL observer in a REAL child process against a REAL
socket or file. Nothing is stubbed: an observer proven against a mock of itself
would be `check_datafeed_granted_mode`'s D3.16 rebuilt in a new file.
"""
# pylint: disable=invalid-name,redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test; `listener` is a fixture reused by
# name. Both deliberate, so the pragma is per-file and named.

from __future__ import annotations

import socket
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixverify.observe import (  # pylint: disable=wrong-import-position
    _Recorder,
    covers,
    format_address,
    observe_check,
    resolve_fd,
    undeclared,
)

_TEMPLATE = '''"""Planted check."""
from nixverify.contract import CheckResult, Status

DEPENDS_ON = ()
RESOURCES = {resources}


def run(mode, ctx):
    """Planted body."""
{body}
    return CheckResult(name="{name}", status=Status.PASS, evidence="planted")
'''


def plant(checks_dir: Path, name: str, body: str, resources: str = "()") -> None:
    """Write a synthetic check whose run() does exactly `body`."""
    checks_dir.mkdir(parents=True, exist_ok=True)
    indented = "\n".join(f"    {line}" for line in body.strip().splitlines())
    (checks_dir / f"{name}.py").write_text(
        _TEMPLATE.format(resources=resources, body=indented, name=name),
        encoding="utf-8",
    )


@pytest.fixture
def listener() -> Iterator[int]:
    """A REAL listening TCP socket on loopback. Yields its port."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def test_a_reachable_connect_is_observed_as_a_socket_claim(
    tmp_path: Path, listener: int
) -> None:
    """The base case: a real connect to a real listener becomes a canonical claim."""
    plant(
        tmp_path / "checks",
        "check_dial",
        f"import socket\n"
        f"s = socket.create_connection(('127.0.0.1', {listener}), timeout=5)\n"
        f"s.close()",
    )
    run = observe_check(tmp_path / "checks", "check_dial", tmp_path)
    assert run.measured, run.error
    assert f"socket:127.0.0.1:{listener}" in run.claims, run.claims
    assert run.unreachable == (), "a reachable endpoint must not be marked unreachable"


def test_a_REFUSED_connect_is_STILL_an_observed_claim_and_is_marked_unreachable(
    tmp_path: Path,
) -> None:
    """THE MASKED-HAZARD PRIMITIVE. The attempt IS the claim; the errno is separate.

    ARC 024 measured both Gateway gates dialling 127.0.0.1:4002 while the Gateway
    was DOWN. An observer that only recorded successful connects would have seen
    two gates that touched nothing and reported a serene green over D1.41. So the
    audit hook — which fires BEFORE the syscall — supplies the claim, and the
    outcome wrapper supplies the reason it could not be followed further.
    """
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()  # nothing is listening now

    plant(
        tmp_path / "checks",
        "check_dead_dial",
        f"import socket\n"
        f"try:\n"
        f"    socket.create_connection(('127.0.0.1', {port}), timeout=2)\n"
        f"except OSError:\n"
        f"    pass",
    )
    run = observe_check(tmp_path / "checks", "check_dead_dial", tmp_path)
    assert run.measured, run.error
    assert f"socket:127.0.0.1:{port}" in run.claims, (
        "a connect that was REFUSED is still a claim on that endpoint — the port "
        "being dead today says nothing about tomorrow"
    )
    assert (f"127.0.0.1:{port}", "ECONNREFUSED") in run.unreachable, run.unreachable


def test_file_WRITES_are_observed_and_file_READS_are_not(tmp_path: Path) -> None:
    """The stated scope of the file class, proven in both directions."""
    readable = tmp_path / "already-here.txt"
    readable.write_text("x", encoding="utf-8")
    target = tmp_path / "written.txt"
    plant(
        tmp_path / "checks",
        "check_io",
        f"from pathlib import Path\n"
        f"Path({str(readable)!r}).read_text(encoding='utf-8')\n"
        f"Path({str(target)!r}).write_text('y', encoding='utf-8')",
    )
    run = observe_check(tmp_path / "checks", "check_io", tmp_path)
    assert run.measured, run.error
    assert f"file-write:{target}" in run.claims, run.claims
    assert f"file-write:{readable}" not in run.claims, (
        "a read is not a contended claim and must not be reported as one"
    )


def test_os_open_write_flags_are_observed_even_without_a_mode_string(
    tmp_path: Path,
) -> None:
    """`os.open` supplies flags and no mode. A check writing that way is not invisible."""
    target = tmp_path / "raw.txt"
    plant(
        tmp_path / "checks",
        "check_raw",
        f"import os\n"
        f"fd = os.open({str(target)!r}, os.O_WRONLY | os.O_CREAT)\n"
        f"os.close(fd)",
    )
    run = observe_check(tmp_path / "checks", "check_raw", tmp_path)
    assert f"file-write:{target}" in run.claims, run.claims


def test_subprocesses_are_observed(tmp_path: Path) -> None:
    """A check that shells out claims the program it spawns."""
    plant(
        tmp_path / "checks",
        "check_spawn",
        "import subprocess\n"
        "subprocess.run(['/bin/true'], check=False, capture_output=True)",
    )
    run = observe_check(tmp_path / "checks", "check_spawn", tmp_path)
    assert "subprocess:/bin/true" in run.claims, run.claims


def test_module_level_side_effects_are_OUTSIDE_the_observation_window(
    tmp_path: Path, listener: int
) -> None:
    """Observation is armed after import, so the import is not the check's claim.

    Stated in observe.py and proven here: a socket opened at module level belongs
    to the ENGINE's hazard (loader imports it), not to the check's declared claims.
    """
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "check_eager.py").write_text(
        f"import socket\n"
        f"from nixverify.contract import CheckResult, Status\n"
        f"DEPENDS_ON = ()\n"
        f"RESOURCES = ()\n"
        f"_s = socket.create_connection(('127.0.0.1', {listener}), timeout=5)\n"
        f"_s.close()\n"
        f"def run(mode, ctx):\n"
        f'    return CheckResult(name="check_eager", status=Status.PASS, evidence="e")\n',
        encoding="utf-8",
    )
    run = observe_check(checks, "check_eager", tmp_path)
    assert run.measured, run.error
    assert run.claims == (), run.claims


def test_a_check_that_RAISES_is_unmeasured_but_keeps_the_claims_it_made(
    tmp_path: Path, listener: int
) -> None:
    """Partial observation is never reported as clean observation."""
    plant(
        tmp_path / "checks",
        "check_boom",
        f"import socket\n"
        f"socket.create_connection(('127.0.0.1', {listener}), timeout=5).close()\n"
        f"raise RuntimeError('planted')",
    )
    run = observe_check(tmp_path / "checks", "check_boom", tmp_path)
    assert not run.measured
    assert "planted" in run.error
    assert f"socket:127.0.0.1:{listener}" in run.claims


def test_a_TIMEOUT_is_unmeasured_never_clean(tmp_path: Path) -> None:
    """A check that never returns has UNOBSERVED resource use, not none."""
    plant(tmp_path / "checks", "check_hang", "import time\ntime.sleep(30)")
    run = observe_check(tmp_path / "checks", "check_hang", tmp_path, timeout=1.0)
    assert not run.measured
    assert "timed out" in run.error
    assert "UNOBSERVED" in run.error


def test_a_check_that_will_not_import_is_unmeasured(tmp_path: Path) -> None:
    """An unimportable check yields an error, never an empty claim set."""
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "check_broken.py").write_text("this is not python\n", encoding="utf-8")
    run = observe_check(checks, "check_broken", tmp_path)
    assert not run.measured
    assert "check_broken" in run.error


# --- the vocabulary: the one place this gate could be quietly weakened -------


def test_covers_venv_matches_paths_under_the_venv_only(tmp_path: Path) -> None:
    """`venv` is the token check_venv and check_python_deps already use."""
    assert covers("venv", f"subprocess:{tmp_path}/.venv/bin/python3", tmp_path)
    assert covers("venv", f"file-write:{tmp_path}/.venv/pyvenv.cfg", tmp_path)
    assert not covers("venv", f"subprocess:{tmp_path}/scripts/x", tmp_path)
    assert not covers("venv", "socket:127.0.0.1:4002", tmp_path)


def test_covers_journal_matches_the_syslog_socket_and_the_journal_tools(
    tmp_path: Path,
) -> None:
    """`journal` is check_verify_logging's declared token."""
    assert covers("journal", "unix-socket:/dev/log", tmp_path)
    assert covers("journal", "subprocess:/usr/bin/journalctl", tmp_path)
    assert not covers("journal", "unix-socket:/tmp/other.sock", tmp_path)
    assert not covers("journal", "subprocess:/usr/bin/git", tmp_path)


def test_covers_port_token_matches_any_host_on_that_port(tmp_path: Path) -> None:
    """`port:4002` is the spelling the disjointness tests already use."""
    assert covers("port:4002", "socket:127.0.0.1:4002", tmp_path)
    assert not covers("port:4002", "socket:127.0.0.1:4001", tmp_path)
    assert not covers("port:4002", "subprocess:/usr/bin/git", tmp_path)


def test_covers_network_token_matches_remote_hosts_and_NOT_loopback(
    tmp_path: Path,
) -> None:
    """`network:pypi` must not silently cover a loopback broker session."""
    assert covers("network:pypi", "socket:151.101.0.223:443", tmp_path)
    assert not covers("network:pypi", "socket:127.0.0.1:4002", tmp_path)
    assert not covers("network:pypi", "socket:::1:4002", tmp_path)


def test_covers_file_write_token_resolves_a_RELATIVE_declaration_against_nix_home(
    tmp_path: Path,
) -> None:
    """A declaration must read the same on this box and the next one."""
    assert covers("file-write:checks", f"file-write:{tmp_path}/checks/.ctl", tmp_path)
    assert not covers("file-write:checks", f"file-write:{tmp_path}/logs/x", tmp_path)


def test_an_UNRECOGNISED_declared_token_matches_by_exact_equality_ONLY(
    tmp_path: Path,
) -> None:
    """Guessing what a novel token was meant to cover is how a gate becomes a stamp."""
    assert covers("whatever-i-invented", "whatever-i-invented", tmp_path)
    assert not covers("whatever-i-invented", "socket:127.0.0.1:4002", tmp_path)
    assert not covers("", "socket:127.0.0.1:4002", tmp_path)


def test_undeclared_reports_exactly_the_claims_no_token_accounts_for(
    tmp_path: Path,
) -> None:
    """The finding, isolated from the gate that reports it."""
    claims = ("socket:127.0.0.1:4002", f"subprocess:{tmp_path}/.venv/bin/python3")
    assert undeclared(claims, ("venv",), tmp_path) == ("socket:127.0.0.1:4002",)
    assert undeclared(claims, ("venv", "port:4002"), tmp_path) == ()
    assert undeclared(claims, (), tmp_path) == claims


def test_format_address_is_total_over_the_address_families_it_may_meet() -> None:
    """A hook that raised would turn an observation into a defect in the observed."""
    assert format_address(("127.0.0.1", 4002)) == ("socket", "127.0.0.1:4002")
    assert format_address("/dev/log") == ("unix-socket", "/dev/log")
    assert format_address(b"/dev/log") == ("unix-socket", "/dev/log")
    assert format_address(None)[0] == "socket"


# ===========================================================================
# CHECK-DEBT D3.118 — `dir_fd`-relative targets (ARC 031 / 0.4)
# ===========================================================================
#
# The defect, measured by ARC 030 sub-agent B and reproduced here as the first
# test below: `tempfile.TemporaryDirectory.__exit__` goes through
# `shutil.rmtree`, which on Linux takes CPython's TOCTOU-safe fd-relative
# strategy and unlinks each entry as `os.unlink(entry.name, dir_fd=parent_fd)`.
# The PEP 578 event fires with that literal `(basename, dir_fd)` pair, so the
# recorded claim was `file-write:sample.py` — a bare fixture basename with no
# path segment any `file-write:<root>` declaration's prefix check can match.
# Two checks were held FAIL by it, and the only cheap repair was a literal
# per-filename token, which is the anchor doctrine C.4 forbids.
#
# These tests are the can-fail for the repair: each drives the REAL observer,
# in a real child process where possible, and asserts BOTH that the resolved
# absolute path appears AND that the bare basename does not.


def test_a_TemporaryDirectory_teardown_records_ABSOLUTE_paths_not_basenames(
    tmp_path: Path,
) -> None:
    """D3.118's exact reproduction, in the direction that discharges it."""
    plant(
        tmp_path / "checks",
        "check_tempdir",
        "import pathlib\n"
        "import tempfile\n"
        "with tempfile.TemporaryDirectory(prefix='nix-d3118-') as tmp:\n"
        "    (pathlib.Path(tmp) / 'sample.py').write_text('x=1\\n')\n"
        "    (pathlib.Path(tmp) / 'sub').mkdir()",
        resources='("file-write:/tmp",)',
    )
    run = observe_check(tmp_path / "checks", "check_tempdir", tmp_path)
    assert run.measured, run.error
    assert "file-write:sample.py" not in run.claims, (
        "the bare basename is D3.118 itself — a claim no honest "
        f"file-write:<root> declaration can cover: {run.claims}"
    )
    assert "file-write:sub" not in run.claims, run.claims
    removed = [c for c in run.claims if c.endswith("/sample.py")]
    assert removed, f"the unlinked entry was not recorded at all: {run.claims}"
    assert all(c.startswith("file-write:/tmp/nix-d3118-") for c in removed), removed
    assert undeclared(run.claims, ("file-write:/tmp",), tmp_path) == (), (
        "the whole point of the repair: an ORDINARY, non-literal "
        "file-write:/tmp declaration now accounts for every teardown claim"
    )


def test_the_dir_fd_ARGUMENT_INDEX_is_right_for_each_event_shape(
    tmp_path: Path,
) -> None:
    """`os.remove(path, dir_fd)` vs `os.mkdir(path, mode, dir_fd)`.

    The index differs per event and a single wrong entry silently reads a
    MODE as a descriptor. Driven at the recorder, because a real
    `os.mkdir(..., dir_fd=...)` cannot be provoked from a plant reliably —
    the argument tuple is the thing under test, so it is supplied exactly.
    """
    import os  # pylint: disable=import-outside-toplevel

    fd = os.open(str(tmp_path), os.O_RDONLY)
    try:
        recorder = _Recorder()
        recorder.armed = True
        recorder.hook("os.remove", ("gone.py", fd))
        recorder.hook("os.rmdir", ("gonedir", fd))
        recorder.hook("os.mkdir", ("made", 0o777, fd))
        recorder.hook("os.rename", ("from", "to", fd, fd))
    finally:
        os.close(fd)
    assert recorder.lost == 0, "a lost claim is indistinguishable from no claim"
    root = str(tmp_path)
    assert f"file-write:{root}/gone.py" in recorder.claims, recorder.claims
    assert f"file-write:{root}/gonedir" in recorder.claims, recorder.claims
    assert f"file-write:{root}/made" in recorder.claims, (
        "os.mkdir's dir_fd is args[2]; reading args[1] would resolve the MODE "
        f"(0o777) as a descriptor: {recorder.claims}"
    )
    assert f"file-write:{root}/to" in recorder.claims, (
        "a rename's DESTINATION is the write — it destroys whatever was "
        f"there: {recorder.claims}"
    )
    assert f"file-write:{root}/from" in recorder.claims, recorder.claims


def test_os_truncate_by_FILE_DESCRIPTOR_is_observed(tmp_path: Path) -> None:
    """`os.truncate(fd, length)` — the one mutator whose subject IS a descriptor.

    Previously dropped outright (`isinstance(path, int)` returned early), which
    made `multiprocessing.shared_memory`'s own `ftruncate` sizing invisible.
    """
    target = tmp_path / "sized.bin"
    plant(
        tmp_path / "checks",
        "check_truncate",
        f"import os\n"
        f"fd = os.open({str(target)!r}, os.O_RDWR | os.O_CREAT)\n"
        f"os.truncate(fd, 0)\n"
        f"os.close(fd)",
    )
    run = observe_check(tmp_path / "checks", "check_truncate", tmp_path)
    assert run.measured, run.error
    assert f"file-write:{target}" in run.claims, run.claims


def test_resolve_fd_is_TOTAL_over_a_descriptor_that_is_not_open() -> None:
    """The residual, named: an unresolvable fd yields '' and never raises."""
    assert resolve_fd(999_999) == ""
    assert resolve_fd(-1) == ""


def test_an_UNRESOLVABLE_dir_fd_FALLS_BACK_rather_than_losing_the_claim() -> None:
    """A dropped claim is worse than a weak one — it looks like no claim at all."""
    recorder = _Recorder()
    recorder.armed = True
    recorder.hook("os.remove", ("orphan.py", 999_999))
    assert recorder.lost == 0, recorder.lost
    assert "file-write:orphan.py" in recorder.claims, recorder.claims


def test_an_ABSOLUTE_target_ignores_a_dir_fd_that_is_also_supplied(
    tmp_path: Path,
) -> None:
    """`os.remove('/abs/x', dir_fd=fd)` is an absolute path; joining would corrupt it."""
    import os  # pylint: disable=import-outside-toplevel

    fd = os.open(str(tmp_path), os.O_RDONLY)
    try:
        recorder = _Recorder()
        recorder.armed = True
        recorder.hook("os.remove", ("/etc/hostname", fd))
    finally:
        os.close(fd)
    assert "file-write:/etc/hostname" in recorder.claims, recorder.claims


def test_covers_shm_matches_dev_shm_and_nothing_else(tmp_path: Path) -> None:
    """The `shm` token, unknown to the vocabulary until D3.118's truncate arm.

    Three checks have declared `shm` since ARC 021 and the table had no rule
    for it, so it matched by exact string equality only — invisible while
    `os.ftruncate`'s fd-relative event carried no path at all.
    """
    assert covers("shm", "file-write:/dev/shm/nix_ring_gate_1_a", tmp_path)
    assert covers("shm", "file-write:/dev/shm", tmp_path)
    assert not covers("shm", "file-write:/dev/shmem/x", tmp_path), (
        "a prefix rule that matched /dev/shmem would be a rubber stamp"
    )
    assert not covers("shm", f"file-write:{tmp_path}/x", tmp_path)
    assert not covers("shm", "socket:127.0.0.1:4002", tmp_path)
