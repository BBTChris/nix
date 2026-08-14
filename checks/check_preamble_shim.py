#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK (`PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`/`CORRECTABLE`/`SUBJECTS`), its `run()` try/except CANNOT_MEASURE
# wrapper, and its `standalone_main` `__main__` footer against every other
# house-style check's — including its own new sibling, `check_nixverify_init`.
# That shape is REQUIRED, not accidental duplication (§4.2: every check is
# independently runnable and self-contained), the same reasoning
# `check_capture_plane2.py` and a dozen others already state at this exact
# site.
"""`checks/_preamble.py` actually performs the two-line contract every check
relies on: `sys.dont_write_bytecode = True` set BEFORE any `nixverify` import,
and `scripts/` appended (never inserted) to `sys.path` so `import nixverify`
resolves whether the check runs under the engine or standalone (§4.2).

WHY THIS IS A NEW GATE. `_preamble.py` is `checks/gate_coverage_baseline.json`'s
temporary CHECK-A8 exclusion (D3.104): it is imported by every `checks/check_*.py`
that exists, and NOTHING names it as a SUBJECT or asserts on its own two-line
behaviour directly — the many test modules that mention it exercise it only as
an incidental side effect of importing some check (confirmed: no `scripts/tests/
test_*.py` asserts on `sys.dont_write_bytecode` or the `sys.path` append in
isolation; the closest, `test_cli.py`, imports it to test something else). A file
executed on every run and asserted about nowhere is exactly the shape
`scripts/nixverify/__init__.py`'s sibling exclusion entry already names for a
different module.

WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING (§7.12)?

 1. The two structural facts are read off the WRONG file, or the file is
    missing. GUARDED: `ANCHOR` is a required member (`SUBJECTS`), and an absent
    anchor is CANNOT_MEASURE, never PASS (`nix_check_contract.md` §5.3).
 2. The scan matches on a substring rather than the actual AST shape, so a
    docstring mentioning "dont_write_bytecode" or "sys.path" would false-PASS a
    broken shim. GUARDED: both facts are found by walking the parsed AST for the
    exact assignment/call shapes, never by text search — the same discipline
    `check_synthetic_stop_only` uses for its own bans.
 3. `sys.path` is mutated with `insert(0, ...)` instead of `append(...)` and the
    scan does not distinguish them. GUARDED: the call's method name is checked,
    not merely that SOME `sys.path` mutation exists — `loader.py`'s own docstring
    explains why `append` (never `insert`) is load-bearing (a front-inserted
    check directory could shadow a stdlib module named `queue.py` or similar for
    every check loaded afterward).
 4. `sys.dont_write_bytecode` is set to a non-`True` value that is still
    "truthy" in a loose read of the source (e.g. `1`). GUARDED: the scan requires
    the literal `True` constant, matching what the module actually does today
    and what the test drives.

NON-CORRECTABLE for the same reason as `check_synthetic_stop_only`: the subject
is verify-machinery source every other check depends on to even load; a repair
that rewrote it to satisfy its own gate is the class of action the check
contract's rule 1 (measure vs. mutate) does not extend to its own bootstrap.

DRIVE. `scan_preamble_source` is a pure function over SOURCE TEXT — never a live
file mutation — exercised in `scripts/tests/test_check_preamble_shim.py` against
four synthetic variants (missing bytecode guard, missing path append, `insert`
instead of `append`, and the correct shape) to prove the scan is falsifiable in
both directions, plus a non-vacuity assertion that the REAL file on disk scans
clean. No subprocess, no copy, no risk to the live import surface every other
check depends on for the duration of this run — the isolation the arc brief asks
for is achieved by never touching a file at all, only parsing text.
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
#: Reads one source file. Opens no socket, spawns no process, writes nothing.
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = ()
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is verify-machinery source imported by every checks/check_*.py "
    "before anything else runs; a repair that rewrote it to satisfy its own gate "
    "would be editing the bootstrap the gate needs to even be loaded"
)
#: REQUIRED: an absent anchor is CANNOT_MEASURE, never PASS (§5.3).
ANCHOR = "checks/_preamble.py"
SUBJECTS: tuple[str, ...] = ("checks/_preamble.py",)

NAME = "check_preamble_shim"


def _is_true_const(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _scans_dont_write_bytecode(tree: ast.Module) -> bool:
    """`sys.dont_write_bytecode = True` as a module-level (or any) Assign."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not _is_true_const(node.value):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "dont_write_bytecode"
                and isinstance(target.value, ast.Name)
                and target.value.id == "sys"
            ):
                return True
    return False


def _scans_sys_path_append(tree: ast.Module) -> tuple[bool, bool]:
    """(append_found, insert_found_instead) for a `sys.path.<verb>(...)` call."""
    append_found = False
    insert_found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        target = func.value
        if not (
            isinstance(target, ast.Attribute)
            and target.attr == "path"
            and isinstance(target.value, ast.Name)
            and target.value.id == "sys"
        ):
            continue
        if func.attr == "append":
            append_found = True
        elif func.attr == "insert":
            insert_found = True
    return append_found, insert_found


def scan_preamble_source(source: str) -> list[str]:
    """All defects in the shim's source text. Pure — no filesystem, no import.

    Shared by `run()` and by the plant/restore drive test, exactly the
    `check_synthetic_stop_only` pattern: one code path, so the test and the
    gate can never silently diverge on what "a defect" means.
    """
    try:
        tree = ast.parse(source, filename=ANCHOR)
    except SyntaxError as exc:
        return [f"unparseable: {exc.msg} (line {exc.lineno})"]
    defects: list[str] = []
    if not _scans_dont_write_bytecode(tree):
        defects.append(
            "no `sys.dont_write_bytecode = True` assignment found — a check "
            "importing nixverify through this shim could write __pycache__ "
            "entries that checks/check_capture_plane2.py then attributes to "
            "whichever check happens to import first (the ARC 026 defect this "
            "line exists to close)"
        )
    append_found, insert_found = _scans_sys_path_append(tree)
    if not append_found:
        if insert_found:
            defects.append(
                "sys.path is mutated with insert(...) rather than append(...) — "
                "a front-inserted check directory can shadow a same-named stdlib "
                "module (e.g. queue.py) for every check loaded afterward "
                "(loader.py's own documented hazard)"
            )
        else:
            defects.append(
                "no sys.path.append(...) of the scripts/ directory found — "
                "`import nixverify` would fail for a check run standalone"
            )
    return defects


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Structurally verify the import shim every check depends on."""
    try:
        path = ctx.nix_home / ANCHOR
        if not path.is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"anchor {ANCHOR} absent — nothing to scan (§5.3)",
            )
        source = path.read_text(encoding="utf-8")
        defects = scan_preamble_source(source)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=f"{ANCHOR}: {len(defects)} defect(s) in the import shim",
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"{ANCHOR}: sys.dont_write_bytecode=True and sys.path.append(scripts) "
                "both present and correctly shaped"
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
