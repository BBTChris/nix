"""CLI wiring and the stdlib-only / no-stdin invariants (§9)."""

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

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


def _reads_stdin(path: Path) -> bool:
    """True if `path` contains a real `input()` call or `sys.stdin` access.

    Parses with `ast` rather than substring-matching so prose mentioning
    "stdin" in a docstring or comment cannot trip the check — only actual
    code usage counts.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "input":
                return True
        if isinstance(node, ast.Attribute) and node.attr == "stdin":
            value = node.value
            if isinstance(value, ast.Name) and value.id == "sys":
                return True
    return False


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


def test_old_root_verify_is_gone() -> None:
    """§13: scripts/ is the canonical home per directory_structure.md."""
    assert not (REPO / "verify.py").exists()
