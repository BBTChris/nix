"""ARC 037 sub-agent D — the standing suite over `nixscore.liveness` and TRIGGER 6.

The subject is `docs/CHECK-DEBT.md` D3.244: **for `stale_after_s` after the
Scoring process dies, readers RANK on a corpse's frozen table.** ARC 036
measured 144,699 such arbitrations over a 0.483 s window at
`stale_after_s = 0.5`. The repair is an observation of the WRITER — libzmq's own
peer-disconnect event — carried alongside a §12.7 sequence deadline for the
publisher that is alive but wedged and therefore never disconnects.

Three kinds of test, and the split is the point:

* **REAL PROCESSES, REAL SIGNALS.** A real `scripts/nixscore/process.py` child
  is spawned, subscribed to, and `SIGKILL`ed; the assertions are over the
  KERNEL's reaped wait status and over what the shipped `RankingReader` decided
  after it. `EVENT_DISCONNECTED` cannot be produced by a fixture.

* **CAN-FAIL CONTROLS THAT PLANT A DEFECT.** Every control that matters here is
  paired with the same drive under a PLANTED break — the observer removed, the
  deadline removed, the latch inverted, the observer made to raise — and the
  paired assertion requires the RED, naming the condition. A control that cannot
  demonstrate its defect is blind, not passing.

* **THE INVARIANT THAT OUTRANKS THE SUBJECT.** §6.6:467 — *"Ranking is an
  optimization, never a safety gate: a scoring outage must NEVER halt order
  flow."* Liveness makes the fallback fire SOONER; it may never make it fail,
  raise, block or deny. Several tests below exist only to hold that line.

**Every control asserts the REASON** — the named condition in the verdict's own
text — never a boolean alone (check contract §18). A dead publisher, a wedged
one and a broken observer all reach `live is False`, and they are three
different incidents.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access,duplicate-code
# pylint: disable=use-implicit-booleaness-not-comparison
# `errors == []` asserts the TYPE and the emptiness together, the convention
# `scripts/tests/test_declarations.py` adopts: `not x` is also satisfied by
# `None`, so a drive that started returning None would pass a truthiness
# assertion while having measured nothing.
# `protected-access`: two tests reach `StateSubscriber._socket` to prove the new
# public `socket` property returns THAT object and not a copy. A public alias
# invented for the test would make the assertion vacuous.

from __future__ import annotations

import itertools
import json
import os
import signal
import subprocess  # nosec B404 - runs sys.executable on a fixed argv, no shell
import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixbus.statebus import StateSubscriber, endpoint_for
from nixscore.liveness import (
    SIGNAL_HEARTBEAT,
    SIGNAL_OBSERVER,
    SIGNAL_PEER,
    LivenessError,
    LivenessVerdict,
    PublisherLiveness,
)
from nixscore.process import SIGNALLED_EXIT

# ARC 037 STAGE 2 — the CROSS-BRANCH repair. Sub-agent D wrote this suite
# against `nixscore.process.RankingReader`; sub-agent F, in a worktree D
# could not see, deleted that class as CHECK-DEBT D3.271's duplicate and
# kept the survivor here. Both branches were green alone.
from nixscore.publisher import RankingReader
from nixscore.seam import RANKING_TOPIC, SEAM_REV, Arbitration, RankingMirror

FIRST = ("alpha", "ES")
SECOND = ("bravo", "ES")
STALE_AFTER_S = 0.5
REAP_TIMEOUT_S = 20.0


def _argv(endpoint: str, interval_s: float) -> list[str]:
    """argv for one Scoring child. Built here; never a shell string."""
    return [
        sys.executable,
        str(REPO / "scripts" / "nixscore" / "process.py"),
        "--endpoint",
        endpoint,
        "--interval-s",
        str(interval_s),
        "--score",
        f"{FIRST[0]},{FIRST[1]},900.0,14",
        "--score",
        f"{SECOND[0]},{SECOND[1]},100.0,11",
    ]


def _spawn(endpoint: str, interval_s: float = 0.05):
    """Start a real Scoring child and read its self-announcement."""
    # pylint: disable=consider-using-with
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        _argv(endpoint, interval_s),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=REAP_TIMEOUT_S)
        stderr = (proc.stderr.read() if proc.stderr else "")[:400]
        pytest.fail(f"Scoring child printed no announcement; stderr={stderr!r}")
    return proc, json.loads(line)


def _reader(endpoint: str, **kwargs) -> RankingReader:
    """A real subscriber on a real socket, wrapped in the SHIPPED reader."""
    return RankingReader(
        StateSubscriber(endpoint, [RANKING_TOPIC]),
        stale_after_s=STALE_AFTER_S,
        **kwargs,
    )


def _observer(reader: RankingReader) -> PublisherLiveness:
    """The reader's observer, narrowed. A reader built without one is a defect."""
    observer = reader.liveness
    assert isinstance(observer, PublisherLiveness), (
        f"reader has no liveness observer ({observer!r}) — the repair is not "
        "wired, and every assertion below would be measuring the unrepaired path"
    )
    return observer


