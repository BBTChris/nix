#!/usr/bin/env python3
"""D3.205 — no `git` subprocess in this tree runs on an inherited environment.

## Why a GATE and not another remembered call site

`git` honours `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` **ahead of `-C`
and ahead of `cwd`**, and `pre-commit` (and `git` itself) export them into every
hook. `nixverify.gitenv.scrubbed_env` has existed since ARC 026 and the rule was
applied **per site, from memory**. ARC 035 measured what that is worth: five
unscrubbed calls in `scripts/harness.py` rewrote the canonical index and wrote
`core.bare = true` onto `/home/bbt/nix`, and the class **recurred three times in
one arc — twice inside the instrument built to police it**.

A rule enforced by remembering is not enforced. This gate makes the sixth
unscrubbed call impossible to add quietly, and it is the reason ARC 036's
Phase 0 is blocking: the arc that follows it spawns five worktrees, each
running git.

## The list is DERIVED, never snapshotted (§0f)

There is no accepted-call-site list in this file. Every run re-enumerates the
tracked `.py` files under `scripts/` and `checks/` with `git ls-files` and
re-parses them, so a **new** unscrubbed call added by a later arc reddens this
gate without anyone remembering to add it anywhere. A snapshot would be a moving
anchor (`debug.md` §8 failure mode #4) at exactly the cadence this has to be
right.

## The deliberate exception, stated at the call site and nowhere else

`scripts/tests/test_gitenv_hostile.py` and **this gate's own corruption half**
must run git **unscrubbed** — that is the control that proves the hostile
environment is genuinely hostile. Such a call carries the `MARKER` comment on or
beside its own line. The marker is not a way out: `MARKER_SCOPE` is an
ENUMERATED pair of paths, not a directory rule, and the gate reports every
marker it honoured on every run so the exception cannot grow silently.

This gate REDDENED ON ITSELF the first time it ran over the whole tree, on a
`_git` helper whose `env=env` parameter made the two halves indistinguishable at
the call site. Both the helper and the scope rule below are what that verdict
produced.

## Both halves, and then the harness's own blind spot

The static scan alone would prove that the word `scrubbed_env` appears in the
right places. So the gate also DRIVES the mechanism against a throwaway victim
repository:

* **The unscrubbed half must CORRUPT.** Same argv, hostile `GIT_DIR` /
  `GIT_INDEX_FILE` / `GIT_WORK_TREE`, no scrub — the victim's index **must**
  change. *If it does not change, this gate FAILS.* A control that cannot
  demonstrate the defect is not a passing control, it is a blind one, and
  reading its silence as safety is the exact reading that let D3.205 recur.
* **The scrubbed half must be INERT.** Same argv, the same hostile environment
  passed through `scrubbed_env`, and the victim's index must come back
  **byte-identical**.

* **And the whole control is then re-run under a hostile AMBIENT environment**
  — `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` planted into what the
  fixtures themselves inherit. This is the plant D3.205 asks for: it is where
  the defect masked itself twice, because a harness building its victim under
  an inherited `GIT_WORK_TREE` builds it somewhere else, and then the
  corruption half quietly stops corrupting. Both runs must reach the same
  verdict; a silence under the hostile ambient is a FAIL naming the masking.

Every fixture git call in this module runs under `scrubbed_env` — the fixture
that builds the isolation must not be the thing that breaks it (doctrine C.8).

## Non-vacuity

A green here means nothing unless the scan actually saw git calls, and unless
the analyser can say NO. Both are re-derived every run: the scan asserts it
found at least `MIN_CALL_SITES` real git invocations, and the analyser is driven
over a synthetic source holding one scrubbed and one unscrubbed call and must
flag **exactly** the unscrubbed one. An analyser that flags neither, or both, is
reported as blind rather than as green.

EVERY FINDING NAMES THE REASON, never an exit code (check contract §11/§18):
the file, the line, the resolved `env=` expression, and which of the three
selector variables survived.
"""

# pylint: disable=duplicate-code
# R0801 pairs this module's §4.4 declaration preamble with every other check
# that shells out to git. THE DUPLICATION CANNOT BE FACTORED OUT AND THAT IS THE
# DESIGN: `PRIVILEGE`, `DEPENDS_ON`, `RESOURCES` and the rest are read
# STATICALLY, by AST, without importing the check (check contract §4.4), so a
# shared base module would be invisible to that reader.
from __future__ import annotations

