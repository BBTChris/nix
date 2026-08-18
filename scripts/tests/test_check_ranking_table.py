"""The §6.6 ranking-table gate must REDDEN on each defect it claims to see.

BOTH HALVES, everywhere. Every arm here breaks the SUBJECT, proves the gate
goes non-green *naming the reason*, then un-breaks it and proves the same code
goes green — a control that cannot demonstrate the defect is BLIND, not
passing, and a red raised for an unrelated reason is not a measurement either,
so every assertion names a substring of the reason and never only a status.

Doctrine C.8: no plant touches a production artefact. The one file-level plant
(a reader that computes) is a REAL COPY of the shipped module written under
`tmp_path`, and the gate is pointed at that home.

## §0a on this file: what would make it pass while measuring nothing?

1. **Every arm could be tested by calling a predicate that returns a constant.**
   Closed by driving the gate's own arm functions with measurement dicts that
   differ in exactly one field, and asserting the defect list changes.
2. **The end-to-end run could be asserted green without ever being asserted
   red.** Closed by `test_run_reddens_on_a_computing_reader`, which plants a
   computing `lookup` into a copied tree and requires the SHIPPED `run()` to go
   red naming the hot-path reason — and by the honest-tree half beside it.
3. **The module's own concurrency claim could be asserted rather than driven.**
   Closed by `test_view_does_not_tear_while_the_two_lookup_path_does`, which
   requires the tearable control to ACTUALLY TEAR in the same run; if it does
   not, the test fails as blind rather than passing.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Test names spell the OUTCOME. The sys.path bootstrap is repeated per module
# deliberately; one shared helper would let a single edit un-bind several.
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _extra in (str(REPO / "checks"), str(REPO / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_ranking_table as gate  # pylint: disable=import-error
from nixbus.statebus import StateMessage  # pylint: disable=import-error
from nixscore import publisher as pub  # pylint: disable=import-error
from nixscore import seam  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

FIRST = gate.FIRST
SECOND = gate.SECOND


def _rows(high_first: bool = True, generation: int = 7) -> dict:
    return {
        FIRST: seam.RankRow(
            FIRST[0], FIRST[1], 900.0 if high_first else 1.0, 1, generation
        ),
        SECOND: seam.RankRow(
            SECOND[0], SECOND[1], 100.0 if high_first else 9999.0, 2, generation
        ),
    }


def _snapshot(high_first: bool = True, identity: str | None = None):
    return seam.RankingSnapshot(
        rows=_rows(high_first),
        span_days=10,
        writer_identity=identity or seam.SCORING_WRITER_IDENTITY,
    )


def _verdict(outcome: str, winner=FIRST):
    return seam.Verdict(
        seam.Arbitration(outcome), winner, "synthetic verdict for a plant"
    )


def _reasons(defects: list[tuple[str, str]]) -> str:
    return " | ".join(f"{site}: {why}" for site, why in defects)


# ---------------------------------------------------------------------------
# THE MODULE ITSELF, over a real socket
# ---------------------------------------------------------------------------


@pytest.fixture()
def bus(tmp_path: Path):
    """A writer and a reader on one real `ipc://` endpoint under tmp_path."""
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    reader = pub.RankingReader(endpoint, stale_after_s=30.0)
    try:
        yield writer, reader
    finally:
        reader.close()
        writer.close()


def test_a_late_joiner_gets_the_table_and_a_cold_reader_gets_none(tmp_path: Path):
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    try:
        writer.publish_rows(_rows(), 10)
        reader = pub.RankingReader(endpoint, stale_after_s=30.0)
        try:
            # BEFORE: connected, and holding nothing. §12.7 — incomplete IS stale.
            assert reader.view() is None
            assert reader.stale is True
            cold = reader.arbitrate(FIRST, SECOND)
            assert str(cold.outcome) == "fcfs"
            assert "no ranking snapshot" in cold.reason
            # AFTER: the snapshot-on-subscribe lands and the same reader ranks.
            writer.service(1000)
            result = reader.pump(600)
            assert result.received >= 1, "the late joiner received nothing"
            assert result.accepted >= 1
            assert reader.view() is not None
            assert reader.stale is False
            hot = reader.arbitrate(FIRST, SECOND)
            assert str(hot.outcome) == "ranked"
            assert hot.winner == FIRST
        finally:
            reader.close()
    finally:
        writer.close()


def test_a_foreign_identity_is_refused_and_counted(bus):
    writer, reader = bus
    writer.publish_rows(_rows(), 10)
    writer.service(1000)
    reader.pump(600)
    accepted = reader.applied
    assert accepted >= 1, "nothing legitimate landed, so the refusal proves nothing"
    # A snapshot that WOULD flip the winner, stamped by anyone else.
    reader.ingest(
        StateMessage(
            seam.RANKING_TOPIC,
            _snapshot(high_first=False, identity="impostor").as_wire(),
            9_999,
            time.time(),
            True,
        )
    )
    assert reader.applied == accepted, "an impostor's table became the mirror"
    assert reader.foreign_rejected == 1, "the refusal was silent, not counted"
    assert reader.arbitrate(FIRST, SECOND).winner == FIRST


def test_off_topic_and_malformed_messages_are_counted_separately(bus):
    _writer, reader = bus
    reader.ingest(StateMessage("not-ranking", {}, 1, time.time(), True))
    assert reader.off_topic == 1
    reader.ingest(
        StateMessage(seam.RANKING_TOPIC, {"nonsense": 1}, 2, time.time(), True)
    )
    assert reader.malformed_rejected == 1
    assert reader.view() is None


def test_sequence_holes_are_counted_and_restarts_are_not_holes(bus):
    _writer, reader = bus
    for sequence in (1, 2, 5):
        reader.ingest(
            StateMessage(
                seam.RANKING_TOPIC, _snapshot().as_wire(), sequence, time.time(), True
            )
        )
    assert reader.gaps_detected == 1, "a two-message hole was not noticed"
    assert reader.messages_lost == 2
    # A publisher restart resets the sequence. That is a regression, not a hole,
    # and §12.7's restart rebuild requires the snapshot to land anyway.
    before = reader.applied
    reader.ingest(
        StateMessage(seam.RANKING_TOPIC, _snapshot().as_wire(), 1, time.time(), True)
    )
    assert reader.sequence_regressions == 1
    assert reader.gaps_detected == 1, "a restart was miscounted as a hole"
    assert reader.applied == before + 1, "a restarted publisher was locked out"


def test_the_publisher_does_not_block_on_a_reader_that_never_drains(tmp_path: Path):
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    reader = pub.RankingReader(endpoint, stale_after_s=600.0)
    try:
        writer.service(1000)
        rows = _rows()
        worst = 0.0
        for _ in range(gate.BURST_PUBLISHES):
            mark = time.perf_counter()
            writer.publish_rows(rows, 10)
            worst = max(worst, time.perf_counter() - mark)
        received = reader.pump(600).received
    finally:
        reader.close()
        writer.close()
    # NON-VACUITY: the burst must really have overrun the buffers, or "it did
    # not block" was never put to the test.
    assert writer.published - received > 0, (
        "the burst never exceeded the socket buffers"
    )
    assert worst <= gate.PUBLISH_BUDGET_S, f"a single publish took {worst:.4f}s"


def test_view_does_not_tear_while_the_two_lookup_path_does(tmp_path: Path):
    """The named trap: an overlap that never overlaps proves serialisation.

    The two-lookup path is the CONTROL and it must actually tear in this run.
    """
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    reader = pub.RankingReader(endpoint, stale_after_s=600.0)
    stop = threading.Event()
    counts = {"writes": 0}

    def _write() -> None:
        written = 0
        while not stop.is_set():
            written += 1
            payload = seam.RankingSnapshot(
                rows=_rows(generation=written), span_days=10
            ).as_wire()
            reader.ingest(
                StateMessage(seam.RANKING_TOPIC, payload, written, time.time(), True)
            )
        counts["writes"] = written

    thread = threading.Thread(target=_write, daemon=True)
    thread.start()
    try:
        observed = gate._read_loop(reader)  # pylint: disable=protected-access
    finally:
        stop.set()
        thread.join(timeout=5.0)
        reader.close()
        writer.close()
    assert counts["writes"] > 0 and observed["reads"] > 0
    assert observed["generations"] >= gate.MIN_OVERLAP_GENERATIONS, (
        "the reader never straddled a write — this is a serialisation test "
        "wearing a concurrency test's name"
    )
    assert observed["torn_naive"] > 0, (
        "the deliberately-tearable two-lookup path did not tear, so this run "
        "cannot see tearing and its verdict on the view path is blind"
    )
    assert observed["torn_view"] == 0, (
        f"{observed['torn_view']} reads out of ONE captured view returned rows "
        "from different published tables"
    )


# ---------------------------------------------------------------------------
# THE GATE'S ARMS — each broken one field at a time
# ---------------------------------------------------------------------------


def _live(nonce: str = "nonce", **overrides) -> dict:
    rows = dict(_rows())
    # The nonce rides a REAL row, exactly as the gate publishes it: the arm
    # looks it up inside the table, so a fixture without it is a fixture that
    # would redden the honest half.
    rows[(nonce, "NONCE")] = seam.RankRow(nonce, "NONCE", 0.0, 3, 0)
    view = pub.RankingView(
        rows=rows, span_days=10, seq=2, stamp=time.time(), captured_at=time.time()
    )
    base = {
        "endpoint": "ipc:///tmp/x/ranking.ipc",
        "socket_file_exists": True,
        "served": 1,
        "pump": pub.PumpResult(1, 1, 0, 0, 0, 508),
        "cold": {"view": None, "stale": True, "verdict": _verdict("fcfs")},
        "view": view,
        "verdict": _verdict("ranked"),
        "bytes": 508,
    }
    base.update(overrides)
    return base


def test_transport_arm_reddens_when_the_late_joiner_gets_nothing():
    defects: list[tuple[str, str]] = []
    gate._arm_transport(_live(), "nonce", defects, [])  # pylint: disable=protected-access
    assert not defects, "the honest half already reddened"

    defects = []
    gate._arm_transport(  # pylint: disable=protected-access
        _live(view=None), "nonce", defects, []
    )
    assert "snapshot-on-subscribe is mandatory" in _reasons(defects)


def test_transport_arm_reddens_when_the_payload_is_not_the_table_under_test():
    defects: list[tuple[str, str]] = []
    # The gate looks the nonce up INSIDE the table; a table without it is an
    # envelope that arrived carrying someone else's rows.
    gate._arm_transport(_live(), "MISSING", defects, [])  # pylint: disable=protected-access
    assert "carries no row for nonce" in _reasons(defects)


def test_control_arm_reddens_when_the_unserviced_run_still_gets_a_table():
    defects: list[tuple[str, str]] = []
    control = {"view": None, "pump": pub.PumpResult(0, 0, 0, 0, 0, 0)}
    gate._arm_control(control, defects, [])  # pylint: disable=protected-access
    assert not defects

    defects = []
    control["view"] = _live()["view"]
    gate._arm_control(control, defects, [])  # pylint: disable=protected-access
    assert "was not caused by the mechanism under test" in _reasons(defects)


def test_cold_arm_reddens_when_a_reader_with_no_snapshot_calls_itself_fresh():
    defects: list[tuple[str, str]] = []
    gate._arm_cold(_live(), defects, [])  # pylint: disable=protected-access
    assert not defects

    defects = []
    cold = {"view": None, "stale": False, "verdict": _verdict("fcfs")}
    gate._arm_cold(_live(cold=cold), defects, [])  # pylint: disable=protected-access
    assert "an incomplete mirror IS stale" in _reasons(defects)


def test_cold_arm_reddens_when_the_fed_reader_never_ranks():
    defects: list[tuple[str, str]] = []
    gate._arm_cold(  # pylint: disable=protected-access
        _live(verdict=_verdict("fcfs")), defects, []
    )
    assert "would pass a reader that says FCFS to everything" in _reasons(defects)


def _burst(**overrides) -> dict:
    base = {
        "worst": 0.0005,
        "total": 0.05,
        "published": 4000,
        "received": 2000,
        "bytes": 1_000_000,
        "gaps": 0,
        "lost": 0,
    }
    base.update(overrides)
    return base


def test_backpressure_arm_reddens_when_a_publish_blocks():
    defects: list[tuple[str, str]] = []
    gate._arm_backpressure(_burst(), defects, [])  # pylint: disable=protected-access
    assert not defects

    defects = []
    gate._arm_backpressure(  # pylint: disable=protected-access
        _burst(worst=gate.PUBLISH_BUDGET_S * 3), defects, []
    )
    assert "never to wait on a reader" in _reasons(defects)


def test_backpressure_arm_reddens_when_the_burst_never_overran_the_buffers():
    defects: list[tuple[str, str]] = []
    gate._arm_backpressure(  # pylint: disable=protected-access
        _burst(received=4000), defects, []
    )
    assert "was not actually put to the test" in _reasons(defects)


def _overlap(**overrides) -> dict:
    base = {
        "reads": 2_000_000,
        "writes": 130_000,
        "generations": 240,
        "torn_naive": 50,
        "torn_view": 0,
    }
    base.update(overrides)
    return base


def test_concurrency_arm_calls_itself_blind_when_nothing_overlapped():
    assert gate._arm_concurrency(_overlap(), [], []) == ""  # pylint: disable=protected-access
    blind = gate._arm_concurrency(  # pylint: disable=protected-access
        _overlap(generations=1), [], []
    )
    assert "proves serialisation, not safety" in blind


def test_concurrency_arm_calls_itself_blind_when_its_own_control_did_not_fire():
    blind = gate._arm_concurrency(  # pylint: disable=protected-access
        _overlap(torn_naive=0), [], []
    )
    assert "its silence about the view path is blindness" in blind


def test_concurrency_arm_reddens_on_a_torn_view():
    defects: list[tuple[str, str]] = []
    blind = gate._arm_concurrency(  # pylint: disable=protected-access
        _overlap(torn_view=3), defects, []
    )
    assert blind == ""
    assert "rows from DIFFERENT published tables" in _reasons(defects)


def _hijack(**overrides) -> dict:
    base = {
        "error": "",
        "legit": {"applied": 7, "bytes": 2505, "verdict": _verdict("ranked")},
        "returncode": -9,
        "arrived": 16,
        "applied": 7,
        "foreign_rejected": 16,
        "bytes": 8242,
        "verdict": _verdict("fcfs"),
    }
    base.update(overrides)
    return base


def test_sole_writer_arm_calls_itself_blind_when_no_impostor_traffic_arrived():
    assert gate._arm_sole_writer(_hijack(), [], []) == ""  # pylint: disable=protected-access
    blind = gate._arm_sole_writer(_hijack(arrived=0), [], [])  # pylint: disable=protected-access
    assert "ZERO of its messages reached the reader" in blind


def test_sole_writer_arm_reddens_when_the_impostor_table_is_accepted():
    defects: list[tuple[str, str]] = []
    gate._arm_sole_writer(  # pylint: disable=protected-access
        _hijack(applied=23), defects, []
    )
    assert "ACCEPTED an impostor's table" in _reasons(defects)


def test_sole_writer_arm_reddens_when_the_refusal_is_silent():
    defects: list[tuple[str, str]] = []
    gate._arm_sole_writer(  # pylint: disable=protected-access
        _hijack(foreign_rejected=0), defects, []
    )
    assert "A silent drop is indistinguishable" in _reasons(defects)


def test_sole_writer_arm_reddens_when_the_impostor_flips_the_winner():
    defects: list[tuple[str, str]] = []
    gate._arm_sole_writer(  # pylint: disable=protected-access
        _hijack(verdict=_verdict("ranked", SECOND)), defects, []
    )
    assert "changed the winner" in _reasons(defects)


def test_the_read_path_arm_can_fail_on_a_planted_computing_reader():
    ok, why = gate._read_path_arm_can_fail()  # pylint: disable=protected-access
    assert ok, why


def test_read_path_arm_reddens_on_a_computing_lookup_and_greens_on_a_plain_one():
    computing = (
        "class RankingView:\n"
        "    def lookup(self, strategy_id, symbol):\n"
        "        return sum(r.realized_ema for r in self.rows.values()) / 2\n"
    )
    defects: list[tuple[str, str]] = []
    gate._arm_read_path(computing, defects, [])  # pylint: disable=protected-access
    assert "O(1) table lookup, NEVER math" in _reasons(defects)

    defects = []
    clean = (
        "class RankingView:\n"
        "    def lookup(self, strategy_id, symbol):\n"
        "        return self.rows.get((strategy_id, symbol))\n"
    )
    gate._arm_read_path(clean, defects, [])  # pylint: disable=protected-access
    assert not defects


def test_read_path_arm_reddens_when_it_scanned_nothing():
    defects: list[tuple[str, str]] = []
    gate._arm_read_path("X = 1\n", defects, [])  # pylint: disable=protected-access
    assert "a scan over nothing cannot report a computing reader" in _reasons(defects)


# ---------------------------------------------------------------------------
# END TO END — the SHIPPED run(), against an honest tree and a broken copy
# ---------------------------------------------------------------------------


def _home_with(tmp_path: Path, source: str) -> Path:
    """A throwaway nix_home carrying `source` at the subject's path."""
    target = tmp_path / gate.SUBJECT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


