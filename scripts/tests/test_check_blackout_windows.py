"""ARC 033 / Stage 1A — the can-fail suite for `checks/check_blackout_windows.py`.

**THE REQUIREMENT THIS FILE EXISTS TO SATISFY:** prove the gate actually
reddens on a real defect in EACH declared arm, and that each red NAMES THE
REASON — the site and the condition — never the exit code or the status alone
(check contract v2 rule 11 / §18).

**Every plant goes in the SUBJECT, on a COPY under `tmp_path`** (doctrine C.8).
No control edits an input: an evaluator handed a doctored window set would only
show that the gate can read a tuple, whereas a doctored EVALUATOR is the defect
the gate exists to catch. Every control below rewrites its own private copy of
`scripts/nixrisk/blackout.py` and drives the SHIPPED gate's own bytes against
it.

**THE TWO HEADLINE CONTROLS ARE OPPOSITES, on purpose:**
`test_an_evaluator_that_never_blocks_reddens` and
`test_an_evaluator_that_always_blocks_reddens`. Those are the two ways a
window rule can be worthless, they are invisible to each other, and a suite
that plants only one of them is a suite that certifies the other.
"""
# pylint: disable=redefined-outer-name,duplicate-code
# C0116 / R0903 disabled at module scope for the port DOUBLES below. Each is a
# stand-in carrying exactly the verbs its port declares; a docstring per
# one-line accessor, or a second method invented to clear a class-shape
# threshold, makes each double a worse stand-in for the thing it doubles --
# the reason `check_limiter_gate` records at the same disable. The TESTS
# themselves each carry a docstring naming the property they drive.
# pylint: disable=missing-function-docstring,too-few-public-methods

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - git ls-files, fixed argv, no shell
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

# pylint: disable=wrong-import-position
import check_blackout_windows as gate
from nixverify.contract import Context, Mode, Status
from nixverify.gitenv import scrubbed_env

# pylint: enable=wrong-import-position

SUBJECT = "scripts/nixrisk/blackout.py"


@pytest.fixture(scope="session")
def base_home(tmp_path_factory) -> Path:
    """One throwaway tree carrying every tracked file the SUBJECT needs.

    `scripts/nixrisk/` and `scripts/crucible/` only: `load_subject` imports the
    two packages out of `<nix_home>/scripts`, and the gate's own `nixverify`
    imports come from the real repository, so copying the rest would slow every
    session for nothing.
    """
    root = tmp_path_factory.mktemp("blackout-base")
    listing = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "ls-files", "--", "scripts/nixrisk", "scripts/crucible"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_env(),
        timeout=120,
    ).stdout.splitlines()
    for rel in listing:
        src = REPO / rel
        if not src.is_file():
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    return root


@pytest.fixture
def home(base_home: Path, tmp_path: Path) -> Path:
    """A private view of the base tree, safe to perturb.

    HARDLINKED, not copied: the vendored calendar is ~9 MB and every control
    needs its own tree. `_plant` unlinks before writing, so a perturbation
    breaks the link instead of editing the shared inode — `write_text` alone
    truncates in place and would corrupt the base for every later control.
    """
    target = tmp_path / "home"
    shutil.copytree(base_home, target, copy_function=os.link)
    return target


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(nix_home: Path, old: str, new: str, rel: str = SUBJECT) -> None:
    """Rewrite a COPIED file. Loud if the anchor moved or is ambiguous."""
    path = nix_home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{rel}: anchor appears {text.count(old)} times, not once — the plant "
        "would measure something other than what it names"
    )
    path.unlink()
    path.write_text(text.replace(old, new), encoding="utf-8")


def _red(result, *, site_contains: str, why_contains: str) -> None:
    """A red that NAMES the reason. Never the status alone (§18)."""
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL_NEEDS_OPERATOR, got {result.status!r}: "
        f"{result.detail or result.evidence}"
    )
    assert site_contains in (result.site or ""), (
        f"site {result.site!r} does not name {site_contains!r}"
    )
    blob = f"{result.evidence or ''} {result.detail or ''}"
    assert why_contains in blob, f"reason {blob!r} does not carry {why_contains!r}"


def _cannot(result, *, why_contains: str) -> None:
    assert result.status is Status.CANNOT_MEASURE, (
        f"expected CANNOT_MEASURE, got {result.status!r}: "
        f"{result.detail or result.evidence}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail {result.detail!r} does not carry {why_contains!r}"
    )


# ---------------------------------------------------------------------------
# The unplanted tree is GREEN — without this every red below is unattributable
# ---------------------------------------------------------------------------


def test_the_shipped_subject_passes(home: Path):
    """The control every plant is measured against."""
    result = _run(home)
    assert result.status is Status.PASS, result.detail or result.evidence
    assert "DENIED" in (result.evidence or "") and "PERMITTED" in (
        result.evidence or ""
    )


