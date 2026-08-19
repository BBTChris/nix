#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: the §3 gate pass never blocks on a group-commit — measured UNDER LOAD.

ARC 035 / Stage 1 / sub-agent A (A3). Subject:
`scripts/plane1_hotpath_drill.py`, over `scripts/nixrisk/gate.py`,
`scripts/nixrisk/wal.py` and `scripts/nixrisk/plane1_sink.py`.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §11 (the entry pathway is
*cache reads and arithmetic only*) and §11 item 6 (*group-commit event-log writes off
the hot path, WAL-buffered*).

ONE property (§5.5): *a Plane-1 group-commit in flight does not appear in the
gate's latency, and an instrument that could not see it if it did is not
reporting that property.*

## THE §0a THE ARC BRIEF WROTE THIS GATE AGAINST

> *an idle-system latency test proves NOTHING about hot-path isolation.*

Correct, and it is the easy trap: time the gate on a quiet box, see microseconds,
declare isolation. It measures the box. A gate that DID block on Postgres would
look identical, because on an idle system there is nothing to block on.

So the verdict is a RELATION between three arms of the same loop, never any one
figure (the drill builds them; this gate only judges them):

* **BASELINE** — the gate loop alone. The number an idle-system test reports.
* **CONCURRENT** — the same loop while a persistence thread really is
  committing through a sink with a real delay in `commit()`.
* **SYNCHRONOUS CONTROL** — the same loop with the identical slow sink wired
  INLINE, inside the timed region.

**ARM 3 is what makes ARMS 1–2 mean anything.** If a deliberately slow sink
placed directly on the hot path does NOT inflate the latency, then the timing is
not measuring the hot path at all and no conclusion about isolation may be drawn
from it. That is checked explicitly (`discriminates`) and a failure of it is
CANNOT_MEASURE, not a PASS.

A fourth arm repeats CONCURRENT against the REAL `Plane1PostgresSink` and a real
scratch database, so the claim is about the shipped sink and not only about a
`time.sleep`.

## THE STATISTIC

p99 over n = 2,000 timed gate evaluations per fast arm (300 for the control,
each of which pays a real commit). The median and max travel with it. **A mean
would be the wrong instrument**: a hot path that blocks does so on the minority
of iterations that coincide with a flush, and averaging is exactly the operation
that hides a minority. A single timing is not a measurement and none is reported.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **Nothing is committed during the concurrent arm.** If the hot loop finishes
   before a single commit completes, "the gate did not block" is trivially true
   and says nothing. *Closed:* `commits_during_hot_loop` must meet
   `MIN_OVERLAP_COMMITS`, or CANNOT_MEASURE.
2. **The instrument cannot see blocking.** *Closed:* the synchronous control's
   p99 must be at least `CONTROL_INFLATION_FLOOR` x the delay it was given —
   i.e. the slow sink must actually show up when it IS on the hot path.
3. **The delay is not actually slow.** A sink that "sleeps" for nothing would
   satisfy 2 vacuously by both arms being equal. *Closed:* the same floor in 2
   is expressed against the CONFIGURED delay, so a zero delay cannot pass it.
4. **The gate loop is not the real gate.** A synthetic `pass` loop proves
   nothing about `nixrisk.gate`. *Closed:* the drill builds the shipped
   `default_manifest` and a real `GatePass`, and this gate re-asserts the
   drill's own module identity by importing it rather than reimplementing the
   loop here.
5. **The postgres arm silently vanishes on a box without a cluster**, leaving
   the whole verdict resting on a `time.sleep`. *Closed:* the arm reports
   `available: False` with a reason and the evidence prints it; the sleep-based
   arms still stand on their own control, and the postgres arm's absence is
   named rather than invisible.

## A MEASURED ARTEFACT THE VERDICT DELIBERATELY DOES NOT TURN ON

The concurrent arm's **max** is routinely ~one full commit while its p99 is tens
of microseconds. That is CPython's 5 ms switch interval meeting the drill's WAL
mutex — the persistence thread holds the lock, releases the GIL inside `fsync`,
and needs the GIL back to release the lock while the hot thread holds it. It is a
real hazard of putting a mutex on the hot path, it is a finding of ARC 035 / A,
and it is NOT what §11 item 6 is about. The gate judges the p99 and prints the max, so
the artefact is visible without being able to decide a verdict.

## WHAT THIS GATE CANNOT PROVE, STATED RATHER THAN IMPLIED

