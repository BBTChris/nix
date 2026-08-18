#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): the symbols
# are read STATICALLY, by AST, without importing the check, so a shared base
# module would be invisible to that reader and the duplication is required.
"""Gate: the §6.6 ranking table is published, read O(1), and written by ONE process.

Subject: `scripts/nixscore/publisher.py` — the real publish path — driven over a
live `ipc://` ZeroMQ endpoint, across a real process boundary, with the
publisher really killed.

Authority: `docs/nix_check_contract.md` §4, §17, §18 for the gate contract, and
`docs/nics_risk_subsystem_spec_v1.3.md` for the subject — §6.6 (line 429; the
ranking table, its sole writer, the O(1) reads and the FCFS fallback, all
LOCKED), §12.7 (line 644, LOCKED: *"Mirror model, NOT raw shared memory"*,
snapshot-on-subscribe mandatory, freshness stamps ride each update), and
§11:595 (*"Ranking-table lookup only … Allocator and Limiter do O(1) reads"*).

## Boundary against the two gates that already exist (§5.5 requires it in both)

* `checks/check_state_bus.py` owns `scripts/nixbus/statebus.py` — whether the
  TRANSPORT delivers at all. It says nothing about the ranking table.
* `checks/check_scoring_seam.py` owns `scripts/nixscore/seam.py` — the SHAPE of
  the read path and the five FCFS triggers, driven **with no transport**: its
  own declaration is `RESOURCES = ()` and it feeds hand-built `StateMessage`s.
* This gate owns `scripts/nixscore/publisher.py` and everything that only exists
  once real sockets and real processes are involved: a late joiner over a real
  socket, a real backpressure burst, a real thread overlapping reads with
  writes, and a real `SIGKILL` followed by a real impostor binding the real
  endpoint. None of the three re-measures another: this one would still fail on
  a hijackable reader over a perfect bus and a perfect seam.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **Nothing was ever published and nothing ever arrived.** *Closed by the
   NON-VACUITY PRECONDITION:* the verdict reads the readers' `bytes_received`,
   and zero bytes across every socket arm is CANNOT_MEASURE, never PASS.
2. **The sole-writer arm ran with no impostor traffic reaching the consumer.**
   A consumer that refuses nothing because nothing arrived looks exactly like a
   consumer that refuses correctly. *Closed by requiring the impostor's bytes to
   have been COUNTED on the wire before the refusal is credited*, and by
   requiring `foreign_rejected` to have increased by at least as many messages
   as arrived.
3. **The impostor could not actually have won.** Refusing a snapshot that would
   have produced the same answer proves nothing. *Closed by making the
   impostor's table the REVERSE of the incumbent's*, so accepting it would flip
   the arbitration winner — and by asserting the winner did not flip.
4. **The concurrency arm never overlapped a read with a write.** This is the
   named trap: a harness that serialises proves serialisation, not safety.
   *Closed three ways:* the reader must observe **at least two distinct
   generations** (so its reads demonstrably straddled a write), both counters
   must be non-zero, and — the real one — **the naive two-lookup path must
   actually TEAR in this run**. A run in which the deliberately-tearable read
   does not tear is a run whose harness cannot see tearing, and it is reported
   CANNOT_MEASURE rather than green.
5. **The read path recomputes and every output is still correct.** A reader that
   recomputes an EMA produces the right number; only the SHAPE shows it.
   *Closed by parsing the subject's read path* — reusing
   `check_scoring_seam.read_path_defects`, the instrument that already owns that
   property (doctrine C.9), rather than writing a second one — and by planting a
   computing reader through it every run.
6. **The backpressure arm passed because the burst was small enough not to
   matter.** *Closed by requiring the burst to have actually exceeded the
   socket's buffers* — messages must really have been lost — before the
   never-blocked verdict is credited.

## WHICH COPY OF THE SUBJECT EACH ARM MEASURES

Stated because the two are not the same object and a reader is entitled to know.
The five DRIVING arms exercise the `nixscore.publisher` this process **imported**
— the code that is actually loaded, which is also what the spawned publisher
subprocess is pointed at, derived from `publisher.__file__` rather than from
`ctx.nix_home`. The AST arm parses `ctx.nix_home / SUBJECT` **from disk**. In
production the two are the same file; they differ only under a test that points
the gate at a planted tree, which is exactly how the read-path arm's can-fail
binding is re-established end to end.

## What this gate does NOT prove

It does not prove the Scoring process computes a correct EMA (nothing here
computes one; that is sub-agent A's engine), and it does not prove the Allocator
consumes the rank (sub-agent E). It proves the table gets there, is read in O(1),
and cannot be written by anyone else.
"""

