#!/usr/bin/env python3
"""Gate: the §6.1-6.3 blackout evaluator DENIES INSIDE its windows and PERMITS
OUTSIDE them, on the live vendored calendar -- and the calendar-source roster
cannot grow a second member without a flagging path (SPEC-A10).

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *entry is
denied exactly while `now` is inside a published window or margin is elevated,
and the denial names which.* No instrument in this tree owned it.
`check_limiter_gate` measures the EXECUTOR that dispatches the rule and says so
in its own docstring -- *"Whether `blackout_window`'s cache is ever populated
with a real calendar is out of this arc entirely and out of this gate."* This
gate's subject is the thing that populates it.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless a document is
named on the same line.

------------------------------------------------------------------------------
WHY EVERY ARM DRIVES `now` TO BOTH SIDES OF EVERY EDGE
------------------------------------------------------------------------------
An evaluator that always answers "not blocked" satisfies every OUTSIDE drive
and every assertion about a clear market. An evaluator that always answers
"blocked" satisfies every INSIDE drive. **Either one alone is a gate that
measures nothing**, and the two failures are opposite, so no single-sided suite
can see both. Each arm therefore drives at least one instant genuinely inside
the window and one genuinely outside it, and the floors below require BOTH
populations to be non-empty before any verdict is issued.

The instants are not typed here. They are DERIVED from the vendored calendar --
`crucible.calendar` is asked for a real weekend break and a real daily break for
a real symbol -- so a regenerated artifact moves the drives with it rather than
reddening a correct tree (doctrine C.4: floors, not today's numbers; the same
argument applied to dates).

------------------------------------------------------------------------------
ARMS
------------------------------------------------------------------------------
  ARM A  §6.1 EOD. Inside `[close - EOD_BLACKOUT_MIN, next open)` denies and
         names the window; one second before the lead, and at the re-open
         instant itself, permit. The half-open interval is measured, not
         assumed.
  ARM B  §6.2 EOW UNION. On a real Friday the EOD and EOW windows OVERLAP and
         the EOW leading edge is wider. Three drives: an instant only the wide
         window covers (blocked), the SAME instant against a set from which the
         wide window has been removed (permitted -- one window cannot show a
         union), and an instant both cover (blocked, attributed to EOW).
  ARM C  §6.3 ASYMMETRIC EDGES. Leading edge by clock; margin spikes; margin
         RETURNS to baseline and is still held by the min-time floor; the floor
         expires and entry is permitted; an unscheduled spike with no window at
         all denies; and margin held elevated PAST the re-acceptance period is
         re-accepted, alerts the operator, and unlocks.
  ARM D  §3 ONSET. The clear -> in-window transition releases the symbol's
         reservations via `TerminalPath.BLACKOUT_ONSET` -- the FROZEN seam's own
         member -- exactly once, and leaves another symbol's reservation alone.
  ARM E  SPEC-A10. `CALENDAR_SOURCES` is read STATICALLY off the subject's
         bytes. One member today; more than one requires a static call to the
         flagging path, and the flagging path must exist either way.
  ARM F  §6.5's "new blackout types are DATA, not code". No decision path in
         `BlackoutEvaluator` branches on `WindowKind` or compares `.kind`.

## EXIT / STATUS CONTRACT (nix_check_contract.md §4.2)
  PASS (0)            every arm clean and every non-vacuity floor met
  FAIL (1)            a measured violation, sited and named
  CANNOT_MEASURE (2)  a subject is absent, unimportable, or a floor is unmet
                      -- never PASS (§17)

------------------------------------------------------------------------------
debug.md §7.12 -- THE STANDING QUESTION: how could this gate be GREEN while the
property is FALSE?
------------------------------------------------------------------------------
(Deliberately NOT labelled with the arc-brief section number that asked for it:
check contract v2 rule 13 -- arc-brief labels are per-arc, collide across arcs,
and are not identifiers. `check_spec_citations` enforces that mechanically.)

1. **Every drive could land OUTSIDE the window.** A suite whose `now` never
   enters a window sees "not blocked" everywhere and reports PASS over an
   evaluator that cannot deny at all. *Closed:* `FLOORS["blocked_drives"]` and
   `FLOORS["permitted_drives"]` are BOTH non-zero, so a run in which nothing
   was denied and a run in which nothing was permitted are each CANNOT_MEASURE.
   Every drive is counted on the side it actually landed, not on the side it
   was intended to land.

2. **The window set could be empty**, so `now ∈ any window` is trivially false
   and the OUTSIDE drives all pass. *Closed:* ARM A and ARM B assert the
   generated set's SHAPE before driving it -- an EOD window and an EOW window
   with the wider EOW lead -- and `FLOORS["windows_generated"]` refuses a set
   below three windows across the driven symbols.

3. **The union could be shown with one window.** A single window covering the
   instant "proves" a union the same way one number proves an average.
   *Closed:* ARM B asserts the OVERLAP as a premise (two windows, distinct
   starts, common end), then drives the instant that only the wider one covers,
   then REMOVES the wider one from a copy of the published set and requires the
   verdict to FLIP. The flip is the union; the single blocked drive is not.

4. **The margin arm could be driven with margin that never returns.** A test
   that spikes margin and never restores it proves the block but not the
   release, and a rule that never releases is a permanent lockout that looks
   identical. *Closed:* ARM C drives margin back TO the baseline and asserts
   the block persists (floor), then past the floor and asserts it lifts; and it
   separately holds margin elevated past the re-acceptance period and asserts
   the lockout breaks WITH an operator alert.

5. **The gate could import the subject from the wrong tree.** A gate that
   imports `nixrisk.blackout` through the ambient `sys.path` measures whichever
   tree imported first, and a plant under `tmp_path` would never load.
   *Closed:* `load_subject` prefixes `<nix_home>/scripts`, purges `nixrisk*`
   and `crucible*` from `sys.modules` first and restores both afterwards -- the
   same mechanism, and the same declared `interpreter:` resources, as
   `check_limiter_gate`.

6. **The static arms could be satisfied by deleting the thing they judge.** ARM
   E would pass over a module with no `CALENDAR_SOURCES` (nothing to compare)
   and ARM F over a module with no `BlackoutEvaluator` (nothing to scan).
   *Closed:* both arms report CANNOT_MEASURE when their subject is absent, and
   ARM E additionally requires the flagging function to be DEFINED, so removing
   it is a finding rather than a route to green.

7. **The roster could name paths that do not exist**, making ARM E a comparison
   between two literals. *Closed:* every entry in `CALENDAR_SOURCES` is
   resolved against the tree under measurement, and an entry that is not on
   disk is a FAIL naming it.

------------------------------------------------------------------------------
C.9 -- WHAT THIS GATE DELIBERATELY DOES NOT MEASURE
------------------------------------------------------------------------------
`check_limiter_gate` owns the executor's phase ordering, its denial naming and
its O(1) claim. `check_calendar_schema` owns the calendar artifact's UTC
canonicity, its provenance chain, its per-symbol keying and the local-time read
ban -- and ARM F here is NOT a second copy of that gate's ARM B: that one bans
reading a stored local-time COLUMN anywhere in the tree, this one bans a rule
branching on a window KIND inside one class. Different subject, different
failure. `check_risks_data_only` owns the knobs as data. None is repeated here.

**Not measured by anything yet, and stated so no green implies it:** that the
window set is ever published by a live poller (§6.4 -- there is no poller), that
a scheduled econ event ever arrives (there is no econ-event artifact), that a
broker order is cancelled at the venue on onset (execution is not wired), and
that §6.1b's session-close flatten fires. Those are other agents' and other
arcs'.

## NON-CORRECTABLE
The measured side is the behaviour of a rule module and the reference side is
§6 of a frozen spec. An instrument empowered to edit the evaluator into
agreement would be authoring the subject it certifies -- the objection
`check_limiter_gate` records in the same words.
"""

