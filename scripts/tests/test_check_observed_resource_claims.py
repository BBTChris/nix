"""ARC 025 C1 — the standing gate over OBSERVED vs DECLARED resource claims.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. A demonstration missing the last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8): every population here
is built under `tmp_path`. The one test that reads the real tree only READS it.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=duplicate-code
# Test names SHOUT the property; `listener` is a reused fixture; the sys.path
# bootstrap forces late imports. Each deliberate, so the pragma is named.

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note: a
# front insertion would let a future `checks/` sibling shadow a stdlib module.
sys.path.append(str(REPO / "checks"))

import check_observed_resource_claims as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
    exit_code_for,
)
from nixverify.declarations import read_all  # pylint: disable=wrong-import-position
from nixverify.observe import ObservedRun  # pylint: disable=wrong-import-position
from test_observe import plant  # pylint: disable=wrong-import-position

GATE_FILE = REPO / "checks" / "check_observed_resource_claims.py"


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


def _population(home: Path, count: int = 6) -> Path:
    """A credible synthetic check population that claims nothing and says so."""
    checks = home / "checks"
    for index in range(count):
        plant(checks, f"check_quiet_{index}", "pass", resources="()")
    # One check that genuinely claims something and declares it, so the gate has
    # a live comparison and the run is never vacuously clean.
    plant(
        checks,
        "check_honest",
        "import subprocess\n"
        "subprocess.run(['/bin/true'], check=False, capture_output=True)",
        resources="('subprocess:/bin/true',)",
    )
    (checks / "registry.json").write_text(
        json.dumps({"blocks": [{"name": "all", "checks": ["check_honest"]}]}),
        encoding="utf-8",
    )
    return checks


def _run(home: Path):
    """Drive the gate in-process against a synthetic home."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _cli(home: Path) -> subprocess.CompletedProcess[str]:
    """Drive the gate through its own CLI, which is what an operator runs."""
    return subprocess.run(
        [sys.executable, str(GATE_FILE), str(home)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


# --- NON-VACUITY, BEFORE ANY PLANT (doctrine C.3, §5.3) ---------------------


def test_NONVACUITY_the_gates_scope_contains_the_real_registered_population() -> None:
    """The scope must contain the subjects, or a green means nothing.

    Doctrine C.3's incident: a rule inherited a scope that made it structurally
    unable to see the file it was written about, and would have passed forever.
    So this asserts the gate's own subject list — derived from the checks FOLDER,
    the direction that can see an orphan — really contains the two gates whose
    collision opened D1.41, and really excludes the gate itself.
    """
    subjects = sorted(name for name in read_all(REPO / "checks") if name != gate.NAME)
    assert "check_ibgateway_config" in subjects
    assert "check_ibgateway_service" in subjects
    assert gate.NAME not in subjects, (
        "the gate must never observe itself — the child would sweep again"
    )
    assert len(subjects) >= gate.MIN_CREDIBLE_CHECKS


def test_NONVACUITY_the_observer_actually_records_claims_on_the_real_tree() -> None:
    """Scope containment is not enough: the instrument must be armed on it.

    This is the live half. It asserts the gate's evidence reports a non-zero
    number of runtime claims against the real population, which is the same
    assertion `run()` makes on every invocation before it is allowed to report.

    STRENGTHENED ARC 026, AND THE OLD SPELLING WAS THE DEFECT THIS PROJECT KEEPS
    FINDING INSIDE ITS OWN INSTRUMENTS. It read
    `assert "0 runtime resource claim(s)" not in result.evidence` — a SUBSTRING
    test on a rendered number. It went RED the first time the real population
    recorded **20** claims, because "20 runtime resource claim(s)" contains
    "0 runtime resource claim(s)". The assertion was correct for one decade of
    counts and silently wrong for the next, and it would equally have passed a
    genuine zero rendered any other way. The number is now PARSED and compared,
    which is what the assertion always meant.
    """
    result = _run(REPO)
    recorded = re.search(r"(\d+) runtime resource claim\(s\)", result.evidence)
    assert recorded, result.evidence
    assert int(recorded.group(1)) > 0, result.evidence
    assert result.status is not Status.PASS or result.evidence


# --- THE PLANT: FAIL, NAMING CHECK AND ENDPOINT ------------------------------


def test_PLANT_an_undeclared_socket_FAILS_naming_the_check_AND_the_endpoint(
    tmp_path: Path, listener: int
) -> None:
    """D2.27's residual, caught: `RESOURCES = ()` beside a real connect."""
    checks = _population(tmp_path)
    plant(
        checks,
        "check_leaky",
        f"import socket\n"
        f"socket.create_connection(('127.0.0.1', {listener}), timeout=5).close()",
        resources="()",
    )
    result = _run(tmp_path)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"check_leaky:socket:127.0.0.1:{listener}" in result.site, result.site
    assert "check_leaky" in result.detail
    assert f"socket:127.0.0.1:{listener}" in result.detail
    assert "false declaration" in result.detail


def test_CONTROL_declaring_the_same_endpoint_turns_that_FAIL_into_a_PASS(
    tmp_path: Path, listener: int
) -> None:
    """§5.1 step 6. Without this, the gate is only shown able to fail."""
    checks = _population(tmp_path)
    plant(
        checks,
        "check_leaky",
        f"import socket\n"
        f"socket.create_connection(('127.0.0.1', {listener}), timeout=5).close()",
        resources=f"('port:{listener}',)",
    )
    result = _run(tmp_path)
    assert result.status is Status.PASS, result
    assert "runtime resource claim(s) recorded" in result.evidence


def test_the_CLI_exits_1_and_prints_the_check_and_the_endpoint(
    tmp_path: Path, listener: int
) -> None:
    """The demonstrated FAIL path an operator actually sees — not the code alone.

    ARC 024's re-verify control initially passed because the subprocess CRASHED
    and also returned 1, so the exit code is asserted TOGETHER with the site.
    """
    checks = _population(tmp_path)
    plant(
        checks,
        "check_leaky",
        f"import socket\n"
        f"socket.create_connection(('127.0.0.1', {listener}), timeout=5).close()",
        resources="()",
    )
    proc = _cli(tmp_path)
    assert proc.returncode == exit_code_for(Status.FAIL_NEEDS_OPERATOR) == 1, (
        proc.stderr
    )
    combined = proc.stdout + proc.stderr
    assert "check_leaky" in combined, combined
    assert f"socket:127.0.0.1:{listener}" in combined, combined


# --- THE MASKED-HAZARD CLAUSE ------------------------------------------------


def test_MASKED_HAZARD_an_unreachable_subject_is_CANNOT_MEASURE_and_never_PASS(
    tmp_path: Path,
) -> None:
    """**A SAFETY PROPERTY PROVEN WHILE ITS SUBJECT IS UNAVAILABLE IS NOT PROVEN.**

    The planted check declares the port it dials, so its declaration is TRUE for
    everything the observer saw — the tempting verdict is PASS. It must not be.
    The connect was REFUSED, so every line of that check after the connect did
    not execute, and whatever it would have claimed there is unobserved. This is
    the Gateway situation on this box exactly: both gates get ECONNREFUSED, and
    an observer that called that clean would report green over D1.41.
    """
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()

    checks = _population(tmp_path)
    plant(
        checks,
        "check_masked",
        f"import socket\n"
        f"try:\n"
        f"    socket.create_connection(('127.0.0.1', {port}), timeout=2)\n"
        f"except OSError:\n"
        f"    pass",
        resources=f"('port:{port}',)",
    )
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "check_masked" in result.detail
    assert f"127.0.0.1:{port}" in result.detail
    assert "ECONNREFUSED" in result.detail
    assert "UNOBSERVED" in result.detail
    assert exit_code_for(result.status) == 2


def test_MASKED_HAZARD_holds_against_the_REAL_gateway_gates_on_this_box() -> None:
    """The clause, proven on its real subject rather than only on a synthetic.

    The IB Gateway is down here. Both Gateway gates dial 127.0.0.1:4002 and both
    get ECONNREFUSED — the ARC 024 one-off spy's measurement, now standing. This
    asserts the gate reports them as unobservable and names the endpoint. If the
    Gateway ever comes up this test is expected to change verdict, which is the
    point: the gate's answer is a function of reality, not of its own opinion.
    """
    from nixverify.observe import observe_check

    checks = REPO / "checks"
    for name in ("check_ibgateway_config", "check_ibgateway_service"):
        observed = observe_check(checks, name, REPO)
        assert "socket:127.0.0.1:4002" in observed.claims, (
            f"{name} was not observed dialling 4002 — either the gate changed or "
            "the observer went blind; both need a human"
        )
        if not observed.unreachable:
            pytest.skip(f"{name} reached 4002 — the Gateway is UP on this box")
        findings = gate.classify(observed, read_all(checks)[name], REPO)
        assert [f.verdict for f in findings] == [gate.UNKNOWN], findings
        assert "4002" in findings[0].reason
        assert "not proven" in findings[0].reason


def test_a_positively_undeclared_claim_OUTRANKS_masking(tmp_path: Path) -> None:
    """Order is the ruling: direct evidence of a false declaration beats a shrug.

    A check that was caught dialling an endpoint it did not declare has been
    caught, whether or not something else about the run was unobservable.
    """
    observed = ObservedRun(
        check="check_x",
        claims=("socket:127.0.0.1:4002",),
        unreachable=(("127.0.0.1:4002", "ECONNREFUSED"),),
    )
    declaration = read_all(REPO / "checks")["check_venv"]  # declares ('venv',)
    findings = gate.classify(observed, declaration, tmp_path)
    assert [f.verdict for f in findings] == [gate.FAIL], findings


# --- THE §7.12 CLOSURES, EACH PROVEN FIRING ---------------------------------


def test_an_UNDECLARED_check_is_CANNOT_MEASURE_and_never_PASS(tmp_path: Path) -> None:
    """You cannot call a statement false when none was made — but nor is it clean."""
    checks = _population(tmp_path)
    (checks / "check_mute.py").write_text(
        "from nixverify.contract import CheckResult, Status\n"
        "import subprocess\n"
        "DEPENDS_ON = ()\n"
        "def run(mode, ctx):\n"
        "    subprocess.run(['/bin/true'], check=False, capture_output=True)\n"
        '    return CheckResult(name="check_mute", status=Status.PASS, evidence="e")\n',
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "check_mute declares no RESOURCES" in result.detail
    assert "subprocess:/bin/true" in result.detail


def test_a_DISARMED_observer_is_CANNOT_MEASURE_not_a_clean_population(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 closure 1, proven FIRING rather than asserted.

    Zero claims across the whole population is the signature of an observer that
    is not observing, and it reads identically to a population that touches
    nothing. The gate must refuse to tell them apart.
    """
    _population(tmp_path)
    monkeypatch.setattr(
        gate,
        "observe_check",
        lambda checks_dir, name, home, **kw: ObservedRun(check=name),
    )
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "ZERO claims" in result.detail
    assert "disarmed observer" in result.detail


def test_a_TINY_population_is_CANNOT_MEASURE(tmp_path: Path) -> None:
    """§7.12 closure 2: an empty checks/ must not read as 'nothing undeclared'."""
    plant(tmp_path / "checks", "check_only", "pass")
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "credibility floor" in result.detail


def test_an_UNMEASURED_observation_is_a_finding_never_an_absence(
    tmp_path: Path,
) -> None:
    """§7.12 closure 5: a child that dies must not vanish from the report."""
    findings = gate.classify(
        ObservedRun(check="check_x", error="observation timed out after 60.0s"),
        read_all(REPO / "checks")["check_venv"],
        tmp_path,
    )
    assert [f.verdict for f in findings] == [gate.UNKNOWN]
    assert "timed out" in findings[0].reason


# --- THE CO-SCHEDULING ARM ---------------------------------------------------


def test_this_gate_FAILS_if_the_registry_puts_it_in_a_PARALLEL_block(
    tmp_path: Path,
) -> None:
    """Its real claim is the union of everything it re-executes, so it runs alone.

    Declared as one opaque token because the union cannot be a literal without
    restating the population; the hazard that declaration would have prevented is
    measured here instead. Co-scheduled with the Gateway gates, this gate's child
    would dial 4002 beside them — D1.41 reintroduced by the instrument built to
    catch it.
    """
    checks = _population(tmp_path)
    (checks / "registry.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "name": "reckless",
                        "parallel": True,
                        "checks": [gate.NAME, "check_honest"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "registry.json:reckless" in result.site
    assert "re-executes every registered check" in result.detail


def test_a_SEQUENTIAL_block_containing_this_gate_is_fine(tmp_path: Path) -> None:
    """The control for the arm above — it must not always fire."""
    checks = _population(tmp_path)
    (checks / "registry.json").write_text(
        json.dumps(
            {"blocks": [{"name": "fine", "checks": [gate.NAME, "check_honest"]}]}
        ),
        encoding="utf-8",
    )
    assert gate._coscheduling_defect(tmp_path) is None  # pylint: disable=protected-access


# --- DECLARATION CONFORMANCE -------------------------------------------------


# --- BOTH DOCUMENTED LAUNCH MODES (ARC 032, CHECK-DEBT D3.140) ---------------
#
# The plant here is D3.140's own mechanism, reproduced under tmp_path: a check
# that spawns `sys.executable` and declares `subprocess:python`. `covers`
# matches a subprocess token by BASENAME, so that declaration is TRUE under
# `.venv/bin/python` and FALSE under `/usr/bin/python3` — the same tree, the
# same commit, opposite verdicts, decided by nothing but the launch.

_SPAWNS_ITS_OWN_INTERPRETER = (
    "import subprocess, sys\n"
    "subprocess.run([sys.executable, '-c', 'pass'], check=False, capture_output=True)"
)


def _launch_mode_paths(home: Path) -> dict[str, str]:
    """What each documented launch mode's interpreter reports itself to be.

    Asked of the interpreters rather than assumed from the paths, for the same
    reason the gate asks: a venv `python` reports a different `sys.executable`
    from the path used to launch it whenever the tree is a linked worktree, and
    an assertion against the requested path would be testing the wrong string.
    """
    from nixverify.observe import documented_interpreters

    reported = {}
    for label, path in documented_interpreters(home):
        proc = subprocess.run(
            [path, "-c", "import sys; sys.stdout.write(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 0, f"{label} ({path}) would not run: {proc.stderr}"
        reported[label] = proc.stdout.strip()
    return reported


def test_PLANT_a_declaration_TRUE_under_ONE_interpreter_and_FALSE_under_the_OTHER(
    tmp_path: Path,
) -> None:
    """D3.140's condition, planted, driven through the SHIPPED run(), and RED.

    The declaration is not wrong under every launch mode — that is the whole
    point, and it is why one sweep passed this for as long as the gate did one
    sweep. The assertion is on the REASON (rule 11 / §18): the finding must name
    the interpreter it holds under AND the claim, and must NOT name the other
    interpreter, because a report that listed both would say the declaration is
    false under a launch mode where it is true.
    """
    modes = _launch_mode_paths(tmp_path)
    checks = _population(tmp_path)
    plant(
        checks,
        "check_split",
        _SPAWNS_ITS_OWN_INTERPRETER,
        resources="('subprocess:python',)",
    )
    result = _run(tmp_path)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"check_split:subprocess:{modes['system']}" in result.site, result.site
    assert "false declaration" in result.detail, result.detail
    assert f"subprocess:{modes['system']}" in result.detail, result.detail
    assert f"observed under: {modes['system']}" in result.detail, result.detail
    assert modes["venv"] not in result.detail, (
        "the finding claims the declaration is false under the venv launch mode "
        f"too, where it is TRUE: {result.detail}"
    )


def test_CONTROL_declaring_BOTH_interpreters_turns_that_FAIL_into_a_PASS(
    tmp_path: Path,
) -> None:
    """§5.1 step 6, and the proof the gate is not simply hostile to `subprocess:`.

    Same plant, same two sweeps, one token added. Without this the arm above
    shows only that the gate can go red.
    """
    checks = _population(tmp_path)
    plant(
        checks,
        "check_split",
        _SPAWNS_ITS_OWN_INTERPRETER,
        resources="('subprocess:python', 'subprocess:python3')",
    )
    result = _run(tmp_path)
    assert result.status is Status.PASS, result
    assert "2 DISTINCT documented launch mode(s)" in result.evidence, result.evidence


def test_a_finding_under_BOTH_launch_modes_names_BOTH(
    tmp_path: Path, listener: int
) -> None:
    """The merge's discriminating half: one line, both interpreters, not two lines.

    A declaration false under both is a different finding from one false under
    one, with a different repair. If `_merge` unioned nothing, this would render
    as two identical-looking lines and the distinction D3.140 is about would be
    invisible in the report.
    """
    modes = _launch_mode_paths(tmp_path)
    checks = _population(tmp_path)
    plant(
        checks,
        "check_leaky",
        f"import socket\n"
        f"socket.create_connection(('127.0.0.1', {listener}), timeout=5).close()",
        resources="()",
    )
    result = _run(tmp_path)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert result.site.count(f"check_leaky:socket:127.0.0.1:{listener}") == 1, (
        f"the same finding was reported once per sweep: {result.site}"
    )
    for path in modes.values():
        assert path in result.detail, (path, result.detail)


def test_a_MISSING_documented_interpreter_is_CANNOT_MEASURE_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 closure 7 / rule 10: one launch mode absent means one is UNMEASURED.

    The population here is otherwise clean, so the tempting verdict is PASS —
    which is precisely the verdict rule 10 forbids. A safety property proven
    while one of its two subjects is unavailable is not proven.
    """
    _population(tmp_path)
    absent = tmp_path / "no-such-interpreter"
    monkeypatch.setattr(
        gate,
        "documented_interpreters",
        lambda home: (("venv", sys.executable), ("system", str(absent))),
    )
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert str(absent) in result.detail, result.detail
    assert "UNAVAILABLE" in result.detail, result.detail
    assert "system launch mode" in result.detail, result.detail
    assert exit_code_for(result.status) == 2


def test_the_SAME_interpreter_TWICE_is_CANNOT_MEASURE_not_two_launch_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 closure 6 — the failure this whole arm exists to prevent.

    Two sweeps of one interpreter produce two identical passes and read exactly
    like a declaration proven under both launch modes. It is the manufactured
    input a "both interpreters" gate is easiest to build on, so the gate refuses
    it by name.
    """
    _population(tmp_path)
    monkeypatch.setattr(
        gate,
        "documented_interpreters",
        lambda home: (("venv", sys.executable), ("system", sys.executable)),
    )
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "SAME interpreter" in result.detail, result.detail
    assert sys.executable in result.detail, result.detail


def test_a_child_that_ran_under_a_DIFFERENT_interpreter_is_UNOBSERVED_for_that_mode() -> (
    None
):
    """An "I launched X" is not an "X ran" — D3.140's mechanism one level down.

    A unit over the pure comparison, in the same shape as
    `test_a_positively_undeclared_claim_OUTRANKS_masking` above: an interpreter
    that reports itself as something else cannot be planted without a wrapper
    that the launch-mode probe would itself catch first, so the mismatched
    record is supplied directly.
    """
    system = "/usr/bin/python3"
    mode = gate.LaunchMode(label="system", requested=system, reported=system)
    conformance = gate._interpreter_conformance  # pylint: disable=protected-access

    def observed(interpreter: str) -> ObservedRun:
        return ObservedRun(
            check="check_x",
            claims=("subprocess:/bin/true",),
            interpreter=interpreter,
        )

    findings = conformance([observed("/somewhere/else/python")], mode)
    assert [f.verdict for f in findings] == [gate.UNKNOWN], findings
    assert "/somewhere/else/python" in findings[0].reason
    assert system in findings[0].reason
    assert "UNOBSERVED" in findings[0].reason
    assert findings[0].site == "check_x:system"

    assert not conformance([observed(system)], mode), (
        "the arm fires on a child that DID run under the mode"
    )


def test_this_gates_own_declarations_are_literals_the_AST_reader_can_read() -> None:
    """§4.4: a declaration that must be executed to be read is not a declaration."""
    declaration = read_all(REPO / "checks")[gate.NAME]
    assert declaration.errors == (), declaration.errors
    assert declaration.resources == gate.RESOURCES
    assert declaration.time_bound is True
    assert declaration.expected_s == gate.TOTAL_BUDGET_S
    assert declaration.correctable is False
    assert declaration.non_correctable_reason.strip()
    assert "scripts/nixverify/observe.py" in declaration.subjects
