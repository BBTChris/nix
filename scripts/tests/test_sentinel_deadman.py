"""ARC 034 / B — the §12.1 deadman can say no, and can say yes for the right reason.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen risk spec,
unless another document is named on the same line.

EVERY CONTROL HERE ASSERTS THE REASON, never an exit code and never a bare
status (`docs/nix_check_contract.md` §18). An exception type is a shared
namespace: `MarkerError` is raised by a corrupt line, a schema mismatch and a
device that refused to sync, and a control that only caught the class would pass
against all three whichever one it meant.

The properties, and why each has a control:

  * **ABSENCE IS NOT LOSS.** A Sentinel that started before the Limiter has seen
    nothing and has no evidence of exposure. Collapsing that into "lost" flattens
    every cold boot — §12.1:605's nuisance hazard fired on the most routine event
    there is.
  * **A FROZEN `seq` UNDER A LIVE `ts` IS A HANG.** The one case staleness cannot
    catch, and the reason the watchdog runs two detectors instead of one.
  * **THE MARKER IS ON DISK BEFORE THE BROKER IS TOUCHED.** Proven by a broker
    double that READS the marker from inside `flatten_all` — the ordering is
    measured at the instant it matters, not inferred from the file afterwards.
  * **A `BEFORE` WITH NO `AFTER` IS EVIDENCE, NOT CORRUPTION.** Driven by a
    broker that dies, and replayed by the real `nixrisk.coldstart.ColdStart`.
  * **THE BROKER WINS OVER THE DEAD PROCESS'S HINT, BOTH WAYS.** One direction
    alone is passed by a Sentinel that always flattens and by one that never
    does.
  * **A DOWN ALERT CHANNEL COSTS NOTHING** (§14:975, zero delivery dependency).

No plant touches a production artifact (doctrine C.8): every case runs inside
`tmp_path`, and the only real files read are `risks/*.config.json`, which are
copied before being perturbed.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=too-many-lines
# C0302 (too-many-lines): one control per property, and the properties are
# the §12.1 deadman's whole surface — the heartbeat's three conditions, the
# marker's durability and refusals, the watchdog's two detectors and its
# latches, the hint-versus-broker pair, the knobs, and the replay. Splitting
# them across modules would hide which suite owns which property, and every
# control here is short; the length is the count, not the complexity.
# pylint: disable=protected-access,too-few-public-methods
# pylint: disable=use-implicit-booleaness-not-comparison
# C1803 (`x == []` could be `not x`): REFUSED here, and the refusal is the point.
# `not x` is satisfied by None, 0, "" and any object with a falsey `__len__`, so
# it asserts "something falsey happened" where these controls assert "the value
# is the EMPTY SEQUENCE". A Sentinel that returned None where it should return an
# empty tuple of acks is exactly the silent pass this suite exists to catch, and
# the simplification would hide it.
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# test module by requirement. protected-access: two controls reach into the
# watchdog's own latch to prove a SECOND poll behaves differently from the
# first, which is a property of the state and cannot be seen from outside it.

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import nixsentinel.config as sconfig
from nixrisk.coldstart import SOURCE_SENTINEL, ColdStart
from nixsentinel.heartbeat import (
    HEARTBEAT_SCHEMA,
    HeartbeatError,
    HeartbeatFile,
    HeartbeatPublisher,
)
from nixsentinel.marker import (
    MarkerError,
    MarkerReplay,
    MarkerWriter,
    pending_acts,
    unbracketed,
)
from nixsentinel.seam import (
    MARKER_SCHEMA,
    BrokerAck,
    MarkerPhase,
    MarkerRecord,
    SentinelPosition,
    TriggerCause,
)
from nixsentinel.watchdog import LivenessClass, Sentinel

#: A fast knob set for the controls. Real `SentinelKnobs`, drill values: the
#: properties under test are ORDERING and CONDITION, neither of which is a
#: function of the clock.
KNOBS = sconfig.SentinelKnobs(
    heartbeat_interval_s=1.0,
    heartbeat_miss_grace_cycles=1.0,
    heartbeat_loss_multiple=5.0,
    poll_interval_s=0.25,
)
THRESHOLD = KNOBS.loss_threshold_s


# --------------------------------------------------------------------------
# Doubles — the collaborators only. Every SUBJECT below is the real class.
# --------------------------------------------------------------------------


class Broker:
    """The Sentinel's own session. Records the verb order; can misbehave."""

    def __init__(self, symbols=(), *, boom=None, peek=None) -> None:
        self.symbols = tuple(symbols)
        self.calls: list[str] = []
        self._boom = boom
        self._peek = peek
        #: What the marker file held at the instant `flatten_all` was entered.
        self.saw_marker: list[dict] = []

    def connect(self) -> None:
        """Open this process's own session."""
        self.calls.append("connect")

    def open_positions(self):
        """The AUTHORITATIVE answer to §12.1:605's second half."""
        self.calls.append("open_positions")
        return tuple(SentinelPosition(symbol=s, size=1) for s in self.symbols)

    def flatten_all(self):
        """Close everything — or fail, or look at the marker on the way past."""
        self.calls.append("flatten_all")
        if self._peek is not None:
            self.saw_marker = [
                json.loads(line)
                for line in self._peek.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        if self._boom is not None:
            raise self._boom
        return tuple(
            BrokerAck(symbol=s, ok=True, detail="test: closed") for s in self.symbols
        )

    def disconnect(self) -> None:
        """Release the session."""
        self.calls.append("disconnect")


class Alert:
    """The operator channel. `fail=True` VIOLATES the seam's never-raises rule."""

    def __init__(self, *, fail: bool = False) -> None:
        self.raised: list[tuple[str, str]] = []
        self._fail = fail

    def raise_alert(self, cause: TriggerCause, detail: str) -> None:
        """Tell the operator, or refuse to."""
        self.raised.append((cause.value, detail))
        if self._fail:
            raise RuntimeError("test: the operator alert channel is DOWN")


class Plane1:
    """A recording §9 sink. `calls` preserves enqueue/sync ORDER."""

    def __init__(self) -> None:
        self.rows: list = []
        self.calls: list[str] = []

    def enqueue(self, row) -> None:
        """Buffer one row. Not durable by design."""
        self.rows.append(row)
        self.calls.append("enqueue")

    def sync_to_disk(self) -> int:
        """Make the buffer durable."""
        self.calls.append("sync")
        return len(self.rows)

    def pending(self) -> int:
        """Rows enqueued but not durable."""
        return 0


def _sentinel(tmp_path: Path, *, broker: Broker, alert: Alert | None = None):
    """A real `Sentinel` over a real `HeartbeatFile` and a real `MarkerWriter`."""
    return Sentinel(
        heartbeat=HeartbeatFile(tmp_path / "hb.json"),
        broker=broker,
        marker=MarkerWriter(tmp_path / "marker.jsonl"),
        alert=alert or Alert(),
        knobs=KNOBS,
        pid=4242,
    )


def _beat(tmp_path: Path, *, pid: int, seq_to: int, ts: float, hint: int = 1) -> None:
    """Publish `seq_to` beats from `pid`, all stamped `ts`. Real publisher."""
    publisher = HeartbeatPublisher(tmp_path / "hb.json", pid=pid, clock=lambda: ts)
    for _ in range(seq_to):
        publisher.publish(hint)


def _marker(tmp_path: Path) -> list[dict]:
    """The marker file, raw. Read as JSON so a control can assert on ORDER."""
    path = tmp_path / "marker.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _record(phase: MarkerPhase, cause: TriggerCause, **kw) -> MarkerRecord:
    """One real `MarkerRecord`, seam types throughout."""
    return MarkerRecord(
        schema=MARKER_SCHEMA,
        phase=phase,
        ts=kw.get("ts", 1000.0),
        cause=cause,
        symbols=kw.get("symbols", ("MES",)),
        acks=kw.get("acks", ()),
        sentinel_pid=kw.get("sentinel_pid", 4242),
        heartbeat_age_s=kw.get("heartbeat_age_s", 9.0),
    )


# ==========================================================================
# THE HEARTBEAT — absence, corruption and schema are THREE conditions
# ==========================================================================


def test_a_HEARTBEAT_THAT_WAS_NEVER_PUBLISHED_reads_as_NONE_and_never_raises(
    tmp_path: Path,
) -> None:
    """The seam's port: `None` means never published, which is not a fault."""
    assert HeartbeatFile(tmp_path / "hb.json").read() is None


def test_a_CORRUPT_HEARTBEAT_RAISES_and_SAYS_it_is_not_an_absent_one(
    tmp_path: Path,
) -> None:
    """Absence and corruption must not collapse: one is a cold boot, the other a
    fault, and treating the second as the first hides it forever."""
    (tmp_path / "hb.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(HeartbeatError) as caught:
        HeartbeatFile(tmp_path / "hb.json").read()

    assert "not a heartbeat record" in str(caught.value), caught.value
    assert "absent" in str(caught.value), caught.value


def test_a_HEARTBEAT_FROM_ANOTHER_BUILD_is_REFUSED_by_schema_and_says_so(
    tmp_path: Path,
) -> None:
    """The publisher and the watcher are different processes and may be different
    builds; reading fields positionally into the wrong meaning is the failure."""
    (tmp_path / "hb.json").write_text(
        json.dumps(
            {
                "schema": HEARTBEAT_SCHEMA + 7,
                "pid": 1,
                "ts": 1.0,
                "seq": 1,
                "positions_open": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HeartbeatError) as caught:
        HeartbeatFile(tmp_path / "hb.json").read()

    assert "schema" in str(caught.value), caught.value
    assert "different builds" in str(caught.value), caught.value


def test_an_EMPTY_HEARTBEAT_FILE_is_a_FAULT_and_not_an_absent_one(
    tmp_path: Path,
) -> None:
    """Something made the file. That is not 'the Limiter never spoke'."""
    (tmp_path / "hb.json").write_text("", encoding="utf-8")

    with pytest.raises(HeartbeatError) as caught:
        HeartbeatFile(tmp_path / "hb.json").read()

    assert "did not finish being written" in str(caught.value), caught.value


def test_the_PUBLISHER_STAMPS_ITS_PID_ONCE_and_ADVANCES_SEQ_per_beat(
    tmp_path: Path,
) -> None:
    """`seq` is the progress signal and `pid` the identity; both are what let a
    restart be told from a hang."""
    publisher = HeartbeatPublisher(tmp_path / "hb.json", pid=77, clock=lambda: 5.0)
    first = publisher.publish(2)
    second = publisher.publish(2)

    assert (first.pid, first.seq) == (77, 1), first
    assert (second.pid, second.seq) == (77, 2), second
    assert publisher.seq == 2, publisher.seq
    assert HeartbeatFile(tmp_path / "hb.json").read() == second
    assert HeartbeatPublisher(tmp_path / "hb.json", pid=78).seq == 0, (
        "a FRESH publisher must start at zero — a seq that persisted across "
        "processes would make a restart indistinguishable from a hang"
    )


# ==========================================================================
# THE MARKER — durability, append-only, and a refusal to discard evidence
# ==========================================================================


def test_APPEND_IS_DURABLE_ON_RETURN_across_a_process_that_stops_existing(
    tmp_path: Path,
) -> None:
    """`os._exit` skips every buffer flush, every `finally` and every `atexit`
    hook. A record that survives it was on the device when `append` returned —
    which is the whole of §12.1:608's fix, and is not provable by any assertion
    made inside the process that did the writing."""
    marker = tmp_path / "marker.jsonl"
    # The reprs are computed FIRST so the program below carries no nested
    # quoting. A drill program that is subtly mis-quoted fails for a reason no
    # linter reads and no assertion names.
    scripts_dir = repr(str(REPO / "scripts"))
    target = repr(str(marker))
    program = (
        "import os, sys;"
        f"sys.path.insert(0, {scripts_dir});"
        "from nixsentinel.marker import MarkerWriter;"
        "from nixsentinel.seam import MARKER_SCHEMA, MarkerPhase, MarkerRecord, "
        "TriggerCause;"
        f"MarkerWriter({target}).append(MarkerRecord(schema=MARKER_SCHEMA, "
        "phase=MarkerPhase.BEFORE, ts=1.0, cause=TriggerCause.HEARTBEAT_LOST, "
        "symbols=('MES',), acks=(), sentinel_pid=1, heartbeat_age_s=9.0));"
        "os._exit(0)"
    )

    proc = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False
    )

    assert proc.returncode == 0, proc.stderr
    survived = MarkerReplay(marker).read_pending()
    assert len(survived) == 1, (
        "the record did not survive a process that ceased immediately after "
        f"append() returned, so it was buffered: {proc.stderr}"
    )
    assert survived[0].phase is MarkerPhase.BEFORE


def test_APPEND_CALLS_FSYNC_before_it_returns(tmp_path: Path, monkeypatch) -> None:
    """Observed, not read out of the writer's own docstring."""
    seen: list[int] = []
    real = os.fsync

    def spy(fd: int) -> None:
        seen.append(fd)
        real(fd)

    monkeypatch.setattr(os, "fsync", spy)

    MarkerWriter(tmp_path / "marker.jsonl").append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
    )

    assert seen, "append() returned having synced nothing"


def test_a_FAILED_FSYNC_is_LOUD_and_never_returns_as_if_the_record_were_safe(
    tmp_path: Path, monkeypatch
) -> None:
    """A caller told a record is durable when nothing reached the device has been
    handed the exact false assurance §12.1:608 exists to remove."""

    def angry(fd: int) -> None:
        raise OSError(5, f"test: the device refused fd {fd}")

    monkeypatch.setattr(os, "fsync", angry)

    with pytest.raises(MarkerError) as caught:
        MarkerWriter(tmp_path / "marker.jsonl").append(
            _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
        )

    assert "refusing to return as if the record were durable" in str(caught.value)


def test_a_BEFORE_WITH_NO_AFTER_READS_BACK_and_is_never_treated_as_damage(
    tmp_path: Path,
) -> None:
    """The single most valuable line the file can hold. A reader that rejected it
    would destroy the evidence of the exact catastrophe §12.1 was written for."""
    MarkerWriter(tmp_path / "marker.jsonl").append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
    )

    records = MarkerReplay(tmp_path / "marker.jsonl").read_pending()

    assert [r.phase for r in records] == [MarkerPhase.BEFORE]
    assert pending_acts(records) == ((records[0], None),)


def test_a_DAMAGED_LINE_is_REFUSED_by_name_rather_than_SKIPPED(
    tmp_path: Path,
) -> None:
    """Skipping is the one thing this reader must not do: the unparsable line may
    be the only evidence that an emergency flatten was attempted."""
    marker = tmp_path / "marker.jsonl"
    MarkerWriter(marker).append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
    )
    with marker.open("a", encoding="utf-8") as handle:
        handle.write('{"schema": 1, "phase": "sideways"}\n')

    with pytest.raises(MarkerError) as caught:
        MarkerReplay(marker).read_pending()

    assert "refusing to SKIP it" in str(caught.value), caught.value
    assert f"{marker}:2" in str(caught.value), caught.value


