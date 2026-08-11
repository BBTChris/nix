#!/usr/bin/env python3
"""The market-data mode reported at the seam is the GRANTED one, and "nothing
was granted" is distinguishable from "real-time was granted".

CHECK-DEBT D1.13. ONE gate, ONE property (`nix_check_contract.md` §5.5,
doctrine C.9): *the broker-datafeed seam reports the mode the venue actually
granted, and it can express the difference between an ungranted field and a
grant of 1.* The boundary against this gate's sibling is stated in both
docstrings so it survives the next author:

  * THIS gate owns the OBSERVATION of the feed's mode — what the venue said,
    how it is read, and whether "unread" can be told from "real-time".
  * `check_datafeed_bar_seal` owns the LIFECYCLE of published series data —
    once a bar is out, it never changes silently. It does not read the mode.

They share a SCOPE DERIVATION and not one line of code: `nix_check_contract.md`
§4.2 requires every `checks/check_*.py` be independently runnable, which
forbids the shared helper that would keep the two derivations identical. That
residual is not left to drift — the derived-claims registry carries
`datafeed_scope_files`, whose two sources are the two gates' own
`--print-scope-count`, so a divergence between them is RED rather than silent.

==============================================================================
THE DEFECT, AND IT IS ALREADY ON THE RECORD AS HAVING NEARLY LANDED
==============================================================================
Two independent traps, and either alone produces a confident wrong answer:

  1. IBKR SILENTLY DOWNGRADES. ARC 013 requested `marketDataType` 4
     (delayed-frozen) and was granted 3 (delayed) with **no error raised**.
     Requesting 1 (real-time) produced **no grant callback at all** and error
     354. Banked, with the tick counts and the errors, in
     `sessions/SESSION.md` under "ARC 013 — delayed market data verified".

  2. `ib_async`'s `Ticker.marketDataType` DEFAULTS TO 1. An unset field is
     therefore byte-identical to a genuine real-time grant. This is MEASURED,
     not inherited: the gate re-reads the default out of the installed,
     pinned distribution on every run (arm A2 below) rather than restating
     the integer here.

ARC 013 hit both at once and caught it by hand: *"The first run showed
`granted=1` for real-time — but `ib_async`'s `Ticker.marketDataType` defaults
to 1, so that was an unset field, not a grant, for a subscription that returned
zero ticks and error 354. Verified by sentinelling the field to 0 after
subscribing so only a real callback could move it: mode 1 never moved, modes 3
and 4 both moved to 3."* That paragraph is the empirical basis for every
assertion below; the three-way distinction this gate enforces is not a
hypothesis, it is a reproduction of a measurement.

`MarketDataMode` in `scripts/broker/broker_seam.py` already carries
`UNKNOWN = 0` beside `REALTIME = 1`, so the seam's vocabulary CAN express the
distinction. Nothing forced anyone to use it. That is what this gate forces.

==============================================================================
WHY THE OBVIOUS GATE IS THE DEFECT
==============================================================================
Two weaker gates both pass the defect, and both are the shape a reasonable
author reaches for first:

  * *"assert granted is not UNKNOWN"* — passes on the unsentinelled read,
    because the unsentinelled read returns 1, and 1 is not UNKNOWN.
  * *"assert declared == granted"* — passes whenever both are 1, which is
    exactly the state ARC 013's first run was in: declared real-time, field
    never written, read as real-time, zero ticks.

**A gate that cannot tell "unset" from "granted 1" reproduces the exact defect
it exists to catch.** The assertion set below is therefore THREE-WAY and every
leg is made explicitly, including the negative ones, because
`granted is UNKNOWN` and `granted is not REALTIME` are different statements
about the same value and only the pair of them excludes the defect.

==============================================================================
SCOPE — DERIVED FROM THE TREE'S CONTENT, NOT FROM A PATH SOMEONE TYPED
==============================================================================
`debug.md` §8 failure mode #14: a scope set by a list a person edits is
silenced by omission, and no diff to the gate ever appears. There is no
datafeed file list in this module. The scope is computed on every run:

  ROSTER — the datafeed verb roster is read by AST out of whichever module in
      the tree declares `DATAFEED_PORT_VERBS`. Not typed here. A verb added to
      the port joins the quorum test automatically.

  SUBJECTS — every class under `SCAN_ROOTS` that defines at least
      `DATAFEED_QUORUM` of those roster verbs as methods and is not a
      `Protocol`. An adapter written at `scripts/broker/`, `scripts/capture/`
      or anywhere else joins the scan the moment it is written.

  THE DECLARING MODULE IS EXCLUDED FROM THE SUBJECT SET, and the exclusion is
      derived rather than named: the module that declares the roster is the
      seam, and the seam's stub says of itself that its job "is to prove the
      contract is satisfiable without a venue". A vendorless stub has no venue,
      therefore no grant, therefore nothing for this gate to observe.
      **Every excluded implementation is printed as an ADVISORY on every run**,
      named and counted, so the exclusion can never become invisible — and
      §7.12 condition 5 states what it costs.

  TEST DIRECTORIES are excluded, and that exclusion is derived too: `testpaths`
      is read out of `pyproject.toml`. Any datafeed implementation found under
      them is reported as an advisory, never silently dropped.

==============================================================================
FOUR ARMS, NONE SUFFICIENT ALONE
==============================================================================
ARM A — REPRESENTATIONAL CAPACITY. `debug.md` §7.12 instances 4 and 5 are both
    cases where the instrument could not EXPRESS the difference it was asked to
    detect, so this is checked before anything else is believed.
      A1. The seam's `MarketDataMode` declares a sentinel member (`UNKNOWN`)
          and a real-time member, with DIFFERENT values. Read by AST from the
          roster-declaring module; if the enum ever loses `UNKNOWN`, or aliases
          it onto `REALTIME`, every downstream assertion below becomes
          unfalsifiable and this arm says so.
      A2. THE SENTINEL IS NOT THE VENDOR'S DEFAULT. The pinned vendor
          distributions in `checks/pinned_deps.json` are imported in a
          subprocess and searched for a class carrying the vendor mode field;
          its dataclass default is read off the installed package. If that
          default ever equalled the sentinel, sentinelling would assert
          nothing and the whole repair would be void. This is doctrine B.7's
          shape — a fact parsed out of an external authority and compared
          against a constant the code states — pointed at a wheel instead of a
          document.

ARM B — THE THREE-WAY DRIVE, and the reason this gate exists.
      B1. BEHAVIOURAL. Every mode-resolution callable in a subject module —
          discovered by its RETURN ANNOTATION being the seam's mode enum, which
          is content-derived and survives any rename of the function — is
          executed three times and all three legs are asserted:

              sentinel value (0) -> UNKNOWN     and NOT REALTIME
              vendor default (1) -> REALTIME    and NOT UNKNOWN
              downgrade  (3)     -> DELAYED     and NOT DELAYED_FROZEN

          plus the discrimination assertion the other three do not imply:
          **leg 1 and leg 2 must produce DIFFERENT values.** An observer that
          collapses them is the defect, and it is the one leg that catches an
          implementation which "handles" the sentinel by mapping it to
          real-time.
      B2. STRUCTURAL — THE SENTINEL WRITE. A subject module that reads the
          vendor mode field must also WRITE the sentinel to it. Without that
          write the field holds the vendor default forever and B1's leg 1 never
          occurs in production no matter how correct the observer is. B1 proves
          the observer can express the distinction; B2 proves the distinction
          is actually reachable. Neither implies the other.
      B3. STRUCTURAL — NEVER INFER FROM THE REQUEST. A name passed to the
          vendor's mode-REQUEST call must not be the name that supplies the
          granted mode. *That the request was made is not evidence of what was
          granted* — it is the whole defect, and this is its plantable shape.

ARM C — NO FABRICATED GRANT OFFLINE. Each subject is CONSTRUCTED and asked for
    its `FeedLag` without any venue session. An adapter that has never
    connected has been granted nothing, so it must report `UNKNOWN`. Reporting
    a mode here is the absence principle's exact violation — substituting a
    plausible value for "not reported" — and unlike arms A and B it needs no
    vendor, so it binds against any adapter that can be constructed at all.

==============================================================================
CITATIONS
==============================================================================
`nics_risk_subsystem_spec_v1.3.md` §2A:86-92 — the broker-datafeed roster this
gate derives its quorum from. §2A:105 — invariant 3, order and datafeed
contracts are disjoint; this gate never reads an order-path artefact, and the
scope derivation is keyed to the DATAFEED roster alone so it cannot drift
across that line. §2A:104-105 — invariant 2, no vendor type crosses the seam,
which is why the granted mode must arrive as `MarketDataMode` and not as the
vendor's integer.

`MarketDataMode` itself is NOT in §2A. It is a flagged Nix addition, declared
as such in its own docstring, on the `feed_lag()` precedent. Cited that way
deliberately: `check_spec_citations` can only resolve what exists, and claiming
a section for it would manufacture the phantom-§2.1 defect ARC 018 removed.

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
Seven conditions, each stated so it could be planted.

 1. NO DATAFEED IMPLEMENTATION EXISTS, so the subject set is empty and a scan
    of zero classes reports "no violations".
    GUARDED, and this is the gate's state in ARC 021's own worktree: an empty
    subject set is CANNOT_MEASURE (exit 2), never PASS. `nix_check_contract.md`
    §5.3 — an empty scope must be CANNOT_MEASURE.

 2. A SUBJECT EXISTS BUT NOTHING IN IT CAN BE DRIVEN — every verb raises, as
    `IBKRDatafeedAdapter` in `scripts/broker/ibkr_mapping.py` does today, so
    arms B and C both find nothing to execute and the gate "passes" on arm A
    alone.
    GUARDED: PASS requires arm B1 to have executed at least one observer on all
    three legs. Arm A can never carry a PASS by itself — it proves the
    vocabulary exists, not that anyone used it.

 3. THE OBSERVER IS NOT DISCOVERABLE because it carries no return annotation,
    or its annotation is a string the resolver cannot bind to the seam's enum.
    GUARDED as CANNOT_MEASURE with the subject named, not as PASS — but the
    RESIDUAL is real and is stated rather than hidden: a subject whose mode
    resolution is inlined into `feed_lag()` with no separately annotated
    callable presents arm B1 no binding site. Arm C still binds, arm B2/B3
    still bind, and the gate reports exactly which arms measured. Closing it
    means executing the adapter against a synthesised vendor SDK, which is
    NAMED GAP 1 below.

 4. THE VENDOR DEFAULT CHANGES to 0 upstream, making the sentinel
    indistinguishable from an unset field again while every assertion here
    still passes.
    GUARDED by arm A2, which reads the default off the installed distribution
    every run instead of trusting this docstring. If the pinned wheel is
    missing, A2 is CANNOT_MEASURE — it never assumes.

 5. THE SUBJECT MOVES INTO THE DECLARING MODULE. An adapter written inside
    `broker_seam.py` is excluded by the seam-exclusion rule and vanishes from
    the subject set.
    PARTIALLY GUARDED: the exclusion is reported as an advisory on every run
    with each excluded class named, and if the exclusion empties the subject
    set the verdict is CANNOT_MEASURE by condition 1. It is not fully closed,
    because distinguishing "the vendorless reference stub" from "a vendor
    adapter someone put in the wrong file" is a judgment about intent. The
    mitigation is that the wrong file is itself an invariant-3 breach and would
    be visible in review; the advisory is what makes it visible here.

 6. `SCAN_ROOTS` DOES NOT CONTAIN THE DATAFEED. Code outside `scripts/` is not
    walked at all. UNGUARDED, same residual `check_order_path_bans` carries,
    and stated for the same reason: an undocumented limit is one refactor from
    being met silently.

 7. THE MODE FIELD IS SPELLED DIFFERENTLY. `VENDOR_MODE_FIELD` and
    `VENDOR_REQUEST_CALLS` are data. A second venue naming its granted mode
    something else is invisible to arms B2 and B3 until its spelling is added.
    UNGUARDED BY CONSTRUCTION, and deliberately so: these are vendor wire
    names, they cannot be derived from a vendor-neutral seam, and inventing a
    heuristic over them would be a stale literal anchor with extra steps
    (`debug.md` §7.4). Arm A2's search over the pinned distributions is the
    partial mitigation — it finds the field on whatever class actually carries
    it — and arm B1, which is behavioural, does not depend on the spelling at
    all.

NAMED GAP 1 — DRIVING THE ADAPTER AGAINST A SYNTHESISED VENDOR SDK, ASSESSED
AND NOT CLOSED. Arms B1 and C execute real code, but neither drives the full
`subscribe -> callback -> feed_lag` sequence, because doing so requires a
stand-in for the whole vendor client. A permissive stand-in is `debug.md`
§7.12 instance 5 exactly — the polite fake whose missing `multiplier` made two
different units numerically identical — and a faithful one is a second
implementation of the vendor SDK, which nobody can keep honest. What closes
this properly is a LIVE session, which is the known-red this gate carries.
Recorded here rather than half-closed.
"""

