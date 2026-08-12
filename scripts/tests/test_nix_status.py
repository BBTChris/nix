"""nix_status.sh must render EVERY check verify.py reports, not a subset.

Measured defect (ARC 028, this file's reason to exist). `nix_status.sh` v1.0.0
shipped two independent faults that between them meant the dashboard showed
2 of the 28 checks in `checks/registry.json`:

  1. It refused to invoke verify.py at all. Its `CANDIDATE_FLAGS` roster can
     only express a bare boolean token (`--verify-only`, `--no-repair`, ...),
     but verify.py's verify-only mode is the *value-taking* option
     `--mode verify`. No candidate matched `verify.py --help`, so check 3
     failed closed and the run never happened.
  2. Its output parser was case-sensitive and did not know verify.py's marker
     vocabulary. `render.py` emits `[ok]`, `[FAIL]`, `[??]`, `[--]`, `[GRD]`;
     the parser tested for `OK`/`PASS`/`FAIL`/`RED` as uppercase words. Only
     `[FAIL]` matched. The 24 passing checks and two of the three cannot-
     measures were silently dropped; the two lines that did appear got through
     on uppercase keywords that happened to occur in their free-text detail.

Both faults are of the same family — the wrapper guessing at another
instrument's interface instead of deriving from it — so these tests anchor to
the REAL `nixverify.render`/`nixverify.contract` rather than to a copy of the
line format. If verify.py's renderer changes its glyphs, these fail and name
the wrapper as the thing to update, which is the whole point: the parser's
contract IS the renderer's output.
"""

# pylint: disable=invalid-name
# Test names SHOUT the property, as in every other suite here.

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

NIX_HOME = Path(__file__).resolve().parents[2]
STATUS_SH = NIX_HOME / "scripts" / "nix_status.sh"
VERIFY_PY = NIX_HOME / "scripts" / "verify.py"

# The roster the stub reports — one of every status the contract defines, so a
# parser that only understands some of the glyph vocabulary cannot pass.
STUB_ROSTER = [
    ("check_alpha_pass", "PASS", "", ""),
    ("check_bravo_pass", "PASS", "/home/bbt/nix", ""),
    ("check_charlie_fail", "FAIL_REPAIRABLE", "127.0.0.1:4002", "endpoint unreachable"),
    ("check_delta_operator", "FAIL_NEEDS_OPERATOR", "", "operator must act"),
    ("check_echo_cannot", "CANNOT_MEASURE", "", "subject unavailable"),
    ("check_foxtrot_skipped", "SKIPPED", "", "not applicable at this privilege"),
    ("check_golf_guarded", "GUARDED", "", "known red, owned by a live arc"),
    # Detail text carrying words the old parser keyed on. A PASS whose detail
    # says "failed" must still be green: the marker decides the verdict, never
    # prose in the detail (the v1.0.0 parser scored these backwards).
    ("check_hotel_pass", "PASS", "", "no retries failed; RED path unused"),
]

_STUB = """\
import sys
from pathlib import Path

sys.path.insert(0, {nixverify!r})
from nixverify.contract import CheckResult, Status  # noqa: E402
from nixverify.render import render_results, render_summary, theme_for  # noqa: E402

ROSTER = {roster!r}
ARGV_LOG = Path({argv_log!r})

if "--help" in sys.argv[1:]:
    # Reproduce the real verify.py's argparse surface, including the fact that
    # verify-only is a CHOICE of --mode, not a standalone flag.
    print("usage: verify.py [-h] [--mode {{verify,correct,install}}]")
    print("                 [--privilege {{user,root,all}}] [--maintenance]")
    print("                 [--allow-interactive] [--verbose] [--registry REGISTRY]")
    print()
    print("options:")
    print("  -h, --help            show this help message and exit")
    print("  --mode {{verify,correct,install}}")
    print("  --verbose")
    sys.exit(0)

ARGV_LOG.write_text("\\n".join(sys.argv[1:]), encoding="utf-8")

results = [
    CheckResult(name=n, status=Status[s], site=site, detail=detail)
    for n, s, site, detail in ROSTER
]
theme = theme_for(sys.stdout, {{}})
print(render_results(results, theme, False))
print(render_summary(results, 0, theme))
sys.exit({rc})
"""


