#!/usr/bin/env python3
# C0302: this module is over pylint's line ceiling and the excess is PROSE —
# the §7.12 standing question answered route by route, a rationale beside
# every arm, and the WHAT-THIS-CANNOT-PROVE section a green over §4's
# half-built recovery model requires. Doctrine B.7 puts the argument next to
# the instrument it argues for, and §4.2 requires a check be ONE
# independently-runnable artifact — splitting it to satisfy a line counter
# would move half the reasoning away from the code it explains.
# pylint: disable=too-many-lines
"""The Allocator REFLECTS §4's in-flight-closing state; a dying strategy gets no capital.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *capital
eligibility follows the PUBLISHED per-position lifecycle state — a strategy
whose rows enter an in-flight-closing state is refused new capital in a
contention pass, and becomes eligible again when its rows return to flat.*
Five arms serve that one property.

It is the instrument for `docs/nics_risk_subsystem_spec_v1.3.md` §4:281-286,
transcribed rather than paraphrased: *"The **transitional state is visible
too**: a strategy mid-recovery reads as **in-flight-closing**, NOT
normal-and-available, so it is never counted eligible for new capital while
dying. (This is why the published table carries per-position lifecycle state,
not just aggregates.)"*

  * **ARM 1 — the screened state is the SPEC'S, parsed at run time.** The
    hyphenated phrase is pulled out of §4's own sentence in the frozen document,
    required to fall inside §4's line span, and mapped onto `PositionState` BY
    VALUE. **No lifecycle state name enters this gate's executable code** — the
    can-fail suite asserts that over the AST — so ARM 1's reference side cannot
    be a transcription that drifted.

  * **ARM 2 — THE TRANSITION, and it is the arm that matters.** A gate in which
    no strategy is ever mid-recovery proves nothing: the refusing branch is dead
    code that looks identical to `return True`. So this arm DRIVES the
    transition on ONE moving snapshot sequence, through the REAL producer, the
    REAL wire and the REAL consumer — `nixrisk.picture.FinancialPictureBook` and
    `nixrisk.flatten.ProtectiveFlatten` publish; `nixbus.statebus` carries it
    over an `ipc://` socket; `nixalloc.mirror.AllocatorMirror` consumes it. The
    only stand-in is the BROKER, which is the one collaborator that provably
    cannot be real here. Three snapshots — open, in-flight-closing, flat — and
    the arm asserts the eligibility VALUE CHANGED at each step and changed BACK,
    that each step's published version really advanced, and that the middle
    step's picture really carries a closing row. A sequence whose eligibility
    never moves is reported as a discriminator failure, never a pass.

  * **ARM 3 — the CONTENTION pass refuses the dying, and names why.** The same
    three snapshots, screened through the shipped `contention.rank_eligible`
    with two contenders. The dying strategy arrives FIRST, so under §6.6:466's
    FCFS fallback it would head the ordering if the screen did nothing — the arm
    asserts it leads at step 1, is ABSENT at step 2 with a refusal naming the
    state and the trade, and leads again at step 3. The healthy contender must
    survive all three, because a screen that refuses everything would pass a
    test that only looked at the dying one.

  * **ARM 4 — FAIL CLOSED, in the three ways the screen can fail to answer.**
    A mirror that has never heard from the Limiter must refuse; a mirror that
    still HOLDS a picture past its freshness ceiling must ALSO refuse (§6.4's
    *never carry on with the last value* — the branch a `picture is None` guard
    misses entirely); and a lifecycle view that RAISES must refuse without the
    exception escaping onto the pass. The refusals are required to name
    DIFFERENT reasons: three refusals reaching one boolean are distinguishable
    only by what they say (§18).

  * **ARM 5 — the boundary, BY ATTEMPT and BY CENSUS (§2, §4:260-274).** The
    Allocator reflects recovery; it does not drive it. This arm reaches for
    every recovery-driving verb on the shipped lifecycle module and requires
    each reach to come back empty, requires the module to be free of coroutines,
    and then MEASURES the producer census: which modules in the tree actually
    construct a row in the screened state. No module under the Allocator's own
    package may be among them, and at least one outside it must be, or the
    transition arm is driving a state nothing produces.

`debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
MEASURING NOTHING? Seven routes, each closed by a mechanism rather than by care:

 1. **The modules could be missing or unimportable**, and every arm skipped.
    CLOSED: CANNOT_MEASURE naming the exception (§17), never a PASS. Every
    module is imported out of `ctx.nix_home` and each one's `__file__` is
    compared back, because `checks/_preamble.py` puts the REAL `scripts/` on
    `sys.path` permanently and a name-based import would measure the live tree
    whatever `ctx.nix_home` said (D3.124).
 2. **ARM 1's spec sentence could be renamed or moved**, leaving the regex
    matching nothing and an empty expected set comparing equal to an empty
    measured one. CLOSED: no match, or a match outside §4's own line span, is
    CANNOT_MEASURE naming the anchor.
 3. **ARM 2 could run on a sequence where nothing ever closes**, which is every
    fixture that does not drive a flatten. CLOSED: the arm requires the middle
    snapshot to carry at least `MIN_CLOSING_ROWS` row(s) in the screened state
    and requires the three published versions to be strictly increasing; either
    failing is reported as a discriminator failure rather than a pass.
 4. **ARM 2 could pass because eligibility is a CONSTANT.** A screen hard-wired
    to False refuses the dying strategy perfectly. CLOSED: the arm asserts the
    value at each step and requires the sequence True → False → True, so a
    constant of either polarity fails.
 5. **The bus could deliver nothing** and every step read the same stale mirror.
    CLOSED: each step waits for its own published version to arrive within a
    bounded budget, and a version that never lands is CANNOT_MEASURE naming the
    endpoint — never a PASS over an unmoved mirror (§17).
 6. **An arm could be skipped by an earlier arm's exception**, leaving a green
    over four. CLOSED: the arms run unconditionally, each returns its own
    findings, and an arm that raises becomes a finding naming itself.
 7. **ARM 5's census could match nothing** — a scan whose pattern never hits
    reports "no Allocator-side producers" and passes. CLOSED: the census must
    find at least `MIN_PRODUCERS` producer outside the Allocator package, or the
    arm reports that it cannot discriminate.

WHAT THIS GATE CANNOT PROVE, stated rather than implied, because §4's recovery
half is unbuilt and a green here must not read as coverage of it:

  * **It cannot prove anything about strategy-death recovery.** Heartbeat
    detection, the one-cycle wait, flatten-on-death, force-deregister,
    kill+relaunch, the crash-loop cap and quarantine (§4:260-274) were ARC R5
    (§12B:878-880) and absent when this gate was written; ARC 034 built them at
    `scripts/nixrisk/recovery.py` and `scripts/nixrisk/supervision.py` (§12.2:616
    -618's R4 breaker). **They are still not this gate's subject**:
    `checks/check_orphan_recovery.py` and `checks/check_supervision.py` own them,
    and doctrine C.9 forbids a second instrument here. This gate proves the
    Allocator REFLECTS a published state correctly. The module states who
    produces that state in `lifecycle.RECOVERY_PRODUCER`, which this gate READS
    and prints rather than restating.
  * **It cannot prove score persistence across death** (§4:275-280). That is the
    Scoring process's, §6.6:457-461 makes it the sole writer of the ranking
    table, and it is R5. Nothing here persists, archives or computes a score;
    `lifecycle.SCORE_BOUNDARY` says so and is printed on every run.
  * **It cannot prove the screen runs on a live order path.** No Allocator
    process exists. Every arm calls the modules directly.
  * **It cannot prove the transport** — `check_state_bus` owns the bus and
    `check_allocator_mirror` owns the consumer. The socket is here so the
    transition's INPUT is produced rather than manufactured, not to re-measure
    either of them (doctrine C.9).
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# §4.2 requires each checks/check_*.py be independently runnable and map status
# -> exit code identically, and doctrine B.2 requires the crash path return
# CANNOT_MEASURE in both. Those blocks are MANDATED to be the same text, as is
# the import-out-of-home / provenance block this gate shares with
# check_allocator_mirror -- factoring it into a shared helper would make one
# gate's ability to read its own subject depend on another gate's bytes.
#
# pylint: disable=too-few-public-methods,missing-class-docstring
# pylint: disable=missing-function-docstring
# The broker and fan-out stand-ins below are one-verb doubles for §4's frozen
# collaborator ports. Each class's NAME states what it stands in for; a
# docstring restating the name is noise.

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
#: `pyzmq` is a `checks/pinned_deps.json` pin and ARM 2 drives a real `ipc://`
#: endpoint, so the venv is what makes this gate's transition arm runnable.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: FOUR claims, declared against what this gate really touches:
#: * `file-write:/tmp` — `tempfile.mkdtemp` for the bus root, plus
#:   `_remove_tree`'s ABSOLUTE-path unlinks. `shutil.rmtree` is deliberately not
#:   used: on POSIX it unlinks with a BARE RELATIVE name through a directory fd,
#:   which the audit hook records with no directory attached and no path-rooted
#:   declaration can account for (measured ARC 026, `check_state_bus`).
#: * `zmq-ipc` — the AF_UNIX sockets libzmq binds and connects. NOT observable
#:   by `check_observed_resource_claims` (libzmq calls `bind(2)` from C), so the
#:   observer will report no socket and be wrong in the permissive direction.
#:   Declared anyway: the claim is real and the PLAN is what needs to know.
#: * `interpreter:sys.modules` / `interpreter:sys.path` — `load()` purges and
#:   restores the first-party package namespaces so the gate reads the tree it
#:   was GIVEN rather than the live repository.
#: `subprocess:*` is deliberately ABSENT: this gate spawns nothing.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "zmq-ipc",
)
TIME_BOUND = True
#: Three published versions over one socket, each with a bounded settle budget,
#: plus four in-process arms. Measured at ~0.8 s on the MS-01; the headroom is
#: for a loaded box, not for a budget nobody checked.
EXPECTED_S = 4.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is the frozen risk spec -- §4:284-286's locked sentence "
    "-- and the measured side is a transition driven through the shipped "
    "producer, wire and consumer. There is no edit an instrument could make to "
    "either side that would not be manufacturing its own green: correcting the "
    "spec is forbidden outright, and correcting the modules is writing the "
    "implementation the gate exists to judge"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixalloc/lifecycle.py",
    "scripts/nixalloc/contention.py",
)

NAME = "check_allocator_lifecycle"

LIFECYCLE = "scripts/nixalloc/lifecycle.py"
CONTENTION = "scripts/nixalloc/contention.py"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"
#: The package that must never PRODUCE the state it screens on (§2, ARM 5).
ALLOCATOR_PACKAGE = "scripts/nixalloc/"
#: Excluded from the ARM 5 census: a test is not a production writer, it IS the
#: measurement — the same line `check_artifact_gate_coverage` draws.
CENSUS_SKIP = "scripts/tests/"

#: §4's own sentence, anchored on the bolded hyphenated phrase so a renamed or
#: moved sentence is a loud CANNOT_MEASURE rather than an empty expected set
#: silently agreeing with an empty measured one (§7.12/2). The state NAME is the
#: capture group; it is never spelled in this gate.
_SCREENED_PHRASE = re.compile(r"\*\*in-flight-(?P<state>[a-z]+)\*\*")
#: A numbered markdown heading, for deriving the cited section's line span.
_HEADING = re.compile(r"^##\s+(?P<label>[0-9]+[A-Za-z]?)\.\s")
#: The section §4:284-286 lives in. A LABEL, not a coordinate: the coordinate is
#: derived from the document at run time and printed in the evidence.
_SECTION = "4"

#: Non-vacuity floors, each anchored BELOW today's figure on purpose: a
#: threshold equal to the current count is a moving anchor (`debug.md` §7.4).
MIN_CLOSING_ROWS = 1
MIN_PRODUCERS = 1
MIN_STEPS = 3

#: Socket budgets. Generous enough that ipc setup is not a race, bounded enough
#: that exhausting one is a finding rather than a hang. `service(0)` and NOT a
#: long budget: `StatePublisher.service` sits for its full timeout when no
#: subscription is pending, which is the steady state after the first step —
#: paying that on every step turned a sub-second settle into three seconds, and
#: three seconds times a can-fail suite is a gate nobody runs.
SERVICE_MS = 0
DRAIN_MS = 100
SETTLE_ATTEMPTS = 60
#: Freshness ceiling for the driven mirror. Explicit: the class takes no default.
MAX_AGE_S = 60.0

#: The two strategies the transition is driven with. Arbitrary labels for a
#: race; nothing about a lifecycle state or a bucket is read from them. The
#: DYING one arrives FIRST so that under §6.6:466's FCFS fallback it would head
#: the ordering if the screen did nothing.
DYING = "strat-dying"
HEALTHY = "strat-healthy"
SYMBOL = "MESU6"
BALANCE = 100_000.0
MARGIN_PER_CONTRACT = 1_000.0
SIZE = 2
TRADE_ID = "T-transition-1"
#: ARC 032 / SPEC-A9: the published row's stop distance in ticks. Positive so
#: §7's correlation cap could price this row if it ever saw it — this gate is
#: about §4's screen, and a zero would make every fixture here simultaneously a
#: D3.136 fail-open case, which is a second subject in one gate (§5.5).
STOP_DISTANCE_TICKS = 20

#: Recovery verbs whose presence on the Allocator's lifecycle module would be it
#: DRIVING recovery rather than reflecting it. §4:260-274 gives every one of
#: them to the Limiter and the supervisor; §2 makes the Allocator permissive.
#: The can-fail suite plants each in turn and requires a finding naming it.
_DRIVING_VERBS = (
    "flatten",
    "deregister",
    "kill",
    "relaunch",
    "quarantine",
    "heartbeat",
    "restart",
    "supervise",
    "crash",
    "archive",
    "persist",
    "respawn",
)

#: Imported out of the tree under test: `(attribute, dotted name, path it must
#: resolve to)`. The attribute is spelled rather than derived from the dotted
#: name's last component, because `nixalloc.seam` and `nixrisk.seam` share one —
#: a derived key would silently keep whichever imported last and every arm would
#: then read a module it did not ask for.
_MODULES = (
    ("alloc_seam", "nixalloc.seam", "scripts/nixalloc/seam.py"),
    ("lifecycle", "nixalloc.lifecycle", LIFECYCLE),
    ("contention", "nixalloc.contention", CONTENTION),
    ("mirror", "nixalloc.mirror", "scripts/nixalloc/mirror.py"),
    ("risk_seam", "nixrisk.seam", "scripts/nixrisk/seam.py"),
    ("picture", "nixrisk.picture", "scripts/nixrisk/picture.py"),
    ("flatten", "nixrisk.flatten", "scripts/nixrisk/flatten.py"),
    ("reservations", "nixrisk.reservations", "scripts/nixrisk/reservations.py"),
    ("statebus", "nixbus.statebus", "scripts/nixbus/statebus.py"),
)
_PACKAGES = ("nixalloc", "nixrisk", "nixbus", "risk_config")

#: §3:169's uncertainty trigger — *"a flatten sent to be safe with no known
#: trade"*. Chosen because it is the trigger §4's reconcile path is written
#: against and it is not one of the R4 triggers `fire()` refuses outright.
_TRIGGER = "UNCERTAINTY"


class Finding(NamedTuple):
    """One divergence. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


