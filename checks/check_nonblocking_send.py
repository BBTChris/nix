#!/usr/bin/env python3
"""Module 2 invariant B6 — NO SEND VERB BLOCKS THE CALLER, re-measured live.

ONE gate, ONE property: `nics_risk_subsystem_spec_v1.3.md` §2A:107 invariant 5
and §13 objective 11 (line 904, the one objective the spec marks **critical**)
— *"Non-blocking send. No send verb blocks the caller under any socket
condition; flatten must not block."* It pairs with the Limiter's I9;
`scripts/broker/broker_order_ibkr.py` is the PRODUCER of that guarantee.

WHY THIS GATE IS OWED, AND WHAT IT CLOSES (ARC 059 recon). The property IS met
and WAS measured. ARC 019 A1 drove all four sync send verbs against a real
`ib_async.IB` over a real loopback socket under four conditions — healthy,
silent peer, full send buffer, peer vanished — 5 reps per cell; worst cell in
the whole matrix `0.003295 s`, and the flatten fan-out topped out at
`0.00889 s` at N=20. **That measurement lives in a DOCSTRING and nothing
re-runs it.** A comment is not an instrument: core directive 1 is *prove real
properties, not proxies* and directive 2 is *prefer direct measurement over
inference*, and a prose table is inference about a tree that has moved 40 arcs
since. This gate turns the docstring into a live instrument — it re-drives the
real send verbs on every run and holds them to a declared budget.

WHAT THIS GATE DOES **NOT** PROVE, stated here because the distinction is the
whole risk of building it (ARM 4 below enforces that the file keeps saying so):
**non-blocking is not delivery.** ARC 019 also measured 200 `place_order`
calls into a verified-saturated pipe returning in 0.032 s total with **ZERO
bytes delivered to the peer**. The send path does not block — it ABSORBS. Debt
row D1.22 (a send verb cannot tell the caller whether the order reached the
venue) was NARROWED by ARC 020 A7's `send_backlog()` observability, **not
discharged**. Every evidence string this gate emits says
`non-blocking, NOT delivered (D1.22 open)` for exactly that reason.

FOUR ARMS, none sufficient alone:

  ARM 1 VACUITY GUARD. Subject absent/unparseable, roster unreadable, or a walk
      that inspected ZERO send verbs is CANNOT_MEASURE naming the reason. The
      number of send verbs actually inspected is reported as evidence on every
      run, pass or fail.

  ARM 2 STRUCTURAL (AST, no vendor SDK needed). Every sync send verb's own body
      is walked for blocking constructs — see the ban list below.

  ARM 3 BEHAVIOURAL / TIMED. The REAL `IBKRBrokerOrder` is constructed and
      driven against a deliberately hostile transport that accepts everything,
      drains nothing and answers nothing, and each verb must return inside
      `NONBLOCKING_BUDGET_S`.

  ARM 4 THE HONEST LIMIT MUST STAY STATED. The D1.22 caveat must still be in
      the file; deleting it is a FAIL.

WHAT IS DELIBERATELY **NOT** BANNED HERE (doctrine C.9 — never build a second
instrument over a subject the suite already drives):

  * `asyncio.run` / `run_until_complete` / `run_forever` on the order path are
    `checks/check_order_path_bans.py`'s property, cited to the same §2A:103-107.
    Re-banning them here would give two gates one subject and let them disagree
    the first time either moved.
  * the sync/async PARTITION of the port is `broker_seam.check_await_conformance`'s
    property. This gate consumes the partition (it reads `ORDER_ASYNC_VERBS`)
    and never re-derives or re-judges it; what it judges is `await` appearing
    inside a verb the partition already calls sync.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. **The subject could be absent, unparseable, or not importable.** CLOSED:
    each is CANNOT_MEASURE naming the file and the exception type (§17 — never
    a PASS).
 2. **The walk could find no send verbs and report "no violations".** An empty
    walk is the classic green-on-nothing. CLOSED: fewer than one inspected verb
    is CANNOT_MEASURE, the inspected COUNT and the verb names are in `evidence`
    on every run, and the derived roster is printed with them.
 3. **The verb set could be a list somebody typed**, which goes stale the first
    time a verb is added to the port (`debug.md` §8 failure mode #14). CLOSED:
    `SEND_PATH_VERBS` is DERIVED by AST from `broker_seam.py` —
    `ORDER_PORT_VERBS` minus `ORDER_ASYNC_VERBS` — so a verb added to the port
    lands on the send path automatically, and a roster this gate cannot read is
    CANNOT_MEASURE rather than an empty ban list.
 4. **It could inspect a STUB that happens to carry the right method names.**
    CLOSED twice: the structural arm requires a class defining at least
    `PORT_QUORUM` roster verbs and names it in evidence; the behavioural arm
    asserts the constructed object's own class comes from the module whose
    `__file__` resolves to the subject path under `ctx.nix_home`, so it cannot
    be quietly driving an installed copy.
 5. **The timed arm could drive a FRIENDLY transport that drains instantly**,
    which no send could ever block against. CLOSED: `_HostileTransport` accepts
    into an unbounded outbox, delivers nothing and emits no ack/fill/status;
    the drive asserts `absorbed > 0` and `delivered == 0` and reports both, so
    a transport that quietly started draining would be visible, and a drive
    that sent nothing at all is a finding rather than a pass.
 6. **The budget could be set so loose it catches nothing, or so tight the gate
    is flaky and gets suppressed.** CLOSED by deriving it from the measurement
    it re-runs: see `NONBLOCKING_BUDGET_S`'s own justification.
 7. **A PASS here could be read as "orders reach the venue".** CLOSED: ARM 4
    fails if the in-file D1.22 caveat is deleted, and every evidence string
    this gate emits carries `non-blocking, NOT delivered (D1.22 open)`.
 8. **The behavioural arm could fail to construct the adapter and be reported
    as a pass by a gate that only counted structural findings.** CLOSED: an
    unconstructable adapter is CANNOT_MEASURE naming why, and it is only
    outranked by real structural findings (aggregate rule 4: Fail > Cannot-
    measure), never swallowed by them.
 9. **The gate could mutate the tree it measures.** CLOSED: it opens the two
    subjects read-only and drives the adapter in-process against a fake. It
    writes nothing anywhere. `sys.path`, `sys.modules` and the adapter's logger
    level are saved and restored in `finally` blocks.
"""

