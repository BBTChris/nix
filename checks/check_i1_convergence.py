#!/usr/bin/env python3
# C0302: over pylint's 1000-line default. The overage is the DERIVATION, the
# per-path driver table's reasons and the §7.12 block — check contract v2 rule 11
# makes the reason sentences the assertion rather than decoration, and §4.2
# requires a check be ONE independently runnable file.
# pylint: disable=too-many-lines
"""ARC 058 / I1 ARC D — THE CONVERGENCE GATE: the daemon's required-path set is
COMPLETE, and every member of it is DAEMON-INVOKED AND DRIVEN.

This gate's PASS **is invariant I1's discharge.** Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md` unless another document is named on the
same line. `D3.<n>` cites `docs/CHECK-DEBT.md`; `CHECK-A<n>` cites
`docs/CHECK-CONTRACT-AMENDMENTS.md`.

THE PROPERTY, AND WHY NOTHING IN THIS TREE OWNED IT
------------------------------------------------------------------------------
I1 is not *a path works*. Every path in this tree has a gate that proves its
CORRECTNESS, and each of those gates is scrupulously scoped to ONE property
(`nix_check_contract.md` §5.5). The census this gate was opened against, run at
ARC 058 / stage 5 and recorded here so a later reader can re-run it rather than
trust it:

* `check_limiter_daemon_dispatch` — the daemon dispatches §2A's fill / cancel /
  reject and resolves a pending timeout, CORRECTLY and exactly once.
* `check_stop_maintenance` — §4:187-196's trail and the `SYNTHETIC_STOP`
  breach->flatten, CORRECTLY.
* `check_uncertainty_flatten` — §14's four uncertainty producers, CORRECTLY, and
  the completeness of THAT ONE FAMILY (its ARM 4 derives the condition set).
* `check_flatten` — the executor as a LIBRARY. It spawns no daemon.
* `check_go_timeout` — §4:210-212's breaker. `check_limiter_loop_alive` — the
  loop. `check_two_phase_entry` — I4. `check_limiter_gate` — §3's ordering.

**Not one of them asks whether the SET is complete.** Each is blind, by design,
to a path that exists in a library and is reachable from no running process —
which is the state ARC 038 found FIVE Limiter invariants in, and which D3.178
named as *zero production callers*. A tree of green single-path gates and a
daemon that invokes half of them look identical from every one of those gates.
That pair — **the required-path set, and its completeness** — is what this gate
owns, so doctrine C.9 is respected rather than argued around.

THE REQUIRED SET IS DERIVED, AND A CHECKLIST WOULD BE THE DEFECT
------------------------------------------------------------------------------
A hand-written list of paths is complete on the day it is written and silently
incomplete on every day after. So the set is DERIVED, by shape, from FOUR
vocabularies the tree already keeps — never from prose and never from a list in
this file:

* **F1 `completion:<event>`** — one per member of `nixrisk/completions.py`'s
  `SPEC_EVENTS`, §2A:74-84's pushed broker events, read by AST. A member wired
  in `WIRED_EVENTS` must DISPATCH; one that is not must be REFUSED BY NAME as
  `unwired`. Both are daemon paths, and the second is the one an §2A event added
  later arrives on.
* **F2 `uncertainty:<condition>`** — one per member of `limiterd.py`'s
  `UncertaintyCondition` enum, §14's unprotectable-position conditions.
* **F3 `ingress:<name>`** — one per `<name>.before(...)` wrapper composed into
  `loop.attach(ingress=...)`. That composition IS §5:322's tick, and every
  wrapper in it is per-tick daemon work.
* **F4 `handler:<param>`** — one per collaborator parameter of
  `CompletionHandler.__init__`. Every one is a consumer a drained completion
  must actually reach.
* **F5 `sender:<name>`** — one per driver `ProtectiveSenders` fans §5:323's
  queue out to. These are the PROTECTIVE-EXIT sends, and §14 gives them zero
  wire dependency.

Add a fifth uncertainty condition, a sixth ingress wrapper, a ninth §2A event or
a third protective sender and `required` grows on the next run with no edit
here. **A required path this gate cannot classify — no driver, no observer — is
CANNOT_MEASURE NAMING IT, never PASS** (check contract rule 10: a safety
property proven while its subject is unavailable is not proven).

WHAT IS MEASURED
------------------------------------------------------------------------------
* **ARM 1 — THE REQUIRED SET, DERIVED.** The five vocabularies above, read out
  of the subject's own AST in this gate's interpreter without importing the
  subject (D3.224: one tree per interpreter — the measurement `check_uncertainty_
  flatten` paid for at ARC 057's re-measure).
* **ARM 2 — EVERY REQUIRED PATH IS DAEMON-INVOKED.** Proven structurally from
  `limiterd.py`'s AST: the path's owner is CONSTRUCTED in `main()` and REACHES
  §5:322's loop — through `attach(ingress=)`, `attach(handler=)` or
  `attach(sender_send=)`. **A path present in a library and absent from that
  composition is the library-not-daemon state I1 forbids**, and it FAILs naming
  the site. This is the arm PLANT A trips.
* **ARM 3 — EVERY REQUIRED PATH IS DRIVEN.** A real `limiterd` subprocess, real
  files through the real ingress, real commands — never a direct call into a
  handler, because ARC 038's deepest finding was that every Limiter invariant in
  this tree had been proven about a library a test constructed. Every verdict is
  read out of the daemon's OWN published record, and the counter for each path
  must MOVE. This is the arm PLANT C trips.
* **ARM 4 — COMPLETENESS.** `driven == required == invoked`, with both set
  differences named. A path that is required and not driven, or invoked and not
  required, is a finding in its own sentence.
* **ARM 5 — NON-VACUITY.** Nothing may have moved before this gate touched
  anything; the completions are proven to have entered from the ingress
  DIRECTORY (`last_source`); and the protective send is proven to have run on
  §5:323's thread and not the loop's.

§7.12 — THE STANDING QUESTION: HOW COULD THIS GATE BE GREEN AND I1 FALSE?
------------------------------------------------------------------------------
 1. **The set is whatever this file lists.** GUARDED: ARM 1 derives it from five
    vocabularies in the subject's own source and this file holds no copy of any
    of them. The DRIVER TABLE is keyed by the derived ids and is this gate's
    COVERAGE, never its authority — a key it cannot serve is CANNOT_MEASURE.
 2. **A path is "invoked" because the object exists.** GUARDED: ARM 2 requires
    the owner to be reachable from `loop.attach`'s three seams, which is the
    only place this process turns an object into per-tick work. Existence in the
    module is exactly the state ARM 2 exists to reject.
 3. **A path is "driven" because a handler was called.** GUARDED: every drive
    goes through the daemon's own ingress — a file in `inbox/`, `completions/`,
    `status/` or `onset/` — and this gate never imports the subject.
 4. **Something had already run before the gate acted.** GUARDED: ARM 5 reads
    every counter at boot and refuses if any is non-zero.
 5. **The daemon reported movement it did not cause.** GUARDED: the observations
    are the daemon's own published counters plus, where the question is *did a
    venue message happen*, the BROKER's own record on the far side of the call
    (check contract rule 2).
 6. **The gate imports its subject and measures a second copy of the tree.**
    GUARDED: nothing here imports `limiterd` or `nixrisk`. The derivation is
    AST-only and the drive is a subprocess. That is D3.224's *one tree per
    interpreter*, taken as a rule rather than as a caveat.
 7. **A green here means the daemon is operationally live.** NOT GUARDED, and
    it is not this gate's claim. The broker is a stub, there is no price capture
    feed (D3.473), onset is dispatched and not DETECTED (D3.470), the
    pending-timeout status directory has no producer (D3.468). Those are later
    modules by correct decomposition. What is proven is *the complete required
    machinery is invoked by a running process and driven end to end*, which is
    exactly and only what I1 says.
 8. **The exit code alone decided it.** GUARDED: every finding names its site
    and its reason (check contract rule 11), and the plants below were each
    confirmed by the SENTENCE they produced, not by the integer.

NON-CORRECTABLE, and the reason is `check_stop_maintenance`'s and
`check_uncertainty_flatten`'s. The subject is the daemon's own wiring. A gate
empowered to edit it until its own drive came back clean would be manufacturing
the very green that I1's discharge is supposed to certify.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess  # nosec B404
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
EXPECTED_S = 120.0
DEPENDS_ON: tuple[str, ...] = ()
#: SPAWNS `limiterd` subprocesses into fresh temp runtime directories. Declared
#: because check contract rule 12 has the declaration checked against what is
#: OBSERVED at runtime, not merely against itself.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:python",
    "subprocess:python3",
)
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the Limiter daemon's own dispatch and wiring set — the "
    "property this gate proves IS invariant I1. A repair that edited the wiring "
    "until this gate came back clean would be manufacturing the green that I1's "
    "discharge certifies"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/limiterd.py",
    # The two vocabularies the required set is DERIVED from that do not live in
    # `limiterd.py`. Declared as subjects for the reason `check_uncertainty_
    # flatten` declares its detectors: a plant in either must redden this gate,
    # and it cannot if the file is not its subject.
    "scripts/nixrisk/completions.py",
    # ARC 058's closing-fill handler — the path whose absence was the whole of
    # ARC D, and the one PLANT A reverts to library-only.
    "scripts/nixrisk/closing.py",
)

NAME = "check_i1_convergence"

LIMITERD_FILE: Final[str] = "scripts/limiterd.py"
COMPLETIONS_FILE: Final[str] = "scripts/nixrisk/completions.py"

# -- what this gate SENDS IN --------------------------------------------------
SYMBOL: Final[str] = "ES"
#: NEVER reserved, so it is absent from §3's published margin field set and the
#: origin write refuses a fill in it (§4:198). That is D3.372's condition.
OTHER: Final[str] = "NQ"
TICK_SIZE: Final[float] = 0.25
STOP_TICKS: Final[int] = 8
FILL_PRICE: Final[float] = 5000.0
#: Through the stop at `5000 - 8 * 0.25 = 4998.0`.
BREACH_PRICE: Final[float] = 4997.0
QTY: Final[int] = 2
MARGIN: Final[float] = 500.0
BALANCE: Final[float] = 250_000.0
STRATEGY: Final[str] = "check-i1-convergence"

DRIVE_TICK_S: Final[float] = 0.02
DRIVE_HEARTBEAT_S: Final[float] = 0.2
DRIVE_MAX_TICKS: Final[int] = 20_000
BOOT_TIMEOUT_S: Final[float] = 30.0
REPLY_TIMEOUT_S: Final[float] = 20.0
WATCH_HORIZON_S: Final[float] = 25.0
#: D3.469's bounded reconciliation window for THIS gate's drives. Passed on the
#: command line for the reason `--go-timeout` is overridable: the shipped value
#: is what an operator tuned, and a gate that waited it out would spend its
#: budget sleeping.
DRIVE_WINDOW_S: Final[float] = 1.0
#: §4:210-212's T for the drive that proves the Plane-1 booker runs on the tick.
#: Short for `DRIVE_WINDOW_S`'s reason. Harmless to every other path here: only
#: the `go` verb arms the timer, and no other drive issues one.
DRIVE_GO_TIMEOUT_S: Final[float] = 0.6

#: The `loop.attach` keyword each vocabulary's owner must reach §5:322 through.
#: Used only to say WHICH seam a missing path was missing from — the arm reads
#: the AST, never this mapping.
_SEAM_OF: Final[dict[str, str]] = {
    "completion": "handler",
    "handler": "handler",
    "ingress": "ingress",
    "sender": "sender_send",
    "uncertainty": "sender_send",
}


class Cannot(RuntimeError):
    """The subject could not be reached. CANNOT_MEASURE, never PASS (rule 10)."""


class Missed(RuntimeError):
    """A watched condition never arrived. Carries the last status it saw."""

    def __init__(self, what: str, status: dict[str, Any]) -> None:
        self.what = what
        self.status = status
        super().__init__(what)


# --------------------------------------------------------------------------
# ARM 1 — THE REQUIRED SET, DERIVED FROM THE SUBJECT'S OWN SOURCE
# --------------------------------------------------------------------------


def _tree(path: Path) -> ast.Module:
    """Parse one subject. A file this gate cannot read is CANNOT_MEASURE."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise Cannot(f"cannot parse {path}: {type(exc).__name__}: {exc}") from exc