def _warm(readers: list[RankingReader], budget_s: float = 5.0) -> bool:
    """Pump until every mirror is fresh. Returns whether all landed."""
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        for reader in readers:
            reader.pump(50)
        if all(reader.mirror.fresh() for reader in readers):
            return True
    return False


def _drive(readers: list[RankingReader], seconds: float) -> list[list[str]]:
    """Pump and arbitrate flat out. Returns one outcome list per reader."""
    out: list[list[str]] = [[] for _ in readers]
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        for index, reader in enumerate(readers):
            reader.pump(0)
            out[index].append(str(reader.arbitrate(FIRST, SECOND).outcome))
    return out


# ---------------------------------------------------------------------------
# THE SEAM'S SIXTH TRIGGER — pure, no transport
# ---------------------------------------------------------------------------


def _fed_mirror(now: float = 100.0) -> RankingMirror:
    """A mirror holding a fresh, complete, unambiguous table. The corpse state."""
    from nixbus.statebus import StateMessage
    from nixscore.seam import RankingSnapshot, rank_rows

    mirror = RankingMirror(stale_after_s=STALE_AFTER_S)
    snapshot = RankingSnapshot(
        rows=rank_rows({FIRST: 900.0, SECOND: 100.0}), span_days=10
    )
    mirror.apply(StateMessage(RANKING_TOPIC, snapshot.as_wire(), 1, now, True), now=now)
    return mirror


def test_seam_rev_moved_because_the_arbitration_contract_did() -> None:
    """A sixth FCFS trigger is a contract change, and the literal says so."""
    assert SEAM_REV == "1.1.0", (
        "seam.py's own rule is that SEAM_REV moves when the row shape OR the "
        "arbitration contract changes; TRIGGER 6 is the second"
    )


def test_an_unfed_mirror_behaves_exactly_as_seam_rev_1_0_0_did() -> None:
    """The DEFAULT must not turn §6.6's degraded mode into the only mode.

    The non-vacuity control at the smallest possible scale: a mirror nobody
    feeds liveness to still RANKS. Its can-fail twin is the next test.
    """
    mirror = _fed_mirror()
    assert mirror.liveness_fed == 0
    assert mirror.fresh(now=100.1) is True
    verdict = mirror.arbitrate(FIRST, SECOND, now=100.1)
    assert verdict.outcome is Arbitration.RANKED, verdict.reason


def test_trigger_six_is_the_only_thing_that_changed_the_verdict() -> None:
    """CAN-FAIL: the SAME complete, fresh, unambiguous table goes FCFS on a plant.

    Every other FCFS trigger is false here — the mirror is populated, both rows
    are present, the EMAs differ, the writer identity matches and the age is
    inside the threshold. That combination is exactly the RANKED-from-a-corpse
    state D3.244 measured, and only TRIGGER 6 can end it.
    """
    mirror = _fed_mirror()
    mirror.note_liveness(False, "PLANTED: the publisher's peer is GONE", SIGNAL_PEER)
    assert mirror.writer_live is False
    assert mirror.liveness_lost == 1
    assert mirror.fresh(now=100.1) is False, (
        "§6.6:465's fallback condition is 'the Scoring process is DOWN or its "
        "table is STALE' — fresh() must answer both halves"
    )
    verdict = mirror.arbitrate(FIRST, SECOND, now=100.1)
    assert verdict.outcome is Arbitration.FCFS
    assert verdict.winner == FIRST, "FCFS is the EARLIER ARRIVAL, always"
    assert "WRITER not live" in verdict.reason
    assert SIGNAL_PEER in verdict.reason, "§18: the reason must name WHICH signal"
    assert "PLANTED: the publisher's peer is GONE" in verdict.reason


