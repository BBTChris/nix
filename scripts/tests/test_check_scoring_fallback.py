"""ARC 036 sub-agent C — the standing suite over `check_scoring_fallback`.

Three kinds of test, and the split is the point:

* **BOTH HALVES ON A REAL SUBJECT.** A faithful copy of the modules under
  `tmp_path` is run through the SHIPPED gate three times: unbroken (must be
  green), with the reader's freshness threshold widened so the mirror can never
  go stale (must redden, naming the fallback that never fired), and with a
  `raise` planted on the order path that no dynamic arm can reach (must redden,
  naming the raise). The second break is the interesting one: it is invisible to
  every measurement the drill takes, and only the shape arm can see it. **No
  production artifact is edited — every plant lives under `tmp_path`**
  (doctrine C.8).

* **ONE END-TO-END RUN of the shipped gate against the real tree.** The only
  test that proves the gate's method executes at all against the artifacts that
  actually ship. A suite of arm tests over crafted inputs would be
  `docs/CHECK-DEBT.md` D3.16 exactly: a gate reporting PASS over a method nothing
  ever ran.

* **PER-ARM CAN-FAILS over crafted outcomes.** Each starts from an outcome the
  gate accepts and breaks ONE field, so a red is attributable to that arm.

**Every control asserts the REASON** — the named condition, in the verdict's own
detail or the process's own output — never the exit code alone (check contract
§18). That matters more here than almost anywhere: a killed process, a process
that failed to start, and a gate whose interpreter lacks `pyzmq` all reach the
same integer.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access,duplicate-code
# pylint: disable=use-implicit-booleaness-not-comparison
# `defects == []` asserts the TYPE and the emptiness together, the convention
# `scripts/tests/test_declarations.py` adopts: `not x` is also satisfied by
# `None`, so an arm that started returning None would pass a truthiness
# assertion while having measured nothing.
# `protected-access`: the can-fails drive the gate's ARMS, some of which are
# private by design; a public arm would be a surface invented for the test.

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - runs sys.executable on a staged copy, no shell
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_scoring_fallback as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_scoring_fallback.py"
FAILING = (Status.FAIL_NEEDS_OPERATOR, Status.FAIL_REPAIRABLE)

#: Ceiling on one staged gate run. The gate measures ~5.5 s on this node; the
#: budget is a broken-machine detector, not a performance assertion.
STAGED_TIMEOUT_S = 240

#: Packages the staged copy needs to be a working tree. Named rather than
#: copying `scripts/` wholesale: `docs/CHECK-DEBT.md` D3.206 is the row where
#: seven fixtures copied both venvs into `/tmp` and reported a full disk as 234
#: unrelated regressions.
_STAGED_PACKAGES = ("nixscore", "nixbus", "nixverify")


def _ctx() -> Context:
    return Context(nix_home=REPO, mode=Mode.VERIFY)


# ---------------------------------------------------------------------------
# BOTH HALVES, on a real subject staged under tmp_path
# ---------------------------------------------------------------------------


def _stage(tmp_path: Path) -> Path:
    """A faithful, minimal copy of the tree this gate needs. Never the venvs."""
    home = tmp_path / "tree"
    (home / "scripts").mkdir(parents=True)
    (home / "checks").mkdir()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for package in _STAGED_PACKAGES:
        shutil.copytree(
            REPO / "scripts" / package, home / "scripts" / package, ignore=ignore
        )
    shutil.copy2(REPO / "scripts" / "scoring_kill_drill.py", home / "scripts")
    shutil.copy2(REPO / "checks" / "_preamble.py", home / "checks")
    shutil.copy2(GATE_FILE, home / "checks")
    return home


def _run_staged(home: Path) -> subprocess.CompletedProcess[str]:
    """Run the staged gate as its own executable (check contract §4.2)."""
    return subprocess.run(  # nosec B603 - argv built here, no shell
        [sys.executable, str(home / "checks" / "check_scoring_fallback.py")],
        capture_output=True,
        text=True,
        timeout=STAGED_TIMEOUT_S,
        check=False,
    )


def _edit(path: Path, old: str, new: str) -> None:
    """Plant one edit, refusing silently-missed anchors."""
    source = path.read_text(encoding="utf-8")
    assert old in source, f"plant anchor missing from {path}: {old!r}"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def test_staged_tree_is_green_before_it_is_broken(tmp_path: Path) -> None:
    """The un-break half. A staging that cannot go green proves nothing about a red."""
    result = _run_staged(_stage(tmp_path))
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr[-2000:]!r}"
    )
    assert "SIGKILLed mid-contention" in result.stdout
    assert "reaped -9" in result.stdout


def test_a_mirror_that_can_never_go_stale_reddens_the_gate(tmp_path: Path) -> None:
    """BREAK THE SUBJECT: widen the freshness threshold so the CLOCK never fires.

    This is the failure §6.6:465 is written against, arriving the quiet way: the
    reader keeps answering, keeps answering CONFIDENTLY, and answers from a table
    whose writer is a corpse.

    **What this plant produces CHANGED in ARC 037, and the change is the repair.**
    Before liveness, widening the threshold made the reader rank from a corpse
    forever and ARM WINDOW said *"NEVER fell back to FCFS after Scoring died"*.
    Now the kill arm falls back anyway — on the writer's disconnect, in
    milliseconds, exactly as CHECK-DEBT D3.244 asked — so the break survives the
    death and is caught instead by ARM STALE, where the publisher stays ALIVE
    and only the clock can end the window. The next test drives the corpse case
    with liveness switched OFF, which is where the old reason still lives.
    """
    home = _stage(tmp_path)
    # `publisher.py` and not `process.py` since ARC 037's D3.271 collapse: the
    # reader the drill drives lives there now, and the gate DERIVES that rather
    # than being told, so the plant follows the class the same way the gate does.
    _edit(
        home / "scripts" / "nixscore" / "publisher.py",
        "self._mirror = RankingMirror(stale_after_s=stale_after_s, identity=identity)",
        "self._mirror = RankingMirror(stale_after_s=1e9, identity=identity)",
    )
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "the verdict does not follow the age" in result.stdout
    assert "stale-but-present" in result.stdout


def test_a_corpse_ranked_forever_reddens_the_window_arm(tmp_path: Path) -> None:
    """BREAK THE SUBJECT TWICE: no liveness observer AND a threshold that never trips.

    Together those restore the pre-ARC-037 world exactly — a reader with no way
    to learn the writer died and no clock that will ever say so — and ARM WINDOW
    must still be able to say *"NEVER fell back"*. Without this the arm's
    strongest finding would have no test left that can produce it, which is how
    a control goes blind while every suite stays green.
    """
    home = _stage(tmp_path)
    # ARC 037 STAGE 2 — RE-POINTED, and the re-point is the finding. This plant
    # named `nixscore/process.py`, because sub-agent D wrote it against the
    # `RankingReader` that lived there. Sub-agent F deleted that class in a
    # worktree D could not see (D3.271's duplicate) and the survivor is here.
    # `_edit` REFUSES a missing anchor rather than planting nothing, which is
    # the only reason this was a red test instead of a silently vacuous one.
    reader = home / "scripts" / "nixscore" / "publisher.py"
    _edit(
        reader,
        "self._mirror = RankingMirror(stale_after_s=stale_after_s, identity=identity)",
        "self._mirror = RankingMirror(stale_after_s=1e9, identity=identity)",
    )
    _edit(reader, "observe_liveness: bool = True", "observe_liveness: bool = False")
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "NEVER fell back to FCFS after Scoring died" in result.stdout


def test_a_raise_on_the_order_path_reddens_the_gate(tmp_path: Path) -> None:
    """BREAK THE SUBJECT: a `raise` on the order path that no drive can reach.

    The guard is unreachable, so every dynamic arm stays green and every measured
    number is unchanged. Only the shape arm can see it — which is the whole
    reason a shape arm exists next to a drill.
    """
    home = _stage(tmp_path)
    _edit(
        home / "scripts" / "nixscore" / "publisher.py",
        '        """Delegate to the frozen seam. Never blocks, never raises, never math."""\n',
        '        """Delegate to the frozen seam. Never blocks, never raises, never math."""\n'
        "        if first is None:\n"
        '            raise ValueError("unreachable")\n',
    )
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "can raise" in result.stdout
    assert "stall wearing a traceback" in result.stdout


def test_a_SECOND_RankingReader_in_the_package_reddens_the_gate(tmp_path: Path) -> None:
    """PLANT D3.271 ITSELF: re-introduce the duplicate class ARC 036 shipped.

    This is the state the tree was actually in — `nixscore.process.RankingReader`
    beside `nixscore.publisher.RankingReader` — and nothing in the tree could see
    it. The gate must now name BOTH files, not merely say a duplicate exists
    (check contract §18: assert the REASON).
    """
    home = _stage(tmp_path)
    process = home / "scripts" / "nixscore" / "process.py"
    process.write_text(
        process.read_text(encoding="utf-8")
        + "\n\nclass RankingReader:  # planted duplicate, D3.271\n"
        "    def arbitrate(self, first, second):\n"
        "        return self.mirror.arbitrate(first, second)\n",
        encoding="utf-8",
    )
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "2 classes named RankingReader" in result.stdout
    assert "scripts/nixscore/process.py" in result.stdout
    assert "scripts/nixscore/publisher.py" in result.stdout
    assert "D3.271" in result.stdout


# ---------------------------------------------------------------------------
# The shipped gate, against the shipped tree
# ---------------------------------------------------------------------------


def test_gate_passes_against_the_real_tree() -> None:
    """The only test that proves the METHOD runs against what actually ships."""
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "SIGKILLed mid-contention" in result.evidence
    assert "order-path exception(s)" in result.evidence


def test_declarations_are_present_and_honest() -> None:
    """§4.4's declaration set, read the way `verify.py` reads it: statically."""
    declared = read_declaration(GATE_FILE)
    # `publisher.py` joined in ARC 037: D3.271's collapse moved
    # `RankingReader.arbitrate` there and this gate's shape scan followed it.
    assert declared.subjects == (
        "scripts/nixscore/process.py",
        "scripts/nixscore/publisher.py",
        "scripts/scoring_kill_drill.py",
    )
    assert "zmq-ipc" in declared.resources
    assert "subprocess:python" in declared.resources
    assert "subprocess:python3" in declared.resources
    assert "file-write:/tmp" in declared.resources
    assert declared.depends_on == ("check_venv",)
    assert declared.on_fail == "continue"


