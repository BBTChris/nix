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
#: ARC 047. The §4 cascade the daemon now dispatches INTO. It is a subject of
#: the gate although this arc edited none of it — the arm that places the
#: protective stop lives here, and a plant in it must redden the gate.
FILLS = "scripts/nixrisk/fills.py"
#: ARC 053. The §3 terminal handlers the daemon now CALLS on BOTH resolution
#: paths — `on_reject` from the completion dispatch, `resolve_pending_timeouts`
#: from the per-tick poll. A subject of the gate for the reason `FILLS` is: a
#: plant in either handler must redden it, which it cannot do unless the file is
#: declared. This arc edited none of it.
OUTCOMES = "scripts/nixrisk/outcomes.py"
#: ARC 054. I11's onset SELECTION, which the daemon now CALLS on both onset
#: paths. A subject of the gate for the reason `FILLS` and `OUTCOMES` are, and
#: NOT a duplicate of `check_flatten` ARM 3b (doctrine C.9): that arm measures
#: which orders the selection admits, this gate measures whether anything with a
#: pid ever invokes it. This arc edited none of it.
FLATTEN = "scripts/nixrisk/flatten.py"


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
    # ARC 047 made it TWO — one RELEASED by the cancel arm, one CONVERTED by the
    # fill arm, and §3 makes a fill a terminal release too (*"released on: fill
    # (converts to open-margin)"*). ARC 053 made it FIVE: the reject arm
    # releases one and the pending-timeout arm takes two and releases both.
    # ARC 054 makes it NINE: the onset arm takes four and every one of them is
    # released under its own onset cause (SPEC-A7). The literal moves because the
    # DRIVE does, and the gate derives the same figure from which arms this build
    # can run rather than carrying it as a constant.
    assert f"released={5 + gate.ONSET_RESERVATIONS}" in result.evidence
    # ARC 053 — the two RESOLUTION paths, and the negative property, in the
    # evidence of a PASS. A green that does not say it covered them is a green
    # whose scope a reader cannot see.
    assert "REJECT ARM:" in result.evidence
    assert "1500.0 of committed margin was RELEASED" in result.evidence
    assert "PENDING-TIMEOUT ARM:" in result.evidence
    assert "resends=0" in result.evidence
    assert "NO-RESEND CENSUS:" in result.evidence
    assert "reaches NONE of the venue-placement verbs" in result.evidence
    # And the FILL arm's own evidence: the conversion AND the placed stop.
    assert "FILL ARM:" in result.evidence
    assert "PROTECTIVE STOP is armed at 4998.0" in result.evidence
    assert "Σ open margin 2100.0" in result.evidence
    assert "committed 2100.0 unchanged" in result.evidence
    assert "unstopped=[]" in result.evidence


