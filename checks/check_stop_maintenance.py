#!/usr/bin/env python3
"""§4:190-196 — the RUNNING Limiter maintains its stops and fires ONE flatten.

ONE gate, ONE property, stated as the sentence D3.451 denied: *a synthetic stop
armed by this daemon is TRAILED toward price by the tick, is BREACHED when price
crosses it, and produces EXACTLY ONE protective flatten, sent OFF the hot path.*

ARC 055 / I1 ARC C1. MEASURED at `66f9f8b` before anything was written, on a
live `limiterd`: a stop armed at `5000.0 - 8 x 0.25 = 4998.0`, `level` INVARIANT
across 101 real ticks, no price directory, no price verb, no price block in the
status reply, and `hasattr(broker, "flatten") is False`. The same numbers driven
through the LIBRARY trailed to `5002.0` and reported the breach. The mechanism
worked and nothing with a pid drove it. **An armed stop that is never maintained
and never breached is not protection**, and this gate is what makes that a
measured property of the daemon rather than a paragraph in a docstring.

------------------------------------------------------------------------------
WHY A NEW GATE — the census, and what each existing owner actually owns
------------------------------------------------------------------------------
Doctrine C.9 forbids a second instrument over a property the suite already
drives, so the owners were enumerated before this file existed:

* `check_synthetic_stop_only` owns §12.1's PROHIBITION — the stop path reaches
  no broker verb and no venue stop order-type. It proves what the stop book must
  NOT do; it is silent on whether anything drives it.
* `check_flatten` owns the EXECUTOR — §14's zero-wire property (ARM 1/ARM 6),
  §4's dual-authority precedence (ARM 2), §3:173's onset selectivity (ARM 3/3b)
  and §4's reconcile (ARM 4). Every arm drives `nixrisk.flatten` as a LIBRARY.
  It never spawns a process and so cannot answer *did the daemon fire*.
* `check_limiter_daemon_dispatch` owns HAS-A-PID-CALLED-IT for the §2A
  completion routes — cancel, fill, reject, pending-timeout, onset. Its subject
  is the completion INBOX; the price tick is not a completion and no arm of it
  polls one.
* `check_hot_path_purity` owns §11's PURITY. ARC 055 extends it with ARM 3c so
  I9 is re-proven over `StopWatch.poll`, which is the right home for that
  property — it is the same property over new code, and a second purity gate
  would be the duplicate C.9 refuses. It says nothing about whether the poll
  produces a CORRECT flatten.

What is left unowned is exactly this file's subject: **monotonicity of the trail
under a driven price, and one flatten per breach**. Neither is measured anywhere
in the tree at `66f9f8b`.

------------------------------------------------------------------------------
FOUR ARMS
------------------------------------------------------------------------------
* **ARM 1 — the daemon FIRES.** A real `limiterd` subprocess, a real reservation,
  a real fill, a real armed stop, then a price pushed THROUGH the level over the
  daemon's own `price` verb. Driven through the LOOP's poll, never by calling
  `StopWatch.poll` directly: the gap I1 names is *the mechanism exists and no
  process calls it*, and a gate that called it would re-prove the library.
* **ARM 2 — FIRE-ONCE.** N further ticks past the breach with price still past
  the level. Still one flatten at the loop, one at the sender, one at the broker.
  A double-flatten is a real defect: each extra firing is an extra venue order.
* **ARM 3 — the trail is MONOTONIC.** Over the SHIPPED `StopWatch.poll` and a
  real `StopBook`: price advances -> the stop TIGHTENS; price retraces below the
  high-water but above the trail -> the stop does NOT loosen and the high-water
  does not retreat; price crosses the TRAILED level -> the breach fires and the
  firing names the trailed level, not the armed one.

  IT IS NOT DRIVEN THROUGH THE DAEMON'S FILL PATH, AND THE REASON IS A FINDING.
  MEASURED at ARC 055 / S3-B on a live daemon: a `trailing` reservation is
  ACCEPTED (1000.0 committed) and the fill is then REFUSED WHOLE —
  `InvalidStopIntent: a trailing stop needs a trail distance, which the frozen
  ProposedOrder does not carry`. `fills.py` calls `arm(report.price, order)` with
  no `trail_ticks`, so THIS DAEMON CANNOT HOLD A TRAILING STOP AT ALL. Routing
  one through means editing the frozen `ProposedOrder` seam, which ARC 055's
  freeze forbids. CHECK-DEBT D3.474. This arm therefore drives the same poll the
  daemon runs, and ARM 4 below makes that non-vacuous by proving the daemon
  really does hold this poll.
* **ARM 4 — the send is OFF the hot path and WIRE-FREE.** The daemon reports the
  native thread id the send RAN on, read from inside the send. It must equal the
  §5:323 sender thread's and differ from the loop's. And the send path is traced
  under a ban-set: `ProtectiveFlatten.fire` reached from the daemon's own send
  closure must touch no socket, no ZMQ, no asyncio and no state bus. That is I3
  re-proven over ARC 055's NEW code — `check_flatten` ARM 6 owns wire-freedom of
  `nixrisk.flatten`'s own reach and never imports `limiterd`, so the daemon-side
  send closure is invisible to it. Different subject, same property, and the
  distinction is the one ARM 3b draws against ARM 3 in that file.

------------------------------------------------------------------------------
§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?
------------------------------------------------------------------------------
 1. **No stop is ever armed**, so nothing can breach and nothing fires.
    GUARDED: ARM 1 reads the armed stop OUT of the daemon and checks its level
    against `FILL - STOP_TICKS x TICK` computed HERE from what this gate sent.
 2. **The price never reaches the ring**, so the poll polls nothing. GUARDED:
    `prices.published` is read back off the daemon and must have risen, and the
    ring's head must equal the price this gate pushed.
 3. **The poll never runs.** GUARDED: `stops.polls` must rise across the watch,
    and ARM 2 requires it to rise by a floor before it will say fire-once held.
 4. **The breach is "not fired" because price never crossed.** GUARDED: the
    price pushed is derived from the level the DAEMON reported, and a
    control push ABOVE the level must NOT fire before the crossing one does.
 5. **One flatten counted twice, or zero counted as one.** GUARDED: three
    independent counters must agree — the loop's `fires`, the sender's `sends`,
    and the BROKER's own `flattened` list, which is on the far side of the call.
 6. **The trail "does not loosen" because it never moved.** GUARDED: ARM 3
    requires the TIGHTENING first and refuses if the trailed level equals the
    armed one.
 7. **The send is "off the hot path" because it never happened.** GUARDED: ARM 4
    requires `sends >= 1` before it will compare thread ids, and requires the
    three ids to be three distinct measured integers.
 8. **The daemon does not actually hold this poll**, so ARM 3's library drive is
    about dead code. GUARDED: ARM 4 derives, from `limiterd.py`'s own AST, that
    the process composes `StopWatchDriver.before` into its ingress and passes
    `sender_send`; an absence is CANNOT_MEASURE.

Exit-code contract: 0 PASS, 1 FAIL, 2 CANNOT-MEASURE. No uncaught exception
collapses to 1 (doctrine B.2). Fail closed and loud.
"""

