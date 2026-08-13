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
import time
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


def _run_status(
    stub: Path, *args: str, expect_rc: int | None = None, env: dict | None = None
):
    """Run nix_status.sh against the stub. Colour left ON so verdicts are visible.

    `env` ADDS to the fixed environment rather than replacing it. Terminal
    capability is part of that environment now (the orange tier is derived from
    `COLORTERM`/`tput colors`), so a test that cares about which escape is
    emitted has to be able to state the terminal it is testing.
    """
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
            **(env or {}),
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
    # ANSI is STRIPPED FIRST, exactly as `nix_status.sh` strips it before
    # deriving — this asserts the property the wrapper actually relies on.
    #
    # ARC 029 / 0.3. Python 3.14's argparse COLOURISES help, and it honours
    # FORCE_COLOR even when stdout is a pipe. This environment sets FORCE_COLOR=3,
    # under which the real output reads
    # `[36m--mode [33m{verify,correct,install}[0m` — so a regex anchored on
    # `--mode\s+\{` matched on the runner that happened not to export the variable
    # and failed on the one that did. Same bytes, same commit, verdict decided by
    # an environment variable: the class 0.1 opened, in a third instrument.
    #
    # The WRAPPER was never at risk and that was measured rather than assumed:
    # `check_verify_only_flag` builds `help_plain` through `strip_ansi` before
    # `derive_mode_invocation` ever sees it. Stripping here makes the test measure
    # the same text the shipped derivation reads.
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", proc.stdout)
    assert re.search(r"--mode\s+\{[^}]*\bverify\b[^}]*\}", plain), plain