def _write_stub(tmp_path: Path, roster, rc: int) -> tuple[Path, Path]:
    """A fake verify.py that renders `roster` through the REAL renderer."""
    argv_log = tmp_path / "argv.txt"
    stub = tmp_path / "verify.py"
    stub.write_text(
        _STUB.format(
            nixverify=str(NIX_HOME / "scripts"),
            roster=list(roster),
            argv_log=str(argv_log),
            rc=rc,
        ),
        encoding="utf-8",
    )
    return stub, argv_log


def _run_status(stub: Path, *args: str, expect_rc: int | None = None):
    """Run nix_status.sh against the stub. Colour left ON so verdicts are visible."""
    proc = subprocess.run(  # nosec B603,B607 - fixed argv, test-local paths
        ["bash", str(STATUS_SH), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(Path.home()),
            "NIX_VERIFY_PY": str(stub),
            "NIX_PYTHON": sys.executable,
            "NIX_STATUS_LOCK": str(stub.parent / "lock"),
        },
    )
    if expect_rc is not None:
        assert proc.returncode == expect_rc, (
            f"exit {proc.returncode} != {expect_rc}\n{proc.stdout}\n{proc.stderr}"
        )
    return proc


def _bubbles(stdout: str) -> dict[str, str]:
    """Map check name -> colour ('green'|'yellow'|'red') from the rendered bubbles."""
    colours = {"\x1b[92m": "green", "\x1b[93m": "yellow", "\x1b[91m": "red"}
    found: dict[str, str] = {}
    for line in stdout.splitlines():
        match = re.search(r"(\x1b\[9[123]m)●.*?(check_[A-Za-z0-9_.-]+)", line)
        if match:
            found[match.group(2)] = colours[match.group(1)]
    return found


def test_every_reported_check_gets_a_bubble(tmp_path: Path) -> None:
    """The defect, stated as a test: 8 checks reported, 8 bubbles rendered."""
    stub, _ = _write_stub(tmp_path, STUB_ROSTER, rc=1)
    proc = _run_status(stub)
    found = _bubbles(proc.stdout)
    expected = {name for name, _, _, _ in STUB_ROSTER}
    missing = expected - set(found)
    assert not missing, (
        f"nix_status.sh dropped {len(missing)} of {len(expected)} checks "
        f"verify.py reported: {sorted(missing)}\n{proc.stdout}"
    )
    # The site/detail a failing check carries is the actionable part (§5) — it
    # must reach the bubble, not be truncated away by a restated name.
    assert "127.0.0.1:4002" in proc.stdout, proc.stdout
    assert "operator must act" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    "name,colour",
    [
        ("check_alpha_pass", "green"),
        ("check_bravo_pass", "green"),
        ("check_hotel_pass", "green"),  # detail says "failed" — marker still wins
        ("check_charlie_fail", "red"),
        ("check_delta_operator", "red"),
        ("check_echo_cannot", "yellow"),
        ("check_foxtrot_skipped", "yellow"),
        ("check_golf_guarded", "yellow"),
    ],
)
def test_verdict_comes_from_the_marker(tmp_path: Path, name: str, colour: str) -> None:
    """Each status maps to the right bubble — decided by glyph, never by prose."""
    stub, _ = _write_stub(tmp_path, STUB_ROSTER, rc=1)
    proc = _run_status(stub)
    found = _bubbles(proc.stdout)
    assert found.get(name) == colour, f"{name}: {found.get(name)} != {colour}"


def test_invokes_verify_only_mode(tmp_path: Path) -> None:
    """It must run verify.py in VERIFY-ONLY mode — never correct/install."""
    stub, argv_log = _write_stub(tmp_path, STUB_ROSTER, rc=0)
    _run_status(stub)
    assert argv_log.is_file(), "verify.py was never invoked"
    argv = argv_log.read_text(encoding="utf-8").split("\n")
    assert argv[:2] == ["--mode", "verify"], f"invoked with {argv!r}"
    assert "correct" not in argv and "install" not in argv