@dataclass(frozen=True)
class Driven:
    """Everything an arm needs, imported out of the tree under test."""

    modules: dict[str, ModuleType]
    home: Path

    def __getattr__(self, name: str) -> ModuleType:
        """`driven.lifecycle` -> the module loaded out of `home`, never by name."""
        try:
            return self.modules[name]
        except KeyError as exc:  # pragma: no cover - programming error only
            raise AttributeError(name) from exc


# ---------------------------------------------------------------------------
# The stand-ins. The BROKER is the one collaborator that provably cannot be
# real here: there is no venue, and §4's reconcile is defined against broker
# truth. Everything else on the transition path is the shipped code.
# ---------------------------------------------------------------------------


@dataclass
class _Position:
    symbol: str
    net_qty: int
    avg_price: float = 100.0


@dataclass
class _Balance:
    cash: float
    net_liquidation: float
    maint_margin: float = 0.0
    init_margin: float = 0.0
    venue_seq_ts: float = 0.0


class _HaltedMarketBroker:
    """A `BrokerFlattenPort` whose flatten does NOT clear the position.

    §4's market-tradable guard and §12.6: a flatten fired into a halted market
    leaves the position held, which is exactly the case
    `nixrisk.flatten._confirmed_rows` republishes as in-flight-closing. Setting
    `holds` to False afterwards is the market re-opening and the flatten
    landing — the second half of the transition.
    """

    def __init__(self) -> None:
        self.holds = True
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)

    async def query_positions(self) -> list[_Position]:
        return [_Position(SYMBOL, SIZE)] if self.holds else []

    async def query_balance(self) -> _Balance:
        return _Balance(cash=BALANCE, net_liquidation=BALANCE)


