#!/usr/bin/env python3
"""`risks/` is INERT DATA whose every knob is derived from §12A and loaded at boot.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9). The property
is the standing rule `docs/directory_structure.md` writes for this directory —
*"data-role expression of the risk spec + §12A knobs; never a second behavioral
authority"* — made mechanical. Six arms serve that single property and are not
six properties; each one closes a different route by which a data directory turns
into an authority that can disagree with the spec silently.

THE FAILURE THIS EXISTS TO CATCH, and this project has seen its shape before. A
rules library that begins as data and accrues behaviour becomes a second
authority, and its disagreement with the spec is SILENT: both sides look
plausible, neither is obviously wrong, and the code path that decided is not the
one anybody is reading. `checks/check_limiter_seam.py` owns the same property for
one Python file one directory over; this gate's subject is `risks/`, and the
shapes differ — the hazard here is an eval'able rule expression smuggled into a
data file, a knob whose SEMANTICS are settled in `risks/` instead of derived from
§12A, or a §12A knob acquiring a second physical home so two files can drift.

THE ARMS

  * **ARM 1 — nothing in `risks/` is executable.** Every entry is a
    `*.config.json`; every VALUE key's every leaf is a number or a bool. There
    are no strings in value position at all, so no expression, no module path, no
    lambda and no shell fragment can be smuggled in as a knob. Prose is legal
    only under `_`-prefixed documentation keys, which no loader reads — and ARM 5
    proves the loaders do not read them.

  * **ARM 2 — every §12A knob has EXACTLY ONE physical home, and every knob in
    `risks/` cites §12A truthfully.** The expected knob set is PARSED OUT OF THE
    FROZEN SPEC at run time, never typed here: a name added to §12A with no home
    is red, a knob claiming a §12A citation §12A does not carry is red, and a
    knob cited by two files is red because two files that hold one value can
    disagree without either being wrong.

  * **ARM 3 — a value §12A states explicitly has not drifted.** Where §12A writes
    `` `KNOB` = <number> ``, the landed value must equal it. Both sides derived:
    the numbers come out of the frozen file.

  * **ARM 4 — the boot validation is IMPLEMENTED, not decorative.** Each config
    names the module that validates it; the ids in its `_boot_validation` block
    and the rule ids that module declares must correspond in BOTH directions; and
    the shipped configs are RUN through the real validator, so a set that
    violates its own declared rules is red here.

  * **ARM 5 — no loader reads a documentation key.** A validator that consumed
    `_meta` or `_derivations` would make prose load-bearing, at which point
    rewording a comment changes behaviour and the "documentation" is the
    authority after all.

  * **ARM 6 — boot-loaded, restart-only (§12.11).** No validator declares a
    reload/refresh/watch verb, imports a signalling or scheduling module, or
    reads an mtime. *"No hot-reload — a mid-session change would let two
    decisions inside one open trade read different tunables."* The complementary
    half — that the loaded object is frozen and carries a version digest — is
    driven at run time by `scripts/tests/test_risk_config.py`, because
    immutability is a property of an OBJECT and this gate reads source.

`debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
MEASURING NOTHING. Four routes, each closed by a floor asserted BEFORE any
comparison, and each floor is a FLOOR rather than today's figure:

 1. **`risks/` is empty or nearly so**, and every arm iterates nothing. Closed:
    `MIN_CONFIG_FILES` and `MIN_VALUE_KEYS` must both be reached or the verdict
    is CANNOT_MEASURE (§5.3 — an empty scope is never a PASS).
 2. **The §12A parse silently matches nothing**, so "every knob has a home" is a
    statement about the empty set. Closed: `MIN_SPEC_KNOBS`, plus the §12A span
    itself having to be found in the frozen document.
 3. **The default-drift arm finds no stated defaults** and compares nothing.
    Closed: `MIN_SPEC_DEFAULTS`.
 4. **The knob count is a constant in this file** — a transcribed figure wearing
    a derivation's clothes. Closed by construction: no §12A knob name and no
    expected count appears anywhere in this source, and
    `scripts/tests/test_check_risks_data_only.py` asserts that by scanning these
    bytes and by moving the spec and watching the derived figure move with it.

WHAT THIS GATE CANNOT PROVE, stated rather than implied. It reads files. It
cannot prove that a Limiter which does not yet exist consults these numbers, that
a running process was booted from the set on disk, or that the CC-calibrate
placeholders are correct values — §12A itself says they are placeholders. It
cannot see a hot-reload implemented in a module that no config names as its
validator. And a green here says the DATA is inert and faithful, never that any
rule reading it behaves.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first: every side is a file on disk that no check produces.
DEPENDS_ON: tuple[str, ...] = ()
#: Claims NOTHING. File reads, an AST parse and one import of a stdlib-only
#: module; no socket, no subprocess, no write. `()` is the positive claim and is
#: what makes this gate parallel-eligible (check contract v2 §12 — declared
#: claims are checked against OBSERVED ones, so an empty declaration here is
#: falsifiable rather than trusted).
RESOURCES: tuple[str, ...] = ()
#: A block halts on any member's failure; this gate's failure is a finding about
#: data, never a reason to stop measuring the rest of the tree.
ON_FAIL = "continue"
#: No timeout, no poll. The runtime is a handful of file reads.
TIME_BOUND = False
#: NON-CORRECTABLE. Every arm compares `risks/` against the FROZEN spec or
#: against a validator's own declarations. A gate empowered to edit either side
#: into agreement would be manufacturing its own green, and the frozen spec is
#: the one document in this tree nothing may edit.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is the frozen risk spec, which is never edited, and the "
    "measured side is a data directory whose whole purpose is to be checkable "
    "against it. An instrument that could rewrite either side to agree would be "
    "manufacturing its own green -- the same objection that makes "
    "check_limiter_seam and check_artifact_gate_coverage non-correctable."
)
#: Genuinely MEASURED, not merely named: every byte of every file below is parsed
#: on every run, and each one leaving scope makes this gate CANNOT_MEASURE rather
#: than quietly unscanned.
#:
#: `risks/broker_order.config.json` is DELIBERATELY ABSENT from this tuple while
#: being fully scanned by every arm. It is listed in
#: `checks/gate_coverage_baseline.json` as an accepted-uncovered artifact, and
#: declaring it here would correctly redden that ratchet's stale-baseline arm --
#: whose repair is a SHRINK of a file this arc does not own. Recorded as a debt
#: row rather than resolved by declaring less measurement or more.
SUBJECTS: tuple[str, ...] = (
    "risks/allocator.config.json",
    "risks/limiter.config.json",
    "risks/scoring.config.json",
    "risks/staleness.config.json",
    "risks/supervision.config.json",
    "scripts/risk_config.py",
)

NAME = "check_risks_data_only"

RISKS = "risks"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"
CONFIG_SUFFIX = ".config.json"

#: The §12A heading, and where its span ends. Anchored on the heading text so the
#: gate fails LOUD if the section is renamed or renumbered, rather than silently
#: matching nothing and reporting an empty expected set as agreement.
_SECTION_HEADING = re.compile(r"^##\s+12A\.", re.MULTILINE)
_NEXT_SECTION = re.compile(r"^##\s+\S", re.MULTILINE)

#: An inline-code span in the spec, and a knob name inside one. A knob is an
#: UPPER_SNAKE identifier carrying at least one underscore; the trailing class
#: admits `$` because one §12A knob's own spelling ends in a currency sign, and
#: it is not named here — a gate that spells out even one member of the set it
#: derives has a constant on the reference side, and the suite asserts that no
#: knob name appears anywhere in this file. Nothing is typed out: the set this
#: produces is whatever §12A currently says.
_CODE_SPAN = re.compile(r"`([^`]+)`")
_KNOB = re.compile(r"[A-Z][A-Z0-9_]*[A-Z0-9$]")

#: `` `KNOB` = 0.70 `` — the defaults §12A states outright.
_STATED_DEFAULT = re.compile(r"`([A-Z][A-Z0-9_]*[A-Z0-9$])`\s*=\s*(-?\d+(?:\.\d+)?)")

#: A `_derivations` entry's claim on §12A: the line it cites and the knob it
#: names. Both are checked against the frozen document.
_CITATION = re.compile(r"§12A:(\d+)\s+`([A-Z][A-Z0-9_]*[A-Z0-9$])`")
#: The explicit disclaimer a non-§12A knob must carry. A knob that neither cites
#: §12A nor says it is not a §12A knob has an unstated origin, which is the
#: "semantics settled in risks/" shape this gate exists to catch.
_NOT_A_KNOB = re.compile(r"not a §12A knob", re.IGNORECASE)

#: ARM 6. Names that make a config hot-reloadable.
_RELOAD_VERB = re.compile(r"(?i)(reload|refresh|reread|rewatch|watch)")
_RELOAD_IMPORTS = frozenset(
    {"signal", "threading", "asyncio", "sched", "inotify", "pyinotify", "watchdog"}
)
_RELOAD_LITERALS = ("SIGHUP", "st_mtime")
#: Prose about the rule is not the rule. Above this length a string is
#: documentation, and a gate that reddened on its own explanation is unusable.
_WATCH_LITERAL_MAX = 64

#: NON-VACUITY FLOORS (`debug.md` §7.12). Each is a FLOOR the gate must reach or
#: it has measured nothing and says so. Anchored below today's figures on
#: purpose: a threshold equal to the current count is a moving anchor that
#: reddens the moment a knob lands (§7.4).
MIN_CONFIG_FILES = 4
MIN_VALUE_KEYS = 20
MIN_SPEC_KNOBS = 20
MIN_SPEC_DEFAULTS = 8


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ===========================================================================
# THE REFERENCE SIDE — parsed out of the frozen spec, never typed here.
# ===========================================================================


def spec_section_text(home: Path) -> tuple[str, str]:
    """§12A's text and its first line number, or `("", complaint)`."""
    path = home / SPEC
    if not path.is_file():
        return "", f"{SPEC} is not on disk — the reference side is absent"
    text = path.read_text(encoding="utf-8")
    opened = _SECTION_HEADING.search(text)
    if opened is None:
        return "", (
            f"{SPEC}: no '## 12A.' heading — the configuration-parameters "
            "section was renamed, renumbered or moved, so this gate has no "
            "reference side and an empty expected set would compare green "
            "against anything"
        )
    closed = _NEXT_SECTION.search(text, opened.end())
    return text[opened.start() : closed.start() if closed else len(text)], ""


