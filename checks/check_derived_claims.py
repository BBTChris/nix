#!/usr/bin/env python3
"""Every registered number is derived from its source, never restated.

DISCHARGES CHECK-DEBT D2.8 / doctrine B.7 — *no harness parses a constant out of
a document and asserts the code equals it.* This is the DERIVE-NEVER-RESTATE
class, not the vacuous-pass class; the ARC 016 brief conflated the two, the
ledger records the correction, and D2.8 stood open and unassigned until now.

HOW IT WORKS. `checks/derived_claims.json` is a registry of CLAIMS. A claim is a
set of SOURCES, each a command that prints an integer it computed at run time.
All sources of a claim must agree. A source is `derived` (computed from ground
truth) or `stated` (a number a document, config, or code file asserts). The gate
re-derives everything on every run and compares; nothing is remembered between
runs and nothing is stored in the registry.

THE REGISTRY CONTAINS NO EXPECTED VALUES — not one integer. Storing "16" beside
the claim that section 2A has 16 elements would rebuild, inside the instrument,
the exact defect the instrument exists to catch. `debug.md` §7.4: never anchor
an assertion to something that moves (doctrine C.4).

CITATION CORRECTED ARC 019, by the gate built to correct it. This paragraph
cited "§2.4" of the check contract from ARC 017 until `check_spec_citations`
resolved it: that document has no 2.4 — its labelled headings run 1, 2, 3, 4,
4.1, 4.2, 5, 5.1-5.5, 6-15 and 15.1-15.4 — and the rule being invoked is
doctrine C.4, which `debug.md` operationalises as §7.4. The same phantom is
still live in the check contract's own conformance map, which is an external
document this arc does not own; recorded as CHECK-DEBT D1.21.

SCOPE, v1: numeric claims only. Prose-fact verification is a different
instrument and is not attempted here.

WHY THE CLAIMS ARE WORTH GATING — ten measured instances of this failure class
in this project, tabulated in the registry's own `comment` block so the evidence
travels with the data rather than with the code. The tenth was found the day
this gate was written: `.pre-commit-config.yaml` restated "126 tests" in two
comments while the real collected count was 159 — the first instance found
inside a GATE'S OWN CONFIGURATION rather than a document.

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
 1. The registry is empty, or every claim was deleted from it. A gate that
    iterates zero claims reports "no disagreements".
    GUARDED: an empty `claims` list is CANNOT_MEASURE, never PASS.

 2. A claim has ONE source. One number agrees with itself unconditionally.
    GUARDED: fewer than two sources on any claim is CANNOT_MEASURE, and the
    claim is named.

 3. A claim's two sources are the SAME computation twice — two probes that read
    the same file with the same rule always agree and assert nothing.
    PARTIALLY GUARDED: duplicate probe/argv identity within one claim is
    rejected. Causal independence cannot be proven mechanically, so each claim's
    `note` states in writing why its sources are independent, and that statement
    is what a reviewer checks. `registered_check_count` (manifest vs disk) and
    `pytest_collected_tests` (collector vs AST) are independent in mechanism,
    not merely in spelling.

 4. A `stated` source's locating pattern stops matching, because the prose was
    rewritten, and a no-match is treated as "nothing to check".
    GUARDED: a probe that cannot locate its claim raises, and a raising source
    is CANNOT_MEASURE with the file named — never a silent skip.

 5. A registry entry points at a file that no longer exists and the entry is
    skipped.
    GUARDED: a missing file is FAIL, explicitly, not SKIP. A stale registry is
    a defect in the instrument and the instrument must say so.

 6. Every source fails to run — no venv, no interpreter — and the gate reports
    a clean sweep of nothing.
    GUARDED: unparseable or non-running sources produce CANNOT_MEASURE (exit 2),
    which is not a pass. Only a claim that actually compared two integers
    contributes to PASS, and `evidence` prints each claim with its agreed value
    so a reader can see what was compared.

 7. UNGUARDED, AND THE REAL LIMIT — COVERAGE. This gate proves that every
    registered number is right. It cannot prove the registry covers the numbers
    that matter: a document could restate ten counts and register none of them,
    and this gate would be green over the other seven. That is `debug.md` §8
    failure mode #14 — the scope is a list a person edits — and it is inherent
    to a registry-driven instrument. The mitigation is procedural and is stated
    here so it is not mistaken for a mechanical one: whenever an arc writes a
    number into a document, it adds the claim. There is no machine that can find
    a claim nobody registered.
    RE-CONFIRMED ARC 018 (named gap 5), and deliberately NOT repaired. The
    statement above is still accurate and still where it was. ARC 018 tested it
    the only way it can be tested — by adding three registered numbers
    (`order_path_scope_files`, `broker_order_element_coverage_v1`, and the
    scheme's canonical-form restatement scan) and observing that nothing in this
    gate asked for them, noticed they were missing, or would have gone red had
    they never been added. The gap is therefore not shrinking as the registry
    grows; it is exactly as large as the set of numbers nobody has thought of.
    An instrument that could prove its own completeness would be a different and
    much larger thing, and building a half-version of it would make the gap look
    addressed. Left open, on purpose, in writing.

 8. UNGUARDED — a `restatement_scans` pattern that matches nothing reports "0
    restatements (preferred)", which is indistinguishable from a pattern that
    was always wrong. Zero matches is genuinely the better outcome once a
    restatement has been deleted, so this is not repaired by making zero a
    failure; it is repaired by the pattern being reviewed at the point it is
    added, and by the `note` recording what it was written against.

 9. ADDED ARC 020, for the `broker_order_open_debt_rows` claim specifically.
    That claim selects ledger rows with a VOCABULARY — order-path module
    basenames plus the broker-order roster. An empty vocabulary selects nothing,
    and a count of nothing agrees with a count of nothing: 0 == 0 is a PASS that
    measured no row at all. Three ways the vocabulary can empty out: the order
    path holds no `.py` modules; the frozen spec's broker-order bullet block
    stops yielding identifiers; the seam's roster tuples go empty.
    GUARDED: each of the three raises `ProbeError` rather than returning an
    empty list, so the claim goes CANNOT_MEASURE naming the side that collapsed.
    An empty OPEN-row set raises too, for the same reason.
    NOT GUARDED, DELIBERATELY: a *selection* of zero with a healthy vocabulary.
    Zero open broker-order debt rows is the intended end state of the module and
    making it a failure would make the instrument fight its own purpose. What is
    done instead is that every selected row id is printed in the detail line on
    every run, so a selection that collapses from twelve to zero in one arc is
    readable rather than inferred — the same treatment condition 8 gets.

10. ADDED ARC 023 (B3), for the DEMONSTRATION arm specifically. Every condition
    above is about a NUMBER. A claim of the form *"X is proven to Y"* has no
    number in it, so none of them reaches it, and the measured consequence is
    CHECK-DEBT D1.14: that row banks `FeedLag` as "constructed twice from
    synthesised values differing in one field, and proven to refuse a field
    write". It was true on the branch it was written on. It stopped being true
    at the merge (CHECK-DEBT D3.15, root cause a `float | None` annotation the
    synthesiser cannot resolve), and this gate reported 13/13 across it for two
    arcs, because a claim about a DEMONSTRATION was outside everything it
    measures. The arm below re-executes such claims instead of reading them.
    GUARDED, and each guard is stated so it could be planted:
      a. `demonstrations` absent or empty -> CANNOT_MEASURE, never PASS. An arm
         with no subject is the whole subject of §7.12.
      b. A registered demonstration whose banked assertion no longer appears
         where it says it is banked -> FAIL. A registration outliving its claim
         is failure mode #14 pointed the other way.
      c. The re-execution not running, or exiting outside `accept_exit` ->
         CANNOT_MEASURE for that demonstration, never FAIL (doctrine B.2).
      d. Neither observation pattern matching, OR both matching -> the
         observation is INDETERMINATE and is CANNOT_MEASURE, never a verdict. A
         pattern that quietly stopped matching is `debug.md` §7.4 and must not
         read as "the demonstration performs".
      e. Observed state != declared state, IN EITHER DIRECTION -> FAIL. A
         demonstration that stopped performing is the D1.14 defect; one that
         started performing while still registered as owed means its debt row
         should have been closed and was not.
      f. A demonstration declared `does-not-perform` must name an `owed_row`
         that is OPEN by the ledger's own bold-span rule -> otherwise FAIL. A
         demotion may not outlive the debt that justifies it.
    NOT GUARDED, DELIBERATELY, and it is condition 7 in this arm's clothing: the
    arm proves every REGISTERED demonstration still performs and cannot find a
    demonstration nobody registered. The ledger banks dozens of "proven" and
    "demonstrated" spans and two of them are registered here. Registering them
    all by regex was considered and refused: most are DATED history ("MEASURED
    ARC 018"), which is append-only and must not be re-executed, and no
    mechanical rule separates a dated record from a standing claim. So the
    obligation is procedural and is written here rather than implied: an arc
    that banks a demonstration in the present tense registers it below.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess  # nosec B404 - fixed argv, shell=False, registry is a repo file
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) is disabled at module scope for the two ARC 017 gates.
# nix_check_contract.md §4.2 requires every checks/check_*.py be independently
# runnable and map status -> exit code identically, and doctrine B.2 requires the
# crash path return CANNOT_MEASURE in both. Those blocks are therefore MANDATED to
# be the same text; the only way to deduplicate them is a shared helper, which
# §4.2 is precisely what forbids. Same reasoning as the tail pragma every other
# check carries, hoisted to module scope because R0801 is reported at line 1.
# pylint: disable=duplicate-code
# C0302 (too-many-lines) disabled, ARC 021. The module went over pylint's
# 1000-line default when the three broker-datafeed claims were added (B3), and
# the split was MEASURED rather than assumed. The measurement is deliberately
# NOT restated here — that would be the exact defect this module exists to
# catch (doctrine B.7 / CHECK-DEBT D2.8), and `check_order_path_bans.py` carries
# the same refusal for the same reason. Derive it, do not read it:
#   .venv/bin/python -c "import ast,pathlib;s=pathlib.Path(
#     'checks/check_derived_claims.py').read_text();d=ast.get_docstring(
#     ast.parse(s),clean=False);print(len(s.splitlines()),
#     len(d.splitlines())+2)"
# Why the file may not be split to satisfy the count: `nix_check_contract.md`
# §4.2 requires every checks/check_*.py be independently runnable, so a shared
# helper module is not available; and this gate re-enters ITSELF as the probe
# runner ({self} in derived_claims.json), so its probes must live in the module
# the registry names. Splitting would either break §4.2 or create a second
# instrument for one property, which §5.5 forbids.
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_derived_claims"

# --- ARC 025 orchestration declarations (read statically, never imported) ---
#: DEPENDS ON THE VENV and cannot repair it: the `pytest_collector` source shells
#: to `{venv_python} -m pytest --collect-only`, and with no venv that claim's
#: only externally-implemented source disappears and the claim degrades to NOT
#: MEASURED. That degradation is a coverage defect, and ARC 025 measured its
#: cousin (the FORCE_COLOR defect below) doing exactly this, so an instrument
#: whose coverage is set by the box's state rather than by its subject is
#: something this gate must be ordered out of, not shrug at.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Every measurement is a SUBPROCESS — probes re-enter this file, sources shell
#: out, demonstrations re-execute other checks — so nothing is imported into the
#: engine's interpreter and there is no `interpreter:*` claim. `venv` is claimed
#: because the pytest collector runs the venv's own interpreter; the collection
#: is read-only (`-p no:cacheprovider` writes no cache) but a check MUTATING the
#: venv concurrently would change what this gate collects mid-run, which is
#: exactly the disjointness question `check_python_deps` claims `venv` for.
RESOURCES: tuple[str, ...] = ("venv",)
#: NOT time-bound, and EXPECTED_S is deliberately NOT declared. The honest bound
#: is `_TIMEOUT` multiplied by the number of sources and demonstrations, and that
#: number lives in `derived_claims.json`, which this gate reads at RUN time — so
#: no literal can state it and `declarations.py` cannot evaluate the expression
#: that could (`nix_check_contract.md` §4.4's named weakness). A literal here
#: would be right on the day
#: it was typed and silently wrong on every later edit of the registry, which is
#: `debug.md` §7.4's moving anchor pointed at a declaration. An absent EXPECTED_S
#: is read as `None`, never as zero.
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every defect this gate reports is two sources disagreeing about one "
    "number, and the gate cannot know which side is right — that is the whole "
    "reason a claim carries two independently-derived sources. The only "
    "'repair' available is to overwrite one of them, and the stated side is "
    "usually a figure banked in `docs/CHECK-DEBT.md` or in an arc record, "
    "which `CLAUDE.md` directive 6 forbids rewriting. An engine that silenced "
    "a disagreement by editing the document under measurement would destroy "
    "the evidence at the moment the evidence matters (doctrine A.2)"
)
#: The registry this gate re-derives. Every defect it reports is sited at
#: `derived_claims.json:<claim id>`, so this is the artifact it measures rather
#: than merely reads. The files each claim names are data inside that registry
#: and cannot be a literal here.
SUBJECTS: tuple[str, ...] = ("checks/derived_claims.json",)

REGISTRY = "derived_claims.json"
_INT_ONLY = re.compile(r"^\s*(-?\d+)\s*$")
_TIMEOUT = 300

#: SGR/CSI escape sequences. See `_child_env` for why this exists as well.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class ProbeError(RuntimeError):
    """A probe could not compute its number. Never silently zero."""


# ===========================================================================
# PARSING HELPERS — stdlib only, no import of any subject (§9.4).
# ===========================================================================


def _read(home: Path, rel: str) -> str:
    return (home / rel).read_text(encoding="utf-8")


def _md_block(text: str, heading: str) -> str:
    """The markdown block starting at `heading`, ending at the next divider."""
    start = text.index(heading)
    end = len(text)
    for marker in ("\n### ", "\n## ", "\n---"):
        found = text.find(marker, start + 1)
        if found >= 0:
            end = min(end, found)
    return text[start:end]


def _spec_identifiers(home: Path, heading: str) -> list[str]:
    """§2A element identifiers for one library — BY IDENTIFIER, NOT BY BULLET.

    Only the leading backtick span of a bullet is read, so a prose reference
    later in the same bullet ("primary path is the `on_margin` push below")
    cannot be counted as a second declaration.
    """
    block = _md_block(_read(home, "docs/nics_risk_subsystem_spec_v1.3.md"), heading)
    names: list[str] = []
    for line in block.splitlines():
        if not line.startswith("- "):
            continue
        span = re.match(r"-\s+`([^`]+)`", line)
        if not span:
            continue
        names.extend(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", span.group(1)))
    if not names:
        raise ProbeError(f"no §2A identifiers found under {heading!r}")
    return names


def _binding(node: ast.stmt) -> tuple[str | None, ast.expr | None]:
    """(bound name, assigned expression) for a simple module-level assignment."""
    if isinstance(node, ast.AnnAssign):
        name = node.target.id if isinstance(node.target, ast.Name) else None
        return name, node.value
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        return (target.id if isinstance(target, ast.Name) else None), node.value
    return None, None


def _str_elements(value: ast.expr) -> list[str]:
    if not isinstance(value, ast.Tuple):
        return []
    return [
        elt.value
        for elt in value.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    ]


def _module_tuples(
    home: Path, rel: str, wanted: tuple[str, ...]
) -> dict[str, list[str]]:
    """Read named str-tuple constants out of a module by AST — never by import."""
    tree = ast.parse(_read(home, rel), filename=rel)
    out: dict[str, list[str]] = {}
    for node in tree.body:
        name, value = _binding(node)
        if name in wanted and value is not None:
            out[str(name)] = _str_elements(value)
    missing = [w for w in wanted if w not in out]
    if missing:
        raise ProbeError(f"{rel}: constants not found: {', '.join(missing)}")
    return out


def _finding_pairs(value: ast.expr) -> list[tuple[str, str]]:
    """(verb, grade) for each `Finding("verb", "GRADE", ...)` in a tuple literal."""
    if not isinstance(value, ast.Tuple):
        return []
    pairs: list[tuple[str, str]] = []
    for elt in value.elts:
        if not isinstance(elt, ast.Call) or len(elt.args) < 2:
            continue
        verb, grade = elt.args[0], elt.args[1]
        if isinstance(verb, ast.Constant) and isinstance(grade, ast.Constant):
            pairs.append((str(verb.value), str(grade.value)))
    return pairs


def _arc014_findings(home: Path) -> list[tuple[str, str]]:
    """[(verb, grade)] from ibkr_mapping.FINDINGS, read by AST."""
    rel = "scripts/broker/ibkr_mapping.py"
    tree = ast.parse(_read(home, rel), filename=rel)
    for node in tree.body:
        name, value = _binding(node)
        if name != "FINDINGS" or value is None:
            continue
        pairs = _finding_pairs(value)
        if not pairs:
            raise ProbeError(f"{rel}: FINDINGS present but held no Finding(...) calls")
        return pairs
    raise ProbeError(f"{rel}: FINDINGS not found")


def _normalise_verb(verb: str) -> list[str]:
    """'connect / disconnect' -> [connect, disconnect]; 'flatten(x|all)' -> [flatten].

    Mechanical: drop everything from the first '(' , split on '/', strip. A token
    that is not a bare identifier ('client_order_id mapping', 'symbol
    resolution') survives as a non-identifier and is filtered out by the roster
    intersection rather than by a hand-maintained exclusion list.
    """
    head = verb.split("(", 1)[0]
    return [part.strip() for part in head.split("/") if part.strip()]


def _arc014_roster_grades(home: Path) -> dict[str, str]:
    """Map each §2A broker-order identifier to its ARC 014 grade."""
    roster = _spec_identifiers(home, "### broker-order")
    grades: dict[str, str] = {}
    for verb, grade in _arc014_findings(home):
        for name in _normalise_verb(verb):
            if name in roster:
                grades[name] = grade
    return grades


# ===========================================================================
# PROBES — each returns (integer, detail). Detail goes to stderr.
# ===========================================================================


def _p_registry_check_count(home: Path) -> tuple[int, str]:
    payload = json.loads(_read(home, "checks/registry.json"))
    names = sorted({c for b in payload["blocks"] for c in b["checks"]})
    return len(names), "registry.json: " + ", ".join(names)


def _p_checks_glob_count(home: Path) -> tuple[int, str]:
    files = sorted(p.name for p in (home / "checks").glob("check_*.py"))
    return len(files), "checks/*.py on disk: " + ", ".join(files)


def _p_pytest_ast_count(home: Path) -> tuple[int, str]:
    total = 0
    files = sorted((home / "scripts" / "tests").glob("test_*.py"))
    if not files:
        raise ProbeError("scripts/tests holds no test_*.py")
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            total += _parametrize_multiplier(node, path)
    return total, f"{len(files)} test module(s), parametrize expanded"


def _parametrize_multiplier(node: ast.AST, path: Path) -> int:
    """How many collected items one test function becomes."""
    cases = 1
    for deco in getattr(node, "decorator_list", []):
        if not isinstance(deco, ast.Call):
            continue
        if "parametrize" not in ast.unparse(deco.func):
            continue
        values = deco.args[1] if len(deco.args) > 1 else None
        if not isinstance(values, (ast.List, ast.Tuple)):
            raise ProbeError(
                f"{path.name}: parametrize argvalues is not a literal sequence — "
                "the AST count cannot be trusted; register a different source"
            )
        cases *= len(values.elts)
    return cases


def _p_pinned_deps_count(home: Path) -> tuple[int, str]:
    payload = json.loads(_read(home, "checks/pinned_deps.json"))
    names = sorted(payload["packages"])
    return len(names), "pinned: " + ", ".join(names)


def _debt_rows(home: Path) -> list[str]:
    text = _read(home, "docs/CHECK-DEBT.md")
    return [ln for ln in text.splitlines() if re.match(r"^\|\s*D[123]\.\d+\s*\|", ln)]


#: THE RULE OF RECORD for whether a debt row is paid, quoted from `docs/CHECK-DEBT.md`:
#: "a row is discharged iff some **bold** span in it matches `discharged ARC <n>`".
#:
#: CORRECTED ARC 018 Phase 4. This probe previously tested `"discharged" not in ln.lower()`
#: — a bare substring scan over the whole row. That is precisely the rule the ledger note
#: warns against ("the bold-span restriction is load-bearing, not cosmetic"), so the harness
#: was not implementing the rule its own ledger states, and had not been since ARC 017. It
#: went unnoticed because no open row happened to contain the exact word "discharged": D3.5
#: says "discharges", which the naive scan misses by one letter.
#:
#: ARC 018 broke it for real. Three open rows were counted as paid — D2.14 and D2.15 whose
#: bodies read "**NARROWED ARC 018, NOT DISCHARGED.**", and D1.19 whose body cites
#: "discharged D1.18". The count came back 26 against a hand-derived 29, and the three-row
#: gap is exactly those rows. A ledger that cannot say "not discharged" without marking
#: itself paid is the instrument being its own defect (`VERIFY-AND-CHECKS.md` Part C).
_DISCHARGED = re.compile(r"\*\*[^*]*\bdischarged ARC \d+", re.IGNORECASE)


def _p_check_debt_open_count(home: Path) -> tuple[int, str]:
    rows = _debt_rows(home)
    if not rows:
        raise ProbeError("docs/CHECK-DEBT.md: no D1./D2./D3. rows matched")
    open_ids = [
        re.match(r"^\|\s*(D[123]\.\d+)", ln).group(1)  # type: ignore[union-attr]
        for ln in rows
        if not _DISCHARGED.search(ln)
    ]
    return len(open_ids), f"{len(rows)} rows, open: {', '.join(open_ids)}"


def _p_check_debt_series_latest(home: Path) -> tuple[int, str]:
    text = _read(home, "docs/CHECK-DEBT.md")
    rows = re.findall(
        r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(ARC \d+)\s*\|\s*(\d+)\s*\|",
        text,
        re.MULTILINE,
    )
    if not rows:
        raise ProbeError("docs/CHECK-DEBT.md: series table has no dated rows")
    arc, stated = rows[-1]
    return int(stated), f"latest series row is {arc} stating {stated} open"


def _p_spec_order_identifier_count(home: Path) -> tuple[int, str]:
    names = _spec_identifiers(home, "### broker-order")
    return len(names), "§2A broker-order by identifier: " + ", ".join(names)


def _p_seam_order_roster_count(home: Path) -> tuple[int, str]:
    tuples = _module_tuples(
        home, "scripts/broker/broker_seam.py", ("ORDER_PORT_VERBS", "ORDER_EVENTS")
    )
    total = sum(len(v) for v in tuples.values())
    parts = ", ".join(f"{k}={len(v)}" for k, v in sorted(tuples.items()))
    return total, f"broker_seam.py {parts}"


def _p_arc014_roster_covered(home: Path) -> tuple[int, str]:
    grades = _arc014_roster_grades(home)
    roster = _spec_identifiers(home, "### broker-order")
    ungraded = [n for n in roster if n not in grades]
    detail = f"{len(grades)} of {len(roster)} §2A broker-order elements graded"
    if ungraded:
        detail += f"; UNGRADED: {', '.join(ungraded)}"
    return len(grades), detail


def _p_arc014_grade_tally_sum(home: Path) -> tuple[int, str]:
    grades = _arc014_roster_grades(home)
    tally: dict[str, int] = {}
    for grade in grades.values():
        tally[grade] = tally.get(grade, 0) + 1
    breakdown = ", ".join(f"{g} {n}" for g, n in sorted(tally.items()))
    return sum(tally.values()), f"re-derived over the §2A roster: {breakdown}"


def _p_order_path_anchor_files(home: Path) -> tuple[int, str]:
    """`.py` files under the gate's STATED anchor `ORDER_PATH_DIRS` (ARC 018, D2.15).

    The anchor constant is read out of `check_order_path_bans.py` by AST rather
    than retyped here — retyping it would make this probe a restatement of the
    thing it is supposed to check, inside the instrument built to catch that.
    """
    rel = "checks/check_order_path_bans.py"
    dirs = _module_tuples(home, rel, ("ORDER_PATH_DIRS",))["ORDER_PATH_DIRS"]
    if not dirs:
        raise ProbeError(f"{rel}: ORDER_PATH_DIRS is empty")
    files = sorted({p for d in dirs for p in (home / d).rglob("*.py") if p.is_file()})
    return len(files), f"anchor {list(dirs)}: " + ", ".join(p.name for p in files)


# --------------------------------------------------------------------------
# BROKER-ORDER ELEMENT COVERAGE — scheme `sec2a-element-v1`.
# --------------------------------------------------------------------------
# RENAMED ARC 020 (operator ruling) from `broker_order_percent_sec2a_element_v1`
# to `broker_order_element_coverage_v1`. THE RENAME IS A FRAMING CORRECTION, NOT
# A NEW MEASUREMENT: the scheme identifier is unchanged, both probes below
# compute exactly what they computed before, and the claim's cross-derivation —
# a denominator read out of the frozen spec against a denominator read out of
# the seam code — survives intact. What changed is the NAME, which now carries
# the limitation instead of hiding it.
#
# Definition, so the series is reproducible and a scheme change is visible:
#
#   coverage(level) = 100 * |roster elements graded CLEAN| / |roster|
#   roster          = the broker-order element set of the frozen spec's
#                     section 2A, BY IDENTIFIER
#   grades          = ARC 014's FINDINGS, re-derived over that roster
#
# Both terms are re-derived on every run; neither is stored anywhere.
#
# THIS IS BREADTH AND IT IS BLIND TO DEPTH. It answers one question — how many
# of the specified broker-order elements has anybody graded CLEAN — and no
# other. It does not move when a defect inside an already-CLEAN element is
# found, and it does not move when one is fixed. ARC 019 is the measured
# instance: an arc that closed four defects, discovered five more, corrected a
# banked performance figure fivefold and produced the module's first Tier-3
# traversal registered as ZERO MOVEMENT under this scheme — correctly, because
# it added no elements. A number that cannot see the best arc the module has had
# is not a progress number, and the old name said it was one.
#
# "PERCENT MOVED" IS RETIRED AS A FRAMING FOR THIS SCHEME. A change in this
# level is a change in ELEMENT COVERAGE, is named as such, and is never
# presented as how far the module moved. The companion depth figure is the claim
# `broker_order_open_debt_rows` below, which is DELIBERATELY NOT A PERCENT.
#
# NO CONFIDENCE DIMENSION IS INVENTED HERE, and that is a decision rather than
# an omission. A per-element confidence score would be a hand-maintained rubric,
# which is the stale literal anchor this whole harness exists to remove; adding
# one would put the defect back inside the instrument built to catch it.
_SCHEME_ID = "sec2a-element-v1"


def _clean_fraction(roster: list[str], grades: dict[str, str]) -> tuple[int, int, int]:
    """(clean, total, integer percent) for one roster under one grade map."""
    if not roster:
        raise ProbeError("empty roster — a percent over nothing is not a percent")
    clean = sum(1 for name in roster if grades.get(name) == "CLEAN")
    return clean, len(roster), 100 * clean // len(roster)


def _p_broker_order_coverage_spec(home: Path) -> tuple[int, str]:
    """Scheme `sec2a-element-v1`, denominator from the FROZEN SPEC."""
    roster = _spec_identifiers(home, "### broker-order")
    clean, total, pct = _clean_fraction(roster, _arc014_roster_grades(home))
    return pct, (
        f"scheme {_SCHEME_ID}, spec denominator: ELEMENT COVERAGE — CLEAN "
        f"{clean} of {total} section 2A broker-order identifiers = {pct}% "
        "(breadth, blind to depth; a level, not a per-arc delta)"
    )


def _p_broker_order_coverage_seam(home: Path) -> tuple[int, str]:
    """Scheme `sec2a-element-v1`, denominator from the CODE's restatement."""
    tuples = _module_tuples(
        home, "scripts/broker/broker_seam.py", ("ORDER_PORT_VERBS", "ORDER_EVENTS")
    )
    roster = list(tuples["ORDER_PORT_VERBS"]) + list(tuples["ORDER_EVENTS"])
    grades: dict[str, str] = {}
    for verb, grade in _arc014_findings(home):
        for name in _normalise_verb(verb):
            if name in roster:
                grades[name] = grade
    clean, total, pct = _clean_fraction(roster, grades)
    return pct, (
        f"scheme {_SCHEME_ID}, seam denominator: ELEMENT COVERAGE — CLEAN "
        f"{clean} of {total} broker_seam.py ORDER_PORT_VERBS+ORDER_EVENTS "
        f"= {pct}% (breadth, blind to depth)"
    )


# --------------------------------------------------------------------------
# BROKER-ORDER OPEN DEBT ROWS — the depth companion, and NOT a percent.
# --------------------------------------------------------------------------
# ARC 020 C2. Element coverage above is breadth. This is the other axis: how
# many OPEN debts in the ledger are about the broker-order module. It rises when
# a traversal finds defects and falls when they are paid, which is exactly the
# movement the coverage figure cannot see.
#
# IT IS A COUNT AND IT MUST NEVER BE EXPRESSED AS A PERCENT. To make a percent
# of it one would have to divide by a total, and the only honest total is "how
# many outstanding obligations does this module have" — which is the same
# quantity as "how much do we trust this module", and is unknowable. That is
# named gap 5 verbatim: the standing question's condition 7 above says this
# instrument cannot prove the registry covers the numbers that matter, so the
# denominator would be the size of a set nobody can enumerate. A percent over an
# unknowable denominator is a confidence score wearing arithmetic, and inventing
# one here would rebuild the rubric the rename in the block above just removed.
# Twelve open rows is twelve open rows. It is a FLOOR on outstanding broker-order
# obligations, never a fraction of them.
#
# THE MODULE-SCOPING RULE, stated so it can be argued with rather than inferred:
#
#   A row is BROKER-ORDER SCOPED iff it is OPEN — by the ledger's own bold-span
#   rule, `_DISCHARGED` above — AND its row text names at least one order-path
#   artefact, being either
#     (i)  the basename of a Python module that exists under the order path AND
#          does NOT implement the broker-datafeed port, or
#     (ii) a broker-order roster identifier, matched on word boundaries.
#
# NOTHING IN THAT RULE IS TYPED. The order path is read by AST out of
# `check_order_path_bans.py`'s own `ORDER_PATH_DIRS` anchor — the same
# non-restating technique `_p_order_path_anchor_files` uses — and the basenames
# come off the disk. The roster comes from the frozen spec on one side of the
# claim and from the seam's declared tuples on the other, which is where the two
# sources get their independence.
#
# THE "AND DOES NOT IMPLEMENT THE DATAFEED PORT" CLAUSE IS ARC 022 (C3), AND IT
# IS THE REPAIR OF A MEASURED CONTAMINATION — debt row D2.19. Until ARC 022 the
# basename half was the raw directory glob, so EVERY `.py` under `scripts/broker`
# was an order-path vocabulary term regardless of which §2A library it belongs
# to. Two distinct contaminations followed, both measured on this tree rather
# than reasoned about:
#
#   * A SHARED HOST. `ibkr_mapping.py` carries BOTH §2A adapters, so a row about
#     its datafeed half was counted as broker-order depth. That is D2.19's
#     original subject and it moved `broker_order_open_debt_rows` 11 -> 13 in
#     ARC 021 while nothing touched broker-order.
#   * A DATAFEED-ONLY MODULE ON THE ORDER PATH. `broker_datafeed_ibkr.py` landed
#     in ARC 021 and lives under `scripts/broker/` because that is where §2A code
#     lives — so the glob made the DATAFEED ADAPTER'S OWN BASENAME an order-path
#     vocabulary term, and D1.13, D3.9 and D3.10 (three rows with no order roster
#     identifier anywhere in them) were counted as broker-order depth. D2.19
#     predicted the arrival of a datafeed-only module would SELF-HEAL this; it
#     healed the datafeed side's basename half and made the ORDER side worse.
#
# The clause says the thing the glob could not: a basename attributes to a
# library only when it is DISTINCTIVE to that library. It is the exact mirror of
# `_datafeed_only_modules` below, which has always subtracted the order port, and
# the subtraction is derived from the seam's own `DATAFEED_PORT_VERBS` — nothing
# is listed by hand, so a third §2A module joins or leaves the vocabulary by
# being written.
#
# WHAT THE CLAUSE DELIBERATELY DOES NOT DO — the residual, named because ARC 021
# named this ambiguity before it bit and it bit anyway:
#   f. THE ROSTER HALF IS NOT MADE DISTINCTIVE, AND IT CARRIES THE SAME DEFECT.
#      `connect` and `disconnect` are in BOTH §2A rosters. The datafeed claim
#      subtracts them; this one cannot, because they are genuinely broker-order
#      verbs too and an order row about `connect()` is real order debt. MEASURED
#      CONSEQUENCE ON THIS TREE: D1.38 — a row whose entire subject is
#      `BrokerDatafeedPort`'s sync/async split — is selected here, on the single
#      word `connect`. It is left selected rather than papered over, because the
#      only mechanical repairs are worse than the disease: dropping the shared
#      verbs blinds the order claim to every real connect/disconnect row, and
#      requiring two roster hits blinds it to single-verb rows. This residual is
#      recorded in D2.19 and stays open with it.
#   g. A SHARED HOST NOW NEEDS CORROBORATION FROM THE ROSTER HALF, WHICH IS PROSE.
#      A row genuinely about `ibkr_mapping.py`'s ORDER half that names no order
#      roster identifier is now invisible here. That is disclosure (c) — the rule
#      reads prose — pointed at the shared host specifically, and it is the price
#      of not counting the datafeed half. The mitigation is unchanged and weak:
#      every selected row id is printed on every run.
#
# WHAT IS AMBIGUOUS, named rather than papered over — the rule attributes rows
# to a module MECHANICALLY, and mechanical attribution is not the same as
# correct attribution:
#
#  a. APPARATUS-ABOUT-THE-MODULE versus DEFECT-IN-THE-MODULE. Two selected rows
#     are not defects in the order path at all. One is a residual in the gate
#     that scans the order path; the other is a test instrument that happens to
#     live in a seam module. Both are genuine outstanding broker-order
#     obligations and both are counted. Whether "scoped to broker-order" means
#     defects IN the code or obligations ABOUT it is a judgment, and this rule
#     does not make it — it counts both, and this paragraph is why.
#  b. IT UNDER-COUNTS ROWS THAT TALK ABOUT THE MODULE WITHOUT NAMING ANYTHING IN
#     IT. A row deferred until "broker-order code exists" names no artefact and
#     is not selected, correctly by the rule and arguably wrongly in substance.
#  c. THE RULE READS PROSE, so the ledger's wording is load-bearing. Rewording a
#     row to drop the verb name silently removes it from the count. That is
#     failure mode #14 one level down — a scope set by text a person edits — and
#     the mitigation is that every selected id is printed on every run.
#  d. A ROW IS NOT A DEFECT. One selected row lists five observed symptoms of a
#     single repair; another holds two separate specification gaps. The claim
#     counts the ledger's unit of account, which is the row, and the number is
#     therefore a floor and not a census.
#  e. THE TWO ROSTERS CAN LEGITIMATELY DIVERGE. If the seam declares a
#     broker-order element the spec does not — a flagged Nix addition, the
#     `feed_lag()` precedent — the seam-side vocabulary gains a word the
#     spec-side one lacks and the sources can disagree. That is the same
#     derive-never-restate pair the coverage claim already carries, one level up,
#     and a disagreement is the instrument working rather than a defect in it.


def _order_path_basenames(home: Path) -> tuple[list[str], list[str]]:
    """Order-DISTINCTIVE `.py` basenames under the order path, and what was cut.

    Returns `(distinctive, excluded)`. Both anchors are read by AST and never
    typed: the directory list comes out of `check_order_path_bans.py`'s own
    `ORDER_PATH_DIRS`, and the datafeed subtraction comes out of the seam's
    `DATAFEED_PORT_VERBS`. See the D2.19 block above for why the subtraction
    exists — a module that implements the datafeed port cannot say, by basename
    alone, which §2A library a row about it is about.
    """
    rel = "checks/check_order_path_bans.py"
    dirs = _module_tuples(home, rel, ("ORDER_PATH_DIRS",))["ORDER_PATH_DIRS"]
    if not dirs:
        raise ProbeError(f"{rel}: ORDER_PATH_DIRS is empty")
    on_path = sorted(
        {p.name for d in dirs for p in (home / d).rglob("*.py") if p.is_file()}
    )
    if not on_path:
        raise ProbeError(f"order path {list(dirs)} holds no .py module to name")

    seam = "scripts/broker/broker_seam.py"
    tuples = _module_tuples(home, seam, ("ORDER_PORT_VERBS", "DATAFEED_PORT_VERBS"))
    feed = _port_implementors(home, list(tuples["DATAFEED_PORT_VERBS"]), 3)
    order = _port_implementors(home, list(tuples["ORDER_PORT_VERBS"]), 4)

    names = [n for n in on_path if n not in feed]
    excluded = [n for n in on_path if n in feed]
    # NON-VACUITY, and it is the whole point of the subtraction being safe: the
    # surviving vocabulary must still hold a module that actually implements the
    # ORDER port. A seam edit that made every order module look like a datafeed
    # module would otherwise empty this list silently and the claim would report
    # a smaller number having measured less.
    if not set(names) & order:
        raise ProbeError(
            f"order-path vocabulary {names} holds no module implementing the "
            f"order port (order implementors: {sorted(order)}); the datafeed "
            f"subtraction removed {excluded} and left nothing distinctive"
        )
    return names, excluded


def _open_debt_rows(home: Path) -> list[tuple[str, str]]:
    """(id, row text) for every row the ledger's bold-span rule leaves OPEN."""
    rows = _debt_rows(home)
    if not rows:
        raise ProbeError("docs/CHECK-DEBT.md: no D1./D2./D3. rows matched")
    out = [
        (re.match(r"^\|\s*(D[123]\.\d+)", ln).group(1), ln)  # type: ignore[union-attr]
        for ln in rows
        if not _DISCHARGED.search(ln)
    ]
    if not out:
        raise ProbeError("docs/CHECK-DEBT.md: every row reads discharged")
    return out


#: A roster identifier immediately preceded by `<name>.` is an ATTRIBUTE of
#: `<name>`, not the port verb. See `_roster_hit`.
_QUALIFIER = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.$")


def _order_path_owners(home: Path) -> set[str]:
    """Receiver names a roster verb may legitimately hang off: order-path module
    basenames (without `.py`) and the classes those modules declare."""
    rel = "checks/check_order_path_bans.py"
    dirs = _module_tuples(home, rel, ("ORDER_PATH_DIRS",))["ORDER_PATH_DIRS"]
    owners: set[str] = set()
    for directory in dirs:
        for path in (home / directory).rglob("*.py"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            owners.add(path.stem)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except OSError, SyntaxError:
                continue
            owners |= {
                node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
            }
    return owners


def _roster_hit(text: str, roster: list[str], owners: set[str]) -> bool:
    """True when `text` names an order roster identifier AS AN ORDER VERB.

    ARC 025 / C4, THE QUALIFIED-IDENTIFIER SUBTRACTION, and it is the D2.19
    principle applied to the roster half instead of to the basename half: a name
    attributes to a library only when it is DISTINCTIVE to that library, and a
    name qualified by a receiver that owns no order-path code is not.

    MEASURED INSTANCE, which is why this exists rather than being reasoned into
    place: D1.41's entire subject is two Gateway gates dialling one endpoint. It
    names no order artefact and no order verb — it was selected on the single
    word `connect` inside the phrase `socket.connect`, the name of the spy that
    took the measurement. `\\bconnect\\b` matches there because `.` is a word
    boundary. `socket` owns no order-path module and no order-path class, so the
    hit is discarded; `IBKRBrokerOrder.disconnect()` and `broker_order_ibkr.flatten`
    survive, because those receivers do.
    """
    for name in roster:
        for match in re.finditer(r"\b" + re.escape(name) + r"\b", text):
            qualifier = _QUALIFIER.search(text[: match.start()])
            if qualifier is None or qualifier.group(1) in owners:
                return True
    return False


def _row_cells(line: str) -> list[str]:
    """A ledger row's cells. `[0]` is the id, `[1]` is the row's own subject."""
    return [cell.strip() for cell in line.split("|")][1:]


def _owned_by_its_instrument(
    rid: str, line: str, on_path: list[str], roster: list[str], owners: set[str]
) -> bool:
    """Is this row's OWNING artefact an order-path one?

    ARC 025 / C4. Applied to D3 rows only, and the restriction is read out of the
    ledger's OWN column headers rather than chosen: D3 is titled *"Instruments
    whose can-fail has never been demonstrated"* and its header row is
    `# | instrument | status | owner`, so **a D3 row's subject is declared by the
    ledger to be an INSTRUMENT**. Its `status` cell is evidence ABOUT that
    instrument, and the artefacts a piece of can-fail evidence recites are the
    instrument's test material, not the row's owner.

    D1 (`# | subject | changed in | owner`) and D2 (`# | doctrine | gap | owner`)
    are deliberately NOT restricted this way, and the difference is structural
    rather than convenient: a D1 subject is a DEFECT DESCRIPTION and a D2
    doctrine cell is a CITATION, so in both tables the module attribution
    legitimately lives in the body. Measured: restricting D1/D2 to their first
    cell drops seven rows that are genuinely order-side (D1.19, D1.22, D1.28,
    D1.29, D1.30, D1.31, D1.38 among them), which is doctrine B.4's forbidden
    direction — narrowing a rule's scope until the number looks better.

    MEASURED INSTANCE: D3.20's subject is *"the ten checks NOT retrofitted in ARC
    024..."*. It was selected as broker-order depth because its status cell
    recites another gate's plant — *"`import tenacity` planted into the real
    `broker_order_ibkr.py`"*. The row is owed against a CHECK. D3.8 survives:
    its instrument cell is *"`RecordingSink.sequence` — the cross-stream ordering
    observable in `scripts/broker/broker_seam.py`"*, which names a module on the
    order path.

    `on_path` is the RAW order-path module set, before D2.19's
    datafeed-distinctiveness subtraction, and that is deliberate: this test asks
    *"is the row's instrument a broker-path artefact at all"*, not *"which §2A
    library does this basename attribute to"*. D3.8's instrument is in
    `broker_seam.py`, which the distinctiveness rule excludes from the ATTRIBUTION
    vocabulary and which is unarguably on the order path.
    """
    if not rid.startswith("D3"):
        return True
    cells = _row_cells(line)
    subject = cells[1] if len(cells) > 1 else ""
    return any(name in subject for name in on_path) or _roster_hit(
        subject, roster, owners
    )


def _broker_order_scoped(home: Path, roster: list[str]) -> tuple[int, str]:
    """Apply the module-scoping rule with one supplied roster vocabulary."""
    if not roster:
        raise ProbeError("empty roster — the scope vocabulary would select nothing")
    files, excluded = _order_path_basenames(home)
    owners = _order_path_owners(home)
    on_path = sorted(set(files) | set(excluded))
    picked = [
        rid
        for rid, line in _open_debt_rows(home)
        if (any(f in line for f in files) or _roster_hit(line, roster, owners))
        and _owned_by_its_instrument(rid, line, on_path, roster, owners)
    ]
    return len(picked), (
        f"NOT A PERCENT — open ledger rows OWNED BY an order-path artefact; "
        f"vocabulary {len(files)} order-distinctive module(s) {files} "
        f"(D2.19: {len(excluded)} datafeed-implementing module(s) {excluded or '[]'} "
        f"on the order path are NOT vocabulary) + {len(roster)} roster "
        f"identifier(s), qualified hits subtracted against {len(owners)} "
        f"order-path owner name(s) (C4); D3 rows attributed by their INSTRUMENT "
        f"cell; selected: {', '.join(picked) or 'NONE'}"
    )


def _p_broker_order_debt_rows_spec(home: Path) -> tuple[int, str]:
    """Scoping vocabulary's roster half read from the FROZEN SPEC."""
    return _broker_order_scoped(home, _spec_identifiers(home, "### broker-order"))


def _p_broker_order_debt_rows_seam(home: Path) -> tuple[int, str]:
    """Scoping vocabulary's roster half read from the SEAM CODE's restatement."""
    tuples = _module_tuples(
        home, "scripts/broker/broker_seam.py", ("ORDER_PORT_VERBS", "ORDER_EVENTS")
    )
    roster = list(tuples["ORDER_PORT_VERBS"]) + list(tuples["ORDER_EVENTS"])
    return _broker_order_scoped(home, roster)


_SEAM_TUPLES = (
    "ORDER_PORT_VERBS",
    "ORDER_EVENTS",
    "DATAFEED_PORT_VERBS",
    "DATAFEED_EVENTS",
)


def _p_seam_declared_total(home: Path) -> tuple[int, str]:
    tuples = _module_tuples(home, "scripts/broker/broker_seam.py", _SEAM_TUPLES)
    parts = ", ".join(f"{k}={len(tuples[k])}" for k in _SEAM_TUPLES)
    return sum(len(v) for v in tuples.values()), f"broker_seam.py {parts}"


def _flagged_addition(source: str, name: str) -> bool:
    """True when `name`'s own docstring names it a Nix addition."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        if node.name == name and "nix addition" in doc.lower():
            return True
    return False


def _p_spec_plus_flagged_additions(home: Path) -> tuple[int, str]:
    spec_order = set(_spec_identifiers(home, "### broker-order"))
    spec_feed = set(_spec_identifiers(home, "### broker-datafeed"))
    tuples = _module_tuples(home, "scripts/broker/broker_seam.py", _SEAM_TUPLES)
    source = _read(home, "scripts/broker/broker_seam.py")

    code_order = set(tuples["ORDER_PORT_VERBS"]) | set(tuples["ORDER_EVENTS"])
    code_feed = set(tuples["DATAFEED_PORT_VERBS"]) | set(tuples["DATAFEED_EVENTS"])
    extras = sorted((code_order - spec_order) | (code_feed - spec_feed))

    flagged = [n for n in extras if _flagged_addition(source, n)]
    unflagged = [n for n in extras if n not in flagged]
    base = len(spec_order) + len(spec_feed)
    detail = (
        f"§2A both libraries by identifier = {base}; "
        f"flagged Nix additions {flagged or '[]'}"
    )
    if unflagged:
        detail += f"; UNFLAGGED seam elements (not counted): {', '.join(unflagged)}"
    return base + len(flagged), detail


# --------------------------------------------------------------------------
# BROKER-DATAFEED — ARC 021 (B3). The second §2A library's claims.
# --------------------------------------------------------------------------
# The datafeed roster and the order roster SHARE `connect`/`disconnect`, so a
# vocabulary built from the raw datafeed roster would select every order row
# that mentions connecting. Every probe below therefore works on the
# DISTINCTIVE vocabulary — the datafeed roster minus the order roster — and the
# subtraction is derived from the same two sources as the roster itself.


def _spec_datafeed_flagged(home: Path) -> tuple[list[str], list[str]]:
    """(§2A datafeed identifiers, flagged Nix additions on the datafeed port)."""
    spec_feed = _spec_identifiers(home, "### broker-datafeed")
    tuples = _module_tuples(
        home,
        "scripts/broker/broker_seam.py",
        ("DATAFEED_PORT_VERBS", "DATAFEED_EVENTS"),
    )
    code_feed = list(tuples["DATAFEED_PORT_VERBS"]) + list(tuples["DATAFEED_EVENTS"])
    source = _read(home, "scripts/broker/broker_seam.py")
    extras = [n for n in code_feed if n not in spec_feed]
    return spec_feed, [n for n in extras if _flagged_addition(source, n)]


def _p_spec_datafeed_plus_flagged(home: Path) -> tuple[int, str]:
    """§2A's datafeed roster PLUS the additions the seam flags as Nix's own.

    The bare §2A count cannot be compared with the seam's, and that is not a
    defect on either side: `feed_lag()` is a declared Nix addition and §2A is
    frozen. This is `seam_declared_elements`' mechanism narrowed to one library
    so the datafeed's own drift is visible rather than averaged into a
    both-libraries total.
    """
    spec_feed, flagged = _spec_datafeed_flagged(home)
    unflagged_detail = ""
    tuples = _module_tuples(
        home,
        "scripts/broker/broker_seam.py",
        ("DATAFEED_PORT_VERBS", "DATAFEED_EVENTS"),
    )
    code_feed = list(tuples["DATAFEED_PORT_VERBS"]) + list(tuples["DATAFEED_EVENTS"])
    unflagged = [n for n in code_feed if n not in spec_feed and n not in flagged]
    if unflagged:
        unflagged_detail = f"; UNFLAGGED (not counted): {', '.join(unflagged)}"
    return len(spec_feed) + len(flagged), (
        f"§2A broker-datafeed by identifier: {', '.join(spec_feed)}; "
        f"flagged Nix additions {flagged or '[]'}{unflagged_detail}"
    )


def _p_seam_datafeed_roster_count(home: Path) -> tuple[int, str]:
    tuples = _module_tuples(
        home,
        "scripts/broker/broker_seam.py",
        ("DATAFEED_PORT_VERBS", "DATAFEED_EVENTS"),
    )
    total = sum(len(v) for v in tuples.values())
    parts = ", ".join(f"{k}={len(v)}" for k, v in sorted(tuples.items()))
    return total, f"broker_seam.py {parts}"


def _port_implementors(home: Path, verbs: list[str], quorum: int) -> set[str]:
    """Module basenames under scripts/ defining `quorum` of `verbs` as methods."""
    out: set[str] = set()
    for path in sorted((home / "scripts").rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = {
                b.name
                for b in node.body
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if len(methods & set(verbs)) >= quorum:
                out.add(path.name)
    return out


def _datafeed_only_modules(home: Path) -> list[str]:
    """Modules implementing the datafeed port and NOT the order port.

    TODAY THIS IS EMPTY, and that is the honest answer rather than a defect:
    the only class implementing the datafeed port outside the seam lives in
    `ibkr_mapping.py`, which implements the order port too, so counting its
    basename would select order rows as datafeed debt. A dedicated datafeed
    module joins this set by being written — no edit here.
    """
    tuples = _module_tuples(
        home,
        "scripts/broker/broker_seam.py",
        ("ORDER_PORT_VERBS", "DATAFEED_PORT_VERBS"),
    )
    feed = _port_implementors(home, list(tuples["DATAFEED_PORT_VERBS"]), 3)
    order = _port_implementors(home, list(tuples["ORDER_PORT_VERBS"]), 4)
    return sorted(feed - order)


def _datafeed_scoped(home: Path, feed: list[str], order: list[str]) -> tuple[int, str]:
    """The module-scoping rule, datafeed edition, with one supplied vocabulary."""
    distinctive = [n for n in feed if n not in order]
    if not distinctive:
        raise ProbeError("datafeed roster is a subset of the order roster")
    files = _datafeed_only_modules(home)
    pats = [re.compile(r"\b" + re.escape(name) + r"\b") for name in distinctive]
    picked = [
        rid
        for rid, line in _open_debt_rows(home)
        if any(f in line for f in files) or any(p.search(line) for p in pats)
    ]
    return len(picked), (
        f"NOT A PERCENT — open ledger rows naming a broker-datafeed artefact; "
        f"vocabulary {len(files)} datafeed-only module(s) {files or '[]'} + "
        f"{len(distinctive)} distinctive identifier(s) {distinctive}; "
        f"selected: {', '.join(picked) or 'NONE'}"
    )


def _p_datafeed_debt_rows_spec(home: Path) -> tuple[int, str]:
    """Vocabulary's roster half read from the FROZEN SPEC (plus flagged additions)."""
    spec_feed, flagged = _spec_datafeed_flagged(home)
    return _datafeed_scoped(
        home, spec_feed + flagged, _spec_identifiers(home, "### broker-order")
    )


def _p_datafeed_debt_rows_seam(home: Path) -> tuple[int, str]:
    """Vocabulary's roster half read from the SEAM CODE's restatement."""
    tuples = _module_tuples(home, "scripts/broker/broker_seam.py", _SEAM_TUPLES)
    feed = list(tuples["DATAFEED_PORT_VERBS"]) + list(tuples["DATAFEED_EVENTS"])
    order = list(tuples["ORDER_PORT_VERBS"]) + list(tuples["ORDER_EVENTS"])
    return _datafeed_scoped(home, feed, order)


PROBES = {
    "registry_check_count": _p_registry_check_count,
    "checks_glob_count": _p_checks_glob_count,
    "pytest_ast_count": _p_pytest_ast_count,
    "pinned_deps_count": _p_pinned_deps_count,
    "check_debt_open_count": _p_check_debt_open_count,
    "check_debt_series_latest": _p_check_debt_series_latest,
    "spec_order_identifier_count": _p_spec_order_identifier_count,
    "seam_order_roster_count": _p_seam_order_roster_count,
    "arc014_roster_covered": _p_arc014_roster_covered,
    "arc014_grade_tally_sum": _p_arc014_grade_tally_sum,
    "seam_declared_total": _p_seam_declared_total,
    "spec_plus_flagged_additions": _p_spec_plus_flagged_additions,
    "order_path_anchor_files": _p_order_path_anchor_files,
    "broker_order_coverage_spec": _p_broker_order_coverage_spec,
    "broker_order_coverage_seam": _p_broker_order_coverage_seam,
    "broker_order_debt_rows_spec": _p_broker_order_debt_rows_spec,
    "broker_order_debt_rows_seam": _p_broker_order_debt_rows_seam,
    "spec_datafeed_plus_flagged": _p_spec_datafeed_plus_flagged,
    "seam_datafeed_roster_count": _p_seam_datafeed_roster_count,
    "datafeed_debt_rows_spec": _p_datafeed_debt_rows_spec,
    "datafeed_debt_rows_seam": _p_datafeed_debt_rows_seam,
}


# ===========================================================================
# SOURCE EXECUTION — every source is a command, run in its own process.
# ===========================================================================


def _argv_for(source: dict, home: Path) -> list[str]:
    subs = {
        "{nix_home}": str(home),
        "{checks_dir}": str(home / "checks"),
        "{system_python}": sys.executable,
        "{venv_python}": str(home / ".venv" / "bin" / "python3"),
        "{self}": str(Path(__file__).resolve()),
    }
    if "probe" in source:
        raw = [
            "{system_python}",
            "{self}",
            "--probe",
            source["probe"],
            "--nix-home",
            "{nix_home}",
        ]
    else:
        raw = list(source["argv"])
    out = []
    for token in raw:
        for key, value in subs.items():
            token = token.replace(key, value)
        out.append(token)
    return out


def _child_env() -> dict[str, str]:
    """The environment every source subprocess runs in — colour NEUTRALISED.

    ARC 025 / C4b. MEASURED DEFECT, not a hypothetical, and it had been live for
    an arc: `pytest_collected_tests`'s collector source anchors its extraction at
    `(?m)^(\\d+) tests? collected`, and pytest emits SGR sequences into a
    CAPTURED pipe whenever `FORCE_COLOR` is set in the ambient environment. The
    Claude Code harness exports `FORCE_COLOR=3`, so the summary line arrives as
    `ESC[32mESC[32m441 tests collected...` — no digit at column 0 — the
    extraction fails, and the claim silently degrades to NOT MEASURED. Measured
    verdict either side of one environment variable, nothing else changed:
    `13/13 claim(s) compared` exit 0 with it unset, `12/13` and CANNOT_MEASURE
    with it set. `docs/CHECK-CONTRACT-AMENDMENTS.md` item 8 records the
    discovery and owes the repair to this arc.

    **AN INSTRUMENT WHOSE COVERAGE IS A FUNCTION OF THE INVOKING SHELL IS NOT
    MEASURING ITS SUBJECT.** It failed in the safe direction — cannot-measure,
    never a wrong number — which makes it a coverage defect rather than a
    correctness one, and coverage defects are the ones that go unnoticed.

    The repair is HERE, at the source runner, and not in the one regex that
    happened to break. Widening that regex would have fixed one claim and left
    the next source someone registers exposed to the same ambient state; every
    source in this registry produces a NUMBER, so colour is contamination in all
    of them. `NO_COLOR` and `TERM=dumb` are the two conventions tools honour;
    `FORCE_COLOR` and `CLICOLOR_FORCE` are removed rather than overridden
    because both are truthy for any value including `"0"` in some tools.

    `_extract` additionally strips ANSI from what it reads, which is the second
    half rather than a duplicate of the first: this half stops the environment
    causing colour, that half survives a tool that colours for its own reasons
    (a config file, a `--color=always` someone registers in an argv). Neither
    alone closes the defect for a source nobody has written yet.
    """
    env = dict(os.environ)
    env.pop("FORCE_COLOR", None)
    env.pop("CLICOLOR_FORCE", None)
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    return env


def _extract(source: dict, stdout: str) -> int:
    stdout = _ANSI.sub("", stdout)
    if source.get("count_lines"):
        return len([ln for ln in stdout.splitlines() if ln.strip()])
    pattern = source.get("extract")
    match = re.search(pattern, stdout) if pattern else _INT_ONLY.match(stdout)
    if not match:
        raise ProbeError(f"no integer in output: {stdout.strip()[:200]!r}")
    return int(match.group(1))


def _run_source(source: dict, home: Path) -> tuple[int | None, str]:
    """Execute one source. Returns (value|None, detail)."""
    argv = _argv_for(source, home)
    try:
        proc = subprocess.run(  # nosec B603 - argv from a repo-controlled registry
            argv,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
            cwd=str(home),
            env=_child_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"did not run: {exc!r}"
    if proc.returncode != 0 and not source.get("extract"):
        return None, f"exit {proc.returncode}: {proc.stderr.strip()[:300]}"
    try:
        return _extract(source, proc.stdout), proc.stderr.strip()[:300]
    except (ProbeError, ValueError) as exc:
        return None, f"{exc}"


def _missing_files(source: dict, home: Path) -> list[str]:
    return [rel for rel in source.get("files", []) if not (home / rel).exists()]


def _scan_restatements(claim: dict, home: Path, agreed: int) -> tuple[list[str], str]:
    """Every restatement of this number, wherever it is written, must be right."""
    defects: list[str] = []
    seen = 0
    for scan in claim.get("restatement_scans", []):
        path = home / scan["file"]
        if not path.exists():
            defects.append(f"{scan['file']}: registered restatement file is missing")
            continue
        for match in re.finditer(scan["pattern"], path.read_text(encoding="utf-8")):
            seen += 1
            if int(match.group(1)) != agreed:
                defects.append(
                    f"{scan['file']} restates {match.group(1)}, derived {agreed}"
                )
    return defects, f"{seen} restatement(s) found"


# ===========================================================================


def _collect_values(
    sources: list[dict], home: Path, cid: str
) -> tuple[list[tuple[str, str]], dict[str, int], list[str]]:
    """Run every source once. A missing file is a defect, never a skip (§7.12/5)."""
    defects: list[tuple[str, str]] = []
    values: dict[str, int] = {}
    notes: list[str] = []
    for source in sources:
        missing = _missing_files(source, home)
        if missing:
            defects.append(
                (
                    f"{REGISTRY}:{cid}/{source['name']}",
                    f"missing file(s): {', '.join(missing)}",
                )
            )
            continue
        value, detail = _run_source(source, home)
        if value is None:
            notes.append(f"{source['name']} unmeasurable ({detail})")
            continue
        values[f"{source['role']}:{source['name']}"] = value
        if detail:
            notes.append(f"{source['name']}: {detail}")
    return defects, values, notes


def _evaluate_claim(claim: dict, home: Path) -> tuple[list[tuple[str, str]], str, bool]:
    """Returns (defects, evidence, measured)."""
    sources = claim.get("sources", [])
    cid = claim["id"]
    if len(sources) < 2:
        return [], f"{cid}: fewer than two sources (§7.12 condition 2)", False

    identities = [s.get("probe") or " ".join(s.get("argv", [])) for s in sources]
    if len(set(identities)) != len(identities):
        return [], f"{cid}: duplicate sources (§7.12 condition 3)", False

    defects, values, notes = _collect_values(sources, home, cid)

    if len(values) < 2:
        joined = "; ".join(notes) or "no sources produced a number"
        return defects, f"{cid}: NOT MEASURED — {joined}", False

    distinct = set(values.values())
    rendered = ", ".join(f"{k}={v}" for k, v in sorted(values.items()))
    if len(distinct) != 1:
        defects.append((f"{REGISTRY}:{cid}", f"sources disagree — {rendered}"))
        return defects, f"{cid}: DISAGREEMENT {rendered} | {'; '.join(notes)}", True

    agreed = distinct.pop()
    scan_defects, scan_note = _scan_restatements(claim, home, agreed)
    for message in scan_defects:
        defects.append((f"{REGISTRY}:{cid}", message))
    return defects, f"{cid}={agreed} [{rendered}; {scan_note}]", True


# ===========================================================================
# DEMONSTRATION CLAIMS — ARC 023 (B3). A claim that cannot be re-executed is
# not a claim. See §7.12 condition 10 in the module docstring for the measured
# instance (CHECK-DEBT D1.14 / D3.15) this arm exists to catch.
# ===========================================================================

DEMOS = "demonstrations"
_STATES = ("performs", "does-not-perform")


def _demo_output(demo: dict, home: Path) -> tuple[str | None, str]:
    """Re-execute the demonstration. Returns (combined output | None, complaint).

    Anything that prevents the re-execution from happening is a complaint, which
    the caller turns into CANNOT_MEASURE — never into a FAIL. A demonstration
    that could not be re-run has not been shown to have stopped performing.
    """
    spec = demo["reexecute"]
    argv = _argv_for({"argv": spec["argv"]}, home)
    try:
        proc = subprocess.run(  # nosec B603 - argv from a repo-controlled registry
            argv,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
            cwd=str(home),
            env=_child_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"re-execution did not run: {exc!r}"
    accept = spec.get("accept_exit")
    if accept is not None and proc.returncode not in accept:
        return (
            None,
            f"re-execution exited {proc.returncode}, outside accept_exit {accept}",
        )
    # ANSI stripped for the same reason `_extract` strips it: the `observe`
    # patterns are anchored to the re-executed check's own words, and a colour
    # sequence landing inside one turns a two-state observation into
    # INDETERMINATE — a cannot-measure caused by the shell, not the subject.
    return _ANSI.sub("", proc.stdout + proc.stderr), ""


def _demo_observed(demo: dict, output: str) -> tuple[str | None, str]:
    """Read the demonstration's state out of its own output. None = indeterminate."""
    hits = [state for state in _STATES if re.search(demo["observe"][state], output)]
    if len(hits) != 1:
        return None, (
            f"observation INDETERMINATE — {len(hits)} of the two patterns matched "
            f"{hits}; a pattern that stopped matching is never a verdict (§7.4)"
        )
    return hits[0], ""


def _demo_stale(demo: dict, home: Path) -> str:
    """'' if the banked assertion is still where the registry says it is."""
    banked = demo["banked"]
    if not (home / banked["file"]).exists():
        return f"{banked['file']} is absent — the banked assertion cannot be located"
    if not re.search(banked["pattern"], _read(home, banked["file"])):
        return (
            f"nothing in {banked['file']} still asserts this demonstration — the "
            f"registration outlived the claim, or the claim was reworded without "
            f"re-registering it"
        )
    return ""


def _evaluate_demo(
    demo: dict, home: Path, open_rows: set[str]
) -> tuple[list[tuple[str, str]], str, bool]:
    """One demonstration. Returns (defects, line, measured)."""
    did = demo["id"]
    site = f"{REGISTRY}:{DEMOS}/{did}"
    stale = _demo_stale(demo, home)
    if stale:
        return [(site, stale)], f"{did}: STALE REGISTRATION", True
    declared = demo["currently"]
    owed = demo.get("owed_row", "")
    if declared == "does-not-perform" and owed not in open_rows:
        return (
            [
                (
                    site,
                    (
                        f"declared {declared!r} against owed_row {owed!r}, which is not "
                        f"an OPEN row of docs/CHECK-DEBT.md — a demotion may not "
                        f"outlive its debt"
                    ),
                )
            ],
            f"{did}: ORPHANED DEMOTION",
            True,
        )
    output, complaint = _demo_output(demo, home)
    if output is None:
        return [], f"{did}: NOT MEASURED — {complaint}", False
    observed, why = _demo_observed(demo, output)
    if observed is None:
        return [], f"{did}: NOT MEASURED — {why}", False
    if observed != declared:
        return (
            [
                (
                    site,
                    (
                        f"registered as {declared!r}; the re-execution observed "
                        f"{observed!r} — a banked demonstration changed state and "
                        f"nothing else in this tree would have said so"
                    ),
                )
            ],
            f"{did}: {observed} != registered {declared}",
            True,
        )
    return [], f"{did}={observed}" + (f" (owed {owed})" if owed else ""), True


def _evaluate_claims(
    claims: list[dict], home: Path
) -> tuple[list[tuple[str, str]], list[str], int]:
    """Every registered claim, re-derived. Returns (defects, lines, measured).

    Extracted from `run()` ARC 023 so that adding the demonstration arm did not
    push one function past pylint's local-variable ceiling — the arms are
    symmetrical in shape, so they are symmetrical in the code as well.
    """
    defects: list[tuple[str, str]] = []
    lines: list[str] = []
    measured = 0
    for claim in claims:
        claim_defects, line, was_measured = _evaluate_claim(claim, home)
        defects.extend(claim_defects)
        lines.append(line)
        measured += int(was_measured)
    return defects, lines, measured


def _evaluate_demonstrations(
    demos: list[dict], home: Path
) -> tuple[list[tuple[str, str]], list[str], int]:
    """Every registered demonstration, re-executed. Returns (defects, lines, measured)."""
    open_rows = {rid for rid, _ in _open_debt_rows(home)}
    defects: list[tuple[str, str]] = []
    lines: list[str] = []
    measured = 0
    for demo in demos:
        demo_defects, line, was_measured = _evaluate_demo(demo, home, open_rows)
        defects.extend(demo_defects)
        lines.append(line)
        measured += int(was_measured)
    return defects, lines, measured


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Re-derive every registered claim and compare. Never repairs a document."""
    try:
        registry_path = Path(__file__).resolve().parent / REGISTRY
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        claims = payload["claims"]
        demos = payload.get(DEMOS, [])
        if not claims:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{REGISTRY} registers no claims (§7.12 condition 1)",
            )
        if not demos:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{REGISTRY} registers no demonstrations (§7.12 condition 10) "
                f"— an arm with no subject is never a PASS",
            )
        defects, lines, measured = _evaluate_claims(claims, ctx.nix_home)
        demo_defects, demo_lines, demo_measured = _evaluate_demonstrations(
            demos, ctx.nix_home
        )
        defects.extend(demo_defects)
        evidence = (
            f"{measured}/{len(claims)} claim(s) compared — "
            + " | ".join(lines)
            + f" || {demo_measured}/{len(demos)} demonstration(s) re-executed — "
            + " | ".join(demo_lines)
        )
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        if measured != len(claims) or demo_measured != len(demos):
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=evidence)
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a crashed gate measured nothing — exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


def _probe_main(argv: list[str]) -> int:
    """`--probe NAME --nix-home PATH`: print one integer, detail on stderr."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--nix-home", required=True)
    args = parser.parse_args(argv)
    probe = PROBES.get(args.probe)
    if probe is None:
        print(f"unknown probe {args.probe!r}", file=sys.stderr)
        return 2
    try:
        value, detail = probe(Path(args.nix_home))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(detail, file=sys.stderr)
    print(value)
    return 0


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    # `--probe NAME --nix-home PATH` is this gate re-entering itself as one
    # source's runner ({self} in derived_claims.json). Not an actuation verb,
    # and intercepted before `parse_actuation`, which would reject it.
    if "--probe" in sys.argv[1:]:
        sys.exit(_probe_main(sys.argv[1:]))

    from nixverify.actuation import standalone_main

    # THIS ALSO DISCHARGES CHECK-DEBT D2.23, and it is worth naming because the
    # row is the reason this gate's own can-fail nearly measured the wrong tree.
    # The previous block resolved `HOME` from `__file__` and read `sys.argv` only
    # for `--probe`, so any other argument was discarded WITHOUT A WORD: running
    # `check_derived_claims.py <scratch>` from this worktree reported a serene
    # green over a defect planted in the scratch tree, because it had measured
    # this one. `standalone_main` takes the home as a positional like every
    # sibling gate, and `parse_actuation` REFUSES an argument it does not
    # recognise instead of ignoring it — which is the stricter of the two
    # discharges D2.23 offers, and the one doctrine C.7 asks for.
    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
