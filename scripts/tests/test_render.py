"""Output rendering per VERIFY-AND-CHECKS.md §12."""

import io

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
