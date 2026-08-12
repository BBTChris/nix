"""Classify one check's edit as DECLARATION-ONLY or MEASUREMENT-PATH (§0c).

ARC 026 / A3. §0c says a retrofitted check keeps its can-fail binding when the
edit was declaration-only, and loses it when the measurement path moved. That
ruling is now load-bearing for **every binding claim in the system**, so the
thing that decides "declaration-only" has to be an instrument rather than a
judgement — and it has to be bound like any other instrument.

--------------------------------------------------------------------------
WHAT WAS ON DISK WHEN THIS WAS WRITTEN — NOTHING.
--------------------------------------------------------------------------
ARC 025's `SESSION.md` records *"an AST classifier over the arc's own diff
separates them: 5 checks had their MEASUREMENT PATH modified ... 10 had
declaration-only edits"*, and the ruling was taken on that basis. **The
classifier was never committed.** A whole-tree grep for `declaration-only`,
`measurement path` and any `classify` symbol outside
`check_observed_resource_claims` and `check_spec_citations` returns nothing.
So ten of ARC 025's fifteen bindings rest on a program that no longer exists,
which is CHECK-DEBT D2.30's defect one level up: not *the control is prose*,
but *the thing that decided which controls were still needed is prose*.

This module is that program, written for the first time, and
`scripts/tests/test_measurement_path.py` is its can-fail.

--------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this classifier
to report DECLARATION-ONLY while `run()` actually changed?
--------------------------------------------------------------------------
Every answer below is a committed, named plant in
`scripts/tests/test_measurement_path.py`. The list is the design.

 1. THE CLOSURE IS ROOTED AT `run` ALONE. `check_derived_claims` does most of
    its measuring inside `PROBES`, which `run()` never names — the probes are
    re-entered as `{self} --probe` from the `__main__` block. A closure rooted
    only at `run` would call an edit to any of the twenty-one probes
    declaration-only, and every number the gate compares would have moved.
    CLOSED: the roots are `run` **plus every module-level statement that is not
    a docstring, an import, or a simple named assignment** — which is exactly
    the `if __name__ == "__main__":` block, and it drags in `_probe_main`,
    `PROBES`, and through them every probe.

 2. A CONSTANT MOVES INSTEAD OF THE CODE. `_TIMEOUT = 300` -> `5`, or a regex
    like `_DISCHARGED` re-spelled. Not a function, so a function-only diff
    misses it.
    CLOSED: the closure contains module-level *bindings* of every kind, and a
    constant referenced from a closure member is a closure member.

 3. THE ALIASING TRAP. A declaration symbol is allowed to change — but only
    because `run()` cannot see it. A check whose `run()` reads its own
    `RESOURCES` (`ctx`-free self-inspection is a real shape; ARC 025's port
    gate reads a declared port) makes that declaration part of the measurement.
    CLOSED: the declaration allowance applies only to declaration symbols that
    are **not** in the closure. A declared name reachable from a root is
    compared like any other closure member.

 4. THE EDIT IS OUTSIDE THIS FILE. A check's `run()` calls
    `nixverify.contract.emit`, `nixverify.actuation.standalone_main`,
    `_preamble`. Nothing in this file changes and the measurement changes
    completely.
    CLOSED: `changed_files` is an INPUT. Any first-party module the check
    imports, transitively, that appears in that set makes the edit
    measurement-path. `resolve_imports` does the transitive walk over the repo.

 5. A DECORATOR, OR A DOCSTRING THAT IS DATA. `@functools.cache` on a probe
    changes what a second call measures; and this project has a working
    instance of a docstring being read as data —
    `check_derived_claims._flagged_addition` returns True when a function's own
    docstring says "nix addition", so a docstring edit in the subject moves a
    registered number.
    CLOSED: closure members are compared by full `ast.dump`, which includes
    decorators and docstrings. No prose is exempted inside the closure. The
    MODULE docstring is the single prose allowance, and it is withdrawn the
    moment the file mentions `__doc__` (condition 7).

 6. AN IMPORT CHANGES SHAPE. `import json` -> `import ujson as json`, or an
    import moved under an `if`.
    CLOSED: every module-level import statement is compared as a sequence, by
    `ast.dump`, before anything else is considered.

 7. THE NAMESPACE IS REACHED DYNAMICALLY. `globals()["PROBES"]`, `eval`,
    `exec`, `importlib.import_module`, `sys.modules[__name__]`, `__doc__`.
    Under any of these a static name graph is not a proof of anything.
    CLOSED: their presence makes the verdict UNDECIDABLE, which the caller
    reads as measurement-path. Detected on the AST — a string literal
    mentioning `importlib.import_module` is not a call, and
    `check_order_path_bans` embeds exactly that string in a probe it ships to a
    subprocess.

 8. SOMETHING CHANGED THAT IS NEITHER CLOSURE NOR DECLARATION. `PRIVILEGE`,
    `INTERACTIVE`, `DISRUPTIVE` are read by the loader, not by `run()`.
    CLOSED BY FAILING CLOSED: any module-level binding that changed and is
    neither in the closure nor a known declaration symbol is measurement-path.
    The classifier never has a category called "probably harmless".

 9. THE FILE IS NEW, DELETED, OR DOES NOT PARSE.
    CLOSED: each is measurement-path with its own reason. A check that did not
    exist before has no binding to preserve.

10. UNGUARDED, AND NAMED — SAME-NAME, DIFFERENT-BEHAVIOUR AT RUNTIME. The
    closure is a static name graph. A closure function calling a method on an
    object whose CLASS came from a changed third-party package is invisible
    here; so is behaviour that depends on the interpreter, the environment, or
    a data file the check reads at run time (`derived_claims.json`,
    `pinned_deps.json`, `registry.json`). This classifier answers *did this
    check's own code change*, which is strictly narrower than *did its
    measurement change*, and `SUBJECTS`-style data edits are outside it by
    construction. Stated here rather than implied, because a classifier that
    looked complete would be worse than one that names its edge.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import subprocess  # nosec B404 - fixed absolute argv, shell=False, history only
import sys
import tarfile
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from nixverify.declarations import _KNOWN as DECLARATION_SYMBOLS
from nixverify.gitenv import scrubbed_env

#: The three classifications. `UNDECIDABLE` is never a synonym for
#: `DECLARATION_ONLY`: `preserves_binding` is False for both it and
#: `MEASUREMENT_PATH`, so an unreadable file costs a binding rather than
#: silently keeping one.
DECLARATION_ONLY = "declaration-only"
MEASUREMENT_PATH = "measurement-path"
UNDECIDABLE = "undecidable"

#: Names whose appearance as a CALL, or as a read of the module's own
#: namespace, makes the static name graph unsound. See condition 7.
_DYNAMIC_CALLS = frozenset({"globals", "locals", "vars", "eval", "exec", "compile"})
_DYNAMIC_ATTRS = frozenset({"import_module", "__import__"})


@dataclasses.dataclass(frozen=True)
class Classification:
    """One edit's verdict, with every reason it was reached.

    `reasons` is the whole point. A verdict of MEASUREMENT_PATH with no reason
    would be an instrument saying "no" without naming a site, which §18 and
    doctrine C.2 both forbid of a control and which is worse in the thing the
    controls are indexed by.
    """

    name: str
    classification: str
    reasons: tuple[str, ...] = ()
    closure: frozenset[str] = frozenset()
    declarations_changed: tuple[str, ...] = ()

    @property
    def preserves_binding(self) -> bool:
        """§0c: only a proven declaration-only edit keeps a can-fail binding."""
        return self.classification == DECLARATION_ONLY


# ===========================================================================
# MODULE-LEVEL STRUCTURE
# ===========================================================================


def _is_docstring(index: int, node: ast.stmt) -> bool:
    return (
        index == 0
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _binding_name(node: ast.stmt) -> str | None:
    """The single module-level name a statement binds, or None."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id
    return None


