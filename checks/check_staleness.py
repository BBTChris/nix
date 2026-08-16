#!/usr/bin/env python3
"""check_staleness -- verify.py gate: §6.4's stale condition and §12.3's
clock-integrity condition are PRODUCED, they fire on a genuinely stale feed,
and they do NOT fire on a slow-but-fresh one.

Subject: `scripts/nixrisk/freshness.py` and the §12A numbers in
`risks/staleness.config.json` that drive it. The gate loads the subject from
`ctx.nix_home` and DRIVES it -- every arm below is a measurement on executed
bytes, not an AST reading of them, except where an arm is explicitly about the
shape of the file.

---

## THE DEFECT THIS GATE EXISTS TO CATCH: ARC 022 F17, AND ITS MIRROR IMAGE

F17 measured "stale" from a **session mean**. The mean agreed while the last
packets were 900 seconds out: the mean was fine and the data was dead. A gate
that only proves "the detector fired on something" would have passed F17,
because F17 fired on plenty of things.

So this gate drives **both** halves against the same detector, and drives a
mean-based comparator alongside on the same two populations to show it
inverting on both:

  * **BRISK-THEN-DEAD** -- many arrivals at a tight cadence, then a long
    silence. The mean is small, the count is large, the feed is DEAD.
    Required: the detector BLOCKS, and the mean-based comparator does not.
  * **SPARSE-BUT-CURRENT** -- a long historical gap, then an arrival moments
    ago. The mean is enormous, the count is tiny, the feed is HEALTHY.
    Required: the detector does NOT block, and the mean-based comparator does.

Either half alone measures nothing useful. A staleness test where the feed is
never stale measures nothing; one where a slow-but-fresh feed is never driven
measures half, and it is the half that lets a correct feed halt the book.

## debug.md §7.12 -- THE STANDING QUESTION: how could this gate be GREEN while
## the property is FALSE?
##
## (Deliberately NOT labelled with the arc-brief section number that asked for
## it: check contract v2 rule 13 -- arc-brief labels are per-arc, collide
## across arcs, and are not identifiers.)

1. **The subject could never be loaded, and a `try/except` could turn that into
   silence.** *Closed:* `load_subject` returns a complaint naming the import
   error, `_subject_defects` returns CANNOT_MEASURE naming every absent path,
   and `run`'s catch-all is CANNOT_MEASURE. There is no path from an absent
   subject to PASS (§17).

2. **The detector could block on EVERYTHING.** A `read()` that returns
   `(True, ...)` unconditionally passes ARM STALE and every EMPTY control, and
   halts the book forever in production. *Closed:* ARM FRESH requires a
   NOT-blocked verdict on the sparse-but-current population and on a
   freshly-observed feed, so a constant-True detector fails here. The two arms
   are each other's control and neither is optional.

3. **The detector could block on NOTHING** -- the F17 shape. *Closed:* ARM
   STALE requires a blocked verdict, and the drive that produces it is
   `FLOORS["stale_drive_ms"]` past the configured threshold.

4. **The "stale" drive could be so marginal that any comparator passes it.** A
   feed one millisecond past its threshold is caught by a mean, a count, a
   coin. *Closed:* the stale drive is the F17 figure itself -- 900 seconds --
   against a threshold read from the real config, and the same population is
   fed to the mean comparator, which is REQUIRED to get it wrong. If the
   comparator ever agrees with the detector on both populations, the drive has
   stopped discriminating and the gate says CANNOT_MEASURE rather than PASS.

5. **The populations could be too small for a mean to mean anything.** A
   "session mean" over two arrivals is not the F17 defect. *Closed:*
   `FLOORS["brisk_arrivals"]` requires a real burst before the silence, and the
   floor is a FLOOR (doctrine C.4): today the drive sends 300, and nothing
   legitimate takes that below 100.

6. **The gate could test a detector nothing consumes.** A perfectly correct
   `read()` that no rule dispatches produces no halt. *Closed:* ARM PORT builds
   the SHIPPED `gate.SymbolFlagRule` / `gate.GlobalFlagRule` around the subject
   and asserts on the `RuleVerdict` those rules return -- so the property
   measured is *the gate denies*, not *a method returns True*. `gate.py` is
   read and never written by this arc.

7. **The thresholds could be typed here.** A gate carrying its own copy of
   `MARGIN_STALE_MS` agrees with itself while the shipped config says something
   else. *Closed:* every threshold, the skew ceiling and the retry ladder are
   read from `risks/staleness.config.json` under `ctx.nix_home` at run time and
   `FLOORS["feeds"]` is the count §12A itself enumerates.

8. **The clock arm could pass on a clock nobody looked at.** *Closed:* the
   never-observed control requires a BLOCK, and the aged-observation control
   requires a BLOCK, so "no reading" and "an old reading" are both refusals --
   which is the §17 rule applied to the instrument that watches the clock.

9. **THE MANUFACTURED INPUT IN THIS GATE, declared rather than buried.** Every
   drive below stamps the feeds it is NOT testing fresh at the judged instant.
   That is a manufactured input and it is load-bearing: `StalenessFlagPort`
   reads all four configured feeds and blocks on any EMPTY key, so a rig that
   left them unobserved would make BOTH halves block and the two arms would
   stop discriminating -- the gate would be green on a coin. The reason the
   manufacture is needed is itself a finding: `price` and `balance` have no
   producer anywhere in the tree today, so on the shipped tree the fail-closed
   default is the whole verdict. CHECK-DEBT carries that; this gate does not
   pretend it away, and it does not stamp the feed UNDER TEST.

## C.9 -- WHAT THIS GATE DELIBERATELY DOES NOT MEASURE

* `checks/check_pollers.py` owns `scripts/nixrisk/pollers.py`: whether the two
  producers exist, demote under push, contain a hung socket, and route their
  readings through the guard. This gate owns the DETECTOR and the guard CLASS.
* `checks/check_risks_data_only.py` owns whether `risks/*.config.json` is
  config-role and whether its declared boot rules correspond to implemented
  ones. This gate reads the numbers and never judges the file's shape.
* `checks/check_limiter_gate.py` owns the executor's pass. Nothing here
  re-proves phase ordering, fail-fast, or the manifest.
* `checks/check_calendar_schema.py` owns `calendar_seam.py`. This gate imports
  its value types and judges none of them.

## NON-CORRECTABLE

The subject is declared source and a config of tunables. A gate that "fixed" a
threshold would be choosing a risk parameter unattended, and one that rewrote
the detector would make its own verdict true by construction.
"""