def spec_knobs(home: Path) -> tuple[frozenset[str], str]:
    """Every knob §12A names. DERIVED at run time; `(knobs, complaint)`."""
    section, complaint = spec_section_text(home)
    if complaint:
        return frozenset(), complaint
    found = {
        knob
        for span in _CODE_SPAN.findall(section)
        for knob in _KNOB.findall(span)
        if "_" in knob
    }
    return frozenset(found), ""


def spec_defaults(home: Path) -> dict[str, float]:
    """Knob -> the value §12A states outright for it. Derived, never listed."""
    section, complaint = spec_section_text(home)
    if complaint:
        return {}
    return {knob: float(value) for knob, value in _STATED_DEFAULT.findall(section)}


def _spec_line(home: Path, number: int) -> str:
    """One line of the frozen spec, 1-based. Empty when out of range."""
    lines = (home / SPEC).read_text(encoding="utf-8").splitlines()
    return lines[number - 1] if 1 <= number <= len(lines) else ""


def _section_span(home: Path) -> tuple[int, int]:
    """The 1-based line range §12A occupies. `(0, 0)` when it cannot be found."""
    path = home / SPEC
    if not path.is_file():
        return 0, 0
    text = path.read_text(encoding="utf-8")
    opened = _SECTION_HEADING.search(text)
    if opened is None:
        return 0, 0
    closed = _NEXT_SECTION.search(text, opened.end())
    first = text.count("\n", 0, opened.start()) + 1
    last = text.count("\n", 0, closed.start()) if closed else text.count("\n") + 1
    return first, last


