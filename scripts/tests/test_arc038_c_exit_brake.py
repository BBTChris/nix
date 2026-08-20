"""ARC 038 / sub-agent C — THE EXIT BRAKE: §14's exit path under DEPRIVATION.

Subject: `scripts/nixrisk/flatten.py`. Authority: `docs/nics_risk_subsystem_spec_v1.3.md`
§14:969 (*"The exit/protective path has **zero wire/delivery dependency**"*), §14:968
(*"Every uncertainty resolves toward **flat**"*), §3:172 (*"Protective exit always
wins over discretionary exit"* and *"Blackout/HALT onset ⇒ Limiter cancels all
pending ENTRY orders"*), §12.4:625 (*"Disk-critical (WAL cannot append) ⇒ HALT new
entries … **Open positions remain protected (stops read memory, not disk)**"*).

WHAT WOULD HAVE TO BE TRUE FOR THIS SUITE TO MEASURE NOTHING (§7.12)
====================================================================
Three things, and each is ruled out by construction rather than by care:

1. **The WAL would have to be a stand-in that cannot fail.** That is exactly how
   the property was lost: `test_flatten.py`'s `Plane1Recorder.enqueue` is
   `self.rows.append(row)`, `check_flatten` uses the same shape, and neither can
   express `DISK_CRITICAL`. So the disk-critical arms here use the REAL
   `nixrisk.wal.Plane1Wal` in a REAL child process with `RLIMIT_FSIZE` set and
   `SIGXFSZ` ignored, so the KERNEL refuses the append with `EFBIG` — the same
   plant `scripts/plane1_degraded_drill.py` uses. Every such arm asserts the WAL
   really reached `DISK_CRITICAL` and really refused, BEFORE it judges the exit.

2. **The deprivation's subject would have to be something the deprivation cannot
   touch.** `check_plane1_degraded`'s C2 arm proves §12.4's *"open positions remain
   protected"* by showing `StopBook.breached()` still returns the breached stop
   under disk-critical — but `breached()` is arithmetic over in-memory state and
   cannot fail for a disk reason, so that assertion is a tautology (ARC 038 finding
   FC5, and the `CHECK-A7` shape one layer out). Here the subject is the
   OBSERVED `broker.flatten(symbol)` invocation and its arguments, recorded at the
   seam. A position is protected when it is FLATTENED, not when a breach is computed.

3. **One target would have to be enough.** A single-target flatten cannot show a
   sweep aborting part-way, so the multi-target arms use THREE positions and THREE
   pending entries and assert on the whole set.

Every control asserts a MESSAGE, a SITE or a FIELD, never an exit code alone
(check contract rule 11, `nix_check_contract.md` §18). Every control runs the
UNPROTECTED half FIRST and requires the bad outcome to APPEAR (ARC 035's lesson:
a control that only ever runs the protected half proves nothing).
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# too-many-lines: over the 1000 default since ARC 048 added the exhaustive
# wire-freedom controls. The overage is the controls and their stated reasons,
# and the alternative was to split I3's suite across two files — which is how
# the ONE-trigger gap this arc closed stayed invisible for ten arcs: the
# measurement and the property it measures belong in the reader's one view.
# Same call `checks/check_flatten.py` and `scripts/nixrisk/flatten.py` make.
# pylint: disable=too-many-lines
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# suite by requirement. protected-access: the falsifier subclasses reach the
# executor's injected collaborators to rebuild the PRE-FIX variant, which is how
# a can-fail twin is written (test_flatten.py's own idiom).

from __future__ import annotations

import json
import os
import signal
import subprocess  # nosec B404 - a child is REQUIRED: RLIMIT_FSIZE is per-process
import sys
import threading
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "broker"))

from nixrisk.flatten import (  # pylint: disable=wrong-import-position
    CloseAuthority,
    CloseOutcome,
    CloseTarget,
    PendingEntry,
    ProtectiveFlatten,
    UnbookedRow,
)
from nixrisk.picture import (  # pylint: disable=wrong-import-position
    FinancialPictureBook,
)
from nixrisk.realized import SYMBOL_FIELD  # pylint: disable=wrong-import-position
from nixrisk.reservations import (  # pylint: disable=wrong-import-position
    ReservationLedger,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    EventKind,
    EventRow,
    FlattenTrigger,
    TerminalPath,
)

#: The child driver. It lives in this file and is re-entered with `--child`, so
#: the planted/unplanted variants cannot drift apart into two programs.
_CHILD_FLAG = "--arc038c-child"

SYMBOLS = ("MESU6", "MNQU6", "MYMU6")
COIDS = ("c-1", "c-2", "c-3")


# ==========================================================================
# In-process doubles for the arms that do NOT need a real WAL
# ==========================================================================


class _Broker:
    """Records the REAL in-process invocation and its arguments — not a log line."""

    def __init__(self) -> None:
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []
        self.lock = threading.Lock()

    def flatten(self, symbol: str | None = None) -> None:
        with self.lock:
            self.flatten_calls.append(symbol)

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[object]:
        return []

    async def query_balance(self) -> object:  # pragma: no cover - not driven here
        raise AssertionError("reconcile is not on the zero-wire path")


class _Recorder:
    """A benign `Plane1Port`. Used only where the WAL is not the subject."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    def enqueue(self, row: object) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)


