"""Terminal rendering shared with install.sh's visual language (§12)."""

from __future__ import annotations

import dataclasses
import threading
import time
from collections.abc import Mapping
from typing import IO

from nixverify.contract import CheckResult, Status

#: Truncation width for the one-line progress surface. A fixed cap rather than a
#: terminal query: `COLUMNS` is not set in every runner and a failed query would
#: have to fall back to a constant anyway. Over-long lines wrap and scroll, which
#: is the one thing an in-place repaint must not do.
_MAX_PROGRESS_WIDTH = 110

#: Per-check `EXPECTED_S` hints, populated by `verify.py` from the loaded check
#: modules. Empty by default so the spinner degrades to a bare count-up, which is
#: the correct rendering for a check that declares nothing.
_EXPECTED: dict[str, float] = {}


def set_expected_durations(expected: Mapping[str, float]) -> None:
    """Install the per-check `EXPECTED_S` hints for the progress surface.

    Separate from construction because the durations are read off the check
    modules by the loader, which happens inside the engine, while the progress
    surface is built by `main()` before the engine runs.
    """
    _EXPECTED.clear()
    _EXPECTED.update(expected)


_UNICODE_GLYPHS = {
    Status.PASS: "✔",
    Status.FAIL_REPAIRABLE: "✖",
    Status.FAIL_NEEDS_OPERATOR: "✖",
    Status.CANNOT_MEASURE: "⚠",
    Status.SKIPPED: "·",
    Status.GUARDED: "◐",
}
_ASCII_GLYPHS = {
    Status.PASS: "[ok]",
    Status.FAIL_REPAIRABLE: "[FAIL]",
    Status.FAIL_NEEDS_OPERATOR: "[FAIL]",
    Status.CANNOT_MEASURE: "[??]",
    Status.SKIPPED: "[--]",
    Status.GUARDED: "[GRD]",
}
# ARC 024 operator ruling: red = Failed, yellow = Guarded, green = Passed,
# light blue = "cannot run or check".
#
# **Yellow was already occupied and this is a RECOLOUR, not an addition.**
# CANNOT_MEASURE was yellow up to ARC 023; the ruling moves it to light blue and
# gives yellow to GUARDED. Light blue covers BOTH cannot-run (SKIPPED) and
# cannot-check (CANNOT_MEASURE), which is exactly what the ruling's phrasing
# names, so SKIPPED loses its distinct grey.
#
# **No information is lost by that merge, and that was checked rather than
# assumed:** the two states already share exit code 2 (§4.2), and they keep
# distinct GLYPHS in both glyph sets (`·`/`⚠`, `[--]`/`[??]`). Colour is
# redundant with the glyph here, so collapsing it degrades no instrument — and
# the glyph, unlike the colour, survives a pipe.
_COLOURS = {
    Status.PASS: "\x1b[32m",
    Status.FAIL_REPAIRABLE: "\x1b[31m",
    Status.FAIL_NEEDS_OPERATOR: "\x1b[31m",
    Status.CANNOT_MEASURE: "\x1b[94m",
    Status.SKIPPED: "\x1b[94m",
    Status.GUARDED: "\x1b[33m",
}
_RESET = "\x1b[0m"


@dataclasses.dataclass(frozen=True)
class Theme:
    """How much the destination stream can render (§12 degradation)."""

    colour: bool
    unicode: bool

    def glyph(self, status: Status) -> str:
        """Status marker, widened so labels align in both glyph sets."""
        table = _UNICODE_GLYPHS if self.unicode else _ASCII_GLYPHS
        return table[status].ljust(6 if not self.unicode else 2)

    def paint(self, status: Status, text: str) -> str:
        """Colour text if the stream supports it."""
        if not self.colour:
            return text
        return f"{_COLOURS[status]}{text}{_RESET}"

    @property
    def detail_sep(self) -> str:
        """Separator between site and detail (em dash for Unicode, hyphen for ASCII)."""
        return "—" if self.unicode else "-"

    @property
    def separator(self) -> str:
        """Separator for summary segments (middle dot for Unicode, pipe for ASCII)."""
        return "·" if self.unicode else "|"


