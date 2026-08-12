"""`scripts/nixrisk/wal.py` — §9's WAL, §11.6's group commit, §12.4's two failures.

What each test proves:

* the record frame round-trips, and a single flipped byte is CAUGHT by the
  checksum and named as a checksum disagreement rather than parsed;
* `recover()` reports a torn tail in BYTES and never raises on damage;
* `enqueue` is not durable and `sync_to_disk` is — `fsyncs` moves only there;
* `GroupCommitWriter` commits from the DURABLE PREFIX only: rows written but
  never fsynced are not handed to the sink;
* §12.4's two failures stay apart — a refusing sink buffers, alerts and keeps
  admitting entries; a WAL that cannot append refuses entries, latches, and
  still permits the protective exit.

The real-process arms (SIGKILL, RLIMIT_FSIZE, the strace-observed fsync) live in
`scripts/wal_kill_drill.py` and are driven by `checks/check_plane1_wal.py`; this
module is the in-process half and does not restate them.
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

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixrisk import wal as wal_mod
from nixrisk.seam import EventKind, EventRow


def _row(index: int) -> EventRow:
    return EventRow(
        kind=EventKind.ACCEPTED,
        ts=1_700_000_000.0 + index,
        strategy_id="s1",
        reason=f"row {index}",
        trade_id=f"T{index}",
        fields={"index": str(index)},
    )


def _wal(tmp_path: Path, **kwargs) -> wal_mod.Plane1Wal:
    return wal_mod.Plane1Wal(tmp_path / "plane1.wal", **kwargs)


# ---------------------------------------------------------------------------
# The frame
# ---------------------------------------------------------------------------


def test_a_record_ROUND_TRIPS_every_SS9_field() -> None:
    original = _row(7)
    assert wal_mod.decode_record(wal_mod.encode_row(original)[:-1]) == original


def test_a_FLIPPED_BYTE_is_caught_by_the_CHECKSUM_and_named() -> None:
    """Without the checksum a corrupted record parses into plausible truth."""
    record = bytearray(wal_mod.encode_row(_row(1))[:-1])
    body_at = record.index(b" ") + 12
    record[body_at] = record[body_at] ^ 0x01
    with pytest.raises(wal_mod.WalError) as red:
        wal_mod.decode_record(bytes(record))
    assert "checksum" in str(red.value), str(red.value)


def test_recover_reports_a_TORN_TAIL_in_bytes_and_does_NOT_raise(
    tmp_path: Path,
) -> None:
    """§9's crash gap needs the intact rows to survive the damaged one."""
    wal = _wal(tmp_path)
    for index in range(4):
        wal.enqueue(_row(index))
    wal.sync_to_disk()
    half = wal_mod.encode_row(_row(99))
    with open(wal.path, "ab", buffering=0) as handle:
        handle.write(half[: len(half) // 2])
    wal.close()

    recovered = wal_mod.recover(wal.path)
    assert len(recovered.rows) == 4, recovered
    assert recovered.torn_tail_bytes > 0, recovered
    assert recovered.corrupt_records == 0, recovered
    assert recovered.intact is False, recovered


def test_recover_COUNTS_a_corrupt_record_without_losing_the_others(
    tmp_path: Path,
) -> None:
    wal = _wal(tmp_path)
    for index in range(3):
        wal.enqueue(_row(index))
    wal.sync_to_disk()
    wal.close()
    blob = bytearray(wal.path.read_bytes())
    blob[blob.index(b"\n") + 15] ^= 0x01
    wal.path.write_bytes(bytes(blob))

    recovered = wal_mod.recover(wal.path)
    assert recovered.corrupt_records == 1, recovered
    assert len(recovered.rows) == 2, [row.trade_id for row in recovered.rows]


# ---------------------------------------------------------------------------
# The split: enqueue is not durability
# ---------------------------------------------------------------------------


def test_enqueue_is_NOT_durable_and_sync_to_disk_IS(tmp_path: Path) -> None:
    """§9/§11.6's split, as counters. `fsyncs` moves in exactly one place."""
    wal = _wal(tmp_path)
    for index in range(5):
        wal.enqueue(_row(index))
    assert wal.pending() == 5, wal.pending()
    assert wal.fsyncs == 0, "enqueue must not reach stable storage"
    assert wal.durable_bytes == 0, wal.durable_bytes

    made = wal.sync_to_disk()
    assert made == 5, made
    assert wal.pending() == 0 and wal.fsyncs == 1, (wal.pending(), wal.fsyncs)
    assert wal.durable_bytes == wal.bytes_written, wal.durable_bytes
    assert wal.sync_to_disk() == 0, "an empty sync is not an fsync"
    assert wal.fsyncs == 1, wal.fsyncs
    wal.close()


def test_group_commit_reads_the_DURABLE_PREFIX_and_nothing_beyond(
    tmp_path: Path,
) -> None:
    """§9's ordering: enqueue -> durable WAL -> writer -> group-commit."""
    wal = _wal(tmp_path)
    sink = wal_mod.RecordingSink()
    writer = wal_mod.GroupCommitWriter(wal, sink)
    for index in range(6):
        wal.enqueue(_row(index))
    assert writer.drain_once().committed == 0, "un-fsynced rows must not commit"
    assert not sink.rows, sink.rows

    wal.sync_to_disk()
    result = writer.drain_once()
    assert result.committed == 6 and result.backlog == 0, result
    assert [row.trade_id for row in sink.rows] == [f"T{i}" for i in range(6)]
    wal.close()


# ---------------------------------------------------------------------------
# §12.4 — the two failures, kept apart
# ---------------------------------------------------------------------------


def test_a_SINK_outage_BUFFERS_alerts_and_keeps_ADMITTING_entries(
    tmp_path: Path,
) -> None:
    """*Degraded persistence ≠ degraded trading* — the whole sentence."""
    alerts: list[tuple[str, str]] = []
    wal = _wal(tmp_path, alert=lambda event, detail: alerts.append((event, detail)))
    sink = wal_mod.RecordingSink()
    writer = wal_mod.GroupCommitWriter(wal, sink)
    sink.fail_with = RuntimeError("planted Postgres outage")
    for index in range(4):
        wal.enqueue(_row(index))
    wal.sync_to_disk()

    result = writer.drain_once()
    assert result.ok is False and "planted Postgres outage" in result.error, result
    assert result.state is wal_mod.PersistenceState.SINK_DEGRADED, result.state
    assert result.backlog == 4, result.backlog
    admits, why = wal.admits_new_entries()
    assert admits is True, why
    assert "NOT degraded trading" in why, why
    assert [event for event, _ in alerts] == ["wal_sink_degraded"], alerts

    wal.enqueue(_row(99))  # trading CONTINUES
    wal.sync_to_disk()
    sink.fail_with = None
    restored = writer.drain_once()
    assert restored.committed == 5 and restored.backlog == 0, restored
    assert wal.state is wal_mod.PersistenceState.HEALTHY, wal.state
    assert "wal_sink_restored" in [event for event, _ in alerts], alerts
    wal.close()


def test_DISK_CRITICAL_refuses_entries_LATCHES_and_still_permits_the_EXIT(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§12.4's halting branch. The KERNEL's version of this is in the drill.

    Here the append is made to fail through the WAL's own handle, which exercises
    `enqueue`'s error path and the latch. `checks/check_plane1_wal.py` ARM 4 is
    the one that makes a real filesystem say EFBIG; this test is about what the
    object does once it has been told, and says so rather than claiming the
    stronger measurement.
    """
    wal = _wal(tmp_path)
    wal.enqueue(_row(0))
    wal.sync_to_disk()

    def _refuse(_data: bytes) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(wal._fh, "write", _refuse)
    with pytest.raises(wal_mod.DiskCritical) as red:
        wal.enqueue(_row(1))
    assert "could not append" in str(red.value), str(red.value)

    assert wal.state is wal_mod.PersistenceState.DISK_CRITICAL, wal.state
    admits, why = wal.admits_new_entries()
    assert admits is False, why
    assert "disk-critical" in why and "errno=28" in why, why

    exits, exit_why = wal.protective_exit_allowed()
    assert exits is True, exit_why
    assert "stops read MEMORY, not disk" in exit_why, exit_why

    # LATCHED: the condition does not clear itself, and a healthy handle does not
    # un-latch it either.
    monkeypatch.undo()
    with pytest.raises(wal_mod.DiskCritical):
        wal.enqueue(_row(2))
    wal.note_sink(False, "sink is fine")
    assert wal.state is wal_mod.PersistenceState.DISK_CRITICAL, wal.state
    wal.close()


def test_the_protective_exit_is_permitted_in_EVERY_state(tmp_path: Path) -> None:
    """The one answer that must never depend on the disk."""
    wal = _wal(tmp_path)
    for degraded in (False, True):
        wal.note_sink(degraded, "state walk")
        allowed, why = wal.protective_exit_allowed()
        assert allowed is True, (wal.state, why)
        assert wal.state.value in why, why
    wal.close()


def test_a_batch_max_below_one_is_REFUSED(tmp_path: Path) -> None:
    with pytest.raises(wal_mod.WalError) as red:
        wal_mod.GroupCommitWriter(_wal(tmp_path), wal_mod.RecordingSink(), batch_max=0)
    assert "batch_max" in str(red.value), str(red.value)