def test_a_MARKER_FROM_ANOTHER_BUILD_is_REFUSED_by_schema_and_says_why(
    tmp_path: Path,
) -> None:
    """Written on one boot, read on a later one; the builds may differ."""
    marker = tmp_path / "marker.jsonl"
    marker.write_text(
        json.dumps(
            {
                "schema": MARKER_SCHEMA + 3,
                "phase": "before",
                "ts": 1.0,
                "cause": "heartbeat_lost",
                "symbols": [],
                "acks": [],
                "sentinel_pid": 1,
                "heartbeat_age_s": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MarkerError) as caught:
        MarkerReplay(marker).read_pending()

    assert "marker schema" in str(caught.value), caught.value
    assert "different BOOTS" in str(caught.value), caught.value


def test_ARCHIVING_RENAMES_and_never_deletes_the_only_account_that_exists(
    tmp_path: Path,
) -> None:
    """Directive 6 applies to the marker as much as to the log it feeds."""
    marker = tmp_path / "marker.jsonl"
    MarkerWriter(marker).append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
    )

    MarkerReplay(marker, clock=lambda: 1234.5).archive()

    assert not marker.exists()
    archived = list(tmp_path.glob("marker.jsonl.*.replayed"))
    assert len(archived) == 1, sorted(p.name for p in tmp_path.iterdir())
    assert archived[0].read_text(encoding="utf-8").strip(), "the archive is empty"
    assert MarkerReplay(marker).read_pending() == ()


def test_UNBRACKETED_RECORDS_are_the_WAKES_THAT_DID_NOT_FLATTEN(
    tmp_path: Path,
) -> None:
    """A deadman that proved its restraint by producing no output would be
    indistinguishable from one that never ran (§12.1:605)."""
    writer = MarkerWriter(tmp_path / "marker.jsonl")
    writer.append(
        _record(MarkerPhase.AFTER, TriggerCause.HEARTBEAT_LOST_NO_POSITIONS, symbols=())
    )
    writer.append(_record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST))
    writer.append(
        _record(
            MarkerPhase.AFTER,
            TriggerCause.HEARTBEAT_LOST,
            acks=(BrokerAck("MES", True, "closed"),),
        )
    )

    records = MarkerReplay(tmp_path / "marker.jsonl").read_pending()

    assert [r.cause for r in unbracketed(records)] == [
        TriggerCause.HEARTBEAT_LOST_NO_POSITIONS
    ]
    assert len(pending_acts(records)) == 1
    assert pending_acts(records)[0][1] is not None