def theme_for(stream: IO[str], env: Mapping[str, str]) -> Theme:
    """Degrade for pipes, NO_COLOR, and non-UTF-8 locales."""
    tty = bool(getattr(stream, "isatty", lambda: False)())
    colour = tty and "NO_COLOR" not in env
    lang = (env.get("LC_ALL") or env.get("LANG") or "").upper()
    return Theme(colour=colour, unicode=tty and "UTF-8" in lang)


def _line(result: CheckResult, theme: Theme, verbose: bool) -> str:
    """One result line. Failures always carry their site (§5)."""
    marker = theme.paint(result.status, theme.glyph(result.status))
    parts = [f"  {marker} {result.name:<22}"]
    if result.site:
        parts.append(result.site)
    if result.detail:
        parts.append(
            f"{theme.detail_sep} {result.detail}" if result.site else result.detail
        )
    if result.upstream_available:
        parts.append(f"(upstream {result.upstream_available} available)")
    if result.action:
        parts.append(f"[{result.action}]")
    if verbose and result.evidence:
        parts.append(f"{theme.separator} {result.evidence}")
    return " ".join(parts).rstrip()


def render_results(results: list[CheckResult], theme: Theme, verbose: bool) -> str:
    """Render every result in registry order (§6)."""
    return "\n".join(_line(r, theme, verbose) for r in results)


