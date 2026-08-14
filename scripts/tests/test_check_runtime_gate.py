"""ARC 030 / sub-agent B — can-fail suite for `checks/check_runtime_gate.py`.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same
tree passing again.

No plant touches `scripts/runtime_gate.py` in place (doctrine C.8): every
control builds a throwaway `nix_home` under `tmp_path` holding a COPY, plus
the `nixverify` package the subject imports.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(REPO / "checks"))

import check_runtime_gate as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir(parents=True)
    shutil.copy(REPO / gate.GATE_FILE, tmp_path / gate.GATE_FILE)
    # runtime_gate.py imports nixverify.gitenv at module scope; scripts/ is
    # already on sys.path in this test process (other test modules put it
    # there), so the REAL nixverify resolves — the subject file itself is
    # what this fixture copies, and `load()` loads it by exact path.
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    path = home / gate.GATE_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


_ESCALATION_ANCHOR = (
    '    if os.environ.get(_NOESCALATE_ENV) == "noescalate":\n'
    "        run.verdict(\n"
    "            name,\n"
    "            code,\n"
    '            f"{why}; escalation suppressed by {_NOESCALATE_ENV}=noescalate; "\n'
    '            f"this run measured {max(run.selected, 0)} test(s)",\n'
    "        )\n"
    '    return f"full-escalated({name}:{why})"'
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "6 named arms" in result.evidence, result.evidence


def test_the_GATE_DECLARES_runtime_gate_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.GATE_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False


# --------------------------------------------------------------------------
# PLANT 1 — drift-with-zero-selection escalates ONLY under noescalate
# (the Phase-4 regression: always escalating even when noescalate is set)
# --------------------------------------------------------------------------


def test_ESCALATION_ALWAYS_ON_fails_and_NAMES_the_taxonomy_arm(home: Path) -> None:
    _plant(
        home,
        _ESCALATION_ANCHOR,
        "    if False:  # PLANTED: noescalate no longer honoured\n"
        "        run.verdict(name, code, why)\n"
        '    return f"full-escalated({name}:{why})"',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "_zero_selection" in result.site, result.site


# --------------------------------------------------------------------------
# PLANT 2 — uncovered detection dropped from read_db
# --------------------------------------------------------------------------


def test_a_DROPPED_UNCOVERED_CHECK_fails_and_NAMES_it(home: Path) -> None:
    _plant(
        home,
        "    out.uncovered = [f for f in scope if f not in out.known]",
        "    out.uncovered = []  # PLANTED: uncovered detection dropped",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "read_db" in result.site, result.site
    assert "orphan.py" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — run_pytest ignores the JUnit XML and always reports (-1, -1)
# --------------------------------------------------------------------------


def test_a_BROKEN_XML_PARSE_fails_and_NAMES_it(home: Path) -> None:
    _plant(
        home,
        "        root = ET.parse(xml_path).getroot()  # nosec B314",
        "        raise ET.ParseError('PLANTED: XML parsing disabled')  # nosec B314",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "run_pytest" in result.site, result.site


# --------------------------------------------------------------------------
# THE THIRD STEP — plant removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.GATE_FILE).read_bytes()
    _plant(
        home,
        "    out.uncovered = [f for f in scope if f not in out.known]",
        "    out.uncovered = []  # PLANTED: uncovered detection dropped",
    )

    planted = _run(home)
    (home / gate.GATE_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.GATE_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_MODULE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.GATE_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "not present under" in result.detail, result.detail


def test_the_GATE_DOES_NOT_LEAK_THE_TMP_COPY_INTO_sys_modules(home: Path) -> None:
    # Save/restore rather than a bare pop: another test module in this same
    # pytest session (`test_runtime_gate.py`) does `import runtime_gate` at
    # collection time and asserts it stays cached — destructively removing
    # that entry here would fail a DIFFERENT file's test depending on run
    # order, which is not this control's property.
    real = sys.modules.pop(gate.GATE_MODULE, None)
    try:
        _run(home)

        assert gate.GATE_MODULE not in sys.modules, (
            "the gate left the tmp_path copy registered under the bare module name"
        )
    finally:
        if real is not None:
            sys.modules[gate.GATE_MODULE] = real
