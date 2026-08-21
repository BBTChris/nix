#!/usr/bin/env python3
# C0302: over the 1000-line default. The overage is the §7.12 block, the
# producer-completeness DERIVATION and the per-finding reason sentences, which
# check contract v2 rule 11 makes the assertion rather than decoration.
# pylint: disable=too-many-lines
"""ARC 057 / I1 ARC C2 — §14's UNCERTAINTY PRODUCERS: WHAT CANNOT BE PROTECTED
IS FLATTENED, AND THE SET OF SUCH CONDITIONS IS COMPLETE BY DERIVATION.

THE SUBJECT, AND WHY IT IS A NEW GATE RATHER THAN AN ARM ON AN OLD ONE
----------------------------------------------------------------------------
§14 is one sentence with two halves: *every uncertainty resolves toward FLAT;
known state beats optimal state*. ARC 055 (I1 ARC C1) wired the first named
protective exit — a breached synthetic stop fires one flatten — and
`check_stop_maintenance` owns it. What that gate does NOT own, and what nothing
in this tree owned before this file, is the OTHER class: the conditions under
which this process holds, or the venue holds, a position it can neither protect
nor account for, and which therefore has no stop to breach.

The census this gate was opened against, run at ARC 057 / stage 1 and recorded
here so a later reader can re-run it rather than trust it:

* `check_flatten` — `SUBJECTS = ("scripts/nixrisk/flatten.py",)`. It owns the
  EXECUTOR as a LIBRARY: §14's zero-wire property (ARM 1/6), §4's dual-authority
  precedence (ARM 2), §3:173's onset selectivity (ARM 3/3b), §4's reconcile
  (ARM 4). Every arm drives `nixrisk.flatten` directly. It owns no producer and
  spawns no daemon.
* `check_stop_maintenance` — the daemon's §4:187-196 TRAIL and the
  `SYNTHETIC_STOP` breach->flatten path. A different CONDITION CLASS: a stop
  that breached is a position that WAS protected and whose protection fired.
* `check_limiter_daemon_dispatch` — the daemon's fill / reject / pending-timeout
  DISPATCH. It measures that the cascade RAN; it says nothing about what §14
  owes a position the cascade REFUSED.

So doctrine C.9 is respected rather than argued around: no arm here duplicates
an instrument the suite already drives over the same subject-property pair.
What is new is the pair itself — *the daemon's set of uncertainty producers,
and its completeness*.

WHAT IS MEASURED
----------------------------------------------------------------------------
* **ARM 1 — EACH OF THE FOUR PRODUCERS FIRES, DRIVEN THROUGH THE DAEMON.** A
  real `limiterd` subprocess, a real reservation, a real §2A completion or a
  real status answer on disk, and the condition genuinely established before
  anything is asserted. Never a direct call into the producer: ARC 038's
  deepest finding was that every Limiter invariant in this tree had been proven
  about a library a test constructed, and a producer proven by calling it is
  that finding restated.
* **ARM 2 — FIRE-ONCE.** Every one of these conditions PERSISTS — a stale feed
  stays stale, an un-armable fill stays in `unarmable()` — so the naive wiring
  is one venue `flatten` per tick against one position. The condition is left
  standing for a floor of further ticks and the count must not move.
* **ARM 3 — D3.469's BOTH BRANCHES.** The bounded reconciliation window is the
  one producer that must NOT fire on detection: a `filled` status answer whose
  execution report is merely delayed is the common case, and flattening on it
  kills a healthy position. So both branches are driven — exec report inside the
  window ⇒ CONVERT and no flatten; deadline first ⇒ flatten — and the
  inside-the-window silence is asserted, not assumed.
* **ARM 4 — PRODUCER COMPLETENESS, BY DERIVATION.** The set of conditions the
  daemon flattens is read from `limiterd.py`'s OWN `UncertaintyCondition` enum
  by AST, and compared against the set the RUNNING process publishes and against
  the set this gate drove. A member with no producer is a FAIL naming it. This
  is the arm the gate exists for: the defect is not a producer that misfires, it
  is a FIFTH unprotectable condition added later with no producer at all — which
  is precisely the state all four of these were in until ARC 057, and which no
  instrument in the tree could see (`check_uncalled_entry_points` looks for
  uncalled ENTRY POINTS, not for unreachable enum members — D3.453's own words).
* **ARM 5 — I9 AND I3, over this arc's NEW code.** The per-tick stale-open scan
  is new hot-path work and I9 is a DISCHARGED invariant, so the scan is traced
  under a MEASURED allow-set and its position count is bounded at §15's five.
  The send is traced under I3's ban-set: §14 gives the protective path zero
  wire/delivery dependency, and every send here is a fire the daemon really
  made.
* **ARM 6 — THE UNCLASSIFIABLE CASE IS CANNOT_MEASURE, NEVER PASS.** The daemon
  publishes `unclassified`: refused fill dispatches it could not put into any
  member of the condition set. A non-empty list means a confirmed venue fill was
  refused and nothing decided whether §14 owed it a flatten. Check contract rule
  10: a safety property whose subject could not be classified has not been
  proven, so this is CANNOT_MEASURE naming the site.

§7.12 — THE STANDING QUESTION: HOW COULD THIS GATE BE GREEN AND THE PROPERTY
FALSE?
----------------------------------------------------------------------------
 1. **Nothing was ever open, so "flattened" is vacuous.** GUARDED: ARM 1 proves
    the CONDITION first out of the daemon's own record — a published §3 row for
    the stale case, `write_refusals` for the not-tradable case, `arm_refusals`
    for the un-armable case, an opened window for the poll case — and refuses to
    assert anything until it holds.
 2. **Something had already fired before the drive touched anything.** GUARDED:
    every arm reads `sends` and the BROKER's own `flattened` list at boot and
    refuses if either is non-empty. A count that moved before this gate acted is
    a count of something it did not cause.
 3. **The flatten was "sent" but the broker never saw it.** GUARDED: the verdict
    is taken from the BROKER's own `flattened` record, on the far side of the
    call — check contract rule 2, one layer out: the return value of a mutating
    call is not a verification, and the driver's `sends` is exactly such a value.
 4. **Fire-once "held" because the condition stopped holding.** GUARDED: ARM 2
    requires the daemon's own `scans` counter to advance by a floor before it
    will read a stable count as fire-once, and the conditions it uses are ones
    that cannot self-clear.
 5. **The gate drove a producer directly.** GUARDED: no condition above is
    established by calling into a producer — every one is set up by writing a
    file the daemon reads or sending a command it answers, and every verdict is
    read out of the daemon's own status reply. The ONE in-process import is
    ARM 5's tracer, and it measures the SHAPE of two paths (which module roots
    they enter, how many positions the scan touches) rather than establishing
    any condition — the same separation `check_stop_maintenance` ARM 3/ARM 4
    keep between a library drive and a daemon drive.
 6. **The condition set is whatever this gate happens to list.** GUARDED: ARM 4
    DERIVES it from the subject's own AST and from the running process, and this
    file contains no hand-written copy of the set to go stale. That is
    `check_flatten` ARM 6's argument, applied to producers instead of triggers.
 7. **The send was on the hot path and nobody looked.** GUARDED: ARM 5 compares
    the sending thread's native id against the loop's, read from INSIDE the send.
 8. **The daemon does not actually hold these producers**, so the drive is about
    code the process does not run. GUARDED: ARM 4 derives from `limiterd.py`'s
    own AST that the scan is composed into the ingress and that the fan-out
    object really reaches §5:323's `sender_send`.

NON-CORRECTABLE, AND THE REASON IS THE SAME AS `check_stop_maintenance`'s. The
subject is risk-path source — the producers that decide whether an unprotectable
position is closed. A gate empowered to edit them until its own drive came back
clean would be manufacturing green over the mechanism that closes a position
nothing else protects.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess  # nosec B404
import sys
import tempfile
import time
from datetime import UTC
from pathlib import Path
from typing import Any, Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
EXPECTED_S = 60.0
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
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (§14's uncertainty producers — the four "
    "conditions under which a position this process cannot protect or account "
    "for is closed). A repair that edited a producer to satisfy its own gate "
    "would be manufacturing green over the mechanism that closes a position "
    "nothing else protects"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/limiterd.py",
    # The detection seams the producers READ. Declared for the reason
    # `check_limiter_daemon_dispatch` declares `fills.py`: the property measured
    # is *the running Limiter flattens what it cannot protect*, and a plant in
    # any of these three detectors must redden this gate — which it cannot do if
    # the file is not its subject. This arc edited NONE of them and that is
    # asserted with `git hash-object`, not claimed.
    "scripts/nixrisk/freshness.py",
    "scripts/nixrisk/fills.py",
    "scripts/nixrisk/outcomes.py",
)

NAME = "check_uncertainty_flatten"

LIMITERD_FILE: Final[str] = "scripts/limiterd.py"

# -- what this gate SENDS IN --------------------------------------------------
SYMBOL: Final[str] = "ES"
#: NEVER reserved, so it is absent from §3's published margin field set and the
#: origin write refuses it as not-tradable (§4:198). That is D3.372's condition.
OTHER: Final[str] = "NQ"
TICK_SIZE: Final[float] = 0.25
STOP_TICKS: Final[int] = 8
FILL_PRICE: Final[float] = 5000.0
QTY: Final[int] = 2
MARGIN: Final[float] = 500.0
BALANCE: Final[float] = 250_000.0
STRATEGY: Final[str] = "check-uncertainty-flatten"

DRIVE_TICK_S: Final[float] = 0.02
DRIVE_HEARTBEAT_S: Final[float] = 0.2
DRIVE_MAX_TICKS: Final[int] = 20_000
BOOT_TIMEOUT_S: Final[float] = 30.0
REPLY_TIMEOUT_S: Final[float] = 20.0
WATCH_HORIZON_S: Final[float] = 25.0
#: D3.469's window for THIS gate's drives. Passed on the command line for the
#: reason `--go-timeout` is overridable: the shipped value is what an operator
#: tuned, and a gate that waited it out would spend its budget sleeping.
DRIVE_WINDOW_S: Final[float] = 2.0
#: How many further per-tick scans ARM 2 watches past the fire before it will
#: say fire-once held. One tick proves nothing: a producer that re-fired every
#: tick would look identical after one look.
FIRE_ONCE_SCAN_FLOOR: Final[int] = 20

#: §14's word, carried on every one of these flattens. Not derived from the
#: daemon: it is the SPEC's word (§3:169's trigger list, §4:301's cooldown
#: ladder) and reading it back off the subject would be the subject grading
#: itself.
UNCERTAINTY_REASON: Final[str] = "uncertainty"

#: Module roots the DAEMON'S SEND may not enter. I3's ban-set, borrowed verbatim
#: from `check_stop_maintenance` because it is the same property over the same
#: boundary: §14 gives the protective path ZERO wire/delivery dependency.
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

#: §15's bound. The stale-open scan may look at no more than this many positions
#: in one tick — §7 scopes this system to five top-liquid instruments.
MAX_POSITIONS: Final[int] = 5


class Cannot(RuntimeError):
    """The subject could not be reached. CANNOT_MEASURE, never PASS (rule 10)."""


class _Missed(RuntimeError):
    """A watched condition never arrived. Carries the last status it saw."""

    def __init__(self, what: str, status: dict[str, Any]) -> None:
        self.what = what
        self.status = status
        super().__init__(what)


class Drive:
    """One `limiterd` process and every path into it. Torn down always."""

    def __init__(self, nix_home: Path, *, window_s: float = DRIVE_WINDOW_S) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="check-uncertainty-flatten-"))
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
                    "--reconcile-window",
                    str(window_s),
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
    def atomically(path: Path, payload: dict[str, Any]) -> Path:
        """Write one JSON file the daemon may be scanning on its own tick."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".partial")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
        return path

    def cmd(self, verb: str, **fields: object) -> dict[str, Any]:
        """Send one command file; return the daemon's own reply."""
        self._n += 1
        cid = f"cuf{self._n:05d}"
        self.atomically(
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

    def reserve(self, cid: str, **over: object) -> dict[str, Any]:
        """§3's take-at-approval, with this gate's own numbers."""
        fields: dict[str, Any] = {
            "strategy_id": STRATEGY,
            "client_order_id": cid,
            "symbol": SYMBOL,
            "side": "long",
            "qty": QTY,
            "margin_per_contract": MARGIN,
            "stop_ticks": STOP_TICKS,
            "stop_mode": "fixed",
            "signal_ts": time.time(),
        }
        fields.update(over)
        return self.cmd("reserve", **fields)

    def fill(self, cid: str, *, symbol: str = SYMBOL) -> Path:
        """One §2A confirmed fill, through the completion directory."""
        return self.atomically(
            self.dir / "completions" / f"fill-{cid}.json",
            {
                "schema": 1,
                "event": "on_fill",
                "client_order_id": cid,
                "exec_id": f"x-{cid}",
                "done_qty": QTY,
                "symbol": symbol,
                "price": FILL_PRICE,
                "cumulative_qty": QTY,
            },
        )

    def status_answer(self, cid: str, state: str) -> Path:
        """One §2A `OrderStatus` answer, through the status directory."""
        return self.atomically(
            self.dir / "status" / f"{cid}.json",
            {
                "client_order_id": cid,
                "state": state,
                "terminal": True,
                "cumulative_qty": QTY,
            },
        )

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
        """Let real ticks elapse, then return the LAST status. Never raises."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            time.sleep(0.05)
        return self.cmd("status")

    def close(self) -> None:
        """SIGTERM and join. Called from a `finally` on every path."""
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


# --------------------------------------------------------------------------
# Reading the daemon's own record
# --------------------------------------------------------------------------


def _block(status: dict[str, Any]) -> dict[str, Any]:
    """The daemon's §14 uncertainty block, or a raise. `None` is CANNOT_MEASURE."""
    block = status.get("uncertainty")
    if block is None:
        raise Cannot(
            f"{LIMITERD_FILE}: this build's status reply carries no "
            "`uncertainty` block — the daemon holds no §14 uncertainty "
            "producers at all, so there is no subject for this gate "
            "(D3.453/D3.372/D3.469/D3.475)"
        )
    return block


def _actions(status: dict[str, Any], condition: str) -> list[dict[str, Any]]:
    """Every uncertainty flatten the daemon fired under one condition."""
    return [
        action
        for action in _block(status).get("actions") or ()
        if action.get("condition") == condition
    ]


def _quiet_start(drive: Drive) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """§7.12 #2: NOTHING may have fired before this gate touched anything."""
    findings: list[tuple[str, str]] = []
    status = drive.cmd("status")
    block = _block(status)
    if block.get("sends") or block.get("flattened") or block.get("actions"):
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NON-VACUITY: the daemon reports sends={block.get('sends')!r} "
                    f"flattened={block.get('flattened')!r} before this gate "
                    "established any condition — a later 'exactly one' would be "
                    "counting something this gate did not cause"
                ),
            )
        )
    return findings, status


