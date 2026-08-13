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
import itertools
import re
import tomllib
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801: the §4.2 `__main__` block and the crash handler are mandated to be the
# same text in every check; the only deduplication is the helper §4.2 forbids.
# pylint: disable=duplicate-code
# C0302 (too-many-lines) disabled in ARC 021 PHASE 4, when the B.4 repair below took
# this module from 967 lines to 1039.
#
# THIS RATIONALE IS DELIBERATELY NOT THE ONE IN `check_datafeed_granted_mode.py`, and the
# difference is measured, not assumed. That module's disable says trimming prose CANNOT
# fix the count because it exceeds 1000 with every module-docstring line removed. Here
# that is FALSE — derive it, do not read it:
#   .venv/bin/python -c "import ast,pathlib;s=pathlib.Path(
#     'checks/check_datafeed_bar_seal.py').read_text();d=ast.get_docstring(
#     ast.parse(s),clean=False);print(len(s.splitlines()),
#     len(d.splitlines())+2)"
# which reports 1039 total against a 219-line docstring, i.e. 820 without it. Deleting
# prose WOULD mechanically satisfy pylint. Copying the sibling's wording would therefore
# have asserted something untrue about this file — the same defect this arc removed from
# `broker_datafeed_ibkr.py`'s dead `import-outside-toplevel` suppression, committed in
# the act of citing doctrine.
#
# So the argument is the narrower and honest one: the prose that would have to go is the
# §7.12 seven-condition answer, which `debug.md` §7.12 requires IN WRITING BESIDE THE
# GATE, and the B.4 repair record, which is the evidence that arm 2 once reddened a
# correct seal and why it no longer does. Both are load-bearing for a reader deciding
# whether to trust this gate. `nix_check_contract.md` §5.5 independently forbids the
# other escape — splitting into a second instrument over the same property.
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- ARC 025 orchestration declarations (read statically, never imported) ---
#: Nothing must run before this gate. It reads source and imports the published
#: types under the SYSTEM interpreter — it never touches `.venv`, so unlike its
#: sibling it does not depend on `check_venv`. Verified rather than assumed:
#: this module contains no `.venv` path and no venv subprocess.
DEPENDS_ON: tuple[str, ...] = ()
#: ARM 4 IS WHY THIS IS NOT EMPTY, and the claim is about the ENGINE's process,
#: not about a file. `engine._run_block` runs a parallel block's members in a
#: `ThreadPoolExecutor` — one interpreter, shared globals — and `_arm4` appends
#: to `sys.path` and `importlib.import_module`s every datafeed module into that
#: interpreter, where the modules stay resident for every check that runs
#: afterwards. Two checks importing subject modules concurrently race on
#: `sys.modules` and on each other's `sys.path` view, and `loader.py`'s own
#: docstring records that its `sys.path` entry is never removed for exactly this
#: reason. A gate that says "I read files only" while mutating the interpreter
#: every other gate is running in would be a false declaration, which is the
#: D2.27 residual — disjointness is proven over declarations — one level down.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No subprocess, no socket, no sleep, no timeout constant anywhere in this
#: module: the runtime is dominated by an AST walk over the scan roots, i.e. by
#: WORK. There is therefore no bound to derive `EXPECTED_S` from, and inventing
#: one from an observed run is what §4.4 forbids — so it is not declared.
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is broker-datafeed SOURCE on the §2A capture path. Every "
    "defect this gate reports is closed by a code change carrying a design "
    "decision the engine cannot make — which guard polarity is correct, which "
    "datafeed event a revision should be declared as, whether a published type "
    "should be frozen or redesigned. An engine that wrote the seal guard would "
    "then be grading code it authored, which is a vacuous pass by construction "
    "(§4.3), and it would be writing on the broker path §4.3's non-correctable "
    "class names"
)
#: The artifacts this gate DRIVES, not merely reads. Held as a literal because
#: `declarations.py` reads it by AST and cannot evaluate a computed expression —
#: which makes it a restatement of a scope this module goes to some length never
#: to type. That restatement is closed MECHANICALLY rather than by discipline:
#: `_subjects_defect` below compares this tuple against the scope actually
#: derived on every run and FAILS on divergence, so a datafeed module written
#: tomorrow reddens this gate until it is declared. Doctrine B.7's pattern —
#: two statements of one fact, with a machine reading both.
SUBJECTS: tuple[str, ...] = (
    "scripts/broker/broker_seam.py",
    "scripts/broker/broker_datafeed_ibkr.py",
    "scripts/broker/ibkr_mapping.py",
)

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
            # Skip SKIP_DIRS and macOS AppleDouble sidecars (`._name.py`): the
            # latter are a sibling's resource fork, raw bytes, not Python, and the
            # Samba-share canonical tree drops them routinely — `ast.parse`-ing one
            # drives the gate to CANNOT_MEASURE on a non-code file (ARC 029,
            # CHECK-DEBT D3.110). Excluded by NAME class, not tracking state.
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name.startswith("._"):
                continue
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
# ARC 021 PHASE 4 REPAIR — doctrine B.4, measured not theorised.
#
# THE SEAL HAS TWO IDIOMATIC SPELLINGS IN PYTHON AND THIS GATE ONLY KNEW ONE.
#
#   membership form          lookup-then-sentinel form
#   ---------------          -------------------------
#   if key not in store:     found = store.get(key)
#       store[key] = value   if found is None:
#                                store[key] = value
#
# They prove the SAME property. The second is the more common of the two in real code
# because it hashes the key once instead of twice, and it is what the first real
# broker-datafeed adapter used. Arm 2 recognised only `In`/`NotIn`, so it reported
# `unguarded store into self._sealed` about a store that is guarded — reddening the
# correct implementation of its own subject on the first adapter it ever bound to.
# `VERIFY-AND-CHECKS.md` doctrine B.4: that gate is BROKEN, not strict.
#
# The repair teaches the gate the second spelling rather than asking the code to adopt
# the first. Requiring one spelling would have been a style rule wearing a correctness
# gate's exit code, and the property — a published entry is never overwritten — is
# indifferent to which is used.
#
# WHY THIS IS NOT A WEAKENING: a lookup binds `name -> (key, container)` ONLY through a
# literal `container.get(key)` call, and the binding is consumed ONLY by an `is None` /
# `is not None` test against that same name. An unguarded store still has no dominating
# test of either spelling and still fails — PLANT P4 below proves it after this repair,
# not before it.
#
# THE RESIDUAL AS ARC 021 LEFT IT (CHECK-DEBT D2.21): polarity was not checked, exactly
# as it was not checked for the membership form (§7.12 condition 5) — `if found is not
# None:` guarding a store read the same as `if found is None:`.
#
# ARC 022 (C4) CLOSES IT. `_absent_proofs` below replaces the polarity-blind
# `_guard_keys`: a test no longer yields one undifferentiated set of guarded
# `(key, container)` pairs applied to BOTH branches. It yields TWO sets — what the test
# proves ABSENT when it is true, and what it proves absent when it is false — and the
# `If` handler applies the first to `body` and the second to `orelse`.
#
# WHY THIS CANNOT BE A WEAKENING, structurally and not by assertion: every branch now
# receives a SUBSET of what it received before. `body` used to receive
# `In ∪ NotIn ∪ Is ∪ IsNot` and now receives `NotIn ∪ Is`; `orelse` used to receive the
# same union and now receives `In ∪ IsNot`. A store that failed before therefore cannot
# pass now. MEASURED, seven guard spellings in a throwaway copy of the tree, plus the
# real adapter as the control:
#
#   spelling                                                   before   after
#   ---------------------------------------------------------  ------   -----
#   `if key not in store: store[k]=v`            correct        PASS     PASS
#   `found=store.get(k); if found is None: store[k]=v` correct   PASS     PASS
#   `if found is not None: revise() else: store[k]=v`  correct   PASS     PASS
#   `store[k]=v`                                 unguarded      FAIL     FAIL
#   guarded, emits no datafeed event (arm 3)                    FAIL     FAIL
#   `if key in store: store[k]=v`                INVERTED       PASS     FAIL
#   `found=store.get(k); if found is not None: store[k]=v` INV   PASS     FAIL
#   `if key not in store or self._force: store[k]=v`  ESCAPE     PASS     FAIL
#
# The last three are the repair. The two INVERTED rows are D2.21 verbatim — a guard that
# overwrites every sealed entry and only ever stores on the re-poll. The ESCAPE row was
# NOT in D2.21 and was found by building the table rather than reasoned about: a
# disjunction weakens the proof to nothing, and the old walk-every-Compare reader counted
# it as a guard because it never looked at how the tests were combined.
#
# B.4's OTHER EDGE, and it is the row that matters most here: `check_datafeed_bar_seal`
# has already reddened the correct implementation of its own subject once (the
# lookup-then-sentinel repair above). The real adapter was re-run as a CONTROL after this
# change and its output is BYTE-IDENTICAL to the output before it, exit 0 either way. The
# gate's arms 1 and 4 are untouched — the blast radius is `_guard_keys` and the one `If`
# branch in `_guarded_assigns`, both read only by arms 2 and 3.
#
# WHAT THIS DOES NOT DO, AND IT IS NOT WHAT D2.21 ASKED: a PASS from arm 2 still is not a
# binding of this gate to the real adapter. D3.9/D3.10 stay open and this gate stays
# UNBOUND — see the ARC 022 rule of record at the head of `docs/CHECK-DEBT.md`.
def _lookup_binding(node: ast.stmt) -> tuple[str, tuple[str, str]] | None:
    """`name = <container>.get(<key>)` -> (name, (key, container)). Else None."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    tgt = node.targets[0]
    val = node.value
    if not isinstance(tgt, ast.Name) or not isinstance(val, ast.Call):
        return None
    fn = val.func
    if not isinstance(fn, ast.Attribute) or fn.attr != "get" or not val.args:
        return None
    return tgt.id, (ast.unparse(val.args[0]), ast.unparse(fn.value))


def _compare_absence(
    test: ast.expr, binds: dict[str, tuple[str, str]]
) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    """One comparison's absence proofs, per polarity. Split out of
    `_absent_proofs` so neither function exceeds the return-count and
    cognitive-complexity ceilings the hook suite enforces; the split is
    structural and changes no verdict."""
    empty: frozenset[tuple[str, str]] = frozenset()
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return empty, empty
    op, cmp_ = test.ops[0], test.comparators[0]
    if isinstance(op, (ast.In, ast.NotIn)):
        member = frozenset({(ast.unparse(test.left), ast.unparse(cmp_))})
        return (member, empty) if isinstance(op, ast.NotIn) else (empty, member)
    left = test.left
    sentinel = (
        isinstance(op, (ast.Is, ast.IsNot))
        and isinstance(left, ast.Name)
        and left.id in binds
        and isinstance(cmp_, ast.Constant)
        and cmp_.value is None
    )
    # The second clause is redundant at run time and is what carries the `ast.Name`
    # narrowing across the boolean into the line below; mypy does not propagate it
    # out of the conjunction above.
    if not sentinel or not isinstance(left, ast.Name):
        return empty, empty
    pair = frozenset({binds[left.id]})
    return (pair, empty) if isinstance(op, ast.Is) else (empty, pair)


def _absent_proofs(
    test: ast.expr, lookups: dict[str, tuple[str, str]] | None = None
) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    """POLARITY-AWARE (ARC 022, D2.21). What `test` proves ABSENT, per branch.

    Returns `(absent_if_true, absent_if_false)` as `(key, container)` pairs. A
    seal is only proven when the store sits on the branch where the key is known
    NOT to be there, so the two branches must be answered separately — `if key in
    store:` proves absence on its ELSE and `if key not in store:` on its THEN, and
    the pre-ARC-022 reader gave both branches the union of the two.

    `lookups` carries the `name -> (key, container)` bindings a preceding
    `container.get(key)` created, so an `is None` test on that name proves the
    same guard a membership test would.

    Boolean combination is handled explicitly rather than by walking every
    `Compare` in the tree: under `and`, truth implies every operand's truth, so
    the true-sets union and nothing is known on the false side; under `or` the
    reverse. That is what makes `if key not in store or force:` unguarded on the
    branch that stores, which the old reader could not express."""
    empty: frozenset[tuple[str, str]] = frozenset()
    binds = lookups or {}
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        true_abs, false_abs = _absent_proofs(test.operand, binds)
        return false_abs, true_abs
    if isinstance(test, ast.BoolOp):
        parts = [_absent_proofs(v, binds) for v in test.values]
        if isinstance(test.op, ast.And):
            return frozenset().union(*(p[0] for p in parts)), empty
        return empty, frozenset().union(*(p[1] for p in parts))
    return _compare_absence(test, binds)


def _emits_event(fn: ast.AST, events: tuple[str, ...]) -> bool:
    """True if a datafeed EVENT emission appears in `fn`'s OWN body.

    ONE HOP THROUGH A SAME-CLASS HELPER WAS BUILT, MEASURED, AND REFUSED IN
    ARC 023 STAGE 2 — see CHECK-DEBT D3.18, which carries both measurements.
    Stage 1 of this arc measured the FALSE POSITIVE this reader has: extracting
    the publish out of `_ingest_history` into a helper made arm 3 report
    *"store is guarded but `_ingest_history` emits no datafeed event"* against a
    correct implementation, which doctrine B.4 calls BROKEN and not strict. The
    obvious repair is to follow one call through `self.<method>`. It was
    implemented and then measured against the plant this arm exists to fail —
    deleting the `on_bar` emission from `_ingest_history` — and the plant
    STOPPED FAILING: `_ingest_history` also calls `self._maybe_revise(...)`,
    which emits `on_bar_revision`, so the hop finds an event and the arm goes
    green over a swallowed publication. The plant is caught at zero hops and not
    at one, verified both ways in a scratch copy of the tree.

    So the hop is a real reduction in strictness on a real input, which
    `VERIFY-AND-CHECKS.md` Part C rule 2 and this arc's own prohibition forbid,
    and BOTH halves are symptoms of the same thing: "does this FUNCTION reach an
    event" cannot distinguish *the revision is declared* from *some event is
    emitted somewhere in here*, and widening the window makes that worse rather
    than better. The false positive is left standing and named rather than
    traded for a false negative."""
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
    nodes: list[ast.stmt],
    guards: frozenset[tuple[str, str]],
    lookups: dict[str, tuple[str, str]] | None = None,
) -> list[tuple[ast.Assign, frozenset[tuple[str, str]]]]:
    """Every `Assign` under `nodes`, paired with the guards that dominate it.
    `If` is the only construct that adds a guard; everything else is descended
    into carrying whatever guards were already active.

    `lookups` accumulates SEQUENTIALLY as the statement list is walked, because
    the lookup-then-sentinel spelling is two statements: the `container.get(key)`
    binding must already have been seen when the `is None` test is reached."""
    out: list[tuple[ast.Assign, frozenset[tuple[str, str]]]] = []
    binds = dict(lookups or {})
    for node in nodes:
        if isinstance(node, ast.If):
            true_abs, false_abs = _absent_proofs(node.test, binds)
            out += _guarded_assigns(node.body, guards | true_abs, binds)
            out += _guarded_assigns(node.orelse, guards | false_abs, binds)
            continue
        if isinstance(node, ast.Assign):
            out.append((node, guards))
        bound = _lookup_binding(node)
        if bound is not None:
            binds[bound[0]] = bound[1]
        kids = [k for k in ast.iter_child_nodes(node) if isinstance(k, ast.stmt)]
        out += _guarded_assigns(kids, guards, binds)
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


def _union_members(ann: str) -> list[str]:
    """A union annotation split into its members, outermost `|` only.

    D3.15, ARC 023 stage 2. The reader this replaces was
    `ann.split("[")[0].split(".")[-1]`, which takes the head of the string and
    therefore reads `float | None` as the single name `float | None`. Nothing
    resolves under that name, one unresolvable field makes the whole type
    unsynthesisable, and `Bar.volume: float | None` was enough to skip `Bar`
    entirely. All five published types reported `not synthesisable` and the arm
    — named by BOTH D2.20 and D2.21 as their compensating control — executed
    nothing for two arcs.

    Depth-tracked because `dict[str, int] | None` must split into two members
    and `dict[str, int]` must not split into three. `Optional[X]` is unwrapped
    to `X` for the same reason a bare `X | None` is: both spell "X or absent",
    and the synthesiser's job is to produce ONE inhabitant of the annotation,
    not to enumerate it."""
    head = ann.split("[")[0].strip().split(".")[-1]
    if head == "Optional" and "[" in ann:
        inner = ann[ann.index("[") + 1 : ann.rindex("]")]
        return _union_members(inner) + ["None"]
    parts: list[str] = []
    depth = 0
    cur = ""
    for ch in ann:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip().strip("\"'") for p in parts if p.strip()]


NONE_NAMES: frozenset[str] = frozenset({"None", "NoneType"})

MAX_SYNTH_CANDIDATES = 1024
"""Hard ceiling on the assignments tried per published type (D3.15).

