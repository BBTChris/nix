#!/usr/bin/env python3
# C0302: over pylint's line ceiling, and the excess is PROSE — the §7.12
# standing question answered condition by condition, plus a stated limit beside
# every arm of the resolver. Doctrine B.7 puts the argument next to the
# instrument it argues for; splitting this gate would move the resolver's known
# blind spots away from the resolver.
# pylint: disable=too-many-lines
# R0801 pairs this file's DECLARATION BLOCK, its git helper and its
# `standalone_main` footer against every other house-style check's. That shape
# is REQUIRED, not accidental duplication (§4.2).
# pylint: disable=duplicate-code
"""Gate: a public entry point in SHIPPED code with ZERO shipped call sites.

ARC 034 / sub-agent D. `checks/uncalled_entry_points_baseline.json` is the
ratchet.

## WHY THIS GATE EXISTS — a measured class, not an anticipated one

ARC 033 built §7's correlation-cap origin write. It was built, it was gated by
`check_origin_write`, it reddened on a wrong stop distance — and **nothing in
production ever called it.** `StopBook.arm` and `PositionOriginWriter.on_fill`
had zero production callers, so production still never CHOSE a stop distance
(CHECK-DEBT D3.150, D3.178). Nothing in the tree could see that, because every
instrument in the tree asks *"does this code do the right thing when driven?"*
and none asked *"does anything drive it?"*

ARC 034's §0a audit of the six ARC 033 gates (D3.191) then found the same class
at 5x scale: **five of six ARC 033 modules have ZERO production importers, and
the only non-test code constructing any of their classes is the gate that
measures them.** 170 of 176 public symbols had no production caller.

This is `check_derived_claims` / D3.16's *"the gate never drives its subject"*
class, moved one layer up — from the TEST level to the PRODUCTION level.

## SCOPE, AND IT IS DERIVED RATHER THAN LISTED

Three populations, all read out of `git ls-files` and a path rule, so nothing
here is a hand-maintained roster that a new directory silently escapes:

* **SHIPPED** — every tracked `*.py` under `scripts/` that is NOT under
  `scripts/tests/`. This is both the population of entry points JUDGED and the
  population of call sites that COUNT.
* **GATE** — every tracked `*.py` under `checks/`. Call sites here are counted
  and reported SEPARATELY, as `gate_only`. **A gate is not shipped code.** A
  class whose only constructor in the tree is the check that measures it is
  precisely the situation this detector exists to name, so counting a gate's
  call as production wiring would make the instrument agree with the defect.
* **NEITHER** — `scripts/tests/`, `databases/`, everything else. A test is a
  measurement, not a caller; a symbol reached only by a test is exactly as
  unwired as one reached by nothing.

Two buckets, both findings, and the distinction is diagnostic:

* `uncalled` — no call site in shipped code and none in a gate either.
* `gate_only` — no call site in shipped code; a GATE calls it. That is the
  literal ARC 033 shape.

## WHAT THIS GATE CANNOT SEE, STATED BEFORE THE VERDICT IS READ

Static AST analysis cannot resolve dynamic dispatch. Read every green here
against these, because a gate that over-reports is a gate people route around
(`debug.md` §7.12's own argument):

1. **`getattr(obj, name)()`, dict-of-callables dispatch, `functools.partial`
   held in a table, anything reached through a string.** INVISIBLE to the
   reference walk. A symbol reached only that way is reported as a finding and
   the report is WRONG. No arm closes this; it is the residual and it is named.
2. **A receiver whose type cannot be inferred.** `obj.m()` where nothing in
   scope says what `obj` is. Those references are reported as CANNOT-RESOLVE for
   every same-named symbol, **never as evidence that the symbol is uncalled** —
   an unresolved reference suppresses the finding rather than creating one, so
   the resolver's ignorance can only cost this gate findings, never invent them.
3. **A `Protocol`-typed parameter IS a real call site**, and resolving those is
   most of the work here. `port.on_fill(...)` where `port: OriginWritePort`
   counts as a call of every class that structurally satisfies that Protocol,
   because that is what the call actually does at runtime. Satisfaction is
   computed structurally (every public verb of the Protocol present on the
   class), which is Python's own rule and is deliberately GENEROUS — a generous
   implementer set costs findings, never manufactures them.
4. **This gate proves a call SITE exists. It does not prove the site EXECUTES**
   — a call inside a branch nothing reaches is a call site here. The same gap
   `check_artifact_gate_coverage` states for `SUBJECTS`, one layer over.

## debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
## MEASURING NOTHING?

1. **The enumeration could be empty.** No tracked files, wrong cwd, git absent
   — "zero entry points, zero findings, PASS" is the purest vacuous green.
   *Closed:* fewer than `MIN_CREDIBLE_MODULES` shipped modules or fewer than
   `MIN_CREDIBLE_ENTRY_POINTS` judged symbols is CANNOT_MEASURE, never PASS.
   The floors are anchored well below the observed figures and are NOT set to
   today's count — a threshold equal to the current number is a moving anchor.
2. **The RESOLVER could resolve everything to a match**, making every symbol
   CALLED and the finding set empty. *Closed twice:* the accepted set is a
   ratchet, so the whole accepted set evaporating is a stale-baseline FAIL on
   every row of it; and `analyse` re-runs the WHOLE walk with receiver
   resolution DISABLED and `vacuity_refusal` requires the two finding sets to
   DIFFER.
3. **The RESOLVER could resolve nothing**, making every symbol CANNOT-RESOLVE
   and the finding set shrink for the opposite reason. *Closed by the same two
   controls*, plus `called` is required to be at least as large as
   `cannot_resolve` — a resolver that has stopped working collapses `called` and
   inflates `cannot_resolve`, and the inequality inverts.
4. **THE DIFFERENTIAL COULD BE THE ONLY THING KEEPING IT HONEST AND COULD
   ITSELF BE VACUOUS.** It compares two computations of one function; if both
   walks shared a broken helper they would agree and the
   control would pass. *Stated, and narrowed rather than claimed closed:* the
   two walks differ ONLY in the `resolve` flag, so a defect in the shared
   reference collector moves both. What it does prove is that receiver
   resolution changes the answer on this tree, TODAY, by a named margin printed
   in the evidence. It is a non-vacuity control, not an independence control,
   and it is labelled as such rather than being read as the stronger thing.
5. **The BASELINE could absorb everything forever.** A ratchet whose accepted
   set only grows is a suppression list wearing a ratchet's name. *Closed by the
   same three rules `check_artifact_gate_coverage` uses:* an accepted entry that
   acquires a caller is a FAIL (stale baseline), an accepted entry whose symbol
   no longer exists is a FAIL (rot), and any addition relative to the tightest
   COMMITTED revision must name the arc that admitted it — with that revision
   derived from the baseline's own git history, which the edit under judgement
   cannot reach in the same motion.
6. **THE BASELINE COULD BE REGENERATED BY THE GATE**, which would make every
   rule above decorative. *Closed by construction:* `CORRECTABLE = False`, there
   is no write path in this file at all, and the baseline is authored. An
   instrument that rewrites its own baseline manufactures its own green.
7. **The bucket labels could rot**, so `gate_only` and `uncalled` stop meaning
   anything and the diagnostic distinction becomes decoration. *Closed:* the
   recorded bucket is compared against the measured one on every run and a
   mismatch is a FAIL naming both values.
8. **The OWNER could be furniture.** 199 findings with a plausible-looking arc
   beside them would be doctrine B.3's *"an owner that cannot pay is no owner
   wearing a name"* at scale. *Closed:* per-module owners are read and validated
   with `guard_owner_defect`, `unassigned` is accepted as HONEST and produces
   CANNOT_MEASURE rather than GUARDED, and §0g's assignment rule rejects the arc
   in flight. **The day-one verdict of this gate is CANNOT_MEASURE for exactly
   that reason and it is not a defect in the gate.**

NON-CORRECTABLE: wiring a producer into production is a design decision about
what the system does, not an edit an instrument may make. A gate that could add
its own call sites would be manufacturing its own green.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import subprocess  # nosec B404 - git ls-files/log/show, fixed argv, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    completed_arcs,
    guard_owner_assignment_defect,
    guard_owner_defect,
    in_flight_arc,
)
from nixverify.gitenv import scrubbed_env

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: Spawns `/usr/bin/git` for `ls-files`, `log` and `show`. Declared because
#: `check_observed_resource_claims` OBSERVES this and an empty tuple beside a
#: real subprocess is a measurable false declaration (D2.27, §4.4).
RESOURCES: tuple[str, ...] = ("subprocess:git",)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "an uncalled entry point is closed by WIRING it — a design decision about "
    "what the system does — or by deleting it. An instrument that could add "
    "its own call sites, or add its own baseline rows, would be manufacturing "
    "its own green"
)
#: ONLY the baseline. The shipped modules this gate READS are deliberately NOT
#: declared: `check_artifact_gate_coverage`'s baseline currently accepts several
#: of them as uncovered, and declaring them here would tighten ANOTHER gate's
#: ratchet as a side effect of naming a file — which is D3.19's *naming is not
#: measuring* used to make an unrelated number fall.
SUBJECTS: tuple[str, ...] = ("checks/uncalled_entry_points_baseline.json",)

NAME = "check_uncalled_entry_points"
GIT = "/usr/bin/git"
BASELINE = "checks/uncalled_entry_points_baseline.json"

#: Below these the enumeration is not credible and the gate refuses to report.
#: Anchored to floors, not to today's counts — a threshold equal to the current
#: number is a moving anchor that reddens the moment a file is added.
MIN_CREDIBLE_MODULES = 40
MIN_CREDIBLE_ENTRY_POINTS = 250

#: How far back the ratchet reads. Bounded so this gate's runtime cannot be set
#: by the length of the repository's history.
_HISTORY_LIMIT = 200

_SHIPPED = "shipped"
_GATE = "gate"

UNCALLED = "uncalled"
GATE_ONLY = "gate_only"
CALLED = "called"
CANNOT_RESOLVE = "cannot_resolve"
BUCKETS = (UNCALLED, GATE_ONLY)

#: Decorators that turn a `def` into an attribute READ rather than a call. Both
#: are referenced as `obj.name`, never `obj.name()`, which is why the reference
#: collector counts attribute ACCESS and not only `ast.Call`.
_PROPERTY_DECORATORS = ("property", "cached_property")

#: ARC 035 (sub-agent D). The annotation was `tuple[tuple[type, ...], str]`,
#: which describes ONE pair rather than the tuple OF pairs this actually is, so
#: `for kinds, name in _CONTAINER_LITERALS` type-checked as unpacking a `str`.
#: The three errors it produced had never been seen: mypy resolves this module
#: only when a `checks/*.py` file is in the same hook invocation as a test that
#: imports it, and no commit had ever passed both until a new check landed.
_CONTAINER_LITERALS: tuple[tuple[tuple[type[ast.AST], ...], str], ...] = (
    ((ast.Dict, ast.DictComp), "dict"),
    ((ast.List, ast.ListComp), "list"),
    ((ast.Tuple, ast.GeneratorExp), "tuple"),
    ((ast.Set, ast.SetComp), "set"),
)


# ===========================================================================
# SCOPE — derived from `git ls-files` and a path rule, never a listed roster.
# ===========================================================================


def _git(home: Path, *args: str) -> tuple[str, str]:
    """Run one git command against `home` and NOTHING else. Returns (out, error).

    `scrubbed_env` is not optional (D3.22): git honours `GIT_DIR`, `GIT_WORK_TREE`
    and friends AHEAD of `-C`, so a caller invoked from inside a pre-commit hook
    would silently enumerate a different repository from the directory it was
    handed.
    """
    if not Path(GIT).exists():
        return "", f"{GIT} not present"
    try:
        proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
            [GIT, "-C", str(home), *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"git {args[0]} failed: {exc!r}"
    if proc.returncode != 0:
        return "", f"git {' '.join(args)} exit {proc.returncode}"
    return proc.stdout, ""


def scope_of(path: str) -> str:
    """`shipped`, `gate`, or `''`. THE scope rule, spelled once.

    A separate function so the test suite can assert the rule directly instead
    of inferring it from a verdict — the boundary between *shipped* and *a gate*
    is the whole premise of this instrument, and a boundary that can only be
    observed through the answer cannot be argued with.
    """
    if not path.endswith(".py"):
        return ""
    if path.startswith("scripts/tests/"):
        return ""
    if path.startswith("scripts/"):
        return _SHIPPED
    if path.startswith("checks/"):
        return _GATE
    return ""


def _in_scope(home: Path) -> tuple[dict[str, str], str]:
    """Every tracked python file that is in scope -> its scope. Or an error."""
    listing, error = _git(home, "ls-files")
    if error:
        return {}, error
    found = {}
    for line in listing.splitlines():
        scope = scope_of(line.strip())
        if scope:
            found[line.strip()] = scope
    return found, ""


# ===========================================================================
# THE CLASS TABLE. Built over shipped AND gate modules, because a receiver in a
# gate still has to be resolved before that gate's call can be attributed.
# ===========================================================================


def type_name(node: ast.expr | None) -> str:  # pylint: disable=too-many-return-statements
    """The bare NAME an annotation / base / constructor expression settles on.

    Deliberately lossy: `dict[str, Window]` -> `dict`, `Foo | None` -> `Foo`,
    `mod.Foo` -> `Foo`. The resolver only ever tests a receiver's type name for
    membership in the class table, so a generic parameter is noise — and
    collapsing `X | None` to `X` is the reading that keeps an optional port
    resolvable instead of silently unresolved.
    """
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return type_name(node.value)
    if isinstance(node, ast.BinOp):
        return type_name(node.left) or type_name(node.right)
    if isinstance(node, ast.IfExp):
        return type_name(node.body) or type_name(node.orelse)
    if isinstance(node, ast.Call):
        return type_name(node.func)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split("[")[0].strip()
    for kinds, name in _CONTAINER_LITERALS:
        if isinstance(node, kinds):
            return name
    return ""


@dataclasses.dataclass
class ClassInfo:
    """One class as this gate needs to see it."""

    name: str
    path: str
    bases: tuple[str, ...]
    is_protocol: bool
    #: method name -> (lineno, kind). Includes private and dunder names: they
    #: are not JUDGED, but they are part of the structural signature a Protocol
    #: satisfaction test reads, and part of the attribute table.
    methods: dict[str, tuple[int, str]] = dataclasses.field(default_factory=dict)
    #: attribute name -> type name, for `self._port.verb()` resolution.
    attrs: dict[str, str] = dataclasses.field(default_factory=dict)

    def public_methods(self) -> frozenset[str]:
        """The verbs a `Protocol` satisfaction test compares."""
        return frozenset(m for m in self.methods if not m.startswith("_"))


def _method_kind(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """`property` or `method`, from the decorator list."""
    for dec in node.decorator_list:
        if type_name(dec) in _PROPERTY_DECORATORS:
            return "property"
    return "method"


def _param_types(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    """Annotated parameter -> type name. The seed of every local resolution."""
    args = node.args
    out: dict[str, str] = {}
    for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
        found = type_name(arg.annotation)
        if found:
            out[arg.arg] = found
    return out


def _self_attr(target: ast.expr) -> str:
    """`self.<name>` -> `<name>`; anything else -> `''`."""
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ):
        return target.attr
    return ""


def _learn_attrs(info: ClassInfo, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    """Learn `self.<attr>` types from one method body.

    Three shapes, and they are the three the tree actually uses: an annotated
    assignment, an assignment from an annotated PARAMETER (which is how every
    injected port in `nixrisk` arrives), and an assignment from a constructor
    call. `setdefault` so the first sighting wins — a later re-bind to something
    weaker must not erase a known port type.
    """
    params = _param_types(fn)
    for sub in ast.walk(fn):
        if isinstance(sub, ast.AnnAssign):
            attr = _self_attr(sub.target)
            found = type_name(sub.annotation)
            if attr and found:
                info.attrs.setdefault(attr, found)
        elif isinstance(sub, ast.Assign):
            _learn_assigned_attr(info, sub, params)


def _learn_assigned_attr(
    info: ClassInfo, node: ast.Assign, params: dict[str, str]
) -> None:
    """`self._x = <param>` or `self._x = Thing(...)` -> one attribute type.

    Split out of `_learn_attrs` to keep both under the cognitive-complexity
    ceiling. The `ast.Name` branch is the one that matters in this tree: every
    injected port in `nixrisk` arrives as an annotated constructor parameter and
    is stored on `self` unannotated, so without it `self._windows.state()` is
    unresolvable and the whole producer family reads CANNOT-RESOLVE.
    """
    value = node.value
    found = (
        params.get(value.id, "") if isinstance(value, ast.Name) else type_name(value)
    )
    if not found:
        return
    for target in node.targets:
        attr = _self_attr(target)
        if attr:
            info.attrs.setdefault(attr, found)


def _class_info(path: str, node: ast.ClassDef) -> ClassInfo:
    """One `ClassDef` read into a `ClassInfo`."""
    bases = tuple(name for name in (type_name(b) for b in node.bases) if name)
    info = ClassInfo(
        name=node.name, path=path, bases=bases, is_protocol="Protocol" in bases
    )
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.methods[item.name] = (item.lineno, _method_kind(item))
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            found = type_name(item.annotation)
            if found:
                info.attrs[item.target.id] = found
    # A SECOND name for the second loop: `item` above is bound over `node.body`
    # and is a `stmt`, while `ast.walk` yields `AST`. Reusing the name narrowed
    # the walk to `stmt` and was the fourth latent error (ARC 035 / D).
    for walked in ast.walk(node):
        if isinstance(walked, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _learn_attrs(info, walked)
    return info


def build_classes(trees: dict[str, ast.Module]) -> dict[str, list[ClassInfo]]:
    """class NAME -> every class with that name, anywhere in scope.

    Keyed by bare name and holding a LIST because two modules may spell the same
    class name, and a resolver that silently picked one would attribute a call
    to the wrong file. Every same-named class is treated as a candidate, which
    costs findings and never invents them.
    """
    out: dict[str, list[ClassInfo]] = {}
    for path, tree in trees.items():
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                out.setdefault(node.name, []).append(_class_info(path, node))
    return out


def protocol_implementers(
    classes: dict[str, list[ClassInfo]],
) -> dict[str, frozenset[str]]:
    """Protocol name -> class names that STRUCTURALLY satisfy it.

    Python's own rule: a class satisfies a `Protocol` when it has every verb the
    Protocol declares, with no inheritance required. That is why
    `port.on_fill(...)` is a real call site for `PositionOriginWriter` even
    though nothing anywhere says the two are related.

    Deliberately GENEROUS — a class that happens to carry the same verb set is
    counted as an implementer. Generosity here can only turn a finding into a
    CALLED, so it costs this gate findings and can never manufacture one.
    Protocols with no public verb are skipped: everything satisfies them.
    """
    out: dict[str, frozenset[str]] = {}
    concrete = [c for group in classes.values() for c in group if not c.is_protocol]
    for name, group in classes.items():
        verbs: set[str] = set()
        for proto in group:
            if proto.is_protocol:
                verbs |= set(proto.public_methods())
        if not verbs:
            continue
        out[name] = frozenset(c.name for c in concrete if verbs <= c.public_methods())
    return out


def dispatch_targets(
    tname: str,
    classes: dict[str, list[ClassInfo]],
    implementers: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Every class name a receiver typed `tname` may actually be dispatching to.

    The type itself, its ancestors (a call of a verb defined on a base IS a call
    of that base's method), and — where the type is a `Protocol` — every class
    that structurally satisfies it.
    """
    seen: set[str] = set()
    frontier = [tname]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        for info in classes.get(current, ()):
            frontier.extend(info.bases)
        frontier.extend(implementers.get(current, ()))
    return frozenset(seen)