# C0302 (too-many-lines): over the 1000 default, and the overage is the §7.12
# block, the four-owner census that justifies this file existing at all, and the
# per-finding reasons check contract v2 rule 11 requires. `check_flatten` and
# `check_hot_path_purity` carry the identical disable for the identical reason.
# pylint: disable=too-many-lines
from __future__ import annotations

import ast
import json
import os
import subprocess  # nosec B404 - one `limiterd` spawn, fixed argv, no shell
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Final, cast

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
EXPECTED_S = 30.0
DEPENDS_ON: tuple[str, ...] = ()
#: SPAWNS a `limiterd` subprocess into a fresh temp runtime directory. Declared
#: because check contract rule 12 has the declaration checked against what is
#: OBSERVED at runtime, not merely against itself.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:python",
    "subprocess:python3",
)
ON_FAIL = "continue"
#: NON-CORRECTABLE: the subject is risk-path source — the poll that decides
#: whether a position's protective stop fires. A gate empowered to edit it until
#: its own drive came back clean would be manufacturing green over the one
#: mechanism that closes a losing position.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (§5:322's price poll, §4:190-196's trail "
    "and the breach->protective-flatten path); a repair that edited it to "
    "satisfy its own gate is the same class of action §4 forbids on the order "
    "path"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/limiterd.py",
    "scripts/nixrisk/stopwatch.py",
    "scripts/nixrisk/stops.py",
)

NAME = "check_stop_maintenance"

LIMITERD_FILE: Final[str] = "scripts/limiterd.py"
STOPWATCH_FILE: Final[str] = "scripts/nixrisk/stopwatch.py"

# -- what this gate SENDS IN. Every expectation below is computed from these. --
SYMBOL: Final[str] = "ES"
TICK_SIZE: Final[float] = 0.25
STOP_TICKS: Final[int] = 8
TRAIL_TICKS: Final[int] = 4
FILL_PRICE: Final[float] = 5000.0
QTY: Final[int] = 2
MARGIN: Final[float] = 500.0
BALANCE: Final[float] = 250_000.0
STRATEGY: Final[str] = "check-stop-maintenance"
CID: Final[str] = "csm-fixed"
#: §4 converts the distance ONCE, at the confirmed fill. Computed HERE, never
#: read back off the daemon and compared against itself (§7.12 #9's shape).
EXPECT_LEVEL: Final[float] = FILL_PRICE - STOP_TICKS * TICK_SIZE

DRIVE_TICK_S: Final[float] = 0.02
DRIVE_HEARTBEAT_S: Final[float] = 0.2
DRIVE_MAX_TICKS: Final[int] = 8000
BOOT_TIMEOUT_S: Final[float] = 30.0
REPLY_TIMEOUT_S: Final[float] = 20.0
WATCH_HORIZON_S: Final[float] = 10.0
#: How many further polls ARM 2 watches past the breach before it will say
#: fire-once held. One tick proves nothing: a path that re-fired every tick
#: would look identical after one look (§0a).
FIRE_ONCE_POLL_FLOOR: Final[int] = 20

#: Module roots the DAEMON'S SEND CLOSURE may not enter. I3's ban-set, and it is
#: a ban-list rather than an allow-set deliberately: the allow-set idiom is
#: `check_hot_path_purity`'s and it is applied there to a path whose complete
#: reach was MEASURED. This arm's subject is a send that legitimately reaches the
#: whole §4 fan-out, so what is asserted is the narrower and still decisive
#: claim §14 actually makes — the protective exit touches no TRANSPORT.
_BANNED_ON_SEND: Final[dict[str, str]] = {
    "socket": "a wire on the exit path (§14: the protective exit has zero wire)",
    "ssl": "a wire on the exit path",
    "http": "a wire on the exit path",
    "urllib": "a wire on the exit path",
    "zmq": "the state bus on the exit path (§14 makes the exit independent of it)",
    "asyncio": "an event loop on a SYNC §2A verb (invariant 5: must not block)",
    "selectors": "a wire on the exit path",
    "select": "a wire on the exit path",
    "psycopg": "a database round trip on the exit path",
    "sqlite3": "a database round trip on the exit path",
    "requests": "a wire on the exit path",
    "nixalloc": "the ALLOCATOR on the exit path (§14: the exit does not need it)",
}


class Cannot(RuntimeError):
    """The subject could not be reached. CANNOT_MEASURE, never PASS (rule 10)."""


