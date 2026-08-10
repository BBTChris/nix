"""IB Gateway API config: declared state vs a live socket (§4.1, §5, §5.3).

The non-vacuity tests are the load-bearing ones. Doctrine C.3: a gate whose
scope cannot reach its subject passes forever. This gate's subject is a live
socket, so "did it actually try to connect?" is the scope question, and it is
asserted here rather than assumed.
"""

import json
import socket
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status, validate_result
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"

JTS_CONFORMANT = """\
[u:abc123]
AutoRestart=1

[IBGateway]
TrustedIPs=127.0.0.1
LocalServerPort=4000
ApiOnly=true

[Logon]
SupportsSSL=ndc1.ibllc.com:4000,true,20260810,false;cdc1.ibllc.com:4000,true
tradingMode=p
"""

EXPECTED = {
    "api_host": "127.0.0.1",
    "api_port": 4002,
    "trusted_ips": ["127.0.0.1"],
    "auto_restart": True,
    "localhost_only": True,
}


def _mod():
    """Load the check for direct access to evaluate()/parse_jts_ini()."""
    loaded = load_check(CHECKS, "check_ibgateway_config")
    assert loaded.run is not None, loaded.load_error
    import check_ibgateway_config as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    return mod


def _ctx() -> Context:
    return Context(nix_home=REPO, mode=Mode.VERIFY)


