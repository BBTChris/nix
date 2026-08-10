"""Pin conformance per VERIFY-AND-CHECKS.md §7."""

import json
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


def test_declares_disruptive_because_repair_swaps_the_order_placing_client() -> None:
    """Task 9 review, Finding 1: repair() reinstalls ib_async — a package
    swap is exactly §4's definition of disruptive. The engine (not this
    check) is what keeps it inspectable at boot despite this (§8)."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.disruptive is True
