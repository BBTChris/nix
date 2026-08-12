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
      B0. THE MAPPING. Every MODULE-LEVEL pure mapping from a vendor integer to
          the seam's enum, in a subject module, executed over the three legs:

              sentinel value (0) -> UNKNOWN     and NOT REALTIME
              vendor default (1) -> REALTIME    and NOT UNKNOWN
              downgrade  (3)     -> DELAYED     and NOT DELAYED_FROZEN

          plus the discrimination assertion the other three do not imply:
          **leg 1 and leg 2 must produce DIFFERENT values.** A mapping that
          collapses them is the defect. THIS ARM CANNOT CARRY A PASS AND
          CONTRIBUTES NO LEG — see B1 for why that sentence is the whole repair.

      B1. THE LIFECYCLE, AND IT IS WHAT THIS GATE NOW MEANS BY "MEASURED".
          REBUILT IN ARC 023 (D3.16). What stood here discovered its observers
          BY RETURN ANNOTATION and called them with a raw integer. That works
          for a pure function and cannot work for an accessor: the port's mode
          verb takes a SYMBOL, so `granted_mode(0)` put the mode integer in
          `self` and raised `AttributeError` on all three legs — while
          `resolve_granted_mode`, a module-level helper carrying the same
          annotation, drove three green legs beside it and the verdict took the
          MAXIMUM. **The gate reported PASS across two arcs over a method it had
          never once executed**, and ARC 021's real plant 2 lives in exactly
          that method.

          The observer is now the roster verb the PORT PROTOCOL declares as
          returning the mode enum (`_port_mode_verb`), and it is driven as a
          LIFECYCLE on a CONSTRUCTED subject rather than called with a number:

            1. constructed, never connected     -> the sentinel. A grant cannot
                                                   precede a session.
            2. subscribed, no grant callback    -> the sentinel, PER SYMBOL and
                                                   ADAPTER-WIDE. This is leg 0,
                                                   driven from a real absence
                                                   instead of a synthetic value.
            3. venue grants 1                   -> REALTIME, not the sentinel
            4. RE-SUBSCRIBED                    -> the sentinel again. A grant
                                                   belongs to a subscription and
                                                   is never inherited.
            5. venue grants 3                   -> DELAYED, not DELAYED_FROZEN
            6. two symbols, two different grants -> the adapter-wide answer is
                                                   the sentinel, never one of
                                                   them. A single mode reported
                                                   for a set that does not share
                                                   one is a fabricated value.
            7. discrimination: steps 2 and 3 must differ.

          The grant is delivered through the subject's OWN callback, found by
          `_grant_writers` — a method that assigns the mode state and takes a
          vendor `int`. Nothing in this file names a vendor keyword, a callback,
          or a symbol type; every one of them is read off the tree.

          NON-VACUITY IS ASSERTED ON EVERY RUN, NOT ONCE. The lifecycle is run
          under `sys.settrace` and the gate asserts the port's mode verb appears
          in the execution trace OF THE SUBJECT'S OWN FILE. A subject the gate
          could not drive is CANNOT_MEASURE naming the subject — never PASS.
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
    GUARDED: PASS requires at least one subject to have completed the WHOLE
    lifecycle, and requires the port's mode verb to appear in that subject's own
    execution trace. Arm A can never carry a PASS by itself — it proves the
    vocabulary exists, not that anyone used it — and neither can arm B0, which
    is why B0 returns no leg count at all.
    THE RESIDUAL, STATED: a subject that raises `NotImplementedError` is
    recorded as REFUSING and does not block a PASS earned by another subject.
    That is deliberate — `ibkr_mapping.IBKRDatafeedAdapter` is a refusing
    skeleton whose whole contract is to raise, and reddening it for honouring
    that contract is doctrine B.4's forbidden direction — and it is a hole an
    adapter could hide in by raising `NotImplementedError` everywhere. Every
    refusing subject is NAMED in the evidence on every run, which is the same
    mitigation the seam-exclusion advisory gets in condition 5.

 3. THE OBSERVER IS NOT DISCOVERABLE. This was the condition the gate FELL
    THROUGH rather than the one it guarded, and the correction is the reason
    arm B1 was rebuilt. As written, discovery was by RETURN ANNOTATION over a
    subject module, so a module-level pure helper carrying that annotation was
    collected beside the accessor and its three green legs were taken as the
    subject's, by `max`. GUARDED NOW at the source: the observer is named by the
    PORT ROSTER and the Protocol's own signature, and the trace assertion makes
    "did the gate execute it?" a machine question. A port that declares no verb
    returning the mode enum is CANNOT_MEASURE naming the roster, never PASS.
    THE RESIDUAL that survives: driving requires the subject to be CONSTRUCTIBLE
    offline. A vendor adapter that opens a socket in `__init__` presents no
    binding site, is reported as `not constructible` with the exception, and is
    CANNOT_MEASURE. That is honest, and it is not closed.

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

 8. THE VENDOR SLOT IS NEVER FOUND, so no construction reaches `connect()` and
    the lifecycle never starts. NEW IN ARC 023, because the lifecycle is new.
    GUARDED as CANNOT_MEASURE naming every candidate slot tried and the
    exception each produced. The slot is found by DRIVING — each optional
    `None`-defaulted constructor keyword is filled with an absorber in turn and
    the first that completes the lifecycle wins — rather than by naming `ib`,
    which would be `debug.md` §7.4's stale anchor pointed at a vendor keyword.

