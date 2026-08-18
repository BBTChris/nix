"""ARC 037 sub-agent D — the standing suite over `check_mirror_liveness`.

Three kinds of test, and the split is the point:

* **BOTH HALVES ON A REAL SUBJECT.** A faithful copy of the modules under
  `tmp_path` is run through the SHIPPED gate: unbroken (must be green), and then
  with each of three plants that a green gate must not survive — the disconnect
  latch removed, so the mirror ranks from a corpse again; the heartbeat deadline
  neutered, so the wedged publisher goes unseen; and the mirror's TRIGGER 6
  deleted, so the observation is made and then ignored. **No production artifact
  is edited — every plant lives under `tmp_path`** (doctrine C.8).

* **ONE END-TO-END RUN of the shipped gate against the real tree.** The only
  test that proves the gate's method executes against the artifacts that
  actually ship. A suite of arm tests over crafted inputs would be
  `docs/CHECK-DEBT.md` D3.16 exactly: a gate reporting PASS over a method
  nothing ever ran.

* **PER-ARM CAN-FAILS over crafted outcomes.** Each starts from an outcome the
  gate accepts and breaks ONE field, so a red is attributable to that arm.

**Every control asserts the REASON** — the named condition in the gate's own
detail or output — never the exit code alone (check contract §18). A killed
process, a process that failed to start, and a gate whose interpreter lacks
`pyzmq` all reach the same integer.
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

import os
import shutil
import subprocess  # nosec B404 - runs sys.executable on a staged copy, no shell
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_mirror_liveness as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_mirror_liveness.py"

#: Ceiling on one staged gate run. The gate measures ~6 s on this node; the
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
    shutil.copy2(REPO / "checks" / "_preamble.py", home / "checks")
    shutil.copy2(GATE_FILE, home / "checks")
    return home


def _run_staged(home: Path) -> subprocess.CompletedProcess[str]:
    """Run the staged gate as its own executable (check contract §4.2).

    **THE ENVIRONMENT IS SCRUBBED, AND IT IS THE WHOLE POINT OF THE FUNCTION.**
    MEASURED, ARC 037 Stage 3.4: this call used to inherit the parent's
    environment. `scripts/tests/binding_census.py` runs the suite with
    `PYTHONPATH = <sitedir>:REPO/scripts:REPO/scripts/tests` so its tracer
    reaches every child interpreter — and the staged gate, launched from
    `/tmp/.../tree/checks/`, then imported `nixscore` **from the REAL tree**
    instead of from the staged one. Every plant in this file was silently
    defeated: the gate measured production code while reporting on a staged
    tree, and PASSED.

    Proven by driving ONE staged, planted tree twice, changing nothing but the
    environment: `PYTHONPATH` unset -> **RED, plant detected**; `PYTHONPATH`
    set to the real `scripts/` -> **GREEN, plant defeated**. The consequence was
    visible in the binding table before the cause was: `check_mirror_liveness`
    read EXERCISED-NEVER-RED over sixteen observations, all of them PASS,
    because under the census not one of its plants could fire.

    This is D3.205's class one layer over — an inherited environment variable
    silently re-pointing a subprocess at the wrong tree — and the repair is the
    same shape: name the environment the child gets instead of inheriting it.

    **THE FIRST REPAIR WAS TOO BROAD, AND THE BINDING CENSUS SAID SO.**
    Replacing `PYTHONPATH` outright also dropped `binding_census.py`'s
    `sitecustomize` directory, which is the only way its tracer reaches a child
    — so the staged runs stopped being OBSERVED at all and
    `check_scoring_fallback` went BOUND -> EXERCISED-NEVER-RED, taking the table
    78 -> 77. Correct plants, invisible to the instrument: the repair for a gate
    that measures the wrong tree must not become a gate nothing can watch.
    Both properties are wanted at once, so the REAL-TREE entries are filtered
    out and every other inherited entry is KEPT.
    """
    repo_entries = {
        str(REPO / "scripts"),
        str(REPO / "scripts" / "tests"),
        str(REPO / "checks"),
    }
    inherited = [
        part
        for part in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if part and part not in repo_entries
    ]
    env = dict(os.environ)
    # The staged tree FIRST and the real tree NOWHERE, but anything else the
    # parent put on the path — a tracer's sitedir above all — is preserved.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(home / "scripts"), str(home / "checks"), *inherited]
    )
    return subprocess.run(  # nosec B603 - argv built here, no shell
        [sys.executable, str(home / "checks" / "check_mirror_liveness.py")],
        capture_output=True,
        text=True,
        timeout=STAGED_TIMEOUT_S,
        check=False,
        env=env,
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
    assert "RANKED decision(s) from the corpse" in result.stdout
    assert "BLIND reader" in result.stdout


def test_removing_the_disconnect_latch_reddens_the_gate(tmp_path: Path) -> None:
    """PLANT: the observer sees `EVENT_DISCONNECTED` and does not latch on it.

    This is D3.244 restored in the most plausible way an implementation could
    regress into it: everything is still there — the monitor socket, the drain,
    the counters, the reason strings — and the one line that turns an event into
    a verdict is gone. The window goes back to being a function of
    `stale_after_s`, and the mirror ranks from a corpse again.
    """
    home = _stage(tmp_path)
    _edit(
        home / "scripts" / "nixscore" / "liveness.py",
        "            elif code in _DEAD_EVENTS:\n"
        "                if code == int(zmq.EVENT_DISCONNECTED):\n"
        "                    self.disconnects += 1\n"
        "                self._peer = False\n",
        "            elif code in _DEAD_EVENTS:\n"
        "                if code == int(zmq.EVENT_DISCONNECTED):\n"
        "                    self.disconnects += 1\n",
    )
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "RANKED from the dead process's frozen table" in result.stdout
    assert "D3.244" in result.stdout


def test_neutering_the_heartbeat_reddens_the_gate(tmp_path: Path) -> None:
    """PLANT: the SECOND signal never fires, so a wedged publisher is invisible.

    The peer signal is untouched, so the kill arm stays green — which is exactly
    the shape of the defect this arm exists over: a process that is alive and
    has stopped working never disconnects, and a gate that only ever killed
    things would never notice.
    """
    home = _stage(tmp_path)
    _edit(
        home / "scripts" / "nixscore" / "liveness.py",
        "        if deadline is not None and age is not None and age > deadline:",
        "        if deadline is not None and age is not None and age > 1e9:",
    )
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "never disconnects" in result.stdout
    assert "second signal exists" in result.stdout


def test_deleting_trigger_six_from_the_seam_reddens_the_gate(tmp_path: Path) -> None:
    """PLANT: the observation is made correctly and then IGNORED.

    The observer still counts its disconnects and still returns `live=False`;
    the mirror simply stops acting on it. Every counter in the evidence would
    still look right, which is why the gate asserts the VERDICT and not the
    instrument's own bookkeeping.
    """
    home = _stage(tmp_path)
    _edit(
        home / "scripts" / "nixscore" / "seam.py",
        "        if not self._writer_live:\n"
        "            return Verdict(\n"
        "                Arbitration.FCFS,\n"
        "                first,\n"
        '                f"ranking WRITER not live [{self._writer_live_signal}]: "\n'
        '                f"{self._writer_live_reason}",\n'
        "            )\n",
        "",
    )
    result = _run_staged(home)
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "RANKED from the dead process's frozen table" in result.stdout


# ---------------------------------------------------------------------------
# The shipped gate, against the shipped tree
# ---------------------------------------------------------------------------


def test_gate_passes_against_the_real_tree() -> None:
    """The only test that proves the METHOD runs against what actually ships."""
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "SIGKILLed mid-contention" in result.evidence
    assert "libzmq DISCONNECT event(s) observed" in result.evidence
    assert "NON-VACUITY" in result.evidence
    assert "WEDGE" in result.evidence
    assert "RAISE" in result.evidence
    assert "144,699 over 0.483s" in result.evidence, (
        "the evidence must carry ARC 036's figure beside this run's, or the "
        "reader cannot tell whether anything improved"
    )


def test_declarations_are_present_and_honest() -> None:
    """§4.4's declaration set, read the way `verify.py` reads it: statically."""
    declared = read_declaration(GATE_FILE)
    assert declared.subjects == ("scripts/nixscore/liveness.py",)
    assert "zmq-ipc" in declared.resources
    assert "subprocess:python" in declared.resources
    assert "subprocess:python3" in declared.resources
    assert "file-write:/tmp" in declared.resources
    assert declared.depends_on == ("check_venv",)
    assert declared.on_fail == "continue"