from __future__ import annotations

import ast
import secrets
import signal
import subprocess  # nosec B404 - fixed argv, shell=False, no untrusted input
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `pyzmq` is a `checks/pinned_deps.json` pin, so the venv is what makes the
#: subject importable at all — same dependency, same reason, as
#: `check_state_bus`.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Declared against what this gate ACTUALLY does — the list below is the
#: enumeration, and no count of it is restated here (directive 3) — because
#: `check_observed_resource_claims` compares declarations against OBSERVED use
#: at runtime (§17, contract rule 12) and a claim it can see and I did not
#: declare is a FAIL:
#: * `file-write:/tmp` — `tempfile.mkdtemp` for the bus roots, and the
#:   absolute-path unlinks that remove them. `shutil.rmtree` is deliberately
#:   NOT used: on POSIX it unlinks through directory fds with bare relative
#:   names, which the audit hook records as `file-write:<basename>` that no
#:   path-rooted declaration can cover (measured on `check_state_bus`, ARC 026).
#: * `zmq-ipc` — the AF_UNIX sockets libzmq binds and connects. NOT observable:
#:   libzmq calls `bind(2)` from C, so CPython's `socket` audit events never
#:   fire. The observer will under-report it; declared anyway, because the plan
#:   is what needs to know.
#: * `subprocess:python` AND `subprocess:python3` — the sole-writer arm spawns a
#:   REAL publisher process with `sys.executable` and `SIGKILL`s it. `covers`
#:   matches by BASENAME, and the basename depends on which interpreter is
#:   running the gate: `.venv/bin/python` under the venv runner,
#:   `/usr/bin/python3` under `nix-verify.service`. MEASURED, and this
#:   declaration was CAUGHT FALSE by `check_observed_resource_claims` with only
#:   the first of the two: *"check_ranking_table was OBSERVED using
#:   subprocess:/usr/bin/python3 and its declaration … does not account for it —
#:   a false declaration (D2.27) [observed under: /usr/bin/python3]"*. One
#:   declaration, two launch modes, and the gate observes both.
#: * `threads` — the concurrency arm runs a real writer thread against a real
#:   reader thread. Also unobservable (no audit event for `Thread.start`), also
#:   declared.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "zmq-ipc",
    "subprocess:python",
    "subprocess:python3",
    "threads",
)
TIME_BOUND = True
#: A ~2.5 s concurrency window, a ~3 s hijack window, a burst and three socket
#: round-trips.
EXPECTED_S = 30.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "Every finding here is a live-behaviour defect — a reader that computes, a "
    "publisher that blocks, a mirror that accepts an impostor, a read that "
    "tears. None has an on-disk setting to flip, and a gate that 'repaired' a "
    "transport by publishing into it would be manufacturing the traffic it "
    "exists to measure."
)
INSTALLABLE = False
ON_FAIL = "continue"
#: The artifact this gate MEASURES, for `check_artifact_gate_coverage`.
#: `seam.py` is deliberately absent: `check_scoring_seam` owns it, and a second
#: gate claiming it would be the duplicate instrument doctrine C.9 forbids.
SUBJECTS: tuple[str, ...] = ("scripts/nixscore/publisher.py",)

NAME = "check_ranking_table"

SUBJECT = "scripts/nixscore/publisher.py"

#: Budgets. Generous enough that ipc setup is not a race, bounded enough that
#: exhausting one is a finding rather than a hang.
SERVICE_MS = 1000
PUMP_MS = 600
#: A single `publish()` must never take this long. Far above any in-memory
#: enqueue and far below anything that waited on a peer. §6.6: Scoring never
#: waits on a reader.
PUBLISH_BUDGET_S = 0.050
#: Enough to overrun XPUB's send HWM and SUB's receive HWM (1000 each by
#: default), so the burst really does force the drop it is measuring.
BURST_PUBLISHES = 4000
#: How long reads and writes are driven against each other. The tear rate on the
#: two-lookup path measured ~3e-5 per read, so this window has to be long enough
#: that a run which sees none is genuinely surprising.
OVERLAP_S = 2.5
#: Below this the concurrency arm has not demonstrated an overlap at all.
MIN_OVERLAP_GENERATIONS = 2
#: How long the impostor is given to be found by the reconnecting subscriber.
HIJACK_S = 3.0

FIRST = ("s1", "ES")
SECOND = ("s2", "NQ")

