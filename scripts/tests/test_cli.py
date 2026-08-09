"""CLI wiring and the stdlib-only / no-stdin invariants (§9)."""

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest  # pylint: disable=import-error
import verify

REPO = Path(__file__).resolve().parents[2]

PASSING = (
    "def run(mode, ctx):\n"
    "    from nixverify.contract import CheckResult, Status\n"
    "    return CheckResult(name='x', status=Status.PASS, evidence='measured')\n"
)


def _fixture(tmp_path: Path, body: str) -> Path:
    """Write a one-check manifest fixture and return its path."""
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "check_one.py").write_text(body, encoding="utf-8")
    manifest = checks / "verify_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "1.0.0",
                "blocks": [{"name": "b", "checks": ["check_one"]}],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_all_passing_exits_zero(tmp_path: Path) -> None:
    """A manifest of only passing checks exits 0."""
    manifest = _fixture(tmp_path, PASSING)
    assert verify.main(["--manifest", str(manifest)]) == 0


def test_missing_manifest_exits_two_not_one(tmp_path: Path) -> None:
    """A manifest we cannot read is unmeasurable, not a failed check."""
    assert verify.main(["--manifest", str(tmp_path / "absent.json")]) == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_permission_denied_manifest_exits_two_not_a_traceback(tmp_path: Path) -> None:
    """A manifest that exists but cannot be read must not crash the CLI (exit 2)."""
    manifest = _fixture(tmp_path, PASSING)
    manifest.chmod(0o000)
    try:
        assert verify.main(["--manifest", str(manifest)]) == 2
    finally:
        manifest.chmod(0o644)


def test_engine_runs_under_system_python_without_the_venv(tmp_path: Path) -> None:
    """§9.1: the engine must work before .venv exists."""
    manifest = _fixture(tmp_path, PASSING)
    proc = subprocess.run(
        [
            "/usr/bin/python3",
            str(REPO / "scripts" / "verify.py"),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_engine_imports_no_third_party_modules() -> None:
    """§9.1 enforced, not merely documented.

    Proves no module loaded as a side effect of importing the engine
    resolves inside site-packages — i.e. nothing third-party got pulled in.
    """
    script = textwrap.dedent(
        """
        import sys

        sys.path.insert(0, "scripts")
        import verify  # noqa: F401
        import nixverify.engine  # noqa: F401
        import nixverify.render  # noqa: F401

        mods = [
            m for m in sys.modules if not m.startswith(("_", "nixverify", "verify"))
        ]
        bad = [
            m
            for m in mods
            if getattr(sys.modules[m], "__file__", None)
            and "site-packages" in sys.modules[m].__file__
        ]
        print(bad)
        raise SystemExit(1 if bad else 0)
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"third-party imports in engine: {proc.stdout}"


def _sys_aliases(tree: ast.Module) -> set[str]:
    """Every name `sys` is reachable under, including `import sys as X`."""
    aliases = {"sys"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update(
                alias.asname
                for alias in node.names
                if alias.name == "sys" and alias.asname
            )
    return aliases


def _imports_stdin_directly(tree: ast.Module) -> bool:
    """True for `from sys import stdin`, which needs no `sys.` prefix at all."""
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "sys"
        and any(alias.name == "stdin" for alias in node.names)
        for node in ast.walk(tree)
    )


def _calls_input(node: ast.AST) -> bool:
    """True if `node` is a call to the bare builtin `input`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "input"
    )


def _accesses_stdin(node: ast.AST, sys_aliases: set[str]) -> bool:
    """True if `node` is `<sys-alias>.stdin`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "stdin"
        and isinstance(node.value, ast.Name)
        and node.value.id in sys_aliases
    )


def _reads_stdin(path: Path) -> bool:
    """True if `path` contains a real `input()` call or `sys.stdin` access.

    Parses with `ast` rather than substring-matching so prose mentioning
    "stdin" in a docstring or comment cannot trip the check — only actual
    code usage counts. Also resolves `import sys as <alias>` bindings (so
    `alias.stdin` is caught, not just the literal name `sys`) and treats
    `from sys import stdin` as a direct hit, since that form makes `stdin`
    usable without ever writing `sys.stdin` again.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if _imports_stdin_directly(tree):
        return True
    sys_aliases = _sys_aliases(tree)
    return any(
        _calls_input(node) or _accesses_stdin(node, sys_aliases)
        for node in ast.walk(tree)
    )


def test_engine_source_never_reads_stdin() -> None:
    """§9.2: one input() would hang a boot unit indefinitely.

    Uses AST inspection rather than a text substring check, so a docstring
    that documents the invariant (e.g. "Never reads stdin") does not itself
    trip the assertion it is describing.
    """
    for path in (
        REPO / "scripts" / "verify.py",
        *(REPO / "scripts" / "nixverify").glob("*.py"),
    ):
        assert not _reads_stdin(path), f"{path} reads stdin"


def test_reads_stdin_ignores_docstring_prose(tmp_path: Path) -> None:
    """A docstring that merely mentions "stdin" is not code usage."""
    path = tmp_path / "mod.py"
    path.write_text('"""Never reads stdin (§9.2)."""\n', encoding="utf-8")
    assert not _reads_stdin(path)


def test_reads_stdin_ignores_unrelated_name(tmp_path: Path) -> None:
    """A variable merely named `stdin` is not `sys.stdin`."""
    path = tmp_path / "mod.py"
    path.write_text("stdin = 1\nprint(stdin)\n", encoding="utf-8")
    assert not _reads_stdin(path)


def test_reads_stdin_catches_bare_input_call(tmp_path: Path) -> None:
    """A direct `input()` call is the exact hazard this check exists for."""
    path = tmp_path / "mod.py"
    path.write_text("x = input()\n", encoding="utf-8")
    assert _reads_stdin(path)


def test_reads_stdin_catches_sys_stdin_attribute(tmp_path: Path) -> None:
    """`sys.stdin.read()` is the other direct hazard."""
    path = tmp_path / "mod.py"
    path.write_text("import sys\nx = sys.stdin.read()\n", encoding="utf-8")
    assert _reads_stdin(path)


def test_reads_stdin_catches_aliased_sys_import(tmp_path: Path) -> None:
    """`import sys as s` must not let `s.stdin` evade the check."""
    path = tmp_path / "mod.py"
    path.write_text("import sys as s\nx = s.stdin.read()\n", encoding="utf-8")
    assert _reads_stdin(path)


def test_reads_stdin_catches_from_sys_import_stdin(tmp_path: Path) -> None:
    """`from sys import stdin` must not let a direct-import form evade the check."""
    path = tmp_path / "mod.py"
    path.write_text("from sys import stdin\nx = stdin.read()\n", encoding="utf-8")
    assert _reads_stdin(path)


def test_old_root_verify_is_gone() -> None:
    """§13: scripts/ is the canonical home per directory_structure.md."""
    assert not (REPO / "verify.py").exists()
