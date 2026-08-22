#!/usr/bin/env python3
"""No vendor type crosses the §2A seam — Module 2 invariant B2, as an INSTRUMENT.

ONE gate, ONE property (`nics_risk_subsystem_spec_v1.3.md` §2A:104-105,
invariant 2): *no type, id, or payload originating in a vendor SDK (`ib_async`
/ `ibapi` / any venue SDK) appears above the §2A seam; everything returned by a
port verb or carried by an event is a NEUTRAL struct or a neutral id.*

WHY THIS GATE EXISTS. Until this arc B2's only proof was a TEST —
`scripts/tests/test_broker_order.py` (around :892, :944, :957) drives the
adapter and asserts the objects handed to a recording sink are neutral. That is
a real control and it stays; what it is not is a REGISTERED INSTRUMENT over the
SOURCE. A test observes the paths it exercises. A vendor annotation on a verb
nobody drove, a vendor import added to the seam, a vendor object returned from
a branch no fixture reaches — none of those are visible to it. This gate reads
the two subject files STATICALLY (`ast`, never an import of the vendor SDK —
the idiom `checks/check_order_path_bans.py` established) so a leak is caught
whether or not any test happens to walk that line.

GROUND TRUTH THE GATE CONFIRMS (measured in the ARC 059 recon, and each fact is
an assertion below rather than a comment):

  * `scripts/broker/broker_seam.py` imports STDLIB ONLY (:57-61). The seam IS
    the line; a vendor import inside it is the defect in its purest form
    (ARM 2).
  * `ClientOrderId` / `ExecId` / `Symbol` are `str` aliases (:293-295) carrying
    the comment *"a vendor int id (IBKR orderId) must be mapped, never
    leaked"*. The port's surface therefore speaks in neutral aliases and
    neutral structs, and ARM 3 reads every annotation on the nine
    `ORDER_PORT_VERBS` and seven `ORDER_EVENTS` to hold it there.
  * In `scripts/broker/broker_order_ibkr.py` the vendor `Trade` is retained
    INTERNALLY and never returned (:1069, :1077); `_Tombstone` (:299-314)
    deliberately holds no ib `Order`, no ib `Trade`, no vendor id. ARM 4 walks
    the adapter's roster methods and every event emission and holds that.
  * ONE DECLARED HOLE: `on_ack.reason` deliberately keeps the venue's own code
    and text (`broker_seam.py`:1528-1530). ARM 5 holds it ANCHORED.

==============================================================================
THE ONE DECLARED EXCEPTION, AND WHY IT IS ANCHORED RATHER THAN LISTED
==============================================================================
`OrderEventSink.on_ack`'s `reason` is ratified prose and carries NO ledger row.
`DECLARED_EXCEPTIONS` below is therefore a single explicit allowance carrying
its citation, and ARM 5 requires the JUSTIFICATION ITSELF to still be present
at the site: the phrases *"deliberately NOT vendor-neutral"* and *"it keeps the
venue's own code and text"* must still be in `on_ack`'s own docstring, and
`reason` must still be annotated `str | None`. Delete the reasoning and the
allowance FAILS — an exception may not outlive the justification it points at.

Note the exception's SHAPE, because it is what keeps ARM 3 unweakened: what
crosses is vendor-authored **content inside a neutral `str`**, never a vendor
**type**. So nothing in ARM 3 is exempted; the allowance is checked in its own
arm and its narrowness (one sink verb, one field, one builtin annotation) is
part of what is measured. It is not silently widened.

==============================================================================
§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?
==============================================================================

 1. **A SUBJECT COULD BE ABSENT OR UNPARSEABLE**, and "no vendor import found
    in a file I never opened" is a perfect green. CLOSED: ARM 1 returns
    CANNOT_MEASURE naming the file and the parse error (check contract rule 10 /
    §17 — never a PASS).

 2. **THE WALK COULD FIND NOTHING TO INSPECT.** The rosters could be renamed,
    emptied, or moved and every arm would sweep an empty set. CLOSED: ARM 1
    asserts the seam module was located, that `ORDER_PORT_VERBS` and
    `ORDER_EVENTS` were read out of it as non-empty literal tuples, that a
    NON-ZERO number of §2A surface functions were actually located by name, and
    that the adapter yielded a non-zero number of roster methods and at least
    one event emission. Every one of those counts is reported as evidence, so a
    silent collapse to a smaller population is visible in the PASS line itself.

 3. **THE ROSTER COULD BE A LIST SOMEBODY TYPED HERE.** Then the gate would
    keep proving the property about the nine verbs it remembers while the port
    grew a tenth. CLOSED: `ORDER_PORT_VERBS` and `ORDER_EVENTS` are read by AST
    out of `broker_seam.py` itself (:1813, :1825). A verb added to the port
    joins the walk with no edit here; a verb the roster names and the seam does
    not declare is a FAIL, not a skip.

 4. **THE CLASSIFIER COULD BE UNABLE TO FIRE.** A "is this vendor?" predicate
    that answers no for every input passes over any population. CLOSED: the
    can-fail suite `scripts/tests/test_check_no_vendor_type_leak.py` plants one
    defect per arm on a COPY of the tree and requires each to FAIL **and name
    the leaked type / the offending import / the verb** (check contract rule 11:
    the reason is asserted, never the exit code alone).

 5. **AN UNDECIDABLE CASE COULD BE READ AS CLEAN.** This is the real hazard of a
    static taint walk, and it is the one that would make the gate worse than
    nothing: a return expression the classifier cannot resolve, quietly counted
    as neutral. CLOSED: the classifier is THREE-VALUED — NEUTRAL / VENDOR /
    UNDECIDED — and an UNDECIDED value reaching a roster return or an event
    argument is reported as CANNOT_MEASURE **naming the method and the exact
    expression**. It is never assumed clean. (Where real findings also exist the
    verdict is FAIL and the undecided cases are listed in the same detail —
    check contract rule 4's aggregate: Fail > Cannot-measure.)

 6. **THE FAIL-CLOSED DEFAULTS COULD BE FAIL-OPEN.** An unannotated parameter of
    a vendor-facing callback (`trade`, `fill`, `position`, `value`) is exactly
    where a vendor object enters this module. CLOSED: an unannotated parameter
    is presumed VENDOR, so anything derived from one must be explicitly mapped
    (a neutral constructor, a scalar coercion, or a helper with a neutral return
    annotation) before it may be returned or emitted. Likewise an annotation
    mentioning `Any` is presumed VENDOR — which is not this gate's invention but
    the adapter's own declared convention, stated at `broker_order_ibkr.py`:390:
    *"`Any`, not `object`: these hold VENDOR types (ib_async Order/Trade) that
    must never cross the seam (invariant 2)"*.

 7. **A DECLARED-NEUTRAL BINDING COULD LAUNDER A VENDOR VALUE.** `exec_id:
    ExecId = fill.execution.execId` is accepted as neutral because the seam's
    own vocabulary says `ExecId` is a `str` — an annotation is a declaration,
    and a wrong one is a lie the gate cannot see. NOT FULLY CLOSED, and
    therefore MEASURED: only annotations resolving entirely to the seam's names
    or to builtins count, and every such binding is COUNTED and the count is
    reported in the evidence, so the population that rests on a declaration is
    visible rather than invisible.

 8. **THE PLANTS COULD EDIT A PRODUCTION FILE.** CLOSED (doctrine C.8): this
    gate only ever READS under `ctx.nix_home`; it writes nothing. The suite
    builds a throwaway `nix_home` under `tmp_path` holding COPIES.

 9. **THE PATHS COULD BE HARDCODED**, so the suite's `tmp_path` tree would be
    ignored and every plant would silently be measured against the real tree —
    a suite that passes while testing nothing. CLOSED: every path is derived
    from `ctx.nix_home`, and the can-fail suite asserts no absolute home prefix
    appears anywhere in this file's source.
"""

