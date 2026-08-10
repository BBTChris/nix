#!/usr/bin/env python3
"""No banned construct reaches the order path.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *the order
path contains no retry machinery and no loop-blocking call.* Both ban classes
live here rather than in two gates so they can never disagree about what "the
order path" IS — a second gate would carry a second file-set derivation, and
the two would drift the first time the tree moved.

WHAT IS BANNED, AND WHY (risk spec v1.3, and ARC 017 §2):

  retry libraries — `tenacity`, `backoff`, `retrying`
      §4: a pending order resolves through `query_order_status`; the system
      NEVER auto-resends. A retry decorator on `place_order` turns one intended
      order into two, at the venue, with real money.

  loop-blocking calls — `asyncio.run`, `run_until_complete`, `run_forever`
      §2A invariant 5: the send path is non-blocking regardless of vendor.
      `flatten()` is the protective path and MUST NOT BLOCK. Any of these on a
      sync verb parks the calling thread on the event loop.

The ban list is DATA (`BANNED_MODULES` / `BANNED_CALLS` below), not logic
threaded through the walker. Adding a ban is a one-line edit to a tuple; it
requires no change to how the scan works.

TWO ARMS, BOTH REQUIRED — neither is sufficient alone:

  (i) STATIC. `ast.parse` every `.py` under `scripts/broker/`, walking `Import`,
      `ImportFrom`, `Attribute`, `Name`, and every `decorator_list`. Catches
      DORMANT code: a banned import that no current call path reaches is still
      one refactor away from reaching one, and arm (ii) cannot see it because
      nothing executes it.

  (ii) DYNAMIC. Import every order-path module in a SUBPROCESS and read that
      process's `sys.modules`. Catches a TRANSITIVE pull-in: a dependency of a
      dependency that drags `tenacity` in. Arm (i) cannot see that at all — the
      import statement is in a third-party file the scan never opens.

SCOPE IS DERIVED, NEVER LISTED. The file set comes from
`Path(nix_home)/scripts/broker` `.rglob("*.py")` AT RUN TIME. A new adapter
file is covered the moment it is written; no registry, no allowlist, nothing a
person edits (`debug.md` §8 failure mode #14 is precisely the opposite
arrangement).

ONE DISCRIMINATION, MEASURED WHEN THE GATE WAS BUILT, NOT ASSUMED (ARC 017).
The first clean run reddened on `seam_simulate.py:525`,
`sys.exit(asyncio.run(main()))`, inside `if __name__ == "__main__":`. That is
the correct implementation of a CLI driver: `asyncio.run` is the sanctioned way
to start a loop from a script entry point, and a `__main__` body is provably
not reachable by import — arm (ii) imports all four modules and executes none
of it. Doctrine B.4 says a gate that reddens the correct implementation of its
own subject is BROKEN, and the repair belongs to the gate's LOGIC, never to its
SCOPE, so `seam_simulate.py` is NOT excluded and never will be. Instead the
property is stated exactly: *no banned construct on order-path code reachable
by importing it*. A banned CALL inside a module-level `__main__` guard is
therefore recorded as an ADVISORY — counted, named, and printed in `evidence`
on every run, so it can never become invisible — while a banned MODULE import
stays a violation everywhere including inside a `__main__` guard, because the
dependency is then on the order path's requirements regardless of what executes.
`nix_check_contract.md` §5.2 permits calibrating a NEW instrument as it comes
online; it requires the calibration be measured, which is what the site above
is a record of.

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
Six conditions, each stated so it could be planted:

 1. `scripts/broker/` is renamed or removed, so `rglob` returns an empty set and
    a scan of zero files reports "no violations".
    GUARDED: `_scope()` requires the set to be non-empty AND to contain every
    name in `REQUIRED_MEMBERS`; anything less is CANNOT_MEASURE, never PASS
    (`nix_check_contract.md` §5.3).

 2. The ban tuples are emptied — a data-driven gate whose data is gone scans
    every file and can find nothing.
    GUARDED: `run()` asserts both ban classes are non-empty before scanning and
    reports CANNOT_MEASURE otherwise. This is the vacuity mode unique to
    expressing rules as data, and it has no analogue in a hardcoded gate.

 3. Arm (ii)'s subprocess fails to import the seam at all (no `PYTHONPATH`, a
    syntax error, a missing venv) and its empty `sys.modules` answer is read as
    "clean".
    GUARDED: the probe reports which modules it actually imported; if that set
    is not the set requested, the arm is CANNOT_MEASURE, not PASS.

 4. UNGUARDED — the order path grows a SECOND home. If a future arc puts an
    adapter in `scripts/risk/` or `scripts/limiter/`, `broker_seam.py` and
    `broker_order_ibkr.py` are both still present, non-vacuity still passes, and
    the new file is simply outside the scan. `ORDER_PATH_DIRS` is the single
    place to fix that, and it is checked into this file rather than into a
    mutable external list so the fix is a reviewable diff.

 5. UNGUARDED — evasion by indirection. `importlib.import_module("tenacity")`,
    `__import__(name)`, or `getattr(loop, "run_until_complete")()` produce no
    `Import` node and no resolvable dotted name, so arm (i) is blind. Arm (ii)
    sees them only if they execute at IMPORT time; inside a function body that
    the probe never calls, both arms miss it.

 6. UNGUARDED, AND THE LARGEST GAP — a HAND-ROLLED retry loop
    (`for _ in range(3): self.place_order(...)`) is banned by ARC 017 §2.1 and
    is NOT detected here. This gate proves the absence of named constructs, not
    the absence of retry semantics. Do not read a PASS as "nothing on the order
    path retries"; read it as "no retry LIBRARY and no loop-blocking CALL is
    present". Detecting the semantic form needs a different instrument and is
    recorded as such rather than quietly implied.

Conditions 4-6 are named rather than fixed because a gate whose limits are
undocumented is one refactor away from meeting them silently.
"""

