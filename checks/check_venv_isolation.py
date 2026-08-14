#!/usr/bin/env python3
"""Gate: the runtime/dev venv split cannot silently re-merge, and a
mid-mutation venv is measured as unavailable, never as pass or fail.

ARC 030 / Stage 2 A2 ("isolation, enforced"). Extends CRUCIBLE-DEPSPLIT
(`.venv` / `.venv-dev`, `docs/CHECK-DEBT.md` D3.111, RESOLVED) with the two
properties that arc's own split did not gate:

1. **The split still exists.** D3.111 was `.venv-dev`'s calendar-generator
   dependency tree (`pandas_market_calendars`, `exchange_calendars`,
   `korean_lunar_calendar`, `pyluach`) bleeding into the shared runtime venv
   and silently bumping `tzdata` outside `ib_async`'s own declared range.
   ARC CRUCIBLE-DEPSPLIT fixed the INSTANCE by splitting the venv. Nothing
   gates the split ITSELF staying split — a future `uv pip install` run
   against the wrong `--python` target, or `.venv-dev` being symlinked into
   `.venv` to "save space", would re-create D3.111 by a different mechanism
   and nothing on this tree would notice until the next accidental collision.
2. **`.venv`'s installed-package state is measured only when it is a STABLE
   subject.** ARC 030's own brief: "CRUCIBLE-DEPSPLIT rebuilt `.venv` from
   scratch while other arcs could run." A gate reading `.venv` while another
   process holds `nixverify.venv_lock`'s mutation lock is reading a state
   that may not exist by the time the verdict is printed — CANNOT_MEASURE,
   never a verdict (`nix_check_contract.md` §17).

## The hazard, proven directly

`scripts/tests/test_check_venv_isolation.py::
test_a_HELD_lock_makes_this_gate_report_CANNOT_MEASURE_not_a_false_verdict`
holds the lock from the test process itself — exactly as a concurrent
`check_venv`/`check_python_deps` repair, or a human running `install.sh` by
hand, would — and shows this gate refuses to report PASS or FAIL against
`.venv` while it is held. The same test file's
`test_a_RE_MERGED_split_is_caught_by_a_dev_only_marker_leaking_into_runtime`
plants one of D3.111's own four dev-only package names into a SCRATCH copy
of a runtime venv's `importlib.metadata` view and shows the marker arm
reddens naming it, then restores byte-identical.

Real, already-measured instance of the CLASS of hazard arm 2 closes,
independent of anything planted for this arc: reconciling `main` through
arc-026..arc-029 in this arc's own Phase 1 surfaced `check_price_ring`
FAILING against `.venv-dev/lib/python3.14/site-packages/numpy/...` at every
pre-CRUCIBLE-DEPSPLIT commit, purely because `.venv-dev` (untracked,
persists across `git checkout`) existed on disk before the code excluding it
from the scan did. That was a code/environment skew across TIME (checkout
vs. build); this gate's lock-awareness closes the same skew across
CONCURRENT PROCESSES on one checkout — see `scripts/nixverify/venv_lock.py`
for the full argument.

## §7.12 — what would make this PASS while measuring nothing?

1. **The DEV_ONLY_MARKERS list is emptied.** GUARDED: `run` asserts it is
   non-empty before querying, CANNOT_MEASURE otherwise — same posture as
   `check_synthetic_stop_only`'s ban-tuple guard.
2. **Neither venv exists.** Both directories absent is the state a fresh
   checkout starts in, not a re-merge — GUARDED: reported CANNOT_MEASURE
   (`check_venv` owns "does `.venv` exist at all"), never PASS-by-vacuity.
3. **The marker query silently returns nothing instead of failing loud.**
   GUARDED: `_installed` returns `None` (distinct from `[]`) on any query
   failure, and `run` reports CANNOT_MEASURE for `None`, mirroring
   `check_python_deps.installed_versions`'s same distinction.
4. **A re-merge happens through a NEW dev-only package this list does not
   name.** UNGUARDED — this is the same "the venn diagram of things checked
   vs. things that exist" gap named in `checks/requirements-runtime.txt`'s
   own comment (`pandas`, `toolz`, `python-dateutil`, `six`, `tzdata` are
   called "exclusive transitives" there but deliberately excluded from
   `DEV_ONLY_MARKERS` here as too common elsewhere to use as a hard marker
   without risking a false positive the day something legitimate needs one).
   Named, not fixed — the four hard markers are D3.111's own exact
   fingerprint, not a general "nothing but runtime packages" prover.
"""

# pylint: disable=duplicate-code
# R0801: this module's declaration preamble necessarily duplicates every
# other checks/check_*.py's — see check_untracked_attribution.py's identical
# note; the contract (§4.4) requires it be readable by AST without importing.
from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.venv_lock import probe_lock

