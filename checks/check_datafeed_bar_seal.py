#!/usr/bin/env python3
"""Once broker-datafeed publishes a series value it is sealed: never rewritten
in place, and a revision is a DECLARED event rather than a silent overwrite.

CHECK-DEBT D1.14. ONE gate, ONE property (`nix_check_contract.md` §5.5,
doctrine C.9): *the lifecycle of published series data on the broker-datafeed
path.* The boundary against its sibling is stated in both docstrings so it
survives the next author:

  * `check_datafeed_granted_mode` owns the OBSERVATION of the feed's mode —
    what the venue granted and whether "unread" can be told from "real-time".
    It never reads a bar.
  * THIS gate owns what happens to a value AFTER it is published. It never
    reads `marketDataType`.

==============================================================================
CHECK-RULE 8 / DOCTRINE C.9 — THE DECISION, AND THE ARGUMENT FOR IT
==============================================================================
*"Extend an instrument that already owns a property; never build a second."*
`checks/registry.json` was surveyed before a line of this file was written.
Registered at ARC 021's base commit: `check_python_runtime`, `check_venv`,
`check_node_identity`, `check_python_deps`, `check_ibgateway_config`,
`check_ibgateway_service`, `check_order_path_bans`, `check_spec_citations`,
`check_hook_suite`, `check_derived_claims`.

**No registered gate owns bar lifecycle, series publication, or datafeed
value immutability.** The two candidates and why each was rejected:

  `check_order_path_bans` — the nearest in MECHANISM (an AST walk over
      `scripts/` deriving its own scope) and the furthest in SUBJECT. It owns
      *the order path contains no retry machinery and no loop-blocking call*.
      Extending it would make one instrument own two unrelated properties, and
      worse, it would give that instrument a scope spanning BOTH §2A libraries
      — which is precisely the coupling
      `nics_risk_subsystem_spec_v1.3.md` §2A:105 invariant 3 forbids
      ("order and datafeed contracts are disjoint — no shared object, so a
      datafeed fault cannot reach the order library"). A gate whose scope
      derivation cannot say which library it is talking about is one refactor
      from reddening spec-mandated poller behaviour on the datafeed side, which
      that gate's own docstring names as the failure it must not commit.

  `check_datafeed_granted_mode` — the nearest in SUBJECT (same module set) and
      a different property. Merging them would produce a single verdict over
      two independent facts, so a mode defect and a seal defect would be
      indistinguishable in `verify.py`'s one-line-per-check output, and one
      arm's CANNOT_MEASURE would suppress the other's PASS. §5.5's remedy for
      exactly this case is a stated split, not a merged gate.

**So: a new gate, and the C.9 residual is paid for rather than waved away.**
The two gates each carry a datafeed-scope derivation, because
`nix_check_contract.md` §4.2 requires every `checks/check_*.py` be
independently runnable and therefore forbids the shared helper that would keep
the two identical. Two derivations of one scope is the drift C.9 warns about.
It is closed mechanically instead of by discipline: the derived-claims registry
carries `datafeed_scope_files`, whose two sources are the two gates' own
`--print-scope-count`, so the day they disagree is RED.

==============================================================================
THE DEFECT
==============================================================================
Stage 0's feed is delayed AND POLLED. `reqHistoricalTicks` is re-requestable
and a later poll can return REVISED values for a period already served —
`scripts/broker/ibkr_mapping.py` grades `subscribe / on_tick` a GAP for exactly
this reason, and ARC 013 measured the ~600 s pipeline delay that makes the
re-poll routine rather than exotic.

A builder that overwrites a bar it already published makes every downstream
consumer's history unreproducible, and — this is the part that makes it
expensive — **the revision arrives looking exactly like new data.** Nothing
distinguishes "the venue corrected itself" from "time passed" unless the seal
is enforced and the correction is declared.

`nics_risk_subsystem_spec_v1.3.md` §2A:91 puts bar construction in capture.py,
not in broker-order — so the seal belongs on the capture side of the datafeed
seam, which is the scope this gate derives.

==============================================================================
SCOPE — DERIVED FROM THE TREE'S CONTENT, NOT FROM A PATH SOMEONE TYPED
==============================================================================
`debug.md` §8 failure mode #14. There is no datafeed file list in this module.

  ROSTER — `DATAFEED_PORT_VERBS` and `DATAFEED_EVENTS` are read by AST out of
      whichever module declares them. Never typed here.

  DATAFEED MODULES — every module under `SCAN_ROOTS` that declares the roster
      or defines a class carrying at least `DATAFEED_QUORUM` roster verbs as
      methods. An adapter or builder written anywhere joins the scan by being
      written.

  PUBLISHED TYPES — the classes the datafeed hands ACROSS the seam, derived
      from annotations rather than named: the parameter and return annotations
      of the seam's datafeed sink events and port verbs, restricted to classes
      declared in a datafeed module. Today that derivation returns `FeedLag`,
      which is the mechanism working on the only published type that exists
      yet.

  THE SERIES SURFACE — the subject of the SEAL, and its absence is why this
      gate is CANNOT_MEASURE in ARC 021's own worktree. It is the union of:
        (a) datafeed events the seam declares that §2A does not — read by
            parsing the frozen spec's own datafeed event bullets and
            subtracting, so a bar-publication event added to `DATAFEED_EVENTS`
            registers automatically; and
        (b) SERIES STORES: a subscript assignment into a `self` attribute whose
            stored VALUE is a published type. That is deliberately narrow. A
            broad rule — "any `self._x[k] = v`" — would redden a subscription
            registry, which legitimately overwrites `self._tickers[symbol]`
            every re-subscribe, and doctrine B.4 says a gate that reddens the
            correct implementation of its own subject is broken, not strict.

  TEST DIRECTORIES are excluded and the exclusion is derived from `testpaths`
      in `pyproject.toml`; anything excluded is printed as an advisory every
      run.

==============================================================================
THREE ARMS
==============================================================================
ARM 1 — IMMUTABLE BY CONSTRUCTION. Every published type is a frozen dataclass,
    a `NamedTuple`, or a tuple. A mutable published value cannot be sealed by
    any amount of discipline downstream: the consumer holds a reference and the
    producer can still reach it.

ARM 2 — NO UNGUARDED OVERWRITE. A series store must be dominated by a
    membership test on the same key against the same container
    (`if key not in self._bars:` / `if key in self._bars:`). An unguarded store
    is the silent rewrite, stated in the shape it actually takes in source.

ARM 3 — A REVISION IS DECLARED. Where the guard exists, the enclosing function
    must reach a datafeed EVENT emission — a call named after a member of
    `DATAFEED_EVENTS`. A guard that detects the revision and returns is worse
    than no guard: it makes the overwrite impossible AND the correction
    invisible, and the venue's changed story is then unrecoverable. The event
    roster is derived, so an event added for revisions satisfies this by being
    declared at the seam, which is where a consumer can find it.

ARM 4 — BEHAVIOURAL, and it executes real code rather than reading it. Every
    published type is CONSTRUCTED twice from synthesised field values differing
    in exactly one field, and three things are asserted on the real objects:
      (i)   writing a field raises — the seal is enforced by the runtime, not
            by convention;
      (ii)  the two instances are NOT equal — a revision is REPRESENTABLE.
            `debug.md` §7.12 instances 4 and 5 are both cases where the
            instrument could not express the difference it was asked to detect;
            a published type with no value equality cannot express "the venue
            changed its story", and non-vacuity here means asserting the two
            synthesised values genuinely differ BEFORE asserting anything about
            immutability. `nix_check_contract.md` §5.1 step 2.
      (iii) two equal-valued instances ARE equal — without which (ii) is
            satisfied trivially by identity comparison and proves nothing.

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
Six conditions, each stated so it could be planted.

 1. NO SERIES SURFACE EXISTS — no Nix-added datafeed event and no series store
    — so arms 2 and 3 walk an empty set and report no violations. THIS IS THE
    GATE'S STATE IN ARC 021's OWN WORKTREE and it is the condition that would
    have produced a false green.
    GUARDED: an empty series surface is CANNOT_MEASURE (exit 2), never PASS
    (`nix_check_contract.md` §5.3). Arms 1 and 4 can measure `FeedLag` today
    and are deliberately NOT allowed to carry a PASS on their own, because
    "the datafeed's one published value type is frozen" is not the D1.14
    property and letting it report PASS would close a debt that is still owed.

 2. THE BAR TYPE IS NEVER DECLARED AT THE SEAM. A builder that publishes bars
    through a return value or a private queue, with no annotation reaching the
    seam's sink or port, is invisible to the published-type derivation, so its
    stores are not series stores and arms 2/3 never see them.
    PARTIALLY GUARDED: condition 1 then holds and the verdict is
    CANNOT_MEASURE, so the gate never claims to have checked. It is not fully
    closed, and closing it means deciding that anything shaped like a bar is a
    bar, which is a name heuristic — `debug.md` §7.4's stale literal anchor
    with extra steps. The correct closure is at the seam: a published value
    that is not declared at the seam is an invariant-1 problem before it is a
    seal problem.

 3. THE PUBLISHED TYPE IS FROZEN BUT HOLDS A MUTABLE MEMBER — a `list` field on
    a frozen dataclass is reassignment-proof and still mutable in place.
    UNGUARDED, NARROWED: arm 4(i) proves the field cannot be REBOUND, which is
    what `frozen=True` actually buys, and does not prove deep immutability.
    Plantable: give a published type a `list[float]` field and mutate it. The
    closure is a recursive value-type check over field annotations; it is not
    written because no published type in this tree has a container field today,
    and a rule with no subject asserts nothing until the day it blocks
    something legitimate. Recorded, not half-built.

 4. THE GUARD IS PRESENT AND WRONG — `if key in self._bars:` guarding the store
    on the branch where the key IS present, i.e. overwriting exactly when it
    must not.
    UNGUARDED. Arm 2 proves a membership test dominates the store; it does not
    prove the polarity. Distinguishing the two needs branch-sense analysis
    through `not`, `else`, and early-return inversions, and a wrong answer
    there reddens correct code. Arm 4(i) is the compensating control: a frozen
    published type cannot be rewritten in place whatever the guard's polarity,
    so this condition costs a silent REPLACEMENT of a sealed entry, not a
    silent MUTATION of one. Named because it is not zero.

 5. THE EVENT ROSTER IS EMPTY OR THE SEAM MOVES. Arm 3 resolves emissions
    against `DATAFEED_EVENTS`; if that constant is deleted the arm has nothing
    to match and every revision path looks undeclared.
    GUARDED: an empty roster is CANNOT_MEASURE before any arm runs, not PASS.

 6. `SCAN_ROOTS` DOES NOT CONTAIN THE BUILDER. Code outside `scripts/` is not
    walked at all. UNGUARDED, the same residual `check_order_path_bans` states,
    and stated here for the same reason: an undocumented limit is one refactor
    away from being met silently.

 7. THE STORED VALUE IS ALIASED BEYOND ONE HOP. A series store is recognised
    when its value is a construction of a published type or a local name that
    one such construction was assigned to. `bars = [Bar(...)]; self._x[k] =
    bars[0]`, or a value returned from a helper, is not recognised, and the
    store falls out of the surface.
    UNGUARDED, NARROWED TO ONE HOP, and this condition exists because the
    zero-hop version was MEASURED: see `_local_published_names`, where the
    gate's own can-fail run produced a PASS over an empty store set against a
    builder written to be correct. That is the honest reason the hop is here —
    it was not foreseen, it was caught.
"""