def test_a_reason_less_note_still_produces_a_reason() -> None:
    """§18 forbids the outcome without the cause, including on the lazy call."""
    mirror = _fed_mirror()
    mirror.note_liveness(False)
    reason = mirror.arbitrate(FIRST, SECOND, now=100.1).reason
    assert reason.strip()
    assert "not live" in reason.lower()


def test_liveness_restored_ranks_again() -> None:
    """The bound is not a one-way latch: a relaunched writer must be believed."""
    mirror = _fed_mirror()
    mirror.note_liveness(False, "gone", SIGNAL_PEER)
    assert mirror.arbitrate(FIRST, SECOND, now=100.1).fell_back
    mirror.note_liveness(True, "peer attached", SIGNAL_PEER)
    assert mirror.arbitrate(FIRST, SECOND, now=100.1).outcome is Arbitration.RANKED
    assert mirror.liveness_lost == 1, "one FALSE edge, not two"


# ---------------------------------------------------------------------------
# THE STATEBUS ACCESSOR — the one thing added to shared transport
# ---------------------------------------------------------------------------


def test_subscriber_socket_property_is_the_socket_itself(tmp_path: Path) -> None:
    """The accessor hands out the real socket, and nothing else changed."""
    endpoint = endpoint_for("acc", tmp_path)
    subscriber = StateSubscriber(endpoint, [RANKING_TOPIC])
    try:
        assert subscriber.socket is subscriber._socket
        assert subscriber.received == 0 and subscriber.bytes_received == 0
    finally:
        subscriber.close()


def test_observer_refuses_a_subscriber_with_no_socket() -> None:
    """CAN-FAIL: an observer that cannot reach a socket must SAY so, not guess.

    A liveness observer built over something it cannot observe would report
    liveness it never measured, which is the vacuous shape this whole module
    exists to remove.
    """

    class Bare:  # pylint: disable=too-few-public-methods
        """A subscriber-shaped object with the accessor removed."""

    with pytest.raises(LivenessError) as caught:
        PublisherLiveness(Bare())
    assert "socket" in str(caught.value)


def test_observer_refuses_a_non_positive_deadline(tmp_path: Path) -> None:
    """CAN-FAIL: a deadline of zero reports every publisher wedged, forever."""
    endpoint = endpoint_for("bad", tmp_path)
    subscriber = StateSubscriber(endpoint, [RANKING_TOPIC])
    try:
        with pytest.raises(LivenessError) as caught:
            PublisherLiveness(subscriber, heartbeat_deadline_s=0.0)
        assert "only mode" in str(caught.value)
    finally:
        subscriber.close()


# ---------------------------------------------------------------------------
# THE KILL — a real death, watched two ways
# ---------------------------------------------------------------------------


