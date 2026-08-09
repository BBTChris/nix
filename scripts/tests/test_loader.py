"""Plugin loading isolation per VERIFY-AND-CHECKS.md §9.3-§9.4."""

from pathlib import Path

from nixverify.loader import load_check


def _plugin(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_import_failure_becomes_a_load_error_not_a_crash(tmp_path: Path) -> None:
    """§9.3-9.4: the check that installs a missing package must survive that
    package being missing. An import error here previously killed the run."""
    _plugin(tmp_path, "check_broken", "import a_package_that_does_not_exist\n")
    loaded = load_check(tmp_path, "check_broken")
    assert loaded.run is None
    assert "a_package_that_does_not_exist" in loaded.load_error


def test_absent_module_becomes_a_load_error(tmp_path: Path) -> None:
    """Test that missing module files are handled gracefully."""
    loaded = load_check(tmp_path, "check_absent")
    assert loaded.run is None
    assert "not found" in loaded.load_error


def test_module_without_run_becomes_a_load_error(tmp_path: Path) -> None:
    """Test that modules without a run() callable are marked as errored."""
    _plugin(tmp_path, "check_norun", "VALUE = 1\n")
    loaded = load_check(tmp_path, "check_norun")
    assert loaded.run is None
    assert "run()" in loaded.load_error


def test_metadata_defaults_when_unspecified(tmp_path: Path) -> None:
    """Test that metadata fields default to expected values."""
    _plugin(tmp_path, "check_bare", "def run(mode, ctx):\n    return None\n")
    loaded = load_check(tmp_path, "check_bare")
    assert loaded.run is not None
    assert loaded.privilege == "user"
    assert loaded.interactive is False
    assert loaded.disruptive is False


def test_metadata_is_read_from_the_module(tmp_path: Path) -> None:
    """§4: the check declares what it needs; the manifest never does."""
    _plugin(
        tmp_path,
        "check_meta",
        'PRIVILEGE = "root"\nINTERACTIVE = True\nDISRUPTIVE = True\n'
        "def run(mode, ctx):\n    return None\n",
    )
    loaded = load_check(tmp_path, "check_meta")
    assert loaded.privilege == "root"
    assert loaded.interactive is True
    assert loaded.disruptive is True