from __future__ import annotations

# The overflow over pylint's 1000-line default is DOCUMENTATION and DRIVES:
# the standing-question block, the C.9 boundary, and two populations that have
# to be built explicitly for the mean comparator to be fed the same bytes as
# the detector. Splitting would put one property in two modules.
# pylint: disable=too-many-lines
# R0801 (duplicate-code) disabled MODULE-WIDE, not at the bottom of the
# file: it is reported against line 1, so a late disable never reaches it.
# The duplication is the check contract's own requirement (§4.2) -- every
# checks/check_*.py carries its own `Finding`, `_fail`, `_cannot`, the
# orchestration declarations and the `standalone_main` tail so that each
# module is independently runnable. Factoring them into a shared helper
# would make every check depend on one module the runner would then have
# to load before it could report that it could not load it.
# pylint: disable=duplicate-code
import ast
import importlib
import itertools
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported; §4.4) ---
#: Nothing produces the subject at run time and no other check gates it.
DEPENDS_ON: tuple[str, ...] = ()
#: The subject is imported from `ctx.nix_home`, which mutates `sys.path` and
#: `sys.modules` for the duration of the load (both restored). Check contract
#: v2 rule 12: a declaration is checked against observation, so the interpreter
#: mutation is DECLARED rather than hoped to be invisible. No port, no
#: subprocess, no write of any kind.
RESOURCES: tuple[str, ...] = ("interpreter:sys.path", "interpreter:sys.modules")
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subjects are declared source and a config of risk tunables; a repair "
    "that rewrote either would make this gate's own verdict true by "
    "construction, and choosing a stale threshold is an operator's decision "
    "under §12A, not an unattended gate's"
)
#: The artifacts this gate covers for `check_artifact_gate_coverage`.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/freshness.py",
    "risks/staleness.config.json",
)

NAME = "check_staleness"

REL_FRESHNESS = "scripts/nixrisk/freshness.py"
REL_CONFIG = "risks/staleness.config.json"
REL_GATE = "scripts/nixrisk/gate.py"
REL_SEAM = "scripts/nixrisk/calendar_seam.py"

#: The feed every drive below runs on. Read from the config's own key set at
#: run time -- this constant is the SELECTION rule, not the feed list.
DRIVE_FEED = "margin"
DRIVE_SYMBOL = "ES"
OTHER_SYMBOL = "NQ"

#: The F17 figure, named: the ARC 022 defect measured "stale" off a session mean
#: that agreed while the last packets were 900 seconds out.
F17_SILENCE_MS = 900_000.0

FLOORS: dict[str, int] = {
    # §12A enumerates MARGIN_STALE_MS, CALENDAR_STALE_MS, PRICE_STALE_MS and
    # BALANCE_STALE_MS. The floor is the SPEC's count, not the tree's, so a
    # config that quietly dropped one is CANNOT_MEASURE rather than a smaller
    # green.
    "feeds": 4,
    # A "session mean" over a handful of arrivals is not the F17 defect. The
    # drive sends 300; nothing legitimate takes a burst below this (C.4).
    "brisk_arrivals": 100,
    # The stale drive must be the F17 silence, not a marginal overshoot.
    "stale_drive_ms": 900_000,
    # Both flag ports must be exercised through a real gate rule.
    "rules_driven": 2,
    # Every arm the docstring enumerates has to have actually run. Unlike the
    # population floors above this one is EXACT-by-construction rather than a
    # C.4 floor over a discovered set: the arms are written out in `_all_arms`,
    # so a deleted arm is a deleted line, not a smaller measurement.
    "arms": 10,
}


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
# Subject loading
# ---------------------------------------------------------------------------


class _Subject(NamedTuple):
    freshness: Any
    #: `nixrisk.calendar_seam` — where `FreshnessStamp` lives.
    seam: Any
    #: `nixrisk.seam` — where the Limiter's `ProposedOrder`/`Decision` live.
    limiter_seam: Any
    gate: Any


_NIXRISK_PREFIX = "nixrisk"


def _purged() -> dict[str, Any]:
    saved = {
        key: value
        for key, value in sys.modules.items()
        if key == _NIXRISK_PREFIX or key.startswith(f"{_NIXRISK_PREFIX}.")
    }
    for key in saved:
        del sys.modules[key]
    return saved


def _restore(saved: dict[str, Any]) -> None:
    for key in [
        key
        for key in list(sys.modules)
        if key == _NIXRISK_PREFIX or key.startswith(f"{_NIXRISK_PREFIX}.")
    ]:
        del sys.modules[key]
    sys.modules.update(saved)


def load_subject(home: Path) -> tuple[_Subject | None, str]:
    """Import the subject FROM `home`. Returns `(subject, complaint)`.

    `sys.modules` is purged of `nixrisk*` before and restored after, for
    `check_limiter_gate.load_subject`'s reason: a check that ran once against
    the repo would otherwise hand back the repo's module for every subsequent
    tree, and a plant that is never loaded is a plant that cannot fail.
    """
    scripts = home / "scripts"
    if not (scripts / "nixrisk" / "freshness.py").is_file():
        return None, f"{REL_FRESHNESS} is not on disk under {home} -- nothing to drive"
    saved_path = list(sys.path)
    saved_mods = _purged()
    sys.path.insert(0, str(scripts.resolve()))
    try:
        seam = importlib.import_module("nixrisk.calendar_seam")
        limiter_seam = importlib.import_module("nixrisk.seam")
        freshness = importlib.import_module("nixrisk.freshness")
        gate = importlib.import_module("nixrisk.gate")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{REL_FRESHNESS} would not import from {home}: {type(exc).__name__}: {exc}"
        )
    finally:
        _restore(saved_mods)
        sys.path[:] = saved_path
    return _Subject(freshness, seam, limiter_seam, gate), ""


