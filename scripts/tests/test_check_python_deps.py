"""Pin conformance per VERIFY-AND-CHECKS.md §7."""

import json
from pathlib import Path

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


def test_declares_non_disruptive_so_it_may_run_at_boot() -> None:
    """§8: a pin-conformance repair is a package swap, but not a disruptive one here."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.disruptive is False
