"""ARC 050. `checks/check_hot_path_purity.py` is BOUND — it can fail, three ways.

A gate nobody has seen fail is a constant with a verdict attached (doctrine
C.3). This module plants a forbidden operation on the hot path of a COPY of the
tree and drives the real gate at it through its own positional `home` argument,
so the shipped `scripts/nixrisk/` is never touched — which is what `CORRECTABLE=False`
means in practice as well as in the declaration.

Three plants, three distinguishable verdicts, each asserted on its REASON and
not on the exit code alone (check contract v2 rule 11 — an exit code is a shared
namespace, and "the detector fired" and "the interpreter would not start" reach
the same integer):

* **PLANT A** — a file write inside `GatePass.evaluate`: FAIL, exit 1, naming
  the `open` the hot path may not perform.
* **PLANT B** — a per-eval import of a blocking primitive inside
  `GatePass.evaluate`: FAIL, exit 1, naming `queue` (§5: the hot loop never
  blocks; the sender thread owns blocking I/O).
* **PLANT C** — an operation the allow-set census cannot classify: CANNOT_MEASURE,
  exit 2, naming the module by name. Never a PASS — §7.12's answer to "what
  would make this pass while measuring nothing" is *an expensive operation
  nobody thought to ban*, and this is the arm that refuses to guess.

And the control, which is what makes the three mean anything: with the plants
REMOVED from the same copied tree, the same gate exits 0.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

NIX = Path(__file__).resolve().parents[2]
GATE = NIX / "checks" / "check_hot_path_purity.py"
PY = NIX / ".venv" / "bin" / "python"

#: The line `GatePass.evaluate` opens with, and the anchor every plant is
#: inserted after. Matched on the SIGNATURE rather than a line number so a
#: shifted file does not silently plant into the wrong function.
_ANCHOR = '        """One pass. Returns §3\'s approve / size-down / deny, rule always named."""'

_PLANT_A = (
    '        with open("/tmp/arc050_plant_a.log", "a", encoding="utf-8") as _fh:\n'
    '            _fh.write("gated\\n")\n'
)
_PLANT_B = "        import queue as _q  # noqa: PLC0415\n        _q.Queue().put(1)\n"
#: PLANT C must be UNCLASSIFIABLE and nothing else, so the import is hoisted to
#: module scope. An `import base64` written INSIDE `evaluate` also drags in
#: `importlib` frames, which the gate classifies as a per-eval import (§5) and
#: answers with exit 1 — correctly, but that is PLANT B's finding, not this
#: one. Measured: the first spelling of this plant reddened as
#: "importlib — a PER-EVAL IMPORT" and never reached the allow-set arm at all.
_PLANT_C = '        _b64.b64encode(b"gated")\n'
_PLANT_C_IMPORT = "import base64 as _b64  # ARC 050 PLANT C\n"


def _tree(tmp_path: Path) -> Path:
    """A COPY of the tree under judgement. The shipped one is never planted in."""
    home = tmp_path / "nix"
    (home / "scripts").mkdir(parents=True)
    shutil.copytree(NIX / "scripts" / "nixrisk", home / "scripts" / "nixrisk")
    return home


def _plant(home: Path, snippet: str, module_import: str = "") -> None:
    gate = home / "scripts" / "nixrisk" / "gate.py"
    text = gate.read_text(encoding="utf-8")
    assert _ANCHOR in text, (
        "the anchor this test plants against is gone from gate.py — the plant "
        "would land somewhere unknown, so the binding proves nothing"
    )
    text = text.replace(_ANCHOR, _ANCHOR + "\n" + snippet, 1)
    if module_import:
        marker = "from __future__ import annotations\n"
        assert marker in text, "gate.py has no future-import line to plant after"
        text = text.replace(marker, marker + module_import, 1)
    gate.write_text(text, encoding="utf-8")


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
    """The control. Without it the three plants prove only that SOMETHING is red."""
    done = _drive(home)
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "pass:" in out
    # Non-vacuity, asserted here rather than trusted: the gate must say it drove
    # real approvals and a real reservation, or its green is about nothing.
    assert "'APPROVE': 4000" in out, out
    assert "ARM 2 discriminator" in out and "raw write(2)=0" in out, out
    assert "fsyncs=0 on-path" in out, out