from __future__ import annotations

import ast
import enum
import re
import tomllib
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801: the §4.2 `__main__` block and the crash handler are mandated to be the
# same text in every check; the only deduplication is the helper §4.2 forbids.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_datafeed_bar_seal"

SCAN_ROOTS: tuple[str, ...] = ("scripts",)
SKIP_DIRS: frozenset[str] = frozenset({".venv", "__pycache__", ".git", "graphify-out"})

ROSTER_CONST = "DATAFEED_PORT_VERBS"
EVENTS_CONST = "DATAFEED_EVENTS"
DATAFEED_QUORUM = 3

# The frozen spec, and the heading whose event bullets define what is NOT a Nix
# addition. Both are coordinates into a file that is never edited, and
# `check_spec_citations` range-checks them.
SPEC_REL = "docs/nics_risk_subsystem_spec_v1.3.md"
SPEC_DATAFEED_HEADING = "### broker-datafeed"

# Base classes whose instances cannot be rewritten in place. `Enum` and its
# stdlib refinements are here on a MEASURED correction, not by assumption: this
# gate's first run reddened `FeedState`, an `enum.Enum` published across the
# datafeed seam, on the grounds that it carries no `frozen=True`. An enum member
# is a singleton and there is nothing on it to rewrite, so that was a gate
# failing on the CORRECT implementation of its own subject — doctrine B.4 calls
# that broken rather than strict, and the repair belongs to the gate's logic.
IMMUTABLE_BASES: frozenset[str] = frozenset(
    {"NamedTuple", "tuple", "Enum", "StrEnum", "IntEnum", "IntFlag", "Flag"}
)