class Drive:
    """One `limiterd` process and every path into it. Torn down always."""

    def __init__(self, nix_home: Path) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="check-stop-maintenance-"))
        self._n = 0
        interpreter = nix_home / ".venv/bin/python"
        if not interpreter.exists():
            raise Cannot(f"no interpreter at {interpreter}")
        script = nix_home / LIMITERD_FILE
        if not script.exists():
            raise Cannot(f"no {LIMITERD_FILE} under {nix_home}")
        try:
            self.proc = subprocess.Popen(  # nosec B603  # pylint: disable=consider-using-with
                [
                    str(interpreter),
                    str(script),
                    "--runtime-dir",
                    str(self.dir),
                    "--heartbeat-interval",
                    str(DRIVE_HEARTBEAT_S),
                    "--tick-interval",
                    str(DRIVE_TICK_S),
                    "--max-ticks",
                    str(DRIVE_MAX_TICKS),
                    "--tick-size",
                    f"{SYMBOL}={TICK_SIZE}",
                    "--account-balance",
                    str(BALANCE),
                ],
                cwd=str(nix_home / "scripts"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONPATH": str(nix_home / "scripts")},
            )
        except OSError as exc:
            raise Cannot(f"cannot spawn limiterd: {exc!r}") from exc
        self._await_boot()

    def _await_boot(self) -> None:
        runtime = self.dir / "limiter.runtime.json"
        deadline = time.time() + BOOT_TIMEOUT_S
        while time.time() < deadline:
            if runtime.exists():
                return
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() if self.proc.stderr else "")[-800:]
                raise Cannot(
                    f"limiterd refused to boot ({self.proc.returncode}): {err}"
                )
            time.sleep(0.05)
        raise Cannot(f"limiterd wrote no runtime record within {BOOT_TIMEOUT_S}s")

    @staticmethod
    def _atomically(path: Path, payload: dict[str, Any]) -> Path:
        """Write one JSON file the daemon may be scanning on its own tick.

        `os.replace` inside the same directory, for ARC 054's measured reason:
        `write_text` creates the file and then fills it, and the daemon scans
        every `DRIVE_TICK_S`. A gate that goes red on its own write race is a
        gate whose red means nothing.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".partial")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
        return path

    def cmd(self, verb: str, **fields: object) -> dict[str, Any]:
        """Send one command file; return the daemon's own reply."""
        self._n += 1
        cid = f"csm{self._n:05d}"
        self._atomically(
            self.dir / "inbox" / f"{cid}.json",
            {"schema": 1, "id": cid, "verb": verb, **fields},
        )
        reply = self.dir / "outbox" / f"{cid}.reply.json"
        deadline = time.time() + REPLY_TIMEOUT_S
        while time.time() < deadline:
            if reply.exists():
                try:
                    return json.loads(reply.read_text())
                except ValueError:
                    time.sleep(0.02)
                    continue
            if self.proc.poll() is not None:
                raise Cannot(
                    f"limiterd exited with {self.proc.returncode} before "
                    f"answering {verb!r}"
                )
            time.sleep(0.02)
        raise Cannot(f"limiterd did not answer {verb!r} within {REPLY_TIMEOUT_S}s")

    def price(self, price: float) -> dict[str, Any]:
        """§5:322's price, published from OUTSIDE the process."""
        return self.cmd("price", symbol=SYMBOL, price=price)

    def watch(self, pred: Any, what: str) -> dict[str, Any]:
        """Poll the daemon's OWN status until `pred`. Watches PAST the tick."""
        deadline = time.time() + WATCH_HORIZON_S
        status = self.cmd("status")
        while time.time() < deadline:
            if pred(status):
                return status
            time.sleep(0.03)
            status = self.cmd("status")
        raise _Missed(what, status)

    def settle(self, seconds: float) -> dict[str, Any]:
        """Let real ticks elapse, then return the LAST status. Never raises.

        Distinct from `watch` for `check_limiter_daemon_dispatch`'s own reason:
        a caller reporting an ABSENCE — *the price crossed and nothing fired* —
        needs its own sentence, and a timeout would replace it with a generic one.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            time.sleep(0.05)
        return self.cmd("status")

    def close(self) -> dict[str, Any]:
        """SIGTERM, join, and return the daemon's own stop record."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream is not None:
                stream.close()
        record = self.dir / "limiter.runtime.json"
        if not record.exists():
            raise Cannot("limiterd left no runtime record to read")
        return json.loads(record.read_text())


class _Missed(RuntimeError):
    """A watched condition never arrived. Carries the last status it saw."""

    def __init__(self, what: str, status: dict[str, Any]) -> None:
        self.what = what
        self.status = status
        super().__init__(what)


def _stop_for(status: dict[str, Any], cid: str) -> dict[str, Any] | None:
    """The daemon's own record of the synthetic stop protecting `cid`, or None."""
    for stop in (status.get("fills") or {}).get("stops") or ():
        if stop.get("client_order_id") == cid:
            return stop
    return None


def _stops_block(status: dict[str, Any]) -> dict[str, Any]:
    """The daemon's §4 maintenance block, or a raise. `None` is CANNOT_MEASURE."""
    block = status.get("stops")
    if block is None:
        raise Cannot(
            f"{LIMITERD_FILE}: this build's status reply carries no `stops` "
            "block — the daemon holds no §5:322 price poll and no §4 trail "
            "maintenance, so there is no subject for this gate (D3.451)"
        )
    return block


# R0911/R0912/R0914/R0915: the returns ARE the fail-closed ladder, and each rung
# is one of the §7.12 vacuity guards — a stop that predates the fill, a counter
# that moved before this gate touched anything, a price that never reached the
# ring, a poll that never ran, a fire above the stop, and the breach itself.
# Collapsing them would mean one sentence covering six distinguishable refusals,
# and check contract v2 rule 11 makes the REASON the assertion.
def _fires_non_vacuity(
    drive: Drive, seen: dict[str, Any]
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """The preconditions to ARM 1: a real reservation and NOTHING already fired."""
    findings: list[tuple[str, str]] = []
    drive.cmd("register", strategy_id=STRATEGY)
    took = drive.cmd(
        "reserve",
        strategy_id=STRATEGY,
        client_order_id=CID,
        symbol=SYMBOL,
        side="long",
        qty=QTY,
        margin_per_contract=MARGIN,
        stop_ticks=STOP_TICKS,
        stop_mode="fixed",
        signal_ts=time.time(),
    )
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reservation: {took.get('reason')}")
    before = _stops_block(took)
    seen["polls_at_reserve"] = before.get("polls")
    # NON-VACUITY (§7.12 #1): no stop may predate the fill.
    if _stop_for(took, CID) is not None:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: a stop is ALREADY armed for {CID!r} before any "
                    "fill was pushed. §4 converts at the CONFIRMED fill and nowhere "
                    "else; a stop that predates it makes every assertion below vacuous"
                ),
            )
        )
        return findings, took
    if before.get("breaches") or before.get("sends"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the daemon reports breaches="
                    f"{before.get('breaches')!r} sends={before.get('sends')!r} before "
                    "any price was pushed — a later 'exactly one' would be counting "
                    "something this gate did not cause"
                ),
            )
        )
        return findings, took

    return findings, took