# pylint: disable=too-many-return-statements,too-many-instance-attributes
# pylint: disable=invalid-name,missing-function-docstring,missing-class-docstring
# invalid-name: the hostile transport is a STAND-IN FOR ib_async's client, and
# its attribute and method names (`orderStatusEvent`, `placeOrder`,
# `reqPositionsAsync`) must be spelled exactly as the vendor spells them or the
# real adapter will not bind to it — a snake_case rename would silently turn
# the behavioural arm vacuous, which is the one thing this gate must never be.
# too-many-instance-attributes: each attribute is one vendor event the real
# adapter subscribes to; the count is the vendor's surface, not incidental
# state. too-many-return-statements: each return is one distinct
# CANNOT_MEASURE cause named separately, per check-contract rule 11 — merging
# them would collapse the reasons into one exit code.

from __future__ import annotations

import ast
import asyncio
import importlib
import logging
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# pylint: disable=missing-function-docstring,missing-class-docstring
# missing-*-docstring: the hostile transport's verbs are named after the
# `ib_async.IB` surface they stand in for, and each arm function's name states
# its own property; a docstring would restate the name. too-few-public-methods:
# the transport is a one-purpose stand-in. too-many-locals: an arm's local count
# is the drive's own inputs and outputs, not incidental state.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
#: The timed arm is the point of the gate (ARM 3), so this is TIME_BOUND by
#: construction. Its own worst case is bounded: five verbs, at most
#: `NONBLOCKING_BUDGET_S` each before the budget itself fires.
TIME_BOUND = True
#: MEASURED on this box, not budgeted: a real-tree run — two AST parses, three
#: module imports and the full drive — completes in well under a second. 5.0 s
#: is the envelope the runner is told to expect, which stays above
#: `NONBLOCKING_BUDGET_S` x the five verbs so the gate's own budget is what
#: fires on a genuine block, never the runner's.
EXPECTED_S = 5.0
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "interpreter:logging",
    "interpreter:asyncio-event-loop",
)
#: NON-CORRECTABLE: a blocking construct on the send path is a design decision
#: about the protective path. An instrument that deleted a `time.sleep` or a
#: lock until the gate went green would be editing the order path unattended —
#: the class of action risk spec §4 forbids — and the deletion could remove the
#: very synchronisation some other invariant depends on.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a blocking construct on the send path is a deliberate change to the "
    "protective path; removing it automatically would edit the order path "
    "unattended and could delete synchronisation some other invariant relies "
    "on. §2A:107 invariant 5 is a property a human must restore knowingly"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/broker/broker_order_ibkr.py",
    "scripts/broker/broker_seam.py",
)

NAME = "check_nonblocking_send"

ADAPTER_FILE = "scripts/broker/broker_order_ibkr.py"
SEAM_FILE = "scripts/broker/broker_seam.py"
CONFIG_FILE = "risks/broker_order.config.json"
LIMITER_FILE = "risks/limiter.config.json"

ADAPTER_MODULE = "broker_order_ibkr"
SEAM_MODULE = "broker_seam"
CONFIG_MODULE = "broker_order_config"
#: `broker_order_ibkr` imports `broker_order_config` and `broker_seam` as FLAT
#: module names, so BOTH directories have to be importable. Measured, not
#: assumed — the same idiom `check_broker_order_config.load()` uses.
PACKAGE_DIRS = ("scripts", "scripts/broker")
PURGE_MODULES = (ADAPTER_MODULE, SEAM_MODULE, CONFIG_MODULE)