from __future__ import annotations

# C0302 (too-many-lines) disabled for the reason `check_limiter_gate` and
# `check_calendar_schema` both record: `nix_check_contract.md` §4.2 requires
# every checks/check_*.py be INDEPENDENTLY RUNNABLE, so the port doubles that
# make these arms drives rather than assertions cannot move to a helper module.
# pylint: disable=too-many-lines
# R0801 (duplicate-code) disabled at module scope: §4.2 MANDATES that the
# standalone block and the status/exit mapping be identical across every gate.
# pylint: disable=duplicate-code
# R0903 (too-few-public-methods) disabled at module scope: every class below is
# a PORT DOUBLE carrying exactly the port's own verbs. A second method invented
# to clear a threshold makes each double a worse stand-in for what it doubles.
# pylint: disable=too-few-public-methods
import ast
import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported; §4.4) ---
#: Nothing must run first. The subject is a stdlib-only module in this tree,
#: imported by path rather than through the venv.
DEPENDS_ON: tuple[str, ...] = ()
#: The subject is loaded by prefixing `<nix_home>/scripts` onto `sys.path` and
#: purging any already-imported `nixrisk*` / `crucible*` so the modules come
#: from the tree under measurement. Both are restored afterwards, and both are
#: DECLARED: check contract v2 rule 12 checks declared claims against observed
#: ones, so an undeclared interpreter mutation here would be a finding against
#: this gate. No socket, no subprocess, no write of any kind.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is §6 of the frozen risk spec, which is never edited, "
    "and the measured side is the behaviour of the blackout evaluator. An "
    "instrument that could rewrite the evaluator to agree with the spec would "
    "be authoring the subject it certifies -- the objection check_limiter_gate "
    "records in the same words."
)
#: Genuinely DRIVEN, not merely named: every arm constructs objects from this
#: module and executes `BlackoutEvaluator.read`.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/blackout.py",)

NAME = "check_blackout_windows"

REL_SUBJECT = "scripts/nixrisk/blackout.py"
EVALUATOR_CLASS = "BlackoutEvaluator"
ROSTER_CONST = "CALENDAR_SOURCES"
FLAGGING_FUNC = "record_source_conflict"

#: NON-VACUITY FLOORS (doctrine C.4). Every one is a FLOOR, not today's count.
#: The first two are the ones that matter: a suite in which nothing was denied,
#: and a suite in which nothing was permitted, are the two opposite ways this
#: gate could pass over an evaluator that decides nothing.
FLOORS = {
    "blocked_drives": 8,
    "permitted_drives": 6,
    #: distinct window kinds actually driven to a BLOCK (eod, eow, news_margin)
    "window_kinds_driven": 3,
    #: windows generated across the driven symbols
    "windows_generated": 3,
    #: symbols driven, so a per-symbol keying bug cannot hide behind one symbol
    "symbols_driven": 2,
    #: break rows the vendored calendar must carry FOR THE DRIVEN PRODUCT GROUP
    #: before its dates are trusted as a source of drive instants. Measured
    #: 5,944 for equity_index (35,478 across the six groups); a floor of 3,000
    #: cannot be met by a truncated artifact and does not move when a
    #: regeneration adds or drops an early close.
    "calendar_break_rows": 3_000,
    #: entries in the SPEC-A10 roster. One today; zero means nothing to judge.
    "calendar_sources": 1,
}

#: How far the date search walks looking for a real weekend break and a real
#: daily break. Two calendar weeks is generous for a market that closes every
#: weekday and every weekend; a wider sweep would hide a calendar that had lost
#: most of its rows, which `calendar_break_rows` is there to catch anyway.
SEARCH_DAYS = 14


