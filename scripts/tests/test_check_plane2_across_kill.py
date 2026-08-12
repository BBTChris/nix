"""ARC 027 C3 — the standing gate over Plane-2 durability across a process death.

Same split as `test_check_feed_kill_drill.py`: one end-to-end run of the SHIPPED
gate against a real SIGKILL and a real journal, then per-arm can-fails over a
crafted drill result. The plant is the evidence record; no production artifact is
touched (doctrine C.8).

**Every control asserts the REASON** — the named condition in the verdict's own
detail — never the exit code alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access,duplicate-code
# pylint: disable=use-implicit-booleaness-not-comparison
# `errors == ()` asserts the TYPE and the emptiness together, the same
# convention `scripts/tests/test_declarations.py` adopts: `not x` is also
# satisfied by `None`, so a reader that started returning None would pass a
# truthiness assertion while having measured nothing.

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_plane2_across_kill as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)
from nixverify.plane2 import (  # pylint: disable=wrong-import-position
    JOURNAL_SOCKET,
    JOURNALCTL,
)

GATE_FILE = REPO / "checks" / "check_plane2_across_kill.py"

FAILING = (Status.FAIL_NEEDS_OPERATOR, Status.FAIL_REPAIRABLE)


def _ctx() -> Context:
    return Context(nix_home=REPO, mode=Mode.VERIFY)


def _passing() -> dict[str, Any]:
    """A drill result the gate accepts: one killed arm, one clean-exit control."""
    return {
        "trials": [{"trial": 0, "pid": 51000, "arm_nonce": "abct0"}],
        "clean_exit": {"pid": 51001, "arm_nonce": "abck", "reap_status": 0},
        "plane2": {
            "error": "",
            "lifecycle_readback_error": "",
            "arms": {
                "abct0": {
                    "pid": 51000,
                    "killed": True,
                    "bus_compared": True,
                    "bus_max_seq": 45,
                    "journal_max_seq": 45,
                    "journal_seq_count": 45,
                    "lost_below_bus_max": [],
                    "beyond_bus_max": [],
                    "process_start_in_journal": True,
                    "process_stop_in_journal": False,
                },
                "abck": {
                    "pid": 51001,
                    "killed": False,
                    "bus_compared": False,
                    "bus_max_seq": 0,
                    "journal_max_seq": 40,
                    "journal_seq_count": 40,
                    "lost_below_bus_max": [],
                    "beyond_bus_max": [],
                    "process_start_in_journal": True,
                    "process_stop_in_journal": True,
                },
            },
        },
    }


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch):
    """Install a crafted drill result and run the SHIPPED gate over it."""

    def _run(mutate) -> Any:
        result = _passing()
        mutate(result)
        monkeypatch.setattr(gate, "_drive", lambda drill: copy.deepcopy(result))
        monkeypatch.setattr(gate, "_precondition", lambda: None)
        return gate.run(Mode.VERIFY, _ctx())

    return _run


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_unbroken_result_passes_and_names_the_loss(planted) -> None:
    """The fixture must pass, or every red below is the fixture's."""
    result = planted(lambda _: None)
    assert result.status is Status.PASS, result.detail
    assert "NO LOSS" in result.evidence
    assert "LOSS NAMED" in result.evidence
    assert "cannot distinguish this death from a hang" in result.evidence
    assert "NOT bounded here" in result.evidence, (
        "the verdict must state what it could not bound, not only what it proved"
    )


# --------------------------------------------------------------------------
# THE REAL THING
# --------------------------------------------------------------------------


def test_the_shipped_gate_kills_a_REAL_emitter_and_reads_the_REAL_journal() -> None:
    """The one test that proves the method executes end to end."""
    if not Path(JOURNAL_SOCKET).exists() or not Path(JOURNALCTL).exists():
        pytest.skip("no journal ingress on this node")
    if not (REPO / ".venv" / "bin" / "python3").is_file():
        pytest.skip("no venv interpreter")
    result = gate.run(Mode.VERIFY, _ctx())
    if result.status is Status.CANNOT_MEASURE:
        pytest.skip(f"the drill could not run here: {result.detail}")
    assert result.status is Status.PASS, result.detail
    assert "the journal holds all" in result.evidence
    assert "emitted NO process_stop" in result.evidence


