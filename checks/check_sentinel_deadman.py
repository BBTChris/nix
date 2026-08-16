#!/usr/bin/env python3
# pylint: disable=duplicate-code,too-many-lines
# C0302 (too-many-lines): one arm per declared property, each carrying its own
# reason string — an operator reads those instead of the code.
# `docs/nix_check_contract.md` §5.5 keeps ONE
# gate to ONE property, so splitting the arms across two check modules would
# create a second gate over half a property — and §4.2 forbids the shared
# helper module that is the only other way to shorten this file.
# C0415 (import-outside-toplevel): every subject is imported INSIDE the arm
# that drives it, deliberately. A subject that cannot be imported must make
# this gate CANNOT_MEASURE through its own `except` (doctrine B.2), and a
# module-level import would instead make the check uncollectable, which is a
# runner error rather than a verdict.
# pylint: disable=import-outside-toplevel
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`docs/nix_check_contract.md` §4.2, §4.4): every
# check declares the same symbols and must be independently runnable, so the
# blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter.
"""Gate: the §12.1 deadman fires when the Risk Engine is really dead with real
exposure, records durably BEFORE it acts, and gains no authority beyond that.

Every bare `§` in this file cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec. Where another document is meant it is named on the line.

ARC 034 / sub-agent B. ONE gate, ONE property (`docs/nix_check_contract.md` §5.5).
Subjects: `scripts/nixsentinel/watchdog.py`, `scripts/nixsentinel/marker.py`,
`scripts/nixsentinel/heartbeat.py`, `scripts/nixsentinel/config.py`,
`scripts/sentinel_kill_drill.py` and `risks/sentinel.config.json`, driven as REAL
objects in REAL processes — never re-implemented here.

  * **ARM 1 — THE KILL.** A real interpreter publishes a real heartbeat and is
    `SIGKILL`ed by pid; a SECOND real process running the real `Sentinel`
    observes the loss and flattens. The verdict requires the KERNEL's reaped wait
    status to be `-SIGKILL`, the Sentinel's observed pid to BE the killed pid,
    and the drill to have seen the Risk Engine ALIVE first. **A Sentinel tested
    only against a live Limiter has never done its job**, and an in-process mock
    of "the heartbeat stopped" is not a killed Limiter.

  * **ARM 2 — THE CONTROL.** The identical drill with the kill removed. Zero
    flattens, zero broker calls, and NO marker file at all — plus a floor on the
    number of wakes, because "it did nothing" is a statement about a Sentinel
    that never ran unless the Sentinel ran.

  * **ARM 3 — THE MID-FLATTEN DEATH.** The Sentinel's broker double calls
    `os._exit` from inside `flatten_all`. The child's exit code must be that
    distinctive number, and the marker on disk must hold a `BEFORE` and NO
    `AFTER`. `os._exit` skips every buffer flush, so a marker that survives it
    was durable when `append` returned.

  * **ARM 4 — THE REPLAY.** The real `nixrisk.coldstart.ColdStart` reads that
    interrupted record through the real `MarkerReplay` and books it into Plane 1
    tagged `source=sentinel` and `interrupted=true`, at the SENTINEL's stamp, and
    archives the marker only AFTER the rows are durable. A `BEFORE` with no
    `AFTER` is not corruption; a replayer that discarded it is the defect.

  * **ARM 5 — DURABILITY.** `MarkerWriter.append` must call `fsync` before it
    returns, and an `fsync` that FAILS must raise rather than return as if the
    record were safe. Both are driven.

  * **ARM 6 — THE §14 AUTHORITY BOUNDARY.** `nixrisk.flatten` still REFUSES the
    `SENTINEL` trigger, by a real call that must raise with a reason; the
    Sentinel's import closure, measured in a clean child interpreter, contains no
    `nixrisk` module; and `watchdog.py` calls no broker verb beyond the four
    §12.1 authorises.

  * **ARM 7 — THE BROKER WINS, BOTH WAYS.** The heartbeat's `positions_open` is a
    hint from a dead process. Two drives where the hint and the broker DISAGREE
    in opposite directions must both follow the broker, and no comparison in
    `watchdog.py` may mention `positions_open` at all.

  * **ARM 8 — THE KNOBS.** The shipped `risks/sentinel.config.json` loads through
    the real `nixsentinel.config.load_sentinel_knobs`, and both boot rules are
    driven RED on a perturbed set. A validator nothing can redden validates
    nothing.

WHAT A GREEN HERE DOES NOT MEAN, stated rather than implied. The BROKER is a
double on every arm and has to be: there is no venue on this node and §12.1's act
is an order. This gate proves the CONDITION, the ORDERING, the DURABILITY and the
BOUNDARY. It proves nothing about a real venue accepting a real close, nothing
about the Sentinel's systemd unit (there is none), and nothing about §10:551's
core placement (`check_core_map` owns that and the Sentinel is not in its map
yet). Those are `docs/CHECK-DEBT.md` rows, not silent gaps.

`docs/debug.md` §7.12 — the standing question, asked at the point this gate was
built: *what would have to be true for this to PASS while measuring nothing?*
Seven answers, each closed by a named mechanism rather than by assertion:

 1. *Nothing was ever killed — the publisher merely exited.* Closed by ARM 1
    requiring `publisher_status == -signal.SIGKILL`, which is the kernel's reaped
    status for the pid this drill spawned, not the drill's own account of itself.
 2. *The Sentinel never saw a healthy Risk Engine, so "loss" was never a
    change.* Closed by `MIN_LIVE_WAKES`: the kill drill must contain wakes
    classified `progressing` BEFORE the loss, or the run is refused.
 3. *The control arm proves restraint by never running.* Closed by
    `MIN_CONTROL_WAKES` — a floor on wakes, not on silence.
 4. *The marker "survived" because the test never actually died.* Closed by ARM
    3 asserting the child's exit code is `MID_FLATTEN_EXIT`, a distinctive number
    reachable only from inside `flatten_all`.
 5. *`fsync` is asserted by reading the writer's own claim.* Closed by ARM 5
    OBSERVING the call and separately making it FAIL, which is a property of the
    running code rather than of its docstring.
 6. *The authority arm reads its ban list out of its subject.* Closed by ARM 6
    deriving the authorised verb set from the FROZEN seam's `SentinelBrokerPort`
    (which `check_sentinel_seam` independently polices) rather than from
    `watchdog.py`, the file under test.
 7. *Every arm inspects and none of them counts.* Closed by the floors above plus
    `MIN_DRIVEN_RULES`, all of which are floors BELOW today's figures (doctrine
    C.4) and none of which is zero.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import signal
import subprocess  # nosec B404 - launches sys.executable with a literal argv, no shell
import sys
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. The drill children are launched through
#: `sys.executable` and import only the standard library plus `scripts/`, so
#: there is no third-party dependency and therefore no `check_venv` edge.
DEPENDS_ON: tuple[str, ...] = ()
#: Declared HONESTLY, because check contract v2 §12 checks declared claims
#: against OBSERVED ones and `()` on a gate that forks is measurable, not
#: trusted.
#: * `subprocess:python` / `subprocess:python3` — the drill re-executes
#:   `scripts/sentinel_kill_drill.py` through `sys.executable`, twice per arm.
#:   BOTH spellings, because the observer matches a subprocess claim by BASENAME
#:   and `sys.executable` is `.venv/bin/python` under pytest and
#:   `/usr/bin/python3` under `nix-verify.service`.
#: * `file-write:/tmp` — every arm runs inside one `tempfile.TemporaryDirectory`.
#: * `interpreter:sys.path` / `interpreter:sys.modules` — `_preamble` puts
#:   `scripts/` on the path, and ARM 5 temporarily replaces `os.fsync` to observe
#:   it, restoring it in a `finally`.
RESOURCES: tuple[str, ...] = (
    "subprocess:python",
    "subprocess:python3",
    "file-write:/tmp",
    "interpreter:sys.path",
    "interpreter:sys.modules",
)
#: TRUE. Every drill child carries a deadline and the gate bounds the parent
#: wait; a drill that hung would be indistinguishable from a Sentinel that never
#: fired, which is the one outcome this gate must never report as a pass.
TIME_BOUND = True
#: NON-CORRECTABLE. Every subject is behaviour under a real process death. An
#: instrument empowered to "repair" a Sentinel that failed to flatten would be
#: writing the trading code it exists to judge, and ARM 6's subject is an
#: AUTHORITY boundary — a self-correcting gate there could widen the very thing
#: it holds shut.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every arm measures behaviour under a real process death, and the only "
    "repair for a deadman that did not fire is to change the deadman. An "
    "instrument that could do that would be manufacturing its own green, and "
    "ARM 6's subject is the §14 authority boundary, which a self-correcting "
    "gate could widen rather than hold"
)
#: Genuinely MEASURED: every module below is imported and driven, and the config
#: is loaded through its real loader.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixsentinel/watchdog.py",
    "scripts/nixsentinel/marker.py",
    "scripts/nixsentinel/heartbeat.py",
    "scripts/nixsentinel/config.py",
    "scripts/sentinel_kill_drill.py",
    "risks/sentinel.config.json",
)

NAME = "check_sentinel_deadman"

WATCHDOG = "scripts/nixsentinel/watchdog.py"
SEAM = "scripts/nixsentinel/seam.py"

#: Non-vacuity floors (`docs/debug.md` §7.12). Floors, deliberately BELOW today's
#: figures (doctrine C.4) so they cannot become moving anchors — but never zero.
MIN_CONTROL_WAKES = 8
MIN_LIVE_WAKES = 2
MIN_DRIVEN_RULES = 2

#: The port whose verbs ARE the authorised act. Read from the FROZEN seam, never
#: from `watchdog.py`: a ban list derived from the file under test is a subject
#: permitted to widen itself, which is the shape `check_pollers` was measured
#: doing in ARC 034 / Phase 0.5.
_BROKER_PORT = "SentinelBrokerPort"

#: The control arm's duration. Long enough to clear `MIN_CONTROL_WAKES` at the
#: drill's poll interval with room to spare, short enough that the gate runs.
_CONTROL_DEADLINE_S = 1.5


class Reading(NamedTuple):
    """What one run actually observed. Every field lands in the evidence."""

    killed_pid: int
    kill_status: int | None
    observed_pid: int | None
    flattened: tuple[str, ...]
    kill_marker_phases: tuple[str, ...]
    control_wakes: int
    control_causes: int
    control_broker_calls: int
    die_returncode: int | None
    die_marker_phases: tuple[str, ...]
    replay_rows: int
    fsync_calls: int
    authorised_verbs: tuple[str, ...]
    nixrisk_in_closure: tuple[str, ...]
    driven_rules: tuple[str, ...]
    live_wakes: int


def _cannot_measure(detail: str) -> CheckResult:
    """Doctrine B.2: an unread subject is CANNOT_MEASURE, never PASS."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ===========================================================================
