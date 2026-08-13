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
import dataclasses
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
#: The amendment ledger. The frozen spec is never edited, so a ruling that adds a
#: terminal path lands here and the gate must read BOTH to know the effective set.
AMENDMENTS = "docs/SPEC-AMENDMENTS.md"

#: The §3 sentence carrying the release paths. Anchored on "released on:" so the
#: gate fails loud if the sentence is renamed or moved, rather than silently
#: matching nothing and reporting an empty expected set as agreement.
_RELEASE_SENTENCE = re.compile(r"released on:(?P<paths>.*?)\.\s", re.DOTALL)

#: How a spec phrase becomes an enum member: take the leading words before any
#: parenthetical or trailing noun, join with `_`. "pending-timeout resolution"
#: -> PENDING_TIMEOUT; "fill (converts to open-margin)" -> FILL.
_TRAILING_NOUN = ("resolution", "cancellation")

#: The amendment ledger's machine-readable surface: a table row whose label is
#: `terminal-path additions`. Anchored on the label so a renamed row is a
#: complaint rather than a silently empty addition set.
_ADDITIONS_ROW = re.compile(
    r"^\|\s*terminal-path additions\s*\|(?P<members>[^|]*)\|\s*$", re.MULTILINE
)
#: Members inside the row, each in backticks. Deliberately NOT exemplified with
#: a real member name: the suite asserts no member appears as a literal in this
#: gate's source, because an expected side the gate spells is a gate agreeing
#: with itself.
_CODE_SPAN = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

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
#: The seam declares four ports; the floor is below that on purpose (doctrine
#: C.4 — a floor, not today's count) but non-zero, because a docstring whose
#: declaration section was renamed would otherwise read as universal agreement.
MIN_DECLARED_VERBS = 6

#: The three disagreements ARM 3 can report, as constants so the loop that finds
#: them stays a loop and not a wall of prose.
_GONE_PORT = (
    "named in the seam's sync/async declaration and NOT DEFINED in the seam — "
    "the declaration governs a port that is gone"
)
_GONE_VERB = (
    "declared SYNCHRONOUS in the seam's own docstring and absent from the class "
    "— the declaration describes a verb nothing has"
)
_ASYNC_VERB = (
    "is `async def` while the seam DECLARES it synchronous — an awaitable gate "
    "verb is a suspension point inside one authoritative pass, which is the "
    "fill-vs-tick race §5 eliminates by construction"
)
_UNSPECCED_PATH = (
    "declared but NOT named by §3 — if the implementation really reaches this "
    "terminal state that is a FINDING ABOUT THE SPEC to be reported, never a "
    "member added here to make a sweep green"
)
_MODULE_ASYNC = (
    "is `async def` at module scope — the seam declares no asynchronous verb, "
    "and the one async surface the Limiter owns is declared in the broker seam, "
    "not restated here"
)


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def _phrase_to_member(phrase: str) -> str:
    """One spec phrase -> the enum member it names. Pure text, no lookup table."""
    text = re.sub(r"\(.*?\)", " ", phrase).strip().lower()
    words = [word for word in re.split(r"[\s\-]+", text) if word]
    while words and words[-1] in _TRAILING_NOUN:
        words.pop()
    return "_".join(words).upper()


def amended_terminal_paths(home: Path) -> tuple[frozenset[str], str]:
    """Terminal paths ADDED by a ruling in `SPEC-AMENDMENTS.md`. Parsed, never typed.

    ARC 029 / 0.4, and the mechanism had to exist before SPEC-A7 could be obeyed.

    **The frozen spec is not edited — that is the standing rule — so an amendment
    that adds a terminal path had nowhere to be seen from.** `spec_terminal_paths`
    read `nics_risk_subsystem_spec_v1.3.md` and nothing else, which left SPEC-A7's
    `HALT_ONSET` in an impossible position: adding the member reddens ARM 1 as
    *"declared but NOT named by §3"* forever, and the only way to green it would be
    to edit the frozen document. A gate that can only be satisfied by breaking a
    standing rule is a gate that will be broken instead.

    So the reference side is now the EFFECTIVE roster: the frozen sentence unioned
    with every amendment's additions. The additions are read out of the ledger's
    own table row — a `terminal-path additions` row — so the ledger
    stays the single source and a future ruling needs no code change here. A
    malformed row is a COMPLAINT, never a silent skip: an amendment nobody can
    parse must not read as an amendment that adds nothing.
    """
    ledger = home / AMENDMENTS
    if not ledger.is_file():
        return frozenset(), (
            f"{AMENDMENTS} is not on disk — amendments to the terminal set could "
            "not be read, and a gate that cannot see them would report the frozen "
            "roster as the whole truth"
        )
    found: set[str] = set()
    for row in _ADDITIONS_ROW.finditer(ledger.read_text(encoding="utf-8")):
        members = _CODE_SPAN.findall(row.group("members"))
        if not members:
            return frozenset(), (
                f"{AMENDMENTS}: a 'terminal-path additions' row names no member in "
                f"backticks: {row.group('members').strip()!r} — an unparseable "
                "amendment must not read as one that adds nothing"
            )
        found.update(member.strip().upper() for member in members)
    return frozenset(found), ""


