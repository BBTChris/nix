"""`check_name_coherence` — one artifact, one name (ARC 026 B1).

The gate's subject is the *identifier* vocabulary for the master execution plan.
ARC 010 renamed `verify_manifest.json` to `registry.json` and left the module,
exception, loader, CLI flag and the file's own version key spelling it
`manifest`. Two names for one thing, one layer apart.

WHAT THIS SUITE IS CAREFUL ABOUT
--------------------------------
* **Non-vacuity BEFORE any plant** (doctrine C.3). The gate is asserted to have
  the real tree in scope and to contain its witnesses before a defect is ever
  introduced. A rule that cannot see the file it was written about would pass
  forever, and this project has measured that happening.
* **Both halves of the can-fail** (doctrine C.2). Plant the exact defect and
  require the gate to FAIL *naming the site and the token*; remove it and
  require PASS. Neither half alone distinguishes *detects the defect* from
  *always fails*.
* **The reason, never the exit code** (check contract §11). Every negative
  assertion below is on the site string or the detail text.
* **No plant touches a production artefact** (doctrine C.8). Every plant lands
  in a throwaway repository under `tmp_path`, built with a scrubbed git
  environment so the fixture cannot reach the real tree (D3.22).
"""

# pylint: disable=invalid-name,duplicate-code,import-outside-toplevel
# Test names SHOUT the property under test, as the rest of this suite does.
# `duplicate-code`: the sys.path bootstrap and the SCRUBBED fixture-git helper
# are repeated per module DELIBERATELY. Factoring them into a shared conftest
# would hide the D3.22 scrub from the reader of each module, and a scrub nobody
# sees at the call site is how three private spellings of it drifted apart in
# the first place. Late imports are the sys.path bootstrap this suite needs.
from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, shell=False, tmp_path only
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
SCRIPTS = REPO / "scripts"
for _extra in (str(CHECKS), str(SCRIPTS)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_name_coherence as gate  # pylint: disable=import-error
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
    validate_result,
)
from nixverify.gitenv import scrubbed_env  # pylint: disable=import-error

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(cwd: Path, *args: str) -> None:
    """Fixture git, scrubbed (D3.22) so it cannot reach the real repository."""
    subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp_path only
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=scrubbed_env(extra=_IDENTITY),
    )


