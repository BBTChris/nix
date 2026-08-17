"""`check_monitor_tui` — the DETECTION can-fail, committed rather than banked.

ARC 035 / Phase 0.2. The three MON-1 artifacts (`monitor.py`, `harness.py`,
`pty_test.py`) had been carried in `gate_coverage_baseline.json`'s `artifacts`
ratchet across four arcs with three re-ownings — one over the ceiling. D3.113
had recorded that *"a plant here would measure nothing"*. This suite is the
refutation: the plants below measure a great deal.

The expensive arm is `test_a_dishonest_gauge_reddens_arm_1`, which copies the
three artifacts to a scratch tree, breaks the ONE doctrine sentence `monitor.py`
opens with — *"A number with no denominator prints N/A, never a guess"* — and
drives the SHIPPED gate against the broken tree. It runs the real child
processes, so it is slow, and it is the arm that proves the gate is an
instrument rather than a declaration.
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

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
import check_monitor_tui as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

_ARTIFACTS = ("monitor.py", "harness.py", "pty_test.py")


def _scratch_tree(tmp_path: Path) -> Path:
    """A scratch `nix_home` holding copies of all three MON-1 artifacts."""
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    for name in _ARTIFACTS:
        shutil.copyfile(REPO / "scripts" / name, home / "scripts" / name)
    return home


# ------------------------------------------------------------- the CONTROL


def test_control_the_shipped_tree_passes_with_the_pin_exact() -> None:
    """The shipped gate against the shipped tree: PASS, pin exact.

    Without this, a red below could be the harness rather than the plant.

    CANNOT_MEASURE is accepted here and PASS is not merely hoped for: this test
    runs inside the full suite, on a box the suite itself is loading, and the
    timing-sensitive pty arm (D3.204) can legitimately withhold the verdict.
    What is NOT accepted is a FAIL, and what is asserted in the CANNOT_MEASURE
    branch is that the withholding names its own reason — the distinction
    between "the box was busy" and "the subject broke" is exactly what would be
    lost by tolerating the arm instead.
    """
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    if result.status is Status.CANNOT_MEASURE:
        assert "timing-sensitive" in result.detail, result.detail
        assert "D3.204" in result.detail
        return
    assert result.status is Status.PASS, result.detail
    assert "EXACTLY the recorded pin" in result.evidence
    assert "not a certification that" in result.evidence


# ------------------------------------------------- ARM 1, driven for real


def test_a_dishonest_gauge_reddens_arm_1(tmp_path: Path) -> None:
    """`build_gauge` invents a denominator it does not have.

    `monitor.py`'s own header doctrine: *"Every gauge names its basis and sample
    size. A number with no denominator prints N/A, never a guess."* The plant
    makes the prior-less path fabricate `100.0`, which is precisely a guess
    wearing a measurement's clothes — the class of defect the whole TUI's
    doctrine section exists to forbid, and the class this project calls "green
    while measuring nothing" everywhere else.

    Slow by construction: it runs the real `--selftest`, the real pty loop and
    the real harness against the broken tree.
    """
    home = _scratch_tree(tmp_path)
    monitor = home / "scripts" / "monitor.py"
    source = monitor.read_text()
    anchor = 'return Gauge(used, prior if prior > 0 else None, "prior", 0, 0.0)'
    assert source.count(anchor) == 1, (
        f"plant anchor appears {source.count(anchor)} times, not once — "
        f"a plant that matches nothing plants nothing (debug.md §8 #4)"
    )
    monitor.write_text(
        source.replace(
            anchor,
            'return Gauge(used, prior if prior > 0 else 100.0, "prior", 0, 0.0)',
        )
    )
    defects, _counts = gate.drive_artifacts(home, sys.executable)
    assert any(d.startswith("ARM1") for d in defects), defects
    assert any("--selftest rc=" in d for d in defects), defects


def test_run_reports_CANNOT_MEASURE_when_an_artifact_is_absent(
    tmp_path: Path,
) -> None:
    """An absent artifact is CANNOT_MEASURE naming it — never PASS (§17)."""
    home = _scratch_tree(tmp_path)
    (home / "scripts" / "pty_test.py").unlink()
    result = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "scripts/pty_test.py" in result.detail
    assert "nothing was measured" in result.detail


# ---------------------------------- ARM 2, and the timing-sensitive split


_PTY_STUB = """\
import sys
print("  ok   pty: alt screen entered")
print("  ok   pty: painted a frame")
{lines}
print("PTY RESULT: 1 failures")
sys.exit(1)
"""


def _stub_pty(home: Path, failing_arm: str) -> None:
    (home / "scripts" / "pty_test.py").write_text(
        _PTY_STUB.format(lines=f'print("  FAIL {failing_arm} :: detail")')
    )


def test_a_timing_sensitive_pty_arm_alone_is_CANNOT_MEASURE(tmp_path: Path) -> None:
    """The measured flake (D3.204), driven.

    A deadline missed on a busy box is not evidence about `monitor.py`. The
    available cheap fix was to drop the arm from ARM 2 entirely; that would
    make a real regression in the resize path invisible forever. CANNOT_MEASURE
    withholds the green and stays loud.
    """
    home = _scratch_tree(tmp_path)
    _stub_pty(home, "pty: survives resize storm")
    defects, _ = gate.drive_artifacts(home, sys.executable)
    assert any(d.startswith("ARM2 CANNOT_MEASURE") for d in defects), defects
    assert any("D3.204" in d for d in defects), defects
    assert not any(d.startswith("ARM2:") for d in defects), defects


def test_a_non_timing_pty_arm_is_a_real_FAIL(tmp_path: Path) -> None:
    """The other direction: the split must not swallow real breakage.

    `pty: alt screen restored` failing means the TUI left the operator's
    terminal in the alternate screen — a real, reproducible defect with no
    clock in it. It is a FAIL, and the CANNOT_MEASURE branch must not reach it.
    """
    home = _scratch_tree(tmp_path)
    _stub_pty(home, "pty: alt screen restored")
    defects, _ = gate.drive_artifacts(home, sys.executable)
    assert any(d.startswith("ARM2:") and "alt screen restored" in d for d in defects), (
        defects
    )
    assert not any(d.startswith("ARM2 CANNOT_MEASURE") for d in defects), defects


def test_a_hard_failure_alongside_a_timing_one_is_still_a_FAIL(
    tmp_path: Path,
) -> None:
    """A real break may not hide behind a flake sharing the same run."""
    home = _scratch_tree(tmp_path)
    (home / "scripts" / "pty_test.py").write_text(
        _PTY_STUB.format(
            lines='print("  FAIL pty: survives resize storm :: d")\n'
            'print("  FAIL pty: no traceback overall :: d")'
        )
    )
    defects, _ = gate.drive_artifacts(home, sys.executable)
    assert any(d.startswith("ARM2:") for d in defects), defects
    assert any("no traceback overall" in d for d in defects), defects
    assert any("plus timing-sensitive" in d for d in defects), defects


def test_a_pty_driver_that_dies_with_no_arms_is_not_excused(
    tmp_path: Path,
) -> None:
    """Zero reported arms and a non-zero exit is a dead driver, not a flake."""
    home = _scratch_tree(tmp_path)
    (home / "scripts" / "pty_test.py").write_text("import sys; sys.exit(3)")
    defects, _ = gate.drive_artifacts(home, sys.executable)
    assert any("did not run to completion" in d for d in defects), defects


def test_only_the_measured_arm_is_declared_timing_sensitive() -> None:
    """One arm, because one is what was observed.

    Adding `pty: still alive after force probe` on the grounds that it "looks
    like the same class" would convert a real future break into a shrug. If it
    ever flakes, that is a new measurement and a new row.
    """
    assert gate._TIMING_SENSITIVE_PTY_ARMS == frozenset({"pty: survives resize storm"})


# ------------------------------------------- ARM 3, the two-way pin itself


_HARNESS_SAMPLE = """\
SCENARIO 1
  ok   alpha
  FAIL beta :: some detail
  ok   gamma  :: with detail
  FAIL beta :: a second call site with the same name
