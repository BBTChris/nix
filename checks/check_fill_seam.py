#!/usr/bin/env python3
"""The fill-handler seam declares §4's surface faithfully, and the classes obey it.

ARC 034 / Phase 0.6(b). ONE gate, ONE property (`nix_check_contract.md` §5.5):
*`scripts/nixrisk/fill_seam.py` declares the fill handler's surface faithfully —
the step ORDER, the synchrony, the narrowed ports — and the production classes
that must satisfy those ports actually do.* Six arms serve that single property.

  * **ARM 1 — the step ORDER, read from the IMPORTED module.** `FillStep` must be
    an `enum.IntEnum` and its member VALUES must be strictly increasing in the
    order the seam's own header fixes: `ARM_STOP` < `RELEASE_REMAINDER` <
    `ORIGIN_WRITE`. **The expected order is PARSED out of the seam's numbered
    docstring list, never typed here**, so a reordering of the list and a
    reordering of the values disagree with each other. The values are read off
    the imported enum rather than out of source text, because the source line
    `ORIGIN_WRITE = 3` is what a reader believes and `FillStep.ORIGIN_WRITE.value`
    is what a handler executes. Red if the class stops being an `IntEnum`, if a
    member is missing, or if the values stop increasing.

  * **ARM 2 — every declared verb is SYNCHRONOUS.** No `async def` anywhere in
    the seam. The justification is the seam's own header and it is NOT §12.1's:
    §5 fixes the Limiter as a single-threaded event loop whose serial processing
    *"eliminates fill-vs-tick races by construction"*, and §3's ATOMICITY RULE
    publishes balance and the position table *"as one snapshot — never two
    separate reads"*. `on_fill` performs four state changes that §3 and §4
    require to be one motion; an `async def` anywhere in that sequence is a
    declared suspension point, and a second fill serviced inside it would publish
    a snapshot from between two halves of one fill.

  * **ARM 3 — the seam carries no behaviour.** Same shape as
    `check_sentinel_seam.behaviour_defects`. **The forbidden-import roster bans
    SIDE-EFFECTING STDLIB MODULES ONLY and deliberately not first-party ones**:
    `fill_seam.py` legitimately imports `nixrisk.execution`, `nixrisk.positions`
    and `nixrisk.seam` for its type annotations, and a roster that banned them
    would force the seam to spell its own annotations as strings — trading a real
    property (the seam touches nothing) for a false one (the seam names nothing).

  * **ARM 4 — `StopArmPort` is strictly NARROWER than `seam.StopBookPort`.**
    `StopBookPort`'s verb roster is derived by AST from `scripts/nixrisk/seam.py`
    at run time and is never typed out here. `StopArmPort` must declare exactly
    ONE verb and that verb must be one of `StopBookPort`'s — so gaining `forget`,
    `maintain` or `breached` is red on the cardinality, gaining anything else is
    red on the subset, and declaring the same set is red because a "narrowing"
    that narrows nothing is a second name for the same authority.

  * **ARM 5 — the production classes STRUCTURALLY SATISFY the ports, DRIVEN.**
    The real `nixrisk.stops.StopBook` and `nixrisk.positions.PositionOriginWriter`
    are constructed out of the tree under judgement and held against the
    `runtime_checkable` Protocols with `isinstance`. **`runtime_checkable`
    isinstance checks METHOD NAMES ONLY** — it is blind to parameter names, to
    arity, and to every annotation — so an `isinstance` that returns `True` is
    worth much less than it looks. That exact weakness was measured in ARC 033's
    gates. This arm therefore adds an `inspect.signature` comparison of the
    PARAMETER NAMES, in order, and that comparison is what makes the arm more
    than a name check. Extra parameters on the real method are allowed only when
    they are optional, because an extra REQUIRED parameter is a call the port's
    caller cannot make.

  * **ARM 6 — D3.177's rule has a declared home.** `NON_IDENTITY_MINT_REQUIRED`
    must be `True` and `TradeIdMintPort` must be declared with a `mint` verb.
    **THIS ARM DOES NOT CHECK THE PRODUCTION MINT, WHICH DOES NOT EXIST YET.**
    A green here means the RULE is stated where a later gate can read it. It does
    NOT mean any minting code is non-identity, and it must never be cited as if
    it did: `positions.identity_trade_id` is still the degenerate mint and
    nothing in this gate can see it. The gate that measures a real mint is owed
    work, not work this file has done.

WHAT THIS GATE CANNOT PROVE, stated rather than implied. Five arms read the seam
STATICALLY and one drives two constructors. It cannot prove that any handler
exists, that a handler executes the steps in the declared order, that the
remainder is really released before the row is published, or that a stop is
armed at all — those are behaviours of code built against this seam and they
need their own instrument driving a real handler over a real fill stream (the
shape `check_origin_write` already has one module over). **A green here means the
DECLARATION is faithful and the two named classes fit the two named ports. It
says nothing about whether a fill handler exists or works.**

`debug.md` §7.12 — the standing question, asked at the point this gate was built:
*what would make this pass while measuring nothing?* Five answers, each closed by
a NAMED mechanism rather than by assertion:

  1. *The seam's numbered step list is renamed or reformatted, ARM 1's expected
     order parses to nothing, and an empty order is trivially increasing.* Closed
     by `MIN_ORDERED_STEPS`: fewer than two ordered steps parsed is
     CANNOT_MEASURE, never PASS. Two is the smallest number for which "strictly
     increasing" says anything at all.
  2. *The subject is renamed, or the import falls through to the LIVE repository
     because `checks/_preamble.py` appends the real `scripts/` to `sys.path` and
     never removes it (D3.124), so the gate reports on a tree it never read.*
     Closed twice: an import failure is CANNOT_MEASURE naming the exception, and
     `_provenance` requires every loaded module's `__file__` to lie under the
     tree under judgement with `nixrisk.fill_seam` pinned to the exact file the
     AST arms parse.
  3. *ARM 4's reference roster is read out of the SUBJECT, so the subject can
     widen itself into agreement.* Closed by deriving `StopBookPort`'s verbs from
     `scripts/nixrisk/seam.py` — a DIFFERENT file, frozen at `SEAM_REV 1.1.0`,
     which the fill seam cannot edit in the same motion — and by
     `MIN_STOPBOOK_VERBS`, so a `StopBookPort` that has been gutted is
     CANNOT_MEASURE rather than a subset relation over nothing.
  4. *ARM 5 passes on `isinstance` alone, which compares method NAMES and nothing
     else, so a class whose parameters have drifted satisfies the Protocol and
     fails at the call.* Closed by `_signature_defect`, which compares the
     PARAMETER NAMES in order; and the pairs are not floored but REQUIRED — a
     missing Protocol or a missing class is a defect naming it, never a silently
     shorter loop.
  5. *Every arm inspects and none of them counts, so a gutted seam passes.*
     Closed by `MIN_CALLABLES`, `MIN_DECLARED_VERBS` and `MIN_PORTS`, which are
     floors STRICTLY BELOW today's figures (doctrine C.4) and non-zero. Today's
     tree carries 6 callables, 6 declared verbs and 6 ports against floors of 4,
     4 and 4; ARC 034 / 0.5 measured five of ARC 033's declared floors being
     arithmetic identities like `300 < 100`, and every floor here is written to
     be a real one.
"""