# ARM 1 / ARM 2 / ARM 3 — the real drills
# ===========================================================================


def kill_defects(outcome: Any, live_wakes: int) -> list[tuple[str, str]]:
    """ARM 1. The headline: a killed Limiter really produces a flatten."""
    defects: list[tuple[str, str]] = []
    if outcome.publisher_status != -signal.SIGKILL:
        defects.append(
            (
                "sentinel_kill_drill:publisher",
                (
                    f"the kernel reaped the publisher with status "
                    f"{outcome.publisher_status!r}, not {-signal.SIGKILL} (-SIGKILL). "
                    "A publisher that EXITED is not a killed Limiter, and the whole "
                    "§12.1:604 property is about a Risk Engine that was killed"
                ),
            )
        )
    if live_wakes < MIN_LIVE_WAKES:
        defects.append(
            (
                "sentinel_kill_drill:settle",
                (
                    f"the Sentinel observed only {live_wakes} wake(s) with a "
                    f"PROGRESSING Risk Engine, below the floor of {MIN_LIVE_WAKES}. A "
                    "drill in which the heartbeat was never seen advancing measures a "
                    "Sentinel that has never watched anything alive, so 'lost' was "
                    "never a change"
                ),
            )
        )
    acted = [wake for wake in outcome.wakes if wake["acted"]]
    if not acted:
        defects.append(
            (
                "nixsentinel/watchdog.py:poll",
                (
                    "the Sentinel never flattened after a real SIGKILL with open "
                    "positions. §12.1:604-605: heartbeat lost AND positions possibly "
                    "open is the condition, and both halves were true"
                ),
            )
        )
        return defects
    wake = acted[-1]
    if wake["observed_pid"] != outcome.publisher_pid:
        defects.append(
            (
                "nixsentinel/watchdog.py:observed_pid",
                (
                    f"the Sentinel attributed the loss to pid {wake['observed_pid']!r} "
                    f"but the drill killed pid {outcome.publisher_pid}. A flatten that "
                    "cannot be attributed to the death that caused it is a flatten "
                    "with no proven cause"
                ),
            )
        )
    defects += _marker_defects(outcome, wake)
    return defects + _session_defects(outcome)