def _subject_defects(home: Path) -> CheckResult | None:
    """CANNOT_MEASURE naming every absent subject (§17)."""
    missing = [
        rel
        for rel in (REL_FRESHNESS, REL_CONFIG, REL_GATE, REL_SEAM)
        if not (home / rel).is_file()
    ]
    if not missing:
        return None
    return _cannot(
        f"absent subject(s) under {home}: {', '.join(missing)} -- a property "
        "proven while its subject is unavailable is not proven (§17)"
    )


def _config_values(home: Path) -> tuple[dict[str, Any], str]:
    """The config's VALUE keys -- `_`-prefixed documentation keys excluded."""
    try:
        raw = json.loads((home / REL_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{REL_CONFIG} could not be read or parsed: {exc}"
    if not isinstance(raw, dict):
        return {}, f"{REL_CONFIG}: top level is {type(raw).__name__}, expected object"
    return {k: v for k, v in raw.items() if not k.startswith("_")}, ""


# ---------------------------------------------------------------------------
# A movable clock, and the two populations
# ---------------------------------------------------------------------------


class _Clock:
    """A settable UTC clock. The detector takes its clock as an argument, so a
    900-second staleness is driven in microseconds rather than waited out."""

    EPOCH = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)

    def __init__(self) -> None:
        self.now = self.EPOCH

    def __call__(self) -> datetime:
        return self.now

    def set_ms(self, offset_ms: float) -> datetime:
        """Move to EPOCH + `offset_ms` and return the new instant."""
        self.now = self.EPOCH + timedelta(milliseconds=offset_ms)
        return self.now


def _mean_interval_ms(arrivals_ms: list[float]) -> float:
    """THE F17 COMPARATOR: the mean gap between arrivals over the session.

    Reproduced here on purpose. It is the quantity ARC 022 used, it is computed
    from the same population the detector sees, and every arm that names it
    requires it to DISAGREE with the detector -- so the gate demonstrates the
    defect rather than describing it.
    """
    if len(arrivals_ms) < 2:
        return float("inf")
    gaps = [b - a for a, b in itertools.pairwise(arrivals_ms)]
    return sum(gaps) / len(gaps)


class _Population(NamedTuple):
    """One drive's arrival instants (ms since epoch) and the instant judged at."""

    name: str
    arrivals_ms: list[float]
    judged_at_ms: float
    #: What the F17 COMPARATOR says about this population. Every arm that names
    #: it requires it to DISAGREE with the detector.
    mean_verdict_stale: bool


def _populations(threshold_ms: float) -> tuple[_Population, _Population]:
    """The two counter-examples. Built from the REAL threshold, never a literal.

    BRISK-THEN-DEAD: `FLOORS["brisk_arrivals"]`x3 arrivals at a third of the
    threshold, then `F17_SILENCE_MS` of nothing.
    SPARSE-BUT-CURRENT: three arrivals an hour apart, then a reading a tenth of
    the threshold ago.
    """
    brisk_n = FLOORS["brisk_arrivals"] * 3
    brisk_gap = threshold_ms / 3.0
    brisk = [i * brisk_gap for i in range(brisk_n)]
    dead_at = brisk[-1] + F17_SILENCE_MS

    hour_ms = 3_600_000.0
    sparse = [0.0, hour_ms, 2 * hour_ms]
    current_at = sparse[-1] + threshold_ms / 10.0

    return (
        _Population(
            name="BRISK-THEN-DEAD",
            arrivals_ms=brisk,
            judged_at_ms=dead_at,
            # the mean gap is a third of the threshold, so a mean-based
            # detector calls this feed FRESH -- which is F17.
            mean_verdict_stale=_mean_interval_ms(brisk) > threshold_ms,
        ),
        _Population(
            name="SPARSE-BUT-CURRENT",
            arrivals_ms=sparse,
            judged_at_ms=current_at,
            mean_verdict_stale=_mean_interval_ms(sparse) > threshold_ms,
        ),
    )


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


def _build_tracker(subject: _Subject, values: dict, clock: _Clock) -> tuple[Any, Any]:
    """`(policy, tracker)` built from the REAL config through the REAL loader."""
    policy = subject.freshness.StalenessPolicy.from_values(values)
    return policy, subject.freshness.FreshnessTracker(policy, clock=clock)


def _drive(
    subject: _Subject,
    values: dict,
    population: _Population,
    symbol: str,
) -> tuple[Any, Any]:
    """Replay one population into a fresh tracker. Returns `(reading, port)`.

    Every OTHER configured feed is stamped fresh at the judged instant, so the
    port's verdict isolates the feed under test. Leaving them unobserved would
    make every drive block on the never-observed rule and the two halves would
    become indistinguishable -- which is the arm passing while measuring
    nothing, one layer inside the gate.
    """
    clock = _Clock()
    policy, tracker = _build_tracker(subject, values, clock)
    stamp_cls = subject.seam.FreshnessStamp
    for seq, offset in enumerate(population.arrivals_ms):
        arrival = clock.set_ms(offset)
        tracker.observe(
            stamp_cls(feed=DRIVE_FEED, as_of=arrival, source_seq=seq), symbol
        )
    judged = clock.set_ms(population.judged_at_ms)
    for feed in policy.feeds:
        if feed != DRIVE_FEED:
            tracker.observe(stamp_cls(feed=feed, as_of=judged, source_seq=1), symbol)
    port = subject.freshness.StalenessFlagPort(tracker)
    return tracker.reading(DRIVE_FEED, symbol), port


def _arm_policy(subject: _Subject, values: dict) -> tuple[list[Finding], dict, str]:
    """ARM POLICY: the §12A knobs load from the SHIPPED config, and hold."""
    try:
        policy = subject.freshness.StalenessPolicy.from_values(values)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            [],
            {},
            (
                f"{REL_CONFIG} would not load through "
                f"{REL_FRESHNESS}:StalenessPolicy.from_values: "
                f"{type(exc).__name__}: {exc} (§17)"
            ),
        )
    feeds = policy.feeds
    if len(feeds) < FLOORS["feeds"]:
        return (
            [],
            {},
            (
                f"{REL_CONFIG} declares {len(feeds)} feed threshold(s) {list(feeds)}, "
                f"below the non-vacuity floor of {FLOORS['feeds']} -- §12A "
                "enumerates MARGIN/CALENDAR/PRICE/BALANCE, and a policy that lost "
                "one leaves a feed ungated rather than gated more loosely "
                "(doctrine C.4, §17)"
            ),
        )
    findings: list[Finding] = []
    if DRIVE_FEED not in feeds:
        return (
            [],
            {},
            (
                f"{REL_CONFIG} carries no {DRIVE_FEED!r} threshold, so every drive "
                "below would run against a feed nobody configured"
            ),
        )
    threshold = policy.threshold_ms(DRIVE_FEED)
    ladder = policy.retry.total_ms
    tightest = min(policy.threshold_ms(f) for f in feeds)
    if ladder >= tightest:
        findings.append(
            Finding(
                f"{REL_CONFIG}:retry_backoff",
                f"the retry ladder totals {ladder:.0f} ms, which is not shorter "
                f"than the tightest threshold {tightest:.0f} ms -- the declared "
                "threshold stops being the quantity that bounds detection, and "
                "§6.4's halt lands at a latency nobody configured",
            )
        )
    if F17_SILENCE_MS <= threshold * 2:
        return (
            findings,
            {},
            (
                f"the F17 silence of {F17_SILENCE_MS:.0f} ms is not comfortably past "
                f"the configured {DRIVE_FEED} threshold of {threshold:.0f} ms, so the "
                "stale drive below would be a marginal overshoot that any comparator "
                "catches -- unmeasured, not proven (§17)"
            ),
        )
    stats = {
        "feeds": list(feeds),
        "threshold_ms": threshold,
        "deadline_ms": policy.deadline_ms(DRIVE_FEED),
        "ladder_ms": ladder,
        "skew_max_ms": policy.clock_skew_max_ms,
    }
    return findings, stats, ""


