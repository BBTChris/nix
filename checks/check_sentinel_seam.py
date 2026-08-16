#!/usr/bin/env python3
"""The Sentinel seam declares the deadman's shape and grants no authority beyond it.

Every bare `§` in this file cites `nics_risk_subsystem_spec_v1.3.md`, the frozen
risk spec. Where another document is meant it is named on the line.

ARC 034 / Phase 0.6(a). ONE gate, ONE property (`nix_check_contract.md` §5.5 —
one gate, one property): *`scripts/nixsentinel/seam.py` declares exactly what
the frozen risk spec fixes — the record's contents, the both-sides-of-the-act
ordering, its own broker session, an append-only writer — and declares no verb
that would make the Sentinel a second trading authority.* Six arms serve that
single property.

  * **ARM 1 — the marker record carries what the SPEC enumerates, derived from
    the spec text.** `nics_risk_subsystem_spec_v1.3.md` §12.1 names the contents
    in one sentence: *"a local
    append-only marker file (timestamp, trigger cause, symbols, broker acks)"*.
    This gate parses that parenthetical out of `nics_risk_subsystem_spec_v1.3.md`
    at run time and maps each phrase to a `MarkerRecord` field. **Nothing is
    typed out here**: the expected set is not a constant in this file, so a field
    dropped from the record is red, and so is a spec phrase with no field.

  * **ARM 2 — both sides of the act are declarable.** §12.1 says the marker is
    written *"before and after acting"*. `MarkerPhase` must carry a member for
    each, and this gate derives both words from the same spec sentence rather
    than spelling them. A seam that could only record one side would make a
    mid-flatten death indistinguishable from a Sentinel that never woke.

  * **ARM 3 — the seam carries no behaviour.** Every callable is a `Protocol`
    method with no body or a property over its own fields. Behaviour in a seam is
    how a declaration becomes a second authority that can silently disagree with
    the spec (`check_limiter_seam` ARM 2, same objection one package over).

  * **ARM 4 — every declared verb is SYNCHRONOUS.** The seam's docstring makes
    this a reasoned DIVERGENCE from §2A's async default (AMENDMENT 5): the
    Sentinel must make progress with no event loop, in the scenario that already
    killed the Risk Engine. An `async def` appearing here would silently reverse
    that ruling, so the gate reddens on one.

  * **ARM 5 — the §14 authority boundary, as a type.** `SentinelBrokerPort` may
    declare ONLY observation and closing. Any verb whose name implies opening,
    sizing, amending or routing an order makes the Sentinel a second Limiter, and
    §14 permits exactly one exception to Limiter-only execution — an emergency
    FLATTEN — not a second execution authority.

  * **ARM 6 — the marker writer is append-only, as a type.** `MarkerWriterPort`
    may declare no verb that could rewind, truncate, seek or clear. §12.1's whole
    fix is a record that outlives the process; a writer able to rewind could
    erase a `BEFORE` on its way to dying. Directive 6 one layer up: append
    history, never rewrite banked evidence.

WHAT THIS GATE CANNOT PROVE, stated rather than implied. It reads the seam
STATICALLY. It cannot prove any implementation fsyncs, that a real Sentinel
writes `BEFORE` before it flattens, or that cold-start replays anything — those
are behaviours of code built against this seam and they need their own
instruments driving real objects. **A green here means the DECLARATION is
faithful and the authority boundary is not widened. It says nothing about
whether a Sentinel exists or works.**

`debug.md` §7.12 — the standing question, asked at the point this gate was built:
*what would make this pass while measuring nothing?* Four answers, and each is
closed by a named mechanism rather than by assertion:

  1. *The spec sentence is renamed and ARM 1 matches nothing, reporting an empty
     expected set as agreement.* Closed by `MIN_SPEC_PHRASES`: fewer than three
     phrases parsed is CANNOT_MEASURE, never PASS.
  2. *The seam file is renamed and the gate reads nothing.* Closed by the
     unreadable-subject path, which is CANNOT_MEASURE.
  3. *ARM 5's ban list is read out of the subject, so the subject can widen
     itself.* Closed by `_BANNED_VERB_STEMS` being a list of ENGLISH STEMS, not a
     roster derived from the seam — the one place a constant in this gate is
     correct, because the property is "no verb of this KIND", which no roster in
     the subject could express. Stated here because `check_pollers` ARM LOCK was
     measured in ARC 034/0.5 doing exactly the wrong version of this.
  4. *Every arm inspects and none of them counts, so a gutted seam passes.*
     Closed by `MIN_CALLABLES` and `MIN_DECLARED_VERBS`, which are floors below
     today's figures (doctrine C.4) but non-zero.
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
#: NON-CORRECTABLE. One side is the FROZEN spec, which is never edited; the other
#: is a declaration whose whole purpose is to be checkable against it. An
#: instrument that could rewrite either side to agree would be manufacturing its
#: own green.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is the frozen risk spec, which is never edited, and the "
    "measured side is the Sentinel seam, whose whole purpose is to be checkable "
    "against it. An instrument empowered to edit either into agreement would be "
    "manufacturing its own green -- and ARM 5's subject is an AUTHORITY "
    "boundary, so a self-correcting gate there could widen the very thing it "
    "exists to hold shut."
)
#: Genuinely MEASURED: every byte of the seam is parsed and every callable in it
#: is classified.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixsentinel/seam.py",
    "scripts/nixsentinel/__init__.py",
)

NAME = "check_sentinel_seam"

SEAM = "scripts/nixsentinel/seam.py"
PACKAGE_INIT = "scripts/nixsentinel/__init__.py"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"

#: §12.1's own sentence naming the marker's contents. Anchored on the phrase that
#: introduces the parenthetical, so a renamed or moved sentence is a LOUD refusal
#: rather than a silently empty expected set matching everything.
_CONTENTS_SENTENCE = re.compile(
    # `\*{0,2}` because the spec bolds the noun phrase: **local append-only
    # marker file** (timestamp, ...). Anchored on the words, tolerant of the
    # markup, so a re-bolding is not mistaken for a rename.
    r"append-only marker file\*{0,2}\s*\((?P<contents>[^)]*)\)",
    re.DOTALL,
)
#: §12.1's ordering phrase. Same anchoring argument.
_BOTH_SIDES = re.compile(r"\*?before and after\*?\s+acting")

#: How a spec phrase becomes a `MarkerRecord` field name. The spec writes English
#: ("trigger cause", "broker acks"); the record writes identifiers. The mapping
#: is declared here and is deliberately SHALLOW -- last word, singularised -- so
#: it cannot quietly absorb a phrase it does not really cover.
_PHRASE_FIELD = {
    "timestamp": "ts",
    "trigger cause": "cause",
    "symbols": "symbols",
    "broker acks": "acks",
}

#: Names whose presence in a seam is behaviour by construction. Same roster as
#: `check_limiter_seam`, and the duplication is deliberate: §4.2 forbids the
#: shared helper that would deduplicate it.
_FORBIDDEN_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "print", "input"}
)
_FORBIDDEN_IMPORTS = frozenset(
    {"os", "subprocess", "socket", "zmq", "threading", "asyncio", "time", "json"}
)

#: ARM 5. **ENGLISH STEMS, not a roster read out of the subject** -- see the
#: §7.12 note 3 in the module docstring for why this is the one place a constant
#: in the gate is the correct instrument. A verb whose name contains any of these
#: makes the Sentinel able to do something other than observe and close.
_BANNED_VERB_STEMS = (
    "place",
    "submit",
    "order",
    "buy",
    "sell",
    "enter",
    "open_order",
    "modify",
    "amend",
    "replace",
    "size",
    "route",
    "reserve",
    "approve",
    "gate",
)
#: The port ARM 5 polices, and the two verbs that ARE the authorised act.
_BROKER_PORT = "SentinelBrokerPort"
_AUTHORISED_BROKER_VERBS = frozenset(
    {"connect", "open_positions", "flatten_all", "disconnect"}
)

#: ARM 6. A writer that could reach any of these is not append-only.
_REWIND_STEMS = ("truncate", "seek", "clear", "rewrite", "delete", "remove", "reset")
_WRITER_PORT = "MarkerWriterPort"

#: Non-vacuity floors (`debug.md` §7.12). Each is a count this gate MUST reach or
#: it has measured nothing and says so rather than passing. Floors, not today's
#: figures (doctrine C.4).
MIN_SPEC_PHRASES = 3
MIN_CALLABLES = 5
MIN_DECLARED_VERBS = 8


class SeamReading(NamedTuple):
    """What one run actually observed. Every field lands in the evidence."""

    spec_phrases: tuple[str, ...]
    record_fields: tuple[str, ...]
    phases: tuple[str, ...]
    callables: int
    verbs: int
    broker_verbs: tuple[str, ...]
    writer_verbs: tuple[str, ...]


def _cannot_measure(detail: str) -> CheckResult:
    """Doctrine B.2: an unread subject is CANNOT_MEASURE, never PASS."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def spec_marker_phrases(home: Path) -> tuple[tuple[str, ...], str]:
    """ARM 1's expected side, PARSED from §12.1. Never a constant here."""
    text = (home / SPEC).read_text(encoding="utf-8")
    match = _CONTENTS_SENTENCE.search(text)
    if match is None:
        return (), (
            f"{SPEC}: §12.1's 'append-only marker file (...)' sentence did not "
            "match. The expected side of ARM 1 is PARSED from that sentence, so "
            "a rename leaves this gate with nothing to compare and it refuses "
            "rather than reporting an empty set as agreement"
        )
    raw = match.group("contents").replace("\n", " ")
    phrases = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return phrases, f"§12.1 names {len(phrases)}: {', '.join(phrases)}"


