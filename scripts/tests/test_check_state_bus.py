"""ARC 026 C2/C4 — the standing gate over §12.7's state-table transport.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing.

**No plant touches a production artifact** (doctrine C.8). Every plant is a shim
namespace handed to the gate through its own `_import_statebus` seam — the real
`scripts/nixbus/statebus.py` is never edited, and every socket the gate opens
lives under a `tempfile` directory it removes itself.

**Every control asserts the REASON** — the site, the named condition, or the
field — never the exit code alone (check contract v2 §11).

THE DEFECT THIS FILE EXISTS FOR is the one the arc brief named: *a transport gate
that passes because nothing was ever published*. `test_a_transport_that_carried_
ZERO_BYTES_is_CANNOT_MEASURE_not_PASS` is that defect planted and caught.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access
# `protected-access`: a can-fail control drives the gate's ARMS, which are
# private by design — an arm made public so a test could reach it would be a
# surface the gate did not need, invented for the test. Doctrine C.8 says the
# plant must not touch the production artifact; it does not say the test may
# only use the public API.
# pylint: disable=duplicate-code,too-few-public-methods
# Test names SHOUT the property; shim classes are deliberately tiny; the
# sys.path bootstrap forces late imports. Each deliberate, so the pragma is named.

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_state_bus as gate  # pylint: disable=wrong-import-position
from nixbus import statebus  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_state_bus.py"


def _bus(**overrides: object) -> types.SimpleNamespace:
    """The real statebus with named parts swapped out. The plant mechanism."""
    parts = {
        "endpoint_for": statebus.endpoint_for,
        "StatePublisher": statebus.StatePublisher,
        "StateSubscriber": statebus.StateSubscriber,
        "Mirror": statebus.Mirror,
    }
    parts.update(overrides)
    return types.SimpleNamespace(**parts)


def _run(monkeypatch: pytest.MonkeyPatch, bus: object):
    """Drive the gate with a planted (or real) statebus."""
    monkeypatch.setattr(gate, "_import_statebus", lambda: (bus, ""))
    return gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — real bytes crossed a real ipc socket.
# --------------------------------------------------------------------------


def test_the_REAL_bus_PASSES_and_the_evidence_names_the_BYTES_it_carried() -> None:
    """A gate that reports on a transport must be able to say what it carried."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail
    assert "bytes of real traffic" in result.evidence, result.evidence
    assert "ipc endpoint materialised: ipc://" in result.evidence, result.evidence
    assert "late subscriber got snapshot" in result.evidence, result.evidence


def test_the_carried_byte_COUNT_is_greater_than_zero() -> None:
    """Non-vacuity as a number, not as a word."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    carried = int(result.evidence.split("transport carried ")[1].split(" bytes")[0])
    assert carried > 0, result.evidence


# --------------------------------------------------------------------------
# PLANT 1 — THE NAMED DEFECT. Nothing was ever published.
# --------------------------------------------------------------------------


class _SilentSubscriber(statebus.StateSubscriber):
    """A subscriber that receives nothing, ever. The named vacuous-pass shape."""

    def drain(self, timeout_ms: int) -> list:
        """Receive nothing and report nothing. `bytes_received` stays 0."""
        return []


def test_a_transport_that_carried_ZERO_BYTES_is_CANNOT_MEASURE_not_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The arc brief's named defect, planted and caught before any arm runs."""
    result = _run(monkeypatch, _bus(StateSubscriber=_SilentSubscriber))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "ZERO bytes" in result.detail, result.detail
    assert "never PASS" in result.detail, result.detail


def test_UNPLANTING_the_silent_subscriber_restores_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plant removed, the same gate passes. Step three of §5.1."""
    assert _run(monkeypatch, _bus(StateSubscriber=_SilentSubscriber)).status is (
        Status.CANNOT_MEASURE
    )
    assert _run(monkeypatch, _bus()).status is Status.PASS


# --------------------------------------------------------------------------
# PLANT 2 — snapshot-on-subscribe removed. §12.7 calls it mandatory.
# --------------------------------------------------------------------------


class _NoSnapshotPublisher(statebus.StatePublisher):
    """A publisher that never answers a subscription. Plain PUB/SUB, unfixed."""

    def service(self, timeout_ms: int = 0) -> int:
        """Ignore every pending subscription."""
        return 0


def test_a_publisher_that_NEVER_SNAPSHOTS_fails_and_NAMES_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late subscriber then gets nothing, which is exactly the slow-joiner loss."""
    result = _run(monkeypatch, _bus(StatePublisher=_NoSnapshotPublisher))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "statebus.py:StatePublisher.service" in result.site, result.site
    assert "snapshot-on-subscribe is mandatory" in result.detail, result.detail


