#!/usr/bin/env python3
"""The Limiter seam is a TRANSCRIPTION of the frozen spec, never a second authority.

ONE gate, ONE property (`nix_check_contract.md` §5.5): *`scripts/nixrisk/seam.py`
declares shape that the frozen risk spec already fixes, and declares nothing
else.* Two arms serve that single property and are not two properties:

  * **ARM 1 — the terminal-path set is the SPEC's, derived from the spec text.**
    §3's reservation lifecycle names its release paths in one sentence. This gate
    parses that sentence out of `nics_risk_subsystem_spec_v1.3.md` at run time
    and compares it to `TerminalPath`'s members. Nothing is typed out here: the
    expected set is not a constant in this file, so a member added to the enum
    without a matching spec sentence is red, and so is a spec sentence with no
    member.

  * **ARM 2 — the seam carries no behaviour.** Every callable in the module is a
    declaration: a `Protocol` method with no body, or a property returning one
    expression over its own fields. Anything that branches, loops, calls out, or
    touches the world is behaviour, and behaviour in the seam is how a data-role
    artifact becomes a second behavioural authority that can silently disagree
    with the spec (`directory_structure.md`'s standing rule for `risks/`, and the
    same failure shape one directory over).

WHY THIS SHAPE AND NOT A CLAIM. `checks/derived_claims.json` compares INTEGERS
from two sources. The property here is set membership between an enum and a
sentence, and the value of the instrument is naming *which member* diverged —
which a count cannot do (doctrine C.2).

WHAT THIS GATE CANNOT PROVE, stated rather than implied. It reads the seam
STATICALLY. It cannot prove the Limiter's executor honours the phase ordering, or
that a reservation is released on every path at run time — those are behaviours
of code this arc builds elsewhere and they need their own instruments driving
real objects. A green here means the DECLARATION is faithful, never that the
implementation obeys it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text; the only way to
# deduplicate them is a shared helper, which §4.2 forbids.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first: both sides are files on disk that no check produces.
DEPENDS_ON: tuple[str, ...] = ()
#: Claims NOTHING. Two file reads and an AST parse; no socket, no subprocess, no
#: write. `()` is the positive claim and is what makes this gate
#: parallel-eligible (check contract v2 §12 — declared claims are checked against
#: OBSERVED ones, so an empty declaration here is falsifiable, not trusted).
RESOURCES: tuple[str, ...] = ()
#: No timeout, no poll. The runtime is two file reads.
TIME_BOUND = False
#: NON-CORRECTABLE. Both arms compare the seam against the FROZEN spec. A gate
#: empowered to edit the seam into agreement would be manufacturing its own
#: green, and the frozen spec is the one document in this tree nothing may edit.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is the frozen risk spec, which is never edited, and the "
    "measured side is a declaration whose whole purpose is to be checkable "
    "against it. An instrument that could rewrite either side to agree would be "
    "manufacturing its own green -- the same objection that makes "
    "check_artifact_gate_coverage non-correctable."
)
#: Genuinely MEASURED here, not merely named: every byte of both files is parsed
#: and every callable in them is classified.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/__init__.py",
)

NAME = "check_limiter_seam"

SEAM = "scripts/nixrisk/seam.py"
PACKAGE = "scripts/nixrisk"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"

#: The §3 sentence carrying the release paths. Anchored on "released on:" so the
#: gate fails loud if the sentence is renamed or moved, rather than silently
#: matching nothing and reporting an empty expected set as agreement.
_RELEASE_SENTENCE = re.compile(r"released on:(?P<paths>.*?)\.\s", re.DOTALL)

#: How a spec phrase becomes an enum member: take the leading words before any
#: parenthetical or trailing noun, join with `_`. "pending-timeout resolution"
#: -> PENDING_TIMEOUT; "fill (converts to open-margin)" -> FILL.
_TRAILING_NOUN = ("resolution", "cancellation")

#: Names whose presence in the seam is behaviour by construction.
_FORBIDDEN_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "print", "input"}
)
_FORBIDDEN_IMPORTS = frozenset(
    {"os", "subprocess", "socket", "zmq", "threading", "asyncio", "time", "json"}
)

#: Non-vacuity floors (`debug.md` §7.12). Each is a count this gate MUST reach or
#: it has measured nothing and says so rather than passing.
MIN_TERMINAL_PATHS = 3
MIN_CALLABLES = 5


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def _phrase_to_member(phrase: str) -> str:
    """One spec phrase -> the enum member it names. Pure text, no lookup table."""
    text = re.sub(r"\(.*?\)", " ", phrase).strip().lower()
    words = [word for word in re.split(r"[\s\-]+", text) if word]
    while words and words[-1] in _TRAILING_NOUN:
        words.pop()
    return "_".join(words).upper()


def spec_terminal_paths(home: Path) -> tuple[frozenset[str], str]:
    """§3's release paths, parsed from the frozen spec. `(members, complaint)`."""
    spec = home / SPEC
    if not spec.is_file():
        return frozenset(), f"{SPEC} is not on disk — the reference side is absent"
    match = _RELEASE_SENTENCE.search(spec.read_text(encoding="utf-8"))
    if match is None:
        return frozenset(), (
            f"{SPEC}: no 'released on:' sentence — §3's reservation lifecycle "
            "was renamed or moved, so this gate has no reference side and an "
            "empty expected set would compare green against anything"
        )
    phrases = [part for part in match.group("paths").split(",") if part.strip()]
    return frozenset(_phrase_to_member(part) for part in phrases), ""