# pylint: disable=too-many-lines
# too-many-lines: the module is long because §7.12 is answered IN WRITING per
# arm and every vendor-vocabulary entry carries the citation that admits it —
# doctrine B.7. Splitting it would put the justification in a different file
# from the rule it justifies, which is the drift this tree keeps paying for.
# missing-function-docstring: each arm helper's name states its own property
# (the §7.12 answer per arm) and a docstring would restate the name; the
# module docstring carries the reasoning. Same ruling as
# checks/check_broker_order_config.py.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import ast
import enum
import sys
from dataclasses import dataclass, field
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-many-return-statements,too-many-branches
# pylint: disable=too-many-locals,too-many-instance-attributes
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: Reads two source files under `nix_home` and nothing else. No import of the
#: subject, no network, no interpreter state mutated (`ast.parse` only), no
#: write anywhere — the plants live in the can-fail suite's `tmp_path`, never
#: in this gate.
RESOURCES: tuple[str, ...] = (
    "file-read:scripts/broker/broker_seam.py",
    "file-read:scripts/broker/broker_order_ibkr.py",
)
#: NON-CORRECTABLE: a leak here is a design decision about where the vendor
#: boundary sits. The only "corrections" available to an instrument are to
#: rewrite an adapter's return, delete an annotation, or widen the declared
#: exception — each of which edits the subject until the measurement comes out
#: green, which is the defect this project names laundering. An instrument that
#: can repair its own subject can no longer be believed about it.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a vendor type above the §2A seam is a boundary defect: the repair is to "
    "map the value to a neutral struct or a neutral id inside the adapter, "
    "which is a design change to the seam-crossing code. An instrument that "
    "edited an annotation, a return, or its own allowance list until it went "
    "green would be deciding where the vendor boundary sits unattended — and "
    "would then be reporting on a tree it had itself repaired"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/broker/broker_seam.py",
    "scripts/broker/broker_order_ibkr.py",
)

NAME = "check_no_vendor_type_leak"

SEAM = "scripts/broker/broker_seam.py"
ADAPTER = "scripts/broker/broker_order_ibkr.py"

#: The roster CONSTANT NAMES, not the rosters. The verbs and events themselves
#: are read out of `broker_seam.py` (§7.12 answer 3).
VERB_ROSTER = "ORDER_PORT_VERBS"
EVENT_ROSTER = "ORDER_EVENTS"

#: Import roots that mean "a venue SDK". `ib_async` is the one this tree
#: actually uses; the rest are named so a future adapter cannot arrive under a
#: spelling this gate has never heard of and be silently in scope.
VENDOR_MODULE_ROOTS: frozenset[str] = frozenset(
    {
        "ib_async",
        "ib_insync",
        "ibapi",
        "ibkr",
        "tws",
        "tradovate",
        "databento",
        "rithmic",
        "cqg",
        "alpaca",
        "polygon",
        "binance",
        "ccxt",
    }
)

#: Vendor TYPE spellings, used only for a name that is neither defined in the
#: file under inspection nor part of the seam's own vocabulary. A neutral name
#: always wins: `Position` is a seam struct, so it is never read as vendor even
#: though ib_async also has one.
VENDOR_TYPE_SPELLINGS: frozenset[str] = frozenset(
    {
        "Trade",
        "Order",
        "OrderState",
        "Contract",
        "ContractDetails",
        "Execution",
        "Fill",
        "CommissionReport",
        "Ticker",
        "AccountValue",
        "PortfolioItem",
        "BarData",
        "IB",
        "Future",
        "ContFuture",
        "MarketOrder",
        "LimitOrder",
    }
)

#: Calls that convert a value to a builtin scalar. Passing a vendor object
#: through one of these is exactly the mapping invariant 2 asks for: what comes
#: out is an `int`/`float`/`str`, not a vendor type.
SCALAR_COERCIONS: frozenset[str] = frozenset(
    {"int", "float", "str", "bool", "abs", "round", "len", "repr", "bytes"}
)

#: Typing/containers that carry no vendor identity of their own.
NEUTRAL_WRAPPERS: frozenset[str] = frozenset(
    {
        "list",
        "dict",
        "tuple",
        "set",
        "frozenset",
        "deque",
        "Optional",
        "Union",
        "Sequence",
        "Iterable",
        "Mapping",
        "Callable",
        "None",
        "NoneType",
        "object",
        "int",
        "float",
        "str",
        "bool",
        "bytes",
        "complex",
    }
)

#: `Any` in an annotation is read as VENDOR, on the adapter's OWN declared
#: convention (`broker_order_ibkr.py`:390). Not this gate's invention.
ANY_MARKER = "Any"


@dataclass(frozen=True)
class DeclaredException:
    """One ratified, cited allowance. There is exactly one, and it is anchored."""

    site: str
    field_name: str
    citation: str
    anchors: tuple[str, ...]
    annotation: str


#: THE ONLY ALLOWANCE. Ratified in prose, carried by NO ledger row, so it is
#: hardcoded HERE with its citation and held to its own justification by ARM 5.
DECLARED_EXCEPTIONS: tuple[DeclaredException, ...] = (
    DeclaredException(
        site="OrderEventSink.on_ack",
        field_name="reason",
        citation=(
            f"{SEAM}:1528-1530 — `reason` is human-readable colour ONLY and is "
            "deliberately NOT vendor-neutral: it keeps the venue's own code and "
            "text, because that is where IBKR error 201's margin figures live. "
            "ARC 018 (D1.18) added `RejectCategory` so no consumer ever has to "
            "READ `reason` to learn anything it acts on — the vendor spelling "
            "crosses as CONTENT inside a neutral `str`, never as a vendor TYPE"
        ),
        anchors=(
            "deliberately NOT vendor-neutral",
            "it keeps the venue's own code and text",
        ),
        annotation="str | None",
    ),
)


class Taint(enum.Enum):
    """Three-valued on purpose (§7.12 answer 5). UNDECIDED is never clean."""

    NEUTRAL = "neutral"
    VENDOR = "vendor"
    UNDECIDED = "undecided"


def _worst(*values: Taint) -> Taint:
    if Taint.VENDOR in values:
        return Taint.VENDOR
    if Taint.UNDECIDED in values:
        return Taint.UNDECIDED
    return Taint.NEUTRAL