#: The roster constants, read by AST out of the seam. Never imported: an import
#: would run the seam, and a gate that has to execute its subject to learn what
#: to measure cannot report on a subject that fails to import.
ROSTER_CONST = "ORDER_PORT_VERBS"
ASYNC_CONST = "ORDER_ASYNC_VERBS"

#: How many roster verbs a class must define before it counts as a real order
#: adapter rather than a name-alike stub. Four, matching
#: `check_order_path_bans.PORT_QUORUM` — the smallest real adapter in this tree
#: defines all nine, and the highest incidental overlap outside the order path
#: is zero.
PORT_QUORUM = 4

#: THE BUDGET, AND WHY IT IS THIS NUMBER.
#:
#: DERIVED FROM THE MEASUREMENT THIS GATE RE-RUNS, not chosen for comfort. ARC
#: 019 A1's worst cell across the whole four-condition matrix was 0.003295 s
#: (flatten at N=5, peer vanished), and the flatten fan-out topped out at
#: 0.00889 s at N=20 (peer accepts, never responds). 0.5 s is ~152x the worst
#: single-verb cell and ~56x the worst fan-out.
#:
#: WHY SO MUCH HEADROOM, deliberately. The defect this arm exists to catch is a
#: BLOCK — a socket wait, a lock, a sleep, a join — and every one of those is
#: unbounded or on the order of seconds, not microseconds. A budget of, say,
#: 0.02 s would separate "blocking" from "not blocking" no better and would
#: redden on an ordinary loaded box, on a cold import, or under a GC pause. A
#: FLAKY GATE GETS SUPPRESSED, and a suppressed gate measures nothing at all —
#: which is the state this gate was written to end. The headroom buys
#: reliability at no cost in discrimination.
NONBLOCKING_BUDGET_S = 0.5

#: The flatten fan-out size the recon measured. Held here so the drive re-runs
#: the SAME shape rather than a smaller one that would hide per-symbol cost.
FLATTEN_FANOUT_N = 20
#: Reps per verb, matching ARC 019's 5. The WORST rep is what is judged.
REPS = 5

#: ARM 4 — the statement of the honest limit, in fragments. Whitespace is
#: normalised and matching is case-insensitive before these are searched for,
#: because the caveat is prose inside a docstring and re-wrapping a paragraph
#: must not read as deleting it. Each fragment is a DISTINCT claim, so a
#: rewrite that drops one is named individually.
CAVEAT_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("debt-row", "d1.22"),
    ("the-measurement", "200 `place_order` calls"),
    ("the-total", "0.032 s"),
    ("the-finding", "zero bytes delivered to the peer"),
    ("the-reading", "does not block"),
    ("the-mechanism", "absorbs"),
)

#: The evidence phrase every verdict carries. A PASS from this gate is a claim
#: about BLOCKING and about nothing else.
DELIVERY_CAVEAT = "non-blocking, NOT delivered (D1.22 open)"

_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


# ---------------------------------------------------------------------------
# ARM 2 — the ban list, as DATA. Adding a construct is a one-line edit.
# ---------------------------------------------------------------------------
#: Calls whose LAST dotted name is one of these block unconditionally.
SLEEP_NAMES = frozenset({"sleep"})
ACQUIRE_NAMES = frozenset({"acquire"})
WAIT_NAMES = frozenset({"wait", "result", "wait_for", "join_thread"})
RECV_NAMES = frozenset({"recv", "recvfrom", "recv_into", "recvmsg", "readline"})
#: `.get`/`.put` are only blocking when they are a `queue.Queue`'s — flagged
#: ONLY when a `block=` keyword is present. A bare `dict.get(k)` is not a
#: blocking construct and `flatten` uses one on the position mirror, so a blind
#: ban would redden the correct implementation of the subject (doctrine B.4:
#: that gate is broken, not strict).
QUEUE_NAMES = frozenset({"get", "put"})
#: `.join` is `str.join` far more often than `Thread.join`. Discriminated
#: STRUCTURALLY, not by name: `", ".join(x)` carries exactly one positional
#: argument; `t.join()` carries none, and `t.join(timeout=…)` carries a
#: `timeout` keyword. `flatten` contains a `str.join` today, which is why this
#: distinction is load-bearing rather than pedantic.
JOIN_NAMES = frozenset({"join"})


