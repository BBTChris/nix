"""Plugin loading isolation per nix_check_contract.md §9.3-§9.4."""

import sys
from pathlib import Path

from nixverify.loader import load_check


def _plugin(tmp_path: Path, name: str, body: str) -> Path:
    """Write a test check module to tmp_path and return the directory."""
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
    """§4: the check declares what it needs; the registry never does."""
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


def test_failed_import_does_not_pollute_sys_modules(tmp_path: Path) -> None:
    """sys.modules must not retain stale modules after failed import.

    Ensures load_check registers the module in sys.modules only after
    successful exec_module, preventing process-wide pollution when exec fails.
    """
    _plugin(tmp_path, "check_stale", "import a_package_that_does_not_exist\n")
    # Remove any prior pollution
    sys.modules.pop("check_stale", None)
    loaded = load_check(tmp_path, "check_stale")
    assert loaded.run is None
    assert "a_package_that_does_not_exist" in loaded.load_error
    # Verify the stale module was never registered
    assert "check_stale" not in sys.modules


def test_metadata_getattr_error_captured(tmp_path: Path) -> None:
    """PEP 562 module.__getattr__ exceptions during metadata reads are captured.

    This test does NOT exercise the run lookup gap (see next test) because
    run is defined, so getattr finds it via normal lookup and never calls __getattr__.
    Kept to verify metadata read protection works.
    """
    _plugin(
        tmp_path,
        "check_getattr_error",
        "def run(mode, ctx):\n    return None\n"
        "def __getattr__(name):\n"
        "    raise RuntimeError(f'custom getattr error for {name}')\n",
    )
    loaded = load_check(tmp_path, "check_getattr_error")
    # run() itself is found and callable, but metadata reads will hit __getattr__
    assert loaded.run is None  # Metadata read failed, so run is not returned
    assert "attribute read failed" in loaded.load_error
    assert "RuntimeError" in loaded.load_error


def test_check_can_import_a_sibling_module_in_the_same_directory(
    tmp_path: Path,
) -> None:
    """A check's own directory must be importable, mirroring standalone execution.

    `python3 checks/check_x.py` auto-adds checks/ to sys.path[0] (CPython
    interpreter startup behaviour). load_check must replicate that so a check
    importing a sibling helper (e.g. `checks/_preamble.py`) behaves the same
    whether run under the engine or standalone.
    """
    _plugin(tmp_path, "_helper", "VALUE = 'from helper'\n")
    _plugin(
        tmp_path,
        "check_uses_sibling",
        "import _helper  # noqa: F401\ndef run(mode, ctx):\n    return _helper.VALUE\n",
    )
    sys.modules.pop("_helper", None)
    loaded = load_check(tmp_path, "check_uses_sibling")
    assert loaded.run is not None, loaded.load_error
    assert loaded.run(None, None) == "from helper"


def test_run_lookup_error_captured(tmp_path: Path) -> None:
    """PEP 562 module.__getattr__ exceptions during run lookup are captured.

    This test exercises the actual gap: a module with NO run attribute that
    defines __getattr__ raising a non-AttributeError. The getattr(module, "run", None)
    call must NOT propagate the exception, but instead return it as load_error.
    """
    _plugin(
        tmp_path,
        "check_no_run_getattr",
        "def __getattr__(name):\n    raise RuntimeError(f'boom {name}')\n",
    )
    # This must not raise — load_check must never raise
    loaded = load_check(tmp_path, "check_no_run_getattr")
    assert loaded.run is None
    assert "attribute read failed" in loaded.load_error
    assert "RuntimeError" in loaded.load_error
    assert "boom run" in loaded.load_error
