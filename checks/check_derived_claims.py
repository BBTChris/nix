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
    (`order_path_scope_files`, `broker_order_percent_sec2a_element_v1`, and the
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
"""

from __future__ import annotations

import argparse
import ast
import json
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
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_derived_claims"

REGISTRY = "derived_claims.json"
_INT_ONLY = re.compile(r"^\s*(-?\d+)\s*$")
_TIMEOUT = 300


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
# C4 — THE BROKER-ORDER PERCENT SCHEME, `sec2a-element-v1`.
# --------------------------------------------------------------------------
# Definition, so the series is reproducible and a scheme change is visible:
#
#   percent(level) = 100 * |roster elements graded CLEAN| / |roster|
#   roster         = the §2A broker-order element set, BY IDENTIFIER
#   grades         = ARC 014's FINDINGS, re-derived over that roster
#
# and an arc's "percent moved" is the CHANGE in that level, in percentage
# points, over the same denominator. Both terms are re-derived on every run;
# neither is stored anywhere.
_SCHEME_ID = "sec2a-element-v1"


def _clean_fraction(roster: list[str], grades: dict[str, str]) -> tuple[int, int, int]:
    """(clean, total, integer percent) for one roster under one grade map."""
    if not roster:
        raise ProbeError("empty roster — a percent over nothing is not a percent")
    clean = sum(1 for name in roster if grades.get(name) == "CLEAN")
    return clean, len(roster), 100 * clean // len(roster)


def _p_broker_order_percent_spec(home: Path) -> tuple[int, str]:
    """Scheme `sec2a-element-v1`, denominator from the FROZEN SPEC."""
    roster = _spec_identifiers(home, "### broker-order")
    clean, total, pct = _clean_fraction(roster, _arc014_roster_grades(home))
    return pct, (
        f"scheme {_SCHEME_ID}, spec denominator: CLEAN {clean} of {total} "
        f"§2A broker-order identifiers = {pct}% (level, not a per-arc delta)"
    )


def _p_broker_order_percent_seam(home: Path) -> tuple[int, str]:
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
        f"scheme {_SCHEME_ID}, seam denominator: CLEAN {clean} of {total} "
        f"broker_seam.py ORDER_PORT_VERBS+ORDER_EVENTS = {pct}%"
    )


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
    "broker_order_percent_spec": _p_broker_order_percent_spec,
    "broker_order_percent_seam": _p_broker_order_percent_seam,
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


def _extract(source: dict, stdout: str) -> int:
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


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Re-derive every registered claim and compare. Never repairs a document."""
    try:
        registry_path = Path(__file__).resolve().parent / REGISTRY
        claims = json.loads(registry_path.read_text(encoding="utf-8"))["claims"]
        if not claims:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{REGISTRY} registers no claims (§7.12 condition 1)",
            )
        defects: list[tuple[str, str]] = []
        lines: list[str] = []
        measured = 0
        for claim in claims:
            claim_defects, line, was_measured = _evaluate_claim(claim, ctx.nix_home)
            defects.extend(claim_defects)
            lines.append(line)
            measured += int(was_measured)

        evidence = f"{measured}/{len(claims)} claim(s) compared — " + " | ".join(lines)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        if measured != len(claims):
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
    if "--probe" in sys.argv[1:]:
        sys.exit(_probe_main(sys.argv[1:]))

    from nixverify.contract import exit_code_for, validate_result

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
