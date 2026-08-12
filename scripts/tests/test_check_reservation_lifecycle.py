"""ARC 028 / B — the can-fail suite for the reservation-lifecycle gate.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their site, then the plants removed and the same
population passing. A demonstration missing the last step shows only that a gate
can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds a
throwaway `nix_home` under `tmp_path` holding a COPY of the real ledger, the real
frozen seam and the real frozen spec, perturbs the COPY, and drives the SHIPPED
gate's own bytes against it. `scripts/nixrisk/reservations.py` is read and never
written.

**Every control asserts the REASON** — the site and the named condition — never
the exit code or the status alone (check contract v2 §11).

**BOTH DIRECTIONS ARE PLANTED, because they are not symmetric.** A leak leaves
capital committed forever; a double release under-counts committed margin and
lets the system over-commit. `test_the_DOUBLE_RELEASE_plant_is_INVISIBLE_to_a
_naive_leak_test` drives the planted ledger directly and shows the ledger still
drains to empty under it — which is why "outstanding is empty" is never this
gate's evidence.
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

import check_reservation_lifecycle as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SEAM = "scripts/nixrisk/seam.py"
INIT = "scripts/nixrisk/__init__.py"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the ledger, the seam and the spec."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    for rel in (gate.LEDGER, SEAM, INIT, SPEC):
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    """Rewrite the COPIED ledger. Fails loudly if the anchor moved."""
    path = home / gate.LEDGER
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# The anchors, spelled once. Each is a real line of the shipped ledger.
_SETTLE_ANCHOR = "        released = dataclasses.replace(\n            live,"
_REFUSE_ANCHOR = (
    "            return Resolution(\n"
    "                refusal=self._refuse_duplicate(client_order_id, via, prior)\n"
    "            )"
)
_SIGMA_ANCHOR = "        return self._sigma"
_EMIT_ANCHOR = (
    "        self._emit(EventKind.RESERVATION_RELEASED, released, "
    "reason or via.value, now)"
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real spec, a real ledger, real margin
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_DRIVEN() -> None:
    """The credibility floor: five spec paths, real margin, real Plane-1 rows."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "§3 release paths 5 parsed from the frozen spec at run time" in (
        result.evidence
    ), result.evidence
    assert "15 reservation(s) taken over 40118.75 of margin" in result.evidence, (
        result.evidence
    )
    assert "15 released" in result.evidence, result.evidence
    assert "5 duplicate terminal event(s) refused" in result.evidence, result.evidence
    assert "30 Plane-1 row(s) booked" in result.evidence, result.evidence


def test_the_PATH_SET_is_PARSED_FROM_THE_SPEC_and_appears_NOWHERE_in_the_gate() -> None:
    """B2's circularity guard, mechanised.

    If the expected path set were a constant in this gate, the gate would be
    proving the ledger covers a set the gate itself chose — and a member the
    ledger added would be covered by construction. The set must come from §3's
    own sentence and from nowhere else.
    """
    paths, complaint = gate.spec_paths(REPO)

    assert complaint == "", complaint
    assert set(paths) == {
        "FILL",
        "CANCEL",
        "REJECT",
        "PENDING_TIMEOUT",
        "BLACKOUT_ONSET",
    }, f"§3 parsed to {sorted(paths)}"
    source = Path(gate.__file__).read_text(encoding="utf-8")
    for member in paths:
        assert member not in source, (
            f"{member} appears in the gate's own source — the expected side "
            "would then be a constant this gate chose, which is exactly the "
            "circularity B2 names"
        )


def test_the_GATE_reads_the_SPEC_SIDE_from_the_TREE_UNDER_TEST(home: Path) -> None:
    """Scope containment (§5.3): editing the copied spec moves the expected set."""
    spec = home / SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "pending-timeout resolution, blackout-onset cancellation.",
            "pending-timeout resolution.",
        ),
        encoding="utf-8",
    )

    paths, complaint = gate.spec_paths(home)

    assert complaint == "", complaint
    assert "BLACKOUT_ONSET" not in paths, paths
    assert "PENDING_TIMEOUT" in paths, paths


# --------------------------------------------------------------------------
# PLANT 1 — THE LEAK. Zero releases on one of §3's paths.
# --------------------------------------------------------------------------