@dataclass
class Loaded:
    adapter: ModuleType
    seam: ModuleType
    config: ModuleType


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in PURGE_MODULES:
        sys.modules.pop(name, None)
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the three flat modules out of `home`, restoring the interpreter."""
    saved_path = list(sys.path)
    saved_modules = {
        key: value for key, value in sys.modules.items() if key in PURGE_MODULES
    }
    for name in PURGE_MODULES:
        sys.modules.pop(name, None)
    for rel in PACKAGE_DIRS:
        sys.path.insert(0, str((home / rel).resolve()))
    importlib.invalidate_caches()
    try:
        adapter = importlib.import_module(ADAPTER_MODULE)
        return (
            Loaded(
                adapter=adapter,
                seam=sys.modules[SEAM_MODULE],
                config=sys.modules[CONFIG_MODULE],
            ),
            "",
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{ADAPTER_FILE}: cannot import {ADAPTER_MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# ---------------------------------------------------------------------------
# AST helpers — the roster is READ, never imported (see ROSTER_CONST)
# ---------------------------------------------------------------------------
def _string_elements(value: ast.expr) -> list[str] | None:
    """The string literals of a Tuple/List/Set, or of `frozenset({...})`."""
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        if value.func.id not in ("frozenset", "set", "tuple", "list"):
            return None
        if len(value.args) != 1:
            return None
        return _string_elements(value.args[0])
    if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return None
    return [
        elt.value
        for elt in value.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    ]


def _module_names(tree: ast.Module, name: str) -> list[str] | None:
    """A module-level `NAME = (...)` / `NAME: T = frozenset({...})`, by AST."""
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        if value is None:
            continue
        found = _string_elements(value)
        if found:
            return found
    return None


def _dotted_tail(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _has_keyword(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _call_defect(call: ast.Call) -> str:
    """The blocking construct this call IS, or `''`."""
    tail = _dotted_tail(call.func)
    if tail in SLEEP_NAMES:
        return f"a sleep — `{tail}(...)`"
    if tail in ACQUIRE_NAMES:
        return f"a lock acquisition — `.{tail}(...)`"
    if tail in WAIT_NAMES:
        return f"a future/event wait — `.{tail}(...)`"
    if tail in RECV_NAMES:
        return f"a socket read — `.{tail}(...)`"
    if tail in QUEUE_NAMES and _has_keyword(call, "block"):
        return f"a blocking queue operation — `.{tail}(..., block=...)`"
    if tail in JOIN_NAMES and (not call.args or _has_keyword(call, "timeout")):
        return "a thread join — `.join()` with no positional argument"
    return ""


def _blocking_hits(func: ast.AST) -> list[tuple[int, str]]:
    """Every blocking construct inside this verb's own body. (lineno, what).

    The WHOLE subtree is walked, nested definitions included. Fail-closed on
    purpose: a `def` nested inside a send verb exists to be called from it, and
    letting the walk stop at a nested scope is exactly the seam a defect would
    be moved through. No send verb in this tree contains one today, so the
    strictness costs nothing and the walk cannot be narrowed silently.
    """
    hits: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Await):
            hits.append((node.lineno, "an `await` — the caller is suspended"))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.AsyncWith) or isinstance(node, ast.AsyncWith):
                    hits.append(
                        (node.lineno, "an `async with` — the caller is suspended")
                    )
                elif not isinstance(ctx, ast.Call):
                    # `with self._lock:` / `with LOCK:` — entering an ALREADY
                    # CONSTRUCTED object is the lock idiom. `with open(...)` and
                    # `with contextlib.suppress(...)` are Calls and are not
                    # flagged, which is what keeps this structural rather than a
                    # name heuristic (debug.md §8 failure mode #4).
                    hits.append(
                        (
                            node.lineno,
                            "a `with <already-constructed object>:` — lock acquisition",
                        )
                    )
        elif isinstance(node, ast.Call):
            defect = _call_defect(node)
            if defect:
                hits.append((node.lineno, defect))
    return sorted(set(hits))


# ---------------------------------------------------------------------------
# ARM 3 — the hostile transport. Accepts everything, drains nothing, answers
# nothing. This is the "peer that accepts nothing" condition of the ARC 019
# matrix, reproduced in-process because the property under test is what the
# CALLER experiences, and the caller cannot tell a real saturated socket from
# one that absorbs and never delivers — which is precisely D1.22.
# ---------------------------------------------------------------------------
class _Event:
    """`ib_async`'s Event surface: `+=` to subscribe, call to emit."""

    def __init__(self) -> None:
        self._handlers: list = []

    def __iadd__(self, fn):
        self._handlers.append(fn)
        return self

    def emit(self, *args) -> None:
        for handler in list(self._handlers):
            handler(*args)