`time.sleep` and socket/subprocess I/O both RELEASE the GIL, so the concurrency
is real for the shape under test — a sink blocked on I/O, which is what a
Postgres commit is. **This gate does not prove isolation against a sink that
burns CPU in Python**; the GIL would serialise that, and §11 item 6's failure mode is
I/O, not computation. It proves nothing about fsync durability
(`check_plane1_wal` owns that, on syscalls), nothing about the schema
(`check_plane1_schema`), and nothing about who may write (`check_plane1_sole_writer`).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
#: MEASURED shape, not budgeted: the synchronous control pays 300 real commits
#: at the configured delay, which dominates. The rest is in-process.
EXPECTED_S = 20.0
ON_FAIL = "continue"
DEPENDS_ON: tuple[str, ...] = ("check_plane1_schema",)
#: The drill runs IN THIS PROCESS (threads, not children), so there is no
#: `subprocess:python` claim to make. It writes WALs under `/tmp` and its
#: postgres arm spawns psql/createdb/dropdb for its own scratch database.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:psql",
    "subprocess:createdb",
    "subprocess:dropdb",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is WHERE the group-commit runs relative to the gate. There is "
    "no state on disk to repair, and a 'correction' would mean editing the hot "
    "path while it is the thing under measurement"
)
ANCHOR = "scripts/plane1_hotpath_drill.py"
SUBJECTS: tuple[str, ...] = (
    "scripts/plane1_hotpath_drill.py",
    "scripts/nixrisk/plane1_sink.py",
)

NAME = "check_plane1_hot_path"

#: Non-vacuity floors. FLOORS, not today's numbers.
#: At least this many group-commits must COMPLETE while the concurrent arm's hot
#: loop is running, or the two never overlapped and the arm measured an idle box.
MIN_OVERLAP_COMMITS: Final[int] = 3
#: The synchronous control's p99 must reach this fraction of the configured
#: delay. Below it, the instrument cannot see blocking and its green is about a
#: timer that measures nothing.
CONTROL_INFLATION_FLOOR: Final[float] = 0.5
#: The concurrent arm's p99 must stay below this fraction of the delay. Ample
#: headroom on purpose: the claim is two orders of magnitude, and a tight
#: threshold would make the gate a flake detector for the scheduler.
CONCURRENT_CEILING: Final[float] = 0.10
#: And it must stay within this multiple of the BASELINE, which is the arm that
#: says what the gate costs with nothing happening at all. Ten, not two, and the
#: reason is measured rather than cautious: this box runs four parallel suites
#: during an arc's Stage 1, and the baseline p99 is ~10 us while a real block
#: would be ~2,000. A 10x bound still catches a hot path paying any material
#: share of a commit; a 2x bound would catch the scheduler.
CONCURRENT_VS_BASELINE_MAX: Final[float] = 10.0

#: The site a FAIL is reported under. ARC 038 / sub-agent F (finding FF6): this
#: read `scripts/nixrisk/wal.py:GroupCommitWriter.drain_once (off the hot path)`,
#: and with a 2 ms block PLANTED inside `GatePass.evaluate` the gate went RED
#: while naming a collaborator the same string calls *off* the path the detail
#: was about. A constant site cannot point at the subject that moved; naming the
#: MEASURED path, with the commit path beside it, at least points at the thing
#: the arms time. CHECK-DEBT D3.406.
_SITE = (
    "scripts/nixrisk/gate.py:GatePass.evaluate (the timed hot path) vs "
    "scripts/nixrisk/wal.py:GroupCommitWriter.drain_once (the commit, off it)"
)


def _import_drill() -> tuple[Any, str]:
    """Lazy import so an unimportable subject is CANNOT_MEASURE, not a load error."""
    try:
        import plane1_hotpath_drill  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return (
            None,
            f"cannot import plane1_hotpath_drill under {sys.executable}: {exc!r}",
        )
    return plane1_hotpath_drill, ""