def test_a_LEAKED_reservation_on_ONE_SPEC_PATH_fails_and_NAMES_that_path(
    home: Path,
) -> None:
    """`_settle` short-circuits for one path: the caller is told 'released' and
    the reservation never leaves the TAKEN set. Capital is committed forever."""
    _plant(
        home,
        _SETTLE_ANCHOR,
        "        if via is TerminalPath.BLACKOUT_ONSET:\n"
        "            return dataclasses.replace(\n"
        "                live,\n"
        "                state=ReservationState.RELEASED,\n"
        "                released_ts=now,\n"
        "                released_via=via,\n"
        "            )\n" + _SETTLE_ANCHOR,
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "resolve[BLACKOUT_ONSET]" in result.site, result.site
    assert "a LEAK" in result.detail, result.detail
    assert "capital stays committed" in result.detail, result.detail
    for untouched in ("resolve[FILL]", "resolve[REJECT]", "resolve[CANCEL]"):
        assert untouched not in result.site, (
            f"{untouched} was named by a plant that only touched BLACKOUT_ONSET "
            f"— the gate is not discriminating per path: {result.site}"
        )


# --------------------------------------------------------------------------
# PLANT 2 — THE DOUBLE RELEASE. §4's remainder-cancel absorbed after the fill.
# --------------------------------------------------------------------------


def test_an_ABSORBED_DOUBLE_RELEASE_fails_and_names_the_SECOND_TERMINAL_EVENT(
    home: Path,
) -> None:
    """The realistic shape, not a synthetic one: §4 says the IOC remainder-cancel
    can lose the race to the fill, so the cancel arrives after the reservation is
    already released. Releasing again decrements Σ twice for one commitment."""
    _plant(
        home,
        _REFUSE_ANCHOR,
        "            self._sigma -= prior.margin\n"
        "            return Resolution(released=prior)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "+duplicate]" in result.site, result.site
    assert "a SECOND terminal event" in result.detail, result.detail
    assert "was ACCEPTED" in result.detail, result.detail
    assert "over-commit" in result.detail, result.detail
    assert "DOUBLE RELEASE" in result.detail, result.detail


def test_the_DOUBLE_RELEASE_plant_is_INVISIBLE_to_a_naive_leak_test(
    home: Path,
) -> None:
    """B3 measured rather than asserted, on the SAME plant as the test above.

    A leak test that only checks the ledger drains to zero PASSES over this
    defect: `outstanding()` is empty and every reservation reported a release.
    What moved is Σ, which goes NEGATIVE — which is why this gate's evidence is
    the Σ trajectory and the §11.7 reconcile, and never "outstanding is empty".
    """
    _plant(
        home,
        _REFUSE_ANCHOR,
        "            self._sigma -= prior.margin\n"
        "            return Resolution(released=prior)",
    )
    loaded, error = gate.load(home)
    assert loaded is not None, error

    rec = gate.Recorder()
    ledger = loaded.reservations.ReservationLedger(rec)
    orders = gate._orders(loaded, "probe")  # pylint: disable=protected-access
    for order in orders:
        ledger.take(order, 1.0)
    booked = sum(order.proposed_margin for order in orders)
    for order in orders:
        ledger.resolve(order.client_order_id, loaded.seam.TerminalPath.FILL, 2.0)
    # The duplicate: §4's remainder-cancel arriving after the fill release.
    ledger.resolve(orders[0].client_order_id, loaded.seam.TerminalPath.CANCEL, 3.0)

    assert ledger.outstanding() == (), (
        "the naive leak test's own predicate must still hold under this plant, "
        "or the plant is not the defect B3 describes"
    )
    assert len(ledger.released()) == len(orders), ledger.released()
    assert ledger.total_reserved() == pytest.approx(-orders[0].proposed_margin), (
        f"Σ is {ledger.total_reserved()!r} — the double release must drive the "
        f"aggregate NEGATIVE by exactly the re-released margin "
        f"{orders[0].proposed_margin!r}, which is the signature 'drains to zero' "
        f"cannot see (booked {booked!r})"
    )
    audit = ledger.audit()
    assert audit.material, (
        f"§11.7's reconcile must call this material: drift {audit.drift!r} "
        f"against tolerance {audit.tolerance!r}"
    )


# --------------------------------------------------------------------------
# PLANT 3 — Σ DERIVED FROM THE STORE, which makes §11.7's reconcile vacuous
# --------------------------------------------------------------------------


def test_a_SIGMA_COMPUTED_FROM_THE_STORE_fails_and_says_the_RECONCILE_is_vacuous(
    home: Path,
) -> None:
    """§11.3 requires an incremental aggregate. A derived one cannot disagree
    with a full scan of the same store, so drift is 0.0 over any defect."""
    _plant(
        home,
        _SIGMA_ANCHOR,
        "        return math.fsum(res.margin for res in self._live.values())",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "total_reserved" in result.site, result.site
    assert "compare a value with itself" in result.detail, result.detail
    assert "incremental running aggregate" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 — the Plane-1 RECORD diverging from the money truth (§12.10)
# --------------------------------------------------------------------------


def test_a_DOUBLE_BOOKED_PLANE1_ROW_fails_even_though_the_MONEY_is_correct(
    home: Path,
) -> None:
    """Σ, the TAKEN set and the audit are all clean under this plant. Only the
    auditable record is wrong — and §9 makes that record the money truth."""
    _plant(home, _EMIT_ANCHOR, _EMIT_ANCHOR + "\n" + _EMIT_ANCHOR)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "Plane 1 carries 2 reservation_released row(s)" in result.detail, (
        result.detail
    )
    assert "money truth and its record diverged" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 5 — the frozen port's own refusal removed
# --------------------------------------------------------------------------


def test_a_RELEASE_that_does_not_RAISE_on_a_double_release_fails(home: Path) -> None:
    """The seam declares `release` 'Raises on unknown id and on double release'.
    A ledger that returns instead has broken the frozen port's contract."""
    _plant(
        home,
        "        prior = self._terminal.get(reservation_id)\n"
        "        if prior is not None:\n"
        "            raise DoubleRelease(",
        "        prior = self._terminal.get(reservation_id)\n"
        "        if prior is not None:\n"
        "            return prior\n"
        "        if False:  # noqa\n"
        "            raise DoubleRelease(",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "RETURNED after that" in result.detail, result.detail
    assert "Raises on unknown id and on" in result.detail, result.detail


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent side is not agreement (§17, §5.3)
# --------------------------------------------------------------------------


def test_an_ABSENT_LEDGER_is_CANNOT_MEASURE_and_names_the_import_failure(
    home: Path,
) -> None:
    """A gate whose subject is gone measured nothing."""
    (home / gate.LEDGER).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import nixrisk.reservations" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_a_SPEC_WHOSE_SENTENCE_MOVED_is_CANNOT_MEASURE_not_a_silent_PASS(
    home: Path,
) -> None:
    """§5.3: an empty scope is never a PASS. The gate must say it lost its side."""
    spec = home / SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("released on:", "freed upon:"),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "no 'released on:' sentence" in result.detail, result.detail
    assert "an empty scope is never a PASS" in result.detail, result.detail


def test_a_SPEC_PATH_THE_SEAM_CANNOT_EXPRESS_is_CANNOT_MEASURE_not_a_SHRUNK_SET(
    home: Path,
) -> None:
    """The gate refuses to report over a path set it silently narrowed — the
    disagreement itself belongs to check_limiter_seam, not to this gate."""
    seam = home / SEAM
    seam.write_text(
        seam.read_text(encoding="utf-8").replace(
            '    BLACKOUT_ONSET = "blackout_onset"\n', ""
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "§3 names release path BLACKOUT_ONSET" in result.detail, result.detail
    assert "a set it silently shrank" in result.detail, result.detail


def test_a_SPEC_WITH_TOO_FEW_PATHS_is_CANNOT_MEASURE_against_a_FLOOR(
    home: Path,
) -> None:
    """MIN_TERMINAL_PATHS is a floor, not today's count."""
    spec = home / SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "released on: fill (converts to open-margin), cancel, reject,\n"
            "   pending-timeout resolution, blackout-onset cancellation.",
            "released on: fill (converts to open-margin), cancel.",
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "below the floor of 3" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_SAME_COPIED_TREE_passes_once_every_plant_is_gone(home: Path) -> None:
    """Without this the gate is only known to be able to fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "§3 release paths 5" in result.evidence, result.evidence


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    """The control proper: the same tree, red under the plant, green without it,
    with the ledger byte-identical before and after."""
    before = (home / gate.LEDGER).read_bytes()
    _plant(
        home,
        _REFUSE_ANCHOR,
        "            self._sigma -= prior.margin\n"
        "            return Resolution(released=prior)",
    )
    planted = _run(home)
    (home / gate.LEDGER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert "a SECOND terminal event" in planted.detail, planted.detail
    assert restored.status is Status.PASS, restored
    assert (home / gate.LEDGER).read_bytes() == before, "the control was not restored"


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    """The gate imports a package out of the tree under test. If it left the
    copy resident, the NEXT run in this process would measure the wrong tree —
    which is the whole reason a plant on a copy can be trusted at all."""
    real = sys.modules.get("nixrisk.reservations")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("nixrisk.reservations") is real, (
        "the gate left the tmp_path copy of nixrisk.reservations in sys.modules"
    )


def test_the_GATE_DECLARES_the_ledger_as_a_SUBJECT_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent."""
    assert gate.LEDGER in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the ledger is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"
