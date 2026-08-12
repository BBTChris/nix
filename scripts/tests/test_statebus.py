"""ARC 026 — the properties `scripts/nixbus/statebus.py` claims (§12.7).

What each test proves:

* **Endpoints.** `endpoint_for` returns an `ipc://` URL and CREATES the directory
  it names; `bus_root(None)` with `XDG_RUNTIME_DIR` unset REFUSES to guess and
  names the variable; an over-long path is refused with the AF_UNIX byte limit in
  the message rather than reaching libzmq as a bare `Invalid argument`.
* **THE HEADLINE (§12.7's mandatory mechanism).** A subscriber that connects
  AFTER the only publication still receives the current table, as a **snapshot**,
  with the payload intact — because `service()` answered its subscription.
* **THE CONTROL.** The identical setup with `service()` never called delivers
  NOTHING. Without this arm the headline would only prove that a message can
  travel; with it, the snapshot is attributable to the mechanism.
* **Transport metadata stays out of the table.** `_kind`/`_seq`/`_stamp` ride the
  `StateMessage` and never appear in the mirrored table — a `_seq` key inside a
  mirror is transport bookkeeping masquerading as state the owner never had.
* **A delta never completes a mirror.** Fed only deltas a `Mirror` reports
  `.stale` and NAMES the missing topic; a snapshot completes it.
* **Out-of-order is counted, not hidden**, and never applied.
* **`Mirror.table()` is a COPY** — a consumer cannot write the mirror it must not
  write.
* **XPUB_VERBOSE.** A SECOND subscriber to an ALREADY-subscribed topic is served
  too, which plain first-subscribe-only delivery would silently skip — with a
  CAN-FAIL arm that plants the real defect (the option cleared) on a throwaway
  socket and requires the control to go red NAMING the unserved subscriber.

Every publisher and subscriber is closed in a fixture `finally`; a leaked socket
hangs `Context.term()` and the suite with it. All endpoints live under `tmp_path`;
nothing here touches `$XDG_RUNTIME_DIR` or any production socket.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access
# `protected-access`: a can-fail control drives the gate's ARMS, which are
# private by design — an arm made public so a test could reach it would be a
# surface the gate did not need, invented for the test. Doctrine C.8 says the
# plant must not touch the production artifact; it does not say the test may
# only use the public API.
# Test names SHOUT the property; the closing fixture is reused by design; the
# sys.path bootstrap is shared with the sibling suites. Each deliberate.

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

import pytest  # pylint: disable=import-error
import zmq  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixbus import statebus  # pylint: disable=wrong-import-position
from nixbus.statebus import (  # pylint: disable=wrong-import-position
    Mirror,
    StateBusError,
    StateMessage,
)

#: Budget the publisher spends answering subscriptions. `service()` spends its
#: whole timeout only while NOTHING has been served: it returns the instant it
#: answers a subscription (`statebus.py`, `if served or time.monotonic() >=
#: deadline`). So this is a per-call cost for an idle publisher and a bound for a
#: busy one — and it is emphatically NOT "wait `SERVICE_MS` for every pending
#: subscribe to arrive". See `_serve_until_MIRRORED` for what that cost me.
SERVICE_MS = 500
#: Budget a subscriber waits for a message it SHOULD get. `drain()` always
#: spends its whole budget proving nothing more is coming, so this is a cost.
POLL_MS = 800
#: Budget the CONTROL waits for a message it must NOT get.
CONTROL_MS = 400

#: Ceiling on ONE subscriber's rendezvous with the publisher. ARRIVAL ends that
#: wait; this number only bounds a bus that is BROKEN rather than slow, which is
#: why it can afford to be enormous. MEASURED on this node 2026-08-12 — time for
#: BOTH subscribes to be answered, worst case of each run:
#:
#:     at rest                          2.3 ms  (median 2.2, n=40)
#:     40 spinners / 20 cores          14.5 ms  (median  8.4, n=40)
#:     80 spinners / 20 cores          30.1 ms  (median 17.9, n=30, load avg 110)
#:
#: Quadrupling the load doubled the worst case; ten seconds is 332x the worst
#: ever observed, so a red here is a defect and never a busy machine.
RENDEZVOUS_CEILING_MS = 10_000
#: Ceiling for the PLANTED arm only. A shorter ceiling is honest there because
#: the planted failure is PERMANENT, not slow: with `XPUB_VERBOSE` cleared the
#: second subscribe never reaches the application at all, so no snapshot is ever
#: emitted for it and waiting the full ceiling would only add ten seconds of
#: certainty to a wait that is already 100x the measured healthy arrival.
PLANT_CEILING_MS = 2_000
#: One pump inside a ceiling: answer whatever subscriptions have landed, then
#: let the subscriber take whatever that produced. Neither slice is a deadline —
#: they are the granularity at which arrival is re-tested.
PUMP_SERVICE_MS = 50
PUMP_DRAIN_MS = 20

TOPIC = "tbl.feed_status"


class _Closable(Protocol):  # pylint: disable=too-few-public-methods
    """Anything the fixture must release. Both bus ends satisfy it."""

    def close(self) -> None:
        """Release the socket, and the context if the object owns one."""


@pytest.fixture
def closing() -> Iterator[list[_Closable]]:
    """Every socket opened by a test is closed here, even when it fails."""
    opened: list[_Closable] = []
    try:
        yield opened
    finally:
        for item in reversed(opened):
            item.close()


def _endpoint(tmp_path: Path, name: str = "b") -> str:
    """A short `ipc://` endpoint under `tmp_path` — AF_UNIX has 108 bytes."""
    return statebus.endpoint_for(name, tmp_path)


def _message(topic: str, payload: dict[str, Any], seq: int, *, snapshot: bool):
    """One decoded update, built directly — the `Mirror` arms need no socket."""
    return StateMessage(
        topic=topic, payload=payload, seq=seq, stamp=time.time(), snapshot=snapshot
    )


# --- endpoints -------------------------------------------------------------


def test_endpoint_for_returns_an_IPC_URL_and_CREATES_the_directory(
    tmp_path: Path,
) -> None:
    """The directory is a side effect the caller depends on, so it is asserted."""
    root = tmp_path / "bus"
    assert not root.exists()

    endpoint = statebus.endpoint_for("cap", root)

    assert endpoint.startswith("ipc://"), endpoint
    assert endpoint.endswith("/cap.ipc"), endpoint
    assert root.is_dir(), f"{root} was not created"


def test_bus_root_with_XDG_RUNTIME_DIR_UNSET_refuses_and_NAMES_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plant: the variable removed. Unplanted by monkeypatch at teardown."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    with pytest.raises(StateBusError, match="XDG_RUNTIME_DIR is unset"):
        statebus.bus_root(None)


def test_an_EXPLICIT_ROOT_is_honoured_even_with_XDG_RUNTIME_DIR_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unplant of the arm above: the refusal is about guessing, not about roots."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    assert statebus.bus_root(tmp_path) == tmp_path


def test_an_OVERLONG_IPC_PATH_is_refused_NAMING_the_AF_UNIX_BYTE_LIMIT(
    tmp_path: Path,
) -> None:
    """libzmq answers `Invalid argument`; this layer answers with the number."""
    deep = tmp_path / ("x" * 60) / ("y" * 60)

    with pytest.raises(StateBusError, match="over the 100-byte") as refusal:
        statebus.endpoint_for("t", deep)

    assert "AF_UNIX limit" in str(refusal.value), str(refusal.value)
    assert str(deep) in str(refusal.value), str(refusal.value)


# --- THE HEADLINE and THE CONTROL ------------------------------------------


def test_a_LATE_SUBSCRIBER_receives_the_CURRENT_TABLE_as_a_SNAPSHOT(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """§12.7's mandatory mechanism: subscribe after the fact, get current state."""
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    payload = {"MESU6": {"tick": "fresh", "poll": "stale"}}
    publisher.publish(TOPIC, payload)

    # Connects AFTER the only publication. Plain PUB/SUB would leave it empty.
    subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(subscriber)
    served = publisher.service(SERVICE_MS)

    assert served == 1, f"the publisher answered {served} subscription(s), wanted 1"
    assert publisher.subscribes_seen == 1, publisher.subscribes_seen
    message = subscriber.poll(POLL_MS)
    assert message is not None, "the late subscriber received nothing"
    assert message.snapshot is True, "a delta would not rebuild a mirror"
    assert message.topic == TOPIC, message.topic
    assert message.payload == payload, message.payload
    assert subscriber.bytes_received > 0, "zero wire bytes is a vacuous pass"
    assert subscriber.mirror.complete, subscriber.mirror.missing


