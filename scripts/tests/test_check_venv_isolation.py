"""Tests for `checks/check_venv_isolation.py` (ARC 030 / Stage 2 A2).

Every control drives a CONSTRUCTED tree under `tmp_path` — never the real
`.venv`/`.venv-dev` (`nix_check_contract.md` §9.4-adjacent discipline: a test
that mutated the shared venv this repo's own gates run against would be the
exact hazard this arc exists to close, committed as a test).
"""

# pylint: disable=invalid-name,import-outside-toplevel,duplicate-code
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "checks"))
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import check_venv_isolation as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status
from nixverify.venv_lock import venv_mutation_lock

# pylint: enable=wrong-import-position


def _run(nix_home: Path, mode: Mode = Mode.VERIFY):
    return gate.run(mode, Context(nix_home=nix_home, mode=mode))


def _fake_venv(root: Path, name: str, packages: list[str]) -> Path:
    """A minimal fake venv: a `python3` shim answering `-c "<query>"` with a
    fixed package list, laid out at `root/name`. Not a real venv (no actual
    interpreter, no site-packages) — `check_venv_isolation` only ever asks
    its interpreter to answer the metadata query, exactly like
    `check_python_deps` does, so a shim that answers that one query
    correctly is a faithful enough double, and building N real venvs (each
    minutes, hundreds of MB) for a unit test is disproportionate to what
    this suite needs to prove.
    """
    venv = root / name
    bindir = venv / "bin"
    bindir.mkdir(parents=True)
    python = bindir / "python3"
    payload = "[" + ", ".join(f'"{p}"' for p in packages) + "]"
    python.write_text(
        f"#!/usr/bin/env python3\nimport sys\nprint('{payload}')\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    return venv


def test_a_clean_split_PASSES_and_names_what_it_measured(tmp_path: Path) -> None:
    """The healthy state: two genuinely separate venvs, no leaked marker."""
    _fake_venv(tmp_path, ".venv", ["ib_async", "pyzmq"])
    _fake_venv(tmp_path, ".venv-dev", ["pandas_market_calendars", "pytest"])
    result = _run(tmp_path)
    assert result.status is Status.PASS
    assert "0 of 4 dev-only marker(s)" in result.evidence


@pytest.mark.parametrize(
    "marker",
    (
        "exchange_calendars",
        "korean_lunar_calendar",
        "pandas_market_calendars",
        "pyluach",
    ),
)
def test_a_LEAKED_dev_only_marker_reddens_naming_the_package(
    tmp_path: Path, marker: str
) -> None:
    """The measured D3.111 shape, replayed as a plant: one of the calendar
    generator's own four exclusive dependency names, present in the RUNTIME
    venv — exactly what a wrong `--python .venv/bin/python` install would do.

    The parametrize list is a LITERAL, not `sorted(gate.DEV_ONLY_MARKERS)`:
    `check_derived_claims`' AST-based `pytest_collected_tests` probe requires
    a literal `List`/`Tuple` argvalues to count parametrized cases without
    importing the module under test (Stage 3 integration, ARC 030 — a
    non-literal argvalues raised `ProbeError` on the real tree). A test right
    below asserts this list is exactly `DEV_ONLY_MARKERS`, so a future add to
    the marker set fails LOUD here rather than silently under-parametrizing.
    """
    _fake_venv(tmp_path, ".venv", ["ib_async", marker])
    _fake_venv(tmp_path, ".venv-dev", ["pandas_market_calendars"])
    result = _run(tmp_path)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert marker in result.site
    assert "re-merged in substance" in result.detail


def test_the_LITERAL_parametrize_list_above_still_equals_DEV_ONLY_MARKERS() -> None:
    """Guards the drift the literal-list rewrite (Stage 3 integration) invites.

    `test_a_LEAKED_dev_only_marker_reddens_naming_the_package` parametrizes
    over a hand-written literal tuple, not `gate.DEV_ONLY_MARKERS` itself,
    because `check_derived_claims`' AST probe cannot count a non-literal
    argvalues. That trade needs its own can-fail: if `DEV_ONLY_MARKERS` ever
    gains or loses a name and this literal is not updated in lockstep, the
    plant coverage above silently under- or over-covers the real marker set.
    This assertion fails LOUD in that case instead.
    """
    literal = {
        "exchange_calendars",
        "korean_lunar_calendar",
        "pandas_market_calendars",
        "pyluach",
    }
    assert literal == set(gate.DEV_ONLY_MARKERS), (
        f"the hand-written parametrize list above ({sorted(literal)}) has "
        f"drifted from gate.DEV_ONLY_MARKERS ({sorted(gate.DEV_ONLY_MARKERS)}) "
        "— update both together"
    )


def test_a_COLLAPSED_split_symlink_reddens_before_querying_packages(
    tmp_path: Path,
) -> None:
    """`.venv-dev` pointed AT `.venv` — the split exists in name only."""
    real = _fake_venv(tmp_path, ".venv", ["ib_async"])
    (tmp_path / ".venv-dev").symlink_to(real, target_is_directory=True)
    result = _run(tmp_path)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "same real directory" in result.evidence
    assert "re-merged" in result.evidence


def test_DEV_VENV_ABSENT_is_a_legitimate_PASS_not_a_collapse(tmp_path: Path) -> None:
    """`.venv-dev` never having been built is the fresh-checkout state, not
    a re-merge — the two conditions must not be conflated (§7.12 condition 2
    is about BOTH absent; this is the narrower "runtime built, dev never
    built" shape, which is equally legitimate and must not redden either).
    """
    _fake_venv(tmp_path, ".venv", ["ib_async", "pyzmq"])
    result = _run(tmp_path)
    assert result.status is Status.PASS
    assert "not built (legitimate)" in result.evidence


def test_NEITHER_venv_present_is_CANNOT_MEASURE_never_a_pass(tmp_path: Path) -> None:
    """A fresh checkout with no `.venv` at all is unmeasurable, not clean."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert "check_venv" in result.detail


def test_an_EMPTY_marker_list_is_CANNOT_MEASURE(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 condition 1: a data-driven gate with no data scans nothing."""
    monkeypatch.setattr(gate, "DEV_ONLY_MARKERS", frozenset())
    _fake_venv(tmp_path, ".venv", ["ib_async"])
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert "empty" in result.detail


# ---------------------------------------------------------------------------
# THE HAZARD, PROVEN: a held mutation lock must produce CANNOT_MEASURE, never
# a false PASS or a false FAIL against a moving target (ARC 030 / Stage 2 A2).
# ---------------------------------------------------------------------------


def test_a_HELD_lock_makes_this_gate_report_CANNOT_MEASURE_not_a_false_verdict(
    tmp_path: Path,
) -> None:
    """The hazard, reproduced directly: hold the lock from THIS process (as
    a concurrent `check_venv`/`check_python_deps` repair — or a human running
    `install.sh` by hand — would), leaving `.venv` in a state that WOULD read
    as a clean PASS if queried (a fully-formed, marker-free fake venv) or,
    with a marker planted, as a FAIL. Show the gate reports neither: it
    reports CANNOT_MEASURE and names the lock, without ever running the
    package query at all.
    """
    _fake_venv(tmp_path, ".venv", ["ib_async", "pyzmq"])  # would otherwise PASS
    with venv_mutation_lock(tmp_path):
        result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert "venv-mutation lock is held" in result.detail
    assert "moving target" in result.detail

    # And once released, the SAME tree measures cleanly — proving the
    # CANNOT_MEASURE was about the lock, not about the venv itself.
    released = _run(tmp_path)
    assert released.status is Status.PASS


def test_a_HELD_lock_masks_a_real_leaked_marker_too_and_that_is_the_point(
    tmp_path: Path,
) -> None:
    """Even a REAL defect (a leaked marker) must not be reported while the
    lock is held — the venv might be mid-repair BECAUSE of exactly this
    defect, and reporting FAIL here would be racing the process fixing it,
    not informing an operator of something stable enough to act on.
    """
    _fake_venv(tmp_path, ".venv", ["ib_async", "pandas_market_calendars"])
    with venv_mutation_lock(tmp_path):
        result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert "moving target" in result.detail


def test_the_lock_is_process_wide_a_SEPARATE_process_sees_it_held(
    tmp_path: Path,
) -> None:
    """Not just re-entrant-safe within one process — a genuinely SEPARATE
    process (forked here to model a second concurrent arc's check run)
    must observe the lock as held, the same real-world shape as two
    `verify.py` invocations racing each other.
    """
    _fake_venv(tmp_path, ".venv", ["ib_async"])
    read_fd, write_fd = os.pipe()
    with venv_mutation_lock(tmp_path):
        pid = os.fork()
        if pid == 0:  # pragma: no cover - child process
            os.close(read_fd)
            result = _run(tmp_path)
            msg = b"1" if result.status is Status.CANNOT_MEASURE else b"0"
            os.write(write_fd, msg)
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        seen = os.read(read_fd, 1)
        os.close(read_fd)
        os.waitpid(pid, 0)
    assert seen == b"1", "a separate process did not observe the held lock"