def _arm_stale_fires(
    subject: _Subject, values: dict, stats: dict
) -> tuple[list[Finding], str]:
    """ARM STALE: a GENUINELY STALE feed blocks, and the mean comparator does not."""
    brisk, _ = _populations(stats["threshold_ms"])
    if len(brisk.arrivals_ms) < FLOORS["brisk_arrivals"]:
        return [], (
            f"the brisk population holds {len(brisk.arrivals_ms)} arrival(s), "
            f"below the floor of {FLOORS['brisk_arrivals']} -- a 'session mean' "
            "over a handful of samples is not the F17 defect (C.4, §17)"
        )
    silence_ms = brisk.judged_at_ms - brisk.arrivals_ms[-1]
    if silence_ms < FLOORS["stale_drive_ms"]:
        return [], (
            f"the stale drive is only {silence_ms:.0f} ms of silence, below the "
            f"floor of {FLOORS['stale_drive_ms']} ms (the F17 figure) -- a "
            "marginal overshoot does not discriminate between a "
            "time-since-last-arrival detector and a mean (§17)"
        )
    reading, port = _drive(subject, values, brisk, DRIVE_SYMBOL)
    findings: list[Finding] = []
    if not reading.blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"a feed silent for {silence_ms:.0f} ms against a "
                f"{stats['threshold_ms']:.0f} ms threshold was NOT blocked "
                f"(state={reading.state}, age={reading.age_ms}) -- this is ARC "
                "022 F17 exactly: the detector agrees with a dead feed",
            )
        )
    blocked, reason = port.read(DRIVE_SYMBOL)
    if not blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:StalenessFlagPort.read",
                "the flag port did not block on the dead feed the tracker "
                "measured -- the port is what `gate.SymbolFlagRule` dispatches, "
                "so a correct tracker behind a clear port halts nothing",
            )
        )
    for token in ("LAST ARRIVAL", f"{silence_ms:.0f} ms"):
        if token not in reason:
            findings.append(
                Finding(
                    f"{REL_FRESHNESS}:StalenessFlagPort.read",
                    f"the denial reason does not name {token!r}: {reason!r}. "
                    "Check contract v2 rule 11: a control asserts the REASON, "
                    "and a denial that cannot say how old the data is sends an "
                    "operator looking for the wrong fault",
                )
            )
    if brisk.mean_verdict_stale:
        return findings, (
            "the F17 mean comparator AGREED with the detector on the "
            "brisk-then-dead population, so this drive no longer discriminates "
            "between a mean and a time-since-last-arrival measure -- the arm is "
            "unmeasured rather than passed (§17)"
        )
    return findings, ""


def _arm_fresh_does_not_fire(
    subject: _Subject, values: dict, stats: dict
) -> tuple[list[Finding], str]:
    """ARM FRESH: a SLOW-BUT-FRESH feed does NOT block, though the mean says stale."""
    _, sparse = _populations(stats["threshold_ms"])
    reading, port = _drive(subject, values, sparse, OTHER_SYMBOL)
    findings: list[Finding] = []
    age = sparse.judged_at_ms - sparse.arrivals_ms[-1]
    if reading.blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"a feed whose LAST ARRIVAL was {age:.0f} ms ago -- inside its "
                f"{stats['threshold_ms']:.0f} ms threshold -- was BLOCKED "
                f"(state={reading.state}): {reading.reason!r}. A slow feed is "
                "not a stale one, and halting on it flattens a healthy book",
            )
        )
    blocked, reason = port.read(OTHER_SYMBOL)
    if blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:StalenessFlagPort.read",
                f"the flag port blocked a slow-but-fresh feed: {reason!r}",
            )
        )
    if not sparse.mean_verdict_stale:
        return findings, (
            "the F17 mean comparator did NOT call the sparse-but-current "
            "population stale, so this drive no longer demonstrates the "
            "inversion it exists to demonstrate (§17)"
        )
    return findings, ""