# R0912 refused with a reason: the branches ARE the two module-level binding
# forms (`X: T = (...)` and `X = (...)`) times the two element forms (a string
# literal and a NAME resolved through the module's own constants). Collapsing
# any of them would make this derivation silently blind to a vocabulary spelled
# the other way, which is the failure this whole gate exists to refuse.
def _binding(node: ast.AST) -> tuple[str | None, ast.expr | None]:
    """`(name, value)` for `X: T = v` or `X = v`; `(None, None)` for anything else.

    Split out because THREE derivations here read a module-level binding and a
    fourth spelling of the same unpack is a fourth place for it to drift.
    """
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id, node.value
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        first = node.targets[0]
        if isinstance(first, ast.Name):
            return first.id, node.value
    return None, None


def _string_constants(tree: ast.Module) -> dict[str, str]:
    """Every module-level `NAME = "literal"`. What a vocabulary's members resolve to."""
    out: dict[str, str] = {}
    for node in tree.body:
        name, value = _binding(node)
        if name and isinstance(value, ast.Constant) and isinstance(value.value, str):
            out[name] = value.value
    return out


def _member(element: ast.expr, constants: dict[str, str], name: str) -> str:
    """ONE vocabulary member, as a string. Unresolvable is CANNOT_MEASURE."""
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return element.value
    if isinstance(element, ast.Name) and element.id in constants:
        return constants[element.id]
    raise Cannot(
        f"{name} carries an element this gate cannot resolve to a string "
        f"({ast.dump(element)[:120]}), so the vocabulary it declares cannot be "
        "derived"
    )


def _assigned_tuple(tree: ast.Module, name: str) -> tuple[str, ...]:
    """The string members of a module-level `NAME: ... = (a, b, ...)` binding.

    Members may be NAMES (`EVENT_FILL`) or literals; a name is resolved against
    the module's own string constants. That indirection is `completions.py`'s
    idiom and reading through it is what keeps this derivation honest: the
    tuple's MEMBERSHIP is the vocabulary, not its spelling.
    """
    constants = _string_constants(tree)
    for node in tree.body:
        bound, value = _binding(node)
        if bound != name or not isinstance(value, (ast.Tuple, ast.List)):
            continue
        return tuple(_member(element, constants, name) for element in value.elts)
    raise Cannot(f"no module-level {name} tuple found")


def _string_member(stmt: ast.stmt) -> str | None:
    """The `.value` of ONE `NAME = "literal"` enum member, or `None`."""
    bound, value = _binding(stmt)
    if bound and isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _enum_members(tree: ast.Module, name: str) -> tuple[str, ...]:
    """The `.value` of every member of a module-level `enum.Enum` class."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != name:
            continue
        out = tuple(
            value
            for value in (_string_member(stmt) for stmt in node.body)
            if value is not None
        )
        if not out:
            raise Cannot(f"enum {name} declares no string members")
        return out
    raise Cannot(f"no enum class named {name}")


def _attach_call(tree: ast.Module) -> ast.Call:
    """§5:322's ONE composition site: the `loop.attach(...)` call in `main`."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "attach"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "loop"
        ):
            return node
    raise Cannot(
        f"{LIMITERD_FILE}: no `loop.attach(...)` call — this process composes "
        "§5:322's tick nowhere, so there is no daemon loop for any path to be "
        "reachable from"
    )


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    """One keyword argument of a call, or None."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _before_chain(node: ast.expr | None) -> tuple[str, ...]:
    """Every `<name>.before(...)` receiver in the composed ingress, outermost first."""
    names: list[str] = []
    for inner in ast.walk(node) if node is not None else ():
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "before"
            and isinstance(inner.func.value, ast.Name)
        ):
            names.append(inner.func.value.id)
    if not names:
        raise Cannot(
            f"{LIMITERD_FILE}: `attach(ingress=...)` composes NO `.before()` "
            "wrapper, so this build does no per-tick work at all"
        )
    return tuple(dict.fromkeys(names))


def _declares_before(node: ast.ClassDef) -> bool:
    """Does this class declare `before(self, inner)` — §5:322's tick-wrapper shape?"""
    return any(
        isinstance(stmt, ast.FunctionDef)
        and stmt.name == "before"
        and len(stmt.args.args) == 2
        and stmt.args.args[0].arg == "self"
        for stmt in node.body
    )


