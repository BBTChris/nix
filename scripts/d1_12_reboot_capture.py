#!/usr/bin/env python3
"""D1.12 — capture IB Gateway service state at boot, BEFORE anyone touches the console.

WHY THIS EXISTS, and why it is not just "run the check after rebooting".

D1.12 asks whether IB Gateway actually comes back after a reboot. `systemctl is-enabled`
is a DECLARATION, not evidence — doctrine C.1 (prove effective running state, never
file-presence / import-success / process-alive). The only evidence is the service's state
after a real reboot.

The trap is the operator. If a human logs in and starts poking — or worse, starts the
Gateway by hand out of habit — the observation is worthless, and it is worthless in the
direction that looks like success. Running the check "after the reboot" by hand cannot
distinguish "it came back on its own" from "it came back because I was here".

So this runs from a systemd oneshot at boot, and it does two things:

  1. It records the check's verdict.
  2. It records EVIDENCE THAT NOBODY WAS THERE — logged-in users, seat sessions, and the
     uptime at capture. A capture taken 4 seconds into a boot with zero sessions is
     evidence. The same verdict taken by hand ten minutes later is not.

(2) is the whole point. Without it this file is just a slower way to be fooled.

FAILS CLOSED: any capture that cannot establish the no-operator precondition is written
with `"trustworthy": false` and a reason. It is never silently downgraded to a pass, and
the absence of a capture file is itself a finding — a boot that produced no file means the
unit did not run, which is the D1.12 failure this is built to detect.

ARMING IT (needs root; the reboot is the operator's call, not this script's):

    sudo cp <this dir>/nix-reboot-capture.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable nix-reboot-capture.service
    # then, and only then, reboot. Do not log in first.

Print the unit text with `--unit`. Read the last capture with `--show`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - fixed argv, no shell, no user input
import sys
from datetime import UTC, datetime
from pathlib import Path

NIX_HOME = Path(__file__).resolve().parent.parent
VENV_PYTHON = NIX_HOME / ".venv" / "bin" / "python"
CHECK = NIX_HOME / "checks" / "check_ibgateway_service.py"
CAPTURE_DIR = NIX_HOME / "logs" / "d1_12_reboot_capture"

# Above this, we cannot claim the console was untouched. A boot reaches multi-user in
# seconds; a capture minutes in means the unit was late or was run by hand, and either
# way the no-operator precondition is no longer established BY the uptime alone.
UNTOUCHED_UPTIME_CEILING_S = 300.0

UNIT_TEXT = """\
[Unit]
Description=Nix D1.12 — capture IB Gateway service state at boot, before console access
# After, NOT Requires: if the gateway unit failed, that IS the measurement. Requiring it
# would make this unit fail to run in exactly the case it exists to record.
After=multi-user.target ibgateway.service
Wants=multi-user.target

[Service]
Type=oneshot
ExecStart=/home/bbt/nix/.venv/bin/python /home/bbt/nix/scripts/d1_12_reboot_capture.py
User=bbt
Group=bbt
# No TimeoutStartSec override: the check is offline and bounded.