def _arm_fires(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-locals,too-many-statements
    drive: Drive,
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """ARM 1 + ARM 2. `(findings, the numbers the daemon reported)`."""
    findings: list[tuple[str, str]] = []
    seen: dict[str, Any] = {}

    findings, _took = _fires_non_vacuity(drive, seen)
    if findings:
        return findings, seen

    drive._atomically(  # pylint: disable=protected-access
        drive.dir / "completions" / "fill.json",
        {
            "schema": 1,
            "event": "on_fill",
            "client_order_id": CID,
            "exec_id": f"x-{CID}",
            "done_qty": QTY,
            "symbol": SYMBOL,
            "price": FILL_PRICE,
            "cumulative_qty": QTY,
        },
    )
    try:
        status = drive.watch(
            lambda st: _stop_for(st, CID) is not None, "a stop armed for the fill"
        )
    except _Missed as miss:
        raise Cannot(
            f"{LIMITERD_FILE}: no stop was armed for {CID!r} after a §2A fill — "
            "this gate's subject is what happens to an ARMED stop, and there is "
            f"none. Last `fills` block: {(miss.status.get('fills') or {})!r}"
        ) from miss
    armed = _stop_for(status, CID) or {}
    level = float(armed.get("level", 0.0))
    seen["armed_level"] = level
    if abs(level - EXPECT_LEVEL) > 1e-9:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the stop for {CID!r} is at {level!r}; §4 anchors it "
                    f"at the confirmed fill, so it must be {FILL_PRICE} - {STOP_TICKS} "
                    f"x {TICK_SIZE} = {EXPECT_LEVEL}. A breach test against a stop at "
                    "an unexpected price measures a different position"
                ),
            )
        )
        return findings, seen

    # -- §7.12 #4: a price ABOVE the level must NOT fire ---------------------
    above = drive.price(level + 5.0)
    if not above.get("accepted"):
        raise Cannot(f"the daemon refused a price: {above.get('reason')}")
    status = drive.settle(0.6)
    block = _stops_block(status)
    prices = status.get("prices") or {}
    seen["published_after_control"] = prices.get("published")
    seen["ring_head"] = (prices.get("head") or {}).get(SYMBOL)
    # NON-VACUITY (§7.12 #2 and #3): the price REACHED the ring and the poll RAN.
    if not prices.get("published"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the daemon reports prices={prices!r} after a "
                    "`price` command it accepted — nothing reached §5:322's ring, so "
                    "a stop that did not move measured an absent input, not an omission"
                ),
            )
        )
        return findings, seen
    if abs(float(seen["ring_head"] or 0.0) - (level + 5.0)) > 1e-9:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the ring's head for {SYMBOL} is "
                    f"{seen['ring_head']!r} and this gate pushed {level + 5.0} — the "
                    "poll is reading a price nobody sent"
                ),
            )
        )
        return findings, seen
    if not block.get("polls"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the daemon reports polls={block.get('polls')!r} — "
                    "§5:322's price poll never ran, so nothing below is about a "
                    "maintained stop"
                ),
            )
        )
        return findings, seen
    if block.get("breaches"):
        findings.append(
            (
                STOPWATCH_FILE,
                (
                    f"A STOP FIRED WITH PRICE ABOVE IT: price {level + 5.0} is on the "
                    f"SAFE side of the stop at {level} for a LONG, and the daemon "
                    f"reports breaches={block.get('breaches')!r}. §4 breaches a long "
                    "at `price <= level`; firing above it closes a live position that "
                    "was never stopped out"
                ),
            )
        )
        return findings, seen

    # -- ARM 1: cross it -----------------------------------------------------
    crossing = level - TICK_SIZE
    seen["crossing_price"] = crossing
    drive.price(crossing)
    try:
        status = drive.watch(
            lambda st: (st.get("stops") or {}).get("sends", 0) >= 1,
            "a protective flatten was fired and SENT",
        )
    except _Missed as miss:
        block = _stops_block(miss.status)
        findings.append(
            (
                STOPWATCH_FILE,
                (
                    f"THE DAEMON DID NOT FIRE A PROTECTIVE FLATTEN FOR AN UNPROTECTED "
                    f"POSITION. Order {CID!r} on {SYMBOL} filled at {FILL_PRICE} with "
                    f"its synthetic stop at {level}; price {crossing} is THROUGH that "
                    f"level and the daemon reports polls={block.get('polls')!r} "
                    f"breaches={block.get('breaches')!r} fires={block.get('fires')!r} "
                    f"sends={block.get('sends')!r} flattened={block.get('flattened')!r}. "
                    "§4:190-196 makes the breach the moment the protective exit fires; "
                    "a position sitting open with price past its stop is unprotected "
                    "in the running daemon (D3.451)"
                ),
            )
        )
        return findings, seen

    block = _stops_block(status)
    action = block.get("last_action") or {}
    seen.update(
        {
            "breaches": block.get("breaches"),
            "fires": block.get("fires"),
            "sends": block.get("sends"),
            "flattened": block.get("flattened"),
            "in_flight": block.get("in_flight"),
            "last_action": action,
            "refusals": block.get("refusals"),
            "sender_send_errors": block.get("sender_send_errors"),
            "loop_native_id": block.get("loop_native_id"),
            "sender_native_id": block.get("sender_native_id"),
            "sent_on_native_id": block.get("sent_on_native_id"),
            "crossing_price": crossing,
        }
    )
    findings.extend(_judge_one_fire(block, action, level, crossing))
    if findings:
        return findings, seen

    return _arm_fire_once(drive, seen, int(block.get("polls") or 0), level), seen


