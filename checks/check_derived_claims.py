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
    is what a reviewer checks. `registered_check_count` (registry vs disk) and
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
#: ARC 025 Stage 2.4 — `subprocess:python3` added after the runtime observer
#: caught it. The `venv` claim covered the pytest collector, which runs under
#: `{venv_python}`; it did NOT cover this gate's OWN probe subprocesses, which
#: re-enter this module as `{self} --probe` under whatever interpreter is
#: running — `/usr/bin/python3` when invoked from `verify.py`, per §9.5. Ten of
#: the thirteen claims are measured that way, so the undeclared program was the
#: one doing most of the work.
RESOURCES: tuple[str, ...] = ("venv", "subprocess:python3")
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


def _module_level_importorskip_target(tree: ast.Module) -> str | None:
    """The module name a TOP-LEVEL `pytest.importorskip(...)` guards, or None.

    ARC CRUCIBLE-DEPSPLIT. Only `tree.body` (the module's own top-level
    statements), never `ast.walk` — a guard nested in a function or an `if`
    does not run at import time and cannot make the whole module uncollectable
    the way a bare module-level call does. `pytest.importorskip` raises
    `Skipped` DURING COLLECTION when its target is not importable, and pytest
    reports the entire module as ONE collected (skipped) item rather than
    walking it for individual `test_*` functions — a real collection-time
    effect the AST count must predict, not merely a runtime skip mark
    (`@pytest.mark.skipif`, which still collects one item per function
    normally and needs no adjustment here).
    """
    for stmt in tree.body:
        call = stmt.value if isinstance(stmt, ast.Expr) else None
        if not isinstance(call, ast.Call):
            continue
        if ast.unparse(call.func) != "pytest.importorskip":
            continue
        if not call.args or not isinstance(call.args[0], ast.Constant):
            continue
        if isinstance(call.args[0].value, str):
            return call.args[0].value
    return None


def _importable_under(venv_python: Path, module_name: str) -> bool | None:
    """Is `module_name` importable under `venv_python`? None if unknown.

    A subprocess, not a static guess — the only way to answer "will pytest's
    collector actually walk this module's functions" is to ask the same
    interpreter pytest itself runs under (`_p_pytest_ast_count`'s docstring
    below; mirrors `check_python_deps.py`'s own §9.4 reasoning: never import
    the target here, ask a disposable subprocess instead). Returns None
    (unknown, not False) when the venv itself cannot answer — a probe that
    collapsed "no venv" into "not importable" would turn a CANNOT_MEASURE
    condition into a wrong number instead of an honest unknown.
    """
    if not venv_python.is_file():
        return None
    try:
        code = f"import importlib.util as u,sys;sys.exit(0 if u.find_spec({module_name!r}) else 1)"
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [str(venv_python), "-c", code],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return proc.returncode == 0


def _p_pytest_ast_count(home: Path) -> tuple[int, str]:
    """Statically predict what `pytest --collect-only` will report.

    ARC CRUCIBLE-DEPSPLIT / D3.111's own venv split exposed the gap this
    function used to have: a module guarded by a top-level
    `pytest.importorskip("pandas_market_calendars", ...)` (the ONE file that
    legitimately imports the Crucible calendar generator,
    `test_crucible_calendar_gen.py`) always used to import successfully,
    because the generator's dependency lived in the SAME shared venv pytest
    ran under. Once the runtime venv genuinely stopped carrying that
    dependency (Success #1), the guard started firing for real, and the real
    pytest collector — correctly — stopped walking that module's 9 `test_*`
    functions and reported ONE collected (skipped) item for it instead. A
    purely-textual AST count that does not know this has no way to predict
    that collapse, so it kept counting 9 — a genuine, previously-latent
    disagreement between two sources that DERIVE the same property by
    different means (§7.12 point 3), now real rather than coincidental.
    """
    files = sorted((home / "scripts" / "tests").glob("test_*.py"))
    if not files:
        raise ProbeError("scripts/tests holds no test_*.py")
    venv_python = home / ".venv" / "bin" / "python3"
    counts = [_count_one_file(path, venv_python) for path in files]
    total = sum(n for n, _ in counts)
    collapsed = [note for _, note in counts if note is not None]
    detail = f"{len(files)} test module(s), parametrize expanded"
    if collapsed:
        detail += f"; collapsed by importorskip: {', '.join(collapsed)}"
    return total, detail