# ===========================================================================
# THE MEASURED SIDE — the files in `risks/`.
# ===========================================================================


class Config(NamedTuple):
    """One parsed config, split into the two halves that matter."""

    rel: str
    module: str
    values: dict[str, object]
    derivations: dict[str, str]
    rule_ids: tuple[str, ...]
    validated_by: str


def _leaves(value: object, path: str) -> list[tuple[str, object]]:
    """Every leaf in a value tree, with a dotted path naming where it sits."""
    if isinstance(value, dict):
        return [
            item
            for key in sorted(value)
            for item in _leaves(value[key], f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            item
            for index, entry in enumerate(value)
            for item in _leaves(entry, f"{path}[{index}]")
        ]
    return [(path, value)]


def _read_configs(home: Path) -> tuple[list[Config], list[tuple[str, str]], str]:
    """Parse `risks/`. Returns (configs, structural defects, complaint)."""
    base = home / RISKS
    if not base.is_dir():
        return [], [], f"{RISKS}/ is not a directory — nothing to measure"
    defects: list[tuple[str, str]] = []
    configs: list[Config] = []
    for path in sorted(base.rglob("*")):
        rel = str(path.relative_to(home))
        if path.is_dir():
            defects.append(
                (
                    rel,
                    (
                        "a subdirectory in risks/ — the directory is a flat set "
                        "of per-module config files, and a tree is where a "
                        "package hides"
                    ),
                )
            )
            continue
        if not rel.endswith(CONFIG_SUFFIX):
            defects.append(
                (
                    rel,
                    (
                        f"is not a {CONFIG_SUFFIX} file — risks/ holds data, and "
                        "anything else here is behaviour or a place to put it"
                    ),
                )
            )
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            defects.append((rel, f"is not readable JSON: {exc}"))
            continue
        if not isinstance(raw, dict):
            defects.append(
                (rel, f"top level is {type(raw).__name__}, expected an object")
            )
            continue
        meta = raw.get("_meta")
        meta = meta if isinstance(meta, dict) else {}
        derivations = raw.get("_derivations")
        rules = raw.get("_boot_validation")
        configs.append(
            Config(
                rel=rel,
                module=path.name[: -len(CONFIG_SUFFIX)],
                values={
                    key: value for key, value in raw.items() if not key.startswith("_")
                },
                derivations=derivations if isinstance(derivations, dict) else {},
                rule_ids=tuple(
                    entry["id"]
                    for entry in (rules if isinstance(rules, list) else [])
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str)
                ),
                validated_by=str(meta.get("validated_by", "")),
            )
        )
    return configs, defects, ""


