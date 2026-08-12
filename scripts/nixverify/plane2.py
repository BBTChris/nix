"""Plane 2 — operational logging to journald (risk spec v1.3 §12.10).

TWO PLANES, STRICTLY SEPARATED. This module implements the second one and can
never implement the first.

- **Plane 1** is Postgres, **Limiter sole writer**, financial truth. §12.10 says
  "No new writers, ever." `verify.py` is not a writer of Plane 1 and nothing in
  this file can make it one: there is no database handle here, by construction.
- **Plane 2** is journald/syslog. Each process writes its **own** structured
  one-line events (UTC timestamp, process, event, key=value). It is
  **diagnostic only — never a reconciliation input, never read by the trading
  path.**

`directory_structure.md` pins `logs/` to non-Plane artifacts (Sentinel marker,
backup staging, web logs). **Plane 2 never lands in `logs/`** — this module
opens exactly one destination, the syslog datagram socket, and never a file.

## The §12.10 wrinkle, and why the transport is what it is

§12.10 gets stdout->journald routing *free* because "every process is already
systemd-managed". `verify.py` is the exception it did not anticipate: it is run
interactively from a shell as often as it is run from `nix-verify.service`. In
the interactive case there is no unit to capture stdout, so the free routing
does not apply and an **explicit journal path is required**.

**Four transports were measured on this node before one was chosen** (ARC 024;
`debug.md` §7.4 — measure, do not assume a package is present):

| transport | measurement | verdict |
|---|---|---|
| `systemd.journal.JournalHandler` | importable under `/usr/bin/python3`,
  `ModuleNotFoundError` under `.venv/bin/python3` | **REFUSED** |
| `SysLogHandler` -> `/dev/log` | round-tripped to `journalctl` under
  **both** interpreters | **CHOSEN** |
| `systemd-cat` | present, but one fork+exec per event | rejected: cost |
| stdout -> journald | no unit in the interactive case | not available |

**`JournalHandler` is refused on a measurement, not on taste, and the refusal is
the whole point of this module's gate.** `verify.py` is stdlib-only (§9.1) so it
can run under the system interpreter before `.venv` exists — but it is *also*
run under `.venv` by the test suite and by an operator with the venv active.
`python3-systemd` is present for one of those interpreters and absent from the
other. A `JournalHandler` chosen on the strength of the system interpreter would
attach cleanly, log nothing, and raise nothing every time `verify.py` ran under
the venv: **a handler attached to a logger that never emits.** That is precisely
the vacuity `checks/check_verify_logging.py` exists to fail, and it would have
been built in at the transport layer where the gate could not see it.

`SysLogHandler` is stdlib, so it adds no dependency to a stdlib-only program and
cannot drift out from under it. `/dev/log` is a symlink to
`/run/systemd/journal/dev-log`, so a syslog datagram *is* a journal entry
(`_TRANSPORT=syslog`), readable by `journalctl` with no shim.

## Non-vacuity is structural here

`logging` swallows handler errors by design — `Handler.handleError` prints to
stderr and returns, so a dead socket produces a silent, cheerful no-op. That
default would make every consumer of this module unfalsifiable. `_CountingSysLogHandler`
therefore counts **delivered** and **failed** records, and `Plane2.emitted` /
`Plane2.failed` are what the gate reads. A `Plane2` that emitted nothing reports
zero, and zero is a FAIL condition for the gate, not an absence of evidence.
"""

from __future__ import annotations

import datetime as _dt
import logging
import logging.handlers
import os
import subprocess  # nosec B404 - journalctl is the only journal reader
import sys
from pathlib import Path
from typing import Any

# The journal's syslog ingress. A symlink to /run/systemd/journal/dev-log on a
# systemd box; measured present on node02.
JOURNAL_SOCKET = "/dev/log"

# SYSLOG_IDENTIFIER in the journal. `journalctl -t nix-verify` selects this
# process's Plane-2 stream and nothing else.
IDENTIFIER = "nix-verify"

# The `proc=` field of §12.10's format. Named, not derived from argv[0], so a
# symlinked or re-exec'd invocation still reports the same producer.
PROCESS = "verify.py"

#: Environment variable that disables emission. Exists so the gate can drive a
#: *control* — emission off must produce a FAIL, which is how the gate proves it
#: is measuring the journal rather than its own optimism.
DISABLE_ENV = "NIX_PLANE2_DISABLED"


