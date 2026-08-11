"""§5 non-vacuity, enforced on the standalone `__main__` path too (I2).

All four checks' `__main__` blocks called `exit_code_for(OUTCOME.status)`
directly, skipping `validate_result`. §4.2 blesses standalone execution as a
first-class contract; §5 says the engine rejects a PASS with empty
`evidence`. A planted vacuous PASS exited 0 standalone while the engine
correctly downgraded the identical result to CANNOT_MEASURE.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
CHECK_FILES = sorted(CHECKS.glob("check_*.py"))
SCRIPTS_DIR = REPO / "scripts"


def _vacuous_standalone_script(tmp_path: Path, *, guarded: bool) -> Path:
    """Write a minimal check module using the real __main__ pattern.

    `guarded=True` reproduces the fixed pattern (wrapped in
    `validate_result`); `guarded=False` reproduces the exact prior defect,
    used as the control proving the test can tell the difference.
    """
    name = "check_vacuous_guarded" if guarded else "check_vacuous_unguarded"
    script = tmp_path / f"{name}.py"
    call = (
        "validate_result(run(Mode.VERIFY, Context(nix_home=Path('.'), mode=Mode.VERIFY)))"
        if guarded
        else "run(Mode.VERIFY, Context(nix_home=Path('.'), mode=Mode.VERIFY))"
    )
    import_line = (
        "from nixverify.contract import ("
        "CheckResult, Context, Mode, Status, exit_code_for, validate_result)"
        if guarded
        else "from nixverify.contract import CheckResult, Context, Mode, Status, exit_code_for"
    )
    script.write_text(
        "import sys\n"
        f"sys.path.append({str(SCRIPTS_DIR)!r})\n"
        "from pathlib import Path\n"
        f"{import_line}\n"
        "\n"
        "def run(mode, ctx):\n"
        "    return CheckResult(name='x', status=Status.PASS)  # no evidence — vacuous\n"
        "\n"
        "if __name__ == '__main__':\n"
        f"    OUTCOME = {call}\n"
        "    print(f'{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}')\n"
        "    sys.exit(exit_code_for(OUTCOME.status))\n",
        encoding="utf-8",
    )
    return script


def test_standalone_pattern_downgrades_a_vacuous_pass(tmp_path: Path) -> None:
    """Direct proof: the __main__ pattern with validate_result exits 2
    (CANNOT_MEASURE), not 0, on a vacuous PASS.
    """
    script = _vacuous_standalone_script(tmp_path, guarded=True)
    proc = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "cannot_measure" in proc.stdout


def test_standalone_pattern_without_validate_result_leaks_the_vacuous_pass(
    tmp_path: Path,
) -> None:
    """Control: reproduces the exact prior defect, so this test file proves
    it can actually fail, not merely that the fixed pattern happens to
    exit 2. Without validate_result, exit 0 leaks a false PASS.
    """
    script = _vacuous_standalone_script(tmp_path, guarded=False)
    proc = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, "control script should reproduce the pre-fix leak"


def _main_block_source(path: Path) -> str:
    """Source of the module's `if __name__ == "__main__":` block, or ""."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ):
            return ast.unparse(node)
    return ""


#: ARC 024. The shared actuation entry point. A check that delegates to it
#: satisfies this guard through it rather than textually — see the test below,
#: which pins that `standalone_main` really does call `validate_result` so the
#: delegation can never become a way around the rule.
_DELEGATE = "standalone_main("


def test_standalone_main_itself_calls_validate_result() -> None:
    """The delegation route must not be a hole in the guard below.

    Every retrofitted check routes `__main__` through
    `nixverify.actuation.standalone_main` instead of repeating the pattern. That
    is only acceptable while the helper applies §5 itself — if this assertion
    ever fails, the next test's `_DELEGATE` allowance is silently excusing four
    checks from the rule it exists to enforce.
    """
    source = (
        Path(__file__).resolve().parent.parent / "nixverify" / "actuation.py"
    ).read_text(encoding="utf-8")
    assert "validate_result(run_fn(" in source, (
        "standalone_main no longer routes the check's result through "
        "validate_result — the delegation allowance below is now a bypass"
    )


def test_every_real_check_standalone_block_calls_validate_result() -> None:
    """Regression guard: every checks/check_*.py must route its __main__
    block through validate_result, not call exit_code_for(run(...).status)
    directly — proven achievable by test_standalone_pattern_* above.

    ARC 024: delegation to `standalone_main` counts, because that helper applies
    `validate_result` on the check's behalf (pinned by the test immediately
    above). The property enforced is *the result is validated*, never *these
    exact characters appear in this block* — and the four retrofitted pilots
    satisfy the property through one implementation rather than four copies,
    which is doctrine C.9's direction.
    """
    missing = [
        path.name
        for path in CHECK_FILES
        if "validate_result(" not in (block := _main_block_source(path))
        and _DELEGATE not in block
    ]
    assert not missing, f"checks/*.py missing validate_result in __main__: {missing}"


def test_main_block_detector_finds_a_planted_missing_call(tmp_path: Path) -> None:
    """Control for the AST helper itself: a module lacking validate_result
    in its __main__ block must be detected, not silently pass.
    """
    path = tmp_path / "check_plain.py"
    path.write_text(
        textwrap.dedent(
            """
            if __name__ == "__main__":
                OUTCOME = run(Mode.VERIFY, Context(nix_home=Path('.'), mode=Mode.VERIFY))
                sys.exit(exit_code_for(OUTCOME.status))
            """
        ),
        encoding="utf-8",
    )
    assert "validate_result(" not in _main_block_source(path)