# ---------------------------------------------------------------------------
# Per-arm can-fails
# ---------------------------------------------------------------------------


def test_every_plant_fires_and_names_a_reason() -> None:
    """The gate's own can-fail battery: each plant produces a REASON, not a flag."""
    plants = gate._plants()
    assert len(plants) >= 17
    for label, findings in plants:
        assert findings, f"{label} produced no finding"
        for site, why in findings:
            assert site, f"{label} produced a finding with no site"
            assert len(why) > 40, f"{label} finding is a flag, not a reason: {why!r}"


def test_arms_can_fail_reports_clean() -> None:
    """No arm is blind, and no arm is a false positive, on this revision."""
    assert gate._arms_can_fail() == ("", "")


def test_healthy_outcomes_produce_no_findings() -> None:
    """The other half of every arm: a clean subject must come back clean."""
    assert gate.kill_defects(gate._GOOD_KILL, gate._GOOD_CLEAN) == []
    assert gate.flow_defects(gate._GOOD_KILL) == []
    assert gate.live_before_defects(gate._GOOD_KILL) == []
    assert gate.window_defects(gate._GOOD_KILL) == []
    assert gate.control_defects(gate._GOOD_NO_KILL) == []
    assert gate.stale_defects(gate._GOOD_STALE) == []


