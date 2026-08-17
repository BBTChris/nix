#!/usr/bin/env python3
"""§12.2's crash-loop breaker, ACTUATED from systemd. The `OnFailure=` target.

ARC 034 / sub-agent C. Authority is the frozen risk spec,
`docs/nics_risk_subsystem_spec_v1.3.md`; every `§` below cites it unless another
document is named on the same line.

WHAT RUNS THIS. A supervised unit that adopts `scripts/nix-supervision.conf`
carries `OnFailure=nix-crash-loop-halt@%n.service`, so systemd runs this program
once per failure of that unit with the failing unit's name as `--unit`. Nothing
on this box carries that line today: ARC 034 was not authorised to install,
enable, start or `daemon-reload` anything on a machine running a live IB
Gateway. The program is therefore driven by `checks/check_supervision.py` and by
`scripts/tests/test_supervision.py` as a SUBPROCESS with its paths pointed at a
scratch directory — which is exactly how systemd will drive it, one short-lived
process per crash.

WHY THE HALT IS A MARKER AND NOT A PLANE-1 ROW. §12.5:634-638, verbatim:

    **Limiter-down case (v1.3):** if a HALT condition arises while the Limiter is
    unavailable (e.g. the Risk Engine itself is the crash-looping process), the
    system is already **fail-closed** — nothing reaches the broker without the
    Limiter — so no separate flag is needed for safety. The `HALT set` row is
    **booked retroactively at next boot by cold-start reconciliation**, same
    pattern as the Sentinel marker replay (§12.1): Plane-1 completeness holds
    without a second writer.

That paragraph describes THIS program's situation by name. So the HALT is
recorded by `halt.HaltMarker`, and `halt.replay_markers` books it at the next
boot through the Limiter's own port. §9's sole-writer invariant is untouched:
this process is not a Plane-1 writer and never opens one.

WHY THE COUNTER IS ON DISK. The subject is a process that is crashing. A restart
counter in that process's memory is reset by the event it counts, so it reaches
one and stays there. `supervision.RestartLedger` is append-only with one
`fsync(2)` per record, and every invocation of this program reads the whole
ledger back before deciding.

EXIT CODES ARE NOT THE ANSWER AND NOTHING ASSERTS ON THEM ALONE (check contract
v2 §11). This program prints one JSON object on stdout carrying the count, the
cap, the window, whether the cap was hit and whether a marker was written; the
exit code is a courtesy for `systemctl status`. Both instruments read the JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

#: The kernel's own per-boot identity. `HaltMarker.record_set` requires a `boot`
#: because ARC 034 / D3.195 measured a per-instance `seq` colliding ACROSS boots:
#: boot 1's `booked` suppressed boot 2's UNBOOKED `set`, and `archive` then
#: renamed the evidence away, so §12.5:637's Plane-1 completeness did not hold.
#:
#: This actuator is a SHORT-LIVED PROCESS invoked by systemd, so it cannot take
#: its boot identity the way `HaltFlag` does — that one mints a uuid per
#: long-lived instance, which is right for a daemon and WRONG here: a fresh uuid
#: per invocation would make every restart look like its own boot and defeat the
#: very collision the argument exists to prevent. The kernel's `boot_id` is
#: stable for the whole boot and changes across boots, which is exactly the
#: identity the marker needs, and it costs one file read with no state to keep.
_KERNEL_BOOT_ID = Path("/proc/sys/kernel/random/boot_id")


def current_boot_id() -> str:
    """This boot's identity — the kernel's, or a uuid when it is unreadable.

    The fallback is deliberately NOT a constant: an unreadable `boot_id` (a
    non-Linux host, a restricted container) must not make two boots share an
    identity, because that reintroduces D3.195's collision silently. A fresh uuid
    over-separates instead, which errs toward replaying a row twice rather than
    toward losing one — and §9's log is append-only, so a duplicate is visible
    where a silent omission is not.
    """
    try:
        return _KERNEL_BOOT_ID.read_text(encoding="utf-8").strip()
    except OSError:
        return uuid.uuid4().hex

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixrisk.halt import HaltCause, HaltMarker
from nixrisk.supervision import (
    SCORE_BOUNDARY,
    RestartLedger,
    SupervisionKnobs,
)

#: Where the durable restart counts live when nothing overrides them. Under
#: `state/`, which is 0600 and gitignored (D1.16), because a restart ledger is
#: operational state and not a repository artifact.
DEFAULT_LEDGER = "state/supervision/restarts.jsonl"

#: Where the §12.5:637 HALT marker lands. Same directory, same reasoning.
DEFAULT_MARKER = "state/supervision/halt.marker"

#: `risks/` is the physical home of the two §12A knobs (§12A is the SEMANTIC
#: authority). Read through the same loader every other module uses.
CONFIG_REL = "risks/supervision.config.json"


def _knobs(home: Path) -> SupervisionKnobs:
    """Load the two knobs through `risk_config`, never by re-reading JSON here.

    Directive 3: the config file is the single physical home and
    `scripts/risk_config.py` is the single reader. A second JSON parse in this
    file would be a second source of truth for a number that gates money.
    """
    import risk_config  # pylint: disable=import-outside-toplevel

    loaded = risk_config.load_risk_configs(home)
    return SupervisionKnobs.from_config(loaded.modules["supervision"].values)


def _report(**fields: Any) -> str:
    """One JSON line. The REASON is a field; the exit code is not the answer."""
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    """Count one restart of `--unit`; declare a §12.2 HALT if the cap is hit."""
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument(
        "--unit", required=True, help="the failing systemd unit (systemd's %%i)"
    )
    parser.add_argument(
        "--home", default=str(REPO), help="repository root holding risks/ and state/"
    )
    parser.add_argument("--ledger", default="", help="override the restart ledger path")
    parser.add_argument("--marker", default="", help="override the HALT marker path")
    parser.add_argument(
        "--now", type=float, default=None, help="override the clock (seconds, UTC)"
    )
    args = parser.parse_args(argv)

    home = Path(args.home).resolve()
    now = time.time() if args.now is None else float(args.now)
    try:
        knobs = _knobs(home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        print(
            _report(
                ok=False,
                unit=args.unit,
                reason=(
                    f"cannot load {CONFIG_REL} from {home}: "
                    f"{type(exc).__name__}: {exc} — refusing to run the §12.2 "
                    "breaker on defaulted knobs (directive 4)"
                ),
            )
        )
        return 2

    ledger = RestartLedger(args.ledger or (home / DEFAULT_LEDGER))
    ledger.record(args.unit, now, detail="systemd OnFailure")
    counted = ledger.since(args.unit, now - knobs.window_s)
    cap_hit = len(counted) >= knobs.crash_loop_max

    reason = (
        f"§12.2:617 — unit {args.unit!r} restarted {len(counted)} time(s) within "
        f"{knobs.crash_loop_window_min} min (cap {knobs.crash_loop_max}, "
        f"{CONFIG_REL})"
    )
    marker_path = ""
    if cap_hit:
        marker = HaltMarker(args.marker or (home / DEFAULT_MARKER))
        seq = len(marker.entries()) + 1
        marker.record_set(HaltCause.CRASH_LOOP, reason, now, seq, current_boot_id())
        marker_path = str(marker.path)

    print(
        _report(
            ok=True,
            unit=args.unit,
            restarts_in_window=len(counted),
            cap=knobs.crash_loop_max,
            window_s=knobs.window_s,
            cap_hit=cap_hit,
            halt_cause=HaltCause.CRASH_LOOP.value if cap_hit else "",
            marker=marker_path,
            marker_note=(
                "§12.5:634-638 — the Limiter may BE the crash-looping process, so "
                "the HALT set row is written as a marker here and booked "
                "retroactively into Plane 1 at next boot by cold-start "
                "reconciliation. This process is not a Plane-1 writer"
            ),
            score_boundary=SCORE_BOUNDARY,
            reason=reason,
        )
    )
    return 1 if cap_hit else 0


if __name__ == "__main__":
    sys.exit(main())