def _count_functions(tree: ast.Module, path: Path) -> int:
    """Plain per-function static count, parametrize expanded."""
    total = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        total += _parametrize_multiplier(node, path)
    return total


def _count_one_file(path: Path, venv_python: Path) -> tuple[int, str | None]:
    """One file's contribution to the collect-only tally, plus a collapse note.

    Split out of `_p_pytest_ast_count` (ARC CRUCIBLE-DEPSPLIT) to keep that
    function's own cognitive complexity low — this is where the
    importorskip-collapse branching actually lives.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    guard_target = _module_level_importorskip_target(tree)
    if guard_target is None:
        return _count_functions(tree, path), None
    if _importable_under(venv_python, guard_target) is False:
        # Verified empirically (ARC CRUCIBLE-DEPSPLIT): a module-level
        # `pytest.importorskip` that fires contributes ZERO to
        # `pytest --collect-only`'s own "N tests collected" tally — not
        # one. It DOES show up as "1 skipped" in a real (non-collect-only)
        # run's terminal summary, but that is a different count than the
        # one this probe's sibling source (`pytest_collector`,
        # `(?m)^(\d+) tests? collected`) reads.
        return 0, f"{path.name}(importorskip {guard_target!r})"
    # True or None (unknown/no venv): fall through to the normal
    # per-function count — either it really does import (collects
    # normally) or the venv cannot answer and the honest fallback is the
    # plain static count, same as before this function existed.
    return _count_functions(tree, path), None


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
    # `ARC [\w-]+` rather than `ARC \d+` (CHECK-DEBT D3.112): every row was
    # numbered until ARC CRUCIBLE-CALENDAR-INFRA, whose brief deliberately
    # withheld a number (the next sequential one, ARC 030, is already
    # CHECK-DEBT D3.104's named owner for unrelated work). A numeric-only
    # pattern went blind to that row's own summary line, producing a real
    # DISAGREEMENT against an otherwise-clean tree. Widened to accept any
    # word/hyphen arc token; still requires the literal "ARC " prefix.
    rows = re.findall(
        r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(ARC [\w-]+)\s*\|\s*(\d+)\s*\|",
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
    # AppleDouble sidecars (`._name.py`, ARC 030 CHECK-DEBT D3.110) match
    # `*.py` and would inflate this DERIVED count against a sidecar that is not
    # code — the exact "tree scanning itself" class D3.110 names, one layer
    # over from a crash: this site never parses content, so it would not
    # crash, but it would silently miscount. Excluded by NAME, matching
    # check_order_path_bans.py's own scan of the same anchor.
    files = sorted(
        {
            p
            for d in dirs
            for p in (home / d).rglob("*.py")
            if p.is_file() and not p.name.startswith("._")
        }
    )
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
# OPEN DEBT ROWS BY OWNING MODULE — the depth companion, and NOT a percent.
# --------------------------------------------------------------------------
# ARC 020 C2 opened this axis: element coverage is BREADTH, this is DEPTH — how
# many OPEN ledger rows a module owes. It rises when a traversal finds defects
# and falls when they are paid, which is the movement coverage cannot see.
#
# IT IS A COUNT AND IT MUST NEVER BE EXPRESSED AS A PERCENT. A percent needs a
# denominator, and the only honest one is "how many outstanding obligations does
# this module have" — the same quantity as "how much do we trust this module",
# and unknowable. A percent over an unknowable denominator is a confidence score
# wearing arithmetic. Nine open rows is nine open rows: a FLOOR on outstanding
# obligations, never a fraction of them.
#
# ============================================================================
# ARC 026 (B3) — SELECTION IS BY AUTHORED COLUMN. THE PROSE SCAN IS GONE.
# ============================================================================
# The rule of record now lives in `docs/CHECK-DEBT.md` ("The `owning module`
# column is AUTHORED, never inferred from prose") and this harness READS it
# rather than restating it — the vocabulary below is parsed out of the ledger's
# own table, so a token added there is a token accepted here with no edit.
#
# WHAT WAS REMOVED, and why removal was the repair rather than a fifth narrowing.
# Until this arc a row was selected if ANY text anywhere in it matched an
# order-path module basename or a roster identifier. Four contaminations, each
# repaired by narrowing the vocabulary and none by changing the mechanism:
#
#   * ARC 021 — `ibkr_mapping.py` hosts both §2A adapters; a row about its
#     datafeed half counted as broker-order depth (11 -> 13, untouched module).
#   * ARC 021 — `broker_datafeed_ibkr.py` lives on the order path because that
#     is where §2A code lives, so the DATAFEED adapter's basename became
#     order-path vocabulary and pulled in three rows with no order verb in them.
#   * ARC 025 — D1.41 entered the metric on the single word `connect`, inside
#     the phrase `socket.connect`: THE SPY THAT TOOK ARC 024'S MEASUREMENT
#     CONTAMINATED THE METRIC MEASURING IT. Repaired by subtracting qualified
#     identifiers whose receiver owns no order-path code.
#   * ARC 025's own residual, stated and not closeable inside the mechanism:
#     selection reads PROSE, so rewording a row moves the count silently
#     (`debug.md` §8 failure mode #14, one level down), and a row about a verb
#     both rosters share cannot be attributed at all.
#
# Each narrowing made the vocabulary smaller and left the mechanism intact, so a
# fifth contamination was one wording away. An authored column ends the class:
# attribution is a judgment a person makes once, visible in a diff, and prose is
# no longer load-bearing.
#
# WHAT IS STILL TRUE OF THE NUMBER, carried forward because it was true before:
#  a. APPARATUS-ABOUT-THE-MODULE vs DEFECT-IN-THE-MODULE is now DECIDED rather
#     than counted both ways. The ledger's rule is "the artefact that must CHANGE
#     to discharge the row", so a row about a gate is owned by the gate even when
#     the gate measures broker-datafeed. That is a position; the prose scan took
#     no position and counted both, which is why it counted things twice.
#  b. A ROW IS NOT A DEFECT. One row can hold five symptoms of a single repair.
#     The claim counts the ledger's unit of account, so it is a floor.
#  c. THE COLUMN IS STILL WRITTEN BY A PERSON. It can be wrong. What it cannot
#     be is wrong INVISIBLY: a wrong token is one word in a diff, where the old
#     mechanism's failures were a word buried in a paragraph nobody was reading
#     as an attribution.


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


#: The ledger's vocabulary table. Read, never restated — a token list typed here
#: would be the derive-never-restate defect inside the instrument built to catch
#: it, which `derived_claims.json` records happening in an arc brief itself.
_VOCAB_ROW = re.compile(r"^\|\s*`([a-z][a-z-]*)`\s*\|", re.MULTILINE)
#: The stated per-module tally — the claim's SECOND source. See the ledger's
#: "Stated per-module tally" block for why an authored column needs one.
_TALLY_ROW = re.compile(r"^\|\s*([a-z][a-z-]*)\s*\|\s*(\d+)\s*\|\s*$", re.MULTILINE)


def _owning_vocabulary(home: Path) -> set[str]:
    """The legal `owning module` tokens, parsed out of the ledger itself."""
    tokens = set(_VOCAB_ROW.findall(_read(home, "docs/CHECK-DEBT.md")))
    if not tokens:
        raise ProbeError(
            "docs/CHECK-DEBT.md: the owning-module vocabulary table parsed to "
            "nothing — with no legal tokens every row would be rejected, and a "
            "count over a rejected population is not a count"
        )
    return tokens


def _owning_module(line: str) -> str:
    """The row's LAST cell. Empty when the row carries no column at all."""
    stripped = line.rstrip()
    if not stripped.endswith("|"):
        return ""
    return stripped[:-1].rsplit("|", 1)[-1].strip()


