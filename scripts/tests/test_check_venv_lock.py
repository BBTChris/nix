"""`check_venv_lock` — the DETECTION can-fail, committed rather than banked.

ARC 035 / Phase 0.2. `scripts/nixverify/venv_lock.py` had been carried in
`checks/gate_coverage_baseline.json`'s `artifacts` ratchet across four arcs with
its owner re-pointed three times, one over the operator ceiling (D2.31). The
brief forbade both available cheap discharges — another walk and an exclusion —
so the gate DRIVES the lock with two real processes, and this suite proves the
gate can go red.

Every plant here is applied to a COPY of `venv_lock.py` in a scratch tree and
driven through the SHIPPED gate's own `drive_contention`. The live module that
this interpreter (and every venv-mutating check) depends on is never mutated.

The CONTROL is the point: an unmutated copy drives clean, so every red below is
attributable to its own mutation and not to the harness.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,missing-function-docstring
# The house convention for can-fail suites: test names spell the
# STATUS they assert (CANNOT_MEASURE, FAIL, STALE_PIN) in the case the
# contract uses, because a reader scanning a failure list needs the
# verdict, not snake_case. Same disables as the sibling suites.
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_venv_lock as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

SUBJECT = REPO / "scripts" / "nixverify" / "venv_lock.py"


def _planted(tmp_path: Path, old: str, new: str, *, name: str = "venv_lock.py") -> Path:
    """A copy of the subject with exactly ONE textual mutation applied."""
    source = SUBJECT.read_text()
    assert old in source, (
        f"plant anchor is stale: {old!r} appears 0 times in {SUBJECT}. "
        f"A plant that matches nothing plants nothing (debug.md §8 #4)."
    )
    target = tmp_path / name
    target.write_text(source.replace(old, new, 1))
    return target


def _drive(path: Path) -> list[str]:
    return gate.drive_contention(path, sys.executable)


# ---------------------------------------------------------------- the CONTROL


def test_control_the_unmutated_subject_drives_clean(tmp_path: Path) -> None:
    """An unmutated COPY passes every arm.

    Without this, a red anywhere below could be the harness rather than the
    plant, and the whole suite would prove nothing.
    """
    control = tmp_path / "venv_lock.py"
    shutil.copyfile(SUBJECT, control)
    assert _drive(control) == []


def test_the_shipped_gate_passes_against_the_shipped_tree() -> None:
    """The gate, unmodified, against the real tree: PASS with 6 arms named."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail
    assert "6/6 arms" in result.evidence


# ------------------------------------------------------------------- ARM 2/3
# The lock stops excluding.


def test_a_lock_that_does_not_lock_reddens_arm_2_and_3(tmp_path: Path) -> None:
    """`flock` removed: the acquire always succeeds, so nothing is excluded.

    This is the defect the whole module exists to prevent — a check reading
    `.venv`'s package state while another process rebuilds it.
    """
    broken = _planted(
        tmp_path,
        "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n                break",
        "break",
    )
    defects = _drive(broken)
    assert any(d.startswith("ARM2") for d in defects), defects
    assert any(d.startswith("ARM3") for d in defects), defects
    assert any(
        "does not exclude" in d or "cannot see a real hold" in d for d in defects
    )


def test_a_blind_probe_reddens_arm_2(tmp_path: Path) -> None:
    """`probe_lock` hard-wired to "free": the observer stops observing.

    A probe that always reports free is the "green while measuring nothing"
    shape one layer down — every caller would treat a moving `.venv` as stable.
    """
    broken = _planted(
        tmp_path,
        "    path = lock_path(nix_home)\n    if not path.is_file():",
        "    path = lock_path(nix_home)\n    if True:",
    )
    defects = _drive(broken)
    assert any(d.startswith("ARM2") for d in defects), defects
    assert any("reports FREE while pid" in d for d in defects), defects


# --------------------------------------------------------------------- ARM 3
# The REASON, not the exit code (check-contract rule 11).


