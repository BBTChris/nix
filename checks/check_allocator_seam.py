#!/usr/bin/env python3
"""The Allocator seam is a CONSUMER of the Limiter's contract, never a copy of it.

ONE gate, ONE property (`nix_check_contract.md` §5.5): *`scripts/nixalloc/seam.py`
declares a consumer-side shape the frozen risk spec already fixes, restates
nothing the Limiter already owns, and is read-only by construction.* Six arms
serve that single property; none of them is a second property.

  * **ARM 1 — the mirrored schema is the Limiter's OBJECT, not its shape.**
    §6.4 says both readers take "the same versioned row — identical bytes by
    construction". Identical-by-construction is an identity claim, so this arm
    asserts `nixalloc.seam.FinancialPicture is nixrisk.seam.FinancialPicture`
    and the same for `PositionRow`, `PositionState` and `ProposedOrder`. A
    locally-redefined dataclass with every field spelled identically passes a
    shape comparison and fails this one — which is the point, because it is a
    second declaration of one wire contract and free to drift tomorrow.

  * **ARM 2 — every declared property of the snapshot is present, derived.**
    `MIRRORED_FIELDS` is compared against `dataclasses.fields()` of the
    Limiter's own type, and `VERSION_FIELD` against that same set. Nothing is
    typed out here: a field renamed or dropped on either side is red, and the
    version stamp disappearing is its own named finding rather than one
    missing element in a set difference.

  * **ARM 3 — READ-ONLY BY CONSTRUCTION, in two independent spellings.** No
    `Protocol` in the module may declare a verb whose name is a mutation, and
    every dataclass in it must be `frozen=True`. Two spellings because they
    fail differently: a mutating verb is an authority the seam grants, and an
    unfrozen value type is an authority it fails to withhold — a consumer that
    edits a published field in place writes canonical state without any
    message leaving the process.

  * **ARM 4 — the correlation buckets are the SPEC's, parsed from the spec.**
    §7's locked sentence names four buckets and their members. This gate reads
    that sentence out of `docs/nics_risk_subsystem_spec_v1.3.md` at run time
    and compares it to `CorrelationBucket` and `BUCKET_OF`. No bucket name and
    no symbol appears as a literal in this file, so the suite can assert that
    too — an expected side the gate spells is a gate agreeing with itself.

  * **ARM 5 — every verb is SYNCHRONOUS, and no verb is a coroutine.** The
    module docstring gives a per-verb reason; this arm checks that the code
    matches the declaration. An `async def` anywhere in the seam is a declared
    suspension point in a single-pass, single-threaded design (§5, §16 U1).

  * **ARM 6 — the seam carries no behaviour.** Every callable is a `Protocol`
    method with no body, or a property returning one expression over its own
    fields. Anything that branches, loops, calls out or touches the world is
    behaviour, and behaviour in a seam is how a boundary becomes a second
    authority that can silently disagree with the spec. Same rule
    `check_limiter_seam` applies one package over, and it is stated per-arm
    rather than shared, because the two seams are separate subjects.

§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?

 1. The seam could be missing or unimportable. CLOSED: CANNOT_MEASURE naming
    the exception (§17), never a PASS.
 2. ARM 4's spec sentence could be renamed or moved, leaving the regex
    matching nothing and an empty expected set comparing equal to an empty
    measured one. CLOSED: a bucket sentence that yields fewer than
    `MIN_CREDIBLE_BUCKETS` entries is CANNOT_MEASURE naming the anchor, not a
    quiet agreement.
 3. ARM 1 could compare shapes and call it identity. CLOSED: it uses `is`, and
    the suite plants a byte-identical local redefinition and requires red.
 4. ARM 3's mutation-verb list could be empty or misspelled, matching nothing.
    CLOSED: the suite drives each forbidden verb name through the arm and
    requires a finding per name; and the frozen-dataclass half is measured on
    the real objects (`dataclasses.fields` + `__dataclass_params__`), not on
    source text.
 5. The AST arms could parse a DIFFERENT file — the seam under `ctx.nix_home`
    versus the one already imported into this process. CLOSED: the arms that
    need objects import by exact path out of `ctx.nix_home`, and the arms that
    need source read that same path; the loaded module's `__file__` is
    compared back against it.
 6. An arm could be skipped by an exception in an earlier arm and the gate
    still report a green over five. CLOSED: the arms run unconditionally, each
    returns its own findings, and the evidence line states the arm count.

WHAT THIS GATE CANNOT PROVE, stated rather than implied. It reads a
DECLARATION. It cannot prove the Allocator's implementation fast-drops before
sizing, refuses a partial mirror, or caps against a bucket sum — those are
behaviours of code built against this boundary and they need their own
instruments driving real objects. A green here means the boundary is faithful,
never that anything obeys it.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# §4.2 requires each checks/check_*.py be independently runnable and map
# status -> exit code identically, and doctrine B.2 requires the crash path
# return CANNOT_MEASURE in both. Those blocks are MANDATED to be the same text.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: Imports two first-party modules by path and reads two files. No socket, no
#: subprocess, no write.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is the frozen risk spec and the Limiter's own frozen "
    "seam, and the measured side is a declaration whose whole purpose is to be "
    "checkable against them. An instrument that could rewrite either side to "
    "agree would be manufacturing its own green"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/__init__.py",
)

NAME = "check_allocator_seam"

SEAM = "scripts/nixalloc/seam.py"
PACKAGE_INIT = "scripts/nixalloc/__init__.py"
LIMITER_SEAM = "scripts/nixrisk/seam.py"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"

#: §7's locked bucket sentence. Anchored on the bolded label so a renamed or
#: moved sentence is a loud CANNOT_MEASURE rather than an empty expected set
#: silently agreeing with an empty measured one (§7.12/2).
_BUCKET_SENTENCE = re.compile(r"\*\*Buckets:\*\*(?P<body>.*?)\(static", re.DOTALL)
#: One bucket inside that sentence: `equities {ES, NQ}`.
_BUCKET_ENTRY = re.compile(r"([A-Za-z]+)\s*\{([^}]*)\}")

#: Below this the parse is not credible. A floor, never today's count.
MIN_CREDIBLE_BUCKETS = 3

#: Verb-name stems whose presence on a consumer-side Protocol is a mutation the
#: seam would be granting. Matched as a whole word or a leading stem, so
#: `publish`, `publish_snapshot` and `set_balance` all hit while `available`
#: (which contains no stem) does not.
_MUTATING_STEMS = (
    "publish",
    "write",
    "set",
    "update",
    "apply",
    "put",
    "take",
    "release",
    "reserve",
    "commit",
    "delete",
    "clear",
    "insert",
    "append",
    "send",
    "place",
    "submit",
    "emit",
)

#: Names whose presence in a seam is behaviour by construction.
_FORBIDDEN_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "print", "input"}
)

#: The names ARM 1 requires to be the SAME OBJECT in both packages.
_SHARED_TYPES = ("FinancialPicture", "PositionRow", "PositionState", "ProposedOrder")


class Finding(NamedTuple):
    """One divergence. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