class _AngryPlane1:
    """A `Plane1Port` whose `enqueue` ALWAYS refuses, with a nameable reason.

    Not a `DiskCritical`: the point of `_book`'s broad catch is that ANY failure
    out of the frozen port is a persistence failure, and this proves it without
    importing a concrete WAL into the assertion.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        self.attempts = 0

    def enqueue(self, row: object) -> None:
        del row  # the row never lands; refusing it IS the behaviour under test
        self.attempts += 1
        raise OSError(self.message)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return 0


class _Strategy:
    def on_closed(self, *args: object, **kwargs: object) -> None:
        pass


class _Scoring:
    def book_realized(self, **kwargs: object) -> None:
        pass


def _executor(
    *,
    broker: _Broker,
    plane1: object,
    cls: type[ProtectiveFlatten] = ProtectiveFlatten,
) -> ProtectiveFlatten:
    return cls(
        broker=broker,  # type: ignore[arg-type]
        ledger=ReservationLedger(plane1),  # type: ignore[arg-type]
        picture=FinancialPictureBook(
            balance=20000.0, deployable_fraction=0.70, sink=None
        ),
        strategy=_Strategy(),  # type: ignore[arg-type]
        plane1=plane1,  # type: ignore[arg-type]
        scoring=_Scoring(),  # type: ignore[arg-type]
    )


# ==========================================================================
# THE FALSIFIERS — the PRE-FIX behaviour, restored, so each control can fail
# ==========================================================================


def _row_for(executor: ProtectiveFlatten, **kwargs: object) -> object:
    """The `EventRow` `_book` would build. Kept out of the falsifier so the
    falsifier differs from the subject in ONE thing: whether it propagates."""
    del executor
    return EventRow(
        kind=kwargs["kind"],  # type: ignore[arg-type]
        ts=kwargs["ts"],  # type: ignore[arg-type]
        strategy_id=kwargs["strategy_id"],  # type: ignore[arg-type]
        reason=kwargs["reason"],  # type: ignore[arg-type]
        trade_id=kwargs["trade_id"],  # type: ignore[arg-type]
        fields={SYMBOL_FIELD: kwargs["symbol"]},  # type: ignore[dict-item]
    )


class _UnlockedArbiter(ProtectiveFlatten):
    """FC2's falsifier: the arbiter's read-modify-write WITHOUT the lock.

    It calls `_arbitrate` directly, which is precisely the pre-ARC-038
    `request_close` body — so the difference between this class and the subject is
    the lock and nothing else.
    """

    def request_close(
        self, target: CloseTarget, authority: CloseAuthority, reason: str
    ) -> CloseOutcome:
        return self._arbitrate(target, authority, reason)


class _WireCoupledFlatten(ProtectiveFlatten):
    """The census falsifier: an exit that publishes the picture on its own path."""

    def request_close(
        self, target: CloseTarget, authority: CloseAuthority, reason: str
    ) -> CloseOutcome:
        self._picture.publish(self._picture.current())
        return super().request_close(target, authority, reason)


# ==========================================================================
# FC1 — a disk-critical WAL may not abort the exit. REAL kernel EFBIG.
# ==========================================================================


def _run_child(tmp_path: Path, arm: str, *, propagate: bool) -> dict:
    """One child: real `Plane1Wal`, `RLIMIT_FSIZE`, real `ProtectiveFlatten`.

    `env=` is passed EXPLICITLY and the child prints the `__file__` it imported
    `nixrisk.flatten` from, which this function asserts against the tree under
    test. That is D3.344's defeat ruled out by measurement rather than by hope:
    an inherited `PYTHONPATH` has, measured, made a child import the production
    module while the harness reported on a different tree.
    """
    env = dict(os.environ)
    keep = [
        p
        for p in env.get("PYTHONPATH", "").split(os.pathsep)
        if p and Path(p).resolve() != (REPO / "scripts").resolve()
    ]
    # The real-tree entry is FILTERED, not the whole variable replaced: replacing
    # it wholesale drops the binding census's `sitecustomize` directory and makes
    # this run invisible to the census.
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "scripts"), *keep])
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        _CHILD_FLAG,
        "--arm",
        arm,
        "--path",
        str(tmp_path / f"{arm}-{propagate}.wal"),
    ]
    if propagate:
        argv.append("--propagate")
    proc = subprocess.run(  # nosec B603 - argv built here, no shell
        argv, capture_output=True, text=True, timeout=120, check=False, env=env
    )
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    assert line, f"child printed nothing (rc={proc.returncode}): {proc.stderr[-600:]}"
    out = json.loads(line)
    assert (
        Path(out["imported_from"]).resolve()
        == (REPO / "scripts" / "nixrisk" / "flatten.py").resolve()
    ), (
        f"the child imported nixrisk.flatten from {out['imported_from']} — the "
        "plant/subject under test is a DIFFERENT file (D3.344)"
    )
    return out


def test_the_EXIT_FIRES_EVERY_TARGET_with_the_WAL_DISK_CRITICAL(tmp_path) -> None:
    """§12.4:625 + §14:969. BOTH HALVES, unprotected first.

    §7.12: with a Plane-1 stand-in that cannot fail this measures nothing, so the
    WAL is real and the KERNEL refuses the append. And a single target could not
    show a sweep aborting, so there are three."""
    # HALF ONE — the PRE-FIX behaviour. The bad outcome must APPEAR.
    bad = _run_child(tmp_path, "flatten", propagate=True)
    assert bad["wal_state"] == "disk_critical", bad
    assert "errno=27" in bad["wal_refusal"], bad["wal_refusal"]
    assert "DiskCritical" in bad["fire_raised"], bad["fire_raised"]
    assert bad["flatten_observed"] == ["MESU6"], bad
    assert bad["still_open_at_broker"] == ["MNQU6", "MYMU6"], (
        "the falsifier did not lose the property — this control cannot fail"
    )

    # HALF TWO — the SHIPPED subject, same kernel refusal, same three targets.
    good = _run_child(tmp_path, "flatten", propagate=False)
    assert good["wal_state"] == "disk_critical", good
    assert "errno=27" in good["wal_refusal"], good["wal_refusal"]
    assert good["fire_raised"] == "", (
        f"the exit raised {good['fire_raised']!r} with the WAL disk-critical — "
        "§12.4:625 keeps open positions PROTECTED when persistence degrades"
    )
    assert good["flatten_observed"] == list(SYMBOLS), (
        f"only {good['flatten_observed']} reached the broker seam; §14:969 gives "
        "the exit path ZERO delivery dependency"
    )
    assert good["still_open_at_broker"] == [], good
    assert good["outcomes"] == [True, True, True], good
    # The row loss is RECORDED, and by reason (rule 11) — not merely counted.
    assert good["unbooked"], "the refused rows were swallowed, not recorded"
    assert any("errno=27" in reason for reason in good["unbooked"]), good["unbooked"]


def test_the_ONSET_SWEEP_CANCELS_EVERY_ENTRY_with_the_WAL_DISK_CRITICAL(
    tmp_path,
) -> None:
    """§3:172 — *"onset cancels ALL pending ENTRY orders"*, and §3:174's reason:
    no order may fill inside a window it was not approved for.

    §7.12: this arm's abort came from `reservations.py:_emit`, NOT from `_book`, so
    a control that only removed `_book`'s propagation would pass while the sweep
    still died. The falsifier therefore propagates BOTH."""
    bad = _run_child(tmp_path, "onset", propagate=True)
    assert bad["wal_state"] == "disk_critical", bad
    assert bad["cancel_observed"] == ["c-1"], (
        "the falsifier completed the sweep — this control cannot fail"
    )
    assert bad["reservations_outstanding"] == ["c-2", "c-3"], bad

    good = _run_child(tmp_path, "onset", propagate=False)
    assert good["wal_state"] == "disk_critical", good
    assert good["raised"] == "", good["raised"]
    assert good["cancel_observed"] == list(COIDS), (
        f"only {good['cancel_observed']} were cancelled — §3:172 says ALL pending "
        "ENTRY orders, and the rest are left working inside a window they were "
        "not approved for"
    )
    assert good["reservations_outstanding"] == [], good
    assert good["reported_cancelled"] == list(COIDS), good
    kinds = good["unbooked_kinds"]
    assert any("RESERVATION_RELEASED" in kind for kind in kinds), kinds


def test_the_UNBOOKED_ROWS_are_RECORDED_and_NAME_the_persistence_reason() -> None:
    """The escalation surface FC1's fix owes. §7.12: a counter would satisfy a
    naive assertion while telling an operator nothing, so this reads the REASON
    (check contract rule 11) and the row's own identity, and it uses a NON-
    `DiskCritical` failure to prove `_book` catches the PORT's failures rather
    than one concrete WAL exception."""
    broker = _Broker()
    angry = _AngryPlane1("EIO: the log device fell off the bus")
    ex = _executor(broker=broker, plane1=angry)

    action = ex.fire(
        FlattenTrigger.NET_LIQ_FLOOR,
        symbol="MESU6",
        targets=[CloseTarget("T-1", "MESU6", "strat-1")],
    )

    assert broker.flatten_calls == ["MESU6"], broker.flatten_calls
    assert action.outcomes[0].executed is True, action
    assert angry.attempts >= 1, "the row was never even attempted"
    rows = tuple(ex.unbooked)
    assert len(rows) == 1, rows
    row = rows[0]
    assert isinstance(row, UnbookedRow), row
    assert row.kind is EventKind.PROTECTIVE_EXIT, row
    assert row.trade_id == "T-1" and row.symbol == "MESU6", row
    assert "EIO: the log device fell off the bus" in row.reason, row.reason
    assert "OSError" in row.reason, row.reason

    # And the healthy half: a working port leaves the surface EMPTY, so a
    # non-empty tuple is information and not decoration.
    ok = _executor(broker=_Broker(), plane1=_Recorder())
    ok.fire(
        FlattenTrigger.NET_LIQ_FLOOR,
        symbol="MESU6",
        targets=[CloseTarget("T-2", "MESU6", "strat-1")],
    )
    assert not ok.unbooked, ok.unbooked


def test_a_REFUSED_REALIZING_ROW_does_not_BURN_the_trade_s_ONE_FIGURE() -> None:
    """The consequence of FC1's own fix, closed in the same edit.

    `_realizing_fields` marks a trade as "figure already booked" while BUILDING the
    row. If the row is then refused, leaving the mark set would make the next
    realizing row say *"already booked on this trade's 'protective_exit' row"*
    about a row §9 never received — the figure lost twice. §7.12: without this
    control the fix would trade one silent loss for another."""
    broker = _Broker()
    angry = _AngryPlane1("ENOSPC: no space left on device")
    ex = _executor(broker=broker, plane1=angry)

    ex.fire(
        FlattenTrigger.SYNTHETIC_STOP,
        symbol="MESU6",
        targets=[CloseTarget("T-9", "MESU6", "strat-1")],
    )
    assert ex.unbooked, "the refusal did not happen; the control is vacuous"
    assert "T-9" not in ex._realized_booked, (
        f"the trade is still marked booked ({ex._realized_booked}) against a row "
        "the WAL refused"
    )


# ==========================================================================
# FC2 — PROTECTIVE beats DISCRETIONARY under a REAL threaded race
# ==========================================================================


class _HoldingDict(dict):
    """The arbiter's `_closed` map with a TRIP-WIRE on the read.

    Holds the FIRST reader inside the read-modify-write window for real, so the
    interleaving is FORCED rather than guessed at with a sleep. A sleep-based
    version would be flaky in exactly the direction that hides the defect.
    """

    def __init__(self, gate: threading.Event, log: list[str], hold_for: str) -> None:
        super().__init__()
        self.gate = gate
        self.log = log
        self.hold_for = hold_for
        self.armed = True

    def get(self, key, default=None):  # type: ignore[override]
        value = super().get(key, default)
        who = threading.current_thread().name
        self.log.append(f"{who}:read prior={value.authority.value if value else None}")
        if self.armed and who == self.hold_for:
            self.armed = False
            self.gate.wait(10.0)
        return value


def _contend(cls: type[ProtectiveFlatten], *, protective_first: bool) -> dict:
    """Two real threads at ONE trade, the window forced open, one arrival order."""
    broker = _Broker()
    ex = _executor(broker=broker, plane1=_Recorder(), cls=cls)
    gate = threading.Event()
    log: list[str] = []
    ex._closed = _HoldingDict(gate, log, hold_for="held")  # type: ignore[assignment]
    target = CloseTarget("T-1", "MESU6", "strat-1")
    loser = (
        CloseAuthority.DISCRETIONARY if protective_first else CloseAuthority.PROTECTIVE
    )
    winner = (
        CloseAuthority.PROTECTIVE if protective_first else CloseAuthority.DISCRETIONARY
    )

    def worker(authority: CloseAuthority) -> None:
        ex.request_close(target, authority, f"{authority.value} contended")
        log.append(f"{threading.current_thread().name}:wrote {authority.value}")

    held = threading.Thread(target=worker, args=(loser,), name="held")
    held.start()
    deadline = time.time() + 10.0
    while not log and time.time() < deadline:
        time.sleep(0.001)
    assert log, "the trip-wire never fired — the window was not opened"
    free = threading.Thread(target=worker, args=(winner,), name="free")
    free.start()
    # A SHORT join, then release, then a generous one — and the short join's
    # outcome is itself a reading. Unlocked, `free` is not blocked by anything and
    # completes here, which is what lets it write BEFORE the held thread and lose
    # the property. Locked, `free` is waiting on `_arbiter` and is still alive,
    # which IS the serialisation, observed rather than assumed. Joining `free`
    # first and only then releasing the gate would deadlock the harness for the
    # locked case and was measured doing exactly that.
    free.join(2.0)
    free_completed_before_release = not free.is_alive()
    gate.set()
    held.join(10.0)
    free.join(10.0)
    assert not held.is_alive() and not free.is_alive(), (
        f"a contending thread hung: held={held.is_alive()} free={free.is_alive()}"
    )
    record = ex.closed_record("T-1")
    assert record is not None
    return {
        "winner": record.authority,
        "hard_reset": record.hard_reset,
        "log": log,
        "flattens": len(broker.flatten_calls),
        "free_completed_before_release": free_completed_before_release,
    }


@pytest.mark.parametrize("protective_first", [True, False])
def test_PROTECTIVE_WINS_under_a_REAL_THREADED_RACE_in_BOTH_orders(
    protective_first: bool,
) -> None:
    """§3:172 — *"Protective exit always wins over discretionary exit."*

    §7.12: `test_flatten.py` and `check_flatten` drive both orderings SEQUENTIALLY
    and call that contention. Two ordered calls never open the read-modify-write
    window, so they cannot see this. Real threads, and the falsifier is the SAME
    class without the lock — so the only difference between the two halves is the
    thing under test."""
    # HALF ONE — unlocked. The bad outcome must APPEAR in at least the order that
    # loses it, and it is precisely the order where PROTECTIVE completes first.
    bad = _contend(_UnlockedArbiter, protective_first=protective_first)
    assert bad["free_completed_before_release"] is True, (
        "the unlocked falsifier's second thread did NOT run inside the first "
        "thread's read-modify-write window, so no interleaving was produced and "
        "this control measured nothing"
    )
    if protective_first:
        assert bad["winner"] is CloseAuthority.DISCRETIONARY, (
            f"the unlocked arbiter kept protective ({bad['log']}) — this control "
            "cannot fail"
        )
        assert bad["hard_reset"] is False, bad

    # HALF TWO — the shipped subject.
    good = _contend(ProtectiveFlatten, protective_first=protective_first)
    assert good["free_completed_before_release"] is False, (
        "the second thread completed while the first was still inside the "
        "critical section — the arbiter is NOT serialising, and the verdict below "
        "would be luck rather than the lock"
    )
    assert good["winner"] is CloseAuthority.PROTECTIVE, (
        f"a discretionary close became the recorded winner over a protective one "
        f"({good['log']}) — §3:172 makes protective ALWAYS win"
    )
    assert good["hard_reset"] is True, (
        "hard_reset is False on a protective win, so §4's one-in-flight slot is "
        f"never freed ({good})"
    )


def test_the_SEQUENTIAL_precedence_rules_are_UNCHANGED_by_the_lock() -> None:
    """FC2's fix must be a SERIALISATION, not a re-decision. §7.12: a lock that
    also changed a verdict would pass the threaded control above while quietly
    rewriting §4's arbiter, so the sequential answers are pinned here."""
    for first, second, expect_superseded, expect_executed in (
        (CloseAuthority.DISCRETIONARY, CloseAuthority.PROTECTIVE, True, True),
        (CloseAuthority.PROTECTIVE, CloseAuthority.DISCRETIONARY, False, False),
    ):
        broker = _Broker()
        ex = _executor(broker=broker, plane1=_Recorder())
        target = CloseTarget("T-1", "MESU6", "strat-1")
        ex.request_close(target, first, f"{first.value} first")
        outcome = ex.request_close(target, second, f"{second.value} second")
        record = ex.closed_record("T-1")
        assert record is not None
        assert record.authority is CloseAuthority.PROTECTIVE, record
        assert record.hard_reset is True, record
        assert (record.superseded is not None) is expect_superseded, record
        assert outcome.executed is expect_executed, outcome
        if not expect_executed:
            assert "protective always wins" in outcome.dropped_reason, outcome