def spec_terminal_paths(home: Path) -> tuple[frozenset[str], str]:
    """The EFFECTIVE release-path roster. `(members, complaint)`.

    §3's frozen sentence UNIONED with `SPEC-AMENDMENTS.md`'s additions — see
    `amended_terminal_paths` for why the union exists. Both sources must be
    readable; either one failing is a complaint, because a roster assembled from
    half its sources compares green against the wrong set rather than no set.
    """
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
    amended, complaint = amended_terminal_paths(home)
    if complaint:
        return frozenset(), complaint
    phrases = [part for part in match.group("paths").split(",") if part.strip()]
    frozen = frozenset(_phrase_to_member(part) for part in phrases)
    return frozen | amended, ""


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


#: A `Class.method` named inside the seam's own module docstring.
_DECLARED_VERB = re.compile(r"`(?P<cls>[A-Z][A-Za-z0-9]*)\.(?P<method>[a-z_]+)`")
#: A Port class named inside that docstring, with no method attached.
_DECLARED_PORT = re.compile(r"`(?P<cls>[A-Z][A-Za-z0-9]*Port)`")


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }


def synchrony_defects(tree: ast.Module) -> tuple[list[tuple[str, str]], int]:
    """Is the seam's SYNC/ASYNC DECLARATION true of the seam's own code?

    ARM 3, and it exists because ARC 028's sub-agent B REFUTED the claim that
    this gate guarded it. Measured on `tmp_path` copies through these very bytes:
    all four `ReservationLedgerPort` verbs rewritten `def` -> `async def` PASSED,
    with empty detail. The seam's most-argued property — every gate verb is
    synchronous, because §5's single-threaded loop eliminates fill-vs-tick races
    by construction and an awaitable `evaluate` is a declared suspension point
    mid-pass — was guarded by prose alone. Prose is what this gate exists to stop
    being the guarantee.

    **The reference side is the seam's OWN DOCSTRING, and that is not circular.**
    The docstring is the DECLARATION and the code is the SUBJECT; they are
    written by different acts and drift apart in exactly the way that matters. A
    verb the declaration names and the code has dropped is red; a verb the code
    has made awaitable is red. What it cannot catch is a declaration and a code
    change made together and consistently — which is a decision, visible on the
    diff, not a drift.
    """
    doc = ast.get_docstring(tree) or ""
    classes = _classes(tree)
    named, missing = _declared_verbs(doc, classes)
    defects = [(f"{SEAM}:{cls}", _GONE_PORT) for cls in missing]
    checked = 0
    for cls, method in sorted(named):
        node = classes[cls]
        found = [
            item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == method
        ]
        if not found:
            defects.append((f"{SEAM}:{cls}.{method}", _GONE_VERB))
            continue
        checked += 1
        defects.extend(
            (f"{SEAM}:{item.lineno} {cls}.{method}", _ASYNC_VERB)
            for item in found
            if isinstance(item, ast.AsyncFunctionDef)
        )
    defects.extend(_module_scope_async(tree, classes))
    return defects, checked