# ===========================================================================
# THE ARMS
# ===========================================================================


def _arm1_inert(configs: list[Config]) -> list[tuple[str, str]]:
    """No string, null or executable expression sits in a VALUE position."""
    defects: list[tuple[str, str]] = []
    for cfg in configs:
        for key, value in sorted(cfg.values.items()):
            for where, leaf in _leaves(value, key):
                if isinstance(leaf, (bool, int, float)):
                    continue
                defects.append(
                    (
                        f"{cfg.rel}:{where}",
                        (
                            f"value is {type(leaf).__name__} {leaf!r}, and a "
                            "knob in risks/ may only be a number. A string in "
                            "value position is where an eval'able rule "
                            "expression, a module path or a code-path key "
                            "enters a data file"
                        ),
                    )
                )
    return defects


# R0911 refused with a reason: each return is a DIFFERENT way a derivation can
# fail to be one, and doctrine C.2 requires the gate name WHICH — no entry at
# all, an unstated origin, a coordinate outside §12A, a line that does not carry
# the cited name, and a knob §12A does not have. A single exit would thread the
# same five reasons through a variable, which is the count wearing a disguise.
def _claimed_knob(  # pylint: disable=too-many-return-statements
    derivation: object, home: Path, knobs: frozenset[str], span: tuple[int, int]
) -> tuple[str, str]:
    """`(knob, why)` for one `_derivations` entry — exactly one is non-empty.

    Split out of `_arm2_citations` so the CITATION question ("is this entry's
    claim on §12A true?") is one readable function and the BOOKKEEPING question
    ("does any knob have two homes, and does every knob have one?") is another.
    Both were one loop and the loop was long enough that its two subjects were
    hard to separate by eye.
    """
    if not isinstance(derivation, str) or not derivation.strip():
        return "", (
            "has no `_derivations` entry — a knob with no stated origin has its "
            "semantics settled HERE, which is exactly the second authority "
            "risks/ may not become"
        )
    cited = _CITATION.search(derivation)
    if cited is None:
        if _NOT_A_KNOB.search(derivation):
            return "", ""
        return "", (
            "cites no `§12A:<line> `KNOB`` and does not say it is not a §12A "
            "knob — its origin is unstated, so nothing can tell a derived value "
            "from an invented one"
        )
    line, knob = int(cited.group(1)), cited.group(2)
    first, last = span
    if not first <= line <= last:
        return "", (
            f"cites §12A:{line}, which is outside §12A's own span "
            f"({first}-{last}) in {SPEC} — the coordinate points somewhere else "
            "in the document"
        )
    if knob not in _spec_line(home, line):
        return "", (
            f"cites §12A:{line} for `{knob}`, and that line of {SPEC} does not "
            "carry that name — the citation is unfalsifiable prose, not a "
            "derivation"
        )
    if knob not in knobs:
        return "", (
            f"claims §12A knob `{knob}`, which the parsed §12A knob set does "
            "not contain"
        )
    return knob, ""