import ast
import dataclasses
import hashlib
import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, tmp dirs only
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import PREFIX, SELECTORS, scrubbed_env

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first: this gate reads the tracked tree and drives git in a
#: temporary directory. It produces no artifact any other check consumes.
DEPENDS_ON: tuple[str, ...] = ()
#: `git` because this gate SPAWNS it (the enumeration plus the both-halves
#: control), and `file-write:/tmp` because the throwaway victim repository is
#: built there.
#:
#: **THE SECOND CLAIM WAS ADDED BECAUSE THE OBSERVER SAID SO, NOT BECAUSE IT WAS
#: FORESEEN.** This gate shipped declaring `("subprocess:git",)` alone, with a
#: comment reasoning that a `TemporaryDirectory` "holds nothing another check
#: contends for" and so did not need claiming. `check_observed_resource_claims`
#: reported thirty-odd real `file-write:/tmp/gitenv-gate-*` observations against
#: that declaration on the first run under the engine. The declaration was
#: honest and it was WRONG, which is exactly the case §17/rule 12 exists for:
#: claims are checked against OBSERVED use, never against their own reasoning.
#: Recorded here rather than quietly edited, because a gate built this arc to
#: stop a rule being enforced from memory should not itself be trusted from
#: memory.
RESOURCES: tuple[str, ...] = ("subprocess:git", "file-write:/tmp")
#: FALSE on the facts: one `git ls-files`, an AST parse per tracked module, and
#: roughly a dozen git invocations against a tmpfs victim.
TIME_BOUND = False
#: NON-CORRECTABLE. The only mechanical "correction" is to edit shipped source
#: and insert `env=scrubbed_env()` into a call this gate does not understand the
#: intent of — writing into the order path's neighbourhood on the strength of a
#: pattern match. The correction is a human editing the call site.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "The only mechanical correction available is to insert `env=scrubbed_env()` "
    "into a shipped call this gate matched by AST shape and does not understand "
    "the intent of — an automated edit into the neighbourhood of the order path, "
    "on the strength of a pattern match. Worse, the marker path makes the "
    "cheaper 'correction' a one-line comment that silences the finding, which is "
    "the exact move D3.205 is a record of. Two of the fourteen call sites this "
    "gate first reddened on were DELIBERATE controls that had to stay "
    "unscrubbed, and no rule available to a corrector could tell them from the "
    "twelve that were defects. A human edits the call site."
)
INSTALLABLE = False
ON_FAIL = "continue"

NAME = "check_git_env_scrub"

#: The comment token that marks a DELIBERATE unscrubbed call. Honoured only
#: within `MARKER_SCOPE` — see the module docstring.
MARKER = "gitenv-allow-unscrubbed"
#: Where a marked call may live, ENUMERATED. A control belongs with its test —
#: and this gate's own both-halves control lives inside this gate, which is the
#: second entry and the only one outside `scripts/tests/`.
#:
#: THE SECOND ENTRY EXISTS BECAUSE THIS GATE REDDENED ON ITSELF. Written with
#: `scripts/tests/` as the only scope, its first live run over the whole tree
#: reported `checks/check_git_env_scrub.py`'s own corruption half as an
#: offender — correctly, because that call IS unscrubbed and must be, or the
#: gate has no control. Widening the scope to the `checks/` DIRECTORY would have
#: bought the green by making every gate in the tree eligible for a one-line
#: silencer; naming the single file keeps the ratchet, and a third entry means
#: editing this tuple where a reviewer sees it.
MARKER_SCOPE = ("scripts/tests/", "checks/check_git_env_scrub.py")

#: Non-vacuity floor for the enumeration. The tree carried well over twenty git
#: invocations when this gate was written; a scan reporting fewer than this has
#: lost its subject (an empty `ls-files`, a parse that silently failed) and its
#: green would be an artefact of the instrument, not a property of the tree.
MIN_CALL_SITES = 10

#: The `subprocess` entry points that can start a process.
RUNNERS = frozenset({"run", "Popen", "check_output", "check_call", "call"})

#: The three variables measured doing damage. Named so a finding can say WHICH
#: one survived rather than "the environment was wrong".
DAMAGING = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")

#: The scope that is scanned. Derived per run from `git ls-files`.
SCAN_ROOTS = ("scripts", "checks")


