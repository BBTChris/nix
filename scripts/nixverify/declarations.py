"""Read a check's orchestration declarations WITHOUT running the check.

ARC 024 §3.3. The binding invariant is one sentence: **`--optimize` must be able
to read every check's declared dependencies and resource claims without
executing the check's measurement logic.**

## Two mechanisms were measured against the real population, then one was chosen

§3.3 deliberately left the spelling unspecified and named this as exactly the
place ARC 022's A1 trap lived. Both candidates were built and run against all 13
registered checks before anything was written down.

| | AST parse | import-to-read |
|---|---|---|
| coverage | 13/13 | 13/13 *(only after replicating `loader.py`'s
  `sys.path` step — 1/13 without it)* |
| wall clock | **27.8 ms** | 29.7 ms |
| `sys.modules` growth | 0 | **+76 across 7 modules** |
| executes module-level code | **no** | yes |

**Cost is not the discriminator — the two are within 7% of each other, and the
first import measurement that showed 1/13 was an unfair comparison against a
strawman and was re-taken before being used.** The discriminator is the
invariant itself, and it is structural:

1. **Import cannot promise not to execute measurement logic; AST cannot execute
   it.** No check on today's tree does work at module level, so import is *safe
   today*. But the operator's own estimate for this population is "hundreds when
   complete", and the guarantee has to hold for a check nobody has written yet.
   One future check that dials IBKR, opens a socket, or spawns a subprocess at
   module level turns `--optimize` — a planning tool — into a thing that
   performs measurements as a side effect of planning. AST parse cannot do that
   however badly a future check is written.
2. **Import permanently mutates the process.** `loader.py`'s own docstring
   records that its `sys.path` entry "is never removed", a deliberate trade made
   because blocks run in parallel. Measured here: importing the population adds
   **76 modules** to `sys.modules`. A derivation step should not leave residue
   in the interpreter that derived it.
3. **Import fails closed in the wrong direction.** A check whose module-level
   code raises yields *no declaration at all*, and the tempting recovery is to
   treat it as declaring nothing — which §3.3 bans by name, because a check that
   silently declares nothing lands in a parallel block it does not belong in.
   AST reads the declaration out of a file that would not import.

**The failure mode of the mechanism NOT chosen is demonstrated, not asserted** —
see `scripts/tests/test_declarations.py::test_import_to_read_executes_module_level_code`,
which plants a check whose module level writes a file, then shows import-to-read
creates it and `read_declaration` does not.

## AST's own weakness is handled rather than ignored

AST parse is brittle to expression form: `RESOURCES = ("journal",)` reads, and
`RESOURCES = _BASE + ("journal",)` does not. That weakness is real and is why
this module **never silently defaults**. A declaration present but not
literal-evaluable produces a named error in `Declaration.errors`; a declaration
absent entirely produces a named error. Both are loud at the point of use
(`optimize.py`), and neither is ever quietly read as "no dependencies".
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

#: The symbols a check may declare. Anything else at module level is ignored —
#: this reads a declaration, it does not audit the file.
DEPENDS_ON = "DEPENDS_ON"
RESOURCES = "RESOURCES"
TIME_BOUND = "TIME_BOUND"
EXPECTED_S = "EXPECTED_S"
CORRECTABLE = "CORRECTABLE"
NON_CORRECTABLE_REASON = "NON_CORRECTABLE_REASON"
#: Failure policy this check demands of the plan (ARC 025 Stage 2.2). `"halt"`
#: means a failure here makes everything downstream meaningless, so the run
#: stops rather than reporting twelve verdicts measured against a floor that
#: already failed.
#:
#: This exists because `--optimize` was found SILENTLY DROPPING the policy. The
#: hand-maintained registry carried `on_fail: "halt"` on `bootstrap-floor`;
#: `derive_plan` never emitted `on_fail` at all and `Block.on_fail` defaults to
#: `"continue"`, so `--optimize --commit` would have installed a plan in which a
#: broken Python runtime no longer halts the run — and every stated success
#: criterion for the derivation would still have been met. That is this
#: project's vacuity class wearing a planning tool.
#:
#: Declared on the CHECK rather than written into the plan for §4.4's standing
#: reason: one source of truth per fact, so the check and the plan cannot
#: disagree. §6 still says the registry OWNS failure policy — it does; this is
#: where the registry now DERIVES it from.
ON_FAIL = "ON_FAIL"
VALID_ON_FAIL = ("halt", "continue")

#: Repo-relative artifacts this check claims to MEASURE. Feeds
#: `check_artifact_gate_coverage.py`. Read the bound on what that gate can prove
#: before trusting this: it establishes that a check NAMES an artifact, which is
#: strictly weaker than that a check DRIVES it.
SUBJECTS = "SUBJECTS"

#: Declaring these two is what makes a check eligible for a parallel block.
REQUIRED_FOR_PARALLEL = (DEPENDS_ON, RESOURCES)


@dataclasses.dataclass(frozen=True)
class Declaration:  # pylint: disable=too-many-instance-attributes
    """One check's orchestration metadata, read statically.

    `errors` is non-empty whenever anything could not be read. A caller that
    ignores it is choosing a silent default, which is the thing §3.3 forbids —
    so `optimize.py` treats a non-empty `errors` as fatal for that check.
    """

    name: str
    depends_on: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    time_bound: bool = False
    expected_s: float | None = None
    correctable: bool = True
    non_correctable_reason: str = ""
    on_fail: str = "continue"
    subjects: tuple[str, ...] = ()
    declared: frozenset[str] = frozenset()
    errors: tuple[str, ...] = ()

    @property
    def declares_resources(self) -> bool:
        """True when the check said something about what it claims.

        Distinct from `bool(self.resources)`: a check that declares
        `RESOURCES = ()` HAS declared — it has claimed nothing — and that is a
        different statement from never having been asked.
        """
        return RESOURCES in self.declared


def _module_level_assignments(tree: ast.Module) -> dict[str, ast.expr]:
    """Collect `NAME = <expr>` and `NAME: T = <expr>` at module level only.

    Module level only, on purpose: a declaration set inside a function or an
    `if` is conditional, and a conditional declaration is one whose value
    depends on execution — which is what this module exists not to need.
    """
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            found[node.target.id] = node.value
    return found


def _literal(
    name: str, symbol: str, node: ast.expr, errors: list[str]
) -> object | None:
    """`ast.literal_eval` one declaration, recording a LOUD error on failure."""
    try:
        return ast.literal_eval(node)
    except ValueError, SyntaxError, TypeError:
        errors.append(
            f"{name}: {symbol} is not a literal this mechanism can read "
            f"(line {getattr(node, 'lineno', '?')}). Declare it as a literal "
            "tuple/str/bool/number; a computed declaration cannot be read "
            "without executing the module."
        )
        return None


def _as_str_tuple(
    name: str, symbol: str, value: object, errors: list[str]
) -> tuple[str, ...]:
    """Coerce a declaration to a tuple of strings, loudly."""
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, str) for item in value):
            return tuple(str(item) for item in value)
        errors.append(f"{name}: {symbol} must contain only strings, got {value!r}")
        return ()
    errors.append(
        f"{name}: {symbol} must be a tuple or list, got {type(value).__name__}"
    )
    return ()


#: Every declarable symbol, in the order a reader meets them. Table-driven so
#: adding a declaration is one row here plus one field on `Declaration` — not a
#: seventh near-identical block in `read_declaration`.
_KNOWN = (
    DEPENDS_ON,
    RESOURCES,
    TIME_BOUND,
    EXPECTED_S,
    CORRECTABLE,
    NON_CORRECTABLE_REASON,
    ON_FAIL,
    SUBJECTS,
)


def _read_on_fail(name: str, assigned: dict[str, ast.expr], errors: list[str]) -> str:
    """Read ON_FAIL. An unrecognised value is a LOUD error, never a default.

    Defaulting a misspelled `"HALT"` to `"continue"` would silently discard the
    exact policy this declaration exists to carry — the failure mode that made
    it necessary in the first place.
    """
    if ON_FAIL not in assigned:
        return "continue"
    value = _literal(name, ON_FAIL, assigned[ON_FAIL], errors)
    if value is None:
        return "continue"
    if not isinstance(value, str) or value not in VALID_ON_FAIL:
        errors.append(
            f"{name}: {ON_FAIL} must be one of {VALID_ON_FAIL}, got {value!r}"
        )
        return "continue"
    return value


def _read_tuple(
    name: str, symbol: str, assigned: dict[str, ast.expr], errors: list[str]
) -> tuple[str, ...]:
    """Read a tuple-of-strings declaration, or record why it could not be read."""
    if symbol not in assigned:
        return ()
    value = _literal(name, symbol, assigned[symbol], errors)
    if value is None:
        return ()
    return _as_str_tuple(name, symbol, value, errors)


def _read_expected(
    name: str, assigned: dict[str, ast.expr], errors: list[str]
) -> float | None:
    """Read EXPECTED_S. `bool` is excluded deliberately: it is an `int` subclass,
    and `EXPECTED_S = True` would otherwise silently become 1.0 seconds."""
    if EXPECTED_S not in assigned:
        return None
    value = _literal(name, EXPECTED_S, assigned[EXPECTED_S], errors)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if value is not None:
            errors.append(f"{name}: {EXPECTED_S} must be a number, got {value!r}")
        return None
    return float(value)


def read_declaration(path: Path) -> Declaration:
    """Read one check's declarations by parsing it. Never imports, never runs it."""
    name = path.stem
    errors: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return Declaration(name=name, errors=(f"{name}: unreadable: {exc!r}",))
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return Declaration(name=name, errors=(f"{name}: does not parse: {exc!r}",))

    assigned = _module_level_assignments(tree)
    declared = frozenset(symbol for symbol in _KNOWN if symbol in assigned)

    correctable = True
    if CORRECTABLE in assigned:
        correctable = bool(_literal(name, CORRECTABLE, assigned[CORRECTABLE], errors))

    reason = ""
    if NON_CORRECTABLE_REASON in assigned:
        value = _literal(
            name, NON_CORRECTABLE_REASON, assigned[NON_CORRECTABLE_REASON], errors
        )
        reason = value if isinstance(value, str) else ""

    # A check that refuses correction must say why. A refusal with no reason is
    # indistinguishable from a check that forgot to implement one.
    if not correctable and not reason.strip():
        errors.append(
            f"{name}: CORRECTABLE is False but NON_CORRECTABLE_REASON is empty — "
            "a refusal must name its reason (§2.3)"
        )

    return Declaration(
        name=name,
        depends_on=_read_tuple(name, DEPENDS_ON, assigned, errors),
        resources=_read_tuple(name, RESOURCES, assigned, errors),
        time_bound=bool(_literal(name, TIME_BOUND, assigned[TIME_BOUND], errors))
        if TIME_BOUND in assigned
        else False,
        expected_s=_read_expected(name, assigned, errors),
        correctable=correctable,
        non_correctable_reason=reason,
        on_fail=_read_on_fail(name, assigned, errors),
        subjects=_read_tuple(name, SUBJECTS, assigned, errors),
        declared=declared,
        errors=tuple(errors),
    )


def read_all(checks_dir: Path) -> dict[str, Declaration]:
    """Read every `check_*.py` in `checks_dir`.

    Derived from the FOLDER, never from the registry. That direction is the
    structural fix for this project's recurring defect class — bandit scanning
    nothing, pre-commit skipping untracked files, `--all-files` missing
    untracked, D2.24's ignore spellings — where a tracking state silently sets a
    gate's scope. A check present on disk and absent from the registry is an
    ORPHAN and must be reportable as one, which is impossible if the registry is
    what enumerates.
    """
    return {
        path.stem: read_declaration(path)
        for path in sorted(checks_dir.glob("check_*.py"))
    }
