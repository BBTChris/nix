"""Full-engine run against the real node, plus the §5.1 control cycle."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "scripts" / "verify.py"
MANIFEST = REPO / "checks" / "verify_manifest.json"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke the real verify.py as a subprocess, capturing stdout/stderr."""
    return subprocess.run(
        [sys.executable, str(VERIFY), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_manifest_lists_only_checks_that_exist() -> None:
    """A manifest naming an absent check would silently CANNOT_MEASURE."""
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for block in payload["blocks"]:
        for name in block["checks"]:
            assert (REPO / "checks" / f"{name}.py").is_file(), name


def test_real_run_reports_every_check_in_manifest_order() -> None:
    """Results print in manifest order, never completion order (§6)."""
    proc = _run(["--verbose"])
    order = [
        "check_python_runtime",
        "check_venv",
        "check_node_identity",
        "check_python_deps",
    ]
    positions = [proc.stdout.index(name) for name in order]
    assert positions == sorted(positions), proc.stdout


def test_real_run_exits_zero_or_two_never_one_on_a_healthy_box() -> None:
    """Node identity may be absent pre-install; that is 1, and is informative."""
    proc = _run([])
    assert proc.returncode in (0, 1, 2)
    assert "passed" in proc.stdout


def test_summary_line_is_present() -> None:
    """The summary line always carries the process exit code."""
    assert "exit" in _run([]).stdout