# ==========================================================================
# THE WATCHDOG — the condition, both halves, and the two detectors
# ==========================================================================


def test_a_SENTINEL_THAT_HAS_NEVER_SEEN_A_HEARTBEAT_DOES_NOT_ACT(
    tmp_path: Path,
) -> None:
    """Absence is not loss. Treating it as loss flattens every cold boot."""
    broker = Broker(("MES",))
    outcome = _sentinel(tmp_path, broker=broker).poll(now=10_000.0)

    assert outcome.liveness is LivenessClass.NEVER_SEEN
    assert outcome.cause is None and not outcome.acted
    assert "has ever been published" in outcome.detail, outcome.detail
    assert broker.calls == [], broker.calls
    assert _marker(tmp_path) == []


def test_a_LIVE_HEARTBEAT_PRODUCES_NO_ACTION_and_NO_BROKER_SESSION(
    tmp_path: Path,
) -> None:
    """§14:977 keeps flatten execution Limiter-only while the Limiter lives, and
    the Sentinel's own session is opened when the condition fires, not kept warm."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)

    first = sentinel.poll(now=1000.0)
    _beat(tmp_path, pid=100, seq_to=2, ts=1001.0)
    second = sentinel.poll(now=1001.0)

    assert first.liveness is LivenessClass.FIRST_SEEN
    assert second.liveness is LivenessClass.PROGRESSING
    assert (first.cause, second.cause) == (None, None)
    assert broker.calls == [], broker.calls
    assert _marker(tmp_path) == []


def test_a_FROZEN_SEQ_UNDER_AN_ADVANCING_TS_IS_A_HANG_and_IS_LOST(
    tmp_path: Path,
) -> None:
    """THE case staleness cannot catch. A wedged Risk Engine can still have a
    thread stamping a fresh `ts` while the counter that proves work is frozen; a
    watcher reading `ts` alone calls that healthy forever.

    The heartbeat here is NEVER stale — `ts` tracks `now` on every poll — so a
    verdict of LOST can only have come from the no-progress detector.
    """
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    publisher = HeartbeatPublisher(tmp_path / "hb.json", pid=100, clock=lambda: 0.0)

    outcomes = []
    for step in range(int(THRESHOLD) + 3):
        now = 1000.0 + step
        # Same pid, same seq, FRESH ts: the file is rewritten by hand so `seq`
        # cannot advance, which is what a wedged publisher looks like.
        (tmp_path / "hb.json").write_text(
            json.dumps(
                {
                    "schema": HEARTBEAT_SCHEMA,
                    "pid": 100,
                    "ts": now,
                    "seq": 1,
                    "positions_open": 1,
                }
            ),
            encoding="utf-8",
        )
        outcomes.append(sentinel.poll(now=now))
    del publisher

    assert outcomes[0].liveness is LivenessClass.FIRST_SEEN
    acted = [wake for wake in outcomes if wake.acted]
    assert len(acted) == 1, [w.cause for w in outcomes]
    fired = acted[0]
    assert fired.liveness is LivenessClass.FROZEN
    assert not fired.stale, (
        "the staleness detector fired, so this control did not measure the hang "
        f"detector at all: age={fired.heartbeat_age_s}"
    )
    assert fired.no_progress, fired.detail
    assert fired.cause is TriggerCause.HEARTBEAT_LOST, fired.detail
    assert "no progress" in fired.detail, fired.detail
    assert "stale" not in fired.detail, (
        "the message names the staleness detector on a wake where it did not "
        f"fire: {fired.detail}"
    )


def test_a_NEW_PID_WITH_SEQ_RESET_IS_A_RESTART_and_is_NOT_a_loss(
    tmp_path: Path,
) -> None:
    """§12.2's supervisor did its job. `ts` alone cannot tell this from a hang,
    and the two call for different operator narratives."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=9, ts=1000.0)
    sentinel.poll(now=1000.0)

    _beat(tmp_path, pid=200, seq_to=1, ts=1001.0)
    after = sentinel.poll(now=1001.0)

    assert after.liveness is LivenessClass.RESTARTED, after.detail
    assert (after.observed_pid, after.observed_seq) == (200, 1)
    assert after.cause is None and not after.acted
    assert broker.calls == [], broker.calls


