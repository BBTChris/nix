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
pass, no reservations, no stops, no Plane-1 writer, and no GO-timeout
(§4:210-212 is explicitly out of this arc). It is the SUBSTRATE: a single-
threaded loop that beats, a low-priority sender thread that records, and a live
`StrategyRegistry` that outlives the commands it serves. Anything else a reader
wants from a Limiter is in `nixrisk/` and is not wired to this process yet.

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
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Final

from nixrisk.loop import (
    LimiterLoop,
    LoopStop,
    heartbeat_interval_from_config,
    tick_interval_for,
)
from nixrisk.recovery import RecoveryError
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
VERBS: Final[tuple[str, ...]] = (VERB_REGISTER, VERB_GO, VERB_STATUS)


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
    loop: LimiterLoop, *, boot_ts: float, stopped_ts: float | None
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
        "stopped_ts": stopped_ts,
    }


def _stop_record(
    loop: LimiterLoop, stop: LoopStop, *, boot_ts: float, stopped_ts: float
) -> dict[str, Any]:
    """The clean-stop record: the boot shape plus what the run actually did."""
    record = _runtime_record(loop, boot_ts=boot_ts, stopped_ts=stopped_ts)
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
        loop = LimiterLoop(
            heartbeat=publisher,
            heartbeat_interval_s=interval,
            tick_interval_s=tick,
            max_ticks=max(0, int(args.max_ticks)),
        )
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
        ingress=Inbox(inbox_dir, loop).drain,
        handler=CommandHandler(loop, outbox_dir).handle,
    )

    boot_ts = time.time()
    runtime_path = runtime_dir / RUNTIME_NAME
    _write_json_atomically(
        runtime_path, _runtime_record(loop, boot_ts=boot_ts, stopped_ts=None)
    )
    _install_signal_handlers(loop)

    stop = loop.run()

    _write_json_atomically(
        runtime_path,
        _stop_record(loop, stop, boot_ts=boot_ts, stopped_ts=time.time()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
