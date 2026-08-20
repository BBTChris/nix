#!/usr/bin/env python3
"""`limiterd` — the Limiter as an OS PROCESS. The §2:42 Risk-Engine entrypoint.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 039 / sub-agent A. `scripts/nixrisk/loop.py` is §5:322's event loop as an
object; this file is what makes it a thing with a pid. Until it existed, nothing
in this tree could be sent a signal, appear in `pgrep`, show two tasks under
`/proc/<pid>/task`, or be killed — and every Limiter property the tree had
proven was a property of a library that a test constructed and then discarded
(ARC 038's deepest finding).

WHAT THIS PROCESS IS NOT, STATED FIRST SO NOTHING READS IT AS MORE
-------------------------------------------------------------------
It places no orders. It holds no positions. It has no broker session, no gate
pass, no reservations and no stops. **ARC 042 gave it ONE Plane-1 write and no
other** — §12.10's `go_timeout` row, enqueued when §4:210-212's breaker fires;
every other §9 event type is still unwritten by this process (see
`Plane1Booker`). It is the SUBSTRATE: a
single-threaded loop that beats, a low-priority sender thread that records, and a
live `StrategyRegistry` that outlives the commands it serves. Anything else a
reader wants from a Limiter is in `nixrisk/` and is not wired to this process yet.

ARC 040 (slice 2) added ONE invariant to that substrate and no other: §4:210-212's
GO-TIMEOUT, the deadlock breaker on the one-in-flight lock. The `resolve` verb
came with it, because §4:203-206's terminal feedback is the only thing that can
show the breaker does NOT fire on a healthy GO. §14:971's *"it can never wedge"*
is the claim; `checks/check_go_timeout.py` is what measures it from outside this
process, through the `go_timeouts` rows in the stop record below.

WHY FILES AND A DIRECTORY RATHER THAN ZMQ
------------------------------------------
§5:322 names a *"ZMQ inbox"* and §2:38 puts the Allocator behind one. There is no
bus in this tree yet (`CLAUDE.md`'s spec table lists the Nix-side bus
implementation under *not yet authored*), and inventing one inside the arc that
builds the loop would mean neither could be measured without the other. A
directory of small JSON files needs the kernel and nothing else, which is the
same argument `nixsentinel/heartbeat.py` makes for the heartbeat file, and it
makes the whole command path drivable from a shell — which is exactly how the
out-of-process gate must drive it.

Replies are written with `tempfile` + `os.replace` for the reason the heartbeat
is: `os.replace` is atomic within a filesystem, so a reader either sees the whole
reply or no reply, never half of one.

THE RUNTIME DIRECTORY IS A FIXED CONTRACT
------------------------------------------
    DIR/risk_engine.heartbeat.json  §12.1:604's beat. The NAME is
                                    `nixsentinel.heartbeat.DEFAULT_HEARTBEAT_NAME`
                                    imported, never spelled here (directive 3),
                                    because the Sentinel reads it by that name.
    DIR/inbox/                      `*.json` command files. Drained and unlinked
                                    by the loop's own tick.
    DIR/outbox/                     `<id>.reply.json`, one per command, atomic.
    DIR/limiter.runtime.json        written ONCE at boot and again at clean stop.
    DIR/plane1.wal                  ARC 042. §9's DURABLE LOCAL WAL, appended by
                                    `Plane1Booker` when §4:210-212's breaker
                                    fires. The `--plane1-wal` flag moves it; the
                                    shared-pool writer that group-commits it into
                                    Postgres is a DIFFERENT process and is not
                                    started here (§9's own split).

`limiter.runtime.json`'s boot record is the in-process half of §12.2:618 —
*"Boot-flatten makes any single restart safe by design"* — made checkable: a
fresh process starts with an empty registry and no in-flight lock, so `flat` is
true by construction and `registrations` / `in_flight` are empty. It says
NOTHING about the broker; `nixrisk/coldstart.py` owns that half and is not wired
in here. A reader that took this file for the broker's answer would be taking
the one claim §4's cold-start section calls trustless.

DEATH — BOTH KINDS, AND BOTH ARE THE DOCUMENTED STATE
------------------------------------------------------
`SIGTERM` and `SIGINT` call `loop.stop()`, the loop exits at the top of its next
tick, the sender is joined, the stop record is written with a real `stopped_ts`,
and the exit code is 0. That is the supervised restart §12.2:617 expects.

`SIGKILL` is uncatchable BY DESIGN and nothing here pretends otherwise. The
process vanishes, the heartbeat file freezes at whatever `seq` the last completed
tick published, and `limiter.runtime.json` keeps `"stopped_ts": null`. That pair
— a frozen `seq` with a null `stopped_ts` — is precisely what §12.1:604 has the
Sentinel act on, and it is the reason `stopped_ts` is written at stop rather than
being inferable from the file's absence.

`debug.md` §7.12 — THE STANDING QUESTION: what would have to be true for a run of
this program to look healthy while proving nothing?
  1. **The loop never ticked** (a `--max-ticks 0` misread as "no ticks", say).
     GUARDED: 0 means *run forever*, and the stop record carries `ticks`, so a
     run that ticked zero times says so in the file the gate reads.
  2. **The heartbeat file was written by something other than the loop.** GUARDED
     in `nixrisk/loop.py`: `_publish_heartbeat` refuses any thread but the loop's
     and refuses any call from outside a tick, so a `seq` in that file cannot have
     come from anywhere else in this process.
  3. **The inbox was never drained, and the absence of replies read as "no
     commands".** GUARDED: every command file produces a reply file, including an
     unparsable one, and the reply names the reason. A command with no reply is a
     drain that did not happen.
  4. **The sender thread was never started, so the §5:323 two-task shape is a
     claim.** GUARDED: `SenderThread.start` waits on an `Event` the thread sets
     from inside itself, and refuses to boot if it never arrives.
  5. **The GO-timeout row was never booked and the absence read as "the breaker
     never fired"** (ARC 042 / CHECK-DEBT D3.425 — the state this process was in
     until this arc: the breaker fired, the runtime record said so, and §9's
     evidence plane held nothing). GUARDED: the stop record's `plane1` block
     reports `firings_seen`, `booked`, `refused` and the WAL's own `enqueued` /
     `durable` counters, so *fired and booked*, *fired and refused* and *never
     fired* are three distinguishable readings rather than one absence.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Final

from nixrisk.loop import (
    GoTimeout,
    LimiterLoop,
    LoopStop,
    go_timeout_from_config,
    heartbeat_interval_from_config,
    tick_interval_for,
)
from nixrisk.recovery import RecoveryError
from nixrisk.seam import EventKind, EventRow
from nixrisk.wal import Plane1Wal, WalError
from nixsentinel.heartbeat import DEFAULT_HEARTBEAT_NAME, HeartbeatPublisher

#: Named once so every refusal points at the same file (doctrine C.2).
SITE: Final[str] = "scripts/limiterd.py"

#: The runtime directory's fixed layout. `HEARTBEAT_NAME` is IMPORTED rather
#: than spelled, because the Sentinel opens that exact name and a second copy of
#: the string here could drift from the one it reads (directive 3).
HEARTBEAT_NAME: Final[str] = DEFAULT_HEARTBEAT_NAME
INBOX_DIR: Final[str] = "inbox"
OUTBOX_DIR: Final[str] = "outbox"
RUNTIME_NAME: Final[str] = "limiter.runtime.json"
#: ARC 042. §9's durable local WAL, inside the runtime directory by default so
#: one directory is the whole contract and a drive can find the evidence beside
#: the record that claims it. `--plane1-wal` moves it.
PLANE1_WAL_NAME: Final[str] = "plane1.wal"

#: Wire versions. Three DIFFERENT namespaces because the three records cross
#: different boundaries and may be read by differently-built programs: the
#: runtime record is read by an operator and by the gate, the command file is
#: written by a client, and the reply is read by that client.
RUNTIME_SCHEMA: Final[int] = 1
COMMAND_SCHEMA: Final[int] = 1
REPLY_SCHEMA: Final[int] = 1

#: Command files read per tick. §11:581's bound applied to the ingress read for
#: the same reason `nixrisk/loop.py` bounds the drain: a directory somebody
#: dumped ten thousand files into must not hold one tick open past the beat.
INBOX_MAX_PER_TICK: Final[int] = 32

#: The mode every file this process writes carries. Nothing in `~/nix` outside
#: `state/` needs to be world-readable and the default umask is not a guarantee;
#: `nixsentinel/heartbeat.py` records the same reasoning for the beat.
_MODE: Final[int] = 0o600

#: The verbs the loop serves this arc. Deliberately three: enough to exercise
#: the live registry and the one-in-flight lock from another process, and no
#: verb that could reach money. §12.11's authenticated operator verbs are a
#: different surface and are not these.
VERB_REGISTER: Final[str] = "register"
VERB_GO: Final[str] = "go"
VERB_STATUS: Final[str] = "status"
#: ARC 040. §4:203-206's terminal feedback, landed because §4:210-212's breaker
#: cannot be shown NOT to fire early unless a GO can end some other way. Without
#: it every GO in this process would end at the timeout and a gate would read
#: that as the invariant working — §0a of this arc's brief, exactly.
VERB_RESOLVE: Final[str] = "resolve"
VERBS: Final[tuple[str, ...]] = (
    VERB_REGISTER,
    VERB_GO,
    VERB_STATUS,
    VERB_RESOLVE,
)


@dataclass(frozen=True)
class RawCommand:
    """One file the ingress read, BEFORE anything decided what it means.

    Carries the bytes and the path rather than a parsed object on purpose: the
    parse is a decision, decisions belong in the tick (§5:322's serial
    processing), and a parse failure has to produce a REPLY, which the ingress
    cannot write because it does not know the id yet.
    """

    path: Path
    blob: bytes
    read_error: str


# R0903 (too-few-public-methods): ONE public verb is the whole collaborator.
# It is the loop's per-tick ingress callback and nothing else calls it; a
# second method added to clear a threshold would widen a surface whose
# narrowness is what keeps §11:581's bound on the tick meaningful.
# pylint: disable=too-few-public-methods
class Inbox:
    """§5:322's inbox read, standing in for the ZMQ socket the spec names.

    Called once per tick from inside the tick. Bounded at `INBOX_MAX_PER_TICK`
    and sorted, so the order commands are served in is the order the filesystem
    reports them in rather than whatever `scandir` felt like — FCFS is §5:325's
    own contention rule one component over, and an arbitrary order here would be
    a race nobody declared.
    """

    def __init__(self, directory: Path, loop: LimiterLoop) -> None:
        self.directory = directory
        self._loop = loop

    def drain(self, tick: int) -> int:
        """Read up to `INBOX_MAX_PER_TICK` command files onto the loop's queue.

        Does NOT unlink. The file is removed by `CommandHandler` after its reply
        is on disk, so a crash between the read and the reply leaves the command
        where the next boot can still see it.
        """
        del tick
        try:
            names = sorted(
                entry.name
                for entry in os.scandir(self.directory)
                if entry.is_file() and entry.name.endswith(".json")
            )
        except OSError as exc:
            raise RuntimeError(
                f"{SITE}: cannot scan the inbox {self.directory}: {exc!r}"
            ) from exc
        taken = 0
        for name in names[:INBOX_MAX_PER_TICK]:
            path = self.directory / name
            try:
                blob = path.read_bytes()
                error = ""
            except OSError as exc:
                blob = b""
                error = f"cannot read {path.name}: {exc!r}"
            self._loop.submit(RawCommand(path=path, blob=blob, read_error=error))
            taken += 1
        return taken


# R0903 (too-few-public-methods): ONE public verb is the whole handler. It is
# the loop's per-item callback and nothing else calls it; a second method added
# to clear a threshold would widen a surface whose narrowness is the point.
# pylint: disable=too-few-public-methods
class CommandHandler:
    """Turns one `RawCommand` into one reply file. NEVER RAISES.

    Fail-closed and contained (directive 4, and `nixrisk/loop.py`'s own
    containment argument): every refusal is a reply with `accepted: false` and a
    reason naming the spec coordinate it refused under. A command that could kill
    this process would be a remote kill switch on the process §12.1:604 has the
    Sentinel watching, so an unparsable file is answered, not fatal.
    """

    def __init__(self, loop: LimiterLoop, outbox: Path) -> None:
        self._loop = loop
        self._outbox = outbox

    def handle(self, item: object) -> None:
        """The loop's per-item callback. Writes the reply, then unlinks the command."""
        if not isinstance(item, RawCommand):
            raise TypeError(
                f"{SITE}: the loop handed the handler a {type(item).__name__}, "
                "not a RawCommand — nothing else may be submitted to this loop"
            )
        reply = self._reply_for(item)
        self._write_reply(str(reply["id"]), reply)
        try:
            item.path.unlink()
        except OSError:
            # Unlinked already, or a directory that vanished under us. The reply
            # is on disk either way, and re-serving a command whose reply exists
            # is the lesser fault: the reply is idempotent by id.
            pass

    # -- verb dispatch ------------------------------------------------------

    # R0911 (too-many-return-statements): the returns ARE the fail-closed ladder
    # — unreadable file, bad JSON, wrong top-level type, wrong schema, unknown
    # verb, and the dispatch itself. Collapsing them into one exit would mean one
    # reason string covering six distinguishable refusals, and check contract v2
    # §11 makes the REASON the assertion.
    # pylint: disable=too-many-return-statements
    def _reply_for(self, command: RawCommand) -> dict[str, Any]:
        """One reply dict for one command. Every path returns; none raises."""
        fallback_id = command.path.stem
        if command.read_error:
            return self._refuse(fallback_id, "", command.read_error)
        try:
            raw = json.loads(command.blob.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return self._refuse(
                fallback_id, "", f"{command.path.name} is not valid JSON: {exc!r}"
            )
        if not isinstance(raw, dict):
            return self._refuse(
                fallback_id,
                "",
                f"{command.path.name}: top level is {type(raw).__name__}, "
                "expected an object",
            )
        command_id = str(raw.get("id") or fallback_id)
        verb = str(raw.get("verb") or "")
        schema = raw.get("schema")
        if schema != COMMAND_SCHEMA:
            return self._refuse(
                command_id,
                verb,
                f"command schema {schema!r} != this build's {COMMAND_SCHEMA} — "
                "refusing to read fields into a meaning they may not have",
            )
        if verb not in VERBS:
            return self._refuse(
                command_id,
                verb,
                f"unknown verb {verb!r}; this build serves {list(VERBS)}",
            )
        try:
            return self._dispatch(command_id, verb, raw)
        except RecoveryError as exc:
            return self._refuse(command_id, verb, str(exc))
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return self._refuse(
                command_id, verb, f"{type(exc).__name__}: {exc} (contained)"
            )

    def _dispatch(
        self, command_id: str, verb: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        """The three verbs. Split out so `_reply_for` holds only the refusals."""
        if verb == VERB_STATUS:
            beat = self._loop.last_beat
            return self._reply(
                command_id,
                verb,
                accepted=True,
                reason=(
                    f"{SITE}: tick {self._loop.tick_count}, heartbeat seq "
                    f"{self._loop.heartbeat_seq}, last beat ts "
                    f"{None if beat is None else beat.ts}, registrations "
                    f"{list(self._loop.registry.registered())}, in flight "
                    f"{[list(pair) for pair in self._loop.in_flight_holders()]}, "
                    f"go armed "
                    f"{[[s, c, round(e, 3)] for s, c, e in self._loop.go_armed()]}, "
                    f"go timeouts {len(self._loop.go_timeouts())}, "
                    f"go timeout knob {self._loop.go_timeout_s}, "
                    f"sender handoffs {self._loop.sender.handoffs}"
                ),
            )
        strategy_id = str(raw.get("strategy_id") or "")
        if not strategy_id:
            return self._refuse(
                command_id, verb, f"{verb!r} requires a non-empty strategy_id"
            )
        if verb == VERB_REGISTER:
            row = self._loop.admit(strategy_id, now=time.time())
            return self._reply(
                command_id,
                verb,
                accepted=True,
                reason=(
                    f"{SITE}: {strategy_id!r} admitted into the LIVE registry at "
                    f"slot {row.slot} — §4:266-268's slot, held by this process "
                    "for as long as it runs"
                ),
            )
        client_order_id = str(raw.get("client_order_id") or "")
        if not client_order_id:
            return self._refuse(
                command_id, verb, f"{verb!r} requires a non-empty client_order_id"
            )
        if verb == VERB_RESOLVE:
            outcome = str(raw.get("outcome") or "")
            accepted, reason = self._loop.resolve_in_flight(
                strategy_id, client_order_id, outcome
            )
            return self._reply(command_id, verb, accepted=accepted, reason=reason)
        if not self._loop.registry.is_registered(strategy_id):
            return self._refuse(
                command_id,
                verb,
                f"{strategy_id!r} is not registered in this Risk Engine — "
                "§4:266-268 keys every piece of Limiter state to a registration, "
                "so there is no slot for an order to be in flight in",
            )
        accepted, reason = self._loop.take_in_flight(strategy_id, client_order_id)
        if accepted:
            self._loop.hand_to_sender((strategy_id, client_order_id))
        return self._reply(command_id, verb, accepted=accepted, reason=reason)

    # -- reply plumbing -----------------------------------------------------

    def _reply(
        self, command_id: str, verb: str, *, accepted: bool, reason: str
    ) -> dict[str, Any]:
        """The reply record. `tick` and `seq` are read at reply time, from the loop."""
        return {
            "schema": REPLY_SCHEMA,
            "id": command_id,
            "verb": verb,
            "accepted": accepted,
            "reason": reason,
            "tick": self._loop.tick_count,
            "seq": self._loop.heartbeat_seq,
            "pid": os.getpid(),
        }

    def _refuse(self, command_id: str, verb: str, why: str) -> dict[str, Any]:
        """A refusal. Always carries a reason; `accepted: false` alone says nothing."""
        return self._reply(command_id, verb, accepted=False, reason=f"{SITE}: {why}")

    def _write_reply(self, command_id: str, reply: dict[str, Any]) -> None:
        """`<id>.reply.json`, written atomically. A reader sees all of it or none."""
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in command_id)
        _write_json_atomically(self._outbox / f"{safe}.reply.json", reply)


# R0903 (too-few-public-methods): TWO public verbs and both are the contract —
# the booking itself and the ingress wrapper that schedules it. A third added to
# clear a threshold would widen the one surface in this process that can write to
# §9's evidence plane.
# pylint: disable=too-few-public-methods
class Plane1Booker:
    """ARC 042. §9's ENQUEUE for §12.10's `go_timeout` row, and nothing else.

    CHECK-DEBT **D3.425**, and the finding it discharges stated exactly:
    `_break_go_deadlocks` fires, releases the §4:208 lock and writes a RUNTIME
    RECORD — and a runtime record is not §9's evidence plane. §12.10 puts
    GO-timeout on **Plane 1** because the firing GATES MONEY (the GO is treated
    as DENIED and the strategy reset to flat-and-free), so the transition owes a
    row in the append-only log and had none.

    WHAT THIS IS NOT, STATED FIRST
    ------------------------------
    It is not a second writer. §9 makes the **Limiter** the sole Plane-1 writer
    and this process IS the Limiter (§2:42); wiring it to write is making the
    first and only intended writer function. Proving that no OTHER process can
    write is the sole-writer ENFORCEMENT property (I8) and is a different arc —
    it could not be enforced against a writer that did not yet write.

    It is not the shared-pool writer either. §9's path is *enqueue -> durable
    local WAL -> shared-pool writer -> group-commit to Postgres*, and this
    object owns the FIRST ARROW ONLY. `nixrisk.wal.GroupCommitWriter` and
    `nixrisk.plane1_sink.Plane1PostgresSink` own the rest, out of this process,
    and nothing here starts them. A row that reached the WAL and not Postgres is
    §12.4's buffering working, not this object failing.

    It books ONE event type. Every other §9 row this daemon could owe —
    accepted, denied, filled, closed, reservation, cancel, HALT, operator action,
    strategy lifecycle, cold start — is STILL UNWRITTEN by this process. That is
    named debt, not a silent gap.

    EXACTLY ONCE, WITHOUT A RETRY (§4:240-241)
    ------------------------------------------
    One firing is one enqueue is one row. The breaker is idempotent from the
    loop's side — it pops the stamp after it fires, so a strategy fires once —
    but this booker reads a LEDGER (`LimiterLoop.go_timeouts()`), and a ledger is
    re-read every tick. So each firing is keyed by
    `(strategy_id, client_order_id, fired_tick)` and the key is recorded
    **BEFORE** the enqueue is attempted, never after. That order is the §4:240-241
    rule expressed in code: a booking that raised is NOT retried on the next
    tick, because a retry is how one intended row becomes two. The failure is
    COUNTED and reported in the stop record instead, which is the loud half of
    directive 4 — a refused booking that nothing recorded would be the same
    silence D3.425 named, one layer down.

    WHY THE INGRESS, AND WHY ONE TICK LATE
    --------------------------------------
    `nixrisk.loop.LimiterLoop.tick` runs `_run_ingress` -> `_drain` ->
    `_break_go_deadlocks` -> `_beat_if_due`, and that ORDER is an invariant of
    the loop (a breaker that ran before the drain would false-release a GO whose
    terminal feedback was sitting in the same inbox). The ingress callback is the
    one hook this process owns inside the tick, so booking there books the
    PREVIOUS tick's firings. The lateness is bounded by one tick interval and is
    stated rather than hidden; the alternative is a hook inside the loop, and
    §4:210-212's breaker is risk-path source this arc deliberately did not touch.

    Nothing is lost to the ledger's bound: `LimiterLoop._go_timeouts` is a deque
    of `FAULT_LEDGER_MAX`, at most one firing per registered strategy can be
    appended between two consecutive ingress calls (the breaker is keyed by
    `strategy_id`), and `main` books ONCE MORE after `run()` returns so the last
    tick's firing is not left behind by the stop.
    """

    def __init__(self, loop: LimiterLoop, wal: Plane1Wal) -> None:
        self._loop = loop
        self._wal = wal
        self._booked: set[tuple[str, str, int]] = set()
        self.firings_seen = 0
        self.booked = 0
        self.refused = 0
        self.last_error = ""

    def book_new_firings(self) -> int:
        """Enqueue a §12.10 row for every firing not booked yet. NEVER RAISES.

        Returns the number booked by THIS call. Contained for the reason
        `CommandHandler.handle` is: this runs inside the tick, and an exception
        escaping here would kill the process §12.1:604 has the Sentinel watching
        — turning a persistence fault into a trading outage, which is precisely
        the conflation §12.4 forbids (*"degraded persistence != degraded
        trading"*).
        """
        booked = 0
        for row in self._loop.go_timeouts():
            key = (row.strategy_id, row.client_order_id, row.fired_tick)
            if key in self._booked:
                continue
            # Recorded BEFORE the attempt. See the class docstring: this is
            # §4:240-241's no-resend rule, and reversing the two lines would
            # make a transient WAL error into a duplicate row.
            self._booked.add(key)
            self.firings_seen += 1
            try:
                self._wal.enqueue(self._row_for(row))
                # §9's word is DURABLE. `enqueue` returns from an unbuffered
                # `write(2)`, which survives a SIGKILL and not a power cut;
                # `sync_to_disk` is the boundary that makes the row evidence.
                # It costs one fsync PER FIRING, and a firing is by definition
                # exceptional — §11.6 keeps GROUP-COMMIT off the hot path, and
                # this is neither a group commit nor the entry pathway.
                self._wal.sync_to_disk()
                self.booked += 1
                booked += 1
            except (WalError, OSError) as exc:
                self.refused += 1
                self.last_error = (
                    f"{SITE}: §12.10 go_timeout row for {row.strategy_id!r}/"
                    f"{row.client_order_id!r} fired on tick {row.fired_tick} was "
                    f"NOT booked to Plane 1: {type(exc).__name__}: {exc}. "
                    "§4:240-241 forbids the retry, so this firing has no row and "
                    "this counter is the only thing that says so"
                )
        return booked

    def _row_for(self, firing: GoTimeout) -> EventRow:
        """One `GoTimeout` observation -> one §9 `EventRow`.

        §9 requires timestamp + strategy_id + trade_id + reason on every row.

        * `ts` is the WALL CLOCK at booking, because `occurred_at` is a
          timestamptz and `GoTimeout` deliberately carries no wall-clock reading
          (its `elapsed_s` is the loop's own monotonic, which is the whole point
          of that record). The loop-clock truth is not discarded: `fired_tick`,
          `admitted_tick`, `elapsed_s` and `timeout_s` ride in `fields`, so a
          reader can tell the two clocks apart instead of being handed one
          number that silently mixes them.
        * `trade_id` is ABSENT and that is a measurement, not an omission. The
          Limiter mints a trade id at OPEN (§4); a GO that never received
          terminal feedback never opened, so there is no trade. The seam types
          it optional for exactly this case and the sink writes the schema's
          documented `'-'` sentinel, which is a different fact from a lost id.
        * `reason` is the breaker's OWN §4:210-212-citing sentence, not the
          string `"go_timeout"` — the event TYPE already carries that, and check
          contract v2 rule 11 makes the reason the assertion.
        """
        return EventRow(
            kind=EventKind.GO_TIMEOUT,
            ts=time.time(),
            strategy_id=firing.strategy_id,
            reason=firing.reason,
            trade_id=None,
            fields={
                "client_order_id": str(firing.client_order_id),
                "admitted_tick": str(firing.admitted_tick),
                "fired_tick": str(firing.fired_tick),
                "elapsed_s": f"{firing.elapsed_s:.6f}",
                "timeout_s": f"{firing.timeout_s:.6f}",
                "released": str(firing.released).lower(),
                "resent": str(firing.resent).lower(),
                "booked_by": SITE,
            },
        )

    def before(self, inner: Callable[[int], object]) -> Callable[[int], object]:
        """Wrap the loop's ingress so the booking runs first, inside the tick.

        Composed rather than folded into `Inbox.drain`: the inbox reads commands
        and this writes evidence, and one object doing both would be one place to
        break two unrelated contracts.
        """

        def _ingress(tick: int) -> object:
            self.book_new_firings()
            return inner(tick)

        return _ingress

    def record(self) -> dict[str, Any]:
        """The out-of-process evidence block. Read by `checks/check_go_timeout.py`.

        Counters, not a boolean: *fired and booked*, *fired and refused* and
        *never fired* must be three readings. `wal_enqueued` / `wal_durable` come
        off the WAL OBJECT rather than being re-counted here, so a booker that
        thought it wrote and a WAL that did not are visibly different.
        """
        return {
            "wal_path": str(self._wal.path),
            "firings_seen": self.firings_seen,
            "booked": self.booked,
            "refused": self.refused,
            "wal_enqueued": self._wal.enqueued,
            "wal_durable": self._wal.durable,
            "wal_state": self._wal.state.value,
            "last_error": self.last_error,
        }


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """Serialise into a sibling temp file and `os.replace` it into place.

    NOT fsynced, and the omission is deliberate and matches
    `nixsentinel/heartbeat.py`: these are LIVE runtime values whose consumer asks
    "what does the process say right now", not evidence that must outlive the
    box. §9's Plane-1 log is the evidence plane and this is not it.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.write(fd, blob.encode("utf-8"))
        os.close(fd)
        os.chmod(tmp, _MODE)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _runtime_record(
    loop: LimiterLoop,
    *,
    boot_ts: float,
    stopped_ts: float | None,
    booker: Plane1Booker | None = None,
) -> dict[str, Any]:
    """`limiter.runtime.json`'s content, at boot and again at clean stop.

    Both records have the SAME shape, so the boot record and the stop record are
    read by one reader and differ only in what they say. `flat` is DERIVED from
    the live registry rather than asserted: at boot it is true because the
    registry is empty by construction, and writing `true` unconditionally would
    make the field an announcement instead of a measurement.
    """
    holders = loop.in_flight_holders()
    return {
        "schema": RUNTIME_SCHEMA,
        "pid": os.getpid(),
        "boot_ts": boot_ts,
        "flat": not holders,
        "registrations": list(loop.registry.registered()),
        "in_flight": [list(pair) for pair in holders],
        #: §12A:831's T, in the record the gate reads. Written rather than
        #: inferable because `check_go_timeout` has to distinguish *the breaker
        #: did not fire* from *the breaker was configured never to*.
        "go_timeout_s": loop.go_timeout_s,
        "go_armed": [[sid, cid, round(el, 3)] for sid, cid, el in loop.go_armed()],
        #: ARC 042 / D3.425. §9's evidence-plane counters, so an out-of-process
        #: reader can tell *fired and booked* from *fired and refused* from
        #: *never fired*. `None` only if the booker could not be built, which
        #: `main` refuses to boot on.
        "plane1": None if booker is None else booker.record(),
        "stopped_ts": stopped_ts,
    }


def _stop_record(
    loop: LimiterLoop,
    stop: LoopStop,
    *,
    boot_ts: float,
    stopped_ts: float,
    booker: Plane1Booker | None = None,
) -> dict[str, Any]:
    """The clean-stop record: the boot shape plus what the run actually did."""
    record = _runtime_record(
        loop, boot_ts=boot_ts, stopped_ts=stopped_ts, booker=booker
    )
    record.update(
        {
            # `flat` comes from the STOP OBSERVATION here, not from the live
            # registry `_runtime_record` re-derives it from. Every other field in
            # this record is `stop`'s, and `LoopStop` is explicitly the state
            # observed AFTER the loop exited and the sender was joined — reading
            # one field of a stop record off a still-mutable object while the
            # other eleven come from the snapshot is the split source directive 3
            # forbids. The two agree today because nothing mutates the registry
            # after `run()` returns; the day something does, this field would
            # have been the one that quietly stopped describing the same moment
            # as the eleven beside it.
            "flat": stop.flat,
            "reason": stop.reason,
            "ticks": stop.ticks,
            "heartbeats": stop.heartbeats,
            "last_seq": stop.last_seq,
            "last_beat_ts": stop.last_beat_ts,
            "sender_alive": stop.sender_alive,
            "sender_joined": stop.sender_joined,
            "sender_handoffs": stop.sender_handoffs,
            "sender_ledger": [
                {"seq": row.seq, "tick": row.tick, "payload": repr(row.payload)}
                for row in loop.sender.ledger()
            ],
            "overruns": stop.overruns,
            # THE EVIDENCE `checks/check_go_timeout.py` READS. One row per
            # §4:210-212 firing, each carrying its own elapsed against its own
            # T, so a breaker that fired on EVERY GO is distinguishable from one
            # that fired on a lost one — a bare count is not.
            "go_timeouts": [
                {
                    "strategy_id": row.strategy_id,
                    "client_order_id": row.client_order_id,
                    "admitted_tick": row.admitted_tick,
                    "fired_tick": row.fired_tick,
                    "elapsed_s": row.elapsed_s,
                    "timeout_s": row.timeout_s,
                    "released": row.released,
                    "resent": row.resent,
                    "reason": row.reason,
                }
                for row in stop.go_timeouts
            ],
            "faults": list(stop.faults),
        }
    )
    return record


def _parser() -> argparse.ArgumentParser:
    """The CLI. FIXED CONTRACT — the out-of-process gate is written against it."""
    parser = argparse.ArgumentParser(
        prog="limiterd",
        description=(
            "Run the §5:322 Limiter event loop as a process: one ticking thread, "
            "one low-priority sender thread, and the §12.1:604 heartbeat "
            "published from the tick."
        ),
    )
    parser.add_argument(
        "--runtime-dir",
        required=True,
        help=(
            "Directory holding the heartbeat, inbox/, outbox/ and "
            "limiter.runtime.json. Created if absent."
        ),
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=None,
        help=(
            "Seconds between beats. Default: §12A:832 heartbeat_interval_s from "
            "risks/limiter.config.json. Overridable so a test can run the loop "
            "fast; the shipped value is the one the Sentinel's threshold derives "
            "from and production must not pass this."
        ),
    )
    parser.add_argument(
        "--tick-interval",
        type=float,
        default=None,
        help=(
            "Seconds between ticks. Default: the heartbeat interval divided by "
            "nixrisk.loop.TICKS_PER_HEARTBEAT (a declared Nix addition — §12A "
            "names no tick cadence)."
        ),
    )
    parser.add_argument(
        "--go-timeout",
        type=float,
        default=None,
        help=(
            "Seconds a GO may hold the §4:208 one-in-flight lock with no "
            "terminal feedback before §4:210-212's deadlock breaker releases it. "
            "Default: §12A:831 go_timeout_s from risks/limiter.config.json. "
            "Overridable so a control can drive the breaker inside a test's "
            "budget; the shipped value is the one the platform ISSUES to every "
            "strategy in its REGISTER_ACK (nix_strategy_contract_v1.1.md §4.2) "
            "and production must not pass this."
        ),
    )
    parser.add_argument(
        "--plane1-wal",
        default=None,
        help=(
            "Path to §9's durable local Plane-1 WAL this process appends the "
            f"§12.10 go_timeout row to. Default: {PLANE1_WAL_NAME} inside the "
            "runtime directory. The shared-pool writer that group-commits it "
            "into Postgres is a different process and is not started here."
        ),
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=0,
        help=(
            "Stop cleanly after this many ticks. 0 or absent = run forever. A "
            "safety stop so a stray daemon cannot outlive the test that started it."
        ),
    )
    return parser


def _install_signal_handlers(loop: LimiterLoop) -> None:
    """`SIGTERM`/`SIGINT` -> `loop.stop()`. The clean death of §12.2:617.

    The handler does nothing but set a flag and record a reason. Anything that
    could block inside a handler would turn the supervisor's polite `SIGTERM`
    into its follow-up `SIGKILL`, which is the death that leaves no `stopped_ts`.
    """

    def _handler(signum: int, frame: FrameType | None) -> None:
        del frame
        loop.stop(f"{SITE}: {signal.Signals(signum).name} received (§12.2:617)")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


# R0914 (too-many-locals): `main` is a BOOT SEQUENCE, and every local is one
# thing the process must resolve before it may tick — the two intervals, the
# three directories, the publisher, the knob, the loop, the WAL path, the booker,
# the boot stamp, the record path. ARC 042 added two (`wal_path`, `booker`) and
# crossed the threshold. Extracting a helper to satisfy the counter would split
# the boot across two frames while leaving the same number of things resolved,
# and the `except` below — which turns ANY boot failure into a loud exit 2 with
# no runtime directory to write into — has to wrap all of them or it wraps a lie.
# pylint: disable=too-many-locals
def main(argv: list[str] | None = None) -> int:
    """Boot, run, and write the documented final state. Returns the exit code.

    Exit 0 is a CLEAN stop — signalled or `--max-ticks` reached — and the stop
    record on disk is what says which. Exit 2 is a refusal to boot at all
    (unreadable config, a runtime directory that cannot be made), and it is loud
    on stderr because there is no runtime directory to write it into.
    """
    args = _parser().parse_args(argv)
    runtime_dir = Path(args.runtime_dir).resolve()
    try:
        interval = (
            heartbeat_interval_from_config()
            if args.heartbeat_interval is None
            else float(args.heartbeat_interval)
        )
        tick = (
            tick_interval_for(interval)
            if args.tick_interval is None
            else float(args.tick_interval)
        )
        inbox_dir = runtime_dir / INBOX_DIR
        outbox_dir = runtime_dir / OUTBOX_DIR
        for directory in (runtime_dir, inbox_dir, outbox_dir):
            directory.mkdir(parents=True, exist_ok=True)
        publisher = HeartbeatPublisher(runtime_dir / HEARTBEAT_NAME)
        go_timeout = (
            go_timeout_from_config()
            if args.go_timeout is None
            else float(args.go_timeout)
        )
        loop = LimiterLoop(
            heartbeat=publisher,
            heartbeat_interval_s=interval,
            tick_interval_s=tick,
            go_timeout_s=go_timeout,
            max_ticks=max(0, int(args.max_ticks)),
        )
        # ARC 042. Opened BEFORE the loop runs and a failure REFUSES THE BOOT:
        # §12.10's go_timeout row gates money, and a Limiter that cannot write
        # its evidence plane must not start rather than trade unrecorded. This
        # is the boot half of §12.4 — the RUNNING half (a WAL that goes
        # disk-critical mid-run) is the WAL's own policy and is contained in
        # `Plane1Booker.book_new_firings`, which never kills the tick.
        wal_path = (
            runtime_dir / PLANE1_WAL_NAME
            if args.plane1_wal is None
            else Path(args.plane1_wal)
        )
        booker = Plane1Booker(loop, Plane1Wal(wal_path))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        print(
            f"{SITE}: refusing to boot the Limiter: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    # Wired after construction because both collaborators need the loop, and the
    # loop must own them rather than the other way round: §5:322's serial
    # processing means the inbox read and the command handling happen INSIDE the
    # tick, not on either collaborator's own schedule.
    loop.attach(
        # ARC 042: the booking runs FIRST inside the tick, then the inbox read.
        # `Plane1Booker.before` composes the two rather than folding the write
        # into the reader — see its docstring for why it is one tick behind the
        # firing and why nothing is lost to that.
        ingress=booker.before(Inbox(inbox_dir, loop).drain),
        handler=CommandHandler(loop, outbox_dir).handle,
    )

    boot_ts = time.time()
    runtime_path = runtime_dir / RUNTIME_NAME
    _write_json_atomically(
        runtime_path,
        _runtime_record(loop, boot_ts=boot_ts, stopped_ts=None, booker=booker),
    )
    _install_signal_handlers(loop)

    stop = loop.run()

    # The TAIL booking. The ingress books the previous tick's firings, so a
    # breaker that fired on the LAST tick before the stop would otherwise leave
    # a released lock with no §9 row — the exact D3.425 shape, surviving in the
    # one tick this arc could not reach from inside the loop. Idempotent by the
    # same key set, so a firing already booked in the tick is not booked twice.
    booker.book_new_firings()

    _write_json_atomically(
        runtime_path,
        _stop_record(
            loop, stop, boot_ts=boot_ts, stopped_ts=time.time(), booker=booker
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