def test_HEARTBEAT_LOST_WITH_A_FLAT_ACCOUNT_RECORDS_RESTRAINT_and_does_NOT_flatten(
    tmp_path: Path,
) -> None:
    """§12.1:605 conditions the act on positions possibly being open. The
    restraint is written down so it is an observable fact."""
    broker = Broker(())
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0, hint=4)

    outcome = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert outcome.cause is TriggerCause.HEARTBEAT_LOST_NO_POSITIONS
    assert not outcome.acted
    assert "flatten_all" not in broker.calls, broker.calls
    assert [r["phase"] for r in _marker(tmp_path)] == ["after"], _marker(tmp_path)
    assert _marker(tmp_path)[0]["cause"] == "heartbeat_lost_no_positions"


def test_THE_MARKER_IS_ALREADY_ON_DISK_WHEN_THE_BROKER_IS_TOUCHED(
    tmp_path: Path,
) -> None:
    """The ordering measured AT THE INSTANT IT MATTERS. The broker double reads
    the marker file from inside `flatten_all`; a `BEFORE` written after the send —
    or buffered — would not be there to read."""
    broker = Broker(("MES", "MNQ"), peek=tmp_path / "marker.jsonl")
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)

    outcome = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert broker.calls == ["connect", "open_positions", "flatten_all"], broker.calls
    assert [r["phase"] for r in broker.saw_marker] == ["before"], broker.saw_marker
    assert broker.saw_marker[0]["symbols"] == ["MES", "MNQ"]
    assert broker.saw_marker[0]["acks"] == [], (
        "the 'before' record carried acknowledgements, and nothing had been asked "
        "to acknowledge anything yet"
    )
    assert outcome.acted and outcome.cause is TriggerCause.HEARTBEAT_LOST
    assert [r["phase"] for r in _marker(tmp_path)] == ["before", "after"]


