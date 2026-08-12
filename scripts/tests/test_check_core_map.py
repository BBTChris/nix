"""ARC 026 C1/C4 — the standing gate over §10's core map as RUNNING STATE.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. A demonstration missing the last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8). Every plant builds a
miniature `nix_home` under `tmp_path` — a `.venv/bin/python3` symlink to the real
interpreter and a `scripts/capture.py` that pins wherever the plant wants — and
points the gate's `Context` at it. The real `scripts/capture.py` is never edited
and the real tree is only ever READ.

**Every control asserts the REASON** — the site or the named condition — never
the exit code alone (check contract v2 §11). And no test in this file ever calls
`pin_self` on the pytest process itself: a test that pinned its own runner would
confine the whole session to one core, which is an instrument changing the
machine it is measuring.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access
# `protected-access`: a can-fail control drives the gate's ARMS, which are
# private by design — an arm made public so a test could reach it would be a
# surface the gate did not need, invented for the test. Doctrine C.8 says the
# plant must not touch the production artifact; it does not say the test may
# only use the public API.
# pylint: disable=duplicate-code
# Test names SHOUT the property; fixtures are reused by design; the sys.path
# bootstrap forces late imports. Each deliberate, so the pragma is named.

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_core_map as gate  # pylint: disable=wrong-import-position
from nixbus.core_map import Role  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_core_map.py"

#: A `capture.py` stand-in. `{cores}` is what it pins to; `{honour_no_pin}` is
#: whether `--no-pin` is respected, which is how the CONTROL arm is planted
#: against. It prints the same first-line JSON the real one does, because that
#: contract — a PID on stdout, then hold — is what the gate depends on.
FAKE_CAPTURE = """\
import json, os, sys, time
cores = {cores!r}
if "--no-pin" not in sys.argv or not {honour_no_pin!r}:
    os.sched_setaffinity(0, cores)
mask = sorted(os.sched_getaffinity(os.getpid()))
print(json.dumps({{"pid": os.getpid(), "role": "capture", "pinned": True,
                   "syscall": mask, "procfs": mask, "agree": True, "error": ""}}),
      flush=True)
hold = 0.0
if "--hold-s" in sys.argv:
    hold = float(sys.argv[sys.argv.index("--hold-s") + 1])
time.sleep(hold)
"""


def _plant_home(tmp_path: Path, *, cores: set[int], honour_no_pin: bool = True) -> Path:
    """Build a miniature nix_home whose `capture.py` pins to `cores`."""
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True, exist_ok=True)
    (home / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (home / ".venv" / "bin" / "python3").symlink_to(Path(sys.executable).resolve())
    (home / "scripts" / "capture.py").write_text(
        FAKE_CAPTURE.format(cores=sorted(cores), honour_no_pin=honour_no_pin),
        encoding="utf-8",
    )
    return home


def _run(home: Path):
    """Drive the gate against a planted home."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate measures the real tree and really measures it.
# --------------------------------------------------------------------------


def test_the_REAL_capture_py_is_measured_and_reports_the_KERNELS_mask() -> None:
    """The unplanted gate passes, and its evidence names both kernel readers."""
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail
    assert "sched_getaffinity=1" in result.evidence, result.evidence
    assert "Cpus_allowed_list=1" in result.evidence, result.evidence