NAMED GAP 1 — DRIVING THE ADAPTER AGAINST A SYNTHESISED VENDOR SDK. NARROWED
IN ARC 023, NOT CLOSED, AND THE NARROWING IS WHAT THIS ARC BOUGHT. The gate now
DOES drive `construct -> connect -> subscribe -> grant callback -> read ->
re-subscribe` against the real adapter, which is the sequence this gap said it
did not. What makes that admissible rather than `debug.md` §7.12 instance 5 —
the polite fake whose missing `multiplier` made two different units numerically
identical — is that `_Absorber` is a SINK AND NOT A SOURCE: it accepts every
wire call and returns only more of itself, and every value asserted on comes
back out of the subject's own state through the port's own verb. A stand-in that
started returning meaningful values would void that argument.

WHAT IS STILL NOT DRIVEN, and it is the real remainder: the venue's own
behaviour. That IBKR grants 3 when 4 is requested, silently, is a fact about the
venue, and no absorber can produce it. Only a LIVE session can, and that is the
known-red this gate carries (`docs/CHECK-DEBT.md` D1.33). The gate now proves
the adapter reports the grant it is GIVEN; it does not prove what the venue
gives.
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

# --- ARC 025 orchestration declarations (read statically, never imported) ---
#: DEPENDS ON THE VENV, and unlike `check_python_deps` this gate cannot repair
#: it. `_drive` refuses to run without `.venv/bin/python3` and every behavioural
#: arm — A2's vendor-wheel read and the whole subscribe/grant/re-subscribe
#: lifecycle — is inside that subprocess, so an absent venv silently reduces
#: this gate to its two representational arms. `check_python_deps` declares no
#: dependency because the venv is ITS subject and it repairs what it needs; here
#: the venv is the INSTRUMENT, and an instrument this gate cannot fix must be
#: established before it runs or its coverage is set by the box's state.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Reads the venv interpreter (never writes it) and imports the adapter only in
#: a SUBPROCESS — deliberately, so vendor imports do not stay resident in the
#: engine's interpreter for every later check. That is why this gate makes no
#: `interpreter:*` claim and its sibling does. `sys.settrace` is likewise set
#: inside the probe process, not in the engine's, so it is not a claim on the
#: shared interpreter either.
RESOURCES: tuple[str, ...] = ("venv",)
#: Not time-bound: the runtime is dominated by constructing and driving the
#: subjects, not by waiting. `EXPECTED_S` is declared anyway and is derived from
#: this module's OWN bound rather than from a stopwatch (§4.4 forbids the
#: stopwatch): `_drive`'s `subprocess.run(..., timeout=120)`, and `run()` reaches
#: `_drive` twice on the worst path — once for `_vendor_default`, once for the
#: lifecycle — so the bound this gate can take is 240 s. It is a CEILING, and a
#: ceiling that cannot move under load is the point; the observed 0.47 s is a
#: moving anchor and is not what is declared here.
TIME_BOUND = False
EXPECTED_S = 240.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the broker-datafeed adapter's SOURCE and the mode it "
    "reports. A repair here is a code change on the §2A datafeed path, and the "
    "one repair an engine could plausibly automate — writing the sentinel back "
    "into subscribe() — is the exact line whose deletion is this gate's own "
    "banked plant, so the engine would be authoring the code it then grades "
    "(§4.3, a vacuous pass by construction). Arm A2 additionally reads the "
    "PINNED vendor wheel; 'correcting' a vendor default would mean mutating an "
    "installed distribution to satisfy an assertion about it"
)
#: The artifacts this gate DRIVES. A literal because `declarations.py` reads it
#: by AST (§4.4) — and a literal file list in a gate whose docstring insists
#: there is no datafeed file list in this module is a restatement, so it is
#: closed mechanically: `_subjects_defect` compares it against the scope this
#: run derived and FAILS on divergence (doctrine B.7).
SUBJECTS: tuple[str, ...] = (
    "scripts/broker/broker_seam.py",
    "scripts/broker/broker_datafeed_ibkr.py",
    "scripts/broker/ibkr_mapping.py",
)

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

# Symbols the LIFECYCLE drive subscribes. Two, because the adapter-wide answer
# over two DIFFERENTLY-granted subscriptions is a leg the single-symbol legs do
# not imply. Spelled so they could never be a real contract.
PROBE_SYMBOLS: tuple[str, str] = ("GATE-PROBE-A", "GATE-PROBE-B")

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


# ARC 021 PHASE 4 REPAIR — doctrine B.4, measured not theorised.
#
# `self` and `cls` are BINDING names, not value sources. Arm B3 asks whether the
# value handed to the vendor's request call is the same value reported as granted.
# It answers that by intersecting two name sets, which is a name-identity
# approximation of dataflow — and every method call on an object contributes the
# receiver's name to both sets. So a correct adapter that writes
#
#     self._ib.reqMarketDataType(self._requested_mode.value)   # requested: {self, ...}
#     ... granted_mode=self.granted_mode(symbol)               # granted:   {self, ...}
#
# intersects to `{'self'}` and is reported as deriving the grant from the request —
# which is the OPPOSITE of what that code does: `granted_mode()` floors at UNKNOWN and
# never reads `_requested_mode`. This gate reddened the correct implementation of its
# own subject on the first real adapter it ever bound to, which `VERIFY-AND-CHECKS.md`
# doctrine B.4 calls BROKEN, not strict.
#
# Excluding the two binding names is the minimum repair that removes the false
# positive without weakening the arm: a genuine `granted_mode=requested_mode` still
# shares a real value name, and PLANT P3 (below) still fails as it must. It is NOT a
# suppression — nothing is added to a reviewed-exception list, and the arm still runs
# over every subject.
#
# THE RESIDUAL, NAMED (CHECK-DEBT D2.20): this remains name-identity, not dataflow. A
# grant laundered through a rename (`m = self._requested_mode; ... granted_mode=m`)
# shares the name `m` and IS caught; one laundered through an unrelated-looking
# attribute is not. Arm B1's three-way behavioural drive is the compensating control,
# because it executes the observer rather than reading it.
BINDING_NAMES: frozenset[str] = frozenset({"self", "cls"})


