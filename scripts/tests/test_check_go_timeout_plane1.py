"""ARC 042 / D3.425 — the can-fail binding for `check_go_timeout`'s Plane-1 arms.

The arms were bound by OBSERVATION first: two plants were installed in
`scripts/limiterd.py` on a real tree, the gate was driven against a real
`limiterd` process each time, and it returned exit 1 naming the site. This file
makes that binding DURABLE — check contract v2 rule 9 makes a retrofitted check a
new check whose can-fail binding must be re-established, and a binding that lives
only in an arc's transcript is a binding that is gone next arc.

Both plants are re-driven here against the SHIPPED gate functions, which is the
part that matters: `_arm_firing_is_booked` and `_judge_plane1` are imported from
`checks/check_go_timeout.py`, never re-implemented.

NON-VACUITY (rule 4): every plant is paired with the unplanted control in the
same test, so a matcher that fired on everything — or on nothing — fails here.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring,protected-access
# pylint: disable=use-implicit-booleaness-not-comparison
# `== []` is DELIBERATE and stronger than `not x`: the arms return a list of
# Findings, and `not x` would also pass for `None` — which is what a broken
# arm returns when it forgets to return at all. The control assertions are the
# whole non-vacuity argument here, so they assert the exact value.
# House convention: test names SHOUT the property, in the case the contract
# uses. `_arm_firing_is_booked` and `_judge_plane1` are private to the gate and
# are DRIVEN here on purpose — they ARE the subject, and a public accessor would
# be API invented for a test to use. Same disables as the sibling suites.
import sys
import tempfile
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
CHECKS = REPO / "checks"
for _path in (str(SCRIPTS), str(CHECKS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position
import check_go_timeout as GATE  # pylint: disable=import-error
from nixrisk.seam import EventKind, EventRow  # pylint: disable=import-error
from nixrisk.wal import Plane1Wal  # pylint: disable=import-error

#: The REAL tree. The static arm's control reads the shipped `limiterd.py`.
HOME = REPO


def _tree(tmp_path: Path, limiterd_source: str) -> Path:
    """A minimal home whose only content is the module the static arm reads."""
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "limiterd.py").write_text(limiterd_source)
    return tmp_path


# ---------------------------------------------------------------------------
# ARM 3 — the STATIC fire path
# ---------------------------------------------------------------------------
_BOOKING = """
class Booker:
    def book_new_firings(self):
        for row in self._loop.go_timeouts():
            self._wal.enqueue(self._row_for(row))

    def _row_for(self, firing):
        return EventRow(kind=EventKind.GO_TIMEOUT, ts=0.0, strategy_id="s", reason="r")
"""

_NO_BOOKING = """
class Booker:
    def book_new_firings(self):
        for row in self._loop.go_timeouts():
            pass

    def _row_for(self, firing):
        return EventRow(kind=EventKind.GO_TIMEOUT, ts=0.0, strategy_id="s", reason="r")
"""

_STATUS_ONLY = """
class Handler:
    def _dispatch(self):
        return f"go timeouts {len(self._loop.go_timeouts())}"
"""


def test_the_STATIC_arm_PASSES_the_real_shipped_limiterd() -> None:
    """The control. Without this, every plant below could be a matcher that
    fires on anything, and "the plant reddened it" would say nothing."""
    assert GATE._arm_firing_is_booked(HOME) == []


def test_PLANT_A_the_booking_call_removed_is_a_FINDING() -> None:
    """ARC 040's exact state: the fire path reads the ledger and enqueues nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        clean = GATE._arm_firing_is_booked(_tree(Path(tmp) / "a", _BOOKING))
        planted = GATE._arm_firing_is_booked(_tree(Path(tmp) / "b", _NO_BOOKING))
    assert clean == [], (
        "the unplanted control must be clean or the plant proves nothing"
    )
    assert len(planted) == 1
    assert "book_new_firings()" in planted[0].why
    assert "D3.425" in planted[0].why
    assert "durable local WAL" in planted[0].why


def test_the_STATIC_arm_REFUSES_a_status_verb_as_a_booking() -> None:
    """A function that reads the ledger only to REPORT it is not a booking.

    Measured on ARC 042's own PLANT A run: `CommandHandler._dispatch` reads
    `go_timeouts()` for the status sentence, and an arm that accepted the first
    ledger reader it found would have been satisfied by it forever.
    """
    with tempfile.TemporaryDirectory() as tmp:
        found = GATE._arm_firing_is_booked(_tree(Path(tmp), _STATUS_ONLY))
    assert len(found) == 1
    assert "_dispatch()" in found[0].why