from __future__ import annotations

import ast
import json
import subprocess  # nosec B404 - fixed argv, shell=False, no user input
import sys
import tomllib
from pathlib import Path
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code): the §4.2 `__main__` block and the crash handler are
# MANDATED to be the same text in every check, and the only way to deduplicate
# them is the shared helper §4.2 forbids. Same refusal every other gate carries.
# pylint: disable=duplicate-code
#
# C0302 (too-many-lines) disabled. The module is over pylint's 1000-line default
# with EVERY line of the module docstring removed — derive it, do not read it:
#   .venv/bin/python -c "import ast,pathlib;s=pathlib.Path(
#     'checks/check_datafeed_granted_mode.py').read_text();d=ast.get_docstring(
#     ast.parse(s),clean=False);print(len(s.splitlines()),
#     len(d.splitlines())+2)"
# so trimming prose cannot fix it, and two doctrine rules put the prose there:
# debug.md §7.12 requires the standing question be answered IN WRITING BESIDE
# THE GATE (seven conditions here, each stated so it could be planted), and
# `nix_check_contract.md` §5.5 requires this property be owned by ONE
# instrument, so all four arms, the scope derivation and the probe live in one
# file by design. Splitting to satisfy a line count would either move the §7.12
# answer away from the gate or create the second instrument §5.5 forbids. Same
# refusal, for the same two reasons, as check_order_path_bans.py.
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_datafeed_granted_mode"

