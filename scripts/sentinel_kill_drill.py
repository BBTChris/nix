#!/usr/bin/env python3
"""The §12.1 deadman drill: a REAL Limiter killed, a REAL Sentinel watching.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 034 / sub-agent B (B3). Same shape and same reason as
`scripts/feed_kill_drill.py`: the property under test is *"heartbeat lost and
positions possibly open ⇒ emergency flatten-all"* (§12.1:604-605), and that
property is only falsifiable against a process that really died.

------------------------------------------------------------------------------
WHY A DRILL AND NOT AN IN-PROCESS TEST
------------------------------------------------------------------------------
An in-process double that stops returning heartbeats measures the watchdog's
arithmetic and nothing else. It cannot distinguish a Sentinel that works from
one that would have shared the Limiter's fate, because there is no Limiter and
no fate. **A Sentinel tested only against a live Limiter has never done its
job.** So:

* the publisher is a real `fork`+`exec`ed interpreter running the real
  `nixsentinel.heartbeat.HeartbeatPublisher`, with its own pid;
* it is killed with `SIGKILL`, which no handler can intercept and no `finally`
  can soften — the kernel's reaped wait status is recorded as the proof;
* the Sentinel is a SECOND real process which never shared an address space with
  the first, running the real `nixsentinel.watchdog.Sentinel`, the real
  `HeartbeatFile` reader and the real `MarkerWriter`;
* the flatten's acks and the pid the Sentinel observed are written to disk by
  the child, so the attribution survives the child too.

------------------------------------------------------------------------------
WHAT IS A DOUBLE HERE, AND WHY THAT IS HONEST
------------------------------------------------------------------------------
The BROKER is a double, and it has to be: there is no venue on this node and
§12.1's act is an order. `DrillBroker` satisfies the frozen
`SentinelBrokerPort` and records what it was asked to do. Everything the
property is ABOUT — the heartbeat, its loss, the marker's ordering and
durability, the decision — is the real code.

`DrillAlert` can be made to RAISE, which the seam says an `AlertPort` never
does. Driving a violating implementation is the point: §14:975 gives the exit
path zero delivery dependency, and the only way to show a broken channel cannot
cost an exit is to break one.

------------------------------------------------------------------------------
WHY THE MID-FLATTEN DEATH USES `os._exit`
------------------------------------------------------------------------------
`os._exit` skips every `finally`, every `atexit` hook and every buffer flush the
interpreter would otherwise perform. A test that raised an exception inside
`flatten_all` would prove the marker survives an EXCEPTION; only a hard exit
proves it survives a process that stops existing, which is the case §12.1:608
was written for.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess  # nosec B404 - re-executes THIS file, argv built here, no shell
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# pylint: disable=wrong-import-position
from nixsentinel.config import SentinelKnobs
from nixsentinel.heartbeat import (
    DEFAULT_HEARTBEAT_NAME,
    HeartbeatFile,
    HeartbeatPublisher,
)
from nixsentinel.marker import (
    DEFAULT_MARKER_NAME,
    MarkerReplay,
    MarkerWriter,
    as_dict,
)
from nixsentinel.seam import BrokerAck, SentinelPosition, TriggerCause
from nixsentinel.watchdog import Sentinel, WakeOutcome

#: Drill cadence. Deliberately far faster than §12A:832's one-second production
#: interval: the property is an ORDERING and a CONDITION, neither of which is a
#: function of the clock, and a drill that took thirty seconds per arm would be
#: a drill nobody runs. The RATIOS are what the real configuration fixes, and
#: they are preserved — the loss multiple and the poll fraction below satisfy the
#: same two `risk_config` boot rules the shipped `risks/sentinel.config.json`
#: does.
DRILL_INTERVAL_S = 0.05
DRILL_LOSS_MULTIPLE = 4.0
DRILL_POLL_S = 0.02
DRILL_GRACE_CYCLES = 1.0

#: How long a child may run before the drill gives up on it. A drill that hung
#: would be indistinguishable from a Sentinel that never fired.
DRILL_DEADLINE_S = 20.0

#: How long the Sentinel watches a HEALTHY publisher before the kill. Not
#: cosmetic: without it the Sentinel reads exactly one beat and every kill drill
#: classifies the loss as `frozen`, so the run never exercises the transition
#: from a Risk Engine that was demonstrably PROGRESSING to one that is dead —
#: which is the transition §12.1:604 is about. Measured: the first version of
#: this drill had no settle and reported `liveness=frozen` on a `SIGKILL`.
DRILL_SETTLE_S = 0.4

#: Modes the sentinel child understands.
MODE_NORMAL = "normal"
MODE_DIE_MID_FLATTEN = "die-mid-flatten"
MODE_ALERT_FAILS = "alert-fails"

_MODES = (MODE_NORMAL, MODE_DIE_MID_FLATTEN, MODE_ALERT_FAILS)

#: The exit code the mid-flatten child uses. A distinctive number, so a child
#: that died for any OTHER reason cannot be mistaken for the drill working.
MID_FLATTEN_EXIT = 97


def drill_knobs() -> SentinelKnobs:
    """The drill's knob set. A real `SentinelKnobs`, not a stand-in."""
    return SentinelKnobs(
        heartbeat_interval_s=DRILL_INTERVAL_S,
        heartbeat_miss_grace_cycles=DRILL_GRACE_CYCLES,
        heartbeat_loss_multiple=DRILL_LOSS_MULTIPLE,
        poll_interval_s=DRILL_POLL_S,
    )