# --------------------------------------------------------------------------
# ARM 1 + ARM 2 — each producer FIRES, once, driven through the daemon
# --------------------------------------------------------------------------


def _establish_stale_open(drive: Drive) -> str:
    """D3.453: a REAL open position whose price feed then goes quiet."""
    drive.cmd("register", strategy_id=STRATEGY)
    took = drive.reserve("cuf-stale")
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reservation: {took.get('reason')}")
    drive.fill("cuf-stale")
    try:
        status = drive.watch(
            lambda st: (st.get("fills") or {}).get("positions"),
            "a published §3 position row",
        )
    except _Missed as miss:
        raise Cannot(
            f"{LIMITERD_FILE}: no §3 row was published for a §2A fill, so there "
            "is no OPEN position for §6.4's flatten-open half to be about. Last "
            f"`fills` block: {(miss.status.get('fills') or {})!r}"
        ) from miss
    rows = (status.get("fills") or {}).get("positions") or []
    open_rows = [row for row in rows if row.get("state") == "open"]
    if not open_rows:
        raise Cannot(
            f"{LIMITERD_FILE}: the §3 table holds {rows!r} and none is OPEN — "
            "the stale-open condition is about an OPEN position"
        )
    # The feed is ALIVE first, and that is load-bearing: a symbol nothing has
    # ever priced is `CacheState.EMPTY`, which this daemon deliberately does NOT
    # flatten on (D3.473 — there is no capture feed in this tree, so EMPTY is
    # every symbol's state and firing on it would report the absence of a feed
    # as a position hazard). What is asserted below is a feed that WAS observed
    # and went QUIET.
    published = drive.price(FILL_PRICE)
    if not published.get("accepted"):
        raise Cannot(f"the daemon refused a price: {published.get('reason')}")
    status = drive.settle(0.3)
    if not _block(status).get("price_feed_observations"):
        raise Cannot(
            f"{LIMITERD_FILE}: the daemon accepted a `price` and recorded ZERO "
            "freshness observations, so §6.4's detector was never fed and a "
            "later 'stale' would be measuring an absent input, not a quiet feed"
        )
    return str(open_rows[0].get("trade_id") or "")


