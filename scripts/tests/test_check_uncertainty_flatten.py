"""ARC 057 — the can-fail suite for `checks/check_uncertainty_flatten.py` (rule 4).

Non-vacuity FIRST (the real tree's own condition set derives clean and the
completeness judgement is silent on it), then PLANTS that must turn the gate's
own judgement RED or CANNOT_MEASURE and NAME the site, then the plants removed
and the same inputs judged clean again.

**No plant touches a production artifact** (doctrine C.8), and no plant copies
the tree. This gate SPAWNS a `limiterd` out of `nix_home`, so a scratch
`nix_home` built by copying `~/nix` under `tmp_path` is the D3-class incident the
project memory records (620 GB, ARC 050). The two things planted here are
therefore the two the gate DERIVES rather than drives:

* `_declared_conditions` reads ONE file — `scripts/limiterd.py` — so a scratch
  tree holding one hand-written module is a complete, honest subject for it and
  costs two directories.
* `_completeness` is a pure function over `(nix_home, drove, published)`, so
  planting *a producer that detected and did not fire* into `drove` exercises the
  exact branch a source defect reaches.

The FOUR SOURCE-LEVEL PLANTS the brief names — A (a producer detects but does not
fire), B (D3.469 flattens before its deadline), C (a condition re-fires), D (a
fifth condition with no producer) — were driven against the SHIPPED gate at
ARC 057 / S4b as real edits to `scripts/limiterd.py`, each returning a red
verdict naming its site, with the file restored byte-identically afterwards
(`sha256` compared before and after). They are recorded in `RESULTS.md` rather
than run here, because each costs six `limiterd` spawns and a live perturbation
of a risk-path file.
"""
# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=duplicate-code
# protected-access: this suite's whole subject is the gate's JUDGEMENT, and the
# judgement lives in `_completeness` and `_declared_conditions`. Driving it
# through `run()` instead would mean six daemon spawns per plant to reach one
# pure function — and would still not let a plant set `drove`.
# pylint: disable=protected-access

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_uncertainty_flatten as gate  # pylint: disable=wrong-import-position

#: The set ARC 057 wired, and the debt row each member discharges. Written HERE
#: rather than imported from the gate, deliberately: the gate DERIVES its set
#: from the subject and holds no copy, so a copy has to exist somewhere for the
#: derivation to be checkable at all — and a test is where a fixed expectation
#: belongs. If a later arc adds a fifth condition, this line is one of the two
#: places that must move, and the other is `gate._PRODUCERS`.
WIRED: dict[str, str] = {
    "stale_open": "D3.453",
    "not_tradable_fill": "D3.372",
    "undetailed_poll_fill": "D3.469",
    "unarmable_fill": "D3.475",
}


def _published(names: dict[str, str]) -> dict[str, str]:
    """What the running daemon publishes: condition -> its debt origin."""
    return {name: f"{debt} — the row that named it" for name, debt in names.items()}


def _all_fired(names: dict[str, str]) -> dict[str, bool]:
    return {name: True for name in names}


def _scratch_tree(tmp_path: Path, source: str) -> Path:
    """A `nix_home` holding ONE file. Never a copy of `~/nix` (project memory)."""
    home = tmp_path / "nix"
    (home / "scripts").mkdir(parents=True)
    (home / "scripts" / "limiterd.py").write_text(source, encoding="utf-8")
    return home