# ===========================================================================
# THE JUDGED POPULATION
# ===========================================================================


@dataclasses.dataclass(frozen=True)
class EntryPoint:
    """One public entry point in shipped code."""

    path: str
    owner: str  # class name, or "" for a module-level function
    name: str
    lineno: int
    kind: str  # function | method | property | protocol_verb

    @property
    def symbol(self) -> str:
        """`Class.verb` or `function` — the key inside a baseline module row."""
        return f"{self.owner}.{self.name}" if self.owner else self.name

    @property
    def sid(self) -> str:
        """`<path>::<symbol>` — the ratchet's identity, and greppable."""
        return f"{self.path}::{self.symbol}"


def _class_entry_points(
    path: str, node: ast.ClassDef, classes: dict[str, list[ClassInfo]]
) -> list[EntryPoint]:
    """Public methods and properties of one PUBLIC module-level class.

    A `_Private` class is skipped: it is not reachable as a contract entry point
    from outside its module, so its verbs are internal structure rather than a
    seam. This also removes the whole family of stdlib overrides on private
    adapters (`handleError` on a `logging.Handler` subclass, say), which are
    dispatched by a framework this gate cannot see.
    """
    if node.name.startswith("_"):
        return []
    info = next(c for c in classes[node.name] if c.path == path)
    return [
        EntryPoint(
            path=path,
            owner=node.name,
            name=method,
            lineno=lineno,
            kind="protocol_verb" if info.is_protocol else kind,
        )
        for method, (lineno, kind) in info.methods.items()
        if not method.startswith("_")
    ]