def _establish_not_tradable(drive: Drive) -> str:
    """D3.372: a confirmed fill whose ORIGIN WRITE refuses (§4:198)."""
    drive.cmd("register", strategy_id=STRATEGY)
    took = drive.reserve("cuf-untradable")
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reservation: {took.get('reason')}")
    before = int((drive.cmd("status").get("fills") or {}).get("write_refusals") or 0)
    if before:
        raise Cannot(
            f"{LIMITERD_FILE}: write_refusals={before} before this gate pushed "
            "any fill — the condition below would not be this gate's"
        )
    # The venue reports the fill in a symbol this Limiter never approved, so the
    # symbol is absent from §3's published margin field set and `positions.py`
    # raises `UntradableSymbol` inside `_row` — AFTER `_ledger.ingest` has booked
    # the fill. That is D3.372's measured shape, reproduced through the daemon.
    drive.fill("cuf-untradable", symbol=OTHER)
    try:
        drive.watch(
            lambda st: int((st.get("fills") or {}).get("write_refusals") or 0) > before,
            "the origin write to REFUSE the fill",
        )
    except _Missed as miss:
        raise Cannot(
            f"{LIMITERD_FILE}: the origin write never refused a fill in "
            f"{OTHER!r}, so D3.372's condition was not established. Last "
            f"`fills` block: {(miss.status.get('fills') or {})!r}"
        ) from miss
    return "cuf-untradable"


def _establish_unarmable(drive: Drive) -> str:
    """D3.475: a fill whose §4 stop conversion is REFUSED. The VENUE half."""
    drive.cmd("register", strategy_id=STRATEGY)
    # A TRAILING order carrying NO trail distance. ARC 056 releases the
    # reservation and refuses the whole cascade; the venue keeps the position.
    took = drive.reserve("cuf-unarmable", stop_mode="trailing")
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reservation: {took.get('reason')}")
    drive.fill("cuf-unarmable")
    try:
        status = drive.watch(
            lambda st: int((st.get("fills") or {}).get("arm_refusals") or 0) > 0,
            "§4's stop conversion to be REFUSED",
        )
    except _Missed as miss:
        raise Cannot(
            f"{LIMITERD_FILE}: §4's conversion never refused a trailing fill "
            "carrying no trail distance, so D3.475's condition was not "
            f"established. Last `fills` block: {(miss.status.get('fills') or {})!r}"
        ) from miss
    if not (status.get("fills") or {}).get("unarmable"):
        raise Cannot(
            f"{LIMITERD_FILE}: arm_refusals moved but `unarmable` is empty, so "
            "there is no named order for §14 to be about"
        )
    return "cuf-unarmable"


