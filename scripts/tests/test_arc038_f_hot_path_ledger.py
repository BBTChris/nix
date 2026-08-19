"""ARC 038 / sub-agent F — §14's hot path, measured over the SHIPPED APPROVE path.

`docs/nics_risk_subsystem_spec_v1.3.md` §14:965: *"Hot path = cache reads +
arithmetic only."* §11:579 spells the pathway out and §11 item 6 puts
group-commit event-log writes off it, *WAL-buffered*. Every `§` cites v1.3.

## WHY THIS SUITE EXISTS — the gap is in the INSTRUMENT, not in the claim

`checks/check_plane1_hot_path.py` is the standing gate for §11 item 6 and it is a
good one: ARC 038 (F) planted a 2 ms block inside `GatePass.evaluate` and it went
RED, planted a real per-evaluation `write(2)` and it went RED again. But its
subject is built by `scripts/plane1_hotpath_drill.py::_gate`, and that
`GatePass` carries **`ledger=None`** — measured, printed from the object. So
`GatePass._settle`'s reservation take, `ReservationLedger._book`, its Plane-1
`_emit` and `Plane1Wal.enqueue` — the ONLY I/O the shipped approve path performs
— are all OUTSIDE every timed region the gate reports on. ARC 038 (F) measured
the difference: p50 8.2 -> 34.3 us, max **13.3 -> 1169.8 us**, and 4,202
`write(2)` syscalls under `strace` for 4,200 approvals, because `Plane1Wal` opens
its handle `buffering=0` on purpose (`wal.py`'s own docstring: *"so `enqueue`
issues the `write(2)` itself"*). CHECK-DEBT D3.400.

This suite owns the arm the drill does not have. It is deliberately NOT a second
copy of the drill's three-arm relation (doctrine C.9): nothing here re-asserts
that the gate is off the group-commit path. What it asserts is the SHAPE and
COUNT of what the approve path does per evaluation, so the day a network sink,
an fsync, or a second write appears behind the ledger, a number moves.

## §7.12 — THE STANDING QUESTION, ANSWERED CONDITION BY CONDITION

*What would have to be true for this suite to pass while the hot path is doing
blocking work?*

1. **The observer could be blind.** A monkeypatched spy is defeated by a
   reference captured before the patch, and a defeated spy reports *no claims*.
   So the census is a CPython audit hook (PEP 578) — it cannot be removed and
   cannot be bypassed — installed in a CHILD interpreter, because a hook
   installed in the pytest process would outlive the test.
2. **The child could import the WRONG tree.** D3.344 (ARC 037) measured exactly
   that: a child launched with no `env=` inherited a `PYTHONPATH` pointing at the
   real tree and every plant was defeated. So the child gets an explicit `env=`
   and PRINTS `nixrisk.gate.__file__`, which is asserted to live under this
   worktree before any count is read.
3. **The census could be green because nothing was driven.** So the child prints
   the evaluation count and the decision, and both are asserted: an arm that
   denied would never reach `_settle` and would perform no append at all.
4. **The census could be green because it cannot SEE a blocking call.** So
   `test_the_CENSUS_SEES_a_socket_on_the_approve_path` puts a real
   `socket.connect` behind the ledger's Plane-1 port and requires the named
   event to appear. Without that half the zero means nothing.
5. **The timing arm could be a fast box rather than a fast path.** So the
   sleeping-sink arm runs beside it and must be inflated by roughly the delay —
   the same argument the drill makes for its own synchronous control.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=too-few-public-methods,missing-function-docstring

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - argv built here, no shell, own child only
import sys
import tempfile
import time
from pathlib import Path

from nixrisk.gate import GatePass, default_manifest
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    Decision,
    FinancialPicture,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.wal import Plane1Wal

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
FRACTION = 0.70
SAFETY_PAD = 0.10
TOLERANCE = 1e-6
#: Enough evaluations that a once-per-N syscall cannot hide, small enough that a
#: loaded box still finishes. Reported, never inferred.
EVALUATIONS = 600
#: The audit-event families a §14 hot path may not enter. `open` covers reads as
#: well as writes, which `scripts/nixverify/observe.py` deliberately does NOT —
#: that module answers "what does a CHECK claim", where a read is noise; here a
#: read is the finding, and that difference is why this is not a second copy of
#: it (doctrine C.9).
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "open",
    "socket.",
    "subprocess.",
    "os.system",
    "os.exec",
    "os.listdir",
    "os.scandir",
    "os.rename",
    "os.remove",
    "os.mkdir",
    "shutil.",
    "time.sleep",
)


class _Clear:
    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        return False, ""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        del strategy_id
        return False, ""

    def mark(self) -> tuple[float, bool]:
        return 10_000_000.0, True


def _order(index: int) -> ProposedOrder:
    return ProposedOrder(
        client_order_id=f"hp-{index}",
        strategy_id="s1",
        symbol="ES",
        side=Side.LONG,
        qty=4,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture() -> FinancialPicture:
    return FinancialPicture(
        version=1,
        published_ts=1.0,
        balance=1_000_000.0,
        positions=(),
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=500_000.0,
    )


def _gate_with_real_ledger(wal_path: Path) -> tuple[GatePass, Plane1Wal]:
    """The SHIPPED approve path: real gate, real ledger, real WAL."""
    wal = Plane1Wal(wal_path)
    clear = _Clear()
    rules = list(
        default_manifest(
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
    )
    return GatePass(clear, rules, ReservationLedger(wal)), wal


# ---------------------------------------------------------------------------
# THE APPEND, COUNTED — what the drill's `ledger=None` arm cannot see
# ---------------------------------------------------------------------------


def test_the_SHIPPED_APPROVE_PATH_makes_exactly_ONE_WAL_APPEND_per_approval(
    tmp_path: Path,
) -> None:
    """§11 item 6 is *WAL-buffered*; `Plane1Wal` is `buffering=0` by design, so
    every approval is one append and NO fsync. Counted off the WAL's own
    counters, which exist for exactly this reason."""
    gate, wal = _gate_with_real_ledger(tmp_path / "plane1.wal")
    try:
        decisions = [
            gate.evaluate(_order(i), _picture(), now=1.0 + i).decision
            for i in range(EVALUATIONS)
        ]
        assert all(d is Decision.APPROVE for d in decisions), decisions[:5]
        assert wal.enqueued == EVALUATIONS, (
            f"{wal.enqueued} append(s) for {EVALUATIONS} approvals — §3's "
            "'approve => TAKE RESERVATION' writes exactly one Plane-1 row per "
            "approval, so any other number means a route changed"
        )
        assert wal.fsyncs == 0, (
            f"{wal.fsyncs} fsync(s) INSIDE the gate pass. §11 item 6 puts durability "
            "on the group-commit writer, not on the entry pathway"
        )
        assert wal.bytes_written > 0, wal.bytes_written
    finally:
        wal.close()


def test_the_APPEND_COUNT_assertion_REJECTS_a_ledgerless_gate(tmp_path: Path) -> None:
    """THE CAN-FAIL HALF, and it is the drill's own configuration.

    `plane1_hotpath_drill._gate()` builds `GatePass(clear, rules)` with no
    ledger. The same assertion set run against that shape must FAIL — which is
    the whole content of CHECK-DEBT D3.400."""
    clear = _Clear()
    gate = GatePass(
        clear,
        list(
            default_manifest(
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
        ),
    )
    wal = Plane1Wal(tmp_path / "unused.wal")
    try:
        for i in range(EVALUATIONS):
            assert gate.evaluate(_order(i), _picture(), 1.0 + i).decision is (
                Decision.APPROVE
            )
        assert wal.enqueued == 0, (
            "a ledgerless gate wrote to the WAL — then the falsifier does not "
            "falsify and the control above measures nothing"
        )
    finally:
        wal.close()


def test_a_SLEEPING_PLANE1_PORT_shows_UP_in_the_pass(tmp_path: Path) -> None:
    """The timing arm's own can-fail. The approve path is timed with the real
    WAL, then with a Plane-1 port that sleeps 2 ms — the second MUST be inflated
    by roughly the delay, or elapsed time here is not measuring the pass."""
    delay_s = 0.002
    gate, wal = _gate_with_real_ledger(tmp_path / "fast.wal")
    try:
        fast = []
        for i in range(200):
            start = time.perf_counter_ns()
            gate.evaluate(_order(i), _picture(), 1.0 + i)
            fast.append(time.perf_counter_ns() - start)
    finally:
        wal.close()

    class _SleepingPlane1:
        """A `Plane1Port` whose append blocks. ALL THREE verbs, deliberately:
        a double that satisfies half a port stops satisfying it the day the
        subject calls the other half — `test_limiter_gate.py::Ledger` states the
        same argument for the same reason."""

        def __init__(self) -> None:
            self.rows = 0

        def enqueue(self, row: object) -> None:
            del row
            self.rows += 1
            time.sleep(delay_s)

        def pending(self) -> int:
            return self.rows

        def sync_to_disk(self) -> int:
            made, self.rows = self.rows, 0
            return made

    clear = _Clear()
    slow_gate = GatePass(
        clear,
        list(
            default_manifest(
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
        ),
        ReservationLedger(_SleepingPlane1()),
    )
    slow = []
    for i in range(60):
        start = time.perf_counter_ns()
        slow_gate.evaluate(_order(1000 + i), _picture(), 1.0 + i)
        slow.append(time.perf_counter_ns() - start)

    fast_p50 = sorted(fast)[len(fast) // 2] / 1000.0
    slow_p50 = sorted(slow)[len(slow) // 2] / 1000.0
    assert fast_p50 < 0.25 * delay_s * 1e6, (
        f"the real approve path's p50 was {fast_p50:.1f}us against a "
        f"{delay_s * 1e6:.0f}us reference — the fast arm is not fast, so the "
        "comparison below says nothing"
    )
    assert slow_p50 > 0.5 * delay_s * 1e6, (
        f"a Plane-1 port that sleeps {delay_s * 1e6:.0f}us moved the pass's p50 "
        f"only to {slow_p50:.1f}us. Elapsed time inside `GatePass.evaluate` is "
        "not measuring the pass, and no latency claim here may be believed"
    )


# ---------------------------------------------------------------------------
# THE AUDIT-HOOK CENSUS, in a CHILD interpreter
# ---------------------------------------------------------------------------

_CENSUS_CHILD = r'''
import collections, json, os, sys, tempfile
sys.path.insert(0, SCRIPTS)
from nixrisk import gate as gate_mod
from nixrisk.gate import GatePass, default_manifest
from nixrisk.reservations import ReservationLedger
from nixrisk.wal import Plane1Wal
from nixrisk.seam import FinancialPicture, ProposedOrder, Side, StopMode

MODE = sys.argv[1]
N = int(sys.argv[2])

class Clear:
    def read(self, symbol=None): return False, ""
    def is_set(self): return False, ""
    def in_flight(self, strategy_id): return False, ""
    def mark(self): return 10_000_000.0, True

class SocketPlane1:
    """A Plane-1 port that dials a socket per row — the FALSIFIER."""
    def __init__(self):
        import socket
        self._socket = socket
    def enqueue(self, row):
        s = self._socket.socket()
        try:
            s.connect(("127.0.0.1", 1))
        except OSError:
            pass
        finally:
            s.close()

def order(i):
    return ProposedOrder(client_order_id="hp-%d" % i, strategy_id="s1", symbol="ES",
                         side=Side.LONG, qty=4, margin_per_contract=1000.0,
                         stop_ticks=40, stop_mode=StopMode.FIXED, signal_ts=1.0)

picture = FinancialPicture(version=1, published_ts=1.0, balance=1_000_000.0,
                           positions=(), margin_per_contract={"ES": 1000.0},
                           sum_open_margin=0.0, sum_reservations=0.0,
                           committed=0.0, deployable=500_000.0)

tmp = tempfile.mkdtemp(prefix="arc038f-census-%d-" % os.getpid())
wal = Plane1Wal(os.path.join(tmp, "plane1.wal"))
plane1 = SocketPlane1() if MODE == "falsifier" else wal
clear = Clear()
rules = list(default_manifest(blackout=clear, tradability=clear, staleness=clear,
                             clock_skew=clear, in_flight=clear, net_liq=clear,
                             deployable_fraction=0.70, survival_safety_pad=0.10,
                             coherence_tolerance=1e-6))
g = GatePass(clear, rules, ReservationLedger(plane1))
g.evaluate(order(-1), picture, 0.0)          # warm every lazy import

events = collections.Counter()
armed = [False]
sys.addaudithook(lambda event, args: events.update([event]) if armed[0] else None)
armed[0] = True
decisions = collections.Counter()
for i in range(N):
    decisions[g.evaluate(order(i), picture, 1.0 + i).decision.value] += 1
armed[0] = False
wal.close()
for name in os.listdir(tmp):
    os.unlink(os.path.join(tmp, name))
os.rmdir(tmp)
print(json.dumps({
    "gate_file": gate_mod.__file__,
    "evaluations": N,
    "decisions": dict(decisions),
    "audit_events": dict(sorted(events.items())),
    "wal_enqueued": wal.enqueued,
}))
'''


def _run_census(mode: str) -> dict:
    """Drive the census in a CHILD, with an EXPLICIT env (D3.344)."""
    source = _CENSUS_CHILD.replace("SCRIPTS", repr(str(SCRIPTS)))
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    env["PYTHONPATH"] = str(SCRIPTS)
    proc = subprocess.run(  # nosec B603 - argv built here, no shell
        [sys.executable, "-c", source, mode, str(EVALUATIONS)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tempfile.gettempdir(),
        timeout=600,
    )
    assert proc.returncode == 0, f"census child failed: {proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _forbidden(events: dict[str, int]) -> dict[str, int]:
    return {
        name: count
        for name, count in events.items()
        if name.startswith(FORBIDDEN_PREFIXES)
    }


def test_the_SHIPPED_APPROVE_PATH_enters_NO_blocking_audit_event() -> None:
    """§14:965 — *cache reads + arithmetic only*, OBSERVED rather than argued.

    A PEP 578 audit hook cannot be removed and cannot be bypassed by
    re-importing, so a clean result here is an observation and not a belief."""
    result = _run_census("shipped")

    # D3.344: prove the child imported THIS tree before reading any count.
    assert result["gate_file"] == str(SCRIPTS / "nixrisk" / "gate.py"), result[
        "gate_file"
    ]
    # Non-vacuity: the pass was DRIVEN, and it APPROVED, so `_settle` ran.
    assert result["evaluations"] == EVALUATIONS, result
    assert result["decisions"] == {"approve": EVALUATIONS}, result["decisions"]
    assert result["wal_enqueued"] >= EVALUATIONS, result

    offenders = _forbidden(result["audit_events"])
    assert offenders == {}, (
        f"the §14 hot path entered {offenders} across {EVALUATIONS} approved "
        f"evaluations. Full census: {result['audit_events']}"
    )


def test_the_CENSUS_SEES_a_socket_on_the_approve_path() -> None:
    """THE CAN-FAIL HALF. A real `socket.connect` behind the ledger's Plane-1
    port MUST appear by name, or the zero above is about a blind observer."""
    result = _run_census("falsifier")

    assert result["gate_file"] == str(SCRIPTS / "nixrisk" / "gate.py"), result
    offenders = _forbidden(result["audit_events"])
    assert "socket.connect" in offenders, (
        f"a socket dialled once per approval did NOT reach the census: "
        f"{result['audit_events']}. The observer is blind and the clean result "
        "in the sibling control may not be read as a measurement"
    )
    assert offenders["socket.connect"] >= EVALUATIONS, offenders