def test_the_WRAPPER_derives_its_invocation_from_COLOURISED_help() -> None:
    """The end-to-end property, driven under the environment that breaks a parser.

    Pinned separately from the test above because the two can fail for different
    reasons: that one asks whether verify.py still OFFERS `--mode verify`, this
    one asks whether the wrapper can still FIND it when argparse paints the text.
    A `nix_status.sh` that could not would refuse to invoke verify.py at all and
    report a dashboard over a run that never happened — check 3 failing closed,
    which is safe and still wrong.
    """
    stub_free_env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(Path.home()),
        "NIX_PYTHON": sys.executable,
        "FORCE_COLOR": "3",
    }
    proc = subprocess.run(  # nosec B603 - fixed argv, repo-local path
        [sys.executable, str(VERIFY_PY), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
        env=stub_free_env,
    )
    assert "\x1b[" in proc.stdout, (
        "argparse did not colourise under FORCE_COLOR=3, so this control is no "
        "longer exercising the condition it was written for"
    )
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", proc.stdout)
    assert re.search(r"--mode\s+\{[^}]*\bverify\b[^}]*\}", plain)


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


# --------------------------------------------------------------------------
# v1.3.0 — live output
#
# The wrapper's half of `--stream`. The property is TEMPORAL, so the tests below
# are too: an assertion made only on the finished stdout cannot tell a live
# surface from a batched one, which is precisely how the original defect went
# unnoticed — every verdict was present, all of them arriving at once after 70
# seconds of blank screen.
# --------------------------------------------------------------------------

# A stub that streams. It advertises `--stream` in --help and, when given it,
# emits one `>>` line per check through the REAL StreamProgress, sleeping
# between them so "live" is measurable rather than asserted. Without the flag it
# behaves exactly like the plain stub — which is how the fallback path is
# exercised by every test above this section, for free.
_STREAM_STUB = """\
import sys
import time
from pathlib import Path

sys.path.insert(0, {nixverify!r})
from nixverify.contract import CheckResult, Status  # noqa: E402
from nixverify.render import (  # noqa: E402
    StreamProgress,
    render_results,
    render_summary,
    theme_for,
)

ROSTER = {roster!r}
ARGV_LOG = Path({argv_log!r})
DELAY = {delay!r}

if "--help" in sys.argv[1:]:
    print("usage: verify.py [-h] [--mode {{verify,correct,install}}] [--stream]")
    print()
    print("options:")
    print("  -h, --help            show this help message and exit")
    print("  --mode {{verify,correct,install}}")
    print("  --stream              print each check's verdict as it lands")
    print("  --verbose")
    sys.exit(0)

ARGV_LOG.write_text("\\n".join(sys.argv[1:]), encoding="utf-8")

theme = theme_for(sys.stdout, {{}})
results = []
progress = StreamProgress(sys.stdout, theme, len(ROSTER))
for n, s, site, detail in ROSTER:
    time.sleep(DELAY)
    result = CheckResult(name=n, status=Status[s], site=site, detail=detail)
    result.duration_s = DELAY
    results.append(result)
    if "--stream" in sys.argv[1:]:
        progress.check_verdict(result)

print(render_results(results, theme, False))
print(render_summary(results, 0, theme))
sys.exit({rc})
"""


def _write_stream_stub(
    tmp_path: Path, roster, rc: int, delay: float = 0.0
) -> tuple[Path, Path]:
    """A fake verify.py that STREAMS `roster` through the real StreamProgress."""
    argv_log = tmp_path / "argv.txt"
    stub = tmp_path / "verify.py"
    stub.write_text(
        _STREAM_STUB.format(
            nixverify=str(NIX_HOME / "scripts"),
            roster=list(roster),
            argv_log=str(argv_log),
            rc=rc,
            delay=delay,
        ),
        encoding="utf-8",
    )
    return stub, argv_log


def test_a_verdict_REACHES_THE_SCREEN_before_the_run_ends(tmp_path: Path) -> None:
    """The defect, stated as a test — and it is a test about TIME.

    Four checks, one second apart. The first verdict must be readable on stdout
    while the run is still going; v1.2.0 produced nothing until the process
    exited, four seconds later. Read incrementally from a live pipe, because
    reading to EOF is exactly the measurement that cannot tell the two apart.
    """
    roster = [(f"check_{i}", "PASS", "", "") for i in range(4)]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=0, delay=1.0)

    with subprocess.Popen(  # nosec B603,B607 - fixed argv, test-local paths
        ["bash", str(STATUS_SH), "--no-color", "--no-splash"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(Path.home()),
            "NIX_VERIFY_PY": str(stub),
            "NIX_PYTHON": sys.executable,
            "NIX_STATUS_LOCK": str(tmp_path / "lock"),
        },
    ) as proc:
        try:
            assert proc.stdout is not None
            first_verdict_at = None
            started = time.monotonic()
            for line in proc.stdout:
                if "check_0" in line:
                    first_verdict_at = time.monotonic() - started
                    break
            assert first_verdict_at is not None, "no verdict was ever printed"
            # The run cannot finish before ~4s (4 checks x 1s). A first verdict
            # at ~1s is live; one at ~4s is the old batch wearing a new order.
            # Measured both ways before this test was kept: 1.19s with live
            # output, 4.32s with --no-live. The gate discriminates.
            assert first_verdict_at < 3.0, (
                f"first verdict took {first_verdict_at:.2f}s — that is batch "
                "timing, not live output"
            )
            assert proc.poll() is None, "the run had already finished; nothing was live"
        finally:
            proc.kill()
            proc.wait(timeout=30)


def test_the_HEADER_is_printed_before_any_verdict(tmp_path: Path) -> None:
    """A header rendered after its body is not a header."""
    roster = [("check_alpha", "PASS", "", ""), ("check_bravo", "PASS", "", "")]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=0)
    lines = _run_status(stub, "--no-color", "--no-splash", expect_rc=0).stdout
    header = lines.index("NIX — STATUS", 0) if "NIX — STATUS" in lines else -1
    first_check = lines.index("check_alpha")
    assert header != -1 and header < first_check, lines