def _requested_names(tree: ast.Module) -> set[str]:
    """Names handed to the vendor's mode-REQUEST call. Binding names excluded —
    see BINDING_NAMES."""
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
    return out - BINDING_NAMES


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
    return out - BINDING_NAMES


def _arm_b23(
    home: Path, subject: Subject, sentinel: int
) -> tuple[list[tuple[str, str]], list[str]]:
    """(defects, measured-notes) for the two structural sub-arms.

    EVERY BRANCH EMITS A NOTE, INCLUDING THE BRANCH THAT MEASURED NOTHING. Added
    ARC 023 (S2), and it is D3.15's lesson applied one gate over rather than
    remembered: both of these arms were SILENT when they had no subject, so
    "measured and found nothing wrong" and "found nothing to measure" produced
    the same output — which is exactly how arm 4 of the sibling gate sat vacuous
    for two arcs while two other rows leaned on it. On the real adapter today B2
    is vacuous by construction (`marketDataType` is never read by name; the
    grant arrives as a callback parameter) and B3's granted-side name set is
    EMPTY (D2.20), and until now the run said neither."""
    tree = _parse(home / subject.rel)
    if tree is None:
        return [(subject.rel, "unparseable")], []
    defects: list[tuple[str, str]] = []
    notes: list[str] = []
    reads = _mode_field_reads(tree)
    writes = _sentinel_writes(tree, sentinel)
    requested, granted = _requested_names(tree), _granted_names(tree)
    if not reads:
        notes.append(
            f"B2 {subject.rel}: VACUOUS — {VENDOR_MODE_FIELD} never read by name, so "
            "this arm has no subject here (the lifecycle's re-subscribe leg is what "
            "covers the property behaviourally)"
        )
    if not granted:
        notes.append(
            f"B3 {subject.rel}: VACUOUS on the granted side — no `granted_mode=` "
            "keyword anywhere, so the intersection is empty whatever the request "
            "names are (D2.20)"
        )
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
    shared = requested & granted
    if requested:
        notes.append(f"B3 {subject.rel}: request-call names {sorted(requested)}")
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
def _returns_mode(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if node.returns is None:
        return False
    return ast.unparse(node.returns).strip("\"'").split(".")[-1] == MODE_ENUM


def _class_node(home: Path, subject: Subject) -> ast.ClassDef | None:
    tree = _parse(home / subject.rel)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == subject.cls:
            return node
    return None


def _port_mode_verb(home: Path, roster: Roster) -> str | None:
    """THE OBSERVER, NAMED BY THE SETTLED ROSTER AND NOT BY AN ANNOTATION.

    D3.16, and this function is the whole of the rebuild's premise. What stood
    here was `_observers()`, which collected every callable in a SUBJECT MODULE
    whose return annotation was the mode enum. Its docstring said "discovery by
    annotation, not by name … `debug.md` §7.4's requirement applied to a scope",
    and the argument is not wrong in general — it is wrong about WHERE the
    contract lives. The contract is the PORT. `resolve_granted_mode` is a
    module-level pure helper in `broker_datafeed_ibkr.py` carrying exactly that
    annotation, so annotation-discovery collected it beside the adapter's own
    accessor, drove it happily three ways, and the resulting leg count masked
    the three `AttributeError`s the real accessor raised. Two arcs of PASS over
    a method the gate never executed.

    So the observer is now the roster verb the PORT PROTOCOL declares as
    returning the mode enum. It is derived twice over — membership from
    `DATAFEED_PORT_VERBS`, type from the Protocol's own signature — and a
    helper that is not on the port cannot be mistaken for it however it is
    annotated."""
    tree = _parse(home / roster.rel)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not _is_protocol(node):
            continue
        for body in node.body:
            if not isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if body.name in roster.verbs and _returns_mode(body):
                return body.name
    return None


def _resolvers(home: Path, subject: Subject) -> list[str]:
    """MODULE-LEVEL pure mappings from a vendor integer to the seam's enum.

    Kept, demoted, and RENAMED from what it was. This is the set annotation
    discovery used to return, minus the methods; driving it is worth something
    (a mapping that collapses 0 onto 1 is a real defect and this is the cheapest
    place to catch it) and it is worth EXACTLY that. It contributes ZERO
    lifecycle legs, so it can never again stand in for the accessor — which is
    the mechanical form of D3.16's lesson, as opposed to the remembered form."""
    tree = _parse(home / subject.rel)
    if tree is None:
        return []
    out = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _returns_mode(node)
        and len(node.args.args) == 1
    ]
    return sorted(set(out))


class GrantWriter(NamedTuple):
    """A method through which a VENDOR grant reaches the subject's mode state."""

    name: str
    params: tuple[str, ...]
    int_params: tuple[str, ...]