#: The publisher the sole-writer arm spawns and kills. Inline rather than a
#: file on disk: a second `.py` artifact would need its own gate coverage, and
#: this program is a fixture, not a module.
PUBLISHER_PROGRAM = """
import sys, time
sys.path.insert(0, sys.argv[2])
from nixscore.publisher import RankingWriter
from nixscore.seam import RankRow
ep = sys.argv[1]
w = RankingWriter(ep)
rows = {
    ("s1", "ES"): RankRow("s1", "ES", 900.0, 1, 7),
    ("s2", "NQ"): RankRow("s2", "NQ", 100.0, 2, 7),
}
w.publish_rows(rows, 10)
print("READY", flush=True)
while True:
    w.service(200)
    w.publish_rows(rows, 10)
    time.sleep(0.05)
"""


def _import_subject() -> tuple[Any, Any, str]:
    """Import the subject and the frozen seam lazily.

    `verify.py` may run under a python without pyzmq (`nix-verify.service` uses
    `/usr/bin/python3`), and a module-level import would make that a LOAD ERROR
    for the whole check rather than an honest CANNOT_MEASURE.
    """
    try:
        from nixscore import (  # pylint: disable=import-outside-toplevel
            publisher,
            seam,
        )
    except ImportError as exc:
        return (
            None,
            None,
            f"cannot import nixscore.publisher under {sys.executable}: {exc!r}",
        )
    return publisher, seam, ""


def _rows(seam: Any, nonce: str, high_first: bool) -> dict[tuple[str, str], Any]:
    """Two pair-rows carrying `nonce` inside the table, not beside it.

    The nonce rides a real row so a delivered table can be told apart from a
    delivered *envelope*: a transport that carried the right topic and the wrong
    payload is a mirror that lies.
    """
    return {
        FIRST: seam.RankRow(FIRST[0], FIRST[1], 900.0 if high_first else 1.0, 1, 7),
        SECOND: seam.RankRow(
            SECOND[0], SECOND[1], 100.0 if high_first else 9999.0, 2, 7
        ),
        (nonce, "NONCE"): seam.RankRow(nonce, "NONCE", 0.0, 3, 0),
    }


def _remove_tree(root: Path) -> None:
    """Delete a scratch bus directory by ABSOLUTE path, never `shutil.rmtree`.

    See the `RESOURCES` note: `rmtree` unlinks through directory fds with bare
    relative names, which the resource observer records as an unattributable
    `file-write:<basename>`.
    """
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# ARM 1 — a LATE joiner receives the current table over a real ipc socket
# ---------------------------------------------------------------------------


def _late_joiner(pub: Any, seam: Any, root: Path, nonce: str, *, service: bool) -> dict:
    """Publish, THEN subscribe. `service=False` is the CONTROL.

    The table is published before the reader exists and never published again,
    so the only thing that can deliver it is the subscribe-triggered snapshot.
    The control is identical except that the mechanism is never allowed to run.
    """
    endpoint = pub.ranking_endpoint(root)
    writer = pub.RankingWriter(endpoint)
    reader = None
    try:
        writer.publish_rows(_rows(seam, nonce, True), 10)
        socket_file = Path(endpoint.removeprefix("ipc://"))
        reader = pub.RankingReader(endpoint, stale_after_s=30.0)
        cold = {
            "view": reader.view(),
            "stale": reader.stale,
            "verdict": reader.arbitrate(FIRST, SECOND),
        }
        served = writer.service(SERVICE_MS) if service else 0
        result = reader.pump(PUMP_MS)
        return {
            "endpoint": endpoint,
            "socket_file_exists": socket_file.exists(),
            "served": served,
            "pump": result,
            "cold": cold,
            "view": reader.view(),
            "verdict": reader.arbitrate(FIRST, SECOND),
            "bytes": reader.bytes_received,
        }
    finally:
        if reader is not None:
            reader.close()
        writer.close()


