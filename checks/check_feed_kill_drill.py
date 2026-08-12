#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check
# must declare the same symbols and must be independently runnable, so the
# blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter.
"""Gate: killing the datafeed under load produces PER-CHANNEL detection that is
attributable to the death.

Subject: `scripts/feed_kill_drill.py` driving `scripts/capture.py`,
`scripts/nixbus/statebus.py` and `scripts/nixbus/price_ring.py`.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §13 objective **V24**
(datafeed half only — see below), §12.7, §10;
`docs/SPEC-AMENDMENTS.md` AMENDMENT 6 (freshness is per-channel).

## WHAT THIS GATE'S GREEN DOES NOT MEAN

**V24 is not discharged by this gate and cannot be.** Its success criterion is
*"prove the order path is undisturbed (latency + zero missed exits)"*, and §10's
Core 2 Risk Engine does not exist on this node — `nixbus.core_map.Role.
RISK_ENGINE` says so. There is no order path to disturb. This gate covers the
**datafeed half**: a real process, under real load, really killed, with detection
really attributable to the killing. `docs/CHECK-DEBT.md` **D1.47** carries the
order-path half and **D1.49** carries the reconnect half.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The feed was never under load, so "the feed stopped" was never a change.**
   *Closed by arm 1:* every trial must show `observed_tick_rate_hz` at or above
   `MIN_RATE_HZ`, and that figure is reconstructed by a separate process from the
   ring's own sequence numbers in shared memory. Nothing the producer said about
   itself is an input to it.
2. **The process was never actually killed.** A drill that stopped *feeding* the
   producer, or let it exit, would produce the same staleness. *Closed by arm 2:*
   the PID is the one this drill spawned, the signal is recorded by number, and
   the verdict requires the KERNEL's reaped wait status to be `-SIGKILL`.
3. **Detection is on a timer and merely FOLLOWS the kill.** The trap this item
   exists to catch. *Closed by arm 4:* the kill offset is randomised per trial and
   the gate requires `stdev(detect - start)` to exceed `stdev(detect - kill)` by
   `ATTRIBUTION_RATIO`. A timer-driven detector produces the reverse ordering; a
   run whose kill offsets did not actually vary is a REFUSAL, because with no
   spread the two hypotheses predict identical numbers.
4. **The detector fires on everything, all the time.** *Closed by arm 5, the
   CONTROL:* an identical producer under identical load, never killed, run at
   least as long as the trials, must produce ZERO `fresh -> stale` transitions —
   and must itself have carried credible load, or "quiet" is a statement about a
   producer that was never running.
5. **One collapsed verdict is reported as several channels.** *Closed twice.* Arm
   3 requires the two channels to go stale at measurably DIFFERENT times, each
   tracking its own threshold. Arm 6 requires the `starve` arm — one channel's
   venue clock frozen with the process ALIVE and nothing killed — to move exactly
   that one channel, which no single timer can do.
6. **The drill silently did fewer trials than it claimed.** *Closed:* the trial
   count is asserted against `TRIALS`, and an attribution refusal string is
   surfaced verbatim rather than folded into a boolean.

## Why this gate is not `DISRUPTIVE`

It kills only processes it spawned itself, by PID, never by name, and both
transports it opens are per-run: an `ipc://` endpoint under a private temporary
directory and a shared-memory segment named with this run's nonce. Nothing
outside its own children is signalled, and the segment is unlinked on every path
including failure.
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

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: The drill spawns `.venv/bin/python3` children that import `pyzmq`.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Six claims. Two of the six were added after the OBSERVER contradicted the
#: first declaration — `check_observed_resource_claims` reported this gate using
#: `file-write:/tmp/nixdrill-*` and `subprocess:.../.venv/bin/python`, neither of
#: which the original four accounted for. Declaring what was measured, rather
#: than arguing with the measurement, is D2.27's whole point.
#: * `subprocess:python3` / `subprocess:python` — the drill re-executes itself as
#:   the producer through `sys.executable`, once per trial plus the control and
#:   starve arms. BOTH spellings, because the observer matches a subprocess claim
#:   by BASENAME and `sys.executable` is `.venv/bin/python` under pytest and
#:   `/usr/bin/python3` under `nix-verify.service`.
#: * `file-write:/tmp` — the private bus root, a `tempfile.TemporaryDirectory`.
#: * `zmq-ipc` — `StatePublisher` binds an `ipc://` endpoint; `StateSubscriber`
#:   connects it. Shared with `check_state_bus`, so the two must not be parallel.
#: * `shm` — `PriceRingWriter` creates a `/dev/shm` segment. Shared with
#:   `check_price_ring`.
#: * `cpu-affinity` — the producer pins itself to §10's Core 1 through the real
#:   `capture.py` path. Shared with `check_core_map`. Not in the observer's
#:   vocabulary (it happens in the CHILD), so it is declared for the PLAN's
#:   benefit: over-declaring costs parallelism, under-declaring costs correctness.
RESOURCES: tuple[str, ...] = (
    "subprocess:python3",
    "subprocess:python",
    "file-write:/tmp",
    "zmq-ipc",
    "shm",
    "cpu-affinity",
)
TIME_BOUND = True
#: Three trials, each a randomised kill plus a staleness window, then a control
#: at least as long as the longest trial, then the starve arm. MEASURED, not
#: budgeted: ~15 s on this node.
EXPECTED_S = 22.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what the system DOES when a process dies; there is no state "
    "on disk to repair, and a 'correction' would mean changing the detector while "
    "it is the thing under measurement"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/feed_kill_drill.py",
    "scripts/capture.py",
    "scripts/nixbus/price_ring.py",
    "scripts/nixbus/statebus.py",
)

NAME = "check_feed_kill_drill"

#: Randomised kills. Three is the floor the attribution statistic accepts; more
#: costs seconds per trial and buys precision this verdict does not turn on.
TRIALS = 3

#: A trial below this was not under load. Two orders of magnitude below the
#: ~2.6e6 ticks/s measured on this node, so it is a FLOOR and not a restatement
#: of today's throughput — a figure anchored to the current rate would redden the
#: day the box got slower for an unrelated reason (`debug.md` §7.4).
MIN_RATE_HZ = 10_000.0

#: The two channels must go stale at least this far apart. Their thresholds
#: differ by 0.70 s; half of that leaves room for scheduler noise while still
#: being impossible for one shared timer to produce.
MIN_CHANNEL_GAP_S = 0.35

_TICK = "tick"
_POLL = "poll"


def _load() -> tuple[Any, str]:
    """Import the drill lazily. CANNOT_MEASURE when the interpreter lacks pyzmq —
    `nix-verify.service` runs `verify.py` under `/usr/bin/python3`."""
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    for extra in (str(scripts), str(scripts / "broker")):
        if extra not in sys.path:
            sys.path.append(extra)
    try:
        import feed_kill_drill  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, f"cannot import feed_kill_drill under {sys.executable}: {exc!r}"
    return feed_kill_drill, ""


def _arm1_load(result: dict, defects: list, ev: list) -> None:
    """Every trial was under credible, MEASURED load."""
    site = "scripts/nixbus/price_ring.py:PriceRingReader.read_seq"
    rates = [trial["observed_tick_rate_hz"] for trial in result["trials"]]
    slow = [rate for rate in rates if rate < MIN_RATE_HZ]
    if slow:
        defects.append(
            (
                site,
                (
                    f"trial rate(s) {[round(r) for r in slow]} Hz below the "
                    f"{MIN_RATE_HZ:.0f} Hz floor — a datafeed that was not "
                    "delivering cannot be shown to have stopped delivering"
                ),
            )
        )
        return
    ev.append(
        "LOAD MEASURED downstream from ring sequence numbers: "
        + ", ".join(f"{rate:,.0f} ticks/s" for rate in rates)
    )


def _arm2_death(result: dict, defects: list, ev: list) -> None:
    """The kernel's account of the death, per trial: PID, signal, wait status."""
    site = "os.kill(pid, SIGKILL) / subprocess.Popen.wait"
    for trial in result["trials"]:
        expected = -trial["signal_number"]
        if trial["reap_status"] != expected:
            defects.append(
                (
                    site,
                    (
                        f"trial {trial['trial']} pid={trial['pid']} was sent "
                        f"{trial['signal']} ({trial['signal_number']}) and reaped with "
                        f"status {trial['reap_status']}, not {expected} — the process "
                        "did not die of the signal this drill sent it"
                    ),
                )
            )
            return
    ev.append(
        "DEATHS: "
        + "; ".join(
            f"pid={t['pid']} {t['signal']} reaped={t['reap_status']}"
            for t in result["trials"]
        )
    )