def _arm2_citations(
    configs: list[Config], home: Path, knobs: frozenset[str]
) -> tuple[list[tuple[str, str]], dict[str, tuple[str, str]]]:
    """Every knob cites §12A truthfully, and no §12A knob has two homes."""
    defects: list[tuple[str, str]] = []
    homes: dict[str, tuple[str, str]] = {}
    span = _section_span(home)
    for cfg in configs:
        for key in sorted(cfg.values):
            knob, why = _claimed_knob(cfg.derivations.get(key), home, knobs, span)
            if why:
                defects.append((f"{cfg.rel}:{key}", why))
            elif knob and knob in homes:
                other_file, other_key = homes[knob]
                defects.append(
                    (
                        f"{cfg.rel}:{key}",
                        (
                            f"is a SECOND physical home for §12A knob `{knob}` "
                            f"— {other_file}:{other_key} already holds it. Two "
                            "files holding one value can disagree without "
                            "either being obviously wrong, and the disagreement "
                            "is silent"
                        ),
                    )
                )
            elif knob:
                homes[knob] = (cfg.rel, key)
    defects.extend(
        (
            f"{RISKS}/",
            (
                f"§12A names `{missing}` and no file in risks/ lands it — a "
                "tunable the spec owns with no physical home is a literal "
                "waiting to be typed into code"
            ),
        )
        for missing in sorted(knobs - set(homes))
    )
    return defects, homes


def _arm3_defaults(
    configs: list[Config], defaults: dict[str, float], homes: dict[str, tuple[str, str]]
) -> list[tuple[str, str]]:
    """A value §12A states outright has not drifted in the physical layout."""
    by_rel = {cfg.rel: cfg for cfg in configs}
    defects: list[tuple[str, str]] = []
    for knob, expected in sorted(defaults.items()):
        placed = homes.get(knob)
        if placed is None:
            continue
        rel, key = placed
        landed = by_rel[rel].values.get(key)
        if isinstance(landed, bool) or not isinstance(landed, (int, float)):
            defects.append((f"{rel}:{key}", f"is {landed!r}, not a number"))
        elif float(landed) != expected:
            defects.append(
                (
                    f"{rel}:{key}",
                    (
                        f"is {landed}, but §12A states `{knob}` = {expected} "
                        "outright. The physical layout may not silently change a "
                        "value the semantic authority fixes"
                    ),
                )
            )
    return defects


