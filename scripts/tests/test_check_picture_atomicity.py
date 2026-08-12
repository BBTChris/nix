"""`checks/check_picture_atomicity.py` — the SHIPPED gate's bytes, driven to red.

Structure per `docs/nix_check_contract.md` §5.1: non-vacuity FIRST, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing. **Every control asserts the REASON** — the site, the named condition or
the field — never the exit code alone (check contract v2 §11).

THE BINDING MECHANISM, and why it does not touch the gate. `run()` reaches its
subject through one seam, `_import_subjects()`, and every construction inside the
gate goes through the namespace that seam returns (`picture_mod.X`). So a plant
is a `types.SimpleNamespace` carrying the REAL `nixrisk.picture` names with one
swapped for a subclass, and the gate's own bytes execute unmodified. The gate's
sha256 is asserted unchanged either side of the whole module, so a future edit
that turns one of these into a modified-gate red reddens here first.

Doctrine C.8: no plant touches a production artifact. Every socket lives under a
`tempfile.mkdtemp` the gate itself makes and removes; `scripts/nixrisk/picture.py`
and `scripts/nixbus/statebus.py` are never written.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,missing-function-docstring
# `invalid-name`: test names SHOUT the property under measurement, which is the
# house convention (`scripts/tests/test_statebus.py`) and is what makes a red
# line in the suite output readable without opening the file.
# `protected-access`: a can-fail control drives the gate's ARMS and helpers,
# which are private by design — a helper made public so a test could reach it
# would be a surface the gate did not need, invented for the test.
# `redefined-outer-name`: pytest fixtures are injected by name; that IS the API.
# `duplicate-code`: the sys.path bootstrap and the `--correct` refusal probe are
# MANDATED to be identical across suites (`nix_check_contract.md` §4.2).
# `missing-function-docstring`: a handful of one-line controls whose NAME is the
# whole statement; the rest carry docstrings.

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest  # pylint: disable=import-error
import zmq  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

# pylint: disable=wrong-import-position
import check_picture_atomicity as gate
from nixbus import statebus
from nixrisk import picture as pic
from nixverify.contract import Context, Mode, Status
from nixverify.declarations import read_declaration

GATE_FILE = REPO / "checks" / "check_picture_atomicity.py"
GATE_SHA = hashlib.sha256(GATE_FILE.read_bytes()).hexdigest()


def _subjects(**overrides: object) -> types.SimpleNamespace:
    """The real picture module with named parts swapped out. The plant mechanism."""
    parts = {
        name: getattr(pic, name)
        for name in (
            "FinancialPictureBook",
            "StateBusPictureSink",
            "PictureMirror",
            "PictureError",
            "TOPIC",
            "decode_picture",
            "encode_picture",
            "picture_defects",
        )
    }
    parts.update(overrides)
    return types.SimpleNamespace(**parts)


def _run(monkeypatch: pytest.MonkeyPatch, subjects: object):
    """Drive the SHIPPED gate with a planted (or real) picture module."""
    monkeypatch.setattr(gate, "_import_subjects", lambda: (subjects, statebus, ""))
    return gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))


# ---------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate really raced, and its detector really has power
# ---------------------------------------------------------------------------


def test_the_gate_PASSES_and_its_evidence_reports_a_REAL_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step 1 and step 6 of §5.1 — the control for every plant below."""
    result = _run(monkeypatch, _subjects())
    assert result.status is Status.PASS, (result.status, result.detail)
    assert "measured:" in result.evidence, result.evidence
    assert "distinct version(s)" in result.evidence, result.evidence
    assert "wire byte(s)" in result.evidence, result.evidence


