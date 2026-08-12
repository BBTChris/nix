#!/usr/bin/env python3
"""Verify the IB Gateway API surface against its declared state.

Owns: **API configuration** — that the API socket genuinely answers the IB
wire protocol on the declared port, and that the settings Gateway does keep
in plaintext match what Nix declared. It does **not** own service persistence
(units, enablement, display) — that is `check_ibgateway_service.py`'s
property, and §5.5 forbids a second instrument for a property another owns.

Proves effective state, never a proxy (doctrine C.1). "jts.ini exists" and
"the JVM is alive" are both true of a Gateway sitting on its login screen
with no API listener. This check completes the v100+ handshake and reads back
the server version, which only a live API endpoint can produce.

Stdlib-only at module scope (§9.1) and never imports its subject (§9.4): the
handshake is 20 lines of `socket`, so this runs under /usr/bin/python3 before
.venv or ib_async exist.

Status discipline (§4.1): an unreachable Gateway is CANNOT_MEASURE, never
FAIL. A downed Gateway and a misconfigured one are different facts, and
collapsing them would send --correct after a defect that does not exist.
Every real defect here is FAIL_NEEDS_OPERATOR: Gateway's settings are
changed by a human at the VNC console, so the engine must never claim it can
repair them.
"""

from __future__ import annotations

import json
import socket
import struct
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status, result_from_defects

PRIVILEGE = "user"
INTERACTIVE = False

# --- ARC 025 Stage 2.1 orchestration declarations (Wave C, declare-only) ---
DEPENDS_ON: tuple[str, ...] = ()
#: The API endpoint, and nothing else. Both Gateway gates claim this SAME token
#: on purpose: `check_ibgateway_service` imports this module's `api_handshake`
#: and dials the identical socket, and IBKR sessions collide by design (clientId
#: 1/2/905 are distinct for exactly this reason). Declaring the shared token is
#: what keeps `--optimize` from ever promoting the two into one parallel block —
#: the constraint is now DECLARED and mechanically checked rather than being a
#: property of the hand-maintained block order (§6, ARC 024's live hazard).
#:
#: The non-loopback reject probe dials the same port from a routable source
#: address, so it is the same claim; `port:` matches on port, not on host.
RESOURCES: tuple[str, ...] = ("port:4002",)
#: Runtime is set by socket timeouts, not by work. NOT derived from an observed
#: run: this box measures 0.04 s only because the Gateway is DOWN and
#: ECONNREFUSED returns instantly. That figure is MASKED — it is what the check
#: costs when its subject is unavailable, which is the one case the bound does
#: not describe. 12.0 = CONNECT_TIMEOUT (8.0) + REJECT_TIMEOUT (4.0), one call
#: each on the worst path, both literals in this module.
TIME_BOUND = True
EXPECTED_S = 12.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the API surface this gate reads is not a file the engine can write. "
    "'Allow connections from localhost only' lives in Gateway's ENCRYPTED "
    "settings store and is observable only by behaviour, and the remaining "
    "settings take effect through a Gateway restart that drops an "
    "authenticated session. A 'correction' here would mean restarting the "
    "broker connection unattended — §4.3 names broker session state as a "
    "member of the non-correctable class, and §8 makes a session-dropping "
    "restart an operator decision, never an unattended repair"
)
#: NOT `checks/ibgateway_expected.json`. This gate READS that file as its
#: expectation (`load_expected` is a bare `json.loads` with no validation), and
#: an input is not a measured subject. Declaring it would move the coverage
#: count without measuring anything — the vacuity `check_artifact_gate_coverage`
#: already warns it cannot see (D3.19).
SUBJECTS: tuple[str, ...] = ()
# Reads a socket and a config file. Nothing is restarted or swapped, so this
# is safe on the boot runner (§8).
DISRUPTIVE = False

NAME = "check_ibgateway_config"

JTS_INI = Path.home() / "Jts" / "jts.ini"
EXPECTED_FILE = "ibgateway_expected.json"

# Handshake budget. Long enough for a loaded JVM, short enough that a boot
# unit is never held up materially.
CONNECT_TIMEOUT = 8.0
# Deliberately shorter: this one runs against an address expected NOT to
# answer, so it is paid in full on every healthy run.
REJECT_TIMEOUT = 4.0