from __future__ import annotations

import ast
import enum
import importlib
import inspect
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text; the only way to
# deduplicate them is a shared helper, which §4.2 forbids.
# pylint: disable=duplicate-code
#
# C0302 (too-many-lines): this gate is over the 1000-line default, and the excess
# is DOCSTRING, not logic — the six arms' reasoning, `debug.md` §7.12's standing
# question with its four named closures, and the per-constant `#:` notes that say
# why each expected value is derived rather than typed.
#
# `nix_check_contract.md` §5.5 makes
# one gate own one property, so splitting this file would either create a second
# gate over half a property or move the reasoning into a module the gate does not
# import — and the reasoning is the part that stops the next author re-opening a
# hole a previous arc closed. `check_limiter_seam` and `check_origin_write` carry
# the same shape for the same reason.
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first: the seam and the frozen `nixrisk/seam.py` are files on
#: disk that no check produces, and the two classes ARM 5 drives are shipped
#: modules, not artifacts a check installs.
DEPENDS_ON: tuple[str, ...] = ()
#: **DECLARED HONESTLY, AND THIS DIVERGES FROM THE ARC BRIEF, WHICH ASKED FOR
#: `()`.** The brief's `()` would be right for a purely static gate; ARM 5 is not
#: static — it IMPORTS `nixrisk` out of `ctx.nix_home` so the conformance is
#: DRIVEN rather than asserted, which means `load()` mutates `sys.path` and
#: `sys.modules` for the duration and restores both. Check contract v2 rule 12
#: says declared claims are checked against OBSERVED ones, so `()` here would be
#: exactly the falsifiable-and-false declaration that rule exists to catch, and
#: every other importing gate on this tree (`check_origin_write`,
#: `check_execution_ledger`, `check_allocator_seam`, ...) declares these two.
#: A gate that lied about its claims to match a brief would be the first thing
#: the resource observer reddened on.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep. Two file reads, an AST parse and two
#: constructor calls over dictionaries.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every arm compares a DECLARATION against something written by a different "
    "hand -- the seam's own numbered step list, the frozen nixrisk/seam.py at "
    "SEAM_REV 1.1.0, and two production classes written without knowledge of "
    "this seam. An instrument empowered to edit either side into agreement "
    "would be manufacturing its own green, and ARM 4's subject is an AUTHORITY "
    "NARROWING: a self-correcting gate there could widen StopArmPort until the "
    "fill handler could forget a stop or fire an exit from inside a fill, which "
    "is the very thing the narrowing exists to make structurally impossible."
)
#: Genuinely MEASURED: every byte of the fill seam is parsed, its enum and its
#: module constant are read off the IMPORTED module, and two of its ports are
#: held against real constructed objects. `scripts/nixrisk/seam.py` is READ as
#: ARM 4's reference side and is `check_limiter_seam`'s subject, not this one's.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/fill_seam.py",)

NAME = "check_fill_seam"