def _arm_transport(
    live: dict, nonce: str, defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """§12.7's snapshot-on-subscribe, carrying the ranking table itself."""
    site = f"{SUBJECT}:RankingWriter.service"
    if not live["endpoint"].startswith("ipc://"):
        defects.append((site, f"endpoint {live['endpoint']!r} is not ipc://"))
        return
    if not live["socket_file_exists"]:
        defects.append(
            (
                site,
                "no AF_UNIX socket file existed on disk while the publisher was bound",
            )
        )
    view = live["view"]
    if view is None:
        defects.append(
            (
                site,
                (
                    f"a reader that joined AFTER the only publication received "
                    f"{live['pump'].received} message(s) and holds NO table — "
                    "§12.7's snapshot-on-subscribe is mandatory, not polish"
                ),
            )
        )
        return
    if view.lookup(nonce, "NONCE") is None:
        defects.append(
            (
                site,
                (
                    f"the delivered table carries no row for nonce {nonce!r} — the "
                    "transport delivered something that is not the table under test"
                ),
            )
        )
        return
    ev.append(
        f"late joiner got the ranking table over {live['endpoint']}: "
        f"served={live['served']} rows={len(view.rows)} seq={view.seq} "
        f"stamp_age={view.age_s():.3f}s bytes={live['bytes']}"
    )


def _arm_control(control: dict, defects: list[tuple[str, str]], ev: list[str]) -> None:
    """With `service()` never called, the late joiner must get NOTHING."""
    if control["view"] is not None:
        defects.append(
            (
                f"{SUBJECT}:RankingReader.pump",
                (
                    "the CONTROL run — identical except that snapshot-on-subscribe "
                    "was never serviced — still delivered a table, so arm 1's "
                    "arrival was not caused by the mechanism under test"
                ),
            )
        )
        return
    ev.append(
        f"control (no service()): received={control['pump'].received} "
        f"view=None — the snapshot really is what delivered arm 1"
    )


def _arm_cold(live: dict, defects: list[tuple[str, str]], ev: list[str]) -> None:
    """Between connect and the first snapshot the reader is STALE and answers FCFS.

    §12.7: *"mirror incomplete => treated as stale => fast-drop/deny until
    snapshot lands"*, and §6.6 makes the degraded answer FCFS rather than a deny.
    Measured over a real socket that is genuinely connected — which is the only
    place the question is interesting, because a reader with a live connection
    and no data is exactly the state that looks healthy.
    """
    cold = live["cold"]
    site = f"{SUBJECT}:RankingReader.view"
    if cold["view"] is not None:
        defects.append(
            (site, "a reader that has received nothing already holds a table")
        )
    if not cold["stale"]:
        defects.append(
            (
                site,
                (
                    "a connected reader with no snapshot reported FRESH. §12.7: an "
                    "incomplete mirror IS stale; a live socket is not data"
                ),
            )
        )
    if str(cold["verdict"].outcome) != "fcfs":
        defects.append(
            (
                f"{SUBJECT}:RankingReader.arbitrate",
                (
                    f"a reader with no snapshot returned {cold['verdict'].outcome!r} "
                    "instead of the FCFS fallback"
                ),
            )
        )
        return
    after = live["verdict"]
    if str(after.outcome) != "ranked" or after.winner != FIRST:
        defects.append(
            (
                f"{SUBJECT}:RankingReader.arbitrate",
                (
                    f"after the snapshot landed the reader answered "
                    f"{after.outcome!r}/{after.winner!r}, not ranked/{FIRST!r} — "
                    "without this half the gate would pass a reader that says FCFS "
                    "to everything"
                ),
            )
        )
        return
    ev.append(
        f"before/after over one socket: no-snapshot -> "
        f"{cold['verdict'].outcome} ({cold['verdict'].reason[:48]}...); "
        f"after snapshot -> {after.outcome} winner={after.winner}"
    )


# ---------------------------------------------------------------------------
# ARM 2 — a slow reader must not stall Scoring
# ---------------------------------------------------------------------------


def _burst(pub: Any, seam: Any, root: Path, nonce: str) -> dict:
    """Publish a burst into a connected reader that never drains. Times it."""
    endpoint = pub.ranking_endpoint(root)
    writer = pub.RankingWriter(endpoint)
    reader = None
    try:
        reader = pub.RankingReader(endpoint, stale_after_s=600.0)
        writer.service(SERVICE_MS)
        rows = _rows(seam, nonce, True)
        worst = 0.0
        started = time.perf_counter()
        for _ in range(BURST_PUBLISHES):
            mark = time.perf_counter()
            writer.publish_rows(rows, 10)
            worst = max(worst, time.perf_counter() - mark)
        total = time.perf_counter() - started
        result = reader.pump(PUMP_MS)
        return {
            "worst": worst,
            "total": total,
            "published": writer.published,
            "received": result.received,
            "bytes": reader.bytes_received,
            "gaps": reader.gaps_detected,
            "lost": reader.messages_lost,
        }
    finally:
        if reader is not None:
            reader.close()
        writer.close()


def _arm_backpressure(
    burst: dict, defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """§6.6: Scoring never waits on a reader. And what the silence costs."""
    site = f"{SUBJECT}:RankingWriter.publish_rows"
    if burst["worst"] > PUBLISH_BUDGET_S:
        defects.append(
            (
                site,
                (
                    f"the worst single publish into a non-draining reader took "
                    f"{burst['worst'] * 1000:.2f}ms, over the "
                    f"{PUBLISH_BUDGET_S * 1000:.0f}ms budget. §6.6 requires Scoring "
                    "never to wait on a reader; a publisher that blocks on a slow "
                    "dashboard has put the dashboard on the scoring loop"
                ),
            )
        )
        return
    dropped = burst["published"] - burst["received"]
    if dropped <= 0:
        defects.append(
            (
                site,
                (
                    f"a {BURST_PUBLISHES}-message burst into a never-draining reader "
                    f"lost NOTHING ({burst['published']} published, "
                    f"{burst['received']} received) — the burst did not exceed the "
                    "socket buffers, so 'the publisher did not block' was not "
                    "actually put to the test"
                ),
            )
        )
        return
    ev.append(
        f"backpressure: {burst['published']} publishes in {burst['total']:.3f}s, "
        f"worst single {burst['worst'] * 1000:.3f}ms (budget "
        f"{PUBLISH_BUDGET_S * 1000:.0f}ms) — Scoring never waited; the reader "
        f"received {burst['received']} and LOST {dropped} as a TAIL TRUNCATION "
        f"(interior seq gaps detected={burst['gaps']}), so its table looks whole "
        f"and is behind — staleness, not sequencing, is what catches this"
    )


# ---------------------------------------------------------------------------
# ARM 3 — reads DRIVEN CONCURRENTLY WITH WRITES
# ---------------------------------------------------------------------------


def _overlap(pub: Any, seam: Any, root: Path) -> dict:
    """Run a writer thread against a reader thread and count torn observations.

    Two read shapes are driven against the SAME concurrent writer:

    * `lookup(first)` then `lookup(second)` — two independent reads of the
      mirror, which is the shape of `RankingMirror.arbitrate`. This one is
      EXPECTED to tear, and it is this arm's can-fail control: a run in which it
      does not tear is a run whose harness cannot see tearing.
    * `view()` then two lookups on the captured view — one attribute read, then
      an immutable table. This one must NOT tear.

    The generation rides `days_observed`, which every row in a given published
    table shares, so two rows disagreeing about it means they came from two
    different tables.
    """
    endpoint = pub.ranking_endpoint(root)
    writer = pub.RankingWriter(endpoint)
    reader = pub.RankingReader(endpoint, stale_after_s=600.0)
    stop = threading.Event()
    counts = {"writes": 0}
    thread = threading.Thread(
        target=_write_loop, args=(pub, seam, reader, stop, counts), daemon=True
    )
    thread.start()
    try:
        observed = _read_loop(reader)
    finally:
        stop.set()
        thread.join(timeout=5.0)
        reader.close()
        writer.close()
    observed["writes"] = counts["writes"]
    return observed


def _write_loop(pub: Any, seam: Any, reader: Any, stop: Any, counts: dict) -> None:
    """The writer thread: fold generation-stamped tables in as fast as it can."""
    from nixbus.statebus import StateMessage  # pylint: disable=import-outside-toplevel

    written = 0
    while not stop.is_set():
        written += 1
        rows = {
            key: seam.RankRow(key[0], key[1], float(written), 1, written)
            for key in (FIRST, SECOND)
        }
        payload = seam.RankingSnapshot(rows=rows, span_days=10).as_wire()
        reader.ingest(
            StateMessage(pub.RANKING_TOPIC, payload, written, time.time(), True)
        )
    counts["writes"] = written


def _read_loop(reader: Any) -> dict:
    """The reader thread (this one): both read shapes, torn observations counted."""
    torn_naive = 0
    torn_view = 0
    reads = 0
    generations: set[int] = set()
    deadline = time.perf_counter() + OVERLAP_S
    while time.perf_counter() < deadline:
        reads += 1
        left = reader.lookup(*FIRST)
        right = reader.lookup(*SECOND)
        if left is not None and right is not None:
            generations.add(left.days_observed)
            if left.days_observed != right.days_observed:
                torn_naive += 1
        view = reader.view()
        if view is not None:
            torn_view += _view_tear(view)
    return {
        "reads": reads,
        "generations": len(generations),
        "torn_naive": torn_naive,
        "torn_view": torn_view,
    }


def _view_tear(view: Any) -> int:
    """1 if two rows out of ONE captured view disagree about their generation."""
    left = view.lookup(*FIRST)
    right = view.lookup(*SECOND)
    if left is None or right is None:
        return 0
    return int(left.days_observed != right.days_observed)


def _arm_concurrency(over: dict, defects: list[tuple[str, str]], ev: list[str]) -> str:
    """Torn reads. Returns a non-empty string when the ARM ITSELF is blind."""
    if over["reads"] == 0 or over["writes"] == 0:
        return (
            f"the overlap harness did {over['reads']} read(s) against "
            f"{over['writes']} write(s) — nothing was driven"
        )
    if over["generations"] < MIN_OVERLAP_GENERATIONS:
        return (
            f"the reader observed {over['generations']} distinct table "
            f"generation(s) over {over['reads']} reads, so its reads never "
            "straddled a write. A concurrency test that does not overlap "
            "proves serialisation, not safety"
        )
    if over["torn_naive"] == 0:
        return (
            f"the deliberately-tearable two-lookup path tore {over['torn_naive']} "
            f"times in {over['reads']} reads against {over['writes']} writes — "
            "this arm's own control did not fire, so its silence about the view "
            "path is blindness, not a measurement"
        )
    if over["torn_view"] > 0:
        defects.append(
            (
                f"{SUBJECT}:RankingView",
                (
                    f"{over['torn_view']} of {over['reads']} reads taken from ONE "
                    f"captured view returned rows from DIFFERENT published tables. "
                    "A view is captured by a single attribute read and is immutable "
                    "afterwards; a tear here means the table is being mutated in "
                    "place, which is §12.7's *torn reads* in the mirror model"
                ),
            )
        )
        return ""
    ev.append(
        f"concurrency: {over['reads']} reads overlapped {over['writes']} writes "
        f"across {over['generations']} distinct table generations; the "
        f"two-lookup path (the shape of RankingMirror.arbitrate) TORE "
        f"{over['torn_naive']} times, the single-capture view path tore 0 — the "
        "overlap is proven by the control firing, not asserted"
    )
    return ""


# ---------------------------------------------------------------------------
# ARM 4 — SOLE WRITER, proven by killing the writer and letting an impostor bind
# ---------------------------------------------------------------------------


def _hijack(pub: Any, seam: Any, root: Path) -> dict:
    """Real publisher process, SIGKILL, impostor rebinds, reader must refuse.

    This is the only shape in which the sole-writer property is actually at
    risk. Measured on this node: `ipc://` bind is NOT exclusive — an impostor
    can bind a live endpoint and libzmq will not object — but an ALREADY
    CONNECTED subscriber keeps its inode and never sees the impostor. The
    subscriber only lands on the impostor when it RECONNECTS, and it only
    reconnects when the incumbent dies. So the process really is killed.
    """
    endpoint = pub.ranking_endpoint(root)
    # The scripts root is derived from the module THIS process imported, not
    # from `ctx.nix_home`: the driving arms exercise the code that is actually
    # loaded, and pointing the child at a different tree would let the two
    # halves of this gate measure two different modules.
    scripts = str(Path(pub.__file__).resolve().parents[1])
    # `with` is wrong here on purpose: the publisher must OUTLIVE this
    # statement — it is killed deliberately, mid-arm, and the `finally` below
    # owns its teardown. nosec B603: literal argv — this interpreter, an
    # in-module program string, and two paths this gate itself derived.
    proc = subprocess.Popen(  # nosec B603 # pylint: disable=consider-using-with
        [sys.executable, "-c", PUBLISHER_PROGRAM, endpoint, scripts],
        stdout=subprocess.PIPE,
        text=True,
    )
    reader = None
    impostor = None
    try:
        if (proc.stdout is None) or proc.stdout.readline().strip() != "READY":
            return {"error": "the publisher subprocess never reported READY"}
        reader = pub.RankingReader(endpoint, stale_after_s=1.0)
        reader.pump(1500)
        legit = {
            "applied": reader.applied,
            "bytes": reader.bytes_received,
            "verdict": reader.arbitrate(FIRST, SECOND),
        }
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5.0)
        impostor = pub.RankingWriter(endpoint, identity="impostor")
        arrived = _drive_impostor(impostor, seam, reader)
        return {
            "error": "",
            "legit": legit,
            "returncode": proc.returncode,
            "arrived": arrived,
            "applied": reader.applied,
            "foreign_rejected": reader.foreign_rejected,
            "bytes": reader.bytes_received,
            "verdict": reader.arbitrate(FIRST, SECOND),
        }
    finally:
        if impostor is not None:
            impostor.close()
        if reader is not None:
            reader.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5.0)
        if proc.stdout is not None:
            proc.stdout.close()


