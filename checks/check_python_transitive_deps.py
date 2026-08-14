#!/usr/bin/env python3
"""Verify no INSTALLED transitive dependency violates another installed
package's own declared version range.

ARC CRUCIBLE-DEPSPLIT / docs/CHECK-DEBT.md D3.111. `check_python_deps.py`
compares the venv against `checks/pinned_deps.json`'s THREE declared
top-level pins, exactly, and nothing else — it has never looked at what those
three (or anything else installed) themselves declare needing. D3.111 was
exactly that blind spot, measured directly: installing the Crucible calendar
generator's dev dependency into the (then-single, now-split) runtime venv
silently bumped `tzdata` to a version outside `ib_async`'s own declared
`tzdata<2026.0,>=2025.2` requirement, and nothing on this tree noticed —
`ib_async` still imported, `check_python_deps` still PASSed, because neither
one's subject is "does everyone's own stated requirement still hold".

This check's subject is that gap: for every distribution installed in the
venv, read ITS OWN declared requirements (`Requires-Dist`, the same metadata
`pip`/`uv` resolve against) and check whether the version actually installed
for each still satisfies them. It never repairs (CORRECTABLE = False, below)
— there is no single safe automatic repair for "some already-pinned package's
own dependency drifted", because the fix might be pinning the drifted
package, widening the declaring package's own requirement, or a human
decision that the drift is fine; automating any of those here would be this
check quietly making that call for D3.111's own live-broker-adjacent
packages, which is exactly what the arc's hard limits forbid.

A violation may be reported as a tracked, justified exception instead of a
hard FAIL — see `load_exceptions` / `checks/transitive_deps_exceptions.json`
— but an untracked violation is always FAIL_NEEDS_OPERATOR. A blanket
skip/ignore is never legal here (arc hard limit); every exception is a named,
matched (consumer, dependency, declared_range) triple with its own
justification, so a DIFFERENT future drift of the same edge (the declaring
package raising or lowering its own requirement) is NOT silently covered by a
stale exception written against the old range.
"""

# pylint: disable=duplicate-code
# R0801: this module's declaration preamble (PRIVILEGE/DEPENDS_ON/RESOURCES/…)
# necessarily duplicates every other checks/check_*.py's — see
# check_canonical_tree.py's identical note. The contract (§4.4) requires each
# literal be readable by AST without importing the check; a shared base module
# would be invisible to that reader.
from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.venv_lock import probe_lock

PRIVILEGE = "user"
INTERACTIVE = False
# Never mutates the venv — inspection only. §4/§8's DISRUPTIVE test ("does
# this check ever change something order-flow-adjacent") is trivially false:
# CORRECTABLE = False below means repair() does not exist.
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Same subject as check_python_deps (the venv's installed tree) but this
#: check does not need pin-repair to have run first — it reports on whatever
#: is ACTUALLY installed, repaired or not. check_venv only: the venv must
#: exist to have anything to inspect.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Read-only metadata query via the venv's own interpreter (importlib.metadata
#: in a subprocess, same pattern as check_python_deps) — no network, no
#: mutation. Still claims "venv" because it spawns a subprocess reading it;
#: two checks reading concurrently is fine in principle but the registry has
#: no parallel blocks today (checks/registry.json), and claiming it keeps
#: this check honest about its subject rather than under-declaring for a
#: parallelism this repo does not currently have.
RESOURCES: tuple[str, ...] = ("venv",)
#: A single subprocess querying local package metadata; milliseconds.
TIME_BOUND = False
#: NON-CORRECTABLE by design — see module docstring's third paragraph.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a transitive-range violation has no single safe automatic repair: the "
    "right fix might be pinning the drifted package, raising or lowering the "
    "declaring package's own requirement, or a human judgment call that the "
    "drift is acceptable (tracked as an exception). ib_async is on the live "
    "broker path (CLAUDE.md, this arc's FACTS) — this check reports the "
    "condition and names the site; it does not choose a fix on Chris's "
    "behalf."
)
#: This check's subjects: the exceptions ledger it reads (the pins file is
#: NOT restated — evaluate() re-derives nothing from pinned_deps.json, see
#: load_exceptions) and this arc's own checkpoint file — named here rather
#: than left uncovered, same as CALENDAR-INFRA named its checkpoint under
#: check_crucible_calendar.py's SUBJECTS (check_artifact_gate_coverage's
#: ratchet governs every tracked `.py`/`.json` artifact; a checkpoint that
#: is not literally validated by this check still needs a name, or it is an
#: uncovered artifact with no check declaring it, not merely a
#: session-scoped scratch file).
SUBJECTS: tuple[str, ...] = (
    "checks/transitive_deps_exceptions.json",
    "sessions/crucible_depsplit_checkpoint.json",
)