SEAM = "scripts/nixrisk/fill_seam.py"
#: ARM 4's REFERENCE side, and a different file on purpose -- see §7.12 note 3.
STOP_SEAM = "scripts/nixrisk/seam.py"
PACKAGE = "nixrisk"
MODULE = "nixrisk.fill_seam"
_MODULES = (
    MODULE,
    "nixrisk.seam",
    "nixrisk.stops",
    "nixrisk.positions",
    "nixrisk.picture",
    "nixrisk.execution",
)

#: ARM 1's expected side: the seam's own numbered list of steps, e.g.
#: "  1. `FillStep.ARM_STOP` — ...". **Parsed, never typed.** The docstring is
#: the DECLARATION and the enum is the SUBJECT; they are written by different
#: acts and drift apart in exactly the way that matters, which is the same
#: reasoning `check_limiter_seam` ARM 3 carries for its sync/async declaration.
_ORDERED_STEP = re.compile(
    r"^\s*(?P<rank>\d+)\.\s+`FillStep\.(?P<member>[A-Z_]+)`", re.MULTILINE
)

#: The class whose members ARM 1 orders, and the ports ARM 4 and ARM 6 police.
_STEP_ENUM = "FillStep"
_STOP_ARM_PORT = "StopArmPort"
_STOP_BOOK_PORT = "StopBookPort"
_MINT_PORT = "TradeIdMintPort"
_MINT_VERB = "mint"
_MINT_RULE = "NON_IDENTITY_MINT_REQUIRED"

#: ARM 3. Names whose presence in a seam is behaviour by construction. Same
#: roster as `check_limiter_seam` and `check_sentinel_seam`, and the duplication
#: is deliberate: §4.2 forbids the shared helper that would deduplicate it.
_FORBIDDEN_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "print", "input"}
)
#: **SIDE-EFFECTING STDLIB ONLY. First-party imports are NOT banned here, and
#: that is a reasoned narrowing rather than an oversight.** `fill_seam.py`
#: imports `nixrisk.execution`, `nixrisk.positions` and `nixrisk.seam` to spell
#: the types its ports take and return; banning them would force those
#: annotations into strings and trade the real property (the seam reaches
#: nothing outside the interpreter) for a false one (the seam may not NAME the
#: types it declares over). `asyncio` is on the roster and ARM 2 covers the same
#: ground from the other side: one bans the import, the other bans the keyword.
_FORBIDDEN_IMPORTS = frozenset(
    {"os", "subprocess", "socket", "zmq", "threading", "asyncio", "time", "json"}
)

#: ARM 5's roster: `(port, module attribute, class, why this pair)`. **This IS a
#: constant in the gate, unlike ARM 1's and ARM 4's reference sides, and the
#: difference is stated rather than glossed.** The seam names the satisfying
#: classes only in prose ("Satisfied by `nixrisk.stops.StopBook.arm`"), and
#: deriving the pairing from that prose would let a docstring edit retarget the
#: gate at a class that happens to fit. The pairing is the ARCHITECTURAL claim;
#: it is written here so that changing it is a diff on the instrument.
_CONFORMANCE: tuple[tuple[str, str, str, str], ...] = (
    (
        _STOP_ARM_PORT,
        "stops",
        "StopBook",
        (
            "§4 -- the distance->price conversion at confirmed fill lives in the "
            "stop book, and the fill handler consumes exactly one verb of it"
        ),
    ),
    (
        "OriginWritePort",
        "positions",
        "PositionOriginWriter",
        (
            "§3 -- the origin write publishes the row whose stop_distance §7:501 "
            "prices bucket exposure from"
        ),
    ),
)

#: The instrument symbol ARM 5's two constructors are fed. An arbitrary but real
#: contract spelling; nothing in the gate reads a figure back out of it.
_SYMBOL = "ESZ6"
_TICK = 0.25
_MARGIN = 500.0
_BALANCE = 250_000.0
_FRACTION = 0.70

# --------------------------------------------------------------------------
# NON-VACUITY FLOORS (`debug.md` §7.12). **Every one is STRICTLY BELOW today's
# figure and non-zero.** Today the seam carries 3 ordered steps, 6 callables, 6
# declared verbs and 6 ports, and `nixrisk/seam.py`'s `StopBookPort` carries 4
# verbs. Doctrine C.4: a threshold set to today's number is an anchor that moves
# and discriminates nothing; ARC 034 / 0.5 measured five declared floors in ARC
# 033's gates that were arithmetic identities, so each figure below is written
# with the number it sits under.
# --------------------------------------------------------------------------

#: Ordered steps parsed from the seam's numbered list. Today 3. Two is the
#: smallest count for which "strictly increasing" is a statement about anything.
MIN_ORDERED_STEPS = 2
#: Callables classified by ARM 3. Today 6. A seam this small was gutted, and
#: ARM 3 over an empty file is universal agreement.
MIN_CALLABLES = 4
#: Verbs ARM 2 held against the synchrony rule. Today 6. ARM 2 over no verbs
#: proves nothing about synchrony.
MIN_DECLARED_VERBS = 4
#: `Protocol` classes declared in the seam. Today 6. Below this the seam has
#: stopped being the surface the handler consumes.
MIN_PORTS = 4
#: Verbs on `nixrisk/seam.py`'s `StopBookPort`, ARM 4's reference side. Today 4.
#: A proper-subset relation against a gutted superset proves nothing.
MIN_STOPBOOK_VERBS = 3


