"""§12.7's state-table transport: ZeroMQ `ipc://` PUB/SUB, snapshot-on-subscribe.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.7 (*Cache distribution &
restart rebuild — state-table transport*, **LOCKED v1.3**), §12.9 (dashboards
subscribe like any other consumer and get snapshot-on-subscribe), §3 (two ZMQ
hops total on the trade pathway).

§12.7 in four sentences, because every one of them is a property below:

1. **Mirror model, NOT raw shared memory.** The owner holds the real table in its
   own memory and publishes an atomic snapshot outward; every consumer keeps a
   **private read-only mirror it never writes**.
2. **Transport = ZeroMQ PUB/SUB**, brokerless, publisher binds, consumers
   subscribe, **freshness stamps ride each update**.
3. **Snapshot-on-subscribe is mandatory, not polish** — plain PUB/SUB is
   fire-and-forget, so a publisher emits a full snapshot on subscribe *plus a
   periodic full-state refresh*.
4. **Mirror incomplete => treated as stale => fast-drop/deny until the snapshot
   lands.** A half-built mirror is never sized on.

## §0b — THE SPELLING IS `PUB`; THE PUBLISHER SOCKET HERE IS `XPUB`

Recorded, with the measurement, rather than done quietly.

§12.7 says *"ZeroMQ plain PUB/SUB"* and, in the same paragraph, *"Publishers
therefore emit a full snapshot **on subscribe**"*. **A `zmq.PUB` socket cannot do
the second thing.** A subscription is handled entirely inside libzmq for a PUB
socket: it never surfaces to the application, so a PUB publisher has no event at
which to emit a snapshot. MEASURED on this node 2026-08-12, pyzmq 27.1.0 /
libzmq 4.3.5 — bind, connect a real `zmq.SUB`, subscribe `b"tbl."`, poll the
publisher for 700 ms:

    PUB:  pollin=0 frame=None
    XPUB: pollin=1 frame=b'\\x01tbl.'

`zmq.XPUB` is the *same wire protocol* — a `zmq.SUB` peer cannot tell the
difference, which is what keeps "plain PUB/SUB" true of the transport — and it
additionally delivers subscription frames (`\\x01 + topic`) up to the
application. `XPUB_VERBOSE` makes it deliver *every* subscribe rather than only
the first for a given topic, so a second consumer of an already-subscribed topic
also gets its snapshot.

So the invariant §12.7 states — *a late subscriber receives current state* — is
implemented, and the socket-type spelling is the thing that changed. Taking the
spelling literally would have deleted the mandatory mechanism. Subscribers are
`zmq.SUB` exactly as the spec says, and no consumer's code is affected.

## What rides each update

`{"_kind": "snapshot"|"delta", "_seq": int, "_stamp": float, ...payload}`.
`_stamp` is §12.7's *"freshness stamps ride each update"*: the publisher's clock
at publication. It is a TRANSPORT freshness stamp — how old this mirror copy is
— and is deliberately **not** a venue timestamp. Confusing the two would put a
local clock where §2A:106 invariant 4 requires a venue-sourced one; a venue
timestamp, where one exists, is part of the payload and stays there.

## What this module is NOT

It is not the price firehose. §12.7's *sole exception* — per-tick prices — lives
in `price_ring.py` on shared memory, because even ZeroMQ overhead is too much per
tick. Nothing stateful may go there and nothing per-tick may come here.
"""

from __future__ import annotations

import dataclasses
import json
import os
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

# pylint: disable=import-error
# `pyzmq` is a `checks/pinned_deps.json` pin installed in `.venv`; pylint runs
# from its own isolated pre-commit environment, which has no venv packages and
# so cannot resolve it statically. Same per-line disable the test suite already
# uses for `import pytest`.
import zmq

#: `\x01`/`\x00` + topic: libzmq's subscribe/unsubscribe frames, as delivered to
#: an XPUB socket. Named rather than inlined because the two bytes are the whole
#: mechanism and a reader should not have to recognise them.
_SUBSCRIBE = 1
_UNSUBSCRIBE = 0

#: AF_UNIX's `sun_path` is 108 bytes including the NUL. libzmq reports a bare
#: `Invalid argument` past it, which is an unreadable failure for something as
#: mundane as a long temp directory, so it is caught here with the length in the
#: message.
_MAX_IPC_PATH = 100


class StateBusError(RuntimeError):
    """A state-bus operation failed. Always carries what could not be done."""