class Finding(NamedTuple):
    """One divergence. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


def _fail(findings: list[Finding]) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(f.site for f in findings),
        evidence=f"{len(findings)} violation(s): " + "; ".join(f.why for f in findings),
        detail=" | ".join(f"{f.site}: {f.why}" for f in findings),
    )


def _cannot(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ---------------------------------------------------------------------------
# Loading the subject FROM THE TREE UNDER MEASUREMENT
# ---------------------------------------------------------------------------


class _Subject:
    """The four modules of ONE tree. Typed `Any` for `check_limiter_gate`'s
    reason: the whole point is that the tree is chosen at run time, so a static
    type here would be a claim about WHICH tree was loaded."""

    def __init__(self, blackout: Any, seam: Any, cal_seam: Any, calendar: Any) -> None:
        self.blackout = blackout
        self.seam = seam
        self.cal_seam = cal_seam
        self.calendar = calendar


_PREFIXES = ("nixrisk", "crucible")


def _purge() -> dict[str, Any]:
    """Remove and return every cached module from the packages under test."""
    saved = {
        key: value
        for key, value in sys.modules.items()
        if key.split(".")[0] in _PREFIXES
    }
    for key in saved:
        del sys.modules[key]
    return saved


def load_subject(home: Path) -> tuple[_Subject | None, str]:
    """Import the subject from `home`. Returns `(subject, complaint)`.

    `sys.modules` is purged of both packages before and restored after: a check
    that ran once against the repo would otherwise hand back the repo's module
    for every subsequent tree, and a plant that is never loaded is a plant that
    cannot fail.
    """
    scripts = home / "scripts"
    if not (scripts / "nixrisk" / "blackout.py").is_file():
        return None, f"{REL_SUBJECT} is not on disk under {home} -- nothing to drive"
    saved_path = list(sys.path)
    saved_mods = _purge()
    sys.path.insert(0, str(scripts.resolve()))
    try:
        seam = importlib.import_module("nixrisk.seam")
        cal_seam = importlib.import_module("nixrisk.calendar_seam")
        blackout = importlib.import_module("nixrisk.blackout")
        calendar = importlib.import_module("crucible.calendar")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{REL_SUBJECT} would not import from {home}: {type(exc).__name__}: {exc}"
        )
    finally:
        _purge()
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path
    return _Subject(blackout, seam, cal_seam, calendar), ""


# ---------------------------------------------------------------------------
# The driven population -- port doubles carrying exactly the ports' verbs
# ---------------------------------------------------------------------------


class _Clock:
    """A settable UTC clock. `now` is DRIVEN; nothing reads the wall clock."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        """The instant the evaluator will see as `now`."""
        return self.at


class _WindowCache:
    """`WindowSetReadPort` over one mutable per-symbol map."""

    def __init__(self, cal_seam: Any) -> None:
        self._cal_seam = cal_seam
        self.sets: dict[str, Any] = {}

    def windows(self, symbol: str) -> Any:
        """The published set for `symbol`, or None."""
        return self.sets.get(symbol)

    def state(self) -> Any:
        """FRESH: staleness is `check_calendar_schema`'s and the poller's."""
        return self._cal_seam.CacheState.FRESH

    def freshness(self) -> Any:
        """No stamp: the evaluator reads state, not the stamp."""
        return None


class _BaselineCache:
    """`MarginBaselineReadPort` over one mutable per-symbol map."""

    def __init__(self, cal_seam: Any) -> None:
        self._cal_seam = cal_seam
        self.levels: dict[str, Any] = {}

    def baseline(self, symbol: str) -> Any:
        """The accepted baseline for `symbol`, or None."""
        return self.levels.get(symbol)

    def state(self) -> Any:
        """FRESH, for the reason the window cache gives."""
        return self._cal_seam.CacheState.FRESH

    def freshness(self) -> Any:
        """No stamp; see the window cache."""
        return None


class _Picture:
    """`FinancialPicturePort` over one mutable per-symbol margin mapping."""

    def __init__(self, seam: Any) -> None:
        self._seam = seam
        self.margin: dict[str, float] = {}

    def publish(self, picture: Any) -> None:
        """§6.4 makes the Limiter a READER. A publish here is a defect."""
        raise AssertionError("the evaluator must never publish (§6.4 read-only)")

    def current(self) -> Any:
        """One §3 snapshot carrying the per-symbol margin under drive."""
        return self._seam.FinancialPicture(
            version=1,
            published_ts=0.0,
            balance=100_000.0,
            positions=(),
            margin_per_contract=dict(self.margin),
            sum_open_margin=0.0,
            sum_reservations=0.0,
            committed=0.0,
            deployable=70_000.0,
        )


class _Alerts:
    """`AlertSink`, recording."""

    def __init__(self) -> None:
        self.raised: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        """Record one operator alert."""
        self.raised.append((code, message))


class _Onsets:
    """`OnsetSink`, recording."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    def on_blackout_onset(self, onset: Any) -> None:
        """Record one §3 onset."""
        self.seen.append(onset)


class _Ledger:
    """`ReservationLedgerPort`, enough of it to observe a release."""

    def __init__(self, seam: Any) -> None:
        self._seam = seam
        self.rows: list[Any] = []
        self.released: list[tuple[str, Any]] = []

    def take(self, order: Any, now: float) -> Any:
        """§3's take is the gate's, never a blackout rule's."""
        raise AssertionError("the evaluator must never take a reservation")

    def release(self, reservation_id: str, via: Any, now: float) -> None:
        """Record which id was released and under which `TerminalPath`."""
        del now
        self.released.append((reservation_id, via))
        self.rows = [r for r in self.rows if r.reservation_id != reservation_id]

    def outstanding(self) -> tuple[Any, ...]:
        """Every reservation currently TAKEN."""
        return tuple(self.rows)

    def total_reserved(self) -> float:
        """§11.3's running aggregate over the TAKEN set."""
        return sum(r.margin for r in self.rows)


@dataclass
class _Rig:  # pylint: disable=too-many-instance-attributes
    """One wired evaluator plus every double it reads.

    Eight fields because §6.4 keeps these caches separate and the evaluator
    takes them separately; bundling them to satisfy a counter would hide which
    double a drive perturbed.
    """

    evaluator: Any
    clock: _Clock
    windows: _WindowCache
    baselines: _BaselineCache
    picture: _Picture
    alerts: _Alerts
    onsets: _Onsets
    ledger: _Ledger


@dataclass
class _Tally:
    """Both sides of every drive, counted where they LANDED."""

    blocked: int = 0
    permitted: int = 0
    kinds: set[str] = field(default_factory=set)
    windows: int = 0
    symbols: set[str] = field(default_factory=set)

    def record(self, symbol: str, blocked: bool, reason: str) -> None:
        """Count one drive on the side it actually landed on."""
        self.symbols.add(symbol)
        if blocked:
            self.blocked += 1
        else:
            self.permitted += 1
        for kind in ("eod", "eow", "news_margin"):
            if blocked and f"inside the {kind} window" in reason:
                self.kinds.add(kind)


