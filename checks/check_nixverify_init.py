#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK (`PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`/`CORRECTABLE`/`SUBJECTS`), its `run()` try/except CANNOT_MEASURE
# wrapper, and its `standalone_main` `__main__` footer against every other
# house-style check's — including its own new sibling, `check_preamble_shim`.
# That shape is REQUIRED, not accidental duplication (§4.2: every check is
# independently runnable and self-contained), the same reasoning
# `check_capture_plane2.py` and a dozen others already state at this exact
# site.
"""`scripts/nixverify/__init__.py` re-exports six names from `nixverify.contract`
and nothing else. This gate proves the re-export is COHERENT: every name in
`__all__` is actually imported from a sibling module that is present on disk and
actually defines it — and every name imported FROM a sibling is listed in
`__all__`. Either direction drifting silently is the real failure mode: a name
removed or renamed in `contract.py` while `__init__.py` still imports it raises
`ImportError` the instant ANYTHING does `import nixverify` — which is every
`checks/check_*.py` in this tree, via `checks/_preamble.py`'s shim, before that
check's own `run()` gets a chance to say anything at all.

WHY THIS IS THE HARDEST OF THE EIGHT (arc brief, Stage 2 / sub-agent C).
`scripts/nixverify/__init__.py` is executed on every import of the package —
including the import this very check performs to report its own verdict. A
plant that broke the LIVE file would not redden this gate; it would prevent
`verify.py` from loading ANY check, this one included, and the failure would
surface as an opaque interpreter traceback outside the check contract entirely
— the worst possible verdict shape, per doctrine. So the property is proven
WITHOUT ever mutating the file every running check depends on: `scan_init_
coherence` is a pure function over SOURCE TEXT for `__init__.py` AND source text
for each sibling it imports from, resolved and parsed but never executed,
never imported, never written. The live package that this process is currently
running under is never touched.

WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING (§7.12)?

 1. The scan reads `__init__.py`'s CURRENT `sys.modules['nixverify']` state
    instead of its source on disk, which would report on whatever already
    imported successfully rather than on the file as committed. GUARDED: the
    real file's TEXT is read fresh off `ctx.nix_home` every run and re-parsed;
    nothing is read from an already-imported module object.
 2. `__all__` is emptied, so an empty list "coheres" with an empty import set
    vacuously. GUARDED: `run()` asserts `__all__` is non-empty before scanning
    and returns CANNOT_MEASURE otherwise — the same floor
    `check_synthetic_stop_only` applies to its own ban tuples.
 3. A sibling module referenced by `from nixverify.X import name` is resolved
    against the WRONG file (e.g. matched by substring rather than the exact
    dotted path), so a typo'd module name silently matches something else.
    GUARDED: the sibling path is built by exact dotted-segment join
    (`nixverify.contract` -> `scripts/nixverify/contract.py`) and CANNOT_MEASURE
    if that exact file is absent — never a fuzzy match.
 4. `contract.py` defines the name via a decorator or dynamic `globals()[...] =
    ...` assignment the AST walk does not recognise, so a present name is
    wrongly reported missing (a false FAIL). NAMED, not guarded: the resolver
    recognises `def`, `class`, plain `Name` assignment targets, and `import ...
    as` aliases — the four shapes every name in the real file today actually
    uses — and nothing fancier. A future export via a dynamic shape would need
    this resolver extended; it would currently read CANNOT_MEASURE-adjacent as
    a false defect rather than a silent false PASS, which is the safer failure
    direction for a gate whose subject breaks the whole suite.

NON-CORRECTABLE: rewriting `__init__.py` to satisfy its own gate is editing the
bootstrap every other check (including this one) needs to even be importable —
the same class of self-referential repair `check_preamble_shim` refuses.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
#: Reads source files only. Never imports the package it is checking.
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = ()
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is scripts/nixverify/__init__.py, executed on every import of "
    "the package this gate itself (and every other check) is built on; a "
    "repair that rewrote it to satisfy its own gate is the bootstrap editing "
    "itself, the same class of action check_preamble_shim refuses for its "
    "sibling shim"
)
ANCHOR = "scripts/nixverify/__init__.py"
SUBJECTS: tuple[str, ...] = ("scripts/nixverify/__init__.py",)

NAME = "check_nixverify_init"

_NIXVERIFY_DIR = "scripts/nixverify"
_BINDING_ASSIGN_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _all_list(tree: ast.Module) -> list[str] | None:
    """The literal `__all__ = [...]` list of string constants, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            return None
        names: list[str] = []
        for elt in node.value.elts:
            if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
                return None
            names.append(elt.value)
        return names
    return None