class Roster(NamedTuple):
    """The seam's datafeed declaration, read out of the tree."""

    rel: str
    verbs: tuple[str, ...]
    events: tuple[str, ...]


class Surface(NamedTuple):
    """What one run of the scope derivation found."""

    published: list[str]
    stores: list[Store]
    added: list[str]
    advisories: list[str]


class Store(NamedTuple):
    """One subscript assignment into a `self` attribute holding a published type."""

    rel: str
    func: str
    container: str
    line: int
    guarded: bool
    declares: bool


# --------------------------------------------------------------------------
# TREE WALK — identical intent to the sibling gate, deliberately not shared
# (§4.2). `datafeed_scope_files` is what stops the two drifting.
# --------------------------------------------------------------------------
def _testpaths(home: Path) -> tuple[str, ...]:
    cfg = home / "pyproject.toml"
    if not cfg.is_file():
        return ()
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    ini = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return tuple(ini.get("testpaths", []))


def _walk(home: Path) -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = home / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if not any(part in SKIP_DIRS for part in path.parts):
                out.append(path)
    return out


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return None


def _const_binding(node: ast.stmt, name: str) -> ast.expr | None:
    """The expression bound to module-level `name` by this statement, if any.

    BOTH `X = (...)` and `X: tuple[str, ...] = (...)` are handled: the seam
    declares its rosters annotated, and a reader that walked only `ast.Assign`
    found nothing and reported "no module declares the roster" — measured on
    this gate's first run, an instrument returning a confident answer about an
    empty set."""
    targets: list[ast.expr] = []
    value: ast.expr | None = None
    if isinstance(node, ast.Assign):
        targets, value = list(node.targets), node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets, value = [node.target], node.value
    if any(isinstance(t, ast.Name) and t.id == name for t in targets):
        return value
    return None


