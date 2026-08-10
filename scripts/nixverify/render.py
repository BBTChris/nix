"""Terminal rendering shared with install.sh's visual language (§12)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import IO

from nixverify.contract import CheckResult, Status

_UNICODE_GLYPHS = {
    Status.PASS: "✔",
    Status.FAIL_REPAIRABLE: "✖",
    Status.FAIL_NEEDS_OPERATOR: "✖",
    Status.CANNOT_MEASURE: "⚠",
    Status.SKIPPED: "·",
}
_ASCII_GLYPHS = {
    Status.PASS: "[ok]",
    Status.FAIL_REPAIRABLE: "[FAIL]",
    Status.FAIL_NEEDS_OPERATOR: "[FAIL]",
    Status.CANNOT_MEASURE: "[??]",
    Status.SKIPPED: "[--]",
}
_COLOURS = {
    Status.PASS: "\x1b[32m",
    Status.FAIL_REPAIRABLE: "\x1b[31m",
    Status.FAIL_NEEDS_OPERATOR: "\x1b[31m",
    Status.CANNOT_MEASURE: "\x1b[33m",
    Status.SKIPPED: "\x1b[90m",
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
    """Render every result in manifest order (§6)."""
    return "\n".join(_line(r, theme, verbose) for r in results)


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
    body = f" {theme.separator} ".join(segments)
    return f"\n  {body}{'':<10}exit {exit_code}"