def _constructed_from(tree: ast.Module, classes: set[str]) -> dict[str, str]:
    """Every local `main()` binds to a call of one of `classes`. name -> class."""
    owners: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "main":
            continue
        for stmt in ast.walk(node):
            bound, call = _binding(stmt)
            if (
                bound
                and isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in classes
            ):
                owners[bound] = call.func.id
    return owners


def _before_owners(tree: ast.Module) -> dict[str, str]:
    """Per-tick paths, DERIVED BY SHAPE: `main()`-constructed owners of `before`.

    **MEMBERSHIP MUST NOT COME FROM THE COMPOSITION IT IS COMPARED AGAINST**, and
    that was measured. This arm first derived the ingress set from
    `loop.attach(ingress=...)` itself; PLANT A2 then deleted `onset.before(...)`
    from that chain and the required set SHRANK from 23 to 22 — the un-wired
    path stopped being required by the act of un-wiring it, which is the
    library-not-daemon state making itself invisible. So the vocabulary is the
    SHAPE instead: a class that declares `def before(self, inner)` is a per-tick
    composer (that signature IS §5:322's tick-wrapper contract), and every local
    `main()` constructs from one is a required per-tick path whether or not the
    tick composes it. Un-wiring now leaves it REQUIRED and NOT INVOKED, which is
    exactly what it is.

    Returns `local name -> class name`.
    """
    composers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and _declares_before(node)
    }
    if not composers:
        raise Cannot(
            f"{LIMITERD_FILE}: no class declares `before(self, inner)`, so this "
            "build composes no per-tick work at all"
        )
    owners = _constructed_from(tree, composers)
    if not owners:
        raise Cannot(
            f"{LIMITERD_FILE}: `main()` constructs none of the per-tick "
            f"composers {sorted(composers)} — this process would run an empty tick"
        )
    return owners


def _init_params(tree: ast.Module, cls: str) -> tuple[str, ...]:
    """Every collaborator parameter of one class's `__init__`, `self` excluded."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != cls:
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
                args = [arg.arg for arg in stmt.args.args if arg.arg != "self"]
                args += [arg.arg for arg in stmt.args.kwonlyargs]
                if not args:
                    raise Cannot(f"{cls}.__init__ takes no collaborator")
                return tuple(args)
    raise Cannot(f"{LIMITERD_FILE}: no class {cls} with an __init__")


def _sender_drivers(tree: ast.Module) -> tuple[str, ...]:
    """Every driver §5:323's fan-out object hands a payload to.

    Read off `ProtectiveSenders.__init__`'s parameters for `_init_params`'s
    reason: the constructor is where this process declares which producers share
    the ONE sender queue, and a producer added to the fan-out without a
    constructor slot could not be handed anything.
    """
    return _init_params(tree, "ProtectiveSenders")


def _required(nix_home: Path) -> dict[str, str]:
    """ARM 1. The required-path set, id -> the vocabulary it was derived from."""
    limiterd = _tree(nix_home / LIMITERD_FILE)
    completions = _tree(nix_home / COMPLETIONS_FILE)
    required: dict[str, str] = {}
    for event in _assigned_tuple(completions, "SPEC_EVENTS"):
        required[f"completion:{event}"] = (
            f"{COMPLETIONS_FILE}: SPEC_EVENTS (§2A:74-84's pushed broker events)"
        )
    for condition in _enum_members(limiterd, "UncertaintyCondition"):
        required[f"uncertainty:{condition}"] = (
            f"{LIMITERD_FILE}: UncertaintyCondition (§14's unprotectable conditions)"
        )
    for wrapper, owner in _before_owners(limiterd).items():
        required[f"ingress:{wrapper}"] = (
            f"{LIMITERD_FILE}: {owner} declares `before(self, inner)` and "
            f"`main()` constructs it as {wrapper!r} — §5:322's per-tick contract"
        )
    for param in _init_params(limiterd, "CompletionHandler"):
        required[f"handler:{param}"] = (
            f"{LIMITERD_FILE}: CompletionHandler.__init__ collaborator — a "
            "consumer every drained §2A completion must reach"
        )
    for driver in _sender_drivers(limiterd):
        required[f"sender:{driver}"] = (
            f"{LIMITERD_FILE}: ProtectiveSenders.__init__ — §5:323's protective "
            "fan-out (§14: zero wire dependency)"
        )
    return required


# --------------------------------------------------------------------------
# ARM 2 — EVERY REQUIRED PATH IS DAEMON-INVOKED (library-not-daemon detector)
# --------------------------------------------------------------------------


def _main_locals(tree: ast.Module) -> set[str]:
    """Every name `main()` binds. The set of things this process CONSTRUCTS."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            names: set[str] = set()
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                    names.add(inner.id)
            return names
    raise Cannot(f"{LIMITERD_FILE}: no `main()` — this file boots no process")


def _completion_handler_binding(tree: ast.Module) -> tuple[str, ast.Call]:
    """The NAME `main()` binds the `CompletionHandler(...)` to, and the call.

    Resolved by name rather than by looking for the constructor inside
    `loop.attach(handler=...)`, because this process composes the handler in two
    steps — build it, then hand it to `LoopHandler` — and a gate that only
    recognised an inline construction would call the shipped, correct wiring
    library-not-daemon. Measured: the first run of this gate did exactly that.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        call = node.value
        if (
            isinstance(target, ast.Name)
            and isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "CompletionHandler"
        ):
            return target.id, call
    raise Cannot(
        f"{LIMITERD_FILE}: `main()` never binds a CompletionHandler, so no "
        "drained §2A completion reaches any consumer at all"
    )


def _handler_supplied(tree: ast.Module) -> dict[str, str]:
    """What `main()` actually hands `CompletionHandler(...)`, param -> expression.

    THE LIBRARY-NOT-DAEMON DETECTOR, at its sharpest point. Every collaborator
    of `CompletionHandler` is OPTIONAL in the constructor — deliberately, so a
    build without one reports `null` rather than a zero (check contract rule 10)
    — and the consequence is that a path can be removed from this daemon by
    deleting ONE argument at ONE call site while every line of its library
    survives, every unit test still passes, and every single-path gate over it
    stays green. That edit is exactly PLANT A.
    """
    params = _init_params(tree, "CompletionHandler")
    _, node = _completion_handler_binding(tree)
    supplied: dict[str, str] = {}
    for index, arg in enumerate(node.args):
        if index < len(params):
            supplied[params[index]] = ast.unparse(arg)
    for keyword in node.keywords:
        if keyword.arg:
            supplied[keyword.arg] = ast.unparse(keyword.value)
    return {
        name: expression
        for name, expression in supplied.items()
        if expression != "None"
    }


def _uncertainty_fanout(tree: ast.Module) -> set[str]:
    """Every §14 condition the producer fan-out map can actually fire.

    A member of `UncertaintyCondition` absent from `_UNCERTAINTY_TRIGGER` is
    detectable and NOT fireable — the condition exists in the vocabulary and no
    running process can turn it into a §4 close. That is the library-not-daemon
    state in its §14 spelling, and `UncertaintyDriver.send` would raise `KeyError`
    on it inside a contained sender, which is a silent stop.
    """
    for node in ast.walk(tree):
        target, value = _binding(node)
        if target != "_UNCERTAINTY_TRIGGER" or not isinstance(value, ast.Dict):
            continue
        members: set[str] = set()
        for key in value.keys:
            if isinstance(key, ast.Attribute):
                members.add(key.attr)
        return members
    raise Cannot(
        f"{LIMITERD_FILE}: no `_UNCERTAINTY_TRIGGER` map — §14's conditions "
        "reach no §4 trigger, so none of them can fire"
    )


@dataclass(frozen=True)
class _Wiring:  # pylint: disable=too-many-instance-attributes
    # NINE fields and each is ONE structural fact ARM 2 reads out of
    # `limiterd.py`. They are a frozen record rather than nine locals so the
    # judgement below is a pure function of the subject's shape — which is what
    # makes the rule-4 plant-both pair a single call with one thing changed.
    """Everything ARM 2 needs to know about how `main()` composes §5:322's tick."""

    ingress_names: frozenset[str]
    constructed: frozenset[str]
    supplied: dict[str, str]
    fanout: frozenset[str]
    sender_params: frozenset[str]
    sender_src: str
    sender_root: str
    handler_src: str
    handler_name: str

    @property
    def handler_reaches_loop(self) -> bool:
        """Does the CompletionHandler `main()` built reach `attach(handler=)`?

        By NAME, because the composition is two-step — build it, then hand it to
        `LoopHandler`. A gate that only recognised an inline construction would
        call the shipped, correct wiring library-not-daemon. Measured: the first
        run of this gate did exactly that.
        """
        return bool(self.handler_name) and self.handler_name in self.handler_src