def _grant_writers(home: Path, subject: Subject, mode_verb: str) -> list[GrantWriter]:
    """The subject's grant-DELIVERY entry points, derived, not named.

    A grant writer is a method that (a) assigns to an attribute spelled the same
    as the port's mode verb — the state the verb reports — and (b) takes a
    parameter annotated `int`, which is the vendor's wire value arriving from
    outside. Both halves are needed and neither is a spelling this file invents:
    (a) comes from the roster via `_port_mode_verb`, (b) is what makes the
    method a DELIVERY rather than a reset.

    On the real adapter this selects `_on_ib_market_data_type` and rejects both
    `subscribe` and `disconnect`, which also write the field but write the
    SENTINEL and take no vendor value. That distinction is the property: only a
    venue callback may report a mode."""
    node = _class_node(home, subject)
    if node is None:
        return []
    out: list[GrantWriter] = []
    for fn in ast.walk(node):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        writes = any(
            isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == mode_verb for t in n.targets
            )
            for n in ast.walk(fn)
        )
        if not writes:
            continue
        args = fn.args.args[1:]  # drop the binding name
        ints = tuple(
            a.arg
            for a in args
            if a.annotation is not None
            and ast.unparse(a.annotation).split("[")[0].split(".")[-1] == "int"
        )
        if not ints:
            continue
        out.append(GrantWriter(fn.name, tuple(a.arg for a in args), ints))
    return out


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


class Drive(NamedTuple):
    """What the behavioural probe came back with."""

    defects: list[tuple[str, str]]
    notes: list[str]
    driven: list[str]
    """Subjects whose FULL lifecycle ran. Only these can carry a PASS."""
    broken: list[str]
    """Subjects the gate could not drive. CANNOT_MEASURE, never PASS."""
    refusing: list[str]
    """Subjects that raised `NotImplementedError`. A NOTE — see `_drive_legs`."""
    traced: dict[str, list[str]]
    """subject -> the functions of its own module that actually EXECUTED."""


def _behavioural(
    home: Path,
    subjects: list[Subject],
    members: dict[str, int],
    ctx: tuple[str, tuple[str, ...]],
) -> Drive:
    """Arms B1 (lifecycle), B0 (mapping) and C, one probe for the subject set."""
    mode_verb, events = ctx
    payload = {
        "op": "drive",
        "home": str(home),
        "subjects": [
            {
                "rel": s.rel,
                "cls": s.cls,
                "mode_verb": mode_verb,
                "resolvers": _resolvers(home, s),
                "grant_writers": [list(g) for g in _grant_writers(home, s, mode_verb)],
            }
            for s in subjects
        ],
        "three_way": [list(t) for t in THREE_WAY],
        "members": members,
        "mode_enum": MODE_ENUM,
        "sentinel": SENTINEL_MEMBER,
        "symbols": list(PROBE_SYMBOLS),
        "events": list(events),
    }
    res = _drive(home, payload)
    if "error" in res:
        return Drive(
            [],
            [f"B1/C: probe unavailable — {res['error']}"],
            [],
            ["probe unavailable"],
            [],
            {},
        )
    return Drive(
        defects=[(d["site"], d["why"]) for d in res.get("defects", [])],
        notes=list(res.get("notes", [])),
        driven=list(res.get("driven", [])),
        broken=list(res.get("broken", [])),
        refusing=list(res.get("refusing", [])),
        traced={k: list(v) for k, v in res.get("traced", {}).items()},
    )


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


def _non_vacuity(drive: Drive, subjects: list[Subject], mode_verb: str) -> str:
    """'' if the gate DEMONSTRATED it drove the port's mode verb on a real
    subject; otherwise the reason it did not.

    THIS IS D3.16 IN ONE FUNCTION, AND IT IS ASSERTED BEFORE ANY VERDICT IS
    BELIEVED. `nix_check_contract.md` §5.1 step 2 and doctrine C.3 both require
    non-vacuity to be proven before a plant; the two arcs this row covers show
    why it has to be proven on EVERY RUN instead. The old gate could not have
    answered "did you execute `IBKRBrokerDatafeed.granted_mode`?" — it had no
    representation of the question. The probe now traces the lifecycle with
    `sys.settrace` and reports which functions of the SUBJECT'S OWN MODULE
    executed, and this asserts the mode verb is among them. A gate that cannot
    show it drove its subject reports CANNOT_MEASURE and says which subject."""
    if not drive.driven:
        return (
            f"no subject completed the {mode_verb} lifecycle — "
            f"{len(subjects)} subject(s), {len(drive.refusing)} declared refusal(s) "
            f"{drive.refusing}, {len(drive.broken)} undrivable {drive.broken}"
        )
    missing = [s for s in drive.driven if mode_verb not in drive.traced.get(s, [])]
    if missing:
        return (
            f"the lifecycle ran but {mode_verb} never appeared in the execution "
            f"trace of {missing} — the gate did not drive the method it reports on "
            "(D3.16, and this is the assertion that makes that sentence checkable)"
        )
    return ""