# ---------------------------------------------------------------------------
# The two opposite vacuity failures
# ---------------------------------------------------------------------------


NEVER = "active = [w for w in published.windows if w.start <= now < w.end]"


def test_an_evaluator_that_never_blocks_reddens(home: Path):
    """The headline plant: no window is ever active, so nothing is ever denied."""
    _plant(home, NEVER, "active = []")
    _red(
        _run(home),
        site_contains="§6.1 EOD",
        why_contains="and the evaluator permitted entry",
    )


def test_an_evaluator_that_always_blocks_reddens(home: Path):
    """The opposite failure, invisible to every inside drive."""
    _plant(home, NEVER, "active = list(published.windows)")
    _red(
        _run(home),
        site_contains="§6.1 EOD",
        why_contains="A rule that always blocks is not a blackout",
    )


# ---------------------------------------------------------------------------
# ARM B — the §6.2 union and its attribution
# ---------------------------------------------------------------------------


def test_the_narrow_window_winning_the_attribution_reddens(home: Path):
    """§6.2 says the WIDEST active leading edge wins. This plant picks the narrowest."""
    _plant(
        home,
        "binding = min(active, key=lambda w: (w.start, -w.end.timestamp()))",
        "binding = max(active, key=lambda w: (w.start, -w.end.timestamp()))",
    )
    _red(
        _run(home),
        site_contains="§6.2 EOW",
        why_contains="the WIDEST active leading edge win",
    )


def test_dropping_the_eow_window_entirely_reddens(home: Path):
    """No §6.2 window at all: the union has one side and the arm says so."""
    _plant(home, "if brk.klass == WEEKEND_BREAK_CLASS:", "if False:")
    _red(
        _run(home),
        site_contains="§6.2 EOW",
        why_contains="one window cannot show a union",
    )


# ---------------------------------------------------------------------------
# ARM C — §6.3's asymmetric edges
# ---------------------------------------------------------------------------


def test_a_missing_min_time_floor_reddens(home: Path):
    """Margin returns to baseline and the block lifts instantly — no '+ floor'."""
    _plant(
        home,
        "state.hold_until = now + timedelta(seconds=self._knobs.margin_min_hold_s)",
        "state.hold_until = now",
    )
    _red(
        _run(home),
        site_contains="§6.3",
        why_contains="released immediately",
    )


def test_a_permanent_lockout_reddens(home: Path):
    """No re-acceptance path: a broker hike locks the system out forever."""
    _plant(
        home,
        "if held >= self._knobs.margin_reacceptance_s:",
        "if held >= 1e18:",
    )
    _red(
        _run(home),
        site_contains="§6.3",
        why_contains="must never lock the system out forever",
    )


def test_a_silent_re_acceptance_reddens(home: Path):
    """The level is re-accepted and the operator is never told."""
    _plant(home, "if self._alert is not None:", "if False:")
    _red(
        _run(home),
        site_contains="§6.3",
        why_contains="re-accepted with no operator alert",
    )


def test_an_evaluator_blind_to_unscheduled_spikes_reddens(home: Path):
    """§6.3's reactive edge must fire with no calendar entry at all."""
    _plant(
        home,
        "        ceiling = baseline.level * (1.0 + self._knobs.margin_elevated_pct)",
        "        ceiling = baseline.level * 1e9",
    )
    _red(
        _run(home),
        site_contains="§6.3",
        why_contains="did not hold the trailing edge open",
    )


# ---------------------------------------------------------------------------
# ARM D — §3 onset
# ---------------------------------------------------------------------------


def test_an_onset_that_never_fires_reddens(home: Path):
    """§3: onset cancels pending entry orders. This one cancels nothing."""
    _plant(
        home,
        "        if entered and window is not None:\n"
        "            self._fire_onset(symbol, window, now)",
        "        if entered and window is None:\n"
        "            self._fire_onset(symbol, window, now)",
    )
    _red(
        _run(home),
        site_contains="_fire_onset",
        why_contains="exactly once per edge",
    )


def test_an_onset_booked_via_the_wrong_terminal_path_reddens(home: Path):
    """A second spelling of one release path puts the wrong cause in §9's record."""
    _plant(
        home,
        "    via: TerminalPath = TerminalPath.BLACKOUT_ONSET",
        "    via: TerminalPath = TerminalPath.CANCEL",
    )
    _red(
        _run(home),
        site_contains="_fire_onset",
        why_contains="record of money truth",
    )


def test_an_onset_that_releases_another_symbols_reservation_reddens(home: Path):
    """The blast radius is one symbol; §3's cancel is not a portfolio flatten."""
    _plant(home, "if reservation.symbol != symbol:", "if False:")
    _red(
        _run(home),
        site_contains="_fire_onset",
        why_contains="leave another symbol's",
    )


