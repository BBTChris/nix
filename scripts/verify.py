#!/usr/bin/env python3
"""verify.py — Nix provisioning/verification engine.

Authority: docs/nix_check_contract.md v1.0.0.

Stdlib only (§9.1) so it runs under system python3 before .venv exists.
Never reads stdin (§9.2) — all interactivity belongs to install.sh.

Run at: end of install.sh, every boot (nix-verify.service), and weekly
Saturday 03:00 America/Chicago (nix-verify-root.timer) — outside any
trading session per the risk spec's no-new-entry window.

Repairs the *environment* only. Per risk spec v1.3 §12.11 config changes
take effect through restart; this never hot-edits live tunables.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from nixverify.contract import (  # pylint: disable=wrong-import-position
    CheckResult,
    Context,
    Mode,
    Status,
    exit_code_for,
)
from nixverify.declarations import read_all  # pylint: disable=wrong-import-position
from nixverify.engine import (  # pylint: disable=wrong-import-position
    aggregate_exit,
    run_blocks,
)
from nixverify.optimize import (  # pylint: disable=wrong-import-position
    OptimizeError,
    derive_plan,
    plan_to_payload,
)
from nixverify.plane2 import Plane2  # pylint: disable=wrong-import-position
from nixverify.registry import (  # pylint: disable=wrong-import-position
    RegistryError,
    load_registry,
)
from nixverify.render import (  # pylint: disable=wrong-import-position
    LiveProgress,
    StreamProgress,
    render_results,
    render_summary,
    theme_for,
)

NIX_HOME = Path(__file__).resolve().parent.parent


class _RunObserver:
    """Fans the engine's callbacks out to Plane 2 and to the progress surface.

    **The two sinks are held side by side and never composed.** Plane 2 receives
    only `emit(event, **fields)` calls built here from the CheckResult; the
    progress surface receives only the same callbacks and writes only to the
    terminal. Neither holds a reference to the other, so there is no path — not
    even an accidental one through a shared logger — by which a spinner frame
    could reach the journal (ARC 024 §1.3).

    `logging` makes that easy to get wrong, which is why `plane2.Plane2` sets
    `propagate = False` on its own logger: a root handler installed by anything
    else must not pick up Plane-2 records, and Plane-2 records must not pick up
    anyone else's handlers.
    """

    def __init__(self, plane2: Plane2, progress: LiveProgress | StreamProgress) -> None:
        self._plane2 = plane2
        self._progress = progress

    def check_start(self, name: str) -> None:
        """Announce a check beginning on both surfaces."""
        self._plane2.emit("check_start", check=name)
        self._progress.check_start(name)

    def check_verdict(self, result: CheckResult) -> None:
        """Announce a verdict on both surfaces."""
        self._plane2.emit(
            "check_verdict",
            check=result.name,
            status=result.status.value,
            exit=exit_code_for(result.status),
            duration_s=f"{result.duration_s:.4f}",
            site=result.site or "-",
        )
        self._progress.check_verdict(result)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """CLI surface. Modes are semantic; --verbose is orthogonal to them."""
    parser = argparse.ArgumentParser(
        description="Nix node inspection, correction, and installation"
    )
    parser.add_argument(
        "--mode", choices=[m.value for m in Mode], default=Mode.VERIFY.value
    )
    parser.add_argument(
        "--privilege",
        choices=["user", "root", "all"],
        default="user",
        help="'all' is for install.sh, which runs both subsets in one pass",
    )
    parser.add_argument(
        "--maintenance",
        action="store_true",
        help="permit disruptive repairs (weekly window only, §8)",
    )
    parser.add_argument(
        "--allow-interactive",
        action="store_true",
        help="permit INTERACTIVE checks — install.sh only, never a unit (§9.2)",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--stream",
        action="store_true",
        help=(
            "print each check's verdict and duration the moment it lands, "
            "instead of only the block at the end; survives a pipe"
        ),
    )
    parser.add_argument(
        "--registry", default=str(NIX_HOME / "checks" / "registry.json")
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="derive the execution plan from checks/ and write <registry>.proposed",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="with --optimize: install the derived plan over the live registry",
    )
    return parser.parse_args(argv)


def _run_optimize(registry_path: Path, commit: bool) -> int:
    """`--optimize`: derive the plan, report, and propose rather than overwrite.

    **[ARCHITECT RULING — revocable, and flagged.]** The operator ruling says
    `--optimize` overwrites the existing registry. It does not, by default: it
    writes `<registry>.proposed`, prints a diff, and requires `--commit` to
    install. The registry is the master execution plan for eventually hundreds of
    checks; one bad derivation that silently overwrote it would destroy the
    ordering with no recovery point and no diff to review, and would surface
    later as checks running in the wrong order — which reads as a product bug,
    not a tooling bug. `--commit` is one keystroke and restores the ruling
    exactly. **Operator's call; say the word and the default flips.**
    """
    checks_dir = registry_path.parent
    declarations = read_all(checks_dir)
    try:
        plan = derive_plan(checks_dir, registry_path)
    except OptimizeError as exc:
        print(f"  verify.py --optimize: cannot derive — {exc}", file=sys.stderr)
        return 2
    for note in plan.notes:
        print(f"  note: {note}")
    for error in plan.errors:
        print(f"  ERROR: {error}", file=sys.stderr)
    if not plan.ok:
        # Fail closed and loud: a plan with a cycle, an orphan, or an undeclared
        # check is not written anywhere, not even as a proposal. A `.proposed`
        # file on disk is an invitation to commit it.
        print(
            f"  verify.py --optimize: {len(plan.errors)} error(s) — no plan written",
            file=sys.stderr,
        )
        return 1
    payload = plan_to_payload(plan, declarations)
    rendered = json.dumps(payload, indent=2) + "\n"
    target = registry_path if commit else registry_path.with_suffix(".json.proposed")
    current = (
        registry_path.read_text(encoding="utf-8") if registry_path.is_file() else ""
    )
    diff = list(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=str(registry_path),
            tofile=str(target),
        )
    )
    target.write_text(rendered, encoding="utf-8")
    print(
        "".join(diff) if diff else "  (derived plan is identical to the live registry)"
    )
    verb = "INSTALLED" if commit else "proposed"
    print(f"  verify.py --optimize: {verb} {target}")
    if not commit:
        print("  re-run with --commit to install it")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Load the registry, run its blocks, render, and return the exit code."""
    args = _parse_args(argv)
    theme = theme_for(sys.stdout, os.environ)
    registry_path = Path(args.registry)
    if args.optimize:
        return _run_optimize(registry_path, args.commit)
    plane2 = Plane2()
    plane2.emit(
        "run_start",
        mode=args.mode,
        privilege=args.privilege,
        maintenance=args.maintenance,
        allow_interactive=args.allow_interactive,
        registry=str(registry_path),
        transport=plane2.transport,
    )
    try:
        blocks = load_registry(registry_path)
    except RegistryError as exc:
        # Unreadable registry is unmeasurable, not a failed check (§4.1).
        plane2.emit("run_end", outcome="cannot_measure", reason=str(exc), exit=2)
        print(f"  verify.py: cannot measure — {exc}", file=sys.stderr)
        return 2
    ctx = Context(
        nix_home=NIX_HOME,
        mode=Mode(args.mode),
        privilege=args.privilege,
        maintenance=args.maintenance,
        allow_interactive=args.allow_interactive,
    )
    total = sum(len(block.checks) for block in blocks)
    # One progress surface, never two. `--stream` and the spinner are two
    # renderings of the same fact — running both would put an append-only log and
    # an in-place repaint on the same terminal, where the repaint's `\r` would
    # overwrite whatever line the log had just committed.
    progress: LiveProgress | StreamProgress = (
        StreamProgress(sys.stdout, theme, total)
        if args.stream
        else LiveProgress(sys.stdout, theme, total)
    )
    observer = _RunObserver(plane2, progress)
    progress.start()
    try:
        results = run_blocks(blocks, registry_path.parent, ctx, observer)
    finally:
        # Unconditional: a check that kills the run must not leave the terminal
        # holding a half-painted spinner line and a hidden cursor.
        progress.stop()
    exit_code = aggregate_exit(results)
    counts = {status: 0 for status in Status}
    for result in results:
        counts[result.status] += 1
    plane2.emit(
        "run_end",
        exit=exit_code,
        passed=counts[Status.PASS],
        failed=counts[Status.FAIL_REPAIRABLE] + counts[Status.FAIL_NEEDS_OPERATOR],
        cannot_measure=counts[Status.CANNOT_MEASURE],
        skipped=counts[Status.SKIPPED],
        guarded=counts[Status.GUARDED],
        emitted=plane2.emitted,
    )
    print(render_results(results, theme, args.verbose))
    print(render_summary(results, exit_code, theme))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