def _arm_fire_once(
    drive: Drive, seen: dict[str, Any], polls_at_fire: int, level: float
) -> list[tuple[str, str]]:
    """ARM 2. A breached position must NOT re-fire, across N further real polls.

    One tick proves nothing: a path that re-fired every tick would look
    identical after one look (§0a). So price is pushed further past the level
    several times and the three counters must still read exactly one.
    """
    findings: list[tuple[str, str]] = []
    for step in (1, 2, 4, 1):
        drive.price(level - TICK_SIZE * step)
        time.sleep(0.15)
    status = drive.settle(0.8)
    block = _stops_block(status)
    seen["polls_after"] = block.get("polls")
    seen["suppressed"] = block.get("suppressed")
    seen["sends_after"] = block.get("sends")
    seen["flattened_after"] = block.get("flattened")
    if int(block.get("polls") or 0) < polls_at_fire + FIRE_ONCE_POLL_FLOOR:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the poll advanced from {polls_at_fire} to "
                    f"{block.get('polls')!r}, fewer than the {FIRE_ONCE_POLL_FLOOR} "
                    "further polls this arm needs. A fire-once claim over a loop that "
                    "barely ticked is a claim about one tick (§0a)"
                ),
            )
        )
        return findings
    if int(block.get("sends") or 0) != 1 or list(block.get("flattened") or []) != [
        SYMBOL
    ]:
        findings.append(
            (
                STOPWATCH_FILE,
                (
                    f"DOUBLE-FLATTEN: after the breach for {CID!r} at {level}, "
                    f"{block.get('polls')!r} further poll(s) with price still past the "
                    f"level produced sends={block.get('sends')!r} and the broker "
                    f"recorded flattened={block.get('flattened')!r}. A breached "
                    "position is marked flatten-in-flight and must NOT re-fire: every "
                    "extra firing is an extra venue order against a position already "
                    "being closed (§4)"
                ),
            )
        )
    if not block.get("suppressed"):
        findings.append(
            (
                STOPWATCH_FILE,
                (
                    f"NON-VACUITY: suppressed={block.get('suppressed')!r} after "
                    f"{block.get('polls')!r} polls with price past the stop. `breached` "
                    "is a READ that returns the stop on every tick, so a fire-once "
                    "claim needs the suppression to have actually happened — zero means "
                    "the re-breach never occurred and nothing was suppressed"
                ),
            )
        )
    return findings


def _judge_one_fire(  # pylint: disable=too-many-branches
    block: dict[str, Any], action: dict[str, Any], level: float, crossing: float
) -> list[tuple[str, str]]:
    """The ONE-flatten judgement, from three independent counters (§7.12 #5)."""
    findings: list[tuple[str, str]] = []
    fires = int(block.get("fires") or 0)
    sends = int(block.get("sends") or 0)
    flattened = list(block.get("flattened") or [])
    if not (fires == sends == 1 and flattened == [SYMBOL]):
        findings.append(
            (
                STOPWATCH_FILE,
                (
                    f"the breach of {CID!r} at {level} by price {crossing} produced "
                    f"fires={fires} (the loop), sends={sends} (the sender thread) and "
                    f"flattened={flattened} (the BROKER's own record). §4 fires ONE "
                    "protective flatten per breach and all three must read exactly one "
                    f"{SYMBOL}; three counters that disagree mean the send and the "
                    "detection are counting different events"
                ),
            )
        )
    if action.get("trigger") != "synthetic_stop":
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the flatten was fired under trigger {action.get('trigger')!r}; a "
                    "stop-out is §3:169's `synthetic_stop` and the trigger is what the "
                    "§12.10 row and every downstream consumer attribute the close to"
                ),
            )
        )
    if action.get("executed") != [True]:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the protective close reports executed={action.get('executed')!r} "
                    f"and dropped={action.get('dropped')!r} — §4's arbiter did not "
                    "execute the close, so the flatten was decided and not issued"
                ),
            )
        )
    if abs(float(action.get("level", 0.0)) - level) > 1e-9:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the flatten names level={action.get('level')!r} and the daemon's "
                    f"own stop is at {level} — the firing is attributed to a stop that "
                    "is not the one that breached"
                ),
            )
        )
    if block.get("refusals"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the sender REFUSED the firing: {block.get('refusals')!r}. A "
                    "detected breach that could not be fired leaves the position open "
                    "with price past its stop"
                ),
            )
        )
    if block.get("sender_send_errors"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"§5:323's sender raised on the send: "
                    f"{block.get('sender_send_errors')!r} — the protective flatten was "
                    "enqueued and did not reach the broker"
                ),
            )
        )
    if list(block.get("in_flight") or []) != [CID]:
        findings.append(
            (
                STOPWATCH_FILE,
                (
                    f"the breached position is in_flight={block.get('in_flight')!r} and "
                    f"must be [{CID!r}] — the fire-once mark is what stops the next "
                    "tick issuing a second flatten, and an unmarked position will"
                ),
            )
        )
    return findings


# R0911: same ladder, same reason — every early return names a DISTINCT way the
# trail can be wrong (armed at the wrong level, did not tighten, the latch did not
# set, the retrace was not a retrace, it loosened, the high-water retreated, it
# fired above itself). Collapsing them would put seven defects behind one sentence.
def _trail_tighten_and_retrace(  # pylint: disable=too-many-return-statements
    ring: Any, book: Any, watch: Any, advance: float
) -> tuple[Any, float, str]:
    """`(tightened, retrace, complaint)` — the TIGHTEN, then the retrace that must not loosen.

    The tighten comes FIRST and its failure is its own complaint, because
    "it did not loosen" over a stop that never moved is vacuous (§7.12 #6).
    """
    ring.publish(SYMBOL, advance)
    watch.poll(1)
    tightened = book.get("csm-trail")
    expect_trail = advance - TRAIL_TICKS * TICK_SIZE
    if tightened is None or tightened.level != expect_trail:
        return (
            None,
            0.0,
            (
                f"a favourable advance to {advance} left the stop at "
                f"{None if tightened is None else tightened.level!r}; §4:190-196 "
                f"ratchets it to high_water - trail x tick = {expect_trail}. The "
                "trail did not TIGHTEN, so 'it did not loosen' would be vacuous "
                "(§7.12 #6)"
            ),
        )
    if not tightened.activated:
        return (
            None,
            0.0,
            (
                "the trail moved but `activated` did not latch — §4's activation "
                "is a LATCH and a stop that re-decides it from the current price "
                "can de-activate on a retrace and give ground back"
            ),
        )

    # THE RETRACE: below the high-water, ABOVE the trailed level.
    retrace = tightened.level + 3 * TICK_SIZE
    if not advance > retrace > tightened.level:
        return (
            None,
            0.0,
            (
                f"the retrace price {retrace} is not strictly between the "
                f"high-water {advance} and the trailed level {tightened.level} — "
                "this arm would be testing something other than a retrace"
            ),
        )
    ring.publish(SYMBOL, retrace)
    watch.poll(2)
    after = book.get("csm-trail")
    if after is None or after.level != tightened.level:
        return (
            None,
            retrace,
            (
                f"THE TRAIL LOOSENED. Price retraced from {advance} to {retrace} "
                "— still ABOVE the trailed level — and the stop moved from "
                f"{tightened.level} to {None if after is None else after.level!r}. "
                "§4:190-196: the stop only ever moves in the strategy's favour and "
                "NEVER gives ground back; a loosening trail hands back locked-in "
                "protection at the worst moment"
            ),
        )
    if after.high_water != advance:
        return (
            None,
            retrace,
            (
                f"THE HIGH-WATER RETREATED from {advance} to {after.high_water!r}. "
                "It is monotone in the favourable direction by construction, and a "
                "high-water that retreats implies a trail level that retreats"
            ),
        )
    if watch.breaches:
        return (
            None,
            retrace,
            (
                f"a retrace to {retrace}, ABOVE the trailed level "
                f"{tightened.level}, reported {watch.breaches} breach(es) — §4 "
                "breaches a long at `price <= level` and firing above it closes a "
                "live position"
            ),
        )
    return tightened, retrace, ""


