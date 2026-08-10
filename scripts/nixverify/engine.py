"""Block execution, gating, and aggregation (§6, §8)."""

from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


def _execute(checks_dir: Path, name: str, ctx: Context) -> CheckResult:
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


def _run_block(block: Block, checks_dir: Path, ctx: Context) -> list[CheckResult]:
    """Execute one block. Parallel blocks still report in manifest order."""
    if not block.parallel or len(block.checks) == 1:
        return [_execute(checks_dir, name, ctx) for name in block.checks]
    with ThreadPoolExecutor(max_workers=len(block.checks)) as pool:
        futures = [
            pool.submit(_execute, checks_dir, name, ctx) for name in block.checks
        ]
        return [future.result() for future in futures]


def run_blocks(
    blocks: tuple[Block, ...], checks_dir: Path, ctx: Context
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
        block_results = _run_block(block, checks_dir, ctx)
        results.extend(block_results)
        if block.on_fail == "halt" and any(r.status in FAILURES for r in block_results):
            halted_by = block.name
    return results


def aggregate_exit(results: list[CheckResult]) -> int:
    """§4.2: failure dominates cannot-measure, which dominates pass."""
    if any(r.status in FAILURES for r in results):
        return 1
    if any(r.status in (Status.CANNOT_MEASURE, Status.SKIPPED) for r in results):
        return 2
    return 0