# --------------------------------------------------------------------------
# SCOPE — no file list. Roots only, and the roots are a FLOOR (§7.12 cond. 6).
# --------------------------------------------------------------------------
SCAN_ROOTS: tuple[str, ...] = ("scripts",)
SKIP_DIRS: frozenset[str] = frozenset({".venv", "__pycache__", ".git", "graphify-out"})

# The seam constants that identify the datafeed declaration. Their VALUES are
# never typed here — only the names of the constants to go and read.
ROSTER_CONST = "DATAFEED_PORT_VERBS"
EVENTS_CONST = "DATAFEED_EVENTS"

# The seam enum that must be able to express "nothing was granted".
MODE_ENUM = "MarketDataMode"
SENTINEL_MEMBER = "UNKNOWN"
REALTIME_MEMBER = "REALTIME"
DELAYED_MEMBER = "DELAYED"
DELAYED_FROZEN_MEMBER = "DELAYED_FROZEN"

# How many roster verbs a class must define before it counts as an
# implementation. Three of five: the seam's own stub defines all five, and the
# highest incidental overlap outside the datafeed is `connect`/`disconnect`,
# which is two — so three discriminates, and it discriminates by a measured
# margin rather than a guessed one.
DATAFEED_QUORUM = 3

# --------------------------------------------------------------------------
# VENDOR WIRE NAMES — data, not logic, and §7.12 condition 7 owns the limit.
# These cannot be derived from a vendor-neutral seam by construction.
# --------------------------------------------------------------------------
VENDOR_MODE_FIELD = "marketDataType"
VENDOR_REQUEST_CALLS: tuple[str, ...] = ("reqMarketDataType",)

