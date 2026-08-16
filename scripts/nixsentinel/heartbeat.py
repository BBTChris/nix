"""The RISK-ENGINE heartbeat: the Limiter publishes it, the Sentinel watches it.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 034 / sub-agent B (B1). Implements the FROZEN `HeartbeatPort` declared in
`scripts/nixsentinel/seam.py` and adds the PRODUCER side, which did not exist:
§12.1:604 says the Sentinel *"Watches the Risk-Engine heartbeat"*, and nothing in
this tree published one. A watcher with no producer is a watcher that can only
ever report "never seen", which is the one reading it must never act on.

------------------------------------------------------------------------------
TWO HEARTBEATS EXIST IN THIS SYSTEM AND THIS IS NOT THE OTHER ONE
------------------------------------------------------------------------------
* **THIS one is the RISK-ENGINE heartbeat (§12.1:604).** One publisher — the
  Limiter — and one watcher — the Sentinel. Losing it means the process that
  holds every synthetic stop is gone, and the response is an emergency flatten.
* The **STRATEGY heartbeat** (§4:260-261, `nix_strategy_contract_v1.1.md` §4.6)
  is a different signal with a different publisher (each strategy), a different
  watcher (the Limiter), a different threshold (`HEARTBEAT_MISS_GRACE`, one
  cycle) and a different response (§4's orphan recovery). It is not this file's
  subject and this file must never be read as covering it.

They share the §12A:832 `HEARTBEAT_INTERVAL` knob and nothing else. The shared
knob is exactly why the confusion is available, so it is named here.

------------------------------------------------------------------------------
WHY A FILE, AND WHY `os.replace` RATHER THAN AN APPEND
------------------------------------------------------------------------------
§12.1:603 requires the Sentinel to be *"Tiny, dependency-minimal"* and on a
*"separate code path (minimal common-mode failure)"*. A ZMQ socket, a shared
memory segment or a broker of any kind is a dependency that can be sick in the
same way the thing that killed the Risk Engine was sick. A single small file
written with `os.replace` needs the kernel and nothing else, and `os.replace` is
atomic within a filesystem, so a reader either sees the whole previous record or
the whole new one — never half of each.

**The heartbeat is deliberately NOT fsynced, and that is the opposite of the
marker file's rule on purpose.** A heartbeat is LIVENESS, not evidence: its only
consumer asks "has this changed recently", and a beat lost to a power cut is a
beat correctly read as lost. `nixsentinel/marker.py` fsyncs every record because
that file is the evidence that has to outlive the process; paying the same cost
once a second for a value whose whole meaning is "recent" would buy nothing.

------------------------------------------------------------------------------
WHY THE RECORD CARRIES `pid` AND `seq` AND NOT ONLY `ts`
------------------------------------------------------------------------------
The seam's `Heartbeat` docstring fixes this and this module is what makes it
true. A stalled process and a restarted one both stop the value a naive watcher
reads, and they call for different operator narratives:

* a NEW `pid` with `seq` restarted from zero is a **RESTART** (§12.2's supervisor
  did its job);
* the SAME `pid` with a FROZEN `seq` is a **HANG** — and a hung process can still
  have a thread updating `ts`, so a watcher reading `ts` alone would call it
  healthy forever.

`seq` is therefore the progress signal and `ts` is the staleness signal, and
`nixsentinel/watchdog.py` requires BOTH to declare the heartbeat live.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO
------------------------------------------------------------------------------
It does not decide the loss threshold (that is `nixsentinel/config.py` reading
`risks/sentinel.config.json`), it does not decide what to do about a lost
heartbeat (`nixsentinel/watchdog.py`), and it does not run the Limiter's publish
loop — the Limiter owns its own cadence and calls `publish()` from it. It
imports NOTHING from `nixrisk`: §12.1:603's separate code path is the property
this package exists to hold, and an import edge from here into the Limiter's
package would be the common-mode failure named as the reason for the separation.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from nixsentinel.seam import Heartbeat

#: The record's wire schema. A DIFFERENT number from `MARKER_SCHEMA` and from
#: `SENTINEL_SEAM_REV`: this record crosses a PROCESS boundary live, so a Sentinel
#: built at one revision can meet a Limiter built at another and must refuse
#: loudly rather than read fields into the wrong meaning.
HEARTBEAT_SCHEMA = 1

#: The file's name under whatever directory the operator points the pair at.
#: `docs/directory_structure.md`'s `logs` line is the Sentinel MARKER's home and
#: is not this file's: a heartbeat is not an artifact, it is a live value with a
#: one-second lifetime, and putting it in `logs/` would imply it is kept.
DEFAULT_HEARTBEAT_NAME = "risk_engine.heartbeat.json"

#: The mode both sides use. The heartbeat names a pid and a position count; it is
#: not a credential, but nothing in `~/nix` outside `state/` needs to be world
#: readable and the default umask is not a guarantee.
_MODE = 0o600


class HeartbeatError(RuntimeError):
    """A heartbeat that exists but cannot be understood.

    Deliberately DISTINCT from absence. `HeartbeatPort.read` returns `None` for
    "no heartbeat has ever been published", which is a Sentinel that started
    before the Limiter and has no evidence of anything; this exception is
    "something is there and it is not a heartbeat", which is a real fault. The
    seam's `HeartbeatPort` docstring fixes exactly this split and names collapsing
    the two as the defect that would flatten every cold boot.

    Never swallowed here. `nixsentinel/watchdog.py` catches it and counts it as
    NO PROGRESS — fail closed — because a heartbeat it cannot read is a heartbeat
    that has not proven the Limiter alive.
    """


class HeartbeatPublisher:
    """The PRODUCER — the Limiter's side of §12.1:604's heartbeat.

    Owned by the Risk Engine, called from its own cadence at §12A:832's
    `HEARTBEAT_INTERVAL`. It is in `nixsentinel/` rather than `nixrisk/` for one
    reason: the two sides must agree on the record's shape byte for byte, and one
    module holding both spellings is the only way that agreement cannot drift
    (directive 3 — derive from a single source of truth). The import edge that
    creates runs `nixrisk -> nixsentinel`, which is the SAFE direction: the
    Sentinel's own import graph stays free of the Limiter's, which is the whole of
    §12.1:603's *separate code path*.

    `seq` starts at zero and increments per published beat, per process. It is
    NOT persisted across a restart, and that is the point: a fresh process
    starting at zero is precisely how the watcher tells a restart from a hang.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        pid: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        #: Recorded once at construction. A publisher that re-read `os.getpid()`
        #: every beat would report the FORKED child's pid after a fork, which is a
        #: different process claiming the parent's heartbeat.
        self.pid = os.getpid() if pid is None else pid
        self._clock = clock
        self._seq = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HeartbeatError(
                f"cannot create the heartbeat directory for {self.path}: {exc!r}"
            ) from exc

    @property
    def seq(self) -> int:
        """Beats published by THIS process so far. Zero before the first."""
        return self._seq

    def publish(self, positions_open: int) -> Heartbeat:
        """Publish one beat atomically. Returns exactly what was written.

        `positions_open` is the Limiter's own count and is published as a HINT.
        The seam's `Heartbeat` docstring is explicit that it is not authoritative
        and that the Sentinel must ask its own broker session instead — it is
        published anyway because an operator reading the file after the fact wants
        to know what the dead process believed it was holding.

        Atomic by `os.replace`, so a reader mid-write sees the previous whole
        record rather than a torn one. NOT fsynced — see the module docstring.
        """
        self._seq += 1
        beat = Heartbeat(
            pid=self.pid,
            ts=float(self._clock()),
            seq=self._seq,
            positions_open=int(positions_open),
        )
        payload = json.dumps(
            {
                "schema": HEARTBEAT_SCHEMA,
                "pid": beat.pid,
                "ts": beat.ts,
                "seq": beat.seq,
                "positions_open": beat.positions_open,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self._write_atomically(payload)
        return beat

    def _write_atomically(self, payload: str) -> None:
        """Write into a sibling temp file and `os.replace` it into place."""
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            os.write(fd, payload.encode("utf-8"))
            os.close(fd)
            os.chmod(tmp, _MODE)
            os.replace(tmp, self.path)
        except OSError as exc:
            # Best effort: a temp file left behind would accumulate one per beat.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise HeartbeatError(
                f"cannot publish the heartbeat to {self.path}: {exc!r}"
            ) from exc


# R0903 (too-few-public-methods): ONE public verb is the whole port. The
# frozen `HeartbeatPort` declares `read` and nothing else, and a second verb
# added to satisfy a counter would widen a surface whose narrowness is the
# §12.1:603 dependency-minimal argument.
# pylint: disable=too-few-public-methods
class HeartbeatFile:
    """The WATCHER's side. Satisfies the frozen `HeartbeatPort`. SYNCHRONOUS.

    Deliberately NOT a subclass of `HeartbeatPort`. A `Protocol`'s method bodies
    are docstrings, so a verb this class forgot to override would return `None`
    silently — and `None` is a MEANINGFUL value on this port ("never published"),
    so the forgetting would be invisible and would read as a healthy cold boot
    forever. `nixrisk/coldstart.py` records the same argument for the same reason;
    conformance is proven by comparing signatures, which is a measurement.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def read(self) -> Heartbeat | None:
        """The most recent beat, or `None` if none has ever been published.

        `None` for ABSENCE only. A file that exists and is not a heartbeat raises
        `HeartbeatError`: the seam's port declares that absence never raises and
        leaves an unreadable record to the implementation to signal, and signalling
        it is what lets the watchdog fail closed instead of mistaking corruption
        for a cold boot.
        """
        try:
            blob = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HeartbeatError(
                f"cannot read the heartbeat at {self.path}: {exc!r}"
            ) from exc
        if not blob.strip():
            # A zero-length file is the `os.replace` window on a filesystem that
            # allowed it, or a truncated create. It is not a record; it is also
            # not "never published", because something made the file.
            raise HeartbeatError(
                f"{self.path} is empty — that is a heartbeat that did not finish "
                "being written, not an absent one, and the two must not collapse"
            )
        # The SCHEMA is read on its own, before the fields, and that ordering is
        # the point rather than a style choice: a record from another build may
        # parse perfectly and mean something else, so the version has to be
        # settled before any field is given a meaning.
        raw = self._parsed(blob)
        schema = self._schema(raw)
        if schema != HEARTBEAT_SCHEMA:
            raise HeartbeatError(
                f"{self.path}: heartbeat schema {schema} != this build's "
                f"{HEARTBEAT_SCHEMA} — refusing to read fields into a meaning "
                "they may not have. The publisher and the watcher are "
                "different processes and may be different builds"
            )
        return self._fields(raw)

    def _unreadable(self, exc: Exception) -> HeartbeatError:
        """The one refusal every malformed-record path raises. One sentence, one
        place, so the three callers below cannot drift apart in what they say."""
        return HeartbeatError(
            f"{self.path} is not a heartbeat record ({exc!r}) — refusing to "
            "treat an unparsable beat as an absent one, because absence means "
            "the Limiter has never spoken and this file proves it has"
        )

    def _parsed(self, blob: bytes) -> object:
        """The bytes as JSON, or a refusal naming the file."""
        try:
            return json.loads(blob.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise self._unreadable(exc) from exc

    def _schema(self, raw: object) -> int:
        """The record's declared version, or a refusal."""
        try:
            return int(raw["schema"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError) as exc:
            raise self._unreadable(exc) from exc

    def _fields(self, raw: object) -> Heartbeat:
        """The four fields, once the version is known to be this build's."""
        try:
            return Heartbeat(
                pid=int(raw["pid"]),  # type: ignore[index]
                ts=float(raw["ts"]),  # type: ignore[index]
                seq=int(raw["seq"]),  # type: ignore[index]
                positions_open=int(raw["positions_open"]),  # type: ignore[index]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise self._unreadable(exc) from exc
