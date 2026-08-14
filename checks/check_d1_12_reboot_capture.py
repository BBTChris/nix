#!/usr/bin/env python3
"""D1.12's reboot-capture program, DRIVEN — `scripts/d1_12_reboot_capture.py`.

ONE gate, TWO properties: `capture()`'s `trustworthy` flag is derived from
the no-operator precondition (who/loginctl/uptime) and CORRECTLY reflects it
in both directions, and `capture()` queries the CORRECT (`nix-`prefixed)
systemd unit names — the module's own docstring records that ARC 019's
demonstration of this file exercised only the operator-presence half and
missed a real defect where the OLD unrefixed unit names would have silently
queried units that do not exist. Both are driven directly, never observed
passively (D3.104: "NAMED BY NOTHING" — CHECK-DEBT, this arc).

WHY EVERY `subprocess` CALL IS PATCHED, NEVER REAL. The subject shells to
`who`, `loginctl` and `systemctl` — real host state that varies by machine,
by who is logged into THIS box while `verify.py` runs, and by whether the
IBGateway units exist on the box running the check at all. A gate whose
verdict depended on who happened to be logged in when it ran would be
unreproducible and would conflate "the box's live state" with "the
program's logic is correct" — exactly the class of accidental coupling
`check_ibgateway_config` refuses for the same reason (an unreachable Gateway
is CANNOT_MEASURE, never a verdict about configuration). So this gate
replaces the subject's own `_run` with a fully-controlled double and drives
FIXED, REPRODUCIBLE scenarios through the real `observe_operator_presence`
and `capture` functions.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to import. CLOSED: CANNOT_MEASURE naming the
    exception (§17, never a PASS).
 2. `trustworthy` could be checked only in the "clean boot" direction, which
    a function that always returns `True` would also pass. CLOSED: the
    drive requires BOTH a clean-boot scenario to read `untouched=True` AND a
    logged-in-user scenario to read `untouched=False` naming `who`'s output
    in the reason — a falsifier that ignores `who` entirely is driven and
    shown to fail the second assertion.
 3. The unit-name check could pass by coincidence if the fixture's
    "not-found" sentinel happened to never appear for the WRONG names too.
    CLOSED: the patched `systemctl show` double returns `LoadState=not-found`
    for any unit not in an explicit known-good set, and this gate first
    proves the DOUBLE itself discriminates (a wrong name in a probe call
    reads not-found) before trusting the real drive's silence about it.
 4. The uptime-ceiling check could pass without ever driving a poll past the
    ceiling. CLOSED: a stale-uptime scenario is driven and required to read
    `untouched=False` naming the ceiling.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the test doubles'
# verbs are named after the ports they stand in for, and each arm function's
# name states its own property (§7.12 answer per arm) — a docstring would
# restate the name. too-few-public-methods: several doubles are one-verb
# stand-ins for a frozen port's single relevant method. too-many-locals: an
# arm's local count is the drive's own inputs/outputs, not incidental state.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: `load()` uses `importlib.util.spec_from_file_location` (an exact-path
#: load), never `sys.path`/`sys.modules` search or mutation — see `load`'s
#: docstring for why a name-based import is unsafe for this flat module.
RESOURCES: tuple[str, ...] = ()
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject decides whether D1.12's reboot evidence can be TRUSTED; an "
    "instrument empowered to edit that logic until its own drive came back "
    "clean would be deciding, unattended, what counts as proof nobody "
    "touched the console — the exact human judgment call the module exists "
    "to preserve evidence for"
)
SUBJECTS: tuple[str, ...] = ("scripts/d1_12_reboot_capture.py",)

NAME = "check_d1_12_reboot_capture"

CAPTURE_FILE = "scripts/d1_12_reboot_capture.py"
CAPTURE_MODULE = "d1_12_reboot_capture"

#: The unit names the module's own docstring says are the ONLY correct ones
#: to query — the ARC 020 correction. Any other name reaching the patched
#: `systemctl show` double is a regression back to the bug ARC 019 missed.
_KNOWN_GOOD_UNITS = frozenset({"nix-xvfb.service", "nix-ibgateway.service"})


class Finding(NamedTuple):
    site: str
    why: str


def load(home: Path) -> tuple[ModuleType | None, str]:
    """Load the subject by EXACT FILE PATH, never by a `sys.path` search.

    `d1_12_reboot_capture` is a flat, unpackaged module. A name-based
    `importlib.import_module` search walks the WHOLE of `sys.path` in order,
    and this checks engine's own `_preamble.py` appends the real repo's
    `scripts/` to `sys.path` as a side effect of every check's import — so a
    tree under test that is MISSING this file would still resolve to the
    real one sitting later on `sys.path`, and a plant on a copy would measure
    the wrong file silently. `spec_from_file_location` loads exactly the path
    handed to it and nothing else, so a `home` missing the file is
    unimportable full stop, and it is never registered in `sys.modules`
    under this module's bare name, so it cannot leak into a later run.
    """
    path = home / CAPTURE_FILE
    if not path.is_file():
        return None, (
            f"{CAPTURE_FILE}: not present under {home} — the subject is "
            "unavailable, so nothing was measured (§17: never a PASS)"
        )
    spec = importlib.util.spec_from_file_location(CAPTURE_MODULE, path)
    if spec is None or spec.loader is None:
        return None, f"{CAPTURE_FILE}: could not build an import spec for {path}"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{CAPTURE_FILE}: cannot execute {path} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )


class _FakeRun:
    """Replaces the subject's `_run`. Deterministic, records every call."""

    def __init__(
        self, *, who: str = "", loginctl: str = "", uptime_ok: bool = True
    ) -> None:
        self.who_output = who
        self.loginctl_output = loginctl
        self.uptime_ok = uptime_ok
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, cmd: list[str]) -> tuple[int, str]:
        self.calls.append(tuple(cmd))
        head = cmd[0] if cmd else ""
        if head == "who":
            return 0, self.who_output
        if head == "loginctl":
            return 0, self.loginctl_output
        if head == "systemctl" and len(cmd) >= 2 and cmd[1] == "show":
            unit = cmd[2]
            if unit in _KNOWN_GOOD_UNITS:
                return 0, (
                    f"Id={unit}\nLoadState=loaded\nActiveState=active\n"
                    "SubState=running\nResult=success\n"
                    "ExecMainStartTimestamp=Thu 2026-01-01 00:00:05 UTC\nNRestarts=0"
                )
            return (
                0,
                (
                    f"Id={unit}\nLoadState=not-found\nActiveState=inactive\n"
                    "SubState=dead\nResult=success"
                ),
            )
        if head == "systemctl" and len(cmd) >= 2 and cmd[1] == "is-enabled":
            return 0, "enabled"
        # The IB Gateway check itself and anything else: never actually run.
        return 0, "(patched: not actually run)"