# --------------------------------------------------------------------------
# PER-ARM CAN-FAILS
# --------------------------------------------------------------------------


def test_a_record_the_bus_saw_and_the_journal_lacks_FAILS_arm_1(planted) -> None:
    """The durability claim itself: a seq on the bus and not in the journal."""
    result = planted(
        lambda r: r["plane2"]["arms"]["abct0"].__setitem__(
            "lost_below_bus_max", [17, 18, 19]
        )
    )
    assert result.status in FAILING, result.detail
    assert "never reached the journal" in result.detail
    assert "pid=51000" in result.detail
    assert "journal" in result.site


def test_a_stream_with_no_process_start_FAILS_arm_2(planted) -> None:
    """Heartbeats cannot be attributed to a life this gate never saw begin."""
    result = planted(
        lambda r: r["plane2"]["arms"]["abct0"].__setitem__(
            "process_start_in_journal", False
        )
    )
    assert result.status in FAILING, result.detail
    assert "no process_start event for pid=51000" in result.detail


def test_a_process_stop_after_SIGKILL_FAILS_arm_3(planted) -> None:
    """SIGKILL runs no code. An event claiming otherwise came from somewhere else."""
    result = planted(
        lambda r: r["plane2"]["arms"]["abct0"].__setitem__(
            "process_stop_in_journal", True
        )
    )
    assert result.status in FAILING, result.detail
    assert "SIGKILL runs no code" in result.detail
    assert "CaptureProcess.close" in result.site


def test_an_emitter_that_never_says_goodbye_is_CANNOT_MEASURE(planted) -> None:
    """§7.12 answer 4 — the arm that makes the loss claim falsifiable at all.

    If the CLEAN-EXIT control also lacks `process_stop`, the killed arm's missing
    `process_stop` is a property of the emitter, not a consequence of the kill,
    and the gate must refuse rather than report a finding it did not earn.
    """
    result = planted(
        lambda r: r["plane2"]["arms"]["abck"].__setitem__(
            "process_stop_in_journal", False
        )
    )
    assert result.status is Status.CANNOT_MEASURE
    assert "never says goodbye" in result.detail


def test_a_producer_that_barely_lived_is_CANNOT_MEASURE(planted) -> None:
    """'Nothing was lost' over three records is a statement about an empty set."""
    result = planted(
        lambda r: r["plane2"]["arms"]["abct0"].__setitem__("bus_max_seq", 3)
    )
    assert result.status is Status.CANNOT_MEASURE
    assert "statement about an empty set" in result.detail


def test_an_unreadable_journal_is_CANNOT_MEASURE_never_a_pass(planted) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = planted(
        lambda r: r["plane2"].__setitem__("error", "journalctl exit 1: nope")
    )
    assert result.status is Status.CANNOT_MEASURE
    assert "journal unreadable" in result.detail


def test_a_missing_journal_socket_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The precondition, driven for real rather than patched away."""
    monkeypatch.setattr(gate, "JOURNAL_SOCKET", "/nonexistent/dev/log")
    result = gate.run(Mode.VERIFY, _ctx())
    assert result.status is Status.CANNOT_MEASURE
    assert "no syslog socket" in result.detail


# --------------------------------------------------------------------------
# DECLARATIONS
# --------------------------------------------------------------------------


def test_the_gate_declares_what_the_plan_needs() -> None:
    """The journal claim is the one `check_capture_plane2` also makes."""
    declaration = read_declaration(GATE_FILE)
    assert declaration.errors == ()
    assert declaration.depends_on == ("check_venv",)
    assert "journal" in declaration.resources
    assert set(declaration.resources) == {
        "journal",
        "subprocess:python3",
        "subprocess:python",
        "file-write:/tmp",
        "zmq-ipc",
        "shm",
        "cpu-affinity",
    }
    assert declaration.on_fail == "continue"
    assert "scripts/nixverify/plane2.py" in declaration.subjects