from __future__ import annotations

import ast
import json
import subprocess  # nosec B404 - fixed argv, shell=False, no user input
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

NAME = "check_order_path_bans"

# --------------------------------------------------------------------------
# THE BANS — data, not logic.
# --------------------------------------------------------------------------
# Root package names. A match on the root bans every submodule with it:
# `tenacity` bans `tenacity.retry`, and `import backoff.types` is caught by the
# same rule that catches `import backoff`.
BANNED_MODULES: tuple[str, ...] = ("tenacity", "backoff", "retrying")

# Call/attribute names. A pattern containing a dot must match the TAIL of the
# resolved dotted name, so `asyncio.run` fires on `asyncio.run(...)` and on
# `aio.run(...)` only if the object is literally spelled `asyncio`. A pattern
# without a dot matches the final segment alone, so `run_until_complete` fires
# on any receiver — `loop.`, `self._loop.`, or bare.
#
# `asyncio.run` is deliberately dotted: a bare `run` would fire on
# `subprocess.run`, which is legitimate everywhere, and a gate that reddens
# correct code is broken rather than strict (doctrine B.4).
BANNED_CALLS: tuple[str, ...] = ("asyncio.run", "run_until_complete", "run_forever")

# The order path, relative to nix_home. A tuple so a second home is one edit.
ORDER_PATH_DIRS: tuple[str, ...] = ("scripts/broker",)

# Non-vacuity floor: the scan is only believable if it reached these.
REQUIRED_MEMBERS: tuple[str, ...] = ("broker_seam.py", "broker_order_ibkr.py")

# Arm (ii)'s probe. Imports each named module and reports what the interpreter
# actually ended up holding. Printed as JSON so the gate parses a structure
# rather than scraping prose.
_IMPORT_PROBE = """
import importlib, json, sys
wanted = json.loads(sys.argv[1])
banned = set(json.loads(sys.argv[2]))
imported, failures = [], {}
for name in wanted:
    try:
        importlib.import_module(name)
        imported.append(name)
    except BaseException as exc:            # any failure, including SystemExit
        failures[name] = f"{type(exc).__name__}: {exc}"
present = sorted(m for m in sys.modules if m.split(".")[0] in banned)
print(json.dumps({
    "imported": imported,
    "failures": failures,
    "banned_present": present,
    "sys_modules_total": len(sys.modules),
}))
"""


def _dotted(node: ast.AST) -> str | None:
    """Resolve `a.b.c` to 'a.b.c'. Returns None for a computed receiver.

    A subscript or call in the chain (`handlers[0].run_forever`) is
    unresolvable by design — reported as None so the caller does not invent a
    name it did not read. §7.12 condition 5 records that this is a blind spot.
    """
    parts: list[str] = []
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if not isinstance(cursor, ast.Name):
        return None
    parts.append(cursor.id)
    return ".".join(reversed(parts))


def _call_violation(dotted: str) -> str | None:
    """Match a resolved dotted name against BANNED_CALLS. None if clean."""
    for pattern in BANNED_CALLS:
        if "." in pattern:
            if dotted == pattern or dotted.endswith("." + pattern):
                return pattern
        elif dotted.rsplit(".", 1)[-1] == pattern:
            return pattern
    return None


def _module_violation(dotted: str) -> str | None:
    """Match a module path (or a bare receiver) against BANNED_MODULES."""
    root = dotted.split(".", 1)[0]
    return root if root in BANNED_MODULES else None