@dataclass
class _StrategySink:
    # `notified` and not `closed`: the can-fail suite asserts by AST that no
    # published lifecycle state value is spelled as an identifier anywhere in
    # this gate, and a field named for one would make the reference side look
    # transcribed even where it is parsed out of the frozen document.
    notified: list[tuple[str, str, str, bool]] = field(default_factory=list)

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.notified.append((trade_id, strategy_id, reason, hard_reset))


@dataclass
class _ScoringSink:
    """§4 fan-out (d). Records the hand-off; the EMA math is R5 and absent."""

    booked: list[tuple[tuple[str, ...], float]] = field(default_factory=list)

    def book_realized(
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        del confirmed_balance, ts
        self.booked.append((closed_trades, realized_delta))


class _Plane1:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return len(self.rows)


class _SilentFeed:
    """A `SnapshotFeedPort` that never heard anything. ARM 4's EMPTY mirror."""

    def __init__(self, update: Any) -> None:
        self._update = update

    def read(self, timeout_ms: int) -> Any:
        del timeout_ms
        return self._update


class _RaisingView:
    """A `LifecycleViewPort` that cannot answer. ARM 4's fail-closed control."""

    def eligibility(self, strategy_id: str) -> Any:
        raise RuntimeError(f"the mirrored picture is unreadable for {strategy_id}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key
        for key in sys.modules
        if key in _PACKAGES or key.startswith(tuple(f"{p}." for p in _PACKAGES))
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Driven | None, str]:
    """Import every subject OUT OF `home`, never by name off the live repo."""
    for _, _, rel in _MODULES:
        if not (home / rel).is_file():
            return None, (
                f"{rel}: no such file under {home} — the subject is unavailable, "
                "so nothing was measured (§17: never a PASS)"
            )
    if not (home / SPEC).is_file():
        return None, f"{SPEC}: absent under {home}; ARM 1 has no reference side"
    saved_path = list(sys.path)
    saved = {
        key: value
        for key, value in sys.modules.items()
        if key in _PACKAGES or key.startswith(tuple(f"{p}." for p in _PACKAGES))
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        modules = {
            attribute: importlib.import_module(dotted)
            for attribute, dotted, _ in _MODULES
        }
        defect = _provenance(modules, home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{LIFECYCLE}: cannot import the subjects from {home} — "
            f"{type(exc).__name__}: {exc}. Nothing was measured (§17)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved)
    if defect:
        return None, (
            f"{LIFECYCLE}: {defect}. Nothing about {home} was measured, so this "
            "is CANNOT_MEASURE and is deliberately never a PASS (§17)"
        )
    return Driven(modules=modules, home=home), ""


def _provenance(modules: dict[str, ModuleType], home: Path) -> str:
    """Did every loaded module really come OUT OF `home`? MEASURED, not assumed.

    `checks/_preamble.py` appends the REAL `scripts/` to `sys.path` permanently,
    so a name-based import resolves against the live repository whatever
    `ctx.nix_home` says — the defect measured LIVE on two shipped gates (D3.124).
    """
    want = {attribute: rel for attribute, _, rel in _MODULES}
    for key, module in modules.items():
        origin = getattr(module, "__file__", None)
        if origin is None:
            return f"{module.__name__} has no __file__, so its origin is unknowable"
        got = Path(origin).resolve()
        expected = (home / want[key]).resolve()
        if got != expected:
            return f"{module.__name__} was imported from {got}, not {expected}"
    return ""


# ---------------------------------------------------------------------------
# ARM 1 — the screened state is the SPEC's (§4:284-286)
# ---------------------------------------------------------------------------


def _section_span(text: str, label: str) -> tuple[int, int] | None:
    """The 1-based line span of `## <label>. ...`, or None if it is not there.

    The span runs to the line before the NEXT numbered heading — the same rule
    `check_spec_citations` derives its spans by, so a coordinate this gate
    reports and a citation that gate resolves mean the same thing.
    """
    lines = text.splitlines()
    starts: list[tuple[int, str]] = [
        (number, match.group("label"))
        for number, line in enumerate(lines, start=1)
        if (match := _HEADING.match(line))
    ]
    for index, (line_number, found) in enumerate(starts):
        if found == label:
            end = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
            return line_number, max(end, line_number)
    return None


def spec_state(home: Path) -> tuple[str, int, str]:
    """`(state name, line, complaint)` parsed from §4's own locked sentence."""
    text = (home / SPEC).read_text(encoding="utf-8")
    span = _section_span(text, _SECTION)
    if span is None:
        return "", 0, f"{SPEC}: no heading for section {_SECTION}, so no span to check"
    for number, line in enumerate(text.splitlines(), start=1):
        match = _SCREENED_PHRASE.search(line)
        if match is None:
            continue
        if not span[0] <= number <= span[1]:
            continue
        return match.group("state"), number, ""
    return (
        "",
        0,
        (
            f"{SPEC}: the bolded in-flight-* phrase did not match inside section "
            f"{_SECTION}'s span {span} — an unmatched anchor yields an EMPTY "
            "expected set, which would compare equal to an empty measured one and "
            "report agreement (§7.12/2)"
        ),
    )


def _states(driven: Driven) -> dict[str, Any]:
    """`{published value: member}` of the seam's lifecycle enumeration."""
    return {member.value: member for member in driven.alloc_seam.PositionState}


def _screened_member(driven: Driven) -> tuple[Any, str]:
    """`(the PositionState §4's sentence names, complaint)`. Derived, never typed."""
    name, _, complaint = spec_state(driven.home)
    if complaint:
        return None, complaint
    member = _states(driven).get(name)
    if member is None:
        return None, f"{SPEC}: {name!r} is not a published lifecycle state"
    return member, ""


def _arm_spec(driven: Driven) -> tuple[list[Finding], str]:
    """The module's screened set is exactly the state §4's sentence names."""
    name, line, complaint = spec_state(driven.home)
    if complaint:
        return [], complaint
    states = _states(driven)
    member = states.get(name)
    if member is None:
        return [], (
            f"{SPEC}:{line}: §4 names state {name!r} and PositionState publishes "
            f"{sorted(states)} — the spec's word is not a published state, so "
            "there is nothing to compare and nothing was measured"
        )
    declared = set(driven.lifecycle.IN_FLIGHT_CLOSING)
    if declared != {member}:
        return [
            Finding(
                f"{LIFECYCLE}:IN_FLIGHT_CLOSING",
                f"screens {sorted(state.value for state in declared)} and "
                f"§4:{line}'s locked sentence names {name!r}. The set a strategy "
                "is refused capital for is the SPEC's, not the module's",
            )
        ], ""
    return [], ""


# ---------------------------------------------------------------------------
# ARM 2 / ARM 3 — the transition, driven end to end
# ---------------------------------------------------------------------------


# R0902 refused with a reason: these eight are exactly what one step of the
# transition has to carry for the arms to judge it without re-driving anything —
# the label, the published version, the row counts on both sides of the screen,
# the eligibility value, its reason, the resulting ordering and the refusals.
# Dropping one would either lose an assertion or force an arm to re-run the
# socket sequence to recover it.
@dataclass(frozen=True)
class Step:  # pylint: disable=too-many-instance-attributes
    """One published snapshot, and what the Allocator made of it."""

    label: str
    version: int
    rows: int
    screened_rows: int
    eligible: bool
    reason: str
    ordering: tuple[str, ...]
    refused: tuple[tuple[str, str], ...]


def _row(driven: Driven, state: Any) -> Any:
    """§3:159's published position row. ONE constructor in this file.

    Deliberately the only place a `PositionRow` is built here: the published row
    is being widened in this same arc, so a scattered constructor would be a
    scattered edit.
    """
    return driven.alloc_seam.PositionRow(
        trade_id=TRADE_ID,
        symbol=SYMBOL,
        strategy_id=DYING,
        size=SIZE,
        margin=MARGIN_PER_CONTRACT * SIZE,
        state=state,
        # ARC 032 / Phase 0.4: `stop_distance` is a published field now
        # (`SEAM_REV 1.1.0`, `SPEC-A9`). One edit, as this function's docstring
        # predicted. `STOP_DISTANCE_TICKS` and not a bare literal so the number
        # has a name, and positive so §7's cap would price this row — a zero
        # here would be a §4 fixture that is also a §7 finding.
        stop_distance=STOP_DISTANCE_TICKS,
    )


def _settle(publisher: Any, mirror: Any, target: int) -> bool:
    """Wait, bounded, for `target` to reach the mirror over the real socket."""
    for _ in range(SETTLE_ATTEMPTS):
        publisher.service(SERVICE_MS)
        mirror.refresh(DRAIN_MS)
        if mirror.version() >= target:
            return True
        publisher.refresh_all()
    return bool(mirror.version() >= target)


def _observe(driven: Driven, mirror: Any, label: str, screened: Any) -> Step:
    """Screen ONE arrived snapshot, and run the contention pass over it."""
    snapshot = mirror.snapshot()
    picture = snapshot.picture
    verdict = driven.lifecycle.eligibility_from_mirror(snapshot, DYING)
    live = driven.lifecycle.MirrorLifecycle(mirror)
    #: ONE read of the mirror, pinned, so both contenders are screened against
    #: the SAME version — a view re-read per contender could straddle a publish.
    pinned = live.pin()
    view = live if pinned is None else pinned
    contender = driven.contention.Contender
    ranking = driven.contention.rank_eligible(
        [
            contender(strategy_id=DYING, symbol=SYMBOL, arrival_seq=1),
            contender(strategy_id=HEALTHY, symbol=SYMBOL, arrival_seq=2),
        ],
        None,
        view,
    )
    rows = tuple(picture.positions) if picture is not None else ()
    return Step(
        label=label,
        version=mirror.version(),
        rows=len(rows),
        screened_rows=sum(1 for row in rows if row.state in screened),
        eligible=bool(verdict.eligible),
        reason=verdict.reason,
        ordering=tuple(item.strategy_id for item in ranking.ordering),
        refused=tuple(
            (item.contender.strategy_id, item.reason) for item in ranking.refused
        ),
    )


def _executor(driven: Driven, book: Any, broker: Any) -> Any:
    """§4's protective-flatten executor, wired to the SHIPPED ledger and book."""
    plane1 = _Plane1()
    return driven.flatten.ProtectiveFlatten(
        broker=broker,
        ledger=driven.reservations.ReservationLedger(plane1),
        picture=book,
        strategy=_StrategySink(),
        plane1=plane1,
        scoring=_ScoringSink(),
        clock=time.time,
    )


def _transition(driven: Driven, root: Path) -> tuple[list[Step], str]:
    """Drive open -> in-flight-closing -> flat on ONE moving snapshot sequence.

    Real producer (`FinancialPictureBook` + `ProtectiveFlatten`), real wire
    (`nixbus.statebus` over `ipc://`), real consumer (`AllocatorMirror`). The
    broker is the only stand-in, and it is the one collaborator that provably
    cannot be real: §4's reconcile is DEFINED against broker truth.
    """
    statebus, picture_mod = driven.statebus, driven.picture
    endpoint = statebus.endpoint_for("alloc-lifecycle", root=root)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        book = picture_mod.FinancialPictureBook(
            balance=BALANCE,
            deployable_fraction=picture_mod.SPEC_DEPLOYABLE_FRACTION,
            sink=picture_mod.StateBusPictureSink(publisher),
            margin_per_contract={SYMBOL: MARGIN_PER_CONTRACT},
        )
        subscriber = statebus.StateSubscriber(endpoint, [picture_mod.TOPIC])
        mirror = driven.mirror.AllocatorMirror(
            driven.mirror.StateBusFeed(subscriber), max_age_s=MAX_AGE_S
        )
        broker = _HaltedMarketBroker()
        executor = _executor(driven, book, broker)
        return _steps(driven, book, broker, executor, publisher, mirror, endpoint)
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


# R0913/R0917 refused with a reason: these are the six live objects one moving
# sequence needs — the producer, the broker whose truth moves, the executor that
# republishes, the publisher that must be serviced, the consumer that must
# receive, and the endpoint the failure has to name. Collapsing them into a
# struct would mint a value type that exists only to satisfy an argument count.
def _steps(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    driven: Driven,
    book: Any,
    broker: Any,
    executor: Any,
    publisher: Any,
    mirror: Any,
    endpoint: str,
) -> tuple[list[Step], str]:
    """The three published versions, each waited for and each screened."""
    screened = driven.lifecycle.IN_FLIGHT_CLOSING
    steps: list[Step] = []
    # The labels are deliberately NOT the lifecycle state values: the can-fail
    # suite asserts by AST that no published state name is spelled anywhere in
    # this gate's executable code, so a label that happened to be one would make
    # the reference side look transcribed even where it is parsed.
    plan = (
        ("held", lambda: book.commit(positions=(_row(driven, _open_state(driven)),))),
        ("mid-recovery", lambda: _flatten_into_halt(driven, executor)),
        ("flat", lambda: _market_reopens(broker, executor)),
    )
    for label, action in plan:
        action()
        target = book.current().version
        if not _settle(publisher, mirror, target):
            return steps, (
                f"{endpoint}: published version {target} ({label}) never reached "
                f"the mirror within {SETTLE_ATTEMPTS} settle attempts — the "
                "sequence did not move, so every later reading would be the "
                "same stale one and nothing was measured (§17)"
            )
        steps.append(_observe(driven, mirror, label, screened))
    return steps, ""


def _open_state(driven: Driven) -> Any:
    """§4:201's confirmed-fill state, read off the published enumeration."""
    return driven.alloc_seam.PositionState.OPEN


def _flatten_into_halt(driven: Driven, executor: Any) -> None:
    """Fire a protective flatten the market will not absorb (§12.6, §4)."""
    executor.fire(driven.risk_seam.FlattenTrigger[_TRIGGER], symbol=SYMBOL)
    asyncio.run(executor.reconcile_and_publish())


def _market_reopens(broker: Any, executor: Any) -> None:
    """Broker truth goes flat; the reconcile publishes the CONFIRMED state."""
    broker.holds = False
    asyncio.run(executor.reconcile_and_publish())


def _arm_transition(driven: Driven, steps: list[Step]) -> tuple[list[Finding], str]:
    """The eligibility VALUE must move True -> False -> True, and versions with it."""
    # Every arm takes the same two things so `_drive` can run them uniformly and
    # none can be skipped by another's exception (§7.12/6). This one judges the
    # sequence the driver already produced and reaches for nothing else.
    del driven
    if len(steps) < MIN_STEPS:
        return [], (
            f"only {len(steps)} of {MIN_STEPS} snapshots were driven, so the "
            "transition was never completed and no value could change"
        )
    opened, dying, recovered = steps[0], steps[1], steps[2]
    versions = [step.version for step in steps]
    if versions != sorted(set(versions)):
        return [
            Finding(
                f"{LIFECYCLE}:eligibility_from_mirror",
                f"the three readings carry versions {versions}, which are not "
                "strictly increasing — the mirror did not move between steps, so "
                "any change in the answer came from somewhere other than the "
                "published snapshot",
            )
        ], ""
    if dying.screened_rows < MIN_CLOSING_ROWS:
        return [
            Finding(
                f"{LIFECYCLE}:IN_FLIGHT_CLOSING",
                f"the middle snapshot (version {dying.version}) carries "
                f"{dying.screened_rows} row(s) in the screened state, below the "
                f"discriminator floor of {MIN_CLOSING_ROWS}. The producer never "
                "produced the state, so this arm measures nothing about it — "
                "reported as an instrument failure rather than a pass",
            )
        ], ""
    return _transition_findings(opened, dying, recovered), ""


def _transition_findings(opened: Step, dying: Step, recovered: Step) -> list[Finding]:
    """The three assertions ARM 2 makes, each naming its own reason."""
    site = f"{LIFECYCLE}:eligibility_from_mirror"
    findings: list[Finding] = []
    if not opened.eligible:
        findings.append(
            Finding(
                site,
                f"{DYING} was refused capital at version {opened.version} while "
                f"holding {opened.rows} row(s) and NONE in the screened state — "
                f"a screen that refuses a healthy strategy is not §4:284-286, it "
                f"is a constant. It said: {opened.reason}",
            )
        )
    if dying.eligible:
        findings.append(
            Finding(
                site,
                f"{DYING} was still counted ELIGIBLE for new capital at version "
                f"{dying.version} while holding {dying.screened_rows} published "
                "row(s) in the in-flight-closing state — §4:284-286 says a "
                "strategy mid-recovery is never counted eligible for new capital "
                f"while dying. It said: {dying.reason}",
            )
        )
    if not recovered.eligible:
        findings.append(
            Finding(
                site,
                f"{DYING} was still refused at version {recovered.version} after "
                f"its rows returned to flat ({recovered.rows} published row(s), "
                f"{recovered.screened_rows} screened) — the refusal did not "
                "release, so eligibility is latched rather than reflected. It "
                f"said: {recovered.reason}",
            )
        )
    return findings


def _arm_contention(driven: Driven, steps: list[Step]) -> tuple[list[Finding], str]:
    """The contention pass drops the dying contender and keeps the healthy one."""
    del driven
    if len(steps) < MIN_STEPS:
        return [], f"only {len(steps)} of {MIN_STEPS} snapshots; ARM 3 has no subject"
    opened, dying, recovered = steps[0], steps[1], steps[2]
    site = f"{CONTENTION}:rank_eligible"
    findings: list[Finding] = []
    if not opened.ordering or opened.ordering[0] != DYING:
        findings.append(
            Finding(
                site,
                f"{DYING} arrived FIRST and the healthy ordering is "
                f"{opened.ordering} — §6.6:466's FCFS fallback puts the earliest "
                "arrival at the head, so unless it leads here the later "
                "disappearance proves nothing about the screen",
            )
        )
    findings += _dying_findings(dying, site)
    if DYING not in recovered.ordering:
        findings.append(
            Finding(
                site,
                f"{DYING} is still absent from the ordering {recovered.ordering} "
                "after its rows returned to flat — the screen is a one-way door",
            )
        )
    if HEALTHY not in dying.ordering:
        findings.append(
            Finding(
                site,
                f"{HEALTHY} was screened out too (ordering {dying.ordering}) "
                "while owning no published row — a screen that refuses everyone "
                "passes a test that only watches the dying contender",
            )
        )
    return findings, ""


def _dying_findings(dying: Step, site: str) -> list[Finding]:
    """The middle step: absent from the ordering, and the refusal names why."""
    if DYING in dying.ordering:
        return [
            Finding(
                site,
                f"{DYING} is still in the contention ordering {dying.ordering} "
                "while holding a published in-flight-closing row — §4:284-286 "
                "keeps it out of the race for new capital, and §6.6:466's FCFS "
                "fallback would otherwise hand it the head of the ordering",
            )
        ]
    named = [reason for who, reason in dying.refused if who == DYING]
    if not named:
        return [
            Finding(
                site,
                f"{DYING} left the ordering with no refusal record at all "
                f"(refused={[who for who, _ in dying.refused]}) — a contender "
                "that vanishes without a reason is indistinguishable from one "
                "that was never offered (§18)",
            )
        ]
    if TRADE_ID not in named[0]:
        return [
            Finding(
                site,
                f"the refusal of {DYING} names neither the trade nor the state: "
                f"{named[0]!r}. §18 requires the REASON, and a refusal that "
                "cannot say which position is closing is unactionable",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 4 — FAIL CLOSED, in the three ways the screen can fail to answer
# ---------------------------------------------------------------------------


def _stale_but_held(driven: Driven) -> Any:
    """A mirror HOLDING a real picture whose stamp is past the ceiling (§6.4).

    The dangerous half of not-FRESH, and the one a `picture is None` guard
    misses entirely: the picture is right there, and reading it anyway is the
    *"carry on with the last value"* §6.4 forbids by name. Built through the
    real producer with its clock pinned at the epoch, so the age is enormous
    and the control cannot be a flake.
    """
    picture_mod = driven.picture
    book = picture_mod.FinancialPictureBook(
        balance=BALANCE,
        deployable_fraction=picture_mod.SPEC_DEPLOYABLE_FRACTION,
        margin_per_contract={SYMBOL: MARGIN_PER_CONTRACT},
        clock=lambda: 0.0,
    )
    aged = book.commit(positions=(_row(driven, _open_state(driven)),))
    mirror = driven.mirror.AllocatorMirror(
        _SilentFeed(
            driven.mirror.MirrorUpdate(picture=aged, heard=True, complete=True)
        ),
        max_age_s=MAX_AGE_S,
    )
    mirror.refresh(0)
    return mirror


def _stale_findings(driven: Driven) -> list[Finding]:
    """A STALE mirror that still HOLDS a picture must refuse (§6.4)."""
    mirror = _stale_but_held(driven)
    state = mirror.snapshot().state
    if state is driven.alloc_seam.MirrorState.FRESH:
        return [
            Finding(
                f"{LIFECYCLE}:eligibility_from_mirror",
                "the aged-picture control produced a FRESH mirror, so the "
                "stale branch was never reached and this control measures "
                "nothing — an instrument failure, not a pass",
            )
        ]
    if driven.lifecycle.MirrorLifecycle(mirror).eligibility(DYING).eligible:
        return [
            Finding(
                f"{LIFECYCLE}:eligibility_from_mirror",
                f"a {state.value.upper()} mirror that still HOLDS a picture "
                f"admitted {DYING} for new capital — §6.4's rule for a stale "
                "cache is refuse, never carry on with the last value, and a "
                "guard that only tests `picture is None` misses exactly this",
            )
        ]
    return []


def _arm_fail_closed(driven: Driven) -> tuple[list[Finding], str]:
    """An unread mirror, a stale-but-held mirror and a raising view all REFUSE."""
    mirror = driven.mirror.AllocatorMirror(
        _SilentFeed(driven.mirror.MirrorUpdate()), max_age_s=MAX_AGE_S
    )
    mirror.refresh(0)
    unheard = driven.lifecycle.MirrorLifecycle(mirror).eligibility(DYING)
    findings: list[Finding] = []
    if unheard.eligible:
        findings.append(
            Finding(
                f"{LIFECYCLE}:eligibility_from_mirror",
                f"a mirror in state {mirror.snapshot().state.value!r} — nothing "
                "has ever arrived from the Limiter — still admitted "
                f"{DYING} for new capital. §12.7 never sizes on a half-built "
                "mirror, and an eligibility computed off no picture is an "
                "admission dressed as a measurement",
            )
        )
    findings += _stale_findings(driven)
    raising, raised_reason = _raising_view_findings(driven)
    findings += raising
    if not findings and unheard.reason.strip() == raised_reason.strip():
        findings.append(
            Finding(
                f"{LIFECYCLE}:eligibility_from_mirror",
                "the unheard-mirror refusal and the unanswerable-view refusal "
                "name the SAME reason, so two different faults with two "
                "different repairs are indistinguishable (§18)",
            )
        )
    return findings, ""


def _raising_view_findings(driven: Driven) -> tuple[list[Finding], str]:
    """A view that raises must refuse WITHOUT the exception reaching the pass."""
    site = f"{CONTENTION}:rank_eligible"
    contender = driven.contention.Contender
    field_of = [contender(strategy_id=DYING, symbol=SYMBOL, arrival_seq=1)]
    try:
        ranking = driven.contention.rank_eligible(field_of, None, _RaisingView())
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                site,
                f"a lifecycle view that raises let {type(exc).__name__}: {exc} "
                "escape onto the contention pass — an unanswerable safety screen "
                "must REFUSE, not propagate a failure into the caller",
            )
        ], ""
    if ranking.ordering:
        return [
            Finding(
                site,
                f"a lifecycle view that raises still admitted "
                f"{[item.strategy_id for item in ranking.ordering]} — an "
                "unanswerable screen that admits is the fail-OPEN direction, and "
                "the one that hands capital to a strategy that may be dying",
            )
        ], ""
    named = [item.reason for item in ranking.refused]
    if not named or "RuntimeError" not in named[0]:
        return [
            Finding(
                site,
                f"the refusal from a raising view names {named!r} — §18 requires "
                "the reason, and a screen that cannot say WHY it could not "
                "answer is a silent outage",
            )
        ], ""
    return [], named[0]


# ---------------------------------------------------------------------------
# ARM 5 — the boundary, BY ATTEMPT and BY CENSUS (§2, §4:260-274)
# ---------------------------------------------------------------------------


def _carries(name: str, stem: str) -> bool:
    """Whole word or leading stem, so `kill` and `kill_strategy` both hit."""
    lowered = name.lstrip("_").lower()
    return lowered == stem or lowered.startswith(f"{stem}_")


def _producers(home: Path, attr: str) -> tuple[str, ...]:
    """Every tracked module that CONSTRUCTS a row in the screened state.

    A construction, not a mention: the pattern is a `state=<Enum>.<ATTR>` keyword
    on a call. A module that merely names the member — this gate does, and so
    does `lifecycle.IN_FLIGHT_CLOSING` — is a reader, not a producer, and a
    census that could not tell them apart would report the screen as its own
    writer.
    """
    found: list[str] = []
    for path in sorted((home / "scripts").rglob("*.py")):
        rel = path.relative_to(home).as_posix()
        if rel.startswith(CENSUS_SKIP):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        if any(_is_producer(node, attr) for node in ast.walk(tree)):
            found.append(rel)
    return tuple(found)


def _is_producer(node: ast.AST, attr: str) -> bool:
    """Is this node a `state=<something>.<attr>` keyword on a call?"""
    return (
        isinstance(node, ast.keyword)
        and node.arg == "state"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == attr
    )


def _arm_boundary(driven: Driven) -> tuple[list[Finding], str]:
    """No driving verb, no coroutine, and no Allocator-side producer."""
    findings = [
        Finding(
            f"{LIFECYCLE}:{name}",
            f"the Allocator's lifecycle module exposes {name!r}, whose stem is "
            f"the recovery verb {stem!r}. §4:260-274 gives flatten, "
            "force-deregister, kill+relaunch and quarantine to the Limiter and "
            "the supervisor; §2 makes the Allocator permissive. This module "
            "REFLECTS recovery and a verb that drives it is the authority split "
            "crossed in the one direction it may not be",
        )
        for name in dir(driven.lifecycle)
        if not name.startswith("__")
        for stem in _DRIVING_VERBS
        if _carries(name, stem)
    ]
    source = (driven.home / LIFECYCLE).read_text(encoding="utf-8")
    findings += [
        Finding(
            f"{LIFECYCLE}:{node.name}",
            "declared `async def` — the screen is consulted inside §16 U1's "
            "single pass, and a suspension point there is a window in which the "
            "published picture can change under the decision it produced",
        )
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef)
    ]
    census, complaint = _census_findings(driven)
    return findings + census, complaint


def _census_findings(driven: Driven) -> tuple[list[Finding], str]:
    """WHO publishes the screened state, measured over the tree under test."""
    member, complaint = _screened_member(driven)
    if member is None:
        return [], f"ARM 5 has no census: {complaint}"
    producers = _producers(driven.home, member.name)
    outside = [rel for rel in producers if not rel.startswith(ALLOCATOR_PACKAGE)]
    if len(outside) < MIN_PRODUCERS:
        return [], (
            f"the census found {len(outside)} producer(s) of the screened state "
            f"outside {ALLOCATOR_PACKAGE}, below the floor of {MIN_PRODUCERS} — "
            "nothing in this tree publishes the state the transition arm claims "
            "to drive, so the census cannot discriminate and is reported as an "
            "instrument failure rather than a clean boundary"
        )
    inside = [rel for rel in producers if rel.startswith(ALLOCATOR_PACKAGE)]
    return [
        Finding(
            f"{rel}:state=",
            "the Allocator's own package CONSTRUCTS a position row in the "
            "screened state. §2 makes the Allocator permissive and §4:281-286 "
            "makes it a READER of the mirrored snapshot: the Limiter publishes "
            "recovery, the Allocator reflects it. A producer here is the "
            "Allocator writing canonical state that appears in no event log",
        )
        for rel in inside
    ], ""


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

ARMS = 5


def _remove_tree(root: Path) -> None:
    """Delete the scratch bus directory by ABSOLUTE path, never `shutil.rmtree`.

    MEASURED, ARC 026 (`check_state_bus._remove_tree`): on POSIX `rmtree`
    recurses on directory file descriptors and unlinks with a BARE RELATIVE
    name, which the audit hook records with no directory attached, so no
    path-rooted RESOURCES declaration can ever account for it.
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


def _evidence(driven: Driven, steps: list[Step]) -> str:
    """What was actually driven, in figures rather than adjectives."""
    _, line, _ = spec_state(driven.home)
    member, _ = _screened_member(driven)
    census = _producers(driven.home, member.name) if member is not None else ()
    sequence = "; ".join(
        f"{step.label}=v{step.version}/{step.screened_rows} screened row(s)/"
        f"eligible={step.eligible}/ordering={list(step.ordering)}"
        for step in steps
    )
    return (
        f"{ARMS} arms driving the SHIPPED {LIFECYCLE} and {CONTENTION} out of "
        f"{driven.home}: the screened state parsed from {SPEC} §{_SECTION} at "
        f"line {line} with no state name spelled in this gate; a transition "
        f"driven over a REAL ipc:// socket through the real producer "
        f"(nixrisk.picture + nixrisk.flatten), the real wire (nixbus.statebus) "
        f"and the real consumer (nixalloc.mirror) — {sequence}; the contention "
        f"pass screened at every step with the dying contender arriving FIRST; "
        f"fail-closed proven three ways — an unheard mirror, a mirror still "
        f"HOLDING a picture past its ceiling, and a view that raises; "
        f"{len(_DRIVING_VERBS)} recovery verbs reached for BY ATTEMPT and all "
        f"absent; producer census {list(census)}. "
        f"WHAT PRODUCES THIS STATE — {driven.lifecycle.RECOVERY_PRODUCER}. "
        f"WHAT IS NOT HERE — {driven.lifecycle.SCORE_BOUNDARY}"
    )


def _drive(driven: Driven, root: Path) -> tuple[list[Finding], list[str], list[Step]]:
    """Run EVERY arm unconditionally and collect both halves of each answer."""
    steps, complaint = _transition(driven, root)
    findings: list[Finding] = []
    unmeasured: list[str] = [complaint] if complaint else []
    arms = (
        _arm_spec,
        lambda driven_: _arm_transition(driven_, steps),
        lambda driven_: _arm_contention(driven_, steps),
        _arm_fail_closed,
        _arm_boundary,
    )
    for index, arm in enumerate(arms, start=1):
        try:
            arm_findings, arm_complaint = arm(driven)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            # An arm that throws IS a finding about its subject, and it names
            # which arm — without this the FIRST arm to raise would abort the
            # other four and the gate would report CANNOT_MEASURE over a real,
            # nameable defect.
            findings.append(
                Finding(
                    f"{LIFECYCLE}:arm-{index}",
                    f"the arm raised {type(exc).__name__}: {exc} — a rule that "
                    "cannot be driven at all is a finding about the rule, and "
                    "the remaining arms still ran",
                )
            )
            continue
        findings += arm_findings
        if arm_complaint:
            unmeasured.append(arm_complaint)
    return findings, unmeasured, steps


def _verdict(
    driven: Driven, findings: list[Finding], unmeasured: list[str], steps: list[Step]
) -> CheckResult:
    """Turn the arms' answers into one status. §5.3: an empty scope never passes."""
    if unmeasured and not findings:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, detail="; ".join(unmeasured)
        )
    evidence = _evidence(driven, steps)
    if not findings:
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    detail = "; ".join(f"{site}: {why}" for site, why in findings)
    if unmeasured:
        detail = f"{detail}. ALSO UNMEASURED: {'; '.join(unmeasured)}"
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(site for site, _ in findings),
        evidence=evidence,
        detail=detail,
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive all five arms against the modules under `ctx.nix_home`."""
    root: Path | None = None
    try:
        driven, error = load(ctx.nix_home)
        if driven is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        root = Path(tempfile.mkdtemp(prefix="nixalloc-lifecycle-gate-"))
        findings, unmeasured, steps = _drive(driven, root)
        return _verdict(driven, findings, unmeasured, steps)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )
    finally:
        if root is not None:
            _remove_tree(root)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
