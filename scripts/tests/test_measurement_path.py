"""The §0c classifier's can-fail: it must not say DECLARATION-ONLY while `run()` moved.

ARC 026 / A3. §0c's ratification condition is that the thing deciding
"declaration-only" is itself bound, because every binding claim in the system
now rests on it. This file is that binding.

**Every plant here is a synthetic check built under `tmp_path`.** Doctrine C.8:
a plant never touches a production artifact, and the artifacts this classifier
judges are the fifteen registered gates. The only production subjects are
read-only — `checks/check_derived_claims.py` for non-vacuity, and immutable git
history for the real-subject arm.

WHAT THE REAL-SUBJECT ARM MEASURED, because it is the finding rather than the
apparatus: re-run over ARC 025's own diff (`45a37fa` -> `0f9c5b9`), this
classifier reports **declaration-only for 0 of 15 checks**, against the ten
ARC 025 ruled declaration-only. Two independent reasons, both measured:

  * `scripts/nixverify/contract.py` changed in that arc, and the function that
    changed is `validate_result` — the post-processor EVERY check's verdict
    passes through. It gained `guard_owner_defect`, which downgrades a GUARDED
    verdict whose owner names a range. Every check imports it transitively, so
    every check's measurement path moved without its own file being touched.
  * Even ignoring cross-file edits, six of the ten had their
    `if __name__ == "__main__":` block rewritten by the retrofit — that block
    is the standalone CLI, which is how `verify.py` and every can-fail control
    invoke the gate.

Four (`check_venv`, `check_python_deps`, `check_order_path_bans`,
`check_verify_logging`) are declaration-only *within their own file*, and that
is what `test_arc025_check_venv_is_declaration_only_within_its_own_file`
asserts. The cross-file arm is what flips them, and
`test_arc025_check_venv_flips_when_the_shared_contract_moves` is the
verdict-by-verdict pair that proves the arm is the discriminator rather than a
blanket "everything changed".
"""

from __future__ import annotations

# R0801: see test_check_python_runtime.py. Each instrument's control stands on
# its own file; one shared helper would let a single edit un-bind several.
# pylint: disable=duplicate-code
import ast
import subprocess  # nosec B404 - fixed argv, shell=False, repo history only
import sys
import textwrap
from collections.abc import Iterable
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixverify.gitenv import scrubbed_env  # pylint: disable=import-error
from nixverify.measurement_path import (  # pylint: disable=import-error
    DECLARATION_ONLY,
    DECLARATION_SYMBOLS,
    MEASUREMENT_PATH,
    UNDECIDABLE,
    Classification,
    _split,  # pylint: disable=import-error
    classify_source,
    measurement_closure,
    resolve_imports,
)

# ---------------------------------------------------------------------------
# THE SUBJECT UNDER PLANT — a synthetic check with the shape that matters.
#
# `_probe_only` is reachable ONLY through `PROBES` -> `_probe_main` -> the
# `__main__` block. That is `check_derived_claims`'s real shape: twenty-one of
# its measurements are re-entered as `{self} --probe`, and `run()` names none
# of them. A classifier rooted at `run` alone is blind to every one.
# ---------------------------------------------------------------------------
BASE = textwrap.dedent(
    '''
    """A synthetic check. Never registered, never run — plant material only."""

    from __future__ import annotations

    import json
    from pathlib import Path

    NAME = "check_synthetic"
    PRIVILEGE = "user"
    DEPENDS_ON: tuple[str, ...] = ("check_venv",)
    RESOURCES: tuple[str, ...] = ("venv",)
    ON_FAIL = "continue"

    _LIMIT = 3


    def _shared(home: Path) -> int:
        """Counts json files. Called by run()."""
        return len(list(home.glob("*.json")))


    def _probe_only(home: Path) -> int:
        """Counts py files. Reachable ONLY from the __main__ block."""
        return len(list(home.glob("*.py")))


    PROBES = {"probe_only": _probe_only}


    def run(mode: str, ctx: object) -> str:
        home = Path(str(ctx))
        return "fail" if _shared(home) > _LIMIT else "pass"


    def _probe_main(argv: list[str]) -> int:
        return PROBES[argv[0]](Path(argv[1]))


    if __name__ == "__main__":
        import sys

        print(json.dumps({"n": _probe_main(sys.argv[1:])}))
    '''
).strip()


