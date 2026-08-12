#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check
# must declare the same symbols and must be independently runnable, so the
# blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter. Same pragma, same
# reason, as `scripts/nixverify/actuation.py` line 1.
"""Gate: `capture.py`'s PER-CHANNEL staleness transitions reach the journal.

Subject: `scripts/capture.py`'s Plane-2 stream and the journal it writes to.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.10 (two-plane model,
locked — *"feed staleness transitions"* is a Plane-2-only inventory row, and
*"Plane 1 ... Limiter sole writer ... No new writers, ever"*);
`docs/SPEC-AMENDMENTS.md` AMENDMENT 6 (freshness is per-channel, ARC 023 — the
ruling text calls itself AMENDMENT 5 and that file records why the number moved);
`docs/directory_structure.md` (`logs/` holds non-Plane artifacts ONLY).

## WHY `capture.py` OWES THIS AND THE BROKER LIBRARIES DO NOT

§12.10: *"Each **process** writes its own structured one-line events."*
`broker_datafeed_ibkr.py` is an in-process library living inside `capture.py`
(§2A:86) and has no stream of its own. `capture.py` is the process, so the
obligation lands here — and AMENDMENT 6 is what turned it from one event per
symbol into one event **per channel**, because a symbol observed by two channels
with two lags has two staleness states and collapsing them is F21.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **It asks the emitter whether it emitted.** *Closed:* the verdict comes from
   `journalctl` reading the journal back, exactly as `check_verify_logging`'s
   does. The emitter's counters are corroboration, never the verdict.
2. **It finds an entry from an earlier run.** *Closed by the NONCE*, which rides
   in the `symbol=` field of the real event through the real path — not bolted on
   as an extra field the production path would never carry.
3. **It proves a round-trip and never checks the CHANNEL.** A per-symbol event
   that arrived would satisfy a shape test and would be exactly the collapse
   AMENDMENT 6 forbids. *Closed by arm 3*, which requires `channel=`, `from=`,
   `to=` and the numbers behind the verdict (`excess_staleness_s`,
   `threshold_s`, `lag_provenance`) on every recovered line.
4. **It emits on every observation and calls that "transitions".** §12.10 rejects
   chatty per-tick logging by name. *Closed by arm 4, the CONTROL:* the SAME
   report is observed twice and the second observation must emit NOTHING. A gate
   that counted only "at least one event" would pass a level-logger.
5. **It proves Plane 2 and ignores Plane 1.** *Closed by arms 5 and 6:*
   `scripts/capture.py` is parsed and must import no database driver, and
   `logs/` must hold no `proc=capture.py` artifact.

**Zero recovered entries is CANNOT_MEASURE, never PASS.**

## This gate does NOT pin a core, deliberately

`CaptureProcess.start()` normally pins to §10's Core 1. Driven here with
`pin=False`: a gate that pinned would confine `verify.py`'s own process to one
core for the rest of the run — an instrument changing the machine it is
measuring. `checks/check_core_map.py` measures the pin, in a spawned process,
where it belongs.
"""

from __future__ import annotations

import ast
import dataclasses
import secrets
import sys
import time
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
from nixverify.plane2 import JOURNAL_SOCKET, JOURNALCTL, Plane2, read_back

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `capture.py` imports `nixbus.statebus` -> `pyzmq`, a `pinned_deps.json` pin.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: ONE claim: the journal. Both halves of it are OBSERVABLE by
#: `check_observed_resource_claims` and both are covered by this token —
#: `SysLogHandler` connects the AF_UNIX socket `/dev/log` (audited as
#: `socket.connect`), and `read_back` spawns `/usr/bin/journalctl` (audited as
#: `subprocess.Popen`). No publisher and no ring are constructed here, so this
#: gate makes no `zmq-ipc` and no `shm` claim, and it deliberately spawns nothing
#: else — the reason `check_core_map` and not this gate owns the child process.
RESOURCES: tuple[str, ...] = ("journal",)
TIME_BOUND = True
#: Dominated by READBACK_TIMEOUT_S below, not by an observed duration.
EXPECTED_S = 8.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the journal transport and the emission rule inside a process; "
    "'correcting' either would mean writing the events under measurement"
)
SUBJECTS: tuple[str, ...] = ("scripts/capture.py",)