def _trail_walk(
    ring: Any, book: Any, watch: Any, advance: float, trailed: float
) -> tuple[int, str]:
    """`(steps, complaint)` — walk price DOWN and require the level not to fall.

    One retrace comparison is not monotonicity: a defect that ratchets off the
    CURRENT price instead of the monotone high-water shows up only when price
    walks DOWN, and `stops.py`'s own docstring names that implementation as the
    one the `activated` latch exists to forbid. MEASURED: a plant that merely
    widened `_tighter` was invisible to a single comparison, because the
    high-water is monotone and so is the level it implies. The sequence is what
    makes this arm see the defect the plant stands in for.
    """
    walk = trailed
    walked = 0
    for step in range(1, 9):
        step_price = advance - step * TICK_SIZE
        if step_price <= trailed:
            break
        ring.publish(SYMBOL, step_price)
        watch.poll(100 + step)
        now = book.get("csm-trail")
        if now is None or now.level < walk:
            return walked, (
                f"THE TRAIL LOOSENED ON A DESCENDING WALK. At price {step_price} "
                f"— still ABOVE the trailed level {trailed} — the stop moved from "
                f"{walk} to {None if now is None else now.level!r}. §4:190-196: "
                "the ratchet NEVER gives ground back, and a trail recomputed from "
                "the current price rather than the high-water is exactly how it does"
            )
        if now.high_water != advance:
            return walked, (
                f"THE HIGH-WATER RETREATED to {now.high_water!r} at price "
                f"{step_price}; it is monotone in the favourable direction by "
                f"construction and {advance} is the highest price ever published"
            )
        walk = now.level
        walked += 1
    if walked < 2:
        return walked, (
            f"the descending walk took {walked} step(s) above the trailed level "
            f"{trailed} — fewer than two, so 'the level never fell' is a "
            "statement about a sequence that barely existed"
        )
    if watch.breaches:
        return walked, (
            f"the descending walk, which stayed ABOVE the trailed level "
            f"{trailed} throughout, reported {watch.breaches} breach(es)"
        )
    return walked, ""


def _arm_monotonic(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-locals,too-many-statements
    nix_home: Path,
) -> tuple[list[str], str]:
    """ARM 3. `(evidence, complaint)` — the trail TIGHTENS and never LOOSENS.

    Over the SHIPPED `StopWatch.poll` and a real `StopBook`. See the module
    docstring on why this is not driven through the daemon's fill path (D3.474,
    measured) and on why ARM 4 is what keeps it non-vacuous.
    """
    sys.path.insert(0, str(nix_home / "scripts"))
    try:
        from nixrisk.seam import (  # pylint: disable=import-outside-toplevel
            ProposedOrder,
            Side,
            StopMode,
        )
        from nixrisk.stops import StopBook  # pylint: disable=import-outside-toplevel
        from nixrisk.stopwatch import (  # pylint: disable=import-outside-toplevel
            PriceRing,
            StopWatch,
        )
    except ImportError as exc:
        return [], f"the §4 trail modules do not import: {exc!r}"

    book = StopBook({SYMBOL: TICK_SIZE})
    ring = PriceRing()
    watch = StopWatch(ring, book)
    order = ProposedOrder(
        strategy_id=STRATEGY,
        client_order_id="csm-trail",
        symbol=SYMBOL,
        side=Side.LONG,
        qty=QTY,
        margin_per_contract=MARGIN,
        stop_ticks=STOP_TICKS,
        stop_mode=StopMode.TRAILING,
        signal_ts=time.time(),
    )
    armed = book.arm(FILL_PRICE, order, trail_ticks=TRAIL_TICKS)
    if abs(armed.level - EXPECT_LEVEL) > 1e-9:
        return [], (
            f"the trailing stop armed at {armed.level!r} and §4 anchors it at "
            f"{EXPECT_LEVEL} — the drive starts from the wrong level"
        )

    advance = FILL_PRICE + 3.0
    tightened, retrace, complaint = _trail_tighten_and_retrace(
        ring, book, watch, advance
    )
    if complaint:
        return [], complaint

    walked, complaint = _trail_walk(ring, book, watch, advance, tightened.level)
    if complaint:
        return [], complaint

    # THE CROSSING: through the TRAILED level, which is not the armed one.
    ring.publish(SYMBOL, tightened.level - TICK_SIZE)
    enqueued = watch.poll(3)
    fired = watch.drain()
    if enqueued != 1 or len(fired) != 1:
        return [], (
            f"crossing the TRAILED level {tightened.level} enqueued {enqueued} "
            f"firing(s) and drained {len(fired)} — a trailed stop that does not "
            "fire when it is taken out is the D3.451 defect one level up"
        )
    if abs(fired[0].level - tightened.level) > 1e-9:
        return [], (
            f"the firing names level={fired[0].level!r}; the stop that breached is "
            f"the TRAILED one at {tightened.level}, not the armed one at "
            f"{armed.level}. A protective exit attributed to the wrong level "
            "cannot be audited against the trail that produced it"
        )
    before_suppressed = watch.suppressed
    for step in range(4, 9):
        ring.publish(SYMBOL, tightened.level - TICK_SIZE * step)
        watch.poll(step)
    if watch.breaches != 1 or watch.drain():
        return [], (
            f"fire-once does NOT hold over a trailed breach: breaches="
            f"{watch.breaches}, and further polls enqueued more firings"
        )
    final = book.get("csm-trail")
    if final is None:
        return [], (
            "the trailed stop vanished from the book between the breach and the "
            "evidence read — there is nothing to report the trail's history from"
        )
    evidence = [
        (
            f"armed {armed.level} -> tightened {tightened.level} "
            f"(hwm {advance} - {TRAIL_TICKS} x {TICK_SIZE})"
        ),
        (
            f"retrace to {retrace} left the level at {final.level} and the "
            f"high-water at {final.high_water} (NO ground given back)"
        ),
        (
            f"crossing {tightened.level - TICK_SIZE} fired ONE firing naming "
            f"{fired[0].level}"
        ),
        (
            f"descending walk of {walked} step(s) above the trailed level: the "
            "level never fell and the high-water never retreated"
        ),
        (
            f"{watch.suppressed - before_suppressed} re-breach(es) suppressed, "
            f"breaches still {watch.breaches}"
        ),
    ]
    return evidence, ""


