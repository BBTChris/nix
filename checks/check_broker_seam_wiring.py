#!/usr/bin/env python3
"""SEAM WIRING — the §2A broker-order seam is ONE seam, and the Limiter HOLDS it.

ONE gate, ONE property: Module 2 invariant **B12-1** (ARC 061). *"The process
that owns the Limiter constructs the REAL broker-order adapter, across ONE seam
module object, without reaching a venue."* This is the FIRST gate in the tree
that spans the §2A seam — every gate before it measured one side or the other.

WHY A NEW GATE IS OWED (measured, ARC 060 S1 / CHECK-DEBT D3.485):

  (a) **THE SEAM COULD BE LOADED TWICE.** `broker_order_ibkr.py` reaches the
      seam by its FLAT name. A consumer with BOTH `<home>/scripts` and
      `<home>/scripts/broker` on `sys.path` therefore reaches ONE FILE under TWO
      module names — `broker_seam` and `broker.broker_seam` — and Python builds
      TWO module objects, with TWO `SessionState` classes, for which `is` is
      FALSE. Nothing in the tree measured that.
  (b) **AND THE DEFECT FAILS OPEN.** `_publish_session`'s non-transition rule is
      an IDENTITY comparison (`state is SessionState.DOWN`). Under the double
      load it silently cannot fire: the ARC 016 teardown sequence emits TWO
      `on_session(DOWN)` events instead of one, which is D1.17 reappearing with
      the adapter entirely innocent. No exception, no log line, no red test.
  (c) **NOTHING PROVED THE LIMITER CONSTRUCTS AN ADAPTER AT ALL.** Until ARC 061
      `limiterd.py` and every `scripts/nixrisk/*.py` imported NO broker module,
      so §2A's port was satisfied by nothing with a pid (CHECK-DEBT B12/D3.352).

SCOPE FENCE — READ THIS BEFORE CITING THIS GATE. This gate proves CONSTRUCTION
and IDENTITY. It does NOT prove that broker events reach the Limiter's handlers:
`limiterd.UnwiredOrderEventSink` routes nothing on purpose, and wiring it is
B12-2's work with B12-2's proof. A green here is *"one seam, a real adapter
behind the port, and no venue dialled"* — not *"the Limiter is wired"*.

THE FOUR ARMS

  ARM 1 — ONE SEAM MODULE OBJECT, and every §2A seam TYPE a single class object
          under both spellings. The type list is DERIVED BY SHAPE from the seam
          module, never spelled here.
  ARM 2 — THE IDENTITY GUARD ACTUALLY FIRES. The real adapter is constructed
          with a recording sink and DRIVEN: UP -> DOWN -> DOWN through
          `_publish_session`, using the PACKAGE-spelling enum. Exactly ONE
          `on_session(DOWN)` must be emitted.
  ARM 3 — THE PRODUCTION CONSTRUCTION SITE EXISTS AND IS REAL.
          `limiterd.construct_broker_order_port()` is CALLED; what it returns
          must be a `BrokerOrderPort`, must be the adapter class the Limiter
          itself holds, must come from a file inside `<home>/scripts/broker/`,
          and must satisfy every port verb DERIVED from the roster and the
          Protocol.
  ARM 4 — NO LIVE CONNECT ON THE CONSTRUCTION PATH, proven two ways: the
          injected client is `None` (the adapter's own documented "caller must
          supply before connect()"), and every socket dial attempted during the
          call is INTERCEPTED, REFUSED and NAMED.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. **COMPARING ZERO SEAM TYPES** (condition A, failure mode #2). A derivation
    that saw no classes would loop zero times and agree with itself. CLOSED:
    ARM 1 counts what it compared, a count of zero is CANNOT_MEASURE naming the
    empty derivation, and the count is in `evidence` on EVERY run — so a
    silently-narrowing derivation is visible in the record.
 2. **COMPARING ZERO PORT VERBS.** Same hole one arm along. CLOSED: ARM 3
    refuses an empty verb set — the roster and the Protocol's declared members
    are UNIONED, so both would have to be empty, and either is reported.
 3. **A HARDCODED VERB OR TYPE LIST** (D3.426, the moving anchor). A gate
    holding its own copy of "the nine verbs" measures its own literal and goes
    stale the day the contract moves. CLOSED: `seam_types()` derives the types BY
    SHAPE (public classes the seam module itself defines) and `port_verbs()`
    derives the verbs from `ORDER_PORT_VERBS` unioned with `BrokerOrderPort`'s
    own declared members. Neither is typed here.
 4. **ASSERTING THE CLASSES ARE IDENTICAL AND STOPPING THERE** (Part C rule 1 —
    a proxy, not the property). Object identity is what the guard USES, not the
    guard firing. CLOSED: ARM 2 DRIVES `_publish_session` on a real constructed
    adapter and counts the emissions at the SINK, outside the method. The
    property measured is the event count, not the `is`.
 5. **INTROSPECTING A STUB INSTEAD OF THE ADAPTER.** The seam ships
    `StubBrokerOrder` and `HollowBrokerOrder`, both of which satisfy the port by
    construction. CLOSED: ARM 3 requires the constructed object's class to BE the
    class the LIMITER holds, and its file to resolve inside `<home>/scripts/
    broker/` — so a stand-in cannot satisfy this arm.
 6. **IMPORT SUCCESS STANDING IN FOR CONSTRUCTION** (Part C rule 1 again: never
    import-success, never file-presence). CLOSED: nothing here is satisfied by
    an import. The constructor is CALLED and its return value is interrogated;
    a `construct_broker_order_port` that returns `None` is a FAIL, not a pass.
 7. **THE NO-CONNECT CLAIM RESTING ON A PROMISE.** "It does not connect" is a
    sentence in a docstring. CLOSED: ARM 4(b) replaces `socket.socket.connect`
    and `connect_ex` for the DURATION of the call, records every dial and refuses
    it with `ECONNREFUSED`, so a path that reaches a venue is NAMED with the
    address. Nothing is dialled, and the gateway's state is irrelevant here.
 8. **A SUBJECT THAT WILL NOT IMPORT SCORED AS CLEAN.** CLOSED: every
    unresolvable subject — a module that will not import, an absent Protocol, a
    missing enum member, an adapter class the Limiter does not hold — is
    CANNOT_MEASURE NAMING IT (§17 / check-rule 10), never a PASS.
 9. **THE GATE MUTATING THE SUBJECT TO GO GREEN.** CLOSED: `CORRECTABLE =
    False`; see `NON_CORRECTABLE_REASON`. This gate writes no file.
10. **INTERPRETER SIDE-EFFECTS LEAKING.** The subject mutates `sys.path` at
    import (`limiterd.py` inserts `<home>/scripts/broker` itself), and this gate
    adds two entries and patches `socket.socket`. Anything left behind would
    change what every later check imports and dials. CLOSED: `_tree_imported()`
    and `_socket_sentinel()` restore in a `finally`, and the suite asserts it.
"""