def _patch_uptime(module: Any, seconds: float | None) -> None:
    module.read_uptime_seconds = lambda: seconds  # type: ignore[method-assign]


def _patch_run(module: Any, fake: _FakeRun) -> None:
    module._run = fake  # type: ignore[attr-defined]  # pylint: disable=protected-access


# --------------------------------------------------------------------------
# ARM 1 — trustworthy correctly reflects the no-operator precondition
# --------------------------------------------------------------------------


def _arm_trustworthy(module: Any) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{CAPTURE_FILE}:observe_operator_presence"

    # A clean, untouched boot: no one logged in, uptime well under the ceiling.
    clean = _FakeRun(who="", loginctl="", uptime_ok=True)
    _patch_run(module, clean)
    _patch_uptime(module, 4.0)
    presence = module.observe_operator_presence()
    if not presence["untouched"]:
        findings.append(
            Finding(
                site,
                "a clean boot (no who, no sessions, uptime=4s) read "
                f"untouched=False: {presence['reasons_not_untouched']}",
            )
        )

    # A user logged in: must read untouched=False and NAME the who output.
    dirty = _FakeRun(
        who="bbt      tty1         2026-01-01 00:00", loginctl="", uptime_ok=True
    )
    _patch_run(module, dirty)
    _patch_uptime(module, 4.0)
    presence2 = module.observe_operator_presence()
    if presence2["untouched"]:
        findings.append(
            Finding(site, "a logged-in `who` output still read untouched=True")
        )
    elif not any("logged in" in r for r in presence2["reasons_not_untouched"]):
        findings.append(
            Finding(
                site,
                f"logged-in case did not name the reason: {presence2['reasons_not_untouched']}",
            )
        )

    # A stale capture, well past the ceiling: must read untouched=False naming it.
    _patch_run(module, _FakeRun(who="", loginctl="", uptime_ok=True))
    _patch_uptime(module, module.UNTOUCHED_UPTIME_CEILING_S + 100.0)
    presence3 = module.observe_operator_presence()
    if presence3["untouched"]:
        findings.append(
            Finding(site, "an uptime past the ceiling still read untouched=True")
        )
    elif not any("ceiling" in r for r in presence3["reasons_not_untouched"]):
        findings.append(
            Finding(
                site,
                f"stale-uptime case did not name the ceiling: {presence3['reasons_not_untouched']}",
            )
        )

    # Falsifier: presence detection that ignores `who` entirely.
    real_observe = module.observe_operator_presence

    def _blind_to_who() -> dict:
        who_rc, _who_out = module._run(["who"])  # pylint: disable=protected-access
        del who_rc
        return {
            "who_rc": 0,
            "who": "",
            "loginctl_rc": 0,
            "loginctl_sessions": "",
            "uptime_s_at_capture": 4.0,
            "untouched": True,
            "reasons_not_untouched": [],
        }

    module.observe_operator_presence = _blind_to_who  # type: ignore[assignment]
    _patch_run(module, dirty)
    blind_presence = module.observe_operator_presence()
    module.observe_operator_presence = real_observe  # type: ignore[assignment]
    if not blind_presence["untouched"]:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the who-blind falsifier still reported untouched=False — it no longer falsifies",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — capture() queries the CORRECT (nix-prefixed) unit names