def _wiring(tree: ast.Module) -> _Wiring:
    """Read the composition once. Every fact below comes from the subject's AST."""
    attach = _attach_call(tree)
    sender_expr = _kwarg(attach, "sender_send")
    sender_src = "" if sender_expr is None else ast.unparse(sender_expr)
    handler_expr = _kwarg(attach, "handler")
    handler_name, _ = _completion_handler_binding(tree)
    return _Wiring(
        ingress_names=frozenset(_before_chain(_kwarg(attach, "ingress"))),
        constructed=frozenset(_main_locals(tree)),
        supplied=_handler_supplied(tree),
        fanout=frozenset(_uncertainty_fanout(tree)),
        sender_params=frozenset(_sender_drivers(tree)),
        sender_src=sender_src or "<absent>",
        sender_root=sender_src.split(".", maxsplit=1)[0],
        handler_src="" if handler_expr is None else ast.unparse(handler_expr),
        handler_name=handler_name,
    )


def _judge_completion(member: str, wiring: _Wiring) -> str:
    """ONE structural fact covers the whole §2A family: the handler reaches the tick."""
    if wiring.handler_reaches_loop and wiring.supplied:
        return ""
    return (
        f"LIBRARY-NOT-DAEMON: §2A event {member!r} has no route into §5:322's "
        f"tick — `loop.attach(handler=...)` is "
        f"{wiring.handler_src or '<absent>'!r} and the CompletionHandler "
        f"`main()` built as {wiring.handler_name!r} is not composed into it. The "
        "dispatch code exists and no running process reaches it"
    )


def _judge_uncertainty(member: str, wiring: _Wiring) -> str:
    """A §14 condition with no §4 trigger is detectable and NOT actionable."""
    if member.upper() in wiring.fanout:
        return ""
    return (
        f"LIBRARY-NOT-DAEMON: §14 condition {member!r} is declared in "
        "`UncertaintyCondition` and is absent from `_UNCERTAINTY_TRIGGER`, so no "
        "§4 trigger exists for it and the sender can never fire a flatten on it. "
        "The condition is detectable and not actionable"
    )


def _judge_ingress(member: str, wiring: _Wiring) -> str:
    """A per-tick composer must be BUILT in `main()` and COMPOSED into the tick."""
    composed = member in wiring.ingress_names
    built = member in wiring.constructed
    if composed and built:
        return ""
    return (
        f"LIBRARY-NOT-DAEMON: per-tick path {member!r} is "
        f"{'composed into' if composed else 'not composed into'} "
        "`loop.attach(ingress=...)` and is "
        f"{'constructed' if built else 'NOT constructed'} in `main()`. §5:322's "
        "tick is the only place this process turns an object into work"
    )


def _judge_handler(member: str, wiring: _Wiring) -> str:
    """A declared completion collaborator `main()` hands nothing bypasses every fill."""
    if member in wiring.supplied:
        return ""
    return (
        f"LIBRARY-NOT-DAEMON: `CompletionHandler` declares the collaborator "
        f"{member!r} and `main()` hands it NOTHING (absent, or explicitly None), "
        "so every drained §2A completion bypasses it. The consumer's library is "
        "intact and no running process calls it — D3.178's *zero production "
        "callers*, one call site wide"
    )


def _judge_sender(member: str, wiring: _Wiring) -> str:
    """A protective sender that does not reach §5:323 has no thread to fire on."""
    if member in wiring.sender_params and wiring.sender_root in wiring.constructed:
        return ""
    return (
        f"LIBRARY-NOT-DAEMON: protective sender {member!r} does not reach "
        f"§5:323 — `loop.attach(sender_send=...)` is {wiring.sender_src!r}. §14 "
        "gives the protective exit zero wire dependency and this process gives "
        "it no thread"
    )


#: family -> the judge that decides whether that family's member is INVOKED. Keyed
#: by the families `_required` produces; a path whose family has no judge is
#: UNCLASSIFIABLE and says so rather than passing.
_JUDGES: Final[dict[str, Callable[[str, _Wiring], str]]] = {
    "completion": _judge_completion,
    "uncertainty": _judge_uncertainty,
    "ingress": _judge_ingress,
    "handler": _judge_handler,
    "sender": _judge_sender,
}


def _invoked(
    nix_home: Path, required: dict[str, str]
) -> tuple[set[str], list[tuple[str, str]]]:
    """ARM 2. `(invoked, findings)` — proven structurally, never by existence."""
    wiring = _wiring(_tree(nix_home / LIMITERD_FILE))
    findings: list[tuple[str, str]] = []
    invoked: set[str] = set()
    for path in sorted(required):
        family, _, member = path.partition(":")
        judge = _JUDGES.get(family)
        if judge is None:
            findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"UNCLASSIFIABLE: {path!r} belongs to no known family, so "
                        "this gate cannot say which of §5:322's seams it should "
                        "reach"
                    ),
                )
            )
            continue
        why = judge(member, wiring)
        if why:
            findings.append((LIMITERD_FILE, why))
        else:
            invoked.add(path)
    return invoked, findings


# --------------------------------------------------------------------------
# ARM 3 — the drive. A REAL limiterd, real files, the daemon's own record.
# --------------------------------------------------------------------------