from __future__ import annotations

import contextlib
import errno
import importlib
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any, Generic, NamedTuple, Protocol

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: `sys.path` and `sys.modules` because the tree under measurement is IMPORTED;
#: `socket.socket` because ARM 4(b) replaces two of its methods for the duration
#: of one call. All three are interpreter-global and all three are restored.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "interpreter:socket.socket",
)
#: NON-CORRECTABLE: every defect this gate can find is a wiring decision.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every defect this gate can find is a decision about how the Limiter is "
    "wired to §2A — which module name the seam is reached by, which class the "
    "construction site builds, which verbs the port carries, whether that path "
    "may dial a venue. An instrument that inserted a `sys.modules` alias, "
    "rewrote a construction site, or stubbed out a socket call until it went "
    "green would be REWIRING A DAEMON to make itself green: doctrine B.4's "
    "forbidden direction, and the one repair that destroys the evidence"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/limiterd.py",
    "scripts/broker/broker_order_ibkr.py",
    "scripts/broker/broker_seam.py",
)

NAME = "check_broker_seam_wiring"

LIMITER_FILE = "scripts/limiterd.py"
ADAPTER_FILE = "scripts/broker/broker_order_ibkr.py"
SEAM_FILE = "scripts/broker/broker_seam.py"
SUBJECT_FILES = (LIMITER_FILE, ADAPTER_FILE, SEAM_FILE)

#: Module names DERIVED from the subject paths rather than typed twice:
#: `scripts/broker/broker_seam.py` is reachable as `broker_seam` (flat) and as
#: `broker.broker_seam` (package), and D3.485 is the claim that the two names
#: resolve to ONE module object.
BROKER_PKG = Path(SEAM_FILE).parent.name
SEAM_FLAT = Path(SEAM_FILE).stem
SEAM_PKG = f"{BROKER_PKG}.{SEAM_FLAT}"
LIMITER_MODULE = Path(LIMITER_FILE).stem
ADAPTER_STEM = Path(ADAPTER_FILE).stem

#: THE DOUBLE-LOAD `sys.path` SHAPE, reproduced deliberately: BOTH the package
#: dir and the broker dir — the shape under which one file used to become two
#: module objects, so the shape ARM 1 has to measure under.
PACKAGE_DIRS = ("scripts", BROKER_PKG and f"scripts/{BROKER_PKG}")

ADAPTER_CLASS = "IBKRBrokerOrder"
CONSTRUCTOR = "construct_broker_order_port"
PORT_PROTOCOL = "BrokerOrderPort"
VERB_ROSTER = "ORDER_PORT_VERBS"
SESSION_ENUM = "SessionState"