def test_run_is_green_on_the_shipped_tree():
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, f"{result.detail} :: {result.evidence}"
    # NON-VACUITY: a PASS that measured nothing would carry no traffic figure.
    assert "bytes of real ranking traffic" in (result.evidence or "")


def test_run_reddens_on_a_computing_reader(tmp_path: Path):
    honest = (REPO / gate.SUBJECT).read_text(encoding="utf-8")
    broken = honest.replace(
        '        """O(1). One dict get on a table that can no longer change."""\n'
        "        return self.rows.get((strategy_id, symbol))\n",
        '        """A reader that computes. The right number, the wrong path."""\n'
        "        return sum(r.realized_ema for r in self.rows.values()) / 2\n",
        1,
    )
    assert broken != honest, "the plant did not apply — this arm would be vacuous"
    home = _home_with(tmp_path, broken)
    result = gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "O(1) table lookup, NEVER math" in (result.detail or "")

    # THE OTHER HALF: the same tree, the same gate, the plant reverted.
    clean = _home_with(tmp_path / "clean", honest)
    again = gate.run(Mode.VERIFY, Context(nix_home=clean, mode=Mode.VERIFY))
    assert again.status is Status.PASS, f"{again.detail} :: {again.evidence}"


def test_run_cannot_measure_when_the_subject_is_unreadable(tmp_path: Path):
    result = gate.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert gate.SUBJECT in (result.detail or "")