#: The verb sequence a §12.1:605 flatten must produce on the Sentinel's OWN
#: session: open it, ask it what is really open, close everything, hand it back.
#: Written as an ORDER rather than a set — `flatten_all` before `open_positions`
#: would be a flatten against no observation, which is the nuisance act §12.1:605
#: conditions away.
_EXPECTED_SESSION = ("connect", "open_positions", "flatten_all", "disconnect")


def _session_defects(outcome: Any) -> list[tuple[str, str]]:
    """ARM 1's session half: opened, used in order, and HANDED BACK.

    The teardown is not housekeeping. §12.1:605 gives the Sentinel its OWN broker
    session precisely so it does not share the Limiter's; a session it never
    releases is one a restarted Risk Engine may find still held, which turns the
    separation into a different collision.
    """
    verbs = tuple(call["verb"] for call in outcome.broker_calls)
    if verbs != _EXPECTED_SESSION:
        return [
            (
                "nixsentinel/watchdog.py:_ensure_session",
                (
                    f"the Sentinel's own broker session saw {list(verbs)}, not "
                    f"{list(_EXPECTED_SESSION)}. §12.1:605 requires it to open its OWN "
                    "session, ask the BROKER what is open before deciding, flatten, "
                    "and give the session back"
                ),
            )
        ]
    return []


def _marker_defects(outcome: Any, wake: dict[str, Any]) -> list[tuple[str, str]]:
    """ARM 1's record half: `BEFORE` then `AFTER`, with the acks."""
    phases = tuple(record["phase"] for record in outcome.marker_records)
    if phases != ("before", "after"):
        return [
            (
                "logs/sentinel_marker.jsonl",
                (
                    f"the marker holds phases {phases!r}, not ('before', 'after'). "
                    "§12.1:610 requires a record on BOTH sides of the act"
                ),
            )
        ]
    before, after = outcome.marker_records
    defects: list[tuple[str, str]] = []
    if before["ts"] > after["ts"]:
        defects.append(
            (
                "logs/sentinel_marker.jsonl",
                (
                    f"the 'before' record is stamped {before['ts']!r}, later than the "
                    f"'after' record at {after['ts']!r} — the file's own order "
                    "contradicts the act's"
                ),
            )
        )
    if before["acks"]:
        defects.append(
            (
                "logs/sentinel_marker.jsonl:before",
                (
                    "the 'before' record carries broker acknowledgements. It is "
                    "written before one instruction reaches the broker, so there is "
                    "nothing that could have acknowledged anything"
                ),
            )
        )
    if tuple(after["symbols"]) != tuple(wake["symbols"]):
        defects.append(
            (
                "logs/sentinel_marker.jsonl:after",
                (
                    f"the marker records symbols {after['symbols']!r} and the flatten "
                    f"covered {wake['symbols']!r}"
                ),
            )
        )
    if len(after["acks"]) != len(wake["symbols"]):
        defects.append(
            (
                "logs/sentinel_marker.jsonl:after",
                (
                    f"{len(after['acks'])} broker ack(s) recorded for "
                    f"{len(wake['symbols'])} symbol(s). §12.1:610 names the acks as "
                    "part of the record"
                ),
            )
        )
    return defects


