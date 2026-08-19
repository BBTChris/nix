#!/usr/bin/env python3
# pylint: disable=duplicate-code,too-many-lines
# C0302 (too-many-lines): one arm per declared property, each carrying its own
# reason string — an operator reads those instead of the code, and
# `docs/nix_check_contract.md` §5.5 keeps ONE gate to ONE property, so splitting
# the arms across two check modules would create a second gate over half a
# property. §4.2 forbids the shared helper module that is the only other way to
# shorten this file.
# C0415 (import-outside-toplevel): the heartbeat READER is imported inside the
# measurement, deliberately. A reader that cannot be imported must make this gate
# CANNOT_MEASURE through its own `except` (doctrine B.2); a module-level import
# would instead make the check uncollectable, which is a runner error rather than
# a verdict.
# pylint: disable=import-outside-toplevel
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`ON_FAIL`/
# `SUBJECTS`, and the `standalone_main` `__main__` — against every other check's.
# That similarity is the CONTRACT (`docs/nix_check_contract.md` §4.2, §4.4):
# every check declares the same symbols and must be independently runnable, so
# the blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter.
"""Gate: the Limiter daemon is a REAL RUNNING PROCESS whose §12.1 heartbeat
advances BECAUSE THE LOOP TICKED — and stops advancing the instant it dies.

Every bare `§` in this file cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec. Where another document is meant it is named on the line.

ARC 039 / sub-agent B. ONE gate, ONE property (`docs/nix_check_contract.md`
§5.5). Subjects: `scripts/limiterd.py` and `scripts/nixrisk/loop.py`, driven as a
REAL `fork`+`exec`ed process with its own pid — never imported and never ticked
by hand.

------------------------------------------------------------------------------
WHY THIS GATE EXISTS AND WHY IT IS NOT A SECOND OPINION (doctrine C.9)
------------------------------------------------------------------------------
Three gates in this tree stand near this subject and none of them owns it:

* `check_limiter_seam` reads `scripts/nixrisk/seam.py` STATICALLY and says so in
  its own docstring — it judges DECLARATIONS.
* `check_limiter_gate` drives `scripts/nixrisk/gate.py`'s two-phase pass IN
  PROCESS. A pass that ran is not a daemon that is running.
* `check_sentinel_deadman` kills a real publisher and proves the WATCHER acts.
  Its publisher is `scripts/sentinel_kill_drill.py`'s drill child — a purpose-
  built interpreter that calls `HeartbeatPublisher.publish` in a `for` loop. It
  proves the Sentinel's side of §12.1:603-605 and deliberately proves nothing
  about the Limiter's side, because until this arc there WAS no Limiter daemon.

So the LIMITER's half of §12.1:603 — *"Watches the Risk-Engine heartbeat"*
requires something to publish one from the loop that holds the synthetic stops —
was unowned. This gate owns it and nothing else. It does not re-judge the
Sentinel's response (that is `check_sentinel_deadman`), does not re-judge the
gate pass, and does not re-judge the seam.

------------------------------------------------------------------------------
THE PROPERTY, STATED SO IT CAN BE FALSIFIED
------------------------------------------------------------------------------
"The heartbeat advances" is not the property. A `cron` job, a stray thread, an
orphaned grandchild or a test fixture can all advance a counter in a file. The
property is **the heartbeat advances if and only if the Limiter's loop is
ticking**, and the only way to falsify the "only if" half is to KILL the loop and
watch the counter stop. §12.1:604-605 spends the Sentinel's entire authority on
that inference: heartbeat lost ⇒ emergency flatten-all. A heartbeat that can
advance without the loop makes the Sentinel blind to a dead Limiter — the
positions keep their synthetic stops on paper and nothing holds them.

FIVE ARMS, each a different way for that inference to be false:

  * **ARM 1 — IT IS A REAL OS PROCESS.** `scripts/limiterd.py` is launched
    through `sys.executable` with a bounded `--max-ticks`, and the verdict reads
    `/proc/<pid>` — not the daemon's own account of itself. `/proc/<pid>/cmdline`
    must NAME `limiterd.py`, because a pid alone is a recycled integer and a gate
    that checked only `/proc/<pid>` existence would go green against whatever
    process the kernel handed that number next. `/proc/<pid>/task` must show at
    least two threads, which is §5:322-324's shape — *"single-threaded event
    loop … + one low-priority sender thread"* — and is the cheapest external
    evidence that the thing running is the architecture the spec fixes rather
    than a script that sleeps.

  * **ARM 2 — THE BEAT CLIMBS, AND IT IS THIS PROCESS'S BEAT.** The record is
    read from OUTSIDE the daemon's interpreter with the shipped
    `nixsentinel.heartbeat.HeartbeatFile`, sampled repeatedly, and `seq` must
    CLIMB monotonically while the process lives. Every sample's `pid` must equal
    the pid this gate launched: a heartbeat naming another pid is another
    process's heartbeat, and reading it as this one's is the exact confusion
    `nixsentinel/heartbeat.py` says `pid` exists to prevent.

  * **ARM 3 — IT DIES AND THE BEAT DIES WITH IT.** `SIGKILL` — uncatchable, no
    handler, no `finally` — then `/proc/<pid>` must be GONE (after the kernel has
    reaped it, so the check is not reading a zombie), and `seq` must be FROZEN
    across a further sampling window. **This is the arm the whole gate is for.**
    An advancing counter after the kill is a §12.1 catastrophe wearing a green.

  * **ARM 4 — THE LOCK IS LIVE STATE THE RUNNING LOOP OWNS.** §4:208-209 —
    *"one in-flight action per strategy. While an order is pending, the
    strategy's next signal is rejected-with-reason until resolution."* Driven
    through the daemon's file inbox from another process: `register`, then `go`,
    then a SECOND `go` for the same `strategy_id`. The second must be refused,
    and **the refusal's REASON is asserted** — the §4 citation and the
    `client_order_id` actually holding the lock — never `accepted=false` alone
    (check contract v2 §11 / `docs/nix_check_contract.md` §18). `accepted=false`
    is one boolean shared by every possible denial; a loop that refused every
    `go` would satisfy it.

  * **ARM 5 — RESTART IS FLAT (§12.2:617-618).** *"Boot-flatten makes any single
    restart safe by design."* The daemon is relaunched INTO THE SAME RUNTIME
    DIRECTORY the killed one left behind — holding a registration and an
    in-flight lock — and its boot record must read `flat: true` with EMPTY
    `registrations` and `in_flight`, under a NEW pid, with `seq` restarted below
    the value the dead process reached. Reusing the dirty directory is the point:
    a restart into a clean directory proves only that a fresh process is fresh.

------------------------------------------------------------------------------
WHY THE VERDICT ORDER IS DEFECTS FIRST, FLOORS SECOND
------------------------------------------------------------------------------
`check_sentinel_deadman` checks its non-vacuity floors BEFORE its arms. This gate
does the opposite, on purpose, and the reason is specific to what is being
measured here: **the subject can silence the instrument by dying.** A daemon that
exits immediately produces zero heartbeat samples, and a sample-count floor
evaluated first would report CANNOT_MEASURE — an amber that says "I could not
look" about a subject this gate looked at and watched die. That would let the
worst defect in scope buy the mildest verdict, which is the "break the instrument
to go amber" escape.

A floor exists to stop a vacuous PASS, so it never needs to outrank a FAIL. The
things that genuinely mean *the instrument could not look* — the entrypoint
absent, `exec` failing, `/proc` not mounted, the shipped heartbeat reader not
importable — are raised as `_Unmeasurable` BEFORE any arm runs, because in those
cases there is no observation to judge at all.

------------------------------------------------------------------------------
`docs/debug.md` §7.12 — THE STANDING QUESTION, asked at the point this gate was
built: *what would have to be true for this to PASS while measuring nothing?*
------------------------------------------------------------------------------
 1. *`scripts/limiterd.py` is absent and "no daemon misbehaved" reads as green.*
    Closed: a missing entrypoint is `_Unmeasurable` (exit 2) naming the path,
    before anything else happens.
 2. *The process never started — `exec` failed, the interpreter is wrong — and
    the empty observation passes.* Closed: an `OSError` from `Popen` is
    `_Unmeasurable`, and a process that started and then EXITED is a positively
    observed ARM 1 defect rather than an absence.
 3. *No heartbeat was ever published and there was nothing to disagree with.*
    Closed twice: fewer than `MIN_ALIVE_SAMPLES` readable beats is a refusal
    (`_floor_refusal`) rather than a pass, and a live process that published
    nothing is an ARM 2 defect naming the file that never appeared.
 4. *`seq` "climbed" over a window too short to contain a real beat.* Closed by
    `MIN_SEQ_ADVANCE`: the observed climb must be at least three beats, a floor
    deliberately far BELOW what the configured interval yields in the window
    (doctrine C.4 — a floor, never today's figure) and never zero.
 5. *The frozen-after-death arm passes because nothing was sampled after the
    kill.* Closed by `MIN_FROZEN_SAMPLES`: a refusal, not a pass, if the
    post-mortem window produced fewer than three readings.
 6. *The heartbeat being read belongs to some other process.* Closed by ARM 2
    comparing every sample's `pid` against the pid THIS gate launched, and by
    ARM 1 reading `/proc/<pid>/cmdline` — a pid is a recycled integer and the
    cmdline is what makes the identity non-circular.
 7. *`/proc/<pid>` "disappeared" because the check looked at a zombie's parent,
    or looked before the kernel had finished.* Closed by reaping the child with
    `Popen.wait()` BEFORE the `/proc` read, and by requiring the reaped status to
    be exactly `-SIGKILL` — the kernel's account, not the gate's.
 8. *The one-in-flight arm passes on `accepted=false` produced by a loop that
    refuses everything.* Closed by requiring the FIRST `go` to be ACCEPTED and
    the second's reason to name both a `§` citation and the holding
    `client_order_id` — a constant refusal fails the first, and a generic refusal
    fails the second.
 9. *The restart arm passes because the restart was into a clean directory.*
    Closed by reusing the KILLED process's runtime directory, which still holds
    its registration, its in-flight lock and its high-water `seq`.
10. *Every arm inspects and none of them counts.* Closed by the four floors
    above plus `MIN_REPLIES`, all of them floors below today's figures and none
    of them zero.

------------------------------------------------------------------------------
WHAT A GREEN HERE DOES NOT MEAN, stated rather than implied
------------------------------------------------------------------------------
There is no venue on this node, so nothing here is proof that an order reached a
broker. The command inbox is a FILE inbox and is not §5:322's ZMQ inbox; this
gate proves the loop drains commands and owns the lock, never that the transport
is the one the spec names. There is no systemd unit for this daemon, so §12.2's
supervisor is not exercised — only the "restart is flat" half of :617-618. And a
green says nothing about the Sentinel's response to the death this gate causes;
`check_sentinel_deadman` owns that and is the gate to read beside this one.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess  # nosec B404 - launches sys.executable with a literal argv, no shell
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. The daemon is launched through `sys.executable` and
#: imports only the standard library plus `scripts/`, so there is no third-party
#: dependency and therefore no `check_venv` edge.
DEPENDS_ON: tuple[str, ...] = ()
#: Declared HONESTLY, because check contract v2 §12 / `nix_check_contract.md`
#: §4.4 checks DECLARED claims against OBSERVED ones, and `()` on a gate that
#: forks processes is measurable rather than trusted.
#: * `subprocess:python` / `subprocess:python3` — this gate launches
#:   `scripts/limiterd.py` through `sys.executable` twice. BOTH spellings,
#:   because the observer matches a subprocess claim by BASENAME and
#:   `sys.executable` is `.venv/bin/python` under pytest and `/usr/bin/python3`
#:   under `nix-verify.service`.
#: * `file-write:/tmp` — the runtime directory, the command inbox and the
#:   daemon's captured output all live inside one `tempfile.TemporaryDirectory`.
#: * `interpreter:sys.path` / `interpreter:sys.modules` — `_preamble` puts
#:   `scripts/` on the path and the heartbeat reader is imported inside the
#:   measurement.
RESOURCES: tuple[str, ...] = (
    "subprocess:python",
    "subprocess:python3",
    "file-write:/tmp",
    "interpreter:sys.path",
    "interpreter:sys.modules",
)
#: TRUE, and every wait in this file carries a deadline. A gate that hung waiting
#: for a beat would be indistinguishable from a Limiter that never published one,
#: which is the single outcome this instrument must never leave ambiguous.
TIME_BOUND = True
#: CONTINUE. A dead Limiter loop is a catastrophic finding but it is not a
#: finding that makes the REST of the run unreadable, which is the only thing
#: `"halt"` buys (`nix_check_contract.md` §4.4 / AMENDMENT 5): halting is for a
#: check whose failure invalidates every check after it, as `check_python_runtime`
#: and `check_venv` do. Declaring `"halt"` here would also force this gate into
#: its own single-check block for a reason it does not have.
ON_FAIL = "continue"
#: NON-CORRECTABLE. Every arm measures the behaviour of a real process under a
#: real death. The only "repair" for a loop whose heartbeat outlives it is to
#: change the loop — an instrument empowered to do that would be writing the
#: trading code it exists to judge, and would be manufacturing its own green.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every arm measures a real process under a real SIGKILL, and the only repair "
    "for a heartbeat that advances without the loop is to change the loop. An "
    "instrument that could do that would be manufacturing its own green -- the "
    "same objection that makes check_sentinel_deadman non-correctable, one "
    "process boundary away"
)
#: Genuinely MEASURED: the entrypoint is executed as a real process and the loop
#: module is the code that process runs. Neither is merely named.
SUBJECTS: tuple[str, ...] = (
    "scripts/limiterd.py",
    "scripts/nixrisk/loop.py",
)

NAME = "check_limiter_loop_alive"

ENTRYPOINT = "scripts/limiterd.py"
LOOP_MODULE = "scripts/nixrisk/loop.py"
#: The boot record's name, fixed by the daemon's contract. The HEARTBEAT's name
#: is NOT spelled here — it is read from `nixsentinel.heartbeat` at run time, so
#: the publisher and this reader cannot drift apart (directive 3).
RUNTIME_RECORD = "limiter.runtime.json"

#: The strategy this gate drives. Deliberately not a plausible production id: a
#: run that leaked into a real runtime directory should be obvious in the record.
STRATEGY_ID = "GATE-LIMITER-LOOP-ALIVE"
#: The `client_order_id` that will HOLD the §4:208 lock. ARM 4 requires the
#: second `go`'s refusal to name this exact string.
HOLDING_COID = "COID-HOLDS-THE-LOCK"
#: The second `go`'s id. It must be refused, so it must never appear as a holder.
BLOCKED_COID = "COID-MUST-BE-REFUSED"

#: Cadence the daemon is launched with. Fast enough that a second-scale window
#: contains tens of beats, slow enough that the loop is doing real work per tick.
HEARTBEAT_INTERVAL_S = 0.05
TICK_INTERVAL_S = 0.05
#: The BACKSTOP, not the plan. This gate kills the daemon itself; `--max-ticks`
#: bounds it anyway so that a gate which crashed between launch and kill cannot
#: leave a daemon running on the node. 600 ticks at 0.05s is 30 seconds.
MAX_TICKS = 600

#: Deadlines. Every one of them is a refusal or a defect when it expires; none of
#: them is ever a pass.
_BOOT_DEADLINE_S = 8.0
_ALIVE_WINDOW_S = 1.2
_ALIVE_SAMPLE_GAP_S = 0.1
_FROZEN_WINDOW_S = 0.8
_FROZEN_SAMPLE_GAP_S = 0.15
_REPLY_DEADLINE_S = 2.5
_REAP_DEADLINE_S = 5.0
_RESTART_DEADLINE_S = 3.0
_POLL_GAP_S = 0.02

#: Non-vacuity floors (`docs/debug.md` §7.12). Floors, deliberately BELOW what
#: the configured cadence yields in the configured windows (doctrine C.4, so they
#: cannot become moving anchors) — but never zero.
MIN_ALIVE_SAMPLES = 6
MIN_SEQ_ADVANCE = 3
MIN_FROZEN_SAMPLES = 3
MIN_REPLIES = 3
#: §5:322-324: *"single-threaded event loop … + one low-priority sender thread"*.
MIN_THREADS = 2

#: Spellings that count as naming §4:208's concurrency rule. A set rather than a
#: single string because the sentence has two idiomatic spellings and a gate that
#: demanded one of them would be judging orthography, not the citation.
_INFLIGHT_SPELLINGS = ("in-flight", "in flight")


class _Unmeasurable(RuntimeError):
    """The instrument could not look. NEVER a verdict about the subject.

    Raised only for the four conditions in which there is no observation to
    judge: the entrypoint is absent, `exec` failed, `/proc` is not readable, or
    the shipped heartbeat reader will not import. Everything else — including a
    daemon that started and died — is a real observation and reaches an arm.
    """


class Beat(NamedTuple):
    """One heartbeat sample as read from OUTSIDE the daemon's interpreter."""

    pid: int
    seq: int
    ts: float