# ==========================================================================
# The DIRECTNESS census — no queue, no future, no topic, no loop, no socket
# ==========================================================================

#: Modules whose presence on the exit path would BE a wire/delivery dependency.
#: `nixrisk.wal` is deliberately ABSENT: the local WAL append is on the path and
#: that is FC1's subject, now made non-fatal rather than removed.
_BANNED = (
    "asyncio",
    "queue",
    "concurrent",
    "threading",
    "socket",
    "select",
    "selectors",
    "ssl",
    "http",
    "urllib",
    "zmq",
    "subprocess",
    "multiprocessing",
    "nixbus",
    "nixrisk.picture",
    "nixrisk.plane1_sink",
)


def _census(run) -> set[str]:
    """Every `module.qualname` entered during `run()`. A MEASUREMENT of the live
    call, not a reading of the source."""
    seen: set[str] = set()

    def profile(frame, event, arg):
        del arg
        if event == "call":
            seen.add(
                f"{frame.f_globals.get('__name__', '?')}.{frame.f_code.co_qualname}"
            )

    sys.setprofile(profile)
    try:
        run()
    finally:
        sys.setprofile(None)
    return seen


def _banned_in(census: set[str]) -> set[str]:
    hits = set()
    for entry in census:
        for module in _BANNED:
            if entry == module or entry.startswith(module + "."):
                hits.add(module)
    return hits


