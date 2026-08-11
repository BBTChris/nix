"""ARC 024 §3.3 — the declaration mechanism, and the failure mode of the one not chosen.

§3.3 required that both candidate mechanisms be measured against the real check
population, that one be picked, and that **the failure mode of the one not
chosen be demonstrated**. The measurement lives in
`scripts/nixverify/declarations.py`'s docstring; the demonstration lives here,
in `test_import_to_read_executes_module_level_code`, because a failure mode
asserted in prose is a failure mode nobody has seen.
"""
# pylint: disable=invalid-name,import-outside-toplevel,use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test on purpose; `== ()` is asserted
# rather than `not x` because an empty tuple and a falsey non-tuple are
# different outcomes here; late imports are the sys.path bootstrap this suite
# needs. Each is deliberate, so the pragma is per-file and named.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixverify.declarations import (  # pylint: disable=wrong-import-position
    Declaration,
    read_all,
    read_declaration,
)

DECLARED = '''\
"""A well-formed check."""
DEPENDS_ON = ("check_a",)
RESOURCES = ("journal", "port:4002")
TIME_BOUND = True
EXPECTED_S = 8.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = "order path"
'''


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_reads_every_declaration_from_a_literal_module(tmp_path: Path) -> None:
    """The happy path: all six symbols recovered without importing anything."""
    decl = read_declaration(_write(tmp_path, "check_ok", DECLARED))
    assert decl.depends_on == ("check_a",)
    assert decl.resources == ("journal", "port:4002")
    assert decl.time_bound is True
    assert decl.expected_s == 8.0
    assert decl.correctable is False
    assert decl.non_correctable_reason == "order path"
    assert decl.errors == ()


def test_a_non_literal_declaration_is_a_LOUD_error_not_a_silent_default(
    tmp_path: Path,
) -> None:
    """§3.3's central requirement.

    A computed declaration cannot be read without executing the module. The one
    thing that must NOT happen is for it to be read as "no dependencies" — that
    is how a check lands in a parallel block it does not belong in. It must
    surface as an error naming the file and the symbol.
    """
    body = "_BASE = ('a',)\nDEPENDS_ON = _BASE + ('b',)\nRESOURCES = ()\n"
    decl = read_declaration(_write(tmp_path, "check_computed", body))
    assert decl.depends_on == ()  # nothing was recovered...
    assert decl.errors, "a non-literal declaration must produce an error"
    assert any("DEPENDS_ON" in err for err in decl.errors)
    assert any("not a literal" in err for err in decl.errors)


def test_declaring_nothing_is_distinguishable_from_declaring_empty(
    tmp_path: Path,
) -> None:
    """`RESOURCES = ()` is a claim; a missing RESOURCES is an absence.

    These must not collapse into each other: the first says "I claim no shared
    resource" and is eligible for a parallel block; the second says nothing at
    all and is not.
    """
    silent = read_declaration(_write(tmp_path, "check_silent", "X = 1\n"))
    empty = read_declaration(_write(tmp_path, "check_empty", "RESOURCES = ()\n"))
    assert silent.declares_resources is False
    assert empty.declares_resources is True
    assert empty.resources == ()


def test_a_refusal_must_name_its_reason(tmp_path: Path) -> None:
    """§2.3: CORRECTABLE=False with no reason is indistinguishable from a stub."""
    body = "DEPENDS_ON = ()\nRESOURCES = ()\nCORRECTABLE = False\n"
    decl = read_declaration(_write(tmp_path, "check_mute", body))
    assert any("NON_CORRECTABLE_REASON" in err for err in decl.errors)


def test_a_file_that_would_not_import_still_yields_its_declaration(
    tmp_path: Path,
) -> None:
    """The reason import-to-read fails closed in the wrong direction.

    This module imports a package that does not exist, so `import` recovers
    nothing at all and a caller would be tempted to default it to "declares
    nothing". Parsing recovers the declaration regardless.
    """
    body = "import a_package_that_does_not_exist\nDEPENDS_ON = ('check_a',)\nRESOURCES = ()\n"
    decl = read_declaration(_write(tmp_path, "check_unimportable", body))
    assert decl.depends_on == ("check_a",)
    assert decl.errors == ()


def test_import_to_read_executes_module_level_code(tmp_path: Path) -> None:
    """DEMONSTRATION of the mechanism NOT chosen (§3.3 requirement).

    The invariant is that `--optimize` reads declarations **without executing
    the check's measurement logic**. This plants a check whose module level has
    an observable side effect — it writes a file — and shows the two mechanisms
    diverge on exactly that property:

    - import-to-read: the side effect HAPPENS.
    - `read_declaration`: it does not.

    No check on today's tree does work at module level, so import would be safe
    today. It is the guarantee for the hundreds of checks not yet written that
    cannot be made by importing them.
    """
    witness = tmp_path / "SIDE_EFFECT_HAPPENED"
    body = (
        "from pathlib import Path\n"
        f"Path({str(witness)!r}).write_text('executed', encoding='utf-8')\n"
        "DEPENDS_ON = ()\n"
        "RESOURCES = ()\n"
    )
    path = _write(tmp_path, "check_side_effect", body)

    # The chosen mechanism: reads the declaration, runs nothing.
    decl = read_declaration(path)
    assert decl.declares_resources is True
    assert not witness.exists(), (
        "read_declaration executed module-level code — the whole point of "
        "choosing AST parse over import-to-read is that this cannot happen"
    )

    # The mechanism not chosen: same file, side effect fires.
    spec = importlib.util.spec_from_file_location("check_side_effect_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert witness.exists(), (
        "the demonstration is vacuous unless import actually triggers the side "
        "effect it is here to demonstrate"
    )
    assert witness.read_text(encoding="utf-8") == "executed"


def test_read_all_derives_scope_from_the_FOLDER(tmp_path: Path) -> None:
    """Scope comes from the folder, never from a registry.

    This is the structural fix for the project's recurring defect class where a
    tracking state silently sets a gate's scope. A registry cannot report an
    orphan, because an orphan is what the registry does not know about.
    """
    _write(tmp_path, "check_one", "DEPENDS_ON = ()\nRESOURCES = ()\n")
    _write(tmp_path, "check_two", "DEPENDS_ON = ()\nRESOURCES = ()\n")
    _write(tmp_path, "not_a_check", "DEPENDS_ON = ()\n")
    found = read_all(tmp_path)
    assert set(found) == {"check_one", "check_two"}


def test_the_real_population_parses_without_executing(tmp_path: Path) -> None:
    """Regression: every registered check must remain statically readable.

    A check that stops parsing here would silently drop out of `--optimize`'s
    view. `tmp_path` is unused; the subject is the real folder.
    """
    del tmp_path
    found = read_all(REPO / "checks")
    assert len(found) >= 13
    for name, decl in found.items():
        assert isinstance(decl, Declaration), name
        # Parse errors are fatal; declaration errors are the tree's real state.
        assert not any("does not parse" in err for err in decl.errors), name


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("DEPENDS_ON = 'check_a'\nRESOURCES = ()\n", "must be a tuple or list"),
        ("DEPENDS_ON = (1, 2)\nRESOURCES = ()\n", "only strings"),
        ("DEPENDS_ON = ()\nRESOURCES = ()\nEXPECTED_S = 'soon'\n", "must be a number"),
    ],
)
def test_malformed_declarations_name_what_is_wrong(
    tmp_path: Path, body: str, fragment: str
) -> None:
    """Every rejection names the symbol and the shape it wanted."""
    decl = read_declaration(_write(tmp_path, "check_bad", body))
    assert any(fragment in err for err in decl.errors), decl.errors
