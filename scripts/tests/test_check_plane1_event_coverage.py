"""`check_plane1_event_coverage` — the DETECTION can-fail, committed not banked.

ARC 035 / Stage 1 / sub-agent A (A4). The brief:

> *a "logging works" test on one event type generalized is manufactured
> coverage. EACH §12.10 event type is its own drive.*

This suite proves the gate can tell the three states apart and reddens when the
census regresses. The expensive arms (which build a real scratch database and
drive every routable type end to end) carry an unmutated CONTROL; the ratchet
arms are driven directly over synthetic census states, which is both faster and
more precise than manufacturing a real regression for each.

Every plant asserts its anchor before mutating, and the tree copy never includes
`.venv` or `.venv-dev`.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring,protected-access
# `_DRIVE_KIND` is private to the gate and is READ here on purpose: the
# assertion is that no §12.10 type is silently absent from the drive loop,
# and a public accessor would be API invented for a test to use.
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
CHECKS = REPO / "checks"
for _path in (str(SCRIPTS), str(CHECKS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position
import check_plane1_event_coverage as gate  # pylint: disable=import-error
import check_plane1_schema  # pylint: disable=import-error
from nixrisk.plane1_sink import (  # pylint: disable=import-error
    UNROUTABLE_PLANE1_EVENTS,
)
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)

_HAS_PG = shutil.which("psql") is not None and shutil.which("createdb") is not None
pg_only = pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")


@pytest.fixture(name="tree")
def _tree(tmp_path) -> Path:
    """A copy of `scripts/` alone — the producer census's whole subject.

    NEVER `.venv`/`.venv-dev`: `shutil.ignore_patterns` matches EXACTLY and this
    arc's Phase 0 already lost a shared 31 G tmpfs to that mistake.
    """
    root = tmp_path / "tree"
    root.mkdir()
    shutil.copytree(
        REPO / "scripts",
        root / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", ".venv", ".venv-dev"),
    )
    return root


# ------------------------------------------------------------- THE INVENTORY


def test_the_inventory_size_agrees_with_the_SCHEMA_GATES_independent_pin() -> None:
    """Two gates pinned §12.10's size independently; a disagreement is a finding."""
    assert gate.EXPECTED_EVENT_TYPES == len(
        check_plane1_schema.SPEC_12_10_PLANE1_EVENTS
    )


def test_every_routable_type_has_exactly_one_DRIVE_KIND() -> None:
    """No §12.10 type may be silently absent from the drive loop."""
    routable = set(check_plane1_schema.SPEC_12_10_PLANE1_EVENTS) - set(
        UNROUTABLE_PLANE1_EVENTS
    )
    assert set(gate._DRIVE_KIND) == routable, sorted(
        routable.symmetric_difference(gate._DRIVE_KIND)
    )


# ------------------------------------------------------- THE CENSUS, for real


@pg_only
def test_control_the_shipped_tree_classifies_with_no_defect() -> None:
    """The unmutated census: every routable type drives and lands."""
    state, defects, _notes = gate.classify(REPO)
    assert not defects, defects
    assert len(state) == gate.EXPECTED_EVENT_TYPES
    assert set(UNROUTABLE_PLANE1_EVENTS) == {
        t for t, s in state.items() if s == "UNROUTABLE"
    }
    driven = sum(1 for s in state.values() if s in {"DRIVEN", "TRANSPORT-ONLY"})
    assert driven >= gate.MIN_TYPES_DRIVEN


@pg_only
def test_control_the_shipped_gate_PASSES_and_names_every_state() -> None:
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"Plane-1 subject not reachable here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    # The brief: the distinction must be visible in the GATE'S OWN VERDICT.
    assert "TRANSPORT-ONLY" in result.evidence
    assert "NOT YET PRODUCED" in result.evidence
    assert "UNROUTABLE" in result.evidence
    for event_type in ("filled", "go_timeout", "signal", "halt_set"):
        assert event_type in result.evidence


