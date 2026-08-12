#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check
# must declare the same symbols and must be independently runnable.
"""Gate: Plane 2 survives its own process being killed — and NAMES what is lost.

Subject: `scripts/nixverify/plane2.py`'s transport and `scripts/capture.py`'s
event stream, across a SIGKILL of the emitting process.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.10 (two-plane logging,
locked — Plane 2 is journald, per-process, diagnostic only; Plane 1 is Postgres
with the Limiter as sole writer, no new writers ever).

## THE PROPERTY, STATED AS TWO SENTENCES THAT MUST BOTH BE TRUE

§12.10's durability story is about Postgres going down and Plane 2 continuing.
This gate asks the harder neighbouring question — **does Plane 2 survive the
death of the process that writes it?** — and it is only half a gate if it stops
at "yes".

1. **Every record whose `emit()` returned is in the journal.** `plane2.py` uses
   `SysLogHandler`, one `sendto` per record on the `/dev/log` datagram socket,
   with no userspace buffer between the call and the kernel. Checkable, because
   each heartbeat's `seq` goes out on **two independent transports** — journald
   and the ZeroMQ state bus — and the bus is read by a different process that
   survives. Any seq the bus delivered and the journal lacks is a measured loss.
2. **`process_stop` is gone, and that is the loss.** `CaptureProcess.close()`
   emits it; SIGKILL runs no code; no handler is possible for SIGKILL. So the
   journal's last word about a killed `capture.py` is an ordinary heartbeat, and
   **an operator reading Plane 2 alone cannot tell a killed process from a hung
   one from an idle one.** This gate requires that absence and reports it as a
   FINDING in its own evidence, never as a silence.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The journal was never read.** *Closed:* a `journalctl` error, or zero
   recovered heartbeats, is CANNOT_MEASURE — deliberately never PASS
   (`nix_check_contract.md` §17: a property proven while its subject is
   unavailable is not proven).
2. **It reads an EARLIER run's entries.** *Closed by the per-arm NONCE*, which
   rides in the real event's own `nonce=` field through the real path.
3. **The producer emitted almost nothing, so "nothing was lost" is trivial.**
   *Closed:* the killed arm must have carried at least `MIN_HEARTBEATS` records
   over the bus before it died, or the comparison had nothing to compare.
4. **`process_stop` is absent because the emitter NEVER emits it.** The one that
   makes property 2 unfalsifiable, and it is the reason this gate costs an extra
   arm. *Closed by the CLEAN-EXIT CONTROL:* the same program, same path, exits
   normally in the same run, and `process_stop` **must** be present for it. If the
   control's `process_stop` is also missing, the verdict is CANNOT_MEASURE — the
   kill taught us nothing about a stream that never says goodbye anyway.
5. **The comparison is the producer being asked about itself.** *Closed:* the
   bus-side count comes from `StateSubscriber` in a separate, surviving process,
   and the journal side from `journalctl`. Neither is the emitter's own counter.

## WHAT THIS GATE CANNOT BOUND, and does not pretend to

The bus gives a LOWER bound on what the producer emitted. Records the producer
would have written after its last successful `sendto` leave no trace anywhere, so
the loss is bounded from below and **not from above**. Likewise the producer's own
`Plane2.failed` counter dies with it: a datagram `/dev/log` rejected in the final
instants is unobservable from outside. Both are stated in the verdict's evidence.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)
from nixverify.plane2 import JOURNAL_SOCKET, JOURNALCTL

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Seven claims, each OBSERVED rather than asserted — and two of them were added
#: after `check_observed_resource_claims` contradicted the first declaration,
#: which is D2.27 working as designed:
#: * `journal` — the producer writes `/dev/log`; this gate spawns
#:   `/usr/bin/journalctl` to read it back. Shared with `check_capture_plane2`
#:   and `check_verify_logging`.
#: * `subprocess:python3` / `subprocess:python` — the producer children, spawned
#:   through `sys.executable`. Both spellings: the observer matches a subprocess
#:   claim by BASENAME, and `sys.executable` differs between the runners.
#: * `file-write:/tmp` — the private bus root.
#: * `zmq-ipc`, `shm` — the drill's two transports, as `check_feed_kill_drill`.
#: * `cpu-affinity` — the producer pins to §10's Core 1 by the real path.
RESOURCES: tuple[str, ...] = (
    "journal",
    "subprocess:python3",
    "subprocess:python",
    "file-write:/tmp",
    "zmq-ipc",
    "shm",
    "cpu-affinity",
)
TIME_BOUND = True
#: One killed trial, one clean-exit control, and the journal readback (which is
#: bounded by `feed_kill_drill.JOURNAL_TIMEOUT_S`). MEASURED ~8 s on this node.
EXPECTED_S = 14.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what reaches journald across a process death; 'correcting' it "
    "would mean writing the records under measurement"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixverify/plane2.py",
    "scripts/capture.py",
    "scripts/feed_kill_drill.py",
)

NAME = "check_plane2_across_kill"

#: Below this the killed producer had barely begun and "nothing was lost" is a
#: statement about an empty set. At the drill's 50 Hz beat this is 0.4 s of life.
MIN_HEARTBEATS = 20


def _load() -> tuple[Any, str]:
    """Import the drill lazily. CANNOT_MEASURE under an interpreter without zmq."""
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    for extra in (str(scripts), str(scripts / "broker")):
        if extra not in sys.path:
            sys.path.append(extra)
    try:
        import feed_kill_drill  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, f"cannot import feed_kill_drill under {sys.executable}: {exc!r}"
    return feed_kill_drill, ""


def _precondition() -> CheckResult | None:
    """CANNOT_MEASURE when the subject is absent. Never PASS by failing to look."""
    if not Path(JOURNAL_SOCKET).exists():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"no syslog socket at {JOURNAL_SOCKET} — Plane 2 has no ingress here",
        )
    if not Path(JOURNALCTL).exists():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"{JOURNALCTL} not present — cannot read the journal back",
        )
    return None


def _arms(result: dict) -> tuple[dict | None, dict | None]:
    """`(killed, clean)` — the two arms this gate compares, or `None` for missing."""
    plane2 = result.get("plane2", {})
    trial = result["trials"][0]
    clean = result.get("clean_exit", {})
    return (
        plane2["arms"].get(trial["arm_nonce"]),
        plane2["arms"].get(clean.get("arm_nonce", "")),
    )


def _arm1_no_loss(killed: dict, defects: list, ev: list) -> None:
    """Every seq the BUS proved the producer emitted is in the journal."""
    site = "journal(-t nix-capture)"
    if killed["lost_below_bus_max"]:
        lost = killed["lost_below_bus_max"]
        defects.append(
            (
                site,
                (
                    f"pid={killed['pid']} published seq 1..{killed['bus_max_seq']} on "
                    f"the state bus and {len(lost)} of them never reached the journal "
                    f"({lost[:8]}{'...' if len(lost) > 8 else ''}) — Plane 2 did not "
                    "survive its own process dying"
                ),
            )
        )
        return
    ev.append(
        f"NO LOSS: killed pid={killed['pid']} — the bus delivered seq "
        f"1..{killed['bus_max_seq']} and the journal holds all "
        f"{killed['journal_seq_count']} of them (journal max "
        f"{killed['journal_max_seq']})"
    )


def _arm2_start_present(killed: dict, defects: list, ev: list) -> None:
    """The process announced itself, so the stream we are reading is really its."""
    site = "scripts/capture.py:CaptureProcess.start"
    if not killed["process_start_in_journal"]:
        defects.append(
            (
                site,
                (
                    f"no process_start event for pid={killed['pid']} in the journal — "
                    "the heartbeats recovered cannot be attributed to a process whose "
                    "life this gate never saw begin"
                ),
            )
        )
        return
    ev.append(f"process_start present for the killed pid={killed['pid']}")


def _arm3_stop_lost(killed: dict, clean: dict, defects: list, ev: list) -> None:
    """THE LOSS, named — and attributable, because the clean exit still says goodbye."""
    site = "scripts/capture.py:CaptureProcess.close"
    if killed["process_stop_in_journal"]:
        defects.append(
            (
                site,
                (
                    f"a process_stop event exists for pid={killed['pid']}, which was "
                    "SIGKILLed — SIGKILL runs no code, so this event was produced by "
                    "something other than the process it claims to be about"
                ),
            )
        )
        return
    ev.append(
        f"LOSS NAMED: killed pid={killed['pid']} emitted NO process_stop, while the "
        f"clean-exit control pid={clean['pid']} (reaped 0) emitted one on the same "
        "code path — so the absence is attributable to the kill, not to an emitter "
        "that never says goodbye. An operator reading Plane 2 alone cannot "
        "distinguish this death from a hang or an idle process"
    )


def _drive(drill: Any) -> dict:
    """One killed trial plus the clean-exit control, in a private bus root."""
    with tempfile.TemporaryDirectory(prefix="nixp2kill-") as tmp:
        return drill.run_drill(Path(tmp), trials=1, pin=True, starve=False, plane2=True)


def _blocked(
    result: dict, killed: dict | None, clean: dict | None
) -> CheckResult | None:
    """Every state in which this gate has not earned a verdict. Never a PASS."""
    error = result.get("plane2", {}).get("error", "")
    if error:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"journal unreadable: {error}",
        )
    if killed is None or clean is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail="the drill produced no killed arm or no clean-exit control arm",
        )
    if killed["bus_max_seq"] < MIN_HEARTBEATS:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"the killed producer got only {killed['bus_max_seq']} heartbeat(s) "
                f"onto the bus before dying (floor {MIN_HEARTBEATS}) — 'nothing was "
                "lost' over a set that small is a statement about an empty set"
            ),
        )
    if not clean["process_stop_in_journal"]:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"the CLEAN-EXIT control pid={clean['pid']} reached its own deadline "
                "and still put no process_stop in the journal, so the killed arm's "
                "missing process_stop says nothing about the kill — this gate refuses "
                "to read an emitter that never says goodbye as evidence of a death"
            ),
        )
    return None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Kill a Plane-2 emitter mid-stream and compare journald against the bus."""
    blocked = _precondition()
    if blocked is not None:
        return blocked
    drill, error = _load()
    if drill is None:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
    try:
        result = _drive(drill)
    except (OSError, RuntimeError, ValueError) as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"the drill could not be run to completion: {exc!r}",
        )
    killed, clean = _arms(result)
    stopped = _blocked(result, killed, clean)
    if stopped is not None:
        return stopped
    assert killed is not None and clean is not None  # nosec B101 - narrowed by _blocked
    evidence: list[str] = []
    defects: list[tuple[str, str]] = []
    _arm1_no_loss(killed, defects, evidence)
    _arm2_start_present(killed, defects, evidence)
    _arm3_stop_lost(killed, clean, defects, evidence)
    evidence.append(
        "BOUND: the bus is a LOWER bound on what the producer emitted — records it "
        "would have written after its last successful sendto, and any /dev/log "
        "rejection in its final instants, leave no trace outside the dead process "
        "and are NOT bounded here"
    )
    return result_from_defects(NAME, defects, "; ".join(evidence))


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