class GateError(Exception):
    """A subject could not be read or parsed — always CANNOT_MEASURE."""


def _parse(home: Path, rel: str) -> ast.Module:
    path = home / rel
    if not path.is_file():
        raise GateError(f"{rel} is absent under {home} — nothing to measure (§17)")
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise GateError(
            f"{rel} could not be parsed — {type(exc).__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# VOCABULARY — what this file calls neutral, and what it calls vendor
# ---------------------------------------------------------------------------


@dataclass
class Vocab:
    """Names, classified, for ONE module under inspection."""

    rel: str
    #: Module-level names the file defines itself (classes, functions, aliases).
    local: set[str] = field(default_factory=set)
    #: The seam's module-level vocabulary — neutral wherever it is used.
    seam: frozenset[str] = frozenset()
    #: local name -> the module it was imported from.
    imported: dict[str, str] = field(default_factory=dict)

    def is_vendor_name(self, name: str) -> bool:
        source = self.imported.get(name)
        if source and source.split(".")[0] in VENDOR_MODULE_ROOTS:
            return True
        if name in VENDOR_MODULE_ROOTS:
            return True
        return (
            name in VENDOR_TYPE_SPELLINGS
            and name not in self.local
            and name not in self.seam
        )

    def is_neutral_name(self, name: str) -> bool:
        if self.is_vendor_name(name):
            return False
        return (
            name in self.local
            or name in self.seam
            or name in NEUTRAL_WRAPPERS
            # A name IMPORTED FROM A NON-VENDOR MODULE is neutral by the
            # property's own definition: invariant 2 bans what ORIGINATES IN
            # THE VENDOR SDK, and every import in the file is visible right
            # here, so "which module did this name come from" is decided, not
            # guessed. This is what resolves `time.time()` and
            # `BrokerOrderConfig` rather than leaving them UNDECIDED. The
            # vendor test above runs FIRST, so `from ib_async import Trade`
            # can never reach this line.
            or name in self.imported
        )


def _module_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _imported_names(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out[(alias.asname or alias.name).split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = node.module
    return out


def _build_vocab(rel: str, tree: ast.Module, seam_names: frozenset[str]) -> Vocab:
    return Vocab(
        rel=rel,
        local=_module_level_names(tree),
        seam=seam_names,
        imported=_imported_names(tree),
    )


def _annotation_names(node: ast.expr | None) -> list[str]:
    """Every identifier an annotation mentions, dotted roots included."""
    if node is None:
        return []
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.append(child.id)
        elif isinstance(child, ast.Attribute):
            base = child.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                names.append(f"{base.id}.{child.attr}")
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            names.append(child.value)
    return names


def _vendor_in_annotation(node: ast.expr | None, vocab: Vocab) -> str:
    """The vendor spelling this annotation names, or `''`."""
    for name in _annotation_names(node):
        root = name.split(".")[0]
        if root in VENDOR_MODULE_ROOTS:
            return name
        if vocab.is_vendor_name(root) or (root != name and vocab.is_vendor_name(name)):
            return name
    return ""


def _annotation_taint(node: ast.expr | None, vocab: Vocab) -> Taint:
    if node is None:
        return Taint.UNDECIDED
    if _vendor_in_annotation(node, vocab):
        return Taint.VENDOR
    names = _annotation_names(node)
    if ANY_MARKER in names:
        return Taint.VENDOR
    if not names:
        return Taint.NEUTRAL
    if all(vocab.is_neutral_name(name.split(".")[0]) for name in names):
        return Taint.NEUTRAL
    return Taint.UNDECIDED


# ---------------------------------------------------------------------------
# ARM 1/2/3 — the seam
# ---------------------------------------------------------------------------


def _module_binding(node: ast.stmt) -> tuple[str | None, ast.expr | None]:
    """STEP of `_roster`, NOT A SECOND GATE — the single name a module-level
    statement binds, and the expression bound to it, or `(None, None)`.

    It reports no finding, raises nothing, and has no verdict of its own; its
    only caller is `_roster`, which owns the property. Split out because the
    gate crossed the tree's cognitive-complexity ceiling, and doctrine B.4
    forbids raising a ceiling to admit code — decomposition changes no verdict
    on any input.
    """
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id, node.value
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id, node.value
    return None, None


def _roster_members(const: str, value: ast.expr) -> tuple[str, ...]:
    """STEP of `_roster`, NOT A SECOND GATE — the string members of the roster's
    own literal, or `GateError` if the literal is not one this gate can read.

    The `GateError` it raises is `_roster`'s CANNOT_MEASURE, reported by
    `_roster`'s caller; this function registers nothing and is reached from
    nowhere else. Split out for the cognitive-complexity ceiling only.
    """
    if not isinstance(value, (ast.Tuple, ast.List)):
        raise GateError(
            f"{SEAM}: {const} is not a literal tuple/list ("
            f"{type(value).__name__}) — the roster cannot be derived"
        )
    members: list[str] = []
    for element in value.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            raise GateError(
                f"{SEAM}: {const} holds a non-literal member — "
                "the roster cannot be derived"
            )
        members.append(element.value)
    return tuple(members)


def _roster(tree: ast.Module, const: str) -> tuple[str, ...]:
    """The roster, read out of the seam's own literal tuple. Never typed here."""
    for node in tree.body:
        target, value = _module_binding(node)
        if target != const or value is None:
            continue
        return _roster_members(const, value)
    raise GateError(
        f"{SEAM}: {const} not found at module level — the §2A surface roster "
        "cannot be derived, so nothing was measured (§17)"
    )


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _defs_named(
    tree: ast.Module, wanted: frozenset[str]
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every def in the module whose name is on the roster, with its owner."""
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in wanted:
                found.append(("<module>", node))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name in wanted
                ):
                    found.append((node.name, item))
    return found


def _statement_import_findings(node: ast.Import) -> list[tuple[str, str]]:
    """STEP of ARM 2, NOT A SECOND GATE — the `import <vendor>` reason only.

    ARM 2 (`_arm_seam_imports`) is the gate and its sole caller; this reports
    one of ARM 2's three distinct reasons and nothing else. Split out for the
    cognitive-complexity ceiling: doctrine B.4 forbids raising a ceiling to
    admit code, and decomposition changes no verdict on any input.
    """
    findings: list[tuple[str, str]] = []
    for alias in node.names:
        root = alias.name.split(".")[0]
        if root not in VENDOR_MODULE_ROOTS:
            continue
        why = (
            f"the SEAM imports the vendor SDK {alias.name!r} "
            f"(`import {alias.name}`). The seam IS the line: "
            "§2A:104-105 invariant 2 puts every vendor type below "
            "it, and a vendor module named inside it is that "
            "boundary already crossed"
        )
        findings.append((f"{SEAM}:{node.lineno}", why))
    return findings


def _from_import_findings(node: ast.ImportFrom) -> list[tuple[str, str]]:
    """STEP of ARM 2, NOT A SECOND GATE — the `from <vendor> import ...` reason.

    A separate reason from the plain-import one above and from the dynamic one
    below; check-contract rule 11 requires each be NAMED, so they stay three.
    Owner and only caller: `_arm_seam_imports`.
    """
    root = (node.module or "").split(".")[0]
    if root not in VENDOR_MODULE_ROOTS:
        return []
    names = ", ".join(alias.name for alias in node.names)
    why = (
        f"the SEAM imports {names!r} from the vendor SDK "
        f"{node.module!r} (`from {node.module} import {names}`) "
        "— §2A:104-105 invariant 2"
    )
    return [(f"{SEAM}:{node.lineno}", why)]


def _called_name(target: ast.expr) -> str:
    """STEP of `_dynamic_import_findings`, NOT A SECOND GATE — the bare name a
    call's callee spells (`import_module` / `__import__`), or `''`."""
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _dynamic_import_findings(node: ast.Call) -> list[tuple[str, str]]:
    """STEP of ARM 2, NOT A SECOND GATE — the `import_module('<vendor>')` reason.

    The third of ARM 2's three distinct reasons. It has no exit code, no
    registration and no meaning apart from `_arm_seam_imports`, which owns the
    property and is its only caller.
    """
    dotted = _called_name(node.func)
    if dotted not in ("import_module", "__import__"):
        return []
    findings: list[tuple[str, str]] = []
    for arg in node.args:
        if (
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and arg.value.split(".")[0] in VENDOR_MODULE_ROOTS
        ):
            why = (
                f"the SEAM dynamically imports the vendor SDK "
                f"{arg.value!r} via {dotted} — a vendor module reaches "
                "the seam whether the import is statement-shaped or not"
            )
            findings.append((f"{SEAM}:{node.lineno}", why))
    return findings


def _arm_seam_imports(tree: ast.Module) -> list[tuple[str, str]]:
    """ARM 2 — the seam imports NO vendor module. It imports stdlib only (:57-61)."""
    findings: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            findings += _statement_import_findings(node)
        elif isinstance(node, ast.ImportFrom) and node.module:
            findings += _from_import_findings(node)
        elif isinstance(node, ast.Call):
            findings += _dynamic_import_findings(node)
    return findings


def _all_arguments(args: ast.arguments) -> list[ast.arg]:
    """STEP of ARM 3 and of `Walker.environment`, NOT A SECOND GATE — every
    parameter one `def` declares, positional-only through `**kwargs`.

    It classifies nothing and reports nothing; it answers "what are the
    parameters" for two callers that each own their own property. Split out for
    the cognitive-complexity ceiling (doctrine B.4: raising it is the forbidden
    direction) and because the same list was assembled twice.
    """
    collected = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        collected.append(args.vararg)
    if args.kwarg is not None:
        collected.append(args.kwarg)
    return collected


def _surface_return_finding(
    node: ast.FunctionDef | ast.AsyncFunctionDef, vocab: Vocab, kind: str, site: str
) -> list[tuple[str, str]]:
    """STEP of ARM 3, NOT A SECOND GATE — the RETURNS-a-vendor-type reason only.

    ARM 3 (`_arm_surface_annotations`) owns the property and is the only
    caller. This is one of ARM 3's three distinct reasons, kept distinct
    because check-contract rule 11 requires each be named.
    """
    leaked = _vendor_in_annotation(node.returns, vocab)
    if not leaked:
        return []
    # `leaked` is truthy only for a non-None annotation, but that is a
    # fact about `_vendor_in_annotation`, not one the type carries.
    # Render defensively so the narration cannot raise on the path that
    # exists to REPORT a defect.
    rendered = ast.unparse(node.returns) if node.returns else "<absent>"
    why = (
        f"the {kind} {node.name!r} RETURNS the vendor type {leaked!r} "
        f"(`-> {rendered}`). §2A:104-105 invariant 2: "
        "everything returned by a port verb or carried by an event is "
        "a NEUTRAL struct or a neutral id"
    )
    return [(site, why)]


def _surface_parameter_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef, vocab: Vocab, kind: str, site: str
) -> tuple[list[tuple[str, str]], int]:
    """STEP of ARM 3, NOT A SECOND GATE — the CARRIES-a-vendor-type reason, plus
    the count of parameter annotations actually classified.

    A distinct reason from the return one, reported by ARM 3, its only caller.
    The count is returned rather than reported: it is evidence ARM 3 assembles,
    not a verdict this function reaches.
    """
    findings: list[tuple[str, str]] = []
    classified = 0
    for argument in _all_arguments(node.args):
        if argument.arg == "self":
            continue
        classified += 1
        leaked = _vendor_in_annotation(argument.annotation, vocab)
        if not leaked:
            continue
        # Same reasoning as the return arm above: render defensively.
        shown = ast.unparse(argument.annotation) if argument.annotation else "<absent>"
        why = (
            f"the {kind} {node.name!r} CARRIES the vendor type "
            f"{leaked!r} on parameter {argument.arg!r} "
            f"(`{argument.arg}: {shown}`). "
            "§2A:104-105 invariant 2"
        )
        findings.append((site, why))
    return findings, classified


def _roster_gap_finding(
    roster: tuple[str, ...],
    located: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]],
    kind: str,
) -> list[tuple[str, str]]:
    """STEP of ARM 3, NOT A SECOND GATE — the roster-names-a-surface-the-seam-
    does-not-declare reason.

    The third of ARM 3's distinct reasons. It has no exit code, no registration
    and no meaning apart from `_arm_surface_annotations`, its only caller.
    """
    missing = sorted(set(roster) - {node.name for _, node in located})
    if not missing or not located:
        return []
    why = (
        f"the roster names {kind}(s) {missing} that the seam declares "
        "nowhere. The roster is the authority (broker_seam.py:1810-1812), "
        "so an unmatched member is an unmeasured surface, not a skip"
    )
    roster_name = VERB_ROSTER if kind == "port verb" else EVENT_ROSTER
    return [(f"{SEAM}:{roster_name}", why)]


def _arm_surface_annotations(
    tree: ast.Module, vocab: Vocab, roster: tuple[str, ...], kind: str
) -> tuple[list[tuple[str, str]], int, int]:
    """ARM 3 — no vendor type in a §2A return or parameter annotation."""
    findings: list[tuple[str, str]] = []
    located = _defs_named(tree, frozenset(roster))
    annotations = 0
    for owner, node in located:
        site = f"{SEAM}:{node.lineno} {owner}.{node.name}"
        annotations += 1
        findings += _surface_return_finding(node, vocab, kind, site)
        parameter_findings, classified = _surface_parameter_findings(
            node, vocab, kind, site
        )
        findings += parameter_findings
        annotations += classified
    findings += _roster_gap_finding(roster, located, kind)
    return findings, len(located), annotations


def _allowance_site_node(
    classes: dict[str, ast.ClassDef], allowance: DeclaredException
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """STEP of ARM 5, NOT A SECOND GATE — the def the allowance points at, or
    `None` when the seam no longer declares it.

    ARM 5 (`_arm_declared_exception`) owns the property and is the only caller;
    this locates a node and reports nothing. Split out for the
    cognitive-complexity ceiling — doctrine B.4 forbids raising a ceiling to
    admit code, and decomposition changes no verdict on any input.
    """
    owner, verb = allowance.site.split(".", 1)
    holder = classes.get(owner)
    node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    if holder is not None:
        for item in holder.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == verb
            ):
                node = item
    return node


def _allowance_anchor_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    allowance: DeclaredException,
    site: str,
) -> list[tuple[str, str]]:
    """STEP of ARM 5, NOT A SECOND GATE — the justification-anchor-is-gone
    reason only.

    One of ARM 5's four distinct reasons, kept distinct because check-contract
    rule 11 requires each be named. Reported by `_arm_declared_exception`, its
    owner and only caller.
    """
    docstring = ast.get_docstring(node) or ""
    flattened = " ".join(docstring.split())
    findings: list[tuple[str, str]] = []
    for anchor in allowance.anchors:
        if anchor in flattened:
            continue
        why = (
            f"the JUSTIFICATION ANCHOR {anchor!r} is no longer present "
            f"in {allowance.site}'s own docstring. The vendor-content "
            f"allowance on {allowance.field_name!r} is ratified in "
            "PROSE and carried by no ledger row, so the prose IS the "
            "ratification: an allowance may not outlive the "
            "justification it points at. Restore the reasoning at the "
            "site, or remove the allowance and make "
            f"{allowance.field_name!r} vendor-neutral. Cited as: "
            f"{allowance.citation}"
        )
        findings.append((site, why))
    return findings