# The three legs. (probe input, expected member, member it must NOT be.)
# Leg 1's input is the sentinel; leg 2's is the vendor default, re-measured by
# arm A2 on every run and asserted equal to this before the leg is believed.
THREE_WAY: tuple[tuple[int, str, str], ...] = (
    (0, SENTINEL_MEMBER, REALTIME_MEMBER),
    (1, REALTIME_MEMBER, SENTINEL_MEMBER),
    (3, DELAYED_MEMBER, DELAYED_FROZEN_MEMBER),
)


class Subject(NamedTuple):
    """One datafeed implementation found in the tree."""

    rel: str
    cls: str


class Roster(NamedTuple):
    """The seam's datafeed declaration, read out of the tree."""

    rel: str
    verbs: tuple[str, ...]


# --------------------------------------------------------------------------
# TREE WALK
# --------------------------------------------------------------------------
def _testpaths(home: Path) -> tuple[str, ...]:
    """Test roots, read from pyproject.toml — never a literal (#14)."""
    cfg = home / "pyproject.toml"
    if not cfg.is_file():
        return ()
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    paths = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return tuple(paths.get("testpaths", []))


def _walk(home: Path) -> list[Path]:
    """Every .py under SCAN_ROOTS, skipping SKIP_DIRS."""
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = home / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
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

    Both `X = (...)` and `X: tuple[str, ...] = (...)` are handled: the seam
    declares its rosters annotated, and a reader that walked only `ast.Assign`
    would report "no module declares the roster" while looking straight at it."""
    targets: list[ast.expr] = []
    value: ast.expr | None = None
    if isinstance(node, ast.Assign):
        targets, value = list(node.targets), node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets, value = [node.target], node.value
    if any(isinstance(t, ast.Name) and t.id == name for t in targets):
        return value
    return None


def _str_tuple(value: ast.expr) -> tuple[str, ...] | None:
    """The value as a tuple of string literals, or None if it is anything else."""
    if not isinstance(value, (ast.Tuple, ast.List)):
        return None
    got: list[str] = []
    for elt in value.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            got.append(elt.value)
    return tuple(got) if len(got) == len(value.elts) else None


def _tuple_const(tree: ast.Module, name: str) -> tuple[str, ...] | None:
    """Read a module-level tuple-of-str constant by AST. No import, no exec."""
    for node in tree.body:
        value = _const_binding(node, name)
        if value is not None:
            got = _str_tuple(value)
            if got is not None:
                return got
    return None


def _roster(home: Path) -> Roster | None:
    """Find whichever module declares the datafeed roster, and read it."""
    for path in _walk(home):
        tree = _parse(path)
        if tree is None:
            continue
        verbs = _tuple_const(tree, ROSTER_CONST)
        if verbs:
            return Roster(str(path.relative_to(home)), verbs)
    return None


def _datafeed_events(home: Path, roster: Roster) -> tuple[str, ...]:
    """The seam's datafeed EVENT roster — what a sink double must satisfy."""
    tree = _parse(home / roster.rel)
    return (tree and _tuple_const(tree, EVENTS_CONST)) or ()


def _is_protocol(node: ast.ClassDef) -> bool:
    names = {ast.unparse(b) for b in node.bases}
    return any(n.split(".")[-1] == "Protocol" for n in names)


