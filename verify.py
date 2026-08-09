#!/usr/bin/env python3
"""
verify.py — idempotent, plugin-based inspection/remediation engine.
Per elements_v2.md §1.3.

Modes: --summary (default), --verbose, --repair
Plugins: every checks/check_*.py exposing a run(mode) -> CheckResult.
Run at: end of install.sh, every boot (systemd service), weekly Saturday
03:00 America/Chicago (systemd timer) — confirmed outside any trading
session (risk spec: no new entry from 30min before Friday close through
Sunday session open; Saturday has no session at all).

verify.py repairs the *environment* only. Per v1.3 §12.11: config changes
take effect only through restart — this never hot-edits live tunables.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import sys
from pathlib import Path

NIX_HOME = Path(__file__).resolve().parent
CHECKS_DIR = NIX_HOME / "checks"


@dataclasses.dataclass
class CheckResult:
    """Outcome of one plugin's run() call."""

    name: str
    ok: bool
    detail: str = ""
    repaired: bool = False


def load_plugins():
    """Import every checks/check_*.py exposing a run() callable."""
    plugins = []
    if not CHECKS_DIR.is_dir():
        return plugins
    for path in sorted(CHECKS_DIR.glob("check_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "run"):
            plugins.append((path.stem, mod))
    return plugins


def run_plugins(plugins, repair: bool) -> list[CheckResult]:
    """Run each plugin, isolating a broken plugin from crashing the whole pass."""
    results: list[CheckResult] = []
    for name, mod in plugins:
        try:
            result = mod.run(repair=repair)
        except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
            # A single misbehaving plugin must not abort the rest of the run —
            # it's reported as a failed check instead, same as any other FAIL.
            result = CheckResult(name=name, ok=False, detail=f"plugin raised: {exc!r}")
        results.append(result)
    return results


def print_results(results: list[CheckResult], verbose: bool) -> None:
    """Print one line per check result."""
    for result in results:
        status = "OK" if result.ok else "FAIL"
        line = f"[{status}] {result.name}"
        if verbose or not result.ok:
            if result.detail:
                line += f" — {result.detail}"
            if result.repaired:
                line += " (repaired)"
        print(line)


def main() -> int:
    """Entry point: load plugins, run them, report, exit non-zero on any failure."""
    parser = argparse.ArgumentParser(
        description="verify.py — Nix node state inspection/remediation"
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--repair", action="store_true", help="Verify+Repair mode")
    args = parser.parse_args()

    plugins = load_plugins()
    if not plugins:
        print(
            "verify.py: no check_*.py plugins found under checks/ — nothing to verify yet "
            "(expected pre-R1; plugins land as each subsystem is built)"
        )
        return 0

    results = run_plugins(plugins, repair=args.repair)
    print_results(results, verbose=args.verbose)

    failed = [r for r in results if not r.ok]
    print(f"verify.py: {len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