class Drive:
    """One `limiterd` process and every path into it. Torn down always."""

    def __init__(self, nix_home: Path, *, tag: str) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix=f"check-i1-{tag}-"))
        self._n = 0
        interpreter = nix_home / ".venv/bin/python"
        if not interpreter.exists():
            raise Cannot(f"no interpreter at {interpreter}")
        script = nix_home / LIMITERD_FILE
        if not script.exists():
            raise Cannot(f"no {LIMITERD_FILE} under {nix_home}")
        try:
            self.proc = subprocess.Popen(  # nosec B603  # pylint: disable=consider-using-with
                [
                    str(interpreter),
                    str(script),
                    "--runtime-dir",
                    str(self.dir),
                    "--heartbeat-interval",
                    str(DRIVE_HEARTBEAT_S),
                    "--tick-interval",
                    str(DRIVE_TICK_S),
                    "--max-ticks",
                    str(DRIVE_MAX_TICKS),
                    "--tick-size",
                    f"{SYMBOL}={TICK_SIZE}",
                    "--account-balance",
                    str(BALANCE),
                    "--reconcile-window",
                    str(DRIVE_WINDOW_S),
                    "--go-timeout",
                    str(DRIVE_GO_TIMEOUT_S),
                ],
                cwd=str(nix_home / "scripts"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONPATH": str(nix_home / "scripts")},
            )
        except OSError as exc:
            raise Cannot(f"cannot spawn limiterd: {exc!r}") from exc
        self._await_boot()

    def _await_boot(self) -> None:
        runtime = self.dir / "limiter.runtime.json"
        deadline = time.time() + BOOT_TIMEOUT_S
        while time.time() < deadline:
            if runtime.exists():
                return
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() if self.proc.stderr else "")[-800:]
                raise Cannot(
                    f"limiterd refused to boot ({self.proc.returncode}): {err}"
                )
            time.sleep(0.05)
        raise Cannot(f"limiterd wrote no runtime record within {BOOT_TIMEOUT_S}s")

    @staticmethod
    def atomically(path: Path, payload: dict[str, Any]) -> Path:
        """Write one JSON file the daemon may be scanning on its own tick."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".partial")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
        return path

    def cmd(self, verb: str, **fields: object) -> dict[str, Any]:
        """Send one command file; return the daemon's own reply."""
        self._n += 1
        cid = f"cic{self._n:05d}"
        self.atomically(
            self.dir / "inbox" / f"{cid}.json",
            {"schema": 1, "id": cid, "verb": verb, **fields},
        )
        reply = self.dir / "outbox" / f"{cid}.reply.json"
        deadline = time.time() + REPLY_TIMEOUT_S
        while time.time() < deadline:
            if reply.exists():
                try:
                    return json.loads(reply.read_text())
                except ValueError:
                    time.sleep(0.02)
                    continue
            if self.proc.poll() is not None:
                raise Cannot(
                    f"limiterd exited with {self.proc.returncode} before "
                    f"answering {verb!r}"
                )
            time.sleep(0.02)
        raise Cannot(f"limiterd did not answer {verb!r} within {REPLY_TIMEOUT_S}s")

    def reserve(self, cid: str, **over: object) -> dict[str, Any]:
        """§3's take-at-approval, with this gate's own numbers."""
        fields: dict[str, Any] = {
            "strategy_id": STRATEGY,
            "client_order_id": cid,
            "symbol": SYMBOL,
            "side": "long",
            "qty": QTY,
            "margin_per_contract": MARGIN,
            "stop_ticks": STOP_TICKS,
            "stop_mode": "fixed",
            "signal_ts": time.time(),
        }
        fields.update(over)
        took = self.cmd("reserve", **fields)
        if not took.get("accepted"):
            raise Cannot(f"the daemon refused a reservation: {took.get('reason')}")
        return took

    def completion(self, name: str, payload: dict[str, Any]) -> Path:
        """One §2A exec report, through the COMPLETIONS DIRECTORY (never a call)."""
        return self.atomically(
            self.dir / "completions" / f"{name}.json", {"schema": 1, **payload}
        )

    def fill(
        self,
        cid: str,
        *,
        symbol: str = SYMBOL,
        price: float = FILL_PRICE,
        exec_id: str | None = None,
        name: str | None = None,
    ) -> Path:
        """One §2A confirmed fill."""
        return self.completion(
            name or f"fill-{cid}",
            {
                "event": "on_fill",
                "client_order_id": cid,
                "exec_id": exec_id or f"x-{cid}",
                "done_qty": QTY,
                "symbol": symbol,
                "price": price,
                "cumulative_qty": QTY,
            },
        )

    def status_answer(self, cid: str, state: str) -> Path:
        """One §2A `OrderStatus` answer, through the STATUS DIRECTORY."""
        return self.atomically(
            self.dir / "status" / f"{cid}.json",
            {
                "client_order_id": cid,
                "state": state,
                "terminal": True,
                "cumulative_qty": QTY,
            },
        )

    def onset(self, **state: object) -> Path:
        """One declared onset state, through the ONSET DIRECTORY."""
        return self.atomically(self.dir / "onset" / "state.json", dict(state))

    def price(self, price: float) -> dict[str, Any]:
        """§5:322's price, published from OUTSIDE the process."""
        answer = self.cmd("price", symbol=SYMBOL, price=price)
        if not answer.get("accepted"):
            raise Cannot(f"the daemon refused a price: {answer.get('reason')}")
        return answer

    def watch(self, pred: Callable[[dict[str, Any]], Any], what: str) -> dict[str, Any]:
        """Poll the daemon's OWN status until `pred`. Watches PAST the tick."""
        deadline = time.time() + WATCH_HORIZON_S
        status = self.cmd("status")
        while time.time() < deadline:
            if pred(status):
                return status
            time.sleep(0.03)
            status = self.cmd("status")
        raise Missed(what, status)

    def stop_record(self) -> dict[str, Any]:
        """SIGTERM, join, and read the CLEAN STOP record the daemon wrote."""
        self.close()
        try:
            return json.loads((self.dir / "limiter.runtime.json").read_text())
        except (OSError, ValueError) as exc:
            raise Cannot(f"unreadable stop record: {exc!r}") from exc

    def close(self) -> None:
        """SIGTERM and join. Called from a `finally` on every path."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream is not None:
                stream.close()


def _block(status: dict[str, Any], name: str) -> dict[str, Any]:
    """One published block, or a raise. `None` is CANNOT_MEASURE, never zero."""
    block = status.get(name)
    if block is None:
        raise Cannot(
            f"{LIMITERD_FILE}: this build's status reply carries no {name!r} "
            "block, so the paths it would report are held by nothing in this "
            "process (check contract rule 10: a property proven while its "
            "subject is unavailable is not proven)"
        )
    return block


def _quiet_start(drive: Drive) -> list[tuple[str, str]]:
    """ARM 5 / §7.12 #4. NOTHING may have moved before this gate touched anything."""
    findings: list[tuple[str, str]] = []
    status = drive.cmd("status")
    moved: list[str] = []
    completions = _block(status, "completions")
    if completions.get("seen"):
        moved.append(f"completions.seen={completions['seen']}")
    uncertainty = _block(status, "uncertainty")
    if uncertainty.get("sends") or uncertainty.get("flattened"):
        moved.append(
            f"uncertainty.sends={uncertainty.get('sends')!r} "
            f"flattened={uncertainty.get('flattened')!r}"
        )
    stops = _block(status, "stops")
    if stops.get("sends") or stops.get("breaches"):
        moved.append(
            f"stops.sends={stops.get('sends')!r} breaches={stops.get('breaches')!r}"
        )
    closing = _block(status, "closing")
    if closing.get("closed") or (closing.get("flattens") or {}).get("armed"):
        moved.append(f"closing={json.dumps(closing)[:200]}")
    if moved:
        findings.append(
            (
                LIMITERD_FILE,
                "NON-VACUITY: the daemon reports " + "; ".join(moved) + " before "
                "this gate established anything — a later 'this path was driven' "
                "would be counting something this gate did not cause",
            )
        )
    return findings


# -- the per-path drivers ----------------------------------------------------
#
# THIS TABLE IS THIS GATE'S COVERAGE, NEVER ITS AUTHORITY. It is keyed by the
# ids ARM 1 DERIVES, and a derived id with no entry here is CANNOT_MEASURE
# naming it (§7.12 #1). Each entry is `(establish, observe)`: `establish` acts
# through the daemon's own ingress, `observe` reads the daemon's own record.