def test_the_STATIC_arm_SURVIVES_a_rename_of_every_nix_identifier() -> None:
    """D3.426: shape, not spelling. Renaming the booker must not red the gate."""
    renamed = (
        _BOOKING.replace("Booker", "Zqx")
        .replace("book_new_firings", "wibble")
        .replace("_row_for", "_thing")
        .replace("self._wal", "self._sink")
    )
    with tempfile.TemporaryDirectory() as tmp:
        assert GATE._arm_firing_is_booked(_tree(Path(tmp), renamed)) == []


# ---------------------------------------------------------------------------
# ARM 4 — the LIVE Plane-1 row, judged off a real WAL
# ---------------------------------------------------------------------------
FIRING = {
    "strategy_id": "s1",
    "client_order_id": "cid-lost",
    "fired_tick": 103,
    "elapsed_s": 2.0,
    "timeout_s": 2.0,
    "released": True,
    "resent": False,
}


def _wal_with(path: Path, count: int) -> None:
    wal = Plane1Wal(path)
    try:
        for _ in range(count):
            wal.enqueue(
                EventRow(
                    kind=EventKind.GO_TIMEOUT,
                    ts=50.0,
                    strategy_id="s1",
                    reason="scripts/nixrisk/loop.py: §4:210-212 GO-timeout FIRED",
                    trade_id=None,
                    fields={
                        "client_order_id": "cid-lost",
                        "fired_tick": "103",
                        "resent": "false",
                    },
                )
            )
        wal.sync_to_disk()
    finally:
        wal.close()


def _record(root: Path, *, booked: int, durable: int) -> dict:
    return {
        "boot_ts": 0.0,
        "stopped_ts": 100.0,
        "plane1": {
            "wal_path": str(root / "plane1.wal"),
            "booked": booked,
            "refused": 0,
            "wal_enqueued": booked,
            "wal_durable": durable,
        },
    }


def test_the_LIVE_arm_PASSES_one_firing_one_row(tmp_path: Path) -> None:
    """The control for both plants below."""
    _wal_with(tmp_path / "plane1.wal", 1)
    assert (
        GATE._judge_plane1(tmp_path, _record(tmp_path, booked=1, durable=1), [FIRING])
        == []
    )


def test_PLANT_A_a_firing_with_NO_row_is_the_D3_425_FINDING(tmp_path: Path) -> None:
    """The runtime record has the firing and §9's log does not."""
    _wal_with(tmp_path / "plane1.wal", 0)
    found = GATE._judge_plane1(
        tmp_path, _record(tmp_path, booked=1, durable=0), [FIRING]
    )
    assert len(found) == 1
    assert "D3.425" in found[0].why
    assert "holds NO `go_timeout` row" in found[0].why
    assert "the claim and the artefact disagreeing" in found[0].why


def test_PLANT_B_a_duplicate_booking_REPORTS_N_rows(tmp_path: Path) -> None:
    """§4:240-241: one firing is one row, and the finding must say how many."""
    _wal_with(tmp_path / "plane1.wal", 7)
    found = GATE._judge_plane1(
        tmp_path, _record(tmp_path, booked=7, durable=7), [FIRING]
    )
    assert any("produced 7 `go_timeout` row(s)" in f.why for f in found)
    assert any("§4:240-241" in f.why for f in found)


def test_a_missing_plane1_block_is_a_FINDING(tmp_path: Path) -> None:
    """A process that cannot say whether it booked is unfalsifiable from outside."""
    found = GATE._judge_plane1(tmp_path, {"boot_ts": 0.0, "stopped_ts": 1.0}, [FIRING])
    assert len(found) == 1
    assert "no `plane1` block" in found[0].why


def test_NON_VACUITY_no_firing_is_CANNOT_MEASURE_never_a_pass(tmp_path: Path) -> None:
    """§17 / rule 10. With no firing, zero rows is true for free."""
    _wal_with(tmp_path / "plane1.wal", 0)
    with pytest.raises(GATE.Cannot):
        GATE._judge_plane1(tmp_path, _record(tmp_path, booked=0, durable=0), [])


def test_a_WAL_OUTSIDE_the_drive_is_CANNOT_MEASURE_not_evidence(tmp_path: Path) -> None:
    """A file this run did not write says nothing about this run's firing."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    _wal_with(other / "plane1.wal", 1)
    record = _record(other, booked=1, durable=1)
    with pytest.raises(GATE.Cannot):
        GATE._judge_plane1(tmp_path / "drive", record, [FIRING])


def test_a_row_from_ANOTHER_firing_is_a_FINDING(tmp_path: Path) -> None:
    """The row must be THIS firing's, not a leftover with the right event type."""
    _wal_with(tmp_path / "plane1.wal", 1)
    other = dict(FIRING, client_order_id="cid-someone-else")
    found = GATE._judge_plane1(
        tmp_path, _record(tmp_path, booked=1, durable=1), [other]
    )
    assert any("client_order_id" in f.why for f in found)