def _str_tuple(value: ast.expr) -> tuple[str, ...]:
    """The value as a tuple of string literals; empty if it is anything else."""
    if not isinstance(value, (ast.Tuple, ast.List)):
        return ()
    got: list[str] = []
    for elt in value.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            got.append(elt.value)
    return tuple(got) if len(got) == len(value.elts) else ()


def _tuple_const(tree: ast.Module, name: str) -> tuple[str, ...]:
    """Read a module-level tuple-of-str constant by AST. No import, no exec."""
    for node in tree.body:
        value = _const_binding(node, name)
        if value is not None:
            got = _str_tuple(value)
            if got:
                return got
    return ()


def _roster(home: Path) -> Roster | None:
    for path in _walk(home):
        tree = _parse(path)
        if tree is None:
            continue
        verbs = _tuple_const(tree, ROSTER_CONST)
        if verbs:
            return Roster(
                str(path.relative_to(home)), verbs, _tuple_const(tree, EVENTS_CONST)
            )
    return None


def _methods(node: ast.ClassDef) -> set[str]:
    return {
        b.name
        for b in node.body
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _datafeed_modules(home: Path, roster: Roster) -> tuple[list[str], list[str]]:
    """(datafeed module relpaths, advisories)."""
    mods: list[str] = [roster.rel]
    advisories: list[str] = []
    tests = _testpaths(home)
    for path in _walk(home):
        rel = str(path.relative_to(home))
        if rel == roster.rel:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        hit = any(
            isinstance(n, ast.ClassDef)
            and len(_methods(n) & set(roster.verbs)) >= DATAFEED_QUORUM
            for n in ast.walk(tree)
        )
        if not hit:
            continue
        if any(rel.startswith(t) for t in tests):
            advisories.append(f"excluded (testpaths): {rel}")
        else:
            mods.append(rel)
    return mods, advisories


# --------------------------------------------------------------------------
# PUBLISHED TYPES — derived from annotations, never named
# --------------------------------------------------------------------------
def _declared_classes(
    home: Path, mods: list[str]
) -> dict[str, tuple[str, ast.ClassDef]]:
    out: dict[str, tuple[str, ast.ClassDef]] = {}
    for rel in mods:
        tree = _parse(home / rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                out.setdefault(node.name, (rel, node))
    return out


def _annotation_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.add(sub.value.strip().split("[")[0].split(".")[-1])
    return out


def _sig_annotations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.expr]:
    """Every annotation in one signature — parameters and return alike."""
    out = [a.annotation for a in node.args.args if a.annotation is not None]
    if node.returns is not None:
        out.append(node.returns)
    return out


def _published_types(
    home: Path, roster: Roster, classes: dict[str, tuple[str, ast.ClassDef]]
) -> list[str]:
    """Classes crossing the seam via a datafeed verb or event signature."""
    wanted = set(roster.verbs) | set(roster.events)
    tree = _parse(home / roster.rel)
    if tree is None:
        return []
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted:
            continue
        for ann in _sig_annotations(node):
            names |= _annotation_names(ann)
    return sorted(n for n in names if n in classes)


def _spec_datafeed_events(home: Path) -> tuple[str, ...]:
    """The §2A datafeed event identifiers, parsed out of the frozen spec."""
    path = home / SPEC_REL
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = next(
            i for i, ln in enumerate(lines) if ln.startswith(SPEC_DATAFEED_HEADING)
        )
    except StopIteration:
        return ()
    out: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith(("###", "## ")):
            break
        out.extend(re.findall(r"`(on_[a-z_]+)\(", line))
    return tuple(dict.fromkeys(out))


# --------------------------------------------------------------------------
# ARM 1 — immutable by construction
# --------------------------------------------------------------------------
def _is_immutable_type(node: ast.ClassDef) -> bool:
    if any(b.split(".")[-1] in IMMUTABLE_BASES for b in map(ast.unparse, node.bases)):
        return True
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        if ast.unparse(dec.func).split(".")[-1] != "dataclass":
            continue
        for kw in dec.keywords:
            if (
                kw.arg == "frozen"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                return True
    return False


def _arm1(
    published: list[str], classes: dict[str, tuple[str, ast.ClassDef]]
) -> list[tuple[str, str]]:
    defects: list[tuple[str, str]] = []
    for name in published:
        rel, node = classes[name]
        if not _is_immutable_type(node):
            defects.append(
                (
                    f"{rel}:{name}",
                    (
                        "published across the datafeed seam and mutable — a consumer's "
                        "copy can be rewritten by the producer, so no seal downstream "
                        "can hold"
                    ),
                )
            )
    return defects


# --------------------------------------------------------------------------
# ARMS 2 and 3 — the series stores
# --------------------------------------------------------------------------
def _guard_keys(test: ast.expr) -> frozenset[tuple[str, str]]:
    """(key, container) pairs a membership test in `test` compares."""
    out: set[tuple[str, str]] = set()
    for node in ast.walk(test):
        if not isinstance(node, ast.Compare):
            continue
        for op, cmp_ in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                out.add((ast.unparse(node.left), ast.unparse(cmp_)))
    return frozenset(out)


def _emits_event(fn: ast.AST, events: tuple[str, ...]) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            tail = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if tail in events:
                return True
    return False


def _local_published_names(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, published: set[str]
) -> set[str]:
    """Local names holding a published type.

    FOUND BY THIS GATE'S OWN CAN-FAIL RUN, not reasoned about. The first
    detector required the stored VALUE to be a literal construction —
    `self._bars[key] = Bar(...)` — and the correct builder written to prove the
    gate could say no assigns through a local first:

        candidate = Bar(...)
        if key not in self._bars:
            self._bars[key] = candidate

    so the gate reported PASS with `series stores: []`. It had examined the
    subject and seen nothing, which is `debug.md` §7.12's whole subject and
    exactly the vacuity the arm exists to prevent. One local hop is resolved
    here; deeper aliasing is §7.12 condition 7 below."""
    out: set[str] = set()
    for node in ast.walk(fn):
        made = (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func).split(".")[-1] in published
        )
        if made and isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
            continue
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and ast.unparse(node.annotation).split("[")[0].split(".")[-1] in published
        ):
            out.add(node.target.id)
    return out


