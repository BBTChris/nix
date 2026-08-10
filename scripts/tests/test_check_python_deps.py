"""Pin conformance per nix_check_contract.md §7."""

import json
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"


def _run(mode: Mode, home: Path):
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    return loaded.run(mode, Context(nix_home=home, mode=mode))


def test_real_venv_satisfies_the_real_pins() -> None:
    """PASS against this repo's own real venv, with evidence recorded."""
    result = _run(Mode.VERIFY, REPO)
    assert result.status is Status.PASS
    assert "ib_async" in result.evidence


def test_pins_file_lists_ib_async_at_the_arc_008_version() -> None:
    """The pins file, not this test, is the single source of truth (§7)."""
    pins = json.loads((CHECKS / "pinned_deps.json").read_text(encoding="utf-8"))
    assert pins["packages"]["ib_async"] == "2.1.0"


def test_wrong_version_fails_and_names_the_package(  # pylint: disable=unused-argument
    tmp_path: Path,
) -> None:
    """§7: drift from the pin is a defect the check must name specifically.

    `tmp_path` is unused: `evaluate()` is pure and needs no filesystem, but
    the signature is kept as specified by task-9-brief.md rather than
    silently trimmed.
    """
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    result = mod.evaluate({"ib_async": "2.1.0"}, {"ib_async": "2.0.1"})
    assert result.status is Status.FAIL_REPAIRABLE
    assert "ib_async" in result.site
    assert "2.0.1" in result.detail


def test_absent_package_fails_and_names_it() -> None:
    """A missing package is drift too, not a silent pass."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    result = mod.evaluate({"ib_async": "2.1.0"}, {})
    assert result.status is Status.FAIL_REPAIRABLE
    assert "ib_async" in result.site


def test_matching_pin_passes_with_evidence() -> None:
    """§5: PASS carries non-empty evidence naming what was measured."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    result = mod.evaluate({"ib_async": "2.1.0"}, {"ib_async": "2.1.0"})
    assert result.status is Status.PASS
    assert "2.1.0" in result.evidence


def test_query_failure_is_cannot_measure_not_absent(tmp_path: Path) -> None:
    """Task 9 review, Finding 2 (§4.1): a subprocess that cannot answer must
    never collapse into 'nothing is installed' — that would send --correct
    into an unattended reinstall against a defect that may not exist.

    The fake interpreter is a real, executable file that always exits
    nonzero, so `installed_versions()` genuinely cannot parse a version
    list out of it — this is not a mock standing in for the failure, it is
    the failure.
    """
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_python.chmod(0o755)

    result = _run(Mode.VERIFY, tmp_path)

    assert result.status is Status.CANNOT_MEASURE


def test_load_pins_rejects_malformed_entries(tmp_path: Path) -> None:
    """Minor finding: pinned_deps.json feeds this check's `pip install` argv
    directly and install.sh's deliberately-unquoted `$PINS` shell expansion
    (§7). A package name starting with `-` or a version with a space/glob
    character would corrupt one side's argv and word-split/glob the other.
    """
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    (tmp_path / "pinned_deps.json").write_text(
        json.dumps({"packages": {"-evil": "1.0.0"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="-evil"):
        mod.load_pins(tmp_path)


def _expected_print_pins() -> str:
    """What `--print-pins` must emit, DERIVED from the pins file.

    ARC 015: these two tests previously hardcoded "ib_async==2.1.0", which restated a
    mutable fact the pins file owns (CLAUDE.md directive 3) — so adding the
    pytest-asyncio pin broke two tests that were not measuring anything about
    pytest-asyncio. Deriving keeps them honest: the assertion is about the FORMAT and
    ORDERING install.sh's `$PINS` expansion depends on, and about the output covering
    every declared pin, neither of which weakens when a pin is added.

    Non-vacuity: `test_pins_file_lists_ib_async_at_the_arc_008_version` above is the test
    that pins the actual version, and it still hardcodes on purpose. Deriving here does
    not leave the version unasserted anywhere.
    """
    pins = json.loads((CHECKS / "pinned_deps.json").read_text(encoding="utf-8"))
    return "\n".join(
        f"{name.lower()}=={version}"
        for name, version in sorted(pins["packages"].items())
    )


def test_print_pins_emits_validated_specs_one_per_line() -> None:
    """Task 9 review round 2, Finding A: install.sh must consume this
    output rather than re-parsing pinned_deps.json itself, so the pins
    guard actually reaches the shell-side `$PINS` expansion it was written
    to protect (§7). One implementation, one validator, one source.
    """
    proc = subprocess.run(
        [sys.executable, str(CHECKS / "check_python_deps.py"), "--print-pins"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    expected = _expected_print_pins()
    assert proc.stdout.strip() == expected
    # The shape install.sh relies on, asserted independently of the contents: one
    # `name==version` spec per line, no blanks, no stray whitespace to word-split on.
    lines = proc.stdout.strip().splitlines()
    assert lines == sorted(lines)
    assert all(line.count("==") == 1 and " " not in line for line in lines), lines
    assert len(lines) >= 2, "pins collapsed to fewer than the two declared packages"


def test_print_pins_works_under_system_python_with_no_venv() -> None:
    """install.sh runs before .venv exists (§9.1-adjacent): this mode must
    not need anything beyond stdlib, or install.sh could never call it."""
    proc = subprocess.run(
        ["/usr/bin/python3", str(CHECKS / "check_python_deps.py"), "--print-pins"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == _expected_print_pins()


def test_pins_file_lists_pytest_asyncio() -> None:
    """ARC 015 Part 3: the query verbs became coroutines, so the suite that drives them
    needs pytest-asyncio — and anything the venv must contain is pinned here or
    check_python_deps cannot see it drift (§7)."""
    pins = json.loads((CHECKS / "pinned_deps.json").read_text(encoding="utf-8"))
    assert pins["packages"]["pytest-asyncio"] == "1.4.0"


def test_declares_disruptive_because_repair_swaps_the_order_placing_client() -> None:
    """Task 9 review, Finding 1: repair() reinstalls ib_async — a package
    swap is exactly §4's definition of disruptive. The engine (not this
    check) is what keeps it inspectable at boot despite this (§8)."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.disruptive is True