def test_the_EXIT_PATH_TOUCHES_NO_WIRE_MODULE() -> None:
    """§14:969, proven by INSTRUMENTING the call. BOTH HALVES.

    §7.12: reading the source and concluding "there is no such path" is not a
    measurement, and a healthy transport hides a dependency it does not exercise.
    So the census is taken from the running interpreter, and the falsifier — an
    exit that publishes the picture — must show up in it, or the census is blind."""
    # HALF ONE — the falsifier's wire touch must APPEAR in the census.
    coupled_broker = _Broker()
    coupled = _executor(
        broker=coupled_broker, plane1=_Recorder(), cls=_WireCoupledFlatten
    )
    bad = _census(
        lambda: coupled.fire(
            FlattenTrigger.SYNTHETIC_STOP,
            symbol="MESU6",
            targets=[CloseTarget("T-1", "MESU6", "strat-1")],
        )
    )
    assert "nixrisk.picture" in _banned_in(bad), (
        f"the census did not see the coupled exit's publish — it is blind. "
        f"census had {sorted(e for e in bad if 'picture' in e)}"
    )

    # HALF TWO — the shipped subject.
    broker = _Broker()
    ex = _executor(broker=broker, plane1=_Recorder())
    good = _census(
        lambda: ex.fire(
            FlattenTrigger.SYNTHETIC_STOP,
            symbol="MESU6",
            targets=[CloseTarget("T-1", "MESU6", "strat-1")],
        )
    )
    assert broker.flatten_calls == ["MESU6"], broker.flatten_calls
    hits = _banned_in(good)
    assert not hits, (
        f"the exit path entered {sorted(hits)} — §14:969 gives it ZERO "
        f"wire/delivery dependency. Offending frames: "
        f"{sorted(e for e in good if any(e.startswith(m) for m in hits))}"
    )