def test_BOTH_PLANTS_actually_TORE_which_is_what_gives_the_arm_power(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§0a: a concurrency test that never observes the failing case is a sleep.

    The number is parsed back out of the evidence rather than trusted as a word.
    """
    result = _run(monkeypatch, _subjects())
    assert "PLANT two-read consumer" in result.evidence, result.evidence
    assert "PLANT two-attribute book" in result.evidence, result.evidence
    rate = result.evidence.split("the weaker of the two plants tore at ")[1]
    assert float(rate.split("%")[0]) > 0.0, result.evidence
    assert "TORN READ at version" in result.evidence, result.evidence


def test_the_detector_names_BOTH_generations_not_merely_that_it_disagreed() -> None:
    """Doctrine C.2: the value of the instrument is naming WHICH member diverged."""
    seam = sys.modules["nixrisk.seam"]
    balance, rows = gate._world(seam, 5)
    _, fresh = gate._world(seam, 6)
    torn = seam.FinancialPicture(
        version=1,
        published_ts=0.0,
        balance=balance,
        positions=fresh,
        margin_per_contract={},
        sum_open_margin=sum(row.margin for row in fresh),
        sum_reservations=0.0,
        committed=0.0,
        deployable=0.0,
    )
    defect = gate._generation_defect(torn)
    assert "generation 5" in defect and "generation 6" in defect, defect
    assert (
        gate._generation_defect(
            seam.FinancialPicture(
                version=1,
                published_ts=0.0,
                balance=balance,
                positions=rows,
                margin_per_contract={},
                sum_open_margin=sum(row.margin for row in rows),
                sum_reservations=0.0,
                committed=0.0,
                deployable=0.0,
            )
        )
        == ""
    ), "the CONTROL: one generation is not a tear"


# ---------------------------------------------------------------------------
# THE PLANTS
# ---------------------------------------------------------------------------


class _TwoCommitBook(pic.FinancialPictureBook):
    """THE PUBLISHER PLANT: balance and the table advance as TWO versions.

    Exactly §3's forbidden shape — *"never two separate reads"* — reached from
    the other side. A reader landing between the two commits holds a snapshot
    whose balance is generation k+1 and whose table is still k.
    """

    def commit(self, **changes: object):  # type: ignore[override]
        balance = changes.pop("balance", None)
        positions = changes.pop("positions", None)
        if balance is not None:
            super().commit(balance=balance, **changes)  # type: ignore[arg-type]
        time.sleep(0)
        if positions is not None:
            super().commit(positions=positions)  # type: ignore[arg-type]
        return self.current()


class _AtomicStandIn:
    """A stand-in for the gate's OWN publisher plant that never tears.

    Planting this is how the detector-power arm is shown to be load-bearing: if
    the gate accepted a plant that produced no tears, its measured arm's clean
    sheet would be about a harness with no power.
    """

    def __init__(self, seam: object) -> None:
        self._book = pic.FinancialPictureBook(
            balance=gate._BASE, deployable_fraction=gate._FRACTION
        )
        del seam

    def commit(self, **changes: object):
        """Atomic, deliberately — the plant that fails to plant."""
        return self._book.commit(**changes)  # type: ignore[arg-type]

    def current(self):
        """One attribute load, exactly like the subject."""
        return self._book.current()


class _AlwaysTradableMirror(pic.PictureMirror):
    """THE MIRROR PLANT: §12.7's fast-drop rule, deleted."""

    def tradable(self) -> tuple[bool, str]:
        """Always permits — including on an empty mirror."""
        return True, "planted: this mirror never refuses"


def test_a_TWO_COMMIT_publisher_reddens_the_MEASURED_arm_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subject broken in the exact way §3 forbids, judged by the shipped gate."""
    result = _run(monkeypatch, _subjects(FinancialPictureBook=_TwoCommitBook))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "picture.py:FinancialPictureBook.commit" in result.site, result.site
    assert "TORN READ at version" in result.detail, result.detail
    assert "never two separate reads" in result.detail, result.detail


def test_a_PLANT_THAT_DOES_NOT_TEAR_reddens_the_DETECTOR_POWER_arm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the harness cannot show the failing case it must not report success."""
    monkeypatch.setattr(gate, "_TwoAttributeBook", _AtomicStandIn)
    result = _run(monkeypatch, _subjects())
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "PLANT two-attribute book" in result.site, result.site
    assert "the detector was never shown the failing case" in result.detail
    assert "harness with no power" in result.detail, result.detail


def test_a_MIRROR_THAT_NEVER_REFUSES_reddens_and_names_tradable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§12.7: mirror incomplete ⇒ stale ⇒ fast-drop/deny until the snapshot lands."""
    result = _run(monkeypatch, _subjects(PictureMirror=_AlwaysTradableMirror))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "picture.py:PictureMirror.tradable" in result.site, result.site
    assert "never sized on" in result.detail, result.detail


def test_a_TORN_ENCODER_reddens_the_WIRE_arm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tear moved onto the wire: a body whose balance is frozen at generation 1.

    THE PLANT SURFACE IS THE SINK, NOT `encode_picture`, and that was found by
    measurement: the first spelling swapped `encode_picture` in the namespace the
    gate holds, and the arm stayed green — `StateBusPictureSink.emit` calls the
    function through its OWN module's globals, so a namespace override never
    reaches it. What is plantable is what the gate constructs, which is the sink.
    """

    class _StaleBalanceSink(pic.StateBusPictureSink):
        """Emits a snapshot whose balance is generation 1 and whose table is not."""

        def emit(self, picture) -> None:
            """§3's tear, moved onto the wire."""
            super().emit(dataclasses.replace(picture, balance=gate._BASE + 1))

    result = _run(monkeypatch, _subjects(StateBusPictureSink=_StaleBalanceSink))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "encode_picture/decode_picture" in result.site, result.site
    assert "torn snapshot on the wire" in result.detail, result.detail


def test_an_UNDECODABLE_wire_is_CANNOT_MEASURE_and_never_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§5.3: a subscriber that decoded nothing has not shown the wire is well."""

    def _refuse(_payload):
        raise pic.PictureError("planted: this consumer understands nothing")

    result = _run(monkeypatch, _subjects(decode_picture=_refuse))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "deliberately never PASS" in result.detail, result.detail


def test_a_SILENT_SINK_reddens_the_SNAPSHOT_ON_SUBSCRIBE_arm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§12.7: snapshot-on-subscribe is mandatory, not polish."""

    class _NeverServes(pic.StateBusPictureSink):
        """The plant: subscriptions are never answered."""

        def service(self, timeout_ms: int = 0) -> int:
            """Answers nothing, exactly as a `zmq.PUB` publisher cannot."""
            del timeout_ms
            return 0

    # The ceiling, not the property, is shortened: the planted failure is
    # PERMANENT rather than slow, so waiting the full 10 s twice would add
    # twenty seconds of certainty to a wait already 300x the healthy arrival.
    monkeypatch.setattr(gate, "RENDEZVOUS_CEILING_MS", 400)
    result = _run(monkeypatch, _subjects(StateBusPictureSink=_NeverServes))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "picture.py:StateBusPictureSink.service" in result.site, result.site
    assert "went UNSERVED" in result.detail, result.detail
    assert "mandatory, not polish" in result.detail, result.detail


def test_the_LATE_SUBSCRIBER_arm_has_POWER_measured_by_clearing_XPUB_VERBOSE(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The arm's own can-fail control, driven through the gate's driver.

    §12.7's snapshot-on-subscribe rests on `XPUB_VERBOSE`: without it libzmq
    delivers only the FIRST subscribe for a topic, so a second dashboard mirrors
    an empty table forever, which looks exactly like a quiet feed. The plant is a
    single `setsockopt` on THIS TEST'S OWN publisher subclass — doctrine C.8:
    `scripts/nixbus/statebus.py` still sets the option unconditionally for every
    publisher anyone else builds.

    The SEQUENTIAL staging is what gives this teeth (CHECK-DEBT D3.39's second
    finding): with both subscribers connected back-to-back, PUB/SUB fans the one
    snapshot out to every already-connected peer and the arm cannot fail at all.
    MEASURED here: shipped, both mirror generation 7 on 630 wire bytes each;
    planted, the second takes ZERO bytes and never mirrors.
    """

    class _NoVerbose(statebus.StatePublisher):
        """The plant: every subscribe after the first for a topic is swallowed."""

        def __init__(self, endpoint: str, **kwargs: object) -> None:
            super().__init__(endpoint, **kwargs)  # type: ignore[arg-type]
            self._socket.setsockopt(zmq.XPUB_VERBOSE, 0)

    monkeypatch.setattr(gate, "RENDEZVOUS_CEILING_MS", 1_500)
    seam = sys.modules["nixrisk.seam"]

    def _drive(publisher_class: object) -> dict:
        bus = types.SimpleNamespace(
            endpoint_for=statebus.endpoint_for,
            StatePublisher=publisher_class,
            StateSubscriber=statebus.StateSubscriber,
            Mirror=statebus.Mirror,
        )
        return gate._late_subscribers(pic, bus, seam, tmp_path)

    shipped = _drive(statebus.StatePublisher)
    assert shipped["first"]["ok"] and shipped["second"]["ok"], shipped
    assert shipped["generations"] == [7.0, 7.0], shipped["generations"]

    planted = _drive(_NoVerbose)
    assert planted["first"]["ok"], "the plant must not break the FIRST subscriber"
    assert not planted["second"]["ok"], planted["second"]
    assert planted["second"]["missing"] == [pic.TOPIC], planted["second"]
    assert planted["bytes"][1] == 0, "zero wire bytes is the quiet-feed signature"


def test_a_race_that_NEVER_RACED_is_CANNOT_MEASURE_and_names_the_shortfall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§0a's first answer: an atomicity verdict over a quiescent object is nothing."""
    monkeypatch.setattr(gate, "RACE_CEILING_S", 0.2)
    monkeypatch.setattr(gate, "MIN_READS", 10**9)
    result = _run(monkeypatch, _subjects())
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "did not demonstrably race the writer" in result.detail, result.detail
    assert "deliberately never PASS" in result.detail, result.detail


def test_UNPLANTING_restores_PASS_on_the_same_population(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§5.1 step 6 — the control that attributes every red above to its plant."""
    assert _run(monkeypatch, _subjects(FinancialPictureBook=_TwoCommitBook)).status is (
        Status.FAIL_NEEDS_OPERATOR
    )
    assert _run(monkeypatch, _subjects()).status is Status.PASS


def test_the_gate_was_never_MODIFIED_by_any_control_above() -> None:
    """Binding requires the SHIPPED bytes. This is that requirement, measured."""
    assert hashlib.sha256(GATE_FILE.read_bytes()).hexdigest() == GATE_SHA


# ---------------------------------------------------------------------------
# Declarations and actuation
# ---------------------------------------------------------------------------


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_venv",), declaration.depends_on
    assert declaration.resources == ("file-write:/tmp", "zmq-ipc"), (
        declaration.resources
    )
    assert declaration.subjects == ("scripts/nixrisk/picture.py",), declaration.subjects


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "rewriting the code under measurement" in combined, combined


def test_an_unimportable_subject_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctrine B.2: a gate that could not reach its subject measured nothing."""
    monkeypatch.setattr(
        gate, "_import_subjects", lambda: (None, None, "planted: no picture module")
    )
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "planted: no picture module" in result.detail, result.detail