def _arm_offpath_and_wirefree(
    nix_home: Path, seen: dict[str, Any]
) -> tuple[list[str], list[tuple[str, str]], str]:
    """ARM 4. `(evidence, findings, complaint)` — I9's boundary and I3, re-proven."""
    evidence: list[str] = []
    findings: list[tuple[str, str]] = []

    loop_id = seen.get("loop_native_id")
    sender_id = seen.get("sender_native_id")
    ran_on = seen.get("sent_on_native_id")
    if not (
        isinstance(loop_id, int)
        and isinstance(sender_id, int)
        and isinstance(ran_on, int)
    ):
        return (
            evidence,
            findings,
            (
                f"the daemon reported loop={loop_id!r} sender={sender_id!r} "
                f"ran_on={ran_on!r} — three measured thread ids are needed before "
                "'the send was off the hot path' means anything (§7.12 #7)"
            ),
        )
    if ran_on != sender_id or ran_on == loop_id:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"THE PROTECTIVE FLATTEN WAS SENT ON THE HOT PATH. The send ran on "
                    f"native thread {ran_on}; §5:323's sender thread is {sender_id} and "
                    f"the loop is {loop_id}. `ProtectiveFlatten.fire` takes the §4 "
                    "arbitration lock and appends a §12.10 row, and §5:323 puts "
                    "blocking work on the sender precisely so *the hot loop never "
                    "blocks* — running it on the loop breaks I9, discharged at ARC 050"
                ),
            )
        )
    else:
        evidence.append(
            f"send ran on native tid {ran_on} = sender {sender_id} != loop {loop_id}"
        )

    # -- the daemon really composes this poll and this send (§7.12 #8) -------
    source = (nix_home / LIMITERD_FILE).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=LIMITERD_FILE)
    except SyntaxError as exc:
        return evidence, findings, f"{LIMITERD_FILE} does not parse: {exc}"
    composed = any(
        isinstance(node, ast.Attribute)
        and node.attr == "before"
        and isinstance(node.value, ast.Name)
        and node.value.id == "stopwatch"
        for node in ast.walk(tree)
    )
    handed = any(
        isinstance(node, ast.keyword)
        and node.arg == "sender_send"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "send"
        for node in ast.walk(tree)
    )
    if not (composed and handed):
        return (
            evidence,
            findings,
            (
                f"{LIMITERD_FILE} composes the price poll into its ingress: "
                f"{composed}; hands the fire to §5:323's sender: {handed}. Both "
                "must be true in the SOURCE, or ARM 3's library drive is about "
                "code the process does not run"
            ),
        )
    evidence.append("limiterd composes stopwatch.before(...) and sender_send=...send")

    # -- I3: the send closure touches no transport ---------------------------
    banned, complaint = _trace_send_roots(nix_home)
    if complaint:
        return evidence, findings, complaint
    if banned:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "THE PROTECTIVE EXIT ACQUIRED A WIRE: "
                    + "; ".join(banned)
                    + ". §14 "
                    "gives the protective path ZERO delivery dependency — it fires when "
                    "the Allocator is down, the bus is down and the sockets are gone. A "
                    "transport on this path removes the one guarantee that makes the "
                    "exit trustworthy (I3, discharged at ARC 048)"
                ),
            )
        )
    else:
        evidence.append("send path traced: no transport root entered (I3 preserved)")
    return evidence, findings, ""