def _stale_at(trial: dict, channel: str) -> float | None:
    """When this channel first read STALE, relative to the kill."""
    return trial["detect_latency_s"].get(channel)


def _arm3_per_channel(result: dict, defects: list, ev: list) -> None:
    """Both channels moved, at DIFFERENT times, each tracking its own threshold."""
    site = "scripts/capture.py:FeedStalenessMonitor.observe"
    gaps: list[float] = []
    for trial in result["trials"]:
        tick, poll = _stale_at(trial, _TICK), _stale_at(trial, _POLL)
        if tick is None or poll is None:
            defects.append(
                (
                    site,
                    (
                        f"trial {trial['trial']} produced fresh->stale on "
                        f"{sorted(trial['detect_latency_s'])} — AMENDMENT 6 requires "
                        "a verdict per channel and both channels' venue clocks "
                        "stopped at the same instant"
                    ),
                )
            )
            return
        if poll - tick < MIN_CHANNEL_GAP_S:
            defects.append(
                (
                    site,
                    (
                        f"trial {trial['trial']}: tick went stale at {tick:.3f}s and "
                        f"poll at {poll:.3f}s, {poll - tick:.3f}s apart (floor "
                        f"{MIN_CHANNEL_GAP_S}s) — channels this close together are "
                        "compatible with one collapsed timer serving both"
                    ),
                )
            )
            return
        gaps.append(poll - tick)
    thresholds = result["thresholds_s"]
    ev.append(
        f"PER-CHANNEL: tick(threshold {thresholds[_TICK]}s) and poll(threshold "
        f"{thresholds[_POLL]}s) separated by "
        + ", ".join(f"{gap:.3f}s" for gap in gaps)
    )