def _declared_verbs(
    doc: str, classes: dict[str, ast.ClassDef]
) -> tuple[set[tuple[str, str]], list[str]]:
    """`(Class, method)` pairs the declaration governs, and classes it lost.

    A port named BARE contributes every method it defines; a port named as
    `Class.verb` contributes that verb. Both spellings appear in the seam's
    declaration and each reaches the code by a different path — which is exactly
    where the first repair leaked: it handled one and stepped over the other.
    """
    named = {(m.group("cls"), m.group("method")) for m in _DECLARED_VERB.finditer(doc)}
    ports = {m.group("cls") for m in _DECLARED_PORT.finditer(doc)}
    for cls in ports & set(classes):
        named.update(
            (cls, item.name)
            for item in classes[cls].body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    # Parenthesised deliberately: `-` binds tighter than `|`, and the
    # unparenthesised spelling reported EVERY declared port as missing.
    missing = sorted(({cls for cls, _ in named} | ports) - set(classes))
    return {(cls, method) for cls, method in named if cls in classes}, missing


def _module_scope_async(
    tree: ast.Module, classes: dict[str, ast.ClassDef]
) -> list[tuple[str, str]]:
    """`async def` outside any class. The seam declares no asynchronous verb."""
    inside = {id(item) for cls in classes.values() for item in cls.body}
    return [
        (f"{SEAM}:{node.lineno} {node.name}", _MODULE_ASYNC)
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and id(node) not in inside
    ]


#: The §3 line naming the protective-exit trigger set, ARC 029 / 0.6. Anchored on
#: "Limiter (" at the head of §3's EXIT / PROTECTIVE PATH block so a renamed or
#: moved block is a complaint rather than an empty expected set.
_EXIT_TRIGGER_LINE = re.compile(r"^Limiter \((?P<triggers>[^)]*)\)", re.MULTILINE)

#: ARM 5's reference, and the honest note that goes with it.
#:
#: **This IS a constant in the gate, unlike ARM 1's roster, and the difference is
#: stated rather than glossed.** §3 enumerates its release paths and its exit
#: triggers in sentences a parser can read, so those arms derive. It does NOT
#: enumerate the fields of a stop record or a survival reading — no sentence
#: exists to parse — so the requirement below is HUMAN-DERIVED from the cited
#: invariant and carries that citation in its own text.
#:
#: It earns its place because ARC 028 measured the gap it closes: the seam gate
#: passed on a DELETED FIELD. Every entry names the invariant that would be
#: unprovable if the field vanished, so a reader can check the derivation rather
#: than trust it.
_REQUIRED_FIELDS: tuple[tuple[str, str, str], ...] = (
    (
        "SurvivalReading",
        "net_liq",
        "§15 C2 — survival is watched on NET-LIQ; the broker liquidates on it",
    ),
    (
        "SurvivalReading",
        "cash",
        (
            "§15 C2 — sizing is computed on CASH, and conflating the two is the "
            "defect the two fields exist to make impossible"
        ),
    ),
    (
        "StopState",
        "initial_distance_ticks",
        "§4 — the GO carries stop intent as a tick DISTANCE, never a price",
    ),
    (
        "StopState",
        "trail_distance_ticks",
        "§4 — trailing needs a second distance, or activation cannot be computed",
    ),
    (
        "StopState",
        "anchor",
        (
            "§4 — conversion happens ONCE at confirmed fill; without the anchor a "
            "re-conversion could use a different price and no field would disagree"
        ),
    ),
    (
        "StopState",
        "activated",
        (
            "§4 — the trailing latch. Recomputed each tick it could de-activate on "
            "a retrace and give ground back, which a ratchet must never do"
        ),
    ),
    # §3's FULL FINANCIAL-PICTURE PUBLISH enumerates these by name, and ARC 029 /
    # 0.6 measured that deleting one was SILENT — the plant matrix aimed at
    # BrokerTruth.positions hit FinancialPicture.positions first and NOTHING
    # reddened. That is ARC 028's deleted-field gap living in the type this seam
    # has carried since it was written, not just in the exit half added today.
    (
        "FinancialPicture",
        "balance",
        (
            "§3 — the picture publishes account BALANCE (live) as part of ONE "
            "atomic snapshot; without it a consumer computes headroom off a "
            "balance it fetched separately, which the atomicity rule forbids"
        ),
    ),
    (
        "FinancialPicture",
        "positions",
        (
            "§3 — per-position rows keyed by trade_id, every position in whatever "
            "state it is in, are half of what makes the snapshot complete"
        ),
    ),
    (
        "FinancialPicture",
        "sum_open_margin",
        "§3 — Σ open margin is published, never recomputed by a consumer",
    ),
    (
        "FinancialPicture",
        "sum_reservations",
        "§3 — Σ reservations is a §11.3 running aggregate the Allocator mirrors",
    ),
    (
        "FinancialPicture",
        "committed",
        "§3 — committed liquidity is published as a field",
    ),
    (
        "FinancialPicture",
        "deployable",
        "§3 — uncommitted (deployable) liquidity is the figure sizing reads",
    ),
    (
        "BrokerTruth",
        "positions",
        "§4 — cold start pulls the true open-position SET as ground truth",
    ),
    (
        "BrokerTruth",
        "balance",
        (
            "§4 — balance and positions come from ONE poll; two reads is the "
            "stale-balance tear §3's atomicity rule forbids"
        ),
    ),
)


def spec_exit_triggers(home: Path) -> tuple[frozenset[str], str]:
    """§3's protective-exit trigger set, parsed from the frozen spec (ARM 4)."""
    spec = home / SPEC
    if not spec.is_file():
        return frozenset(), f"{SPEC} is not on disk — the reference side is absent"
    match = _EXIT_TRIGGER_LINE.search(spec.read_text(encoding="utf-8"))
    if match is None:
        return frozenset(), (
            f"{SPEC}: §3's EXIT / PROTECTIVE PATH line was renamed or moved, so "
            "this arm has no reference side and an empty expected set would "
            "compare green against anything"
        )
    parts = [part for part in match.group("triggers").split("/") if part.strip()]
    return frozenset(_phrase_to_member(part) for part in parts), ""


def exit_trigger_defects(
    expected: frozenset[str], declared: frozenset[str]
) -> list[tuple[str, str]]:
    """ARM 4's comparison, both directions, each naming the member."""
    defects = [
        (
            f"{SEAM}:FlattenTrigger",
            (
                f"§3 names a protective-exit trigger {missing} that the seam "
                "does not declare — a trigger the spec requires and the Limiter "
                "cannot name"
            ),
        )
        for missing in sorted(expected - declared)
    ]
    defects.extend(
        (f"{SEAM}:FlattenTrigger.{extra}", _UNSPECCED_PATH)
        for extra in sorted(declared - expected)
    )
    return defects


def required_field_defects(tree: ast.Module) -> list[tuple[str, str]]:
    """ARM 5: a declared type is missing a field its invariant needs.

    ARC 028's measured gap — the seam gate passed on a DELETED FIELD — and the
    reason this arm exists at all. A field removed from a frozen value type is a
    silent change: nothing fails to import, no verdict changes shape, and the
    invariant it carried simply stops being expressible.
    """
    present: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            present[node.name] = {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    defects: list[tuple[str, str]] = []
    for cls, field_name, citation in _REQUIRED_FIELDS:
        if cls not in present:
            defects.append((f"{SEAM}:{cls}", f"declared type is GONE — {citation}"))
        elif field_name not in present[cls]:
            defects.append(
                (
                    f"{SEAM}:{cls}.{field_name}",
                    f"required field is absent — {citation}",
                )
            )
    return defects


# Eight fields because five arms measured eight things. The threshold is about
# behavioural classes accreting state; this is a frozen record with no behaviour,
# and dropping a field to satisfy a count would LOSE A MEASUREMENT from the
# verdict's evidence — the same reasoning seam.py carries for its value types.
@dataclasses.dataclass(frozen=True)
class SeamReading:  # pylint: disable=too-many-instance-attributes
    """Everything the five arms measured, in one record.

    A record rather than seven arguments threaded through `run`: the arms grew
    from three to five in ARC 029 / 0.6 and both the argument count and the local
    count went over their ceilings in the same motion. Those ceilings are a real
    constraint on how much one function may hold, and the honest answer to
    "too many locals" is fewer things, not a wider limit.
    """

    expected: frozenset[str]
    declared: frozenset[str]
    triggers: frozenset[str]
    declared_triggers: frozenset[str]
    classified: int
    behaviour: list[tuple[str, str]]
    verbs: int
    synchrony: list[tuple[str, str]]


def _measure(
    home: Path, sides: tuple[ast.Module, frozenset[str], frozenset[str]]
) -> tuple[list[tuple[str, str]], SeamReading | None, CheckResult | None]:
    """Run all five arms. `(defects, reading, refusal)`; one of the last two is set.

    Extracted from `run` in ARC 029 / 0.6. Five arms produce eight measurements,
    and `run` went over the complexity, local-variable and return-count ceilings
    as they landed. The honest response to "too many locals" is fewer things in
    one place, not a wider limit.
    """
    tree, expected, declared = sides
    defects = terminal_path_defects(expected, declared)

    exit_defects, counts, exit_refusal = exit_arms(home, tree)
    if exit_refusal is not None:
        return defects, None, exit_refusal
    defects.extend(exit_defects)

    behaviour, classified = behaviour_defects(tree)
    defects.extend(behaviour)
    synchrony, verbs = synchrony_defects(tree)
    defects.extend(synchrony)

    floor = _floor_refusal(classified, verbs, defects)
    if floor is not None:
        return defects, None, floor

    return (
        defects,
        SeamReading(
            expected=expected,
            declared=declared,
            triggers=counts[0],
            declared_triggers=counts[1],
            classified=classified,
            behaviour=behaviour,
            verbs=verbs,
            synchrony=synchrony,
        ),
        None,
    )


def _floor_refusal(
    classified: int, verbs: int, defects: list[tuple[str, str]]
) -> CheckResult | None:
    """The two non-vacuity floors, or `None`. Extracted in ARC 029 / 0.6.

    **The verb floor fires ONLY when nothing was positively observed**, and that
    condition is load-bearing rather than cosmetic: §17 says a positively-observed
    defect outranks masking, and the first spelling of this rule returned
    CANNOT_MEASURE while THROWING AWAY defects arms 1 and 2 had already found —
    a gate discarding its own measurement in order to report that it could not
    measure.
    """
    if classified < MIN_CALLABLES:
        return _cannot_measure(
            f"{SEAM}: classified only {classified} callable(s), below the "
            f"floor of {MIN_CALLABLES} — the AST walk found almost nothing, "
            "so a clean sheet here would be about an empty scan"
        )
    if verbs < MIN_DECLARED_VERBS and not defects:
        return _cannot_measure(
            f"{SEAM}: the sync/async declaration reached only {verbs} verb(s), "
            f"below the floor of {MIN_DECLARED_VERBS} — the docstring's "
            "declaration section was renamed or the ports are gone, and a "
            "clean sheet would be about an empty reading"
        )
    return None


def _evidence(reading: SeamReading) -> str:
    """The verdict's evidence line, built in one place.

    Extracted from `run` in ARC 029 / 0.6 to keep it under the complexity and
    local-variable ceilings — the arms grew from three to five and the line
    naming what each measured grew with them.

    **The relation is COMPUTED, never spelled.** ARC 029 / 0.4 measured this line
    printing `6 == TerminalPath members 5` on a run that was RED for exactly that
    inequality — a verdict's own evidence asserting the agreement the verdict was
    denying, in the one place a reader looks when told something is wrong.
    """
    relation = "==" if len(reading.expected) == len(reading.declared) else "!="
    return (
        f"§3 release paths {len(reading.expected)} {relation} TerminalPath members "
        f"{len(reading.declared)} [{', '.join(sorted(reading.expected))}]; "
        f"{reading.classified} callable(s) classified, "
        f"{len(reading.behaviour)} carrying behaviour; "
        f"{reading.verbs} verb(s) held against the seam's own sync/async "
        f"declaration, {len(reading.synchrony)} disagreeing; "
        f"§3 exit triggers {len(reading.triggers)} vs FlattenTrigger "
        f"{len(reading.declared_triggers)}; {len(_REQUIRED_FIELDS)} required field(s) "
        "held against their cited invariants; "
        f"parsed at run time from {SPEC} unioned with {AMENDMENTS}, not from "
        "a constant in this gate"
    )


def exit_arms(
    home: Path, tree: ast.Module
) -> tuple[
    list[tuple[str, str]], tuple[frozenset[str], frozenset[str]], CheckResult | None
]:
    """ARM 4 and ARM 5 together. `(defects, (expected, declared), refusal)`.

    One helper for two arms because they share a refusal shape: either can find
    its reference side missing, and in both cases the honest verdict is
    CANNOT_MEASURE rather than a comparison against an empty set.
    """
    triggers, complaint = spec_exit_triggers(home)
    if complaint:
        return [], (frozenset(), frozenset()), _cannot_measure(complaint)
    declared = _enum_members(tree, "FlattenTrigger")
    if not declared:
        return (
            [],
            (frozenset(), frozenset()),
            _cannot_measure(
                f"{SEAM}: no FlattenTrigger enum — §3's protective-exit trigger "
                "set has no measured side"
            ),
        )
    defects = exit_trigger_defects(triggers, declared)
    defects.extend(required_field_defects(tree))
    return defects, (triggers, declared), None


def terminal_path_defects(
    expected: frozenset[str], declared: frozenset[str]
) -> list[tuple[str, str]]:
    """ARM 1's comparison, both directions, each naming the member."""
    defects = [
        (
            f"{SEAM}:TerminalPath",
            (
                f"§3 names a release path {missing} that the seam does not "
                "declare — a path the spec requires and the ledger cannot report"
            ),
        )
        for missing in sorted(expected - declared)
    ]
    defects.extend(
        (f"{SEAM}:TerminalPath.{extra}", _UNSPECCED_PATH)
        for extra in sorted(declared - expected)
    )
    return defects


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
        defects, reading, refusal = _measure(ctx.nix_home, sides)
        if refusal is not None:
            return refusal
        if reading is None:  # pragma: no cover - `_measure` sets exactly one
            return _cannot_measure(
                f"{SEAM}: measurement returned neither a reading nor a refusal"
            )
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