def _knobs(subject: _Subject) -> Any:
    """The knobs the drives run under. Values are the module's own validation
    domain, not §12A's numbers: this gate measures BEHAVIOUR at chosen widths
    and `check_risks_data_only` owns whether the shipped numbers match §12A."""
    return subject.blackout.BlackoutKnobs(
        eod_blackout_min=20,
        eow_blackout_min=30,
        news_blackout_min=20,
        margin_elevated_pct=0.10,
        margin_min_hold_s=300,
        margin_reacceptance_s=3600,
    )


def _rig(subject: _Subject, at: datetime) -> _Rig:
    """Wire the SHIPPED evaluator over the SHIPPED calendar at instant `at`."""
    clock = _Clock(at)
    windows = _WindowCache(subject.cal_seam)
    baselines = _BaselineCache(subject.cal_seam)
    picture = _Picture(subject.seam)
    alerts = _Alerts()
    onsets = _Onsets()
    ledger = _Ledger(subject.seam)
    evaluator = subject.blackout.BlackoutEvaluator(
        windows=windows,
        baselines=baselines,
        picture=picture,
        clock=clock,
        knobs=_knobs(subject),
        alert=alerts,
        onset=onsets,
        ledger=ledger,
    )
    return _Rig(evaluator, clock, windows, baselines, picture, alerts, onsets, ledger)


def _drive(rig: _Rig, tally: _Tally, symbol: str, at: datetime) -> tuple[bool, str]:
    """Move `now` to `at`, read the port, and COUNT the side it landed on."""
    rig.clock.at = at
    blocked, reason = rig.evaluator.read(symbol)
    tally.record(symbol, blocked, reason)
    return blocked, reason


# ---------------------------------------------------------------------------
# Drive instants, DERIVED from the vendored calendar
# ---------------------------------------------------------------------------


class _Breaks(NamedTuple):
    """One real daily break and one real weekend break for one symbol."""

    symbol: str
    group: str
    daily: Any
    weekend: Any


def _find_breaks(subject: _Subject, symbol: str) -> tuple[_Breaks | None, str]:
    """The first DAILY_BREAK and WEEKEND break in a fixed sweep of the artifact.

    Derived, never typed: a regenerated calendar moves these dates and the arms
    move with them. The sweep starts one week after the artifact's own first
    session so the search does not begin on a boundary row.
    """
    calendar = subject.calendar
    try:
        group = calendar.product_group_of(symbol)
        first, _last = calendar.artifact_span(group)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, f"{symbol}: {type(exc).__name__}: {exc}"
    start = datetime.fromisoformat(first).date() + timedelta(days=7)
    daily = weekend = None
    for offset in range(SEARCH_DAYS):
        try:
            brk = calendar.break_window(group, start + timedelta(days=offset))
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return None, f"{symbol}: break_window raised {type(exc).__name__}: {exc}"
        if brk is None:
            continue
        if brk.klass == "DAILY_BREAK" and daily is None:
            daily = brk
        elif brk.klass == "WEEKEND" and weekend is None:
            weekend = brk
    if daily is None or weekend is None:
        return None, (
            f"{symbol}: the vendored calendar yielded no "
            f"{'DAILY_BREAK' if daily is None else 'WEEKEND'} break in "
            f"{SEARCH_DAYS} days from {start} -- the drive instants cannot be "
            "derived, so nothing was measured (§17)"
        )
    return _Breaks(symbol, group, daily, weekend), ""


def _break_rows(subject: _Subject, group: str) -> int:
    """How many break rows the artifact carries for `group`. A floor subject."""
    try:
        # pylint: disable=protected-access
        return len(subject.calendar._load_breaks().get(group, ()))
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# ARM A -- §6.1 EOD, inside and outside
# ---------------------------------------------------------------------------


def _arm_eod(subject: _Subject, breaks: _Breaks, tally: _Tally) -> list[Finding]:
    """Inside the lead denies; one second before it, and at re-open, permit."""
    site = f"{REL_SUBJECT}:BlackoutEvaluator.read[§6.1 EOD {breaks.symbol}]"
    source = subject.blackout.SessionWindowSource(_knobs(subject))
    close, reopen = breaks.daily.start, breaks.daily.end
    rig = _rig(subject, close)
    window_set = source.window_set(breaks.symbol, close)
    rig.windows.sets[breaks.symbol] = window_set
    tally.windows += len(window_set.windows)

    findings: list[Finding] = []
    inside = close - timedelta(minutes=10)
    blocked, reason = _drive(rig, tally, breaks.symbol, inside)
    if not blocked:
        findings.append(
            Finding(
                site,
                f"now={inside.isoformat()} is INSIDE the §6.1 window "
                f"[{(close - timedelta(minutes=20)).isoformat()}, "
                f"{reopen.isoformat()}) and the evaluator permitted entry",
            )
        )
    elif "eod" not in reason or reopen.isoformat() not in reason:
        findings.append(
            Finding(
                site,
                "denied inside the §6.1 window but the reason names neither the "
                f"kind nor the window's end: {reason!r} (§3 requires an "
                "actionable denial)",
            )
        )

    edge = close - timedelta(minutes=20)
    if not _drive(rig, tally, breaks.symbol, edge)[0]:
        findings.append(
            Finding(
                site,
                f"the leading edge {edge.isoformat()} itself did not block; "
                "`[start, end)` is half-open at the START, so the first instant "
                "of the blackout is inside it",
            )
        )
    findings += _outside(
        rig,
        tally,
        breaks.symbol,
        site,
        "§6.1",
        [
            edge - timedelta(seconds=1),
            reopen,
            reopen + timedelta(minutes=30),
        ],
    )
    # §6.1 runs THROUGH the next open, not merely up to the close.
    mid = close + (reopen - close) / 2
    if not _drive(rig, tally, breaks.symbol, mid)[0]:
        findings.append(
            Finding(
                site,
                f"now={mid.isoformat()} is between the close and the next open "
                "and the evaluator permitted entry -- §6.1 runs 'through its "
                "next session open', not up to the close",
            )
        )
    return findings