# ---------------------------------------------------------------------------
# The doubles — the only two things here that are not production code
# ---------------------------------------------------------------------------


class DrillBroker:
    """The Sentinel's OWN session, doubled. Satisfies `SentinelBrokerPort`.

    Records every verb it was asked for, in order, to a JSON lines file, so the
    call sequence survives a child that dies. `connect` before `open_positions`
    is part of what the drill proves: a Sentinel that polled a session it had
    never opened would be reading the Limiter's, which is the shared handle
    §12.1:605 forbids.
    """

    def __init__(
        self, positions: tuple[str, ...], log: Path, *, die_on_flatten: bool = False
    ) -> None:
        self._positions = positions
        self._log = log
        self._die = die_on_flatten

    def _note(self, verb: str, detail: str = "") -> None:
        with self._log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"verb": verb, "detail": detail}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def connect(self) -> None:
        """Open this process's own session."""
        self._note("connect")

    def open_positions(self) -> tuple[SentinelPosition, ...]:
        """What the broker says is open. The AUTHORITATIVE answer (§12.1:605)."""
        self._note("open_positions", ",".join(self._positions))
        return tuple(
            SentinelPosition(symbol=symbol, size=1) for symbol in self._positions
        )

    def flatten_all(self) -> tuple[BrokerAck, ...]:
        """Close everything. In `die-mid-flatten` mode, stops existing instead."""
        self._note("flatten_all", ",".join(self._positions))
        if self._die:
            # No exception, no unwinding, no flush: the process ceases. This is
            # what §12.1:608's fix has to survive.
            os._exit(MID_FLATTEN_EXIT)  # pylint: disable=protected-access
        return tuple(
            BrokerAck(symbol=symbol, ok=True, detail="drill: closed at market")
            for symbol in self._positions
        )

    def disconnect(self) -> None:
        """Release the session. Never raises."""
        self._note("disconnect")


# R0903 (too-few-public-methods): `AlertPort` declares exactly one verb.
# pylint: disable=too-few-public-methods
class DrillAlert:
    """The operator channel, doubled. Optionally BROKEN, on purpose.

    `fail=True` makes `raise_alert` raise, which the frozen `AlertPort` says it
    never does. §14:975 gives the protective path zero delivery dependency, and
    the only way to measure that a dead channel cannot abort a flatten is to
    supply a dead channel.
    """

    def __init__(self, log: Path, *, fail: bool = False) -> None:
        self._log = log
        self._fail = fail

    def raise_alert(self, cause: TriggerCause, detail: str) -> None:
        """Tell the operator, or refuse to, loudly."""
        with self._log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"cause": cause.value, "detail": detail}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if self._fail:
            raise RuntimeError(
                "drill: the operator alert channel is DOWN. §14:975 gives the "
                "protective path zero delivery dependency, so this must not cost "
                "the flatten"
            )


# ---------------------------------------------------------------------------
# The two child roles
# ---------------------------------------------------------------------------


def _run_publisher(argv: list[str]) -> int:
    """Role `publisher`: be a Risk Engine that publishes and can be killed."""
    path, positions_open = Path(argv[0]), int(argv[1])
    publisher = HeartbeatPublisher(path)
    sys.stdout.write(json.dumps({"pid": os.getpid()}) + "\n")
    sys.stdout.flush()
    while True:
        publisher.publish(positions_open)
        time.sleep(DRILL_INTERVAL_S)