def _drive_impostor(impostor: Any, seam: Any, reader: Any) -> int:
    """Publish the REVERSED table from the impostor. Returns messages that arrived."""
    rows = _rows(seam, "impostor", False)
    snapshot = seam.RankingSnapshot(rows=rows, span_days=10, writer_identity="impostor")
    arrived = 0
    deadline = time.perf_counter() + HIJACK_S
    while time.perf_counter() < deadline:
        impostor.service(100)
        impostor.publish(snapshot)
        arrived += reader.pump(100).received
    return arrived


def _arm_sole_writer(hij: dict, defects: list[tuple[str, str]], ev: list[str]) -> str:
    """§6.6's sole writer. Returns a non-empty string when the arm is blind."""
    if hij.get("error"):
        return hij["error"]
    if hij["legit"]["applied"] == 0:
        return (
            "the legitimate publisher process delivered nothing, so there was "
            "no table for an impostor to overwrite"
        )
    if hij["arrived"] == 0:
        return (
            f"the impostor bound the same ipc endpoint and published for "
            f"{HIJACK_S}s but ZERO of its messages reached the "
            "reader — a consumer that refuses nothing because nothing arrived "
            "is indistinguishable from one that refuses correctly"
        )
    site = f"{SUBJECT}:RankingReader.ingest"
    if hij["applied"] != hij["legit"]["applied"]:
        defects.append(
            (
                site,
                (
                    f"the reader ACCEPTED an impostor's table: applied went "
                    f"{hij['legit']['applied']} -> {hij['applied']} after the real "
                    "publisher was SIGKILLed and a foreign process bound its "
                    "endpoint. §6.6 makes Scoring the sole writer and the consumer "
                    "is the only place that is enforceable — ipc:// bind is not "
                    "exclusive"
                ),
            )
        )
    if hij["foreign_rejected"] < hij["arrived"]:
        defects.append(
            (
                site,
                (
                    f"{hij['arrived']} impostor message(s) arrived but only "
                    f"{hij['foreign_rejected']} were COUNTED as refused. A silent "
                    "drop is indistinguishable from a message that never arrived "
                    "(check contract §18)"
                ),
            )
        )
    if hij["verdict"].winner != FIRST:
        defects.append(
            (
                f"{SUBJECT}:RankingReader.arbitrate",
                (
                    f"the impostor's REVERSED table changed the winner to "
                    f"{hij['verdict'].winner!r}. The impostor was given a table that "
                    "would flip the answer precisely so that refusing it is a "
                    "measurable outcome and not a formality"
                ),
            )
        )
    ev.append(
        f"sole writer: real publisher pid killed (rc={hij['returncode']}), "
        f"impostor rebound the SAME ipc endpoint (libzmq does NOT refuse it), "
        f"{hij['arrived']} foreign message(s) reached the reconnecting "
        f"subscriber and were all refused on the identity stamp "
        f"(foreign_rejected={hij['foreign_rejected']}, applied stayed "
        f"{hij['applied']}); verdict {hij['verdict'].outcome} winner "
        f"{hij['verdict'].winner} — the reversed table did not win"
    )
    return ""