def bus_root(root: str | os.PathLike[str] | None = None) -> Path:
    """Directory holding the `ipc://` endpoints.

    Defaults to `$XDG_RUNTIME_DIR/nix/bus` — a per-user tmpfs, cleaned by the
    system at logout, outside `~/nix` on purpose: `docs/directory_structure.md`
    enumerates the canonical tree and has no entry for runtime sockets, and
    inventing an undocumented top-level directory is the gap that document's
    v1.2.0 closed for `state/`. A socket is not an artifact of the project; it is
    an artifact of a process being alive.
    """
    if root is not None:
        return Path(root)
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not runtime:
        raise StateBusError(
            "XDG_RUNTIME_DIR is unset and no root was given — refusing to guess a "
            "socket directory; a bus endpoint in the wrong place is a publisher "
            "and a subscriber that never meet"
        )
    return Path(runtime) / "nix" / "bus"


def endpoint_for(name: str, root: str | os.PathLike[str] | None = None) -> str:
    """`ipc://` endpoint for a named state table, creating its directory."""
    directory = bus_root(root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StateBusError(f"cannot create bus root {directory}: {exc!r}") from exc
    path = directory / f"{name}.ipc"
    # ENCODED length, not `len(str(path))`. `sun_path` is a byte buffer, so a
    # codepoint count is the wrong measurement and would let a path with any
    # non-ASCII component pass this guard and then fail inside libzmq with the
    # bare `Invalid argument` the guard exists to prevent — a check whose message
    # says "bytes" while counting characters. Found in review, ARC 026.
    encoded = len(str(path).encode("utf-8"))
    if encoded > _MAX_IPC_PATH:
        raise StateBusError(
            f"ipc path is {encoded} bytes, over the {_MAX_IPC_PATH}-byte "
            f"AF_UNIX limit: {path}"
        )
    return f"ipc://{path}"


@dataclasses.dataclass(frozen=True)
class StateMessage:
    """One received update. `snapshot` is what distinguishes the two §12.7 kinds."""

    topic: str
    payload: dict[str, Any]
    seq: int
    stamp: float
    snapshot: bool

    @property
    def age_s(self) -> float:
        """Seconds since the publisher stamped this update."""
        return max(0.0, time.time() - self.stamp)


def _decode(topic: bytes, body: bytes) -> StateMessage:
    """Parse one wire message. Raises `StateBusError` on anything malformed."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateBusError(f"undecodable body on topic {topic!r}: {exc!r}") from exc
    if not isinstance(payload, dict):
        raise StateBusError(f"topic {topic!r}: body is not an object")
    # The three `_`-prefixed transport fields are stripped out of the table and
    # promoted to the message. A mirror is a copy of the OWNER'S table, and a
    # `_seq` key appearing inside it would be transport bookkeeping masquerading
    # as state — the consumer would mirror, and could act on, a field the owner
    # never had.
    return StateMessage(
        topic=topic.decode("utf-8", errors="replace"),
        payload={k: v for k, v in payload.items() if not k.startswith("_")},
        seq=int(payload.get("_seq", -1)),
        stamp=float(payload.get("_stamp", 0.0)),
        snapshot=bool(payload.get("_kind") == "snapshot"),
    )


class StatePublisher:  # pylint: disable=too-many-instance-attributes
    """One process's outward view of the state tables it OWNS.

    Four of its ten attributes are COUNTERS — `deltas_published`,
    `snapshots_served`, `subscribes_seen`, `unsubscribes_seen` — and they exist
    for the same reason `Plane2.emitted` does: a transport that cannot say what
    it carried cannot be measured, only believed.

    Single writer by construction: the tables live in this object's own memory
    and a consumer receives copies. There is deliberately no method by which a
    subscriber can write back — §12.7's mirror model is that *"raw shared state
    tables would let multiple processes touch the same bytes"*.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        context: zmq.Context | None = None,
        linger_ms: int = 0,
    ) -> None:
        self.endpoint = endpoint
        # A PRIVATE context, never `zmq.Context.instance()`. MEASURED: with the
        # shared singleton, a publisher and a subscriber in one process both
        # believe they own it, and the first `term()` blocks forever waiting for
        # the other's socket to close. A context is cheap; a hang is not.
        self._own_context = context is None
        self._context = context or zmq.Context()
        self._socket = self._context.socket(zmq.XPUB)
        # Every subscribe reaches the application, not only the first for a
        # topic. Without it a second dashboard subscribing to an
        # already-subscribed topic gets no snapshot and mirrors an empty table.
        self._socket.setsockopt(zmq.XPUB_VERBOSE, 1)
        self._socket.setsockopt(zmq.LINGER, linger_ms)
        try:
            self._socket.bind(endpoint)
        except zmq.ZMQError as exc:
            self._socket.close()
            raise StateBusError(f"cannot bind {endpoint}: {exc!r}") from exc
        self._tables: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self.deltas_published = 0
        self.snapshots_served = 0
        self.subscribes_seen = 0
        self.unsubscribes_seen = 0

    @property
    def topics(self) -> tuple[str, ...]:
        """Topics this publisher owns a table for."""
        return tuple(sorted(self._tables))

    def table(self, topic: str) -> Mapping[str, Any]:
        """The owner's own copy. Returned read-only; consumers get copies."""
        return dict(self._tables.get(topic, {}))

    def _send(self, topic: str, payload: Mapping[str, Any], *, snapshot: bool) -> None:
        self._seq += 1
        body = dict(payload)
        body["_kind"] = "snapshot" if snapshot else "delta"
        body["_seq"] = self._seq
        body["_stamp"] = time.time()
        self._socket.send_multipart(
            [topic.encode("utf-8"), json.dumps(body).encode("utf-8")]
        )

    def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        """Update the owned table and fan the new state out as a delta.

        The stored snapshot is REPLACED, not merged: §12.7 says the publisher
        emits an *atomic snapshot*, and a merged store would let a late
        subscriber receive a table assembled from fragments that were never
        simultaneously true.
        """
        self._tables[topic] = dict(payload)
        self._send(topic, self._tables[topic], snapshot=False)
        self.deltas_published += 1

    def refresh_all(self) -> int:
        """§12.7's *periodic full-state refresh*. Returns tables re-sent."""
        for topic, payload in sorted(self._tables.items()):
            self._send(topic, payload, snapshot=True)
        self.snapshots_served += len(self._tables)
        return len(self._tables)

    def _serve_subscription(self, frame: bytes) -> int:
        """Handle one XPUB subscription frame. Returns snapshots emitted."""
        if not frame:
            return 0
        prefix = frame[1:].decode("utf-8", errors="replace")
        if frame[0] == _UNSUBSCRIBE:
            self.unsubscribes_seen += 1
            return 0
        if frame[0] != _SUBSCRIBE:
            return 0
        self.subscribes_seen += 1
        served = 0
        for topic, payload in sorted(self._tables.items()):
            if topic.startswith(prefix):
                self._send(topic, payload, snapshot=True)
                served += 1
        self.snapshots_served += served
        return served

    def service(self, timeout_ms: int = 0) -> int:
        """Answer pending subscriptions with snapshots. Returns snapshots sent.

        Must be called from the owner's loop. It is a separate method rather than
        a background thread on purpose: a thread would make the owned table
        reachable from two threads and reintroduce exactly the shared-mutation
        problem §12.7's mirror model exists to remove.
        """
        served = 0
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        while True:
            try:
                frame = self._socket.recv(zmq.NOBLOCK)
            except zmq.Again:
                # Return as soon as the work is DONE, not when the budget is
                # spent. `timeout_ms` is how long to wait for a subscription to
                # arrive, not how long to sit still after answering one — a loop
                # that burned its full budget every pass would put that latency
                # straight into the owner's cycle time.
                if served or time.monotonic() >= deadline:
                    return served
                time.sleep(0.002)
                continue
            served += self._serve_subscription(frame)

    def close(self) -> None:
        """Release the socket (and the context if this object made it)."""
        self._socket.close()
        if self._own_context:
            self._context.term()