def _outcome_json(outcome: WakeOutcome) -> dict[str, Any]:
    """One wake, flattened to JSON. Every figure the verdict was reached on."""
    return {
        "cause": None if outcome.cause is None else outcome.cause.value,
        "acted": outcome.acted,
        "liveness": outcome.liveness.value,
        "heartbeat_age_s": outcome.heartbeat_age_s,
        "silence_s": outcome.silence_s,
        "symbols": list(outcome.symbols),
        "acks": [
            {"symbol": ack.symbol, "ok": ack.ok, "detail": ack.detail}
            for ack in outcome.acks
        ],
        "observed_pid": outcome.observed_pid,
        "observed_seq": outcome.observed_seq,
        "hinted_positions_open": outcome.hinted_positions_open,
        "broker_positions_open": outcome.broker_positions_open,
        "latched": outcome.latched,
        "alert_failed": outcome.alert_failed,
        "stale": outcome.stale,
        "no_progress": outcome.no_progress,
        "detail": outcome.detail,
    }


def _run_sentinel(argv: list[str]) -> int:  # pylint: disable=too-many-locals
    """Role `sentinel`: be the deadman, in a process of its own."""
    heartbeat, marker, result, broker_log, alert_log = (Path(p) for p in argv[:5])
    positions = tuple(part for part in argv[5].split(",") if part)
    mode, deadline = argv[6], float(argv[7])
    if mode not in _MODES:
        raise SystemExit(f"unknown drill mode {mode!r}; expected one of {_MODES}")
    broker = DrillBroker(
        positions, broker_log, die_on_flatten=mode == MODE_DIE_MID_FLATTEN
    )
    alert = DrillAlert(alert_log, fail=mode == MODE_ALERT_FAILS)
    sentinel = Sentinel(
        heartbeat=HeartbeatFile(heartbeat),
        broker=broker,
        marker=MarkerWriter(marker),
        alert=alert,
        knobs=drill_knobs(),
    )
    # The REAL `Sentinel.run_until`, not a loop written here. A production loop
    # that only a production process would ever run is a loop nothing has ever
    # measured; driving it from every drill arm is what makes it a subject.
    stop_at = time.monotonic() + deadline
    outcomes = sentinel.run_until(
        lambda seen: (
            time.monotonic() >= stop_at or bool(seen) and seen[-1].cause is not None
        )
    )
    result.write_text(
        json.dumps(
            {"pid": os.getpid(), "wakes": [_outcome_json(o) for o in outcomes]},
            indent=1,
        ),
        encoding="utf-8",
    )
    return 0


# ---------------------------------------------------------------------------
# The orchestrator — what the gate and the suite call
# ---------------------------------------------------------------------------


# R0902 (too-many-instance-attributes): NINE, and every one is a raw
# observation the gate reaches a verdict on — the killed pid, the kernel's
# reaped status, the child's exit code, the wakes, the marker, the broker
# calls and the alerts. Dropping one to reach seven would drop an observation
# from the evidence, which is the thing a failing drill is read for.
# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class DrillOutcome:
    """One complete drill, with every raw observation kept.

    Nothing here is a verdict. The gate decides; this records what happened, so
    a failure can be read rather than guessed at.
    """

    publisher_pid: int
    #: The KERNEL's reaped status for the publisher. `-9` is `SIGKILL` and is the
    #: proof that the process was killed rather than allowed to exit.
    publisher_status: int | None
    sentinel_pid: int | None
    sentinel_returncode: int | None
    wakes: tuple[dict[str, Any], ...]
    marker_records: tuple[dict[str, Any], ...]
    broker_calls: tuple[dict[str, Any], ...]
    alerts: tuple[dict[str, Any], ...]
    detail: str = ""


def _jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    """Every JSON line in a file, in order. Empty when the file is absent."""
    if not path.is_file():
        return ()
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def _marker_dump(path: Path) -> tuple[dict[str, Any], ...]:
    """The marker, read back through the REAL `MarkerReplay`.

    Rendered by `nixsentinel.marker.as_dict`, the writer's OWN mapping, rather
    than a second spelling here: two descriptions of one wire format can disagree
    about a field name, and the drill's report would then be about a shape the
    file never had (directive 3, doctrine C.9).
    """
    return tuple(as_dict(record) for record in MarkerReplay(path).read_pending())


