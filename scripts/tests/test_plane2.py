"""Plane-2 journald emitter per risk spec v1.3 §12.10 (ARC 024).

The load-bearing property of this module is that §12.10 events are **one line
each**: journald splits on newlines, so a value carrying a newline would smear
one event across several journal entries and make the stream unparseable by
anything downstream. Several tests below exist only to hold that line.

The second property under test is that `Plane2` never lies about delivery. A
`logging` handler swallows its own errors by design, so "the socket is dead" and
"everything is fine" look identical from inside the process unless something
counts. These tests pin the counters and the `available` / `unavailable_reason`
pair that `checks/check_verify_logging.py` reads.
"""
# pylint: disable=invalid-name,import-outside-toplevel,use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test on purpose; `== ()` is asserted
# rather than `not x` because an empty tuple and a falsey non-tuple are
# different outcomes here; late imports are the sys.path bootstrap this suite
# needs. Each is deliberate, so the pragma is per-file and named.

import datetime as dt
import shutil
import socket
import time
import uuid
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.plane2 import (
    DISABLE_ENV,
    IDENTIFIER,
    JOURNAL_SOCKET,
    PROCESS,
    Plane2,
    _render_value,  # pylint: disable=protected-access
    format_event,
    read_back,
)

TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _journal_socket_present() -> bool:
    """True only when /dev/log exists AND is really a socket.

    `exists()` alone is not enough: a regular file at that path is exactly the
    false-green condition `Plane2._open` was hardened against in ARC 024.
    """
    return Path(JOURNAL_SOCKET).is_socket()


def _journalctl_readable() -> bool:
    """True only when journalctl exists and this user may actually read a stream.

    In a container journalctl is often absent, or present and refused. Either
    way the live round-trip below must SKIP, never fail — an absent journal is
    not a defect in this module.
    """
    if shutil.which("/usr/bin/journalctl") is None:
        return False
    _, error = read_back(since="-1 min")
    return not error


LIVE_JOURNAL = _journal_socket_present() and _journalctl_readable()


@pytest.fixture(name="dgram_socket")
def _dgram_socket(tmp_path: Path):
    """A real bound AF_UNIX SOCK_DGRAM listener, so delivery can be measured.

    Hermetic stand-in for /dev/log: SysLogHandler opens a unix datagram socket
    the same way against either, so this exercises the real transport without
    depending on systemd being present.
    """
    path = tmp_path / "dev-log"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(str(path))
    server.settimeout(2.0)
    try:
        yield path, server
    finally:
        server.close()


# -- format_event / _render_value ------------------------------------------


def test_format_event_orders_ts_proc_event_then_caller_fields() -> None:
    """§12.10 field order: UTC timestamp, process, event, then key=value."""
    line = format_event("run_start", {"mode": "verify", "checks": 13})
    parts = line.split(" ")
    assert parts[0].startswith("ts=")
    assert parts[1] == f"proc={PROCESS}"
    assert parts[2] == "event=run_start"
    # Insertion order preserved, not sorted: an event reads in the order the
    # code thought about it.
    assert parts[3] == "mode=verify"
    assert parts[4] == "checks=13"


def test_format_event_is_exactly_one_line() -> None:
    """One event, one journal entry — no embedded or trailing newline."""
    line = format_event("run_start", {"mode": "verify"})
    assert "\n" not in line
    assert "\r" not in line


def test_render_value_quotes_a_value_containing_a_space() -> None:
    """A bare space would end the token early and split one field into two."""
    assert _render_value("two words") == '"two words"'


def test_render_value_escapes_an_embedded_quote_inside_the_quoted_form() -> None:
    """Quoting is only safe if the quote character itself is escaped."""
    assert _render_value('say "hi"') == '"say \\"hi\\""'


def test_render_value_escapes_a_newline_rather_than_dropping_the_field() -> None:
    """A dropped field is an event that lies about what it observed."""
    rendered = _render_value("line one\nline two")
    assert "\n" not in rendered
    assert "\\n" in rendered
    assert "line two" in rendered


def test_event_with_a_multiline_value_still_renders_as_one_line() -> None:
    """THE load-bearing property: journald splits on newlines.

    A check detail containing a traceback is the realistic source of an embedded
    newline, and it must never be able to smear one event across several journal
    entries.
    """
    line = format_event(
        "check_verdict",
        {"name": "check_venv", "detail": "Traceback:\n  File x\r\n  boom"},
    )
    assert "\n" not in line
    assert "\r" not in line


def test_timestamp_parses_as_utc_iso8601_with_microseconds() -> None:
    """The `ts=` field must be machine-parseable and genuinely UTC.

    `utcnow()` would produce a naive datetime that claims UTC in prose only;
    comparing the parsed value against `now(timezone.utc)` is what makes the
    claim falsifiable on a box whose local zone is not UTC.
    """
    ts = format_event("e", {}).split(" ", 1)[0].removeprefix("ts=")
    # DTZ007 (naive strptime, no %z) is the point, not an oversight: the wire
    # format ends in a literal `Z`, so parsing it yields a naive datetime and the
    # UTC claim has to be verified against a real clock below rather than trusted.
    parsed = dt.datetime.strptime(ts, TS_FORMAT)  # noqa: DTZ007
    assert parsed.microsecond >= 0  # %f consumed a real microsecond field
    aware = parsed.replace(tzinfo=dt.UTC)
    assert aware.tzinfo is dt.UTC
    assert aware.utcoffset() == dt.timedelta(0)
    drift = abs((dt.datetime.now(tz=dt.UTC) - aware).total_seconds())
    assert drift < 120, f"ts={ts} is not UTC-now (drift {drift}s)"