def _allowance_field_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    allowance: DeclaredException,
    site: str,
) -> list[tuple[str, str]]:
    """STEP of ARM 5, NOT A SECOND GATE — the field-is-gone and the
    annotation-was-WIDENED reasons.

    Two of ARM 5's four distinct reasons; they are reported separately here for
    the same rule-11 reason they were reported separately before. Owner and
    only caller: `_arm_declared_exception`.
    """
    parameters = [*node.args.args, *node.args.kwonlyargs]
    matched = [p for p in parameters if p.arg == allowance.field_name]
    if not matched:
        why = (
            f"{allowance.site} no longer declares a "
            f"{allowance.field_name!r} parameter, so the allowance names a "
            "field that does not exist"
        )
        return [(site, why)]
    actual = (
        ast.unparse(matched[0].annotation)
        if matched[0].annotation is not None
        else "<unannotated>"
    )
    if actual == allowance.annotation:
        return []
    why = (
        f"{allowance.field_name!r} is annotated {actual!r}, not "
        f"{allowance.annotation!r}. The allowance is deliberately "
        "NARROW: what crosses is vendor-authored CONTENT inside a "
        "neutral str, never a vendor TYPE. A different annotation is a "
        "WIDENING of a ratified exception and must be argued, not "
        f"absorbed. Cited as: {allowance.citation}"
    )
    return [(site, why)]