def _enum_members(tree: ast.Module, name: str) -> frozenset[str]:
    """Members of `class <name>(enum.Enum)`, read by AST, never by import."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return frozenset(
                target.id
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            )
    return frozenset()


def _call_defect(node: ast.AST) -> tuple[str, str] | None:
    """A call to something in `_FORBIDDEN_CALLS`, named with its line."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    called = func.id if isinstance(func, ast.Name) else ""
    if called not in _FORBIDDEN_CALLS:
        return None
    return (f"{SEAM}:{node.lineno}", f"calls {called}() — that is behaviour")


def _import_defect(node: ast.AST) -> tuple[str, str] | None:
    """An import of a module that reaches the world, named with its line."""
    if not isinstance(node, (ast.Import, ast.ImportFrom)):
        return None
    named = (
        (node.module or "") if isinstance(node, ast.ImportFrom) else node.names[0].name
    )
    root = named.split(".")[0]
    if root not in _FORBIDDEN_IMPORTS:
        return None
    return (
        f"{SEAM}:{node.lineno}",
        (
            f"imports {root} — the seam declares shape and touches nothing, so "
            "a module that reaches the world is behaviour"
        ),
    )


def _is_declaration_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """`""` when this callable is a declaration; else why it is behaviour."""
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]
    if not body:
        return ""
    if len(body) > 1:
        return f"{len(body)} statements after the docstring"
    only = body[0]
    if isinstance(only, ast.Pass) or (
        isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant)
    ):
        return ""
    if isinstance(only, ast.Return):
        for inner in ast.walk(only):
            if isinstance(inner, (ast.For, ast.While, ast.If, ast.Try)):
                return "a return carrying control flow"
        return ""
    return f"a {type(only).__name__} statement"


def behaviour_defects(tree: ast.Module) -> tuple[list[tuple[str, str]], int]:
    """Every callable that is not a declaration, and how many were classified."""
    defects: list[tuple[str, str]] = []
    seen = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen += 1
            why = _is_declaration_body(node)
            if why:
                defects.append((f"{SEAM}:{node.lineno} {node.name}", why))
            continue
        defect = _call_defect(node) or _import_defect(node)
        if defect is not None:
            defects.append(defect)
    return defects, seen


class _Sides(NamedTuple):
    """Both sides of the comparison, once each is known to be non-empty."""

    tree: ast.Module
    expected: frozenset[str]
    declared: frozenset[str]


def _gather(home: Path) -> tuple[_Sides | None, CheckResult | None]:
    """Read both sides, or say WHY the comparison cannot be made.

    Split out of `run` so every non-vacuity refusal lives in one place: §5.3's
    "an empty scope is never a PASS" is a single rule, and a reader checking that
    the gate honours it should not have to trace it through the comparison logic.
    Returns exactly one of the two members set.
    """
    seam = home / SEAM
    if not seam.is_file():
        return None, _cannot_measure(f"{SEAM} is not on disk — nothing to measure")
    tree = ast.parse(seam.read_text(encoding="utf-8"), filename=SEAM)

    expected, complaint = spec_terminal_paths(home)
    if complaint:
        return None, _cannot_measure(
            f"{complaint} (§5.3: an empty scope is never a PASS)"
        )
    if len(expected) < MIN_TERMINAL_PATHS:
        return None, _cannot_measure(
            f"§3 yielded only {len(expected)} release path(s) "
            f"({', '.join(sorted(expected)) or 'none'}), below the floor of "
            f"{MIN_TERMINAL_PATHS} — the parse stopped matching"
        )

    declared = _enum_members(tree, "TerminalPath")
    if not declared:
        return None, _cannot_measure(
            f"{SEAM}: no TerminalPath enum — the measured side is absent"
        )
    return _Sides(tree, expected, declared), None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Compare the seam against the frozen spec. Never repairs — see the reason."""
    try:
        sides, refusal = _gather(ctx.nix_home)
        if refusal is not None or sides is None:
            # `_gather` sets exactly one member. The `or` arm is unreachable and
            # is written anyway rather than as an `assert`: an assert vanishes
            # under -O, and a gate whose refusal path evaporates in optimised
            # bytecode would return a bare PASS over an unread subject.
            return refusal or _cannot_measure(
                f"{SEAM}: neither a reading nor a refusal — the gate's own "
                "pre-flight returned nothing, which is never a verdict"
            )
        tree, expected, declared = sides

        defects: list[tuple[str, str]] = []
        for missing in sorted(expected - declared):
            defects.append(
                (
                    f"{SEAM}:TerminalPath",
                    (
                        f"§3 names a release path {missing} that the seam does "
                        "not declare — a path the spec requires and the ledger "
                        "cannot report"
                    ),
                )
            )
        for extra in sorted(declared - expected):
            defects.append(
                (
                    f"{SEAM}:TerminalPath.{extra}",
                    (
                        "declared but NOT named by §3 — if the implementation "
                        "really reaches this terminal state that is a FINDING "
                        "ABOUT THE SPEC to be reported, never a member added "
                        "here to make a sweep green"
                    ),
                )
            )

        behaviour, classified = behaviour_defects(tree)
        if classified < MIN_CALLABLES:
            return _cannot_measure(
                f"{SEAM}: classified only {classified} callable(s), below the "
                f"floor of {MIN_CALLABLES} — the AST walk found almost nothing, "
                "so a clean sheet here would be about an empty scan"
            )
        defects.extend(behaviour)

        evidence = (
            f"§3 release paths {len(expected)} == TerminalPath members "
            f"{len(declared)} [{', '.join(sorted(expected))}]; "
            f"{classified} callable(s) classified, {len(behaviour)} carrying behaviour; "
            f"parsed from {SPEC} at run time, not from a constant in this gate"
        )
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
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    import sys

    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