NAME = "check_capture_plane2"

READBACK_TIMEOUT_S = 6.0
READBACK_POLL_S = 0.2

#: A Plane-1 writer is a process that talks to Postgres. §12.10 says the Limiter
#: is the only one, forever, so `capture.py` importing any of these would be the
#: violation whatever it went on to do with the handle.
_DB_MODULES = frozenset(
    {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "pg8000", "sqlite3", "MySQLdb"}
)

#: §12.10's fields, plus the three numbers AMENDMENT 6 requires a per-channel
#: verdict to carry so an operator can recompute it.
_REQUIRED_FIELDS = (
    "ts",
    "proc",
    "event",
    "symbol",
    "channel",
    "from",
    "to",
    "excess_staleness_s",
    "threshold_s",
    "lag_provenance",
)


@dataclasses.dataclass(frozen=True)
class _Emitted:
    """The emitter's own counters, snapshotted before the transport is closed."""

    delivered: int
    failed: int
    last_error: str


def _load() -> tuple[Any, str]:
    """Import `capture` and the seam types lazily. CANNOT_MEASURE, never a load
    error for the whole check, when the interpreter lacks pyzmq —
    `nix-verify.service` runs `verify.py` under `/usr/bin/python3`."""
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    for extra in (str(scripts), str(scripts / "broker")):
        if extra not in sys.path:
            sys.path.append(extra)
    try:
        import broker_seam  # pylint: disable=import-outside-toplevel
        import capture  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, f"cannot import capture.py under {sys.executable}: {exc!r}"
    return (capture, broker_seam), ""


def _report(seam: Any, symbol: str, state: Any, now: float) -> Any:
    """Build one per-channel `FreshnessReport` on the TICK channel.

    Uses the seam's own `FeedLag`/`ChannelFreshness`/`FreshnessReport` rather than
    a stand-in, so `ChannelFreshness.__post_init__`'s refusal of a verdict that
    contradicts its own numbers applies to this gate's inputs too. A stub would
    let the gate feed `capture.py` a state the real seam could never produce.
    """
    lag = seam.FeedLag(
        declared_lag_s=1.0,
        observed_lag_s=None,
        observed_n=0,
        provenance=seam.LagProvenance.VENDOR_DECLARED,
        granted_mode=seam.MarketDataMode.DELAYED,
    )
    threshold = 5.0
    excess = {"fresh": 0.5, "stale": 60.0}.get(state.value)
    channel = seam.ChannelFreshness(
        channel=seam.FeedChannel.TICK,
        venue_ts=None if excess is None else now - 1.0,
        lag=lag,
        excess_staleness_s=excess,
        threshold_s=threshold,
        state=state,
        recv_ts=now,
    )
    return seam.FreshnessReport(symbol=symbol, now=now, channels=(channel,))