def _spawn(role: str, args: list[str]) -> subprocess.Popen[str]:
    """Launch one child role under this interpreter, with `scripts/` importable."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SCRIPTS)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.Popen(  # nosec B603 - argv built here, no shell
        # pylint: disable=consider-using-with
        [sys.executable, str(Path(__file__).resolve()), role, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _await_first_beat(path: Path, deadline: float) -> bool:
    """Block until the publisher has really published. Never assume it has."""
    stop_at = time.monotonic() + deadline
    while time.monotonic() < stop_at:
        if path.is_file() and path.stat().st_size:
            return True
        time.sleep(0.01)
    return False


def run_drill(  # pylint: disable=too-many-locals
    workdir: Path,
    *,
    positions: tuple[str, ...] = ("MES",),
    mode: str = MODE_NORMAL,
    kill: bool = True,
    deadline: float = DRILL_DEADLINE_S,
) -> DrillOutcome:
    """Run one drill end to end and return every raw observation.

    `kill=False` is the CONTROL arm: the same publisher, the same Sentinel, the
    same duration — and no death. §12.1:605's nuisance flatten is its own hazard,
    and the only way to show it did not fire is to run the identical drill with
    the one variable removed.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    # The FILENAMES come from the modules that own them, never retyped here: a
    # drill reporting on `sentinel_marker.jsonl` while the writer had been moved
    # to another name would report on a file nobody writes (directive 3).
    heartbeat = workdir / DEFAULT_HEARTBEAT_NAME
    marker = workdir / DEFAULT_MARKER_NAME
    result = workdir / "sentinel_result.json"
    broker_log = workdir / "broker_calls.jsonl"
    alert_log = workdir / "alerts.jsonl"
    hint = len(positions)

    publisher = _spawn("publisher", [str(heartbeat), str(hint)])
    try:
        if publisher.stdout is None:
            # A `raise`, never an `assert`: `python -O` strips asserts, and a
            # drill whose pre-flight vanishes under an optimisation flag would
            # report on a publisher it never spoke to.
            raise RuntimeError(
                "the drill publisher was launched with no readable stdout, so "
                "its pid cannot be learned and nothing can be attributed to it"
            )
        publisher_pid = int(json.loads(publisher.stdout.readline())["pid"])
        if not _await_first_beat(heartbeat, deadline):
            raise RuntimeError(
                f"the drill publisher (pid {publisher_pid}) never wrote a "
                f"heartbeat to {heartbeat}; a Sentinel drill against a publisher "
                "that never published measures nothing"
            )
        sentinel = _spawn(
            "sentinel",
            [
                str(heartbeat),
                str(marker),
                str(result),
                str(broker_log),
                str(alert_log),
                ",".join(positions),
                mode,
                str(deadline),
            ],
        )
        # Let the Sentinel watch a LIVE Risk Engine first, so the kill is a
        # transition it observes rather than the only state it has ever seen.
        time.sleep(DRILL_SETTLE_S)
        status = _kill_publisher(publisher, publisher_pid) if kill else None
        sentinel.communicate(timeout=deadline + 10.0)
        returncode = sentinel.returncode
    finally:
        _reap(publisher)
    wakes = ()
    if result.is_file():
        wakes = tuple(json.loads(result.read_text(encoding="utf-8"))["wakes"])
    return DrillOutcome(
        publisher_pid=publisher_pid,
        publisher_status=status,
        sentinel_pid=sentinel.pid,
        sentinel_returncode=returncode,
        wakes=wakes,
        marker_records=_marker_dump(marker),
        broker_calls=_jsonl(broker_log),
        alerts=_jsonl(alert_log),
        detail=f"mode={mode} kill={kill} positions={positions}",
    )


def _kill_publisher(proc: subprocess.Popen[str], pid: int) -> int:
    """`SIGKILL` the publisher and return the KERNEL's reaped wait status.

    By pid, and only the pid this drill spawned. `SIGKILL` because no handler can
    intercept it and no `finally` can soften it: a `SIGTERM` would let the
    publisher tidy up, and a Limiter that got to tidy up is not the Limiter
    §12.1:604 is about.
    """
    os.kill(pid, signal.SIGKILL)
    proc.wait(timeout=10.0)
    return proc.returncode


def _reap(proc: subprocess.Popen[str]) -> None:
    """Make sure no drill child outlives the drill. Never raises."""
    if proc.poll() is None:
        try:
            proc.kill()
            proc.wait(timeout=5.0)
        except OSError, subprocess.SubprocessError:
            pass
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()


def main(argv: list[str]) -> int:
    """`publisher` and `sentinel` are child roles; anything else is an error."""
    if not argv:
        raise SystemExit("usage: sentinel_kill_drill.py <publisher|sentinel> ...")
    role, rest = argv[0], argv[1:]
    if role == "publisher":
        return _run_publisher(rest)
    if role == "sentinel":
        return _run_sentinel(rest)
    raise SystemExit(f"unknown drill role {role!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
