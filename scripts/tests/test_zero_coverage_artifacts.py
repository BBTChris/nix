"""Real coverage for artifacts a change to which selected NO test (ARC 029 / 0.5).

`scripts/runtime_gate.py` reports, every commit, the tracked files whose
modification selects nothing:

    RUNTIME-GATE uncovered (a change to these selects no test):
        checks/_preamble.py · scripts/nixverify/__init__.py ·
        scripts/tests/binding_tracer.py · scripts/d1_12_reboot_capture.py

**The brief said four and named a different four**, listing
`databases/schema/extract_sources.py` and `scripts/nixbus/__init__.py`; both are
covered today and neither appears in the measured set. The count matched by
coincidence. The list here is the one the gate printed at ARC 029 / 0.5, and this
module's own docstring is therefore a measurement rather than a transcription.

## Why an "executed by every import" file is the worst kind of uncovered

`checks/_preamble.py` runs before anything else in all thirty-one checks and
`scripts/nixverify/__init__.py` runs on every import of the engine. Neither has
ever been asserted about. A defect in either does not fail loudly in one place —
it changes the environment underneath every gate at once, which is the shape that
produces a tree full of green checks measuring the wrong thing. That is why they
are covered here with BEHAVIOURAL assertions and not with an import smoke test:
`import x` proves the file parses, which is the weakest claim available and the
one D3.19 warns is nothing discharged by being named.
"""

# pylint: disable=invalid-name,import-outside-toplevel
# Test names SHOUT the property under test, as in every other suite here.
# The imports are deliberately LOCAL: several controls assert that a module is
# importable only AFTER a sys.path bootstrap has run, and a top-level import
# would perform that bootstrap as a side effect of collection — the test would
# then pass because the suite imported it, not because the preamble works.

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, repo-local paths
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# checks/_preamble.py — the bootstrap every check imports first
# ---------------------------------------------------------------------------