def _drive_completions(drive: Drive) -> dict[str, dict[str, Any]]:
    """Every §2A event, one at a time, through the completions directory.

    Returns `event -> the status the daemon published right after it`, so the
    caller can assert per-event movement rather than reading one shared total.
    """
    seen: dict[str, dict[str, Any]] = {}
    drive.cmd("register", strategy_id=STRATEGY)

    drive.reserve("cic-cancel")
    drive.completion(
        "cancel",
        {
            "event": "on_cancel",
            "client_order_id": "cic-cancel",
            "exec_id": "x-cic-cancel",
            "done_qty": 0,
        },
    )
    seen["on_cancel"] = drive.watch(
        lambda st: (_block(st, "completions").get("cancels_dispatched") or 0) >= 1,
        "§3's cancel release, dispatched by the daemon",
    )

    drive.reserve("cic-reject")
    drive.completion(
        "reject",
        {
            "event": "on_reject",
            "client_order_id": "cic-reject",
            "exec_id": "x-cic-reject",
            "done_qty": 0,
        },
    )
    seen["on_reject"] = drive.watch(
        lambda st: (_block(st, "completions").get("rejects_dispatched") or 0) >= 1,
        "§3's reject release, dispatched by the daemon",
    )

    drive.reserve("cic-entry")
    drive.fill("cic-entry")
    seen["on_fill"] = drive.watch(
        lambda st: (_block(st, "completions").get("fills_dispatched") or 0) >= 1,
        "§4's fill cascade, dispatched by the daemon",
    )
    return seen


def _drive_unwired(drive: Drive, event: str) -> dict[str, Any]:
    """One §2A event this build does NOT dispatch. It must be REFUSED BY NAME."""
    drive.completion(
        f"unwired-{event}",
        {
            "event": event,
            "client_order_id": f"cic-{event}",
            "exec_id": f"x-cic-{event}",
            "done_qty": 0,
        },
    )
    return drive.watch(
        lambda st: _block(st, "completions").get("last_event") == event,
        f"the daemon to CLASSIFY §2A's {event!r}",
    )


def _drive_breach_and_close(
    drive: Drive, findings: list[tuple[str, str]]
) -> dict[str, dict[str, Any]]:
    """C1's breach -> protective send -> ARC 058's closing fill, end to end.

    The two halves are contained SEPARATELY. A breach that never fires and a
    flatten whose closing fill is never reconciled are two different paths, and
    reporting one absence for both would name the wrong site — which is exactly
    what PLANT A1 needs this gate to get right.
    """
    out: dict[str, dict[str, Any]] = {}
    row = drive.watch(
        lambda st: _block(st, "fills").get("positions") or [],
        "the entry fill to publish a §3 OPEN row",
    )
    positions = _block(row, "fills").get("positions") or []
    if not any(entry.get("state") == "open" for entry in positions):
        raise Cannot(
            f"{LIMITERD_FILE}: §3's table holds {positions!r} and none is OPEN, "
            "so there is no protected position for a stop to breach"
        )
    drive.price(BREACH_PRICE)
    fired = _step(
        lambda: drive.watch(
            lambda st: (_block(st, "stops").get("sends") or 0) >= 1,
            "§4:187-196's breach to FIRE and SEND one protective flatten",
        ),
        findings,
    )
    if fired is not None:
        out["sender:stops"] = fired
    drive.fill("cic-flatten", price=BREACH_PRICE, name="closing")
    reconciled = _step(
        lambda: drive.watch(
            lambda st: (_block(st, "closing").get("closed") or 0) >= 1,
            "the closing fill to be RECONCILED (§12.10 closed row, §3 release)",
        ),
        findings,
    )
    if reconciled is not None:
        out["handler:closing"] = reconciled
    return out


def _drive_onset(drive: Drive) -> dict[str, Any]:
    """§3:173's onset, declared through the onset directory and swept."""
    drive.reserve("cic-onset")
    drive.onset(blackout=[SYMBOL], halt=False)
    return drive.watch(
        lambda st: (_block(st, "onset").get("blackout_onsets") or 0) >= 1,
        "§3:173's blackout onset to be DETECTED on the edge and swept",
    )


def _drive_timeout(drive: Drive) -> dict[str, Any]:
    """§4's pending-timeout resolution: an answer on disk, resolved by the poll."""
    drive.reserve("cic-timeout")
    drive.status_answer("cic-timeout", "cancelled")
    return drive.watch(
        lambda st: (_block(st, "timeouts").get("resolved") or 0) >= 1,
        "§4's pending-timeout poll to RESOLVE an overdue order",
    )


def _drive_go_timeout(drive: Drive) -> dict[str, Any]:
    """§4:210-212's breaker, so the Plane-1 booker composed into the tick RUNS."""
    drive.cmd("go", strategy_id=STRATEGY, client_order_id="cic-go")
    return drive.watch(
        lambda st: "go timeouts 0" not in str(st.get("reason") or ""),
        "§4:210-212's deadlock breaker to FIRE, giving the booker a row to book",
    )


def _drive_stale_open(drive: Drive) -> dict[str, Any]:
    """§14 / D3.453: a REAL open position whose price feed then goes quiet."""
    drive.cmd("register", strategy_id=STRATEGY)
    drive.reserve("cic-stale")
    drive.fill("cic-stale")
    drive.watch(
        lambda st: _block(st, "fills").get("positions") or [],
        "a published §3 position row for the stale-open condition",
    )
    # The feed is ALIVE first and that is load-bearing: a symbol nothing has ever
    # priced is EMPTY, which this daemon deliberately does not flatten on
    # (D3.473). What is established is a feed that WAS observed and went QUIET.
    drive.price(FILL_PRICE)
    return drive.watch(
        lambda st: (_block(st, "uncertainty").get("detected") or {}).get("stale_open"),
        "§6.4's flatten-open half to DETECT a stale OPEN position",
    )


def _drive_not_tradable(drive: Drive) -> dict[str, Any]:
    """§14 / D3.372: a confirmed fill whose §4:198 origin write refuses."""
    drive.cmd("register", strategy_id=STRATEGY)
    drive.reserve("cic-untradable")
    drive.fill("cic-untradable", symbol=OTHER)
    return drive.watch(
        lambda st: (_block(st, "uncertainty").get("detected") or {}).get(
            "not_tradable_fill"
        ),
        "§4:198's origin write to REFUSE a fill in an unapproved symbol",
    )


def _drive_unarmable(drive: Drive) -> dict[str, Any]:
    """§14 / D3.475: a fill whose §4 stop conversion is REFUSED."""
    drive.cmd("register", strategy_id=STRATEGY)
    drive.reserve("cic-unarmable", stop_mode="trailing")
    drive.fill("cic-unarmable")
    return drive.watch(
        lambda st: (_block(st, "uncertainty").get("detected") or {}).get(
            "unarmable_fill"
        ),
        "§4's stop conversion to REFUSE a trailing fill carrying no distance",
    )


def _drive_poll_fill(drive: Drive) -> dict[str, Any]:
    """§14 / D3.469: the poll answers `filled` and nothing can convert it."""
    drive.cmd("register", strategy_id=STRATEGY)
    drive.reserve("cic-pollfill")
    drive.status_answer("cic-pollfill", "filled")
    return drive.watch(
        lambda st: (_block(st, "uncertainty").get("detected") or {}).get(
            "undetailed_poll_fill"
        ),
        "D3.469's bounded window to expire and the condition to be DETECTED",
    )


#: §14's four producers, each in its OWN daemon. Separate processes because the
#: conditions are not independent inside one: a breach that closes the ES
#: position removes the OPEN row `stale_open` is about, and a shared daemon would
#: make the drive order decide the verdict.
_UNCERTAINTY_DRIVES: Final[dict[str, Callable[[Drive], dict[str, Any]]]] = {
    "uncertainty:stale_open": _drive_stale_open,
    "uncertainty:not_tradable_fill": _drive_not_tradable,
    "uncertainty:unarmable_fill": _drive_unarmable,
    "uncertainty:undetailed_poll_fill": _drive_poll_fill,
}