# ==========================================================================
# THE CHILD — re-entered with --arc038c-child. Real WAL, real RLIMIT_FSIZE.
# ==========================================================================

_FSIZE_LIMIT = 4096


# too-many-locals / too-many-statements: this function IS the child program — the
# WAL, the enqueuer, the executor, the reservations, the fill loop, the arm and the
# announcement. Splitting it would put the `RLIMIT_FSIZE` plant and the drive it
# constrains in different frames, which is the one thing that must stay obviously
# in one process. broad-exception-caught: the arms must REPORT what the subject
# raised rather than die of it, which is how the finding was measured at all.
def _child_main(  # pylint: disable=too-many-locals,too-many-statements
    argv: list[str],
) -> int:  # pragma: no cover - runs in a child
    """One disk-critical arm, announced as one JSON line on stdout.

    import-outside-toplevel below is REQUIRED, not stylistic: `resource` and the
    `nixrisk` names are imported AFTER `setrlimit`, inside the child, so nothing
    the parent process imported can satisfy them and the child's own
    `nixrisk.flatten.__file__` is what gets announced and asserted (D3.344)."""
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    arm = argv[argv.index("--arm") + 1]
    path = argv[argv.index("--path") + 1]
    propagate = "--propagate" in argv

    # SIGXFSZ's default action is to KILL. Ignored so the write RETURNS EFBIG and
    # the process survives to report — which is §12.4's actual condition.
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    import resource

    resource.setrlimit(resource.RLIMIT_FSIZE, (_FSIZE_LIMIT, _FSIZE_LIMIT))

    import nixrisk.flatten as flatten_mod
    from nixrisk.degraded import Plane1Enqueuer
    from nixrisk.seam import ProposedOrder, Side, StopMode
    from nixrisk.wal import DiskCritical, Plane1Wal

    wal = Plane1Wal(path)
    enq = Plane1Enqueuer(wal)
    broker = _Broker()
    cls = _PropagatingEverything if propagate else ProtectiveFlatten
    ex = _executor(broker=broker, plane1=enq, cls=cls)

    out: dict[str, object] = {
        "arm": arm,
        "propagate": propagate,
        "imported_from": flatten_mod.__file__,
    }

    # Reservations taken while the WAL is still HEALTHY, so the onset arm has real
    # reservations to release. A reservation taken after the failure is a
    # different claim (`plane1_degraded_drill`'s own argument).
    if arm == "onset":
        for coid in COIDS:
            ex._ledger.take(
                ProposedOrder(
                    client_order_id=coid,
                    strategy_id="strat-1",
                    symbol=SYMBOLS[0],
                    side=Side.LONG,
                    qty=1,
                    margin_per_contract=1000.0,
                    stop_ticks=20,
                    stop_mode=StopMode.FIXED,
                    signal_ts=1000.0,
                ),
                time.time(),
            )

    refusal, accepted = "", 0
    for index in range(4000):
        try:
            enq.enqueue(
                EventRow(
                    kind=EventKind.SIGNAL,
                    ts=time.time(),
                    strategy_id="arc038c",
                    reason=f"filling the WAL, row {index}",
                    trade_id=f"fill-{index:05d}",
                    fields={"symbol": SYMBOLS[0]},
                )
            )
        except DiskCritical as exc:
            refusal = str(exc)
            break
        accepted += 1
    out["wal_state"] = wal.state.value
    out["wal_refusal"] = refusal
    out["accepted_rows"] = accepted

    if arm == "flatten":
        targets = [CloseTarget(f"T-{i}", s, "strat-1") for i, s in enumerate(SYMBOLS)]
        raised, action = "", None
        try:
            action = ex.fire(FlattenTrigger.SYNTHETIC_STOP, targets=targets)
        except BaseException as exc:  # noqa: BLE001
            raised = f"{type(exc).__name__}: {exc}"
        out["fire_raised"] = raised
        out["flatten_observed"] = [c for c in broker.flatten_calls if c is not None]
        out["still_open_at_broker"] = sorted(
            set(SYMBOLS) - {c for c in broker.flatten_calls if c is not None}
        )
        out["outcomes"] = (
            None if action is None else [o.executed for o in action.outcomes]
        )
    else:
        pending = [PendingEntry(c, "strat-1", SYMBOLS[0]) for c in COIDS]
        raised, sweep = "", None
        try:
            # assignment-from-no-return: the FALSIFIER's override ends in a raise,
            # so pylint infers None for both branches. The SUBJECT returns an
            # `OnsetCancellation`, which is exactly what this arm reads.
            sweep = ex.cancel_entries_on_onset(  # pylint: disable=assignment-from-no-return
                TerminalPath.BLACKOUT_ONSET, pending
            )
        except BaseException as exc:  # noqa: BLE001
            raised = f"{type(exc).__name__}: {exc}"
        out["raised"] = raised
        out["cancel_observed"] = list(broker.cancel_calls)
        out["reported_cancelled"] = None if sweep is None else list(sweep.cancelled)
        out["reservations_outstanding"] = sorted(
            r.client_order_id for r in ex._ledger.outstanding()
        )

    out["unbooked"] = [r.reason for r in ex.unbooked]
    out["unbooked_kinds"] = [r.kind.name for r in ex.unbooked]
    print(json.dumps(out))
    return 0