def entry_points(
    trees: dict[str, ast.Module],
    scopes: dict[str, str],
    classes: dict[str, list[ClassInfo]],
) -> dict[str, EntryPoint]:
    """Every public entry point defined in SHIPPED code, by `sid`.

    Module-level functions and the public verbs of public module-level classes.
    Nested definitions are excluded — a function defined inside another function
    is a closure, not a seam. `Protocol` verbs ARE included: a declared seam verb
    nothing consumes is exactly the finding this gate is named for.
    """
    found: dict[str, EntryPoint] = {}
    for path, tree in trees.items():
        if scopes.get(path) != _SHIPPED:
            continue
        for point in _module_entry_points(path, tree, classes):
            found[point.sid] = point
    return found


def _module_entry_points(
    path: str, tree: ast.Module, classes: dict[str, list[ClassInfo]]
) -> list[EntryPoint]:
    """One shipped module's public entry points. Module BODY only, by design."""
    found: list[EntryPoint] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                found.append(EntryPoint(path, "", node.name, node.lineno, "function"))
        elif isinstance(node, ast.ClassDef):
            found.extend(_class_entry_points(path, node, classes))
    return found


# ===========================================================================
# THE REFERENCE WALK
# ===========================================================================


@dataclasses.dataclass
class Tally:
    """What the walk observed, per entry point."""

    shipped: int = 0
    gate: int = 0
    unresolved: int = 0
    #: References whose receiver RESOLVED to something that is not this symbol's
    #: class. The resolver actively ruling a candidate OUT, which is the work
    #: `_resolution_effect` proves is happening.
    ruled_out: int = 0


