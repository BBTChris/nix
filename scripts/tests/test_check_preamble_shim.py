"""`check_preamble_shim` — the DETECTION can-fail, committed rather than banked.

ARC 030 Stage 2 / sub-agent C. Drives `scan_preamble_source` (the pure function
`run()` also calls) over four synthetic variants: the correct shape, a missing
`sys.dont_write_bytecode` guard, a missing `sys.path` append, and an `insert(0,
...)` used in place of `append(...)`. Non-vacuity is proven separately by
scanning the REAL `checks/_preamble.py` on disk and asserting zero defects —
this gate must be green on the tree as it stands today, not merely capable of
turning red on a fabricated string.

No file on disk is ever mutated by this test: every plant is synthetic source
TEXT passed directly to the pure scanner, so there is zero risk to the live
import shim every other check (including this test's own collection) depends
on to run at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_preamble_shim as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

scan_preamble_source = gate.scan_preamble_source
run = gate.run

_CORRECT = """
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))
"""

_MISSING_BYTECODE_GUARD = """
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))
"""

_MISSING_PATH_APPEND = """
import sys

sys.dont_write_bytecode = True
"""

_INSERT_INSTEAD_OF_APPEND = """
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
"""

_BYTECODE_SET_TO_TRUTHY_NOT_TRUE = """
import sys
from pathlib import Path

sys.dont_write_bytecode = 1

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))
"""


def test_correct_shape_scans_clean() -> None:
    """The real shim shape, on synthetic source, scans clean."""
    assert not scan_preamble_source(_CORRECT)


def test_missing_bytecode_guard_is_a_defect() -> None:
    """A missing sys.dont_write_bytecode assignment is named."""
    defects = scan_preamble_source(_MISSING_BYTECODE_GUARD)
    assert len(defects) == 1
    assert "dont_write_bytecode" in defects[0]


def test_missing_path_append_is_a_defect() -> None:
    """A missing sys.path.append is named."""
    defects = scan_preamble_source(_MISSING_PATH_APPEND)
    assert len(defects) == 1
    assert "sys.path.append" in defects[0]


def test_insert_instead_of_append_is_named_distinctly() -> None:
    """Rule 11: the reason is asserted, not merely a red verdict."""
    defects = scan_preamble_source(_INSERT_INSTEAD_OF_APPEND)
    assert len(defects) == 1
    assert "insert" in defects[0]
    assert "shadow" in defects[0]


def test_truthy_non_true_bytecode_value_is_a_defect() -> None:
    """The literal `True` constant is required, not merely a truthy value."""
    defects = scan_preamble_source(_BYTECODE_SET_TO_TRUTHY_NOT_TRUE)
    assert len(defects) == 1
    assert "dont_write_bytecode" in defects[0]


def test_both_missing_reports_two_defects() -> None:
    """Both facts absent reports both defects, not just the first found."""
    defects = scan_preamble_source("# empty shim\n")
    assert len(defects) == 2


def test_unparseable_source_is_named_not_raised() -> None:
    """A syntax error is reported as a defect, never an unhandled exception."""
    defects = scan_preamble_source("def broken(:\n")
    assert len(defects) == 1
    assert "unparseable" in defects[0]


def test_non_vacuity_the_real_shim_on_disk_scans_clean() -> None:
    """§7.12: this gate must be observed PASS on the real, unplanted tree."""
    real = (REPO / "checks" / "_preamble.py").read_text(encoding="utf-8")
    assert not scan_preamble_source(real)


def test_run_passes_against_the_real_tree() -> None:
    """The full `run()` path, not just the pure scanner, is green for real."""
    ctx = Context(nix_home=REPO, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.PASS, result.detail


def test_run_is_cannot_measure_when_the_anchor_is_absent(tmp_path: Path) -> None:
    """§5.3: an absent anchor is CANNOT_MEASURE, never a silent PASS."""
    (tmp_path / "checks").mkdir()
    ctx = Context(nix_home=tmp_path, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.CANNOT_MEASURE
    assert "absent" in result.detail


@pytest.mark.parametrize(
    "source,expected_substr",
    [
        (_MISSING_BYTECODE_GUARD, "dont_write_bytecode"),
        (_MISSING_PATH_APPEND, "sys.path.append"),
        (_INSERT_INSTEAD_OF_APPEND, "insert"),
    ],
)
def test_run_reddens_on_a_planted_defect(
    tmp_path: Path, source: str, expected_substr: str
) -> None:
    """The full `run()` path reddens naming the reason — not the exit code alone."""
    checks_dir = tmp_path / "checks"
    checks_dir.mkdir()
    (checks_dir / "_preamble.py").write_text(source, encoding="utf-8")
    ctx = Context(nix_home=tmp_path, mode=Mode.VERIFY)
    result = run(Mode.VERIFY, ctx)
    assert result.status == Status.FAIL_NEEDS_OPERATOR
    assert result.site == "checks/_preamble.py"
    assert expected_substr in result.detail
