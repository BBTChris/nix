"""The Sentinel's frozen seam — types and ports, no behaviour (§12.1).

ARC 034 / Phase 0.6(a). Landed BEFORE any implementation so the watchdog, the
marker writer and the cold-start replay can be built in parallel against a
settled boundary instead of against each other. Same shape and same discipline
as `nixrisk/seam.py` (ARC 028 / Phase 0.6), and for the same reason.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the line.

------------------------------------------------------------------------------
WHAT IS IN HERE
------------------------------------------------------------------------------
Value types, enumerations, and `Protocol` declarations. No rule, no arithmetic,
no I/O, no policy. The behaviour — when to fire, what to write, how to replay —
lives in this package's own modules and in `nixrisk/coldstart.py`.

------------------------------------------------------------------------------
SYNCHRONOUS OR ASYNCHRONOUS — declared per verb, and this seam DIVERGES
------------------------------------------------------------------------------
§2A's broker ports are ASYNC by default (`SPEC-AMENDMENTS` AMENDMENT 5) because
they are I/O against a venue, and §10 makes outbound exit connectivity in-process
with an async sender. **Every verb declared in this module is SYNCHRONOUS, and
that is a deliberate divergence, not an oversight.**

* **`HeartbeatPort.read` — SYNCHRONOUS.** The Sentinel's whole job is to make
  progress when the rest of the system has stopped. A coroutine needs a running
  event loop to make progress; a loop is a dependency, and §12.1 says
  *dependency-minimal*. A blocking read of a file or a shared page needs nothing
  but the interpreter.

* **`SentinelBrokerPort` — SYNCHRONOUS, and this is the load-bearing one.**
  §10's async-sender ruling is about the LIMITER's outbound path, where an async
  sender keeps a single-threaded event loop from blocking on a socket while it
  still has ticks to service. The Sentinel has no event loop and nothing else to
  service: it wakes, observes a dead heartbeat, and flattens. Declaring these
  verbs `async` would require this process to host an asyncio loop — importing
  `asyncio`, constructing a loop, and depending on that loop being schedulable —
  in the exact scenario where the machine is already sick enough to have killed
  the Risk Engine. **The cost of the divergence is stated rather than hidden:** a
  synchronous flatten BLOCKS this process for the duration of the broker round
  trip, so the Sentinel cannot watch the heartbeat while it is flattening. That
  is acceptable here and nowhere else, because by the time it is flattening the
  condition it watches for has already fired and there is no second action for it
  to take.

* **`MarkerWriterPort.append` — SYNCHRONOUS, and DURABLE ON RETURN.** §12.1's
  fix exists because the Sentinel fires when the sole event-log writer is dead;
  a marker that is buffered when the process dies is exactly the record that was
  supposed to survive. `append` returns only after the bytes are on the disk
  (write + flush + fsync). This is the OPPOSITE of `nixrisk.seam.Plane1Port`'s
  enqueue-without-durability split, and the difference is the point: Plane 1 has
  a shared-pool writer behind it that will make the row durable later, and the
  Sentinel has nothing behind it at all.

* **`AlertPort.raise_alert` — SYNCHRONOUS.** §12.1 pairs the flatten with an
  operator alert; §14 gives the protective path zero wire dependency. A
  synchronous call that fails must not prevent the flatten — see the ORDER note
  below, which fixes that as a declared property rather than a convention.

------------------------------------------------------------------------------
THE ORDER IS PART OF THE SEAM, because the order is the safety property
------------------------------------------------------------------------------
§12.1: the marker is written *"before and after acting"*. `MarkerPhase` exists so
that ordering is a value in the record rather than a comment in an implementation:

  1. `MarkerPhase.BEFORE` — appended, and DURABLE, before a single flatten
     instruction reaches the broker. A Sentinel that dies mid-flatten therefore
     still leaves a record saying it had decided to act and on which symbols.
     **Without this, a mid-flatten death is indistinguishable from a Sentinel
     that never woke up**, and cold-start would reconcile a partially flattened
     account against an event log that never heard of the attempt.
  2. the flatten, on the Sentinel's OWN session.
  3. `MarkerPhase.AFTER` — appended with the broker acknowledgements.

A marker file holding a `BEFORE` with no `AFTER` is not corruption; it is the
record of an interrupted act, and `MarkerReplayPort` is declared to accept it.

------------------------------------------------------------------------------
WHAT THIS SEAM DELIBERATELY DOES NOT DECIDE
------------------------------------------------------------------------------
The heartbeat transport (file, shared page, or socket), the marker file's
location, the poll interval, the loss threshold, the alert channel, and how
cold-start turns a replayed record into Plane-1 rows. Those are §12A tunables and
implementation, and this module holding them would make it a second behavioural
authority — the standing objection `directory_structure.md` records for `risks/`.

**It also does not decide that the Sentinel may do anything beyond flatten and
alert.** `SentinelBrokerPort` has no verb that opens, modifies, or sizes a
position, and that absence is the §14 authority boundary expressed as a type.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# R0903 (too-few-public-methods): every `Protocol` below is deliberately a
# SINGLE-VERB port, and the narrowness is the safety argument rather than an
# oversight. `HeartbeatPort` reads; `MarkerWriterPort` appends; `AlertPort`
# alerts. Adding a second verb to satisfy a default threshold of two would widen
# a surface whose whole value is that it cannot do anything else — and for
# `SentinelBrokerPort` that widening IS the §14 breach `check_sentinel_seam`
# ARM 5 exists to catch. The threshold is about behavioural classes; these carry
# no behaviour at all.
#
# R0902 (too-many-instance-attributes): `MarkerRecord` carries the four fields
# §12.1 enumerates plus the three that make a record REPLAYABLE rather than
# merely readable (`schema`, `phase`, `sentinel_pid`/`heartbeat_age_s`). Dropping
# one to reach seven would either lose a field the spec names or push it into a
# nested struct the replayer must read separately — and this record is written by
# a dying process for a later boot, which is the one place a "read it separately"
# split cannot be made safe. Same case `nixrisk/seam.py`'s value types document.
# pylint: disable=too-few-public-methods,too-many-instance-attributes

#: This seam's revision. Bumped when a declared type or port CHANGES SHAPE;
#: a widening that adds an optional field bumps the minor, a field removed or
#: re-typed bumps the major. Read by `checks/check_sentinel_seam.py`, which
#: refuses a shape change that did not move it.
SENTINEL_SEAM_REV = "1.0.0"

#: The marker file's record schema. A DIFFERENT number from the seam rev on
#: purpose: the marker is written by one process and read by another, on a later
#: BOOT, so a replayer may legitimately meet a record written by an older build.
#: The seam rev is a build-time agreement; this is a wire-compatibility one.
MARKER_SCHEMA = 1


class MarkerPhase(enum.Enum):
    """Which side of the flatten this record was written on (§12.1).

    The whole reason `before` and `after` are a declared enum rather than a
    boolean: `BEFORE` alone is a MEANINGFUL, expected terminal state of the
    marker file (the Sentinel died mid-act), and a boolean invites reading the
    missing `AFTER` as a bug in the writer rather than as the very evidence the
    §12.1 fix exists to preserve.
    """

    BEFORE = "before"
    AFTER = "after"


class TriggerCause(enum.Enum):
    """Why the Sentinel woke up and decided to act.

    `HEARTBEAT_LOST` is §12.1's own condition and the only one that authorises a
    flatten. The other two members exist so the marker can record a wake-up that
    did NOT flatten, which is what makes "it did not fire a nuisance flatten"
    an observable fact rather than an absence of evidence.
    """

    #: Heartbeat lost AND positions possibly open. §12.1's condition, both halves.
    HEARTBEAT_LOST = "heartbeat_lost"
    #: Heartbeat lost, but the broker reports no open position. NO flatten:
    #: §12.1 conditions the act on positions possibly being open, and a flatten
    #: against a flat account is a nuisance action with its own hazard.
    HEARTBEAT_LOST_NO_POSITIONS = "heartbeat_lost_no_positions"
    #: The heartbeat came back within the loss threshold. NO flatten.
    HEARTBEAT_RECOVERED = "heartbeat_recovered"


@dataclass(frozen=True)
class Heartbeat:
    """What the Risk Engine publishes and the Sentinel watches (§12.1).

    **`positions_open` rides on the heartbeat and is NOT authoritative**, and the
    distinction is the whole §12.1 condition. It is the Limiter's last known
    count, so by the time the Sentinel reads it the Limiter has been dead for at
    least the loss threshold and the figure is stale by construction. It is a
    HINT that says "there was exposure when I last spoke". The authoritative
    answer comes from `SentinelBrokerPort.open_positions()` on the Sentinel's own
    session — the broker, not a dead process's memory (§4: *broker wins and we
    correct*).

    `seq` is monotonic per Limiter process and `pid` identifies that process, so
    a restarted Limiter is distinguishable from a stalled one: a NEW pid with
    `seq` restarted at zero is a restart, whereas the same pid with a frozen
    `seq` is a hang. Watching `ts` alone cannot tell those apart, and they call
    for different operator narratives even though both are heartbeat loss.
    """

    #: The Limiter process that wrote this. §12.2's supervision needs the pid to
    #: attribute a restart; the drill needs it to prove which process was killed.
    pid: int
    #: Wall-clock UTC epoch seconds at write. §12.3: all internal time is UTC.
    ts: float
    #: Monotonic per-process counter. A frozen `seq` under a live `pid` is a
    #: HANG; a reset `seq` under a new `pid` is a RESTART.
    seq: int
    #: The Limiter's last known open-position count. A HINT — see above.
    positions_open: int


@runtime_checkable
class HeartbeatPort(Protocol):
    """Where the Sentinel reads the Risk-Engine heartbeat. SYNCHRONOUS.

    Returns `None` when no heartbeat has ever been published — which is NOT the
    same condition as a stale one and must not be collapsed into it. A Sentinel
    that started before the Limiter has seen no heartbeat and has no evidence of
    exposure; a Sentinel whose heartbeat has gone stale has seen one and lost it.
    Treating "never seen" as "lost" would make the Sentinel flatten every cold
    boot, which is §12.1's nuisance hazard fired on the most routine event there
    is.

    Never raises for absence. A read that cannot be performed at all (permission,
    corrupt record) is a different condition and is the implementation's to
    signal.
    """

    def read(self) -> Heartbeat | None:
        """The most recent heartbeat, or `None` if none has ever been published."""


@dataclass(frozen=True)
class SentinelPosition:
    """One open position as the SENTINEL's OWN broker session reports it.

    Deliberately NOT `nixrisk.seam.PositionRow`. That type is §3's published row
    and carries `trade_id`, `strategy_id`, `margin` and `stop_distance` — the
    Limiter's bookkeeping, none of which the Sentinel has or needs, and all of
    which it would have to obtain from the dead process it is replacing. Reusing
    it would create exactly the shared dependency §12.1 forbids, and would let a
    field the Sentinel cannot fill be quietly defaulted.

    Symbol and signed size. That is what a flatten needs.
    """

    symbol: str
    #: Signed contracts. Sign carries direction; a flatten closes it either way.
    size: int


@dataclass(frozen=True)
class BrokerAck:
    """One broker acknowledgement of one close instruction (§12.1's `broker acks`).

    `ok=False` with a `detail` is a FIRST-CLASS outcome, not an exception: §12.1
    requires the acks in the marker, and the record of a REFUSED close is the
    most important thing the marker can carry — it is the difference between "the
    account is flat" and "the Sentinel tried and the venue said no". An
    implementation that raised on a rejection would write no `AFTER` record and
    the failure would look identical to a mid-flatten death.
    """

    symbol: str
    ok: bool
    #: The venue's own words where there are any. `check` convention: assert the
    #: REASON, never the exit code alone (`nix_check_contract.md` §18).
    detail: str = ""


@runtime_checkable
class SentinelBrokerPort(Protocol):
    """The Sentinel's OWN broker session (§12.1). SYNCHRONOUS — see the header.

    **This is a SEPARATE SESSION, not a shared handle.** §12.1: *"emergency
    flatten-all via its OWN broker session"*. Sharing the Limiter's session would
    mean the Sentinel's only means of acting dies with the process it is watching
    — the common-mode failure this whole component exists to avoid.

    **The verb list is the §14 authority boundary, expressed as a type.** There
    is no `place_order`, no `modify`, no `size`, no `cancel_and_replace`. The
    Sentinel can observe exposure and close it. Anything else it could do would
    be a second trading authority, and §14 permits exactly one exception to
    Limiter-only execution — a FLATTEN when the Limiter is dead — not a second
    Limiter.
    """

    def connect(self) -> None:
        """Establish this process's own session. Raises if it cannot."""

    def open_positions(self) -> tuple[SentinelPosition, ...]:
        """What the BROKER says is open right now. The authoritative answer.

        Empty tuple means flat. This is the second half of §12.1's condition and
        the reason the heartbeat's `positions_open` is only a hint.
        """

    def flatten_all(self) -> tuple[BrokerAck, ...]:
        """Close every open position. One ack per symbol attempted, in order.

        Returns rather than raises on a venue rejection — see `BrokerAck`.
        """

    def disconnect(self) -> None:
        """Release the session. Never raises: a failed teardown must not mask a
        completed flatten, and by this point the act is already recorded."""


@dataclass(frozen=True)
class MarkerRecord:
    """One line of the local append-only marker file (§12.1's durable record).

    §12.1 enumerates the contents: *"timestamp, trigger cause, symbols, broker
    acks"*. All four are here, plus the three fields that make a record
    REPLAYABLE rather than merely readable:

    * `schema` — so a replayer meeting a record from an older build refuses
      loudly instead of reading fields positionally into the wrong meaning.
    * `phase` — which side of the flatten (see the header's ORDER note).
    * `sentinel_pid` and `heartbeat_age_s` — the attribution §12.10 Plane 1 needs
      when cold-start books the row: *which* watcher acted and *how dead* the
      Limiter was. A replayed row that cannot say why it exists is a row an
      operator cannot audit.

    `acks` is empty on a `BEFORE` record by construction — nothing has been
    acknowledged yet — and that emptiness is not a defect.
    """

    schema: int
    phase: MarkerPhase
    #: UTC epoch seconds (§12.3: all internal time is UTC).
    ts: float
    cause: TriggerCause
    #: The symbols this act covers. On `BEFORE` these come from the Sentinel's
    #: own `open_positions()` read, never from the dead Limiter's hint.
    symbols: tuple[str, ...]
    acks: tuple[BrokerAck, ...]
    #: Which watcher wrote this.
    sentinel_pid: int
    #: How long the heartbeat had been silent when the decision was taken.
    heartbeat_age_s: float


@runtime_checkable
class MarkerWriterPort(Protocol):
    """Append-only, local, durable on return. SYNCHRONOUS (see the header).

    **Append-only is a declared property, not an implementation habit.** There is
    no `truncate`, no `rewrite`, no `clear`. §12.1's record has to survive the
    process that wrote it; a writer that could rewind could erase a `BEFORE`
    record on its way to dying, which is precisely the evidence the fix exists to
    keep. Directive 6 says the same thing one layer up: append history, never
    rewrite banked evidence.
    """

    def append(self, record: MarkerRecord) -> None:
        """Append one record and return only once it is DURABLE on disk.

        Durable means the bytes have reached the storage device — write, flush,
        fsync — not that they are in a buffer this process owns. A buffered
        marker dies with the process it was written to outlive.
        """


@runtime_checkable
class MarkerReplayPort(Protocol):
    """Cold-start's side: read what the Sentinel left, book it, archive it.

    §12.1: *"On next boot, cold-start reconciliation reads the marker and books
    the flatten into the real event log retroactively (rows tagged
    `source=sentinel`), then archives the marker."*

    **`read_pending` must return an interrupted act**, i.e. a `BEFORE` with no
    matching `AFTER`. That is the single most important record in the file and a
    reader that treated it as malformed would discard the evidence of the exact
    catastrophe §12.1 was written for.

    **`archive` is separate from `read_pending` and must run only AFTER the rows
    are booked.** Archiving inside the read would lose the marker if booking then
    failed, turning a recoverable replay into a silent gap in Plane 1.
    """

    def read_pending(self) -> tuple[MarkerRecord, ...]:
        """Every record awaiting replay, in write order. Empty if none."""

    def archive(self) -> None:
        """Retire the replayed marker. Called only after the rows are booked."""


@runtime_checkable
class AlertPort(Protocol):
    """The operator alert §12.1 pairs with the flatten. SYNCHRONOUS.

    **Declared to never raise.** §14 gives the protective path zero delivery
    dependency: an alert channel that is down is a degraded observability
    condition, and letting it abort the flatten would trade a real exposure for a
    notification. An implementation that cannot deliver records the failure and
    returns — the marker file is the durable record, not this.
    """

    def raise_alert(self, cause: TriggerCause, detail: str) -> None:
        """Tell the operator. Never raises; delivery failure is not the flatten's
        problem (§14)."""
