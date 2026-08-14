#!/usr/bin/env python3
"""`checks/ibgateway_expected.json`'s own SHAPE, validated — not the live Gateway.

ONE gate, ONE property: the declared-state file `check_ibgateway_config.py` and
`check_ibgateway_service.py` both read as an unvalidated INPUT is itself a
well-formed declaration — every key present, every value the type and shape
its two consumers assume when they do `expected["api_port"]`,
`int(expected["api_port"])`, `expected["units"]`, `expected["display"]` with
NO validation at either call site.

WHY THIS IS A GENUINELY NEW GATE, NOT THE SAME REFUSAL A PRIOR ARC MADE.
`check_ibgateway_config.py`'s own `SUBJECTS` comment refuses to declare this
file THERE, correctly: that gate's job is proving the LIVE Gateway matches the
declaration, and a gate that never validates its input's shape cannot claim
"declaring the input as a subject" as real coverage (D3.19 — naming is not
measuring). This gate does not touch either consumer or the network; it is a
STANDALONE, pure, socket-free validation of the FILE, and it drives that file
to a wrong shape and shows both real consumers would misbehave on it — a
`TypeError`/`ValueError`/nonsensical comparison at the exact call site named
below — before asserting this gate itself catches it first.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The file could be absent. CLOSED: CANNOT_MEASURE naming the path (§17,
    never a PASS).
 2. A schema check could validate keys that are present without ever failing
    on one that is malformed, if every rule were a existence check. CLOSED:
    every rule below is DRIVEN by a targeted plant (a copy with exactly one
    field corrupted) that must redden naming that field, proven in
    `scripts/tests/test_check_ibgateway_expected_schema.py`.
 3. `api_port` could equal jts.ini's SSL-tunnel port (4000) — the file's own
    `why_not_jts_ini` comment names this as the exact confusion the declared
    state exists to avoid, and a schema check that only asked "is this an
    int" would admit the vendor's wrong port silently. CLOSED: 4000 is an
    explicit rejected value, cited to the file's own comment.
 4. `units` could hold a string that is not a real systemd unit filename
    (e.g. missing `.service`), and both consumers would pass it to `systemctl`
    verbatim. CLOSED: every unit is checked against systemd's unit-name
    grammar and the `.service` suffix.
"""

from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
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
#: Reads one file only. No socket, no subprocess.
RESOURCES: tuple[str, ...] = ()
#: CORRECTABLE: this is a shape/type validation over a data file this arc owns
#: the schema of — unlike the live-Gateway settings `check_ibgateway_config`
#: reads (encrypted store, human-only), a malformed declared-state file is the
#: kind of defect a deterministic rewrite to the last-known-good shape could
#: repair. Declared NON-correctable anyway: this gate has no "last known good"
#: to fall back to, and a JSON-shape auto-rewrite risks silently changing WHAT
#: is declared (a port, an IP) rather than merely its shape — which is a human
#: decision about the Gateway's network exposure, never an unattended one.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a malformed field here (a wrong port, a non-loopback IP, a mistyped "
    "unit name) is a human's declared-state error about network exposure "
    "and service identity; an instrument that rewrote it to something merely "
    "well-typed could silently declare a DIFFERENT port or host than the one "
    "the operator intended, which is worse than refusing"
)
SUBJECTS: tuple[str, ...] = ("checks/ibgateway_expected.json",)

NAME = "check_ibgateway_expected_schema"

EXPECTED_FILE = "checks/ibgateway_expected.json"

#: jts.ini's [IBGateway] LocalServerPort — the SSL tunnel to ndc1.ibllc.com,
#: NOT the API port. Cited from the file's own `why_not_jts_ini` comment.
_JTS_SSL_TUNNEL_PORT = 4000

#: systemd unit-name grammar (simplified): letters, digits, and
#: `:-_.\@` per systemd.unit(5), ending in `.service`.
_UNIT_NAME = re.compile(r"^[A-Za-z0-9:_.\\@-]+\.service$")

_DISPLAY = re.compile(r"^:\d+(\.\d+)?$")

REQUIRED_KEYS: tuple[str, ...] = (
    "api_host",
    "api_port",
    "trusted_ips",
    "auto_restart",
    "localhost_only",
    "display",
    "units",
)