@dataclasses.dataclass(frozen=True)
class Site:
    """One `git` subprocess invocation found in the tree."""

    path: str
    line: int
    env_expr: str
    scrubbed: bool
    marked: bool

    @property
    def where(self) -> str:
        """`path:line`, the anchor every finding is reported against."""
        return f"{self.path}:{self.line}"


# --------------------------------------------------------------------------
# The analyser. Exported so a test can drive it over synthetic sources, which
# is how its can-fail binding is re-established every run rather than recorded.
# --------------------------------------------------------------------------


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return "<absent>"
    try:
        return ast.unparse(node)
    except AttributeError, ValueError:  # pragma: no cover - defensive
        return f"<{type(node).__name__}>"


class _Resolver:
    """Name and function-return bindings for one module.

    Deliberately whole-file and not scope-exact. A name bound to `"git"` in one
    function and to something else in another is resolved as a git call, and a
    name bound to a scrub in one place is NOT accepted as scrubbed unless every
    binding of it resolves to a scrub. Both directions err toward reporting,
    which is the safe direction for a gate whose failure mode is silence.

    ## Exactly ONE cross-module hop, and why not zero and not two

    Several test harnesses deliberately spell the scrub as the GATE's own helper
    — `env=gate._clean_git_env()`, `env=gate.git_env()` — and say why in their
    docstrings: *"the harness runs git exactly the way the gate does, so a
    hazard can never be invisible on one side and live on the other."* That is a
    real property, so a resolver that cannot see through the hop would force
    those call sites to be rewritten and would delete it.

    So `alias.helper()` is followed **once**, into the module `alias` names,
    using the same tracked-file index the scan is derived from — no list of
    blessed helper names anywhere (that would be the moving anchor this gate is
    built to avoid). A second hop is NOT followed and resolves to unproven: at
    two hops the reader of the call site can no longer see what the environment
    is, which is the condition under which three private spellings of this scrub
    drifted apart in the first place.
    """

    def __init__(
        self,
        tree: ast.AST,
        *,
        modules: dict[str, str] | None = None,
        depth: int = 0,
    ) -> None:
        self.assign: dict[str, list[ast.expr]] = {}
        self.returns: dict[str, list[ast.expr]] = {}
        #: alias -> module name, from `import X as Y` / `from P import X as Y`.
        self.aliases: dict[str, str] = {}
        #: module name -> source text, supplied by the caller from the tracked set.
        self.modules = modules or {}
        self.depth = depth
        for node in ast.walk(tree):
            self._collect_alias(node)
            self._collect_binding(node)

    def _collect_alias(self, node: ast.AST) -> None:
        """`import X as Y` / `from P import X as Y` -> alias -> module name."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                key = alias.asname or alias.name.split(".")[0]
                self.aliases[key] = alias.name.split(".")[-1]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                self.aliases[alias.asname or alias.name] = alias.name

    def _collect_binding(self, node: ast.AST) -> None:
        """Name assignments and function returns, whole-file (see class doc)."""
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.assign.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                self.assign.setdefault(node.target.id, []).append(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._collect_returns(node)

    def _collect_returns(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Every value this function can return, by function name."""
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and inner.value is not None:
                self.returns.setdefault(node.name, []).append(inner.value)

    # -- argv head ------------------------------------------------------
    def argv_head(self, node: ast.expr | None, depth: int = 0) -> str | None:
        """The literal program name an argv expression starts with, or None.

        The four shapes that occur in this tree, in order: a bare string; a
        list/tuple literal (`["git", ...]`); a concatenation whose LEFT side
        carries the head (`base + args`, `("git",) + args`); and a name or call
        that has to be resolved through a binding.
        """
        if node is None or depth > 6:
            return None
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, (ast.List, ast.Tuple)):
            return self.argv_head(node.elts[0], depth + 1) if node.elts else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.argv_head(node.left, depth + 1)
        return self._resolved_head(node, depth)

    def _resolved_head(self, node: ast.expr, depth: int) -> str | None:
        """A name or a call resolved through its bindings. `Starred` is opaque."""
        if isinstance(node, ast.Name):
            return self._first_head(self.assign.get(node.id, ()), depth)
        if isinstance(node, ast.Call):
            return self._first_head(self.returns.get(_call_name(node) or "", ()), depth)
        return None

    def _first_head(self, bound: Iterable[ast.expr], depth: int) -> str | None:
        """The first binding that resolves to a literal program name."""
        for value in bound:
            head = self.argv_head(value, depth + 1)
            if head is not None:
                return head
        return None

    # -- env ------------------------------------------------------------
    def env_scrubbed(self, node: ast.expr | None, depth: int = 0) -> bool:
        """True only if this `env=` expression provably routes through the scrub."""
        if node is None or depth > 6:
            return False
        if isinstance(node, ast.Call):
            return self._call_scrubs(node, depth)
        if isinstance(node, ast.Name):
            bound = self.assign.get(node.id) or []
            return bool(bound) and all(
                self.env_scrubbed(value, depth + 1) for value in bound
            )
        if isinstance(node, ast.Dict):
            # `{**scrubbed_env(), "GIT_AUTHOR_NAME": ...}` — the scrub must be
            # one of the `**` spreads, or the dict is an authored environment.
            return any(
                key is None and self.env_scrubbed(value, depth + 1)
                for key, value in zip(node.keys, node.values, strict=True)
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self.env_scrubbed(node.left, depth + 1) or self.env_scrubbed(
                node.right, depth + 1
            )
        return False

    def _call_scrubs(self, node: ast.Call, depth: int) -> bool:
        """Whether a CALL used as `env=` resolves through the scrub."""
        name = _call_name(node)
        if name is not None and name.split(".")[-1] == "scrubbed_env":
            # THE NAME ALONE IS NOT ENOUGH. A module could define
            # `def scrubbed_env(): return os.environ` and buy silence off a
            # spelling. It counts only where the module IMPORTS the real one
            # — which `scripts/harness.py` and `scripts/monitor.py` both do
            # inside a `try:`, above their standalone-copy fallbacks, so the
            # documented exception still resolves and a fake one does not.
            return "scrubbed_env" in self.aliases
        if name == "dict":
            parts = list(node.args) + [kw.value for kw in node.keywords]
            return any(self.env_scrubbed(part, depth + 1) for part in parts)
        if name and "." not in name and name in self.returns:
            return all(self.env_scrubbed(b, depth + 1) for b in self.returns[name])
        return self._cross_module_scrub(name)

    def _cross_module_scrub(self, name: str | None) -> bool:
        """`alias.helper()` — follow it into `alias`'s module, ONCE."""
        if self.depth >= 1 or not name or "." not in name:
            return False
        alias, _, helper = name.rpartition(".")
        module = self.aliases.get(alias)
        source = self.modules.get(module or "")
        if source is None:
            return False
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        inner = _Resolver(tree, modules=self.modules, depth=self.depth + 1)
        bound = inner.returns.get(helper)
        if not bound:
            return False
        return all(inner.env_scrubbed(value) for value in bound)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return f"{_unparse(func.value)}.{func.attr}"
    return None


def _is_runner(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in RUNNERS and _unparse(func.value).endswith("subprocess")
    if isinstance(func, ast.Name):
        return func.id in RUNNERS
    return False


def scan_source(
    rel_path: str, text: str, modules: dict[str, str] | None = None
) -> tuple[list[Site], str]:
    """Every `git` subprocess call in one module. Returns (sites, error).

    `modules` maps a module name to its source and is what the single
    cross-module hop reads; it is built from the same `git ls-files` enumeration
    the scan is derived from, never from a list in this file.

    A non-empty error means this module could not be parsed and the caller must
    treat that as CANNOT_MEASURE — a parse failure read as "no git calls here"
    is precisely the fail-open silence this gate exists to refuse.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], f"{rel_path}: cannot parse: {exc}"
    lines = text.splitlines()
    resolver = _Resolver(tree, modules=modules)
    sites = [
        site
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_runner(node)
        if (site := _site_for(node, rel_path, lines, resolver)) is not None
    ]
    return sites, ""


def _argv_of(node: ast.Call) -> ast.expr | None:
    """The argv expression, positional or `args=`."""
    if node.args:
        return node.args[0]
    return next((kw.value for kw in node.keywords if kw.arg == "args"), None)


def _site_for(
    node: ast.Call, rel_path: str, lines: list[str], resolver: _Resolver
) -> Site | None:
    """One `Site` if this call spawns `git`, else None."""
    head = resolver.argv_head(_argv_of(node))
    if head is None or Path(head).name != "git":
        return None
    env_kw = next((k for k in node.keywords if k.arg == "env"), None)
    start = max(0, node.lineno - 2)
    end = min(len(lines), (node.end_lineno or node.lineno) + 1)
    return Site(
        path=rel_path,
        line=node.lineno,
        env_expr=_unparse(env_kw.value if env_kw is not None else None),
        scrubbed=env_kw is not None and resolver.env_scrubbed(env_kw.value),
        marked=any(MARKER in line for line in lines[start:end]),
    )


def offenders(sites: list[Site]) -> list[Site]:
    """Sites that run git on an inherited environment without saying so."""
    out = []
    for site in sites:
        if site.scrubbed:
            continue
        if site.marked and site.path.startswith(MARKER_SCOPE):
            continue
        out.append(site)
    return out


# --------------------------------------------------------------------------
# The tree enumeration
# --------------------------------------------------------------------------


def tracked_python(home: Path) -> tuple[list[str], str]:
    """Tracked `.py` files under the scanned roots. Returns (paths, error)."""
    try:
        proc = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["git", "ls-files", "--", *SCAN_ROOTS],
            cwd=home,
            capture_output=True,
            text=True,
            check=False,
            env=scrubbed_env(),
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"git ls-files failed: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return [], f"git ls-files exit {proc.returncode}: {proc.stderr.strip()}"
    return sorted(line for line in proc.stdout.splitlines() if line.endswith(".py")), ""


# --------------------------------------------------------------------------
# The both-halves control, driven against a throwaway victim
# --------------------------------------------------------------------------


def _git(
    args: list[str], cwd: Path, ambient: Mapping[str, str]
) -> subprocess.CompletedProcess:
    """Every FIXTURE git call, scrubbed HERE where the scrub is visible.

    It takes the AMBIENT environment rather than a ready-made one, and does the
    scrub itself. Written the other way — `env` as a parameter the caller fills
    in — this helper's own call site read `env=env`, which is a variable holding
    whatever the caller decided, and THIS GATE REDDENED ON IT. That was the
    right verdict: a reader of this line could not tell a scrubbed call from an
    inherited one, which is the entire property being policed.

    The one call in this module that must NOT be scrubbed is written inline in
    `drive_control`, at full length, with the marker on it.
    """
    return subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp only
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_env(ambient, extra=_IDENTITY),
        timeout=60,
    )


_IDENTITY = {
    "GIT_AUTHOR_NAME": "gate",
    "GIT_AUTHOR_EMAIL": "gate@localhost",
    "GIT_COMMITTER_NAME": "gate",
    "GIT_COMMITTER_EMAIL": "gate@localhost",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclasses.dataclass(frozen=True)
class ControlResult:
    """What the two halves did to the victim's index."""

    corrupted_unscrubbed: bool
    inert_scrubbed: bool
    before: str
    after_unscrubbed: str
    after_scrubbed: str
    error: str = ""


def drive_control(root: Path, ambient: dict[str, str]) -> ControlResult:
    """Corrupt a victim with an unscrubbed call; prove the scrub prevents it.

    `ambient` is the environment the FIXTURES inherit. Passing a hostile one is
    the D3.205 plant: a harness that builds its victim under an inherited
    `GIT_WORK_TREE` builds it elsewhere, and the corruption half then quietly
    stops corrupting. Every fixture call below runs under `scrubbed_env(ambient)`
    precisely so that plant cannot land — and the caller re-runs this whole
    routine with a hostile ambient to prove it.
    """
    victim = root / "victim"
    scratch = root / "scratch"
    victim.mkdir(parents=True)
    scratch.mkdir(parents=True)

    proc = _git(["init", "-q", "."], victim, ambient)
    if proc.returncode != 0:
        return ControlResult(False, False, "", "", "", f"victim init: {proc.stderr}")
    (victim / "victim_tracked_marker.txt").write_text("victim\n", encoding="utf-8")
    _git(["add", "-A"], victim, ambient)
    proc = _git(["commit", "-qm", "victim baseline"], victim, ambient)
    if proc.returncode != 0:
        return ControlResult(False, False, "", "", "", f"victim commit: {proc.stderr}")

    index = victim / ".git" / "index"
    if not index.is_file():
        return ControlResult(False, False, "", "", "", "victim has no .git/index")
    before = _digest(index)
    pristine = root / "index.pristine"
    shutil.copy2(index, pristine)

    # A file that exists ONLY in the scratch tree. If the hostile variables win,
    # it lands in the victim's index — a name that cannot be there by accident.
    (scratch / "hostile_intruder_marker.txt").write_text("intruder\n", encoding="utf-8")

    hostile = dict(ambient)
    hostile.update(_IDENTITY)
    hostile["GIT_DIR"] = str(victim / ".git")
    hostile["GIT_WORK_TREE"] = str(scratch)
    hostile["GIT_INDEX_FILE"] = str(index)

    # HALF 1 — UNSCRUBBED ON PURPOSE. It MUST corrupt the victim, and the whole
    # gate turns on this one call reaching it. Written inline at full length
    # rather than through `_git`, because `_git` scrubs and this must not: the
    # difference between the two halves has to be READABLE at the call site,
    # which is the property this gate polices everywhere else.
    subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp only
        ["git", "add", "-A"],  # gitenv-allow-unscrubbed
        cwd=str(scratch),
        capture_output=True,
        text=True,
        check=False,
        env=hostile,
        timeout=60,
    )
    after_unscrubbed = _digest(index)

    shutil.copy2(pristine, index)
    if _digest(index) != before:  # pragma: no cover - defensive
        return ControlResult(
            False, False, before, after_unscrubbed, "", "victim index restore failed"
        )

    # HALF 2 — the SAME hostile environment, through the scrub. MUST be inert.
    _git(["add", "-A"], scratch, hostile)
    after_scrubbed = _digest(index)

    return ControlResult(
        corrupted_unscrubbed=after_unscrubbed != before,
        inert_scrubbed=after_scrubbed == before,
        before=before,
        after_unscrubbed=after_unscrubbed,
        after_scrubbed=after_scrubbed,
    )


def analyser_can_fail() -> tuple[bool, str]:
    """Drive the analyser over one scrubbed and one unscrubbed call.

    Re-derived every run. A binding that is recorded rather than measured is the
    thing §4.9 says does not survive a retrofit; this one is re-established at
    the moment of use.
    """
    probe = (
        "import subprocess\n"
        "from nixverify.gitenv import scrubbed_env\n"
        "def good():\n"
        "    return subprocess.run(['git', 'status'], env=scrubbed_env())\n"
        "def bad():\n"
        "    return subprocess.run(['git', 'status'])\n"
    )
    sites, error = scan_source("probe.py", probe)
    if error:
        return False, f"analyser could not parse its own probe: {error}"
    if len(sites) != 2:
        return False, f"analyser saw {len(sites)} git call(s) in a 2-call probe"
    bad = offenders(sites)
    if len(bad) != 1 or bad[0].line != 6:
        return False, (
            "analyser flagged "
            + (", ".join(s.where for s in bad) or "nothing")
            + " in a probe whose ONLY unscrubbed call is probe.py:6 — it cannot "
            "tell a scrubbed call from an inherited one, so its silence is blind"
        )
    return True, ""


# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Scan:
    """What the tree enumeration found. `error` non-empty means CANNOT_MEASURE."""

    sites: list[Site]
    modules_read: int
    error: str = ""


def scan_tree(home: Path) -> Scan:
    """Every git invocation in the tracked scope, derived fresh."""
    paths, error = tracked_python(home)
    if error:
        return Scan([], 0, f"the scanned scope could not be derived: {error}")

    sources: dict[str, str] = {}
    problems: list[str] = []
    for rel in paths:
        try:
            sources[rel] = (home / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{rel}: unreadable: {exc!r}")

    #: module name -> source, for the single cross-module hop. Derived from the
    #: tracked set; a name colliding across roots keeps the first, which is only
    #: ever consulted to CONFIRM a scrub, never to excuse one.
    modules: dict[str, str] = {}
    for rel, text in sources.items():
        modules.setdefault(Path(rel).stem, text)

    sites: list[Site] = []
    for rel, text in sources.items():
        found, err = scan_source(rel, text, modules)
        if err:
            problems.append(err)
            continue
        sites.extend(found)

    if problems:
        return Scan(
            [],
            len(paths),
            "modules in the scanned scope could not be read or parsed, so an "
            "unscrubbed call in them would be invisible: " + "; ".join(problems),
        )
    return Scan(sites, len(paths))


def _control_findings(label: str, result: ControlResult) -> list[str]:
    """What one both-halves run says went wrong, or nothing."""
    if result.error:
        return [f"{label}: control could not run: {result.error}"]
    out = []
    if not result.corrupted_unscrubbed:
        out.append(
            f"{label}: THE CONTROL IS BLIND — an unscrubbed `git add -A` under "
            f"GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE left the victim index at "
            f"{result.before[:12]} unchanged. The subject was not reproduced, so "
            "the scrubbed half proves nothing. This is the masking D3.205 "
            "measured twice, not a pass"
        )
    if not result.inert_scrubbed:
        out.append(
            f"{label}: scrubbed_env DID NOT NEUTRALISE the hostile environment — "
            f"victim index {result.before[:12]} -> {result.after_scrubbed[:12]} "
            "across a scrubbed call"
        )
    return out


def drive_both_ambients() -> tuple[ControlResult, ControlResult, list[str]]:
    """The control under a clean ambient AND under the D3.205 plant."""
    with tempfile.TemporaryDirectory(prefix="gitenv-gate-") as tmp:
        clean = drive_control(Path(tmp) / "clean", scrubbed_env())
    hostile = scrubbed_env(
        os.environ,
        extra={var: str(Path(tempfile.gettempdir()) / "nowhere") for var in DAMAGING},
    )
    with tempfile.TemporaryDirectory(prefix="gitenv-gate-") as tmp:
        planted = drive_control(Path(tmp) / "planted", hostile)
    findings = _control_findings("clean-ambient", clean) + _control_findings(
        "hostile-ambient", planted
    )
    return clean, planted, findings


def _evidence(scan: Scan, bad: list[Site], marked: list[Site], clean) -> str:
    return (
        f"derived {len(scan.sites)} git invocation(s) from {scan.modules_read} "
        f"tracked module(s) under {'/, '.join(SCAN_ROOTS)}/; "
        f"{len(scan.sites) - len(bad) - len(marked)} route through "
        f"nixverify.gitenv.scrubbed_env, {len(marked)} are declared unscrubbed "
        f"controls under {MARKER_SCOPE} "
        f"({', '.join(s.where for s in marked) or 'none'}); the both-halves "
        f"control corrupted a throwaway victim's index with an unscrubbed call "
        f"({clean.before[:12]} -> {clean.after_unscrubbed[:12]}) and left it "
        f"byte-identical through the scrub, under a clean ambient AND under a "
        f"planted hostile ambient ({', '.join(DAMAGING)}); the scrub rule is the "
        f"{PREFIX!r} prefix over {len(SELECTORS)} named selectors"
    )


def _cannot(site: str, detail: str) -> CheckResult:
    return CheckResult(
        name=NAME, status=Status.CANNOT_MEASURE, site=f"{NAME}:{site}", detail=detail
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure it. See the module docstring for what and why."""
    try:
        can_fail, why = analyser_can_fail()
        if not can_fail:
            return _cannot("analyser_can_fail", why)

        scan = scan_tree(ctx.nix_home)
        if scan.error:
            return _cannot("scan", scan.error)
        if len(scan.sites) < MIN_CALL_SITES:
            return _cannot(
                "non-vacuity",
                f"the scan found {len(scan.sites)} git invocation(s) across "
                f"{scan.modules_read} tracked module(s), below the floor of "
                f"{MIN_CALL_SITES}. The scope has been lost; a green over an "
                "empty scope measures nothing",
            )

        clean, _planted, control_findings = drive_both_ambients()

        bad = offenders(scan.sites)
        marked = [s for s in scan.sites if s.marked and s.path.startswith(MARKER_SCOPE)]
        evidence = _evidence(scan, bad, marked, clean)

        findings = control_findings + [
            f"{s.where}: runs `git` with env={s.env_expr} — an inherited "
            f"environment. Under a hook git exports {'/'.join(DAMAGING)} and "
            "`-C` does NOT override them, so this call talks about whatever "
            "started the process. Route it through "
            "nixverify.gitenv.scrubbed_env()"
            for s in bad
        ]
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(
                    [s.where for s in bad]
                    + [f"{NAME}:control"] * bool(control_findings)
                ),
                evidence=evidence,
                detail="; ".join(findings),
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
