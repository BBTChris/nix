#!/usr/bin/env python3
"""§4's two-phase entry: `OPEN` is asserted ONLY on a CONFIRMED FILL.

ARC 049 / invariant **I4**. ONE gate, ONE property (`nix_check_contract.md`
§5.5):

    every site in the shipped tree that ORIGINATES the `OPEN` position state is
    reachable only behind a confirmed execution report, and a confirmed fill
    DOES reach `OPEN` — so `OPEN` tracks confirmed fills EXACTLY, no more and
    no less.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen risk spec,
unless another document is named on the same line. `D3.<n>` cites
`docs/CHECK-DEBT.md`; `CHECK-A<n>` cites `docs/CHECK-CONTRACT-AMENDMENTS.md`.

THE AUTHORITY, both halves on one line each:

* **§4** — *"Two-phase entry states: `PENDING` (placement accepted) -> `OPEN`
  (fill CONFIRMED). Open is asserted ONLY on broker fill confirmation — never
  on placement ack, never optimistically."*
* **§2A** — `place_order` returns an ack, *never a fill*; `on_ack` is the ack
  and `on_fill` is the confirmation. **§4** — *"position state derives from
  cumulative fills"*.
* **§14** — uncertainty resolves toward FLAT. Never toward an optimistic open.

WHY BOTH DIRECTIONS ARE ONE PROPERTY AND NOT TWO GATES
------------------------------------------------------------------------------
They are the two error directions of ONE equality. `OPEN ⊆ confirmed fills` is
the **phantom position**: committed margin and sizing math for a position that
does not exist, and a protective stop armed on nothing. `confirmed fills ⊆
OPEN` is the **unprotected real position**: size at the venue that §3's table
and §12.7's mirror read as flat, so §7:501 prices it at zero and the
correlation cap ADMITS MORE (D3.136's fail-open, under a new spelling). Split
into two gates, each would have to derive "the set of OPEN-setters" for itself
and the two derivations would drift the first time the tree moved — doctrine
C.9's disagreement case exactly.

DOCTRINE C.9 — WHY THIS IS A NEW INSTRUMENT AND NOT A SECOND ONE
------------------------------------------------------------------------------
C.9 forbids a SECOND instrument for a property that is already owned. This
property was owned by nothing. Measured at ARC 049 S1 over all 98 gates:
`check_execution_ledger` owns *position derives from the unique fill set*
inside `execution.py` and says in its own text that nothing there proves the
state model calls it; `check_fill_handler` owns the fill MOTION (arm, release,
publish); `check_origin_write` owns the published `stop_distance`'s value;
`check_plane1_projection` owns the projection's rebuildability. None of them
asks *which sites can assert OPEN, and is a fill required to reach them*. The
nearest thing in the tree was a pytest control, and S1 measured it evadable —
see below.

THE DEFECT THIS GATE EXISTS FOR (ARC 049 S1, reproduced on a copy)
------------------------------------------------------------------------------
`scripts/tests/test_arc038_c_open_is_confirmed_fill.py::
test_OPEN_is_WRITTEN_at_EXACTLY_TWO_SITES_and_PENDING_at_NONE` is the standing
absence proof for I4. It derives the OPEN-setter set by **`grep` for the
literal text `state=PositionState.OPEN`**, then asserts the set of MODULES.
Two consequences, both measured:

1. **It is spelling-bound (D3.426).** A phantom path that publishes §3's row
   with `state=_ENTRY_STATE`, where `_ENTRY_STATE = PositionState.OPEN` sits at
   module level, is invisible to it. Planted into a throwaway copy of
   `scripts/nixrisk/positions.py`, the control stayed GREEN while a by-shape
   derivation gained a site.
2. **It is module-granular, and it is a test.** Even had it moved, it counts
   modules rather than sites — `projection.py`'s three `build.state =
   STATE_OPEN` transitions are outside its match entirely — and it runs under
   pytest, so it says nothing about the tree a node is actually running.
   `verify.py` had no arm for I4 at all.

So the tree was CORRECT and the PROOF was not: the ARC 048 / I3 shape. Nothing
in `scripts/` was edited to green this gate (`CORRECTABLE = False`, and S2 was
empty by design — `git hash-object` proved the state-model files byte-identical
across ARC 049).

WHAT "BY SHAPE" MEANS HERE (D3.426)
------------------------------------------------------------------------------
The census does not look for a spelling. It looks for the SHAPE *an OPEN-valued
expression is bound into a `state` slot*, which is one of:

* a call keyword — `f(..., state=<expr>)`;
* an assignment to a `state` name or attribute — `build.state = <expr>`.

`<expr>` is resolved through a per-module alias environment, so
`PositionState.OPEN`, `PositionState("open")`, `STATE_OPEN`, `"open"`, an
`x if c else y` with either branch OPEN, and any module-level or function-level
name bound to one of those all resolve alike. Each site is then CLASSIFIED:

* **ORIGINATOR** — the expression is statically OPEN-valued. This site DECIDES
  `OPEN`, and it is what this gate judges.
* **TRANSPORT** — the expression derives from the site's own input (a subscript
  or attribute of a parameter, of `self`, or of a comprehension target):
  `PositionState(raw["state"])` in the wire decoder, `state=self.state` in the
  fold's `frozen()`. These REPRODUCE a state some originator already decided;
  they cannot mint one. Recorded, never judged as originators.
* **UNCLASSIFIABLE** — anything else. **CANNOT_MEASURE naming the site, never
  PASS** (§17, check-contract rule 10): a derivation that silently drops what it
  does not understand is how a phantom path stays invisible.

debug.md §7.12 — THE STANDING QUESTION, asked where the gate is built
------------------------------------------------------------------------------
*What would have to be true for this gate to PASS while measuring nothing?*

1. **The census could find nothing.** An import rename, a walker bug, a wrong
   root — zero OPEN-setters reads exactly like a tree with no phantom.
   *Closed:* `MIN_ORIGINATORS` / `MIN_MODULES_SCANNED` are FLOORS strictly below
   today's counts (doctrine C.4), and below them the verdict is CANNOT_MEASURE.
2. **The accepted set could be keyed to line numbers.** A reformat would then
   red-herring, and worse, a MOVED site would read as a NEW one.
   *Closed:* the accepted table is keyed by `(module, enclosing function)`, and
   line numbers appear only in evidence strings (failure mode #4).
3. **The drive could assert "not OPEN" over an empty rig.** An order never
   really placed is trivially not open.
   *Closed:* NON-VACUITY — the ack arm asserts the reservation is genuinely
   outstanding, the approval genuinely recorded and the origin genuinely minted
   BEFORE it reads any state surface, and the fill arm asserts the execution
   ledger genuinely moved.
4. **The drive could watch only the tick the ack landed on.** A state not-yet
   OPEN is not proof it will not wrongly open on the next event (§0a).
   *Closed:* the ack arm re-reads every surface after a second event (the
   reject/expire release) before it reports.
5. **The gate could import the LIVE repository instead of the tree under
   judgement.** `checks/_preamble.py` appends the real `scripts/` to `sys.path`
   and never removes it, so an empty `nix_home` falls through to this checkout
   and the gate reports on a tree it never read (D3.124).
   *Closed:* every loaded subject module's `__file__` must lie under
   `ctx.nix_home` or the verdict is CANNOT_MEASURE naming the foreign path.
6. **The static gate-proofs could be satisfied by any code at all.** "The
   function calls `ingest` somewhere" is not a gate.
   *Closed:* each accepted originator carries a NAMED structural precondition
   that is re-derived from the AST every run, and each one is falsifiable — the
   PLANT B rehearsal removes exactly one of them and the gate reddens naming it.

WHAT THIS GATE DOES NOT PROVE, stated rather than implied
------------------------------------------------------------------------------
* **The pending-timeout resolution is out of scope.** §4's `PENDING ->
  confirmed | cancelled | indeterminate` via `query_order_status` (never an
  auto-resend) is the POLL path, invariant **I1**, and nothing here wires or
  measures it.
* **D3.372 is NOT discharged by a green here.** A confirmed fill whose origin
  write is REFUSED (`UntradableSymbol` — §4:198's not-tradable symbol) leaves
  §3's table and §12.7's mirror reading FLAT over a real position and records
  only a counter. That is a real `confirmed fills ⊄ OPEN` case, it is MEASURED,
  it BLOCKS on an architect ruling about which surface carries the condition,
  and it is pinned by `test_arc038_c_open_is_confirmed_fill.py::
  test_a_REFUSED_ORIGIN_WRITE_leaves_the_PICTURE_and_the_MIRROR_reading_FLAT`.
  This gate drives the ACCEPTING path and says so on every run in its evidence
  string, so a green cannot be read as covering the refusal.
* It does not prove production fills reach the sink — that is the daemon
  dispatch, `check_limiter_daemon_dispatch`'s subject.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# C0302: the §7.12 block, the C.9 argument and the per-finding reason strings
# ARE the deliverable — each one is a sentence an operator reads out of a red
# verdict — and §4.2 requires a check be independently runnable as ONE file.
# pylint: disable=too-many-lines,duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The subjects are imported from the tree under test
#: and no other check produces them.
DEPENDS_ON: tuple[str, ...] = ()
#: Imports the risk package out of `ctx.nix_home` (mutating `sys.path` and
#: `sys.modules` for the load and restoring both), and writes ONE Plane-1 WAL
#: under `/tmp` so the reservation ledger is the real one rather than a double
#: — the spelling `file-write:/tmp` is the tree's, so the observed-claim
#: comparison in `check_observed_resource_claims` can match it. Declared for
#: the same reason `check_execution_ledger`
#: declares the interpreter claims (§4.4, §17: observed claims are compared
#: against declared ones).
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
)
#: No timeout, no poll, no sleep, no socket. Every drive is in-process.
TIME_BOUND = False
#: NON-CORRECTABLE, and this is the load-bearing declaration of the arc.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is WHICH SITES MAY ASSERT AN OPEN POSITION. A gate empowered "
    "to edit them would be manufacturing its own green over the exact code "
    "path that decides whether committed margin and an armed stop correspond "
    "to size that exists at the venue. The repair for a premature OPEN is the "
    "removal of a path, decided by a human against §4; the repair for a fill "
    "stuck short of OPEN is a change to the state model. Neither is a "
    "mechanical edit an instrument may make to its own subject"
)
#: DELIBERATELY EMPTY, and the reason is the census.
#:
#: This gate parses EVERY module under `scripts/` — the whole point is that a
#: premature-OPEN path may appear in a file nobody thought to name — and drives
#: `positions.py`, `execution.py`, `fills.py`, `picture.py` and `projection.py`
#: out of the tree under judgement. Every one of those already has an owning
#: gate that declares it (`check_origin_write`, `check_execution_ledger`,
#: `check_fill_handler`, `check_picture_atomicity`, `check_plane1_projection`).
#: `check_artifact_gate_coverage` counts SUBJECTS declarations, so listing them
#: again here would move coverage arithmetic without adding coverage — the
#: dishonest half of D3.138's argument. What this gate owns is a property ACROSS
#: the tree, and a tree is not an artifact row.
SUBJECTS: tuple[str, ...] = ()

NAME = "check_two_phase_entry"

PACKAGE = "nixrisk"
#: The scan root, relative to `nix_home`. Tests are excluded: a control that
#: reddens on its own source text measures the harness, not the tree.
SCAN_ROOT = "scripts"
EXCLUDED_PARTS = ("/tests/",)

# --------------------------------------------------------------------------
# NON-VACUITY FLOORS (doctrine C.4 — every one strictly BELOW today's count, so
# a floor equal to today's number cannot pass as a measurement).
# Today: 5 originators, 3 transports, 100+ modules parsed.
# --------------------------------------------------------------------------

#: Below this the census found so little that "no phantom" is indistinguishable
#: from "the walker is broken".
MIN_ORIGINATORS = 3
#: Below this the scan root is wrong or empty.
MIN_MODULES_SCANNED = 40
#: The ack drive must genuinely reserve capital before "nothing is open" means
#: anything.
MIN_RESERVED_ON_ACK = 1.0

# --------------------------------------------------------------------------
# THE ACCEPTED ORIGINATOR TABLE.
#
# Keyed by `(module, enclosing qualified function)` — NEVER by line number
# (§7.12 answer 2). Each row names the CONFIRMED-FILL PRECONDITION that makes
# the site legal, and `arm_gates` re-derives that precondition from the AST on
# every run. A row whose precondition has gone is a FAIL, not a stale comment.
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Accepted:
    """One site allowed to originate `OPEN`, and why it is allowed."""

    module: str
    function: str
    #: The structural precondition, re-derived every run by `arm_gates`.
    gate: str
    why: str


ACCEPTED: tuple[Accepted, ...] = (
    Accepted(
        module="scripts/nixrisk/positions.py",
        function="PositionOriginWriter._row",
        gate="row_only_from_on_fill",
        why=(
            "§3's origin write. `_row` is called from `on_fill` and nowhere "
            "else, and `on_fill` has already handed the report to "
            "`ExecutionLedger.ingest` — a CONFIRMED execution report is the "
            "only way to reach it"
        ),
    ),
    Accepted(
        module="scripts/nixrisk/projection.py",
        function="_on_fill",
        gate="handler_bound_to_filled_event",
        why=(
            "§9's fold. This handler is reachable only through `_HANDLERS` "
            "keyed by `EVENT_FILLED`, so only a `filled` Plane-1 event runs it"
        ),
    ),
    Accepted(
        module="scripts/nixrisk/projection.py",
        function="_on_cancel",
        gate="guarded_by_zero_fill_refusal",
        why=(
            "§4's IOC remainder-cancel RESOLVES a partial; it moves no size. "
            "It returns an anomaly before touching state when "
            "`build.qty_filled == 0`, so it can only re-state a position "
            "cumulative fills already opened"
        ),
    ),
    Accepted(
        module="scripts/nixrisk/projection.py",
        function="_on_reduce",
        gate="guarded_by_zero_fill_refusal",
        why=(
            "an exit. Same `qty_filled == 0` refusal — an exit for a trade "
            "that never opened is an anomaly, never a row"
        ),
    ),
    Accepted(
        module="scripts/nixrisk/projection.py",
        function="position_rows",
        gate="fold_emits_only_filled_builds",
        why=(
            "cold-start reconciliation maps STORED projection rows into §3's "
            "type. Its OPEN is legal because `fold_events` emits a position "
            "only for a build with `qty_filled > 0`, so no never-filled trade "
            "can reach the table it reads"
        ),
    ),
)

_ACCEPTED_KEYS = {(a.module, a.function): a for a in ACCEPTED}

# --------------------------------------------------------------------------
# The by-shape census.
# --------------------------------------------------------------------------

#: Site kinds.
ORIGINATOR = "originator"
TRANSPORT = "transport"
UNCLASSIFIABLE = "unclassifiable"

#: Where §3's position-state enum is declared. Read, never assumed: the member
#: NAMES and the wire VALUES are both derived from this file, so a rename or a
#: new member moves this gate's value domain with the tree instead of leaving a
#: literal behind (failure mode #4).
STATE_ENUM_MODULE = "scripts/nixrisk/seam.py"
#: The one member this gate is about. Everything else in the enum is derived.
OPEN_MEMBER = "OPEN"


@dataclasses.dataclass(frozen=True)
class Site:
    """One place the tree binds something into a POSITION `state` slot."""

    module: str
    lineno: int
    function: str
    kind: str
    source: str


@dataclasses.dataclass(frozen=True)
class Domain:
    """The position-state value domain and the types that carry it.

    DERIVED from the tree on every run (D3.426: by shape, never by spelling
    memorised here). `open_names` are the member names an expression may
    resolve through; `open_values` the wire strings; `state_values` the whole
    enum's strings, which is what identifies a class as position-carrying.
    """

    enum_name: str
    open_names: frozenset[str]
    open_values: frozenset[str]
    member_names: frozenset[str]
    state_values: frozenset[str]
    types: frozenset[str]
    modules: frozenset[str]


def _enum_domain(home: Path) -> tuple[str, dict[str, str], str]:
    """The position-state enum's `{member: value}`, from the tree. Or why not."""
    path = home / STATE_ENUM_MODULE
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return "", {}, f"cannot parse {STATE_ENUM_MODULE}: {exc!r}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        members = {
            target.id: stmt.value.value
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
            for target in stmt.targets
            if isinstance(target, ast.Name)
        }
        if OPEN_MEMBER in members and "PENDING" in members:
            return node.name, members, ""
    return (
        "",
        {},
        (
            f"no enum in {STATE_ENUM_MODULE} declares both {OPEN_MEMBER} and "
            f"PENDING — §4's two-phase entry states are not where this gate "
            f"expects them, so its value domain cannot be derived"
        ),
    )