#: The teardown sequence ARC 016 measured, as (enum MEMBER NAME, reason). The
#: member names are looked up on the seam's own enum — a name this enum does not
#: carry is CANNOT_MEASURE, not a silent skip.
PROBE_SEQUENCE: tuple[tuple[str, str | None], ...] = (
    ("UP", None),
    ("DOWN", "transport disconnected"),
    ("DOWN", "requested"),
)
DOWN_MEMBER = "DOWN"
#: §2A defines `on_session` as connectivity TRANSITIONS, so the sequence above
#: is exactly ONE down edge. Two is D3.485's dead guard.
EXPECTED_DOWN_EVENTS = 1

#: Module-name roots purged before and after the import window. Named rather
#: than pattern-matched because a `__file__` sweep would also catch `nixverify`,
#: which this gate is itself running inside.
PURGE_ROOTS = (
    BROKER_PKG,
    SEAM_FLAT,
    ADAPTER_STEM,
    "broker_order_config",
    LIMITER_MODULE,
    "nixrisk",
    "nixsentinel",
    "risk_config",
)

#: Bases that contribute typing machinery rather than contract members.
_MACHINERY = (object, Protocol, Generic)
_MISSING = object()

Finding = tuple[str, str]


class Loaded(NamedTuple):
    """The tree under measurement, imported under the double-load path shape."""

    limiter: ModuleType
    flat_seam: ModuleType
    pkg_seam: ModuleType


class Measured(NamedTuple):
    """What was actually compared. Reported in `evidence` on EVERY run."""

    types_compared: int
    verbs_checked: int
    constructed: bool
    session_events: int
    down_events: int
    dial_attempts: tuple[str, ...]


class Guard(NamedTuple):
    """ARM 2's return, as ONE value rather than four loose ones."""

    findings: list[Finding]
    unmeasurable: list[Finding]
    sessions: int
    downs: int


class Wiring(NamedTuple):
    """ARM 3 + ARM 4's return, as one value rather than five loose ones."""

    findings: list[Finding]
    unmeasurable: list[Finding]
    port: Any
    attempts: tuple[str, ...]
    verbs_checked: int


# THE IMPORT WINDOW — the interpreter is left exactly as it was found


def _is_target(name: str) -> bool:
    """STEP of `_tree_imported`, NOT A SECOND GATE. Is this module ours to purge?"""
    return any(name == root or name.startswith(f"{root}.") for root in PURGE_ROOTS)


def _purge() -> dict[str, ModuleType]:
    """STEP of `_tree_imported`, NOT A SECOND GATE. Remove and return our modules."""
    saved: dict[str, ModuleType] = {}
    for name in [key for key in sys.modules if _is_target(key)]:
        saved[name] = sys.modules.pop(name)
    return saved


@contextlib.contextmanager
def _tree_imported(home: Path) -> Iterator[None]:
    """Put `home`'s tree on `sys.path` under the DOUBLE-LOAD shape, then undo it.

    Both `<home>/scripts` and `<home>/scripts/broker` go on the path: that is the
    shape that used to give one seam file two module objects (D3.485), so it is
    the shape ARM 1 must measure under. `limiterd.py` ALSO inserts the broker dir
    itself at import, which is a second reason every entry is restored from a
    saved copy rather than popped by count.
    """
    saved_path = list(sys.path)
    saved_modules = _purge()
    for rel in PACKAGE_DIRS:
        sys.path.insert(0, str((home / rel).resolve()))
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for name in [key for key in sys.modules if _is_target(key)]:
            del sys.modules[name]
        sys.modules.update(saved_modules)


def import_tree() -> tuple[Loaded | None, str]:
    """Import the Limiter FIRST — it is the production entrypoint — then the seam.

    The order is the PRODUCTION order and it is load-bearing: `limiterd.py` puts
    `<home>/scripts/broker` on the path and pulls the adapter in, and the
    adapter's canonical-seam preamble registers both spellings. Asking for
    `broker.broker_seam` afterwards is the real question: *does a consumer that
    picks the OTHER spelling get the same module object?*
    """
    try:
        limiter = importlib.import_module(LIMITER_MODULE)
        pkg_seam = importlib.import_module(SEAM_PKG)
        flat_seam = importlib.import_module(SEAM_FLAT)
        return Loaded(limiter=limiter, flat_seam=flat_seam, pkg_seam=pkg_seam), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{LIMITER_FILE}: cannot import {LIMITER_MODULE}/{SEAM_PKG}/"
            f"{SEAM_FLAT} — {type(exc).__name__}: {exc}. The subject is "
            "unavailable, so nothing was measured (§17 / check-rule 10: never "
            "a PASS)"
        )


# DERIVATIONS — nothing below is a list this gate typed (D3.426, Part C rule 4)