class Reading(NamedTuple):
    """What one run actually observed. Every field lands in the evidence."""

    launched_pid: int
    proc_present_while_alive: bool
    cmdline: str
    threads: int
    exited_early_rc: int | None
    alive_beats: tuple[Beat, ...]
    beat_errors: tuple[str, ...]
    reaped_status: int | None
    proc_present_after_reap: bool
    seq_at_death: int | None
    frozen_beats: tuple[Beat, ...]
    replies: tuple[dict[str, Any], ...]
    restart_pid: int | None
    restart_beat: Beat | None
    boot_record: dict[str, Any] | None
    stopped_record: dict[str, Any] | None
    stderr_tail: str


def _cannot_measure(detail: str) -> CheckResult:
    """Doctrine B.2: an unread subject is CANNOT_MEASURE, never PASS."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ===========================================================================
# THE INSTRUMENT — everything below reads the daemon from the OUTSIDE
# ===========================================================================


def proc_present(pid: int) -> bool:
    """`/proc/<pid>` exists. The kernel's answer, not the daemon's."""
    return Path(f"/proc/{pid}").exists()


def proc_cmdline(pid: int) -> str:
    """`/proc/<pid>/cmdline`, NUL-separated, as one readable string.

    Read because a pid is a recycled integer. `check_sentinel_deadman` can get
    away with a bare pid comparison because it spawned both sides microseconds
    apart; this gate SIGKILLs its subject and then asks whether the pid is gone,
    which is precisely the window in which the kernel may hand that number to
    something else.
    """
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def proc_threads(pid: int) -> int:
    """Threads in `/proc/<pid>/task`, or -1 if the directory cannot be read."""
    try:
        return len(os.listdir(f"/proc/{pid}/task"))
    except OSError:
        return -1


def _launch(home: Path, runtime: Path, log: Path) -> subprocess.Popen[bytes]:
    """Start the daemon as a REAL process. Raises `_Unmeasurable` on exec failure.

    Output goes to a FILE rather than a pipe: a daemon that logged enough to fill
    a pipe buffer would block on write, and the gate would then measure its own
    plumbing rather than the loop.
    """
    argv = [
        sys.executable,
        str(home / ENTRYPOINT),
        "--runtime-dir",
        str(runtime),
        "--heartbeat-interval",
        str(HEARTBEAT_INTERVAL_S),
        "--tick-interval",
        str(TICK_INTERVAL_S),
        "--max-ticks",
        str(MAX_TICKS),
    ]
    try:
        # nosec B603 - argv is built here from literals and paths, shell=False.
        handle = log.open("ab")
        return subprocess.Popen(  # nosec B603
            argv,
            cwd=str(home),
            stdout=handle,
            stderr=handle,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise _Unmeasurable(
            f"{ENTRYPOINT}: could not be executed ({exc!r}) -- the gate never "
            "obtained a process to judge, which is an instrument failure and not "
            "a finding about the loop"
        ) from exc


def _stop(proc: subprocess.Popen[bytes] | None) -> None:
    """Kill and reap, unconditionally. A gate that leaks a daemon is a defect."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.kill()
        proc.wait(timeout=_REAP_DEADLINE_S)
    except OSError, subprocess.SubprocessError:
        pass