def test_plant_a_file_write_on_the_hot_path_fails(home: Path) -> None:
    """A file write inside the gate decision: exit 1, and it names the `open`."""
    _plant(home, _PLANT_A)
    done = _drive(home)
    assert done.returncode == 1, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "fail" in out.lower(), out
    # Rule 11: the REASON, not the code. The verdict must name the syscall class
    # and the spec coordinate it violated.
    assert "FORBIDDEN" in out, out
    assert "open" in out, out
    assert "§11" in out or "§5" in out, out


def test_plant_b_per_eval_import_of_a_blocking_primitive_fails(home: Path) -> None:
    """A per-eval `import queue` inside the gate decision: exit 1, named."""
    _plant(home, _PLANT_B)
    done = _drive(home)
    assert done.returncode == 1, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "FORBIDDEN" in out, out
    assert "queue" in out, out


def test_plant_c_an_unclassifiable_op_cannot_measure(home: Path) -> None:
    """An op in NEITHER list: exit 2, naming it. Never a PASS."""
    _plant(home, _PLANT_C, _PLANT_C_IMPORT)
    done = _drive(home)
    assert done.returncode == 2, f"rc={done.returncode}\n{done.stdout}\n{done.stderr}"
    out = done.stdout
    assert "cannot_measure" in out, out
    assert "base64" in out, out
    assert "ALLOW-SET" in out, out
    assert "pass:" not in out, out


def test_plants_removed_the_same_tree_goes_green(tmp_path: Path) -> None:
    """RED-before / GREEN-after on ONE tree, so the control is not a second tree."""
    home = _tree(tmp_path)
    gate = home / "scripts" / "nixrisk" / "gate.py"
    pristine = gate.read_text(encoding="utf-8")

    _plant(home, _PLANT_A)
    red = _drive(home)
    assert red.returncode == 1, f"{red.stdout}\n{red.stderr}"

    gate.write_text(pristine, encoding="utf-8")
    # __pycache__ would serve the planted bytecode back; the gate imports from
    # source and this removes the doubt rather than reasoning about it.
    shutil.rmtree(gate.parent / "__pycache__", ignore_errors=True)
    green = _drive(home)
    assert green.returncode == 0, f"{green.stdout}\n{green.stderr}"
    assert "pass:" in green.stdout


def test_the_derivation_refuses_a_tree_whose_shape_moved(home: Path) -> None:
    """ARM 6 is a real control: break the derived shape, get CANNOT_MEASURE.

    The `StopBook` per-tick verbs are derived by the LOOP over `self._by_symbol`.
    Rename that attribute and the derivation finds nothing — which must be a
    refusal naming the lost shape, never a silent empty set that compares equal
    to a silent empty drive.
    """
    stops = home / "scripts" / "nixrisk" / "stops.py"
    stops.write_text(
        stops.read_text(encoding="utf-8").replace("_by_symbol", "_by_sym"),
        encoding="utf-8",
    )
    done = _drive(home)
    assert done.returncode == 2, f"rc={done.returncode}\n{done.stdout}"
    assert "ARM 6" in done.stdout, done.stdout
    assert "_by_symbol" in done.stdout, done.stdout


def test_the_gate_reads_the_tree_it_was_pointed_at(tmp_path: Path) -> None:
    """D3.124 provenance: a missing subject is a refusal, not a fall-through.

    `_preamble` leaves the LIVE `scripts/` on `sys.path`, so a home with no
    `nixrisk` must not resolve to this checkout and report on it.
    """
    empty = tmp_path / "empty"
    (empty / "scripts").mkdir(parents=True)
    done = _drive(empty)
    assert done.returncode == 2, f"rc={done.returncode}\n{done.stdout}"
    assert "cannot_measure" in done.stdout, done.stdout


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