def _arm4_attribution(result: dict, defects: list, ev: list) -> str:
    """Detection tracks the KILL clock, not the wall clock. The core arm.

    Returns a non-empty REFUSAL string when the statistic could not have
    discriminated at all. That is CANNOT_MEASURE and deliberately not a FAIL: an
    instrument with no power has said nothing about its subject, and
    `nix_check_contract.md` §17 is explicit that a property which could not be
    measured is neither proven nor disproven.
    """
    site = "scripts/feed_kill_drill.py:attribution"
    for channel in (_TICK, _POLL):
        stats = result["attribution"][channel]
        if stats.get("refusal"):
            return f"{site} — {channel}: {stats['refusal']}"
        if not stats["attributed"]:
            defects.append(
                (
                    site,
                    (
                        f"{channel}: stdev(detect-kill)={stats['detect_latency_stdev_s']:.4f}s "
                        f"vs stdev(detect-start)={stats['detect_since_start_stdev_s']:.4f}s "
                        f"(ratio {stats['ratio']:.1f}, need >{result['attribution_ratio']}) "
                        "over kill offsets that varied by "
                        f"{stats['kill_offset_stdev_s']:.4f}s — detection is not "
                        "tracking the death"
                    ),
                )
            )
            return ""
        ev.append(
            f"ATTRIBUTION {channel}: n={stats['n']} kill-offset stdev "
            f"{stats['kill_offset_stdev_s']:.4f}s; detect-kill stdev "
            f"{stats['detect_latency_stdev_s']:.4f}s (mean "
            f"{stats['detect_latency_mean_s']:.4f}s) vs detect-start stdev "
            f"{stats['detect_since_start_stdev_s']:.4f}s; ratio {stats['ratio']:.1f}"
        )
    return ""