def test_a_dead_publisher_goes_unranked_and_a_blind_reader_does_not(
    tmp_path: Path,
) -> None:
    """D3.244, driven: same socket, same death, one observing reader and one blind.

    The blind reader IS the can-fail control. It is the shipped code with the
    repair switched off, so if it also stopped ranking promptly there would be
    no defect here for the observer to have repaired, and this test would be
    green over nothing.
    """
    endpoint = endpoint_for("kill", tmp_path)
    proc, hello = _spawn(endpoint)
    seeing = _reader(endpoint)
    blind = _reader(endpoint, observe_liveness=False)
    try:
        assert _warm([seeing, blind]), "neither mirror ever went fresh"
        pre = _drive([seeing, blind], 0.15)
        assert pre[0].count("ranked") > 50, "the observing reader was never ranking"
        assert "fcfs" not in pre[0], "it was already falling back before the kill"

        os.kill(int(hello["pid"]), signal.SIGKILL)
        status = proc.wait(timeout=REAP_TIMEOUT_S)
        assert status == -int(signal.SIGKILL), (
            f"reaped {status!r}: only the kernel's wait status distinguishes a "
            "process that was KILLED from one that exited or never started"
        )
        post = _drive([seeing, blind], STALE_AFTER_S + 0.3)

        assert post[0], "no decisions were taken after the kill"
        assert post[0].count("ranked") <= 25, (
            f"{post[0].count('ranked')} arbitration(s) RANKED from a corpse's "
            "table — D3.244 exactly"
        )
        assert post[1].count("ranked") > 1000, (
            "the BLIND reader on the same socket ranked "
            f"{post[1].count('ranked')} time(s) from the same corpse — under "
            "1000 this run contained no defect to repair, so the observing "
            "reader's zero proves nothing"
        )
        assert _observer(seeing).disconnects >= 1
        assert seeing.mirror.liveness_lost >= 1
        assert seeing.mirror.writer_live is False
        verdict = _observer(seeing).verdict()
        assert verdict.live is False
        assert verdict.signal == SIGNAL_PEER
        assert "peer is GONE" in verdict.reason
    finally:
        if proc.poll() is None:  # pragma: no cover - only if the kill missed
            proc.kill()
            proc.wait(timeout=REAP_TIMEOUT_S)
        seeing.close()
        blind.close()


def test_order_flow_never_halts_across_the_death(tmp_path: Path) -> None:
    """§6.6:467 outranks everything this module is for. Measured, not asserted.

    Every arbitration across the death must ANSWER — never raise, never deny,
    never stall. The gap that straddles the kill instant is the one that
    matters, so it is the WORST gap that is asserted, never the mean.
    """
    endpoint = endpoint_for("flow", tmp_path)
    proc, hello = _spawn(endpoint)
    reader = _reader(endpoint)
    stamps: list[float] = []
    outcomes: list[str] = []
    errors: list[str] = []
    try:
        assert _warm([reader])
        until = time.monotonic() + 0.15
        while time.monotonic() < until:
            reader.pump(0)
            outcomes.append(str(reader.arbitrate(FIRST, SECOND).outcome))
            stamps.append(time.monotonic())
        os.kill(int(hello["pid"]), signal.SIGKILL)
        assert proc.wait(timeout=REAP_TIMEOUT_S) == -int(signal.SIGKILL)
        until = time.monotonic() + 0.6
        while time.monotonic() < until:
            reader.pump(0)
            try:
                outcomes.append(str(reader.arbitrate(FIRST, SECOND).outcome))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
            stamps.append(time.monotonic())
    finally:
        if proc.poll() is None:  # pragma: no cover
            proc.kill()
            proc.wait(timeout=REAP_TIMEOUT_S)
        reader.close()
    assert errors == [], (
        f"the order path raised {errors!r}. An exception out of the fallback is "
        "a stall wearing a traceback"
    )
    assert len(outcomes) > 200
    assert set(outcomes) <= {"ranked", "fcfs"}, "§6.6 allows exactly two outcomes"
    worst = max(b - a for a, b in itertools.pairwise(stamps))
    assert worst < 0.5, f"worst inter-decision gap {worst:.3f}s — order flow stalled"


def test_a_healthy_publisher_stays_live_and_ranked(tmp_path: Path) -> None:
    """NON-VACUITY. A bound that never lets anything be ranked is the worse defect."""
    endpoint = endpoint_for("ok", tmp_path)
    proc, _hello = _spawn(endpoint)
    reader = _reader(endpoint)
    try:
        assert _warm([reader])
        outcomes = _drive([reader], 0.3)[0]
        assert proc.poll() is None, "the healthy publisher did not survive the arm"
        assert outcomes.count("fcfs") == 0, (
            f"{outcomes.count('fcfs')} FCFS verdict(s) against a LIVE publisher — "
            "the liveness bound has turned degraded mode into the only mode"
        )
        assert outcomes.count("ranked") > 200
        assert reader.mirror.liveness_fed > 0, "the mirror was never fed"
        assert reader.mirror.liveness_lost == 0
        verdict = _observer(reader).verdict()
        assert verdict.live is True
        assert "peer is attached" in verdict.reason
    finally:
        reader.close()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=REAP_TIMEOUT_S) == SIGNALLED_EXIT