class _Walk(ast.NodeVisitor):
    # C0103: `visit_ClassDef` / `visit_Attribute` / `visit_Name` are dispatch
    # names `ast.NodeVisitor` looks up by node class name. Renaming them to
    # satisfy a case convention silently disables the visitor — the method is
    # never called and the walk quietly measures nothing, which is exactly the
    # vacuity this gate exists to refuse.
    # pylint: disable=invalid-name
    """Collect references to judged names, resolving receivers where possible.

    ONE class, two behaviours, selected by `resolve`. The name-only mode exists
    for `_resolution_effect` and is not a second implementation: running the
    SAME walk with resolution switched off is what makes the difference between
    the two answers attributable to resolution and to nothing else.
    """

    def __init__(self, engine: Analyzer, path: str, scope: str, resolve: bool) -> None:
        self.engine = engine
        self.path = path
        self.scope = scope
        self.resolve = resolve
        self.cls: str = ""
        self.locals: list[dict[str, str]] = [{}]

    # -- scope bookkeeping --------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track the enclosing class so `self.<verb>` resolves."""
        previous, self.cls = self.cls, node.name
        self.generic_visit(node)
        self.cls = previous

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        env = _param_types(node)
        for sub in ast.walk(node):
            if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                found = type_name(sub.annotation)
                if found:
                    env.setdefault(sub.target.id, found)
            elif isinstance(sub, ast.Assign):
                self._learn_local(env, sub)
        self.locals.append(env)
        self.generic_visit(node)
        self.locals.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    @staticmethod
    def _learn_local(env: dict[str, str], node: ast.Assign) -> None:
        """`x = Thing(...)` / `x = A() if c else B()` -> a local type binding."""
        if not isinstance(node.value, (ast.Call, ast.IfExp)):
            return
        found = type_name(node.value)
        if not found:
            return
        for target in node.targets:
            if isinstance(target, ast.Name):
                env.setdefault(target.id, found)

    # -- resolution ---------------------------------------------------------

    def receiver_type(self, node: ast.expr) -> str:
        """The type NAME of a receiver expression, or `''` when unresolved."""
        if isinstance(node, ast.Name):
            return self._name_type(node.id)
        if isinstance(node, ast.Attribute):
            return self._attr_type(node)
        return type_name(node) if isinstance(node, (ast.Call, ast.IfExp)) else ""

    def _name_type(self, ident: str) -> str:
        if ident in ("self", "cls"):
            return self.cls
        for env in reversed(self.locals):
            if ident in env:
                return env[ident]
        return ""

    def _attr_type(self, node: ast.Attribute) -> str:
        owner = self.receiver_type(node.value)
        if not owner:
            return ""
        for info in self.engine.classes.get(owner, ()):
            if node.attr in info.attrs:
                return info.attrs[node.attr]
        return ""

    # -- the two reference shapes -------------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """`obj.verb` — a call OR a property read. Both are references."""
        candidates = self.engine.by_name.get(node.attr)
        if candidates:
            self._record(candidates, node)
        self.generic_visit(node)

    def _record(self, candidates: tuple[str, ...], node: ast.Attribute) -> None:
        tname = self.receiver_type(node.value) if self.resolve else ""
        if not tname:
            for sid in candidates:
                self.engine.tally[sid].unresolved += 1
            return
        targets = self.engine.dispatch(tname)
        for sid in candidates:
            tally = self.engine.tally[sid]
            if self.engine.points[sid].owner in targets:
                setattr(tally, self.scope, getattr(tally, self.scope) + 1)
            else:
                tally.ruled_out += 1

    def visit_Name(self, node: ast.Name) -> None:
        """A bare name in LOAD position — how a module-level function is used.

        Deliberately unqualified: `from nixrisk.roll import advance` binds the
        function to a bare name, and a local variable that happens to share it
        is counted too. That is the conservative direction — it can only turn a
        finding into a CALLED.
        """
        if isinstance(node.ctx, ast.Load):
            for sid in self.engine.by_name.get(node.id, ()):
                if not self.engine.points[sid].owner:
                    tally = self.engine.tally[sid]
                    setattr(tally, self.scope, getattr(tally, self.scope) + 1)
        self.generic_visit(node)