def test_a_kill_that_was_really_an_exit_is_caught() -> None:
    """§18: the reaped status is the discriminator, and it must be asserted."""
    findings = gate.kill_defects(
        gate._with(gate._GOOD_KILL, reap_status=0), gate._GOOD_CLEAN
    )
    assert any("Only the kernel's reaped wait status" in why for _, why in findings)


def test_a_stale_table_read_as_fresh_is_caught() -> None:
    """C2's silent failure, stated by the arm that owns it."""
    broken = gate._with(
        gate._GOOD_STALE,
        outside=gate._with(gate._GOOD_SAMPLE_OUT, fresh=True, outcome="ranked"),
    )
    findings = gate.stale_defects(broken)
    assert any("silent failure" in why for _, why in findings)


def test_an_instant_fallback_is_caught_as_a_proxy() -> None:
    """A transition at t+0 means the trigger was liveness, not the table's age."""
    findings = gate.window_defects(
        gate._with(gate._GOOD_KILL, frozen_table_window_s=0.001)
    )
    assert any(
        "not being measured against real elapsed time" in why for _, why in findings
    )


def test_a_halt_reachable_from_the_scoring_module_is_caught() -> None:
    """§6.6 stated backwards: the optimization becoming the safety gate."""
    findings, scanned = gate.shape_defects(gate._HALTING)
    assert scanned == 1
    assert any("stated backwards" in why for _, why in findings)


def test_a_boundary_that_did_not_straddle_is_CANNOT_MEASURE_not_a_FAIL() -> None:
    """A red the scheduler earned is as dishonest as a green (CHECK-DEBT D3.204).

    Both samples on the same side of the threshold means the arm compared two
    readings instead of a fresh one with a stale one — no subject, so §17 says
    CANNOT_MEASURE. The verdict itself must still follow the MEASURED age, which
    is what keeps the overshoot from also producing a spurious defect.
    """
    overshot = gate._with(
        gate._GOOD_STALE,
        outside=gate._with(
            gate._GOOD_SAMPLE_OUT, observed_age_s=0.45, fresh=True, outcome="ranked"
        ),
    )
    assert "did NOT" in gate.boundary_unmeasurable(overshot)
    assert "D3.204" in gate.boundary_unmeasurable(overshot)
    # ... and the sample itself is CLEAN, because at 0.45s under a 0.5s
    # threshold `fresh=True` / `ranked` is the CORRECT answer.
    assert gate.stale_defects(overshot) == []
    assert gate.boundary_unmeasurable(gate._GOOD_STALE) == ""


def test_a_pure_delegation_is_not_flagged() -> None:
    """The arm must be able to say 'clean', or its findings carry no information."""
    findings, scanned = gate.shape_defects(gate._DELEGATING)
    assert scanned == 1
    assert findings == []