def _state_value_names(tree: ast.Module, state_values: frozenset[str]) -> set[str]:
    """Module-level names bound to one of §3's state wire values."""
    return {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and node.value.value in state_values
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _declares_state(
    node: ast.ClassDef,
    enum_name: str,
    state_values: frozenset[str],
    local: set[str],
) -> bool:
    """Does this class declare a `state` field carrying a position state?"""
    return any(
        _state_field_carries(stmt, enum_name, state_values, local) for stmt in node.body
    )


def _state_field_carries(
    stmt: ast.stmt,
    enum_name: str,
    state_values: frozenset[str],
    local: set[str],
) -> bool:
    """Is this statement a `state` field declaration carrying a position state?"""
    if not isinstance(stmt, ast.AnnAssign):
        return False
    target = stmt.target
    if not (isinstance(target, ast.Name) and target.id == "state"):
        return False
    if isinstance(stmt.annotation, ast.Name) and stmt.annotation.id == enum_name:
        return True
    default = stmt.value
    if isinstance(default, ast.Constant) and default.value in state_values:
        return True
    return isinstance(default, ast.Name) and default.id in local


def _position_types(home: Path, enum_name: str, state_values: frozenset[str]):
    """Classes that carry a position state, and the modules that hold them.

    A class is position-carrying when it declares a `state` field ANNOTATED with
    the enum, or a `state` field whose default is one of the enum's wire values
    (the projection's `_Build.state: str = STATE_PARTIAL` shape). Both are
    derived; neither is a list of names kept here.
    """
    types: set[str] = set()
    modules: set[str] = set()
    aliases: dict[str, set[str]] = {}
    for path in sorted((home / SCAN_ROOT).rglob("*.py")):
        rel = str(path.relative_to(home))
        if any(part in f"/{rel}" for part in EXCLUDED_PARTS):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        local = _state_value_names(tree, state_values)
        aliases[rel] = set(local)
        if local:
            # A module that binds a name to one of §3's state VALUES is working
            # in the position-state domain, whatever it calls its classes. This
            # is what puts `projection.py` — whose `_Build.state` is a plain
            # `str` defaulted to `STATE_PARTIAL` — in scope without this gate
            # memorising either name.
            modules.add(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _declares_state(
                node, enum_name, state_values, local
            ):
                types.add(node.name)
                modules.add(rel)
    return frozenset(types), frozenset(modules), aliases


def _literal_in(node: ast.AST, names: frozenset[str], values: frozenset[str]) -> bool:
    """Is `node` one of these state members/values, ignoring aliases? By SHAPE."""
    if isinstance(node, ast.Attribute) and node.attr in names:
        return True
    if isinstance(node, ast.Constant) and node.value in values:
        return True
    if isinstance(node, ast.Call):
        # `PositionState("open")` / `PositionState(STATE_OPEN)`
        return any(_literal_in(arg, names, values) for arg in node.args)
    if isinstance(node, ast.IfExp):
        return _literal_in(node.body, names, values) or _literal_in(
            node.orelse, names, values
        )
    return False


def _literal_open(node: ast.AST, domain: Domain) -> bool:
    """Is `node` an OPEN-valued expression, ignoring aliases? By SHAPE."""
    return _literal_in(node, domain.open_names, domain.open_values)


def _literal_state(node: ast.AST, domain: Domain) -> bool:
    """Is `node` ANY of §3's position states? OPEN included."""
    return _literal_in(node, domain.member_names, domain.state_values)


def _alias_env(
    tree: ast.Module, domain: Domain, *, any_state: bool = False
) -> set[str]:
    """Names bound anywhere in this module to a state-valued expression.

    `any_state=False` (the default) resolves the OPEN aliases — the set that
    decides whether a site ORIGINATES an open position. `any_state=True`
    resolves aliases for EVERY member of §3's enum, which is how a non-OPEN
    state constant (`STATE_PARTIAL`) is told apart from an expression this
    derivation genuinely does not understand.

    Module level AND function level: `_ENTRY_STATE = PositionState.OPEN` at the
    top of a file and `st = PositionState.OPEN` inside a function are the same
    evasion, and ARC 049 S1 planted the first of them. A fixpoint, because one
    alias may be defined through another.
    """
    literal = _literal_state if any_state else _literal_open
    env: set[str] = set()
    while _alias_pass(tree, domain, literal, env):
        pass
    return env


def _bound_names(node: ast.AST, domain: Domain, literal, env: set[str]) -> set[str]:
    """The plain names this binding gives a state-valued expression to."""
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return set()
    value = node.value
    if value is None:
        return set()
    if not (
        literal(value, domain) or (isinstance(value, ast.Name) and value.id in env)
    ):
        return set()
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {t.id for t in targets if isinstance(t, ast.Name)}


def _alias_pass(tree: ast.Module, domain: Domain, literal, env: set[str]) -> bool:
    """One sweep of the alias fixpoint. True if it learned a new name."""
    learned = False
    for node in ast.walk(tree):
        for name in _bound_names(node, domain, literal, env) - env:
            env.add(name)
            learned = True
    return learned


def _derives_from_input(node: ast.AST, domain: Domain) -> bool:
    """Does this expression REPRODUCE a state carried in the site's input?

    True for a subscript or an attribute read — `raw["state"]`, `self.state`,
    `row.state`, `PositionState(raw["state"])`, `str(row["state"])`. Such a site
    cannot MINT `OPEN`: whatever it produces, some originator decided upstream.
    False for anything else, so the default stays at "I do not understand this"
    rather than at "harmless".
    """
    if isinstance(node, ast.Subscript):
        return True
    if isinstance(node, ast.Attribute):
        return not _literal_open(node, domain)
    if isinstance(node, ast.Call):
        return bool(node.args) and all(
            _derives_from_input(arg, domain) for arg in node.args
        )
    return False


def _label(node: ast.AST | None) -> str:
    """A short, stable label for a node that is not a plain Name."""
    return "<none>" if node is None else type(node).__name__


def _state_bindings(
    tree: ast.AST, domain: Domain, in_scope_module: bool, env: set[str] | None = None
):
    """Every `(lineno, value)` this subtree binds into a POSITION `state` slot.

    Scope, and why it is drawn here rather than at "anything called `state`":
    `scripts/` holds a datafeed whose per-symbol subscription bookkeeping also
    uses a local named `state`. Judging those would make the gate CANNOT_MEASURE
    on code that cannot hold a position, which is a gate that never reports.
    A binding is in scope when EITHER

    * the value is OPEN-valued by shape — an originator wherever it lives, which
      is the spelling-proof half and the reason a planted alias cannot hide; OR
    * the slot is a position-state slot: a keyword on a call to a class this
      run DERIVED as position-carrying, or a `.state` assignment inside a module
      that declares one.
    """
    aliases = env or set()

    def open_valued(node: ast.AST) -> bool:
        return _literal_open(node, domain) or (
            isinstance(node, ast.Name) and node.id in aliases
        )

    # A class FIELD DECLARATION is not a transition. `state: str =
    # STATE_PARTIAL` declares what a fold accumulator STARTS as; what this gate
    # judges is code that MOVES a state to OPEN. A declared default that IS
    # open-valued is still in scope — it comes back through `open_valued`
    # below — so nothing about OPEN is waived by this, only the vocabulary a
    # neighbouring enum happens to use for its own non-open states.
    declarations = {
        id(stmt)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign)
    }

    found: list[tuple[int, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            found += _call_state_kwargs(node, domain, open_valued)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            found += _assign_state_targets(
                node, declarations, in_scope_module, open_valued
            )
    return found


def _called_name(func: ast.AST) -> str:
    """The bare name a call site invokes, for a `Name` or an `Attribute`."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _call_state_kwargs(node: ast.Call, domain: Domain, open_valued):
    """`f(..., state=<expr>)`, where `f` is position-carrying or `<expr>` opens."""
    out: list[tuple[int, ast.AST]] = []
    called = _called_name(node.func)
    for kw in node.keywords:
        if kw.arg != "state":
            continue
        if called in domain.types or open_valued(kw.value):
            out.append((getattr(kw.value, "lineno", node.lineno), kw.value))
    return out


def _target_name(target: ast.AST) -> str | None:
    """The attribute or name a binding writes to, or None for anything else."""
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return None


def _assign_state_targets(node, declarations, in_scope_module: bool, open_valued):
    """`x.state = <expr>` / `state = <expr>`, minus class field declarations."""
    value = node.value
    if value is None:
        return []
    if id(node) in declarations and not open_valued(value):
        return []
    if not (in_scope_module or open_valued(value)):
        return []
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [
        (node.lineno, value) for target in targets if _target_name(target) == "state"
    ]


def _enclosing(tree: ast.Module) -> dict[int, str]:
    """Line -> qualified enclosing function name, for every line in a body."""
    out: dict[int, str] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                for line in range(child.lineno, (child.end_lineno or child.lineno) + 1):
                    out[line] = name
                walk(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def _worst_of(*kinds: str) -> str:
    """A ternary is as dangerous as its most dangerous branch. Fail-closed."""
    if ORIGINATOR in kinds:
        return ORIGINATOR
    if UNCLASSIFIABLE in kinds:
        return UNCLASSIFIABLE
    return TRANSPORT


# R0911: eight returns, one per KIND of expression, each on its own line with
# the reason beside it. Collapsing them into a chain of `kind = ...` assignments
# would hide which shape produced which classification — and this function's
# whole job is to say WHY a site is or is not an originator.
def _classify(  # pylint: disable=too-many-return-statements
    value: ast.AST, env: set[str], domain: Domain, states: set[str] | None = None
) -> str:
    """ORIGINATOR / TRANSPORT / UNCLASSIFIABLE — three-way, fail-closed."""
    if _literal_open(value, domain):
        return ORIGINATOR
    if isinstance(value, ast.Name):
        if value.id in env:
            return ORIGINATOR
        # A name bound to a NON-open member of §3's enum: `STATE_PARTIAL`. It
        # cannot open a position, and it is not an expression this derivation
        # failed to understand.
        return TRANSPORT if value.id in (states or set()) else UNCLASSIFIABLE
    if isinstance(value, ast.IfExp):
        return _worst_of(
            _classify(value.body, env, domain, states),
            _classify(value.orelse, env, domain, states),
        )
    if isinstance(value, ast.Constant):
        # A non-OPEN state literal: `STATE_PARTIAL`'s value, `"closed"`.
        return TRANSPORT if value.value in domain.state_values else UNCLASSIFIABLE
    if _derives_from_input(value, domain):
        return TRANSPORT
    if isinstance(value, ast.Attribute):
        # A non-OPEN enum member: `PositionState.CLOSING`. Unambiguous, and not
        # a state this gate judges.
        return TRANSPORT
    return UNCLASSIFIABLE


# R0914: the census carries the whole derivation in one frame — the enum, its
# members and values, the derived types and modules, the per-module alias envs,
# the source lines and the enclosing-function map — because every one of them is
# an INPUT to one classification and threading them through a helper object
# would put a second structure between the tree and its verdict.
def census(  # pylint: disable=too-many-locals
    home: Path,
) -> tuple[list[Site], int, Domain | None, str]:
    """Every POSITION `state` binding in the scan root, classified. By SHAPE."""
    root = home / SCAN_ROOT
    if not root.is_dir():
        return [], 0, None, f"no scan root at {SCAN_ROOT} under {home}"
    enum_name, members, complaint = _enum_domain(home)
    if complaint:
        return [], 0, None, complaint
    state_values = frozenset(members.values())
    types, modules, _ = _position_types(home, enum_name, state_values)
    domain = Domain(
        enum_name=enum_name,
        open_names=frozenset({OPEN_MEMBER}),
        open_values=frozenset({members[OPEN_MEMBER]}),
        member_names=frozenset(members),
        state_values=state_values,
        types=types,
        modules=modules,
    )
    if not types:
        return (
            [],
            0,
            domain,
            (
                f"no class in {SCAN_ROOT} declares a `state` field carrying "
                f"{enum_name}; the census has no position-state slot to look at"
            ),
        )

    sites: list[Site] = []
    scanned = 0
    for path in sorted(root.rglob("*.py")):
        rel = str(path.relative_to(home))
        if any(part in f"/{rel}" for part in EXCLUDED_PARTS):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError) as exc:
            return [], scanned, domain, f"cannot parse {rel}: {exc!r}"
        scanned += 1
        env = _alias_env(tree, domain)
        states = _alias_env(tree, domain, any_state=True)
        lines = text.splitlines()
        enclosing = _enclosing(tree)
        for lineno, value in _state_bindings(tree, domain, rel in domain.modules, env):
            sites.append(
                Site(
                    module=rel,
                    lineno=lineno,
                    function=enclosing.get(lineno, "<module>"),
                    kind=_classify(value, env, domain, states),
                    source=(
                        lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
                    ),
                )
            )
    return sites, scanned, domain, ""


# --------------------------------------------------------------------------
# ARM CENSUS — the derived set equals the accepted set.
# --------------------------------------------------------------------------


def arm_census(sites: list[Site]) -> tuple[list[tuple[str, str]], str]:
    """Findings, plus the ONE reason the census cannot be judged at all."""
    unclassifiable = [s for s in sites if s.kind == UNCLASSIFIABLE]
    if unclassifiable:
        first = unclassifiable[0]
        return [], (
            f"{first.module}:{first.lineno} in {first.function} binds "
            f"`state` to an expression this derivation cannot classify as "
            f"originating or reproducing OPEN: {first.source!r}. A census that "
            f"silently dropped it would be exactly how a premature-OPEN path "
            f"stays invisible, so the verdict is CANNOT_MEASURE "
            f"({len(unclassifiable)} such site(s))"
        )

    findings: list[tuple[str, str]] = []
    originators = [s for s in sites if s.kind == ORIGINATOR]
    derived = {(s.module, s.function) for s in originators}
    accepted = set(_ACCEPTED_KEYS)

    for module, function in sorted(derived - accepted):
        site = next(
            s for s in originators if (s.module, s.function) == (module, function)
        )
        findings.append(
            (
                f"{module}:{site.lineno}",
                (
                    f"UNDECLARED OPEN-SETTER in {function}: {site.source!r}. This "
                    f"site ORIGINATES the OPEN position state and no accepted "
                    f"row says a confirmed fill is required to reach it. If it "
                    f"can run on a placement ack it is a PHANTOM POSITION — "
                    f"committed margin, sizing math and a protective stop for "
                    f"size that does not exist at the venue (§4, §2A). Prove it "
                    f"requires a confirmed fill and add it to ACCEPTED, or "
                    f"remove it"
                ),
            )
        )
    for module, function in sorted(accepted - derived):
        findings.append(
            (
                f"{module}::{function}",
                (
                    "ACCEPTED OPEN-SETTER HAS VANISHED: this gate's table says "
                    f"{function} originates OPEN behind "
                    f"{_ACCEPTED_KEYS[(module, function)].gate!r} and the census "
                    "no longer finds it. Either the site moved (re-key the row) "
                    "or the OPEN transition was removed, which is the "
                    "'confirmed fill never reaches OPEN' direction and leaves a "
                    "real position unprotected"
                ),
            )
        )
    return findings, ""


# --------------------------------------------------------------------------
# ARM GATES — each accepted originator's confirmed-fill precondition, re-derived.
# --------------------------------------------------------------------------


def _func(tree: ast.Module, qualname: str) -> ast.AST | None:
    """The FunctionDef for a dotted qualified name, or None."""
    parts = qualname.split(".")

    def find(node: ast.AST, rest: list[str]) -> ast.AST | None:
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and child.name == rest[0]
            ):
                if len(rest) == 1:
                    return child
                return find(child, rest[1:])
        return None

    return find(tree, parts)


def _calls_named(node: ast.AST, name: str) -> bool:
    """Does this subtree call something whose final attribute is `name`?"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == name:
                return True
            if isinstance(func, ast.Name) and func.id == name:
                return True
    return False


def _gate_row_only_from_on_fill(tree: ast.Module) -> str:
    """`_row` is called only from `on_fill`, and `on_fill` ingests first."""
    callers = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "_row"
                ):
                    callers.append(node.name)
    if callers != ["on_fill"]:
        return (
            f"`PositionOriginWriter._row` — the §3 row that carries "
            f"`state=PositionState.OPEN` — is now reached from {callers or []} "
            f"rather than from `on_fill` alone. Any caller that is not handed a "
            f"CONFIRMED ExecutionReport is a premature-OPEN path (§4)"
        )
    on_fill = _func(tree, "PositionOriginWriter.on_fill")
    if on_fill is None:
        return "`PositionOriginWriter.on_fill` is gone; the origin write has no known entry"
    if not _calls_named(on_fill, "ingest"):
        return (
            "`PositionOriginWriter.on_fill` no longer hands the report to the "
            "execution ledger (`ingest`), so the OPEN row it publishes is no "
            "longer derived from a confirmed, deduplicated fill (§4: position "
            "state derives from cumulative fills)"
        )
    return ""


def _gate_handler_bound_to_filled_event(tree: ast.Module) -> str:
    """`_on_fill` is the `_HANDLERS` value for `EVENT_FILLED`, and only that."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "_HANDLERS" for t in node.targets
        ):
            continue
        mapping = node.value
        if not isinstance(mapping, ast.Dict):
            return (
                "`_HANDLERS` is no longer a literal dict; the event->handler "
                "binding cannot be read"
            )
        # `ast.iter_fields` rather than `mapping.keys` / `mapping.values`:
        # `check_uncalled_entry_points` resolves a public entry point by RECEIVER
        # TYPE, and a bare `.keys` on an expression it cannot type moves a real
        # finding (`freshness.py::SourceMonotonicGuard.keys`) from `uncalled` to
        # `cannot_resolve` — this gate would be eroding another gate's ratchet as
        # a side effect of how it spells an AST read. Measured, ARC 049.
        fields = dict(ast.iter_fields(mapping))
        bound = {
            (k.id if isinstance(k, ast.Name) else _label(k)): (
                v.id if isinstance(v, ast.Name) else _label(v)
            )
            for k, v in zip(fields["keys"], fields["values"])
        }
        keys_for_on_fill = [k for k, v in bound.items() if v == "_on_fill"]
        if keys_for_on_fill != ["EVENT_FILLED"]:
            return (
                f"`_on_fill` — which sets the projection state to STATE_OPEN — "
                f"is bound in `_HANDLERS` to {keys_for_on_fill or []} rather "
                f"than to EVENT_FILLED alone. A non-fill event reaching it "
                f"would open a position in §9's projection with no fill behind "
                f"it (§4)"
            )
        return ""
    return "`_HANDLERS` not found in the projection; the event->handler binding cannot be read"


def _gate_guarded_by_zero_fill_refusal(
    tree: ast.Module, qualname: str, domain: Domain
) -> str:
    """The function refuses, before touching state, when `qty_filled == 0`."""
    func = _func(tree, qualname)
    if func is None:
        return f"`{qualname}` is gone from the projection"
    open_lines = [
        lineno
        for lineno, value in _state_bindings(
            func, domain, True, _alias_env(tree, domain)
        )
        if _literal_open(value, domain)
        or (isinstance(value, ast.Name) and value.id in _alias_env(tree, domain))
    ]
    if not open_lines:
        return ""
    guard_lines = [
        node.lineno
        for node in ast.walk(func)
        if isinstance(node, ast.If)
        and any(
            isinstance(cmp_node, ast.Compare)
            and isinstance(cmp_node.left, ast.Attribute)
            and cmp_node.left.attr == "qty_filled"
            and any(isinstance(op, ast.Eq) for op in cmp_node.ops)
            and any(
                isinstance(c, ast.Constant) and c.value == 0
                for c in cmp_node.comparators
            )
            for cmp_node in ast.walk(node.test)
        )
        and any(isinstance(stmt, ast.Return) for stmt in ast.walk(node))
    ]
    if not guard_lines:
        return (
            f"`{qualname}` sets the projection state to STATE_OPEN at line(s) "
            f"{open_lines} with no `qty_filled == 0` refusal in front of it. "
            f"Without that guard a cancel or an exit for a trade that NEVER "
            f"FILLED opens a position in §9's projection — a phantom the "
            f"cold-start reconciler would then believe (§4)"
        )
    if min(guard_lines) > min(open_lines):
        return (
            f"`{qualname}`'s `qty_filled == 0` refusal is at line "
            f"{min(guard_lines)}, AFTER the STATE_OPEN transition at line "
            f"{min(open_lines)}. A guard that runs second does not guard"
        )
    return ""


def _gate_fold_emits_only_filled_builds(tree: ast.Module) -> str:
    """`fold_events` emits a position only for a build with `qty_filled > 0`."""
    func = _func(tree, "fold_events")
    if func is None:
        return "`fold_events` is gone; nothing constrains what reaches the projection table"
    for node in ast.walk(func):
        if not isinstance(node, ast.comprehension):
            continue
        for cond in node.ifs:
            for cmp_node in ast.walk(cond):
                if (
                    isinstance(cmp_node, ast.Compare)
                    and isinstance(cmp_node.left, ast.Attribute)
                    and cmp_node.left.attr == "qty_filled"
                    and any(isinstance(op, ast.Gt) for op in cmp_node.ops)
                ):
                    return ""
    return (
        "`fold_events` no longer filters its emitted positions to builds with "
        "`qty_filled > 0`. `position_rows` stamps EVERY stored row "
        "`PositionState.OPEN`, so a trade that only ever saw an ack, a cancel "
        "or an exit would reach cold-start reconciliation as an OPEN position "
        "that never existed (§4)"
    )


def arm_gates(home: Path, domain: Domain) -> list[tuple[str, str]]:
    """Every accepted originator's precondition, re-derived from the AST."""
    findings: list[tuple[str, str]] = []
    trees: dict[str, ast.Module] = {}
    for accepted in ACCEPTED:
        if accepted.module not in trees:
            path = home / accepted.module
            try:
                trees[accepted.module] = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError) as exc:
                findings.append((accepted.module, f"cannot parse: {exc!r}"))
                continue
        tree = trees.get(accepted.module)
        if tree is None:
            continue
        if accepted.gate == "row_only_from_on_fill":
            why = _gate_row_only_from_on_fill(tree)
        elif accepted.gate == "handler_bound_to_filled_event":
            why = _gate_handler_bound_to_filled_event(tree)
        elif accepted.gate == "guarded_by_zero_fill_refusal":
            why = _gate_guarded_by_zero_fill_refusal(tree, accepted.function, domain)
        elif accepted.gate == "fold_emits_only_filled_builds":
            why = _gate_fold_emits_only_filled_builds(tree)
        else:  # pragma: no cover - unreachable while ACCEPTED is a literal
            why = f"no derivation implements the gate {accepted.gate!r}"
        if why:
            findings.append((f"{accepted.module}::{accepted.function}", why))
    return findings


# --------------------------------------------------------------------------
# The drive. Real objects, out of the tree under judgement.
# --------------------------------------------------------------------------

_MODULES = (
    "nixrisk.seam",
    "nixrisk.execution",
    "nixrisk.picture",
    "nixrisk.positions",
    "nixrisk.stops",
    "nixrisk.fills",
    "nixrisk.reservations",
    "nixrisk.degraded",
    "nixrisk.wal",
    "nixrisk.projection",
)

SYMBOL = "MESU6"
TICK = 0.25
MARGIN = 1000.0
FILL_PRICE = 5000.0


@dataclasses.dataclass
class Loaded:
    """The subject modules, resolved out of the tree under judgement."""

    mods: dict[str, ModuleType]
    home: Path

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - convenience
        raise AttributeError(item)


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the risk package out of `home`, or say why not. Restores state."""
    scripts = str(home / SCAN_ROOT)
    if not (home / SCAN_ROOT / PACKAGE / "__init__.py").is_file():
        return None, f"no {PACKAGE} package under {home / SCAN_ROOT}"
    saved_path = list(sys.path)
    saved_mods = {k: v for k, v in sys.modules.items() if k.split(".")[0] == PACKAGE}
    for name in list(sys.modules):
        if name.split(".")[0] == PACKAGE:
            del sys.modules[name]
    sys.path.insert(0, scripts)
    try:
        mods = {name: importlib.import_module(name) for name in _MODULES}
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        sys.path[:] = saved_path
        sys.modules.update(saved_mods)
        return (
            None,
            f"cannot import {PACKAGE} out of {home}: {type(exc).__name__}: {exc}",
        )
    finally:
        sys.path[:] = saved_path
    # D3.124 — provenance. `_preamble` leaves the LIVE scripts/ on sys.path, so
    # a missing tree falls through to this checkout and the gate would report on
    # a tree it never read.
    for name, mod in mods.items():
        origin = getattr(mod, "__file__", None)
        if origin is None or not str(Path(origin).resolve()).startswith(
            str(home.resolve())
        ):
            sys.modules.update(saved_mods)
            return None, (
                f"{name} resolved to {origin!r}, which is OUTSIDE the tree under "
                f"judgement ({home}) — the verdict would be about another tree"
            )
    return Loaded(mods=mods, home=home), ""


def unload(saved: dict[str, ModuleType]) -> None:
    """Put `sys.modules` back the way it was found."""
    for name in list(sys.modules):
        if name.split(".")[0] == PACKAGE:
            del sys.modules[name]
    sys.modules.update(saved)


class Rig:  # pylint: disable=too-many-instance-attributes
    """§3's entry seam: approval book, reservations, stops, ledger, writer, sink.

    Fourteen attributes would be a smell in production code; here every one is a
    real component of the seam that some assertion below reads. The claim is
    that NONE of them reads OPEN off an ack, so dropping one to satisfy a count
    would drop a surface from the measurement.
    """

    def __init__(self, loaded: Loaded, tmp: Path) -> None:
        mods = loaded.mods
        self.seam = mods["nixrisk.seam"]
        self.execution = mods["nixrisk.execution"]
        self.picture_mod = mods["nixrisk.picture"]
        self.picture = mods["nixrisk.picture"].FinancialPictureBook(
            balance=50_000.0,
            deployable_fraction=0.70,
        )
        self.picture.commit(margin_per_contract={SYMBOL: MARGIN})
        self.wal = mods["nixrisk.wal"].Plane1Wal(str(tmp / "plane1.wal"))
        self.plane1 = mods["nixrisk.degraded"].Plane1Enqueuer(self.wal)
        self.reservations = mods["nixrisk.reservations"].ReservationLedger(self.plane1)
        self.orders = mods["nixrisk.fills"].ApprovedOrderBook()
        self.stops = mods["nixrisk.stops"].StopBook({SYMBOL: TICK})
        self.ledger = mods["nixrisk.execution"].ExecutionLedger()
        self.origins = mods["nixrisk.positions"].EntryOrderOrigins()
        self.writer = mods["nixrisk.positions"].PositionOriginWriter(
            picture=self.picture,
            ledger=self.ledger,
            stops=self.stops,
            origins=self.origins,
        )
        self.handler = mods["nixrisk.fills"].FillHandler(
            orders=self.orders,
            stops=self.stops,
            remainder=mods["nixrisk.fills"].IocRemainder(
                reservations=self.reservations,
                cancels=_NullCancel(),
                clock=time.time,
            ),
            writer=self.writer,
        )
        self.sink = mods["nixrisk.fills"].LimiterFillSink(
            handler=self.handler, orders=self.orders, clock=time.time
        )

    def order(self, coid: str, qty: int = 2):
        """One §2:38 approved order shape."""
        return self.seam.ProposedOrder(
            client_order_id=coid,
            strategy_id="strat-1",
            symbol=SYMBOL,
            side=self.seam.Side.LONG,
            qty=qty,
            margin_per_contract=MARGIN,
            stop_ticks=20,
            stop_mode=self.seam.StopMode.FIXED,
            signal_ts=1000.0,
        )

    def ack(self, order):
        """§2A's PLACEMENT ACK: approved, joined, reserved, WORKING. No fill."""
        self.orders.record(order)
        self.origins.record(order)
        taken = self.reservations.take(order, time.time())
        self.picture.commit(sum_reservations=self.reservations.total_reserved())
        return taken

    def fill(self, coid: str, exec_id: str, qty: int, cumulative: int) -> None:
        """One §2A `on_fill`, through the production entry point."""
        self.sink.on_fill(coid, exec_id, SYMBOL, qty, FILL_PRICE, cumulative)

    def surfaces(self) -> dict[str, Any]:
        """Every surface a consumer could read as "this position is open"."""
        picture = self.picture.current()
        state_open = self.seam.PositionState.OPEN
        return {
            "open_trades": sorted(
                row.trade_id for row in picture.positions if row.state is state_open
            ),
            "all_rows": sorted(
                f"{row.trade_id}:{row.state.value}:{row.size}"
                for row in picture.positions
            ),
            "sum_open_margin": picture.sum_open_margin,
            "sum_reservations": picture.sum_reservations,
            "reservations_outstanding": sorted(
                r.client_order_id for r in self.reservations.outstanding()
            ),
            "approved": sorted(self.orders.approved()),
            "armed_stops": sorted(s.client_order_id for s in self.stops.stops()),
            "ledger_net_qty": self.ledger.position(SYMBOL).net_qty,
        }


class _NullCancel:  # pylint: disable=too-few-public-methods
    """The venue cancel port. The remainder path calls it; nothing asserts on it."""

    def cancel_order(self, client_order_id: str) -> None:
        """Accept and drop — this gate never asks a broker anything."""


# --------------------------------------------------------------------------
# ARM DRIVEN A — NO PREMATURE OPEN (the phantom direction).
# --------------------------------------------------------------------------


def arm_no_premature_open(rig: Rig) -> tuple[list[tuple[str, str]], str]:
    """An acked, working, unfilled order is PENDING — never OPEN. Non-vacuous."""
    findings: list[tuple[str, str]] = []
    order = rig.order("c-ack-1")
    taken = rig.ack(order)
    acked = rig.surfaces()

    # NON-VACUITY FIRST (§7.12 answer 3): if the order was not really placed,
    # "nothing is open" is a statement about an empty rig.
    if acked["approved"] != ["c-ack-1"]:
        return [], (
            "the ack drive did not record an approved order, so there is no "
            "genuinely PENDING order and 'the ack did not open a position' "
            "would be vacuous"
        )
    if acked["reservations_outstanding"] != ["c-ack-1"]:
        return [], (
            "the ack drive left no outstanding reservation; §3 takes margin AT "
            "APPROVAL, so without it the order is not in the state whose "
            "premature promotion to OPEN this arm exists to refuse"
        )
    if acked["sum_reservations"] < MIN_RESERVED_ON_ACK:
        return [], (
            f"the ack reserved {acked['sum_reservations']} of margin, below the "
            f"{MIN_RESERVED_ON_ACK} floor — nothing was really committed"
        )
    if rig.origins.origin_for_order("c-ack-1") is None:
        return [], (
            "the ack minted no trade<->order join, so §3's table has no key to "
            "publish a row under and 'no row was published' proves nothing"
        )

    if acked["open_trades"]:
        findings.append(
            (
                "picture.positions",
                (
                    f"PHANTOM POSITION: a placement ack with NO FILL left "
                    f"{acked['open_trades']} reading OPEN in §3's published "
                    f"table. §4 asserts OPEN only on broker fill confirmation. "
                    f"Committed margin and a protective stop now correspond to "
                    f"size that does not exist at the venue"
                ),
            )
        )
    if acked["all_rows"]:
        findings.append(
            (
                "picture.positions",
                (
                    f"an ack published position row(s) {acked['all_rows']} into "
                    f"§3's table. The two-phase entry state for an acked, "
                    f"unfilled order is carried by the RESERVATION, not by a "
                    f"published row; a row here is where an optimistic open "
                    f"first appears (§4, §3:159)"
                ),
            )
        )
    if acked["sum_open_margin"] != 0.0:
        findings.append(
            (
                "picture.sum_open_margin",
                (
                    f"an ack moved Σ OPEN margin to {acked['sum_open_margin']}. "
                    f"§3 counts an unfilled order under Σ RESERVATIONS; open "
                    f"margin for an unfilled order is the phantom in the "
                    f"capital arithmetic every Phase-B rule is evaluated against"
                ),
            )
        )
    if acked["ledger_net_qty"] != 0:
        findings.append(
            (
                "ExecutionLedger.position",
                (
                    f"an ack moved the execution ledger to net "
                    f"{acked['ledger_net_qty']} — §2A says `place_order` returns "
                    f"an ack, NEVER a fill"
                ),
            )
        )

    # WATCH PAST THE TICK (§0a): not-yet-OPEN on the ack is not proof the state
    # will not wrongly open on the NEXT event. Drive §3's terminal NON-FILL
    # outcome — the venue rejects, the reservation is released under REJECT —
    # and read every surface again. §14: uncertainty resolves toward FLAT.
    rig.reservations.release(
        taken.reservation_id, rig.seam.TerminalPath.REJECT, time.time()
    )
    rig.picture.commit(sum_reservations=rig.reservations.total_reserved())
    rejected = rig.surfaces()
    if rejected["reservations_outstanding"]:
        return findings, (
            "the reject drive left the reservation outstanding, so the second "
            "event never landed and 'a reject did not open a position' would be "
            "a statement about an event that did not happen"
        )
    if rejected["open_trades"] or rejected["all_rows"]:
        findings.append(
            (
                "picture.positions",
                (
                    f"a REJECTED order reached §3's table as "
                    f"{rejected['all_rows']}. §4 resolves a rejected placement "
                    f"toward FLAT and §14 resolves uncertainty the same way; "
                    f"nothing about a reject may produce an open position"
                ),
            )
        )
    if rejected["sum_open_margin"] != 0.0:
        findings.append(
            (
                "picture.sum_open_margin",
                (
                    f"a rejected order left Σ open margin at "
                    f"{rejected['sum_open_margin']} — capital committed to a "
                    f"position that was never placed"
                ),
            )
        )
    return findings, ""


# --------------------------------------------------------------------------
# ARM DRIVEN B — OPEN ON CONFIRMED FILL (the unprotected direction).
# --------------------------------------------------------------------------


def arm_open_on_confirmed_fill(rig: Rig) -> tuple[list[tuple[str, str]], str]:
    """A confirmed fill reaches OPEN, exactly once, from cumulative fills."""
    findings: list[tuple[str, str]] = []
    order = rig.order("c-fill-1", qty=5)
    rig.ack(order)
    before = rig.surfaces()
    if before["open_trades"]:
        return [], (
            "the fill arm's rig already held an OPEN trade before any fill was "
            "delivered, so 'the fill opened it' cannot be read off this drive"
        )

    rig.fill("c-fill-1", "e-1", 2, 2)
    first = rig.surfaces()
    if first["ledger_net_qty"] != 2:
        return [], (
            f"the execution ledger reads net {first['ledger_net_qty']} after a "
            f"2-lot confirmed fill, so the fill did not genuinely arrive and "
            f"the state verdict below would be vacuous"
        )
    if first["open_trades"] != ["c-fill-1"]:
        findings.append(
            (
                "picture.positions",
                (
                    f"UNPROTECTED REAL POSITION: a CONFIRMED 2-lot fill left "
                    f"§3's table reading {first['all_rows'] or 'FLAT'} — the "
                    f"execution ledger holds net {first['ledger_net_qty']} and "
                    f"the published table does not. §7:501 prices bucket "
                    f"exposure from that table, so a real position priced at "
                    f"zero makes the correlation cap ADMIT MORE (D3.136)"
                ),
            )
        )
    if first["sum_open_margin"] <= 0.0:
        findings.append(
            (
                "picture.sum_open_margin",
                (
                    f"a confirmed fill left Σ open margin at "
                    f"{first['sum_open_margin']}; the position converted from a "
                    f"reservation to open margin at the fill (§3's lifecycle) "
                    f"and the capital picture has not followed it"
                ),
            )
        )

    # IDEMPOTENCE: the SAME (order_id, exec_id) again must not double-open.
    rig.fill("c-fill-1", "e-1", 2, 2)
    again = rig.surfaces()
    if again["ledger_net_qty"] != first["ledger_net_qty"]:
        findings.append(
            (
                "ExecutionLedger.position",
                (
                    f"a RE-DELIVERED execution report (same order_id/exec_id) "
                    f"moved the position from {first['ledger_net_qty']} to "
                    f"{again['ledger_net_qty']}. §4 deduplicates by that pair; "
                    f"a reconnect replay would double the position"
                ),
            )
        )
    if again["all_rows"] != first["all_rows"]:
        findings.append(
            (
                "picture.positions",
                (
                    f"a RE-DELIVERED fill changed §3's rows from "
                    f"{first['all_rows']} to {again['all_rows']} — the published "
                    f"state is not derived from the unique fill set (§4)"
                ),
            )
        )

    # PARTIAL ACCUMULATION: the remainder arrives; size is cumulative and the
    # state was already OPEN from the FIRST confirmed fill.
    rig.fill("c-fill-1", "e-2", 3, 5)
    whole = rig.surfaces()
    if whole["ledger_net_qty"] != 5:
        findings.append(
            (
                "ExecutionLedger.position",
                (
                    f"after 2 + 3 confirmed lots the ledger reads "
                    f"{whole['ledger_net_qty']}, not 5 — position does not "
                    f"derive from CUMULATIVE fills (§4)"
                ),
            )
        )
    if whole["all_rows"] != ["c-fill-1:open:5"]:
        findings.append(
            (
                "picture.positions",
                (
                    f"after 2 + 3 confirmed lots §3's table reads "
                    f"{whole['all_rows']}, not the single cumulative OPEN row "
                    f"['c-fill-1:open:5']. §4 sets the position to the ACTUAL "
                    f"FILLED QTY under one trade_id"
                ),
            )
        )
    return findings, ""


# --------------------------------------------------------------------------
# ARM FOLD — §9's projection opens on a `filled` event and on nothing else.
# --------------------------------------------------------------------------


def arm_fold(loaded: Loaded) -> tuple[list[tuple[str, str]], str]:
    """An ack-only Plane-1 log folds to ZERO positions; a fill folds to one."""
    projection = loaded.mods["nixrisk.projection"]
    findings: list[tuple[str, str]] = []

    def event(event_id: int, event_type: str, **payload: Any):
        return projection.LogEvent(
            event_id=event_id,
            wal_seq=event_id,
            occurred_at="2026-08-20T00:00:00Z",
            event_type=event_type,
            strategy_id="strat-1",
            trade_id="t-1",
            reason="",
            symbol=SYMBOL,
            natural_key="",
            payload=payload,
        )

    ack_only = projection.fold_events(
        [
            event(1, "reservation_taken", margin=2000.0),
            event(2, "accepted", qty=2),
        ]
    )
    if ack_only.position_events != 0:
        findings.append(
            (
                "scripts/nixrisk/projection.py::fold_events",
                (
                    f"an ack-only log produced {ack_only.position_events} "
                    f"POSITION event(s); §9's `accepted` is position-neutral and "
                    f"a fold that treats it otherwise opens a position on a "
                    f"placement ack (§4)"
                ),
            )
        )
    if ack_only.positions:
        findings.append(
            (
                "scripts/nixrisk/projection.py::fold_events",
                (
                    f"PHANTOM IN THE PROJECTION: a log holding only a "
                    f"reservation and an ACK folded to "
                    f"{[p.trade_id + ':' + p.state for p in ack_only.positions]}. "
                    f"Cold-start reconciliation reads this table as the true "
                    f"open-position set (§4)"
                ),
            )
        )

    filled = projection.fold_events(
        [
            event(1, "accepted", qty=2),
            event(
                2,
                "filled",
                qty=2,
                qty_requested=2,
                price="5000.0",
                side="buy",
                stop_distance="20",
            ),
        ]
    )
    if len(filled.positions) != 1 or filled.positions[0].state != "open":
        findings.append(
            (
                "scripts/nixrisk/projection.py::fold_events",
                (
                    f"a CONFIRMED `filled` event folded to "
                    f"{[(p.trade_id, p.state) for p in filled.positions]} rather "
                    f"than one `open` position. A real fill the projection does "
                    f"not open is a position cold-start reconciliation will not "
                    f"know it holds (§4)"
                ),
            )
        )

    exit_first = projection.fold_events(
        [event(1, "closed", qty=2)],
    )
    if exit_first.positions:
        findings.append(
            (
                "scripts/nixrisk/projection.py::fold_events",
                (
                    "an EXIT for a trade that never filled produced a position "
                    "row. §4 mints a position at OPEN and OPEN comes from a "
                    "fill; an exit before any open is an anomaly, not a row"
                ),
            )
        )
    elif not exit_first.anomalies:
        findings.append(
            (
                "scripts/nixrisk/projection.py::fold_events",
                (
                    "an EXIT for a trade that never filled was SILENTLY "
                    "SKIPPED — no position and no anomaly. A fold that ignores "
                    "the event a decision is owed on reports a clean tree"
                ),
            )
        )
    return findings, ""


# --------------------------------------------------------------------------
# Verdict.
# --------------------------------------------------------------------------


def _cannot(detail: str, site: str = "") -> CheckResult:
    return CheckResult(
        name=NAME, status=Status.CANNOT_MEASURE, site=site, detail=detail
    )


def _evidence(sites: list[Site], scanned: int, drives: int) -> str:
    originators = [s for s in sites if s.kind == ORIGINATOR]
    return (
        f"{scanned} module(s) parsed; OPEN-setters by shape: "
        f"{len(originators)} originator(s) "
        f"[{', '.join(sorted({f'{s.module}::{s.function}' for s in originators}))}]; "
        f"{drives} drive(s) on real objects. "
        f"NOT covered: the D3.372 refused-origin-write path (architect-blocked) "
        f"and §4's pending-timeout resolution (I1)"
    )


def _census_floors(sites: list[Site], scanned: int, root: str) -> str:
    """The ONE reason the census is not judgeable, or `""` (doctrine C.4)."""
    if scanned < MIN_MODULES_SCANNED:
        return (
            f"only {scanned} module(s) parsed under {SCAN_ROOT}, below the "
            f"{MIN_MODULES_SCANNED} floor — the scan root is wrong or empty, and "
            f"'no premature-OPEN site' would be a statement about nothing "
            f"({root})"
        )
    originators = [site for site in sites if site.kind == ORIGINATOR]
    if len(originators) < MIN_ORIGINATORS:
        return (
            f"the census found {len(originators)} OPEN-setter(s), below the "
            f"{MIN_ORIGINATORS} floor. A tree with no site that can assert OPEN "
            f"is indistinguishable from a derivation that stopped working, and "
            f"rule 10 forbids certifying the first while the second is live "
            f"({root})"
        )
    return ""


def _drive_arms(loaded: Loaded) -> tuple[list[tuple[str, str]], list[str], int]:
    """Every driven arm, on real objects. Returns (findings, blocked, drives).

    A LATER arm that cannot measure must not erase an EARLIER arm's finding.
    Check-contract rule 4 orders the aggregate Fail > Cannot-measure, and the
    reason is this exact case: PLANT A's phantom makes the ack arm RED and, by
    leaving an OPEN row standing before any fill, makes the fill arm's
    precondition unmeasurable. Returning the refusal would report light-blue
    over a measured phantom — so both travel back and the caller orders them.
    """
    findings: list[tuple[str, str]] = []
    blocked: list[str] = []
    drives = 0
    with tempfile.TemporaryDirectory(prefix="check_two_phase_") as tmp:
        for arm in (arm_no_premature_open, arm_open_on_confirmed_fill):
            found, refused = arm(Rig(loaded, Path(tmp)))
            findings += found
            if refused:
                blocked.append(f"{arm.__name__}: {refused}")
            else:
                drives += 1
        found, refused = arm_fold(loaded)
        findings += found
        if refused:
            blocked.append(f"arm_fold: {refused}")
        else:
            drives += 1
    return findings, blocked, drives


def _verdict(findings: list[tuple[str, str]], blocked: list[str], evidence: str):
    """One reading or one refusal, never both and never neither."""
    if blocked and not findings:
        return _cannot("; ".join(blocked))
    if blocked:
        findings = findings + [
            (
                "arms-not-measured",
                (
                    "and these arms could not be measured on the same tree "
                    "(reported alongside the FAIL rather than instead of it, "
                    "rule 4): " + "; ".join(blocked)
                ),
            )
        ]
    if not findings:
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(site for site, _ in findings),
        evidence=evidence,
        detail="; ".join(f"{site}: {why}" for site, why in findings),
        action=(
            "§4: OPEN is asserted ONLY on broker fill confirmation. Remove the "
            "premature-OPEN path, or restore the confirmed-fill transition, and "
            "re-run"
        ),
    )


def _measure(home: Path) -> CheckResult:
    """The whole measurement, static then driven. Raises nothing it can help."""
    root = str(home / SCAN_ROOT)
    sites, scanned, domain, complaint = census(home)
    if complaint or domain is None:
        return _cannot(complaint, site=root)
    floor = _census_floors(sites, scanned, root)
    if floor:
        return _cannot(floor, site=root)

    findings, refusal = arm_census(sites)
    if refusal:
        return _cannot(refusal, site=root)
    findings += arm_gates(home, domain)

    loaded, why = load(home)
    if loaded is None:
        return _cannot(why, site=root)
    saved = {k: v for k, v in sys.modules.items() if k.split(".")[0] == PACKAGE}
    try:
        driven, blocked, drives = _drive_arms(loaded)
    finally:
        unload(saved)
    return _verdict(findings + driven, blocked, _evidence(sites, scanned, drives))


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove OPEN tracks confirmed fills exactly. Never repairs (CORRECTABLE=False)."""
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
# (§4.2) requires each module be independently runnable, so this block cannot be
# factored into a shared helper without breaking that.
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