# ===========================================================================
# THE ANALYSIS
# ===========================================================================


@dataclasses.dataclass
class Analyzer:  # pylint: disable=too-many-instance-attributes
    # Eight fields: three populations (trees, scopes, classes), two derived
    # tables (implementers, by_name), the judged set, the tally and the
    # dispatch memo. None is incidental state — each is one input the walk
    # needs, and folding two together would hide which one a defect moved.
    """One pass over the tree. `run()` is called TWICE per analysis.

    Once with receiver resolution ON — the answer — and once with it OFF, which
    is the non-vacuity differential §7.12 point 4 describes. The same object is
    reused deliberately: two Analyzers would be two populations, and the
    difference between the answers would no longer be attributable to the flag.
    """

    trees: dict[str, ast.Module]
    scopes: dict[str, str]
    classes: dict[str, list[ClassInfo]]
    implementers: dict[str, frozenset[str]]
    points: dict[str, EntryPoint]
    by_name: dict[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    tally: dict[str, Tally] = dataclasses.field(default_factory=dict)
    _cache: dict[str, frozenset[str]] = dataclasses.field(default_factory=dict)

    def dispatch(self, tname: str) -> frozenset[str]:
        """Memoised `dispatch_targets` — the walk asks for the same types often."""
        if tname not in self._cache:
            self._cache[tname] = dispatch_targets(
                tname, self.classes, self.implementers
            )
        return self._cache[tname]

    def run(self, *, resolve: bool) -> dict[str, str]:
        """Walk every in-scope module and return `sid -> verdict`."""
        self.by_name = {}
        for sid, point in self.points.items():
            self.by_name[point.name] = self.by_name.get(point.name, ()) + (sid,)
        self.tally = {sid: Tally() for sid in self.points}
        for path, tree in self.trees.items():
            scope = self.scopes.get(path, "")
            if scope:
                _Walk(self, path, scope, resolve).visit(tree)
        return {sid: self.verdict(sid) for sid in self.points}

    def verdict(self, sid: str) -> str:
        """CALLED > GATE_ONLY > CANNOT_RESOLVE > UNCALLED, in that order.

        The order is the whole safety argument. A single shipped call site
        settles it; a gate call downgrades to the diagnostic bucket; an
        UNRESOLVED reference SUPPRESSES the finding rather than creating one, so
        the resolver's ignorance costs findings and never invents them; and only
        a symbol nothing anywhere names at all is UNCALLED.
        """
        tally = self.tally[sid]
        if tally.shipped:
            return CALLED
        if tally.gate:
            return GATE_ONLY
        if tally.unresolved:
            return CANNOT_RESOLVE
        return UNCALLED


# ===========================================================================
# THE BASELINE — a one-way ratchet with a git-derived high-water mark.
#
# The SHAPE is `check_artifact_gate_coverage`'s, deliberately and not by
# accident: that gate already argued out where a ratchet's prior mark must live
# (not in the file the edit under judgement is editing, and not in a second
# config file beside it), and inventing a second mechanism for one property is
# what doctrine C.9 forbids. What is NOT shared is the CODE — see CHECK-DEBT
# D3.202, which records the duplication rather than hiding it.
# ===========================================================================


@dataclasses.dataclass(frozen=True)
class Row:
    """One accepted finding: an entry point with no shipped caller."""

    #: The bucket MEASURED when this row was written. Compared on every run.
    bucket: str = ""
    #: The single arc that admitted this symbol to the accepted set. A RECEIPT
    #: (backward-looking), never a promise — so a completed arc is the normal
    #: and correct value here.
    admitted: str = ""


@dataclasses.dataclass(frozen=True)
class Module:
    """One shipped module's accepted findings, with ONE owner and ONE reason."""

    #: The arc that will WIRE these entry points, or `unassigned`. A
    #: forward-looking promise, so `guard_owner_defect` applies with the
    #: completion set — and `unassigned` is HONEST (doctrine B.3) and produces
    #: CANNOT_MEASURE rather than a GUARDED that nobody owes.
    owner: str = ""
    #: Why this module's entry points have no production caller. Required.
    reason: str = ""
    rows: dict[str, Row] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Baseline:
    """The ratchet file, parsed. `error` non-empty means it could not be read."""

    modules: dict[str, Module] = dataclasses.field(default_factory=dict)
    error: str = ""

    @property
    def accepted(self) -> frozenset[str]:
        """Every accepted `sid` — the quantity the ratchet judges."""
        return frozenset(
            f"{path}::{symbol}"
            for path, module in self.modules.items()
            for symbol in module.rows
        )

    def row(self, sid: str) -> Row | None:
        """The accepted row for one `sid`, or `None`."""
        path, _, symbol = sid.partition("::")
        module = self.modules.get(path)
        return module.rows.get(symbol) if module else None


UNASSIGNED = "unassigned"


def parse_baseline(text: str, where: str) -> Baseline:
    """Parse baseline JSON. Shared by the working tree and by `git show`."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return Baseline(error=f"{where} unreadable: {exc!r}")
    if not isinstance(payload, dict):
        return Baseline(error=f"{where} is not a JSON object")
    raw = payload.get("modules")
    if not isinstance(raw, dict):
        return Baseline(error=f"{where}: `modules` is not a JSON object")
    modules: dict[str, Module] = {}
    for path, entry in raw.items():
        if not isinstance(entry, dict):
            return Baseline(error=f"{where}:{path} is not a JSON object")
        symbols = entry.get("symbols")
        if not isinstance(symbols, dict):
            return Baseline(error=f"{where}:{path}: `symbols` is not a JSON object")
        modules[str(path)] = Module(
            owner=str(entry.get("owner", "")),
            reason=str(entry.get("reason", "")),
            rows={
                str(name): Row(
                    bucket=str(row.get("bucket", "")) if isinstance(row, dict) else "",
                    admitted=(
                        str(row.get("admitted", "")) if isinstance(row, dict) else ""
                    ),
                )
                for name, row in symbols.items()
            },
        )
    return Baseline(modules=modules)


def load_baseline(home: Path) -> Baseline:
    """Read the baseline as it stands in the WORKING TREE."""
    path = home / BASELINE
    if not path.is_file():
        return Baseline(error=f"{BASELINE} absent")
    try:
        return parse_baseline(path.read_text(encoding="utf-8"), BASELINE)
    except OSError as exc:
        return Baseline(error=f"{BASELINE} unreadable: {exc!r}")


@dataclasses.dataclass(frozen=True)
class History:
    """Every COMMITTED revision of the baseline, oldest first."""

    revisions: tuple[tuple[str, Baseline], ...] = ()
    truncated: bool = False
    error: str = ""


def committed_history(home: Path) -> History:
    """Read every committed revision of the baseline, oldest first.

    **A revision that cannot be read is an ERROR, never a skip.** A silently
    skipped revision might be exactly the tightest one, and a high-water mark
    that quietly rises is the vacuous pass a ratchet exists to refuse.

    A baseline with NO history is an ERROR too, and on the arc that CREATES this
    file that is the correct and expected verdict: until the file is committed,
    nothing on this box can show that the accepted set has not grown.
    """
    listing, error = _git(
        home, "log", f"-{_HISTORY_LIMIT}", "--format=%H", "--", BASELINE
    )
    if error:
        return History(error=error)
    shas = [line.strip() for line in listing.splitlines() if line.strip()]
    if not shas:
        return History(
            error=(
                f"{BASELINE} has no commit history — the ratchet has nothing to "
                "ratchet against, so the accepted set cannot be shown not to "
                "have grown. Expected on the arc that creates the file"
            )
        )
    revisions: list[tuple[str, Baseline]] = []
    for sha in reversed(shas):
        blob, blob_error = _git(home, "show", f"{sha}:{BASELINE}")
        if blob_error:
            return History(error=f"{blob_error} — cannot establish the high-water mark")
        revision = parse_baseline(blob, f"{BASELINE}@{sha[:12]}")
        if revision.error:
            return History(error=f"{revision.error} — cannot establish the mark")
        revisions.append((sha, revision))
    return History(revisions=tuple(revisions), truncated=len(shas) >= _HISTORY_LIMIT)


def mark_from(history: History) -> tuple[frozenset[str], str]:
    """The minimum-over-history accepted set, and the revision it came from.

    The MINIMUM over the whole history rather than `HEAD`: `HEAD` alone would
    let an addition be laundered by committing it, since one commit later the
    addition IS the prior mark.
    """
    best: frozenset[str] | None = None
    best_sha = ""
    for sha, revision in history.revisions:
        if best is None or len(revision.accepted) < len(best):
            best, best_sha = revision.accepted, sha
    return (best or frozenset()), best_sha


# ===========================================================================
# THE ARMS. Each returns `[(site, why)]`.
# ===========================================================================


def growth_defects(
    baseline: Baseline, mark: frozenset[str], sha: str
) -> list[tuple[str, str]]:
    """Every accepted entry added since the tightest committed revision.

    The set may SHRINK freely — that is the point of a ratchet. An ADDITION is
    permitted only when the baseline names the arc that admitted it, under the
    same grammar `validate_result` enforces on `guard_owner`. SHAPE only: no
    `completed` argument, because `admitted` is a receipt and passing the
    completion set would redden every honest entry at the next arc boundary.
    """
    defects: list[tuple[str, str]] = []
    for sid in sorted(baseline.accepted - mark):
        row = baseline.row(sid)
        defect = guard_owner_defect(row.admitted if row else "")
        if defect:
            defects.append(
                (
                    f"{BASELINE}:{sid}:admitted",
                    (
                        f"{sid!r} was ADDED to the accepted set since the "
                        f"tightest committed revision {sha[:12]} ({len(mark)} "
                        f"entries); a ratchet may only shrink, and an addition "
                        f"requires a named arc in `admitted` — {defect}"
                    ),
                )
            )
    return defects


#: How many findings each arm RENDERS. A cap is necessary — an operator cannot
#: read four hundred rows — and a SILENT cap is a lie: it makes the list an
#: operator reads look like the whole truth. MEASURED by ARC 036 sub-agent D:
#: 47 un-baselined findings existed and 25 rendered, so 22 were invisible,
#: including five of D3.214's own "carried BY NAME" seam entries and every one
#: of a whole new module's fifteen. The counters moved; the rows did not. It bit
#: the ARC 036 integrator again on the merged tree, where exactly 25 rows
#: rendered while five sub-agents' surface was in flight.
#:
#: `_capped` is the repair and it is deliberately not a bigger number: the cap
#: stays, and what changes is that the list SAYS when it truncated. Doctrine:
#: no silent caps — if a run bounds its own coverage, it prints what it dropped.
#: CHECK-DEBT D3.253.
RENDER_CAP = 25


def _capped(defects: list[tuple[str, str]], arm: str) -> list[tuple[str, str]]:
    """At most `RENDER_CAP` rows, and a LOUD row when there were more."""
    if len(defects) <= RENDER_CAP:
        return defects
    hidden = len(defects) - RENDER_CAP
    return defects[:RENDER_CAP] + [
        (
            f"{BASELINE}:{arm}:truncated",
            (
                f"{hidden} further finding(s) NOT SHOWN — {len(defects)} were "
                f"measured and {RENDER_CAP} render. The rows above are not the "
                "whole set, and reading them as one is how a whole module's "
                "surface went invisible for two consecutive runs (D3.253)"
            ),
        )
    ]


def regression_defects(
    baseline: Baseline, findings: dict[str, str]
) -> list[tuple[str, str]]:
    """A finding the baseline does not accept. THE arm this gate exists for."""
    rows = [
        (
            sid,
            (
                f"{bucket.upper()}: this public entry point has NO call site in "
                "shipped code and is not in the accepted baseline. Wire it, "
                "delete it, or admit it by name"
            ),
        )
        for sid, bucket in sorted(findings.items())
        if sid not in baseline.accepted
    ]
    return _capped(rows, "regression")


def rot_defects(
    baseline: Baseline, findings: dict[str, str], points: dict[str, EntryPoint]
) -> list[tuple[str, str]]:
    """An accepted entry that is no longer a finding. The ratchet may only shrink.

    Two causes, distinguished because the repair differs: the symbol ACQUIRED a
    caller (good news the baseline must record by shrinking), or the symbol is
    GONE (renamed or deleted, and the row is now describing nothing).
    """
    defects: list[tuple[str, str]] = []
    for sid in sorted(baseline.accepted - set(findings)):
        gone = sid not in points
        defects.append(
            (
                f"{BASELINE}:{sid}",
                (
                    f"the baseline accepts {sid!r} as uncalled, but that symbol "
                    "no longer exists — tighten the baseline (a ratchet may "
                    "only shrink, and a row describing nothing is a suppression "
                    "entry)"
                    if gone
                    else (
                        f"the baseline accepts {sid!r} as uncalled, but shipped "
                        "code now CALLS it — tighten the baseline (a ratchet may "
                        "only shrink)"
                    )
                ),
            )
        )
    return _capped(defects, "rot")


def bucket_defects(
    baseline: Baseline, findings: dict[str, str]
) -> list[tuple[str, str]]:
    """The recorded bucket, compared against the measured one on every run.

    An unchecked label rots into decoration, and the `uncalled` / `gate_only`
    distinction is the whole diagnostic value of this gate: `gate_only` is
    literally the ARC 033 shape (*the only thing that constructs it is the check
    that measures it*), and it must not silently become interchangeable with
    *nothing names it at all*.
    """
    defects: list[tuple[str, str]] = []
    for sid, measured in sorted(findings.items()):
        row = baseline.row(sid)
        if row is None:
            continue
        if row.bucket not in BUCKETS:
            defects.append(
                (
                    f"{BASELINE}:{sid}:bucket",
                    (
                        f"`bucket` is {row.bucket!r}; expected one of "
                        f"{list(BUCKETS)}. An unclassified row cannot be checked"
                    ),
                )
            )
        elif row.bucket != measured:
            defects.append(
                (
                    f"{BASELINE}:{sid}:bucket",
                    (
                        f"recorded {row.bucket!r}, MEASURED {measured!r} — the "
                        "row has stopped describing what is true"
                    ),
                )
            )
    return _capped(defects, "bucket")


def shape_defects(baseline: Baseline) -> list[tuple[str, str]]:
    """Every module states its case. A module row with no reason is not a row."""
    return [
        (
            f"{BASELINE}:{path}:reason",
            (
                "no `reason` — each module states why its entry points have no "
                "production caller; a row that cannot say why is a suppression "
                "entry"
            ),
        )
        for path, module in sorted(baseline.modules.items())
        if not module.reason.strip()
    ]


def assignment_defects(
    baseline: Baseline,
    head: dict[str, str],
    completed: frozenset[int],
    live: int | None,
) -> list[tuple[str, str]]:
    """STANDING RULE §0g — an owner being ASSIGNED right now, judged now.

    A module whose owner differs from the value committed at `HEAD` is an
    assignment that exists only in this working tree. `unassigned` is exempt: it
    is not a promise, so there is no promise to judge, and refusing it here
    would push every honest row into naming an arc that cannot pay — which is
    the furniture doctrine B.3 refuses.
    """
    defects: list[tuple[str, str]] = []
    for path, module in sorted(baseline.modules.items()):
        owner = module.owner.strip()
        if owner == UNASSIGNED or head.get(path, "") == owner:
            continue
        defect = guard_owner_assignment_defect(owner, completed, live)
        if defect:
            defects.append((f"{BASELINE}:{path}:owner", defect))
    return defects


def owner_deferrals(
    baseline: Baseline, completed: frozenset[int]
) -> list[tuple[str, str]]:
    """The READ rule, per module. `unassigned` defers HONESTLY rather than passing.

    Doctrine B.3 calls `unassigned` honest, and it is — but honest is not the
    same as owned, and a backlog nobody has committed to wiring may not be
    certified. Both cases defer; they defer with different words, so an operator
    can tell *nobody has taken this* from *the arc that took it is over*.
    """
    defects: list[tuple[str, str]] = []
    for path, module in sorted(baseline.modules.items()):
        owner = module.owner.strip()
        if owner == UNASSIGNED:
            defects.append(
                (
                    f"{BASELINE}:{path}:owner",
                    (
                        "`unassigned` — honest (doctrine B.3) and NOT owned. No "
                        "arc has committed to wiring these entry points, so the "
                        "gate withholds certification rather than guarding a "
                        "promise nobody made"
                    ),
                )
            )
            continue
        defect = guard_owner_defect(owner, completed)
        if defect:
            defects.append((f"{BASELINE}:{path}:owner", defect))
    return defects


def render(pairs: list[tuple[str, str]]) -> str:
    """`[(site, why)]` -> one detail line, IDENTICAL reasons grouped by site."""
    grouped: dict[str, list[str]] = {}
    for site, why in pairs:
        grouped.setdefault(why, []).append(site)
    return "; ".join(
        (
            sites[0]
            if len(sites) == 1
            else f"{len(sites)} row(s) [{', '.join(sites[:12])}]"
        )
        + f": {why}"
        for why, sites in grouped.items()
    )


# ===========================================================================
# THE RUN
# ===========================================================================


@dataclasses.dataclass(frozen=True)
class Measured:
    """One run's raw analysis, so the renderers take one argument."""

    scopes: dict[str, str]
    points: dict[str, EntryPoint]
    verdicts: dict[str, str]
    findings: dict[str, str]
    name_only_findings: frozenset[str]
    ruled_out: int

    def count(self, verdict: str) -> int:
        """How many judged symbols landed in one bucket."""
        return sum(1 for value in self.verdicts.values() if value == verdict)

    @property
    def shipped_modules(self) -> int:
        """The population whose entry points are JUDGED."""
        return sum(1 for scope in self.scopes.values() if scope == _SHIPPED)


def _parse_trees(home: Path, scopes: dict[str, str]) -> tuple[dict, str]:
    """Every in-scope module parsed. A file that will not parse is an ERROR.

    Never a skip: the skipped module could be the only caller of half the tree,
    and a finding set computed over a smaller population than it claims is a
    measurement of a different repository.
    """
    trees: dict[str, ast.Module] = {}
    for path in sorted(scopes):
        try:
            source = (home / path).read_text(encoding="utf-8")
            trees[path] = ast.parse(source, filename=path)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            return {}, f"{path} could not be parsed: {exc!r}"
    return trees, ""


def analyse(home: Path) -> tuple[Measured | None, str]:
    """The whole measurement. Returns `(Measured, '')` or `(None, refusal)`.

    Exported under a plain name because the can-fail suite drives it directly
    against scratch trees whose correct answer is known — a suite that could
    only observe this gate's exit code would be asserting the very thing
    check-contract rule 11 forbids.
    """
    scopes, error = _in_scope(home)
    if error:
        return None, error
    trees, parse_error = _parse_trees(home, scopes)
    if parse_error:
        return None, parse_error
    classes = build_classes(trees)
    implementers = protocol_implementers(classes)
    points = entry_points(trees, scopes, classes)
    engine = Analyzer(trees, scopes, classes, implementers, points)
    verdicts = engine.run(resolve=True)
    ruled_out = sum(tally.ruled_out for tally in engine.tally.values())
    findings = {sid: v for sid, v in verdicts.items() if v in BUCKETS}
    # THE NON-VACUITY DIFFERENTIAL (§7.12 point 4). Identical walk, receiver
    # resolution OFF. Recomputed every run rather than asserted once.
    name_only = engine.run(resolve=False)
    return (
        Measured(
            scopes=scopes,
            points=points,
            verdicts=verdicts,
            findings=findings,
            name_only_findings=frozenset(
                sid for sid, v in name_only.items() if v in BUCKETS
            ),
            ruled_out=ruled_out,
        ),
        "",
    )


def vacuity_refusal(state: Measured) -> str:
    """Why this run may not be reported at all, or `''`. §7.12 points 1-4."""
    if state.shipped_modules < MIN_CREDIBLE_MODULES:
        return (
            f"only {state.shipped_modules} shipped module(s) enumerated, below "
            f"the credibility floor of {MIN_CREDIBLE_MODULES} — a tiny "
            "enumeration would make every entry point trivially called"
        )
    if len(state.points) < MIN_CREDIBLE_ENTRY_POINTS:
        return (
            f"only {len(state.points)} public entry point(s) judged, below the "
            f"credibility floor of {MIN_CREDIBLE_ENTRY_POINTS}"
        )
    called, unresolved = state.count(CALLED), state.count(CANNOT_RESOLVE)
    if called < unresolved:
        return (
            f"the resolver settled {called} call site(s) and could not settle "
            f"{unresolved} — a resolver that has stopped working collapses the "
            "first number and inflates the second, and this run cannot tell "
            "that apart from a tree nobody calls"
        )
    delta = len(state.findings) - len(state.name_only_findings)
    if delta <= 0:
        return (
            "RECEIVER RESOLUTION CHANGED NOTHING: re-running the identical walk "
            f"with resolution disabled produced {len(state.name_only_findings)} "
            f"finding(s) against {len(state.findings)}. Resolution is what "
            "separates a real call from a same-named attribute on an unrelated "
            "object, and a run in which it made no difference has not shown it "
            "is working"
        )
    return ""


def evidence_for(state: Measured, baseline: Baseline, mark: tuple) -> str:
    """What was measured, on every run, including what it does NOT prove."""
    only_by_resolution = sorted(state.findings.keys() - state.name_only_findings)
    return (
        f"{state.shipped_modules} shipped module(s) + "
        f"{sum(1 for s in state.scopes.values() if s == _GATE)} gate module(s); "
        f"{len(state.points)} public entry point(s) judged; "
        f"{state.count(CALLED)} CALLED in shipped code, "
        f"{state.count(GATE_ONLY)} GATE-ONLY, {state.count(UNCALLED)} UNCALLED, "
        f"{state.count(CANNOT_RESOLVE)} CANNOT-RESOLVE (reported, never counted "
        f"as a finding); {state.ruled_out} reference(s) RULED OUT by receiver "
        f"type; baseline accepts {len(baseline.accepted)} finding(s) across "
        f"{len(baseline.modules)} module(s); ratchet high-water mark "
        f"{len(mark[0])} at committed revision {mark[1][:12] or 'none'}. "
        f"NON-VACUITY: resolution OFF yields {len(state.name_only_findings)} "
        f"finding(s) against {len(state.findings)} ON — "
        f"{len(only_by_resolution)} finding(s) exist ONLY because a receiver was "
        f"resolved ({', '.join(only_by_resolution[:4]) or 'none'}). "
        "LIMITS: dynamic dispatch (getattr, callable tables, strings) is "
        "INVISIBLE here, and a call SITE is not proof the site executes. Do not "
        "read a green as proof that anything runs."
    )


def _fail(state, baseline, mark, defects) -> CheckResult:
    """The FAIL verdict, with every site named."""
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(site for site, _ in defects)[:4000],
        evidence=evidence_for(state, baseline, mark),
        detail=render(defects),
    )


