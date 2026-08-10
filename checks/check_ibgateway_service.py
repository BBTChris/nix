#!/usr/bin/env python3
"""Verify Xvfb and IB Gateway survive a boot, and are genuinely usable.

Owns: **service persistence** — that `nix-xvfb.service` and
`nix-ibgateway.service` are enabled, and that the things they manage actually
work. It does **not** own API configuration (trusted IPs, auto-restart,
localhost-only); `check_ibgateway_config.py` owns those, and §5.5 / doctrine
C.9 forbid a second instrument for a property another already owns.

**The failure mode this gate exists to catch** is a unit that is `enabled` and
`active` while the thing it manages is unusable. So `systemctl is-enabled` and
process-alive are recorded as *evidence*, never as the verdict: the verdict
comes from the display answering `xdpyinfo` and the Gateway completing a real
API handshake. The predecessor system's recorded mistake was computing broker
connection state and never publishing it anywhere a check could read, so no
instrument could tell connected from disconnected. This does not rebuild that.

**Reachability means something different here than in `check_ibgateway_config`,
deliberately.** There, an unreachable Gateway is `CANNOT_MEASURE`: that gate
reads configuration *through* the connection, so no connection means no
reading. Here, an unreachable Gateway with its unit enabled is the defect
itself — persistence that does not persist. Same observation, two gates, two
correct meanings. The handshake is *imported* from `check_ibgateway_config`
rather than reimplemented, so the two can never disagree about what
"reachable" is.

Stdlib-only at module scope (§9.1); never imports its subject (§9.4).
"""

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status, result_from_defects

# checks/ is on sys.path under the engine (loader appends it) but not when
# this module is run directly. Adding it here keeps the sibling import below
# working on both paths, exactly as _preamble does for scripts/.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

# Deliberately below the sys.path append above, so pylint's position and
# grouping rules are both waived here rather than the append being moved.
# pylint: disable=wrong-import-position,ungrouped-imports
from check_ibgateway_config import api_handshake, load_expected

PRIVILEGE = "user"
INTERACTIVE = False
# Reads unit state and opens sockets. Never starts, stops, or enables
# anything — repairing this would restart Gateway and drop an authenticated
# session, which is an operator decision, not an unattended one.
DISRUPTIVE = False

NAME = "check_ibgateway_service"

XDPYINFO = "/usr/bin/xdpyinfo"
SYSTEMCTL = "/usr/bin/systemctl"
PROBE_TIMEOUT = 8.0


def unit_property(unit: str, verb: str) -> tuple[str, str]:
    """Ask systemd about one unit. Returns (value, error).

    A non-zero exit is normal here — `is-enabled` exits 1 for a disabled unit
    and prints the state on stdout — so the state is read from stdout and
    only a failure to *run* systemctl at all becomes an error.
    """
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [SYSTEMCTL, verb, unit],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"{type(exc).__name__}: {exc}"
    value = proc.stdout.strip()
    if not value:
        return "", (proc.stderr.strip() or f"systemctl {verb} {unit}: no output")
    return value, ""


def display_answers(display: str) -> tuple[bool, str]:
    """Prove the X display serves a real client. Returns (ok, evidence).

    `xdpyinfo` is a genuine X client: it opens the display and reads the
    server's dimensions. Xvfb being in the process table proves none of that
    — a display server can be alive and not accepting connections.
    """
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [XDPYINFO, "-display", display],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr.strip() or f"xdpyinfo exit {proc.returncode}")[:120]
    dims = [ln for ln in proc.stdout.splitlines() if "dimensions:" in ln]
    detail = dims[0].strip() if dims else "display opened"
    return True, detail


def check_units(units: list[str]) -> tuple[list[tuple[str, str]], list[str], str]:
    """Read enablement for every declared unit.

    Returns (defects, evidence_fragments, fatal_error). `fatal_error` is set
    only when systemd could not be queried at all — unmeasurable, not failed.
    """
    defects: list[tuple[str, str]] = []
    evidence: list[str] = []
    for unit in units:
        enabled, error = unit_property(unit, "is-enabled")
        if error:
            return [], [], f"cannot query systemd about {unit}: {error}"
        active, _ = unit_property(unit, "is-active")
        evidence.append(f"{unit}={enabled}/{active or 'unknown'}")
        if enabled != "enabled":
            defects.append(
                (
                    unit,
                    f"is-enabled reports {enabled!r} — will not come back after a reboot",
                )
            )
    return defects, evidence, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Assess boot persistence and real usability. Never repairs (see above)."""
    expected = load_expected(Path(__file__).resolve().parent)
    units = list(expected["units"])
    display = expected["display"]
    host, port = expected["api_host"], int(expected["api_port"])

    defects, evidence, fatal = check_units(units)
    if fatal:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=fatal)

    # The display: usability, not liveness.
    if not Path(XDPYINFO).is_file():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"{XDPYINFO} absent — cannot prove the display answers, and "
            "process-alive is not a substitute (doctrine C.1)",
        )
    ok, display_detail = display_answers(display)
    evidence.append(f"display {display}: {display_detail}")
    if not ok:
        defects.append((f"display {display}", f"does not answer — {display_detail}"))

    # The Gateway socket: same handshake check_ibgateway_config uses, imported
    # rather than reimplemented (§5.5).
    outcome, api_detail = api_handshake(host, port, PROBE_TIMEOUT)
    evidence.append(f"{host}:{port} handshake: {outcome} ({api_detail[:48]})")
    if outcome != "answered":
        defects.append(
            (
                f"{host}:{port} (nix-ibgateway.service)",
                f"API endpoint not reachable — {outcome}: {api_detail[:80]}",
            )
        )

    return result_from_defects(NAME, defects, "; ".join(evidence))


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.contract import exit_code_for, validate_result

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.site:
        print(f"  site: {OUTCOME.site}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