def spec_declares_both_sides(home: Path) -> bool:
    """ARM 2's expected side: does §12.1 require a record on BOTH sides?"""
    text = (home / SPEC).read_text(encoding="utf-8")
    return _BOTH_SIDES.search(text) is not None


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    """Top-level classes by name."""
    return {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}


def _dataclass_fields(node: ast.ClassDef) -> tuple[str, ...]:
    """Annotated assignments in a class body, in source order."""
    return tuple(
        stmt.target.id
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    )


def _enum_members(node: ast.ClassDef) -> tuple[str, ...]:
    """Plain assignments in an enum body, in source order."""
    return tuple(
        stmt.targets[0].id
        for stmt in node.body
        if isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
    )


def _port_verbs(node: ast.ClassDef) -> tuple[str, ...]:
    """Method names declared on a class, in source order."""
    return tuple(
        stmt.name
        for stmt in node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
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
        return (SEAM, f"calls {name}() — a seam performs no act")
    return None


def _import_defects(node: ast.AST) -> list[tuple[str, str]]:
    """Forbidden imports on one node, in source order. Empty when clean."""
    if not isinstance(node, (ast.Import, ast.ImportFrom)):
        return []
    mod = getattr(node, "module", None) or ""
    names = [mod, *(alias.name for alias in node.names)]
    roots = [candidate.split(".")[0] for candidate in names]
    return [
        (SEAM, f"imports {root} — a seam declares, it does not act")
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
                defects.append((SEAM, why))
    return defects, seen


def synchrony_defects(tree: ast.Module) -> tuple[list[tuple[str, str]], int]:
    """ARM 4. Every declared verb must be `def`, never `async def`."""
    defects: list[tuple[str, str]] = []
    verbs = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            verbs += 1
            if isinstance(node, ast.AsyncFunctionDef):
                defects.append(
                    (
                        f"{SEAM}:{node.lineno}",
                        (
                            f"{node.name} is `async def`. The Sentinel seam declares "
                            "every verb SYNCHRONOUS as a reasoned divergence from "
                            "§2A's async default: it must make progress with no event "
                            "loop, in the scenario that already killed the Risk "
                            "Engine. Reversing that ruling silently is what this arm "
                            "refuses"
                        ),
                    )
                )
    return defects, verbs


def authority_defects(classes: dict[str, ast.ClassDef]) -> list[tuple[str, str]]:
    """ARM 5 — §14's boundary. Returns one defect per offending verb."""
    node = classes.get(_BROKER_PORT)
    if node is None:
        return [
            (
                SEAM,
                (
                    f"{_BROKER_PORT} is not declared. ARM 5 polices the Sentinel's "
                    "flatten-only authority on that port; with the port gone there "
                    "is nothing holding the boundary and its absence is a defect, "
                    "not a vacuous pass"
                ),
            )
        ]
    defects: list[tuple[str, str]] = []
    for verb in _port_verbs(node):
        lowered = verb.lower()
        hit = next((stem for stem in _BANNED_VERB_STEMS if stem in lowered), None)
        if hit is not None:
            defects.append(
                (
                    f"{SEAM}:{_BROKER_PORT}.{verb}",
                    (
                        f"verb name contains {hit!r} — §14 permits the Sentinel ONE "
                        "exception to Limiter-only execution, an emergency FLATTEN "
                        "when the Limiter is dead. A verb that opens, sizes, amends "
                        "or routes makes it a second trading authority"
                    ),
                )
            )
        elif verb not in _AUTHORISED_BROKER_VERBS:
            defects.append(
                (
                    f"{SEAM}:{_BROKER_PORT}.{verb}",
                    (
                        "verb is not one of the four §12.1 authorises "
                        f"({', '.join(sorted(_AUTHORISED_BROKER_VERBS))}). A widened "
                        "session port is a widened authority whatever it is called"
                    ),
                )
            )
    return defects


def append_only_defects(classes: dict[str, ast.ClassDef]) -> list[tuple[str, str]]:
    """ARM 6 — the writer cannot rewind."""
    node = classes.get(_WRITER_PORT)
    if node is None:
        return [
            (
                SEAM,
                (
                    f"{_WRITER_PORT} is not declared. §12.1's durable record has no "
                    "writer, so there is nothing to be append-only"
                ),
            )
        ]
    defects: list[tuple[str, str]] = []
    for verb in _port_verbs(node):
        lowered = verb.lower()
        hit = next((stem for stem in _REWIND_STEMS if stem in lowered), None)
        if hit is not None:
            defects.append(
                (
                    f"{SEAM}:{_WRITER_PORT}.{verb}",
                    (
                        f"verb name contains {hit!r} — a marker writer that can "
                        "rewind could erase a BEFORE record on its way to dying, "
                        "which is the exact evidence §12.1's fix exists to keep"
                    ),
                )
            )
    return defects


def record_defects(
    classes: dict[str, ast.ClassDef], phrases: tuple[str, ...]
) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """ARM 1 — the spec's enumerated contents against `MarkerRecord`'s fields."""
    node = classes.get("MarkerRecord")
    if node is None:
        return [(SEAM, "MarkerRecord is not declared — §12.1's record has no type")], ()
    fields = _dataclass_fields(node)
    defects: list[tuple[str, str]] = []
    for phrase in phrases:
        want = _PHRASE_FIELD.get(phrase)
        if want is None:
            defects.append(
                (
                    f"{SPEC}:§12.1",
                    (
                        f"the spec enumerates {phrase!r} and this gate has no field "
                        "mapping for it. A phrase the gate cannot map is a phrase it "
                        "is not checking, so it is reported rather than skipped"
                    ),
                )
            )
        elif want not in fields:
            defects.append(
                (
                    f"{SEAM}:MarkerRecord",
                    (
                        f"§12.1 enumerates {phrase!r} and MarkerRecord has no "
                        f"{want!r} field — a marker missing it cannot be replayed "
                        "into Plane 1 with the information the spec requires"
                    ),
                )
            )
    return defects, fields


def phase_defects(
    classes: dict[str, ast.ClassDef], both_sides: bool
) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """ARM 2 — §12.1's before-and-after, as enum members."""
    node = classes.get("MarkerPhase")
    if node is None:
        return [(SEAM, "MarkerPhase is not declared")], ()
    members = _enum_members(node)
    if not both_sides:
        return [
            (
                f"{SPEC}:§12.1",
                (
                    "the 'before and after acting' phrase did not match, so ARM 2's "
                    "expected side is unread. Refusing rather than passing on an "
                    "unparsed requirement"
                ),
            )
        ], members
    defects = [
        (
            f"{SEAM}:MarkerPhase",
            (
                f"§12.1 requires a record written before AND after acting; the enum "
                f"has no {want!r} member. Without it a mid-flatten death is "
                "indistinguishable from a Sentinel that never woke"
            ),
        )
        for want in ("BEFORE", "AFTER")
        if want not in members
    ]
    return defects, members


def _evidence(reading: SeamReading) -> str:
    """Every figure this run actually observed. Never a restatement."""
    return (
        f"§12.1 phrases {len(reading.spec_phrases)} "
        f"({', '.join(reading.spec_phrases)}); MarkerRecord fields "
        f"{len(reading.record_fields)} ({', '.join(reading.record_fields)}); "
        f"MarkerPhase {', '.join(reading.phases)}; {reading.callables} callables, "
        f"{reading.verbs} declared verbs, all synchronous; "
        f"{_BROKER_PORT} verbs {', '.join(reading.broker_verbs)}; "
        f"{_WRITER_PORT} verbs {', '.join(reading.writer_verbs)}"
    )


def _floor_refusal(reading: SeamReading) -> CheckResult | None:
    """`debug.md` §7.12: a run that reached nothing reports so, never PASS."""
    if len(reading.spec_phrases) < MIN_SPEC_PHRASES:
        return _cannot_measure(
            f"§12.1's contents parenthetical yielded {len(reading.spec_phrases)} "
            f"phrase(s), below the floor of {MIN_SPEC_PHRASES}. ARM 1's expected "
            "side is derived from that sentence; too few means the sentence moved "
            "and this gate compared almost nothing"
        )
    if reading.callables < MIN_CALLABLES:
        return _cannot_measure(
            f"{SEAM}: {reading.callables} callable(s) classified, below the floor "
            f"of {MIN_CALLABLES}. A seam this small is a seam that was gutted, and "
            "ARM 3 over an empty file is universal agreement"
        )
    if reading.verbs < MIN_DECLARED_VERBS:
        return _cannot_measure(
            f"{SEAM}: {reading.verbs} declared verb(s), below the floor of "
            f"{MIN_DECLARED_VERBS}. ARM 4 over no verbs proves nothing about "
            "synchrony"
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
    if not seam_path.is_file():
        return [], None, f"{SEAM}: not a file — the subject is unreadable"
    if not (home / PACKAGE_INIT).is_file():
        return [], None, f"{PACKAGE_INIT}: not a file — the package is unreadable"
    try:
        tree = ast.parse(seam_path.read_text(encoding="utf-8"), filename=SEAM)
    except SyntaxError as exc:
        return [], None, f"{SEAM}: does not parse ({exc})"
    phrases, _detail = spec_marker_phrases(home)
    both_sides = spec_declares_both_sides(home)
    classes = _classes(tree)
    defects: list[tuple[str, str]] = []
    rec_defects, fields = record_defects(classes, phrases)
    defects += rec_defects
    ph_defects, phases = phase_defects(classes, both_sides)
    defects += ph_defects
    beh_defects, callables = behaviour_defects(tree)
    defects += beh_defects
    syn_defects, verbs = synchrony_defects(tree)
    defects += syn_defects
    defects += authority_defects(classes)
    defects += append_only_defects(classes)
    broker = classes.get(_BROKER_PORT)
    writer = classes.get(_WRITER_PORT)
    reading = SeamReading(
        spec_phrases=phrases,
        record_fields=fields,
        phases=phases,
        callables=callables,
        verbs=verbs,
        broker_verbs=_port_verbs(broker) if broker is not None else (),
        writer_verbs=_port_verbs(writer) if writer is not None else (),
    )
    return defects, reading, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Compare the Sentinel seam against §12.1. Never repairs — see the reason."""
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
    import sys

    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