def _limiterd_source(*, members: dict[str, str], wired: bool = True) -> str:
    """A minimal `limiterd.py` carrying only what `_declared_conditions` reads."""
    body = "\n".join(f'    {name.upper()} = "{name}"' for name in members)
    ingress = (
        "        ingress=uncertainty.before(stopwatch.before(read)),\n"
        if wired
        else "        ingress=stopwatch.before(read),\n"
    )
    return (
        "import enum\n\n\n"
        "class UncertaintyCondition(enum.Enum):\n"
        '    """§14\'s conditions."""\n\n'
        f"{body or '    pass'}\n\n\n"
        "class ProtectiveSenders:\n"
        '    """§5:323\'s fan-out."""\n\n'
        "    def send(self, payload):\n"
        "        return payload\n\n\n"
        "def main():\n"
        "    loop.attach(\n"
        f"{ingress}"
        "        sender_send=senders.send,\n"
        "    )\n"
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the REAL tree derives the real set, and it judges clean
# --------------------------------------------------------------------------


def test_the_REAL_tree_declares_EXACTLY_the_four_conditions_this_arc_wired() -> None:
    declared, wiring = gate._declared_conditions(REPO)
    assert declared == frozenset(WIRED), sorted(declared)
    assert all(wiring.values()), wiring


def test_the_GATE_HOLDS_NO_COPY_of_the_condition_set(tmp_path: Path) -> None:
    """`check_flatten` ARM 6's lesson: a hand-written set is a set that goes stale.

    Proven by CHANGING the subject rather than by grepping the gate: a tree whose
    conditions share not one name with the shipped four must derive to exactly
    those names. A gate carrying a baked-in list would answer with the list.
    """
    invented = {"feed_gone": "X1", "venue_disagrees": "X2"}
    home = _scratch_tree(tmp_path, _limiterd_source(members=invented))
    declared, _wiring = gate._declared_conditions(home)
    assert declared == frozenset(invented), sorted(declared)
    assert not declared & frozenset(WIRED), sorted(declared)


def test_COMPLETENESS_is_SILENT_when_every_declared_condition_FIRED() -> None:
    evidence, findings, cannot = gate._completeness(
        REPO, _all_fired(WIRED), _published(WIRED)
    )
    assert cannot == "", cannot
    assert not findings, findings
    assert any("completeness BY DERIVATION" in line for line in evidence), evidence


def test_the_GATE_DECLARES_the_daemon_and_its_DETECTORS_as_SUBJECTS() -> None:
    """Coverage that is real: a plant in any of these must be able to redden this."""
    for path in (
        "scripts/limiterd.py",
        "scripts/nixrisk/freshness.py",
        "scripts/nixrisk/fills.py",
        "scripts/nixrisk/outcomes.py",
    ):
        assert path in gate.SUBJECTS, path
    assert gate.CORRECTABLE is False and gate.NON_CORRECTABLE_REASON
    assert "subprocess:python" in gate.RESOURCES, gate.RESOURCES
    assert gate.ON_FAIL == "continue"


def test_the_ALLOW_SET_is_JUSTIFIED_entry_by_entry() -> None:
    """An allow-set granted rather than measured is how I9 breaks silently."""
    assert gate._SCAN_ALLOWED_ROOTS
    for root, why in gate._SCAN_ALLOWED_ROOTS.items():
        assert why.strip(), root
    for banned in ("socket", "psycopg", "zmq", "asyncio", "subprocess"):
        assert banned not in gate._SCAN_ALLOWED_ROOTS, banned


def test_ROOTS_OF_keeps_the_nixrisk_package_split_the_allow_set_is_written_in() -> None:
    assert gate._roots_of({"nixrisk.freshness.x", "json", "limiterd"}) == {
        "nixrisk.freshness",
        "json",
        "limiterd",
    }


# --------------------------------------------------------------------------
# THE PLANTS — each must go RED and NAME its condition
# --------------------------------------------------------------------------


def test_PLANT_A_a_producer_that_DETECTED_and_did_not_FIRE_is_named() -> None:
    """§14's exact hazard: the condition holds, the position is real, nothing fires."""
    drove = _all_fired(WIRED)
    drove["stale_open"] = False
    _evidence, findings, cannot = gate._completeness(REPO, drove, _published(WIRED))
    assert cannot == "", cannot
    assert findings, "a producer that never fired was accepted"
    detail = "; ".join(why for _site, why in findings)
    assert "INCOMPLETE PRODUCER SET" in detail, detail
    assert "stale_open" in detail, detail


def test_PLANT_D_a_FIFTH_condition_with_NO_producer_is_named(tmp_path: Path) -> None:
    """The defect this gate exists for: a condition added later and never wired."""
    members = dict(WIRED)
    members["orphaned_position"] = "PLANT D"
    home = _scratch_tree(tmp_path, _limiterd_source(members=members))
    declared, _wiring = gate._declared_conditions(home)
    assert "orphaned_position" in declared, sorted(declared)
    _evidence, _findings, cannot = gate._completeness(
        home, _all_fired(WIRED), _published(members)
    )
    assert cannot, "a condition with no drive and no producer was accepted"
    assert "orphaned_position" in cannot, cannot
    assert "UNMEASURED" in cannot, cannot


def test_PLANT_the_RUNNING_set_and_the_DECLARED_set_DISAGREE(tmp_path: Path) -> None:
    """What an operator acts on is the PUBLISHED set; a divergence is a finding."""
    home = _scratch_tree(tmp_path, _limiterd_source(members=WIRED))
    published = _published(WIRED)
    published.pop("unarmable_fill")
    _evidence, findings, cannot = gate._completeness(home, _all_fired(WIRED), published)
    assert cannot == "", cannot
    detail = "; ".join(why for _site, why in findings)
    assert "RUNNING daemon publishes" in detail, detail
    assert "unarmable_fill" in detail, detail


def test_PLANT_the_producers_are_DECLARED_but_NOT_WIRED(tmp_path: Path) -> None:
    """§7.12 #8: a drive against code the process never composes proves nothing."""
    home = _scratch_tree(tmp_path, _limiterd_source(members=WIRED, wired=False))
    _declared, wiring = gate._declared_conditions(home)
    assert wiring["scan_composed"] is False, wiring
    _evidence, _findings, cannot = gate._completeness(
        home, _all_fired(WIRED), _published(WIRED)
    )
    assert cannot, "an unwired producer set was accepted"
    assert "not WIRED" in cannot, cannot


def test_PLANT_an_EMPTY_condition_set_is_CANNOT_MEASURE_not_a_pass(tmp_path: Path) -> None:
    """A set with no members flattens nothing and would otherwise trivially agree."""
    home = _scratch_tree(tmp_path, _limiterd_source(members={}))
    _evidence, _findings, cannot = gate._completeness(home, {}, {})
    assert cannot, "an empty producer set passed"
    assert "no `UncertaintyCondition` members" in cannot, cannot


# --------------------------------------------------------------------------
# RULE 4 — PLANT BOTH: the same judgement, planted and un-planted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("planted", [True, False])
def test_RULE_4_PLANT_BOTH_the_same_derivation_red_then_green(
    tmp_path: Path, planted: bool
) -> None:
    """The gate's verdict must FOLLOW the subject, not the run.

    A check that only ever reports one colour has not been shown to be measuring
    anything. Same function, same call shape, ONE difference in the subject.
    """
    members = dict(WIRED)
    if planted:
        members["orphaned_position"] = "PLANT"
    home = _scratch_tree(tmp_path / ("red" if planted else "green"),
                         _limiterd_source(members=members))
    _evidence, findings, cannot = gate._completeness(
        home, _all_fired(WIRED), _published(members)
    )
    if planted:
        assert cannot and "orphaned_position" in cannot, (cannot, findings)
    else:
        assert cannot == "" and not findings, (cannot, findings)