def seam_types(module: ModuleType) -> tuple[str, ...]:
    """The §2A seam's public TYPES, derived BY SHAPE from the module itself.

    Every public name the seam module binds to a class it DEFINES (`__module__`
    is the module's own name, so re-exports of someone else's class are not
    claimed). That derivation carries the enums whose identity the seam's `is`
    comparisons rest on — `SessionState`, `Side`, `OrderType`, `RejectCategory`,
    `AckStatus`, `TimeInForce` — without this file naming any of them, which is
    the whole point: a seam that grows a type gets it compared for free, and a
    gate holding a list would not.
    """
    own = module.__name__
    return tuple(
        sorted(
            name
            for name, obj in vars(module).items()
            if not name.startswith("_")
            and isinstance(obj, type)
            and getattr(obj, "__module__", "") == own
        )
    )


def declared_members(proto: type) -> frozenset[str]:
    """The PUBLIC members a Protocol actually declares — BY INTROSPECTION.

    Walks the Protocol's own MRO, skipping the typing machinery, and unions each
    class's `__dict__` and `__annotations__`. Deliberately NOT
    `__protocol_attrs__`: that set is frozen when the class object is created, so
    a member attached afterwards is invisible to it.
    """
    names: set[str] = set()
    for klass in proto.__mro__:
        if klass in _MACHINERY:
            continue
        names |= {name for name in vars(klass) if not name.startswith("_")}
        names |= {
            name
            for name in getattr(klass, "__annotations__", {})
            if not name.startswith("_")
        }
    return frozenset(names)


def port_verbs(seam: ModuleType) -> tuple[str, ...]:
    """Every verb `BrokerOrderPort` carries — roster UNION Protocol members.

    Two independent places in the seam's source, unioned rather than one trusted:
    a verb the roster names and the Protocol forgot, or the reverse, is still a
    verb an adapter has to satisfy, and this gate is not the instrument that
    adjudicates which of the two is right (that is `check_broker_seam_identity`).
    """
    roster = frozenset(getattr(seam, VERB_ROSTER, ()) or ())
    proto = getattr(seam, PORT_PROTOCOL, None)
    members = declared_members(proto) if isinstance(proto, type) else frozenset()
    return tuple(sorted(roster | members))


# ARM 1 — ONE SEAM MODULE OBJECT, ONE CLASS OBJECT PER SEAM TYPE


def arm_one_seam(loaded: Loaded) -> list[Finding]:
    """STEP of `collect`, NOT A SECOND GATE. One file, one module object."""
    if loaded.flat_seam is loaded.pkg_seam:
        return []
    return [
        (
            f"{ADAPTER_FILE}:_canonicalise_seam",
            (
                f"DOUBLE-LOADED SEAM (D3.485): sys.modules[{SEAM_FLAT!r}] and "
                f"sys.modules[{SEAM_PKG!r}] are TWO DISTINCT module objects "
                f"(id {id(loaded.flat_seam):#x} vs {id(loaded.pkg_seam):#x}) for "
                f"the ONE file {SEAM_FILE}. Every `is` comparison across the "
                "seam — sides, order types, reject categories, session states — "
                "then fails OPEN with no exception and no log line"
            ),
        )
    ]


def arm_type_identity(loaded: Loaded) -> tuple[list[Finding], list[Finding], int]:
    """(findings, unmeasurable, compared). Every seam TYPE is ONE class object."""
    names = seam_types(loaded.flat_seam)
    if not names:
        return (
            [],
            [
                (
                    f"{SEAM_FILE}:seam_types",
                    (
                        "VACUOUS: the by-shape derivation found NO public classes "
                        f"defined by {SEAM_FLAT} — every identity comparison below "
                        "would run zero times and agree about nothing (debug.md "
                        "§7.12 condition A). The derivation is broken, not the seam"
                    ),
                )
            ],
            0,
        )
    split: list[str] = []
    absent: list[str] = []
    compared = 0
    for name in names:
        other = getattr(loaded.pkg_seam, name, _MISSING)
        if other is _MISSING:
            absent.append(name)
            continue
        compared += 1
        if getattr(loaded.flat_seam, name) is not other:
            split.append(name)
    return _type_findings(split, absent), [], compared


def _site(names: list[str]) -> str:
    """STEP of `_type_findings`, NOT A SECOND GATE. A `site` a reader can scan.

    A split load splits EVERY seam type, so `site` is abbreviated while `detail`
    names every one: the site field is where a reader looks first, and fifty
    names there is unreadable rather than precise.
    """
    head = ",".join(names[:3])
    return f"{SEAM_FILE}:{head}" + (f"+{len(names) - 3} more" if len(names) > 3 else "")