def _establish_poll_fill(drive: Drive) -> str:
    """D3.469: the pending-timeout poll sees `filled` and cannot convert."""
    drive.cmd("register", strategy_id=STRATEGY)
    took = drive.reserve("cuf-pollfill")
    if not took.get("accepted"):
        raise Cannot(f"the daemon refused the reservation: {took.get('reason')}")
    drive.status_answer("cuf-pollfill", "filled")
    try:
        drive.watch(
            lambda st: _block(st).get("windows_opened"),
            "the bounded reconciliation window to OPEN",
        )
    except _Missed as miss:
        raise Cannot(
            f"{LIMITERD_FILE}: a `filled` status answer opened NO reconciliation "
            "window, so D3.469's condition was not established. Last `timeouts` "
            f"block: {(miss.status.get('timeouts') or {})!r}"
        ) from miss
    # An immediate flatten is NOT refused here, and the restraint is deliberate.
    # For ARM 1 a fire is what is being asked for; firing TOO EARLY is a defect
    # of the WINDOW, which is ARM 3's subject, and raising here would report it
    # as *this gate could not measure* rather than as *the daemon killed a
    # position whose exec report was merely delayed*. Measured at ARC 057 / S4b:
    # PLANT B (deadline = the instant the window opened) exited 2 through this
    # raise until it was moved, and a defect downgraded to CANNOT_MEASURE is a
    # defect that never names itself.
    return "cuf-pollfill"


#: Each condition, the setup that ESTABLISHES it through the daemon, and the
#: debt row it discharges. The KEYS are compared against the daemon's own
#: derived set in ARM 4 — this table is the gate's coverage, never its authority.
_PRODUCERS: Final[tuple[tuple[str, Any, str], ...]] = (
    ("stale_open", _establish_stale_open, "D3.453"),
    ("not_tradable_fill", _establish_not_tradable, "D3.372"),
    ("unarmable_fill", _establish_unarmable, "D3.475"),
    ("undetailed_poll_fill", _establish_poll_fill, "D3.469"),
)


def _fires_once(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-locals
    nix_home: Path, condition: str, establish: Any, debt: str
) -> tuple[list[str], list[tuple[str, str]]]:
    """ARM 1 + ARM 2 for ONE producer. `(evidence, findings)`."""
    evidence: list[str] = []
    findings: list[tuple[str, str]] = []
    drive = Drive(nix_home)
    try:
        quiet, _status = _quiet_start(drive)
        if quiet:
            return evidence, quiet
        establish(drive)
        try:
            status = drive.watch(
                lambda st: _actions(st, condition),
                f"an {condition} protective flatten",
            )
        except _Missed as miss:
            block = _block(miss.status)
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"UNPROTECTED POSITION. The {condition!r} condition "
                        f"({debt}) was ESTABLISHED on a live daemon and NO §14 "
                        f"protective flatten was fired for it within "
                        f"{WATCH_HORIZON_S}s. The daemon reports "
                        f"detected={block.get('detected')!r} "
                        f"suppressed={block.get('suppressed')!r} "
                        f"sends={block.get('sends')!r} "
                        f"flattened={block.get('flattened')!r} "
                        f"unclassified={block.get('unclassified')!r} "
                        f"last_error={block.get('last_error')!r}. §14 is *every "
                        f"uncertainty resolves toward FLAT*: a producer that "
                        f"DETECTS and does not FIRE leaves a real position at "
                        f"the venue with nothing protecting it"
                    ),
                )
            )
            return evidence, findings
        actions = _actions(status, condition)
        block = _block(status)
        if len(actions) != 1:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{condition!r} ({debt}) fired {len(actions)} protective "
                        f"flattens for ONE condition: {actions!r}. §4 issues one "
                        "close per position and each extra firing is an extra "
                        "`flatten` at the broker"
                    ),
                )
            )
            return evidence, findings
        action = actions[0]
        if action.get("reason") != UNCERTAINTY_REASON:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{condition!r} fired with reason={action.get('reason')!r} "
                        f"and §14/§4:301 name it {UNCERTAINTY_REASON!r} — the word "
                        "rides through §4's fan-out onto the §12.10 row, so §9's "
                        "record would keep the wrong cause"
                    ),
                )
            )
        executed = list(action.get("executed") or ())
        flattened = list(block.get("flattened") or ())
        if not (executed == [True] or (not action.get("trade_ids") and flattened)):
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{condition!r} recorded a flatten that did not EXECUTE: "
                        f"executed={executed!r} dropped={action.get('dropped')!r}, "
                        f"and the BROKER's own record is {flattened!r}. A "
                        "declaration of intent is not a flatten (§4, and "
                        "`FlattenAction`'s own docstring)"
                    ),
                )
            )
        if not flattened:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{condition!r} reports a send and the BROKER recorded NO "
                        "flatten. Check contract rule 2: the return value of a "
                        "mutating call is not a verification, and this driver's "
                        "`sends` is exactly such a value one layer up"
                    ),
                )
            )
        if findings:
            return evidence, findings
        evidence.append(
            f"{condition} ({debt}): condition established on a live daemon, ONE "
            f"flatten fired at tick {action.get('tick')} — trigger="
            f"{action.get('trigger')} reason={action.get('reason')} "
            f"symbol={action.get('symbol')!r} trades={action.get('trade_ids')!r} "
            f"executed={executed!r}, broker flattened={flattened!r}"
        )

        # -- ARM 2: FIRE-ONCE, watched past the tick -------------------------
        scans_before = int(block.get("scans") or 0)
        sends_before = int(block.get("sends") or 0)
        later = drive.settle(max(1.0, FIRE_ONCE_SCAN_FLOOR * DRIVE_TICK_S * 3))
        after = _block(later)
        scans_after = int(after.get("scans") or 0)
        if scans_after - scans_before < FIRE_ONCE_SCAN_FLOOR:
            raise Cannot(
                f"{LIMITERD_FILE}: the daemon ran only "
                f"{scans_after - scans_before} further per-tick scans past the "
                f"{condition!r} fire and this gate needs {FIRE_ONCE_SCAN_FLOOR} "
                "before a stable count means fire-once rather than a stopped loop"
            )
        again = _actions(later, condition)
        if len(again) != 1 or int(after.get("sends") or 0) != sends_before:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"DOUBLE-FLATTEN. {condition!r} ({debt}) re-fired across "
                        f"{scans_after - scans_before} further ticks with the "
                        f"condition still standing: {len(again)} action(s), sends "
                        f"{sends_before} -> {after.get('sends')!r}, broker "
                        f"flattened={after.get('flattened')!r}. Every one of these "
                        "conditions PERSISTS, so a producer without a fire-once "
                        "mark issues one venue `flatten` per tick against one "
                        "position"
                    ),
                )
            )
            return evidence, findings
        evidence.append(
            f"{condition} fire-once: {scans_after - scans_before} further ticks "
            f"with the condition standing, still ONE action, sends still "
            f"{sends_before}, suppressed={after.get('suppressed')!r}"
        )

        # -- ARM 5 (per drive): the send was OFF the hot path ---------------
        sent_on = after.get("sent_on_native_id")
        sender = after.get("sender_native_id")
        loop = after.get("loop_native_id")
        if sent_on is None or sent_on != sender or sent_on == loop:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"THE PROTECTIVE FLATTEN WAS NOT SENT ON §5:323's SENDER "
                        f"THREAD. {condition!r} ran its send on native thread "
                        f"{sent_on!r}; the sender is {sender!r} and the loop is "
                        f"{loop!r}. `ProtectiveFlatten.fire` takes the §4 "
                        "arbitration lock and appends a §12.10 row, and §5:323 "
                        "puts blocking work on the sender precisely so *the hot "
                        "loop never blocks* — running it on the loop breaks I9, "
                        "discharged at ARC 050"
                    ),
                )
            )
        else:
            evidence.append(
                f"{condition} send ran on native tid {sent_on} = sender {sender} "
                f"!= loop {loop} (I9)"
            )
        if after.get("refusals"):
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{condition!r}: the sender REFUSED a firing it was handed "
                        f"— {after.get('refusals')!r}. A refused protective "
                        "flatten is an unprotected position, and §4:240-241 "
                        "forbids the resend that would paper over it"
                    ),
                )
            )
        if after.get("last_error"):
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{condition!r}: §14's reconciliation sweep contained a "
                        f"raise — {after.get('last_error')!r}. A contained sweep "
                        "produces no flatten on the tick it failed"
                    ),
                )
            )
        return evidence, findings
    finally:
        drive.close()