class SeamReading(NamedTuple):
    """What one run actually observed. Every field lands in the evidence."""

    step_order: tuple[str, ...]
    step_values: tuple[int, ...]
    callables: int
    verbs: int
    ports: int
    arm_verbs: tuple[str, ...]
    stopbook_verbs: tuple[str, ...]
    conformance: tuple[str, ...]
    mint_rule: object


class Loaded(NamedTuple):
    """The subject and the collaborators, imported out of the tree under test."""

    fill_seam: ModuleType
    seam: ModuleType
    stops: ModuleType
    positions: ModuleType
    picture: ModuleType
    execution: ModuleType


def _cannot_measure(detail: str) -> CheckResult:
    """Doctrine B.2: an unread subject is CANNOT_MEASURE, never PASS."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# --------------------------------------------------------------------------
# LOADING — the subject comes out of the tree under test, never out of this one
# --------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    """Drop every `nixrisk*` module, restoring whatever was there before."""
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def _provenance(loaded: Loaded, home: Path) -> str:
    """Did every loaded module really come OUT OF `home`? MEASURED, not assumed.

    D3.124: `checks/_preamble.py` appends the REAL `scripts/` to `sys.path` and
    never removes it, so an import against a tree lacking the subject resolves
    against the live repository and the gate measures a tree other than the one
    it reports on. The SUBJECT is pinned harder than the collaborators, because
    ARMs 2, 3, 4 and 6 parse `home/SEAM` from disk while ARM 1 reads the
    IMPORTED enum: those two halves must be the same FILE, not merely two files
    under one root.
    """
    root = (home / "scripts").resolve()
    subject = (home / SEAM).resolve()
    for module in loaded:
        origin = getattr(module, "__file__", None)
        if origin is None:
            return f"{module.__name__} has no __file__, so its origin is unknowable"
        resolved = Path(origin).resolve()
        if root != resolved and root not in resolved.parents:
            return (
                f"{module.__name__} was imported from {resolved}, which is NOT "
                f"under {root} — the tree under judgement does not contain the "
                "subject and the import fell through to another tree, so this "
                "gate measured something other than what it is reporting on "
                "(§17: never a PASS)"
            )
        if module.__name__ == MODULE and resolved != subject:
            return (
                f"{MODULE} was imported from {resolved}, not from the {SEAM} "
                f"this gate parses statically ({subject}) — the driven half and "
                "the read half would be judging two different files, so nothing "
                "was measured about either (§17: never a PASS)"
            )
    return ""


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the subject from `home`, leaving the interpreter as it was found.

    A path-keyed import is what lets a plant live on a `tmp_path` COPY (doctrine
    C.8): the gate drives whichever tree it is pointed at, and the production
    seam is never written.
    """
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    # A tree created after interpreter start is invisible to FileFinder's
    # directory-mtime cache, and the resulting ModuleNotFoundError would report
    # "the subject is unavailable" over a subject that is right there.
    importlib.invalidate_caches()
    try:
        loaded = Loaded(*(importlib.import_module(name) for name in _MODULES))
        complaint = _provenance(loaded, home)
        return (None, complaint) if complaint else (loaded, "")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{SEAM}: cannot import {MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# AST helpers — the shape ARMs 2, 3, 4 and 6 read off the file itself
# --------------------------------------------------------------------------


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    """Classes by name, at any depth."""
    return {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }


def _port_verbs(node: ast.ClassDef) -> tuple[str, ...]:
    """Method names declared on a class, in source order."""
    return tuple(
        stmt.name
        for stmt in node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _protocol_count(classes: dict[str, ast.ClassDef]) -> int:
    """How many classes declare themselves `Protocol`s. The seam's port count."""
    return sum(
        1
        for node in classes.values()
        if any(
            isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases
        )
    )


def _is_declaration_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """ARM 3: is this callable a DECLARATION, or is it behaviour?

    A declaration is a docstring, `...`, `pass`, or a single `return` over the
    function's own arguments and attributes. Anything that branches, loops, calls
    out or touches the world is behaviour.
    """
    body = [
        stmt
        for stmt in node.body
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
    ]
    if not body:
        return ""
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        if isinstance(stmt, ast.Return):
            continue
        return (
            f"{node.name}: body carries {type(stmt).__name__}, which is "
            "behaviour, not a declaration"
        )
    return ""


def _call_defect(node: ast.AST) -> tuple[str, str] | None:
    """A forbidden call, or `None`. Split out of `behaviour_defects` so that
    function stays under the complexity ceiling — the same decomposition
    `check_limiter_seam` uses for the identical arm."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = getattr(func, "id", None) or getattr(func, "attr", None)
    if name in _FORBIDDEN_CALLS:
        return (f"{SEAM}:{node.lineno}", f"calls {name}() — a seam performs no act")
    return None


def _import_defects(node: ast.AST) -> list[tuple[str, str]]:
    """Forbidden imports on one node, in source order. Empty when clean."""
    if not isinstance(node, (ast.Import, ast.ImportFrom)):
        return []
    mod = getattr(node, "module", None) or ""
    names = [mod, *(alias.name for alias in node.names)]
    roots = [candidate.split(".")[0] for candidate in names]
    return [
        (
            f"{SEAM}:{node.lineno}",
            (
                f"imports {root} — a seam declares, it does not act. "
                "First-party imports are deliberately NOT banned "
                "here; this roster is side-effecting stdlib only"
            ),
        )
        for root in roots
        if root in _FORBIDDEN_IMPORTS
    ]


def behaviour_defects(tree: ast.Module) -> tuple[list[tuple[str, str]], int]:
    """ARM 3. Returns `(defects, callables_seen)`."""
    defects: list[tuple[str, str]] = []
    seen = 0
    for node in ast.walk(tree):
        call = _call_defect(node)
        if call is not None:
            defects.append(call)
        defects += _import_defects(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen += 1
            why = _is_declaration_body(node)
            if why:
                defects.append((f"{SEAM}:{node.lineno}", why))
    return defects, seen


def synchrony_defects(tree: ast.Module) -> tuple[list[tuple[str, str]], int]:
    """ARM 2. Every declared verb must be `def`, never `async def`."""
    defects: list[tuple[str, str]] = []
    verbs = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            verbs += 1
            if isinstance(node, ast.AsyncFunctionDef):
                defects.append(
                    (
                        f"{SEAM}:{node.lineno} {node.name}",
                        (
                            f"{node.name} is `async def`. The fill seam declares every "
                            "verb SYNCHRONOUS because §5 fixes the Limiter as a "
                            "single-threaded loop whose serial processing "
                            "'eliminates fill-vs-tick races by construction', and §3's "
                            "ATOMICITY RULE publishes balance and the position table "
                            "as ONE snapshot. An awaitable verb is a declared "
                            "suspension point inside the four state changes one fill "
                            "must make as one motion, and a second fill serviced "
                            "inside it publishes a snapshot torn between two halves "
                            "of the first"
                        ),
                    )
                )
    return defects, verbs


# --------------------------------------------------------------------------
# ARM 1 — the step order
# --------------------------------------------------------------------------


def declared_step_order(source: str) -> tuple[str, ...]:
    """ARM 1's expected side, PARSED from the seam's numbered list. Never typed."""
    found = sorted(
        (int(match.group("rank")), match.group("member"))
        for match in _ORDERED_STEP.finditer(source)
    )
    seen: list[str] = []
    for _rank, member in found:
        if member not in seen:
            seen.append(member)
    return tuple(seen)


def step_defects(
    module: ModuleType, order: tuple[str, ...]
) -> tuple[list[tuple[str, str]], tuple[int, ...]]:
    """ARM 1 — `(defects, observed values)`, read off the IMPORTED enum."""
    cls = getattr(module, _STEP_ENUM, None)
    if not isinstance(cls, type):
        return [
            (
                f"{SEAM}:{_STEP_ENUM}",
                (
                    f"{_STEP_ENUM} is not declared as a class — the handler's step "
                    "order has no type, so the ordering is back to being a comment "
                    "in whatever implementation lands next"
                ),
            )
        ], ()
    defects: list[tuple[str, str]] = []
    if not issubclass(cls, enum.IntEnum):
        defects.append(
            (
                f"{SEAM}:{_STEP_ENUM}",
                (
                    f"{_STEP_ENUM} is not an `enum.IntEnum` (its bases are "
                    f"{', '.join(base.__name__ for base in cls.__bases__)}). The seam "
                    "declares IntEnum so a gate can assert `observed == sorted(observed)` "
                    "over the steps a handler REALLY recorded; over a plain Enum that "
                    "comparison does not typecheck and the order goes back to being "
                    "asserted from source order, which proves nothing about execution"
                ),
            )
        )
    members = (
        {member.name: member for member in cls} if issubclass(cls, enum.Enum) else {}
    )
    values: list[int] = []
    for name in order:
        member = members.get(name)
        if member is None:
            defects.append(
                (
                    f"{SEAM}:{_STEP_ENUM}.{name}",
                    (
                        f"the seam's own numbered list names step {name!r} and the "
                        f"{_STEP_ENUM} enum has no such member — the declaration "
                        "governs a step nothing can record, so a handler that skipped "
                        "it would leave no observable trace"
                    ),
                )
            )
            continue
        try:
            values.append(int(member.value))
        except TypeError, ValueError:
            defects.append(
                (
                    f"{SEAM}:{_STEP_ENUM}.{name}",
                    (
                        f"member value {member.value!r} is not an integer, so the "
                        "VALUES cannot BE the order"
                    ),
                )
            )
    if len(values) == len(order) and any(
        values[i] >= values[i + 1] for i in range(len(values) - 1)
    ):
        spelled = " < ".join(
            f"{name}={value}" for name, value in zip(order, values, strict=False)
        )
        defects.append(
            (
                f"{SEAM}:{_STEP_ENUM}",
                (
                    f"the member VALUES are not strictly increasing in the order the "
                    f"seam's own header fixes: {spelled}. §4 requires the stop to be "
                    "ARMED before §3's row is written — `PositionOriginWriter.on_fill` "
                    "refuses an unstopped fill, and a defaulted zero distance would "
                    "price a real position at zero dollar risk, make the correlation "
                    "bucket read emptier than it is and ADMIT MORE (§7:501, D3.136's "
                    "fail-open under a new spelling) — and the release must sit "
                    "BETWEEN them so the published snapshot does not still hold the "
                    "over-reserved capital"
                ),
            )
        )
    return defects, tuple(values)


# --------------------------------------------------------------------------
# ARM 4 — the narrowing, against a roster derived from a DIFFERENT file
# --------------------------------------------------------------------------


def stopbook_verbs(tree: ast.Module) -> tuple[str, ...]:
    """ARM 4's REFERENCE side: `StopBookPort`'s verbs, by AST, never typed here."""
    node = _classes(tree).get(_STOP_BOOK_PORT)
    return () if node is None else _port_verbs(node)


def narrowing_defects(
    arm_verbs: tuple[str, ...], book_verbs: tuple[str, ...]
) -> list[tuple[str, str]]:
    """ARM 4 — `StopArmPort` is a STRICTLY narrower surface than `StopBookPort`."""
    defects: list[tuple[str, str]] = []
    arm = set(arm_verbs)
    book = set(book_verbs)
    extra = sorted(arm - book)
    if extra:
        defects.append(
            (
                f"{SEAM}:{_STOP_ARM_PORT}",
                (
                    f"declares {', '.join(extra)}, which {STOP_SEAM}'s "
                    f"{_STOP_BOOK_PORT} does not — a port that is not even a SUBSET "
                    "of the book it narrows is a new surface wearing a narrowing's "
                    "name, and no class satisfying the book need satisfy it"
                ),
            )
        )
    elif not arm < book:
        defects.append(
            (
                f"{SEAM}:{_STOP_ARM_PORT}",
                (
                    f"declares {', '.join(sorted(arm)) or 'nothing'}, which is the "
                    f"WHOLE of {_STOP_BOOK_PORT}'s roster rather than a PROPER "
                    "subset — a narrowing that narrows nothing is a second name for "
                    "the same authority"
                ),
            )
        )
    if len(arm_verbs) != 1:
        defects.append(
            (
                f"{SEAM}:{_STOP_ARM_PORT}",
                (
                    f"declares {len(arm_verbs)} verb(s) "
                    f"({', '.join(arm_verbs) or 'none'}) and the fill handler consumes "
                    "exactly ONE. Every extra verb — forget, maintain, breached — is "
                    "authority the handler structurally must not have: per-tick "
                    "maintenance and stop-out detection belong to the tick path, and "
                    "a handler holding them could fire an exit from inside a fill, "
                    "which §14 makes Limiter-only and `nixrisk.flatten` owns"
                ),
            )
        )
    return defects


# --------------------------------------------------------------------------
# ARM 5 — the production classes, DRIVEN
# --------------------------------------------------------------------------


def _instance(loaded: Loaded, class_name: str) -> Any:
    """One REAL object of `class_name`, built from the tree under judgement.

    Constructed rather than checked with `issubclass` because an object that
    cannot be built is a finding in its own right, and because `isinstance` on a
    `runtime_checkable` Protocol is the exact call a caller of the port makes.
    """
    if class_name == "StopBook":
        return loaded.stops.StopBook({_SYMBOL: _TICK})
    return loaded.positions.PositionOriginWriter(
        picture=loaded.picture.FinancialPictureBook(
            balance=_BALANCE,
            deployable_fraction=_FRACTION,
            margin_per_contract={_SYMBOL: _MARGIN},
        ),
        ledger=loaded.execution.ExecutionLedger(),
        stops=loaded.stops.StopBook({_SYMBOL: _TICK}),
        origins=loaded.positions.EntryOrderOrigins(),
    )


def _signature_defect(proto_fn: Any, real_fn: Any) -> str:
    """Do the PARAMETER NAMES line up? The half `isinstance` cannot see.

    `runtime_checkable` isinstance compares METHOD NAMES ONLY — it is blind to
    arity, to parameter names and to every annotation. A class whose parameters
    have drifted therefore satisfies the Protocol and fails at the call, and that
    weakness was measured in ARC 033's gates. Extra parameters on the real method
    are allowed when they are OPTIONAL (`StopBook.arm` carries a keyword-only
    `trail_ticks` the port does not declare) and are a defect when they are
    REQUIRED, because a required extra is a call the port's caller cannot make.
    """
    try:
        want = [
            param.name
            for param in inspect.signature(proto_fn).parameters.values()
            if param.name != "self"
        ]
        real = [
            param
            for param in inspect.signature(real_fn).parameters.values()
            if param.name != "self"
        ]
    except (TypeError, ValueError) as exc:
        return f"signature unreadable ({type(exc).__name__}: {exc})"
    got = [param.name for param in real]
    if got[: len(want)] != want:
        return (
            f"the port declares ({', '.join(want) or 'no parameters'}) and the "
            f"class takes ({', '.join(got) or 'no parameters'}). "
            "`runtime_checkable` isinstance compares METHOD NAMES ONLY, so this "
            "class SATISFIES the Protocol and would fail at the call"
        )
    for extra in real[len(want) :]:
        if extra.default is inspect.Parameter.empty and extra.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            return (
                f"the class takes an EXTRA REQUIRED parameter {extra.name!r} that "
                "the port does not declare — a caller holding only the port "
                "cannot supply it, so the structural fit is nominal"
            )
    return ""


def conformance_defects(
    loaded: Loaded, port_verbs: dict[str, tuple[str, ...]]
) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """ARM 5 — `(defects, pairs actually driven)`. Never a shorter silent loop."""
    defects: list[tuple[str, str]] = []
    driven: list[str] = []
    for port, attr, class_name, why in _CONFORMANCE:
        proto = getattr(loaded.fill_seam, port, None)
        cls = getattr(getattr(loaded, attr), class_name, None)
        if proto is None or cls is None:
            defects.append(
                (
                    f"{SEAM}:{port}",
                    (
                        f"the pair {port} <- {PACKAGE}.{attr}.{class_name} could not "
                        f"be assembled (port {'missing' if proto is None else 'found'}, "
                        f"class {'missing' if cls is None else 'found'}) — {why}"
                    ),
                )
            )
            continue
        try:
            obj = _instance(loaded, class_name)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            defects.append(
                (
                    f"{SEAM}:{port}",
                    (
                        f"{PACKAGE}.{attr}.{class_name} could not be CONSTRUCTED "
                        f"({type(exc).__name__}: {exc}), so the conformance is "
                        "asserted rather than driven and this arm measured nothing "
                        "about it"
                    ),
                )
            )
            continue
        driven.append(f"{class_name}->{port}")
        if not isinstance(obj, proto):
            missing = [
                verb for verb in port_verbs.get(port, ()) if not hasattr(obj, verb)
            ]
            defects.append(
                (
                    f"{SEAM}:{port}",
                    (
                        f"{PACKAGE}.{attr}.{class_name} does NOT structurally satisfy "
                        f"{port}: missing {', '.join(missing) or 'an unnamed member'}. "
                        f"{why}"
                    ),
                )
            )
            continue
        for verb in port_verbs.get(port, ()):
            why_sig = _signature_defect(getattr(proto, verb), getattr(cls, verb))
            if why_sig:
                defects.append((f"{SEAM}:{port}.{verb}", why_sig))
    return defects, tuple(driven)


# --------------------------------------------------------------------------
# ARM 6 — D3.177's rule has a declared home. NOT a statement about any mint.
# --------------------------------------------------------------------------


def mint_rule_defects(
    module: ModuleType, classes: dict[str, ast.ClassDef]
) -> tuple[list[tuple[str, str]], object]:
    """ARM 6 — `(defects, the rule's observed value)`.

    **This says nothing about the production mint, which does not exist yet.**
    `positions.identity_trade_id` returns `order.client_order_id` unchanged and
    is the degenerate mint D3.177's ruling forbids in production; nothing here
    can see it. A green means the RULE has a declared home a later gate can read.
    """
    value = getattr(module, _MINT_RULE, None)
    defects: list[tuple[str, str]] = []
    if value is not True:
        defects.append(
            (
                f"{SEAM}:{_MINT_RULE}",
                (
                    f"is {value!r}, not True. D3.177's architect ruling keeps "
                    "`trade_id` and `client_order_id` DISTINCT behind an explicit, "
                    "gated, Limiter-owned join; an identity mint is an equality that "
                    "holds by construction, so no observation can ever contradict it "
                    "and every round-trip gate over it passes on every input. The "
                    "rule turned off here is the rule turned off everywhere that "
                    "reads it"
                ),
            )
        )
    node = classes.get(_MINT_PORT)
    if node is None:
        defects.append(
            (
                f"{SEAM}:{_MINT_PORT}",
                (
                    f"{_MINT_PORT} is not declared — the mint has no name, no "
                    "identity and no place a gate can find it, which is the "
                    "'default nobody chose' the port exists to prevent"
                ),
            )
        )
    elif _MINT_VERB not in _port_verbs(node):
        defects.append(
            (
                f"{SEAM}:{_MINT_PORT}.{_MINT_VERB}",
                (
                    f"{_MINT_PORT} declares no {_MINT_VERB!r} verb "
                    f"({', '.join(_port_verbs(node)) or 'no verbs at all'}) — a port "
                    "with no minting verb cannot be the injected policy"
                ),
            )
        )
    return defects, value


# --------------------------------------------------------------------------
# THE VERDICT
# --------------------------------------------------------------------------


def _evidence(reading: SeamReading) -> str:
    """Every figure this run actually observed. Never a restatement."""
    steps = ", ".join(
        f"{name}={value}"
        for name, value in zip(reading.step_order, reading.step_values, strict=False)
    )
    return (
        f"FillStep order parsed from the seam's own numbered list: "
        f"{len(reading.step_order)} step(s) [{steps or 'none'}]; "
        f"{reading.callables} callable(s) classified, {reading.verbs} declared "
        f"verb(s), all synchronous; {reading.ports} Protocol port(s); "
        f"{_STOP_ARM_PORT} verbs [{', '.join(reading.arm_verbs) or 'none'}] vs "
        f"{STOP_SEAM}'s {_STOP_BOOK_PORT} verbs "
        f"[{', '.join(reading.stopbook_verbs) or 'none'}]; "
        f"{len(reading.conformance)} class->port pair(s) DRIVEN "
        f"[{', '.join(reading.conformance) or 'none'}] with isinstance and a "
        f"parameter-name comparison; {_MINT_RULE}={reading.mint_rule!r} "
        "(the RULE's home — never a statement about any production mint)"
    )


def _floor_refusal(reading: SeamReading) -> CheckResult | None:
    """`debug.md` §7.12: a run that reached nothing reports so, never PASS."""
    if len(reading.step_order) < MIN_ORDERED_STEPS:
        return _cannot_measure(
            f"{SEAM}: the seam's numbered step list yielded "
            f"{len(reading.step_order)} step(s), below the floor of "
            f"{MIN_ORDERED_STEPS}. ARM 1's expected ORDER is parsed from that "
            "list; too few means the list was renamed or reformatted, and "
            "'strictly increasing' over nothing is universal agreement"
        )
    if reading.callables < MIN_CALLABLES:
        return _cannot_measure(
            f"{SEAM}: {reading.callables} callable(s) classified, below the floor "
            f"of {MIN_CALLABLES}. A seam this small is a seam that was gutted, "
            "and ARM 3 over an empty file is universal agreement"
        )
    if reading.verbs < MIN_DECLARED_VERBS:
        return _cannot_measure(
            f"{SEAM}: {reading.verbs} declared verb(s), below the floor of "
            f"{MIN_DECLARED_VERBS}. ARM 2 over no verbs proves nothing about "
            "synchrony"
        )
    if reading.ports < MIN_PORTS:
        return _cannot_measure(
            f"{SEAM}: {reading.ports} Protocol port(s), below the floor of "
            f"{MIN_PORTS}. The seam has stopped being the surface the fill "
            "handler consumes, so there is nothing for the arms to be about"
        )
    if len(reading.stopbook_verbs) < MIN_STOPBOOK_VERBS:
        return _cannot_measure(
            f"{STOP_SEAM}: {_STOP_BOOK_PORT} declares "
            f"{len(reading.stopbook_verbs)} verb(s), below the floor of "
            f"{MIN_STOPBOOK_VERBS}. ARM 4's REFERENCE side is that roster, and a "
            "proper-subset relation against a gutted superset proves nothing "
            "about the narrowing"
        )
    return None


def _measure(  # pylint: disable=too-many-locals
    home: Path,
) -> tuple[list[tuple[str, str]], SeamReading | None, str]:
    """Run all six arms. Returns `(defects, reading, refusal_detail)`.

    R0914 (too-many-locals): six arms produce six defect lists and six
    observations, and every observation lands in `SeamReading` because the
    evidence string reports what this run actually saw. Splitting the function to
    reach fifteen locals would either drop an observation from the evidence — a
    gate that cannot say what it read can only be believed — or hide the arms
    behind a dispatch table, which makes the SIX arms harder to count than the
    threshold is worth. Each arm is already its own named function; this is the
    composition, and its complexity is linear in the arm count.
    """
    seam_path = home / SEAM
    stop_path = home / STOP_SEAM
    if not seam_path.is_file():
        return [], None, f"{SEAM}: not a file — the subject is unreadable"
    if not stop_path.is_file():
        return (
            [],
            None,
            (
                f"{STOP_SEAM}: not a file — ARM 4's reference roster is absent, and "
                "a narrowing measured against nothing is not a narrowing"
            ),
        )
    try:
        source = seam_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=SEAM)
        stop_tree = ast.parse(stop_path.read_text(encoding="utf-8"), filename=STOP_SEAM)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        return [], None, f"{SEAM}: does not parse ({type(exc).__name__}: {exc})"
    loaded, complaint = load(home)
    if loaded is None:
        return [], None, complaint
    classes = _classes(tree)
    arm_node = classes.get(_STOP_ARM_PORT)
    arm_verbs = () if arm_node is None else _port_verbs(arm_node)
    book_verbs = stopbook_verbs(stop_tree)
    port_verbs = {name: _port_verbs(node) for name, node in classes.items()}

    order = declared_step_order(source)
    defects: list[tuple[str, str]] = []
    step_errs, values = step_defects(loaded.fill_seam, order)
    defects += step_errs
    sync_errs, verbs = synchrony_defects(tree)
    defects += sync_errs
    beh_errs, callables = behaviour_defects(tree)
    defects += beh_errs
    defects += narrowing_defects(arm_verbs, book_verbs)
    conf_errs, driven = conformance_defects(loaded, port_verbs)
    defects += conf_errs
    mint_errs, mint_rule = mint_rule_defects(loaded.fill_seam, classes)
    defects += mint_errs

    reading = SeamReading(
        step_order=order,
        step_values=values,
        callables=callables,
        verbs=verbs,
        ports=_protocol_count(classes),
        arm_verbs=arm_verbs,
        stopbook_verbs=book_verbs,
        conformance=driven,
        mint_rule=mint_rule,
    )
    return defects, reading, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Hold the fill seam against §4's order, §5's synchrony and two classes."""
    try:
        defects, reading, refusal = _measure(ctx.nix_home)
        if reading is None:
            return _cannot_measure(
                refusal
                or f"{SEAM}: neither a reading nor a refusal — a gate's own "
                "pre-flight returning nothing is never a verdict"
            )
        floor = _floor_refusal(reading)
        if floor is not None:
            return floor
        evidence = _evidence(reading)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
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
