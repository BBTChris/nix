"""`check_two_phase_entry` — the CAN-FAIL binding for I4.

ARC 049. A gate that has never been seen to go red is an assertion, not an
instrument (doctrine C.2). This module puts the gate in front of trees that
carry the exact defects §4's two-phase entry rule exists to prevent, and
requires the RIGHT verdict with the RIGHT reason — never the exit code alone
(check contract rule 11: an exit code is a shared namespace, and "the detector
fired" and "the interpreter refused to start" reach the same integer).

**Doctrine C.8 — a plant never touches a production artifact.** Every plant here
is written into a private `shutil.copytree` of `scripts/`, and the gate is
pointed at THAT tree through `Context.nix_home`. Nothing under `/home/bbt/nix/
scripts` is edited, and the clean-copy control below proves the copy itself is
not the thing that reddens.

THE FOUR PLANTS

* **A(driven) — THE PHANTOM.** The ack path publishes §3's row optimistically,
  so an acked-but-UNFILLED order reads OPEN. Committed margin, sizing math and
  a protective stop for size that is not at the venue.
* **A(static) — THE PHANTOM THE GREP CONTROL MISSES.** The same defect spelled
  through a module-level alias (`state=_ENTRY_STATE`). This is the ARC 049 S1
  reproduction: `test_arc038_c_open_is_confirmed_fill.py::
  test_OPEN_is_WRITTEN_at_EXACTLY_TWO_SITES_and_PENDING_at_NONE` stays GREEN on
  this tree, and this gate does not.
* **B — THE UNPROTECTED POSITION.** A confirmed fill no longer reaches OPEN.
  Real size at the venue that §3's table reads as flat.
* **B(gate) — THE ERODED PRECONDITION.** The projection's `qty_filled == 0`
  refusal is removed, so a cancel for a never-filled trade can open a position
  in §9's projection. The behavioural arms cannot see this: no drive here folds
  that log, which is exactly why the precondition is re-derived statically.
* **C — THE UNCLASSIFIABLE SETTER.** A `state` slot filled from an expression
  the derivation cannot resolve. CANNOT_MEASURE naming it, never PASS.
"""
# Test names SHOUT the property under test on purpose — a red verdict in CI
# should read as a sentence about the defect, not as a symbol to look up.
# Same convention, same reason, as test_status_contract.py and the ARC 038
# invariant suites; late imports are the sys.path bootstrap this file needs.
# pylint: disable=invalid-name,import-outside-toplevel

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "checks"))
sys.path.insert(0, str(REPO / "scripts"))

import check_two_phase_entry as gate  # pylint: disable=wrong-import-position
from nixverify.contract import Mode, Status  # pylint: disable=wrong-import-position


class _Ctx:  # pylint: disable=too-few-public-methods
    """The one field the gate reads off a `Context`."""

    def __init__(self, home: Path) -> None:
        self.nix_home = home


@pytest.fixture(name="tree")
def _tree(tmp_path):
    """A private copy of `scripts/`, minus the tests and the caches.

    The tests are excluded because the gate excludes them from its own scan;
    the caches because a stale `__pycache__` would let the drive import a
    module the plant never touched.
    """
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    for entry in sorted((REPO / "scripts").iterdir()):
        if entry.name in ("tests", "__pycache__"):
            continue
        target = home / "scripts" / entry.name
        if entry.is_dir():
            shutil.copytree(
                entry, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        else:
            shutil.copy2(entry, target)
    return home


def _run(home: Path):
    return gate.run(Mode.VERIFY, _Ctx(home))


def _append(home: Path, rel: str, text: str) -> None:
    path = home / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _swap(home: Path, rel: str, old: str, new: str) -> None:
    path = home / rel
    body = path.read_text(encoding="utf-8")
    assert old in body, f"plant anchor not found in {rel}: {old!r}"
    path.write_text(body.replace(old, new, 1), encoding="utf-8")


# ==========================================================================
# NON-VACUITY: the copy is not the thing that reddens.
# ==========================================================================


def test_the_CLEAN_COPY_passes_so_every_red_below_is_the_PLANT(tree) -> None:
    """Without this the plants prove only that a copied tree upsets the gate."""
    result = _run(tree)
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    # And it measured something: a PASS over an empty census is the §7.12
    # failure this gate's floors exist to refuse, so read the count back.
    assert "5 originator(s)" in result.evidence, result.evidence
    assert "positions.py::PositionOriginWriter._row" in result.evidence, result.evidence


def test_the_gate_REFUSES_a_tree_it_cannot_read_rather_than_passing(tmp_path) -> None:
    """§17 / rule 10: no subject is CANNOT_MEASURE, never a green."""
    empty = tmp_path / "empty"
    (empty / "scripts").mkdir(parents=True)
    result = _run(empty)
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "seam.py" in result.detail or "module(s) parsed" in result.detail, (
        result.detail
    )


# ==========================================================================
# PLANT A (driven) — THE PHANTOM POSITION
# ==========================================================================

_OPTIMISTIC_OPEN = """
        # ---- ARC 049 PLANT A (driven): the OPTIMISTIC OPEN ----------------
        if sum_reservations is not None and positions is None:
            held = tuple(
                PositionRow(
                    trade_id=f"phantom-{index}",
                    symbol=symbol,
                    strategy_id="strat-1",
                    size=1,
                    margin=margin,
                    state=PositionState.OPEN,
                    stop_distance=20,
                )
                for index, (symbol, margin) in enumerate(
                    sorted(self._current.margin_per_contract.items())
                )
            )
            if held:
                positions = held
"""


def test_PLANT_A_driven_an_ACKED_UNFILLED_order_reading_OPEN_is_a_FAIL(tree) -> None:
    """§4: never on placement ack, never optimistically."""
    _swap(
        tree,
        "scripts/nixrisk/picture.py",
        "    ) -> FinancialPicture:\n",
        "    ) -> FinancialPicture:\n" + _OPTIMISTIC_OPEN,
    )
    result = _run(tree)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"{result.status}: {result.detail or result.evidence}"
    )
    # RULE 11 — the REASON, not the status. The verdict must name the phantom.
    assert "PHANTOM POSITION" in result.detail, result.detail
    assert "phantom-0" in result.detail, result.detail
    assert "picture.positions" in result.site, result.site