# --------------------------------------------------------------------------
# ARM 3 — D3.469's BOTH branches: the window HOLDS, and then it decides
# --------------------------------------------------------------------------


def _window_branches(  # pylint: disable=too-many-return-statements,too-many-branches
    nix_home: Path,
) -> tuple[list[str], list[tuple[str, str]]]:
    """The reconciliation window is a HOLD first. Both outcomes, driven."""
    evidence: list[str] = []
    findings: list[tuple[str, str]] = []

    # -- branch B: the exec report arrives INSIDE the window --------------
    drive = Drive(nix_home, window_s=DRIVE_WINDOW_S * 3)
    try:
        quiet, _status = _quiet_start(drive)
        if quiet:
            return evidence, quiet
        opened = _establish_poll_fill(drive)
        if _block(drive.cmd("status")).get("sends"):
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"D3.469 FIRED AT THE INSTANT ITS WINDOW OPENED for "
                        f"{opened!r}: the `filled` status answer was treated as a "
                        "flatten trigger rather than as the start of a bounded "
                        "hold. The ruling is HOLD then decide — the delayed "
                        "exec report is the common case"
                    ),
                )
            )
            return evidence, findings
        drive.fill("cuf-pollfill")
        try:
            status = drive.watch(
                lambda st: _block(st).get("windows_reconciled"),
                "the window to be CLOSED by the real exec report",
            )
        except _Missed as miss:
            block = _block(miss.status)
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        "D3.469: a real §2A execution report arrived INSIDE the "
                        "reconciliation window and the window was never closed "
                        f"by it — windows_open={block.get('windows_open')!r} "
                        f"windows_reconciled={block.get('windows_reconciled')!r}, "
                        f"§3 rows="
                        f"{((miss.status.get('fills') or {}).get('positions'))!r}. "
                        "The window exists so the delayed-but-valid report can "
                        "convert; one that does not close is a countdown to "
                        "flattening a healthy position"
                    ),
                )
            )
            return evidence, findings
        rows = (status.get("fills") or {}).get("positions") or []
        if not [row for row in rows if row.get("state") == "open"]:
            raise Cannot(
                f"{LIMITERD_FILE}: the window closed as reconciled and §3's table "
                f"holds {rows!r} — nothing OPEN, so 'the exec report converted' "
                "cannot be what was measured"
            )
        later = drive.settle(DRIVE_WINDOW_S * 4)
        block = _block(later)
        detected = (block.get("detected") or {}).get("undetailed_poll_fill")
        if detected:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        "D3.469 FLATTENED A HEALTHY POSITION. The §2A execution "
                        "report arrived inside the reconciliation window and "
                        "CONVERTED — §3 published an OPEN row — and the producer "
                        f"fired anyway ({detected} time(s)): "
                        f"{block.get('actions')!r}. A protective exit issued "
                        "against a position whose report was merely delayed is "
                        "not a safe direction, it is a different failure"
                    ),
                )
            )
            return evidence, findings
        evidence.append(
            "D3.469 branch B: exec report inside the window CONVERTED (§3 row "
            f"published, windows_reconciled={block.get('windows_reconciled')!r}) "
            f"and NO uncertainty flatten fired across {DRIVE_WINDOW_S * 4}s past "
            "the deadline"
        )
    finally:
        drive.close()

    # -- branch A: the DEADLINE expires first ----------------------------
    drive = Drive(nix_home, window_s=DRIVE_WINDOW_S * 3)
    try:
        quiet, _status = _quiet_start(drive)
        if quiet:
            return evidence, quiet
        opened_at = time.time()
        _establish_poll_fill(drive)
        mid = drive.settle(DRIVE_WINDOW_S)
        block = _block(mid)
        if block.get("sends"):
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        "D3.469 FIRED INSIDE ITS OWN WINDOW. "
                        f"{time.time() - opened_at:.2f}s after the `filled` status "
                        f"answer — window {block.get('reconcile_window_s')!r}s — "
                        f"the daemon had already flattened: {block.get('actions')!r}. "
                        "The ruling is HOLD then decide: an exec report that is "
                        "merely delayed is the common case, and flattening on the "
                        "status answer kills a position that was about to convert"
                    ),
                )
            )
            return evidence, findings
        evidence.append(
            f"D3.469 branch A: {DRIVE_WINDOW_S}s into a "
            f"{block.get('reconcile_window_s')!r}s window the daemon had fired "
            f"NOTHING (sends={block.get('sends')!r}, "
            f"windows_open={block.get('windows_open')!r})"
        )
        try:
            status = drive.watch(
                lambda st: _actions(st, "undetailed_poll_fill"),
                "the flatten AFTER the reconciliation deadline",
            )
        except _Missed as miss:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        "D3.469: the reconciliation window expired with no §2A "
                        "execution report and NO flatten was fired — "
                        f"{_block(miss.status)!r}. The venue holds a filled "
                        "position this process cannot account for, and §14 "
                        "resolves it toward FLAT"
                    ),
                )
            )
            return evidence, findings
        action = _actions(status, "undetailed_poll_fill")[0]
        evidence.append(
            "D3.469 branch A: the deadline expired first and ONE flatten fired — "
            f"trigger={action.get('trigger')} reason={action.get('reason')} "
            f"executed={action.get('executed')!r}, broker flattened="
            f"{_block(status).get('flattened')!r}"
        )
    finally:
        drive.close()
    return evidence, findings


