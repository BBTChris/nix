"""ARC 055 — the can-fail suite for `checks/check_stop_maintenance.py` (rule 4).

Non-vacuity FIRST (the real tree passes and the evidence names all four arms),
then PLANTS that must turn the gate's own judgement RED and NAME the site, then
the plants removed and the same inputs judged clean again.

**No plant touches a production artifact** (doctrine C.8), and no plant copies
the tree: this gate SPAWNS a `limiterd` out of `nix_home`, so a scratch `nix_home`
would be a copy of `~/nix` under `tmp_path` — which is the D3-class incident the
project memory records (620 GB, ARC 050). So the plants are applied where this
gate's decisions are actually made: to the DATA the daemon reported. `_judge_one_fire`
and `_arm_monotonic`'s complaint path are pure functions over measured numbers,
and planting a double-flatten or a missing mark into that data exercises the exact
branch a source defect would reach.

The SOURCE-LEVEL plants (A: the breach never tested; B: the ratchet reading the
current price; B': the trail widened away from price; C: the fire-once mark
ignored) were driven against the shipped gate at ARC 055 / S4 and each returned
exit 1 naming its site. They are recorded in `RESULTS.md` rather than run here,
because each costs a `limiterd` spawn and a live perturbation of a risk-path file.
"""
# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=duplicate-code
# protected-access: this suite's whole subject is the gate's JUDGEMENT, and the
# judgement lives in `_judge_one_fire` and `_arm_monotonic`. Driving it through
# `run()` instead would mean spawning a `limiterd` per plant to reach one pure
# function over numbers — and would still not let a plant set those numbers.
# pylint: disable=protected-access

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_stop_maintenance as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

LEVEL = gate.EXPECT_LEVEL
CROSSING = LEVEL - gate.TICK_SIZE


def _clean_block() -> dict:
    """Exactly what a healthy daemon reports for ONE breach of ONE stop."""
    return {
        "fires": 1,
        "sends": 1,
        "flattened": [gate.SYMBOL],
        "in_flight": [gate.CID],
        "refusals": [],
        "sender_send_errors": [],
    }


def _clean_action() -> dict:
    return {
        "trigger": "synthetic_stop",
        "executed": [True],
        "dropped": [],
        "level": LEVEL,
        "price": CROSSING,
    }


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the judgement is clean on clean numbers
# --------------------------------------------------------------------------


def test_the_ONE_FIRE_judgement_is_SILENT_on_a_healthy_daemons_numbers() -> None:
    assert not gate._judge_one_fire(_clean_block(), _clean_action(), LEVEL, CROSSING)


def test_the_MONOTONIC_ARM_passes_on_the_REAL_shipped_poll() -> None:
    evidence, complaint = gate._arm_monotonic(REPO)
    assert complaint == "", complaint
    joined = "; ".join(evidence)
    assert "tightened" in joined and "NO ground given back" in joined, joined
    assert "descending walk" in joined, joined


def test_the_GATE_DECLARES_the_poll_and_the_daemon_as_SUBJECTS() -> None:
    """Coverage that is real: a plant in either file must be able to redden this."""
    assert "scripts/nixrisk/stopwatch.py" in gate.SUBJECTS
    assert "scripts/limiterd.py" in gate.SUBJECTS
    assert gate.CORRECTABLE is False and gate.NON_CORRECTABLE_REASON
    assert "subprocess:python" in gate.RESOURCES, gate.RESOURCES


def test_the_EXPECTED_LEVEL_is_COMPUTED_here_and_not_read_off_the_daemon() -> None:
    """§7.12 #9 — a figure read back and compared against itself proves nothing."""
    assert gate.EXPECT_LEVEL == gate.FILL_PRICE - gate.STOP_TICKS * gate.TICK_SIZE
    assert gate.EXPECT_LEVEL == 4998.0


# --------------------------------------------------------------------------
# THE PLANTS — each must FAIL and NAME its condition
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutation", "must_say"),
    [
        ({"sends": 2, "flattened": ["ES", "ES"]}, "fires=1"),
        ({"sends": 0, "flattened": []}, "sends=0"),
        ({"fires": 1, "sends": 1, "flattened": []}, "flattened=[]"),
        ({"in_flight": []}, "fire-once mark"),
        ({"refusals": ["no join"]}, "sender REFUSED"),
        ({"sender_send_errors": ["BrokenPipe"]}, "raised on the send"),
    ],
)
def test_a_PLANTED_fire_defect_is_NAMED_by_the_judgement(mutation, must_say) -> None:
    block = _clean_block() | mutation
    findings = gate._judge_one_fire(block, _clean_action(), LEVEL, CROSSING)
    assert findings, f"{mutation} produced no finding"
    joined = "; ".join(why for _, why in findings)
    assert must_say in joined, joined
    assert all(site for site, _ in findings), findings


@pytest.mark.parametrize(
    ("mutation", "must_say"),
    [
        ({"trigger": "uncertainty"}, "synthetic_stop"),
        ({"executed": [False], "dropped": ["already closed"]}, "did not execute"),
        ({"level": LEVEL + 1.0}, "not the one that breached"),
    ],
)
def test_a_PLANTED_action_defect_is_NAMED_by_the_judgement(mutation, must_say) -> None:
    findings = gate._judge_one_fire(
        _clean_block(), _clean_action() | mutation, LEVEL, CROSSING
    )
    assert findings, f"{mutation} produced no finding"
    assert must_say in "; ".join(why for _, why in findings)


def test_the_DOUBLE_FLATTEN_plant_names_EVERY_disagreeing_counter() -> None:
    """The three counters are independent on purpose; the message must show all."""
    block = _clean_block() | {"sends": 7, "flattened": ["ES"] * 7}
    findings = gate._judge_one_fire(block, _clean_action(), LEVEL, CROSSING)
    joined = "; ".join(why for _, why in findings)
    assert "fires=1" in joined and "sends=7" in joined and "flattened=" in joined


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same inputs judged clean again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_judgement_SILENT() -> None:
    block = _clean_block()
    block["sends"] = 2
    assert gate._judge_one_fire(block, _clean_action(), LEVEL, CROSSING)
    block["sends"] = 1
    assert not gate._judge_one_fire(block, _clean_action(), LEVEL, CROSSING)


# --------------------------------------------------------------------------
# THE WHOLE GATE, END TO END — spawns a real `limiterd`. MEASURED at 2.54s, so
# it is NOT marked slow and NOT opt-in: an end-to-end arm nobody runs by default
# is an arm that stops being true without saying so.
# --------------------------------------------------------------------------


def test_the_WHOLE_GATE_passes_on_the_real_tree_and_names_FOUR_arms() -> None:
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result
    for arm in ("ARM 1 driven", "ARM 2 fire-once", "ARM 3 monotonic", "ARM 4"):
        assert arm in (result.evidence or ""), result.evidence
    assert "NOT PROVEN" not in (result.evidence or ""), result.evidence