def test_PLANT_A_static_an_ALIASED_OPEN_SETTER_is_a_FAIL(tree) -> None:
    """The ARC 049 S1 reproduction: the defect the `grep` control cannot see."""
    _append(
        tree,
        "scripts/nixrisk/positions.py",
        '''

# ---- ARC 049 PLANT A (static): the phantom, spelled through an alias -------
_ENTRY_STATE = PositionState.OPEN


def publish_on_ack(order, origins) -> PositionRow:
    """PHANTOM: §3's row, OPEN, on the placement ACK. No fill anywhere."""
    origin = origins.origin_for_order(order.client_order_id)
    return PositionRow(
        trade_id=origin.trade_id,
        symbol=order.symbol,
        strategy_id=order.strategy_id,
        size=order.qty,
        margin=order.qty * order.margin_per_contract,
        state=_ENTRY_STATE,
        stop_distance=order.stop_ticks,
    )
''',
    )
    result = _run(tree)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"{result.status}: {result.detail or result.evidence}"
    )
    assert "UNDECLARED OPEN-SETTER" in result.detail, result.detail
    assert "publish_on_ack" in result.detail, result.detail
    assert "PHANTOM POSITION" in result.detail, result.detail


def test_PLANT_A_static_is_INVISIBLE_to_the_ARC_038_grep_control(tree) -> None:
    """The whole reason this gate exists, measured rather than asserted.

    The standing control's derivation is `grep -rn "state=PositionState.OPEN"`
    over `scripts/`, reduced to the set of MODULES. The alias plant above adds
    no such text and lands in a module already in the set, so the control's
    assertion still holds — while the by-shape census gains a site.
    """
    import subprocess  # nosec B404 - fixed argv, no shell  # pylint: disable=import-outside-toplevel

    def control_modules() -> set[str]:
        out = subprocess.run(  # nosec B603,B607 - fixed argv, no shell
            [
                "grep",
                "-rn",
                "state=PositionState.OPEN",
                "--include=*.py",
                str(tree / "scripts"),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        return {
            line.split(":")[0].replace(str(tree) + "/", "")
            for line in out.stdout.strip().splitlines()
            if line and "/tests/" not in line
        }

    before_control = control_modules()
    before_sites, _, _, why = gate.census(tree)
    assert not why, why
    _append(
        tree,
        "scripts/nixrisk/positions.py",
        "\n\n_ENTRY_STATE = PositionState.OPEN\n\n"
        "def publish_on_ack(order, origins):\n"
        "    return PositionRow(\n"
        '        trade_id="t", symbol=order.symbol, strategy_id="s", size=1,\n'
        "        margin=1.0, state=_ENTRY_STATE, stop_distance=1,\n"
        "    )\n",
    )
    after_control = control_modules()
    after_sites, _, _, why = gate.census(tree)
    assert not why, why

    assert before_control == after_control, (
        "the grep control DID move on the alias plant; the finding this gate "
        "was built for no longer reproduces and its docstring must be corrected"
    )
    before_open = {
        (s.module, s.function) for s in before_sites if s.kind == gate.ORIGINATOR
    }
    after_open = {
        (s.module, s.function) for s in after_sites if s.kind == gate.ORIGINATOR
    }
    assert after_open - before_open == {
        ("scripts/nixrisk/positions.py", "publish_on_ack")
    }, sorted(after_open - before_open)


# ==========================================================================
# PLANT B — THE UNPROTECTED REAL POSITION
# ==========================================================================


def test_PLANT_B_a_CONFIRMED_FILL_that_never_reaches_OPEN_is_a_FAIL(tree) -> None:
    """The converse direction: OPEN must track EVERY confirmed fill."""
    _swap(
        tree,
        "scripts/nixrisk/positions.py",
        "            state=PositionState.OPEN,",
        "            state=PositionState.PENDING,",
    )
    result = _run(tree)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"{result.status}: {result.detail or result.evidence}"
    )
    assert "UNPROTECTED REAL POSITION" in result.detail, result.detail
    # It must name the position, and the disagreement that proves it is real.
    assert "c-fill-1:pending:2" in result.detail, result.detail
    # And the census must notice the accepted originator has gone.
    assert "ACCEPTED OPEN-SETTER HAS VANISHED" in result.detail, result.detail


def test_PLANT_B_gate_an_ERODED_ZERO_FILL_REFUSAL_is_a_FAIL(tree) -> None:
    """Invisible to every drive here — which is why it is derived statically."""
    _swap(
        tree,
        "scripts/nixrisk/projection.py",
        """    if build.qty_filled == 0:
        return [
            (
                f"event {event.event_id} ({EVENT_CANCEL}) resolves trade "
                f"{event.trade_id}, which has no fill — nothing to resolve"
            )
        ]
""",
        "",
    )
    result = _run(tree)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"{result.status}: {result.detail or result.evidence}"
    )
    assert "_on_cancel" in result.detail, result.detail
    assert "qty_filled == 0" in result.detail, result.detail
    assert "phantom" in result.detail.lower(), result.detail