def _tail(log: Path, limit: int = 400) -> str:
    """The last bytes the daemon wrote. Evidence when it died unexpectedly."""
    try:
        return log.read_text(encoding="utf-8", errors="replace").strip()[-limit:]
    except OSError:
        return ""


# R0903 (too-few-public-methods): ONE public verb is the whole surface, and it
# is the whole surface on purpose — this gate reads the heartbeat through
# `nixsentinel.heartbeat.HeartbeatFile`, whose frozen port declares `read` and
# nothing else. A second verb added here to satisfy a counter would be a verb
# the shipped reader does not have, and the point of binding to the shipped
# reader is that this gate cannot become a second authority on the record.
# pylint: disable=too-few-public-methods
class _Reader:
    """The heartbeat, read with the SHIPPED reader from another process.

    Bound to `nixsentinel.heartbeat.HeartbeatFile` rather than re-implemented:
    re-parsing the record here would make this gate a second authority on the
    record's shape, and the two spellings would disagree the first time either
    moved (directive 3). The errors it raises are COLLECTED rather than swallowed
    — `HeartbeatError` means "something is there and it is not a heartbeat",
    which that module's own docstring is explicit is a real fault.
    """

    def __init__(self, path: Path, cls: Any, error: type[Exception]) -> None:
        self.path = path
        self._file = cls(path)
        self._error = error
        self.errors: list[str] = []

    def sample(self) -> Beat | None:
        """One reading, or `None` for "no beat has ever been published"."""
        try:
            beat = self._file.read()
        except self._error as exc:  # pragma: no cover - a real fault, recorded
            self.errors.append(str(exc))
            return None
        except OSError as exc:
            self.errors.append(f"{self.path}: {exc!r}")
            return None
        if beat is None:
            return None
        return Beat(pid=int(beat.pid), seq=int(beat.seq), ts=float(beat.ts))