def _get_call_key(node: ast.AST) -> str | None:
    """The literal key of a `<expr>.get("key")` call, or None.

    Split out of `_validator_facts` so the documentation-key detector reads as
    two named questions — a subscript and a `.get()` — rather than one condition
    long enough that pylint counts it.
    """
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "get" or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _declared_ids(node: ast.AST) -> set[str]:
    """Rule ids this node declares: a `BOOT_RULE_IDS` tuple or an `id=` keyword.

    BOTH SPELLINGS of the assignment are read, because a type annotation is not a
    declaration of intent to be invisible: `BOOT_RULE_IDS = (...)` is an
    `ast.Assign` and `BOOT_RULE_IDS: tuple[str, ...] = (...)` is an
    `ast.AnnAssign`, and a reader handling only the first would report a
    validator with a perfectly good rule list as implementing nothing.
    """
    value: ast.expr | None = None
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "BOOT_RULE_IDS"
        for target in node.targets
    ):
        value = node.value
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "BOOT_RULE_IDS"
    ):
        value = node.value
    if value is not None:
        return {
            element.value
            for element in ast.walk(value)
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    if (
        isinstance(node, ast.keyword)
        and node.arg == "id"
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ):
        return {node.value.value}
    return set()


def _lifecycle_defect(node: ast.AST, rel: str) -> tuple[str, str] | None:
    """ARM 6: one route by which a boot-loaded config becomes hot-reloadable."""
    if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)
    ) and _RELOAD_VERB.search(node.name):
        return (
            f"{rel}:{node.lineno} {node.name}",
            (
                "declares a reload/watch verb — §12.11 locks the config "
                "lifecycle boot-loaded, restart-only, because a mid-session "
                "change would let two decisions inside one open trade read "
                "different tunables"
            ),
        )
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        named = (
            (node.module or "")
            if isinstance(node, ast.ImportFrom)
            else node.names[0].name
        )
        root = named.split(".")[0]
        if root in _RELOAD_IMPORTS:
            return (
                f"{rel}:{node.lineno}",
                (
                    f"imports {root} — a config loader that can be signalled, "
                    "scheduled or woken is a config loader that can hot-reload, "
                    "which §12.11 forbids"
                ),
            )
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _watch_literal_defect(node.value, node.lineno, rel)
    return None


def _watch_literal_defect(text: str, line: int, rel: str) -> tuple[str, str] | None:
    """A short string literal naming an mtime or a hangup signal.

    Long strings are skipped: this module's own prose discusses both, and a gate
    that reddened on a docstring explaining the rule would be unusable.
    """
    if len(text) >= _WATCH_LITERAL_MAX:
        return None
    for literal in _RELOAD_LITERALS:
        if literal in text:
            return (
                f"{rel}:{line}",
                (
                    f"carries the literal {literal!r} — an mtime or a hangup is "
                    "how a boot-loaded config starts watching itself"
                ),
            )
    return None


def _doc_key_defect(node: ast.AST, rel: str) -> tuple[str, str] | None:
    """ARM 5: a `_`-prefixed key read in subscript or `.get()` position."""
    read: str | None = None
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        read = node.slice.value if isinstance(node.slice.value, str) else None
    read = _get_call_key(node) or read
    if read is None or not read.startswith("_") or read == "_":
        return None
    line = getattr(node, "lineno", 0)
    return (
        f"{rel}:{line}",
        (
            f"reads documentation key {read!r} out of a config — the "
            "`_`-prefixed keys are the file's own account of where its numbers "
            "came from, and a loader that consumes them makes rewording a "
            "comment a behaviour change"
        ),
    )