def _step(
    fn: Callable[[], Any],
    findings: list[tuple[str, str]],
) -> Any:
    """Run ONE drive step. A condition that never arrives is a FINDING, not a raise.

    **THIS CONTAINMENT IS A CORRECTION THIS ARC MADE TO ITS OWN GATE, AND THE
    MEASUREMENT IS RECORDED RATHER THAN THE FIX ALONE.** PLANT A1 — the closing
    handler removed from `main()`'s one `CompletionHandler(...)` call, its library
    untouched — first made this gate exit **2**: the drive's `Missed` propagated
    to `run`'s catch-all and came back *cannot_measure: gate raised Missed*. ARM
    2 had already produced the LIBRARY-NOT-DAEMON finding that names the path,
    and it was discarded with the exception. A defect downgraded to
    CANNOT_MEASURE is a defect that never names itself
    (`check_uncertainty_flatten`'s ARC 057 / S4b ruling, met again here), and a
    path that cannot be driven is precisely what I1 is about — so it is reported
    as one, with the last status the daemon published attached.
    """
    try:
        return fn()
    except Missed as miss:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NOT DRIVEN: {miss.what} — the drive went through the daemon's "
                    "own ingress and the daemon's own record never showed it. Last "
                    f"status: {json.dumps(miss.status)[:600]}"
                ),
            )
        )
        return None


@dataclass
class Tally:
    """What ARM 3 accumulates. One record so the phases below take one argument.

    `driven` is the answer; the other three are what an operator reads. They
    travel together because a phase that added to one and not the others would
    produce a verdict with no sentence behind it (check contract rule 11).
    """

    driven: set[str]
    findings: list[tuple[str, str]]
    cannot: list[str]
    evidence: list[str]


def _phase_wired_events(drive: Drive, out: Tally) -> dict[str, dict[str, Any]]:
    """§2A's DISPATCHED events, driven through the completions directory."""
    wired = _step(lambda: _drive_completions(drive), out.findings) or {}
    for event, status in wired.items():
        block = _block(status, "completions")
        out.driven.add(f"completion:{event}")
        out.evidence.append(
            f"completion:{event} DRIVEN — "
            f"last_disposition={block.get('last_disposition')!r} from "
            f"{block.get('last_source')!r}"
        )
    return wired


def _phase_unwired_events(
    drive: Drive,
    spec_events: list[str],
    wired_events: set[str],
    already: dict[str, dict[str, Any]],
    out: Tally,
) -> None:
    """Every §2A event this build does NOT dispatch. It must be REFUSED BY NAME."""
    for event in spec_events:
        if event in already:
            continue
        if event in wired_events:
            # Declared DISPATCHED by the subject and NOT hand-driven above. This
            # gate holds no drive that establishes it, and a wired event proven
            # by the generic unwired probe would be proven by the wrong
            # observation. CANNOT_MEASURE naming it (check contract rule 10).
            out.cannot.append(
                f"{COMPLETIONS_FILE}: §2A event {event!r} is declared in "
                "WIRED_EVENTS — this build says it DISPATCHES it — and this gate "
                "holds no drive that establishes that dispatch. The path is "
                "REQUIRED and UNPROVEN; it is not a pass"
            )
            continue
        # `partial` BINDS the loop variable: a bare closure would capture the
        # name and every deferred call would probe the last event in the list.
        status = _step(partial(_drive_unwired, drive, event), out.findings)
        if status is None:
            continue
        block = _block(status, "completions")
        if block.get("last_disposition") != "unwired":
            out.findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"§2A event {event!r} is in SPEC_EVENTS and NOT in "
                        f"WIRED_EVENTS, and the daemon answered "
                        f"{block.get('last_disposition')!r} rather than "
                        "'unwired'. An event the spec pushes must be refused BY "
                        "NAME, not absorbed"
                    ),
                )
            )
            continue
        out.driven.add(f"completion:{event}")
        out.evidence.append(
            f"completion:{event} DRIVEN — refused BY NAME as 'unwired' from "
            f"{block.get('last_source')!r}"
        )


def _note_protective_send(status: dict[str, Any], out: Tally) -> None:
    """ARM 5 over C1's send: the BROKER saw it, and it ran OFF the loop thread."""
    stops = _block(status, "stops")
    out.evidence.append(
        f"sender:stops DRIVEN — sends={stops.get('sends')} broker "
        f"flattened={stops.get('flattened')!r} on thread "
        f"{stops.get('sent_on_native_id')} (loop {stops.get('loop_native_id')})"
    )
    if stops.get("sent_on_native_id") == stops.get("loop_native_id"):
        out.findings.append(
            (
                LIMITERD_FILE,
                (
                    "the protective flatten was SENT ON THE LOOP THREAD "
                    f"({stops.get('sent_on_native_id')}). §5:323 puts blocking "
                    "work on the sender and *the hot loop never blocks*; a send "
                    "on the loop is I9 broken silently"
                ),
            )
        )
    if not stops.get("flattened"):
        out.findings.append(
            (
                LIMITERD_FILE,
                (
                    "NON-VACUITY: the driver reports a send and the BROKER's own "
                    "`flattened` record is empty — check contract rule 2: the "
                    "return of a mutating call is not a verification"
                ),
            )
        )


def _note_close(status: dict[str, Any], out: Tally) -> None:
    """ARC 058's close, and §3's own published Σ on the far side of the release."""
    closing = _block(status, "closing")
    closes = closing.get("closes") or []
    out.evidence.append(
        f"handler:closing DRIVEN — closed={closing.get('closed')} "
        f"close={json.dumps(closes[-1]) if closes else '<none>'}"
    )
    picture = _block(status, "picture")
    if picture.get("sum_open_margin"):
        out.findings.append(
            (
                LIMITERD_FILE,
                (
                    "the closing fill was reconciled and §3 still publishes "
                    f"sum_open_margin={picture.get('sum_open_margin')!r} — the "
                    "open margin of a position the venue has closed is capital "
                    "this process is holding against nothing (§3)"
                ),
            )
        )


def _phase_exits(drive: Drive, out: Tally) -> None:
    """C1's breach -> protective send -> ARC 058's closing fill."""
    exits = _step(lambda: _drive_breach_and_close(drive, out.findings), out.findings)
    out.driven.update(exits or {})
    if exits and "sender:stops" in exits:
        _note_protective_send(exits["sender:stops"], out)
    if exits and "handler:closing" in exits:
        _note_close(exits["handler:closing"], out)


def _phase_tick(drive: Drive, out: Tally) -> None:
    """The per-tick paths and the completion collaborators, off one status read."""
    for path, driver in (
        ("ingress:onset", _drive_onset),
        ("ingress:timeouts", _drive_timeout),
    ):
        status = _step(partial(driver, drive), out.findings)
        if status is None:
            continue
        block = path.partition(":")[2]
        out.driven.add(path)
        out.evidence.append(
            f"{path} DRIVEN — {json.dumps(_block(status, block))[:220]}"
        )
    tick = drive.cmd("status")
    for path, block, key in (
        ("ingress:stopwatch", "stops", "polls"),
        ("ingress:uncertainty", "uncertainty", "scans"),
        ("handler:dispatcher", "completions", "seen"),
    ):
        moved = _block(tick, block).get(key) or 0
        if moved >= 1:
            out.driven.add(path)
            out.evidence.append(f"{path} DRIVEN — {key}={moved}")
    # §4:203-206's OPEN push is observed as the file the DAEMON wrote, because
    # this build's status reply carries no `feedback` block — the artifact is the
    # daemon's own and is a stronger reading than a counter would be.
    feedback = sorted(
        path.name
        for path in (drive.dir / "outbox").iterdir()
        if path.name.endswith(".feedback.json")
    )
    if feedback:
        out.driven.add("handler:feedback")
        out.evidence.append(f"handler:feedback DRIVEN — the daemon wrote {feedback}")


def _phase_booker(drive: Drive, out: Tally) -> None:
    """§4:210-212's breaker, so the Plane-1 booker composed into the tick RUNS.

    LAST, and read out of the CLEAN STOP record rather than the status reply:
    `Plane1Booker` publishes its counters into `limiter.runtime.json` and not
    into `_picture()`, so the only place a running daemon reports whether the
    booker booked is the record it writes when it stops.
    """
    _step(partial(_drive_go_timeout, drive), out.findings)
    plane1 = drive.stop_record().get("plane1") or {}
    if (plane1.get("booked") or 0) >= 1:
        out.driven.add("ingress:booker")
        out.evidence.append(
            f"ingress:booker DRIVEN — firings_seen={plane1.get('firings_seen')} "
            f"booked={plane1.get('booked')} wal_enqueued={plane1.get('wal_enqueued')}"
        )