def _arm5_control(result: dict, defects: list, ev: list) -> None:
    """CONTROL — same load, no kill, at least as long: the detector stays quiet."""
    site = "scripts/feed_kill_drill.py:_hold(control)"
    control = result["control"]
    if control["observed_tick_rate_hz"] < MIN_RATE_HZ:
        defects.append(
            (
                site,
                (
                    f"the control arm observed {control['observed_tick_rate_hz']:.0f} "
                    f"ticks/s, below the {MIN_RATE_HZ:.0f} Hz floor — a silent "
                    "detector over a producer that was not producing proves nothing"
                ),
            )
        )
        return
    fired = [t for t in control["transitions"] if t["to"] == "stale"]
    if fired:
        defects.append(
            (
                site,
                (
                    f"the control arm was never killed and still produced "
                    f"{len(fired)} fresh->stale transition(s) "
                    f"({[t['channel'] for t in fired]}) over {control['held_s']:.2f}s "
                    "— the detector fires without a death, so every trial's red is "
                    "uninformative"
                ),
            )
        )
        return
    ev.append(
        f"CONTROL: {control['held_s']:.2f}s at "
        f"{control['observed_tick_rate_hz']:,.0f} ticks/s, no kill, 0 fresh->stale"
    )


def _arm6_starve(result: dict, defects: list, ev: list) -> None:
    """ONE channel starved, process ALIVE: exactly that channel may move."""
    site = "scripts/feed_kill_drill.py:_hold(starve)"
    starve = result["starve"]
    starved = starve["starved_channel"]
    moved = sorted({t["channel"] for t in starve["transitions"] if t["to"] == "stale"})
    if moved != [starved]:
        defects.append(
            (
                site,
                (
                    f"freezing only the {starved!r} channel's venue clock, with the "
                    f"process alive and the other channel still publishing, moved "
                    f"{moved or 'no channel'} to stale — AMENDMENT 6 requires the "
                    "channels to report independently"
                ),
            )
        )
        return
    ev.append(
        f"INDEPENDENCE: {starved!r} starved with the process ALIVE -> only "
        f"{moved} went stale over {starve['held_s']:.2f}s"
    )


def _drive(drill: Any) -> dict:
    """Run the drill in a private temporary bus root. Cleaned on every path."""
    with tempfile.TemporaryDirectory(prefix="nixdrill-") as tmp:
        result = drill.run_drill(
            Path(tmp), trials=TRIALS, pin=True, starve=True, plane2=False
        )
    result["attribution_ratio"] = drill.ATTRIBUTION_RATIO
    return result


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Kill a live datafeed under load and prove the detection was caused by it."""
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
    if len(result["trials"]) != TRIALS:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"{len(result['trials'])} trial(s) completed, {TRIALS} required — "
                "an attribution statistic over fewer trials than it claims is not a "
                "weaker result, it is a wrong one"
            ),
        )
    resolution = (
        f"observer resolution {result['observer_resolution_ms']}ms — nothing here "
        "attributes a death more finely than that"
    )
    evidence: list[str] = [resolution]
    defects: list[tuple[str, str]] = []
    _arm1_load(result, defects, evidence)
    _arm2_death(result, defects, evidence)
    _arm3_per_channel(result, defects, evidence)
    refusal = _arm4_attribution(result, defects, evidence)
    if refusal and not defects:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=refusal,
            evidence="; ".join(evidence),
        )
    _arm5_control(result, defects, evidence)
    _arm6_starve(result, defects, evidence)
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