JOURNALCTL = "/usr/bin/journalctl"


def read_back(
    identifier: str = IDENTIFIER, since: str = "-2 min", grep: str = ""
) -> tuple[list[str], str]:
    """Read this process's Plane-2 stream back out of the journal.

    Returns `(lines, error)` and never raises. Lives here, beside the emitter,
    because the emitter and the reader have to agree on the identifier and the
    output format, and two copies of that agreement drift. `check_verify_logging`
    and `scripts/tests/test_plane2.py` both call this rather than each building
    their own `journalctl` argv — which they did until pylint's similarity
    checker pointed out they were the same six lines twice.

    An empty `lines` with an empty `error` means the journal answered and held
    nothing matching; the two are kept distinct so a caller can tell "nothing
    was logged" from "I could not look".
    """
    if not Path(JOURNALCTL).exists():
        return [], f"{JOURNALCTL} not present"
    try:
        proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
            [JOURNALCTL, "-t", identifier, "--since", since, "--no-pager", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"journalctl failed: {exc!r}"
    if proc.returncode != 0:
        return [], f"journalctl exit {proc.returncode}: {proc.stderr.strip()[:200]}"
    lines = proc.stdout.splitlines()
    return ([line for line in lines if grep in line] if grep else lines), ""


def _utc_now() -> str:
    """§12.10's UTC timestamp, ISO 8601, microsecond, explicit Z.

    `datetime.now(tz=utc)` rather than `utcnow()`: the latter returns a naive
    datetime that *claims* UTC in prose only, which is the same class of defect
    as a value that is true by comment.
    """
    return _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _render_value(value: Any) -> str:
    """Render one field value as a single key=value token.

    Newlines and spaces are what would break the one-line contract, so they are
    the two things this refuses to pass through. A value is never dropped for
    being awkward — it is escaped — because a silently dropped field is an
    event that lies about what it observed.
    """
    text = str(value)
    text = text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    if " " in text or '"' in text:
        text = '"' + text.replace('"', '\\"') + '"'
    return text


def format_event(event: str, fields: dict[str, Any], *, process: str = PROCESS) -> str:
    """§12.10 one-line structured event: UTC timestamp, process, event, key=value.

    Field order is: timestamp, process, event, then the caller's keys in the
    order given. Insertion order is preserved rather than sorted so an event
    reads in the order the code thought about it.

    `process` is keyword-only and defaults to `verify.py` (ARC 026). §12.10 says
    *"Each process writes its **own** structured one-line events"*, so `proc=` is
    per-EMITTER, not a module constant — `capture.py` is the second process to
    own a Plane-2 stream and it must not report itself as `verify.py`. The
    parameter was added rather than a second module written, per
    `nix_check_contract.md` check-rule 8: extend, do not duplicate. Two copies of
    the §12.10 format would drift, and the format is the contract.
    """
    parts = [f"ts={_utc_now()}", f"proc={process}", f"event={event}"]
    parts.extend(f"{key}={_render_value(value)}" for key, value in fields.items())
    return " ".join(parts)


class _CountingSysLogHandler(logging.handlers.SysLogHandler):
    """A SysLogHandler that admits when it failed.

    The base class routes every exception through `handleError`, which by
    default prints to stderr and swallows. That makes "the socket is dead" and
    "everything is fine" indistinguishable from inside the process — the exact
    shape of a false green. This subclass keeps two counters so the difference
    is observable, and so `check_verify_logging.py` has a real subject.
    """

    def __init__(self, address: str) -> None:
        super().__init__(
            address=address, facility=logging.handlers.SysLogHandler.LOG_DAEMON
        )
        self.delivered = 0
        self.failed = 0
        self.last_error = ""

    def emit(self, record: logging.LogRecord) -> None:
        """Delegate, then record which way it went."""
        before = self.failed
        super().emit(record)
        if self.failed == before:
            self.delivered += 1

    def handleError(self, record: logging.LogRecord) -> None:
        """Count the failure and keep its cause. Never re-raise into the run.

        The undelivered record's own text is kept alongside the exception: an
        operator reading `last_error` needs to know *which* event went missing,
        not only that the socket objected.
        """
        self.failed += 1
        exc = sys.exc_info()[1]
        cause = repr(exc) if exc is not None else "unknown"
        self.last_error = f"{cause} while emitting {record.getMessage()!r}"


class Plane2:  # pylint: disable=too-many-instance-attributes
    """The process's own Plane-2 event stream.

    Gained an eighth attribute in ARC 026 — `process`, the `proc=` field — when
    `capture.py` became the second process to own a Plane-2 stream. §12.10 makes
    that per-EMITTER, so it is state on the emitter and not a module constant.

    Construction never raises. A transport that cannot be opened yields an
    instance whose `available` is False and whose `unavailable_reason` names the
    cause — `verify.py` must still run and still report when the journal is
    missing, and it must not pretend it logged.
    """

    def __init__(
        self,
        socket_path: str = JOURNAL_SOCKET,
        identifier: str = IDENTIFIER,
        env: dict[str, str] | None = None,
        *,
        process: str = PROCESS,
    ) -> None:
        environ = os.environ if env is None else env
        self.socket_path = socket_path
        self.identifier = identifier
        #: The `proc=` field every event from THIS emitter carries (§12.10).
        self.process = process
        self.disabled = environ.get(DISABLE_ENV, "") not in ("", "0")
        self.available = False
        self.unavailable_reason = ""
        self._handler: _CountingSysLogHandler | None = None
        self._logger: logging.Logger | None = None
        if self.disabled:
            self.unavailable_reason = f"disabled by {DISABLE_ENV}"
            return
        self._open(socket_path, identifier)

    def _open(self, socket_path: str, identifier: str) -> None:
        """Attach the transport, or record precisely why it could not be."""
        path = Path(socket_path)
        if not path.exists():
            self.unavailable_reason = f"no syslog socket at {socket_path}"
            return
        # A regular file at this path opens without complaint under
        # SysLogHandler's unix-socket fallback and then silently swallows every
        # datagram. MEASURED in ARC 024 while building `check_verify_logging`'s
        # control arm: `available=True delivered=0`. `available` meaning "the
        # constructor did not object" is not worth reporting, so it is made to
        # mean "the destination is a socket" instead.
        if not path.is_socket():
            self.unavailable_reason = f"{socket_path} is not a socket"
            return
        try:
            handler = _CountingSysLogHandler(address=socket_path)
        except OSError as exc:
            self.unavailable_reason = f"cannot open {socket_path}: {exc!r}"
            return
        handler.setFormatter(logging.Formatter(f"{identifier}: %(message)s"))
        logger = logging.getLogger(f"nixverify.plane2.{identifier}")
        logger.setLevel(logging.INFO)
        # propagate=False so a Plane-2 event can never surface on a root handler
        # attached by something else — the presentation stream and this stream
        # must not be able to reach each other (§1.3, and see `render.py`).
        logger.propagate = False
        logger.handlers = [handler]
        self._handler = handler
        self._logger = logger
        self.available = True

    @property
    def emitted(self) -> int:
        """Records the transport actually delivered. Zero is a finding."""
        return self._handler.delivered if self._handler else 0

    @property
    def failed(self) -> int:
        """Records the transport tried and failed to deliver."""
        return self._handler.failed if self._handler else 0

    @property
    def last_error(self) -> str:
        """The transport's account of its most recent delivery failure.

        Public so a gate can report *why* nothing was delivered without reaching
        into the private handler — the counters alone say that delivery failed
        and never say what objected.
        """
        return self._handler.last_error if self._handler else ""

    @property
    def transport(self) -> str:
        """Human-readable description of where events are going, or why nowhere."""
        if self.available:
            return f"syslog:{self.socket_path} ident={self.identifier}"
        return f"unavailable ({self.unavailable_reason})"

    def emit(self, event: str, **fields: Any) -> str:
        """Write one §12.10 event. Returns the rendered line (for tests/gates).

        Returns the line even when the transport is unavailable so a caller can
        still see what *would* have been written; `emitted` is what says whether
        it was.
        """
        line = format_event(event, fields, process=self.process)
        if self._logger is not None:
            self._logger.info(line)
        return line

    def close(self) -> None:
        """Release the socket. Idempotent."""
        if self._handler is not None:
            self._handler.close()
            if self._logger is not None:
                self._logger.handlers = []
            self._handler = None
            self._logger = None
            self.available = False