@dataclass
class _HostileTransport:
    """Everything written to it is ABSORBED. Nothing is ever delivered."""

    next_order_id: int = 1
    outbox: list = field(default_factory=list)
    delivered: int = 0
    #: `send_backlog()` reads this; `None` is the vendor's own CANNOT-MEASURE.
    client: object = None

    def __post_init__(self) -> None:
        self.orderStatusEvent = _Event()
        self.execDetailsEvent = _Event()
        self.errorEvent = _Event()
        self.positionEvent = _Event()
        self.accountValueEvent = _Event()
        self.disconnectedEvent = _Event()

    async def connectAsync(self, host, port, clientId, timeout=10, fetchFields=None):  # pylint: disable=invalid-name,unused-argument
        await asyncio.sleep(0)  # the venue does not answer synchronously

    def disconnect(self) -> None:
        self.outbox.append(("disconnect",))

    def placeOrder(self, contract, order):
        order.orderId = self.next_order_id
        self.next_order_id += 1
        self.outbox.append(("place", contract, order))
        return SimpleNamespace(
            order=order,
            contract=contract,
            orderStatus=SimpleNamespace(
                status="PendingSubmit", filled=0, remaining=order.totalQuantity
            ),
        )

    def cancelOrder(self, order, manualCancelOrderTime=""):
        # pylint: disable=invalid-name,unused-argument
        self.outbox.append(("cancel", order))

    async def reqPositionsAsync(self):
        await asyncio.sleep(0)
        return []

    @property
    def absorbed(self) -> int:
        return len(self.outbox)


def _contract(symbol: str):
    """A futures contract carrying a REAL multiplier, as IBKR sends it (a str)."""
    return SimpleNamespace(
        localSymbol=symbol, symbol=symbol[:3], conId=793356217, multiplier="5"
    )


@dataclass
class Drive:
    """What the timed arm observed. `worst` is per verb, seconds."""

    worst: dict[str, float]
    absorbed: int
    delivered: int
    adapter_file: str


def _time_call(fn, *args) -> float:
    start = time.perf_counter()
    fn(*args)
    return time.perf_counter() - start


def _drive(loaded: Loaded, home: Path) -> tuple[Drive | None, str]:
    """Construct the REAL adapter and time every sync send verb. Or say why not."""
    seam = loaded.seam
    for rel in (CONFIG_FILE, LIMITER_FILE):
        if not (home / rel).is_file():
            return None, (
                f"{rel} is absent, so the real adapter cannot be constructed — "
                "its §12A config is boot-loaded with no default-on-missing path. "
                "The timed arm measured nothing (§17: never a PASS)"
            )
    try:
        cfg = loaded.config.load_broker_order_config(
            path=home / CONFIG_FILE, limiter_path=home / LIMITER_FILE
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{CONFIG_FILE}: the adapter's own loader refused the shipped config "
            f"({type(exc).__name__}: {exc}), so the real adapter cannot be "
            "constructed and the timed arm measured nothing (§17)"
        )

    sink = seam.RecordingSink()
    transport = _HostileTransport()
    log = logging.getLogger("nix.broker_order.ibkr")
    saved_level, saved_propagate = log.level, log.propagate
    try:
        # The adapter logs at WARNING on a session teardown with orders in
        # flight — which is the NORMAL end state of this drive, since the
        # hostile peer acknowledges nothing. Silenced for the drive only, and
        # restored below: presentation output must not carry a check's own
        # test noise (check contract rule 8).
        log.setLevel(logging.CRITICAL + 1)
        log.propagate = False
        adapter = loaded.adapter.IBKRBrokerOrder(
            sink,
            ib=transport,
            contract_resolver=_contract,
            client_id=905,
            config=cfg,
        )
        # ANTI-STUB, and NOT via `inspect.getsourcefile`: `load()` restores
        # `sys.modules` in its own `finally`, so the adapter's module is no
        # longer registered by name and `inspect` reports it a built-in class.
        # The module OBJECT is still held, and its `__file__` is the fact that
        # matters — which file the class actually came from.
        source = getattr(loaded.adapter, "__file__", None)
        expected = str((home / ADAPTER_FILE).resolve())
        if (
            type(adapter).__module__ != ADAPTER_MODULE
            or source is None
            or str(Path(source).resolve()) != expected
        ):
            return None, (
                f"the constructed adapter is {type(adapter).__module__}."
                f"{type(adapter).__name__} from {source!r}, not from "
                f"{expected!r} — the timed arm would have measured a DIFFERENT "
                "file from the one this gate names as its subject (§7.12 hole 4)"
            )
        asyncio.run(adapter.connect())
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{ADAPTER_FILE}: the real adapter could not be brought to a live "
            f"session against the hostile transport — {type(exc).__name__}: "
            f"{exc}. Nothing was timed (§17: never a PASS; if this needs a live "
            "venue it is CANNOT_MEASURE, never a PASS)"
        )
    finally:
        log.setLevel(saved_level)
        log.propagate = saved_propagate

    try:
        log.setLevel(logging.CRITICAL + 1)
        log.propagate = False
        # The flatten fan-out is sized from the position MIRROR, which is fed by
        # positionEvent — so the fan-out shape is set here, at N=20, the same N
        # the ARC 019 table's widest column used.
        for index in range(FLATTEN_FANOUT_N):
            transport.positionEvent.emit(
                SimpleNamespace(
                    contract=_contract(f"MES{index:02d}"), position=1, avgCost=5.0
                )
            )
        worst: dict[str, float] = {}
        orders = [
            seam.NeutralOrder(
                f"nbs-{n}",
                "MES00",
                seam.Side.BUY,
                1,
                seam.OrderType.MARKET,
                seam.TimeInForce.DAY,
            )
            for n in range(REPS)
        ]
        worst["place_order"] = max(
            _time_call(adapter.place_order, order) for order in orders
        )
        worst["query_order_status"] = max(
            _time_call(adapter.query_order_status, order.client_order_id)
            for order in orders
        )
        worst["cancel_order"] = max(
            _time_call(adapter.cancel_order, order.client_order_id) for order in orders
        )
        # ONE flatten, not five: the idempotency window deliberately suppresses
        # a repeat inside it, so reps two through five would measure the
        # suppression path rather than the fan-out.
        worst["flatten"] = _time_call(adapter.flatten)
        worst["disconnect"] = _time_call(adapter.disconnect)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{ADAPTER_FILE}: a send verb RAISED during the timed drive — "
            f"{type(exc).__name__}: {exc}. A verb that raises was not timed, so "
            "the non-blocking property is unmeasured here (§17: never a PASS)"
        )
    finally:
        log.setLevel(saved_level)
        log.propagate = saved_propagate

    return (
        Drive(
            worst=worst,
            absorbed=transport.absorbed,
            delivered=transport.delivered,
            adapter_file=expected,
        ),
        "",
    )