@dataclasses.dataclass(frozen=True)
class _Module:
    """A check module reduced to the three things this question needs."""

    bindings: dict[str, ast.stmt]
    imports: tuple[str, ...]
    others: tuple[str, ...]
    other_nodes: tuple[ast.stmt, ...]
    dynamic: tuple[str, ...]


def _dynamic_uses(tree: ast.Module) -> tuple[str, ...]:
    """Every dynamic-namespace escape, by AST — never by text (condition 7)."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _DYNAMIC_CALLS:
                found.append(f"{func.id}() at line {node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr in _DYNAMIC_ATTRS:
                found.append(f"{ast.unparse(func)}() at line {node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr == "modules":
            found.append(f"{ast.unparse(node)} at line {node.lineno}")
        elif isinstance(node, ast.Name) and node.id == "__doc__":
            found.append(f"__doc__ at line {node.lineno}")
    return tuple(sorted(set(found)))


def _split(tree: ast.Module) -> _Module:
    bindings: dict[str, ast.stmt] = {}
    imports: list[str] = []
    others: list[str] = []
    other_nodes: list[ast.stmt] = []
    for index, node in enumerate(tree.body):
        if _is_docstring(index, node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.dump(node))
            continue
        name = _binding_name(node)
        if name is not None:
            bindings[name] = node
            continue
        others.append(ast.dump(node))
        other_nodes.append(node)
    return _Module(
        bindings=bindings,
        imports=tuple(imports),
        others=tuple(others),
        other_nodes=tuple(other_nodes),
        dynamic=_dynamic_uses(tree),
    )


def _referenced(node: ast.AST) -> set[str]:
    """Every bare name a subtree reads. Attribute bases count; attrs do not."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