def _verdict(
    defects: list[tuple[str, str]],
    evidence: str,
    drive: Drive,
    ctx: tuple[list[Subject], str],
) -> CheckResult:
    """FAIL dominates; then non-vacuity; then no subject may be undrivable."""
    subjects, mode_verb = ctx
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(s for s, _ in defects),
            evidence=evidence,
            detail="; ".join(f"{s}: {w}" for s, w in defects),
        )
    vacuous = _non_vacuity(drive, subjects, mode_verb)
    if vacuous:
        return _cannot(vacuous, evidence=evidence)
    # D3.16, ARC 022/023. An undrivable subject is a cannot-measure about the
    # INSTRUMENT — `nix_check_contract.md` §5.3 — and never a pass about the code,
    # however well another subject drove. A declared `NotImplementedError` is not
    # in this set: see `_drive_legs`.
    if drive.broken:
        return _cannot(
            "could not DRIVE a subject — "
            + "; ".join(drive.broken)
            + ". Another subject satisfied the lifecycle, which is the shape that "
            "made this a PASS until ARC 022; a leg that raised is not a leg that "
            "passed (D3.16)",
            evidence=evidence,
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def _subjects_defect(roster_rel: str, subs: set[str]) -> list[tuple[str, str]]:
    """`SUBJECTS` must equal the scope this run actually derived.

    The derived set is the roster-declaring module — arm A1 reads
    `MarketDataMode` out of it and reddens if the sentinel is aliased away, so
    it is measured, not merely opened — plus every module holding a subject
    class. Divergence in either direction is a defect and they are different
    defects: an underclaim credits `check_artifact_gate_coverage` with nothing
    for a file this gate drives; an overclaim credits it with coverage over a
    file this gate no longer reaches.
    """
    declared, derived = set(SUBJECTS), {roster_rel} | subs
    site = "checks/check_datafeed_granted_mode.py:SUBJECTS"
    out: list[tuple[str, str]] = []
    undeclared = sorted(derived - declared)
    if undeclared:
        out.append(
            (
                site,
                (
                    f"the derived scope contains {undeclared}, which SUBJECTS "
                    f"does not declare — check_artifact_gate_coverage would "
                    f"report these as uncovered while this gate drives them"
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


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Verdict. PASS requires the port's mode verb to have been DRIVEN through a
    full subscribe/grant/re-subscribe lifecycle on a real subject, and the
    execution trace to prove it."""
    home = ctx.nix_home
    roster = _roster(home)
    if roster is None:
        return _cannot(f"no module under {SCAN_ROOTS} declares {ROSTER_CONST}")
    members = _enum_members(home, roster)
    if not members:
        return _cannot(f"{roster.rel} declares {ROSTER_CONST} but no {MODE_ENUM} enum")
    mode_verb = _port_mode_verb(home, roster)
    if mode_verb is None:
        return _cannot(
            f"no verb on {ROSTER_CONST} is declared by a Protocol in {roster.rel} as "
            f"returning {MODE_ENUM} — the port does not oblige anyone to report the "
            "granted mode, so this gate has no contract to bind to (§7.12 cond. 3)"
        )

    defects, notes = _representational(home, roster, members)
    subjects, advisories = _scope(home, roster)
    notes.append(
        f"scope: roster {roster.rel} {roster.verbs}; mode verb {mode_verb!r}; "
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
    drive = _behavioural(
        home, subjects, members, (mode_verb, _datafeed_events(home, roster))
    )
    defects += (
        static_defects
        + drive.defects
        + _subjects_defect(roster.rel, {s.rel for s in subjects})
    )
    notes += static_notes + drive.notes
    notes.append(
        "NON-VACUITY: driven "
        + str(drive.driven)
        + "; refusing "
        + str(drive.refusing)
        + "; "
        + "; ".join(
            f"{s} executed {len(fns)} function(s) of its own module including "
            f"{mode_verb!r}: {mode_verb in fns}"
            for s, fns in sorted(drive.traced.items())
        )
    )
    return _verdict(defects, "; ".join(notes), drive, (subjects, mode_verb))


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
) -> tuple[list, list, int, dict[int, str], list[str]]:
    """ARM B0 — run one MODULE-LEVEL MAPPING over all three legs.

    Was arm B1 until ARC 023 stage 2, and the demotion is the point. This drives
    a pure vendor-int -> enum function; it is real code and a collapsed mapping
    is a real defect, so it keeps its defects. What it no longer does is
    contribute a LEG, because a leg is now a step of the lifecycle in
    `_run_lifecycle` and nothing else. See `_port_mode_verb` for why: this arm's
    three green legs are precisely what masked three `AttributeError`s on the
    accessor for two arcs (D3.16).

    (defects, notes, legs, seen, broken).

    D3.16, ARC 022. A LEG THAT RAISED IS NOT A LEG THAT PASSED, and until this arc
    the two were indistinguishable in the verdict: every exception became a `note`
    and `continue`d, so an observer the gate could not execute AT ALL contributed
    nothing and the run still reported PASS on another observer's legs. ARC 022
    measured that live — all three legs against `IBKRBrokerDatafeed.granted_mode`
    raised `AttributeError: 'int' object has no attribute '_symbols'` (the port
    split put a symbol parameter in front, so the mode integer landed in `self`),
    and this gate printed `pass`. A gate that reports green about a subject it
    never drove is the vacuity `debug.md` §7.12 exists to catch.

    THE DISTINCTION IS DELIBERATE AND IS NOT A LOOPHOLE:
      - `NotImplementedError` is a DECLARED REFUSAL. `ibkr_mapping.IBKRDatafeedAdapter`
        is a refusing skeleton whose whole contract is to raise it, and reddening a
        subject for honouring its own declared contract is `VERIFY-AND-CHECKS.md`
        doctrine B.4's forbidden direction. Recorded as a note, as before.
      - ANY OTHER exception means THE GATE FAILED TO DRIVE ITS SUBJECT. That is a
        cannot-measure about the instrument, not a pass about the code, and it is
        returned as `broken` so the verdict can say so.

    This is strictly-stricter by construction: no input that failed before can pass
    now, and the only verdicts that change are ones that were PASS while measuring
    nothing."""
    defects: list[dict[str, str]] = []
    notes: list[str] = []
    legs = 0
    seen: dict[int, str] = {}
    broken: list[str] = []
    for value, want, forbid in three_way:
        try:
            got = fn(value)
        except NotImplementedError as exc:
            notes.append(
                f"B1 {site_prefix}({value}): declared refusal — "
                f"{type(exc).__name__}: {exc}"
            )
            continue
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            notes.append(
                f"B1 {site_prefix}({value}): raised {type(exc).__name__}: {exc}"
            )
            broken.append(f"{site_prefix}({value}): {type(exc).__name__}: {exc}")
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
    return defects, notes, legs, seen, broken


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


def _probe_mappings(mod: Any, spec: dict[str, Any], payload: dict[str, Any]) -> tuple:
    """ARM B0 over every module-level mapping in the subject module."""
    defects: list[dict[str, str]] = []
    notes: list[str] = []
    broken: list[str] = []
    for name in spec["resolvers"]:
        fn = getattr(mod, name, None)
        prefix = f"{spec['rel']}:{name}"
        if not callable(fn):
            notes.append(f"B0 {prefix}: not resolvable")
            continue
        got_d, got_n, _, seen, got_b = _drive_legs(fn, prefix, payload["three_way"])
        defects += got_d + _discrimination(prefix, seen)
        notes += got_n
        broken += got_b
    return defects, notes, broken


# --------------------------------------------------------------------------
# ARM B1 — THE LIFECYCLE DRIVE. The rebuild, and the arc's headline.
# --------------------------------------------------------------------------
class _Absorber:
    """A vendor client that absorbs every wire call and supplies NO VALUE.

    `debug.md` §7.12 instance 5 is the polite fake whose missing `multiplier`
    made two different units numerically identical, and it is the reason a
    stand-in for a vendor SDK is normally refused here (NAMED GAP 1). This one
    is admissible for a stated reason: it is a SINK, not a SOURCE. Every value
    this arm asserts on comes back out of the subject's own state through the
    port's own mode verb; the absorber's entire contribution is to let
    `connect()` and `subscribe()` reach their ends without a socket. If it ever
    started returning meaningful values, that argument would stop holding — so
    it returns only more of itself, which is meaningful nowhere."""

    def __getattr__(self, name: str) -> Any:
        return _Absorber()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return _Absorber()


def _ctor_slots(cls: type) -> tuple[list[str], list[str]]:
    """(required parameters, OPTIONAL parameters defaulting to None).

    The constructor is READ rather than typed. A vendor-neutral gate cannot know
    the venue-client keyword is spelled `ib` — `debug.md` §7.4 says a gate that
    typed it goes stale the first time a second venue lands — so the candidate
    slots are every optional parameter whose default is `None`, and WHICH of
    them is the vendor is settled by driving, in `_lifecycle_result`.

    Defaulting to `None` is NOT sufficient on its own and this was measured, not
    foreseen: `IBKRBrokerDatafeed.poll_lag_record` also defaults to `None` (the
    poll channel is UNOBSERVED on this system), and filling it with an absorber
    makes `_require_channel` refuse the construction — correctly, and loudly, in
    AMENDMENT 6's own words."""
    import inspect  # pylint: disable=import-outside-toplevel

    required: list[str] = []
    optional: list[str] = []
    sig = inspect.signature(cls)  # the CLASS, not the instance's __init__ (mypy misc)
    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if param.default is inspect.Parameter.empty:
            required.append(name)
        elif param.default is None:
            optional.append(name)
    return required, optional


def _build(mod: Any, spec: dict[str, Any], events: tuple[str, ...], slots: list[str]):
    """One construction: sink doubles into the required slots, absorbers into
    `slots`, and every other default left exactly as the adapter declared it."""
    cls = getattr(mod, spec["cls"])
    required, _ = _ctor_slots(cls)
    return cls(
        *[_sink_double(events) for _ in required],
        **{name: _Absorber() for name in slots},
    )


async def _maybe_await(value: Any) -> Any:
    import inspect  # pylint: disable=import-outside-toplevel

    return await value if inspect.isawaitable(value) else value


class _Reader:  # pylint: disable=too-few-public-methods
    """The port's mode verb, callable with or without a symbol.

    A class and not a closure because the arity question — does this verb take a
    symbol? — is answered ONCE off the signature and then reused at eight call
    sites; re-deriving it per call would be a second place for it to be wrong."""

    def __init__(self, inst: Any, mode_verb: str):
        import inspect  # pylint: disable=import-outside-toplevel

        self.fn = getattr(inst, mode_verb)
        self.per_symbol = any(
            p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            for p in inspect.signature(self.fn).parameters.values()
        )

    def __call__(self, symbol: Any = None) -> str:
        got = self.fn(symbol) if (symbol is not None and self.per_symbol) else self.fn()
        return getattr(got, "name", repr(got))


def _grant(inst: Any, writer: list, symbol: Any, value: int) -> Any:
    """Deliver a VENDOR grant through the subject's own callback."""
    name, params, int_params = writer[0], writer[1], set(writer[2])
    fn = getattr(inst, name)
    return fn(*[value if p in int_params else symbol for p in params])


class _Lifecycle:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """One subject, driven from construction through re-subscription.

    R0902/R0903 refused with a reason. The attribute count IS the sequence's
    state — the instance, the reader, the writer, the defects, the notes, the
    values seen and the leg count — and every one of them is read by more than
    one step. Splitting it to satisfy a ceiling would put the lifecycle's state
    in one object and its steps in another, which is the shape that lets a step
    be added without the assertion that goes with it. One public entry point
    (`run`) is the design: a caller may drive the whole sequence or none of it,
    never half."""

    def __init__(self, inst: Any, spec: dict[str, Any], payload: dict[str, Any]):
        self.inst = inst
        self.spec = spec
        self.payload = payload
        self.site = f"{spec['rel']}:{spec['cls']}"
        self.read = _Reader(inst, spec["mode_verb"])
        writers = spec["grant_writers"]
        self.writer = writers[0] if writers else None
        self.sentinel = payload["sentinel"]
        self.defects: list[dict[str, str]] = []
        self.notes: list[str] = []
        self.seen: dict[int, str] = {}
        self.legs = 0

    def _fail(self, where: str, why: str) -> None:
        self.defects.append({"site": f"{self.site}.{where}", "why": why})

    def _expect(self, where: str, got: str, want: str, why: str) -> None:
        self.notes.append(f"B1 {self.site}.{where} -> {got}")
        if got != want:
            self._fail(where, f"{why} (reported {got}, expected {want})")

    async def _verb(self, name: str, *args: Any) -> Any:
        return await _maybe_await(getattr(self.inst, name)(*args))

    async def run(self) -> None:
        """The sequence. Every step is a statement about the GRANT and none of
        them is a statement about the request."""
        sym, other = self.payload["symbols"]
        # STEP 1 — CONSTRUCTED, NEVER CONNECTED. Nothing has been granted, so the
        # only honest answer is the sentinel. Reporting a mode here is the absence
        # principle's exact violation.
        self._expect(
            f"{self.spec['mode_verb']}()@no-session",
            self.read(),
            self.sentinel,
            "never connected, yet reports a granted mode — a grant that did not happen",
        )
        await self._verb("connect")
        await self._verb("subscribe", sym)
        # STEP 2 — SUBSCRIBED, NO GRANT CALLBACK. This is leg 0 of the three-way,
        # driven through the real absence rather than through a synthetic value.
        got = self.read(sym)
        self.seen[0] = got
        self.legs += 1
        self._expect(
            f"{self.spec['mode_verb']}({sym})@subscribed-ungranted",
            got,
            self.sentinel,
            "subscribed with no grant callback received, yet reports a mode",
        )
        self._expect(
            f"{self.spec['mode_verb']}()@subscribed-ungranted",
            self.read(),
            self.sentinel,
            "the adapter-wide answer names a mode while nothing has been granted "
            "— that the request was made is not evidence of what was granted",
        )
        await self._granted_legs(sym)
        await self._divergence(sym, other)

    async def _granted_legs(self, sym: Any) -> None:
        """The venue's grant, three ways, each followed by the re-subscription
        assertion: A GRANT BELONGS TO A SUBSCRIPTION AND IS NOT INHERITED."""
        if self.writer is None:
            self.notes.append(
                f"B1 {self.site}: no grant-delivery entry point — no method writes "
                f"{self.spec['mode_verb']!r} from an int parameter, so the venue's "
                "grant cannot be driven"
            )
            return
        for value, want, forbid in self.payload["three_way"]:
            if value == self.payload["members"][self.sentinel]:
                continue  # driven as STEP 2, from the real absence
            _grant(self.inst, self.writer, sym, value)
            got = self.read(sym)
            self.seen[value] = got
            self.legs += 1
            where = f"{self.spec['mode_verb']}({sym})@granted-{value}"
            self._expect(where, got, want, "the venue's grant is misreported")
            if got == forbid:
                self._fail(where, f"reported {forbid} — the defect")
            await self._verb("subscribe", sym)
            self._expect(
                f"{self.spec['mode_verb']}({sym})@re-subscribed-after-{value}",
                self.read(sym),
                self.sentinel,
                "a RE-SUBSCRIPTION inherited the previous subscription's grant — "
                "the new subscription has had no grant callback, and a grant that "
                "outlives the subscription it was made to is a grant that did not "
                "happen",
            )
        self.defects += [
            {"site": self.site, "why": d["why"]}
            for d in _discrimination(self.site, self.seen)
        ]

    async def _divergence(self, sym: Any, other: Any) -> None:
        """TWO SUBSCRIPTIONS, TWO DIFFERENT GRANTS. A single mode reported for a
        set that does not share one is a fabricated value — the same absence
        principle as STEP 1, at the adapter-wide arity."""
        if self.writer is None:
            return
        if not self.read.per_symbol:
            self.notes.append(
                f"B1 {self.site}: mode verb takes no symbol — divergence leg skipped"
            )
            return
        legs = [v for v, _, _ in self.payload["three_way"]]
        first, second = legs[1], legs[2]
        _grant(self.inst, self.writer, sym, first)
        await self._verb("subscribe", other)
        _grant(self.inst, self.writer, other, second)
        self._expect(
            f"{self.spec['mode_verb']}()@divergent-grants",
            self.read(),
            self.sentinel,
            f"two subscriptions granted {first} and {second} and the adapter-wide "
            "answer names one of them — a single mode reported for a set that does "
            "not share one is a fabricated value",
        )


class Attempt(NamedTuple):
    """One construction of the subject, driven, with its own execution trace."""

    slots: list[str]
    defects: list
    notes: list
    outcome: str
    legs: int
    traced: list[str]


def _attempt(
    mod: Any, spec: dict[str, Any], payload: dict[str, Any], slots: list[str]
) -> Attempt:
    """Construct with `slots` filled by absorbers and run the whole lifecycle.

    THE TRACE IS TAKEN AROUND THIS ATTEMPT AND NOTHING ELSE, so the non-vacuity
    assertion cannot be satisfied by a construction that failed, by arm C, or by
    the mapping arm. Only the attempt whose verdict is reported carries a trace.
    """
    site = f"{spec['rel']}:{spec['cls']}"
    try:
        inst = _build(mod, spec, tuple(payload["events"]), slots)
    except NotImplementedError as exc:
        return Attempt(
            slots, [], [f"B1 {site}: declared refusal — {exc}"], "refusing", 0, []
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return Attempt(
            slots,
            [],
            [f"B1 {site} {slots}: not constructible — {exc!r}"],
            f"not constructible with {slots}",
            0,
            [],
        )
    cycle = _Lifecycle(inst, spec, payload)
    cycle.notes.append(f"B1 {site}: constructed, absorbers in {slots}")

    def thunk() -> str:
        try:
            _sync_run(cycle.run())
        except NotImplementedError as exc:
            cycle.notes.append(f"B1 {site}: declared refusal — {exc}")
            return "refusing"
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            cycle.notes.append(f"B1 {site}: raised {type(exc).__name__}: {exc}")
            return f"{type(exc).__name__}: {exc}"
        if cycle.legs < len(payload["three_way"]):
            return f"only {cycle.legs} of {len(payload['three_way'])} legs ran"
        return "driven"

    outcome, traced = _traced(mod, thunk)
    return Attempt(slots, cycle.defects, cycle.notes, outcome, cycle.legs, traced)


def _lifecycle_result(
    mod: Any, spec: dict[str, Any], payload: dict[str, Any]
) -> Attempt:
    """The subject's best attempt. outcome ∈ driven / refusing / <why not>.

    THE VENDOR SLOT IS FOUND BY DRIVING, NOT BY NAMING. Each optional
    `None`-defaulted constructor keyword is tried alone, then all of them
    together, then none at all, and the first attempt that completes the
    lifecycle wins. That is a behavioural derivation of a fact this file must
    not state — which venue keyword holds the client — and it is why nothing
    here knows the word `ib`.

    A `NotImplementedError` short-circuits the search immediately. A refusing
    skeleton has no vendor slot to find, and continuing to hunt for one would
    turn its declared contract into a search failure, which is doctrine B.4's
    forbidden direction dressed as diligence."""
    cls = getattr(mod, spec["cls"], None)
    if not isinstance(cls, type):
        return Attempt(
            [],
            [],
            [f"B1 {spec['rel']}: {spec['cls']} not resolvable"],
            "class not resolvable",
            0,
            [],
        )
    _, optional = _ctor_slots(cls)
    candidates: list[list[str]] = [[s] for s in optional] + [list(optional), []]
    best: Attempt | None = None
    for slots in candidates:
        got = _attempt(mod, spec, payload, slots)
        if got.outcome in ("driven", "refusing"):
            return got
        if best is None or got.legs > best.legs:
            best = got
    return best if best is not None else Attempt([], [], [], "no candidate", 0, [])


def _sync_run(coro: Any) -> Any:
    import asyncio  # pylint: disable=import-outside-toplevel

    return asyncio.run(coro)


def _traced(mod: Any, thunk: Any) -> tuple[Any, list[str]]:
    """Run `thunk`, recording which functions OF `mod`'s OWN FILE executed.

    THE NON-VACUITY INSTRUMENT, AND IT IS PERMANENT (D3.16). Its whole job is to
    make "did this gate execute its subject?" a question with a machine answer
    on every run, instead of a thing a docstring asserts. Filtering by the
    subject's own filename is what keeps it from being satisfied by the probe's
    own frames."""
    import os  # pylint: disable=import-outside-toplevel

    want = os.path.realpath(getattr(mod, "__file__", "") or "")
    seen: set[str] = set()

    def tracer(frame: Any, event: str, _arg: Any) -> Any:
        # Returns None IMPLICITLY, and that is the contract rather than an
        # omission: a global trace function returning None tells CPython not to
        # trace that frame's lines, which is what keeps this affordable.
        if event == "call" and os.path.realpath(frame.f_code.co_filename) == want:
            seen.add(frame.f_code.co_name)

    sys.settrace(tracer)
    try:
        return thunk(), sorted(seen)
    finally:
        sys.settrace(None)


def _probe_subject(spec: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Every behavioural arm over one subject, with the trace beside them."""
    import importlib  # pylint: disable=import-outside-toplevel

    site = f"{spec['rel']}:{spec['cls']}"
    try:
        mod = importlib.import_module(Path(spec["rel"]).stem)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return {
            "defects": [],
            "notes": [
                f"B1 {spec['rel']}: not importable — {type(exc).__name__}: {exc}"
            ],
            "broken": [f"{spec['rel']}: not importable"],
            "refusing": [],
            "driven": [],
            "traced": {},
        }
    map_d, map_n, map_b = _probe_mappings(mod, spec, payload)
    life = _lifecycle_result(mod, spec, payload)
    off_d, off_n = _probe_offline(spec, tuple(payload["events"]))
    return {
        "defects": map_d + life.defects + off_d,
        "notes": map_n + life.notes + off_n,
        "broken": map_b
        + (
            []
            if life.outcome in ("driven", "refusing")
            else [f"{site}: {life.outcome}"]
        ),
        "refusing": [site] if life.outcome == "refusing" else [],
        "driven": [site] if life.outcome == "driven" else [],
        "traced": {site: life.traced},
    }


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
    out: dict[str, Any] = {
        "defects": [],
        "notes": [],
        "broken": [],
        "refusing": [],
        "driven": [],
        "traced": {},
    }
    for spec in payload["subjects"]:
        got = _probe_subject(spec, payload)
        for key in ("defects", "notes", "broken", "refusing", "driven"):
            out[key] += got[key]
        out["traced"].update(got["traced"])
    print(json.dumps(out))
    return 0


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    # Both of these predate the flag surface, neither is an actuation verb, and
    # both are intercepted BEFORE `parse_actuation` because an argparse surface
    # that did not know them would reject them. `--drive` is this gate's own
    # probe re-entry (the subprocess that owns every behavioural arm);
    # `--print-scope-count` is one source of `derived_claims.json`'s
    # `datafeed_scope_files`, the cross-check that keeps this gate's scope
    # derivation and `check_datafeed_bar_seal`'s from drifting apart. Losing
    # either to the retrofit would blind a live instrument silently.
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

    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