def _type_findings(split: list[str], absent: list[str]) -> list[Finding]:
    """STEP of `arm_type_identity`, NOT A SECOND GATE. Renders what it found."""
    findings: list[Finding] = []
    if split:
        findings.append(
            (
                _site(split),
                (
                    f"SPLIT SEAM TYPES ({len(split)}): {', '.join(split)} — each is "
                    f"TWO class objects, one under {SEAM_FLAT!r} and one under "
                    f"{SEAM_PKG!r}. `{SESSION_ENUM}.{DOWN_MEMBER} is "
                    f"{SESSION_ENUM}.{DOWN_MEMBER}` is FALSE across that split, "
                    "which is D3.485's dead identity guard"
                ),
            )
        )
    if absent:
        findings.append(
            (
                _site(absent),
                (
                    f"ASYMMETRIC SEAM ({len(absent)}): {', '.join(absent)} are "
                    f"defined under {SEAM_FLAT!r} but absent from {SEAM_PKG!r} — "
                    "the two spellings do not even carry the same names"
                ),
            )
        )
    return findings


# ARM 2 — THE IDENTITY GUARD, DRIVEN. Part C rule 1: not `is`, the EVENT COUNT.


class RecordingSink:  # pylint: disable=too-few-public-methods
    """A §2A sink that RECORDS every event. The probe ARM 2 reads its verdict from.

    `__getattr__` rather than seven spelled methods: the event roster is the
    seam's to define, and a probe that named them would be the hardcoded list
    §7.12 answer 3 forbids one layer down. Anything the adapter pushes is
    recorded under the name it was pushed as.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> None:
            self.events.append((name, args, kwargs))

        return record


def _probe_states(session_enum: type) -> tuple[list[Any], list[Finding]]:
    """STEP of `arm_guard_fires`, NOT A SECOND GATE. Resolve the probe's members."""
    states: list[Any] = []
    unmeasurable: list[Finding] = []
    for member, reason in PROBE_SEQUENCE:
        value = getattr(session_enum, member, _MISSING)
        if value is _MISSING:
            unmeasurable.append(
                (
                    f"{SEAM_FILE}:{SESSION_ENUM}.{member}",
                    (
                        f"{SESSION_ENUM} carries no member {member!r}, so the ARC "
                        "016 teardown sequence cannot be driven and the identity "
                        "guard was NOT exercised (§17)"
                    ),
                )
            )
            continue
        states.append((value, reason))
    return states, unmeasurable


def arm_guard_fires(klass: type | None, session_enum: Any) -> Guard:
    """DRIVE the guard, and read the verdict AT THE SINK.

    Constructs the REAL adapter with a recording sink, sets `_connected` as the
    real lifecycle does, and pushes the ARC 016 sequence through
    `_publish_session` USING THE PACKAGE-SPELLING ENUM. Under one seam module
    object §2A's transition rule collapses the second DOWN and exactly ONE
    `on_session(DOWN)` reaches the sink; under the D3.485 double load the
    `state is SessionState.DOWN` comparison is False, the rule cannot fire, and
    TWO arrive.
    """
    if klass is None or not isinstance(session_enum, type):
        return Guard([], [_no_probe_subject(klass)], 0, 0)
    states, unmeasurable = _probe_states(session_enum)
    if unmeasurable:
        return Guard([], unmeasurable, 0, 0)
    sink = RecordingSink()
    try:
        adapter = klass(sink=sink, ib=None)
        adapter._connected = True  # pylint: disable=protected-access
        for state, reason in states:
            adapter._publish_session(state, reason)  # pylint: disable=protected-access
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return Guard([], [_probe_raised(exc)], 0, 0)
    return _guard_findings(sink)


def _no_probe_subject(klass: type | None) -> Finding:
    """STEP of `arm_guard_fires`, NOT A SECOND GATE. Name the absent subject."""
    what = (
        f"{LIMITER_FILE} does not hold the adapter class {ADAPTER_CLASS}"
        if klass is None
        else f"{SEAM_PKG} does not carry the enum {SESSION_ENUM}"
    )
    return (
        f"{LIMITER_FILE}:{ADAPTER_CLASS}",
        (
            f"{what} — the identity guard could not be DRIVEN, so ARM 2 proved "
            "nothing. A guard not exercised is not a guard shown to fire (§17)"
        ),
    )


def _probe_raised(exc: BaseException) -> Finding:
    """STEP of `arm_guard_fires`, NOT A SECOND GATE. A probe that could not run."""
    return (
        f"{ADAPTER_FILE}:_publish_session",
        (
            f"driving the ARC 016 teardown sequence raised {type(exc).__name__}: "
            f"{exc} — the identity guard was NOT exercised, so ARM 2 measured "
            "nothing (§17 / check-rule 10: never a PASS)"
        ),
    )