# --------------------------------------------------------------------------
# ARM 4 — PRODUCER COMPLETENESS, BY DERIVATION
# --------------------------------------------------------------------------


def _declared_conditions(nix_home: Path) -> tuple[frozenset[str], dict[str, bool]]:
    """§14's condition set and the daemon's wiring, DERIVED from `limiterd.py`'s AST.

    Never a list in this file. `check_flatten` ARM 6 exists because a gate that
    hand-wrote its own copy of the frozen trigger set drove ONE of six and
    returned `pass:` with a planted defect on another; the same failure mode over
    a producer set would be a green over a condition nobody wired. So the set is
    read from the subject, and this gate's own `_PRODUCERS` table is compared
    AGAINST it rather than standing in for it.
    """
    source = (nix_home / LIMITERD_FILE).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=LIMITERD_FILE)
    conditions: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "UncertaintyCondition"):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if isinstance(stmt.value, ast.Constant) and isinstance(
                stmt.value.value, str
            ):
                conditions.add(stmt.value.value)
    wiring = {
        # the per-tick scan really is composed into the daemon's ingress ...
        "scan_composed": any(
            isinstance(node, ast.Attribute)
            and node.attr == "before"
            and isinstance(node.value, ast.Name)
            and node.value.id == "uncertainty"
            for node in ast.walk(tree)
        ),
        # ... and the fire really is handed to §5:323's sender.
        "sender_wired": any(
            isinstance(node, ast.keyword)
            and node.arg == "sender_send"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "send"
            for node in ast.walk(tree)
        ),
        # ... and the fan-out really offers the payload to C2's driver.
        "fanout_calls_uncertainty": any(
            isinstance(node, ast.ClassDef) and node.name == "ProtectiveSenders"
            for node in ast.walk(tree)
        ),
    }
    return frozenset(conditions), wiring


def _completeness(
    nix_home: Path, drove: dict[str, bool], published: dict[str, str]
) -> tuple[list[str], list[tuple[str, str]], str]:
    """ARM 4. `(evidence, findings, cannot)`. The arm this gate exists for."""
    evidence: list[str] = []
    findings: list[tuple[str, str]] = []
    declared, wiring = _declared_conditions(nix_home)
    if not declared:
        return (
            evidence,
            findings,
            (
                f"{LIMITERD_FILE} declares no `UncertaintyCondition` members, so "
                "there is no §14 producer set to judge. This gate derives the set "
                "from the subject and holds no copy of its own"
            ),
        )
    if not all(wiring.values()):
        return (
            evidence,
            findings,
            (
                f"{LIMITERD_FILE}: §14's producers are declared but not WIRED — "
                f"{wiring!r}. Both the per-tick scan and §5:323's send must be "
                "composed in the SOURCE, or every drive above is about code the "
                "process does not run"
            ),
        )
    running = frozenset(published)
    if running != declared:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"the RUNNING daemon publishes conditions {sorted(running)} and "
                    f"{LIMITERD_FILE} declares {sorted(declared)}. The published "
                    "set is what an operator and every downstream reader act on; "
                    f"the difference is {sorted(running ^ declared)}"
                ),
            )
        )
    unproduced = sorted(declared - {name for name, fired in drove.items() if fired})
    if unproduced:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"INCOMPLETE PRODUCER SET. §14's condition set declares "
                    f"{sorted(declared)} and no protective flatten was observed "
                    f"for {unproduced}. A named uncertainty condition with no "
                    "producer is the exact defect this arm exists for: the "
                    "position is real, the condition is detected, and nothing "
                    "resolves it toward flat. Each member must name a debt row "
                    "and fire on a live daemon, or be removed from the set"
                ),
            )
        )
    uncovered = sorted(declared - {name for name, _, _ in _PRODUCERS})
    if uncovered:
        return (
            evidence,
            findings,
            (
                f"{LIMITERD_FILE} declares uncertainty condition(s) {uncovered} "
                "that this gate has no drive for, so their producers are "
                "UNMEASURED. A condition an instrument cannot reach has not been "
                "shown safe (check contract rule 10) — add a drive to "
                "`_PRODUCERS` in the same arc that adds the condition"
            ),
        )
    evidence.append(
        f"ARM 4 completeness BY DERIVATION: {len(declared)} condition(s) "
        f"{sorted(declared)} declared in {LIMITERD_FILE}'s own enum, the same set "
        f"published by the running daemon, every one DRIVEN and every one FIRED; "
        f"wiring derived from the source: {wiring!r}"
    )
    for name, _establish, debt in _PRODUCERS:
        evidence.append(f"  {name} <- {debt}: {published.get(name, '')[:90]}")
    return evidence, findings, ""


# --------------------------------------------------------------------------
# ARM 5 — I9 and I3 over THIS ARC'S NEW CODE
# --------------------------------------------------------------------------

#: The ONLY module roots the per-tick stale-open scan may enter. DERIVED BY
#: MEASUREMENT against the shipped scan (ARC 057 / S4), never granted: anything
#: else is UNCLASSIFIABLE and reports CANNOT_MEASURE naming it, which is the hole
#: `check_hot_path_purity`'s own allow-set closes for the §3 gate pass. Each
#: entry says why it is here.
_SCAN_ALLOWED_ROOTS: Final[dict[str, str]] = {
    "limiterd": "the scan itself, and the daemon's own frozen record types",
    "nixrisk.picture": "§11.3's precomputed snapshot, read as ONE attribute load",
    "nixrisk.seam": "the frozen record types (PositionRow, PositionState)",
    "nixrisk.freshness": (
        "§6.4's staleness DETECTOR — one dict lookup for the held stamp and ONE "
        "subtraction against it. It is on this list because the alternative is a "
        "SECOND notion of staleness in this tree, and D3.453 is the row recording "
        "that the detector already existed and nothing joined it to a flatten"
    ),
    "nixrisk.calendar_seam": "the frozen CacheState/FreshnessStamp value types",
    "nixrisk.positions": "the trade<->order join lookup, one dict read",
    "datetime": "the injected clock the detector subtracts against — no syscall",
    "enum": "member value/name lookup on the frozen CacheState/PositionState",
    "dataclasses": "frozen record construction for the firing this may enqueue",
    "__main__": "this gate's own drive closures",
    NAME: "this gate's own drive closures when imported by verify.py",
    "checks": "this gate's own drive closures under the package spelling",
}