class Loaded(NamedTuple):
    """Both seams, imported by exact path out of the tree under test."""

    allocator: ModuleType
    limiter: ModuleType
    source: str
    tree: ast.Module


def _import_by_path(home: Path, rel: str, name: str) -> ModuleType:
    """Import one module by EXACT path. Never by `sys.path` name search.

    `checks/_preamble.py` appends the REAL repository's `scripts/` to
    `sys.path` permanently, so a name-based import resolves against the live
    tree whatever `home` says — the defect `check_d1_12_reboot_capture`'s
    first draft shipped. Registered in `sys.modules` before exec because both
    seams decorate frozen dataclasses, and `dataclasses` resolves each class's
    own module out of `sys.modules` while the decorator runs.
    """
    target = (home / rel).resolve()
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"no import spec for {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    loaded_from = Path(getattr(module, "__file__", "") or "").resolve()
    if loaded_from != target:
        raise ImportError(f"loaded {loaded_from}, not {target}")
    return module


def load(home: Path) -> tuple[Loaded | None, str]:
    """Both seams plus the Allocator seam's own source and AST, or the reason not."""
    for rel in (SEAM, PACKAGE_INIT, LIMITER_SEAM):
        if not (home / rel).is_file():
            return None, (
                f"{rel}: no such file under {home} — the subject is "
                "unavailable, so nothing was measured (§17: never a PASS)"
            )
    saved_path = list(sys.path)
    saved_modules = dict(sys.modules)
    try:
        # The Limiter seam FIRST and under its real dotted name: the Allocator
        # seam imports `nixrisk.seam`, and ARM 1's identity claim is only
        # meaningful if that import resolves to the copy under `home`.
        sys.path.insert(0, str((home / "scripts").resolve()))
        limiter = _import_by_path(home, LIMITER_SEAM, "nixrisk.seam")
        allocator = _import_by_path(home, SEAM, "nix_check_allocator_seam_subject")
        source = (home / SEAM).read_text(encoding="utf-8")
        return Loaded(allocator, limiter, source, ast.parse(source)), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{SEAM}: cannot load out of {home} — {type(exc).__name__}: {exc}. "
            "Nothing was measured (§17)"
        )
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if k not in saved_modules]:
            del sys.modules[key]
        sys.modules.update(saved_modules)


