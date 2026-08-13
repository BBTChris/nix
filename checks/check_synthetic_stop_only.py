#!/usr/bin/env python3
"""§12.1 — the synthetic-stop path places NO broker-native stop order.

ONE gate, ONE property: *the synthetic-stop machinery is our software, not a
broker-side stop* (`nics_risk_subsystem_spec_v1.3.md` §12.1:606 — "This is our
software, not a broker-side stop — that prohibition stands"). A synthetic stop
lives in the Limiter's memory and is fired by the protective-flatten path; it may
NEVER be delegated to a venue as a resting stop order, because a broker-native
stop is a second authority the Limiter cannot see, cannot audit on Plane 1, and
cannot flatten on `restart = flat`.

WHY A NEW GATE RATHER THAN AN EXTENSION OF `check_order_path_bans`. That gate owns
a DIFFERENT property — *no retry machinery and no loop-blocking call on the ORDER
PATH* (doctrine C.9: one instrument per property) — and its scope is derived from
modules that DECLARE the order port. `scripts/nixrisk/stops.py` declares no order
port: it is the opposite, a module that must be proven NOT to reach one. Folding
this property into that gate would mean editing its registered `SUBJECTS` and its
scope derivation, which ARC 029's sub-agent-A charter forbids. So this is a
focused, presently-UNREGISTERED sibling; registering it in `checks/registry.json`
is an integrator task (Stage 2), noted in the arc's RESULTS.

WHAT IS BANNED ON THE SYNTHETIC-STOP PATH, AND WHY (all data, not logic):

  (i)  BROKER IMPORTS. The stop book is pure arithmetic over `StopState`; it has
       no business importing the §2A broker order seam or any adapter. An import
       is DORMANT reach — one call site away from placing an order — so it is
       banned even if nothing currently calls through it.

  (ii) ORDER-PLACEMENT VERBS. A call whose tail name is a send-path order verb
       (`place_order`, `submit_order`, `cancel_order`) IS the act of delegating
       to the venue. The synthetic stop must reach none of them: it returns the
       breached stops and the protective-flatten machinery — a different module —
       does the firing.

  (iii) BROKER-NATIVE STOP ORDER-TYPE CODES. The exact venue order-type strings
       for a resting stop (`STP`, `STP LMT`, `TRAIL`, `TRAIL LIMIT`) appearing as
       a string LITERAL is the fingerprint of constructing a broker-side stop.
       Matched as an EXACT literal value, never as a substring: the English word
       "stop" is this module's whole subject and reddening it would be reddening
       the correct implementation of the gate's own subject (doctrine B.4).

SCOPE. Anchored on `scripts/nixrisk/stops.py` and WIDENED by derivation: any
`scripts/nixrisk/*.py` defining a class that implements at least `PORT_QUORUM` of
the `StopBookPort` verbs joins the scan, so a renamed or split stop book cannot
slip out of scope silently (`debug.md` §8 failure mode #14). The anchor is a
FLOOR: if it is absent the scan measured nothing and the verdict is
CANNOT_MEASURE, never PASS (`nix_check_contract.md` §5.3).

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The ban tuples are emptied — a data-driven gate with no data finds nothing.
    GUARDED: `run` asserts all three ban classes are non-empty before scanning
    and returns CANNOT_MEASURE otherwise.
 2. `stops.py` is renamed or removed, so the scan walks zero files and reports
    "no violations". GUARDED: `ANCHOR` is a required member; a scope missing it
    is CANNOT_MEASURE (§5.3).
 3. The stop path grows a second home and the new file is simply outside the
    scan. GUARDED for a module that IMPLEMENTS the port: derivation adds it. NOT
    guarded for a module that CALLS a stop book it does not implement — the same
    residual `check_order_path_bans` names for the future Limiter; recorded here,
    not silently absent.
 4. Evasion by computed import/getattr (`importlib.import_module(name)`,
    `getattr(broker, verb)()`). UNGUARDED, and closing it means either flagging
    every `getattr` or executing the module — the same trade `check_order_path_
    bans` NAMED GAP 4 declined at acceptable cost. Named, not fixed.
 5. A broker-native stop constructed via an order-type code this gate does not
    list. UNGUARDED to the extent the venue vocabulary is larger than the four
    codes here; the import and verb arms catch the DELEGATION regardless of the
    code, so a stop order still cannot reach the venue without tripping (i)/(ii).
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
#: Reads source files only; opens no socket, spawns no process, writes nothing.
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = ()
#: NON-CORRECTABLE, same charter as `check_order_path_bans`: the subject is
#: risk-path source. A gate that rewrote `stops.py` to satisfy itself is the same
#: class of action risk spec §4 forbids on the order path — remediation there
#: converts one intended action into two, or edits away the very thing under test.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/stops.py); a repair that "
    "edited it to satisfy its own gate is the same class of action risk spec §4 "
    "forbids on the order path"
)
#: DRIVEN, not merely named: `stops.py` is opened, `ast.parse`d, and walked on
#: every run, and it is a REQUIRED member so its departure from scope is
#: CANNOT_MEASURE rather than a silent shrink. The drive is PROVEN in
#: `scripts/tests/test_stops.py`, which plants a broker import and an order verb
#: into a copy and shows this gate reddens naming the site, then restores.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/stops.py",)

NAME = "check_synthetic_stop_only"

# --------------------------------------------------------------------------
# THE BANS — data, not logic.
# --------------------------------------------------------------------------
#: Root module names whose import puts the broker within reach of the stop path.
#: A match on the root bans every submodule with it.
BANNED_IMPORT_ROOTS: tuple[str, ...] = (
    "broker_seam",
    "broker_order_ibkr",
    "broker_order_config",
    "broker_datafeed_ibkr",
    "ibkr_mapping",
    "seam_simulate",
)
#: A dotted import path segment that betrays the broker package regardless of
#: how the module is spelled (`scripts.broker.x`, `broker.x`).
BANNED_IMPORT_MARKER = "broker"

#: Send-path order verbs. A call whose tail name is one of these IS delegation.
BANNED_ORDER_VERBS: frozenset[str] = frozenset(
    {"place_order", "submit_order", "cancel_order"}
)

#: Exact venue order-type codes for a resting broker-side stop. Matched as an
#: EXACT string-literal value, never a substring — the word "stop" is legitimate.
BANNED_ORDER_TYPE_CODES: frozenset[str] = frozenset(
    {"STP", "STP LMT", "TRAIL", "TRAIL LIMIT"}
)

#: The floor. The scan is only believable if it reached this file.
ANCHOR = "scripts/nixrisk/stops.py"
NIXRISK_DIR = "scripts/nixrisk"

#: The frozen `StopBookPort` verbs, used to derive a second home. A class
#: defining at least this many of them is a stop book.
STOP_PORT_VERBS: frozenset[str] = frozenset({"arm", "maintain", "breached", "forget"})
PORT_QUORUM = 3

_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _dotted_tail(node: ast.expr) -> str | None:
    """The tail name of `a.b.c` (-> 'c') or a bare `name` (-> 'name'), else None."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _import_hits(tree: ast.Module) -> list[tuple[int, str]]:
    """Broker imports anywhere in the module. (line, why)."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".", 1)[0]
            segments = name.split(".")
            if root in BANNED_IMPORT_ROOTS or BANNED_IMPORT_MARKER in segments:
                hits.append(
                    (node.lineno, f"imports broker module {name!r} onto the stop path")
                )
    return hits


def _call_hits(tree: ast.Module) -> list[tuple[int, str]]:
    """Order-placement verb calls anywhere in the module. (line, why)."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        tail = _dotted_tail(node.func)
        if tail in BANNED_ORDER_VERBS:
            hits.append(
                (
                    node.lineno,
                    f"calls order-placement verb {tail!r} — delegates to the venue",
                )
            )
    return hits