def test_the_gate_is_registered_and_not_an_orphan() -> None:
    """A check absent from the plan never runs, and nothing says so."""
    import json

    registry = json.loads(
        (REPO / "checks" / "registry.json").read_text(encoding="utf-8")
    )
    named = [c for block in registry["blocks"] for c in block["checks"]]
    assert gate.NAME in named


# ---------------------------------------------------------------------------
# Per-arm can-fails
# ---------------------------------------------------------------------------


def test_every_plant_fires_and_names_a_reason() -> None:
    """The gate's own can-fail battery: each plant produces a REASON, not a flag."""
    plants = gate._plants()
    assert len(plants) >= 25
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
    assert gate.kill_defects(gate._GOOD_KILL) == []
    assert gate.corpse_defects(gate._GOOD_KILL) == []
    assert gate.blind_control_defects(gate._GOOD_KILL) == []
    assert gate.flow_defects(gate._GOOD_KILL) == []
    assert gate.vacuity_defects(gate._GOOD_VACUITY) == []
    assert gate.wedge_defects(gate._GOOD_WEDGE) == []
    assert gate.raise_defects(gate._GOOD_RAISE) == []


def test_the_corpse_ceiling_is_the_figure_d3_244_is_about() -> None:
    """One arm, driven across its own boundary, so the bound is a bound."""
    ceiling = gate.MAX_RANKED_FROM_CORPSE
    at = gate._with(
        gate._GOOD_KILL, post={"decisions": 9999, "ranked": ceiling, "fcfs": 9999}
    )
    over = gate._with(
        gate._GOOD_KILL, post={"decisions": 9999, "ranked": ceiling + 1, "fcfs": 9999}
    )
    assert gate.corpse_defects(at) == []
    findings = gate.corpse_defects(over)
    assert findings
    assert any("D3.244" in why for _site, why in findings)