A ceiling and not a hope: the search below is a cartesian product over the
enum-typed fields, so a type with six five-member enums is 15 625 constructions
and this gate has a boot-time budget. Exhausting the ceiling is reported as
`not constructible`, which is a NOTE — the arm says it could not build the type,
it never says the type is wrong."""


def _synth_one(ann: str, mod: object) -> tuple[list[object], bool] | None:
    """(candidate values, is_numeric) for ONE non-union annotation.

    A LIST rather than a single value since D3.15: an enum field offers every
    member, because a type with cross-field invariants is constructible for some
    assignments and not others and picking `members[0]` is picking one draw from
    that space and calling the type unbuildable when it loses. `FeedLag` is the
    measured case — `provenance=LagProvenance.UNOBSERVED` beside a non-`None`
    `observed_lag_s` is refused by its own `__post_init__`, correctly."""
    tail = ann.split("[")[0].split(".")[-1].strip("\"'")
    resolved = getattr(mod, tail, None)
    if tail == "int":
        return [1], True
    if tail == "float":
        return [1.0], True
    if tail == "bool":
        return [False], False
    if isinstance(resolved, type) and issubclass(resolved, enum.Enum):
        members: list[object] = list(resolved)
        return (members, False) if members else None
    if resolved is str or tail == "str":
        return ["x"], False
    return None


def _synth_value(ann: str, mod: object) -> tuple[list[object], bool] | None:
    """(value, is_numeric) for one annotation, resolved against its module.

    Resolving against the module rather than a table of primitive names is what
    lets an enum-typed or alias-typed field be filled with a REAL member instead
    of making the whole type unsynthesisable — `FeedLag.granted_mode` is the
    case that forced it.

    A UNION resolves to its FIRST SYNTHESISABLE NON-`None` MEMBER (D3.15), and
    falls back to `None` only when no other member resolves. The ORDER is
    load-bearing in both directions and neither half is arbitrary:

      * Preferring the non-`None` member is what keeps the field NUMERIC.
        `Bar.volume: float | None` filled with `None` would leave `Bar`
        constructible but would remove a field the plan can vary; take that
        preference away from every optional numeric field and a type can end up
        with no numeric field at all, at which point `_synth` returns None
        again and the arm is back to measuring nothing.
      * Falling back to `None` is what keeps the type CONSTRUCTIBLE when the
        non-`None` member is a type this synthesiser cannot build —
        `FeedLag.window: LagWindow | None` is exactly that case, and refusing
        the whole of `FeedLag` over one optional composite field is D3.15's
        defect in a second costume. `None` IS an inhabitant of the annotation;
        substituting it is not a fabricated value.

    What is NOT done here is synthesising the composite recursively. That would
    make the arm's reach depend on how deep the synthesiser can dig, and a
    partial dig produces a half-built object the type's own `__post_init__` may
    reject — reported as `not constructible` against correct code, which is
    doctrine B.4's forbidden direction."""
    members = _union_members(ann)
    optional = any(m in NONE_NAMES for m in members)
    for member in members:
        if member in NONE_NAMES:
            continue
        got = _synth_one(member, mod)
        if got is not None:
            values, numeric = got
            # `None` LAST, so the non-`None` fill is preferred and the field
            # stays numeric wherever it can be; it is still offered, because
            # `observed_lag_s=None` is what makes several `FeedLag` assignments
            # legal at all.
            return (list(values) + [None] if optional else list(values)), numeric
    if optional:
        return [None], False
    return None


