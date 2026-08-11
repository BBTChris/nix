"""Block execution, gating, and aggregation (§6, §8)."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from nixverify.contract import (
    FAILURES,
    CheckResult,
    Context,
    Mode,
    Status,
    validate_result,
)
from nixverify.loader import LoadedCheck, load_check
from nixverify.manifest import Block


def _skip(name: str, reason: str) -> CheckResult:
    """A check that did not run. Never reported as a pass (§4.2)."""
    return CheckResult(name=name, status=Status.SKIPPED, detail=reason)


def _gate(loaded: LoadedCheck, ctx: Context) -> str:
    """Return a skip reason, or '' if this check may run in this context.

    DISRUPTIVE is deliberately not gated here (Task 9 review, Finding 1):
    skipping loses the *report* along with the repair, so a boot outside
    the maintenance window would never learn pins had drifted until the
    weekly run. `_execute` downgrades a disruptive check's mode instead —
    it still runs, still reports, only the repair is withheld (§8).
    """
    if ctx.privilege not in ("all", loaded.privilege):
        return f"privilege: needs {loaded.privilege}, run is {ctx.privilege}"
    if loaded.interactive and not ctx.allow_interactive:
        return "interactive: runnable only from install.sh"
    return ""


_WITHHELD_NOTE = (
    "disruptive repair withheld outside maintenance window — inspected only (§8)"
)


class Observer(Protocol):
    """What the engine tells an onlooker as it goes.

    Two implementations exist: the Plane-2 emitter (`verify.py`) and the
    progress surface (`render.LiveProgress`). They are deliberately separate
    objects with no shared state — §1.3 of the ARC 024 ruling requires that
    presentation can never enter the journal, and the cheapest way to guarantee
    that is for the two sinks never to touch.

    **Called from worker threads** when a block is parallel, so an implementation
    must be safe to re-enter. Both shipped implementations serialise on a lock.
    """

    def check_start(self, name: str) -> None:
        """A check is about to run."""

    def check_verdict(self, result: CheckResult) -> None:
        """A check has returned; `result.duration_s` is stamped."""


def _timed(fn: Callable[[], CheckResult]) -> CheckResult:
    """Run `fn`, stamping wall-clock onto whatever CheckResult comes back.

    `perf_counter` rather than wall time: this number is reported, and a clock
    step (NTP, DST) must not be able to produce a negative duration in the
    journal. It is never an input to a verdict.
    """
    started = time.perf_counter()
    result = fn()
    result.duration_s = round(time.perf_counter() - started, 4)
    return result


def _execute(
    checks_dir: Path, name: str, ctx: Context, observer: Observer | None = None
) -> CheckResult:
    """Run one check with every failure path captured, timed, and announced."""
    if observer is not None:
        observer.check_start(name)
    result = _timed(lambda: _execute_inner(checks_dir, name, ctx))
    if observer is not None:
        observer.check_verdict(result)
    return result


def _execute_inner(checks_dir: Path, name: str, ctx: Context) -> CheckResult:
    """Run one check with every failure path captured."""
    loaded = load_check(checks_dir, name)
    if loaded.load_error:
        return CheckResult(
            name=name, status=Status.CANNOT_MEASURE, detail=loaded.load_error
        )
    reason = _gate(loaded, ctx)
    if reason:
        return _skip(name, reason)
    if loaded.run is None:
        return CheckResult(
            name=name,
            status=Status.CANNOT_MEASURE,
            detail="loaded check has no run callable",
        )
    withheld = (
        loaded.disruptive and ctx.mode.rank > Mode.VERIFY.rank and not ctx.maintenance
    )
    run_ctx = dataclasses.replace(ctx, mode=Mode.VERIFY) if withheld else ctx
    try:
        result = loaded.run(run_ctx.mode, run_ctx)
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
        return CheckResult(
            name=name, status=Status.CANNOT_MEASURE, detail=f"check raised: {exc!r}"
        )
    if not isinstance(result, CheckResult):
        return CheckResult(
            name=name,
            status=Status.CANNOT_MEASURE,
            detail=f"check returned {type(result).__name__}, not CheckResult",
        )
    # Task 9 second review, Finding B: only note the withheld repair on a
    # status the repair would actually have acted on. A PASS never reached
    # the repair branch in the first place — noting it there would read as
    # something held back when nothing was wrong.
    if withheld and result.status in FAILURES:
        result.detail = (
            f"{result.detail}; {_WITHHELD_NOTE}" if result.detail else _WITHHELD_NOTE
        )
    result.name = name
    return validate_result(result)


def _run_block(
    block: Block, checks_dir: Path, ctx: Context, observer: Observer | None = None
) -> list[CheckResult]:
    """Execute one block. Parallel blocks still report in manifest order."""
    if not block.parallel or len(block.checks) == 1:
        return [_execute(checks_dir, name, ctx, observer) for name in block.checks]
    with ThreadPoolExecutor(max_workers=len(block.checks)) as pool:
        futures = [
            pool.submit(_execute, checks_dir, name, ctx, observer)
            for name in block.checks
        ]
        return [future.result() for future in futures]


def run_blocks(
    blocks: tuple[Block, ...],
    checks_dir: Path,
    ctx: Context,
    observer: Observer | None = None,
) -> list[CheckResult]:
    """Execute blocks in order, honouring on_fail policy."""
    results: list[CheckResult] = []
    halted_by: str = ""
    for block in blocks:
        if halted_by:
            results.extend(
                _skip(name, f"halted by earlier block {halted_by!r}")
                for name in block.checks
            )
            continue
        block_results = _run_block(block, checks_dir, ctx, observer)
        results.extend(block_results)
        if block.on_fail == "halt" and any(r.status in FAILURES for r in block_results):
            halted_by = block.name
    return results


def aggregate_exit(results: list[CheckResult]) -> int:
    """§4.2 as amended: FAIL > CANNOT-MEASURE > GUARDED > PASS.

    **GUARDED ranks BELOW cannot-measure, and the order is the ruling.** A
    cannot-measure carries no information about its subject; a GUARDED verdict
    carries a measurement *and* the name of the arc that discharges it. Ranking
    the informative state above the uninformative one would let a run of
    known-red deferrals out-shout a gate that went blind, which is the direction
    `VERIFY-AND-CHECKS.md` §B.2's exit 2 exists to prevent.

    **Non-regression was measured twice, and the second measurement is the
    stronger one.** When the amendment landed no check emitted GUARDED, so the
    branch was unreachable and the aggregate was bit-identical to the
    pre-amendment function — verified by the full suite and by `verify.py`
    returning exit 1 with the same 10/1/1 triple. That claim then stopped being
    true in the same arc: `check_artifact_gate_coverage` is the first emitter,
    and the re-measured run reads
    `11 passed | 1 failed | 1 cannot measure | 0 skipped | 1 guarded — exit 1`.
    The aggregate is still 1, which is this dominance rule holding a **live**
    GUARDED below a live FAIL rather than an unexercised branch being harmless.
    """
    if any(r.status in FAILURES for r in results):
        return 1
    if any(r.status in (Status.CANNOT_MEASURE, Status.SKIPPED) for r in results):
        return 2
    if any(r.status is Status.GUARDED for r in results):
        return 3
    return 0