# R0914: the locals are the SEVEN collaborators `ProtectiveFlatten` requires
# plus the three stand-ins `StopWatchDriver.send` reads. Every one is named
# because the point of this arm is that the send path is assembled EXACTLY as
# the daemon assembles it.
def _trace_send_roots(  # pylint: disable=too-many-locals
    nix_home: Path,
) -> tuple[list[str], str]:
    """`(banned, complaint)` — module roots the daemon's SEND CLOSURE enters.

    Driven in-process with `sys.setprofile`, the mechanism `check_flatten` ARM 6
    uses for the same property over a different subject. The subject HERE is
    `limiterd.StopWatchDriver.send` — the closure §5:323's thread actually runs —
    which ARM 6 cannot see because it never imports `limiterd`.
    """
    sys.path.insert(0, str(nix_home / "scripts"))
    try:
        import limiterd as daemon  # pylint: disable=import-outside-toplevel
        from nixrisk.flatten import (  # pylint: disable=import-outside-toplevel
            BrokerFlattenPort,
            ProtectiveFlatten,
        )
        from nixrisk.picture import (  # pylint: disable=import-outside-toplevel
            FinancialPictureBook,
        )
        from nixrisk.positions import (  # pylint: disable=import-outside-toplevel
            EntryOrderOrigins,
        )
        from nixrisk.reservations import (  # pylint: disable=import-outside-toplevel
            ReservationLedger,
        )
        from nixrisk.seam import (  # pylint: disable=import-outside-toplevel
            ProposedOrder,
            Side,
            StopMode,
        )
        from nixrisk.stopwatch import (  # pylint: disable=import-outside-toplevel
            BreachFiring,
        )
        from nixrisk.wal import Plane1Wal  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return [], f"the send path does not import: {exc!r}"

    class _Sink:
        """A §4 fan-out sink that records. The COMPLETION path is ARC D's."""

        def on_closed(self, *_a: object, **_k: object) -> None:
            """Recorded, not raised: this arm traces the FIRE, not the fan-out."""

        def book_realized(self, *_a: object, **_k: object) -> None:
            """Same."""

    tmp = Path(tempfile.mkdtemp(prefix="csm-wire-"))
    venue = daemon.RecordedVenue()
    if not hasattr(venue, "flatten"):
        return [], (
            "the daemon's broker has no `flatten` verb, so there is no send to "
            "trace — the protective exit cannot fire even in principle"
        )
    wal = Plane1Wal(tmp / "plane1.wal")
    exits = ProtectiveFlatten(
        # `cast`, for `limiterd.main`'s own reason: `RecordedVenue` has the two
        # SYNC verbs the protective path calls and not the two ASYNC reconcile
        # reads, which is the state ARC 055 ships and ARC D changes.
        broker=cast(BrokerFlattenPort, venue),
        ledger=ReservationLedger(wal),
        picture=FinancialPictureBook(balance=BALANCE, deployable_fraction=0.70),
        strategy=_Sink(),
        plane1=wal,
        scoring=_Sink(),
        clock=time.time,
    )
    origins = EntryOrderOrigins()
    order = ProposedOrder(
        strategy_id=STRATEGY,
        client_order_id="csm-wire",
        symbol=SYMBOL,
        side=Side.LONG,
        qty=QTY,
        margin_per_contract=MARGIN,
        stop_ticks=STOP_TICKS,
        stop_mode=StopMode.FIXED,
        signal_ts=time.time(),
    )
    origins.record(order)

    class _Fills:  # pylint: disable=too-few-public-methods
        """The one collaborator `StopWatchDriver.send` reads: the trade join."""

        def __init__(self) -> None:
            self.origins = origins

    class _Watch:
        """`StopWatchDriver` holds one; `send` never touches it. Declared, unused."""

        polls = maintained = breaches = suppressed = 0

        def in_flight(self) -> tuple[str, ...]:
            """Never called by `send`; present so the driver constructs."""
            return ()

        def pending(self) -> tuple[object, ...]:
            """Never called by `send`; present so the driver constructs."""
            return ()

    class _Loop:  # pylint: disable=too-few-public-methods
        """Only `sender` is read, and only by `record()`. `send` never touches it."""

        sender = None

    # `cast`, and the casts are the statement: this arm traces `send`, which
    # reads exactly ONE collaborator (`fills.origins`) and touches neither the
    # watch nor the loop. Handing it real ones would put a `StopBook` and a
    # `LimiterLoop` inside the trace and make the census about them.
    driver = daemon.StopWatchDriver(
        cast(Any, _Watch()), exits, cast(Any, _Loop()), cast(Any, _Fills())
    )
    firing = BreachFiring(
        client_order_id="csm-wire",
        symbol=SYMBOL,
        side=Side.LONG,
        level=EXPECT_LEVEL,
        price=EXPECT_LEVEL - TICK_SIZE,
        tick=1,
    )
    roots: set[str] = set()

    def _profile(frame: Any, event: str, _arg: Any) -> None:
        if event != "call":
            return
        name = frame.f_globals.get("__name__", "")
        roots.add(name.split(".")[0] if name else "?")

    sys.setprofile(_profile)
    try:
        driver.send(firing)
    finally:
        sys.setprofile(None)

    if driver.sends != 1 or list(venue.flattened) != [SYMBOL]:
        return [], (
            f"the traced send produced sends={driver.sends} and "
            f"flattened={list(venue.flattened)!r} — the trace is over a send that "
            "did not happen, so its silence about wires means nothing"
        )
    return (
        sorted(
            f"{root} — {_BANNED_ON_SEND[root]}"
            for root in roots
            if root in _BANNED_ON_SEND
        ),
        "",
    )


def _measure(nix_home: Path) -> CheckResult:
    """Every arm, in order. CANNOT_MEASURE whenever the subject was unreachable."""
    drive: Drive | None = None
    try:
        drive = Drive(nix_home)
        findings, seen = _arm_fires(drive)
    except Cannot as exc:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, site=LIMITERD_FILE, detail=str(exc)
        )
    finally:
        if drive is not None:
            try:
                drive.close()
            except Cannot:
                pass

    trail_evidence, complaint = _arm_monotonic(nix_home)
    if complaint and not findings:
        # A trail defect is a FAIL, not a cannot-measure: the drive ran and the
        # subject answered. The complaint carries §4's coordinate.
        findings.append((STOPWATCH_FILE, f"§4:190-196 — {complaint}"))

    off_evidence: list[str] = []
    if not findings:
        off_evidence, off_findings, off_complaint = _arm_offpath_and_wirefree(
            nix_home, seen
        )
        if off_complaint:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=LIMITERD_FILE,
                detail=f"ARM 4: {off_complaint}",
            )
        findings.extend(off_findings)

    evidence = (
        f"ARM 1 driven `limiterd`: stop armed at {seen.get('armed_level')!r} "
        f"(= {FILL_PRICE} - {STOP_TICKS} x {TICK_SIZE}); ring published "
        f"{seen.get('published_after_control')!r} head={seen.get('ring_head')!r}; "
        f"price {seen.get('crossing_price')!r} crossed it -> "
        f"fires={seen.get('fires')!r} sends={seen.get('sends')!r} "
        f"broker flattened={seen.get('flattened')!r} "
        f"in_flight={seen.get('in_flight')!r} action={seen.get('last_action')!r} | "
        f"ARM 2 fire-once: polls {seen.get('polls_after')!r}, "
        f"suppressed={seen.get('suppressed')!r}, still sends="
        f"{seen.get('sends_after')!r} flattened={seen.get('flattened_after')!r} | "
        f"ARM 3 monotonic trail: {'; '.join(trail_evidence) or 'NOT PROVEN'} | "
        f"ARM 4: {'; '.join(off_evidence) or 'NOT PROVEN'}"
    )
    if findings:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(sorted({site for site, _ in findings})),
            detail="; ".join(why for _, why in findings),
            evidence=evidence,
            action=(
                "the daemon must poll §5:322's price ring on the tick, ratchet "
                "§4:190-196's trails toward price WITHOUT ever loosening one, and "
                "fire EXACTLY ONE protective flatten per breach on §5:323's sender "
                "thread. This gate never edits its subject (CORRECTABLE=False)"
            ),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the running Limiter maintains its stops and fires once. Never repairs."""
    try:
        return _measure(Path(ctx.nix_home))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation this gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