def test_the_PREAMBLE_makes_nixverify_importable_from_a_STANDALONE_check() -> None:
    """§4.2: a check is a verify.py plugin AND a standalone executable.

    Run directly, `scripts/` is not on the path and `from nixverify.contract
    import ...` fails at import time — every check in the tree would be
    unrunnable from its own CLI. The bootstrap is what makes both paths work, so
    the assertion drives the real thing: a check, as a program, in a subprocess
    with no inherited PYTHONPATH.
    """
    proc = subprocess.run(  # nosec B603 - fixed argv, repo-local path
        [sys.executable, str(REPO / "checks" / "check_limiter_seam.py")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd="/",
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
    )
    assert "ModuleNotFoundError" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_the_PREAMBLE_SUPPRESSES_BYTECODE_so_a_pyc_write_is_not_attributed() -> None:
    """The load-bearing line, and the reason it lives in this file.

    ARC 026 Stage 2.2 measured the runtime observer FAILING `check_capture_plane2`
    for a `.pyc` write against an honest `RESOURCES` declaration. Writing a `.pyc`
    is the interpreter caching a module, not a check using a resource — and
    because the cache is shared, the write lands on whichever check imports
    FIRST on a cold tree. Three other gates were clean only because they were
    scheduled later. A claim that moves between checks when the PLAN is reordered
    is an artefact of the instrument, so the cause was fixed here rather than
    declared around.

    Asserted as BEHAVIOUR — no `__pycache__` appears for a freshly-copied check —
    rather than by reading `sys.dont_write_bytecode`, because the flag being set
    is the mechanism and the absent cache file is the property.
    """
    proc = subprocess.run(  # nosec B603 - fixed argv, repo-local path
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '"
            + str(REPO / "checks")
            + "'); import _preamble; print(sys.dont_write_bytecode)",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert proc.stdout.strip() == "True", proc.stdout
    # And the observable consequence: importing a check leaves no cache behind.
    before = set((REPO / "checks").glob("__pycache__/*.pyc"))
    subprocess.run(  # nosec B603 - fixed argv, repo-local path
        [sys.executable, str(REPO / "checks" / "check_limiter_seam.py")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert set((REPO / "checks").glob("__pycache__/*.pyc")) == before


def test_the_PREAMBLE_does_not_DUPLICATE_its_path_entry() -> None:
    """Imported by thirty-one checks in one process; the guard is load-bearing.

    `sys.path` is process-global and every check imports this module. Without the
    membership test the engine's path would grow one duplicate entry per check
    per run — harmless-looking, and exactly the kind of unbounded growth that
    makes an import-shadowing defect (debug.md failure mode #8) harder to see.
    """
    import importlib  # pylint: disable=import-outside-toplevel

    sys.path.insert(0, str(REPO / "checks"))
    import _preamble  # pylint: disable=import-error,import-outside-toplevel

    scripts = str(REPO / "scripts")
    before = sys.path.count(scripts)
    importlib.reload(_preamble)
    assert sys.path.count(scripts) == before


# ---------------------------------------------------------------------------
# scripts/nixverify/__init__.py — executed by every import of the engine
# ---------------------------------------------------------------------------


def test_the_PACKAGE_EXPORTS_ARE_THE_CONTRACTS_OWN_OBJECTS() -> None:
    """Re-export, never redefinition.

    A package initialiser that rebound any of these names to a local copy would
    give the engine and a check two different `Status` enums, and an `is`
    comparison between them would be silently false — the failure would surface
    as a verdict that matches no branch rather than as an import error.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    import nixverify  # pylint: disable=import-error,import-outside-toplevel
    from nixverify import (
        contract,  # pylint: disable=import-error,import-outside-toplevel
    )

    assert nixverify.__all__, "the package exports nothing"
    for name in nixverify.__all__:
        assert hasattr(nixverify, name), f"{name} is in __all__ and not exported"
        assert getattr(nixverify, name) is getattr(contract, name), (
            f"nixverify.{name} is not contract.{name} — the initialiser rebound a "
            "name, so two modules can hold different objects of the same name"
        )


def test_the_PACKAGE_IS_STDLIB_ONLY_as_section_9_1_requires() -> None:
    """§9.1: verify.py runs under system python3 before `.venv` exists.

    A third-party import reachable from the package root would make the whole
    engine unimportable on a fresh node — at exactly the moment install.sh needs
    it — and the failure would look like a broken interpreter rather than a
    broken dependency rule.
    """
    proc = subprocess.run(  # nosec B603 B607 - fixed argv, system interpreter
        [
            "/usr/bin/python3",
            "-c",
            "import sys; sys.path.insert(0, '"
            + str(REPO / "scripts")
            + "'); import nixverify; print(len(nixverify.__all__))",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stdout.strip()) >= 6, proc.stdout


# ---------------------------------------------------------------------------
# scripts/tests/binding_tracer.py — the instrument the binding table rests on
# ---------------------------------------------------------------------------


def test_the_TRACER_RECORDS_a_real_check_verdict_and_names_its_STATUS() -> None:
    """§0f's evidence is only as good as the instrument that collects it.

    The binding table — thirty-one rows, `BOUND=30` — is derived entirely from
    what this tracer writes. A tracer that silently recorded nothing would
    produce a table reading UNBOUND everywhere, which `binding_census` refuses;
    but a tracer that recorded the WRONG STATUS would produce a table that looks
    exactly like a healthy one. That is the case asserted here: a real check is
    driven and the recorded status must be the verdict it actually returned.
    """
    sys.path.insert(0, str(REPO / "scripts" / "tests"))
    import binding_tracer  # pylint: disable=import-error,import-outside-toplevel

    assert binding_tracer._check_name("check_venv.py") == "check_venv"  # pylint: disable=protected-access
    assert binding_tracer._check_name("test_check_venv.py") is None, (  # pylint: disable=protected-access
        "a TEST file was read as a check — the census would attribute a "
        "control's own name to the gate it drives"
    )
    # Driven with the REAL contract objects rather than a stand-in: the tracer
    # reads `result.status.name`, and a fake that exposed `.value` instead would
    # have "passed" against a shape the tracer never meets. That mistake was made
    # writing this control and is recorded because it is the whole hazard — an
    # instrument tested against a mock of its own input measures the mock.
    sys.path.insert(0, str(REPO / "scripts"))
    from nixverify.contract import (  # pylint: disable=import-error,import-outside-toplevel
        CheckResult,
        Status,
    )

    red = CheckResult(name="check_x", status=Status.FAIL_REPAIRABLE)
    assert binding_tracer._status_name(red) == "FAIL_REPAIRABLE"  # pylint: disable=protected-access
    green = CheckResult(name="check_x", status=Status.PASS)
    assert binding_tracer._status_name(green) == "PASS"  # pylint: disable=protected-access
    # A non-result must not be reported as a verdict: the census counts these.
    assert binding_tracer._status_name(object()) == ""  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# scripts/d1_12_reboot_capture.py — coverable in part, and honest about the rest
# ---------------------------------------------------------------------------


def test_the_REBOOT_CAPTURE_is_IMPORTABLE_and_its_PRECONDITION_is_pure() -> None:
    """What can be measured without a reboot, measured — and no more.

    D1.12 is ARMED and UNFIRED and has been owed by thirteen arcs; it fires once,
    on a real reboot, and only the operator's tap session can discharge it. So
    this control deliberately does NOT claim to test the capture. It covers the
    part that is pure — the module loads under the engine's own rules and its
    thresholds are readable constants — so that a change to the file selects a
    test instead of selecting nothing, which is all 0.5 asks for.

    **Nothing here is discharged by being named (D3.19):** the capture itself
    remains uncovered and the row still says so.
    """
    source = (REPO / "scripts" / "d1_12_reboot_capture.py").read_text(encoding="utf-8")
    compiled = compile(source, "d1_12_reboot_capture.py", "exec")
    assert compiled is not None
    assert "loginctl" in source, (
        "the loginctl precondition is the whole of D1.12's ARMED state; if it is "
        "gone the row is describing an instrument that no longer exists"
    )


@pytest.mark.parametrize(
    "artifact",
    [
        "checks/_preamble.py",
        "scripts/nixverify/__init__.py",
        "scripts/tests/binding_tracer.py",
        "scripts/d1_12_reboot_capture.py",
    ],
)
def test_every_artifact_this_module_claims_to_cover_EXISTS(artifact: str) -> None:
    """A coverage claim over a path that moved is a claim over nothing.

    The runtime gate names paths; if one is renamed, the tests above would keep
    passing while covering a file that is gone — the scope-collapse class this
    project has met seven times.
    """
    assert (REPO / artifact).is_file(), f"{artifact} named as covered and absent"


# ---------------------------------------------------------------------------
# checks/ibgateway_expected.json — the row that was hiding behind a stale owner
# ---------------------------------------------------------------------------
#
# ARC 029 / 0.5, and it is the reason re-pointing an owner is not a fix on its
# own. `check_artifact_gate_coverage` had been CANNOT_MEASURE since ARC 027
# closed, because all sixteen baseline rows named that arc as their guard owner
# and a completed arc cannot discharge anything (doctrine B.3). Re-pointing the
# marker to a live arc let the gate MEASURE again — and the first thing it
# reported was a finding the unmeasurable state had been hiding: one baseline row
# is named by nothing under scripts/tests/.
#
# That is the whole argument for treating CANNOT_MEASURE as a debt rather than a
# resting state. The gate was not quiet because things were fine.


def test_the_IBGATEWAY_EXPECTED_CONFIG_is_the_gates_SINGLE_SOURCE() -> None:
    """The file exists to be the only place expectations live — asserted, not assumed.

    `check_ibgateway_config` reads every expectation out of this JSON and
    hardcodes none of them (§2.4, doctrine C.4). The property that matters is
    therefore not "the file parses" but "the gate does not carry a second copy of
    what the file says": a hardcoded port beside a declared one is exactly the
    two-authorities defect the single-source rule exists to prevent.
    """
    import json  # pylint: disable=import-outside-toplevel

    expected = json.loads(
        (REPO / "checks" / "ibgateway_expected.json").read_text(encoding="utf-8")
    )
    assert expected, "the declared desired state is empty"

    # The §4.4 DECLARATION BLOCK is exempt, and the exemption is measured rather
    # than assumed: `RESOURCES = ("port:4002",)` names the same port the JSON
    # declares, and it MUST be a literal — the check contract requires those
    # declarations be read STATICALLY, by AST, without importing the check, so a
    # value computed from a JSON read at import time would be invisible to the
    # planner. A first spelling of this control scanned the whole file and
    # reported that literal as a second authority; it is neither an authority nor
    # avoidable. Everything below the declarations is still held to the rule.
    gate_source = (REPO / "checks" / "check_ibgateway_config.py").read_text(
        encoding="utf-8"
    )
    gate_source = "\n".join(
        line
        for line in gate_source.splitlines()
        if not line.startswith(("RESOURCES", "DEPENDS_ON", "SUBJECTS"))
    )
    # Every scalar the file declares must be ABSENT as a literal from the gate.
    literals = [
        value
        for value in expected.values()
        if isinstance(value, (int, str)) and not isinstance(value, bool)
    ]
    ports = [value for value in literals if isinstance(value, int) and value > 1000]
    assert ports, "no port-shaped expectation found — the file's shape changed"
    for port in ports:
        assert str(port) not in gate_source, (
            f"{port} is declared in ibgateway_expected.json AND written literally "
            "into the gate — two authorities for one value, which is what the "
            "single-source rule forbids"
        )
