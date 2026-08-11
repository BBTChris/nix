"""ARC 024 Stage 2 — actuation verbs, the refusal paths, and the re-verify control.

The load-bearing test in this file is
`test_reverify_FAILS_after_a_successful_looking_correction`. §2.2's ruling is
that a post-actuation confirmation must be an independent re-measurement rather
than a return value from the correcting path, and that claim is only worth
anything if the re-measurement can actually disagree. This file makes it
disagree, on purpose, and asserts the disagreement wins.
"""
# pylint: disable=invalid-name,import-outside-toplevel,use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test on purpose; `== ()` is asserted
# rather than `not x` because an empty tuple and a falsey non-tuple are
# different outcomes here; late imports are the sys.path bootstrap this suite
# needs. Each is deliberate, so the pragma is per-file and named.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixverify.actuation import (  # pylint: disable=wrong-import-position
    ActuationRefused,
    Reverification,
    guard_mutation,
    parse_actuation,
    reverify,
    session_state,
    standalone_main,
)
from nixverify.contract import (  # pylint: disable=wrong-import-position
    CheckResult,
    Context,
    Mode,
    Status,
)

# --------------------------------------------------------------- flag surface


def test_no_flags_means_measure_only() -> None:
    """The default must never mutate. This is the whole safety posture."""
    assert parse_actuation([], prog="x").mode is Mode.VERIFY


def test_correct_and_install_are_explicit_and_mutually_exclusive() -> None:
    """A mutation requires someone to have typed it."""
    assert parse_actuation(["--correct"], prog="x").mode is Mode.CORRECT
    assert parse_actuation(["--install"], prog="x").mode is Mode.INSTALL
    with pytest.raises(SystemExit):
        parse_actuation(["--correct", "--install"], prog="x")


# ------------------------------------------------------------------- refusals


def test_a_non_correctable_check_refuses_and_names_its_reason() -> None:
    """§2.3. The refusal must carry the reason, not just decline."""
    with pytest.raises(ActuationRefused) as excinfo:
        guard_mutation(Mode.CORRECT, False, "the order path", "check_x")
    assert "NON-CORRECTABLE" in str(excinfo.value)
    assert "the order path" in str(excinfo.value)


def test_a_non_correctable_check_still_verifies() -> None:
    """Refusing to mutate must not refuse to measure."""
    guard_mutation(Mode.VERIFY, False, "the order path", "check_x")


def test_the_per_check_refusal_precedes_the_session_interlock() -> None:
    """Order matters, and the reason is subtle.

    If the interlock ran first on a busy box, a non-correctable check would
    report "a session is running" — and the operator would infer, wrongly, that
    correction becomes available once the session ends. It never does.
    """
    with pytest.raises(ActuationRefused) as excinfo:
        guard_mutation(Mode.CORRECT, False, "credentials", "check_x", force=True)
    assert "NON-CORRECTABLE" in str(excinfo.value)


def test_force_is_not_an_override_for_the_interlock() -> None:
    """§2.4 is fail-closed; a flag that unlocked it would make it decoration."""
    state = session_state()
    if state.permits_mutation:
        pytest.skip(
            "box measures INACTIVE; the override path needs a non-permitting state"
        )
    with pytest.raises(ActuationRefused) as excinfo:
        guard_mutation(Mode.CORRECT, True, "", "check_x", force=True)
    assert "not an override" in str(excinfo.value)


def test_session_state_is_one_of_exactly_three_verdicts() -> None:
    """UNKNOWN is a real state, not an error. A two-state interlock must guess."""
    assert session_state().verdict in {"active", "inactive", "unknown"}


def test_only_a_positively_measured_inactive_permits_mutation() -> None:
    """Absence of evidence is not evidence of a flat book."""
    from nixverify.actuation import SessionState

    assert SessionState("inactive", "").permits_mutation is True
    assert SessionState("active", "").permits_mutation is False
    assert SessionState("unknown", "").permits_mutation is False


# ------------------------------------------------------- the re-verify control