def _outside(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rig: _Rig,
    tally: _Tally,
    symbol: str,
    site: str,
    clause: str,
    instants: list[datetime],
) -> list[Finding]:
    """Every instant here must PERMIT. The other half of every window arm."""
    findings = []
    for at in instants:
        blocked, reason = _drive(rig, tally, symbol, at)
        if blocked:
            findings.append(
                Finding(
                    site,
                    f"now={at.isoformat()} is OUTSIDE every {clause} window and "
                    f"the evaluator denied entry: {reason!r}. A rule that "
                    "always blocks is not a blackout",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# ARM B -- §6.2 EOW union
# ---------------------------------------------------------------------------


def _arm_eow(  # pylint: disable=too-many-locals
    subject: _Subject, breaks: _Breaks, tally: _Tally
) -> list[Finding]:
    """The union, shown by REMOVING the wide window and watching it flip."""
    site = f"{REL_SUBJECT}:BlackoutEvaluator.read[§6.2 EOW {breaks.symbol}]"
    source = subject.blackout.SessionWindowSource(_knobs(subject))
    close, reopen = breaks.weekend.start, breaks.weekend.end
    rig = _rig(subject, close)
    published = source.window_set(breaks.symbol, close)
    weekend_windows = [w for w in published.windows if w.end == reopen]
    kinds = {w.kind.value: w for w in weekend_windows}
    if set(kinds) != {"eod", "eow"}:
        return [
            Finding(
                site,
                f"the weekend break at {close.isoformat()} produced windows "
                f"{sorted(kinds)}; §6.2's union needs BOTH an eod and an eow "
                "window over the same close, and one window cannot show a union",
            )
        ]
    if not kinds["eow"].start < kinds["eod"].start:
        return [
            Finding(
                site,
                f"the eow lead {kinds['eow'].start.isoformat()} is not wider "
                f"than the eod lead {kinds['eod'].start.isoformat()} -- with no "
                "overlap there is nothing for 'widest active leading edge wins' "
                "to decide, and this arm would be vacuous",
            )
        ]
    rig.windows.sets[breaks.symbol] = published
    tally.windows += len(published.windows)

    findings: list[Finding] = []
    # (1) an instant ONLY the wide window covers.
    between = kinds["eow"].start + (kinds["eod"].start - kinds["eow"].start) / 2
    blocked, reason = _drive(rig, tally, breaks.symbol, between)
    if not blocked:
        findings.append(
            Finding(
                site,
                f"now={between.isoformat()} lies inside the eow window and "
                "outside the eod window, and the evaluator permitted entry -- "
                "§6.2's wider leading edge did not win",
            )
        )
    elif "eow" not in reason:
        findings.append(
            Finding(
                site, f"blocked at {between.isoformat()} without naming eow: {reason!r}"
            )
        )

    # (2) THE UNION CONTROL. Same instant, wide window removed from the set.
    narrow_only = tuple(w for w in published.windows if w.kind.value != "eow")
    rig.windows.sets[breaks.symbol] = subject.cal_seam.WindowSet(
        symbol=breaks.symbol, windows=narrow_only, generated_at=published.generated_at
    )
    still_blocked, why = _drive(rig, tally, breaks.symbol, between)
    if still_blocked:
        findings.append(
            Finding(
                site,
                f"with the eow window removed, now={between.isoformat()} still "
                f"blocked ({why!r}). The remaining windows already covered the "
                "instant, so the previous drive demonstrated no union -- one "
                "window cannot show one",
            )
        )
    rig.windows.sets[breaks.symbol] = published

    # (3) an instant BOTH cover: the attribution must be the wider one.
    both = kinds["eod"].start + timedelta(minutes=5)
    blocked, reason = _drive(rig, tally, breaks.symbol, both)
    if not blocked:
        findings.append(
            Finding(
                site, f"now={both.isoformat()} is inside both windows and permitted"
            )
        )
    elif "inside the eow window" not in reason or "['eod']" not in reason:
        findings.append(
            Finding(
                site,
                f"at {both.isoformat()} both windows are active; §6.2 makes the "
                "WIDEST active leading edge win, so the denial must name eow "
                f"and record eod as also active. It said: {reason!r}",
            )
        )

    findings += _outside(
        rig,
        tally,
        breaks.symbol,
        site,
        "§6.2",
        [
            kinds["eow"].start - timedelta(minutes=10),
            reopen,
        ],
    )
    # And the whole weekend in between is blocked.
    if not _drive(rig, tally, breaks.symbol, close + (reopen - close) / 2)[0]:
        findings.append(
            Finding(site, "the middle of the weekend break permitted entry")
        )
    return findings


# ---------------------------------------------------------------------------
# ARM C -- §6.3 asymmetric edges
# ---------------------------------------------------------------------------


def _quiet_instant(breaks: _Breaks) -> datetime:
    """An instant far from any session boundary, so only §6.3 can block there.

    Six hours after the daily re-open: the session runs ~23h, so this is inside
    it and nowhere near the next close. Driving the news arm inside an EOD
    window would prove nothing about the news edge, because the EOD window
    would block on its own.
    """
    return breaks.daily.end + timedelta(hours=6)


def _arm_news_margin(  # pylint: disable=too-many-locals,too-many-statements
    subject: _Subject, breaks: _Breaks, tally: _Tally
) -> list[Finding]:
    """Clock lead in; live margin out; and the anti-lockout re-acceptance."""
    site = f"{REL_SUBJECT}:BlackoutEvaluator.read[§6.3 {breaks.symbol}]"
    blackout = subject.blackout
    source = blackout.SessionWindowSource(_knobs(subject))
    event_at = _quiet_instant(breaks)
    event = blackout.ScheduledEvent(
        symbol=breaks.symbol, at=event_at, source="gate-drive", label="margin-event"
    )
    rig = _rig(subject, event_at)
    published = source.window_set(breaks.symbol, event_at, events=(event,))
    rig.windows.sets[breaks.symbol] = published
    tally.windows += len(published.windows)
    rig.baselines.levels[breaks.symbol] = subject.cal_seam.MarginBaseline(
        symbol=breaks.symbol, level=1000.0, accepted_at=event_at - timedelta(days=1)
    )
    rig.picture.margin[breaks.symbol] = 1000.0

    findings: list[Finding] = []
    # PREMISE: this instant is quiet. If it is not, every §6.3 drive below is
    # measuring an EOD window instead and the arm is vacuous.
    if _drive(rig, tally, breaks.symbol, event_at - timedelta(minutes=25))[0]:
        return [
            Finding(
                site,
                f"the chosen quiet instant {event_at.isoformat()} is inside "
                "another window, so nothing below would measure §6.3",
            )
        ]

    # LEADING EDGE = clock.
    blocked, reason = _drive(
        rig, tally, breaks.symbol, event_at - timedelta(minutes=10)
    )
    if not blocked or "news_margin" not in reason:
        findings.append(
            Finding(
                site,
                "20 min before a scheduled margin event the leading edge must "
                f"block and name the window; got blocked={blocked} {reason!r}",
            )
        )

    # TRAILING EDGE = live margin. The spike.
    rig.picture.margin[breaks.symbol] = 4000.0
    blocked, reason = _drive(
        rig, tally, breaks.symbol, event_at + timedelta(seconds=30)
    )
    if not blocked or "margin elevated" not in reason:
        findings.append(
            Finding(
                site,
                "live margin at 4x the baseline after the event did not hold "
                f"the trailing edge open: blocked={blocked} {reason!r}",
            )
        )

    # MARGIN ACTUALLY RETURNS. Still held by the min-time floor.
    rig.picture.margin[breaks.symbol] = 1000.0
    blocked, reason = _drive(
        rig, tally, breaks.symbol, event_at + timedelta(seconds=60)
    )
    if not blocked or "min-time floor" not in reason:
        findings.append(
            Finding(
                site,
                "margin returned to baseline 30 s after the spike and the "
                "evaluator released immediately; §6.3's trailing edge is "
                f"'returns to baseline (+ MIN-TIME FLOOR)': {reason!r}",
            )
        )

    # PAST THE FLOOR: released. This is the drive that proves the block ends.
    blocked, reason = _drive(
        rig, tally, breaks.symbol, event_at + timedelta(seconds=600)
    )
    if blocked:
        findings.append(
            Finding(
                site,
                "margin has been back at baseline for longer than the min-time "
                f"floor and the evaluator still denies: {reason!r}. A trailing "
                "edge that never trails is a permanent lockout",
            )
        )

    findings += _unscheduled_and_lockout(subject, breaks, tally, site)
    return findings


def _unscheduled_and_lockout(
    subject: _Subject, breaks: _Breaks, tally: _Tally, site: str
) -> list[Finding]:
    """The spike with no window, and the regime shift that must not lock out."""
    findings: list[Finding] = []
    source = subject.blackout.SessionWindowSource(_knobs(subject))
    at = _quiet_instant(breaks)
    rig = _rig(subject, at)
    rig.windows.sets[breaks.symbol] = source.window_set(breaks.symbol, at)
    rig.baselines.levels[breaks.symbol] = subject.cal_seam.MarginBaseline(
        symbol=breaks.symbol, level=1000.0, accepted_at=at - timedelta(days=1)
    )
    rig.picture.margin[breaks.symbol] = 1000.0
    if _drive(rig, tally, breaks.symbol, at)[0]:
        return [Finding(site, f"the quiet instant {at.isoformat()} was not quiet")]

    # UNSCHEDULED: no window anywhere near, margin spikes.
    rig.picture.margin[breaks.symbol] = 1200.0
    blocked, reason = _drive(rig, tally, breaks.symbol, at)
    if not blocked or "UNSCHEDULED" not in reason:
        findings.append(
            Finding(
                site,
                "an unscheduled 20% margin spike with no calendar entry did not "
                f"block: blocked={blocked} {reason!r}. §6.3's reactive edge "
                "catches unscheduled spikes for free or it is a second clock",
            )
        )

    # ANTI-LOCKOUT: margin STAYS elevated past the re-acceptance period.
    just_short = at + timedelta(seconds=3599)
    if not _drive(rig, tally, breaks.symbol, just_short)[0]:
        findings.append(
            Finding(
                site,
                "margin still elevated one second inside the re-acceptance "
                "period and the evaluator already released -- the period is not "
                "being observed",
            )
        )
    past = at + timedelta(seconds=3601)
    blocked, reason = _drive(rig, tally, breaks.symbol, past)
    if blocked:
        findings.append(
            Finding(
                site,
                "margin held stable-elevated beyond the re-acceptance period "
                f"and the evaluator still denies: {reason!r}. §6.3: 'a "
                "permanent broker hike must never lock the system out forever'",
            )
        )
    codes = [code for code, _ in rig.alerts.raised]
    if "margin_baseline_re_accepted" not in codes:
        findings.append(
            Finding(
                site,
                f"the baseline was re-accepted with no operator alert (alerts "
                f"raised: {codes}). §6.3 requires the operator be told: a "
                "silent re-baselining is the system deciding it needs less "
                "protection and telling nobody",
            )
        )
    # And it STAYS unlocked -- the lockout is broken, not reported broken once.
    if _drive(rig, tally, breaks.symbol, at + timedelta(seconds=7200))[0]:
        findings.append(
            Finding(site, "the re-accepted baseline did not persist to the next read")
        )
    return findings


# ---------------------------------------------------------------------------
# ARM D -- §3 onset
# ---------------------------------------------------------------------------


def _arm_onset(subject: _Subject, breaks: _Breaks, tally: _Tally) -> list[Finding]:
    """One onset per clear -> in-window edge, via the seam's own TerminalPath."""
    site = f"{REL_SUBJECT}:BlackoutEvaluator._fire_onset[§3 {breaks.symbol}]"
    source = subject.blackout.SessionWindowSource(_knobs(subject))
    close, reopen = breaks.daily.start, breaks.daily.end
    rig = _rig(subject, close)
    rig.windows.sets[breaks.symbol] = source.window_set(breaks.symbol, close)
    rig.ledger.rows = [
        _reservation(subject, "r1", breaks.symbol),
        _reservation(subject, "r2", breaks.symbol),
        _reservation(subject, "rOther", "__other__"),
    ]

    findings: list[Finding] = []
    _drive(rig, tally, breaks.symbol, close - timedelta(minutes=40))
    if rig.onsets.seen:
        findings.append(Finding(site, "an onset fired while outside every window"))
    _drive(rig, tally, breaks.symbol, close - timedelta(minutes=10))
    if len(rig.onsets.seen) != 1:
        findings.append(
            Finding(
                site,
                f"crossing into the §6.1 window produced {len(rig.onsets.seen)} "
                "onset record(s); §3 releases 'on blackout-onset cancellation' "
                "exactly once per edge",
            )
        )
        return findings
    onset = rig.onsets.seen[0]
    if onset.via is not subject.seam.TerminalPath.BLACKOUT_ONSET:
        findings.append(
            Finding(
                site,
                f"the onset was booked via {onset.via!r}, not the seam's own "
                "TerminalPath.BLACKOUT_ONSET -- §3's release-path list is the "
                "spec's, and a second spelling puts the wrong cause in §9's "
                "record of money truth",
            )
        )
    released = [rid for rid, _ in rig.ledger.released]
    if released != ["r1", "r2"]:
        findings.append(
            Finding(
                site,
                f"onset released {released}; it must release exactly this "
                "symbol's outstanding reservations and leave another symbol's "
                "alone (§3 'onset cancels PENDING ENTRY orders')",
            )
        )
    _drive(rig, tally, breaks.symbol, close - timedelta(minutes=5))
    if len(rig.onsets.seen) != 1:
        findings.append(
            Finding(site, "a second read inside the SAME window fired a second onset")
        )
    _drive(rig, tally, breaks.symbol, reopen + timedelta(minutes=5))
    _drive(rig, tally, breaks.symbol, close - timedelta(minutes=5))
    if len(rig.onsets.seen) != 2:
        findings.append(
            Finding(site, "leaving the window and re-entering did not fire a new onset")
        )
    return findings


def _reservation(subject: _Subject, rid: str, symbol: str) -> Any:
    return subject.seam.Reservation(
        reservation_id=rid,
        client_order_id=f"c-{rid}",
        strategy_id=f"s-{rid}",
        symbol=symbol,
        margin=500.0,
        state=subject.seam.ReservationState.TAKEN,
        taken_ts=0.0,
    )


# ---------------------------------------------------------------------------
# ARM E / ARM F -- static arms over the subject's own bytes
# ---------------------------------------------------------------------------


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError, UnicodeDecodeError:
        return None


def _assigned_value(tree: ast.Module, name: str) -> ast.expr | None:
    """The value assigned to module-level `name`, read STATICALLY.

    Check contract v2 rule 6's reasoning applied to a declaration: reading a
    value by AST cannot execute the module it is read from, so the gate cannot
    be influenced by its subject.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return node.value
    return None


def _string_elements(node: ast.expr | None) -> tuple[str, ...]:
    if not isinstance(node, ast.Tuple):
        return ()
    return tuple(
        e.value
        for e in node.elts
        if isinstance(e, ast.Constant) and isinstance(e.value, str)
    )


def _arm_source_roster(home: Path, tree: ast.Module) -> tuple[list[Finding], int, str]:
    """SPEC-A10: a second calendar source requires a flagging path. Returns
    `(findings, roster_size, cannot_measure)`."""
    site = f"{REL_SUBJECT}:{ROSTER_CONST}"
    roster = _string_elements(_assigned_value(tree, ROSTER_CONST))
    if len(roster) < FLOORS["calendar_sources"]:
        return (
            [],
            len(roster),
            (
                f"ARM E: {REL_SUBJECT} declares {len(roster)} calendar "
                f"source(s), below the non-vacuity floor of "
                f"{FLOORS['calendar_sources']}. SPEC-A10's ratchet has nothing "
                "to judge, so it was not measured -- deleting the roster is not "
                "a route to green (§17)"
            ),
        )

    findings = [
        Finding(
            site,
            f"declares calendar source {entry!r}, which is not on disk under "
            f"{home}. A roster naming an absent path is a comparison between "
            "two literals, and SPEC-A10's ratchet would ride on it",
        )
        for entry in roster
        if not (home / entry).exists()
    ]

    defined = any(
        isinstance(node, ast.FunctionDef) and node.name == FLAGGING_FUNC
        for node in ast.walk(tree)
    )
    if not defined:
        findings.append(
            Finding(
                f"{REL_SUBJECT}:{FLAGGING_FUNC}",
                f"the SPEC-A10 flagging path {FLAGGING_FUNC!r} is not defined. "
                "The ratchet requires something to require; removing it would "
                "make the roster free to grow",
            )
        )
    if len(roster) > 1 and not _calls(tree, FLAGGING_FUNC):
        findings.append(
            Finding(
                site,
                f"declares {len(roster)} calendar sources {list(roster)} and "
                f"nothing in {REL_SUBJECT} calls {FLAGGING_FUNC!r}. SPEC-A10: "
                "'live source wins on disagreement; disagreements are logged as "
                "flagged events, never silently resolved' -- with two sources "
                "and no flagging path, a disagreement is resolved silently by "
                "whichever read happens first",
            )
        )
    return findings, len(roster), ""


def _calls(tree: ast.Module, name: str) -> bool:
    """True where `name(...)` is called somewhere other than inside its own def."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            continue
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == name:
                return True
            if isinstance(func, ast.Attribute) and func.attr == name:
                return True
    return False


def _arm_kind_agnostic(tree: ast.Module) -> tuple[list[Finding], int, str]:
    """§6.5: no rule branches on `WindowKind`. Returns `(findings, nodes, cm)`."""
    evaluator = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == EVALUATOR_CLASS
        ),
        None,
    )
    if evaluator is None:
        return (
            [],
            0,
            (
                f"ARM F: {REL_SUBJECT} declares no class {EVALUATOR_CLASS!r}, so "
                "there is no decision path to scan for a kind branch (§17)"
            ),
        )
    findings: list[Finding] = []
    scanned = 0
    for node in ast.walk(evaluator):
        scanned += 1
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "WindowKind"
        ):
            findings.append(
                Finding(
                    f"{REL_SUBJECT}:{node.lineno}",
                    f"{EVALUATOR_CLASS} references WindowKind.{node.attr} on a "
                    "decision path. calendar_seam.py: the gating rule is 'now ∈ "
                    "any window', kind-agnostic, and 'if a future reader finds "
                    "a rule switching on WindowKind, that rule is the defect' "
                    "(§6.5: new blackout types are DATA, not code)",
                )
            )
        if isinstance(node, ast.Compare) and _mentions_kind(node):
            findings.append(
                Finding(
                    f"{REL_SUBJECT}:{node.lineno}",
                    f"{EVALUATOR_CLASS} COMPARES a window's `.kind`. §6.1's "
                    "entry-only asymmetry rides on Window.entry_only, a "
                    "per-ROW boolean; a kind comparison makes a new blackout "
                    "type a code change",
                )
            )
    return findings, scanned, ""