def _one_allowance_findings(
    classes: dict[str, ast.ClassDef], allowance: DeclaredException
) -> list[tuple[str, str]]:
    """STEP of ARM 5, NOT A SECOND GATE — every reason ARM 5 has about ONE
    allowance, including the site-is-gone reason.

    It aggregates its three sibling steps for one row of `DECLARED_EXCEPTIONS`
    and hands the list back; the verdict is `_arm_declared_exception`'s, and
    nothing else calls this.
    """
    site = f"{SEAM} {allowance.site}.{allowance.field_name}"
    node = _allowance_site_node(classes, allowance)
    if node is None:
        why = (
            f"the declared exception points at {allowance.site}, which "
            f"{SEAM} no longer declares. An allowance whose SITE is gone "
            "cannot be honoured — it is a hole with nothing behind it. "
            f"Cited as: {allowance.citation}"
        )
        return [(site, why)]
    findings = _allowance_anchor_findings(node, allowance, site)
    findings += _allowance_field_findings(node, allowance, site)
    return findings


def _arm_declared_exception(
    tree: ast.Module,
) -> tuple[list[tuple[str, str]], int]:
    """ARM 5 — the ONE allowance is still anchored to its justification."""
    findings: list[tuple[str, str]] = []
    classes = _classes(tree)
    for allowance in DECLARED_EXCEPTIONS:
        findings += _one_allowance_findings(classes, allowance)
    return findings, len(DECLARED_EXCEPTIONS)


# ---------------------------------------------------------------------------
# ARM 4 — the adapter's taint walk
# ---------------------------------------------------------------------------