def test_A_BROKER_THAT_DIES_MID_FLATTEN_LEAVES_A_BEFORE_AND_NO_AFTER(
    tmp_path: Path,
) -> None:
    """The interrupted act. The exception propagates — §12.2's crash-loop breaker
    is what decides what happens next, and swallowing it here would put a second
    supervision policy in the one module whose value is that it has none."""
    boom = RuntimeError("test: the venue never answered")
    broker = Broker(("MES",), boom=boom)
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)

    with pytest.raises(RuntimeError) as caught:
        sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert "never answered" in str(caught.value), caught.value
    assert [r["phase"] for r in _marker(tmp_path)] == ["before"], _marker(tmp_path)


def test_A_DOWN_ALERT_CHANNEL_DOES_NOT_COST_THE_FLATTEN(tmp_path: Path) -> None:
    """§14:975 — the exit path has zero delivery dependency. The channel here
    VIOLATES the seam's never-raises declaration, which is the only way to
    measure that a broken one cannot abort an exit."""
    broker = Broker(("MES",))
    alert = Alert(fail=True)
    sentinel = _sentinel(tmp_path, broker=broker, alert=alert)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)

    outcome = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert outcome.acted and len(outcome.acks) == 1
    assert [r["phase"] for r in _marker(tmp_path)] == ["before", "after"]
    assert "alert channel refused" in outcome.alert_failed, outcome.alert_failed
    assert "zero delivery dependency" in outcome.alert_failed
    assert alert.raised, "the channel was never even attempted"


def test_A_SECOND_POLL_WHILE_STILL_DEAD_DOES_NOT_FLATTEN_AGAIN(
    tmp_path: Path,
) -> None:
    """The Limiter is dead, so nothing can have opened a new position; a
    re-flatten every poll would be a stream of nuisance orders at a flat account."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)

    first = sentinel.poll(now=1000.0 + THRESHOLD + 1)
    second = sentinel.poll(now=1000.0 + THRESHOLD + 2)

    assert first.acted and not second.acted
    assert second.latched, second.detail
    assert "already acted" in second.detail, second.detail
    assert broker.calls.count("flatten_all") == 1, broker.calls


def test_A_RECOVERED_HEARTBEAT_CLEARS_THE_LATCH_and_is_RECORDED(
    tmp_path: Path,
) -> None:
    """A watcher that declared death and then quietly changed its mind would
    leave an operator with no account of how the episode ended."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)
    sentinel.poll(now=1000.0 + THRESHOLD + 1)

    _beat(tmp_path, pid=200, seq_to=1, ts=2000.0)
    recovered = sentinel.poll(now=2000.0)

    assert recovered.cause is TriggerCause.HEARTBEAT_RECOVERED, recovered.detail
    assert not recovered.acted
    assert sentinel._fired is False, "the latch survived a recovery"
    causes = [r["cause"] for r in _marker(tmp_path)]
    assert causes[-1] == "heartbeat_recovered", causes