def test_the_reader_re_acquires_when_scoring_relaunches(tmp_path: Path) -> None:
    """CAN-FAIL for the latch: a one-way bound would leave every consumer on FCFS.

    The reader is NOT restarted and NOT resubscribed. If the liveness latch
    could not clear, an operator restarting Scoring would leave the whole system
    degraded permanently and silently.
    """
    endpoint = endpoint_for("again", tmp_path)
    proc, hello = _spawn(endpoint)
    reader = _reader(endpoint)
    second = None
    try:
        assert _warm([reader])
        os.kill(int(hello["pid"]), signal.SIGKILL)
        assert proc.wait(timeout=REAP_TIMEOUT_S) == -int(signal.SIGKILL)
        assert _drive([reader], 0.1)[0].count("ranked") <= 25
        second, _hello2 = _spawn(endpoint)
        deadline = time.monotonic() + 5.0
        regained = None
        while time.monotonic() < deadline:
            reader.pump(0)
            if reader.arbitrate(FIRST, SECOND).outcome is Arbitration.RANKED:
                regained = time.monotonic()
                break
        assert regained is not None, (
            "the un-restarted reader never RANKED again after Scoring relaunched "
            "— the liveness latch is one-way"
        )
        assert _observer(reader).connects >= 1
    finally:
        reader.close()
        for child in (proc, second):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=REAP_TIMEOUT_S)


# ---------------------------------------------------------------------------
# THE SECOND SIGNAL — alive, connected, and not publishing
# ---------------------------------------------------------------------------


def test_a_wedged_publisher_trips_the_heartbeat_and_not_the_peer(
    tmp_path: Path,
) -> None:
    """The failure mode signal 1 is blind to, with the control that proves it.

    The child is spawned with a publish interval far longer than the drive, so
    it binds, publishes once, and then sits alive in its loop without ever
    advancing §12.7's `_seq`. Nothing disconnects. The control reader — same
    publisher, deadline disabled — must still be RANKING, or something other
    than the heartbeat ended the watched reader's ranking.
    """
    endpoint = endpoint_for("wedge", tmp_path)
    proc, _hello = _spawn(endpoint, interval_s=60.0)
    watched = _reader(endpoint, heartbeat_deadline_s=0.15)
    control = _reader(endpoint)
    try:
        assert _warm([watched, control])
        outcomes = _drive([watched, control], 0.35)
        assert proc.poll() is None, "the wedged publisher DIED — signal 1 could see it"
        assert _observer(watched).peer_observed is True, (
            "the PEER signal fired on a publisher that never disconnected"
        )
        verdict = _observer(watched).verdict()
        assert verdict.live is False
        assert verdict.signal == SIGNAL_HEARTBEAT
        assert "WEDGED" in verdict.reason
        assert "sequence" in verdict.reason
        assert outcomes[0].count("fcfs") > 100
        assert "wedged" in _first_fcfs_reason(watched)
        assert outcomes[1].count("fcfs") == 0, (
            "the control reader on the SAME wedged publisher also fell back, so "
            "the watched reader's fallback is not attributable to the deadline"
        )
        assert outcomes[1].count("ranked") > 100
        assert _observer(control).verdict().live is True
        assert watched.mirror.lookup(*FIRST) is not None, (
            "the wedged mirror lost its rows, so this measured the absent-table "
            "trigger rather than the wedge"
        )
    finally:
        watched.close()
        control.close()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=REAP_TIMEOUT_S) == SIGNALLED_EXIT


def _first_fcfs_reason(reader: RankingReader) -> str:
    """The reason the reader would give right now, lower-cased. §18's artifact."""
    return reader.arbitrate(FIRST, SECOND).reason.lower()