def _guarded_assigns(
    nodes: list[ast.stmt], guards: frozenset[tuple[str, str]]
) -> list[tuple[ast.Assign, frozenset[tuple[str, str]]]]:
    """Every `Assign` under `nodes`, paired with the membership tests that
    dominate it. `If` is the only construct that adds a guard; everything else
    is descended into carrying whatever guards were already active."""
    out: list[tuple[ast.Assign, frozenset[tuple[str, str]]]] = []
    for node in nodes:
        if isinstance(node, ast.If):
            inner = guards | _guard_keys(node.test)
            out += _guarded_assigns(node.body, inner)
            out += _guarded_assigns(node.orelse, inner)
            continue
        if isinstance(node, ast.Assign):
            out.append((node, guards))
        kids = [k for k in ast.iter_child_nodes(node) if isinstance(k, ast.stmt)]
        out += _guarded_assigns(kids, guards)
    return out


def _store_target(
    node: ast.Assign, published: set[str], locals_: set[str]
) -> tuple[str, str, int] | None:
    """(container, key, line) if this assignment stores a PUBLISHED value into a
    subscript of a `self` attribute. Anything else is not a series store."""
    val = node.value
    made = (
        isinstance(val, ast.Call) and ast.unparse(val.func).split(".")[-1] in published
    ) or (isinstance(val, ast.Name) and val.id in locals_)
    if not made:
        return None
    for tgt in node.targets:
        if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Attribute):
            return ast.unparse(tgt.value), ast.unparse(tgt.slice), tgt.lineno
    return None