NAME = "check_python_transitive_deps"

# Executed inside the VENV's own interpreter via subprocess (never imported
# here — same reason check_python_deps.py never imports what it checks,
# §9.4: a missing/broken target package must not be able to break the check
# meant to report on it). `pip._vendor.packaging` is used rather than a
# hand-rolled PEP 440/508 parser: pip vends it into every venv `python -m
# venv` creates (it is pip's own dependency-resolution machinery), so it is
# available wherever there is a venv to inspect at all, without adding a new
# top-level dependency this check would then have to be exempted from
# checking. `{"extra": ""}` asks each requirement's marker to evaluate as a
# DEFAULT (no-extra) install — the same set `pip install <pkg>` (no extras)
# actually pulls in — while still resolving python_version/sys_platform/etc.
# markers against this real interpreter (verified: Marker.evaluate() fills
# every key it is not given from the live environment).
_QUERY = r"""
import json, importlib.metadata as m
from pip._vendor.packaging.requirements import Requirement, InvalidRequirement
from pip._vendor.packaging.version import Version, InvalidVersion

installed = {}
for d in m.distributions():
    n = d.metadata["Name"]
    if n:
        installed[n.lower()] = d.version

violations = []
for dist in m.distributions():
    consumer = dist.metadata["Name"]
    if not consumer:
        continue
    for req_str in dist.requires or []:
        try:
            req = Requirement(req_str)
        except InvalidRequirement:
            continue
        if req.marker is not None:
            try:
                if not req.marker.evaluate({"extra": ""}):
                    continue
            except Exception:
                continue
        if not req.specifier:
            continue
        actual = installed.get(req.name.lower())
        if actual is None:
            continue
        try:
            actual_v = Version(actual)
        except InvalidVersion:
            continue
        if not req.specifier.contains(actual_v, prereleases=True):
            violations.append({
                "consumer": consumer,
                "consumer_version": dist.version,
                "dependency": req.name.lower(),
                "declared_range": str(req.specifier),
                "installed": actual,
            })

violations.sort(key=lambda v: (v["consumer"].lower(), v["dependency"]))
print(json.dumps(violations))
"""


def query_violations(venv_python: Path) -> list[dict[str, str]] | None:
    """Ask the venv's own interpreter for its transitive-range violations.

    Returns `None` on any failure to query — distinct from `[]`, which means
    "queried fine, nothing violates" (mirrors check_python_deps.py's
    `installed_versions`, §4.1, Task 9 review Finding 2 there: collapsing the
    two would let a transient query failure report a false PASS).
    """
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(venv_python), "-c", _QUERY],
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
    if not isinstance(parsed, list):
        return None
    return parsed


def load_exceptions(checks_dir: Path) -> list[dict[str, str]]:
    """Read the tracked-exception ledger. Empty list if the file is absent.

    Absent, not CANNOT_MEASURE: an empty ledger is a legitimate, common state
    (this arc ships it empty — D3.111 was RESOLVED, not reported — see
    RESULTS.md) and the file's own existence is not this check's subject; a
    missing ledger means "no exceptions declared", not "unmeasurable".
    """
    path = checks_dir / "transitive_deps_exceptions.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    exceptions = payload.get("exceptions", [])
    if not isinstance(exceptions, list):
        raise TypeError(f"{path}: 'exceptions' must be a list")
    return exceptions