def _mentions_kind(node: ast.Compare) -> bool:
    """True where either side of a comparison reads a `.kind` attribute."""
    for side in (node.left, *node.comparators):
        for inner in ast.walk(side):
            if isinstance(inner, ast.Attribute) and inner.attr == "kind":
                return True
    return False


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _floor_complaint(  # pylint: disable=too-many-locals
    tally: _Tally, roster: int, rows: int
) -> str:
    """The first unmet floor, as a CANNOT_MEASURE detail. `''` where all met."""
    checks = [
        (
            tally.blocked,
            FLOORS["blocked_drives"],
            (
                "drives that DENIED. An evaluator that never denies satisfies "
                "every outside drive and is exactly the failure this gate exists "
                "to catch"
            ),
        ),
        (
            tally.permitted,
            FLOORS["permitted_drives"],
            (
                "drives that PERMITTED. An evaluator that always denies "
                "satisfies every inside drive, which is the opposite failure and "
                "equally invisible to a one-sided suite"
            ),
        ),
        (
            len(tally.kinds),
            FLOORS["window_kinds_driven"],
            (
                "distinct window kinds driven to a block (§6.1 eod, §6.2 eow, "
                "§6.3 news_margin)"
            ),
        ),
        (tally.windows, FLOORS["windows_generated"], "windows generated and published"),
        (len(tally.symbols), FLOORS["symbols_driven"], "symbols driven"),
        (rows, FLOORS["calendar_break_rows"], "break rows in the vendored calendar"),
        (roster, FLOORS["calendar_sources"], "declared calendar sources"),
    ]
    for measured, floor, what in checks:
        if measured < floor:
            return (
                f"non-vacuity floor unmet: {measured} {what}, floor {floor}. A "
                "population below the floor cannot certify the property; that "
                "is unmeasured, not proven (doctrine C.4, §17)"
            )
    return ""