def _series_stores_in_fn(
    rel: str,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    published: set[str],
    events: tuple[str, ...],
) -> list[Store]:
    """Subscript stores whose VALUE is a published type. Narrow by design."""
    declares = _emits_event(fn, events)
    locals_ = _local_published_names(fn, published)
    out: list[Store] = []
    for node, guards in _guarded_assigns(fn.body, frozenset()):
        hit = _store_target(node, published, locals_)
        if hit is None:
            continue
        container, key, line = hit
        out.append(
            Store(
                rel=rel,
                func=fn.name,
                container=container,
                line=line,
                guarded=(key, container) in guards,
                declares=declares,
            )
        )
    return out


def _series_stores(
    home: Path, mods: list[str], published: set[str], events: tuple[str, ...]
) -> list[Store]:
    out: list[Store] = []
    for rel in mods:
        tree = _parse(home / rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out += _series_stores_in_fn(rel, node, published, events)
    return out


def _arm23(stores: list[Store]) -> list[tuple[str, str]]:
    defects: list[tuple[str, str]] = []
    for st in stores:
        site = f"{st.rel}:{st.func}:{st.line}"
        if not st.guarded:
            defects.append(
                (
                    site,
                    (
                        f"unguarded store into {st.container} — a re-poll returning a "
                        "revised value overwrites a published entry silently"
                    ),
                )
            )
        elif not st.declares:
            defects.append(
                (
                    site,
                    (
                        f"store into {st.container} is guarded but {st.func} emits no "
                        "datafeed event — the revision is detected and swallowed, so the "
                        "venue's changed story is unrecoverable"
                    ),
                )
            )
    return defects


# --------------------------------------------------------------------------
# ARM 4 — behavioural, over the real published types
# --------------------------------------------------------------------------
class Plan(NamedTuple):
    """Two constructor argument sets differing in exactly one numeric field."""

    base: dict[str, object]
    other: dict[str, object]
    vary: str


def _field_annotations(node: ast.ClassDef) -> dict[str, str]:
    return {
        stmt.target.id: ast.unparse(stmt.annotation)
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }


def _synth_value(ann: str, mod: object) -> tuple[object, bool] | None:
    """(value, is_numeric) for one annotation, resolved against its module.

    Resolving against the module rather than a table of primitive names is what
    lets an enum-typed or alias-typed field be filled with a REAL member instead
    of making the whole type unsynthesisable — `FeedLag.granted_mode` is the
    case that forced it."""
    tail = ann.split("[")[0].split(".")[-1].strip("\"'")
    resolved = getattr(mod, tail, None)
    if tail == "int":
        return 1, True
    if tail == "float":
        return 1.0, True
    if tail == "bool":
        return False, False
    if isinstance(resolved, type) and issubclass(resolved, enum.Enum):
        members = list(resolved)
        return (members[0], False) if members else None
    if resolved is str or tail == "str":
        return "x", False
    return None


def _synth(node: ast.ClassDef, mod: object) -> Plan | None:
    """Two field maps differing in exactly one NUMERIC field.

    Numeric so "differs by one field" is unambiguous and the difference is one
    the type's own equality must be able to see."""
    base: dict[str, object] = {}
    numeric: list[str] = []
    for name, ann in _field_annotations(node).items():
        got = _synth_value(ann, mod)
        if got is None:
            return None
        value, is_numeric = got
        base[name] = value
        if is_numeric:
            numeric.append(name)
    if not numeric:
        return None
    vary = numeric[0]
    bumped = base[vary]
    if not isinstance(bumped, (int, float)):
        return None
    return Plan(base=base, other={**base, vary: bumped + 1}, vary=vary)


def _drive_seal(cls: type, plan: Plan, site: str) -> tuple[list, str]:
    """Drive one published type. (defects, note). Executes real objects.

    Non-vacuity FIRST (`nix_check_contract.md` §5.1 step 2): the two synthesised
    values must genuinely differ before anything is asserted about immutability.
    A re-poll returning identical data proves nothing, and neither does this."""
    first = cls(**plan.base)
    other = cls(**plan.other)
    same = cls(**plan.base)
    if first == other:
        return [
            (
                site,
                (
                    f"two values differing in {plan.vary} compare EQUAL — a revision "
                    "is not representable, so no seal can detect one"
                ),
            )
        ], ""
    defects: list[tuple[str, str]] = []
    if first != same:
        defects.append(
            (
                site,
                (
                    "two identical values compare UNEQUAL — equality is identity, so "
                    "'unchanged' cannot be asserted either"
                ),
            )
        )
    try:
        setattr(first, plan.vary, plan.base[plan.vary])
    except AttributeError:
        # dataclasses.FrozenInstanceError subclasses AttributeError, and a
        # NamedTuple raises AttributeError too — so this is the precise
        # exception for "the runtime refused the write", not a blind catch.
        return defects, (
            f"arm4 {site}: revision representable (differs in {plan.vary}), "
            f"field write refused, value equality holds"
        )
    defects.append(
        (
            f"{site}.{plan.vary}",
            (
                "a published value accepted a field write — the seal is a "
                "convention, not a runtime guarantee"
            ),
        )
    )
    return defects, ""


def _arm4(
    home: Path, published: list[str], classes: dict[str, tuple[str, ast.ClassDef]]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Construct each published type and drive the seal. Executes real code."""
    import sys  # pylint: disable=import-outside-toplevel

    for extra in (str(home / "scripts"), str(home / "scripts" / "broker")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    defects: list[tuple[str, str]] = []
    notes: list[str] = []
    for name in published:
        rel, node = classes[name]
        got_defects, note = _arm4_one(rel, name, node)
        defects += got_defects
        notes.append(note)
    return defects, notes


def _arm4_one(
    rel: str, name: str, node: ast.ClassDef
) -> tuple[list[tuple[str, str]], str]:
    """One published type, imported and driven. Anything unmeasurable is a NOTE,
    never a violation — a type this gate cannot construct is not a defect in the
    type, and calling it one would be the gate reddening code it never read."""
    import importlib  # pylint: disable=import-outside-toplevel

    site = f"{rel}:{name}"
    try:
        mod = importlib.import_module(Path(rel).stem)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [], f"arm4 {site}: not importable — {type(exc).__name__}"
    plan = _synth(node, mod)
    if plan is None:
        return [], f"arm4 {site}: not synthesisable from annotations"
    try:
        return _drive_seal(getattr(mod, name), plan, site)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [], f"arm4 {site}: not constructible — {type(exc).__name__}"


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------
def _cannot(detail: str, evidence: str = "") -> CheckResult:
    return CheckResult(
        name=NAME, status=Status.CANNOT_MEASURE, detail=detail, evidence=evidence
    )


def _surface(home: Path, roster: Roster) -> Surface:
    """Published types, series stores, Nix-added events, and the advisories."""
    mods, advisories = _datafeed_modules(home, roster)
    classes = _declared_classes(home, mods)
    published = _published_types(home, roster, classes)
    spec_events = _spec_datafeed_events(home)
    added = [e for e in roster.events if e not in spec_events]
    stores = _series_stores(home, mods, set(published), roster.events)
    advisories.append(f"datafeed modules: {mods}")
    advisories.append(
        f"§2A datafeed events parsed from the frozen spec: {list(spec_events)}"
    )
    return Surface(
        published=published, stores=stores, added=added, advisories=advisories
    )


def _evidence(roster: Roster, surface: Surface, a4_notes: list[str]) -> str:
    """Everything the run actually measured, printed whether it passed or not."""
    lines = [
        f"scope: roster {roster.rel} verbs={roster.verbs} events={roster.events}",
        f"published types: {surface.published}",
        f"nix-added datafeed events: {surface.added}",
        "series stores: " + str([f"{s.rel}:{s.func}:{s.line}" for s in surface.stores]),
        *a4_notes,
        f"advisories: {surface.advisories}",
    ]
    return "; ".join(lines)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Verdict. PASS requires a SERIES surface — arms 1 and 4 alone cannot carry
    one, because "the one published type is frozen" is not D1.14."""
    home = ctx.nix_home
    roster = _roster(home)
    if roster is None:
        return _cannot(f"no module under {SCAN_ROOTS} declares {ROSTER_CONST}")
    if not roster.events:
        return _cannot(f"{roster.rel} declares no {EVENTS_CONST} (§7.12 cond. 5)")

    surface = _surface(home, roster)
    classes = _declared_classes(home, _datafeed_modules(home, roster)[0])
    a4_defects, a4_notes = _arm4(home, surface.published, classes)
    defects = _arm1(surface.published, classes) + _arm23(surface.stores) + a4_defects
    evidence = _evidence(roster, surface, a4_notes)

    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(s for s, _ in defects),
            evidence=evidence,
            detail="; ".join(f"{s}: {w}" for s, w in defects),
        )
    if not surface.stores and not surface.added:
        return _cannot(
            "no series publication surface on the broker-datafeed path — no "
            "datafeed event beyond §2A's pair and no store of a published type. "
            "Nothing is sealed because nothing is published, so a PASS would "
            "measure nothing (§7.12 cond. 1)",
            evidence=evidence,
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    import sys as _sys

    from nixverify.contract import exit_code_for, validate_result

    if len(_sys.argv) > 1 and _sys.argv[1] == "--print-scope-count":
        _HOME = (
            Path(_sys.argv[2])
            if len(_sys.argv) > 2
            else Path(__file__).resolve().parent.parent
        )
        _R = _roster(_HOME)
        print(len(_datafeed_modules(_HOME, _R)[0]) - 1 if _R else 0)
        _sys.exit(0)

    HOME = (
        Path(_sys.argv[1])
        if len(_sys.argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    _sys.exit(exit_code_for(OUTCOME.status))