# --------------------------------------------------------------------------
# ARM 1 — the mirrored types are the Limiter's OBJECTS
# --------------------------------------------------------------------------


def _arm_shared_identity(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    for name in _SHARED_TYPES:
        site = f"{SEAM}:{name}"
        theirs = getattr(loaded.limiter, name, None)
        ours = getattr(loaded.allocator, name, None)
        if theirs is None:
            findings.append(
                Finding(
                    f"{LIMITER_SEAM}:{name}",
                    "the Limiter seam no longer declares it, so the Allocator "
                    "cannot be consuming it — §6.4's one snapshot has lost a type",
                )
            )
            continue
        if ours is None:
            findings.append(
                Finding(site, "the Allocator seam does not re-export it at all")
            )
            continue
        if ours is not theirs:
            findings.append(
                Finding(
                    site,
                    f"{name} is a DIFFERENT object from {LIMITER_SEAM}'s "
                    f"({ours!r} is not {theirs!r}) — §6.4 fixes one snapshot "
                    "under one writer and one version stamp, read by both "
                    "sides as identical bytes BY CONSTRUCTION. A second "
                    "declaration is identical only by inspection, which is "
                    "the thing that stops being true",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — every declared property of the snapshot, derived from the source
# --------------------------------------------------------------------------


def _arm_mirrored_fields(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{SEAM}:MIRRORED_FIELDS"
    picture = getattr(loaded.limiter, "FinancialPicture", None)
    if picture is None or not dataclasses.is_dataclass(picture):
        return [
            Finding(
                f"{LIMITER_SEAM}:FinancialPicture",
                "not a dataclass, so its declared properties cannot be read",
            )
        ]
    expected = tuple(field.name for field in dataclasses.fields(picture))
    declared = tuple(getattr(loaded.allocator, "MIRRORED_FIELDS", ()))
    if declared != expected:
        missing = sorted(set(expected) - set(declared))
        extra = sorted(set(declared) - set(expected))
        findings.append(
            Finding(
                site,
                f"the mirrored field set does not match the Limiter's own "
                f"FinancialPicture. missing={missing or 'none'} "
                f"extra={extra or 'none'} order_matches="
                f"{sorted(declared) == sorted(expected)}; declared={list(declared)}",
            )
        )
    stamp = getattr(loaded.allocator, "VERSION_FIELD", "")
    if stamp not in expected:
        findings.append(
            Finding(
                f"{SEAM}:VERSION_FIELD",
                f"the version stamp {stamp!r} is not a field of the published "
                "snapshot — §3's atomicity rule is checkable from outside ONLY "
                "through that stamp, so dropping or renaming it makes a torn "
                "read unobservable rather than impossible",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — read-only by construction, in two independent spellings
# --------------------------------------------------------------------------


def _mutating_stem(verb: str) -> str:
    """The mutation stem a verb name carries, or ''. Whole word or leading stem."""
    lowered = verb.lstrip("_").lower()
    for stem in _MUTATING_STEMS:
        if lowered == stem or lowered.startswith(f"{stem}_"):
            return stem
    return ""


def _protocol_classes(tree: ast.Module) -> list[ast.ClassDef]:
    """Every class whose bases name `Protocol`."""
    return [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any("Protocol" in ast.unparse(base) for base in node.bases)
    ]


def _no_mutating_verb(loaded: Loaded) -> list[Finding]:
    """SPELLING 1 — an authority the seam would be GRANTING."""
    return [
        Finding(
            f"{SEAM}:{klass.name}.{item.name}",
            f"a consumer-side port declares the mutating verb {item.name!r} "
            f"(stem {_mutating_stem(item.name)!r}) — §2 makes the Allocator "
            "permissive: it proposes and never writes canonical state, and a "
            "boundary that grants the verb has granted the authority",
        )
        for klass in _protocol_classes(loaded.tree)
        for item in klass.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _mutating_stem(item.name)
    ]


def _every_value_type_frozen(loaded: Loaded) -> list[Finding]:
    """SPELLING 2 — an authority the seam would be FAILING TO WITHHOLD.

    Measured on the real objects (`__dataclass_params__`) rather than on
    source text: a `@dataclass` spelled through an alias, or applied by a
    decorator factory, is invisible to a text scan and identical here.
    """
    return [
        Finding(
            f"{SEAM}:{name}",
            "a MUTABLE value type on the consumer side — a mirror holder "
            "could edit a published field in place, which is a write to "
            "canonical state that never leaves the process and appears in no "
            "event log (§2, §9)",
        )
        for name, obj in vars(loaded.allocator).items()
        if dataclasses.is_dataclass(obj)
        and isinstance(obj, type)
        and not _is_frozen(obj)
    ]


def _is_frozen(obj: type) -> bool:
    """`@dataclass(frozen=True)`? Read off the real class, defaulting FROZEN.

    Defaulting to True on a class with no `__dataclass_params__` is deliberate
    and is the strict direction here: the caller has already established the
    object IS a dataclass, so an absent params attribute means a future
    dataclasses implementation moved it, not that the class is mutable — and
    inventing a finding out of an unreadable attribute is a false positive
    this gate would carry forever.
    """
    params = getattr(obj, "__dataclass_params__", None)
    return bool(getattr(params, "frozen", True))


def _arm_read_only(loaded: Loaded) -> list[Finding]:
    return _no_mutating_verb(loaded) + _every_value_type_frozen(loaded)


# --------------------------------------------------------------------------
# ARM 4 — the buckets are the spec's, parsed from the spec
# --------------------------------------------------------------------------


def spec_buckets(home: Path) -> tuple[dict[str, str], str]:
    """`({symbol: bucket_name}, complaint)` parsed from §7's locked sentence."""
    path = home / SPEC
    if not path.is_file():
        return {}, f"{SPEC}: not present under {home}"
    match = _BUCKET_SENTENCE.search(path.read_text(encoding="utf-8"))
    if match is None:
        return {}, (
            f"{SPEC}: the §7 '**Buckets:**' sentence did not match its anchor "
            "— an unmatched anchor yields an EMPTY expected set, which would "
            "compare equal to an empty measured one and report agreement"
        )
    found: dict[str, str] = {}
    for bucket, members in _BUCKET_ENTRY.findall(match.group("body")):
        for symbol in (part.strip() for part in members.split(",")):
            if symbol:
                found[symbol] = bucket.lower()
    if len(set(found.values())) < MIN_CREDIBLE_BUCKETS:
        return {}, (
            f"{SPEC}: parsed {len(set(found.values()))} bucket(s) from the §7 "
            f"sentence, below the credibility floor of {MIN_CREDIBLE_BUCKETS}"
        )
    return found, ""


def _arm_buckets(loaded: Loaded, home: Path) -> tuple[list[Finding], str]:
    expected, complaint = spec_buckets(home)
    if complaint:
        return [], complaint
    findings: list[Finding] = []
    bucket_of = getattr(loaded.allocator, "BUCKET_OF", {})
    declared = {
        symbol: getattr(bucket, "value", str(bucket))
        for symbol, bucket in bucket_of.items()
    }
    if declared != expected:
        findings.append(
            Finding(
                f"{SEAM}:BUCKET_OF",
                f"the symbol->bucket map disagrees with §7's locked sentence. "
                f"spec={dict(sorted(expected.items()))} "
                f"seam={dict(sorted(declared.items()))}",
            )
        )
    enum_cls = getattr(loaded.allocator, "CorrelationBucket", None)
    members = {member.value for member in enum_cls} if enum_cls is not None else set()
    if members != set(expected.values()):
        findings.append(
            Finding(
                f"{SEAM}:CorrelationBucket",
                f"the bucket enum disagrees with §7. spec="
                f"{sorted(set(expected.values()))} seam={sorted(members)}",
            )
        )
    return findings, ""


# --------------------------------------------------------------------------
# ARM 5 — no coroutine anywhere in the seam
# --------------------------------------------------------------------------


def _arm_synchronous(loaded: Loaded) -> list[Finding]:
    return [
        Finding(
            f"{SEAM}:{node.name}",
            "declared `async def`, contradicting this seam's own per-verb "
            "synchronous declaration — a coroutine is a declared suspension "
            "point, and §5's single-threaded loop plus §16 U1's single pass "
            "are what make the per-GO cost bounded and the snapshot read "
            "skew-free",
        )
        for node in ast.walk(loaded.tree)
        if isinstance(node, ast.AsyncFunctionDef)
    ]


# --------------------------------------------------------------------------
# ARM 6 — the seam carries no behaviour
# --------------------------------------------------------------------------


def _is_declaration_body(node: ast.FunctionDef) -> bool:
    """A docstring, an ellipsis, a `pass`, or a single `return <expr>`."""
    body = [
        stmt
        for stmt in node.body
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
    ]
    if not body:
        return True
    if len(body) > 1:
        return False
    only = body[0]
    if isinstance(only, ast.Pass):
        return True
    if isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant):
        return only.value.value is Ellipsis
    return isinstance(only, ast.Return)


def _arm_no_behaviour(loaded: Loaded) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(loaded.tree):
        if isinstance(node, ast.Call):
            func = node.func
            named = func.id if isinstance(func, ast.Name) else ""
            if named in _FORBIDDEN_CALLS:
                findings.append(
                    Finding(
                        f"{SEAM}:line {node.lineno}",
                        f"calls {named}() — a seam that touches the world is "
                        "behaviour, and behaviour in a boundary is a second "
                        "authority that can silently disagree with the spec",
                    )
                )
        if isinstance(node, ast.FunctionDef) and not _is_declaration_body(node):
            findings.append(
                Finding(
                    f"{SEAM}:{node.name}",
                    "has a body that is neither a docstring, an ellipsis, a "
                    "pass, nor a single return expression — that is a rule, "
                    "and rules belong in the implementation this seam bounds",
                )
            )
    return findings


ARMS = 6


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive all six arms against the seam under `ctx.nix_home`."""
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_shared_identity(loaded)
        findings += _arm_mirrored_fields(loaded)
        findings += _arm_read_only(loaded)
        bucket_findings, unmeasurable = _arm_buckets(loaded, ctx.nix_home)
        findings += bucket_findings
        findings += _arm_synchronous(loaded)
        findings += _arm_no_behaviour(loaded)
        if unmeasurable and not findings:
            return CheckResult(
                name=NAME, status=Status.CANNOT_MEASURE, detail=unmeasurable
            )
        evidence = (
            f"{SEAM} (seam_rev "
            f"{getattr(loaded.allocator, 'SEAM_REV', '?')}): {ARMS} arms — the "
            f"{len(_SHARED_TYPES)} shared types asserted IDENTICAL OBJECTS to "
            f"{LIMITER_SEAM}'s (not merely same-shaped); "
            f"{len(getattr(loaded.allocator, 'MIRRORED_FIELDS', ()))} mirrored "
            "field(s) and the version stamp derived from the Limiter's own "
            "dataclass; read-only proven in two spellings (no mutating verb on "
            "any Protocol, every value type frozen); the correlation buckets "
            "parsed out of §7's locked sentence in the frozen spec with no "
            "bucket or symbol spelled in this gate; zero coroutines; zero "
            "behaviour"
        )
        if findings:
            detail = "; ".join(f"{site}: {why}" for site, why in findings)
            if unmeasurable:
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