def _all_arms(  # pylint: disable=too-many-return-statements,too-many-locals
    home: Path, subject: _Subject
) -> tuple[list[Finding], dict[str, Any], str]:
    """Run every arm. Returns `(findings, stats, cannot_measure)`."""
    tree = _parse(home / REL_SUBJECT)
    if tree is None:
        return [], {}, f"{REL_SUBJECT} could not be read or parsed (§17)"

    findings: list[Finding] = []
    tally = _Tally()
    try:
        symbols = tuple(subject.calendar.known_symbols())[:2]
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            [],
            {},
            (
                f"the vendored calendar could not name its symbols "
                f"({type(exc).__name__}: {exc}) -- the drive instants come from the "
                "calendar, so with no calendar nothing was driven and nothing was "
                "proven (§17)"
            ),
        )
    if len(symbols) < FLOORS["symbols_driven"]:
        return (
            [],
            {},
            (
                f"the vendored symbol map carries {len(symbols)} symbol(s); at "
                f"least {FLOORS['symbols_driven']} are needed so a per-symbol "
                "keying defect cannot hide behind a single symbol (§17)"
            ),
        )
    rows = 0
    for symbol in symbols:
        breaks, complaint = _find_breaks(subject, symbol)
        if breaks is None:
            return findings, {}, complaint
        rows = max(rows, _break_rows(subject, breaks.group))
        try:
            findings += _arm_eod(subject, breaks, tally)
            findings += _arm_eow(subject, breaks, tally)
            findings += _arm_news_margin(subject, breaks, tally)
            findings += _arm_onset(subject, breaks, tally)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return (
                findings,
                {},
                (
                    f"driving {symbol} raised {type(exc).__name__}: {exc} -- the "
                    "subject could not be exercised, so nothing was proven (§17)"
                ),
            )

    roster_findings, roster, cannot = _arm_source_roster(home, tree)
    findings += roster_findings
    kind_findings, scanned, kind_cannot = _arm_kind_agnostic(tree)
    findings += kind_findings

    stats = {
        "blocked": tally.blocked,
        "permitted": tally.permitted,
        "kinds": sorted(tally.kinds),
        "windows": tally.windows,
        "symbols": sorted(tally.symbols),
        "roster": roster,
        "rows": rows,
        "scanned": scanned,
    }
    return (
        findings,
        stats,
        cannot or kind_cannot or _floor_complaint(tally, roster, rows),
    )