def _violation_key(v: dict[str, str]) -> tuple[str, str, str]:
    return (v["consumer"].lower(), v["dependency"].lower(), v["declared_range"])


def evaluate(
    violations: list[dict[str, str]], exceptions: list[dict[str, str]]
) -> CheckResult:
    """Compare violations against tracked exceptions. Pure — hence testable.

    Matched on the (consumer, dependency, declared_range) TRIPLE, not just
    (consumer, dependency): if the declaring package's own requirement
    changes (a bump either widens or narrows it), a stale exception written
    against the OLD range must not silently cover a DIFFERENT new violation
    — hard limit, no blanket skip. A changed range simply fails as unexcepted
    until the exception is rewritten to match it.
    """
    exception_keys = {
        (
            str(e.get("consumer", "")).lower(),
            str(e.get("dependency", "")).lower(),
            str(e.get("declared_range", "")),
        )
        for e in exceptions
    }
    unexcepted = [v for v in violations if _violation_key(v) not in exception_keys]
    guarded = [v for v in violations if _violation_key(v) in exception_keys]

    def _render(vs: list[dict[str, str]]) -> str:
        return "; ".join(
            f"{v['consumer']} {v['consumer_version']} requires "
            f"{v['dependency']}{v['declared_range']}, installed {v['installed']}"
            for v in vs
        )

    if unexcepted:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=", ".join(sorted({v["dependency"] for v in unexcepted})),
            evidence=f"{len(unexcepted)} unreported transitive-range "
            f"violation(s) of {len(violations)} total",
            detail=_render(unexcepted),
        )
    if guarded:
        owners = sorted({str(e.get("arc", "")) for e in exceptions})
        return CheckResult(
            name=NAME,
            status=Status.GUARDED,
            site=", ".join(sorted({v["dependency"] for v in guarded})),
            evidence=f"{len(guarded)} tracked-exception transitive-range "
            f"violation(s), all matched to a named exception",
            detail=_render(guarded),
            guard_owner=owners[0] if len(owners) == 1 else "; ".join(owners),
        )
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence="0 transitive-range violations across the installed tree "
        "(0 exceptions active)"
        if not exceptions
        else f"0 transitive-range violations across the installed tree "
        f"({len(exceptions)} exception(s) on file, none currently matched)",
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure the venv's installed tree against everyone's own ranges."""
    checks_dir = Path(__file__).resolve().parent
    venv_python = ctx.nix_home / ".venv" / "bin" / "python3"
    if not venv_python.is_file():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"no venv interpreter at {venv_python} — check_venv owns this",
        )
    violations = query_violations(venv_python)
    if violations is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"could not query the installed tree via {venv_python}",
        )
    exceptions = load_exceptions(checks_dir)
    result = evaluate(violations, exceptions)
    # ARC 030 / Stage 2 A2: this gate is NON-CORRECTABLE and read-only, but a
    # violation reported while `.venv` is mid-mutation is still a verdict
    # about a moving target — a package briefly absent or half-installed
    # between `rm` and reinstall can present a transient "range violated"
    # shape that has nothing to do with a real drift (§17).
    if result.status is not Status.PASS:
        held, lock_detail = probe_lock(ctx.nix_home)
        if held:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=result.site,
                detail=f"{result.detail}; AND the venv-mutation lock is "
                f"held by another process ({lock_detail}) — this may be the "
                "in-progress mutation, not a real transitive-range "
                "violation; re-measure once it releases",
            )
    return result


# Deliberately duplicated across every checks/check_*.py — see
# check_canonical_tree.py's identical note (§4.2 independent-runnability).
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
