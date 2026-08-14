"""Transitive-range conformance per docs/CHECK-DEBT.md D3.111.

check_python_deps.py compares the venv against the THREE declared top-level
pins, exactly, and nothing else. `check_python_transitive_deps` is a
different subject: whether every INSTALLED package's own declared
requirements are still satisfied by whatever else is installed — the gap
D3.111 fell through (`tzdata` bumped outside `ib_async`'s own declared
range, silently, because nothing compared the two).

THE REAL CAN-FAIL (Success #4, arc hard limit — "a real failing scenario,
run in an interpreter, not a mental walkthrough"): a disposable venv, built
and torn down inside a single test, reproduces the EXACT D3.111 shape —
`ib_async==2.1.0` installed normally (declares `tzdata<2026.0,>=2025.2`),
then `tzdata` force-upgraded past it with `pip install --no-deps` (the same
kind of resolver-bypassing state a two-step install produces without anyone
asking for it). `query_violations()` runs against that disposable venv's own
real interpreter — no mock, no hand-built dict standing in for what pip
would report. See `test_a_forced_out_of_range_transitive_dep_reddens_the_gate`.
"""

# pylint: disable=invalid-name,duplicate-code
# Test names SHOUT the property under test, as in every other suite here.
# duplicate-code: the fake-interpreter fixture setup here necessarily pairs
# with the near-identical one in test_check_python_deps.py.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"


def _run(mode: Mode, home: Path):
    loaded = load_check(CHECKS, "check_python_transitive_deps")
    assert loaded.run is not None, loaded.load_error
    return loaded.run(mode, Context(nix_home=home, mode=mode))


