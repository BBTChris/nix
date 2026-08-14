"""`check_nixverify_init` — the DETECTION can-fail, committed rather than banked.

ARC 030 Stage 2 / sub-agent C. `scripts/nixverify/__init__.py` is executed on
every `import nixverify` in this repository — including this test's own import
of the check module — and was named by NOTHING before this arc
(`gate_coverage_baseline.json`'s exclusion entry: "NAMED BY NOTHING ... ASSERTED
ABOUT nowhere"). Every plant here is synthetic SOURCE TEXT handed to the pure
`scan_init_coherence`; the live `scripts/nixverify/__init__.py` this process is
running under is never mutated, never re-imported, never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_nixverify_init as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

scan_init_coherence = gate.scan_init_coherence
run = gate.run

_CONTRACT_SRC = """
class CheckResult:
    pass

class Context:
    pass

class Mode:
    pass

class Status:
    pass

def exit_code_for(status):
    return 0

def validate_result(result, home):
    return result
"""

_CORRECT_INIT = """
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    exit_code_for,
    validate_result,
)

__all__ = [
    "CheckResult",
    "Context",
    "Mode",
    "Status",
    "exit_code_for",
    "validate_result",
]
"""


def test_correct_shape_scans_clean() -> None:
    """The real shape, on synthetic sources, scans clean."""
    defects = scan_init_coherence(_CORRECT_INIT, {"contract": _CONTRACT_SRC})
    assert not defects


def test_all_lists_a_name_removed_from_the_sibling() -> None:
    """The real failure mode: contract.py drops a name, __init__.py still

    imports it. Every check in the tree would fail to import.
    """
    stale_contract = _CONTRACT_SRC.replace(
        "def validate_result(result, home):\n    return result\n", ""
    )
    defects = scan_init_coherence(_CORRECT_INIT, {"contract": stale_contract})
    assert len(defects) == 1
    assert "validate_result" in defects[0]
    assert "ImportError" in defects[0]


def test_all_lists_a_name_never_imported() -> None:
    """A phantom __all__ entry with no backing import is a defect."""
    init = _CORRECT_INIT.replace('    "validate_result",\n', "").replace(
        "__all__ = [", '__all__ = [\n    "phantom_export",'
    )
    defects = scan_init_coherence(init, {"contract": _CONTRACT_SRC})
    reasons = " ".join(defects)
    assert "phantom_export" in reasons
    assert "no `from nixverify" in reasons


def test_import_present_but_missing_from_all() -> None:
    """An import not re-advertised in __all__ is a defect."""
    init = """
from nixverify.contract import CheckResult, Context

__all__ = ["CheckResult"]
"""
    defects = scan_init_coherence(init, {"contract": _CONTRACT_SRC})
    assert len(defects) == 1
    assert "Context" in defects[0]
    assert "__all__ does not list it" in defects[0]


def test_missing_sibling_file_is_named_not_a_silent_pass() -> None:
    """A sibling absent from the resolved scope is named, never silently passed."""
    defects = scan_init_coherence(_CORRECT_INIT, {})
    assert defects
    assert any("absent from the resolved scope" in d for d in defects)


def test_no_all_literal_is_a_defect() -> None:
    """No literal __all__ list at all is a defect."""
    init = "from nixverify.contract import CheckResult\n"
    defects = scan_init_coherence(init, {"contract": _CONTRACT_SRC})
    assert len(defects) == 1
    assert "__all__" in defects[0]


def test_unparseable_init_is_named_not_raised() -> None:
    """A syntax error is reported as a defect, never an unhandled exception."""
    defects = scan_init_coherence("def broken(:\n", {})
    assert len(defects) == 1
    assert "unparseable" in defects[0]


def test_non_vacuity_the_real_init_on_disk_scans_clean() -> None:
    """§7.12: this gate must be observed PASS on the real, unplanted tree."""
    real_init = (REPO / "scripts" / "nixverify" / "__init__.py").read_text(
        encoding="utf-8"
    )
    submodules = {
        sub
        for sub, _ in gate._from_imports(  # pylint: disable=protected-access
            __import__("ast").parse(real_init)
        )
    }
    sibling_sources = {
        sub: (REPO / "scripts" / "nixverify" / f"{sub}.py").read_text(encoding="utf-8")
        for sub in submodules
        if (REPO / "scripts" / "nixverify" / f"{sub}.py").is_file()
    }
    defects = scan_init_coherence(real_init, sibling_sources)
    assert not defects, defects


def test_run_passes_against_the_real_tree() -> None:
    """The full `run()` path, not just the pure scanner, is green for real."""
    ctx = Context(nix_home=REPO, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.PASS, result.detail


def test_run_is_cannot_measure_when_the_anchor_is_absent(tmp_path: Path) -> None:
    """§5.3: an absent anchor is CANNOT_MEASURE, never a silent PASS."""
    (tmp_path / "scripts" / "nixverify").mkdir(parents=True)
    ctx = Context(nix_home=tmp_path, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.CANNOT_MEASURE
    assert "absent" in result.detail


def test_run_reddens_on_a_planted_stale_export(tmp_path: Path) -> None:
    """The full `run()` path, driven end to end against a scratch tree."""
    nv_dir = tmp_path / "scripts" / "nixverify"
    nv_dir.mkdir(parents=True)
    (nv_dir / "contract.py").write_text(
        _CONTRACT_SRC.replace(
            "def validate_result(result, home):\n    return result\n", ""
        ),
        encoding="utf-8",
    )
    (nv_dir / "__init__.py").write_text(_CORRECT_INIT, encoding="utf-8")
    ctx = Context(nix_home=tmp_path, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.FAIL_NEEDS_OPERATOR
    assert result.site == "scripts/nixverify/__init__.py"
    assert "validate_result" in result.detail


def test_run_is_cannot_measure_when_all_is_empty(tmp_path: Path) -> None:
    """§7.12 condition 2: an empty __all__ scans nothing, so it is CANNOT_MEASURE."""
    nv_dir = tmp_path / "scripts" / "nixverify"
    nv_dir.mkdir(parents=True)
    (nv_dir / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    ctx = Context(nix_home=tmp_path, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.CANNOT_MEASURE