def _arm_retry_window(
    subject: _Subject, values: dict, stats: dict
) -> tuple[list[Finding], str]:
    """ARM RETRY: §6.4 declares stale only AFTER retry/backoff."""
    clock = _Clock()
    _, tracker = _build_tracker(subject, values, clock)
    stamp_cls = subject.seam.FreshnessStamp
    arrival = clock.set_ms(0.0)
    tracker.observe(
        stamp_cls(feed=DRIVE_FEED, as_of=arrival, source_seq=1), DRIVE_SYMBOL
    )

    findings: list[Finding] = []
    threshold, deadline = stats["threshold_ms"], stats["deadline_ms"]
    inside = threshold + (deadline - threshold) / 2.0
    clock.set_ms(inside)
    mid = tracker.reading(DRIVE_FEED, DRIVE_SYMBOL)
    if mid.blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"a feed {inside:.0f} ms old blocked while still inside the "
                f"retry/backoff window that ends at {deadline:.0f} ms -- §6.4 "
                "puts the halt behind the retries, and halting in front of them "
                "makes the configured RETRY_BACKOFF decorative",
            )
        )
    if str(mid.state).rsplit(".", maxsplit=1)[-1] != "STALE":
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"a feed {inside:.0f} ms old, past its {threshold:.0f} ms "
                f"threshold, reported state={mid.state} rather than STALE -- the "
                "observation and the halt are different questions and the cache "
                "cannot report the first",
            )
        )
    clock.set_ms(deadline + 1.0)
    past = tracker.reading(DRIVE_FEED, DRIVE_SYMBOL)
    if not past.blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"a feed {deadline + 1:.0f} ms old did not block, though the "
                f"retry ladder ended at {deadline:.0f} ms -- the retries have "
                "run and §6.4's halt has nothing left to wait for",
            )
        )
    return findings, ""


def _arm_empty_and_future(
    subject: _Subject, values: dict, stats: dict
) -> tuple[list[Finding], str]:
    """ARM EMPTY: never-observed blocks; a FUTURE-dated stamp blocks."""
    clock = _Clock()
    _, tracker = _build_tracker(subject, values, clock)
    port = subject.freshness.StalenessFlagPort(tracker)
    findings: list[Finding] = []

    blocked, reason = port.read(DRIVE_SYMBOL)
    if not blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:StalenessFlagPort.read",
                "a tracker that has NEVER observed anything reported clear -- an "
                "unstarted or wedged poller would be indistinguishable from a "
                "quiet healthy one, and §6.4 makes that a halt-and-flatten (§17)",
            )
        )
    elif "NEVER" not in reason:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:StalenessFlagPort.read",
                f"the empty-cache denial does not distinguish never-observed "
                f"from stale: {reason!r}. The two send an operator to different "
                "places (rule 11)",
            )
        )

    ahead_ms = stats["skew_max_ms"] * 10.0
    stamp_cls = subject.seam.FreshnessStamp
    future = clock.EPOCH + timedelta(milliseconds=ahead_ms)
    tracker.observe(
        stamp_cls(feed=DRIVE_FEED, as_of=future, source_seq=1), DRIVE_SYMBOL
    )
    clock.set_ms(0.0)
    reading = tracker.reading(DRIVE_FEED, DRIVE_SYMBOL)
    if not reading.blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"a source stamp {ahead_ms:.0f} ms AHEAD of the local clock did "
                "not block. A future-dated stamp never ages, so the feed reads "
                "fresh forever -- the safety property inverted rather than "
                "weakened",
            )
        )
    elif "AHEAD" not in reading.reason:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.reading",
                f"the future-stamp denial reads as ordinary staleness: "
                f"{reading.reason!r}. The fault is a clock or a venue, and a "
                "reason that says 'stale' sends the operator to the feed",
            )
        )
    return findings, ""


_SKEW_SITE = f"{REL_FRESHNESS}:ClockSkewMonitor.read"


def _skew_at(obs_cls, now, off_ms: float, taken_at=None):
    """One SkewObservation `off_ms` behind the reference, taken at `taken_at`."""
    return obs_cls(
        local=now,
        reference=now - timedelta(milliseconds=off_ms),
        source="exchange",
        observed_at=taken_at if taken_at is not None else now,
    )


def _clock_unobserved(monitor) -> list[Finding]:
    """A monitor that has taken NO reading has not proven the clock."""
    blocked, _ = monitor.read()
    if blocked:
        return []
    return [
        Finding(
            _SKEW_SITE,
            "a monitor that has taken NO skew observation reported the clock "
            "clear. §12.3 makes every blackout clock-driven, so an unverified "
            "clock is a stale-class HALT (§17)",
        )
    ]


def _clock_good(monitor, obs_cls, now, good_ms: float, ceiling: float) -> list[Finding]:
    """UNSKEWED must NOT halt. Without this half the arm is satisfied by a
    monitor that blocks unconditionally."""
    monitor.observe(_skew_at(obs_cls, now, good_ms))
    blocked, reason = monitor.read()
    if not blocked:
        return []
    return [
        Finding(
            _SKEW_SITE,
            f"a clock {good_ms:.0f} ms off, well inside "
            f"CLOCK_SKEW_MAX_MS={ceiling:.0f} ms, was HALTed: {reason!r}. A "
            "monitor that blocks on a good clock halts the book on chrony's "
            "ordinary jitter",
        )
    ]


