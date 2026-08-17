#!/usr/bin/env python3
"""§12.4's ladder, driven against a Postgres that really goes down.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.4 (*Degraded persistence
≠ degraded trading*), §12.9 (push alert tiers), §12.5 (HALT semantics), §9 (the
event-sourced write path), §12.10 (**Limiter sole writer, no new writers,
ever**). Schema: `databases/schema/plane1.sql`, frozen ARC 035 / Phase 0.4, and
`docs/nix_plane1_schema_spec.md` §2.2 for the ordering authority and the
exactly-once key. Subjects: `scripts/nixrisk/degraded.py`,
`scripts/nixrisk/wal.py`. Gate: `checks/check_plane1_degraded.py`.

§12.4, verbatim:

> Postgres outage: WAL buffers, trading continues, operator alerted.
> **Disk-critical** (WAL cannot append) ⇒ HALT new entries — no audit trail, no
> new risk. Open positions remain protected (stops read memory, not disk).

---

## §0a — WHAT WOULD HAVE TO BE TRUE FOR THIS DRILL TO MEASURE NOTHING

1. **POSTGRES NEVER GOES DOWN.** The outage already in this tree is
   `RecordingSink.fail_with = RuntimeError(...)` — a Python attribute, not a
   server. No socket is closed and nothing refuses a connection. *Closed:* this
   drill builds its **own ephemeral cluster** (`initdb`, `pg_ctl` on a private
   unix socket, `listen_addresses=''`) and stops it with **`-m immediate`**, and
   the arm banks the postmaster's PID, that PID's absence from `/proc`
   afterwards, the socket's absence, and the connect error psql really returned.

2. **THE OUTAGE IS A GRACEFUL SHUTDOWN.** This is the SIGKILL/fsync trap one
   layer up, and it is the vacuous claim this brief carries. `pg_ctl stop -m
   fast` checkpoints and flushes: *"no rows were lost"* across it is true **by
   construction** and measures nothing about durability. A SIGKILL of a `psql`
   CLIENT is worse — it never touches the server. *Closed:* `-m immediate` only,
   against a cluster started `synchronous_commit=on` and `fsync=on`, and the
   reconnect arm requires the restarted server to have **actually run recovery**
   ("database system was not properly shut down") before it will call the
   surviving rows evidence.

3. **"TRADING CONTINUES" IS `admits_new_entries() == True`.** That is one `if`
   over an enum. *Closed:* the continuation is driven through the real hot path
   while the server is down — `gate.GatePass.evaluate` returns APPROVE,
   `reservations.ReservationLedger` takes a reservation (which enqueues its own
   §12.10 row), and `stops.StopBook` ratchets a live stop.

4. **"OPEN STOPS STILL FIRE" IS `protective_exit_allowed()`.** That method is
   `return True, "..."` with no branch: it cannot answer False in any state, so
   an assertion over it is an assertion over a literal — the `CHECK-A7` shape
   (a classifier whose output is a constant decides nothing). *Closed:* the
   property is measured as a **real armed stop, breached by a real price tick,
   in the same process and the same instant that the WAL refuses every append**.
   The refusal is proven at that instant by a probe enqueue that raises
   `DiskCritical`.

5. **EVERYTHING IS DENIED, SO THE DISK-CRITICAL DENY PROVES NOTHING.** *Closed:*
   the C2 control — the identical child with `setrlimit` not called — must
   APPROVE the identical order. Plant and control differ in one syscall.

6. **THE FLUSH IS NEVER SHOWN A DUPLICATE.** A flush with no duplicate in it
   exercises no unique index. *Closed, both directions:* a plain re-INSERT of an
   already-committed row must come back **SQLSTATE 23505 naming the (natural_key,
   occurred_at) key** — the code alone is a shared namespace, and
   `plane1_positions_pkey` is a 23505 too — and a deliberate **re-delivery of a
   whole committed group through the real sink** must insert **0** rows and leave
   the log's row count unchanged.

7. **ORDERING IS ASSERTED FROM THE WRONG AUTHORITY.** `event_id` is assigned at
   INSERT and Postgres commit order under group-commit is *batch* order; either
   would "prove" ordering while proving that a sequence increments. *Closed:*
   the assertion joins back to the WAL — the `natural_key` sequence read out of
   Postgres `ORDER BY wal_seq` must equal the sequence `wal.recover()` reads off
   the WAL's own bytes.

---

## WHAT THIS DRILL DOES NOT TOUCH, AND CANNOT

**It never goes near the system cluster.** Three sibling agents, the operator's
`trade_history` analytics store and the production `nix_plane1` database live
there. Every `pg_ctl` call in this file carries `-D <this drill's tmpdir>/pg`,
the cluster it builds sets `listen_addresses=''` so it is unreachable by TCP,
and teardown is unconditional in a `finally`.

**It is not a power cut.** Postgres durability here is proven at `-m immediate` +
`synchronous_commit=on` + observed recovery; the local WAL's is proven by
`check_plane1_wal`'s observed `fsync` syscall. Neither drops the page cache.

**`PsqlCommitSink` is this drill's instrument, not the shipped sink.** It is a
`CommitSinkPort` over the `psql` binary, connecting as **`nix_limiter`** — the
Limiter's own role — at the end of the Limiter's own
`enqueue → WAL → writer → group-commit` path. It authors no row and adds no
writer (§12.10). A production sink lands separately; substituting it here is a
constructor argument.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import argparse
import dataclasses
import glob
import json
import os
import secrets
import shutil
import signal
import subprocess  # nosec B404 - psql/pg_ctl/initdb ARE the instruments (§9.1)
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))

# pylint: disable=wrong-import-position
from nixrisk.degraded import (
    NATURAL_KEY_FIELD,
    NO_TRADE,
    WAL_SEQ_FIELD,
    PersistenceHaltFlag,
    Plane1Enqueuer,
    instrumented_wal,
)
from nixrisk.gate import GatePass, default_manifest
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    EventKind,
    EventRow,
    FinancialPicture,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.stops import StopBook
from nixrisk.survival import Alert
from nixrisk.wal import DiskCritical, GroupCommitWriter, PersistenceState, recover

# The suppressions, argued once here rather than six times inline.
# * `too-many-lines`: this file is 60% PROSE — the §0a hazard list, the
#   never-touch-the-system-cluster note, and one argued comment per arm. The
#   alternative is a second module holding the reasoning apart from the code it
#   is about, which is how a rationale goes stale. `feed_kill_drill.py` and
#   `nixrisk/halt.py` make the same call for the same reason.
# * `too-many-instance-attributes`: `EphemeralCluster` carries four binary paths,
#   three paths, a running flag and a crash log; `_Session` carries the seven
#   objects of §9's write path plus §3's pass. Collapsing either into a dict
#   would trade a named attribute for a string key.
# * `too-few-public-methods`: `_Clear` and `_CollectingAlertSink` are one-verb
#   ports — the drill's ENVIRONMENT, not its subject.
# pylint: disable=too-many-lines,too-many-instance-attributes
# pylint: disable=too-few-public-methods

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Where Debian/Ubuntu keep `initdb` and `pg_ctl`. They are NOT on PATH (only
#: the client wrappers are), so the drill looks them up rather than assuming.
_PG_BIN_GLOB: Final[str] = "/usr/lib/postgresql/*/bin"

#: Trades driven BEFORE the outage. A floor, not a budget: below it "rows
#: committed before the crash survived it" is a statement about a small set.
TRADES_BEFORE = 6
#: Trades driven WHILE the server is down. Same reasoning for the backlog.
TRADES_DURING = 8
#: Bytes the disk-critical child may write before the KERNEL refuses. §12.4's
#: real failure, produced by `RLIMIT_FSIZE` + `SIGXFSZ` ignored + `EFBIG` — the
#: pattern `scripts/wal_kill_drill.py` established and this drill reuses.
FSIZE_LIMIT = 4096
#: Upper bound on the disk-critical child's append loop. The refusal is
#: measured, never assumed, so this only bounds the loop.
CRITICAL_ROWS = 4096

#: §3 knobs, at their §12A defaults. The gate is the SUBJECT of the "trading
#: continues" claim, so it runs with its shipped manifest and not a stub.
FRACTION = 0.70
SAFETY_PAD = 0.10
TOLERANCE = 1e-6

#: The stop the C2 arm arms, breaches, and requires to fire while the WAL is
#: refusing every append.
STOP_SYMBOL = "ES"
STOP_TICK = 0.25
STOP_FILL = 5000.0
STOP_TICKS = 40

_CLUSTER_TIMEOUT_S = 120.0
_PSQL_TIMEOUT_S = 120.0
_CHILD_TIMEOUT_S = 180.0

#: `EventKind` -> `plane1_event_enum`. **NOT `kind.value`**, and the difference
#: is a finding rather than a formatting detail: the code's `EventKind` and the
#: frozen schema's `plane1_event_enum` DO NOT AGREE. `cold_start` is the enum's
#: `cold_start_outcome`; the four strategy-death kinds are all the one inventory
#: row `strategy_lifecycle` (§12.10:757 lists register / force-deregister / kill
#: / relaunch / quarantine / restore as ONE row); and `boot` is in §12.10's
#: inventory at NO tier at all. A sink that inserted `row.kind.value` directly
#: would raise `invalid input value for enum` at group-commit time, in
#: production, for six of the twenty kinds.
EVENT_TYPE_MAP: Final[Mapping[EventKind, str]] = {
    EventKind.SIGNAL: "signal",
    EventKind.ACCEPTED: "accepted",
    EventKind.DENIED: "denied",
    EventKind.RESERVATION_TAKEN: "reservation_taken",
    EventKind.RESERVATION_RELEASED: "reservation_released",
    EventKind.PROTECTIVE_EXIT: "protective_exit",
    EventKind.EXIT_INTENT: "exit_intent",
    EventKind.CLOSED: "closed",
    EventKind.CANCEL: "cancel",
    EventKind.COLD_START: "cold_start_outcome",
    EventKind.HALT_SET: "halt_set",
    EventKind.HALT_CLEARED: "halt_cleared",
    EventKind.FORCE_DEREGISTER: "strategy_lifecycle",
    EventKind.KILL: "strategy_lifecycle",
    EventKind.RELAUNCH: "strategy_lifecycle",
    EventKind.QUARANTINE: "strategy_lifecycle",
}

#: Kinds with no §12.10 Plane-1 inventory row. Enumerated rather than left to
#: fall out of the map, so the gap is a declaration a reader can argue with.
#: `BOOT` is the whole set today: §12.10 routes the *cold-start OUTCOME* to
#: Plane 1 and routes a process start to Plane 2 only.
UNMAPPED_KINDS: Final[frozenset[EventKind]] = frozenset({EventKind.BOOT})


class ClusterUnavailable(RuntimeError):
    """The ephemeral cluster could not be built or reached — §17, never a PASS."""


class SinkUnavailable(RuntimeError):
    """The group-commit sink could not reach Postgres. §12.4's outage, for real."""