def _guard_of_record(baseline: Baseline) -> str:
    """The single arc `CheckResult.guard_owner` can hold, out of many.

    A STATED LIMITATION, not a design — the same one `check_artifact_gate_
    coverage` records as D3.63. The full per-module map is in `detail` on every
    run; what is lost is reading the owner off the summary line.
    """
    owners = {
        module.owner.strip()
        for module in baseline.modules.values()
        if module.owner.strip() and module.owner.strip() != UNASSIGNED
    }
    return min(owners, default="")


def _collect_defects(state, baseline, history) -> list[tuple[str, str]]:
    """Every FAIL-class arm, all evaluated, so one defect never hides fifteen."""
    mark, mark_sha = mark_from(history)
    defects = regression_defects(baseline, state.findings)
    defects.extend(rot_defects(baseline, state.findings, state.points))
    defects.extend(growth_defects(baseline, mark, mark_sha))
    defects.extend(bucket_defects(baseline, state.findings))
    defects.extend(shape_defects(baseline))
    return defects


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Enumerate public entry points, find the ones nothing ships a call to.

    Five named outcomes: the refusal (nothing credible was enumerated), the
    failure (the ratchet was violated), the deferral (the backlog has no owner
    who can pay), the guarded deferral (it has one), and the pass (there is no
    backlog at all).
    """
    home = Path(ctx.nix_home)
    try:
        state, refusal = analyse(home)
        if state is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=refusal)
        vacuous = vacuity_refusal(state)
        if vacuous:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=vacuous)
        baseline = load_baseline(home)
        history = committed_history(home)
        mark = mark_from(history)
        evidence = evidence_for(state, baseline, mark)
        for blocker in (baseline.error, history.error):
            if blocker:
                return CheckResult(
                    name=NAME,
                    status=Status.CANNOT_MEASURE,
                    evidence=evidence,
                    detail=blocker,
                )
        return _judge(state, baseline, history, home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


def _head_owners(history: History) -> dict[str, str]:
    """Each module's owner as most recently COMMITTED. `{}` with no history."""
    if not history.revisions:
        return {}
    _sha, newest = history.revisions[-1]
    return {path: module.owner.strip() for path, module in newest.modules.items()}


