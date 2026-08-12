#!/usr/bin/env python3
"""Verify venv packages match their pins.

§7: conformance-to-pin is repaired; a newer upstream release is advisory
only. An unattended run must never swap the library that places orders.

Never imports the packages it checks (§9.4) — it queries the venv's own
importlib.metadata in a subprocess, so a missing package cannot break the
check meant to install it.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
# §4/§8: repair() swaps a package — the vendor client that will place real
# orders. That is exactly §4's definition of disruptive. The engine (Task 9
# review, Finding 1) downgrades a disruptive check to inspection-only
# outside the maintenance window rather than skipping it, so this still
# reports drift at boot — it just never repairs there.
DISRUPTIVE = True

# --- ARC 024 orchestration declarations (read statically, never imported) ---
#: Nothing must run before this; the venv gate is a separate concern that this
#: check does not depend on for its own measurement (it resolves the venv path
#: itself and reports CANNOT_MEASURE if it is absent).
#: ARC 025: was `()`, and that was an UNDER-declaration measured by `--optimize`
#: once the floor gained a halt policy. This check's entire subject is the set of
#: packages installed INSIDE `.venv`; running it before `check_venv` has proven
#: the venv answers means reporting on the contents of something not yet shown to
#: exist. `RESOURCES` already claimed `venv` — the ordering edge was the half that
#: was missing, and the plan cannot infer it from a resource claim.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: The shared .venv, exclusively — pip mutates it, so no other check may run in
#: parallel with this one while also claiming it. This is the D3.12 hazard
#: written down as a claim instead of left in a docstring.
RESOURCES: tuple[str, ...] = ("venv", "network:pypi")
TIME_BOUND = False
CORRECTABLE = True
NON_CORRECTABLE_REASON = ""
#: The pins file this gate reads and the venv it compares against.
SUBJECTS: tuple[str, ...] = ("checks/pinned_deps.json",)

NAME = "check_python_deps"

_QUERY = (
    "import json,importlib.metadata as m;"
    "print(json.dumps({d.metadata['Name'].lower(): d.version"
    " for d in m.distributions() if d.metadata['Name']}))"
)

# This file's own token grammar: pinned_deps.json feeds both this check's
# `pip install` argv and install.sh's deliberately-unquoted `$PINS` shell
# expansion (§7). A name starting with `-` or a version containing a space
# or glob character would corrupt argv on one side and word-split/glob on
# the other — not attacker-reachable (it requires write access to a
# reviewed repo file), but it is the single feed for two consumers. The
# first character is restricted to alnum/underscore (never `-` or `.`) so a
# token cannot be mistaken for a flag by pip's argv parser or a hidden-file
# glob by the shell; interior `-`/`.` stay legal for names like
# "scikit-learn" and versions like "2.1.0".
_PIN_TOKEN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def load_pins(checks_dir: Path) -> dict[str, str]:
    """Read the pins file — never hardcode a version here (§2.4)."""
    path = checks_dir / "pinned_deps.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    pins: dict[str, str] = {}
    for name, version in payload["packages"].items():
        key = str(name).lower()
        if not _PIN_TOKEN.match(key) or not _PIN_TOKEN.match(str(version)):
            raise ValueError(f"{path}: malformed pin {name!r}=={version!r}")
        pins[key] = version
    return pins


def installed_versions(venv_python: Path) -> dict[str, str] | None:
    """Ask the venv what it has.

    Returns `None` if the venv could not answer at all (timeout, exec
    failure, unparseable output) — distinct from `{}`, which this function
    never actually returns, but which `evaluate()` would read as "queried
    fine, nothing installed". Collapsing the two would turn a transient
    failure into an unattended `pip install` repair against packages that
    may be installed correctly (§4.1, Task 9 review Finding 2).
    """
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(venv_python), "-c", _QUERY],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    # PEP 758 (Python 3.14): an unparenthesized multi-type except without an
    # `as` binding is valid syntax, not a Python-2 leftover — ruff-format's
    # canonical output. See the parenthesized form below (with `as exc`) for
    # the case that still requires parens.
    except OSError, subprocess.SubprocessError:
        return None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def evaluate(pins: dict[str, str], present: dict[str, str]) -> CheckResult:
    """Compare pins against reality. Pure — hence directly testable."""
    drifted = []
    for package, wanted in sorted(pins.items()):
        actual = present.get(package)
        if actual is None:
            drifted.append(f"{package}: absent (want {wanted})")
        elif actual != wanted:
            drifted.append(f"{package}: {actual} (want {wanted})")
    if drifted:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_REPAIRABLE,
            site=", ".join(d.split(":")[0] for d in drifted),
            detail="; ".join(drifted),
        )
    conformant = ", ".join(f"{p}=={v}" for p, v in sorted(pins.items()))
    return CheckResult(
        name=NAME, status=Status.PASS, evidence=f"pins satisfied: {conformant}"
    )


def repair(venv_python: Path, pins: dict[str, str]) -> str:
    """Reinstall every pin exactly. Returns '' on success."""
    specs = [f"{package}=={version}" for package, version in sorted(pins.items())]
    try:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(venv_python), "-m", "pip", "install", "--quiet", *specs],
            capture_output=True,
            text=True,
            timeout=900,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{exc!r}"
    return ""


def run(mode: Mode, ctx: Context) -> CheckResult:
    """Verify pins; reinstall to pin when permitted."""
    checks_dir = Path(__file__).resolve().parent
    venv_python = ctx.nix_home / ".venv" / "bin" / "python3"
    if not venv_python.is_file():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"no venv interpreter at {venv_python} — check_venv owns this",
        )
    pins = load_pins(checks_dir)
    present = installed_versions(venv_python)
    if present is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"could not query installed packages via {venv_python} (§4.1)",
        )
    result = evaluate(pins, present)
    if result.status is Status.PASS or mode.rank < Mode.CORRECT.rank:
        return result
    failure = repair(venv_python, pins)
    if failure:
        result.detail = f"{result.detail}; repair failed: {failure}"
        return result
    reinstalled = installed_versions(venv_python)
    if reinstalled is None:
        result.detail = f"{result.detail}; reinstalled but post-repair query failed"
        return result
    repaired = evaluate(pins, reinstalled)
    repaired.action = "reinstalled to pin"
    return repaired


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    # --print-pins (Task 9 review round 2, Finding A): the one validated
    # reader of pinned_deps.json (load_pins, §7) — install.sh calls this
    # instead of re-parsing the JSON itself, so the token guard actually
    # reaches the shell-side `$PINS` expansion it exists to protect. Must
    # work under the bare system interpreter with no .venv and nothing
    # beyond stdlib: install.sh calls it before the venv exists.
    if "--print-pins" in sys.argv[1:]:
        for _pkg, _ver in sorted(load_pins(Path(__file__).resolve().parent).items()):
            print(f"{_pkg}=={_ver}")
        sys.exit(0)

    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            "check_python_deps",
        )
    )