class Finding(NamedTuple):
    site: str
    why: str


def _is_ipv4(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def _check_api_host(data: dict, site: str) -> list[Finding]:
    if _is_ipv4(data["api_host"]):
        return []
    return [
        Finding(f"{site}:api_host", f"{data['api_host']!r} is not a valid IPv4 address")
    ]


def _check_api_port(data: dict, site: str) -> list[Finding]:
    port = data["api_port"]
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return [
            Finding(f"{site}:api_port", f"{port!r} is not a valid TCP port (1-65535)")
        ]
    if port == _JTS_SSL_TUNNEL_PORT:
        return [
            Finding(
                f"{site}:api_port",
                f"api_port={port} is jts.ini's [IBGateway] LocalServerPort — the "
                "SSL tunnel to ndc1.ibllc.com, NOT the API port (the file's own "
                "why_not_jts_ini comment names this exact confusion)",
            )
        ]
    return []


def _check_trusted_ips(data: dict, site: str) -> list[Finding]:
    ips = data["trusted_ips"]
    if not isinstance(ips, list) or not ips:
        return [Finding(f"{site}:trusted_ips", f"{ips!r} is not a non-empty list")]
    return [
        Finding(f"{site}:trusted_ips", f"{entry!r} is not a valid IPv4 address")
        for entry in ips
        if not _is_ipv4(entry)
    ]


def _check_bool_flags(data: dict, site: str) -> list[Finding]:
    return [
        Finding(f"{site}:{flag}", f"{data[flag]!r} is not a bool")
        for flag in ("auto_restart", "localhost_only")
        if not isinstance(data[flag], bool)
    ]


def _check_display(data: dict, site: str) -> list[Finding]:
    display = data["display"]
    if isinstance(display, str) and _DISPLAY.match(display):
        return []
    return [Finding(f"{site}:display", f"{display!r} is not an X display spec (':N')")]


def _check_units(data: dict, site: str) -> list[Finding]:
    units = data["units"]
    if not isinstance(units, list) or not units:
        return [Finding(f"{site}:units", f"{units!r} is not a non-empty list")]
    return [
        Finding(
            f"{site}:units", f"{entry!r} is not a valid systemd *.service unit name"
        )
        for entry in units
        if not isinstance(entry, str) or not _UNIT_NAME.match(entry)
    ]


#: One rule per required key. A flat table rather than one long branchy
#: function — each rule is independently readable and independently testable
#: via `evaluate`, and the dispatch loop itself is trivial (§7.12: a function
#: this shape cannot silently skip a rule, because skipping one is dropping a
#: table row, not falling through a branch).
_RULES: tuple[Any, ...] = (
    _check_api_host,
    _check_api_port,
    _check_trusted_ips,
    _check_bool_flags,
    _check_display,
    _check_units,
)


def evaluate(data: dict) -> list[Finding]:
    """The whole rule set, pure and side-effect-free (directly testable)."""
    site = EXPECTED_FILE
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        # Every rule below reads a key by name; stop rather than KeyError.
        return [Finding(site, f"missing required key(s): {missing}")]
    return [finding for rule in _RULES for finding in rule(data, site)]


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        path = ctx.nix_home / EXPECTED_FILE
        if not path.is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{EXPECTED_FILE} is absent — nothing to measure (§17)",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=EXPECTED_FILE,
                evidence=f"{EXPECTED_FILE}: parsed as JSON",
                detail=f"{EXPECTED_FILE} is not valid JSON: {exc}",
            )
        if not isinstance(data, dict):
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=EXPECTED_FILE,
                evidence=f"{EXPECTED_FILE}: parsed as JSON",
                detail=f"top level is {type(data).__name__}, expected an object",
            )
        findings = evaluate(data)
        evidence = (
            f"{EXPECTED_FILE}: {len(REQUIRED_KEYS)} required key(s) checked for "
            "type/shape — api_host/trusted_ips as IPv4, api_port in 1-65535 and "
            f"!= {_JTS_SSL_TUNNEL_PORT} (the jts.ini SSL-tunnel port), display as "
            "an X spec, units as *.service unit names"
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