def _judge(
    state: Measured, baseline: Baseline, history: History, home: Path
) -> CheckResult:
    """The verdict, once everything is measured and readable."""
    mark = mark_from(history)
    evidence = evidence_for(state, baseline, mark)
    completed, completion_error = completed_arcs(home)
    if completion_error:
        # FAIL CLOSED: without the completion record a live owner cannot be told
        # from a dead one, and "probably still open" is the assumption that let
        # a completed arc stand as an owner through a whole arc (D3.40).
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail=f"{BASELINE} owners cannot be judged — {completion_error}",
        )
    live, live_error = in_flight_arc(home)
    defects = _collect_defects(state, baseline, history)
    defects.extend(assignment_defects(baseline, _head_owners(history), completed, live))
    if defects:
        return _fail(state, baseline, mark, defects)
    deferrals = owner_deferrals(baseline, completed)
    if live_error and baseline.modules:
        deferrals.append((f"{BASELINE}:modules", live_error))
    if deferrals:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail=render(deferrals),
        )
    if baseline.modules:
        return CheckResult(
            name=NAME,
            status=Status.GUARDED,
            evidence=evidence,
            guard_owner=_guard_of_record(baseline),
            detail="; ".join(
                f"{path} -> {module.owner.strip()} ({len(module.rows)} entry "
                f"point(s) with no shipped caller)"
                for path, module in sorted(baseline.modules.items())
            ),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


# Deliberately duplicated across every checks/check_*.py (§4.2).
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
