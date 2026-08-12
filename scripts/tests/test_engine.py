"""Engine execution semantics per nix_check_contract.md §6, §8."""

from pathlib import Path

from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.engine import aggregate_exit, run_blocks
from nixverify.registry import Block

PASSING = (
    "def run(mode, ctx):\n"
    "    from nixverify.contract import CheckResult, Status\n"
    "    return CheckResult(name='x', status=Status.PASS, evidence='measured')\n"
)
FAILING = (
    "def run(mode, ctx):\n"
    "    from nixverify.contract import CheckResult, Status\n"
    "    return CheckResult(name='x', status=Status.FAIL_REPAIRABLE, site='s')\n"
)
RAISING = "def run(mode, ctx):\n    raise RuntimeError('boom')\n"


def _plugin(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")


def _ctx(tmp_path: Path, **kw: object) -> Context:
    return Context(nix_home=tmp_path, mode=Mode.VERIFY, **kw)  # type: ignore[arg-type]


def test_raising_check_becomes_cannot_measure_not_a_crash(tmp_path: Path) -> None:
    """A check that raises must not crash the engine."""
    _plugin(tmp_path, "check_boom", RAISING)
    results = run_blocks(
        (Block(name="b", checks=("check_boom",)),), tmp_path, _ctx(tmp_path)
    )
    assert results[0].status is Status.CANNOT_MEASURE
    assert "boom" in results[0].detail


def test_load_error_becomes_cannot_measure(tmp_path: Path) -> None:
    """A missing check module is uncertainty, not a failure."""
    results = run_blocks(
        (Block(name="b", checks=("check_absent",)),), tmp_path, _ctx(tmp_path)
    )
    assert results[0].status is Status.CANNOT_MEASURE


def test_halt_skips_all_later_blocks(tmp_path: Path) -> None:
    """on_fail='halt' must skip every later block, not just the next one."""
    _plugin(tmp_path, "check_bad", FAILING)
    _plugin(tmp_path, "check_later", PASSING)
    results = run_blocks(
        (
            Block(name="floor", checks=("check_bad",), on_fail="halt"),
            Block(name="rest", checks=("check_later",)),
        ),
        tmp_path,
        _ctx(tmp_path),
    )
    assert results[0].status is Status.FAIL_REPAIRABLE
    assert results[1].status is Status.SKIPPED
    assert "floor" in results[1].detail
    assert "rest" not in results[1].detail


def test_continue_runs_later_blocks(tmp_path: Path) -> None:
    """§6 default: one unrelated failure must not blind the operator."""
    _plugin(tmp_path, "check_bad", FAILING)
    _plugin(tmp_path, "check_later", PASSING)
    results = run_blocks(
        (
            Block(name="one", checks=("check_bad",)),
            Block(name="two", checks=("check_later",)),
        ),
        tmp_path,
        _ctx(tmp_path),
    )
    assert results[1].status is Status.PASS


def _sleeping_check(seconds: float) -> str:
    """A passing check body that sleeps first, to stagger completion order."""
    return (
        "def run(mode, ctx):\n"
        "    import time\n"
        f"    time.sleep({seconds})\n"
        "    from nixverify.contract import CheckResult, Status\n"
        "    return CheckResult(name='x', status=Status.PASS, evidence='measured')\n"
    )


def test_parallel_block_reports_in_registry_order(tmp_path: Path) -> None:
    """§6: completion order must never leak into output — runs must diff.

    Durations are staggered so that completion order is the exact reverse of
    registry order (check_a finishes last, check_c finishes first). A version
    that reads results via as_completed() instead of submission order would
    report [check_c, check_b, check_a] here and fail.
    """
    _plugin(tmp_path, "check_a", _sleeping_check(0.15))
    _plugin(tmp_path, "check_b", _sleeping_check(0.05))
    _plugin(tmp_path, "check_c", _sleeping_check(0.0))
    results = run_blocks(
        (Block(name="p", checks=("check_a", "check_b", "check_c"), parallel=True),),
        tmp_path,
        _ctx(tmp_path),
    )
    assert [r.name for r in results] == ["check_a", "check_b", "check_c"]


def test_wrong_privilege_is_skipped(tmp_path: Path) -> None:
    """A root check must not run under a user-privilege run."""
    _plugin(tmp_path, "check_root", 'PRIVILEGE = "root"\n' + PASSING)
    results = run_blocks(
        (Block(name="b", checks=("check_root",)),),
        tmp_path,
        _ctx(tmp_path, privilege="user"),
    )
    assert results[0].status is Status.SKIPPED
    assert "privilege" in results[0].detail


def test_privilege_all_runs_both_user_and_root_checks(tmp_path: Path) -> None:
    """§8: install.sh runs everything in one pass; the units run subsets."""
    _plugin(tmp_path, "check_user", PASSING)
    _plugin(tmp_path, "check_root", 'PRIVILEGE = "root"\n' + PASSING)
    results = run_blocks(
        (Block(name="b", checks=("check_user", "check_root")),),
        tmp_path,
        _ctx(tmp_path, privilege="all"),
    )
    assert [r.status for r in results] == [Status.PASS, Status.PASS]


def test_interactive_check_is_skipped_headless(tmp_path: Path) -> None:
    """A headless run must not block waiting on an operator."""
    _plugin(tmp_path, "check_ask", "INTERACTIVE = True\n" + PASSING)
    results = run_blocks(
        (Block(name="b", checks=("check_ask",)),), tmp_path, _ctx(tmp_path)
    )
    assert results[0].status is Status.SKIPPED


def test_interactive_check_runs_when_explicitly_allowed(tmp_path: Path) -> None:
    """Without this, an INTERACTIVE check could never run anywhere."""
    _plugin(tmp_path, "check_ask", "INTERACTIVE = True\n" + PASSING)
    results = run_blocks(
        (Block(name="b", checks=("check_ask",)),),
        tmp_path,
        _ctx(tmp_path, allow_interactive=True),
    )
    assert results[0].status is Status.PASS


DISRUPTIVE_MUTATING = (
    "DISRUPTIVE = True\n"
    "def run(mode, ctx):\n"
    "    from nixverify.contract import CheckResult, Status\n"
    "    if mode == 'correct':\n"
    "        (ctx.nix_home / 'mutated.txt').write_text('mutated', encoding='utf-8')\n"
    "    return CheckResult(name='x', status=Status.FAIL_REPAIRABLE, site='s',"
    " detail='would repair')\n"
)


def test_disruptive_check_downgraded_outside_maintenance(tmp_path: Path) -> None:
    """§8: a boot can happen mid-session — the repair must not fire, but the
    inspection must still run and report, or drift goes unseen until Saturday.

    Task 9 review, Finding 1: the prior behaviour (SKIPPED) lost the report
    along with the repair. DISRUPTIVE gates the repair only; inspecting
    changes nothing, so it must run at Mode.VERIFY regardless of the
    requested mode.
    """
    _plugin(tmp_path, "check_restart", DISRUPTIVE_MUTATING)
    ctx = Context(nix_home=tmp_path, mode=Mode.CORRECT, maintenance=False)
    results = run_blocks((Block(name="b", checks=("check_restart",)),), tmp_path, ctx)
    assert results[0].status is Status.FAIL_REPAIRABLE
    assert "maintenance" in results[0].detail
    # The discriminating proof: the fixture only mutates when it is actually
    # invoked with mode == 'correct'. A downgrade that skipped instead, or
    # that downgraded the report but not the actual mode passed to run(),
    # would leave this assertion unable to tell the difference from a real
    # repair having fired.
    assert not (tmp_path / "mutated.txt").exists()


def test_disruptive_check_downgraded_pass_has_no_withheld_note(tmp_path: Path) -> None:
    """Task 9 second review, Finding B: the withheld note describes a repair
    that was held back. Appending it to a PASS — where no repair was ever
    contemplated because nothing was wrong — reads as though something was
    withheld when nothing was.
    """
    _plugin(tmp_path, "check_restart", "DISRUPTIVE = True\n" + PASSING)
    ctx = Context(nix_home=tmp_path, mode=Mode.CORRECT, maintenance=False)
    results = run_blocks((Block(name="b", checks=("check_restart",)),), tmp_path, ctx)
    assert results[0].status is Status.PASS
    assert results[0].detail == ""


def test_disruptive_check_runs_in_maintenance(tmp_path: Path) -> None:
    """The maintenance window is what permits a disruptive repair to fire."""
    _plugin(tmp_path, "check_restart", "DISRUPTIVE = True\n" + PASSING)
    ctx = Context(nix_home=tmp_path, mode=Mode.CORRECT, maintenance=True)
    results = run_blocks((Block(name="b", checks=("check_restart",)),), tmp_path, ctx)
    assert results[0].status is Status.PASS


def test_disruptive_check_runs_in_verify_mode_because_it_changes_nothing(
    tmp_path: Path,
) -> None:
    """DISRUPTIVE gates the repair, not the inspection."""
    _plugin(tmp_path, "check_restart", "DISRUPTIVE = True\n" + PASSING)
    ctx = Context(nix_home=tmp_path, mode=Mode.VERIFY, maintenance=False)
    results = run_blocks((Block(name="b", checks=("check_restart",)),), tmp_path, ctx)
    assert results[0].status is Status.PASS


def test_vacuous_pass_is_rejected_end_to_end(tmp_path: Path) -> None:
    """§5 enforced by the engine, not merely by the check author."""
    _plugin(
        tmp_path,
        "check_vacuous",
        "def run(mode, ctx):\n"
        "    from nixverify.contract import CheckResult, Status\n"
        "    return CheckResult(name='x', status=Status.PASS)\n",
    )
    results = run_blocks(
        (Block(name="b", checks=("check_vacuous",)),), tmp_path, _ctx(tmp_path)
    )
    assert results[0].status is Status.CANNOT_MEASURE


def test_aggregate_exit_prefers_failure_over_cannot_measure() -> None:
    """§4.2 aggregate precedence."""
    assert aggregate_exit([CheckResult("a", Status.PASS, evidence="e")]) == 0
    assert (
        aggregate_exit(
            [
                CheckResult("a", Status.CANNOT_MEASURE),
                CheckResult("b", Status.FAIL_REPAIRABLE, site="s"),
            ]
        )
        == 1
    )
    assert aggregate_exit([CheckResult("a", Status.CANNOT_MEASURE)]) == 2
    assert aggregate_exit([]) == 0