def _write_ini(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "jts.ini"
    path.write_text(text, encoding="utf-8")
    return path


def _stub_env(monkeypatch, tmp_path, handshake, addresses=()):
    """Point the check at a fixture jts.ini and a scripted handshake."""
    mod = _mod()
    monkeypatch.setattr(mod, "api_handshake", handshake)
    monkeypatch.setattr(mod, "JTS_INI", _write_ini(tmp_path, JTS_CONFORMANT))
    monkeypatch.setattr(mod, "non_loopback_addresses", lambda: list(addresses))
    monkeypatch.setattr(mod, "load_expected", lambda _d: EXPECTED)
    return mod


# ---------------------------------------------------------------- non-vacuity


def test_run_actually_attempts_a_live_connection(monkeypatch, tmp_path: Path) -> None:
    """§5.3 / doctrine C.3: the gate's scope must contain its subject.

    A gate that reached PASS without opening a socket would be measuring
    nothing — the exact vacuity this check exists to prevent. Record every
    handshake attempt and assert one was made against the declared endpoint.
    """
    attempts: list[tuple[str, int]] = []

    def spy(host, port, _timeout, source=""):  # pylint: disable=unused-argument
        attempts.append((host, port))
        return ("answered", "187")

    mod = _stub_env(monkeypatch, tmp_path, spy)
    result = mod.run(Mode.VERIFY, _ctx())

    assert attempts, "run() reached a verdict without attempting any connection"
    assert (EXPECTED["api_host"], EXPECTED["api_port"]) in attempts
    assert result.status is Status.PASS


def test_pass_evidence_names_the_negotiated_server_version(
    monkeypatch, tmp_path: Path
) -> None:
    """§5: a PASS must carry evidence only a real handshake could produce."""
    mod = _stub_env(monkeypatch, tmp_path, lambda *a, **k: ("answered", "187"))
    result = validate_result(mod.run(Mode.VERIFY, _ctx()))

    assert result.status is Status.PASS
    assert "serverVersion=187" in result.evidence


def test_the_check_is_registered() -> None:
    """A gate nobody runs is not a gate (doctrine D.5/D.6)."""
    registry = json.loads((CHECKS / "registry.json").read_text(encoding="utf-8"))
    registered = [c for b in registry["blocks"] for c in b["checks"]]
    assert "check_ibgateway_config" in registered


# ------------------------------------------------ unreachable != misconfigured


def test_unreachable_gateway_is_cannot_measure_not_fail(
    monkeypatch, tmp_path: Path
) -> None:
    """§4.1: a downed Gateway is a different fact from a broken one."""
    mod = _stub_env(
        monkeypatch, tmp_path, lambda *a, **k: ("unreachable", "ConnectionRefusedError")
    )
    result = mod.run(Mode.VERIFY, _ctx())

    assert result.status is Status.CANNOT_MEASURE


def test_tcp_open_but_not_the_ib_protocol_is_cannot_measure(
    monkeypatch, tmp_path: Path
) -> None:
    """Something else squatting the port has not told us the config is wrong."""
    mod = _stub_env(monkeypatch, tmp_path, lambda *a, **k: ("no-reply", "closed"))
    assert mod.run(Mode.VERIFY, _ctx()).status is Status.CANNOT_MEASURE


# --------------------------------------------------------------- real defects


@pytest.mark.parametrize(
    "key,value,site_fragment",
    [
        ("trusted_ips", ["10.0.0.9"], "TrustedIPs"),
        ("auto_restart", False, "AutoRestart"),
    ],
)
def test_declared_vs_actual_drift_fails_and_names_the_site(
    key, value, site_fragment
) -> None:
    """§5: a FAIL must name the specific setting, never fail generically."""
    mod = _mod()
    expected = dict(EXPECTED) | {key: value}
    defects = mod.evaluate(expected, mod.parse_jts_ini(JTS_CONFORMANT))
    assert defects, "drift produced no defect"
    assert any(site_fragment in site for site, _ in defects)


def test_conformant_ini_produces_no_defects() -> None:
    """The control half: the same comparator must clear a correct config."""
    mod = _mod()
    assert not mod.evaluate(EXPECTED, mod.parse_jts_ini(JTS_CONFORMANT))


def test_non_loopback_source_that_is_served_is_a_named_defect(
    monkeypatch, tmp_path: Path
) -> None:
    """'Allow connections from localhost only' is observable only as behaviour."""
    mod = _stub_env(
        monkeypatch,
        tmp_path,
        lambda *a, **k: ("answered", "187"),
        addresses=["192.168.1.25"],
    )
    result = validate_result(mod.run(Mode.VERIFY, _ctx()))

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "192.168.1.25" in result.site


def test_missing_per_user_section_is_a_named_defect() -> None:
    """A Gateway that never logged in writes no [u:*] section."""
    mod = _mod()
    defects = mod.evaluate(
        EXPECTED, mod.parse_jts_ini("[IBGateway]\nTrustedIPs=127.0.0.1\n")
    )
    assert any("u:*" in site for site, _ in defects)


def test_absent_jts_ini_is_cannot_measure_even_when_the_api_answers(
    monkeypatch, tmp_path: Path
) -> None:
    """The API being up does not license a verdict about settings we cannot read."""
    mod = _stub_env(monkeypatch, tmp_path, lambda *a, **k: ("answered", "187"))
    monkeypatch.setattr(mod, "JTS_INI", tmp_path / "absent.ini")
    assert mod.run(Mode.VERIFY, _ctx()).status is Status.CANNOT_MEASURE


# ------------------------------------------------------------------- parsing


def test_parse_jts_ini_keeps_values_containing_colons_and_semicolons() -> None:
    """Why configparser is not used — see parse_jts_ini's docstring."""
    ini = _mod().parse_jts_ini(JTS_CONFORMANT)
    assert ini["Logon"]["SupportsSSL"].startswith("ndc1.ibllc.com:4000,true")
    assert ";cdc1.ibllc.com:4000" in ini["Logon"]["SupportsSSL"]


def test_parse_jts_ini_reads_the_hashed_per_user_section() -> None:
    """The [u:<hash>] section name is generated — it must be derived, not named."""
    assert _mod().parse_jts_ini(JTS_CONFORMANT)["u:abc123"]["AutoRestart"] == "1"


def test_the_port_is_not_a_literal_in_the_check_source() -> None:
    """§2.4 / doctrine C.4: the port comes from declared state, never from code."""
    source = (CHECKS / "check_ibgateway_config.py").read_text(encoding="utf-8")
    declared = json.loads(
        (CHECKS / "ibgateway_expected.json").read_text(encoding="utf-8")
    )
    assert str(declared["api_port"]) not in source


def test_handshake_reports_unreachable_rather_than_raising() -> None:
    """A closed port must be a verdict, not an exception escaping the check."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    free_port = sock.getsockname()[1]
    sock.close()
    outcome, _ = _mod().api_handshake("127.0.0.1", free_port, 2.0)
    assert outcome == "unreachable"


def test_real_gateway_or_honest_cannot_measure() -> None:
    """End-to-end against whatever is really there — no stubs.

    Deliberately tolerant of the Gateway being down: this asserts the gate
    reaches an honest verdict against real state, never that the box happens
    to have a Gateway running right now.
    """
    loaded = load_check(CHECKS, "check_ibgateway_config")
    assert loaded.run is not None, loaded.load_error
    result = validate_result(loaded.run(Mode.VERIFY, _ctx()))
    assert result.status in (
        Status.PASS,
        Status.CANNOT_MEASURE,
        Status.FAIL_NEEDS_OPERATOR,
    )
    if result.status is Status.PASS:
        assert "serverVersion=" in result.evidence