def _validator_facts(home: Path, rel: str) -> tuple[set[str], list[tuple[str, str]]]:
    """Rule ids a validator DECLARES, and its §12.11 lifecycle defects (ARM 6).

    Read by AST, never by importing: a gate that imported every validator it
    judged would be running the code under test to decide whether the code under
    test is honest.
    """
    path = home / rel
    if not path.is_file():
        return set(), [(rel, "is named as a validator and is not on disk")]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    ids: set[str] = set()
    defects: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        ids |= _declared_ids(node)
        defect = _lifecycle_defect(node, rel) or _doc_key_defect(node, rel)
        if defect is not None:
            defects.append(defect)
    return ids, defects


def _arm4_boot_rules(
    configs: list[Config], home: Path
) -> tuple[list[tuple[str, str]], int]:
    """Declared ids and implemented ids correspond, in both directions."""
    defects: list[tuple[str, str]] = []
    checked = 0
    cache: dict[str, tuple[set[str], list[tuple[str, str]]]] = {}
    for cfg in configs:
        if not cfg.rule_ids:
            defects.append(
                (
                    f"{cfg.rel}:_boot_validation",
                    (
                        "declares no boot rule with an `id` — a config nothing "
                        "can reject is a config with no validation, and a list "
                        "of prose nothing executes is documentation"
                    ),
                )
            )
            continue
        if not cfg.validated_by:
            defects.append(
                (
                    f"{cfg.rel}:_meta.validated_by",
                    (
                        "names no validating module, so its declared rule ids "
                        "correspond to nothing that runs"
                    ),
                )
            )
            continue
        if cfg.validated_by not in cache:
            cache[cfg.validated_by] = _validator_facts(home, cfg.validated_by)
        implemented, lifecycle = cache[cfg.validated_by]
        defects.extend(lifecycle)
        checked += 1
        for orphan in sorted(set(cfg.rule_ids) - implemented):
            defects.append(
                (
                    f"{cfg.rel}:_boot_validation.{orphan}",
                    (
                        f"is declared here and {cfg.validated_by} implements no "
                        "rule with that id — a declared rule nothing runs is "
                        "documentation wearing a rule's clothes"
                    ),
                )
            )
    return defects, checked


def _validated_configs(configs: list[Config], home: Path) -> list[tuple[str, str]]:
    """ARM 4's other half: RUN the real validator over the SHIPPED configs."""
    try:
        import risk_config  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return [(f"{RISKS}/", f"scripts/risk_config.py is not importable: {exc}")]
    owned = {cfg.module for cfg in configs} & set(risk_config.OWNED_MODULES)
    if not owned:
        return [
            (
                f"{RISKS}/",
                (
                    "no config in risks/ belongs to a module the validator owns "
                    "— the boot rules would run over nothing"
                ),
            )
        ]
    try:
        risk_config.load_risk_configs(home)
    except risk_config.RiskConfigError as exc:
        return [
            (
                f"{RISKS}/",
                (
                    "the SHIPPED configs do not satisfy their own declared boot "
                    f"validation: {exc}"
                ),
            )
        ]
    # The correspondence, from the code side: every rule the validator applies to
    # a module must be DECLARED in that module's file.
    defects: list[tuple[str, str]] = []
    for cfg in configs:
        if cfg.module not in owned:
            continue
        for rule_id in risk_config.rule_ids_for(cfg.module):
            if rule_id not in cfg.rule_ids:
                defects.append(
                    (
                        f"{cfg.rel}:_boot_validation",
                        (
                            f"does not declare `{rule_id}`, which the validator "
                            "applies to this module — a rule that runs and is "
                            "written down nowhere is a rule nobody can find"
                        ),
                    )
                )
    return defects


class _Sides(NamedTuple):
    """Both sides, once each is known to be non-empty."""

    configs: list[Config]
    knobs: frozenset[str]
    defaults: dict[str, float]
    value_keys: int
    structural: list[tuple[str, str]]