def _constructs(cls: type, base: dict, other: dict) -> bool:
    """True if the type accepts BOTH halves of a candidate plan.

    The exception is swallowed BY DESIGN and that is not a silent failure: a
    refusal here is the type's own `__post_init__` declining an assignment the
    synthesiser guessed, which is information about the GUESS and not about the
    type. If every candidate is refused, `_synth` reports it as a note naming
    the count — so the aggregate is loud even though each individual refusal is
    not."""
    try:
        cls(**base)
        cls(**other)
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001
        return False
    return True


def _numeric_field(base: dict[str, object]) -> str | None:
    """The first field holding a real number. `bool` is excluded explicitly:
    `isinstance(True, int)` is True, and varying a bool by +1 leaves the
    annotation's domain."""
    for name, value in base.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return name
    return None


def _synth(node: ast.ClassDef, mod: object) -> tuple[Plan | None, str]:
    """(plan, reason-if-none). Two field maps differing in exactly one NUMERIC
    field, and BOTH PROVEN TO CONSTRUCT before the plan is returned.

    Numeric so "differs by one field" is unambiguous and the difference is one
    the type's own equality must be able to see.

    D3.15, ARC 023 stage 2 — WHY THIS SEARCHES RATHER THAN PICKS. The reader
    this replaces built exactly one assignment, from the first candidate for
    every field, and handed it to the caller to construct. For a type whose
    fields are independent that is the same thing as a search; for a type with
    CROSS-FIELD INVARIANTS it is one draw, and `FeedLag` refuses that draw for a
    correct reason of its own (`observed_lag_s` set beside a provenance that is
    not `OBSERVED` is an observation that does not declare itself observed).
    Reporting `not constructible` there says something false about a type this
    gate is supposed to be driving.

    THE SEARCH IS BOUNDED AND ITS EXHAUSTION IS REPORTED, never silent: a type
    whose product exceeds `MAX_SYNTH_CANDIDATES` is a NOTE naming the count, and
    a note has never been a defect in this arm. What the search may NOT do is
    weaken an assertion to find a fit — every returned plan still has to survive
    all three of `_drive_seal`'s assertions afterwards, unchanged."""
    fields = _field_annotations(node)
    if not fields:
        return None, "not synthesisable from annotations"
    names: list[str] = []
    choices: list[list[object]] = []
    for name, ann in fields.items():
        got = _synth_value(ann, mod)
        if got is None:
            return None, "not synthesisable from annotations"
        names.append(name)
        choices.append(got[0])
    cls = getattr(mod, node.name, None)
    if not isinstance(cls, type):
        return None, "not constructible — the class is not importable by name"
    tried = 0
    for combo in itertools.product(*choices):
        tried += 1
        if tried > MAX_SYNTH_CANDIDATES:
            return None, (
                f"not constructible — {MAX_SYNTH_CANDIDATES} candidate assignments "
                "exhausted without one the type accepts"
            )
        base = dict(zip(names, combo, strict=True))
        vary = _numeric_field(base)
        if vary is None:
            continue
        other = {**base, vary: base[vary] + 1}  # type: ignore[operator]
        if _constructs(cls, base, other):
            return Plan(base=base, other=other, vary=vary), ""
    return None, (
        f"not constructible — no assignment of {tried} candidate(s) the type accepts"
    )


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
    # ONE measurement, TWO consumers: the defect below and the note returned on
    # the write-refused path are both read off this name. ARC 027 (B3), D3.21 —
    # the note used to assert "value equality holds" unconditionally, so under
    # the `eq=False` plant the gate shipped a CORRECT verdict beside FALSE
    # evidence and an operator reading the evidence line concluded the opposite
    # of the verdict. A narration authored independently of the measurement it
    # describes is a defect of its own class, distinct from an unread number.
    equality_holds = first == same
    if not equality_holds:
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
            f"field write refused, value equality "
            f"{'holds' if equality_holds else 'DOES NOT HOLD'}"
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
    plan, reason = _synth(node, mod)
    if plan is None:
        return [], f"arm4 {site}: {reason}"
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