def _guard_findings(sink: RecordingSink) -> Guard:
    """STEP of `arm_guard_fires`, NOT A SECOND GATE. Count what reached the sink."""
    sessions = [item for item in sink.events if item[0] == "on_session"]
    downs = [
        item
        for item in sessions
        if item[1] and getattr(item[1][0], "name", None) == DOWN_MEMBER
    ]
    if len(downs) == EXPECTED_DOWN_EVENTS:
        return Guard([], [], len(sessions), len(downs))
    reasons = [
        item[2].get("reason", item[1][1] if len(item[1]) > 1 else None)
        for item in downs
    ]
    return Guard(
        [
            (
                f"{ADAPTER_FILE}:_publish_session",
                (
                    f"DEAD IDENTITY GUARD: the ARC 016 teardown sequence emitted "
                    f"{len(downs)} on_session({DOWN_MEMBER}) events (reasons "
                    f"{reasons!r}) where §2A's transition rule permits exactly "
                    f"{EXPECTED_DOWN_EVENTS}. `state is {SESSION_ENUM}.{DOWN_MEMBER}` "
                    "did not hold for an enum member that IS that state — the "
                    "seam is double-loaded and the guard fails OPEN (D3.485/D1.17)"
                ),
            )
        ],
        [],
        len(sessions),
        len(downs),
    )


# ARM 4(b) — THE VENUE SENTINEL. Nothing is dialled; every dial is REFUSED.


@contextlib.contextmanager
def _socket_sentinel(attempts: list[str]) -> Iterator[None]:
    """Intercept and REFUSE every socket dial, recording the address reached for.

    Refused, not merely observed: this gate must never open a connection to prove
    one was attempted, and `ECONNREFUSED` is a failure the caller already has to
    handle. Both methods are restored in a `finally`, including the usual case
    where `socket.socket` never carried them in its own `__dict__` (they are
    inherited from `_socket.socket`, so the restore is a `delattr`).
    """
    saved = {
        verb: socket.socket.__dict__.get(verb, _MISSING)
        for verb in ("connect", "connect_ex")
    }

    def guard(verb: str) -> Any:
        def dial(_self: Any, address: Any, *_args: Any, **_kwargs: Any) -> Any:
            attempts.append(f"socket.socket.{verb}({address!r})")
            raise OSError(errno.ECONNREFUSED, f"{NAME}: venue dial refused by the gate")

        return dial

    for verb in saved:
        setattr(socket.socket, verb, guard(verb))
    try:
        yield
    finally:
        for verb, original in saved.items():
            if original is _MISSING:
                delattr(socket.socket, verb)
            else:
                setattr(socket.socket, verb, original)


def construct(limiter: ModuleType) -> tuple[Any, tuple[str, ...], str]:
    """(port, dial attempts, error). CALL the production construction site.

    The call, not its existence: Part C rule 1 forbids proving a property by
    import success, and "`limiterd` defines a function named
    `construct_broker_order_port`" is exactly that proxy.
    """
    factory = getattr(limiter, CONSTRUCTOR, None)
    if not callable(factory):
        return (
            None,
            (),
            (
                f"NO CONSTRUCTION SITE: {LIMITER_FILE} exposes no callable "
                f"{CONSTRUCTOR}() — nothing in the process that owns the Limiter "
                "constructs an adapter behind §2A's port (B12-1)"
            ),
        )
    attempts: list[str] = []
    try:
        with _socket_sentinel(attempts):
            built = factory()
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            None,
            tuple(attempts),
            (
                f"{CONSTRUCTOR}() raised {type(exc).__name__}: {exc} — the "
                "construction site exists but does not produce an adapter"
            ),
        )
    port = built[0] if isinstance(built, tuple) and built else built
    if port is None:
        return (
            None,
            tuple(attempts),
            (
                f"NO ADAPTER BEHIND THE PORT: {CONSTRUCTOR}() returned "
                f"{built!r} — the construction site exists and produces NOTHING, "
                "which is B12-1's defect wearing the shape of a call that worked"
            ),
        )
    return port, tuple(attempts), ""


# ARM 3 — THE CONSTRUCTED OBJECT IS THE REAL ADAPTER, AND IT IS THE PORT


def _real_adapter_findings(port: Any, klass: type | None, home: Path) -> list[Finding]:
    """STEP of `arm_construction`, NOT A SECOND GATE. A stub cannot satisfy this."""
    findings: list[Finding] = []
    built = type(port)
    if klass is not None and built is not klass:
        findings.append(
            (
                f"{LIMITER_FILE}:{CONSTRUCTOR}",
                (
                    f"WRONG CLASS: {CONSTRUCTOR}() returned a "
                    f"{built.__module__}.{built.__name__}, which is NOT the "
                    f"{ADAPTER_CLASS} the Limiter itself imported — a stand-in "
                    "satisfies the port by construction (§7.12 answer 5)"
                ),
            )
        )
    origin = getattr(sys.modules.get(built.__module__), "__file__", "") or ""
    expected = (home / "scripts" / BROKER_PKG).resolve()
    if not origin or Path(origin).resolve().parent != expected:
        findings.append(
            (
                f"{LIMITER_FILE}:{CONSTRUCTOR}",
                (
                    f"OUT-OF-TREE ADAPTER: {built.__name__} is defined in "
                    f"{origin or '<unknown>'}, not inside {expected} — the gate "
                    "cannot show the construction site built the adapter from the "
                    "tree it was pointed at (§17)"
                ),
            )
        )
    return findings