# R0911 refused with a reason: every return is a DIFFERENT non-vacuity floor,
# and §5.3 requires each one say which floor was not reached. A single exit point
# would need a reason variable threaded through the same six tests, which is the
# same count wearing a different shape.
def _gather(  # pylint: disable=too-many-return-statements
    home: Path,
) -> tuple[_Sides | None, CheckResult | None]:
    """Read both sides, or say WHY the comparison cannot be made.

    Every non-vacuity refusal lives here so §5.3's "an empty scope is never a
    PASS" is a single rule a reader can check in one place. Exactly one of the
    two members is set.
    """
    configs, structural, complaint = _read_configs(home)
    if complaint:
        return None, _cannot_measure(
            f"{complaint} (§5.3: an empty scope is never a PASS)"
        )
    if len(configs) < MIN_CONFIG_FILES:
        return None, _cannot_measure(
            f"{RISKS}/ yielded only {len(configs)} config file(s), below the "
            f"floor of {MIN_CONFIG_FILES} — a no-behaviour gate over a nearly "
            "empty directory passes trivially"
        )
    value_keys = sum(len(cfg.values) for cfg in configs)
    if value_keys < MIN_VALUE_KEYS:
        return None, _cannot_measure(
            f"{RISKS}/ carries only {value_keys} value key(s), below the floor "
            f"of {MIN_VALUE_KEYS} — the arms would iterate almost nothing"
        )
    knobs, knob_complaint = spec_knobs(home)
    if knob_complaint:
        return None, _cannot_measure(
            f"{knob_complaint} (§5.3: an empty scope is never a PASS)"
        )
    if len(knobs) < MIN_SPEC_KNOBS:
        return None, _cannot_measure(
            f"§12A yielded only {len(knobs)} knob name(s) "
            f"({', '.join(sorted(knobs)) or 'none'}), below the floor of "
            f"{MIN_SPEC_KNOBS} — the parse stopped matching, and 'every knob has "
            "a home' over a tiny set is a statement about nothing"
        )
    defaults = spec_defaults(home)
    if len(defaults) < MIN_SPEC_DEFAULTS:
        return None, _cannot_measure(
            f"§12A yielded only {len(defaults)} stated default(s), below the "
            f"floor of {MIN_SPEC_DEFAULTS} — the drift arm would compare nothing"
        )
    return _Sides(configs, knobs, defaults, value_keys, structural), None


def run(  # pylint: disable=unused-argument,too-many-locals
    mode: Mode, ctx: Context
) -> CheckResult:
    """Measure `risks/` against the frozen spec. Never repairs — see the reason."""
    try:
        sides, refusal = _gather(ctx.nix_home)
        if refusal is not None or sides is None:
            # `_gather` sets exactly one member. The `or` arm is unreachable and
            # is written anyway rather than as an `assert`: an assert vanishes
            # under -O, and a gate whose refusal path evaporates in optimised
            # bytecode would return a bare PASS over an unread subject.
            return refusal or _cannot_measure(
                f"{RISKS}/: neither a reading nor a refusal — the gate's own "
                "pre-flight returned nothing, which is never a verdict"
            )
        configs, knobs, defaults, value_keys, structural = sides

        defects: list[tuple[str, str]] = list(structural)
        defects.extend(_arm1_inert(configs))
        citation_defects, homes = _arm2_citations(configs, ctx.nix_home, knobs)
        defects.extend(citation_defects)
        defects.extend(_arm3_defaults(configs, defaults, homes))
        rule_defects, validators = _arm4_boot_rules(configs, ctx.nix_home)
        defects.extend(rule_defects)
        defects.extend(_validated_configs(configs, ctx.nix_home))

        leaves = sum(
            len(_leaves(value, key))
            for cfg in configs
            for key, value in cfg.values.items()
        )
        evidence = (
            f"{len(configs)} config file(s), {value_keys} value key(s), "
            f"{leaves} numeric leaf/leaves, {validators} validated by a named "
            f"module; §12A knobs {len(knobs)} == homes {len(homes)}, "
            f"{len(defaults)} stated default(s) compared; the knob set and the "
            f"defaults are parsed from {SPEC} at run time, not from a constant "
            "in this gate"
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