def control_defects(outcome: Any) -> list[tuple[str, str]]:
    """ARM 2. The nuisance-flatten hazard, shown NOT to have fired."""
    defects: list[tuple[str, str]] = []
    if len(outcome.wakes) < MIN_CONTROL_WAKES:
        defects.append(
            (
                "sentinel_kill_drill:control",
                (
                    f"the control Sentinel woke {len(outcome.wakes)} time(s), below "
                    f"the floor of {MIN_CONTROL_WAKES}. A component that proved its "
                    "restraint by not running proved nothing"
                ),
            )
        )
    fired = [wake for wake in outcome.wakes if wake["cause"] is not None]
    if fired:
        defects.append(
            (
                "nixsentinel/watchdog.py:poll",
                (
                    f"the Sentinel reached {len(fired)} §12.1 condition(s) against a "
                    f"LIVE Risk Engine: {[wake['cause'] for wake in fired]!r}. §14:977 "
                    "makes execution of any flatten Limiter-only while the Limiter "
                    "lives"
                ),
            )
        )
    if outcome.broker_calls:
        defects.append(
            (
                "nixsentinel/watchdog.py:_ensure_session",
                (
                    f"the Sentinel touched its broker session "
                    f"{len(outcome.broker_calls)} time(s) while the heartbeat was "
                    "healthy. Its session is opened when the condition fires, not "
                    "kept warm against a living Limiter"
                ),
            )
        )
    if outcome.marker_records:
        defects.append(
            (
                "logs/sentinel_marker.jsonl",
                (
                    f"the control run wrote {len(outcome.marker_records)} marker "
                    "record(s). Nothing happened, so there is nothing to record"
                ),
            )
        )
    return defects


def interrupted_defects(outcome: Any, mid_flatten_exit: int) -> list[tuple[str, str]]:
    """ARM 3. A Sentinel that dies MID-FLATTEN still leaves a record."""
    defects: list[tuple[str, str]] = []
    if outcome.sentinel_returncode != mid_flatten_exit:
        defects.append(
            (
                "sentinel_kill_drill:die-mid-flatten",
                (
                    f"the Sentinel child exited {outcome.sentinel_returncode!r}, not "
                    f"{mid_flatten_exit}. That code is reachable only from inside "
                    "`flatten_all`, so any other value means the process did not die "
                    "where the drill needed it to and this arm measured nothing"
                ),
            )
        )
    phases = tuple(record["phase"] for record in outcome.marker_records)
    if phases != ("before",):
        defects.append(
            (
                "logs/sentinel_marker.jsonl",
                (
                    f"after a mid-flatten death the marker holds {phases!r}; it must "
                    "hold exactly one 'before' and no 'after'. A 'before' that did "
                    "not survive means the record was buffered, and §12.1:608's whole "
                    "fix is a record that outlives the process"
                ),
            )
        )
    return defects


# ===========================================================================
# ARM 6 — the §14 boundary
# ===========================================================================


def refusal_defects() -> list[tuple[str, str]]:
    """ARM 6a. `nixrisk.flatten` must still refuse the `SENTINEL` trigger.

    A REAL call to the real `fire`, not a read of `_R4_TRIGGERS`: the refusal is
    a behaviour, and a set membership is a proxy for it. The collaborators are
    `None` because the refusal is the first statement in the verb — if it ever
    stopped being first, this drive would fail with a different exception and
    that is the correct outcome, not a false green.
    """
    from nixrisk.flatten import (  # pylint: disable=import-outside-toplevel
        ProtectiveFlatten,
        TriggerNotFireable,
    )
    from nixrisk.seam import FlattenTrigger  # pylint: disable=import-outside-toplevel

    flattener = ProtectiveFlatten(
        broker=None,  # type: ignore[arg-type]
        ledger=None,  # type: ignore[arg-type]
        picture=None,  # type: ignore[arg-type]
        strategy=None,  # type: ignore[arg-type]
        plane1=None,  # type: ignore[arg-type]
        scoring=None,  # type: ignore[arg-type]
    )
    try:
        flattener.fire(FlattenTrigger.SENTINEL, symbol="MES")
    except TriggerNotFireable as exc:
        if "SENTINEL" not in str(exc):
            return [
                (
                    "nixrisk/flatten.py:fire",
                    (
                        f"the SENTINEL refusal raised without naming the trigger: "
                        f"{exc}. Check contract v2 §11: assert the REASON, and a "
                        "refusal an operator cannot attribute is a refusal they "
                        "cannot act on"
                    ),
                )
            ]
        return []
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            (
                "nixrisk/flatten.py:fire",
                (
                    f"firing SENTINEL raised {type(exc).__name__} rather than "
                    f"TriggerNotFireable ({exc}) — the deliberate refusal is no "
                    "longer the first thing that verb does"
                ),
            )
        ]
    return [
        (
            "nixrisk/flatten.py:fire",
            (
                "the Limiter's protective flattener ACCEPTED the SENTINEL trigger. "
                "§14:977-978 permits exactly ONE exception to Limiter-only execution "
                "— the Sentinel, when the Limiter is dead — and the live Limiter's "
                "own module is not it"
            ),
        )
    ]