@pg_only
def test_a_type_that_LOSES_its_producer_reddens_the_gate(tree) -> None:
    """The regression the ratchet exists for, driven end to end.

    `cold_start_outcome` is DRIVEN today because `nixrisk/coldstart.py`
    references `EventKind.COLD_START`. Break every reference and the type falls
    to TRANSPORT-ONLY — the path still works, nothing emits it — which is a
    regression in what the money record covers.
    """
    target = tree / "scripts" / "nixrisk" / "coldstart.py"
    text = target.read_text()
    anchor = "EventKind.COLD_START"
    assert text.count(anchor) >= 1, "plant anchor is absent"
    mutated = text.replace(anchor, "_RetiredKind.COLD_START")
    assert anchor not in mutated, "plant did not apply"
    target.write_text(mutated)
    state, defects, _notes = gate.classify(tree)
    assert state["cold_start_outcome"] == "TRANSPORT-ONLY", state
    ratchet, _ = gate.ratchet_defects(state)
    assert any("LOST their producer" in d for d in ratchet), ratchet
    assert any("cold_start_outcome" in d for d in ratchet), ratchet
    assert not defects, defects  # the TRANSPORT half is untouched


@pg_only
def test_the_producer_census_ignores_the_seam_that_DEFINES_the_enum() -> None:
    """`seam.py` names every member; counting it gives everyone a producer free."""
    census = gate.producer_census(REPO)
    assert "seam.py" not in set().union(*census.values())
    assert "coldstart.py" in census["COLD_START"]
    assert "SIGNAL" not in census, "signal has no emitter in scripts/nixrisk/"


# ------------------------------------------------------------- THE RATCHET


def test_a_NEWLY_UNROUTABLE_type_reddens_the_ratchet() -> None:
    """A type the Limiter can no longer enqueue at all."""
    state = {t: "DRIVEN" for t in check_plane1_schema.SPEC_12_10_PLANE1_EVENTS}
    for t in UNROUTABLE_PLANE1_EVENTS:
        state[t] = "UNROUTABLE"
    state["halt_set"] = "UNROUTABLE"
    defects, _notes = gate.ratchet_defects(state)
    assert any("became UNROUTABLE" in d and "halt_set" in d for d in defects), defects


def test_a_type_GAINING_a_producer_is_a_NOTE_not_a_FAIL() -> None:
    """The asymmetry, asserted so it is a decision rather than a bug.

    Four sub-agents land emitters in parallel in this arc; a gate that reddened
    on progress is a gate that gets switched off. The cost is stated in the
    gate's docstring and carried by `check_plane1_sole_writer`.
    """
    state = {t: "DRIVEN" for t in check_plane1_schema.SPEC_12_10_PLANE1_EVENTS}
    for t in UNROUTABLE_PLANE1_EVENTS:
        state[t] = "UNROUTABLE"
    defects, notes = gate.ratchet_defects(state)
    assert not defects, defects
    assert any("GAINED a producer" in n for n in notes), notes


def test_the_UNMUTATED_state_produces_neither_defect_nor_regression_note() -> None:
    """The ratchet's own CONTROL: today's real shape must be quiet."""
    state = {t: "DRIVEN" for t in check_plane1_schema.SPEC_12_10_PLANE1_EVENTS}
    for t in UNROUTABLE_PLANE1_EVENTS:
        state[t] = "UNROUTABLE"
    for t in gate.EXPECTED_UNPRODUCED:
        state[t] = "TRANSPORT-ONLY"
    defects, notes = gate.ratchet_defects(state)
    assert not defects, defects
    assert not notes, notes


# ---------------------------------------------------------------- §17 / vacuity


def test_an_unreachable_cluster_is_CANNOT_MEASURE_not_a_PASS(monkeypatch) -> None:
    """A census over nothing is the purest vacuous green (§17)."""

    def _explode(*_args, **_kwargs):
        raise gate.Unmeasurable("planted: the cluster is unreachable")

    monkeypatch.setattr(gate, "_scratch_database", _explode)
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "unreachable" in result.detail
