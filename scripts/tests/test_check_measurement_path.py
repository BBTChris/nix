"""ARC 031 / 0.3 — the can-fail suite for `checks/check_measurement_path.py`.

CHECK-DEBT D3.120's discharge route (a). Structure follows the
`check_flatten` / `check_coldstart` precedent: non-vacuity FIRST (the real
tree passes), then plants that must FAIL and NAME their site, then the plant
removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8). Every control
builds a throwaway `nix_home` under `tmp_path` holding a COPY of
`scripts/nixverify/measurement_path.py`, perturbs the COPY, and drives the
SHIPPED gate's own bytes against it. The real
`scripts/nixverify/measurement_path.py` is read and never written here.

WHY THE PLANTS ARE SABOTAGES OF THE CLASSIFIER, not of a check. The subject
is an instrument, so its failure mode is *giving the wrong answer*, and the
dangerous wrong answer is `DECLARATION_ONLY` — the verdict that PRESERVES a
can-fail binding. Each plant below removes one of the subject's own §7.12
closures and the gate must go red naming the arm that noticed.

Every control asserts the REASON — the site and the named condition — never
the exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_measurement_path as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.gitenv import scrubbed_env  # pylint: disable=wrong-import-position

SUBJECT = gate.SUBJECT_FILE


def _git(cwd: Path, *args: str) -> None:
    """One git command in the throwaway tree, scrubbed environment (D3.22)."""
    subprocess.run(  # nosec B603 - fixed absolute path, shell=False, tmp tree
        ["/usr/bin/git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        timeout=60,
        env=scrubbed_env(),
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying a COPY of the classifier.

    It is a REAL git repository with one commit, because the gate's
    empty-range arm drives `changed_paths(home, "HEAD", "HEAD")` against it.
    A non-git tree makes that arm CANNOT_MEASURE — which the gate reports
    honestly and which this suite proves separately below — but it would
    also stop every plant here from exercising the arm at all.
    """
    target = tmp_path / SUBJECT
    target.parent.mkdir(parents=True)
    shutil.copy(REPO / SUBJECT, target)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(
        tmp_path,
        "-c",
        "user.email=test@nix.local",
        "-c",
        "user.name=nix-test",
        "commit",
        "-q",
        "-m",
        "planted subject",
    )
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    """Rewrite the COPIED classifier. Fails loudly if the anchor moved."""
    path = home / SUBJECT
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"anchor appears {text.count(old)} times, not once — the plant would "
        "measure something other than what it names"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _red(result, *, site_contains: str, why_contains: str) -> None:
    """One red verdict, asserted by REASON and SITE, never by status alone."""
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL_NEEDS_OPERATOR, got {result.status!r}: {result.detail}"
    )
    assert site_contains in (result.site or ""), (
        f"site {result.site!r} does not name {site_contains!r}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the real tree, and the real gate, both directions
# --------------------------------------------------------------------------


def test_the_REAL_repository_passes_and_the_copy_passes_identically(
    home: Path,
) -> None:
    """A gate that cannot pass on a clean subject measures nothing on a dirty one."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
    assert SUBJECT in (live.evidence or ""), live.evidence
    copied = _run(home)
    assert copied.status is Status.PASS, copied.detail


def test_the_gate_DECLARES_the_artifact_the_coverage_ratchet_counts() -> None:
    """D3.120 is discharged by COVERAGE, and coverage is what SUBJECTS names.

    `check_artifact_gate_coverage` can see exactly one thing — whether a
    check declares the path — so a gate that drove the classifier perfectly
    while naming nothing would leave the ledger row exactly where it was.
    """
    assert SUBJECT in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, (
        "a gate that could 'repair' the rule it is measured against is the "
        "instrument rewriting its own subject"
    )


def test_a_MISSING_subject_is_cannot_measure_and_never_a_PASS(tmp_path: Path) -> None:
    """§17: a safety property proven while its subject is unavailable is not proven."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert SUBJECT in (result.detail or ""), result.detail


def test_an_UNPARSEABLE_subject_is_cannot_measure(home: Path) -> None:
    """An import failure names the exception rather than reading as clean."""
    (home / SUBJECT).write_text("def classify_source(  :::\n", encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "SyntaxError" in (result.detail or ""), result.detail


def test_the_gate_loads_the_subject_BY_PATH_not_by_sys_path_name(home: Path) -> None:
    """§7.12/2 — `_preamble` appends the REAL scripts/ to `sys.path` forever.

    `check_d1_12_reboot_capture`'s first draft shipped exactly this defect:
    a name-based import silently resolved against the live repository while
    the gate believed it was measuring the tree it was handed. Proven by
    planting a sabotage in the COPY only: if the gate resolved by name it
    would load the pristine real file and report PASS.
    """
    _plant(
        home,
        '    if "run" in module.bindings:\n        frontier.add("run")\n',
        '    if "run" in module.bindings:\n        frontier.add("run")\n'
        "    frontier -= {'_probe_main'}\n",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        "the gate passed on a sabotaged COPY — it is reading the real tree, "
        f"not the tree it was given: {result.detail}"
    )
    module, error = gate.load(home)
    assert module is not None, error
    assert Path(module.__file__ or "").resolve() == (home / SUBJECT).resolve()


# --------------------------------------------------------------------------
# PLANTS — one per §7.12 closure the subject claims
# --------------------------------------------------------------------------


def test_a_closure_rooted_at_run_ALONE_reddens_the_main_block_arm(
    home: Path,
) -> None:
    """Condition 1, the defect the naive implementation has.

    Rooting only at `run` calls an edit to any of `check_derived_claims`'
    twenty-one probes declaration-only, and every number that gate compares
    would have moved.
    """
    _plant(
        home,
        "    frontier: set[str] = set()\n"
        "    for dumped in module.other_nodes:\n"
        "        frontier |= _referenced(dumped)\n",
        "    frontier: set[str] = set()\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="measurement_closure[__main__ root]",
        why_contains="declaration-only",
    )
    assert "preserves_binding=True" in (result.detail or ""), (
        "the finding must say the wrong verdict PRESERVED a binding — that "
        f"is the whole hazard: {result.detail}"
    )
    assert "twenty-one-probe hazard" in (result.detail or ""), (
        "the closure-membership sub-arm must fire too — `_probe` is reachable "
        f"ONLY as __main__ -> _probe_main -> _probe: {result.detail}"
    )
    assert "falsifier" not in (result.detail or ""), (
        "the falsifier sub-arm must stay quiet here: it fires only when a "
        "run()-rooted closure STILL contains the planted symbol, which would "
        f"mean the plant probes nothing: {result.detail}"
    )


def test_a_classifier_that_ignores_a_changed_CONSTANT_reddens(home: Path) -> None:
    """Condition 2 — `_TIMEOUT = 300 -> 5` is not a function, and it still moves."""
    _plant(
        home,
        "        if same:\n            continue\n",
        "        if same or isinstance(new, ast.Assign):\n            continue\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_compare_bindings[constant]",
        why_contains="a module-level CONSTANT that run() reads changed",
    )


def test_a_classifier_that_excuses_EVERY_declaration_reddens_the_aliasing_trap(
    home: Path,
) -> None:
    """Condition 3 — a declaration `run()` READS is part of the measurement."""
    _plant(
        home,
        "        if name in closure:\n",
        "        if name in DECLARATION_SYMBOLS:\n"
        "            declarations.append(name)\n"
        "        elif name in closure:\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_compare_bindings[aliasing trap]",
        why_contains="run() READS its own RESOURCES",
    )


def test_a_classifier_blind_to_a_CROSS_FILE_edit_reddens(home: Path) -> None:
    """Condition 4 — nothing in the check moved and its measurement moved completely."""
    _plant(
        home,
        "    imported = resolve_imports(repo, after) | resolve_imports(repo, before)\n",
        "    imported = frozenset()\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_cross_file_reasons",
        why_contains="a transitively-imported first-party module changed",
    )


def test_a_classifier_that_certifies_WITHOUT_a_repo_root_reddens(home: Path) -> None:
    """The other half of condition 4: an arm that could not run is not a clean arm."""
    _plant(
        home,
        "    elif changed_files:\n        reasons.append(\n"
        '            "changed_files was supplied without a repo root, so the "\n',
        "    elif False:\n        reasons.append(\n"
        '            "changed_files was supplied without a repo root, so the "\n',
    )
    result = _run(home)
    _red(
        result,
        site_contains="_cross_file_reasons:no-repo",
        why_contains="must REFUSE to certify",
    )


def test_a_classifier_blind_to_DYNAMIC_namespace_access_reddens(home: Path) -> None:
    """Condition 7 — under `globals()` a static name graph proves nothing."""
    _plant(
        home,
        "    found: list[str] = []\n    for node in ast.walk(tree):\n",
        "    found: list[str] = []\n    for node in []:\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_dynamic_uses",
        why_contains="globals() makes a static name graph unsound",
    )


def test_a_classifier_that_matches_dynamic_access_BY_TEXT_reddens(
    home: Path,
) -> None:
    """The discriminator, in the direction that costs bindings for nothing.

    `check_order_path_bans` embeds the literal string
    `importlib.import_module` in a probe it ships to a subprocess. A text
    match would call every edit to that file undecidable forever.
    """
    _plant(
        home,
        "def _dynamic_uses(tree: ast.Module) -> tuple[str, ...]:\n",
        "def _dynamic_uses(tree: ast.Module) -> tuple[str, ...]:\n"
        "    if 'import_module' in ast.unparse(tree):\n"
        "        return ('text match',)\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_dynamic_uses[string literal]",
        why_contains="is not a call",
    )


def test_a_classifier_with_a_probably_harmless_category_reddens(home: Path) -> None:
    """Condition 8 — unclassified module-level state fails CLOSED, or not at all."""
    _plant(
        home,
        "        else:\n            reasons.append(\n"
        '                f"{name} was {where}; it is neither a declaration '
        'symbol nor on "\n',
        "        elif False:\n            reasons.append(\n"
        '                f"{name} was {where}; it is neither a declaration '
        'symbol nor on "\n',
    )
    result = _run(home)
    _red(
        result,
        site_contains="_compare_bindings[fail-closed]",
        why_contains="there is no 'probably harmless'",
    )


def test_a_NEW_check_that_KEEPS_a_binding_reddens(home: Path) -> None:
    """Condition 9 — a check that did not exist has no binding to preserve."""
    _plant(
        home,
        "            name,\n            MEASUREMENT_PATH,\n"
        '            ("the check is new — a check that did not exist has no binding",),\n',
        "            name,\n            DECLARATION_ONLY,\n"
        '            ("the check is new — a check that did not exist has no binding",),\n',
    )
    result = _run(home)
    _red(
        result,
        site_contains="classify_source[new/deleted]",
        why_contains="a check that did not exist has no binding to preserve",
    )


def test_a_DELETED_check_that_keeps_a_binding_reddens(home: Path) -> None:
    """The other half of condition 9, planted separately so neither hides the other."""
    _plant(
        home,
        'return Classification(name, MEASUREMENT_PATH, ("the check was deleted",))',
        'return Classification(name, DECLARATION_ONLY, ("the check was deleted",))',
    )
    result = _run(home)
    _red(
        result,
        site_contains="classify_source[new/deleted]",
        why_contains="a deleted check keeps no binding",
    )


def test_an_EMPTY_RANGE_that_does_not_refuse_reddens(home: Path) -> None:
    """§0a, the audit half: a range that changed no files classifies every
    check as declaration-only, in silence, and looks exactly like an arc that
    genuinely touched no measurement path."""
    _plant(
        home,
        "    if not out:\n        raise RangeError(\n",
        "    if not out:\n        return ()\n    if False:\n        raise RangeError(\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="changed_paths[empty range]",
        why_contains="in silence",
    )


# --------------------------------------------------------------------------
# RESTORE — the plant removed, the same tree green again
# --------------------------------------------------------------------------


def test_the_plant_REMOVED_returns_the_same_tree_to_green(home: Path) -> None:
    """A red that does not clear on repair is a broken gate, not a finding."""
    original = (home / SUBJECT).read_text(encoding="utf-8")
    _plant(
        home,
        "    frontier: set[str] = set()\n"
        "    for dumped in module.other_nodes:\n"
        "        frontier |= _referenced(dumped)\n",
        "    frontier: set[str] = set()\n",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / SUBJECT).write_text(original, encoding="utf-8")
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail
    assert (home / SUBJECT).read_bytes() == (REPO / SUBJECT).read_bytes(), (
        "the restored copy is not byte-identical to the shipped subject"
    )


def test_a_NON_GIT_home_makes_the_empty_range_arm_CANNOT_MEASURE(
    tmp_path: Path,
) -> None:
    """§0a, found by driving rather than by reading — and it was a real defect.

    `changed_paths` raises the SAME `RangeError` for "git could not answer"
    as for "this range changed no files", so the arm's first draft — a bare
    `except RangeError: pass` — passed vacuously against every tree that is
    not a git repository. The gate now requires the refusal to NAME the empty
    range and reports CANNOT_MEASURE otherwise, never a green.
    """
    target = tmp_path / SUBJECT
    target.parent.mkdir(parents=True)
    shutil.copy(REPO / SUBJECT, target)
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "changed_paths[empty range]" in (result.detail or ""), result.detail
    assert "refused for a different reason" in (result.detail or ""), result.detail