class LiveProgress:  # pylint: disable=too-many-instance-attributes
    """The progress surface. Terminal only — it can never reach Plane 2.

    ## Why this exists at all

    Up to ARC 023 `verify.py` printed **nothing** until the whole run finished:
    `main()` called `run_blocks()` and only then `print(render_results(...))`.
    Measured on the ARC 023 tree, all thirteen result lines arrived within 32 ms
    at the end of a multi-second run. There was no progress surface to add
    colours or spinners to, so this class is the surface, not a decoration on
    one.

    ## Determinate vs indeterminate (operator ruling 4.2), and the honest part

    The ruling is: time-bound event => text progress indicator; non-deterministic
    duration => spinner with a count-up clock. Rule 4.3 adds that which-is-which
    is *declared*, and the standing check-script rule forbids anchoring an
    expected duration to a moving value.

    **Those two rules together rule out the obvious implementation, and saying so
    is the point.** A per-check progress bar needs a denominator. The only
    denominators available are (a) last run's timing — forbidden, it is exactly
    the moving anchor §7.4 names, and a bar calibrated on it silently becomes
    wrong — or (b) a hand-typed constant, which is a restated mutable fact under
    `CLAUDE.md` directive 3 and rots the first time the check changes.

    So the two indicators are anchored differently and only one of them claims
    to be a measurement:

    - **The run-level indicator is DERIVED and real.** `n/total` counts checks
      completed against the total the registry declares. Both halves come from
      the registry, nothing is typed, and it cannot drift: add a check and the
      denominator moves in the same motion.
    - **The per-check indicator is a spinner with a count-up clock, and it
      measures elapsed time only** — never predicted remaining time. A check may
      declare `EXPECTED_S`, and where it does the clock shows `4.1s/~8.0s` — but
      `EXPECTED_S` is required to be **derived from a constant already in the
      check's own code** (its subprocess timeout, say), never from an observed
      duration. It is a hint rendered beside a real elapsed count, and it is
      never the thing being counted.

    Net effect: nothing on this surface is a prediction dressed as a measurement.

    ## Degradation

    Non-TTY => this class emits nothing at all. Not "no colour" — nothing. The
    plain sequential result block that `render_results` already produced is the
    entire non-TTY output, byte-identical to the pre-ARC-024 behaviour.
    """

    #: Braille spinner. Falls back to ASCII when the stream is not UTF-8.
    _UNICODE_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _ASCII_FRAMES = "|/-\\"

    def __init__(self, stream: IO[str], theme: Theme, total: int) -> None:
        self._stream = stream
        self._theme = theme
        self._total = total
        self._done = 0
        self._lock = threading.Lock()
        self._active: dict[str, float] = {}
        self._tick = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # The single gate on every write. `theme.colour` is already
        # `isatty() and NO_COLOR unset`, so a redirect, a pipe, a systemd unit
        # and NO_COLOR all land here as False and this surface stays silent.
        self._live = theme.colour

    def _frames(self) -> str:
        """Spinner alphabet the destination stream can actually render."""
        return self._UNICODE_FRAMES if self._theme.unicode else self._ASCII_FRAMES

    def start(self) -> None:
        """Begin animating. No-op on a non-TTY."""
        if not self._live:
            return
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _animate(self) -> None:
        """Repaint ~10x/second until stopped."""
        while not self._stop.wait(0.1):
            with self._lock:
                self._paint()

    def _paint(self) -> None:
        """Write one frame. Caller holds the lock."""
        frames = self._frames()
        self._tick += 1
        spin = frames[self._tick % len(frames)]
        running = ", ".join(
            f"{name} {time.perf_counter() - began:.1f}s"
            + (f"/~{_EXPECTED.get(name):.1f}s" if _EXPECTED.get(name) else "")
            for name, began in sorted(self._active.items())
        )
        counter = f"{self._done}/{self._total}"
        line = f"  {spin} {counter} {running}" if running else f"  {spin} {counter}"
        # \r + clear-to-end-of-line: one line, rewritten in place, never scrolled.
        self._stream.write(f"\r\x1b[2K{line[:_MAX_PROGRESS_WIDTH]}")
        self._stream.flush()

    def _erase(self) -> None:
        """Clear the progress line so result output starts clean."""
        self._stream.write("\r\x1b[2K")
        self._stream.flush()

    # -- Observer protocol (engine.Observer) --------------------------------

    def check_start(self, name: str) -> None:
        """Engine hook. Thread-safe: parallel blocks call this concurrently."""
        if not self._live:
            return
        with self._lock:
            self._active[name] = time.perf_counter()

    def check_verdict(self, result: CheckResult) -> None:
        """Engine hook. Thread-safe."""
        if not self._live:
            return
        with self._lock:
            self._active.pop(result.name, None)
            self._done += 1

    def stop(self) -> None:
        """Stop animating and clear the line. Idempotent."""
        if not self._live:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            self._erase()