def test_NON_VACUITY_the_gate_reads_the_WIRED_PATH_DECLARATION_not_a_literal():
    """`WIRED_EVENTS` is imported, so the gate narrows as later arcs wire paths."""
    from nixrisk import completions  # pylint: disable=import-outside-toplevel

    assert gate.WIRED == tuple(completions.WIRED_EVENTS)
    assert "on_cancel" in gate.WIRED
    # ARC 047. The fill arm runs only when the build declares the path, and the
    # gate reads that declaration rather than assuming it — so this asserts the
    # DERIVATION, not the literal.
    assert gate.HAS_CANCEL is ("on_cancel" in completions.WIRED_EVENTS)
    assert gate.HAS_FILL is ("on_fill" in completions.WIRED_EVENTS)
    # ARC 053, derived the same way and for the same reason.
    assert gate.HAS_REJECT is ("on_reject" in completions.WIRED_EVENTS)
    assert "on_reject" in gate.WIRED
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
        "        result = self._dispatcher.dispatch(completion)",
        "        result = DispatchResult(  # PLANT A: the dispatch removed.\n"
        '            Disposition.UNWIRED, completion, "PLANT A"\n'
        "        )",
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
# PLANT D (ARC 047) — the FILL DISPATCH removed. The loop drains a §2A:75 fill
# and nothing converts: the reservation stays taken against an order that has
# already filled, and the position it opened is in no published table.
# ---------------------------------------------------------------------------
def test_PLANT_D_a_daemon_that_DRAINS_the_FILL_and_never_CONVERTS_FAILS(
    tmp_path: Path,
):
    """PLANT D: the fill route removed — the loop drains the exec report, §3's
    reservation never converts to open-margin, and the gate must name it."""
    home = _population(tmp_path)
    _perturb(
        home,
        COMPLETIONS,
        "        if completion.event == EVENT_FILL:\n"
        "            return self._finish(self._dispatch_fill(completion))",
        "        if completion.event == EVENT_FILL:  # PLANT D\n"
        "            return self._finish(\n"
        "                DispatchResult(\n"
        '                    Disposition.UNWIRED, completion, "PLANT D"\n'
        "                )\n"
        "            )",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: drained, not converted — and both halves of §3's lifecycle.
    assert "THE DAEMON DID NOT CONVERT" in result.detail
    assert "DRAINED BY THE LOOP" in result.detail
    assert "fills_dispatched=0" in result.detail
    assert "still 2100.0" in result.detail
    assert "converts to open-margin" in result.detail
    # And it must NOT claim an unprotected position: no capital moved, so
    # nothing is unprotected. The two readings stay apart.
    assert "UNPROTECTED POSITION" not in result.detail


# ---------------------------------------------------------------------------
# PLANT E (ARC 047) — THE SAFETY PLANT. The protective stop is NOT placed and
# the conversion runs anyway. This is the one condition that is worse than not
# wiring fill at all: a live position nothing protects (§4, §12.1; §14 -> FLAT),
# inside the hazard I11 guards. It is the point of this slice.
# ---------------------------------------------------------------------------
def test_PLANT_E_a_daemon_that_CONVERTS_WITHOUT_PLACING_THE_STOP_FAILS(
    tmp_path: Path,
):
    """PLANT E: §4's distance->price arm removed. The remainder release still
    runs, so the capital moves; nothing protects the filled position."""
    home = _population(tmp_path)
    _perturb(
        home,
        FILLS,
        "        state = self._stops.arm(report.price, order)",
        "        state = None  # PLANT E: the protective stop is NOT placed",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    # The SITE is where the stop should have been placed, not where the money
    # was counted — an operator handed `limiterd.py` here would look in the
    # wrong file.
    assert FILLS in result.site
    # THE REASON, by name. Not "a stop is missing" — the PAIR: capital moved
    # and nothing protects the position.
    assert "UNPROTECTED POSITION" in result.detail
    assert "RELEASED 2100.0" in result.detail
    assert "NO STOP for that order" in result.detail
    assert "stops=[]" in result.detail
    # §12.1's synthetic-stop reasoning is carried into the refusal, so the
    # operator reading it is told WHY a missing StopState is a live hazard.
    assert "§12.1 makes the stop SYNTHETIC" in result.detail


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
    assert set(gate.SUBJECTS) == {LIMITERD, COMPLETIONS, FILLS, OUTCOMES, FLATTEN}


# ---------------------------------------------------------------------------
# The same real population, passing unperturbed, AFTER every plant. Without
# this the suite shows only that a gate can fail.
# ---------------------------------------------------------------------------
def test_the_SHIPPED_daemon_still_PASSES_after_every_plant(tmp_path: Path):
    """The same real, unperturbed population still PASSES after every plant
    above — proves the plants, not the fixture, cause the failures."""
    result = gate.run(Mode.VERIFY, _ctx(_population(tmp_path)))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"


# ===========================================================================
# ARC 053 — the two RESOLUTION paths, and the one that can lose money.
#
# Three plants, and the third is not like the other two. PLANT 053A and 053B
# remove a resolution: a reservation leaks, §11.3's Σ stays inflated, and every
# capital rule that reads it becomes more conservative than it should be. That
# is a real defect and it costs opportunity.
#
# PLANT 053C is the one that costs MONEY. §4 resolves a pending timeout by
# `query_order_status` and NEVER by an auto-resend, because a resend puts a
# SECOND LIVE ORDER at the venue while the first is still working — a double
# fill on one signal, with §3 holding one reservation for both. It is the single
# most dangerous defect this arc could introduce, so it is refused twice: by the
# STRUCTURAL census (which runs before anything is driven, precisely so that a
# build that can resend is never driven) and by the driven arm (which watches
# `committed` across twenty further queries, because a second live order needs a
# second reservation and that is the number that would move).
# ===========================================================================


def test_PLANT_053A_a_daemon_that_LEAVES_REJECT_UNWIRED_FAILS_naming_the_leak(
    tmp_path: Path,
):
    """PLANT 053A: `on_reject` removed from `WIRED_EVENTS` — the pre-ARC-053
    daemon exactly. The loop DRAINS the reject and records it UNWIRED, so the
    venue refused the order and its reservation is never returned."""
    home = _population(tmp_path)
    _perturb(
        home,
        COMPLETIONS,
        "WIRED_EVENTS: Final[tuple[str, ...]] = "
        "(EVENT_CANCEL, EVENT_FILL, EVENT_REJECT)",
        "WIRED_EVENTS: Final[tuple[str, ...]] = (EVENT_CANCEL, EVENT_FILL)"
        "  # PLANT 053A",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: drained, not dispatched, and the capital is still committed.
    assert "THE DAEMON DID NOT RELEASE ON A REJECT" in result.detail
    assert "DRAINED BY THE LOOP" in result.detail
    assert "rejects_dispatched=0" in result.detail
    assert "still TAKEN" in result.detail
    # And it must be distinguishable from the INGRESS failure PLANT C models.
    assert "NEVER ARRIVED" not in result.detail


def test_PLANT_053B_a_daemon_whose_POLL_NEVER_RUNS_FAILS_naming_the_ZOMBIE(
    tmp_path: Path,
):
    """PLANT 053B: the poll unhooked from the tick. An order past §12A:830's ack
    deadline is never queried — it hangs indefinitely and its reservation
    leaks. The daemon still HOLDS a poller, so `timeouts` is present and the
    gate must not read this as *this build does not poll*."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        "        ingress=onset.before(booker.before(timeouts.before(_read_both))),",
        "        ingress=onset.before(booker.before(_read_both)),  # PLANT 053B",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: the zombie and the leaked reservation, both named.
    assert "ZOMBIE ORDER" in result.detail
    assert "NOTHING POLLED IT" in result.detail
    assert "polls=0" in result.detail
    assert "reservation LEAKS" in result.detail
    # NOT the cannot-measure branch: the poller is present, it simply never ran.
    assert "holds no §4 pending-timeout poller" not in result.detail


def test_PLANT_053C_a_poll_that_RESENDS_instead_of_QUERYING_FAILS_the_CENSUS(
    tmp_path: Path,
):
    """PLANT 053C — THE DANGEROUS ONE. The poll calls `place_order` on every
    overdue order instead of resolving what the query said. §4 forbids the
    auto-resend outright: the original order is still working at the venue, so
    the resend is a second live order on one signal and one reservation.

    The STRUCTURAL census must catch it, and catching it there rather than by
    driving is the point — the gate refuses to DRIVE a build that can place a
    second order, because the drive would itself be the act of placing it."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        "            records = self._outcomes.resolve_pending_timeouts(self._query)",
        "            records = self._outcomes.resolve_pending_timeouts(self._query)\n"
        "            for _r in records:  # PLANT 053C: §4's forbidden auto-resend\n"
        "                self._query.place_order(_r)",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: the §4 violation, the verb, and the double-order risk.
    assert "NO-RESEND VIOLATION" in result.detail
    assert "place_order" in result.detail
    assert "SECOND LIVE ORDER" in result.detail
    assert "NEVER by an auto-resend" in result.detail


def test_the_NO_RESEND_CENSUS_derives_its_BAN_LIST_from_the_SEAM_not_itself():
    """§7.12: the census would pass while measuring nothing if its ban list were
    empty, or if the closure resolved nothing. Both are refused, and neither
    figure is written in the gate — the verbs come off
    `broker_seam.ORDER_PORT_VERBS`, which that file's own comment calls *"the
    authority, not the docstrings"*."""
    banned, complaint = gate._placement_verbs(REPO)  # pylint: disable=protected-access
    assert not complaint, complaint
    assert "place_order" in banned
    assert "flatten" in banned
    assert "cancel_order" in banned
    # The ONE verb the poll may reach is excluded, not banned.
    assert gate.POLL_ALLOWED_VERB not in banned
    # And the ban list is the seam's, not a copy: every member is on the roster.
    seam = (REPO / gate.BROKER_SEAM_FILE).read_text(encoding="utf-8")
    for verb in banned:
        assert f'"{verb}"' in seam, verb


def test_the_NO_RESEND_CENSUS_is_CANNOT_MEASURE_when_the_SEAM_is_UNREADABLE(
    tmp_path: Path,
):
    """A ban list that could not be derived must never become an empty one.

    This is the vacuity trap the census exists inside: `calls & banned` over an
    empty `banned` is empty for every build, including one that resends on every
    tick. So an unreadable roster is CANNOT_MEASURE, never a pass."""
    home = _population(tmp_path)
    (home / gate.BROKER_SEAM_FILE).write_text("ORDER_PORT_VERBS = 'not a tuple'\n")
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "roster could not be derived" in result.detail


def test_the_NO_RESEND_CENSUS_REFUSES_to_credit_an_ABSENCE_it_cannot_see(
    tmp_path: Path,
):
    """The other half of the vacuity trap: a walk that resolves no calls contains
    no banned verb either, so the census REQUIRES its own reach — the poll's work
    and the one verb it is allowed — before it will credit an absence.

    MEASURED, and the measurement is a second control for free: gutting the poll
    so it does no work makes the census blind AND makes the driven arm find a
    real zombie, so the verdict is FAIL by rule 4 rather than the CANNOT_MEASURE
    this test first expected. Both are named, which is what rule 4 requires — the
    found defect decides the verdict and the blind arm is still reported."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        "            records = self._outcomes.resolve_pending_timeouts(self._query)",
        "            records = ()  # the poll no longer does the poll's work",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    # The census went blind and SAID SO rather than crediting the absence.
    assert "does not reach `resolve_pending_timeouts`" in result.detail
    assert "ALSO UNMEASURED" in result.detail
    # And the driven arm found the real consequence of the same gutting.
    assert "ZOMBIE ORDER" in result.detail


def test_RULE_4_a_FAIL_on_one_arm_OUTRANKS_a_CANNOT_MEASURE_on_another(
    tmp_path: Path,
):
    """THE PLANT-BOTH CONTROL. Rule 4: Fail > Cannot-measure, and the ordering is
    the rule rather than a convenience.

    Both are planted at once — the reject path left UNWIRED (a real, found
    defect) and the venue-verb roster made unreadable (an arm that cannot
    measure at all). The verdict must be FAIL, because cannot-measure is the
    answer for a run with nothing against it; downgrading a found defect because
    a DIFFERENT arm went blind is exactly how a red becomes a light blue.

    And the blind arm must still be NAMED: an operator told `fail` must not also
    be left believing the whole run was judged."""
    home = _population(tmp_path)
    _perturb(
        home,
        COMPLETIONS,
        "WIRED_EVENTS: Final[tuple[str, ...]] = "
        "(EVENT_CANCEL, EVENT_FILL, EVENT_REJECT)",
        "WIRED_EVENTS: Final[tuple[str, ...]] = (EVENT_CANCEL, EVENT_FILL)"
        "  # PLANT: reject unwired",
    )
    (home / gate.BROKER_SEAM_FILE).write_text("ORDER_PORT_VERBS = 'not a tuple'\n")

    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    # The FAIL is the reject leak — the arm that actually found something.
    assert "THE DAEMON DID NOT RELEASE ON A REJECT" in result.detail
    # ...and the arm that could not measure is reported, not absorbed.
    assert "ALSO UNMEASURED" in result.detail
    assert "roster could not be derived" in result.detail


def test_RULE_4_the_SAME_blind_arm_ALONE_is_CANNOT_MEASURE_not_a_PASS(
    tmp_path: Path,
):
    """The other half of the pair, and it is what makes the test above mean
    something: with ONLY the blind arm planted the verdict is CANNOT_MEASURE. If
    this were a PASS, the control above would be showing that FAIL beats PASS."""
    home = _population(tmp_path)
    (home / gate.BROKER_SEAM_FILE).write_text("ORDER_PORT_VERBS = 'not a tuple'\n")
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "roster could not be derived" in result.detail


# ===========================================================================
# ARC 054 — §3:173's ONSET SWEEP, at the DAEMON.
#
# Four plants over TWO halves of one sentence, and the halves fail in opposite
# directions. PLANT 054A and 054B are INCOMPLETENESS: an entry the sweep never
# reaches stays working at the venue and fills inside a window §3:174 says it
# was never approved for. PLANT 054C is OVER-BREADTH, and it is the one that
# costs a position: cancelling or disarming a protective order inside a window
# leaves a REAL open position with nothing under it (§14). ARC 045 measured that
# bug in the library; these controls exist so it cannot reappear one layer up.
#
# PLANT 054B2 is not a duplicate of 054B. 054B's omission is visible in the
# daemon's own published enumeration, so the gate's pre-check catches it before
# anything is swept. 054B2 hides the omission behind a COMPLETE-looking report —
# the failure mode a gate that trusted the enumeration's self-description would
# pass — and it must still fail, because Σ over the ledger's TAKEN set is a
# number `pending_entries()` cannot edit.
# ===========================================================================


def test_PLANT_054A_a_daemon_that_DETECTS_an_onset_and_NEVER_SWEEPS_FAILS(
    tmp_path: Path,
):
    """PLANT 054A: the onset dispatch removed, the COUNTER left in place — the
    pre-ARC-054 daemon with a counter bolted on. It is the worst of the three
    because everything downstream reads it as a sweep: `blackout_onsets` and
    `halt_onsets` advance, and not one entry is cancelled."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        """        if halted and not self._halted:
            self._dispatch(TerminalPath.HALT_ONSET, None)
            self.halt_onsets += 1
            fired += 1
        for symbol in sorted(symbols - self._blackout):
            self._dispatch(TerminalPath.BLACKOUT_ONSET, symbol)
            self.blackout_onsets += 1
            fired += 1""",
        """        if halted and not self._halted:
            self.halt_onsets += 1        # PLANT 054A: dispatch removed
            fired += 1
        for symbol in sorted(symbols - self._blackout):
            self.blackout_onsets += 1    # PLANT 054A: dispatch removed
            fired += 1""",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: no sweep, the SURVIVORS named, and the window they can fill in.
    assert "NO SWEEP" in result.detail
    assert "cdd-onset-a1" in result.detail
    assert "still pending ENTRY orders" in result.detail
    assert "blackout window they were never approved for" in result.detail
    assert '"sweeps": []' in result.detail
    # ...and the capital is demonstrably still committed against them.
    assert "still TAKEN at process exit" in result.detail


def test_PLANT_054B_an_INCOMPLETE_pending_entries_FAILS_naming_the_MISSED_entry(
    tmp_path: Path,
):
    """PLANT 054B: `pending_entries()` drops one order that holds an OUTSTANDING
    §3 reservation. The sweep iterates exactly this enumeration, so the omitted
    order is one no onset can ever cancel — D3.443's whole reason for existing."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        """            entries.append(
                PendingEntry(
                    client_order_id=coid,""",
        """            if coid.endswith("a2"):   # PLANT 054B
                continue
            entries.append(
                PendingEntry(
                    client_order_id=coid,""",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: the MISSED entry, by name, against the order state it is in.
    assert "INCOMPLETE ENUMERATION" in result.detail
    assert "cdd-onset-a2" in result.detail
    assert "hold OUTSTANDING" in result.detail
    assert "the sweep will NEVER cancel" in result.detail
    # NOT the no-sweep reading: the dispatch is intact, the book is not.
    assert "NO SWEEP" not in result.detail


def test_PLANT_054B2_an_omission_the_ENUMERATIONS_OWN_REPORT_HIDES_still_FAILS(
    tmp_path: Path,
):
    """PLANT 054B2: the same omission, plus a `record()` that reports the
    COMPLETE set — so the daemon's published enumeration says nothing is
    missing. The pre-check is defeated by construction and the gate must still
    fail, on Σ over the LEDGER's TAKEN set and on the survivor itself."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        """            entries.append(
                PendingEntry(
                    client_order_id=coid,""",
        """            if coid.endswith("a2"):   # PLANT 054B2
                continue
            entries.append(
                PendingEntry(
                    client_order_id=coid,""",
    )
    _perturb(
        home,
        LIMITERD,
        """        entries = self.pending_entries()
        return {
            "enumerations": self.enumerations,""",
        """        entries = tuple(   # PLANT 054B2: the report HIDES the omission
            PendingEntry(str(r.client_order_id), str(r.strategy_id), str(r.symbol),
                         role=OrderRole.ENTRY)
            for r in self._reservations.outstanding()
        )
        return {
            "enumerations": self.enumerations,""",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: the enumeration LOOKED complete, and the money record disagreed.
    assert "INCOMPLETE ENUMERATION" not in result.detail
    assert "SURVIVED THE SWEEP" in result.detail
    assert "cdd-onset-a2" in result.detail
    assert "did NOT cancel" in result.detail


def test_PLANT_054C_a_sweep_that_UNPROTECTS_a_LIVE_POSITION_FAILS(tmp_path: Path):
    """PLANT 054C — THE DANGEROUS ONE. The daemon's onset dispatch disarms every
    protective stop alongside its entry sweep.

    Disarming is the form over-breadth actually takes here: §12.1 keeps stops
    SYNTHETIC, `StopBook` reaches no broker, so there is no venue message to
    intercept and `forget` IS the act of unprotecting a live position. It is also
    invisible to the no-resend census — `forget` is not a placement verb — which
    is precisely why this control is the driven arm's and not the census's."""
    home = _population(tmp_path)
    _perturb(
        home,
        LIMITERD,
        """        pending = self._book.pending_entries()
        protective_before = self._protective()""",
        """        pending = self._book.pending_entries()
        protective_before = self._protective()
        for _stop in list(self._fills.stops.stops()):   # PLANT 054C
            self._fills.stops.forget(_stop.client_order_id)""",
    )
    result = gate.run(Mode.VERIFY, _ctx(home))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert LIMITERD in result.site
    # THE REASON: the protective book moved, and the POSITION it left bare.
    assert "CHANGED the protective book" in result.detail
    assert "left unprotected inside the window" in result.detail
    assert "cdd-fill-1" in result.detail
    assert "TRD-" in result.detail
    # NOT an incompleteness reading: every entry was still swept correctly.
    assert "did NOT cancel" not in result.detail


def test_the_SHIPPED_daemon_still_PASSES_after_every_ARC_054_plant(tmp_path: Path):
    """The same real, unperturbed population still PASSES after all four onset
    plants — the plants, not the fixture, cause the failures."""
    result = gate.run(Mode.VERIFY, _ctx(_population(tmp_path)))
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    # AND the green SAYS what it watched: a negative property nobody can read
    # off an absence (check contract v2 rule 11).
    assert "ONSET ARM" in (result.evidence or "")
    assert "PROTECTIVE BOOK UNCHANGED" in (result.evidence or "")
    assert "EDGE-triggered" in (result.evidence or "")
