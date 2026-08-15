#!/usr/bin/env python3
"""The §0c classifier, DRIVEN — `scripts/nixverify/measurement_path.py`.

CHECK-DEBT D3.120, discharge route (a). `measurement_path.py` decides whether
a retrofitted check KEEPS its can-fail binding, so it is load-bearing for
every binding claim in the tree — and until this gate existed it was the one
piece of that machinery no `checks/check_*.py` named as a SUBJECT. It sat in
`gate_coverage_baseline.json`'s ratchet instead, was re-owned once per arc,
and ARC 030's pre-close re-point pushed it over the operator's ceiling of two.
**The ceiling breach flagged an overdue MEASUREMENT, not an overdue escape
hatch** (architect ruling, ARC 031 / 0.3): this gate is the measurement, and
the row leaves the ratchet because it is COVERED, not because it was excused.

WHAT IS MEASURED, and it is the direction that matters. The classifier's
dangerous verdict is `DECLARATION_ONLY`, because that is the one that
PRESERVES a binding — a classifier drifting toward "measurement-path" is
merely pessimistic and costs bindings it should have kept, while one drifting
toward "declaration-only" silently certifies a can-fail that no longer holds.
So every arm below plants a subject whose CORRECT verdict is known, and each
one whose correct verdict is `MEASUREMENT_PATH` is a real drive of the
classifier toward its wrong answer. A wrong classification reddens this gate
and NAMES THE SITE (§18 — never the exit code alone).

§7.12 THE STANDING QUESTION — what would have to be true for this gate to
PASS while measuring nothing?

 1. The subject could fail to import. CLOSED: `CANNOT_MEASURE` naming the
    exception (§17 — never a PASS).
 2. It could import the WRONG file. `checks/_preamble.py` appends the real
    repository's `scripts/` to `sys.path` permanently, so a name-based import
    resolves against the live tree no matter which tree this gate was pointed
    at — the defect `check_d1_12_reboot_capture`'s first draft shipped and its
    own can-fail caught. CLOSED: loaded by
    `importlib.util.spec_from_file_location` against the EXACT path under
    `ctx.nix_home`, and the loaded module's `__file__` is asserted to be that
    path.
 3. Every arm could assert a verdict the classifier reaches for an unrelated
    reason — a plant classified MEASUREMENT_PATH because its imports moved
    would "prove" the closure rule while exercising none of it. CLOSED: each
    plant changes exactly ONE thing, and the arms that turn on the closure
    additionally assert WHICH REASON was given, not merely the verdict.
 4. The closure arm could pass under a classifier rooted at `run` alone —
    which is the naive implementation, and the one condition 1 of the
    subject's own docstring exists to refuse. CLOSED: ARM 1 drives a
    FALSIFIER closure (rooted at `run` only, built from the subject's own
    `_split`) over the SAME plant and requires it to LOSE the finding. If the
    falsifier still catches it, the plant was not probing the second root and
    the arm is worthless — so that is itself a finding.
 5. The audit half (`changed_paths`) could be certified by a range that
    resolves to zero files, which classifies every check as declaration-only
    in silence. CLOSED: ARM 6 drives the real refusal against the real
    repository with `HEAD..HEAD` and requires `RangeError`.
 6. The whole gate could be green because no arm ran — an exception in arm 3
    skipping arms 4-6. CLOSED: every arm returns its findings, the arms run
    unconditionally, and the evidence line states the arm count that actually
    executed.

WHAT IS NOT MEASURED, stated rather than implied. This gate drives the
classifier's DECISION over synthetic subjects. It does not re-derive
condition 10 (same-name-different-behaviour at run time), which the subject's
own docstring names as its unguarded edge; a gate cannot close an edge its
subject declares open.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# The load/Finding/arm shape is deliberately the same as its sibling gates —
# a per-artifact driving check has one honest shape and diverging from it to
# satisfy a duplication metric would make the family harder to audit, not
# easier.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
    "subprocess:git",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject decides whether a can-fail binding survives a retrofit; a "
    "repair that edited it to satisfy its own gate would be the instrument "
    "rewriting the rule it is measured against"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixverify/measurement_path.py",)

NAME = "check_measurement_path"

SUBJECT_FILE = "scripts/nixverify/measurement_path.py"


class Finding(NamedTuple):
    """One wrong classification. `site` names WHERE, `why` names the reason."""

    site: str
    why: str


def load(home: Path) -> tuple[ModuleType | None, str]:
    """Import the subject BY EXACT PATH out of `home`. Never by name.

    §7.12/2: a `sys.path` name search would resolve against the real
    repository's `scripts/` — which `checks/_preamble.py` appends permanently
    — and this gate would measure the live tree while believing it measured
    `home`. The path is built here and the loaded module's own `__file__` is
    compared back against it.
    """
    target = (home / SUBJECT_FILE).resolve()
    if not target.is_file():
        return None, (
            f"{SUBJECT_FILE}: no such file under {home} — the subject is "
            "unavailable, so nothing was measured (§17: never a PASS)"
        )
    try:
        spec = importlib.util.spec_from_file_location(
            "nix_check_measurement_path_subject", target
        )
        if spec is None or spec.loader is None:
            return None, f"{SUBJECT_FILE}: no import spec for {target}"
        module = importlib.util.module_from_spec(spec)
        # Registered BEFORE exec and left registered: the subject decorates
        # two `@dataclasses.dataclass(frozen=True)` classes, and dataclasses
        # resolves each class's own module out of `sys.modules` while the
        # decorator runs. An unregistered module makes that lookup return
        # None and the exec dies with `'NoneType' object has no attribute
        # '__dict__'` — an import failure that reads as CANNOT_MEASURE and
        # would have made this gate permanently unable to see its subject.
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{SUBJECT_FILE}: cannot load {target} — "
            f"{type(exc).__name__}: {exc}. Nothing was measured (§17)"
        )
    loaded_from = Path(getattr(module, "__file__", "")).resolve()
    if loaded_from != target:
        return None, (
            f"{SUBJECT_FILE}: loaded {loaded_from}, not {target} — the gate "
            "would be measuring a different file than the one under test"
        )
    return module, ""


# --------------------------------------------------------------------------
# Plant material. Every pair differs in exactly ONE thing (§7.12/3).
# --------------------------------------------------------------------------

#: A check-shaped module whose `run()` reads a constant and whose only path to
#: `_probe` is the `__main__` block — the subject's own condition 1, in the
#: smallest source that can carry it.
_BASE = '''"""Planted subject."""
import json

RESOURCES = ("venv",)
PRIVILEGE = "user"
_TIMEOUT = {timeout}


def _probe():
    return {probe!r}


def _probe_main():
    print(json.dumps(_probe()))


def run(mode, ctx):
    return _TIMEOUT


if __name__ == "__main__":
    _probe_main()
'''


#: A DECLARATION symbol consulted only by the standalone block — the shape
#: that makes the root set decide the verdict rather than merely the reason.
_MAIN_DECL = '''"""Planted subject."""
RESOURCES = ("venv",)
CORRECTABLE = {value}


def run(mode, ctx):
    return 1


if __name__ == "__main__":
    if CORRECTABLE:
        print("would correct")
'''


def _plant(*, timeout: int = 300, probe: str = "a") -> str:
    return _BASE.format(timeout=timeout, probe=probe)


def _verdict(
    module: ModuleType, before: str | None, after: str | None, **kwargs: object
) -> Any:
    """`classify_source` on the loaded subject, one plant pair.

    `Any` because the return type is the SUBJECT's `Classification`, defined
    in the file under test and loaded by path — annotating it against an
    imported copy would type this gate against a different module than the
    one it measures.
    """
    return module.classify_source("check_planted", before, after, **kwargs)


def _wrong(site: str, expected: str, got: Any, what: str) -> list[Finding]:
    """One finding, spelled the same way everywhere, or none."""
    if got.classification == expected:
        return []
    return [
        Finding(
            site,
            f"{what}: classifier said {got.classification!r} "
            f"(preserves_binding={got.preserves_binding}), expected "
            f"{expected!r}. Reasons given: {list(got.reasons) or 'NONE'}",
        )
    ]


# --------------------------------------------------------------------------
# ARM 1 — the closure is rooted at `__main__` too, not at `run` alone
# --------------------------------------------------------------------------


def _naive_closure(module: ModuleType, source: str) -> frozenset[str]:
    """The FALSIFIER: a closure rooted at `run` ALONE.

    Built from the subject's own `_split` so the only difference from the real
    `measurement_closure` is the root set — which is precisely the thing ARM 1
    claims to be measuring. Any other implementation difference would make the
    falsifier prove something else.
    """
    reduced = module._split(module.ast.parse(source))  # pylint: disable=protected-access
    frontier = {"run"} if "run" in reduced.bindings else set()
    closure: set[str] = set()
    while frontier:
        name = frontier.pop()
        if name in closure or name not in reduced.bindings:
            continue
        closure.add(name)
        frontier |= module._referenced(  # pylint: disable=protected-access
            reduced.bindings[name]
        )
    return frozenset(closure)


def _arm_main_block_root(module: ModuleType) -> list[Finding]:
    """Condition 1, driven where the root set actually FLIPS the verdict.

    A changed name that is neither a declaration symbol nor in the closure
    falls through to the subject's fail-closed branch and reads
    measurement-path anyway — so a plant on an ordinary helper cannot tell a
    `run`-rooted closure from the real one. The discriminator is a
    DECLARATION symbol reachable only from the `__main__` block, which is a
    real shape and not a contrivance: every check in this tree ends with a
    standalone block, and one that consults `CORRECTABLE` before honouring
    `--correct` puts a declaration squarely on the measurement path.
    Run-rooted, `CORRECTABLE` is excused as a declaration and the binding is
    PRESERVED; correctly rooted, it is a measurement edit.
    """
    site = f"{SUBJECT_FILE}:measurement_closure[__main__ root]"
    got = _verdict(
        module, _MAIN_DECL.format(value="True"), _MAIN_DECL.format(value="False")
    )
    findings = _wrong(
        site,
        module.MEASUREMENT_PATH,
        got,
        "a DECLARATION symbol reachable only from the __main__ block changed",
    )
    if not findings and not any("CORRECTABLE" in reason for reason in got.reasons):
        findings.append(
            Finding(
                site,
                "the verdict is right but no reason names `CORRECTABLE` — a "
                f"MEASUREMENT_PATH reached for some other cause: {list(got.reasons)}",
            )
        )
    # The falsifier must LOSE this. If a run-only closure still contains
    # `CORRECTABLE`, the plant is not probing the second root at all (§7.12/4).
    if "CORRECTABLE" in _naive_closure(module, _MAIN_DECL.format(value="False")):
        findings.append(
            Finding(
                f"{site}:falsifier",
                "a closure rooted at run() ALONE still contains `CORRECTABLE`, "
                "so this plant does not exercise the __main__ root and the arm "
                "above proves nothing about condition 1",
            )
        )
    # And the probe case, which is the one the subject's own docstring names:
    # `check_derived_claims` reaches all twenty-one of its probes ONLY through
    # its `__main__` block.
    after = _plant(probe="b")
    reached = module.measurement_closure(
        module._split(module.ast.parse(after))  # pylint: disable=protected-access
    )
    if "_probe" not in reached:
        findings.append(
            Finding(
                f"{site}:closure",
                "the REAL measurement_closure does not contain `_probe`, "
                "reachable only as __main__ -> _probe_main -> _probe — the "
                "twenty-one-probe hazard condition 1 names is wide open",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — a constant on the measurement path (condition 2)
# --------------------------------------------------------------------------


def _arm_constant(module: ModuleType) -> list[Finding]:
    site = f"{SUBJECT_FILE}:_compare_bindings[constant]"
    got = _verdict(module, _plant(timeout=300), _plant(timeout=5))
    findings = _wrong(
        site,
        module.MEASUREMENT_PATH,
        got,
        "a module-level CONSTANT that run() reads changed (300 -> 5)",
    )
    if not findings and not any("_TIMEOUT" in reason for reason in got.reasons):
        findings.append(
            Finding(
                site,
                f"no reason names `_TIMEOUT`: {list(got.reasons)}",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — the declaration allowance, BOTH directions (condition 3)
# --------------------------------------------------------------------------

#: `run()` reads its own `RESOURCES` — the aliasing trap. A declaration
#: symbol reachable from a root is a measurement symbol.
_ALIASED = '''"""Planted subject."""
RESOURCES = {resources}


def run(mode, ctx):
    return RESOURCES
'''


def _arm_declaration_allowance(module: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    allow_site = f"{SUBJECT_FILE}:_compare_bindings[declaration]"
    got = _verdict(
        module,
        _plant(),
        _plant().replace('RESOURCES = ("venv",)', 'RESOURCES = ("venv", "journal")'),
    )
    findings += _wrong(
        allow_site,
        module.DECLARATION_ONLY,
        got,
        "a declaration symbol run() cannot see changed; §0c preserves the binding",
    )
    if not findings and "RESOURCES" not in got.declarations_changed:
        findings.append(
            Finding(
                allow_site,
                "the verdict is DECLARATION_ONLY but `RESOURCES` is not "
                f"reported as the changed declaration: {got.declarations_changed}",
            )
        )

    trap_site = f"{SUBJECT_FILE}:_compare_bindings[aliasing trap]"
    trapped = _verdict(
        module,
        _ALIASED.format(resources='("venv",)'),
        _ALIASED.format(resources='("venv", "journal")'),
    )
    findings += _wrong(
        trap_site,
        module.MEASUREMENT_PATH,
        trapped,
        "run() READS its own RESOURCES, so the declaration IS the measurement",
    )
    return findings


# --------------------------------------------------------------------------
# ARM 4 — the edit that is not in this file at all (condition 4)
# --------------------------------------------------------------------------

_IMPORTER = '''"""Planted subject."""
from nixverify.helper import shared

RESOURCES = ()


def run(mode, ctx):
    return shared()
'''


def _arm_cross_file(module: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{SUBJECT_FILE}:_cross_file_reasons"
    rel = "scripts/nixverify/helper.py"
    with tempfile.TemporaryDirectory(prefix="nix-mpath-gate-") as tmp:
        repo = Path(tmp)
        helper = repo / rel
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("def shared():\n    return 1\n", encoding="utf-8")

        got = _verdict(
            module,
            _IMPORTER,
            _IMPORTER,  # THIS FILE IS BYTE-IDENTICAL. The edit is elsewhere.
            changed_files=(rel,),
            repo=repo,
        )
        findings += _wrong(
            site,
            module.MEASUREMENT_PATH,
            got,
            "a transitively-imported first-party module changed while the "
            "check's own bytes did not move at all",
        )
        if not findings and not any(rel in reason for reason in got.reasons):
            findings.append(
                Finding(site, f"no reason names {rel}: {list(got.reasons)}")
            )

        # The same pair with the helper NOT in the changed set must be
        # declaration-only — otherwise the arm above passes for everything.
        quiet = _verdict(
            module,
            _IMPORTER,
            _IMPORTER,
            changed_files=("scripts/nixverify/unrelated.py",),
            repo=repo,
        )
        findings += _wrong(
            f"{site}:negative",
            module.DECLARATION_ONLY,
            quiet,
            "an UNRELATED changed file must not make every edit measurement-path",
        )

    # changed_files without a repo root cannot run the cross-file arm, and a
    # classifier that certified anyway would be silently blind to condition 4.
    refused = _verdict(module, _IMPORTER, _IMPORTER, changed_files=(rel,))
    findings += _wrong(
        f"{site}:no-repo",
        module.MEASUREMENT_PATH,
        refused,
        "changed_files supplied with no repo root must REFUSE to certify",
    )
    return findings


# --------------------------------------------------------------------------
# ARM 5 — dynamic namespace access, and the AST/text discriminator (cond. 7)
# --------------------------------------------------------------------------

_DYNAMIC = '''"""Planted subject."""
RESOURCES = ()


def run(mode, ctx):
    return globals()["RESOURCES"]
'''

_STRING_ONLY = '''"""Planted subject."""
RESOURCES = ()
_PROBE = "importlib.import_module({0!r})"


def run(mode, ctx):
    return _PROBE
'''


def _arm_dynamic(module: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{SUBJECT_FILE}:_dynamic_uses"
    got = _verdict(module, _DYNAMIC, _DYNAMIC.replace('"RESOURCES"', '"PRIVILEGE"'))
    findings += _wrong(
        site,
        module.UNDECIDABLE,
        got,
        "globals() makes a static name graph unsound",
    )
    if got.preserves_binding:
        findings.append(
            Finding(
                site,
                "UNDECIDABLE preserved the binding — an unreadable subject "
                "must COST a binding, never silently keep one",
            )
        )

    text_site = f"{SUBJECT_FILE}:_dynamic_uses[string literal]"
    quiet = _verdict(
        module,
        _STRING_ONLY.format("a"),
        _STRING_ONLY.format("a"),  # identical
    )
    findings += _wrong(
        text_site,
        module.DECLARATION_ONLY,
        quiet,
        "a STRING mentioning importlib.import_module is not a call — "
        "check_order_path_bans ships exactly that string in a probe",
    )
    return findings


# --------------------------------------------------------------------------
# ARM 6 — fail closed on the unclassifiable, and the empty-range refusal
# --------------------------------------------------------------------------

_UNKNOWN = '''"""Planted subject."""
RESOURCES = ()
SOMETHING_ELSE = {value}


def run(mode, ctx):
    return 1
'''


def _arm_fail_closed(module: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    closed_site = f"{SUBJECT_FILE}:_compare_bindings[fail-closed]"
    got = _verdict(module, _UNKNOWN.format(value=1), _UNKNOWN.format(value=2))
    findings += _wrong(
        closed_site,
        module.MEASUREMENT_PATH,
        got,
        "a module-level binding that is neither a declaration symbol nor on "
        "the measurement path changed — there is no 'probably harmless'",
    )

    new_site = f"{SUBJECT_FILE}:classify_source[new/deleted]"
    findings += _wrong(
        new_site,
        module.MEASUREMENT_PATH,
        _verdict(module, None, _plant()),
        "a check that did not exist has no binding to preserve",
    )
    findings += _wrong(
        new_site,
        module.MEASUREMENT_PATH,
        _verdict(module, _plant(), None),
        "a deleted check keeps no binding",
    )
    findings += _wrong(
        f"{SUBJECT_FILE}:_parse_pair",
        module.UNDECIDABLE,
        _verdict(module, _plant(), "def run(  :::\n"),
        "a revision that does not parse is UNDECIDABLE, not declaration-only",
    )

    return findings


def _arm_empty_range(module: ModuleType, home: Path) -> tuple[list[Finding], str]:
    """The audit half's §0a guard. Returns (findings, cannot-measure reason).

    MEASURED THE HARD WAY, and this arm's first draft got it wrong: `home`
    is not necessarily a git repository, and `changed_paths` raises the SAME
    `RangeError` for "git could not answer" as for "the range is empty". A
    bare `except RangeError: pass` therefore passed vacuously against every
    non-git tree — the exact shape §0a asks about, found by this gate's own
    can-fail suite driving it against a `tmp_path` copy. The refusal is now
    required to NAME the empty range, and a git failure is CANNOT_MEASURE
    for the whole gate rather than a silent green (§17).
    """
    site = f"{SUBJECT_FILE}:changed_paths[empty range]"
    try:
        touched = module.changed_paths(home, "HEAD", "HEAD")
    except module.RangeError as exc:
        if "changed no files" in str(exc):
            return [], ""
        return [], (
            f"{site}: the empty-range guard could not be measured under "
            f"{home} — changed_paths refused for a different reason: {exc}. "
            "A guard proven while its subject is unreachable is not proven"
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                site,
                f"HEAD..HEAD raised {type(exc).__name__}: {exc} instead of "
                "RangeError — the empty-range guard did not fire",
            )
        ], ""
    return [
        Finding(
            site,
            f"HEAD..HEAD returned {list(touched)[:5]} instead of refusing "
            "— an empty range classifies EVERY check as declaration-only "
            "in silence, which is the §0a hazard this guard exists for",
        )
    ], ""


#: Arms that run unconditionally on every invocation. Stated so the evidence
#: line cannot claim coverage an exception skipped (§7.12/6).
ARMS = 7


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the §0c classifier over all seven arms. Verify-only, always."""
    try:
        module, error = load(ctx.nix_home)
        if module is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_main_block_root(module)
        findings += _arm_constant(module)
        findings += _arm_declaration_allowance(module)
        findings += _arm_cross_file(module)
        findings += _arm_dynamic(module)
        findings += _arm_fail_closed(module)
        range_findings, unmeasurable = _arm_empty_range(module, ctx.nix_home)
        findings += range_findings
        if unmeasurable and not findings:
            return CheckResult(
                name=NAME, status=Status.CANNOT_MEASURE, detail=unmeasurable
            )
        evidence = (
            f"{SUBJECT_FILE}: drove the §0c classifier over {ARMS} arms of "
            "planted before/after pairs whose correct verdict is known — the "
            "__main__-block closure root (with a run()-only falsifier proven "
            "to LOSE the finding), a measurement-path constant, the "
            "declaration allowance in both directions including the aliasing "
            "trap, a cross-file edit that never touched the check, dynamic "
            "namespace access vs a string literal that merely mentions it, "
            "fail-closed on unclassified state, and the empty-range refusal "
            "driven against this repository's own HEAD..HEAD"
        )
        if findings:
            detail = "; ".join(f"{site}: {why}" for site, why in findings)
            if unmeasurable:
                # Reported alongside, never instead of: a real finding
                # outranks an arm that could not run, but hiding the arm that
                # could not run is how a partial measurement reads as a whole
                # one.
                detail = f"{detail}. ALSO UNMEASURED: {unmeasurable}"
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail=detail,
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