def closure_defects(home: Path) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """ARM 6b. The Sentinel's import closure, measured in a CLEAN interpreter.

    A child, not this process: this gate has already imported `nixrisk` for ARM
    6a, so asking `sys.modules` here would answer a question about the gate. The
    child imports `nixsentinel.watchdog` and nothing else and reports what came
    with it.
    """
    probe = (
        "import json, sys; import nixsentinel.watchdog; "
        "print(json.dumps({'risk': sorted(m for m in sys.modules "
        "if m.split('.')[0] == 'nixrisk'), "
        "'self': 'nixsentinel.watchdog' in sys.modules}))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(home / "scripts")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(  # nosec B603 - argv built here, no shell
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
            cwd=str(home),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"the import-closure probe could not run: {exc!r}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"the import-closure probe exited {proc.returncode}: {proc.stderr.strip()}"
        )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if not payload["self"]:
        raise RuntimeError(
            "the import-closure probe did not import nixsentinel.watchdog, so its "
            "empty answer is a statement about nothing"
        )
    found = tuple(payload["risk"])
    if found:
        return [
            (
                "scripts/nixsentinel/",
                (
                    f"importing the Sentinel pulled in {found!r}. §12.1:603 requires a "
                    "SEPARATE CODE PATH with minimal common-mode failure: a shared "
                    "import graph means the defect that killed the Risk Engine also "
                    "kills its watcher, which is the failure this component exists to "
                    "avoid"
                ),
            )
        ], found
    return [], found


def _authorised_verbs(home: Path) -> tuple[str, ...]:
    """The four verbs the FROZEN seam declares on `SentinelBrokerPort`.

    Parsed from the seam, NOT from `watchdog.py`. The seam is independently
    policed by `checks/check_sentinel_seam.py` ARM 5, so this gate's expected
    side cannot be widened by the file it is judging.
    """
    tree = ast.parse((home / SEAM).read_text(encoding="utf-8"), filename=SEAM)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == _BROKER_PORT:
            return tuple(
                stmt.name
                for stmt in node.body
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return ()


def verb_defects(home: Path, verbs: tuple[str, ...]) -> list[tuple[str, str]]:
    """ARM 6c. `watchdog.py` calls no broker verb outside the authorised set."""
    tree = ast.parse((home / WATCHDOG).read_text(encoding="utf-8"), filename=WATCHDOG)
    allowed = set(verbs)
    defects: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        if not (isinstance(target, ast.Attribute) and target.attr == "_broker"):
            continue
        if node.func.attr not in allowed:
            defects.append(
                (
                    f"{WATCHDOG}:{node.lineno}",
                    (
                        f"calls self._broker.{node.func.attr}(), which the frozen "
                        f"SentinelBrokerPort does not declare (it declares "
                        f"{sorted(allowed)}). §14:977-978 permits the Sentinel one "
                        "emergency flatten, not a second execution authority"
                    ),
                )
            )
    return defects


# ===========================================================================
# ARM 7 — the broker's answer beats the dead process's hint
# ===========================================================================


def _drive_disagreement(
    workdir: Path, *, hint: int, broker_symbols: tuple[str, ...]
) -> Any:
    """One poll of a REAL `Sentinel` with a stale heartbeat and a chosen broker."""
    from nixsentinel.heartbeat import (  # pylint: disable=import-outside-toplevel
        HeartbeatFile,
        HeartbeatPublisher,
    )
    from nixsentinel.marker import (
        MarkerWriter,  # pylint: disable=import-outside-toplevel
    )
    from nixsentinel.watchdog import Sentinel  # pylint: disable=import-outside-toplevel
    from sentinel_kill_drill import (  # pylint: disable=import-outside-toplevel
        DrillAlert,
        DrillBroker,
        drill_knobs,
    )

    workdir.mkdir(parents=True, exist_ok=True)
    beat_path = workdir / "risk_engine.heartbeat.json"
    # A beat stamped in the past: the Risk Engine spoke, and then stopped.
    HeartbeatPublisher(beat_path, pid=424242, clock=lambda: 1000.0).publish(hint)
    sentinel = Sentinel(
        heartbeat=HeartbeatFile(beat_path),
        broker=DrillBroker(broker_symbols, workdir / "broker.jsonl"),
        marker=MarkerWriter(workdir / "sentinel_marker.jsonl"),
        alert=DrillAlert(workdir / "alerts.jsonl"),
        knobs=drill_knobs(),
        pid=999999,
    )
    return sentinel.poll(now=2000.0)


def hint_defects(workdir: Path) -> list[tuple[str, str]]:
    """ARM 7. Drive BOTH directions of disagreement and follow the broker.

    One direction alone measures nothing: a Sentinel that always flattens passes
    the "hint says flat, broker says open" case, and one that never flattens
    passes the "hint says open, broker says flat" case.
    """
    defects: list[tuple[str, str]] = []
    open_case = _drive_disagreement(
        workdir / "hint-says-flat", hint=0, broker_symbols=("MES",)
    )
    if not open_case.acted:
        defects.append(
            (
                "nixsentinel/watchdog.py:_on_lost",
                (
                    "the heartbeat's hint said ZERO positions and the Sentinel's own "
                    "broker session reported one open — and no flatten fired. §4 makes "
                    "the broker the record and the hint a stale value from a process "
                    f"that has been dead for the loss threshold ({open_case.detail})"
                ),
            )
        )
    flat_case = _drive_disagreement(
        workdir / "hint-says-open", hint=3, broker_symbols=()
    )
    if flat_case.acted:
        defects.append(
            (
                "nixsentinel/watchdog.py:_on_lost",
                (
                    "the heartbeat's hint said THREE positions, the Sentinel's own "
                    "broker session reported none, and a flatten fired anyway. That is "
                    "a nuisance flatten driven by a dead process's memory"
                ),
            )
        )
    if flat_case.cause is None:
        defects.append(
            (
                "nixsentinel/watchdog.py:_no_positions",
                (
                    "the Sentinel woke, found the heartbeat lost and the account flat, "
                    "and recorded no cause at all. §12.1:605's restraint has to be an "
                    "OBSERVABLE fact; an absence of evidence is not evidence of "
                    "restraint"
                ),
            )
        )
    return defects


def branch_defects(home: Path) -> list[tuple[str, str]]:
    """ARM 7's static half: no COMPARISON in `watchdog.py` reads the hint.

    Behavioural drives show the broker won on two inputs; this shows there is no
    third input on which the hint could win, because the value never reaches a
    test at all.

    **Scoped to the DECIDING position, not to proximity.** Only the `test` of an
    `if`/`while`/conditional expression and the operands of a comparison count.
    The first version of this arm walked the whole node and reddened on
    `beat.positions_open if beat else None` — a null guard whose test is `beat`,
    which decides nothing about the hint. An arm that cannot tell "read while a
    branch happens to be nearby" from "read in order to branch" would push the
    module toward contortions that make the hazard harder to see, not easier.
    """
    tree = ast.parse((home / WATCHDOG).read_text(encoding="utf-8"), filename=WATCHDOG)
    deciding: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp)):
            deciding.append(node.test)
        elif isinstance(node, ast.Compare):
            deciding.append(node)
    defects: list[tuple[str, str]] = []
    for node in deciding:
        for inner in ast.walk(node):
            if isinstance(inner, ast.Attribute) and inner.attr == "positions_open":
                defects.append(
                    (
                        f"{WATCHDOG}:{inner.lineno}",
                        (
                            "a conditional reads the heartbeat's `positions_open`. It "
                            "is the LAST KNOWN count of a process that has been dead "
                            "for at least the loss threshold — a hint, stale by "
                            "construction. The authoritative answer is "
                            "SentinelBrokerPort.open_positions() on the Sentinel's own "
                            "session (§4: broker wins and we correct)"
                        ),
                    )
                )
    return defects