# ---------------------------------------------------------------------------
# ARM 5 — the read path does not compute
# ---------------------------------------------------------------------------


def _read_path_findings(source: str) -> tuple[list, int]:
    """Delegate to the instrument that already owns this property (C.9)."""
    from check_scoring_seam import (  # pylint: disable=import-outside-toplevel
        read_path_defects,
    )

    return read_path_defects(source)


def _read_path_arm_can_fail() -> tuple[bool, str]:
    """Plant a computing reader and a clean one; the arm must separate them."""
    computing = (
        "class RankingView:\n"
        "    def lookup(self, strategy_id, symbol):\n"
        "        rows = self.rows\n"
        "        return sum(r.realized_ema for r in rows.values()) / len(rows)\n"
    )
    findings, scanned = _read_path_findings(computing)
    if scanned != 1 or not findings:
        return False, (
            f"a reader that sums and divides the whole ranking table produced "
            f"{len(findings)} finding(s) over {scanned} scanned function(s) — "
            "the read-path arm cannot see a computing reader, so its silence is "
            "blind, not green"
        )
    clean, clean_scanned = _read_path_findings(
        "class RankingView:\n"
        "    def lookup(self, strategy_id, symbol):\n"
        "        return self.rows.get((strategy_id, symbol))\n"
    )
    if clean_scanned != 1 or clean:
        return False, (
            f"a plain dict lookup was reported as computing "
            f"({[f.why for f in clean]}) — the arm flags everything, which is "
            "the same blindness pointed the other way"
        )
    return True, ""