def _clock_skewed(
    monitor, obs_cls, now, bad_ms: float, ceiling: float
) -> list[Finding]:
    """SKEWED must halt, and the denial must NAME the skew (rule 11)."""
    monitor.observe(_skew_at(obs_cls, now, bad_ms))
    blocked, reason = monitor.read()
    if not blocked:
        return [
            Finding(
                _SKEW_SITE,
                f"a clock {bad_ms:.0f} ms off, past "
                f"CLOCK_SKEW_MAX_MS={ceiling:.0f} ms, did not HALT -- §12.3: "
                "skew > threshold => stale-class HALT",
            )
        ]
    return [
        Finding(
            _SKEW_SITE,
            f"the skew denial does not name {token!r}: {reason!r} "
            "(rule 11: assert the REASON)",
        )
        for token in ("§12.3", f"{bad_ms:.0f} ms")
        if token not in reason
    ]


def _clock_aged(monitor, obs_cls, clock, skews: tuple[float, float]):
    """An AGED observation must halt: a clock proven once is not proven now.

    `skews` is `(good_ms, holding_ceiling_ms)` as one argument rather than two,
    because they are read together and nothing here uses one without the other.
    """
    good_ms, ceiling_ms = skews
    now = clock.set_ms(0.0)
    monitor.observe(_skew_at(obs_cls, now, good_ms))
    clock.set_ms(ceiling_ms * 2.0)
    blocked, _ = monitor.read()
    if blocked:
        return []
    return [
        Finding(
            _SKEW_SITE,
            f"a skew observation {ceiling_ms * 2:.0f} ms old, past its "
            f"{ceiling_ms:.0f} ms holding ceiling, still reported the clock "
            "clear -- the clock was good once, which is not a measurement of "
            "now (§17)",
        )
    ]


def _arm_clock(
    subject: _Subject, values: dict, stats: dict
) -> tuple[list[Finding], str]:
    """ARM CLOCK (§12.3): skewed HALTs, unskewed does not, unseen HALTs.

    Four controls, and each is another's control: a monitor that blocks on
    everything fails the good-clock half, one that blocks on nothing fails the
    other three.
    """
    clock = _Clock()
    policy, _ = _build_tracker(subject, values, clock)
    ceiling_ms = stats["threshold_ms"]
    monitor = subject.freshness.ClockSkewMonitor(
        policy, clock=clock, observation_max_age_ms=ceiling_ms
    )
    obs_cls = subject.freshness.SkewObservation
    skew_max = stats["skew_max_ms"]
    good, bad = skew_max / 5.0, skew_max * 4.0
    now = clock.set_ms(0.0)

    findings = _clock_unobserved(monitor)
    findings += _clock_good(monitor, obs_cls, now, good, skew_max)
    findings += _clock_skewed(monitor, obs_cls, now, bad, skew_max)
    findings += _clock_aged(monitor, obs_cls, clock, (good, ceiling_ms))
    return findings, ""


def _arm_utc(subject: _Subject, values: dict) -> tuple[list[Finding], str]:
    """ARM UTC (§12.3): a naive or offset instant is REFUSED at the boundary."""
    clock = _Clock()
    _, tracker = _build_tracker(subject, values, clock)
    stamp_cls = subject.seam.FreshnessStamp
    naive_error = subject.freshness.NaiveInstantError
    findings: list[Finding] = []

    naive = clock.EPOCH.replace(tzinfo=None)
    try:
        tracker.observe(
            stamp_cls(feed=DRIVE_FEED, as_of=naive, source_seq=1), DRIVE_SYMBOL
        )
    except naive_error:
        pass
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:_utc",
                f"a NAIVE instant raised {type(exc).__name__} rather than "
                "NaiveInstantError -- §12.3's UTC rule has to be refused by "
                "name or a caller cannot distinguish it from any other fault",
            )
        )
    else:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.observe",
                "a NAIVE datetime was ACCEPTED as a source stamp. §12.3: 'All "
                "internal time is UTC'. An age computed from a naive instant has "
                "units that depend on the host's local zone, so every threshold "
                "in §12A silently means something else",
            )
        )
    return findings, ""


def _arm_guard(subject: _Subject, values: dict) -> tuple[list[Finding], str]:
    """ARM GUARD (§6.4b): older readings are DISCARDED, and the guard is PER KEY."""
    clock = _Clock()
    _, tracker = _build_tracker(subject, values, clock)
    stamp_cls = subject.seam.FreshnessStamp
    findings: list[Finding] = []

    newer = clock.set_ms(10_000.0)
    older = clock.EPOCH
    tracker.observe(stamp_cls(feed=DRIVE_FEED, as_of=newer, source_seq=2), DRIVE_SYMBOL)
    before = tracker.guard.discarded_older
    admitted = tracker.observe(
        stamp_cls(feed=DRIVE_FEED, as_of=older, source_seq=1), DRIVE_SYMBOL
    )
    if admitted:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:SourceMonotonicGuard.admit",
                "a reading OLDER than the one held was ADMITTED. §6.4b: the "
                "guard accepts a value only if it is newer than the one it "
                "holds; anything older is discarded, not applied -- so a late "
                "venue packet would move a per-symbol reading backwards and "
                "mislead sizing",
            )
        )
    if tracker.guard.discarded_older != before + 1:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:SourceMonotonicGuard.discarded_older",
                "the discard was not COUNTED. A guard that cannot say it fired "
                "can only be believed, and `discarded_older` is the only "
                "externally visible evidence §6.4b's rule ever ran",
            )
        )
    held = tracker.held(DRIVE_FEED, DRIVE_SYMBOL)
    if held is not None and held.as_of != newer:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:SourceMonotonicGuard",
                f"the held stamp regressed to {held.as_of.isoformat()} after a "
                "discarded reading -- discarded must mean NOT APPLIED",
            )
        )

    # PER KEY: a late update on one symbol must not touch another.
    tracker.observe(stamp_cls(feed=DRIVE_FEED, as_of=newer, source_seq=2), OTHER_SYMBOL)
    tracker.observe(stamp_cls(feed=DRIVE_FEED, as_of=older, source_seq=1), DRIVE_SYMBOL)
    other = tracker.held(DRIVE_FEED, OTHER_SYMBOL)
    if other is None or other.as_of != newer:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:feed_key",
                f"a late update on {DRIVE_SYMBOL!r} regressed {OTHER_SYMBOL!r} "
                "-- §6.4b makes the guard PER KEY so that cannot happen",
            )
        )

    # An equal instant is not NEWER.
    before = tracker.guard.discarded_older
    tracker.observe(stamp_cls(feed=DRIVE_FEED, as_of=newer, source_seq=2), OTHER_SYMBOL)
    if tracker.guard.discarded_older != before + 1:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:SourceMonotonicGuard._is_newer",
                "a reading with an IDENTICAL source instant and sequence was "
                "admitted. §6.4b accepts a value ONLY if it is newer, so a venue "
                "re-sending the same reading must not be able to refresh its own "
                "age -- which would make a dead feed immortal",
            )
        )
    return findings, ""