# -- Plane2 availability ----------------------------------------------------


def test_regular_file_destination_is_reported_unavailable(tmp_path: Path) -> None:
    """MEASURED in ARC 024: a regular file opens fine and swallows every datagram.

    `available` must therefore mean "the destination is a socket", not "the
    constructor did not object".
    """
    path = tmp_path / "not-a-socket"
    path.write_text("", encoding="utf-8")
    plane = Plane2(socket_path=str(path), env={})
    assert plane.available is False
    assert "not a socket" in plane.unavailable_reason
    assert str(path) in plane.unavailable_reason


def test_missing_socket_path_is_reported_unavailable_and_named(tmp_path: Path) -> None:
    """Construction never raises; it records precisely which path was absent."""
    path = tmp_path / "absent" / "dev-log"
    plane = Plane2(socket_path=str(path), env={})
    assert plane.available is False
    assert str(path) in plane.unavailable_reason


def test_disable_env_turns_emission_off_without_breaking_the_caller() -> None:
    """The gate's control arm: emission off must be observable, not fatal.

    `env` is passed explicitly rather than mutating os.environ — the parameter
    exists so a test can drive the control without a process-wide side effect.
    """
    plane = Plane2(socket_path=JOURNAL_SOCKET, env={DISABLE_ENV: "1"})
    assert plane.disabled is True
    assert plane.available is False
    assert DISABLE_ENV in plane.unavailable_reason
    line = plane.emit("run_start", mode="verify")
    assert "event=run_start" in line  # the caller still sees what WOULD be written
    assert plane.emitted == 0  # ...and nothing claims it was written


def test_disable_env_zero_and_empty_do_not_disable() -> None:
    """Only a truthy value disables; "0" is an explicit "leave it on"."""
    assert Plane2(socket_path="/nonexistent", env={DISABLE_ENV: "0"}).disabled is False
    assert Plane2(socket_path="/nonexistent", env={DISABLE_ENV: ""}).disabled is False


def test_emit_on_an_unavailable_plane_does_not_raise(tmp_path: Path) -> None:
    """verify.py must still run and still report when the journal is missing."""
    plane = Plane2(socket_path=str(tmp_path / "absent"), env={})
    line = plane.emit("check_verdict", name="check_venv", status="pass")
    assert "event=check_verdict" in line
    assert plane.emitted == 0
    assert plane.failed == 0
    assert "unavailable" in plane.transport


# -- Plane2 delivery, over a real unix datagram socket ----------------------


def test_emit_delivers_a_datagram_and_counts_it(dgram_socket) -> None:
    """Non-vacuity: `emitted` must move only when a record really went out."""
    path, server = dgram_socket
    plane = Plane2(socket_path=str(path), identifier="nix-verify-test", env={})
    assert plane.available is True, plane.unavailable_reason
    try:
        plane.emit("run_start", mode="verify")
        payload = server.recv(4096).decode("utf-8", "replace")
        assert "event=run_start" in payload
        assert "nix-verify-test" in payload  # SYSLOG_IDENTIFIER tag
        assert plane.emitted == 1
        assert plane.failed == 0
    finally:
        plane.close()


def test_transport_names_the_socket_when_available(dgram_socket) -> None:
    """The operator-facing description must name where events actually go."""
    path, _server = dgram_socket
    plane = Plane2(socket_path=str(path), identifier="nix-verify-test", env={})
    try:
        assert str(path) in plane.transport
        assert "nix-verify-test" in plane.transport
    finally:
        plane.close()


def test_close_is_idempotent_and_marks_the_plane_unavailable(dgram_socket) -> None:
    """close() runs on every exit path, including after an earlier close()."""
    path, _server = dgram_socket
    plane = Plane2(socket_path=str(path), identifier="nix-verify-test", env={})
    assert plane.available is True, plane.unavailable_reason
    plane.close()
    assert plane.available is False
    plane.close()  # must not raise
    assert plane.available is False


def test_close_on_a_never_opened_plane_does_not_raise(tmp_path: Path) -> None:
    """The unavailable path must survive the same shutdown sequence."""
    plane = Plane2(socket_path=str(tmp_path / "absent"), env={})
    plane.close()
    plane.close()
    assert plane.available is False


# -- Live journald round trip ----------------------------------------------


@pytest.mark.skipif(
    not LIVE_JOURNAL,
    reason="no /dev/log socket or journalctl unavailable/unreadable (container)",
)
def test_event_round_trips_to_journalctl() -> None:
    """End-to-end proof that a syslog datagram really becomes a journal entry.

    Skipped, never failed, where there is no journal: the absence of systemd is
    a property of the box, not a defect in this module.
    """
    nonce = uuid.uuid4().hex
    plane = Plane2(socket_path=JOURNAL_SOCKET, env={})
    assert plane.available is True, plane.unavailable_reason
    try:
        plane.emit("test_round_trip", nonce=nonce)
        assert plane.emitted == 1
    finally:
        plane.close()

    deadline = time.monotonic() + 5.0
    seen = ""
    while time.monotonic() < deadline:
        lines, _ = read_back(since="-1 min")
        seen = "\n".join(lines)
        if nonce in seen:
            break
        time.sleep(0.25)
    assert nonce in seen, f"nonce {nonce} never appeared in journalctl -t {IDENTIFIER}"