def test_streamed_lines_are_NOT_counted_as_extra_bubbles(tmp_path: Path) -> None:
    """Every check is shown twice — live, then in the recap — and tallied ONCE.

    The live path prints and the recap prints, but only `record` counts. A tally
    that double-counted would be the summary disagreeing with the list above it,
    which is the exact defect class the v1.2.0 counter was built to avoid.
    """
    roster = [(f"check_{i:02d}", "PASS", "", "") for i in range(6)]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=0)
    out = _run_status(stub, "--no-color", "--no-splash", expect_rc=0).stdout

    # 6 checks + the 4 wrapper verdicts (verify.py, interpreter, mode, run).
    total_line = [ln for ln in out.splitlines() if "TOTAL" in ln]
    assert total_line, out
    assert total_line[0].split()[-1] == "10", f"{total_line[0]}\n{out}"
    # Each check really did appear twice: once live, once in the recap.
    assert out.count("check_00") == 2, out


def test_stream_is_passed_ONLY_when_help_proves_it(tmp_path: Path) -> None:
    """Same doctrine as check 3, applied to the second flag: prove, never assume.

    An assumed `--stream` reaches an older verify.py as an unknown argument,
    which argparse exits 2 on — and this script would then report the NODE as
    unmeasurable on the strength of its own guess about its instrument.
    """
    # Two stubs, two directories: each writes its own argv log, and the two must
    # not overwrite one another's.
    streaming_dir, plain_dir = tmp_path / "streaming", tmp_path / "plain"
    streaming_dir.mkdir()
    plain_dir.mkdir()
    roster = [("check_alpha", "PASS", "", "")]
    streaming, stream_argv = _write_stream_stub(streaming_dir, roster, rc=0)
    plain, plain_argv = _write_stub(plain_dir, roster, rc=0)

    _run_status(streaming, "--no-color", "--no-splash", expect_rc=0)
    assert "--stream" in stream_argv.read_text(encoding="utf-8").split("\n")

    proc = _run_status(plain, "--no-color", "--no-splash", expect_rc=0)
    assert "--stream" not in plain_argv.read_text(encoding="utf-8").split("\n")
    assert "has no --stream" in proc.stdout, (
        "a verify.py without --stream must SAY the live view is unavailable, "
        "not silently show nothing"
    )


def test_NO_LIVE_restores_the_v120_behaviour(tmp_path: Path) -> None:
    """The escape hatch: no `>>`, no --stream, everything at the end."""
    roster = [("check_alpha", "PASS", "", "")]
    stub, argv_log = _write_stream_stub(tmp_path, roster, rc=0)
    out = _run_status(
        stub, "--no-color", "--no-splash", "--no-live", expect_rc=0
    ).stdout
    assert "--stream" not in argv_log.read_text(encoding="utf-8").split("\n")
    assert out.count("check_alpha") == 1, out


def test_BRIEF_prints_one_line_and_no_live_output(tmp_path: Path) -> None:
    """--brief exists to be grepped; six progress lines above it would end that."""
    roster = [(f"check_{i}", "PASS", "", "") for i in range(6)]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=0)
    out = _run_status(stub, "--no-color", "--brief", expect_rc=0).stdout
    assert out.strip() == "NIX ● HEALTHY", out


# -- colour: warning and error text names its own colour -------------------
#
# Two ways for a message to be unreadable, and this section holds one test for
# each because the second was introduced BY the fix for the first:
#
#   1. no colour at all — `${DIM}` sets faintness, so the text wore the
#      terminal's default foreground (faint green on this operator's profile);
#   2. a colour the terminal cannot parse — a 24-bit SGR sent to a 256-colour
#      terminal, which swallowed the message that followed it. Measured on this
#      node: TERM=xterm-256color, COLORTERM unset, no RGB in terminfo.
#
# Both are the same underlying fault — legibility resting on an untested
# property of the terminal — so both are pinned.