def _protocol_findings(gate, ports) -> tuple[list[Finding], str]:
    """Each port structurally satisfies the `runtime_checkable` Protocol
    `gate.py` declares for the rule that dispatches it."""
    findings: list[Finding] = []
    for obj, proto in ports:
        declared = getattr(gate, proto, None)
        if declared is None:
            return [], (
                f"{REL_GATE} declares no {proto} -- the port this module "
                "implements does not exist in the gate it is meant to feed (§17)"
            )
        if not isinstance(obj, declared):
            findings.append(
                Finding(
                    f"{REL_FRESHNESS}:{type(obj).__name__}",
                    f"does not satisfy {REL_GATE}:{proto}. The rule that would "
                    "dispatch it cannot be constructed, so the condition this "
                    "module produces reaches no gate",
                )
            )
    return findings, ""


def _empty_order(limiter_seam):
    """A minimal `ProposedOrder`. Both rules are SIZE_INDEPENDENT, so nothing
    in it is consulted -- it exists because the verb takes one."""
    return limiter_seam.ProposedOrder(
        client_order_id="c1",
        strategy_id="s1",
        symbol=DRIVE_SYMBOL,
        side=limiter_seam.Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=10,
        stop_mode=next(iter(limiter_seam.StopMode)),
        signal_ts=0.0,
    )


def _rule_findings(limiter_seam, rules, order) -> list[Finding]:
    """Each SHIPPED rule DENIES, and names a reason, when its port blocks.

    `picture` is `None` on purpose: `SymbolFlagRule.evaluate` deletes it on its
    first line, and a fabricated financial picture here would suggest one is
    consulted.
    """
    findings: list[Finding] = []
    for rule in rules:
        verdict = rule.evaluate(order, None)
        if verdict.decision is not limiter_seam.Decision.DENY:
            findings.append(
                Finding(
                    f"{REL_GATE}:{rule.name}",
                    f"an EMPTY cache and an UNOBSERVED clock produced "
                    f"{verdict.decision} rather than DENY. The port blocks and "
                    "the rule does not, so the halt condition is produced and "
                    "then dropped between the two",
                )
            )
        elif not verdict.reason:
            findings.append(
                Finding(
                    f"{REL_GATE}:{rule.name}",
                    "denied with an EMPTY reason -- §3 requires a denial to be "
                    "actionable, and the port's reason is the only account "
                    "anything downstream receives",
                )
            )
    return findings


def _arm_port(
    subject: _Subject, values: dict, stats: dict
) -> tuple[list[Finding], int, str]:
    """ARM PORT: the SHIPPED `gate.py` rules deny when these ports block.

    The property measured is *the gate denies*, not *a method returns True*: a
    perfectly correct `read()` that no rule dispatches produces no halt.
    """
    gate, limiter_seam = subject.gate, subject.limiter_seam
    clock = _Clock()
    policy, tracker = _build_tracker(subject, values, clock)
    stale_port = subject.freshness.StalenessFlagPort(tracker)
    skew_port = subject.freshness.ClockSkewMonitor(
        policy, clock=clock, observation_max_age_ms=stats["threshold_ms"]
    )
    findings, cannot = _protocol_findings(
        gate, ((stale_port, "SymbolFlagPort"), (skew_port, "GlobalFlagPort"))
    )
    if cannot:
        return [], 0, cannot
    rules = (
        gate.SymbolFlagRule("data_staleness", stale_port, "§6.4 stale-data halt"),
        gate.GlobalFlagRule("clock_skew", skew_port, "§12.3 clock integrity"),
    )
    findings += _rule_findings(limiter_seam, rules, _empty_order(limiter_seam))
    if len(rules) < FLOORS["rules_driven"]:
        return (
            findings,
            len(rules),
            (
                f"only {len(rules)} rule(s) were driven, below the floor of "
                f"{FLOORS['rules_driven']} -- both §3 phase-A bullets this module "
                "produces must be exercised (§17)"
            ),
        )
    return findings, len(rules), ""