def _port_findings(
    port: Any, seam: ModuleType, verbs: tuple[str, ...]
) -> list[Finding]:
    """STEP of `arm_construction`, NOT A SECOND GATE. Every DERIVED verb, checked."""
    findings: list[Finding] = []
    proto = getattr(seam, PORT_PROTOCOL, None)
    if isinstance(proto, type) and not isinstance(port, proto):
        findings.append(
            (
                f"{LIMITER_FILE}:{CONSTRUCTOR}",
                (
                    f"NOT A {PORT_PROTOCOL}: the object behind the port fails "
                    f"isinstance({PORT_PROTOCOL}) — the Limiter holds something "
                    "that does not satisfy §2A's broker-order port"
                ),
            )
        )
    for verb in verbs:
        attr = getattr(port, verb, None)
        if not callable(attr):
            findings.append(
                (
                    f"{ADAPTER_FILE}:{type(port).__name__}.{verb}",
                    (
                        f"UNSATISFIED VERB {verb!r}: {PORT_PROTOCOL} carries it and "
                        f"the constructed adapter does not — "
                        f"{type(port).__name__}.{verb} is "
                        f"{type(attr).__name__ if attr is not None else 'absent'}. "
                        "A caller written against the port cannot call this adapter"
                    ),
                )
            )
    return findings


def arm_no_connect(
    port: Any, attempts: tuple[str, ...], real: bool
) -> tuple[list[Finding], list[Finding]]:
    """(findings, unmeasurable). ARM 4: constructed, never connected — BOTH ways.

    `real` is ARM 3's verdict that the constructed object IS the adapter class
    the Limiter holds. The structural half reads that adapter's own documented
    guarantee (`_ib`: *"injected; None means caller must supply before
    connect()"*), which a stand-in does not carry — so on a stand-in only the
    behavioural half runs and ARM 3's WRONG CLASS finding stands as the verdict,
    rather than being withheld over an attribute that was never the subject.
    """
    findings: list[Finding] = []
    unmeasurable: list[Finding] = []
    if attempts:
        findings.append(
            (
                f"{LIMITER_FILE}:{CONSTRUCTOR}",
                (
                    f"LIVE CONNECT ON THE CONSTRUCTION PATH: {len(attempts)} socket "
                    f"dial(s) attempted during {CONSTRUCTOR}() — {'; '.join(attempts)}. "
                    "Construction must never reach a venue: B12-1 constructs, B12-2 "
                    "wires, and the live cutover is M2-F"
                ),
            )
        )
    if port is None or not real:
        return findings, unmeasurable
    client = getattr(port, "_ib", _MISSING)
    if client is _MISSING:
        unmeasurable.append(
            (
                f"{ADAPTER_FILE}:{type(port).__name__}._ib",
                (
                    "the constructed adapter exposes no `_ib` attribute, so the "
                    "STRUCTURAL half of the no-connect property (the adapter's own "
                    "'injected; None means caller must supply before connect()') "
                    "could not be read (§17)"
                ),
            )
        )
    elif client is not None:
        findings.append(
            (
                f"{LIMITER_FILE}:{CONSTRUCTOR}",
                (
                    f"CLIENT INJECTED AT CONSTRUCTION: the adapter's `_ib` is a "
                    f"{type(client).__name__}, not None — the process holds an "
                    "adapter that HAS something to dial with, and the no-connect "
                    "guarantee stops being structural"
                ),
            )
        )
    return findings, unmeasurable


def _wiring_arms(loaded: Loaded, home: Path, klass: type | None) -> Wiring:
    """STEP of `collect`, NOT A SECOND GATE. ARM 3 + ARM 4, over ONE construction.

    One call, not two: the construction path is both arms' subject, and calling
    it twice would let a site that dialled only on its first call read as clean.
    Split out of `collect` because that function crossed pylint's local-variable
    ceiling, and raising a ceiling is doctrine B.4's forbidden direction.
    """
    port, attempts, error = construct(loaded.limiter)
    findings: list[Finding] = []
    if error:
        findings.append((f"{LIMITER_FILE}:{CONSTRUCTOR}", error))
    verbs = port_verbs(loaded.flat_seam)
    subject = port if port is not None else klass
    if verbs and subject is not None:
        findings += _port_findings(subject, loaded.flat_seam, verbs)
    # `type(port) is klass`, deliberately NOT isinstance: the property is that the
    # construction site built THE adapter class the Limiter holds, and a subclass
    # is exactly the stand-in §7.12 answer 5 exists to refuse.
    real = (
        port is not None and klass is not None and type(port) is klass  # pylint: disable=unidiomatic-typecheck
    )
    if port is not None:
        findings += _real_adapter_findings(port, klass, home)
    connect_findings, unmeasurable = arm_no_connect(port, attempts, real)
    return Wiring(
        findings=findings + connect_findings,
        unmeasurable=unmeasurable,
        port=port,
        attempts=attempts,
        verbs_checked=len(verbs) if subject is not None else 0,
    )