def _main_guard_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Line ranges of module-level `if __name__ == "__main__":` bodies.

    Provably unreachable by import, which is what makes a loop-blocking call
    legal there and nowhere else. Computed from the AST, never from a filename.
    """
    ranges: list[tuple[int, int]] = []
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left = node.test.left
        rights = node.test.comparators
        is_name = isinstance(left, ast.Name) and left.id == "__name__"
        is_main = any(
            isinstance(c, ast.Constant) and c.value == "__main__" for c in rights
        )
        if is_name and is_main and node.body:
            first, last = node.body[0], node.body[-1]
            ranges.append((first.lineno, getattr(last, "end_lineno", last.lineno)))
    return ranges


# A hit is (line, name, why, is_callsite). Kept as a flat tuple so the three
# collectors below stay independent of how a hit is later classified.
Hit = tuple[int, str, str, bool]


def _import_hits(tree: ast.Module) -> list[Hit]:
    """`import tenacity` / `from backoff import x` anywhere in the file."""
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hit = _module_violation(alias.name)
                if hit:
                    hits.append(
                        (
                            node.lineno,
                            alias.name,
                            f"banned retry library {hit!r}",
                            False,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            hit = _module_violation(node.module or "")
            if hit:
                hits.append(
                    (
                        node.lineno,
                        node.module or "",
                        f"banned retry library {hit!r}",
                        False,
                    )
                )
    return hits


def _reference_hits(tree: ast.Module) -> list[Hit]:
    """Any resolvable name or dotted attribute matching a ban."""
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Attribute, ast.Name)):
            continue
        dotted = node.id if isinstance(node, ast.Name) else _dotted(node)
        if not dotted:
            continue
        call_hit = _call_violation(dotted)
        if call_hit:
            hits.append(
                (node.lineno, dotted, f"banned loop-blocking call {call_hit!r}", True)
            )
        mod_hit = _module_violation(dotted)
        if mod_hit and isinstance(node, ast.Attribute):
            hits.append(
                (node.lineno, dotted, f"banned retry library {mod_hit!r}", False)
            )
    return hits


def _decorator_name(deco: ast.expr) -> str | None:
    """The dotted name a decorator resolves to, with or without a call."""
    target = deco.func if isinstance(deco, ast.Call) else deco
    return target.id if isinstance(target, ast.Name) else _dotted(target)


def _node_decorator_hits(node: ast.AST) -> list[Hit]:
    """Bans among one definition's decorators. Never advisory: applied at import."""
    hits: list[Hit] = []
    for deco in getattr(node, "decorator_list", []):
        dotted = _decorator_name(deco)
        if not dotted:
            continue
        if _module_violation(dotted) or _call_violation(dotted):
            hits.append(
                (
                    getattr(deco, "lineno", getattr(node, "lineno", 0)),
                    f"@{dotted}",
                    f"banned decorator on {getattr(node, 'name', '?')!r}",
                    False,
                )
            )
    return hits


def _decorator_hits(tree: ast.Module) -> list[Hit]:
    """Decorators re-read so a decorated site is reported AS a decorator.

    `@backoff.on_exception` on `place_order` is a different fact from a stray
    reference to the module, and the operator reading the FAIL needs to know
    which one it is.
    """
    hits: list[Hit] = []
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if isinstance(node, defs):
            hits.extend(_node_decorator_hits(node))
    return hits


def scan_source(
    path: Path, source: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Arm (i). Returns (violations, advisories) for one file.

    `site` is `<file>:<line> <name>` — doctrine C.2 requires the gate name the
    specific site, not "a violation was found". An advisory is a banned CALL
    inside a module-level `__main__` guard: named and counted on every run, but
    not a violation, because nothing importing the order path can reach it.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(f"{path}:{exc.lineno or 0}", f"unparseable: {exc.msg}")], []

    guards = _main_guard_ranges(tree)
    found: list[tuple[str, str]] = []
    advisories: list[tuple[str, str]] = []
    for line, name, why, is_callsite in (
        _import_hits(tree) + _reference_hits(tree) + _decorator_hits(tree)
    ):
        site = f"{path.name}:{line} {name}"
        guarded = any(start <= line <= end for start, end in guards)
        if is_callsite and guarded:
            advisories.append((site, f"{why} — inside __main__ guard, not imported"))
        else:
            found.append((site, why))
    return found, advisories