class StateSubscriber:  # pylint: disable=too-many-instance-attributes
    """A consumer's read-only side. Owns a `Mirror` it never lets anyone write.

    `received` and `bytes_received` are the non-vacuity observables
    `checks/check_state_bus.py` reads; without them a subscriber could only be
    asked whether it errored, which is the vacuous-pass shape the arc brief
    named."""

    def __init__(
        self,
        endpoint: str,
        topics: Iterable[str],
        *,
        required: Iterable[str] | None = None,
        context: zmq.Context | None = None,
        linger_ms: int = 0,
    ) -> None:
        # `topics` are SUBSCRIPTION PREFIXES (libzmq matches by prefix); `required`
        # are the EXACT table names this consumer cannot act without. They are
        # separate arguments because they are separate facts, and conflating them
        # is a live defect shape: subscribing to `"tbl."` and requiring `"tbl."`
        # makes a mirror that can never complete, since no table is named `tbl.`.
        # Defaulting `required` to `topics` is correct only when the prefixes ARE
        # the table names, which is the common case and the reason for the default.
        self.endpoint = endpoint
        self.topics = tuple(topics)
        # A PRIVATE context, never `zmq.Context.instance()`. MEASURED: with the
        # shared singleton, a publisher and a subscriber in one process both
        # believe they own it, and the first `term()` blocks forever waiting for
        # the other's socket to close. A context is cheap; a hang is not.
        self._own_context = context is None
        self._context = context or zmq.Context()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.setsockopt(zmq.LINGER, linger_ms)
        try:
            self._socket.connect(endpoint)
        except zmq.ZMQError as exc:
            self._socket.close()
            raise StateBusError(f"cannot connect {endpoint}: {exc!r}") from exc
        for topic in self.topics:
            self._socket.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))
        self.mirror = Mirror(self.topics if required is None else required)
        self.received = 0
        #: Wire bytes this subscriber actually took off the socket. The
        #: non-vacuity observable, and the reason it exists: a gate that asks
        #: "were there errors?" of a subscriber that received nothing has
        #: measured nothing at all. Zero here is a finding, exactly as
        #: `Plane2.emitted == 0` is.
        self.bytes_received = 0

    @property
    def socket(self) -> zmq.Socket:
        """The raw `zmq.SUB` socket. **READ-ONLY ACCESS, for OBSERVERS.**

        Added ARC 037 / sub-agent D, and deliberately the smallest thing that
        could be added. `zmq.Socket.get_monitor_socket()` is the only way to
        learn that the PUBLISHER'S PROCESS died — libzmq raises
        `EVENT_DISCONNECTED` on the peer going away, which is an observation of
        the WRITER rather than a timeout over the table it wrote — and it can
        only be asked of the socket itself. Nothing in this module changes: no
        monitor is attached here, no event is drained here, and a subscriber
        with no observer behaves exactly as it did before this property existed.

        It is a property and not a method so it reads as what it is: a handle,
        not an operation. `zmq.SUB` cannot send, so handing it out grants no
        write to the mirror this class exists to keep read-only (§12.7).

        The observer that takes it OWNS the monitor socket's lifetime and must
        close it before `close()` runs. MEASURED on this node (pyzmq 27.1.0 /
        libzmq 4.3.5): a monitor socket left open makes `Context.term()` block
        forever, and `Socket.disable_monitor()` does NOT close it — it drops
        pyzmq's reference and calls `monitor(None, 0)`, so the socket leaks and
        the hang is the same. `nixscore.liveness.PublisherLiveness.close` does
        both, in the order that was measured to terminate.
        """
        return self._socket

    def poll(self, timeout_ms: int) -> StateMessage | None:
        """Receive one update into the mirror, or `None` on timeout."""
        if not self._socket.poll(timeout_ms, zmq.POLLIN):
            return None
        topic, body = self._socket.recv_multipart()
        self.bytes_received += len(topic) + len(body)
        message = _decode(topic, body)
        self.mirror.apply(message)
        self.received += 1
        return message

    def drain(self, timeout_ms: int) -> list[StateMessage]:
        """Receive everything available within the budget. Never blocks past it."""
        messages: list[StateMessage] = []
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                return messages
            message = self.poll(remaining)
            if message is None:
                return messages
            messages.append(message)

    def close(self) -> None:
        """Release the socket (and the context if this object made it)."""
        self._socket.close()
        if self._own_context:
            self._context.term()