_ORANGE_TRUECOLOR = "\x1b[1;38;2;255;102;0m"
_ORANGE_256 = "\x1b[1;38;5;208m"
_ORANGE_16 = "\x1b[1;93m"


def test_failure_text_is_NEON_ORANGE_and_never_merely_dim(tmp_path: Path) -> None:
    """`\\033[2m` sets faintness, not colour — dim text wears the terminal's own.

    On a green-on-black profile that rendered every failure detail as faint
    green: the least legible colour on screen carrying the most urgent text, in
    the hue that means "fine". A line that reports trouble states its colour.
    """
    roster = [
        ("check_alpha", "FAIL_REPAIRABLE", "127.0.0.1:4002", "endpoint unreachable"),
        ("check_bravo", "CANNOT_MEASURE", "", "subject unavailable"),
        ("check_charlie", "PASS", "", "all good"),
    ]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=1)
    out = _run_status(
        stub,
        "--no-splash",
        expect_rc=2,
        env={"NIX_STATUS_COLOR_TIER": "truecolor"},
    ).stdout

    for line in out.splitlines():
        if "endpoint unreachable" in line or "subject unavailable" in line:
            assert _ORANGE_TRUECOLOR in line, (
                f"warning/error text was not orange: {line!r}"
            )
    # A pass keeps the quiet treatment: reassurance must not compete with alarm.
    pass_lines = [ln for ln in out.splitlines() if "all good" in ln]
    assert pass_lines and all(_ORANGE_TRUECOLOR not in ln for ln in pass_lines), (
        pass_lines
    )


@pytest.mark.parametrize(
    ("env", "expected", "forbidden"),
    [
        # This node, and the regression: 256 colours, no COLORTERM. A 24-bit
        # sequence here made every warning and error message disappear.
        ({"TERM": "xterm-256color"}, _ORANGE_256, _ORANGE_TRUECOLOR),
        # A terminal that says it means it.
        (
            {"TERM": "xterm-256color", "COLORTERM": "truecolor"},
            _ORANGE_TRUECOLOR,
            _ORANGE_256,
        ),
        # Neither advertisement: fall all the way back to a 16-colour value that
        # every terminal since the 1980s renders. Never to nothing.
        ({"TERM": "vt100"}, _ORANGE_16, _ORANGE_TRUECOLOR),
        # No TERM at all — `tput` cannot answer, and the answer must still be a
        # colour rather than an empty string or a crash.
        ({}, _ORANGE_16, _ORANGE_TRUECOLOR),
    ],
    ids=["256-colour", "truecolor", "16-colour", "no-TERM"],
)
def test_the_orange_TIER_matches_what_the_terminal_advertises(
    tmp_path: Path, env: dict, expected: str, forbidden: str
) -> None:
    """Derived from the terminal, never assumed — and never degraded to nothing.

    The 24-bit form is not universally renderable. Sent to a 256-colour terminal
    it is not merely approximated, it is mis-parsed, and the text after it is
    swallowed — which turned "the most urgent line on screen is hard to read"
    into "the most urgent line on screen is absent".
    """
    roster = [("check_alpha", "FAIL_REPAIRABLE", "site", "endpoint unreachable")]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=1)
    out = _run_status(stub, "--no-splash", expect_rc=2, env=env).stdout

    detail = [ln for ln in out.splitlines() if "endpoint unreachable" in ln]
    assert detail, out
    assert all(expected in ln for ln in detail), detail
    assert all(forbidden not in ln for ln in detail), detail


def test_NO_COLOR_strips_the_orange_too(tmp_path: Path) -> None:
    """A colour added is a colour --no-color must be able to remove."""
    roster = [("check_alpha", "FAIL_REPAIRABLE", "site", "endpoint unreachable")]
    stub, _ = _write_stream_stub(tmp_path, roster, rc=1)
    out = _run_status(stub, "--no-color", "--no-splash", expect_rc=2).stdout
    assert "\x1b[" not in out, out