def test_the_CONTROL_without_service_the_late_subscriber_gets_NOTHING(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """Identical setup, `service()` never called. This is what attributes the
    snapshot above to the mechanism rather than to PUB/SUB delivery."""
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    publisher.publish(TOPIC, {"MESU6": {"tick": "fresh"}})

    subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(subscriber)
    # No publisher.service(...) — the subscription is never answered.

    assert subscriber.poll(CONTROL_MS) is None, "state arrived with no mechanism"
    assert subscriber.received == 0, subscriber.received
    assert subscriber.bytes_received == 0, subscriber.bytes_received
    assert publisher.snapshots_served == 0, publisher.snapshots_served
    assert subscriber.mirror.stale is True, "an unfed mirror must read stale"
    assert subscriber.mirror.missing == (TOPIC,), subscriber.mirror.missing


def test_TRANSPORT_METADATA_rides_the_MESSAGE_and_never_the_TABLE(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """`_kind`/`_seq`/`_stamp` are bookkeeping; a mirror is the OWNER's table."""
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    publisher.publish(TOPIC, {"MESU6": {"tick": "fresh"}})
    subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(subscriber)
    publisher.service(SERVICE_MS)

    message = subscriber.poll(POLL_MS)

    assert message is not None, "nothing to inspect — the arm would be vacuous"
    # ON the message:
    assert message.seq > 0, message.seq
    assert message.stamp > 0.0, message.stamp
    assert message.snapshot is True
    assert message.age_s >= 0.0, message.age_s
    # NOT in the table, at any depth the mirror exposes:
    for key in ("_kind", "_seq", "_stamp"):
        assert key not in message.payload, f"{key} leaked into the payload"
        assert key not in subscriber.mirror.table(TOPIC), f"{key} leaked into mirror"
    assert dict(subscriber.mirror.table(TOPIC)) == {"MESU6": {"tick": "fresh"}}


def _serve_until_MIRRORED(
    publisher: statebus.StatePublisher,
    name: str,
    subscriber: statebus.StateSubscriber,
    *,
    ceiling_ms: int = RENDEZVOUS_CEILING_MS,
) -> tuple[int, float]:
    """Pump both ends until `name`'s mirror completes. ARRIVAL is the terminator.

    Returns `(snapshots served, seconds waited)`. Raises `AssertionError` NAMING
    the subscriber that went unserved, how long it waited, and what its mirror is
    still missing — the reason, never a bare count.

    Why this exists (CHECK-DEBT D3.39). The arm below used to call
    `publisher.service(SERVICE_MS)` ONCE and assert the return was 2, on the
    belief that 500 ms was a budget within which both subscribes would arrive. It
    is not a budget: `service()` returns the instant it answers ANY subscription,
    so the single call captured only whichever subscribe frames happened to be
    queued at that microsecond. MEASURED 2026-08-12, 40 rendezvous each:

        at rest               single service(500) returned <2 in   2/40
        40 spinners/20 cores  single service(500) returned <2 in  26/40
        80 spinners/20 cores  single service(500) returned <2 in  22/30

    and in EVERY one of those 50 short calls `service()` had returned after
    0.1–23.6 ms — never near 500 ms. The clock was never the constraint, so
    raising the number would have fixed nothing; the missing subscribe had simply
    not landed yet and arrived, in the worst case observed, 30.1 ms in. Polling
    for arrival removes the race outright rather than out-running it.

    The shipped test failed 10/20 runs under the 40-spinner load, reproducing
    `1 snapshot(s) for 2 subscribers` exactly as CHECK-DEBT D3.39 reported.
    """
    started = time.monotonic()
    deadline = started + ceiling_ms / 1000.0
    served = 0
    while True:
        served += publisher.service(PUMP_SERVICE_MS)
        subscriber.drain(PUMP_DRAIN_MS)
        waited = time.monotonic() - started
        if subscriber.mirror.complete:
            return served, waited
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"the {name} subscriber went UNSERVED: it waited "
                f"{waited * 1000:.0f} ms of a {ceiling_ms} ms ceiling and its "
                f"mirror is still missing {subscriber.mirror.missing}; it took "
                f"{subscriber.received} message(s) / {subscriber.bytes_received} "
                f"wire byte(s), while the publisher saw "
                f"{publisher.subscribes_seen} subscribe frame(s) and served "
                f"{publisher.snapshots_served} snapshot(s) in total. A subscribe "
                f"frame that never reached the application is the signature of "
                f"XPUB_VERBOSE being unset"
            )


def test_TWO_SUBSCRIBERS_are_BOTH_served_because_XPUB_VERBOSE_is_set(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """A second subscribe on an ALREADY-subscribed topic is still answered.

    Without `XPUB_VERBOSE` libzmq delivers only the FIRST subscribe for a topic,
    so the second dashboard mirrors an empty table forever — a failure that looks
    exactly like a quiet feed.

    The staging is SEQUENTIAL — `first` is served to completion BEFORE `second`
    connects — and that is load-bearing, not tidiness. MEASURED 2026-08-12 with
    the option deliberately cleared: two subscribers connected back-to-back and
    then serviced BOTH complete their mirrors anyway, because the one snapshot
    the single delivered subscribe produces is fanned out by PUB/SUB to every
    peer already connected. Only once the topic is already subscribed AND already
    answered does the swallowed second subscribe leave a subscriber with nothing:
    `second.received == 0`, `bytes_received == 0`, mirror missing forever. The
    can-fail arm below is that measurement, planted.
    """
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    publisher.publish(TOPIC, {"MESU6": {"tick": "fresh"}})

    first = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(first)
    served_first, _ = _serve_until_MIRRORED(publisher, "first", first)

    # ONLY NOW does the second join. The topic is already subscribed and already
    # answered, which is the exact state first-subscribe-only delivery swallows.
    second = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(second)
    served_second, _ = _serve_until_MIRRORED(publisher, "second", second)

    served = served_first + served_second
    assert served == 2, f"{served} snapshot(s) for 2 subscribers"
    assert publisher.subscribes_seen == 2, publisher.subscribes_seen
    for name, subscriber in (("first", first), ("second", second)):
        assert subscriber.mirror.complete, f"{name}: {subscriber.mirror.missing}"
        assert subscriber.received > 0, f"the {name} subscriber received nothing"
        assert subscriber.bytes_received > 0, f"{name}: zero wire bytes is vacuous"


def test_the_CAN_FAIL_arm_XPUB_VERBOSE_CLEARED_leaves_the_SECOND_UNSERVED(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """Plant the REAL defect and require the control above to go red, by name.

    Doctrine C.8: the plant never touches the production artifact. `XPUB_VERBOSE`
    is cleared here on THIS TEST'S OWN throwaway socket — `scripts/nixbus/
    statebus.py` still sets it, unconditionally, for every publisher anyone else
    builds. Clearing it on a live bound XPUB is exactly the defect's shape:
    libzmq forwards a subscribe up to the application only for the first peer to
    subscribe a given topic.

    Both halves are here. PLANTED, the arm must fail AND name `second`. UNPLANTED
    — the option restored on the same socket, a third subscriber joining the same
    already-subscribed topic — it must pass, which is what attributes the red to
    the plant rather than to the harness, the ceiling, or the machine.
    """
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    publisher._socket.setsockopt(zmq.XPUB_VERBOSE, 0)  # THE PLANT
    publisher.publish(TOPIC, {"MESU6": {"tick": "fresh"}})

    first = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(first)
    _serve_until_MIRRORED(publisher, "first", first)
    second = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(second)

    with pytest.raises(AssertionError) as red:
        _serve_until_MIRRORED(publisher, "second", second, ceiling_ms=PLANT_CEILING_MS)

    # The REASON, not merely that something raised: the arm names the subscriber
    # that went unserved, what it is missing, and that it took nothing at all.
    assert "the second subscriber went UNSERVED" in str(red.value), str(red.value)
    assert TOPIC in str(red.value), str(red.value)
    assert "0 message(s) / 0 wire byte(s)" in str(red.value), str(red.value)
    assert publisher.subscribes_seen == 1, "the plant did not swallow a subscribe"

    # UNPLANT, same socket, same already-subscribed topic.
    publisher._socket.setsockopt(zmq.XPUB_VERBOSE, 1)
    third = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(third)

    served, _ = _serve_until_MIRRORED(publisher, "third", third)

    assert served == 1, served
    assert publisher.subscribes_seen == 2, publisher.subscribes_seen
    assert third.mirror.complete, third.mirror.missing
    assert third.bytes_received > 0, "zero wire bytes is a vacuous unplant"


def test_refresh_all_RESENDS_every_owned_table_as_a_SNAPSHOT(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """§12.7's periodic full-state refresh, separate from snapshot-on-subscribe.

    The `service()` call BEFORE the publish is the slow-joiner rendezvous, and it
    is here because it is a real property of the transport: a delta emitted
    before a subscription has propagated to the publisher is DROPPED, silently,
    by plain PUB/SUB. That is precisely §12.7's argument for snapshots, and this
    arm needs the delta to arrive in order to prove the delta does not complete
    the mirror.
    """
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
    closing.append(subscriber)
    assert publisher.service(SERVICE_MS) == 0, "no table exists to snapshot yet"
    assert publisher.subscribes_seen == 1, "the subscription never propagated"

    publisher.publish(TOPIC, {"MESU6": {"tick": "fresh"}})
    assert subscriber.drain(POLL_MS), "the delta never arrived — arm is vacuous"
    assert subscriber.mirror.stale is True, "a delta must not complete a mirror"

    resent = publisher.refresh_all()

    assert resent == 1, resent
    assert publisher.topics == (TOPIC,), publisher.topics
    messages = subscriber.drain(POLL_MS)
    assert [m.snapshot for m in messages] == [True], messages
    assert subscriber.mirror.complete, subscriber.mirror.missing


def test_publish_REPLACES_the_owned_table_rather_than_MERGING_into_it(
    tmp_path: Path, closing: list[_Closable]
) -> None:
    """An atomic snapshot: never a table assembled from fragments."""
    endpoint = _endpoint(tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)

    publisher.publish(TOPIC, {"MESU6": {"tick": "fresh"}})
    publisher.publish(TOPIC, {"MNQU6": {"tick": "stale"}})

    assert dict(publisher.table(TOPIC)) == {"MNQU6": {"tick": "stale"}}


# --- the Mirror, driven directly -------------------------------------------


def test_a_mirror_fed_ONLY_DELTAS_is_STALE_and_NAMES_the_missing_topic() -> None:
    """§12.7: incomplete => stale => fast-drop, until the SNAPSHOT lands."""
    mirror = Mirror([TOPIC])

    mirror.apply(_message(TOPIC, {"MESU6": {"tick": "fresh"}}, 1, snapshot=False))

    assert mirror.stale is True, "a delta completed a mirror"
    assert mirror.complete is False
    assert mirror.missing == (TOPIC,), mirror.missing
    assert mirror.applied == 1, mirror.applied
    # Unplant: the snapshot arrives and the same mirror completes.
    mirror.apply(_message(TOPIC, {"MESU6": {"tick": "fresh"}}, 2, snapshot=True))
    assert mirror.complete is True, mirror.missing
    assert mirror.stale is False
    assert not mirror.missing, f"still missing {mirror.missing}"


def test_an_OUT_OF_ORDER_message_is_COUNTED_and_NOT_APPLIED() -> None:
    """A lower `_seq` is a stale copy; hiding it would hide a reordered bus."""
    mirror = Mirror([TOPIC])
    mirror.apply(_message(TOPIC, {"v": 5}, 5, snapshot=True))

    mirror.apply(_message(TOPIC, {"v": 3}, 3, snapshot=True))

    assert mirror.out_of_order == 1, mirror.out_of_order
    assert mirror.applied == 1, "the stale copy was applied"
    assert dict(mirror.table(TOPIC)) == {"v": 5}, mirror.table(TOPIC)


def test_a_REPEATED_sequence_number_is_also_OUT_OF_ORDER() -> None:
    """`<=`, not `<`: a re-sent seq carries no new state and must not apply."""
    mirror = Mirror([TOPIC])
    mirror.apply(_message(TOPIC, {"v": 5}, 5, snapshot=True))

    mirror.apply(_message(TOPIC, {"v": 9}, 5, snapshot=True))

    assert mirror.out_of_order == 1, mirror.out_of_order
    assert dict(mirror.table(TOPIC)) == {"v": 5}, mirror.table(TOPIC)


def test_mirror_table_returns_a_COPY_so_a_consumer_cannot_write_the_mirror() -> None:
    """The mirror is read-only by construction, not by convention."""
    mirror = Mirror([TOPIC])
    mirror.apply(_message(TOPIC, {"MESU6": "fresh"}, 1, snapshot=True))

    handed_out = dict(mirror.table(TOPIC))
    handed_out["MESU6"] = "TAMPERED"
    handed_out["injected"] = "TAMPERED"

    assert dict(mirror.table(TOPIC)) == {"MESU6": "fresh"}, mirror.table(TOPIC)


def test_a_mirror_REQUIRING_a_topic_it_never_subscribed_to_stays_STALE() -> None:
    """`required` and `topics` are separate facts; conflating them never completes."""
    mirror = Mirror(["tbl."])

    mirror.apply(_message(TOPIC, {"MESU6": "fresh"}, 1, snapshot=True))

    assert mirror.complete is False, "prefix matching would fake completion"
    assert mirror.missing == ("tbl.",), mirror.missing


def test_the_ipc_LENGTH_GUARD_counts_BYTES_and_not_CODEPOINTS() -> None:
    """The guard's message says bytes; it must measure bytes.

    Found in review, ARC 026: the check read `len(str(path))`, a codepoint count,
    while reporting a byte limit. A path whose components are non-ASCII passed a
    guard that then let libzmq answer with the bare `Invalid argument` the guard
    exists to prevent — a measurement that disagreed with its own message.

    Each `é` is two UTF-8 bytes, so this root is under the limit by codepoints
    and over it by bytes. It must raise.
    """
    # NOT `tmp_path`: pytest's own prefix is ~60 characters, which spends the
    # whole budget before the fixture says anything. A short root under /tmp is
    # what leaves room for the two measurements to DISAGREE, which is the point.
    base = Path(tempfile.mkdtemp(prefix="nb", dir="/tmp"))  # nosec B108
    try:
        root = base / ("é" * 45)
        root.mkdir()
        endpoint = str(root / "x.ipc")
        assert len(endpoint) <= statebus._MAX_IPC_PATH, (
            f"the fixture is not under the limit by CODEPOINTS ({len(endpoint)}), "
            "so it proves nothing"
        )
        assert len(endpoint.encode()) > statebus._MAX_IPC_PATH, endpoint
        with pytest.raises(
            statebus.StateBusError, match="over the 100-byte AF_UNIX limit"
        ):
            statebus.endpoint_for("x", root=root)
    finally:
        shutil.rmtree(base, ignore_errors=True)