class Mirror:
    """A consumer's PRIVATE read-only copy of the tables it requires.

    §12.7: *"mirror incomplete => treated as stale => fast-drop/deny until
    snapshot lands"*. `complete` is that sentence: a mirror is incomplete until a
    **snapshot** has arrived for every required topic. A delta alone never
    completes it — a delta is a change to a table this consumer may never have
    seen, and applying it to nothing produces a table that looks whole and is
    not.
    """

    def __init__(self, required: Iterable[str]) -> None:
        self.required = tuple(required)
        self._tables: dict[str, dict[str, Any]] = {}
        self._snapshotted: set[str] = set()
        self._last_seq: dict[str, int] = {}
        self.applied = 0
        self.out_of_order = 0

    def apply(self, message: StateMessage) -> None:
        """Fold one update in. Out-of-order sequences are COUNTED, never hidden."""
        previous = self._last_seq.get(message.topic, -1)
        if message.seq <= previous:
            self.out_of_order += 1
            return
        self._last_seq[message.topic] = message.seq
        self._tables[message.topic] = dict(message.payload)
        if message.snapshot:
            self._snapshotted.add(message.topic)
        self.applied += 1

    def table(self, topic: str) -> Mapping[str, Any]:
        """This consumer's copy of one table. A COPY: the mirror is never handed
        out by reference, so a consumer cannot write the mirror it must not
        write."""
        return dict(self._tables.get(topic, {}))

    @property
    def missing(self) -> tuple[str, ...]:
        """Required topics with no snapshot yet. Empty means complete."""
        return tuple(t for t in self.required if t not in self._snapshotted)

    @property
    def complete(self) -> bool:
        """True once every required table arrived as a snapshot."""
        return not self.missing

    @property
    def stale(self) -> bool:
        """§12.7's fast-drop condition. An incomplete mirror IS stale."""
        return not self.complete