# ===========================================================================
# ARM 5 / ARM 8 — durability and the knobs
# ===========================================================================


def durability_defects(workdir: Path) -> tuple[list[tuple[str, str]], int]:
    """ARM 5. `append` fsyncs before it returns, and says so when it cannot."""
    import nixsentinel.marker as marker_mod  # pylint: disable=import-outside-toplevel

    record = _sample_record()
    calls: list[int] = []
    real = os.fsync

    def spy(fd: int) -> None:
        calls.append(fd)
        real(fd)

    def angry(fd: int) -> None:
        raise OSError(5, f"drill: the device refused to sync fd {fd}")

    workdir.mkdir(parents=True, exist_ok=True)
    defects: list[tuple[str, str]] = []
    try:
        os.fsync = spy  # type: ignore[assignment]
        marker_mod.MarkerWriter(workdir / "synced.jsonl").append(record)
        if not calls:
            defects.append(
                (
                    "nixsentinel/marker.py:append",
                    (
                        "append() returned without calling fsync. A marker still in "
                        "the page cache dies with the process it was written to "
                        "outlive, which is the whole of §12.1:608's fix"
                    ),
                )
            )
        os.fsync = angry  # type: ignore[assignment]
        try:
            marker_mod.MarkerWriter(workdir / "unsynced.jsonl").append(record)
        except marker_mod.MarkerError as exc:
            if "refus" not in str(exc).lower():
                defects.append(
                    (
                        "nixsentinel/marker.py:append",
                        (
                            f"a failed fsync raised MarkerError without saying it was "
                            f"refusing to claim durability: {exc}"
                        ),
                    )
                )
        else:
            defects.append(
                (
                    "nixsentinel/marker.py:append",
                    (
                        "append() returned NORMALLY when fsync failed. The caller is "
                        "then told the record is durable when nothing reached the "
                        "device (check contract v2 §11: the reason, never the code)"
                    ),
                )
            )
    finally:
        os.fsync = real  # type: ignore[assignment]
    return defects, len(calls)


def _sample_record() -> Any:
    """One real `MarkerRecord`, built from the frozen seam's own types."""
    from nixsentinel.seam import (  # pylint: disable=import-outside-toplevel
        MARKER_SCHEMA,
        MarkerPhase,
        MarkerRecord,
        TriggerCause,
    )

    return MarkerRecord(
        schema=MARKER_SCHEMA,
        phase=MarkerPhase.BEFORE,
        ts=1000.0,
        cause=TriggerCause.HEARTBEAT_LOST,
        symbols=("MES",),
        acks=(),
        sentinel_pid=1,
        heartbeat_age_s=5.0,
    )


def knob_defects(
    home: Path, workdir: Path
) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """ARM 8. The shipped knobs load, and EVERY rule that governs them REDDENS.

    There is deliberately no second check here that the threshold outlasts the
    Limiter's grace. `load_sentinel_knobs` above already refuses a set that
    violates it — the boot rule is what does the refusing — so an arm re-testing
    the relation could never produce a defect. **An arm that cannot redden is the
    vacuity this gate exists to hunt**, and it was written and then removed
    rather than left in place looking like coverage.
    """
    import nixsentinel.config as cfg  # pylint: disable=import-outside-toplevel

    defects: list[tuple[str, str]] = []
    try:
        cfg.load_sentinel_knobs(home)
    except cfg.SentinelConfigError as exc:
        return [
            ("risks/sentinel.config.json", f"the shipped knob set is invalid: {exc}")
        ], ()
    driven, attempted = _driven_rules(home, workdir, cfg)
    if len(attempted) < MIN_DRIVEN_RULES:
        defects.append(
            (
                "checks/check_sentinel_deadman.py:_driven_rules",
                (
                    f"this arm attempted only {len(attempted)} perturbation(s), "
                    f"below the floor of {MIN_DRIVEN_RULES}. A can-fail census "
                    "with nothing in it agrees with everything"
                ),
            )
        )
    undriven = tuple(rule for rule in attempted if rule not in driven)
    if undriven:
        defects.append(
            (
                "scripts/risk_config.py:BOOT_RULES",
                (
                    f"sentinel boot rule(s) {list(undriven)} did not reject a set "
                    "built to violate them. A validator nothing can redden has "
                    "validated nothing (docs/debug.md §7.12)"
                ),
            )
        )
    return defects, driven