def _read_path_names(source: str) -> set[str]:
    """Read-path function names actually defined in the subject."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    wanted = {"lookup", "arbitrate", "age_s", "fresh", "view"}
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    }


def _arm_read_path(source: str, defects: list[tuple[str, str]], ev: list[str]) -> None:
    """§6.6/§11:595 — the Allocator and Limiter look up, they never compute."""
    findings, scanned = _read_path_findings(source)
    names = _read_path_names(source)
    if scanned == 0 or not names:
        defects.append(
            (
                f"{NAME}:non-vacuity",
                (
                    f"the read-path scan found {scanned} judged function(s) in "
                    f"{SUBJECT} — a scan over nothing cannot report a computing reader"
                ),
            )
        )
        return
    for finding in findings:
        defects.append((f"{SUBJECT}:{finding.site}", finding.why))
    ev.append(
        f"read path: scanned {scanned} function(s) "
        f"({', '.join(sorted(names))}) in {SUBJECT} for computation, iteration "
        f"and O(n) scans — {len(findings)} finding(s); the arm proved it can see "
        "a computing reader on a planted subject this run"
    )


# ---------------------------------------------------------------------------


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def _drive(pub: Any, seam: Any, nonce: str) -> tuple[dict, str]:
    """Every arm's raw measurement, or ("", error). Owns the scratch roots."""
    roots = [Path(tempfile.mkdtemp(prefix=f"nixrank-{n}-")) for n in range(5)]
    try:
        return {
            "live": _late_joiner(pub, seam, roots[0], nonce, service=True),
            "control": _late_joiner(pub, seam, roots[1], f"CTL-{nonce}", service=False),
            "burst": _burst(pub, seam, roots[2], f"BST-{nonce}"),
            "overlap": _overlap(pub, seam, roots[3]),
            "hijack": _hijack(pub, seam, roots[4]),
        }, ""
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
        return {}, f"the ranking bus could not be driven: {type(exc).__name__}: {exc}"
    finally:
        for root in roots:
            _remove_tree(root)