# ---------------------------------------------------------------------------
# The arms
# ---------------------------------------------------------------------------
@dataclass
class Walk:
    """What ARM 2 found. `blocked` is the reason it could not walk, if any."""

    send_verbs: tuple[str, ...] = ()
    inspected: tuple[str, ...] = ()
    adapter_class: str = ""
    findings: list[tuple[str, str]] = field(default_factory=list)
    blocked: str = ""


def _send_path_verbs(seam_tree: ast.Module) -> tuple[tuple[str, ...], str]:
    """`ORDER_PORT_VERBS` minus `ORDER_ASYNC_VERBS`, both read by AST."""
    roster = _module_names(seam_tree, ROSTER_CONST)
    if not roster:
        return (), (
            f"{SEAM_FILE} does not declare a readable `{ROSTER_CONST}` — the "
            "send-verb set is DERIVED from it and cannot be derived, so nothing "
            "was walked (§17: never a PASS)"
        )
    asyncs = _module_names(seam_tree, ASYNC_CONST)
    if not asyncs:
        return (), (
            f"{SEAM_FILE} does not declare a readable `{ASYNC_CONST}` — the sync "
            "half of the port is derived by SUBTRACTION and an unreadable async "
            "set would silently make every verb send-path (§17)"
        )
    unknown = sorted(set(asyncs) - set(roster))
    if unknown:
        return (), (
            f"{ASYNC_CONST} names {', '.join(unknown)}, absent from "
            f"{ROSTER_CONST} — the two rosters disagree, so the sync/async "
            "partition this gate consumes is not trustworthy (§17)"
        )
    send = tuple(verb for verb in roster if verb not in set(asyncs))
    if not send:
        return (), (
            f"every verb in {ROSTER_CONST} is declared async — there is no send "
            "path left to walk, which would make this gate vacuous (§17)"
        )
    return send, ""


def _parse_subjects(home: Path) -> tuple[ast.Module | None, ast.Module | None, str]:
    """STEP of `_arm_structural`, comparison-free. NOT A SECOND GATE.

    `nix_check_contract.md` check-rule 8 is one gate per property, and the
    property here is still ARM 1 + ARM 2's — one owner, `_arm_structural`,
    which is this function's only caller. What is split out is a step, not a
    verdict: nothing calls this and reports a result, and it has no exit code,
    no registration and no independent meaning. The split exists because the
    gate crossed the tree's cognitive-complexity ceiling and the two available
    answers were to decompose it or to raise the ceiling. Raising a ceiling to
    admit code is doctrine B.4's forbidden direction; decomposition changes no
    verdict on any input.

    Returns both parsed subjects, or `(None, None, reason)` — the reason string
    is `_arm_structural`'s `Walk.blocked`, unchanged in wording.
    """
    adapter_path = home / ADAPTER_FILE
    seam_path = home / SEAM_FILE
    for path, rel in ((adapter_path, ADAPTER_FILE), (seam_path, SEAM_FILE)):
        if not path.is_file():
            return None, None, f"{rel} is absent — nothing to measure (§17)"
    try:
        adapter_tree = ast.parse(
            adapter_path.read_text(encoding="utf-8"), filename=str(adapter_path)
        )
        seam_tree = ast.parse(
            seam_path.read_text(encoding="utf-8"), filename=str(seam_path)
        )
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        return (
            None,
            None,
            (
                f"a subject could not be parsed — {type(exc).__name__}: {exc}. "
                "An unparseable subject is CANNOT_MEASURE, never a PASS (§17)"
            ),
        )
    return adapter_tree, seam_tree, ""