[Install]
WantedBy=multi-user.target
"""


def _run(cmd: list[str]) -> tuple[int, str]:
    """Return (exit code, combined output). Never raises on a missing binary."""
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def read_uptime_seconds() -> float | None:
    """Seconds since boot, or None if /proc/uptime is unreadable.

    None is a distinct answer from a large number: it means the capture cannot say how
    long after boot it ran, which is one of the two things that establish the
    no-operator precondition.
    """
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except OSError, ValueError, IndexError:
        return None


def read_boot_id() -> str | None:
    """The kernel's boot id, or None. Names the boot a capture belongs to, so two
    captures cannot be silently attributed to the same reboot."""
    try:
        return (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
        )
    except OSError:
        return None


def observe_operator_presence() -> dict:
    """Everything we can say about whether a human was here when we measured.

    Derived from the running system, never asserted. Each source is recorded raw so a
    reader can disagree with our conclusion rather than having to trust it.
    """
    who_rc, who_out = _run(["who"])
    sessions_rc, sessions_out = _run(
        ["loginctl", "list-sessions", "--no-legend", "--no-pager"]
    )
    uptime_s = read_uptime_seconds()

    reasons: list[str] = []
    if who_rc != 0:
        reasons.append(f"`who` did not run (rc={who_rc}); login state unverifiable")
    elif who_out:
        reasons.append(f"a user was logged in at capture: {who_out!r}")
    if sessions_rc == 0 and sessions_out:
        reasons.append(f"loginctl reported active session(s): {sessions_out!r}")
    if uptime_s is None:
        reasons.append("/proc/uptime unreadable; capture time relative to boot unknown")
    elif uptime_s > UNTOUCHED_UPTIME_CEILING_S:
        reasons.append(
            f"captured {uptime_s:.1f}s after boot, past the "
            f"{UNTOUCHED_UPTIME_CEILING_S:.0f}s ceiling — too late to establish that "
            "the console was untouched"
        )

    return {
        "who_rc": who_rc,
        "who": who_out,
        "loginctl_rc": sessions_rc,
        "loginctl_sessions": sessions_out,
        "uptime_s_at_capture": uptime_s,
        "untouched": not reasons,
        "reasons_not_untouched": reasons,
    }


def capture() -> dict:
    """One D1.12 observation: the verdict, plus the evidence that it can be trusted.

    `trustworthy` is derived from the operator-presence probe and never from the check's
    own exit code — a green check taken while a human was logged in is exactly the
    observation this file exists to refuse.
    """
    presence = observe_operator_presence()
    check_rc, check_out = _run([str(VENV_PYTHON), str(CHECK)])
    unit_rc, unit_out = _run(
        [
            "systemctl",
            "show",
            "ibgateway.service",
            "--no-pager",
            "--property=ActiveState,SubState,Result,ExecMainStartTimestamp,NRestarts",
        ]
    )
    enabled_rc, enabled_out = _run(["systemctl", "is-enabled", "ibgateway.service"])

    return {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "boot_id": read_boot_id(),
        "debt_row": "D1.12",
        "operator_presence": presence,
        # The verdict is only as good as the precondition. Both are recorded; neither is
        # allowed to stand in for the other.
        "trustworthy": presence["untouched"],
        "check_ibgateway_service": {"exit": check_rc, "output": check_out},
        # `is-enabled` is a DECLARATION and is recorded as one — it is never the evidence.
        "systemctl_is_enabled_DECLARATION_ONLY": {
            "exit": enabled_rc,
            "output": enabled_out,
        },
        "systemctl_show": {"exit": unit_rc, "output": unit_out},
    }


def main() -> int:
    """Capture (default), or `--unit` to print the systemd unit, or `--show` to read
    the latest capture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unit", action="store_true", help="print the systemd unit text"
    )
    parser.add_argument("--show", action="store_true", help="print the latest capture")
    args = parser.parse_args()

    if args.unit:
        print(UNIT_TEXT, end="")
        return 0

    if args.show:
        files = sorted(CAPTURE_DIR.glob("*.json"))
        if not files:
            print(
                f"no capture in {CAPTURE_DIR} — the unit has not run across a boot. "
                "D1.12 remains RED; absence of a capture is itself the finding.",
                file=sys.stderr,
            )
            return 1
        print(files[-1].read_text(encoding="utf-8"), end="")
        return 0

    record = capture()
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = record["captured_at_utc"].replace(":", "").replace("-", "")
    out = CAPTURE_DIR / f"{stamp}-{record['boot_id'] or 'unknown-boot'}.json"
    out.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.chmod(out, 0o644)

    verdict = "TRUSTWORTHY" if record["trustworthy"] else "NOT TRUSTWORTHY"
    print(f"{verdict}: wrote {out}")
    for reason in record["operator_presence"]["reasons_not_untouched"]:
        print(f"  precondition not met: {reason}")
    # Exit 0 even when untrustworthy: the capture SUCCEEDED at recording that it cannot
    # be trusted. A non-zero exit here would make systemd log a unit failure and invite
    # someone to "fix" it, when the correct response is to reboot again without touching
    # the console. The verdict lives in the file, where a reader must look at it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
