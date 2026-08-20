"""ARC 046 / S5 — the can-fail suite for the daemon-dispatch gate.

Structure follows `docs/nix_check_contract.md` §5.1: non-vacuity FIRST, then one
PLANT per declared arm that must FAIL and NAME its site, then the same real
population passing unperturbed. A demonstration missing the last step shows only
that a gate can fail.

**EVERY CONTROL ASSERTS THE REASON** — a substring of `site` or `detail` naming
WHAT was wrong — never a status and never an exit code (check contract v2 §11 /
`docs/nix_check_contract.md` §18). `FAIL_NEEDS_OPERATOR` is one integer shared by
every arm of the gate, so a control keyed on it alone would pass whenever the
gate failed for any reason at all, including a reason the control did not plant.

**No control touches a production artifact** (doctrine C.8). Every plant builds a
throwaway `nix_home` under `tmp_path` — the REAL `scripts/` and `risks/` copied,
the venv symlinked — and perturbs the COPY. The shipped gate is imported by its
real path and never copied.

**Why a perturbed copy of the real daemon rather than a stub.** The property is
that the RUNNING daemon dispatches; a stub daemon proving a gate can read a stub
is the library-not-process substitution this whole gate exists to refuse. Each
plant is a ONE-LINE removal from a real, working `limiterd` — the smallest edit
that makes the invariant false and leaves everything else true — so a plant that
fires is evidence about the dispatch and not about a fixture.

**PLANT C exists because PLANT A broke the instrument first.** MEASURED, in this
arc: the gate's original non-vacuity signal was `completions.seen`, which is
incremented INSIDE the dispatch, so removing the dispatch made "the loop never
received a completion" and "the loop received one and told nobody" the same
reading. The first is a broken instrument, the second is the defect. `consumed`
was split out from `seen` for exactly that, and PLANT C is what keeps the split
honest: it removes the INGRESS, and the gate must then say *never arrived* while
PLANT A says *arrived and was not dispatched*.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_limiter_daemon_dispatch as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

LIMITERD = "scripts/limiterd.py"
COMPLETIONS = "scripts/nixrisk/completions.py"


def _ctx(home: Path) -> Context:
    return Context(nix_home=home, mode=Mode.VERIFY)


def _population(tmp_path: Path) -> Path:
    """A throwaway `nix_home`: the REAL daemon, copied, and the real venv."""
    home = tmp_path / "nix_home"
    (home).mkdir()
    shutil.copytree(
        REPO / "scripts",
        home / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "tests", "*.pyc"),
    )
    shutil.copytree(REPO / "risks", home / "risks")
    (home / ".venv").symlink_to(REPO / ".venv")
    return home


def _perturb(home: Path, relative: str, old: str, new: str) -> None:
    """Replace exactly one occurrence in the COPY. Refuses a silent no-op."""
    path = home / relative
    text = path.read_text()
    assert text.count(old) == 1, (
        f"the plant's anchor is not unique in {relative} "
        f"({text.count(old)} occurrences) — the plant would not be the "
        "perturbation it claims to be"
    )
    path.write_text(text.replace(old, new))


# ---------------------------------------------------------------------------
# NON-VACUITY, FIRST. A gate that cannot pass on the real population proves
# nothing when it fails on a planted one.
# ---------------------------------------------------------------------------
def test_NON_VACUITY_the_SHIPPED_daemon_PASSES_and_the_evidence_names_the_drive():
    """The real `limiterd` dispatches a real cancel completion. Evidence, not a bit."""
    result = gate.run(Mode.VERIFY, _ctx(REPO))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    # The evidence must SHOW the drive, not assert it: a PASS whose evidence
    # could have been written without running anything is the shape doctrine
    # C.3 refuses.
    assert "drove a real limiterd" in result.evidence
    assert "committed 0.0 -> 2000.0" in result.evidence
    assert "dispatched=1" in result.evidence
    assert "duplicates=1" in result.evidence
    assert "released=1" in result.evidence


def test_NON_VACUITY_the_gate_reads_the_WIRED_PATH_DECLARATION_not_a_literal():
    """`WIRED_EVENTS` is imported, so the gate narrows as later arcs wire paths."""
    from nixrisk import completions  # pylint: disable=import-outside-toplevel

    assert gate.WIRED == tuple(completions.WIRED_EVENTS)
    assert "on_cancel" in gate.WIRED
    # And every §2A event the build does NOT wire is derived, never listed here.
    assert set(gate.UNWIRED_CANDIDATES) == set(completions.SPEC_EVENTS) - set(
        gate.WIRED
    )


def test_the_COPIED_population_PASSES_before_any_plant(tmp_path: Path):
    """The fixture itself is honest: an unperturbed copy is green."""
    result = gate.run(Mode.VERIFY, _ctx(_population(tmp_path)))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"


# ---------------------------------------------------------------------------
# PLANT A — the DISPATCH removed. The daemon drains the completion and never
# tells §3. This is the pre-ARC-046 daemon, and it is I1.
# ---------------------------------------------------------------------------
def test_PLANT_A_a_daemon_that_DRAINS_the_cancel_and_never_dispatches_FAILS(
    tmp_path: Path,
):
    """PLANT A: the dispatch call removed — the loop drains the completion and
    never tells §3, so committed stays inflated and the gate must say so."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        "        self._dispatcher.dispatch(completion)\n        self._unlink(item)",
        "        # PLANT A: the dispatch removed.\n        self._unlink(item)",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON, not the code: the loop DRAINED it, and committed is inflated.
    assert "THE DAEMON DID NOT RELEASE" in result.detail
    assert "DRAINED BY THE LOOP (consumed=1" in result.detail
    assert "dispatched=0" in result.detail
    assert "still 2000.0" in result.detail
    # And the leak is named at the process boundary too.
    assert "outstanding=1" in result.detail