def _plant(old: str, new: str, source: str = BASE) -> str:
    """One textual substitution, asserted to have actually landed."""
    assert old in source, f"plant anchor {old!r} is not in the subject"
    planted = source.replace(old, new, 1)
    assert planted != source, "the plant changed nothing"
    return planted


def _classify(
    after: str,
    *,
    changed_files: Iterable[str] = (),
    repo: Path | None = None,
) -> Classification:
    return classify_source(
        "check_synthetic", BASE, after, changed_files=changed_files, repo=repo
    )


# ===========================================================================
# NON-VACUITY — asserted before any plant (doctrine C.3).
# ===========================================================================


def test_the_declaration_vocabulary_is_derived_not_retyped() -> None:
    """The allowed-to-change set comes from `declarations.py`, not from a list here.

    Retyping the eight symbols would put this project's own restatement defect
    (doctrine B.7) inside the instrument that decides which controls survive.
    """
    from nixverify import declarations  # pylint: disable=import-outside-toplevel

    assert DECLARATION_SYMBOLS is declarations._KNOWN  # pylint: disable=protected-access
    assert "RESOURCES" in DECLARATION_SYMBOLS
    assert "ON_FAIL" in DECLARATION_SYMBOLS
    assert "PRIVILEGE" not in DECLARATION_SYMBOLS, (
        "PRIVILEGE is read by the loader and is not a declaration this "
        "classifier may wave through"
    )


def test_the_synthetic_subject_has_the_shape_the_plants_need() -> None:
    """The plant material must contain a probe run() cannot see, or plant 5 is vacuous."""
    module = _split(ast.parse(BASE))
    closure = measurement_closure(module)
    assert "run" in closure
    assert "_shared" in closure
    assert "_probe_only" in closure, (
        "the probe-only path is not in the closure — the headline plant would "
        "pass for the wrong reason"
    )
    assert "PROBES" in closure
    assert "RESOURCES" not in closure, (
        "the subject's run() reads RESOURCES, so the aliasing plant would be "
        "measuring the wrong thing"
    )


def test_the_closure_of_a_real_check_contains_its_probes() -> None:
    """NON-VACUITY AGAINST THE REAL SUBJECT.

    `check_derived_claims` is the gate whose probes are all behind `--probe`.
    If the closure of the real file does not reach them, this classifier would
    have certified every probe edit in the system as declaration-only.
    """
    source = (REPO / "checks" / "check_derived_claims.py").read_text(encoding="utf-8")
    closure = measurement_closure(_split(ast.parse(source)))
    for required in ("run", "PROBES", "_p_registry_check_count", "_probe_main"):
        assert required in closure, f"{required} is not on the measured path"


def test_the_import_resolver_reaches_the_shared_verdict_post_processor() -> None:
    """`nixverify/contract.py` must resolve, transitively, from a real check.

    It is the file whose ARC 025 change unbound everything. A resolver that did
    not reach it would make the cross-file arm's zero a false negative.
    """
    source = (REPO / "checks" / "check_venv.py").read_text(encoding="utf-8")
    resolved = resolve_imports(REPO, source)
    assert "scripts/nixverify/contract.py" in resolved
    assert "scripts/nixverify/declarations.py" in resolved, (
        "the walk is not transitive — declarations.py is reached only through "
        "actuation.py, not imported by the check directly"
    )


# ===========================================================================
# THE TRUE NEGATIVES — it must be able to say YES, or it is not a classifier.
# ===========================================================================


def test_a_comment_only_edit_preserves_the_binding() -> None:
    """Both halves of doctrine C.2: remove the plant and it must pass."""
    after = _plant("_LIMIT = 3", "_LIMIT = 3  # tuned ARC 026")
    verdict = _classify(after)
    assert verdict.classification == DECLARATION_ONLY, verdict.reasons
    assert verdict.preserves_binding