def _driven_rules(
    home: Path, workdir: Path, cfg: Any
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Perturb the knob set one rule at a time. Returns `(reddened, attempted)`.

    Real files in a real copied tree, loaded by the real loader. A rule proven
    by an in-memory stub would be a rule proven against a shape the loader never
    sees. Returning BOTH sets is what keeps the caller's floor from being an
    arithmetic identity: "two rules reddened" is only meaningful against how many
    were tried.
    """
    perturbations = {
        "sentinel.loss_outlasts_limiter_grace": {"heartbeat_loss_multiple": 1},
        "sentinel.poll_fits_loss_threshold": {"poll_interval_s": 99},
    }
    driven: list[str] = []
    for rule_id, patch in perturbations.items():
        root = workdir / rule_id.replace(".", "_")
        (root / "risks").mkdir(parents=True, exist_ok=True)
        for name in ("limiter", "sentinel"):
            shutil.copy(
                home / "risks" / f"{name}.config.json",
                root / "risks" / f"{name}.config.json",
            )
        target = root / "risks" / "sentinel.config.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload.update(patch)
        target.write_text(json.dumps(payload), encoding="utf-8")
        try:
            cfg.load_sentinel_knobs(root)
        except cfg.SentinelConfigError as exc:
            if f"[{rule_id}" in str(exc):
                driven.append(rule_id)
    return tuple(driven), tuple(perturbations)


# ===========================================================================
# ARM 4 — the replay
# ===========================================================================


class _Plane1Spy:
    """A recording Plane-1 sink. Order matters: durability precedes archiving."""

    def __init__(self) -> None:
        self.rows: list[Any] = []
        self.calls: list[str] = []

    def enqueue(self, row: Any) -> None:
        """Buffer one row. Not durable — that is `sync_to_disk`'s job."""
        self.rows.append(row)
        self.calls.append("enqueue")

    def sync_to_disk(self) -> int:
        """Make the buffered rows durable. Returns how many."""
        self.calls.append("sync")
        return len(self.rows)

    def pending(self) -> int:
        """Rows enqueued but not yet durable."""
        return 0


def replay_defects(marker_path: Path) -> tuple[list[tuple[str, str]], int]:
    """ARM 4. The real `ColdStart` books the INTERRUPTED record, then archives."""
    from nixrisk.coldstart import ColdStart  # pylint: disable=import-outside-toplevel
    from nixsentinel.marker import (
        MarkerReplay,  # pylint: disable=import-outside-toplevel
    )

    plane1 = _Plane1Spy()
    replay = MarkerReplay(marker_path, clock=lambda: 5000.0)
    pending = replay.read_pending()
    cold = ColdStart(
        broker=None,  # type: ignore[arg-type]
        flattener=None,  # type: ignore[arg-type]
        halt=None,  # type: ignore[arg-type]
        plane1=plane1,
        sentinel_marker=replay,
    )
    rows = cold.replay_sentinel_marker(now=5000.0)
    defects: list[tuple[str, str]] = []
    if not pending:
        return [
            (
                str(marker_path),
                (
                    "the interrupted marker read back EMPTY. A 'before' with no "
                    "'after' is not corruption — it is the evidence §12.1:608 exists "
                    "to preserve, and a reader that discards it is the defect"
                ),
            )
        ], 0
    exits = [row for row in rows if row.fields.get("source") == "sentinel"]
    if not exits:
        defects.append(
            (
                "nixrisk/coldstart.py:replay_sentinel_marker",
                (
                    "no row was booked with source=sentinel. §12.1:612-613 requires "
                    "the flatten to be booked retroactively with exactly that tag"
                ),
            )
        )
    elif not any(row.fields.get("interrupted") == "true" for row in exits):
        defects.append(
            (
                "nixrisk/coldstart.py:replay_sentinel_marker",
                (
                    "the interrupted act was booked as an ordinary one. A close whose "
                    "'after' record never arrived is UNCONFIRMED, and a row that "
                    "cannot say so is a row an operator will read as settled"
                ),
            )
        )
    elif exits[0].ts != pending[0].ts:
        defects.append(
            (
                "nixrisk/coldstart.py:_sentinel_row",
                (
                    f"the retroactive row is stamped {exits[0].ts!r} rather than the "
                    f"Sentinel's own {pending[0].ts!r}. A row carrying the boot time "
                    "moves a money event by however long the box was down"
                ),
            )
        )
    defects += _archive_defects(plane1, marker_path)
    return defects, len(rows)


def _archive_defects(plane1: _Plane1Spy, marker_path: Path) -> list[tuple[str, str]]:
    """The ordering half of ARM 4: sync, THEN archive; and the marker is renamed."""
    defects: list[tuple[str, str]] = []
    if "sync" not in plane1.calls:
        defects.append(
            (
                "nixrisk/coldstart.py:replay_sentinel_marker",
                (
                    "the rows were enqueued and never synced before the marker was "
                    "archived. `enqueue` returns without durability by design "
                    "(nixrisk/seam.py Plane1Port), so archiving on it destroys the "
                    "only record on the exact boot where the WAL then fails"
                ),
            )
        )
    if marker_path.exists():
        defects.append(
            (
                str(marker_path),
                (
                    "the marker was still in place after a completed replay. "
                    "§12.1:613: cold start *archives* it, or the next boot books the "
                    "same emergency again"
                ),
            )
        )
    archived = list(marker_path.parent.glob(f"{marker_path.name}.*.replayed"))
    if not archived:
        defects.append(
            (
                str(marker_path.parent),
                (
                    "no archived marker was found. Archiving is a RENAME and never a "
                    "delete: the marker is the only account of what the dying process "
                    "saw (directive 6)"
                ),
            )
        )
    return defects


# ===========================================================================
# The composition
# ===========================================================================


def _measure(  # pylint: disable=too-many-locals
    home: Path, workdir: Path
) -> tuple[list[tuple[str, str]], Reading]:
    """Run every arm. Returns `(defects, reading)`."""
    from sentinel_kill_drill import (  # pylint: disable=import-outside-toplevel
        MID_FLATTEN_EXIT,
        MODE_DIE_MID_FLATTEN,
        run_drill,
    )

    kill = run_drill(workdir / "kill", positions=("MES", "MNQ"))
    live = sum(1 for wake in kill.wakes if wake["liveness"] == "progressing")
    control = run_drill(
        workdir / "control",
        positions=("MES",),
        kill=False,
        deadline=_CONTROL_DEADLINE_S,
    )
    die = run_drill(workdir / "die", positions=("MES",), mode=MODE_DIE_MID_FLATTEN)
    closure, in_closure = closure_defects(home)
    verbs = _authorised_verbs(home)
    fsync_defects, fsyncs = durability_defects(workdir / "durability")
    replay, replay_rows = replay_defects(workdir / "die" / "sentinel_marker.jsonl")
    knobs, driven = knob_defects(home, workdir / "knobs")
    defects = (
        kill_defects(kill, live)
        + control_defects(control)
        + interrupted_defects(die, MID_FLATTEN_EXIT)
        + replay
        + fsync_defects
        + refusal_defects()
        + closure
        + verb_defects(home, verbs)
        + hint_defects(workdir / "hint")
        + branch_defects(home)
        + knobs
    )
    acted = [wake for wake in kill.wakes if wake["acted"]]
    reading = Reading(
        killed_pid=kill.publisher_pid,
        kill_status=kill.publisher_status,
        observed_pid=int(acted[-1]["observed_pid"]) if acted else None,
        flattened=tuple(str(s) for s in acted[-1]["symbols"]) if acted else (),
        kill_marker_phases=tuple(str(r["phase"]) for r in kill.marker_records),
        control_wakes=len(control.wakes),
        control_causes=sum(1 for w in control.wakes if w["cause"] is not None),
        control_broker_calls=len(control.broker_calls),
        die_returncode=die.sentinel_returncode,
        die_marker_phases=tuple(str(r["phase"]) for r in die.marker_records),
        replay_rows=replay_rows,
        fsync_calls=fsyncs,
        authorised_verbs=verbs,
        nixrisk_in_closure=in_closure,
        driven_rules=driven,
        live_wakes=live,
    )
    return defects, reading


def _evidence(reading: Reading) -> str:
    """Every figure this run actually observed. Never a restatement."""
    return (
        f"kill: pid {reading.killed_pid} reaped {reading.kill_status} "
        f"(-{signal.SIGKILL} is SIGKILL), Sentinel attributed to "
        f"{reading.observed_pid}, flattened {list(reading.flattened)}, marker "
        f"{list(reading.kill_marker_phases)}, {reading.live_wakes} live wake(s); "
        f"control: {reading.control_wakes} wake(s), {reading.control_causes} "
        f"cause(s), {reading.control_broker_calls} broker call(s); mid-flatten "
        f"death: rc {reading.die_returncode}, marker "
        f"{list(reading.die_marker_phases)}; replay booked {reading.replay_rows} "
        f"row(s); {reading.fsync_calls} fsync(s) observed on one append; "
        f"authorised broker verbs {list(reading.authorised_verbs)}; nixrisk in "
        f"the Sentinel's import closure: {list(reading.nixrisk_in_closure)}; boot "
        f"rules driven red {list(reading.driven_rules)}"
    )


def _floor_refusal(reading: Reading) -> CheckResult | None:
    """`docs/debug.md` §7.12: a run that reached nothing says so, never PASS."""
    if not reading.authorised_verbs:
        return _cannot_measure(
            f"{SEAM}: {_BROKER_PORT} declares no verb, so ARM 6c's authorised set "
            "is empty and every call in the watchdog would compare against "
            "nothing. The expected side is derived from the frozen seam and an "
            "empty derivation is a refusal, not agreement"
        )
    if reading.kill_status is None:
        return _cannot_measure(
            "the kill drill never reaped a publisher, so ARM 1 has no kernel "
            "status to judge and the headline property was not measured"
        )
    return None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the §12.1 deadman for real. Never repairs — see the reason."""
    try:
        with tempfile.TemporaryDirectory(prefix="nixsentineldrill-") as raw:
            defects, reading = _measure(ctx.nix_home, Path(raw))
        floor = _floor_refusal(reading)
        if floor is not None:
            return floor
        evidence = _evidence(reading)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


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