def test_AN_UNREADABLE_HEARTBEAT_COUNTS_AS_NO_PROGRESS_and_FAILS_CLOSED(
    tmp_path: Path,
) -> None:
    """A heartbeat this process cannot read has not proven the Limiter alive."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)
    sentinel.poll(now=1000.0)

    (tmp_path / "hb.json").write_text("{corrupt", encoding="utf-8")
    outcome = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert outcome.liveness is LivenessClass.UNREADABLE, outcome.detail
    assert outcome.cause is TriggerCause.HEARTBEAT_LOST, outcome.detail
    assert outcome.acted


# ==========================================================================
# THE HINT IS NOT THE ANSWER — both directions
# ==========================================================================


def test_THE_BROKER_WINS_WHEN_THE_HINT_SAYS_FLAT_AND_THE_BROKER_SAYS_OPEN(
    tmp_path: Path,
) -> None:
    """§4: the broker is the record. The hint is the last known count of a
    process that has been dead for at least the loss threshold."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0, hint=0)

    outcome = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert outcome.hinted_positions_open == 0
    assert outcome.broker_positions_open == 1
    assert outcome.acted, outcome.detail


def test_THE_BROKER_WINS_WHEN_THE_HINT_SAYS_OPEN_AND_THE_BROKER_SAYS_FLAT(
    tmp_path: Path,
) -> None:
    """The other direction, and it must be driven too: a Sentinel that ALWAYS
    flattens passes the control above and fails only here."""
    broker = Broker(())
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0, hint=5)

    outcome = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert outcome.hinted_positions_open == 5
    assert outcome.broker_positions_open == 0
    assert not outcome.acted, outcome.detail
    assert outcome.cause is TriggerCause.HEARTBEAT_LOST_NO_POSITIONS


# ==========================================================================
# THE KNOBS — a narrower load is the common-mode property, not a shortcut
# ==========================================================================


def test_THE_SENTINEL_LOADS_ITS_KNOBS_WHEN_A_SIBLING_CONFIG_IS_BROKEN(
    tmp_path: Path,
) -> None:
    """§12.1:603's *minimal common-mode failure*, made measurable. A deadman that
    refused to start because the Allocator's config had a typo would be absent
    exactly when the box is sick enough to produce one — and `load_risk_configs`
    is shown here refusing the very same tree, so the difference is real."""
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    (tmp_path / "risks" / "allocator.config.json").write_text(
        "{ broken", encoding="utf-8"
    )

    knobs = sconfig.load_sentinel_knobs(tmp_path)

    assert knobs.loss_threshold_s > knobs.limiter_grace_s
    import risk_config as rc  # pylint: disable=import-outside-toplevel

    with pytest.raises(rc.RiskConfigError) as caught:
        rc.load_risk_configs(tmp_path)
    assert "allocator" in str(caught.value), caught.value


def test_A_BROKEN_LIMITER_CONFIG_IS_A_REAL_REFUSAL_and_says_which_file(
    tmp_path: Path,
) -> None:
    """§12A:832's interval has ONE physical home and the threshold is a multiple
    of it. That dependency is genuine, so the refusal is loud rather than
    defaulted (directive 4, doctrine C.7)."""
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    (tmp_path / "risks" / "limiter.config.json").write_text(
        "{ broken", encoding="utf-8"
    )

    with pytest.raises(sconfig.SentinelConfigError) as caught:
        sconfig.load_sentinel_knobs(tmp_path)

    assert "limiter.config.json" in str(caught.value), caught.value
    assert "not valid JSON" in str(caught.value), caught.value


def test_A_KNOB_SET_NO_RULE_GOVERNS_NEVER_LOADS_AS_IF_VALIDATED() -> None:
    """docs/debug.md §7.12: a validator that evaluated nothing must not return."""
    assert sconfig.sentinel_rules(), (
        "no BOOT_RULES entry names the sentinel module, so load_sentinel_knobs "
        "would run zero rules and return a knob set nothing had judged"
    )


# ==========================================================================
# THE REPLAY — §12.1:612-613, through the real cold-start reconciler
# ==========================================================================


def _cold(marker: Path, plane1: Plane1) -> ColdStart:
    """A real `ColdStart` with a real `MarkerReplay` and nothing else live."""
    return ColdStart(
        broker=None,  # type: ignore[arg-type]
        flattener=None,  # type: ignore[arg-type]
        halt=None,  # type: ignore[arg-type]
        plane1=plane1,
        sentinel_marker=MarkerReplay(marker, clock=lambda: 9999.0),
    )


def test_AN_INTERRUPTED_FLATTEN_IS_BOOKED_TAGGED_AND_STAMPED_WHEN_IT_HAPPENED(
    tmp_path: Path,
) -> None:
    """§12.1:612-613. A row carrying the BOOT time would move a money event by
    however long the box was down, and one that could not say the close was
    unconfirmed would be read as settled."""
    marker = tmp_path / "marker.jsonl"
    MarkerWriter(marker).append(
        _record(
            MarkerPhase.BEFORE,
            TriggerCause.HEARTBEAT_LOST,
            ts=777.0,
            symbols=("MES", "MNQ"),
        )
    )
    plane1 = Plane1()

    rows = _cold(marker, plane1).replay_sentinel_marker(now=9999.0)

    exits = [
        r
        for r in rows
        if r.fields.get("source") == SOURCE_SENTINEL and r.fields.get("symbol")
    ]
    assert [r.fields["symbol"] for r in exits] == ["MES", "MNQ"], rows
    assert all(r.ts == 777.0 for r in exits), [r.ts for r in exits]
    assert all(r.fields["interrupted"] == "true" for r in exits)
    assert all(r.fields["ack_ok"] == "unknown" for r in exits)
    assert "did not survive the act" in exits[0].fields["ack_detail"]
    assert "MID-FLATTEN" in exits[0].reason, exits[0].reason