def _code_strings(path: Path) -> list[str]:
    """Every string literal in a module EXCEPT its docstrings.

    Docstrings are excluded because this gate's docstring quotes the very
    spellings the test forbids, in the course of explaining why it does not read
    them. A prose mention is not a read; a string literal in the code is one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_the_gate_reads_NO_configuration_file_anywhere() -> None:
    """The named failure mode, refuted structurally rather than by assertion.

    A core-affinity gate that reads the unit file or a JSON config is measuring
    intent. This gate cannot: no CODE string in it names one.
    """
    literals = _code_strings(GATE_FILE)
    for forbidden in ("AllowedCPUs", "systemctl", ".json", "/etc/systemd"):
        offenders = [text for text in literals if forbidden in text]
        assert not offenders, f"{forbidden} reached the affinity gate: {offenders}"


def test_the_measurement_is_of_ANOTHER_process_not_of_the_gate_itself() -> None:
    """The subject is a spawned PID, so the gate never reports on state it wrote."""
    home = REPO
    child = gate._run_child(home, pin=True)
    assert child.pid, child.error
    assert child.pid != __import__("os").getpid(), "the gate measured itself"
    assert child.reading is not None and child.reading.mask == {1}, child.reading


# --------------------------------------------------------------------------
# PLANT 1 — the process pins to the WRONG core.
# --------------------------------------------------------------------------


def test_a_process_pinned_OFF_ITS_SPEC_CORE_fails_and_NAMES_the_site(
    tmp_path: Path,
) -> None:
    """The headline can-fail: §10 assigns capture.py core 1 and it took core 3."""
    home = _plant_home(tmp_path, cores={3})
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "scripts/capture.py:pin_self(Role.CAPTURE)" in result.site, result.site
    assert "§10 assigns capture.py core 1" in result.detail, result.detail
    assert "Cpus_allowed_list=3" in result.detail, result.detail


def test_UNPLANTING_the_wrong_core_restores_PASS_on_the_same_population(
    tmp_path: Path,
) -> None:
    """The plant removed, the same miniature home passes. Step three of §5.1."""
    home = _plant_home(tmp_path, cores={3})
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / "scripts" / "capture.py").write_text(
        FAKE_CAPTURE.format(cores=[1], honour_no_pin=True), encoding="utf-8"
    )
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail


def test_a_process_pinned_to_an_OFF_MAP_core_fails_and_NAMES_it(
    tmp_path: Path,
) -> None:
    """Cores 6-19 are assigned by nothing in §10; landing there is a finding."""
    home = _plant_home(tmp_path, cores={7})
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "Cpus_allowed_list=7" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — the CONTROL arm, which is what makes arm 1 falsifiable.
# --------------------------------------------------------------------------


def test_a_CONTROL_that_reads_THE_SAME_MASK_fails_and_says_why_it_is_vacuous(
    tmp_path: Path,
) -> None:
    """If an unpinned run reads core 1 too, the reading carries no information.

    Planted by a `capture.py` that ignores `--no-pin` — i.e. a world in which
    every process is on core 1 whatever it asked for. The gate must refuse to
    call that a pass.
    """
    home = _plant_home(tmp_path, cores={1}, honour_no_pin=False)
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "CONTROL" in result.site, result.site
    assert "carry no information" in result.detail, result.detail


def test_UNPLANTING_the_control_defect_restores_PASS(tmp_path: Path) -> None:
    """Honour `--no-pin` again and the same home passes."""
    home = _plant_home(tmp_path, cores={1}, honour_no_pin=False)
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / "scripts" / "capture.py").write_text(
        FAKE_CAPTURE.format(cores=[1], honour_no_pin=True), encoding="utf-8"
    )
    assert _run(home).status is Status.PASS


# --------------------------------------------------------------------------
# PLANT 3 — the slice's kernel cpuset denies a core the map assigns.
# --------------------------------------------------------------------------


def test_a_SLICE_that_denies_a_spec_core_fails_and_NAMES_the_cpuset_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cgroup enforces 0-3 while §10 assigns 0-5."""
    monkeypatch.setattr(gate, "slice_cpuset", lambda: (frozenset({0, 1, 2, 3}), ""))
    result = _run(_plant_home(tmp_path, cores={1}))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "cpuset.cpus.effective" in result.site, result.site
    assert "denied by the cgroup" in result.detail, result.detail
    assert "4-5" in result.detail, result.detail


def test_an_UNREADABLE_slice_is_CANNOT_MEASURE_not_PASS(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 10: a property proven while its subject is unavailable is not proven."""
    monkeypatch.setattr(
        gate, "slice_cpuset", lambda: (frozenset(), "cgroup absent on this node")
    )
    result = _run(_plant_home(tmp_path, cores={1}))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "cgroup absent on this node" in result.detail, result.detail


# --------------------------------------------------------------------------
# The gate refuses to look, loudly, rather than passing.
# --------------------------------------------------------------------------


def test_a_MISSING_venv_interpreter_is_CANNOT_MEASURE_and_NAMES_the_path(
    tmp_path: Path,
) -> None:
    """A home with no interpreter cannot spawn the subject, and says so."""
    (tmp_path / "scripts").mkdir()
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert ".venv/bin/python3" in result.detail, result.detail


def test_a_CHILD_THAT_PRINTS_NOTHING_is_CANNOT_MEASURE_and_NAMES_the_cause(
    tmp_path: Path,
) -> None:
    """No PID means no `/proc` to read, which is not the same as a clean box."""
    home = _plant_home(tmp_path, cores={1})
    (home / "scripts" / "capture.py").write_text("import sys\n", encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "printed nothing" in result.detail, result.detail


def test_ISOLATION_is_reported_and_never_claimed() -> None:
    """§10's isolcpus column is not in effect here, and the gate must say so."""
    result = _run(REPO)
    assert "ISOLATION NOT CLAIMED" in result.evidence, result.evidence


# --------------------------------------------------------------------------
# Orchestration declarations and the actuation surface.
# --------------------------------------------------------------------------


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_venv",)
    assert declaration.resources == ("subprocess:python3", "cpu-affinity")
    assert "scripts/capture.py" in declaration.subjects


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "another process's scheduler state" in combined, combined


def test_the_MAP_ITSELF_comes_from_the_spec_and_not_from_this_gate() -> None:
    """Directive 3: one source of truth. §10's rows live in `core_map`, not here."""
    assert gate.SPEC_ASSIGNED[Role.CAPTURE] == frozenset({1})
    assert "SPEC_ASSIGNED = " not in GATE_FILE.read_text(encoding="utf-8")