def _mod():
    # load_check() appends checks/ to sys.path as a side effect (mirrors
    # test_check_python_deps.py's identical helper) — must run before the
    # bare `import check_python_transitive_deps` below can resolve, and
    # every caller of this helper needs that regardless of test order.
    loaded = load_check(CHECKS, "check_python_transitive_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_transitive_deps as m  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    return m


_VIOLATION = {
    "consumer": "ib_async",
    "consumer_version": "2.1.0",
    "dependency": "tzdata",
    "declared_range": "<2026.0,>=2025.2",
    "installed": "2026.3",
}


def test_no_violations_passes_with_evidence() -> None:
    """§5: PASS carries non-empty evidence naming what was measured."""
    result = _mod().evaluate([], [])
    assert result.status is Status.PASS
    assert result.evidence.strip()


def test_unexcepted_violation_fails_and_names_the_dependency() -> None:
    """An untracked transitive-range violation is always a hard FAIL."""
    result = _mod().evaluate([_VIOLATION], [])
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "tzdata" in result.site
    assert "ib_async" in result.detail
    assert "2026.3" in result.detail


def test_matching_exception_is_guarded_not_failed() -> None:
    """A tracked, matching exception downgrades FAIL to GUARDED, owner named."""
    exceptions = [
        {
            "consumer": "ib_async",
            "dependency": "tzdata",
            "declared_range": "<2026.0,>=2025.2",
            "justification": "test fixture",
            "arc": "ARC 999",
        }
    ]
    result = _mod().evaluate([_VIOLATION], exceptions)
    assert result.status is Status.GUARDED
    assert result.guard_owner == "ARC 999"
    assert result.evidence.strip()


def test_exception_with_stale_range_does_not_cover_a_new_violation() -> None:
    """Hard limit: no blanket skip. A DIFFERENT declared_range than the one
    the exception names must still FAIL — the declaring package's own
    requirement changed, so the old exception no longer describes today."""
    exceptions = [
        {
            "consumer": "ib_async",
            "dependency": "tzdata",
            "declared_range": "<2027.0,>=2025.2",  # different from _VIOLATION's
            "justification": "stale",
            "arc": "ARC 999",
        }
    ]
    result = _mod().evaluate([_VIOLATION], exceptions)
    assert result.status is Status.FAIL_NEEDS_OPERATOR


def test_query_failure_is_cannot_measure(tmp_path: Path) -> None:
    """A subprocess that cannot answer is CANNOT_MEASURE, never a false PASS
    (mirrors check_python_deps.py's identical Task-9 finding)."""
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_python.chmod(0o755)

    result = _run(Mode.VERIFY, tmp_path)
    assert result.status is Status.CANNOT_MEASURE


def test_a_violation_UNDER_a_HELD_venv_mutation_lock_is_CANNOT_MEASURE(
    tmp_path: Path,
) -> None:
    """ARC 030 / Stage 2 A2 — the same lock-awareness proven on the sibling
    gates, here for the read-only, NON-CORRECTABLE member of the trio. Even
    a gate that never repairs anything must not report a stable-sounding
    FAIL_NEEDS_OPERATOR against a venv another process is actively mutating
    — the violation might be the mutation's own transient in-between state.
    """
    # pylint: disable-next=import-outside-toplevel
    from nixverify.venv_lock import venv_mutation_lock

    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python3"
    payload = (
        '[{"consumer": "ib_async", "consumer_version": "2.1.0", '
        '"dependency": "tzdata", "declared_range": "<2026.0,>=2025.2", '
        '"installed": "2026.3"}]'
    )
    fake_python.write_text(
        f"#!/usr/bin/env python3\nprint('{payload}')\n", encoding="utf-8"
    )
    fake_python.chmod(0o755)

    with venv_mutation_lock(tmp_path):
        held = _run(Mode.VERIFY, tmp_path)
    assert held.status is Status.CANNOT_MEASURE
    assert "venv-mutation lock is held" in held.detail

    released = _run(Mode.VERIFY, tmp_path)
    assert released.status is Status.FAIL_NEEDS_OPERATOR


def test_no_venv_is_cannot_measure(tmp_path: Path) -> None:
    """No `.venv` interpreter at all is CANNOT_MEASURE, not a query failure."""
    result = _run(Mode.VERIFY, tmp_path)
    assert result.status is Status.CANNOT_MEASURE


def test_load_exceptions_missing_file_is_empty_not_an_error(tmp_path: Path) -> None:
    """An absent ledger means 'no exceptions declared', not 'unmeasurable'."""
    assert _mod().load_exceptions(tmp_path) == []


def test_load_exceptions_rejects_malformed_shape(tmp_path: Path) -> None:
    """A non-list `exceptions` key is a loud TypeError, not a silent []."""
    (tmp_path / "transitive_deps_exceptions.json").write_text(
        '{"exceptions": "not-a-list"}', encoding="utf-8"
    )
    with pytest.raises(TypeError, match="must be a list"):
        _mod().load_exceptions(tmp_path)


def test_declares_non_correctable_with_a_reason() -> None:
    """No safe automatic repair exists for a transitive-range violation —
    see the module docstring's third paragraph and NON_CORRECTABLE_REASON."""
    mod = _mod()
    assert mod.CORRECTABLE is False
    assert mod.NON_CORRECTABLE_REASON.strip()

    # pylint: disable-next=import-outside-toplevel
    from nixverify.declarations import read_all

    declared = read_all(CHECKS)["check_python_transitive_deps"]
    assert declared.correctable is False
    assert declared.non_correctable_reason.strip()
    assert declared.errors == (), declared.errors
    assert declared.depends_on == ("check_venv",)
    assert declared.resources == ("venv",)


def test_real_venv_currently_has_zero_violations() -> None:
    """The runtime venv split (this arc) is what makes this PASS true today:
    before it, D3.111's tzdata/ib_async pair would have shown up here."""
    result = _run(Mode.VERIFY, REPO)
    assert result.status is Status.PASS, result.detail


# ===========================================================================
# THE REAL CAN-FAIL — Success #4 / Hard Limit #8. A disposable venv, not a
# mental walkthrough. Torn down by pytest's own tmp_path cleanup; nothing to
# restore because nothing shared was ever touched (§7.12: could this pass
# while measuring nothing? No candidate venv -> CANNOT_MEASURE, proven above;
# a real interpreter that really has the violation is the only way this
# reaches FAIL_NEEDS_OPERATOR).
# ===========================================================================


def test_a_forced_out_of_range_transitive_dep_reddens_the_gate(
    tmp_path: Path,
) -> None:
    """Reproduces D3.111's exact shape in a disposable venv: `ib_async`
    installed normally (declares `tzdata<2026.0,>=2025.2`), then `tzdata`
    force-upgraded past that range with `--no-deps` — precisely the state a
    second, uncoordinated install step produces without anyone asking for
    it. `query_violations()` runs against the disposable venv's OWN real
    interpreter; nothing here is a hand-built dict standing in for pip.
    """
    venv_dir = tmp_path / "disposable"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    venv_python = venv_dir / "bin" / "python"
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--quiet", "ib_async==2.1.0"],
        check=True,
        capture_output=True,
        timeout=300,
    )

    # CONTROL: freshly resolved, tzdata is in ib_async's own declared range.
    control = _mod().query_violations(venv_python)
    assert control == [], control
    assert _mod().evaluate(control, []).status is Status.PASS

    # PLANT: force tzdata out of range, bypassing the resolver exactly the
    # way an uncoordinated second install does.
    subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "tzdata==2026.3",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )

    violations = _mod().query_violations(venv_python)
    assert violations, "the plant did not produce a detectable violation"
    names = {(v["consumer"].lower(), v["dependency"]) for v in violations}
    assert ("ib_async", "tzdata") in names, violations

    result = _mod().evaluate(violations, [])
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "tzdata" in result.site
    assert "ib_async" in result.detail
    assert "2026.3" in result.detail