def _scope(nix_home: Path) -> tuple[list[Path], str]:
    """Derive the file set at run time. Returns (files, complaint)."""
    files: list[Path] = []
    roots: list[Path] = []
    for rel in ORDER_PATH_DIRS:
        root = nix_home / rel
        roots.append(root)
        if root.is_dir():
            files.extend(sorted(p for p in root.rglob("*.py") if p.is_file()))
    if not files:
        return [], f"no .py files under {', '.join(str(r) for r in roots)}"
    names = {p.name for p in files}
    missing = [m for m in REQUIRED_MEMBERS if m not in names]
    if missing:
        return files, f"scope missing required member(s): {', '.join(missing)}"
    return files, ""


def _probe_interpreter(nix_home: Path) -> Path:
    """Prefer the venv: its sys.modules is the one the trading code will hold."""
    venv = nix_home / ".venv" / "bin" / "python3"
    return venv if venv.is_file() else Path(sys.executable)


def import_arm(nix_home: Path, files: list[Path]) -> tuple[list[tuple[str, str]], str]:
    """Arm (ii). Returns ([(site, why)], evidence-or-complaint).

    The second element is evidence on success and a CANNOT_MEASURE complaint
    prefixed 'cannot measure:' on failure — the two are never collapsed (§4.1).
    """
    modules = sorted({p.stem for p in files if not p.stem.startswith("_")})
    if not modules:
        return [], "cannot measure: no importable module names in scope"
    interpreter = _probe_interpreter(nix_home)
    env_paths = ":".join(str(nix_home / rel) for rel in ORDER_PATH_DIRS)
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [
                str(interpreter),
                "-c",
                _IMPORT_PROBE,
                json.dumps(modules),
                json.dumps(list(BANNED_MODULES)),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(nix_home),
            env={
                "PYTHONPATH": env_paths,
                "PATH": "/usr/bin:/bin",
                "HOME": str(nix_home),
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"cannot measure: probe did not run ({exc!r})"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        return [], f"cannot measure: probe output unparseable — {tail}"

    if payload["failures"] or sorted(payload["imported"]) != modules:
        detail = "; ".join(f"{k}: {v}" for k, v in payload["failures"].items())
        return [], (
            f"cannot measure: probe imported {payload['imported']} of {modules}"
            f" — {detail or 'no reason reported'}"
        )
    defects = [
        (
            f"{interpreter.name}:sys.modules[{mod!r}]",
            "banned module reachable by import",
        )
        for mod in payload["banned_present"]
    ]
    evidence = (
        f"imported {len(payload['imported'])} order-path module(s) under "
        f"{interpreter} -> {payload['sys_modules_total']} modules resident, "
        f"0 banned"
        if not defects
        else f"imported {payload['imported']} under {interpreter}"
    )
    return defects, evidence


def _static_arm(
    files: list[Path],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str]:
    """Arm (i) over the whole derived file set. Returns (defects, advisories, evidence)."""
    defects: list[tuple[str, str]] = []
    advisories: list[tuple[str, str]] = []
    for path in files:
        hits, notes = scan_source(path, path.read_text(encoding="utf-8"))
        defects.extend(hits)
        advisories.extend(notes)
    advisory_note = (
        "; ".join(f"ADVISORY {site} ({why})" for site, why in advisories)
        if advisories
        else "0 __main__-guarded advisories"
    )
    evidence = (
        f"arm(i) AST-scanned {len(files)} file(s) under "
        f"{', '.join(ORDER_PATH_DIRS)}: {', '.join(sorted(p.name for p in files))}; "
        f"{len(BANNED_MODULES)} banned module(s), {len(BANNED_CALLS)} banned call(s); "
        f"{advisory_note}"
    )
    return defects, advisories, evidence


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Both arms over a run-time-derived file set. Never repairs: source code
    on the order path is not something an unattended engine may edit."""
    try:
        if not BANNED_MODULES or not BANNED_CALLS:
            return _cannot_measure(
                "ban list empty — a data-driven gate with no data "
                "scans everything and finds nothing (§7.12 condition 2)"
            )
        files, complaint = _scope(ctx.nix_home)
        if complaint:
            return _cannot_measure(
                f"{complaint} (§5.3: an empty scope is never a PASS)"
            )

        defects, _advisories, static_evidence = _static_arm(files)
        dyn_defects, dyn_note = import_arm(ctx.nix_home, files)
        defects.extend(dyn_defects)

        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=f"{static_evidence}; arm(ii) {dyn_note}",
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        if dyn_note.startswith("cannot measure:"):
            result = _cannot_measure(
                f"arm(i) clean but arm(ii) {dyn_note} — one arm is not the gate"
            )
            result.evidence = static_evidence
            return result
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=f"{static_evidence}; arm(ii) {dyn_note}",
        )
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
    from nixverify.contract import exit_code_for, validate_result

    HOME = Path(__file__).resolve().parent.parent
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