def _drive(loaded: tuple[Any, Any], nonce: str) -> tuple[list[Any], int, _Emitted]:
    """Run the real emission path. Returns `(transitions, repeat_count, counters)`.

    The counters are snapshotted BEFORE `close()`. `Plane2.close()` drops its
    handler, after which `emitted` reads 0 — so a gate holding the object across
    the close would report "the emitter delivered nothing" about an emitter that
    had delivered everything, which is a false negative built into the evidence.
    """
    capture, seam = loaded
    plane = Plane2(identifier=capture.IDENTIFIER, process=capture.PROCESS)
    # pin=False: see the module docstring. A gate must not repin its own runner.
    process = capture.CaptureProcess(plane2=plane, pin=False)
    process.start()
    symbol = f"GATE-{nonce}"
    now = time.time()
    transitions: list[Any] = []
    for state in (
        seam.ChannelState.FRESH,
        seam.ChannelState.STALE,
        seam.ChannelState.CANNOT_MEASURE,
    ):
        transitions.extend(process.observe_freshness(_report(seam, symbol, state, now)))
    # CONTROL — the SAME state again. A transition log emits nothing here; a
    # level log emits a fourth event.
    repeat = process.observe_freshness(
        _report(seam, symbol, seam.ChannelState.CANNOT_MEASURE, now)
    )
    counters = _Emitted(
        delivered=plane.emitted, failed=plane.failed, last_error=plane.last_error
    )
    process.close()
    return transitions, len(repeat), counters


def _await_readback(identifier: str, nonce: str) -> tuple[list[str], str]:
    """Poll the journal until this run's events land or the budget is spent."""
    deadline = time.perf_counter() + READBACK_TIMEOUT_S
    while time.perf_counter() < deadline:
        lines, error = read_back(identifier=identifier, since="-2 min", grep=nonce)
        if lines:
            return lines, ""
        if error:
            return [], error
        time.sleep(READBACK_POLL_S)
    return [], ""


def _fields(line: str) -> dict[str, str]:
    """Split a §12.10 one-line event into its key=value fields."""
    found: dict[str, str] = {}
    for token in line.split(" "):
        if "=" in token:
            key, _, value = token.partition("=")
            found.setdefault(key, value)
    return found


#: The three moves the driver provokes, in order. ARC 027 (B3): hoisted to module
#: scope so `_arm_roundtrip`'s journal expectation and `_arm_transitions`' move
#: expectation are ONE value. The round-trip arm previously carried the literal
#: `3` inside a sentence, and a literal inside a sentence is where a stale number
#: is invisible.
EXPECTED_MOVES: tuple[tuple[str, str], ...] = (
    ("unobserved", "fresh"),
    ("fresh", "stale"),
    ("stale", "cannot_measure"),
)


def _arm_transitions(
    transitions: list[Any], repeat: int, defects: list, ev: list
) -> None:
    """Three moves, and the fourth observation moves nothing (CONTROL)."""
    site = "scripts/capture.py:FeedStalenessMonitor.observe"
    moves = [(t.previous, t.current.value) for t in transitions]
    expected = list(EXPECTED_MOVES)  # `moves` is a list; compare like with like
    if moves != expected:
        defects.append((site, f"transitions were {moves}, expected {expected}"))
        return
    if repeat:
        defects.append(
            (
                site,
                (
                    f"re-observing an UNCHANGED channel produced {repeat} more "
                    "event(s) — §12.10's inventory row is *staleness TRANSITIONS*, "
                    "and a level log at feed-poll rate is the chatty logging that "
                    "section rejects by name"
                ),
            )
        )
        return
    ev.append(f"transitions {moves}; CONTROL: unchanged re-observation emitted 0")


def _arm_roundtrip(lines: list[str], defects: list, ev: list, produced: int) -> None:
    """This run's events are in the journal — three of them, not four.

    ARC 027 (B3), D3.21's class. `produced` is the number of transitions the
    driver actually got back from the process, and the narration now reports it
    instead of asserting the constant `3`. Under a Plane-2 delivery failure the
    process produces fewer, the arm FAILs correctly, and the sentence beside the
    failure used to tell the operator a number nothing had measured.

    **The COMPARISON stays against `len(EXPECTED_MOVES)`, deliberately.**
    Comparing the journal count to `produced` would compare the measurement to
    itself: a process that produced zero transitions would then be satisfied by
    zero journal entries, which is the vacuous pass this arm exists to refuse.
    One number is the expectation, the other is the observation, and only the
    observation belongs in the narration.
    """
    site = "journal(-t nix-capture)"
    events = [line for line in lines if "event=feed_staleness_transition" in line]
    if len(events) != len(EXPECTED_MOVES):
        defects.append(
            (
                site,
                (
                    f"{len(events)} feed_staleness_transition entr(ies) carrying this "
                    f"run's nonce reached the journal; {len(EXPECTED_MOVES)} were "
                    f"expected and the process produced {produced}"
                ),
            )
        )
        return
    ev.append(f"round-trip: {len(events)} per-channel transition events recovered")