def _verb_findings(
    class_name: str, methods: Mapping[str, ast.AST], send_verbs: tuple[str, ...]
) -> tuple[list[str], list[tuple[str, str]]]:
    """STEP of `_arm_structural` — ONE candidate class's send verbs. NOT A SECOND GATE.

    Same standing as `_parse_subjects` above: a step of ARM 2 with one caller
    (`_walk_adapter_classes`), no exit code, no registration, no independent
    meaning. It decides nothing the undecomposed walk did not decide; the ban
    list itself still lives in `_blocking_hits`/`_call_defect`, which this only
    calls. Returns `(inspected verb labels, findings)` in walk order.
    """
    inspected: list[str] = []
    findings: list[tuple[str, str]] = []
    for verb in send_verbs:
        method = methods.get(verb)
        if method is None:
            continue
        inspected.append(f"{class_name}.{verb}")
        for lineno, what in _blocking_hits(method):
            findings.append(
                (
                    f"{ADAPTER_FILE}:{lineno}",
                    (
                        f"send verb `{class_name}.{verb}` contains {what} — "
                        f"§2A:107 invariant 5 and §13 objective 11 (critical) "
                        f"require that no send verb blocks the caller, and "
                        f"`flatten` is the protective path"
                    ),
                )
            )
    return inspected, findings