def test_A_COMPLETED_FLATTEN_IS_BOOKED_WITH_ITS_ACKS_and_NOT_flagged_interrupted(
    tmp_path: Path,
) -> None:
    """The ordinary case has to be distinguishable from the catastrophic one, or
    the flag proves nothing."""
    marker = tmp_path / "marker.jsonl"
    writer = MarkerWriter(marker)
    writer.append(_record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST, ts=500.0))
    writer.append(
        _record(
            MarkerPhase.AFTER,
            TriggerCause.HEARTBEAT_LOST,
            ts=501.0,
            acks=(BrokerAck("MES", False, "venue rejected: market closed"),),
        )
    )
    plane1 = Plane1()

    rows = _cold(marker, plane1).replay_sentinel_marker(now=9999.0)

    exits = [r for r in rows if r.fields.get("symbol")]
    assert len(exits) == 1, rows
    assert exits[0].fields["interrupted"] == "false"
    assert exits[0].fields["ack_ok"] == "false"
    assert "venue rejected" in exits[0].fields["ack_detail"]


def test_THE_MARKER_IS_ARCHIVED_ONLY_AFTER_THE_ROWS_ARE_DURABLE(
    tmp_path: Path,
) -> None:
    """`enqueue` returns without durability by design. Archiving on it destroys
    the only record on the exact boot where the WAL then fails to reach disk."""
    marker = tmp_path / "marker.jsonl"
    MarkerWriter(marker).append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
    )
    plane1 = Plane1()

    _cold(marker, plane1).replay_sentinel_marker(now=9999.0)

    assert plane1.calls[-1] == "sync", plane1.calls
    assert not marker.exists()
    assert list(tmp_path.glob("marker.jsonl.*.replayed"))


def test_NON_FLATTEN_WAKES_ARE_COUNTED_and_NOT_booked_as_exits(
    tmp_path: Path,
) -> None:
    """A wake that did not flatten is not a flatten. Putting it in §9's money
    record under an exit kind would place a non-event in the ledger."""
    marker = tmp_path / "marker.jsonl"
    MarkerWriter(marker).append(
        _record(MarkerPhase.AFTER, TriggerCause.HEARTBEAT_LOST_NO_POSITIONS, symbols=())
    )
    plane1 = Plane1()

    rows = _cold(marker, plane1).replay_sentinel_marker(now=9999.0)

    assert len(rows) == 1, rows
    assert rows[0].fields["non_flatten_wakes"] == "1", rows[0].fields
    assert rows[0].fields["causes"] == "heartbeat_lost_no_positions"
    assert not any(r.fields.get("symbol") for r in rows)


def test_A_BOX_WITH_NO_MARKER_REPLAYS_NOTHING_and_that_is_NOT_an_error(
    tmp_path: Path,
) -> None:
    """The ordinary case: the Sentinel never fired."""
    plane1 = Plane1()

    rows = _cold(tmp_path / "absent.jsonl", plane1).replay_sentinel_marker(now=1.0)

    assert rows == ()
    assert plane1.calls == []


def test_REPLAY_IS_IDEMPOTENT_because_the_marker_is_archived(
    tmp_path: Path,
) -> None:
    """A second boot must not book the same emergency again; §9's log is
    append-only and two rows where one event happened is a corrupted ledger."""
    marker = tmp_path / "marker.jsonl"
    MarkerWriter(marker).append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST)
    )
    plane1 = Plane1()
    cold = _cold(marker, plane1)

    first = cold.replay_sentinel_marker(now=9999.0)
    second = cold.replay_sentinel_marker(now=10_000.0)

    assert first and second == ()
    assert len(plane1.rows) == len(first)


# ==========================================================================
# THE §0a FINDINGS — each of these controls exists because the first version
# of this module got the property WRONG, or never reached it at all
# ==========================================================================


def test_A_POSITION_THAT_APPEARS_AFTER_A_FLAT_ANSWER_IS_STILL_FLATTENED(
    tmp_path: Path,
) -> None:
    """THE HAZARD THIS ARC'S §0a AUDIT FOUND STATED BACKWARDS.

    The first version of `_no_positions` set the acted latch, on the reasoning
    that "the Limiter is dead, so nothing can have opened a new position". That
    reasoning is sound only AFTER a flatten has closed what was there, and it is
    exactly false here: an order in flight at the instant the Risk Engine died
    fills afterwards. A Sentinel that looked once, saw flat, and latched would
    ignore the resulting position for the rest of the episode — so the one case
    where re-asking the broker matters most was the one it stopped asking in.
    """
    broker = Broker(())
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0, hint=0)

    first = sentinel.poll(now=1000.0 + THRESHOLD + 1)
    broker.symbols = ("MES",)  # the in-flight order fills
    second = sentinel.poll(now=1000.0 + THRESHOLD + 2)

    assert first.cause is TriggerCause.HEARTBEAT_LOST_NO_POSITIONS
    assert not first.acted
    assert second.acted, second.detail
    assert second.symbols == ("MES",)
    assert broker.calls.count("open_positions") == 2, (
        "the Sentinel stopped asking the broker after a flat answer, which is the "
        f"latched-on-flat defect: {broker.calls}"
    )
    assert [r["phase"] for r in _marker(tmp_path)] == ["after", "before", "after"]