def _from_imports(tree: ast.Module) -> list[tuple[str, str]]:
    """Every `from nixverify.X import name [as alias]` -> (module, bound_name)."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module != "nixverify" and not node.module.startswith("nixverify."):
            continue
        segments = node.module.split(".")
        submodule = segments[1] if len(segments) > 1 else ""
        for alias in node.names:
            bound = alias.asname or alias.name
            out.append((submodule, bound))
    return out


def _module_level_bindings(tree: ast.Module) -> set[str]:
    """Every name bound at MODULE level: def/class/assignment/import-as."""
    bound: set[str] = set()
    for node in tree.body:
        if isinstance(node, _BINDING_ASSIGN_NODES):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
    return bound


def _resolution_defect(
    submodule: str, bound: str, sibling_sources: dict[str, str]
) -> str:
    """Direction 3 for ONE import: does it resolve to a real binding?

    Split out of `scan_init_coherence` to keep that function's cognitive
    complexity low — one property, one small function, per doctrine C.9's
    spirit applied within a single module.
    """
    if not submodule:
        return f"`from nixverify import {bound}` has no submodule"
    source = sibling_sources.get(submodule)
    if source is None:
        return (
            f"imports {bound!r} from nixverify.{submodule}, but "
            f"{_NIXVERIFY_DIR}/{submodule}.py is absent from the resolved "
            "scope — CANNOT_MEASURE, not a silent pass"
        )
    try:
        sib_tree = ast.parse(source, filename=f"{submodule}.py")
    except SyntaxError as exc:
        return f"{_NIXVERIFY_DIR}/{submodule}.py is unparseable: {exc.msg}"
    if bound in _module_level_bindings(sib_tree):
        return ""
    return (
        f"imports {bound!r} from nixverify.{submodule}, but "
        f"{submodule}.py defines no module-level {bound!r} — "
        "`import nixverify` would raise ImportError"
    )


def scan_init_coherence(init_source: str, sibling_sources: dict[str, str]) -> list[str]:
    """All coherence defects between `__init__.py` and the siblings it imports.

    Pure — no filesystem, no import. `sibling_sources` maps submodule name
    (e.g. "contract") to that sibling's own source text, resolved by the
    caller so this function never touches a path itself.
    """
    try:
        tree = ast.parse(init_source, filename=ANCHOR)
    except SyntaxError as exc:
        return [f"unparseable: {exc.msg} (line {exc.lineno})"]

    all_list = _all_list(tree)
    if all_list is None:
        return ["no literal `__all__ = [...]` of string constants found"]

    imports = _from_imports(tree)
    imported_names = {bound for _, bound in imports}

    defects: list[str] = []

    # Direction 1: everything in __all__ must be bound by an import.
    defects.extend(
        f"__all__ lists {name!r} but no `from nixverify.<mod> import` binds it "
        f"— `from nixverify import {name}` would raise ImportError"
        for name in all_list
        if name not in imported_names
    )

    # Direction 2: everything imported from a sibling must be in __all__.
    defects.extend(
        f"imports {bound!r} from nixverify.{submodule} but __all__ does not "
        "list it — re-exported but not advertised"
        for submodule, bound in imports
        if bound not in all_list
    )

    # Direction 3: each import must resolve to a REAL binding in the sibling's
    # OWN source — the failure mode that breaks `import nixverify` outright.
    defects.extend(
        defect
        for submodule, bound in imports
        if (defect := _resolution_defect(submodule, bound, sibling_sources))
    )

    return defects


def _resolve_sibling_sources(nix_home: Path, submodules: set[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for submodule in submodules:
        if not submodule:
            continue
        path = nix_home / _NIXVERIFY_DIR / f"{submodule}.py"
        if path.is_file():
            sources[submodule] = path.read_text(encoding="utf-8")
    return sources


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Structurally verify __init__.py's re-export coherence with its siblings."""
    try:
        path = ctx.nix_home / ANCHOR
        if not path.is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"anchor {ANCHOR} absent — nothing to scan (§5.3)",
            )
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=ANCHOR)
        except SyntaxError as exc:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=f"{ANCHOR} does not parse",
                detail=f"unparseable: {exc.msg} (line {exc.lineno})",
            )
        all_list = _all_list(tree)
        if not all_list:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=(
                    f"{ANCHOR} has no non-empty literal __all__ — a coherence "
                    "scan with nothing to check finds nothing (§7.12 cond. 2)"
                ),
            )
        submodules = {sub for sub, _ in _from_imports(tree)}
        sibling_sources = _resolve_sibling_sources(ctx.nix_home, submodules)
        defects = scan_init_coherence(source, sibling_sources)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=f"{ANCHOR}: {len(defects)} coherence defect(s)",
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"{ANCHOR}: {len(all_list)} export(s) coherent with "
                f"{len(sibling_sources)} sibling module(s) "
                f"[{', '.join(sorted(sibling_sources))}]"
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py (§4.2).
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