def _open_rows_by_module(home: Path) -> dict[str, list[str]]:
    """Open row ids grouped by authored owning module. FAILS CLOSED.

    A row with no column, an empty column, or a token outside the ledger's own
    vocabulary is a **ProbeError naming the row**, never a silent exclusion. The
    failure mode this column replaces was exactly a row leaving a count without
    anybody noticing, and a lenient parser would rebuild it one layer down.
    """
    vocabulary = _owning_vocabulary(home)
    grouped: dict[str, list[str]] = {token: [] for token in vocabulary}
    unattributed: list[str] = []
    for rid, line in _open_debt_rows(home):
        token = _owning_module(line)
        if token not in vocabulary:
            unattributed.append(f"{rid}={token or '<absent>'}")
            continue
        grouped[token].append(rid)
    if unattributed:
        raise ProbeError(
            "docs/CHECK-DEBT.md: open row(s) carry no valid `owning module` "
            f"token: {', '.join(unattributed)}; legal tokens are "
            f"{sorted(vocabulary)}"
        )
    return grouped


def _stated_tally(home: Path) -> dict[str, int]:
    """The ledger's hand-written per-module tally — the STATED source."""
    tally = {
        name: int(count)
        for name, count in _TALLY_ROW.findall(_read(home, "docs/CHECK-DEBT.md"))
    }
    vocabulary = _owning_vocabulary(home)
    if not tally:
        raise ProbeError(
            "docs/CHECK-DEBT.md: the stated per-module tally parsed to nothing — "
            "the claim would then have one source, which is unchecked by "
            "construction"
        )
    alien = sorted(set(tally) - vocabulary)
    if alien:
        raise ProbeError(
            f"docs/CHECK-DEBT.md: the tally names {alien}, which the "
            "owning-module vocabulary does not contain"
        )
    return tally