def _await_beat(
    reader: _Reader, proc: subprocess.Popen[bytes], deadline: float
) -> Beat | None:
    """Wait for the first beat, or for the process to exit. Bounded either way."""
    until = time.monotonic() + deadline
    while time.monotonic() < until:
        beat = reader.sample()
        if beat is not None:
            return beat
        if proc.poll() is not None:
            return None
        time.sleep(_POLL_GAP_S)
    return None


def _sample_window(reader: _Reader, window: float, gap: float) -> tuple[Beat, ...]:
    """Sample the heartbeat repeatedly over a wall-clock window."""
    beats: list[Beat] = []
    until = time.monotonic() + window
    while time.monotonic() < until:
        beat = reader.sample()
        if beat is not None:
            beats.append(beat)
        time.sleep(gap)
    return tuple(beats)


def _submit(runtime: Path, command: dict[str, Any]) -> None:
    """Drop one command into the daemon's inbox ATOMICALLY.

    Written to a dotfile and `os.replace`d into place. A loop that globbed
    `inbox/*.json` while this gate was still writing one would read a truncated
    command and the gate would have manufactured a defect that the daemon does
    not have.
    """
    inbox = runtime / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    tmp = inbox / f".{command['id']}.tmp"
    tmp.write_text(json.dumps(command, sort_keys=True), encoding="utf-8")
    os.replace(tmp, inbox / f"{command['id']}.json")


def _await_reply(
    runtime: Path, ident: str, proc: subprocess.Popen[bytes]
) -> dict[str, Any] | None:
    """Wait for `outbox/<id>.reply.json`. Bounded; `None` means it never came."""
    path = runtime / "outbox" / f"{ident}.reply.json"
    until = time.monotonic() + _REPLY_DEADLINE_S
    while time.monotonic() < until:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            if proc.poll() is not None:
                return None
            time.sleep(_POLL_GAP_S)
            continue
        if isinstance(payload, dict):
            return payload
        return {"id": ident, "malformed": repr(payload)}
    return None


def _drive_lock(
    runtime: Path, proc: subprocess.Popen[bytes]
) -> tuple[dict[str, Any], ...]:
    """ARM 4's drive: register, go, go. Stops early if a reply never arrives.

    Sequential rather than three files dropped at once, deliberately. Two `go`
    commands landing in the same tick would make the outcome depend on the
    daemon's within-tick ordering, and this gate would then be measuring a
    filename sort instead of §4:208's lock.
    """
    replies: list[dict[str, Any]] = []
    plan = (
        {
            "schema": 1,
            "id": "gate-register",
            "verb": "register",
            "strategy_id": STRATEGY_ID,
            "client_order_id": "COID-REGISTRATION",
        },
        {
            "schema": 1,
            "id": "gate-go-first",
            "verb": "go",
            "strategy_id": STRATEGY_ID,
            "client_order_id": HOLDING_COID,
        },
        {
            "schema": 1,
            "id": "gate-go-second",
            "verb": "go",
            "strategy_id": STRATEGY_ID,
            "client_order_id": BLOCKED_COID,
        },
    )
    for command in plan:
        _submit(runtime, command)
        reply = _await_reply(runtime, str(command["id"]), proc)
        if reply is None:
            break
        replies.append(reply)
    return tuple(replies)