def _order_type_hits(tree: ast.Module) -> list[tuple[int, str]]:
    """Broker-native stop order-type codes as string literals. (line, why)."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in BANNED_ORDER_TYPE_CODES:
            hits.append(
                (
                    node.lineno,
                    (
                        f"string literal {node.value!r} is a broker-native stop "
                        "order-type code — the fingerprint of a broker-side stop"
                    ),
                )
            )
    return hits


def scan_stop_source(relpath: str, source: str) -> list[tuple[str, str]]:
    """All three ban arms over one module's source. Returns (site, why) pairs.

    Pure and side-effect-free so `test_stops.py` can drive it over planted
    source directly, and so `run` and the drive test share ONE code path.
    """
    try:
        tree = ast.parse(source, filename=relpath)
    except SyntaxError as exc:
        return [(f"{relpath}:{exc.lineno or 0}", f"unparseable: {exc.msg}")]
    hits = _import_hits(tree) + _call_hits(tree) + _order_type_hits(tree)
    return [(f"{relpath}:{line}", why) for line, why in sorted(hits)]


def _implements_stop_port(tree: ast.Module) -> bool:
    """True when some class defines >= PORT_QUORUM StopBookPort verbs."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {m.name for m in node.body if isinstance(m, _FUNC_NODES)}
        if len(methods & STOP_PORT_VERBS) >= PORT_QUORUM:
            return True
    return False


def _scope(nix_home: Path) -> tuple[list[Path], str]:
    """Anchor + derived stop modules under scripts/nixrisk, or a complaint.

    §5.3: an empty scope, or one missing the anchor, is CANNOT_MEASURE.
    """
    base = nix_home / NIXRISK_DIR
    files: set[Path] = set()
    anchor = nix_home / ANCHOR
    if anchor.is_file():
        files.add(anchor)
    if base.is_dir():
        for path in sorted(base.glob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError, UnicodeDecodeError:
                continue
            if _implements_stop_port(tree):
                files.add(path)
    if not anchor.is_file():
        return [], f"anchor {ANCHOR} absent — the scan reached nothing to measure"
    return sorted(files), ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Scan the synthetic-stop path for any delegation to a broker-side stop."""
    try:
        if (
            not BANNED_IMPORT_ROOTS
            or not BANNED_ORDER_VERBS
            or not BANNED_ORDER_TYPE_CODES
        ):
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail="a ban class is empty — a data-driven gate with no data "
                "scans everything and finds nothing (§7.12 condition 1)",
            )
        files, complaint = _scope(ctx.nix_home)
        if complaint:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{complaint} (§5.3: an empty scope is never a PASS)",
            )
        defects: list[tuple[str, str]] = []
        for path in files:
            rel = path.relative_to(ctx.nix_home)
            defects.extend(scan_stop_source(str(rel), path.read_text(encoding="utf-8")))
        scanned = ", ".join(sorted(p.name for p in files))
        evidence = (
            f"§12.1 synthetic-stop-only: AST-scanned {len(files)} file(s) "
            f"[{scanned}] for {len(BANNED_IMPORT_ROOTS)} broker import root(s), "
            f"{len(BANNED_ORDER_VERBS)} order verb(s), "
            f"{len(BANNED_ORDER_TYPE_CODES)} native stop order-type code(s); "
            "0 delegations"
        )
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence.replace(
                    "0 delegations", f"{len(defects)} delegation(s)"
                ),
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
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