class UnmappedEventKind(RuntimeError):
    """A row whose `EventKind` has no §12.10 Plane-1 inventory row.

    Raised rather than dropped or coerced. Dropping loses a Plane-1 row, which is
    the worst failure this path can have; coercing invents an event type §12.10
    never authorised, which the schema gate's ARM 3 calls *an unaudited money
    event someone can write*.
    """


# ---------------------------------------------------------------------------
# The ephemeral cluster — MINE, on a private socket, and never the system one
# ---------------------------------------------------------------------------


def pg_bin(name: str) -> str | None:
    """Locate a server-side PostgreSQL binary. `None` when it is not installed."""
    direct = shutil.which(name)
    if direct is not None:
        return direct
    for folder in sorted(glob.glob(_PG_BIN_GLOB), reverse=True):
        candidate = Path(folder) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


class EphemeralCluster:
    """A throwaway PostgreSQL server this drill owns, crashes, and deletes.

    Every `pg_ctl` invocation names `-D self.datadir`, which is inside a
    `mkdtemp` this object made. `listen_addresses=''` means the server has no TCP
    socket at all and can only be reached through the unix socket in the same
    temporary directory, so there is no path by which a stray connection string
    reaches it or by which this object reaches anything else.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.datadir = root / "pg"
        self.logfile = root / "pg.log"
        self.socket_dir = root
        self._initdb = pg_bin("initdb")
        self._pg_ctl = pg_bin("pg_ctl")
        self._psql = shutil.which("psql")
        self._createdb = shutil.which("createdb")
        self.running = False
        self.crashes: list[dict[str, Any]] = []

    # -- availability ------------------------------------------------------

    def missing(self) -> tuple[str, ...]:
        """Binaries this drill needs and does not have. Empty means measurable."""
        return tuple(
            name
            for name, path in (
                ("initdb", self._initdb),
                ("pg_ctl", self._pg_ctl),
                ("psql", self._psql),
                ("createdb", self._createdb),
            )
            if path is None
        )

    # -- lifecycle ---------------------------------------------------------

    def create(self) -> None:
        """`initdb` into my own datadir. Trust auth on a socket only I can see."""
        assert self._initdb is not None  # nosec B101 - guarded by missing()
        proc = self._run(
            [
                self._initdb,
                "-D",
                str(self.datadir),
                "-A",
                "trust",
                "-U",
                _superuser(),
                "-E",
                "UTF8",
            ]
        )
        if proc.returncode != 0:
            raise ClusterUnavailable(f"initdb failed: {proc.stderr[-500:]}")

    def start(self, tag: str) -> None:
        """Start the postmaster and WAIT for it. `synchronous_commit=on`, `fsync=on`.

        `tag` names this boot's OWN log file. Per-boot rather than appended,
        because `recovered()` greps that log for the recovery banner: with one
        shared log, the banner from the FIRST crash would still be there after a
        clean restart and the control that requires its ABSENCE could never fail.

        Both are stated explicitly rather than left to the build default, because
        the whole of C3's "no rows lost" rests on them: an asynchronous commit
        acknowledges a transaction the WAL has not yet flushed, and a
        `-m immediate` crash would then legitimately lose it. A drill that lost
        rows for that reason would look like a defect in the code under test.
        """
        assert self._pg_ctl is not None  # nosec B101 - guarded by missing()
        self.logfile = self.root / f"pg-{tag}.log"
        proc = self._run(
            [
                self._pg_ctl,
                "-D",
                str(self.datadir),
                "-o",
                (
                    f"-k {self.socket_dir} -c listen_addresses='' "
                    "-c synchronous_commit=on -c fsync=on"
                ),
                "-l",
                str(self.logfile),
                "-w",
                "start",
            ]
        )
        if proc.returncode != 0:
            raise ClusterUnavailable(
                f"pg_ctl start failed: {proc.stderr[-300:]} / log: "
                f"{self.log_text()[-500:]}"
            )
        self.running = True

    def postmaster_pid(self) -> int:
        """The live postmaster's PID, from its own pidfile. Never inferred."""
        pidfile = self.datadir / "postmaster.pid"
        try:
            return int(pidfile.read_text(encoding="utf-8").splitlines()[0])
        except (OSError, IndexError, ValueError) as exc:
            raise ClusterUnavailable(f"cannot read {pidfile}: {exc!r}") from exc

    def crash(self) -> dict[str, Any]:
        """THE OUTAGE. `pg_ctl stop -m immediate` — a real crash of a real server.

        Not `-m fast`: a graceful shutdown checkpoints and flushes, so "nothing
        was lost" across it is true by construction and measures nothing. The
        evidence returned is what makes the outage falsifiable — the PID before,
        that PID's absence from `/proc` after, the socket's absence, and the
        error psql actually got when it tried to connect.
        """
        return self._stop("immediate")

    def graceful_stop(self) -> dict[str, Any]:
        """THE CONTROL for `crash()`: `-m fast`, a courteous shutdown.

        Exists so that "the restarted server ran recovery" is a DISCRIMINATING
        assertion. A graceful stop checkpoints, so the next boot prints no
        recovery banner; without this arm, `recovered()` could be a matcher that
        matches anything and nobody would know.
        """
        return self._stop("fast")

    def _stop(self, mode: str) -> dict[str, Any]:
        assert self._pg_ctl is not None  # nosec B101 - guarded by missing()
        pid = self.postmaster_pid()
        socket_path = self.socket_dir / ".s.PGSQL.5432"
        proc = self._run(
            [self._pg_ctl, "-D", str(self.datadir), "-m", mode, "-w", "stop"]
        )
        self.running = False
        rc, _out, err = self.psql("postgres", "select 1")
        evidence = {
            "mode": mode,
            "postmaster_pid": pid,
            "pg_ctl_returncode": proc.returncode,
            "pid_alive_after_stop": Path(f"/proc/{pid}").exists(),
            "socket_present_after_stop": socket_path.exists(),
            "connect_returncode": rc,
            "connect_stderr": err[-300:],
            "datadir_filesystem": _filesystem_of(self.datadir),
        }
        self.crashes.append(evidence)
        return evidence

    def destroy(self) -> None:
        """Stop (immediately) and remove. Safe to call twice, safe after a crash."""
        if self._pg_ctl is not None and self.datadir.exists():
            self._run(
                [self._pg_ctl, "-D", str(self.datadir), "-m", "immediate", "-w", "stop"]
            )
        self.running = False
        remove_tree(self.root)

    def log_text(self) -> str:
        """The server's own log. Where recovery announces itself."""
        try:
            return self.logfile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def recovered(self) -> bool:
        """Did the restarted server really run crash recovery?

        Without this, a `-m immediate` that happened to follow a checkpoint would
        be indistinguishable from a clean stop, and C3's durability claim would
        rest on a shutdown mode rather than on an observed recovery.
        """
        return "was not properly shut down" in self.log_text()

    # -- SQL ---------------------------------------------------------------

    def createdb(self, name: str) -> None:
        """Create one scratch database. Named with this agent's `p1c_` prefix."""
        assert self._createdb is not None  # nosec B101 - guarded by missing()
        proc = self._run([self._createdb, "-h", str(self.socket_dir), name])
        if proc.returncode != 0:
            raise ClusterUnavailable(f"createdb {name}: {proc.stderr[-300:]}")

    def load(self, dbname: str, sql_path: Path) -> None:
        """Load the SHIPPED `databases/schema/plane1.sql`. Never a copy of it."""
        assert self._psql is not None  # nosec B101 - guarded by missing()
        proc = self._run(
            [
                self._psql,
                "-h",
                str(self.socket_dir),
                "-d",
                dbname,
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(sql_path),
            ]
        )
        if proc.returncode != 0:
            raise ClusterUnavailable(f"load {sql_path.name}: {proc.stderr[-500:]}")

    def psql(
        self, dbname: str, sql: str, *, verbose: bool = False
    ) -> tuple[int, str, str]:
        """One SQL string. `(rc, stdout, stderr)`; NEVER raises on a SQL error.

        `verbose` turns on psql's VERBOSITY so the SQLSTATE appears in stderr.
        A message is prose; a SQLSTATE is a contract (check contract §18).
        """
        if self._psql is None:
            return 127, "", "psql is not on PATH"
        argv = [
            self._psql,
            "-h",
            str(self.socket_dir),
            "-d",
            dbname,
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
        ]
        if verbose:
            argv += ["-v", "VERBOSITY=verbose"]
        proc = self._run(argv, stdin_text=sql)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def scalar(self, dbname: str, sql: str) -> str:
        """A SELECT that must succeed. Anything else is a measurement failure."""
        rc, out, err = self.psql(dbname, sql)
        if rc != 0:
            raise ClusterUnavailable(f"{sql[:60]}: rc={rc} {err[-300:]}")
        return out

    @staticmethod
    def _run(
        argv: Sequence[str], *, stdin_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.pop("PGHOST", None)
        env.pop("PGPORT", None)
        env.pop("PGDATABASE", None)
        env["PGCONNECT_TIMEOUT"] = "5"
        return subprocess.run(  # nosec B603 - argv built here, no shell
            list(argv),
            input=stdin_text if stdin_text is not None else "",
            capture_output=True,
            text=True,
            timeout=max(_CLUSTER_TIMEOUT_S, _PSQL_TIMEOUT_S),
            check=False,
            env=env,
        )


def remove_tree(root: Path) -> None:
    """Recursive delete by ABSOLUTE path — never `shutil.rmtree`.

    On POSIX `shutil.rmtree` unlinks through a directory descriptor with a bare
    relative name, which the resource observer records as an unattributable
    `file-write:base.wal` that no rooted `file-write:/tmp` declaration can cover.
    `check_plane1_wal` learned this and named it in its RESOURCES note; this is
    the same removal, made recursive because an `initdb` datadir is deep.
    """
    if not root.exists():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.is_symlink():
            remove_tree(child)
        else:
            try:
                child.unlink()
            except OSError:
                continue
    try:
        root.rmdir()
    except OSError:
        pass


def _filesystem_of(path: Path) -> str:
    """The fstype the datadir really lives on. Reported, never assumed.

    Load-bearing for how far the durability claim reaches. On a **tmpfs** an
    `fsync` is a no-op, so `-m immediate` proves the postmaster died and its
    shared buffers were lost and crash recovery replayed the WAL — and proves
    NOTHING about a power cut, because the bytes never had to reach a platter.
    That is the honest scope of every "no rows lost" figure this drill produces,
    and printing the fstype is what keeps it honest rather than implied.
    """
    target = str(path.resolve())
    best = ("", "unknown")
    try:
        for line in Path("/proc/self/mounts").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            mount, fstype = parts[1], parts[2]
            inside = target == mount or target.startswith(mount.rstrip("/") + "/")
            if inside and len(mount) >= len(best[0]):
                best = (mount, fstype)
    except OSError:
        return "unknown"
    return best[1]


def _superuser() -> str:
    """The bootstrap superuser for MY cluster: whoever is running the drill."""
    return os.environ.get("USER") or os.environ.get("LOGNAME") or "postgres"


# ---------------------------------------------------------------------------
# The sink — §9's group-commit half, over a real database, as `nix_limiter`
# ---------------------------------------------------------------------------


def _row_json(row: EventRow) -> dict[str, Any]:
    """One `EventRow` -> the JSON object the INSERT reads.

    `wal_seq` and `natural_key` are read OUT of the row, never minted here. A
    sink that minted either would give a re-delivered record a different key,
    the unique index would never fire, and exactly-once would be structurally
    impossible while every test looked fine (schema spec §2.2).
    """
    kind = row.kind
    if kind in UNMAPPED_KINDS or kind not in EVENT_TYPE_MAP:
        raise UnmappedEventKind(
            f"EventKind.{kind.name} has no §12.10 Plane-1 inventory row, so "
            f"there is no plane1_event_enum member to write it as. Refused "
            f"rather than dropped (a lost Plane-1 row is unrecoverable) and "
            f"rather than coerced (an event type §12.10 never authorised is an "
            f"unaudited money event someone can write)"
        )
    fields = dict(row.fields)
    if WAL_SEQ_FIELD not in fields or NATURAL_KEY_FIELD not in fields:
        raise UnmappedEventKind(
            f"row {kind.name} carries no {WAL_SEQ_FIELD}/{NATURAL_KEY_FIELD}: "
            f"{sorted(fields)}. Ordering is authoritative from the WAL sequence "
            f"and exactly-once rides on the natural key; a row with neither can "
            f"be neither ordered nor deduplicated. Stamp it at enqueue "
            f"(nixrisk.degraded.Plane1Enqueuer)"
        )
    return {
        "ts": row.ts,
        "event_type": EVENT_TYPE_MAP[kind],
        "strategy_id": row.strategy_id or NO_TRADE,
        "trade_id": row.trade_id or NO_TRADE,
        "reason": row.reason or NO_TRADE,
        "symbol": fields.get("symbol", ""),
        "wal_seq": int(fields[WAL_SEQ_FIELD]),
        "natural_key": fields[NATURAL_KEY_FIELD],
        "payload": fields,
    }


_INSERT_SQL: Final[str] = """
BEGIN;
SET ROLE nix_limiter;
WITH ins AS (
    INSERT INTO plane1_event_log
        (occurred_at, event_type, strategy_id, trade_id, reason, symbol,
         wal_seq, natural_key, payload)
    SELECT to_timestamp((r->>'ts')::double precision),
           (r->>'event_type')::plane1_event_enum,
           r->>'strategy_id', r->>'trade_id', r->>'reason',
           nullif(r->>'symbol', ''),
           (r->>'wal_seq')::bigint, r->>'natural_key', r->'payload'
      FROM jsonb_array_elements({batch}::jsonb) AS r
     ORDER BY (r->>'wal_seq')::bigint
    {conflict}
    RETURNING 1
)
SELECT count(*) FROM ins;
COMMIT;
"""


def _dollar_quote(text: str) -> str:
    """Dollar-quote a literal. No escaping, therefore no escaping BUG.

    The tag is random and asserted absent from the payload, so there is no string
    a caller can supply that closes the quote. This is why nothing in this file
    hand-escapes a quote character.
    """
    for _ in range(8):
        tag = f"$p1c{secrets.token_hex(6)}$"
        if tag not in text:
            return f"{tag}{text}{tag}"
    raise RuntimeError("could not find a dollar-quote tag absent from the payload")


class PsqlCommitSink:
    """§9's group-commit sink over `psql`, as `nix_limiter`. Not a second writer.

    `commit` is ONE transaction for the whole group — that is what "group commit"
    means, and a per-row transaction would make a partial group possible, which
    is a torn batch in the durable record.

    `ON CONFLICT (natural_key, occurred_at) DO NOTHING` is the reconnect heal:
    a re-delivered buffered group inserts the rows Postgres has not seen and
    silently absorbs the ones it has. The *mechanism* underneath — that the index
    really refuses a duplicate — is proven separately by `probe_duplicate`, with
    a plain INSERT and an asserted SQLSTATE, because `DO NOTHING` is
    indistinguishable from a table with no unique index at all.
    """

    def __init__(self, cluster: EphemeralCluster, dbname: str) -> None:
        self._cluster = cluster
        self._dbname = dbname
        self.groups = 0
        self.rows_offered = 0
        self.rows_inserted = 0
        self.failures = 0
        self.last_error = ""

    def commit(self, rows: Sequence[EventRow]) -> int:
        """Persist a GROUP in one transaction. Returns rows actually inserted."""
        if not rows:
            return 0
        payload = json.dumps([_row_json(row) for row in rows], separators=(",", ":"))
        sql = _INSERT_SQL.format(
            batch=_dollar_quote(payload),
            conflict="ON CONFLICT (natural_key, occurred_at) DO NOTHING",
        )
        rc, out, err = self._cluster.psql(self._dbname, sql, verbose=True)
        self.rows_offered += len(rows)
        if rc != 0:
            self.failures += 1
            self.last_error = err[-300:]
            raise SinkUnavailable(f"group-commit refused (rc={rc}): {err[-300:]}")
        self.groups += 1
        inserted = int(out.splitlines()[-1]) if out else 0
        self.rows_inserted += inserted
        return inserted

    def redeliver(self, rows: Sequence[EventRow]) -> int:
        """THE PLANTED DUPLICATE, through the real flush path. Must insert 0."""
        return self.commit(rows)

    def probe_duplicate(self, row: EventRow) -> dict[str, Any]:
        """Re-insert ONE committed row with a PLAIN insert. Must be refused.

        Rolled back, so the probe adds nothing whatever the answer. `DO NOTHING`
        is deliberately absent here: with it, a table carrying no unique index at
        all would return the same silent success, and the whole exactly-once
        claim would rest on a clause rather than on an index.
        """
        payload = json.dumps([_row_json(row)], separators=(",", ":"))
        sql = _INSERT_SQL.format(batch=_dollar_quote(payload), conflict="").replace(
            "COMMIT;", "ROLLBACK;"
        )
        rc, out, err = self._cluster.psql(self._dbname, sql, verbose=True)
        return {
            "returncode": rc,
            "stdout": out,
            "sqlstate": _sqlstate(err),
            "stderr": err[-600:],
            "natural_key": row.fields[NATURAL_KEY_FIELD],
        }


#: `insufficient_privilege` is 42501; `unique_violation` is 23505. The code alone
#: is never the assertion — `plane1_positions_pkey` is a 23505 too — so the arm
#: also requires the DETAIL line naming the (natural_key, occurred_at) key.
SQLSTATE_UNIQUE_VIOLATION: Final[str] = "23505"


def _sqlstate(stderr: str) -> str:
    """psql under VERBOSITY=verbose prints `ERROR:  <sqlstate>: <message>`."""
    for line in stderr.splitlines():
        head, sep, rest = line.partition(":")
        if head.strip() in {"ERROR", "FATAL", "PANIC"} and sep:
            code = rest.strip().split(":", 1)[0].strip()
            if len(code) == 5 and code[0].isdigit():
                return code
    return ""


# ---------------------------------------------------------------------------
# The trading environment the continuation claim is measured against
# ---------------------------------------------------------------------------


class _Clear:
    """Every §11.1-shaped port, clear. The gate's environment, not its subject.

    The claim under measurement is *"the Limiter keeps gating while Postgres is
    down"*, so every OTHER reason to deny is held clear and the persistence halt
    flag is the only thing that can move. A port that blocked would make an
    approval impossible and a denial unattributable.
    """

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        """`(blocked, reason)` — never blocked."""
        del symbol
        return False, ""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)` — never locked."""
        del strategy_id
        return False, ""

    def mark(self) -> tuple[float, bool]:
        """§6.5's net-liq mark: healthy and fresh."""
        return 10_000_000.0, True


class _CollectingAlertSink:
    """A §12.9 `AlertSink` that keeps what it was given. The transport is not ours."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def emit(self, alert: Alert) -> None:
        """Keep one alert."""
        self.alerts.append(alert)


def _order(index: int, qty: int = 4) -> ProposedOrder:
    """One well-formed §3 proposal. Distinct client_order_id per trade."""
    return ProposedOrder(
        client_order_id=f"p1c-{index:04d}",
        strategy_id="degraded-drill",
        symbol=STOP_SYMBOL,
        side=Side.LONG,
        qty=qty,
        margin_per_contract=1000.0,
        stop_ticks=STOP_TICKS,
        stop_mode=StopMode.FIXED,
        signal_ts=float(index),
    )


def _picture(reserved: float) -> FinancialPicture:
    """One §3 snapshot, self-consistent, with Σ reservations carried forward."""
    return FinancialPicture(
        version=1,
        published_ts=1.0,
        balance=1_000_000.0,
        positions=(),
        margin_per_contract={STOP_SYMBOL: 1000.0},
        sum_open_margin=0.0,
        sum_reservations=reserved,
        committed=reserved,
        deployable=500_000.0,
    )


def _manifest() -> tuple[Any, ...]:
    """§3's SHIPPED rule set, at its §12A defaults."""
    clear = _Clear()
    return default_manifest(
        blackout=clear,
        tradability=clear,
        staleness=clear,
        clock_skew=clear,
        in_flight=clear,
        net_liq=clear,
        deployable_fraction=FRACTION,
        survival_safety_pad=SAFETY_PAD,
        coherence_tolerance=TOLERANCE,
    )


def _alert_json(alert: Alert) -> dict[str, Any]:
    return {
        "tier": alert.tier.value,
        "event": alert.event,
        "detail": alert.detail[:200],
        "snapshot": dict(alert.snapshot),
    }


# ---------------------------------------------------------------------------
# C1 + C3 — one cluster, one WAL, one continuous trading session
# ---------------------------------------------------------------------------


class _Session:
    """The Limiter's §9 write path plus §3's pass, over one WAL and one sink."""

    def __init__(self, root: Path, cluster: EphemeralCluster, dbname: str) -> None:
        self.sink_alerts = _CollectingAlertSink()
        self.wal_path = root / "plane1.wal"
        self.wal, self.alerts = instrumented_wal(str(self.wal_path), self.sink_alerts)
        self.enqueuer = Plane1Enqueuer(self.wal)
        self.sink = PsqlCommitSink(cluster, dbname)
        self.writer = GroupCommitWriter(self.wal, self.sink)
        self.alerts.bind(self.wal, backlog=self.writer.backlog)
        self.ledger = ReservationLedger(self.enqueuer)
        # Through `enqueuer.wal`, not `self.wal`: the halt flag must read the
        # SAME WAL the enqueuer writes to, and going through the decorator's own
        # accessor is what makes that structural instead of coincidental.
        self.gate = GatePass(
            PersistenceHaltFlag(self.enqueuer.wal), list(_manifest()), self.ledger
        )
        self.book = StopBook({STOP_SYMBOL: STOP_TICK})
        self.index = 0

    def trade(self, count: int) -> list[dict[str, Any]]:
        """Drive `count` proposals through §3's real pass. Returns each verdict."""
        outcomes: list[dict[str, Any]] = []
        for _ in range(count):
            self.index += 1
            order = _order(self.index)
            self.enqueuer.enqueue(
                EventRow(
                    kind=EventKind.SIGNAL,
                    ts=time.time(),
                    strategy_id=order.strategy_id,
                    reason="strategy proposal reached the Limiter",
                    trade_id=order.client_order_id,
                    fields={"symbol": order.symbol},
                )
            )
            outcome = self.gate.evaluate(
                order, _picture(self.ledger.total_reserved()), time.time()
            )
            outcomes.append(
                {
                    "client_order_id": order.client_order_id,
                    "decision": outcome.decision.value,
                    "rule": outcome.rule,
                    "reason": outcome.reason[:160],
                }
            )
        return outcomes

    def drain_all(self, limit: int = 64) -> list[dict[str, Any]]:
        """Group-commit until the backlog is empty or the sink refuses."""
        results: list[dict[str, Any]] = []
        for _ in range(limit):
            before = self.writer.backlog()
            if before == 0:
                break
            result = self.writer.drain_once()
            results.append(
                {
                    "committed": result.committed,
                    "backlog": result.backlog,
                    "state": result.state.value,
                    "error": result.error[:200],
                }
            )
            if result.error or result.committed == 0:
                break
        return results

    def wal_order(self) -> list[str]:
        """The natural keys in the WAL's own byte order — the ordering AUTHORITY."""
        return [
            row.fields[NATURAL_KEY_FIELD]
            for row in recover(self.wal_path, self.wal.durable_bytes).rows
        ]


def arm_c1_outage(  # pylint: disable=too-many-locals
    session: _Session, cluster: EphemeralCluster, dbname: str
) -> dict[str, Any]:
    """C1: Postgres really goes down mid-trade; the Limiter keeps trading."""
    before = session.trade(TRADES_BEFORE)
    session.wal.sync_to_disk()
    session.drain_all()
    committed_before = int(
        cluster.scalar(dbname, "select count(*) from plane1_event_log")
    )
    # The open position exists BEFORE the outage. A stop armed after it would be
    # a different claim — §12.4 protects the book that already exists. TRAILING,
    # so that `maintain` has something to move: a FIXED stop never ratchets, and
    # "the stop machinery is still live" would then be a claim about a method
    # that correctly did nothing.
    armed = session.book.arm(
        STOP_FILL,
        dataclasses.replace(_order(9001), stop_mode=StopMode.TRAILING),
        trail_ticks=STOP_TICKS,
    )

    crash = cluster.crash()

    during = session.trade(TRADES_DURING)
    session.wal.sync_to_disk()
    drains = session.drain_all()
    admits, admit_reason = session.wal.admits_new_entries()

    # ...and it is still RATCHETED and still BREACHED, from MEMORY, with the
    # server gone. `stops read memory, not disk` measured as movement and a
    # trigger, not as a method that returns an unconditional True.
    ratcheted = session.book.maintain(STOP_SYMBOL, STOP_FILL + 5.0)
    live = session.book.get(armed.client_order_id)
    breached_during_outage = session.book.breached(
        STOP_SYMBOL, (live.level if live else armed.level) - STOP_TICK
    )

    # And the gate is STILL asked, AFTER the WAL has learned the sink is down.
    after_degraded = session.trade(2)

    warnings = [
        _alert_json(a)
        for a in session.sink_alerts.alerts
        if a.event == "wal_sink_degraded"
    ]
    return {
        "arm": "c1_outage",
        "database": dbname,
        "crash": crash,
        "rows_committed_before_outage": committed_before,
        "decisions_before": before,
        "decisions_during_outage": during,
        "decisions_after_state_degraded": after_degraded,
        "drains_during_outage": drains,
        "state_during_outage": session.wal.state.value,
        "expected_state": PersistenceState.SINK_DEGRADED.value,
        "backlog_during_outage": session.writer.backlog(),
        "rows_enqueued_not_yet_durable": session.enqueuer.pending(),
        "admits_new_entries": admits,
        "admit_reason": admit_reason,
        "stop_armed_level": armed.level,
        "stop_ratcheted": len(ratcheted),
        "stop_level_after_ratchet": live.level if live else armed.level,
        "stop_breached_during_outage": [
            s.client_order_id for s in breached_during_outage
        ],
        "reservations_outstanding": len(session.ledger.outstanding()),
        "sum_reserved": session.ledger.total_reserved(),
        "warning_alerts": warnings,
        "all_alerts": [_alert_json(a) for a in session.sink_alerts.alerts],
    }


def arm_c3_reconnect(  # pylint: disable=too-many-locals
    session: _Session, cluster: EphemeralCluster, dbname: str, committed_before: int
) -> dict[str, Any]:
    """C3: the server comes back; the backlog flushes in order, exactly once."""
    cluster.start("recover")
    recovery_observed = cluster.recovered()
    recovery_log = cluster.log_text()[-600:]
    survived = int(cluster.scalar(dbname, "select count(*) from plane1_event_log"))

    # Everything still buffered becomes durable before the flush, so the order
    # comparison below covers every row rather than a prefix of them.
    session.wal.sync_to_disk()
    drains = session.drain_all()
    total = int(cluster.scalar(dbname, "select count(*) from plane1_event_log"))

    in_pg = cluster.scalar(
        dbname, "select natural_key from plane1_event_log order by wal_seq"
    ).splitlines()
    in_wal = session.wal_order()
    seqs = [
        int(v)
        for v in cluster.scalar(
            dbname, "select wal_seq from plane1_event_log order by wal_seq"
        ).splitlines()
    ]
    monotone_with_event_id = cluster.scalar(
        dbname,
        "select bool_and(ok) from (select wal_seq >= lag(wal_seq) over "
        "(order by event_id) as ok from plane1_event_log) t",
    )

    # THE PLANTED DUPLICATE, twice over.
    committed_rows = recover(session.wal_path, session.wal.durable_bytes).rows
    replayed = list(committed_rows[: min(4, len(committed_rows))])
    redelivered = session.sink.redeliver(replayed)
    after_redelivery = int(
        cluster.scalar(dbname, "select count(*) from plane1_event_log")
    )
    probe = session.sink.probe_duplicate(replayed[0]) if replayed else {}
    after_probe = int(cluster.scalar(dbname, "select count(*) from plane1_event_log"))

    # THE CONTROL for "recovery was observed": a COURTEOUS stop, whose next boot
    # must print no recovery banner at all.
    graceful = cluster.graceful_stop()
    cluster.start("clean")
    graceful["recovery_observed_after_graceful_stop"] = cluster.recovered()

    restored = [
        _alert_json(a)
        for a in session.sink_alerts.alerts
        if a.event == "wal_sink_restored"
    ]
    return {
        "arm": "c3_reconnect",
        "recovery_observed": recovery_observed,
        "graceful_control": graceful,
        "server_log_tail": recovery_log,
        "rows_committed_before_outage": committed_before,
        "rows_surviving_the_crash": survived,
        "drains_after_reconnect": drains,
        "rows_after_flush": total,
        "state_after_reconnect": session.wal.state.value,
        "backlog_after_flush": session.writer.backlog(),
        "durable_wal_rows": len(committed_rows),
        "next_wal_seq": session.enqueuer.next_seq,
        "order_in_postgres": in_pg,
        "order_in_wal": in_wal,
        "order_matches_wal": in_pg == in_wal,
        "wal_seq_contiguous": seqs == list(range(len(seqs))),
        "wal_seq_monotone_with_event_id": monotone_with_event_id,
        "duplicate_rows_offered": len(replayed),
        "duplicate_rows_inserted": redelivered,
        "rows_after_redelivery": after_redelivery,
        "duplicate_probe": probe,
        "rows_after_probe": after_probe,
        "sink_rows_offered": session.sink.rows_offered,
        "sink_rows_inserted": session.sink.rows_inserted,
        "restored_alerts": restored,
    }


# ---------------------------------------------------------------------------
# C2 — the child that makes the KERNEL refuse the append
# ---------------------------------------------------------------------------


def _announce(**fields: Any) -> None:
    """One JSON line, flushed. The parent learns the outcome from the CHILD."""
    print(json.dumps({"pid": os.getpid(), **fields}, default=str), flush=True)


def _critical_child(path: Path, *, rlimit: bool) -> int:  # pylint: disable=too-many-locals
    """§12.4's halting branch and its control, in one child. `rlimit` is the plant.

    With `rlimit` set, the KERNEL refuses the append with `EFBIG` and the WAL
    latches DISK_CRITICAL. Without it, everything else is identical — which is
    what makes the deny attributable to the disk and not to a gate that denies
    everything.
    """
    if rlimit:
        import resource  # pylint: disable=import-outside-toplevel

        # SIGXFSZ's default action is to kill. Ignored so the write RETURNS
        # EFBIG and the process is still alive to report it — which is §12.4's
        # condition: the WAL cannot append and the Limiter must say so.
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_LIMIT, FSIZE_LIMIT))

    sink_alerts = _CollectingAlertSink()
    wal, alerts = instrumented_wal(str(path), sink_alerts)
    del alerts
    enqueuer = Plane1Enqueuer(wal)
    ledger = ReservationLedger(enqueuer)
    book = StopBook({STOP_SYMBOL: STOP_TICK})
    gate = GatePass(PersistenceHaltFlag(wal), list(_manifest()), ledger)

    # THE OPEN POSITION, armed BEFORE anything fails. §12.4 protects the book
    # that already exists; a stop armed after the failure would be a different
    # claim.
    armed = book.arm(STOP_FILL, _order(1))

    accepted = 0
    refusal = ""
    for index in range(CRITICAL_ROWS):
        try:
            enqueuer.enqueue(
                EventRow(
                    kind=EventKind.SIGNAL,
                    ts=time.time(),
                    strategy_id="degraded-drill",
                    reason=f"filling the WAL, row {index}",
                    trade_id=f"p1c-fill-{index:05d}",
                    fields={"symbol": STOP_SYMBOL},
                )
            )
        except DiskCritical as exc:
            refusal = str(exc)
            break
        accepted += 1

    # HALF ONE: a NEW ENTRY, through §3's real pass, with the persistence halt
    # flag as its HaltFlagPort.
    outcome = gate.evaluate(_order(2), _picture(ledger.total_reserved()), time.time())

    # HALF TWO, in the SAME instant: the WAL still refuses every append...
    probe_raised = ""
    try:
        enqueuer.enqueue(
            EventRow(
                kind=EventKind.SIGNAL,
                ts=time.time(),
                strategy_id="degraded-drill",
                reason="probe: is the WAL still refusing right now?",
                trade_id="p1c-probe",
                fields={"symbol": STOP_SYMBOL},
            )
        )
    except DiskCritical as exc:
        probe_raised = type(exc).__name__

    # ...and the armed stop is nonetheless BREACHED and returned. This is the
    # measured form of "open positions remain protected (stops read memory, not
    # disk)" — not `protective_exit_allowed()`, which is an unconditional True.
    breach_price = armed.level - STOP_TICK
    breached = book.breached(STOP_SYMBOL, breach_price)
    admits, admit_reason = wal.admits_new_entries()

    _announce(
        arm="c2_critical" if rlimit else "c2_control",
        rlimit=rlimit,
        path=str(path),
        accepted=accepted,
        refusal=refusal[:300],
        state=wal.state.value,
        admits_new_entries=admits,
        admit_reason=admit_reason[:200],
        gate_decision=outcome.decision.value,
        gate_rule=outcome.rule,
        gate_reason=outcome.reason[:300],
        reservations_taken=len(ledger.outstanding()),
        armed_level=armed.level,
        breach_price=breach_price,
        breached_ids=[state.client_order_id for state in breached],
        breached_levels=[state.level for state in breached],
        append_probe_raised=probe_raised,
        alerts=[_alert_json(a) for a in sink_alerts.alerts],
    )
    return 0


def arm_c2(root: Path, *, rlimit: bool) -> dict[str, Any]:
    """Run one C2 child and report what it announced. Never in-process.

    In a child because `RLIMIT_FSIZE` is a per-process limit and setting it in
    the drill would cap every later file the drill writes, including the
    ephemeral cluster's.
    """
    path = root / ("critical.wal" if rlimit else "control.wal")
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--critical-child",
        "--path",
        str(path),
    ]
    if rlimit:
        argv.append("--rlimit")
    proc = subprocess.run(  # nosec B603 - argv built here, no shell
        argv, capture_output=True, text=True, timeout=_CHILD_TIMEOUT_S, check=False
    )
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if not line:
        raise ClusterUnavailable(
            f"C2 child printed no announcement (rc={proc.returncode}): "
            f"{proc.stderr[-400:]}"
        )
    return {"reap_status": proc.returncode, **json.loads(line)}


# ---------------------------------------------------------------------------
# The whole drill
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """`/home/bbt/nix` in the primary tree; the worktree root in a worktree."""
    return Path(__file__).resolve().parent.parent


def run_drill(root: Path) -> dict[str, Any]:
    """Every arm, once. The check reads this dict and never re-derives it."""
    root.mkdir(parents=True, exist_ok=True)
    schema = repo_root() / "databases" / "schema" / "plane1.sql"
    cluster = EphemeralCluster(root / "cluster")
    missing = cluster.missing()
    if missing:
        return {
            "nonce": f"ARC035C-{secrets.token_hex(6)}",
            "root": str(root),
            "available": False,
            "reason": (
                f"missing PostgreSQL binaries {list(missing)} — a degraded-"
                f"persistence property proven while no server can be built is "
                f"not proven (§17)"
            ),
        }
    if not schema.is_file():
        return {
            "nonce": f"ARC035C-{secrets.token_hex(6)}",
            "root": str(root),
            "available": False,
            "reason": f"the frozen schema {schema} is absent; nothing to load",
        }
    dbname = f"p1c_degraded_{secrets.token_hex(4)}"
    try:
        cluster.root.mkdir(parents=True, exist_ok=True)
        cluster.create()
        cluster.start("boot")
        cluster.createdb(dbname)
        cluster.load(dbname, schema)
        session = _Session(root, cluster, dbname)
        c1 = arm_c1_outage(session, cluster, dbname)
        c3 = arm_c3_reconnect(
            session, cluster, dbname, c1["rows_committed_before_outage"]
        )
        session.wal.close()
    finally:
        cluster.destroy()
    return {
        "nonce": f"ARC035C-{secrets.token_hex(6)}",
        "root": str(root),
        "available": True,
        "database": dbname,
        "postgres_version": _pg_version(),
        "c1": c1,
        "c3": c3,
        "c2_critical": arm_c2(root, rlimit=True),
        "c2_control": arm_c2(root, rlimit=False),
    }


def _pg_version() -> str:
    binary = pg_bin("postgres")
    if binary is None:
        return "unknown"
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "--version"], capture_output=True, text=True, timeout=30, check=False
    )
    return proc.stdout.strip() or proc.stderr.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ARC 035 §12.4 degraded-persistence drill"
    )
    parser.add_argument("--critical-child", action="store_true", help="child mode")
    parser.add_argument("--rlimit", action="store_true", help="child: RLIMIT_FSIZE")
    parser.add_argument("--path", type=Path, help="WAL path (child mode)")
    parser.add_argument("--root", type=Path, help="scratch root (parent mode)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the C2 child, or the whole drill and print it as JSON."""
    args = _parser().parse_args(argv)
    if args.critical_child:
        if args.path is None:
            raise SystemExit("--path is required in child mode")
        return _critical_child(args.path, rlimit=args.rlimit)
    root = args.root or Path(os.environ.get("TMPDIR", "/tmp")) / "nixp1c"  # nosec B108
    print(json.dumps(run_drill(root), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