# ---------------------------------------------------------------------------
# PLANT B — the §4:214 DEDUP defeated. A re-delivered exec report reaches §3.
# ---------------------------------------------------------------------------
def test_PLANT_B_a_daemon_whose_DEDUP_lets_a_REDELIVERY_through_FAILS(
    tmp_path: Path,
):
    """PLANT B: the §4:214 dedup defeated — a re-delivered exec report reaches
    §3, and the gate must name the missing daemon-level guard, not just a red."""
    home = _population(tmp_path)
    _perturb(
        home,
        COMPLETIONS,
        "        if key in self._keys:\n            return False",
        "        if False and key in self._keys:  # PLANT B\n            return False",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert COMPLETIONS in result.site
    assert "duplicates=0" in result.detail
    assert "§4:214 dedup did not see it" in result.detail
    # §7.12 #5 — and it names WHOSE guard actually stopped the second release.
    # `reservations.py`'s (ARC 044 / I2) still holds, which is why the plant
    # produces a booked REFUSAL rather than a second decrement of Σ. The gate
    # must fail on the missing daemon-level guard and say so, rather than pass
    # because the layer below happened to cover for it.
    assert "the LEDGER booked 1 refusal" in result.detail


# ---------------------------------------------------------------------------
# PLANT C — the INGRESS removed. Distinct from PLANT A, and the gate must say
# so: "never arrived" is a broken instrument, "arrived and was dropped" is the
# defect. See the module docstring.
# ---------------------------------------------------------------------------
def test_PLANT_C_a_daemon_that_never_READS_a_completion_FAILS_as_NEVER_ARRIVED(
    tmp_path: Path,
):
    """PLANT C: the completion ingress removed — the gate must report NEVER
    ARRIVED, distinct from PLANT A's arrived-and-was-dropped, per the module
    docstring's non-vacuity split."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        "        taken = command_ingress(tick)\n        completion_ingress(tick)",
        "        taken = command_ingress(tick)  # PLANT C: completion read removed",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    assert "NON-VACUITY" in result.detail
    assert "never advanced" in result.detail
    # And it must NOT claim the dispatch failed — it cannot know that.
    assert "THE DAEMON DID NOT RELEASE" not in result.detail


# ---------------------------------------------------------------------------
# RULE 10 — a property proven while its subject is unavailable is not proven.
# ---------------------------------------------------------------------------
def test_a_population_with_NO_limiterd_is_CANNOT_MEASURE_and_never_PASS(
    tmp_path: Path,
):
    """Rule 10: no limiterd to observe means CANNOT_MEASURE, never PASS."""
    home = tmp_path / "empty"
    (home / "scripts").mkdir(parents=True)
    (home / ".venv").symlink_to(REPO / ".venv")
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "limiterd" in result.detail


def test_a_daemon_that_REFUSES_TO_BOOT_is_CANNOT_MEASURE_and_never_PASS(
    tmp_path: Path,
):
    """A limiterd that exits before serving anything is CANNOT_MEASURE, never PASS."""
    home = _population(tmp_path)
    (home / LIMITERD).write_text(
        '"""PLANT: a limiterd that refuses to boot."""\nimport sys\n'
        'sys.stderr.write("planted boot refusal\\n")\nsys.exit(2)\n'
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "boot" in result.detail
    assert "planted boot refusal" in result.detail


# ---------------------------------------------------------------------------
# A build that wires NOTHING has no subject. Not a pass.
# ---------------------------------------------------------------------------
def test_a_build_that_WIRES_NO_EVENT_is_CANNOT_MEASURE(monkeypatch: pytest.MonkeyPatch):
    """A build with WIRED empty has no subject to measure — CANNOT_MEASURE,
    not a vacuous PASS."""
    monkeypatch.setattr(gate, "WIRED", ())
    result = gate.run(Mode.VERIFY, _ctx(REPO))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "WIRED_EVENTS is empty" in result.detail


# ---------------------------------------------------------------------------
# The declarations the plan is derived from (check contract rules 6 and 12).
# ---------------------------------------------------------------------------
def test_the_gate_DECLARES_the_subprocess_and_the_temp_write_it_actually_makes():
    """The declared RESOURCES/CORRECTABLE/DEPENDS_ON/SUBJECTS match what the
    gate actually does (check contract rules 6 and 12)."""
    assert "subprocess:python" in gate.RESOURCES
    assert "file-write:/tmp" in gate.RESOURCES
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON
    assert not gate.DEPENDS_ON
    assert set(gate.SUBJECTS) == {LIMITERD, COMPLETIONS}


# ---------------------------------------------------------------------------
# The same real population, passing unperturbed, AFTER every plant. Without
# this the suite shows only that a gate can fail.
# ---------------------------------------------------------------------------
def test_the_SHIPPED_daemon_still_PASSES_after_every_plant(tmp_path: Path):
    """The same real, unperturbed population still PASSES after every plant
    above — proves the plants, not the fixture, cause the failures."""
    result = gate.run(Mode.VERIFY, _ctx(_population(tmp_path)))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