def measurement_closure(module: _Module) -> frozenset[str]:
    """Module-level names reachable from `run` or from a non-binding statement.

    The second root is condition 1 and it is not a nicety: the
    `if __name__ == "__main__":` block is where a check's standalone CLI lives,
    and in `check_derived_claims` it is the ONLY path to `_probe_main`, hence
    the only path to the twenty-one probes that produce every number the gate
    compares. Rooting at `run` alone would have called an edit to any of them
    declaration-only.
    """
    frontier: set[str] = set()
    for dumped in module.other_nodes:
        frontier |= _referenced(dumped)
    if "run" in module.bindings:
        frontier.add("run")
    closure: set[str] = set()
    while frontier:
        name = frontier.pop()
        if name in closure or name not in module.bindings:
            continue
        closure.add(name)
        frontier |= _referenced(module.bindings[name])
    return frozenset(closure)


# ===========================================================================
# CROSS-FILE: the edit that is not in this file at all (condition 4)
# ===========================================================================


def _imported_modules(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
            out |= {f"{node.module}.{alias.name}" for alias in node.names}
    return out


#: Where a first-party module name may live, repo-relative. Ordered by how the
#: real tree resolves them: `nixverify.contract` is `scripts/nixverify/`, a bare
#: `_preamble` is a check's own sibling.
_ROOTS = ("scripts", "checks")


def resolve_imports(repo: Path, source: str) -> frozenset[str]:
    """Repo-relative `.py` paths this source imports, TRANSITIVELY.

    Transitive because the hazard is transitive: `check_x` imports
    `nixverify.actuation`, which imports `nixverify.contract`, and an edit to
    `contract.py` moves `check_x`'s measurement without either of the other two
    files changing. Anything that does not resolve to a file under `scripts/`
    or `checks/` is third-party or stdlib and is out of scope by definition —
    condition 10 names that edge rather than pretending to cover it.
    """
    resolved: set[str] = set()
    frontier = [source]
    while frontier:
        try:
            tree = ast.parse(frontier.pop())
        except SyntaxError:
            continue
        for dotted in _imported_modules(tree):
            for root in _ROOTS:
                rel = f"{root}/{dotted.replace('.', '/')}.py"
                if rel in resolved or not (repo / rel).is_file():
                    continue
                resolved.add(rel)
                frontier.append((repo / rel).read_text(encoding="utf-8"))
    return frozenset(resolved)


# ===========================================================================
# THE CLASSIFIER
# ===========================================================================


def _compare_bindings(
    before: _Module, after: _Module, closure: frozenset[str]
) -> tuple[list[str], list[str]]:
    """(reasons the measurement path moved, declaration symbols that changed)."""
    reasons: list[str] = []
    declarations: list[str] = []
    for name in sorted(set(before.bindings) | set(after.bindings)):
        old = before.bindings.get(name)
        new = after.bindings.get(name)
        same = old is not None and new is not None and ast.dump(old) == ast.dump(new)
        if same:
            continue
        where = "added" if old is None else "removed" if new is None else "changed"
        if name in closure:
            reasons.append(
                f"{name} is on the measurement path and was {where} "
                f"(reachable from run() or from the module's __main__ block)"
            )
        elif name in DECLARATION_SYMBOLS:
            declarations.append(name)
        else:
            reasons.append(
                f"{name} was {where}; it is neither a declaration symbol nor on "
                "the measurement path, so it cannot be shown harmless — "
                "unclassified module-level state fails closed (§7.12/8)"
            )
    return reasons, declarations


def _parse_pair(
    name: str, before: str, after: str
) -> tuple[_Module, _Module] | Classification:
    """Both revisions reduced to `_Module`, or the UNDECIDABLE that stops it."""
    reduced: list[_Module] = []
    for label, source in (("before", before), ("after", after)):
        try:
            reduced.append(_split(ast.parse(source, filename=f"{name}.py<{label}>")))
        except SyntaxError as exc:
            return Classification(
                name, UNDECIDABLE, (f"the {label} revision does not parse: {exc!r}",)
            )
    return reduced[0], reduced[1]


def _structure_reasons(old: _Module, new: _Module) -> list[str]:
    """Imports and unnamed module-level statements — the two nameless surfaces."""
    reasons: list[str] = []
    if old.imports != new.imports:
        reasons.append(
            "the module-level imports changed — every name the closure resolves "
            "comes through them, so an import edit is a measurement edit"
        )
    if old.others != new.others:
        reasons.append(
            "a module-level statement that binds no name changed (the "
            "__main__ block, a module-level call, or a conditional) — it "
            "executes on every standalone invocation"
        )
    return reasons


def _cross_file_reasons(
    repo: Path, changed_files: Iterable[str], before: str, after: str
) -> list[str]:
    """Condition 4: an edit that never touched this file but moved its measurement."""
    changed = set(changed_files)
    if not changed:
        return []
    imported = resolve_imports(repo, after) | resolve_imports(repo, before)
    return [
        f"{rel} is imported (transitively) by this check and changed "
        "in the same edit — the measurement path leaves this file"
        for rel in sorted(imported & changed)
    ]


def classify_source(
    name: str,
    before: str | None,
    after: str | None,
    *,
    changed_files: Iterable[str] = (),
    repo: Path | None = None,
) -> Classification:
    """Classify one check's edit from its two source texts.

    `before=None` means the file is new; `after=None` means it was deleted.
    `changed_files` are the repo-relative paths the same edit touched — pass
    them, or condition 4 is wide open.
    """
    if after is None:
        return Classification(name, MEASUREMENT_PATH, ("the check was deleted",))
    if before is None:
        return Classification(
            name,
            MEASUREMENT_PATH,
            ("the check is new — a check that did not exist has no binding",),
        )
    parsed = _parse_pair(name, before, after)
    if isinstance(parsed, Classification):
        return parsed
    old, new = parsed

    dynamic = sorted(set(old.dynamic) | set(new.dynamic))
    if dynamic:
        return Classification(
            name,
            UNDECIDABLE,
            tuple(
                f"dynamic namespace access makes a static name graph unsound: {use}"
                for use in dynamic
            ),
        )

    closure = measurement_closure(new) | measurement_closure(old)
    reasons = _structure_reasons(old, new)
    binding_reasons, declarations = _compare_bindings(old, new, closure)
    reasons.extend(binding_reasons)

    if repo is not None:
        reasons.extend(_cross_file_reasons(repo, changed_files, before, after))
    elif changed_files:
        reasons.append(
            "changed_files was supplied without a repo root, so the "
            "cross-file arm could not run — refusing to certify (§7.12/4)"
        )

    if reasons:
        return Classification(
            name,
            MEASUREMENT_PATH,
            tuple(reasons),
            closure,
            tuple(sorted(declarations)),
        )
    return Classification(
        name, DECLARATION_ONLY, (), closure, tuple(sorted(declarations))
    )


def classify_paths(
    name: str,
    before: Path | None,
    after: Path | None,
    *,
    changed_files: Iterable[str] = (),
    repo: Path | None = None,
) -> Classification:
    """`classify_source` over two files. A missing path reads as absent."""

    def _read(path: Path | None) -> str | None:
        if path is None or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    return classify_source(
        name,
        _read(before),
        _read(after),
        changed_files=changed_files,
        repo=repo,
    )


# ===========================================================================
# THE ARC AUDIT — every check, every arc range (ARC 027 / 0.1)
# ===========================================================================
#
# ARC 026 built the classifier and ran it, by hand, over ONE range. ARC 027's
# Phase 0.1 has to run it over five, and the §0a hazard named in that brief is
# precise: **an empty or wrong diff range produces a clean report while
# measuring nothing.** A range that resolves to zero changed files classifies
# every check as declaration-only, in silence, and the output is indistinguish-
# able from an arc that genuinely touched no measurement path.
#
# So the range is not a convenience argument, it is the thing most likely to be
# wrong, and `changed_paths` REFUSES an empty one — `RangeError`, exit 2, no
# table printed. There is no flag to override it.
#
# The second correctness point is subtler. `resolve_imports` decides whether a
# first-party import resolves by asking whether the file EXISTS, and the obvious
# spelling passes the live working tree as `repo`. That answers condition 4
# against *today's* module population rather than the revision's: a helper that
# existed at ARC 022 and was deleted since would silently stop being an import
# the classifier can follow, and the cross-file arm would go quiet exactly where
# history is oldest. Both revisions are therefore EXTRACTED with `git archive`
# and classified against their own trees.

GIT = "/usr/bin/git"

#: The two roots `resolve_imports` searches. Extracting only these keeps the
#: per-revision archive small; nothing outside them can be a first-party import.
_ARCHIVE_PATHS = ("scripts", "checks")


class RangeError(RuntimeError):
    """A diff range that cannot be trusted to have measured anything."""


def _git(cwd: Path, *args: str) -> str:
    """One git command, scrubbed environment (D3.22), stdout or raise."""
    proc = subprocess.run(  # nosec B603 - fixed absolute path, shell=False
        [GIT, "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=scrubbed_env(),
    )
    if proc.returncode != 0:
        raise RangeError(f"git {' '.join(args)} exit {proc.returncode}: {proc.stderr}")
    return proc.stdout


def changed_paths(repo: Path, before: str, after: str) -> tuple[str, ...]:
    """Repo-relative paths the range touched. **An empty range is an error.**"""
    out = tuple(
        line for line in _git(repo, "diff", "--name-only", before, after).splitlines()
    )
    if not out:
        raise RangeError(
            f"{before}..{after} changed no files — an empty range classifies every "
            "check as declaration-only while measuring nothing (§0a). Refusing."
        )
    return out


def check_names(repo: Path, rev: str) -> tuple[str, ...]:
    """`checks/check_*.py` present at one revision, repo-relative, sorted."""
    listed = _git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()
    return tuple(
        sorted(
            rel
            for rel in listed
            if rel.startswith("checks/check_") and rel.endswith(".py")
        )
    )


def extract_revision(repo: Path, rev: str, dest: Path) -> Path:
    """`scripts/` and `checks/` of one revision, on disk, for import resolution."""
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest.parent / f"{dest.name}.tar"
    archive.write_bytes(
        subprocess.run(  # nosec B603 - fixed absolute path, shell=False
            [GIT, "-C", str(repo), "archive", "--format=tar", rev, *_ARCHIVE_PATHS],
            capture_output=True,
            check=True,
            timeout=300,
            env=scrubbed_env(),
        ).stdout
    )
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")  # nosec B202 - data filter, own history
    archive.unlink()
    return dest


def audit_range(
    repo: Path, before: str, after: str, workdir: Path
) -> tuple[tuple[str, ...], list[Classification]]:
    """Classify every check across one arc's range. Returns (changed, verdicts)."""
    changed = changed_paths(repo, before, after)
    old_tree = extract_revision(repo, before, workdir / "before")
    new_tree = extract_revision(repo, after, workdir / "after")
    names = sorted(set(check_names(repo, before)) | set(check_names(repo, after)))
    return changed, [
        classify_paths(
            Path(rel).stem,
            old_tree / rel,
            new_tree / rel,
            changed_files=changed,
            repo=new_tree,
        )
        for rel in names
    ]


def _render(
    before: str, after: str, changed: Sequence[str], rows: list[Classification]
) -> None:
    """Print one range's verdicts.

    `untouched` is separated from `declaration-only` in the presentation and
    NOWHERE else: both preserve a binding, so the classifier is right to give
    them one verdict, but a reader auditing §0c needs to know whether the rule
    was *load-bearing* for a row or whether the file simply never moved.
    """
    print(f"\n=== {before}..{after} — {len(changed)} file(s) changed ===")
    touched = set(changed)
    preserved = [row.name for row in rows if row.preserves_binding]
    for row in rows:
        own = f"checks/{row.name}.py"
        mark = "" if own in touched else "  (file untouched)"
        head = f"  {row.name:<34} {row.classification}{mark}"
        if row.declarations_changed:
            head += f"  [declarations: {', '.join(row.declarations_changed)}]"
        print(head)
        for reason in row.reasons:
            print(f"      - {reason}")
    print(
        f"  -- {len(rows)} check(s); {len(preserved)} preserve a binding: "
        f"{preserved or 'none'}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m nixverify.measurement_path --before SHA --after SHA`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="nix-mpath-") as tmp:
            changed, rows = audit_range(repo, args.before, args.after, Path(tmp))
    except RangeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _render(args.before, args.after, changed, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