def test_THE_FLAT_ANSWER_IS_RECORDED_ONCE_PER_EPISODE_and_not_once_per_poll(
    tmp_path: Path,
) -> None:
    """The record latch that replaced the action latch. Restraint stays
    observable; the marker does not gain a line every quarter second."""
    broker = Broker(())
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0, hint=0)

    for step in range(5):
        sentinel.poll(now=1000.0 + THRESHOLD + 1 + step)

    assert [r["cause"] for r in _marker(tmp_path)] == ["heartbeat_lost_no_positions"]
    assert broker.calls.count("open_positions") == 5, broker.calls


def test_A_HEARTBEAT_THAT_VANISHES_AFTER_BEING_SEEN_IS_A_LOSS_not_a_cold_boot(
    tmp_path: Path,
) -> None:
    """`VANISHED` is a different observation from `NEVER_SEEN` and must not
    collapse into it: this watcher HAS evidence that a Limiter existed."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)
    sentinel.poll(now=1000.0)

    (tmp_path / "hb.json").unlink()
    gone = sentinel.poll(now=1000.0 + THRESHOLD + 1)

    assert gone.liveness is LivenessClass.VANISHED, gone.detail
    assert gone.cause is TriggerCause.HEARTBEAT_LOST
    assert gone.acted


def test_LOSS_FIRES_AT_THE_THRESHOLD_INSTANT_and_not_only_beyond_it(
    tmp_path: Path,
) -> None:
    """The boundary instant, driven. `>=` and `>` differ by exactly one moment,
    and a control that only ever tests `threshold + 1` never tells them apart."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=1000.0)

    just_inside = sentinel.poll(now=1000.0 + THRESHOLD - 0.001)
    at_boundary = sentinel.poll(now=1000.0 + THRESHOLD)

    assert just_inside.cause is None, just_inside.detail
    assert at_boundary.cause is TriggerCause.HEARTBEAT_LOST, at_boundary.detail


def test_ARCHIVING_A_MARKER_THAT_WAS_NEVER_WRITTEN_IS_A_NO_OP(
    tmp_path: Path,
) -> None:
    """The ordinary boot. Nothing fired, so there is nothing to retire, and that
    must not be an error on the one path every boot takes."""
    replay = MarkerReplay(tmp_path / "never.jsonl", clock=lambda: 1.0)

    replay.archive()

    assert list(tmp_path.iterdir()) == []


def test_AN_ACK_FOR_A_SYMBOL_THE_SENTINEL_DID_NOT_ENUMERATE_IS_STILL_BOOKED(
    tmp_path: Path,
) -> None:
    """A leg that opened between the position read and the send is the one thing
    an operator most needs to see, and a replay that booked only what was
    expected would drop exactly it."""
    marker = tmp_path / "marker.jsonl"
    writer = MarkerWriter(marker)
    writer.append(
        _record(MarkerPhase.BEFORE, TriggerCause.HEARTBEAT_LOST, symbols=("MES",))
    )
    writer.append(
        _record(
            MarkerPhase.AFTER,
            TriggerCause.HEARTBEAT_LOST,
            symbols=("MES",),
            acks=(
                BrokerAck("MES", True, "closed"),
                BrokerAck("MNQ", True, "closed a leg we had not enumerated"),
            ),
        )
    )
    plane1 = Plane1()

    rows = _cold(marker, plane1).replay_sentinel_marker(now=9999.0)

    booked = [r.fields["symbol"] for r in rows if r.fields.get("symbol")]
    assert booked == ["MES", "MNQ"], booked


def test_THE_RUN_LOOP_HANDS_THE_BROKER_SESSION_BACK(tmp_path: Path) -> None:
    """§12.1:605 gives the Sentinel its OWN session. One it never releases is one
    a restarted Risk Engine may find still held, which turns the separation into a
    different collision."""
    broker = Broker(("MES",))
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=0.0)

    wakes = sentinel.run_until(
        lambda seen: bool(seen) and seen[-1].cause is not None,
        sleep=lambda _s: None,
        max_wakes=5,
    )

    assert any(wake.acted for wake in wakes), [w.detail for w in wakes]
    assert broker.calls[-1] == "disconnect", broker.calls


def test_THE_RUN_LOOP_HANDS_THE_SESSION_BACK_EVEN_WHEN_A_WAKE_RAISES(
    tmp_path: Path,
) -> None:
    """The fault still propagates — §12.2's breaker decides what happens next —
    and the session is still released on the way out, because `disconnect` is
    declared never to raise and so cannot replace the fault being reported."""
    boom = RuntimeError("test: the venue never answered")
    broker = Broker(("MES",), boom=boom)
    sentinel = _sentinel(tmp_path, broker=broker)
    _beat(tmp_path, pid=100, seq_to=1, ts=0.0)

    with pytest.raises(RuntimeError) as caught:
        sentinel.run_until(lambda seen: False, sleep=lambda _s: None, max_wakes=5)

    assert "never answered" in str(caught.value), caught.value
    assert broker.calls[-1] == "disconnect", broker.calls


def test_A_MARKER_LINE_THAT_IS_NOT_AN_OBJECT_IS_REFUSED_by_shape(
    tmp_path: Path,
) -> None:
    """A JSON array is valid JSON and is not a record. Reading it positionally is
    how a replayer comes to book a flatten that never happened."""
    marker = tmp_path / "marker.jsonl"
    marker.write_text("[1, 2, 3]\n", encoding="utf-8")

    with pytest.raises(MarkerError) as caught:
        MarkerReplay(marker).read_pending()

    assert "record is list, expected an object" in str(caught.value), caught.value