# ---------------------------------------------------------------------------
# ARM E — SPEC-A10's ratchet
# ---------------------------------------------------------------------------


ROSTER = 'CALENDAR_SOURCES: tuple[str, ...] = ("scripts/crucible/calendar_data",)'


def test_a_second_calendar_source_without_a_flagging_path_reddens(home: Path):
    """SPEC-A10's whole buildable claim, driven as a real future edit."""
    _plant(
        home,
        ROSTER,
        "CALENDAR_SOURCES: tuple[str, ...] = (\n"
        '    "scripts/crucible/calendar_data",\n'
        '    "scripts/crucible",\n'
        ")",
    )
    _red(
        _run(home),
        site_contains="CALENDAR_SOURCES",
        why_contains="never silently resolved",
    )


def test_a_second_source_with_a_flagging_call_is_accepted(home: Path):
    """The ratchet is over the FLAGGING PATH, not over the number of sources.

    Without this control the arm would be indistinguishable from `len(roster)
    == 1`, which forbids the change rather than governing it.
    """
    _plant(
        home,
        ROSTER,
        "CALENDAR_SOURCES: tuple[str, ...] = (\n"
        '    "scripts/crucible/calendar_data",\n'
        '    "scripts/crucible",\n'
        ")",
    )
    _plant(
        home,
        "        self._assert_vocabulary(symbol, group, target, classes)",
        "        self._assert_vocabulary(symbol, group, target, classes)\n"
        "        record_source_conflict(\n"
        "            field_name='windows',\n"
        "            live_value=len(out),\n"
        "            live_source=CALENDAR_SOURCES[0],\n"
        "            other_value=len(out),\n"
        "            other_source=CALENDAR_SOURCES[1],\n"
        "            at=day,\n"
        "        )",
    )
    assert _run(home).status is Status.PASS


def test_a_roster_naming_an_absent_path_reddens(home: Path):
    """A roster of literals is a comparison the ratchet cannot ride on."""
    _plant(home, ROSTER, 'CALENDAR_SOURCES: tuple[str, ...] = ("scripts/no_such_dir",)')
    _red(
        _run(home),
        site_contains="CALENDAR_SOURCES",
        why_contains="two literals",
    )


def test_deleting_the_flagging_path_reddens(home: Path):
    """Removing what the ratchet requires must not be a route to green."""
    _plant(home, "def record_source_conflict(", "def _retired_flagging_path(")
    _red(
        _run(home),
        site_contains="record_source_conflict",
        why_contains="is not defined",
    )


def test_an_empty_roster_is_cannot_measure_not_pass(home: Path):
    """Deleting the subject of an arm is unmeasured, never proven (§17)."""
    _plant(home, ROSTER, "CALENDAR_SOURCES: tuple[str, ...] = ()")
    _cannot(_run(home), why_contains="has nothing to judge")


# ---------------------------------------------------------------------------
# ARM F — §6.5's "new blackout types are DATA, not code"
# ---------------------------------------------------------------------------


def test_a_rule_branching_on_window_kind_reddens(home: Path):
    """calendar_seam.py: "if a future reader finds a rule switching on
    `WindowKind`, that rule is the defect"."""
    _plant(
        home,
        "        others = sorted(w.kind.value for w in active if w is not binding)",
        "        if binding.kind is WindowKind.EOD:\n"
        "            pass\n"
        "        others = sorted(w.kind.value for w in active if w is not binding)",
    )
    _red(
        _run(home),
        site_contains=SUBJECT,
        why_contains="new blackout types are DATA, not code",
    )


def test_removing_the_evaluator_class_is_cannot_measure(home: Path):
    """ARM F over an absent class is unmeasured, not clean."""
    _plant(home, "class BlackoutEvaluator:", "class _RetiredEvaluator:")
    _cannot(_run(home), why_contains="could not be exercised")


# ---------------------------------------------------------------------------
# §17 — an absent subject is never a PASS
# ---------------------------------------------------------------------------


def test_an_absent_subject_is_cannot_measure(home: Path):
    """A gate whose subject is gone has measured nothing."""
    (home / SUBJECT).unlink()
    _cannot(_run(home), why_contains="nothing to drive")


def test_an_unimportable_subject_is_cannot_measure(home: Path):
    """A syntax error is a lost subject, not a clean tree."""
    path = home / SUBJECT
    text = path.read_text(encoding="utf-8")
    path.unlink()
    path.write_text(text + "\nthis is not python\n", encoding="utf-8")
    _cannot(_run(home), why_contains="would not import")


def test_an_absent_calendar_is_cannot_measure(home: Path):
    """§17: the drive instants come from the calendar; without it, no drive."""
    shutil.rmtree(home / "scripts/crucible/calendar_data")
    _cannot(_run(home), why_contains="§17")
