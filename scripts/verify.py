#!/usr/bin/env python3
"""verify.py — Nix provisioning/verification engine.

Authority: docs/VERIFY-AND-CHECKS.md v1.0.0.

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
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from nixverify.contract import Context, Mode  # pylint: disable=wrong-import-position
from nixverify.engine import (  # pylint: disable=wrong-import-position
    aggregate_exit,
    run_blocks,
)
from nixverify.manifest import (  # pylint: disable=wrong-import-position
    ManifestError,
    load_manifest,
)
from nixverify.render import (  # pylint: disable=wrong-import-position
    render_results,
    render_summary,
    theme_for,
)

NIX_HOME = Path(__file__).resolve().parent.parent


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
        "--manifest", default=str(NIX_HOME / "checks" / "verify_manifest.json")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Load the manifest, run its blocks, render, and return the exit code."""
    args = _parse_args(argv)
    theme = theme_for(sys.stdout, os.environ)
    manifest_path = Path(args.manifest)
    try:
        blocks = load_manifest(manifest_path)
    except ManifestError as exc:
        # Unreadable manifest is unmeasurable, not a failed check (§4.1).
        print(f"  verify.py: cannot measure — {exc}", file=sys.stderr)
        return 2
    ctx = Context(
        nix_home=NIX_HOME,
        mode=Mode(args.mode),
        privilege=args.privilege,
        maintenance=args.maintenance,
        allow_interactive=args.allow_interactive,
    )
    results = run_blocks(blocks, manifest_path.parent, ctx)
    exit_code = aggregate_exit(results)
    print(render_results(results, theme, args.verbose))
    print(render_summary(results, exit_code, theme))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