def test_a_generic_exception_reddens_arm_3_even_though_it_still_raises(
    tmp_path: Path,
) -> None:
    """`VenvLockHeld` downgraded to `RuntimeError`.

    The lock still excludes and something is still raised — a gate asserting
    only "an exception happened" would stay green. Callers distinguish
    contention (report CANNOT_MEASURE and move on) from a broken lock by the
    TYPE, so the type is the assertion.
    """
    broken = _planted(
        tmp_path,
        'raise VenvLockHeld(f"{path}: held by another process") from exc',
        'raise RuntimeError(f"{path}: held by another process") from exc',
    )
    defects = _drive(broken)
    assert any(d.startswith("ARM3") for d in defects), defects
    assert any("not VenvLockHeld" in d for d in defects), defects


def test_a_reasonless_message_reddens_arm_3(tmp_path: Path) -> None:
    """The right exception type carrying no path.

    Right type, no reason. Rule 11 again: an operator handed "held by another
    process" with no path cannot tell WHICH lock, and on a box with several
    worktrees that is the whole question.
    """
    broken = _planted(
        tmp_path,
        'raise VenvLockHeld(f"{path}: held by another process") from exc',
        'raise VenvLockHeld("busy") from exc',
    )
    defects = _drive(broken)
    assert any(d.startswith("ARM3") for d in defects), defects
    assert any("does not name the lock path" in d for d in defects), defects


# --------------------------------------------------------------------- ARM 4
# The timeout is honoured, not merely declared.


def test_an_ignored_timeout_reddens_arm_4(tmp_path: Path) -> None:
    """`blocking=True` gives up instantly.

    It still raises `VenvLockHeld` — the arm's type assertion alone would pass.
    Only the elapsed-time floor catches it, and the floor is a LOWER bound
    precisely because a loaded box can lengthen a wait but never shorten it.
    """
    broken = _planted(
        tmp_path,
        "if not blocking or time.monotonic() >= deadline:",
        "if True:",
    )
    defects = _drive(broken)
    assert any(d.startswith("ARM4") for d in defects), defects
    assert any("gave up after" in d for d in defects), defects


# --------------------------------------------------------------------- ARM 6
# The lock must survive `rm -rf .venv`.


def test_moving_the_lock_inside_the_venv_reddens_arm_6(tmp_path: Path) -> None:
    """The lock file relocated under `.venv`.

    The module's own docstring makes surviving a `rm -rf .venv` mid-rebuild
    load-bearing; a lock inside the directory it guards is deleted by the very
    operation it exists to serialize.
    """
    broken = _planted(
        tmp_path,
        'return nix_home / "state" / LOCK_FILENAME',
        'return nix_home / ".venv" / LOCK_FILENAME',
    )
    defects = _drive(broken)
    assert any(d.startswith("ARM6") for d in defects), defects
    assert any("lives INSIDE the venv it guards" in d for d in defects), defects


# ------------------------------------------------------------ non-vacuity arm


def test_a_holder_that_never_takes_the_lock_is_CANNOT_MEASURE_not_PASS(
    tmp_path: Path,
) -> None:
    """If contention is never established, nothing was measured (§17).

    `venv_mutation_lock` replaced by a no-op context manager that the CHILD
    also uses, so the child exits/never announces. The gate must refuse to
    call that a pass. This is hazard 1 of the §7.12 list, driven.
    """
    broken = _planted(
        tmp_path,
        '    lock_dir = nix_home / "state"',
        '    raise SystemExit(7)\n    lock_dir = nix_home / "state"',
    )
    with pytest.raises(TimeoutError) as excinfo:
        _drive(broken)
    assert "nothing was measured" in str(excinfo.value)


def test_run_reports_CANNOT_MEASURE_when_the_subject_is_absent(
    tmp_path: Path,
) -> None:
    """An absent subject is CANNOT_MEASURE naming the path — never PASS (§17)."""
    result = gate.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "absent" in result.detail