def _methods(node: ast.ClassDef) -> set[str]:
    return {
        b.name
        for b in node.body
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _implementations(tree: ast.Module, verbs: tuple[str, ...]) -> list[str]:
    """Class names in this module meeting the datafeed quorum."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or _is_protocol(node):
            continue
        if len(_methods(node) & set(verbs)) >= DATAFEED_QUORUM:
            found.append(node.name)
    return found


def _scope(home: Path, roster: Roster) -> tuple[list[Subject], list[str]]:
    """(subjects, advisories). The declaring module and testpaths are excluded
    and every exclusion is named — an invisible exclusion is failure mode #14
    wearing a different hat."""
    subjects: list[Subject] = []
    advisories: list[str] = []
    tests = _testpaths(home)
    for path in _walk(home):
        rel = str(path.relative_to(home))
        tree = _parse(path)
        if tree is None:
            continue
        impls = _implementations(tree, roster.verbs)
        if not impls:
            continue
        if rel == roster.rel:
            advisories += [
                f"excluded (declaring module, vendorless): {rel}:{c}" for c in impls
            ]
        elif any(rel.startswith(t) for t in tests):
            advisories += [f"excluded (testpaths): {rel}:{c}" for c in impls]
        else:
            subjects += [Subject(rel, c) for c in impls]
    return subjects, advisories


# --------------------------------------------------------------------------
# ARM A1 — the seam's enum can express the distinction
# --------------------------------------------------------------------------
def _int_members(node: ast.ClassDef) -> dict[str, int]:
    """`NAME = <int>` members of one class body."""
    out: dict[str, int] = {}
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Constant):
            continue
        if not isinstance(stmt.value.value, int):
            continue
        for tgt in stmt.targets:
            if isinstance(tgt, ast.Name):
                out[tgt.id] = stmt.value.value
    return out


def _enum_members(home: Path, roster: Roster) -> dict[str, int]:
    """`MarketDataMode` members, by AST, out of the roster-declaring module."""
    tree = _parse(home / roster.rel)
    if tree is None:
        return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == MODE_ENUM:
            return _int_members(node)
    return {}


def _arm_a1(members: dict[str, int], roster: Roster) -> list[tuple[str, str]]:
    site = f"{roster.rel}:{MODE_ENUM}"
    missing = [m for m in (SENTINEL_MEMBER, REALTIME_MEMBER) if m not in members]
    if missing:
        return [
            (site, f"cannot express the distinction — missing {', '.join(missing)}")
        ]
    if members[SENTINEL_MEMBER] == members[REALTIME_MEMBER]:
        return [
            (
                site,
                (
                    f"{SENTINEL_MEMBER} and {REALTIME_MEMBER} share value "
                    f"{members[SENTINEL_MEMBER]} — an unset field is a real-time grant"
                ),
            )
        ]
    return []


# --------------------------------------------------------------------------
# ARM B2/B3 — structural: the sentinel write, and never-infer-from-the-request
# --------------------------------------------------------------------------
def _mode_field_reads(tree: ast.Module) -> int:
    return sum(
        1
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute)
        and n.attr == VENDOR_MODE_FIELD
        and isinstance(n.ctx, ast.Load)
    )


def _sentinel_writes(tree: ast.Module, sentinel: int) -> int:
    """Assignments writing the sentinel value into the vendor mode field."""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        hits = [
            t
            for t in node.targets
            if isinstance(t, ast.Attribute) and t.attr == VENDOR_MODE_FIELD
        ]
        if not hits:
            continue
        val = node.value
        literal = isinstance(val, ast.Constant) and val.value == sentinel
        member = (
            isinstance(val, ast.Attribute)
            and val.attr == SENTINEL_MEMBER
            and ast.unparse(val).split(".")[-2:-1] == [MODE_ENUM]
        )
        if literal or member:
            count += 1
    return count


def _requested_names(tree: ast.Module) -> set[str]:
    """Names handed to the vendor's mode-REQUEST call."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        tail = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if tail not in VENDOR_REQUEST_CALLS:
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            out |= {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
            out |= {n.attr for n in ast.walk(arg) if isinstance(n, ast.Attribute)}
    return out


def _granted_names(tree: ast.Module) -> set[str]:
    """Names that supply the value of a `granted_mode=` keyword."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "granted_mode":
                continue
            out |= {n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)}
            out |= {n.attr for n in ast.walk(kw.value) if isinstance(n, ast.Attribute)}
    return out


def _arm_b23(
    home: Path, subject: Subject, sentinel: int
) -> tuple[list[tuple[str, str]], list[str]]:
    """(defects, measured-notes) for the two structural sub-arms."""
    tree = _parse(home / subject.rel)
    if tree is None:
        return [(subject.rel, "unparseable")], []
    defects: list[tuple[str, str]] = []
    notes: list[str] = []
    reads = _mode_field_reads(tree)
    writes = _sentinel_writes(tree, sentinel)
    if reads:
        notes.append(f"B2 {subject.rel}: {reads} read(s), {writes} sentinel write(s)")
        if not writes:
            defects.append(
                (
                    f"{subject.rel}:{VENDOR_MODE_FIELD}",
                    (
                        f"reads the vendor mode field {reads}x and never writes the "
                        f"sentinel {sentinel} to it — an unread field reports the vendor "
                        f"default, which is a grant that never happened"
                    ),
                )
            )
    shared = _requested_names(tree) & _granted_names(tree)
    if _requested_names(tree):
        notes.append(
            f"B3 {subject.rel}: request-call names {sorted(_requested_names(tree))}"
        )
    if shared:
        defects.append(
            (
                f"{subject.rel}:granted_mode",
                (
                    f"granted mode is derived from the REQUESTED value {sorted(shared)} — "
                    "that the request was made is not evidence of what was granted"
                ),
            )
        )
    return defects, notes


# --------------------------------------------------------------------------
# ARM B1 / ARM C — behavioural, in a subprocess under the venv interpreter
# --------------------------------------------------------------------------
def _observers(home: Path, subject: Subject) -> list[str]:
    """Callables whose RETURN ANNOTATION is the seam's mode enum.

    Discovery by annotation, not by name: a rename of the function does not
    hide it, which is `debug.md` §7.4's requirement applied to a scope."""
    tree = _parse(home / subject.rel)
    if tree is None:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.returns is None:
            continue
        if ast.unparse(node.returns).strip("\"'").split(".")[-1] == MODE_ENUM:
            out.append(node.name)
    return sorted(set(out))


def _venv_python(home: Path) -> Path:
    return home / ".venv" / "bin" / "python3"


def _drive(home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Re-enter this module as a probe under the venv interpreter.

    A subprocess, never an in-process import: an adapter module imported into
    the gate's own interpreter would leave its vendor imports resident for
    every later check in the same `verify.py` run."""
    python = _venv_python(home)
    if not python.is_file():
        return {"error": f"no venv interpreter at {python}"}
    argv = [str(python), str(Path(__file__).resolve()), "--drive", json.dumps(payload)]
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            argv,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(home),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": f"probe failed: {type(exc).__name__}: {exc}"}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {
            "error": f"probe rc={proc.returncode} stderr={proc.stderr.strip()[:400]}"
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"probe output not JSON: {exc}"}


def _sink_double(events: tuple[str, ...]) -> Any:
    """A recording sink built FROM the seam's event roster, not from a list.

    Derived so that an event added to `DATAFEED_EVENTS` is satisfied by the
    double automatically — a hand-written double is failure mode #14 one level
    down, and `debug.md` §7.12 instance 7 is an ORDER sink handed to the
    DATAFEED port, which a roster-derived double cannot be."""
    body = {e: (lambda *a, **k: None) for e in events}
    return type("GateFeedSinkDouble", (), body)()


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------
def _vendor_default(home: Path, pins: list[str]) -> dict[str, Any]:
    return _drive(home, {"op": "vendor_default", "packages": pins})


def _pinned_packages(home: Path) -> list[str]:
    path = home / "checks" / "pinned_deps.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return sorted(data.get("packages", {}))


def _cannot(detail: str, evidence: str = "") -> CheckResult:
    return CheckResult(
        name=NAME, status=Status.CANNOT_MEASURE, detail=detail, evidence=evidence
    )


def _arm_a2(
    home: Path, members: dict[str, int]
) -> tuple[list[tuple[str, str]], str, int | None]:
    """(defects, note, measured vendor default)."""
    pins = _pinned_packages(home)
    if not pins:
        return [], "A2: no pinned distributions to search — CANNOT MEASURE", None
    res = _vendor_default(home, pins)
    if "error" in res or res.get("default") is None:
        return (
            [],
            f"A2: vendor default not measurable — {res.get('error', 'not found')}",
            None,
        )
    default = int(res["default"])
    where = res.get("where", "?")
    note = f"A2: vendor default {VENDOR_MODE_FIELD}={default} measured on {where}"
    if default == members.get(SENTINEL_MEMBER):
        return (
            [
                (
                    where,
                    (
                        f"the vendor default equals the seam sentinel ({default}) — "
                        "sentinelling asserts nothing and an unset field is a grant"
                    ),
                )
            ],
            note,
            default,
        )
    return [], note, default


def _behavioural(
    home: Path,
    subjects: list[Subject],
    members: dict[str, int],
    events: tuple[str, ...],
) -> tuple[list[tuple[str, str]], list[str], int]:
    """Arms B1 and C, one probe for the whole subject set."""
    payload = {
        "op": "drive",
        "home": str(home),
        "subjects": [
            {"rel": s.rel, "cls": s.cls, "observers": _observers(home, s)}
            for s in subjects
        ],
        "three_way": [list(t) for t in THREE_WAY],
        "members": members,
        "mode_enum": MODE_ENUM,
        "events": list(events),
    }
    res = _drive(home, payload)
    if "error" in res:
        return [], [f"B1/C: probe unavailable — {res['error']}"], 0
    defects = [(d["site"], d["why"]) for d in res.get("defects", [])]
    return defects, list(res.get("notes", [])), int(res.get("legs", 0))


def _representational(
    home: Path, roster: Roster, members: dict[str, int]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Arm A: the seam's enum can express the distinction, and the sentinel is
    not the vendor's own default."""
    a2_defects, a2_note, _ = _arm_a2(home, members)
    return (
        _arm_a1(members, roster) + a2_defects,
        [f"A1: {MODE_ENUM} = {members}", a2_note],
    )


def _static_arms(
    home: Path, subjects: list[Subject], sentinel: int
) -> tuple[list[tuple[str, str]], list[str]]:
    """Arms B2 and B3 over every subject."""
    defects: list[tuple[str, str]] = []
    notes: list[str] = []
    for subject in subjects:
        sub_defects, sub_notes = _arm_b23(home, subject, sentinel)
        defects += sub_defects
        notes += sub_notes
    return defects, notes


def _verdict(defects: list[tuple[str, str]], evidence: str, legs: int) -> CheckResult:
    """FAIL dominates; then the three-way must have actually run; only then PASS."""
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(s for s, _ in defects),
            evidence=evidence,
            detail="; ".join(f"{s}: {w}" for s, w in defects),
        )
    if legs < len(THREE_WAY):
        return _cannot(
            f"arm B1 executed {legs} of {len(THREE_WAY)} legs — the three-way "
            "distinction is unproven, so a PASS would measure nothing "
            "(§7.12 cond. 2/3)",
            evidence=evidence,
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Verdict. PASS requires arm B1 to have executed all three legs."""
    home = ctx.nix_home
    roster = _roster(home)
    if roster is None:
        return _cannot(f"no module under {SCAN_ROOTS} declares {ROSTER_CONST}")
    members = _enum_members(home, roster)
    if not members:
        return _cannot(f"{roster.rel} declares {ROSTER_CONST} but no {MODE_ENUM} enum")

    defects, notes = _representational(home, roster, members)
    subjects, advisories = _scope(home, roster)
    notes.append(
        f"scope: roster {roster.rel} {roster.verbs}; "
        f"{len(subjects)} subject(s) {[f'{s.rel}:{s.cls}' for s in subjects]}; "
        f"{len(advisories)} advisory: {advisories}"
    )
    if not subjects:
        return _cannot(
            "no broker-datafeed implementation outside the declaring module — "
            "nothing grants a mode, so there is nothing to observe (§7.12 cond. 1)",
            evidence="; ".join(notes),
        )

    static_defects, static_notes = _static_arms(
        home, subjects, members[SENTINEL_MEMBER]
    )
    beh_defects, beh_notes, legs = _behavioural(
        home, subjects, members, _datafeed_events(home, roster)
    )
    defects += static_defects + beh_defects
    notes += static_notes + beh_notes
    return _verdict(defects, "; ".join(notes), legs)


# --------------------------------------------------------------------------
# PROBE — runs in a separate interpreter (see _drive)
# --------------------------------------------------------------------------
def _class_mode_default(obj: type) -> Any | None:
    """The dataclass default of the vendor mode field on `obj`, if it has one."""
    import dataclasses  # pylint: disable=import-outside-toplevel

    if not dataclasses.is_dataclass(obj):
        return None
    for field in dataclasses.fields(obj):
        if field.name == VENDOR_MODE_FIELD and field.default is not dataclasses.MISSING:
            return field.default
    return None


def _package_mode_default(pkg: str) -> dict[str, Any] | None:
    """Search one installed distribution for the class carrying the mode field."""
    import importlib  # pylint: disable=import-outside-toplevel

    try:
        mod = importlib.import_module(pkg)
    except ImportError:
        return None
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if not isinstance(obj, type):
            continue
        default = _class_mode_default(obj)
        if default is not None:
            return {"default": default, "where": f"{pkg}.{attr}.{VENDOR_MODE_FIELD}"}
    return None


def _probe_vendor_default(packages: list[str]) -> dict[str, Any]:
    """The vendor default, MEASURED off the installed wheel — never restated."""
    for pkg in packages:
        found = _package_mode_default(pkg)
        if found is not None:
            return found
    return {"default": None}


def _drive_legs(
    fn: Any, site_prefix: str, three_way: list
) -> tuple[list, list, int, dict[int, str]]:
    """Run one observer over all three legs. (defects, notes, legs, seen)."""
    defects: list[dict[str, str]] = []
    notes: list[str] = []
    legs = 0
    seen: dict[int, str] = {}
    for value, want, forbid in three_way:
        try:
            got = fn(value)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            notes.append(
                f"B1 {site_prefix}({value}): raised {type(exc).__name__}: {exc}"
            )
            continue
        legs += 1
        name = getattr(got, "name", repr(got))
        seen[value] = name
        site = f"{site_prefix}({value})"
        if name != want:
            defects.append({"site": site, "why": f"reported {name}, expected {want}"})
        if name == forbid:
            defects.append({"site": site, "why": f"reported {forbid} — the defect"})
        notes.append(f"B1 {site} -> {name}")
    return defects, notes, legs, seen


def _discrimination(site_prefix: str, seen: dict[int, str]) -> list:
    """THE LEG THE OTHER THREE DO NOT IMPLY: the sentinel and the vendor default
    must not produce the same answer. An observer that collapses them is the
    defect, and every other assertion here passes while it does."""
    if 0 in seen and 1 in seen and seen[0] == seen[1]:
        return [
            {
                "site": site_prefix,
                "why": (
                    f"sentinel 0 and vendor default 1 both report {seen[0]} — "
                    "the observer cannot tell an unset field from a real-time grant"
                ),
            }
        ]
    return []


def _resolve_observer(mod: Any, spec: dict[str, Any], obs: str) -> Any:
    fn = getattr(mod, obs, None)
    if fn is None:
        fn = getattr(getattr(mod, spec["cls"], None), obs, None)
    return fn if callable(fn) else None


def _drive_one_observer(
    mod: Any, spec: dict[str, Any], obs: str, payload: dict[str, Any]
) -> tuple[list, list, int]:
    """One observer, three legs, plus the discrimination assertion."""
    prefix = f"{spec['rel']}:{obs}"
    fn = _resolve_observer(mod, spec, obs)
    if fn is None:
        return [], [f"B1 {prefix}: not resolvable"], 0
    defects, notes, legs, seen = _drive_legs(fn, prefix, payload["three_way"])
    return defects + _discrimination(prefix, seen), notes, legs


def _probe_observers(
    spec: dict[str, Any], payload: dict[str, Any]
) -> tuple[list, list, int]:
    import importlib  # pylint: disable=import-outside-toplevel

    notes: list[str] = []
    modname = Path(spec["rel"]).stem
    try:
        mod = importlib.import_module(modname)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        notes.append(f"B1 {spec['rel']}: not importable — {type(exc).__name__}: {exc}")
        return [], notes, 0
    defects: list[dict[str, str]] = []
    legs = 0
    for obs in spec["observers"]:
        got_defects, got_notes, got_legs = _drive_one_observer(mod, spec, obs, payload)
        defects += got_defects
        notes += got_notes
        legs = max(legs, got_legs)
    return defects, notes, legs


def _probe_offline(spec: dict[str, Any], events: tuple[str, ...]) -> tuple[list, list]:
    import importlib  # pylint: disable=import-outside-toplevel

    defects: list[dict[str, str]] = []
    notes: list[str] = []
    modname = Path(spec["rel"]).stem
    try:
        mod = importlib.import_module(modname)
        cls = getattr(mod, spec["cls"])
        inst = cls(_sink_double(events))
        lag = inst.feed_lag()
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        notes.append(
            f"C {spec['rel']}:{spec['cls']}: not drivable — {type(exc).__name__}"
        )
        return defects, notes
    name = getattr(getattr(lag, "granted_mode", None), "name", "?")
    notes.append(f"C {spec['rel']}:{spec['cls']}: offline granted_mode={name}")
    if name != SENTINEL_MEMBER:
        defects.append(
            {
                "site": f"{spec['rel']}:{spec['cls']}.feed_lag",
                "why": (
                    f"never connected, yet reports granted_mode={name} — a grant that "
                    "did not happen; the seam declares absence, it never substitutes "
                    "a value for one"
                ),
            }
        )
    return defects, notes


def _probe_main(raw: str) -> int:
    payload = json.loads(raw)
    if payload["op"] == "vendor_default":
        print(json.dumps(_probe_vendor_default(payload["packages"])))
        return 0
    home = Path(payload["home"])
    sys.path[:0] = [str(home / "scripts"), str(home / "scripts" / "broker")]
    events = tuple(payload.get("events", ()))
    defects: list[dict[str, str]] = []
    notes: list[str] = []
    legs = 0
    for spec in payload["subjects"]:
        obs_d, obs_n, obs_legs = _probe_observers(spec, payload)
        off_d, off_n = _probe_offline(spec, events)
        defects += obs_d + off_d
        notes += obs_n + off_n
        legs = max(legs, obs_legs)
    print(json.dumps({"defects": defects, "notes": notes, "legs": legs}))
    return 0


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.contract import exit_code_for, validate_result

    if len(sys.argv) > 2 and sys.argv[1] == "--drive":
        sys.exit(_probe_main(sys.argv[2]))

    if len(sys.argv) > 1 and sys.argv[1] == "--print-scope-count":
        _HOME = (
            Path(sys.argv[2])
            if len(sys.argv) > 2
            else Path(__file__).resolve().parent.parent
        )
        _R = _roster(_HOME)
        # MODULES, not classes: this number is one source of the
        # `datafeed_scope_files` claim and the sibling gate derives the other,
        # so the two must be counting the same thing or the claim compares
        # nothing (evidence instance 7 — two derivations that coincide).
        print(len({s.rel for s in _scope(_HOME, _R)[0]}) if _R else 0)
        sys.exit(0)

    HOME = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
