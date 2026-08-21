"""ARC 051. `checks/check_input_freshness.py` is BOUND — it can fail, four ways.

A gate nobody has seen fail is a constant with a verdict attached (doctrine
C.3). Every plant below lands on a COPY of the tree and the real gate is driven
at that copy through its own positional `home` argument, so the shipped
`scripts/` is never touched — which is what `CORRECTABLE=False` means in
practice as well as in the declaration.

Four plants, four distinguishable verdicts, each asserted on its REASON and not
on the exit code alone (check contract v2 rule 11 — an exit code is a shared
namespace, and "the detector fired" and "the interpreter would not start" reach
the same integer):

* **PLANT A** — `StalenessFlagPort.read` stops reporting its blocking feeds, so
  a feed 900 s past a 2 000 ms threshold is sized on: FAIL, exit 1, naming the
  input and the stale stamp it ignored.
* **PLANT B** — `SourceMonotonicGuard.admit` stops discarding an older-than-held
  reading, so a late poll regresses the held value: FAIL, exit 1, naming the
  regressed value (§6.4b / V27).
* **PLANT C** — `PictureMirror.picture` stops refusing an incomplete mirror, so
  a delta-only, half-built mirror reads sizeable: FAIL, exit 1 (§12.7 / V31).
* **PLANT D** — a NEW gate input whose annotation the freshness census cannot
  classify: CANNOT_MEASURE, exit 2, naming it. Never a PASS — §7.12's answer to
  "what would make this pass while measuring nothing" is *an input nobody
  thought to check*, and this is the arm that refuses to guess.

And two controls, which are what make the four mean anything:

* the unplanted copy exits 0, with its non-vacuity printed (a real APPROVE over
  the whole manifest, and a real snapshot that BECAME sizeable);
* **PLANT A AND PLANT D TOGETHER** — a FAIL on one arm and a CANNOT_MEASURE on
  another, simultaneously — must come out **exit 1**. Check contract rule 4:
  Fail > Cannot-measure, and the unclassifiable arm is judged LAST. This
  ordering has been gotten wrong in four consecutive gate first-drafts, so it
  is tested rather than reasoned about.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

NIX = Path(__file__).resolve().parents[2]
GATE = NIX / "checks" / "check_input_freshness.py"
PY = NIX / ".venv" / "bin" / "python"

# --- PLANT A: the staleness port stops reporting its blocking feeds ----------
_A_ANCHOR = "        blocking = [r for r in self.readings(symbol) if r.blocked]"
_A_PLANT = "        blocking = []  # ARC 051 PLANT A"

# --- PLANT B: the monotonic guard stops discarding an older reading ----------
_B_ANCHOR = "        if current is not None and not self._is_newer(stamp, current):"
_B_PLANT = "        if False:  # ARC 051 PLANT B"

# --- PLANT C: the mirror stops refusing a half-built table -------------------
_C_ANCHOR = "        if not mirror.complete:"
_C_PLANT = "        if False:  # ARC 051 PLANT C"

# --- PLANT D: a new gate input the census cannot classify --------------------
#: Keyword-only WITH a default, which is how an input is realistically added:
#: every existing construction site keeps working, so nothing raises and the
#: only thing that notices is a census that classifies every input. The
#: annotation is a mandatory, non-`Sequence` port type `gate.py` does not
#: declare — the one shape `_classify` deliberately refuses to guess about.
_D_ANCHOR = "    coherence_tolerance: float,"
_D_PLANT = (
    "    coherence_tolerance: float,\n"
    "    venue_feed: VenueFeedPort = None,  # ARC 051 PLANT D"
)


def _tree(tmp_path: Path) -> Path:
    """A COPY of the tree under judgement. The shipped one is never planted in."""
    home = tmp_path / "nix"
    (home / "scripts").mkdir(parents=True)
    for pkg in ("nixrisk", "nixbus", "nixalloc"):
        shutil.copytree(NIX / "scripts" / pkg, home / "scripts" / pkg)
    (home / "risks").mkdir()
    shutil.copy2(
        NIX / "risks" / "staleness.config.json",
        home / "risks" / "staleness.config.json",
    )
    return home


_FILES = {
    "freshness": ("nixrisk", "freshness.py"),
    "picture": ("nixrisk", "picture.py"),
    "gate": ("nixrisk", "gate.py"),
}


def _plant(home: Path, which: str, anchor: str, replacement: str) -> None:
    pkg, name = _FILES[which]
    target = home / "scripts" / pkg / name
    text = target.read_text(encoding="utf-8")
    assert anchor in text, (
        f"the anchor this test plants against is gone from {pkg}/{name} — the "
        "plant would land nowhere, so the binding would prove nothing"
    )
    target.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
    shutil.rmtree(target.parent / "__pycache__", ignore_errors=True)


def _drive(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PY), str(GATE), str(home)],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


@pytest.fixture(name="home")
def _home(tmp_path: Path) -> Path:
    return _tree(tmp_path)


def test_the_unplanted_copy_passes(home: Path) -> None:
    """The control. Without it the four plants prove only that SOMETHING is red."""
    done = _drive(home)
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "pass:" in out, out
    # Non-vacuity, asserted here rather than trusted. A gate whose green is
    # about a pass that denied at rule one is worth nothing.
    assert '"decision": "approve"' in out, out
    assert '"evaluated": 10' in out, out
    assert '"snapshot_landed": true' in out, out
    assert '"discarded_older": 3' in out, out
    # And the census must have found the real shape, not an empty set.
    assert '"ports": 5' in out, out
    assert "published_ts" in out, out


def test_plant_a_a_stale_input_sized_on_fails(home: Path) -> None:
    """A stale feed the gate acts on: exit 1, naming the input and the stamp."""
    _plant(home, "freshness", _A_ANCHOR, _A_PLANT)
    done = _drive(home)
    assert done.returncode == 1, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "fail" in out.lower(), out
    # Rule 11: the REASON, not the code.
    assert "SIZED ON A STALE INPUT" in out or "STALE INPUT NOT REFUSED" in out, out
    assert "price" in out, out
    assert "§6.4" in out or "§3" in out, out


def test_plant_b_a_regressing_held_value_fails(home: Path) -> None:
    """The monotonic discard removed: exit 1, naming the regressed value."""
    _plant(home, "freshness", _B_ANCHOR, _B_PLANT)
    done = _drive(home)
    assert done.returncode == 1, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "REGRESSED" in out or "OUT-OF-ORDER READING ADMITTED" in out, out
    assert "§6.4b" in out, out
    assert "SourceMonotonicGuard" in out, out


def test_plant_c_a_half_built_mirror_sized_on_fails(home: Path) -> None:
    """The incomplete-mirror refusal removed: exit 1, §12.7 named."""
    _plant(home, "picture", _C_ANCHOR, _C_PLANT)
    done = _drive(home)
    assert done.returncode == 1, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "MIRROR" in out, out
    assert "§12.7" in out, out
    assert "PictureMirror.tradable" in out, out


def test_plant_d_an_unclassifiable_gate_input_cannot_measure(home: Path) -> None:
    """A gate input in NO bucket: exit 2, naming it. Never a PASS."""
    _plant(home, "gate", _D_ANCHOR, _D_PLANT)
    done = _drive(home)
    assert done.returncode == 2, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "cannot_measure" in out.lower(), out
    assert "UNCLASSIFIABLE GATE INPUT" in out, out
    assert "venue_feed" in out, out
    assert "VenueFeedPort" in out, out
    assert "pass:" not in out, out


def test_rule_4_a_fail_and_a_cannot_measure_together_come_out_fail(
    home: Path,
) -> None:
    """PLANT A **and** PLANT D at once: FAIL WINS. Check contract rule 4.

    A positively-observed violation outranks a limit of the census, always. The
    inverse — CANNOT_MEASURE reported while the gate is holding a real finding
    — withholds certification over a defect it had already seen, and is the
    ordering four consecutive gate first-drafts got wrong (ARC 045, 049, 050 x2).
    """
    _plant(home, "freshness", _A_ANCHOR, _A_PLANT)
    _plant(home, "gate", _D_ANCHOR, _D_PLANT)
    done = _drive(home)
    assert done.returncode == 1, (
        "FAIL must beat CANNOT_MEASURE (check contract rule 4): "
        f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    )
    out = done.stdout
    assert "fail" in out.lower(), out
    assert "STALE" in out, out
    # And the unclassifiable input must NOT have been reported as the verdict.
    assert "cannot_measure" not in out.lower(), out


def test_plants_removed_the_same_tree_goes_green(tmp_path: Path) -> None:
    """RED-before / GREEN-after on ONE tree, so the control is not a second tree."""
    home = _tree(tmp_path)
    target = home / "scripts" / "nixrisk" / "freshness.py"
    pristine = target.read_text(encoding="utf-8")

    _plant(home, "freshness", _A_ANCHOR, _A_PLANT)
    red = _drive(home)
    assert red.returncode == 1, f"{red.stdout}\n{red.stderr}"

    target.write_text(pristine, encoding="utf-8")
    # __pycache__ would serve the planted bytecode back; the gate imports from
    # source and this removes the doubt rather than reasoning about it.
    shutil.rmtree(target.parent / "__pycache__", ignore_errors=True)
    green = _drive(home)
    assert green.returncode == 0, f"{green.stdout}\n{green.stderr}"
    assert "pass:" in green.stdout


def test_a_gate_that_denies_everything_is_not_a_pass(home: Path) -> None:
    """Denial-by-construction is caught: §7.12 item 6, as a control.

    A detector that blocked every reading would satisfy all three deny arms and
    prove nothing. Planting it must be RED, not green.
    """
    _plant(
        home,
        "freshness",
        _A_ANCHOR,
        "        blocking = list(self.readings(symbol))  # ARC 051 deny-everything",
    )
    done = _drive(home)
    assert done.returncode == 1, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    assert "NON-VACUITY FAILED" in done.stdout, done.stdout


def test_the_gate_reads_the_tree_it_was_pointed_at(tmp_path: Path) -> None:
    """D3.124 provenance: a missing subject is a refusal, not a fall-through.

    `_preamble` leaves the LIVE `scripts/` on `sys.path`, so a home with no
    `nixrisk` must not resolve to this checkout and report on it.
    """
    empty = tmp_path / "empty"
    (empty / "scripts").mkdir(parents=True)
    done = _drive(empty)
    assert done.returncode == 2, f"rc={done.returncode}\n{done.stdout}"
    assert "cannot_measure" in done.stdout.lower(), done.stdout
    assert "§17" in done.stdout, done.stdout


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