# Client-side supported range. The server answers with the version it
# negotiated; we assert only that it answered, never a specific number —
# Gateway updates on the vendor's schedule (§7) and pinning the version here
# would be an anchor to a moving value (§2.4).
_API_RANGE = b"v100..187"


def load_expected(checks_dir: Path) -> dict:
    """Read declared state. Never hardcode a port or an IP here (§2.4)."""
    return json.loads((checks_dir / EXPECTED_FILE).read_text(encoding="utf-8"))


def parse_jts_ini(text: str) -> dict[str, dict[str, str]]:
    """Minimal INI reader for jts.ini.

    configparser is avoided deliberately: jts.ini's first section header is
    `[u:diieodccik...]`, and its values contain `:` and `;` (SupportsSSL,
    Peer), which configparser's default delimiters and inline-comment
    handling mangle. This reads what is actually on disk rather than what a
    general parser assumes.
    """
    sections: dict[str, dict[str, str]] = {}
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
        elif "=" in line and current:
            key, _, value = line.partition("=")
            sections[current][key.strip()] = value.strip()
    return sections


def api_handshake(
    host: str, port: int, timeout: float, source: str = ""
) -> tuple[str, str]:
    """Complete the v100+ prologue. Returns (outcome, detail).

    outcome is one of:
      "answered"  -> detail is the negotiated server version
      "no-reply"  -> TCP connected but the peer closed without speaking the
                     protocol. This is what Gateway does to a source address
                     its localhost-only policy rejects, so it is a *result*,
                     not an error.
      "unreachable" -> could not connect at all.
    """
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        if source:
            sock.bind((source, 0))
        sock.connect((host, port))
    except OSError as exc:
        sock.close()
        return "unreachable", f"{type(exc).__name__}: {exc}"
    try:
        sock.sendall(b"API\x00" + struct.pack("!I", len(_API_RANGE)) + _API_RANGE)
        return _read_prologue(sock)
    except OSError as exc:
        return "no-reply", f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    """Read `size` bytes, or fewer if the peer closes first."""
    body = b""
    while len(body) < size:
        chunk = sock.recv(size - len(body))
        if not chunk:
            break
        body += chunk
    return body


def _read_prologue(sock: socket.socket) -> tuple[str, str]:
    """Parse the server's reply to the prologue. See api_handshake."""
    head = sock.recv(4)
    if len(head) < 4:
        return "no-reply", "peer closed before replying to the prologue"
    size = struct.unpack("!I", head)[0]
    # Sanity-bound the declared length: a non-IB service answering here must
    # not be able to make this check allocate arbitrarily.
    if not 0 < size <= 4096:
        return "no-reply", f"implausible frame length {size} — not the IB protocol"
    body = _recv_exactly(sock, size)
    fields = body.split(b"\x00")
    if len(fields) < 2 or not fields[0].isdigit():
        return "no-reply", f"peer answered but not with the IB protocol: {body[:40]!r}"
    return "answered", fields[0].decode()


def non_loopback_addresses() -> list[str]:
    """Local addresses that are not loopback, for the localhost-only probe.

    Derived from the host's own interfaces at check time — never a literal
    (§2.4). Returns [] when the box genuinely has no routable address, which
    the caller must treat as "cannot measure this property", not as a pass.
    """
    found: list[str] = []
    for family, _, _, _, sockaddr in socket.getaddrinfo(
        socket.gethostname(), None, socket.AF_INET
    ):
        addr = sockaddr[0]
        if (
            family is socket.AF_INET
            and isinstance(addr, str)
            and not addr.startswith("127.")
        ):
            found.append(addr)
    # getaddrinfo often yields only loopback on a headless box; ask the
    # routing table for the address that would carry outbound traffic.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed, no packet sent
        addr = probe.getsockname()[0]
        if not addr.startswith("127.") and addr not in found:
            found.append(addr)
    except OSError:
        pass
    finally:
        probe.close()
    return found