def _module_depth_derived(home: Path, module: str) -> tuple[int, str]:
    """Count of OPEN rows the ledger's column attributes to `module`."""
    grouped = _open_rows_by_module(home)
    if module not in grouped:
        raise ProbeError(
            f"docs/CHECK-DEBT.md: {module!r} is not in the owning-module "
            f"vocabulary {sorted(grouped)} — the claim would count a module the "
            "ledger cannot express"
        )
    picked = grouped[module]
    total = sum(len(ids) for ids in grouped.values())
    return len(picked), (
        f"NOT A PERCENT — OPEN ledger rows whose AUTHORED `owning module` column "
        f"reads {module!r}; {total} open row(s) attributed across "
        f"{len(grouped)} module(s); selected: {', '.join(picked) or 'NONE'}"
    )


def _module_depth_stated(home: Path, module: str) -> tuple[int, str]:
    """What the ledger's own tally table SAYS `module` owes."""
    tally = _stated_tally(home)
    if module not in tally:
        raise ProbeError(
            f"docs/CHECK-DEBT.md: the stated per-module tally has no row for "
            f"{module!r} (it names {sorted(tally)}) — an absent row would read "
            "as zero, and zero is a claim"
        )
    return tally[module], (
        f"stated by the ledger's per-module tally: {module}={tally[module]} "
        f"(whole tally: {', '.join(f'{k}={v}' for k, v in sorted(tally.items()))})"
    )


def _p_broker_order_debt_rows_ledger(home: Path) -> tuple[int, str]:
    """DERIVED: the row scan over the authored column."""
    return _module_depth_derived(home, "broker-order")


def _p_broker_order_debt_rows_tally(home: Path) -> tuple[int, str]:
    """STATED: the ledger's own per-module tally."""
    return _module_depth_stated(home, "broker-order")


def _p_datafeed_debt_rows_ledger(home: Path) -> tuple[int, str]:
    """DERIVED: the row scan over the authored column."""
    return _module_depth_derived(home, "broker-datafeed")


def _p_datafeed_debt_rows_tally(home: Path) -> tuple[int, str]:
    """STATED: the ledger's own per-module tally."""
    return _module_depth_stated(home, "broker-datafeed")


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
    "broker_order_debt_rows_ledger": _p_broker_order_debt_rows_ledger,
    "broker_order_debt_rows_tally": _p_broker_order_debt_rows_tally,
    "spec_datafeed_plus_flagged": _p_spec_datafeed_plus_flagged,
    "seam_datafeed_roster_count": _p_seam_datafeed_roster_count,
    "datafeed_debt_rows_ledger": _p_datafeed_debt_rows_ledger,
    "datafeed_debt_rows_tally": _p_datafeed_debt_rows_tally,
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