def test_a_pure_declaration_edit_preserves_the_binding() -> None:
    """The whole reason §0c exists: adding ON_FAIL must not cost a binding."""
    after = _plant('ON_FAIL = "continue"', 'ON_FAIL = "halt"')
    verdict = _classify(after)
    assert verdict.classification == DECLARATION_ONLY, verdict.reasons
    assert verdict.declarations_changed == ("ON_FAIL",)


# ===========================================================================
# THE PLANTS. Each is one answer to "what would make it say DECLARATION-ONLY
# while run() changed?" — and each asserts the REASON, never the verdict alone
# (§18): a classifier that reddened everything would pass an exit-code-shaped
# assertion while measuring nothing.
# ===========================================================================


def test_a_literal_inside_a_helper_run_calls_is_a_measurement_change() -> None:
    """A glob pattern inside `_shared`, which `run()` calls directly."""
    after = _plant('home.glob("*.json")', 'home.glob("*.jsonl")')
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("_shared is on the measurement path" in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_a_module_constant_run_consumes_is_a_measurement_change() -> None:
    """`_TIMEOUT = 300 -> 5` in the real gate is this shape."""
    after = _plant("_LIMIT = 3", "_LIMIT = 300")
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("_LIMIT is on the measurement path" in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_a_probe_reachable_only_from_main_is_a_measurement_change() -> None:
    """THE HEADLINE PLANT — condition 1.

    `run()` never names `_probe_only`. A closure rooted at `run` alone calls
    this edit declaration-only, and in `check_derived_claims` that would cover
    every probe behind `{self} --probe`, which is where ten of its thirteen
    claims get BOTH their numbers.
    """
    after = _plant('home.glob("*.py")', 'home.glob("*.pyc")')
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any(
        "_probe_only is on the measurement path" in r for r in verdict.reasons
    ), verdict.reasons


def test_a_declaration_run_actually_reads_is_not_a_free_declaration() -> None:
    """THE ALIASING TRAP — condition 3.

    Here `run()` is rewritten to consult `RESOURCES`. From that moment the
    declaration IS part of the measurement, and the same `RESOURCES` edit that
    was free in `test_a_pure_declaration_edit_preserves_the_binding` must cost
    the binding.
    """
    aliased = _plant(
        'return "fail" if _shared(home) > _LIMIT else "pass"',
        'return "fail" if _shared(home) > len(RESOURCES) else "pass"',
    )
    verdict = classify_source(
        "check_synthetic",
        aliased,
        _plant(
            'RESOURCES: tuple[str, ...] = ("venv",)',
            "RESOURCES: tuple[str, ...] = ()",
            aliased,
        ),
    )
    assert verdict.classification == MEASUREMENT_PATH
    assert any("RESOURCES is on the measurement path" in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_a_decorator_on_a_closure_function_is_a_measurement_change() -> None:
    """`@functools.cache` on a probe changes what the second call measures."""
    after = _plant(
        "def _shared(home: Path) -> int:",
        "@staticmethod\ndef _shared(home: Path) -> int:",
    )
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("_shared is on the measurement path" in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_a_docstring_inside_the_closure_is_a_measurement_change() -> None:
    """Not pedantry — this project reads docstrings as data.

    `check_derived_claims._flagged_addition` returns True when a function's own
    docstring says "nix addition", and that decides a registered number.
    """
    after = _plant(
        '"""Counts json files. Called by run()."""',
        '"""Counts json files. A Nix addition."""',
    )
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("_shared is on the measurement path" in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_an_import_edit_is_a_measurement_change() -> None:
    """Every name the closure resolves arrives through the imports."""
    after = _plant("import json", "import json5 as json")
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("module-level imports changed" in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_a_main_block_edit_is_a_measurement_change() -> None:
    """The standalone CLI is how every can-fail control invokes a gate."""
    after = _plant('print(json.dumps({"n": _probe_main(sys.argv[1:])}))', "pass")
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("binds no name changed" in r for r in verdict.reasons), verdict.reasons


def test_an_unclassified_module_constant_fails_closed() -> None:
    """`PRIVILEGE` is read by the loader, not by run(), and is not a declaration.

    The classifier has no "probably harmless" category — condition 8.
    """
    after = _plant('PRIVILEGE = "user"', 'PRIVILEGE = "root"')
    verdict = _classify(after)
    assert verdict.classification == MEASUREMENT_PATH
    assert any(
        "PRIVILEGE was changed" in r and "fails closed" in r for r in verdict.reasons
    ), verdict.reasons


def test_dynamic_namespace_access_is_undecidable_never_declaration_only() -> None:
    """`globals()["PROBES"]` makes a static name graph a guess — condition 7."""
    after = _plant("PROBES[argv[0]]", 'globals()["PROBES"][argv[0]]')
    verdict = _classify(after)
    assert verdict.classification == UNDECIDABLE
    assert not verdict.preserves_binding, (
        "UNDECIDABLE must never preserve a binding — an unreadable file costs "
        "a binding rather than silently keeping one"
    )
    assert any("globals()" in r for r in verdict.reasons), verdict.reasons


def test_a_string_mentioning_import_module_is_not_a_dynamic_use() -> None:
    """The escape scan is on the AST, never on the text.

    `check_order_path_bans` embeds `importlib.import_module(name)` inside a
    string literal it ships to a subprocess. A text scan would call the whole
    gate undecidable forever, which is doctrine B.4's forbidden direction —
    a gate broken rather than strict.
    """
    after = _plant("_LIMIT = 3", '_LIMIT = 3\n_SNIPPET = "importlib.import_module(x)"')
    verdict = _classify(after)
    assert verdict.classification != UNDECIDABLE, verdict.reasons
    assert any("_SNIPPET was added" in r for r in verdict.reasons), verdict.reasons


def test_a_file_that_does_not_parse_is_undecidable() -> None:
    """An unreadable revision proves nothing, so it certifies nothing."""
    verdict = _classify(BASE + "\ndef broken(:\n")
    assert verdict.classification == UNDECIDABLE
    assert any("does not parse" in r for r in verdict.reasons), verdict.reasons


def test_a_new_check_has_no_binding_to_preserve() -> None:
    """A check that did not exist before cannot have kept a can-fail."""
    verdict = classify_source("check_synthetic", None, BASE)
    assert verdict.classification == MEASUREMENT_PATH
    assert any("the check is new" in r for r in verdict.reasons), verdict.reasons


def test_changed_files_without_a_repo_root_refuses_to_certify() -> None:
    """The cross-file arm cannot run, so the verdict may not be a certification."""
    after = _plant("_LIMIT = 3", "_LIMIT = 3  # comment")
    verdict = _classify(after, changed_files=["scripts/nixverify/contract.py"])
    assert verdict.classification == MEASUREMENT_PATH
    assert any("could not run" in r for r in verdict.reasons), verdict.reasons


# ===========================================================================
# CONDITION 4 — the edit that is not in this file at all.
# ===========================================================================


def test_a_changed_shared_helper_costs_the_binding(tmp_path: Path) -> None:
    """The plant is in `nixverify/`, and the check's own file is byte-identical.

    Built under `tmp_path` as a miniature repo: doctrine C.8 forbids planting
    into the real `scripts/nixverify/`, and this arm's whole subject is a file
    outside the check.
    """
    pkg = tmp_path / "scripts" / "nixverify"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "contract.py").write_text("VALUE = 1\n", encoding="utf-8")
    source = BASE.replace(
        "import json", "import json\nfrom nixverify.contract import VALUE"
    )
    unchanged = classify_source(
        "check_synthetic", source, source, changed_files=[], repo=tmp_path
    )
    assert unchanged.classification == DECLARATION_ONLY, unchanged.reasons

    verdict = classify_source(
        "check_synthetic",
        source,
        source,
        changed_files=["scripts/nixverify/contract.py"],
        repo=tmp_path,
    )
    assert verdict.classification == MEASUREMENT_PATH
    assert any(
        "scripts/nixverify/contract.py is imported" in r for r in verdict.reasons
    ), verdict.reasons


# ===========================================================================
# THE REAL SUBJECT — ARC 025's own diff, from immutable history.
# ===========================================================================

ARC024 = "45a37fa"
ARC025 = "0f9c5b9"


def _git_env() -> dict[str, str]:
    """D3.22: git honours GIT_DIR / GIT_INDEX_FILE AHEAD of -C, and pre-commit
    exports GIT_INDEX_FILE. Without this strip, this suite reads a different
    repository than the one it names and reports a confident verdict about it.

    ARC 036: this was a PRIVATE re-spelling of `nixverify.gitenv.scrubbed_env`
    — the fifth on the tree — and `gitenv.py`'s own docstring says why that is
    the `avg_price` shape: three spellings of one rule had already diverged by
    three variables and nothing said which was right. `check_git_env_scrub`
    found it by deriving the call sites instead of remembering them.
    """
    return scrubbed_env()


def _show(rev: str, rel: str) -> str:
    proc = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, repo history
        ["git", "show", f"{rev}:{rel}"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if proc.returncode != 0:
        pytest.fail(f"{rev}:{rel} is not in this repository's history: {proc.stderr}")
    return proc.stdout


def test_arc025_check_venv_is_declaration_only_within_its_own_file() -> None:
    """Half one of the verdict-by-verdict pair, and it is the honest half.

    ARC 025's retrofit of `check_venv` really was declaration-only *in that
    file*: `DEPENDS_ON` and `ON_FAIL` were added and nothing else moved. A
    classifier that could not see this would be reddening everything.
    """
    verdict = classify_source(
        "check_venv",
        _show(ARC024, "checks/check_venv.py"),
        _show(ARC025, "checks/check_venv.py"),
        changed_files=["checks/check_venv.py"],
        repo=REPO,
    )
    assert verdict.classification == DECLARATION_ONLY, verdict.reasons
    assert set(verdict.declarations_changed) == {"DEPENDS_ON", "ON_FAIL"}


def test_arc025_check_venv_flips_when_the_shared_contract_moves() -> None:
    """Half two, and it is ARC 025's ten declaration-only rulings falling over.

    `scripts/nixverify/contract.py` changed in the same arc, and the function
    that changed is `validate_result` — the post-processor every check's verdict
    passes through. Nothing in `check_venv.py` moved; its measurement did.
    """
    verdict = classify_source(
        "check_venv",
        _show(ARC024, "checks/check_venv.py"),
        _show(ARC025, "checks/check_venv.py"),
        changed_files=["checks/check_venv.py", "scripts/nixverify/contract.py"],
        repo=REPO,
    )
    assert verdict.classification == MEASUREMENT_PATH
    assert any(
        "scripts/nixverify/contract.py is imported" in r for r in verdict.reasons
    ), verdict.reasons


def test_arc025_declared_no_check_declaration_only_once_the_arm_is_applied() -> None:
    """The census: 0 of 15, against the 10 the ruling was taken on.

    Asserted as a per-check statement rather than as a bare count, so a future
    arc reading this knows WHICH ruling it is inheriting.
    """
    changed = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
        ["git", "diff", "--name-only", ARC024, ARC025],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=True,
        env=_git_env(),
    ).stdout.split()
    assert "scripts/nixverify/contract.py" in changed, (
        "the shared verdict post-processor did not change in ARC 025 — this "
        "finding's premise is gone and the ruling must be re-derived"
    )
    listed = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
        ["git", "ls-tree", "-r", "--name-only", ARC025],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=True,
        env=_git_env(),
    ).stdout.splitlines()
    names = [f for f in listed if f.startswith("checks/check_") and f.endswith(".py")]
    assert len(names) == 15, f"expected ARC 025's fifteen checks, got {len(names)}"
    preserved = [
        rel
        for rel in names
        if classify_source(
            Path(rel).stem,
            _show(ARC024, rel) if rel in _show_ok(ARC024) else None,
            _show(ARC025, rel),
            changed_files=changed,
            repo=REPO,
        ).preserves_binding
    ]
    assert preserved == [], (
        f"{preserved} would keep an ARC 025 binding; the measured answer when "
        "this was written is that none of the fifteen does"
    )


def _show_ok(rev: str) -> list[str]:
    return subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
        ["git", "ls-tree", "-r", "--name-only", rev],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=True,
        env=_git_env(),
    ).stdout.splitlines()