def _pass(stats: dict[str, Any]) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=(
            f"{stats['blocked']} drive(s) DENIED and {stats['permitted']} "
            f"PERMITTED across symbols {stats['symbols']}, over "
            f"{stats['windows']} windows generated from the vendored calendar "
            f"({stats['rows']} break rows). Window kinds driven to a block: "
            f"{stats['kinds']}. §6.2's union was shown by removing the wider "
            "window and observing the verdict flip; §6.3's trailing edge was "
            "driven back TO baseline (held by the min-time floor), past the "
            "floor (released), and held elevated past the re-acceptance period "
            "(re-accepted, operator alerted). §3 onset fires once per edge via "
            f"TerminalPath.BLACKOUT_ONSET. SPEC-A10 roster: {stats['roster']} "
            f"source(s), flagging path present; {stats['scanned']} AST nodes in "
            f"{EVALUATOR_CLASS} carry no WindowKind branch. NOT measured here: "
            "that any live poller publishes these sets, that any econ event "
            "arrives, or that a venue order is cancelled on onset"
        ),
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Six arms over the §6.1-6.3 blackout evaluator, driven on both sides."""
    try:
        home = Path(ctx.nix_home)
        subject, complaint = load_subject(home)
        if subject is None:
            return _cannot(
                f"{complaint} -- the subject could not be observed, so its "
                "property was not measured (§17); never a PASS"
            )
        findings, stats, cannot = _all_arms(home, subject)
        # FAIL outranks CANNOT_MEASURE within a check, per the contract's own
        # aggregate ordering: a violation an arm MEASURED stays measured when a
        # later arm loses its subject.
        if findings:
            return _fail(findings)
        return _cannot(cannot) if cannot else _pass(stats)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return _cannot(f"gate raised {type(exc).__name__}: {exc}")


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