def _own_nodes(node: ast.AST):
    """Walk `node`'s body WITHOUT descending into nested function scopes.

    A nested `def`'s returns belong to it, not to the roster verb around it —
    `query_balance`'s local `num()` returns a float and must not be read as
    `query_balance` returning one.
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            continue
        stack.extend(ast.iter_child_nodes(current))


@dataclass
class Walker:
    """The three-valued taint classifier for ONE module (§7.12 answers 5 & 6)."""

    vocab: Vocab
    #: method name -> return-annotation taint, for `self.<m>(...)` resolution.
    methods: dict[str, Taint] = field(default_factory=dict)
    #: `self.<attr>` -> taint, derived from the class's own assignments.
    attributes: dict[str, Taint] = field(default_factory=dict)
    #: module-level function name -> return-annotation taint.
    functions: dict[str, Taint] = field(default_factory=dict)
    #: How many bindings were accepted as neutral purely on an ANNOTATION.
    declared_neutral: int = 0

    # -- expressions --------------------------------------------------------

    def taint(self, node: ast.expr | None, env: dict[str, Taint]) -> Taint:
        if node is None:
            return Taint.NEUTRAL
        for step in (self._taint_simple, self._taint_operator, self._taint_container):
            verdict = step(node, env)
            if verdict is not None:
                return verdict
        # UNCHANGED FALL-THROUGH (§7.12 answer 5): an expression shape none of
        # the three steps above recognises is UNDECIDED, never clean.
        return Taint.UNDECIDED

    def _taint_simple(self, node: ast.expr, env: dict[str, Taint]) -> Taint | None:
        """STEP of `taint`, NOT A SECOND GATE — the leaf and reference shapes.

        `taint` is the classifier and this function's only caller; the three
        `_taint_*` steps are one `if`-ladder split three ways, tried in the same
        order the ladder had. `None` means "not my shape, keep looking" and is
        never a verdict. Split out because the classifier crossed the tree's
        cognitive-complexity ceiling: doctrine B.4 forbids raising a ceiling to
        admit code, and decomposition changes no verdict on any input.
        """
        if isinstance(node, ast.Constant):
            return Taint.NEUTRAL
        if isinstance(node, (ast.JoinedStr, ast.FormattedValue, ast.Compare)):
            return Taint.NEUTRAL
        if isinstance(node, ast.Name):
            return self._name(node, env)
        if isinstance(node, ast.Attribute):
            return self._attribute(node, env)
        if isinstance(node, ast.Subscript):
            return self.taint(node.value, env)
        if isinstance(node, ast.Call):
            return self._call(node, env)
        if isinstance(node, ast.Await):
            return self.taint(node.value, env)
        if isinstance(node, ast.Starred):
            return self.taint(node.value, env)
        if isinstance(node, ast.NamedExpr):
            return self.taint(node.value, env)
        return None

    def _taint_operator(self, node: ast.expr, env: dict[str, Taint]) -> Taint | None:
        """STEP of `taint`, NOT A SECOND GATE — the operator shapes, each still
        worst-of over its own operands. `None` means "not my shape"."""
        if isinstance(node, (ast.BoolOp,)):
            return _worst(*(self.taint(value, env) for value in node.values))
        if isinstance(node, ast.BinOp):
            return _worst(self.taint(node.left, env), self.taint(node.right, env))
        if isinstance(node, ast.UnaryOp):
            return self.taint(node.operand, env)
        if isinstance(node, ast.IfExp):
            return _worst(self.taint(node.body, env), self.taint(node.orelse, env))
        return None

    def _taint_container(self, node: ast.expr, env: dict[str, Taint]) -> Taint | None:
        """STEP of `taint`, NOT A SECOND GATE — the container and comprehension
        shapes, each still worst-of over their members. `None` means "not my
        shape"."""
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return _worst(*(self.taint(element, env) for element in node.elts))
        if isinstance(node, ast.Dict):
            parts = [*node.keys, *node.values]
            return _worst(*(self.taint(part, env) for part in parts))
        if isinstance(
            node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
        ):
            return self._comprehension(node, env)
        return None

    def _name(self, node: ast.Name, env: dict[str, Taint]) -> Taint:
        """STEP of `_taint_simple`, NOT A SECOND GATE — one bare name's taint,
        vendor test FIRST, then the local binding, then the vocabulary."""
        if self.vocab.is_vendor_name(node.id):
            return Taint.VENDOR
        if node.id in env:
            return env[node.id]
        if self.vocab.is_neutral_name(node.id) or node.id in SCALAR_COERCIONS:
            return Taint.NEUTRAL
        return Taint.UNDECIDED

    def _attribute(self, node: ast.Attribute, env: dict[str, Taint]) -> Taint:
        base = node.value
        if isinstance(base, ast.Name):
            if base.id in VENDOR_MODULE_ROOTS or self.vocab.is_vendor_name(base.id):
                return Taint.VENDOR
            if base.id == "self":
                return self.attributes.get(node.attr, Taint.UNDECIDED)
        return self.taint(base, env)

    def _call(self, node: ast.Call, env: dict[str, Taint]) -> Taint:
        arguments = [
            *(self.taint(arg, env) for arg in node.args),
            *(self.taint(kw.value, env) for kw in node.keywords),
        ]
        target = node.func
        if isinstance(target, ast.Name):
            return self._call_by_name(target, arguments)
        if isinstance(target, ast.Attribute):
            return self._call_by_attribute(target, env)
        return Taint.UNDECIDED

    def _call_by_name(self, target: ast.Name, arguments: list[Taint]) -> Taint:
        """STEP of `_call`, NOT A SECOND GATE — a call whose callee is a bare
        name: coercion, vendor constructor, known function, or neutral struct.

        `_call` owns the property and is the only caller. Split out for the
        cognitive-complexity ceiling; doctrine B.4 forbids raising a ceiling to
        admit code, and decomposition changes no verdict on any input.
        """
        if target.id in SCALAR_COERCIONS:
            return Taint.NEUTRAL
        if self.vocab.is_vendor_name(target.id):
            return Taint.VENDOR
        if target.id in self.functions:
            return self.functions[target.id]
        if self.vocab.is_neutral_name(target.id):
            # A neutral struct/alias constructed from clean parts. A VENDOR
            # argument still leaks — wrapping a vendor object in a neutral
            # dataclass does not make it neutral.
            return _worst(*arguments) if arguments else Taint.NEUTRAL
        return Taint.UNDECIDED

    def _call_by_attribute(self, target: ast.Attribute, env: dict[str, Taint]) -> Taint:
        """STEP of `_call`, NOT A SECOND GATE — a call whose callee is an
        attribute: `self.<m>()` resolved against the class, anything else
        against the base expression."""
        base = target.value
        if isinstance(base, ast.Name) and base.id == "self":
            if target.attr in self.methods:
                return self.methods[target.attr]
            if target.attr in self.attributes:
                return self.attributes[target.attr]
            return Taint.UNDECIDED
        return self.taint(base, env)

    def _comprehension(self, node: ast.expr, env: dict[str, Taint]) -> Taint:
        inner = dict(env)
        for generator in node.generators:  # type: ignore[attr-defined]
            source = self.taint(generator.iter, inner)
            self._bind(generator.target, source, inner)
        if isinstance(node, ast.DictComp):
            return _worst(self.taint(node.key, inner), self.taint(node.value, inner))
        return self.taint(node.elt, inner)  # type: ignore[attr-defined]

    # -- bindings -----------------------------------------------------------

    def _bind(self, target: ast.expr, value: Taint, env: dict[str, Taint]) -> None:
        if isinstance(target, ast.Name):
            env[target.id] = _worst(env.get(target.id, value), value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind(element, value, env)

    def environment(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> dict[str, Taint]:
        """Parameters + every binding in the function's OWN scope, worst-of merged."""
        env: dict[str, Taint] = {}
        for parameter in _all_arguments(node.args):
            if parameter.arg == "self":
                continue
            if parameter.annotation is None:
                # FAIL-CLOSED (§7.12 answer 6): an unannotated parameter in a
                # vendor-facing adapter is exactly where a vendor object enters.
                env[parameter.arg] = Taint.VENDOR
            else:
                env[parameter.arg] = _annotation_taint(parameter.annotation, self.vocab)
        for statement in _own_nodes(node):
            self._bind_statement(statement, env)
        return env

    def _bind_statement(self, statement: ast.AST, env: dict[str, Taint]) -> None:
        if isinstance(statement, ast.Assign):
            value = self.taint(statement.value, env)
            for target in statement.targets:
                self._bind(target, value, env)
        elif isinstance(statement, ast.AnnAssign):
            declared = _annotation_taint(statement.annotation, self.vocab)
            value = (
                self.taint(statement.value, env)
                if statement.value is not None
                else Taint.NEUTRAL
            )
            if declared is Taint.NEUTRAL and value is not Taint.NEUTRAL:
                # §7.12 answer 7 — accepted on the DECLARATION, and counted so
                # the population resting on one is visible in the evidence.
                self.declared_neutral += 1
                value = Taint.NEUTRAL
            elif declared is Taint.VENDOR:
                value = Taint.VENDOR
            self._bind(statement.target, value, env)
        elif isinstance(statement, ast.AugAssign):
            self._bind(statement.target, self.taint(statement.value, env), env)
        elif isinstance(statement, (ast.For, ast.AsyncFor)):
            self._bind(statement.target, self.taint(statement.iter, env), env)
        elif isinstance(statement, ast.withitem):
            if statement.optional_vars is not None:
                self._bind(
                    statement.optional_vars,
                    self.taint(statement.context_expr, env),
                    env,
                )
        elif isinstance(statement, ast.ExceptHandler) and statement.name:
            env[statement.name] = _annotation_taint(statement.type, self.vocab)


def _assignment_taint(
    statement: ast.AST, walker: Walker, env: dict[str, Taint]
) -> tuple[list[ast.expr], Taint | None]:
    """STEP of `_self_attributes`, NOT A SECOND GATE — the targets one statement
    assigns and the taint it assigns them, or `([], None)` for a non-assignment.

    `_self_attributes` owns the derivation and is the only caller; this reports
    nothing and has no verdict. Split out for the cognitive-complexity ceiling
    — doctrine B.4 forbids raising a ceiling to admit code, and decomposition
    changes no verdict on any input.
    """
    if isinstance(statement, ast.Assign):
        return list(statement.targets), walker.taint(statement.value, env)
    if isinstance(statement, ast.AnnAssign):
        declared = _annotation_taint(statement.annotation, walker.vocab)
        value = (
            declared
            if declared is not Taint.UNDECIDED
            else walker.taint(statement.value, env)
        )
        return [statement.target], value
    return [], None


def _record_self_targets(
    attributes: dict[str, Taint], targets: list[ast.expr], value: Taint | None
) -> None:
    """STEP of `_self_attributes`, NOT A SECOND GATE — merge one statement's
    `self.<attr>` targets into the map, worst-of, so the answer can only get
    stricter. Its only caller is `_self_attributes`."""
    if value is None:
        return
    for target in targets:
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            continue
        attributes[target.attr] = _worst(attributes.get(target.attr, value), value)


def _self_attributes(node: ast.ClassDef, walker: Walker) -> dict[str, Taint]:
    """`self.<attr>` taints, derived from the class's own assignments."""
    attributes: dict[str, Taint] = {}
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        env = walker.environment(item)
        for statement in _own_nodes(item):
            targets, value = _assignment_taint(statement, walker, env)
            _record_self_targets(attributes, targets, value)
    return attributes


def _build_walker(tree: ast.Module, vocab: Vocab, holder: ast.ClassDef) -> Walker:
    walker = Walker(vocab=vocab)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walker.functions[node.name] = _annotation_taint(node.returns, vocab)
    for item in holder.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walker.methods[item.name] = _annotation_taint(item.returns, vocab)
            for nested in ast.walk(item):
                if isinstance(nested, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    walker.functions.setdefault(
                        nested.name, _annotation_taint(nested.returns, vocab)
                    )
    # Two passes: the first resolves `self.<attr>` with attributes still
    # unknown, the second re-derives them now that the map is populated. A
    # fixpoint in two steps, merged worst-of, so the answer can only get
    # stricter, never looser.
    walker.attributes = _self_attributes(holder, walker)
    second = _self_attributes(holder, walker)
    walker.attributes = {
        key: _worst(walker.attributes.get(key, value), value)
        for key, value in second.items()
    }
    walker.declared_neutral = 0
    return walker


def _adapter_class(tree: ast.Module, verbs: tuple[str, ...]) -> ast.ClassDef | None:
    """The class implementing the port, found by the roster, not by its name."""
    best: ast.ClassDef | None = None
    best_score = 0
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        score = sum(
            1
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name in verbs
        )
        if score > best_score:
            best, best_score = node, score
    return best


def _verb_annotation_finding(
    item: ast.FunctionDef | ast.AsyncFunctionDef, vocab: Vocab, site: str
) -> list[tuple[str, str]]:
    """STEP of ARM 4, NOT A SECOND GATE — the adapter-DECLARES-a-vendor-return
    reason only.

    ARM 4 (`_arm_adapter`) owns the property and is the only caller. This is
    one of ARM 4's four distinct reasons, kept distinct because check-contract
    rule 11 requires each be named. Split out because ARM 4 crossed the tree's
    cognitive-complexity ceiling; doctrine B.4 forbids raising a ceiling to
    admit code, and decomposition changes no verdict on any input.
    """
    leaked = _vendor_in_annotation(item.returns, vocab)
    if not leaked:
        return []
    why = (
        f"the adapter declares port verb {item.name!r} as "
        f"returning the vendor type {leaked!r} — §2A:104-105 "
        "invariant 2"
    )
    return [(site, why)]


def _verb_return_findings(
    item: ast.FunctionDef | ast.AsyncFunctionDef,
    walker: Walker,
    env: dict[str, Taint],
    holder_name: str,
) -> tuple[list[tuple[str, str]], list[str], int]:
    """STEP of ARM 4, NOT A SECOND GATE — the verb-RETURNS-a-vendor-value
    reason, the UNDECIDED returns, and the count of returns walked.

    A distinct reason from the declaration one above; the UNDECIDED list is not
    a second verdict either — ARM 4's caller decides whether it is FAIL detail
    or CANNOT_MEASURE (check-contract rule 4's aggregate). Only caller:
    `_arm_adapter`.
    """
    findings: list[tuple[str, str]] = []
    undecided: list[str] = []
    returns = 0
    for statement in _own_nodes(item):
        if not isinstance(statement, ast.Return):
            continue
        returns += 1
        verdict = walker.taint(statement.value, env)
        expression = (
            ast.unparse(statement.value) if statement.value is not None else "None"
        )
        site = f"{ADAPTER}:{statement.lineno} {holder_name}.{item.name}"
        if verdict is Taint.VENDOR:
            why = (
                f"port verb {item.name!r} RETURNS a vendor-derived "
                f"value across the seam: `return {expression}`. "
                "§2A:104-105 invariant 2 — the vendor Trade is "
                "retained INTERNALLY and never returned "
                f"({ADAPTER}:1069, :1077); map it to a neutral struct "
                "or a neutral id first"
            )
            findings.append((site, why))
        elif verdict is Taint.UNDECIDED:
            undecided.append(
                f"{site} returns `{expression}`, which this gate "
                "cannot classify statically as neutral or vendor — "
                "reported, NEVER assumed clean"
            )
    return findings, undecided, returns


def _emission_payload(node: ast.Call) -> list[tuple[str, ast.expr]]:
    """STEP of `_emission_argument_findings`, NOT A SECOND GATE — one emission's
    arguments, labelled by position or by keyword (`**` for an unpacking)."""
    payload = [(str(index), arg) for index, arg in enumerate(node.args)]
    payload += [(kw.arg or "**", kw.value) for kw in node.keywords]
    return payload


def _emission_argument_findings(
    node: ast.Call,
    attr: str,
    walker: Walker,
    env: dict[str, Taint],
    site: str,
) -> tuple[list[tuple[str, str]], list[str]]:
    """STEP of ARM 4, NOT A SECOND GATE — the event-EMITTED-carrying-a-vendor-
    value reason and the UNDECIDED emissions, for ONE call site.

    The fourth of ARM 4's distinct reasons. It registers nothing, has no exit
    code, and is reached only from `_event_emission_findings`, which is itself
    a step of `_arm_adapter`.
    """
    findings: list[tuple[str, str]] = []
    undecided: list[str] = []
    for label, argument in _emission_payload(node):
        verdict = walker.taint(argument, env)
        expression = ast.unparse(argument)
        if verdict is Taint.VENDOR:
            why = (
                f"event {attr!r} is EMITTED carrying a "
                f"vendor-derived value in argument {label} — "
                f"`{expression}`. §2A:104-105 invariant 2: everything "
                "carried by an event is a NEUTRAL struct or a neutral id"
            )
            findings.append((site, why))
        elif verdict is Taint.UNDECIDED:
            undecided.append(
                f"{site} emits {attr} with argument {label} = "
                f"`{expression}`, which this gate cannot classify "
                "statically — reported, NEVER assumed clean"
            )
    return findings, undecided


def _event_emission_findings(
    item: ast.FunctionDef | ast.AsyncFunctionDef,
    walker: Walker,
    env: dict[str, Taint],
    holder_name: str,
    event_set: frozenset[str],
) -> tuple[list[tuple[str, str]], list[str], int]:
    """STEP of ARM 4, NOT A SECOND GATE — every §2A event emission inside ONE
    adapter method, with the count of emissions walked.

    It locates the emissions and defers each one's classification to
    `_emission_argument_findings`; the verdict is `_arm_adapter`'s, and nothing
    else calls this.
    """
    findings: list[tuple[str, str]] = []
    undecided: list[str] = []
    emissions = 0
    for node in _own_nodes(item):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if not isinstance(target, ast.Attribute) or target.attr not in event_set:
            continue
        emissions += 1
        site = f"{ADAPTER}:{node.lineno} {holder_name}.{item.name}"
        call_findings, call_undecided = _emission_argument_findings(
            node, target.attr, walker, env, site
        )
        findings += call_findings
        undecided += call_undecided
    return findings, undecided, emissions


def _arm_adapter(
    tree: ast.Module,
    vocab: Vocab,
    verbs: tuple[str, ...],
    events: tuple[str, ...],
) -> tuple[list[tuple[str, str]], list[str], dict[str, int]]:
    """ARM 4 — no vendor object is RETURNED from a roster verb or EMITTED."""
    findings: list[tuple[str, str]] = []
    undecided: list[str] = []
    counts = {"methods": 0, "returns": 0, "emissions": 0, "declared_neutral": 0}

    holder = _adapter_class(tree, verbs)
    if holder is None:
        return findings, undecided, counts

    walker = _build_walker(tree, vocab, holder)
    verb_set = frozenset(verbs)
    event_set = frozenset(events)

    for item in holder.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        env = walker.environment(item)
        if item.name in verb_set:
            counts["methods"] += 1
            site = f"{ADAPTER}:{item.lineno} {holder.name}.{item.name}"
            findings += _verb_annotation_finding(item, vocab, site)
            verb_findings, verb_undecided, returns = _verb_return_findings(
                item, walker, env, holder.name
            )
            findings += verb_findings
            undecided += verb_undecided
            counts["returns"] += returns

        emit_findings, emit_undecided, emissions = _event_emission_findings(
            item, walker, env, holder.name, event_set
        )
        findings += emit_findings
        undecided += emit_undecided
        counts["emissions"] += emissions
    counts["declared_neutral"] = walker.declared_neutral
    return findings, undecided, counts


# ---------------------------------------------------------------------------
# VERDICT
# ---------------------------------------------------------------------------


def _measure(home: Path) -> CheckResult:
    seam_tree = _parse(home, SEAM)
    adapter_tree = _parse(home, ADAPTER)

    seam_names = frozenset(_module_level_names(seam_tree))
    seam_vocab = _build_vocab(SEAM, seam_tree, seam_names)
    adapter_vocab = _build_vocab(ADAPTER, adapter_tree, seam_names)

    verbs = _roster(seam_tree, VERB_ROSTER)
    events = _roster(seam_tree, EVENT_ROSTER)

    findings: list[tuple[str, str]] = []
    findings += _arm_seam_imports(seam_tree)

    verb_findings, verb_count, verb_annotations = _arm_surface_annotations(
        seam_tree, seam_vocab, verbs, "port verb"
    )
    event_findings, event_count, event_annotations = _arm_surface_annotations(
        seam_tree, seam_vocab, events, "event"
    )
    findings += verb_findings + event_findings

    adapter_findings, undecided, counts = _arm_adapter(
        adapter_tree, adapter_vocab, verbs, events
    )
    findings += adapter_findings

    exception_findings, exception_count = _arm_declared_exception(seam_tree)
    findings += exception_findings

    # ARM 1 — VACUITY GUARD. Every one of these is a way the walk could have
    # swept an empty set and reported a clean tree.
    surface = verb_count + event_count
    if not verbs or not events:
        raise GateError(
            f"{SEAM}: {VERB_ROSTER} has {len(verbs)} members and {EVENT_ROSTER} "
            f"has {len(events)} — an EMPTY roster means the §2A surface was "
            "never walked, and an empty walk is never a PASS (§17)"
        )
    if surface == 0:
        raise GateError(
            f"{SEAM}: the rosters name {len(verbs)} verbs and {len(events)} "
            "events, and NOT ONE of them is declared as a function in the seam "
            "— zero §2A surface functions were inspected, so nothing was "
            "measured (§17)"
        )
    if counts["methods"] == 0:
        raise GateError(
            f"{ADAPTER}: no class implementing any of the {len(verbs)} roster "
            "verbs was found — the adapter half of invariant 2 was not "
            "measured (§17)"
        )
    if counts["emissions"] == 0:
        raise GateError(
            f"{ADAPTER}: the adapter declares roster verbs but emits NONE of "
            f"the {len(events)} §2A events — the event half of invariant 2 was "
            "not measured (§17)"
        )

    evidence = (
        f"§2A:104-105 invariant 2 (B2), measured by AST with no vendor SDK "
        f"imported: {SEAM} imports checked for {len(VENDOR_MODULE_ROOTS)} "
        f"venue-SDK roots (it imports stdlib only, :57-61); rosters DERIVED "
        f"from the file ({VERB_ROSTER}={len(verbs)} verbs, "
        f"{EVENT_ROSTER}={len(events)} events), locating {surface} §2A surface "
        f"functions and classifying {verb_annotations + event_annotations} "
        f"annotations; {counts['methods']} adapter roster methods walked "
        f"({counts['returns']} returns, {counts['emissions']} event emissions) "
        f"through a three-valued taint classifier, of which "
        f"{counts['declared_neutral']} binding(s) were accepted on a neutral "
        f"annotation; {exception_count} declared exception "
        f"(on_ack.reason) re-anchored to its justification at {SEAM}:1528-1530"
    )

    if findings:
        detail = "; ".join(f"{site}: {why}" for site, why in findings)
        if undecided:
            detail += "; UNDECIDED (not assumed clean): " + "; ".join(undecided)
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in findings),
            evidence=evidence,
            detail=detail,
        )
    if undecided:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail=(
                f"{len(undecided)} seam-crossing value(s) could not be "
                "classified statically, so invariant 2 is NOT proven for them "
                "— a gate that assumed them clean would be worse than one that "
                "says it cannot tell: " + "; ".join(undecided)
            ),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        return _measure(ctx.nix_home)
    except GateError as exc:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=str(exc))
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
