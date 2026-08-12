"""IB Gateway API config: declared state vs a live socket (§4.1, §5, §5.3).

The non-vacuity tests are the load-bearing ones. Doctrine C.3: a gate whose
scope cannot reach its subject passes forever. This gate's subject is a live
socket, so "did it actually try to connect?" is the scope question, and it is
asserted here rather than assumed.
"""

import ast
import json
import socket
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status, validate_result
from nixverify.declarations import read_declaration
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


# pylint: disable=duplicate-code
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


def _resources_line_span(source: str) -> tuple[int, int]:
    """1-indexed [start, end] lines of the module-level RESOURCES assignment."""
    for node in ast.parse(source).body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            first = node.targets[0]
            target = first.id if isinstance(first, ast.Name) else None
        if target == "RESOURCES":
            return node.lineno, (node.end_lineno or node.lineno)
    raise AssertionError("check_ibgateway_config declares no module-level RESOURCES")


def test_the_port_is_not_a_literal_in_the_check_logic() -> None:
    """§2.4 / doctrine C.4: the port comes from declared state, never from code.

    SCOPE NARROWED, AND THE GATE MADE STRICTER, ARC 025 Stage 2.1.

    This asserted the port string appeared NOWHERE in the source. Stage 2.1 then
    had to declare `RESOURCES = ("port:4002",)`, because the shared token is what
    stops `--optimize` co-scheduling the two Gateway gates on one endpoint, and
    `declarations.py` reads declarations by AST — it can only read a LITERAL, so
    there is no spelling of that declaration which derives the port at import
    time. The two requirements are in genuine tension and the tension is real,
    not a bug in either.

    Weakening the gate to "assert nothing" would have been doctrine B.4's
    forbidden direction. Instead the property is split and the pair demands
    strictly MORE than the single assertion did:

      * here — the port is absent from everything the check REASONS with, which
        is the property §2.4 actually cares about; and
      * `test_the_declared_port_must_equal_the_expectation_file` — the
        declaration is PINNED to `ibgateway_expected.json`, so it cannot drift.

    Absence could always be satisfied by a check that ignored the port entirely.
    Equality cannot.
    """
    source = (CHECKS / "check_ibgateway_config.py").read_text(encoding="utf-8")
    declared = json.loads(
        (CHECKS / "ibgateway_expected.json").read_text(encoding="utf-8")
    )
    start, end = _resources_line_span(source)
    lines = source.splitlines()
    logic = "\n".join(lines[: start - 1] + lines[end:])

    # Non-vacuity BEFORE the assertion (doctrine C.3): prove the excluded span is
    # the declaration and nothing more, and that logic is still most of the file.
    excluded = "\n".join(lines[start - 1 : end])
    assert "RESOURCES" in excluded, excluded
    assert len(logic) > 0.8 * len(source), "excluded far more than one declaration"
    assert "api_handshake" in logic, "the check's real logic was excluded"

    assert str(declared["api_port"]) not in logic


def test_the_declared_port_must_equal_the_expectation_file() -> None:
    """Doctrine B.7 — the document and the code cannot drift, because a machine
    reads both and compares.

    `RESOURCES` has to carry a literal port (the AST reader cannot evaluate an
    expression), which makes it exactly the kind of anchor doctrine C.4 warns
    about: correct the day it is typed, silently wrong the first time an
    operator repoints `api_port`. This closes that by construction — changing
    `ibgateway_expected.json` without changing the declaration is RED, and
    changing the declaration without the file is RED.
    """
    declared = json.loads(
        (CHECKS / "ibgateway_expected.json").read_text(encoding="utf-8")
    )
    expected_token = f"port:{declared['api_port']}"

    for name in ("check_ibgateway_config", "check_ibgateway_service"):
        decl = read_declaration(CHECKS / f"{name}.py")
        assert not decl.errors, decl.errors
        assert expected_token in decl.resources, (
            f"{name} declares RESOURCES={decl.resources} but "
            f"{CHECKS / 'ibgateway_expected.json'} says api_port="
            f"{declared['api_port']}. The declaration and the expectation file "
            "have drifted — that is the moving anchor doctrine C.4 names."
        )


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