# NOT re-enabled: `_installed()` below necessarily pairs with
# `check_python_deps.installed_versions`'s identical query-subprocess-and-
# distinguish-None-from-[]-shape (§4.1, Task 9 review Finding 2, applied
# here for the same reason) — same class of unavoidable duplication as the
# declaration preamble, just further down the file.

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Read-only: queries `.venv` via a subprocess, same pattern as
#: `check_python_deps`/`check_python_transitive_deps`. Claims "venv" because
#: it spawns a subprocess reading it, not because it mutates anything.
RESOURCES: tuple[str, ...] = ("venv",)
TIME_BOUND = False
#: NON-CORRECTABLE: there is no safe automatic repair for "the split
#: re-merged" (uninstalling packages from a shared venv on Chris's behalf is
#: exactly the class of unattended action CLAUDE.md directive 7 forbids) or
#: for "the lock is held" (waiting it out is the only correct response, and
#: this gate's OWN JOB is to say so, not to force through it).
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a re-merged split needs a human decision about which install put the "
    "dev-only package there and whether the runtime venv or the pin set is "
    "wrong; a held lock needs nothing but re-measurement once it releases — "
    "neither has a safe unattended repair"
)
SUBJECTS: tuple[str, ...] = ()

NAME = "check_venv_isolation"

#: D3.111's own four names, and only those. See §7.12 condition 4 for why
#: the wider "exclusive transitives" list is deliberately NOT here.
DEV_ONLY_MARKERS: frozenset[str] = frozenset(
    {
        "pandas_market_calendars",
        "exchange_calendars",
        "korean_lunar_calendar",
        "pyluach",
    }
)

_QUERY = (
    "import json,importlib.metadata as m;"
    "print(json.dumps(sorted({d.metadata['Name'].lower() "
    "for d in m.distributions() if d.metadata['Name']})))"
)


def _installed(python: Path) -> list[str] | None:
    """Every distribution name installed under `python`'s venv, or `None`.

    `None` is a query failure (timeout, exec failure, unparseable output),
    distinct from `[]` (queried fine, nothing installed) — the same
    distinction `check_python_deps.installed_versions` makes, for the same
    reason: collapsing them would let a transient query failure read as "no
    packages, therefore no re-merge", which is a false PASS.
    """
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(python), "-c", _QUERY],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except OSError, subprocess.SubprocessError:
        return None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def collapsed(runtime: Path, dev: Path) -> bool:
    """True when `.venv` and `.venv-dev` name the SAME real directory.

    Catches a symlink, a bind mount, or one being pointed at the other —
    any mechanism that makes them stop being two independent installations,
    not just the literal `.venv-dev` directory being deleted (that is
    "not built yet", a legitimate state `run` handles separately, not a
    collapse).
    """
    if not (runtime.is_dir() and dev.is_dir()):
        return False
    try:
        return runtime.resolve() == dev.resolve()
    except OSError:
        return False


def leaked_markers(installed: list[str]) -> list[str]:
    """Which DEV_ONLY_MARKERS appear in a package list. Pure, hence testable."""
    present = set(installed)
    return sorted(DEV_ONLY_MARKERS & present)


def run(  # pylint: disable=unused-argument,too-many-return-statements
    mode: Mode, ctx: Context
) -> CheckResult:
    """Prove the split still exists and `.venv` is a stable measurement subject."""
    if not DEV_ONLY_MARKERS:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail="DEV_ONLY_MARKERS is empty — a data-driven gate with no "
            "data scans everything and finds nothing (§7.12 condition 1)",
        )

    runtime = ctx.nix_home / ".venv"
    dev = ctx.nix_home / ".venv-dev"
    runtime_python = runtime / "bin" / "python3"

    # ARC 030 / Stage 2 A2: is `.venv` mid-mutation RIGHT NOW? Checked first,
    # before any other measurement — every arm below reads `.venv`'s current
    # state, and none of them are trustworthy against a moving target.
    held, lock_detail = probe_lock(ctx.nix_home)
    if held:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=str(runtime),
            detail=f"the venv-mutation lock is held by another process "
            f"({lock_detail}) — `.venv`'s installed-package state is a "
            "moving target; re-measure once it releases (§17)",
        )

    if collapsed(runtime, dev):
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=str(runtime),
            evidence=f"{runtime} and {dev} resolve to the same real "
            "directory — the runtime/dev split has re-merged",
            detail="D3.111's mechanism can recur through this path even "
            "with the split's history intact: separate the two, or "
            "rebuild whichever one was pointed at the other",
        )

    if not runtime_python.is_file():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"no venv interpreter at {runtime_python} — check_venv "
            "owns whether `.venv` exists at all",
        )

    installed = _installed(runtime_python)
    if installed is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"could not query installed packages via {runtime_python} (§4.1)",
        )

    leaked = leaked_markers(installed)
    if leaked:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=", ".join(leaked),
            evidence=f"{len(leaked)} of {len(DEV_ONLY_MARKERS)} dev-only "
            f"marker(s) present in the RUNTIME venv: {', '.join(leaked)}",
            detail="the calendar-generator dependency tree (D3.111's own "
            "fingerprint) has leaked into `.venv` — the runtime/dev split "
            "has re-merged in substance even though the two directories "
            "are still physically separate",
        )

    dev_status = "present" if dev.is_dir() else "not built (legitimate)"
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=f"{runtime} and {dev} ({dev_status}) remain separate; "
        f"0 of {len(DEV_ONLY_MARKERS)} dev-only marker(s) present in the "
        f"runtime venv's {len(installed)} installed package(s)",
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