def evaluate(expected: dict, ini: dict[str, dict[str, str]]) -> list[tuple[str, str]]:
    """Compare declared state against jts.ini's plaintext settings.

    Returns [(site, detail)] — empty means conformant. Pure, hence directly
    testable without a Gateway.
    """
    defects: list[tuple[str, str]] = []

    gateway = ini.get("IBGateway", {})
    want_ips = [ip.strip() for ip in expected["trusted_ips"]]
    got_raw = gateway.get("TrustedIPs")
    if got_raw is None:
        defects.append(("jts.ini:[IBGateway]TrustedIPs", "key absent"))
    else:
        got_ips = [ip.strip() for ip in got_raw.split(",") if ip.strip()]
        if got_ips != want_ips:
            defects.append(
                ("jts.ini:[IBGateway]TrustedIPs", f"{got_ips} (declared {want_ips})")
            )

    # AutoRestart lives in the per-user [u:<dir>] section, whose name is a
    # generated directory hash — derive it rather than naming it (§2.4).
    user_sections = [name for name in ini if name.startswith("u:")]
    if not user_sections:
        defects.append(
            ("jts.ini:[u:*]", "no per-user section — Gateway never logged in?")
        )
    else:
        section = user_sections[0]
        got = ini[section].get("AutoRestart")
        want = "1" if expected["auto_restart"] else "0"
        if got != want:
            defects.append(
                (f"jts.ini:[{section}]AutoRestart", f"{got!r} (declared {want!r})")
            )
    return defects


def probe_localhost_only(port: int, defects: list[tuple[str, str]]) -> str:
    """Measure whether a non-loopback source is served, appending any defect.

    'Allow connections from localhost only' appears in no file on disk — it
    lives in Gateway's encrypted settings store — so the only way to know its
    effective state is to be a non-localhost client and see what happens.
    Gateway accepts the TCP connection either way; the discriminator is
    whether it answers the protocol prologue.

    Returns the evidence string. A host with no routable address returns
    "unprobed" rather than a pass — an unmeasured property is not a satisfied
    one (§5).
    """
    addresses = non_loopback_addresses()
    if not addresses:
        return "no non-loopback address on this host — property unprobed"
    source = addresses[0]
    outcome, detail = api_handshake(source, port, REJECT_TIMEOUT, source=source)
    if outcome != "answered":
        return f"{source} refused ({outcome}: {detail[:60]})"
    defects.append(
        (
            f"IB Gateway API :{port} accepts {source}",
            (
                "non-loopback source completed the handshake — "
                "'allow connections from localhost only' is OFF"
            ),
        )
    )
    return f"{source} ACCEPTED (defect)"


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Assess the Gateway API surface. Never repairs — see module docstring."""
    checks_dir = Path(__file__).resolve().parent
    expected = load_expected(checks_dir)
    host, port = expected["api_host"], int(expected["api_port"])

    # 1. Effective state first. Everything below is only meaningful about a
    #    Gateway that is actually serving the API.
    outcome, detail = api_handshake(host, port, CONNECT_TIMEOUT)
    if outcome == "unreachable":
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"no API endpoint at {host}:{port} — {detail}. "
            "Gateway down or not logged in; that is not a misconfiguration (§4.1)",
        )
    if outcome == "no-reply":
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"{host}:{port} accepted TCP but did not complete the IB "
            f"handshake — {detail}. Cannot read configuration through a "
            "connection that never opened (§4.1)",
        )
    server_version = detail

    # 2. Declared-vs-actual on everything Gateway keeps in plaintext.
    if not JTS_INI.is_file():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=f"IB API answered on {host}:{port}, serverVersion={server_version}",
            detail=f"{JTS_INI} absent — API is up but its settings cannot be read",
        )
    ini = parse_jts_ini(JTS_INI.read_text(encoding="utf-8", errors="replace"))
    defects = evaluate(expected, ini)

    # 3. localhost-only is not in any file — it is only observable as
    #    behaviour, so measure the behaviour.
    reject_evidence = (
        probe_localhost_only(port, defects)
        if expected.get("localhost_only")
        else "not probed"
    )

    evidence = (
        f"IB API handshake on {host}:{port} -> serverVersion={server_version}; "
        f"jts.ini sections={sorted(ini)}; localhost-only probe: {reject_evidence}"
    )
    return result_from_defects(NAME, defects, evidence)


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            "check_ibgateway_config",
        )
    )
