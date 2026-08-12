"""Full-engine run against the real node, plus the §5.1 control cycle."""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "scripts" / "verify.py"
MANIFEST = REPO / "checks" / "registry.json"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke the real verify.py as a subprocess, capturing stdout/stderr."""
    return subprocess.run(
        ["/usr/bin/python3", str(VERIFY), *args],
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


#: A rendered verdict line: `  [ok]   check_name ...`. The glyph set is §12's.
_VERDICT = re.compile(r"^\s*\[(?:ok|FAIL|\?\?|GRD|--)\]\s+(\S+)", re.MULTILINE)


def _reported_order(stdout: str) -> list[str]:
    """The checks that actually REPORTED, in the order they were printed.

    Read off the verdict lines rather than by `str.index`, which was the old
    method and is unsafe here: check names now appear inside OTHER checks'
    evidence — `check_observed_resource_claims` names every check it observed,
    and `check_derived_claims` names the population it counted. A substring
    search finds whichever mention comes first in the byte stream, which is not
    necessarily the check's own verdict line.
    """
    return _VERDICT.findall(stdout)


def test_real_run_reports_every_check_in_manifest_order() -> None:
    """Results print in manifest order, never completion order (§6).

    ARC 025 Stage 2.3: the expected order is DERIVED FROM THE MANIFEST, not
    restated here. It used to be a hardcoded list of four names reflecting the
    hand-maintained `bootstrap-floor / identity / trading-stack` blocks — and
    `--optimize` then re-derived the plan from the dependency graph, which puts
    `check_node_identity` ahead of `check_venv` because nothing at that level
    claims the venv. The literal list was a moving anchor (doctrine C.4) and it
    moved. A restated expectation cannot survive the thing it describes being
    generated; a derived one can, and it now covers ALL of the population
    instead of a sample of four.

    This is also Stage 2.3's third census: EXECUTED == PLANNED == ON DISK. A
    check on disk but absent from the plan never runs, and its absence looks
    exactly like green.
    """
    proc = _run(["--verbose"])
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    planned = [name for block in payload["blocks"] for name in block["checks"]]
    on_disk = sorted(p.stem for p in (REPO / "checks").glob("check_*.py"))
    reported = _reported_order(proc.stdout)

    # Non-vacuity before the assertion: a run that printed no verdict line at
    # all would otherwise satisfy an order comparison trivially.
    assert len(reported) > 1, proc.stdout

    assert reported == planned, (
        f"reported order {reported} != manifest order {planned}\n{proc.stdout}"
    )
    # Census, three ways — not two. Two agreeing counts can both omit the same
    # check; the third is what makes an orphan visible.
    assert len(reported) == len(planned) == len(on_disk), (
        f"executed={len(reported)} planned={len(planned)} on_disk={len(on_disk)}"
    )
    assert sorted(reported) == sorted(planned) == on_disk


def test_real_run_exit_code_is_within_the_documented_taxonomy() -> None:
    """Exit is 0/1/2 per §4.2; 1 is legitimate (e.g. a real FAIL), not excluded."""
    proc = _run([])
    assert proc.returncode in (0, 1, 2)
    assert "passed" in proc.stdout


def test_summary_line_is_present() -> None:
    """The summary line always carries the process exit code."""
    assert "exit" in _run([]).stdout