def _arm_fields(lines: list[str], defects: list, ev: list) -> None:
    """Every recovered line carries §12.10's fields AND the per-channel numbers."""
    site = "journal entry"
    for line in lines:
        if "event=feed_staleness_transition" not in line:
            continue
        fields = _fields(line)
        missing = [key for key in _REQUIRED_FIELDS if key not in fields]
        if missing:
            defects.append((site, f"fields {missing} missing from {line[:90]!r}"))
            return
        if fields["proc"] != "capture.py":
            defects.append((site, f"proc={fields['proc']!r}, expected capture.py"))
            return
        if fields["channel"] != "tick":
            defects.append((site, f"channel={fields['channel']!r}, expected tick"))
            return
    ev.append("every recovered event carries ts/proc/event/symbol/channel/from/to")


def _arm_no_plane1(home: Path, defects: list, ev: list) -> None:
    """§12.10: Plane 1 has one writer and it is not this process."""
    source = home / "scripts" / "capture.py"
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError) as exc:
        defects.append((str(source), f"cannot parse to prove Plane-1 absence: {exc!r}"))
        return
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    offenders = sorted(imported & _DB_MODULES)
    if offenders:
        defects.append(
            (
                "scripts/capture.py",
                (
                    f"imports {offenders} — §12.10 says of Plane 1 'Limiter sole "
                    "writer ... No new writers, ever', and capture.py is not the "
                    "Limiter"
                ),
            )
        )
        return
    ev.append("Plane-1 absence: capture.py imports no database driver")


def _arm_logs_dir(home: Path, defects: list, ev: list) -> None:
    """Plane 2 never lands in `logs/` (`directory_structure.md`)."""
    logs = home / "logs"
    strays: list[str] = []
    if logs.is_dir():
        for path in logs.rglob("*"):
            if not path.is_file():
                continue
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:20000]
            except OSError:
                continue
            if "proc=capture.py" in head or "nix-capture" in head:
                strays.append(str(path.relative_to(home)))
    for stray in strays:
        defects.append((stray, "capture.py Plane-2 artifact found under logs/"))
    if not strays:
        ev.append("logs/ holds no capture.py Plane-2 artifact")


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


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive per-channel transitions through the real emitter and read them back."""
    blocked = _precondition()
    if blocked is not None:
        return blocked
    loaded, error = _load()
    if loaded is None:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)

    home = Path(ctx.nix_home)
    evidence: list[str] = []
    defects: list[tuple[str, str]] = []
    nonce = f"ARC026-{secrets.token_hex(8)}"
    transitions, repeat, counters = _drive(loaded, nonce)
    lines, read_error = _await_readback(loaded[0].IDENTIFIER, nonce)
    if read_error:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"journal unreadable: {read_error}",
        )
    if not lines:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"the process reported emitting {counters.delivered} record(s) and "
                f"NONE carrying nonce {nonce} reached the journal within "
                f"{READBACK_TIMEOUT_S}s (last_error={counters.last_error or '-'}) — "
                "this is CANNOT_MEASURE and is deliberately never PASS"
            ),
        )
    evidence.append(f"emitter delivered={counters.delivered} failed={counters.failed}")

    _arm_transitions(transitions, repeat, defects, evidence)
    _arm_roundtrip(lines, defects, evidence, len(transitions))
    _arm_fields(lines, defects, evidence)
    _arm_no_plane1(home, defects, evidence)
    _arm_logs_dir(home, defects, evidence)
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