def _roots_of(frames: set[str]) -> set[str]:
    """Module roots from qualified names. Two segments for a package, else one."""
    roots: set[str] = set()
    for name in frames:
        parts = name.split(".")
        roots.add(".".join(parts[:2]) if parts[0] == "nixrisk" and len(parts) > 1 else parts[0])
    return roots


def _profile_roots(fn: Any) -> tuple[set[str], int]:
    """Run `fn` under `sys.setprofile` and return `(module roots, call count)`."""
    seen: set[str] = set()
    calls = 0

    def _hook(frame: Any, event: str, _arg: object) -> None:
        nonlocal calls
        if event not in ("call", "c_call"):
            return
        calls += 1
        name = frame.f_globals.get("__name__") if event == "call" else None
        if isinstance(name, str):
            seen.add(name)

    sys.setprofile(_hook)
    try:
        fn()
    finally:
        sys.setprofile(None)
    return seen, calls


def _trace_new_code(  # pylint: disable=too-many-locals,too-many-statements
    nix_home: Path,
) -> tuple[list[str], list[tuple[str, str]], str]:
    """ARM 5. The SCAN stays hot-path pure (I9); the SEND stays wire-free (I3).

    In-process and assembled EXACTLY as the daemon assembles it — that is the
    whole point, and it is `check_stop_maintenance` ARM 4's argument: a trace of
    a path a test built differently is a trace of a different path.
    """
    evidence: list[str] = []
    findings: list[tuple[str, str]] = []
    sys.path.insert(0, str(nix_home / "scripts"))
    try:
        import limiterd as daemon  # pylint: disable=import-outside-toplevel
        from nixrisk.flatten import (  # pylint: disable=import-outside-toplevel
            ProtectiveFlatten,
        )
        from nixrisk.freshness import (  # pylint: disable=import-outside-toplevel
            FreshnessTracker,
            StalenessPolicy,
        )
        from nixrisk.reservations import (  # pylint: disable=import-outside-toplevel
            ReservationLedger,
        )
        from nixrisk.seam import (  # pylint: disable=import-outside-toplevel
            PositionRow,
            PositionState,
        )
    except ImportError as exc:
        return evidence, findings, f"§14's producers do not import: {exc!r}"

    class _Venue:
        """A §2A broker that RECORDS. The exit path's far side."""

        def __init__(self) -> None:
            self.flattened: list[str | None] = []

        def flatten(self, symbol: str | None = None) -> None:
            """Recorded, never sent: this arm traces the CALL, not a venue."""
            self.flattened.append(symbol)

        def cancel_order(self, client_order_id: str) -> None:
            """§3:173's onset verb. Present so the port shape matches the daemon's."""
            _ = client_order_id

    class _Sink:
        """A §4 fan-out sink that records. The COMPLETION path is ARC D's."""

        def on_closed(self, *_a: object, **_k: object) -> None:
            """Recorded, not raised: this arm traces the FIRE, not the fan-out."""

        def book_realized(self, *_a: object, **_k: object) -> None:
            """Same."""

    class _Wal:
        """§9's Plane-1 port, recording. The WAL itself is `check_plane1_wal`'s."""

        def append(self, *_a: object, **_k: object) -> None:
            """Recorded."""

        def enqueue(self, *_a: object, **_k: object) -> None:
            """Recorded."""

    class _Loop:
        """The two verbs `UncertaintyDriver` reads off §5:322's loop."""

        tick_count = 1

        class sender:  # pylint: disable=invalid-name,too-few-public-methods
            """§5:323's thread, as the driver reads its id."""

            native_id = -1

        @staticmethod
        def hand_to_sender(_payload: object) -> None:
            """§5:323's unbounded put. Recorded, never queued: ARM 1 drives the real one."""

    try:
        policy = StalenessPolicy.from_values(
            {"price_stale_ms": 2000, "clock_skew_max_ms": 250,
             "retry_backoff": {"attempts": 3, "initial_ms": 250, "multiplier": 2.0}}
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return evidence, findings, f"§6.4's policy does not build: {type(exc).__name__}: {exc}"

    # §9 makes the Limiter the SOLE Plane-1 writer and the ledger requires the
    # port rather than defaulting to a sink, so the recorder above is passed in.
    # This arm traces a PATH's shape; the WAL itself is `check_plane1_wal`'s.
    ledger = ReservationLedger(_Wal())
    fills = daemon.FillPath(
        reservations=ledger,
        balance=BALANCE,
        deployable_fraction=0.7,
        tick_size={SYMBOL: TICK_SIZE},
    )
    # §15's bound is the subject, so the scan is given the WORST CASE §7 allows:
    # five OPEN rows. A scan traced over one position could not tell an O(n) walk
    # from an O(1) read.
    rows = tuple(
        PositionRow(
            trade_id=f"TRD-{n}",
            symbol=SYMBOL,
            strategy_id=STRATEGY,
            size=QTY,
            margin=MARGIN,
            state=PositionState.OPEN,
            stop_distance=STOP_TICKS,
        )
        for n in range(MAX_POSITIONS)
    )
    fills.picture.commit(
        positions=rows, margin_per_contract={SYMBOL: MARGIN}, sum_reservations=0.0
    )
    stamped = [0]

    def _clock() -> Any:
        from datetime import (  # pylint: disable=import-outside-toplevel
            datetime as dt,
        )
        from datetime import (
            timedelta,
        )
        stamped[0] += 1
        return dt.now(UTC) + timedelta(seconds=stamped[0] * 10)

    watch = daemon.UncertaintyWatch(
        FreshnessTracker(policy, clock=_clock), fills, reconcile_window_s=1.0
    )
    from datetime import (  # pylint: disable=import-outside-toplevel
        datetime as _dt,
    )
    watch.observe_price(SYMBOL, _dt.now(UTC))

    roots, calls = _profile_roots(lambda: watch.scan_open_positions(1))
    entered = _roots_of(roots)
    unknown = sorted(entered - set(_SCAN_ALLOWED_ROOTS))
    if unknown:
        return (
            evidence,
            findings,
            (
                f"the per-tick stale-open scan entered module root(s) {unknown} "
                f"that are not in this gate's MEASURED allow-set "
                f"{sorted(_SCAN_ALLOWED_ROOTS)}. An unclassified root on the hot "
                "path is CANNOT_MEASURE naming it, never a pass: I9 is a "
                "DISCHARGED invariant and a widened allow-set is how one is "
                "broken silently"
            ),
        )
    if watch.detected["stale_open"] != MAX_POSITIONS:
        return (
            evidence,
            findings,
            (
                f"the traced scan detected {watch.detected['stale_open']} stale "
                f"open position(s) over {MAX_POSITIONS} STALE §3 rows — the trace "
                "did not cover the work it claims to have measured"
            ),
        )
    evidence.append(
        f"ARM 5 (I9): the stale-open scan over §15's worst case "
        f"({MAX_POSITIONS} OPEN rows, all STALE, all detected) entered ONLY "
        f"{sorted(entered)} in {calls} traced calls — every root in the measured "
        "allow-set, no I/O root, no transport root"
    )

    venue = _Venue()
    exits = ProtectiveFlatten(
        broker=venue,
        ledger=ledger,
        picture=fills.picture,
        strategy=_Sink(),
        plane1=_Wal(),
        scoring=_Sink(),
        clock=time.time,
    )
    driver = daemon.UncertaintyDriver(watch, exits, _Loop())
    firing = daemon.UncertaintyFiring(
        condition=daemon.UncertaintyCondition.UNARMABLE_FILL,
        key="cuf-trace",
        symbol=SYMBOL,
        trade_id="",
        strategy_id=STRATEGY,
        detail="ARM 5's traced send",
        tick=1,
    )
    send_roots, send_calls = _profile_roots(lambda: driver.send(firing))
    if driver.sends != 1 or list(venue.flattened) != [SYMBOL]:
        return (
            evidence,
            findings,
            (
                f"the traced send produced sends={driver.sends} and the broker "
                f"recorded {list(venue.flattened)!r} — the trace is over a send "
                "that did not happen, so its silence about transports proves "
                "nothing (§17)"
            ),
        )
    banned = sorted(
        f"{root} ({why})"
        for root, why in _BANNED_ON_SEND.items()
        if root in _roots_of(send_roots)
    )
    if banned:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    "THE §14 UNCERTAINTY FLATTEN ACQUIRED A WIRE: "
                    + "; ".join(banned)
                    + ". §14 gives the protective path ZERO delivery dependency — "
                    "it fires when the Allocator is down, the bus is down and the "
                    "sockets are gone. A transport on this path removes the one "
                    "guarantee that makes the exit trustworthy (I3, discharged at "
                    "ARC 048)"
                ),
            )
        )
    else:
        evidence.append(
            f"ARM 5 (I3): the uncertainty send FIRED (broker flattened "
            f"{list(venue.flattened)!r}) across {send_calls} traced calls and "
            "entered no banned transport root"
        )
    return evidence, findings, ""


