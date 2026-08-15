"""ARC 030 / sub-agent B — can-fail suite for `checks/check_extract_sources.py`.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same
tree passing again.

No plant touches `databases/schema/extract_sources.py` in place (doctrine
C.8): every control drives a COPY, and the gate itself already isolates its
subprocess's cwd to a tempdir so no plant or real run ever writes into the
working tree.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Test names SHOUT the property under test and the fixtures are one-liners, so
# a docstring here would restate the name. The pragma is per-file and named,
# matching `test_check_observed_resource_claims.py`.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(REPO / "checks"))

import check_extract_sources as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "databases" / "schema").mkdir(parents=True)
    shutil.copy(REPO / gate.SCRIPT_FILE, tmp_path / gate.SCRIPT_FILE)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    path = home / gate.SCRIPT_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


_CHMOD_ANCHOR = 'if name.endswith(".sh"):\n        os.chmod(name, 0o755)'


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "read back extracted content byte-for-byte" in result.evidence, (
        result.evidence
    )


def test_the_GATE_DECLARES_the_script_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.SCRIPT_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False


def test_the_RESOURCES_declaration_holds_under_BOTH_documented_interpreters() -> None:
    """CHECK-DEBT D3.140 — the defect this gate's declaration actually had.

    This gate spawns `sys.executable`, so the interpreter it claims is whichever
    one launched `verify.py`, and `nixverify.observe.covers` matches a
    `subprocess:` token by BASENAME. `subprocess:python` alone was therefore
    TRUE under `.venv/bin/python` and FALSE under `/usr/bin/python3` — the
    launch mode every `nix-verify*.service` unit pins.

    Derived from `documented_interpreters`, never from a literal path list: a
    second copy of "which interpreters exist" here would be the restated mutable
    fact directive 3 forbids, and would go stale silently.

    The second half is the control, and it is the load-bearing half: each token
    must be the ONLY one covering its interpreter. Without it this test passes
    on a declaration containing one token and a decorative one.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    from nixverify.observe import (  # pylint: disable=import-outside-toplevel
        covers,
        documented_interpreters,
    )

    modes = documented_interpreters(REPO)
    assert len(modes) > 1, modes
    for label, path in modes:
        claim = f"subprocess:{path}"
        matching = [t for t in gate.RESOURCES if covers(t, claim, REPO)]
        assert matching, (
            f"RESOURCES={list(gate.RESOURCES)} accounts for nothing this gate "
            f"spawns under the {label} launch mode ({claim}) — a false "
            "declaration under a documented invocation (D3.140)"
        )
        assert len(matching) == 1, (
            f"{matching} all cover the {label} launch mode; one of them is "
            "decorative and could be deleted without this test noticing"
        )


# --------------------------------------------------------------------------
# PLANT 1 — the executable-bit chmod removed
# --------------------------------------------------------------------------


def test_a_REMOVED_CHMOD_fails_and_NAMES_the_sh_file(home: Path) -> None:
    _plant(
        home,
        _CHMOD_ANCHOR,
        "if False:\n        os.chmod(name, 0o755)  # PLANTED: chmod disabled",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "setup.sh" in result.site, result.site
    assert "NOT executable" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — every extraction marked executable (over-broad chmod)
# --------------------------------------------------------------------------


def test_an_OVER_BROAD_CHMOD_fails_and_NAMES_the_non_sh_file(home: Path) -> None:
    _plant(
        home,
        _CHMOD_ANCHOR,
        "if True:  # PLANTED: chmod applied to every extraction, not just .sh\n"
        "        os.chmod(name, 0o755)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "schema.sql" in result.site, result.site
    assert "IS executable" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — the extraction regex broken (extracts nothing)
# --------------------------------------------------------------------------


def test_a_BROKEN_REGEX_fails_and_NAMES_the_missing_file(home: Path) -> None:
    _plant(home, "filename=(\\S+)", "filename=NEVER_MATCHES_ANYTHING_XYZ")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "was not extracted" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plant removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.SCRIPT_FILE).read_bytes()
    _plant(
        home,
        _CHMOD_ANCHOR,
        "if False:\n        os.chmod(name, 0o755)  # PLANTED: chmod disabled",
    )

    planted = _run(home)
    (home / gate.SCRIPT_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.SCRIPT_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_SCRIPT_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.SCRIPT_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "absent" in result.detail, result.detail