def test_the_heartbeat_is_bounded_far_tighter_than_stale_after_s(
    tmp_path: Path,
) -> None:
    """The second signal must beat the clock, or it is the clock with a new name."""
    endpoint = endpoint_for("tight", tmp_path)
    proc, _hello = _spawn(endpoint, interval_s=60.0)
    watched = _reader(endpoint, heartbeat_deadline_s=0.15)
    try:
        assert _warm([watched])
        landed = None
        deadline = time.monotonic() + STALE_AFTER_S
        started = time.monotonic()
        while time.monotonic() < deadline:
            watched.pump(0)
            if watched.arbitrate(FIRST, SECOND).fell_back:
                landed = time.monotonic() - started
                break
        assert landed is not None, "the heartbeat never fired inside stale_after_s"
        assert landed < STALE_AFTER_S / 2, (
            f"the wedge was detected after {landed:.3f}s, which is not tighter "
            f"than the {STALE_AFTER_S}s freshness threshold in any useful sense"
        )
        table_age = watched.mirror.age_s()
        assert table_age is not None and table_age < STALE_AFTER_S, (
            "the table had already aged past the threshold, so the CLOCK could "
            "have produced this fallback and the heartbeat proved nothing"
        )
    finally:
        watched.close()
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=REAP_TIMEOUT_S)


# ---------------------------------------------------------------------------
# THE OBSERVER IS THE NEW FAILURE MODE
# ---------------------------------------------------------------------------


class _Exploding:
    """An observer whose `observe()` always raises. Delegates everything else."""

    def __init__(self, real: PublisherLiveness) -> None:
        self._real = real
        self.calls = 0

    def note_message(self, seq: int = -1) -> None:
        """Delegate, so the mirror still fills and the table is still present."""
        self._real.note_message(seq)

    def observe(self) -> int:
        """Always raises. The whole point."""
        self.calls += 1
        raise RuntimeError("planted liveness observer failure")

    def note_observe_error(self, exc: BaseException) -> None:
        """Delegate, so the SHIPPED latch is what produces the verdict."""
        self._real.note_observe_error(exc)

    def verdict(self, now: float | None = None) -> LivenessVerdict:
        """Delegate to the shipped verdict logic."""
        return self._real.verdict(now)

    def close(self) -> None:
        """Delegate teardown, so the monitor socket is still released."""
        self._real.close()


def test_an_observer_that_raises_leaves_order_flow_running(tmp_path: Path) -> None:
    """§6.6:467, held against the mechanism this arc ADDED.

    A liveness observer built to make an outage visible sooner must not become a
    new way for order flow to stop. Fail CLOSED — to FCFS, which is a decision —
    and never to a raise, a stall or a deny.
    """
    endpoint = endpoint_for("boom", tmp_path)
    proc, _hello = _spawn(endpoint)
    subscriber = StateSubscriber(endpoint, [RANKING_TOPIC])
    observer = _Exploding(PublisherLiveness(subscriber))
    reader = RankingReader(subscriber, stale_after_s=STALE_AFTER_S, liveness=observer)
    outcomes: list[str] = []
    errors: list[str] = []
    try:
        until = time.monotonic() + 0.2
        while time.monotonic() < until:
            reader.pump(0)
            try:
                outcomes.append(str(reader.arbitrate(FIRST, SECOND).outcome))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
        verdict = observer.verdict()
    finally:
        reader.close()
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=REAP_TIMEOUT_S)
    assert observer.calls > 0, "nothing raised, so this measured the healthy path"
    assert errors == [], (
        f"the ORDER PATH raised {errors!r} because the liveness observer did"
    )
    assert len(outcomes) > 50
    assert outcomes.count("ranked") == 0, (
        "the reader kept RANKING while its liveness observer was blind — "
        "directive 4 is fail CLOSED"
    )
    assert reader.liveness_errors, "the shipped pump caught nothing"
    assert verdict.live is False
    assert verdict.signal == SIGNAL_OBSERVER
    assert "RuntimeError" in verdict.reason, (
        "§18: the reason must name the exception, not merely report 'not live'"
    )