def _imported_names(tree: ast.AST) -> list[tuple[int, str]]:
    """Every module name this file imports, with the line it sits on."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.lineno, node.module or ""))
    return found


def _banned_reason(name: str, banned: dict[str, str]) -> str:
    """The reason `name` is banned, or `""`. Prefix match, so a submodule counts."""
    for bad, why in banned.items():
        if name == bad or name.startswith(f"{bad}."):
            return why
    return ""


def _arm_purity(home: Path) -> tuple[list[Finding], int, str]:
    """ARM PURITY: `freshness.py` imports no I/O and does NOT import `pollers`.

    Structural, and it is the enforcement of the module's own central argument:
    fail-closed detection must not depend on the machinery it is watching. A
    detector that imported the poller would be reachable only through the
    object whose stall it exists to report.
    """
    try:
        tree = ast.parse((home / REL_FRESHNESS).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [], 0, f"{REL_FRESHNESS} could not be parsed: {exc} (§17)"
    banned = {
        "asyncio": "the detector must answer while the machinery it watches is wedged",
        "socket": "no I/O on a fail-closed detector's path",
        "subprocess": "no I/O on a fail-closed detector's path",
        "time": "the clock is INJECTED; a detector reading the wall clock can "
        "only be tested by waiting, and a 900-second staleness cannot be driven",
        "nixrisk.pollers": "the dependency runs one way -- the poller imports the "
        "detector, never the reverse",
    }
    findings: list[Finding] = []
    seen = 0
    for lineno, name in _imported_names(tree):
        seen += 1
        why = _banned_reason(name, banned)
        if why:
            findings.append(
                Finding(f"{REL_FRESHNESS}:{lineno}", f"imports {name!r}: {why}")
            )
    if seen == 0:
        return (
            findings,
            seen,
            (
                f"{REL_FRESHNESS} declares no import at all -- an import scan over "
                "a module with no imports finds no banned one and would report PASS "
                "(§17)"
            ),
        )
    return findings, seen, ""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _all_arms(subject: _Subject, values: dict) -> tuple[list[Finding], dict, str]:
    findings: list[Finding] = []
    stats: dict = {"arms": 0}

    policy_findings, policy_stats, cannot = _arm_policy(subject, values)
    findings += policy_findings
    if cannot:
        return findings, stats, cannot
    stats.update(policy_stats)
    stats["arms"] += 1

    for three_arg in (
        _arm_stale_fires,
        _arm_fresh_does_not_fire,
        _arm_retry_window,
        _arm_empty_and_future,
        _arm_clock,
    ):
        arm_findings, cannot = three_arg(subject, values, stats)
        findings += arm_findings
        if cannot:
            return findings, stats, cannot
        stats["arms"] += 1

    # Written out rather than looped: these two take `(subject, values)` and
    # the five above take `(subject, values, stats)`. A loop over both shapes
    # needs a cast to run at all, and a cast is a claim about a signature made
    # in the one place a type checker stops reading it.
    for two_arg in (_arm_utc, _arm_guard):
        arm_findings, cannot = two_arg(subject, values)
        findings += arm_findings
        if cannot:
            return findings, stats, cannot
        stats["arms"] += 1

    port_findings, stats["rules"], cannot = _arm_port(subject, values, stats)
    findings += port_findings
    if cannot:
        return findings, stats, cannot
    stats["arms"] += 1
    return findings, stats, ""


def _pass(stats: dict) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=(
            f"{stats['arms']} arms over {REL_FRESHNESS} driven from "
            f"{REL_CONFIG}'s own numbers ({len(stats['feeds'])} feeds "
            f"{stats['feeds']}, {DRIVE_FEED} threshold "
            f"{stats['threshold_ms']:.0f} ms, retry ladder "
            f"{stats['ladder_ms']:.0f} ms, deadline {stats['deadline_ms']:.0f} ms, "
            f"CLOCK_SKEW_MAX_MS {stats['skew_max_ms']:.0f} ms). "
            f"STALE: a feed silent for {F17_SILENCE_MS:.0f} ms (the ARC 022 F17 "
            "figure) BLOCKS, while the F17 session-mean comparator on the same "
            "population calls it fresh. FRESH: a sparse feed whose last arrival "
            "is inside the threshold does NOT block, while the same comparator "
            "calls it stale. The measure is TIME SINCE LAST ARRIVAL -- never a "
            "count, never a mean. RETRY: past-threshold reports STALE and does "
            "not halt until the retry deadline. CLOCK: unobserved HALTs, "
            "unskewed does NOT, skewed HALTs, an aged observation HALTs. "
            f"GUARD: §6.4b discards older readings per key. PORT: {stats['rules']} "
            "shipped gate rules DENY on these ports. PURITY: "
            f"{stats['imports']} imports scanned, no I/O and no poller import. "
            "NOT MEASURED HERE: the pollers themselves (check_pollers), and any "
            "staleness a non-Python or out-of-process producer might introduce"
        ),
    )


def _measure(home: Path) -> CheckResult:
    """Everything `run` does, minus the catch-all. Split so the fail-closed
    boundary is one expression and this function is one story."""
    absent = _subject_defects(home)
    if absent is not None:
        return absent
    values, error = _config_values(home)
    if error:
        return _cannot(f"{error} (§17)")
    # ARM PURITY runs BEFORE the import, and that ordering is the arm's own
    # subject: a detector that imports the poller it watches is a CIRCULAR
    # import, so a purity arm scheduled after `load_subject` would be reported
    # as an unloadable module rather than as the coupling it is. The arm is
    # pure AST and needs no import to run.
    purity_findings, imports, purity_cannot = _arm_purity(home)
    subject, complaint = load_subject(home)
    if subject is None:
        # FAIL outranks CANNOT_MEASURE: a violation already MEASURED stays
        # measured when a later stage loses its subject.
        return _fail(purity_findings) if purity_findings else _cannot(complaint)
    findings, stats, cannot = _all_arms(subject, values)
    stats["imports"] = imports
    if not purity_cannot:
        stats["arms"] += 1
    return _verdict(purity_findings + findings, stats, cannot or purity_cannot)


def _verdict(findings: list[Finding], stats: dict, cannot: str) -> CheckResult:
    """The check contract's aggregate ordering, applied WITHIN this check.

    `Fail > Cannot-measure > Guarded > Pass`: a violation an earlier arm
    MEASURED stays measured when a later arm loses its subject.
    """
    if findings:
        return _fail(findings)
    if cannot:
        return _cannot(cannot)
    if stats["arms"] < FLOORS["arms"]:
        return _cannot(
            f"only {stats['arms']} of {FLOORS['arms']} arms ran -- a partial "
            "sweep certifies nothing (§17)"
        )
    return _pass(stats)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Nine arms over the freshness detector, driven from the shipped config."""
    try:
        return _measure(Path(ctx.nix_home))
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
