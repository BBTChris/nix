"""`check_datafeed_granted_mode` — the can-fail, as a COMMITTED control.

ARC 026 / A2. Discharges the `check_datafeed_granted_mode` quarter of CHECK-DEBT
**D2.30**, and lands the compensating control D3.9 has been owed since ARC 021.

WHY THIS FILE EXISTS RATHER THAN A PARAGRAPH. ARC 023 and ARC 025 both re-bound
this gate against the real adapter, both recorded control shas in an arc report,
and **neither committed an artifact**. The plants ran from ad-hoc harnesses that
no longer exist, so the next retrofit starts its can-fail from zero. §0e: a
binding claim needs a committed, runnable artifact that reproduces the can-fail.
A control sha in a results document is evidence that a measurement happened, not
an instrument anyone can re-run.

THE THREE PLANTS ARE THE REAL D1.13 DEFECT IN ITS THREE REACHABLE SHAPES, all
in the REAL `broker_datafeed_ibkr.py` — never a fake, and never the production
copy (doctrine C.8: every plant lands in a `tmp_path` copy of the tree, and the
control is restored and re-verified byte-identical by sha256).

  1. **The sentinel write deleted from `subscribe`.** Invisible on a first
     subscription, because the per-symbol state already defaults to the
     sentinel; wrong on a RE-subscription, which inherits the previous
     subscription's grant. This is ARC 021's plant 1 — the one both gates
     passed in ARC 021 and neither could see.
  2. **The per-symbol accessor returns the REQUESTED mode.** "We asked for
     delayed" is not evidence of what was granted.
  3. **The adapter-wide accessor returns the requested mode**, which also
     destroys the divergence answer: two subscriptions granted different modes
     must report UNKNOWN, never one of them.

EVERY ASSERTION NAMES THE REASON (§18), never the exit code alone. Plants 2 and
3 both exit 1 and both site inside the same class; the strings that separate
them are `@subscribed-ungranted` versus `@divergent-grants`, and an exit-code
assertion cannot tell either from the interpreter failing to start.
"""

from __future__ import annotations

# R0801: the scratch-tree fixture is deliberately duplicated across the two
# datafeed control files rather than shared. One helper module would let a
# single edit un-bind both gates at once, which is the tax §0c exists to make
# visible — and these two gates are precisely the pair D3.10 keeps open.
# pylint: disable=duplicate-code
import hashlib
import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, scratch tree only
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
GATE = "checks/check_datafeed_granted_mode.py"
ADAPTER = "scripts/broker/broker_datafeed_ibkr.py"


def _env() -> dict[str, str]:
    """D3.22: git honours GIT_DIR / GIT_INDEX_FILE ahead of -C, and pre-commit
    exports GIT_INDEX_FILE. Stripped so nothing this launches reaches a
    different repository than the tree under measurement."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _run(home: Path) -> tuple[int, str]:
    """The gate's own standalone CLI — the surface `verify.py` uses."""
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
    home = tmp_path_factory.mktemp("granted_mode") / "nix"
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
    """Plant into the copied adapter; restore it byte-identically afterwards.

    `__pycache__` is purged either side of the plant. Without it a stale `.pyc`
    lets the restored tree keep executing planted code, and the control half of
    doctrine C.2 would be measuring the plant.
    """
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


def test_the_gate_actually_drives_the_real_subject(scratch: Path) -> None:
    """A gate whose scope does not contain the adapter would pass forever.

    The gate reports which functions of the subject's own module executed. That
    line — not a docstring — is what makes the plants below meaningful.
    """
    exit_code, output = _run(scratch)
    assert exit_code == 0, output[:2000]
    assert "NON-VACUITY: driven ['scripts/broker/broker_datafeed_ibkr.py" in output
    assert (
        "executed 8 function(s) of its own module including 'granted_mode': True"
        in (output)
    ), "the mode verb did not execute — every plant below would be unobserved"


# ===========================================================================
# THE CAN-FAIL. Three real D1.13 shapes, each asserting its own REASON.
# ===========================================================================


def test_deleting_the_subscribe_sentinel_is_caught_on_re_subscription(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """ARC 021's plant 1 — the one that passed both gates when it was first made."""
    plant(
        "        state.granted_mode = MarketDataMode.UNKNOWN\n"
        "        state.requested_mode = self._requested_mode",
        "        state.requested_mode = self._requested_mode",
    )
    exit_code, output = _run(scratch)
    assert exit_code == 1, output[:2000]
    assert "granted_mode(GATE-PROBE-A)@re-subscribed-after-1" in output
    assert "a RE-SUBSCRIPTION inherited the previous subscription's grant" in output
    assert "(reported REALTIME, expected UNKNOWN)" in output


def test_a_per_symbol_accessor_that_infers_from_the_request_is_caught(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """ARC 021's plant 2. "We asked for delayed" is not evidence of a grant."""
    plant(
        "            return state.granted_mode if state else MarketDataMode.UNKNOWN",
        "            return state.requested_mode if state else MarketDataMode.UNKNOWN",
    )
    exit_code, output = _run(scratch)
    assert exit_code == 1, output[:2000]
    assert "granted_mode(GATE-PROBE-A)@subscribed-ungranted" in output
    assert "subscribed with no grant callback received, yet reports a mode" in output
    assert "(reported DELAYED, expected UNKNOWN)" in output


def test_an_adapter_wide_accessor_that_fabricates_a_shared_mode_is_caught(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """The divergence answer, which is a different property from the per-symbol one.

    Two subscriptions granted 1 and 3 do not share a mode; naming one of them is
    a fabricated value. This plant and the previous one both exit 1 — the
    strings are what separate them (§18).
    """
    plant(
        "        modes = {st.granted_mode for st in self._symbols.values()}",
        "        modes = {st.requested_mode for st in self._symbols.values()}",
    )
    exit_code, output = _run(scratch)
    assert exit_code == 1, output[:2000]
    assert "granted_mode()@divergent-grants" in output
    assert (
        "two subscriptions granted 1 and 3 and the adapter-wide answer names one"
        in (output)
    )
    assert "a fabricated value" in output


def test_the_control_is_green_again_once_every_plant_is_gone(scratch: Path) -> None:
    """Doctrine C.2's other half, on the tree the plants above ran against.

    Ordered last so it observes every fixture teardown. Distinguishes *detects
    the defect* from *always fails*.
    """
    exit_code, output = _run(scratch)
    assert exit_code == 0, output[:2000]
    assert "granted_mode(GATE-PROBE-A)@re-subscribed-after-1 -> UNKNOWN" in output
