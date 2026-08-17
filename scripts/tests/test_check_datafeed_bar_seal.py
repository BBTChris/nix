"""`check_datafeed_bar_seal` — the can-fail, as a COMMITTED control.

ARC 026 / A2. Discharges the `check_datafeed_bar_seal` quarter of CHECK-DEBT
**D2.30**.

ARC 023 measured three real-subject can-fails for this gate and ARC 025 re-bound
it after the §0c retrofit; between them they committed no artifact, so the
evidence was prose and the plants were gone. §0e: the binding needs an
instrument, not a sha in a report.

TWO PLANTS, BOTH IN THE REAL `_ingest_history` OF THE REAL ADAPTER, both landing
in a `tmp_path` copy (doctrine C.8) with the control restored byte-identical:

  1. **The `on_bar` emission deleted.** The seal store stays guarded, so a
     revision is still DETECTED — and then swallowed. The venue's changed story
     becomes unrecoverable while every structural property still holds.
  2. **The seal guard's polarity inverted.** An unguarded store means a re-poll
     returning a revised value silently overwrites a published entry.

THE TWO ARE WHY §18 EXISTS, and this pair is the cleanest instance of it in the
project: **both exit 1 and both name the SAME site** —
`scripts/broker/broker_datafeed_ibkr.py:_ingest_history:1704`. An exit-code
assertion cannot distinguish them; a site assertion cannot distinguish them
either. Only the reason can: *"emits no datafeed event — the revision is
detected and swallowed"* versus *"unguarded store into self._sealed"*. A control
that asserted only `exit == 1` here would pass with the gate detecting the wrong
defect, or with the interpreter failing to start.
"""

from __future__ import annotations

# R0801: the scratch-tree fixture is deliberately duplicated across the two
# datafeed control files rather than shared — see the note in
# test_check_datafeed_granted_mode.py.
# pylint: disable=duplicate-code
import hashlib
import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, scratch tree only
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
GATE = "checks/check_datafeed_bar_seal.py"
ADAPTER = "scripts/broker/broker_datafeed_ibkr.py"
SITE = "scripts/broker/broker_datafeed_ibkr.py:_ingest_history"


def _env() -> dict[str, str]:
    """D3.22: git honours GIT_DIR / GIT_INDEX_FILE ahead of -C, and pre-commit
    exports GIT_INDEX_FILE. Stripped so nothing this launches reaches a
    different repository than the tree under measurement."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _run(home: Path) -> tuple[int, str]:
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False, scratch tree
        [str(REPO / ".venv" / "bin" / "python"), str(home / GATE), str(home)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(home),
        env=_env(),
    )
    return proc.returncode, proc.stdout + proc.stderr


@pytest.fixture(name="scratch", scope="module")
def _scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    home = tmp_path_factory.mktemp("bar_seal") / "nix"
    shutil.copytree(
        REPO,
        home,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", ".venv-dev", "*.pyc"
        ),
    )
    (home / ".venv").symlink_to(REPO / ".venv")
    return home


@pytest.fixture(name="plant")
def _plant(scratch: Path) -> Iterator[Callable[[str, str], None]]:
    """Plant into the copied adapter; restore byte-identically, purging pycache."""
    target = scratch / ADAPTER
    before = target.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(target.read_bytes()).hexdigest()

    def _apply(old: str, new: str) -> None:
        assert old in before, f"plant anchor is not in the adapter: {old[:70]!r}"
        for cache in scratch.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        target.write_text(before.replace(old, new, 1), encoding="utf-8")

    yield _apply
    for cache in scratch.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    target.write_text(before, encoding="utf-8")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before_sha


# ===========================================================================
# NON-VACUITY, before any plant (doctrine C.3).
# ===========================================================================


def test_the_gate_found_the_series_store_it_is_about_to_judge(scratch: Path) -> None:
    """Arm 2 has no subject unless a series store was discovered.

    A scan that finds zero stores reports no violations and measures nothing —
    doctrine C.3's own worked example, and the reason this assertion precedes
    every plant.
    """
    exit_code, output = _run(scratch)
    assert exit_code == 0, output[:2000]
    assert f"series stores: ['{SITE}:" in output, (
        "no series store discovered — both plants below would be unobserved"
    )
    assert "arm4 scripts/broker/broker_seam.py:Bar: revision representable" in output


# ===========================================================================
# THE CAN-FAIL. Same site, different reasons — §18's exemplar.
# ===========================================================================


def test_a_detected_revision_that_is_never_emitted_is_caught(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """The seal is still guarded. The revision is found, and then swallowed."""
    plant(
        "            if key in self._unpublished:\n"
        "                self._sink.on_bar(bar)",
        "            if key in self._unpublished:\n                pass",
    )
    exit_code, output = _run(scratch)
    assert exit_code == 1, output[:2000]
    assert SITE in output
    assert "emits no datafeed event" in output
    assert "the revision is detected and swallowed" in output
    assert "unguarded store" not in output, (
        "the gate reported the OTHER defect — same site, same exit code, wrong "
        "finding, and only the reason string can tell (§18)"
    )


def test_an_unguarded_seal_store_is_caught(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """Polarity inverted: a re-poll silently overwrites a published entry."""
    plant(
        "            sealed = self._sealed.get(key)\n            if sealed is None:",
        "            sealed = self._sealed.get(key)\n            if sealed is not None:",
    )
    exit_code, output = _run(scratch)
    assert exit_code == 1, output[:2000]
    assert SITE in output
    assert "unguarded store into self._sealed" in output
    assert "a re-poll returning a revised value overwrites a published entry" in output
    assert "emits no datafeed event" not in output


def test_the_control_is_green_again_once_every_plant_is_gone(scratch: Path) -> None:
    """Doctrine C.2's other half, on the tree the plants above ran against."""
    exit_code, output = _run(scratch)
    assert exit_code == 0, output[:2000]
    assert "field write refused, value equality holds" in output