not a result line at all
"""


def test_parse_harness_reads_both_verdicts_and_keeps_duplicates() -> None:
    """Duplicates are preserved because two call sites are two facts.

    `4K shows wtok used` really is asserted twice in the shipped harness. A set
    would collapse them, and the repair of exactly one would then be invisible
    in BOTH directions.
    """
    oks, fails = gate.parse_harness(_HARNESS_SAMPLE)
    assert oks == ["alpha", "gamma"]
    assert fails == ["beta", "beta"]


def test_an_exact_match_is_clean() -> None:
    assert not gate.compare_to_pin(["a", "b"], ("b", "a"))


def test_a_new_failure_is_a_REGRESSION() -> None:
    """A red that is not in the pin is new breakage, named."""
    defects = gate.compare_to_pin(["a", "b", "c"], ("a", "b"))
    assert len(defects) == 1
    assert defects[0].startswith("ARM3 REGRESSION")
    assert "c" in defects[0]


def test_a_repaired_arm_is_a_STALE_PIN() -> None:
    """The direction that stops this becoming a suppression file.

    A pin that only ever grows accepts everything eventually. A recorded red
    that stopped failing means the record is lying about the subject, and the
    gate says so instead of quietly enjoying the improvement.
    """
    defects = gate.compare_to_pin(["a"], ("a", "b"))
    assert len(defects) == 1
    assert defects[0].startswith("ARM3 STALE PIN")
    assert "b" in defects[0]
    assert "suppression file" in defects[0]


def test_one_arm_repaired_and_one_broken_reports_BOTH() -> None:
    """The counts match, so a naive length comparison would report clean."""
    defects = gate.compare_to_pin(["a", "z"], ("a", "b"))
    assert len(defects) == 2
    assert any(d.startswith("ARM3 REGRESSION") and "z" in d for d in defects)
    assert any(d.startswith("ARM3 STALE PIN") and "b" in d for d in defects)


def test_losing_one_of_two_identical_names_is_a_STALE_PIN() -> None:
    """The duplicate case, driven: one of the two `4K` sites repaired."""
    defects = gate.compare_to_pin(["dup"], ("dup", "dup"))
    assert len(defects) == 1
    assert defects[0].startswith("ARM3 STALE PIN")


def test_the_recorded_pin_is_non_empty() -> None:
    """Hazard 1 of the §7.12 list: an empty pin matches an empty crash.

    If `KNOWN_RED` is ever emptied by a real repair, this assertion is what
    forces the floor argument to be re-made rather than silently inherited.
    """
    assert gate.KNOWN_RED
    assert gate.MIN_CREDIBLE_CHECKS > 0


def test_a_harness_that_dies_early_is_CANNOT_MEASURE_not_PASS(
    tmp_path: Path,
) -> None:
    """A crashed harness reports a small arm population, not a clean one.

    Plant: `harness.py` replaced by a stub that prints three passing arms and
    exits 0. Its failing set is empty, which is *better* than the pin, so the
    stale-pin arm would already redden — but the floor is what makes the
    verdict CANNOT_MEASURE (nothing ran) rather than FAIL (something ran and
    disagreed). The distinction is the whole of §17.
    """
    home = _scratch_tree(tmp_path)
    (home / "scripts" / "harness.py").write_text(
        "print('  ok   a')\nprint('  ok   b')\nprint('  ok   c')\n"
    )
    defects, counts = gate.drive_artifacts(home, sys.executable)
    assert counts["total"] == 3
    assert any(d.startswith("ARM3 CANNOT_MEASURE") for d in defects), defects
    result = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "did not run to completion" in result.detail