def test_close_is_idempotent_and_does_not_hang(tmp_path: Path) -> None:
    """MEASURED: a leaked monitor socket makes `Context.term()` block forever.

    The failure this guards is a hang, so the assertion is that the call
    RETURNS — pytest's own timeout is what would catch the regression.
    """
    endpoint = endpoint_for("td", tmp_path)
    subscriber = StateSubscriber(endpoint, [RANKING_TOPIC])
    observer = PublisherLiveness(subscriber)
    observer.close()
    observer.close()
    subscriber.close()


def test_a_message_cannot_resurrect_a_latched_disconnect(tmp_path: Path) -> None:
    """CAN-FAIL for the latch's direction. Buffered bytes are not a live writer.

    `note_message` promotes only the NEVER-OBSERVED state. If it could clear a
    latched `False`, a message that was already in the subscriber's buffer when
    the publisher died would put the mirror straight back into the corpse state
    the disconnect had just ended.
    """
    endpoint = endpoint_for("latch", tmp_path)
    subscriber = StateSubscriber(endpoint, [RANKING_TOPIC])
    observer = PublisherLiveness(subscriber)
    try:
        observer.note_message(1)
        assert observer.peer_observed is True
        observer._peer = False  # the latch a DISCONNECT would have set
        observer.note_message(2)
        assert observer.peer_observed is False, (
            "a buffered message cleared a latched disconnect — the corpse state "
            "is reachable again"
        )
        assert observer.verdict().signal == SIGNAL_PEER
    finally:
        observer.close()
        subscriber.close()


def test_a_never_attached_publisher_is_not_reported_as_GONE(tmp_path: Path) -> None:
    """CHECK-DEBT D3.318: a §18 reason must not contradict its own count.

    A subscriber connected before any publisher binds latches `_peer = False`
    off `CONNECT_DELAYED`/`CONNECT_RETRIED`. The verdict is FCFS either way and
    correctly so — what must be right is what an operator is told, and "GONE …
    after 0 disconnect(s)" is a sentence falsified by a number inside it.
    """
    endpoint = endpoint_for("cold", tmp_path)
    reader = _reader(endpoint)
    try:
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            reader.pump(0)
        verdict = _observer(reader).verdict()
        assert verdict.live is False
        assert verdict.signal == SIGNAL_PEER
        assert _observer(reader).disconnects == 0
        assert "NEVER been attached" in verdict.reason
        assert "GONE" not in verdict.reason, (
            f"a cold start was reported as a death: {verdict.reason!r}"
        )
        assert reader.arbitrate(FIRST, SECOND).outcome is Arbitration.FCFS
    finally:
        reader.close()


def test_the_fallback_alarm_names_which_half_of_6_6_465_fired(tmp_path: Path) -> None:
    """§12.9: the alert carries the CAUSE, and there are two causes.

    *"the Scoring process is DOWN or its table is STALE"* is two conditions.
    An operator paged with an age and no verdict cannot tell a dead process from
    a slow one, and those are different incidents.
    """
    from nixscore.process import (
        SCORING_DOWN_CODE,
        FallbackAlarm,
        RecordingAlertSink,
    )

    endpoint = endpoint_for("alarm", tmp_path)
    proc, hello = _spawn(endpoint)
    reader = _reader(endpoint)
    sink = RecordingAlertSink()
    alarm = FallbackAlarm(reader.mirror, alert=sink)
    try:
        assert _warm([reader])
        alarm.poll()
        assert sink.codes() == (), "the first observation is a baseline, not an edge"
        os.kill(int(hello["pid"]), signal.SIGKILL)
        assert proc.wait(timeout=REAP_TIMEOUT_S) == -int(signal.SIGKILL)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not sink.codes():
            reader.pump(0)
            alarm.poll()
        assert sink.codes() == (SCORING_DOWN_CODE,)
        message = sink.alerts[0][1]
        assert "deciding condition is the WRITER's liveness" in message, message
        assert f"[{SIGNAL_PEER}]" in message, message
        for token in ("threshold", "snapshot", "age"):
            assert token in message.lower(), f"§12.9 omits {token!r}: {message!r}"
    finally:
        if proc.poll() is None:  # pragma: no cover
            proc.kill()
            proc.wait(timeout=REAP_TIMEOUT_S)
        reader.close()