def _read_record(runtime: Path) -> dict[str, Any] | None:
    """The boot record, or `None` if it is absent or not an object."""
    try:
        payload = json.loads((runtime / RUNTIME_RECORD).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return payload if isinstance(payload, dict) else None


# ===========================================================================
# THE ARMS — pure over one `Reading`, so a failing arm names itself
# ===========================================================================


def process_defects(reading: Reading) -> list[tuple[str, str]]:
    """ARM 1: it is a real OS process, and it is THIS process."""
    defects: list[tuple[str, str]] = []
    site = f"{ENTRYPOINT}:pid {reading.launched_pid}"
    if reading.exited_early_rc is not None:
        defects.append(
            (
                site,
                (
                    f"the entrypoint EXITED with rc {reading.exited_early_rc} before the "
                    "observation window closed. A Limiter is a resident loop -- a "
                    "process that runs once and returns publishes no heartbeat for the "
                    f"Sentinel to lose (§12.1:603). Daemon output: {reading.stderr_tail!r}"
                ),
            )
        )
        return defects
    if not reading.proc_present_while_alive:
        defects.append(
            (
                site,
                (
                    "/proc/<pid> did not exist while the gate believed the daemon was "
                    "running -- the kernel has no such process, so nothing was alive to "
                    "publish the beats that were read"
                ),
            )
        )
    if "limiterd.py" not in reading.cmdline:
        defects.append(
            (
                f"{site}:/proc/cmdline",
                (
                    f"the live pid's cmdline is {reading.cmdline!r}, which does not name "
                    "limiterd.py. A pid is a recycled integer; a gate satisfied by "
                    "/proc/<pid> alone would go green against whatever process the "
                    "kernel handed that number next"
                ),
            )
        )
    if reading.threads < MIN_THREADS:
        defects.append(
            (
                f"{site}:/proc/task",
                (
                    f"{reading.threads} thread(s) in /proc/<pid>/task, below the "
                    f"{MIN_THREADS} §5:322-324 fixes -- 'single-threaded event loop "
                    "... + one low-priority sender thread'. A loop with no sender "
                    "thread blocks the hot path on broker I/O, which is the race class "
                    "that shape exists to eliminate"
                ),
            )
        )
    return defects


def heartbeat_defects(reading: Reading) -> list[tuple[str, str]]:
    """ARM 2: the beat climbs while it lives, and it is this pid's beat."""
    defects: list[tuple[str, str]] = []
    site = f"{ENTRYPOINT}:risk_engine.heartbeat.json"
    if reading.exited_early_rc is not None:
        return defects
    if not reading.alive_beats:
        defects.append(
            (
                site,
                (
                    "the daemon was ALIVE for the whole observation window and no "
                    "heartbeat record was ever readable. §12.1:603 gives the Sentinel "
                    "one input; a Limiter that never writes it is already invisible"
                ),
            )
        )
        return defects
    first, last = reading.alive_beats[0], reading.alive_beats[-1]
    advance = last.seq - first.seq
    if advance < MIN_SEQ_ADVANCE:
        defects.append(
            (
                site,
                (
                    f"seq moved {first.seq} -> {last.seq} ({advance}) across "
                    f"{len(reading.alive_beats)} samples over {_ALIVE_WINDOW_S}s at a "
                    f"{HEARTBEAT_INTERVAL_S}s interval, below the floor of "
                    f"{MIN_SEQ_ADVANCE}. A heartbeat that does not advance while the "
                    "process lives is a HANG, which nixsentinel/heartbeat.py names as "
                    "the case seq exists to distinguish from a restart"
                ),
            )
        )
    regressions = [
        (before.seq, after.seq)
        for before, after in zip(reading.alive_beats, reading.alive_beats[1:])
        if after.seq < before.seq
    ]
    if regressions:
        defects.append(
            (
                site,
                (
                    f"seq went BACKWARDS at {regressions[:3]} while one process lived. "
                    "seq increments per beat per process, so a decrease means either "
                    "another process is writing this file or the counter is not derived "
                    "from the loop at all"
                ),
            )
        )
    foreign = sorted(
        {beat.pid for beat in reading.alive_beats} - {reading.launched_pid}
    )
    if foreign:
        defects.append(
            (
                f"{site}:pid",
                (
                    f"the heartbeat named pid(s) {foreign} while this gate launched pid "
                    f"{reading.launched_pid}. A beat naming another pid is another "
                    "process's beat, and reading it as this one's is exactly the "
                    "confusion the pid field exists to prevent -- the Sentinel would "
                    "then be watching a liveness signal no Limiter owns"
                ),
            )
        )
    return defects


def death_defects(reading: Reading) -> list[tuple[str, str]]:
    """ARM 3: the headline. It dies, and the beat dies with it."""
    defects: list[tuple[str, str]] = []
    site = f"{ENTRYPOINT}:SIGKILL pid {reading.launched_pid}"
    if reading.exited_early_rc is not None:
        return defects
    if reading.reaped_status != -signal.SIGKILL:
        defects.append(
            (
                site,
                (
                    f"the kernel reaped status {reading.reaped_status}, not "
                    f"-{signal.SIGKILL} (SIGKILL). The gate's whole inference rests on "
                    "the process having been killed uncatchably; a different status "
                    "means it exited some other way and the freeze below proves nothing"
                ),
            )
        )
    if reading.proc_present_after_reap:
        defects.append(
            (
                f"{site}:/proc",
                (
                    "/proc/<pid> still existed AFTER the child was reaped -- the pid was "
                    "not released, so 'the heartbeat stopped when the process died' has "
                    "not been demonstrated against a process that is actually gone"
                ),
            )
        )
    if len(reading.frozen_beats) < MIN_FROZEN_SAMPLES:
        return defects
    after = [beat.seq for beat in reading.frozen_beats]
    if reading.seq_at_death is not None and max(after) > reading.seq_at_death:
        defects.append(
            (
                f"{site}:seq advanced after death",
                (
                    f"seq was {reading.seq_at_death} when the process was reaped and "
                    f"reached {max(after)} across {len(reading.frozen_beats)} samples "
                    f"over the following {_FROZEN_WINDOW_S}s. THE HEARTBEAT ADVANCED "
                    "WITHOUT THE LOOP. §12.1:604-605 spends the Sentinel's entire "
                    "authority on the opposite inference -- heartbeat present means "
                    "Limiter alive -- so a beat that outlives its process makes the "
                    "Sentinel blind to a dead Limiter holding open positions"
                ),
            )
        )
    return defects


def _reply_shape_defects(
    reply: dict[str, Any], ident: str, launched_pid: int
) -> list[tuple[str, str]]:
    """Fields every reply must carry, whatever it decided."""
    defects: list[tuple[str, str]] = []
    site = f"{ENTRYPOINT}:outbox/{ident}.reply.json"
    if reply.get("id") != ident:
        defects.append(
            (
                site,
                (
                    f"the reply names id {reply.get('id')!r}, not {ident!r} -- a reply "
                    "that cannot be attributed to its command is a reply about "
                    "something else"
                ),
            )
        )
    if reply.get("pid") != launched_pid:
        defects.append(
            (
                f"{site}:pid",
                (
                    f"the reply names pid {reply.get('pid')!r}, not the launched "
                    f"{launched_pid}. The lock is state a RUNNING loop owns; a reply "
                    "from another process is not evidence about this one"
                ),
            )
        )
    if not isinstance(reply.get("tick"), int):
        defects.append(
            (
                f"{site}:tick",
                (
                    f"tick is {reply.get('tick')!r}, not an int -- the tick number is "
                    "what ties the decision to a loop iteration rather than to an "
                    "import-time constant"
                ),
            )
        )
    return defects


def lock_defects(reading: Reading) -> list[tuple[str, str]]:
    """ARM 4: §4:208-209's one-in-flight lock, driven from another process."""
    defects: list[tuple[str, str]] = []
    site = f"{ENTRYPOINT}:inbox"
    if reading.exited_early_rc is not None:
        return defects
    if len(reading.replies) < MIN_REPLIES:
        defects.append(
            (
                site,
                (
                    f"{len(reading.replies)} of {MIN_REPLIES} replies arrived within "
                    f"{_REPLY_DEADLINE_S}s each. A loop that does not drain its inbox "
                    "owns no lock, and §4:209's 'rejected-with-reason until resolution' "
                    "cannot be observed at all"
                ),
            )
        )
        return defects
    register, first_go, second_go = reading.replies[:3]
    for reply, ident in (
        (register, "gate-register"),
        (first_go, "gate-go-first"),
        (second_go, "gate-go-second"),
    ):
        defects.extend(_reply_shape_defects(reply, ident, reading.launched_pid))
    if register.get("accepted") is not True:
        defects.append(
            (
                f"{site}:register",
                (
                    f"registration was refused: {register.get('reason')!r}. Nothing "
                    "downstream is measurable if the strategy never registered"
                ),
            )
        )
    if first_go.get("accepted") is not True:
        defects.append(
            (
                f"{site}:first go",
                (
                    f"the FIRST go was refused: {first_go.get('reason')!r}. §4:208 "
                    "rejects the NEXT signal while one is pending; a loop that refuses "
                    "the first refuses everything, and a gate satisfied by "
                    "accepted=false on the second would call that a pass"
                ),
            )
        )
    if second_go.get("accepted") is not False:
        defects.append(
            (
                f"{site}:second go",
                (
                    "the SECOND go for the same strategy was ACCEPTED while the first "
                    f"was still in flight ({HOLDING_COID}). §4:208-209: 'one in-flight "
                    "action per strategy ... the strategy's next signal is "
                    "rejected-with-reason until resolution'"
                ),
            )
        )
        return defects
    reason = str(second_go.get("reason", ""))
    lowered = reason.lower()
    if not any(spelling in lowered for spelling in _INFLIGHT_SPELLINGS):
        defects.append(
            (
                f"{site}:second go reason",
                (
                    f"the refusal reason {reason!r} does not name the one-in-flight "
                    "rule. check contract v2 §11 -- a control asserts the REASON, "
                    "never the boolean: accepted=false is one value shared by every "
                    "possible denial, so an unnamed refusal is indistinguishable from "
                    "a loop that rejects on some other ground entirely"
                ),
            )
        )
    if "§" not in reason:
        defects.append(
            (
                f"{site}:second go citation",
                (
                    f"the refusal reason {reason!r} carries no § citation. An operator "
                    "reading a rejected signal must be able to reach the rule that "
                    "rejected it (§4:208-209)"
                ),
            )
        )
    if HOLDING_COID not in reason:
        defects.append(
            (
                f"{site}:second go holder",
                (
                    f"the refusal reason {reason!r} does not name the client_order_id "
                    f"holding the lock ({HOLDING_COID}). Without the holder the reason "
                    "cannot be acted on: §4:210-212's GO-timeout exists precisely "
                    "because a lock can wedge, and the operator's first question is "
                    "which order is holding it"
                ),
            )
        )
    return defects


def _restart_state_defects(record: dict[str, Any], site: str) -> list[tuple[str, str]]:
    """The three fields §12.2:618's boot-flatten makes true. Split out for length."""
    defects: list[tuple[str, str]] = []
    if record.get("flat") is not True:
        defects.append(
            (
                f"{site}:flat",
                (
                    f"the restarted daemon's boot record reads flat={record.get('flat')!r}. "
                    "§12.2:618 -- 'Boot-flatten makes any single restart safe by "
                    "design'. A restart that does not assert flat has inherited "
                    "exposure it never confirmed"
                ),
            )
        )
    for field in ("registrations", "in_flight"):
        value = record.get(field)
        if value != []:
            defects.append(
                (
                    f"{site}:{field}",
                    (
                        f"the restarted daemon inherited {field}={value!r} from the "
                        "runtime directory the KILLED process left behind. A restart "
                        "that resumes a dead process's lock is a restart into trading, "
                        "which §12.2:617-618 forbids by design"
                    ),
                )
            )
    return defects


def restart_defects(reading: Reading) -> list[tuple[str, str]]:
    """ARM 5: §12.2's restart is flat, driven into the DIRTY runtime directory."""
    defects: list[tuple[str, str]] = []
    site = f"{ENTRYPOINT}:{RUNTIME_RECORD}"
    if reading.restart_pid is None:
        defects.append(
            (
                site,
                (
                    "the daemon could not be relaunched after the kill, so §12.2:617-618's "
                    "restart-is-flat property was never reached"
                ),
            )
        )
        return defects
    if reading.restart_pid == reading.launched_pid:
        defects.append(
            (
                site,
                (
                    f"the restart reports the SAME pid {reading.restart_pid} as the "
                    "process this gate killed, which cannot be a fresh process"
                ),
            )
        )
    record = reading.boot_record
    if record is None:
        defects.append(
            (
                site,
                (
                    f"no readable {RUNTIME_RECORD} after the restart. The boot record is "
                    "the only external evidence that the restarted loop asserted flat"
                ),
            )
        )
    else:
        if record.get("pid") != reading.restart_pid:
            defects.append(
                (
                    f"{site}:pid",
                    (
                        f"the boot record names pid {record.get('pid')!r}, not the "
                        f"restarted {reading.restart_pid} -- the record was left by the "
                        "DEAD process and the restart never rewrote it"
                    ),
                )
            )
        defects.extend(_restart_state_defects(record, site))
    beat = reading.restart_beat
    if beat is None:
        defects.append(
            (
                f"{ENTRYPOINT}:restart heartbeat",
                (
                    f"no heartbeat naming the restarted pid {reading.restart_pid} "
                    f"appeared within {_RESTART_DEADLINE_S}s. A restarted Limiter that "
                    "does not resume publishing leaves the Sentinel reading the dead "
                    "process's last record"
                ),
            )
        )
    elif reading.seq_at_death is not None and beat.seq >= reading.seq_at_death:
        defects.append(
            (
                f"{ENTRYPOINT}:restart heartbeat seq",
                (
                    f"the restarted process's first observed seq is {beat.seq}, at or "
                    f"above the dead process's final {reading.seq_at_death}. seq "
                    "restarts at zero per process; a counter that carries across a "
                    "restart destroys the ONE signal that separates a restart from a "
                    "hang (nixsentinel/heartbeat.py)"
                ),
            )
        )
    stopped = reading.stopped_record
    if stopped is None or stopped.get("stopped_ts") is None:
        defects.append(
            (
                f"{site}:stopped_ts",
                (
                    "SIGTERM did not produce a clean stop: stopped_ts is "
                    f"{None if stopped is None else stopped.get('stopped_ts')!r}. The "
                    "field can only be written by a handler that ran, so its absence "
                    "means the signal was not handled and the daemon died the same way "
                    "a crash would -- indistinguishable, on disk, from the SIGKILL above"
                ),
            )
        )
    return defects


# ===========================================================================
# THE RUN — one launch, one kill, one restart
# ===========================================================================


def _live_phase(
    proc: subprocess.Popen[bytes], reader: _Reader, runtime: Path
) -> tuple[dict[str, Any], tuple[Beat, ...], tuple[dict[str, Any], ...]]:
    """Everything measured while the first process is ALIVE."""
    first = _await_beat(reader, proc, _BOOT_DEADLINE_S)
    # Read WHILE THE PROCESS IS RUNNING. An earlier draft asked `/proc` for
    # liveness inside the arm instead, which runs after the kill — so the gate
    # reported "the kernel has no such process" against a daemon it had itself
    # just killed, and reddened a healthy tree. The observation and the judgement
    # are different moments and only the observation can see a live process.
    identity = {
        "present": proc_present(proc.pid),
        "cmdline": proc_cmdline(proc.pid),
        "threads": proc_threads(proc.pid),
        "first": first,
    }
    if proc.poll() is not None:
        return identity, (), ()
    beats = _sample_window(reader, _ALIVE_WINDOW_S, _ALIVE_SAMPLE_GAP_S)
    replies = _drive_lock(runtime, proc)
    return identity, beats, replies


def _kill_phase(
    proc: subprocess.Popen[bytes], reader: _Reader
) -> tuple[int | None, bool, int | None, tuple[Beat, ...]]:
    """SIGKILL, reap, then watch the counter. ARM 3's whole observation."""
    pid = proc.pid
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        status = proc.wait(timeout=_REAP_DEADLINE_S)
    except subprocess.TimeoutExpired:
        status = None
    # Read /proc only AFTER the reap: an unreaped child is a zombie and its
    # /proc entry legitimately still exists, so the earlier read would fail an
    # honest daemon for the gate's own impatience (§7.12 answer 7).
    present = proc_present(pid)
    at_death = reader.sample()
    frozen = _sample_window(reader, _FROZEN_WINDOW_S, _FROZEN_SAMPLE_GAP_S)
    return status, present, (at_death.seq if at_death else None), frozen


def _restart_phase(
    home: Path, runtime: Path, log: Path, reader: _Reader
) -> tuple[subprocess.Popen[bytes], Beat | None, dict[str, Any] | None]:
    """Relaunch into the DIRTY runtime directory the killed process left."""
    proc = _launch(home, runtime, log)
    until = time.monotonic() + _RESTART_DEADLINE_S
    beat: Beat | None = None
    while time.monotonic() < until:
        sample = reader.sample()
        if sample is not None and sample.pid == proc.pid:
            beat = sample
            break
        if proc.poll() is not None:
            break
        time.sleep(_POLL_GAP_S)
    return proc, beat, _read_record(runtime)


def _measure(home: Path, workdir: Path) -> Reading:  # pylint: disable=too-many-locals
    """Drive the real daemon end to end. Raises `_Unmeasurable`, never guesses."""
    if not (home / ENTRYPOINT).is_file():
        raise _Unmeasurable(
            f"{ENTRYPOINT} is not on disk under {home} -- there is no daemon to "
            "judge. A gate that reported 'no misbehaviour' here would be reporting "
            "on an empty scope (docs/debug.md §7.12)"
        )
    if not Path("/proc/self/task").is_dir():
        raise _Unmeasurable(
            "/proc/self/task is not readable, so process liveness and thread count "
            "cannot be observed from outside the daemon at all. Every arm of this "
            "gate reads the kernel rather than the subject's own account"
        )
    try:
        from nixsentinel.heartbeat import (
            DEFAULT_HEARTBEAT_NAME,
            HeartbeatError,
            HeartbeatFile,
        )
    except Exception as exc:
        raise _Unmeasurable(
            f"nixsentinel.heartbeat will not import ({exc!r}) -- the SHIPPED reader "
            "is this gate's only window on the record, and re-implementing the "
            "parse here would make the gate a second authority on its shape"
        ) from exc

    runtime = workdir / "runtime"
    (runtime / "inbox").mkdir(parents=True, exist_ok=True)
    (runtime / "outbox").mkdir(parents=True, exist_ok=True)
    log = workdir / "limiterd.out"
    reader = _Reader(runtime / DEFAULT_HEARTBEAT_NAME, HeartbeatFile, HeartbeatError)

    first_proc: subprocess.Popen[bytes] | None = None
    second_proc: subprocess.Popen[bytes] | None = None
    try:
        first_proc = _launch(home, runtime, log)
        identity, beats, replies = _live_phase(first_proc, reader, runtime)
        early = first_proc.poll()
        if early is not None:
            # Annotated because the two branches below assign the same four
            # names from different shapes, and mypy widens from whichever it
            # sees first: `early` is `int` here and `int | None` there, and
            # `frozen` is the empty tuple here and a tuple of beats there.
            # Naming the types once is the fix; letting the first branch fix
            # them would make a correct second branch read as an error.
            status: int | None = early
            present: bool = proc_present(first_proc.pid)
            at_death: int | None = None
            frozen: tuple[Beat, ...] = ()
            first_proc.wait(timeout=_REAP_DEADLINE_S)
        else:
            status, present, at_death, frozen = _kill_phase(first_proc, reader)
        second_proc, restart_beat, boot = _restart_phase(home, runtime, log, reader)
        restart_pid = second_proc.pid
        try:
            second_proc.send_signal(signal.SIGTERM)
            second_proc.wait(timeout=_REAP_DEADLINE_S)
        except OSError, subprocess.SubprocessError:
            pass
        stopped = _read_record(runtime)
        return Reading(
            launched_pid=first_proc.pid,
            proc_present_while_alive=bool(identity["present"]),
            cmdline=str(identity["cmdline"]),
            threads=int(identity["threads"]),
            exited_early_rc=early,
            alive_beats=beats,
            beat_errors=tuple(reader.errors),
            reaped_status=status,
            proc_present_after_reap=present,
            seq_at_death=at_death,
            frozen_beats=frozen,
            replies=replies,
            restart_pid=restart_pid,
            restart_beat=restart_beat,
            boot_record=boot,
            stopped_record=stopped,
            stderr_tail=_tail(log),
        )
    finally:
        # A gate that leaks a daemon is a defect, on every path including the
        # failure paths and including an exception raised mid-measurement.
        _stop(first_proc)
        _stop(second_proc)


def _evidence(reading: Reading) -> str:
    """Every figure this run actually observed. Never a restatement."""
    alive = reading.alive_beats
    span = f"{alive[0].seq}->{alive[-1].seq}" if alive else "none"
    frozen = (
        sorted({beat.seq for beat in reading.frozen_beats})
        if reading.frozen_beats
        else []
    )
    accepted = [reply.get("accepted") for reply in reading.replies]
    return (
        f"launched pid {reading.launched_pid} present-while-alive "
        f"{reading.proc_present_while_alive} cmdline {reading.cmdline!r} with "
        f"{reading.threads} thread(s); {len(alive)} beat sample(s) over "
        f"{_ALIVE_WINDOW_S}s, seq {span}; reaped {reading.reaped_status} "
        f"(-{signal.SIGKILL} is SIGKILL), /proc present after reap "
        f"{reading.proc_present_after_reap}; seq at death {reading.seq_at_death}, "
        f"{len(reading.frozen_beats)} post-mortem sample(s) showing seq {frozen}; "
        f"inbox replies accepted={accepted}; restart pid {reading.restart_pid} "
        f"first seq "
        f"{reading.restart_beat.seq if reading.restart_beat else None}, boot record "
        f"{reading.boot_record}; stopped_ts "
        f"{(reading.stopped_record or {}).get('stopped_ts')}; reader errors "
        f"{list(reading.beat_errors)}"
    )


def _floor_refusal(reading: Reading) -> CheckResult | None:
    """`docs/debug.md` §7.12: a run that reached nothing says so, never PASS.

    Evaluated AFTER the arms — see the module docstring. These floors exist to
    stop a vacuous green, so they never need to outrank a red; letting them do so
    would let a daemon buy amber by making the gate measure less.
    """
    if len(reading.alive_beats) < MIN_ALIVE_SAMPLES:
        return _cannot_measure(
            f"only {len(reading.alive_beats)} heartbeat sample(s) were read while "
            f"the daemon lived, below the floor of {MIN_ALIVE_SAMPLES}. The gate "
            "did not observe enough beats to say the counter was climbing, and a "
            f"pass from that scope would mean nothing. Reader errors: "
            f"{list(reading.beat_errors)}"
        )
    if len(reading.frozen_beats) < MIN_FROZEN_SAMPLES:
        return _cannot_measure(
            f"only {len(reading.frozen_beats)} post-mortem sample(s), below the "
            f"floor of {MIN_FROZEN_SAMPLES}. The headline property -- the beat "
            "STOPS when the loop stops -- is a statement about a window, and this "
            "run did not observe one"
        )
    if reading.seq_at_death is None:
        return _cannot_measure(
            "no heartbeat was readable at the moment the process was reaped, so "
            "there is no value for the post-mortem samples to be compared against"
        )
    return None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the Limiter daemon for real. Never repairs -- see the reason."""
    try:
        with tempfile.TemporaryDirectory(prefix="nixlimiterlive-") as raw:
            reading = _measure(ctx.nix_home, Path(raw))
        defects = (
            process_defects(reading)
            + heartbeat_defects(reading)
            + death_defects(reading)
            + lock_defects(reading)
            + restart_defects(reading)
        )
        evidence = _evidence(reading)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        floor = _floor_refusal(reading)
        if floor is not None:
            return floor
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except _Unmeasurable as refusal:
        return _cannot_measure(str(refusal))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 --
        # exit 1 would report a violation the gate never observed.
        return _cannot_measure(f"gate raised {type(exc).__name__}: {exc}")


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
