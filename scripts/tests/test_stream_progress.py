"""`--stream` — verdicts published as they land, not banked until the end.

## The defect this suite exists for

`verify.py main()` ran every block and only then printed. `LiveProgress` was the
only progress surface, and it is TTY-gated by construction (`theme.colour` is
`isatty() and NO_COLOR unset`), so anything reading verify.py through a pipe —
`nix_status.sh`, a systemd unit, a log capture — saw nothing at all until the
final block. Measured on this tree that is ~70 seconds of blank screen, a single
check accounting for 36 of them.

`StreamProgress` is the pipe-facing surface. The properties below are the ones
that make it a live surface rather than a differently-shaped batch:

  * it emits on a NON-TTY, which is exactly where `LiveProgress` must not;
  * it FLUSHES each line, because Python block-buffers a pipe and an unflushed
    write would reproduce batch-at-the-end through a userspace buffer instead of
    through `main()` — the same defect, one layer down, and invisible in any test
    that only inspects the final string;
  * it is ADDITIVE — the end-of-run registry-order block (§6) still prints, so
    no existing consumer of verify.py's output parses differently.

The flush test is the load-bearing one. `io.StringIO` has no observable buffer,
so a test built on it would pass whether or not the flush existed; the recording
stream below is what makes the property falsifiable at all.
"""

# pylint: disable=invalid-name,import-outside-toplevel
# Test names SHOUT the property under test, as in every other suite here.

from __future__ import annotations

import io
import json
import subprocess  # nosec B404 - fixed argv, repo-local paths
import sys
import threading
from pathlib import Path

from nixverify.contract import CheckResult, Status
from nixverify.render import (
    StreamProgress,
    Theme,
    render_results,
)

NIX_HOME = Path(__file__).resolve().parents[2]
VERIFY_PY = NIX_HOME / "scripts" / "verify.py"

PLAIN = Theme(colour=False, unicode=False)
COLOUR = Theme(colour=True, unicode=True)


class RecordingStream(io.StringIO):
    """A stream that remembers WHEN it was flushed, not merely what it holds.

    Every `flush()` snapshots the full text written so far. A surface that wrote
    all its lines and flushed once at the end would leave a single snapshot
    holding everything; a live surface leaves one snapshot per line, each a
    strict prefix of the next. That is the difference between streaming and
    batching, and it is invisible to any assertion made on the final value.
    """

    def __init__(self) -> None:
        super().__init__()
        self.snapshots: list[str] = []

    def flush(self) -> None:
        self.snapshots.append(self.getvalue())
        super().flush()


def _result(name: str, status: Status = Status.PASS, duration: float = 0.5):
    """A CheckResult with its duration already stamped, as the engine leaves it."""
    result = CheckResult(name=name, status=status, evidence="measured")
    result.duration_s = duration
    return result


# -- the property LiveProgress cannot have ---------------------------------


def test_stream_progress_EMITS_on_a_non_tty() -> None:
    """The whole point. `LiveProgress` writes nothing here; this must write.

    Pinned as its own test because the two surfaces are deliberate opposites on
    this axis, and a future refactor that unified them would silently take the
    live output away from every piped reader.
    """
    stream = RecordingStream()
    progress = StreamProgress(stream, PLAIN, total=1)
    progress.start()
    progress.check_verdict(_result("check_venv"))
    progress.stop()
    assert "check_venv" in stream.getvalue()


def test_each_verdict_is_flushed_as_it_is_written() -> None:
    """One flush per line, each holding a strict prefix of the next.

    This is the test that would fail if the `flush()` call were dropped — the
    final string would be identical, and a piped reader would still wait for the
    8 KiB buffer or process exit.
    """
    stream = RecordingStream()
    progress = StreamProgress(stream, PLAIN, total=3)
    for i, name in enumerate(("check_a", "check_b", "check_c"), start=1):
        progress.check_verdict(_result(name))
        assert len(stream.snapshots) == i, (
            f"after {i} verdicts there were {len(stream.snapshots)} flushes — "
            "verdicts are being buffered, not streamed"
        )
        assert name in stream.snapshots[-1]
    # Each snapshot is a prefix of the one after it: append-only, never rewritten.
    for earlier, later in zip(stream.snapshots, stream.snapshots[1:]):
        assert later.startswith(earlier)


def test_a_verdict_is_readable_before_the_next_check_starts() -> None:
    """A line lands at verdict time, not at run end — asserted mid-run."""
    stream = RecordingStream()
    progress = StreamProgress(stream, PLAIN, total=2)
    progress.check_start("check_a")
    progress.check_verdict(_result("check_a"))
    mid_run = stream.getvalue()
    progress.check_start("check_b")
    assert "check_a" in mid_run
    assert "check_b" not in mid_run


# -- what each line carries -------------------------------------------------


def test_the_line_carries_name_counter_and_the_ENGINE_duration() -> None:
    """Duration is the engine's measurement, formatted — never recomputed here."""
    stream = RecordingStream()
    progress = StreamProgress(stream, PLAIN, total=4)
    progress.check_verdict(_result("check_feed_kill_drill", duration=13.29))
    line = stream.getvalue().strip()
    assert line.startswith(">>")
    assert "[ok]" in line
    assert "check_feed_kill_drill" in line
    assert "1/4" in line
    assert "13.29s" in line


def test_the_counter_counts_completions_against_the_registry_total() -> None:
    """n/total, both halves derived: the denominator is the registry's own count."""
    stream = RecordingStream()
    progress = StreamProgress(stream, PLAIN, total=3)
    for name in ("check_a", "check_b", "check_c"):
        progress.check_verdict(_result(name))
    counters = [line.split()[3] for line in stream.getvalue().strip().splitlines()]
    assert counters == ["1/3", "2/3", "3/3"]


