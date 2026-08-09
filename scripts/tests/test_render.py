"""Output rendering per VERIFY-AND-CHECKS.md §12."""

import io
import re

from nixverify.contract import CheckResult, Status
from nixverify.render import render_results, render_summary, theme_for


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_non_tty_gets_ascii_and_no_escape_codes() -> None:
    """§12: piping to a log must yield clean text."""
    theme = theme_for(io.StringIO(), {"LANG": "C.UTF-8"})
    assert theme.colour is False
    text = render_results([CheckResult("c", Status.PASS, evidence="e")], theme, False)
    assert "\x1b[" not in text
    assert "[ok]" in text


def test_no_colour_env_disables_colour_on_a_tty() -> None:
    """§12: NO_COLOR environment variable disables colour."""
    theme = theme_for(_Tty(), {"NO_COLOR": "1", "LANG": "C.UTF-8"})
    assert theme.colour is False


def test_non_utf8_lang_falls_back_to_ascii_glyphs() -> None:
    """§12: non-UTF-8 locale falls back to ASCII markers."""
    theme = theme_for(_Tty(), {"LANG": "C"})
    assert theme.unicode is False
    text = render_results([CheckResult("c", Status.PASS, evidence="e")], theme, False)
    assert "✔" not in text


def test_utf8_tty_gets_unicode_glyphs() -> None:
    """§12: UTF-8 TTY renders Unicode glyphs."""
    theme = theme_for(_Tty(), {"LANG": "en_US.UTF-8"})
    assert theme.unicode is True
    text = render_results([CheckResult("c", Status.PASS, evidence="e")], theme, False)
    assert "✔" in text


def test_failure_always_shows_its_site() -> None:
    """§5: the operator must see which setting is wrong, not a generic error."""
    theme = theme_for(io.StringIO(), {"LANG": "C"})
    result = CheckResult(
        "c", Status.FAIL_REPAIRABLE, site="jts.ini:ReadOnlyApi", detail="on"
    )
    assert "jts.ini:ReadOnlyApi" in render_results([result], theme, False)


def test_evidence_is_hidden_unless_verbose() -> None:
    """Evidence details are only shown in verbose mode."""
    theme = theme_for(io.StringIO(), {"LANG": "C"})
    result = CheckResult("c", Status.PASS, evidence="serverVersion=176")
    assert "serverVersion" not in render_results([result], theme, False)
    assert "serverVersion" in render_results([result], theme, True)


def test_upstream_advisory_is_shown_but_not_a_failure() -> None:
    """§7: newer upstream is information, never a defect."""
    theme = theme_for(io.StringIO(), {"LANG": "C"})
    result = CheckResult("c", Status.PASS, evidence="2.1.0", upstream_available="2.2.0")
    text = render_results([result], theme, False)
    assert "2.2.0" in text
    assert "[FAIL]" not in text


def test_summary_counts_each_state_and_shows_exit() -> None:
    """Summary reports counts per state and exit code."""
    theme = theme_for(io.StringIO(), {"LANG": "C"})
    results = [
        CheckResult("a", Status.PASS, evidence="e"),
        CheckResult("b", Status.FAIL_REPAIRABLE, site="s"),
        CheckResult("c", Status.CANNOT_MEASURE),
        CheckResult("d", Status.SKIPPED),
    ]
    text = render_summary(results, 1, theme)
    assert "1 passed" in text
    assert "1 failed" in text
    assert "1 cannot measure" in text
    assert "1 skipped" in text
    assert "exit 1" in text


def test_ascii_output_is_purity_encodable() -> None:
    """ASCII theme output must be ASCII-encodable (no mojibake in logs)."""
    theme = theme_for(io.StringIO(), {"LANG": "C"})
    results = [
        CheckResult(
            "check",
            Status.FAIL_REPAIRABLE,
            site="jts.ini:ReadOnlyApi",
            detail="on",
            evidence="1.2.3",
            action="restart",
            upstream_available="2.0.0",
        ),
    ]
    text = render_results(results, theme, True)
    text += render_summary(results, 1, theme)
    # Must not raise UnicodeEncodeError
    text.encode("ascii")


def test_lc_all_overrides_lang_for_utf8() -> None:
    """LC_ALL overrides LANG (POSIX precedence): LC_ALL=C with UTF-8 LANG → ASCII."""
    theme = theme_for(_Tty(), {"LC_ALL": "C", "LANG": "en_US.UTF-8"})
    assert theme.unicode is False


def test_lang_used_when_lc_all_not_set() -> None:
    """When LC_ALL is not set, LANG determines UTF-8 mode."""
    theme = theme_for(_Tty(), {"LANG": "en_US.UTF-8"})
    assert theme.unicode is True


def test_lc_all_utf8_overrides_lang_ascii() -> None:
    """LC_ALL=en_US.UTF-8 with LANG=C → Unicode (LC_ALL precedence)."""
    theme = theme_for(_Tty(), {"LC_ALL": "en_US.UTF-8", "LANG": "C"})
    assert theme.unicode is True


def test_summary_colours_failed_count_on_tty() -> None:
    """Failed count is coloured on a TTY when failures present."""
    theme = theme_for(_Tty(), {"LANG": "en_US.UTF-8"})
    results = [
        CheckResult("a", Status.PASS),
        CheckResult("b", Status.FAIL_REPAIRABLE, site="s"),
    ]
    text = render_summary(results, 1, theme)
    assert "\x1b[" in text  # Colour codes present
    assert "1 failed" in text


def test_summary_no_colour_on_non_tty() -> None:
    """Failed count is not coloured on a non-TTY even with failures."""
    theme = theme_for(io.StringIO(), {"LANG": "en_US.UTF-8"})
    results = [
        CheckResult("a", Status.PASS),
        CheckResult("b", Status.FAIL_REPAIRABLE, site="s"),
    ]
    text = render_summary(results, 1, theme)
    assert "\x1b[" not in text
    assert "1 failed" in text


def test_summary_no_colour_when_no_failures() -> None:
    """Failed count is not coloured when there are no failures (even on TTY)."""
    theme = theme_for(_Tty(), {"LANG": "en_US.UTF-8"})
    results = [CheckResult("a", Status.PASS)]
    text = render_summary(results, 0, theme)
    # "0 failed" should not be coloured
    assert "0 failed" in text
    # The colour code should not appear for the failed segment
    # Check that there's no colour code immediately around "failed"
    assert not re.search(r"\x1b\[.*0 failed", text)