class _PropagatingEverything(ProtectiveFlatten):  # pragma: no cover - child only
    """The PRE-ARC-038 executor: `_book` propagates AND the onset sweep does not
    absorb `resolve`'s failure. Both of FC1's sites restored in one class, because
    the onset arm's abort came from `reservations.py` and a falsifier that only
    restored `_book` would pass while the sweep still died."""

    def _book(self, **kwargs: object) -> None:  # type: ignore[override]
        self._plane1.enqueue(_row_for(self, **kwargs))  # type: ignore[arg-type]

    # `scope` is accepted and ignored: the falsifier differs from the subject in
    # whether it PROPAGATES, and a narrower signature would make it differ in a
    # second way (pylint W0221 / LSP).
    def cancel_entries_on_onset(  # type: ignore[override]
        self, cause, pending, *, scope=None
    ):
        del scope
        now = self._clock()
        cancelled: list[str] = []
        for entry in pending:
            self._broker.cancel_order(entry.client_order_id)
            self._ledger.resolve(entry.client_order_id, cause, now, reason=cause.value)
            cancelled.append(entry.client_order_id)
            self._book(
                kind=EventKind.CANCEL,
                trade_id=None,
                strategy_id=entry.strategy_id,
                symbol=entry.symbol,
                reason=f"{cause.value} onset entry-cancel",
                ts=now,
            )
        raise AssertionError("unreachable in the disk-critical arm")