def _preflight(ctx: Context) -> tuple[Any, Any, str, str]:
    """Import the subject, prove the AST arm can fail, read the source.

    Returns `(publisher, seam, source, error)`; a non-empty `error` means the
    gate cannot measure and names why. Split out of `run` so the three
    guard clauses do not push it over the return-statement budget — the same
    reason `_guarded_defect` is split out of `validate_result`.
    """
    pub, seam, error = _import_subject()
    if pub is None:
        return None, None, "", error
    ok, why = _read_path_arm_can_fail()
    if not ok:
        return None, None, "", f"the read-path arm cannot fail: {why}"
    try:
        source = (ctx.nix_home / SUBJECT).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, None, "", f"cannot read {SUBJECT}: {exc!r}"
    return pub, seam, source, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the real publish path and check what actually happened."""
    pub, seam, source, error = _preflight(ctx)
    if error:
        return _cannot(error, [])

    nonce = f"ARC036B-{secrets.token_hex(6)}"
    measured, error = _drive(pub, seam, nonce)
    evidence: list[str] = []
    if error:
        return _cannot(error, evidence)

    # THE NON-VACUITY PRECONDITION. Nothing below means anything without it, so
    # it is settled before any arm contributes a verdict.
    carried = (
        int(measured["live"]["bytes"])
        + int(measured["burst"]["bytes"])
        + int(measured["hijack"].get("bytes", 0))
    )
    if carried == 0:
        return _cannot(
            "the ranking transport carried ZERO bytes across every arm — a "
            "reader that received nothing cannot report that the table is "
            "published (§12.7). CANNOT_MEASURE, deliberately never PASS",
            evidence,
        )
    evidence.append(f"transport carried {carried} bytes of real ranking traffic")

    defects: list[tuple[str, str]] = []
    _arm_transport(measured["live"], nonce, defects, evidence)
    _arm_control(measured["control"], defects, evidence)
    _arm_cold(measured["live"], defects, evidence)
    _arm_backpressure(measured["burst"], defects, evidence)
    blind = _arm_concurrency(measured["overlap"], defects, evidence)
    if blind:
        return _cannot(f"the concurrency arm is blind: {blind}", evidence)
    blind = _arm_sole_writer(measured["hijack"], defects, evidence)
    if blind:
        return _cannot(f"the sole-writer arm is blind: {blind}", evidence)
    _arm_read_path(source, defects, evidence)
    return result_from_defects(NAME, defects, "; ".join(evidence))


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