class StreamProgress:
    """One line per verdict, printed the moment the verdict lands (`--stream`).

    ## Why this exists alongside `LiveProgress`

    `LiveProgress` is a TTY-only, in-place repaint: it writes `\\r` + clear-line
    and keeps ONE line on screen. That is the right surface for an operator
    watching a terminal, and the wrong one for anything reading verify.py through
    a pipe — `theme.colour` is `isatty()`, so a pipe silences it completely, and
    the only output a pipe ever saw was the final block after the last check.

    `nix_status.sh` is exactly that reader. It captured a run and could not show
    a single verdict until the whole run finished. This class is the pipe-facing
    half of the same fact: append-only, one flushed line per completed check,
    identical whether the destination is a terminal or a FIFO.

    ## What is measured and what is merely counted

    - `result.duration_s` is stamped by `engine._timed` off `perf_counter`. It is
      a MEASUREMENT of the check that just ran, not an estimate, and nothing here
      recomputes it — this class formats a number the engine already produced.
    - `n/total` counts completed checks against the registry's own total, the
      same derived denominator `LiveProgress` uses. Add a check and the
      denominator moves in the same motion; nothing is typed.

    No remaining-time prediction appears here, for the reason `LiveProgress`
    documents at length: the only available denominators for one would be last
    run's timing (a moving anchor, §7.4) or a hand-typed constant (a restated
    mutable fact, directive 3).

    ## The `>>` sentinel, and why the final block is left alone

    Every line starts with `>>`, a token `render_results` never emits. That keeps
    the streamed lines and the end-of-run registry-order block (§6) mutually
    unambiguous in one stream: a consumer that wants live output reads `>>`
    lines, a consumer that wants the ordered block reads what it always read, and
    neither has to know about the other. `--stream` therefore ADDS output and
    removes none — nothing that parsed verify.py before parses differently now.
    """

    #: Name column width. Matches `_line()`'s 22 plus room for the longer
    #: `check_*` names, so live lines and the final block read as one column.
    _NAME_W = 30

    def __init__(self, stream: IO[str], theme: Theme, total: int) -> None:
        self._stream = stream
        self._theme = theme
        self._total = total
        self._done = 0
        # Parallel blocks call `check_verdict` from worker threads. The lock
        # covers the counter increment AND the write, so two verdicts landing
        # together can neither share a number nor interleave mid-line.
        self._lock = threading.Lock()

    def start(self) -> None:
        """No-op. Nothing is animated; there is no thread to start."""

    def check_start(self, name: str) -> None:
        """No-op. A started check has no verdict yet, and only verdicts print.

        Deliberate: announcing starts as well would double the line count and,
        in a parallel block, interleave starts and verdicts into an order that
        reads as though checks finished in an order they did not.
        """

    def check_verdict(self, result: CheckResult) -> None:
        """Print this verdict now. Flushed, because a pipe is block-buffered.

        The flush is the entire feature. Python buffers stdout in ~8 KiB blocks
        when it is not a TTY, so an unflushed write would sit in userspace until
        the run ended — reproducing, through a pipe, precisely the batch-at-the-
        end behaviour this class exists to remove.
        """
        with self._lock:
            self._done += 1
            done = self._done
            marker = self._theme.paint(result.status, self._theme.glyph(result.status))
            counter = f"{done}/{self._total}"
            self._stream.write(
                f"  >> {marker} {result.name:<{self._NAME_W}} "
                f"{counter:>7}  {result.duration_s:6.2f}s\n"
            )
            self._stream.flush()

    def stop(self) -> None:
        """No-op. Nothing was left half-painted; every line ended in a newline."""


def render_summary(results: list[CheckResult], exit_code: int, theme: Theme) -> str:
    """Counts per state plus the process exit code."""
    counts = {status: 0 for status in Status}
    for result in results:
        counts[result.status] += 1
    failed = counts[Status.FAIL_REPAIRABLE] + counts[Status.FAIL_NEEDS_OPERATOR]
    failed_text = f"{failed} failed"
    if failed > 0:
        # Paint with whichever failure status is actually present, rather
        # than hardcoding FAIL_REPAIRABLE's colour — a run with only
        # FAIL_NEEDS_OPERATOR results must not be painted as though a
        # repairable failure occurred.
        failure_status = (
            Status.FAIL_REPAIRABLE
            if counts[Status.FAIL_REPAIRABLE] > 0
            else Status.FAIL_NEEDS_OPERATOR
        )
        failed_text = theme.paint(failure_status, failed_text)
    segments = [
        f"{counts[Status.PASS]} passed",
        failed_text,
        f"{counts[Status.CANNOT_MEASURE]} cannot measure",
        f"{counts[Status.SKIPPED]} skipped",
    ]
    # AMENDMENT 1 (ARC 024). Appended, and only when non-zero — the triple this
    # project quotes in every arc close-out ("10 passed | 1 failed | 1 cannot
    # measure") is a banked figure, and silently widening it on every run would
    # make ARC 024's summary line incomparable with ARC 023's for no reason. A
    # guarded verdict is loud when it exists and invisible when it does not.
    if counts[Status.GUARDED]:
        segments.append(
            theme.paint(Status.GUARDED, f"{counts[Status.GUARDED]} guarded")
        )
    body = f" {theme.separator} ".join(segments)
    return f"\n  {body}{'':<10}exit {exit_code}"