def _subjects_defect(mods: list[str]) -> list[tuple[str, str]]:
    """`SUBJECTS` must equal the scope this run actually derived.

    `SUBJECTS` feeds `check_artifact_gate_coverage`, whose own docstring bounds
    what it can prove: that a check NAMES an artifact, which is strictly weaker
    than that a check DRIVES it. Here the two are made the same statement. The
    declaration is a literal because the AST reader cannot evaluate anything
    else (`nix_check_contract.md` §4.4), and a literal file list inside THIS
    gate is precisely the typed
    scope `debug.md` §8 failure mode #14 is about — so it is not left to be
    right, it is compared against the derived scope on every run.

    Both directions are defects and they are different defects. A derived module
    missing from `SUBJECTS` is coverage this gate is credited with and does not
    have; a `SUBJECTS` entry the derivation no longer returns is coverage
    claimed over a file that has left the gate's scope.
    """
    declared, derived = set(SUBJECTS), set(mods)
    site = "checks/check_datafeed_bar_seal.py:SUBJECTS"
    out: list[tuple[str, str]] = []
    undeclared = sorted(derived - declared)
    if undeclared:
        out.append(
            (
                site,
                (
                    f"the derived datafeed scope contains {undeclared}, which "
                    f"SUBJECTS does not declare — check_artifact_gate_coverage "
                    f"would report these as uncovered while this gate drives them"
                ),
            )
        )
    stale = sorted(declared - derived)
    if stale:
        out.append(
            (
                site,
                (
                    f"SUBJECTS declares {stale}, which this run's derivation "
                    f"did not return — coverage is claimed over a file no "
                    f"longer in this gate's scope"
                ),
            )
        )
    return out


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
    mods = _datafeed_modules(home, roster)[0]
    classes = _declared_classes(home, mods)
    a4_defects, a4_notes = _arm4(home, surface.published, classes)
    defects = (
        _arm1(surface.published, classes)
        + _arm23(surface.stores)
        + a4_defects
        + _subjects_defect(mods)
    )
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


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    import sys as _sys

    # `--print-scope-count` is NOT an actuation verb and predates the flag
    # surface: it is the source `derived_claims.json:datafeed_scope_files`
    # reads, and it is what keeps this gate's scope derivation and its
    # sibling's from drifting apart. It is intercepted before
    # `parse_actuation` because an argparse surface that did not know it
    # would reject it, and silently losing this entry point would blind the
    # one cross-check that pairs the two datafeed gates.
    if len(_sys.argv) > 1 and _sys.argv[1] == "--print-scope-count":
        _HOME = (
            Path(_sys.argv[2])
            if len(_sys.argv) > 2
            else Path(__file__).resolve().parent.parent
        )
        _R = _roster(_HOME)
        print(len(_datafeed_modules(_HOME, _R)[0]) - 1 if _R else 0)
        _sys.exit(0)

    from nixverify.actuation import standalone_main

    _sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