def collect(
    loaded: Loaded, home: Path
) -> tuple[list[Finding], list[Finding], Measured]:
    """Run all four arms. Returns (findings, unmeasurable, what was measured)."""
    findings = arm_one_seam(loaded)
    type_findings, unmeasurable, compared = arm_type_identity(loaded)
    findings += type_findings

    held = getattr(loaded.limiter, ADAPTER_CLASS, None)
    klass = held if isinstance(held, type) else None
    guard = arm_guard_fires(klass, getattr(loaded.pkg_seam, SESSION_ENUM, None))
    wiring = _wiring_arms(loaded, home, klass)

    measured = Measured(
        types_compared=compared,
        verbs_checked=wiring.verbs_checked,
        constructed=wiring.port is not None,
        session_events=guard.sessions,
        down_events=guard.downs,
        dial_attempts=wiring.attempts,
    )
    return (
        findings + guard.findings + wiring.findings,
        unmeasurable + guard.unmeasurable + wiring.unmeasurable,
        measured,
    )


def _vacuity(measured: Measured) -> list[Finding]:
    """Rule 3, restated as a refusal: a run that compared nothing is not a PASS."""
    holes: list[Finding] = []
    if measured.verbs_checked == 0:
        holes.append(
            (
                f"{SEAM_FILE}:{VERB_ROSTER}",
                (
                    f"VACUOUS: ZERO port verbs were checked — {VERB_ROSTER} and "
                    f"{PORT_PROTOCOL}'s declared members are both empty, or there "
                    "was no adapter to check them against. Every verb comparison "
                    "ran zero times (debug.md §7.12 condition A)"
                ),
            )
        )
    if measured.session_events == 0:
        holes.append(
            (
                f"{ADAPTER_FILE}:_publish_session",
                (
                    "VACUOUS: the identity guard emitted NO session events at all, "
                    "so ARM 2 counted nothing. `is`-identity alone is a proxy; the "
                    "property is the guard FIRING (Part C rule 1)"
                ),
            )
        )
    return holes


def evidence(measured: Measured) -> str:
    """The non-vacuity record, present on EVERY run (Part C rule 3)."""
    return (
        f"B12-1: {measured.types_compared} §2A seam types compared for object "
        f"identity across {SEAM_FLAT!r} and {SEAM_PKG!r} (derived by shape, not "
        f"listed); {measured.verbs_checked} port verbs derived from {VERB_ROSTER} "
        f"+ {PORT_PROTOCOL} and checked against the adapter; "
        f"{CONSTRUCTOR}() really called (adapter constructed="
        f"{measured.constructed}); the identity guard really driven — "
        f"{measured.session_events} on_session event(s), {measured.down_events} of "
        f"them {DOWN_MEMBER} (§2A permits {EXPECTED_DOWN_EVENTS}); "
        f"{len(measured.dial_attempts)} socket dial(s) attempted on the "
        "construction path. EVENT WIRING IS OUT OF SCOPE (B12-2)"
    )


def verdict(
    findings: list[Finding], unmeasurable: list[Finding], measured: Measured
) -> CheckResult:
    """STEP of `run`, NOT A SECOND GATE — it renders, it does not measure.

    Cannot-measure withholds the verdict even when findings were also collected,
    and those findings are still NARRATED, so a CANNOT_MEASURE never silently
    swallows what was seen.
    """
    record = evidence(measured)
    if unmeasurable:
        detail = "; ".join(f"{site}: {why}" for site, why in unmeasurable)
        if findings:
            detail += "; ALSO (measured, but the verdict is unmeasurable): "
            detail += "; ".join(f"{site}: {why}" for site, why in findings)
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site="; ".join(site for site, _ in unmeasurable),
            evidence=record,
            detail=detail,
        )
    if findings:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in findings),
            evidence=record,
            detail="; ".join(f"{site}: {why}" for site, why in findings),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=record)


def measure(home: Path) -> CheckResult:
    """STEP of `run`, NOT A SECOND GATE. Everything inside the import window."""
    loaded, error = import_tree()
    if loaded is None:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITER_FILE,
            detail=error,
        )
    findings, unmeasurable, measured = collect(loaded, home)
    return verdict(findings, unmeasurable + _vacuity(measured), measured)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure B12-1: one seam, a real adapter, no venue. Never corrects."""
    try:
        for rel in SUBJECT_FILES:
            if not (ctx.nix_home / rel).is_file():
                return CheckResult(
                    name=NAME,
                    status=Status.CANNOT_MEASURE,
                    site=rel,
                    detail=f"{rel} is absent — there is no seam to span (§17)",
                )
        with _tree_imported(ctx.nix_home):
            return measure(ctx.nix_home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=SEAM_FILE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