def test_UNPLANTING_the_missing_snapshot_restores_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step three of §5.1 for plant 2."""
    assert _run(monkeypatch, _bus(StatePublisher=_NoSnapshotPublisher)).status is (
        Status.FAIL_NEEDS_OPERATOR
    )
    assert _run(monkeypatch, _bus()).status is Status.PASS


# --------------------------------------------------------------------------
# PLANT 3 — the CONTROL leaks, so arrival proves nothing.
# --------------------------------------------------------------------------


class _AlwaysDeliversSubscriber(statebus.StateSubscriber):
    """A subscriber that reports traffic it did not receive.

    This is the plant that attacks the gate's CONTROL rather than its measured
    arm: if a subscriber "receives" a table with snapshot-on-subscribe never run,
    then receiving one WITH the mechanism running is not evidence the mechanism
    works, and the measured arm's PASS is vacuous.
    """

    def drain(self, timeout_ms: int) -> list:
        """Real traffic, plus a fabricated message when there was none."""
        messages = super().drain(timeout_ms)
        if messages:
            return messages
        self.received += 1
        self.bytes_received += 32
        return [
            statebus.StateMessage(
                topic=gate.TOPIC,
                payload={"nonce": "fabricated"},
                seq=1,
                stamp=1.0,
                snapshot=True,
            )
        ]


def test_a_CONTROL_that_RECEIVES_ANYWAY_fails_and_says_the_pass_would_be_vacuous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate refuses to certify a mechanism its control cannot distinguish."""
    result = _run(monkeypatch, _bus(StateSubscriber=_AlwaysDeliversSubscriber))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "CONTROL (service() never called)" in result.site, result.site
    assert "would be vacuous" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 — a mirror that calls itself complete without a snapshot.
# --------------------------------------------------------------------------


class _NeverStaleMirror(statebus.Mirror):
    """§12.7's fast-drop condition, deleted."""

    @property
    def stale(self) -> bool:
        """Always ready. The exact thing that lets a half-built mirror be sized on."""
        return False


def test_a_mirror_that_is_NEVER_STALE_fails_and_NAMES_Mirror_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§12.7: mirror incomplete => treated as stale until the snapshot lands."""
    result = _run(monkeypatch, _bus(Mirror=_NeverStaleMirror))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "statebus.py:Mirror.complete" in result.site, result.site
    assert "treated as stale until a snapshot lands" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 5 — the freshness stamp stops riding the update.
# --------------------------------------------------------------------------


class _StamplessSubscriber(statebus.StateSubscriber):
    """Delivers real tables with the §12.7 freshness stamp stripped off."""

    def drain(self, timeout_ms: int) -> list:
        """Strip `_stamp` from every message the real transport delivered."""
        return [
            statebus.StateMessage(
                topic=message.topic,
                payload=message.payload,
                seq=message.seq,
                stamp=0.0,
                snapshot=message.snapshot,
            )
            for message in super().drain(timeout_ms)
        ]


def test_an_update_with_NO_FRESHNESS_STAMP_fails_and_NAMES_the_send_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§12.7: *freshness stamps ride each update*."""
    result = _run(monkeypatch, _bus(StateSubscriber=_StamplessSubscriber))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "statebus.py:StatePublisher._send" in result.site, result.site
    assert "freshness stamp on every update" in result.detail, result.detail


# --------------------------------------------------------------------------
# The gate refuses to look, loudly, rather than passing.
# --------------------------------------------------------------------------


def test_an_UNIMPORTABLE_subject_is_CANNOT_MEASURE_and_NAMES_the_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`verify.py` may run under an interpreter with no pyzmq. That is not a PASS."""
    monkeypatch.setattr(
        gate, "_import_statebus", lambda: (None, "cannot import nixbus.statebus: boom")
    )
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "cannot import nixbus.statebus" in result.detail, result.detail


def test_a_bus_that_RAISES_is_CANNOT_MEASURE_and_carries_the_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A driving failure is 'I could not look', never 'the bus is fine'."""

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("planted bind failure")

    result = _run(monkeypatch, _bus(StatePublisher=_explode))
    assert result.status is Status.CANNOT_MEASURE
    assert "planted bind failure" in result.detail, result.detail


# --------------------------------------------------------------------------
# The transport really is ipc://, and the declarations really are readable.
# --------------------------------------------------------------------------


def test_the_endpoint_the_gate_drives_is_IPC_and_materialises_on_disk() -> None:
    """§12.7's transport, observed as a kernel object rather than a library claim."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert "ipc endpoint materialised: ipc:///" in result.evidence, result.evidence


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_venv",)
    assert declaration.resources == ("file-write:/tmp", "zmq-ipc")
    assert declaration.subjects == ("scripts/nixbus/statebus.py",)


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "manufacturing the traffic it exists to measure" in combined, combined