_LYING_CHECK = '''\
"""A check that reports success in CORRECT mode and failure when re-measured.

This is a CONTROL, not a check. It exists to prove the post-actuation re-verify
is independent: `run()` under CORRECT returns PASS unconditionally, exactly as a
`correct()`-returned-True code path would, while a fresh verify-only process
reports the real state and fails.
"""
import sys
from pathlib import Path
sys.path.append(__SCRIPTS__)
from nixverify.contract import CheckResult, Context, Mode, Status, validate_result

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
DEPENDS_ON = ()
RESOURCES = ()
CORRECTABLE = True
NON_CORRECTABLE_REASON = ""


def run(mode, ctx):
    if mode.rank > Mode.VERIFY.rank:
        # The correcting path is delighted with itself.
        return CheckResult(
            name="check_lying", status=Status.PASS, evidence="correct() returned True"
        )
    # The real effective state, read fresh, disagrees.
    return CheckResult(
        name="check_lying",
        status=Status.FAIL_NEEDS_OPERATOR,
        site="the real subject",
        evidence="re-measured",
        detail="the correction did not take",
    )


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(Path(__file__).resolve(), run, "check_lying")
    )
'''


def test_reverify_FAILS_after_a_successful_looking_correction(tmp_path: Path) -> None:
    """§2.2's control, and the reason the re-verify is a subprocess.

    `run(CORRECT)` returns PASS. If the confirmation were the correcting path's
    return value — the project's signature defect, an instrument reporting on a
    state it just wrote — this would exit 0 and report a vacuous success. The
    independent re-measurement reports the real state, and its verdict is the
    one that survives.
    """
    checks = tmp_path / "checks"
    checks.mkdir()
    check = checks / "check_lying.py"
    check.write_text(
        _LYING_CHECK.replace("__SCRIPTS__", repr(str(REPO / "scripts"))),
        encoding="utf-8",
    )

    # The correcting path alone says PASS...
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_lying_probe", check)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    optimistic = module.run(Mode.CORRECT, Context(nix_home=tmp_path, mode=Mode.CORRECT))
    assert optimistic.status is Status.PASS, "the control must look successful"

    # ...and the independent re-measurement disagrees, and wins.
    proc = subprocess.run(
        [sys.executable, str(check), str(tmp_path), "--correct"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 1, (
        "standalone_main returned the CORRECTION's verdict, not the re-verify's "
        f"— stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "RE-VERIFY DID NOT CONFIRM" in proc.stderr


def test_verify_only_on_the_same_control_needs_no_reverify(tmp_path: Path) -> None:
    """Without a mutation there is nothing to re-confirm, and none is run."""
    checks = tmp_path / "checks"
    checks.mkdir()
    check = checks / "check_lying.py"
    check.write_text(
        _LYING_CHECK.replace("__SCRIPTS__", repr(str(REPO / "scripts"))),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(check), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 1
    assert "re-verify" not in proc.stdout


def test_reverify_of_a_missing_check_is_cannot_measure(tmp_path: Path) -> None:
    """A re-verify that could not run is never read as confirmation."""
    outcome = reverify(tmp_path / "nope.py", tmp_path, timeout=30)
    assert outcome.exit_code == 2
    assert outcome.confirmed is False


def test_only_exit_zero_counts_as_confirmed() -> None:
    """Exit 2 is 'I could not tell', which is not a confirmation."""
    assert Reverification(0, "", "").confirmed is True
    assert Reverification(1, "", "").confirmed is False
    assert Reverification(2, "", "").confirmed is False
    assert Reverification(3, "", "").confirmed is False


# ------------------------------------------------------ the real pilot surface


@pytest.mark.parametrize(
    "pilot", ["check_python_deps", "check_venv", "check_order_path_bans"]
)
def test_each_pilot_exposes_the_actuation_flags(pilot: str) -> None:
    """The three Stage 6 pilots must all answer --help with the full surface."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "checks" / f"{pilot}.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for flag in ("--correct", "--install", "--force"):
        assert flag in proc.stdout, f"{pilot} does not expose {flag}"


def test_the_order_path_pilot_refuses_correction_for_its_declared_reason() -> None:
    """§2.3's charter member, driven end to end against the real check."""
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "checks" / "check_order_path_bans.py"),
            "--correct",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 1
    assert "NON-CORRECTABLE" in proc.stderr
    assert "order path" in proc.stderr


def test_standalone_main_is_importable_by_every_retrofitted_check() -> None:
    """Guards against the shared helper drifting out from under the pilots."""
    assert callable(standalone_main)
    assert isinstance(CheckResult(name="x", status=Status.PASS), CheckResult)
