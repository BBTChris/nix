"""ARC 030 / sub-agent B — the can-fail suite for `checks/check_flatten.py`.

Structure follows `nix_check_contract.md` §5.1 / the `check_reservation_lifecycle`
precedent: non-vacuity FIRST (the real tree passes), then plants that must FAIL
and NAME their site, then the plants removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of `flatten.py` and its
frozen collaborators (`seam.py`, `picture.py`, `reservations.py`,
`broker_seam.py`), perturbs the COPY, and drives the SHIPPED gate's own bytes
against it. `scripts/nixrisk/flatten.py` is read and never written by this suite.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# missing-function-docstring: the helpers below are named after what they do
# to one file (`_run`, `_plant`) and a docstring would restate the name. Added
# ARC 037/A: measured PRE-EXISTING on the untouched tree (pylint exit 16 over
# this file alone), surfaced by an unrelated one-line change bringing the file
# into a commit's hook scope.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_flatten as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "scripts/nixrisk/flatten.py",
    # ARC 037 (D3.220): flatten.py imports the realized-P&L arithmetic, so a
    # scratch tree without it cannot import the subject at all.
    "scripts/nixrisk/realized.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/reservations.py",
    "scripts/nixrisk/__init__.py",
)
BROKER = ("scripts/broker/broker_seam.py",)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the executor and its frozen seams."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in NIXRISK + BROKER:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    """Rewrite the COPIED flatten.py. Fails loudly if the anchor moved."""
    path = home / gate.FLATTEN_FILE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# The precedence guard the reverse-ordering arm depends on — a real line of the
# shipped executor.
_DISCRETIONARY_GUARD = (
    "        prior = self._closed.get(target.trade_id)\n"
    "        if prior is not None:\n"
    "            if authority is CloseAuthority.DISCRETIONARY:"
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_FOUR_arms() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "zero-wire fire" in result.evidence, result.evidence
    assert "dual-authority precedence" in result.evidence, result.evidence
    assert "onset-cancel" in result.evidence, result.evidence
    assert "reconcile-then-publish" in result.evidence, result.evidence


def test_the_GATE_DECLARES_flatten_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.FLATTEN_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the exit path is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


# --------------------------------------------------------------------------
# PLANT 1 — zero-wire: couple the exit to the wire
# --------------------------------------------------------------------------


def test_a_WIRE_COUPLED_FIRE_fails_and_NAMES_the_wire_dependency(home: Path) -> None:
    """Publishing before flattening reddens the zero-wire arm: the dead sink
    raises before the broker is ever reached."""
    _plant(
        home,
        "        if trigger in _R4_TRIGGERS:",
        "        self._picture.publish(self._picture.current())\n"
        "        if trigger in _R4_TRIGGERS:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "fire[zero-wire]" in result.site, result.site
    assert "wire dependency" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — precedence: the discretionary-cannot-override guard removed
# --------------------------------------------------------------------------


def test_a_REMOVED_PRECEDENCE_GUARD_fails_and_NAMES_the_reverse_ordering(
    home: Path,
) -> None:
    """With the DISCRETIONARY guard gone, a discretionary close arriving after a
    protective one for the same trade EXECUTES and overwrites the winner — the
    exact hazard §4's 'protective always wins' forbids."""
    _plant(
        home,
        _DISCRETIONARY_GUARD,
        "        prior = self._closed.get(target.trade_id)\n"
        "        if False:  # PLANTED: discretionary guard disabled\n"
        "            if authority is CloseAuthority.DISCRETIONARY:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "precedence-reverse" in result.site, result.site
    assert "must be DROPPED" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — onset: collapse HALT_ONSET to a bare CANCEL
# --------------------------------------------------------------------------


def test_an_ONSET_CAUSE_COLLAPSED_TO_CANCEL_fails_and_NAMES_the_wrong_cause(
    home: Path,
) -> None:
    """SPEC-A7: booking a HALT-onset release under a shared CANCEL erases which
    onset released the capital. The plant forces every onset release via CANCEL."""
    # ARC 038 / C (FC1): the release is now inside a `try:` in
    # `cancel_entries_on_onset` — a persistence failure out of `resolve` may not
    # abort the sweep (§3:172 cancels ALL pending entries) — so the anchor gained
    # one indent level. `_plant` asserts the anchor appears exactly once, so a
    # stale anchor reddens LOUDLY rather than planting nothing, which is why this
    # was caught by the suite and not by a reviewer.
    _plant(
        home,
        "                resolution = self._ledger.resolve(\n"
        "                    entry.client_order_id, cause, now, reason=cause.value\n"
        "                )",
        "                resolution = self._ledger.resolve(\n"
        "                    entry.client_order_id, TerminalPath.CANCEL, now, "
        "reason=cause.value\n"
        "                )",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "onset" in result.site, result.site
    assert "released via" in result.detail, result.detail
    assert "not HALT_ONSET" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 — reconcile-then-publish: publish the pre-flatten INTENT
# --------------------------------------------------------------------------


def test_RECONCILE_PUBLISHING_THE_INTENT_fails_and_NAMES_the_wrong_balance(
    home: Path,
) -> None:
    """A `reconcile_and_publish` that commits the pre-flatten projection balance
    instead of broker truth reddens the confirmed-state arm."""
    _plant(
        home,
        "        realized_delta = balance.cash - projection.balance\n"
        "        rows = self._confirmed_rows(projection, held_symbols)\n"
        "\n"
        "        picture = self._picture.commit(\n"
        "            balance=balance.cash,",
        "        realized_delta = balance.cash - projection.balance\n"
        "        rows = self._confirmed_rows(projection, held_symbols)\n"
        "\n"
        "        picture = self._picture.commit(\n"
        "            balance=projection.balance,  # PLANTED: publishes the intent",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "reconcile_and_publish" in result.site, result.site
    assert "broker truth" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.FLATTEN_FILE).read_bytes()
    _plant(
        home,
        _DISCRETIONARY_GUARD,
        "        prior = self._closed.get(target.trade_id)\n"
        "        if False:  # PLANTED: discretionary guard disabled\n"
        "            if authority is CloseAuthority.DISCRETIONARY:",
    )
    planted = _run(home)
    (home / gate.FLATTEN_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.FLATTEN_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent subject is not agreement
# --------------------------------------------------------------------------


def test_an_ABSENT_FLATTEN_MODULE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.FLATTEN_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = sys.modules.get("nixrisk.flatten")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("nixrisk.flatten") is real, (
        "the gate left the tmp_path copy of nixrisk.flatten in sys.modules"
    )


# --------------------------------------------------------------------------
# ARC 045 / I11 — the ONSET SELECTION arm (ARM 3b), bound from three plants
# --------------------------------------------------------------------------
#
# Each plant is ONE literal edit to the COPIED subject, and each names a
# different half of §3:172-174. A/B are FAIL (exit 1); C is CANNOT_MEASURE
# (exit 2), because an order kind the arm cannot classify is a completeness it
# did not measure — never a PASS (check contract rule 10, D3.440).


#: A unique anchor on `OrderRole.PROTECTIVE`. The bare member line is NOT
#: unique — `CloseAuthority` carries the same spelling — and `_plant` refuses a
#: multi-hit anchor, which is the helper doing its job rather than a nuisance.
_ORDER_ROLE_TAIL = (
    '    PROTECTIVE = "protective"\n'
    "\n"
    "\n"
    "#: ARC 045 / I11. The order roles an onset sweep MAY cancel."
)

#: The selectivity guard's two spellings. PLANT B widens it by exactly the two
#: members §3:173 excludes — the smallest edit that unprotects a live position.
_ROLES_NARROW = (
    "_CANCELLABLE_ROLES: frozenset[OrderRole] = frozenset({OrderRole.ENTRY})"
)
_ROLES_WIDE = (
    "_CANCELLABLE_ROLES: frozenset[OrderRole] = frozenset(\n"
    "    {OrderRole.ENTRY, OrderRole.EXIT, OrderRole.PROTECTIVE}\n"
    ")"
)


def test_the_REAL_TREE_passes_the_SELECTION_arm_and_the_EVIDENCE_names_it() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "onset SELECTION" in result.evidence, result.evidence
    assert "complete by derivation" in result.evidence, result.evidence
    # Non-vacuity of the arm itself: it says what it staged, so a green over an
    # empty scope is not readable as a green over a real one.
    assert "3 entries + 2 exits + 1 open position staged" in result.evidence, (
        result.evidence
    )
    # ARC 048 / I3 added ARM 6 (exhaustive wire-freedom). The count is asserted
    # rather than described so an arm silently dropped from `run` reddens here.
    assert "6 arms" in result.evidence, result.evidence


def test_PLANT_A_an_INSCOPE_ENTRY_SURVIVES_the_onset_FAILS_and_NAMES_it(
    home: Path,
) -> None:
    """INCOMPLETE. The sweep reaches only the first entry; two stay working."""
    _plant(
        home,
        "        for entry in pending:",
        "        for entry in tuple(pending)[:1]:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "cancel_entries_on_onset[selection]" in result.site, result.site
    assert "INCOMPLETE" in result.detail, result.detail
    # It names the SURVIVING entries, not merely a count.
    assert "c-a2" in result.detail and "c-b1" in result.detail, result.detail
    # ...and the window they can now fill in.
    assert "fill inside the HALT window" in result.detail, result.detail
    assert "§3:174" in result.detail, result.detail


def test_PLANT_B_the_predicate_CANCELS_AN_EXIT_FAILS_and_NAMES_the_position(
    home: Path,
) -> None:
    """OVER-BROAD — the dangerous one. Widening `_CANCELLABLE_ROLES` by one
    literal turns the onset sweep into something that cancels a protective stop
    guarding a live position, which is what §14 exists to prevent."""
    _plant(
        home,
        _ROLES_NARROW,
        _ROLES_WIDE,
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "cancel_entries_on_onset[selection]" in result.site, result.site
    assert "OVER-BROAD" in result.detail, result.detail
    # It names the cancelled protective order...
    assert "c-stop" in result.detail, result.detail
    # ...and the position that cancel left unprotected.
    assert "MESU6" in result.detail, result.detail
    assert "UNPROTECTED" in result.detail, result.detail
    assert "§14" in result.detail, result.detail


def test_PLANT_C_an_UNCLASSIFIABLE_ENTRY_KIND_is_CANNOT_MEASURE_never_PASS(
    home: Path,
) -> None:
    """A new `OrderRole` member the arm has no disposition for. The arm must
    refuse to certify completeness rather than pass over a kind it cannot
    place — the D3.440 lesson, one module over."""
    _plant(
        home,
        _ORDER_ROLE_TAIL,
        '    PROTECTIVE = "protective"\n    ICEBERG = "iceberg"'
        + _ORDER_ROLE_TAIL[len('    PROTECTIVE = "protective"') :],
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    # It NAMES the kind it could not classify.
    assert "iceberg" in result.detail, result.detail
    assert "cannot classify" in result.detail, result.detail
    assert "D3.440" in result.detail, result.detail
    # And it is emphatically not a pass.
    assert result.status is not Status.PASS


def test_PLANT_C_and_a_REAL_FAIL_TOGETHER_report_the_FAIL(home: Path) -> None:
    """Contract rule 4: Fail > Cannot-measure. A tree carrying both must not
    hide a real violation behind an unmeasured one."""
    _plant(
        home,
        _ORDER_ROLE_TAIL,
        '    PROTECTIVE = "protective"\n    ICEBERG = "iceberg"'
        + _ORDER_ROLE_TAIL[len('    PROTECTIVE = "protective"') :],
    )
    _plant(
        home,
        "        for entry in pending:",
        "        for entry in tuple(pending)[:1]:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result


def test_THE_PLANTS_REMOVED_the_SAME_TREE_PASSES(home: Path) -> None:
    """The both-halves close: the throwaway tree is not passing because it is a
    copy, and the plants above are not failing for an environmental reason."""
    before = _run(home)
    assert before.status is Status.PASS, before

    _plant(
        home,
        _ROLES_NARROW,
        _ROLES_WIDE,
    )
    planted = _run(home)
    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted

    _plant(
        home,
        _ROLES_WIDE,
        _ROLES_NARROW,
    )
    after = _run(home)
    assert after.status is Status.PASS, after


# --------------------------------------------------------------------------
# ARM 6 — EXHAUSTIVE wire-freedom (ARC 048 / I3, discharging FC5 / D3.373)
# --------------------------------------------------------------------------
#
# ARM 1 drives ONE trigger against ONE dead surface. ARC 038 / sub-agent C
# measured what that misses and filed it as FC5: a wire dependency reachable
# from a trigger ARM 1 never drives is invisible. ARC 048 / S1 re-measured it
# before writing the arm — PLANT A below left a real position OPEN at the
# broker and the gate returned rc=0 — so these controls pin a defect that was
# observed, not one that was imagined.


def _plant_seam(home: Path, old: str, new: str) -> None:
    """PLANT C edits the frozen seam, not the executor — hence its own helper."""
    path = home / "scripts/nixrisk/seam.py"
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


#: The `reason` default line inside `fire`, unique in the module. PLANT A hangs
#: a wire touch off it guarded on ONE trigger, which is what a real per-trigger
#: dependency looks like — a stale-price flatten "just checking the bus first".
_FIRE_REASON_DEFAULT = (
    '            reason = f"protective flatten (trigger={trigger.value})"\n'
)
_FIRE_REASON_WIRED = _FIRE_REASON_DEFAULT + (
    "        if trigger is FlattenTrigger.STALE_PRICE:\n"
    "            self._picture.publish(self._picture.current())\n"
)


def test_the_REAL_TREE_passes_ARM_6_and_the_EVIDENCE_names_its_DERIVATIONS() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "EXHAUSTIVE wire-freedom" in result.evidence, result.evidence
    # The evidence has to say what made it exhaustive, or a green over one
    # trigger reads identically to a green over all of them — which is the
    # exact confusion FC5 recorded.
    assert "every fireable FlattenTrigger" in result.evidence, result.evidence
    assert "BOTH target shapes" in result.evidence, result.evidence
    assert "Plane-1 delivery wire DEAD" in result.evidence, result.evidence
    assert "AST-derived" in result.evidence, result.evidence


def test_PLANT_A_a_WIRE_DEPENDENCY_on_an_UNDRIVEN_TRIGGER_FAILS_and_NAMES_it(
    home: Path,
) -> None:
    """FC5's own shape. ARM 1 drives SYNTHETIC_STOP; this wires STALE_PRICE.

    Measured at ARC 048 / S1 against the pre-extension gate: rc=0, `pass:`,
    with `still_open=['MESU6']` at the broker. The whole point of ARM 6 is that
    this now reddens, so the control asserts the REASON and not the status —
    the trigger, the wire, and the position left open (contract rule 11).
    """
    _plant(home, _FIRE_REASON_DEFAULT, _FIRE_REASON_WIRED)
    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "fire[wire-freedom]" in result.site, result.site
    assert "trigger=stale_price" in result.detail, result.detail
    assert "ConnectionError" in result.detail, result.detail
    assert "OPEN at the broker" in result.detail, result.detail
    assert "§14:969" in result.detail, result.detail
    # BOTH target shapes must report it — §4's untargeted uncertainty flatten
    # and the targeted per-trade close are two distinct broker-flatten sites.
    assert "(targeted)" in result.detail, result.detail
    assert "(untargeted)" in result.detail, result.detail


def test_PLANT_C_an_UNCLASSIFIABLE_TRIGGER_is_CANNOT_MEASURE_never_PASS(
    home: Path,
) -> None:
    """A newly declared trigger the arm has no disposition for.

    The I2/I11 completeness lesson: the arm cannot know whether a new member is
    meant to fire or to be refused, and either guess certifies a path it never
    drove. It must say so and name the member (§17: never a PASS).
    """
    _plant_seam(
        home,
        '    SENTINEL = "sentinel"\n',
        '    SENTINEL = "sentinel"\n    MARGIN_CALL = "margin_call"\n',
    )
    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "margin_call" in result.detail, result.detail
    assert "NO disposition" in result.detail, result.detail


def test_PLANT_D_an_UNREACHED_EXIT_SITE_FAILS_because_COMPLETENESS_is_the_POINT(
    home: Path,
) -> None:
    """A DERIVED `self._broker.flatten()` site the drive never enters.

    Completeness is the obligation (contract rule 4). The set of protective-exit
    sites is derived from the subject's own AST, so a NEW exit the drive does
    not reach is a protective path this arm proved nothing about — which is the
    general form of the defect FC5 recorded in the particular.
    """
    _plant(
        home,
        "    def request_close(\n",
        "    def emergency_flatten(self, symbol: str) -> None:\n"
        "        self._broker.flatten(symbol)\n"
        "\n"
        "    def request_close(\n",
    )
    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "never entered" in result.detail, result.detail
    assert "ProtectiveFlatten.emergency_flatten" in result.detail, result.detail


def test_a_DISPOSITION_the_SUBJECT_DISAGREES_WITH_is_CANNOT_MEASURE(
    home: Path,
) -> None:
    """The subject stops refusing SENTINEL while the arm still calls it refused.

    Not a wire question, so not a FAIL: what the arm cannot do is say what this
    trigger is supposed to DO, and driving it either way would assert the arm's
    opinion rather than the subject's contract.
    """
    _plant(
        home,
        "_R4_TRIGGERS: frozenset[FlattenTrigger] = frozenset({FlattenTrigger.SENTINEL})",
        "_R4_TRIGGERS: frozenset[FlattenTrigger] = frozenset()",
    )
    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "sentinel" in result.detail, result.detail
    assert "disagree" in result.detail, result.detail


def test_ARM_6_PLANTS_REMOVED_the_SAME_TREE_PASSES(home: Path) -> None:
    """Both halves: the tree is not passing because it is a copy, and PLANT A is
    not failing for an environmental reason. Same tree, three verdicts."""
    before = _run(home)
    assert before.status is Status.PASS, before

    _plant(home, _FIRE_REASON_DEFAULT, _FIRE_REASON_WIRED)
    planted = _run(home)
    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted

    _plant(home, _FIRE_REASON_WIRED, _FIRE_REASON_DEFAULT)
    after = _run(home)
    assert after.status is Status.PASS, after