def test_real_verify_py_mode_is_discoverable() -> None:
    """Guard against verify.py's CLI drifting away from what the wrapper derives.

    The wrapper derives its invocation from `verify.py --help` rather than
    hardcoding it. This proves the thing it derives is still there — if
    verify.py renames its verify-only mode, this fails here rather than
    silently in the dashboard.
    """
    proc = subprocess.run(  # nosec B603 - fixed argv, repo-local path
        [sys.executable, str(VERIFY_PY), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert re.search(r"--mode\s+\{[^}]*\bverify\b[^}]*\}", proc.stdout), proc.stdout


def test_all_registered_checks_are_covered(tmp_path: Path) -> None:
    """No check in checks/ may be invisible to the dashboard.

    The roster is derived from the checks folder, so a check added later is
    covered without editing this test.
    """
    names = sorted(p.stem for p in (NIX_HOME / "checks").glob("check_*.py"))
    assert len(names) >= 20, f"unexpectedly few checks found: {names}"
    roster = [(n, "PASS", "", "") for n in names]
    stub, _ = _write_stub(tmp_path, roster, rc=0)
    proc = _run_status(stub, expect_rc=0)
    found = _bubbles(proc.stdout)
    missing = set(names) - set(found)
    assert not missing, (
        f"{len(missing)} checks never reach the dashboard: {sorted(missing)}"
    )


def test_zero_parsed_verdicts_is_not_healthy(tmp_path: Path) -> None:
    """The vacuous-pass guard must survive the fix (debug.md §7.3/§7.9)."""
    stub, _ = _write_stub(tmp_path, [], rc=0)
    proc = _run_status(stub, expect_rc=2)
    assert "refusing to report healthy" in proc.stdout


def test_exit_code_2_is_degraded_not_failed(tmp_path: Path) -> None:
    """verify.py exit 2 means cannot-measure (contract §4.2), not failure.

    The wrapper must reconcile against verify.py's documented exit mapping —
    0 pass / 1 fail / 2 cannot-measure / 3 guarded — instead of treating every
    non-zero rc as a disagreement, which would paint every degraded run red.
    """
    roster = [("check_echo_cannot", "CANNOT_MEASURE", "", "")]
    stub, _ = _write_stub(tmp_path, roster, rc=2)
    proc = _run_status(stub, expect_rc=1)
    assert "DEGRADED" in proc.stdout, proc.stdout


def test_exit_code_3_is_guarded_not_failed(tmp_path: Path) -> None:
    """verify.py exit 3 is GUARDED (CHECK-A1) — degraded, never a red rollup."""
    roster = [("check_golf_guarded", "GUARDED", "", "")]
    stub, _ = _write_stub(tmp_path, roster, rc=3)
    proc = _run_status(stub, expect_rc=1)
    assert "DEGRADED" in proc.stdout, proc.stdout


# --------------------------------------------------------------------------
# v1.2.0 — display order, the summary tally, and the SSH splash
#
# All three are PRESENTATION. None of them may be able to move a verdict, and
# the first test below is the one that asserts that rather than assuming it.
# --------------------------------------------------------------------------


def _ordered_names(stdout: str) -> list[tuple[str, str]]:
    """Check names in the order they are RENDERED, with their colour."""
    colours = {"\x1b[92m": "green", "\x1b[93m": "yellow", "\x1b[91m": "red"}
    out: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        match = re.search(r"(\x1b\[9[123]m)●.*?(check_[A-Za-z0-9_.-]+)", line)
        if match:
            out.append((match.group(2), colours[match.group(1)]))
    return out


def test_bubbles_are_grouped_PASS_then_FAIL_then_WARNING(tmp_path: Path) -> None:
    """The order the operator asked for, asserted on the rendered output.

    The roster is deliberately handed over in an order that is neither the
    target order nor alphabetical, so a script that simply echoed verify.py's
    own sequence would produce a different list and fail here.
    """
    roster = [
        ("check_zulu", "PASS", "", ""),
        ("check_alpha", "FAIL_NEEDS_OPERATOR", "site", "down"),
        ("check_mike", "CANNOT_MEASURE", "", "unreachable"),
        ("check_bravo", "PASS", "", ""),
        ("check_yankee", "FAIL_NEEDS_OPERATOR", "site", "down"),
        ("check_charlie", "GUARDED", "", "owned"),
    ]
    stub, _ = _write_stub(tmp_path, roster, rc=1)

    rendered = _ordered_names(_run_status(stub, expect_rc=2).stdout)
    groups = [colour for _, colour in rendered]

    assert groups == ["green", "green", "red", "red", "yellow", "yellow"], (
        f"rendered order was {rendered} — expected every PASS, then every FAIL, "
        "then every WARNING"
    )


def test_ALPHABETICAL_ORDER_SURVIVES_INSIDE_each_group(tmp_path: Path) -> None:
    """The secondary key. Without it two runs over one tree could differ."""
    roster = [
        ("check_zulu", "PASS", "", ""),
        ("check_alpha", "PASS", "", ""),
        ("check_mike", "PASS", "", ""),
        ("check_delta", "FAIL_NEEDS_OPERATOR", "site", "down"),
        ("check_bravo", "FAIL_NEEDS_OPERATOR", "site", "down"),
    ]
    stub, _ = _write_stub(tmp_path, roster, rc=1)

    names = [name for name, _ in _ordered_names(_run_status(stub, expect_rc=2).stdout)]

    assert names == [
        "check_alpha",
        "check_mike",
        "check_zulu",
        "check_bravo",
        "check_delta",
    ], f"rendered {names} — alphabetical must hold WITHIN each verdict group"


def test_the_DISPLAY_ORDER_CANNOT_MOVE_THE_EXIT_CODE(tmp_path: Path) -> None:
    """Grouping is a sort key; severity is `WORST_STATUS`. Conflating them would
    be the defect — a FAIL rendered after the passes must still exit 2, and a
    warning-only run must still exit 1 even though warnings render last."""
    only_warn = [("check_alpha", "CANNOT_MEASURE", "", "unreachable")]
    stub, _ = _write_stub(tmp_path, only_warn, rc=2)
    _run_status(stub, expect_rc=1)

    with_fail = [
        ("check_alpha", "PASS", "", ""),
        ("check_zulu", "FAIL_NEEDS_OPERATOR", "site", "down"),
    ]
    second = tmp_path / "b"
    second.mkdir()
    stub2, _ = _write_stub(second, with_fail, rc=1)
    _run_status(stub2, expect_rc=2)


def test_the_SUMMARY_TALLY_AGREES_WITH_THE_BUBBLES_ABOVE_IT(tmp_path: Path) -> None:
    """The tally is counted as bubbles are recorded, so it cannot disagree.

    Asserted against the rendered list rather than against the roster: the point
    is that the two halves of the SAME screen agree, which is what an operator
    reads. Four wrapper bubbles precede the checks and all four pass, so the
    PASS count carries them and TOTAL must account for them.
    """
    roster = [
        ("check_alpha", "PASS", "", ""),
        ("check_bravo", "PASS", "", ""),
        ("check_charlie", "FAIL_NEEDS_OPERATOR", "site", "down"),
        ("check_delta", "CANNOT_MEASURE", "", "unreachable"),
        ("check_echo", "GUARDED", "", "owned"),
    ]
    stub, _ = _write_stub(tmp_path, roster, rc=1)
    out = _run_status(stub, "--no-color", expect_rc=2).stdout

    def _tally(word: str) -> int:
        match = re.search(rf"^\s*●?\s*{word}\s+(\d+)\s*$", out, re.MULTILINE)
        assert match, f"no {word} row in the SUMMARY block:\n{out}"
        return int(match.group(1))

    rendered = _ordered_names(_run_status(stub, expect_rc=2).stdout)
    check_pass = sum(1 for _, c in rendered if c == "green")
    check_fail = sum(1 for _, c in rendered if c == "red")
    check_warn = sum(1 for _, c in rendered if c == "yellow")

    assert "SUMMARY" in out, out
    assert _tally("FAIL") == check_fail, out
    assert _tally("WARNING") == check_warn, out
    # The four wrapper bubbles are passes and are counted too.
    assert _tally("PASS") == check_pass + 4, out
    assert _tally("TOTAL") == _tally("PASS") + _tally("FAIL") + _tally("WARNING"), out


def test_the_SPLASH_is_EXECUTED_not_transcribed(tmp_path: Path) -> None:
    """The banner must be RUN, so it cannot drift from the one SSH shows.

    A stub splash is pointed at via NIX_STATUS_SPLASH_SCRIPT and must appear in
    the output. If the script had copied the artwork instead, a stub could not
    change what is printed — which is exactly the drift being prevented.
    """
    splash = tmp_path / "splash.sh"
    splash.write_text("#!/bin/sh\necho 'SPLASH-MARKER-7f3a'\n", encoding="utf-8")
    splash.chmod(0o755)
    stub, _ = _write_stub(tmp_path, [("check_alpha", "PASS", "", "")], rc=0)

    proc = subprocess.run(  # nosec B603,B607 - fixed argv, test-local paths
        ["bash", str(STATUS_SH), "--no-color"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(Path.home()),
            "NIX_VERIFY_PY": str(stub),
            "NIX_PYTHON": sys.executable,
            "NIX_STATUS_LOCK": str(tmp_path / "lock"),
            "NIX_STATUS_SPLASH_SCRIPT": str(splash),
        },
    )
    assert "SPLASH-MARKER-7f3a" in proc.stdout, proc.stdout
    assert proc.stdout.index("SPLASH-MARKER-7f3a") < proc.stdout.index(
        "NIX — STATUS"
    ), "the splash must render ABOVE the status block"


def test_a_MISSING_SPLASH_SAYS_SO_and_does_NOT_break_the_dashboard(
    tmp_path: Path,
) -> None:
    """Silence would leave an operator unable to tell suppressed from broken."""
    stub, _ = _write_stub(tmp_path, [("check_alpha", "PASS", "", "")], rc=0)

    proc = subprocess.run(  # nosec B603,B607 - fixed argv, test-local paths
        ["bash", str(STATUS_SH), "--no-color"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(Path.home()),
            "NIX_VERIFY_PY": str(stub),
            "NIX_PYTHON": sys.executable,
            "NIX_STATUS_LOCK": str(tmp_path / "lock"),
            "NIX_STATUS_SPLASH_SCRIPT": str(tmp_path / "does-not-exist"),
        },
    )
    assert proc.returncode == 0, proc.stdout
    assert "not present or not executable" in proc.stdout, proc.stdout
    assert "NIX — STATUS" in proc.stdout, "the dashboard must still render"


def test_NO_SPLASH_suppresses_it_entirely(tmp_path: Path) -> None:
    """`--no-splash` must print neither the banner nor a complaint about it."""
    splash = tmp_path / "splash.sh"
    splash.write_text("#!/bin/sh\necho 'SPLASH-MARKER-7f3a'\n", encoding="utf-8")
    splash.chmod(0o755)
    stub, _ = _write_stub(tmp_path, [("check_alpha", "PASS", "", "")], rc=0)

    proc = subprocess.run(  # nosec B603,B607 - fixed argv, test-local paths
        ["bash", str(STATUS_SH), "--no-color", "--no-splash"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(Path.home()),
            "NIX_VERIFY_PY": str(stub),
            "NIX_PYTHON": sys.executable,
            "NIX_STATUS_LOCK": str(tmp_path / "lock"),
            "NIX_STATUS_SPLASH_SCRIPT": str(splash),
        },
    )
    assert "SPLASH-MARKER-7f3a" not in proc.stdout, proc.stdout
    assert "splash:" not in proc.stdout, proc.stdout