def judge(result: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """The whole verdict over one drill result. `(unmeasurable, defects, evidence)`.

    Split out and parameterised by the RESULT DICT so the can-fail suite can hand
    it a doctored measurement and drive the SHIPPED judgement over it, without
    needing to make a real machine block.
    """
    unmeasurable: list[str] = []
    defects: list[str] = []
    evidence: list[str] = []

    delay_us = float(result["delay_s"]) * 1_000_000.0
    baseline = result["baseline"]
    concurrent = result["concurrent"]
    control = result["synchronous_control"]

    # HAZARD 1 — did the two ever overlap?
    overlap = int(concurrent["commits_during_hot_loop"])
    if overlap < MIN_OVERLAP_COMMITS:
        unmeasurable.append(
            f"only {overlap} group-commit(s) completed while the concurrent hot "
            f"loop ran, against a floor of {MIN_OVERLAP_COMMITS}. The gate was "
            f"never actually concurrent with a commit, so 'the gate did not "
            f"block' is trivially true and measures an idle system — the exact "
            f"§0a the arc brief names"
        )

    # HAZARD 2/3 — CAN THE INSTRUMENT SEE BLOCKING AT ALL?
    if control["p99_us"] < CONTROL_INFLATION_FLOOR * delay_us:
        unmeasurable.append(
            f"THE CONTROL FAILED: with the identical slow sink wired INLINE on "
            f"the hot path, p99 was {control['p99_us']:.1f}us against a "
            f"{delay_us:.0f}us delay (floor "
            f"{CONTROL_INFLATION_FLOOR * delay_us:.0f}us). If a commit placed "
            f"directly on the hot path does not show up in the timing, this "
            f"instrument cannot discriminate and the concurrent arm's small "
            f"number is about a timer, not about §11 item 6"
        )
    if unmeasurable:
        return unmeasurable, defects, evidence

    evidence.append(
        f"CONTROL (slow sink INLINE, n={control['n']}): p50 "
        f"{control['p50_us']:.1f}us, p99 {control['p99_us']:.1f}us, max "
        f"{control['max_us']:.1f}us against a {delay_us:.0f}us commit — the "
        f"instrument DOES see blocking"
    )

    # THE PROPERTY.
    if concurrent["p99_us"] > CONCURRENT_CEILING * delay_us:
        defects.append(
            f"§11 item 6: with a group-commit in flight the gate's p99 was "
            f"{concurrent['p99_us']:.1f}us, above "
            f"{CONCURRENT_CEILING * delay_us:.0f}us ({CONCURRENT_CEILING:.0%} of "
            f"one commit). The entry pathway is 'cache reads and arithmetic only' "
            f"(§11) and a gate that pays a fraction of the commit is a gate the "
            f"commit is on"
        )
    if concurrent["p99_us"] > CONCURRENT_VS_BASELINE_MAX * max(
        baseline["p99_us"], 1e-6
    ):
        defects.append(
            f"§11 item 6: the gate's p99 rose from {baseline['p99_us']:.1f}us with "
            f"nothing happening to {concurrent['p99_us']:.1f}us with commits in "
            f"flight — more than {CONCURRENT_VS_BASELINE_MAX}x. The commit is "
            f"visible in the hot path"
        )
    evidence.append(
        f"BASELINE (gate alone, n={baseline['n']}): p50 {baseline['p50_us']:.1f}us, "
        f"p99 {baseline['p99_us']:.1f}us. CONCURRENT (n={concurrent['n']}, "
        f"{overlap} commit(s) completed during the loop, "
        f"{concurrent['rows_committed']} row(s)): p50 "
        f"{concurrent['p50_us']:.1f}us, p99 {concurrent['p99_us']:.1f}us, max "
        f"{concurrent['max_us']:.1f}us — "
        f"{control['p99_us'] / max(concurrent['p99_us'], 1e-6):.0f}x below the "
        f"synchronous control"
    )

    # THE POSTGRES ARM — the shipped sink, not a sleep.
    postgres = result["postgres"]
    if not postgres.get("available"):
        evidence.append(
            "POSTGRES ARM SKIPPED and NAMED (§17, not a silent pass): "
            f"{postgres.get('error', 'no reason given')}. The verdict above rests "
            "on the sleep-based arms and their control"
        )
    else:
        if postgres["groups_during_hot_loop"] < 1 or postgres["rows_landed"] < 1:
            defects.append(
                f"the POSTGRES arm landed {postgres['rows_landed']} row(s) in "
                f"{postgres['groups_during_hot_loop']} group(s) during the hot "
                f"loop — the real sink never committed, so the arm measured "
                f"nothing about the shipped writer"
            )
        elif postgres["p99_us"] > CONCURRENT_VS_BASELINE_MAX * max(
            baseline["p99_us"], 1e-6
        ):
            defects.append(
                f"§11 item 6 against the REAL sink: the gate's p99 was "
                f"{postgres['p99_us']:.1f}us with Plane1PostgresSink committing "
                f"concurrently, against a baseline of {baseline['p99_us']:.1f}us"
            )
        else:
            evidence.append(
                f"POSTGRES (real Plane1PostgresSink, n={postgres['n']}, "
                f"{postgres['groups_during_hot_loop']} group(s), "
                f"{postgres['rows_landed']} row(s) landed): p50 "
                f"{postgres['p50_us']:.1f}us, p99 {postgres['p99_us']:.1f}us"
            )
    return unmeasurable, defects, evidence


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Run the drill and judge the RELATION between its arms."""
    del ctx
    drill, error = _import_drill()
    if drill is None:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, site=ANCHOR, detail=error
        )
    root = Path(tempfile.mkdtemp(prefix="nixp1hot-"))
    try:
        result = drill.run_drill(root)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail=f"the drill raised {type(exc).__name__}: {exc}",
        )
    finally:
        for leftover in root.glob("*"):
            leftover.unlink(missing_ok=True)
        root.rmdir()
    unmeasurable, defects, evidence = judge(result)
    if unmeasurable:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=_SITE,
            detail="; ".join(unmeasurable),
        )
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=_SITE,
            evidence=f"{len(defects)} hot-path defect(s). " + " | ".join(evidence),
            detail="; ".join(defects),
        )
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=" | ".join(evidence)
        + ". WHAT THIS DOES NOT PROVE: isolation against a sink that burns CPU "
        "in Python (the GIL would serialise it; §11 item 6's failure mode is I/O), "
        "WAL fsync durability (check_plane1_wal), or who may write "
        "(check_plane1_sole_writer)",
    )


# Deliberately duplicated across every checks/check_*.py (§4.2).
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