def test_every_contract_status_reaches_the_stream_with_its_own_marker() -> None:
    """No status is silently unrenderable — a dropped one would read as a skip."""
    stream = RecordingStream()
    statuses = list(Status)
    progress = StreamProgress(stream, PLAIN, total=len(statuses))
    for i, status in enumerate(statuses):
        progress.check_verdict(_result(f"check_{i}", status=status))
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == len(statuses)
    markers = {line.split()[1] for line in lines}
    assert markers == {"[ok]", "[FAIL]", "[??]", "[--]", "[GRD]"}


def test_colour_is_applied_only_where_the_theme_allows_it() -> None:
    """§12 degradation, same rule the rest of render.py obeys."""
    plain, painted = RecordingStream(), RecordingStream()
    StreamProgress(plain, PLAIN, total=1).check_verdict(_result("check_a"))
    StreamProgress(painted, COLOUR, total=1).check_verdict(_result("check_a"))
    assert "\x1b[" not in plain.getvalue()
    assert "\x1b[" in painted.getvalue()


# -- additive, not a replacement -------------------------------------------


def test_the_sentinel_cannot_collide_with_the_end_of_run_block() -> None:
    """`>>` is what keeps both renderings unambiguous in one stream.

    `render_results` must never produce a line a live-output reader would mistake
    for a streamed verdict — that is the entire basis on which `--stream` can be
    additive rather than a mode that replaces the §6 block.
    """
    results = [_result(f"check_{i}", status=s) for i, s in enumerate(Status)]
    for line in render_results(results, PLAIN, verbose=True).splitlines():
        assert not line.strip().startswith(">>")


# -- thread safety (parallel blocks) ---------------------------------------


def test_concurrent_verdicts_produce_whole_lines_and_unique_counters() -> None:
    """Parallel blocks call `check_verdict` from worker threads (engine.Observer).

    Two failures are possible and both are checked: interleaved half-lines, and
    two verdicts sharing a counter value because the increment raced. The lock
    has to cover the increment AND the write for both to hold.
    """
    stream = RecordingStream()
    total = 40
    progress = StreamProgress(stream, PLAIN, total=total)
    barrier = threading.Barrier(total)

    def emit(i: int) -> None:
        barrier.wait()
        progress.check_verdict(_result(f"check_{i:02d}"))

    threads = [threading.Thread(target=emit, args=(i,)) for i in range(total)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = stream.getvalue().splitlines()
    assert len(lines) == total
    counters = sorted(int(line.split()[3].split("/")[0]) for line in lines)
    assert counters == list(range(1, total + 1))
    for line in lines:
        assert line.startswith("  >> [ok]")
        assert line.rstrip().endswith("s")


# -- end to end, through the real verify.py --------------------------------

_TRIVIAL_CHECK = '''\
"""A check that measures nothing, so the test measures the STREAM."""
from nixverify.contract import CheckResult, Status

DEPENDS_ON = ()
RESOURCES = ()


def run(mode, ctx):
    return CheckResult(name="", status=Status.PASS, evidence="constant")
'''


def _tiny_tree(tmp_path: Path, names: list[str]) -> Path:
    """A checks/ dir and registry holding `names`, runnable by the real engine."""
    checks = tmp_path / "checks"
    checks.mkdir()
    for name in names:
        (checks / f"{name}.py").write_text(_TRIVIAL_CHECK, encoding="utf-8")
    registry = checks / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "registry_version": "1.0.0",
                "blocks": [
                    {
                        "name": "level-0",
                        "parallel": False,
                        "on_fail": "continue",
                        "checks": names,
                        "claims": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry


def _run_verify(registry: Path, *extra: str) -> subprocess.CompletedProcess:
    """Invoke the REAL verify.py against a temp registry, output through a pipe."""
    return subprocess.run(  # nosec B603 - fixed argv, repo-local paths
        [
            sys.executable,
            str(VERIFY_PY),
            "--mode",
            "verify",
            "--registry",
            str(registry),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_stream_ADDS_lines_and_removes_none(tmp_path: Path) -> None:
    """`--stream` is additive: the §6 block is byte-identical with and without it.

    The strongest form of "nothing that parsed verify.py before parses
    differently now" — asserted against the real binary, not a reimplementation
    of what it is believed to print.
    """
    registry = _tiny_tree(tmp_path, ["check_alpha", "check_bravo"])
    plain = _run_verify(registry)
    streamed = _run_verify(registry, "--stream")
    assert plain.returncode == streamed.returncode

    stream_lines = [
        line for line in streamed.stdout.splitlines() if line.strip().startswith(">>")
    ]
    rest = [
        line
        for line in streamed.stdout.splitlines()
        if not line.strip().startswith(">>")
    ]
    assert len(stream_lines) == 2, streamed.stdout
    assert rest == plain.stdout.splitlines(), (
        "the end-of-run block changed when --stream was passed; it must not"
    )


def test_streamed_lines_all_precede_the_end_of_run_block(tmp_path: Path) -> None:
    """Live first, recap last — in the real process, through a real pipe."""
    registry = _tiny_tree(tmp_path, ["check_alpha", "check_bravo"])
    lines = _run_verify(registry, "--stream").stdout.splitlines()
    streamed = [i for i, line in enumerate(lines) if line.strip().startswith(">>")]
    block = [i for i, line in enumerate(lines) if "[ok]" in line and i not in streamed]
    assert streamed and block
    assert max(streamed) < min(block)


def test_without_stream_nothing_is_printed_before_the_block(tmp_path: Path) -> None:
    """The v1.2.0 behaviour is still available and still silent through a pipe."""
    registry = _tiny_tree(tmp_path, ["check_alpha"])
    out = _run_verify(registry).stdout
    assert ">>" not in out