if __name__ == "__main__":  # pragma: no cover
    if _CHILD_FLAG in sys.argv:
        sys.exit(_child_main(sys.argv))
    raise SystemExit("this file is a pytest suite; run it with pytest")


# ==========================================================================
# ARC 048 / I3 — the EXHAUSTIVE arm. Every derived trigger, everything dead.
# ==========================================================================
#
# `test_the_EXIT_PATH_TOUCHES_NO_WIRE_MODULE` above drives ONE trigger
# (`SYNTHETIC_STOP`). ARC 038 recorded the gap as FC5 and ARC 048 re-measured
# it: the frozen enum declares SEVEN triggers, `flatten.py` refuses ONE, so SIX
# are fireable — and a wire dependency reachable from any of the other five was
# invisible to every standing instrument. These controls close it at the
# library level; `checks/check_flatten.py`'s ARM 6 is the standing gate.


class _DeadSink:
    """The state bus, unreachable. Every emit REJECTS — it is not merely idle."""

    def __init__(self) -> None:
        self.attempts = 0

    def emit(self, picture: object) -> None:
        del picture
        self.attempts += 1
        raise ConnectionError("state bus down / ZMQ unavailable")


def _module_refusals() -> frozenset[FlattenTrigger]:
    import nixrisk.flatten as mod  # pylint: disable=import-outside-toplevel

    return frozenset(mod._R4_TRIGGERS)  # pylint: disable=protected-access


def _fireable_triggers() -> list[FlattenTrigger]:
    """DERIVED, not listed: the frozen vocabulary minus the module's refusals.

    A list written here would go stale the moment a member is added, which is
    the precise failure mode this arm exists to prevent.
    """
    refused = _module_refusals()
    return [t for t in FlattenTrigger if t not in refused]


def test_the_DERIVED_TRIGGER_SET_IS_THE_SPEC_S_SET_and_the_REFUSAL_IS_LOUD() -> None:
    """§3:169's list is the checklist the derivation is verified AGAINST.

    Transcribed: "synthetic stop / stale price / net-liq floor / session close /
    uncertainty / orphan / sentinel". If the enum and the spec ever disagree,
    that is a finding about the spec to be reported (the ARC 028 / SPEC-A7 rule)
    and this control is where it surfaces.
    """
    assert {t.value for t in FlattenTrigger} == {
        "synthetic_stop",
        "stale_price",
        "net_liq_floor",
        "session_close",
        "uncertainty",
        "orphan",
        "sentinel",
    }
    fireable = _fireable_triggers()
    assert {t.value for t in fireable} == {
        "synthetic_stop",
        "stale_price",
        "net_liq_floor",
        "session_close",
        "uncertainty",
        "orphan",
    }, [t.value for t in fireable]

    # The refused one is refused LOUDLY — never a silent no-op that would read
    # as "flattened" (§14: the Sentinel runs when the Limiter is DEAD).
    broker = _Broker()
    executor = _executor(broker=broker, plane1=_Recorder())
    with pytest.raises(Exception) as excinfo:
        executor.fire(
            FlattenTrigger.SENTINEL,
            symbol="MESU6",
            targets=[CloseTarget("T-1", "MESU6", "strat-1")],
        )
    assert "sentinel" in str(excinfo.value)
    assert not broker.flatten_calls, broker.flatten_calls