# --------------------------------------------------------------------------
# THE VERDICT
# --------------------------------------------------------------------------


def _measure(  # pylint: disable=too-many-branches,too-many-locals,too-many-return-statements
    nix_home: Path,
) -> CheckResult:
    """Drive every producer on a real daemon, then judge the SET. Never repairs."""
    evidence: list[str] = []
    findings: list[tuple[str, str]] = []
    drove: dict[str, bool] = {}
    published: dict[str, str] = {}
    unclassified: list[str] = []

    # -- ARM 1 + ARM 2, one live daemon per producer ------------------------
    for condition, establish, debt in _PRODUCERS:
        try:
            arm_evidence, arm_findings = _fires_once(
                nix_home, condition, establish, debt
            )
        except Cannot as exc:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=LIMITERD_FILE,
                detail=f"{condition} ({debt}): {exc}",
                evidence="; ".join(evidence),
            )
        evidence.extend(arm_evidence)
        findings.extend(arm_findings)
        drove[condition] = not arm_findings

    # -- ARM 3, D3.469's two branches --------------------------------------
    try:
        window_evidence, window_findings = _window_branches(nix_home)
    except Cannot as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=f"D3.469's reconciliation window: {exc}",
            evidence="; ".join(evidence),
        )
    evidence.extend(window_evidence)
    findings.extend(window_findings)

    # -- the daemon's own DERIVED condition set, and ARM 6 ------------------
    drive = Drive(nix_home)
    try:
        block = _block(drive.cmd("status"))
        published = dict(block.get("conditions") or {})
        unclassified = list(block.get("unclassified") or ())
    except Cannot as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=str(exc),
            evidence="; ".join(evidence),
        )
    finally:
        drive.close()

    # -- ARM 4, completeness by derivation ---------------------------------
    comp_evidence, comp_findings, cannot = _completeness(nix_home, drove, published)
    if cannot:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=cannot,
            evidence="; ".join(evidence),
        )
    evidence.extend(comp_evidence)
    findings.extend(comp_findings)

    # -- ARM 5, I9 and I3 over the new code --------------------------------
    try:
        trace_evidence, trace_findings, trace_cannot = _trace_new_code(nix_home)
    except Cannot as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=str(exc),
            evidence="; ".join(evidence),
        )
    if trace_cannot:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=trace_cannot,
            evidence="; ".join(evidence),
        )
    evidence.extend(trace_evidence)
    findings.extend(trace_findings)

    # -- ARM 6: an unclassifiable condition is CANNOT_MEASURE, never PASS ---
    if unclassified:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=(
                "the daemon could not classify "
                f"{len(unclassified)} refused fill dispatch(es) into any member "
                f"of §14's condition set: {unclassified}. A confirmed venue fill "
                "was refused and nothing decided whether §14 owed it a flatten — "
                "check contract rule 10: a safety property whose subject could "
                "not be classified has not been proven, and 'there is no "
                "unprotected position' is exactly such a property"
            ),
            evidence="; ".join(evidence),
        )

    if findings:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(sorted({site for site, _ in findings})),
            detail="; ".join(why for _, why in findings),
            evidence="; ".join(evidence),
            action=(
                "every condition under which this daemon holds — or the venue "
                "holds — a position it cannot protect or account for must fire "
                "EXACTLY ONE protective flatten with reason=uncertainty, on "
                "§5:323's sender thread, wire-free (§14). The set of such "
                "conditions is DERIVED from `limiterd.py`'s own "
                "`UncertaintyCondition`: a member added without a producer is "
                "the defect this gate names. It never edits its subject "
                "(CORRECTABLE=False)"
            ),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence="; ".join(evidence))


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the running Limiter flattens what it cannot protect. Never repairs."""
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