def _phase_one_producer(
    nix_home: Path, path: str, establish: Callable[[Drive], dict[str, Any]], out: Tally
) -> None:
    """ONE §14 producer, in its OWN daemon. See `_UNCERTAINTY_DRIVES` for why."""
    producer = Drive(nix_home, tag=path.partition(":")[2])
    try:
        block = _block(establish(producer), "uncertainty")
        out.driven.update({path, "sender:uncertainty", "handler:uncertainty"})
        out.evidence.append(
            f"{path} DRIVEN — detected={json.dumps(block.get('detected'))} "
            f"sends={block.get('sends')} flattened={block.get('flattened')!r}"
        )
        fired = _block(
            producer.watch(
                lambda st: (_block(st, "uncertainty").get("sends") or 0) >= 1,
                f"a §4 protective flatten for {path}",
            ),
            "uncertainty",
        )
        if not fired.get("flattened"):
            out.findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"NON-VACUITY: {path} reports sends={fired.get('sends')!r} "
                        "and the BROKER's own `flattened` record is empty"
                    ),
                )
            )
        if fired.get("sent_on_native_id") == fired.get("loop_native_id"):
            out.findings.append(
                (
                    LIMITERD_FILE,
                    (
                        f"{path}'s protective flatten was SENT ON THE LOOP THREAD "
                        "— §5:323 and I9"
                    ),
                )
            )
        if fired.get("unclassified"):
            out.cannot.append(
                f"{LIMITERD_FILE}: while driving {path} the daemon recorded "
                f"UNCLASSIFIED refused fills {fired['unclassified']!r} — a "
                "confirmed venue fill nothing decided §14's owed answer for. "
                "Check contract rule 10: not proven"
            )
    except Missed as miss:
        out.findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NOT DRIVEN: {path} — {miss.what} never happened. The path is "
                    "composed into this daemon and no drive through its own "
                    "ingress could make it run. Last status: "
                    f"{json.dumps(miss.status.get('uncertainty'))[:400]}"
                ),
            )
        )
    finally:
        producer.close()


def _driven(
    nix_home: Path, required: dict[str, str]
) -> tuple[set[str], list[tuple[str, str]], list[str], list[str]]:
    """ARM 3 + ARM 5. `(driven, findings, cannot, evidence)`."""
    out = Tally(driven=set(), findings=[], cannot=[], evidence=[])
    spec_events = sorted(
        path.partition(":")[2] for path in required if path.startswith("completion:")
    )
    #: DERIVED, never listed here. An event this build declares it DISPATCHES is
    #: a different path from one it declares it refuses, and the two are proven
    #: by different observations — so the split has to come from the subject.
    wired_events = set(
        _assigned_tuple(_tree(nix_home / COMPLETIONS_FILE), "WIRED_EVENTS")
    )

    drive = Drive(nix_home, tag="main")
    try:
        out.findings.extend(_quiet_start(drive))
        wired = _phase_wired_events(drive, out)
        _phase_unwired_events(drive, spec_events, wired_events, wired, out)
        _phase_exits(drive, out)
        _phase_tick(drive, out)
        _phase_booker(drive, out)
    finally:
        drive.close()

    for path, establish in _UNCERTAINTY_DRIVES.items():
        if path in required:
            _phase_one_producer(nix_home, path, establish, out)
    return out.driven, out.findings, out.cannot, out.evidence


# --------------------------------------------------------------------------
# ARM 4 — COMPLETENESS, and the verdict
# --------------------------------------------------------------------------


def _measure(  # pylint: disable=too-many-branches,too-many-locals
    nix_home: Path,
) -> CheckResult:
    """Derive, prove invoked, drive, and compare the three sets."""
    required = _required(nix_home)
    invoked, invoke_findings = _invoked(nix_home, required)
    findings = list(invoke_findings)
    cannot: list[str] = []
    evidence: list[str] = [
        f"required-path set DERIVED ({len(required)}): {sorted(required)}"
    ]

    # A required path with no driver is CANNOT_MEASURE naming it (§7.12 #1). The
    # coverage is checked BEFORE the drive so a vocabulary that grew is reported
    # as *this gate cannot say*, never as a drive that quietly skipped it.
    servable = (
        {
            f"completion:{event}"
            for event in (
                path.partition(":")[2]
                for path in required
                if path.startswith("completion:")
            )
        }
        | set(_UNCERTAINTY_DRIVES)
        | {
            "ingress:onset",
            "ingress:timeouts",
            "ingress:stopwatch",
            "ingress:uncertainty",
            "ingress:booker",
            "handler:dispatcher",
            "handler:feedback",
            "handler:uncertainty",
            "handler:closing",
            "sender:stops",
            "sender:uncertainty",
        }
    )
    unservable = sorted(set(required) - servable)
    for path in unservable:
        cannot.append(
            f"UNCLASSIFIABLE REQUIRED PATH {path!r} — derived from "
            f"{required[path]}, and this gate holds no driver that can exercise "
            "it through a real daemon. A required path this instrument cannot "
            "reach is NOT PROVEN (check contract rule 10); it is not a pass"
        )

    driven, drive_findings, drive_cannot, drive_evidence = _driven(nix_home, required)
    findings.extend(drive_findings)
    cannot.extend(drive_cannot)
    evidence.extend(drive_evidence)

    # ARM 4. The completeness comparison, both directions, each named.
    missing_drive = sorted(set(required) - driven - set(unservable))
    for path in missing_drive:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"NOT DRIVEN: {path!r} is a REQUIRED path (derived from "
                    f"{required[path]}) and this gate could not make a running "
                    "daemon exercise it. I1 is *the daemon invokes the complete "
                    "required set*, and an unexercised member is exactly the gap"
                ),
            )
        )
    extra = sorted(driven - set(required))
    for path in extra:
        findings.append(
            (
                LIMITERD_FILE,
                (
                    f"DRIVEN AND NOT REQUIRED: {path!r} was exercised and is absent "
                    "from the DERIVED required set — the derivation and the drive "
                    "disagree about what this daemon is accountable for"
                ),
            )
        )
    missing_invoke = sorted(set(required) - invoked)
    evidence.append(
        f"invoked {len(invoked)}/{len(required)} · driven {len(driven & set(required))}"
        f"/{len(required)} · unservable {len(unservable)}"
    )

    if findings:
        head = findings[0]
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site=head[0],
            detail="; ".join(f"{site}: {why}" for site, why in findings[:6])
            + (f" — and {len(findings) - 6} more" if len(findings) > 6 else ""),
            evidence=" | ".join(evidence)[:4000],
            action=(
                "wire the named path into `loop.attach`'s ingress/handler/"
                "sender_send composition, or drive it, and re-run. I1 does NOT "
                "discharge while any required path is library-not-daemon"
            ),
        )
    if cannot:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail="; ".join(cannot[:4]),
            evidence=" | ".join(evidence)[:4000],
        )
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        site=LIMITERD_FILE,
        detail=(
            f"I1 CONVERGENCE: the daemon's required-path set is COMPLETE at "
            f"{len(required)} paths, DERIVED from five vocabularies in the "
            f"subject's own source; every one is daemon-INVOKED (reachable from "
            f"§5:322's `loop.attach`) and every one was DRIVEN through a real "
            f"limiterd's own ingress. invoked={len(invoked)} driven="
            f"{len(driven & set(required))} missing_invoke={missing_invoke}"
        ),
        evidence=" | ".join(evidence)[:4000],
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove I1: the daemon invokes the COMPLETE required path set. Never repairs."""
    try:
        return _measure(Path(ctx.nix_home))
    except Cannot as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=LIMITERD_FILE,
            detail=str(exc),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation this gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
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