@pytest.mark.parametrize("targeted", [True, False], ids=["targeted", "untargeted"])
def test_EVERY_FIREABLE_TRIGGER_FLATTENS_with_EVERYTHING_DEAD(targeted: bool) -> None:
    """§14:969's absence proof, taken over the DERIVED set rather than one member.

    Dead: the state bus (`emit` raises) and the Plane-1 delivery wire (`enqueue`
    raises). Absent by construction: the Allocator — `ProtectiveFlatten` takes no
    allocator collaborator, which is §3:172's *"exit never routes through
    Allocator"* held structurally rather than mocked.

    BOTH target shapes, because they are two DIFFERENT broker-flatten sites:
    `fire` calls `self._broker.flatten(symbol)` directly for §4's untargeted
    uncertainty flatten, and `_arbitrate` calls it per trade for a targeted one.
    """
    for trigger in _fireable_triggers():
        sink, plane1 = _DeadSink(), _AngryPlane1("EFBIG: the WAL cannot append")
        broker = _Broker()
        executor = ProtectiveFlatten(
            broker=broker,  # type: ignore[arg-type]
            ledger=ReservationLedger(_Recorder()),  # type: ignore[arg-type]
            picture=FinancialPictureBook(
                balance=20000.0, deployable_fraction=0.70, sink=sink
            ),
            strategy=_Strategy(),  # type: ignore[arg-type]
            plane1=plane1,  # type: ignore[arg-type]
            scoring=_Scoring(),  # type: ignore[arg-type]
        )
        targets = [CloseTarget("T-1", "MESU6", "strat-1")] if targeted else []

        executor.fire(trigger, symbol="MESU6", targets=targets)

        assert broker.flatten_calls == ["MESU6"], (
            f"{trigger.value} ({'targeted' if targeted else 'untargeted'}) did not "
            f"reach the broker with the wire dead: {broker.flatten_calls!r}"
        )
        # NON-VACUITY: the dead wire was really REACHED FOR on the targeted
        # shape (the exit books its Plane-1 row) and really refused, so this is
        # a live dependency surviving, not a wire nobody touched. The untargeted
        # shape books nothing, which is itself the property (§4).
        if targeted:
            assert plane1.attempts >= 1, (
                f"{trigger.value}: the Plane-1 wire was never touched, so its "
                "deadness proves nothing"
            )
            assert executor.unbooked, (
                f"{trigger.value}: the refused row was not RECORDED — a flatten "
                "that loses its audit row must say so (FC1)"
            )


def test_the_DEAD_DOUBLES_REALLY_REJECT_so_the_ARM_ABOVE_IS_NOT_VACUOUS() -> None:
    """The other half of non-vacuity: prove the wire is dead, not just unused."""
    with pytest.raises(ConnectionError):
        _DeadSink().emit(object())
    with pytest.raises(OSError):
        _AngryPlane1("EFBIG").enqueue(object())


def test_a_PROTECTIVE_EXIT_FIRES_MID_ONSET_and_STILL_WINS_over_DISCRETIONARY() -> None:
    """§3:173 — an onset cancels pending ENTRIES and leaves exits untouched.

    The I11 boundary, re-confirmed from the exit side: a HALT onset sweep runs,
    and a protective flatten fired AFTER it still reaches the broker and still
    beats a discretionary close of the same trade. A blackout that could starve
    the exit would invert §14:969 exactly as a dead wire would.
    """
    broker = _Broker()
    plane1 = _Recorder()
    executor = _executor(broker=broker, plane1=plane1)
    ledger = ReservationLedger(plane1)

    # A HALT onset sweeps the pending entries. Nothing here flattens.
    executor_ledger_before = len(broker.flatten_calls)
    executor.cancel_entries_on_onset(TerminalPath.HALT_ONSET, [])
    assert len(broker.flatten_calls) == executor_ledger_before, broker.flatten_calls
    del ledger

    # Mid-onset, a discretionary exit takes the trade first...
    target = CloseTarget("T-1", "MESU6", "strat-1")
    first = executor.request_close(target, CloseAuthority.DISCRETIONARY, "edge spent")
    assert first.executed is True, first  # non-vacuity: it really went first

    # ...and the protective exit OVERRIDES it, unconditionally.
    second = executor.request_close(target, CloseAuthority.PROTECTIVE, "stop breached")

    assert second.executed is True, second
    record = executor.closed_record("T-1")
    assert record is not None
    assert record.authority is CloseAuthority.PROTECTIVE, record
    assert record.superseded is CloseAuthority.DISCRETIONARY, record
    # §4: the FSM hard-resets to flat and the one-in-flight slot is freed.
    assert record.hard_reset is True, record
    assert record.reason == "stop breached", record
    assert broker.flatten_calls == ["MESU6", "MESU6"], broker.flatten_calls