# ==========================================================================
# PLANT C — THE UNCLASSIFIABLE OPEN-SETTER  (exit 2, never a PASS)
# ==========================================================================


def test_PLANT_C_an_UNCLASSIFIABLE_state_setter_is_CANNOT_MEASURE(tree) -> None:
    """Rule 10 / §17: what the derivation cannot classify, it may not certify."""
    _append(
        tree,
        "scripts/nixrisk/positions.py",
        '''

# ---- ARC 049 PLANT C: a state this derivation cannot resolve ---------------
def _pick_state():
    """Whatever this returns, it is not readable from the call site."""
    return PositionState.OPEN


def publish_somehow(order, origins) -> PositionRow:
    origin = origins.origin_for_order(order.client_order_id)
    return PositionRow(
        trade_id=origin.trade_id,
        symbol=order.symbol,
        strategy_id=order.strategy_id,
        size=order.qty,
        margin=1.0,
        state=_pick_state(),
        stop_distance=order.stop_ticks,
    )
''',
    )
    result = _run(tree)
    assert result.status is Status.CANNOT_MEASURE, (
        f"{result.status}: {result.detail or result.evidence}"
    )
    assert "cannot classify" in result.detail, result.detail
    assert "publish_somehow" in result.detail, result.detail
    assert "_pick_state()" in result.detail, result.detail


# ==========================================================================
# PLANTS REMOVED -> the gate goes back to green on the same rig.
# ==========================================================================


def test_REMOVING_the_plant_restores_the_PASS(tree) -> None:
    """RED-then-GREEN on one tree: the verdict tracks the defect, not the run."""
    target = tree / "scripts" / "nixrisk" / "positions.py"
    clean = target.read_text(encoding="utf-8")
    _swap(
        tree,
        "scripts/nixrisk/positions.py",
        "            state=PositionState.OPEN,",
        "            state=PositionState.PENDING,",
    )
    assert _run(tree).status is Status.FAIL_NEEDS_OPERATOR
    target.write_text(clean, encoding="utf-8")
    restored = _run(tree)
    assert restored.status is Status.PASS, f"{restored.status}: {restored.detail}"


# ==========================================================================
# The exit-code contract, on the CLI surface (contract rule 1 / §4.2).
# ==========================================================================


def test_the_gate_is_INDEPENDENTLY_RUNNABLE_and_measure_only_by_default() -> None:
    """A flagless check never mutates (check contract rule 1)."""
    import subprocess  # nosec B404 - fixed argv, no shell  # pylint: disable=import-outside-toplevel

    before = (REPO / "scripts" / "nixrisk" / "positions.py").read_bytes()
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        [
            str(REPO / ".venv" / "bin" / "python"),
            str(REPO / "checks" / gate.NAME) + ".py",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        cwd=str(REPO),
    )
    assert proc.returncode in (0, 1, 2), proc.returncode
    assert gate.NAME not in proc.stderr or proc.returncode != 0, proc.stderr
    assert (REPO / "scripts" / "nixrisk" / "positions.py").read_bytes() == before, (
        "the gate mutated its own subject on a flagless run"
    )