# --------------------------------------------------------------------------


def _arm_unit_names(module: Any) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{CAPTURE_FILE}:capture[units]"

    # First, prove the double itself discriminates: a WRONG name reads not-found.
    fake = _FakeRun(who="", loginctl="", uptime_ok=True)
    _patch_run(module, fake)
    _patch_uptime(module, 4.0)
    _rc, wrong_out = module._run(  # pylint: disable=protected-access
        ["systemctl", "show", "ibgateway.service", "--no-pager"]
    )
    if "not-found" not in wrong_out:
        findings.append(
            Finding(
                f"{site}:double-sanity",
                "the fixture's OWN double did not flag the wrong (unprefixed) name as not-found",
            )
        )

    record = module.capture()
    for unit, payload in record["units"].items():
        if unit not in _KNOWN_GOOD_UNITS:
            findings.append(
                Finding(site, f"capture() queried an unexpected unit name: {unit!r}")
            )
            continue
        output = payload["systemctl_show"]["output"]
        if "not-found" in output:
            findings.append(
                Finding(
                    site,
                    f"capture() queried {unit!r} and got LoadState=not-found — "
                    "the ARC 020 unprefixed-name regression",
                )
            )
    if set(record["units"]) != _KNOWN_GOOD_UNITS:
        findings.append(
            Finding(
                site,
                f"capture() queried {sorted(record['units'])}, expected "
                f"exactly {sorted(_KNOWN_GOOD_UNITS)}",
            )
        )
    return findings


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        module, error = load(ctx.nix_home)
        if module is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_trustworthy(module)
        findings += _arm_unit_names(module)
        evidence = (
            f"{CAPTURE_FILE}: drove observe_operator_presence/capture with a "
            "fully-patched _run over 3 scenarios (clean boot, logged-in user, "
            "stale uptime) plus a who-blind falsifier, and drove capture()'s "
            "unit-query set against the ARC 020 nix-prefix regression"
        )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(f.site for f in findings),
                evidence=evidence,
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
