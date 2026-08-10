"""Xvfb + IB Gateway boot persistence, and real usability (§4.1, §5, §5.3).

This gate exists because "unit enabled and active" is not "the thing works".
Its tests are written the same way: none of them accept a systemctl verb as
proof of anything, and the non-vacuity tests assert the gate really reaches
the display and the socket rather than short-circuiting on unit state.
"""

import json
from pathlib import Path

from nixverify.contract import Context, Mode, Status, validate_result
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"

UNITS = ["nix-xvfb.service", "nix-ibgateway.service"]
EXPECTED = {
    "api_host": "127.0.0.1",
    "api_port": 4002,
    "display": ":99",
    "units": UNITS,
}


# pylint: disable=duplicate-code
def _mod():
    """Load the check for direct access to its helpers."""
    loaded = load_check(CHECKS, "check_ibgateway_service")
    assert loaded.run is not None, loaded.load_error
    import check_ibgateway_service as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    return mod


def _ctx() -> Context:
    return Context(nix_home=REPO, mode=Mode.VERIFY)


def _healthy(monkeypatch, mod, enabled="enabled"):
    """Stub every external observation to a working system."""
    monkeypatch.setattr(mod, "load_expected", lambda _d: EXPECTED)
    monkeypatch.setattr(
        mod,
        "unit_property",
        lambda _u, verb: (enabled if verb == "is-enabled" else "active", ""),
    )
    monkeypatch.setattr(
        mod, "display_answers", lambda _d: (True, "dimensions: 1440x900")
    )
    monkeypatch.setattr(mod, "api_handshake", lambda *a, **k: ("answered", "187"))


# ---------------------------------------------------------------- non-vacuity


def test_run_probes_the_display_and_the_socket_not_just_unit_state(
    monkeypatch,
) -> None:
    """§5.3 / doctrine C.3: the gate's scope must contain its subject.

    The whole point of this gate is that unit state is not proof. If it could
    reach PASS without touching the display or the socket, it would be the
    proxy check it exists to replace.
    """
    mod = _mod()
    probed: list[str] = []
    _healthy(monkeypatch, mod)

    def spy_display(display):
        probed.append(f"display:{display}")
        return (True, "ok")

    def spy_socket(host, port, _timeout):
        probed.append(f"socket:{host}:{port}")
        return ("answered", "187")

    monkeypatch.setattr(mod, "display_answers", spy_display)
    monkeypatch.setattr(mod, "api_handshake", spy_socket)

    result = mod.run(Mode.VERIFY, _ctx())

    assert "display::99" in probed, "reached a verdict without opening the display"
    assert "socket:127.0.0.1:4002" in probed, (
        "reached a verdict without opening the socket"
    )
    assert result.status is Status.PASS


def test_evidence_records_what_was_measured_not_just_that_it_passed(
    monkeypatch,
) -> None:
    """§5: a PASS carries what was observed, or the engine downgrades it."""
    mod = _mod()
    _healthy(monkeypatch, mod)
    result = validate_result(mod.run(Mode.VERIFY, _ctx()))

    assert result.status is Status.PASS
    assert "dimensions" in result.evidence
    assert "handshake: answered" in result.evidence


def test_the_check_is_registered() -> None:
    """A gate nobody runs is not a gate (doctrine D.5/D.6)."""
    registry = json.loads((CHECKS / "registry.json").read_text(encoding="utf-8"))
    registered = [c for b in registry["blocks"] for c in b["checks"]]
    assert "check_ibgateway_service" in registered


def test_it_does_not_duplicate_the_config_check_handshake() -> None:
    """§5.5 / doctrine C.9: one implementation of 'reachable', two consumers.

    Two instruments measuring one property will disagree eventually. This
    asserts the service gate imports the handshake rather than owning a copy.
    """
    source = (CHECKS / "check_ibgateway_service.py").read_text(encoding="utf-8")
    assert "from check_ibgateway_config import" in source
    assert "def api_handshake" not in source


# --------------------------------------------------------------- real defects


def test_a_disabled_unit_fails_and_names_that_unit(monkeypatch) -> None:
    """The boot property: disabled means it will not come back."""
    mod = _mod()
    _healthy(monkeypatch, mod)
    monkeypatch.setattr(
        mod,
        "unit_property",
        lambda unit, verb: (
            ("disabled" if unit == "nix-xvfb.service" else "enabled", "")
            if verb == "is-enabled"
            else ("active", "")
        ),
    )

    result = validate_result(mod.run(Mode.VERIFY, _ctx()))

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "nix-xvfb.service" in result.site
    assert "nix-ibgateway.service" not in result.site


def test_enabled_units_with_a_dead_display_still_fails(monkeypatch) -> None:
    """The exact failure this gate exists for: enabled, active, unusable."""
    mod = _mod()
    _healthy(monkeypatch, mod)
    monkeypatch.setattr(
        mod, "display_answers", lambda _d: (False, "unable to open display")
    )

    result = validate_result(mod.run(Mode.VERIFY, _ctx()))

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert ":99" in result.site


def test_enabled_units_with_an_unreachable_gateway_fails(monkeypatch) -> None:
    """Persistence that does not persist is a defect, not an unknown.

    Deliberately the opposite of check_ibgateway_config, which calls the same
    observation CANNOT_MEASURE — that gate reads config *through* the
    connection; this one is asserting the connection exists at all.
    """
    mod = _mod()
    _healthy(monkeypatch, mod)
    monkeypatch.setattr(
        mod, "api_handshake", lambda *a, **k: ("unreachable", "refused")
    )

    result = validate_result(mod.run(Mode.VERIFY, _ctx()))

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "4002" in result.site


def test_unqueryable_systemd_is_cannot_measure_not_fail(monkeypatch) -> None:
    """§4.1: no systemd answer is an unknown, never a violation."""
    mod = _mod()
    _healthy(monkeypatch, mod)
    monkeypatch.setattr(mod, "unit_property", lambda _u, _v: ("", "FileNotFoundError"))

    assert mod.run(Mode.VERIFY, _ctx()).status is Status.CANNOT_MEASURE


def test_absent_xdpyinfo_is_cannot_measure(monkeypatch) -> None:
    """Without an X client there is no proof — and alive is not a substitute."""
    mod = _mod()
    _healthy(monkeypatch, mod)
    monkeypatch.setattr(mod, "XDPYINFO", "/nonexistent/xdpyinfo")

    assert mod.run(Mode.VERIFY, _ctx()).status is Status.CANNOT_MEASURE


def test_units_come_from_declared_state_not_from_the_source() -> None:
    """§2.4 / doctrine C.4: unit names are declared, never literals in code."""
    source = (CHECKS / "check_ibgateway_service.py").read_text(encoding="utf-8")
    declared = json.loads(
        (CHECKS / "ibgateway_expected.json").read_text(encoding="utf-8")
    )
    assert declared["units"] == UNITS
    # nix-ibgateway.service appears once, inside a human-facing site string;
    # the iterated list itself must come from declared state.
    assert 'units = list(expected["units"])' in source


def test_real_system_reaches_an_honest_verdict() -> None:
    """End-to-end against whatever is really there — no stubs."""
    loaded = load_check(CHECKS, "check_ibgateway_service")
    assert loaded.run is not None, loaded.load_error
    result = validate_result(loaded.run(Mode.VERIFY, _ctx()))
    assert result.status in (
        Status.PASS,
        Status.CANNOT_MEASURE,
        Status.FAIL_NEEDS_OPERATOR,
    )
    if result.status is Status.PASS:
        assert "handshake: answered" in result.evidence