@pytest.fixture(name="tree")
def _tree(tmp_path: Path) -> Path:
    """A throwaway repository shaped enough for the gate to report on it.

    It carries the two witness paths, a clean `scripts/nixverify/registry.py`,
    and enough filler to clear `MIN_CREDIBLE_FILES` — the filler exists because
    the credibility floor is a real arm of the gate and a fixture below it would
    only ever exercise the CANNOT_MEASURE path.
    """
    root = tmp_path / "tree"
    (root / "scripts" / "nixverify").mkdir(parents=True)
    (root / "checks").mkdir()
    (root / "scripts" / "verify.py").write_text(
        "from nixverify.registry import RegistryError, load_registry\n",
        encoding="utf-8",
    )
    (root / "checks" / "registry.json").write_text(
        '{"registry_version": "1.0.0", "blocks": []}\n', encoding="utf-8"
    )
    (root / "scripts" / "nixverify" / "registry.py").write_text(
        "def load_registry(path):\n    return ()\n", encoding="utf-8"
    )
    for index in range(gate.MIN_CREDIBLE_FILES):
        (root / f"filler_{index}.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _run(tree: Path):
    """Drive the shipped entry point, through the engine's own validation."""
    return validate_result(
        gate.run(Mode.VERIFY, Context(nix_home=tree, mode=Mode.VERIFY))
    )


# --- non-vacuity, before any plant ----------------------------------------


def test_NON_VACUITY_the_real_tree_is_in_scope_and_holds_the_witnesses() -> None:
    """The gate's scope must contain the files that carried the vocabulary.

    Asserted against the REAL repository, not the fixture: a fixture proves the
    logic works on a tree the test built, and this project has measured a rule
    whose scope made it structurally unable to see the file it was written about
    (doctrine C.3). The assertion is on membership — an invariant — never on a
    count, which would be an anchor that moves (failure mode #4).
    """
    paths, error = gate.tracked_files(REPO)
    assert not error, error
    missing = [w for w in gate.WITNESS_PATHS if w not in paths]
    assert not missing, f"the gate cannot see {missing} — its scope lost its subject"
    assert len(paths) >= gate.MIN_CREDIBLE_FILES, len(paths)


def test_NON_VACUITY_the_banned_list_is_not_empty() -> None:
    """An empty ban list would clear every file having tested it against nothing."""
    assert gate.BANNED, "BANNED is empty — §7.12 answer 2"


def test_every_banned_spelling_has_a_case(request: pytest.FixtureRequest) -> None:
    """The can-fail's literal parameter list must equal the gate's rule.

    The parametrised control below spells its tokens as a LITERAL so the AST
    test-counter can read it. That literal is a restatement, and an unchecked
    restatement is the defect this project has recorded ten times — so it is
    checked: the parameters pytest actually collected are compared against
    `gate.BANNED`, and a spelling added to the gate without a demonstration
    fails HERE, naming the token, instead of shipping undemonstrated.
    """
    collected = {
        item.callspec.params["token"]
        for item in request.session.items
        if item.originalname
        == "test_CAN_FAIL_each_banned_spelling_is_caught_and_the_site_is_named"
    }
    assert collected == set(gate.BANNED), (
        f"the control's parameters {sorted(collected)} do not match the gate's "
        f"BANNED {sorted(gate.BANNED)} — a banned spelling with no plant is a "
        "rule nobody has shown able to fire"
    )


def test_the_real_tree_is_clean_of_manifest_as_identifier() -> None:
    """The live verdict: ARC 026 B1's purge holds on the tree that ships."""
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail


# --- the can-fail, one plant per banned spelling --------------------------


# THE LIST IS A LITERAL, AND `test_every_banned_spelling_has_a_case` IS WHY THAT
# IS SAFE. `check_derived_claims` derives `pytest_collected_tests` by AST and
# REFUSES to count a parametrize whose argvalues it cannot evaluate statically —
# `gate.BANNED` here turned that claim into CANNOT_MEASURE, measured in ARC 026
# on this file. A literal restores the count; the equality assertion below is
# what stops the literal drifting from the rule, so a spelling added to the gate
# without a demonstration is a RED naming the missing token rather than a silent
# gap. Doctrine B.7 applied to a test's own parameters.
@pytest.mark.parametrize(
    "token",
    [
        "manifest_version",
        "ManifestError",
        "load_manifest",
        "--manifest",
        "nixverify/manifest.py",
        "nixverify.manifest",
        "<manifest>",
    ],
)
def test_CAN_FAIL_each_banned_spelling_is_caught_and_the_site_is_named(
    tree: Path, token: str
) -> None:
    """Plant the exact defect; the gate must FAIL and name file, line and token.

    Parametrised over `BANNED` rather than over a hand-written list, so a
    spelling added to the gate without a demonstration is impossible: the suite
    grows a case by the gate growing a rule. Nothing here asserts an exit code —
    the assertions are the SITE and the TOKEN, which is what tells a reader the
    gate found the thing rather than merely disliking the tree.
    """
    planted = tree / "scripts" / "nixverify" / "consumer.py"
    planted.write_text(f"# a live use: {token}\n", encoding="utf-8")
    _git(tree, "add", "-A")

    result = _run(tree)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "scripts/nixverify/consumer.py:1" in result.site, result.site
    assert token in result.detail, result.detail
    assert "one name and it is `registry`" in result.detail, result.detail

    # --- the other half: remove the plant, the gate must go green again ---
    planted.unlink()
    _git(tree, "add", "-A")
    restored = _run(tree)
    assert restored.status is Status.PASS, restored.detail


def test_a_historical_record_may_keep_the_vocabulary(tree: Path) -> None:
    """The exemption is real and is scoped to records that must not be rewritten.

    `CLAUDE.md` directive 6 forbids rewriting banked evidence, so the amendment
    ledger's account of what the vocabulary used to be has to survive. The
    assertion pairs with the one below it: the same bytes in a non-exempt path
    are a defect, which is what makes this an exemption rather than a hole.
    """
    docs = tree / "docs"
    docs.mkdir()
    (docs / "CHECK-CONTRACT-AMENDMENTS.md").write_text(
        "ARC 025 left `load_manifest()` and `--manifest` in place.\n", encoding="utf-8"
    )
    _git(tree, "add", "-A")
    assert _run(tree).status is Status.PASS


def test_the_same_bytes_outside_the_exemption_are_a_defect(tree: Path) -> None:
    """CONTROL for the test above — otherwise it proves only that the gate is quiet."""
    docs = tree / "docs"
    docs.mkdir()
    (docs / "some_other_note.md").write_text(
        "ARC 025 left `load_manifest()` and `--manifest` in place.\n", encoding="utf-8"
    )
    _git(tree, "add", "-A")
    result = _run(tree)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "docs/some_other_note.md:1" in result.site, result.site


# --- the vacuous-pass closures, each asserted rather than described -------


def test_an_uncredible_population_is_CANNOT_MEASURE_not_PASS(tmp_path: Path) -> None:
    """§7.12 answer 1. A tiny tree makes every file trivially clean."""
    root = tmp_path / "tiny"
    root.mkdir()
    (root / "one.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    result = _run(root)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "credibility floor" in result.detail, result.detail


def test_a_scope_without_its_witnesses_is_CANNOT_MEASURE(tree: Path) -> None:
    """§7.12 answer 1, second half: scope present but subject gone.

    The plant is the removal of `scripts/verify.py` — a scope that no longer
    contains the file the vocabulary lived in cannot demonstrate it is still
    looking where the defect was, and the honest verdict is 'unknown'.
    """
    (tree / "scripts" / "verify.py").unlink()
    _git(tree, "add", "-A")
    result = _run(tree)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "scripts/verify.py" in result.detail, result.detail


def test_git_absent_or_failing_is_CANNOT_MEASURE_not_PASS(tmp_path: Path) -> None:
    """A directory that is not a repository at all: unmeasurable, never clean."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result.detail


def test_the_declarations_are_readable_statically() -> None:
    """§4.4 — the plan reads DEPENDS_ON/RESOURCES by AST, never by importing."""
    from nixverify.declarations import (
        read_all,  # pylint: disable=import-outside-toplevel
    )

    declared = read_all(CHECKS)[gate.NAME]
    assert declared.resources == ("subprocess:git",), declared.resources
    assert declared.depends_on == (), declared.depends_on
    assert not declared.correctable