def _walk_adapter_classes(
    adapter_tree: ast.Module, roster: frozenset[str], send_verbs: tuple[str, ...]
) -> tuple[str, list[str], list[tuple[str, str]]]:
    """STEP of `_arm_structural` — the class walk. NOT A SECOND GATE.

    Same standing as `_parse_subjects` above: one caller (`_arm_structural`),
    no exit code, no registration, no independent meaning. The anti-stub quorum
    it applies is ARM 1's, evaluated exactly where it was before the split;
    returning an empty `adapter_class` or an empty `inspected` is NOT a verdict
    here — `_arm_structural` still owns what those mean.
    """
    findings: list[tuple[str, str]] = []
    inspected: list[str] = []
    adapter_class = ""
    for node in ast.walk(adapter_tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {m.name: m for m in node.body if isinstance(m, _FUNC_NODES)}
        if len(set(methods) & roster) < PORT_QUORUM:
            # ARM 1, anti-stub: a class carrying one or two roster names is not
            # an order adapter, and walking it would let a stub stand in for the
            # subject (§7.12 hole 4).
            continue
        adapter_class = adapter_class or node.name
        verbs, hits = _verb_findings(node.name, methods, send_verbs)
        inspected.extend(verbs)
        findings.extend(hits)
    return adapter_class, inspected, findings


def _arm_structural(home: Path) -> Walk:
    """ARM 1 + ARM 2 — derive the send verbs, then walk their bodies."""
    adapter_tree, seam_tree, unreadable = _parse_subjects(home)
    if adapter_tree is None or seam_tree is None:
        return Walk(blocked=unreadable)

    send_verbs, complaint = _send_path_verbs(seam_tree)
    if complaint:
        return Walk(blocked=complaint)

    roster = frozenset(_module_names(seam_tree, ROSTER_CONST) or ())
    adapter_class, inspected, findings = _walk_adapter_classes(
        adapter_tree, roster, send_verbs
    )

    if not adapter_class:
        return Walk(
            blocked=(
                f"{ADAPTER_FILE} declares no class defining at least "
                f"{PORT_QUORUM} of {ROSTER_CONST} — the file this gate is "
                "pointed at is not an order adapter, so nothing was walked "
                "(§17: never a PASS)"
            )
        )
    if not inspected:
        return Walk(
            blocked=(
                f"the walk of {ADAPTER_FILE} inspected ZERO send verbs "
                f"(derived send path: {', '.join(send_verbs)}). An empty walk is "
                "never a PASS (§7.12 hole 2)"
            )
        )
    return Walk(
        send_verbs=send_verbs,
        inspected=tuple(inspected),
        adapter_class=adapter_class,
        findings=findings,
    )


def _arm_caveat(home: Path) -> list[tuple[str, str]]:
    """ARM 4 — the D1.22 honest limit must still be stated in the file."""
    path = home / ADAPTER_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [(ADAPTER_FILE, f"unreadable while checking the caveat: {exc!r}")]
    flat = re.sub(r"\s+", " ", text).lower()
    missing = [
        f"{label} ({fragment!r})"
        for label, fragment in CAVEAT_FRAGMENTS
        if fragment not in flat
    ]
    if not missing:
        return []
    return [
        (
            f"{ADAPTER_FILE}:D1.22-caveat",
            (
                "the statement of the HONEST LIMIT has been deleted or reworded "
                f"past recognition — missing: {'; '.join(missing)}. ARC 019 "
                "measured 200 place_order calls into a saturated pipe returning "
                "in 0.032 s with ZERO bytes delivered: the send path does not "
                "block, it ABSORBS. D1.22 was NARROWED by ARC 020 A7, not "
                "discharged. Without that caveat in the file, a green "
                "non-blocking gate reads as proof of DELIVERY, which it is not"
            ),
        )
    ]


def _arm_timed(drive: Drive) -> list[tuple[str, str]]:
    """ARM 3's verdict over an already-completed drive."""
    findings: list[tuple[str, str]] = []
    if drive.absorbed <= 0:
        findings.append(
            (
                f"{ADAPTER_FILE}:timed",
                (
                    "the hostile transport absorbed NOTHING — the drive called the "
                    "send verbs without any of them reaching the transport, so the "
                    "timings measure an empty path (§7.12 hole 5)"
                ),
            )
        )
    if drive.delivered:
        findings.append(
            (
                f"{ADAPTER_FILE}:timed",
                (
                    f"the hostile transport reported {drive.delivered} delivered "
                    "message(s); it is built to deliver none, so the condition this "
                    "arm claims to have measured did not hold (§7.12 hole 5)"
                ),
            )
        )
    for verb, seconds in sorted(drive.worst.items()):
        if seconds > NONBLOCKING_BUDGET_S:
            findings.append(
                (
                    f"{ADAPTER_FILE}:{verb}",
                    (
                        f"send verb `{verb}` took {seconds:.6f} s against a peer "
                        f"that never drains, exceeding the budget of "
                        f"{NONBLOCKING_BUDGET_S} s — IT BLOCKED. §2A:107 "
                        "invariant 5 / §13 objective 11 (critical): no send verb "
                        "blocks the caller under any socket condition, and "
                        "flatten must not block"
                    ),
                )
            )
    return findings


def _evidence(walk: Walk, drive: Drive | None, timed_note: str) -> str:
    measured = (
        ", ".join(
            f"{verb} {seconds:.6f}s" for verb, seconds in sorted(drive.worst.items())
        )
        if drive is not None
        else timed_note
    )
    absorbed = (
        f"{drive.absorbed} message(s) absorbed, {drive.delivered} delivered"
        if drive is not None
        else "not driven"
    )
    return (
        f"{ADAPTER_FILE}: walked {len(walk.inspected)} send verb(s) "
        f"({', '.join(walk.inspected)}) derived as {ROSTER_CONST} minus "
        f"{ASYNC_CONST} from {SEAM_FILE} -> {', '.join(walk.send_verbs)}; "
        f"adapter class {walk.adapter_class} (>= {PORT_QUORUM} roster verbs, so "
        f"not a stub); then drove the REAL adapter against a transport that "
        f"never drains, {REPS} reps per verb, flatten fan-out N="
        f"{FLATTEN_FANOUT_N}, budget {NONBLOCKING_BUDGET_S}s — worst per verb: "
        f"{measured}; transport {absorbed}; the D1.22 honest-limit caveat is "
        f"still stated in the file. THIS GATE PROVES {DELIVERY_CAVEAT}"
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        walk = _arm_structural(ctx.nix_home)
        if walk.blocked:
            return CheckResult(
                name=NAME, status=Status.CANNOT_MEASURE, detail=walk.blocked
            )
        loaded, load_error = load(ctx.nix_home)
        drive: Drive | None = None
        timed_note = load_error
        if loaded is not None:
            drive, timed_note = _drive(loaded, ctx.nix_home)

        findings = list(walk.findings)
        findings += _arm_caveat(ctx.nix_home)
        if drive is not None:
            findings += _arm_timed(drive)

        evidence = _evidence(walk, drive, timed_note)
        if findings:
            # Fail > Cannot-measure (check contract rule 4): a real structural or
            # caveat defect is reported as the FAIL it is, and an unrunnable
            # timed arm is carried in the detail rather than swallowing it.
            detail = "; ".join(f"{site}: {why}" for site, why in findings)
            if drive is None:
                detail += f"; ALSO, the timed arm could not run: {timed_note}"
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail=detail,
            )
        if drive is None:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                evidence=evidence,
                detail=(
                    "the STRUCTURAL arm found no blocking construct, but the "
                    f"BEHAVIOURAL arm could not run: {timed_note}. A property "
                    "proven while half its instrument is unavailable is not "
                    "proven (check contract rule 10)"
                ),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