def test_the_liveness_window_ceiling_is_far_below_the_freshness_threshold() -> None:
    """A liveness route that drifts to the clock has become the age route."""
    assert gate.MAX_LIVENESS_WINDOW_S < gate.STALE_AFTER_S / 4
    findings = gate.corpse_defects(
        gate._with(gate._GOOD_KILL, window_s=gate.STALE_AFTER_S)
    )
    assert any("AGE route wearing" in why for _site, why in findings)


def test_the_shape_arms_scan_the_shipped_files_and_find_them_clean() -> None:
    """The static half, run over what ships — not over a string in this file."""
    liveness = (REPO / "scripts" / "nixscore" / "liveness.py").read_text(
        encoding="utf-8"
    )
    findings, scanned = gate.read_path_defects(liveness)
    assert scanned == len(gate.LIVENESS_READ_PATH), (
        f"scanned {scanned} read verb(s); a scan over nothing cannot report a "
        "read that raises"
    )
    assert findings == []
    seam = (REPO / "scripts" / "nixscore" / "seam.py").read_text(encoding="utf-8")
    order_findings, order_scanned = gate.order_path_defects(seam)
    assert order_scanned == 2
    assert order_findings == []


def test_an_order_path_that_asks_the_observer_is_a_finding() -> None:
    """The hot path reads a boolean. Calling out to an observer is the regression."""
    findings, scanned = gate.order_path_defects(gate._ASKING_ORDER)
    assert scanned == 2
    assert any("calls verdict()" in why for _site, why in findings)