def test_the_gate_declares_its_subject_and_its_resources():
    """§4.4 / rule 12: declarations are read statically and must be honest."""
    assert gate.SUBJECTS == ("scripts/nixscore/publisher.py",)
    for claim in (
        "file-write:/tmp",
        "zmq-ipc",
        "subprocess:python",
        "subprocess:python3",
        "threads",
    ):
        assert claim in gate.RESOURCES, f"{claim} is used and not declared"
    assert gate.CORRECTABLE is False and gate.INSTALLABLE is False
    assert isinstance(gate.NON_CORRECTABLE_REASON, str)
    assert gate.NON_CORRECTABLE_REASON.strip()


def test_the_subject_module_is_typed_and_importable_without_a_transport(
    tmp_path: Path,
):
    """`ranking_endpoint` must not require a live socket to be derived.

    The root comes from `tmp_path`, never a literal `/tmp/...`: bandit's B108
    fires on a hardcoded temp path and it is right to — a fixed name under a
    world-writable directory is a real hazard, and this hook's scope covers the
    test tree precisely so the suite cannot model the bad habit.
    """
    assert pub.RANKING_ENDPOINT_NAME == "ranking"
    assert pub.ranking_endpoint(tmp_path).endswith("/ranking.ipc")


def test_a_view_is_immutable_once_captured():
    view = pub.RankingView(
        rows=_rows(), span_days=10, seq=1, stamp=0.0, captured_at=0.0
    )
    with pytest.raises((AttributeError, TypeError)):
        view.span_days = 99  # type: ignore[misc]


def _unused(_: Any) -> None:
    """Keeps `Any` imported for the annotations above without a lint waiver."""
