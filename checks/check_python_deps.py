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
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_python_deps"

_QUERY = (
    "import json,importlib.metadata as m;"
    "print(json.dumps({d.metadata['Name'].lower(): d.version"
    " for d in m.distributions() if d.metadata['Name']}))"
)


def load_pins(checks_dir: Path) -> dict[str, str]:
    """Read the pins file — never hardcode a version here (§2.4)."""
    path = checks_dir / "pinned_deps.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in payload["packages"].items()}


def installed_versions(venv_python: Path) -> dict[str, str]:
    """Ask the venv what it has. Returns {} if it cannot answer."""
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(venv_python), "-c", _QUERY],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except OSError, subprocess.SubprocessError:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


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
    result = evaluate(pins, installed_versions(venv_python))
    if result.status is Status.PASS or mode.rank < Mode.CORRECT.rank:
        return result
    failure = repair(venv_python, pins)
    if failure:
        result.detail = f"{result.detail}; repair failed: {failure}"
        return result
    repaired = evaluate(pins, installed_versions(venv_python))
    repaired.action = "reinstalled to pin"
    return repaired


if __name__ == "__main__":
    from nixverify.contract import exit_code_for

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
